from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from .loader import load_all, load_rate
from .models import DemandCharge, EnergyCharge, RateSchedule, TimeWindow
from .summary import rate_schedule_summary_dataframe, rate_schedule_summary_table

__all__ = [
    "DemandCharge",
    "EnergyCharge",
    "RateSchedule",
    "TimeWindow",
    "load_all",
    "load_rate",
    "rate_schedule_summary_dataframe",
    "rate_schedule_summary_table",
]

try:
    __version__: str = _version(__name__)  # normal case: installed package
except PackageNotFoundError:  # source checkout / CI w-o install
    __version__ = "0+dev"
