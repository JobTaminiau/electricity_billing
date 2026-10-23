"""Schema tests for tariff schema v1 (WP3).

These check validation and version selection. Expected values are hand
arithmetic or literal inputs, never taken from the production code.
"""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

import coned_billing
from coned_billing.errors import ConEdBillingError, TariffSchemaError, TariffSelectionError
from coned_billing.loader import load_rate
from coned_billing.tariff_schema import (
    TariffRegistry,
    default_registry,
    load_sources,
    load_tariff_version,
    parse_tariff_version,
)

TARIFFS = Path(coned_billing.__file__).parent / "tariffs"
NY = "America/New_York"


def _cite(text="x"):
    return {"document": "doc-a", "leaf": "1", "revision": 0, "page": 1, "text": text}


def _version(**over):
    """A minimal valid transcribed version (one fixed and two energy components)."""
    d = {
        "schema_version": 1,
        "tariff_id": "test_rate",
        "version": "2024-01-01",
        "utility": "U",
        "jurisdiction": "J",
        "tariff_book": "B",
        "service_classification": "SC-0",
        "rate_option": "Rate 0",
        "voltage": None,
        "zone": None,
        "timezone": NY,
        "effective": {"start": date(2024, 1, 1), "end": date(2025, 1, 1)},
        "verification_status": "transcribed",
        "calculation_modes": ["historical", "scenario"],
        "sources": ["doc-a"],
        "components": [
            {
                "id": "customer_charge",
                "name": "Customer Charge",
                "category": "fixed_charge",
                "determinant": "billing_period",
                "unit": "USD/month",
                "rate": 10.0,
                "window": {"excluded_holidays": "none"},
                "source": _cite(),
            },
            {
                "id": "energy_summer",
                "name": "Energy summer",
                "category": "delivery_energy",
                "determinant": "kwh",
                "unit": "USD/kWh",
                "rate": 0.2,
                "window": {"months": [6, 7, 8, 9], "excluded_holidays": "none"},
                "exclusive_group": "energy",
                "source": _cite(),
            },
            {
                "id": "energy_other",
                "name": "Energy other",
                "category": "delivery_energy",
                "determinant": "kwh",
                "unit": "cents/kWh",
                "rate": 15.0,
                "window": {"months": [1, 2, 3, 4, 5, 10, 11, 12], "excluded_holidays": "none"},
                "exclusive_group": "energy",
                "source": _cite(),
            },
        ],
        "excluded_components": [],
    }
    d.update(over)
    return d


def _parse(d):
    return parse_tariff_version(d, where="t.yml")


def _demand(**over):
    c = {
        "id": "demand",
        "name": "Demand",
        "category": "delivery_demand",
        "determinant": "max_demand_kw",
        "unit": "USD/kW",
        "rate": 20.0,
        "window": {"excluded_holidays": "none"},
        "demand_measurement": {
            "method": "integrated_demand",
            "integration_minutes": 30,
            "convention": "fixed_clock",
            "source": _cite(),
        },
        "source": _cite(),
    }
    c.update(over)
    return c


def _with_component(c, d=None):
    d = d or _version()
    d["components"].append(c)
    return d


# ─────────────────────────────── valid input ──────────────────────────────────
def test_minimal_version_loads():
    v = _parse(_version())
    assert v.key == ("test_rate", "2024-01-01")
    assert v.component("energy_other").rate_usd == pytest.approx(0.15, abs=1e-15)
    assert v.covers(date(2024, 1, 1)) and v.covers(date(2024, 12, 31))
    assert not v.covers(date(2025, 1, 1))  # end is exclusive
    assert not v.covers(date(2023, 12, 31))


def test_bundled_registry_loads():
    reg = default_registry()
    assert set(reg.tariff_ids()) == {
        "sc1_rate1",
        "sc2_rate1",
        "sc8_rate1_lt",
        "sc9_rate1_lt",
        "sc9_rate1_ht",
        "sc9_rate2_lt",
    }
    for tid in reg.tariff_ids():
        assert "legacy" in [v.version for v in reg.versions(tid)]


