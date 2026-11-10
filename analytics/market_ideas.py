"""GREEDY STOCKS — Evidence-based Market Ideas Engine.

Scope:
    NIFTY 50 only.

Sources:
    Existing historical ranking engine.
    Existing Greedy selection audit log.

Important:
    Insights describe historical observations, not predictions
    or personalised investment recommendations.
    Split/bonus-adjusted prices are not total-return prices.
    Corporate-action coverage is partial.
    Greedy selections are historical in-sample experiments.
"""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.historical_rankings import run_historical_rankings


OUTPUT_DIR = ROOT / "database" / "processed" / "analytics"

GREEDY_LOG = OUTPUT_DIR / "greedy_selection_log.csv"

SUPPORTED_PERIODS = {"1M", "3M", "6M", "1Y"}


def safe_number(value, decimals=4):
    """Convert pandas/numpy numeric values to JSON-safe numbers."""
    if value is None or pd.isna(value):
        return None

    return round(float(value), decimals)


def company_reference(row):
    """Return a standard company reference."""
    return {
        "symbol": str(row["symbol"]),
        "company_name": str(row["company_name"]),
        "sector": (
            str(row["sector"])
            if pd.notna(row["sector"])
            else "Unclassified"
        ),
    }


def build_idea(
    category,
    title,
    what,
    why,
    risk,
    explore,
    evidence,
    status="AVAILABLE",
):
    """Build a consistent Market Ideas record."""
    return {
        "category": category,
        "title": title,
        "what": what,
        "why": why,
        "risk": risk,
        "explore": explore,
        "evidence": evidence,
        "status": status,
    }


def performance_standouts(ranking, period, top_n=5):
    """Identify companies with the strongest historical returns."""
    valid = ranking[
        ranking["period_return"].notna()
        & (ranking["data_status"] == "CALCULATED")
    ].copy()

    valid = valid.sort_values(
        ["period_return", "symbol"],
        ascending=[False, True],
    )

    ideas = []

    for _, row in valid.head(top_n).iterrows():
        company = company_reference(row)
        return_pct = safe_number(row["period_return"])

        ideas.append(
            build_idea(
                category="PERFORMANCE_STANDOUTS",
                title=(
                    f"{company['symbol']} — "
                    "Historical performance standout"
                ),
                what=(
                    f"{company['company_name']} recorded a "
                    f"{return_pct}% return over {period}."
                ),
                why=(
                    "It ranked among the strongest NIFTY 50 "
                    "historical performers for the selected period."
                ),
                risk=(
                    "Past performance does not predict future returns. "
                    "Review volatility, drawdown and company fundamentals "
                    "before drawing conclusions."
                ),
                explore=(
                    f"Explain the historical performance and risks "
                    f"of {company['symbol']}."
                ),
                evidence={
                    **company,
                    "period": period,
                    "period_return_pct": return_pct,
                    "return_rank": safe_number(row["return_rank"]),
                    "annualized_volatility_pct": safe_number(
                        row["annualized_volatility"]
                    ),
                    "maximum_drawdown_pct": safe_number(
                        row["maximum_drawdown"]
                    ),
                    "sharpe_ratio": safe_number(row["sharpe_ratio"]),
                    "observations": int(row["observations"]),
                },
            )
        )

    return ideas


def risk_stability_insights(ranking, period, top_n=5):
    """Find historically lower-volatility and lower-drawdown stocks."""
    valid = ranking[
        ranking["annualized_volatility"].notna()
        & ranking["maximum_drawdown"].notna()
        & (ranking["data_status"] == "CALCULATED")
    ].copy()

    if valid.empty:
        return []

    # Prefer lower volatility, then drawdowns closer to zero.
    valid = valid.sort_values(
        ["annualized_volatility", "maximum_drawdown"],
        ascending=[True, False],
    )

    ideas = []

    for _, row in valid.head(top_n).iterrows():
        company = company_reference(row)

        volatility = safe_number(row["annualized_volatility"])
        drawdown = safe_number(row["maximum_drawdown"])

        ideas.append(
            build_idea(
                category="RISK_AND_STABILITY",
                title=(
                    f"{company['symbol']} — "
                    "Lower historical volatility"
                ),
                what=(
                    f"{company['company_name']} had annualised "
                    f"volatility of {volatility}% and maximum "
                    f"drawdown of {drawdown}% over {period}."
                ),
                why=(
                    "It ranked relatively well on historical "
                    "volatility and drawdown within the available universe."
                ),
                risk=(
                    "Lower historical volatility does not mean "
                    "capital protection or low future risk. "
                    "This is not a measure of fundamental business risk."
                ),
                explore=(
                    f"Compare the historical risk profile of "
                    f"{company['symbol']} with its sector."
                ),
                evidence={
                    **company,
                    "period": period,
                    "annualized_volatility_pct": volatility,
                    "maximum_drawdown_pct": drawdown,
                    "period_return_pct": safe_number(
                        row["period_return"]
                    ),
                    "sharpe_ratio": safe_number(row["sharpe_ratio"]),
                    "observations": int(row["observations"]),
                },
            )
        )

    return ideas


