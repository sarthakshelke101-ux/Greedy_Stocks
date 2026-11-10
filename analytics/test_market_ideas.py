"""Tests for the GREEDY STOCKS Market Ideas engine."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from analytics import market_ideas as mi


def sample_ranking():
    """Build a small deterministic ranking dataset for testing."""
    rows = [
        # Positive sector
        ("POS_A", "Positive A Ltd", "Positive Sector", 8.0, 20.0, -5.0),
        ("POS_B", "Positive B Ltd", "Positive Sector", 4.0, 22.0, -6.0),

        # Negative sector
        ("NEG_A", "Negative A Ltd", "Negative Sector", -8.0, 25.0, -12.0),
        ("NEG_B", "Negative B Ltd", "Negative Sector", -4.0, 24.0, -10.0),

        # Flat sector
        ("FLAT_A", "Flat A Ltd", "Flat Sector", 0.0, 18.0, -3.0),
        ("FLAT_B", "Flat B Ltd", "Flat Sector", 0.0, 19.0, -4.0),

        # Single-company sector should be excluded
        ("SINGLE", "Single Ltd", "Single Sector", 5.0, 21.0, -7.0),
    ]

    result = pd.DataFrame(
        [
            {
                "symbol": symbol,
                "company_name": company_name,
                "sector": sector,
                "period_return": period_return,
                "annualized_volatility": volatility,
                "maximum_drawdown": drawdown,
                "sharpe_ratio": 0.5,
                "return_rank": index + 1,
                "observations": 100,
                "data_status": "CALCULATED",
                "last_price_date": pd.Timestamp("2026-11-05"),
            }
            for index, (
                symbol,
                company_name,
                sector,
                period_return,
                volatility,
                drawdown,
            ) in enumerate(rows)
        ]
    )

    result.attrs.update(
        {
            "index": "NIFTY 50",
            "snapshot_month": "2026-10-01",
            "price_basis": "SPLIT_BONUS_ADJUSTED",
            "dividend_adjusted": False,
            "membership_basis": "LATEST_MONTHLY_SNAPSHOT",
            "corporate_action_coverage": "PARTIAL",
        }
    )

    return result


class TestMarketIdeas(unittest.TestCase):

    def setUp(self):
        self.ranking = sample_ranking()

    def test_performance_standouts(self):
        ideas = mi.performance_standouts(
            self.ranking,
            "3M",
            top_n=3,
        )

        self.assertEqual(len(ideas), 3)
        self.assertTrue(
            all(
                idea["category"] == "PERFORMANCE_STANDOUTS"
                for idea in ideas
            )
        )

        self.assertEqual(
            ideas[0]["evidence"]["symbol"],
            "POS_A",
        )

    def test_risk_stability_insights(self):
        ideas = mi.risk_stability_insights(
            self.ranking,
            "3M",
            top_n=3,
        )

        self.assertEqual(len(ideas), 3)

        volatilities = [
            idea["evidence"]["annualized_volatility_pct"]
            for idea in ideas
        ]

        self.assertEqual(volatilities, sorted(volatilities))

    def test_sector_positive_negative_and_flat_classification(self):
        ideas = mi.sector_opportunities(
            self.ranking,
            "3M",
            top_n=10,
        )

        classifications = {
            idea["evidence"]["sector"]:
                idea["evidence"]["classification"]
            for idea in ideas
        }

        self.assertEqual(
            classifications["Positive Sector"],
            "POSITIVE_HISTORICAL_PERFORMANCE",
        )

        self.assertEqual(
            classifications["Negative Sector"],
            "NEGATIVE_HISTORICAL_PERFORMANCE",
        )

        self.assertEqual(
            classifications["Flat Sector"],
            "FLAT_HISTORICAL_PERFORMANCE",
        )

        self.assertNotIn("Single Sector", classifications)

    def test_sector_requires_at_least_two_companies(self):
        ideas = mi.sector_opportunities(
            self.ranking,
            "3M",
            top_n=10,
        )

        sectors = {
            idea["evidence"]["sector"]
            for idea in ideas
        }

        self.assertNotIn("Single Sector", sectors)

    def test_missing_sector_is_handled(self):
        row = self.ranking.iloc[0].copy()
        row["sector"] = None

        company = mi.company_reference(row)

        self.assertEqual(company["sector"], "Unclassified")

    def test_missing_greedy_log_returns_unavailable_idea(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_file = Path(temp_dir) / "missing.csv"

            with patch.object(mi, "GREEDY_LOG", missing_file):
                ideas = mi.greedy_experimental_insights()

        self.assertEqual(len(ideas), 1)
        self.assertEqual(ideas[0]["category"], "GREEDY_PICKS")
        self.assertEqual(ideas[0]["status"], "UNAVAILABLE")

    def test_greedy_log_missing_required_columns_raises_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "greedy.csv"
            pd.DataFrame(
                {"step": [1], "selected_symbol": ["TEST"]}
            ).to_csv(log_file, index=False)

            with patch.object(mi, "GREEDY_LOG", log_file):
                with self.assertRaises(ValueError):
                    mi.greedy_experimental_insights()

    def test_greedy_log_generates_historical_experiment_ideas(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "greedy.csv"

            pd.DataFrame(
                {
                    "step": [2, 1],
                    "selected_symbol": ["TEST_B", "TEST_A"],
                    "sector": ["Sector B", "Sector A"],
                    "portfolio_sharpe": [0.8, 0.5],
                    "previous_portfolio_sharpe": [0.4, 0.2],
                    "candidates_evaluated": [10, 10],
                    "sector_limit": [3, 3],
                }
            ).to_csv(log_file, index=False)

            with patch.object(mi, "GREEDY_LOG", log_file):
                ideas = mi.greedy_experimental_insights(top_n=2)

        self.assertEqual(len(ideas), 2)
        self.assertEqual(
            ideas[0]["evidence"]["symbol"],
            "TEST_A",
        )
        self.assertEqual(
            ideas[0]["evidence"]["classification"],
            "HISTORICAL_TRAINING_EXPERIMENT",
        )
        self.assertIn("not live", ideas[0]["risk"])

    def test_fundamental_research_is_not_fabricated(self):
        idea = mi.fundamental_research_status()

        self.assertEqual(
            idea["category"],
            "FUNDAMENTAL_RESEARCH",
        )
        self.assertEqual(
            idea["status"],
            "NOT_YET_AVAILABLE",
        )
        self.assertFalse(
            idea["evidence"]["fundamental_data_available"]
        )
        self.assertFalse(
            idea["evidence"]["valuation_claims_enabled"]
        )

    def test_stock_comparison_builds_union_and_overlap(self):
        ideas = [
            {
                "category": "PERFORMANCE_STANDOUTS",
                "status": "AVAILABLE",
                "evidence": {
                    "symbol": "AAA",
                    "company_name": "AAA Ltd",
                    "period_return_pct": 12.0,
                    "annualized_volatility_pct": 20.0,
                    "maximum_drawdown_pct": -5.0,
                    "sharpe_ratio": 1.2,
                },
            },
            {
                "category": "PERFORMANCE_STANDOUTS",
                "status": "AVAILABLE",
                "evidence": {
                    "symbol": "BBB",
                    "company_name": "BBB Ltd",
                    "period_return_pct": 8.0,
                    "annualized_volatility_pct": 18.0,
                    "maximum_drawdown_pct": -4.0,
                    "sharpe_ratio": 0.9,
                },
            },
            {
                "category": "RISK_AND_STABILITY",
                "status": "AVAILABLE",
                "evidence": {
                    "symbol": "BBB",
                    "company_name": "BBB Ltd",
                    "period_return_pct": 8.0,
                    "annualized_volatility_pct": 18.0,
                    "maximum_drawdown_pct": -4.0,
                    "sharpe_ratio": 0.9,
                },
            },
            {
                "category": "RISK_AND_STABILITY",
                "status": "AVAILABLE",
                "evidence": {
                    "symbol": "CCC",
                    "company_name": "CCC Ltd",
                    "period_return_pct": -2.0,
                    "annualized_volatility_pct": 12.0,
                    "maximum_drawdown_pct": -6.0,
                    "sharpe_ratio": -0.2,
                },
            },
        ]

        result = mi.build_stock_comparison(ideas)

        self.assertEqual(
            [stock["symbol"] for stock in result["stocks"]],
            ["AAA", "BBB", "CCC"],
        )
        self.assertEqual(result["stock_count"], 3)
        self.assertEqual(result["overlap_symbols"], ["BBB"])
        self.assertEqual(
            result["stocks"][1]["categories"],
            ["Performance", "Low Volatility"],
        )

    def test_stock_comparison_preserves_missing_metrics(self):
        ideas = [{
            "category": "PERFORMANCE_STANDOUTS",
            "status": "AVAILABLE",
            "evidence": {
                "symbol": "MISS",
                "period_return_pct": 5.0,
                "annualized_volatility_pct": None,
                "maximum_drawdown_pct": -3.0,
                "sharpe_ratio": None,
            },
        }]

        result = mi.build_stock_comparison(ideas)
        stock = result["stocks"][0]

        self.assertIsNone(stock["annualized_volatility_pct"])
        self.assertIsNone(stock["sharpe_ratio"])

    def test_stock_comparison_ignores_unavailable_and_duplicate_records(self):
        ideas = [
            {
                "category": "PERFORMANCE_STANDOUTS",
                "status": "AVAILABLE",
                "evidence": {"symbol": "AAA", "period_return_pct": 5.0},
            },
            {
                "category": "PERFORMANCE_STANDOUTS",
                "status": "AVAILABLE",
                "evidence": {"symbol": "AAA", "period_return_pct": 5.0},
            },
            {
                "category": "RISK_AND_STABILITY",
                "status": "UNAVAILABLE",
                "evidence": {"symbol": "BBB"},
            },
        ]

        result = mi.build_stock_comparison(ideas)

        self.assertEqual(result["stock_count"], 1)
        self.assertEqual(
            [stock["symbol"] for stock in result["stocks"]],
            ["AAA"],
        )
        self.assertEqual(result["overlap_symbols"], [])

    def test_stock_comparison_handles_empty_input(self):
        result = mi.build_stock_comparison([])

        self.assertEqual(result["stocks"], [])
        self.assertEqual(result["stock_count"], 0)
        self.assertEqual(result["overlap_symbols"], [])

    def test_invalid_period_is_rejected(self):
        with self.assertRaises(ValueError):
            mi.generate_market_ideas(period="5Y")

    def test_non_string_period_is_rejected(self):
        with self.assertRaises(ValueError):
            mi.generate_market_ideas(period=3)

    def test_invalid_top_n_is_rejected(self):
        for value in [0, 11, -1, 2.5, True, "5"]:
            with self.subTest(top_n=value):
                with self.assertRaises(ValueError):
                    mi.generate_market_ideas(top_n=value)

    def test_generate_market_ideas_builds_expected_categories(self):
        with (
            patch.object(
                mi,
                "run_historical_rankings",
                return_value=self.ranking,
            ),
            patch.object(
                mi,
                "greedy_experimental_insights",
                return_value=[],
            ),
        ):
            report = mi.generate_market_ideas(
                period="3M",
                top_n=3,
            )

        categories = {
            idea["category"]
            for idea in report["ideas"]
        }

        expected = {
            "PERFORMANCE_STANDOUTS",
            "RISK_AND_STABILITY",
            "SECTOR_PERFORMANCE",
            "FUNDAMENTAL_RESEARCH",
        }

        self.assertTrue(expected.issubset(categories))
        self.assertEqual(report["metadata"]["index"], "NIFTY 50")
        self.assertFalse(report["metadata"]["database_writes"])
        self.assertEqual(report["metadata"]["universe_size"], 7)

    def test_json_output_is_valid(self):
        report = {
            "metadata": {"period": "3M"},
            "ideas": [
                {
                    "category": "TEST",
                    "evidence": {
                        "valid_number": mi.safe_number(12.34567),
                        "missing_number": mi.safe_number(float("nan")),
                    },
                }
            ],
        }

        encoded = json.dumps(
            report,
            allow_nan=False,
        )

        decoded = json.loads(encoded)

        self.assertEqual(
            decoded["ideas"][0]["evidence"]["valid_number"],
            12.3457,
        )
        self.assertIsNone(
            decoded["ideas"][0]["evidence"]["missing_number"]
        )

    def test_save_market_ideas_creates_json_file(self):
        report = {
            "metadata": {"period": "3M"},
            "ideas": [],
            "disclosures": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                mi,
                "OUTPUT_DIR",
                Path(temp_dir),
            ):
                output_file = mi.save_market_ideas(report)

                self.assertTrue(output_file.exists())

                with output_file.open(
                    "r",
                    encoding="utf-8",
                ) as file:
                    saved = json.load(file)

        self.assertEqual(saved["metadata"]["period"], "3M")
        self.assertEqual(output_file.name, "market_ideas_3m.json")


if __name__ == "__main__":
    unittest.main()
