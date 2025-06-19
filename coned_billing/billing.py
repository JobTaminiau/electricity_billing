from pathlib import Path
import pandas as pd

from .loader import load_rate


def bill(load_csv: str, tariff_yml: str) -> pd.DataFrame:
    df = pd.read_csv(load_csv, parse_dates=["ts"])
    schedule = load_rate(Path(tariff_yml))
    return schedule.bill(df, kw_col="kW", ts_col="ts")
