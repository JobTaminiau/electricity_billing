import sys

import pytest

from coned_billing.summary import rate_schedule_summary_dataframe, rate_schedule_summary_table


def test_rate_schedule_summary_dataframe_contents():
    df = rate_schedule_summary_dataframe()

    expected_columns = {
        "Rate code",
        "Customer charge ($/month)",
        "Supply charge (¢/kWh)",
        "Merchant charge (¢/kWh)",
        "Delivery demand ($/kW)",
        "Supply demand ($/kW)",
        "Energy charges (¢/kWh)",
    }
    assert set(df.columns) == expected_columns

    # Explicit list of the bundled tariffs, each present exactly once. Kept
    # independent of the tariff directory so a lost or added file is noticed.
    assert sorted(df["Rate code"]) == [
        "SC-1-RES-NYC-RATE-1",
        "SC-2-GEN-NYC-RATE-1",
        "SC-8-MULTIDWELL-NYC-RATE-1-LT",
        "SC-9-GEN-NYC-RATE-1-HT",
        "SC-9-GEN-NYC-RATE-1-LT",
        "SC-9-GEN-NYC-RATE-2-LT",
    ]

    # Spot check a few values to ensure the summary contains the expected text.
    sc1 = df.loc[df["Rate code"] == "SC-1-RES-NYC-RATE-1"].iloc[0]
    assert sc1["Delivery demand ($/kW)"] == "None"
    assert "16.11" in sc1["Energy charges (¢/kWh)"]

    sc9_rate2 = df.loc[df["Rate code"] == "SC-9-GEN-NYC-RATE-2-LT"].iloc[0]
    assert "Weekdays" in sc9_rate2["Delivery demand ($/kW)"]
    assert "00:00" not in sc9_rate2["Delivery demand ($/kW)"]


def test_rate_schedule_summary_table_renders():
    pytest.importorskip("great_tables")
    from great_tables import GT

    table = rate_schedule_summary_table()
    assert isinstance(table, GT)


def test_rate_schedule_summary_table_without_great_tables(monkeypatch):
    # A None entry in sys.modules makes ``import great_tables`` raise ImportError.
    monkeypatch.setitem(sys.modules, "great_tables", None)
    with pytest.raises(ImportError, match=r"coned_billing\[report\]"):
        rate_schedule_summary_table()
