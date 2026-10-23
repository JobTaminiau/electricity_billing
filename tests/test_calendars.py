"""WP2: holiday calendars and time windows (R2).

Arithmetic/calendar reference tests: every expected date is hard-coded from an
independent calendar (checked against a printed calendar for each year), never
derived from the package's own lookup.

Source-reference tests check that each holiday set cites the PSC No. 10 leaf
whose text defines it.
"""

from __future__ import annotations

from datetime import date, datetime, time

import numpy as np
import pandas as pd
import pytest

from coned_billing import ConEdBillingError, LoadProfile, RateSchedule
from coned_billing.calendars import (
    HOLIDAY_SETS,
    Holiday,
    get_holiday_set,
    holiday_date,
    is_coned_holiday,
)
from coned_billing.loader import load_rate
from coned_billing.models import DemandCharge, EnergyCharge, TimeWindow

NY = "America/New_York"

# Independent reference dates (fourth Thursday of November, last Monday of May,
# first Monday of September), read off printed calendars.
THANKSGIVING = {
    2019: date(2019, 11, 28),
    2020: date(2020, 11, 26),
    2024: date(2024, 11, 28),
    2025: date(2025, 11, 27),
    2026: date(2026, 11, 26),
    2030: date(2030, 11, 28),
    2035: date(2035, 11, 22),
}
MEMORIAL = {
    2019: date(2019, 5, 27),
    2021: date(2021, 5, 31),
    2026: date(2026, 5, 25),
    2035: date(2035, 5, 28),
}
LABOR = {
    2019: date(2019, 9, 2),
    2020: date(2020, 9, 7),
    2026: date(2026, 9, 7),
    2035: date(2035, 9, 3),
}


# ─────────────────────────── rule-based holiday dates ────────────────────────────
@pytest.mark.parametrize(("year", "expected"), sorted(THANKSGIVING.items()))
def test_thanksgiving_fourth_thursday(year, expected):
    assert holiday_date(Holiday.THANKSGIVING_DAY, year) == expected


@pytest.mark.parametrize(("year", "expected"), sorted(MEMORIAL.items()))
def test_memorial_day_last_monday_of_may(year, expected):
    assert holiday_date(Holiday.MEMORIAL_DAY, year) == expected


@pytest.mark.parametrize(("year", "expected"), sorted(LABOR.items()))
def test_labor_day_first_monday_of_september(year, expected):
    assert holiday_date(Holiday.LABOR_DAY, year) == expected


def test_fixed_date_holidays_have_no_observed_shift():
    # 2021-07-04 and 2027-07-04 are Sundays, 2021-12-25 a Saturday. The cited
    # leaves give no observed-day rule, so the civil date stays the holiday and
    # the following Monday / preceding Friday is not one.
    assert holiday_date(Holiday.INDEPENDENCE_DAY, 2021) == date(2021, 7, 4)
    assert is_coned_holiday(date(2021, 7, 5)) is False
    assert is_coned_holiday(date(2021, 12, 24)) is False
    assert is_coned_holiday(date(2027, 7, 5)) is False


def test_full_2025_coned_six_set():
    expected = {
        date(2025, 1, 1),
        date(2025, 5, 26),
        date(2025, 7, 4),
        date(2025, 9, 1),
        date(2025, 11, 27),
        date(2025, 12, 25),
    }
    assert HOLIDAY_SETS["coned_six"].dates(2025, 2025) == expected


@pytest.mark.parametrize(
    "day", ["2019-12-25", "2019-01-01", "2031-07-04", "2035-11-22", "2049-09-06"]
)
def test_holidays_outside_any_fixed_range(day):
    assert is_coned_holiday(pd.Timestamp(day)) is True


def test_invalid_year_rejected():
    with pytest.raises(ConEdBillingError, match="year"):
        holiday_date(Holiday.CHRISTMAS_DAY, 1800)


# ─────────────────────────── scalar and vector interfaces ────────────────────────
def test_scalar_interface_types():
    for when in (
        date(2023, 7, 4),
        datetime(2023, 7, 4, 9),
        pd.Timestamp("2023-07-04 09:00", tz=NY),
    ):
        result = is_coned_holiday(when)
        assert result is True and type(result) is bool
    assert is_coned_holiday(pd.Timestamp("2023-07-05")) is False


