from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from .demand import BilledDemand, MonthlyDemand, billed_demand, billed_demands, contract_demand
from .errors import (
    ConEdBillingError,
    DemandDeterminationError,
    LoadDataError,
    TariffSchemaError,
    TariffSelectionError,
)
from .load import Gap, LoadProfile, read_load_csv
from .loader import load_all, load_rate
from .models import DemandCharge, EnergyCharge, RateSchedule, TimeWindow
from .summary import rate_schedule_summary_dataframe, rate_schedule_summary_table
from .tariff_schema import (
    TariffRegistry,
    TariffVersion,
    default_registry,
    load_tariff_version,
)

__all__ = [
    "BilledDemand",
    "ConEdBillingError",
    "DemandCharge",
    "DemandDeterminationError",
    "EnergyCharge",
    "Gap",
    "LoadDataError",
    "LoadProfile",
    "MonthlyDemand",
    "RateSchedule",
    "TariffRegistry",
    "TariffSchemaError",
    "TariffSelectionError",
    "TariffVersion",
    "TimeWindow",
    "billed_demand",
    "billed_demands",
    "contract_demand",
    "default_registry",
    "load_all",
    "load_rate",
    "load_tariff_version",
    "rate_schedule_summary_dataframe",
    "rate_schedule_summary_table",
    "read_load_csv",
]

try:
    __version__: str = _version(__name__)  # normal case: installed package
except PackageNotFoundError:  # source checkout / CI w-o install
    __version__ = "0+dev"
