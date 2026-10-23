from datetime import time

import numpy as np
import pandas as pd
import pytest

from coned_billing.calendars import _CONED_HOLIDAYS
from coned_billing.models import (
    DemandCharge,
    EnergyCharge,
    RateSchedule,
    TimeWindow,
)


# ───────────────────────────── TimeWindow.mask ─────────────────────────────
def _daily_index(start: str, periods: int) -> pd.DatetimeIndex:
    return pd.date_range(start=start, periods=periods, freq="D", tz="America/New_York")


def test_timewindow_filters_months():
    idx = _daily_index("2023-01-30", periods=5)  # spans Jan and Feb
    window = TimeWindow(months=(1,))

    mask = window.mask(idx)

    assert mask.tolist() == [True, True, False, False, False]


def test_timewindow_weekday_and_weekend_flags():
    idx = _daily_index("2023-01-06", periods=4)  # Fri → Mon
    weekday_window = TimeWindow(weekdays_only=True)
    weekend_window = TimeWindow(weekdays_only=False)

    assert weekday_window.mask(idx).tolist() == [True, False, False, True]
    assert weekend_window.mask(idx).tolist() == [False, True, True, False]


def test_timewindow_excludes_holidays_by_default():
    reference_holiday = min(_CONED_HOLIDAYS)
    idx = pd.DatetimeIndex(
        [
            reference_holiday - pd.Timedelta(days=1),
            reference_holiday,
        ]
    )

    default_window = TimeWindow()
    include_window = TimeWindow(include_holidays=True)

    assert default_window.mask(idx).tolist() == [True, False]
    assert include_window.mask(idx).tolist() == [True, True]


def test_timewindow_time_bounds_are_half_open():
    idx = pd.date_range(
        "2023-01-01 07:30",
        periods=4,
        freq="30min",
        tz="America/New_York",
    )
    window = TimeWindow(start=time(8, 0), end=time(9, 0))

    # 07:30 excluded, 08:00 & 08:30 included, 09:00 excluded (half-open interval)
    assert window.mask(idx).tolist() == [False, True, True, False]


# ───────────────────────────── RateSchedule.bill ───────────────────────────
def _base_schedule() -> RateSchedule:
    return RateSchedule(
        code="TEST",
        customer_charge=30.0,
        demand_components=[DemandCharge(rate=5.0, window=TimeWindow())],
        demand_supply=[DemandCharge(rate=2.0, window=TimeWindow())],
        energy_components=[
            EnergyCharge(rate=10.0, window=TimeWindow(start=time(0, 0), end=time(12, 0))),
            EnergyCharge(rate=20.0, window=TimeWindow(start=time(12, 0), end=None)),
        ],
        supply_charge=2.0,
        merchant_charge=1.0,
    )


def test_bill_regular_frequency_components_sum():
    idx = pd.date_range(
        "2023-03-01",
        periods=24,
        freq="h",
        tz="America/New_York",
    )
    load = pd.DataFrame({"kW": 1.0}, index=idx)
    sched = _base_schedule()

    monthly = sched.bill(load)
    period = pd.Period("2023-03", freq="M")

    hours_morning = 12
    hours_afternoon = 12
    kwh_total = hours_morning + hours_afternoon
    energy_expected = (
        hours_morning * 1.0 * 10.0 / 100.0
        + hours_afternoon * 1.0 * 20.0 / 100.0
        + kwh_total * (2.0 + 1.0) / 100.0
    )
    demand_expected = 5.0 * 1.0
    demand_supply_expected = 2.0 * 1.0
    customer_expected = 30.0

    assert monthly.loc[period, "energy_cost"] == pytest.approx(energy_expected)
    assert monthly.loc[period, "demand_cost"] == pytest.approx(demand_expected)
    assert monthly.loc[period, "demand_supply_cost"] == pytest.approx(demand_supply_expected)
    assert monthly.loc[period, "customer_charge"] == pytest.approx(customer_expected)
    assert monthly.loc[period, "total"] == pytest.approx(
        energy_expected + demand_expected + demand_supply_expected + customer_expected
    )


def test_bill_handles_irregular_intervals():
    idx = pd.to_datetime(
        [
            "2023-05-01 08:00",
            "2023-05-01 08:45",
            "2023-05-01 13:15",
        ]
    ).tz_localize("America/New_York")
    load = pd.DataFrame({"kW": [4.0, 6.0, 8.0]}, index=idx)
    sched = _base_schedule()

    monthly = sched.bill(load)
    period = pd.Period("2023-05", freq="M")

    dt_hours = np.array([1.0, 0.75, 4.5])  # first row defaults to 1 hour
    kwh = load["kW"].to_numpy() * dt_hours
    component_rates = np.array([10.0, 10.0, 20.0])
    energy_expected = np.sum(kwh * component_rates / 100.0) + np.sum(kwh) * (2.0 + 1.0) / 100.0

    demand_expected = 5.0 * 8.0
    demand_supply_expected = 2.0 * 8.0
    customer_expected = 30.0

    assert monthly.loc[period, "energy_cost"] == pytest.approx(energy_expected)
    assert monthly.loc[period, "demand_cost"] == pytest.approx(demand_expected)
    assert monthly.loc[period, "demand_supply_cost"] == pytest.approx(demand_supply_expected)
    assert monthly.loc[period, "customer_charge"] == pytest.approx(customer_expected)


def test_bill_accepts_ts_column_and_multiple_customers():
    data = pd.DataFrame(
        {
            "ts": pd.date_range(
                "2023-07-01",
                periods=2,
                freq="h",
                tz="America/New_York",
            ),
            "kW": [2.0, 4.0],
        }
    )
    sched = _base_schedule()

    monthly = sched.bill(data, kw_col="kW", ts_col="ts", n_customers=3)
    period = pd.Period("2023-07", freq="M")

    assert monthly.loc[period, "customer_charge"] == pytest.approx(30.0 * 3)
    assert not monthly.loc[period].isna().any()