def test_vector_interface_types():
    idx = pd.DatetimeIndex(
        ["2023-01-01", "2023-01-03", "2023-11-23"]
    )  # NY day, ordinary, Thanksgiving
    out = is_coned_holiday(idx)
    assert isinstance(out, np.ndarray) and out.dtype == bool
    assert out.tolist() == [True, False, True]
    assert is_coned_holiday(pd.DatetimeIndex([])).shape == (0,)


def test_tz_aware_uses_new_york_civil_date():
    # 2023-07-05 02:00 UTC is 2023-07-04 22:00 EDT: still July 4 in New York.
    assert is_coned_holiday(pd.Timestamp("2023-07-05 02:00", tz="UTC")) is True
    # 2023-07-04 03:00 UTC is 2023-07-03 23:00 EDT: not yet July 4 in New York.
    assert is_coned_holiday(pd.Timestamp("2023-07-04 03:00", tz="UTC")) is False
    idx = pd.DatetimeIndex(["2023-07-05 02:00", "2023-07-04 03:00"]).tz_localize("UTC")
    assert is_coned_holiday(idx).tolist() == [True, False]


# ─────────────────────────── rate-specific holiday sets ──────────────────────────
def test_sc1_rate2_sets_differ_by_season():
    summer = HOLIDAY_SETS["sc1_rate2_summer"]
    winter = HOLIDAY_SETS["sc1_rate2_nonsummer"]
    assert summer.holidays == {Holiday.INDEPENDENCE_DAY, Holiday.LABOR_DAY}
    assert winter.holidays == {
        Holiday.NEW_YEARS_DAY,
        Holiday.MEMORIAL_DAY,
        Holiday.THANKSGIVING_DAY,
        Holiday.CHRISTMAS_DAY,
    }
    assert summer.holidays.isdisjoint(winter.holidays)
    assert summer.holidays | winter.holidays == HOLIDAY_SETS["coned_six"].holidays


@pytest.mark.parametrize(
    ("name", "leaf"),
    [
        ("coned_six", "leaf 389.3 rev 1"),
        ("sc1_rate2_summer", "leaf 389 rev 23"),
        ("sc1_rate2_nonsummer", "leaf 389 rev 23"),
    ],
)
def test_holiday_sets_cite_their_leaf(name, leaf):
    assert leaf in HOLIDAY_SETS[name].source
    assert "PSC No. 10" in HOLIDAY_SETS[name].source


def test_component_windows_use_their_own_holiday_set():
    # SC-1 Rate II pattern (leaf 389): summer on-peak excludes only July 4 and
    # Labor Day, so Memorial Day 2026 (May 25, non-summer anyway) and the
    # summer days are tested against the summer set.
    summer_peak = TimeWindow(
        months=(6, 7, 8, 9),
        weekdays_only=True,
        start=time(10),
        end=time(22),
        excluded_holidays="sc1_rate2_summer",
    )
    nonsummer_peak = TimeWindow(
        months=(1, 2, 3, 4, 5, 10, 11, 12),
        weekdays_only=True,
        start=time(10),
        end=time(22),
        excluded_holidays="sc1_rate2_nonsummer",
    )
    idx = pd.DatetimeIndex(
        [
            "2026-07-03 12:00",
            "2026-09-07 12:00",
            "2026-05-25 12:00",
            "2026-11-26 12:00",
            "2026-11-27 12:00",
        ]
    ).tz_localize(NY)
    # Fri Jul 3 (not a holiday in this text: no observed shift), Labor Day, Memorial Day,
    # Thanksgiving, Friday after Thanksgiving.
    assert summer_peak.mask(idx).tolist() == [True, False, False, False, False]
    assert nonsummer_peak.mask(idx).tolist() == [False, False, False, False, True]


def test_custom_holiday_list_and_unknown_names():
    hs = get_holiday_set(["independence_day", "labor_day"])
    assert hs.holidays == {Holiday.INDEPENDENCE_DAY, Holiday.LABOR_DAY}
    with pytest.raises(ConEdBillingError, match="unknown holiday name"):
        get_holiday_set(["independence_day", "juneteenth"])
    with pytest.raises(ConEdBillingError, match="unknown holiday set"):
        get_holiday_set("federal")


