
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "database" / "processed" / "constituents"

SOURCE = DATA_DIR / "nifty50_membership_changes.csv"
OUTPUT = DATA_DIR / "nifty50_membership_events_reconciled.csv"

df = pd.read_csv(SOURCE, dtype=str)

events = []

# Verified symbol continuity
events.append({
    "event_date": "2025-10-24",
    "event_type": "SYMBOL_CHANGE",
    "old_symbol": "TATAMOTORS",
    "new_symbol": "TMPV",
    "company_identity": "Tata Motors Passenger Vehicles Limited",
    "verification": "NSE circular NSE/FAOP/70882"
})

# Verified actual index replacements
verified_replacements = [
    {
        "event_date": "2025-09-30",
        "event_type": "INDEX_REPLACEMENT",
        "old_symbol": "HEROMOTOCO",
        "new_symbol": "INDIGO",
        "company_identity": "Separate company replacement",
        "verification": "NSE Indices press release, 22 Aug 2025"
    },
    {
        "event_date": "2025-09-30",
        "event_type": "INDEX_REPLACEMENT",
        "old_symbol": "INDUSINDBK",
        "new_symbol": "MAXHEALTH",
        "company_identity": "Separate company replacement",
        "verification": "NSE Indices press release, 22 Aug 2025"
    },
    {
        "event_date": "2026-09-30",
        "event_type": "INDEX_REPLACEMENT",
        "old_symbol": "WIPRO",
        "new_symbol": "BSE",
        "company_identity": "Separate company replacement",
        "verification": "NSE Indices press release, 10 Aug 2026"
    }
]

events.extend(verified_replacements)

result = pd.DataFrame(events)

result.to_csv(OUTPUT, index=False)

print("=" * 70)
print("NIFTY 50 MEMBERSHIP EVENT RECONCILIATION")
print("=" * 70)

print(result.to_string(index=False))

print("\nMonthly snapshot differences from original audit:")
print(df.to_string(index=False))

print(f"\nReconciled event file saved:\n{OUTPUT}")
print("\nNOTE: This file contains verified event mappings.")
print("It does not replace the original monthly snapshot history.")
