
import argparse
import logging
import re
import subprocess
import sys

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT / "backend"))

from database import engine
from nse_trading_calendar import get_session_status


PIPELINE = ROOT / "backend" / "run_daily_nse_pipeline.py"
LOG_DIR = ROOT / "backend" / "logs"

IST = ZoneInfo("Asia/Kolkata")
PUBLICATION_TIME = time(18, 30)


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                LOG_DIR / "nse_catch_up.log",
                encoding="utf-8",
            ),
        ],
    )


def validate_date(value):
    if not re.fullmatch(r"\d{8}", value):
        raise ValueError("Date must use YYYYMMDD format.")

    return datetime.strptime(value, "%Y%m%d").date()


def get_latest_database_date():
    with engine.connect() as conn:
        latest = conn.execute(
            text("""
                SELECT MAX(trade_date)
                FROM stock_prices
            """)
        ).scalar_one()

    if latest is None:
        raise RuntimeError(
            "stock_prices contains no records. "
            "Run the initial historical import first."
        )

    if isinstance(latest, datetime):
        return latest.date()

    if isinstance(latest, date):
        return latest

    return date.fromisoformat(str(latest))


def get_target_date(now=None):
    """
    Before 18:30 IST, target the previous calendar date.
    At or after 18:30 IST, include today's date.
    The trading calendar filters weekends and holidays.
    """

    if now is None:
        now = datetime.now(IST)

    if now.tzinfo is None:
        raise ValueError("Current time must be timezone-aware.")

    local_now = now.astimezone(IST)

    if local_now.time() >= PUBLICATION_TIME:
        return local_now.date()

    return local_now.date() - timedelta(days=1)


def verify_import(trade_date):
    with engine.connect() as conn:
        count = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM stock_prices
                WHERE trade_date = :trade_date
            """),
            {"trade_date": trade_date},
        ).scalar_one()

    if count == 0:
        raise RuntimeError(
            f"Importer completed but no stock_prices records "
            f"were found for {trade_date}."
        )

    return count


def process_missing_dates(latest_date, target_date, dry_run=False):

    if target_date <= latest_date:
        logging.info(
            "Database is already up to date. "
            "Latest database date: %s | Target date: %s",
            latest_date,
            target_date,
        )
        return

    logging.info("Latest database date: %s", latest_date)
    logging.info("Catch-up target date: %s", target_date)

    processed = 0
    skipped = 0
    manual_review = 0

    current_date = latest_date + timedelta(days=1)

    while current_date <= target_date:

        result = get_session_status(current_date)

        status = result["status"]

        logging.info(
            "Checking %s | %s | %s",
            current_date,
            status,
            result["reason"],
        )

        # Ordinary weekends and holidays
        if status in ("WEEKEND_CLOSED", "NSE_HOLIDAY"):
            skipped += 1
            current_date += timedelta(days=1)
            continue

        # Never guess special-session behaviour
        if status == "SPECIAL_SESSION_REQUIRES_CONFIRMATION":
            logging.warning(
                "SPECIAL SESSION SKIPPED: %s | %s. "
                "Manual review required. Continuing catch-up.",
                current_date,
                result["reason"],
            )
            manual_review += 1
            current_date += timedelta(days=1)
            continue

        # Never guess dates in an unconfigured calendar year
        if status == "CALENDAR_NOT_CONFIGURED":
            raise RuntimeError(
                f"NSE calendar is not configured for "
                f"{current_date.year}. Catch-up stopped safely."
            )

        if status != "REGULAR_SESSION":
            raise RuntimeError(
                f"Unknown calendar status: {status}"
            )

        logging.info(
            "Eligible trading date found: %s",
            current_date,
        )

        if dry_run:
            logging.info(
                "[DRY RUN] Would download, validate and import %s",
                current_date,
            )
            current_date += timedelta(days=1)
            continue

        # Run the existing download + import pipeline
        subprocess.run(
            [
                sys.executable,
                str(PIPELINE),
                "--date",
                current_date.strftime("%Y%m%d"),
            ],
            cwd=ROOT,
            check=True,
        )

        # Confirm that database records were actually imported
        imported_count = verify_import(current_date)

        logging.info(
            "Verified %s database records for %s",
            imported_count,
            current_date,
        )

        processed += 1

        current_date += timedelta(days=1)

    logging.info("=" * 65)
    logging.info("NSE CATCH-UP SUMMARY")
    logging.info("New trading dates processed: %s", processed)
    logging.info("Weekend/holiday dates skipped: %s", skipped)
    logging.info("Special sessions requiring manual review: %s", manual_review)
    logging.info("Catch-up target: %s", target_date)
    logging.info("=" * 65)


def main():

    parser = argparse.ArgumentParser(
        description="GREEDY STOCKS NSE automatic catch-up manager"
    )

    parser.add_argument(
        "--through-date",
        help=(
            "Optional target date in YYYYMMDD format. "
            "Normally determined automatically using IST."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show missing trading dates without downloading or importing.",
    )

    args = parser.parse_args()

    setup_logging()

    try:

        if args.through_date:
            target_date = validate_date(args.through_date)
        else:
            target_date = get_target_date()

        latest_date = get_latest_database_date()

        logging.info("=" * 65)
        logging.info("GREEDY STOCKS - AUTOMATIC CATCH-UP")
        logging.info("Target date: %s", target_date)
        logging.info("Latest database date: %s", latest_date)
        logging.info("Dry run: %s", args.dry_run)
        logging.info("=" * 65)

        process_missing_dates(
            latest_date,
            target_date,
            dry_run=args.dry_run,
        )

    except subprocess.CalledProcessError as exc:

        logging.exception(
            "Catch-up stopped because the daily pipeline failed. "
            "Exit code: %s",
            exc.returncode,
        )

        sys.exit(exc.returncode or 1)

    except Exception:

        logging.exception(
            "NSE automatic catch-up failed."
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
