"""Regression tests for the defects confirmed in WP0 (review findings F3.1-F3.8).

Each test asserts the *correct* behaviour and is marked ``xfail(strict=True)``
with its finding ID while the defect is open. Resolved so far: F3.1 and the
CSV/local-time parts of F3.3 (WP1); F3.2 and the F3.8 end-of-day part
(WP2); F3.4 and F3.8 (WP3); F3.5 (WP4). The work package that fixes a defect
removes the marker (and may adapt the test to the new API). A strict xfail
that starts passing fails the suite: investigate it, do not delete the test.

Expected values are independent of the package: durations, hand arithmetic,
calendar dates, and rates read from the bundled 02/01/2026 leaves.
"""

from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import coned_billing
from coned_billing import calendars
from coned_billing.billing import bill
from coned_billing.demand import billed_demand
from coned_billing.errors import DemandDeterminationError, LoadDataError, TariffSelectionError
from coned_billing.load import LoadProfile
from coned_billing.loader import load_rate
from coned_billing.models import EnergyCharge, RateSchedule, TimeWindow
from coned_billing.tariff_schema import default_registry

TARIFFS = Path(coned_billing.__file__).parent / "tariffs"
NY = "America/New_York"


def _xfail(finding: str):
    return pytest.mark.xfail(strict=True, reason=finding)


def _energy_only(cents_per_kwh: float = 100.0) -> RateSchedule:
    """Energy-only schedule at 1 $/kWh, so ``energy_cost`` in $ equals kWh."""
    return RateSchedule(
        code="TEST",
        customer_charge=0.0,
        demand_components=[],
        demand_supply=[],
        energy_components=[
            EnergyCharge(rate=cents_per_kwh, window=TimeWindow(include_holidays=True))
        ],
        supply_charge=0.0,
        merchant_charge=0.0,
    )


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "tariff.yml"
    p.write_text(textwrap.dedent(body))
    return p


# ───────────────────────────── F3.1 interval energy ─────────────────────────────
def test_energy_independent_of_freq_metadata():
    idx = pd.date_range("2024-01-01", periods=4, freq="15min", tz=NY)
    no_freq = pd.DatetimeIndex(list(idx))
    assert no_freq.freq is None
    # 4 intervals x 0.25 h x 1 kW = 1 kWh exactly.
    for index in (idx, no_freq):
        cost = _energy_only().bill(pd.DataFrame({"kW": 1.0}, index=index))["energy_cost"].sum()
        assert cost == pytest.approx(1.0, abs=1e-12)


def test_missing_intervals_are_not_stretched():
    idx = pd.date_range("2024-01-01", "2024-01-31 23:45", freq="15min", tz=NY)
    idx = pd.DatetimeIndex(list(idx[idx.day != 15]))
    load = pd.DataFrame({"kW": 1.0}, index=idx)
    # Either reject the gap, or bill only observed energy: 30 days x 24 h x 1 kW.
    # Default: the gap is rejected. Opt-in: only observed energy, 30 d x 24 h x 1 kW.
    with pytest.raises(LoadDataError, match="missing interval"):
        _energy_only().bill(load)
    cost = _energy_only().bill(load, on_gap="allow")["energy_cost"].sum()
    assert cost == pytest.approx(720.0, abs=1e-9)


# ───────────────────────────── F3.2 holidays ────────────────────────────────────
def test_tz_aware_july4_excluded_by_holiday_excluding_window():
    idx = pd.DatetimeIndex([pd.Timestamp("2023-07-04 12:00", tz=NY)])
    assert TimeWindow(include_holidays=False).mask(idx).tolist() == [False]


def test_utc_input_july4_local_excluded():
    # 2023-07-04 16:00 UTC is 12:00 EDT on July 4.
    idx = pd.DatetimeIndex([pd.Timestamp("2023-07-04 16:00", tz="UTC")])
    assert TimeWindow(include_holidays=False).mask(idx).tolist() == [False]


def test_thanksgiving_is_fourth_thursday():
    # Independent calendar: Nov 27 2025 and Nov 26 2026 are the fourth Thursdays.
    idx = pd.DatetimeIndex(["2025-11-06", "2025-11-27", "2026-11-05", "2026-11-26"])
    assert list(calendars.is_coned_holiday(idx)) == [False, True, False, True]


@pytest.mark.parametrize("day", ["2019-12-25", "2031-07-04", "2035-01-01"])
def test_holidays_outside_cached_range(day):
    assert list(calendars.is_coned_holiday(pd.DatetimeIndex([day]))) == [True]


def test_scalar_holiday_lookup():
    assert calendars.is_coned_holiday(pd.Timestamp("2023-07-04")) is True
    assert calendars.is_coned_holiday(pd.Timestamp("2023-07-05")) is False


