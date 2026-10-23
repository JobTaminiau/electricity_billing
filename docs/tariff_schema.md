# Tariff schema v1

Tariff data is stored as dated, source-cited *versions*, validated strictly on
load. The code is in `coned_billing/tariff_schema.py`. The billing engine
starts using these versions in WP5. Until then, `RateSchedule.bill` and
`load_rate` keep working on the legacy files.

```python
from datetime import date
import coned_billing as cb

reg = cb.default_registry()
v = reg.historical("sc1_rate1", date(2023, 7, 15))  # the version in effect that day
v = reg.scenario("sc9_rate1_lt", "2026-02-01")        # an explicitly chosen version
v.component("energy_delivery").rate, v.verification_status
```

## Files

```
coned_billing/tariffs/v1/
  sources.yml                      register of cited source documents (generated)
  verification_record.yml          owner approvals; only the owner edits it
  <tariff_id>/<version>.yml        one file per version
docs/sources/psc10/...             the cited leaves, checked by sha256
```

`tariff_id` names a supported tariff (D3): `sc1_rate1`, `sc2_rate1`,
`sc8_rate1_lt`, `sc9_rate1_lt`, `sc9_rate1_ht` and `sc9_rate2_lt`. Any other
rate or option is rejected with a message.

A version is named after its first day of service, for example
`2026-02-01`. When two revisions claim the same day, the leaf revision is
appended, as in `2024-01-01-r18`. The legacy values are kept as version
`legacy`.

## Version metadata (spec 6.1)

| Field | Meaning |
|---|---|
| `schema_version` | `1` |
| `tariff_id`, `version` | Stable identifiers. The file must be `<tariff_id>/<version>.yml`. |
| `utility`, `jurisdiction`, `tariff_book` | Con Edison, NY PSC, PSC No. 10 |
| `service_classification`, `rate_option` | For example `SC-9`, `Rate II - General - Large - Time-of-Day` |
| `voltage`, `zone` | `low_tension` / `high_tension` / `null`. `zone` is `null` because these rates are not zone-specific. |
| `timezone` | Must be `America/New_York` |
| `effective.start`, `effective.end` | Dates of service. Start is inclusive and end is exclusive; `end: null` means until superseded. GR 10.5.1 applies rates to service rendered on and after their effective date. |
| `valid_as_of` | For an open-ended version, the last date its sources were checked. Historical dates after it are rejected. |
| `known_overlaps` | Other versions that claim the same dates in the sources (see below) |
| `verification_status` | `unverified`, `transcribed`, `owner_verified` or `bill_reconciled` (spec 5.1) |
| `calculation_modes` | `historical` and/or `scenario`. An unverified version is scenario-only. |
| `case`, `sources` | PSC case. `sources` lists the document ids from `sources.yml`. |
| `eligibility`, `required_account_inputs` | Who the rate applies to, and what the caller must state, such as the service voltage |
| `assumptions`, `notes`, `legacy_notes` | Explicit assumptions, and preserved legacy comments |
| `components`, `excluded_components` | See below |

## Components (spec 6.2)

| Field | Meaning |
|---|---|
| `id`, `name` | Stable id (`[a-z][a-z0-9_]*`) and a descriptive name |
| `category` | `fixed_charge`, `minimum_charge`, `delivery_energy`, `supply_energy`, `merchant_charge`, `delivery_demand`, `supply_demand`, `adjustment` or `credit` |
| `determinant` | `billing_period`, `kwh` (in the window) or `max_demand_kw` (in the window) |
| `unit` + `rate` | Written in the tariff's own units: `USD/month`, `USD/kWh`, `cents/kWh` or `USD/kW` |
| `blocks` | Alternative to `rate`. A list of `{up_to, rate, unit}`; the last block has `up_to: null`. |
| `block_proration` | Required with `blocks`. `bounds_days_over_30` scales the block bounds by days/30 (kWh blocks). `total_days_over_30` scales the block total by days/30 (kW blocks). `reject_partial_periods` applies when no rule was found. All cite GR 10.5.2. |
| `proration` | `days_over_30` or `none`, with its citation |
| `window` | `months`, `weekdays_only`, `start`, `end` and a **required** `excluded_holidays` (see `docs/calendars.md`) |
| `exclusive_group` | Components in a group must cover every hour exactly once. Energy components must belong to one. |
| `demand_measurement` | Required for demand: `{method: integrated_demand, integration_minutes: 30}` (GR 10.4), or `input_interval_maximum` for legacy data |
| `source` | `{document, leaf, revision, page, text, method}`. `text` quotes the leaf; `method` is `text_layer` or `page_image`. Required unless the version is `unverified`. |

