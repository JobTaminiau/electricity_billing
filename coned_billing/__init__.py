from importlib.metadata import PackageNotFoundError, version as _version

from .models import TimeWindow, DemandCharge, EnergyCharge, RateSchedule
from .loader import load_rate, load_all
from .summary import rate_schedule_summary_dataframe, rate_schedule_summary_table

__all__ = [
    "TimeWindow",
    "DemandCharge",
    "EnergyCharge",
    "RateSchedule",
    "load_rate",
    "load_all",
    "rate_schedule_summary_dataframe",
    "rate_schedule_summary_table",
]

try:
    __version__: str = _version(__name__)      # normal case: installed package
except PackageNotFoundError:                   # source checkout / CI w-o install
    __version__ = "0+dev"
