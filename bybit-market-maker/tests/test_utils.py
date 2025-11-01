import unittest

from bybit_market_maker.utils import calculate_order_sizes
from bybit_market_maker.utils import calculate_spread
from bybit_market_maker.utils import calculate_volatility
from bybit_market_maker.utils import format_price
from bybit_market_maker.utils import format_quantity


class TestUtils(unittest.TestCase):
    def test_calculate_volatility(self):
        prices = [100, 102, 101, 103, 102]
        volatility = calculate_volatility(prices, window=4)
        self.assertIsInstance(volatility, float)
        self.assertGreater(volatility, 0)

        # Test with not enough data
        prices = [100, 102]
        volatility = calculate_volatility(prices, window=4)
        self.assertIsNone(volatility)

    def test_calculate_spread(self):
        config = {
            "trading": {
                "volatility_factor": 1.5,
                "inventory_factor": 2.0,
                "min_spread": 0.0005,
                "max_spread": 0.005,
            }
        }
        bid_spread, ask_spread = calculate_spread(0.001, 0.01, 0.5, config)
        self.assertIsInstance(bid_spread, float)
        self.assertIsInstance(ask_spread, float)
        self.assertGreater(bid_spread, 0)
        self.assertGreater(ask_spread, 0)

    def test_calculate_order_sizes(self):
        sizes = calculate_order_sizes(100, 5, 0.5, "Buy")
        self.assertEqual(len(sizes), 5)
        self.assertIsInstance(sizes[0], float)
        self.assertGreater(sizes[0], 0)

    def test_format_price(self):
        price = 123.456
        formatted_price = format_price(price, tick_size=0.01)
        self.assertEqual(formatted_price, 123.46)

    def test_format_quantity(self):
        quantity = 1.23456
        formatted_quantity = format_quantity(quantity, lot_size=0.001)
        self.assertEqual(formatted_quantity, 1.235)


if __name__ == "__main__":
    unittest.main()
