"""Utilities for summarising the available rate schedules."""

from __future__ import annotations

from calendar import month_abbr
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from .loader import load_all
from .models import DemandCharge, EnergyCharge, TimeWindow

if TYPE_CHECKING:  # pragma: no cover
    from great_tables import GT


__all__ = [
    "rate_schedule_summary_dataframe",
    "rate_schedule_summary_table",
]


def _month_text(months: Iterable[int] | None) -> str:
    if not months:
        return "All months"
    # convert to e.g. "Jan, Feb, Mar"
    return ", ".join(month_abbr[m] for m in months)


def _window_summary(window: TimeWindow) -> str:
    parts: list[str] = []

    months = _month_text(window.months)
    if months != "All months":
        parts.append(months)

    if window.weekdays_only is True:
        parts.append("Weekdays")
    elif window.weekdays_only is False:
        parts.append("Weekends")

    if window.start is not None or window.end is not None:
        start = window.start.strftime("%H:%M") if window.start else "00:00"
        end = window.end.strftime("%H:%M") if window.end else "24:00"
        parts.append(f"{start}–{end}")

    if window.include_holidays:
        parts.append("Incl. holidays")
    elif parts:  # only specify exclusion when other filters are present
        parts.append("Excl. holidays")

    return ", ".join(parts) if parts else "All hours"


def _summarise_demand(charges: Iterable[DemandCharge]) -> str:
    formatted = [f"{charge.rate:.2f} $/kW ({_window_summary(charge.window)})" for charge in charges]
    return "; ".join(formatted) if formatted else "None"


def _summarise_energy(charges: Iterable[EnergyCharge]) -> str:
    formatted = [
        f"{charge.rate:.2f} ¢/kWh ({_window_summary(charge.window)})" for charge in charges
    ]
    return "; ".join(formatted) if formatted else "None"


def rate_schedule_summary_dataframe(tariff_dir: Path | None = None) -> pd.DataFrame:
    """Return a tidy summary of all available rate schedules."""

    if tariff_dir is None:
        tariff_dir = Path(__file__).with_name("tariffs")

    schedules = sorted(load_all(tariff_dir), key=lambda rs: rs.code)

    rows = []
    for schedule in schedules:
        rows.append(
            {
                "Rate code": schedule.code,
                "Customer charge ($/month)": schedule.customer_charge,
                "Supply charge (¢/kWh)": schedule.supply_charge,
                "Merchant charge (¢/kWh)": schedule.merchant_charge,
                "Delivery demand ($/kW)": _summarise_demand(schedule.demand_components),
                "Supply demand ($/kW)": _summarise_demand(schedule.demand_supply),
                "Energy charges (¢/kWh)": _summarise_energy(schedule.energy_components),
            }
        )

    return pd.DataFrame(rows)


def rate_schedule_summary_table(tariff_dir: Path | None = None) -> GT:
    """Build a :class:`great_tables.GT` table describing all rate schedules.

    Requires the optional ``great_tables`` dependency (``coned_billing[report]``).
    """

    try:
        from great_tables import GT
    except ImportError as exc:  # optional dependency (extra "report")
        raise ImportError(
            "rate_schedule_summary_table() needs the optional 'great_tables' package. "
            "Install it with: pip install 'coned_billing[report]'. "
            "rate_schedule_summary_dataframe() returns the same data without it."
        ) from exc

    df = rate_schedule_summary_dataframe(tariff_dir)
    table = (
        GT(df)
        .tab_header(title="Con Edison Rate Schedule Summary")
        .fmt_currency(columns=["Customer charge ($/month)"], currency="USD")
        .fmt_number(columns=["Supply charge (¢/kWh)", "Merchant charge (¢/kWh)"], decimals=4)
    )
    return table
