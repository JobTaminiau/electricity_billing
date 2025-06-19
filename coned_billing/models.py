from __future__ import annotations
from dataclasses import dataclass
from datetime import time
from typing import Sequence

import numpy as np
import pandas as pd

from .calendars import _CONED_HOLIDAYS

__all__ = [
    "TimeWindow",
    "DemandCharge",
    "EnergyCharge",
    "RateSchedule",
]


# ──────────────────────────────────── helpers ────────────────────────────────────
def _to_minutes(t: time) -> int:  # 00:15->15
    return t.hour * 60 + t.minute


def _is_weekend(ts: pd.Timestamp) -> bool:
    return ts.weekday() >= 5  # 5=Sat,6=Sun


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
    energy_components   list[EnergyCharge]
    supply_charge       cents/kWh (flat)
    merchant_charge     cents/kWh (flat)
    """

    code: str
    customer_charge: float
    demand_components: list[DemandCharge]
    energy_components: list[EnergyCharge]
    supply_charge: float
    merchant_charge: float
    n_customers: int = 1  # sets the number of customers for the customer charge

    # ──────── billing engine ────────
    def bill(
        self,
        load_df: pd.DataFrame,
        kw_col: str = "kW",
        ts_col: str | None = None,
    ) -> pd.DataFrame:
        """
        Parameters
        ----------
        load_df   DataFrame with a tz-aware DateTimeIndex or a column named *ts_col*
                  and a power column (*kW*). Can be any frequency ≤ 1 h.
        Returns
        -------
        DataFrame with all cost components + totals per calendar month
        """
        if ts_col:
            load_df = load_df.set_index(ts_col)
        load_df = load_df.sort_index()
        idx = load_df.index  # convenience

        # convert each row's demand (kW) into energy (kWh for that interval)
        if idx.freq is not None:  # regular grid → fast path
            kwh = load_df[kw_col] * (idx.freq.delta / pd.Timedelta("1h"))
        else:  # fallback: variable intervals
            dt_hours = (
                idx.to_series()
                .diff()
                .dt.total_seconds()
                .fillna(0)
                .div(3600.0)
                .replace(0, 1)  # first row or zero-width → assume 1 h
            )
            kwh = load_df[kw_col] * dt_hours

        # ── Energy charges (volumetric) ──────────────────────────────────────
        energy_cost = pd.Series(0.0, index=idx)
        for ec in self.energy_components:
            mask = ec.window.mask(idx)
            energy_cost[mask] += kwh[mask] * ec.rate / 100.0

        # Flat supply + merchant
        energy_cost += kwh * (self.supply_charge + self.merchant_charge) / 100.0

        # ── Demand charges (peak) ────────────────────────────────────────────
        demand_cost = pd.Series(0.0, index=idx)
        grouped = load_df.groupby(load_df.index.to_period("M"))
        for period, sub in grouped:
            for dc in self.demand_components:
                mask = dc.window.mask(sub.index)
                if mask.any():
                    peak_kw = sub.loc[mask, kw_col].max()
                    demand_cost.loc[sub.index] += dc.rate * peak_kw / len(sub)

        # ── Monthly customer charge ─────────────────────────────────────────
        monthly_fee = (
            grouped.size().rename("obs_count").to_frame()
            * 0.0  # broadcast shape
            + self.customer_charge * self.n_customers
        )

        # ── Summaries ───────────────────────────────────────────────────────
        result = pd.DataFrame(
            {
                "energy_cost": energy_cost,
                "demand_cost": demand_cost,
                kw_col: load_df[kw_col],
            }
        )

        monthly = (
            result.resample("M", kind="period").sum(numeric_only=True).join(monthly_fee, how="left")
        )
        monthly["customer_charge"] = monthly.pop("obs_count")
        monthly["total"] = (
            monthly["energy_cost"] + monthly["demand_cost"] + monthly["customer_charge"]
        )

        return monthly