A `USD/month` block is a flat charge for that block, and it is allowed only as
the first block. It reproduces wording such as "first 5 kW (or less) $249.01
per month", whose minimum charge is "the charge for 5 kW of demand".
`Component.block_charge(quantity, elapsed_days=...)` evaluates a block
structure with its proration rule.

`excluded_components` lists every charge the tariff requires that is not
modeled, each with `id`, `name`, `reason` and, where available, a `source`.
Examples are the GR 26 adjustments, GR 25 supply, the GR 30 increase, the
reactive power charge and the minimum monthly charge.

## Validation (spec 6.3)

Loading fails, naming the field, on:

- missing required fields, unknown keys or misspellings (for example
  `weekday_only`);
- wrong types, non-finite numbers, or units that do not fit the category and
  determinant;
- invalid dates or effective ranges, invalid months, and invalid windows
  (overnight, `"24:00"`, unknown holiday set);
- duplicate component ids, and unknown source ids or cited documents;
- malformed blocks: fewer than two, non-increasing, unbounded in the middle,
  bounded at the end, or without a proration rule;
- a gap or an overlap inside an `exclusive_group`, checked on every
  15-minute interval of 2024, which includes both DST changes and every
  holiday;
- a sign that does not fit the category: credits must be ≤ 0, adjustments
  may take either sign, and everything else must be ≥ 0.

Overlapping windows are allowed outside exclusive groups. This is how the
additive SC-9 Rate II demand charges are expressed.

The registry also rejects:

- duplicate versions;
- dated versions of one tariff that overlap without `known_overlaps` declared
  on both;
- `owner_verified` or `bill_reconciled` without an entry in
  `verification_record.yml`.

## Selection (R4)

- `historical(tariff_id, day)` returns the one version in effect on that
  service date. It raises `TariffSelectionError` for an unknown tariff, a
  date that no version covers, a date after `valid_as_of`, or a date that two
  versions claim (`known_overlaps`). It never substitutes current rates.
- `historical_segments(tariff_id, start, end)` splits a service period by
  version.
- `scenario(tariff_id, version)` returns an explicitly named version. A
  scenario may apply a version to load data from any date. WP5 records the
  mismatch.

## Known ambiguity: January 2024

The NY PSC ETS lists two revisions of leaf 388 (SC-1) and of leaf 397 (SC-2)
with the initial effective date 01/01/2024. Revision 18 (Case 22-E-0064) and
revision 19 (Case 15-E-0751) carry different rates, and both were cancelled
effective 02/04/2024. Both are transcribed and declared as `known_overlaps`.
Historical mode rejects 2024-01-01 to 2024-02-03 until the owner resolves which
revision was billed.

## Workflow

- `scripts/build_source_leaves.py`: copies the cited leaves into
  `docs/sources/` and rewrites `sources.yml`. It needs the laptop source set
  and `pypdf`.
- `scripts/migrate_legacy_tariffs.py`: regenerates the `legacy` versions.
- `scripts/check_transcription_text.py`: checks that every text-layer quote
  is in its PDF and that every value is in its quote. It needs `pdftotext`.
- `scripts/generate_tariff_docs.py`: regenerates `docs/support_matrix.md` and
  `docs/dev/transcription_review.md`. A test checks that both are current.
- `scripts/update_tariff_snapshot.py`: run it after a deliberate value
  change. The snapshot test fails on any undeclared change.
