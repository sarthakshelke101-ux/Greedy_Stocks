from analytics._bootstrap import PROJECT_ROOT

import pandas as pd
from sqlalchemy import text

from database import engine
from analytics.financial_metrics import calculate_metrics


INDEX_SYMBOL = "NIFTY 50"


def get_latest_constituents() -> pd.DataFrame:
    """Return companies from the latest available NIFTY 50 snapshot.

    These are monthly snapshot observations, not verified daily
    effective-membership intervals.
    """
    query = text("""
        SELECT
            s.report_month,
            s.symbol,
            s.security_name,
            s.industry,
            s.weightage,
            c.id AS company_id,
            c.company_name,
            sec.name AS sector
        FROM index_constituent_snapshots s
        JOIN companies c
            ON c.symbol = s.symbol
        LEFT JOIN sectors sec
            ON sec.id = c.sector_id
        WHERE s.index_symbol = :index_symbol
          AND s.report_month = (
              SELECT MAX(report_month)
              FROM index_constituent_snapshots
              WHERE index_symbol = :index_symbol
          )
        ORDER BY s.weightage DESC, s.symbol
    """)

    with engine.connect() as conn:
        rows = conn.execute(
            query,
            {"index_symbol": INDEX_SYMBOL}
        ).mappings().all()

    result = pd.DataFrame([dict(row) for row in rows])

    if result.empty:
        raise ValueError(
            f"No constituent snapshot found for {INDEX_SYMBOL}."
        )

    result["report_month"] = pd.to_datetime(result["report_month"])

    return result


def get_company_prices(
    company_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.Series:
    """Retrieve raw closing prices for one company.

    Missing or invalid prices remain missing; they are not forward-filled.
    """
    query = text("""
        SELECT trade_date, close_price
        FROM stock_prices
        WHERE company_id = :company_id
          AND (:start_date IS NULL OR trade_date >= :start_date)
          AND (:end_date IS NULL OR trade_date <= :end_date)
        ORDER BY trade_date
    """)

    with engine.connect() as conn:
        rows = conn.execute(
            query,
            {
                "company_id": company_id,
                "start_date": start_date,
                "end_date": end_date,
            }
        ).mappings().all()

    if not rows:
        return pd.Series(dtype=float, name="close_price")

    frame = pd.DataFrame([dict(row) for row in rows])
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame["close_price"] = pd.to_numeric(
        frame["close_price"], errors="coerce"
    )

    return pd.Series(
        frame["close_price"].values,
        index=pd.DatetimeIndex(frame["trade_date"]),
        name="close_price",
        dtype=float,
    )


def calculate_latest_snapshot_metrics(
    start_date: str | None = None,
    end_date: str | None = None,
    risk_free_rate: float = 0.0,
) -> pd.DataFrame:
    """Calculate raw-price metrics for the latest snapshot's companies.

    IMPORTANT:
    This is not a point-in-time historical NIFTY 50 ranking.
    """
    constituents = get_latest_constituents()
    results = []

    for company in constituents.to_dict("records"):
        prices = get_company_prices(
            company_id=int(company["company_id"]),
            start_date=start_date,
            end_date=end_date,
        )

        metrics = calculate_metrics(
            prices,
            risk_free_rate=risk_free_rate,
        )

        results.append({
            "symbol": company["symbol"],
            "company_name": company["company_name"],
            "sector": company["sector"],
            "snapshot_month": company["report_month"].date().isoformat(),
            **metrics,
        })

    result = pd.DataFrame(results)

    if not result.empty:
        result = result.sort_values(
            "period_return_pct",
            ascending=False,
            na_position="last",
        ).reset_index(drop=True)

    return result


if __name__ == "__main__":
    print("GREEDY STOCKS — READ-ONLY ANALYTICS DATABASE TEST")

    constituents = get_latest_constituents()

    print("\nLatest snapshot:")
    print(constituents["report_month"].iloc[0].date())

    print("Companies found:", len(constituents))
    print("\nSnapshot preview:")
    print(
        constituents[
            ["symbol", "company_name", "sector", "weightage"]
        ].head(10).to_string(index=False)
    )

    metrics = calculate_latest_snapshot_metrics()

    print("\nCalculated company metrics:", len(metrics))
    print(
        metrics[
            ["symbol", "period_return_pct", "cagr_pct",
             "annualized_volatility_pct", "maximum_drawdown_pct",
             "sharpe_ratio"]
        ].head(10).to_string(index=False)
    )

    print("\nPrice basis: RAW_CLOSE_UNADJUSTED")
    print("Universe: LATEST MONTHLY NIFTY 50 SNAPSHOT")
    print("Database writes: NONE")


def get_all_companies_with_prices(min_observations: int = 252) -> pd.DataFrame:
    """Return active and inactive companies with sufficient actual price history."""
    if min_observations < 1:
        raise ValueError("min_observations must be positive.")

    query = text("""
        SELECT
            c.id AS company_id,
            c.symbol,
            c.company_name,
            COALESCE(sec.name, 'Unclassified') AS sector,
            c.is_active,
            MIN(sp.trade_date) AS first_price_date,
            MAX(sp.trade_date) AS last_price_date,
            COUNT(DISTINCT sp.trade_date) AS observations
        FROM companies c
        JOIN stock_prices sp ON sp.company_id = c.id
        LEFT JOIN sectors sec ON sec.id = c.sector_id
        GROUP BY c.id, c.symbol, c.company_name, sec.name, c.is_active
        HAVING COUNT(DISTINCT sp.trade_date) >= :minimum
        ORDER BY c.symbol
    """)

    with engine.connect() as conn:
        rows = conn.execute(
            query, {"minimum": min_observations}
        ).mappings().all()

    result = pd.DataFrame([dict(r) for r in rows])
    if result.empty:
        raise ValueError("No companies meet the historical data threshold.")

    if result["symbol"].duplicated().any():
        raise ValueError("Duplicate canonical company symbols detected.")

    return result
