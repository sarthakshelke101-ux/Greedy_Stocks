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

INITIAL_TRAIN = 120
TEST_WINDOW = 30
TARGET_STOCKS = 10
MAX_PER_SECTOR = 3


def greedy_select(train_prices, sectors):
    selected = []

    for step in range(TARGET_STOCKS):
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
                train_prices,
                sectors,
                symbols=trial,
                risk_free_rate=0.0,
            )

            sharpe = result["metrics"].get("sharpe_ratio")

            if sharpe is not None and pd.notna(sharpe):
                candidates.append((float(sharpe), symbol))

        if not candidates:
            raise ValueError(f"No eligible candidate at step {step + 1}")

        candidates.sort(reverse=True)
        selected.append(candidates[0][1])

    return selected


def main():
    print("\nGREEDY STOCKS — WALK-FORWARD VALIDATION")
    print("=" * 70)

    constituents = get_latest_constituents()

    if len(constituents) != 50:
        raise ValueError("Expected 50 NIFTY 50 constituents.")

    sectors = dict(zip(constituents["symbol"], constituents["sector"]))

    series = []

    for _, row in constituents.iterrows():
        prices = get_company_prices(
            int(row["company_id"]),
            START_DATE,
            END_DATE,
        )
        series.append(prices.rename(row["symbol"]))

    all_prices = pd.concat(series, axis=1).sort_index()
    prices = all_prices.dropna(axis=0, how="any")

    benchmark = get_index_closes(START_DATE, END_DATE)

    # All folds use the same dates for all 50 stocks and benchmark.
    benchmark = benchmark.reindex(prices.index)

    if benchmark.isna().any():
        raise ValueError("Benchmark prices missing on common dates.")

    print(f"Common price observations: {len(prices)}")
    print(f"Date range: {prices.index[0].date()} to {prices.index[-1].date()}")

    results = []
    fold = 1
    train_end = INITIAL_TRAIN

    while train_end < len(prices):
        test_end = min(train_end + TEST_WINDOW, len(prices))

        if test_end - train_end < 20:
            break

        train = prices.iloc[:train_end].copy()

        # Previous training close is retained as test baseline.
        test = prices.iloc[train_end - 1:test_end].copy()

        print(f"\nFOLD {fold}")
        print("-" * 70)
        print(
            f"Training: {train.index[0].date()} to "
            f"{train.index[-1].date()} ({len(train)} prices)"
        )
        print(
            f"Testing: {test.index[1].date()} to "
            f"{test.index[-1].date()} ({len(test) - 1} returns)"
        )

        # Selection sees training data only.
        selected = greedy_select(train, sectors)
        selected_sectors = {s: sectors[s] for s in selected}

        # Evaluate fixed selections on unseen data.
        train_result = calculate_portfolio(
            train,
            selected_sectors,
            symbols=selected,
            risk_free_rate=0.0,
        )

        test_result = calculate_portfolio(
            test,
            selected_sectors,
            symbols=selected,
            risk_free_rate=0.0,
        )

        train_benchmark = benchmark.reindex(train.index)
        test_benchmark = benchmark.reindex(test.index)

        train_comparison = compare_with_benchmark(
            train_result["daily_returns"],
            train_benchmark,
        )

        test_comparison = compare_with_benchmark(
            test_result["daily_returns"],
            test_benchmark,
        )

        print("Selected:", ", ".join(selected))
        print(
            f"Training Sharpe: "
            f"{train_result['metrics']['sharpe_ratio']:.4f}"
        )
        print(
            f"Testing Sharpe: "
            f"{test_result['metrics']['sharpe_ratio']:.4f}"
        )
        print(
            f"Test portfolio return: "
            f"{test_comparison['portfolio_return_pct']:.4f}%"
        )
        print(
            f"Test NIFTY return: "
            f"{test_comparison['benchmark_return_pct']:.4f}%"
        )
        print(
            f"Test excess return: "
            f"{test_comparison['excess_return_pct']:.4f} percentage points"
        )

        results.append({
            "fold": fold,
            "train_start": str(train.index[0].date()),
            "train_end": str(train.index[-1].date()),
            "test_start": str(test.index[1].date()),
            "test_end": str(test.index[-1].date()),
            "train_observations": len(train),
            "test_return_observations": len(test) - 1,
            "selected_stocks": ", ".join(selected),
            "train_sharpe": train_result["metrics"]["sharpe_ratio"],
            "test_sharpe": test_result["metrics"]["sharpe_ratio"],
            "test_portfolio_return_pct": test_comparison["portfolio_return_pct"],
            "test_benchmark_return_pct": test_comparison["benchmark_return_pct"],
            "test_excess_return_pct": test_comparison["excess_return_pct"],
            "test_max_drawdown_pct": test_result["metrics"]["maximum_drawdown_pct"],
        })

        fold += 1
        train_end = test_end

    if not results:
        raise ValueError("No valid walk-forward folds generated.")

    output_dir = ROOT / "database" / "processed" / "analytics"
    output_dir.mkdir(parents=True, exist_ok=True)

    report = pd.DataFrame(results)

    report.to_csv(
        output_dir / "greedy_walk_forward_results.csv",
        index=False,
    )

    print("\nWALK-FORWARD SUMMARY")
    print("=" * 70)

    print(report[[
        "fold",
        "test_start",
        "test_end",
        "test_portfolio_return_pct",
        "test_benchmark_return_pct",
        "test_excess_return_pct",
        "test_sharpe",
    ]].to_string(index=False))

    print("\nAGGREGATE RESULTS")
    print("-" * 70)
    print("Folds:", len(report))
    print(
        "Positive excess-return folds:",
        int((report["test_excess_return_pct"] > 0).sum()),
    )
    print(
        "Average test excess return:",
        round(report["test_excess_return_pct"].mean(), 4),
        "percentage points",
    )
    print(
        "Median test excess return:",
        round(report["test_excess_return_pct"].median(), 4),
        "percentage points",
    )

    print("\nSaved: greedy_walk_forward_results.csv")
    print("Database writes: None")
    print("Historical membership: Latest snapshot, retrospective.")
    print("Dividends excluded; corporate-action coverage partial.")
    print("Each fold is a historical test, not a live trading result.")


if __name__ == "__main__":
    main()
