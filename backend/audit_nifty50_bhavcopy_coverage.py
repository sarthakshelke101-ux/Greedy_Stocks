
from pathlib import Path
from collections import defaultdict
from zipfile import ZipFile
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

BHAVCOPY_DIR = ROOT / "database" / "raw" / "bhavcopy"

CONSTITUENT_FILE = (
    ROOT / "database" / "processed" /
    "constituents" / "nifty50_constituent_snapshots.csv"
)

EXPECTED_COLUMNS = [
    "TradDt",
    "ISIN",
    "TckrSymb",
    "SctySrs",
]


def main():
    constituents = pd.read_csv(
        CONSTITUENT_FILE,
        dtype=str
    )

    symbols = set(
        constituents["Security Symbol"]
        .dropna()
        .str.strip()
        .str.upper()
    )

    archives = sorted(BHAVCOPY_DIR.glob("*.zip"))

    if not archives:
        raise FileNotFoundError(
            f"No ZIP archives found in {BHAVCOPY_DIR}"
        )

    stats = defaultdict(
        lambda: {
            "rows": 0,
            "dates": set(),
            "isins": set(),
            "series": set(),
            "duplicate_rows": 0,
        }
    )

    total_matching_rows = 0
    total_files = 0
    errors = []

    print(f"Historical NIFTY 50 symbols: {len(symbols)}")
    print(f"Bhavcopy archives discovered: {len(archives)}")
    print("Starting read-only coverage audit...\n")

    for archive_path in archives:
        try:
            with ZipFile(archive_path) as archive:
                csv_files = [
                    name for name in archive.namelist()
                    if name.lower().endswith(".csv")
                ]

                if len(csv_files) != 1:
                    errors.append(
                        f"{archive_path.name}: "
                        f"Expected 1 CSV, found {len(csv_files)}"
                    )
                    continue

                with archive.open(csv_files[0]) as file:
                    df = pd.read_csv(
                        file,
                        usecols=EXPECTED_COLUMNS,
                        dtype=str,
                    )

            total_files += 1

            df["TckrSymb"] = (
                df["TckrSymb"]
                .fillna("")
                .str.strip()
                .str.upper()
            )

            df["SctySrs"] = (
                df["SctySrs"]
                .fillna("")
                .str.strip()
                .str.upper()
            )

            matched = df[
                df["TckrSymb"].isin(symbols)
            ].copy()

            total_matching_rows += len(matched)

            # Keep all matching series for investigation.
            for row in matched.itertuples(index=False):
                date_value = getattr(row, "TradDt")
                isin_value = getattr(row, "ISIN")
                symbol = getattr(row, "TckrSymb")
                series = getattr(row, "SctySrs")

                item = stats[symbol]

                item["rows"] += 1

                if pd.notna(date_value):
                    item["dates"].add(str(date_value))

                if pd.notna(isin_value) and str(isin_value).strip():
                    item["isins"].add(str(isin_value).strip())

                if pd.notna(series) and str(series).strip():
                    item["series"].add(str(series).strip())

            duplicate_mask = matched.duplicated(
                ["TradDt", "TckrSymb", "SctySrs"],
                keep=False,
            )

            duplicates = matched[duplicate_mask]

            for symbol, count in duplicates.groupby("TckrSymb").size().items():
                stats[symbol]["duplicate_rows"] += int(count)

        except Exception as error:
            errors.append(
                f"{archive_path.name}: {type(error).__name__}: {error}"
            )

    print("=" * 110)
    print("NIFTY 50 HISTORICAL BHAVCOPY COVERAGE")
    print("=" * 110)

    rows = []

    for symbol in sorted(symbols):
        item = stats[symbol]

        dates = sorted(item["dates"])

        rows.append({
            "symbol": symbol,
            "rows": item["rows"],
            "first_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None,
            "unique_dates": len(item["dates"]),
            "ISIN_count": len(item["isins"]),
            "ISINs": ", ".join(sorted(item["isins"])),
            "series": ", ".join(sorted(item["series"])),
            "duplicate_rows": item["duplicate_rows"],
        })

    report = pd.DataFrame(rows)

    output_dir = (
        ROOT / "database" / "processed" / "audit"
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = (
        output_dir / "nifty50_bhavcopy_coverage_audit.csv"
    )

    report.to_csv(output_file, index=False)

    print(report.to_string(index=False))

    print("\n" + "=" * 110)
    print("AUDIT SUMMARY")
    print("=" * 110)

    print(f"Archives discovered: {len(archives)}")
    print(f"Archives successfully inspected: {total_files}")
    print(f"Historical symbols checked: {len(symbols)}")
    print(f"Matching Bhavcopy rows: {total_matching_rows}")
    print(
        "Symbols with no matching rows:",
        int((report["rows"] == 0).sum())
    )
    print(
        "Symbols with multiple ISINs:",
        int((report["ISIN_count"] > 1).sum())
    )
    print(
        "Symbols with duplicate rows:",
        int((report["duplicate_rows"] > 0).sum())
    )
    print(f"Archive errors: {len(errors)}")

    if errors:
        print("\nERRORS:")
        for error in errors:
            print(error)

    print(f"\nReport saved to: {output_file}")


if __name__ == "__main__":
    main()
