import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pandas as pd

from config import Config
from market_maker import MarketMaker


class TestMarketMaker(unittest.TestCase):
    def setUp(self):
        """Set up a new MarketMaker instance for each test."""
        self.config = Config()
        self.market_maker = MarketMaker()
        self.market_maker.session = None  # Disable live trading

    def test_calculate_volatility(self):
        """Test the volatility calculation."""
        self.market_maker.price_history = pd.Series(range(100, 120))
        self.config.VOLATILITY_WINDOW = 20
        volatility = self.market_maker.calculate_volatility()
        self.assertGreater(volatility, 0)

    def test_calculate_spread(self):
        """Test the spread calculation."""
        self.market_maker.current_volatility = 1.5
        self.market_maker.position = 0.05
        self.config.MAX_POSITION = 0.1
        spread = self.market_maker.calculate_spread()
        self.assertGreater(spread, self.config.BASE_SPREAD)

    def test_calculate_order_prices(self):
        """Test the order price calculation."""
        self.market_maker.mid_price = 20000
        self.market_maker.current_volatility = 1.0
        self.market_maker.position = 0
        bid_prices, ask_prices = self.market_maker.calculate_order_prices()
        self.assertEqual(len(bid_prices), self.config.ORDER_LEVELS)
        self.assertEqual(len(ask_prices), self.config.ORDER_LEVELS)
        self.assertLess(bid_prices[0], self.market_maker.mid_price)
        self.assertGreater(ask_prices[0], self.market_maker.mid_price)

    def test_calculate_order_sizes(self):
        """Test the order size calculation with inventory skew."""
        self.market_maker.position = 0.05
        self.config.MAX_POSITION = 0.1
        buy_sizes, sell_sizes = self.market_maker.calculate_order_sizes()
        self.assertLess(buy_sizes[0], sell_sizes[0])


if __name__ == "__main__":
    unittest.main()
