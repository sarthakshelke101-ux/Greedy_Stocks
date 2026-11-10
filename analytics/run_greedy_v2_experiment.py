
"""Run a chronological, out-of-sample Greedy V2 experiment."""

import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

from analytics.greedy_v2_data import prepare_greedy_v2_dataset
from analytics.greedy_v2_splits import chronological_split
from analytics.greedy_v2_engine import greedy_select_stocks
from analytics.portfolio_analytics import (
    calculate_portfolio,
    compare_with_benchmark,
)
from analytics.validation.trial_registry import append_trial, DEFAULT_PATH


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "database" / "processed" / "analytics"

TARGET_STOCKS = 10
MAX_PER_SECTOR = 3
RISK_FREE_RATE = 0.0

PRICE_BASIS = "SPLIT_BONUS_ADJUSTED"
RETURN_TYPE = "PRICE_RETURN"


def json_safe(value):
    """Convert supported objects into JSON-compatible values."""

    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if hasattr(value, "item"):
        return value.item()

    return value


def scalar_metrics(portfolio):
    """Return scalar financial metrics without pandas objects."""

    metrics = portfolio["metrics"]
    output = {}

    for key, value in metrics.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            output[key] = value

    return output


def evaluate_period(name, prices, benchmark, sectors, symbols):
    """Evaluate a fixed stock selection on one historical period."""

    portfolio = calculate_portfolio(
        prices=prices,
        sectors=sectors,
        symbols=symbols,
        risk_free_rate=RISK_FREE_RATE,
        max_stocks=TARGET_STOCKS,
        max_per_sector=MAX_PER_SECTOR,
        price_basis=PRICE_BASIS,
        return_type=RETURN_TYPE,
    )

    comparison = compare_with_benchmark(
        portfolio["daily_returns"],
        benchmark,
    )

    return {
        "period": name,
        "start_date": str(
            portfolio["daily_returns"].index[0].date()
        ),
        "end_date": str(
            portfolio["daily_returns"].index[-1].date()
        ),
        "return_observations": len(
            portfolio["daily_returns"]
        ),
        "portfolio_metrics": scalar_metrics(portfolio),
        "benchmark_comparison": {
            "portfolio_return_pct": comparison[
                "portfolio_return_pct"
            ],
            "benchmark_return_pct": comparison[
                "benchmark_return_pct"
            ],
            "excess_return_pct": comparison[
                "excess_return_pct"
            ],
            "common_return_observations": comparison[
                "common_return_observations"
            ],
            "benchmark_basis": comparison[
                "benchmark_basis"
            ],
        },
        "portfolio_metadata": portfolio["metadata"],
    }


