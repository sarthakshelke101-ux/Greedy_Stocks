from __future__ import annotations

import json
import logging
import re
from datetime import date

import pandas as pd
from sqlalchemy import text

from backend.database import engine
from analytics import adjusted_price_adapter
from analytics import index_adapter
from analytics import database_adapter
from analytics.financial_metrics import calculate_metrics

log = logging.getLogger("greedy_historical")

PLANNER = (
    "Return JSON only: "
    '{"symbol":"NSE ticker or null","start_date":"YYYY-MM-DD or null",'
    '"end_date":"YYYY-MM-DD or null","include_nifty":true/false,'
    '"analysis_request":"what the user wants"} '
    "Resolve relative dates using today's date supplied below. "
    "Only identify a symbol when clear. Never return SQL or prose."
)


def _json(text_value):
    s = (text_value or "").strip()
    s = re.sub(r"^```(?:json)?|```$", "", s, flags=re.I).strip()
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("Invalid planner JSON")
    obj = json.loads(s[a:b + 1])
    if not isinstance(obj, dict):
        raise ValueError("Planner output is not an object")
    return obj


def _plan(client, model, question):
    today = date.today()
    response = client.models.generate_content(
        model=model,
        contents=f"{PLANNER}\nToday: {today}\nQuestion: {question}",
    )
    p = _json(getattr(response, "text", ""))
    symbol = p.get("symbol")
    if symbol:
        symbol = str(symbol).strip().upper()
        if not re.fullmatch(r"[A-Z0-9&._-]{1,30}", symbol):
            raise ValueError("Invalid ticker format")

    bounds_query = text("""
        SELECT MIN(sp.trade_date) AS first_date,
               MAX(sp.trade_date) AS last_date
        FROM stock_prices sp
        JOIN companies c ON c.id = sp.company_id
        WHERE (:symbol IS NULL OR UPPER(c.symbol) = :symbol)
    """)
    with engine.connect() as conn:
        bounds = conn.execute(
            bounds_query, {"symbol": symbol}
        ).mappings().first()

    if not bounds or not bounds["first_date"] or not bounds["last_date"]:
        raise ValueError("No historical stock price data is available.")

    available_start = date.fromisoformat(str(bounds["first_date"])[:10])
    available_end = date.fromisoformat(str(bounds["last_date"])[:10])

    end = date.fromisoformat(p["end_date"]) if p.get("end_date") else available_end
    start = date.fromisoformat(p["start_date"]) if p.get("start_date") else available_start

    start = max(start, available_start)
    end = min(end, available_end)
    if start > end:
        raise ValueError("Invalid date range")

    return (
        symbol,
        start,
        end,
        bool(p.get("include_nifty")),
        str(p.get("analysis_request") or question)[:1000],
    )


def _stock(symbol, start, end):
    # Restrict analysis to the latest available NIFTY 50 snapshot.
    constituents = database_adapter.get_latest_constituents()
    supported = set(
        constituents["symbol"].astype(str).str.strip().str.upper()
    )
    if symbol not in supported:
        raise ValueError(
            f"{symbol} is not in the latest available NIFTY 50 constituent snapshot."
        )

    query = text("""
        SELECT id, symbol, company_name
        FROM companies
        WHERE UPPER(symbol) = :symbol
        LIMIT 1
    """)
    with engine.connect() as conn:
        company = conn.execute(
            query, {"symbol": symbol}
        ).mappings().first()

    if not company:
        raise ValueError(f"Company master record not found for {symbol}.")

    frame = adjusted_price_adapter.get_adjusted_company_prices(
        company_id=int(company["id"]),
        start_date=start.isoformat(),
        end_date=end.isoformat(),
    )
    if frame.empty or "adjusted_close" not in frame.columns:
        raise ValueError(f"No adjusted price observations found for {symbol}.")

    frame = frame.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame["close_price"] = pd.to_numeric(
        frame["adjusted_close"], errors="coerce"
    )
    frame = frame.dropna(subset=["trade_date", "close_price"])
    frame = frame[frame["close_price"] > 0]
    frame = frame.sort_values("trade_date").drop_duplicates("trade_date")

    if len(frame) < 2:
        raise ValueError(f"Insufficient adjusted price history for {symbol}.")

    frame["symbol"] = str(company["symbol"])
    frame["company_name"] = str(company["company_name"])
    return frame.reset_index(drop=True)


def _nifty(start, end):
    series = index_adapter.get_index_closes(
        start_date=start.isoformat(),
        end_date=end.isoformat(),
    )
    if series is None or series.empty:
        return pd.DataFrame(columns=["trade_date", "close_value"])

    frame = series.rename("close_value").rename_axis("trade_date").reset_index()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame["close_value"] = pd.to_numeric(
        frame["close_value"], errors="coerce"
    )
    return (
        frame.dropna()
        .query("close_value > 0")
        .sort_values("trade_date")
        .drop_duplicates("trade_date")
        .reset_index(drop=True)
    )


