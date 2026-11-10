"""Phase 5 Ask GREEDY integration regression tests."""

import pytest

import backend.chat_routes as chat


@pytest.mark.parametrize("question", [
    "Explain volatility",
    "What is Sharpe ratio?",
    "Explain maximum drawdown",
    "What is diversification?",
    "Explain beta",
    "What is liquidity?",
    "Explain CAGR",
])
def test_pure_education_uses_education_intent(question):
    assert chat.detect_intents(question) == ["EDUCATION"]


def test_pure_education_does_not_generate_market_ideas(monkeypatch):
    def unexpected_call(**kwargs):
        raise AssertionError(
            "Pure education must not generate Market Ideas."
        )

    monkeypatch.setattr(
        chat, "generate_market_ideas", unexpected_call
    )

    context = chat.build_financial_context("Explain volatility")

    assert "CONCEPT:" in context
    assert "Historical observations" in context


def test_pure_education_sharpe_does_not_generate_market_ideas(
    monkeypatch,
):
    def unexpected_call(**kwargs):
        raise AssertionError(
            "Pure education must not generate Market Ideas."
        )

    monkeypatch.setattr(
        chat, "generate_market_ideas", unexpected_call
    )

    context = chat.build_financial_context("What is Sharpe ratio?")

    assert "CONCEPT:" in context
    assert "excess return" in context.lower()


def test_mixed_education_and_stock_research_preserved():
    intents = chat.detect_intents(
        "Explain volatility and show the least volatile stocks"
    )

    assert "EDUCATION" in intents
    assert "RISK_AND_STABILITY" in intents


def test_mixed_context_contains_education_and_verified_data(
    monkeypatch,
):
    ideas = [{
        "status": "AVAILABLE",
        "evidence": {
            "symbol": "TESTCO",
            "annualized_volatility_pct": 24.5,
            "sharpe_ratio": 1.2,
        },
    }]

    calls = []

    def fake_market_ideas(**kwargs):
        calls.append(kwargs)
        return {
            "ideas": ideas,
            "metadata": {"period": "3M"},
            "comparison": None,
        }

    monkeypatch.setattr(
        chat, "generate_market_ideas", fake_market_ideas
    )
    monkeypatch.setattr(
        chat, "format_insights",
        lambda **kwargs: "VERIFIED TEST METRICS",
    )

    context = chat.build_financial_context(
        "Explain volatility and show the least volatile stocks"
    )

    assert calls
    assert "VERIFIED TEST METRICS" in context
    assert "CONCEPT:" in context
    assert "TESTCO: 24.5" in context


def test_missing_metrics_are_not_fabricated():
    context = chat.build_financial_context("Explain beta")

    assert "verified beta value is not currently available" in context
    assert "buy or sell recommendation" in context.lower()


def test_gemini_unavailable_uses_deterministic_fallback(monkeypatch):
    monkeypatch.setattr(
        chat, "generate_gemini_answer", lambda **kwargs: None
    )

    answer = chat.generate_greedy_answer(
        "Explain beta", []
    )

    assert "GREEDY AI is temporarily unavailable" in answer
    assert "CONCEPT:" in answer


def test_gemini_success_returns_ai_answer(monkeypatch):
    monkeypatch.setattr(
        chat,
        "generate_gemini_answer",
        lambda **kwargs: "Mocked educational answer.",
    )

    answer = chat.generate_greedy_answer(
        "Explain beta", []
    )

    assert answer == "Mocked educational answer."


def test_gemini_empty_response_uses_fallback(monkeypatch):
    monkeypatch.setattr(
        chat, "generate_gemini_answer", lambda **kwargs: ""
    )

    answer = chat.generate_greedy_answer(
        "Explain volatility", []
    )

    assert "temporarily unavailable" in answer


def test_general_help_remains_general():
    assert chat.detect_intents("How do I use this application?") == [
        "GENERAL"
    ]


def test_stock_performance_intent_is_preserved():
    assert "PERFORMANCE_STANDOUTS" in chat.detect_intents(
        "Show the best performing stocks"
    )


def test_education_engine_and_gemini_configuration():
    from analytics.ask_greedy.financial_education import CONCEPTS
    import os

    assert len(CONCEPTS) >= 10
    assert os.getenv("GEMINI_API_KEY")
