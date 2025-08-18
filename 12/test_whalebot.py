import unittest
import pandas as pd
import numpy as np
from decimal import Decimal, getcontext
from unittest.mock import MagicMock, patch
import logging

# Set precision for Decimal
getcontext().prec = 10

# It's good practice to import the module/classes you are testing
from whalebot import (
    generate_signature,
    interpret_indicator,
    TradingAnalyzer,
    load_config,
    fetch_klines # To create a realistic dataframe
)

# Disable logging for tests to keep output clean
logging.disable(logging.CRITICAL)

class TestHelperFunctions(unittest.TestCase):
    """Tests for standalone helper functions in the whalebot script."""

    def test_generate_signature(self):
        """Tests the HMAC SHA256 signature generation."""
        api_secret = "my_super_secret_key"
        params = {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "orderType": "Limit",
            "qty": "1.0",
            "price": "50000.0"
        }
        # Note: The actual signature generation for Bybit V5 is more complex than this,
        # but we test the function as it is written in the script.
        actual_signature = generate_signature(api_secret, params)
        self.assertIsInstance(actual_signature, str)
        self.assertEqual(len(actual_signature), 64) # SHA256 hex digest is 64 chars

    def test_interpret_indicator_rsi(self):
        """Tests the interpretation of RSI values."""
        self.assertIn("Overbought", interpret_indicator(MagicMock(), "rsi", [75.0]))
        self.assertIn("Oversold", interpret_indicator(MagicMock(), "rsi", [25.0]))
        self.assertIn("Neutral", interpret_indicator(MagicMock(), "rsi", [50.0]))

    def test_interpret_indicator_mfi(self):
        """Tests the interpretation of MFI values."""
        self.assertIn("Overbought", interpret_indicator(MagicMock(), "mfi", [85.0]))
        self.assertIn("Oversold", interpret_indicator(MagicMock(), "mfi", [15.0]))
        self.assertIn("Neutral", interpret_indicator(MagicMock(), "mfi", [50.0]))

    def test_interpret_indicator_adx(self):
        """Tests the interpretation of ADX values."""
        self.assertIn("Trending", interpret_indicator(MagicMock(), "adx", [30.0]))
        self.assertIn("Ranging", interpret_indicator(MagicMock(), "adx", [20.0]))

    def test_interpret_indicator_no_data(self):
        """Tests indicator interpretation with no data."""
        self.assertIn("No data available", interpret_indicator(MagicMock(), "rsi", []))
        self.assertIn("No data available", interpret_indicator(MagicMock(), "mfi", None))


