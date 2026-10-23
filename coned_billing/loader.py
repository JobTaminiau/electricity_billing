import re
from datetime import time
from pathlib import Path

import yaml

from .errors import ConEdBillingError
from .models import DemandCharge, EnergyCharge, RateSchedule, TimeWindow

# helper ───────────────────────────────────────────────────────────────────
END_OF_DAY = "end_of_day"
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _parse_time(s: str | None, *, field: str = "start") -> time | None:
    """Parse "HH:MM" (00:00-23:59). ``end: end_of_day`` (or omission) means midnight."""
    if s is None:
        return None
    if field == "end" and s == END_OF_DAY:
        return None
    if not isinstance(s, str):
        raise ConEdBillingError(f'{field} must be a quoted "HH:MM" string, got {s!r}')
    if s.strip() == "24:00":
        raise ConEdBillingError(
            f'{field}: "24:00" is not accepted; write end: {END_OF_DAY} (or omit end) '
            "for a window that runs to midnight"
        )
    m = _HHMM.match(s.strip())
    if not m:
        raise ConEdBillingError(f'{field} must be "HH:MM" between 00:00 and 23:59, got {s!r}')
    return time(int(m.group(1)), int(m.group(2)))


_TOP_KEYS = frozenset(
    {
        "code",
        "customer_charge",
        "supply_charge",
        "merchant_charge",
        "demand_delivery",
        "demand_supply",
        "energy",
        "notes",
    }
)
_REQUIRED_TOP = ("code", "customer_charge", "supply_charge", "merchant_charge")
_CHARGE_KEYS = frozenset({"rate", "window"})
_WINDOW_KEYS = frozenset(
    {"months", "weekdays_only", "start", "end", "include_holidays", "excluded_holidays"}
)


def _check_keys(d: object, allowed: frozenset[str], where: str) -> dict:
    """Reject unknown or misspelled keys (F3.8), naming them."""
    if not isinstance(d, dict):
        raise ConEdBillingError(f"{where}: expected a mapping, got {type(d).__name__}")
    unknown = [k for k in d if k not in allowed]
    if unknown:
        raise ConEdBillingError(f"{where}: unknown key(s) {unknown}; allowed: {sorted(allowed)}")
    return d


def _window_from_dict(d: dict, where: str = "window") -> TimeWindow:
    _check_keys(d, _WINDOW_KEYS, where)
    return TimeWindow(
        months=d.get("months"),
        weekdays_only=d.get("weekdays_only"),
        start=_parse_time(d.get("start"), field="start"),
        end=_parse_time(d.get("end"), field="end"),
        include_holidays=d.get("include_holidays", False),
        excluded_holidays=d.get("excluded_holidays"),
    )


def _charges(data: dict, key: str, path: Path) -> list[tuple[float, TimeWindow]]:
    out = []
    for i, c in enumerate(data.get(key) or []):
        where = f"{path.name}: {key}[{i}]"
        _check_keys(c, _CHARGE_KEYS, where)
        if "rate" not in c or "window" not in c:
            raise ConEdBillingError(f"{where}: needs both rate and window")
        out.append((c["rate"], _window_from_dict(c["window"], f"{where}.window")))
    return out


def load_rate(path: Path) -> RateSchedule:
    """Load a legacy-format tariff YAML (see tariffs/schema.txt).

    Unknown or misspelled keys raise :class:`ConEdBillingError` (WP3). The
    validated, dated schema is :mod:`coned_billing.tariff_schema`.
    """
    path = Path(path)
    data = _check_keys(yaml.safe_load(path.read_text()), _TOP_KEYS, path.name)
    missing = [k for k in _REQUIRED_TOP if k not in data]
    if missing:
        raise ConEdBillingError(f"{path.name}: missing required key(s) {missing}")

    demand = [DemandCharge(rate=r, window=w) for r, w in _charges(data, "demand_delivery", path)]
    demand_supply = [
        DemandCharge(rate=r, window=w) for r, w in _charges(data, "demand_supply", path)
    ]
    energy = [EnergyCharge(rate=r, window=w) for r, w in _charges(data, "energy", path)]

    return RateSchedule(
        code=data["code"],
        customer_charge=data["customer_charge"],
        demand_components=demand,
        demand_supply=demand_supply,
        energy_components=energy,
        supply_charge=data["supply_charge"],
        merchant_charge=data["merchant_charge"],
    )


def load_all(directory: Path) -> list[RateSchedule]:
    return [load_rate(p) for p in directory.glob("*.yml")]
