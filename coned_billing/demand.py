"""Demand determination (requirement R5, WP4).

Billed demand is determined separately from energy. For each demand component
of a tariff version, :func:`billed_demand` returns the maximum demand in the
component's window during a billing period, the demand interval in which it
occurred, and machine-readable flags for every approximation.

Rules, in short (full text and sources in ``docs/demand.md``):

* **Integrated demand.** General Rule 10.4 (leaf 84) sets the maximum demand as
  "the highest 30-minute integrated demand occurring during the billing period".
  A demand interval's kW is its energy divided by its duration, i.e. the mean
  of the input interval-average kW over the demand interval. Finer input (5 or
  15 minutes) is integrated, never billed at its raw maximum.
* **Convention.** ``fixed_clock`` demand intervals start on clock multiples of
  their length in New York time (:00 and :30); ``rolling`` intervals start at
  every input interval. GR 10.4 does not say which applies; the tariff files
  state the assumption.
* **Windows.** A demand interval belongs to a component's window only if every
  input interval in it does. Each component takes its own maximum, so the
  additive SC-9 Rate II charges each get their own peak.
* **Billing period.** A demand interval counts only if it lies entirely inside
  ``[period_start, period_end)``. A rate change inside the period does not split
  the determinant: GR 10.4 takes one maximum per billing period, and GR 10.5.1
  prorates the rates (WP5).
* **Resolution.** Input coarser than the integration length is rejected unless
  the caller selects ``resolution="hourly_approximation"``: each hourly average
  is then used as the demand, which cannot be higher than the true 30-minute
  peak in that hour. The result is flagged and its status is ``approximated``.
  No subhourly peak is invented.
* **Missing data.** Missing input intervals inside the period are rejected
  unless ``on_incomplete="skip"``; demand intervals that are not complete are
  then left out and flagged.
* **Ties.** When the maximum occurs more than once, the earliest interval is
  reported.

:func:`contract_demand` implements the history-derived Contract Demand of the
SC-8 and SC-9 Minimum Monthly Charge (leaves 440 and 454) without look-ahead.
The Minimum Monthly Charge itself is not modeled (see ``docs/demand.md``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from .errors import DemandDeterminationError
from .load import TARIFF_TZ, LoadProfile

if TYPE_CHECKING:
    from .tariff_schema import Component, TariffVersion

__all__ = [
    "DEMAND_FLAGS",
    "BilledDemand",
    "MonthlyDemand",
    "billed_demand",
    "billed_demands",
    "contract_demand",
    "integrated_demand",
]

Resolution = Literal["exact", "hourly_approximation"]
OnIncomplete = Literal["raise", "skip"]
Convention = Literal["fixed_clock", "rolling"]

#: Flags a :class:`BilledDemand` can carry, with their meaning.
DEMAND_FLAGS: Mapping[str, str] = {
    "hourly_approximation": (
        "input intervals are longer than the tariff's integration interval; each input interval's "
        "average kW was used as the demand, which can understate the billed peak"
    ),
    "input_interval_maximum": (
        "legacy method: the largest input interval kW, with no integration interval (unverified)"
    ),
    "incomplete_intervals_skipped": (
        "some input intervals in the billing period are missing; demand intervals that were not "
        "complete were left out"
    ),
    "no_intervals_in_window": "no complete demand interval of the period falls in the window",
    "period_spans_window_months": (
        "the billing period contains days both inside and outside the window's months; how the "
        "charge is split is decided by the billing engine (WP5)"
    ),
}

_MINUTE = pd.Timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class BilledDemand:
    """The demand determinant of one component for one billing period.

    ``kw`` is 0.0 when no demand interval of the period falls in the window
    (flag ``no_intervals_in_window``). ``peak_start``/``peak_end`` bound the
    demand interval in which the maximum occurred, in New York time.
    ``status`` is ``measured`` when the determinant follows the component's
    measurement rule from the data given, ``approximated`` when an explicit
    approximation was selected, and ``unverified`` for the legacy method.
    """

    component_id: str
    kw: float
    peak_start: pd.Timestamp | None
    peak_end: pd.Timestamp | None
    method: str
    integration_minutes: int | None
    convention: str | None
    input_interval_minutes: int
    n_demand_intervals: int
    window_days: int
    period_days: int
    status: Literal["measured", "approximated", "unverified"]
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MonthlyDemand:
    """One billing period's maximum registered demand, for demand history."""

    period_start: date
    period_end: date  # exclusive
    kw: float


