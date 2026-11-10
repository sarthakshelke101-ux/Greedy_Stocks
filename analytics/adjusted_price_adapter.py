
"""Read-only database adapter for split/bonus-adjusted prices.

Raw database prices remain untouched.
Dividends, rights, mergers and demergers are not adjusted.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from backend.database import engine
from analytics.adjusted_prices import build_adjusted_prices


def get_company_actions(
    company_id: int,
    end_date: str | None = None,
) -> list[dict]:
    """Load supported corporate actions up to the requested date."""

    query = text("""
        SELECT
            action_type,
            ex_date,
            ratio,
            source_name,
            source_reference
        FROM corporate_actions
        WHERE company_id = :company_id
          AND action_type IN ('STOCK_SPLIT', 'BONUS')
          AND (:end_date IS NULL OR ex_date <= :end_date)
        ORDER BY ex_date, id
    """)

    with engine.connect() as conn:
        rows = conn.execute(
            query,
            {
                "company_id": company_id,
                "end_date": end_date,
            },
        ).mappings().all()

    return [dict(row) for row in rows]


def get_adjusted_company_prices(
    company_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """Return raw and split/bonus-adjusted historical prices.

    All available price history up to end_date is loaded before applying
    start_date. This preserves the effect of earlier corporate actions.
    """

    query = text("""
        SELECT trade_date, close_price
        FROM stock_prices
        WHERE company_id = :company_id
          AND (:end_date IS NULL OR trade_date <= :end_date)
        ORDER BY trade_date
    """)

    with engine.connect() as conn:
        rows = conn.execute(
            query,
            {
                "company_id": company_id,
                "end_date": end_date,
            },
        ).mappings().all()

    if not rows:
        result = pd.DataFrame(
            columns=[
                "trade_date",
                "close",
                "adjustment_factor",
                "adjusted_close",
            ]
        )
        result.attrs["company_id"] = company_id
        result.attrs["price_basis"] = "SPLIT_BONUS_ADJUSTED"
        result.attrs["dividend_adjusted"] = False
        result.attrs["corporate_action_coverage"] = "PARTIAL"
        return result

    raw_prices = pd.DataFrame([dict(row) for row in rows])

    raw_prices["close"] = pd.to_numeric(
        raw_prices.pop("close_price"),
        errors="coerce",
    )

    actions = get_company_actions(
        company_id=company_id,
        end_date=end_date,
    )

    adjusted = build_adjusted_prices(
        prices=raw_prices,
        actions=actions,
        date_col="trade_date",
        price_col="close",
    )

    if start_date is not None:
        start = pd.Timestamp(start_date)

        if start.tz is not None:
            raise ValueError("start_date must not contain a timezone")

        adjusted = adjusted[
            adjusted["trade_date"] >= start.normalize()
        ]

    adjusted = adjusted.reset_index(drop=True)

    adjusted.attrs["company_id"] = company_id
    adjusted.attrs["price_basis"] = "SPLIT_BONUS_ADJUSTED"
    adjusted.attrs["dividend_adjusted"] = False
    adjusted.attrs["corporate_action_coverage"] = "PARTIAL"

    return adjusted


if __name__ == "__main__":
    print("ADJUSTED PRICE ADAPTER — READ-ONLY TEST")

    query = text("""
        SELECT id, symbol
        FROM companies
        WHERE symbol IN (
            'BAJFINANCE',
            'KOTAKBANK',
            'BSE',
            'NESTLEIND',
            'HDFCBANK',
            'TRENT'
        )
        ORDER BY symbol
    """)

    with engine.connect() as conn:
        companies = conn.execute(query).mappings().all()

    for company in companies:
        result = get_adjusted_company_prices(
            company_id=int(company["id"]),
            start_date="2025-04-01",
            end_date="2026-11-05",
        )

        print(f"\n{company['symbol']}")
        print("Price observations:", len(result))
        print("First date:", result["trade_date"].min() if not result.empty else None)
        print("Last date:", result["trade_date"].max() if not result.empty else None)
        print("Price basis:", result.attrs["price_basis"])
        print("Dividend adjusted:", result.attrs["dividend_adjusted"])

        if not result.empty:
            print(
                result[
                    ["trade_date", "close", "adjustment_factor", "adjusted_close"]
                ].tail(3).to_string(index=False)
            )

    print("\nDatabase writes: NONE")
