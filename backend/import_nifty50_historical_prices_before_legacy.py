
import sys
import argparse

sys.path.insert(0, "backend")

from pathlib import Path
from zipfile import ZipFile
from io import BytesIO
from decimal import Decimal

import pandas as pd

from sqlalchemy import text
from database import engine


ROOT = Path("database/raw/bhavcopy")


REQUIRED = {
    "TradDt", "TckrSymb", "SctySrs",
    "OpnPric", "HghPric", "LwPric", "ClsPric",
    "PrvsClsgPric", "TtlTradgVol", "TtlTrfVal",
    "TtlNbOfTxsExctd"
}


PRICE_COLUMNS = {
    "OpnPric": "open_price",
    "HghPric": "high_price",
    "LwPric": "low_price",
    "ClsPric": "close_price",
    "PrvsClsgPric": "previous_close",
    "TtlTradgVol": "total_traded_volume",
    "TtlTrfVal": "total_traded_value",
    "TtlNbOfTxsExctd": "total_trades"
}


INSERT_SQL = text("""
    INSERT INTO stock_prices (
        company_id, trade_date,
        open_price, high_price, low_price, close_price,
        previous_close, total_traded_volume,
        total_traded_value, total_trades, price_source
    ) VALUES (
        :company_id, :trade_date,
        :open_price, :high_price, :low_price, :close_price,
        :previous_close, :total_traded_volume,
        :total_traded_value, :total_trades, 'NSE CM-UDiFF EQ'
    )
""")


def decimal_value(value):
    return Decimal(str(value)).quantize(Decimal("0.0001"))


def load_company_map(conn):
    rows = conn.execute(
        text("SELECT id, symbol FROM companies")
    ).mappings().all()

    return {
        r["symbol"]: r["id"]
        for r in rows
    }


def read_bhavcopy(zf):
    members = [
        n for n in zf.namelist()
        if n.lower().endswith(".csv") and not n.endswith("/")
    ]

    for member in members:
        with zf.open(member) as f:
            raw = f.read()

        try:
            df = pd.read_csv(
                BytesIO(raw),
                dtype=str
            )
        except Exception:
            continue

        if REQUIRED.issubset(df.columns):
            return member, df

    return None, None


def normalize_rows(df, company_map, archive_name):
    df = df.copy()

    for col in REQUIRED:
        df[col] = df[col].astype(str).str.strip()

    # Only EQ series and registered company symbols
    df = df[
        (df["SctySrs"] == "EQ") &
        (df["TckrSymb"].isin(company_map))
    ].copy()

    if df.empty:
        return []

    # Validate trading dates
    df["TradDt"] = pd.to_datetime(
        df["TradDt"],
        errors="coerce"
    ).dt.date

    if df["TradDt"].isna().any():
        raise ValueError(
            f"Invalid trading date in {archive_name}"
        )

    # Convert numerical columns
    for col in PRICE_COLUMNS:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    numeric_cols = list(PRICE_COLUMNS)

    if df[numeric_cols].isna().any().any():
        raise ValueError(
            f"Missing or invalid numeric data in {archive_name}"
        )

    # Prices must be positive
    if (df[[
        "OpnPric", "HghPric", "LwPric",
        "ClsPric", "PrvsClsgPric"
    ]] <= 0).any().any():

        raise ValueError(
            f"Non-positive price in {archive_name}"
        )

    # Trading statistics cannot be negative
    if (df[[
        "TtlTradgVol",
        "TtlTrfVal",
        "TtlNbOfTxsExctd"
    ]] < 0).any().any():

        raise ValueError(
            f"Negative trading statistic in {archive_name}"
        )

    # Validate OHLC relationships
    invalid_ohlc = (
        (df["HghPric"] < df["LwPric"]) |
        (df["HghPric"] < df["OpnPric"]) |
        (df["HghPric"] < df["ClsPric"]) |
        (df["LwPric"] > df["OpnPric"]) |
        (df["LwPric"] > df["ClsPric"])
    )

    if invalid_ohlc.any():
        raise ValueError(
            f"OHLC inconsistency in {archive_name}"
        )

    # No duplicate symbol/date records
    if df.duplicated(["TradDt", "TckrSymb"]).any():
        raise ValueError(
            f"Duplicate EQ symbol/date in {archive_name}"
        )

    # Each archive must represent exactly one trading date
    dates = df["TradDt"].unique()

    if len(dates) != 1:
        raise ValueError(
            f"Expected one trading date per archive, "
            f"found {len(dates)}"
        )

    rows = []

    for r in df.to_dict("records"):
        rows.append({
            "company_id": company_map[r["TckrSymb"]],
            "symbol": r["TckrSymb"],
            "trade_date": r["TradDt"],

            "open_price": decimal_value(r["OpnPric"]),
            "high_price": decimal_value(r["HghPric"]),
            "low_price": decimal_value(r["LwPric"]),
            "close_price": decimal_value(r["ClsPric"]),

            "previous_close": decimal_value(
                r["PrvsClsgPric"]
            ),

            "total_traded_volume": int(
                r["TtlTradgVol"]
            ),

            "total_traded_value": decimal_value(
                r["TtlTrfVal"]
            ),

            "total_trades": int(
                r["TtlNbOfTxsExctd"]
            )
        })

    return rows


def existing_rows_for_date(conn, trade_date):
    records = conn.execute(
        text("""
            SELECT company_id, trade_date,
                   open_price, high_price, low_price, close_price,
                   previous_close, total_traded_volume,
                   total_traded_value, total_trades
            FROM stock_prices
            WHERE trade_date = :trade_date
        """),
        {"trade_date": trade_date}
    ).mappings().all()

    return {
        (r["company_id"], r["trade_date"]): r
        for r in records
    }