# ────────────────────────────── integration ──────────────────────────────────────
def integrated_demand(
    profile: LoadProfile,
    minutes: int,
    convention: Convention,
    *,
    in_window: np.ndarray | None = None,
) -> pd.DataFrame:
    """Integrated demand intervals of ``minutes`` length from ``profile``.

    Returns a frame indexed by demand interval start (New York time) with
    columns ``kW`` (average demand over the interval), ``complete`` (every
    input interval present) and ``in_window`` (every input interval inside the
    window given by the boolean array ``in_window``, aligned with the profile).
    The input interval must divide ``minutes``.
    """
    step = profile.interval
    length = pd.Timedelta(minutes=minutes)
    if minutes <= 0 or length % step != pd.Timedelta(0):
        raise DemandDeterminationError(
            f"input interval {_fmt(step)} does not divide the {minutes}-minute demand interval"
        )
    k = int(length // step)
    win = np.ones(len(profile), dtype=bool) if in_window is None else np.asarray(in_window, bool)
    if win.shape != (len(profile),):
        raise DemandDeterminationError("in_window must have one value per input interval")
    starts_ns = profile.start.as_unit("ns").asi8

    if convention == "fixed_clock":
        # New York offsets are whole hours, so clock alignment in New York time
        # equals alignment of UTC epoch nanoseconds for divisors of 60 minutes.
        block = starts_ns // length.value
        uniq, first, counts = np.unique(block, return_index=True, return_counts=True)
        sums = np.add.reduceat(profile.kw, first)
        win_all = np.logical_and.reduceat(win, first)
        start = pd.DatetimeIndex(pd.to_datetime(uniq * length.value, utc=True)).tz_convert(
            TARIFF_TZ
        )
        return pd.DataFrame(
            {"kW": sums / k, "complete": counts == k, "in_window": win_all},
            index=start.rename("demand_start"),
        )
    if convention == "rolling":
        n = len(profile) - k + 1
        if n <= 0:
            return pd.DataFrame(
                {"kW": [], "complete": [], "in_window": []},
                index=pd.DatetimeIndex([], tz=TARIFF_TZ, name="demand_start"),
            ).astype({"kW": float, "complete": bool, "in_window": bool})
        csum = np.concatenate(([0.0], np.cumsum(profile.kw)))
        means = (csum[k:] - csum[:-k]) / k
        # Contiguous: the k input intervals have no gap between them.
        complete = (starts_ns[k - 1 :] - starts_ns[: len(starts_ns) - k + 1]) == (
            k - 1
        ) * step.value
        wsum = np.concatenate(([0], np.cumsum(win.astype(np.int64))))
        win_all = (wsum[k:] - wsum[:-k]) == k
        return pd.DataFrame(
            {"kW": means, "complete": complete, "in_window": win_all},
            index=profile.start[:n].rename("demand_start"),
        )
    raise DemandDeterminationError(f"unknown demand convention {convention!r}")


# ────────────────────────────── billed demand ────────────────────────────────────
def billed_demand(
    profile: LoadProfile,
    component: Component,
    *,
    period_start: date | pd.Timestamp,
    period_end: date | pd.Timestamp,
    resolution: Resolution = "exact",
    on_incomplete: OnIncomplete = "raise",
) -> BilledDemand:
    """Maximum demand of ``component`` in its window during a billing period.

    ``period_start`` is inclusive and ``period_end`` exclusive; dates mean
    midnight in New York. ``resolution="exact"`` (the default, and the only
    choice for a reconstructed bill) rejects input coarser than the
    component's integration interval. ``resolution="hourly_approximation"``
    accepts it and flags the result. ``on_incomplete="skip"`` leaves out
    demand intervals with missing input instead of raising.
    """
    m = component.demand_measurement
    if component.determinant != "max_demand_kw" or m is None:
        raise DemandDeterminationError(f"component {component.id!r} is not a demand component")
    if resolution not in ("exact", "hourly_approximation"):
        raise DemandDeterminationError(
            f"resolution must be 'exact' or 'hourly_approximation', got {resolution!r}"
        )
    if on_incomplete not in ("raise", "skip"):
        raise DemandDeterminationError(
            f"on_incomplete must be 'raise' or 'skip', got {on_incomplete!r}"
        )
    t0, t1 = _instant(period_start, "period_start"), _instant(period_end, "period_end")
    if t1 <= t0:
        raise DemandDeterminationError(f"billing period end {t1} is not after start {t0}")

    step = profile.interval
    in_period = (profile.start >= t0) & (profile.end <= t1)
    expected = (t1 - t0) // step
    present = int(in_period.sum())
    flags: list[str] = []
    if present < expected:
        if on_incomplete == "raise":
            raise DemandDeterminationError(
                f"{expected - present} of {expected} input interval(s) in the billing period "
                f"[{t0}, {t1}) are missing; demand cannot be determined from incomplete data. "
                "Pass on_incomplete='skip' to leave out incomplete demand intervals (flagged)."
            )
        flags.append("incomplete_intervals_skipped")

    sub = _subset(profile, in_period)
    window = component.window.mask(sub.start) if len(sub) else np.zeros(0, bool)
    status: Literal["measured", "approximated", "unverified"] = "measured"
    minutes, convention = m.integration_minutes, m.convention

    if m.method == "input_interval_maximum":
        status = "unverified"
        flags.append("input_interval_maximum")
        frame = pd.DataFrame(
            {"kW": sub.kw, "complete": True, "in_window": window},
            index=sub.start.rename("demand_start"),
        )
        length = step
    else:
        assert minutes is not None and convention is not None
        length = pd.Timedelta(minutes=minutes)
        if step > length:
            if resolution == "exact":
                raise DemandDeterminationError(
                    f"component {component.id!r} bills the highest {minutes}-minute integrated "
                    f"demand, but the input resolution is {_fmt(step)}. A coarser resolution "
                    "cannot reproduce the billed demand; supply interval data of "
                    f"{minutes} minutes or finer, or select resolution='hourly_approximation' "
                    "for a flagged scenario estimate."
                )
            status = "approximated"
            flags.append("hourly_approximation")
            frame = pd.DataFrame(
                {"kW": sub.kw, "complete": True, "in_window": window},
                index=sub.start.rename("demand_start"),
            )
            length = step
        else:
            frame = (
                integrated_demand(sub, minutes, convention, in_window=window)
                if len(sub)
                else _empty()
            )

    usable = frame[frame["complete"].to_numpy() & frame["in_window"].to_numpy()]
    window_days, period_days = _window_days(component, t0, t1)
    if 0 < window_days < period_days:
        flags.append("period_spans_window_months")
    if usable.empty:
        flags.append("no_intervals_in_window")
        kw, peak = 0.0, None
    else:
        kws = usable["kW"].to_numpy()
        i = int(np.argmax(kws))  # first occurrence: the earliest peak
        kw, peak = float(kws[i]), usable.index[i]
    return BilledDemand(
        component_id=component.id,
        kw=kw,
        peak_start=peak,
        peak_end=None if peak is None else peak + length,
        method=m.method,
        integration_minutes=minutes,
        convention=convention,
        input_interval_minutes=int(step // _MINUTE),
        n_demand_intervals=len(usable),
        window_days=window_days,
        period_days=period_days,
        status=status,
        flags=tuple(flags),
    )


def billed_demands(
    profile: LoadProfile,
    version: TariffVersion,
    *,
    period_start: date | pd.Timestamp,
    period_end: date | pd.Timestamp,
    resolution: Resolution = "exact",
    on_incomplete: OnIncomplete = "raise",
) -> dict[str, BilledDemand]:
    """:func:`billed_demand` for every demand component of ``version``."""
    return {
        c.id: billed_demand(
            profile,
            c,
            period_start=period_start,
            period_end=period_end,
            resolution=resolution,
            on_incomplete=on_incomplete,
        )
        for c in version.components
        if c.determinant == "max_demand_kw"
    }


# ────────────────────────────── demand history ───────────────────────────────────
def contract_demand(
    history: Iterable[MonthlyDemand],
    *,
    as_of: date,
    account_start: date,
    include_current_period: bool,
    months: int = 18,
) -> float:
    """Contract Demand for the billing period ending ``as_of`` (exclusive end).

    SC-8 and SC-9 (leaves 440 and 454): "the Customer's highest registered
    demand in the most recent 18 months, or the highest registered demand on the
    Customer's account if the account has less than 18 months of demand
    history". Only periods that end on or before ``as_of`` are used, so data
    after the bill can never change the result. The leaves do not say whether
    the current billing period is one of the 18 months, so the caller must state
    it with ``include_current_period``. Contract Demand reductions under GR 10.10
    are not modeled.

    ``history`` must cover every day from ``max(account_start, as_of - months)``
    up to the period considered, without gaps, or a
    :class:`DemandDeterminationError` is raised.
    """
    if not isinstance(include_current_period, bool):
        raise DemandDeterminationError("include_current_period must be True or False")
    rows = sorted(history, key=lambda r: r.period_start)
    for r in rows:
        if r.period_end <= r.period_start:
            raise DemandDeterminationError(f"history period {r} ends before it starts")
        if not np.isfinite(r.kw) or r.kw < 0:
            raise DemandDeterminationError(f"history demand must be finite and >= 0, got {r.kw}")
    # Only what is known when the bill for the period ending as_of is rendered.
    known = [r for r in rows if r.period_end <= as_of]
    if not include_current_period:
        known = [r for r in known if r.period_end < as_of]
    if not known:
        raise DemandDeterminationError(f"no demand history ends on or before {as_of}")
    end = known[-1].period_end
    if include_current_period and end != as_of:
        raise DemandDeterminationError(
            f"the current billing period (ending {as_of}) is not in the history"
        )
    horizon = (pd.Timestamp(end) - pd.DateOffset(months=months)).date()
    begin = max(horizon, account_start)
    used = [r for r in known if r.period_end > begin]
    if not used:
        raise DemandDeterminationError(f"no demand history after the account start {begin}")
    covered = begin
    for r in used:
        if r.period_start > covered:
            raise DemandDeterminationError(
                f"demand history has a gap from {covered} to {r.period_start}; the Contract "
                "Demand needs every billing period back to that date"
            )
        covered = max(covered, r.period_end)
    return max(r.kw for r in used)


# ────────────────────────────── helpers ──────────────────────────────────────────
def _instant(value: date | pd.Timestamp, name: str) -> pd.Timestamp:
    if isinstance(value, pd.Timestamp):
        if value.tz is None:
            raise DemandDeterminationError(f"{name} must be timezone-aware or a date")
        return value.tz_convert(TARIFF_TZ)
    if isinstance(value, date):
        return pd.Timestamp(value).tz_localize(TARIFF_TZ)
    raise DemandDeterminationError(f"{name} must be a date or a tz-aware Timestamp")


def _subset(profile: LoadProfile, mask: np.ndarray) -> LoadProfile:
    kw = profile.kw[mask]
    return LoadProfile(start=profile.start[mask], interval=profile.interval, kw=kw)


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "kW": np.zeros(0),
            "complete": np.zeros(0, bool),
            "in_window": np.zeros(0, bool),
        },
        index=pd.DatetimeIndex([], tz=TARIFF_TZ, name="demand_start"),
    )


def _window_days(component: Component, t0: pd.Timestamp, t1: pd.Timestamp) -> tuple[int, int]:
    days = pd.date_range(t0.normalize(), t1, freq="D", inclusive="left")
    months: Sequence[int] | None = component.window.months
    if months is None:
        return len(days), len(days)
    return int(np.isin(days.month, list(months)).sum()), len(days)


def _fmt(step: pd.Timedelta) -> str:
    return f"{int(step // _MINUTE)} minutes"
