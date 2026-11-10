"""Quality checks for historical NIFTY 50 rankings.

This is an integration/quality-check script, not a unittest module.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import math
import pandas as pd

from analytics.historical_rankings import PERIODS, run_historical_rankings


EXPECTED_COMPANIES = 50
PERIOD_ORDER = ["1M", "3M", "6M", "1Y"]


def check(condition, message):
    if condition:
        print(f"[PASS] {message}")
        return True
    print(f"[FAIL] {message}")
    return False


def validate_period(period):
    print("\n" + "=" * 75)
    print(f"VALIDATING {period} HISTORICAL RANKINGS")
    print("=" * 75)

    failures = 0
    warnings = 0
    result = run_historical_rankings(period)

    failures += not check(
        len(result) == EXPECTED_COMPANIES,
        f"Exactly {EXPECTED_COMPANIES} companies returned ({len(result)})",
    )
    failures += not check(
        result["symbol"].nunique() == EXPECTED_COMPANIES,
        "All company symbols are unique",
    )

    valid_statuses = {"CALCULATED", "INSUFFICIENT_DATA"}
    failures += not check(
        result["data_status"].notna().all()
        and set(result["data_status"].unique()).issubset(valid_statuses),
        "Every company has a recognized calculation status",
    )

    calculated = result[result["data_status"] == "CALCULATED"]
    insufficient = result[result["data_status"] == "INSUFFICIENT_DATA"]

    failures += not check(
        len(calculated) + len(insufficient) == EXPECTED_COMPANIES,
        "Every company has an explicit calculation status",
    )
    failures += not check(
        calculated["observations"].ge(2).all(),
        "Calculated companies have at least two valid observations",
    )
    failures += not check(
        calculated["period_return"].notna().all(),
        "Calculated companies have period returns",
    )
    failures += not check(
        calculated["annualized_volatility"].notna().all()
        and calculated["annualized_volatility"].ge(0).all(),
        "Calculated companies have non-negative annualised volatility",
    )
    failures += not check(
        calculated["maximum_drawdown"].notna().all()
        and calculated["maximum_drawdown"].le(0).all(),
        "Calculated companies have valid non-positive maximum drawdown",
    )

    failures += not check(
        insufficient["return_rank"].isna().all(),
        "Insufficient-data companies are not assigned return ranks",
    )
    failures += not check(
        insufficient["data_quality_reason"].notna().all(),
        "Insufficient-data companies have an explicit reason",
    )

    returns = calculated["period_return"].tolist()
    sorted_returns = sorted(returns, reverse=True)
    failures += not check(
        all(
            math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
            for a, b in zip(returns, sorted_returns)
        ),
        "Calculated return ranking is sorted highest to lowest",
    )

    expected_ranks = calculated["period_return"].rank(
        method="min",
        ascending=False,
    )
    failures += not check(
        calculated["return_rank"].reset_index(drop=True).equals(
            expected_ranks.reset_index(drop=True)
        ),
        "Return ranks correctly handle ties",
    )

    failures += not check(
        result["corporate_action_coverage"].eq("PARTIAL").all()
        and result.attrs.get("corporate_action_coverage") == "PARTIAL",
        "Partial corporate-action coverage is disclosed",
    )
    failures += not check(
        result.attrs.get("dividend_adjusted") is False,
        "Results are not misrepresented as dividend-adjusted",
    )
    failures += not check(
        result.attrs.get("price_basis") == "SPLIT_BONUS_ADJUSTED",
        "Split/bonus-adjusted price basis is disclosed",
    )
    failures += not check(
        result.attrs.get("membership_basis") == "LATEST_MONTHLY_SNAPSHOT",
        "Latest-snapshot universe methodology is disclosed",
    )

    expected_start = pd.Timestamp(result.attrs["requested_start_date"])
    common_end = pd.Timestamp(result.attrs["common_end_date"])

    if not calculated.empty:
        date_checks = (
            pd.to_datetime(calculated["first_price_date"]).ge(expected_start)
            & pd.to_datetime(calculated["last_price_date"]).eq(common_end)
        )
    else:
        date_checks = pd.Series(dtype=bool)

    failures += not check(
        not calculated.empty and date_checks.all(),
        "Every calculated company covers the requested window through the common end date",
    )

    expected_count = result.attrs.get("expected_session_count")
    failures += not check(
        calculated["observations"].eq(expected_count).all(),
        "Every calculated company contains every expected shared session",
    )
    failures += not check(
        result.attrs.get("session_reference") == "DISTINCT_STOCK_PRICE_DATES",
        "Session-reference limitation is disclosed",
    )

    if period == "1M":
        warnings += 1
        print(
            "[WARN] One-month CAGR is highly annualised; "
            "do not present it as an expected future return."
        )

    warnings += 1
    print(
        "[WARN] Latest monthly constituent snapshot is not exact daily "
        "historical membership."
    )
    warnings += 1
    print(
        "[WARN] Corporate-action coverage is partial and dividends are "
        "not included."
    )
    warnings += 1
    print(
        "[WARN] Session dates come from imported stock_prices, not an "
        "independently certified NSE calendar."
    )

    print(f"\n{period} RESULTS: {failures} FAIL, {warnings} WARN")
    return failures, warnings


def main():
    total_failures = 0
    total_warnings = 0

    for period in PERIOD_ORDER:
        failures, warnings = validate_period(period)
        total_failures += failures
        total_warnings += warnings

    print("\n" + "=" * 75)
    print("HISTORICAL RANKING VALIDATION SUMMARY")
    print("=" * 75)
    print("Periods tested:", len(PERIOD_ORDER))
    print("Total company-period slots:", EXPECTED_COMPANIES * len(PERIOD_ORDER))
    print("Failures:", total_failures)
    print("Warnings:", total_warnings)

    if total_failures == 0:
        print("\nPASS: STRUCTURAL RANKING CHECKS COMPLETED")
        print("Production approval is still pending broader data validation.")
    else:
        print("\nFAIL: FIX THE REPORTED ISSUES BEFORE PROCEEDING.")

    raise SystemExit(1 if total_failures else 0)


if __name__ == "__main__":
    main()
