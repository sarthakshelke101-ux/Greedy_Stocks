from pathlib import Path
from datetime import date
import pandas as pd
from sqlalchemy import inspect, text

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import engine

START = "2016-11-08"
END = "2026-11-06"
OUT = Path("database/reports/10y_coverage")
OUT.mkdir(parents=True, exist_ok=True)

def pick(columns, choices):
    lookup = {c.lower(): c for c in columns}
    for choice in choices:
        if choice in lookup:
            return lookup[choice]
    return None

inspector = inspect(engine)
tables = inspector.get_table_names()

print("\n10-YEAR HISTORICAL PRICE COVERAGE AUDIT")
print("=" * 65)
print("Period:", START, "to", END)
print("Tables discovered:", ", ".join(tables))

# Locate price table.
price_table_name = next(
    (t for t in tables if t.lower() == "stock_prices"), None
)
if not price_table_name:
    raise RuntimeError(
        f"stock_prices table not found. Available tables: {tables}"
    )

price_cols = [c["name"] for c in inspector.get_columns(price_table_name)]
price_date = pick(price_cols, ["date", "trade_date", "price_date"])
company_id = pick(price_cols, ["company_id", "stock_id"])
price_value = pick(
    price_cols,
    ["adjusted_close", "adj_close", "close_adj", "close_price", "close", "closing_price"]
)

if not price_date or not price_value:
    raise RuntimeError(
        f"Could not identify date/price columns. Found: {price_cols}"
    )

with engine.connect() as conn:
    prices = pd.read_sql(
        text(f"SELECT * FROM `{price_table_name}`"),
        conn
    )

prices[price_date] = pd.to_datetime(prices[price_date], errors="coerce")
prices = prices[
    prices[price_date].between(START, END)
].copy()

# Resolve company IDs to ticker symbols.
symbol_col = pick(price_cols, ["symbol", "ticker", "stock_symbol"])
if symbol_col:
    prices["audit_symbol"] = prices[symbol_col].astype(str).str.upper()
elif company_id:
    company_table_name = next(
        (t for t in tables if t.lower() in ("companies", "stocks", "company")),
        None
    )
    if not company_table_name:
        raise RuntimeError("Company table not found for company_id mapping.")

    company_cols = [
        c["name"] for c in inspector.get_columns(company_table_name)
    ]
    company_pk = pick(company_cols, ["id", "company_id", "stock_id"])
    company_symbol = pick(
        company_cols, ["symbol", "ticker", "stock_symbol"]
    )
    if not company_pk or not company_symbol:
        raise RuntimeError(
            f"Cannot map company IDs. Columns: {company_cols}"
        )

    with engine.connect() as conn:
        companies = pd.read_sql(
            text(f"SELECT `{company_pk}`, `{company_symbol}` "
                 f"FROM `{company_table_name}`"),
            conn
        )

    prices = prices.merge(
        companies,
        left_on=company_id,
        right_on=company_pk,
        how="left"
    )
    prices["audit_symbol"] = prices[company_symbol].astype(str).str.upper()
else:
    raise RuntimeError("No ticker symbol or company_id column found.")

prices = prices.dropna(subset=["audit_symbol", price_date])
prices = prices[
    ~prices["audit_symbol"].isin(["", "NAN", "NONE"])
]
prices["audit_price"] = pd.to_numeric(
    prices[price_value], errors="coerce"
)
prices = prices.dropna(subset=["audit_price"])
prices = prices[prices["audit_price"] > 0]

# Find a benchmark date series to represent actual market sessions.
benchmark_dates = None
benchmark_source = None

for table_name in tables:
    name = table_name.lower()
    if not any(k in name for k in ("benchmark", "nifty", "index")):
        continue

    cols = [c["name"] for c in inspector.get_columns(table_name)]
    dcol = pick(cols, ["date", "trade_date", "price_date"])
    if not dcol:
        continue

    with engine.connect() as conn:
        candidate = pd.read_sql(
            text(f"SELECT DISTINCT `{dcol}` FROM `{table_name}`"),
            conn
        )

    candidate[dcol] = pd.to_datetime(candidate[dcol], errors="coerce")
    candidate = candidate[dcol].dropna()
    candidate = candidate[candidate.between(START, END)]

    if len(candidate) > 0:
        benchmark_dates = pd.DatetimeIndex(candidate.unique()).sort_values()
        benchmark_source = table_name
        break

