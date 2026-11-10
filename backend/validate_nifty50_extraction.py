
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "database" / "processed" / "constituents"

REAL_FILE = DATA_DIR / "nifty50_constituent_snapshots.csv"
DUMMY_FILE = DATA_DIR / "nifty50_dummy_adjustments.csv"

if not REAL_FILE.exists():
    raise FileNotFoundError(f"Missing file: {REAL_FILE}")

df = pd.read_csv(REAL_FILE, dtype=str)
dummy = pd.read_csv(DUMMY_FILE, dtype=str) if DUMMY_FILE.exists() else pd.DataFrame()

symbol_col = "Security Symbol"
month_col = "report_month"
weight_col = "Weightage (%)"

required = [symbol_col, month_col, weight_col]
missing_columns = [c for c in required if c not in df.columns]

if missing_columns:
    raise ValueError(f"Missing columns: {missing_columns}")

df[symbol_col] = df[symbol_col].fillna("").str.strip().str.upper()
df[weight_col] = pd.to_numeric(df[weight_col], errors="coerce")

print("=" * 75)
print("GREEDY STOCKS — NIFTY 50 EXTRACTION VALIDATION")
print("=" * 75)

print(f"\nTotal real records: {len(df)}")
print(f"Unique report months: {df[month_col].nunique()}")
print(f"Unique symbols across all months: {df[symbol_col].nunique()}")

blank_symbols = int((df[symbol_col] == "").sum())
dummy_in_real = int(df[symbol_col].str.startswith("DUMMY").sum())
invalid_weights = int(df[weight_col].isna().sum())

print(f"Blank symbols: {blank_symbols}")
print(f"DUMMY symbols in real file: {dummy_in_real}")
print(f"Missing/non-numeric weights: {invalid_weights}")

print("\nMONTH-BY-MONTH VALIDATION")
print("-" * 75)

all_months_pass = True

for month, group in df.groupby(month_col):
    count = len(group)
    unique_count = group[symbol_col].nunique()
    duplicates = int(group[symbol_col].duplicated().sum())
    weight_total = group[weight_col].sum(min_count=1)

    passed = (
        count == 50
        and unique_count == 50
        and duplicates == 0
        and (group[symbol_col] != "").all()
        and not group[symbol_col].str.startswith("DUMMY").any()
        and group[weight_col].notna().all()
    )

    if not passed:
        all_months_pass = False

    print(
        f"{month} | rows={count} | unique={unique_count} | "
        f"duplicates={duplicates} | weight total={weight_total:.6f} | "
        f"{'PASS' if passed else 'CHECK'}"
    )

print("\nDUMMY AUDIT FILE")
print("-" * 75)

if not dummy.empty:
    print(f"DUMMY records preserved: {len(dummy)}")
    print(
        dummy.groupby("report_month")["Security Symbol"]
        .apply(lambda values: ", ".join(values.astype(str)))
        .to_string()
    )
else:
    print("No DUMMY records in the separate audit file.")

overall_pass = (
    all_months_pass
    and blank_symbols == 0
    and dummy_in_real == 0
)

print("\n" + "=" * 75)
print("OVERALL RESULT:", "PASS" if overall_pass else "CHECK REQUIRED")
print("=" * 75)

print("\nNo database records were created or modified.")
