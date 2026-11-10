
"""Compare Greedy V2 against equal-weight and random baselines."""

import json
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from analytics.greedy_v2_data import prepare_greedy_v2_dataset
from analytics.greedy_v2_splits import chronological_split
from analytics.greedy_v2_engine import greedy_select_stocks
from analytics.portfolio_analytics import (
    calculate_portfolio,
    compare_with_benchmark,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "database" / "processed" / "analytics"

TARGET_STOCKS = 10
MAX_PER_SECTOR = 3
RISK_FREE_RATE = 0.0
PRICE_BASIS = "SPLIT_BONUS_ADJUSTED"
RETURN_TYPE = "PRICE_RETURN"

RANDOM_PORTFOLIO_COUNT = 500
RANDOM_SEED = 42


def safe_value(value):
    if isinstance(value, dict):
        return {str(k): safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_value(v) for v in value]
    if isinstance(value, (np.integer, np.floating)):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def scalar_metrics(portfolio):
    metrics = portfolio["metrics"]
    keys = [
        "period_return_pct",
        "cagr_pct",
        "annualized_volatility_pct",
        "maximum_drawdown_pct",
        "sharpe_ratio",
    ]
    return {key: metrics.get(key) for key in keys}


def evaluate_portfolio(
    prices,
    benchmark,
    sectors,
    symbols,
    max_stocks,
    max_per_sector,
):
    portfolio = calculate_portfolio(
        prices=prices,
        sectors=sectors,
        symbols=symbols,
        risk_free_rate=RISK_FREE_RATE,
        max_stocks=max_stocks,
        max_per_sector=max_per_sector,
        price_basis=PRICE_BASIS,
        return_type=RETURN_TYPE,
    )

    comparison = compare_with_benchmark(
        portfolio["daily_returns"],
        benchmark,
    )

    return {
        "symbols": list(symbols),
        "metrics": scalar_metrics(portfolio),
        "portfolio_return_pct": comparison["portfolio_return_pct"],
        "benchmark_return_pct": comparison["benchmark_return_pct"],
        "excess_return_pct": comparison["excess_return_pct"],
        "common_return_observations": comparison[
            "common_return_observations"
        ],
        "metadata": portfolio["metadata"],
    }


def generate_random_portfolios(
    symbols,
    sectors,
    count=RANDOM_PORTFOLIO_COUNT,
    seed=RANDOM_SEED,
):
    """Generate unique random portfolios respecting sector limits."""

    rng = random.Random(seed)
    symbols = list(symbols)

    portfolios = set()
    attempts = 0
    max_attempts = count * 10000

    while len(portfolios) < count and attempts < max_attempts:
        attempts += 1
        candidate = tuple(sorted(rng.sample(symbols, TARGET_STOCKS)))

        sector_counts = {}
        for symbol in candidate:
            sector = sectors[symbol]
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

        if all(
            amount <= MAX_PER_SECTOR
            for amount in sector_counts.values()
        ):
            portfolios.add(candidate)

    if len(portfolios) != count:
        raise RuntimeError(
            f"Generated only {len(portfolios)} of {count} "
            "requested unique valid portfolios."
        )

    return sorted(portfolios)


def summarize_random_results(rows):
    """Summarize the distribution of random portfolio outcomes."""

    frame = pd.DataFrame(rows)

    summary = {}

    columns = [
        "portfolio_return_pct",
        "excess_return_pct",
        "sharpe_ratio",
        "annualized_volatility_pct",
        "maximum_drawdown_pct",
    ]

    for column in columns:
        values = pd.to_numeric(
            frame[column],
            errors="coerce",
        ).dropna()

        summary[column] = {
            "mean": float(values.mean()),
            "median": float(values.median()),
            "p05": float(values.quantile(0.05)),
            "p95": float(values.quantile(0.95)),
            "minimum": float(values.min()),
            "maximum": float(values.max()),
        }

    summary["portfolios_count"] = len(frame)

    return summary


def run_period_comparison(
    period_name,
    prices,
    benchmark,
    sectors,
    greedy_symbols,
    random_portfolios,
):
    print(f"\nBASELINE COMPARISON — {period_name}")
    print("-" * 65)

    # Greedy V2: fixed training-selected stocks.
    greedy = evaluate_portfolio(
        prices,
        benchmark,
        sectors,
        greedy_symbols,
        TARGET_STOCKS,
        MAX_PER_SECTOR,
    )

    # All 50 NIFTY constituents, equal weighted.
    sector_counts = {}
    for symbol in prices.columns:
        sector = sectors[symbol]
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    all_50 = evaluate_portfolio(
        prices,
        benchmark,
        sectors,
        list(prices.columns),
        max_stocks=len(prices.columns),
        max_per_sector=max(sector_counts.values()),
    )

    # Random valid 10-stock portfolios.
    random_rows = []

    for index, symbols in enumerate(random_portfolios, start=1):
        result = evaluate_portfolio(
            prices,
            benchmark,
            sectors,
            symbols,
            TARGET_STOCKS,
            MAX_PER_SECTOR,
        )

        random_rows.append({
            "portfolio_id": index,
            "symbols": ",".join(symbols),
            "portfolio_return_pct": result["portfolio_return_pct"],
            "benchmark_return_pct": result["benchmark_return_pct"],
            "excess_return_pct": result["excess_return_pct"],
            "sharpe_ratio": result["metrics"]["sharpe_ratio"],
            "annualized_volatility_pct": result["metrics"][
                "annualized_volatility_pct"
            ],
            "maximum_drawdown_pct": result["metrics"][
                "maximum_drawdown_pct"
            ],
        })

    random_summary = summarize_random_results(random_rows)

    print(
        f"Greedy V2 excess return: "
        f"{greedy['excess_return_pct']:.4f} pp"
    )
    print(
        f"Equal-weight 50 excess return: "
        f"{all_50['excess_return_pct']:.4f} pp"
    )
    print(
        f"Random median excess return: "
        f"{random_summary['excess_return_pct']['median']:.4f} pp"
    )
    print(
        f"Random 5th–95th percentile: "
        f"{random_summary['excess_return_pct']['p05']:.4f} to "
        f"{random_summary['excess_return_pct']['p95']:.4f} pp"
    )

    return {
        "period": period_name,
        "greedy_v2": greedy,
        "equal_weight_all_50": all_50,
        "random_portfolios": random_summary,
        "random_portfolio_rows": random_rows,
    }


def main():
    print("\nGREEDY STOCKS — V2 BASELINE COMPARISON")
    print("=" * 65)

    dataset = prepare_greedy_v2_dataset(
        start_date="2025-04-01",
        end_date="2026-11-05",
    )

    prices = dataset.adjusted_prices.copy()
    benchmark = dataset.benchmark_prices.copy()
    sectors = dataset.sectors

    if not prices.index.equals(benchmark.index):
        raise ValueError("Stock and benchmark dates are not aligned.")

    splits = chronological_split(
        prices,
        train_fraction=0.60,
        validation_fraction=0.20,
    )

    train_benchmark = benchmark.loc[splits.train.index]
    validation_benchmark = benchmark.loc[splits.validation.index]
    test_benchmark = benchmark.loc[splits.test.index]

    # Select stocks from training data only.
    selection = greedy_select_stocks(
        train_prices=splits.train,
        sectors=sectors,
        target_stocks=TARGET_STOCKS,
        max_per_sector=MAX_PER_SECTOR,
        risk_free_rate=RISK_FREE_RATE,
    )

    greedy_symbols = selection.get("selected_symbols")
    if greedy_symbols is None:
        greedy_symbols = selection.get("selected_stocks")

    if greedy_symbols is None:
        raise KeyError(
            f"Selected symbols not found: {list(selection.keys())}"
        )

    greedy_symbols = list(greedy_symbols)

    if len(greedy_symbols) != TARGET_STOCKS:
        raise ValueError("Incorrect Greedy V2 portfolio size.")

    # Random portfolios are generated independently of validation/test.
    random_portfolios = generate_random_portfolios(
        symbols=prices.columns,
        sectors=sectors,
    )

    print(f"\nRandom portfolios generated: {len(random_portfolios)}")
    print(f"Random seed: {RANDOM_SEED}")
    print(f"Greedy V2 selection: {', '.join(greedy_symbols)}")

    validation = run_period_comparison(
        "VALIDATION",
        splits.validation,
        validation_benchmark,
        sectors,
        greedy_symbols,
        random_portfolios,
    )

    final_test = run_period_comparison(
        "FINAL_TEST",
        splits.test,
        test_benchmark,
        sectors,
        greedy_symbols,
        random_portfolios,
    )

    results = {
        "experiment": "GREEDY_V2_BASELINE_COMPARISON",
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "greedy_selected_symbols": greedy_symbols,
        "random_portfolio_count": len(random_portfolios),
        "random_seed": RANDOM_SEED,
        "constraints": {
            "target_stocks": TARGET_STOCKS,
            "max_per_sector": MAX_PER_SECTOR,
            "risk_free_rate": RISK_FREE_RATE,
        },
        "data_metadata": dataset.metadata,
        "split_metadata": splits.metadata,
        "methodology": {
            "greedy_selection_uses_training_only": True,
            "random_selection_uses_training_returns": False,
            "validation_used_to_select_portfolios": False,
            "test_used_to_select_portfolios": False,
            "random_portfolios_unique": True,
            "portfolio_weighting": "EQUAL_WEIGHT",
            "rebalancing": "DAILY",
            "price_basis": PRICE_BASIS,
            "return_type": RETURN_TYPE,
            "dividend_adjusted": False,
            "corporate_action_coverage": "PARTIAL",
            "transaction_costs_included": False,
            "equal_weight_50_sector_cap": False,
            "database_writes": False,
        },
        "period_results": {
            "validation": validation,
            "final_test": final_test,
        },
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    json_path = OUTPUT_DIR / "greedy_v2_baseline_comparison.json"
    csv_path = OUTPUT_DIR / "greedy_v2_random_baselines.csv"

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(
            safe_value(results),
            file,
            indent=2,
            allow_nan=False,
        )

    random_frames = []

    for period_name, period_result in [
        ("VALIDATION", validation),
        ("FINAL_TEST", final_test),
    ]:
        frame = pd.DataFrame(
            period_result["random_portfolio_rows"]
        )
        frame.insert(0, "period", period_name)
        random_frames.append(frame)

    pd.concat(
        random_frames,
        ignore_index=True,
    ).to_csv(csv_path, index=False)

    print("\nOUTPUT FILES")
    print(json_path)
    print(csv_path)
    print("\nDatabase writes: NONE")
    print("BASELINE COMPARISON: COMPLETE")


if __name__ == "__main__":
    main()
