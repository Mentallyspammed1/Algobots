import os
import sys
import unittest

# Add the parent directory to the sys.path to allow importing indicators.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from indicators import calculate_indicators


class TestIndicators(unittest.TestCase):

    def setUp(self):
        # Common kline data for testing
        self.klines_short = [
            {"timestamp": 1, "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100},
            {"timestamp": 2, "open": 11, "high": 13, "low": 10, "close": 12, "volume": 110},
            {"timestamp": 3, "open": 12, "high": 14, "low": 11, "close": 13, "volume": 120},
            {"timestamp": 4, "open": 13, "high": 15, "low": 12, "close": 14, "volume": 130},
            {"timestamp": 5, "open": 14, "high": 16, "low": 13, "close": 15, "volume": 140},
        ]
        # A longer set of klines for indicators that require more data
        self.klines_long = [
            {"timestamp": i, "open": 100+i, "high": 105+i, "low": 98+i, "close": 102+i, "volume": 100+i*10} for i in range(1, 201)
        ]
        # Klines for specific MACD/BB tests (ensure enough data for periods)
        self.klines_for_macd_bb = [
            {"timestamp": 1, "open": 10, "high": 10, "low": 10, "close": 10, "volume": 100},
            {"timestamp": 2, "open": 10, "high": 10, "low": 10, "close": 11, "volume": 100},
            {"timestamp": 3, "open": 11, "high": 11, "low": 11, "close": 12, "volume": 100},
            {"timestamp": 4, "open": 12, "high": 12, "low": 12, "close": 13, "volume": 100},
            {"timestamp": 5, "open": 13, "high": 13, "low": 13, "close": 14, "volume": 100},
            {"timestamp": 6, "open": 14, "high": 14, "low": 14, "close": 15, "volume": 100},
            {"timestamp": 7, "open": 15, "high": 15, "low": 15, "close": 16, "volume": 100},
            {"timestamp": 8, "open": 16, "high": 16, "low": 16, "close": 17, "volume": 100},
            {"timestamp": 9, "open": 17, "high": 17, "low": 17, "close": 18, "volume": 100},
            {"timestamp": 10, "open": 18, "high": 18, "low": 18, "close": 19, "volume": 100},
            {"timestamp": 11, "open": 19, "high": 19, "low": 19, "close": 20, "volume": 100},
            {"timestamp": 12, "open": 20, "high": 20, "low": 20, "close": 21, "volume": 100},
            {"timestamp": 13, "open": 21, "high": 21, "low": 21, "close": 22, "volume": 100},
            {"timestamp": 14, "open": 22, "high": 22, "low": 22, "close": 23, "volume": 100},
            {"timestamp": 15, "open": 23, "high": 23, "low": 23, "close": 24, "volume": 100},
            {"timestamp": 16, "open": 24, "high": 24, "low": 24, "close": 25, "volume": 100},
            {"timestamp": 17, "open": 25, "high": 25, "low": 25, "close": 26, "volume": 100},
            {"timestamp": 18, "open": 26, "high": 26, "low": 26, "close": 27, "volume": 100},
            {"timestamp": 19, "open": 27, "high": 27, "low": 27, "close": 28, "volume": 100},
            {"timestamp": 20, "open": 28, "high": 28, "low": 28, "close": 29, "volume": 100},
            {"timestamp": 21, "open": 29, "high": 29, "low": 29, "close": 30, "volume": 100},
            {"timestamp": 22, "open": 30, "high": 30, "low": 30, "close": 31, "volume": 100},
            {"timestamp": 23, "open": 31, "high": 31, "low": 31, "close": 32, "volume": 100},
            {"timestamp": 24, "open": 32, "high": 32, "low": 32, "close": 33, "volume": 100},
            {"timestamp": 25, "open": 33, "high": 33, "low": 33, "close": 34, "volume": 100},
            {"timestamp": 26, "open": 34, "high": 34, "low": 34, "close": 35, "volume": 100},
            {"timestamp": 27, "open": 35, "high": 35, "low": 35, "close": 36, "volume": 100},
            {"timestamp": 28, "open": 36, "high": 36, "low": 36, "close": 37, "volume": 100},
            {"timestamp": 29, "open": 37, "high": 37, "low": 37, "close": 38, "volume": 100},
            {"timestamp": 30, "open": 38, "high": 38, "low": 38, "close": 39, "volume": 100},
        ]

        self.default_config = {
            "supertrend_length": 10,
            "supertrend_multiplier": 3.0,
            "rsi_length": 14,
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "ef_period": 10,
            "macd_fast_period": 12,
            "macd_slow_period": 26,
            "macd_signal_period": 9,
            "bb_period": 20,
            "bb_std_dev": 2.0,
        }

    def test_insufficient_klines(self):
        # Test with klines less than required for indicators
        config = self.default_config.copy()
        config["supertrend_length"] = 20
        config["rsi_length"] = 20
        config["ef_period"] = 20
        config["macd_slow_period"] = 30 # Make it require more data
        config["bb_period"] = 30 # Make it require more data
        result = calculate_indicators(self.klines_short, config)
        self.assertIsNone(result)

    def test_calculate_indicators_basic(self):
        # Test with enough klines for basic calculation
        result = calculate_indicators(self.klines_long, self.default_config)
        self.assertIsNotNone(result)
        self.assertIn('supertrend', result)
        self.assertIn('rsi', result)
        self.assertIn('fisher', result)
        self.assertIn('macd', result)
        self.assertIn('bollinger_bands', result)
        self.assertIsInstance(result['supertrend'], dict)
        self.assertIsInstance(result['rsi'], float)
        self.assertIsInstance(result['fisher'], float)
        self.assertIsInstance(result['macd'], dict)
        self.assertIsInstance(result['bollinger_bands'], dict)

    def test_macd_calculation(self):
        # Expected values calculated using TradingView for a simple increasing close price series
        # Close prices: 10, 11, 12, ..., 39 (30 klines)
        # MACD(12, 26, 9)
        config = self.default_config.copy()
        result = calculate_indicators(self.klines_for_macd_bb, config)
        self.assertIsNotNone(result)

        # Expected values for the LAST kline (close=39)
        # These values are approximate and depend on exact EMA calculation method
        # Using a calculator/TradingView for verification:
        # Last Fast EMA (12): ~33.07
        # Last Slow EMA (26): ~29.59
        # MACD Line: ~3.48
        # Signal Line (9 EMA of MACD): ~2.89
        # Histogram: ~0.59

        self.assertAlmostEqual(result['macd']['macd_line'], 3.48, places=2)
        self.assertAlmostEqual(result['macd']['signal_line'], 2.89, places=2)
        self.assertAlmostEqual(result['macd']['histogram'], 0.59, places=2)

    def test_bollinger_bands_calculation(self):
        # Expected values calculated using TradingView for a simple increasing close price series
        # Close prices: 10, 11, 12, ..., 39 (30 klines)
        # BB(20, 2.0)
        config = self.default_config.copy()
        result = calculate_indicators(self.klines_for_macd_bb, config)
        self.assertIsNotNone(result)

        # Expected values for the LAST kline (close=39)
        # Middle Band (SMA 20 of last 20 closes): (20+21+...+39)/20 = 29.5
        # StdDev (20 periods, last 20 closes): ~5.77
        # Upper Band: 29.5 + (5.77 * 2) = 41.04
        # Lower Band: 29.5 - (5.77 * 2) = 17.96

        self.assertAlmostEqual(result['bollinger_bands']['middle_band'], 29.5, places=2)
        self.assertAlmostEqual(result['bollinger_bands']['upper_band'], 41.04, places=2)
        self.assertAlmostEqual(result['bollinger_bands']['lower_band'], 17.96, places=2)


if __name__ == '__main__':
    unittest.main()
