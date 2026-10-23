"""Validated, versioned tariff schema v1 (R3, WP3).

A *tariff* (``tariff_id``, e.g. ``sc1_rate1``) has one or more dated
*versions*. Each version is one YAML file under ``tariffs/v1/<tariff_id>/``
and states its effective dates, verification status, sources, charge
components and excluded components. Parsing is strict: unknown keys,
misspellings, wrong types, non-finite values, bad units, bad dates or months,
duplicate component IDs, malformed blocks and invalid windows all raise
:class:`~coned_billing.errors.TariffSchemaError` naming the offending field.

The schema is documented in ``docs/tariff_schema.md``. Billing with these
versions arrives in WP5; this module provides the data model, validation and
version selection.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import yaml

from .calendars import TARIFF_TZ
from .errors import ConEdBillingError, TariffSchemaError, TariffSelectionError
from .loader import _parse_time
from .models import TimeWindow

__all__ = [
    "CATEGORIES",
    "SCHEMA_VERSION",
    "Block",
    "Citation",
    "Component",
    "DemandMeasurement",
    "ExcludedComponent",
    "Proration",
    "SourceDocument",
    "TariffRegistry",
    "TariffVersion",
    "default_registry",
    "load_sources",
    "load_tariff_version",
]

SCHEMA_VERSION = 1

VerificationStatus = Literal["unverified", "transcribed", "owner_verified", "bill_reconciled"]
VERIFICATION_STATUSES: tuple[str, ...] = (
    "unverified",
    "transcribed",
    "owner_verified",
    "bill_reconciled",
)
CalculationMode = Literal["historical", "scenario"]
CALCULATION_MODES = ("historical", "scenario")
VOLTAGES = ("low_tension", "high_tension")

#: Rate units accepted by the schema, with the factor that converts them to USD.
UNIT_TO_USD: dict[str, float] = {
    "USD/month": 1.0,
    "USD/kWh": 1.0,
    "cents/kWh": 0.01,
    "USD/kW": 1.0,
}
_ENERGY_UNITS = frozenset({"USD/kWh", "cents/kWh"})
_DEMAND_UNITS = frozenset({"USD/kW"})
_FIXED_UNITS = frozenset({"USD/month"})


@dataclass(frozen=True, slots=True)
class _Category:
    units: frozenset[str]
    determinants: frozenset[str]
    sign: Literal["nonnegative", "nonpositive", "any"]


#: Component categories (spec 6.2) with their allowed units, billing
#: determinants and sign rule. Credits must be <= 0; adjustments may take
#: either sign; every other category must be >= 0.
CATEGORIES: dict[str, _Category] = {
    "fixed_charge": _Category(_FIXED_UNITS, frozenset({"billing_period"}), "nonnegative"),
    "minimum_charge": _Category(_FIXED_UNITS, frozenset({"billing_period"}), "nonnegative"),
    "delivery_energy": _Category(_ENERGY_UNITS, frozenset({"kwh"}), "nonnegative"),
    "supply_energy": _Category(_ENERGY_UNITS, frozenset({"kwh"}), "nonnegative"),
    "merchant_charge": _Category(_ENERGY_UNITS, frozenset({"kwh"}), "nonnegative"),
    "delivery_demand": _Category(_DEMAND_UNITS, frozenset({"max_demand_kw"}), "nonnegative"),
    "supply_demand": _Category(_DEMAND_UNITS, frozenset({"max_demand_kw"}), "nonnegative"),
    "adjustment": _Category(
        _FIXED_UNITS | _ENERGY_UNITS | _DEMAND_UNITS,
        frozenset({"billing_period", "kwh", "max_demand_kw"}),
        "any",
    ),
    "credit": _Category(
        _FIXED_UNITS | _ENERGY_UNITS | _DEMAND_UNITS,
        frozenset({"billing_period", "kwh", "max_demand_kw"}),
        "nonpositive",
    ),
}
_UNIT_FOR_DETERMINANT = {
    "billing_period": _FIXED_UNITS,
    "kwh": _ENERGY_UNITS,
    "max_demand_kw": _DEMAND_UNITS,
}

#: Block proration rules (spec 6.2). ``bounds_days_over_30``: block bounds are
#: scaled by elapsed days / 30 (GR 10.5.2, kWh blocks); ``total_days_over_30``:
#: the block charges are totalled, then scaled by elapsed days / 30 (GR 10.5.2,
#: kW blocks); ``reject_partial_periods``: no rule found, so a billing period of
#: other than 30 days is rejected.
BLOCK_PRORATION_RULES = ("bounds_days_over_30", "total_days_over_30", "reject_partial_periods")
#: Proration of whole-component charges (GR 10.5.2).
PRORATION_RULES = ("days_over_30", "none")

_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_VERSION = re.compile(r"^(legacy|\d{4}-\d{2}-\d{2}(-r\d+)?)$")
_PACKAGE_V1 = "tariffs/v1"


# ─────────────────────────────── strict parsing ───────────────────────────────
class _Ctx:
    """Location of a value inside a file, for error messages."""

    def __init__(self, where: str) -> None:
        self.where = where

    def __truediv__(self, key: object) -> _Ctx:
        return _Ctx(f"{self.where}.{key}" if self.where else str(key))

    def fail(self, msg: str) -> TariffSchemaError:
        return TariffSchemaError(f"{self.where}: {msg}")


def _mapping(v: object, ctx: _Ctx, required: Iterable[str], optional: Iterable[str]) -> dict:
    if not isinstance(v, Mapping):
        raise ctx.fail(f"expected a mapping, got {type(v).__name__}")
    req, opt = set(required), set(optional)
    unknown = [k for k in v if k not in req | opt]
    if unknown:
        raise ctx.fail(f"unknown key(s) {unknown}; allowed: {sorted(req | opt)}")
    missing = sorted(req - set(v))
    if missing:
        raise ctx.fail(f"missing required key(s) {missing}")
    return dict(v)


def _str(v: object, ctx: _Ctx, *, nonempty: bool = True) -> str:
    if not isinstance(v, str) or (nonempty and not v.strip()):
        raise ctx.fail(f"expected a non-empty string, got {v!r}")
    return v


def _opt_str(v: object, ctx: _Ctx) -> str | None:
    return None if v is None else _str(v, ctx)


def _int(v: object, ctx: _Ctx, *, minimum: int | None = None) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise ctx.fail(f"expected an integer, got {v!r}")
    if minimum is not None and v < minimum:
        raise ctx.fail(f"must be >= {minimum}, got {v}")
    return v


def _number(v: object, ctx: _Ctx) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ctx.fail(f"expected a number, got {v!r}")
    f = float(v)
    if not math.isfinite(f):
        raise ctx.fail(f"must be finite, got {v!r}")
    return f


def _date(v: object, ctx: _Ctx) -> date:
    # YAML parses unquoted ISO dates to datetime.date; quoted ones arrive as str.
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v)
        except ValueError:
            pass
    raise ctx.fail(f"expected an ISO date YYYY-MM-DD, got {v!r}")


def _opt_date(v: object, ctx: _Ctx) -> date | None:
    return None if v is None else _date(v, ctx)


def _choice(v: object, ctx: _Ctx, choices: Sequence[str]) -> str:
    if v not in choices:
        raise ctx.fail(f"must be one of {list(choices)}, got {v!r}")
    return str(v)


def _str_list(v: object, ctx: _Ctx) -> tuple[str, ...]:
    if v is None:
        return ()
    if not isinstance(v, list):
        raise ctx.fail(f"expected a list, got {type(v).__name__}")
    return tuple(_str(x, ctx / i) for i, x in enumerate(v))


# ─────────────────────────────── data model ───────────────────────────────────
@dataclass(frozen=True, slots=True)
class SourceDocument:
    """A primary source file tracked in ``docs/sources/`` with its checksum."""

    id: str
    title: str
    url: str
    retrieved_utc: str
    sha256: str
    file: str  # path relative to docs/sources/
    parent_file: str | None = None  # document the file was extracted from
    parent_sha256: str | None = None
    parent_page: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class Citation:
    """Where a value comes from: document, leaf, revision and page."""

    document: str
    leaf: str
    revision: int
    page: int  # 1-based page of ``document``
    text: str | None = None  # the quoted tariff wording
    method: Literal["text_layer", "page_image"] = "text_layer"


@dataclass(frozen=True, slots=True)
class Proration:
    rule: str
    source: Citation | None = None


@dataclass(frozen=True, slots=True)
class DemandMeasurement:
    """How billed demand is measured (R5; used by WP4)."""

    method: Literal["integrated_demand", "input_interval_maximum"]
    integration_minutes: int | None
    source: Citation | None = None


@dataclass(frozen=True, slots=True)
class Block:
    """One block of a tiered charge, from the previous bound up to ``up_to``.

    ``up_to`` is None for the final, unbounded block. A block whose unit is
    ``USD/month`` is a flat charge for that block (e.g. "first 5 kW (or less)
    $249.01 per month"); it is allowed only as the first block.
    """

    up_to: float | None
    rate: float
    unit: str

    @property
    def rate_usd(self) -> float:
        return self.rate * UNIT_TO_USD[self.unit]


@dataclass(frozen=True, slots=True)
class Component:
    """One charge component of a tariff version (spec 6.2)."""

    id: str
    name: str
    category: str
    determinant: str
    window: TimeWindow
    unit: str | None = None
    rate: float | None = None
    blocks: tuple[Block, ...] = ()
    block_proration: Proration | None = None
    proration: Proration | None = None
    exclusive_group: str | None = None
    demand_measurement: DemandMeasurement | None = None
    source: Citation | None = None
    notes: str | None = None

    @property
    def rate_usd(self) -> float | None:
        """The flat rate in USD per determinant unit (None for block charges)."""
        if self.rate is None or self.unit is None:
            return None
        return self.rate * UNIT_TO_USD[self.unit]

    def block_charge(self, quantity: float, *, elapsed_days: int | None = None) -> float:
        """Charge in USD for ``quantity`` billed through this component's blocks.

        ``quantity`` is the billing determinant for the period (kWh in the
        window, or kW of maximum demand). ``elapsed_days`` is the length of the
        billing period; None means a standard 30-day period. Proration follows
        ``block_proration`` (General Rule 10.5.2).
        """
        if not self.blocks:
            raise ConEdBillingError(f"component {self.id!r} has no blocks")
        q = _number(quantity, _Ctx("quantity"))
        if q < 0:
            raise ConEdBillingError(f"quantity must be >= 0, got {quantity!r}")
        days = 30 if elapsed_days is None else elapsed_days
        if isinstance(days, bool) or not isinstance(days, int) or days < 1:
            raise ConEdBillingError(f"elapsed_days must be a positive integer, got {days!r}")
        rule = self.block_proration.rule if self.block_proration else "reject_partial_periods"
        if days != 30 and rule == "reject_partial_periods":
            raise ConEdBillingError(
                f"component {self.id!r}: no proration rule is recorded for its blocks, so "
                f"a {days}-day billing period cannot be billed"
            )
        scale = days / 30 if rule == "bounds_days_over_30" else 1.0
        total, lower = 0.0, 0.0
        for b in self.blocks:
            upper = math.inf if b.up_to is None else b.up_to * scale
            if b.unit == "USD/month":
                total += b.rate_usd  # flat charge for the block, applies "(or less)"
            else:
                total += max(0.0, min(q, upper) - lower) * b.rate_usd
            lower = upper
            if q <= lower:
                break
        if rule == "total_days_over_30":
            total *= days / 30
        return total


@dataclass(frozen=True, slots=True)
class ExcludedComponent:
    """A charge the tariff requires but this version does not model."""

    id: str
    name: str
    reason: str
    source: Citation | None = None


@dataclass(frozen=True, slots=True)
class TariffVersion:
    """One dated version of a tariff (spec 6.1)."""

    tariff_id: str
    version: str
    utility: str
    jurisdiction: str
    tariff_book: str
    service_classification: str
    rate_option: str
    voltage: str | None
    zone: str | None
    timezone: str
    effective_start: date | None  # inclusive, by date of service (GR 10.5.1)
    effective_end: date | None  # exclusive; None = until superseded
    valid_as_of: date | None  # last date the sources were checked (open-ended versions)
    verification_status: str
    calculation_modes: tuple[str, ...]
    sources: tuple[str, ...]
    components: tuple[Component, ...]
    excluded_components: tuple[ExcludedComponent, ...]
    assumptions: tuple[str, ...] = ()
    eligibility: str | None = None
    required_account_inputs: tuple[str, ...] = ()
    known_overlaps: tuple[str, ...] = ()  # versions of the same tariff this one overlaps
    case: str | None = None
    notes: str | None = None
    legacy_notes: str | None = None
    path: Path | None = field(default=None, compare=False)

    @property
    def key(self) -> tuple[str, str]:
        return (self.tariff_id, self.version)

    def covers(self, day: date) -> bool:
        """Whether ``day`` lies in ``[effective_start, effective_end)``."""
        if self.effective_start is None or day < self.effective_start:
            return False
        return self.effective_end is None or day < self.effective_end

    def component(self, component_id: str) -> Component:
        for c in self.components:
            if c.id == component_id:
                return c
        raise KeyError(component_id)


# ─────────────────────────────── parsing ──────────────────────────────────────
def _citation(v: object, ctx: _Ctx) -> Citation:
    d = _mapping(v, ctx, ("document", "leaf", "revision", "page"), ("text", "method"))
    leaf = d["leaf"]
    if isinstance(leaf, bool) or not isinstance(leaf, (str, int)):
        raise (ctx / "leaf").fail(f"expected a leaf number such as '389.3', got {leaf!r}")
    return Citation(
        document=_str(d["document"], ctx / "document"),
        leaf=str(leaf),
        revision=_int(d["revision"], ctx / "revision", minimum=0),
        page=_int(d["page"], ctx / "page", minimum=1),
        text=_opt_str(d.get("text"), ctx / "text"),
        method=_choice(d.get("method", "text_layer"), ctx / "method", ("text_layer", "page_image")),  # type: ignore[arg-type]
    )


def _opt_citation(v: object, ctx: _Ctx) -> Citation | None:
    return None if v is None else _citation(v, ctx)


_WINDOW_KEYS = ("months", "weekdays_only", "start", "end")


def _window(v: object, ctx: _Ctx) -> TimeWindow:
    # v1 requires an explicit holiday set on every window (no silent default).
    d = _mapping(v, ctx, ("excluded_holidays",), _WINDOW_KEYS)
    months = d.get("months")
    if months is not None and (
        not isinstance(months, list)
        or not all(isinstance(m, int) and not isinstance(m, bool) for m in months)
    ):
        raise (ctx / "months").fail(f"expected a list of integers 1-12, got {months!r}")
    try:
        return TimeWindow(
            months=months,
            weekdays_only=d.get("weekdays_only"),
            start=_parse_time(d.get("start"), field="start"),
            end=_parse_time(d.get("end"), field="end"),
            excluded_holidays=d["excluded_holidays"],
        )
    except ConEdBillingError as exc:
        raise ctx.fail(str(exc)) from None


def _proration(v: object, ctx: _Ctx, rules: Sequence[str]) -> Proration:
    d = _mapping(v, ctx, ("rule",), ("source",))
    return Proration(
        _choice(d["rule"], ctx / "rule", rules), _opt_citation(d.get("source"), ctx / "source")
    )


def _demand_measurement(v: object, ctx: _Ctx) -> DemandMeasurement:
    d = _mapping(v, ctx, ("method",), ("integration_minutes", "source"))
    method = _choice(d["method"], ctx / "method", ("integrated_demand", "input_interval_maximum"))
    minutes = d.get("integration_minutes")
    if method == "integrated_demand":
        minutes = _int(minutes, ctx / "integration_minutes", minimum=1)
    elif minutes is not None:
        raise (ctx / "integration_minutes").fail("only allowed with method integrated_demand")
    return DemandMeasurement(method, minutes, _opt_citation(d.get("source"), ctx / "source"))  # type: ignore[arg-type]


def _blocks(v: object, ctx: _Ctx, category: _Category) -> tuple[Block, ...]:
    if not isinstance(v, list) or len(v) < 2:
        raise ctx.fail("expected a list of at least 2 blocks")
    out: list[Block] = []
    prev = 0.0
    for i, raw in enumerate(v):
        bctx = ctx / i
        d = _mapping(raw, bctx, ("up_to", "rate", "unit"), ())
        unit = _choice(d["unit"], bctx / "unit", sorted(UNIT_TO_USD))
        if unit not in category.units and not (unit == "USD/month" and i == 0):
            raise (bctx / "unit").fail(
                f"unit {unit!r} not allowed here; allowed: {sorted(category.units)}"
                + (" (USD/month only as a flat first block)" if unit != "USD/month" else "")
            )
        last = i == len(v) - 1
        up = d["up_to"]
        if last:
            if up is not None:
                raise (bctx / "up_to").fail("the last block must be unbounded (up_to: null)")
        else:
            if up is None:
                raise (bctx / "up_to").fail("only the last block may be unbounded")
            up = _number(up, bctx / "up_to")
            if up <= prev:
                raise (bctx / "up_to").fail(
                    f"block bounds must increase strictly from {prev:g}; got {up:g} "
                    "(blocks are contiguous: each starts where the previous ends)"
                )
            prev = up
        out.append(Block(up, _number(d["rate"], bctx / "rate"), unit))
    return tuple(out)


_COMPONENT_KEYS_REQ = ("id", "name", "category", "determinant", "window")
_COMPONENT_KEYS_OPT = (
    "unit",
    "rate",
    "blocks",
    "block_proration",
    "proration",
    "exclusive_group",
    "demand_measurement",
    "source",
    "notes",
)


def _component(v: object, ctx: _Ctx) -> Component:
    d = _mapping(v, ctx, _COMPONENT_KEYS_REQ, _COMPONENT_KEYS_OPT)
    cid = _str(d["id"], ctx / "id")
    if not _ID.match(cid):
        raise (ctx / "id").fail(f"must match {_ID.pattern}, got {cid!r}")
    ctx = _Ctx(f"{ctx.where}[{cid}]")
    cat_name = _choice(d["category"], ctx / "category", sorted(CATEGORIES))
    cat = CATEGORIES[cat_name]
    det = _choice(d["determinant"], ctx / "determinant", sorted(cat.determinants))
    has_rate, has_blocks = "rate" in d, "blocks" in d
    if has_rate == has_blocks:
        raise ctx.fail("give exactly one of rate (with unit) or blocks")
    unit = rate = None
    blocks: tuple[Block, ...] = ()
    if has_rate:
        unit = _choice(d.get("unit"), ctx / "unit", sorted(UNIT_TO_USD))
        if unit not in cat.units or unit not in _UNIT_FOR_DETERMINANT[det]:
            raise (ctx / "unit").fail(
                f"unit {unit!r} does not fit category {cat_name} / determinant {det}; "
                f"allowed: {sorted(cat.units & _UNIT_FOR_DETERMINANT[det])}"
            )
        rate = _number(d["rate"], ctx / "rate")
        values = [rate]
    else:
        if "unit" in d:
            raise (ctx / "unit").fail("block charges give a unit per block, not per component")
        blocks = _blocks(d["blocks"], ctx / "blocks", cat)
        values = [b.rate for b in blocks]
        if det == "billing_period":
            raise (ctx / "blocks").fail("fixed charges cannot be tiered")
        if "block_proration" not in d:
            raise ctx.fail(
                "block charges need block_proration (the tariff's partial-period rule, or "
                "rule: reject_partial_periods if none is found)"
            )
    for x in values:
        if cat.sign == "nonnegative" and x < 0:
            raise ctx.fail(f"category {cat_name} rates must be >= 0, got {x:g}")
        if cat.sign == "nonpositive" and x > 0:
            raise ctx.fail(f"category {cat_name} (a credit) must be <= 0, got {x:g}")
    if "block_proration" in d and not blocks:
        raise (ctx / "block_proration").fail("only allowed on block charges")
    demand = None
    if det == "max_demand_kw":
        if "demand_measurement" not in d:
            raise ctx.fail("demand components need demand_measurement")
        demand = _demand_measurement(d["demand_measurement"], ctx / "demand_measurement")
    elif "demand_measurement" in d:
        raise (ctx / "demand_measurement").fail("only allowed on demand components")
    group = d.get("exclusive_group")
    if group is not None and not _ID.match(_str(group, ctx / "exclusive_group")):
        raise (ctx / "exclusive_group").fail(f"must match {_ID.pattern}")
    return Component(
        id=cid,
        name=_str(d["name"], ctx / "name"),
        category=cat_name,
        determinant=det,
        window=_window(d["window"], ctx / "window"),
        unit=unit,
        rate=rate,
        blocks=blocks,
        block_proration=(
            _proration(d["block_proration"], ctx / "block_proration", BLOCK_PRORATION_RULES)
            if "block_proration" in d
            else None
        ),
        proration=(
            _proration(d["proration"], ctx / "proration", PRORATION_RULES)
            if "proration" in d
            else None
        ),
        exclusive_group=group,
        demand_measurement=demand,
        source=_opt_citation(d.get("source"), ctx / "source"),
        notes=_opt_str(d.get("notes"), ctx / "notes"),
    )


def _excluded(v: object, ctx: _Ctx) -> ExcludedComponent:
    d = _mapping(v, ctx, ("id", "name", "reason"), ("source",))
    cid = _str(d["id"], ctx / "id")
    if not _ID.match(cid):
        raise (ctx / "id").fail(f"must match {_ID.pattern}, got {cid!r}")
    return ExcludedComponent(
        cid,
        _str(d["name"], ctx / "name"),
        _str(d["reason"], ctx / "reason"),
        _opt_citation(d.get("source"), ctx / "source"),
    )


_VERSION_REQ = (
    "schema_version",
    "tariff_id",
    "version",
    "utility",
    "jurisdiction",
    "tariff_book",
    "service_classification",
    "rate_option",
    "voltage",
    "zone",
    "timezone",
    "effective",
    "verification_status",
    "calculation_modes",
    "sources",
    "components",
    "excluded_components",
)
_VERSION_OPT = (
    "valid_as_of",
    "assumptions",
    "eligibility",
    "required_account_inputs",
    "known_overlaps",
    "case",
    "notes",
    "legacy_notes",
)


def parse_tariff_version(
    data: object,
    *,
    where: str = "<tariff>",
    sources: Mapping[str, SourceDocument] | None = None,
    path: Path | None = None,
) -> TariffVersion:
    """Validate one parsed YAML mapping and return a :class:`TariffVersion`."""
    ctx = _Ctx(where)
    d = _mapping(data, ctx, _VERSION_REQ, _VERSION_OPT)
    if d["schema_version"] != SCHEMA_VERSION:
        raise (ctx / "schema_version").fail(
            f"expected {SCHEMA_VERSION}, got {d['schema_version']!r}"
        )
    tid = _str(d["tariff_id"], ctx / "tariff_id")
    if not _ID.match(tid):
        raise (ctx / "tariff_id").fail(f"must match {_ID.pattern}, got {tid!r}")
    ver = d["version"]
    if isinstance(ver, date):
        ver = ver.isoformat()
    ver = _str(ver, ctx / "version")
    if not _VERSION.match(ver):
        raise (ctx / "version").fail(f"must be 'legacy' or YYYY-MM-DD[-rN], got {ver!r}")
    tz = _str(d["timezone"], ctx / "timezone")
    if tz != TARIFF_TZ:
        raise (ctx / "timezone").fail(
            f"Con Edison tariffs are evaluated in {TARIFF_TZ}, got {tz!r}"
        )
    eff = _mapping(d["effective"], ctx / "effective", ("start", "end"), ())
    start = _opt_date(eff["start"], ctx / "effective" / "start")
    end = _opt_date(eff["end"], ctx / "effective" / "end")
    if start is None and end is not None:
        raise (ctx / "effective").fail("end given without start")
    if start is not None and end is not None and end <= start:
        raise (ctx / "effective").fail(f"end {end} must be after start {start}")
    valid_as_of = _opt_date(d.get("valid_as_of"), ctx / "valid_as_of")
    status = _choice(d["verification_status"], ctx / "verification_status", VERIFICATION_STATUSES)
    modes = _str_list(d["calculation_modes"], ctx / "calculation_modes")
    if not modes:
        raise (ctx / "calculation_modes").fail("list at least one mode")
    for i, m in enumerate(modes):
        _choice(m, ctx / "calculation_modes" / i, CALCULATION_MODES)
    if len(set(modes)) != len(modes):
        raise (ctx / "calculation_modes").fail("duplicate modes")
    if "historical" in modes:
        if start is None:
            raise (ctx / "effective").fail("historical mode needs effective dates")
        if status == "unverified":
            raise (ctx / "calculation_modes").fail(
                "an unverified version cannot be used in historical mode"
            )
        if end is None and valid_as_of is None:
            raise ctx.fail("an open-ended historical version needs valid_as_of")
    voltage = d["voltage"]
    if voltage is not None:
        _choice(voltage, ctx / "voltage", VOLTAGES)
    src_ids = _str_list(d["sources"], ctx / "sources")
    if sources is not None:
        unknown = [s for s in src_ids if s not in sources]
        if unknown:
            raise (ctx / "sources").fail(f"unknown source id(s) {unknown}")
    if not isinstance(d["components"], list) or not d["components"]:
        raise (ctx / "components").fail("expected a non-empty list")
    comps = tuple(_component(c, ctx / "components" / i) for i, c in enumerate(d["components"]))
    if not isinstance(d["excluded_components"], list):
        raise (ctx / "excluded_components").fail("expected a list (may be empty)")
    excl = tuple(
        _excluded(c, ctx / "excluded_components" / i)
        for i, c in enumerate(d["excluded_components"])
    )
    ids = [c.id for c in comps] + [c.id for c in excl]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise (ctx / "components").fail(f"duplicate component id(s) {dupes}")
    tv = TariffVersion(
        tariff_id=tid,
        version=ver,
        utility=_str(d["utility"], ctx / "utility"),
        jurisdiction=_str(d["jurisdiction"], ctx / "jurisdiction"),
        tariff_book=_str(d["tariff_book"], ctx / "tariff_book"),
        service_classification=_str(d["service_classification"], ctx / "service_classification"),
        rate_option=_str(d["rate_option"], ctx / "rate_option"),
        voltage=voltage,
        zone=_opt_str(d["zone"], ctx / "zone"),
        timezone=tz,
        effective_start=start,
        effective_end=end,
        valid_as_of=valid_as_of,
        verification_status=status,
        calculation_modes=modes,
        sources=src_ids,
        components=comps,
        excluded_components=excl,
        assumptions=_str_list(d.get("assumptions"), ctx / "assumptions"),
        eligibility=_opt_str(d.get("eligibility"), ctx / "eligibility"),
        required_account_inputs=_str_list(
            d.get("required_account_inputs"), ctx / "required_account_inputs"
        ),
        known_overlaps=_str_list(d.get("known_overlaps"), ctx / "known_overlaps"),
        case=_opt_str(d.get("case"), ctx / "case"),
        notes=_opt_str(d.get("notes"), ctx / "notes"),
        legacy_notes=_opt_str(d.get("legacy_notes"), ctx / "legacy_notes"),
        path=path,
    )
    _check_citations(tv, ctx, sources)
    _check_exclusive_groups(tv, ctx)
    return tv


def _all_citations(tv: TariffVersion) -> Iterable[tuple[str, Citation | None]]:
    for c in tv.components:
        yield c.id, c.source
        if c.block_proration is not None:
            yield f"{c.id}.block_proration", c.block_proration.source
        if c.demand_measurement is not None and c.demand_measurement.method == "integrated_demand":
            yield f"{c.id}.demand_measurement", c.demand_measurement.source


def _check_citations(
    tv: TariffVersion, ctx: _Ctx, sources: Mapping[str, SourceDocument] | None
) -> None:
    cited = {cit.document for _, cit in _all_citations(tv) if cit is not None}
    cited |= {e.source.document for e in tv.excluded_components if e.source is not None}
    stray = sorted(cited - set(tv.sources))
    if stray:
        raise (ctx / "sources").fail(
            f"citations refer to document(s) {stray} not listed in sources"
        )
    if tv.verification_status == "unverified":
        return
    missing = [name for name, cit in _all_citations(tv) if cit is None]
    if missing:
        raise ctx.fail(f"a {tv.verification_status} version needs a source citation for {missing}")


#: Grid used to check that the windows of an exclusive group partition time:
#: a leap year at 15-minute resolution, which contains both DST changes and
#: every holiday. Bundled window boundaries are whole hours.
def _coverage_grid() -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", "2025-01-01", freq="15min", tz=TARIFF_TZ, inclusive="left")


def _check_exclusive_groups(tv: TariffVersion, ctx: _Ctx) -> None:
    groups: dict[str, list[Component]] = {}
    for c in tv.components:
        if c.category in ("delivery_energy", "supply_energy") and c.exclusive_group is None:
            raise ctx.fail(
                f"component {c.id!r}: energy components must name an exclusive_group "
                "(mutually exclusive windows that cover every hour)"
            )
        if c.exclusive_group is not None:
            groups.setdefault(c.exclusive_group, []).append(c)
    if not groups:
        return
    grid = _coverage_grid()
    for name, members in groups.items():
        cats = {m.category for m in members}
        if len(cats) != 1:
            raise ctx.fail(f"exclusive_group {name!r} mixes categories {sorted(cats)}")
        count = np.zeros(len(grid), dtype=int)
        for m in members:
            count += m.window.mask(grid).astype(int)
        if (count == 0).any():
            first = grid[np.argmax(count == 0)]
            raise ctx.fail(f"exclusive_group {name!r} leaves a gap, e.g. at {first}")
        if (count > 1).any():
            first = grid[np.argmax(count > 1)]
            raise ctx.fail(f"exclusive_group {name!r} has overlapping windows, e.g. at {first}")


# ─────────────────────────────── files and registry ───────────────────────────
def _package_dir() -> Path:
    return Path(str(resources.files("coned_billing"))) / _PACKAGE_V1


def load_sources(path: Path | None = None) -> dict[str, SourceDocument]:
    """Read the source-document register (``tariffs/v1/sources.yml``)."""
    path = path or _package_dir() / "sources.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    ctx = _Ctx(path.name)
    d = _mapping(data, ctx, ("schema_version", "documents"), ())
    if d["schema_version"] != SCHEMA_VERSION:
        raise (ctx / "schema_version").fail(f"expected {SCHEMA_VERSION}")
    out: dict[str, SourceDocument] = {}
    if not isinstance(d["documents"], list):
        raise (ctx / "documents").fail("expected a list")
    for i, raw in enumerate(d["documents"]):
        c = ctx / "documents" / i
        r = _mapping(
            raw,
            c,
            ("id", "title", "url", "retrieved_utc", "sha256", "file"),
            ("parent_file", "parent_sha256", "parent_page", "notes"),
        )
        sha = _str(r["sha256"], c / "sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise (c / "sha256").fail("expected 64 lowercase hex digits")
        doc = SourceDocument(
            id=_str(r["id"], c / "id"),
            title=_str(r["title"], c / "title"),
            url=_str(r["url"], c / "url"),
            retrieved_utc=_str(r["retrieved_utc"], c / "retrieved_utc"),
            sha256=sha,
            file=_str(r["file"], c / "file"),
            parent_file=_opt_str(r.get("parent_file"), c / "parent_file"),
            parent_sha256=_opt_str(r.get("parent_sha256"), c / "parent_sha256"),
            parent_page=None
            if r.get("parent_page") is None
            else _int(r["parent_page"], c / "parent_page", minimum=1),
            notes=_opt_str(r.get("notes"), c / "notes"),
        )
        if doc.id in out:
            raise (c / "id").fail(f"duplicate document id {doc.id!r}")
        out[doc.id] = doc
    return out


def load_tariff_version(
    path: Path, *, sources: Mapping[str, SourceDocument] | None = None
) -> TariffVersion:
    """Load and validate one tariff-version YAML file."""
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parse_tariff_version(data, where=path.name, sources=sources, path=path)


def _load_verification_record(path: Path) -> set[tuple[str, str]]:
    """Versions the owner has approved (``verification_record.yml``)."""
    if not path.exists():
        return set()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    ctx = _Ctx(path.name)
    d = _mapping(data, ctx, ("approvals",), ())
    out: set[tuple[str, str]] = set()
    for i, raw in enumerate(d["approvals"] or []):
        c = ctx / "approvals" / i
        r = _mapping(raw, c, ("tariff_id", "version", "verified_by", "date"), ("notes",))
        _str(r["verified_by"], c / "verified_by")
        _date(r["date"], c / "date")
        ver = r["version"]
        out.add(
            (
                _str(r["tariff_id"], c / "tariff_id"),
                ver.isoformat() if isinstance(ver, date) else _str(ver, c / "version"),
            )
        )
    return out


class TariffRegistry:
    """All versions of all tariffs, validated together.

    Besides each file's own checks, the registry rejects duplicate versions,
    undeclared overlaps between dated versions of the same tariff, and
    ``owner_verified`` status without an owner approval record.
    """

    def __init__(
        self,
        versions: Iterable[TariffVersion],
        *,
        approved: set[tuple[str, str]] | None = None,
    ) -> None:
        approved = approved or set()
        self.sources: dict[str, SourceDocument] = {}
        by_tariff: dict[str, dict[str, TariffVersion]] = {}
        for v in versions:
            vs = by_tariff.setdefault(v.tariff_id, {})
            if v.version in vs:
                raise TariffSchemaError(f"duplicate version {v.key}")
            if (
                v.verification_status in ("owner_verified", "bill_reconciled")
                and v.key not in approved
            ):
                raise TariffSchemaError(
                    f"{v.key} is marked {v.verification_status} but has no owner approval in "
                    "verification_record.yml (only the owner can confer this status)"
                )
            vs[v.version] = v
        self._by_tariff = {
            t: dict(sorted(vs.items(), key=lambda kv: (kv[1].effective_start or date.min, kv[0])))
            for t, vs in sorted(by_tariff.items())
        }
        for vs in self._by_tariff.values():
            self._check_overlaps(list(vs.values()))

    @staticmethod
    def _check_overlaps(versions: list[TariffVersion]) -> None:
        dated = [v for v in versions if v.effective_start is not None]
        for i, a in enumerate(dated):
            for b in dated[i + 1 :]:
                a_end = a.effective_end or date.max
                b_end = b.effective_end or date.max
                assert a.effective_start is not None and b.effective_start is not None
                if a.effective_start < b_end and b.effective_start < a_end:
                    declared = b.version in a.known_overlaps and a.version in b.known_overlaps
                    if not declared:
                        raise TariffSchemaError(
                            f"{a.tariff_id}: versions {a.version!r} and {b.version!r} overlap; "
                            "fix the dates, or declare a known ambiguity with known_overlaps "
                            "on both versions"
                        )

    @classmethod
    def from_directory(
        cls,
        directory: Path | None = None,
        *,
        sources_path: Path | None = None,
        verification_record: Path | None = None,
    ) -> TariffRegistry:
        directory = Path(directory) if directory else _package_dir()
        sources = load_sources(sources_path or directory / "sources.yml")
        record = verification_record or directory / "verification_record.yml"
        files = sorted(p for p in directory.glob("*/*.yml"))
        versions = [load_tariff_version(p, sources=sources) for p in files]
        for p, v in zip(files, versions, strict=True):
            if p.parent.name != v.tariff_id or p.stem != v.version:
                raise TariffSchemaError(
                    f"{p}: file must be named <tariff_id>/<version>.yml "
                    f"({v.tariff_id}/{v.version}.yml)"
                )
        reg = cls(versions, approved=_load_verification_record(record))
        reg.sources = sources
        return reg

    # ── queries ──
    def tariff_ids(self) -> list[str]:
        return list(self._by_tariff)

    def versions(self, tariff_id: str) -> list[TariffVersion]:
        return list(self._tariff(tariff_id).values())

    def __iter__(self):
        for vs in self._by_tariff.values():
            yield from vs.values()

    def _tariff(self, tariff_id: str) -> dict[str, TariffVersion]:
        try:
            return self._by_tariff[tariff_id]
        except KeyError:
            raise TariffSelectionError(
                f"unknown or unsupported tariff {tariff_id!r}; supported: {self.tariff_ids()}. "
                "Other Con Edison rates and options (e.g. standby, voluntary TOU, SC-9 Rate "
                "III, Westchester-specific charges) are not supported."
            ) from None

    def scenario(self, tariff_id: str, version: str) -> TariffVersion:
        """An explicitly chosen version, for scenario mode (R4)."""
        vs = self._tariff(tariff_id)
        if version not in vs:
            raise TariffSelectionError(
                f"{tariff_id} has no version {version!r}; versions: {list(vs)}"
            )
        v = vs[version]
        if "scenario" not in v.calculation_modes:
            raise TariffSelectionError(f"{v.key} is not available in scenario mode")
        return v

    def historical(self, tariff_id: str, day: date | pd.Timestamp) -> TariffVersion:
        """The version in effect on service date ``day`` (historical mode, R4).

        A timezone-aware Timestamp is converted to its New York civil date.
        """
        if isinstance(day, pd.Timestamp):
            ts = day.tz_convert(TARIFF_TZ) if day.tz is not None else day
            day = ts.date()
        if not isinstance(day, date):
            raise TariffSelectionError(f"expected a date, got {day!r}")
        vs = [v for v in self._tariff(tariff_id).values() if "historical" in v.calculation_modes]
        hits = [v for v in vs if v.covers(day)]
        if len(hits) > 1:
            raise TariffSelectionError(
                f"{tariff_id} on {day}: ambiguous, versions {[v.version for v in hits]} both "
                "claim this date in the cited sources; no version is selected"
            )
        if not hits:
            spans = [f"{v.effective_start}..{v.effective_end or 'open'}" for v in vs]
            raise TariffSelectionError(
                f"{tariff_id} on {day}: no transcribed version covers this date "
                f"(covered: {spans}); current rates are never substituted"
            )
        v = hits[0]
        if v.effective_end is None and v.valid_as_of is not None and day > v.valid_as_of:
            raise TariffSelectionError(
                f"{tariff_id} on {day}: after {v.valid_as_of}, the last date its sources "
                "were checked; a later version may exist"
            )
        return v

    def historical_segments(
        self, tariff_id: str, start: date, end: date
    ) -> list[tuple[date, date, TariffVersion]]:
        """Split service dates ``[start, end)`` by the version in effect."""
        if end <= start:
            raise TariffSelectionError("end must be after start")
        out: list[tuple[date, date, TariffVersion]] = []
        for d in pd.date_range(start, end, freq="D", inclusive="left").date:
            v = self.historical(tariff_id, d)
            if out and out[-1][2] is v:
                out[-1] = (out[-1][0], d + pd.Timedelta(days=1).to_pytimedelta(), v)
            else:
                out.append((d, d + pd.Timedelta(days=1).to_pytimedelta(), v))
        return out


_DEFAULT: TariffRegistry | None = None


def default_registry() -> TariffRegistry:
    """The bundled tariff registry (loaded and validated once)."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = TariffRegistry.from_directory()
    return _DEFAULT


def as_plain(obj: Any) -> Any:
    """A JSON-friendly view of a dataclass tree (used for snapshots and docs)."""
    if isinstance(obj, TimeWindow):
        return {
            "months": list(obj.months) if obj.months else None,
            "weekdays_only": obj.weekdays_only,
            "start": obj.start.strftime("%H:%M") if obj.start else None,
            "end": obj.end.strftime("%H:%M") if obj.end else "end_of_day",
            "excluded_holidays": obj.holiday_set.name,
        }
    if hasattr(obj, "__dataclass_fields__"):
        return {k: as_plain(getattr(obj, k)) for k in obj.__dataclass_fields__ if k != "path"}
    if isinstance(obj, (list, tuple)):
        return [as_plain(x) for x in obj]
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


def snapshot_values(reg: TariffRegistry) -> dict[str, Any]:
    """Tariff values, dates and statuses keyed by ``tariff_id/version`` (for the snapshot test)."""
    out: dict[str, Any] = {}
    for v in reg:
        out[f"{v.tariff_id}/{v.version}"] = {
            "effective": [as_plain(v.effective_start), as_plain(v.effective_end)],
            "verification_status": v.verification_status,
            "components": {
                c.id: {
                    "category": c.category,
                    "rate": c.rate,
                    "unit": c.unit,
                    "blocks": [[b.up_to, b.rate, b.unit] for b in c.blocks],
                    "window": as_plain(c.window),
                    "source": None
                    if c.source is None
                    else [c.source.document, c.source.leaf, c.source.revision],
                }
                for c in v.components
            },
            "excluded": [e.id for e in v.excluded_components],
        }
    return out
