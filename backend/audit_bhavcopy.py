
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from collections import Counter
import csv
import io

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FOLDER = PROJECT_ROOT / "database" / "raw" / "bhavcopy"

EXPECTED_COLUMNS = {
    "TradDt",
    "TckrSymb",
    "SctySrs",
    "OpnPric",
    "HghPric",
    "LwPric",
    "ClsPric",
    "PrvsClsgPric",
    "TtlTradgVol",
    "TtlTrfVal",
    "TtlNbOfTxsExctd",
}

def audit():
    print("=" * 65)
    print("GREEDY STOCKS - NSE BHAVCOPY READ-ONLY AUDIT")
    print("=" * 65)

    if not DATA_FOLDER.exists():
        print(f"ERROR: Folder not found: {DATA_FOLDER}")
        return

    zip_files = sorted(DATA_FOLDER.glob("*.zip"))

    print(f"\nDataset folder: {DATA_FOLDER}")
    print(f"ZIP archives found: {len(zip_files)}")

    if not zip_files:
        print("\nNo ZIP files found. Check the folder location.")
        return

    total_csv = 0
    total_rows = 0
    total_bad = 0
    date_counts = Counter()
    duplicate_hashes = {}
    seen_hashes = set()

    import hashlib

    for number, zip_path in enumerate(zip_files, start=1):
        print(f"\n[{number}/{len(zip_files)}] {zip_path.name}")

        try:
            with ZipFile(zip_path, "r") as archive:
                bad_member = archive.testzip()

                if bad_member:
                    print(f"  CORRUPT MEMBER: {bad_member}")
                    total_bad += 1
                    continue

                csv_members = [
                    item for item in archive.infolist()
                    if not item.is_dir()
                    and item.filename.lower().endswith(".csv")
                ]

                if not csv_members:
                    print("  WARNING: No CSV file inside archive")
                    continue

                for member in csv_members:
                    total_csv += 1
                    content = archive.read(member)
                    digest = hashlib.sha256(content).hexdigest()

                    if digest in seen_hashes:
                        duplicate_hashes[digest] = (
                            duplicate_hashes.get(digest, 1) + 1
                        )
                        print(f"  DUPLICATE CONTENT: {member.filename}")
                        continue

                    seen_hashes.add(digest)

                    try:
                        text = content.decode("utf-8-sig")
                        reader = csv.DictReader(io.StringIO(text))

                        columns = set(reader.fieldnames or [])
                        missing = EXPECTED_COLUMNS - columns

                        if missing:
                            print(
                                "  UNEXPECTED SCHEMA. Missing columns:",
                                sorted(missing)
                            )
                            continue

                        rows = 0
                        file_dates = set()

                        for row in reader:
                            rows += 1
                            date = row.get("TradDt", "").strip()
                            if date:
                                file_dates.add(date)

                        total_rows += rows

                        for date in file_dates:
                            date_counts[date] += 1

                        print(f"  CSV: {member.filename}")
                        print(f"  Rows: {rows}")
                        print(f"  Trading dates: {sorted(file_dates)}")
                        print("  Schema: VALID")

                    except UnicodeDecodeError:
                        print("  ERROR: CSV encoding is not UTF-8")
                        total_bad += 1
                    except Exception as error:
                        print(f"  CSV ERROR: {error}")
                        total_bad += 1

        except BadZipFile:
            print("  ERROR: Invalid ZIP archive")
            total_bad += 1
        except Exception as error:
            print(f"  ERROR: {error}")
            total_bad += 1

    print("\n" + "=" * 65)
    print("AUDIT SUMMARY")
    print("=" * 65)
    print(f"ZIP archives: {len(zip_files)}")
    print(f"CSV files inspected: {total_csv}")
    print(f"Total CSV rows: {total_rows}")
    print(f"Files with errors: {total_bad}")
    print(f"Unique trading dates: {len(date_counts)}")
    print(f"Duplicate CSV contents: {len(duplicate_hashes)}")

    if date_counts:
        print(f"First date: {min(date_counts)}")
        print(f"Last date: {max(date_counts)}")

    print("\nAUDIT COMPLETE - ORIGINAL FILES WERE NOT MODIFIED")

if __name__ == "__main__":
    audit()
