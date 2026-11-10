import sys
sys.path.insert(0, "backend")

from pathlib import Path
from zipfile import ZipFile
from io import BytesIO
from decimal import Decimal
import pandas as pd

from sqlalchemy import text
from database import engine

ROOT = Path("database/raw/bhavcopy")
COMPANY_ID = 16
EXPECTED_ISIN = "INE758T01015"

DATES = [
    "20250401", "20250402", "20250403",
    "20250404", "20250407", "20250408"
]

INSERT_PRICE = text("""
    INSERT INTO stock_prices (
        company_id, trade_date,
        open_price, high_price, low_price, close_price,
        previous_close, total_traded_volume,
        total_traded_value, total_trades, price_source
    ) VALUES (
        :company_id, :trade_date,
        :open_price, :high_price, :low_price, :close_price,
        :previous_close, :volume, :value, :trades,
        'NSE CM-UDiFF EQ - historical ticker ZOMATO'
    )
""")

def main():
    with engine.connect() as conn:
        company = conn.execute(text("""
            SELECT id, symbol FROM companies WHERE id = :id
        """), {"id": COMPANY_ID}).mappings().first()

    if not company or company["symbol"] != "ETERNAL":
        raise ValueError("Company ID 16 is not ETERNAL. Aborting.")

    collected = []

    for date_code in DATES:
        matches = list(ROOT.glob(f"*{date_code}*.zip"))

        if len(matches) != 1:
            raise ValueError(
                f"Expected one archive for {date_code}; found {len(matches)}"
            )

        with ZipFile(matches[0]) as zf:
            found = False

            for member in zf.namelist():
                if not member.lower().endswith(".csv"):
                    continue

                with zf.open(member) as f:
                    df = pd.read_csv(BytesIO(f.read()), dtype=str)

                required = {
                    "TradDt", "TckrSymb", "SctySrs", "ISIN",
                    "OpnPric", "HghPric", "LwPric", "ClsPric",
                    "PrvsClsgPric", "TtlTradgVol",
                    "TtlTrfVal", "TtlNbOfTxsExctd"
                }

                if not required.issubset(df.columns):
                    continue

                rows = df[
                    (df["TckrSymb"].str.strip() == "ZOMATO") &
                    (df["SctySrs"].str.strip() == "EQ")
                ]

                if rows.empty:
                    continue

                if len(rows) != 1:
                    raise ValueError(f"Multiple ZOMATO EQ rows on {date_code}")

                r = rows.iloc[0]

                if r["ISIN"].strip() != EXPECTED_ISIN:
                    raise ValueError(f"Unexpected ISIN on {date_code}")

                prices = {
                    "open_price": Decimal(r["OpnPric"]),
                    "high_price": Decimal(r["HghPric"]),
                    "low_price": Decimal(r["LwPric"]),
                    "close_price": Decimal(r["ClsPric"]),
                    "previous_close": Decimal(r["PrvsClsgPric"])
                }

                if any(v <= 0 for v in prices.values()):
                    raise ValueError(f"Invalid price on {date_code}")

                if (
                    prices["high_price"] < max(
                        prices["open_price"], prices["close_price"]
                    )
                    or prices["low_price"] > min(
                        prices["open_price"], prices["close_price"]
                    )
                ):
                    raise ValueError(f"Invalid OHLC on {date_code}")

                collected.append({
                    "company_id": COMPANY_ID,
                    "trade_date": pd.to_datetime(
                        r["TradDt"]
                    ).date(),
                    **prices,
                    "volume": int(r["TtlTradgVol"]),
                    "value": Decimal(r["TtlTrfVal"]),
                    "trades": int(r["TtlNbOfTxsExctd"])
                })

                found = True
                break

            if not found:
                raise ValueError(f"ZOMATO EQ row missing in {date_code}")

    if len(collected) != 6:
        raise ValueError(f"Expected six observations, got {len(collected)}")

    with engine.begin() as conn:
        inserted = 0

        for row in collected:
            existing = conn.execute(text("""
                SELECT id FROM stock_prices
                WHERE company_id = :company_id
                  AND trade_date = :trade_date
            """), row).first()

            if existing:
                raise ValueError(
                    f"Price already exists for {row['trade_date']}; "
                    "manual conflict review required."
                )

            conn.execute(INSERT_PRICE, row)
            inserted += 1

        # Preserve the historical source ticker as an observed alias.
        existing_alias = conn.execute(text("""
            SELECT id, valid_to
            FROM company_identifiers
            WHERE company_id = :company_id
              AND identifier_type = 'TICKER'
              AND identifier_value = 'ZOMATO'
              AND valid_from = '2025-04-01'
        """), {"company_id": COMPANY_ID}).mappings().first()

        if existing_alias:
            if str(existing_alias["valid_to"]) != "2025-04-08":
                raise ValueError("Existing ZOMATO ticker mapping conflicts.")
        else:
            conn.execute(text("""
                INSERT INTO company_identifiers (
                    company_id, identifier_type, identifier_value,
                    valid_from, valid_to, source_name, source_reference
                ) VALUES (
                    :company_id, 'TICKER', 'ZOMATO',
                    '2025-04-01', '2025-04-08',
                    'NSE CM-UDiFF Common Bhavcopy Final',
                    'Observed ZOMATO EQ ticker rows in six NSE daily archives; '
                    'dates are source observation boundaries, not legal '
                    'effective-date certification.'
                )
            """), {"company_id": COMPANY_ID})

    print("\nHISTORICAL TICKER CORRECTION COMPLETE")
    print("Company:", company["symbol"], "ID:", COMPANY_ID)
    print("Verified source ISIN:", EXPECTED_ISIN)
    print("Source observations:", len(collected))
    print("New price records:", inserted)
    print("Historical ticker alias: ZOMATO")
    print("Observed ticker dates: 2025-04-01 to 2025-04-08")

if __name__ == "__main__":
    main()
