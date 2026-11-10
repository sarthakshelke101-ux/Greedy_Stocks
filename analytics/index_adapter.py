
"""GREEDY STOCKS — Read-only NIFTY 50 benchmark adapter."""

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from database import engine

INDEX_SYMBOL = "NIFTY 50"
INDEX_DATA_SOURCE = "NSE Indices Historical PR"


def get_index_prices(
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """Retrieve NIFTY 50 daily OHLC values from MySQL.

    Returns a read-only DataFrame indexed by trading date.
    Does not forward-fill missing sessions.
    """

    query = text("""
        SELECT
            trade_date,
            open_value,
            high_value,
            low_value,
            close_value,
            data_source
        FROM index_prices
        WHERE index_symbol = :index_symbol
          AND (:start_date IS NULL OR trade_date >= :start_date)
          AND (:end_date IS NULL OR trade_date <= :end_date)
        ORDER BY trade_date
    """)

    with engine.connect() as conn:
        rows = conn.execute(
            query,
            {
                "index_symbol": INDEX_SYMBOL,
                "start_date": start_date,
                "end_date": end_date,
            },
        ).mappings().all()

    if not rows:
        return pd.DataFrame(
            columns=[
                "open_value",
                "high_value",
                "low_value",
                "close_value",
                "data_source",
            ],
            index=pd.DatetimeIndex([], name="trade_date"),
        )

    frame = pd.DataFrame([dict(row) for row in rows])

    frame["trade_date"] = pd.to_datetime(frame["trade_date"])

    if frame["trade_date"].duplicated().any():
        raise ValueError("Duplicate NIFTY 50 trading dates found.")

    frame = frame.sort_values("trade_date")
    frame = frame.set_index("trade_date")

    price_columns = [
        "open_value",
        "high_value",
        "low_value",
        "close_value",
    ]

    frame[price_columns] = frame[price_columns].apply(
        pd.to_numeric,
        errors="coerce",
    )

    if frame[price_columns].isna().any().any():
        raise ValueError("Missing or invalid NIFTY 50 OHLC values.")

    if (frame[price_columns] <= 0).any().any():
        raise ValueError("Non-positive NIFTY 50 OHLC values.")

    if (
        (frame["high_value"] < frame[["open_value", "close_value"]].max(axis=1))
        | (frame["low_value"] > frame[["open_value", "close_value"]].min(axis=1))
        | (frame["high_value"] < frame["low_value"])
    ).any():
        raise ValueError("Invalid NIFTY 50 OHLC relationships.")

    return frame


def get_index_closes(
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.Series:
    """Return NIFTY 50 closing index values."""

    frame = get_index_prices(start_date, end_date)

    return frame["close_value"].rename("nifty50_close")


if __name__ == "__main__":
    prices = get_index_prices()

    print("GREEDY STOCKS — NIFTY 50 INDEX ADAPTER")
    print("Database writes: NONE")
    print("Index:", INDEX_SYMBOL)
    print("Data source:", INDEX_DATA_SOURCE)
    print("Records:", len(prices))

    if not prices.empty:
        print("First date:", prices.index.min().date())
        print("Last date:", prices.index.max().date())
        print("\nLatest five sessions:")
        print(prices.tail(5).to_string())
