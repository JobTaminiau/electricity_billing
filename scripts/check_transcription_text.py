"""Check transcribed tariff values against the text of the cited leaves.

For every citation with ``method: text_layer``, the quoted ``text`` must occur
in the cited PDF's text layer (whitespace-normalized). For every component,
each rate value must appear in its own quote. Citations with
``method: page_image`` (leaves without a text layer) are listed for manual
review instead.

Needs the ``pdftotext`` command (poppler). Development aid; not run by pytest.

Usage::

    python scripts/check_transcription_text.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from functools import cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from coned_billing.tariff_schema import TariffRegistry  # noqa: E402

SOURCES = REPO / "docs" / "sources"


def normalize(s: str) -> str:
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\$ +", "$", s)  # "$     72.00" in right-aligned columns
    s = re.sub(r"(\d)- ", r"\1-", s)  # "30-\nday" line breaks
    return s.strip()


@cache
def text_of(file: str) -> str:
    out = subprocess.run(
        ["pdftotext", "-layout", str(SOURCES / file), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return normalize(out.stdout)


def numbers_in(s: str) -> set[float]:
    return {float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", s)}


def main() -> int:
    reg = TariffRegistry.from_directory()
    problems, images, checked = [], [], 0
    for v in reg:
        if v.verification_status == "unverified":
            continue
        cits = []
        for c in v.components:
            cits.append((c.id, c.source))
            if c.block_proration:
                cits.append((f"{c.id}.block_proration", c.block_proration.source))
            if c.proration:
                cits.append((f"{c.id}.proration", c.proration.source))
            if c.demand_measurement:
                cits.append((f"{c.id}.demand_measurement", c.demand_measurement.source))
            quote = c.source.text if c.source else None
            values = [c.rate] if c.rate is not None else [b.rate for b in c.blocks]
            for x in values:
                if quote is None or not any(abs(x - n) < 1e-12 for n in numbers_in(quote)):
                    problems.append(f"{v.key} {c.id}: value {x} not in its quote {quote!r}")
        cits += [(e.id, e.source) for e in v.excluded_components]
        for name, cit in cits:
            if cit is None or cit.text is None:
                continue
            doc = reg.sources[cit.document]
            if cit.method == "page_image":
                images.append(f"{v.key} {name}: {doc.file}: {cit.text!r}")
                continue
            checked += 1
            if normalize(cit.text) not in text_of(doc.file):
                problems.append(f"{v.key} {name}: quote not found in {doc.file}: {cit.text!r}")
    print(f"checked {checked} text-layer quotes")
    print(f"{len(images)} quotes rest on page images (review by eye):")
    for line in sorted(set(images)):
        print("  ", line)
    for p in problems:
        print("PROBLEM", p)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
