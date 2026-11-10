from pathlib import Path
import json, math
import numpy as np
import pandas as pd

ROOT = Path.cwd()
BASE = ROOT / "database/processed/analytics/greedy_10y_point_in_time"
EXP = BASE / "experiment4_final_unique_date_costs"
PRICE = ROOT / "database/processed/point_in_time/corporate_action_adjusted/nifty50_daily_adjusted_price_returns.csv"
ASSIGN = BASE / "experiment3_nested_walk_forward/outer_selections.csv"
DAILY = EXP / "unique_date_fold_assignment.csv"

OUT = EXP / "indian_delivery_cost_results"
OUT.mkdir(parents=True, exist_ok=True)

# Zerodha resident-individual NSE equity delivery reference tariff
STT = 0.001
STAMP_BUY = 0.00015
EXCHANGE = 0.0000307
SEBI = 0.000001
GST = 0.18
BROKERAGE = 0.0
DP_PER_SCRIP = 15.34  # ₹13 + GST; already GST-inclusive
CAPITALS = [100000, 500000, 1000000, 2500000]
SLIPPAGE_BPS_PER_SIDE = [0, 2.5, 5, 10, 15]

def fail(msg):
    raise SystemExit("STOP: " + msg)

for p in [PRICE, DAILY]:
    if not p.exists():
        fail(f"Missing input: {p}")

print("Loading adjusted stock returns...")
prices = pd.read_csv(PRICE, low_memory=False)
required = {"trade_date", "symbol", "adjusted_price_return"}
if not required.issubset(prices.columns):
    fail(f"Price columns missing: {required - set(prices.columns)}")

prices["trade_date"] = pd.to_datetime(prices["trade_date"]).dt.strftime("%Y-%m-%d")
prices["symbol"] = prices["symbol"].astype(str).str.strip()
prices["adjusted_price_return"] = pd.to_numeric(prices["adjusted_price_return"], errors="coerce")
prices = prices.dropna(subset=["adjusted_price_return"])
if prices.duplicated(["trade_date", "symbol"]).any():
    fail("Duplicate date/symbol rows in adjusted returns.")

ret = prices.pivot(index="trade_date", columns="symbol", values="adjusted_price_return")
print(f"Return matrix: {ret.shape[0]} dates x {ret.shape[1]} symbols")

print("Loading unique-date walk-forward portfolio assignments...")
daily = pd.read_csv(DAILY)
need = {"date", "strategy_return", "benchmark_return", "selected_stocks"}
if not need.issubset(daily.columns):
    fail(f"Assignment columns missing: {need - set(daily.columns)}")

daily["date"] = pd.to_datetime(daily["date"]).dt.strftime("%Y-%m-%d")
daily = daily.sort_values("date").reset_index(drop=True)
if daily["date"].duplicated().any():
    fail("Assignment file contains duplicate dates.")

daily["selected"] = daily["selected_stocks"].fillna("").apply(
    lambda x: [s.strip() for s in str(x).split(",") if s.strip()]
)
if daily["selected"].map(len).min() < 1:
    fail("At least one date has no selected stocks.")

missing_dates, missing_symbols = [], set()
for row in daily.itertuples():
    if row.date not in ret.index:
        missing_dates.append(row.date)
        continue
    missing_symbols.update(set(row.selected) - set(ret.columns))

if missing_dates:
    fail(f"{len(missing_dates)} portfolio dates absent from return panel; first: {missing_dates[:3]}")
if missing_symbols:
    fail(f"Selected symbols absent from adjusted return file: {sorted(missing_symbols)}")

# Validate the supplied strategy returns against the selected-stock equal-weight returns.
checks = []
for row in daily.itertuples():
    asset_r = ret.loc[row.date, row.selected].astype(float)
    if asset_r.isna().any():
        fail(f"Missing selected-stock return on {row.date}")
    calc = float(asset_r.mean())
    checks.append(abs(calc - float(row.strategy_return)))

max_return_diff = max(checks)
if max_return_diff > 0.00005:
    fail(f"Selected-stock returns do not reconcile to saved strategy returns. Max diff={max_return_diff:.8f}")

