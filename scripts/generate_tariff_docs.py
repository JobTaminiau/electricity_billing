"""Regenerate docs/support_matrix.md and docs/dev/transcription_review.md.

Usage::

    python scripts/generate_tariff_docs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from coned_billing.tariff_docs import (  # noqa: E402
    render_support_matrix,
    render_transcription_review,
)
from coned_billing.tariff_schema import TariffRegistry  # noqa: E402


def main() -> None:
    reg = TariffRegistry.from_directory()
    (REPO / "docs" / "support_matrix.md").write_text(render_support_matrix(reg), encoding="utf-8")
    (REPO / "docs" / "dev" / "transcription_review.md").write_text(
        render_transcription_review(reg), encoding="utf-8"
    )
    print("wrote docs/support_matrix.md and docs/dev/transcription_review.md")


if __name__ == "__main__":
    main()
