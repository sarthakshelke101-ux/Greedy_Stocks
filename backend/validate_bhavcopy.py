
from pathlib import Path
from zipfile import ZipFile
from collections import Counter
from decimal import Decimal, InvalidOperation
import csv
import io

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "database" / "raw" / "bhavcopy"

REQUIRED = {
    "TradDt", "TckrSymb", "SctySrs",
    "OpnPric", "HghPric", "LwPric",
    "ClsPric", "PrvsClsgPric",
    "TtlTradgVol", "TtlTrfVal",
    "TtlNbOfTxsExctd"
}

stats = Counter()
issues = Counter()
symbols = Counter()
series = Counter()
dates = set()

def number(value):
    try:
        result = Decimal(value.strip())
        if not result.is_finite():
            return None
        return result
    except (InvalidOperation, AttributeError):
        return None

for archive_path in sorted(FOLDER.glob("*.zip")):
    if archive_path.name.upper() == "ZIPPED.ZIP":
        continue

    try:
        with ZipFile(archive_path) as archive:
            csv_files = [
                item for item in archive.namelist()
                if item.lower().endswith(".csv")
            ]

            for member in csv_files:
                with archive.open(member) as raw:
                    text = io.TextIOWrapper(
                        raw, encoding="utf-8-sig", newline=""
                    )
                    reader = csv.DictReader(text)

                    if not REQUIRED.issubset(set(reader.fieldnames or [])):
                        issues["schema_errors"] += 1
                        continue

                    for row in reader:
                        stats["rows"] += 1

                        symbol = (row.get("TckrSymb") or "").strip()
                        trading_date = (row.get("TradDt") or "").strip()
                        security_series = (row.get("SctySrs") or "").strip()

                        if not symbol:
                            issues["missing_symbols"] += 1
                            continue

                        symbols[symbol] += 1
                        series[security_series] += 1

                        if not trading_date:
                            issues["missing_dates"] += 1
                        else:
                            dates.add(trading_date)

                        prices = {
                            key: number(row.get(key))
                            for key in [
                                "OpnPric", "HghPric",
                                "LwPric", "ClsPric",
                                "PrvsClsgPric"
                            ]
                        }

                        if any(v is None for v in prices.values()):
                            issues["invalid_prices"] += 1
                            continue

                        if any(v <= 0 for v in prices.values()):
                            issues["non_positive_prices"] += 1

                        if prices["HghPric"] < prices["LwPric"]:
                            issues["high_below_low"] += 1

                        if prices["HghPric"] < max(
                            prices["OpnPric"], prices["ClsPric"]
                        ):
                            issues["high_below_open_or_close"] += 1

                        if prices["LwPric"] > min(
                            prices["OpnPric"], prices["ClsPric"]
                        ):
                            issues["low_above_open_or_close"] += 1

                        volume = number(row.get("TtlTradgVol"))
                        value = number(row.get("TtlTrfVal"))
                        trades = number(row.get("TtlNbOfTxsExctd"))

                        if volume is None or volume < 0:
                            issues["invalid_volume"] += 1

                        if value is None or value < 0:
                            issues["invalid_turnover"] += 1

                        if trades is None or trades < 0:
                            issues["invalid_trade_count"] += 1

    except Exception as error:
        issues["archive_errors"] += 1
        print(f"ERROR: {archive_path.name}: {error}")

print("\n" + "=" * 55)
print("GREEDY STOCKS - DEEP DATA VALIDATION")
print("=" * 55)

print(f"Total rows examined: {stats['rows']}")
print(f"Unique symbols: {len(symbols)}")
print(f"Unique trading dates: {len(dates)}")
print(f"First date: {min(dates) if dates else 'N/A'}")
print(f"Last date: {max(dates) if dates else 'N/A'}")

print("\nSECURITY SERIES")
for name, count in series.most_common():
    print(f"{name or '(blank)'}: {count}")

print("\nTOP 20 SYMBOLS")
for name, count in symbols.most_common(20):
    print(f"{name}: {count}")

print("\nVALIDATION ISSUES")
if issues:
    for name, count in issues.most_common():
        print(f"{name}: {count}")
else:
    print("No validation issues detected.")

print("\nOriginal ZIP archives were not modified.")
