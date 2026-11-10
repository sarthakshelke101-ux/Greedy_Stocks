"""Read-only historical price coverage audit and certification.

Important:
- A 10-year date span does not prove complete daily observations.
- No missing prices are synthesized or forward-filled.
- Historical coverage is assessed per company.
- Source provenance and quality findings are reported separately.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any


def subtract_years(value: date, years: int) -> date:
    """Subtract calendar years safely, including leap-day boundaries."""
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def classify_history(
    first_date: date | None,
    last_date: date | None,
    cutoff_date: date,
    as_of_date: date,
) -> str:
    """Classify observed date span, not daily completeness."""
    if first_date is None or last_date is None:
        return "NO_PRICE_HISTORY"

    if last_date < cutoff_date:
        return "STALE_HISTORY"

    if first_date > cutoff_date:
        return "PARTIAL_10Y_HISTORY"

    if last_date < as_of_date:
        return "HISTORY_ENDS_BEFORE_AS_OF"

    return "10Y_DATE_SPAN_OBSERVED"


def _serialise(value: Any) -> Any:
    if isinstance(value, (date,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "as_tuple"):
        return str(value)
    raise TypeError(f"Cannot serialise {type(value).__name__}")


def audit_historical_coverage(db_engine=None, years: int = 10) -> dict:
    """Audit stock_prices and companies using a read-only connection."""
    if years < 1 or years > 50:
        raise ValueError("years must be between 1 and 50")

    if db_engine is None:
        from backend.database import engine as db_engine

    from sqlalchemy import text

    with db_engine.connect() as conn:
        latest = conn.execute(
            text("SELECT MAX(trade_date) FROM stock_prices")
        ).scalar()

        if latest is None:
            raise RuntimeError("stock_prices contains no trade dates")

        if isinstance(latest, str):
            latest = date.fromisoformat(latest)

        as_of = latest
        cutoff = subtract_years(as_of, years)

        company_rows = conn.execute(text("""
            SELECT
                c.id AS company_id,
                c.symbol,
                c.company_name,
                c.is_active,
                COUNT(sp.id) AS total_rows,
                MIN(sp.trade_date) AS first_date,
                MAX(sp.trade_date) AS last_date,
                COUNT(DISTINCT sp.trade_date) AS distinct_dates,
                SUM(CASE WHEN sp.trade_date >= :cutoff
                         THEN 1 ELSE 0 END) AS rows_in_window,
                SUM(CASE WHEN sp.trade_date >= :cutoff
                         AND sp.close_price IS NULL
                         THEN 1 ELSE 0 END) AS null_closes_in_window,
                SUM(CASE WHEN sp.trade_date >= :cutoff
                         AND sp.close_price <= 0
                         THEN 1 ELSE 0 END) AS nonpositive_closes_in_window,
                COUNT(DISTINCT sp.price_source) AS source_count
            FROM companies c
            LEFT JOIN stock_prices sp ON sp.company_id = c.id
            GROUP BY c.id, c.symbol, c.company_name, c.is_active
            ORDER BY c.symbol
        """), {"cutoff": cutoff}).mappings().all()

        source_rows = conn.execute(text("""
            SELECT COALESCE(price_source, '<NULL>') AS source,
                   COUNT(*) AS row_count,
                   MIN(trade_date) AS first_date,
                   MAX(trade_date) AS last_date
            FROM stock_prices
            WHERE trade_date >= :cutoff
            GROUP BY price_source
            ORDER BY row_count DESC
        """), {"cutoff": cutoff}).mappings().all()

        monthly_rows = conn.execute(text("""
            SELECT DATE_FORMAT(trade_date, '%Y-%m') AS month,
                   COUNT(*) AS price_rows,
                   COUNT(DISTINCT company_id) AS companies_covered,
                   COUNT(DISTINCT trade_date) AS observed_dates
            FROM stock_prices
            WHERE trade_date >= :cutoff
            GROUP BY DATE_FORMAT(trade_date, '%Y-%m')
            ORDER BY month
        """), {"cutoff": cutoff}).mappings().all()

        duplicate_count = conn.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT company_id, trade_date
                FROM stock_prices
                WHERE trade_date >= :cutoff
                GROUP BY company_id, trade_date
                HAVING COUNT(*) > 1
            ) duplicate_keys
        """), {"cutoff": cutoff}).scalar_one()

        invalid_rows = conn.execute(text("""
            SELECT COUNT(*)
            FROM stock_prices sp
            WHERE sp.trade_date >= :cutoff
              AND (
                sp.close_price IS NULL
                OR sp.close_price <= 0
                OR (sp.high_price IS NOT NULL
                    AND sp.low_price IS NOT NULL
                    AND sp.high_price < sp.low_price)
                OR (sp.high_price IS NOT NULL
                    AND sp.close_price > sp.high_price)
                OR (sp.low_price IS NOT NULL
                    AND sp.close_price < sp.low_price)
                OR sp.total_traded_volume < 0
              )
        """), {"cutoff": cutoff}).scalar_one()

    companies = []
    for row in company_rows:
        first = row["first_date"]
        last = row["last_date"]

        if isinstance(first, str):
            first = date.fromisoformat(first)
        if isinstance(last, str):
            last = date.fromisoformat(last)

        companies.append({
            "company_id": row["company_id"],
            "symbol": row["symbol"],
            "company_name": row["company_name"],
            "is_active": bool(row["is_active"]),
            "total_rows": int(row["total_rows"] or 0),
            "first_date": first,
            "last_date": last,
            "distinct_dates": int(row["distinct_dates"] or 0),
            "rows_in_window": int(row["rows_in_window"] or 0),
            "null_closes_in_window": int(
                row["null_closes_in_window"] or 0
            ),
            "nonpositive_closes_in_window": int(
                row["nonpositive_closes_in_window"] or 0
            ),
            "source_count": int(row["source_count"] or 0),
            "span_status": classify_history(first, last, cutoff, as_of),
        })

    status_counts = {}
    for item in companies:
        status = item["span_status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "audit_name": "GREEDY STOCKS 10-Year Historical Coverage",
        "audit_version": 1,
        "read_only": True,
        "years_requested": years,
        "as_of_date": as_of,
        "cutoff_date": cutoff,
        "methodology": {
            "span_status": (
                "Compares first and last observed price dates with the "
                "requested window. It does not certify every trading day."
            ),
            "missing_dates": (
                "Not inferred from calendar days. Exchange trading "
                "calendar and security-specific listing periods are required."
            ),
            "adjustments": (
                "This audit reports raw stock_prices coverage. It does not "
                "claim split, bonus or dividend-adjusted total returns."
            ),
        },
        "summary": {
            "companies": len(companies),
            "status_counts": status_counts,
            "duplicate_company_date_keys": int(duplicate_count),
            "invalid_price_rows": int(invalid_rows),
            "monthly_buckets": len(monthly_rows),
        },
        "companies": companies,
        "price_sources": [dict(row) for row in source_rows],
        "monthly_coverage": [dict(row) for row in monthly_rows],
    }


