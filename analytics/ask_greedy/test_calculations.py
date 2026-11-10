"""Tests for Ask GREEDY deterministic calculations."""
import numpy as np
import pytest

from analytics.ask_greedy.calculations import (
    portfolio_return, sharpe_ratio, portfolio_volatility,
    validate_correlation_matrix, maximum_sharpe,
    drawdown, whole_share_allocation
)


def test_weighted_portfolio_return():
    assert portfolio_return([.5,.3,.2],[.20,-.15,.05]) == pytest.approx(.065)


def test_sharpe():
    assert sharpe_ratio(.18,.06,.25) == pytest.approx(.48)


def test_three_asset_correlation_matrix_is_valid():
    c = [[1,.9,-.8],[.9,1,-.9],[-.8,-.9,1]]
    result = validate_correlation_matrix(c)
    assert result["valid"] is True
    assert result["determinant"] == pytest.approx(.036)


def test_three_asset_portfolio_volatility():
    c = [[1,.9,-.8],[.9,1,-.9],[-.8,-.9,1]]
    result = portfolio_volatility([1/3]*3,[.2,.15,.1],c)
    assert result >= 0


def test_maximum_sharpe_returns_valid_weights():
    c = [[1,.9,-.8],[.9,1,-.9],[-.8,-.9,1]]
    result = maximum_sharpe([.15,.12,.10],[.2,.15,.1],c,.05)
    assert sum(result["weights"]) == pytest.approx(1)
    assert min(result["weights"]) >= 0
    assert result["volatility"] > 0


def test_drawdown():
    assert drawdown([-.60,1.50]) == pytest.approx(-.60)


def test_whole_share_allocation_respects_capital():
    result = whole_share_allocation(10000,[4500,3000,2500,1200,800])
    assert result["invested"] <= 10000
    assert result["cash_remaining"] >= -1e-8


def test_rejects_invalid_weights():
    with pytest.raises(ValueError):
        portfolio_return([.6,.6],[.1,.2])
