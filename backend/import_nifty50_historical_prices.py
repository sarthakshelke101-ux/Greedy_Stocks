import sys
import argparse
sys.path.insert(0, "backend")
from pathlib import Path
from zipfile import ZipFile
from io import BytesIO
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pandas as pd
from sqlalchemy import text
from database import engine

ROOT = Path("database/raw/bhavcopy")

UDIFF_REQUIRED = {
    "TradDt", "TckrSymb", "SctySrs", "OpnPric", "HghPric", "LwPric",
    "ClsPric", "PrvsClsgPric", "TtlTradgVol", "TtlTrfVal",
    "TtlNbOfTxsExctd"
}
LEGACY_REQUIRED = {
    "SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE", "PREVCLOSE",
    "TOTTRDQTY", "TOTTRDVAL", "TIMESTAMP", "TOTALTRADES"
}
UDIFF_MAP = {
    "TradDt": "trade_date", "TckrSymb": "symbol", "SctySrs": "series",
    "OpnPric": "open_price", "HghPric": "high_price", "LwPric": "low_price",
    "ClsPric": "close_price", "PrvsClsgPric": "previous_close",
    "TtlTradgVol": "total_traded_volume", "TtlTrfVal": "total_traded_value",
    "TtlNbOfTxsExctd": "total_trades", "ISIN": "isin"
}
LEGACY_MAP = {
    "TIMESTAMP": "trade_date", "SYMBOL": "symbol", "SERIES": "series",
    "OPEN": "open_price", "HIGH": "high_price", "LOW": "low_price",
    "CLOSE": "close_price", "PREVCLOSE": "previous_close",
    "TOTTRDQTY": "total_traded_volume", "TOTTRDVAL": "total_traded_value",
    "TOTALTRADES": "total_trades", "ISIN": "isin"
}
INSERT_SQL = text("""
    INSERT INTO stock_prices (
        company_id, trade_date, open_price, high_price, low_price, close_price,
        previous_close, total_traded_volume, total_traded_value, total_trades,
        price_source
    ) VALUES (
        :company_id, :trade_date, :open_price, :high_price, :low_price,
        :close_price, :previous_close, :total_traded_volume,
        :total_traded_value, :total_trades, :price_source
    )
""")


