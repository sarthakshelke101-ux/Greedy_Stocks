
"""GREEDY STOCKS — NIFTY 50 benchmark analytics.

Uses the official NSE Indices Historical Price Return (PR) dataset
stored in MySQL. All operations are read-only.

Important:
- This is a Price Return (PR) index, not TRI.
- No dividend adjustment is included.
- No trading calendar is assumed unless explicitly supplied.
- Results describe historical performance, not future returns.
"""

from __future__ import annotations

from analytics.index_adapter import (
    INDEX_SYMBOL,
    INDEX_DATA_SOURCE,
    get_index_closes,
)

from analytics.financial_metrics import calculate_metrics


def calculate_benchmark_metrics(
    start_date: str | None = None,
    end_date: str | None = None,
    risk_free_rate: float = 0.0,
) -> dict:
    """Calculate historical NIFTY 50 PR benchmark metrics."""

    if risk_free_rate <= -1:
        raise ValueError(
            "Annual risk-free rate must be greater than -100%."
        )

    prices = get_index_closes(
        start_date=start_date,
        end_date=end_date,
    )

    if prices.empty:
        raise ValueError(
            "No NIFTY 50 benchmark prices found for the requested period."
        )

    metrics = calculate_metrics(
        prices,
        risk_free_rate=risk_free_rate,
        price_basis="NSE_NIFTY_50_INDEX_CLOSE",
        return_type="PRICE_RETURN",
    )

    return {
        "benchmark": INDEX_SYMBOL,
        "benchmark_name": "NIFTY 50",
        "benchmark_type": "PRICE_RETURN_INDEX",
        "data_source": INDEX_DATA_SOURCE,
        "dividend_adjusted": False,
        "calendar_validation": "NOT_SUPPLIED",
        "database_writes": False,
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "metrics": metrics,
        "disclosures": [
            "Benchmark represents the NIFTY 50 Price Return (PR) Index.",
            "Returns exclude dividends.",
            "Historical performance is not a forecast.",
            "Risk metrics use 252 trading days per year.",
            "Risk-free rate is an annual assumption supplied by the caller.",
            "Trading-session calendar has not been independently validated.",
            "Short-history CAGR is suppressed when fewer than 60 returns exist.",
        ],
    }


if __name__ == "__main__":
    result = calculate_benchmark_metrics()

    print("=" * 60)
    print("GREEDY STOCKS — NIFTY 50 BENCHMARK ANALYTICS")
    print("=" * 60)

    print("Benchmark:", result["benchmark"])
    print("Type:", result["benchmark_type"])
    print("Data source:", result["data_source"])
    print("Dividend adjusted:", result["dividend_adjusted"])
    print("Database writes:", result["database_writes"])
    print("Calendar validation:", result["calendar_validation"])

    print("\nMETRICS")
    print("-" * 60)

    for key, value in result["metrics"].items():
        print(f"{key}: {value}")

    print("\nDISCLOSURES")
    print("-" * 60)

    for disclosure in result["disclosures"]:
        print("-", disclosure)
