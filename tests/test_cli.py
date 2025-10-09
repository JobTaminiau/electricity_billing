import sys
from pathlib import Path

import pandas as pd

from coned_billing import cli


def _create_tariff(path: Path) -> None:
    path.write_text(
        """
code: CLI
customer_charge: 5.0
demand_delivery: []
demand_supply: []
energy:
  - rate: 12.0
    window:
      start: "00:00"
supply_charge: 1.0
merchant_charge: 0.5
"""
    )


def _create_load_csv(path: Path) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "ts": pd.date_range(
                "2023-08-01",
                periods=3,
                freq="H",
                tz="America/New_York",
            ),
            "kW": [1.0, 1.0, 1.0],
        }
    )
    df.to_csv(path, index=False)
    return df


def test_cli_prints_to_stdout(monkeypatch, capsys, tmp_path):
    load_csv = tmp_path / "load.csv"
    tariff = tmp_path / "tariff.yml"
    _create_load_csv(load_csv)
    _create_tariff(tariff)

    monkeypatch.setenv("PYTHONHASHSEED", "0")
    monkeypatch.setattr(sys, "argv", ["coned-billing", str(load_csv), str(tariff)])

    cli.main()
    captured = capsys.readouterr()

    assert "energy_cost" in captured.out
    assert "total" in captured.out


def test_cli_writes_to_file(monkeypatch, tmp_path):
    load_csv = tmp_path / "load.csv"
    tariff = tmp_path / "tariff.yml"
    output = tmp_path / "out.csv"
    _create_load_csv(load_csv)
    _create_tariff(tariff)

    monkeypatch.setattr(
        sys,
        "argv",
        ["coned-billing", str(load_csv), str(tariff), "--out", str(output)],
    )

    cli.main()

    assert output.exists()
    content = output.read_text()
    assert "energy_cost" in content
    assert "total" in content
