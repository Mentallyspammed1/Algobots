import os
import sys
import unittest

# Add the parent directory to the sys.path to allow importing indicators.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from indicators import calculate_indicators


class TestIndicators(unittest.TestCase):
    def setUp(self):
        # Common kline data for testing
        self.klines_short = [
            {
                "timestamp": 1,
                "open": 10,
                "high": 12,
                "low": 9,
                "close": 11,
                "volume": 100,
            },
            {
                "timestamp": 2,
                "open": 11,
                "high": 13,
                "low": 10,
                "close": 12,
                "volume": 110,
            },
            {
                "timestamp": 3,
                "open": 12,
                "high": 14,
                "low": 11,
                "close": 13,
                "volume": 120,
            },
            {"timestamp": 4, "open": 13, "low": 12, "close": 14, "volume": 130},
            {
                "timestamp": 5,
                "open": 14,
                "high": 16,
                "low": 13,
                "close": 15,
                "volume": 140,
            },
        ]
        self.klines_long = [
            {
                "timestamp": i,
                "open": 100 + i,
                "high": 105 + i,
                "low": 98 + i,
                "close": 102 + i,
                "volume": 100 + i * 10,
            }
            for i in range(1, 201)
        ]
        self.default_config = {
            "supertrend_length": 10,
            "supertrend_multiplier": 3.0,
            "rsi_length": 14,
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "ef_period": 10,
        }

    def test_insufficient_klines(self):
        # Test with klines less than required for indicators
        config = self.default_config.copy()
        config["supertrend_length"] = 20
        config["rsi_length"] = 20
        config["ef_period"] = 20
        result = calculate_indicators(self.klines_short, config)
        self.assertIsNone(result)

    def test_calculate_indicators_basic(self):
        # Test with enough klines for basic calculation
        result = calculate_indicators(self.klines_long, self.default_config)
        self.assertIsNotNone(result)
        self.assertIn("supertrend", result)
        self.assertIn("rsi", result)
        self.assertIn("fisher", result)
        self.assertIsInstance(result["supertrend"], dict)
        self.assertIsInstance(result["rsi"], float)
        self.assertIsInstance(result["fisher"], float)

    # TODO: Add more specific tests for Supertrend, RSI, Fisher values
    # These would require known inputs and expected outputs, possibly from a tradingview or other calculator.


if __name__ == "__main__":
    unittest.main()
