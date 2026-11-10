
from pathlib import Path
from zipfile import ZipFile
import csv
import io

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "database" / "raw" / "bhavcopy"

count = 0
limit = 30

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
                    try:
                        op = float(row["OpnPric"])
                        hi = float(row["HghPric"])
                        lo = float(row["LwPric"])
                        cl = float(row["ClsPric"])
                    except (ValueError, TypeError, KeyError):
                        continue

                    low_issue = lo > min(op, cl)
                    high_issue = hi < max(op, cl)

                    if low_issue or high_issue:
                        count += 1

                        if count <= limit:
                            print("-" * 60)
                            print("FILE:", archive_path.name)
                            print("DATE:", row.get("TradDt"))
                            print("SYMBOL:", row.get("TckrSymb"))
                            print("SERIES:", row.get("SctySrs"))
                            print("OPEN:", op)
                            print("HIGH:", hi)
                            print("LOW:", lo)
                            print("CLOSE:", cl)
                            print("LOW ISSUE:", low_issue)
                            print("HIGH ISSUE:", high_issue)

print("\nTotal flagged records:", count)
print("Examples displayed:", min(count, limit))
