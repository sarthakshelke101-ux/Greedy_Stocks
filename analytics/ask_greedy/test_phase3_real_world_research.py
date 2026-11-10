import pytest

from analytics.ask_greedy.real_world_research import (
    extract_symbols,
    extract_budget,
    allocate_equal_whole_shares,
)
from analytics.ask_greedy.research_planner import fallback_research_plan


def operations(question):
    return [item["operation"] for item in fallback_research_plan(question)]


def test_extract_explicit_nse_symbol():
    assert extract_symbols("Show latest price of RELIANCE") == ["RELIANCE"]


def test_extract_multiple_symbols_without_duplicates():
    assert extract_symbols("Compare TCS and INFY with TCS") == ["TCS", "INFY"]


def test_does_not_treat_generic_market_words_as_symbols():
    assert extract_symbols("Show latest stock price on NSE") == []


def test_extract_rupee_budget():
    assert extract_budget("I have a budget of Rs 50,000") == 50000.0


def test_extract_inr_budget():
    assert extract_budget("Invest INR 125000 in these stocks") == 125000.0


def test_missing_budget_is_not_invented():
    assert extract_budget("Can I afford RELIANCE?") is None


def test_equal_budget_whole_share_allocation():
    result = allocate_equal_whole_shares(
        ["AAA", "BBB"],
        {"AAA": 100.0, "BBB": 200.0},
        1000.0,
    )
    assert [x["quantity"] for x in result["holdings"]] == [5, 2]
    assert result["invested"] == 900.0
    assert result["unallocated_cash"] == 100.0


def test_budget_below_one_share_reports_zero_quantity():
    result = allocate_equal_whole_shares(
        ["AAA"], {"AAA": 1000.0}, 500.0
    )
    assert result["holdings"][0]["quantity"] == 0
    assert result["unallocated_cash"] == 500.0


def test_invalid_price_is_rejected():
    with pytest.raises(ValueError):
        allocate_equal_whole_shares(["AAA"], {"AAA": 0}, 1000)


def test_missing_price_is_rejected():
    with pytest.raises(ValueError):
        allocate_equal_whole_shares(["AAA"], {}, 1000)


def test_non_positive_budget_is_rejected():
    with pytest.raises(ValueError):
        allocate_equal_whole_shares(["AAA"], {"AAA": 100}, 0)


def test_latest_price_routes_to_phase3_operation():
    assert "latest_price" in operations("Show latest price of RELIANCE")


def test_budget_question_routes_to_affordability():
    assert "affordability" in operations(
        "With a budget of Rs 50000, how many RELIANCE shares can I afford?"
    )


def test_education_question_does_not_trigger_phase3_price_operations():
    names = operations("Explain volatility in simple terms")
    assert "latest_price" not in names
    assert "affordability" not in names


def test_historical_research_route_is_preserved():
    names = operations("Analyse RELIANCE historical returns")
    assert "historical_analysis" in names
