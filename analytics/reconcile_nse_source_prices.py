"""Read-only NSE EQ source-to-MySQL price reconciliation."""

from pathlib import Path
from zipfile import ZipFile
from decimal import Decimal, InvalidOperation

import pandas as pd
from sqlalchemy import text, bindparam

from analytics.database_adapter import get_latest_constituents
from backend.database import engine


ROOT = Path(__file__).resolve().parents[1]
BHAVCOPY_DIR = ROOT / "database" / "raw" / "bhavcopy"

REQUIRED = {
    "TradDt", "TckrSymb", "SctySrs",
    "OpnPric", "HghPric", "LwPric", "ClsPric",
    "PrvsClsgPric", "TtlTradgVol", "TtlTrfVal",
    "TtlNbOfTxsExctd",
}

DECIMAL_FIELDS = [
    "open_price", "high_price", "low_price",
    "close_price", "previous_close", "total_traded_value",
]

INTEGER_FIELDS = [
    "total_traded_volume", "total_trades",
]

SOURCE_FIELDS = {
    "OpnPric": "open_price",
    "HghPric": "high_price",
    "LwPric": "low_price",
    "ClsPric": "close_price",
    "PrvsClsgPric": "previous_close",
    "TtlTradgVol": "total_traded_volume",
    "TtlTrfVal": "total_traded_value",
    "TtlNbOfTxsExctd": "total_trades",
}


def decimal_value(value):
    return Decimal(str(value)).quantize(Decimal("0.0001"))


def normalize_source_row(row, company_id):
    result = {
        "company_id": int(company_id),
        "trade_date": pd.Timestamp(row["TradDt"]).date(),
    }

    for source_field, db_field in SOURCE_FIELDS.items():
        value = row[source_field]

        if pd.isna(value):
            raise ValueError(f"Missing {source_field}")

        if db_field in DECIMAL_FIELDS:
            result[db_field] = decimal_value(value)
        else:
            numeric = Decimal(str(value))
            if numeric != numeric.to_integral_value():
                raise ValueError(f"Non-integer {source_field}: {value}")
            result[db_field] = int(numeric)

    return result


def values_match(source, database):
    for field in DECIMAL_FIELDS:
        if database[field] is None:
            return False, field

        if Decimal(str(database[field])).quantize(
            Decimal("0.0001")
        ) != source[field]:
            return False, field

    for field in INTEGER_FIELDS:
        if database[field] is None:
            return False, field

        if int(database[field]) != source[field]:
            return False, field

    return True, None


