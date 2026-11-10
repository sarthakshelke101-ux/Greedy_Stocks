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


def greedy_select(train, sectors):
    selected = []

    for _ in range(TARGET_STOCKS):
        candidates = []

        for symbol in train.columns:
            if symbol in selected:
                continue

            if (
                sum(sectors[s] == sectors[symbol] for s in selected)
                >= MAX_PER_SECTOR
            ):
                continue

            result = calculate_portfolio(
                train,
                sectors,
                symbols=selected + [symbol],
                risk_free_rate=0.0,
            )

            sharpe = result["metrics"].get("sharpe_ratio")

            if sharpe is not None and pd.notna(sharpe):
                candidates.append((float(sharpe), symbol))

        if not candidates:
            raise ValueError("No eligible Greedy candidate.")

        candidates.sort(reverse=True)
        selected.append(candidates[0][1])

    return selected


def top_weight_select(constituents):
    selected = []
    counts = {}

    for _, row in constituents.sort_values(
        "weightage", ascending=False
    ).iterrows():
        symbol = row["symbol"]
        sector = row["sector"]

        if counts.get(sector, 0) >= MAX_PER_SECTOR:
            continue

        selected.append(symbol)
        counts[sector] = counts.get(sector, 0) + 1

        if len(selected) == TARGET_STOCKS:
            break

    if len(selected) != TARGET_STOCKS:
        raise ValueError("Could not select 10 top-weight stocks.")

    return selected


def evaluate(name, symbols, test, sectors, benchmark):
    selected_sectors = {s: sectors[s] for s in symbols}

    # EQUAL_50 is a comparison baseline, not a GREEDY LAB portfolio.
    # Preserve the normal constraints for the two 10-stock strategies.
    if name == "EQUAL_50":
        max_stocks = 50
        max_per_sector = 50
    else:
        max_stocks = TARGET_STOCKS
        max_per_sector = MAX_PER_SECTOR

    result = calculate_portfolio(
        test,
        selected_sectors,
        symbols=symbols,
        risk_free_rate=0.0,
        max_stocks=max_stocks,
        max_per_sector=max_per_sector,
    )

    comparison = compare_with_benchmark(
        result["daily_returns"],
        benchmark,
    )

    return {
        "strategy": name,
        "portfolio_return_pct": comparison["portfolio_return_pct"],
        "benchmark_return_pct": comparison["benchmark_return_pct"],
        "excess_return_pct": comparison["excess_return_pct"],
        "sharpe_ratio": result["metrics"]["sharpe_ratio"],
        "volatility_pct": result["metrics"]["annualized_volatility_pct"],
        "max_drawdown_pct": result["metrics"]["maximum_drawdown_pct"],
        "stocks": ", ".join(symbols),
    }


def main():
    print("\nGREEDY STOCKS — STRATEGY BASELINE COMPARISON")
    print("=" * 75)

    constituents = get_latest_constituents()

    if len(constituents) != 50:
        raise ValueError("Expected 50 NIFTY 50 constituents.")

    sectors = dict(zip(constituents["symbol"], constituents["sector"]))

    series = []

    for _, row in constituents.iterrows():
        price = get_company_prices(
            int(row["company_id"]),
            START_DATE,
            END_DATE,
        )
        series.append(price.rename(row["symbol"]))

    all_prices = pd.concat(series, axis=1).sort_index()
    prices = all_prices.dropna(axis=0, how="any")

    benchmark = get_index_closes(
        START_DATE,
        END_DATE,
    ).reindex(prices.index)

    if benchmark.isna().any():
        raise ValueError("Benchmark has missing common dates.")

    top10 = top_weight_select(constituents)

    print(f"Common price observations: {len(prices)}")
    print(f"Top-weight baseline: {', '.join(top10)}")
    print(f"Equal-weight universe: {len(prices.columns)} stocks")

    results = []
    fold = 1
    train_end = INITIAL_TRAIN

    while train_end < len(prices):
        test_end = min(train_end + TEST_WINDOW, len(prices))

        if test_end - train_end < 20:
            break

        train = prices.iloc[:train_end]
        test = prices.iloc[train_end - 1:test_end]
        test_benchmark = benchmark.reindex(test.index)

        greedy = greedy_select(train, sectors)

        strategies = [
            ("GREEDY", greedy),
            ("TOP_10_INDEX_WEIGHT", top10),
            ("EQUAL_50", list(prices.columns)),
        ]

        print(
            f"\nFOLD {fold}: "
            f"{test.index[1].date()} to {test.index[-1].date()}"
        )

        for name, symbols in strategies:
            result = evaluate(
                name,
                symbols,
                test,
                sectors,
                test_benchmark,
            )

            result["fold"] = fold
            result["test_start"] = str(test.index[1].date())
            result["test_end"] = str(test.index[-1].date())

            results.append(result)

            print(
                f"{name:20} "
                f"Return: {result['portfolio_return_pct']:8.3f}% | "
                f"Excess: {result['excess_return_pct']:8.3f} pp | "
                f"Sharpe: {result['sharpe_ratio']:7.3f}"
            )

        fold += 1
        train_end = test_end

    report = pd.DataFrame(results)

    output_dir = ROOT / "database" / "processed" / "analytics"
    output_dir.mkdir(parents=True, exist_ok=True)

    report.to_csv(
        output_dir / "greedy_strategy_baseline_comparison.csv",
        index=False,
    )

    summary = report.groupby("strategy").agg(
        folds=("fold", "count"),
        average_return_pct=("portfolio_return_pct", "mean"),
        average_excess_pct=("excess_return_pct", "mean"),
        median_excess_pct=("excess_return_pct", "median"),
        positive_excess_folds=(
            "excess_return_pct",
            lambda x: int((x > 0).sum()),
        ),
        average_sharpe=("sharpe_ratio", "mean"),
        average_drawdown_pct=("max_drawdown_pct", "mean"),
    ).reset_index()

    print("\nAGGREGATE STRATEGY COMPARISON")
    print("=" * 75)
    print(summary.to_string(index=False))

    summary.to_csv(
        output_dir / "greedy_strategy_baseline_summary.csv",
        index=False,
    )

    print("\nSaved:")
    print("greedy_strategy_baseline_comparison.csv")
    print("greedy_strategy_baseline_summary.csv")

    print("\nNo database writes performed.")
    print("All strategies use the same test dates.")
    print("All portfolio strategies use equal weights and daily rebalancing.")
    print("Historical constituent snapshot is retrospective.")
    print("Dividends excluded; corporate-action coverage partial.")


if __name__ == "__main__":
    main()
