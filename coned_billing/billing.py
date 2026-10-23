from __future__ import annotations

from pathlib import Path

import pandas as pd

from .load import Label, read_load_csv
from .loader import load_rate


def bill(
    load_csv: str,
    tariff_yml: str,
    *,
    interval: str | pd.Timedelta = "1h",
    label: Label = "start",
) -> pd.DataFrame:
    """Bill a CSV with columns ``ts`` (timestamp with UTC offset) and ``kW``.

    ``interval`` and ``label`` describe the timestamps; the defaults keep the
    pre-WP1 convention (hourly, interval-start). Mixed UTC offsets across DST
    are handled.
    """
    profile = read_load_csv(load_csv, interval=interval, label=label, ts_col="ts", value_col="kW")
    schedule = load_rate(Path(tariff_yml))
    return schedule.bill(profile)
