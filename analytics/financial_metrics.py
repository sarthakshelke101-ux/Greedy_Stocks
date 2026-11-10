
"""GREEDY STOCKS — Core financial metrics.

All calculations are historical and descriptive, not forecasts.

When an expected trading calendar is supplied, every expected
session in the requested price series must have a valid price.

No prices are forward-filled or silently bridged across gaps.
Invalid non-positive prices remain excluded from calculations
when no expected calendar is supplied.
"""

from __future__ import annotations

import math
import numbers

import pandas as pd

TRADING_DAYS = 252
MIN_CAGR_RETURN_OBSERVATIONS = 60
MIN_RISK_METRIC_OBSERVATIONS = 2

# Daily return volatility below this threshold is treated as effectively
# zero. This prevents floating-point noise from creating enormous Sharpe
# ratios for constant or near-constant return series.
MIN_DAILY_EXCESS_STD = 1e-12


def _validate_trading_days(trading_days: int) -> None:
    if (
        isinstance(trading_days, bool)
        or not isinstance(trading_days, numbers.Integral)
        or trading_days <= 0
    ):
        raise ValueError("trading_days must be a positive integer.")


def _validate_risk_free_rate(risk_free_rate: float) -> None:
    if (
        isinstance(risk_free_rate, bool)
        or not isinstance(risk_free_rate, numbers.Real)
        or not math.isfinite(float(risk_free_rate))
        or risk_free_rate <= -1
    ):
        raise ValueError(
            "Annual risk-free rate must be finite and greater than -100%."
        )


def _clean_prices(prices: pd.Series) -> pd.Series:
    if not isinstance(prices, pd.Series):
        prices = pd.Series(prices)

    result = pd.to_numeric(prices, errors="coerce")

    if isinstance(result.index, pd.DatetimeIndex):
        if result.index.hasnans:
            raise ValueError("Price dates cannot contain NaT.")
        result = result.sort_index()

    if result.index.has_duplicates:
        raise ValueError("Duplicate price dates are not allowed.")

    # Missing values are permitted, but infinite numeric values are not.
    finite_values = result.dropna().map(
        lambda value: math.isfinite(float(value))
    )

    if not finite_values.all():
        raise ValueError("Prices must be positive and finite.")

    return result.where(result > 0).astype(float)


def _normalise_expected_sessions(
    expected_sessions: pd.DatetimeIndex,
) -> pd.DatetimeIndex:
    expected = pd.DatetimeIndex(expected_sessions)

    if expected.hasnans:
        raise ValueError("Expected trading sessions cannot contain NaT.")

    if expected.has_duplicates:
        raise ValueError("Expected trading sessions cannot contain duplicates.")

    return expected.sort_values()


def _validate_trading_calendar(
    prices: pd.Series,
    expected_sessions: pd.DatetimeIndex | None = None,
) -> None:
    """Require exact coverage of a caller-supplied trading-session calendar."""

    if expected_sessions is None:
        return

    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError(
            "A DatetimeIndex is required when validating trading sessions."
        )

    expected = _normalise_expected_sessions(expected_sessions)

    observed_timezone = prices.index.tz
    expected_timezone = expected.tz

    observed_timezone_name = (
        str(observed_timezone) if observed_timezone is not None else None
    )
    expected_timezone_name = (
        str(expected_timezone) if expected_timezone is not None else None
    )

    if observed_timezone_name != expected_timezone_name:
        raise ValueError(
            "Price dates and expected trading sessions must use "
            "the same timezone."
        )

    observed = prices.dropna().index

    missing = expected.difference(observed)
    unexpected = observed.difference(expected)

    if len(unexpected):
        raise ValueError(
            f"{len(unexpected)} observed dates are outside the expected calendar."
        )

    if len(missing):
        raise ValueError(
            f"{len(missing)} expected trading sessions have missing prices."
        )


def _validated_returns(
    prices: pd.Series,
    expected_sessions: pd.DatetimeIndex | None = None,
) -> tuple[pd.Series, pd.Series]:
    clean = _clean_prices(prices)
    _validate_trading_calendar(clean, expected_sessions)

    if expected_sessions is not None:
        expected = _normalise_expected_sessions(expected_sessions)
        # Exact calendar validation above guarantees all expected sessions
        # exist and are valid. Restrict calculations to that ordered calendar.
        clean = clean.reindex(expected)

    returns = clean.pct_change(fill_method=None).dropna()

    if not returns.map(math.isfinite).all():
        raise ValueError(
            "Calculated returns contain non-finite values. "
            "Check the input price range."
        )

    return clean, returns


def daily_returns(
    prices: pd.Series,
    expected_sessions: pd.DatetimeIndex | None = None,
) -> pd.Series:
    _, returns = _validated_returns(prices, expected_sessions)
    return returns


def period_return(
    prices: pd.Series,
    expected_sessions: pd.DatetimeIndex | None = None,
) -> float | None:
    clean, _ = _validated_returns(prices, expected_sessions)
    clean = clean.dropna()

    if len(clean) < 2:
        return None

    result = (clean.iloc[-1] / clean.iloc[0] - 1) * 100

    return float(result) if math.isfinite(result) else None


