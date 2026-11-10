
from __future__ import annotations

import math
import numbers
from typing import Any

import pandas as pd

from financial_metrics import calculate_metrics


def _validate_positive_integer(value: int, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, numbers.Integral)
        or value <= 0
    ):
        raise ValueError(f"{name} must be a positive integer.")


def _validate_risk_free_rate(rate: float) -> None:
    if (
        isinstance(rate, bool)
        or not isinstance(rate, numbers.Real)
        or not math.isfinite(float(rate))
        or rate <= -1
    ):
        raise ValueError(
            "Annual risk-free rate must be finite and greater than -100%."
        )


def _validate_datetime_index(index: pd.Index, name: str) -> None:
    if not isinstance(index, pd.DatetimeIndex):
        raise ValueError(f"{name} must use a DatetimeIndex.")

    if index.hasnans:
        raise ValueError(f"{name} cannot contain NaT dates.")

    if index.has_duplicates:
        raise ValueError(f"Duplicate {name} dates found.")


def _validate_matching_timezones(
    first: pd.DatetimeIndex,
    second: pd.DatetimeIndex,
) -> None:
    first_tz = str(first.tz) if first.tz is not None else None
    second_tz = str(second.tz) if second.tz is not None else None

    if first_tz != second_tz:
        raise ValueError(
            "Portfolio and benchmark dates must use the same timezone."
        )


def _validate_finite_numeric_series(
    values: pd.Series,
    name: str,
) -> pd.Series:
    result = pd.to_numeric(values, errors="coerce")

    numeric_values = result.dropna()

    if not numeric_values.map(
        lambda value: math.isfinite(float(value))
    ).all():
        raise ValueError(f"{name} must contain only finite values.")

    return result.astype(float)


def validate_portfolio(
    symbols: list[str],
    sectors: dict[str, str],
    max_stocks: int = 10,
    max_per_sector: int = 3,
) -> None:
    """Validate the stock selection and sector constraints."""

    _validate_positive_integer(max_stocks, "max_stocks")
    _validate_positive_integer(max_per_sector, "max_per_sector")

    if not isinstance(symbols, (list, tuple)):
        raise ValueError("symbols must be a list or tuple.")

    if not isinstance(sectors, dict):
        raise ValueError("sectors must be a dictionary.")

    if not symbols:
        raise ValueError("Select at least one stock.")

    if any(
        not isinstance(symbol, str) or not symbol.strip()
        for symbol in symbols
    ):
        raise ValueError("Stock symbols must be non-empty strings.")

    if len(symbols) != len(set(symbols)):
        raise ValueError("Duplicate stock symbols are not allowed.")

    if len(symbols) > max_stocks:
        raise ValueError(
            f"Portfolio cannot contain more than {max_stocks} stocks."
        )

    missing = [symbol for symbol in symbols if symbol not in sectors]

    if missing:
        raise ValueError(
            f"Missing sector information for: {missing}"
        )

    invalid_sectors = [
        symbol
        for symbol in symbols
        if not isinstance(sectors[symbol], str)
        or not sectors[symbol].strip()
    ]

    if invalid_sectors:
        raise ValueError(
            f"Invalid sector information for: {invalid_sectors}"
        )

    sector_counts = pd.Series(
        [sectors[symbol] for symbol in symbols]
    ).value_counts()

    violations = sector_counts[
        sector_counts > max_per_sector
    ]

    if not violations.empty:
        raise ValueError(
            f"Maximum {max_per_sector} stocks per sector exceeded: "
            f"{violations.to_dict()}"
        )