def sector_opportunities(ranking, period, top_n=5):
    """Compare NIFTY 50 sector constituent performance historically."""
    valid = ranking[
        ranking["period_return"].notna()
        & ranking["sector"].notna()
        & (ranking["data_status"] == "CALCULATED")
    ].copy()

    if valid.empty:
        return []

    sector_summary = (
        valid.groupby("sector")
        .agg(
            company_count=("symbol", "count"),
            median_return=("period_return", "median"),
            median_volatility=("annualized_volatility", "median"),
            median_drawdown=("maximum_drawdown", "median"),
        )
        .reset_index()
    )

    # Require at least two available companies per sector.
    sector_summary = sector_summary[
        sector_summary["company_count"] >= 2
    ]

    sector_summary = sector_summary.sort_values(
        ["median_return", "sector"],
        ascending=[False, True],
    )

    ideas = []

    for _, row in sector_summary.head(top_n).iterrows():
        sector = str(row["sector"])
        median_return = safe_number(row["median_return"])

        if median_return > 0:
            classification = "POSITIVE_HISTORICAL_PERFORMANCE"
            title = f"{sector} — Positive historical performance"
            interpretation = (
                "The sector's median constituent return was positive "
                "over the selected historical period."
            )

        elif median_return < 0:
            classification = "NEGATIVE_HISTORICAL_PERFORMANCE"
            title = f"{sector} — Negative historical performance"
            interpretation = (
                "The sector's median constituent return was negative "
                "over the selected historical period."
            )

        else:
            classification = "FLAT_HISTORICAL_PERFORMANCE"
            title = f"{sector} — Flat historical performance"
            interpretation = (
                "The sector's median constituent return was approximately zero."
            )

        ideas.append(
            build_idea(
                category="SECTOR_PERFORMANCE",
                title=title,
                what=(
                    f"The {sector} sector had a median constituent "
                    f"return of {median_return}% over {period}."
                ),
                why=(
                    f"{interpretation} The calculation covers "
                    f"{int(row['company_count'])} available "
                    "NIFTY 50 companies."
                ),
                risk=(
                    "This is a comparison of available NIFTY 50 "
                    "constituents, not the return of a complete sector index. "
                    "It does not establish future sector performance."
                ),
                explore=(
                    f"Show the NIFTY 50 companies and historical risks "
                    f"within the {sector} sector."
                ),
                evidence={
                    "sector": sector,
                    "period": period,
                    "company_count": int(row["company_count"]),
                    "median_return_pct": median_return,
                    "median_volatility_pct": safe_number(
                        row["median_volatility"]
                    ),
                    "median_drawdown_pct": safe_number(
                        row["median_drawdown"]
                    ),
                    "classification": classification,
                },
            )
        )

    return ideas