def test_component_specific_holiday_set(tmp_path):
    # Fixture tariff: a window that excludes only Independence Day and Labor Day
    # (the SC-1 Rate II summer on-peak pattern). Christmas must stay inside it.
    path = _write(
        tmp_path,
        """
        code: TEST
        customer_charge: 0
        supply_charge: 0
        merchant_charge: 0
        energy:
          - rate: 1.0
            window:
              excluded_holidays: [independence_day, labor_day]
        """,
    )
    window = load_rate(path).energy_components[0].window
    idx = pd.DatetimeIndex(
        [pd.Timestamp("2023-07-04 12:00", tz=NY), pd.Timestamp("2023-12-25 12:00", tz=NY)]
    )
    assert window.mask(idx).tolist() == [False, True]


# ───────────────────────────── F3.3 local time / CSV ────────────────────────────
def test_utc_and_new_york_inputs_give_identical_bills():
    sched = load_rate(TARIFFS / "sc9_general_rate_2_TOU.yml")
    idx = pd.date_range("2023-01-01", "2023-12-31 23:00", freq="h", tz=NY)
    kw = 800 + 400 * np.sin(np.arange(len(idx)) * 2 * np.pi / 24)
    ny = sched.bill(pd.DataFrame({"kW": kw}, index=idx))["total"].sum()
    utc = sched.bill(pd.DataFrame({"kW": kw}, index=idx.tz_convert("UTC")))["total"].sum()
    assert utc == pytest.approx(ny, rel=1e-12)


def test_csv_across_dst_bills(tmp_path):
    idx = pd.date_range("2023-03-11", "2023-03-13", freq="h", tz=NY)
    load_csv = tmp_path / "load.csv"
    pd.DataFrame({"ts": idx, "kW": 1.0}).to_csv(load_csv, index=False)
    result = bill(str(load_csv), str(TARIFFS / "sc_1_res_rate_1.yml"))
    assert not result.empty


# ───────────────────────────── F3.4 tariff data ─────────────────────────────────
# Resolved in WP3 by the dated, source-cited tariff versions (coned_billing.tariff_schema).
# The legacy files are kept unchanged as version "legacy" (D2), so these tests now
# address the versioned API.
def test_bundled_values_match_feb_2026_leaves():
    # Values read from leaf 388 r23 and leaves 445 r22 and 449 r20 (Case 25-E-0072).
    reg = default_registry()
    on = date(2026, 3, 1)
    sc1 = reg.historical("sc1_rate1", on)
    sc9 = reg.historical("sc9_rate1_lt", on)
    sc9ii = reg.historical("sc9_rate2_lt", on)
    assert sc1.component("customer_charge").rate == 21.00
    assert sc9.component("demand_delivery_summer").rate == 44.05
    assert sc9ii.component("customer_charge").rate == 510.00


def test_sc1_summer_first_250_kwh_block():
    summer = (
        default_registry()
        .historical("sc1_rate1", date(2026, 7, 1))
        .component("energy_delivery_summer")
    )
    # Leaf 388: first 250 kWh at $0.16402, over 250 kWh at $0.18858 (30-day period).
    assert summer.block_charge(600) == pytest.approx(250 * 0.16402 + 350 * 0.18858, abs=1e-9)
    # GR 10.5.2 (leaf 85): a 31-day period prorates the block to 250 * 31 / 30 kWh.
    first = 250 * 31 / 30
    assert summer.block_charge(600, elapsed_days=31) == pytest.approx(
        first * 0.16402 + (600 - first) * 0.18858, abs=1e-9
    )


def test_legacy_sc1_stray_key_is_surfaced(tmp_path):
    # The strict legacy loader names the stray key...
    path = _write(
        tmp_path,
        """
        code: TEST
        customer_charge: 0
        supply_charge: 0
        merchant_charge: 0
        0:
          sc 1 0.1466 + 0.1991
        """,
    )
    with pytest.raises(Exception, match=r"\b0\b"):
        load_rate(path)
    # ...and the bundled file's notes survive the migration to the legacy version.
    legacy = default_registry().scenario("sc1_rate1", "legacy")
    assert "sc 1 0.1466 + 0.1991" in legacy.legacy_notes


def test_load_outside_tariff_effective_period_is_rejected():
    # SC-8 Rate I is transcribed from 02/01/2020; 2019 service dates are uncovered,
    # and the undated legacy version cannot be used in historical mode.
    reg = default_registry()
    with pytest.raises(TariffSelectionError):
        reg.historical("sc8_rate1_lt", date(2019, 1, 1))
    assert "historical" not in reg.scenario("sc8_rate1_lt", "legacy").calculation_modes


# ───────────────────────────── F3.5 demand measurement ──────────────────────────
# WP4: demand follows each component's measurement rule (GR 10.4, 30-minute
# integrated demand) through coned_billing.demand. The tests use the versioned
# SC-9 Rate I tariff instead of a legacy YAML key.
def _sc9_demand():
    v = default_registry().historical("sc9_rate1_lt", date(2026, 3, 1))
    return v.component("demand_delivery_other")


