"""Import verified corporate actions into GREEDY STOCKS.

Idempotent and transactional.
Original stock_prices records are never modified.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text
from database import engine


ACTIONS = [
    {
        "symbol": "BAJFINANCE",
        "action_type": "STOCK_SPLIT",
        "announcement_date": "2025-05-02",
        "ex_date": "2025-06-16",
        "record_date": "2025-06-16",
        "effective_date": "2025-06-16",
        "ratio": "2:1",
        "description": (
            "Face value subdivision from INR 2 to INR 1; "
            "2 new shares for each old share. "
            "Price adjustment factor: 2."
        ),
        "source_name": "NSE corporate actions / issuer announcement",
        "source_reference": (
            "https://www.nseindia.com/get-quote/equity/"
            "BAJFINANCE/Bajaj-Finance-Limited"
        ),
    },
    {
        "symbol": "BAJFINANCE",
        "action_type": "BONUS",
        "announcement_date": "2025-05-02",
        "ex_date": "2025-06-16",
        "record_date": "2025-06-16",
        "effective_date": "2025-06-16",
        "ratio": "4:1",
        "description": (
            "Four bonus shares for every one existing share. "
            "Price adjustment factor: 5. "
            "Combined with same-day 2:1 split, "
            "total pre-event price factor: 10."
        ),
        "source_name": "NSE corporate actions / issuer announcement",
        "source_reference": (
            "https://www.nseindia.com/get-quote/equity/"
            "BAJFINANCE/Bajaj-Finance-Limited"
        ),
    },
    {
        "symbol": "KOTAKBANK",
        "action_type": "STOCK_SPLIT",
        "announcement_date": "2026-01-13",
        "ex_date": "2026-01-14",
        "record_date": "2026-01-14",
        "effective_date": "2026-01-14",
        "ratio": "5:1",
        "description": (
            "Face value subdivision from INR 5 to INR 1; "
            "5 new shares for each old share. "
            "Price adjustment factor: 5."
        ),
        "source_name": "NSE Circular NSE/FAOP/72303",
        "source_reference": (
            "https://nsearchives.nseindia.com/content/"
            "circulars/FAOP72303.pdf"
        ),
    },
    {
        "symbol": "BSE",
        "action_type": "BONUS",
        "announcement_date": None,
        "ex_date": "2025-05-23",
        "record_date": "2025-05-23",
        "effective_date": "2025-05-23",
        "ratio": "2:1",
        "description": (
            "Two bonus shares for every one existing share. "
            "Price adjustment factor: 3."
        ),
        "source_name": "NSE corporate actions",
        "source_reference": (
            "https://www.nseindia.com/get-quote/equity/"
            "BSE/BSE-Limited"
        ),
    },
    {
        "symbol": "NESTLEIND",
        "action_type": "BONUS",
        "announcement_date": "2025-07-29",
        "ex_date": "2025-08-08",
        "record_date": "2025-08-08",
        "effective_date": "2025-08-11",
        "ratio": "1:1",
        "description": (
            "One bonus share for every one existing share. "
            "Price adjustment factor: 2. "
            "Bonus allotment deemed date: 11 August 2025."
        ),
        "source_name": "Nestle India issuer filing",
        "source_reference": (
            "https://www.nestle.in/sites/g/files/pydnoa451/"
            "files/2025-08/Nestle%20-%20Intimation%20of%20"
            "Record%20Date%20for%20bonus%20shares.pdf"
        ),
    },
    {
        "symbol": "HDFCBANK",
        "action_type": "BONUS",
        "announcement_date": None,
        "ex_date": "2025-08-26",
        "record_date": "2025-08-27",
        "effective_date": "2025-08-27",
        "ratio": "1:1",
        "description": (
            "One bonus share for every one existing share. "
            "Price adjustment factor: 2."
        ),
        "source_name": "NSE corporate actions",
        "source_reference": (
            "https://www.nseindia.com/get-quote/equity/"
            "HDFCBANK/HDFC-Bank-Limited"
        ),
    },
    {
        "symbol": "TRENT",
        "action_type": "BONUS",
        "announcement_date": "2026-04-22",
        "ex_date": "2026-06-04",
        "record_date": "2026-06-04",
        "effective_date": "2026-06-04",
        "ratio": "1:2",
        "description": (
            "One bonus share for every two existing shares. "
            "Price adjustment factor: 1.5."
        ),
        "source_name": "NSE corporate actions / Trent issuer filing",
        "source_reference": (
            "https://nsearchives.nseindia.com/corporate/"
            "TRENT_22042026155430_OutcomeofBMFINAL.pdf"
        ),
    },
]


def main():
    inserted = 0
    skipped = 0

    with engine.begin() as conn:
        for action in ACTIONS:
            company_id = conn.execute(
                text("""
                    SELECT id
                    FROM companies
                    WHERE symbol = :symbol
                """),
                {"symbol": action["symbol"]},
            ).scalar_one_or_none()

            if company_id is None:
                raise ValueError(
                    f"Company not found: {action['symbol']}"
                )

            exists = conn.execute(
                text("""
                    SELECT id
                    FROM corporate_actions
                    WHERE company_id = :company_id
                      AND action_type = :action_type
                      AND ex_date = :ex_date
                      AND ratio = :ratio
                    LIMIT 1
                """),
                {
                    "company_id": company_id,
                    "action_type": action["action_type"],
                    "ex_date": action["ex_date"],
                    "ratio": action["ratio"],
                },
            ).scalar_one_or_none()

            if exists:
                print(
                    f"SKIP   {action['symbol']:12} "
                    f"{action['action_type']:12} "
                    f"{action['ex_date']} "
                    f"(existing ID {exists})"
                )
                skipped += 1
                continue

            conn.execute(
                text("""
                    INSERT INTO corporate_actions (
                        company_id,
                        action_type,
                        announcement_date,
                        ex_date,
                        record_date,
                        effective_date,
                        description,
                        ratio,
                        dividend_amount,
                        source_name,
                        source_reference
                    ) VALUES (
                        :company_id,
                        :action_type,
                        :announcement_date,
                        :ex_date,
                        :record_date,
                        :effective_date,
                        :description,
                        :ratio,
                        NULL,
                        :source_name,
                        :source_reference
                    )
                """),
                {
                    "company_id": company_id,
                    **action,
                },
            )

            print(
                f"INSERT {action['symbol']:12} "
                f"{action['action_type']:12} "
                f"{action['ex_date']} "
                f"ratio={action['ratio']}"
            )
            inserted += 1

        total = conn.execute(
            text("SELECT COUNT(*) FROM corporate_actions")
        ).scalar_one()

    print("\n" + "=" * 65)
    print("CORPORATE ACTION IMPORT COMPLETE")
    print("=" * 65)
    print("New records:", inserted)
    print("Existing records skipped:", skipped)
    print("Total corporate-action records:", total)
    print("Original stock_prices modified: NO")


if __name__ == "__main__":
    main()
