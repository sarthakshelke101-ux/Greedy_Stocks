
from pathlib import Path
from zipfile import ZipFile, BadZipFile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FOLDER = PROJECT_ROOT / "database" / "raw" / "bhavcopy"

for zip_path in sorted(DATA_FOLDER.glob("*.zip")):
    try:
        with ZipFile(zip_path, "r") as archive:
            csv_files = [
                name for name in archive.namelist()
                if name.lower().endswith(".csv")
            ]

            if not csv_files:
                print(f"\nNO CSV: {zip_path.name}")
                print("Archive contents:")
                for name in archive.namelist():
                    print(f"  {name}")

    except BadZipFile:
        print(f"\nINVALID ZIP: {zip_path.name}")