def test_yaml_file_round_trip(tmp_path):
    p = tmp_path / "2024-01-01.yml"
    p.write_text(yaml.safe_dump(_version()))
    assert load_tariff_version(p).version == "2024-01-01"


# ─────────────────────────────── required fields ──────────────────────────────
@pytest.mark.parametrize(
    "key",
    [
        "schema_version",
        "tariff_id",
        "version",
        "effective",
        "verification_status",
        "timezone",
        "calculation_modes",
        "sources",
        "components",
        "excluded_components",
        "voltage",
    ],
)
def test_missing_required_top_level_field_fails(key):
    d = _version()
    del d[key]
    with pytest.raises(TariffSchemaError, match=key):
        _parse(d)


@pytest.mark.parametrize("key", ["id", "name", "category", "determinant", "window"])
def test_missing_required_component_field_fails(key):
    d = _version()
    del d["components"][0][key]
    with pytest.raises(TariffSchemaError, match=key):
        _parse(d)


def test_window_without_explicit_holiday_set_fails():
    d = _version()
    d["components"][1]["window"] = {"months": [6, 7, 8, 9]}
    with pytest.raises(TariffSchemaError, match="excluded_holidays"):
        _parse(d)


def test_transcribed_component_without_citation_fails():
    d = _version()
    del d["components"][0]["source"]
    with pytest.raises(TariffSchemaError, match="citation"):
        _parse(d)


# ─────────────────────────────── unknown keys ─────────────────────────────────
def test_misspelled_window_key_is_named():
    d = _version()
    d["components"][1]["window"]["weekday_only"] = True
    with pytest.raises(TariffSchemaError, match="weekday_only"):
        _parse(d)


@pytest.mark.parametrize(
    ("path", "key"),
    [
        ((), "verification"),
        (("components", 0), "rat"),
        (("effective",), "begin"),
        (("components", 0, "source"), "pages"),
    ],
)
def test_unknown_keys_fail_with_the_key_named(path, key):
    d = _version()
    target = d
    for p in path:
        target = target[p]
    target[key] = 1
    with pytest.raises(TariffSchemaError, match=key):
        _parse(d)


def test_legacy_loader_rejects_misspelled_key(tmp_path):
    p = tmp_path / "t.yml"
    p.write_text(
        "code: T\ncustomer_charge: 0\nsupply_charge: 0\nmerchant_charge: 0\n"
        "energy:\n  - {rate: 1, window: {weekday_only: true, include_holidays: true}}\n"
    )
    with pytest.raises(ConEdBillingError, match="weekday_only"):
        load_rate(p)


# ─────────────────────────────── values ───────────────────────────────────────
@pytest.mark.parametrize("unit", ["USD/kwh", "$/kWh", "USD/kW", "USD/month"])
def test_energy_component_with_wrong_unit_fails(unit):
    d = _version()
    d["components"][1]["unit"] = unit
    with pytest.raises(TariffSchemaError, match="unit"):
        _parse(d)


def test_demand_component_needs_usd_per_kw():
    with pytest.raises(TariffSchemaError, match="unit"):
        _parse(_with_component(_demand(unit="USD/kWh")))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), "0.2", True, None])
def test_non_finite_or_non_numeric_rate_fails(bad):
    d = _version()
    d["components"][1]["rate"] = bad
    with pytest.raises(TariffSchemaError, match="rate"):
        _parse(d)


@pytest.mark.parametrize(
    "eff",
    [
        {"start": "2024-13-01", "end": None},
        {"start": "01/01/2024", "end": None},
        {"start": date(2024, 1, 1), "end": date(2024, 1, 1)},
        {"start": date(2024, 2, 1), "end": date(2024, 1, 1)},
        {"start": None, "end": date(2024, 1, 1)},
    ],
)
def test_invalid_effective_dates_fail(eff):
    with pytest.raises(TariffSchemaError, match="effective"):
        _parse(_version(effective=eff))