def main():
    print("\nGREEDY STOCKS — V2 REAL-WORLD EXPERIMENT")
    print("=" * 65)

    # ---------------------------------------------------------
    # 1. Load historical dataset
    # ---------------------------------------------------------

    dataset = prepare_greedy_v2_dataset(
        start_date="2016-11-08",
        end_date="2026-11-05",
    )

    prices = dataset.adjusted_prices.copy()
    benchmark = dataset.benchmark_prices.copy()
    sectors = dataset.sectors

    # Explicit common-date alignment. Never forward-fill or invent prices.
    stock_dates = prices.index
    benchmark_only_dates = benchmark.index.difference(stock_dates)
    stock_only_dates = stock_dates.difference(benchmark.index)
    common_dates = stock_dates.intersection(benchmark.index).sort_values()

    if len(common_dates) == 0:
        raise ValueError("No common stock and benchmark dates.")

    prices = prices.loc[common_dates].copy()
    benchmark = benchmark.loc[common_dates].copy()

    print("\\nBENCHMARK DATE-ALIGNMENT AUDIT")
    print("Common dates:", len(common_dates))
    print("Excluded benchmark-only dates:",
          [str(d.date()) for d in benchmark_only_dates])
    print("Excluded stock-only dates:",
          [str(d.date()) for d in stock_only_dates])
    print("Forward filling: False")

    if not prices.index.equals(benchmark.index):
        raise ValueError("Date alignment failed after intersection.")

    if prices.shape[1] < TARGET_STOCKS:
        raise ValueError(
            f"Only {prices.shape[1]} eligible companies; "
            f"portfolio requires {TARGET_STOCKS}."
        )

    if prices.empty:
        raise ValueError("Historical price dataset is empty.")

    print(f"\nCompanies: {prices.shape[1]}")
    print(f"Observations: {len(prices)}")
    print(
        f"Date range: {prices.index[0].date()} "
        f"to {prices.index[-1].date()}"
    )

    # ---------------------------------------------------------
    # 2. Chronological split
    # ---------------------------------------------------------

    splits = chronological_split(
        prices,
        train_fraction=0.60,
        validation_fraction=0.20,
        allow_sparse_evaluation=True,
    )

    # Use precisely the same dates for NIFTY 50.
    train_benchmark = benchmark.loc[splits.train.index]
    validation_benchmark = benchmark.loc[
        splits.validation.index
    ]
    test_benchmark = benchmark.loc[splits.test.index]

    print("\nCHRONOLOGICAL SPLITS")
    print("-" * 65)

    print(
        f"Training:   {splits.metadata['train_start']} to "
        f"{splits.metadata['train_end']} "
        f"({splits.metadata['train_observations']} observations)"
    )

    print(
        f"Validation: {splits.metadata['validation_start']} to "
        f"{splits.metadata['validation_end']} "
        f"({splits.metadata['validation_observations']} returns)"
    )

    print(
        f"Final test: {splits.metadata['test_start']} to "
        f"{splits.metadata['test_end']} "
        f"({splits.metadata['test_observations']} returns)"
    )

    # ---------------------------------------------------------
    # 3. Greedy selection using training data ONLY
    # ---------------------------------------------------------

    print("\nTRAINING-ONLY STOCK SELECTION")
    print("-" * 65)

    selection = greedy_select_stocks(
        train_prices=splits.train,
        sectors=sectors,
        target_stocks=TARGET_STOCKS,
        max_per_sector=MAX_PER_SECTOR,
        risk_free_rate=RISK_FREE_RATE,
    )

    selected_symbols = selection.get("selected_symbols")

    if selected_symbols is None:
        selected_symbols = selection.get("selected_stocks")

    if selected_symbols is None:
        raise KeyError(
            "Could not find selected symbols in Greedy V2 result. "
            f"Available keys: {list(selection.keys())}"
        )

    selected_symbols = list(selected_symbols)

    if len(selected_symbols) != TARGET_STOCKS:
        raise ValueError(
            f"Expected {TARGET_STOCKS} selected stocks, "
            f"received {len(selected_symbols)}."
        )

    if len(set(selected_symbols)) != len(selected_symbols):
        raise ValueError(
            "Greedy V2 returned duplicate stock symbols."
        )

    if any(
        symbol not in prices.columns
        for symbol in selected_symbols
    ):
        raise ValueError(
            "Selected stock is missing from the price matrix."
        )

    sector_counts = {}

    for symbol in selected_symbols:
        sector = sectors[symbol]
        sector_counts[sector] = (
            sector_counts.get(sector, 0) + 1
        )

    if any(
        count > MAX_PER_SECTOR
        for count in sector_counts.values()
    ):
        raise ValueError(
            "Greedy V2 violated the sector constraint."
        )

    print("\nSelected stocks:")

    for symbol in selected_symbols:
        print(f"  {symbol:<18} {sectors[symbol]}")

    # ---------------------------------------------------------
    # 4. Evaluate the fixed portfolio on all three periods
    # ---------------------------------------------------------

    print("\nEVALUATING TRAINING PERIOD")

    training_result = evaluate_period(
        "TRAINING",
        splits.train,
        train_benchmark,
        sectors,
        selected_symbols,
    )

    print("\nEVALUATING VALIDATION PERIOD")

    validation_result = evaluate_period(
        "VALIDATION",
        splits.validation,
        validation_benchmark,
        sectors,
        selected_symbols,
    )

    print("\nEVALUATING FINAL TEST PERIOD")

    test_result = evaluate_period(
        "FINAL_TEST",
        splits.test,
        test_benchmark,
        sectors,
        selected_symbols,
    )

    # Register the exact final-test daily return series.
    # This does not alter Greedy V2 selection or test-period evaluation.
    registry_portfolio = calculate_portfolio(
        prices=splits.test,
        sectors={s: sectors[s] for s in selected_symbols},
        symbols=selected_symbols,
        risk_free_rate=RISK_FREE_RATE,
        max_stocks=TARGET_STOCKS,
        max_per_sector=MAX_PER_SECTOR,
        price_basis=PRICE_BASIS,
        return_type=RETURN_TYPE,
    )

    registry_returns = registry_portfolio["daily_returns"]
    registry_dates = [str(d.date()) for d in registry_returns.index]

    import hashlib
    import json

    registry_config = {
        "target_stocks": TARGET_STOCKS,
        "max_per_sector": MAX_PER_SECTOR,
        "risk_free_rate": RISK_FREE_RATE,
        "price_basis": PRICE_BASIS,
        "return_type": RETURN_TYPE,
        "selected_symbols": list(selected_symbols),
    }

    identity_payload = json.dumps(
        {
            "algorithm": "GREEDY_V2",
            "config": registry_config,
            "dates": registry_dates,
            "returns": [float(x) for x in registry_returns.tolist()],
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

    # Keep a reproducible fingerprint for this exact experiment output, while
    # assigning a fresh trial ID to each execution. The registry rejects duplicate
    # trial IDs, so a content-only ID prevents legitimate reruns from being recorded.
    experiment_fingerprint = hashlib.sha256(
        identity_payload.encode("utf-8")
    ).hexdigest()

    execution_nonce = uuid.uuid4().hex
    trial_id = "greedy-v2-" + hashlib.sha256(
        f"{experiment_fingerprint}:{execution_nonce}".encode("utf-8")
    ).hexdigest()[:24]

    registry_record = append_trial(
        algorithm="GREEDY_V2",
        config=registry_config,
        daily_returns=registry_returns.tolist(),
        dates=registry_dates,
        trial_id=trial_id,
        metadata={
            "period": "FINAL_TEST",
            "experiment_fingerprint": experiment_fingerprint,
            "start_date": registry_dates[0],
            "end_date": registry_dates[-1],
            "observations": len(registry_returns),
            "membership_basis": "LATEST_MONTHLY_SNAPSHOT",
            "transaction_costs_included": False,
            "source_runner": "run_greedy_v2_experiment.py",
            "benchmark_only_dates_excluded": [
                str(d.date()) for d in benchmark_only_dates
            ],
            "stock_only_dates_excluded": [
                str(d.date()) for d in stock_only_dates
            ],
            "date_alignment": "COMMON_DATES_INTERSECTION",
        },
    )

    print("\\nTRIAL REGISTRY")
    print("Trial ID:", registry_record["trial_id"])
    print("Observations:", registry_record["observations"])

    # ---------------------------------------------------------
    # 5. Prepare experiment report
    # ---------------------------------------------------------

    results = {
        "experiment": "GREEDY_V2_CHRONOLOGICAL",
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "execution_metadata": {
            "trial_id": registry_record["trial_id"],
            "experiment_fingerprint": experiment_fingerprint,
            "registry_created_at_utc": registry_record["created_at_utc"],
            "registry_path": str(DEFAULT_PATH),
            "runner": "analytics/run_greedy_v2_experiment.py",
            "execution_status": "COMPLETED",
        },

        "selected_symbols": selected_symbols,
        "sector_allocation": sector_counts,

        "selection_constraints": {
            "target_stocks": TARGET_STOCKS,
            "max_per_sector": MAX_PER_SECTOR,
            "risk_free_rate": RISK_FREE_RATE,
        },

        "data_metadata": dataset.metadata,
        "split_metadata": splits.metadata,

        "methodology": {
            "selection_uses_training_only": True,
            "validation_used_for_selection": False,
            "test_used_for_selection": False,
            "portfolio_weighting": "EQUAL_WEIGHT",
            "rebalancing": "DAILY",
            "price_basis": PRICE_BASIS,
            "return_type": RETURN_TYPE,
            "dividend_adjusted": False,
            "corporate_action_coverage": "PARTIAL",
            "benchmark": "NIFTY_50_PRICE_RETURN",
            "membership_basis": "LATEST_MONTHLY_SNAPSHOT",
            "transaction_costs_included": False,
            "database_writes": False,
        },

        "period_results": {
            "training": training_result,
            "validation": validation_result,
            "final_test": test_result,
        },
    }

    # ---------------------------------------------------------
    # 6. Save experiment outputs
    # ---------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = (
        OUTPUT_DIR / "greedy_v2_experiment.json"
    )

    log_path = (
        OUTPUT_DIR / "greedy_v2_selection_log.csv"
    )

    with json_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            json_safe(results),
            file,
            indent=2,
            allow_nan=False,
        )

    selection_log = selection.get("selection_log")

    if isinstance(selection_log, pd.DataFrame):
        selection_frame = selection_log.copy()
    else:
        selection_frame = pd.DataFrame(selection_log)

    # Bind every row to this exact execution.
    selection_frame["trial_id"] = registry_record["trial_id"]
    selection_frame["experiment_fingerprint"] = experiment_fingerprint
    selection_frame["generated_at_utc"] = results["generated_at_utc"]
    selection_frame.to_csv(log_path, index=False)

    # ---------------------------------------------------------
    # 7. Print experiment summary
    # ---------------------------------------------------------

    print("\nEXPERIMENT SUMMARY")
    print("=" * 65)

    for name, result in [
        ("TRAINING", training_result),
        ("VALIDATION", validation_result),
        ("FINAL TEST", test_result),
    ]:
        comparison = result["benchmark_comparison"]

        print(f"\n{name}")

        print(
            f"  Portfolio return: "
            f"{comparison['portfolio_return_pct']:.4f}%"
        )

        print(
            f"  NIFTY 50 return:  "
            f"{comparison['benchmark_return_pct']:.4f}%"
        )

        print(
            f"  Excess return:    "
            f"{comparison['excess_return_pct']:.4f} pp"
        )

        print(
            f"  Common sessions:  "
            f"{comparison['common_return_observations']}"
        )

    # ---------------------------------------------------------
    # 8. Disclosures
    # ---------------------------------------------------------

    print("\nDISCLOSURES")
    print("-" * 65)

    print(
        "Historical experiment, not an investment recommendation."
    )
    print("No dividends or transaction costs included.")
    print("Corporate-action coverage is partial.")
    print(
        "Latest constituent snapshot creates survivorship-bias risk."
    )
    print(
        "Equal-weight portfolio assumes daily rebalancing."
    )
    print(
        "Greedy selection is heuristic, not globally optimal."
    )

    print("\nFILES SAVED")
    print(json_path)
    print(log_path)

    print("\nDatabase writes: NONE")
    print("GREEDY V2 EXPERIMENT: COMPLETE")


if __name__ == "__main__":
    main()
