from pathlib import Path
import sys, json, contextlib, io
import numpy as np
import pandas as pd

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "analytics"))

from greedy_v2_data import prepare_greedy_v2_dataset
from greedy_v2_engine import greedy_select_stocks

OUT = ROOT / "database" / "processed" / "analytics"
OUT.mkdir(parents=True, exist_ok=True)

START_DATE = "2025-04-01"
END_DATE = "2026-11-05"
INITIAL_TRAIN = 120
TEST_WINDOW = 30
STEP = 30
TARGET_STOCKS = 10
SECTOR_CAP = 3
COST_BPS = [0, 10, 20, 30]


def select_top_weight(constituents, eligible):
    required = {"symbol", "sector", "weightage"}
    if not required.issubset(constituents.columns):
        raise ValueError(f"Missing constituent columns: {required - set(constituents.columns)}")

    selected, counts = [], {}
    for _, row in constituents.sort_values(
        "weightage", ascending=False
    ).iterrows():
        symbol, sector = row["symbol"], row["sector"]
        if symbol not in eligible:
            continue
        if counts.get(sector, 0) >= SECTOR_CAP:
            continue
        selected.append(symbol)
        counts[sector] = counts.get(sector, 0) + 1
        if len(selected) == TARGET_STOCKS:
            break

    if len(selected) != TARGET_STOCKS:
        raise ValueError("Unable to construct TOP 10 baseline.")
    return selected


def simulate_daily_rebalanced(prices, symbols, cost_bps):
    """
    Equal-weight daily rebalancing.
    Transaction costs are charged on one-way turnover.
    Initial portfolio entry turnover = 100%.
    """
    block = prices[symbols].copy()
    asset_returns = block.pct_change(fill_method=None).iloc[1:]

    if asset_returns.empty or asset_returns.isna().any().any():
        raise ValueError("Missing returns in evaluation period.")

    values = asset_returns.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Non-finite asset returns.")

    n_assets = len(symbols)
    target = np.full(n_assets, 1.0 / n_assets)

    gross = values @ target
    turnover = np.zeros(len(values))
    turnover[0] = 1.0

    for i in range(1, len(values)):
        previous_asset_returns = values[i - 1]
        previous_gross = gross[i - 1]

        denominator = 1.0 + previous_gross
        if denominator <= 0:
            raise ValueError("Invalid portfolio value.")

        drifted = target * (1.0 + previous_asset_returns) / denominator
        turnover[i] = 0.5 * np.abs(target - drifted).sum()

    cost_rate = cost_bps / 10000.0
    net = gross - cost_rate * turnover

    return pd.Series(net, index=asset_returns.index), pd.Series(
        turnover, index=asset_returns.index
    )


def metrics(series):
    x = np.asarray(series, dtype=float)
    if len(x) < 2 or not np.isfinite(x).all():
        raise ValueError("Invalid return series.")
    if (x <= -1).any():
        raise ValueError("Return at or below -100%.")

    vol = np.std(x, ddof=1)
    sharpe = float(np.mean(x) / vol * np.sqrt(252)) if vol > 0 else None
    curve = np.cumprod(1.0 + x)
    peak = np.maximum.accumulate(curve)
    drawdown = curve / peak - 1.0

    return {
        "observations": int(len(x)),
        "total_return_pct": float((curve[-1] - 1) * 100),
        "annualized_sharpe": sharpe,
        "annualized_volatility_pct": float(vol * np.sqrt(252) * 100),
        "maximum_drawdown_pct": float(drawdown.min() * 100),
    }


