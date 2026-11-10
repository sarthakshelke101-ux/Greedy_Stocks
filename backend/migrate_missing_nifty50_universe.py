import sys
import argparse
from pathlib import Path
from zipfile import ZipFile
from collections import defaultdict
from datetime import date
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, "backend")

from database import engine
from import_nifty50_historical_prices import (
    read_bhavcopy, normalize_rows, existing_rows_for_date,
    values_match, INSERT_SQL
)

ROOT = Path("database/raw/bhavcopy")
AUDIT = ROOT / "nifty50_missing_symbol_isin_audit.csv"
SOURCE = "NSE CM Bhavcopy historical identity and price archive"

ALIASES = {
    "INFRATEL": ("INDUSTOWER", "Indus Towers Limited"),
    "IBULHSGFIN": ("SAMMAANCAP", "Sammaan Capital Limited"),
    "LTIM": ("LTM", "LTIMindtree Limited"),
    "ZOMATO": ("ETERNAL", "Eternal Limited"),
}
FALLBACK_NAMES = {
    "HDFC": "Housing Development Finance Corporation Limited",
}
INACTIVE = {"HDFC", "TATAMTRDVR"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Commit the complete migration")
    args = parser.parse_args()

    if not AUDIT.exists():
        raise FileNotFoundError(AUDIT)

    audit = pd.read_csv(AUDIT).fillna("")
    audit["symbol"] = audit["symbol"].str.strip().str.upper()
    expected = {
        r["symbol"]: int(r["eq_rows"])
        for _, r in audit.iterrows()
    }
    date_ranges = {
        r["symbol"]: (pd.to_datetime(r["first_date"]).date(),
                      pd.to_datetime(r["last_date"]).date())
        for _, r in audit.iterrows()
    }
    if len(expected) != 26:
        raise RuntimeError(f"Expected 26 audited symbols, found {len(expected)}")

    archives = sorted(ROOT.rglob("*.zip"))
    if not archives:
        raise FileNotFoundError("No historical ZIP archives found")

    print("GREEDY STOCKS — HISTORICAL UNIVERSE MIGRATION")
    print("Archives:", len(archives), "| Target symbols:", len(expected))
    print("Mode:", "LIVE COMMIT" if args.apply else "DRY RUN / ROLLBACK")

    # Resolve identities and prices from the actual archives.
    periods = defaultdict(lambda: {"first": None, "last": None, "rows": 0})
    date_isin = {}
    observed_rows = defaultdict(int)
    staged_prices = []
    legacy = udiff = 0

    for n, archive in enumerate(archives, 1):
        with ZipFile(archive) as zf:
            _, df, fmt = read_bhavcopy(zf)

        if fmt == "UDIFF":
            symbol_col, series_col, isin_col = "TckrSymb", "SctySrs", "ISIN"
        else:
            symbol_col, series_col, isin_col = "SYMBOL", "SERIES", "ISIN"

        if fmt == "UDIFF":
            udiff += 1
        else:
            legacy += 1

        if not {symbol_col, series_col, isin_col}.issubset(df.columns):
            raise RuntimeError(f"Missing identity columns in {archive.name}")

        symbols = df[symbol_col].fillna("").astype(str).str.strip().str.upper()
        series = df[series_col].fillna("").astype(str).str.strip().str.upper()
        target_mask = symbols.isin(expected) & series.eq("EQ")

        if target_mask.any():
            rows_date, _ = normalize_rows(
                df, {s: {"id": 1, "isin": None} for s in expected},
                archive.name, fmt
            )
            if not rows_date:
                raise RuntimeError(f"Target rows failed normalization: {archive.name}")

            rows_date = [
                row for row in rows_date
                if row["symbol"] in date_ranges
                and date_ranges[row["symbol"]][0] <= row["trade_date"]
                <= date_ranges[row["symbol"]][1]
            ]
            if not rows_date:
                continue
            trade_date = rows_date[0]["trade_date"]

            allowed_symbols = {row["symbol"] for row in rows_date}
            for _, rec in df.loc[target_mask & symbols.isin(allowed_symbols)].iterrows():
                symbol = str(rec[symbol_col]).strip().upper()
                isin = str(rec[isin_col]).strip().upper()
                if not isin or isin.lower() == "nan":
                    raise RuntimeError(f"Missing ISIN: {symbol} on {trade_date}")

                key = (symbol, trade_date)
                previous = date_isin.get(key)
                if previous and previous != isin:
                    raise RuntimeError(
                        f"Two ISINs for {symbol} on {trade_date}: {previous}, {isin}"
                    )
                date_isin[key] = isin

                p = periods[(symbol, isin)]
                p["first"] = trade_date if p["first"] is None else min(p["first"], trade_date)
                p["last"] = trade_date if p["last"] is None else max(p["last"], trade_date)
                p["rows"] += 1
                observed_rows[symbol] += 1

            staged_prices.extend(rows_date)

        if n % 250 == 0 or n == len(archives):
            print(f"Scanned {n}/{len(archives)} archives; staged {len(staged_prices):,} prices")

    for symbol, count in expected.items():
        if observed_rows[symbol] != count:
            raise RuntimeError(
                f"Archive count mismatch for {symbol}: "
                f"expected {count}, found {observed_rows[symbol]}"
            )

    # Ensure ISIN periods for each symbol do not overlap.
    for symbol in expected:
        symbol_periods = sorted(
            [(isin, p["first"], p["last"])
             for (s, isin), p in periods.items() if s == symbol],
            key=lambda x: x[1]
        )
        for left, right in zip(symbol_periods, symbol_periods[1:]):
            if left[2] >= right[1]:
                raise RuntimeError(f"Overlapping ISIN periods for {symbol}: {left}, {right}")

    # One transaction covers company registration, identifiers and prices.
    conn = engine.connect()
    tx = conn.begin()
    try:
        company_ids = {}
        company_info = {}

        for _, rec in audit.iterrows():
            old_symbol = rec["symbol"]
            canonical, successor_name = ALIASES.get(
                old_symbol, (old_symbol, "")
            )
            names = [
                x.strip() for x in str(rec["company_names"]).split("|")
                if x.strip()
            ]
            name = successor_name or (names[0] if names else "")
            name = name or FALLBACK_NAMES.get(old_symbol, "")
            if not name:
                raise RuntimeError(f"No defensible company name for {old_symbol}")

            unique_isins = sorted({
                isin for (s, isin) in periods if s == old_symbol
            })
            company_isin = unique_isins[0] if len(unique_isins) == 1 else None

            existing = conn.execute(text("""
                SELECT id, isin FROM companies WHERE symbol=:symbol
            """), {"symbol": canonical}).mappings().first()

            if existing:
                cid = int(existing["id"])
                if existing["isin"] and company_isin and existing["isin"] != company_isin:
                    raise RuntimeError(
                        f"Company ISIN conflict for {canonical}: "
                        f"{existing['isin']} vs {company_isin}"
                    )
                if not existing["isin"] and company_isin:
                    conn.execute(text("""
                        UPDATE companies SET isin=:isin
                        WHERE id=:id AND isin IS NULL
                    """), {"isin": company_isin, "id": cid})
            else:
                conn.execute(text("""
                    INSERT INTO companies
                        (symbol, company_name, isin, exchange, is_active)
                    VALUES
                        (:symbol, :name, :isin, 'NSE', :active)
                """), {
                    "symbol": canonical,
                    "name": name,
                    "isin": company_isin,
                    "active": 0 if old_symbol in INACTIVE else 1,
                })
                cid = int(conn.execute(text(
                    "SELECT id FROM companies WHERE symbol=:symbol"
                ), {"symbol": canonical}).scalar_one())

            company_ids[old_symbol] = cid
            company_info[old_symbol] = canonical

        # Build the importer map for original historical symbols.
        company_map = {
            symbol: {"id": company_ids[symbol], "isin": None}
            for symbol in expected
        }

        # Insert historical prices with exact conflict checks.
        inserted = unchanged = 0
        # Map staged rows from temporary validation ID to real company IDs.
        for row in staged_prices:
            row["company_id"] = company_ids[row["symbol"]]

        by_date = defaultdict(list)
        for row in staged_prices:
            by_date[row["trade_date"]].append(row)

        for trade_date in sorted(by_date):
            old_rows = existing_rows_for_date(conn, trade_date)
            for row in by_date[trade_date]:
                key = (row["company_id"], row["trade_date"])
                if key in old_rows:
                    if not values_match(old_rows[key], row):
                        raise RuntimeError(
                            f"Existing price conflict: {row['symbol']} {trade_date}"
                        )
                    unchanged += 1
                else:
                    conn.execute(INSERT_SQL, row)
                    inserted += 1

        # Add ISIN histories and old ticker aliases.
        identifiers_added = identifiers_updated = 0

        for (symbol, isin), p in periods.items():
            cid = company_ids[symbol]
            is_latest = not any(
                s == symbol and other_first > p["first"]
                for (s, _), other in periods.items()
                for other_first in [other["first"]]
            )
            valid_to = None if is_latest and symbol not in INACTIVE else p["last"]

            existing_identifier = conn.execute(text("""
                SELECT id, valid_from, valid_to
                FROM company_identifiers
                WHERE company_id=:cid AND identifier_type='ISIN'
                  AND identifier_value=:value
                ORDER BY valid_from
            """), {"cid": cid, "value": isin}).mappings().all()

            exact = next(
                (x for x in existing_identifier if x["valid_from"] == p["first"]),
                None
            )
            if exact:
                if exact["valid_to"] != valid_to:
                    conn.execute(text("""
                        UPDATE company_identifiers SET valid_to=:valid_to
                        WHERE id=:id
                    """), {"valid_to": valid_to, "id": exact["id"]})
                    identifiers_updated += 1
            elif existing_identifier:
                # Extend an existing matching identifier backwards only
                # when it is the same identity period and does not overlap.
                candidate = next(
                    (x for x in existing_identifier
                     if x["valid_from"] > p["first"]
                     and (x["valid_to"] is None or x["valid_to"] >= p["first"])),
                    None
                )
                if candidate:
                    collision = conn.execute(text("""
                        SELECT COUNT(*) FROM company_identifiers
                        WHERE company_id=:cid AND identifier_type='ISIN'
                          AND identifier_value=:value AND valid_from=:start
                    """), {
                        "cid": cid, "value": isin, "start": p["first"]
                    }).scalar_one()
                    if collision:
                        raise RuntimeError(f"Identifier period collision: {symbol}/{isin}")
                    conn.execute(text("""
                        UPDATE company_identifiers SET valid_from=:start,
                            valid_to=:end WHERE id=:id
                    """), {
                        "start": p["first"], "end": valid_to, "id": candidate["id"]
                    })
                    identifiers_updated += 1
                else:
                    conn.execute(text("""
                        INSERT INTO company_identifiers
                            (company_id, identifier_type, identifier_value,
                             valid_from, valid_to, source_name, source_reference)
                        VALUES (:cid, 'ISIN', :value, :start, :end, :source, :ref)
                    """), {
                        "cid": cid, "value": isin, "start": p["first"],
                        "end": valid_to, "source": SOURCE,
                        "ref": f"Observed in {p['rows']} EQ rows in NSE archives"
                    })
                    identifiers_added += 1
            else:
                conn.execute(text("""
                    INSERT INTO company_identifiers
                        (company_id, identifier_type, identifier_value,
                         valid_from, valid_to, source_name, source_reference)
                    VALUES (:cid, 'ISIN', :value, :start, :end, :source, :ref)
                """), {
                    "cid": cid, "value": isin, "start": p["first"],
                    "end": valid_to, "source": SOURCE,
                    "ref": f"Observed in {p['rows']} EQ rows in NSE archives"
                })
                identifiers_added += 1

        for symbol, (canonical, _) in ALIASES.items():
            cid = company_ids[symbol]
            first = min(p["first"] for (s, _), p in periods.items() if s == symbol)
            last = max(p["last"] for (s, _), p in periods.items() if s == symbol)

            existing = conn.execute(text("""
                SELECT id, valid_from FROM company_identifiers
                WHERE company_id=:cid AND identifier_type='TICKER'
                  AND identifier_value=:symbol
            """), {"cid": cid, "symbol": symbol}).mappings().all()

            if existing:
                row = existing[0]
                if row["valid_from"] > first:
                    conn.execute(text("""
                        UPDATE company_identifiers SET valid_from=:first,
                            valid_to=:last WHERE id=:id
                    """), {"first": first, "last": last, "id": row["id"]})
                    identifiers_updated += 1
            else:
                conn.execute(text("""
                    INSERT INTO company_identifiers
                        (company_id, identifier_type, identifier_value,
                         valid_from, valid_to, source_name, source_reference)
                    VALUES (:cid, 'TICKER', :symbol, :first, :last, :source, :ref)
                """), {
                    "cid": cid, "symbol": symbol, "first": first, "last": last,
                    "source": SOURCE,
                    "ref": f"Verified historical ticker for {canonical}"
                })
                identifiers_added += 1

        # Final in-transaction verification.
        target_ids = sorted(set(company_ids.values()))
        placeholders = ",".join(str(x) for x in target_ids)
        totals = conn.execute(text(f"""
            SELECT COUNT(*), COUNT(DISTINCT company_id),
                   COUNT(DISTINCT trade_date), MIN(trade_date), MAX(trade_date)
            FROM stock_prices WHERE company_id IN ({placeholders})
        """)).fetchone()

        if totals[1] != len(target_ids):
            raise RuntimeError(f"Not all target companies have prices: {totals}")

        print("\n========== MIGRATION RESULT ==========")
        print("Historical symbols:", len(expected))
        print("Company identities mapped:", len(target_ids))
        print("Observed EQ rows:", len(staged_prices))
        print("New price rows:", inserted)
        print("Already matching prices:", unchanged)
        print("Identifiers added:", identifiers_added)
        print("Identifiers updated:", identifiers_updated)
        print("Target price rows now:", totals[0])
        print("Companies represented:", totals[1])
        print("Trading dates:", totals[2])
        print("Date range:", totals[3], "to", totals[4])

        if args.apply:
            tx.commit()
            print("\nCOMMITTED SUCCESSFULLY.")
        else:
            tx.rollback()
            print("\nDRY RUN COMPLETE — all changes rolled back.")

    except Exception:
        tx.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
