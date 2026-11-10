
"""GREEDY STOCKS — NIFTY 50 benchmark date coverage audit.

Read-only comparison of NSE index dates and original Bhavcopy ZIP dates.

This is a source-date comparison, NOT an official NSE trading-calendar audit.
No database records are modified.
"""

import csv
import sys
from datetime import date, datetime
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from database import engine


INDEX_CSV = (
    ROOT / "database" / "raw" / "index"
    / "nifty50_historical_pr_combined.csv"
)

BHAVCOPY_DIR = ROOT / "database" / "raw" / "bhavcopy"

OUTPUT_DIR = (
    ROOT / "database" / "processed" / "index"
)

OUTPUT_FILE = OUTPUT_DIR / "benchmark_date_coverage_audit.csv"


def load_index_source_dates():
    """Read unique dates from the original NIFTY 50 PR CSV."""

    dates = set()

    with INDEX_CSV.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            trade_date = datetime.strptime(
                row["Date"].strip(), "%d %b %Y"
            ).date()

            if trade_date in dates:
                raise ValueError(
                    f"Duplicate benchmark source date: {trade_date}"
                )

            dates.add(trade_date)

    return dates


def load_database_index_dates():
    """Read NIFTY 50 benchmark dates from MySQL."""

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT trade_date
                FROM index_prices
                WHERE index_symbol = 'NIFTY 50'
                ORDER BY trade_date
            """)
        ).scalars().all()

    return {
        pd.Timestamp(value).date()
        for value in rows
    }


def load_bhavcopy_archive_dates():
    """Read trading dates from original NSE Bhavcopy ZIP archives."""

    archives = sorted(BHAVCOPY_DIR.glob("*.zip"))

    if not archives:
        raise FileNotFoundError(
            f"No Bhavcopy ZIP archives found: {BHAVCOPY_DIR}"
        )

    archive_dates = set()
    errors = []
    inspected_archives = 0

    for archive_path in archives:
        try:
            with ZipFile(archive_path) as archive:

                csv_files = [
                    name
                    for name in archive.namelist()
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
                value.date()
                for value in dates.dt.normalize()
            )

            inspected_archives += 1

        except Exception as error:
            errors.append(
                f"{archive_path.name}: "
                f"{type(error).__name__}: {error}"
            )

    return (
        archives,
        archive_dates,
        inspected_archives,
        errors,
    )


def main():
    print("\nGREEDY STOCKS — BENCHMARK DATE COVERAGE AUDIT")
    print("=" * 65)

    # 1. Load all three date sets.
    source_dates = load_index_source_dates()
    database_dates = load_database_index_dates()

    (
        archives,
        bhavcopy_dates,
        inspected_archives,
        errors,
    ) = load_bhavcopy_archive_dates()

    # 2. Verify benchmark source and database consistency.
    if source_dates != database_dates:
        missing = sorted(source_dates - database_dates)
        extra = sorted(database_dates - source_dates)

        raise ValueError(
            "Benchmark source/database date mismatch. "
            f"Missing: {missing}; Extra: {extra}"
        )

    # 3. Compare benchmark and Bhavcopy date sets.
    common = source_dates & bhavcopy_dates
    index_only = source_dates - bhavcopy_dates
    bhavcopy_only = bhavcopy_dates - source_dates

    weekend_index_only = sorted(
        trade_date
        for trade_date in index_only
        if trade_date.weekday() >= 5
    )

    special_date = date(2026, 2, 1)

    # 4. Export the complete date comparison report.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=[
                "trade_date",
                "weekday",
                "category",
                "weekend",
                "special_session_review",
            ],
        )

        writer.writeheader()

        for trade_date in sorted(
            source_dates | bhavcopy_dates
        ):

            if (
                trade_date in source_dates
                and trade_date in bhavcopy_dates
            ):
                category = "COMMON_DATE"

            elif trade_date in source_dates:
                category = "INDEX_ONLY"

            else:
                category = "BHAVCOPY_ONLY"

            writer.writerow({
                "trade_date": trade_date.isoformat(),
                "weekday": trade_date.strftime("%A"),
                "category": category,
                "weekend": trade_date.weekday() >= 5,
                "special_session_review": (
                    "REVIEW_2026_02_01"
                    if trade_date == special_date
                    else ""
                ),
            })

    # 5. Print audit results.
    print("\nSOURCE COVERAGE")
    print("-" * 65)

    print("Benchmark source dates:", len(source_dates))
    print("Benchmark database dates:", len(database_dates))
    print("Bhavcopy ZIP archives:", len(archives))
    print("Successfully inspected archives:", inspected_archives)
    print("Unique Bhavcopy archive dates:", len(bhavcopy_dates))

    print("\nDATE COMPARISON")
    print("-" * 65)

    print("Common dates:", len(common))
    print("Benchmark-only dates:", len(index_only))
    print("Bhavcopy-only dates:", len(bhavcopy_only))
    print("Weekend benchmark-only dates:", len(weekend_index_only))
    print("Archive errors:", len(errors))

    print("\nBENCHMARK-ONLY DATES")

    for trade_date in sorted(index_only):
        print(
            trade_date,
            trade_date.strftime("%A"),
            "WEEKEND" if trade_date.weekday() >= 5 else "",
        )

    print("\nBHAVCOPY-ONLY DATES")

    for trade_date in sorted(bhavcopy_only):
        print(
            trade_date,
            trade_date.strftime("%A"),
        )

    # 6. Explicitly identify the special Sunday session.
    print("\nSPECIAL SESSION CHECK")
    print("-" * 65)

    print("Date:", special_date)
    print("Weekday:", special_date.strftime("%A"))
    print("In benchmark:", special_date in source_dates)
    print("In Bhavcopy:", special_date in bhavcopy_dates)

    # 7. Report archive errors.
    if errors:
        print("\nARCHIVE ERRORS")

        for error in errors:
            print(error)

    print("\nOUTPUT")
    print("-" * 65)

    print("Report:", OUTPUT_FILE)
    print("Database writes: NONE")

    print("\nIMPORTANT")
    print("-" * 65)

    print(
        "Bhavcopy date coverage is not an official exchange calendar."
    )

    print(
        "Index-only dates are not automatically invalid sessions."
    )

    # 8. Final structural audit status.
    audit_passed = (
        len(archives) == inspected_archives
        and not errors
        and len(source_dates) == 396
        and len(database_dates) == 396
        and len(bhavcopy_dates) == 369
        and source_dates == database_dates
    )

    print("\n" + "=" * 65)

    if audit_passed:
        print("PASS: SOURCE DATE COVERAGE AUDIT COMPLETED.")
    else:
        print("WARNING: INVESTIGATION REQUIRED.")

    print("Database writes: NONE")


if __name__ == "__main__":
    main()