def test_yaml_window_excluded_holidays(tmp_path):
    path = tmp_path / "t.yml"
    path.write_text(
        """
code: TEST
customer_charge: 0
supply_charge: 0
merchant_charge: 0
energy:
  - {rate: 1.0, window: {excluded_holidays: [independence_day, labor_day]}}
"""
    )
    window = load_rate(path).energy_components[0].window
    idx = pd.DatetimeIndex(["2023-07-04 12:00", "2023-12-25 12:00"]).tz_localize(NY)
    assert window.mask(idx).tolist() == [False, True]


# ─────────────────────────── windows: bounds and validation ──────────────────────
def test_half_open_bounds_08_included_22_excluded():
    w = TimeWindow(weekdays_only=True, start=time(8), end=time(22), include_holidays=True)
    idx = pd.DatetimeIndex(
        ["2024-01-09 07:59", "2024-01-09 08:00", "2024-01-09 21:59", "2024-01-09 22:00"]
    ).tz_localize(NY)
    assert w.mask(idx).tolist() == [False, True, True, False]


def test_end_of_day_without_24_00(tmp_path):
    path = tmp_path / "t.yml"
    path.write_text(
        """
code: TEST
customer_charge: 0
supply_charge: 0
merchant_charge: 0
energy:
  - {rate: 1.0, window: {start: "22:00", end: end_of_day, include_holidays: true}}
"""
    )
    w = load_rate(path).energy_components[0].window
    assert w.end is None
    idx = pd.DatetimeIndex(
        ["2024-01-09 21:59", "2024-01-09 22:00", "2024-01-09 23:59", "2024-01-10 00:00"]
    ).tz_localize(NY)
    assert w.mask(idx).tolist() == [False, True, True, False]
    path.write_text(path.read_text().replace("end_of_day", '"24:00"'))
    with pytest.raises(ConEdBillingError, match="24:00"):
        load_rate(path)


@pytest.mark.parametrize("bad", ["8:00", "25:00", "12:60", "noon", "12:00:00"])
def test_invalid_time_strings(tmp_path, bad):
    path = tmp_path / "t.yml"
    path.write_text(
        f"""
code: TEST
customer_charge: 0
supply_charge: 0
merchant_charge: 0
energy:
  - {{rate: 1.0, window: {{start: "{bad}"}}}}
"""
    )
    with pytest.raises(ConEdBillingError, match="HH:MM"):
        load_rate(path)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"months": (0,)}, "1-12"),
        ({"months": (13,)}, "1-12"),
        ({"months": (6, 6)}, "duplicate"),
        ({"months": ()}, "empty"),
        ({"months": (True,)}, "1-12"),
        ({"start": time(22), "end": time(8)}, "overnight"),
        ({"start": time(8), "end": time(8)}, "overnight"),
        ({"start": time(8, 0, 30)}, "whole-minute"),
        ({"weekdays_only": "yes"}, "weekdays_only"),
        ({"include_holidays": True, "excluded_holidays": "coned_six"}, "not both"),
        ({"excluded_holidays": "federal"}, "unknown holiday set"),
    ],
)
def test_invalid_windows_rejected(kwargs, match):
    with pytest.raises(ConEdBillingError, match=match):
        TimeWindow(**kwargs)


def test_naive_index_rejected_by_mask():
    with pytest.raises(ConEdBillingError, match="timezone-aware"):
        TimeWindow().mask(pd.DatetimeIndex(["2024-01-02 12:00"]))


# ─────────────────────────── weekday / weekend / holiday interactions ────────────
def test_weekday_weekend_holiday_interactions():
    # 2026: Sat Jul 4 (holiday on a weekend), Mon Jul 6, Thu Nov 26 (Thanksgiving),
    # Sat Nov 28.
    idx = pd.DatetimeIndex(
        ["2026-07-04 12:00", "2026-07-06 12:00", "2026-11-26 12:00", "2026-11-28 12:00"]
    ).tz_localize(NY)
    weekday_excl = TimeWindow(weekdays_only=True)  # excludes coned_six
    weekday_incl = TimeWindow(weekdays_only=True, include_holidays=True)
    weekend_excl = TimeWindow(weekdays_only=False)
    any_excl = TimeWindow()
    assert weekday_excl.mask(idx).tolist() == [False, True, False, False]
    assert weekday_incl.mask(idx).tolist() == [False, True, True, False]
    assert weekend_excl.mask(idx).tolist() == [False, False, False, True]
    assert any_excl.mask(idx).tolist() == [False, True, False, True]


