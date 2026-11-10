
"""Greedy V2 — sequential portfolio selection engine.

This module selects stocks using ONLY the price history supplied to it.
The caller is responsible for passing training-period prices, never
validation or test-period prices.

Method:
- Equal-weight portfolio.
- Sequential greedy selection.
- Maximise historical annualised Sharpe ratio.
- Maximum 10 stocks.
- Maximum 3 stocks per sector.
- Risk-free rate defaults to 0%.
"""

from __future__ import annotations

import math
from typing import Any

import sys
from pathlib import Path

import pandas as pd

ANALYTICS_DIR = Path(__file__).resolve().parent

if str(ANALYTICS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYTICS_DIR))

from portfolio_analytics import calculate_portfolio


def greedy_select_stocks(
    train_prices: pd.DataFrame,
    sectors: dict[str, str],
    target_stocks: int = 10,
    max_per_sector: int = 3,
    risk_free_rate: float = 0.0,
) -> dict[str, Any]:
    """Select stocks sequentially using training-period Sharpe ratio."""

    if not isinstance(train_prices, pd.DataFrame):
        raise TypeError("train_prices must be a pandas DataFrame.")

    if train_prices.empty:
        raise ValueError("Training price data is empty.")

    if not isinstance(train_prices.index, pd.DatetimeIndex):
        raise ValueError("Training prices require a DatetimeIndex.")

    if train_prices.index.tz is not None:
        raise ValueError("Training dates must not contain a timezone.")

    if train_prices.index.has_duplicates:
        raise ValueError("Duplicate training dates detected.")

    if not train_prices.columns.is_unique:
        raise ValueError("Duplicate stock symbols detected.")

    if len(train_prices) < 60:
        raise ValueError("At least 60 price observations are required.")

    if not isinstance(target_stocks, int) or isinstance(target_stocks, bool):
        raise ValueError("target_stocks must be an integer.")

    if not isinstance(max_per_sector, int) or isinstance(max_per_sector, bool):
        raise ValueError("max_per_sector must be an integer.")

    if target_stocks < 1:
        raise ValueError("target_stocks must be at least 1.")

    if max_per_sector < 1:
        raise ValueError("max_per_sector must be at least 1.")

    if target_stocks > len(train_prices.columns):
        raise ValueError("Target exceeds the available number of stocks.")

    if not math.isfinite(float(risk_free_rate)):
        raise ValueError("risk_free_rate must be finite.")

    if risk_free_rate < 0:
        raise ValueError("risk_free_rate cannot be negative.")

    prices = train_prices.copy().sort_index()

    prices = prices.apply(pd.to_numeric, errors="coerce")

    if prices.isna().any().any():
        raise ValueError(
            "Training prices contain missing or invalid values. "
            "Do not fill or silently remove them."
        )

    if (prices <= 0).any().any():
        raise ValueError("Training prices must be positive.")

    symbols = list(prices.columns)

    missing_sectors = [
        symbol
        for symbol in symbols
        if symbol not in sectors
        or not isinstance(sectors[symbol], str)
        or not sectors[symbol].strip()
    ]

    if missing_sectors:
        raise ValueError(
            f"Missing sector classifications: {missing_sectors}"
        )

    sector_capacity = sum(
        min(
            max_per_sector,
            sum(
                sectors[symbol] == sector
                for symbol in symbols
            ),
        )
        for sector in set(sectors.values())
    )

    if target_stocks > sector_capacity:
        raise ValueError(
            "Target cannot be reached under the sector constraint."
        )

    selected: list[str] = []
    selection_log: list[dict[str, Any]] = []

    print("\nGREEDY STOCKS — V2 SELECTION ENGINE")
    print("=" * 65)
    print("Available candidates:", len(symbols))
    print("Target portfolio size:", target_stocks)
    print("Maximum stocks per sector:", max_per_sector)
    print("Risk-free rate:", risk_free_rate)
    print("Training observations:", len(prices))
    print("Training dates:", prices.index.min().date(), "to", prices.index.max().date())

    # Sequential greedy selection.
    for step in range(1, target_stocks + 1):

        candidates: list[dict[str, Any]] = []

        for symbol in symbols:

            if symbol in selected:
                continue

            current_sector_count = sum(
                sectors[item] == sectors[symbol]
                for item in selected
            )

            if current_sector_count >= max_per_sector:
                continue

            trial_symbols = selected + [symbol]

            result = calculate_portfolio(
                prices=prices,
                sectors=sectors,
                symbols=trial_symbols,
                risk_free_rate=risk_free_rate,
                max_stocks=target_stocks,
                max_per_sector=max_per_sector,
            )

            sharpe = result["metrics"].get("sharpe_ratio")

            if sharpe is None or pd.isna(sharpe):
                continue

            sharpe = float(sharpe)

            if not math.isfinite(sharpe):
                continue

            candidates.append({
                "symbol": symbol,
                "sector": sectors[symbol],
                "portfolio_sharpe": sharpe,
                "portfolio_size": len(trial_symbols),
            })

        if not candidates:
            raise ValueError(
                f"No valid candidates available at selection step {step}."
            )

        # Deterministic tie-breaking by ticker.
        candidates.sort(
            key=lambda item: (
                -item["portfolio_sharpe"],
                item["symbol"],
            )
        )

        winner = candidates[0]

        previous_sharpe = (
            selection_log[-1]["portfolio_sharpe"]
            if selection_log
            else None
        )

        selected.append(winner["symbol"])

        selection_log.append({
            "step": step,
            "symbol": winner["symbol"],
            "sector": winner["sector"],
            "portfolio_size": len(selected),
            "portfolio_sharpe": winner["portfolio_sharpe"],
            "previous_portfolio_sharpe": previous_sharpe,
            "marginal_sharpe_change": (
                winner["portfolio_sharpe"] - previous_sharpe
                if previous_sharpe is not None
                else None
            ),
            "candidates_evaluated": len(candidates),
        })

        print(
            f"Step {step:02d}: {winner['symbol']:<15} "
            f"Sector: {winner['sector']:<25} "
            f"Sharpe: {winner['portfolio_sharpe']:.4f}"
        )

    # Calculate final portfolio metrics.
    final_result = calculate_portfolio(
        prices=prices,
        sectors=sectors,
        symbols=selected,
        risk_free_rate=risk_free_rate,
        max_stocks=target_stocks,
        max_per_sector=max_per_sector,
    )

    print("\nSELECTION COMPLETE")
    print("-" * 65)
    print("Selected stocks:", len(selected))
    print("Unique sectors:", len({
        sectors[symbol] for symbol in selected
    }))
    print("Selected symbols:", ", ".join(selected))
    print("Final Sharpe:", final_result["metrics"].get("sharpe_ratio"))

    return {
        "selected_symbols": selected,
        "selection_log": pd.DataFrame(selection_log),
        "portfolio_result": final_result,
        "assumptions": {
            "selection_method": "SEQUENTIAL_GREEDY_SHARPE",
            "price_basis": "SPLIT_BONUS_ADJUSTED",
            "weighting": "EQUAL_WEIGHT",
            "daily_rebalancing": True,
            "risk_free_rate": risk_free_rate,
            "target_stocks": target_stocks,
            "max_per_sector": max_per_sector,
            "selection_uses_training_data_only": True,
            "globally_optimal": False,
        },
    }
