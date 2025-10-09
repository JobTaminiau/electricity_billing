import pandas as pd

from coned_billing.calendars import _CONED_HOLIDAYS, is_coned_holiday


def test_is_coned_holiday_datetime_index():
    idx = pd.DatetimeIndex([
        "2023-01-01",  # New Year's Day – holiday
        "2023-01-03",  # Ordinary weekday
    ])

    result = is_coned_holiday(idx)

    assert list(result) == [True, False]


def test_is_coned_holiday_index_membership():
    reference_holiday = min(_CONED_HOLIDAYS)
    idx = pd.DatetimeIndex([
        reference_holiday - pd.Timedelta(days=1),
        reference_holiday,
        reference_holiday + pd.Timedelta(days=1),
    ])

    result = is_coned_holiday(idx)

    assert result.tolist() == [False, True, False]

    # All dates marked as holidays must exist in the cached lookup set
    normalized_holidays = idx[result].normalize()
    assert all(ts in _CONED_HOLIDAYS for ts in normalized_holidays)