# ─────────────────────────── New York time, DST ──────────────────────────────────
def test_same_instant_utc_and_new_york_classified_identically():
    w = TimeWindow(weekdays_only=True, start=time(8), end=time(22), include_holidays=True)
    ny = pd.date_range("2024-01-01", "2024-12-31 23:45", freq="15min", tz=NY)
    np.testing.assert_array_equal(w.mask(ny), w.mask(ny.tz_convert("UTC")))
    np.testing.assert_array_equal(w.mask(ny), w.mask(ny.tz_convert("Asia/Tokyo")))


@pytest.mark.parametrize(
    ("day", "utc_of_8am"),
    [
        ("2024-03-08", "13:00"),
        ("2024-03-11", "12:00"),
        ("2024-11-01", "12:00"),
        ("2024-11-04", "13:00"),
    ],
)
def test_tou_boundary_follows_local_clock_across_dst(day, utc_of_8am):
    # 08:00 New York is 13:00 UTC under EST and 12:00 UTC under EDT.
    w = TimeWindow(weekdays_only=True, start=time(8), end=time(22), include_holidays=True)
    hh = int(utc_of_8am[:2])
    before = pd.Timestamp(f"{day} {hh - 1:02d}:00", tz="UTC")
    at = pd.Timestamp(f"{day} {hh:02d}:00", tz="UTC")
    assert w.mask(pd.DatetimeIndex([before, at])).tolist() == [False, True]


def test_dst_days_window_hours_counted_in_local_time():
    # On both DST-change Sundays an all-days 08:00-22:00 window still holds 14
    # local clock hours; the missing/repeated hour is outside the window.
    w = TimeWindow(start=time(8), end=time(22), include_holidays=True)
    for day in ("2024-03-10", "2024-11-03"):
        start = pd.Timestamp(day, tz=NY)
        idx = pd.date_range(start, start + pd.DateOffset(days=1), freq="h", inclusive="left")
        assert int(w.mask(idx).sum()) == 14


# ─────────────────────────── TOU-boundary crossing assumption (R1) ───────────────
def _bundled_windows():
    from pathlib import Path

    import coned_billing

    tdir = Path(coned_billing.__file__).parent / "tariffs"
    for path in sorted(tdir.glob("*.yml")):
        rs = load_rate(path)
        for c in [*rs.energy_components, *rs.demand_components, *rs.demand_supply]:
            yield path.name, c.window


@pytest.mark.parametrize("interval", ["5min", "15min", "30min", "1h"])
def test_no_aligned_interval_crosses_a_supported_window_boundary(interval):
    idx = pd.date_range("2024-01-01", "2025-01-01", freq=interval, tz=NY, inclusive="left")
    p = LoadProfile.from_series(
        pd.Series(1.0, index=idx), quantity="kW", interval=interval, label="start"
    )
    last = p.end - pd.Timedelta(1, unit="ns")
    for name, w in _bundled_windows():
        assert (w.mask(p.start) == w.mask(last)).all(), name


# ─────────────────────────── billing integration ─────────────────────────────────
def test_holiday_peak_excluded_from_holiday_excluding_demand_window():
    sched = RateSchedule(
        code="TEST",
        customer_charge=0.0,
        demand_components=[
            DemandCharge(
                rate=1.0, window=TimeWindow(weekdays_only=True, start=time(8), end=time(22))
            )
        ],
        demand_supply=[],
        energy_components=[EnergyCharge(rate=0.0, window=TimeWindow(include_holidays=True))],
        supply_charge=0.0,
        merchant_charge=0.0,
    )
    idx = pd.date_range("2023-07-01", "2023-07-31 23:00", freq="h", tz=NY)
    kw = pd.Series(10.0, index=idx)
    kw[pd.Timestamp("2023-07-04 15:00", tz=NY)] = 500.0  # July 4 (Tue) spike
    kw[pd.Timestamp("2023-07-05 15:00", tz=NY)] = 80.0
    out = sched.bill(LoadProfile.from_series(kw, quantity="kW", interval="1h", label="start"))
    assert out["demand_cost"].iloc[0] == pytest.approx(80.0, rel=1e-12)