def greedy_experimental_insights(top_n=10):
    """Read the existing Greedy selection audit log."""
    if not GREEDY_LOG.exists():
        return [
            build_idea(
                category="GREEDY_PICKS",
                title="Greedy selection log unavailable",
                what="The historical Greedy selection log was not found.",
                why="The engine cannot verify the selection sequence.",
                risk="No Greedy selection claims are being generated.",
                explore="Explore how the Greedy portfolio algorithm works.",
                evidence={},
                status="UNAVAILABLE",
            )
        ]

    log = pd.read_csv(GREEDY_LOG)

    required = {
        "step",
        "selected_symbol",
        "sector",
        "portfolio_sharpe",
        "candidates_evaluated",
        "sector_limit",
    }

    missing = required - set(log.columns)

    if missing:
        raise ValueError(
            f"Greedy selection log missing columns: {sorted(missing)}"
        )

    log = log.sort_values("step").head(top_n)

    ideas = []

    for _, row in log.iterrows():
        symbol = str(row["selected_symbol"])
        sector = str(row["sector"])

        ideas.append(
            build_idea(
                category="GREEDY_PICKS",
                title=f"{symbol} — Historical Greedy selection",
                what=(
                    f"{symbol} was selected at step "
                    f"{int(row['step'])} of the historical Greedy experiment."
                ),
                why=(
                    "The algorithm selected this candidate based on "
                    "the portfolio Sharpe objective at that selection step."
                ),
                risk=(
                    "These selections were optimised using historical "
                    "training data. Training-period optimisation can "
                    "overfit and may not generalise to unseen periods. "
                    "These are not live or out-of-sample picks."
                ),
                explore=(
                    f"Explain why {symbol} was selected by the "
                    "Greedy Algorithm and what risks it carries."
                ),
                evidence={
                    "symbol": symbol,
                    "sector": sector,
                    "selection_step": int(row["step"]),
                    "portfolio_sharpe_at_step": safe_number(
                        row["portfolio_sharpe"]
                    ),
                    "previous_portfolio_sharpe": safe_number(
                        row["previous_portfolio_sharpe"]
                    ),
                    "candidates_evaluated": int(
                        row["candidates_evaluated"]
                    ),
                    "sector_limit": int(row["sector_limit"]),
                    "source": GREEDY_LOG.name,
                    "classification": "HISTORICAL_TRAINING_EXPERIMENT",
                },
            )
        )

    return ideas


def fundamental_research_status():
    """Do not invent fundamental or valuation information."""
    return build_idea(
        category="FUNDAMENTAL_RESEARCH",
        title="Fundamental research data not yet integrated",
        what=(
            "Verified company fundamentals and valuation data "
            "are not yet connected to this Market Ideas engine."
        ),
        why=(
            "Fundamental research requires sourced financial statements, "
            "ratios and consistent reporting periods."
        ),
        risk=(
            "Historical share prices alone cannot establish whether "
            "a company is undervalued, overvalued or financially healthy."
        ),
        explore=(
            "Explain which fundamental metrics are needed to analyse "
            "a NIFTY 50 company."
        ),
        evidence={
            "fundamental_data_available": False,
            "valuation_claims_enabled": False,
        },
        status="NOT_YET_AVAILABLE",
    )


def build_stock_comparison(ideas):
    """Build a deterministic union of performance and risk rankings."""
    category_order = [
        ("PERFORMANCE_STANDOUTS", "Performance"),
        ("RISK_AND_STABILITY", "Low Volatility"),
    ]

    stocks = {}

    for category, label in category_order:
        for idea in ideas:
            if (
                idea.get("category") != category
                or idea.get("status") != "AVAILABLE"
            ):
                continue

            evidence = idea.get("evidence") or {}
            symbol = evidence.get("symbol")

            if not symbol:
                continue

            symbol = str(symbol).strip().upper()
            if not symbol:
                continue

            if symbol not in stocks:
                stocks[symbol] = {
                    "symbol": symbol,
                    "company_name": evidence.get("company_name"),
                    "period_return_pct": evidence.get("period_return_pct"),
                    "annualized_volatility_pct": evidence.get(
                        "annualized_volatility_pct"
                    ),
                    "maximum_drawdown_pct": evidence.get(
                        "maximum_drawdown_pct"
                    ),
                    "sharpe_ratio": evidence.get("sharpe_ratio"),
                    "categories": [],
                }

            record = stocks[symbol]

            if label not in record["categories"]:
                record["categories"].append(label)

            # Fill missing values from the second category if available.
            for field in (
                "company_name",
                "period_return_pct",
                "annualized_volatility_pct",
                "maximum_drawdown_pct",
                "sharpe_ratio",
            ):
                if record[field] is None and evidence.get(field) is not None:
                    record[field] = evidence[field]

    result = list(stocks.values())

    overlap = [
        stock["symbol"]
        for stock in result
        if "Performance" in stock["categories"]
        and "Low Volatility" in stock["categories"]
    ]

    return {
        "stocks": result,
        "stock_count": len(result),
        "overlap_symbols": overlap,
    }


