# coned-billing

Estimate monthly bills from an hourly load curve using Consolidated Edison tariffs.

## Required contents

The CSV file entered into the model must contain the following columns:

1. "ts" - timezone-aware timestamp (YYYY-MM-DD HH:MM±HH:MM); offsets may change at DST
2. "kW" - interval-average demand (kW)

State the interval duration and whether timestamps mark interval start or end
(`coned-bill load.csv tariff.yml --interval 15min --label end`). Gaps,
duplicates, misaligned or naive timestamps are rejected. The full input
contract is in [docs/load_data.md](docs/load_data.md). Holidays and
time-of-use windows (New York time, cited holiday sets, `end_of_day`) are
described in [docs/calendars.md](docs/calendars.md).

> **Status:** this package is being upgraded to research quality on branch
> `research-quality` (work packages WP0-WP9, log in `docs/dev/PROGRESS.md`).
> Until WP5 lands, results are scenario estimates of modeled components only,
> rest on unverified legacy rates, and must not be cited as complete bills.
> Known defects are listed as strict-xfail tests in `tests/test_known_defects.py`.

## Development

Requires Python 3.11 or newer.

```bash
pip install -e ".[dev]"          # add ",report" for the great_tables summary table
pytest                           # offline; network tests are opt-in with -m network
ruff check . && ruff format --check .
mypy
```
