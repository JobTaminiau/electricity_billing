"""Validated interval load profiles (input contract R1, WP1).

A :class:`LoadProfile` is a strictly regular grid of intervals with an explicit
duration. Energy is always ``average kW x interval duration``; nothing is
derived from pandas ``.freq`` metadata or from gaps between timestamps.

Contract, in short (full text in ``docs/load_data.md``):

* values are interval-average power in kW, or interval energy in kWh;
* the interval duration is given explicitly (5, 15, 30 or 60 minutes);
* each timestamp marks either the start or the end of its interval, stated
  explicitly by the caller;
* timestamps are timezone-aware. Naive timestamps are rejected unless the
  caller names a timezone *and* policies for ambiguous and nonexistent local
  times;
* intervals are aligned to clock multiples of their duration in New York time;
* timestamps are unique instants and strictly increasing (unsorted input is
  rejected unless ``sort=True``);
* missing intervals are rejected by default. With ``on_gap="allow"`` they are
  recorded in :attr:`LoadProfile.gaps` and contribute no energy; adjacent
  intervals are never stretched;
* values are finite numbers; negative values are rejected on this import-only
  path;
* an empty profile is rejected. A single interval is valid, because its
  duration is explicit.

Internally interval starts are held in ``America/New_York``, the timezone in
which all Con Edison tariff calendars are evaluated.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from os import PathLike
from typing import Literal

import numpy as np
import pandas as pd

from .errors import LoadDataError

__all__ = [
    "SUPPORTED_INTERVALS",
    "TARIFF_TZ",
    "Gap",
    "LoadProfile",
    "read_load_csv",
]

TARIFF_TZ = "America/New_York"
SUPPORTED_INTERVALS: tuple[pd.Timedelta, ...] = tuple(
    pd.Timedelta(minutes=m) for m in (5, 15, 30, 60)
)

Quantity = Literal["kW", "kWh"]
Label = Literal["start", "end"]
GapPolicy = Literal["raise", "allow"]
Ambiguous = Literal["raise", "infer"]
Nonexistent = Literal["raise"]

_HOUR = pd.Timedelta(hours=1)
# A timestamp whose time of day is followed by a UTC offset or "Z" (a bare date
# such as "2024-01-01" must not be mistaken for an offset).
_HAS_OFFSET = re.compile(r"\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s*(?:Z|[+-]\d{2}(?::?\d{2})?)$")


@dataclass(frozen=True, slots=True)
class Gap:
    """A run of missing intervals: ``[start, end)`` in New York time."""

    start: pd.Timestamp
    end: pd.Timestamp
    n_intervals: int


@dataclass(frozen=True, slots=True, eq=False)
class LoadProfile:
    """A validated, regular-grid interval load profile.

    Build it with :meth:`from_series`, :meth:`from_frame` or
    :func:`read_load_csv`; the constructor assumes already-validated parts.

    Attributes
    ----------
    start
        Interval start instants, tz-aware ``America/New_York``, strictly increasing.
    interval
        Duration of every interval.
    kw
        Interval-average power in kW (float64, finite, non-negative).
    gaps
        Missing interval runs, only non-empty when built with ``on_gap="allow"``.
    """

    start: pd.DatetimeIndex
    interval: pd.Timedelta
    kw: np.ndarray
    gaps: tuple[Gap, ...] = field(default=())

    # ────────────────────────────── derived quantities ──────────────────────────
    @property
    def interval_hours(self) -> float:
        return float(self.interval / _HOUR)

    @property
    def kwh(self) -> np.ndarray:
        """Energy per interval in kWh."""
        return self.kw * self.interval_hours

    @property
    def end(self) -> pd.DatetimeIndex:
        """Interval end instants (exclusive), New York time."""
        return self.start + self.interval

    @property
    def total_kwh(self) -> float:
        return float(self.kwh.sum())

    def __len__(self) -> int:
        return len(self.start)

    def to_frame(self) -> pd.DataFrame:
        """Intervals as a DataFrame indexed by New York interval start."""
        return pd.DataFrame(
            {"interval_end": self.end, "kW": self.kw, "kWh": self.kwh},
            index=self.start.rename("interval_start"),
        )

    # ────────────────────────────── constructors ────────────────────────────────
    @classmethod
    def from_series(
        cls,
        values: pd.Series,
        *,
        quantity: Quantity,
        interval: str | pd.Timedelta,
        label: Label,
        on_gap: GapPolicy = "raise",
        sort: bool = False,
        localize_tz: str | None = None,
        ambiguous: Ambiguous | None = None,
        nonexistent: Nonexistent | None = None,
    ) -> LoadProfile:
        """Validate a Series indexed by timestamps.

        Parameters
        ----------
        values
            kW or kWh per interval, indexed by a DatetimeIndex.
        quantity
            ``"kW"`` (interval-average power) or ``"kWh"`` (interval energy).
        interval
            Interval duration, e.g. ``"15min"`` or ``"1h"``.
        label
            Whether each timestamp is the interval ``"start"`` or ``"end"``.
        on_gap
            ``"raise"`` (default) rejects missing intervals; ``"allow"`` records
            them in :attr:`gaps`. Missing energy is never imputed.
        sort
            ``False`` (default) rejects unsorted timestamps; ``True`` sorts them.
        localize_tz, ambiguous, nonexistent
            Only for timezone-naive input: the timezone of the wall-clock
            timestamps and the policies for repeated (fall-back) and skipped
            (spring-forward) local times. All three must be given.
            ``ambiguous="infer"`` resolves repeated hours from their order;
            ``nonexistent`` can only be ``"raise"``.
        """
        if not isinstance(values, pd.Series):
            raise LoadDataError(f"expected a pandas Series, got {type(values).__name__}")
        step = _validate_interval(interval)
        if quantity not in ("kW", "kWh"):
            raise LoadDataError(f"quantity must be 'kW' or 'kWh', got {quantity!r}")
        if label not in ("start", "end"):
            raise LoadDataError(f"label must be 'start' or 'end', got {label!r}")
        if on_gap not in ("raise", "allow"):
            raise LoadDataError(f"on_gap must be 'raise' or 'allow', got {on_gap!r}")
        if len(values) == 0:
            raise LoadDataError("load profile is empty")

        stamps = _as_aware_index(values.index, localize_tz, ambiguous, nonexistent)
        vals = _as_finite_float(values.to_numpy(), quantity)

        if stamps.hasnans:
            raise LoadDataError("timestamps contain NaT")
        starts = stamps - step if label == "end" else stamps
        starts = starts.tz_convert(TARIFF_TZ)

        dup = starts.duplicated()
        if dup.any():
            raise LoadDataError(
                f"{int(dup.sum())} duplicate interval instant(s), first at {starts[dup][0]}"
            )
        if not starts.is_monotonic_increasing:
            if not sort:
                raise LoadDataError("timestamps are not sorted; sort them or pass sort=True")
            order = np.argsort(starts.as_unit("ns").asi8, kind="stable")
            starts, vals = starts[order], vals[order]

        _check_alignment(starts, step)
        gaps = _find_gaps(starts, step)
        if gaps and on_gap == "raise":
            missing = sum(g.n_intervals for g in gaps)
            raise LoadDataError(
                f"{missing} missing interval(s) in {len(gaps)} gap(s), first gap "
                f"[{gaps[0].start}, {gaps[0].end}); missing energy is never imputed. "
                "Fill the data or pass on_gap='allow' to bill observed intervals only."
            )

        kw = vals / float(step / _HOUR) if quantity == "kWh" else vals
        kw = np.ascontiguousarray(kw, dtype="float64")
        kw.setflags(write=False)
        start = pd.DatetimeIndex(starts, freq=None).rename(None)
        return cls(start=start, interval=step, kw=kw, gaps=gaps)

    @classmethod
    def from_frame(
        cls,
        df: pd.DataFrame,
        *,
        value_col: str,
        quantity: Quantity,
        interval: str | pd.Timedelta,
        label: Label,
        ts_col: str | None = None,
        **kwargs,
    ) -> LoadProfile:
        """Validate a DataFrame; timestamps from ``ts_col`` or the index."""
        if value_col not in df.columns:
            raise LoadDataError(f"column {value_col!r} not found; columns are {list(df.columns)}")
        if ts_col is not None:
            if ts_col not in df.columns:
                raise LoadDataError(f"column {ts_col!r} not found; columns are {list(df.columns)}")
            series = pd.Series(df[value_col].to_numpy(), index=_to_datetime_index(df[ts_col]))
        else:
            series = df[value_col]
        return cls.from_series(series, quantity=quantity, interval=interval, label=label, **kwargs)


def read_load_csv(
    path: str | PathLike[str],
    *,
    interval: str | pd.Timedelta,
    label: Label,
    ts_col: str = "ts",
    value_col: str = "kW",
    quantity: Quantity = "kW",
    **kwargs,
) -> LoadProfile:
    """Read a load CSV into a :class:`LoadProfile`.

    Timestamps with UTC offsets are parsed per row, so a file whose offsets
    change at a DST transition (e.g. ``-05:00`` to ``-04:00``) is handled.
    Rows must either all carry an offset or all be naive; naive rows need
    ``localize_tz``, ``ambiguous`` and ``nonexistent`` (see
    :meth:`LoadProfile.from_series`).
    """
    df = pd.read_csv(path, dtype={ts_col: str}, keep_default_na=False)
    return LoadProfile.from_frame(
        df,
        ts_col=ts_col,
        value_col=value_col,
        quantity=quantity,
        interval=interval,
        label=label,
        **kwargs,
    )


# ────────────────────────────── helpers ──────────────────────────────────────────
def _validate_interval(interval: str | pd.Timedelta) -> pd.Timedelta:
    try:
        step = pd.Timedelta(interval)
    except (ValueError, TypeError) as exc:
        raise LoadDataError(f"invalid interval {interval!r}: {exc}") from exc
    if step not in SUPPORTED_INTERVALS:
        allowed = ", ".join(f"{int(s / pd.Timedelta(minutes=1))}min" for s in SUPPORTED_INTERVALS)
        raise LoadDataError(f"unsupported interval {interval!r}; supported: {allowed}")
    return step


def _to_datetime_index(col: pd.Series | Sequence) -> pd.DatetimeIndex:
    """Parse a timestamp column without silently assuming UTC for naive text."""
    s = pd.Series(col)
    if isinstance(s.dtype, pd.DatetimeTZDtype) or pd.api.types.is_datetime64_dtype(s.dtype):
        return pd.DatetimeIndex(s)
    text = s.astype(str).str.strip()
    if (text == "").any():
        raise LoadDataError(f"{int((text == '').sum())} empty timestamp(s)")
    has_offset = text.str.contains(_HAS_OFFSET)
    if has_offset.all():
        try:
            return pd.DatetimeIndex(pd.to_datetime(text, utc=True, format="ISO8601"))
        except (ValueError, TypeError) as exc:
            raise LoadDataError(f"invalid timestamp: {exc}") from exc
    if has_offset.any():
        first = text[~has_offset].iloc[0]
        raise LoadDataError(
            f"timestamps mix UTC offsets and naive values (e.g. {first!r}); "
            "give every row an offset or none"
        )
    try:
        return pd.DatetimeIndex(pd.to_datetime(text, format="ISO8601"))
    except (ValueError, TypeError) as exc:
        raise LoadDataError(f"invalid timestamp: {exc}") from exc


def _as_aware_index(
    index: pd.Index,
    localize_tz: str | None,
    ambiguous: Ambiguous | None,
    nonexistent: Nonexistent | None,
) -> pd.DatetimeIndex:
    if not isinstance(index, pd.DatetimeIndex):
        index = _to_datetime_index(index.to_series())
    if index.tz is not None:
        if localize_tz is not None:
            raise LoadDataError("timestamps are already timezone-aware; do not pass localize_tz")
        return index
    if localize_tz is None:
        raise LoadDataError(
            "timestamps are timezone-naive. Pass timezone-aware timestamps, or give "
            "localize_tz plus explicit ambiguous= and nonexistent= policies."
        )
    if ambiguous not in ("raise", "infer") or nonexistent != "raise":
        raise LoadDataError(
            "localizing naive timestamps needs ambiguous='raise'|'infer' and "
            "nonexistent='raise' stated explicitly"
        )
    try:
        return index.tz_localize(localize_tz, ambiguous=ambiguous, nonexistent=nonexistent)
    except Exception as exc:  # pytz/zoneinfo raise several types
        raise LoadDataError(f"cannot localize timestamps to {localize_tz}: {exc}") from exc


def _as_finite_float(raw: np.ndarray, quantity: str) -> np.ndarray:
    if raw.dtype == bool or (raw.dtype == object and any(isinstance(v, bool) for v in raw)):
        raise LoadDataError(f"{quantity} values must be numbers, not booleans")
    try:
        vals = pd.to_numeric(pd.Series(raw), errors="raise").to_numpy(dtype="float64")
    except (ValueError, TypeError) as exc:
        raise LoadDataError(f"{quantity} values must be numeric: {exc}") from exc
    bad = ~np.isfinite(vals)
    if bad.any():
        raise LoadDataError(
            f"{int(bad.sum())} {quantity} value(s) are NaN or infinite (first at position "
            f"{int(np.flatnonzero(bad)[0])}); missing consumption is never imputed"
        )
    neg = vals < 0
    if neg.any():
        raise LoadDataError(
            f"{int(neg.sum())} negative {quantity} value(s) (first at position "
            f"{int(np.flatnonzero(neg)[0])}); this import-only path does not accept "
            "net export. PV is handled separately (WP7)."
        )
    return vals


def _check_alignment(starts: pd.DatetimeIndex, step: pd.Timedelta) -> None:
    # Seconds since local midnight must be a multiple of the interval. New York
    # offsets are whole hours, so this equals alignment in UTC for these steps.
    secs = starts.hour.to_numpy() * 3600 + starts.minute.to_numpy() * 60 + starts.second.to_numpy()
    sub = starts.microsecond.to_numpy() + starts.nanosecond.to_numpy()
    bad = (secs % int(step.total_seconds()) != 0) | (sub != 0)
    if bad.any():
        raise LoadDataError(
            f"{int(bad.sum())} interval(s) not aligned to {step} clock boundaries, "
            f"first starts at {starts[bad][0]}"
        )


def _find_gaps(starts: pd.DatetimeIndex, step: pd.Timedelta) -> tuple[Gap, ...]:
    if len(starts) < 2:
        return ()
    diffs = np.diff(starts.as_unit("ns").asi8)  # elapsed nanoseconds, DST-safe
    step_ns = step.value
    where = np.flatnonzero(diffs != step_ns)
    gaps = []
    for i in where:
        n_missing = int(diffs[i] // step_ns) - 1
        gaps.append(Gap(start=starts[i] + step, end=starts[i + 1], n_intervals=n_missing))
    return tuple(gaps)
