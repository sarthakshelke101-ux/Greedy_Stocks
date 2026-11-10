
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from database import engine


# =========================================================
# GREEDY STOCKS
# NIFTY 50 MEMBERSHIP EVENT IMPORTER
# =========================================================

ROOT = Path(__file__).resolve().parent.parent

EVENT_FILE = (
    ROOT
    / "database"
    / "processed"
    / "constituents"
    / "nifty50_membership_events_reconciled.csv"
)

EXPECTED_EVENTS = 4
INDEX_SYMBOL = "NIFTY 50"


# =========================================================
# 1. CREATE DATABASE TABLE
# =========================================================

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS index_membership_events (

    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    index_symbol VARCHAR(30) NOT NULL DEFAULT 'NIFTY 50',

    event_date DATE NOT NULL,

    event_type VARCHAR(40) NOT NULL,

    old_company_id INT UNSIGNED NOT NULL,

    new_company_id INT UNSIGNED NOT NULL,

    old_symbol VARCHAR(30) NOT NULL,

    new_symbol VARCHAR(30) NOT NULL,

    company_identity VARCHAR(255) DEFAULT NULL,

    source_reference VARCHAR(500) NOT NULL,

    verification_status VARCHAR(50) NOT NULL
        DEFAULT 'RECONCILED_SOURCE_REGISTER',

    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uq_membership_event (
        index_symbol,
        event_date,
        event_type,
        old_symbol,
        new_symbol
    ),

    KEY idx_membership_event_date (
        index_symbol,
        event_date
    ),

    KEY idx_membership_old_company (
        old_company_id
    ),

    KEY idx_membership_new_company (
        new_company_id
    ),

    CONSTRAINT fk_membership_event_old_company
        FOREIGN KEY (old_company_id)
        REFERENCES companies(id),

    CONSTRAINT fk_membership_event_new_company
        FOREIGN KEY (new_company_id)
        REFERENCES companies(id)

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_0900_ai_ci;
"""


def create_table():

    with engine.begin() as connection:
        connection.execute(text(CREATE_TABLE_SQL))

    print("Membership events table is ready.")


# =========================================================
# 2. LOAD AND VALIDATE EVENT FILE
# =========================================================

def load_events():

    if not EVENT_FILE.exists():
        raise FileNotFoundError(EVENT_FILE)

    df = pd.read_csv(
        EVENT_FILE,
        dtype=str,
        keep_default_na=False,
    )

    required_columns = [
        "event_date",
        "event_type",
        "old_symbol",
        "new_symbol",
        "company_identity",
        "verification",
    ]

    for column in required_columns:

        if column not in df.columns:
            raise ValueError(
                f"Missing event column: {column}"
            )

    if len(df) != EXPECTED_EVENTS:
        raise ValueError(
            f"Expected {EXPECTED_EVENTS} events, "
            f"found {len(df)}."
        )

    for column in required_columns:

        if (df[column].str.strip() == "").any():
            raise ValueError(
                f"Blank values detected in {column}."
            )

    df["event_date"] = pd.to_datetime(
        df["event_date"],
        format="%Y-%m-%d",
        errors="raise",
    ).dt.date

    allowed_types = {
        "SYMBOL_CHANGE",
        "INDEX_REPLACEMENT",
    }

    unexpected_types = set(df["event_type"]) - allowed_types

    if unexpected_types:
        raise ValueError(
            f"Unexpected event types: {unexpected_types}"
        )

    if df.duplicated(
        subset=[
            "event_date",
            "event_type",
            "old_symbol",
            "new_symbol",
        ]
    ).any():

        raise ValueError(
            "Duplicate membership events detected."
        )

    # Validate the four events expected in our reconciled register.
    expected = {
        (
            "2025-10-24",
            "SYMBOL_CHANGE",
            "TATAMOTORS",
            "TMPV",
        ),
        (
            "2025-09-30",
            "INDEX_REPLACEMENT",
            "HEROMOTOCO",
            "INDIGO",
        ),
        (
            "2025-09-30",
            "INDEX_REPLACEMENT",
            "INDUSINDBK",
            "MAXHEALTH",
        ),
        (
            "2026-09-30",
            "INDEX_REPLACEMENT",
            "WIPRO",
            "BSE",
        ),
    }

    actual = {
        (
            str(row.event_date),
            row.event_type,
            row.old_symbol,
            row.new_symbol,
        )
        for row in df.itertuples(index=False)
    }

    if actual != expected:
        raise ValueError(
            "The event register does not match the "
            "four expected reconciled events."
        )

    return df


# =========================================================
# 3. IMPORT EVENTS TRANSACTIONALLY
# =========================================================

def import_events(df):

    inserted = 0
    already_present = 0

    with engine.begin() as connection:

        # Resolve every symbol to its existing company ID.
        company_rows = connection.execute(
            text(
                """
                SELECT id, symbol
                FROM companies
                """
            )
        ).mappings().all()

        company_ids = {
            row["symbol"]: row["id"]
            for row in company_rows
        }

        required_symbols = (
            set(df["old_symbol"])
            | set(df["new_symbol"])
        )

        missing_symbols = sorted(
            required_symbols - set(company_ids)
        )

        if missing_symbols:
            raise ValueError(
                "Company records not found: "
                + ", ".join(missing_symbols)
            )

        for row in df.itertuples(index=False):

            old_id = company_ids[row.old_symbol]
            new_id = company_ids[row.new_symbol]

            existing = connection.execute(
                text(
                    """
                    SELECT
                        id,
                        old_company_id,
                        new_company_id,
                        company_identity,
                        source_reference
                    FROM index_membership_events
                    WHERE index_symbol = :index_symbol
                      AND event_date = :event_date
                      AND event_type = :event_type
                      AND old_symbol = :old_symbol
                      AND new_symbol = :new_symbol
                    """
                ),
                {
                    "index_symbol": INDEX_SYMBOL,
                    "event_date": row.event_date,
                    "event_type": row.event_type,
                    "old_symbol": row.old_symbol,
                    "new_symbol": row.new_symbol,
                },
            ).mappings().one_or_none()

            if existing:

                # Never silently accept conflicting event details.
                if (
                    existing["old_company_id"] != old_id
                    or existing["new_company_id"] != new_id
                    or existing["company_identity"]
                    != row.company_identity
                    or existing["source_reference"]
                    != row.verification
                ):
                    raise RuntimeError(
                        "Existing event conflicts with source: "
                        f"{row.old_symbol} -> {row.new_symbol}"
                    )

                already_present += 1
                continue

            connection.execute(
                text(
                    """
                    INSERT INTO index_membership_events (
                        index_symbol,
                        event_date,
                        event_type,
                        old_company_id,
                        new_company_id,
                        old_symbol,
                        new_symbol,
                        company_identity,
                        source_reference,
                        verification_status
                    )
                    VALUES (
                        :index_symbol,
                        :event_date,
                        :event_type,
                        :old_company_id,
                        :new_company_id,
                        :old_symbol,
                        :new_symbol,
                        :company_identity,
                        :source_reference,
                        'RECONCILED_SOURCE_REGISTER'
                    )
                    """
                ),
                {
                    "index_symbol": INDEX_SYMBOL,
                    "event_date": row.event_date,
                    "event_type": row.event_type,
                    "old_company_id": old_id,
                    "new_company_id": new_id,
                    "old_symbol": row.old_symbol,
                    "new_symbol": row.new_symbol,
                    "company_identity": row.company_identity,
                    "source_reference": row.verification,
                },
            )

            inserted += 1

        # Verify all expected events exist before commit.
        total = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM index_membership_events
                WHERE index_symbol = :index_symbol
                """
            ),
            {"index_symbol": INDEX_SYMBOL},
        ).scalar_one()

        if total != EXPECTED_EVENTS:
            raise RuntimeError(
                f"Expected {EXPECTED_EVENTS} events, found {total}."
            )

    return inserted, already_present


