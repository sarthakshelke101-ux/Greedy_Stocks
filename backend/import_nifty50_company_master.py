
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from database import engine


# =========================================================
# GREEDY STOCKS
# NIFTY 50 COMPANY MASTER IMPORTER
# =========================================================

ROOT = Path(__file__).resolve().parent.parent

CONSTITUENT_DIR = (
    ROOT / "database" / "processed" / "constituents"
)

COMPANY_FILE = (
    CONSTITUENT_DIR / "nifty50_company_master_v2.csv"
)

SECTOR_FILE = (
    CONSTITUENT_DIR / "nifty50_sector_review.csv"
)

EXPECTED_COMPANIES = 54
EXPECTED_SOURCE_INDUSTRIES = 36
EXPECTED_NORMALIZED_SECTORS = 35


# =========================================================
# 1. LOAD AND VALIDATE SOURCE FILES
# =========================================================

def load_and_validate_files():

    if not COMPANY_FILE.exists():
        raise FileNotFoundError(
            f"Company master not found: {COMPANY_FILE}"
        )

    if not SECTOR_FILE.exists():
        raise FileNotFoundError(
            f"Sector review not found: {SECTOR_FILE}"
        )

    companies = pd.read_csv(
        COMPANY_FILE,
        dtype=str,
        keep_default_na=False,
    )

    sectors = pd.read_csv(
        SECTOR_FILE,
        dtype=str,
        keep_default_na=False,
    )

    required_company_columns = [
        "historical_symbol",
        "canonical_symbol",
        "company_identity",
        "mapping_type",
        "source_industry",
        "price_history_adjustment_required",
    ]

    required_sector_columns = [
        "source_industry",
        "normalized_sector",
        "review_status",
    ]

    for column in required_company_columns:

        if column not in companies.columns:
            raise ValueError(
                f"Missing company master column: {column}"
            )

    for column in required_sector_columns:

        if column not in sectors.columns:
            raise ValueError(
                f"Missing sector review column: {column}"
            )

    # -----------------------------------------------------
    # Company master validation
    # -----------------------------------------------------

    if len(companies) != EXPECTED_COMPANIES:
        raise ValueError(
            f"Expected {EXPECTED_COMPANIES} companies, "
            f"found {len(companies)}."
        )

    if companies["historical_symbol"].duplicated().any():
        raise ValueError(
            "Duplicate historical symbols detected."
        )

    if companies["canonical_symbol"].duplicated().any():
        raise ValueError(
            "Duplicate canonical symbols detected."
        )

    required_company_values = [
        "historical_symbol",
        "canonical_symbol",
        "company_identity",
        "mapping_type",
        "source_industry",
    ]

    for column in required_company_values:

        if (companies[column].str.strip() == "").any():
            raise ValueError(
                f"Blank values found in {column}."
            )

    if (
        companies["source_industry"].nunique()
        != EXPECTED_SOURCE_INDUSTRIES
    ):
        raise ValueError(
            "Unexpected number of source industry labels."
        )

    # -----------------------------------------------------
    # Sector review validation
    # -----------------------------------------------------

    if sectors["source_industry"].duplicated().any():
        raise ValueError(
            "Duplicate source industry keys in sector review."
        )

    if (
        sectors["source_industry"].nunique()
        != EXPECTED_SOURCE_INDUSTRIES
    ):
        raise ValueError(
            "Sector review does not contain all expected "
            "source industry labels."
        )

    if (
        sectors["normalized_sector"].nunique()
        != EXPECTED_NORMALIZED_SECTORS
    ):
        raise ValueError(
            "Unexpected number of normalized sectors."
        )

    if (sectors["review_status"] == "PENDING").any():
        raise ValueError(
            "Pending sector reviews exist. Import stopped."
        )

    allowed_statuses = {
        "PRESERVED_SOURCE_LABEL",
        "APPROVED_COSMETIC_NORMALIZATION",
    }

    unexpected_statuses = (
        set(sectors["review_status"])
        - allowed_statuses
    )

    if unexpected_statuses:
        raise ValueError(
            f"Unexpected review statuses: {unexpected_statuses}"
        )

    for column in ["source_industry", "normalized_sector"]:

        if (sectors[column].str.strip() == "").any():
            raise ValueError(
                f"Blank values found in sector column {column}."
            )

    # -----------------------------------------------------
    # Build exact source industry -> normalized sector map
    # -----------------------------------------------------

    sector_mapping = dict(
        zip(
            sectors["source_industry"],
            sectors["normalized_sector"],
        )
    )

    companies["normalized_sector"] = (
        companies["source_industry"].map(sector_mapping)
    )

    if companies["normalized_sector"].isna().any():

        missing = (
            companies.loc[
                companies["normalized_sector"].isna(),
                "source_industry",
            ]
            .unique()
            .tolist()
        )

        raise ValueError(
            f"Unmapped source industries: {missing}"
        )

    # -----------------------------------------------------
    # Tata Motors identity validation
    # -----------------------------------------------------

    tata = companies[
        companies["historical_symbol"].isin(
            ["TATAMOTORS", "TMPV"]
        )
    ]

    tata_mapping = dict(
        zip(
            tata["historical_symbol"],
            tata["mapping_type"],
        )
    )

    if len(tata) != 2:
        raise ValueError(
            "Expected exactly two separate Tata Motors identities."
        )

    if (
        tata_mapping.get("TATAMOTORS")
        != "PRE_DEMERGER_INSTRUMENT"
    ):
        raise ValueError(
            "TATAMOTORS pre-demerger identity is incorrect."
        )

    if (
        tata_mapping.get("TMPV")
        != "POST_DEMERGER_INSTRUMENT"
    ):
        raise ValueError(
            "TMPV post-demerger identity is incorrect."
        )

    # TATAMOTORS historical adjustment is unresolved.
    tata_old = tata[
        tata["historical_symbol"] == "TATAMOTORS"
    ].iloc[0]

    if (
        tata_old["price_history_adjustment_required"]
        != "YES"
    ):
        raise ValueError(
            "TATAMOTORS must retain its adjustment-required flag."
        )

    return companies, sectors


