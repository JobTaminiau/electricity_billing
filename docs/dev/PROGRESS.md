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
| F3.5 | Reproduced | Raw max of input kW, no measurement interval. Neither the SC-8 nor SC-9 leaves define the integration interval; it sits in the General Rules (GR 10), not bundled. | 2 strict xfails; WP4 |
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
- **N2. The plan's SC-1 Rate II holiday example does not match the bundled
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