def annualized_volatility(
    prices: pd.Series,
    trading_days: int = TRADING_DAYS,
    expected_sessions: pd.DatetimeIndex | None = None,
) -> float | None:
    _validate_trading_days(trading_days)
    returns = daily_returns(prices, expected_sessions)

    if len(returns) < MIN_RISK_METRIC_OBSERVATIONS:
        return None

    result = returns.std(ddof=1) * math.sqrt(trading_days) * 100
    return float(result) if math.isfinite(result) else None


def cagr(
    prices: pd.Series,
    trading_days: int = TRADING_DAYS,
    expected_sessions: pd.DatetimeIndex | None = None,
) -> float | None:
    _validate_trading_days(trading_days)
    clean, returns = _validated_returns(prices, expected_sessions)
    clean = clean.dropna()

    if len(returns) < MIN_CAGR_RETURN_OBSERVATIONS:
        return None

    # This convention assumes observed returns represent consecutive
    # trading sessions. Supply expected_sessions for calendar validation.
    years = len(returns) / trading_days

    result = (clean.iloc[-1] / clean.iloc[0]) ** (1 / years) - 1
    result *= 100

    return float(result) if math.isfinite(result) else None


def maximum_drawdown(
    prices: pd.Series,
    expected_sessions: pd.DatetimeIndex | None = None,
) -> float | None:
    _, returns = _validated_returns(prices, expected_sessions)

    if len(returns) == 0:
        return None

    wealth = (1 + returns).cumprod()
    wealth = pd.concat(
        [pd.Series([1.0]), wealth.reset_index(drop=True)],
        ignore_index=True,
    )
    drawdowns = wealth / wealth.cummax() - 1

    result = drawdowns.min() * 100
    return float(result) if math.isfinite(result) else None


def sharpe_ratio(
    prices: pd.Series,
    risk_free_rate: float = 0.0,
    trading_days: int = TRADING_DAYS,
    expected_sessions: pd.DatetimeIndex | None = None,
) -> float | None:
    """Calculate annualised Sharpe ratio.

    Returns None when daily excess-return volatility is effectively zero.
    This avoids unstable ratios caused by floating-point precision.
    """

    _validate_trading_days(trading_days)
    _validate_risk_free_rate(risk_free_rate)

    returns = daily_returns(prices, expected_sessions)

    if len(returns) < MIN_RISK_METRIC_OBSERVATIONS:
        return None

    daily_rf = (1 + risk_free_rate) ** (1 / trading_days) - 1
    excess = returns - daily_rf
    daily_std = excess.std(ddof=1)

    if (
        not math.isfinite(daily_std)
        or daily_std <= MIN_DAILY_EXCESS_STD
    ):
        return None

    result = excess.mean() / daily_std * math.sqrt(trading_days)

    return float(result) if math.isfinite(result) else None


def calculate_metrics(
    prices: pd.Series,
    risk_free_rate: float = 0.0,
    *,
    price_basis: str = "RAW_CLOSE_UNADJUSTED",
    return_type: str = "PRICE_RETURN",
    expected_sessions: pd.DatetimeIndex | None = None,
) -> dict:
    _validate_risk_free_rate(risk_free_rate)

    if not isinstance(price_basis, str) or not price_basis.strip():
        raise ValueError("price_basis must be a non-empty string.")

    if not isinstance(return_type, str) or not return_type.strip():
        raise ValueError("return_type must be a non-empty string.")

    clean, returns = _validated_returns(prices, expected_sessions)
    valid = clean.dropna()

    result = {
        "start_date": (
            str(valid.index[0].date())
            if len(valid) and isinstance(valid.index, pd.DatetimeIndex)
            else None
        ),
        "end_date": (
            str(valid.index[-1].date())
            if len(valid) and isinstance(valid.index, pd.DatetimeIndex)
            else None
        ),
        "price_observations": int(len(valid)),
        "return_observations": int(len(returns)),
        "period_return_pct": period_return(clean, expected_sessions),
        "cagr_pct": cagr(clean, expected_sessions=expected_sessions),
        "annualized_volatility_pct": annualized_volatility(
            clean, expected_sessions=expected_sessions
        ),
        "maximum_drawdown_pct": maximum_drawdown(
            clean, expected_sessions
        ),
        "sharpe_ratio": sharpe_ratio(
            clean,
            risk_free_rate,
            expected_sessions=expected_sessions,
        ),
        "price_basis": price_basis,
        "return_type": return_type,
        "risk_free_rate_annual": risk_free_rate,
        "trading_days_per_year": TRADING_DAYS,
        "cagr_status": (
            "AVAILABLE"
            if len(returns) >= MIN_CAGR_RETURN_OBSERVATIONS
            else "SUPPRESSED_SHORT_HISTORY"
        ),
        "calendar_validation": (
            "VALIDATED"
            if expected_sessions is not None
            else "NOT_SUPPLIED"
        ),
    }

    return result