class TestTradingAnalyzer(unittest.TestCase):
    """Tests for the TradingAnalyzer class and its indicator calculations."""

    @classmethod
    def setUpClass(cls):
        """Set up a sample DataFrame and config that can be used across all tests in this class."""
        cls.config = load_config("config.json")
        data = {
            'start_time': pd.to_datetime(pd.date_range(start='2023-01-01', periods=50, freq='h')),
            'open': np.random.uniform(100, 110, 50),
            'high': np.random.uniform(110, 120, 50),
            'low': np.random.uniform(90, 100, 50),
            'close': [105 + i + np.sin(i/5) * 5 for i in range(50)],
            'volume': np.random.uniform(1000, 5000, 50),
            'turnover': np.random.uniform(100000, 500000, 50)
        }
        cls.df = pd.DataFrame(data)
        for col in cls.df.columns[1:]:
            cls.df[col] = pd.to_numeric(cls.df[col])
        cls.symbol_logger = MagicMock()

    def setUp(self):
        """Create a new analyzer instance for each test to ensure isolation."""
        self.analyzer = TradingAnalyzer(self.df.copy(), self.config, self.symbol_logger, "BTCUSDT", "5")

    def test_initialization(self):
        """Test that the TradingAnalyzer initializes correctly."""
        self.assertIsInstance(self.analyzer, TradingAnalyzer)
        self.assertIn("momentum", self.analyzer.df.columns)
        self.assertIn("volume_ma", self.analyzer.df.columns)
        self.assertIsNotNone(self.analyzer.user_defined_weights)
        self.assertIn("atr", self.analyzer.indicator_values)

    def test_calculate_sma(self):
        """Test the Simple Moving Average calculation."""
        sma_10 = self.analyzer._calculate_sma(window=10)
        self.assertIsInstance(sma_10, pd.Series)
        self.assertEqual(len(sma_10), len(self.df))
        self.assertTrue(sma_10.iloc[:9].isnull().all())
        expected_sma = self.df['close'].iloc[0:10].mean()
        self.assertAlmostEqual(sma_10.iloc[9], expected_sma, places=4)

    def test_calculate_ema(self):
        """Test the Exponential Moving Average calculation."""
        ema_12 = self.analyzer._calculate_ema(window=12)
        self.assertIsInstance(ema_12, pd.Series)
        self.assertEqual(len(ema_12), len(self.df))
        expected_ema = self.df['close'].ewm(span=12, adjust=False).mean()
        pd.testing.assert_series_equal(ema_12, expected_ema)

    def test_calculate_rsi(self):
        """Test the Relative Strength Index calculation."""
        rsi = self.analyzer._calculate_rsi(window=14)
        self.assertIsInstance(rsi, pd.Series)
        self.assertEqual(len(rsi), len(self.df))
        self.assertTrue((rsi.dropna() >= 0).all() and (rsi.dropna() <= 100).all())

    def test_calculate_atr(self):
        """Test the Average True Range calculation."""
        atr = self.analyzer._calculate_atr(window=14)
        self.assertIsInstance(atr, pd.Series)
        self.assertEqual(len(atr), len(self.df))
        self.assertTrue((atr.dropna() >= 0).all())

    def test_calculate_macd(self):
        """Test the MACD calculation."""
        macd_df = self.analyzer._calculate_macd()
        self.assertIsInstance(macd_df, pd.DataFrame)
        self.assertIn('macd', macd_df.columns)
        self.assertIn('signal', macd_df.columns)
        self.assertIn('histogram', macd_df.columns)
        expected_histogram = macd_df['macd'] - macd_df['signal']
        pd.testing.assert_series_equal(macd_df['histogram'], expected_histogram, check_names=False)

    def test_calculate_stoch_rsi(self):
        """Test the Stochastic RSI calculation."""
        stoch_rsi_df = self.analyzer._calculate_stoch_rsi()
        self.assertIsInstance(stoch_rsi_df, pd.DataFrame)
        self.assertIn('k', stoch_rsi_df.columns)
        self.assertIn('d', stoch_rsi_df.columns)
        self.assertTrue((stoch_rsi_df['k'].dropna() >= 0).all() and (stoch_rsi_df['k'].dropna() <= 100).all())
        self.assertTrue((stoch_rsi_df['d'].dropna() >= 0).all() and (stoch_rsi_df['d'].dropna() <= 100).all())

    def test_determine_trend_momentum(self):
        """Test the trend and momentum determination."""
        trend_data = self.analyzer.determine_trend_momentum()
        self.assertIsInstance(trend_data, dict)
        self.assertIn("trend", trend_data)
        self.assertIn("strength", trend_data)
        self.assertIn(trend_data["trend"], ["Uptrend", "Downtrend", "Neutral", "Insufficient Data"])

    def test_generate_trading_signal_no_signal(self):
        """Test that no signal is generated when conditions are neutral."""
        self.analyzer.indicator_values['order_book_walls'] = {'bullish': False, 'bearish': False}
        self.analyzer.indicator_values['stoch_rsi_vals'] = pd.DataFrame({'k': [50], 'd': [50]})
        self.analyzer.indicator_values['rsi'] = [50]
        self.analyzer.indicator_values['mfi'] = [50]
        self.analyzer.indicator_values['ema_alignment'] = 0.0
        self.analyzer.indicator_values['stoch_osc_vals'] = pd.DataFrame({'k': [50], 'd': [50]})
        signal, score, conditions, levels = self.analyzer.generate_trading_signal(Decimal('150.0'))
        self.assertIsNone(signal)
        self.assertEqual(score, 0.0)
        self.assertEqual(len(conditions), 0)

    def test_generate_trading_signal_buy_signal(self):
        """Test that a buy signal is generated under specific bullish conditions."""
        self.analyzer.indicator_values['stoch_rsi_vals'] = pd.DataFrame({'k': [10, 15, 18], 'd': [12, 14, 16]})
        self.analyzer.indicator_values['rsi'] = [25, 28, 29]
        self.analyzer.indicator_values['ema_alignment'] = 1.0
        self.analyzer.indicator_values['order_book_walls'] = {"bullish": True}
        self.analyzer.config["indicators"]["stoch_rsi"] = True
        self.analyzer.config["indicators"]["rsi"] = True
        self.analyzer.config["indicators"]["ema_alignment"] = True
        signal, score, conditions, levels = self.analyzer.generate_trading_signal(Decimal('150.0'))
        self.assertEqual(signal, "buy")
        self.assertGreater(score, 0)
        self.assertIn("Stoch RSI Oversold Crossover", conditions)
        self.assertIn("RSI Oversold", conditions)
        self.assertIn("Bullish EMA Alignment", conditions)
        self.assertIn("Bullish Order Book Wall", conditions)
        self.assertIn("stop_loss", levels)
        self.assertIn("take_profit", levels)

    @patch('whalebot.bybit_request')
    def test_fetch_klines_success(self, mock_bybit_request):
        """Test fetching klines successfully."""
        mock_response = {
            "retCode": 0,
            "result": {
                "list": [
                    ["1622544000000", "45000", "45100", "44900", "45050", "100", "4500000"],
                    ["1622544060000", "45050", "45150", "44950", "45100", "120", "5412000"]
                ]
            }
        }
        mock_bybit_request.return_value = mock_response
        df = fetch_klines("BTCUSDT", "1", "key", "secret", self.symbol_logger)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 2)
        self.assertEqual(df['close'].iloc[0], 45050)

    @patch('whalebot.bybit_request')
    def test_fetch_klines_api_error(self, mock_bybit_request):
        """Test fetching klines when the API returns an error."""
        mock_bybit_request.return_value = {"retCode": 10001, "retMsg": "Error"}
        df = fetch_klines("BTCUSDT", "1", "key", "secret", self.symbol_logger)
        self.assertTrue(df.empty)

    def test_calculate_cci(self):
        """Test the Commodity Channel Index calculation."""
        cci = self.analyzer._calculate_cci(window=20)
        self.assertIsInstance(cci, pd.Series)
        self.assertEqual(len(cci), len(self.df))

    def test_calculate_williams_r(self):
        """Test the Williams %R calculation."""
        wr = self.analyzer._calculate_williams_r(window=14)
        self.assertIsInstance(wr, pd.Series)
        self.assertEqual(len(wr), len(self.df))
        self.assertTrue((wr.dropna() <= 0).all() and (wr.dropna() >= -100).all())

    def test_calculate_mfi(self):
        """Test the Money Flow Index calculation."""
        mfi = self.analyzer._calculate_mfi(window=14)
        self.assertIsInstance(mfi, pd.Series)
        self.assertEqual(len(mfi), len(self.df))
        self.assertTrue((mfi.dropna() >= 0).all() and (mfi.dropna() <= 100).all())

    def test_calculate_adx(self):
        """Test the Average Directional Index calculation."""
        adx = self.analyzer._calculate_adx(window=14)
        self.assertIsInstance(adx, float)
        self.assertGreaterEqual(adx, 0)

    def test_calculate_obv(self):
        """Test the On-Balance Volume calculation."""
        obv = self.analyzer._calculate_obv()
        self.assertIsInstance(obv, pd.Series)
        self.assertEqual(len(obv), len(self.df))

    def test_calculate_adi(self):
        """Test the Accumulation/Distribution Index calculation."""
        adi = self.analyzer._calculate_adi()
        self.assertIsInstance(adi, pd.Series)
        self.assertEqual(len(adi), len(self.df))

    def test_calculate_psar(self):
        """Test the Parabolic SAR calculation."""
        psar = self.analyzer._calculate_psar()
        self.assertIsInstance(psar, pd.Series)
        self.assertEqual(len(psar), len(self.df))

    def test_detect_macd_divergence(self):
        """Test MACD divergence detection."""
        self.analyzer.df['close'].iloc[-1] = 140
        self.analyzer.df['close'].iloc[-2] = 145
        with patch.object(self.analyzer, '_calculate_macd') as mock_macd:
            mock_macd.return_value = pd.DataFrame({'histogram': np.linspace(-1, 2, 50)})
            divergence = self.analyzer.detect_macd_divergence()
            self.assertEqual(divergence, "bullish")

    def test_analyze_order_book_walls(self):
        """Test the order book wall analysis."""
        order_book = {
            'bids': [['100', '50'], ['99', '10']],
            'asks': [['110', '10'], ['111', '12']]
        }
        self.analyzer.df['volume'] = 15
        self.analyzer.df['close'].iloc[-1] = 105
        has_bullish, has_bearish, _, _ = self.analyzer.analyze_order_book_walls(order_book)
        self.assertTrue(has_bullish)
        self.assertFalse(has_bearish)

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)