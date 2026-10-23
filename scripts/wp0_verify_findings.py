"""WP0: reproduce the review findings (F3.1-F3.9) against the current checkout.

Run from the repository root::

    python scripts/wp0_verify_findings.py

Prints one line per check with the observed value. The output is pasted into
docs/dev/PROGRESS.md. This script exercises the *pre-upgrade* API on purpose;
it is a one-off diagnostic and will stop being meaningful as WP1-WP5 land.
Run it at commit 048544d (WP0); later commits change the APIs it probes.
"""

from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from coned_billing import calendars  # noqa: E402
from coned_billing.loader import _parse_time, load_rate  # noqa: E402
from coned_billing.models import DemandCharge, EnergyCharge, RateSchedule, TimeWindow  # noqa: E402

TARIFFS = ROOT / "coned_billing" / "tariffs"
NY = "America/New_York"


def flat_energy_schedule(cents_per_kwh: float = 100.0) -> RateSchedule:
    """1 $/kWh energy-only schedule so energy_cost in $ equals kWh."""
    return RateSchedule(
        code="PROBE",
        customer_charge=0.0,
        demand_components=[],
        demand_supply=[],
        energy_components=[
            EnergyCharge(rate=cents_per_kwh, window=TimeWindow(include_holidays=True))
        ],
        supply_charge=0.0,
        merchant_charge=0.0,
    )


def check(fid: str, label: str, fn) -> None:
    try:
        out = fn()
    except Exception as exc:
        out = f"RAISES {type(exc).__name__}: {exc}"
    print(f"{fid:6s} {label}: {out}")


def f31_freq() -> str:
    idx = pd.date_range("2024-01-01", periods=4, freq="15min", tz=NY)
    s = flat_energy_schedule()
    with_freq = s.bill(pd.DataFrame({"kW": 1.0}, index=idx))["energy_cost"].sum()
    no_freq = s.bill(pd.DataFrame({"kW": 1.0}, index=pd.DatetimeIndex(list(idx))))[
        "energy_cost"
    ].sum()
    return f"with .freq={with_freq:.4f} kWh, without .freq={no_freq:.4f} kWh (expected 1.0000)"


def f31_gap() -> str:
    idx = pd.date_range("2024-01-01", "2024-01-31 23:45", freq="15min", tz=NY)
    idx = idx[idx.day != 15]
    kwh = (
        flat_energy_schedule()
        .bill(pd.DataFrame({"kW": 1.0}, index=pd.DatetimeIndex(list(idx))))["energy_cost"]
        .sum()
    )
    return f"Jan 2024 at 1 kW with Jan 15 missing -> {kwh:.2f} kWh (observed energy is 720, full month 744)"


def f32_july4_tz() -> str:
    idx = pd.date_range("2023-07-04 12:00", periods=1, freq="h", tz=NY)
    naive = pd.DatetimeIndex(["2023-07-04 12:00"])
    w = TimeWindow(include_holidays=False)
    return f"holiday-excluding window keeps tz-aware Jul 4? {bool(w.mask(idx)[0])}; tz-naive? {bool(w.mask(naive)[0])}"


def f32_thanksgiving() -> str:
    hol = sorted(d for d in calendars._CONED_HOLIDAYS if d.month == 11 and d.year in (2025, 2026))
    return (
        "November holidays 2025/2026 = "
        + ", ".join(str(d.date()) for d in hol)
        + " (expected 2025-11-27, 2026-11-26)"
    )


def f32_range() -> str:
    lo, hi = min(calendars._CONED_HOLIDAYS), max(calendars._CONED_HOLIDAYS)
    return f"cached range {lo.date()} .. {hi.date()}; 2031-07-04 holiday? {pd.Timestamp('2031-07-04') in calendars._CONED_HOLIDAYS}"


def f32_scalar() -> str:
    return repr(calendars.is_coned_holiday(pd.Timestamp("2023-07-04")))