def main():
    print("\nGREEDY STOCKS — WALK-FORWARD + COST VALIDATION")
    print("=" * 76)

    dataset = prepare_greedy_v2_dataset(
        start_date=START_DATE,
        end_date=END_DATE,
    )

    prices = dataset.adjusted_prices.copy().sort_index()
    benchmark = dataset.benchmark_prices.copy().sort_index()
    sectors = dataset.sectors

    # Use a fixed universe eligible at the first 120-observation checkpoint.
    initial = prices.iloc[:INITIAL_TRAIN]
    universe = [
        symbol for symbol in initial.columns
        if initial[symbol].notna().all()
        and np.isfinite(initial[symbol].to_numpy(dtype=float)).all()
        and (initial[symbol] > 0).all()
        and symbol in sectors
    ]

    if len(universe) < TARGET_STOCKS:
        raise ValueError("Insufficient complete initial training universe.")

    prices = prices[universe]
    benchmark = benchmark.reindex(prices.index)

    print("Universe:", len(universe))
    print("Date range:", prices.index.min().date(), "to", prices.index.max().date())
    print("Initial training observations:", INITIAL_TRAIN)
    print("Test window:", TEST_WINDOW)
    print("Step:", STEP)
    print("Transaction costs (bps):", COST_BPS)

    fold_rows = []
    selection_rows = []
    daily_rows = []
    fold_number = 0

    # Both modes use the same test dates for direct comparison.
    for train_end in range(
        INITIAL_TRAIN,
        len(prices),
        STEP,
    ):
        test_end = min(train_end + TEST_WINDOW, len(prices))
        if test_end - train_end < 2:
            continue

        fold_number += 1

        expanding_train = prices.iloc[:train_end]
        rolling_train = prices.iloc[max(0, train_end - INITIAL_TRAIN):train_end]

        # Include the previous close so the first test-day return is valid.
        test_prices = prices.iloc[train_end - 1:test_end]
        test_dates = test_prices.index[1:]

        # Include the previous training-day close when calculating
        # the first test-day benchmark return. This preserves all 30
        # intended test observations.
        benchmark_window = benchmark.reindex(test_prices.index)
        benchmark_returns = benchmark_window.pct_change(
            fill_method=None
        ).iloc[1:]

        if benchmark_returns.isna().any():
            valid_dates = benchmark_returns.dropna().index
            test_prices = test_prices.loc[
                [test_prices.index[0], *valid_dates]
            ]
            test_dates = valid_dates
            benchmark_test = benchmark_returns.loc[valid_dates]
        else:
            benchmark_test = benchmark_returns

        if len(test_dates) < 2:
            print(f"Fold {fold_number}: skipped, insufficient benchmark dates.")
            continue

        print(
            f"\nFOLD {fold_number}: "
            f"train end={prices.index[train_end - 1].date()} | "
            f"test={test_dates[0].date()} to {test_dates[-1].date()}"
        )

        modes = {
            "EXPANDING": expanding_train,
            "ROLLING_120": rolling_train,
        }

        for mode, train in modes.items():
            if train.isna().any().any():
                raise ValueError(f"{mode} training matrix has missing values.")

            with contextlib.redirect_stdout(io.StringIO()):
                result = greedy_select_stocks(
                    train_prices=train,
                    sectors=sectors,
                    target_stocks=TARGET_STOCKS,
                    max_per_sector=SECTOR_CAP,
                    risk_free_rate=0.0,
                )

            greedy_symbols = result["selected_symbols"]
            top_symbols = select_top_weight(
                dataset.constituents,
                set(universe),
            )

            strategies = {
                "GREEDY_V2": greedy_symbols,
                "TOP10_INDEX_WEIGHT_SELECTED": top_symbols,
                "EQUAL_WEIGHT_UNIVERSE": universe,
            }

            for strategy, symbols in strategies.items():
                selection_rows.append({
                    "fold": fold_number,
                    "mode": mode,
                    "strategy": strategy,
                    "training_observations": len(train),
                    "training_start": str(train.index[0].date()),
                    "training_end": str(train.index[-1].date()),
                    "test_start": str(test_dates[0].date()),
                    "test_end": str(test_dates[-1].date()),
                    "symbols": ",".join(symbols),
                })

                # All strategies use identical test dates.
                block = test_prices[symbols]
                if block.isna().any().any():
                    raise ValueError(
                        f"Missing test prices: fold={fold_number}, "
                        f"mode={mode}, strategy={strategy}"
                    )

                for bps in COST_BPS:
                    net_returns, turnover = simulate_daily_rebalanced(
                        block, symbols, bps
                    )

                    # The first observation is the first test date.
                    net_returns = net_returns.reindex(test_dates)
                    turnover = turnover.reindex(test_dates)

                    if net_returns.isna().any():
                        raise ValueError("Return alignment failed.")

                    m = metrics(net_returns)
                    benchmark_metrics = metrics(benchmark_test)

                    fold_rows.append({
                        "fold": fold_number,
                        "mode": mode,
                        "strategy": strategy,
                        "cost_bps": bps,
                        "stock_count": len(symbols),
                        **m,
                        "benchmark_return_pct":
                            benchmark_metrics["total_return_pct"],
                        "excess_return_pp":
                            m["total_return_pct"]
                            - benchmark_metrics["total_return_pct"],
                        "average_daily_one_way_turnover_pct":
                            float(turnover.mean() * 100),
                        "cumulative_turnover_multiple":
                            float(turnover.sum()),
                    })

                    for date, value, turn in zip(
                        net_returns.index,
                        net_returns.values,
                        turnover.values,
                    ):
                        daily_rows.append({
                            "date": str(date.date()),
                            "fold": fold_number,
                            "mode": mode,
                            "strategy": strategy,
                            "cost_bps": bps,
                            "net_return": float(value),
                            "one_way_turnover": float(turn),
                        })

            print(
                f"{mode:12} | train={len(train):3} | "
                f"Greedy: {', '.join(greedy_symbols)}"
            )

    if not fold_rows:
        raise RuntimeError("No walk-forward folds completed.")

    fold_df = pd.DataFrame(fold_rows)
    selection_df = pd.DataFrame(selection_rows)
    daily_df = pd.DataFrame(daily_rows)

    # Aggregate fold-level outcomes; do not concatenate overlapping fold returns.
    aggregate = (
        fold_df.groupby(["mode", "strategy", "cost_bps"])
        .agg(
            folds=("fold", "nunique"),
            mean_fold_return_pct=("total_return_pct", "mean"),
            median_fold_return_pct=("total_return_pct", "median"),
            mean_annualized_sharpe=("annualized_sharpe", "mean"),
            mean_max_drawdown_pct=("maximum_drawdown_pct", "mean"),
            mean_excess_return_pp=("excess_return_pp", "mean"),
            mean_turnover_pct=("average_daily_one_way_turnover_pct", "mean"),
        )
        .reset_index()
    )

    fold_df.to_csv(OUT / "walk_forward_fold_metrics.csv", index=False)
    selection_df.to_csv(OUT / "walk_forward_selections.csv", index=False)
    daily_df.to_csv(OUT / "walk_forward_daily_returns.csv", index=False)
    aggregate.to_csv(OUT / "walk_forward_aggregate_metrics.csv", index=False)

    report = {
        "experiment": "GREEDY_STOCKS_ROLLING_EXPANDING_WALK_FORWARD",
        "date_start": str(prices.index.min().date()),
        "date_end": str(prices.index.max().date()),
        "initial_training_observations": INITIAL_TRAIN,
        "test_window": TEST_WINDOW,
        "step": STEP,
        "fold_count": int(fold_df["fold"].nunique()),
        "universe": universe,
        "strategies": [
            "GREEDY_V2",
            "TOP10_INDEX_WEIGHT_SELECTED_EQUAL_WEIGHT",
            "EQUAL_WEIGHT_UNIVERSE",
        ],
        "training_modes": ["EXPANDING", "ROLLING_120"],
        "transaction_cost_bps": COST_BPS,
        "portfolio_method": "EQUAL_WEIGHT_DAILY_REBALANCED",
        "turnover_method": (
            "One-way turnover = half sum absolute difference between "
            "target weights and drifted weights; initial entry turnover=100%."
        ),
        "benchmark": "NIFTY price return",
        "limitations": [
            "Historical latest-constituent universe; survivorship bias remains.",
            "Dividends excluded.",
            "Corporate-action coverage is partial.",
            "Transaction costs are simplified bps estimates, not broker-specific fees.",
            "Daily equal-weight rebalancing is assumed.",
            "Historical period is already observed; not a fresh holdout.",
            "Fold-level returns are not concatenated into one continuous investor equity curve.",
            "TOP10 baseline selects by index weight but is equal-weighted after selection.",
        ],
        "database_writes": False,
        "trial_registry_writes": False,
        "algorithm_modified": False,
        "files": [
            "walk_forward_fold_metrics.csv",
            "walk_forward_selections.csv",
            "walk_forward_daily_returns.csv",
            "walk_forward_aggregate_metrics.csv",
        ],
    }

    with (OUT / "walk_forward_validation_report.json").open(
        "w", encoding="utf-8"
    ) as f:
        json.dump(report, f, indent=2, allow_nan=False)

    print("\nAGGREGATE RESULTS")
    print("=" * 100)
    print(aggregate.to_string(index=False))

    print("\nFOLD COUNT:", report["fold_count"])
    print("\nFILES SAVED:")
    for name in report["files"]:
        print(OUT / name)
    print(OUT / "walk_forward_validation_report.json")

    print("\nWALK-FORWARD VALIDATION COMPLETE")
    print("No algorithm changes. No database writes. No trial registry writes.")


if __name__ == "__main__":
    main()
