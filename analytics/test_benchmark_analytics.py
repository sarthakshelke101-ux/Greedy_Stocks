
"""Deterministic tests for GREEDY STOCKS benchmark analytics."""

import unittest
from unittest.mock import patch

import pandas as pd

from analytics.benchmark_analytics import calculate_benchmark_metrics


class BenchmarkAnalyticsTests(unittest.TestCase):

    def setUp(self):
        self.prices = pd.Series(
            [100.0, 102.0, 101.0, 105.0],
            index=pd.to_datetime([
                "2026-01-01",
                "2026-01-02",
                "2026-01-05",
                "2026-01-06",
            ]),
            name="nifty50_close",
        )

    @patch("analytics.benchmark_analytics.get_index_closes")
    def test_benchmark_metadata(self, mock_prices):
        mock_prices.return_value = self.prices

        result = calculate_benchmark_metrics()

        self.assertEqual(result["benchmark"], "NIFTY 50")
        self.assertEqual(
            result["benchmark_type"],
            "PRICE_RETURN_INDEX",
        )
        self.assertEqual(
            result["data_source"],
            "NSE Indices Historical PR",
        )
        self.assertFalse(result["dividend_adjusted"])
        self.assertFalse(result["database_writes"])

    @patch("analytics.benchmark_analytics.get_index_closes")
    def test_benchmark_metrics_match_financial_metrics(self, mock_prices):
        mock_prices.return_value = self.prices

        result = calculate_benchmark_metrics()
        metrics = result["metrics"]

        self.assertAlmostEqual(
            metrics["period_return_pct"],
            5.0,
        )
        self.assertAlmostEqual(
            metrics["maximum_drawdown_pct"],
            -0.9803921568627416,
        )
        self.assertEqual(metrics["price_observations"], 4)
        self.assertEqual(metrics["return_observations"], 3)

    @patch("analytics.benchmark_analytics.get_index_closes")
    def test_short_history_cagr_is_suppressed(self, mock_prices):
        mock_prices.return_value = self.prices

        result = calculate_benchmark_metrics()
        metrics = result["metrics"]

        self.assertIsNone(metrics["cagr_pct"])
        self.assertEqual(
            metrics["cagr_status"],
            "SUPPRESSED_SHORT_HISTORY",
        )

    @patch("analytics.benchmark_analytics.get_index_closes")
    def test_calendar_validation_is_disclosed(self, mock_prices):
        mock_prices.return_value = self.prices

        result = calculate_benchmark_metrics()

        self.assertEqual(
            result["calendar_validation"],
            "NOT_SUPPLIED",
        )
        self.assertEqual(
            result["metrics"]["calendar_validation"],
            "NOT_SUPPLIED",
        )

    @patch("analytics.benchmark_analytics.get_index_closes")
    def test_requested_dates_are_forwarded(self, mock_prices):
        mock_prices.return_value = self.prices

        calculate_benchmark_metrics(
            start_date="2026-01-01",
            end_date="2026-01-06",
        )

        mock_prices.assert_called_once_with(
            start_date="2026-01-01",
            end_date="2026-01-06",
        )

    @patch("analytics.benchmark_analytics.get_index_closes")
    def test_empty_benchmark_data_is_rejected(self, mock_prices):
        mock_prices.return_value = pd.Series(
            dtype=float,
            name="nifty50_close",
        )

        with self.assertRaisesRegex(ValueError, "No NIFTY 50"):
            calculate_benchmark_metrics()

    @patch("analytics.benchmark_analytics.get_index_closes")
    def test_invalid_risk_free_rate_is_rejected(self, mock_prices):
        mock_prices.return_value = self.prices

        with self.assertRaises(ValueError):
            calculate_benchmark_metrics(risk_free_rate=-1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
