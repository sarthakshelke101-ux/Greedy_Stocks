
import argparse
import csv
import io
import logging
import re
import sys
import time
import zipfile

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "database" / "raw" / "bhavcopy"
LOG_DIR = ROOT / "backend" / "logs"

BASE_URL = "https://nsearchives.nseindia.com/content/cm/"

REQUIRED_COLUMNS = {
    "TradDt", "TckrSymb", "SctySrs",
    "ISIN", "OpnPric", "HghPric",
    "LwPric", "ClsPric", "PrvsClsgPric",
    "TtlTradgVol", "TtlTrfVal",
    "TtlNbOfTxsExctd",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/zip,application/octet-stream,*/*",
    "Referer": "https://www.nseindia.com/all-reports",
}


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                LOG_DIR / "nse_cm_downloader.log",
                encoding="utf-8",
            ),
        ],
    )


def validate_archive(path, expected_date):
    if not zipfile.is_zipfile(path):
        raise ValueError(
            "Downloaded file is not a valid ZIP archive."
        )

    with zipfile.ZipFile(path) as archive:

        bad_member = archive.testzip()

        if bad_member:
            raise ValueError(
                f"Corrupt ZIP member: {bad_member}"
            )

        members = [
            name for name in archive.namelist()
            if name.lower().endswith(".csv")
        ]

        if len(members) != 1:
            raise ValueError(
                f"Expected exactly one CSV; found {len(members)}."
            )

        with archive.open(members[0]) as raw:

            reader = csv.DictReader(
                io.TextIOWrapper(
                    raw,
                    encoding="utf-8-sig"
                )
            )

            columns = set(reader.fieldnames or [])
            missing = REQUIRED_COLUMNS - columns

            if missing:
                raise ValueError(
                    f"Missing required columns: {sorted(missing)}"
                )

            rows = 0

            for row in reader:

                trade_date = (
                    row["TradDt"].strip()
                    if row["TradDt"]
                    else ""
                )

                if trade_date != expected_date:
                    raise ValueError(
                        f"Unexpected trading date: {trade_date}"
                    )

                rows += 1

            if rows == 0:
                raise ValueError(
                    "Archive contains no data rows."
                )

    return rows


def download(
    target_date,
    publication_attempts=6,
    retry_delay=300,
):

    ARCHIVE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    filename = (
        f"BhavCopy_NSE_CM_0_0_0_{target_date}_F_0000.csv.zip"
    )

    destination = ARCHIVE_DIR / filename
    temporary = ARCHIVE_DIR / (filename + ".part")

    expected_date = (
        f"{target_date[:4]}-"
        f"{target_date[4:6]}-"
        f"{target_date[6:]}"
    )

    # --------------------------------------------------
    # CHECK EXISTING ARCHIVE
    # --------------------------------------------------

    if destination.exists():

        rows = validate_archive(
            destination,
            expected_date
        )

        logging.info(
            "Archive already exists and is valid. Rows: %s",
            rows,
        )

        return

    url = BASE_URL + filename

    # --------------------------------------------------
    # HTTP NETWORK RETRY CONFIGURATION
    # --------------------------------------------------

    retry_policy = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=2,
        status_forcelist=[
            429,
            500,
            502,
            503,
            504,
        ],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )

    session = requests.Session()

    session.mount(
        "https://",
        HTTPAdapter(
            max_retries=retry_policy
        ),
    )

    session.headers.update(HEADERS)

    # --------------------------------------------------
    # APPLICATION-LEVEL PUBLICATION RETRIES
    # --------------------------------------------------

    try:

        for attempt in range(
            1,
            publication_attempts + 1
        ):

            temporary.unlink(missing_ok=True)

            logging.info(
                "NSE download attempt %s/%s: %s",
                attempt,
                publication_attempts,
                filename,
            )

            try:

                with session.get(
                    url,
                    stream=True,
                    timeout=(20, 90),
                ) as response:

                    # Archive not published yet
                    if response.status_code == 404:

                        if attempt < publication_attempts:

                            logging.warning(
                                "NSE archive not published yet "
                                "(HTTP 404). "
                                "Retrying in %s seconds.",
                                retry_delay,
                            )

                            time.sleep(retry_delay)
                            continue

                        raise RuntimeError(
                            "NSE archive remained unavailable "
                            "after all publication attempts. "
                            "The date may be a market holiday "
                            "or the report may not have been published."
                        )

                    response.raise_for_status()

                    # Download to temporary file
                    with open(
                        temporary,
                        "wb"
                    ) as file:

                        for chunk in response.iter_content(
                            1024 * 64
                        ):

                            if chunk:
                                file.write(chunk)

                # --------------------------------------------------
                # VALIDATE BEFORE PRESERVING FINAL ARCHIVE
                # --------------------------------------------------

                rows = validate_archive(
                    temporary,
                    expected_date
                )

                # Atomic rename after successful validation
                temporary.replace(destination)

                logging.info(
                    "Download and validation successful."
                )

                logging.info(
                    "Saved: %s",
                    destination,
                )

                logging.info(
                    "Validated CSV rows: %s",
                    rows,
                )

                return

            except Exception as exc:

                temporary.unlink(missing_ok=True)

                if isinstance(
                    exc,
                    requests.HTTPError
                ):

                    status = (
                        exc.response.status_code
                        if exc.response is not None
                        else None
                    )

                    # Do not retry permanent HTTP errors
                    if status not in (
                        429,
                        500,
                        502,
                        503,
                        504,
                    ):
                        raise

                if attempt == publication_attempts:
                    raise

                logging.warning(
                    "Download attempt failed: %s. "
                    "Retrying in %s seconds.",
                    exc,
                    retry_delay,
                )

                time.sleep(retry_delay)

    finally:

        temporary.unlink(missing_ok=True)
        session.close()


def main():

    parser = argparse.ArgumentParser(
        description="GREEDY STOCKS NSE CM-UDiFF Downloader"
    )

    # --------------------------------------------------
    # COMMAND-LINE ARGUMENTS
    # --------------------------------------------------

    parser.add_argument(
        "--date",
        help=(
            "Trading date in YYYYMMDD format. "
            "Defaults to India today."
        ),
    )

    parser.add_argument(
        "--publication-attempts",
        type=int,
        default=6,
        help=(
            "Maximum attempts when NSE has not "
            "published the archive. Default: 6."
        ),
    )

    parser.add_argument(
        "--retry-delay",
        type=int,
        default=300,
        help=(
            "Seconds between publication retry attempts. "
            "Default: 300."
        ),
    )

    args = parser.parse_args()

    # --------------------------------------------------
    # VALIDATE ARGUMENTS
    # --------------------------------------------------

    target_date = args.date or datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).strftime("%Y%m%d")

    if not re.fullmatch(
        r"\d{8}",
        target_date
    ):
        parser.error(
            "Date must use YYYYMMDD format."
        )

    try:

        datetime.strptime(
            target_date,
            "%Y%m%d"
        )

    except ValueError:

        parser.error(
            "Invalid calendar date."
        )

    if args.publication_attempts < 1:
        parser.error(
            "--publication-attempts must be at least 1."
        )

    if args.retry_delay < 1:
        parser.error(
            "--retry-delay must be at least 1."
        )

    # --------------------------------------------------
    # START LOGGING
    # --------------------------------------------------

    setup_logging()

    logging.info(
        "Publication retry attempts: %s",
        args.publication_attempts,
    )

    logging.info(
        "Publication retry delay: %s seconds",
        args.retry_delay,
    )

    # --------------------------------------------------
    # RUN DOWNLOADER
    # --------------------------------------------------

    try:

        download(
            target_date,
            publication_attempts=args.publication_attempts,
            retry_delay=args.retry_delay,
        )

    except Exception as exc:

        logging.exception(
            "NSE download failed: %s",
            exc,
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
