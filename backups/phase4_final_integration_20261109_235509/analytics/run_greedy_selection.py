import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analytics"))

import _bootstrap

from database_adapter import get_latest_constituents, get_company_prices
from portfolio_analytics import calculate_portfolio, compare_with_benchmark
from index_adapter import get_index_closes


START_DATE = "2025-10-24"
END_DATE = "2026-11-05"
TARGET_STOCKS = 10
MAX_PER_SECTOR = 3


def main():
    print("\nGREEDY STOCKS — GREEDY SELECTION ENGINE")
    print("=" * 65)

    constituents = get_latest_constituents()

    if len(constituents) != 50:
        raise ValueError(f"Expected 50 constituents, got {len(constituents)}")

    sectors = dict(zip(constituents["symbol"], constituents["sector"]))

    print("Loading historical prices for 50 companies...")

    price_series = {}

    for _, row in constituents.iterrows():
        symbol = row["symbol"]
        series = get_company_prices(
            int(row["company_id"]),
            START_DATE,
            END_DATE,
        )
        price_series[symbol] = series.rename(symbol)

    all_prices = pd.concat(price_series.values(), axis=1).sort_index()

    # Fair comparison: every candidate uses exactly the same dates.
    prices = all_prices.dropna(axis=0, how="any")

    if len(prices) < 60:
        raise ValueError("Insufficient common price history.")

    if prices.isna().any().any():
        raise ValueError("Common price matrix still contains missing values.")

    print(f"\nCommon price observations: {len(prices)}")
    print(f"First date: {prices.index.min().date()}")
    print(f"Last date: {prices.index.max().date()}")
    print(f"Expected return observations: {len(prices) - 1}")

    selected = []
    selection_log = []

    print("\nSTARTING GREEDY SELECTION")
    print("-" * 65)

    for step in range(1, TARGET_STOCKS + 1):
        candidates = []

        for symbol in prices.columns:
            if symbol in selected:
                continue

            current_sector_count = sum(
                sectors[s] == sectors[symbol] for s in selected
            )

            if current_sector_count >= MAX_PER_SECTOR:
                continue

            trial = selected + [symbol]

            result = calculate_portfolio(
                prices=prices,
                sectors=sectors,
                symbols=trial,
                risk_free_rate=0.0,
            )

            sharpe = result["metrics"].get("sharpe_ratio")

            if sharpe is None or pd.isna(sharpe):
                continue

            candidates.append({
                "symbol": symbol,
                "sector": sectors[symbol],
                "sharpe": float(sharpe),
                "portfolio_size": len(trial),
            })

        if not candidates:
            raise ValueError(
                f"No valid candidates available at selection step {step}."
            )

        candidates.sort(
            key=lambda item: item["sharpe"],
            reverse=True,
        )

        winner = candidates[0]
        previous_sharpe = (
            selection_log[-1]["portfolio_sharpe"]
            if selection_log else None
        )

        selected.append(winner["symbol"])

        selection_log.append({
            "step": step,
            "selected_symbol": winner["symbol"],
            "sector": winner["sector"],
            "portfolio_sharpe": winner["sharpe"],
            "previous_portfolio_sharpe": previous_sharpe,
            "candidates_evaluated": len(candidates),
            "sector_limit": MAX_PER_SECTOR,
        })

        print(
            f"Step {step:02d} | "
            f"Selected: {winner['symbol']:15} | "
            f"Sector: {winner['sector']:35} | "
            f"Sharpe: {winner['sharpe']:.4f} | "
            f"Evaluated: {len(candidates)}"
        )

    # Final portfolio calculation.
    final_result = calculate_portfolio(
        prices=prices,
        sectors=sectors,
        symbols=selected,
        risk_free_rate=0.0,
    )

    benchmark = get_index_closes(START_DATE, END_DATE)
    benchmark = benchmark.reindex(prices.index)

    if benchmark.isna().any():
        raise ValueError(
            "Benchmark has missing values on common stock-price dates."
        )

    comparison = compare_with_benchmark(
        final_result["daily_returns"],
        benchmark,
    )

    # Save selection decisions for transparency and reproducibility.
    output_dir = ROOT / "database" / "processed" / "analytics"
    output_dir.mkdir(parents=True, exist_ok=True)

    log_path = output_dir / "greedy_selection_log.csv"
    pd.DataFrame(selection_log).to_csv(log_path, index=False)

    print("\nFINAL GREEDY PORTFOLIO")
    print("-" * 65)

    for symbol in selected:
        print(f"{symbol:15} | {sectors[symbol]} | Weight: 10%")

    print("\nFINAL PORTFOLIO METRICS")
    print("-" * 65)

    for key, value in final_result["metrics"].items():
        print(f"{key}: {value}")

    print("\nBENCHMARK COMPARISON")
    print("-" * 65)

    for key, value in comparison.items():
        if key != "comparison_returns":
            print(f"{key}: {value}")

    print("\nMETHODOLOGY")
    print("-" * 65)
    print("Algorithm: Sequential greedy Sharpe maximisation")
    print("Candidate universe: Latest NIFTY 50 snapshot")
    print("Historical evaluation: Common dates for all 50 stocks")
    print("Portfolio weights: Equal weight")
    print("Rebalancing: Daily")
    print("Risk-free rate: 0%")
    print("Maximum stocks: 10")
    print("Maximum per sector: 3")
    print("Price basis: Raw unadjusted close")
    print("Dividends: Excluded")
    print("Corporate-action coverage: Partial")
    print("Historical membership: Latest snapshot, not point-in-time")
    print("Database writes: None")

    print(f"\nSelection log saved: {log_path}")
    print("\nGREEDY SELECTION COMPLETED")
    print("=" * 65)


if __name__ == "__main__":
    main()
