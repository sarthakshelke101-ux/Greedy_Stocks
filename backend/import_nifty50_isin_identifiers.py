import sys
sys.path.insert(0, "backend")

from pathlib import Path
import pandas as pd
from sqlalchemy import text
from database import engine

SOURCE = Path("database/processed/audit/nifty50_isin_series_details.csv")
SOURCE_NAME = "NSE CM-UDiFF Common Bhavcopy Final"
SOURCE_REFERENCE = (
    "nifty50_isin_series_details.csv; EQ-series observations; "
    "validity boundaries represent first and last observed trading dates"
)

def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing source file: {SOURCE}")

    df = pd.read_csv(SOURCE, dtype=str)
    required = {"TradDt", "ISIN", "TckrSymb", "SctySrs"}

    if not required.issubset(df.columns):
        raise ValueError(f"Missing columns: {required - set(df.columns)}")

    df = df[df["SctySrs"].str.strip() == "EQ"].copy()

    for col in ["TradDt", "ISIN", "TckrSymb"]:
        df[col] = df[col].str.strip()

    df["TradDt"] = pd.to_datetime(df["TradDt"], errors="raise").dt.date

    if df[["TradDt", "ISIN", "TckrSymb"]].isna().any().any():
        raise ValueError("Null values found in required source columns.")

    if df.duplicated(["TradDt", "TckrSymb"]).any():
        raise ValueError("Duplicate symbol/date observations found.")

    df = df.sort_values(["TckrSymb", "TradDt"]).reset_index(drop=True)

    # A new period begins whenever the ISIN changes for a symbol.
    df["new_period"] = (
        df.groupby("TckrSymb")["ISIN"].transform(
            lambda s: s.ne(s.shift())
        )
    )
    df["period_number"] = df.groupby("TckrSymb")["new_period"].cumsum()

    periods = (
        df.groupby(["TckrSymb", "ISIN", "period_number"], as_index=False)
        .agg(
            valid_from=("TradDt", "min"),
            valid_to=("TradDt", "max"),
            observation_count=("TradDt", "count")
        )
    )

    with engine.begin() as conn:
        companies = conn.execute(
            text("SELECT id, symbol FROM companies")
        ).mappings().all()

        company_map = {row["symbol"]: row["id"] for row in companies}

        missing = sorted(set(periods["TckrSymb"]) - set(company_map))
        if missing:
            raise ValueError(f"Symbols missing from companies table: {missing}")

        inserted = 0
        unchanged = 0

        for row in periods.to_dict("records"):
            company_id = company_map[row["TckrSymb"]]

            existing = conn.execute(
                text("""
                    SELECT id, valid_to
                    FROM company_identifiers
                    WHERE company_id = :company_id
                      AND identifier_type = 'ISIN'
                      AND identifier_value = :isin
                      AND valid_from = :valid_from
                """),
                {
                    "company_id": company_id,
                    "isin": row["ISIN"],
                    "valid_from": row["valid_from"]
                }
            ).mappings().first()

            if existing:
                if existing["valid_to"] != row["valid_to"]:
                    raise ValueError(
                        f"Existing period conflicts for "
                        f"{row['TckrSymb']} / {row['ISIN']}"
                    )
                unchanged += 1
                continue

            conn.execute(
                text("""
                    INSERT INTO company_identifiers (
                        company_id, identifier_type, identifier_value,
                        valid_from, valid_to, source_name, source_reference
                    )
                    VALUES (
                        :company_id, 'ISIN', :isin,
                        :valid_from, :valid_to, :source_name, :source_reference
                    )
                """),
                {
                    "company_id": company_id,
                    "isin": row["ISIN"],
                    "valid_from": row["valid_from"],
                    "valid_to": row["valid_to"],
                    "source_name": SOURCE_NAME,
                    "source_reference": (
                        f"{SOURCE_REFERENCE}; "
                        f"symbol={row['TckrSymb']}; "
                        f"observations={row['observation_count']}"
                    )
                }
            )
            inserted += 1

        total = conn.execute(
            text("SELECT COUNT(*) FROM company_identifiers")
        ).scalar_one()

    print("\nISIN IMPORT SUCCESS")
    print("-" * 50)
    print("EQ observations:", len(df))
    print("Historical ISIN periods:", len(periods))
    print("New records inserted:", inserted)
    print("Existing records unchanged:", unchanged)
    print("Total database identifier records:", total)

    print("\nPERIOD SUMMARY")
    print(
        periods.to_string(index=False)
    )

if __name__ == "__main__":
    main()
