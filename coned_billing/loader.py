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


def _window_from_dict(d: dict) -> TimeWindow:
    return TimeWindow(
        months=d.get("months"),
        weekdays_only=d.get("weekdays_only"),
        start=_parse_time(d.get("start"), field="start"),
        end=_parse_time(d.get("end"), field="end"),
        include_holidays=d.get("include_holidays", False),
        excluded_holidays=d.get("excluded_holidays"),
    )


def load_rate(path: Path) -> RateSchedule:
    data = yaml.safe_load(path.read_text())

    demand = [
        DemandCharge(rate=dc["rate"], window=_window_from_dict(dc["window"]))
        for dc in data.get("demand_delivery", [])
    ]
    demand_supply = [
        DemandCharge(rate=dc["rate"], window=_window_from_dict(dc["window"]))
        for dc in data.get("demand_supply", [])
    ]
    energy = [
        EnergyCharge(rate=ec["rate"], window=_window_from_dict(ec["window"]))
        for ec in data.get("energy", [])
    ]

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
