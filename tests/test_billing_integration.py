from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from coned_billing.billing import bill


def _write_simple_tariff(path: Path) -> None:
    path.write_text(
        """
code: TEST
customer_charge: 12.5
demand_delivery:
  - rate: 7.5
    window:
      start: "00:00"
demand_supply: []
energy:
  - rate: 15.0
    window:
      start: "00:00"
supply_charge: 1.5
merchant_charge: 0.5
"""
    )


def _write_load_csv(path: Path) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "ts": pd.date_range(
                "2023-06-01",
                periods=4,
                freq="H",
                tz="America/New_York",
            ),
            "kW": [1.0, 2.0, 3.0, 4.0],
        }
    )
    df.to_csv(path, index=False)
    return df


def test_bill_reads_files_and_returns_dataframe(tmp_path):
    load_csv = tmp_path / "load.csv"
    tariff = tmp_path / "tariff.yml"

    df = _write_load_csv(load_csv)
    _write_simple_tariff(tariff)

    result = bill(str(load_csv), str(tariff))

    assert list(result.columns) == [
        "energy_cost",
        "demand_cost",
        "demand_supply_cost",
        "kW",
        "customer_charge",
        "total",
    ]
    assert result.index.dtype.name == "period[M]"

    period = result.index[0]
    kwh = df["kW"].sum()  # hourly samples → 1 kWh each
    expected_energy = kwh * (15.0 + 1.5 + 0.5) / 100.0
    expected_demand = 7.5 * df["kW"].max()

    assert result.loc[period, "energy_cost"] == pytest.approx(expected_energy)
    assert result.loc[period, "demand_cost"] == pytest.approx(expected_demand)
    assert result.loc[period, "total"] == pytest.approx(
        expected_energy + expected_demand + result.loc[period, "customer_charge"]
    )
