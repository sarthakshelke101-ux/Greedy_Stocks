"""Read-only trading-session coverage audit for latest NIFTY 50 snapshot."""

import pandas as pd
from sqlalchemy import text, bindparam

from analytics.database_adapter import get_latest_constituents
from backend.database import engine


def main():
    print("=" * 75)
    print("GREEDY STOCKS — TRADING-SESSION COVERAGE AUDIT")
    print("=" * 75)

    constituents = get_latest_constituents()

    if len(constituents) != 50:
        raise ValueError(
            f"Expected 50 latest-snapshot companies; found {len(constituents)}"
        )

    company_ids = constituents["company_id"].astype(int).tolist()

    # Reference dates are all distinct dates represented in stock_prices.
    with engine.connect() as conn:
        date_rows = conn.execute(text("""
            SELECT DISTINCT trade_date
            FROM stock_prices
            ORDER BY trade_date
        """)).fetchall()

        price_query = text("""
            SELECT
                company_id,
                COUNT(*) AS price_rows,
                COUNT(DISTINCT trade_date) AS distinct_dates,
                MIN(trade_date) AS first_date,
                MAX(trade_date) AS last_date,
                SUM(
                    CASE
                        WHEN close_price IS NULL OR close_price <= 0
                        THEN 1 ELSE 0
                    END
                ) AS invalid_closes
            FROM stock_prices
            WHERE company_id IN :company_ids
            GROUP BY company_id
        """).bindparams(
            bindparam("company_ids", expanding=True)
        )

        price_rows = conn.execute(
            price_query,
            {"company_ids": company_ids},
        ).mappings().all()

        company_date_query = text("""
            SELECT company_id, trade_date
            FROM stock_prices
            WHERE company_id IN :company_ids
            ORDER BY company_id, trade_date
        """).bindparams(
            bindparam("company_ids", expanding=True)
        )

        company_dates = conn.execute(
            company_date_query,
            {"company_ids": company_ids},
        ).mappings().all()

    if not date_rows:
        raise ValueError("No trading dates found in stock_prices.")

    reference_dates = pd.DatetimeIndex(
        pd.to_datetime([row[0] for row in date_rows])
    ).normalize()

    stats = pd.DataFrame([dict(row) for row in price_rows])
    dates_frame = pd.DataFrame([dict(row) for row in company_dates])

    if not dates_frame.empty:
        dates_frame["trade_date"] = pd.to_datetime(
            dates_frame["trade_date"]
        ).dt.normalize()

    stats = constituents[
        ["company_id", "symbol", "company_name"]
    ].merge(
        stats,
        on="company_id",
        how="left",
    )

    stats["distinct_dates"] = (
        stats["distinct_dates"].fillna(0).astype(int)
    )
    stats["price_rows"] = stats["price_rows"].fillna(0).astype(int)
    stats["invalid_closes"] = (
        stats["invalid_closes"].fillna(0).astype(int)
    )

    expected_dates = reference_dates[
        (reference_dates >= reference_dates.min())
        & (reference_dates <= reference_dates.max())
    ]

    observed_by_company = {}

    for company_id, group in dates_frame.groupby("company_id"):
        observed_by_company[int(company_id)] = set(
            group["trade_date"].tolist()
        )

    missing_counts = []
    missing_examples = []

    for row in stats.to_dict("records"):
        observed = observed_by_company.get(
            int(row["company_id"]), set()
        )
        missing = [
            date for date in expected_dates
            if date not in observed
        ]

        missing_counts.append(len(missing))
        missing_examples.append(
            ", ".join(date.strftime("%Y-%m-%d") for date in missing[:5])
        )

    stats["missing_reference_dates"] = missing_counts
    stats["missing_date_examples"] = missing_examples

    stats["coverage_pct"] = (
        stats["distinct_dates"] / len(expected_dates) * 100
    ).round(2)

    print("\nREFERENCE DATASET")
    print("Latest snapshot:", constituents["report_month"].iloc[0].date())
    print("Companies audited:", len(constituents))
    print("Distinct reference dates:", len(reference_dates))
    print("First reference date:", reference_dates.min().date())
    print("Last reference date:", reference_dates.max().date())

    print("\nCOVERAGE SUMMARY")
    print(
        "Companies with complete reference-date coverage:",
        int((stats["missing_reference_dates"] == 0).sum()),
    )
    print(
        "Companies with missing reference dates:",
        int((stats["missing_reference_dates"] > 0).sum()),
    )
    print(
        "Total company-date gaps:",
        int(stats["missing_reference_dates"].sum()),
    )
    print(
        "Companies with invalid closing prices:",
        int((stats["invalid_closes"] > 0).sum()),
    )
    print(
        "Total invalid closing-price rows:",
        int(stats["invalid_closes"].sum()),
    )

    print("\nCOMPANY-LEVEL RESULTS")
    print(
        stats[
            [
                "symbol",
                "distinct_dates",
                "missing_reference_dates",
                "coverage_pct",
                "invalid_closes",
            ]
        ].sort_values(
            ["missing_reference_dates", "symbol"],
            ascending=[False, True],
        ).to_string(index=False)
    )

    incomplete = stats[stats["missing_reference_dates"] > 0]

    if not incomplete.empty:
        print("\nFIRST FIVE MISSING REFERENCE DATES PER INCOMPLETE COMPANY")
        print(
            incomplete[
                ["symbol", "missing_date_examples"]
            ].to_string(index=False)
        )

    print("\nAUDIT LIMITATIONS")
    print(
        "- Reference dates come from dates already present in stock_prices."
    )
    print(
        "- This detects company-level gaps against those reference dates."
    )
    print(
        "- It does NOT certify completeness against the official NSE calendar."
    )
    print(
        "- No prices are filled, changed, or written to the database."
    )

    print("\nAUDIT COMPLETE — READ ONLY")


if __name__ == "__main__":
    main()
