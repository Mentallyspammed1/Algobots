import json
import os
import unittest
from decimal import Decimal
from unittest.mock import MagicMock
from unittest.mock import patch

import numpy as np
import pandas as pd

# Import the functions and classes from the script to be tested
# Assuming the script is named tt.py
import tt


class TestConfigLoading(unittest.TestCase):
    """Tests for the load_config function."""

    def setUp(self):
        self.test_config_file = "test_config.json"
        # Clean up any old test files before running a test
        if os.path.exists(self.test_config_file):
            os.remove(self.test_config_file)

    def tearDown(self):
        # Clean up test files after each test
        if os.path.exists(self.test_config_file):
            os.remove(self.test_config_file)
        backup_files = [
            f for f in os.listdir(".") if f.startswith(f"{self.test_config_file}.bak")
        ]
        for f in backup_files:
            os.remove(f)

    def test_load_default_config_on_file_not_found(self):
        """Test that a default config is created if the file doesn't exist."""
        config = tt.load_config(self.test_config_file)
        self.assertTrue(os.path.exists(self.test_config_file))
        self.assertEqual(config["interval"], "15")
        self.assertIn("ehlers_fisher_transform", config["indicators"])

    def test_merge_with_default_config(self):
        """Test that a partial user config is correctly merged with the default."""
        user_config = {
            "interval": "60",
            "analysis_interval": 15,
            "indicators": {"rsi": False, "ehlers_fisher_transform": True},
        }
        with open(self.test_config_file, "w") as f:
            json.dump(user_config, f)

        config = tt.load_config(self.test_config_file)

        # Test that user values override defaults
        self.assertEqual(config["interval"], "60")
        self.assertEqual(config["analysis_interval"], 15)

        # Test that default values are preserved
        self.assertEqual(config["momentum_period"], 10)

        # Test that nested dictionaries are merged
        self.assertFalse(config["indicators"]["rsi"])
        self.assertTrue(config["indicators"]["ehlers_fisher_transform"])
        self.assertTrue(
            config["indicators"]["macd"]
        )  # A default that wasn't in user config

    def test_handle_invalid_json(self):
        """Test handling of a corrupt JSON config file."""
        with open(self.test_config_file, "w") as f:
            f.write("{'invalid_json': True,}")  # Invalid JSON

        # Suppress error logging during this test
        with patch("tt.logger.error"), patch("tt.logger.info"):
            config = tt.load_config(self.test_config_file)

        # Should load default config and back up the corrupt one
        self.assertEqual(config["interval"], "15")
        self.assertTrue(any(".bak_" in f for f in os.listdir(".")))


