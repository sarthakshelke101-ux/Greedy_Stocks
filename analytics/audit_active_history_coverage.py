"""Read-only active-history trading-date coverage audit."""

import pandas as pd
from sqlalchemy import text, bindparam

from analytics.database_adapter import get_latest_constituents
from backend.database import engine


def main():
    constituents = get_latest_constituents()
    company_ids = constituents["company_id"].astype(int).tolist()

    query = text("""
        SELECT company_id, trade_date, close_price
        FROM stock_prices
        WHERE company_id IN :company_ids
        ORDER BY company_id, trade_date
    """).bindparams(bindparam("company_ids", expanding=True))

    with engine.connect() as conn:
        rows = conn.execute(
            query,
            {"company_ids": company_ids},
        ).mappings().all()

        reference_rows = conn.execute(text("""
            SELECT DISTINCT trade_date
            FROM stock_prices
            ORDER BY trade_date
        """)).fetchall()

    prices = pd.DataFrame([dict(row) for row in rows])
    prices["trade_date"] = pd.to_datetime(prices["trade_date"]).dt.normalize()

    reference_dates = pd.DatetimeIndex(
        pd.to_datetime([row[0] for row in reference_rows])
    ).normalize()

    results = []

    for company in constituents.to_dict("records"):
        company_prices = prices[
            prices["company_id"] == company["company_id"]
        ].copy()

        if company_prices.empty:
            results.append({
                "symbol": company["symbol"],
                "first_date": None,
                "last_date": None,
                "observed_dates": 0,
                "expected_dates": 0,
                "missing_dates": None,
                "invalid_closes": 0,
                "coverage_pct": 0.0,
            })
            continue

        first_date = company_prices["trade_date"].min()
        last_date = company_prices["trade_date"].max()

        expected = reference_dates[
            (reference_dates >= first_date)
            & (reference_dates <= last_date)
        ]

        observed = set(company_prices["trade_date"].tolist())
        missing = [date for date in expected if date not in observed]

        invalid = (
            company_prices["close_price"].isna()
            | (pd.to_numeric(
                company_prices["close_price"], errors="coerce"
            ) <= 0)
        ).sum()

        results.append({
            "symbol": company["symbol"],
            "first_date": first_date.date(),
            "last_date": last_date.date(),
            "observed_dates": len(observed),
            "expected_dates": len(expected),
            "missing_dates": len(missing),
            "invalid_closes": int(invalid),
            "coverage_pct": round(
                len(observed) / len(expected) * 100, 2
            ) if len(expected) else 0.0,
            "missing_examples": ", ".join(
                date.strftime("%Y-%m-%d") for date in missing[:5]
            ),
        })

    result = pd.DataFrame(results)

    print("=" * 75)
    print("ACTIVE-HISTORY COVERAGE AUDIT — READ ONLY")
    print("=" * 75)
    print("Companies:", len(result))
    print(
        "Companies with complete active-window coverage:",
        int((result["missing_dates"] == 0).sum()),
    )
    print(
        "Total missing reference dates:",
        int(result["missing_dates"].fillna(0).sum()),
    )
    print(
        "Companies with invalid closes:",
        int((result["invalid_closes"] > 0).sum()),
    )

    print("\nCOMPANY RESULTS")
    print(result[
        [
            "symbol", "first_date", "last_date",
            "observed_dates", "expected_dates",
            "missing_dates", "coverage_pct", "invalid_closes",
        ]
    ].to_string(index=False))

    exceptions = result[
        (result["missing_dates"].fillna(0) > 0)
        | (result["invalid_closes"] > 0)
    ]

    if not exceptions.empty:
        print("\nEXCEPTIONS")
        print(exceptions[
            ["symbol", "missing_examples", "invalid_closes"]
        ].to_string(index=False))
    else:
        print("\nNo company-level gaps found within observed history.")

    print("\nLIMITATION:")
    print(
        "Reference dates are sourced from stock_prices, not an independently "
        "verified official NSE trading calendar."
    )
    print("No database writes performed.")


if __name__ == "__main__":
    main()
