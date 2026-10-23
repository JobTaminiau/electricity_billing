"""Demand determination tests (WP4, R5).

Expected demands are hand arithmetic on literal load values. Rates in the SC-9
Rate II charge check were typed from leaf 449 r20 (02/01/2026), not read from
the tariff files.
"""

from __future__ import annotations

from datetime import date, time

import numpy as np
import pandas as pd
import pytest

from coned_billing.demand import (
    MonthlyDemand,
    billed_demand,
    billed_demands,
    contract_demand,
    integrated_demand,
)
from coned_billing.errors import DemandDeterminationError
from coned_billing.load import LoadProfile
from coned_billing.models import TimeWindow
from coned_billing.tariff_schema import Component, DemandMeasurement, default_registry

NY = "America/New_York"


def _component(minutes=30, convention="fixed_clock", **window):
    window.setdefault("excluded_holidays", "none")
    return Component(
        id="demand",
        name="Demand",
        category="delivery_demand",
        determinant="max_demand_kw",
        window=TimeWindow(**window),
        unit="USD/kW",
        rate=1.0,
        demand_measurement=DemandMeasurement("integrated_demand", minutes, None, convention),
    )


def _profile(start, end, freq, base=0.0, spikes=None, drop=()):
    idx = pd.date_range(start, end, freq=freq, tz=NY, inclusive="left")
    s = pd.Series(base, index=idx, dtype=float)
    for ts, kw in (spikes or {}).items():
        s[pd.Timestamp(ts, tz=NY)] = kw
    if drop:
        s = s.drop([pd.Timestamp(t, tz=NY) for t in drop])
    return LoadProfile.from_series(
        s, quantity="kW", interval=freq, label="start", on_gap="allow" if drop else "raise"
    )


def _bd(profile, component, start, end, **kw):
    return billed_demand(profile, component, period_start=start, period_end=end, **kw)


# ───────────────────────────── integration ──────────────────────────────────────
def test_constant_demand_gives_known_peak():
    p = _profile("2024-01-01", "2024-01-31", "15min", base=10.0)
    d = _bd(p, _component(), date(2024, 1, 1), date(2024, 1, 31))
    assert d.kw == pytest.approx(10.0, abs=1e-12)
    assert d.peak_start == pd.Timestamp("2024-01-01 00:00", tz=NY)  # earliest of the ties
    assert d.peak_end == pd.Timestamp("2024-01-01 00:30", tz=NY)
    assert d.status == "measured" and d.flags == ()
    assert d.n_demand_intervals == 30 * 48


@pytest.mark.parametrize(
    ("minutes", "convention", "want"),
    [
        (30, "fixed_clock", 20.0),  # (0 + 40) / 2
        (30, "rolling", 20.0),  # every 30-minute window holds one spike interval
        (60, "fixed_clock", 10.0),  # (0 + 0 + 0 + 40) / 4
        (15, "fixed_clock", 40.0),
    ],
)
def test_single_15min_spike(minutes, convention, want):
    p = _profile("2024-01-02", "2024-01-03", "15min", spikes={"2024-01-02 00:45": 40.0})
    d = _bd(p, _component(minutes, convention), date(2024, 1, 2), date(2024, 1, 3))
    assert d.kw == pytest.approx(want, abs=1e-12)


def test_five_minute_input_is_integrated_not_maximised():
    p = _profile("2024-01-02", "2024-01-03", "5min")
    s = pd.Series(p.kw.copy(), index=p.start)
    s.iloc[12:18] = [10, 20, 30, 40, 50, 60]  # 01:00-01:30
    p = LoadProfile.from_series(s, quantity="kW", interval="5min", label="start")
    d = _bd(p, _component(), date(2024, 1, 2), date(2024, 1, 3))
    assert d.kw == pytest.approx(210 / 6, abs=1e-12)  # 35 kW, not the raw 60
    assert d.peak_start == pd.Timestamp("2024-01-02 01:00", tz=NY)


def test_fixed_clock_versus_rolling():
    # 40 kW from 00:15 to 00:45 straddles the :30 boundary.
    spikes = {"2024-01-02 00:15": 40.0, "2024-01-02 00:30": 40.0}
    p = _profile("2024-01-02", "2024-01-03", "15min", spikes=spikes)
    fixed = _bd(p, _component(convention="fixed_clock"), date(2024, 1, 2), date(2024, 1, 3))
    rolling = _bd(p, _component(convention="rolling"), date(2024, 1, 2), date(2024, 1, 3))
    assert fixed.kw == pytest.approx(20.0, abs=1e-12)
    assert rolling.kw == pytest.approx(40.0, abs=1e-12)
    assert rolling.peak_start == pd.Timestamp("2024-01-02 00:15", tz=NY)


