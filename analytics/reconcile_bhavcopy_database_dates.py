"""Compare NSE Bhavcopy archive dates against MySQL stock-price dates."""

from pathlib import Path
from zipfile import ZipFile

import pandas as pd
from sqlalchemy import text

from backend.database import engine


ROOT = Path(__file__).resolve().parents[1]
BHAVCOPY_DIR = ROOT / "database" / "raw" / "bhavcopy"


def main():
    print("=" * 75)
    print("NSE BHAVCOPY vs MYSQL — DATE RECONCILIATION")
    print("=" * 75)

    archives = sorted(BHAVCOPY_DIR.glob("*.zip"))

    if not archives:
        raise FileNotFoundError(
            f"No Bhavcopy ZIP archives found: {BHAVCOPY_DIR}"
        )

    archive_dates = set()
    errors = []
    inspected_archives = 0

    print(f"Archives discovered: {len(archives)}")
    print("Reading original NSE archive dates...\n")

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
                        usecols=["TradDt"],
                        dtype=str,
                    )

            dates = pd.to_datetime(
                frame["TradDt"],
                errors="coerce",
            ).dropna()

            archive_dates.update(
                dates.dt.normalize().tolist()
            )

            inspected_archives += 1

        except Exception as error:
            errors.append(
                f"{archive_path.name}: "
                f"{type(error).__name__}: {error}"
            )

    print("Reading distinct MySQL stock-price dates...")

    with engine.connect() as conn:
        database_rows = conn.execute(text("""
            SELECT DISTINCT trade_date
            FROM stock_prices
            ORDER BY trade_date
        """)).fetchall()

    database_dates = set(
        pd.to_datetime(
            [row[0] for row in database_rows]
        ).normalize().tolist()
    )

    missing_in_database = sorted(
        archive_dates - database_dates
    )

    extra_in_database = sorted(
        database_dates - archive_dates
    )

    print("\n" + "=" * 75)
    print("RECONCILIATION RESULTS")
    print("=" * 75)

    print("Archives discovered:", len(archives))
    print("Archives successfully inspected:", inspected_archives)
    print("Unique NSE archive dates:", len(archive_dates))
    print("Unique MySQL dates:", len(database_dates))
    print("Dates present in NSE archives but missing in MySQL:",
          len(missing_in_database))
    print("Dates present in MySQL but absent from NSE archives:",
          len(extra_in_database))
    print("Archive errors:", len(errors))

    if missing_in_database:
        print("\nMISSING FROM MYSQL:")
        for date in missing_in_database:
            print(date.strftime("%Y-%m-%d"))

    if extra_in_database:
        print("\nEXTRA IN MYSQL:")
        for date in extra_in_database:
            print(date.strftime("%Y-%m-%d"))

    if errors:
        print("\nARCHIVE ERRORS:")
        for error in errors:
            print(error)

    exact_match = (
        archive_dates == database_dates
        and not errors
        and inspected_archives == len(archives)
    )

    print("\n" + "=" * 75)

    if exact_match:
        print("PASS: ALL ARCHIVE DATES MATCH MYSQL EXACTLY.")
    else:
        print("FAIL: DATE RECONCILIATION NEEDS INVESTIGATION.")

    print("Database writes: NONE")
    print("Filesystem output files: NONE")

    if not exact_match:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
