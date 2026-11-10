from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
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
    return value


def clean(rows):
    return [
        {k: serialise(v) for k, v in dict(row).items()}
        for row in rows
    ]


def main():
    result = {
        "audit": "GREEDY STOCKS Phase 4 membership integrity",
        "read_only": True,
        "findings": {},
    }

    with engine.connect() as conn:
        tables = set(
            conn.execute(text("SHOW TABLES")).scalars().all()
        )

        missing = [t for t in TABLES if t not in tables]
        if missing:
            raise RuntimeError(f"Required tables missing: {missing}")

        intervals = conn.execute(text("""
            SELECT id, index_symbol, company_id,
                   effective_from, effective_to, source_name
            FROM index_constituents
            ORDER BY index_symbol, company_id, effective_from
        """)).mappings().all()

        actions = conn.execute(text("""
            SELECT id, index_symbol, event_date, company_id,
                   symbol, action, source_reference,
                   verification_status
            FROM index_membership_actions
            ORDER BY event_date, id
        """)).mappings().all()

        events = conn.execute(text("""
            SELECT id, index_symbol, event_date, event_type,
                   old_company_id, new_company_id,
                   old_symbol, new_symbol, company_identity,
                   source_reference, verification_status
            FROM index_membership_events
            ORDER BY event_date, id
        """)).mappings().all()

        spans = conn.execute(text("""
            SELECT id, index_symbol, company_id, symbol,
                   first_observed_month, last_observed_month,
                   observed_month_count, internal_missing_month_count,
                   internal_missing_months, related_event_count,
                   observation_status, start_date_status,
                   end_date_status, source_name, source_reference
            FROM index_constituent_observation_spans
            ORDER BY symbol
        """)).mappings().all()

        snapshots = conn.execute(text("""
            SELECT report_month, symbol, COUNT(*) AS rows_for_symbol,
                   MAX(security_name) AS security_name
            FROM index_constituent_snapshots
            GROUP BY report_month, symbol
            ORDER BY report_month, symbol
        """)).mappings().all()

        companies = conn.execute(text("""
            SELECT id, symbol, company_name, isin, is_active
            FROM companies
        """)).mappings().all()

        identifiers = conn.execute(text("""
            SELECT company_id, identifier_type, identifier_value,
                   valid_from, valid_to, source_name, source_reference
            FROM company_identifiers
            ORDER BY company_id, valid_from
        """)).mappings().all()

        interval_rows = clean(intervals)
        action_rows = clean(actions)
        event_rows = clean(events)
        span_rows = clean(spans)
        snapshot_rows = clean(snapshots)
        company_rows = clean(companies)
        identifier_rows = clean(identifiers)

    # 1. Interval validation and overlaps.
    invalid_intervals = []
    by_company = defaultdict(list)

    for row in interval_rows:
        start = row["effective_from"]
        end = row["effective_to"]

        if start and end and end < start:
            invalid_intervals.append(row)

        by_company[(row["index_symbol"], row["company_id"])].append(row)

    overlaps = []
    for key, rows in by_company.items():
        rows.sort(key=lambda x: x["effective_from"] or "")
        for previous, current in zip(rows, rows[1:]):
            prev_end = previous["effective_to"]
            curr_start = current["effective_from"]

            if prev_end is None or (
                curr_start is not None and curr_start <= prev_end
            ):
                overlaps.append({
                    "index_symbol": key[0],
                    "company_id": key[1],
                    "previous_interval_id": previous["id"],
                    "current_interval_id": current["id"],
                    "previous_end": prev_end,
                    "current_start": curr_start,
                })

    # 2. Evidence and verification checks.
    action_status = Counter(
        str(x["verification_status"]) for x in action_rows
    )
    event_status = Counter(
        str(x["verification_status"]) for x in event_rows
    )

    actions_missing_reference = [
        x for x in action_rows if not x["source_reference"]
    ]
    events_missing_reference = [
        x for x in event_rows if not x["source_reference"]
    ]

    # 3. Observation-span checks.
    spans_with_internal_gaps = [
        x for x in span_rows
        if int(x["internal_missing_month_count"] or 0) > 0
    ]
    spans_without_reference = [
        x for x in span_rows if not x["source_reference"]
    ]

    # 4. Snapshot symbol linkage to current and historical identifiers.
    current_symbols = {
        str(x["symbol"]).strip().upper(): x["id"]
        for x in company_rows if x["symbol"]
    }

    identifier_symbols = {
        str(x["identifier_value"]).strip().upper(): x["company_id"]
        for x in identifier_rows
        if str(x["identifier_type"]).strip().upper()
        in {"SYMBOL", "TICKER", "TRADING_SYMBOL"}
        and x["identifier_value"]
    }

    unresolved_snapshot_symbols = []
    for row in snapshot_rows:
        symbol = str(row["symbol"]).strip().upper()
        if symbol not in current_symbols and symbol not in identifier_symbols:
            unresolved_snapshot_symbols.append(row)

    # 5. Snapshot monthly coverage.
    snapshot_months = sorted({
        x["report_month"] for x in snapshot_rows
        if x["report_month"]
    })

    month_symbol_counts = Counter(
        x["report_month"] for x in snapshot_rows
    )

    # 6. Membership/action/event relationship diagnostics.
    interval_company_ids = {
        x["company_id"] for x in interval_rows
        if x["company_id"] is not None
    }

    action_company_ids = {
        x["company_id"] for x in action_rows
        if x["company_id"] is not None
    }

    event_company_ids = {
        company_id
        for x in event_rows
        for company_id in (x["old_company_id"], x["new_company_id"])
        if company_id is not None
    }

    result["summary"] = {
        "interval_count": len(interval_rows),
        "action_count": len(action_rows),
        "event_count": len(event_rows),
        "observation_span_count": len(span_rows),
        "snapshot_month_symbol_pairs": len(snapshot_rows),
        "snapshot_months": len(snapshot_months),
        "company_count": len(company_rows),
        "identifier_count": len(identifier_rows),
        "invalid_intervals": len(invalid_intervals),
        "overlapping_intervals": len(overlaps),
        "actions_missing_source_reference": len(actions_missing_reference),
        "events_missing_source_reference": len(events_missing_reference),
        "spans_with_internal_gaps": len(spans_with_internal_gaps),
        "spans_missing_source_reference": len(spans_without_reference),
        "unresolved_snapshot_symbol_pairs": len(unresolved_snapshot_symbols),
    }

    result["findings"] = {
        "invalid_intervals": invalid_intervals,
        "overlapping_intervals": overlaps,
        "action_verification_status_counts": dict(action_status),
        "event_verification_status_counts": dict(event_status),
        "actions_missing_source_reference": actions_missing_reference,
        "events_missing_source_reference": events_missing_reference,
        "spans_with_internal_gaps": spans_with_internal_gaps,
        "spans_missing_source_reference": spans_without_reference,
        "unresolved_snapshot_symbols": unresolved_snapshot_symbols,
        "snapshot_month_symbol_counts": [
            {"month": month, "symbol_pairs": month_symbol_counts[month]}
            for month in snapshot_months
        ],
        "action_company_ids_without_interval": sorted(
            action_company_ids - interval_company_ids
        ),
        "event_company_ids_without_interval": sorted(
            event_company_ids - interval_company_ids
        ),
    }

    result["methodology_notes"] = [
        "Overlapping intervals are flagged for review, not automatically treated as errors.",
        "Actions and events without interval matches may represent valid historical transitions.",
        "Snapshot symbols are checked against current symbols and explicitly typed historical identifiers only.",
        "A missing source reference is an evidence gap, not proof that an event is false.",
        "This audit does not certify point-in-time index membership or remove survivorship bias.",
    ]

    output = Path("reports/phase4/membership_integrity_audit.json")
    output.write_text(
        json.dumps(result, indent=2, default=serialise),
        encoding="utf-8",
    )

    print("\nMEMBERSHIP INTEGRITY SUMMARY")
    print(json.dumps(result["summary"], indent=2))

    print("\nACTION VERIFICATION STATUS")
    print(json.dumps(dict(action_status), indent=2))

    print("\nEVENT VERIFICATION STATUS")
    print(json.dumps(dict(event_status), indent=2))

    print("\nSNAPSHOT MONTHS")
    for month in snapshot_months:
        print(f"{month}: {month_symbol_counts[month]} symbol pairs")

    print("\nDetailed report:", output)


if __name__ == "__main__":
    main()
