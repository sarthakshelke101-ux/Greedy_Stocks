import unittest
from copy import deepcopy
from decimal import Decimal

import pandas as pd

from analytics.adjusted_prices import (
    action_adjustment_factor,
    build_adjusted_prices,
)


class AdjustedPriceTests(unittest.TestCase):

    def test_split_factor(self):
        self.assertEqual(
            action_adjustment_factor({
                "action_type": "STOCK_SPLIT",
                "ratio": "5:1",
                "ex_date": "2026-01-14",
            }),
            Decimal("5"),
        )

    def test_bonus_factor(self):
        self.assertEqual(
            action_adjustment_factor({
                "action_type": "BONUS",
                "ratio": "4:1",
                "ex_date": "2025-06-16",
            }),
            Decimal("5"),
        )

    def test_fractional_bonus_factor(self):
        self.assertEqual(
            action_adjustment_factor({
                "action_type": "BONUS",
                "ratio": "1:2",
                "ex_date": "2026-06-04",
            }),
            Decimal("1.5"),
        )

    def test_pre_event_price_is_adjusted(self):
        prices = pd.DataFrame({
            "trade_date": ["2025-05-22", "2025-05-23"],
            "close": [300.0, 110.0],
        })
        result = build_adjusted_prices(prices, [{
            "action_type": "BONUS", "ratio": "2:1", "ex_date": "2025-05-23"
        }])
        self.assertAlmostEqual(result.iloc[0]["adjusted_close"], 100)
        self.assertAlmostEqual(result.iloc[1]["adjusted_close"], 110)

    def test_same_day_bajaj_actions_combine(self):
        prices = pd.DataFrame({
            "trade_date": ["2025-06-13", "2025-06-16"],
            "close": [9331.0, 938.0],
        })
        actions = [
            {"action_type": "STOCK_SPLIT", "ratio": "2:1", "ex_date": "2025-06-16"},
            {"action_type": "BONUS", "ratio": "4:1", "ex_date": "2025-06-16"},
        ]
        result = build_adjusted_prices(prices, actions)
        self.assertAlmostEqual(result.iloc[0]["adjustment_factor"], 10)
        self.assertAlmostEqual(result.iloc[0]["adjusted_close"], 933.1)
        self.assertAlmostEqual(result.iloc[1]["adjusted_close"], 938.0)

    def test_multiple_events_compound(self):
        prices = pd.DataFrame({
            "trade_date": ["2025-01-01", "2025-06-16", "2026-01-14"],
            "close": [1000.0, 110.0, 25.0],
        })
        actions = [
            {"action_type": "BONUS", "ratio": "1:1", "ex_date": "2025-06-16"},
            {"action_type": "STOCK_SPLIT", "ratio": "5:1", "ex_date": "2026-01-14"},
        ]
        result = build_adjusted_prices(prices, actions)
        self.assertAlmostEqual(result.iloc[0]["adjustment_factor"], 10)
        self.assertAlmostEqual(result.iloc[0]["adjusted_close"], 100)
        self.assertAlmostEqual(result.iloc[1]["adjusted_close"], 22)
        self.assertAlmostEqual(result.iloc[2]["adjusted_close"], 25)

    def test_raw_prices_are_preserved(self):
        prices = pd.DataFrame({
            "trade_date": ["2025-05-22", "2025-05-23"],
            "close": [300.0, 110.0],
        })
        original = prices.copy(deep=True)
        result = build_adjusted_prices(prices, [{
            "action_type": "BONUS", "ratio": "2:1", "ex_date": "2025-05-23"
        }])
        pd.testing.assert_frame_equal(prices, original)
        self.assertEqual(result["close"].tolist(), [300.0, 110.0])

    def test_missing_price_is_not_filled(self):
        prices = pd.DataFrame({
            "trade_date": ["2025-05-21", "2025-05-22", "2025-05-23"],
            "close": [300.0, None, 110.0],
        })
        result = build_adjusted_prices(prices, [{
            "action_type": "BONUS", "ratio": "2:1", "ex_date": "2025-05-23"
        }])
        self.assertTrue(pd.isna(result.iloc[1]["adjusted_close"]))
        self.assertAlmostEqual(result.iloc[0]["adjusted_close"], 100)

    def test_unsupported_action_fails(self):
        with self.assertRaises(ValueError):
            action_adjustment_factor({
                "action_type": "DIVIDEND", "ratio": "1:1", "ex_date": "2025-05-23"
            })

    def test_invalid_ratios_fail(self):
        for ratio in ["0:1", "-1:2", "1:0", "abc", "1:2:3", "NaN:1", "Infinity:1", "1:Infinity"]:
            with self.subTest(ratio=ratio):
                with self.assertRaises(ValueError):
                    action_adjustment_factor({"action_type": "STOCK_SPLIT", "ratio": ratio})

    def test_missing_action_fields_fail(self):
        for action in [
            {},
            {"action_type": "BONUS"},
            {"ratio": "2:1"},
            {"action_type": "BONUS", "ratio": None},
        ]:
            with self.subTest(action=action):
                with self.assertRaises(ValueError):
                    action_adjustment_factor(action)

    def test_invalid_ex_dates_fail(self):
        prices = pd.DataFrame({"trade_date": ["2025-05-22"], "close": [100.0]})
        for ex_date in ["", "not-a-date", "NaT", None, float("nan")]:
            with self.subTest(ex_date=ex_date):
                with self.assertRaises(ValueError):
                    build_adjusted_prices(prices, [{
                        "action_type": "BONUS", "ratio": "1:1", "ex_date": ex_date
                    }])

    def test_invalid_price_values_fail(self):
        for value in ["not-a-price", float("inf"), float("-inf"), 0, -10]:
            with self.subTest(value=value):
                prices = pd.DataFrame({"trade_date": ["2025-05-22"], "close": [value]})
                with self.assertRaises(ValueError):
                    build_adjusted_prices(prices, [])

    def test_missing_price_is_allowed_but_not_filled(self):
        prices = pd.DataFrame({
            "trade_date": ["2025-05-22", "2025-05-23"],
            "close": [None, 110.0],
        })
        result = build_adjusted_prices(prices, [])
        self.assertTrue(pd.isna(result.loc[0, "adjusted_close"]))
        self.assertEqual(result.loc[1, "adjusted_close"], 110.0)

    def test_duplicate_dates_fail(self):
        prices = pd.DataFrame({
            "trade_date": ["2025-05-22", "2025-05-22"],
            "close": [100.0, 101.0],
        })
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_adjusted_prices(prices, [])

    def test_unsorted_dates_return_sorted_output(self):
        prices = pd.DataFrame({
            "trade_date": ["2025-05-23", "2025-05-21", "2025-05-22"],
            "close": [103.0, 101.0, 102.0],
        })
        result = build_adjusted_prices(prices, [])
        self.assertEqual(
            result["trade_date"].dt.strftime("%Y-%m-%d").tolist(),
            ["2025-05-21", "2025-05-22", "2025-05-23"],
        )

    def test_no_actions_leave_prices_unchanged(self):
        prices = pd.DataFrame({
            "trade_date": ["2025-05-22", "2025-05-23"],
            "close": [100.0, 110.0],
        })
        result = build_adjusted_prices(prices, [])
        self.assertEqual(result["adjustment_factor"].tolist(), [1.0, 1.0])
        self.assertEqual(result["adjusted_close"].tolist(), [100.0, 110.0])

    def test_duplicate_dataframe_index_labels_are_safe(self):
        prices = pd.DataFrame(
            {"trade_date": ["2025-05-22", "2025-05-23"], "close": [200.0, 110.0]},
            index=[7, 7],
        )
        result = build_adjusted_prices(prices, [{
            "action_type": "BONUS", "ratio": "1:1", "ex_date": "2025-05-23"
        }])
        self.assertAlmostEqual(result.iloc[0]["adjusted_close"], 100)
        self.assertAlmostEqual(result.iloc[1]["adjusted_close"], 110)

    def test_input_actions_are_not_mutated(self):
        prices = pd.DataFrame({"trade_date": ["2025-05-22"], "close": [200.0]})
        actions = [{"action_type": "BONUS", "ratio": "1:1", "ex_date": "2025-05-23"}]
        original_actions = deepcopy(actions)
        build_adjusted_prices(prices, actions)
        self.assertEqual(actions, original_actions)

    def test_metadata_discloses_price_basis(self):
        prices = pd.DataFrame({"trade_date": ["2025-05-22"], "close": [100.0]})
        result = build_adjusted_prices(prices, [])
        self.assertEqual(result.attrs["price_basis"], "SPLIT_BONUS_ADJUSTED")
        self.assertEqual(result.attrs["raw_price_basis"], "RAW_CLOSE_UNADJUSTED")
        self.assertFalse(result.attrs["total_return"])

    def test_missing_or_invalid_price_dates_fail(self):
        for date in [None, "NaT", "not-a-date"]:
            with self.subTest(date=date):
                prices = pd.DataFrame({"trade_date": [date], "close": [100.0]})
                with self.assertRaises(ValueError):
                    build_adjusted_prices(prices, [])

    def test_non_mapping_action_fails(self):
        prices = pd.DataFrame({"trade_date": ["2025-05-22"], "close": [100.0]})
        with self.assertRaises(ValueError):
            build_adjusted_prices(prices, ["not-an-action"])

    def test_action_with_timezone_fails(self):
        prices = pd.DataFrame({"trade_date": ["2025-05-22"], "close": [100.0]})
        with self.assertRaises(ValueError):
            build_adjusted_prices(prices, [{
                "action_type": "BONUS",
                "ratio": "1:1",
                "ex_date": "2025-05-23T00:00:00+05:30",
            }])


if __name__ == "__main__":
    unittest.main(verbosity=2)
