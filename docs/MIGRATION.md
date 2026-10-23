# Migration notes

Deliberate behaviour and API changes on the `research-quality` branch, by work
package. The CHANGELOG is written in WP9 from these notes.

## WP0

- **Python 3.11 or newer** is required (`requires-python = ">=3.11"`).
- **`great_tables` is optional.** Install `coned_billing[report]` to use
  `rate_schedule_summary_table()`. Without it the function raises an
  `ImportError` that names the extra. The previous built-in stand-in object
  is gone; `rate_schedule_summary_dataframe()` is unchanged and needs no
  extra. The returned table no longer carries a `_source_df` attribute; call
  `rate_schedule_summary_dataframe()` for the data.
- **`coned_billing.supply_charge` no longer runs on import.** Importing it
  used to download a CSV, print averages and create a temporary file. The
  legacy behaviour now runs only via `python -m coned_billing.supply_charge`,
  and its signed URL expired in October 2025. Do not use it for research
  results; WP8 replaces it.
- **Package metadata** declares the existing restrictive `LICENSE.txt`
  (`LicenseRef-FREE-All-Rights-Reserved`) instead of MIT.
- Billing results are unchanged. `RateSchedule.bill` now gives the same
  output on pandas 2.2 and pandas 3; it used to fail on pandas 3.

## WP1

- **New:** `LoadProfile`, `read_load_csv`, `Gap`, `ConEdBillingError` and
  `LoadDataError` (a `ValueError` subclass) are exported from `coned_billing`.
  The input contract is documented in `docs/load_data.md`.
- **Energy no longer depends on `.freq`.** Before, energy came from the
  index's `.freq`, or else from backward timestamp differences, with the
  first interval assumed to last 1 h. Now it is always kW × the validated
  interval duration. Results change for any input that lacked `.freq`, such
  as data read from CSV: four 15-minute rows at 1 kW now give 1.00 kWh, where
  they used to give 1.75 kWh.
- **Irregular or gappy input is rejected** with `LoadDataError`. It used to
  be billed as stretched intervals. Pass `on_gap="allow"` to bill only the
  observed intervals. Irregular grids are not supported.
- **Months and TOU windows use New York time.** A UTC-indexed load used to be
  billed by UTC months and hours; it is now converted to New York time first.
- **`RateSchedule.bill`** gains keyword-only `interval=`, `label=` (default
  `"start"`, the old implicit convention) and `on_gap=`. With no `interval`,
  it is taken as the smallest timestamp spacing, and fewer than 2 rows then
  raise an error. Timezone-naive DataFrame indexes are rejected.
- **`n_customers`** must be a positive integer (booleans rejected).
- **`billing.bill()` and the `coned-bill` CLI** read the CSV through
  `read_load_csv`, so files that span a DST change now work. New options are
  `interval` and `label` (CLI: `--interval`, `--label`), defaulting to
  hourly, interval-start. Naive CSV timestamps are rejected; they used to be
  parsed as naive and billed in whatever time they happened to be in.
- **Negative kW values** are rejected on this import-only path. They used to
  be billed as negative consumption.