@pytest.mark.parametrize("months", [[0, 6], [13], [], [6, 6], ["6"], [6.0]])
def test_invalid_months_fail(months):
    d = _version()
    d["components"][1]["window"]["months"] = months
    with pytest.raises(TariffSchemaError, match="months"):
        _parse(d)


@pytest.mark.parametrize(
    "window",
    [
        {"start": "22:00", "end": "08:00", "excluded_holidays": "none"},
        {"end": "24:00", "excluded_holidays": "none"},
        {"start": "8:00", "excluded_holidays": "none"},
        {"excluded_holidays": "easter"},
    ],
)
def test_invalid_windows_fail(window):
    with pytest.raises(TariffSchemaError):
        _parse(_with_component(_demand(window=window)))


def test_duplicate_component_ids_fail():
    d = _version()
    d["components"][2]["id"] = "energy_summer"
    with pytest.raises(TariffSchemaError, match="duplicate component id"):
        _parse(d)


def test_excluded_component_id_cannot_repeat_a_component_id():
    d = _version(excluded_components=[{"id": "customer_charge", "name": "n", "reason": "r"}])
    with pytest.raises(TariffSchemaError, match="duplicate component id"):
        _parse(d)


def test_unknown_source_id_fails():
    with pytest.raises(TariffSchemaError, match="unknown source"):
        parse_tariff_version(_version(), sources={})


def test_citation_to_unlisted_document_fails():
    d = _version()
    d["components"][0]["source"]["document"] = "doc-b"
    with pytest.raises(TariffSchemaError, match="doc-b"):
        _parse(d)


def test_timezone_must_be_new_york():
    with pytest.raises(TariffSchemaError, match="timezone"):
        _parse(_version(timezone="UTC"))


# ─────────────────────────────── sign rules ───────────────────────────────────
def test_negative_delivery_rate_fails():
    d = _version()
    d["components"][1]["rate"] = -0.01
    with pytest.raises(TariffSchemaError, match=">= 0"):
        _parse(d)


def test_documented_negative_credit_is_allowed():
    credit = {
        "id": "credit",
        "name": "A documented credit",
        "category": "credit",
        "determinant": "kwh",
        "unit": "USD/kWh",
        "rate": -0.01,
        "window": {"excluded_holidays": "none"},
        "source": _cite(),
    }
    v = _parse(_with_component(credit))
    assert v.component("credit").rate == -0.01


def test_positive_credit_fails():
    credit = {
        "id": "credit",
        "name": "c",
        "category": "credit",
        "determinant": "billing_period",
        "unit": "USD/month",
        "rate": 1.0,
        "window": {"excluded_holidays": "none"},
        "source": _cite(),
    }
    with pytest.raises(TariffSchemaError, match="<= 0"):
        _parse(_with_component(credit))


def test_adjustment_may_take_either_sign():
    for r in (-0.5, 0.5):
        adj = {
            "id": "adj",
            "name": "a",
            "category": "adjustment",
            "determinant": "kwh",
            "unit": "USD/kWh",
            "rate": r,
            "window": {"excluded_holidays": "none"},
            "source": _cite(),
        }
        assert _parse(_with_component(adj)).component("adj").rate == r


# ─────────────────────────────── exclusive groups and overlaps ────────────────
def test_gap_in_exclusive_energy_group_fails():
    d = _version()
    d["components"][2]["window"]["months"] = [1, 2, 3, 4, 5, 10, 11]  # December uncovered
    with pytest.raises(TariffSchemaError, match="gap"):
        _parse(d)


def test_overlap_in_exclusive_energy_group_fails():
    d = _version()
    d["components"][2]["window"]["months"] = [1, 2, 3, 4, 5, 6, 10, 11, 12]  # June twice
    with pytest.raises(TariffSchemaError, match="overlapping"):
        _parse(d)


