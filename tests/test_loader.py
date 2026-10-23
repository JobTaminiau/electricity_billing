from datetime import time
from pathlib import Path

import coned_billing
from coned_billing.loader import (
    _parse_time,
    _window_from_dict,
    load_all,
    load_rate,
)
from coned_billing.models import DemandCharge, EnergyCharge, TimeWindow

TAR_DIR = Path(coned_billing.__file__).parent / "tariffs"


def test_parse_time_handles_none_and_hhmm():
    assert _parse_time(None) is None
    assert _parse_time("07:30") == time(7, 30)


def test_window_from_dict_round_trip():
    payload = {
        "months": [6, 7, 8],
        "weekdays_only": True,
        "start": "09:00",
        "end": "17:30",
        "include_holidays": True,
    }

    window = _window_from_dict(payload)

    assert isinstance(window, TimeWindow)
    assert window.months == (6, 7, 8)
    assert window.weekdays_only is True
    assert window.start == time(9, 0)
    assert window.end == time(17, 30)
    assert window.include_holidays is True


def test_load_rate_produces_complete_schedule():
    rs = load_rate(TAR_DIR / "sc9_general_rate_1_LT.yml")

    assert rs.code.startswith("SC")
    assert rs.customer_charge > 0
    assert all(isinstance(dc, DemandCharge) for dc in rs.demand_components)
    assert all(isinstance(dc, DemandCharge) for dc in rs.demand_supply)
    assert all(isinstance(ec, EnergyCharge) for ec in rs.energy_components)
    assert rs.supply_charge >= 0
    assert rs.merchant_charge >= 0


def test_load_all_reads_all_yaml_files(tmp_path):
    schedules = load_all(TAR_DIR)
    yaml_count = len(list(TAR_DIR.glob("*.yml")))

    assert len(schedules) == yaml_count
    # All loaded schedules should be unique by code
    codes = {s.code for s in schedules}
    assert len(codes) == len(schedules)
