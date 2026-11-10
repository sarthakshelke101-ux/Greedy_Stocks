from datetime import date

import pytest

from analytics.phase4_historical_coverage import (
    classify_history,
    subtract_years,
)


def test_subtract_ten_years():
    assert subtract_years(date(2026, 11, 9), 10) == date(2016, 11, 9)


def test_subtract_years_handles_leap_day():
    assert subtract_years(date(2024, 2, 29), 1) == date(2023, 2, 28)


def test_full_observed_span():
    assert classify_history(
        date(2016, 11, 9),
        date(2026, 11, 9),
        date(2016, 11, 9),
        date(2026, 11, 9),
    ) == "10Y_DATE_SPAN_OBSERVED"


def test_partial_history():
    assert classify_history(
        date(2018, 1, 1),
        date(2026, 11, 9),
        date(2016, 11, 9),
        date(2026, 11, 9),
    ) == "PARTIAL_10Y_HISTORY"


def test_stale_history():
    assert classify_history(
        date(2010, 1, 1),
        date(2015, 1, 1),
        date(2016, 11, 9),
        date(2026, 11, 9),
    ) == "STALE_HISTORY"


def test_history_ending_before_as_of():
    assert classify_history(
        date(2016, 11, 9),
        date(2026, 10, 30),
        date(2016, 11, 9),
        date(2026, 11, 9),
    ) == "HISTORY_ENDS_BEFORE_AS_OF"


def test_no_history():
    assert classify_history(
        None, None, date(2016, 11, 9), date(2026, 11, 9)
    ) == "NO_PRICE_HISTORY"


@pytest.mark.parametrize("years", [0, -1, 51])
def test_invalid_years_rejected(years):
    from analytics.phase4_historical_coverage import audit_historical_coverage

    with pytest.raises(ValueError):
        audit_historical_coverage(db_engine=object(), years=years)
