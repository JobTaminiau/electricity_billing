"""Tariff-source verification tests (WP3, R14).

These check that stored values are tied to checksummed source documents and
have not drifted. They are distinct from the arithmetic tests: the expected
rates below were typed from the cited leaves, not read from the tariff files.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from coned_billing.tariff_docs import render_support_matrix, render_transcription_review
from coned_billing.tariff_schema import default_registry, snapshot_values

REPO = Path(__file__).resolve().parents[1]
SOURCES = REPO / "docs" / "sources"
SNAPSHOT = Path(__file__).parent / "snapshots" / "tariff_values.json"
needs_sources = pytest.mark.skipif(
    not SOURCES.is_dir(), reason="docs/sources/ is only present in a source checkout"
)


def _transcribed():
    return [v for v in default_registry() if v.verification_status != "unverified"]


def test_every_transcribed_value_has_a_citation():
    for v in _transcribed():
        for c in v.components:
            assert c.source is not None, (v.key, c.id)
            assert c.source.document in v.sources
            assert c.source.text, (v.key, c.id)
            if c.blocks:
                assert c.block_proration is not None and c.block_proration.source is not None
            if c.demand_measurement is not None:
                assert c.demand_measurement.source is not None


@needs_sources
def test_registered_documents_match_their_checksums():
    docs = default_registry().sources
    cited = {
        cit.document
        for v in _transcribed()
        for c in v.components
        for cit in (
            c.source,
            c.block_proration and c.block_proration.source,
            c.proration and c.proration.source,
            c.demand_measurement and c.demand_measurement.source,
        )
        if cit
    }
    assert cited <= set(docs)
    for doc in docs.values():
        path = SOURCES / doc.file
        assert path.is_file(), doc.file
        assert hashlib.sha256(path.read_bytes()).hexdigest() == doc.sha256, doc.file


@needs_sources
def test_every_source_file_is_registered():
    registered = {d.file for d in default_registry().sources.values()}
    on_disk = {p.relative_to(SOURCES).as_posix() for p in SOURCES.rglob("*.pdf")}
    assert on_disk == registered


def test_snapshot_of_tariff_values():
    """A change to any tariff value needs an explicit snapshot update.

    After a reviewed change, run ``python scripts/update_tariff_snapshot.py``
    and commit the snapshot with the change.
    """
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    actual = json.loads(json.dumps(snapshot_values(default_registry())))
    changed = sorted(k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k))
    assert not changed, f"tariff values differ from the snapshot for {changed}"


@needs_sources
def test_generated_docs_are_current():
    reg = default_registry()
    assert (REPO / "docs" / "support_matrix.md").read_text(
        encoding="utf-8"
    ) == render_support_matrix(reg)
    assert (REPO / "docs" / "dev" / "transcription_review.md").read_text(
        encoding="utf-8"
    ) == render_transcription_review(reg)


# Values typed from the 02/01/2026 leaves (PSC No. 10, Case 25-E-0072):
# leaf 388 r23, 397 r23, 432 r21, 445 r22, 449 r20. Units as printed.
FEB_2026 = {
    "sc1_rate1": {
        "customer_charge": 21.00,
        "energy_delivery_summer": [(250, 0.16402), (None, 0.18858)],
        "energy_delivery_other": 0.16402,
    },
    "sc2_rate1": {
        "customer_charge": 34.00,
        "energy_delivery_summer": 0.2038,
        "energy_delivery_other": 0.1709,
    },
    "sc8_rate1_lt": {
        "customer_charge": 59.00,
        "demand_delivery_summer": 55.65,
        "demand_delivery_other": 42.90,
        "energy_delivery": 0.0123,
    },
    "sc9_rate1_lt": {
        "customer_charge": 72.00,
        "demand_delivery_summer": 44.05,
        "demand_delivery_other": 34.50,
        "energy_delivery": 0.0154,
    },
    "sc9_rate1_ht": {
        "customer_charge": 72.00,
        "demand_delivery_summer": 30.41,
        "demand_delivery_other": 21.17,
        "energy_delivery": 0.0143,
    },
    "sc9_rate2_lt": {
        "customer_charge": 510.00,
        "demand_summer_weekday_0800_1800": 11.33,
        "demand_summer_weekday_0800_2200": 22.82,
        "demand_summer_all_hours": 20.61,
        "demand_other_weekday_0800_2200": 19.41,
        "demand_other_all_hours": 5.85,
        "energy_delivery": 0.0079,
    },
}


@pytest.mark.parametrize("tid", sorted(FEB_2026))
def test_feb_2026_values_match_the_leaves(tid):
    v = default_registry().historical(tid, date(2026, 3, 1))
    assert v.version == "2026-02-01" and v.case == "25-E-0072"
    assert {c.id for c in v.components} == set(FEB_2026[tid])
    for cid, want in FEB_2026[tid].items():
        c = v.component(cid)
        if isinstance(want, list):
            assert [(b.up_to, b.rate) for b in c.blocks] == want
        else:
            assert c.rate == want, (tid, cid)


# Spot checks of superseded revisions, typed from the ETS leaf PDFs.
HISTORICAL = [
    ("sc1_rate1", date(2020, 6, 1), "customer_charge", 16.00),  # leaf 388 r13
    ("sc1_rate1", date(2022, 7, 1), "energy_delivery_other", 12.732),  # leaf 388 r15, cents
    ("sc2_rate1", date(2023, 9, 1), "energy_delivery_summer", 17.51),  # leaf 397 r17 (page image)
    ("sc8_rate1_lt", date(2024, 2, 1), "customer_charge", 55.00),  # leaf 432 r17
    ("sc9_rate1_ht", date(2025, 7, 1), "demand_delivery_summer", 29.50),  # leaf 445 r20
    ("sc9_rate2_lt", date(2021, 3, 1), "customer_charge", 143.09),  # leaf 449 r13
    (
        "sc9_rate2_lt",
        date(2023, 10, 1),
        "demand_other_all_hours",
        4.98,
    ),  # leaf 449 r16 (page image)
]


@pytest.mark.parametrize(("tid", "day", "cid", "want"), HISTORICAL)
def test_superseded_revision_spot_checks(tid, day, cid, want):
    assert default_registry().historical(tid, day).component(cid).rate == want


def test_pre_2024_large_rate_i_demand_blocks():
    # Leaf 445 r15 (eff. 01/01/2022): low tension, June-September,
    # "first 5 kW (or less) $219.36 per month", "over 5 kW $31.13 per kW".
    c = (
        default_registry()
        .historical("sc9_rate1_lt", date(2022, 8, 1))
        .component("demand_delivery_summer")
    )
    assert [(b.up_to, b.rate, b.unit) for b in c.blocks] == [
        (5, 219.36, "USD/month"),
        (None, 31.13, "USD/kW"),
    ]
    assert c.block_charge(105) == pytest.approx(219.36 + 100 * 31.13, abs=1e-9)
