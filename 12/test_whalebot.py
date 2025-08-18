import unittest
import pandas as pd
import numpy as np
import os
import json
from unittest.mock import patch, MagicMock
from decimal import Decimal, getcontext

# Set Decimal precision for financial calculations
getcontext().prec = 10

# Import functions and classes from whalebot.py
# We need to adjust the import path if whalebot.py is not directly importable
# For now, assume it's in the same directory or adjust sys.path
from whalebot import load_config, TradingAnalyzer, interpret_indicator, CONFIG_FILE, LOG_DIRECTORY, setup_custom_logger

# Mock the logger to prevent actual log file creation during tests
# and to capture log messages for assertions
class MockLogger:
    def __init__(self):
        self.info_messages = []
        self.warning_messages = []
        self.error_messages = []
        self.exception_messages = []

    def info(self, message):
        self.info_messages.append(message)

    def warning(self, message):
        self.warning_messages.append(message)

    def error(self, message):
        self.error_messages.append(message)

    def exception(self, message):
        self.exception_messages.append(message)

# Patch setup_custom_logger to return our mock logger
patch('whalebot.setup_custom_logger', return_value=MockLogger()).start()

class TestWhalebot(unittest.TestCase):

    def setUp(self):
        # Clean up any existing config.json before each test
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
        
        # Create a dummy DataFrame for testing TradingAnalyzer
        self.sample_df = pd.DataFrame({
            'start_time': pd.to_datetime(pd.Series(range(100, 200)), unit='ms'),
            'open': np.random.rand(100) * 100 + 1000,
            'high': np.random.rand(100) * 100 + 1050,
            'low': np.random.rand(100) * 100 + 950,
            'close': np.random.rand(100) * 100 + 1000,
            'volume': np.random.rand(100) * 10000
        })
        # Ensure close is always between low and high for realistic data
        self.sample_df['close'] = self.sample_df.apply(lambda row: np.clip(row['close'], row['low'], row['high']), axis=1)
        self.sample_df['open'] = self.sample_df.apply(lambda row: np.clip(row['open'], row['low'], row['high']), axis=1)

        # Basic config for tests
        self.test_config = {
            "interval": "5",
            "analysis_interval": 30,
            "atr_period": 14,
            "ema_short_period": 12,
            "ema_long_period": 26,
            "momentum_period": 10,
            "momentum_ma_short": 12,
            "momentum_ma_long": 26,
            "volume_ma_period": 20,
            "stoch_rsi_oversold_threshold": 20,
            "stoch_rsi_overbought_threshold": 80,
            "signal_score_threshold": 1.0,
            "stop_loss_multiple": 1.5,
            "take_profit_multiple": 1.0,
            "atr_change_threshold": 0.005,
            "volume_confirmation_multiplier": 1.5,
            "indicator_periods": {
                "rsi": 14, "mfi": 14, "cci": 20, "williams_r": 14, "adx": 14,
                "stoch_rsi_period": 14, "stoch_rsi_k_period": 3, "stoch_rsi_d_period": 3,
                "momentum": 10, "momentum_ma_short": 12, "momentum_ma_long": 26,
                "volume_ma": 20, "atr": 14, "sma_10": 10,
                "fve_price_ema": 10, "fve_obv_sma": 20, "fve_atr_sma": 20,
                "stoch_osc_k": 14, "stoch_osc_d": 3,
            },
            "indicators": {
                "ema_alignment": True, "momentum": True, "volume_confirmation": True,
                "divergence": True, "stoch_rsi": True, "rsi": True, "macd": True,
                "vwap": False, "obv": True, "adi": True, "cci": True, "wr": True,
                "adx": True, "psar": True, "fve": True, "sma_10": False, "mfi": True,
                "stochastic_oscillator": True,
            },
            "weight_sets": {
                "low_volatility": {"stoch_rsi": 0.5, "stochastic_oscillator": 0.4, "ema_alignment": 0.3, "rsi": 0.3, "mfi": 0.3, "momentum": 0.2, "volume_confirmation": 0.2, "divergence": 0.1, "obv": 0.1, "adi": 0.1, "cci": 0.1, "wr": 0.1, "adx": 0.1, "psar": 0.1, "fve": 0.2, "macd": 0.3, "vwap": 0.0, "sma_10": 0.0},
                "high_volatility": {"stoch_rsi": 0.4, "stochastic_oscillator": 0.3, "ema_alignment": 0.1, "rsi": 0.4, "mfi": 0.4, "momentum": 0.4, "volume_confirmation": 0.1, "divergence": 0.2, "obv": 0.1, "adi": 0.1, "cci": 0.1, "wr": 0.1, "adx": 0.1, "psar": 0.1, "fve": 0.3, "macd": 0.4, "vwap": 0.0, "sma_10": 0.0},
            },
            "order_book_analysis": {
                "enabled": True,
                "wall_threshold_multiplier": 2.0,
                "depth_to_check": 10,
                "support_boost": 3,
                "resistance_boost": 3,
            }
        }
        self.mock_logger = MockLogger()
        self.analyzer = TradingAnalyzer(self.sample_df, self.test_config, self.mock_logger, "TESTUSDT", "5")

    def tearDown(self):
        # Clean up any created config.json after tests
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
        # Reset mock logger messages
        self.mock_logger.info_messages = []
        self.mock_logger.warning_messages = []
        self.mock_logger.error_messages = []
        self.mock_logger.exception_messages = []

    def test_load_config_default(self):
        # Test loading default config when file does not exist
        config = load_config(CONFIG_FILE)
        self.assertIn("interval", config)
        self.assertEqual(config["interval"], "15")
        self.assertTrue(os.path.exists(CONFIG_FILE))

    def test_load_config_existing(self):
        # Test loading existing config
        custom_config = {"interval": "60", "new_setting": "test"}
        with open(CONFIG_FILE, "w") as f:
            json.dump(custom_config, f)
        
        config = load_config(CONFIG_FILE)
        self.assertEqual(config["interval"], "60")
        self.assertEqual(config["new_setting"], "test")
        self.assertIn("analysis_interval", config) # Should merge with defaults

    def test_load_config_invalid_json(self):
        # Test handling of invalid JSON
        with open(CONFIG_FILE, "w") as f:
            f.write("{invalid json")
        
        config = load_config(CONFIG_FILE)
        self.assertIn("interval", config) # Should load defaults
        self.assertIn("Invalid JSON in config file", self.mock_logger.error_messages[0])
        self.assertTrue(os.path.exists(CONFIG_FILE)) # Should recreate valid config

    def test_calculate_atr(self):
        # ATR requires at least 'atr_period' data points
        if len(self.sample_df) > self.test_config["atr_period"]:
            atr_series = self.analyzer._calculate_atr(window=self.test_config["atr_period"])
            self.assertIsInstance(atr_series, pd.Series)
            self.assertFalse(atr_series.empty)
            self.assertFalse(atr_series.isnull().all())
            self.assertGreaterEqual(len(atr_series), self.test_config["atr_period"])
        else:
            self.skipTest("Sample DataFrame too small for ATR calculation")

    def test_calculate_rsi(self):
        if len(self.sample_df) > self.test_config["indicator_periods"]["rsi"]:
            rsi_series = self.analyzer._calculate_rsi(window=self.test_config["indicator_periods"]["rsi"])
            self.assertIsInstance(rsi_series, pd.Series)
            self.assertFalse(rsi_series.empty)
            self.assertFalse(rsi_series.isnull().all())
            self.assertTrue(all(0 <= val <= 100 for val in rsi_series.dropna()))
        else:
            self.skipTest("Sample DataFrame too small for RSI calculation")

    def test_calculate_stoch_rsi(self):
        if len(self.sample_df) > max(self.test_config["indicator_periods"]["stoch_rsi_period"], self.test_config["indicator_periods"]["stoch_rsi_k_period"], self.test_config["indicator_periods"]["stoch_rsi_d_period"]):
            stoch_rsi_df = self.analyzer._calculate_stoch_rsi(
                rsi_window=self.test_config["indicator_periods"]["stoch_rsi_period"],
                stoch_window=self.test_config["indicator_periods"]["stoch_rsi_period"], # Stoch window is usually same as RSI period
                k_window=self.test_config["indicator_periods"]["stoch_rsi_k_period"],
                d_window=self.test_config["indicator_periods"]["stoch_rsi_d_period"]
            )
            self.assertIsInstance(stoch_rsi_df, pd.DataFrame)
            self.assertFalse(stoch_rsi_df.empty)
            self.assertIn('k', stoch_rsi_df.columns)
            self.assertIn('d', stoch_rsi_df.columns)
            self.assertTrue(all(0 <= val <= 100 for val in stoch_rsi_df['k'].dropna()))
            self.assertTrue(all(0 <= val <= 100 for val in stoch_rsi_df['d'].dropna()))
        else:
            self.skipTest("Sample DataFrame too small for Stoch RSI calculation")

    def test_calculate_stochastic_oscillator(self):
        if len(self.sample_df) > max(self.test_config["indicator_periods"]["stoch_osc_k"], self.test_config["indicator_periods"]["stoch_osc_d"]):
            stoch_osc_df = self.analyzer._calculate_stochastic_oscillator()
            self.assertIsInstance(stoch_osc_df, pd.DataFrame)
            self.assertFalse(stoch_osc_df.empty)
            self.assertIn('k', stoch_osc_df.columns)
            self.assertIn('d', stoch_osc_df.columns)
            self.assertTrue(all(0 <= val <= 100 for val in stoch_osc_df['k'].dropna()))
            self.assertTrue(all(0 <= val <= 100 for val in stoch_osc_df['d'].dropna()))
        else:
            self.skipTest("Sample DataFrame too small for Stochastic Oscillator calculation")

    def test_select_weight_set(self):
        # Test high volatility
        self.analyzer.atr_value = 0.1 # Higher than atr_change_threshold (0.005)
        weights = self.analyzer._select_weight_set()
        self.assertEqual(weights, self.test_config["weight_sets"]["high_volatility"])
        self.assertIn("HIGH VOLATILITY", self.mock_logger.info_messages[-1])

        # Test low volatility
        self.mock_logger.info_messages = [] # Clear previous messages
        self.analyzer.atr_value = 0.001 # Lower than atr_change_threshold
        weights = self.analyzer._select_weight_set()
        self.assertEqual(weights, self.test_config["weight_sets"]["low_volatility"])
        self.assertIn("LOW VOLATILITY", self.mock_logger.info_messages[-1])

    @patch('whalebot.TradingAnalyzer._calculate_stoch_rsi')
    @patch('whalebot.TradingAnalyzer._calculate_rsi')
    @patch('whalebot.TradingAnalyzer._calculate_mfi')
    @patch('whalebot.TradingAnalyzer._calculate_ema_alignment')
    @patch('whalebot.TradingAnalyzer._calculate_volume_confirmation')
    @patch('whalebot.TradingAnalyzer.detect_macd_divergence')
    @patch('whalebot.TradingAnalyzer._calculate_stochastic_oscillator')
    @patch('whalebot.TradingAnalyzer.analyze_order_book_walls')
    def test_generate_trading_signal_bullish(self, mock_analyze_order_book_walls, mock_calculate_stochastic_oscillator, mock_detect_macd_divergence, mock_calculate_volume_confirmation, mock_calculate_ema_alignment, mock_calculate_mfi, mock_calculate_rsi, mock_calculate_stoch_rsi):
        # Mock indicator values for a bullish signal
        mock_calculate_stoch_rsi.return_value = pd.DataFrame({'stoch_rsi': [10.0], 'k': [15.0], 'd': [10.0]}) # Oversold, K > D
        mock_calculate_rsi.return_value = pd.Series([25.0]) # Oversold
        mock_calculate_mfi.return_value = pd.Series([15.0]) # Oversold
        mock_calculate_ema_alignment.return_value = 1.0 # Bullish alignment
        mock_calculate_volume_confirmation.return_value = True
        mock_detect_macd_divergence.return_value = "bullish"
        mock_calculate_stochastic_oscillator.return_value = pd.DataFrame({'k': [15.0], 'd': [10.0]}) # Oversold, K > D
        mock_analyze_order_book_walls.return_value = (True, False, {"Bid@1000": Decimal('100')}, {}) # Bullish wall

        # Ensure ATR is set for SL/TP calculation
        self.analyzer.atr_value = 10.0
        self.analyzer.indicator_values["stoch_rsi_vals"] = mock_calculate_stoch_rsi.return_value
        self.analyzer.indicator_values["rsi"] = mock_calculate_rsi.return_value
        self.analyzer.indicator_values["mfi"] = mock_calculate_mfi.return_value
        self.analyzer.indicator_values["ema_alignment"] = mock_calculate_ema_alignment.return_value
        self.analyzer.indicator_values["order_book_walls"] = (True, False, {}, {})
        self.analyzer.indicator_values["stoch_osc_vals"] = mock_calculate_stochastic_oscillator.return_value

        signal, confidence, conditions_met, trade_levels = self.analyzer.generate_trading_signal(Decimal('1000.0'))

        self.assertEqual(signal, "buy")
        self.assertGreater(confidence, 0.0)
        self.assertIn("Stoch RSI Oversold Crossover", conditions_met)
        self.assertIn("RSI Oversold", conditions_met)
        self.assertIn("MFI Oversold", conditions_met)
        self.assertIn("Bullish EMA Alignment", conditions_met)
        self.assertIn("Volume Confirmation", conditions_met)
        self.assertIn("Bullish MACD Divergence", conditions_met)
        self.assertIn("Stoch Oscillator Oversold Crossover", conditions_met)
        self.assertIn("Bullish Order Book Wall", conditions_met)
        self.assertIn("stop_loss", trade_levels)
        self.assertIn("take_profit", trade_levels)

    @patch('whalebot.TradingAnalyzer._calculate_stoch_rsi')
    @patch('whalebot.TradingAnalyzer._calculate_rsi')
    @patch('whalebot.TradingAnalyzer._calculate_mfi')
    @patch('whalebot.TradingAnalyzer._calculate_ema_alignment')
    @patch('whalebot.TradingAnalyzer.detect_macd_divergence')
    @patch('whalebot.TradingAnalyzer._calculate_stochastic_oscillator')
    @patch('whalebot.TradingAnalyzer.analyze_order_book_walls')
    def test_generate_trading_signal_bearish(self, mock_analyze_order_book_walls, mock_calculate_stochastic_oscillator, mock_detect_macd_divergence, mock_calculate_ema_alignment, mock_calculate_mfi, mock_calculate_rsi, mock_calculate_stoch_rsi):
        # Mock indicator values for a bearish signal
        mock_calculate_stoch_rsi.return_value = pd.DataFrame({'stoch_rsi': [90.0], 'k': [85.0], 'd': [90.0]}) # Overbought, K < D
        mock_calculate_rsi.return_value = pd.Series([75.0]) # Overbought
        mock_calculate_mfi.return_value = pd.Series([85.0]) # Overbought
        mock_calculate_ema_alignment.return_value = -1.0 # Bearish alignment
        mock_detect_macd_divergence.return_value = "bearish"
        mock_calculate_stochastic_oscillator.return_value = pd.DataFrame({'k': [85.0], 'd': [90.0]}) # Overbought, K < D
        mock_analyze_order_book_walls.return_value = (False, True, {}, {"Ask@1000": Decimal('100')}) # Bearish wall

        # Ensure ATR is set for SL/TP calculation
        self.analyzer.atr_value = 10.0
        self.analyzer.indicator_values["stoch_rsi_vals"] = mock_calculate_stoch_rsi.return_value
        self.analyzer.indicator_values["rsi"] = mock_calculate_rsi.return_value
        self.analyzer.indicator_values["mfi"] = mock_calculate_mfi.return_value
        self.analyzer.indicator_values["ema_alignment"] = mock_calculate_ema_alignment.return_value
        self.analyzer.indicator_values["order_book_walls"] = (False, True, {}, {})
        self.analyzer.indicator_values["stoch_osc_vals"] = mock_calculate_stochastic_oscillator.return_value

        signal, confidence, conditions_met, trade_levels = self.analyzer.generate_trading_signal(Decimal('1000.0'))

        self.assertEqual(signal, "sell")
        self.assertGreater(confidence, 0.0)
        self.assertIn("Stoch RSI Overbought Crossover", conditions_met)
        self.assertIn("RSI Overbought", conditions_met)
        self.assertIn("MFI Overbought", conditions_met)
        self.assertIn("Bearish EMA Alignment", conditions_met)
        self.assertIn("Bearish MACD Divergence", conditions_met)
        self.assertIn("Stoch Oscillator Overbought Crossover", conditions_met)
        self.assertIn("Bearish Order Book Wall", conditions_met)
        self.assertIn("stop_loss", trade_levels)
        self.assertIn("take_profit", trade_levels)

    def test_interpret_indicator(self):
        mock_logger = MockLogger()
        
        # Test RSI
        self.assertEqual(interpret_indicator(mock_logger, "rsi", 75.0), f"{Fore.RED}RSI:{Style.RESET_ALL} Overbought (75.00)")
        self.assertEqual(interpret_indicator(mock_logger, "rsi", 25.0), f"{Fore.GREEN}RSI:{Style.RESET_ALL} Oversold (25.00)")
        self.assertEqual(interpret_indicator(mock_logger, "rsi", 50.0), f"{Fore.YELLOW}RSI:{Style.RESET_ALL} Neutral (50.00)")

        # Test OBV
        self.assertEqual(interpret_indicator(mock_logger, "obv", [100.0, 110.0]), f"{Fore.BLUE}OBV:{Style.RESET_ALL} Bullish")
        self.assertEqual(interpret_indicator(mock_logger, "obv", [110.0, 100.0]), f"{Fore.BLUE}OBV:{Style.RESET_ALL} Bearish")
        self.assertEqual(interpret_indicator(mock_logger, "obv", [100.0, 100.0]), f"{Fore.BLUE}OBV:{Style.RESET_ALL} Neutral")

        # Test mom (momentum)
        mom_data = {"trend": "Uptrend", "strength": 0.75}
        self.assertEqual(interpret_indicator(mock_logger, "mom", mom_data), f"{Fore.MAGENTA}Momentum Trend:{Style.RESET_ALL} Uptrend (Strength: 0.75)")

        # Test unknown indicator
        self.assertEqual(interpret_indicator(mock_logger, "unknown_indicator", 123.0), f"{Fore.YELLOW}UNKNOWN_INDICATOR:{Style.RESET_ALL} No specific interpretation available.")

        # Test no data
        self.assertIn("No data available", interpret_indicator(mock_logger, "rsi", None))
        self.assertIn("No data available", interpret_indicator(mock_logger, "rsi", []))
        self.assertIn("No data available", interpret_indicator(mock_logger, "rsi", pd.Series(dtype=float)))

if __name__ == '__main__':
    unittest.main()