def test_weekday_holiday_split_partitions_time():
    # Weekday non-holidays plus (weekends and holidays) cover every hour once.
    d = _version()
    d["components"][1:] = [
        {
            **d["components"][1],
            "id": "on",
            "window": {"weekdays_only": True, "excluded_holidays": "coned_six"},
        },
        {
            **d["components"][1],
            "id": "weekend",
            "window": {"weekdays_only": False, "excluded_holidays": "none"},
        },
    ]
    with pytest.raises(TariffSchemaError, match="gap"):  # weekday holidays fall in neither
        _parse(d)


def test_energy_component_must_name_an_exclusive_group():
    d = _version()
    del d["components"][1]["exclusive_group"]
    with pytest.raises(TariffSchemaError, match="exclusive_group"):
        _parse(d)


def test_intentional_additive_demand_overlap_is_accepted():
    # SC-9 Rate II: 8 AM-6 PM, 8 AM-10 PM and all-hours summer demand charges overlap.
    v = default_registry().scenario("sc9_rate2_lt", "2026-02-01")
    demand = [c for c in v.components if c.category == "delivery_demand"]
    ts = pd.DatetimeIndex([pd.Timestamp("2026-07-14 15:00", tz=NY)])  # a Tuesday afternoon
    hits = [c.id for c in demand if c.window.mask(ts)[0]]
    assert hits == [
        "demand_summer_weekday_0800_1800",
        "demand_summer_weekday_0800_2200",
        "demand_summer_all_hours",
    ]


def test_sc9_rate2_weekday_windows_include_holidays():
    # Owner decision 2026-10-23: follow leaf 449, which names no holiday exclusion.
    v = default_registry().scenario("sc9_rate2_lt", "2026-02-01")
    ts = pd.DatetimeIndex([pd.Timestamp("2026-07-03 15:00", tz=NY)])  # Friday; July 4 is a Saturday
    ts4 = pd.DatetimeIndex([pd.Timestamp("2026-09-07 15:00", tz=NY)])  # Labor Day, Monday
    c = v.component("demand_summer_weekday_0800_2200")
    assert c.window.mask(ts)[0] and c.window.mask(ts4)[0]


# ─────────────────────────────── blocks ───────────────────────────────────────
def _block_component(blocks, **over):
    c = {
        "id": "tier",
        "name": "Tiered",
        "category": "delivery_energy",
        "determinant": "kwh",
        "window": {"excluded_holidays": "none"},
        "blocks": blocks,
        "block_proration": {"rule": "bounds_days_over_30", "source": _cite()},
        "exclusive_group": "tiers",
        "source": _cite(),
    }
    c.update(over)
    return c


@pytest.mark.parametrize(
    ("blocks", "match"),
    [
        ([{"up_to": None, "rate": 1, "unit": "USD/kWh"}], "at least 2"),
        (
            [
                {"up_to": 250, "rate": 1, "unit": "USD/kWh"},
                {"up_to": 100, "rate": 2, "unit": "USD/kWh"},
                {"up_to": None, "rate": 3, "unit": "USD/kWh"},
            ],
            "increase",
        ),
        (
            [
                {"up_to": 250, "rate": 1, "unit": "USD/kWh"},
                {"up_to": 250, "rate": 2, "unit": "USD/kWh"},
                {"up_to": None, "rate": 3, "unit": "USD/kWh"},
            ],
            "increase",
        ),
        (
            [
                {"up_to": None, "rate": 1, "unit": "USD/kWh"},
                {"up_to": None, "rate": 2, "unit": "USD/kWh"},
            ],
            "only the last",
        ),
        (
            [
                {"up_to": 250, "rate": 1, "unit": "USD/kWh"},
                {"up_to": 500, "rate": 2, "unit": "USD/kWh"},
            ],
            "unbounded",
        ),
        (
            [
                {"up_to": 0, "rate": 1, "unit": "USD/kWh"},
                {"up_to": None, "rate": 2, "unit": "USD/kWh"},
            ],
            "increase",
        ),
        (
            [
                {"up_to": 250, "rate": 1, "unit": "USD/kWh"},
                {"up_to": None, "rate": 2, "unit": "USD/kW"},
            ],
            "unit",
        ),
        ([{"up_to": 250, "rate": 1}, {"up_to": None, "rate": 2, "unit": "USD/kWh"}], "unit"),
    ],
)
def test_malformed_blocks_fail(blocks, match):
    with pytest.raises(TariffSchemaError, match=match):
        _parse(_with_component(_block_component(blocks)))