# =========================================================
# 4. POST-IMPORT VERIFICATION
# =========================================================

def verify_events():

    with engine.connect() as connection:

        rows = connection.execute(
            text(
                """
                SELECT
                    e.event_date,
                    e.event_type,
                    e.old_symbol,
                    old_c.company_name AS old_company,
                    e.new_symbol,
                    new_c.company_name AS new_company,
                    e.source_reference,
                    e.verification_status
                FROM index_membership_events e
                JOIN companies old_c
                    ON old_c.id = e.old_company_id
                JOIN companies new_c
                    ON new_c.id = e.new_company_id
                WHERE e.index_symbol = :index_symbol
                ORDER BY e.event_date, e.old_symbol
                """
            ),
            {"index_symbol": INDEX_SYMBOL},
        ).mappings().all()

    print("\n" + "=" * 70)
    print("MEMBERSHIP EVENT VERIFICATION")
    print("=" * 70)

    for row in rows:
        print(
            f"\nDate: {row['event_date']}"
            f"\nType: {row['event_type']}"
            f"\nOld: {row['old_symbol']} - {row['old_company']}"
            f"\nNew: {row['new_symbol']} - {row['new_company']}"
            f"\nSource: {row['source_reference']}"
            f"\nStatus: {row['verification_status']}"
        )

    if len(rows) != EXPECTED_EVENTS:
        raise RuntimeError(
            "Post-import event verification failed."
        )

    print("\nALL FOUR EVENTS VERIFIED IN DATABASE.")


# =========================================================
# 5. MAIN
# =========================================================

def main():

    print("=" * 70)
    print("GREEDY STOCKS - MEMBERSHIP EVENT IMPORT")
    print("=" * 70)

    # Validate source before database modifications.
    events = load_events()

    print("\nSOURCE VALIDATION PASSED")
    print(f"Events found: {len(events)}")

    # Prepare table.
    create_table()

    # Import transactionally.
    inserted, existing = import_events(events)

    print("\nIMPORT COMPLETE")
    print(f"New events inserted: {inserted}")
    print(f"Existing events reused: {existing}")

    # Verify final database records.
    verify_events()

    print("\nMEMBERSHIP EVENT IMPORT SUCCESSFUL.")


if __name__ == "__main__":
    main()
