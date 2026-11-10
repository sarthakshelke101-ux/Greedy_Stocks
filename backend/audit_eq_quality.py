
import csv
import zipfile
from pathlib import Path
from collections import Counter
from decimal import Decimal, InvalidOperation

DATA_DIR = Path("database/raw/bhavcopy")

stats = Counter()
issues = Counter()
examples = []

def parse_number(value):
    try:
        if value is None or not value.strip():
            return None
        return Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        return None

for zip_path in sorted(DATA_DIR.glob("*.zip")):
    if zip_path.name.upper() == "ZIPPED.ZIP":
        continue

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            if not member.lower().endswith(".csv"):
                continue

            with archive.open(member) as file:
                reader = csv.DictReader(
                    line.decode("utf-8-sig") for line in file
                )

                for row in reader:
                    if row.get("SctySrs", "").strip() != "EQ":
                        continue

                    stats["eq_rows"] += 1

                    fields = {
                        "volume": "TtlTradgVol",
                        "traded_value": "TtlTrfVal",
                        "trades": "TtlNbOfTxsExctd",
                    }

                    parsed = {}

                    for name, column in fields.items():
                        raw = row.get(column)
                        value = parse_number(raw)
                        parsed[name] = value

                        if raw is None or not raw.strip():
                            issues[f"missing_{name}"] += 1
                        elif value is None:
                            issues[f"invalid_{name}"] += 1
                        elif value < 0:
                            issues[f"negative_{name}"] += 1
                        elif value == 0:
                            issues[f"zero_{name}"] += 1

                    volume = parsed["volume"]
                    value = parsed["traded_value"]
                    trades = parsed["trades"]

                    if volume is not None and value is not None:
                        if volume > 0 and value == 0:
                            issues["positive_volume_zero_value"] += 1

                        if volume == 0 and value > 0:
                            issues["zero_volume_positive_value"] += 1

                    if volume is not None and trades is not None:
                        if volume > 0 and trades == 0:
                            issues["positive_volume_zero_trades"] += 1

                        if volume == 0 and trades > 0:
                            issues["zero_volume_positive_trades"] += 1

                    if any(
                        parsed[name] is None or parsed[name] <= 0
                        for name in fields
                    ) and len(examples) < 15:
                        examples.append({
                            "date": row.get("TradDt"),
                            "symbol": row.get("TckrSymb"),
                            **parsed,
                        })

print("\nEQ VOLUME / VALUE / TRADE COUNT AUDIT")
print("=" * 60)
print(f"Total EQ records: {stats['eq_rows']:,}")

print("\nQUALITY CHECK COUNTS")
print("=" * 60)

if not issues:
    print("No missing, invalid, negative or zero values found.")
else:
    for name, count in sorted(issues.items()):
        print(f"{name:40} {count:>10,}")

print("\nSUSPICIOUS RECORD EXAMPLES")
print("=" * 60)

if not examples:
    print("No suspicious records found.")
else:
    for example in examples:
        print(example)

print("\nAUDIT COMPLETE — ORIGINAL ARCHIVES NOT MODIFIED.")