def test_flat_block_allowed_only_first():
    blocks = [
        {"up_to": 5, "rate": 1, "unit": "USD/kW"},
        {"up_to": 10, "rate": 100, "unit": "USD/month"},
        {"up_to": None, "rate": 2, "unit": "USD/kW"},
    ]
    c = _demand(blocks=blocks, block_proration={"rule": "total_days_over_30", "source": _cite()})
    del c["unit"], c["rate"]
    with pytest.raises(TariffSchemaError, match="USD/month"):
        _parse(_with_component(c))


def test_block_charge_needs_a_proration_rule():
    c = _block_component(
        [{"up_to": 1, "rate": 1, "unit": "USD/kWh"}, {"up_to": None, "rate": 2, "unit": "USD/kWh"}]
    )
    del c["block_proration"]
    with pytest.raises(TariffSchemaError, match="block_proration"):
        _parse(_with_component(c))


def test_rate_and_blocks_are_exclusive():
    c = _block_component(
        [{"up_to": 1, "rate": 1, "unit": "USD/kWh"}, {"up_to": None, "rate": 2, "unit": "USD/kWh"}],
        rate=1.0,
    )
    with pytest.raises(TariffSchemaError, match="exactly one"):
        _parse(_with_component(c))


def _tiers(rule="bounds_days_over_30"):
    d = _version()
    d["components"][1:] = [
        _block_component(
            [
                {"up_to": 250, "rate": 0.1, "unit": "USD/kWh"},
                {"up_to": None, "rate": 0.2, "unit": "USD/kWh"},
            ],
            block_proration={"rule": rule, "source": _cite()},
            exclusive_group="energy",
        )
    ]
    return _parse(d).component("tier")


def test_block_charge_hand_arithmetic_30_days():
    c = _tiers()
    assert c.block_charge(0) == 0.0
    assert c.block_charge(100) == pytest.approx(10.0, abs=1e-12)
    assert c.block_charge(250) == pytest.approx(25.0, abs=1e-12)
    assert c.block_charge(600) == pytest.approx(250 * 0.1 + 350 * 0.2, abs=1e-12)


def test_block_bounds_prorated_by_elapsed_days():
    # GR 10.5.2: block usage prorated by elapsed days / 30; 36 days -> first block 300 kWh.
    c = _tiers()
    assert c.block_charge(600, elapsed_days=36) == pytest.approx(300 * 0.1 + 300 * 0.2, abs=1e-12)
    assert c.block_charge(600, elapsed_days=24) == pytest.approx(200 * 0.1 + 400 * 0.2, abs=1e-12)


def test_partial_period_rejected_without_a_rule():
    c = _tiers("reject_partial_periods")
    assert c.block_charge(600) == pytest.approx(95.0, abs=1e-12)
    with pytest.raises(ConEdBillingError, match="31-day"):
        c.block_charge(600, elapsed_days=31)


def test_flat_first_demand_block_and_total_proration():
    blocks = [
        {"up_to": 5, "rate": 249.01, "unit": "USD/month"},
        {"up_to": None, "rate": 35.51, "unit": "USD/kW"},
    ]
    c = _demand(blocks=blocks, block_proration={"rule": "total_days_over_30", "source": _cite()})
    del c["unit"], c["rate"]
    comp = _parse(_with_component(c)).component("demand")
    assert comp.block_charge(3) == pytest.approx(249.01, abs=1e-9)  # "first 5 kW (or less)"
    assert comp.block_charge(12) == pytest.approx(249.01 + 7 * 35.51, abs=1e-9)
    assert comp.block_charge(12, elapsed_days=33) == pytest.approx(
        (249.01 + 7 * 35.51) * 33 / 30, abs=1e-9
    )


