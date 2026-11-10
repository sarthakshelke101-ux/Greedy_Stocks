"""Five-strategy GREEDY V2 research runner. Original V2 engine is not modified."""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from analytics.greedy_v2_data import prepare_greedy_v2_dataset
from analytics.greedy_v2_splits import chronological_split
from analytics.greedy_v2_engine import greedy_select_stocks
from analytics.portfolio_analytics import calculate_portfolio, compare_with_benchmark

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "database" / "processed" / "analytics" / "five_strategy_experiment"
TARGET_STOCKS = 10
MAX_PER_SECTOR = 3
RISK_FREE_RATE = 0.0
COST_BPS_PER_TURNOVER = 10.0
MIN_TRAIN_OBS = 60
STRATEGIES = [
    "GREEDY_V2_BASELINE",
    "RISK_AWARE",
    "DIVERSIFICATION_AWARE",
    "COST_AWARE",
    "STABILITY_BASED",
]


def stats(returns: pd.Series) -> dict:
    r = pd.to_numeric(returns, errors="coerce").dropna().astype(float)
    if len(r) < 2:
        raise ValueError("At least two daily returns required.")
    wealth = (1 + r).cumprod()
    peak = wealth.cummax()
    dd = wealth / peak - 1
    vol = float(r.std(ddof=1) * np.sqrt(252))
    sharpe = float((r.mean() * 252) / vol) if vol > 0 else 0.0
    return {
        "total_return_pct": float((wealth.iloc[-1] - 1) * 100),
        "annualized_volatility_pct": vol * 100,
        "sharpe_ratio": sharpe,
        "maximum_drawdown_pct": float(dd.min() * 100),
        "observations": int(len(r)),
    }


def trial_returns(prices, sectors, symbols):
    p = calculate_portfolio(
        prices=prices, sectors=sectors, symbols=symbols,
        risk_free_rate=RISK_FREE_RATE, max_stocks=TARGET_STOCKS,
        max_per_sector=MAX_PER_SECTOR, price_basis="SPLIT_BONUS_ADJUSTED",
        return_type="PRICE_RETURN",
    )
    return p["daily_returns"]


def turnover_cost_adjusted_sharpe(returns: pd.Series, bps: float) -> tuple[float, float]:
    # Approximate daily-rebalance turnover from portfolio weights drifting
    # after returns. Cost is charged on one-way traded notional.
    r = returns.astype(float)
    wealth = 1.0
    weights = np.repeat(1.0 / TARGET_STOCKS, TARGET_STOCKS)
    # Equal-weight daily rebalance implies roughly half the sum of absolute
    # deviations from target after each session. Use portfolio-level proxy
    # based on cross-sectional dispersion unavailable in portfolio returns;
    # therefore use a transparent conservative daily turnover assumption.
    # At minimum, a full rebalance cost proxy is 1/N of portfolio notional.
    daily_turnover = 1.0 - 1.0 / TARGET_STOCKS
    cost = daily_turnover * (bps / 10000.0)
    net = r - cost
    return stats(net)["sharpe_ratio"], cost * 100


def strategy_score(prices, sectors, selected, candidate, strategy, cost_bps):
    trial = selected + [candidate]
    ret = trial_returns(prices, sectors, trial)
    m = stats(ret)
    if strategy == "RISK_AWARE":
        # Penalise both annualised volatility and peak-to-trough drawdown.
        score = m["sharpe_ratio"] - 0.015 * m["annualized_volatility_pct"] - 0.02 * abs(m["maximum_drawdown_pct"])
    elif strategy == "DIVERSIFICATION_AWARE":
        stock_ret = prices[trial].pct_change(fill_method=None).dropna(how="any")
        corr = stock_ret.corr().abs().to_numpy()
        upper = corr[np.triu_indices_from(corr, k=1)]
        mean_corr = float(upper.mean()) if len(upper) else 0.0
        score = m["sharpe_ratio"] - 0.75 * mean_corr
    elif strategy == "COST_AWARE":
        net_sharpe, _ = turnover_cost_adjusted_sharpe(ret, cost_bps)
        score = net_sharpe
    elif strategy == "STABILITY_BASED":
        # Score the same trial portfolio over three chronological slices
        # of training data; reward mean Sharpe and penalise dispersion.
        chunks = [prices[trial].iloc[idx].copy() for idx in np.array_split(np.arange(len(prices)), 3) if len(idx) >= MIN_TRAIN_OBS]
        if len(chunks) < 2:
            score = m["sharpe_ratio"]
        else:
            sh = [stats(trial_returns(chunk, sectors, trial))["sharpe_ratio"] for chunk in chunks]
            score = float(np.mean(sh) - 0.5 * np.std(sh, ddof=0))
    else:
        raise ValueError(strategy)
    return float(score), m


def experimental_select(prices, sectors, strategy, cost_bps=COST_BPS_PER_TURNOVER):
    symbols = list(prices.columns)
    selected = []
    logs = []
    for step in range(1, TARGET_STOCKS + 1):
        candidates = []
        for sym in symbols:
            if sym in selected:
                continue
            if sum(sectors[x] == sectors[sym] for x in selected) >= MAX_PER_SECTOR:
                continue
            score, metrics = strategy_score(prices, sectors, selected, sym, strategy, cost_bps)
            candidates.append((score, sym, metrics))
        if not candidates:
            raise ValueError(f"{strategy}: no eligible candidate at step {step}")
        candidates.sort(key=lambda x: (-x[0], x[1]))
        score, winner, metrics = candidates[0]
        selected.append(winner)
        logs.append({
            "strategy": strategy, "step": step, "symbol": winner,
            "sector": sectors[winner], "selection_score": score,
            "training_sharpe_at_selection": metrics["sharpe_ratio"],
        })
        print(f"  {strategy} step {step:02d}/{TARGET_STOCKS}: {winner} score={score:.4f}")
    return selected, logs


