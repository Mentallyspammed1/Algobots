# Mock the config module before importing mm
import sys
import unittest
from unittest.mock import MagicMock

import numpy as np

sys.modules['config'] = MagicMock()
import config
from mm import MarketMaker


class TestMarketMakerCalculations(unittest.TestCase):

    def setUp(self):
        # Set up mock config values for tests
        config.QTY_PRECISION = 6
        config.NUM_ORDERS = 5
        config.MAX_SPREAD_MULTIPLIER = 3.0
        config.BASE_SPREAD = 0.001

        self.market_maker = MarketMaker()

    def test_scale_qtys(self):
        # Test case 1: Basic scaling
        x = 100.0
        n = 5
        scaling_factor = 1.0
        expected_qtys = [33.333333, 26.666667, 20.0, 13.333333, 6.666667, -6.666667, -13.333333, -20.0, -26.666667, -33.333333]
        result = self.market_maker.scale_qtys(x, n, scaling_factor)
        self.assertAlmostEqual(sum(result), sum(expected_qtys), places=5)
        for i in range(len(result)):
            self.assertAlmostEqual(result[i], expected_qtys[i], places=5)

        # Test case 2: Different scaling factor
        x = 100.0
        n = 5
        scaling_factor = 0.5
        expected_qtys_scaled = [16.666667, 13.333333, 10.0, 6.666667, 3.333333, -3.333333, -6.666667, -10.0, -13.333333, -16.666667]
        result_scaled = self.market_maker.scale_qtys(x, n, scaling_factor)
        self.assertAlmostEqual(sum(result_scaled), sum(expected_qtys_scaled), places=5)
        for i in range(len(result_scaled)):
            self.assertAlmostEqual(result_scaled[i], expected_qtys_scaled[i], places=5)

    def test_calculate_volatility(self):
        # Test case 1: Not enough prices
        self.market_maker.last_prices = [100.0, 101.0]
        self.assertEqual(self.market_maker.calculate_volatility(period=5), 0.0)

        # Test case 2: Sufficient prices, no volatility
        self.market_maker.last_prices = [100.0] * 20
        self.assertAlmostEqual(self.market_maker.calculate_volatility(period=10), 0.0, places=5)

        # Test case 3: Some volatility
        self.market_maker.last_prices = [100, 101, 100, 102, 101, 103, 102, 104, 103, 105, 104, 106, 105, 107, 106, 108, 107, 109, 108, 110]
        volatility = self.market_maker.calculate_volatility(period=20)
        self.assertGreater(volatility, 0.0)
        self.assertLess(volatility, 1.0) # Volatility should be a reasonable percentage

    def test_calculate_adaptive_spread(self):
        # Test case 1: No volatility history
        self.market_maker.volatility_history = []
        self.assertAlmostEqual(self.market_maker.calculate_adaptive_spread(0.001, 0.05), 0.001, places=5)

        # Test case 2: Volatility below average
        self.market_maker.volatility_history = [0.05, 0.06, 0.07]
        avg_vol = np.mean(self.market_maker.volatility_history)
        current_vol = 0.04
        expected_spread = config.BASE_SPREAD * (1 + (current_vol / (avg_vol + 1e-6) - 1) * 0.5)
        self.assertAlmostEqual(self.market_maker.calculate_adaptive_spread(config.BASE_SPREAD, current_vol), expected_spread, places=5)

        # Test case 3: Volatility above average
        self.market_maker.volatility_history = [0.01, 0.02, 0.03]
        avg_vol = np.mean(self.market_maker.volatility_history)
        current_vol = 0.05
        expected_spread = config.BASE_SPREAD * (1 + (current_vol / (avg_vol + 1e-6) - 1) * 0.5)
        self.assertAlmostEqual(self.market_maker.calculate_adaptive_spread(config.BASE_SPREAD, current_vol), expected_spread, places=5)

        # Test case 4: Volatility hits max multiplier
        self.market_maker.volatility_history = [0.001]
        current_vol = 1.0 # Very high volatility
        expected_spread = config.BASE_SPREAD * config.MAX_SPREAD_MULTIPLIER
        self.assertAlmostEqual(self.market_maker.calculate_adaptive_spread(config.BASE_SPREAD, current_vol), expected_spread, places=5)

if __name__ == '__main__':
    unittest.main()
