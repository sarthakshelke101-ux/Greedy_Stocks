
from pathlib import Path
from zipfile import ZipFile
from collections import Counter
from decimal import Decimal, InvalidOperation
import csv
import io

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "database" / "raw" / "bhavcopy"

stats = Counter()
examples = {}

def dec(value):
    try:
        result = Decimal(value.strip())
        return result if result.is_finite() else None
    except (InvalidOperation, AttributeError):
        return None

for archive_path in sorted(FOLDER.glob("*.zip")):
    if archive_path.name.upper() == "ZIPPED.ZIP":
        continue

    with ZipFile(archive_path) as archive:
        for member in archive.namelist():
            if not member.lower().endswith(".csv"):
                continue

            with archive.open(member) as raw:
                text = io.TextIOWrapper(
                    raw, encoding="utf-8-sig", newline=""
                )
                reader = csv.DictReader(text)

                for row in reader:
                    series = (row.get("SctySrs") or "").strip()
                    values = [
                        dec(row.get(key, ""))
                        for key in [
                            "OpnPric", "HghPric",
                            "LwPric", "ClsPric"
                        ]
                    ]

                    if any(value is None for value in values):
                        continue

                    op, hi, lo, cl = values
                    low_issue = lo > min(op, cl)
                    high_issue = hi < max(op, cl)

                    if low_issue or high_issue:
                        stats[(series, "anomalies")] += 1

                        if len(examples.get(series, [])) < 3:
                            examples.setdefault(series, []).append({
                                "date": row.get("TradDt"),
                                "symbol": row.get("TckrSymb"),
                                "open": str(op),
                                "high": str(hi),
                                "low": str(lo),
                                "close": str(cl),
                            })

                    stats[(series, "rows")] += 1

print("\nANOMALIES BY SECURITY SERIES")
print("=" * 55)

for series in sorted({key[0] for key in stats}):
    total = stats[(series, "rows")]
    flagged = stats[(series, "anomalies")]
    print(
        f"{series or '(blank)':8} "
        f"Rows: {total:>9,} "
        f"Anomalies: {flagged:>5,}"
    )

print("\nEXAMPLES BY AFFECTED SERIES")
print("=" * 55)

for series, records in sorted(examples.items()):
    print(f"\nSERIES: {series}")
    for record in records:
        print(record)
