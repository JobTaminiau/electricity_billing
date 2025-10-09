import pandas as pd

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

    # Ensure all known tariffs are present once.
    codes = set(df["Rate code"])
    assert codes == {
        "SC-1-RES-NYC-RATE-1",
        "SC-2-GEN-NYC-RATE-1",
        "SC-9-GEN-NYC-RATE-1-LT",
        "SC-9-GEN-NYC-RATE-1-HT",
        "SC-9-GEN-NYC-RATE-2-LT",
    }

    # Spot check a few values to ensure the summary contains the expected text.
    sc1 = df.loc[df["Rate code"] == "SC-1-RES-NYC-RATE-1"].iloc[0]
    assert sc1["Delivery demand ($/kW)"] == "None"
    assert "16.11" in sc1["Energy charges (¢/kWh)"]

    sc9_rate2 = df.loc[df["Rate code"] == "SC-9-GEN-NYC-RATE-2-LT"].iloc[0]
    assert "Weekdays" in sc9_rate2["Delivery demand ($/kW)"]
    assert "00:00" not in sc9_rate2["Delivery demand ($/kW)"]


def test_rate_schedule_summary_table_has_dataframe():
    table = rate_schedule_summary_table()

    # The helper attaches the dataframe to the GT instance for introspection/testing.
    df = getattr(table, "_source_df")
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
