"""Deterministic tests for GREEDY STOCKS financial metrics."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import math
import unittest

import pandas as pd

from analytics.financial_metrics import (
    daily_returns,
    period_return,
    annualized_volatility,
    cagr,
    maximum_drawdown,
    sharpe_ratio,
    calculate_metrics,
)


class FinancialMetricsTests(unittest.TestCase):

    def setUp(self):
        self.prices = pd.Series(
            [100.0, 110.0, 99.0],
            index=pd.to_datetime([
                "2026-01-01",
                "2026-01-02",
                "2026-01-05",
            ]),
        )

    def test_daily_returns(self):
        result = daily_returns(self.prices)
        self.assertAlmostEqual(result.iloc[0], 0.10)
        self.assertAlmostEqual(result.iloc[1], -0.10)

    def test_period_return(self):
        self.assertAlmostEqual(period_return(self.prices), -1.0)

    def test_annualized_volatility(self):
        expected = (
            pd.Series([0.10, -0.10]).std(ddof=1)
            * math.sqrt(252)
            * 100
        )
        self.assertAlmostEqual(annualized_volatility(self.prices), expected)

    def test_cagr_short_history_is_suppressed(self):
        self.assertIsNone(cagr(self.prices))

    def test_maximum_drawdown(self):
        self.assertAlmostEqual(maximum_drawdown(self.prices), -10.0)

    def test_sharpe_zero_risk_free_rate(self):
        self.assertAlmostEqual(sharpe_ratio(self.prices), 0.0)

    def test_flat_prices(self):
        prices = pd.Series(
            [100.0] * 100,
            index=pd.bdate_range("2025-01-01", periods=100),
        )
        self.assertAlmostEqual(period_return(prices), 0.0)
        self.assertAlmostEqual(cagr(prices), 0.0)
        self.assertAlmostEqual(annualized_volatility(prices), 0.0)
        self.assertAlmostEqual(maximum_drawdown(prices), 0.0)
        self.assertIsNone(sharpe_ratio(prices))

    def test_insufficient_observations(self):
        prices = pd.Series([100.0])
        self.assertIsNone(period_return(prices))
        self.assertIsNone(annualized_volatility(prices))
        self.assertIsNone(cagr(prices))
        self.assertIsNone(maximum_drawdown(prices))
        self.assertIsNone(sharpe_ratio(prices))

    def test_missing_price_is_not_forward_filled_or_bridged(self):
        prices = pd.Series([100.0, None, 110.0])
        self.assertEqual(len(daily_returns(prices)), 0)

    def test_invalid_prices_are_excluded_from_period_endpoints(self):
        prices = pd.Series([100.0, 0.0, -5.0, 110.0])
        self.assertAlmostEqual(period_return(prices), 10.0)

    def test_datetime_prices_are_sorted(self):
        prices = pd.Series(
            [99.0, 100.0, 110.0],
            index=pd.to_datetime([
                "2026-01-05",
                "2026-01-01",
                "2026-01-02",
            ]),
        )
        self.assertAlmostEqual(period_return(prices), -1.0)

    def test_duplicate_price_dates_are_rejected(self):
        prices = pd.Series(
            [100.0, 101.0],
            index=pd.to_datetime(["2026-01-01", "2026-01-01"]),
        )
        with self.assertRaisesRegex(ValueError, "Duplicate price dates"):
            daily_returns(prices)

    def test_invalid_risk_free_rate_is_rejected(self):
        with self.assertRaises(ValueError):
            sharpe_ratio(self.prices, risk_free_rate=-1.0)

    def test_invalid_trading_days_are_rejected(self):
        for value in (0, -1, 2.5, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    annualized_volatility(self.prices, trading_days=value)

    def test_metrics_metadata_discloses_raw_prices(self):
        result = calculate_metrics(self.prices)
        self.assertEqual(result["price_basis"], "RAW_CLOSE_UNADJUSTED")
        self.assertEqual(result["trading_days_per_year"], 252)

    def test_missing_expected_trading_session_is_rejected(self):
        prices = pd.Series(
            [100.0, 102.0, 104.0],
            index=pd.to_datetime([
                "2026-01-01",
                "2026-01-02",
                "2026-01-06",
            ]),
        )
        expected_sessions = pd.to_datetime([
            "2026-01-01",
            "2026-01-02",
            "2026-01-05",
            "2026-01-06",
        ])
        with self.assertRaisesRegex(ValueError, "missing prices"):
            daily_returns(prices, expected_sessions)

    def test_valid_expected_trading_sessions_are_accepted(self):
        prices = self.prices.copy()
        expected_sessions = prices.index
        returns = daily_returns(prices, expected_sessions)
        self.assertEqual(len(returns), 2)

    def test_duplicate_expected_sessions_are_rejected(self):
        expected = pd.to_datetime([
            "2026-01-01",
            "2026-01-02",
            "2026-01-02",
            "2026-01-05",
        ])
        with self.assertRaisesRegex(ValueError, "cannot contain duplicates"):
            daily_returns(self.prices, expected)

    def test_expected_calendar_requires_datetime_price_index(self):
        prices = pd.Series([100.0, 101.0, 102.0])
        expected = pd.date_range("2026-01-01", periods=3, freq="B")
        with self.assertRaisesRegex(ValueError, "DatetimeIndex"):
            daily_returns(prices, expected)

    def test_period_return_validates_expected_sessions(self):
        expected = pd.to_datetime([
            "2026-01-01",
            "2026-01-02",
            "2026-01-05",
            "2026-01-06",
        ])
        with self.assertRaisesRegex(ValueError, "missing prices"):
            period_return(self.prices, expected)

    def test_calculate_metrics_validates_calendar_before_reporting(self):
        expected = pd.to_datetime([
            "2026-01-01",
            "2026-01-02",
            "2026-01-05",
            "2026-01-06",
        ])
        with self.assertRaisesRegex(ValueError, "missing prices"):
            calculate_metrics(self.prices, expected_sessions=expected)

    def test_infinite_prices_are_rejected(self):
        prices = pd.Series(
            [100.0, float("inf"), 110.0],
            index=pd.date_range(
                "2026-01-01",
                periods=3,
            ),
        )
        with self.assertRaisesRegex(ValueError, "Prices must be positive"):
            daily_returns(prices)

    def test_negative_infinite_prices_are_rejected(self):
        prices = pd.Series(
            [100.0, float("-inf"), 110.0],
            index=pd.date_range(
                "2026-01-01",
                periods=3,
            ),
        )
        with self.assertRaisesRegex(ValueError, "Prices must be positive"):
            daily_returns(prices)

    def test_nat_price_dates_are_rejected(self):
        prices = pd.Series(
            [100.0, 110.0],
            index=pd.DatetimeIndex(["2026-01-01", None]),
        )
        with self.assertRaisesRegex(ValueError, "NaT"):
            daily_returns(prices)

    def test_timezone_mismatch_is_rejected(self):
        prices = pd.Series(
            [100.0, 110.0],
            index=pd.date_range(
                "2026-01-01", periods=2, tz="UTC"
            ),
        )
        expected = pd.date_range("2026-01-01", periods=2)
        with self.assertRaisesRegex(ValueError, "timezone"):
            daily_returns(prices, expected)

    def test_nan_risk_free_rate_is_rejected(self):
        with self.assertRaises(ValueError):
            sharpe_ratio(self.prices, risk_free_rate=float("nan"))

    def test_infinite_risk_free_rate_is_rejected(self):
        with self.assertRaises(ValueError):
            sharpe_ratio(self.prices, risk_free_rate=float("inf"))

    def test_boolean_risk_free_rate_is_rejected(self):
        with self.assertRaises(ValueError):
            sharpe_ratio(self.prices, risk_free_rate=True)

    def test_invalid_expected_sessions_with_nat_are_rejected(self):
        expected = pd.DatetimeIndex(
            ["2026-01-01", None]
        )
        with self.assertRaisesRegex(ValueError, "NaT"):
            daily_returns(self.prices, expected)

if __name__ == "__main__":
    unittest.main(verbosity=2)
