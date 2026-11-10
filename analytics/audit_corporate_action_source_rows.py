from pathlib import Path
from zipfile import ZipFile
from io import BytesIO
import pandas as pd

ROOT = Path("database/raw/bhavcopy")

targets = {
    ("BAJFINANCE", "2025-06-13", "2025-06-16"),
    ("KOTAKBANK", "2026-01-13", "2026-01-14"),
    ("BSE", "2025-05-22", "2025-05-23"),
    ("NESTLEIND", "2025-08-07", "2025-08-08"),
    ("HDFCBANK", "2025-08-25", "2025-08-26"),
    ("TRENT", "2026-06-03", "2026-06-04"),
}

symbols = {item[0] for item in targets}
dates_needed = {
    date
    for _, previous, event in targets
    for date in (previous, event)
}

found = []

for archive in ROOT.glob("*.zip"):
    try:
        with ZipFile(archive) as z:
            for member in z.namelist():
                if not member.lower().endswith(".csv"):
                    continue

                with z.open(member) as file:
                    frame = pd.read_csv(file, low_memory=False)

                required = {
                    "TradDt", "TckrSymb", "ISIN",
                    "SctySrs", "PrvsClsgPric", "ClsPric"
                }

                if not required.issubset(frame.columns):
                    continue

                frame["TradDt"] = pd.to_datetime(
                    frame["TradDt"], errors="coerce"
                ).dt.strftime("%Y-%m-%d")

                selected = frame[
                    frame["TckrSymb"].isin(symbols)
                    & frame["TradDt"].isin(dates_needed)
                ]

                if not selected.empty:
                    selected = selected.copy()
                    selected["archive"] = archive.name
                    found.append(selected)

    except Exception as exc:
        print("ARCHIVE ERROR:", archive.name, str(exc))

if not found:
    print("No matching source records found.")
else:
    result = pd.concat(found, ignore_index=True)

    columns = [
        "TradDt", "TckrSymb", "ISIN", "SctySrs",
        "PrvsClsgPric", "ClsPric", "archive"
    ]

    result = result.sort_values(["TckrSymb", "TradDt", "SctySrs"])

    print("\nORIGINAL NSE BHAVCOPY RECORDS")
    print("=" * 110)
    print(result[columns].to_string(index=False))

    print("\nSOURCE ROW COUNTS")
    print(result.groupby(["TckrSymb", "TradDt"]).size().to_string())

print("\nSOURCE FILES READ:", len(list(ROOT.glob("*.zip"))))
print("DATABASE WRITES: NONE")
