import sys
from pathlib import Path

import pandas as pd

import _bootstrap

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analytics"))

from database_adapter import get_latest_constituents, get_company_prices
from index_adapter import get_index_closes
from portfolio_analytics import calculate_portfolio, compare_with_benchmark


START_DATE = "2025-04-01"
END_DATE = "2026-11-05"
PORTFOLIO_SIZE = 10
MAX_PER_SECTOR = 3


def select_stocks(constituents):
    """Select highest-weight constituents within sector constraints."""

    ranked = constituents.sort_values(
        "weightage", ascending=False
    )

    selected = []
    sector_counts = {}

    for _, row in ranked.iterrows():
        sector = row["sector"]

        if sector_counts.get(sector, 0) >= MAX_PER_SECTOR:
            continue

        selected.append(row)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

        if len(selected) == PORTFOLIO_SIZE:
            break

    if len(selected) != PORTFOLIO_SIZE:
        raise ValueError(
            f"Could select only {len(selected)} stocks."
        )

    return pd.DataFrame(selected)


def main():
    print("\nGREEDY STOCKS — REAL DATA PORTFOLIO RUN")
    print("=" * 55)

    # 1. Load latest NIFTY 50 universe.
    constituents = get_latest_constituents()

    if len(constituents) != 50:
        raise ValueError(
            f"Expected 50 constituents, received {len(constituents)}."
        )

    selected = select_stocks(constituents)

    print(f"\nConstituent snapshot: {selected['report_month'].iloc[0]}")
    print("\nSELECTED STOCKS")
    print("-" * 55)

    for _, row in selected.iterrows():
        print(
            f"{row['symbol']:15} "
            f"{row['sector']:40} "
            f"Index weight: {row['weightage']}%"
        )

    # 2. Retrieve actual historical closing prices.
    price_series = {}

    for _, row in selected.iterrows():
        symbol = row["symbol"]
        company_id = int(row["company_id"])

        series = get_company_prices(
            company_id,
            START_DATE,
            END_DATE,
        )

        if series.empty:
            raise ValueError(f"No price history found for {symbol}.")

        price_series[symbol] = series.rename(symbol)

    prices = pd.concat(price_series.values(), axis=1).sort_index()

    sectors = dict(zip(selected["symbol"], selected["sector"]))

    print("\nPRICE DATA")
    print("-" * 55)
    print(f"Stocks selected: {len(price_series)}")
    print(f"Price date range: {prices.index.min()} to {prices.index.max()}")
    print(f"Price rows: {len(prices)}")
    print(f"Missing price cells: {int(prices.isna().sum().sum())}")

    # 3. Calculate equal-weight portfolio.
    result = calculate_portfolio(
        prices=prices,
        sectors=sectors,
        symbols=list(selected["symbol"]),
        risk_free_rate=0.0,
    )

    # 4. Align benchmark prices to exactly the stock-price dates.
    benchmark = get_index_closes(
        START_DATE,
        END_DATE,
    )

    benchmark = benchmark.reindex(prices.index)

    missing_benchmark = int(benchmark.isna().sum())

    print(f"Missing benchmark prices on stock dates: {missing_benchmark}")

    if missing_benchmark:
        raise ValueError(
            "Benchmark does not cover all stock-price dates. "
            "Cannot claim a fully aligned comparison."
        )

    comparison = compare_with_benchmark(
        result["daily_returns"],
        benchmark,
    )

    # 5. Display results.
    print("\nPORTFOLIO METRICS")
    print("-" * 55)

    for key, value in result["metrics"].items():
        print(f"{key}: {value}")

    print("\nBENCHMARK COMPARISON")
    print("-" * 55)

    for key, value in comparison.items():
        if key != "comparison_returns":
            print(f"{key}: {value}")

    print("\nSECTOR ALLOCATION")
    print("-" * 55)

    for sector, weight in result["sector_allocation"].items():
        print(f"{sector}: {weight * 100:.2f}%")

    print("\nDATA AND METHODOLOGY")
    print("-" * 55)

    for key, value in result["metadata"].items():
        print(f"{key}: {value}")

    print("\nIMPORTANT DISCLOSURES")
    print("-" * 55)
    print("Universe: latest monthly NIFTY 50 snapshot.")
    print("Selection: highest index weights, subject to sector cap.")
    print("Portfolio weights: equal weight.")
    print("Rebalancing: daily.")
    print("Price basis: unadjusted closing prices.")
    print("Corporate actions: partial split/bonus adjustment coverage.")
    print("Dividends: not included.")
    print("Benchmark: NIFTY 50 Price Return index.")
    print("Database writes: none.")
    print("Historical results are not forecasts.")

    print("\nREAL DATA PORTFOLIO RUN COMPLETED")
    print("=" * 55)


if __name__ == "__main__":
    main()
