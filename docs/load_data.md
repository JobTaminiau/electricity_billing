# Load-data contract

`coned_billing` bills a validated `LoadProfile`: a strictly regular grid of
intervals with an explicit duration. This page defines what is accepted and
what each choice means. It is the reference for requirement R1 (WP1).

## Building a profile

```python
import pandas as pd
from coned_billing import LoadProfile, read_load_csv

# From a pandas Series indexed by tz-aware timestamps
profile = LoadProfile.from_series(
    series,              # kW (interval-average) or kWh (interval energy)
    quantity="kW",       # "kW" or "kWh"
    interval="15min",    # "5min", "15min", "30min" or "1h"
    label="start",       # timestamps mark the interval "start" or "end"
)

# From a CSV with columns ts, kW
profile = read_load_csv("load.csv", interval="1h", label="start")
```

All three arguments `quantity`, `interval` and `label` are required. Nothing is
inferred from pandas `.freq` metadata or from the spacing of timestamps.

## Values and units

| `quantity` | Meaning | Energy of an interval |
|---|---|---|
| `"kW"` | average power over the interval | kW × interval hours |
| `"kWh"` | energy delivered during the interval | as given |

`kWh` input is converted to average kW (kWh ÷ interval hours), so both forms of
the same physical load give identical results.

Values must be finite numbers. These are rejected with `LoadDataError`:
NaN, ±infinity, empty CSV cells, text, and booleans. Negative values are
also rejected, because this is the import-only path. Net export and PV come
in WP7.

## Timestamps

- **Timezone.** Timestamps must be timezone-aware, in any timezone.
  Timezone-naive input is rejected unless you pass `localize_tz` together with
  explicit policies: `ambiguous="raise"` or `"infer"` for the repeated
  fall-back hour, and `nonexistent="raise"` for skipped spring-forward times.
  No other policies are offered, because shifting or dropping times would
  invent or lose energy.
- **Tariff time.** Every profile is converted to `America/New_York`. Calendar
  months and time-of-use windows are evaluated in New York civil time,
  whatever the input timezone. The same instants given in UTC and in New York
  time produce identical bills.
- **Labels.** With `label="start"`, the timestamp 2024-01-31 23:00 marks the
  interval [23:00, 24:00) on January 31. With `label="end"`, the timestamp
  2024-02-01 00:00 marks the same interval, which belongs to January.
- **Alignment.** Interval starts must sit on clock multiples of the interval
  in New York time. For example, 15-minute intervals start at :00, :15, :30
  or :45, and hourly intervals start on the hour. Misaligned grids are
  rejected. Because New York's UTC offsets are whole hours, an aligned grid
  never has an interval crossing a calendar-month boundary, or an on-the-hour
  time-of-use boundary.
- **Uniqueness and order.** Each instant may appear once. The same instant
  written with two different offsets counts as a duplicate. Unsorted input is
  rejected unless you pass `sort=True`.

## DST

Spacing is checked in elapsed time (UTC), not wall-clock time.

| Day | Hourly | 30-min | 15-min |
|---|---|---|---|
| Spring forward (e.g. 2024-03-10) | 23 | 46 | 92 |
| Fall back (e.g. 2024-11-03) | 25 | 50 | 100 |

The repeated 01:00 hour on fall-back days stays as two distinct intervals:
01:00 EDT and 01:00 EST.

CSV files written from New York time carry offsets that change at DST, for
example `-05:00` and `-04:00`. `read_load_csv` parses each row's offset, so
such files load correctly. In a CSV, either every row has an offset (or `Z`)
or none does; a file that mixes the two is rejected.

## Missing data

Missing intervals are **rejected by default**. The error reports how many
intervals are missing and where the first gap is.

With `on_gap="allow"`, the profile keeps only the observed intervals, and
each missing run is recorded in `profile.gaps` with its start, end and number
of intervals. Missing energy is never imputed, and an interval next to a gap
is never stretched to cover it. From WP5, a billing period with gaps is
reported as `incomplete_period`.

## Edge cases

- An empty profile is rejected.
- A single interval is valid, because its duration is explicit.
- Leap years need no special handling: February 2024 has 696 hourly
  intervals.

## Legacy entry points

`RateSchedule.bill(df, ...)` still accepts a DataFrame. It now takes
`interval=`, `label=` (default `"start"`) and `on_gap=`. If `interval` is
omitted, it is taken to be the smallest spacing between timestamps, and the
grid then has to validate as regular, so irregular data are rejected rather
than stretched. Both `coned_billing.billing.bill(csv, tariff)` and the
`coned-bill` CLI read their CSV through `read_load_csv` and default to
`--interval 1h --label start`. WP5 replaces these interfaces with an
explicit-mode API.
