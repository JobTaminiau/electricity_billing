from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import time

import numpy as np
import pandas as pd

from .calendars import _CONED_HOLIDAYS
from .errors import LoadDataError
from .load import GapPolicy, Label, LoadProfile

__all__ = [
    "DemandCharge",
    "EnergyCharge",
    "RateSchedule",
    "TimeWindow",
]


# ──────────────────────────────────── helpers ────────────────────────────────────
def _to_minutes(t: time) -> int:  # 00:15->15
    return t.hour * 60 + t.minute


def _is_weekend(ts: pd.DatetimeIndex) -> bool:
    return ts.day_of_week >= 5  # 5=Sat,6=Sun


def _month_periods(idx: pd.DatetimeIndex) -> pd.PeriodIndex:
    """Monthly periods of the index's wall-clock time (tz dropped explicitly)."""
    naive = idx.tz_localize(None) if idx.tz is not None else idx
    return naive.to_period("M")


def _check_n_customers(n: object) -> None:
    if isinstance(n, bool) or not isinstance(n, (int, np.integer)) or n < 1:
        raise LoadDataError(f"n_customers must be a positive integer, got {n!r}")


def _infer_interval(index: pd.Index) -> pd.Timedelta:
    """Smallest elapsed spacing of a timestamp index (validated afterwards)."""
    if len(index) < 2:
        raise LoadDataError(
            "cannot infer the interval from fewer than 2 timestamps; pass interval="
        )
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise LoadDataError(
            "timestamps must be a timezone-aware DatetimeIndex; parse CSV files with "
            "coned_billing.read_load_csv"
        )
    diffs = np.diff(np.sort(index.as_unit("ns").asi8))
    positive = diffs[diffs > 0]
    if positive.size == 0:
        raise LoadDataError("all timestamps are identical")
    return pd.Timedelta(int(positive.min()), unit="ns")


# ──────────────────────────────────── core DSL ───────────────────────────────────
@dataclass(frozen=True, slots=True)
class TimeWindow:
    """Single rule for when a charge applies."""

    months: Sequence[int] | None = None  # e.g., (6, 7, 8, 9)
    weekdays_only: bool | None = None  # True=Mon-Fri, False=Sat/Sun, None=any
    start: time | None = None  # inclusive (defaults 00:00)
    end: time | None = None  # exclusive (defaults 24:00)
    include_holidays: bool = False

    def mask(self, idx: pd.DatetimeIndex) -> np.ndarray:
        m = np.full(idx.shape, True, dtype=bool)

        if self.months is not None:
            m &= idx.month.isin(self.months)
        if self.weekdays_only is True:
            m &= ~_is_weekend(idx)
        elif self.weekdays_only is False:
            m &= _is_weekend(idx)

        if not self.include_holidays:
            m &= ~idx.normalize().isin(_CONED_HOLIDAYS)

        if self.start is not None or self.end is not None:
            s = 0 if self.start is None else _to_minutes(self.start)
            e = 24 * 60 if self.end is None else _to_minutes(self.end)
            minute_of_day = idx.hour * 60 + idx.minute
            m &= (minute_of_day >= s) & (minute_of_day < e)

        return m


@dataclass(frozen=True, slots=True)
class DemandCharge:
    """Peak-based $/kW multiplier."""

    rate: float  # dollars per kW
    window: TimeWindow


@dataclass(frozen=True, slots=True)
class EnergyCharge:
    """Volumetric cents/kWh multiplier."""

    rate: float  # cents per kWh
    window: TimeWindow


