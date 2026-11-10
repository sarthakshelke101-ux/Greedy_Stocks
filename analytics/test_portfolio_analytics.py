import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analytics"))

from portfolio_analytics import (
    calculate_portfolio,
    compare_with_benchmark,
    validate_portfolio,
)


class TestPortfolioAnalytics(unittest.TestCase):

    def setUp(self):
        dates = pd.bdate_range("2025-01-01", periods=100)

        self.prices = pd.DataFrame(
            {
                "RELIANCE": 100 * np.cumprod(1 + np.full(100, 0.001)),
                "HDFCBANK": 200 * np.cumprod(1 + np.full(100, 0.002)),
                "INFY": 300 * np.cumprod(1 + np.full(100, -0.0005)),
                "TCS": 400 * np.cumprod(1 + np.full(100, 0.0015)),
            },
            index=dates,
        )

        self.sectors = {
            "RELIANCE": "Energy",
            "HDFCBANK": "Banking",
            "INFY": "IT",
            "TCS": "IT",
        }

    def test_equal_weights(self):
        result = calculate_portfolio(self.prices, self.sectors)
        self.assertAlmostEqual(sum(result["weights"].values()), 1.0)
        for weight in result["weights"].values():
            self.assertAlmostEqual(weight, 0.25)

    def test_sector_allocation(self):
        result = calculate_portfolio(self.prices, self.sectors)
        self.assertAlmostEqual(result["sector_allocation"]["IT"], 0.50)
        self.assertAlmostEqual(result["sector_allocation"]["Energy"], 0.25)
        self.assertAlmostEqual(result["sector_allocation"]["Banking"], 0.25)

    def test_sector_limit_rejected(self):
        sectors = {
            "A": "IT", "B": "IT", "C": "IT", "D": "IT"
        }
        with self.assertRaises(ValueError):
            validate_portfolio(["A", "B", "C", "D"], sectors)

    def test_maximum_stock_limit(self):
        symbols = [f"S{i}" for i in range(11)]
        sectors = {symbol: f"Sector{i}" for i, symbol in enumerate(symbols)}
        with self.assertRaises(ValueError):
            validate_portfolio(symbols, sectors)

    def test_duplicate_symbols_rejected(self):
        with self.assertRaises(ValueError):
            validate_portfolio(
                ["RELIANCE", "RELIANCE"],
                self.sectors,
            )

    def test_missing_sector_rejected(self):
        with self.assertRaises(ValueError):
            calculate_portfolio(
                self.prices,
                {"RELIANCE": "Energy"},
            )

    def test_missing_price_column_rejected(self):
        with self.assertRaises(ValueError):
            calculate_portfolio(
                self.prices,
                self.sectors,
                symbols=["RELIANCE", "UNKNOWN"],
            )

    def test_missing_prices_are_not_filled(self):
        prices = self.prices.copy()
        prices.loc[prices.index[20], "INFY"] = np.nan

        result = calculate_portfolio(prices, self.sectors)

        self.assertFalse(result["metadata"]["missing_values_filled"])
        self.assertLess(
            result["metadata"]["aligned_return_observations"],
            len(prices) - 1,
        )

    def test_portfolio_returns_are_equal_weighted(self):
        result = calculate_portfolio(self.prices, self.sectors)

        expected = (
            result["stock_returns"]["RELIANCE"] * 0.25
            + result["stock_returns"]["HDFCBANK"] * 0.25
            + result["stock_returns"]["INFY"] * 0.25
            + result["stock_returns"]["TCS"] * 0.25
        )

        pd.testing.assert_series_equal(
            result["daily_returns"],
            expected.rename("portfolio"),
        )

    def test_daily_rebalancing_disclosed(self):
        result = calculate_portfolio(self.prices, self.sectors)
        self.assertEqual(result["metadata"]["rebalancing"], "DAILY")

    def test_correlation_matrix(self):
        result = calculate_portfolio(self.prices, self.sectors)
        self.assertEqual(result["correlation"].shape, (4, 4))
        self.assertTrue(
            np.allclose(
                np.diag(result["correlation"]),
                1.0,
                equal_nan=True,
            )
        )

    def test_benchmark_comparison(self):
        result = calculate_portfolio(self.prices, self.sectors)
        benchmark = pd.Series(
            100 * np.cumprod(1 + np.full(100, 0.001)),
            index=self.prices.index,
        )

        comparison = compare_with_benchmark(
            result["daily_returns"],
            benchmark,
        )

        self.assertIn("excess_return_pct", comparison)
        self.assertGreater(
            comparison["common_return_observations"],
            0,
        )

    def test_zero_or_negative_prices_rejected(self):
        prices = self.prices.copy()
        prices.iloc[10, 0] = 0

        with self.assertRaises(ValueError):
            calculate_portfolio(prices, self.sectors)

    def test_duplicate_dates_rejected(self):
        prices = pd.concat([self.prices, self.prices.iloc[[0]]])

        with self.assertRaises(ValueError):
            calculate_portfolio(prices, self.sectors)


    def test_infinite_portfolio_prices_rejected(self):
        prices = self.prices.copy()
        prices.iloc[10, 0] = np.inf

        with self.assertRaisesRegex(ValueError, "finite"):
            calculate_portfolio(prices, self.sectors)

    def test_negative_infinite_portfolio_prices_rejected(self):
        prices = self.prices.copy()
        prices.iloc[10, 0] = -np.inf

        with self.assertRaisesRegex(ValueError, "finite"):
            calculate_portfolio(prices, self.sectors)

    def test_nat_portfolio_dates_rejected(self):
        prices = self.prices.copy()
        dates = list(prices.index)
        dates[10] = pd.NaT
        prices.index = pd.DatetimeIndex(dates)

        with self.assertRaisesRegex(ValueError, "NaT"):
            calculate_portfolio(prices, self.sectors)

    def test_nan_risk_free_rate_rejected(self):
        with self.assertRaises(ValueError):
            calculate_portfolio(
                self.prices,
                self.sectors,
                risk_free_rate=float("nan"),
            )

    def test_infinite_risk_free_rate_rejected(self):
        with self.assertRaises(ValueError):
            calculate_portfolio(
                self.prices,
                self.sectors,
                risk_free_rate=float("inf"),
            )

    def test_boolean_risk_free_rate_rejected(self):
        with self.assertRaises(ValueError):
            calculate_portfolio(
                self.prices,
                self.sectors,
                risk_free_rate=True,
            )

    def test_valid_negative_risk_free_rate_accepted(self):
        result = calculate_portfolio(
            self.prices,
            self.sectors,
            risk_free_rate=-0.01,
        )
        self.assertEqual(
            result["metadata"]["risk_free_rate"],
            -0.01,
        )

    def test_infinite_benchmark_prices_rejected(self):
        benchmark = pd.Series(
            100 * np.cumprod(1 + np.full(100, 0.001)),
            index=self.prices.index,
        )
        benchmark.iloc[10] = np.inf

        portfolio_returns = calculate_portfolio(
            self.prices,
            self.sectors,
        )["daily_returns"]

        with self.assertRaisesRegex(ValueError, "finite"):
            compare_with_benchmark(
                portfolio_returns,
                benchmark,
            )

    def test_nat_benchmark_dates_rejected(self):
        benchmark = pd.Series(
            100 * np.cumprod(1 + np.full(100, 0.001)),
            index=self.prices.index,
        )
        dates = list(benchmark.index)
        dates[10] = pd.NaT
        benchmark.index = pd.DatetimeIndex(dates)

        portfolio_returns = calculate_portfolio(
            self.prices,
            self.sectors,
        )["daily_returns"]

        with self.assertRaisesRegex(ValueError, "NaT"):
            compare_with_benchmark(
                portfolio_returns,
                benchmark,
            )

    def test_timezone_mismatch_in_benchmark_rejected(self):
        portfolio_returns = pd.Series(
            [0.01, 0.02, -0.01],
            index=pd.date_range("2026-01-01", periods=3),
        )
        benchmark = pd.Series(
            [100.0, 101.0, 102.0, 101.0],
            index=pd.date_range(
                "2025-12-31",
                periods=4,
                tz="UTC",
            ),
        )

        with self.assertRaisesRegex(ValueError, "timezone"):
            compare_with_benchmark(
                portfolio_returns,
                benchmark,
            )

if __name__ == "__main__":
    unittest.main(verbosity=2)
