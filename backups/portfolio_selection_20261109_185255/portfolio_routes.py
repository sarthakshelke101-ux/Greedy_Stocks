"""GREEDY STOCKS ? configurable Greedy V2 portfolio API."""

import logging
import math
import sys
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, FiniteFloat

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.greedy_v2_data import prepare_greedy_v2_dataset
from analytics.greedy_v2_splits import chronological_split
from analytics.greedy_v2_engine import greedy_select_stocks
from analytics.portfolio_analytics import (
    calculate_portfolio,
    compare_with_benchmark,
)
from analytics.portfolio_allocation import allocate_capital

router = APIRouter(tags=["Portfolio"])
logger = logging.getLogger("greedy_stocks_portfolio")


class PortfolioRequest(BaseModel):
    capital: FiniteFloat = Field(gt=0, le=100_000_000_000)
    stock_count: int = Field(default=5, ge=1, le=10)
    training_years: int = Field(default=10, ge=1, le=10)
    max_per_sector: int = Field(default=3, ge=1, le=10)
    risk_free_rate: FiniteFloat = Field(default=0.0, ge=0, le=1)


def _clean(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (date,)):
        return value.isoformat()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _metrics(result):
    return {
        str(key): _clean(value)
        for key, value in result["metrics"].items()
        if isinstance(value, (str, int, float, bool))
        or value is None
    }


@router.post("/portfolio/generate")
def generate_portfolio(request: PortfolioRequest):
    """Generate a capital-constrained portfolio using original Greedy V2."""
    try:
        today = date.today()
        end_date = today.isoformat()
        start_date = (today - timedelta(days=365 * request.training_years)).isoformat()

        dataset = prepare_greedy_v2_dataset(
            start_date=start_date,
            end_date=end_date,
        )

        split = chronological_split(
            dataset.adjusted_prices,
            allow_sparse_evaluation=True,
        )

        # Greedy selection sees training data only.
        selection = greedy_select_stocks(
            train_prices=split.train,
            sectors=dataset.sectors,
            target_stocks=request.stock_count,
            max_per_sector=request.max_per_sector,
            risk_free_rate=request.risk_free_rate,
        )

        symbols = selection["selected_symbols"]

        # Latest raw close is used for executable share quantities.
        latest_prices = {}

        for symbol in symbols:
            raw_column = (
                symbol if symbol in dataset.raw_prices.columns
                else f"{symbol}_RAW"
            )

            if raw_column not in dataset.raw_prices.columns:
                raise ValueError(
                    f"Raw price history unavailable for {symbol} "
                    f"(expected column: {raw_column})."
                )

            available = dataset.raw_prices[raw_column].dropna()

            if available.empty:
                raise ValueError(f"No usable raw price is available for {symbol}.")

            latest_prices[symbol] = float(available.iloc[-1])

        allocation = allocate_capital(
            symbols=symbols,
            prices=latest_prices,
            capital=float(request.capital),
        )

        # Validation-period metrics are kept separate from training selection.
        validation_prices = split.validation
        validation_benchmark = dataset.benchmark_prices.reindex(split.validation.index)

        validation_result = calculate_portfolio(
            prices=validation_prices,
            sectors=dataset.sectors,
            symbols=symbols,
            risk_free_rate=request.risk_free_rate,
            max_stocks=request.stock_count,
            max_per_sector=request.max_per_sector,
            price_basis="SPLIT_BONUS_ADJUSTED",
            return_type="PRICE_RETURN",
        )

        test_prices = split.test
        test_benchmark = dataset.benchmark_prices.reindex(test_prices.index)

        test_result = calculate_portfolio(
            prices=test_prices,
            sectors=dataset.sectors,
            symbols=symbols,
            risk_free_rate=request.risk_free_rate,
            max_stocks=request.stock_count,
            max_per_sector=request.max_per_sector,
            price_basis="SPLIT_BONUS_ADJUSTED",
            return_type="PRICE_RETURN",
        )

        test_comparison = compare_with_benchmark(
            test_result["daily_returns"],
            test_benchmark,
        )

        comparison = compare_with_benchmark(
            validation_result["daily_returns"],
            validation_benchmark,
        )

        holdings = allocation["holdings"]
        for holding in holdings:
            holding["sector"] = dataset.sectors[holding["symbol"]]

        return {
            "status": "success",
            "selection_method": "SEQUENTIAL_GREEDY_SHARPE",
            "portfolio": allocation,
            "holdings": holdings,
            "selection_log": selection["selection_log"].to_dict(
                orient="records"
            ),
            "training": {
                "start": str(split.train.index.min().date()),
                "end": str(split.train.index.max().date()),
                "observations": len(split.train),
                "selection_sharpe": _clean(
                    selection["portfolio_result"]["metrics"].get("sharpe_ratio")
                ),
            },
            "validation": {
                "start": str(validation_prices.index.min().date()),
                "end": str(validation_prices.index.max().date()),
                "observations": len(validation_prices),
                "metrics": _metrics(validation_result),
                "benchmark": {
                    key: _clean(value)
                    for key, value in comparison.items()
                    if key != "comparison_returns"
                },
            },
            "test": {
                "start": str(test_prices.index[1].date()),
                "end": str(test_prices.index[-1].date()),
                "observations": len(test_prices) - 1,
                "metrics": _metrics(test_result),
                "benchmark": {
                    key: _clean(value)
                    for key, value in test_comparison.items()
                    if key != "comparison_returns"
                },
            },
            "data_limitations": {
                "membership_basis": dataset.metadata["membership_basis"],
                "corporate_action_coverage": dataset.metadata[
                    "corporate_action_coverage"
                ],
                "dividend_adjusted": dataset.metadata["dividend_adjusted"],
                "price_basis": dataset.metadata["price_basis"],
                "benchmark_basis": "NIFTY_50_PRICE_RETURN",
                "historical_membership_survivorship_bias": True,
                "historical_metrics_are_daily_rebalanced": True,
                "live_holdings_use_latest_raw_close": True,
            },
            "assumptions": selection["assumptions"],
        }

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Portfolio generation failed.")
        raise HTTPException(
            status_code=500,
            detail="Portfolio generation failed. Check backend logs.",
        ) from exc
