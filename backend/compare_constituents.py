
import csv
import io
import zipfile
from pathlib import Path
from decimal import Decimal, InvalidOperation
from collections import Counter

REPORT_DIR = Path("database/raw/constituents")


def parse_decimal(value, field, symbol, issues):
    raw = (value or "").strip()

    if not raw:
        issues[f"missing_{field}"] += 1
        return None

    try:
        return Decimal(raw)
    except InvalidOperation:
        issues[f"invalid_{field}"] += 1
        print(
            f"INVALID VALUE | Symbol: {symbol} | "
            f"Field: {field} | Value: {raw!r}"
        )
        return None


def load_index_report(zip_path, target_csv):
    with zipfile.ZipFile(zip_path) as archive:
        content = archive.read(target_csv).decode("utf-8-sig")

    lines = content.splitlines()

    header_index = next(
        i for i, line in enumerate(lines)
        if line.startswith("Sr. No,")
    )

    reader = csv.DictReader(
        io.StringIO("\n".join(lines[header_index:]))
    )

    records = {}
    issues = Counter()
    duplicate_symbols = []

    for row in reader:
        symbol = (row.get("Security Symbol") or "").strip()

        if not symbol:
            continue

        if symbol in records:
            duplicate_symbols.append(symbol)
            continue

        weight = parse_decimal(
            row.get("Weightage (%)"),
            "weight",
            symbol,
            issues
        )

        if weight is None:
            issues["rows_without_valid_weight"] += 1

        records[symbol] = {
            "name": (row.get("Security Name") or "").strip(),
            "industry": (row.get("Basic Industry") or "").strip(),
            "weight": weight,
            "beta": parse_decimal(
                row.get("Beta"), "beta", symbol, issues
            ),
            "volatility": parse_decimal(
                row.get("Volatility (%)"),
                "volatility",
                symbol,
                issues
            ),
        }

    return records, issues, duplicate_symbols


def inspect_month(zip_path):
    results = {}

    with zipfile.ZipFile(zip_path) as archive:
        files = archive.namelist()

    for index_name in ("nifty50", "niftynext50"):
        expected = f"{index_name}_mcwb.csv"

        target = next(
            (
                name for name in files
                if Path(name).name.lower() == expected
            ),
            None
        )

        if target is None:
            raise RuntimeError(
                f"{expected} not found inside {zip_path.name}"
            )

        results[index_name] = load_index_report(zip_path, target)

    return results


reports = {}

for path in sorted(REPORT_DIR.glob("*.zip")):
    reports[path.stem] = inspect_month(path)

if len(reports) != 2:
    raise RuntimeError(
        f"Expected exactly 2 reports, found {len(reports)}"
    )

month_names = sorted(reports)
older_name, newer_name = month_names

print("\nCONSTITUENT REPORT VALIDATION")
print("=" * 65)
print(f"Older report: {older_name}")
print(f"Newer report: {newer_name}")

for month in month_names:
    print(f"\n{month.upper()}")

    for index_name, (records, issues, duplicates) in reports[month].items():
        valid_weights = [
            record["weight"]
            for record in records.values()
            if record["weight"] is not None
        ]

        weight_sum = sum(valid_weights, Decimal("0"))

        print(f"\n{index_name.upper()}")
        print(f"  Securities: {len(records)}")
        print(f"  Duplicate symbols: {len(duplicates)}")
        print(f"  Valid weights: {len(valid_weights)}")
        print(f"  Total reported weight: {weight_sum}%")
        print(f"  Missing/invalid fields: {dict(issues)}")

        if len(records) != 50:
            print("  WARNING: Expected 50 securities.")

        if duplicates:
            print(f"  Duplicate examples: {duplicates[:10]}")


print("\nMONTH-TO-MONTH MEMBERSHIP CHANGES")
print("=" * 65)

for index_name in ("nifty50", "niftynext50"):
    old = reports[older_name][index_name][0]
    new = reports[newer_name][index_name][0]

    old_symbols = set(old)
    new_symbols = set(new)

    print(f"\n{index_name.upper()}")
    print("Added:", sorted(new_symbols - old_symbols) or "None")
    print("Removed:", sorted(old_symbols - new_symbols) or "None")

    changed_weights = []

    for symbol in sorted(old_symbols & new_symbols):
        old_weight = old[symbol]["weight"]
        new_weight = new[symbol]["weight"]

        if (
            old_weight is not None
            and new_weight is not None
            and old_weight != new_weight
        ):
            changed_weights.append(
                (symbol, old_weight, new_weight)
            )

    print(f"Weight changes: {len(changed_weights)}")

    for symbol, old_weight, new_weight in changed_weights:
        print(f"  {symbol}: {old_weight}% -> {new_weight}%")


print("\nCOMPARISON COMPLETE — NO DATABASE CHANGES MADE.")
