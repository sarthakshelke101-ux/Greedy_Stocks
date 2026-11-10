from pathlib import Path
import sys
import json
import hashlib
import contextlib
import io

import numpy as np
import pandas as pd
from scipy.stats import skew, kurtosis

ROOT = Path(__file__).resolve().parents[1]
ANALYTICS = ROOT / "analytics"
OUTPUT = ROOT / "database" / "processed" / "analytics"

sys.path.insert(0, str(ANALYTICS))

from greedy_v2_data import prepare_greedy_v2_dataset
from greedy_v2_splits import chronological_split
from greedy_v2_engine import greedy_select_stocks
from portfolio_analytics import calculate_portfolio
from validation.trial_registry import append_trial, read_trials
from validation.deflated_sharpe import deflated_sharpe
from validation.pbo_cscv import estimate_pbo


START_DATE = "2025-04-01"
END_DATE = "2026-11-05"
RISK_FREE_RATE = 0.0
PRICE_BASIS = "SPLIT_BONUS_ADJUSTED"
RETURN_TYPE = "PRICE_RETURN"


def select_top_weight(constituents, eligible, count=10, sector_cap=3):
    required = {"symbol", "sector", "weightage"}
    if not required.issubset(constituents.columns):
        raise ValueError(
            f"Constituent data missing columns: {required - set(constituents.columns)}"
        )

    selected = []
    counts = {}

    rows = constituents.sort_values("weightage", ascending=False)

    for _, row in rows.iterrows():
        symbol = row["symbol"]
        sector = row["sector"]

        if symbol not in eligible:
            continue
        if counts.get(sector, 0) >= sector_cap:
            continue

        selected.append(symbol)
        counts[sector] = counts.get(sector, 0) + 1

        if len(selected) == count:
            break

    if len(selected) != count:
        raise ValueError("Could not construct top-weight baseline.")

    return selected


def make_greedy(train, sectors, count, cap):
    # Suppress verbose selection logs; selection logic remains unchanged.
    with contextlib.redirect_stdout(io.StringIO()):
        result = greedy_select_stocks(
            train_prices=train,
            sectors=sectors,
            target_stocks=count,
            max_per_sector=cap,
            risk_free_rate=RISK_FREE_RATE,
        )

    symbols = (
        result.get("selected_symbols")
        or result.get("selected_stocks")
    )
    if not symbols or len(symbols) != count:
        raise ValueError(f"Invalid GREEDY selection for {count}/{cap}.")

    return list(symbols)


def calculate_returns(prices, sectors, symbols):
    result = calculate_portfolio(
        prices=prices,
        sectors={s: sectors[s] for s in symbols},
        symbols=symbols,
        risk_free_rate=RISK_FREE_RATE,
        max_stocks=len(symbols),
        max_per_sector=max(
            sum(sectors[s] == sector for s in symbols)
            for sector in {sectors[s] for s in symbols}
        ),
        price_basis=PRICE_BASIS,
        return_type=RETURN_TYPE,
    )
    return result["daily_returns"]


