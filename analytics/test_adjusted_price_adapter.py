
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from analytics.adjusted_price_adapter import (
    get_company_actions,
    get_adjusted_company_prices,
)


def make_mock_connection(rows):
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.all.return_value = rows

    context_manager = MagicMock()
    context_manager.__enter__.return_value = connection

    return context_manager, connection


class AdjustedPriceAdapterTests(unittest.TestCase):

    @patch("analytics.adjusted_price_adapter.engine.connect")
    def test_get_company_actions_returns_database_rows(self, mock_connect):
        rows = [
            {
                "action_type": "BONUS",
                "ex_date": pd.Timestamp("2025-05-23"),
                "ratio": "2:1",
                "source_name": "NSE",
                "source_reference": "TEST-REFERENCE",
            }
        ]

        context, connection = make_mock_connection(rows)
        mock_connect.return_value = context

        result = get_company_actions(11)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["action_type"], "BONUS")
        self.assertEqual(result[0]["ratio"], "2:1")

        params = connection.execute.call_args.args[1]
        self.assertEqual(params["company_id"], 11)
        self.assertIsNone(params["end_date"])

    @patch("analytics.adjusted_price_adapter.engine.connect")
    def test_company_actions_respect_end_date(self, mock_connect):
        context, connection = make_mock_connection([])
        mock_connect.return_value = context

        get_company_actions(
            company_id=11,
            end_date="2025-06-30",
        )

        query_text = str(connection.execute.call_args.args[0])
        params = connection.execute.call_args.args[1]

        self.assertIn("ex_date <= :end_date", query_text)
        self.assertEqual(params["end_date"], "2025-06-30")

    @patch("analytics.adjusted_price_adapter.get_company_actions")
    @patch("analytics.adjusted_price_adapter.engine.connect")
    def test_start_date_filter_happens_after_adjustment(
        self,
        mock_connect,
        mock_actions,
    ):
        rows = [
            {"trade_date": "2025-05-22", "close_price": 300.0},
            {"trade_date": "2025-05-23", "close_price": 150.0},
            {"trade_date": "2025-05-26", "close_price": 155.0},
        ]

        context, connection = make_mock_connection(rows)
        mock_connect.return_value = context

        mock_actions.return_value = [
            {
                "action_type": "BONUS",
                "ratio": "1:1",
                "ex_date": "2025-05-26",
            }
        ]

        result = get_adjusted_company_prices(
            company_id=11,
            start_date="2025-05-23",
            end_date="2025-05-30",
        )

        self.assertEqual(len(result), 2)

        # The 1:1 bonus adjusts the earlier price by a factor of 2.
        self.assertEqual(result.iloc[0]["adjustment_factor"], 2.0)
        self.assertAlmostEqual(result.iloc[0]["adjusted_close"], 75.0)

        # The ex-date price is not adjusted.
        self.assertEqual(result.iloc[1]["adjustment_factor"], 1.0)
        self.assertAlmostEqual(result.iloc[1]["adjusted_close"], 155.0)

        # The action history is requested with the same end-date cutoff.
        mock_actions.assert_called_once_with(
            company_id=11,
            end_date="2025-05-30",
        )

        # The raw price query also receives the end-date cutoff.
        params = connection.execute.call_args.args[1]
        self.assertEqual(params["end_date"], "2025-05-30")

    @patch("analytics.adjusted_price_adapter.get_company_actions")
    @patch("analytics.adjusted_price_adapter.engine.connect")
    def test_raw_prices_are_preserved(
        self,
        mock_connect,
        mock_actions,
    ):
        rows = [
            {"trade_date": "2025-05-22", "close_price": 300.0},
            {"trade_date": "2025-05-23", "close_price": 150.0},
        ]

        context, _ = make_mock_connection(rows)
        mock_connect.return_value = context

        mock_actions.return_value = [
            {
                "action_type": "BONUS",
                "ratio": "1:1",
                "ex_date": "2025-05-23",
            }
        ]

        result = get_adjusted_company_prices(11)

        self.assertEqual(result["close"].tolist(), [300.0, 150.0])
        self.assertEqual(result["adjusted_close"].tolist(), [150.0, 150.0])

    @patch("analytics.adjusted_price_adapter.get_company_actions")
    @patch("analytics.adjusted_price_adapter.engine.connect")
    def test_no_actions_leave_prices_unchanged(
        self,
        mock_connect,
        mock_actions,
    ):
        rows = [
            {"trade_date": "2025-05-22", "close_price": 100.0},
            {"trade_date": "2025-05-23", "close_price": 110.0},
        ]

        context, _ = make_mock_connection(rows)
        mock_connect.return_value = context
        mock_actions.return_value = []

        result = get_adjusted_company_prices(11)

        self.assertEqual(result["adjustment_factor"].tolist(), [1.0, 1.0])
        self.assertEqual(result["adjusted_close"].tolist(), [100.0, 110.0])

    @patch("analytics.adjusted_price_adapter.engine.connect")
    def test_empty_company_history_returns_empty_dataframe(self, mock_connect):
        context, _ = make_mock_connection([])
        mock_connect.return_value = context

        result = get_adjusted_company_prices(999999)

        self.assertTrue(result.empty)
        self.assertIn("adjusted_close", result.columns)
        self.assertEqual(result.attrs["price_basis"], "SPLIT_BONUS_ADJUSTED")
        self.assertFalse(result.attrs["dividend_adjusted"])

    @patch("analytics.adjusted_price_adapter.get_company_actions")
    @patch("analytics.adjusted_price_adapter.engine.connect")
    def test_metadata_discloses_price_basis(
        self,
        mock_connect,
        mock_actions,
    ):
        rows = [
            {"trade_date": "2025-05-22", "close_price": 100.0},
        ]

        context, _ = make_mock_connection(rows)
        mock_connect.return_value = context
        mock_actions.return_value = []

        result = get_adjusted_company_prices(11)

        self.assertEqual(result.attrs["company_id"], 11)
        self.assertEqual(result.attrs["price_basis"], "SPLIT_BONUS_ADJUSTED")
        self.assertFalse(result.attrs["dividend_adjusted"])
        self.assertEqual(result.attrs["corporate_action_coverage"], "PARTIAL")

    @patch("analytics.adjusted_price_adapter.engine.connect")
    def test_price_query_has_end_date_filter(self, mock_connect):
        rows = [
            {"trade_date": "2025-05-22", "close_price": 100.0},
        ]

        context, connection = make_mock_connection(rows)
        mock_connect.return_value = context

        with patch(
            "analytics.adjusted_price_adapter.get_company_actions",
            return_value=[],
        ):
            get_adjusted_company_prices(
                company_id=11,
                end_date="2025-05-22",
            )

        query_text = str(connection.execute.call_args.args[0])
        params = connection.execute.call_args.args[1]

        self.assertIn("trade_date <= :end_date", query_text)
        self.assertEqual(params["end_date"], "2025-05-22")


if __name__ == "__main__":
    unittest.main(verbosity=2)
