# Primary tariff sources

This folder holds only the leaves that the tariff files cite (owner decision,
WP0). The full source set stays outside git:

- the 760-page PSC No. 10 PDF;
- 459 superseded leaves from the NY PSC Electronic Tariff System;
- the MSC data and statements.

Every PDF here is listed in `coned_billing/tariffs/v1/sources.yml` with its
sha256, URL and retrieval time. `tests/test_tariff_sources.py` checks those
checksums and fails if a file is missing, changed or unregistered.

- `psc10/current-2026-10-23/`: single pages extracted with pypdf from
  `electric-tariff.pdf`, retrieved 2026-10-23 19:10Z from coned.com (sha256
  `4141be1f16d8e49d5be19b77aa508645753890bb61ffd9019ad27a6459cb851f`). The
  register records each page's parent document and page number.
- `psc10/ets/`: superseded leaves downloaded on 2026-10-23 from the NY PSC
  Electronic Tariff System, copied byte for byte. Six of them have no text
  layer: leaf 388 r17, 397 r17, 432 r16, 445 r17 and 449 r16, whose values
  were transcribed from the rendered page image, and the holiday leaf
  389.3 r0, which is kept for reference only.

Regenerate both folders and the register with
`python scripts/build_source_leaves.py --sources <laptop source folder>`.