def write_coverage_report(result: dict, output_dir: str | Path) -> tuple[Path, Path]:
    """Write JSON and company CSV reports."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "historical_coverage_10y.json"
    csv_path = output_dir / "historical_coverage_10y.csv"

    json_path.write_text(
        json.dumps(result, indent=2, default=_serialise),
        encoding="utf-8",
    )

    fields = [
        "company_id", "symbol", "company_name", "is_active",
        "total_rows", "first_date", "last_date", "distinct_dates",
        "rows_in_window", "null_closes_in_window",
        "nonpositive_closes_in_window", "source_count", "span_status",
    ]

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for company in result["companies"]:
            writer.writerow({
                key: _serialise(value) if isinstance(value, date) else value
                for key, value in company.items()
            })

    return json_path, csv_path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Read-only historical price coverage certification"
    )
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--output-dir", default="reports/phase4")
    args = parser.parse_args()

    result = audit_historical_coverage(years=args.years)
    json_path, csv_path = write_coverage_report(
        result, args.output_dir
    )

    print(json.dumps(result["summary"], indent=2))
    print("As-of:", result["as_of_date"])
    print("Cutoff:", result["cutoff_date"])
    print("JSON:", json_path)
    print("CSV:", csv_path)
    print("NOTE: date-span classification is not daily completeness certification.")


if __name__ == "__main__":
    main()
