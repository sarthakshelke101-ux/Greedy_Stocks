
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from database import engine


router = APIRouter(tags=["NIFTY 50 Sectors"])

PERIOD_DAYS = {
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "1Y": 365,
}


def serialize(value):
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def get_sector_data(period: str):
    if period not in PERIOD_DAYS:
        raise HTTPException(
            status_code=400,
            detail="Period must be 1M, 3M, 6M, or 1Y.",
        )

    try:
        with engine.connect() as connection:
            snapshot_month = connection.execute(
                text("""
                    SELECT MAX(report_month)
                    FROM index_constituent_snapshots
                    WHERE index_symbol = 'NIFTY 50'
                """)
            ).scalar()

            if snapshot_month is None:
                raise HTTPException(
                    status_code=503,
                    detail="NIFTY 50 constituent snapshot is unavailable.",
                )

            companies = connection.execute(
                text("""
                    SELECT
                        c.id AS company_id,
                        c.symbol,
                        c.company_name,
                        s.id AS sector_id,
                        s.name AS sector_name,
                        s.description AS sector_description,
                        snap.weightage
                    FROM index_constituent_snapshots snap
                    INNER JOIN companies c
                        ON c.symbol = snap.symbol
                    LEFT JOIN sectors s
                        ON s.id = c.sector_id
                    WHERE snap.index_symbol = 'NIFTY 50'
                      AND snap.report_month = :snapshot_month
                    ORDER BY s.name, c.company_name
                """),
                {"snapshot_month": snapshot_month},
            ).mappings().all()

            latest_date = connection.execute(
                text("SELECT MAX(trade_date) FROM stock_prices")
            ).scalar()

            if latest_date is None:
                raise HTTPException(
                    status_code=503,
                    detail="Historical stock price data is unavailable.",
                )

            target_date = latest_date - timedelta(
                days=PERIOD_DAYS[period]
            )

            price_rows = connection.execute(
                text("""
                    SELECT
                        c.id AS company_id,

                        (
                            SELECT p.close_price
                            FROM stock_prices p
                            WHERE p.company_id = c.id
                              AND p.trade_date <= :target_date
                              AND p.close_price > 0
                            ORDER BY p.trade_date DESC
                            LIMIT 1
                        ) AS start_price,

                        (
                            SELECT p.trade_date
                            FROM stock_prices p
                            WHERE p.company_id = c.id
                              AND p.trade_date <= :target_date
                              AND p.close_price > 0
                            ORDER BY p.trade_date DESC
                            LIMIT 1
                        ) AS start_date,

                        (
                            SELECT p.close_price
                            FROM stock_prices p
                            WHERE p.company_id = c.id
                              AND p.trade_date <= :latest_date
                              AND p.close_price > 0
                            ORDER BY p.trade_date DESC
                            LIMIT 1
                        ) AS end_price,

                        (
                            SELECT p.trade_date
                            FROM stock_prices p
                            WHERE p.company_id = c.id
                              AND p.trade_date <= :latest_date
                              AND p.close_price > 0
                            ORDER BY p.trade_date DESC
                            LIMIT 1
                        ) AS end_date

                    FROM companies c
                    WHERE c.id IN :company_ids
                """).bindparams(),
                {
                    "target_date": target_date,
                    "latest_date": latest_date,
                    "company_ids": tuple(
                        row["company_id"] for row in companies
                    ) or (-1,),
                },
            ).mappings().all()

        prices_by_company = {
            row["company_id"]: row
            for row in price_rows
        }

        sector_groups = {}

        for company in companies:
            sector_id = company["sector_id"]
            sector_name = company["sector_name"] or "Unclassified"

            if sector_id not in sector_groups:
                sector_groups[sector_id] = {
                    "sector_id": sector_id,
                    "sector_name": sector_name,
                    "sector_description": company["sector_description"],
                    "companies": [],
                    "returns": [],
                }

            price = prices_by_company.get(company["company_id"])

            company_return = None

            if (
                price
                and price["start_price"]
                and price["end_price"]
                and float(price["start_price"]) > 0
            ):
                company_return = (
                    float(price["end_price"])
                    / float(price["start_price"])
                    - 1
                ) * 100

                sector_groups[sector_id]["returns"].append(
                    company_return
                )

            sector_groups[sector_id]["companies"].append({
                "symbol": company["symbol"],
                "company_name": company["company_name"],
                "weightage": serialize(company["weightage"]),
                "start_date": serialize(
                    price["start_date"] if price else None
                ),
                "end_date": serialize(
                    price["end_date"] if price else None
                ),
                "period_return_pct": (
                    round(company_return, 4)
                    if company_return is not None
                    else None
                ),
            })

        sectors = []

        for group in sector_groups.values():
            returns = group.pop("returns")
            sector_companies = group["companies"]

            available = len(returns)
            total = len(sector_companies)

            average_return = (
                sum(returns) / available
                if available
                else None
            )

            sector_companies.sort(
                key=lambda item: (
                    item["period_return_pct"] is None,
                    -(item["period_return_pct"] or 0),
                )
            )

            sectors.append({
                **group,
                "company_count": total,
                "companies_with_price_data": available,
                "average_constituent_return_pct": (
                    round(average_return, 4)
                    if average_return is not None
                    else None
                ),
                "data_coverage_pct": round(
                    available / total * 100, 2
                ) if total else 0,
            })

        sectors.sort(
            key=lambda item: (
                item["average_constituent_return_pct"] is None,
                -(item["average_constituent_return_pct"] or 0),
            )
        )

        return {
            "index": "NIFTY 50",
            "period": period,
            "snapshot_month": serialize(snapshot_month),
            "data_as_of": serialize(latest_date),
            "comparison_target_date": serialize(target_date),
            "sector_count": len(sectors),
            "company_count": len(companies),
            "sectors": sectors,
            "methodology": {
                "membership_basis": "LATEST_MONTHLY_NIFTY_50_SNAPSHOT",
                "return_method": "EQUAL_WEIGHT_AVERAGE_OF_CONSTITUENT_PRICE_RETURNS",
                "price_basis": "RAW_CLOSE_UNADJUSTED",
                "return_type": "PRICE_RETURN",
                "dividend_adjusted": False,
                "official_sector_index": False,
                "database_writes": False,
            },
            "limitations": [
                "Membership reflects the latest monthly NIFTY 50 snapshot, not historical membership for each date.",
                "Sector performance is the equal-weight average of available constituent price returns, not an official sector index.",
                "Raw unadjusted closing prices are used; corporate actions are not adjusted in this endpoint.",
                "Dividend-adjusted total returns are not available.",
                "Companies without valid prices on both comparison dates are excluded from the sector average.",
                "The comparison start uses each company's latest available close on or before the target date.",
            ],
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="Unable to generate NIFTY 50 sector data.",
        ) from error


@router.get("/sectors")
def list_sectors(
    period: str = Query(
        default="3M",
        pattern="^(1M|3M|6M|1Y)$",
    ),
):
    """Return sector summaries and their NIFTY 50 constituents."""
    return get_sector_data(period)


@router.get("/sectors/{sector_id}")
def get_sector(
    sector_id: int,
    period: str = Query(
        default="3M",
        pattern="^(1M|3M|6M|1Y)$",
    ),
):
    """Return one sector and its NIFTY 50 constituent details."""
    report = get_sector_data(period)

    for sector in report["sectors"]:
        if sector["sector_id"] == sector_id:
            return {
                **report,
                "sectors": [sector],
            }

    raise HTTPException(
        status_code=404,
        detail="Sector not found in the latest NIFTY 50 snapshot.",
    )
