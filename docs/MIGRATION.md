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
