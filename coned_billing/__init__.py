from importlib.metadata import PackageNotFoundError, version as _version

from .models import TimeWindow, DemandCharge, EnergyCharge, RateSchedule
from .loader import load_rate, load_all

__all__ = [
    "TimeWindow",
    "DemandCharge",
    "EnergyCharge",
    "RateSchedule",
    "load_rate",
    "load_all",
]

try:
    __version__: str = _version(__name__)      # normal case: installed package
except PackageNotFoundError:                   # source checkout / CI w-o install
    __version__ = "0+dev"
