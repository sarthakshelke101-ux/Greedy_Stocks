"""Beginner-friendly financial education grounded in verified GREEDY data."""

import re


CONCEPTS = {
    "volatility": {
        "aliases": ["volatility", "volatile", "price swings"],
        "definition": (
            "Volatility measures how widely an asset's returns fluctuate. "
            "Higher volatility means returns have varied more; it does not "
            "tell us whether the next move will be up or down."
        ),
        "interpretation": (
            "Annualised volatility is expressed as a percentage. It is a "
            "historical measure of variability, not a guaranteed loss limit."
        ),
        "metric": "annualized_volatility_pct",
        "label": "Annualised volatility",
    },
    "sharpe ratio": {
        "aliases": ["sharpe ratio", "sharpe"],
        "definition": (
            "The Sharpe ratio measures excess return relative to volatility. "
            "It helps compare how much historical excess return was earned "
            "for each unit of measured risk."
        ),
        "interpretation": (
            "A higher positive value was better on this historical measure. "
            "A negative value means the measured return was below the "
            "risk-free rate used by the calculation. It is not a forecast."
        ),
        "metric": "sharpe_ratio",
        "label": "Sharpe ratio",
    },
    "maximum drawdown": {
        "aliases": ["maximum drawdown", "drawdown", "peak to trough"],
        "definition": (
            "Maximum drawdown is the largest peak-to-trough decline in the "
            "measured wealth series during the selected period."
        ),
        "interpretation": (
            "For example, -20% means the series fell 20% from a previous "
            "peak at its worst point in that period. It does not mean the "
            "stock will necessarily fall by that amount again."
        ),
        "metric": "maximum_drawdown_pct",
        "label": "Maximum drawdown",
    },
    "historical return": {
        "aliases": ["historical return", "stock return", "returns", "return"],
        "definition": (
            "Historical return describes the percentage change over a "
            "completed period. It describes what happened, not what will "
            "happen next."
        ),
        "interpretation": (
            "A positive return does not show how smooth the journey was. "
            "Read it alongside volatility and drawdown."
        ),
        "metric": "period_return_pct",
        "label": "Historical return",
    },
    "diversification": {
        "aliases": ["diversification", "diversified", "concentration"],
        "definition": (
            "Diversification means spreading exposure across different "
            "companies, sectors or asset types instead of depending on "
            "one holding or one source of risk."
        ),
        "interpretation": (
            "Owning more stocks does not automatically create good "
            "diversification. Holdings can still move together, and "
            "sector concentration can remain high."
        ),
        "metric": None,
        "label": None,
    },
    "correlation": {
        "aliases": ["correlation", "correlated", "move together"],
        "definition": (
            "Correlation describes how two return series have moved "
            "together historically. It ranges from -1 to +1: positive "
            "values indicate movement in the same direction, negative "
            "values indicate movement in opposite directions, and values "
            "near zero indicate weaker linear co-movement."
        ),
        "interpretation": (
            "Correlation is not causation and can change over time. "
            "A verified pairwise correlation matrix is not supplied "
            "by this education context."
        ),
        "metric": None,
        "label": None,
    },
    "beta": {
        "aliases": ["beta", "market sensitivity"],
        "definition": (
            "Beta estimates how sensitive an asset's returns have been "
            "to movements in a chosen benchmark. A beta near 1 historically "
            "indicates similar sensitivity; above 1 indicates greater "
            "sensitivity and below 1 lower sensitivity."
        ),
        "interpretation": (
            "Beta depends on the benchmark, dates and calculation method. "
            "A verified beta value is not currently available here."
        ),
        "metric": None,
        "label": None,
    },
    "liquidity": {
        "aliases": ["liquidity", "liquid", "trading volume", "bid ask"],
        "definition": (
            "Liquidity describes how easily an asset can be bought or sold "
            "without substantially affecting its price. Trading activity, "
            "bid-ask spreads and market depth can all matter."
        ),
        "interpretation": (
            "A verified liquidity measure, bid-ask spread or market-depth "
            "feed is not supplied by this context."
        ),
        "metric": None,
        "label": None,
    },
    "risk and return": {
        "aliases": ["risk return", "risk-reward", "risk reward"],
        "definition": (
            "Risk and return should be considered together. A higher "
            "historical return may have come with larger fluctuations "
            "or deeper declines."
        ),
        "interpretation": (
            "There is no single metric that captures every kind of risk. "
            "Compare return, volatility and drawdown over the same period."
        ),
        "metric": None,
        "label": None,
    },
    "cagr": {
        "aliases": ["cagr", "compound annual growth"],
        "definition": (
            "CAGR, or compound annual growth rate, is the constant annual "
            "growth rate that would connect a starting value to an ending "
            "value over a specified number of years."
        ),
        "interpretation": (
            "CAGR smooths the path into one annualised rate. It does not "
            "show interim volatility or drawdowns. A verified CAGR value "
            "is not supplied unless explicitly present in the data."
        ),
        "metric": None,
        "label": None,
    },
}


def _matched_concepts(question):
    q = (question or "").lower()
    matches = []

    for name, item in CONCEPTS.items():
        for alias in item["aliases"]:
            if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", q):
                matches.append(name)
                break

    return matches


def _available_evidence(ideas, metric):
    if not metric:
        return []

    found = []
    seen = set()

    for idea in ideas or []:
        if idea.get("status") != "AVAILABLE":
            continue

        evidence = idea.get("evidence") or {}
        symbol = evidence.get("symbol")

        if not symbol or symbol in seen:
            continue

        value = evidence.get(metric)
        if value is None:
            continue

        seen.add(symbol)
        found.append((str(symbol), value))

    return found


def build_education_context(question, ideas=None, metadata=None):
    """Explain matched concepts and use only supplied verified metrics."""
    matches = _matched_concepts(question)
    lines = [
        "CONTEXTUAL FINANCIAL EDUCATION",
        "Purpose: teach the concept, not recommend a trade.",
        "Historical examples below are observations, not forecasts.",
        "",
    ]

    if not matches:
        lines.extend([
            "NIFTY 50 BASICS",
            "The NIFTY 50 is an index representing 50 selected large "
            "companies listed on the National Stock Exchange of India.",
            "An index is a market indicator; it is not itself a single stock.",
            "",
        ])
        return "\n".join(lines)

    for name in matches:
        item = CONCEPTS[name]
        lines.extend([
            f"CONCEPT: {name.title()}",
            f"Simple explanation: {item['definition']}",
            f"How to interpret it: {item['interpretation']}",
        ])

        metric = item["metric"]
        if metric:
            values = _available_evidence(ideas, metric)

            if values:
                period = (metadata or {}).get("period", "selected period")
                lines.append(
                    f"Verified GREEDY STOCKS examples ({period}):"
                )
                for symbol, value in values[:5]:
                    lines.append(f"- {symbol}: {value}")
            else:
                lines.append(
                    "Verified GREEDY STOCKS example: Not available "
                    "in the supplied report."
                )

        if name in ("diversification", "correlation"):
            lines.append(
                "Data limitation: this response does not contain a "
                "verified portfolio correlation matrix or complete "
                "user-holdings analysis."
            )

        if name in ("beta", "liquidity", "cagr"):
            lines.append(
                "Data limitation: the corresponding verified metric "
                "is not currently supplied."
            )

        lines.append("")

    lines.extend([
        "EDUCATIONAL SAFEGUARD",
        "Historical observations cannot guarantee future results. "
        "Do not turn a single metric into a buy or sell recommendation.",
    ])

    return "\n".join(lines)
