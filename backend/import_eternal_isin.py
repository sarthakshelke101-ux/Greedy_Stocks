import sys
sys.path.insert(0, "backend")

from pathlib import Path
from zipfile import ZipFile
from io import BytesIO
import pandas as pd

from sqlalchemy import text
from database import engine

ROOT = Path("database/raw/bhavcopy")
COMPANY_ID = 16
SYMBOLS = {"ZOMATO", "ETERNAL"}

def main():
    observations = []

    for archive in sorted(ROOT.rglob("*.zip")):
        with ZipFile(archive) as zf:
            for member in zf.namelist():
                if not member.lower().endswith(".csv"):
                    continue

                with zf.open(member) as f:
                    df = pd.read_csv(BytesIO(f.read()), dtype=str)

                required = {"TradDt", "TckrSymb", "SctySrs", "ISIN"}
                if not required.issubset(df.columns):
                    continue

                matched = df[
                    df["TckrSymb"].str.strip().isin(SYMBOLS) &
                    (df["SctySrs"].str.strip() == "EQ")
                ]

                for r in matched.to_dict("records"):
                    observations.append({
                        "date": pd.to_datetime(r["TradDt"]).date(),
                        "symbol": r["TckrSymb"].strip(),
                        "isin": r["ISIN"].strip()
                    })

    if not observations:
        raise ValueError("No ZOMATO/ETERNAL EQ observations found.")

    df = pd.DataFrame(observations)

    if df.duplicated(["date"]).any():
        raise ValueError("More than one ZOMATO/ETERNAL EQ row on a date.")

    isins = sorted(df["isin"].unique())
    if len(isins) != 1:
        raise ValueError(f"Multiple ISINs found: {isins}")

    isin = isins[0]
    first_date = df["date"].min()
    last_date = df["date"].max()

    if len(df) != 369:
        raise ValueError(
            f"Expected 369 source observations, found {len(df)}. "
            "Review before importing."
        )

    with engine.begin() as conn:
        company = conn.execute(text("""
            SELECT id, symbol, isin
            FROM companies WHERE id = :id
        """), {"id": COMPANY_ID}).mappings().first()

        if not company or company["symbol"] != "ETERNAL":
            raise ValueError("Company identity check failed.")

        if company["isin"] not in (None, isin):
            raise ValueError(
                f"Company master ISIN conflict: {company['isin']} vs {isin}"
            )

        existing = conn.execute(text("""
            SELECT id, valid_to
            FROM company_identifiers
            WHERE company_id = :company_id
              AND identifier_type = 'ISIN'
              AND identifier_value = :isin
              AND valid_from = :first_date
        """), {
            "company_id": COMPANY_ID,
            "isin": isin,
            "first_date": first_date
        }).mappings().first()

        if existing:
            if str(existing["valid_to"]) != str(last_date):
                raise ValueError("Existing ETERNAL ISIN period conflicts.")
            status = "Already present and matching"
        else:
            conn.execute(text("""
                INSERT INTO company_identifiers (
                    company_id, identifier_type, identifier_value,
                    valid_from, valid_to, source_name, source_reference
                ) VALUES (
                    :company_id, 'ISIN', :isin,
                    :first_date, :last_date, :source_name, :source_reference
                )
            """), {
                "company_id": COMPANY_ID,
                "isin": isin,
                "first_date": first_date,
                "last_date": last_date,
                "source_name": "NSE CM-UDiFF Common Bhavcopy Final",
                "source_reference": (
                    "EQ observations under historical symbols ZOMATO and "
                    "ETERNAL; dates are observed source boundaries, "
                    "not independent legal validity certification."
                )
            })
            status = "Inserted"

        conn.execute(text("""
            UPDATE companies
            SET isin = :isin
            WHERE id = :company_id
        """), {"isin": isin, "company_id": COMPANY_ID})

    print("\nETERNAL ISIN VERIFICATION SUCCESS")
    print("Company: ETERNAL")
    print("ISIN:", isin)
    print("Source observations:", len(df))
    print("Historical symbols:", sorted(df["symbol"].unique()))
    print("First observed:", first_date)
    print("Last observed:", last_date)
    print("Identifier status:", status)

if __name__ == "__main__":
    main()
