from __future__ import annotations

import json
import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from backend.database import engine


SYMBOL_TYPES = {"SYMBOL", "TICKER", "TRADING_SYMBOL"}


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
        value.year, value.month,
        calendar.monthrange(value.year, value.month)[1]
    )


def valid_on(row, target):
    start = as_date(row.get("valid_from"))
    end = as_date(row.get("valid_to"))
    return (start is None or start <= target) and (
        end is None or target <= end
    )


def interval_active(row, target):
    start = as_date(row["effective_from"])
    end = as_date(row["effective_to"])
    return (start is None or start <= target) and (
        end is None or target <= end
    )


def main():
    prior_path = Path(
        "reports/phase4/snapshot_interval_reconciliation.json"
    )
    if not prior_path.exists():
        raise FileNotFoundError(prior_path)

    prior = json.loads(prior_path.read_text(encoding="utf-8"))

    with engine.connect() as conn:
        snapshots = [
            dict(x) for x in conn.execute(text("""
                SELECT index_symbol, report_month, symbol, security_name,
                       source_archive, source_csv
                FROM index_constituent_snapshots
                ORDER BY report_month, symbol
            """)).mappings().all()
        ]

        intervals = [
            dict(x) for x in conn.execute(text("""
                SELECT id, index_symbol, company_id, effective_from,
                       effective_to, source_name
                FROM index_constituents
                ORDER BY effective_from
            """)).mappings().all()
        ]

        companies = [
            dict(x) for x in conn.execute(text("""
                SELECT id, symbol, company_name, isin, is_active
                FROM companies
            """)).mappings().all()
        ]

        identifiers = [
            dict(x) for x in conn.execute(text("""
                SELECT company_id, identifier_type, identifier_value,
                       valid_from, valid_to, source_name, source_reference
                FROM company_identifiers
                ORDER BY identifier_value, valid_from
            """)).mappings().all()
        ]

        actions = [
            dict(x) for x in conn.execute(text("""
                SELECT id, index_symbol, event_date, company_id, symbol,
                       action, source_reference, verification_status
                FROM index_membership_actions
                ORDER BY event_date
            """)).mappings().all()
        ]

        events = [
            dict(x) for x in conn.execute(text("""
                SELECT id, index_symbol, event_date, event_type,
                       old_company_id, new_company_id, old_symbol,
                       new_symbol, company_identity, source_reference,
                       verification_status
                FROM index_membership_events
                ORDER BY event_date
            """)).mappings().all()
        ]

    for row in snapshots + intervals + companies + identifiers + actions + events:
        for key, value in list(row.items()):
            if isinstance(value, (date, datetime)):
                row[key] = value.isoformat()

    company_by_id = {x["id"]: x for x in companies}

    identifiers_by_symbol = defaultdict(list)
    for row in identifiers:
        if str(row["identifier_type"]).strip().upper() in SYMBOL_TYPES:
            symbol = str(row["identifier_value"] or "").strip().upper()
            if symbol:
                identifiers_by_symbol[symbol].append(row)

    current_by_symbol = defaultdict(list)
    for row in companies:
        symbol = str(row["symbol"] or "").strip().upper()
        if symbol:
            current_by_symbol[symbol].append(row)

    snapshot_groups = defaultdict(list)
    for row in snapshots:
        key = (row["index_symbol"], row["report_month"])
        snapshot_groups[key].append(row)

    def resolve_symbol(symbol, target):
        symbol = str(symbol).strip().upper()
        candidates = set()

        for item in identifiers_by_symbol.get(symbol, []):
            if valid_on(item, target):
                candidates.add(item["company_id"])

        # Current company symbol is only a fallback when no valid
        # historical identifier record resolves this symbol.
        if not candidates:
            candidates.update(
                x["id"] for x in current_by_symbol.get(symbol, [])
            )

        return sorted(candidates)

    def describe_company(company_id):
        row = company_by_id.get(company_id)
        if not row:
            return {"company_id": company_id, "company_found": False}
        return {
            "company_id": company_id,
            "current_symbol": row["symbol"],
            "company_name": row["company_name"],
            "isin": row["isin"],
            "is_active": row["is_active"],
        }

    diagnostics = []

    for (index_symbol, report_month), snapshot_rows in sorted(snapshot_groups.items()):
        report_date = as_date(report_month)
        for convention, target in (
            ("month_start", report_date),
            ("month_end", month_end(report_date)),
        ):
            expected_ids = {
                x["company_id"] for x in intervals
                if x["index_symbol"] == index_symbol
                and x["company_id"] is not None
                and interval_active(x, target)
            }

            resolved = {}
            ambiguous = []
            unresolved = []

            for snap in snapshot_rows:
                symbol = str(snap["symbol"]).strip().upper()
                candidates = resolve_symbol(symbol, target)

                if len(candidates) == 1:
                    resolved[symbol] = candidates[0]
                elif len(candidates) == 0:
                    unresolved.append({
                        "symbol": symbol,
                        "security_name": snap["security_name"],
                    })
                else:
                    ambiguous.append({
                        "symbol": symbol,
                        "security_name": snap["security_name"],
                        "candidate_company_ids": candidates,
                        "candidate_companies": [
                            describe_company(x) for x in candidates
                        ],
                    })

            observed_ids = set(resolved.values())
            missing_ids = sorted(expected_ids - observed_ids)
            unexpected_ids = sorted(observed_ids - expected_ids)

            # Only emit months where the earlier naive audit found
            # mismatches, or where date-aware resolution finds ambiguity.
            prior_key = (
                "month_start_results" if convention == "month_start"
                else "month_end_results"
            )
            prior_rows = {
                (x["index_symbol"], x["report_month"]): x
                for x in prior[prior_key]
            }
            prior_row = prior_rows.get((index_symbol, str(report_month)))

            if (prior_row and not prior_row["exact_match"]) or ambiguous or unresolved:
                window_start = target - timedelta(days=45)
                window_end = target + timedelta(days=45)

                nearby_actions = [
                    x for x in actions
                    if x["index_symbol"] == index_symbol
                    and window_start <= as_date(x["event_date"]) <= window_end
                ]

                nearby_events = [
                    x for x in events
                    if x["index_symbol"] == index_symbol
                    and window_start <= as_date(x["event_date"]) <= window_end
                ]

                diagnostics.append({
                    "index_symbol": index_symbol,
                    "report_month": str(report_month),
                    "convention": convention,
                    "comparison_date": target.isoformat(),
                    "snapshot_symbols": [
                        {
                            "symbol": str(x["symbol"]).strip().upper(),
                            "security_name": x["security_name"],
                            "resolved_company_id": resolved.get(
                                str(x["symbol"]).strip().upper()
                            ),
                        }
                        for x in snapshot_rows
                    ],
                    "expected_interval_companies_missing_from_snapshot": [
                        describe_company(x) for x in missing_ids
                    ],
                    "snapshot_companies_unexpected_in_intervals": [
                        describe_company(x) for x in unexpected_ids
                    ],
                    "ambiguous_symbols": ambiguous,
                    "unresolved_symbols": unresolved,
                    "nearby_actions": [
                        {k: serialise(v) for k, v in x.items()}
                        for x in nearby_actions
                    ],
                    "nearby_events": [
                        {k: serialise(v) for k, v in x.items()}
                        for x in nearby_events
                    ],
                    "source_files": [
                        {
                            "source_archive": x["source_archive"],
                            "source_csv": x["source_csv"],
                        }
                        for x in snapshot_rows
                    ],
                })

    # Detect reused historical ticker values with overlapping validity.
    identifier_collisions = []
    for symbol, rows in identifiers_by_symbol.items():
        for i, left in enumerate(rows):
            for right in rows[i + 1:]:
                if left["company_id"] == right["company_id"]:
                    continue

                left_start = as_date(left["valid_from"]) or date.min
                left_end = as_date(left["valid_to"]) or date.max
                right_start = as_date(right["valid_from"]) or date.min
                right_end = as_date(right["valid_to"]) or date.max

                if max(left_start, right_start) <= min(left_end, right_end):
                    identifier_collisions.append({
                        "symbol": symbol,
                        "left_company": describe_company(left["company_id"]),
                        "right_company": describe_company(right["company_id"]),
                        "left_valid_from": left["valid_from"],
                        "left_valid_to": left["valid_to"],
                        "right_valid_from": right["valid_from"],
                        "right_valid_to": right["valid_to"],
                    })

    result = {
        "audit": "Phase 4 date-aware membership mismatch diagnostics",
        "read_only": True,
        "diagnostic_month_convention_cases": len(diagnostics),
        "historical_symbol_identifier_collisions": len(identifier_collisions),
        "identifier_collisions": identifier_collisions,
        "diagnostics": diagnostics,
        "methodology": [
            "Historical symbol identifiers are resolved using validity dates.",
            "Current company symbols are used only as fallback when no valid historical identifier resolves the ticker.",
            "Ambiguous mappings are not silently assigned.",
            "Membership intervals use inclusive effective dates.",
            "This is a diagnostic, not an automatic membership correction.",
        ],
    }

    output = Path(
        "reports/phase4/membership_mismatch_diagnostics.json"
    )
    output.write_text(
        json.dumps(result, indent=2, default=serialise),
        encoding="utf-8",
    )

    print("\nDATE-AWARE DIAGNOSTIC SUMMARY")
    print("Mismatch cases inspected:", len(diagnostics))
    print("Historical ticker collisions:", len(identifier_collisions))

    for row in diagnostics:
        print(
            f"\n{row['report_month']} {row['convention']} "
            f"on {row['comparison_date']}"
        )
        print("  Missing:", [
            x.get("current_symbol") for x in
            row["expected_interval_companies_missing_from_snapshot"]
        ])
        print("  Unexpected:", [
            x.get("current_symbol") for x in
            row["snapshot_companies_unexpected_in_intervals"]
        ])
        print("  Ambiguous:", [
            x["symbol"] for x in row["ambiguous_symbols"]
        ])
        print("  Unresolved:", [
            x["symbol"] for x in row["unresolved_symbols"]
        ])
        print("  Nearby actions:", len(row["nearby_actions"]))
        print("  Nearby events:", len(row["nearby_events"]))

    print("\nDetailed report:", output)


if __name__ == "__main__":
    main()
