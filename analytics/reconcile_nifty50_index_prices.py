
import csv
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from database import engine

CSV_PATH = (
    ROOT / "database" / "raw" / "index"
    / "nifty50_historical_pr_combined.csv"
)

PRICE_FIELDS = {
    "Open": "open_value",
    "High": "high_value",
    "Low": "low_value",
    "Close": "close_value",
}

def main():
    source = {}

    with CSV_PATH.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            date = datetime.strptime(
                row["Date"].strip(), "%d %b %Y"
            ).date()

            source[date] = {
                field: Decimal(row[column].strip()).quantize(
                    Decimal("0.0001")
                )
                for column, field in PRICE_FIELDS.items()
            }

    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT trade_date, open_value, high_value,
                       low_value, close_value
                FROM index_prices
                WHERE index_symbol = 'NIFTY 50'
                ORDER BY trade_date
            """)
        ).mappings().all()

    database = {
        row["trade_date"]: {
            field: row[field]
            for field in PRICE_FIELDS.values()
        }
        for row in result
    }

    source_dates = set(source)
    database_dates = set(database)

    missing = sorted(source_dates - database_dates)
    extra = sorted(database_dates - source_dates)

    mismatches = []

    for date in sorted(source_dates & database_dates):
        for field in PRICE_FIELDS.values():
            expected = source[date][field]
            actual = Decimal(str(database[date][field])).quantize(
                Decimal("0.0001")
            )

            if expected != actual:
                mismatches.append({
                    "date": date,
                    "field": field,
                    "source": expected,
                    "database": actual,
                })

    print("\n--- NIFTY 50 SOURCE RECONCILIATION ---")
    print(f"Source records: {len(source)}")
    print(f"Database records: {len(database)}")
    print(f"Missing database dates: {len(missing)}")
    print(f"Extra database dates: {len(extra)}")
    print(f"OHLC field mismatches: {len(mismatches)}")

    if missing:
        print("\nMissing dates:", missing)

    if extra:
        print("\nExtra dates:", extra)

    if mismatches:
        print("\nFirst 20 mismatches:")
        for item in mismatches[:20]:
            print(item)

    if (
        len(source) == 396
        and len(database) == 396
        and not missing
        and not extra
        and not mismatches
    ):
        print("\nPASS: All 396 records match the source exactly.")
    else:
        print("\nFAIL: Reconciliation requires investigation.")

if __name__ == "__main__":
    main()