print(f"Return reconciliation passed. Max difference: {max_return_diff:.10f}")
print("Simulating daily equal-weight rebalances and delivery charges...")

results, daily_rows = [], []

for capital in CAPITALS:
    for slip_bps in SLIPPAGE_BPS_PER_SIDE:
        nav = float(capital)
        prev_weights = {}
        previous_day_returns = {}
        gross_nav = float(capital)
        benchmark_nav = float(capital)
        total_cost = total_dp = total_statutory = total_slippage = 0.0
        total_buy = total_sell = 0.0
        total_dp_events = 0
        peak = nav
        max_dd = 0.0

        for row in daily.itertuples():
            date = row.date
            selected = row.selected
            target = {s: 1.0 / len(selected) for s in selected}

            # Previous close holdings after that day's market movement.
            if prev_weights:
                drifted = {
                    s: w * (1.0 + previous_day_returns.get(s, 0.0))
                    for s, w in prev_weights.items()
                }
                denom = sum(drifted.values())
                if denom <= 0:
                    fail(f"Invalid portfolio value before rebalance on {date}")
                pretrade = {s: w / denom for s, w in drifted.items()}
            else:
                pretrade = {}

            all_symbols = set(pretrade) | set(target)
            changes = {s: target.get(s, 0.0) - pretrade.get(s, 0.0) for s in all_symbols}
            buys = {s: x for s, x in changes.items() if x > 1e-12}
            sells = {s: -x for s, x in changes.items() if x < -1e-12}

            buy_notional = nav * sum(buys.values())
            sell_notional = nav * sum(sells.values())
            dp_count = len(sells)

            turnover_buy = sum(buys.values())
            turnover_sell = sum(sells.values())

            # Charges on executed buy/sell notional.
            stt_cost = (buy_notional + sell_notional) * STT
            stamp_cost = buy_notional * STAMP_BUY
            exchange_cost = (buy_notional + sell_notional) * EXCHANGE
            sebi_cost = (buy_notional + sell_notional) * SEBI
            brokerage_cost = (buy_notional + sell_notional) * BROKERAGE
            gst_cost = GST * (exchange_cost + sebi_cost + brokerage_cost)
            dp_cost = dp_count * DP_PER_SCRIP
            slippage_cost = (buy_notional + sell_notional) * (slip_bps / 10000.0)

            statutory = stt_cost + stamp_cost + exchange_cost + sebi_cost + gst_cost + brokerage_cost
            costs = statutory + dp_cost + slippage_cost

            # Deduct execution costs, then apply that day's selected portfolio return.
            nav_before = nav
            nav_after_cost = max(0.0, nav - costs)
            asset_returns = ret.loc[date, selected].astype(float).to_dict()
            gross_return = float(np.mean(list(asset_returns.values())))
            nav = nav_after_cost * (1.0 + gross_return)

            # Benchmark remains price-return index, as in the original experiment.
            benchmark_nav *= (1.0 + float(row.benchmark_return))
            gross_nav *= (1.0 + gross_return)

            total_cost += costs
            total_dp += dp_cost
            total_statutory += statutory
            total_slippage += slippage_cost
            total_buy += buy_notional
            total_sell += sell_notional
            total_dp_events += dp_count

            peak = max(peak, nav)
            drawdown = nav / peak - 1.0
            max_dd = min(max_dd, drawdown)

            daily_rows.append({
                "capital_inr": capital,
                "slippage_bps_per_side": slip_bps,
                "date": date,
                "selected_stocks": ",".join(selected),
                "nav_before_cost": nav_before,
                "buy_notional": buy_notional,
                "sell_notional": sell_notional,
                "sell_scrip_count_dp": dp_count,
                "stt": stt_cost,
                "stamp_duty": stamp_cost,
                "exchange_charge": exchange_cost,
                "sebi_fee": sebi_cost,
                "gst": gst_cost,
                "dp_charge": dp_cost,
                "slippage": slippage_cost,
                "total_cost": costs,
                "gross_strategy_return": gross_return,
                "net_nav": nav,
                "benchmark_nav": benchmark_nav,
                "drawdown": drawdown
            })

            # Today's target portfolio drifts with today's returns until next rebalance.
            prev_weights = target
            previous_day_returns = asset_returns

        n = len(daily)
        strategy_return = (nav / capital - 1.0) * 100
        gross_return_pct = (gross_nav / capital - 1.0) * 100
        benchmark_return = (benchmark_nav / capital - 1.0) * 100
        excess = strategy_return - benchmark_return

        net_returns = []
        ddf = pd.DataFrame([x for x in daily_rows
                            if x["capital_inr"] == capital
                            and x["slippage_bps_per_side"] == slip_bps])
        net_returns = ddf["net_nav"].pct_change().dropna()
        sharpe = (
            float(np.sqrt(252) * net_returns.mean() / net_returns.std(ddof=1))
            if len(net_returns) > 1 and net_returns.std(ddof=1) > 0 else None
        )

        results.append({
            "capital_inr": capital,
            "slippage_bps_per_side": slip_bps,
            "observations": n,
            "gross_strategy_return_pct": gross_return_pct,
            "net_strategy_return_pct": strategy_return,
            "benchmark_price_return_pct": benchmark_return,
            "net_excess_vs_nifty_pp": excess,
            "net_final_value_inr": nav,
            "benchmark_final_value_inr": benchmark_nav,
            "total_cost_inr": total_cost,
            "dp_charges_inr": total_dp,
            "statutory_charges_inr": total_statutory,
            "slippage_cost_inr": total_slippage,
            "buy_turnover_inr": total_buy,
            "sell_turnover_inr": total_sell,
            "dp_sell_scrip_events": total_dp_events,
            "average_daily_one_way_turnover_pct": (
                100 * (total_buy + total_sell) / (2 * capital * n)
            ),
            "net_sharpe_approx": sharpe,
            "max_drawdown_pct": max_dd * 100
        })