class TestTradingAnalyzer(unittest.TestCase):
    """Tests for the TradingAnalyzer class and its indicator calculations."""

    def setUp(self):
        """Set up a sample DataFrame and config for testing."""
        # Create a sample DataFrame with predictable data
        data = {
            "start_time": pd.to_datetime(pd.date_range(start="2023-01-01", periods=50)),
            "open": np.linspace(100, 150, 50),
            "high": np.linspace(102, 155, 50)
            + np.sin(np.linspace(0, 3 * np.pi, 50)) * 2,
            "low": np.linspace(98, 145, 50) - np.sin(np.linspace(0, 3 * np.pi, 50)) * 2,
            "close": pd.Series(np.linspace(101, 148, 50)),
            "volume": np.linspace(1000, 2000, 50),
        }
        self.df = pd.DataFrame(data)

        # Create a mock logger
        self.mock_logger = MagicMock()

        # Use the default config from the script for consistency
        self.config = tt.load_config("default_config_for_test.json")
        if os.path.exists("default_config_for_test.json"):
            os.remove("default_config_for_test.json")

        self.analyzer = tt.TradingAnalyzer(
            self.df, self.config, self.mock_logger, "BTCUSDT", "15"
        )

    def test_calculate_rsi(self):
        """Test the RSI calculation."""
        rsi_series = self.analyzer._calculate_rsi(window=14)
        self.assertIsInstance(rsi_series, pd.Series)
        self.assertEqual(len(rsi_series), len(self.df))
        # In a consistent uptrend, RSI should be high
        self.assertTrue(rsi_series.iloc[-1] > 70)

    def test_calculate_macd(self):
        """Test the MACD calculation."""
        macd_df = self.analyzer._calculate_macd()
        self.assertIsInstance(macd_df, pd.DataFrame)
        self.assertIn("macd", macd_df.columns)
        self.assertIn("signal", macd_df.columns)
        self.assertIn("histogram", macd_df.columns)
        # In a steady uptrend, MACD line should be above the signal line
        self.assertTrue(macd_df["macd"].iloc[-1] > macd_df["signal"].iloc[-1])

    def test_calculate_ehlers_fisher_transform(self):
        """Test the Ehlers Fisher Transform calculation."""
        fisher_df = self.analyzer._calculate_ehlers_fisher_transform(period=10)
        self.assertIsInstance(fisher_df, pd.DataFrame)
        self.assertIn("fisher", fisher_df.columns)
        self.assertIn("signal", fisher_df.columns)
        # With a strong uptrend, the Fisher value should be positive and high
        self.assertTrue(fisher_df["fisher"].iloc[-1] > 1.0)

    def test_calculate_laguerre_rsi(self):
        """Test the Laguerre RSI calculation."""
        laguerre_series = self.analyzer._calculate_laguerre_rsi(gamma=0.5)
        self.assertIsInstance(laguerre_series, pd.Series)
        # Values should be between 0 and 1
        self.assertTrue(all(0 <= x <= 1 for x in laguerre_series))
        # In a strong uptrend, it should be in the overbought area
        self.assertTrue(
            laguerre_series.iloc[-1] > self.config["laguerre_rsi_overbought"]
        )

    def test_generate_buy_signal(self):
        """Test that a buy signal is generated under specific conditions."""
        # Create a scenario for a buy signal (e.g., oversold RSI and Stoch RSI crossover)
        close_prices = [
            150,
            140,
            130,
            120,
            110,
            100,
            90,
            85,
            80,
            75,
            70,
            72,
            75,
            78,
            82,
        ]
        num_repeats = len(self.df) // len(close_prices) + 1
        buy_data = self.df.copy()
        buy_data["close"] = pd.Series(close_prices * num_repeats).head(len(self.df))

        buy_analyzer = tt.TradingAnalyzer(
            buy_data, self.config, self.mock_logger, "BTCUSDT", "15"
        )

        buy_analyzer._calculate_all_indicators()

        # Force Stoch RSI to be in an oversold crossover state for a clear signal
        stoch_rsi_vals = buy_analyzer.indicator_values["stoch_rsi_vals"]
        stoch_rsi_vals.iloc[-1, stoch_rsi_vals.columns.get_loc("k")] = 15
        stoch_rsi_vals.iloc[-1, stoch_rsi_vals.columns.get_loc("d")] = 10
        buy_analyzer.indicator_values["stoch_rsi_vals"] = stoch_rsi_vals

        signal, score, conditions, _ = buy_analyzer.generate_trading_signal(
            Decimal("82.0")
        )

        self.assertEqual(signal, "buy")
        self.assertGreater(score, self.config["signal_score_threshold"])
        self.assertIn("Stoch RSI Oversold Crossover", conditions)

    def test_generate_sell_signal(self):
        """Test that a sell signal is generated under specific conditions."""
        # Create a scenario for a sell signal (e.g., overbought RSI)
        sell_data = self.df.copy()
        sell_data["close"] = pd.Series(
            np.linspace(100, 200, 50)
        )  # Strong uptrend to create overbought
        sell_analyzer = tt.TradingAnalyzer(
            sell_data, self.config, self.mock_logger, "BTCUSDT", "15"
        )

        sell_analyzer._calculate_all_indicators()

        # Force Stoch RSI to be in an overbought crossover state
        stoch_rsi_vals = sell_analyzer.indicator_values["stoch_rsi_vals"]
        stoch_rsi_vals.iloc[-1, stoch_rsi_vals.columns.get_loc("k")] = 85
        stoch_rsi_vals.iloc[-1, stoch_rsi_vals.columns.get_loc("d")] = 90
        sell_analyzer.indicator_values["stoch_rsi_vals"] = stoch_rsi_vals

        signal, score, conditions, _ = sell_analyzer.generate_trading_signal(
            Decimal("200.0")
        )

        self.assertEqual(signal, "sell")
        self.assertGreater(score, self.config["signal_score_threshold"])
        self.assertIn("Stoch RSI Overbought Crossover", conditions)

    def test_no_signal(self):
        """Test that no signal is generated in a sideways market."""
        # Sideways market data
        sideways_data = self.df.copy()
        sideways_data["close"] = pd.Series(
            100 + np.sin(np.linspace(0, 5 * np.pi, 50)) * 2
        )
        sideways_analyzer = tt.TradingAnalyzer(
            sideways_data, self.config, self.mock_logger, "BTCUSDT", "15"
        )

        sideways_analyzer._calculate_all_indicators()
        signal, score, _, _ = sideways_analyzer.generate_trading_signal(
            Decimal("100.0")
        )

        self.assertIsNone(signal)
        self.assertLess(score, self.config["signal_score_threshold"])


if __name__ == "__main__":
    unittest.main(argv=["first-arg-is-ignored"], exit=False)
