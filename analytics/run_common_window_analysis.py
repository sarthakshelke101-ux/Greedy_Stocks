import pandas as pd

from analytics.database_adapter import (
    get_latest_constituents,
    get_company_prices,
)
from analytics.financial_metrics import calculate_metrics

START = "2025-10-24"
END = "2026-11-05"

constituents = get_latest_constituents()
results = []
reference_dates = None

for company in constituents.to_dict("records"):
    prices = get_company_prices(
        int(company["company_id"]),
        start_date=START,
        end_date=END,
    )

    prices = prices.dropna()

    dates = set(prices.index.date)

    if reference_dates is None:
        reference_dates = dates
    elif dates != reference_dates:
        raise ValueError(
            f"Trading calendar mismatch: {company['symbol']}"
        )

    metrics = calculate_metrics(prices, risk_free_rate=0.0)

    results.append({
        "symbol": company["symbol"],
        "company_name": company["company_name"],
        "sector": company["sector"],
        **metrics,
    })

ranking = pd.DataFrame(results)

if len(ranking) != 50:
    raise ValueError("Expected exactly 50 companies.")

if ranking["return_observations"].nunique() != 1:
    raise ValueError("Return observation counts are inconsistent.")

ranking = ranking.sort_values(
    "period_return_pct",
    ascending=False,
    na_position="last",
).reset_index(drop=True)

ranking.insert(0, "rank", range(1, len(ranking) + 1))

print("\nGREEDY STOCKS — COMPARABLE NIFTY 50 SNAPSHOT RANKING")
print("=" * 105)
print(f"Period: {START} to {END}")
print("Companies:", len(ranking))
print("Common trading dates:", len(reference_dates))
print("Return observations:", ranking["return_observations"].iloc[0])
print("Price basis: RAW_CLOSE_UNADJUSTED")
print("Risk-free rate: 0%")
print("\nTOP 10")
print(
    ranking[
        ["rank", "symbol", "period_return_pct", "cagr_pct",
         "annualized_volatility_pct", "maximum_drawdown_pct",
         "sharpe_ratio"]
    ].head(10).to_string(index=False)
)

print("\nBOTTOM 5")
print(
    ranking[
        ["rank", "symbol", "period_return_pct"]
    ].tail(5).to_string(index=False)
)

print("\nDatabase writes: NONE")
