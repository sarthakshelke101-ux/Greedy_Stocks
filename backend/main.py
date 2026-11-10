import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import logging
import sys
from pathlib import Path

from chat_routes import router as chat_router
from sector_routes import router as sector_router
from company_routes import router as company_router
from portfolio_routes import router as portfolio_router
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

# --------------------------------------------------
# PROJECT PATH
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# --------------------------------------------------
# IMPORTS
# --------------------------------------------------

from database import engine
from analytics.market_ideas import generate_market_ideas


# --------------------------------------------------
# LOGGING
# --------------------------------------------------

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("greedy_stocks_api")


# --------------------------------------------------
# GREEDY STOCKS API INITIALIZATION
# --------------------------------------------------

app = FastAPI(
    title="GREEDY STOCKS API",
    description=(
        "AI-powered, beginner-friendly NIFTY 50 "
        "learning and market research assistant."
    ),
    version="1.1.0",
)


# --------------------------------------------------
# CORS CONFIGURATION
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(company_router)
app.include_router(portfolio_router)
app.include_router(sector_router)
app.include_router(chat_router)

# --------------------------------------------------
# ROOT ENDPOINT
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "Welcome to GREEDY STOCKS API",
        "status": "running",
        "application": "GREEDY STOCKS",
        "version": "1.1.0",
    }


# --------------------------------------------------
# APPLICATION HEALTH CHECK
# --------------------------------------------------

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "application": "GREEDY STOCKS",
        "version": "1.1.0",
    }


# --------------------------------------------------
# DATABASE HEALTH CHECK
# --------------------------------------------------

@app.get("/health/db")
def database_health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected",
            "name": "greedy_stocks",
        }

    except Exception:
        logger.exception("Database health check failed.")

        return {
            "status": "unhealthy",
            "database": "disconnected",
        }


# --------------------------------------------------
# MARKET IDEAS ENDPOINT
# --------------------------------------------------

@app.get("/market-ideas")
def market_ideas(
    period: str = Query(
        default="3M",
        pattern="^(1M|3M|6M|1Y)$",
        description="Historical analysis period.",
    ),
    top_n: int = Query(
        default=5,
        ge=1,
        le=10,
        description="Number of top insights per ranking category.",
    ),
):
    """
    Generate evidence-based NIFTY 50 Market Ideas.

    Supported periods:
        1M, 3M, 6M, 1Y

    This endpoint:
        - Reads existing historical data.
        - Generates historical insights.
        - Returns structured JSON.
        - Does not write to the database.
        - Does not save report files.
    """

    try:
        logger.info(
            "Generating Market Ideas: period=%s, top_n=%s",
            period,
            top_n,
        )

        report = generate_market_ideas(
            period=period,
            top_n=top_n,
        )

        return report

    except ValueError as error:
        logger.warning(
            "Invalid Market Ideas request: %s",
            error,
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception:
        logger.exception(
            "Market Ideas generation failed."
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Market Ideas could not be generated. "
                "Check the backend terminal logs."
            ),
        )
