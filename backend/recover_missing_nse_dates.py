import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import Counter

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Resolve project paths and Python imports correctly.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database import engine
from sqlalchemy import text

FOLDER = ROOT / "database" / "raw" / "bhavcopy"
MANIFEST = FOLDER / "backfill_manifest.json"
IMPORTER = ROOT / "backend" / "import_nifty50_historical_prices.py"
CUTOFF = date(2024, 7, 8)

FOLDER.mkdir(parents=True, exist_ok=True)

# Preserve original manifest.
backup = FOLDER / "backfill_manifest.before_recovery.json"
if not backup.exists():
    shutil.copy2(MANIFEST, backup)

data = json.loads(MANIFEST.read_text(encoding="utf-8"))
entries = data["dates"]

def save_manifest():
    tmp = MANIFEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(MANIFEST)

def archive_details(d):
    if d < CUTOFF:
        month = d.strftime("%b").upper()
        name = f"cm{d.day:02d}{month}{d.year}bhav.csv.zip"
        url = (
            "https://archives.nseindia.com/content/historical/"
            f"EQUITIES/{d.year}/{month}/{name}"
        )
    else:
        name = f"BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
        url = f"https://nsearchives.nseindia.com/content/cm/{name}"
    return name, url

def set_status(key, name, url, status, error=""):
    entries[key] = {
        "archive": name,
        "url": url,
        "status": status,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "error": error
    }
    save_manifest()

# Get actual missing weekdays.
with engine.connect() as conn:
    stored = set(conn.execute(text("""
        SELECT DISTINCT trade_date FROM stock_prices
    """)).scalars().all())

if not stored:
    raise RuntimeError("No stock price dates found in database.")

first, last = min(stored), max(stored)
missing = []
d = first

while d <= last:
    if d.weekday() < 5 and d not in stored:
        missing.append(d)
    d += timedelta(days=1)

# Process dates not already recorded in the manifest.
targets = [d for d in missing if d.isoformat() not in entries]

print("\n===== GREEDY STOCKS AUTOMATIC RECOVERY =====")
print("Missing weekdays:", len(missing))
print("Already in manifest:", len(missing) - len(targets))
print("New dates to investigate:", len(targets))
print("Manifest backup:", backup)

session = requests.Session()
retry = Retry(
    total=5,
    connect=5,
    read=5,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
    respect_retry_after_header=True
)
session.mount("https://", HTTPAdapter(max_retries=retry))
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/"
})

counts = Counter()

for index, day in enumerate(targets, 1):
    key = day.isoformat()
    name, url = archive_details(day)
    archive = FOLDER / name
    part = archive.with_suffix(archive.suffix + ".part")

    print(f"\n[{index}/{len(targets)}] Checking {key}")

    try:
        if not archive.exists():
            response = session.get(url, timeout=60)

            if response.status_code == 404:
                set_status(
                    key, name, url, "NOT_FOUND",
                    "HTTP 404 during recovery check"
                )
                counts["NOT_FOUND"] += 1
                print("HTTP 404 - needs calendar/archive review.")
                continue

            response.raise_for_status()
            part.write_bytes(response.content)

            with zipfile.ZipFile(part) as z:
                bad = z.testzip()
                csv_files = [
                    x for x in z.namelist()
                    if x.lower().endswith(".csv")
                ]

                if bad:
                    raise RuntimeError(f"Corrupt ZIP member: {bad}")

                if len(csv_files) != 1:
                    raise RuntimeError(
                        f"Expected one CSV; found {len(csv_files)}"
                    )

            part.replace(archive)

        # Dry-run validation before any database writes.
        dry = subprocess.run(
            [
                sys.executable, str(IMPORTER),
                "--archive", str(archive),
                "--dry-run"
            ],
            cwd=ROOT,
            capture_output=True,
            text=True
        )

        print(dry.stdout)
        if dry.stderr:
            print(dry.stderr)

        match = re.search(
            r"New price records:\s*(\d+)", dry.stdout
        )
        new_records = int(match.group(1)) if match else 0

        rejected = re.search(
            r"Rejected archives:\s*(\d+)", dry.stdout
        )
        rejected_count = int(rejected.group(1)) if rejected else -1

        if (
            dry.returncode != 0
            or rejected_count != 0
            or new_records == 0
        ):
            error = (
                f"Dry-run unsuccessful; new_records={new_records}, "
                f"rejected={rejected_count}. "
                + dry.stderr[-1000:]
            )
            set_status(key, name, url, "FAILED", error)
            counts["FAILED"] += 1
            print("NOT IMPORTED - dry-run failed or had no new rows.")
            continue

        # Live import after successful dry-run.
        live = subprocess.run(
            [
                sys.executable, str(IMPORTER),
                "--archive", str(archive)
            ],
            cwd=ROOT,
            capture_output=True,
            text=True
        )

        print(live.stdout)
        if live.stderr:
            print(live.stderr)

        if live.returncode != 0:
            set_status(
                key, name, url, "FAILED",
                live.stderr[-1000:]
            )
            counts["FAILED"] += 1
            print("LIVE IMPORT FAILED.")
            continue

        # Confirm records exist for this date.
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT COUNT(*) FROM stock_prices
                WHERE trade_date = :day
            """), {"day": day}).scalar_one()

        if rows == 0:
            set_status(
                key, name, url, "FAILED",
                "Live import succeeded but DB has zero rows"
            )
            counts["FAILED"] += 1
            continue

        set_status(key, name, url, "IMPORTED")
        counts["IMPORTED"] += 1
        print(f"SUCCESS: {rows} records imported for {key}")

    except Exception as exc:
        if part.exists():
            part.unlink()

        set_status(key, name, url, "FAILED", str(exc))
        counts["FAILED"] += 1
        print("ERROR:", exc)

    time.sleep(0.5)

# Final database audit.
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT MIN(trade_date), MAX(trade_date),
               COUNT(*), COUNT(DISTINCT trade_date),
               COUNT(DISTINCT company_id)
        FROM stock_prices
    """)).fetchone()

    final_dates = set(conn.execute(text("""
        SELECT DISTINCT trade_date FROM stock_prices
    """)).scalars().all())

remaining = []
d = min(final_dates)
end = max(final_dates)

while d <= end:
    if d.weekday() < 5 and d not in final_dates:
        remaining.append(d)
    d += timedelta(days=1)

print("\n===== RECOVERY SUMMARY =====")
for status in ["IMPORTED", "NOT_FOUND", "FAILED"]:
    print(f"{status}: {counts[status]}")

print("\n===== FINAL DATABASE AUDIT =====")
print("First date:", result[0])
print("Last date:", result[1])
print("Total records:", result[2])
print("Trading dates:", result[3])
print("Companies represented:", result[4])
print("Remaining missing weekdays:", len(remaining))

print("\nManifest:", MANIFEST)
print("Backup:", backup)
print("\nRECOVERY FINISHED.")
