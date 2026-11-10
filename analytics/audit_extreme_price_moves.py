import pandas as pd

from analytics.database_adapter import (
    get_latest_constituents,
    get_company_prices,
)

constituents = get_latest_constituents()
extreme_moves = []

for company in constituents.to_dict("records"):
    prices = get_company_prices(int(company["company_id"]))
    returns = prices.pct_change(fill_method=None).dropna()

    for date, change in returns.items():
        if abs(change) >= 0.15:
            extreme_moves.append({
                "symbol": company["symbol"],
                "date": date.date(),
                "return_pct": change * 100,
                "previous_close": prices.shift(1).loc[date],
                "close": prices.loc[date],
            })

audit = pd.DataFrame(extreme_moves)

print("EXTREME DAILY PRICE MOVEMENTS (15% OR MORE)")
print("=" * 100)

if audit.empty:
    print("No daily movements above the threshold.")
else:
    audit["abs_return"] = audit["return_pct"].abs()
    audit = audit.sort_values("abs_return", ascending=False)

    print(
        audit[
            ["symbol", "date", "previous_close", "close", "return_pct"]
        ].head(30).to_string(index=False)
    )

print("\nKOTAKBANK — ISIN TRANSITION INSPECTION")
print("=" * 100)

kotak = constituents.loc[
    constituents["symbol"] == "KOTAKBANK"
]

if not kotak.empty:
    prices = get_company_prices(
        int(kotak.iloc[0]["company_id"]),
        start_date="2026-01-07",
        end_date="2026-01-21",
    )
    print(prices.to_string())
else:
    print("KOTAKBANK not found in latest snapshot.")

print("\nDatabase writes: NONE")
