"""Capital allocation for GREEDY STOCKS portfolios."""

from math import floor, isfinite


def allocate_capital(
    symbols: list[str],
    prices: dict[str, float],
    capital: float,
) -> dict:
    """Allocate capital equally across selected stocks using whole shares."""
    if not isinstance(capital, (int, float)) or isinstance(capital, bool):
        raise ValueError("Capital must be a number.")
    if not isfinite(capital) or capital <= 0:
        raise ValueError("Capital must be finite and greater than zero.")
    if not symbols or len(symbols) > 10 or len(set(symbols)) != len(symbols):
        raise ValueError("Select between 1 and 10 unique stocks.")

    clean_prices = {}
    for symbol in symbols:
        price = prices.get(symbol)
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            raise ValueError(f"Missing valid price for {symbol}.")
        if not isfinite(price) or price <= 0:
            raise ValueError(f"Invalid price for {symbol}.")
        clean_prices[symbol] = float(price)

    minimum = sum(clean_prices.values())
    if minimum > capital:
        raise ValueError(
            f"Insufficient capital. At least ?{minimum:.2f} is required "
            "to buy one share of every selected stock."
        )

    budget_per_stock = capital / len(symbols)
    holdings = []
    invested = 0.0

    for symbol in symbols:
        price = clean_prices[symbol]
        quantity = floor(budget_per_stock / price)
        amount = round(quantity * price, 2)
        invested += amount
        holdings.append({
            "symbol": symbol,
            "price": price,
            "quantity": quantity,
            "invested": amount,
            "weight": 0.0,
        })

    invested = round(invested, 2)
    for holding in holdings:
        holding["weight"] = round(
            holding["invested"] / invested, 6
        ) if invested else 0.0

    return {
        "capital": round(float(capital), 2),
        "invested": invested,
        "cash_remaining": round(float(capital) - invested, 2),
        "stock_count": len(symbols),
        "holdings": holdings,
    }
