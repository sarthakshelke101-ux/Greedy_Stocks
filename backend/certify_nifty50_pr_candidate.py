import csv
from pathlib import Path
from datetime import datetime

REVIEW = Path("database/raw/index/nifty50_historical_pr_10y_review.csv")
OLD = Path("database/raw/index/nifty50_historical_pr_combined.csv")
OUT = Path("database/raw/index/nifty50_historical_pr_10y_candidate.csv")
AUDIT = Path("database/raw/index/nifty50_pr_source_corrections.csv")

def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        result = {}
        for row in csv.DictReader(f):
            d = datetime.strptime(row["Date"], "%d %b %Y").date()
            if d in result:
                raise RuntimeError(f"Duplicate date in {path}: {d}")
            result[d] = row
        return result

new = read_csv(REVIEW)
old = read_csv(OLD)

if len(new) < 2200:
    raise RuntimeError(f"Insufficient history: {len(new)} rows")

if min(new) != datetime(2016,11,8).date() or max(new) != datetime(2026,11,6).date():
    raise RuntimeError("Date boundaries incorrect")

corrections = []
for d, previous in old.items():
    if d not in new:
        raise RuntimeError(f"Old date missing: {d}")

    for field in ["Open", "High", "Low", "Close"]:
        a = float(previous[field])
        b = float(new[d][field])

        if abs(a-b) <= 0.011:
            continue

        # Only the independently verified 18-Sep-2025 High discrepancy is allowed.
        if d.isoformat() == "2025-09-18" and field == "High":
            if abs(b - 25448.55) > 0.001 or abs(a - 25448.95) > 0.001:
                raise RuntimeError("Unexpected values for known discrepancy")
            corrections.append({
                "Date": str(d), "Field": field,
                "Old_Source_Value": a,
                "NSE_Verified_Value": b,
                "Reason": "Independent NSE API re-fetch confirmed 25448.55"
            })
        else:
            raise RuntimeError(f"Unexpected mismatch: {d} {field}: old={a}, new={b}")

if len(corrections) != 1:
    raise RuntimeError(f"Expected exactly one documented correction; got {len(corrections)}")

# Validate every OHLC record.
for d, x in new.items():
    o,h,l,c = [float(x[k]) for k in ["Open","High","Low","Close"]]
    if min(o,h,l,c) <= 0 or not (l <= min(o,c) <= max(o,c) <= h):
        raise RuntimeError(f"OHLC failure: {d}")

fields = ["Index Name","Date","Open","High","Low","Close"]
with OUT.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(new[d] for d in sorted(new))

with AUDIT.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(corrections[0]))
    w.writeheader()
    w.writerows(corrections)

print("\n========== CERTIFICATION ==========")
print("STATUS: PASS")
print("Total observations:", len(new))
print("Coverage:", min(new), "to", max(new))
print("Existing observations reconciled:", len(old))
print("Unexplained mismatches: 0")
print("Documented corrections:", len(corrections))
print("Corrected 18-Sep-2025 High: 25448.55")
print("OHLC validation: PASS")
print("Candidate:", OUT.resolve())
print("Correction audit:", AUDIT.resolve())
print("MYSQL WRITES: NONE")
