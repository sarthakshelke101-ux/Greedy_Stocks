
import io
import zipfile
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOURCE_DIR = PROJECT_ROOT / "database" / "raw" / "constituents"
OUTPUT_DIR = PROJECT_ROOT / "database" / "processed" / "constituents"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MONTHS = {
    "jan": "01", "feb": "02", "mar": "03",
    "apr": "04", "may": "05", "jun": "06",
    "june": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11",
    "dec": "12",
}

snapshots = []
dummy_records = []

print("GREEDY STOCKS - NIFTY 50 CONSTITUENT EXTRACTION")
print("=" * 65)

archives = sorted(SOURCE_DIR.glob("mcwb_*.zip"))

for archive in archives:
    parts = archive.stem.lower().replace("mcwb_", "").split("_")

    if len(parts) != 1:
        print(f"SKIPPED: Unexpected filename: {archive.name}")
        continue

    month_part = parts[0]

    month_name = "".join(
        character for character in month_part if character.isalpha()
    )
    year_part = "".join(
        character for character in month_part if character.isdigit()
    )

    if month_name not in MONTHS or len(year_part) != 2:
        print(f"SKIPPED: Cannot identify month: {archive.name}")
        continue

    report_month = f"20{year_part}-{MONTHS[month_name]}"

    with zipfile.ZipFile(archive) as zip_file:

        # IMPORTANT: Only NIFTY 50. Never read NIFTY Next 50.
        target_file = next(
            (
                name for name in zip_file.namelist()
                if Path(name).name.lower() == "nifty50_mcwb.csv"
            ),
            None
        )

        if target_file is None:
            print(f"MISSING NIFTY 50 FILE: {archive.name}")
            continue

        raw = pd.read_csv(
            io.BytesIO(zip_file.read(target_file)),
            header=None,
            dtype=str
        )

        header_index = None

        for index, row in raw.iterrows():
            values = row.fillna("").astype(str).str.strip().str.lower()

            if values.str.contains(
                "security symbol", regex=False
            ).any():
                header_index = index
                break

        if header_index is None:
            print(f"HEADER NOT FOUND: {archive.name}")
            continue

        df = pd.read_csv(
            io.BytesIO(zip_file.read(target_file)),
            header=header_index,
            dtype=str
        )

        df.columns = df.columns.astype(str).str.strip()

        symbol_col = next(
            (
                column for column in df.columns
                if "security symbol" in column.lower()
            ),
            None
        )

        if symbol_col is None:
            print(f"SYMBOL COLUMN NOT FOUND: {archive.name}")
            continue

        df = df.dropna(how="all").copy()

        df[symbol_col] = df[symbol_col].fillna("").str.strip().str.upper()

        # Ignore empty/non-security rows.
        df = df[df[symbol_col] != ""].copy()

        df.insert(0, "report_month", report_month)
        df.insert(1, "source_archive", archive.name)
        df.insert(2, "source_csv", target_file)

        # Keep dummy corporate-action entries separate.
        is_dummy = df[symbol_col].str.startswith("DUMMY")

        dummy_df = df[is_dummy].copy()
        real_df = df[~is_dummy].copy()

        if not dummy_df.empty:
            dummy_records.extend(dummy_df.to_dict("records"))

        snapshots.extend(real_df.to_dict("records"))

        symbols = real_df[symbol_col]

        duplicate_count = int(symbols.duplicated().sum())

        print(
            f"{report_month} | "
            f"Real constituents: {len(real_df)} | "
            f"DUMMY entries: {len(dummy_df)} | "
            f"Duplicate symbols: {duplicate_count}"
        )

        if len(real_df) != 50:
            print("  WARNING: Expected 50 real constituents.")

        if duplicate_count:
            print("  WARNING: Duplicate constituent symbols detected.")

# Create output dataframes.
snapshot_df = pd.DataFrame(snapshots)
dummy_df = pd.DataFrame(dummy_records)

snapshot_path = OUTPUT_DIR / "nifty50_constituent_snapshots.csv"
dummy_path = OUTPUT_DIR / "nifty50_dummy_adjustments.csv"

if not snapshot_df.empty:
    snapshot_df.to_csv(snapshot_path, index=False)

if not dummy_df.empty:
    dummy_df.to_csv(dummy_path, index=False)

print("\n" + "=" * 65)
print("EXTRACTION SUMMARY")
print("=" * 65)

print(f"Reports processed: {len(archives)}")
print(f"Real NIFTY 50 records: {len(snapshot_df)}")
print(f"Separate DUMMY records: {len(dummy_df)}")
print(f"Unique report months: {snapshot_df['report_month'].nunique() if not snapshot_df.empty else 0}")

print(f"\nReal constituents file:\n{snapshot_path}")
print(f"\nDUMMY audit file:\n{dummy_path}")

print("\nNIFTY 50 EXTRACTION COMPLETE.")
print("Original ZIP archives were not modified.")
