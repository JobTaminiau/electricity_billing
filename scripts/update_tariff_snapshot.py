"""Rewrite the snapshot of bundled tariff values (tests/snapshots/tariff_values.json).

The snapshot guards against accidental edits to tariff files. Run this only
after a deliberate, reviewed change to a tariff value, and commit the snapshot
with that change.

Usage::

    python scripts/update_tariff_snapshot.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from coned_billing.tariff_schema import TariffRegistry, snapshot_values  # noqa: E402

PATH = REPO / "tests" / "snapshots" / "tariff_values.json"


def main() -> None:
    snap = snapshot_values(TariffRegistry.from_directory())
    PATH.write_text(json.dumps(snap, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {PATH.relative_to(REPO)} ({len(snap)} versions)")


if __name__ == "__main__":
    main()
