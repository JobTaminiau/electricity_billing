"""Generated documentation for the bundled tariffs (R11, WP3).

``render_support_matrix`` writes ``docs/support_matrix.md`` and
``render_transcription_review`` writes ``docs/dev/transcription_review.md``,
both from the tariff metadata. Regenerate with
``python scripts/generate_tariff_docs.py``; a test checks they are current.
"""

from __future__ import annotations

from .tariff_schema import Citation, Component, TariffRegistry, TariffVersion

__all__ = ["render_support_matrix", "render_transcription_review"]

_VOLT = {None: "n/a", "low_tension": "low tension", "high_tension": "high tension"}


def _span(v: TariffVersion) -> str:
    if v.effective_start is None:
        return "undated"
    end = v.effective_end.isoformat() if v.effective_end else f"open (checked {v.valid_as_of})"
    return f"{v.effective_start} to {end}"


def _window(c: Component) -> str:
    w = c.window
    parts = []
    if w.months:
        parts.append("months " + ",".join(str(m) for m in w.months))
    if w.weekdays_only is True:
        parts.append("Mon-Fri")
    elif w.weekdays_only is False:
        parts.append("Sat-Sun")
    if w.start or w.end:
        s = w.start.strftime("%H:%M") if w.start else "00:00"
        e = w.end.strftime("%H:%M") if w.end else "end of day"
        parts.append(f"{s}-{e}")
    parts.append(f"holidays excluded: {w.holiday_set.name}")
    return "; ".join(parts)


def _value(c: Component) -> str:
    if c.blocks:
        out, lo = [], 0.0
        for b in c.blocks:
            rng = f"{lo:g}-{b.up_to:g}" if b.up_to is not None else f"over {lo:g}"
            out.append(f"{rng}: {b.rate:g} {b.unit}")
            lo = b.up_to or lo
        return "; ".join(out)
    return f"{c.rate:g} {c.unit}"


def _cite(reg: TariffRegistry, cit: Citation | None) -> str:
    if cit is None:
        return "none"
    doc = reg.sources.get(cit.document)
    where = f"PSC 10 PDF p. {doc.parent_page}" if doc and doc.parent_page else "NY PSC ETS leaf PDF"
    return f"leaf {cit.leaf} rev {cit.revision} ({where})"


def _md(s: str | None) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def render_support_matrix(reg: TariffRegistry) -> str:
    lines = [
        "# Tariff support matrix",
        "",
        "Generated from the tariff metadata by `python scripts/generate_tariff_docs.py`; do not edit.",
        "",
        "Verification status (spec 5.1): `unverified` values have unknown provenance; `transcribed` "
        "values cite a leaf, revision and page of a checksummed source; `owner_verified` needs an entry "
        "in `coned_billing/tariffs/v1/verification_record.yml`, which only the owner edits.",
        "",
        "Effective dates are dates of service, start inclusive, end exclusive. Rates and options not "
        "listed here are rejected (D3).",
        "",
    ]
    for tid in reg.tariff_ids():
        vs = reg.versions(tid)
        v0 = vs[-1]
        lines += [
            f"## `{tid}`: {v0.service_classification} {v0.rate_option}",
            "",
            f"Voltage: {_VOLT[v0.voltage]}. Zone: {v0.zone or 'not zone-specific'}.",
            "",
            "| Version | Effective (service dates) | Status | Modes | Source leaves | Notes |",
            "|---|---|---|---|---|---|",
        ]
        for v in vs:
            leaves = ", ".join(
                sorted({f"{c.source.leaf} r{c.source.revision}" for c in v.components if c.source})
            )
            note = "ambiguous: overlaps " + ", ".join(v.known_overlaps) if v.known_overlaps else ""
            lines.append(
                f"| {v.version} | {_span(v)} | {v.verification_status} | "
                f"{', '.join(v.calculation_modes)} | {leaves or 'uncited'} | {note} |"
            )
        latest = [v for v in vs if v.verification_status != "unverified"][-1]
        lines += [
            "",
            f"Implemented components (latest transcribed version, {latest.version}):",
            "",
        ]
        for c in latest.components:
            dem = ""
            if c.demand_measurement is not None:
                m = c.demand_measurement
                dem = (
                    f"; demand: {m.integration_minutes}-minute integrated"
                    if m.method == "integrated_demand"
                    else "; demand: input-interval maximum"
                )
            lines.append(f"- `{c.id}` ({c.category}): {_value(c)}; {_window(c)}{dem}")
        lines += ["", "Excluded components:", ""]
        lines += [f"- `{e.id}`: {e.name}. {e.reason}" for e in latest.excluded_components]
        inputs = latest.required_account_inputs or ("none",)
        lines += ["", "Required account inputs: " + "; ".join(inputs) + ".", ""]
        minutes = sorted(
            {
                c.demand_measurement.integration_minutes
                for c in latest.components
                if c.demand_measurement is not None and c.demand_measurement.integration_minutes
            }
        )
        if minutes:
            lines += [
                "Supported demand resolution: billed demand is the "
                + ", ".join(f"{m}-minute" for m in minutes)
                + " integrated demand (GR 10.4); deriving it from interval data is WP4.",
                "",
            ]
    return "\n".join(lines).rstrip() + "\n"


def render_transcription_review(reg: TariffRegistry) -> str:
    lines = [
        "# Transcription review",
        "",
        "Generated from the tariff files by `python scripts/generate_tariff_docs.py`; do not edit.",
        "",
        "Each transcribed value is listed next to its citation and the quoted leaf wording. "
        "`scripts/check_transcription_text.py` confirms that every text-layer quote occurs in the cited "
        "PDF and that every value occurs in its quote. Rows marked **page image** come from leaves "
        "without a text layer and were read from the rendered page: check these by eye.",
        "",
        "To approve a version, add it to `coned_billing/tariffs/v1/verification_record.yml` "
        "(owner only) and set its `verification_status` to `owner_verified`.",
        "",
    ]
    for v in reg:
        if v.verification_status == "unverified":
            continue
        lines += [
            f"## `{v.tariff_id}` {v.version}",
            "",
            f"{v.service_classification} {v.rate_option}, {_VOLT[v.voltage]}; {_span(v)}; "
            f"case {v.case or 'n/a'}; status {v.verification_status}.",
            "",
            "| Component | Value | Window | Citation | Quoted text | Method |",
            "|---|---|---|---|---|---|",
        ]
        for c in v.components:
            cit = c.source
            method = "**page image**" if cit and cit.method == "page_image" else "text layer"
            lines.append(
                f"| `{c.id}` | {_value(c)} | {_window(c)} | {_cite(reg, cit)} | "
                f"{_md(cit.text if cit else '')} | {method} |"
            )
        lines += [
            "",
            "Excluded: " + ", ".join(f"`{e.id}`" for e in v.excluded_components) + ".",
            "",
        ]
        if v.notes:
            lines += [f"Note: {v.notes}", ""]
    return "\n".join(lines).rstrip() + "\n"
