import argparse
import json
import subprocess
import sys
import time
import zipfile
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DIR = ROOT / "database" / "raw" / "bhavcopy"
MANIFEST_PATH = ARCHIVE_DIR / "backfill_manifest.json"
IMPORTER = ROOT / "backend" / "import_nifty50_historical_prices.py"

LEGACY_CUTOFF = date(2024, 7, 8)  # UDiFF archive era begins 08-Jul-2024
LEGACY_BASE = "https://archives.nseindia.com/content/historical/EQUITIES/"
UDIFF_BASE = "https://nsearchives.nseindia.com/content/cm/"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/zip,application/octet-stream,*/*",
    "Referer": "https://www.nseindia.com/",
}


def make_session():
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.headers.update(HEADERS)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def archive_details(day):
    if day < LEGACY_CUTOFF:
        month = day.strftime("%b").upper()
        filename = f"cm{day:%d}{month}{day:%Y}bhav.csv.zip"
        url = urljoin(
            LEGACY_BASE,
            f"{day:%Y}/{month}/{filename}"
        )
    else:
        filename = f"BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"
        url = urljoin(UDIFF_BASE, filename)
    return filename, url


def expected_csv_date(df, day):
    if "TIMESTAMP" in df.columns:
        values = pd.to_datetime(
            df["TIMESTAMP"].astype(str).str.strip(),
            format="%d-%b-%Y",
            errors="coerce",
        ).dropna().dt.date.unique()
    elif "TradDt" in df.columns:
        values = pd.to_datetime(
            df["TradDt"].astype(str).str.strip(),
            errors="coerce",
        ).dropna().dt.date.unique()
    else:
        raise ValueError("CSV has neither TIMESTAMP nor TradDt date field")

    if len(values) != 1 or values[0] != day:
        raise ValueError(
            f"Archive date mismatch: expected {day}, found {list(values)}"
        )


def validate_archive(path, day):
    with zipfile.ZipFile(path) as zf:
        bad_member = zf.testzip()
        if bad_member is not None:
            raise ValueError(f"ZIP CRC failure in {bad_member}")

        csv_members = [
            name for name in zf.namelist()
            if name.lower().endswith(".csv") and not name.endswith("/")
        ]
        if len(csv_members) != 1:
            raise ValueError(
                f"Expected exactly one CSV; found {len(csv_members)}"
            )

        with zf.open(csv_members[0]) as handle:
            df = pd.read_csv(handle, dtype=str)

    legacy_required = {
        "SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE",
        "PREVCLOSE", "TOTTRDQTY", "TOTTRDVAL", "TIMESTAMP", "TOTALTRADES"
    }
    udiff_required = {
        "TradDt", "TckrSymb", "SctySrs", "OpnPric", "HghPric", "LwPric",
        "ClsPric", "PrvsClsgPric", "TtlTradgVol", "TtlTrfVal",
        "TtlNbOfTxsExctd"
    }

    if legacy_required.issubset(df.columns):
        detected = "LEGACY"
    elif udiff_required.issubset(df.columns):
        detected = "UDIFF"
    else:
        raise ValueError("Unrecognized NSE bhavcopy CSV header")

    expected = "LEGACY" if day < LEGACY_CUTOFF else "UDIFF"
    if detected != expected:
        raise ValueError(
            f"Unexpected archive format for {day}: "
            f"expected {expected}, detected {detected}"
        )

    expected_csv_date(df, day)
    if df.empty:
        raise ValueError("CSV contains no data rows")
    return detected, len(df)


def load_manifest():
    if not MANIFEST_PATH.exists():
        return {"version": 1, "dates": {}}
    with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("dates"), dict):
        raise ValueError("Backfill manifest has an invalid structure")
    return data


def save_manifest(manifest):
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST_PATH.with_suffix(".json.part")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
    temporary.replace(MANIFEST_PATH)


def candidate_dates(start, end):
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)


def download_one(session, day, destination):
    filename, url = archive_details(day)
    temporary = destination.with_suffix(destination.suffix + ".part")

    try:
        response = session.get(url, timeout=(15, 45))
    except requests.RequestException as exc:
        raise RuntimeError(f"Network failure: {exc}") from exc

    if response.status_code == 404:
        return "NOT_FOUND", url, filename, None

    response.raise_for_status()
    temporary.write_bytes(response.content)

    try:
        detected, row_count = validate_archive(temporary, day)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return "DOWNLOADED", url, filename, {
        "format": detected,
        "csv_rows": row_count,
        "bytes": destination.stat().st_size,
    }


def import_archive(path):
    result = subprocess.run(
        [
            sys.executable,
            str(IMPORTER),
            "--archive",
            str(path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    if result.returncode != 0:
        raise RuntimeError(
            f"Importer exited with code {result.returncode}"
        )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Resumable NSE CM historical backfill. "
            "404 dates are recorded as NOT_FOUND, never assumed holidays."
        )
    )
    parser.add_argument("--start-date", default="2016-11-08")
    parser.add_argument("--end-date", default="2026-11-08")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Maximum weekday candidates to process in this run."
    )
    parser.add_argument(
        "--plan-only", action="store_true",
        help="List weekday candidates without downloading or importing."
    )
    parser.add_argument(
        "--retry-not-found", action="store_true",
        help="Retry dates previously recorded as NOT_FOUND."
    )
    parser.add_argument(
        "--download-only", action="store_true",
        help="Download and validate archives but do not import them."
    )
    args = parser.parse_args()

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if end < start:
        parser.error("--end-date must be on or after --start-date")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    dates = list(candidate_dates(start, end))
    if args.limit is not None:
        dates = dates[:args.limit]

    print("GREEDY STOCKS - RESUMABLE NSE HISTORICAL BACKFILL")
    print(f"Range: {start} through {end}")
    print(f"Weekday candidates in this run: {len(dates)}")
    print("Legacy format: before 2024-07-08")
    print("UDiFF format: 2024-07-08 onward")
    print("404 policy: NOT_FOUND for later calendar review")
    if args.plan_only:
        for day in dates:
            filename, url = archive_details(day)
            print(f"{day} | {filename} | {url}")
        return

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    session = make_session()

    downloaded = imported = existing = not_found = failed = reviewed = 0

    for index, day in enumerate(dates, start=1):
        key = day.isoformat()
        state = manifest["dates"].get(key, {})
        status = state.get("status")

        if status == "IMPORTED":
            reviewed += 1
            continue
        if status == "NOT_FOUND" and not args.retry_not_found:
            not_found += 1
            continue

        filename, url = archive_details(day)
        destination = ARCHIVE_DIR / filename

        try:
            if destination.exists():
                detected, row_count = validate_archive(destination, day)
                existing += 1
                detail = {
                    "format": detected,
                    "csv_rows": row_count,
                    "bytes": destination.stat().st_size,
                }
                print(f"[EXISTING] {day} | {filename}")
            else:
                result, url, filename, detail = download_one(
                    session, day, destination
                )
                if result == "NOT_FOUND":
                    manifest["dates"][key] = {
                        "status": "NOT_FOUND",
                        "url": url,
                        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "note": "HTTP 404; not classified as a holiday",
                    }
                    save_manifest(manifest)
                    not_found += 1
                    print(f"[NOT FOUND - REVIEW] {day} | HTTP 404")
                    continue
                downloaded += 1
                print(
                    f"[DOWNLOADED] {day} | {detail['format']} | "
                    f"{detail['csv_rows']} CSV rows | {detail['bytes']} bytes"
                )

            manifest["dates"][key] = {
                "status": "DOWNLOADED",
                "archive": filename,
                "url": url,
                **detail,
                "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            save_manifest(manifest)

            if not args.download_only:
                import_archive(destination)
                manifest["dates"][key]["status"] = "IMPORTED"
                manifest["dates"][key]["imported_at"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )
                save_manifest(manifest)
                imported += 1

        except Exception as exc:
            failed += 1
            manifest["dates"][key] = {
                "status": "FAILED",
                "archive": filename,
                "url": url,
                "error": str(exc),
                "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            save_manifest(manifest)
            print(f"[FAILED] {day} | {exc}", file=sys.stderr)

        print(
            f"Progress {index}/{len(dates)} | downloaded {downloaded} | "
            f"imported {imported} | existing {existing} | "
            f"not-found {not_found} | failed {failed}"
        )

    print("\nBACKFILL RUN SUMMARY")
    print("Weekday candidates:", len(dates))
    print("New downloads:", downloaded)
    print("Imported dates:", imported)
    print("Existing archives checked:", existing)
    print("Previously imported dates skipped:", reviewed)
    print("HTTP 404 dates needing calendar review:", not_found)
    print("Failures needing investigation:", failed)
    print("Manifest:", MANIFEST_PATH)


if __name__ == "__main__":
    main()
