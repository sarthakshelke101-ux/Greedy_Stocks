"""Tests for contextual financial education."""

import unittest

from analytics.ask_greedy.financial_education import (
    CONCEPTS,
    build_education_context,
)


class TestFinancialEducation(unittest.TestCase):

    def test_all_core_concepts_have_definitions(self):
        required = {
            "volatility",
            "sharpe ratio",
            "maximum drawdown",
            "historical return",
            "diversification",
            "correlation",
            "beta",
            "liquidity",
            "risk and return",
            "cagr",
        }
        self.assertTrue(required.issubset(CONCEPTS))

        for concept in required:
            self.assertTrue(CONCEPTS[concept]["definition"])
            self.assertTrue(CONCEPTS[concept]["interpretation"])

    def test_volatility_uses_verified_stock_metric(self):
        ideas = [{
            "status": "AVAILABLE",
            "evidence": {
                "symbol": "TESTCO",
                "annualized_volatility_pct": 24.5,
            },
        }]

        context = build_education_context(
            "Explain volatility",
            ideas=ideas,
            metadata={"period": "3M"},
        )

        self.assertIn("TESTCO: 24.5", context)
        self.assertIn("3M", context)
        self.assertIn("historical", context.lower())

    def test_sharpe_uses_verified_metric(self):
        ideas = [{
            "status": "AVAILABLE",
            "evidence": {
                "symbol": "TESTCO",
                "sharpe_ratio": 1.25,
            },
        }]

        context = build_education_context(
            "What is Sharpe ratio?",
            ideas=ideas,
        )

        self.assertIn("TESTCO: 1.25", context)
        self.assertIn("excess return", context.lower())

    def test_drawdown_uses_verified_metric(self):
        ideas = [{
            "status": "AVAILABLE",
            "evidence": {
                "symbol": "TESTCO",
                "maximum_drawdown_pct": -18.2,
            },
        }]

        context = build_education_context(
            "Explain maximum drawdown",
            ideas=ideas,
        )

        self.assertIn("TESTCO: -18.2", context)
        self.assertIn("peak-to-trough", context)

    def test_unavailable_metric_is_not_fabricated(self):
        context = build_education_context(
            "Explain volatility",
            ideas=[],
        )

        self.assertIn("Not available", context)

    def test_unavailable_beta_is_disclosed(self):
        context = build_education_context("What is beta?")

        self.assertIn("verified beta value is not currently available", context)

    def test_diversification_discloses_missing_portfolio_data(self):
        context = build_education_context(
            "Explain diversification"
        )

        self.assertIn("correlation matrix", context)
        self.assertIn("Data limitation", context)

    def test_liquidity_does_not_invent_a_value(self):
        context = build_education_context("What is liquidity?")

        self.assertIn("verified liquidity measure", context)
        self.assertNotIn("TESTCO:", context)

    def test_duplicate_symbols_are_reported_once(self):
        ideas = [
            {
                "status": "AVAILABLE",
                "evidence": {
                    "symbol": "TESTCO",
                    "annualized_volatility_pct": 20.0,
                },
            },
            {
                "status": "AVAILABLE",
                "evidence": {
                    "symbol": "TESTCO",
                    "annualized_volatility_pct": 20.0,
                },
            },
        ]

        context = build_education_context(
            "Explain volatility",
            ideas=ideas,
        )

        self.assertEqual(context.count("- TESTCO:"), 1)

    def test_unavailable_ideas_are_ignored(self):
        ideas = [{
            "status": "UNAVAILABLE",
            "evidence": {
                "symbol": "TESTCO",
                "annualized_volatility_pct": 20.0,
            },
        }]

        context = build_education_context(
            "Explain volatility",
            ideas=ideas,
        )

        self.assertIn("Not available", context)
        self.assertNotIn("- TESTCO: 20.0", context)

    def test_nifty_basics_fallback(self):
        context = build_education_context("Explain NIFTY 50")

        self.assertIn("50 selected large companies", context)
        self.assertIn("market indicator", context)


if __name__ == "__main__":
    unittest.main()