def test_demand_uses_declared_integration_interval():
    idx = pd.date_range("2026-03-03 00:00", periods=96, freq="15min", tz=NY)
    kw = np.zeros(96)
    kw[3] = 40.0  # one 15-min spike; 30-min block average = (0 + 40) / 2 = 20 kW
    profile = LoadProfile.from_series(
        pd.Series(kw, index=idx), quantity="kW", interval="15min", label="start"
    )
    d = billed_demand(
        profile, _sc9_demand(), period_start=date(2026, 3, 3), period_end=date(2026, 3, 4)
    )
    assert d.kw == pytest.approx(20.0, abs=1e-12)


def test_hourly_input_rejected_for_30min_demand():
    idx = pd.date_range("2026-03-03", periods=24, freq="h", tz=NY)
    profile = LoadProfile.from_series(
        pd.Series(1.0, index=idx), quantity="kW", interval="1h", label="start"
    )
    with pytest.raises(DemandDeterminationError, match=r"(?i)resolution"):
        billed_demand(
            profile, _sc9_demand(), period_start=date(2026, 3, 3), period_end=date(2026, 3, 4)
        )


# ───────────────────────────── F3.6 bill coverage ───────────────────────────────
@_xfail("F3.6: result does not state completeness or excluded components")
def test_result_reports_completeness_status():
    sc9 = load_rate(TARIFFS / "sc9_general_rate_1_LT.yml")
    idx = pd.date_range("2024-01-01", "2024-01-31 23:00", freq="h", tz=NY)
    out = sc9.bill(pd.DataFrame({"kW": 1.0}, index=idx))
    assert "completeness_status" in out.columns
    # GR 26 adjustments are not modeled, so this can never be a complete bill.
    assert (out["completeness_status"] != "complete").all()


# ───────────────────────────── F3.7 output units ────────────────────────────────
@_xfail("F3.7: monthly output sums a kW column")
def test_monthly_output_reports_kwh_and_peak_not_summed_kw():
    idx = pd.date_range("2023-01-01", "2023-01-31 23:00", freq="h", tz=NY)
    out = _energy_only().bill(pd.DataFrame({"kW": 10.0}, index=idx))
    assert "kW" not in out.columns
    kwh_cols = [c for c in out.columns if "kwh" in c.lower()]
    peak_cols = [c for c in out.columns if "peak" in c.lower() and "kw" in c.lower()]
    assert kwh_cols and out[kwh_cols[0]].iloc[0] == pytest.approx(7440.0)  # 744 h x 10 kW
    assert peak_cols and out[peak_cols[0]].iloc[0] == pytest.approx(10.0)


@_xfail("F3.7: delivery, supply and merchant energy costs are combined")
def test_energy_cost_categories_reported_separately():
    sched = RateSchedule(
        code="TEST",
        customer_charge=0.0,
        demand_components=[],
        demand_supply=[],
        energy_components=[EnergyCharge(rate=10.0, window=TimeWindow(include_holidays=True))],
        supply_charge=5.0,
        merchant_charge=1.0,
    )
    idx = pd.date_range("2023-01-01", periods=10, freq="h", tz=NY)
    out = sched.bill(pd.DataFrame({"kW": 1.0}, index=idx))
    # 10 kWh: delivery $1.00, supply $0.50, merchant $0.10.
    assert out["delivery_energy_cost"].iloc[0] == pytest.approx(1.00)
    assert out["supply_energy_cost"].iloc[0] == pytest.approx(0.50)
    assert out["merchant_cost"].iloc[0] == pytest.approx(0.10)


# ───────────────────────────── F3.8 schema permissiveness ───────────────────────
def test_misspelled_window_key_rejected(tmp_path):
    path = _write(
        tmp_path,
        """
        code: TEST
        customer_charge: 0
        supply_charge: 0
        merchant_charge: 0
        demand_delivery:
          - {rate: 1.0, window: {weekday_only: true, start: "08:00", end: "18:00"}}
        energy:
          - {rate: 0, window: {include_holidays: true}}
        """,
    )
    with pytest.raises(Exception, match="weekday_only"):
        load_rate(path)


def test_end_of_day_24_00_is_explicit(tmp_path):
    path = _write(
        tmp_path,
        """
        code: TEST
        customer_charge: 0
        supply_charge: 0
        merchant_charge: 0
        energy:
          - {rate: 1.0, window: {start: "22:00", end: "24:00", include_holidays: true}}
        """,
    )
    # Correct behaviour is either a schema error that names the end-of-day rule,
    # or a window that runs to midnight. A bare datetime.time ValueError is neither.
    try:
        window = load_rate(path).energy_components[0].window
    except Exception as exc:
        assert "24:00" in str(exc)
        return
    idx = pd.DatetimeIndex([pd.Timestamp(f"2024-01-02 {h}:00", tz=NY) for h in (21, 22, 23)])
    assert window.mask(idx).tolist() == [False, True, True]
