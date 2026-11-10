"""Phase 3: latest imported prices and whole-share affordability."""
from __future__ import annotations

import re
import json
from math import floor, isfinite

SYMBOL_PATTERN = re.compile(r"(?<![A-Z0-9])([A-Z][A-Z0-9&-]{1,14})(?![A-Z0-9])")

IGNORED_SYMBOLS = {
    "I", "A", "IN", "ON", "OF", "TO", "FOR", "THE", "AND",
    "NSE", "NIFTY", "STOCK", "STOCKS", "SHARE", "SHARES",
    "PRICE", "PRICES", "LATEST", "CURRENT", "BUY", "SELL",
    "WITH", "FROM", "WHAT", "HOW", "MANY", "CAN", "WILL",
    "GREEDY", "PLEASE", "RS", "INR", "LTP", "BUDGET",
}

BUDGET_PATTERNS = (
    re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
    re.compile(
        r"\b(?:budget|capital|investment amount|invest)\b"
        r"\D{0,24}([\d,]+(?:\.\d{1,2})?)",
        re.I,
    ),
    re.compile(
        r"\bwith\s+(?:a\s+)?(?:budget\s+of\s+)?"
        r"([\d,]+(?:\.\d{1,2})?)\s*(?:rupees|inr|rs)?\b",
        re.I,
    ),
)


def extract_symbols(question: str) -> list[str]:
    """Extract explicit uppercase NSE-style symbols; never guess company names."""
    found = []
    for match in SYMBOL_PATTERN.finditer(question or ""):
        symbol = match.group(1).upper()
        if symbol not in IGNORED_SYMBOLS and symbol not in found:
            found.append(symbol)
    return found[:10]


def extract_budget(question: str):
    """Extract an explicitly stated positive rupee budget."""
    for pattern in BUDGET_PATTERNS:
        match = pattern.search(question or "")
        if match:
            try:
                value = float(match.group(1).replace(",", ""))
            except ValueError:
                continue
            if isfinite(value) and value > 0:
                return value
    return None


def allocate_equal_whole_shares(symbols, prices, capital):
    """Allocate equal budgets with whole shares and report unspent cash."""
    if not symbols or len(symbols) > 10 or len(set(symbols)) != len(symbols):
        raise ValueError("Provide between 1 and 10 unique NSE symbols.")

    if not isinstance(capital, (int, float)) or isinstance(capital, bool):
        raise ValueError("Budget must be a valid positive number.")

    if not isfinite(capital) or capital <= 0:
        raise ValueError("Budget must be a valid positive number.")

    clean = {}
    for symbol in symbols:
        price = prices.get(symbol)
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            raise ValueError(f"Valid latest price unavailable for {symbol}.")
        if not isfinite(price) or price <= 0:
            raise ValueError(f"Invalid latest price for {symbol}.")
        clean[symbol] = float(price)

    per_stock_budget = float(capital) / len(symbols)
    holdings = []
    invested = 0.0

    for symbol in symbols:
        price = clean[symbol]
        quantity = floor(per_stock_budget / price)
        amount = round(quantity * price, 2)
        invested += amount
        holdings.append({
            "symbol": symbol,
            "price": price,
            "quantity": quantity,
            "amount": amount,
            "unaffordable_at_equal_budget": quantity == 0,
        })

    return {
        "capital": round(float(capital), 2),
        "stock_count": len(symbols),
        "budget_per_stock": round(per_stock_budget, 2),
        "invested": round(invested, 2),
        "unallocated_cash": round(float(capital) - invested, 2),
        "holdings": holdings,
    }


def get_latest_raw_prices(symbols):
    """Read the latest imported raw close for each exact company symbol."""
    from sqlalchemy import text
    from backend.database import engine

    if not symbols:
        return {}

    result = {}
    with engine.connect() as connection:
        for symbol in symbols:
            row = connection.execute(
                text("""
                    SELECT
                        c.symbol,
                        sp.trade_date,
                        sp.close_price,
                        sp.price_source
                    FROM companies c
                    JOIN stock_prices sp ON sp.company_id = c.id
                    WHERE c.symbol = :symbol
                      AND sp.close_price IS NOT NULL
                    ORDER BY sp.trade_date DESC
                    LIMIT 1
                """),
                {"symbol": symbol},
            ).mappings().first()

            if row is not None:
                price = float(row["close_price"])
                if not isfinite(price) or price <= 0:
                    continue
                result[symbol] = {
                    "symbol": symbol,
                    "trade_date": str(row["trade_date"]),
                    "price": price,
                    "price_source": row["price_source"],
                    "price_basis": "RAW_CLOSE_UNADJUSTED",
                }

    return result


def build_real_world_research_context(question: str, operation: str):
    """Build evidence-backed latest-price or affordability context."""
    symbols = extract_symbols(question)

    if not symbols:
        return (
            "REAL-WORLD STOCK RESEARCH: No explicit NSE ticker symbol was "
            "identified. Ask the user for the exact NSE symbol. Do not guess."
        )

    records = get_latest_raw_prices(symbols)
    missing = [symbol for symbol in symbols if symbol not in records]

    if not records:
        return (
            "REAL-WORLD STOCK RESEARCH: No imported closing price is available "
            f"for the requested symbols: {', '.join(symbols)}. "
            "Do not invent a quote."
        )

    lines = [
        "VERIFIED LATEST IMPORTED STOCK PRICES",
        "Source: GREEDY STOCKS stock_prices database.",
        "Price basis: raw unadjusted closing price, not a live quote.",
    ]

    for symbol, item in records.items():
        lines.append(
            f"{symbol}: Rs {item['price']:.2f}; "
            f"trade date: {item['trade_date']}; "
            f"source: {item['price_source'] or 'not recorded'}."
        )

    if missing:
        lines.append(
            "Price unavailable for: " + ", ".join(missing)
            + ". These symbols were excluded."
        )

    if operation == "affordability":
        budget = extract_budget(question)
        if budget is None:
            lines.append(
                "AFFORDABILITY NOT CALCULATED: No explicit positive rupee "
                "budget was identified. Ask the user to specify the budget."
            )
        elif missing:
            lines.append(
                "AFFORDABILITY NOT CALCULATED: At least one requested "
                "symbol has no available price. Ask whether to continue "
                "with only the available symbols."
            )
        else:
            allocation = allocate_equal_whole_shares(
                symbols,
                {symbol: item["price"] for symbol, item in records.items()},
                budget,
            )
            lines.append(
                "DETERMINISTIC WHOLE-SHARE AFFORDABILITY RESULT:"
            )
            lines.append(json.dumps(allocation, indent=2))

    lines.extend([
        "Prices are historical imported closes, not executable broker quotes.",
        "Taxes, brokerage, slippage and other transaction charges are excluded.",
        "Do not describe these results as a guaranteed purchase or recommendation.",
    ])

    return "\n".join(lines)
