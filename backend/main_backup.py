
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from database import engine

# --------------------------------------------------
# GREEDY STOCKS API INITIALIZATION
# --------------------------------------------------

app = FastAPI(
    title="GREEDY STOCKS API",
    description="AI-powered NIFTY 50 learning assistant",
    version="1.0.0",
)

# --------------------------------------------------
# CORS CONFIGURATION
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# ROOT ENDPOINT
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "Welcome to GREEDY STOCKS API",
        "status": "running",
        "application": "GREEDY STOCKS",
        "version": "1.0.0",
    }


# --------------------------------------------------
# APPLICATION HEALTH CHECK
# --------------------------------------------------

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "application": "GREEDY STOCKS",
        "version": "1.0.0",
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
        return {
            "status": "unhealthy",
            "database": "disconnected",
        }