def generate_market_ideas(period="3M", top_n=5):
    """Generate structured, evidence-backed NIFTY 50 market ideas."""
    if not isinstance(period, str):
        raise ValueError("Period must be a string.")

    period = period.upper()

    if period not in SUPPORTED_PERIODS:
        raise ValueError(
            f"Unsupported period {period}. "
            f"Choose from {sorted(SUPPORTED_PERIODS)}."
        )

    if not isinstance(top_n, int) or isinstance(top_n, bool):
        raise ValueError("top_n must be an integer.")

    if top_n < 1 or top_n > 10:
        raise ValueError("top_n must be between 1 and 10.")

    print(f"Generating Market Ideas for {period}...")

    ranking = run_historical_rankings(period)

    metadata = {
        "index": ranking.attrs.get("index", "NIFTY 50"),
        "period": period,
        "requested_start_date": ranking.attrs.get("requested_start_date"),
        "common_end_date": ranking.attrs.get("common_end_date"),
        "snapshot_month": str(ranking.attrs.get("snapshot_month")),
        "price_basis": ranking.attrs.get("price_basis"),
        "dividend_adjusted": ranking.attrs.get("dividend_adjusted"),
        "membership_basis": ranking.attrs.get("membership_basis"),
        "corporate_action_coverage": ranking.attrs.get(
            "corporate_action_coverage"
        ),
        "data_as_of": (
            str(ranking["last_price_date"].max())
            if (
                "last_price_date" in ranking.columns
                and ranking["last_price_date"].notna().any()
            )
            else None
        ),
        "universe_size": int(len(ranking)),
        "calculated_companies": int(
            (ranking["data_status"] == "CALCULATED").sum()
        ),
        "insufficient_data_companies": int(
            (ranking["data_status"] != "CALCULATED").sum()
        ),
        "database_writes": False,
        "interpretation": "HISTORICAL_RESEARCH_NOT_INVESTMENT_ADVICE",
    }

    ideas = []

    ideas.extend(
        performance_standouts(ranking, period, top_n)
    )

    ideas.extend(
        risk_stability_insights(ranking, period, top_n)
    )

    ideas.extend(
        sector_opportunities(ranking, period, top_n)
    )

    ideas.extend(
        greedy_experimental_insights(top_n=10)
    )

    ideas.append(fundamental_research_status())

    report = {
        "product": "GREEDY STOCKS",
        "report_type": "MARKET_IDEAS",
        "metadata": metadata,
        "ideas": ideas,
        "comparison": build_stock_comparison(ideas),
        "disclosures": [
            "Insights describe historical observations, not forecasts.",
            "The universe uses the latest monthly NIFTY 50 snapshot.",
            "Historical daily membership is not reconstructed.",
            "Prices are split/bonus adjusted where imported actions apply.",
            "Corporate-action coverage is partial.",
            "Dividends are excluded; this is not a total-return series.",
            (
                "Greedy selections are in-sample historical experiments, "
                "not live or out-of-sample recommendations."
            ),
            (
                "Fundamental and valuation claims are not generated "
                "without verified data."
            ),
        ],
    }

    return report


def save_market_ideas(report):
    """Save a JSON report without writing to the database."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    period = report["metadata"]["period"]
    output_file = OUTPUT_DIR / f"market_ideas_{period.lower()}.json"

    with output_file.open("w", encoding="utf-8") as file:
        json.dump(
            report,
            file,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    return output_file


def print_market_ideas(report):
    """Print a readable Market Ideas report."""
    metadata = report["metadata"]

    print("\n" + "=" * 85)
    print("GREEDY STOCKS — MARKET IDEAS")
    print("=" * 85)

    print(f"Index: {metadata['index']}")
    print(f"Period: {metadata['period']}")
    print(f"Data as of: {metadata['data_as_of']}")
    print(f"Snapshot month: {metadata['snapshot_month']}")
    print(f"Companies calculated: {metadata['calculated_companies']}/50")
    print(f"Price basis: {metadata['price_basis']}")
    print(f"Corporate actions: {metadata['corporate_action_coverage']}")
    print(f"Dividend adjusted: {metadata['dividend_adjusted']}")

    for idea in report["ideas"]:
        print("\n" + "-" * 85)
        print(f"[{idea['category']}] {idea['title']}")
        print(f"What: {idea['what']}")
        print(f"Why: {idea['why']}")
        print(f"Risk: {idea['risk']}")
        print(f"Explore: {idea['explore']}")
        print(f"Status: {idea['status']}")

    print("\n" + "=" * 85)
    print("DISCLOSURES")

    for disclosure in report["disclosures"]:
        print(f"- {disclosure}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate GREEDY STOCKS Market Ideas."
    )

    parser.add_argument(
        "--period",
        choices=sorted(SUPPORTED_PERIODS),
        default="3M",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=5,
    )

    args = parser.parse_args()

    market_ideas = generate_market_ideas(
        period=args.period,
        top_n=args.top,
    )

    print_market_ideas(market_ideas)

    saved_file = save_market_ideas(market_ideas)

    print(f"\nSaved report: {saved_file}")
    print("No database writes performed.")