def f33_utc() -> str:
    sched = load_rate(TARIFFS / "sc9_general_rate_2_TOU.yml")
    idx = pd.date_range("2023-01-01", "2023-12-31 23:00", freq="h", tz=NY)
    rng = np.random.default_rng(0)
    kw = 800 + 400 * np.sin(np.arange(len(idx)) * 2 * np.pi / 24) + rng.uniform(0, 100, len(idx))
    ny = sched.bill(pd.DataFrame({"kW": kw}, index=idx))["total"].sum()
    utc = sched.bill(pd.DataFrame({"kW": kw}, index=idx.tz_convert("UTC")))["total"].sum()
    return f"same physical load: NY-indexed total ${ny:,.0f}, UTC-indexed total ${utc:,.0f}"


def f33_csv() -> str:
    idx = pd.date_range("2023-03-11", "2023-03-13", freq="h", tz=NY)
    buf = io.StringIO()
    pd.DataFrame({"ts": idx, "kW": 1.0}).to_csv(buf, index=False)
    buf.seek(0)
    df = pd.read_csv(buf, parse_dates=["ts"])
    dtype = df["ts"].dtype
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "load.csv"
        pd.DataFrame({"ts": idx, "kW": 1.0}).to_csv(p, index=False)
        from coned_billing.billing import bill

        try:
            bill(str(p), str(TARIFFS / "sc_1_res_rate_1.yml"))
            res = "bill() succeeded"
        except Exception as exc:
            res = f"bill() raises {type(exc).__name__}"
    return f"read_csv dtype across spring-forward = {dtype}; {res}"


def f34_values() -> str:
    sc1 = load_rate(TARIFFS / "sc_1_res_rate_1.yml")
    sc9 = load_rate(TARIFFS / "sc9_general_rate_1_LT.yml")
    sc9ii = load_rate(TARIFFS / "sc9_general_rate_2_TOU.yml")
    summer = [d.rate for d in sc9.demand_components if d.window.months and 7 in d.window.months]
    return (
        f"SC-1 customer {sc1.customer_charge} (leaf 388: 21.00); SC-9 RI LT summer demand {summer} "
        f"(leaf 445: 44.05); SC-9 RII customer {sc9ii.customer_charge} (leaf 449: 510.00)"
    )


def f34_tier() -> str:
    sc1 = load_rate(TARIFFS / "sc_1_res_rate_1.yml")
    idx = pd.date_range("2023-07-01", "2023-07-31 23:00", freq="h", tz=NY)
    kwh_total = 600.0
    df = pd.DataFrame({"kW": kwh_total / len(idx)}, index=idx)
    out = sc1.bill(df)
    delivery = (
        out["energy_cost"].sum() - kwh_total * (sc1.supply_charge + sc1.merchant_charge) / 100
    )
    return (
        f"600 kWh July delivery energy ${delivery:.2f}; all-at-one-rate {kwh_total}*{[e.rate for e in sc1.energy_components]}; "
        "leaf 388 two blocks would give 250*0.16402+350*0.18858 = $106.01"
    )


def f34_stray() -> str:
    import yaml

    raw = yaml.safe_load((TARIFFS / "sc_1_res_rate_1.yml").read_text())
    load_rate(TARIFFS / "sc_1_res_rate_1.yml")
    return f"top-level keys {list(raw)}; load_rate() accepts without complaint"


def f34_dates() -> str:
    sc8 = load_rate(TARIFFS / "sc8_multi_dwell_rate_1.yml")
    idx = pd.date_range("2019-01-01", periods=24, freq="h", tz=NY)
    t = sc8.bill(pd.DataFrame({"kW": 1.0}, index=idx))["total"].iloc[0]
    return f"2019 load billed on 02/01/2026 SC-8 tariff without error: total ${t:.2f}"


def f34_repo() -> str:
    gi = subprocess.run(
        ["git", "check-ignore", "-q", "docs/sources/example.pdf"], cwd=ROOT, check=False
    ).returncode
    src = (TARIFFS / "sources.md").read_text()
    return f"docs/sources/*.pdf ignored by git? {gi == 0}; sources.md has file:/// path? {'file:///' in src}"


