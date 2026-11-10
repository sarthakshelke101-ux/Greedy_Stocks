"""Validate split/bonus-adjusted prices against imported MySQL data."""

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "backend"))

from database import engine
from analytics.adjusted_prices import build_adjusted_prices


TARGET_SYMBOLS = [
    "BAJFINANCE",
    "KOTAKBANK",
    "BSE",
    "NESTLEIND",
    "HDFCBANK",
    "TRENT",
]

START_DATE = "2025-04-01"
END_DATE = "2026-11-05"


def load_company_data(conn, symbol):
    company = conn.execute(
        text("""
            SELECT id, symbol, company_name
            FROM companies
            WHERE symbol = :symbol
        """),
        {"symbol": symbol},
    ).mappings().one_or_none()

    if company is None:
        raise ValueError(f"Company not found: {symbol}")

    prices = pd.read_sql(
        text("""
            SELECT trade_date, close_price AS close
            FROM stock_prices
            WHERE company_id = :company_id
              AND trade_date BETWEEN :start_date AND :end_date
            ORDER BY trade_date
        """),
        conn,
        params={
            "company_id": company["id"],
            "start_date": START_DATE,
            "end_date": END_DATE,
        },
    )

    actions = conn.execute(
        text("""
            SELECT
                action_type,
                ex_date,
                ratio,
                source_name,
                source_reference
            FROM corporate_actions
            WHERE company_id = :company_id
            ORDER BY ex_date
        """),
        {"company_id": company["id"]},
    ).mappings().all()

    return company, prices, [dict(action) for action in actions]


def main():
    print("=" * 75)
    print("GREEDY STOCKS — ADJUSTED PRICE VALIDATION")
    print("=" * 75)
    print("Raw price range:", START_DATE, "to", END_DATE)
    print("Price basis: split/bonus adjusted; no dividend reinvestment")
    print()

    with engine.connect() as conn:
        for symbol in TARGET_SYMBOLS:
            company, prices, actions = load_company_data(conn, symbol)

            if prices.empty:
                print(f"[FAIL] {symbol}: no historical prices")
                continue

            if not actions:
                print(f"[FAIL] {symbol}: no corporate actions found")
                continue

            adjusted = build_adjusted_prices(prices, actions)

            print("-" * 75)
            print(f"{symbol} — {company['company_name']}")
            print(f"Raw observations: {len(prices)}")
            print(f"Corporate actions: {len(actions)}")
            print(
                "Date range:",
                adjusted["trade_date"].min().date(),
                "to",
                adjusted["trade_date"].max().date(),
            )

            for action in actions:
                event_date = pd.Timestamp(action["ex_date"])
                event_rows = adjusted[
                    (adjusted["trade_date"] >= event_date - pd.Timedelta(days=5))
                    & (adjusted["trade_date"] <= event_date + pd.Timedelta(days=5))
                ]

                print(
                    f"\nAction: {action['action_type']} "
                    f"{action['ratio']} | Ex-date: {event_date.date()}"
                )
                print(
                    event_rows[
                        [
                            "trade_date",
                            "close",
                            "adjustment_factor",
                            "adjusted_close",
                        ]
                    ].to_string(index=False)
                )

            # Verify that the calculation did not alter raw closing prices.
            raw_preserved = adjusted["close"].equals(
                prices.sort_values("trade_date")
                .reset_index(drop=True)["close"]
            )

            # Verify every ex-date has factor 1 for that event.
            event_dates_valid = True
            for action in actions:
                ex_date = pd.Timestamp(action["ex_date"])
                ex_rows = adjusted[adjusted["trade_date"] == ex_date]
                if not ex_rows.empty:
                    # Earlier actions may affect this date, but this event
                    # itself must not affect its own ex-date price.
                    earlier_factor = 1.0
                    for previous in actions:
                        previous_date = pd.Timestamp(previous["ex_date"])
                        if previous_date > ex_date:
                            continue
                        if previous_date == ex_date:
                            continue
                        if previous_date > ex_date:
                            continue
                        from analytics.adjusted_prices import action_adjustment_factor
                        earlier_factor *= float(action_adjustment_factor(previous))
                    if abs(ex_rows.iloc[0]["adjustment_factor"] - earlier_factor) > 1e-9:
                        event_dates_valid = False

            print("\nRaw prices preserved:", raw_preserved)
            print("Ex-date treatment valid:", event_dates_valid)

            if raw_preserved and event_dates_valid:
                print(f"[PASS] {symbol}")
            else:
                print(f"[FAIL] {symbol}")

    print("\n" + "=" * 75)
    print("VALIDATION RUN COMPLETE")
    print("No database rows were inserted, updated, or deleted.")
    print("=" * 75)


if __name__ == "__main__":
    main()
