
from pathlib import Path
from decimal import Decimal, InvalidOperation

import pandas as pd
from sqlalchemy import text

from database import engine


ROOT = Path(__file__).resolve().parent.parent

DATA_FILE = (
    ROOT
    / "database"
    / "processed"
    / "constituents"
    / "nifty50_constituent_snapshots.csv"
)


EXPECTED_RECORDS = 950
EXPECTED_MONTHS = 19
RECORDS_PER_MONTH = 50


NUMERIC_COLUMNS = {
    "equity_capital": "Equity Capital (In Rs.)",
    "index_market_cap": "Index Market Capitalisation (Rs. Crores)",
    "weightage": "Weightage (%)",
    "beta": "Beta",
    "r2": "R2",
    "volatility": "Volatility (%)",
    "monthly_return": "Monthly Return",
    "avg_impact_cost": "Avg. Impact Cost (%)",
}


INSERT_SQL = text("""
    INSERT INTO index_constituent_snapshots (
        index_symbol,
        report_month,
        symbol,
        security_name,
        industry,
        equity_capital,
        index_market_cap,
        weightage,
        beta,
        r2,
        volatility,
        monthly_return,
        avg_impact_cost,
        source_archive,
        source_csv
    )
    VALUES (
        :index_symbol,
        :report_month,
        :symbol,
        :security_name,
        :industry,
        :equity_capital,
        :index_market_cap,
        :weightage,
        :beta,
        :r2,
        :volatility,
        :monthly_return,
        :avg_impact_cost,
        :source_archive,
        :source_csv
    )
""")


def clean_text(value):
    """Convert missing Pandas values into Python None."""
    if value is None or pd.isna(value):
        return None

    value = str(value).strip()

    return value if value else None


def first_nonempty(record, columns):
    """Return the first available non-empty value."""
    for column in columns:
        value = clean_text(record.get(column))

        if value is not None:
            return value

    return None


def decimal_or_none(value):
    """Convert valid numeric values into Decimal; missing values to None."""
    if value is None or pd.isna(value):
        return None

    value = str(value).strip()

    if value.upper() in ("", "-", "NA", "N/A", "NAN", "NONE"):
        return None

    try:
        result = Decimal(value)

        if not result.is_finite():
            raise ValueError(f"Non-finite numeric value: {value}")

        return result

    except InvalidOperation as error:
        raise ValueError(
            f"Invalid numeric value: {value}"
        ) from error


def prepare_records():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Constituent CSV not found: {DATA_FILE}"
        )

    df = pd.read_csv(DATA_FILE, dtype=str)

    if len(df) != EXPECTED_RECORDS:
        raise ValueError(
            f"Expected {EXPECTED_RECORDS} records, found {len(df)}"
        )

    required_columns = [
        "report_month",
        "Security Symbol",
        "Security Name",
        "source_archive",
        "source_csv",
        "Weightage (%)",
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing CSV columns: {missing}"
        )

    if not (
        "Basic Industry" in df.columns
        or "Industry" in df.columns
    ):
        raise ValueError(
            "Neither 'Basic Industry' nor 'Industry' column exists."
        )

    # Clean and validate symbols.
    df["Security Symbol"] = (
        df["Security Symbol"]
        .fillna("")
        .str.strip()
        .str.upper()
    )

    if (df["Security Symbol"] == "").any():
        raise ValueError("Blank symbols detected.")

    if df["Security Symbol"].str.startswith("DUMMY").any():
        raise ValueError(
            "DUMMY symbols detected in the real-company CSV."
        )

    # Validate security names.
    df["Security Name"] = (
        df["Security Name"].fillna("").str.strip()
    )

    if (df["Security Name"] == "").any():
        raise ValueError("Blank security names detected.")

    # Convert report months into MySQL DATE format.
    df["report_month"] = pd.to_datetime(
        df["report_month"],
        format="%Y-%m",
        errors="raise",
    ).dt.strftime("%Y-%m-01")

    # Check duplicate month-symbol combinations.
    if df.duplicated(
        ["report_month", "Security Symbol"]
    ).any():
        raise ValueError(
            "Duplicate month-symbol records detected."
        )

    # Exactly 50 real constituents per month.
    monthly_counts = df.groupby("report_month").size()

    if len(monthly_counts) != EXPECTED_MONTHS:
        raise ValueError(
            f"Expected {EXPECTED_MONTHS} months, "
            f"found {len(monthly_counts)}"
        )

    if monthly_counts.ne(RECORDS_PER_MONTH).any():
        raise ValueError(
            "Every monthly snapshot must contain exactly 50 rows."
        )

    # Convert CSV rows into SQL-ready dictionaries.
    rows = []

    for record in df.to_dict("records"):
        industry = first_nonempty(
            record,
            ["Basic Industry", "Industry"],
        )

        row = {
            "index_symbol": "NIFTY 50",
            "report_month": record["report_month"],
            "symbol": clean_text(
                record["Security Symbol"]
            ),
            "security_name": clean_text(
                record["Security Name"]
            ),
            "industry": industry,
            "source_archive": clean_text(
                record["source_archive"]
            ),
            "source_csv": clean_text(
                record["source_csv"]
            ),
        }

        for db_column, csv_column in NUMERIC_COLUMNS.items():
            row[db_column] = decimal_or_none(
                record.get(csv_column)
            )

        # Mandatory fields must never be NULL.
        mandatory_fields = [
            "symbol",
            "security_name",
            "source_archive",
            "source_csv",
        ]

        for field in mandatory_fields:
            if row[field] is None:
                raise ValueError(
                    f"Missing mandatory field '{field}' "
                    f"for report month {row['report_month']}."
                )

        # Weightage is required for every constituent.
        if row["weightage"] is None:
            raise ValueError(
                f"Missing weightage for {row['symbol']} "
                f"in {row['report_month']}."
            )

        rows.append(row)

    return rows, monthly_counts


