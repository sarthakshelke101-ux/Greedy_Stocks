from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import inspect, text
from backend.database import engine


TABLES = [
    "index_constituents",
    "index_membership_actions",
    "index_membership_events",
    "index_constituent_snapshots",
    "index_constituent_observation_spans",
    "companies",
    "company_identifiers",
]


def serialise(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def main():
    inspector = inspect(engine)
    report = {
        "audit": "Phase 4 historical index membership schema audit",
        "read_only": True,
        "tables": {},
    }

    with engine.connect() as conn:
        for table in TABLES:
            if not inspector.has_table(table):
                report["tables"][table] = {"exists": False}
                continue

            columns = inspector.get_columns(table)
            pk = inspector.get_pk_constraint(table)
            indexes = inspector.get_indexes(table)

            schema = {
                "exists": True,
                "columns": [
                    {
                        "name": c["name"],
                        "type": str(c["type"]),
                        "nullable": c.get("nullable"),
                    }
                    for c in columns
                ],
                "primary_key": pk.get("constrained_columns", []),
                "indexes": [
                    {
                        "name": i.get("name"),
                        "columns": i.get("column_names"),
                        "unique": i.get("unique"),
                    }
                    for i in indexes
                ],
            }

            count = conn.execute(
                text(f"SELECT COUNT(*) FROM `{table}`")
            ).scalar_one()
            schema["row_count"] = int(count)

            sample = conn.execute(
                text(f"SELECT * FROM `{table}` LIMIT 5")
            ).mappings().all()

            schema["sample_rows"] = [
                {k: serialise(v) if v is not None else None
                 for k, v in dict(row).items()}
                for row in sample
            ]

            report["tables"][table] = schema

    output = Path("reports/phase4/membership_schema_audit.json")
    output.write_text(
        json.dumps(report, indent=2, default=serialise),
        encoding="utf-8",
    )

    print("\nTABLE SUMMARY")
    for name, info in report["tables"].items():
        if not info.get("exists"):
            print(f"{name}: NOT FOUND")
            continue
        print(
            f"{name}: {info['row_count']} rows | "
            f"columns: {', '.join(c['name'] for c in info['columns'])}"
        )

    print("\nDetailed schema and sample records:", output)


if __name__ == "__main__":
    main()
