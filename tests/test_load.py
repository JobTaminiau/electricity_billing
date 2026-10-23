"""WP1: load-data contract and interval energy (R1).

Arithmetic reference tests: every expected value is an independently known
quantity (interval counts from the calendar, kW x hours by hand). Exact float
comparison is used where the arithmetic is exact in binary (quarter hours,
integer kW); otherwise a 1e-9 relative tolerance covers summation rounding.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from coned_billing import LoadDataError, LoadProfile, RateSchedule, read_load_csv
from coned_billing.models import EnergyCharge, TimeWindow

NY = "America/New_York"


def _kw(idx, value=1.0) -> pd.Series:
    return pd.Series(value, index=idx, dtype="float64")


def _profile(idx, value=1.0, interval="1h", label="start", **kw) -> LoadProfile:
    return LoadProfile.from_series(
        _kw(idx, value), quantity="kW", interval=interval, label=label, **kw
    )


def _energy_only() -> RateSchedule:
    """1 $/kWh, all hours: energy_cost in $ equals kWh."""
    return RateSchedule(
        code="TEST",
        customer_charge=0.0,
        demand_components=[],
        demand_supply=[],
        energy_components=[EnergyCharge(rate=100.0, window=TimeWindow(include_holidays=True))],
        supply_charge=0.0,
        merchant_charge=0.0,
    )


# ─────────────────────────── energy from durations only ──────────────────────────
def test_freq_metadata_is_irrelevant():
    idx = pd.date_range("2024-01-01", periods=4, freq="15min", tz=NY)
    without = pd.DatetimeIndex(list(idx))
    assert idx.freq is not None and without.freq is None
    a = _profile(idx, interval="15min").total_kwh
    b = _profile(without, interval="15min").total_kwh
    assert a == b == 1.0  # 4 x 0.25 h x 1 kW


@pytest.mark.parametrize(
    ("interval", "periods", "kw", "expected_kwh"),
    [
        ("1h", 24, 2.0, 48.0),  # one day hourly
        ("30min", 48, 2.0, 48.0),
        ("15min", 96, 2.0, 48.0),
        ("5min", 288, 2.0, 48.0),
        ("15min", 4, 1.0, 1.0),
    ],
)
def test_known_totals_by_resolution(interval, periods, kw, expected_kwh):
    idx = pd.date_range("2024-03-05", periods=periods, freq=interval, tz=NY)
    assert _profile(idx, kw, interval=interval).total_kwh == expected_kwh


def test_kw_and_equivalent_kwh_inputs_identical():
    idx = pd.date_range("2024-06-01", periods=96, freq="15min", tz=NY)
    kw = np.linspace(0, 40, 96)
    p_kw = LoadProfile.from_series(
        pd.Series(kw, index=idx), quantity="kW", interval="15min", label="start"
    )
    p_kwh = LoadProfile.from_series(
        pd.Series(kw * 0.25, index=idx), quantity="kWh", interval="15min", label="start"
    )
    np.testing.assert_array_equal(p_kw.kw, p_kwh.kw)  # x0.25 then /0.25 is exact
    assert p_kw.total_kwh == p_kwh.total_kwh
    a = _energy_only().bill(p_kw)
    b = _energy_only().bill(p_kwh)
    pd.testing.assert_frame_equal(a, b)


def test_interval_start_and_end_labels():
    # Hourly January 2024 at 1 kW. Start labels: 2024-01-01 00:00 .. 01-31 23:00.
    # End labels for the same intervals: 2024-01-01 01:00 .. 2024-02-01 00:00.
    starts = pd.date_range("2024-01-01 00:00", "2024-01-31 23:00", freq="h", tz=NY)
    ends = starts + pd.Timedelta("1h")
    p_start = _profile(starts, label="start")
    p_end = _profile(ends, label="end")
    assert p_start.start.equals(p_end.start)
    out = _energy_only().bill(p_end)
    # The interval labelled 2024-02-01 00:00 (end) belongs to January.
    assert list(out.index.astype(str)) == ["2024-01"]
    assert out["energy_cost"].iloc[0] == 744.0  # 31 d x 24 h
    # Read with the wrong label, the last hour spills into February.
    spill = _energy_only().bill(_profile(ends, label="start"))
    assert list(spill["energy_cost"]) == [743.0, 1.0]


def test_legacy_bill_label_argument():
    ends = pd.date_range("2024-01-01 01:00", "2024-02-01 00:00", freq="h", tz=NY)
    df = pd.DataFrame({"kW": 1.0}, index=ends)
    out = _energy_only().bill(df, interval="1h", label="end")
    assert out["energy_cost"].iloc[0] == 744.0


# ─────────────────────────── gaps, duplicates, order ─────────────────────────────
def test_missing_intervals_rejected_by_default_and_never_stretched():
    idx = pd.date_range("2024-01-01", "2024-01-01 23:45", freq="15min", tz=NY)
    holed = idx.delete([10, 11, 50])
    with pytest.raises(LoadDataError, match="3 missing interval"):
        _profile(holed, interval="15min")
    p = _profile(holed, interval="15min", on_gap="allow")
    assert p.total_kwh == (96 - 3) * 0.25
    assert [g.n_intervals for g in p.gaps] == [2, 1]
    assert p.gaps[0].start == idx[10] and p.gaps[0].end == idx[12]


def test_duplicate_instants_rejected():
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz=NY)
    dup = idx.append(idx[[2]]).sort_values()
    with pytest.raises(LoadDataError, match="duplicate"):
        _profile(dup)


def test_same_instant_in_different_offsets_is_a_duplicate():
    a = pd.Timestamp("2024-01-01 05:00", tz="UTC")
    b = pd.Timestamp("2024-01-01 00:00", tz=NY)  # the same instant
    idx = pd.DatetimeIndex([a, b.tz_convert("UTC")])
    with pytest.raises(LoadDataError, match="duplicate"):
        _profile(idx)


def test_unsorted_rejected_unless_sort_true():
    idx = pd.date_range("2024-01-01", periods=6, freq="h", tz=NY)
    shuffled = idx[[3, 0, 5, 1, 4, 2]]
    vals = pd.Series([3.0, 0.0, 5.0, 1.0, 4.0, 2.0], index=shuffled)
    with pytest.raises(LoadDataError, match="not sorted"):
        LoadProfile.from_series(vals, quantity="kW", interval="1h", label="start")
    p = LoadProfile.from_series(vals, quantity="kW", interval="1h", label="start", sort=True)
    assert list(p.kw) == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    assert p.start.equals(idx)


def test_empty_rejected_and_single_interval_allowed():
    empty = pd.Series([], index=pd.DatetimeIndex([], tz=NY), dtype="float64")
    with pytest.raises(LoadDataError, match="empty"):
        LoadProfile.from_series(empty, quantity="kW", interval="1h", label="start")
    one = _profile(
        pd.DatetimeIndex([pd.Timestamp("2024-05-01 13:00", tz=NY)]), 3.0, interval="30min"
    )
    assert one.total_kwh == 1.5


def test_legacy_bill_cannot_infer_interval_from_one_row():
    df = pd.DataFrame({"kW": [1.0]}, index=pd.DatetimeIndex([pd.Timestamp("2024-05-01", tz=NY)]))
    with pytest.raises(LoadDataError, match="interval="):
        _energy_only().bill(df)
    assert _energy_only().bill(df, interval="1h")["energy_cost"].iloc[0] == 1.0


# ─────────────────────────── value validation ────────────────────────────────────
@pytest.mark.parametrize(
    ("bad", "match"),
    [
        (np.nan, "NaN or infinite"),
        (np.inf, "NaN or infinite"),
        (-np.inf, "NaN or infinite"),
        ("abc", "numeric"),
        (-1.0, "negative"),
    ],
)
def test_invalid_values_rejected(bad, match):
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz=NY)
    vals = pd.Series([1.0, bad, 1.0], index=idx, dtype=object)
    with pytest.raises(LoadDataError, match=match):
        LoadProfile.from_series(vals, quantity="kW", interval="1h", label="start")


def test_boolean_values_rejected():
    idx = pd.date_range("2024-01-01", periods=2, freq="h", tz=NY)
    with pytest.raises(LoadDataError, match="boolean"):
        LoadProfile.from_series(
            pd.Series([True, False], index=idx), quantity="kW", interval="1h", label="start"
        )


@pytest.mark.parametrize("interval", ["7min", "2h", "0min", "-15min", "soon", "45min"])
def test_invalid_interval_rejected(interval):
    idx = pd.date_range("2024-01-01", periods=2, freq="h", tz=NY)
    with pytest.raises(LoadDataError, match="interval"):
        _profile(idx, interval=interval)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"quantity": "kw"}, "quantity"),
        ({"label": "middle"}, "label"),
        ({"on_gap": "fill"}, "on_gap"),
    ],
)
def test_invalid_options_rejected(kwargs, match):
    idx = pd.date_range("2024-01-01", periods=2, freq="h", tz=NY)
    args = {"quantity": "kW", "interval": "1h", "label": "start", **kwargs}
    with pytest.raises(LoadDataError, match=match):
        LoadProfile.from_series(_kw(idx), **args)


# ─────────────────────────── alignment ───────────────────────────────────────────
@pytest.mark.parametrize(
    ("first", "interval"),
    [
        ("2024-01-01 00:07", "15min"),
        ("2024-01-01 00:15", "30min"),
        ("2024-01-01 00:30", "1h"),
        ("2024-01-01 00:00:30", "15min"),
    ],
)
def test_misaligned_grid_rejected(first, interval):
    idx = pd.date_range(first, periods=4, freq=interval, tz=NY)
    with pytest.raises(LoadDataError, match="not aligned"):
        _profile(idx, interval=interval)


def test_spacing_not_matching_interval_is_a_gap_not_a_stretch():
    # Hourly timestamps declared as 15-minute intervals: 3 of every 4 missing.
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz=NY)
    with pytest.raises(LoadDataError, match="6 missing interval"):
        _profile(idx, interval="15min")


# ─────────────────────────── timezones and DST ───────────────────────────────────
def test_naive_rejected_by_default():
    idx = pd.date_range("2024-01-01", periods=3, freq="h")
    with pytest.raises(LoadDataError, match="naive"):
        _profile(idx)


def test_localize_requires_explicit_policies():
    idx = pd.date_range("2024-01-01", periods=3, freq="h")
    with pytest.raises(LoadDataError, match="ambiguous"):
        _profile(idx, localize_tz=NY)
    p = _profile(idx, localize_tz=NY, ambiguous="raise", nonexistent="raise")
    assert str(p.start.tz) == NY


def test_localize_nonexistent_spring_forward_time_raises():
    # 2024-03-10 02:00-02:59 does not exist in New York.
    idx = pd.DatetimeIndex(["2024-03-10 01:00", "2024-03-10 02:00", "2024-03-10 03:00"])
    with pytest.raises(LoadDataError, match="localize"):
        _profile(idx, localize_tz=NY, ambiguous="raise", nonexistent="raise")


def test_localize_ambiguous_fall_back_hour():
    # Wall clock of 2024-11-03 with the repeated 01:00 hour listed twice.
    wall = pd.DatetimeIndex(
        ["2024-11-03 00:00", "2024-11-03 01:00", "2024-11-03 01:00", "2024-11-03 02:00"]
    )
    with pytest.raises(LoadDataError, match="localize"):
        _profile(wall, localize_tz=NY, ambiguous="raise", nonexistent="raise")
    p = _profile(wall, localize_tz=NY, ambiguous="infer", nonexistent="raise")
    assert len(p) == 4 and not p.gaps
    assert list(p.start.strftime("%H:%M%z")) == [
        "00:00-0400",
        "01:00-0400",
        "01:00-0500",
        "02:00-0500",
    ]


def test_localize_rejected_for_aware_input():
    idx = pd.date_range("2024-01-01", periods=2, freq="h", tz=NY)
    with pytest.raises(LoadDataError, match="already timezone-aware"):
        _profile(idx, localize_tz=NY, ambiguous="raise", nonexistent="raise")


@pytest.mark.parametrize(
    ("day", "interval", "expected"),
    [
        ("2024-03-10", "1h", 23),  # spring forward
        ("2024-11-03", "1h", 25),  # fall back
        ("2024-03-10", "15min", 92),
        ("2024-11-03", "15min", 100),
        ("2024-03-10", "30min", 46),
        ("2024-11-03", "30min", 50),
    ],
)
def test_dst_day_interval_counts(day, interval, expected):
    start = pd.Timestamp(day, tz=NY)
    end = start + pd.DateOffset(days=1)  # next local midnight
    idx = pd.date_range(start, end, freq=interval, inclusive="left")
    p = _profile(idx, interval=interval)
    assert len(p) == expected
    assert p.total_kwh == expected * pd.Timedelta(interval) / pd.Timedelta("1h")


def test_repeated_local_hour_kept_distinct():
    idx = pd.date_range("2024-11-03 00:00", periods=4, freq="h", tz=NY)
    p = _profile(idx, 1.0)
    # 01:00 EDT and 01:00 EST are both present and distinct.
    assert list(p.start.strftime("%H:%M%z")) == [
        "00:00-0400",
        "01:00-0400",
        "01:00-0500",
        "02:00-0500",
    ]


def test_utc_and_new_york_inputs_identical():
    idx = pd.date_range("2024-01-01", "2024-12-31 23:00", freq="h", tz=NY)
    rng = np.random.default_rng(1)
    vals = rng.uniform(0, 50, len(idx))
    ny = LoadProfile.from_series(
        pd.Series(vals, index=idx), quantity="kW", interval="1h", label="start"
    )
    utc = LoadProfile.from_series(
        pd.Series(vals, index=idx.tz_convert("UTC")), quantity="kW", interval="1h", label="start"
    )
    assert ny.start.equals(utc.start)
    np.testing.assert_array_equal(ny.kw, utc.kw)
    pd.testing.assert_frame_equal(_energy_only().bill(ny), _energy_only().bill(utc))


def test_leap_february():
    idx = pd.date_range("2024-02-01", "2024-02-29 23:00", freq="h", tz=NY)
    out = _energy_only().bill(_profile(idx))
    assert out["energy_cost"].iloc[0] == 29 * 24
    idx23 = pd.date_range("2023-02-01", "2023-02-28 23:00", freq="h", tz=NY)
    assert _energy_only().bill(_profile(idx23))["energy_cost"].iloc[0] == 28 * 24


# ─────────────────────────── CSV ─────────────────────────────────────────────────
def _write_csv(path, idx, kw):
    pd.DataFrame({"ts": idx, "kW": kw}).to_csv(path, index=False)


def test_csv_mixed_offsets_across_dst(tmp_path):
    idx = pd.date_range("2024-03-09", "2024-03-12", freq="15min", tz=NY, inclusive="left")
    path = tmp_path / "load.csv"
    _write_csv(path, idx, 2.0)
    text = path.read_text()
    assert "-05:00" in text and "-04:00" in text
    p = read_load_csv(path, interval="15min", label="start")
    assert p.start.equals(idx)
    assert p.total_kwh == (3 * 96 - 4) * 0.25 * 2.0  # 3 days minus the skipped hour


def test_csv_round_trip_preserves_energy_and_bill(tmp_path):
    idx = pd.date_range("2024-01-01", "2024-12-31 23:00", freq="h", tz=NY)
    kw = np.round(np.random.default_rng(7).uniform(0, 30, len(idx)), 6)
    path = tmp_path / "load.csv"
    _write_csv(path, idx, kw)
    direct = LoadProfile.from_series(
        pd.Series(kw, index=idx), quantity="kW", interval="1h", label="start"
    )
    loaded = read_load_csv(path, interval="1h", label="start")
    np.testing.assert_array_equal(direct.kw, loaded.kw)
    pd.testing.assert_frame_equal(_energy_only().bill(direct), _energy_only().bill(loaded))


def test_csv_utc_z_timestamps(tmp_path):
    path = tmp_path / "load.csv"
    path.write_text("ts,kW\n2024-07-01T04:00:00Z,1\n2024-07-01T05:00:00Z,1\n")
    p = read_load_csv(path, interval="1h", label="start")
    assert str(p.start[0]) == "2024-07-01 00:00:00-04:00"


def test_csv_naive_rejected_and_mixed_rejected(tmp_path):
    naive = tmp_path / "naive.csv"
    naive.write_text("ts,kW\n2024-01-01 00:00,1\n2024-01-01 01:00,1\n")
    with pytest.raises(LoadDataError, match="naive"):
        read_load_csv(naive, interval="1h", label="start")
    p = read_load_csv(
        naive, interval="1h", label="start", localize_tz=NY, ambiguous="raise", nonexistent="raise"
    )
    assert p.total_kwh == 2.0
    mixed = tmp_path / "mixed.csv"
    mixed.write_text("ts,kW\n2024-01-01 00:00-05:00,1\n2024-01-01 01:00,1\n")
    with pytest.raises(LoadDataError, match="mix"):
        read_load_csv(mixed, interval="1h", label="start")


def test_csv_invalid_and_empty_timestamps(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("ts,kW\n2024-01-01 00:00-05:00,1\nnot a time-05:00,1\n")
    with pytest.raises(LoadDataError):
        read_load_csv(bad, interval="1h", label="start")
    blank = tmp_path / "blank.csv"
    blank.write_text("ts,kW\n2024-01-01 00:00-05:00,1\n,1\n")
    with pytest.raises(LoadDataError, match="empty timestamp"):
        read_load_csv(blank, interval="1h", label="start")


def test_csv_missing_value_rejected(tmp_path):
    path = tmp_path / "load.csv"
    path.write_text("ts,kW\n2024-01-01 00:00-05:00,1\n2024-01-01 01:00-05:00,\n")
    with pytest.raises(LoadDataError, match=r"numeric|NaN"):
        read_load_csv(path, interval="1h", label="start")


def test_csv_missing_column(tmp_path):
    path = tmp_path / "load.csv"
    path.write_text("time,kw\n2024-01-01 00:00-05:00,1\n")
    with pytest.raises(LoadDataError, match="not found"):
        read_load_csv(path, interval="1h", label="start")


# ─────────────────────────── n_customers ─────────────────────────────────────────
@pytest.mark.parametrize("bad", [0, -1, 1.5, True, "2", None])
def test_n_customers_validated(bad):
    idx = pd.date_range("2024-01-01", periods=2, freq="h", tz=NY)
    with pytest.raises(LoadDataError, match="n_customers"):
        _energy_only().bill(pd.DataFrame({"kW": 1.0}, index=idx), n_customers=bad)


# ─────────────────────────── immutability ────────────────────────────────────────
def test_profile_values_are_read_only():
    p = _profile(pd.date_range("2024-01-01", periods=2, freq="h", tz=NY))
    with pytest.raises(ValueError):
        p.kw[0] = 5.0


# ─────────────────────────── property tests ──────────────────────────────────────
@pytest.mark.parametrize("seed", range(25))
def test_energy_equals_sum_kw_times_duration_random_grids(seed):
    """Seeded random grids: energy == sum(kW) x duration (offline, no Hypothesis)."""
    rng = np.random.default_rng(seed)
    interval = ["5min", "15min", "30min", "1h"][seed % 4]
    step = pd.Timedelta(interval)
    n = int(rng.integers(1, 3000))
    # A random aligned start between 2019 and 2035, often near a DST change.
    base = pd.Timestamp("2019-01-01", tz=NY) + pd.Timedelta(days=int(rng.integers(0, 6000)))
    idx = pd.date_range(base, periods=n, freq=interval)
    kw = rng.uniform(0, 1000, n)
    p = LoadProfile.from_series(
        pd.Series(kw, index=idx), quantity="kW", interval=interval, label="start"
    )
    expected = kw.sum() * (step / pd.Timedelta("1h"))
    assert p.total_kwh == pytest.approx(expected, rel=1e-12)
    assert np.all(np.diff(p.start.as_unit("ns").asi8) == step.value)


def test_energy_property_hypothesis():
    hypothesis = pytest.importorskip("hypothesis")
    st = pytest.importorskip("hypothesis.strategies")

    @hypothesis.settings(max_examples=200, deadline=None)
    @hypothesis.given(
        interval=st.sampled_from(["5min", "15min", "30min", "1h"]),
        day=st.integers(min_value=0, max_value=6000),
        slot=st.integers(min_value=0, max_value=287),
        kw=st.lists(
            st.floats(min_value=0, max_value=1e6, allow_nan=False), min_size=1, max_size=500
        ),
    )
    def check(interval, day, slot, kw):
        step = pd.Timedelta(interval)
        base = pd.Timestamp("2019-01-01", tz="UTC") + pd.Timedelta(days=day)
        base = base + (slot * pd.Timedelta("5min")) // step * step  # aligned
        idx = pd.date_range(base, periods=len(kw), freq=interval)
        p = LoadProfile.from_series(
            pd.Series(kw, index=idx), quantity="kW", interval=interval, label="start"
        )
        assert p.total_kwh == pytest.approx(
            sum(kw) * (step / pd.Timedelta("1h")), rel=1e-12, abs=1e-9
        )

    check()


@pytest.mark.parametrize("interval", ["5min", "15min", "30min", "1h"])
def test_aligned_intervals_never_cross_a_calendar_month(interval):
    # R1: with aligned grids no interval straddles a month boundary in New York
    # time, so assigning an interval to the month of its start is exact.
    idx = pd.date_range("2024-01-01", "2025-01-01", freq=interval, tz=NY, inclusive="left")
    p = _profile(idx, interval=interval)
    last_instant = p.end - pd.Timedelta(1, unit="ns")
    assert (p.start.month == last_instant.month).all()
