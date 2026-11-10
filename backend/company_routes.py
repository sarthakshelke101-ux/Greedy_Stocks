
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from database import engine

router = APIRouter(tags=["Companies"])


def serialize_value(value):
    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    return value


@router.get("/companies/{symbol}")
def get_company_profile(symbol: str):
    symbol = symbol.strip().upper()

    if not symbol or len(symbol) > 30:
        raise HTTPException(
            status_code=400,
            detail="Invalid company symbol.",
        )

    try:
        with engine.connect() as connection:
            company = connection.execute(
                text("""
                    SELECT
                        c.id,
                        c.symbol,
                        c.company_name,
                        c.isin,
                        c.exchange,
                        c.is_active,
                        s.name AS sector,
                        s.description AS sector_description
                    FROM companies c
                    LEFT JOIN sectors s ON s.id = c.sector_id
                    WHERE c.symbol = :symbol
                    LIMIT 1
                """),
                {"symbol": symbol},
            ).mappings().first()

            if not company:
                raise HTTPException(
                    status_code=404,
                    detail=f"Company {symbol} was not found.",
                )

            company_id = company["id"]

            coverage = connection.execute(
                text("""
                    SELECT
                        MIN(trade_date) AS first_trade_date,
                        MAX(trade_date) AS latest_trade_date,
                        COUNT(*) AS observations
                    FROM stock_prices
                    WHERE company_id = :company_id
                """),
                {"company_id": company_id},
            ).mappings().first()

            latest_price = connection.execute(
                text("""
                    SELECT
                        trade_date,
                        open_price,
                        high_price,
                        low_price,
                        close_price,
                        previous_close,
                        total_traded_volume,
                        total_traded_value,
                        total_trades,
                        price_source
                    FROM stock_prices
                    WHERE company_id = :company_id
                    ORDER BY trade_date DESC
                    LIMIT 1
                """),
                {"company_id": company_id},
            ).mappings().first()

            actions = connection.execute(
                text("""
                    SELECT
                        action_type,
                        announcement_date,
                        ex_date,
                        record_date,
                        effective_date,
                        description,
                        ratio,
                        dividend_amount,
                        source_name,
                        source_reference
                    FROM corporate_actions
                    WHERE company_id = :company_id
                    ORDER BY COALESCE(
                        ex_date,
                        effective_date,
                        announcement_date
                    ) DESC
                    LIMIT 50
                """),
                {"company_id": company_id},
            ).mappings().all()

            identifiers = connection.execute(
                text("""
                    SELECT
                        identifier_type,
                        identifier_value,
                        valid_from,
                        valid_to,
                        source_name,
                        source_reference
                    FROM company_identifiers
                    WHERE company_id = :company_id
                    ORDER BY valid_from
                """),
                {"company_id": company_id},
            ).mappings().all()

        return {
            "company": {
                "symbol": company["symbol"],
                "company_name": company["company_name"],
                "isin": company["isin"],
                "exchange": company["exchange"],
                "is_active": bool(company["is_active"]),
                "sector": company["sector"],
                "sector_description": company["sector_description"],
            },
            "price_coverage": {
                "first_price_date": serialize_value(
                    coverage["first_trade_date"]
                ),
                "last_price_date": serialize_value(
                    coverage["latest_trade_date"]
                ),
                "observations": int(coverage["observations"] or 0),
                "price_basis": "RAW_CLOSE_UNADJUSTED",
            },
            "latest_price": (
                {
                    key: serialize_value(value)
                    for key, value in latest_price.items()
                }
                if latest_price else None
            ),
            "corporate_actions": [
                {
                    key: serialize_value(value)
                    for key, value in action.items()
                }
                for action in actions
            ],
            "identifiers": [
                {
                    key: serialize_value(value)
                    for key, value in identifier.items()
                }
                for identifier in identifiers
            ],
            "data_limitations": [
                "Latest price is an unadjusted raw closing price.",
                "Corporate action coverage is limited to imported records.",
                "Dividend-adjusted total-return history is not provided.",
                "Company fundamentals and valuation data are not integrated.",
                "Historical price coverage does not establish historical NIFTY 50 membership.",
            ],
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve the company profile.",
        ) from error
