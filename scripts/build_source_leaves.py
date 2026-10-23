"""Copy the cited tariff leaves into docs/sources/ and write the source register.

The full source set (the 760-page PSC No. 10 PDF, 459 superseded leaves from
the NY PSC ETS, MSC data) stays outside git (owner decision, WP0). This script
keeps only the leaves that tariff files cite:

* single pages extracted from the current full tariff PDF, and
* superseded leaves downloaded from the NY PSC Electronic Tariff System, copied
  byte-for-byte after checking their sha256 against the download manifest.

It then writes ``coned_billing/tariffs/v1/sources.yml`` with each file's
sha256, URL, retrieval time and, for extracted pages, the parent document's
sha256 and page. Requires ``pypdf`` (a dev-only dependency).

Usage::

    python scripts/build_source_leaves.py --sources <dir with MANIFEST.csv, electric-tariff.pdf, historical/>
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import shutil
from pathlib import Path

import pypdf

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "sources"
REGISTER = REPO / "coned_billing" / "tariffs" / "v1" / "sources.yml"
CURRENT_DIR = "psc10/current-2026-10-23"
ETS_DIR = "psc10/ets"

# (pdf page, leaf, revision, initial effective date) from LEAF_INDEX.csv.
CURRENT_PAGES = [
    (98, "84", 1, "01/01/2024"),
    (99, "85", 3, "07/01/2015"),
    (104, "90", 4, "02/01/2020"),
    (486, "327.2", 2, "11/03/2022"),
    (616, "387", 6, "12/01/2023"),
    (617, "388", 23, "02/01/2026"),
    (618, "389", 23, "02/01/2026"),
    (622, "389.3", 1, "04/06/2020"),
    (623, "390", 5, "07/01/2025"),
    (630, "396", 3, "08/01/2023"),
    (631, "397", 23, "02/01/2026"),
    (634, "399", 5, "07/01/2025"),
    (668, "431", 1, "02/20/2012"),
    (669, "432", 21, "02/01/2026"),
    (679, "440", 5, "08/01/2023"),
    (683, "444", 3, "08/01/2023"),
    (684, "445", 22, "02/01/2026"),
    (686, "447", 1, "02/20/2012"),
    (688, "449", 20, "02/01/2026"),
    (699, "454", 5, "08/01/2023"),
]
# (leaf, revision) of superseded leaves from the NY PSC ETS.
ETS_LEAVES = (
    [("84", 0), ("389.3", 0)]
    + [("388", r) for r in (11, 13, 14, 15, 17, 18, 19, 20, 21)]
    + [("397", r) for r in (11, 13, 14, 15, 17, 18, 19, 20, 21)]
    + [("432", r) for r in (12, 13, 14, 16, 17, 18, 19)]
    + [("445", r) for r in (13, 14, 15, 17, 18, 19, 20)]
    + [("449", r) for r in (12, 13, 14, 16, 17, 18)]
)
TARIFF_URL = (
    "https://www.coned.com/-/media/files/coned/documents/rates/electric/psc-10/electric-tariff.pdf"
)


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sources", type=Path, required=True)
    args = ap.parse_args()
    src: Path = args.sources

    manifest = {r["file"]: r for r in csv.DictReader((src / "MANIFEST.csv").open(encoding="utf-8"))}
    tariff = manifest["electric-tariff.pdf"]
    tariff_bytes = (src / "electric-tariff.pdf").read_bytes()
    assert sha256(tariff_bytes) == tariff["sha256"], "electric-tariff.pdf checksum mismatch"
    index = {
        int(r["page"]): r
        for r in csv.DictReader((src / "LEAF_INDEX.csv").open(encoding="utf-8"))
        if r["file"] == "electric-tariff.pdf"
    }
    reader = pypdf.PdfReader(io.BytesIO(tariff_bytes))
    entries: list[dict[str, object]] = []

    (OUT / CURRENT_DIR).mkdir(parents=True, exist_ok=True)
    for page, leaf, rev, eff in CURRENT_PAGES:
        row = index[page]
        assert (row["leaf"], int(row["revision"]), row["initial_effective_date"]) == (
            leaf,
            rev,
            eff,
        ), row
        w = pypdf.PdfWriter()
        w.add_page(reader.pages[page - 1])
        buf = io.BytesIO()
        w.write(buf)
        rel = f"{CURRENT_DIR}/leaf_{leaf}_r{rev}.pdf"
        (OUT / rel).write_bytes(buf.getvalue())
        entries.append(
            {
                "id": f"psc10-leaf-{leaf}-r{rev}",
                "title": f"PSC No. 10 - Electricity, leaf {leaf}, revision {rev} (initial effective {eff})",
                "url": TARIFF_URL,
                "retrieved_utc": tariff["retrieved_utc"],
                "sha256": sha256(buf.getvalue()),
                "file": rel,
                "parent_file": "electric-tariff.pdf",
                "parent_sha256": tariff["sha256"],
                "parent_page": page,
                "notes": "Single page extracted with pypdf from the full tariff PDF.",
            }
        )

    ets = {
        (r["leaf"], int(r["revision"])): r
        for r in csv.DictReader((src / "historical" / "ETS_LEAF_INDEX.csv").open(encoding="utf-8"))
    }
    hist_manifest = {
        r["file"]: r
        for r in csv.DictReader((src / "historical" / "MANIFEST.csv").open(encoding="utf-8"))
    }
    (OUT / ETS_DIR).mkdir(parents=True, exist_ok=True)
    for leaf, rev in ETS_LEAVES:
        row = ets[(leaf, rev)]
        m = hist_manifest[row["file"]]
        data = (src / "historical" / row["file"]).read_bytes()
        assert sha256(data) == row["sha256"] == m["sha256"], row["file"]
        rel = f"{ETS_DIR}/leaf_{leaf}_r{rev}.pdf"
        shutil.copyfile(src / "historical" / row["file"], OUT / rel)
        entries.append(
            {
                "id": f"psc10-leaf-{leaf}-r{rev}",
                "title": (
                    f"PSC No. 10 - Electricity, leaf {leaf}, revision {rev} "
                    f"(effective {row['effective']}, cancelled {row['cancelled']}; case {row['case']})"
                ),
                "url": m["source_url"],
                "retrieved_utc": m["retrieved_utc"],
                "sha256": row["sha256"],
                "file": rel,
                "notes": f"NY PSC Electronic Tariff System, submission {row['submission_id']}.",
            }
        )

    lines = [
        "# Source-document register for tariff schema v1.",
        "# Generated by scripts/build_source_leaves.py; do not edit by hand.",
        "schema_version: 1",
        "documents:",
    ]
    for e in entries:
        lines.append(f"  - id: {e['id']}")
        for k in (
            "title",
            "url",
            "retrieved_utc",
            "sha256",
            "file",
            "parent_file",
            "parent_sha256",
        ):
            if k in e:
                lines.append(f"    {k}: {q(str(e[k]))}")
        if "parent_page" in e:
            lines.append(f"    parent_page: {e['parent_page']}")
        lines.append(f"    notes: {q(str(e['notes']))}")
    REGISTER.parent.mkdir(parents=True, exist_ok=True)
    REGISTER.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(entries)} documents to {REGISTER.relative_to(REPO)}")


if __name__ == "__main__":
    main()