def calculate_portfolio(
    prices,
    sectors,
    symbols=None,
    risk_free_rate=0.0,
    max_stocks=10,
    max_per_sector=3,
    price_basis="RAW_CLOSE_UNADJUSTED",
    return_type="PRICE_RETURN",
) -> dict[str, Any]:
    """
    Calculate an equal-weight, daily-rebalanced portfolio.

    Input:
        prices: Date-indexed closing prices, one column per stock.
        sectors: Mapping of stock symbol to sector.
        symbols: Selected stock symbols. Defaults to all price columns.
        risk_free_rate: Annual risk-free rate for Sharpe ratio.
        max_stocks: Maximum number of stocks in the portfolio.
        max_per_sector: Maximum number of stocks per sector.
        price_basis: Basis for price calculations.
        return_type: Type of returns to calculate.

    Missing observations are not filled. Only dates with valid returns
    for every selected stock are used.

    Equal weights are reset every session, representing daily
    rebalancing rather than buy-and-hold.
    """

    _validate_risk_free_rate(risk_free_rate)
    _validate_positive_integer(max_stocks, "max_stocks")
    _validate_positive_integer(max_per_sector, "max_per_sector")

    if not isinstance(prices, pd.DataFrame):
        raise ValueError("prices must be a pandas DataFrame.")

    if prices.empty:
        raise ValueError("Price dataset is empty.")

    if not isinstance(price_basis, str) or not price_basis.strip():
        raise ValueError("price_basis must be a non-empty string.")

    if not isinstance(return_type, str) or not return_type.strip():
        raise ValueError("return_type must be a non-empty string.")

    selected = (
        list(prices.columns)
        if symbols is None
        else list(symbols)
    )

    validate_portfolio(
        selected,
        sectors,
        max_stocks=max_stocks,
        max_per_sector=max_per_sector,
    )

    missing_columns = [
        symbol for symbol in selected
        if symbol not in prices.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Price columns missing for: {missing_columns}"
        )

    data = prices[selected].copy()

    try:
        converted_index = pd.DatetimeIndex(
            pd.to_datetime(data.index, errors="raise")
        )
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "Portfolio dates must be valid datetime values."
        ) from exc

    _validate_datetime_index(converted_index, "portfolio trading")

    data.index = converted_index
    data = data.sort_index()

    data = data.apply(
        lambda column: pd.to_numeric(column, errors="coerce")
    )

    # Missing observations remain missing; never forward-fill them.
    values = data.to_numpy(dtype=float)
    observed_values = values[~pd.isna(values)]

    if not all(math.isfinite(float(value)) for value in observed_values):
        raise ValueError("Observed prices must be finite.")

    if (observed_values <= 0).any():
        raise ValueError("Observed prices must be positive.")

    # No forward-fill or synthetic prices.
    stock_returns = data.pct_change(fill_method=None)

    # Require all selected stocks to have valid returns on a date.
    aligned_returns = stock_returns.dropna(how="any")

    if len(aligned_returns) < 2:
        raise ValueError(
            "Insufficient aligned return observations."
        )

    if not aligned_returns.map(
        lambda value: math.isfinite(float(value))
    ).all().all():
        raise ValueError("Portfolio returns must be finite.")

    if (aligned_returns <= -1).any().any():
        raise ValueError(
            "Stock returns cannot be less than or equal to -100%."
        )

    weights = {
        symbol: 1.0 / len(selected)
        for symbol in selected
    }

    # Equal weights are reset every session:
    # daily rebalancing assumption.
    portfolio_returns = aligned_returns.mul(
        pd.Series(weights)
    ).sum(axis=1).rename("portfolio")

    if not portfolio_returns.map(math.isfinite).all():
        raise ValueError("Portfolio returns must be finite.")

    cumulative_values = (
        (1 + portfolio_returns).cumprod() * 100
    )

    if not cumulative_values.map(math.isfinite).all():
        raise ValueError(
            "Portfolio value calculation produced non-finite values."
        )

    # Include the starting portfolio value immediately before
    # the first valid return.
    first_return_date = portfolio_returns.index[0]

    prior_dates = data.index[
        data.index < first_return_date
    ]

    if prior_dates.empty:
        raise ValueError(
            "Cannot establish a starting portfolio value."
        )

    baseline_date = prior_dates[-1]

    portfolio_values = pd.concat([
        pd.Series(
            [100.0],
            index=pd.DatetimeIndex([baseline_date]),
        ),
        cumulative_values,
    ])

    portfolio_values.name = "portfolio_value"

    metrics = calculate_metrics(
        portfolio_values,
        risk_free_rate=risk_free_rate,
        price_basis=price_basis,
        return_type=return_type,
    )

    correlation = aligned_returns.corr()

    sector_weights: dict[str, float] = {}

    for symbol, weight in weights.items():
        sector = sectors[symbol]
        sector_weights[sector] = (
            sector_weights.get(sector, 0.0) + weight
        )

    return {
        "symbols": selected,
        "weights": weights,
        "sector_allocation": sector_weights,
        "portfolio_values": portfolio_values,
        "daily_returns": portfolio_returns,
        "stock_returns": aligned_returns,
        "correlation": correlation,
        "metrics": metrics,
        "metadata": {
            "method": "EQUAL_WEIGHT",
            "rebalancing": "DAILY",
            "risk_free_rate": risk_free_rate,
            "price_basis": price_basis,
            "return_type": return_type,
            "dividend_adjusted": False,
            "corporate_action_coverage": "PARTIAL",
            "input_price_observations": len(data),
            "aligned_return_observations": len(aligned_returns),
            "excluded_return_dates": (
                len(stock_returns) - len(aligned_returns)
            ),
            "missing_values_filled": False,
            "database_writes": False,
        },
    }