@pytest.mark.parametrize("bad", [-1, float("nan")])
def test_block_charge_rejects_bad_quantity(bad):
    with pytest.raises(ConEdBillingError):
        _tiers().block_charge(bad)


# ─────────────────────────────── modes and statuses ───────────────────────────
def test_unverified_version_cannot_be_historical():
    with pytest.raises(TariffSchemaError, match="historical"):
        _parse(_version(verification_status="unverified"))


def test_historical_mode_needs_dates():
    with pytest.raises(TariffSchemaError, match="effective"):
        _parse(_version(effective={"start": None, "end": None}))


def test_open_ended_historical_version_needs_valid_as_of():
    with pytest.raises(TariffSchemaError, match="valid_as_of"):
        _parse(_version(effective={"start": date(2024, 1, 1), "end": None}))


def _registry(*versions, approved=None):
    return TariffRegistry([_parse(v) for v in versions], approved=approved)


def test_owner_verified_requires_the_owner_record():
    v = _version(verification_status="owner_verified")
    with pytest.raises(TariffSchemaError, match="verification_record"):
        _registry(v)
    assert _registry(v, approved={("test_rate", "2024-01-01")})


def test_bundled_versions_are_not_owner_verified():
    statuses = {v.verification_status for v in default_registry()}
    assert statuses == {"unverified", "transcribed"}


def test_verification_record_file_gates_owner_status(tmp_path):
    root = tmp_path / "tariffs"
    v1 = root / "v1"
    (v1 / "test_rate").mkdir(parents=True)
    (v1 / "sources.yml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "documents": [
                    {
                        "id": "doc-a",
                        "title": "t",
                        "url": "u",
                        "retrieved_utc": "r",
                        "sha256": "0" * 64,
                        "file": "f.pdf",
                    }
                ],
            }
        )
    )
    (v1 / "test_rate" / "2024-01-01.yml").write_text(
        yaml.safe_dump(_version(verification_status="owner_verified"))
    )
    with pytest.raises(TariffSchemaError, match="owner"):
        TariffRegistry.from_directory(v1)
    (v1 / "verification_record.yml").write_text(
        "approvals:\n"
        "  - {tariff_id: test_rate, version: '2024-01-01', verified_by: Owner, date: 2026-10-24}\n"
    )
    assert TariffRegistry.from_directory(v1).scenario("test_rate", "2024-01-01")


def test_file_must_be_named_after_its_version(tmp_path):
    v1 = tmp_path / "v1"
    (v1 / "test_rate").mkdir(parents=True)
    (v1 / "sources.yml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "documents": [
                    {
                        "id": "doc-a",
                        "title": "t",
                        "url": "u",
                        "retrieved_utc": "r",
                        "sha256": "0" * 64,
                        "file": "f.pdf",
                    }
                ],
            }
        )
    )
    (v1 / "test_rate" / "2024.yml").write_text(yaml.safe_dump(_version()))
    with pytest.raises(TariffSchemaError, match="named"):
        TariffRegistry.from_directory(v1)


# ─────────────────────────────── version selection ────────────────────────────
def _two(a_end=date(2025, 1, 1), b_start=date(2025, 1, 1), **b_over):
    a = _version(effective={"start": date(2024, 1, 1), "end": a_end})
    b = _version(
        version=b_start.isoformat(),
        effective={"start": b_start, "end": None},
        valid_as_of=date(2026, 1, 1),
        **b_over,
    )
    return a, b


def test_contiguous_versions_select_by_service_date():
    reg = _registry(*_two())
    assert reg.historical("test_rate", date(2024, 12, 31)).version == "2024-01-01"
    assert reg.historical("test_rate", date(2025, 1, 1)).version == "2025-01-01"
    segs = reg.historical_segments("test_rate", date(2024, 12, 15), date(2025, 1, 15))
    assert [(s, e, v.version) for s, e, v in segs] == [
        (date(2024, 12, 15), date(2025, 1, 1), "2024-01-01"),
        (date(2025, 1, 1), date(2025, 1, 15), "2025-01-01"),
    ]


