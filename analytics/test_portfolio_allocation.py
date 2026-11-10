import unittest
from analytics.portfolio_allocation import allocate_capital


class PortfolioAllocationTests(unittest.TestCase):
    def test_equal_budget_whole_share_allocation(self):
        result = allocate_capital(
            ["AAA", "BBB"], {"AAA": 100, "BBB": 200}, 10000
        )
        self.assertEqual([x["quantity"] for x in result["holdings"]], [50, 25])
        self.assertEqual(result["invested"], 10000)
        self.assertEqual(result["cash_remaining"], 0)

    def test_leftover_cash_is_preserved(self):
        result = allocate_capital(
            ["AAA", "BBB"], {"AAA": 300, "BBB": 700}, 2000
        )
        self.assertLessEqual(result["invested"], 2000)
        self.assertGreaterEqual(result["cash_remaining"], 0)

    def test_rejects_insufficient_capital(self):
        with self.assertRaises(ValueError):
            allocate_capital(["AAA", "BBB"], {"AAA": 100, "BBB": 200}, 250)

    def test_rejects_more_than_ten_stocks(self):
        symbols = [f"S{i}" for i in range(11)]
        prices = {s: 1 for s in symbols}
        with self.assertRaises(ValueError):
            allocate_capital(symbols, prices, 100)


if __name__ == "__main__":
    unittest.main()
