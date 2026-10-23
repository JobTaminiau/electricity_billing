# Demand determination

Billed demand is determined separately from energy, in `coned_billing/demand.py`
(requirement R5, WP4). The billing engine starts using it in WP5. Until then,
the legacy `RateSchedule.bill` keeps taking the largest input-interval kW,
which is the documented legacy method `input_interval_maximum`.

```python
from datetime import date
import coned_billing as cb

v = cb.default_registry().historical("sc9_rate2_lt", date(2026, 7, 1))
profile = cb.read_load_csv("meter.csv", interval="15min", label="end")
d = cb.billed_demands(profile, v, period_start=date(2026, 7, 1), period_end=date(2026, 8, 1))
d["demand_summer_all_hours"].kw, d["demand_summer_all_hours"].peak_start
```

## Rule and sources

| Provision | Source | Treatment |
|---|---|---|
| "the maximum demand shall be the highest 30-minute integrated demand occurring during the billing period" | GR 10.4, leaf 84 r1 (from 01/01/2024); r0 before: "the highest 30 minute integrated demand" | Implemented: `method: integrated_demand`, `integration_minutes: 30` |
| SC-9 Rate II: "maximum demand for each specified time period"; "the total demand charge will be the sum of the charges for each of the time periods" | leaf 449 | Implemented: each component takes its own maximum in its own window |
| 60-minute demand for SC-1 Rate V and SC-2 Rate III, daily as-used demand for standby service | GR 10.4, leaf 84 r1 | Out of scope (D3) |
| Computed demand of 0.1 kW per 18 kWh for small meters without a demand device | GR 10.4 | Not modeled |
| Accounts with more than one meter (GR 10.8) | GR 10.4 | Not modeled; leaf not obtained |
| Minimum Monthly Charge and Contract Demand | GR 10.10 (leaf 90 r4); SC-8 and SC-9 "Minimum Monthly Charge" (leaves 440 r5 and 454 r5) | Contract Demand implemented as `contract_demand`; the charge itself is excluded (see below) |
| Reactive Power Demand Charge | GR 10.11 | Excluded: needs kVAr data |

## How the determinant is computed

- **Integration.** A demand interval's kW is its energy divided by its
  duration, so it is the mean of the input interval-average kW inside it.
  5- and 15-minute data are integrated to 30 minutes. They are never billed at
  their raw maximum.
- **Convention (assumed).** GR 10.4 does not say whether the 30 minutes are
  fixed clock intervals or a rolling window. The transcribed versions state
  `convention: fixed_clock`, meaning intervals that start on the hour and half
  hour in New York time, and record this as an assumption for the owner to
  confirm. `rolling` (every 30-minute window starting at an input interval) is
  supported for sensitivity runs. Both are the same when the input is already
  30-minute data.
- **Timestamps.** Intervals are taken from `LoadProfile`, which holds interval
  starts in New York time. The reported `peak_start` and `peak_end` bound the
  demand interval of the peak. When the maximum occurs more than once, the
  earliest interval is reported.
- **Windows.** A demand interval belongs to a component's window only if every
  input interval in it does. This is the convention of GR 10.4's standby text
  ("entirely comprised of intervals ending in the same time period"), applied
  here because the general rule is silent. Fixed 30-minute intervals never
  straddle the bundled window boundaries, which all fall on the hour. Holidays
  follow the component's holiday set (see `docs/calendars.md`).
- **Billing period.** Only demand intervals entirely inside
  `[period_start, period_end)` count. Dates mean midnight in New York.
  - Data after the period cannot change its demand.
  - A rate change inside the period does not split the determinant: GR 10.4
    takes one maximum per billing period, and GR 10.5.1 prorates the rates
    (WP5).
  - A period that covers days both inside and outside a component's months,
    for example May 15 to June 15 for a June-September charge, gets the flag
    `period_spans_window_months`. Its determinant is the maximum over the
    in-window days, and `window_days` / `period_days` are reported. The leaves
    do not say how such a bill is split. That is decided in WP5 and is an open
    owner question.

## Resolution and approximation

| Input interval vs. integration | `resolution="exact"` (default) | `resolution="hourly_approximation"` |
|---|---|---|
| finer or equal (5, 15, 30 min for 30-minute demand) | integrated, status `measured` | the same, no flag |
| coarser (60 min for 30-minute demand) | `DemandDeterminationError` naming both resolutions | each hourly average is the demand; status `approximated`, flag `hourly_approximation` |

An hourly average cannot exceed the highest 30-minute demand inside that hour,
so the approximation can understate billed demand. It never invents a
subhourly peak. A reconstructed bill must use `exact`.

## Missing data

Missing input intervals inside the billing period, including a period that the
data do not fully cover, raise `DemandDeterminationError` by default. With
`on_incomplete="skip"`, demand intervals that are not complete are left out,
and the result carries the flag `incomplete_intervals_skipped`. No energy or
demand is imputed.

## Flags and status

`BilledDemand.flags` holds machine-readable flags, listed with their meanings
in `coned_billing.demand.DEMAND_FLAGS`. `status` takes one of three values:

- `measured`: the component's rule was applied to compatible data;
- `approximated`: an explicit approximation was selected;
- `unverified`: the legacy method was used.

## Contract Demand and the Minimum Monthly Charge

SC-8 and SC-9 (leaves 440 r5 and 454 r5) define the Contract Demand as "the
Customer's highest registered demand in the most recent 18 months, or the
highest registered demand on the Customer's account if the account has less
than 18 months of demand history".

`contract_demand(history, as_of=..., account_start=..., include_current_period=...)`
implements this rule:

- **No look-ahead.** It uses only billing periods that end on or before
  `as_of`, so appending later data never changes the result.
- **Current period.** The leaves do not say whether the current billing
  period is one of the 18 months. The caller must state it with
  `include_current_period`; there is no default.
- **Which periods count.** A period counts when it ends after the 18-month
  horizon. With monthly reads, that gives exactly 18 periods.
- **Complete history required.** History that does not reach back to
  `max(account_start, horizon)` without gaps is rejected.
- **Reductions.** Contract Demand reductions (GR 10.10) are not modeled.
- **"Registered demand" for SC-9 Rate II.** The leaves do not say which
  time-period maximum is the registered demand, so the caller supplies the
  monthly values.

The Minimum Monthly Charge (GR 10.10 b: "the product of the Customer's Contract
Demand and 40 percent of the Demand Delivery Charges per kW") applies only when
it exceeds the monthly Pure Base Revenue. Several parts of that comparison are
missing:

- GR 10.10 c continues on leaf 91, which was not obtained;
- the definition of Pure Base Revenue (GR 2) was not obtained;
- the MAC values (GR 26) were not obtained.

The revenue base therefore cannot be verified, and the charge stays an
`excluded_component` in every SC-8 and SC-9 version. It is not computed from a
guessed base.
