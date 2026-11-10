import csv
import io
import urllib.request
from pathlib import Path
from datetime import date

ROOT = Path.cwd()
DATA = ROOT / "database" / "raw" / "bhavcopy"
DATA.mkdir(parents=True, exist_ok=True)

URL = (
    "https://raw.githubusercontent.com/aditya-jha/"
    "nse-historical-membership/main/"
    "index_history/data/index_membership_history.csv"
)

HISTORY_FILE = DATA / "nse_historical_index_membership_source.csv"
OUTPUT = DATA / "nifty50_membership_2016_2026.csv"
UNIQUE_OUTPUT = DATA / "nifty50_unique_companies_2016_2026.csv"
MATCH_OUTPUT = DATA / "nifty50_bhavcopy_match_2016_2026.csv"

START = date(2016, 11, 8)
END = date(2026, 11, 6)

print("Downloading historical membership dataset...")
request = urllib.request.Request(
    URL, headers={"User-Agent": "GREEDY-STOCKS/1.0"}
)
with urllib.request.urlopen(request, timeout=60) as response:
    raw = response.read()

HISTORY_FILE.write_bytes(raw)
reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))

all_rows = list(reader)
print("Historical source rows:", len(all_rows))
print("Source columns:", reader.fieldnames)

def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None

nifty_rows = []
for row in all_rows:
    index_name = (row.get("index_name") or "").strip().upper()
    if index_name != "NIFTY 50":
        continue

    symbol = (row.get("symbol") or "").strip().upper()
    valid_from = parse_date(row.get("valid_from"))
    valid_to = parse_date(row.get("valid_to"))

    if not symbol or not valid_from:
        continue

    # Keep every membership interval overlapping our project period.
    if valid_from <= END and (valid_to is None or valid_to > START):
        nifty_rows.append({
            **row,
            "symbol": symbol,
            "valid_from": valid_from.isoformat(),
            "valid_to": valid_to.isoformat() if valid_to else "",
        })

if not nifty_rows:
    raise RuntimeError(
        "No NIFTY 50 records found. Check source index_name and CSV schema."
    )

fields = list(nifty_rows[0].keys())
with OUTPUT.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(nifty_rows)

# One row per unique historical symbol.
unique = {}
for row in nifty_rows:
    symbol = row["symbol"]
    if symbol not in unique:
        unique[symbol] = {
            "symbol": symbol,
            "first_membership_start": row["valid_from"],
            "last_membership_end": row["valid_to"],
            "membership_intervals": 0,
            "sources": set(),
        }

    item = unique[symbol]
    item["membership_intervals"] += 1
    item["first_membership_start"] = min(
        item["first_membership_start"], row["valid_from"]
    )
    if row["valid_to"]:
        if not item["last_membership_end"] or row["valid_to"] > item["last_membership_end"]:
            item["last_membership_end"] = row["valid_to"]
    else:
        item["last_membership_end"] = "CURRENT"
    if row.get("source"):
        item["sources"].add(row["source"])

unique_rows = []
for item in unique.values():
    unique_rows.append({
        "symbol": item["symbol"],
        "first_membership_start": item["first_membership_start"],
        "last_membership_end": item["last_membership_end"],
        "membership_intervals": item["membership_intervals"],
        "source_types": " | ".join(sorted(item["sources"])),
    })

unique_rows.sort(key=lambda x: x["symbol"])

with UNIQUE_OUTPUT.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=unique_rows[0].keys())
    writer.writeheader()
    writer.writerows(unique_rows)

# Match against the symbols discovered in local Bhavcopy archives.
bhavcopy_file = DATA / "nse_all_symbols_2016_2026.csv"
if not bhavcopy_file.exists():
    raise FileNotFoundError(
        "Run the Bhavcopy symbol discovery first: " + str(bhavcopy_file)
    )

with bhavcopy_file.open("r", encoding="utf-8-sig", newline="") as f:
    bhavcopy_symbols = {
        (r.get("symbol") or "").strip().upper(): r
        for r in csv.DictReader(f)
    }

match_rows = []
for item in unique_rows:
    symbol = item["symbol"]
    bhav = bhavcopy_symbols.get(symbol)
    match_rows.append({
        **item,
        "bhavcopy_available": "YES" if bhav else "NO",
        "bhavcopy_first_date": bhav.get("first_observed_date", "") if bhav else "",
        "bhavcopy_last_date": bhav.get("last_observed_date", "") if bhav else "",
        "bhavcopy_rows": bhav.get("eq_rows_found", "") if bhav else "",
        "company_names_seen": bhav.get("company_names_seen", "") if bhav else "",
    })

with MATCH_OUTPUT.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=match_rows[0].keys())
    writer.writeheader()
    writer.writerows(match_rows)

available = sum(r["bhavcopy_available"] == "YES" for r in match_rows)
missing = len(match_rows) - available

print("\n========== GREEDY STOCKS: HISTORICAL NIFTY 50 ==========")
print("Period:", START, "to", END)
print("Historical membership intervals:", len(nifty_rows))
print("Unique historical NIFTY 50 symbols:", len(unique_rows))
print("Matched with local Bhavcopy:", available)
print("Not matched:", missing)

print("\nHISTORICAL UNIQUE SYMBOL LIST:")
for row in unique_rows:
    print(row["symbol"], "|", row["first_membership_start"],
          "to", row["last_membership_end"],
          "| intervals:", row["membership_intervals"])

print("\nFILES CREATED:")
print("Membership intervals:", OUTPUT)
print("Unique companies:", UNIQUE_OUTPUT)
print("Bhavcopy matching:", MATCH_OUTPUT)
print("Downloaded source:", HISTORY_FILE)

print("\nIMPORTANT:")
print("Historical intervals are not all equally certain.")
print("Review source types and pre-2018 coverage before production use.")
print("Symbol changes and mergers require separate corporate-action mapping.")
