import sys
sys.path.insert(0, "backend")

from sqlalchemy import text
from database import engine

FILE_NAME = (
    "backend/audit_phase2_final.py "
    "(retrospective reconciliation; not original importer log)"
)
IMPORT_TYPE = "POST_IMPORT_RECONCILIATION"

passed_checks = [
    ("COMPANY_MASTER", "54 companies and 54 unique symbols verified."),
    ("MONTHLY_SNAPSHOTS", "950 constituent observations across 19 months; 50 rows per month."),
    ("SNAPSHOT_COMPANY_MAPPING", "Zero unresolved snapshot symbols."),
    ("OBSERVATION_SPANS", "54 instruments; zero internal monthly gaps."),
    ("MEMBERSHIP_EVENTS", "Four events; zero unresolved company links."),
    ("IDENTIFIER_REGISTER", "Eight identifiers; seven ISIN records and one ticker alias; ETERNAL ISIN verified."),
    ("PRICE_COVERAGE", "19,557 prices; 54 instruments; 369 trading dates; 2025-04-01 to 2026-11-05."),
    ("INSTRUMENT_PRICE_COUNTS", "52 instruments have 369 records; TATAMOTORS has 130; TMPV has 239."),
    ("PRICE_QUALITY", "Zero null OHLC, non-positive prices, invalid OHLC relationships or negative trading statistics."),
    ("DUPLICATE_PRICES", "Zero duplicate company/date groups."),
    ("TATA_TRANSITION", "TATAMOTORS ends 2025-10-23; TMPV starts 2025-10-24."),
    ("MEMBERSHIP_DATE_SEMANTICS", "No exact effective membership periods inferred from monthly observations."),
    ("ETERNAL_HISTORICAL_IDENTITY", "Historical ZOMATO ticker and ETERNAL ISIN mapping verified.")
]

warnings = [
    ("CORPORATE_ACTION_COVERAGE",
     "Zero corporate-action records. Adjusted-price and total-return history is not established."),
    ("IMPORT_LOG_PROVENANCE",
     "This is a retrospective reconciliation record. Original historical importer execution logs were not captured."),
    ("VALIDATION_LOG_PROVENANCE",
     "Validation entries document the current reconciliation checks, not historical validation executions.")
]

with engine.begin() as conn:
    existing = conn.execute(text("""
        SELECT id
        FROM data_import_logs
        WHERE file_name = :file_name
          AND import_type = :import_type
        ORDER BY id DESC
        LIMIT 1
    """), {
        "file_name": FILE_NAME,
        "import_type": IMPORT_TYPE
    }).scalar_one_or_none()

    if existing:
        print("Reconciliation log already exists. No duplicate created.")
        print("Import log ID:", existing)
    else:
        import_id = conn.execute(text("""
            INSERT INTO data_import_logs (
                source_id, file_name, import_type,
                records_received, records_imported, records_rejected,
                status, error_message, started_at, completed_at
            ) VALUES (
                NULL, :file_name, :import_type,
                0, 0, 0, 'success',
                'Retrospective reconciliation only; not an original import execution record.',
                NOW(), NOW()
            )
        """), {
            "file_name": FILE_NAME,
            "import_type": IMPORT_TYPE
        }).lastrowid

        for rule, description in passed_checks:
            conn.execute(text("""
                INSERT INTO validation_logs (
                    import_id, severity, validation_rule, description
                ) VALUES (
                    :import_id, 'info', :rule, :description
                )
            """), {
                "import_id": import_id,
                "rule": rule,
                "description": description
            })

        for rule, description in warnings:
            conn.execute(text("""
                INSERT INTO validation_logs (
                    import_id, severity, validation_rule, description
                ) VALUES (
                    :import_id, 'warning', :rule, :description
                )
            """), {
                "import_id": import_id,
                "rule": rule,
                "description": description
            })

        print("\nRECONCILIATION LOG CREATED")
        print("Import log ID:", import_id)
        print("Informational checks:", len(passed_checks))
        print("Warnings:", len(warnings))
        print("Total validation records:", len(passed_checks) + len(warnings))

    print("\nDATABASE LOG COUNTS")
    print("Import logs:", conn.execute(
        text("SELECT COUNT(*) FROM data_import_logs")
    ).scalar_one())

    print("Validation logs:", conn.execute(
        text("SELECT COUNT(*) FROM validation_logs")
    ).scalar_one())