def evaluate(prices, benchmark, sectors, selected, label):
    port = calculate_portfolio(
        prices=prices, sectors=sectors, symbols=selected,
        risk_free_rate=RISK_FREE_RATE, max_stocks=TARGET_STOCKS,
        max_per_sector=MAX_PER_SECTOR, price_basis="SPLIT_BONUS_ADJUSTED",
        return_type="PRICE_RETURN",
    )
    comparison = compare_with_benchmark(port["daily_returns"], benchmark)
    return {
        "period": label,
        "portfolio": stats(port["daily_returns"]),
        "benchmark_return_pct": comparison["benchmark_return_pct"],
        "excess_return_pct": comparison["excess_return_pct"],
        "common_return_observations": comparison["common_return_observations"],
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("\nGREEDY STOCKS — FIVE STRATEGY EXPERIMENT")
    print("Original GREEDY V2 source remains untouched.")
    dataset = prepare_greedy_v2_dataset("2025-04-01", "2026-11-05")
    prices = dataset.adjusted_prices.copy()
    benchmark = dataset.benchmark_prices.copy()
    common = prices.index.intersection(benchmark.index).sort_values()
    prices, benchmark = prices.loc[common], benchmark.loc[common]
    splits = chronological_split(prices, train_fraction=0.60, validation_fraction=0.20, allow_sparse_evaluation=True)
    b_train = benchmark.loc[splits.train.index]
    b_val = benchmark.loc[splits.validation.index]
    b_test = benchmark.loc[splits.test.index]
    sectors = dataset.sectors
    results, all_logs = {}, []
    for strategy in STRATEGIES:
        print(f"\n{'='*70}\nRUNNING {strategy}")
        start = time.perf_counter()
        if strategy == "GREEDY_V2_BASELINE":
            selected_result = greedy_select_stocks(
                train_prices=splits.train, sectors=sectors,
                target_stocks=TARGET_STOCKS, max_per_sector=MAX_PER_SECTOR,
                risk_free_rate=RISK_FREE_RATE,
            )
            selected = list(selected_result["selected_symbols"])
            log = selected_result["selection_log"].copy()
            if not log.empty:
                log.insert(0, "strategy", strategy)
        else:
            selected, log = experimental_select(splits.train, sectors, strategy)
        elapsed = time.perf_counter() - start
        all_logs.extend(log.to_dict(orient="records") if isinstance(log, pd.DataFrame) else log)
        results[strategy] = {
            "selected_symbols": selected,
            "sector_allocation": {s: sum(sectors[x] == s for x in selected) for s in sorted({sectors[x] for x in selected})},
            "runtime_seconds": round(elapsed, 3),
            "training": evaluate(splits.train, b_train, sectors, selected, "TRAINING"),
            "validation": evaluate(splits.validation, b_val, sectors, selected, "VALIDATION"),
            "final_test": evaluate(splits.test, b_test, sectors, selected, "FINAL_TEST"),
        }
        print(f"Completed {strategy} in {elapsed:.1f}s; final-test excess={results[strategy]['final_test']['excess_return_pct']:.3f} pp")
    report = {
        "experiment": "GREEDY_V2_FIVE_STRATEGY_COMPARISON",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "training_window": [str(splits.train.index.min().date()), str(splits.train.index.max().date())],
        "validation_window": [str(splits.validation.index.min().date()), str(splits.validation.index.max().date())],
        "final_test_window": [str(splits.test.index.min().date()), str(splits.test.index.max().date())],
        "configuration": {
            "target_stocks": TARGET_STOCKS, "max_per_sector": MAX_PER_SECTOR,
            "risk_free_rate": RISK_FREE_RATE, "cost_assumption_bps": COST_BPS_PER_TURNOVER,
            "selection_uses_training_data_only": True,
            "original_greedy_v2_modified": False,
            "dividend_adjusted": False, "corporate_action_coverage": "PARTIAL",
            "transaction_costs_are_estimated_not_broker_quotes": True,
        },
        "strategies": results,
    }
    json_path = OUT / "five_strategy_comparison.json"
    csv_path = OUT / "five_strategy_comparison.csv"
    log_path = OUT / "five_strategy_selection_logs.csv"
    json_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    rows = []
    for name, item in results.items():
        row = {"strategy": name, "runtime_seconds": item["runtime_seconds"], "selected_symbols": ",".join(item["selected_symbols"])}
        for period in ("training", "validation", "final_test"):
            row[f"{period}_return_pct"] = item[period]["portfolio"]["total_return_pct"]
            row[f"{period}_sharpe"] = item[period]["portfolio"]["sharpe_ratio"]
            row[f"{period}_max_drawdown_pct"] = item[period]["portfolio"]["maximum_drawdown_pct"]
            row[f"{period}_benchmark_return_pct"] = item[period]["benchmark_return_pct"]
            row[f"{period}_excess_return_pct"] = item[period]["excess_return_pct"]
        rows.append(row)
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    pd.DataFrame(all_logs).to_csv(log_path, index=False)
    print("\nALL FIVE STRATEGIES COMPLETE")
    print("JSON:", json_path)
    print("CSV:", csv_path)
    print("Selection logs:", log_path)
    print("Database writes: NONE")


if __name__ == "__main__":
    main()
