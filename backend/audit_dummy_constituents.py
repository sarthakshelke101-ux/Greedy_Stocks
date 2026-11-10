
import zipfile
from pathlib import Path
import pandas as pd
import io

folder = Path("database/raw/constituents")
total_dummy_rows = 0

for archive in sorted(folder.glob("*.zip")):
    print(f"\n{'=' * 80}")
    print(f"REPORT: {archive.name}")

    with zipfile.ZipFile(archive) as z:
        for filename in z.namelist():

            if not filename.lower().endswith(".csv"):
                continue

            raw = pd.read_csv(
                io.BytesIO(z.read(filename)),
                header=None,
                dtype=str
            )

            # Find the actual header row
            header_index = None

            for i, row in raw.iterrows():
                values = row.fillna("").astype(str).str.strip().str.lower()

                if values.str.contains("security symbol", regex=False).any():
                    header_index = i
                    break

            if header_index is None:
                print(f"\nHEADER NOT FOUND: {filename}")
                print(raw.head(8).to_string(index=False, header=False))
                continue

            df = pd.read_csv(
                io.BytesIO(z.read(filename)),
                header=header_index,
                dtype=str
            )

            df.columns = df.columns.astype(str).str.strip()

            symbol_col = next(
                (c for c in df.columns if "security symbol" in c.lower()),
                None
            )

            if symbol_col is None:
                print(f"\nSYMBOL COLUMN NOT FOUND: {filename}")
                continue

            symbols = df[symbol_col].fillna("").str.strip().str.upper()
            dummy_rows = df[symbols.str.contains("DUMMY", regex=False)]

            if not dummy_rows.empty:
                total_dummy_rows += len(dummy_rows)

                print(f"\nINDEX FILE: {filename}")
                print(f"HEADER ROW: {header_index}")
                print(f"DUMMY ROWS: {len(dummy_rows)}")
                print(dummy_rows.to_string(index=False))

print("\n" + "=" * 80)
print(f"TOTAL DUMMY ROWS FOUND: {total_dummy_rows}")
print("AUDIT COMPLETE — ORIGINAL ZIP FILES UNCHANGED.")