def test_fixed_clock_intervals_align_in_new_york_time_across_dst():
    p = _profile("2024-03-10", "2024-03-11", "15min", base=1.0)
    frame = integrated_demand(p, 30, "fixed_clock")
    assert len(frame) == 46  # 23-hour day
    assert set(frame.index.minute) == {0, 30}
    assert frame["complete"].all()


# ───────────────────────────── windows ──────────────────────────────────────────
def test_peak_outside_a_window_is_ignored_by_that_window_only():
    # Tuesday 2024-07-02 19:00 is inside 8 AM-10 PM but outside 8 AM-6 PM.
    p = _profile("2024-07-01", "2024-08-01", "30min", base=5.0, spikes={"2024-07-02 19:00": 90})
    narrow = _component(months=[7], weekdays_only=True, start=time(8), end=time(18))
    wide = _component(months=[7], weekdays_only=True, start=time(8), end=time(22))
    assert _bd(p, narrow, date(2024, 7, 1), date(2024, 8, 1)).kw == 5.0
    assert _bd(p, wide, date(2024, 7, 1), date(2024, 8, 1)).kw == 90.0


def test_demand_interval_must_lie_entirely_inside_the_window():
    # A rolling interval 17:45-18:15 straddles the 6 PM window end.
    spikes = {"2024-07-02 17:45": 80.0, "2024-07-02 18:00": 80.0}
    p = _profile("2024-07-02", "2024-07-03", "15min", spikes=spikes)
    c = _component(convention="rolling", start=time(8), end=time(18))
    d = _bd(p, c, date(2024, 7, 2), date(2024, 7, 3))
    assert d.kw == pytest.approx(40.0, abs=1e-12)  # 17:30-18:00: (0 + 80) / 2
    assert d.peak_start == pd.Timestamp("2024-07-02 17:30", tz=NY)


def test_sc9_rate2_additive_windows_each_take_their_own_maximum():
    v = default_registry().historical("sc9_rate2_lt", date(2026, 7, 1))
    spikes = {
        "2026-07-07 10:00": 400.0,  # Tue: inside 8-18, 8-22 and all hours
        "2026-07-08 20:00": 600.0,  # Wed: inside 8-22 and all hours
        "2026-07-11 03:00": 800.0,  # Sat: all hours only
    }
    p = _profile("2026-07-01", "2026-08-01", "30min", base=100.0, spikes=spikes)
    d = billed_demands(p, v, period_start=date(2026, 7, 1), period_end=date(2026, 8, 1))
    assert d["demand_summer_weekday_0800_1800"].kw == 400.0
    assert d["demand_summer_weekday_0800_2200"].kw == 600.0
    assert d["demand_summer_all_hours"].kw == 800.0
    assert d["demand_other_all_hours"].kw == 0.0
    assert "no_intervals_in_window" in d["demand_other_all_hours"].flags
    assert d["demand_summer_all_hours"].peak_start == pd.Timestamp("2026-07-11 03:00", tz=NY)
    # Leaf 449 r20: $11.33, $22.82 and $20.61 per kW, summed over the time periods.
    charge = sum(d[k].kw * v.component(k).rate_usd for k in d)
    assert charge == pytest.approx(400 * 11.33 + 600 * 22.82 + 800 * 20.61, abs=1e-9)


@pytest.mark.parametrize(("holidays", "want"), [("coned_six", 5.0), ("none", 70.0)])
def test_holiday_peaks_follow_the_component_holiday_set(holidays, want):
    # Thursday 2024-07-04 is Independence Day.
    p = _profile("2024-07-01", "2024-08-01", "30min", base=5.0, spikes={"2024-07-04 12:00": 70})
    c = _component(weekdays_only=True, start=time(8), end=time(22), excluded_holidays=holidays)
    assert _bd(p, c, date(2024, 7, 1), date(2024, 8, 1)).kw == want


def test_sc9_rate2_counts_a_holiday_peak():
    # Leaf 449 states the periods without holiday wording (owner: follow the leaf).
    v = default_registry().historical("sc9_rate2_lt", date(2025, 7, 1))
    p = _profile("2025-07-01", "2025-08-01", "30min", base=5.0, spikes={"2025-07-04 12:00": 70})
    d = billed_demand(
        p,
        v.component("demand_summer_weekday_0800_1800"),
        period_start=date(2025, 7, 1),
        period_end=date(2025, 8, 1),
    )
    assert d.kw == 70.0


