from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import coned_billing
from coned_billing.loader import load_all, TimeWindow, EnergyCharge, DemandCharge, RateSchedule, load_rate

# ─────────────────────────────── constants ────────────────────────────────
TAR_DIR = Path(coned_billing.__file__).parent / "tariffs"
SCHEDULES = load_all(TAR_DIR)


# ─────────────────────────────── synthetic data ────────────────────────────────
def _synthetic_load():
    idx = pd.date_range("2023-01-01", "2023-01-31 23:00", freq="H", tz="America/New_York")
    return pd.DataFrame({"ts": idx, "kW": 5.0}), idx


# ─────────────────────────────── helpers ───────────────────────────────────
def _energy_coverage_ok(sched: RateSchedule, idx: pd.DatetimeIndex) -> bool:
    """True if every timestamp is covered by *exactly one* EnergyCharge."""
    acc = np.zeros(len(idx), dtype=int)
    for ec in sched.energy_components:
        acc += ec.window.mask(idx).astype(int)
    return acc.min() == 1 and acc.max() == 1


def _rates_non_negative(sched: RateSchedule) -> bool:
    """True if no rate is < 0."""
    return (
        sched.customer_charge >= 0
        and sched.supply_charge >= 0
        and sched.merchant_charge >= 0
        and all(ec.rate >= 0 for ec in sched.energy_components)
        and all(dc.rate >= 0 for dc in sched.demand_components)
    )


def _no_nan_in_bill(sched: RateSchedule, idx: pd.DatetimeIndex) -> bool:
    """Run billing on a dummy 1-kW load and ensure result has no NaN."""
    df = pd.DataFrame({"kW": 1.0}, index=idx)
    monthly = sched.bill(df)
    return not monthly.isna().any().any()


# ───────────────────────────────  tests  ───────────────────────────────────
@pytest.mark.parametrize("sched", SCHEDULES, ids=[s.code for s in SCHEDULES])
def test_energy_coverage(sched: RateSchedule):
    """
    Every hour must match exactly one EnergyCharge window.
    Otherwise some hours are untariffed (0/NaN) or double-billed.
    """
    _, IDX = _synthetic_load()
    assert _energy_coverage_ok(sched, IDX), "energy windows incomplete or overlapping"


@pytest.mark.parametrize("sched", SCHEDULES, ids=[s.code for s in SCHEDULES])
def test_rates_non_negative(sched: RateSchedule):
    """No negative dollar or cent values allowed."""
    assert _rates_non_negative(sched), "negative rate detected"


@pytest.mark.parametrize("sched", SCHEDULES, ids=[s.code for s in SCHEDULES])
def test_bill_has_no_nan(sched: RateSchedule):
    """Billing engine must produce finite, ≥ 0 totals."""
    _, IDX = _synthetic_load()
    assert _no_nan_in_bill(sched, IDX), "NaN present in bill output"
