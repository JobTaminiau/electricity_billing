"""Migrate the six legacy-format tariff YAMLs to schema v1 (D2, WP3).

Each legacy file becomes ``coned_billing/tariffs/v1/<tariff_id>/legacy.yml``
with version ``legacy``, ``verification_status: unverified`` and scenario mode
only. Every value is copied unchanged, in the legacy file's own units; the
legacy header comments and notes are kept under ``legacy_notes``. The legacy
files themselves stay in place for :func:`coned_billing.load_rate`.

Usage::

    python scripts/migrate_legacy_tariffs.py
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
LEGACY = REPO / "coned_billing" / "tariffs"
OUT = LEGACY / "v1"

# legacy file -> (tariff_id, service classification, rate option, voltage)
FILES = {
    "sc_1_res_rate_1.yml": ("sc1_rate1", "SC-1", "Rate I - Residential and Religious", None),
    "sc2_general_rate_1.yml": ("sc2_rate1", "SC-2", "Rate I - General - Small", None),
    "sc8_multi_dwell_rate_1.yml": (
        "sc8_rate1_lt",
        "SC-8",
        "Rate I - Multiple Dwellings - Redistribution",
        "low_tension",
    ),
    "sc9_general_rate_1_LT.yml": (
        "sc9_rate1_lt",
        "SC-9",
        "Rate I - General - Large",
        "low_tension",
    ),
    "sc9_general_rate_I-HT.yml": (
        "sc9_rate1_ht",
        "SC-9",
        "Rate I - General - Large",
        "high_tension",
    ),
    "sc9_general_rate_2_TOU.yml": (
        "sc9_rate2_lt",
        "SC-9",
        "Rate II - General - Large - Time-of-Day",
        "low_tension",
    ),
}


class Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def _list(dumper, data):
    flow = all(isinstance(x, int) and not isinstance(x, bool) for x in data)
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow)


Dumper.add_representer(list, _list)


def window(w: dict) -> dict:
    """Legacy window -> v1 window with an explicit holiday set (legacy semantics)."""
    out = {k: w[k] for k in ("months", "weekdays_only", "start", "end") if k in w}
    if "excluded_holidays" in w:
        out["excluded_holidays"] = w["excluded_holidays"]
    else:  # legacy default: include_holidays false -> the six-day set
        out["excluded_holidays"] = "none" if w.get("include_holidays", False) else "coned_six"
    return out


def migrate(name: str) -> dict:
    tid, sc, rate, voltage = FILES[name]
    text = (LEGACY / name).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    comments = "\n".join(line for line in text.splitlines() if line.lstrip().startswith("#"))
    notes = f"Header comments of {name}:\n{comments}"
    if "notes" in data:
        notes += f"\nnotes (formerly a stray top-level key '0'):\n{data['notes']}"
    dm = {"method": "input_interval_maximum"}
    comps: list[dict] = [
        {
            "id": "customer_charge",
            "name": "Customer charge (legacy)",
            "category": "fixed_charge",
            "determinant": "billing_period",
            "unit": "USD/month",
            "rate": data["customer_charge"],
            "window": {"excluded_holidays": "none"},
        }
    ]
    for i, c in enumerate(data.get("energy") or [], 1):
        comps.append(
            {
                "id": f"energy_delivery_{i}",
                "name": f"Energy delivery charge {i} (legacy)",
                "category": "delivery_energy",
                "determinant": "kwh",
                "unit": "cents/kWh",
                "rate": c["rate"],
                "window": window(c["window"]),
                "exclusive_group": "energy_delivery",
            }
        )
    for key, cat, label in (
        ("demand_delivery", "delivery_demand", "Demand delivery charge"),
        ("demand_supply", "supply_demand", "Demand supply charge"),
    ):
        for i, c in enumerate(data.get(key) or [], 1):
            comps.append(
                {
                    "id": f"{key}_{i}",
                    "name": f"{label} {i} (legacy)",
                    "category": cat,
                    "determinant": "max_demand_kw",
                    "unit": "USD/kW",
                    "rate": c["rate"],
                    "window": window(c["window"]),
                    "demand_measurement": dm,
                }
            )
    comps += [
        {
            "id": "supply_energy",
            "name": "Supply charge (legacy)",
            "category": "supply_energy",
            "determinant": "kwh",
            "unit": "cents/kWh",
            "rate": data["supply_charge"],
            "window": {"excluded_holidays": "none"},
            "exclusive_group": "supply_energy",
        },
        {
            "id": "merchant_charge",
            "name": "Merchant function charge (legacy)",
            "category": "merchant_charge",
            "determinant": "kwh",
            "unit": "cents/kWh",
            "rate": data["merchant_charge"],
            "window": {"excluded_holidays": "none"},
        },
    ]
    return {
        "schema_version": 1,
        "tariff_id": tid,
        "version": "legacy",
        "utility": "Consolidated Edison Company of New York, Inc.",
        "jurisdiction": "New York State Public Service Commission",
        "tariff_book": "PSC No. 10 - Electricity",
        "service_classification": sc,
        "rate_option": rate,
        "voltage": voltage,
        "zone": None,
        "timezone": "America/New_York",
        "effective": {"start": None, "end": None},
        "verification_status": "unverified",
        "calculation_modes": ["scenario"],
        "sources": [],
        "assumptions": [
            f"Values copied unchanged from the legacy file {name} (code {data['code']}); their "
            "provenance and dates are unverified (D2). Scenario mode only.",
            "The legacy files mix delivery values from different leaf revisions with supply and merchant "
            "assumptions from other periods (finding F3.4).",
            "Legacy demand is the largest input-interval kW (method input_interval_maximum), the "
            "pre-WP4 engine behaviour.",
            "Windows keep the legacy holiday semantics: include_holidays false excludes the six-day "
            "set (coned_six), true excludes none.",
        ],
        "legacy_notes": notes,
        "components": comps,
        "excluded_components": [],
    }


def main() -> None:
    for name in FILES:
        d = migrate(name)
        path = OUT / d["tariff_id"] / "legacy.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        body = yaml.dump(d, Dumper=Dumper, sort_keys=False, width=100, allow_unicode=True)
        path.write_text(
            f"# Tariff schema v1. Migrated from coned_billing/tariffs/{name} by\n"
            "# scripts/migrate_legacy_tariffs.py; values unchanged, status unverified.\n" + body,
            encoding="utf-8",
        )
        print(f"{name} -> {path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