summary = pd.DataFrame(results).sort_values(["capital_inr", "slippage_bps_per_side"])
summary_path = OUT / "delivery_cost_scenario_summary.csv"
summary.to_csv(summary_path, index=False)

daily_path = OUT / "delivery_cost_daily_ledger.csv"
pd.DataFrame(daily_rows).to_csv(daily_path, index=False)

assumptions = {
    "model": "NSE equity delivery, Zerodha resident-individual reference",
    "STT_buy_pct": 0.10,
    "STT_sell_pct": 0.10,
    "stamp_duty_buy_pct": 0.015,
    "NSE_transaction_pct_each_side": 0.00307,
    "SEBI_fee_pct_each_side": 0.0001,
    "GST_pct_on_exchange_sebi_brokerage": 18,
    "brokerage_per_order_inr": 0,
    "DP_per_scrip_sold_inr_including_GST": 15.34,
    "slippage_bps_per_side": SLIPPAGE_BPS_PER_SIDE,
    "capital_scenarios_inr": CAPITALS,
    "rebalance": "Daily target equal-weight portfolio; costs charged on buy/sell weight changes",
    "share_quantity": "Fractional-weight/notional estimate; not whole-share execution",
    "dividends": "Excluded",
    "benchmark": "NIFTY price return, not TRI",
    "corporate_actions": "Only currently incorporated known events; not proven exhaustive",
    "membership": "Historical membership and Tata demerger limitations remain",
    "validation_max_strategy_return_difference": max_return_diff,
    "important": "DP fee event count is based on any fractional reduction in a holding. Actual integer-share fills and DP events may differ."
}
(OUT / "delivery_cost_assumptions.json").write_text(json.dumps(assumptions, indent=2), encoding="utf-8")

print("\n=== DELIVERY COST RESULTS ===")
print(summary[[
    "capital_inr", "slippage_bps_per_side",
    "net_strategy_return_pct", "benchmark_price_return_pct",
    "net_excess_vs_nifty_pp", "total_cost_inr",
    "dp_charges_inr", "net_final_value_inr"
]].to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

print("\nSaved:")
print(summary_path)
print(daily_path)
print(OUT / "delivery_cost_assumptions.json")
print("\nWARNING: fractional-notional estimate; not final whole-share execution proof.")
