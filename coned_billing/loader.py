import yaml
from datetime import time
from pathlib import Path
from typing import Dict, List

from .models import RateSchedule, DemandCharge, EnergyCharge, TimeWindow


# helper ───────────────────────────────────────────────────────────────────
def _parse_time(s: str | None) -> time | None:
    if s is None:
        return None
    hh, mm = map(int, s.split(":"))
    return time(hh, mm)


def _window_from_dict(d: Dict) -> TimeWindow:
    return TimeWindow(
        months=d.get("months"),
        weekdays_only=d.get("weekdays_only"),
        start=_parse_time(d.get("start")),
        end=_parse_time(d.get("end")),
        include_holidays=d.get("include_holidays", False),
    )


def load_rate(path: Path) -> RateSchedule:
    data = yaml.safe_load(path.read_text())

    demand = [
        DemandCharge(rate=dc["rate"], window=_window_from_dict(dc["window"]))
        for dc in data.get("demand", [])
    ]
    energy = [
        EnergyCharge(rate=ec["rate"], window=_window_from_dict(ec["window"]))
        for ec in data.get("energy", [])
    ]

    return RateSchedule(
        code=data["code"],
        customer_charge=data["customer_charge"],
        demand_components=demand,
        energy_components=energy,
        supply_charge=data["supply_charge"],
        merchant_charge=data["merchant_charge"],
    )


def load_all(directory: Path) -> List[RateSchedule]:
    return [load_rate(p) for p in directory.glob("*.yml")]
