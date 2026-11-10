
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "database" / "processed" / "constituents"

SOURCE = DATA_DIR / "nifty50_constituent_snapshots.csv"
OUTPUT = DATA_DIR / "nifty50_membership_changes.csv"

df = pd.read_csv(SOURCE, dtype=str)

df["report_month"] = pd.to_datetime(
    df["report_month"],
    format="%Y-%m"
)

df["Security Symbol"] = (
    df["Security Symbol"]
    .fillna("")
    .str.strip()
    .str.upper()
)

df = df.sort_values(["report_month", "Security Symbol"])

months = sorted(df["report_month"].unique())

changes = []

print("=" * 75)
print("GREEDY STOCKS — NIFTY 50 MEMBERSHIP CHANGE AUDIT")
print("=" * 75)

for previous_month, current_month in zip(months, months[1:]):

    previous = df[df["report_month"] == previous_month]
    current = df[df["report_month"] == current_month]

    previous_symbols = set(previous["Security Symbol"])
    current_symbols = set(current["Security Symbol"])

    added = sorted(current_symbols - previous_symbols)
    removed = sorted(previous_symbols - current_symbols)

    previous_label = previous_month.strftime("%Y-%m")
    current_label = current_month.strftime("%Y-%m")

    print(f"\n{previous_label} -> {current_label}")

    if not added and not removed:
        print("No constituent changes.")
        continue

    for symbol in added:
        print(f"ADDED:   {symbol}")
        changes.append({
            "from_month": previous_label,
            "to_month": current_label,
            "change_type": "ADDED",
            "symbol": symbol
        })

    for symbol in removed:
        print(f"REMOVED: {symbol}")
        changes.append({
            "from_month": previous_label,
            "to_month": current_label,
            "change_type": "REMOVED",
            "symbol": symbol
        })

result = pd.DataFrame(
    changes,
    columns=["from_month", "to_month", "change_type", "symbol"]
)

result.to_csv(OUTPUT, index=False)

print("\n" + "=" * 75)
print("SUMMARY")
print("=" * 75)

print(f"Monthly snapshots compared: {len(months) - 1}")
print(f"Total additions: {(result['change_type'] == 'ADDED').sum()}")
print(f"Total removals: {(result['change_type'] == 'REMOVED').sum()}")
print(f"Total membership changes: {len(result)}")

print(f"\nAudit file saved:\n{OUTPUT}")

print("\nIMPORTANT:")
print("These are differences between monthly snapshots.")
print("They are NOT verified official effective dates.")
print("Possible symbol changes require separate investigation.")
