from pathlib import Path
from datetime import date

import pandas as pd

from analytics.database_adapter import get_all_companies_with_prices
from analytics.adjusted_price_adapter import get_adjusted_company_prices
from analytics.index_adapter import get_index_closes


MINIMUM_OBSERVATIONS = 252
START_DATE = "2016-11-08"
END_DATE = date.today().isoformat()


class GreedyV2Dataset:
    def __init__(
        self,
        constituents,
        sectors,
        raw_prices,
        adjusted_prices,
        benchmark_prices,
        metadata,
    ):
        self.constituents = constituents
        self.sectors = sectors
        self.raw_prices = raw_prices
        self.adjusted_prices = adjusted_prices
        self.benchmark_prices = benchmark_prices
        self.metadata = metadata


def _normalise_price_series(series, name):
    result = pd.to_numeric(series, errors="coerce").copy()

    if not isinstance(result.index, pd.DatetimeIndex):
        result.index = pd.to_datetime(result.index, errors="raise")

    if result.index.tz is not None:
        raise ValueError(f"{name} contains timezone-aware dates.")

    result.index = result.index.normalize()
    result = result.sort_index()

    if result.index.has_duplicates:
        raise ValueError(f"{name} contains duplicate dates.")

    if result.isna().any():
        raise ValueError(f"{name} contains missing or invalid prices.")

    if (result <= 0).any():
        raise ValueError(f"{name} contains non-positive prices.")

    result.name = name
    return result


def _load_benchmark(start_date, end_date):
    benchmark = get_index_closes(start_date, end_date)

    if not isinstance(benchmark, pd.Series):
        raise TypeError("get_index_closes must return a pandas Series.")

    return _normalise_price_series(benchmark, "NIFTY_50")


def prepare_greedy_v2_dataset(
    start_date=START_DATE,
    end_date=END_DATE,
):
    print("\nGREEDY STOCKS — V2 DATA PREPARATION")
    print("=" * 65)

    constituents = get_all_companies_with_prices(
        min_observations=MINIMUM_OBSERVATIONS
    ).copy()

    required = {"company_id", "symbol", "sector"}
    missing = required - set(constituents.columns)

    if missing:
        raise ValueError(f"Missing constituent columns: {sorted(missing)}")

    if constituents["symbol"].duplicated().any():
        raise ValueError("Duplicate constituent symbols detected.")

    constituents = constituents.sort_values("symbol").reset_index(drop=True)

    sectors = dict(zip(constituents["symbol"], constituents["sector"]))

    raw_series = {}
    adjusted_series = {}
    coverage = []
    skipped_symbols = []

    for _, company in constituents.iterrows():
        symbol = str(company["symbol"])
        company_id = int(company["company_id"])

        result = get_adjusted_company_prices(
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
        )

        if result.empty:
            skipped_symbols.append(symbol)
            print(f"SKIP {symbol}: no prices in requested window")
            continue

        dates = pd.DatetimeIndex(pd.to_datetime(result["trade_date"]))

        raw = pd.Series(
            result["close"].to_numpy(),
            index=dates,
            name=symbol,
        )

        adjusted = pd.Series(
            result["adjusted_close"].to_numpy(),
            index=dates,
            name=symbol,
        )

        raw_series[symbol] = _normalise_price_series(
            raw, f"{symbol}_RAW"
        )

        adjusted_series[symbol] = _normalise_price_series(
            adjusted, symbol
        )

        coverage.append({
            "symbol": symbol,
            "observations": len(result),
            "first_date": dates.min(),
            "last_date": dates.max(),
        })

    if not adjusted_series:
        raise ValueError("No eligible companies have prices in the requested window.")

    # Keep only companies with observations in this requested window.
    constituents = constituents[
        constituents["symbol"].isin(adjusted_series)
    ].copy().reset_index(drop=True)
    sectors = dict(zip(constituents["symbol"], constituents["sector"]))

    # Preserve each stock's complete available history.
    raw_prices = pd.concat(raw_series.values(), axis=1).sort_index()
    adjusted_prices = pd.concat(
        adjusted_series.values(), axis=1
    ).sort_index()

    # Benchmark remains independent. No all-50-stock intersection.
    benchmark_prices = _load_benchmark(start_date, end_date)

    # Retain the full date range and missing values.
    # Downstream training/evaluation selects valid observations.
    metadata = {
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "actual_start_date": str(adjusted_prices.index.min().date()),
        "actual_end_date": str(adjusted_prices.index.max().date()),
        "constituent_count": len(adjusted_series),
        "skipped_no_window_history": skipped_symbols,
        "universe_basis": "ALL_COMPANIES_WITH_PRICE_HISTORY",
        "minimum_observations": MINIMUM_OBSERVATIONS,
        "inactive_companies_included": True,
        "price_observation_count": len(adjusted_prices),
        "benchmark_observation_count": len(benchmark_prices),
        "stock_symbols": list(adjusted_prices.columns),
        "price_basis": "SPLIT_BONUS_ADJUSTED",
        "raw_price_basis": "RAW_CLOSE_UNADJUSTED",
        "dividend_adjusted": False,
        "corporate_action_coverage": "PARTIAL",
        "membership_basis": "NOT_RESTRICTED_TO_INDEX_MEMBERSHIP",
        "session_reference": "Available stock-price observations",
        "forward_filled": False,
        "database_writes": False,
        "common_all_stock_dates": False,
        "company_coverage": coverage,
    }

    print("\nDATA QUALITY REPORT")
    print("-" * 65)
    print("Requested:", start_date, "to", end_date)
    print("Actual stock history:", metadata["actual_start_date"], "to", metadata["actual_end_date"])
    print("Eligible companies:", len(adjusted_prices.columns))
    print("Inactive companies included:", int((constituents["is_active"] == 0).sum()))
    print("Minimum observations:", MINIMUM_OBSERVATIONS)
    print("Skipped (no window history):", skipped_symbols)
    print("Adjusted matrix:", adjusted_prices.shape)
    print("Raw matrix:", raw_prices.shape)
    print("Benchmark observations:", len(benchmark_prices))
    print("Forward filling: False")
    print("Database writes: False")
    print("\nDATA PREPARATION: PASS")

    return GreedyV2Dataset(
        constituents=constituents,
        sectors=sectors,
        raw_prices=raw_prices,
        adjusted_prices=adjusted_prices,
        benchmark_prices=benchmark_prices,
        metadata=metadata,
    )


if __name__ == "__main__":
    dataset = prepare_greedy_v2_dataset()

    print("\nFINAL MATRIX SHAPES")
    print("Raw:", dataset.raw_prices.shape)
    print("Adjusted:", dataset.adjusted_prices.shape)
    print("Benchmark:", dataset.benchmark_prices.shape)