@dataclass(slots=True)
class RateSchedule:
    """
    Aggregate Con Ed tariff.

    Attributes
    ----------
    code                Human-readable label (e.g. "SC-2 (General, <10 kW)")
    customer_charge     $/month
    demand_components   list[DemandCharge]
    demand_supply       list[DemandCharge]
    energy_components   list[EnergyCharge]
    supply_charge       cents/kWh (flat)
    merchant_charge     cents/kWh (flat)
    """

    code: str
    customer_charge: float
    demand_components: list[DemandCharge]
    demand_supply: list[DemandCharge]
    energy_components: list[EnergyCharge]
    supply_charge: float
    merchant_charge: float

    # ──────── billing engine ────────
    def bill(
        self,
        load_df: pd.DataFrame | LoadProfile,
        kw_col: str = "kW",
        ts_col: str | None = None,
        n_customers: int = 1,  # sets the number of customers for the customer charge
        *,
        interval: str | pd.Timedelta | None = None,
        label: Label = "start",
        on_gap: GapPolicy = "raise",
    ) -> pd.DataFrame:
        """
        Parameters
        ----------
        load_df   A :class:`~coned_billing.load.LoadProfile`, or a DataFrame with a
                  tz-aware DatetimeIndex (or a column named *ts_col*) and an
                  interval-average power column *kw_col* in kW.
        interval  Interval duration of a DataFrame input ("15min", "30min", "1h").
                  If omitted, it is inferred as the smallest spacing between
                  timestamps, and the grid must then be regular (WP1). Ignored for
                  a LoadProfile.
        label     Whether DataFrame timestamps mark interval "start" (default,
                  the pre-WP1 convention) or "end".
        on_gap    "raise" (default) rejects missing intervals; "allow" bills
                  observed intervals only. Never stretches intervals.
        Returns
        -------
        DataFrame with all cost components + totals per calendar month
        (New York local time).
        """
        _check_n_customers(n_customers)
        if isinstance(load_df, LoadProfile):
            profile = load_df
        else:
            frame = load_df.set_index(ts_col) if ts_col else load_df
            if interval is None:
                interval = _infer_interval(frame.index)
            profile = LoadProfile.from_series(
                frame[kw_col],
                quantity="kW",
                interval=interval,
                label=label,
                on_gap=on_gap,
            )
        idx = profile.start  # New York interval starts
        load_kw = pd.Series(profile.kw, index=idx, name=kw_col)
        load_df = load_kw.to_frame()
        kwh = pd.Series(profile.kwh, index=idx)

        # ── Energy charges (volumetric) ──────────────────────────────────────
        energy_cost = pd.Series(0.0, index=idx)
        for ec in self.energy_components:
            mask = ec.window.mask(idx)
            energy_cost[mask] += kwh[mask] * ec.rate / 100.0

        # Flat supply + merchant
        energy_cost += kwh * (self.supply_charge + self.merchant_charge) / 100.0

        # ── Demand charges (peak) ────────────────────────────────────────────
        demand_delivery_cost = pd.Series(0.0, index=idx)
        demand_supply_cost = pd.Series(0.0, index=idx)
        grouped = load_df.groupby(_month_periods(load_df.index))
        for _period, sub in grouped:
            for dc in self.demand_components:
                mask = dc.window.mask(sub.index)
                if mask.any():
                    peak_kw = sub.loc[mask, kw_col].max()
                    demand_delivery_cost.loc[sub.index] += dc.rate * peak_kw / len(sub)
            for sc in self.demand_supply:
                mask = sc.window.mask(sub.index)
                if mask.any():
                    peak_kw = sub.loc[mask, kw_col].max()
                    demand_supply_cost.loc[sub.index] += sc.rate * peak_kw / len(sub)

        # ── Monthly customer charge ─────────────────────────────────────────
        monthly_fee = (
            grouped.size().rename("obs_count").to_frame() * 0.0  # broadcast shape
            + self.customer_charge * n_customers
        )

        # ── Summaries ───────────────────────────────────────────────────────
        result = pd.DataFrame(
            {
                "energy_cost": energy_cost,
                "demand_cost": demand_delivery_cost,
                "demand_supply_cost": demand_supply_cost,
                kw_col: load_kw,
            }
        )

        # Group on local wall-clock months (identical to the former
        # ``resample("M", kind="period")``, which pandas 3 removed).
        monthly = (
            result.groupby(_month_periods(idx)).sum(numeric_only=True).join(monthly_fee, how="left")
        )
        monthly["customer_charge"] = monthly.pop("obs_count")
        monthly["total"] = (
            monthly["energy_cost"]
            + monthly["demand_cost"]
            + monthly["demand_supply_cost"]
            + monthly["customer_charge"]
        )

        return monthly


"""
Bill amounts are averages of twelve monthly bills for each year,
based on the consumption level indicated on each chart. Actual customer consumption and demand will
vary
Delivery Charges include:
Customer Charge: INCLUDED
Delivery (Energy): INCLUDED
Delivery (Demand): INCLUDED
Monthly Adjustment Clause ("MAC"): NOT INCLUDED,
MAC Adjustment: NOT INCLUDED
Billing and Payment Processing Charge: NOT INCLUDED
Delivery Revenue Surcharge: NOT INCLUDED
Revenue Decoupling Mechanism Adjustment: NOT INCLUDED
Dynamic Load Management Surcharge: NOT INCLUDED
Metering Charges: NOT INCLUDED,
VDER Cost Recovery: NOT INCLUDED
AMP Recovery: NOT INCLUDED
EVMR Charge: NOT INCLUDED

Commodity charges include:
Market Supply Charge ("MSC")
MSC I Adjustment
Merchant Function Charge
MSC II Adjustment
Clean Energy Standard Supply Surcharge.

Surcharges include:
Systems Benefits Charge
Renewable Portfolio Standard Charge
Temporary State Assessment Surcharge,
Clean Energy Standard Delivery Surcharge
Tax Surcredit
Gross Receipts Tax.


relevant notes:
For Customers billed under SC 1 Rate V and SC 2 Rate III, maximum as-used daily demand values, where
applicable, shall be determined by calculating the highest integrated 60-minute demand ending in
each day
and being entirely comprised of intervals ending in the same time period. Such Customer’s monthly
maximum demand shall be determined by calculating the highest integrated 60-minute demand during the
billing period in which such use is made.

for tou:
The demand charge for each time period will be determined by multiplying the maximum demand for the
respective time period by the rate applicable to the demand for that time period. The total demand
charge will be
the sum of the charges for each of the time periods
"""
