
import argparse
import logging
import re
import subprocess
import sys

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from nse_trading_calendar import get_session_status


ROOT = Path(__file__).resolve().parent.parent

DOWNLOADER = ROOT / "backend" / "download_nse_cm_bhavcopy.py"
IMPORTER = ROOT / "backend" / "import_nifty50_historical_prices.py"

ARCHIVE_DIR = ROOT / "database" / "raw" / "bhavcopy"
LOG_DIR = ROOT / "backend" / "logs"


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                LOG_DIR / "nse_daily_pipeline.log",
                encoding="utf-8",
            ),
        ],
    )


def validate_date(value):
    if not re.fullmatch(r"\d{8}", value):
        raise ValueError("Date must use YYYYMMDD format.")

    datetime.strptime(value, "%Y%m%d")
    return value


def check_trading_session(target_date):

    parsed_date = datetime.strptime(
        target_date,
        "%Y%m%d",
    ).date()

    result = get_session_status(parsed_date)

    logging.info(
        "NSE calendar status: %s",
        result["status"],
    )

    logging.info(
        "Calendar reason: %s",
        result["reason"],
    )

    if result["status"] in (
        "WEEKEND_CLOSED",
        "NSE_HOLIDAY",
    ):
        logging.info(
            "No regular trading session. Pipeline skipped."
        )
        return False

    if result["status"] == "SPECIAL_SESSION_REQUIRES_CONFIRMATION":
        raise RuntimeError(
            "Special trading session requires manual confirmation. "
            "Automatic pipeline execution is blocked."
        )

    if result["status"] == "CALENDAR_NOT_CONFIGURED":
        raise RuntimeError(
            "NSE calendar is not configured for this year. "
            "Automatic pipeline execution is blocked."
        )

    if result["status"] != "REGULAR_SESSION":
        raise RuntimeError(
            f"Unexpected NSE calendar status: {result['status']}"
        )

    return True


def run_pipeline(target_date):

    # --------------------------------------------------
    # STEP 0: CHECK NSE TRADING CALENDAR
    # --------------------------------------------------

    logging.info("=" * 65)
    logging.info("GREEDY STOCKS - DAILY NSE PIPELINE")
    logging.info("Trading date: %s", target_date)
    logging.info("=" * 65)

    if not check_trading_session(target_date):
        return

    filename = (
        f"BhavCopy_NSE_CM_0_0_0_{target_date}_F_0000.csv.zip"
    )

    archive = ARCHIVE_DIR / filename

    # --------------------------------------------------
    # STEP 1: DOWNLOAD AND VALIDATE
    # --------------------------------------------------

    logging.info("STEP 1: Starting NSE downloader.")

    subprocess.run(
        [
            sys.executable,
            str(DOWNLOADER),
            "--date",
            target_date,
        ],
        cwd=ROOT,
        check=True,
    )

    logging.info("Downloader completed successfully.")

    # --------------------------------------------------
    # STEP 2: VERIFY ARCHIVE EXISTS
    # --------------------------------------------------

    if not archive.exists():
        raise FileNotFoundError(
            f"Expected archive not found: {archive}"
        )

    logging.info(
        "STEP 2: Archive found: %s",
        archive.name,
    )

    # --------------------------------------------------
    # STEP 3: IMPORT ONLY THIS ARCHIVE
    # --------------------------------------------------

    logging.info("STEP 3: Starting single-archive import.")

    subprocess.run(
        [
            sys.executable,
            str(IMPORTER),
            "--archive",
            str(archive),
        ],
        cwd=ROOT,
        check=True,
    )

    logging.info("Importer completed successfully.")

    # --------------------------------------------------
    # SUCCESS
    # --------------------------------------------------

    logging.info("=" * 65)
    logging.info("DAILY NSE PIPELINE COMPLETED SUCCESSFULLY")
    logging.info("Trading date: %s", target_date)
    logging.info("Archive preserved: %s", archive)
    logging.info("=" * 65)


def main():

    parser = argparse.ArgumentParser(
        description="GREEDY STOCKS Daily NSE Pipeline"
    )

    parser.add_argument(
        "--date",
        help=(
            "Trading date in YYYYMMDD format. "
            "Defaults to India today."
        ),
    )

    args = parser.parse_args()

    target_date = args.date or datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).strftime("%Y%m%d")

    try:
        validate_date(target_date)

    except ValueError as exc:
        parser.error(str(exc))

    setup_logging()

    try:
        run_pipeline(target_date)

    except subprocess.CalledProcessError as exc:
        logging.exception(
            "Pipeline stopped because a subprocess failed. "
            "Exit code: %s",
            exc.returncode,
        )
        sys.exit(exc.returncode or 1)

    except Exception:
        logging.exception(
            "Daily NSE pipeline failed."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
