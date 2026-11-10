import requests, csv, time
from datetime import date, datetime, timedelta
from pathlib import Path

START = date(2016, 11, 8)
END = date(2026, 11, 6)
URL = "https://www.nseindia.com/api/historicalOR/indicesHistory"
OUT = Path("database/raw/index/nifty50_historical_pr_10y_candidate.csv")
EXISTING = Path("database/raw/index/nifty50_historical_pr_combined.csv")

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/reports-indices-historical-index-data",
})
for path in ["/", "/report-detail/eq_security"]:
    s.get("https://www.nseindia.com" + path, timeout=30).raise_for_status()

def fetch(a, b):
    params = {
        "indexType": "NIFTY 50",
        "from": a.strftime("%d-%m-%Y"),
        "to": b.strftime("%d-%m-%Y"),
    }
    for attempt in range(1, 5):
        try:
            r = s.get(URL, params=params, timeout=60)
            r.raise_for_status()
            data = r.json().get("data")
            if not isinstance(data, list):
                raise RuntimeError("API data is not a list")
            if len(data) > 70:
                raise RuntimeError(f"Unexpected API cap/response: {len(data)} rows")
            return data
        except Exception as e:
            print(f"Retry {attempt}/4: {str(e)[:180]}")
            if attempt == 4:
                raise
            time.sleep(attempt * 2)

rows = {}
cursor = START
chunk = 0
empty_chunks = 0

while cursor <= END:
    chunk_end = min(cursor + timedelta(days=59), END)
    chunk += 1
    batch = fetch(cursor, chunk_end)
    added = 0

    for x in batch:
        dt = datetime.strptime(x["EOD_TIMESTAMP"], "%d-%b-%Y").date()
        if not START <= dt <= END:
            continue
        if x.get("EOD_INDEX_NAME") != "NIFTY 50":
            raise RuntimeError(f"Wrong index returned: {x}")

        o = float(x["EOD_OPEN_INDEX_VAL"])
        h = float(x["EOD_HIGH_INDEX_VAL"])
        l = float(x["EOD_LOW_INDEX_VAL"])
        c = float(x["EOD_CLOSE_INDEX_VAL"])

        if min(o, h, l, c) <= 0 or not (l <= min(o,c) <= max(o,c) <= h):
            raise RuntimeError(f"Invalid OHLC for {dt}")

        if dt in rows:
            raise RuntimeError(f"Duplicate date across chunks: {dt}")

        rows[dt] = {
            "Index Name": "NIFTY 50",
            "Date": dt.strftime("%d %b %Y"),
            "Open": o, "High": h, "Low": l, "Close": c
        }
        added += 1

    empty_chunks += (added == 0)
    print(f"{chunk:03d} | {cursor} to {chunk_end} | received {len(batch)} | added {added}")
    cursor = chunk_end + timedelta(days=1)
    time.sleep(0.35)

if not rows:
    raise RuntimeError("No records received")

# Compare against the existing trusted source.
old = {}
with EXISTING.open(encoding="utf-8-sig", newline="") as f:
    for x in csv.DictReader(f):
        dt = datetime.strptime(x["Date"], "%d %b %Y").date()
        old[dt] = x

conflicts = []
missing_old = []
for dt, x in old.items():
    if dt not in rows:
        missing_old.append(dt)
        continue
    for key in ["Open", "High", "Low", "Close"]:
        if abs(float(x[key]) - rows[dt][key]) > 0.011:
            conflicts.append((dt, key, x[key], rows[dt][key]))

dates = sorted(rows)
if dates[0] != START or dates[-1] != END:
    raise RuntimeError(f"Boundary failure: {dates[0]} -> {dates[-1]}")
if conflicts or missing_old:
    print("\\nRECONCILIATION REVIEW REQUIRED")
    print("Conflicts:", len(conflicts))
    for item in conflicts:
        print("CONFLICT:", item)
    print("Old dates missing:", len(missing_old))
    for dt in missing_old[:20]:
        print("MISSING:", dt)

    review = OUT.with_name("nifty50_historical_pr_10y_review.csv")
    with review.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Index Name","Date","Open","High","Low","Close"])
        w.writeheader()
        w.writerows(rows[d] for d in dates)
    print("Full downloaded data preserved for review:", review.resolve())
    raise SystemExit("STOPPED SAFELY: no candidate replacement and no database writes.")

# Require a plausible daily-series size; do not silently accept a capped result.
if len(rows) < 2200:
    raise RuntimeError(f"Only {len(rows)} rows; full 10-year coverage not established. Candidate not replaced.")

tmp = OUT.with_suffix(".tmp")
with tmp.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["Index Name","Date","Open","High","Low","Close"])
    w.writeheader()
    w.writerows(rows[d] for d in dates)

tmp.replace(OUT)

print("\n========== FINAL REPORT ==========")
print("STATUS: PASS")
print("Rows:", len(rows))
print("Date range:", dates[0], "to", dates[-1])
print("Existing rows matched:", len(old))
print("Conflicts:", len(conflicts))
print("Old dates missing:", len(missing_old))
print("Empty chunks:", empty_chunks)
print("Candidate:", OUT.resolve())
print("MYSQL WRITES: NONE")