def main():
    print("=" * 80)
    print("NSE EQ SOURCE-TO-MYSQL PRICE RECONCILIATION")
    print("=" * 80)

    constituents = get_latest_constituents()

    if len(constituents) != 50:
        raise ValueError(
            f"Expected 50 latest constituents; found {len(constituents)}"
        )

    selected = constituents[
        ["company_id", "symbol", "company_name"]
    ].copy()

    selected_ids = selected["company_id"].astype(int).tolist()

    # Build direct symbol mapping and dated historical ticker aliases.
    with engine.connect() as conn:
        aliases = conn.execute(
            text("""
                SELECT
                    ci.company_id,
                    ci.identifier_value,
                    ci.valid_from,
                    ci.valid_to,
                    ci.identifier_type
                FROM company_identifiers ci
                WHERE ci.identifier_type = 'TICKER'
                  AND ci.company_id IN :company_ids
            """).bindparams(bindparam("company_ids", expanding=True)),
            {"company_ids": selected_ids},
        ).mappings().all()

    direct_map = {
        row["symbol"]: int(row["company_id"])
        for row in selected.to_dict("records")
    }

    alias_map = {}
    for alias in aliases:
        alias_map[alias["identifier_value"].strip().upper()] = {
            "company_id": int(alias["company_id"]),
            "valid_from": pd.Timestamp(alias["valid_from"]).date(),
            "valid_to": (
                pd.Timestamp(alias["valid_to"]).date()
                if alias["valid_to"] else None
            ),
        }

    archives = sorted(BHAVCOPY_DIR.glob("*.zip"))
    if not archives:
        raise FileNotFoundError(f"No archives found: {BHAVCOPY_DIR}")

    source_records = {}
    source_duplicates = []
    archive_errors = []
    inspected = 0
    matched_rows = 0
    ignored_rows = 0

    print("Latest snapshot companies:", len(selected))
    print("Direct symbols:", len(direct_map))
    print("Historical ticker aliases:", len(alias_map))
    print("Archives discovered:", len(archives))
    print("\nReading original NSE EQ rows...")

    for archive_path in archives:
        try:
            with ZipFile(archive_path) as archive:
                csv_files = [
                    name for name in archive.namelist()
                    if name.lower().endswith(".csv")
                ]

                if len(csv_files) != 1:
                    raise ValueError(
                        f"Expected one CSV, found {len(csv_files)}"
                    )

                with archive.open(csv_files[0]) as file:
                    frame = pd.read_csv(
                        file,
                        usecols=list(REQUIRED),
                        dtype=str,
                    )

            inspected += 1

            frame["TckrSymb"] = (
                frame["TckrSymb"].fillna("").str.strip().str.upper()
            )
            frame["SctySrs"] = (
                frame["SctySrs"].fillna("").str.strip().str.upper()
            )
            frame["TradDt"] = pd.to_datetime(
                frame["TradDt"], errors="coerce"
            ).dt.date

            frame = frame[frame["SctySrs"] == "EQ"]

            for row in frame.to_dict("records"):
                symbol = row["TckrSymb"]
                trade_date = row["TradDt"]

                if pd.isna(trade_date):
                    if symbol in direct_map or symbol in alias_map:
                        raise ValueError(
                            f"Invalid date for mapped symbol {symbol}"
                        )
                    ignored_rows += 1
                    continue

                company_id = direct_map.get(symbol)

                # Apply historical ticker alias only within its recorded
                # observation boundaries.
                if company_id is None and symbol in alias_map:
                    alias = alias_map[symbol]

                    if trade_date < alias["valid_from"]:
                        ignored_rows += 1
                        continue

                    if (
                        alias["valid_to"] is not None
                        and trade_date > alias["valid_to"]
                    ):
                        ignored_rows += 1
                        continue

                    company_id = alias["company_id"]

                if company_id is None:
                    ignored_rows += 1
                    continue

                normalized = normalize_source_row(row, company_id)
                key = (company_id, normalized["trade_date"])

                if key in source_records:
                    source_duplicates.append({
                        "symbol": symbol,
                        "company_id": company_id,
                        "trade_date": str(normalized["trade_date"]),
                    })
                    continue

                source_records[key] = normalized
                matched_rows += 1

        except Exception as error:
            archive_errors.append(
                f"{archive_path.name}: {type(error).__name__}: {error}"
            )

    # Read database rows for exactly the latest 50 companies.
    query = text("""
        SELECT
            company_id,
            trade_date,
            open_price,
            high_price,
            low_price,
            close_price,
            previous_close,
            total_traded_volume,
            total_traded_value,
            total_trades
        FROM stock_prices
        WHERE company_id IN :company_ids
    """).bindparams(bindparam("company_ids", expanding=True))

    with engine.connect() as conn:
        database_rows = conn.execute(
            query,
            {"company_ids": selected_ids},
        ).mappings().all()

    database_records = {
        (int(row["company_id"]), row["trade_date"]): dict(row)
        for row in database_rows
    }

    missing_keys = sorted(
        set(source_records) - set(database_records)
    )
    extra_keys = sorted(
        set(database_records) - set(source_records)
    )

    mismatches = []

    for key in sorted(set(source_records) & set(database_records)):
        matches, field = values_match(
            source_records[key],
            database_records[key],
        )

        if not matches:
            mismatches.append({
                "company_id": key[0],
                "trade_date": str(key[1]),
                "field": field,
                "source_value": str(source_records[key][field]),
                "database_value": str(database_records[key][field]),
            })

    company_names = {
        int(row["company_id"]): row["symbol"]
        for row in selected.to_dict("records")
    }

    print("\n" + "=" * 80)
    print("RECONCILIATION SUMMARY")
    print("=" * 80)
    print("Archives discovered:", len(archives))
    print("Archives successfully inspected:", inspected)
    print("Source EQ records matched to latest 50:", matched_rows)
    print("Database records for latest 50:", len(database_records))
    print("Source rows ignored (outside selected universe/alias dates):",
          ignored_rows)
    print("Source duplicate company/date keys:", len(source_duplicates))
    print("Source records missing from MySQL:", len(missing_keys))
    print("Unexpected MySQL records:", len(extra_keys))
    print("Field-level mismatched records:", len(mismatches))
    print("Archive/source errors:", len(archive_errors))

    if missing_keys:
        print("\nMISSING DATABASE RECORDS — FIRST 20")
        for company_id, trade_date in missing_keys[:20]:
            print(company_names.get(company_id, company_id), trade_date)

    if extra_keys:
        print("\nUNEXPECTED DATABASE RECORDS — FIRST 20")
        for company_id, trade_date in extra_keys[:20]:
            print(company_names.get(company_id, company_id), trade_date)

    if mismatches:
        print("\nFIELD-LEVEL MISMATCHES — FIRST 30")
        for item in mismatches[:30]:
            print(
                f"{company_names.get(item['company_id'], item['company_id'])} "
                f"{item['trade_date']} | {item['field']} | "
                f"source={item['source_value']} | "
                f"database={item['database_value']}"
            )

    if source_duplicates:
        print("\nSOURCE DUPLICATES — FIRST 20")
        for item in source_duplicates[:20]:
            print(item)

    if archive_errors:
        print("\nARCHIVE ERRORS — FIRST 20")
        for error in archive_errors[:20]:
            print(error)

    passed = (
        inspected == len(archives)
        and not archive_errors
        and not source_duplicates
        and not missing_keys
        and not extra_keys
        and not mismatches
    )

    print("\n" + "=" * 80)
    if passed:
        print("PASS: SOURCE PRICE VALUES MATCH MYSQL EXACTLY.")
    else:
        print("FAIL: SOURCE-TO-DATABASE RECONCILIATION NEEDS INVESTIGATION.")

    print("Database writes: NONE")
    print("Source files modified: NONE")

    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
