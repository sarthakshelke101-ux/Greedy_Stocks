import sys, json, csv
from pathlib import Path
from datetime import date, timedelta
from collections import Counter, defaultdict
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database import engine

MANIFEST = ROOT / "database" / "raw" / "bhavcopy" / "backfill_manifest.json"
OUTPUT = ROOT / "database" / "raw" / "bhavcopy" / "missing_dates_audit.csv"

# NSE Capital Market weekday holidays, 2016–2026.
# Historical lists are cross-checked against published NSE calendars.
HOLIDAYS = set("""
2016-01-26 2016-03-07 2016-03-24 2016-03-25 2016-04-14 2016-04-15
2016-04-19 2016-07-06 2016-08-15 2016-09-05 2016-09-13 2016-10-11
2016-10-12 2016-10-31 2016-11-14

2017-01-26 2017-02-24 2017-03-13 2017-04-04 2017-04-14 2017-05-01
2017-06-26 2017-08-15 2017-08-25 2017-10-02 2017-10-20 2017-12-25

2018-01-26 2018-02-13 2018-03-02 2018-03-29 2018-03-30 2018-05-01
2018-08-15 2018-08-22 2018-09-13 2018-09-20 2018-10-02 2018-10-18
2018-11-08 2018-11-23 2018-12-25

2019-03-04 2019-03-21 2019-04-17 2019-04-19 2019-04-29 2019-05-01
2019-06-05 2019-08-12 2019-08-15 2019-09-02 2019-09-10 2019-10-02
2019-10-08 2019-10-21 2019-10-28 2019-11-12 2019-12-25

2020-02-21 2020-03-10 2020-04-02 2020-04-06 2020-04-10 2020-04-14
2020-05-01 2020-05-25 2020-10-02 2020-11-16 2020-11-30 2020-12-25

2021-01-26 2021-03-11 2021-03-29 2021-04-02 2021-04-14 2021-04-21
2021-05-13 2021-07-21 2021-08-19 2021-09-10 2021-10-15 2021-11-05
2021-11-19

2022-01-26 2022-03-01 2022-03-18 2022-04-14 2022-04-15 2022-05-03
2022-08-09 2022-08-15 2022-08-31 2022-10-05 2022-10-26 2022-11-08

2023-01-26 2023-03-07 2023-03-30 2023-04-04 2023-04-07 2023-04-14
2023-05-01 2023-06-29 2023-08-15 2023-09-19 2023-10-02 2023-10-24
2023-11-14 2023-11-27 2023-12-25

2024-01-22 2024-01-26 2024-03-08 2024-03-25 2024-03-29 2024-05-20
2024-08-15 2024-10-02 2024-11-20 2024-12-25

2025-02-26 2025-03-14 2025-03-31 2025-04-10 2025-04-14 2025-04-18
2025-05-01 2025-08-15 2025-08-27 2025-10-02 2025-10-22 2025-11-05
2025-12-25

2026-01-15 2026-01-26 2026-03-03 2026-03-26 2026-03-31 2026-04-03
2026-04-14 2026-05-01 2026-05-28 2026-06-26 2026-09-14 2026-10-02
2026-10-20 2026-11-10 2026-11-24 2026-12-25
""".split())

HOLIDAY_NAMES = {
    "2024-01-22": "Ram Mandir consecration",
    "2024-05-20": "Lok Sabha election",
    "2024-11-20": "Maharashtra assembly election",
    "2026-01-15": "Municipal Corporation Election (Maharashtra)",
}

with engine.connect() as conn:
    first, last = conn.execute(text("""
        SELECT MIN(trade_date), MAX(trade_date) FROM stock_prices
    """)).one()

    existing = {
        row[0] for row in conn.execute(text("""
            SELECT DISTINCT trade_date
            FROM stock_prices
            WHERE trade_date BETWEEN :first AND :last
        """), {"first": first, "last": last})
    }

with open(MANIFEST, "r", encoding="utf-8") as f:
    manifest = json.load(f)

entries = manifest.get("entries", manifest)
if not isinstance(entries, dict):
    entries = {}

missing = []
d = first
while d <= last:
    if d.weekday() < 5 and d not in existing:
        missing.append(d)
    d += timedelta(days=1)

rows = []
for d in missing:
    key = d.isoformat()
    entry = entries.get(key, {})
    if not isinstance(entry, dict):
        entry = {}

    manifest_status = entry.get("status", "NO_MANIFEST_ENTRY")
    if key in HOLIDAYS:
        classification = "NSE_HOLIDAY"
        note = HOLIDAY_NAMES.get(key, "Listed weekday market holiday")
    else:
        classification = "POTENTIAL_DATA_GAP"
        note = "Not in the holiday list used by this audit; verify archive/session"

    rows.append({
        "date": key,
        "year": d.year,
        "weekday": d.strftime("%A"),
        "classification": classification,
        "manifest_status": manifest_status,
        "archive": entry.get("archive", ""),
        "manifest_error": entry.get("error", ""),
        "note": note,
    })

with open(OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [
        "date", "year", "weekday", "classification",
        "manifest_status", "archive", "manifest_error", "note"
    ])
    writer.writeheader()
    writer.writerows(rows)

print("\n========== 139-DATE AUDIT ==========")
print("Database range:", first, "to", last)
print("Missing weekdays found:", len(rows))
print("\nCLASSIFICATION:")
for k, v in Counter(r["classification"] for r in rows).items():
    print(f"{k}: {v}")

print("\nMANIFEST STATUS:")
for k, v in Counter(r["manifest_status"] for r in rows).items():
    print(f"{k}: {v}")

print("\nYEAR-WISE BREAKDOWN:")
years = defaultdict(Counter)
for r in rows:
    years[r["year"]][r["classification"]] += 1
for year in sorted(years):
    counts = years[year]
    print(f"{year}: NSE_HOLIDAY={counts['NSE_HOLIDAY']} | POTENTIAL_DATA_GAP={counts['POTENTIAL_DATA_GAP']}")

print("\nDATE-BY-DATE RESULTS:")
for r in rows:
    print(
        f"{r['date']} | {r['weekday']:<9} | "
        f"{r['classification']:<19} | "
        f"{r['manifest_status']:<16} | {r['note']}"
    )

print("\nCSV REPORT:", OUTPUT)
print("\nIMPORTANT: POTENTIAL_DATA_GAP is not proof of a trading session.")
print("The holiday list is a screening reference; verify uncertain dates against NSE archive records.")
