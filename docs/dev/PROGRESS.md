# Research-quality upgrade: progress log

Branch `research-quality`, created from `master` at the starting commit below.
One entry per work package (WP0-WP9). Each entry records what was done, the
decisions taken, deviations from the plan, and open questions for the owner.

## Starting point

| Item | Value |
|---|---|
| Starting commit | `c8acba4b51e4401a44afca3bfe701c62a6cb7375` ("Add extracted tariff PDF pages and source references in YAMLs") |
| Same as the reviewed commit? | Yes. The review findings (Section 3 of the plan) apply to this checkout. |
| Unpushed local work | None found. No clone of this repository exists under `C:\Users\job_t\code\free` on the owner's laptop; `nyc-solarcity` installs the package from GitHub `master`. To confirm with the owner whether a copy lives elsewhere. |
| Cloud environment | Linux x86_64, CPython 3.13.17, pandas 3.0.5, numpy 2.5.3, PyYAML 6.0.3, pytest 9.1.1, ruff 0.16.9, mypy 2.3.1. No PyPI or coned.com access from the cloud container. |

## WP0: baseline, guardrails, environment repair

### Baseline test results (unmodified starting commit)

| Environment | Result | Cause of failures |
|---|---|---|
| CPython 3.13.17, pandas 3.0.5, numpy 2.5.3 (cloud) | 22 failed, 16 passed | Removed pandas aliases (`"H"`, `"T"`), removed `resample(kind=...)`, removed `Tick.delta`, plus the stale summary test (SC-8 missing from its expected set) |
| CPython 3.13.13, pandas 2.2.3, numpy 2.5.4 (owner's laptop, Windows 11) | 1 failed, 37 passed | Stale summary test (SC-8 missing), as in the review |
| CPython 3.13.13, pandas 3.1.0, numpy 2.5.4 (laptop) | 22 failed, 16 passed | Same causes as the cloud pandas 3.0.5 run |

The pandas 3 count matches the review exactly. `Tick.delta` (used by the
`.freq` fast path in `RateSchedule.bill`) is a pandas 3 removal the review did
not list; it surfaced once the aliases were fixed.

### Findings F3.1-F3.9

Reproduced with `scripts/wp0_verify_findings.py` on pandas 3.0.5 after the
pandas-API repair (the repair touches aliases only, not the logic under test).
Output at the starting logic:

```
F3.1   energy vs .freq: with .freq=1.0000 kWh, without .freq=1.7500 kWh (expected 1.0000)
F3.1   missing day: Jan 2024 at 1 kW with Jan 15 missing -> 744.75 kWh (observed energy is 720, full month 744)
F3.2   tz-aware July 4: holiday-excluding window keeps tz-aware Jul 4? True; tz-naive? False
F3.2   Thanksgiving: November holidays 2025/2026 = 2025-11-06, 2026-11-05 (expected 2025-11-27, 2026-11-26)
F3.2   holiday range: cached range 2020-01-01 .. 2030-01-01; 2031-07-04 holiday? False
F3.2   scalar is_coned_holiday: RAISES AttributeError: 'Timestamp' object has no attribute 'isin'
F3.3   UTC vs NY index: same physical load: NY-indexed total $1,360,517, UTC-indexed total $1,380,518
F3.3   CSV across DST: read_csv dtype across spring-forward = str; bill() raises AttributeError
F3.4   stale values: SC-1 customer 20.0 (leaf 388: 21.00); SC-9 RI LT summer demand [42.8] (leaf 445: 44.05); SC-9 RII customer 500.0 (leaf 449: 510.00)
F3.4   SC-1 summer tier: 600 kWh July delivery energy $111.11; all-at-one-rate 600.0*[16.107, 18.518]; leaf 388 two blocks would give 250*0.16402+350*0.18858 = $106.01
F3.4   stray key: top-level keys [..., 'energy', 0]; load_rate() accepts without complaint
F3.4   effective dates: 2019 load billed on 02/01/2026 SC-8 tariff without error: total $115.43
F3.4   repo hygiene: docs/sources/*.pdf ignored by git? True; sources.md has file:/// path? True
F3.5   demand interval: one 15-min 40 kW spike -> billed demand 40.0 kW (raw max); 30-min integrated = 20.0, 60-min = 10.0
F3.6   completeness: result columns ['energy_cost', 'demand_cost', 'demand_supply_cost', 'kW', 'customer_charge', 'total']; no completeness/exclusion field
F3.7   summed kW: flat 10 kW January -> 'kW' column = 7440
F3.8   misspelled key: 'weekday_only' accepted; weekdays_only=None; Saturday noon in window? True
F3.8   24:00: RAISES ValueError: hour must be in 0..23
F3.9   packaging: requires-python '>=3.9'; license meta {'text': 'MIT'}; LICENSE.txt "All Rights Reserved"; README uses 'kw': True; supply_charge.py imports requests at top level: True; great_tables hard dep: True; CI workflows present: False
```

| ID | Status | Notes | Regression test / resolution |
|---|---|---|---|
| F3.1 | Reproduced | `.freq` path 1.00 kWh vs fallback 1.75 kWh. Missing day: 744.75 kWh billed for 720 kWh observed (gap stretched, and first interval assumed 1 h). | 2 strict xfails; fixed in WP1 |
| F3.2 | Reproduced (all four sub-points) | The review's dollar figures are not re-derived; the mechanisms are. See new finding N2 on the SC-1 Rate II example. | 7 strict xfails incl. a fixture tariff for per-component holiday sets; WP2 |
| F3.3 | Reproduced | Different load from the review, same effect (UTC index shifts months and TOU hours). With pandas 3 the CSV column dtype is `str`, with 2.x `object`; both fail. | 2 strict xfails; WP1 (CSV), WP2/WP5 (local time) |
| F3.4 | Reproduced | Values, missing tiers, stray `0:` key, no date enforcement. The bundled SC-8 PDF starts at leaf 436 (Rate III); the SC-8 YAML cites leaf 432, not bundled. No General Rules bundled. | 4 strict xfails (values, tier, stray key, dates); WP3. `.gitignore` and `sources.md` fixed now |
| F3.5 | Reproduced | Raw max of input kW, no measurement interval. Neither the SC-8 nor SC-9 leaves define the integration interval; it sits in the General Rules (GR 10), not bundled. | 2 strict xfails; fixed in WP4 (tests adapted to `coned_billing.demand`) |
| F3.6 | Reproduced | `total` carries no completeness or exclusion information. | 1 strict xfail; WP5 |
| F3.7 | Reproduced | Flat 10 kW January reports `kW` = 7,440. Delivery, supply and merchant energy are summed into `energy_cost`. | 2 strict xfails; WP5 |
| F3.8 | Reproduced | `weekday_only` silently dropped (window becomes all days); `"24:00"` raises a bare `datetime.time` error. | 2 strict xfails; WP3 (schema), WP2 (end-of-day) |
| F3.9 | Reproduced; most items fixed in WP0 | Python 3.9 claim: confirmed by inspection (`dataclass(slots=True)` needs 3.10; `loader.py` evaluates `str \| None` at definition time without `from __future__ import annotations`). No 3.9 interpreter was run. | Fixed now: requires-python, license metadata, README `kW`, `supply_charge.py` import side effects, `great_tables` optional, CI skeleton. Remaining for WP8/WP9: supply acquisition, final dependency ranges |

### New findings

- **N1. SC-9 Rate II TOU demand windows and holidays (unverified).** Leaf 449
  (Rev. 20, eff. 02/01/2026) defines the windows as "Monday through Friday,
  8 AM to 6 PM / 10 PM" and does not mention holidays. The legacy YAML
  excludes holidays from both windows. Whether ConEd holidays are excluded
  for SC-9 Rate II must come from the General Rules or SC-9 common
  provisions, which are not bundled. WP2 must cite it or mark it unverified.
- **N2. (Retracted in WP2; see the WP2 entry.) The plan's SC-1 Rate II holiday example does not match the bundled
  leaf.** The plan says the SC-1 Rate II summer on-peak period excludes only
  Independence Day and Labor Day. The bundled SC-1 leaf for Rate II
  (02/01/2026) reads "On-peak: All days, 8 AM to midnight, including
  holidays" for both seasons. The example may come from an earlier revision.
  It does not affect the D3 scope (Rate II is unsupported), but the fixture
  test in WP2 should not cite it as current tariff text. The SC-1 Rate IV
  "Common Provisions" do list a six-day holiday set (New Year's, Memorial
  Day, Independence Day, Labor Day, fourth-Thursday Thanksgiving, Christmas).
- **N3. `Tick.delta` removed in pandas 3.** Not in the review's list; fixed
  in WP0 with `pd.Timedelta(idx.freq)` (same values on both pandas lines).
- **N4. Legacy SC-1 non-summer rate differs from the Feb-2026 leaf.** YAML
  16.107 ¢/kWh non-summer and 18.518 ¢ summer; leaf 388 is 16.402 ¢ for all
  non-summer kWh and the first 250 summer kWh, 18.858 ¢ above. Also legacy
  SC-9 Rate I customer charge 71.00 vs leaf 445 72.00, and legacy SC-9 Rate I
  LT/HT energy 1.66/1.54 ¢ vs leaf 445 1.54/1.43 ¢. All are preserved as the
  legacy version in WP3 (D2), not overwritten.
- **N5. Downstream API use.** `nyc-solarcity` (GitHub `master`) calls
  `load_rate(...)` and `RateSchedule.bill(load, n_customers=...)` on
  aggregated hourly loads, renames its `kwh` column to `kW`, and refers to
  the bundled YAML file names. The WP5 deprecation path should keep these
  working (with warnings) until nyc-solarcity migrates.

### What changed

- **pandas 2/3 compatibility.** `resample("M", kind="period")` and
  `to_period("M")` on a tz-aware index replaced by a helper that groups on
  wall-clock months explicitly (identical grouping, no tz-drop warning);
  `idx.freq.delta` replaced by `pd.Timedelta(idx.freq)`; test aliases `"H"`
  and `"30T"` replaced by `"h"` and `"30min"`. Billing logic is otherwise
  unchanged: known defects are pinned by xfails, not fixed early.
- **`requires-python = ">=3.11"`** (D7).
- **Summary test** uses an explicit expected list of all six bundled tariff
  codes, including SC-8.
- **`supply_charge.py` quarantined.** Its module-level download, printing and
  temp-file creation now run only under `python -m coned_billing.supply_charge`;
  `requests` is imported inside that function. The expired URL and
  arithmetic averaging remain, documented in the module docstring, until WP8.
- **`great_tables` is an optional extra (`report`).** The test-only fallback
  shim is removed; `rate_schedule_summary_table()` raises an `ImportError`
  naming the extra when the package is missing.
  `rate_schedule_summary_dataframe()` needs no optional dependency.
- **License metadata (D1).** `license = "LicenseRef-FREE-All-Rights-Reserved"`
  with `license-files = ["LICENSE.txt"]` (PEP 639). No rights granted,
  `LICENSE.txt` unchanged. Added the `Private :: Do Not Upload` classifier so
  an accidental PyPI upload is refused.
- **Tooling.** ruff (lint + format) and mypy configured in `pyproject.toml`;
  the codebase is ruff-formatted and both are clean, with no baseline file
  needed. CI skeleton in `.github/workflows/ci.yml` (test matrix, lint, type
  check, build, wheel smoke test). `xfail_strict = true` globally, and a
  `network` marker deselected by default.
- **`.gitignore`** keeps ignoring PDFs except under `docs/sources/`.
- **`sources.md`** no longer contains the local `file:///C:/Users/...` path.
- **README** uses `kW`, states the package's current status, and lists
  development commands.

### Tests added or changed

- `tests/test_known_defects.py`: 23 strict xfails (F3.1 ×2, F3.2 ×7, F3.3 ×2,
  F3.4 ×4, F3.5 ×2, F3.6 ×1, F3.7 ×2, F3.8 ×2). Each asserts the correct
  behaviour with independent expected values (durations, hand arithmetic,
  calendar dates, leaf values). Each was run with `--runxfail` to confirm it
  fails for the documented reason, not an incidental error.
- `tests/test_import_safety.py`: imports the package and every submodule in a
  fresh interpreter with sockets and DNS blocked, an empty working directory
  and an empty TMPDIR; asserts no output and no files. It fails on the
  starting commit's `supply_charge.py` and passes now.
- `tests/test_summary.py`: explicit expected codes; the `great_tables` test is
  skipped when the extra is absent; a new test checks the helpful
  `ImportError`.
- Existing tests: only frequency aliases changed.

### Results (cloud, CPython 3.13.17, pandas 3.0.5, numpy 2.5.3)

- `pytest`: 39 passed, 1 skipped (great_tables not installed), 23 xfailed;
  also clean with `-W error`.
- `ruff check .` and `ruff format --check .`: clean.
- `mypy`: no issues in 8 source files (pandas and PyYAML treated as untyped
  until stubs are pinned in WP9).
- Build: sdist and wheel built with setuptools 84 (offline, no isolation).
  The wheel installed into a clean virtual environment outside the checkout
  imports, ships the six tariff YAMLs and `LICENSE.txt`, and `coned-bill
  --help` runs.

### Matrix run (owner's laptop, Windows 11 Pro 10.0.26200, uv 0.11.7, commit 048544d)

| Python | pandas | numpy | Result |
|---|---|---|---|
| 3.11.15 | 2.2.3 | 2.4.6 | 40 passed, 23 xfailed |
| 3.11.15 | 3.1.0 | 2.4.6 | 40 passed, 23 xfailed |
| 3.12.13 | 2.2.3 | 2.5.4 | 40 passed, 23 xfailed |
| 3.12.13 | 3.1.0 | 2.5.4 | 40 passed, 23 xfailed |
| 3.13.13 | 2.2.3 | 2.5.4 | 40 passed, 23 xfailed |
| 3.13.13 | 3.1.0 | 2.5.4 | 40 passed, 23 xfailed |
| 3.14.4 | 3.1.0 | 2.5.4 | 40 passed, 23 xfailed |
| 3.14 | 2.2 | | excluded (no wheels) |

No failures, no XPASS; `great_tables` was installed, so its test ran. On the
laptop with Python 3.13: ruff, ruff format and mypy clean; `python -m build`
(isolated) made the sdist and wheel; the wheel installed in a fresh venv
outside the repo imports and `coned-bill --help` exits 0.

Warnings seen there:

- pandas 3.1 deprecates `DatetimeIndex.weekday` (Pandas4Warning). Fixed after
  the matrix run by using `day_of_week` (available in pandas 2.2 too).
- numpy 2.5.4 warns about a "generic" timedelta unit in
  `tests/test_calendars.py` and `tests/test_models.py`, in the tests that
  derive expected holidays from the lookup itself. Not reproducible with
  numpy 2.5.3 in the cloud. Those circular tests are replaced in WP2 (F3.2).

### Decisions taken

- **D8 (schema library):** deferred to WP3, where it is used. Leaning to
  pydantic v2 (already present in the cloud image; `extra="forbid"` gives the
  unknown-key behaviour F3.8 needs with little code).
- **Type checker:** mypy (already used by nyc-solarcity) rather than pyright.
  No `python_version` pin, because numpy ≥ 2.5 stubs use 3.12 syntax; CI runs
  mypy on 3.13.
- **pandas 2.2 × Python 3.14** is excluded from the CI matrix because pandas
  2.2.x has no 3.14 wheels.
- **Lower bounds** `pandas>=2.2`, `numpy>=1.26`, `pyyaml>=6.0`: provisional
  until WP9.

### Deviations

- D1 suggested a `LicenseRef-` identifier *together with* a proprietary
  classifier. PEP 639 (setuptools ≥ 77) rejects `License ::` classifiers
  alongside a license expression, so only the `LicenseRef-` identifier is
  used. The build backend requirement rose from setuptools ≥ 68 to ≥ 77.
- Defects F3.4 (repo hygiene) and F3.9 were fixed directly in WP0 as the plan
  lists them as WP0 tasks; they have ordinary tests, not xfails.

### Open questions for the owner

See the WP0 checkpoint report in the project thread.

### After the WP0 checkpoint (owner decisions, 2026-10-23)

- Push of `research-quality` authorized (no PR, no merge). First GitHub CI run
  (`eb82225`) passed on every job: https://github.com/JobTaminiau/electricity_billing/actions/runs/40009153241
- Downloading primary sources through the owner's laptop authorized, and
  **earlier years are in scope** ("Include rates for earlier years"):
  historical tariff versions and supply prices for 2020-2025 join the plan
  (WP3, WP8). Collected on the laptop under
  `electricity_billing-wp0\sources\` with sha256 manifests:
  - current PSC No. 10 full tariff (760 pp, leaves 1-503) and addenda.
    coned.com offers no separate General Rules or SC files. Key leaves: GR 2
    definitions 12-20, GR 10 demand from 82 (10.10/10.11 around 90-94),
    GR 25 MSC 328-336, GR 26 337-359, SC-8 Rate I 432-435;
  - 459 superseded leaves in force during 2020-2025, from the NY PSC
    Electronic Tariff System, with case and effective/cancelled dates;
  - Con Ed tariff snapshots (2019-2026);
  - the MSC calculator data file (2010-2026), the only primary MSC energy
    series (no monthly MSC energy statements are published);
  - Statements of MSC Capacity and MFC (2020-2025) and MSC adjustment
    summaries.
- Sources policy agreed: the repository keeps the manifests plus only the
  leaves each tariff version cites; the full set is kept outside git.

## WP1: load-data contract and interval energy

### What was done

- `coned_billing/load.py`: `LoadProfile` (validated regular grid: New York
  interval starts, explicit `interval`, read-only `kw`, recorded `gaps`),
  `LoadProfile.from_series` / `from_frame`, and `read_load_csv`.
- `coned_billing/errors.py`: `ConEdBillingError` and
  `LoadDataError(ConEdBillingError, ValueError)`.
- `RateSchedule.bill` builds a `LoadProfile` (or accepts one), bills in
  New York time, and validates `n_customers`. `billing.bill()` and the CLI
  read the CSV through `read_load_csv` and take `interval` and `label`.
- `docs/load_data.md` documents the contract; `docs/MIGRATION.md` lists the
  behaviour changes.

### Decisions

- **Supported intervals:** 5, 15, 30 and 60 minutes. These are the strict
  regular-grid research path. 5 minutes is included for WP4's
  integrated-demand tests. Irregular intervals are not supported.
- **Label convention:** no default in the new API. The legacy
  `RateSchedule.bill` / `bill()` / CLI keep `label="start"`, the pre-WP1
  implicit convention.
- **Gap policy:** reject by default. `on_gap="allow"` records gaps and bills
  only observed intervals; nothing is imputed or stretched.
- **Unsorted input:** reject by default; `sort=True` opts in.
- **Naive timestamps:** reject by default. Localizing needs `localize_tz` plus
  `ambiguous="raise"|"infer"` and `nonexistent="raise"`. No shifting policy is
  offered, because it would invent or drop energy.
- **CSV parsing:** a row-level check that the time of day is followed by an
  offset, so a bare date is not mistaken for one. Rows with offsets are
  parsed with `utc=True`; a file mixing offset and naive rows is rejected.
- **Empty input:** rejected. A single interval is valid.
- **Negative values:** rejected on this import-only path (PV is WP7).
- **Legacy `interval` inference:** when the old DataFrame API is called
  without `interval`, the smallest timestamp spacing is used and must then
  validate as a regular grid. This keeps nyc-solarcity's call working.
  WP5 deprecates the old API.
- **R1.8 (New York calendars) is done here.** It is in R1, which is why the
  F3.3 "UTC vs New York" xfail is removed in WP1 rather than WP2. Holiday
  matching (F3.2) remains xfailed for WP2.
- **pandas 3 datetime resolution:** pandas 3 can store datetimes in µs, so all
  elapsed-time arithmetic goes through `.as_unit("ns")`. The first draft
  misread µs as ns; the tests caught it.

### Tests

`tests/test_load.py` has 38 test functions (97 cases with parametrization).
They cover:

- energy independent of `.freq`, and known totals at 5/15/30/60 minutes;
- kW and kWh equivalence, start/end labels including month assignment, and
  gaps (rejected, or recorded and never stretched);
- duplicate instants, including one instant written with two different
  offsets, and the unsorted policy;
- empty and single-interval input, and NaN, ±inf, text, booleans and
  negative values;
- invalid intervals and options, and misaligned grids;
- naive input and localization policies, including nonexistent and
  ambiguous times;
- DST-day counts (23/25, 46/50, 92/100), distinct repeated hours, and
  UTC/New York equivalence;
- leap February, and CSV input: mixed offsets, round trip, `Z`, naive,
  mixed, blank, missing value and missing column;
- `n_customers` validation and read-only values;
- that aligned grids never cross a month boundary;
- a seeded random property test (25 grids), plus a Hypothesis property test
  that is skipped where Hypothesis is not installed.

Changed: `tests/test_models.py::test_bill_handles_irregular_intervals` now
asserts rejection (`test_bill_rejects_irregular_intervals`), a deliberate
behaviour change. Four xfails are resolved and their markers removed: F3.1 ×2,
F3.3 CSV, and F3.3 UTC/New York.

Not yet in WP1: "a CSV round trip preserves billing results" is tested on the
legacy engine only. It is re-checked on the new engine in WP5.

### Results (cloud, CPython 3.13.17, pandas 3.0.5, numpy 2.5.3)

`pytest -W error`: 135 passed, 2 skipped (Hypothesis, great_tables not
installed), 19 xfailed. ruff and mypy are clean. Laptop matrix: see the WP1
checkpoint.

### Open questions

- nyc-solarcity's hourly loads now fail loudly if they contain gaps or
  duplicate hours. The 2024 ConEd forecast shape has a missing 2024-12-31,
  which used to be silently stretched. Owner to decide whether nyc-solarcity
  should pass `on_gap="allow"` or fix its inputs. Nothing has been changed
  in nyc-solarcity.

## WP2: holidays and time windows

### What was done

- `coned_billing/calendars.py` rewritten: rule-based holidays for 1900–2200
  (`Holiday`, `holiday_date`), named and cited `HolidaySet`s in
  `HOLIDAY_SETS`, `get_holiday_set`, and scalar/vector `is_coned_holiday`
  in New York civil time. No observed-day shift.
- `TimeWindow` gains `excluded_holidays` and full validation; `mask` works
  in New York time and rejects naive input. Windows are half-open; `end`
  `None` means end of day.
- YAML loader: `end_of_day` token, `"24:00"` rejected with a pointer to it,
  strict `HH:MM`, and the `excluded_holidays` key. The strict schema is WP3.
- Docs: `docs/calendars.md`; `docs/MIGRATION.md` WP2 section.

### Sources

All from the full PSC No. 10 PDF (`electric-tariff.pdf`, 760 pp., sha256
`4141be1f16d8e49d5be19b77aa508645753890bb61ffd9019ad27a6459cb851f`,
retrieved 2026-10-23 19:10Z from coned.com):

- leaf 389.3 rev 1 (eff. 04/06/2020), PDF p. 622: SC 1 Rate IV common
  provisions, six-day holiday list; same list in Rider leaf 327.2 rev 2
  (eff. 11/03/2022), PDF p. 486;
- leaf 389 rev 23 (eff. 02/01/2026), PDF p. 618: SC 1 Rate II on-peak
  Mon–Fri 10 AM–10 PM, summer excluding Independence Day and Labor Day,
  non-summer excluding New Year's, Memorial Day, Thanksgiving, Christmas;
- leaf 449 rev 20 (eff. 02/01/2026), PDF p. 688: SC-9 Rate II windows,
  "Monday through Friday", no holiday wording;
- leaf 90 rev 4 (eff. 02/01/2020), PDF p. 104: General Rule 10.10, off-peak
  is the 48 h of Saturday and Sunday plus 10 PM–8 AM Monday–Friday.

### Findings

- **N2 retracted.** My WP0 reading was wrong: I read the SC-1 Rate III text.
  Leaf 389 Rate II matches the spec's example (summer on-peak excludes only
  Independence Day and Labor Day). The two Rate II sets are bundled with
  that citation.
- **N1 resolved by the leaf text.** SC-9 Rate II windows have no holiday
  exclusion (leaf 449, GR 10.10). The legacy YAML still excludes the six
  holidays; it stays as an unverified legacy value, and since holidays are
  now matched correctly, tz-aware SC-9 Rate II bills now drop holidays from
  on-peak demand where they did not before. The WP3 transcription will use
  set `none`. Owner decision requested at the checkpoint.
- **For WP4:** General Rule 10.4 (leaf 84 rev 1, eff. 01/01/2024, PDF p. 98)
  says "the maximum demand shall be the highest 30-minute integrated demand"
  for customers not otherwise specified. The legacy engine takes the highest
  interval kW at the input resolution.
- **For WP3:** the current tariff PDF already carries leaves effective after
  February 2026 (e.g. SC-9 leaf 452 at 08/01/2026 and 10/01/2026), so
  versioning must be per leaf, not per document.

### Tests

`tests/test_calendars.py` rewritten with hard-coded dates: Thanksgiving,
Memorial Day and Labor Day across years; no observed shift; years outside
2020–2030 and out of range; scalar and vector return types; tz conversion to
the New York civil date; the SC-1 Rate II sets and citations; component
windows; custom lists and the YAML key; half-open 08:00/22:00;
`end_of_day` vs `"24:00"`; invalid times and windows; naive masks;
weekday/weekend/holiday interactions; UTC/New York/Tokyo equivalence; DST
boundaries and 14-hour windows on DST days; no aligned 5/15/30/60-minute
interval crossing a bundled window boundary; and a holiday peak excluded
from demand.

Strict xfails removed: the six F3.2 tests (tz-aware July 4, UTC July 4,
Thanksgiving, cache range, scalar lookup, per-component sets) and the F3.8
"24:00" test. 10 xfails remain (F3.4 ×4, F3.5 ×2, F3.6, F3.7 ×2, F3.8
misspelled key).

Changed: `tests/test_billing.py::test_demand_charge_uses_monthly_peak` and
the `tests/test_models.py` half-open test moved off New Year's Day, which
default windows now correctly exclude; the `tests/test_models.py` holiday
test now uses tz-aware July 3/4; `tests/test_loader.py` expects `months` as a
tuple.

### Results (cloud, CPython 3.13.17, pandas 3.0.5, numpy 2.5.3)

`pytest -W error`: 206 passed, 2 skipped (Hypothesis, great_tables not
installed), 10 xfailed. ruff, ruff format and mypy are clean.

## WP3: tariff schema, versioning and source transcription

### What was done

- **Schema v1** (`coned_billing/tariff_schema.py`, documented in
  `docs/tariff_schema.md`) covers:
  - dated versions with the spec 6.1 metadata;
  - components with categories, units in the tariff's own terms,
    determinants, windows that must name their holiday set, blocks with a
    cited proration rule, exclusive groups, demand measurement and
    citations;
  - excluded components.
- **Strict loader and registry.**
  - Unknown keys, types, non-finite values, units, dates, months, windows,
    duplicate ids, source ids, block structure, signs by category, and gaps
    or overlaps in exclusive groups are all rejected, naming the field.
  - The registry rejects undeclared overlapping versions, and
    `owner_verified` status without an entry in `verification_record.yml`.
  - `historical()` and `historical_segments()` select by service date and
    raise on uncovered or ambiguous dates; `scenario()` needs an explicit
    version.
- **The legacy loader is strict too.** `load_rate` names unknown keys
  (F3.8), so the misspelled `weekday_only` now fails.
- **Migration.** `scripts/migrate_legacy_tariffs.py` turns the six legacy
  files into `legacy` versions: values unchanged, `unverified`, scenario
  mode only, header comments kept in `legacy_notes`. The stray `0:` notes in
  `sc_1_res_rate_1.yml` moved, verbatim, under `notes:`.
- **Sources.**
  - 60 cited leaves are in `docs/sources/psc10/` (6.8 MB): 20 pages
    extracted from the current full PDF and 40 superseded leaves from the
    NY PSC ETS.
  - Each is registered in `tariffs/v1/sources.yml` with its sha256, URL and
    retrieval time, and extracted pages also record the parent PDF's sha256
    and page. `scripts/build_source_leaves.py` rebuilds them.
  - `.gitignore` already admitted `docs/sources/**/*.pdf`.
- **Transcription.** 51 versions are `transcribed`:

  | Tariff | Coverage | Versions |
  |---|---|---|
  | SC-1 Rate I | 2019-01-01 onward | 10 |
  | SC-2 Rate I | 2019-01-01 onward | 10 |
  | SC-8 Rate I LT | 2020-02-01 onward | 8 |
  | SC-9 Rate I LT | 2020-02-01 onward | 8 |
  | SC-9 Rate I HT | 2020-02-01 onward | 8 |
  | SC-9 Rate II LT | 2020-02-01 onward | 7 |

  - Every value cites its leaf and revision, with a quote. GR 10.5 (leaf 85)
    is cited for proration and GR 10.4 (leaf 84 r0 or r1) for the 30-minute
    demand.
  - `scripts/check_transcription_text.py`: all 587 text-layer quotes occur in
    their PDFs, and every value occurs in its own quote.
  - 33 quotes on five image-only leaves were read from the rendered page and
    are flagged `page_image` for the owner's review.
- **Generated docs.**
  - `docs/support_matrix.md` and `docs/dev/transcription_review.md`, with a
    test that both are current.
  - `tests/snapshots/tariff_values.json` and its update script.

### Decisions

- **D8: dataclasses with explicit validation, not pydantic.**
  - No new core dependency: the package still installs offline with pandas,
    numpy and PyYAML.
  - Error messages name the exact YAML path (`file.yml.components[id].window`).
  - Cross-field rules (units by category and determinant, signs, block
    contiguity, exclusive-group coverage, overlaps across files) are explicit
    code either way.
- **Versions are named after their first service date.** Where two leaf
  revisions claim the same date, the revision is appended
  (`2024-01-01-r18`).
- **Holidays.** Every window must state its holiday set. All transcribed
  windows use `none`:
  - SC-1, SC-2 and SC-8/SC-9 Rate I windows are month-only;
  - SC-9 Rate II follows leaf 449 (owner, 2026-10-23).
- **Delivery only.** Supply (GR 25), the GR 26 adjustments, the GR 30
  increase, reactive power (GR 10.11) and the minimum monthly charge (GR
  10.10) are `excluded_components` with reasons, so WP5 can mark results
  `modeled_subtotal`.
- **Units follow each leaf:** cents/kWh up to 2025, $/kWh from 02/01/2026.

### Findings

- **N5. Two SC-1 and SC-2 revisions claim 01/01/2024.**
  - Leaf 388 rev 18 (Case 22-E-0064: $19.00, 15.112/17.373 ¢) and rev 19
    (Case 15-E-0751: $18.00, 14.116/16.228 ¢) both state 01/01/2024, and
    both were cancelled 02/04/2024. Leaf 397 rev 18/19 for SC-2 is the same
    case.
  - Rev 19 repeats the rev 17 (08/01/2023) rates. Rev 20 (02/04/2024)
    returns to the rev 18 rates.
  - Both are transcribed as `known_overlaps`, so historical mode rejects
    2024-01-01..2024-02-03. Owner to decide which was billed.
- **N6. SC-8 and SC-9 Rate I changed structure on 01/01/2024.**
  - Before that, demand was billed in blocks: "first 10 kW (or less)" for
    SC-8 and "first 5 kW (or less)" for SC-9, at a flat $/month, then $/kW
    above it, with the minimum charge equal to the first block. There was no
    customer charge.
  - From 01/01/2024 there is a customer charge and a flat $/kW demand
    charge. The schema models the old structure as a flat first block.
- **N7. Transition bills.** SC-8 leaf 432 r18 and SC-9 leaf 445 r19
  (03/16/2024) set special demand charges for bills spanning December 2023
  and January 2024. These are listed as excluded; WP5 must reject billing
  periods that start before 2024-01-01 under these versions.
- **N8. GR 10.5.2 proration.**
  - kWh blocks scale by elapsed days / 30. The old F3.4 test expected an
    unprorated 31-day July; it now checks both cases.
  - Open reading for the owner: is the "per month" customer charge prorated
    by days / 30 (recorded as an assumption), or is it a "per bill"
    charge, which is not prorated?
- **N9. 2019 rate leaves for SC-8, SC-9 Rate I and SC-9 Rate II** carry
  meter ownership, meter service and meter data charges with MSP
  conditions. They are not transcribed, so coverage for these tariffs starts
  2020-02-01.
- **N10. Legacy values identified.**
  - SC-1, SC-2, SC-9 Rate I LT/HT and SC-9 Rate II are the 01/01/2025
    leaves; SC-8 is the 02/01/2026 leaf.
  - The legacy SC-1 file bills every summer kWh at 18.518 ¢, the over-250
    rate (F3.4 confirmed).

### Not obtained or not transcribed (exact list)

- GR 26 statements (MAC, surcharges and adjustment factors), the GR 30
  percentage statement, and GR 25 MSC/MFC values (WP8).
- Reactive power demand rates (GR 10.11) and the minimum monthly charge
  calculation (GR 10.10, contract demand).
- Rate-leaf versions of SC-8 and SC-9 for 2019-01-01..2020-01-31 (N9).
- Superseded revisions of the applicability and common-provision leaves
  (387, 390, 396, 399, 431, 440, 444, 447, 454). Historical versions cite
  only their rate leaf for eligibility.
- SC-8 high tension (outside D3).

### Tests

- `tests/test_tariff_schema.py` (115 cases) covers every WP3 schema test on
  the list:
  - valid loads;
  - missing fields;
  - unknown keys named;
  - units, non-finite values, dates and months;
  - duplicates;
  - sign rules and documented credits;
  - overlaps declared or not;
  - uncovered dates;
  - additive SC-9 Rate II overlap;
  - gaps and overlaps in exclusive energy groups;
  - malformed blocks;
  - legacy migration exactness and the stray key;
  - the owner-status gate;
  - block arithmetic by hand, including GR 10.5.2 proration and the flat
    first demand block.
- `tests/test_tariff_sources.py` (19 cases) covers citations on every
  transcribed value, sha256 of every registered source, no unregistered
  files, the value snapshot, current generated docs, and hand-typed values
  from the Feb-2026 leaves plus spot checks of superseded revisions,
  including two image-only leaves.
- Strict xfails removed: F3.4 ×4, adapted to the versioned API, and the
  F3.8 misspelled key. 5 xfails remain: F3.5 ×2, F3.6 and F3.7 ×2. The F3.5
  `pytest.raises` match was narrowed so that the new unknown-key error does
  not count as the WP4 fix.

### Results (cloud, CPython 3.13.17, pandas 3.0.5, numpy 2.5.3)

`pytest -W error`: 345 passed, 2 skipped, 5 xfailed. ruff, ruff format and
mypy are clean. A wheel built locally contains `tariffs/v1/` and loads all 57
versions outside the checkout.

## WP4: demand determination

### What was done

- **Demand module** `coned_billing/demand.py`, documented in `docs/demand.md`:
  - `billed_demand` and `billed_demands` compute the highest 30-minute
    integrated demand per component window and billing period (GR 10.4,
    leaf 84 r0/r1). Each result records the peak interval, the method and
    convention, the input resolution, the number of demand intervals, the
    days of the period inside the window's months, a status and flags.
  - Each additive SC-9 Rate II component takes its own maximum.
  - A demand interval counts only if it lies wholly inside both the window
    and the billing period.
  - Strict resolution (`exact`) rejects input coarser than the integration
    interval. `resolution="hourly_approximation"` accepts hourly data, uses
    the hourly averages, and flags the result as `approximated`.
  - Missing input raises; `on_incomplete="skip"` leaves incomplete demand
    intervals out, with a flag.
  - Legacy versions (`input_interval_maximum`) keep the raw maximum, with
    status `unverified`.
- **Contract Demand.** `contract_demand` implements the rule of leaves
  440 r5 (SC-8) and 454 r5 (SC-9): the highest registered demand in the most
  recent 18 months, or since the account start. It has no look-ahead, and
  `include_current_period` must be stated explicitly.
- **Schema.** `demand_measurement.convention` (`fixed_clock` or `rolling`) is
  required for integrated demand, and `integration_minutes` must be a divisor
  of 60. All 31 transcribed SC-8 and SC-9 versions state `fixed_clock`, with
  an assumption line.
- **Minimum Monthly Charge.** It stays excluded in every SC-8 and SC-9
  version. Its reason now says why: GR 10.10 c continues on leaf 91, and the
  definition of Pure Base Revenue (GR 2) and the MAC values (GR 26) were not
  obtained, so the revenue base cannot be verified.

### Assessment of minimum, contract and history provisions (task 6)

| Provision | Tariffs | Verified source | Decision |
|---|---|---|---|
| Maximum demand, 30-minute integrated | SC-8 RI, SC-9 RI, SC-9 RII | GR 10.4 (leaf 84) | Implemented |
| Contract Demand from 18 months of history | SC-8 RI, SC-9 RI/RII | leaves 440 r5, 454 r5 (current revisions only) | Implemented as a helper; not yet used by any charge |
| Minimum Monthly Charge = Contract Demand × 40% of demand delivery charges, if above Pure Base Revenue | SC-8, SC-9 | GR 10.10 a, b (leaf 90 r4); the comparison (c) continues on leaf 91, not obtained | Excluded |
| Contract Demand reduction on request | SC-8, SC-9 | GR 10.10 (not obtained) | Not modeled |
| Pre-2024 Rate I "minimum charge" (first 10 kW or 5 kW) | SC-8 RI, SC-9 RI | rate leaves 432 and 445 | Already modeled as the flat first demand block (WP3) |
| Rate II eligibility history (over 1,500 kW / 900 kW in 12 months) | SC-9 | leaf 447 r1 | Eligibility only, not a charge; not modeled |
| Computed demand for small meters (0.1 kW per 18 kWh) | all | GR 10.4 | Not modeled |
| Multi-meter accounts (GR 10.8) | all | not obtained | Not modeled |
| SC-1 and SC-2 Rate I | none: no demand charge | — | n/a |

### Decisions

- **Fixed clock-aligned 30-minute intervals** are assumed, because GR 10.4
  does not say whether the interval is fixed or rolling. The assumption is
  recorded in every affected version and can be changed per version.
  `rolling` is available for sensitivity runs.
- **Window membership:** a demand interval counts only if every input interval
  in it is in the window. This follows GR 10.4's standby wording ("entirely
  comprised of intervals ending in the same time period"); the general rule is
  silent.
- **Ties:** the earliest peak interval is reported.
- **Billing periods across rate changes:** one determinant per billing period
  (GR 10.4). Rates are prorated by GR 10.5.1 in WP5.
- **Periods across season months:** the determinant is the maximum over the
  in-window days, and the period is flagged. How such a bill is split is left
  to WP5 and the owner.

### Findings

- **N11.** GR 10.4 r1 (01/01/2024) adds 60-minute demand for SC-1 Rate V and
  SC-2 Rate III, and daily as-used demand for standby service. Both are
  outside D3. For all other customers the 30-minute rule is unchanged from
  r0.
- **N12.** GR 10.5.2 says "Rates and charges assessed per kW will be prorated
  for 30 days", while kW blocks are "totaled and then prorated on the basis of
  the number of elapsed days divided by 30". The tariff files read the first
  sentence the same way, as days / 30 (`proration: days_over_30`). It could
  also mean that flat kW charges are billed as for 30 days, i.e. not scaled.
  This matters for WP5; owner to confirm.
- **N13.** The leaves do not say whether the current billing period is one of
  the 18 months of Contract Demand history. Nor do they say which SC-9 Rate II
  time-period maximum is the "registered demand".

### Tests

- `tests/test_demand.py` has 32 cases, all with hand-computed values:
  - constant load;
  - an isolated 15-minute spike in 15-, 30- and 60-minute determinants,
    under fixed and rolling conventions;
  - 5-minute integration;
  - fixed versus rolling intervals, and alignment across a DST day;
  - a peak outside a window, and intervals that straddle a window edge;
  - SC-9 Rate II additive maxima, with the charge checked against leaf 449
    rates typed by hand;
  - holiday sets, including SC-9 Rate II counting a July 4 peak;
  - strict rejection of hourly input, and the flagged approximation;
  - the legacy method;
  - missing data, raised and skipped, and a period not covered by the data;
  - billing-period edges and no look-ahead;
  - periods spanning season months and rate changes;
  - argument checks;
  - Contract Demand: the 18-month horizon with and without the current
    period, no look-ahead when future data is appended, a young account,
    gaps, and the required explicit choice.
- `tests/test_tariff_schema.py` has 7 new cases for `convention` and
  `integration_minutes`.
- The F3.5 strict xfails (×2) were adapted to `coned_billing.demand`, and
  their markers removed. 3 xfails remain: F3.6, and F3.7 ×2 (WP5).

### Results (cloud, CPython 3.13.17, pandas 3.0.5, numpy 2.5.3)

`pytest -W error`: 386 passed, 2 skipped, 3 xfailed. ruff, ruff format and
mypy are clean. `scripts/check_transcription_text.py`: 587 text-layer quotes,
0 problems.