"""GREEDY STOCKS - Configurable Greedy V2 portfolio API."""

import logging
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, FiniteFloat

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.greedy_v2_data import prepare_greedy_v2_dataset
from analytics.greedy_v2_splits import chronological_split
from analytics.greedy_v2_engine import greedy_select_stocks
from analytics.portfolio_analytics import (
    calculate_portfolio,
    compare_with_benchmark,
)
from analytics.portfolio_allocation import allocate_capital

router = APIRouter(tags=["Portfolio"])
logger = logging.getLogger("greedy_stocks_portfolio")


class PortfolioRequest(BaseModel):
    capital: FiniteFloat = Field(gt=0, le=100_000_000_000)
    stock_count: int = Field(default=5, ge=1, le=10)
    training_years: int = Field(default=10, ge=1, le=10)
    max_per_sector: int = Field(default=3, ge=1, le=10)
    risk_free_rate: FiniteFloat = Field(default=0.0, ge=0, le=1)


def _clean(value):
    """Convert NumPy/Pandas values into JSON-safe Python values."""
    if value is None:
        return None

    if value is pd.NaT or value is pd.NA:
        return None

    if isinstance(value, (pd.Timestamp, date)):
        return value.isoformat()

    if isinstance(value, np.generic):
        value = value.item()

    if isinstance(value, float) and not math.isfinite(value):
        return None

    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]

    return value


def _metrics(result):
    return _clean(result.get("metrics", {}))


def _period_summary(prices, include_baseline=True):
    if prices is None or prices.empty:
        raise ValueError("Insufficient historical observations for this period.")

    start_index = 0 if include_baseline else 1

    if len(prices) <= start_index:
        raise ValueError("Insufficient historical observations for this period.")

    measured = prices.iloc[start_index:]

    return {
        "start": str(measured.index.min().date()),
        "end": str(measured.index.max().date()),
        "observations": len(measured),
    }


def _benchmark_summary(comparison):
    return {
        str(key): _clean(value)
        for key, value in comparison.items()
        if key != "comparison_returns"
    }