def test_undeclared_overlapping_versions_fail():
    with pytest.raises(TariffSchemaError, match="overlap"):
        _registry(*_two(b_start=date(2024, 6, 1)))


def test_declared_overlap_loads_but_selection_is_ambiguous():
    a, b = _two(b_start=date(2024, 6, 1), known_overlaps=["2024-01-01"])
    a["known_overlaps"] = ["2024-06-01"]
    reg = _registry(a, b)
    assert reg.historical("test_rate", date(2024, 5, 31)).version == "2024-01-01"
    with pytest.raises(TariffSelectionError, match="ambiguous"):
        reg.historical("test_rate", date(2024, 6, 1))


def test_bundled_2024_sc1_double_revision_is_ambiguous():
    reg = default_registry()
    with pytest.raises(TariffSelectionError, match="ambiguous"):
        reg.historical("sc1_rate1", date(2024, 1, 15))
    assert reg.historical("sc1_rate1", date(2024, 2, 4)).version == "2024-02-04"
    assert reg.historical("sc1_rate1", date(2023, 12, 31)).version == "2023-08-01"


@pytest.mark.parametrize(
    "day",
    [date(2023, 12, 31), date(2026, 1, 2)],  # before the first version; after valid_as_of
)
def test_uncovered_historical_dates_fail(day):
    reg = _registry(*_two())
    with pytest.raises(TariffSelectionError):
        reg.historical("test_rate", day)


def test_gap_between_versions_is_uncovered():
    reg = _registry(*_two(a_end=date(2024, 6, 1)))
    with pytest.raises(TariffSelectionError, match="no transcribed version"):
        reg.historical("test_rate", date(2024, 7, 1))


def test_bundled_dates_before_transcription_are_uncovered():
    reg = default_registry()
    with pytest.raises(TariffSelectionError, match="no transcribed version"):
        reg.historical("sc9_rate1_lt", date(2020, 1, 31))
    with pytest.raises(TariffSelectionError, match="checked"):
        reg.historical("sc1_rate1", date(2027, 1, 1))


def test_unknown_or_unsupported_tariff_is_rejected():
    with pytest.raises(TariffSelectionError, match="unsupported"):
        default_registry().historical("sc9_rate3_lt", date(2026, 3, 1))


def test_scenario_mode_needs_an_explicit_existing_version():
    reg = default_registry()
    assert reg.scenario("sc1_rate1", "legacy").verification_status == "unverified"
    with pytest.raises(TariffSelectionError, match="no version"):
        reg.scenario("sc1_rate1", "2027-01-01")


def test_historical_accepts_tz_aware_timestamp_in_new_york():
    reg = default_registry()
    # 2026-02-01 04:30 UTC is still 2026-01-31 in New York.
    ts = pd.Timestamp("2026-02-01 04:30", tz="UTC")
    assert reg.historical("sc1_rate1", ts).version == "2025-01-01"


# ─────────────────────────────── legacy migration ─────────────────────────────
LEGACY = {
    "sc_1_res_rate_1.yml": "sc1_rate1",
    "sc2_general_rate_1.yml": "sc2_rate1",
    "sc8_multi_dwell_rate_1.yml": "sc8_rate1_lt",
    "sc9_general_rate_1_LT.yml": "sc9_rate1_lt",
    "sc9_general_rate_I-HT.yml": "sc9_rate1_ht",
    "sc9_general_rate_2_TOU.yml": "sc9_rate2_lt",
}


