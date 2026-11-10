import csv
from pathlib import Path
from collections import defaultdict
from datetime import date

ROOT = Path("database/raw/bhavcopy")
MEMBERSHIP = ROOT / "nifty50_membership_2016_2026.csv"
IDENTITY_AUDIT = ROOT / "nifty50_combined_historical_symbol_audit.csv"
OUT_LEDGER = ROOT / "nifty50_membership_review_ledger.csv"
OUT_IDENTITY = ROOT / "nifty50_symbol_identity_master.csv"
OUT_ISSUES = ROOT / "nifty50_membership_review_issues.csv"

PERIOD_START = date(2016, 11, 8)
PERIOD_END = date(2026, 11, 6)

def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def get(row, *names):
    lower = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        value = lower.get(name.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""

def parse_date(value, is_end=False):
    value = (value or "").strip()
    if not value or value.upper() in {"CURRENT", "PRESENT", "ONGOING", "NA", "N/A"}:
        return PERIOD_END if is_end else None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None

membership_rows = read_csv(MEMBERSHIP)
audit_rows = read_csv(IDENTITY_AUDIT)

# Build the archive-backed symbol/security identity map.
by_isin = defaultdict(list)
audit_by_symbol = {}

for row in audit_rows:
    symbol = get(row, "symbol").upper()
    isin = get(row, "isins", "isin").upper()
    first = parse_date(get(row, "first_date"))
    last = parse_date(get(row, "last_date"), is_end=True)

    record = {
        "symbol": symbol,
        "isin": isin,
        "first": first,
        "last": last,
        "rows": get(row, "rows"),
        "trading_dates": get(row, "distinct_dates", "distinct_trading_dates"),
    }
    audit_by_symbol[symbol] = record
    if isin:
        by_isin[isin].append(record)

identity_rows = []
for symbol, item in sorted(audit_by_symbol.items()):
    identity_rows.append({
        "trading_symbol": symbol,
        "isin": item["isin"],
        "security_identity_key": item["isin"] or f"UNVERIFIED_SYMBOL:{symbol}",
        "first_bhavcopy_date": item["first"].isoformat() if item["first"] else "",
        "last_bhavcopy_date": item["last"].isoformat() if item["last"] else "",
        "bhavcopy_rows": item["rows"],
        "distinct_trading_dates": item["trading_dates"],
        "identity_evidence": "NSE_BHAVCOPY_ISIN" if item["isin"] else "SYMBOL_ONLY",
    })

with OUT_IDENTITY.open("w", encoding="utf-8-sig", newline="") as f:
    fields = list(identity_rows[0].keys()) if identity_rows else [
        "trading_symbol", "isin", "security_identity_key",
        "first_bhavcopy_date", "last_bhavcopy_date",
        "bhavcopy_rows", "distinct_trading_dates", "identity_evidence"
    ]
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(identity_rows)

ledger = []
issues = []

for row_no, row in enumerate(membership_rows, 2):
    source_symbol = get(row, "symbol", "ticker", "tradingsymbol").upper()
    if not source_symbol:
        issues.append({
            "source_row": row_no,
            "symbol": "",
            "issue": "MISSING_SYMBOL",
            "details": "Membership source row has no symbol",
        })
        continue

    raw_start = get(row, "valid_from", "from_date", "start_date")
    raw_end = get(row, "valid_to", "to_date", "end_date")
    start = parse_date(raw_start)
    end = parse_date(raw_end, is_end=True)

    if start is None:
        issues.append({
            "source_row": row_no,
            "symbol": source_symbol,
            "issue": "INVALID_OR_MISSING_START_DATE",
            "details": f"Source valid_from={raw_start!r}",
        })
        continue

    if end is None:
        issues.append({
            "source_row": row_no,
            "symbol": source_symbol,
            "issue": "INVALID_END_DATE",
            "details": f"Source valid_to={raw_end!r}",
        })
        continue

    if source_symbol == "HDFC" and end == date(2023, 7, 13):
        end = date(2023, 7, 12)

    start = max(start, PERIOD_START)
    end = min(end, PERIOD_END)
    if start > end:
        continue

    source_isin = get(row, "isin").upper()
    source_audit = audit_by_symbol.get(source_symbol)

    if not source_isin and source_audit:
        source_isin = source_audit["isin"]

    # If the source uses a renamed/canonical ticker, split the interval
    # across archive-observed trading symbols sharing the same ISIN.
    if source_isin and source_isin in by_isin:
        candidates = by_isin[source_isin]
    elif source_audit:
        candidates = [source_audit]
    else:
        candidates = []

    matched_segments = []
    for candidate in candidates:
        if not candidate["first"] or not candidate["last"]:
            continue
        seg_start = max(start, candidate["first"])
        seg_end = min(end, candidate["last"])
        if seg_start <= seg_end:
            matched_segments.append((candidate, seg_start, seg_end))

    if matched_segments:
        for candidate, seg_start, seg_end in matched_segments:
            ledger.append({
                "source_row": row_no,
                "company_identity_key": source_isin or f"UNVERIFIED_SYMBOL:{source_symbol}",
                "source_symbol": source_symbol,
                "historical_trading_symbol": candidate["symbol"],
                "isin": source_isin,
                "membership_start": seg_start.isoformat(),
                "membership_end": seg_end.isoformat(),
                "source_valid_from": raw_start,
                "source_valid_to": raw_end,
                "membership_source": get(row, "source"),
                "source_url": get(row, "source_url"),
                "source_notes": get(row, "notes"),
                "price_archive_match": "YES",
                "membership_validation": "LEFT_CENSORED_START_UNVERIFIED" if raw_start == "2014-01-01" else "PROVISIONAL_NOT_OFFICIALLY_VERIFIED",
            })

        covered_start = min(x[1] for x in matched_segments)
        covered_end = max(x[2] for x in matched_segments)
        if covered_start > start or covered_end < end:
            issues.append({
                "source_row": row_no,
                "symbol": source_symbol,
                "issue": "MEMBERSHIP_INTERVAL_NOT_FULLY_COVERED_BY_AUDITED_TICKER",
                "details": f"Source interval {start} to {end}; archive-observed coverage {covered_start} to {covered_end}",
            })
    else:
        ledger.append({
            "source_row": row_no,
            "company_identity_key": source_isin or f"UNVERIFIED_SYMBOL:{source_symbol}",
            "source_symbol": source_symbol,
            "historical_trading_symbol": source_symbol,
            "isin": source_isin,
            "membership_start": start.isoformat(),
            "membership_end": end.isoformat(),
            "source_valid_from": raw_start,
            "source_valid_to": raw_end,
            "membership_source": get(row, "source"),
            "source_url": get(row, "source_url"),
            "source_notes": get(row, "notes"),
            "price_archive_match": "NOT_AUDITED",
            "membership_validation": "LEFT_CENSORED_START_UNVERIFIED" if raw_start == "2014-01-01" else "PROVISIONAL_NOT_OFFICIALLY_VERIFIED",
        })
        issues.append({
            "source_row": row_no,
            "symbol": source_symbol,
            "issue": "NO_MATCH_IN_18_SYMBOL_IDENTITY_AUDIT",
            "details": "This does not prove the symbol is absent from Bhavcopy; it was outside the focused identity audit",
        })

ledger_fields = [
    "source_row", "company_identity_key", "source_symbol",
    "historical_trading_symbol", "isin", "membership_start",
    "membership_end", "source_valid_from", "source_valid_to",
    "membership_source", "source_url", "source_notes",
    "price_archive_match", "membership_validation"
]

with OUT_LEDGER.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=ledger_fields)
    writer.writeheader()
    writer.writerows(sorted(
        ledger,
        key=lambda x: (x["company_identity_key"], x["membership_start"], x["historical_trading_symbol"])
    ))

with OUT_ISSUES.open("w", encoding="utf-8-sig", newline="") as f:
    fields = ["source_row", "symbol", "issue", "details"]
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(issues)

print("\n========== MEMBERSHIP REVIEW BUILD ==========")
print("Input membership rows:", len(membership_rows))
print("Archive-audited symbol identities:", len(identity_rows))
print("Membership ledger rows:", len(ledger))
print("Review issues:", len(issues))
print("\nOUTPUTS:")
print(OUT_LEDGER)
print(OUT_IDENTITY)
print(OUT_ISSUES)
print("\nIMPORTANT: Every membership row remains PROVISIONAL until checked against official dated NSE Indices snapshots/announcements.")
