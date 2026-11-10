import csv
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INPUT = ROOT / "database" / "raw" / "index" / "missing_bhavcopy_recovery.csv"
BHAVCOPY_DIR = ROOT / "database" / "raw" / "bhavcopy"
OUTPUT = ROOT / "database" / "processed" / "index" / "benchmark_date_discrepancy_register.csv"

SPECIAL_SESSION = "2026-02-01"

OUTPUT.parent.mkdir(parents=True, exist_ok=True)

rows = []

with INPUT.open("r", newline="", encoding="utf-8-sig") as file:
    reader = csv.DictReader(file)

    for item in reader:
        trade_date = item["Date"]
        parsed_date = date.fromisoformat(trade_date)
        archive_name = item["ArchiveName"]

        archive_exists = any(BHAVCOPY_DIR.rglob(archive_name))

        if trade_date == SPECIAL_SESSION:
            classification = "CONFIRMED_SESSION"
            evidence = "NSE Circular NSE/CMTR/72349 dated 2026-01-16"
            notes = "Official circular confirms special live equity trading session on Sunday."
        else:
            classification = "PENDING_VERIFICATION"
            evidence = ""
            notes = "Weekday benchmark date; individual exchange-session evidence still required."

        rows.append({
            "trade_date": trade_date,
            "weekday": parsed_date.strftime("%A"),
            "archive_name": archive_name,
            "recovery_status": item["Status"],
            "archive_found": archive_exists,
            "classification": classification,
            "evidence_reference": evidence,
            "notes": notes,
        })

fields = [
    "trade_date",
    "weekday",
    "archive_name",
    "recovery_status",
    "archive_found",
    "classification",
    "evidence_reference",
    "notes",
]

with OUTPUT.open("w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

print("BENCHMARK DATE DISCREPANCY REGISTER")
print("-----------------------------------")
print(f"Total dates: {len(rows)}")
print(f"Confirmed sessions: {sum(r['classification'] == 'CONFIRMED_SESSION' for r in rows)}")
print(f"Pending verification: {sum(r['classification'] == 'PENDING_VERIFICATION' for r in rows)}")
print(f"Archives found: {sum(r['archive_found'] for r in rows)}")
print(f"Archives missing: {sum(not r['archive_found'] for r in rows)}")
print(f"Output: {OUTPUT}")
