import sys
sys.path.insert(0, "backend")

from sqlalchemy import text, inspect
from database import engine

results = []

def record(name, passed, detail, severity="FAIL"):
    status = "PASS" if passed else severity
    results.append((name, status, detail))
    print(f"[{status}] {name}: {detail}")

def main():
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    required = {
        "companies", "company_identifiers",
        "index_constituent_snapshots",
        "index_constituent_observation_spans",
        "index_membership_events", "index_constituents",
        "stock_prices", "corporate_actions",
        "data_import_logs", "validation_logs"
    }

    print("=" * 72)
    print("GREEDY STOCKS — PHASE 2 FINAL RECONCILIATION")
    print("READ-ONLY AUDIT — NO DATABASE CHANGES")
    print("=" * 72)

    missing_tables = sorted(required - tables)
    record(
        "Required database tables",
        not missing_tables,
        "All expected tables exist" if not missing_tables
        else f"Missing: {missing_tables}"
    )

    if missing_tables:
        print("\nAudit stopped because required tables are missing.")
        return

    with engine.connect() as conn:
        # 1. Company master
        companies = conn.execute(text("""
            SELECT COUNT(*) AS total,
                   COUNT(DISTINCT symbol) AS symbols,
                   SUM(isin IS NULL OR isin = '') AS missing_isin
            FROM companies
        """)).mappings().one()

        record(
            "Company master",
            companies["total"] == 54 and companies["symbols"] == 54,
            f"{companies['total']} rows; {companies['symbols']} unique symbols"
        )

        # 2. Monthly constituent snapshots
        snapshots = conn.execute(text("""
            SELECT COUNT(*) AS total,
                   COUNT(DISTINCT report_month) AS months,
                   COUNT(DISTINCT symbol) AS symbols
            FROM index_constituent_snapshots
            WHERE index_symbol = 'NIFTY 50'
        """)).mappings().one()

        monthly = conn.execute(text("""
            SELECT report_month, COUNT(*) AS rows_per_month
            FROM index_constituent_snapshots
            WHERE index_symbol = 'NIFTY 50'
            GROUP BY report_month
            ORDER BY report_month
        """)).mappings().all()

        monthly_ok = len(monthly) == 19 and all(
            r["rows_per_month"] == 50 for r in monthly
        )

        record(
            "Monthly constituent snapshots",
            snapshots["total"] == 950
            and snapshots["months"] == 19
            and snapshots["symbols"] == 54
            and monthly_ok,
            f"{snapshots['total']} rows; {snapshots['months']} months; "
            f"{snapshots['symbols']} instruments; "
            f"{sum(1 for r in monthly if r['rows_per_month'] == 50)}/"
            f"{len(monthly)} months have 50 rows"
        )

        # Snapshot symbols must resolve to company identities.
        unresolved_snapshots = conn.execute(text("""
            SELECT COUNT(*)
            FROM index_constituent_snapshots s
            LEFT JOIN companies c ON c.symbol = s.symbol
            WHERE s.index_symbol = 'NIFTY 50'
              AND c.id IS NULL
        """)).scalar_one()

        record(
            "Snapshot-to-company mapping",
            unresolved_snapshots == 0,
            f"{unresolved_snapshots} unresolved snapshot symbols"
        )

        # 3. Observation spans
        spans = conn.execute(text("""
            SELECT COUNT(*) AS total,
                   SUM(internal_missing_month_count) AS gaps,
                   SUM(observation_status <> 'CONTIGUOUS') AS noncontiguous
            FROM index_constituent_observation_spans
            WHERE index_symbol = 'NIFTY 50'
        """)).mappings().one()

        record(
            "Monthly observation spans",
            spans["total"] == 54
            and (spans["gaps"] or 0) == 0
            and (spans["noncontiguous"] or 0) == 0,
            f"{spans['total']} instruments; "
            f"{spans['gaps'] or 0} internal gaps; "
            f"{spans['noncontiguous'] or 0} non-contiguous"
        )

        # 4. Membership events
        events = conn.execute(text("""
            SELECT COUNT(*) AS total,
                   SUM(
                       (old_symbol IS NOT NULL AND old_symbol <> ''
                        AND old_company_id IS NULL)
                       OR
                       (new_symbol IS NOT NULL AND new_symbol <> ''
                        AND new_company_id IS NULL)
                   ) AS unresolved
            FROM index_membership_events
            WHERE index_symbol = 'NIFTY 50'
        """)).mappings().one()

        record(
            "Membership event register",
            events["total"] == 4 and (events["unresolved"] or 0) == 0,
            f"{events['total']} events; "
            f"{events['unresolved'] or 0} unresolved company links"
        )

        # 5. Identifier mappings
        identifiers = conn.execute(text("""
            SELECT COUNT(*) AS total,
                   SUM(identifier_type = 'ISIN') AS isin_count,
                   SUM(identifier_type = 'TICKER') AS ticker_count
            FROM company_identifiers
        """)).mappings().one()

        eternal = conn.execute(text("""
            SELECT c.isin, ci.identifier_value,
                   ci.valid_from, ci.valid_to
            FROM companies c
            JOIN company_identifiers ci ON ci.company_id = c.id
            WHERE c.symbol = 'ETERNAL'
              AND ci.identifier_type = 'ISIN'
        """)).mappings().all()

        eternal_ok = (
            len(eternal) == 1
            and eternal[0]["isin"] == "INE758T01015"
            and eternal[0]["identifier_value"] == "INE758T01015"
        )

        record(
            "Identifier register",
            identifiers["total"] == 8 and eternal_ok,
            f"{identifiers['total']} identifiers; "
            f"{identifiers['isin_count']} ISIN; "
            f"{identifiers['ticker_count']} ticker aliases; "
            f"ETERNAL ISIN {'verified' if eternal_ok else 'NOT VERIFIED'}"
        )

        # 6. Historical stock prices
        price_summary = conn.execute(text("""
            SELECT COUNT(*) AS total,
                   COUNT(DISTINCT company_id) AS companies,
                   COUNT(DISTINCT trade_date) AS trading_dates,
                   MIN(trade_date) AS first_date,
                   MAX(trade_date) AS last_date
            FROM stock_prices
        """)).mappings().one()

        record(
            "Historical price volume and coverage",
            price_summary["total"] == 19557
            and price_summary["companies"] == 54
            and price_summary["trading_dates"] == 369
            and str(price_summary["first_date"]) == "2025-04-01"
            and str(price_summary["last_date"]) == "2026-11-05",
            f"{price_summary['total']} rows; "
            f"{price_summary['companies']} instruments; "
            f"{price_summary['trading_dates']} dates; "
            f"{price_summary['first_date']} to {price_summary['last_date']}"
        )

        # Per-instrument expected counts.
        per_company = conn.execute(text("""
            SELECT c.symbol, COUNT(p.id) AS records
            FROM companies c
            LEFT JOIN stock_prices p ON p.company_id = c.id
            GROUP BY c.id, c.symbol
            ORDER BY c.symbol
        """)).mappings().all()

        wrong_counts = [
            f"{r['symbol']}={r['records']}"
            for r in per_company
            if r["records"] != (
                130 if r["symbol"] == "TATAMOTORS"
                else 239 if r["symbol"] == "TMPV"
                else 369
            )
        ]

        record(
            "Per-instrument price coverage",
            len(per_company) == 54 and not wrong_counts,
            "All 52 continuous instruments have 369 rows; "
            "TATAMOTORS=130 and TMPV=239"
            if not wrong_counts
            else f"Unexpected counts: {wrong_counts}"
        )

        # 7. OHLC and trading-statistic quality.
        quality = conn.execute(text("""
            SELECT
                SUM(open_price IS NULL OR high_price IS NULL OR
                    low_price IS NULL OR close_price IS NULL)
                    AS null_ohlc,
                SUM(open_price <= 0 OR high_price <= 0 OR
                    low_price <= 0 OR close_price <= 0)
                    AS nonpositive_prices,
                SUM(high_price < low_price OR
                    high_price < open_price OR
                    high_price < close_price OR
                    low_price > open_price OR
                    low_price > close_price)
                    AS invalid_ohlc,
                SUM(total_traded_volume < 0 OR
                    total_traded_value < 0 OR
                    total_trades < 0)
                    AS negative_statistics
            FROM stock_prices
        """)).mappings().one()

        quality_ok = all(
            (quality[k] or 0) == 0 for k in quality
        )

        record(
            "Price quality",
            quality_ok,
            ", ".join(f"{k}={quality[k] or 0}" for k in quality)
        )

        # 8. Duplicate daily prices
        duplicates = conn.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT company_id, trade_date
                FROM stock_prices
                GROUP BY company_id, trade_date
                HAVING COUNT(*) > 1
            ) d
        """)).scalar_one()

        record(
            "Duplicate company/date prices",
            duplicates == 0,
            f"{duplicates} duplicate company/date groups"
        )

        # 9. Tata transition
        tata = conn.execute(text("""
            SELECT c.symbol, MIN(p.trade_date) AS first_date,
                   MAX(p.trade_date) AS last_date,
                   COUNT(p.id) AS records
            FROM companies c
            LEFT JOIN stock_prices p ON p.company_id = c.id
            WHERE c.symbol IN ('TATAMOTORS', 'TMPV')
            GROUP BY c.symbol
        """)).mappings().all()

        tata_map = {r["symbol"]: r for r in tata}
        tata_ok = (
            set(tata_map) == {"TATAMOTORS", "TMPV"}
            and tata_map["TATAMOTORS"]["records"] == 130
            and str(tata_map["TATAMOTORS"]["last_date"]) == "2025-10-23"
            and tata_map["TMPV"]["records"] == 239
            and str(tata_map["TMPV"]["first_date"]) == "2025-10-24"
        )

        record(
            "Tata instrument transition",
            tata_ok,
            "TATAMOTORS ends 2025-10-23; TMPV starts 2025-10-24"
            if tata_ok else "Transition requires investigation"
        )

        # 10. Exact membership periods are intentionally not inferred.
        exact_periods = conn.execute(text("""
            SELECT COUNT(*) FROM index_constituents
            WHERE index_symbol = 'NIFTY 50'
        """)).scalar_one()

        record(
            "Exact effective membership periods",
            exact_periods == 0,
            f"{exact_periods} periods; monthly observations are not "
            "being misrepresented as legal effective dates",
            severity="WARN"
        )

        # 11. Corporate actions
        action_count = conn.execute(text(
            "SELECT COUNT(*) FROM corporate_actions"
        )).scalar_one()

        record(
            "Corporate-action coverage",
            action_count > 0,
            f"{action_count} records; adjusted/total-return history "
            "is not yet established",
            severity="WARN"
        )

        # 12. Import and validation logs
        for table in ["data_import_logs", "validation_logs"]:
            count = conn.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar_one()

            record(
                f"{table} provenance",
                count > 0,
                f"{count} records; "
                + ("log records present" if count > 0
                   else "no audit records found"),
                severity="WARN"
            )

    print("\n" + "=" * 72)
    print("AUDIT RESULT")
    print("=" * 72)

    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    warnings = sum(1 for _, s, _ in results if s == "WARN")

    print("PASS:", passed)
    print("FAIL:", failed)
    print("WARN:", warnings)

    if failed:
        print("\nPHASE 2: NOT READY — FIX FAILED CHECKS")
    elif warnings:
        print("\nPHASE 2: CORE IMPORT CHECKS PASS — WARNINGS REMAIN")
    else:
        print("\nPHASE 2: AUDIT CHECKS PASS")

if __name__ == "__main__":
    main()
