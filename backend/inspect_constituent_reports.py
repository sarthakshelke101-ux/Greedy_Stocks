
import zipfile
from pathlib import Path

REPORT_DIR = Path("database/raw/constituents")

for zip_path in sorted(REPORT_DIR.glob("*.zip")):
    print("\n" + "=" * 60)
    print(f"FILE: {zip_path.name}")
    print("=" * 60)

    with zipfile.ZipFile(zip_path) as archive:
        print("ZIP integrity:", archive.testzip() or "OK")

        for item in archive.infolist():
            print(
                f"Name: {item.filename} | "
                f"Size: {item.file_size:,} bytes"
            )

            if item.filename.lower().endswith((".csv", ".txt")):
                content = archive.read(item.filename)
                print("\nFIRST 2,000 CHARACTERS:")
                print(content[:2000].decode("utf-8-sig", errors="replace"))
