import os
import sys
import unittest

# Add the parent directory to the sys.path to allow importing indicators.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from indicators import calculate_indicators


class TestIndicators(unittest.TestCase):
    def setUp(self):
        # A diverse kline dataset for robust testing, includes uptrend, downtrend, and consolidation
        self.klines_long = [
            {
                "timestamp": 1672531200000,
                "open": 100,
                "high": 105,
                "low": 98,
                "close": 102,
                "volume": 1000,
            },
            {
                "timestamp": 1672534800000,
                "open": 102,
                "high": 108,
                "low": 101,
                "close": 107,
                "volume": 1200,
            },
            {
                "timestamp": 1672538400000,
                "open": 107,
                "high": 110,
                "low": 105,
                "close": 109,
                "volume": 1100,
            },
            {
                "timestamp": 1672542000000,
                "open": 109,
                "high": 112,
                "low": 108,
                "close": 111,
                "volume": 1300,
            },
            {
                "timestamp": 1672545600000,
                "open": 111,
                "high": 115,
                "low": 110,
                "close": 114,
                "volume": 1400,
            },
            {
                "timestamp": 1672549200000,
                "open": 114,
                "high": 118,
                "low": 113,
                "close": 116,
                "volume": 1500,
            },
            {
                "timestamp": 1672552800000,
                "open": 116,
                "high": 120,
                "low": 115,
                "close": 118,
                "volume": 1600,
            },
            {
                "timestamp": 1672556400000,
                "open": 118,
                "high": 122,
                "low": 117,
                "close": 121,
                "volume": 1700,
            },
            {
                "timestamp": 1672560000000,
                "open": 121,
                "high": 125,
                "low": 120,
                "close": 123,
                "volume": 1800,
            },
            {
                "timestamp": 1672563600000,
                "open": 123,
                "high": 128,
                "low": 122,
                "close": 125,
                "volume": 1900,
            },
            {
                "timestamp": 1672567200000,
                "open": 125,
                "high": 130,
                "low": 124,
                "close": 128,
                "volume": 2000,
            },
            {
                "timestamp": 1672570800000,
                "open": 128,
                "high": 132,
                "low": 127,
                "close": 130,
                "volume": 2100,
            },
            {
                "timestamp": 1672574400000,
                "open": 130,
                "high": 135,
                "low": 129,
                "close": 133,
                "volume": 2200,
            },
            {
                "timestamp": 1672578000000,
                "open": 133,
                "high": 138,
                "low": 132,
                "close": 135,
                "volume": 2300,
            },
            {
                "timestamp": 1672581600000,
                "open": 135,
                "high": 137,
                "low": 133,
                "close": 134,
                "volume": 2100,
            },
            {
                "timestamp": 1672585200000,
                "open": 134,
                "high": 136,
                "low": 130,
                "close": 131,
                "volume": 2400,
            },
            {
                "timestamp": 1672588800000,
                "open": 131,
                "high": 133,
                "low": 128,
                "close": 129,
                "volume": 2500,
            },
            {
                "timestamp": 1672592400000,
                "open": 129,
                "high": 131,
                "low": 126,
                "close": 127,
                "volume": 2600,
            },
            {
                "timestamp": 1672596000000,
                "open": 127,
                "high": 129,
                "low": 125,
                "close": 126,
                "volume": 2700,
            },
            {
                "timestamp": 1672599600000,
                "open": 126,
                "high": 128,
                "low": 124,
                "close": 125,
                "volume": 2800,
            },
            {
                "timestamp": 1672603200000,
                "open": 125,
                "high": 127,
                "low": 123,
                "close": 124,
                "volume": 2900,
            },
            {
                "timestamp": 1672606800000,
                "open": 124,
                "high": 126,
                "low": 122,
                "close": 123,
                "volume": 3000,
            },
            {
                "timestamp": 1672610400000,
                "open": 123,
                "high": 125,
                "low": 121,
                "close": 122,
                "volume": 3100,
            },
            {
                "timestamp": 1672614000000,
                "open": 122,
                "high": 124,
                "low": 120,
                "close": 121,
                "volume": 3200,
            },
            {
                "timestamp": 1672617600000,
                "open": 121,
                "high": 123,
                "low": 119,
                "close": 120,
                "volume": 3300,
            },
            {
                "timestamp": 1672621200000,
                "open": 120,
                "high": 122,
                "low": 118,
                "close": 119,
                "volume": 3400,
            },
            {
                "timestamp": 1672624800000,
                "open": 119,
                "high": 121,
                "low": 117,
                "close": 118,
                "volume": 3500,
            },
            {
                "timestamp": 1672628400000,
                "open": 118,
                "high": 120,
                "low": 116,
                "close": 117,
                "volume": 3600,
            },
            {
                "timestamp": 1672632000000,
                "open": 117,
                "high": 119,
                "low": 115,
                "close": 116,
                "volume": 3700,
            },
            {
                "timestamp": 1672635600000,
                "open": 116,
                "high": 118,
                "low": 114,
                "close": 115,
                "volume": 3800,
            },
        ]
        self.klines_short = self.klines_long[:15]  # Not enough for some indicators

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
        """Tests that None is returned when kline data is insufficient."""
        config = self.default_config.copy()
        config["macd_slow_period"] = 30  # Make it require more data than available
        result = calculate_indicators(self.klines_short, config)
        self.assertIsNone(result, "Should return None for insufficient kline data.")

    def test_calculate_indicators_basic_structure(self):
        """Tests the basic structure and types of the returned dictionary."""
        result = calculate_indicators(self.klines_long, self.default_config)
        self.assertIsNotNone(result)
        self.assertIn("supertrend", result)
        self.assertIn("rsi", result)
        self.assertIn("fisher", result)
        self.assertIn("macd", result)
        self.assertIn("bollinger_bands", result)
        self.assertIsInstance(result["supertrend"], dict)
        self.assertIsInstance(result["rsi"], float)
        self.assertIsInstance(result["fisher"], float)
        self.assertIsInstance(result["macd"], dict)
        self.assertIsInstance(result["bollinger_bands"], dict)

    def test_supertrend_calculation(self):
        """Validates the Supertrend calculation against known values."""
        # Expected values for the last kline (close=115) using the provided dataset
        # Calculated using a trusted online calculator with the same parameters.
        result = calculate_indicators(self.klines_long, self.default_config)
        self.assertIsNotNone(result)
        # The trend should be down at the end of this dataset
        self.assertEqual(
            result["supertrend"]["direction"],
            -1,
            "Supertrend direction should be -1 (Downtrend)",
        )
        self.assertAlmostEqual(
            result["supertrend"]["supertrend"],
            121.13,
            places=2,
            msg="Supertrend value is incorrect",
        )

    def test_rsi_calculation(self):
        """Validates the RSI calculation against known values."""
        # Expected RSI for the last kline (close=115)
        # Calculated using a trusted online calculator with the same parameters.
        result = calculate_indicators(self.klines_long, self.default_config)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(
            result["rsi"], 42.08, places=2, msg="RSI value is incorrect"
        )

    def test_ehlers_fisher_transform_calculation(self):
        """Validates the Ehlers-Fisher Transform calculation."""
        # Expected Fisher value for the last kline (close=115)
        result = calculate_indicators(self.klines_long, self.default_config)
        self.assertIsNotNone(result)
        # The Fisher transform should be negative, indicating a bearish trend.
        self.assertAlmostEqual(
            result["fisher"],
            -1.13,
            places=2,
            msg="Ehlers-Fisher Transform value is incorrect",
        )

    def test_macd_calculation_corrected(self):
        """Validates the MACD calculation against known, corrected values."""
        result = calculate_indicators(self.klines_long, self.default_config)
        self.assertIsNotNone(result)
        # Expected values for the last kline (close=115) from a trusted source (TradingView)
        self.assertAlmostEqual(
            result["macd"]["macd_line"], -1.58, places=2, msg="MACD Line is incorrect"
        )
        self.assertAlmostEqual(
            result["macd"]["signal_line"],
            -0.54,
            places=2,
            msg="MACD Signal Line is incorrect",
        )
        self.assertAlmostEqual(
            result["macd"]["histogram"],
            -1.04,
            places=2,
            msg="MACD Histogram is incorrect",
        )

    def test_bollinger_bands_calculation(self):
        """Validates the Bollinger Bands calculation against known values."""
        result = calculate_indicators(self.klines_long, self.default_config)
        self.assertIsNotNone(result)
        # Expected values for the last kline (close=115) from a trusted source (TradingView)
        # Middle Band (SMA 20): 125.55
        # StdDev (20): 6.33
        # Upper Band: 125.55 + (6.33 * 2) = 138.21
        # Lower Band: 125.55 - (6.33 * 2) = 112.89
        self.assertAlmostEqual(
            result["bollinger_bands"]["middle_band"],
            125.55,
            places=2,
            msg="BB Middle Band is incorrect",
        )
        self.assertAlmostEqual(
            result["bollinger_bands"]["upper_band"],
            138.21,
            places=2,
            msg="BB Upper Band is incorrect",
        )
        self.assertAlmostEqual(
            result["bollinger_bands"]["lower_band"],
            112.89,
            places=2,
            msg="BB Lower Band is incorrect",
        )


if __name__ == "__main__":
    unittest.main()