def decimal_value(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError("Non-finite decimal")
        return number.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def load_company_map(conn):
    # Include inactive identities for historical symbols (e.g. TATAMOTORS).
    rows = conn.execute(
        text("SELECT id, symbol, isin FROM companies")
    ).mappings().all()
    return {
        str(r["symbol"]).strip().upper(): {
            "id": r["id"],
            "isin": str(r["isin"]).strip().upper() if r["isin"] else None
        }
        for r in rows
    }


def read_bhavcopy(zf):
    bad_member = zf.testzip()
    if bad_member is not None:
        raise ValueError(f"ZIP CRC validation failed: {bad_member}")
    members = [
        n for n in zf.namelist()
        if n.lower().endswith(".csv") and not n.endswith("/")
    ]
    if len(members) != 1:
        raise ValueError(f"Expected exactly one CSV; found {len(members)}")
    member = members[0]
    with zf.open(member) as f:
        df = pd.read_csv(BytesIO(f.read()), dtype=str)
    if UDIFF_REQUIRED.issubset(df.columns):
        return member, df, "UDIFF"
    if LEGACY_REQUIRED.issubset(df.columns):
        return member, df, "LEGACY"
    raise ValueError(
        "Unrecognized NSE CSV format. "
        f"UDiFF missing: {sorted(UDIFF_REQUIRED - set(df.columns))}; "
        f"legacy missing: {sorted(LEGACY_REQUIRED - set(df.columns))}"
    )


def normalize_rows(df, company_map, archive_name, file_format):
    if file_format == "UDIFF":
        required, rename_map = UDIFF_REQUIRED, UDIFF_MAP
        source_label = "NSE CM-UDiFF EQ"
    elif file_format == "LEGACY":
        required, rename_map = LEGACY_REQUIRED, LEGACY_MAP
        source_label = "NSE CM-Legacy EQ"
    else:
        raise ValueError(f"Unsupported format: {file_format}")

    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in {archive_name}: {sorted(missing)}")

    work = df.copy().rename(columns=rename_map)
    text_cols = [
        "trade_date", "symbol", "series", "open_price", "high_price",
        "low_price", "close_price", "previous_close", "total_traded_volume",
        "total_traded_value", "total_trades"
    ]
    for col in text_cols:
        work[col] = work[col].fillna("").astype(str).str.strip()
    if "isin" not in work.columns:
        work["isin"] = ""
    work["isin"] = work["isin"].fillna("").astype(str).str.strip().str.upper()
    work["symbol"] = work["symbol"].str.upper()
    work["series"] = work["series"].str.upper()

    work = work[work["series"] == "EQ"].copy()
    eq_count = len(work)
    work = work[work["symbol"].isin(company_map)].copy()
    matched_count = len(work)
    stats = {
        "eq_rows": eq_count,
        "matched_rows": matched_count,
        "unmatched_eq_rows": eq_count - matched_count
    }
    if work.empty:
        return [], stats

    # If both ISINs exist, disagreement rejects the archive for manual review.
    mismatches = []
    for rec in work[["symbol", "isin"]].drop_duplicates().to_dict("records"):
        db_isin = company_map[rec["symbol"]]["isin"]
        archive_isin = rec["isin"]
        if db_isin and archive_isin and db_isin != archive_isin:
            mismatches.append(
                f'{rec["symbol"]}: DB={db_isin}, archive={archive_isin}'
            )
    if mismatches:
        raise ValueError("ISIN mismatch; no rows imported: " + "; ".join(mismatches[:20]))

    if file_format == "LEGACY":
        dates = pd.to_datetime(
            work["trade_date"],
            format="mixed",
            dayfirst=True,
            errors="coerce"
        ).dt.date
    else:
        dates = pd.to_datetime(
            work["trade_date"],
            errors="coerce"
        ).dt.date
    if dates.isna().any():
        bad = work.loc[dates.isna(), "trade_date"].head(5).tolist()
        raise ValueError(f"Invalid trade date(s) in {archive_name}: {bad}")
    work["trade_date"] = dates

    numeric_cols = [
        "open_price", "high_price", "low_price", "close_price",
        "previous_close", "total_traded_volume", "total_traded_value",
        "total_trades"
    ]
    for col in numeric_cols:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    if work[numeric_cols].isna().any().any():
        bad_cols = [c for c in numeric_cols if work[c].isna().any()]
        raise ValueError(f"Invalid numeric data in {archive_name}: {bad_cols}")

    price_cols = [
        "open_price", "high_price", "low_price", "close_price", "previous_close"
    ]
    if (work[price_cols] <= 0).any().any():
        raise ValueError(f"Non-positive price in {archive_name}")
    stat_cols = ["total_traded_volume", "total_traded_value", "total_trades"]
    if (work[stat_cols] < 0).any().any():
        raise ValueError(f"Negative trading statistic in {archive_name}")
    for col in ["total_traded_volume", "total_trades"]:
        if ((work[col] % 1) != 0).any():
            raise ValueError(f"Non-integer {col} in {archive_name}")

    invalid_ohlc = (
        (work["high_price"] < work["low_price"]) |
        (work["high_price"] < work["open_price"]) |
        (work["high_price"] < work["close_price"]) |
        (work["low_price"] > work["open_price"]) |
        (work["low_price"] > work["close_price"])
    )
    if invalid_ohlc.any():
        raise ValueError(f"OHLC inconsistency in {archive_name}")
    if work.duplicated(["trade_date", "symbol"]).any():
        raise ValueError(f"Duplicate EQ symbol/date in {archive_name}")
    unique_dates = work["trade_date"].unique()
    if len(unique_dates) != 1:
        raise ValueError(f"Expected one date per archive; found {len(unique_dates)}")

    rows = []
    for rec in work.to_dict("records"):
        identity = company_map[rec["symbol"]]
        rows.append({
            "company_id": identity["id"],
            "symbol": rec["symbol"],
            "trade_date": rec["trade_date"],
            "open_price": decimal_value(rec["open_price"]),
            "high_price": decimal_value(rec["high_price"]),
            "low_price": decimal_value(rec["low_price"]),
            "close_price": decimal_value(rec["close_price"]),
            "previous_close": decimal_value(rec["previous_close"]),
            "total_traded_volume": int(rec["total_traded_volume"]),
            "total_traded_value": decimal_value(rec["total_traded_value"]),
            "total_trades": int(rec["total_trades"]),
            "price_source": source_label
        })
    return rows, stats


def existing_rows_for_date(conn, trade_date):
    records = conn.execute(text("""
        SELECT company_id, trade_date, open_price, high_price, low_price,
               close_price, previous_close, total_traded_volume,
               total_traded_value, total_trades
        FROM stock_prices WHERE trade_date = :trade_date
    """), {"trade_date": trade_date}).mappings().all()
    return {(r["company_id"], r["trade_date"]): r for r in records}


def values_match(old, new):
    decimal_fields = [
        "open_price", "high_price", "low_price", "close_price",
        "previous_close", "total_traded_value"
    ]
    integer_fields = ["total_traded_volume", "total_trades"]
    for field in decimal_fields:
        if old[field] is None or Decimal(str(old[field])) != new[field]:
            return False
    for field in integer_fields:
        if old[field] is None or int(old[field]) != new[field]:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Import NSE CM historical prices (legacy and UDiFF)."
    )
    parser.add_argument("--archive", type=Path,
                        help="Import only this NSE Bhavcopy ZIP.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate and compare without inserting records.")
    args = parser.parse_args()

    if args.archive:
        archive = args.archive.resolve()
        if not archive.is_file() or archive.suffix.lower() != ".zip":
            raise FileNotFoundError(f"Valid ZIP archive not found: {archive}")
        archives, mode = [archive], "SINGLE ARCHIVE"
    else:
        if not ROOT.exists():
            raise FileNotFoundError(f"Archive directory not found: {ROOT}")
        archives, mode = sorted(ROOT.rglob("*.zip")), "FULL HISTORICAL"
    if not archives:
        raise FileNotFoundError("No ZIP archives found.")

    with engine.connect() as conn:
        company_map = load_company_map(conn)

    print("=" * 68)
    print("GREEDY STOCKS - NSE HISTORICAL PRICE IMPORT")
    print("=" * 68)
    print("Import mode:", mode)
    print("Execution:", "DRY RUN - NO WRITES" if args.dry_run else "LIVE IMPORT")
    print("Archives:", len(archives))
    print("Company identities:", len(company_map), "(including inactive)")
    print("Series allowed: EQ only")
    print()

    inserted = unchanged = skipped = legacy_count = udiff_count = 0
    matched_total = unmatched_total = 0
    rejected = []

    for index, archive in enumerate(archives, 1):
        try:
            with ZipFile(archive) as zf:
                _, df, file_format = read_bhavcopy(zf)
            rows, stats = normalize_rows(df, company_map, archive.name, file_format)

            if file_format == "LEGACY":
                legacy_count += 1
            else:
                udiff_count += 1
            matched_total += stats["matched_rows"]
            unmatched_total += stats["unmatched_eq_rows"]

            if not rows:
                skipped += 1
                print(f"SKIPPED (no registered EQ rows): {archive.name}")
                continue

            trade_date = rows[0]["trade_date"]
            new_count = same_count = 0

            if args.dry_run:
                with engine.connect() as conn:
                    old_rows = existing_rows_for_date(conn, trade_date)
                    for row in rows:
                        key = (row["company_id"], row["trade_date"])
                        if key in old_rows:
                            if not values_match(old_rows[key], row):
                                raise ValueError(
                                    f'Conflicting existing price: {row["symbol"]} '
                                    f'on {trade_date}'
                                )
                            same_count += 1
                        else:
                            new_count += 1
            else:
                # Keep one atomic transaction per archive.
                with engine.begin() as conn:
                    old_rows = existing_rows_for_date(conn, trade_date)
                    for row in rows:
                        key = (row["company_id"], row["trade_date"])
                        if key in old_rows:
                            if not values_match(old_rows[key], row):
                                raise ValueError(
                                    f'Conflicting existing price: {row["symbol"]} '
                                    f'on {trade_date}'
                                )
                            same_count += 1
                        else:
                            conn.execute(INSERT_SQL, row)
                            new_count += 1

            inserted += new_count
            unchanged += same_count
            print(
                f"[{file_format}] {archive.name} | {trade_date} | "
                f"EQ matched {stats['matched_rows']} | "
                f"unmatched {stats['unmatched_eq_rows']} | "
                f"new {new_count} | unchanged {same_count}"
            )
        except Exception as exc:
            rejected.append((archive.name, str(exc)))
            print(f"REJECTED: {archive.name} | {exc}")

        if index % 25 == 0 or index == len(archives):
            print(
                f"Progress {index}/{len(archives)} | Inserted {inserted} | "
                f"Unchanged {unchanged} | Skipped {skipped} | "
                f"Rejected {len(rejected)}"
            )

    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM stock_prices")).scalar_one()
        date_range = conn.execute(text("""
            SELECT MIN(trade_date), MAX(trade_date),
                   COUNT(DISTINCT trade_date), COUNT(DISTINCT company_id)
            FROM stock_prices
        """)).fetchone()

    print("\n" + "=" * 68)
    print("IMPORT SUMMARY")
    print("=" * 68)
    print("Execution:", "DRY RUN - NO WRITES" if args.dry_run else "LIVE IMPORT")
    print("Archives discovered:", len(archives))
    print("Legacy archives:", legacy_count)
    print("UDiFF archives:", udiff_count)
    print("Matched EQ rows:", matched_total)
    print("Unmatched EQ rows:", unmatched_total)
    print("New price records:", inserted)
    print("Already matching records:", unchanged)
    print("Skipped archives:", skipped)
    print("Rejected archives:", len(rejected))
    print("Total database price records:", total)
    print("First date:", date_range[0])
    print("Last date:", date_range[1])
    print("Trading dates:", date_range[2])
    print("Companies represented:", date_range[3])

    if rejected:
        print("\nREJECTED ARCHIVES - INVESTIGATION REQUIRED")
        for name, reason in rejected:
            print(f"{name}: {reason}")
        raise RuntimeError(f"{len(rejected)} archive(s) were rejected.")


if __name__ == "__main__":
    main()
