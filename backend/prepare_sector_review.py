
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

SOURCE = (
    ROOT / "database" / "processed" /
    "constituents" / "nifty50_company_master_v2.csv"
)

OUTPUT = (
    ROOT / "database" / "processed" /
    "constituents" / "nifty50_sector_review.csv"
)

# Explicitly approved cosmetic normalizations.
NORMALIZATION_MAP = {
    "PRIVATE SECTOR BANK": "Private Sector Bank",
    "Exchange and DataPlatform": "Exchange and Data Platform",
    "Passenger Cars & UtilityVehicles":
        "Passenger Cars & Utility Vehicles",
}

def main():
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)

    df = pd.read_csv(SOURCE, dtype=str)

    if "source_industry" not in df.columns:
        raise ValueError("source_industry column is missing.")

    industries = sorted(
        df["source_industry"].dropna().unique()
    )

    review = pd.DataFrame({
        "source_industry": industries,
    })

    review["normalized_sector"] = review[
        "source_industry"
    ].map(
        lambda value: NORMALIZATION_MAP.get(value, value)
    )

    review["review_status"] = review[
        "source_industry"
    ].map(
        lambda value: (
            "APPROVED_COSMETIC_NORMALIZATION"
            if value in NORMALIZATION_MAP
            else "PRESERVED_SOURCE_LABEL"
        )
    )

    if review["normalized_sector"].isna().any():
        raise ValueError("Missing normalized sector detected.")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    review.to_csv(OUTPUT, index=False)

    print("=" * 65)
    print("GREEDY STOCKS — SECTOR NORMALIZATION")
    print("=" * 65)

    print(f"Original industry labels: {len(industries)}")
    print(
        "Normalized sectors:",
        review["normalized_sector"].nunique()
    )

    print("\nNORMALIZATION CHANGES:")
    print(
        review[
            review["source_industry"]
            != review["normalized_sector"]
        ].to_string(index=False)
    )

    print("\nFINAL SECTOR MAPPING:")
    print(review.to_string(index=False))

    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()
