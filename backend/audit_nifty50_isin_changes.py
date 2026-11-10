
from pathlib import Path
from zipfile import ZipFile
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BHAVCOPY_DIR = ROOT / "database" / "raw" / "bhavcopy"

TARGET_SYMBOLS = {
    "BAJFINANCE",
    "KOTAKBANK",
    "TATAMOTORS",
    "TMPV",
}

columns = ["TradDt", "ISIN", "TckrSymb", "SctySrs"]

frames = []

archives = sorted(BHAVCOPY_DIR.glob("*.zip"))

for archive_path in archives:
    with ZipFile(archive_path) as archive:
        csv_files = [
            name for name in archive.namelist()
            if name.lower().endswith(".csv")
        ]

        if len(csv_files) != 1:
            raise ValueError(
                f"Unexpected CSV count in {archive_path.name}"
            )

        with archive.open(csv_files[0]) as file:
            df = pd.read_csv(
                file,
                usecols=columns,
                dtype=str,
            )

    df["TckrSymb"] = (
        df["TckrSymb"].fillna("").str.strip().str.upper()
    )

    df["SctySrs"] = (
        df["SctySrs"].fillna("").str.strip().str.upper()
    )

    matched = df[df["TckrSymb"].isin(TARGET_SYMBOLS)].copy()

    frames.append(matched)

all_data = pd.concat(frames, ignore_index=True)

all_data["TradDt"] = pd.to_datetime(
    all_data["TradDt"],
    errors="coerce",
)

all_data["ISIN"] = all_data["ISIN"].fillna("").str.strip()

output_dir = ROOT / "database" / "processed" / "audit"
output_dir.mkdir(parents=True, exist_ok=True)

detail_file = output_dir / "nifty50_isin_series_details.csv"

all_data.sort_values(
    ["TckrSymb", "TradDt", "SctySrs", "ISIN"]
).to_csv(detail_file, index=False)

print("=" * 75)
print("ISIN AND SERIES DISTRIBUTION")
print("=" * 75)

print(
    all_data.groupby(
        ["TckrSymb", "SctySrs", "ISIN"],
        dropna=False,
    ).agg(
        rows=("TradDt", "size"),
        first_date=("TradDt", "min"),
        last_date=("TradDt", "max"),
        unique_dates=("TradDt", "nunique"),
    ).to_string()
)

print("\n" + "=" * 75)
print("EQ SERIES DUPLICATE CHECK")
print("=" * 75)

eq = all_data[all_data["SctySrs"] == "EQ"].copy()

duplicate_mask = eq.duplicated(
    ["TradDt", "TckrSymb"],
    keep=False,
)

print("EQ rows:", len(eq))
print("Unique EQ symbol-date pairs:", 
      eq[["TradDt", "TckrSymb"]].drop_duplicates().shape[0])
print("Duplicate EQ symbol-date rows:", int(duplicate_mask.sum()))

if duplicate_mask.any():
    print("\nDuplicate records:")
    print(
        eq[duplicate_mask].sort_values(
            ["TckrSymb", "TradDt"]
        ).to_string(index=False)
    )

print("\n" + "=" * 75)
print("TATA MOTORS TRANSITION")
print("=" * 75)

tata = eq[
    eq["TckrSymb"].isin(["TATAMOTORS", "TMPV"])
]

print(
    tata.groupby(
        ["TckrSymb", "ISIN"],
        dropna=False,
    ).agg(
        rows=("TradDt", "size"),
        first_date=("TradDt", "min"),
        last_date=("TradDt", "max"),
        unique_dates=("TradDt", "nunique"),
    ).to_string()
)

print(f"\nDetailed report saved: {detail_file}")
