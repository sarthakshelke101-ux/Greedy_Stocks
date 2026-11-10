import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analytics"))

import _bootstrap
from database_adapter import get_latest_constituents, get_company_prices

START = "2025-04-01"
END = "2026-11-05"

constituents = get_latest_constituents()
frames = {}

for _, row in constituents.iterrows():
    symbol = row["symbol"]
    company_id = int(row["company_id"])

    prices = get_company_prices(company_id, START, END)
    frames[symbol] = prices.rename(symbol)

matrix = pd.concat(frames.values(), axis=1).sort_index()

audit = pd.DataFrame({
    "symbol": matrix.columns,
    "price_observations": [matrix[c].notna().sum() for c in matrix.columns],
    "missing_prices": [matrix[c].isna().sum() for c in matrix.columns],
    "first_date": [
        matrix[c].first_valid_index() for c in matrix.columns
    ],
    "last_date": [
        matrix[c].last_valid_index() for c in matrix.columns
    ],
})

print("\nNIFTY 50 HISTORICAL PRICE COVERAGE")
print("=" * 65)
print("Companies:", len(constituents))
print("Date rows:", len(matrix))
print("Complete price dates:", int(matrix.notna().all(axis=1).sum()))
print("Companies with missing prices:", int((audit["missing_prices"] > 0).sum()))
print("\nLOWEST COVERAGE COMPANIES")
print(audit.sort_values("price_observations").head(15).to_string(index=False))

print("\nCOVERAGE SUMMARY")
print(audit["price_observations"].describe().to_string())

print("\nNo database writes performed.")
