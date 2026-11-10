"""Historical NIFTY 50 stock rankings.

Universe:
    Latest available NIFTY 50 monthly constituent snapshot.

Price basis:
    Split/bonus-adjusted close using currently imported corporate actions.
    This is NOT a dividend-adjusted total-return series.

Important:
    Monthly constituent snapshots are not exact daily membership records.
    Corporate-action coverage is currently partial.
    The session reference is derived from dates present in stock_prices;
    it is not an independently certified NSE trading calendar.
"""

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "backend"))

from database import engine
from analytics.adjusted_prices import build_adjusted_prices
from analytics.financial_metrics import (
    period_return,
    annualized_volatility,
    cagr,
    maximum_drawdown,
    sharpe_ratio,
)


PERIODS = {
    "1M": pd.DateOffset(months=1),
    "3M": pd.DateOffset(months=3),
    "6M": pd.DateOffset(months=6),
    "1Y": pd.DateOffset(years=1),
}

RISK_FREE_RATE = 0.0


def get_latest_snapshot(conn):
    return conn.execute(text("""
        SELECT MAX(report_month)
        FROM index_constituent_snapshots
        WHERE index_symbol = 'NIFTY 50'
    """)).scalar_one()


def get_snapshot_companies(conn, snapshot_month):
    rows = conn.execute(text("""
        SELECT
            c.id AS company_id,
            c.symbol,
            c.company_name,
            s.name AS sector,
            snap.weightage AS snapshot_weightage,
            snap.industry AS snapshot_industry
        FROM index_constituent_snapshots snap
        JOIN companies c
            ON c.symbol = snap.symbol
        LEFT JOIN sectors s
            ON s.id = c.sector_id
        WHERE snap.index_symbol = 'NIFTY 50'
          AND snap.report_month = :snapshot_month
        ORDER BY c.symbol
    """), {"snapshot_month": snapshot_month}).mappings().all()

    return [dict(row) for row in rows]


def get_company_prices(conn, company_id, start_date, end_date):
    """Load all history through end_date so earlier actions can adjust the window.

    start_date is retained in the signature for compatibility. It is not
    applied to the SQL query because actions before the ranking window must
    be considered when constructing the adjusted price series.
    """
    return pd.read_sql(text("""
        SELECT
            trade_date,
            close_price AS close
        FROM stock_prices
        WHERE company_id = :company_id
          AND trade_date <= :end_date
        ORDER BY trade_date
    """), conn, params={
        "company_id": company_id,
        "end_date": end_date,
    })


def get_company_actions(conn, company_id, end_date):
    """Load only actions effective by the common ranking end date."""
    rows = conn.execute(text("""
        SELECT
            action_type,
            ex_date,
            ratio,
            source_name,
            source_reference
        FROM corporate_actions
        WHERE company_id = :company_id
          AND ex_date IS NOT NULL
          AND ex_date <= :end_date
        ORDER BY ex_date
    """), {
        "company_id": company_id,
        "end_date": pd.Timestamp(end_date).date(),
    }).mappings().all()

    return [dict(row) for row in rows]


def get_trading_sessions(conn, start_date, end_date):
    """Return observed market dates from imported stock_prices.

    This detects missing observations relative to the imported dataset's
    shared date set. It cannot detect a market session missing from every
    imported stock record, so it is not a substitute for an official NSE
    trading calendar.
    """
    rows = conn.execute(text("""
        SELECT DISTINCT trade_date
        FROM stock_prices
        WHERE trade_date >= :start_date
          AND trade_date <= :end_date
        ORDER BY trade_date
    """), {
        "start_date": pd.Timestamp(start_date).date(),
        "end_date": pd.Timestamp(end_date).date(),
    }).scalars().all()

    return pd.DatetimeIndex(pd.to_datetime(list(rows))).normalize()


def calculate_company_metrics(
    prices,
    actions,
    start_date,
    end_date,
    expected_sessions=None,
):
    if prices.empty or expected_sessions is None or len(expected_sessions) < 2:
        return None

    adjusted = build_adjusted_prices(prices, actions)

    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    window = adjusted[
        (adjusted["trade_date"] >= start)
        & (adjusted["trade_date"] <= end)
    ].copy()

    expected = pd.DatetimeIndex(pd.to_datetime(expected_sessions)).normalize()
    expected = expected[(expected >= start) & (expected <= end)]

    if len(expected) < 2:
        return None

    # Do not drop missing observations and bridge across them. Every
    # expected session must have exactly one valid adjusted close.
    observed = window.dropna(subset=["adjusted_close"]).set_index("trade_date")
    observed.index = pd.DatetimeIndex(observed.index).normalize()

    if observed.index.has_duplicates:
        return None

    if not observed.index.equals(expected):
        return None

    price_series = observed["adjusted_close"].astype(float)

    try:
        metrics = {
            "period_return": period_return(
                price_series,
                expected_sessions=expected,
            ),
            "annualized_volatility": annualized_volatility(
                price_series,
                expected_sessions=expected,
            ),
            "cagr": cagr(
                price_series,
                expected_sessions=expected,
            ),
            "maximum_drawdown": maximum_drawdown(
                price_series,
                expected_sessions=expected,
            ),
            "sharpe_ratio": sharpe_ratio(
                price_series,
                risk_free_rate=RISK_FREE_RATE,
                expected_sessions=expected,
            ),
        }
    except (ValueError, TypeError):
        return None

    metrics.update({
        "observations": len(price_series),
        "first_price_date": price_series.index.min().date(),
        "last_price_date": price_series.index.max().date(),
        "corporate_actions_applied": len(actions),
        "expected_sessions": len(expected),
    })
    return metrics