# ───────────────────────────── resolution ───────────────────────────────────────
def test_strict_mode_rejects_hourly_input_for_30_minute_demand():
    p = _profile("2024-01-02", "2024-01-03", "1h", base=1.0)
    with pytest.raises(DemandDeterminationError, match=r"(?i)resolution is 60 minutes"):
        _bd(p, _component(), date(2024, 1, 2), date(2024, 1, 3))
    with pytest.raises(DemandDeterminationError, match=r"(?i)resolution"):
        _bd(p, _component(15), date(2024, 1, 2), date(2024, 1, 3))


def test_hourly_approximation_is_explicit_and_flagged():
    p = _profile("2024-01-02", "2024-01-03", "1h", base=1.0, spikes={"2024-01-02 14:00": 9.0})
    d = _bd(p, _component(), date(2024, 1, 2), date(2024, 1, 3), resolution="hourly_approximation")
    assert d.kw == 9.0  # the hourly average itself; no subhourly peak is invented
    assert d.status == "approximated" and d.flags == ("hourly_approximation",)
    assert d.peak_end - d.peak_start == pd.Timedelta(hours=1)
    assert d.input_interval_minutes == 60


def test_unknown_resolution_is_rejected():
    p = _profile("2024-01-02", "2024-01-03", "15min")
    with pytest.raises(DemandDeterminationError, match="resolution must be"):
        _bd(p, _component(), date(2024, 1, 2), date(2024, 1, 3), resolution="hourly")


def test_legacy_versions_use_the_raw_input_maximum_and_say_so():
    v = default_registry().scenario("sc9_rate1_lt", "legacy")
    p = _profile("2024-01-02", "2024-01-03", "15min", spikes={"2024-01-02 00:45": 40.0})
    d = billed_demands(p, v, period_start=date(2024, 1, 2), period_end=date(2024, 1, 3))
    assert {x.kw for x in d.values()} <= {40.0, 0.0}
    assert all(x.status == "unverified" and "input_interval_maximum" in x.flags for x in d.values())


# ───────────────────────────── missing data ─────────────────────────────────────
def test_missing_input_is_rejected_by_default():
    p = _profile("2024-01-02", "2024-01-03", "15min", base=3.0, drop=["2024-01-02 06:15"])
    with pytest.raises(DemandDeterminationError, match="1 of 96 input interval"):
        _bd(p, _component(), date(2024, 1, 2), date(2024, 1, 3))


def test_incomplete_demand_intervals_can_be_skipped_with_a_flag():
    p = _profile(
        "2024-01-02",
        "2024-01-03",
        "15min",
        base=3.0,
        spikes={"2024-01-02 06:00": 50.0},
        drop=["2024-01-02 06:15"],
    )
    d = _bd(p, _component(), date(2024, 1, 2), date(2024, 1, 3), on_incomplete="skip")
    assert d.kw == 3.0  # the 06:00-06:30 interval is incomplete and left out
    assert d.flags == ("incomplete_intervals_skipped",)
    assert d.n_demand_intervals == 47


def test_period_not_covered_by_the_data_is_rejected():
    p = _profile("2024-01-02", "2024-01-03", "15min", base=3.0)
    with pytest.raises(DemandDeterminationError, match="missing"):
        _bd(p, _component(), date(2024, 1, 2), date(2024, 1, 4))


# ───────────────────────────── billing periods ──────────────────────────────────
def test_only_intervals_inside_the_billing_period_count():
    spikes = {"2024-01-31 23:30": 99.0, "2024-02-01 00:00": 77.0}
    p = _profile("2024-01-01", "2024-02-03", "30min", base=1.0, spikes=spikes)
    jan = _bd(p, _component(), date(2024, 1, 1), date(2024, 2, 1))
    assert jan.kw == 99.0
    # Data after the period end never changes the period's demand.
    assert _bd(p, _component(), date(2024, 1, 1), date(2024, 2, 1)).kw == jan.kw
    feb = _bd(p, _component(), date(2024, 2, 1), date(2024, 2, 3))
    assert feb.kw == 77.0


def test_period_spanning_window_months_is_flagged():
    p = _profile("2024-05-15", "2024-06-15", "30min", base=2.0, spikes={"2024-05-20 12:00": 50})
    summer = _component(months=[6, 7, 8, 9])
    d = _bd(p, summer, date(2024, 5, 15), date(2024, 6, 15))
    assert d.kw == 2.0  # the May peak is outside the summer window
    assert (d.window_days, d.period_days) == (14, 31)
    assert "period_spans_window_months" in d.flags


