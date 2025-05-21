import pandas as pd
from pandas.tseries.holiday import AbstractHolidayCalendar, Holiday, MO

__all__ = ["is_coned_holiday", "_CONED_HOLIDAYS"]


# ──────────────────────────────────── holidays ───────────────────────────────────
class ConEdHolidayCalendar(AbstractHolidayCalendar):
    rules = (
        Holiday("NewYears", month=1, day=1),
        Holiday("MemorialDay", month=5, day=31, offset=pd.DateOffset(weekday=MO(-1))),
        Holiday("IndependenceDay", month=7, day=4),
        Holiday("LaborDay", month=9, day=1, offset=pd.DateOffset(weekday=MO(+1))),
        Holiday("Thanksgiving", month=11, day=1, offset=pd.DateOffset(weekday=3)),
        Holiday("Christmas", month=12, day=25),
    )


_CONED_HOLIDAYS: set[pd.Timestamp] = {
    pd.Timestamp(h).normalize() for h in ConEdHolidayCalendar().holidays("2020", "2030")
}


def is_coned_holiday(ts: pd.Timestamp) -> bool:
    """Vector‐friendly check."""
    return ts.normalize().isin(_CONED_HOLIDAYS)
