
import unittest
import numpy as np
import pandas as pd

from analytics.greedy_v2_splits import chronological_split


class GreedyV2SplitTests(unittest.TestCase):

    def setUp(self):
        dates = pd.bdate_range("2025-01-01", periods=100)
        self.prices = pd.DataFrame(
            {
                "AAA": np.linspace(100, 150, 100),
                "BBB": np.linspace(200, 240, 100),
                "CCC": np.linspace(80, 110, 100),
            },
            index=dates,
        )

    def test_chronological_split_sizes(self):
        result = chronological_split(self.prices)

        self.assertEqual(len(result.train), 60)
        self.assertEqual(len(result.validation), 21)
        self.assertEqual(len(result.test), 21)

    def test_splits_are_chronological(self):
        result = chronological_split(self.prices)

        self.assertLess(result.train.index[-1], result.validation.index[1])
        self.assertLess(
            result.validation.index[-1],
            result.test.index[1],
        )

    def test_validation_includes_previous_price_baseline(self):
        result = chronological_split(self.prices)

        self.assertEqual(
            result.validation.index[0],
            result.train.index[-1],
        )

    def test_test_includes_previous_price_baseline(self):
        result = chronological_split(self.prices)

        self.assertEqual(
            result.test.index[0],
            result.validation.index[-1],
        )

    def test_no_data_is_lost_between_periods(self):
        result = chronological_split(self.prices)

        self.assertEqual(
            result.train.index[-1],
            result.validation.index[0],
        )
        self.assertEqual(
            result.validation.index[-1],
            result.test.index[0],
        )

    def test_metadata_discloses_split_details(self):
        result = chronological_split(self.prices)

        self.assertEqual(result.metadata["method"], "CHRONOLOGICAL")
        self.assertFalse(result.metadata["shuffled"])
        self.assertFalse(result.metadata["missing_prices_filled"])
        self.assertTrue(result.metadata["baseline_prices_included"])

    def test_unsorted_dates_are_rejected(self):
        prices = self.prices.iloc[::-1]

        with self.assertRaises(ValueError):
            chronological_split(prices)

    def test_duplicate_dates_are_rejected(self):
        prices = pd.concat([self.prices, self.prices.iloc[[0]]])

        with self.assertRaises(ValueError):
            chronological_split(prices)

    def test_missing_prices_are_rejected(self):
        prices = self.prices.copy()
        prices.iloc[10, 0] = np.nan

        with self.assertRaises(ValueError):
            chronological_split(prices)

    def test_non_positive_prices_are_rejected(self):
        prices = self.prices.copy()
        prices.iloc[10, 0] = 0

        with self.assertRaises(ValueError):
            chronological_split(prices)

    def test_insufficient_history_is_rejected(self):
        with self.assertRaises(ValueError):
            chronological_split(self.prices.iloc[:50])

    def test_invalid_split_fractions_are_rejected(self):
        with self.assertRaises(ValueError):
            chronological_split(self.prices, train_fraction=0)

        with self.assertRaises(ValueError):
            chronological_split(self.prices, validation_fraction=1)

        with self.assertRaises(ValueError):
            chronological_split(
                self.prices,
                train_fraction=0.8,
                validation_fraction=0.3,
            )


if __name__ == "__main__":
    unittest.main()