def _year_returns(prices):
    result = []
    for year, group in prices.groupby(prices.index.year):
        if len(group) < 2:
            continue
        result.append({
            "year": int(year),
            "first_observation": group.index[0].date().isoformat(),
            "last_observation": group.index[-1].date().isoformat(),
            "start_adjusted_close": round(float(group.iloc[0]), 4),
            "end_adjusted_close": round(float(group.iloc[-1]), 4),
            "return_pct": round(
                float((group.iloc[-1] / group.iloc[0] - 1) * 100), 4
            ),
            "observations": int(len(group)),
        })
    return result


def _analyse(df, nifty, request):
    prices = (
        df.set_index("trade_date")["close_price"]
        .astype(float)
        .sort_index()
    )
    prices = prices[~prices.index.duplicated(keep="last")]

    if len(prices) < 2:
        raise ValueError("Insufficient observations")

    metrics = calculate_metrics(
        prices,
        risk_free_rate=0.0,
        price_basis="SPLIT_BONUS_ADJUSTED",
        return_type="PRICE_RETURN",
    )

    peak = prices.cummax()
    drawdown = prices / peak - 1
    trough = drawdown.idxmin()
    peak_date = prices.loc[:trough].idxmax()
    calendar = _year_returns(prices)

    result = {
        "company": str(df.iloc[0]["company_name"]),
        "symbol": str(df.iloc[0]["symbol"]),
        "request": request,
        "price_basis": (
            "Split/bonus-adjusted close prices; dividends are not included."
        ),
        "coverage": {
            "first_date": metrics["start_date"],
            "last_date": metrics["end_date"],
            "price_observations": metrics["price_observations"],
            "daily_return_observations": metrics["return_observations"],
        },
        "period_return_pct": metrics["period_return_pct"],
        "cagr_pct": metrics["cagr_pct"],
        "annualized_volatility_pct": metrics["annualized_volatility_pct"],
        "sharpe_ratio": metrics["sharpe_ratio"],
        "sharpe_assumptions": {
            "annual_risk_free_rate": 0.0,
            "trading_days_per_year": 252,
            "method": "Annualized daily excess-return Sharpe ratio",
        },
        "maximum_drawdown": {
            "pct": round(float(drawdown.min() * 100), 4),
            "peak_date": peak_date.date().isoformat(),
            "trough_date": trough.date().isoformat(),
        },
        "calendar_year_returns": calendar,
        "best_calendar_year": (
            max(calendar, key=lambda x: x["return_pct"]) if calendar else None
        ),
        "worst_calendar_year": (
            min(calendar, key=lambda x: x["return_pct"]) if calendar else None
        ),
        "metric_methodology": {
            "trading_days_per_year": metrics["trading_days_per_year"],
            "risk_free_rate_annual": metrics["risk_free_rate_annual"],
            "calendar_validation": metrics["calendar_validation"],
            "cagr_status": metrics["cagr_status"],
        },
    }

    if nifty is not None and not nifty.empty:
        benchmark = nifty.set_index("trade_date")["close_value"].astype(float)
        aligned = pd.concat(
            [prices.rename("stock"), benchmark.rename("nifty")],
            axis=1,
            join="inner",
        ).dropna()

        if len(aligned) >= 2:
            result["nifty_comparison"] = {
                "matched_observations": int(len(aligned)),
                "first_matched_date": aligned.index[0].date().isoformat(),
                "last_matched_date": aligned.index[-1].date().isoformat(),
                "stock_return_pct": round(
                    float((aligned.stock.iloc[-1] / aligned.stock.iloc[0] - 1) * 100),
                    4,
                ),
                "nifty_return_pct": round(
                    float((aligned.nifty.iloc[-1] / aligned.nifty.iloc[0] - 1) * 100),
                    4,
                ),
                "benchmark_basis": "NIFTY 50 index close price return",
            }
        else:
            result["nifty_comparison"] = {
                "status": "UNAVAILABLE",
                "reason": "Insufficient matched stock and index observations.",
            }

    return result


def build_historical_intelligence_context(client, model, question):
    """Read-only historical analysis using adjusted prices and shared metrics."""
    try:
        symbol, start, end, compare, request = _plan(
            client, model, question
        )
        if not symbol:
            return (
                "HISTORICAL_STATUS: NEEDS_CLARIFICATION. "
                "Ask which supported NIFTY 50 ticker the user means."
            )

        stock = _stock(symbol, start, end)
        nifty = _nifty(start, end) if compare else None
        data = _analyse(stock, nifty, request)
        data["requested_period"] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        data["quality_notes"] = [
            "Prices are adjusted for supported stock splits and bonus issues.",
            "Dividend adjustments are not available; these are not total returns.",
            "Corporate-action coverage is partial and depends on stored records.",
            "No missing dates were forward-filled.",
            "Metrics use observed price dates; expected exchange sessions were not supplied.",
            "Calendar-year returns use first and last available adjusted observations.",
            "NIFTY 50 membership is checked against the latest available snapshot only.",
            "This does not establish historical NIFTY 50 membership.",
        ]
        return (
            "HISTORICAL_STATUS: VERIFIED_DATABASE_RESULT\n"
            + json.dumps(data, indent=2, default=str)
        )
    except Exception as exc:
        log.exception("Historical analysis failed")
        return (
            f"HISTORICAL_STATUS: UNAVAILABLE\n"
            f"Reason: {type(exc).__name__}: {str(exc)[:400]}\n"
            "Do not invent figures."
        )

