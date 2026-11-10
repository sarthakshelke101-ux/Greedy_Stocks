import csv
import io
import zipfile
from pathlib import Path
from collections import defaultdict
from datetime import datetime

ROOT = Path.cwd()
DATA = ROOT / "database" / "raw" / "bhavcopy"
OUTPUT = DATA / "nse_all_symbols_2016_2026.csv"

stats = defaultdict(lambda: {
    "names": set(), "first": None, "last": None,
    "rows": 0, "archives": set()
})

files = sorted(DATA.rglob("*.zip")) + sorted(DATA.rglob("*.csv"))
files = [p for p in files if p.name != OUTPUT.name]

def parse_date(value):
    value = (value or "").strip()
    if not value:
        return None

    formats = (
        "%d-%b-%Y", "%d-%b-%y",
        "%Y-%m-%d", "%d-%m-%Y",
        "%d/%m/%Y", "%Y%m%d",
    )

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    return None

def process_csv(raw, source):
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp1252", errors="replace")

    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return 0

    columns = {
        str(c).strip().lstrip("\ufeff").lower(): c
        for c in reader.fieldnames if c
    }

    symbol_col = columns.get("symbol") or columns.get("tckrsymb")
    series_col = columns.get("series") or columns.get("sctysrs")
    name_col = columns.get("name") or columns.get("fininstrmnm")
    date_col = (
        columns.get("timestamp") or columns.get("traddt")
        or columns.get("bizdt") or columns.get("trad_date")
    )

    if not symbol_col or not series_col:
        return 0

    found = 0

    for row in reader:
        symbol = (row.get(symbol_col) or "").strip().upper()
        series = (row.get(series_col) or "").strip().upper()

        if not symbol or series != "EQ":
            continue

        item = stats[symbol]
        name = (row.get(name_col) or "").strip() if name_col else ""
        if name:
            item["names"].add(name)

        item["rows"] += 1
        item["archives"].add(source)

        raw_date = row.get(date_col) if date_col else ""
        trade_date = parse_date(raw_date)

        if trade_date:
            if item["first"] is None or trade_date < item["first"]:
                item["first"] = trade_date
            if item["last"] is None or trade_date > item["last"]:
                item["last"] = trade_date

        found += 1

    return found

processed = 0
rows_found = 0
errors = []

for index, path in enumerate(files, 1):
    try:
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as z:
                for member in z.namelist():
                    if member.lower().endswith(".csv"):
                        rows_found += process_csv(z.read(member), path.name)
                        processed += 1
        else:
            rows_found += process_csv(path.read_bytes(), path.name)
            processed += 1

    except Exception as e:
        errors.append(f"{path.name}: {e}")

    if index % 250 == 0:
        print(f"Scanned {index}/{len(files)} files...", flush=True)

output_rows = []

for symbol, item in sorted(stats.items()):
    output_rows.append({
        "symbol": symbol,
        "company_names_seen": " | ".join(sorted(item["names"])),
        "first_observed_date": item["first"] or "",
        "last_observed_date": item["last"] or "",
        "eq_rows_found": item["rows"],
        "source_files": len(item["archives"]),
    })

with OUTPUT.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "symbol", "company_names_seen", "first_observed_date",
        "last_observed_date", "eq_rows_found", "source_files"
    ])
    writer.writeheader()
    writer.writerows(output_rows)

dated = sum(1 for x in output_rows if x["first_observed_date"])

print("\n========== CORRECTED SYMBOL DISCOVERY ==========")
print("Files processed:", processed)
print("EQ rows scanned:", rows_found)
print("Unique EQ symbols:", len(output_rows))
print("Symbols with valid dates:", dated)
print("Symbols without valid dates:", len(output_rows) - dated)
print("Read errors:", len(errors))

print("\nIMPORTANT SYMBOLS:")
for symbol in ["RELIANCE", "TCS", "INFY", "TATAMOTORS",
               "TMPV", "HDFCBANK", "ICICIBANK"]:
    item = next((x for x in output_rows if x["symbol"] == symbol), None)
    if item:
        print(symbol, "|", item["first_observed_date"],
              "to", item["last_observed_date"])

print("\nMASTER CSV:", OUTPUT)

if errors:
    print("\nFIRST 10 ERRORS:")
    for error in errors[:10]:
        print(error)
