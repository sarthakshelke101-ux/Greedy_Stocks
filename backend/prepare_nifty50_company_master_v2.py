
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

SOURCE_FILE = (
    ROOT / "database" / "processed" /
    "constituents" / "nifty50_company_master.csv"
)

OUTPUT_DIR = (
    ROOT / "database" / "processed" / "constituents"
)

OUTPUT_FILE = OUTPUT_DIR / "nifty50_company_master_v2.csv"


def main():
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(SOURCE_FILE)

    df = pd.read_csv(SOURCE_FILE, dtype=str)

    required = [
        "historical_symbol",
        "canonical_symbol",
        "company_identity",
        "mapping_type",
        "first_snapshot",
        "last_snapshot",
        "snapshot_count",
        "industry",
        "demerger_ex_date",
        "symbol_change_date",
        "price_history_adjustment_required",
    ]

    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    # Preserve the original source industry exactly.
    df["source_industry"] = df["industry"]

    # Keep the pre-demerger Tata Motors identity separate.
    old_tata = df["historical_symbol"] == "TATAMOTORS"

    df.loc[old_tata, "canonical_symbol"] = "TATAMOTORS"
    df.loc[old_tata, "company_identity"] = "Tata Motors Limited (Pre-Demerger)"
    df.loc[old_tata, "mapping_type"] = "PRE_DEMERGER_INSTRUMENT"
    df.loc[old_tata, "price_history_adjustment_required"] = "YES"

    # TMPV remains its own post-demerger identity.
    new_tata = df["historical_symbol"] == "TMPV"

    df.loc[new_tata, "canonical_symbol"] = "TMPV"
    df.loc[new_tata, "company_identity"] = (
        "Tata Motors Passenger Vehicles Limited"
    )
    df.loc[new_tata, "mapping_type"] = "POST_DEMERGER_INSTRUMENT"

    # Each historical symbol must now map to one unique instrument identity.
    if df["historical_symbol"].duplicated().any():
        raise ValueError("Duplicate historical symbols detected.")

    if df["canonical_symbol"].duplicated().any():
        duplicates = df[
            df["canonical_symbol"].duplicated(keep=False)
        ]

        raise ValueError(
            "Canonical instrument symbols are not unique:\n"
            + duplicates.to_string(index=False)
        )

    if len(df) != 54:
        raise ValueError(
            f"Expected 54 historical instruments, found {len(df)}"
        )

    if df["industry"].isna().any():
        raise ValueError("Missing source industry detected.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)

    print("=" * 65)
    print("NIFTY 50 COMPANY MASTER V2 PREPARATION")
    print("=" * 65)

    print(f"Historical instruments: {len(df)}")
    print(f"Unique canonical symbols: {df['canonical_symbol'].nunique()}")
    print(f"Source industries preserved: {df['source_industry'].nunique()}")

    print("\nTATA MOTORS IDENTITIES:")
    print(
        df[
            df["historical_symbol"].isin(["TATAMOTORS", "TMPV"])
        ][
            [
                "historical_symbol",
                "canonical_symbol",
                "company_identity",
                "mapping_type",
                "price_history_adjustment_required",
            ]
        ].to_string(index=False)
    )

    print(f"\nSaved: {OUTPUT_FILE}")
    print("\nOriginal company master remains unchanged.")


if __name__ == "__main__":
    main()
