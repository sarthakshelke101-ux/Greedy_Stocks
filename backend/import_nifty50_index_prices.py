import argparse
import csv
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from database import engine

CSV_PATH = ROOT / "database/raw/index/nifty50_historical_pr_10y_candidate.csv"
INDEX_SYMBOL = "NIFTY 50"
DATA_SOURCE = "NSE Indices Historical PR"
START = "2016-11-08"
END = "2026-11-06"
EXPECTED_ROWS = 2478

FIELDS = ["Index Name", "Date", "Open", "High", "Low", "Close"]
PRICE_FIELDS = ["open_value", "high_value", "low_value", "close_value"]

SELECT_SQL = text("""
    SELECT trade_date, open_value, high_value, low_value, close_value
    FROM index_prices
    WHERE index_symbol = :symbol
      AND trade_date BETWEEN :start_date AND :end_date
    ORDER BY trade_date
""")

INSERT_SQL = text("""
    INSERT INTO index_prices (
        index_symbol, trade_date, open_value, high_value,
        low_value, close_value, data_source
    )
    VALUES (
        :index_symbol, :trade_date, :open_value, :high_value,
        :low_value, :close_value, :data_source
    )
""")

UPDATE_CORRECTION_SQL = text("""
    UPDATE index_prices
    SET high_value = :high_value,
        data_source = :data_source
    WHERE index_symbol = :symbol
      AND trade_date = :trade_date
""")

def load_csv():
    if not CSV_PATH.exists():
        raise FileNotFoundError(CSV_PATH)

    records = []
    seen = set()

    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if set(reader.fieldnames or []) != set(FIELDS):
            raise ValueError(f"Unexpected columns: {reader.fieldnames}")

        for line, row in enumerate(reader, 2):
            if row["Index Name"].strip() != INDEX_SYMBOL:
                raise ValueError(f"Wrong index at line {line}")

            d = datetime.strptime(row["Date"].strip(), "%d %b %Y").date()
            if d in seen:
                raise ValueError(f"Duplicate date: {d}")
            seen.add(d)

            try:
                values = {
                    "open_value": Decimal(row["Open"]),
                    "high_value": Decimal(row["High"]),
                    "low_value": Decimal(row["Low"]),
                    "close_value": Decimal(row["Close"]),
                }
            except (InvalidOperation, TypeError):
                raise ValueError(f"Invalid OHLC at line {line}")

            if any(not v.is_finite() or v <= 0 for v in values.values()):
                raise ValueError(f"Invalid/non-positive OHLC at line {line}")

            o, h, l, c = [values[k] for k in PRICE_FIELDS]
            if h < max(o, c) or l > min(o, c) or h < l:
                raise ValueError(f"Invalid OHLC relationship at line {line}")

            records.append({
                "index_symbol": INDEX_SYMBOL,
                "trade_date": d,
                **{k: v.quantize(Decimal("0.0001")) for k, v in values.items()},
                "data_source": DATA_SOURCE,
            })

    records.sort(key=lambda x: x["trade_date"])

    if len(records) != EXPECTED_ROWS:
        raise ValueError(f"Expected {EXPECTED_ROWS} rows; found {len(records)}")
    if records[0]["trade_date"].isoformat() != START:
        raise ValueError("Incorrect first date")
    if records[-1]["trade_date"].isoformat() != END:
        raise ValueError("Incorrect last date")

    return records

def run(commit=False):
    records = load_csv()
    start, end = records[0]["trade_date"], records[-1]["trade_date"]
    incoming = {r["trade_date"]: r for r in records}

    with engine.connect() as conn:
        existing_rows = conn.execute(
            SELECT_SQL,
            {"symbol": INDEX_SYMBOL, "start_date": start, "end_date": end}
        ).mappings().all()

    existing = {r["trade_date"]: dict(r) for r in existing_rows}
    inserts = []
    corrections = []
    unchanged = 0

    for d, new in incoming.items():
        old = existing.get(d)
        if old is None:
            inserts.append(new)
            continue

        differences = []
        for field in PRICE_FIELDS:
            a = Decimal(str(old[field]))
            b = new[field]
            if abs(a - b) > Decimal("0.011"):
                differences.append((field, a, b))

        if not differences:
            unchanged += 1
            continue

        # Sole allowed correction independently re-fetched from NSE.
        if (
            d.isoformat() == "2025-09-18"
            and differences == [("high_value", Decimal("25448.9500"), Decimal("25448.5500"))]
        ):
            corrections.append({
                "trade_date": d,
                "high_value": new["high_value"],
                "symbol": INDEX_SYMBOL,
                "data_source": DATA_SOURCE,
            })
        else:
            raise RuntimeError(f"Unapproved DB discrepancy on {d}: {differences}")

    print("\\n--- NIFTY 50 PR IMPORT REVIEW ---")
    print("CSV records:", len(records))
    print("Existing DB records:", len(existing))
    print("Unchanged overlaps:", unchanged)
    print("New records to insert:", len(inserts))
    print("Verified correction to apply:", len(corrections))
    print("Date range:", start, "to", end)

    if len(existing) + len(inserts) != EXPECTED_ROWS:
        raise RuntimeError(
            f"Unexpected final count: {len(existing)} existing + "
            f"{len(inserts)} new != {EXPECTED_ROWS}"
        )

    if not commit:
        print("\\nDRY RUN PASSED ? NO DATABASE WRITES.")
        print("Review the counts, then run with --commit.")
        return

    with engine.begin() as conn:
        # Recheck inside the write transaction to avoid stale preflight state.
        current_rows = conn.execute(
            SELECT_SQL,
            {"symbol": INDEX_SYMBOL, "start_date": start, "end_date": end}
        ).mappings().all()
        current = {r["trade_date"]: dict(r) for r in current_rows}

        if current != existing:
            raise RuntimeError("Database changed since preflight; transaction aborted.")

        if inserts:
            conn.execute(INSERT_SQL, inserts)

        for correction in corrections:
            result = conn.execute(UPDATE_CORRECTION_SQL, correction)
            if result.rowcount != 1:
                raise RuntimeError("Expected exactly one corrected DB row.")

        final_rows = conn.execute(
            SELECT_SQL,
            {"symbol": INDEX_SYMBOL, "start_date": start, "end_date": end}
        ).mappings().all()

        if len(final_rows) != EXPECTED_ROWS:
            raise RuntimeError(f"Post-import count mismatch: {len(final_rows)}")

        final = {r["trade_date"]: r for r in final_rows}
        for d, expected in incoming.items():
            actual = final.get(d)
            if actual is None:
                raise RuntimeError(f"Post-import date missing: {d}")
            for field in PRICE_FIELDS:
                if abs(Decimal(str(actual[field])) - expected[field]) > Decimal("0.011"):
                    raise RuntimeError(f"Post-import value mismatch: {d} {field}")

    print("\\nIMPORT COMMITTED SUCCESSFULLY.")
    print("Inserted:", len(inserts))
    print("Corrected:", len(corrections))
    print("Final verified rows:", EXPECTED_ROWS)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    try:
        run(commit=args.commit)
    except Exception as exc:
        print(f"IMPORT FAILED: {exc}")
        raise SystemExit(1)