def test_rate_change_inside_the_period_does_not_split_the_determinant():
    # Period 2026-01-15..2026-02-15 spans the 02/01/2026 version; GR 10.4 takes
    # one maximum per billing period, and each version's component sees it.
    reg = default_registry()
    jan = reg.historical("sc9_rate1_lt", date(2026, 1, 20)).component("demand_delivery_other")
    feb = reg.historical("sc9_rate1_lt", date(2026, 2, 10)).component("demand_delivery_other")
    p = _profile("2026-01-15", "2026-02-15", "15min", base=10.0, spikes={"2026-01-20 09:00": 60})
    for c in (jan, feb):
        d = _bd(p, c, date(2026, 1, 15), date(2026, 2, 15))
        assert d.kw == pytest.approx(35.0, abs=1e-12)  # (60 + 10) / 2
        assert d.peak_start == pd.Timestamp("2026-01-20 09:00", tz=NY)


def test_period_bounds_must_be_ordered_and_aware():
    p = _profile("2024-01-02", "2024-01-03", "15min")
    with pytest.raises(DemandDeterminationError, match="not after"):
        _bd(p, _component(), date(2024, 1, 3), date(2024, 1, 2))
    with pytest.raises(DemandDeterminationError, match="timezone-aware"):
        _bd(p, _component(), pd.Timestamp("2024-01-02"), date(2024, 1, 3))


def test_non_demand_component_is_rejected():
    v = default_registry().historical("sc9_rate1_lt", date(2026, 3, 1))
    p = _profile("2026-03-01", "2026-03-02", "15min")
    with pytest.raises(DemandDeterminationError, match="not a demand component"):
        _bd(p, v.component("energy_delivery"), date(2026, 3, 1), date(2026, 3, 2))


# ───────────────────────────── contract demand ──────────────────────────────────
def _history(first: str, kws):
    starts = pd.date_range(first, periods=len(kws), freq="MS")
    return [
        MonthlyDemand(s.date(), (s + pd.offsets.MonthBegin()).date(), float(kw))
        for s, kw in zip(starts, kws, strict=True)
    ]


def test_contract_demand_uses_the_most_recent_18_months():
    # Jan 2023 .. Jul 2025 (31 months); 900 kW in Jan 2024 is the 19th month back.
    kws = [100.0] * 31
    kws[12] = 900.0  # Jan 2024
    kws[13] = 500.0  # Feb 2024
    h = _history("2023-01-01", kws)
    as_of = date(2025, 8, 1)  # bill for July 2025
    # Including July 2025: Feb 2024 .. Jul 2025.
    assert (
        contract_demand(h, as_of=as_of, account_start=date(2023, 1, 1), include_current_period=True)
        == 500.0
    )
    # Excluding it: Jan 2024 .. Jun 2025.
    assert (
        contract_demand(
            h, as_of=as_of, account_start=date(2023, 1, 1), include_current_period=False
        )
        == 900.0
    )


def test_contract_demand_has_no_look_ahead():
    h = _history("2024-01-01", [100.0] * 12)
    kw = dict(as_of=date(2025, 1, 1), account_start=date(2024, 1, 1), include_current_period=True)
    before = contract_demand(h, **kw)
    later = h + _history("2025-01-01", [5000.0, 7000.0])
    assert contract_demand(later, **kw) == before == 100.0


def test_contract_demand_for_a_young_account_uses_all_history():
    h = _history("2025-03-01", [40.0, 75.0, 60.0])
    assert (
        contract_demand(
            h, as_of=date(2025, 6, 1), account_start=date(2025, 3, 1), include_current_period=True
        )
        == 75.0
    )


def test_contract_demand_rejects_missing_history():
    h = _history("2024-01-01", [100.0] * 12)
    del h[5]
    with pytest.raises(DemandDeterminationError, match="gap"):
        contract_demand(
            h, as_of=date(2025, 1, 1), account_start=date(2024, 1, 1), include_current_period=True
        )
    with pytest.raises(DemandDeterminationError, match="gap"):
        contract_demand(
            _history("2024-06-01", [1.0] * 7),
            as_of=date(2025, 1, 1),
            account_start=date(2023, 1, 1),
            include_current_period=True,
        )


def test_contract_demand_needs_an_explicit_current_period_choice():
    h = _history("2024-01-01", [1.0] * 12)
    with pytest.raises(DemandDeterminationError, match="True or False"):
        contract_demand(
            h, as_of=date(2025, 1, 1), account_start=date(2024, 1, 1), include_current_period=None
        )  # type: ignore[arg-type]
    with pytest.raises(DemandDeterminationError, match="not in the history"):
        contract_demand(
            h, as_of=date(2025, 2, 1), account_start=date(2024, 1, 1), include_current_period=True
        )


def test_integrated_demand_rejects_incompatible_lengths():
    p = _profile("2024-01-02", "2024-01-03", "1h")
    with pytest.raises(DemandDeterminationError, match="does not divide"):
        integrated_demand(p, 30, "fixed_clock")
    assert np.isclose(integrated_demand(p, 60, "rolling")["kW"], 0.0).all()
