
import csv
import io
import re
import zipfile

from pathlib import Path
from datetime import datetime
from decimal import Decimal, InvalidOperation

REPORT_DIR = Path("database/raw/constituents")

INDEX_FILES = {
    "NIFTY50": "nifty50_mcwb.csv",
    "NIFTYNEXT50": "niftynext50_mcwb.csv",
}

MONTH_NAMES = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def get_report_month(path):
    match = re.search(
        r"mcwb_([a-z]+)(\d{2})",
        path.stem,
        re.IGNORECASE
    )

    if not match:
        raise ValueError(
            f"Cannot identify report month from {path.name}"
        )

    month_text = match.group(1).lower()
    year = 2000 + int(match.group(2))

    month_number = MONTH_NAMES.get(month_text)

    if month_number is None:
        raise ValueError(
            f"Unknown month '{month_text}' in {path.name}"
        )

    return datetime(year, month_number, 1)


def parse_decimal(value):
    try:
        raw = (value or "").strip()

        if not raw or raw == "-":
            return None

        return Decimal(raw)

    except InvalidOperation:
        return None


def load_index(archive, target):
    member = next(
        (
            name for name in archive.namelist()
            if Path(name).name.lower() == target.lower()
        ),
        None
    )

    if member is None:
        raise ValueError(f"Missing file: {target}")

    content = archive.read(member).decode("utf-8-sig")
    lines = content.splitlines()

    header_index = next(
        (
            i for i, line in enumerate(lines)
            if line.startswith("Sr. No,")
        ),
        None
    )

    if header_index is None:
        raise ValueError(
            f"CSV header not found in {target}"
        )

    reader = csv.DictReader(
        io.StringIO("\n".join(lines[header_index:]))
    )

    records = {}
    duplicates = []
    invalid_weights = []
    missing_beta = []

    for row in reader:
        symbol = (row.get("Security Symbol") or "").strip()

        if not symbol:
            continue

        if symbol in records:
            duplicates.append(symbol)
            continue

        weight = parse_decimal(row.get("Weightage (%)"))
        beta = parse_decimal(row.get("Beta"))

        if weight is None:
            invalid_weights.append(symbol)

        if beta is None:
            missing_beta.append(symbol)

        records[symbol] = {
            "name": (row.get("Security Name") or "").strip(),
            "industry": (row.get("Basic Industry") or "").strip(),
            "weight": weight,
            "beta": beta,
        }

    valid_weights = [
        record["weight"]
        for record in records.values()
        if record["weight"] is not None
    ]

    weight_sum = sum(valid_weights, Decimal("0"))

    return {
        "records": records,
        "duplicates": duplicates,
        "invalid_weights": invalid_weights,
        "missing_beta": missing_beta,
        "weight_sum": weight_sum,
    }


# --------------------------------------------------
# DISCOVER AND SORT MONTHLY REPORTS
# --------------------------------------------------

paths = sorted(
    REPORT_DIR.glob("*.zip"),
    key=get_report_month
)

if not paths:
    raise RuntimeError(
        f"No monthly ZIP reports found in {REPORT_DIR}"
    )

reports = {}

print("\nFULL HISTORICAL CONSTITUENT AUDIT")
print("=" * 75)

# --------------------------------------------------
# VALIDATE EACH MONTH
# --------------------------------------------------

for path in paths:
    month = get_report_month(path)
    month_key = month.strftime("%Y-%m")

    if month_key in reports:
        raise RuntimeError(
            f"Duplicate monthly report detected: {month_key}"
        )

    print(f"\nREPORT: {path.name} | {month_key}")
    print("-" * 75)

    with zipfile.ZipFile(path) as archive:
        bad_file = archive.testzip()

        if bad_file:
            raise RuntimeError(
                f"ZIP integrity failure: {path.name} -> {bad_file}"
            )

        reports[month_key] = {}

        for index_name, csv_name in INDEX_FILES.items():
            result = load_index(archive, csv_name)

            reports[month_key][index_name] = result

            records = result["records"]

            print(
                f"{index_name:15} "
                f"Count: {len(records):2} | "
                f"Duplicates: {len(result['duplicates']):2} | "
                f"Weight: {result['weight_sum']}% | "
                f"Invalid weights: {len(result['invalid_weights'])} | "
                f"Missing beta: {len(result['missing_beta'])}"
            )

            if len(records) != 50:
                print(
                    f"  WARNING: Expected 50 securities, "
                    f"found {len(records)}."
                )

            if result["duplicates"]:
                print(
                    "  Duplicate symbols:",
                    result["duplicates"]
                )

            if result["invalid_weights"]:
                print(
                    "  Invalid weight symbols:",
                    result["invalid_weights"]
                )

            if result["missing_beta"]:
                print(
                    "  Missing Beta symbols:",
                    result["missing_beta"]
                )


# --------------------------------------------------
# MONTH-TO-MONTH MEMBERSHIP CHANGES
# --------------------------------------------------

print("\nMONTH-TO-MONTH MEMBERSHIP CHANGES")
print("=" * 75)

months = sorted(reports)

for index_name in INDEX_FILES:
    print(f"\n{index_name}")

    previous = None

    for month in months:
        current = set(
            reports[month][index_name]["records"]
        )

        if previous is None:
            print(
                f"{month}: Baseline "
                f"({len(current)} securities)"
            )
        else:
            added = sorted(current - previous)
            removed = sorted(previous - current)

            print(
                f"{month}: "
                f"Added={added or 'None'} | "
                f"Removed={removed or 'None'}"
            )

        previous = current


# --------------------------------------------------
# EXPECTED MONTH COVERAGE
# --------------------------------------------------

print("\nMONTH COVERAGE")
print("=" * 75)

expected_months = {
    f"{year}-{month:02d}"
    for year in (2025, 2026)
    for month in range(1, 13)
    if (
        (year == 2025 and month >= 4)
        or
        (year == 2026 and month <= 11)
    )
}

found_months = set(months)

missing_months = sorted(expected_months - found_months)
unexpected_months = sorted(found_months - expected_months)

print(f"Reports found: {len(found_months)}")
print(f"Expected reports: {len(expected_months)}")
print("Missing months:", missing_months or "None")
print("Unexpected months:", unexpected_months or "None")

print("\nAUDIT COMPLETE — NO DATABASE CHANGES MADE.")