def main():
    rows, monthly_counts = prepare_records()

    print("=" * 65)
    print("GREEDY STOCKS — NIFTY 50 MYSQL IMPORT")
    print("=" * 65)

    print(f"Prepared records: {len(rows)}")
    print(f"Monthly snapshots: {len(monthly_counts)}")
    print("Index scope: NIFTY 50 only")
    print("DUMMY records: excluded")
    print("Starting database preflight...")

    # All inserts and verification run in one transaction.
    # Any failure automatically rolls back the transaction.
    with engine.begin() as connection:

        existing_count = connection.execute(
            text("""
                SELECT COUNT(*)
                FROM index_constituent_snapshots
                WHERE index_symbol = 'NIFTY 50'
            """)
        ).scalar_one()

        if existing_count > 0:
            raise RuntimeError(
                f"Import stopped: {existing_count} NIFTY 50 "
                "snapshot records already exist. "
                "No records were inserted."
            )

        print(
            "Preflight passed: target table has no NIFTY 50 records."
        )

        print("Inserting records...")

        connection.execute(INSERT_SQL, rows)

        final_count = connection.execute(
            text("""
                SELECT COUNT(*)
                FROM index_constituent_snapshots
                WHERE index_symbol = 'NIFTY 50'
            """)
        ).scalar_one()

        if final_count != EXPECTED_RECORDS:
            raise RuntimeError(
                f"Expected {EXPECTED_RECORDS} records after import, "
                f"found {final_count}. Transaction will be rolled back."
            )

        database_month_counts = connection.execute(
            text("""
                SELECT report_month, COUNT(*) AS record_count
                FROM index_constituent_snapshots
                WHERE index_symbol = 'NIFTY 50'
                GROUP BY report_month
                ORDER BY report_month
            """)
        ).all()

        if len(database_month_counts) != EXPECTED_MONTHS:
            raise RuntimeError(
                "Incorrect number of monthly snapshots. "
                "Transaction will be rolled back."
            )

        if any(
            count != RECORDS_PER_MONTH
            for _, count in database_month_counts
        ):
            raise RuntimeError(
                "Monthly database verification failed. "
                "Transaction will be rolled back."
            )

    # Reaching this point means the transaction committed.
    print("\n" + "=" * 65)
    print("IMPORT COMMITTED SUCCESSFULLY")
    print("=" * 65)

    print(f"Database records: {final_count}")
    print(f"Monthly snapshots: {len(database_month_counts)}")

    for month, count in database_month_counts:
        print(f"{month} | {count} records")

    print(
        "\nOriginal ZIP archives and source CSV files remain unchanged."
    )


if __name__ == "__main__":
    main()
