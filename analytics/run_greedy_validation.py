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
TRAIN_RATIO = 0.70


def select_greedy_portfolio(train_prices, sectors):
    selected = []
    log = []

    for step in range(1, TARGET_STOCKS + 1):
        candidates = []

        for symbol in train_prices.columns:
            if symbol in selected:
                continue

            sector_count = sum(
                sectors[s] == sectors[symbol] for s in selected
            )

            if sector_count >= MAX_PER_SECTOR:
                continue

            trial = selected + [symbol]

            result = calculate_portfolio(
                prices=train_prices,
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
            })

        if not candidates:
            raise ValueError(f"No candidates available at step {step}.")

        candidates.sort(key=lambda x: x["sharpe"], reverse=True)
        winner = candidates[0]
        selected.append(winner["symbol"])

        log.append({
            "step": step,
            "selected_symbol": winner["symbol"],
            "sector": winner["sector"],
            "training_sharpe": winner["sharpe"],
            "candidates_evaluated": len(candidates),
        })

        print(
            f"Step {step:02d}: {winner['symbol']:15} "
            f"| Training Sharpe: {winner['sharpe']:.4f}"
        )

    return selected, pd.DataFrame(log)


def print_metrics(title, metrics):
    print(f"\n{title}")
    print("-" * 65)

    for key, value in metrics.items():
        print(f"{key}: {value}")


def main():
    print("\nGREEDY STOCKS — OUT-OF-SAMPLE VALIDATION")
    print("=" * 65)

    constituents = get_latest_constituents()

    if len(constituents) != 50:
        raise ValueError("Expected exactly 50 latest constituents.")

    sectors = dict(zip(constituents["symbol"], constituents["sector"]))

    series_list = []

    for _, row in constituents.iterrows():
        series = get_company_prices(
            int(row["company_id"]),
            START_DATE,
            END_DATE,
        )
        series_list.append(series.rename(row["symbol"]))

    all_prices = pd.concat(series_list, axis=1).sort_index()
    prices = all_prices.dropna(axis=0, how="any")

    if len(prices) < 120:
        raise ValueError("Insufficient common observations for validation.")

    split = int(len(prices) * TRAIN_RATIO)

    # Training ends before the test period begins.
    train_prices = prices.iloc[:split].copy()

    # Keep the last training price only as the test starting baseline.
    test_prices = prices.iloc[split - 1:].copy()

    if len(train_prices) < 60 or len(test_prices) < 61:
        raise ValueError("Insufficient training or test observations.")

    print(f"\nCommon price observations: {len(prices)}")
    print(
        f"Training: {train_prices.index[0].date()} to "
        f"{train_prices.index[-1].date()} "
        f"({len(train_prices)} price observations)"
    )
    print(
        f"Testing: {test_prices.index[1].date()} to "
        f"{test_prices.index[-1].date()} "
        f"({len(test_prices) - 1} return observations)"
    )

    # Select stocks using training data only.
    print("\nGREEDY TRAINING SELECTION")
    print("-" * 65)

    selected, selection_log = select_greedy_portfolio(
        train_prices,
        sectors,
    )

    selected_sectors = {s: sectors[s] for s in selected}

    # Evaluate the fixed selection on unseen test data.
    test_result = calculate_portfolio(
        prices=test_prices,
        sectors=selected_sectors,
        symbols=selected,
        risk_free_rate=0.0,
    )

    train_result = calculate_portfolio(
        prices=train_prices,
        sectors=selected_sectors,
        symbols=selected,
        risk_free_rate=0.0,
    )

    benchmark = get_index_closes(START_DATE, END_DATE)

    train_benchmark = benchmark.reindex(train_prices.index)
    test_benchmark = benchmark.reindex(test_prices.index)

    if train_benchmark.isna().any() or test_benchmark.isna().any():
        raise ValueError("Benchmark has missing prices on evaluation dates.")

    train_comparison = compare_with_benchmark(
        train_result["daily_returns"],
        train_benchmark,
    )

    test_comparison = compare_with_benchmark(
        test_result["daily_returns"],
        test_benchmark,
    )

    print("\nFINAL SELECTED STOCKS")
    print("-" * 65)

    for symbol in selected:
        print(f"{symbol:15} | {sectors[symbol]} | Weight: 10%")

    print_metrics("TRAINING METRICS — IN SAMPLE", train_result["metrics"])
    print_metrics("TEST METRICS — OUT OF SAMPLE", test_result["metrics"])

    print_metrics(
        "TRAINING BENCHMARK COMPARISON",
        {k: v for k, v in train_comparison.items()
         if k != "comparison_returns"},
    )

    print_metrics(
        "TEST BENCHMARK COMPARISON",
        {k: v for k, v in test_comparison.items()
         if k != "comparison_returns"},
    )

    output_dir = ROOT / "database" / "processed" / "analytics"
    output_dir.mkdir(parents=True, exist_ok=True)

    selection_log.to_csv(
        output_dir / "greedy_training_selection_log.csv",
        index=False,
    )

    summary = pd.DataFrame([
        {
            "period": "TRAIN",
            "start_date": str(train_prices.index[0].date()),
            "end_date": str(train_prices.index[-1].date()),
            "portfolio_return_pct": train_comparison["portfolio_return_pct"],
            "benchmark_return_pct": train_comparison["benchmark_return_pct"],
            "excess_return_pct": train_comparison["excess_return_pct"],
            "sharpe_ratio": train_result["metrics"]["sharpe_ratio"],
        },
        {
            "period": "TEST",
            "start_date": str(test_prices.index[1].date()),
            "end_date": str(test_prices.index[-1].date()),
            "portfolio_return_pct": test_comparison["portfolio_return_pct"],
            "benchmark_return_pct": test_comparison["benchmark_return_pct"],
            "excess_return_pct": test_comparison["excess_return_pct"],
            "sharpe_ratio": test_result["metrics"]["sharpe_ratio"],
        },
    ])

    summary.to_csv(
        output_dir / "greedy_out_of_sample_summary.csv",
        index=False,
    )

    print("\nVALIDATION FILES SAVED")
    print("greedy_training_selection_log.csv")
    print("greedy_out_of_sample_summary.csv")

    print("\nDISCLOSURES")
    print("Selection uses training data only.")
    print("Test portfolio uses fixed selected stocks.")
    print("Weights are equal and rebalanced daily.")
    print("Latest constituent snapshot is used retrospectively.")
    print("Prices are unadjusted; dividends are excluded.")
    print("Corporate-action coverage is partial.")
    print("This is a single historical holdout, not proof of predictive ability.")
    print("No database writes performed.")

    print("\nOUT-OF-SAMPLE VALIDATION COMPLETED")


if __name__ == "__main__":
    main()