@router.post("/portfolio/generate")
def generate_portfolio(request: PortfolioRequest):
    """Generate a capital-constrained portfolio using original Greedy V2."""

    try:
        today = date.today()
        end_date = today.isoformat()
        start_date = (
            today - timedelta(days=365 * request.training_years)
        ).isoformat()

        dataset = prepare_greedy_v2_dataset(
            start_date=start_date,
            end_date=end_date,
        )

        if dataset.adjusted_prices is None or dataset.adjusted_prices.empty:
            raise ValueError("No adjusted historical stock prices are available.")

        if dataset.benchmark_prices is None or dataset.benchmark_prices.empty:
            raise ValueError("Historical NIFTY 50 benchmark prices are unavailable.")

        # Chronological split: selection uses training data only.
        split = chronological_split(dataset.adjusted_prices, allow_sparse_evaluation=True)

        if split.train.empty or split.validation.empty or split.test.empty:
            raise ValueError(
                "Insufficient historical data to create train, validation and test periods."
            )

        # Preserve the original sequential Greedy V2 selection algorithm.
        selection = greedy_select_stocks(
            train_prices=split.train,
            sectors=dataset.sectors,
            target_stocks=request.stock_count,
            max_per_sector=request.max_per_sector,
            risk_free_rate=request.risk_free_rate,
        )

        symbols = selection["selected_symbols"]

        if not symbols:
            raise ValueError("Greedy V2 did not select any stocks.")

        # Latest available raw close is used for executable share quantities.
        latest_prices = {}

        for symbol in symbols:
            raw_column = (
                symbol if symbol in dataset.raw_prices.columns
                else f"{symbol}_RAW"
            )
            if raw_column not in dataset.raw_prices.columns:
                raise ValueError(
                    f"Raw price history is unavailable for {symbol}."
                )

            available = dataset.raw_prices[raw_column].dropna()

            if available.empty:
                raise ValueError(f"No usable raw price is available for {symbol}.")

            latest_prices[symbol] = float(available.iloc[-1])

        allocation = allocate_capital(
            symbols=symbols,
            prices=latest_prices,
            capital=float(request.capital),
        )

        holdings = allocation["holdings"]

        for holding in holdings:
            symbol = holding["symbol"]
            holding["sector"] = dataset.sectors.get(symbol, "Unknown")

        # Validation period: evaluate selected symbols without re-selection.
        validation_prices = split.validation
        validation_benchmark = dataset.benchmark_prices.reindex(
            validation_prices.index
        )

        validation_result = calculate_portfolio(
            prices=validation_prices,
            sectors=dataset.sectors,
            symbols=symbols,
            risk_free_rate=request.risk_free_rate,
            max_stocks=request.stock_count,
            max_per_sector=request.max_per_sector,
            price_basis="SPLIT_BONUS_ADJUSTED",
            return_type="PRICE_RETURN",
        )

        validation_comparison = compare_with_benchmark(
            validation_result["daily_returns"],
            validation_benchmark,
        )

        # Final test period remains separate from training and validation.
        test_prices = split.test
        test_benchmark = dataset.benchmark_prices.reindex(test_prices.index)

        test_result = calculate_portfolio(
            prices=test_prices,
            sectors=dataset.sectors,
            symbols=symbols,
            risk_free_rate=request.risk_free_rate,
            max_stocks=request.stock_count,
            max_per_sector=request.max_per_sector,
            price_basis="SPLIT_BONUS_ADJUSTED",
            return_type="PRICE_RETURN",
        )

        test_comparison = compare_with_benchmark(
            test_result["daily_returns"],
            test_benchmark,
        )

        training_period = _period_summary(split.train)
        validation_period = _period_summary(validation_prices, include_baseline=False)
        test_period = _period_summary(test_prices, include_baseline=False)

        return _clean({
            "status": "success",
            "selection_method": "SEQUENTIAL_GREEDY_SHARPE",
            "portfolio": allocation,
            "holdings": holdings,
            "selection_log": selection["selection_log"].to_dict(
                orient="records"
            ),
            "training": {
                **training_period,
                "selection_sharpe": selection["portfolio_result"][
                    "metrics"
                ].get("sharpe_ratio"),
            },
            "validation": {
                **validation_period,
                "metrics": _metrics(validation_result),
                "benchmark": _benchmark_summary(validation_comparison),
            },
            "test": {
                **test_period,
                "metrics": _metrics(test_result),
                "benchmark": _benchmark_summary(test_comparison),
            },
            "data_limitations": {
                "membership_basis": dataset.metadata["membership_basis"],
                "corporate_action_coverage": dataset.metadata[
                    "corporate_action_coverage"
                ],
                "dividend_adjusted": dataset.metadata["dividend_adjusted"],
                "price_basis": dataset.metadata["price_basis"],
                "benchmark_basis": "NIFTY_50_PRICE_RETURN",
                "historical_membership_survivorship_bias": True,
                "historical_metrics_are_daily_rebalanced": True,
                "live_holdings_use_latest_raw_close": True,
                "actual_holdings_buy_and_hold_metrics_calculated": False,
                "training_candidate_count": len(split.metadata["eligible_training_symbols"]),
                "excluded_incomplete_training_symbols": split.metadata[
                    "excluded_incomplete_training_symbols"
                ],
                "validation_test_missing_prices_filled": False,
            },
            "assumptions": selection["assumptions"],
        })

    except ValueError as exc:
        logger.warning("Portfolio request rejected: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:
        logger.exception("Portfolio generation failed.")
        # Diagnostic detail is temporary. Replace with a generic message
        # before deploying this endpoint publicly.
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc
