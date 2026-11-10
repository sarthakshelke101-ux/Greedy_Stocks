
import csv
import re
import zipfile
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
from statistics import median

DATA_DIR = Path("database/raw/bhavcopy")

rows_per_date = Counter()
symbols_per_date = defaultdict(set)
dates_per_symbol = defaultdict(set)

filename_date_mismatches = []
invalid_dates = []
files_without_csv = []

total_eq_rows = 0
total_csv_files = 0

for zip_path in sorted(DATA_DIR.glob("*.zip")):
    if zip_path.name.upper() == "ZIPPED.ZIP":
        continue

    match = re.search(r"(\d{8})", zip_path.name)
    filename_date = None

    if match:
        try:
            filename_date = datetime.strptime(
                match.group(1), "%Y%m%d"
            ).date()
        except ValueError:
            filename_date = None

    with zipfile.ZipFile(zip_path) as archive:
        csv_members = [
            name for name in archive.namelist()
            if name.lower().endswith(".csv")
        ]

        if not csv_members:
            files_without_csv.append(zip_path.name)
            continue

        for member in csv_members:
            total_csv_files += 1

            with archive.open(member) as file:
                reader = csv.DictReader(
                    line.decode("utf-8-sig") for line in file
                )

                for row in reader:
                    if row.get("SctySrs", "").strip() != "EQ":
                        continue

                    total_eq_rows += 1

                    raw_date = row.get("TradDt", "").strip()
                    symbol = row.get("TckrSymb", "").strip()

                    try:
                        trade_date = datetime.strptime(
                            raw_date, "%Y-%m-%d"
                        ).date()
                    except ValueError:
                        invalid_dates.append({
                            "file": zip_path.name,
                            "date": raw_date,
                            "symbol": symbol,
                        })
                        continue

                    if filename_date and trade_date != filename_date:
                        if len(filename_date_mismatches) < 20:
                            filename_date_mismatches.append({
                                "file": zip_path.name,
                                "filename_date": str(filename_date),
                                "csv_date": str(trade_date),
                            })

                    rows_per_date[trade_date] += 1
                    symbols_per_date[trade_date].add(symbol)
                    dates_per_symbol[symbol].add(trade_date)

all_dates = sorted(rows_per_date)
row_counts = list(rows_per_date.values())
symbol_counts = [
    len(symbols_per_date[d]) for d in all_dates
]

print("\nTRADING DATE & SYMBOL COVERAGE AUDIT")
print("=" * 65)

print(f"CSV files inspected: {total_csv_files:,}")
print(f"Total EQ records: {total_eq_rows:,}")
print(f"Unique trading dates: {len(all_dates):,}")
print(f"Unique EQ symbols: {len(dates_per_symbol):,}")

if all_dates:
    print(f"First trading date: {all_dates[0]}")
    print(f"Last trading date:  {all_dates[-1]}")

print("\nDAILY COVERAGE")
print("=" * 65)

if row_counts:
    print(f"Minimum EQ rows/day: {min(row_counts):,}")
    print(f"Median EQ rows/day:  {median(row_counts):,.0f}")
    print(f"Maximum EQ rows/day: {max(row_counts):,}")
    print(f"Minimum symbols/day: {min(symbol_counts):,}")
    print(f"Median symbols/day:  {median(symbol_counts):,.0f}")
    print(f"Maximum symbols/day: {max(symbol_counts):,}")

    threshold = median(row_counts) * 0.80
    low_days = [
        (d, rows_per_date[d], len(symbols_per_date[d]))
        for d in all_dates
        if rows_per_date[d] < threshold
    ]

    print(f"\nDates below 80% of median row count: {len(low_days)}")
    for d, count, symbol_count in low_days[:20]:
        print(
            f"{d} | EQ rows: {count:,} | Symbols: {symbol_count:,}"
        )

print("\nSYMBOL COVERAGE")
print("=" * 65)

symbol_summary = sorted(
    (
        (symbol, len(dates), min(dates), max(dates))
        for symbol, dates in dates_per_symbol.items()
    ),
    key=lambda item: item[1]
)

print("10 symbols with the fewest recorded dates:")
for symbol, count, first, last in symbol_summary[:10]:
    print(f"{symbol:20} {count:5,} dates | {first} to {last}")

print("\n10 symbols with the most recorded dates:")
for symbol, count, first, last in symbol_summary[-10:]:
    print(f"{symbol:20} {count:5,} dates | {first} to {last}")

print("\nARCHIVE / DATE CONSISTENCY")
print("=" * 65)
print(f"Filename-vs-CSV date mismatches: {len(filename_date_mismatches)}")
print(f"Invalid CSV dates: {len(invalid_dates)}")
print(f"ZIP files without CSV: {len(files_without_csv)}")

for item in filename_date_mismatches:
    print("MISMATCH:", item)

for item in invalid_dates[:10]:
    print("INVALID DATE:", item)

for item in files_without_csv[:10]:
    print("NO CSV:", item)

print("\nAUDIT COMPLETE — ORIGINAL ARCHIVES NOT MODIFIED.")