def stable_id(config, dates, values):
    payload = json.dumps(
        {
            "algorithm": "GREEDY_STOCKS_VALIDATION",
            "config": config,
            "dates": dates,
            "returns": [float(x) for x in values],
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return "validation-" + hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()[:24]


def main():
    print("\nGREEDY STOCKS — MULTI-STRATEGY VALIDATION")
    print("=" * 70)

    OUTPUT.mkdir(parents=True, exist_ok=True)

    # 1. Prepare data and chronological splits.
    dataset = prepare_greedy_v2_dataset(
        start_date=START_DATE,
        end_date=END_DATE,
    )

    prices = dataset.adjusted_prices.copy()
    benchmark = dataset.benchmark_prices.copy()
    sectors = dataset.sectors

    common_dates = prices.index.intersection(benchmark.index).sort_values()
    excluded_benchmark_dates = benchmark.index.difference(prices.index)

    prices = prices.loc[common_dates]
    benchmark = benchmark.loc[common_dates]

    splits = chronological_split(
        prices,
        train_fraction=0.60,
        validation_fraction=0.20,
        allow_sparse_evaluation=True,
    )

    print("\nDATA")
    print("Price dates:", len(prices))
    print("Training:", len(splits.train))
    print("Validation:", len(splits.validation) - 1)
    print("Final test:", len(splits.test) - 1)
    print("Training-eligible stocks:", len(splits.train.columns))
    print("Excluded benchmark-only dates:",
          [str(d.date()) for d in excluded_benchmark_dates])
    print("Excluded incomplete training stocks:",
          splits.metadata["excluded_incomplete_training_symbols"])

    train = splits.train
    test = splits.test
    eligible = list(train.columns)

    # 2. Generate predeclared strategy configurations.
    strategies = {}

    configurations = [
        (5, 2),
        (10, 2),
        (10, 3),
        (10, 5),
        (15, 3),
    ]

    for count, cap in configurations:
        name = f"GREEDY_T{count}_S{cap}"
        selected = make_greedy(train, sectors, count, cap)
        strategies[name] = {
            "symbols": selected,
            "algorithm": "GREEDY_V2",
            "config": {
                "target_stocks": count,
                "max_per_sector": cap,
                "risk_free_rate": RISK_FREE_RATE,
                "price_basis": PRICE_BASIS,
                "return_type": RETURN_TYPE,
                "selected_symbols": selected,
            },
        }

    top10 = select_top_weight(
        dataset.constituents,
        set(eligible),
        count=10,
        sector_cap=3,
    )

    strategies["TOP10_INDEX_WEIGHT"] = {
        "symbols": top10,
        "algorithm": "TOP_WEIGHT_BASELINE",
        "config": {"selected_symbols": top10, "sector_cap": 3},
    }

    equal_symbols = eligible.copy()
    strategies["EQUAL_WEIGHT_UNIVERSE"] = {
        "symbols": equal_symbols,
        "algorithm": "EQUAL_WEIGHT_BASELINE",
        "config": {"selected_symbols": equal_symbols},
    }

    # 3. Calculate every strategy's daily test returns.
    return_series = {}
    selection_rows = []

    for name, item in strategies.items():
        symbols = item["symbols"]
        returns = calculate_returns(test, sectors, symbols)
        return_series[name] = returns

        selection_rows.append({
            "strategy": name,
            "algorithm": item["algorithm"],
            "stock_count": len(symbols),
            "selected_symbols": ",".join(symbols),
        })

        print(f"{name:25} {len(symbols):2} stocks | "
              f"{len(returns):3} return observations")

    # 4. Align all strategies on identical dates.
    returns_frame = pd.concat(return_series, axis=1)
    original_observations = len(returns_frame)
    returns_frame = returns_frame.dropna(how="any")

    if len(returns_frame) < 12:
        raise ValueError(
            "Fewer than 12 common return observations; "
            "cannot run meaningful six-slice CSCV."
        )

    if not np.isfinite(returns_frame.to_numpy(dtype=float)).all():
        raise ValueError("Non-finite values in common return matrix.")

    print("\nCOMMON-DATE COMPARISON")
    print("Before alignment:", original_observations)
    print("After alignment:", len(returns_frame))
    print("Start:", returns_frame.index[0].date())
    print("End:", returns_frame.index[-1].date())

    # 5. Register reproducible trials. Identical trials are skipped.
    existing_ids = {
        item["trial_id"] for item in read_trials()
    }

    common_dates_text = [
        str(d.date()) for d in returns_frame.index
    ]

    registered = 0
    skipped = 0

    for name, item in strategies.items():
        aligned_values = returns_frame[name].tolist()
        trial_id = stable_id(
            item["config"],
            common_dates_text,
            aligned_values,
        )

        if trial_id in existing_ids:
            skipped += 1
            continue

        append_trial(
            algorithm=item["algorithm"],
            config=item["config"],
            daily_returns=aligned_values,
            dates=common_dates_text,
            trial_id=trial_id,
            metadata={
                "strategy_name": name,
                "period": "OBSERVED_FINAL_TEST",
                "start_date": common_dates_text[0],
                "end_date": common_dates_text[-1],
                "membership_basis": "LATEST_MONTHLY_SNAPSHOT",
                "transaction_costs_included": False,
                "dividends_included": False,
                "comparison_dates": "COMMON_INTERSECTION",
                "historical_holdout_already_observed": True,
            },
        )
        existing_ids.add(trial_id)
        registered += 1

    print("\nTRIAL REGISTRY")
    print("New trials:", registered)
    print("Duplicates skipped:", skipped)
    print("Total registry records:", len(read_trials()))

    # 6. Calculate strategy metrics and DSR diagnostics.
    metric_rows = []
    n_trials = len(strategies)
    n_obs = len(returns_frame)

    # IID null approximation for the standard deviation of a
    # per-observation Sharpe estimate. Not a serial-correlation correction.
    sharpe_std_iid = 1.0 / np.sqrt(n_obs)

    for name in returns_frame.columns:
        values = returns_frame[name].to_numpy(dtype=float)
        volatility = float(np.std(values, ddof=1))

        if volatility <= 0:
            raise ValueError(f"Zero volatility for {name}")

        daily_sharpe = float(np.mean(values) / volatility)
        annualized_sharpe = daily_sharpe * np.sqrt(252)

        dsr_result = deflated_sharpe(
            observed_sharpe=daily_sharpe,
            n_observations=n_obs,
            n_trials=n_trials,
            skewness=float(skew(values, bias=False)),
            kurtosis=float(kurtosis(values, fisher=False, bias=False)),
            sharpe_std=sharpe_std_iid,
        )

        metric_rows.append({
            "strategy": name,
            "observations": n_obs,
            "total_return_pct": float(
                ((1 + values).prod() - 1) * 100
            ),
            "daily_sharpe": daily_sharpe,
            "annualized_sharpe": annualized_sharpe,
            "annualized_volatility_pct": float(
                volatility * np.sqrt(252) * 100
            ),
            "maximum_drawdown_pct": float(
                ((1 + pd.Series(values)).cumprod()
                 / (1 + pd.Series(values)).cumprod().cummax()
                 - 1).min() * 100
            ),
            "dsr_iid_diagnostic": dsr_result["dsr"],
            "dsr_expected_max_daily_sharpe": (
                dsr_result["expected_max_sharpe"]
            ),
        })

    metrics = pd.DataFrame(metric_rows).sort_values(
        "annualized_sharpe", ascending=False
    )

    # 7. PBO / CSCV across the common daily-return matrix.
    pbo_result = estimate_pbo(
        returns_frame,
        n_slices=6,
    )

    # 8. Export machine-readable results.
    returns_output = returns_frame.copy()
    returns_output.index.name = "trade_date"
    returns_output.to_csv(OUTPUT / "multi_strategy_daily_returns.csv")

    metrics.to_csv(
        OUTPUT / "multi_strategy_validation_metrics.csv",
        index=False,
    )

    pd.DataFrame(selection_rows).to_csv(
        OUTPUT / "multi_strategy_selections.csv",
        index=False,
    )

    report = {
        "experiment": "GREEDY_STOCKS_MULTI_STRATEGY_VALIDATION",
        "period": {
            "start": common_dates_text[0],
            "end": common_dates_text[-1],
            "common_return_observations": n_obs,
            "benchmark_only_dates_excluded": [
                str(d.date()) for d in excluded_benchmark_dates
            ],
        },
        "data": {
            "training_start": splits.metadata["train_start"],
            "training_end": splits.metadata["train_end"],
            "validation_start": splits.metadata["validation_start"],
            "validation_end": splits.metadata["validation_end"],
            "test_start": splits.metadata["test_start"],
            "test_end": splits.metadata["test_end"],
            "training_eligible_symbols": eligible,
            "excluded_incomplete_training_symbols":
                splits.metadata["excluded_incomplete_training_symbols"],
            "forward_filling": False,
            "database_writes": False,
        },
        "strategy_count": n_trials,
        "strategies": selection_rows,
        "metrics": metric_rows,
        "pbo_cscv": pbo_result,
        "dsr_methodology": {
            "method": "PSR against expected maximum Sharpe",
            "sharpe_frequency": "daily",
            "sharpe_std": sharpe_std_iid,
            "sharpe_std_basis": "1/sqrt(number of observations), IID null approximation",
            "assumptions": [
                "IID return approximation",
                "Independent trial approximation",
                "Strategies are correlated; nominal trial count may overstate independent trials",
                "No serial-correlation correction",
            ],
            "interpretation": (
                "Exploratory diagnostic only; not confirmatory evidence."
            ),
        },
        "pbo_methodology": {
            "method": "CSCV",
            "slices": 6,
            "splits": pbo_result["splits"],
            "interpretation": (
                "Retrospective overfitting diagnostic, not a live holdout."
            ),
        },
        "limitations": [
            "The final test period has already been observed.",
            "Latest constituent snapshot introduces survivorship bias.",
            "Dividends are excluded.",
            "Corporate-action coverage is partial.",
            "Transaction costs and slippage are excluded.",
            "Equal-weight daily rebalancing is assumed.",
            "Strategies share data and are statistically dependent.",
            "DSR IID assumptions may not hold for daily financial returns.",
        ],
    }

    with (OUTPUT / "multi_strategy_validation_report.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(report, file, indent=2, allow_nan=False)

    print("\nSTRATEGY RANKING")
    print("=" * 95)
    print(metrics.to_string(index=False))

    print("\nPBO / CSCV")
    print("PBO:", round(pbo_result["pbo"], 4))
    print("Splits:", pbo_result["splits"])
    print("Strategies:", pbo_result["n_strategies"])

    print("\nFILES SAVED")
    print(OUTPUT / "multi_strategy_daily_returns.csv")
    print(OUTPUT / "multi_strategy_validation_metrics.csv")
    print(OUTPUT / "multi_strategy_selections.csv")
    print(OUTPUT / "multi_strategy_validation_report.json")

    print("\nWARNING: retrospective final-test analysis.")
    print("DSR is an IID diagnostic, not a calibrated independent-trial proof.")
    print("No database writes performed.")
    print("\nMULTI-STRATEGY VALIDATION: COMPLETE")


if __name__ == "__main__":
    main()
