from __future__ import annotations

import calendar
import json
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from backend.database import engine


def as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def serialise(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def month_end(value):
    value = as_date(value)
    return date(
        value.year,
        value.month,
        calendar.monthrange(value.year, value.month)[1],
    )


def active_on(interval, target):
    start = as_date(interval["effective_from"])
    end = as_date(interval["effective_to"])

    if start is not None and target < start:
        return False
    if end is not None and target > end:
        return False
    return True


def compare(snapshot_groups, intervals, symbol_to_company, convention):
    results = []

    for key, snapshot_symbols in sorted(snapshot_groups.items()):
        index_symbol, report_month = key
        target = (
            as_date(report_month)
            if convention == "month_start"
            else month_end(report_month)
        )

        expected_ids = {
            row["company_id"]
            for row in intervals
            if row["index_symbol"] == index_symbol
            and row["company_id"] is not None
            and active_on(row, target)
        }

        observed_ids = set()
        unresolved = []

        for symbol in snapshot_symbols:
            company_id = symbol_to_company.get(symbol.upper())
            if company_id is None:
                unresolved.append(symbol)
            else:
                observed_ids.add(company_id)

        missing = sorted(expected_ids - observed_ids)
        unexpected = sorted(observed_ids - expected_ids)

        results.append({
            "index_symbol": index_symbol,
            "report_month": str(report_month),
            "comparison_date": target.isoformat(),
            "snapshot_symbol_count": len(snapshot_symbols),
            "expected_interval_company_count": len(expected_ids),
            "matched_company_count": len(expected_ids & observed_ids),
            "missing_from_snapshot_company_ids": missing,
            "unexpected_in_snapshot_company_ids": unexpected,
            "unresolved_snapshot_symbols": sorted(unresolved),
            "exact_match": (
                not missing and not unexpected and not unresolved
            ),
        })

    return results


def main():
    with engine.connect() as conn:
        intervals = conn.execute(text("""
            SELECT id, index_symbol, company_id,
                   effective_from, effective_to, source_name
            FROM index_constituents
            ORDER BY index_symbol, effective_from
        """)).mappings().all()

        snapshots = conn.execute(text("""
            SELECT index_symbol, report_month, symbol,
                   security_name, source_archive, source_csv
            FROM index_constituent_snapshots
            ORDER BY index_symbol, report_month, symbol
        """)).mappings().all()

        companies = conn.execute(text("""
            SELECT id, symbol FROM companies
        """)).mappings().all()

        identifiers = conn.execute(text("""
            SELECT company_id, identifier_type, identifier_value,
                   valid_from, valid_to
            FROM company_identifiers
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

    symbol_to_company = {}

    for row in companies:
        if row["symbol"]:
            symbol_to_company[str(row["symbol"]).strip().upper()] = row["id"]

    for row in identifiers:
        kind = str(row["identifier_type"]).strip().upper()
        if kind in {"SYMBOL", "TICKER", "TRADING_SYMBOL"}:
            if row["identifier_value"]:
                symbol_to_company[
                    str(row["identifier_value"]).strip().upper()
                ] = row["company_id"]

    snapshot_groups = defaultdict(set)
    for row in snapshots:
        snapshot_groups[
            (row["index_symbol"], row["report_month"])
        ].add(str(row["symbol"]).strip())

    interval_rows = [dict(x) for x in intervals]

    start_results = compare(
        snapshot_groups, interval_rows, symbol_to_company, "month_start"
    )
    end_results = compare(
        snapshot_groups, interval_rows, symbol_to_company, "month_end"
    )

    def summary(rows):
        return {
            "months_compared": len(rows),
            "exact_matches": sum(x["exact_match"] for x in rows),
            "months_with_mismatches": sum(not x["exact_match"] for x in rows),
            "total_missing_members": sum(
                len(x["missing_from_snapshot_company_ids"]) for x in rows
            ),
            "total_unexpected_members": sum(
                len(x["unexpected_in_snapshot_company_ids"]) for x in rows
            ),
            "total_unresolved_symbols": sum(
                len(x["unresolved_snapshot_symbols"]) for x in rows
            ),
        }

    result = {
        "audit": "GREEDY STOCKS snapshot vs effective interval reconciliation",
        "read_only": True,
        "methodology": [
            "Snapshot symbols are mapped to company IDs using current symbols and explicitly typed symbol identifiers.",
            "Membership intervals are evaluated inclusively at their start and end dates.",
            "Both month-start and month-end conventions are tested because report-month date semantics must be established from source archives.",
            "A mismatch is a reconciliation finding, not automatic proof of incorrect source data.",
        ],
        "summary": {
            "month_start": summary(start_results),
            "month_end": summary(end_results),
        },
        "month_start_results": start_results,
        "month_end_results": end_results,
        "membership_actions": [
            {k: serialise(v) for k, v in dict(x).items()}
            for x in actions
        ],
        "membership_events": [
            {k: serialise(v) for k, v in dict(x).items()}
            for x in events
        ],
        "intervals": [
            {k: serialise(v) for k, v in row.items()}
            for row in interval_rows
        ],
    }

    output = Path(
        "reports/phase4/snapshot_interval_reconciliation.json"
    )
    output.write_text(
        json.dumps(result, indent=2, default=serialise),
        encoding="utf-8",
    )

    print("\nRECONCILIATION SUMMARY")
    print(json.dumps(result["summary"], indent=2))

    print("\nMONTH-START COMPARISON")
    for row in start_results:
        print(
            row["report_month"],
            "match=" + str(row["exact_match"]),
            "missing=" + str(len(row["missing_from_snapshot_company_ids"])),
            "unexpected=" + str(len(row["unexpected_in_snapshot_company_ids"])),
        )

    print("\nMONTH-END COMPARISON")
    for row in end_results:
        print(
            row["report_month"],
            "match=" + str(row["exact_match"]),
            "missing=" + str(len(row["missing_from_snapshot_company_ids"])),
            "unexpected=" + str(len(row["unexpected_in_snapshot_company_ids"])),
        )

    print("\nDetailed reconciliation:", output)


if __name__ == "__main__":
    main()