def f35() -> str:
    idx = pd.date_range("2024-01-02", periods=8, freq="15min", tz=NY)
    kw = np.zeros(8)
    kw[3] = 40.0
    s = RateSchedule(
        "PROBE",
        0.0,
        [DemandCharge(rate=1.0, window=TimeWindow(include_holidays=True))],
        [],
        [],
        0.0,
        0.0,
    )
    d = s.bill(pd.DataFrame({"kW": kw}, index=idx))["demand_cost"].sum()
    return f"one 15-min 40 kW spike -> billed demand {d:.1f} kW (raw max); 30-min integrated = 20.0, 60-min = 10.0"


def f36() -> str:
    sc9 = load_rate(TARIFFS / "sc9_general_rate_1_LT.yml")
    idx = pd.date_range("2024-01-01", periods=24, freq="h", tz=NY)
    cols = list(sc9.bill(pd.DataFrame({"kW": 1.0}, index=idx)).columns)
    return f"result columns {cols}; no completeness/exclusion field"


def f37() -> str:
    idx = pd.date_range("2023-01-01", "2023-01-31 23:00", freq="h", tz=NY)
    out = flat_energy_schedule().bill(pd.DataFrame({"kW": 10.0}, index=idx))
    return f"flat 10 kW January -> 'kW' column = {out['kW'].iloc[0]:.0f}"


def f38_misspelled() -> str:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.yml"
        p.write_text(
            textwrap.dedent(
                """
                code: PROBE
                customer_charge: 0
                supply_charge: 0
                merchant_charge: 0
                demand_delivery:
                  - {rate: 1.0, window: {weekday_only: true, start: "08:00", end: "18:00"}}
                energy:
                  - {rate: 0, window: {include_holidays: true}}
                """
            )
        )
        rs = load_rate(p)
        sat = pd.DatetimeIndex([pd.Timestamp("2024-01-06 12:00", tz=NY)])
        return f"'weekday_only' accepted; weekdays_only={rs.demand_components[0].window.weekdays_only}; Saturday noon in window? {bool(rs.demand_components[0].window.mask(sat)[0])}"


def f38_2400() -> str:
    return repr(_parse_time("24:00"))


def f39() -> str:
    import tomllib

    meta = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    lic = (ROOT / "LICENSE.txt").read_text().splitlines()[0]
    readme_kw = '"kw"' in (ROOT / "README.md").read_text()
    sc_src = (ROOT / "coned_billing" / "supply_charge.py").read_text()
    return (
        f"requires-python {meta['requires-python']!r}; license meta {meta['license']}; LICENSE.txt starts {lic!r}; "
        f"README uses 'kw': {readme_kw}; supply_charge.py imports requests at top level: {any(ln.startswith('import requests') for ln in sc_src.splitlines())}; "
        f"great_tables hard dep: {any('great_tables' in d for d in meta['dependencies'])}; "
        f"CI workflows present: {(ROOT / '.github' / 'workflows').exists()}"
    )


def main() -> None:
    print(f"python {sys.version.split()[0]}, pandas {pd.__version__}, numpy {np.__version__}")
    checks = [
        ("F3.1", "energy vs .freq", f31_freq),
        ("F3.1", "missing day", f31_gap),
        ("F3.2", "tz-aware July 4", f32_july4_tz),
        ("F3.2", "Thanksgiving", f32_thanksgiving),
        ("F3.2", "holiday range", f32_range),
        ("F3.2", "scalar is_coned_holiday", f32_scalar),
        ("F3.3", "UTC vs NY index", f33_utc),
        ("F3.3", "CSV across DST", f33_csv),
        ("F3.4", "stale values", f34_values),
        ("F3.4", "SC-1 summer tier", f34_tier),
        ("F3.4", "stray key", f34_stray),
        ("F3.4", "effective dates", f34_dates),
        ("F3.4", "repo hygiene", f34_repo),
        ("F3.5", "demand interval", f35),
        ("F3.6", "completeness", f36),
        ("F3.7", "summed kW", f37),
        ("F3.8", "misspelled key", f38_misspelled),
        ("F3.8", "24:00", f38_2400),
        ("F3.9", "packaging", f39),
    ]
    for fid, label, fn in checks:
        check(fid, label, fn)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # pragma: no cover
        traceback.print_exc()
        sys.exit(1)
