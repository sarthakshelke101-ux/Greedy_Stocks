import sys
sys.path.insert(0, "backend")

from pathlib import Path
import pandas as pd
from sqlalchemy import text
from database import engine

SOURCE = Path(
    "database/processed/constituents/"
    "nifty50_membership_observation_audit_v2.csv"
)

def main():
    df = pd.read_csv(SOURCE, dtype=str).fillna("")
    required = {
        "symbol", "security_name", "first_observed_month",
        "last_observed_month", "observed_month_count",
        "internal_missing_month_count", "internal_missing_months",
        "related_event_count", "related_events", "observation_status",
        "start_date_status", "end_date_status"
    }

    if not required.issubset(df.columns):
        raise ValueError(f"Missing columns: {required - set(df.columns)}")

    if df["symbol"].duplicated().any():
        raise ValueError("Duplicate symbols in observation audit.")

    if len(df) != 54:
        raise ValueError(f"Expected 54 instruments, found {len(df)}")

    df["first_observed_month"] = pd.to_datetime(
        df["first_observed_month"] + "-01"
    ).dt.date

    df["last_observed_month"] = pd.to_datetime(
        df["last_observed_month"] + "-01"
    ).dt.date

    for col in [
        "observed_month_count", "internal_missing_month_count",
        "related_event_count"
    ]:
        df[col] = pd.to_numeric(df[col], errors="raise").astype(int)

    create_sql = """
    CREATE TABLE IF NOT EXISTS index_constituent_observation_spans (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        index_symbol VARCHAR(30) NOT NULL DEFAULT 'NIFTY 50',
        company_id INT UNSIGNED NOT NULL,
        symbol VARCHAR(30) NOT NULL,
        security_name VARCHAR(255) NOT NULL,
        first_observed_month DATE NOT NULL,
        last_observed_month DATE NOT NULL,
        observed_month_count SMALLINT UNSIGNED NOT NULL,
        internal_missing_month_count SMALLINT UNSIGNED NOT NULL,
        internal_missing_months TEXT,
        related_event_count SMALLINT UNSIGNED NOT NULL,
        related_events TEXT,
        observation_status VARCHAR(40) NOT NULL,
        start_date_status VARCHAR(60) NOT NULL,
        end_date_status VARCHAR(60) NOT NULL,
        source_name VARCHAR(150) NOT NULL,
        source_reference VARCHAR(500),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uq_observation_span (index_symbol, company_id),
        KEY idx_observation_symbol (symbol),
        KEY idx_observation_months (
            index_symbol, first_observed_month, last_observed_month
        ),
        CONSTRAINT fk_observation_span_company
            FOREIGN KEY (company_id) REFERENCES companies(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """

    with engine.begin() as conn:
        conn.execute(text(create_sql))

        companies = conn.execute(
            text("SELECT id, symbol FROM companies")
        ).mappings().all()
        company_map = {r["symbol"]: r["id"] for r in companies}

        missing = sorted(set(df["symbol"]) - set(company_map))
        if missing:
            raise ValueError(f"Companies missing from master: {missing}")

        inserted = 0
        unchanged = 0

        for r in df.to_dict("records"):
            company_id = company_map[r["symbol"]]

            params = {
                "company_id": company_id,
                "symbol": r["symbol"],
                "security_name": r["security_name"],
                "first": r["first_observed_month"],
                "last": r["last_observed_month"],
                "observed": r["observed_month_count"],
                "missing_count": r["internal_missing_month_count"],
                "missing_months": r["internal_missing_months"] or None,
                "event_count": r["related_event_count"],
                "events": r["related_events"] or None,
                "status": r["observation_status"],
                "start_status": r["start_date_status"],
                "end_status": r["end_date_status"],
                "source_name": "NIFTY 50 Monthly Constituent Reports",
                "source_reference": SOURCE.as_posix()
            }

            existing = conn.execute(
                text("""
                    SELECT first_observed_month, last_observed_month,
                           observed_month_count, internal_missing_month_count
                    FROM index_constituent_observation_spans
                    WHERE index_symbol = 'NIFTY 50'
                      AND company_id = :company_id
                """),
                params
            ).mappings().first()

            if existing:
                expected = (
                    params["first"], params["last"],
                    params["observed"], params["missing_count"]
                )
                actual = (
                    existing["first_observed_month"],
                    existing["last_observed_month"],
                    existing["observed_month_count"],
                    existing["internal_missing_month_count"]
                )
                if actual != expected:
                    raise ValueError(
                        f"Existing observation span conflicts: {r['symbol']}"
                    )
                unchanged += 1
                continue

            conn.execute(
                text("""
                    INSERT INTO index_constituent_observation_spans (
                        index_symbol, company_id, symbol, security_name,
                        first_observed_month, last_observed_month,
                        observed_month_count, internal_missing_month_count,
                        internal_missing_months, related_event_count,
                        related_events, observation_status,
                        start_date_status, end_date_status,
                        source_name, source_reference
                    ) VALUES (
                        'NIFTY 50', :company_id, :symbol, :security_name,
                        :first, :last, :observed, :missing_count,
                        :missing_months, :event_count, :events, :status,
                        :start_status, :end_status,
                        :source_name, :source_reference
                    )
                """),
                params
            )
            inserted += 1

        total = conn.execute(
            text("""
                SELECT COUNT(*) FROM index_constituent_observation_spans
                WHERE index_symbol = 'NIFTY 50'
            """)
        ).scalar_one()

        exact_periods = conn.execute(
            text("SELECT COUNT(*) FROM index_constituents")
        ).scalar_one()

    print("\nOBSERVATION SPAN IMPORT SUCCESS")
    print("-" * 45)
    print("Source instruments:", len(df))
    print("Inserted:", inserted)
    print("Already matching:", unchanged)
    print("Database observation spans:", total)
    print("Exact membership periods:", exact_periods)
    print("Internal gaps:", int(df["internal_missing_month_count"].sum()))
    print("\nObservation boundaries are NOT legal membership dates.")

if __name__ == "__main__":
    main()