def run_historical_rankings(period="3M"):
    period = period.upper()

    if period not in PERIODS:
        raise ValueError(
            f"Unsupported period {period}. Choose from {list(PERIODS)}."
        )

    with engine.connect() as conn:
        snapshot_month = get_latest_snapshot(conn)

        if snapshot_month is None:
            raise RuntimeError("No NIFTY 50 constituent snapshot found.")

        companies = get_snapshot_companies(conn, snapshot_month)

        if len(companies) != 50:
            raise RuntimeError(
                f"Expected 50 snapshot companies; found {len(companies)}."
            )

        if len({company["symbol"] for company in companies}) != 50:
            raise RuntimeError("Duplicate symbols found in NIFTY 50 snapshot.")

        latest_date = conn.execute(text("""
            SELECT MAX(sp.trade_date)
            FROM stock_prices sp
            JOIN companies c ON c.id = sp.company_id
            JOIN index_constituent_snapshots snap
                ON snap.symbol = c.symbol
            WHERE snap.index_symbol = 'NIFTY 50'
              AND snap.report_month = :snapshot_month
        """), {"snapshot_month": snapshot_month}).scalar_one()

        if latest_date is None:
            raise RuntimeError("No historical prices found.")

        end_date = pd.Timestamp(latest_date).normalize()
        requested_start = (end_date - PERIODS[period]).normalize()
        expected_sessions = get_trading_sessions(
            conn,
            requested_start,
            end_date,
        )

        if len(expected_sessions) < 2:
            raise RuntimeError("Insufficient shared trading-session dates.")

        companies = get_snapshot_companies(conn, snapshot_month)
        results = []

        print(f"Snapshot month: {snapshot_month}")
        print(f"Ranking period: {period}")
        print(f"Requested start: {requested_start.date()}")
        print(f"Common end date: {end_date.date()}")
        print(f"Observed shared sessions: {len(expected_sessions)}")
        print("Universe size:", len(companies))
        print()

        for company in companies:
            prices = get_company_prices(
                conn,
                company["company_id"],
                requested_start,
                end_date,
            )

            actions = get_company_actions(
                conn,
                company["company_id"],
                end_date,
            )

            metrics = calculate_company_metrics(
                prices,
                actions,
                requested_start,
                end_date,
                expected_sessions=expected_sessions,
            )

            if metrics is None:
                results.append({
                    **company,
                    "period_return": None,
                    "annualized_volatility": None,
                    "cagr": None,
                    "maximum_drawdown": None,
                    "sharpe_ratio": None,
                    "observations": 0,
                    "expected_sessions": len(expected_sessions),
                    "first_price_date": None,
                    "last_price_date": None,
                    "corporate_actions_applied": len(actions),
                    "data_status": "INSUFFICIENT_DATA",
                    "data_quality_reason": "MISSING_OR_INVALID_EXPECTED_SESSION",
                    "corporate_action_coverage": "PARTIAL",
                })
                continue

            results.append({
                **company,
                **metrics,
                "data_status": "CALCULATED",
                "data_quality_reason": None,
                "corporate_action_coverage": "PARTIAL",
            })

    result = pd.DataFrame(results)

    result["return_rank"] = (
        result["period_return"]
        .rank(method="min", ascending=False)
        .where(result["period_return"].notna())
    )

    result["volatility_rank"] = (
        result["annualized_volatility"]
        .rank(method="min", ascending=True)
        .where(result["annualized_volatility"].notna())
    )

    result = result.sort_values(
        ["return_rank", "symbol"],
        na_position="last",
    ).reset_index(drop=True)

    result.attrs["index"] = "NIFTY 50"
    result.attrs["snapshot_month"] = str(snapshot_month)
    result.attrs["period"] = period
    result.attrs["requested_start_date"] = requested_start.date().isoformat()
    result.attrs["common_end_date"] = end_date.date().isoformat()
    result.attrs["expected_session_count"] = len(expected_sessions)
    result.attrs["session_reference"] = "DISTINCT_STOCK_PRICE_DATES"
    result.attrs["price_basis"] = "SPLIT_BONUS_ADJUSTED"
    result.attrs["dividend_adjusted"] = False
    result.attrs["membership_basis"] = "LATEST_MONTHLY_SNAPSHOT"
    result.attrs["corporate_action_coverage"] = "PARTIAL"

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--period", choices=list(PERIODS), default="3M")
    args = parser.parse_args()

    ranking = run_historical_rankings(args.period)

    columns = [
        "return_rank",
        "symbol",
        "company_name",
        "sector",
        "period_return",
        "annualized_volatility",
        "cagr",
        "maximum_drawdown",
        "sharpe_ratio",
        "observations",
        "data_status",
        "data_quality_reason",
    ]

    print("\n" + "=" * 110)
    print("GREEDY STOCKS — HISTORICAL NIFTY 50 RANKINGS")
    print("=" * 110)
    print(ranking[columns].to_string(index=False))
    print("\nRanking metadata:")
    print(ranking.attrs)