def values_match(old, new):
    decimal_fields = [
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "previous_close",
        "total_traded_value"
    ]

    integer_fields = [
        "total_traded_volume",
        "total_trades"
    ]

    for field in decimal_fields:
        if (
            old[field] is None or
            Decimal(str(old[field])) != new[field]
        ):
            return False

    for field in integer_fields:
        if (
            old[field] is None or
            int(old[field]) != new[field]
        ):
            return False

    return True


def main():

    # --------------------------------------------------
    # COMMAND-LINE ARGUMENTS
    # --------------------------------------------------

    parser = argparse.ArgumentParser(
        description=(
            "Import NSE CM-UDiFF historical "
            "or single-archive prices."
        )
    )

    parser.add_argument(
        "--archive",
        type=Path,
        help="Import only this NSE Bhavcopy ZIP archive."
    )

    args = parser.parse_args()

    # --------------------------------------------------
    # SELECT IMPORT MODE
    # --------------------------------------------------

    if args.archive:

        archive = args.archive.resolve()

        if not archive.exists() or not archive.is_file():
            raise FileNotFoundError(
                f"Archive not found: {archive}"
            )

        if archive.suffix.lower() != ".zip":
            raise ValueError(
                "The specified archive must be a ZIP file."
            )

        archives = [archive]
        import_mode = "SINGLE ARCHIVE"

    else:

        if not ROOT.exists():
            raise FileNotFoundError(
                f"Archive directory not found: {ROOT}"
            )

        archives = sorted(
            ROOT.rglob("*.zip")
        )

        import_mode = "FULL HISTORICAL"

    if not archives:
        raise FileNotFoundError(
            "No ZIP archives found."
        )

    # --------------------------------------------------
    # LOAD COMPANY IDENTITIES
    # --------------------------------------------------

    with engine.connect() as conn:
        company_map = load_company_map(conn)

    # --------------------------------------------------
    # IMPORT HEADER
    # --------------------------------------------------

    print("=" * 65)
    print("GREEDY STOCKS - NSE HISTORICAL PRICE IMPORT")
    print("=" * 65)

    print("Import mode:", import_mode)
    print("Archives found:", len(archives))
    print("Company identities:", len(company_map))
    print("Series allowed: EQ only")
    print("Price adjustment: None; raw NSE prices")
    print()

    # --------------------------------------------------
    # IMPORT COUNTERS
    # --------------------------------------------------

    imported = 0
    unchanged = 0
    skipped = 0
    rejected = []

    # --------------------------------------------------
    # PROCESS ARCHIVES
    # --------------------------------------------------

    for index, archive in enumerate(archives, start=1):

        try:

            with ZipFile(archive) as zf:

                member, df = read_bhavcopy(zf)

                if df is None:
                    skipped += 1
                    continue

                rows = normalize_rows(
                    df,
                    company_map,
                    archive.name
                )

                if not rows:
                    skipped += 1
                    continue

                trade_date = rows[0]["trade_date"]

                inserted_this_file = 0
                unchanged_this_file = 0

                # Each archive is handled in one transaction
                with engine.begin() as conn:

                    old_rows = existing_rows_for_date(
                        conn,
                        trade_date
                    )

                    for row in rows:

                        key = (
                            row["company_id"],
                            row["trade_date"]
                        )

                        if key in old_rows:

                            if not values_match(
                                old_rows[key],
                                row
                            ):
                                raise ValueError(
                                    f"Conflicting existing price: "
                                    f"{row['symbol']} "
                                    f"on {trade_date}"
                                )

                            unchanged_this_file += 1

                        else:

                            conn.execute(
                                INSERT_SQL,
                                row
                            )

                            inserted_this_file += 1

                imported += inserted_this_file
                unchanged += unchanged_this_file

        except Exception as exc:

            rejected.append(
                (archive.name, str(exc))
            )

        # Progress display
        if index % 25 == 0 or index == len(archives):

            print(
                f"Processed {index}/{len(archives)} | "
                f"Inserted {imported} | "
                f"Unchanged {unchanged} | "
                f"Skipped {skipped} | "
                f"Rejected {len(rejected)}"
            )

    # --------------------------------------------------
    # DATABASE SUMMARY
    # --------------------------------------------------

    with engine.connect() as conn:

        total = conn.execute(
            text("SELECT COUNT(*) FROM stock_prices")
        ).scalar_one()

        date_range = conn.execute(
            text("""
                SELECT MIN(trade_date), MAX(trade_date),
                       COUNT(DISTINCT trade_date),
                       COUNT(DISTINCT company_id)
                FROM stock_prices
            """)
        ).fetchone()

    # --------------------------------------------------
    # FINAL REPORT
    # --------------------------------------------------

    print("\n" + "=" * 65)
    print("IMPORT SUMMARY")
    print("=" * 65)

    print("Import mode:", import_mode)
    print("Archives discovered:", len(archives))
    print("New price records:", imported)
    print("Already matching records:", unchanged)
    print("Skipped archives:", skipped)
    print("Rejected archives:", len(rejected))

    print("Total database price records:", total)
    print("First date:", date_range[0])
    print("Last date:", date_range[1])
    print("Trading dates:", date_range[2])
    print("Companies represented:", date_range[3])

    if rejected:

        print(
            "\nREJECTED ARCHIVES - "
            "INVESTIGATION REQUIRED"
        )

        for name, reason in rejected:
            print(f"{name}: {reason}")

        raise RuntimeError(
            f"{len(rejected)} archive(s) were rejected."
        )


if __name__ == "__main__":
    main()
