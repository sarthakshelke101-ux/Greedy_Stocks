
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "database" / "processed" / "constituents"

SOURCE = DATA_DIR / "nifty50_constituent_snapshots.csv"
OUTPUT = DATA_DIR / "nifty50_company_master.csv"

df = pd.read_csv(SOURCE, dtype=str)

df["Security Symbol"] = (
    df["Security Symbol"].fillna("").str.strip().str.upper()
)

df["report_month"] = pd.to_datetime(
    df["report_month"], format="%Y-%m"
)

# Historical identity and corporate-action mapping.
SYMBOL_MAP = {
    "TATAMOTORS": {
        "canonical_symbol": "TMPV",
        "company_identity": "Tata Motors Passenger Vehicles Limited",
        "mapping_type": "SYMBOL_CHANGE_WITH_DEMERGER",
        "demerger_ex_date": "2025-10-14",
        "symbol_change_date": "2025-10-24",
        "price_history_adjustment_required": "YES"
    }
}

def latest_nonempty(group, columns):
    for column in columns:
        if column in group.columns:
            values = group[column].dropna().astype(str).str.strip()
            values = values[values != ""]
            if not values.empty:
                return values.iloc[-1]
    return ""

master_rows = []

for symbol, group in df.groupby("Security Symbol"):
    group = group.sort_values("report_month")
    latest = group.iloc[-1]

    mapping = SYMBOL_MAP.get(symbol, {})

    master_rows.append({
        "historical_symbol": symbol,
        "canonical_symbol": mapping.get("canonical_symbol", symbol),
        "company_identity": mapping.get(
            "company_identity",
            latest.get("Security Name", "")
        ),
        "mapping_type": mapping.get("mapping_type", "DIRECT"),
        "first_snapshot": group["report_month"].min().strftime("%Y-%m"),
        "last_snapshot": group["report_month"].max().strftime("%Y-%m"),
        "snapshot_count": len(group),
        "industry": latest_nonempty(
            group,
            ["Basic Industry", "Industry"]
        ),
        "demerger_ex_date": mapping.get("demerger_ex_date", ""),
        "symbol_change_date": mapping.get("symbol_change_date", ""),
        "price_history_adjustment_required": mapping.get(
            "price_history_adjustment_required", "NO"
        )
    })

master = pd.DataFrame(master_rows).sort_values(
    ["canonical_symbol", "historical_symbol"]
)

master.to_csv(OUTPUT, index=False)

print("=" * 70)
print("NIFTY 50 COMPANY MASTER — VERSION 2")
print("=" * 70)

print(f"Historical symbols: {len(master)}")
print(f"Canonical identities: {master['canonical_symbol'].nunique()}")
print(f"Missing industries: {(master['industry'].fillna('').str.strip() == '').sum()}")

print("\nCORPORATE ACTION / SYMBOL MAPPING:")
print(
    master[master["mapping_type"] != "DIRECT"].to_string(index=False)
)

print(f"\nSaved: {OUTPUT}")
print("Original monthly snapshots remain unchanged.")
