from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
ANALYTICS = ROOT / "analytics"

# Match the import convention used by existing analytics scripts.
sys.path.insert(0, str(ANALYTICS))

from validation.trial_registry import append_trial
from portfolio_analytics import calculate_portfolio


RUNNER = ANALYTICS / "run_greedy_v2_experiment.py"


def main():
    print("\nGREEDY STOCKS — REGISTERED EXPERIMENT")
    print("=" * 60)

    state = runpy.run_path(str(RUNNER), run_name="__main__")

    splits = state["splits"]
    selection = state["selection"]
    symbols = list(
        selection.get("selected_symbols")
        or selection.get("selected_stocks")
    )
    sectors = state["sectors"]

    test_portfolio = calculate_portfolio(
        prices=splits.test,
        sectors={s: sectors[s] for s in symbols},
        symbols=symbols,
        risk_free_rate=state["RISK_FREE_RATE"],
        max_stocks=state["TARGET_STOCKS"],
        max_per_sector=state["MAX_PER_SECTOR"],
        price_basis=state["PRICE_BASIS"],
        return_type=state["RETURN_TYPE"],
    )

    daily_returns = test_portfolio["daily_returns"]

    record = append_trial(
        algorithm="GREEDY_V2",
        config={
            "target_stocks": state["TARGET_STOCKS"],
            "max_per_sector": state["MAX_PER_SECTOR"],
            "risk_free_rate": state["RISK_FREE_RATE"],
            "price_basis": state["PRICE_BASIS"],
            "return_type": state["RETURN_TYPE"],
            "selected_symbols": symbols,
        },
        daily_returns=daily_returns.tolist(),
        dates=[str(x.date()) for x in daily_returns.index],
        metadata={
            "period": "FINAL_TEST",
            "start_date": str(daily_returns.index[0].date()),
            "end_date": str(daily_returns.index[-1].date()),
            "membership_basis": "LATEST_MONTHLY_SNAPSHOT",
            "transaction_costs_included": False,
            "source_runner": "run_greedy_v2_experiment.py",
        },
    )

    print("\nTRIAL REGISTERED")
    print("Trial ID:", record["trial_id"])
    print("Algorithm:", record["algorithm"])
    print("Daily returns:", record["observations"])
    print("Registry: database/processed/analytics/trial_registry.jsonl")


if __name__ == "__main__":
    main()