# =========================================================
# 2. IMPORT SECTORS AND COMPANIES TRANSACTIONALLY
# =========================================================

def import_master(companies, sectors):

    inserted_sector_count = 0
    inserted_company_count = 0

    with engine.begin() as connection:

        # -------------------------------------------------
        # Read existing sectors
        # -------------------------------------------------

        existing_sector_rows = connection.execute(
            text(
                """
                SELECT id, name
                FROM sectors
                """
            )
        ).mappings().all()

        sector_ids = {
            row["name"]: row["id"]
            for row in existing_sector_rows
        }

        required_sector_names = sorted(
            sectors["normalized_sector"].unique().tolist()
        )

        # -------------------------------------------------
        # Insert missing sectors, reuse exact matches
        # -------------------------------------------------

        for sector_name in required_sector_names:

            if sector_name in sector_ids:
                continue

            result = connection.execute(
                text(
                    """
                    INSERT INTO sectors (name)
                    VALUES (:name)
                    """
                ),
                {
                    "name": sector_name,
                },
            )

            sector_ids[sector_name] = result.lastrowid

            inserted_sector_count += 1

        # -------------------------------------------------
        # Detect existing company conflicts
        # -------------------------------------------------

        existing_company_symbols = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT symbol
                    FROM companies
                    """
                )
            ).all()
        }

        incoming_symbols = set(
            companies["canonical_symbol"].tolist()
        )

        conflicts = sorted(
            incoming_symbols.intersection(
                existing_company_symbols
            )
        )

        if conflicts:
            raise RuntimeError(
                "Import stopped. These company symbols "
                "already exist: "
                + ", ".join(conflicts)
                + ". Transaction rolled back."
            )

        # -------------------------------------------------
        # Insert companies
        # -------------------------------------------------

        for _, row in companies.iterrows():

            sector_name = row["normalized_sector"]

            if sector_name not in sector_ids:
                raise RuntimeError(
                    f"Missing database sector: {sector_name}"
                )

            # is_active represents current instrument status,
            # NOT NIFTY 50 index membership.
            #
            # The pre-demerger TATAMOTORS instrument is retained
            # as an inactive historical identity.

            is_active = (
                0
                if row["mapping_type"]
                == "PRE_DEMERGER_INSTRUMENT"
                else 1
            )

            connection.execute(
                text(
                    """
                    INSERT INTO companies (
                        symbol,
                        company_name,
                        sector_id,
                        exchange,
                        is_active
                    )
                    VALUES (
                        :symbol,
                        :company_name,
                        :sector_id,
                        'NSE',
                        :is_active
                    )
                    """
                ),
                {
                    "symbol": row["canonical_symbol"],
                    "company_name": row["company_identity"],
                    "sector_id": sector_ids[sector_name],
                    "is_active": is_active,
                },
            )

            inserted_company_count += 1

        # -------------------------------------------------
        # Verify inserted records before commit
        # -------------------------------------------------

        for symbol in incoming_symbols:

            verified_row = connection.execute(
                text(
                    """
                    SELECT
                        c.symbol,
                        s.id AS sector_id
                    FROM companies c
                    LEFT JOIN sectors s
                        ON s.id = c.sector_id
                    WHERE c.symbol = :symbol
                    """
                ),
                {
                    "symbol": symbol,
                },
            ).mappings().one_or_none()

            if verified_row is None:
                raise RuntimeError(
                    f"Verification failed for {symbol}."
                )

            if verified_row["sector_id"] is None:
                raise RuntimeError(
                    f"Missing sector relationship for {symbol}."
                )

        if inserted_company_count != EXPECTED_COMPANIES:
            raise RuntimeError(
                f"Expected {EXPECTED_COMPANIES} inserted companies, "
                f"got {inserted_company_count}."
            )

    # The transaction commits only after all checks pass.

    return inserted_sector_count, inserted_company_count


# =========================================================
# 3. VERIFY DATABASE AFTER IMPORT
# =========================================================

def verify_import():

    with engine.connect() as connection:

        company_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM companies
                """
            )
        ).scalar_one()

        sector_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM sectors
                """
            )
        ).scalar_one()

        missing_sector_links = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM companies c
                LEFT JOIN sectors s
                    ON s.id = c.sector_id
                WHERE s.id IS NULL
                """
            )
        ).scalar_one()

        tata_rows = connection.execute(
            text(
                """
                SELECT
                    c.symbol,
                    c.company_name,
                    c.is_active,
                    s.name AS sector
                FROM companies c
                LEFT JOIN sectors s
                    ON s.id = c.sector_id
                WHERE c.symbol IN (
                    'TATAMOTORS',
                    'TMPV'
                )
                ORDER BY c.symbol
                """
            )
        ).mappings().all()

        imported_symbols = connection.execute(
            text(
                """
                SELECT symbol
                FROM companies
                ORDER BY symbol
                """
            )
        ).scalars().all()

    print("\n" + "=" * 65)
    print("DATABASE VERIFICATION")
    print("=" * 65)

    print(f"Total companies: {company_count}")
    print(f"Total sectors: {sector_count}")
    print(f"Missing sector links: {missing_sector_links}")

    print("\nTATA MOTORS IDENTITY CHECK")

    for row in tata_rows:
        print(
            f"{row['symbol']} | "
            f"{row['company_name']} | "
            f"Active: {row['is_active']} | "
            f"Sector: {row['sector']}"
        )

    if missing_sector_links != 0:
        raise RuntimeError(
            "Some companies have missing sector relationships."
        )

    if len(tata_rows) != 2:
        raise RuntimeError(
            "Tata Motors identity verification failed."
        )

    if len(imported_symbols) != EXPECTED_COMPANIES:
        raise RuntimeError(
            "Unexpected company count after import."
        )

    print("\nDATABASE VERIFICATION PASSED")


# =========================================================
# 4. MAIN
# =========================================================

def main():

    print("=" * 65)
    print("GREEDY STOCKS")
    print("NIFTY 50 COMPANY MASTER IMPORT")
    print("=" * 65)

    # Step 1: Validate source files before database changes.
    companies, sectors = load_and_validate_files()

    print("\nPREFLIGHT VALIDATION PASSED")
    print(f"Historical instruments: {len(companies)}")
    print(
        "Source industry labels:",
        companies["source_industry"].nunique(),
    )
    print(
        "Normalized sectors:",
        sectors["normalized_sector"].nunique(),
    )
    print("Pending sector reviews: 0")
    print("Tata Motors identities: separate")

    # Step 2: Import inside a single database transaction.
    print("\nStarting database transaction...")

    inserted_sectors, inserted_companies = import_master(
        companies,
        sectors,
    )

    print("\nIMPORT COMMITTED")
    print(f"New sectors inserted: {inserted_sectors}")
    print(f"New companies inserted: {inserted_companies}")

    # Step 3: Verify committed database state.
    verify_import()

    print("\n" + "=" * 65)
    print("COMPANY MASTER IMPORT COMPLETE")
    print("=" * 65)


if __name__ == "__main__":
    main()