def compare_with_benchmark(
    portfolio_returns: pd.Series,
    benchmark_prices: pd.Series,
) -> dict[str, Any]:
    """Compare portfolio and benchmark on common return dates.

    Portfolio returns must be daily simple returns expressed as decimals.
    Benchmark input must contain positive closing prices.
    """

    if not isinstance(portfolio_returns, pd.Series):
        raise ValueError(
            "portfolio_returns must be a pandas Series."
        )

    if not isinstance(benchmark_prices, pd.Series):
        raise ValueError(
            "benchmark_prices must be a pandas Series."
        )

    if portfolio_returns.empty or benchmark_prices.empty:
        raise ValueError(
            "Portfolio returns and benchmark prices cannot be empty."
        )

    _validate_datetime_index(
        portfolio_returns.index,
        "portfolio return",
    )

    _validate_datetime_index(
        benchmark_prices.index,
        "benchmark trading",
    )

    _validate_matching_timezones(
        portfolio_returns.index,
        benchmark_prices.index,
    )

    portfolio = _validate_finite_numeric_series(
        portfolio_returns,
        "Portfolio returns",
    ).sort_index()

    benchmark = _validate_finite_numeric_series(
        benchmark_prices,
        "Benchmark prices",
    ).sort_index()

    if portfolio.isna().any():
        raise ValueError(
            "Portfolio returns cannot contain missing values."
        )

    if (portfolio <= -1).any():
        raise ValueError(
            "Portfolio returns cannot be less than or equal to -100%."
        )

    if benchmark.isna().any() or (benchmark <= 0).any():
        raise ValueError(
            "Benchmark prices must be positive and finite."
        )

    benchmark_returns = benchmark.pct_change(
        fill_method=None
    ).dropna()

    if not benchmark_returns.map(math.isfinite).all():
        raise ValueError("Benchmark returns must be finite.")

    comparison = pd.concat(
        [
            portfolio.rename("portfolio"),
            benchmark_returns.rename("benchmark"),
        ],
        axis=1,
        join="inner",
    ).dropna()

    if len(comparison) < 2:
        raise ValueError(
            "Insufficient common portfolio and benchmark dates."
        )

    portfolio_growth = (
        (1 + comparison["portfolio"]).prod() - 1
    )

    benchmark_growth = (
        (1 + comparison["benchmark"]).prod() - 1
    )

    if not (
        math.isfinite(float(portfolio_growth))
        and math.isfinite(float(benchmark_growth))
    ):
        raise ValueError(
            "Benchmark comparison produced non-finite returns."
        )

    return {
        "portfolio_return_pct": float(
            portfolio_growth * 100
        ),
        "benchmark_return_pct": float(
            benchmark_growth * 100
        ),
        "excess_return_pct": float(
            (portfolio_growth - benchmark_growth) * 100
        ),
        "common_return_observations": len(comparison),
        "comparison_returns": comparison,
        "benchmark_basis": "NIFTY_50_PRICE_RETURN",
    }