if benchmark_dates is None:
    benchmark_dates = pd.DatetimeIndex(
        prices[price_date].dropna().unique()
    ).sort_values()
    benchmark_source = "UNION_OF_STOCK_PRICE_DATES_PROXY"

print(f"\nExpected-session source: {benchmark_source}")
print(f"Expected dates in period: {len(benchmark_dates):,}")

# Duplicate symbol/date detection.
duplicates = (
    prices.groupby(["audit_symbol", price_date])
    .size()
    .reset_index(name="row_count")
)
duplicates = duplicates[duplicates["row_count"] > 1]
duplicates.to_csv(OUT / "duplicate_symbol_dates.csv", index=False)

# Per-symbol coverage and gap report.
summary_rows = []
gap_rows = []

for symbol, group in prices.groupby("audit_symbol"):
    observed = pd.DatetimeIndex(
        group[price_date].drop_duplicates()
    ).sort_values()

    first = observed.min()
    last = observed.max()

    expected_for_symbol = benchmark_dates[
        (benchmark_dates >= first) & (benchmark_dates <= last)
    ]

    missing = expected_for_symbol.difference(observed)
    coverage = (
        len(observed) / len(expected_for_symbol) * 100
        if len(expected_for_symbol) else 0
    )

    # Consecutive missing expected sessions are grouped into gap runs.
    if len(missing):
        run_start = missing[0]
        previous = missing[0]
        run_length = 1

        for current in missing[1:]:
            idx_prev = benchmark_dates.get_indexer([previous])[0]
            idx_cur = benchmark_dates.get_indexer([current])[0]

            if idx_cur == idx_prev + 1:
                run_length += 1
            else:
                gap_rows.append({
                    "symbol": symbol,
                    "gap_start": run_start.date(),
                    "gap_end": previous.date(),
                    "missing_sessions": run_length
                })
                run_start = current
                run_length = 1
            previous = current

        gap_rows.append({
            "symbol": symbol,
            "gap_start": run_start.date(),
            "gap_end": previous.date(),
            "missing_sessions": run_length
        })

    summary_rows.append({
        "symbol": symbol,
        "first_date": first.date(),
        "last_date": last.date(),
        "observations": len(observed),
        "expected_sessions_between_first_last": len(expected_for_symbol),
        "missing_sessions_between_first_last": len(missing),
        "coverage_pct_between_first_last": round(coverage, 2),
        "full_period_expected_sessions": len(benchmark_dates),
        "full_period_coverage_pct": round(
            len(observed) / len(benchmark_dates) * 100, 2
        ) if len(benchmark_dates) else 0
    })

summary = pd.DataFrame(summary_rows).sort_values(
    ["coverage_pct_between_first_last", "observations"],
    ascending=[True, True]
)
gaps = pd.DataFrame(gap_rows)

summary.to_csv(OUT / "10y_stock_coverage.csv", index=False)
gaps.to_csv(OUT / "10y_missing_session_gaps.csv", index=False)

print("\nCOVERAGE SUMMARY")
print("-" * 65)
print("Stocks:", len(summary))
print("Price observations:", f"{len(prices):,}")
print("Duplicate symbol/date pairs:", len(duplicates))
print("Stocks with gaps:", int((summary["missing_sessions_between_first_last"] > 0).sum()))
print("Total missing expected sessions:", int(summary["missing_sessions_between_first_last"].sum()))

print("\nLOWEST COVERAGE STOCKS")
print(summary.head(20).to_string(index=False))

print("\nLARGEST MISSING-DATA GAPS")
if len(gaps):
    print(
        gaps.sort_values("missing_sessions", ascending=False)
        .head(20).to_string(index=False)
    )
else:
    print("No missing-session gaps detected.")

print("\nIMPORTANT")
if benchmark_source == "UNION_OF_STOCK_PRICE_DATES_PROXY":
    print(
        "No benchmark date table was identified. Coverage uses the union "
        "of stock dates as a proxy, NOT an independently verified exchange calendar."
    )
else:
    print(
        "Expected sessions use benchmark dates. This is a market-session "
        "proxy, not proof of complete historical index membership."
    )

print("\nReports saved:")
print(OUT / "10y_stock_coverage.csv")
print(OUT / "10y_missing_session_gaps.csv")
print(OUT / "duplicate_symbol_dates.csv")
print("\nREAD-ONLY AUDIT: no database writes performed.")
