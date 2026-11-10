
import unittest

import numpy as np
import pandas as pd

from analytics.greedy_v2_engine import greedy_select_stocks


class GreedyV2EngineTests(unittest.TestCase):

    def setUp(self):
        dates = pd.bdate_range("2025-01-01", periods=100)

        rng = np.random.default_rng(42)

        symbols = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]

        daily_drifts = {
            "AAA": 0.0008,
            "BBB": 0.0005,
            "CCC": 0.0003,
            "DDD": 0.0001,
            "EEE": 0.0004,
            "FFF": 0.0006,
        }

        price_data = {}

        for symbol in symbols:
            returns = rng.normal(
                loc=daily_drifts[symbol],
                scale=0.008,
                size=len(dates),
            )

            price_data[symbol] = (
                100 * np.cumprod(1 + returns)
            )

        self.prices = pd.DataFrame(
            price_data,
            index=dates,
        )

        self.sectors = {
            "AAA": "IT",
            "BBB": "IT",
            "CCC": "IT",
            "DDD": "BANKING",
            "EEE": "BANKING",
            "FFF": "PHARMA",
        }

    def test_selects_requested_number_of_stocks(self):
        result = greedy_select_stocks(
            self.prices,
            self.sectors,
            target_stocks=3,
        )

        self.assertEqual(len(result["selected_symbols"]), 3)

    def test_sector_limit_is_respected(self):
        result = greedy_select_stocks(
            self.prices,
            self.sectors,
            target_stocks=4,
            max_per_sector=2,
        )

        selected = result["selected_symbols"]

        for sector in set(self.sectors.values()):
            count = sum(
                self.sectors[symbol] == sector
                for symbol in selected
            )
            self.assertLessEqual(count, 2)

    def test_selected_symbols_are_unique(self):
        result = greedy_select_stocks(
            self.prices,
            self.sectors,
            target_stocks=4,
        )

        selected = result["selected_symbols"]

        self.assertEqual(len(selected), len(set(selected)))

    def test_selection_log_has_one_row_per_step(self):
        result = greedy_select_stocks(
            self.prices,
            self.sectors,
            target_stocks=4,
        )

        self.assertEqual(len(result["selection_log"]), 4)

    def test_selection_log_steps_are_sequential(self):
        result = greedy_select_stocks(
            self.prices,
            self.sectors,
            target_stocks=4,
        )

        self.assertEqual(
            result["selection_log"]["step"].tolist(),
            [1, 2, 3, 4],
        )

    def test_equal_weighting_is_disclosed(self):
        result = greedy_select_stocks(
            self.prices,
            self.sectors,
            target_stocks=3,
        )

        self.assertEqual(
            result["assumptions"]["weighting"],
            "EQUAL_WEIGHT",
        )

    def test_training_only_selection_is_disclosed(self):
        result = greedy_select_stocks(
            self.prices,
            self.sectors,
            target_stocks=3,
        )

        self.assertTrue(
            result["assumptions"]["selection_uses_training_data_only"]
        )

    def test_missing_prices_are_rejected(self):
        prices = self.prices.copy()
        prices.iloc[5, 0] = np.nan

        with self.assertRaises(ValueError):
            greedy_select_stocks(
                prices,
                self.sectors,
                target_stocks=3,
            )

    def test_non_positive_prices_are_rejected(self):
        prices = self.prices.copy()
        prices.iloc[5, 0] = 0

        with self.assertRaises(ValueError):
            greedy_select_stocks(
                prices,
                self.sectors,
                target_stocks=3,
            )

    def test_duplicate_dates_are_rejected(self):
        prices = self.prices.copy()
        prices.index = list(prices.index[:-1]) + [prices.index[-2]]

        with self.assertRaises(ValueError):
            greedy_select_stocks(
                prices,
                self.sectors,
                target_stocks=3,
            )

    def test_insufficient_history_is_rejected(self):
        prices = self.prices.iloc[:30]

        with self.assertRaises(ValueError):
            greedy_select_stocks(
                prices,
                self.sectors,
                target_stocks=3,
            )

    def test_missing_sector_is_rejected(self):
        sectors = self.sectors.copy()
        del sectors["AAA"]

        with self.assertRaises(ValueError):
            greedy_select_stocks(
                self.prices,
                sectors,
                target_stocks=3,
            )

    def test_impossible_sector_constraint_is_rejected(self):
        with self.assertRaises(ValueError):
            greedy_select_stocks(
                self.prices,
                self.sectors,
                target_stocks=5,
                max_per_sector=1,
            )

    def test_invalid_target_is_rejected(self):
        with self.assertRaises(ValueError):
            greedy_select_stocks(
                self.prices,
                self.sectors,
                target_stocks=0,
            )

    def test_risk_free_rate_is_validated(self):
        with self.assertRaises(ValueError):
            greedy_select_stocks(
                self.prices,
                self.sectors,
                target_stocks=3,
                risk_free_rate=-0.01,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
