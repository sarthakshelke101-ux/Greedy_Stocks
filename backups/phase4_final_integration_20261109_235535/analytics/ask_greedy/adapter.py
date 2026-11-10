"""AI-facing calculation adapter. Does not modify the chat route."""
from .calculations import (
    portfolio_return, sharpe_ratio, portfolio_volatility,
    validate_correlation_matrix, maximum_sharpe,
    drawdown, whole_share_allocation
)

AVAILABLE_CALCULATIONS = {
    "portfolio_return": portfolio_return,
    "sharpe_ratio": sharpe_ratio,
    "portfolio_volatility": portfolio_volatility,
    "validate_correlation_matrix": validate_correlation_matrix,
    "maximum_sharpe": maximum_sharpe,
    "drawdown": drawdown,
    "whole_share_allocation": whole_share_allocation,
}

SYSTEM_INSTRUCTION = """
You are Ask GREEDY, a beginner-friendly financial education assistant.
You may calculate from numbers explicitly supplied by the user even when
market data is unavailable. Never claim missing application data prevents
ordinary mathematical calculations.

For numerical finance questions:
1. Identify the supplied inputs and assumptions.
2. Use the deterministic calculation engine when a supported operation fits.
3. Never invent market data or silently change assumptions.
4. Verify returned values and explain units and annualisation.
5. Distinguish mathematical examples from actual market observations.
6. If an operation is unsupported, explain exactly what is missing.
7. Never claim a calculation was tool-verified unless the tool was run.
8. Do not append irrelevant product disclaimers to ordinary arithmetic.
"""