@pytest.mark.parametrize(("name", "tid"), LEGACY.items())
def test_legacy_migration_preserves_values_exactly(name, tid):
    raw = yaml.safe_load((TARIFFS / name).read_text())
    v = default_registry().scenario(tid, "legacy")
    assert v.verification_status == "unverified"
    assert v.calculation_modes == ("scenario",)
    by_cat = {}
    for c in v.components:
        by_cat.setdefault(c.category, []).append(c.rate)
    assert by_cat["fixed_charge"] == [raw["customer_charge"]]
    assert by_cat["supply_energy"] == [raw["supply_charge"]]
    assert by_cat["merchant_charge"] == [raw["merchant_charge"]]
    assert by_cat.get("delivery_energy", []) == [e["rate"] for e in raw["energy"]]
    assert by_cat.get("delivery_demand", []) == [
        e["rate"] for e in raw.get("demand_delivery") or []
    ]
    assert by_cat.get("supply_demand", []) == [e["rate"] for e in raw.get("demand_supply") or []]
    # Legacy holiday semantics are kept: include_holidays false -> six-day set.
    legacy_windows = [e["window"] for e in raw.get("demand_delivery") or []]
    migrated = [c.window for c in v.components if c.category == "delivery_demand"]
    for lw, mw in zip(legacy_windows, migrated, strict=True):
        assert mw.holiday_set.name == ("none" if lw.get("include_holidays") else "coned_six")


def test_legacy_sc1_stray_key_is_surfaced():
    v = default_registry().scenario("sc1_rate1", "legacy")
    assert "stray top-level key '0'" in v.legacy_notes
    assert "sc 1 0.1466 + 0.1991" in v.legacy_notes


def test_legacy_loader_rejects_a_stray_key(tmp_path):
    p = tmp_path / "t.yml"
    p.write_text(
        "code: T\ncustomer_charge: 0\nsupply_charge: 0\nmerchant_charge: 0\n"
        "0:\n  sc 1 0.1466 + 0.1991\n"
    )
    with pytest.raises(ConEdBillingError, match=r"\b0\b"):
        load_rate(p)


def test_bundled_legacy_files_still_load_with_the_legacy_loader():
    for name in LEGACY:
        assert load_rate(TARIFFS / name).code


def test_sources_register_loads():
    docs = load_sources()
    assert len(docs) == len(set(docs))
    assert all(len(d.sha256) == 64 for d in docs.values())


def test_mask_grid_is_a_full_leap_year():
    # Exclusive-group coverage is checked on 2024 at 15 minutes: 366 days less
    # the 1-hour spring-forward gap plus the repeated fall-back hour.
    from coned_billing.tariff_schema import _coverage_grid

    assert len(_coverage_grid()) == 366 * 96
    assert np.unique(_coverage_grid().asi8).size == 366 * 96


def test_parse_does_not_mutate_its_input():
    d = _version()
    before = copy.deepcopy(d)
    _parse(d)
    assert d == before


# ─────────────────────────────── demand measurement (WP4) ─────────────────────
def _measurement(**over):
    m = {
        "method": "integrated_demand",
        "integration_minutes": 30,
        "convention": "fixed_clock",
        "source": _cite(),
    }
    m.update(over)
    return {k: v for k, v in m.items() if v is not None}


@pytest.mark.parametrize("convention", ["fixed_clock", "rolling"])
def test_demand_conventions_load(convention):
    v = _parse(_with_component(_demand(demand_measurement=_measurement(convention=convention))))
    assert v.component("demand").demand_measurement.convention == convention


@pytest.mark.parametrize(
    ("measurement", "field"),
    [
        (_measurement(convention=None), "convention"),
        (_measurement(convention="sliding"), "convention"),
        (_measurement(integration_minutes=45), "integration_minutes"),
        ({"method": "input_interval_maximum", "convention": "fixed_clock"}, "convention"),
    ],
)
def test_bad_demand_measurement_is_rejected(measurement, field):
    with pytest.raises(TariffSchemaError, match=rf"demand_measurement\.{field}"):
        _parse(_with_component(_demand(demand_measurement=measurement)))


def test_every_transcribed_demand_component_states_its_convention():
    for v in default_registry():
        for c in v.components:
            m = c.demand_measurement
            if m is not None and m.method == "integrated_demand":
                assert (m.integration_minutes, m.convention) == (30, "fixed_clock"), v.key
