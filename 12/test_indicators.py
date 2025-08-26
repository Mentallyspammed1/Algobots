import unittest

import numpy as np
import pandas as pd

# We need to import the class we want to test
from whalebot import TradingAnalyzer, load_config

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



class TestTradingAnalyzerIndicators(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up a sample DataFrame and config that can be used for all tests."""
        # Create a more realistic and longer sample DataFrame
        data = {
            'start_time': pd.to_datetime(pd.date_range(start='2023-01-01', periods=100, freq='H')),
            'open': np.random.uniform(90, 110, 100),
            'high': np.random.uniform(100, 120, 100),
            'low': np.random.uniform(80, 100, 100),
            'close': np.random.uniform(95, 115, 100),
            'volume': np.random.uniform(1000, 5000, 100)
        }
        # Ensure high is always >= close and low is always <= close
        data['high'] = data['close'] + np.random.uniform(0, 5, 100)
        data['low'] = data['close'] - np.random.uniform(0, 5, 100)

        cls.df = pd.DataFrame(data)

        # Load the default config from the file to ensure tests run with valid settings
        cls.config = load_config("config.json")

        # Instantiate the analyzer once for all tests to use
        cls.analyzer = TradingAnalyzer(cls.df, cls.config, symbol_logger=MockLogger(), symbol="TESTUSDT", interval="1H")

    def test_setup_and_initialization(self):
        """Test that the analyzer is initialized correctly."""
        self.assertIsInstance(self.analyzer, TradingAnalyzer)
        self.assertEqual(len(self.analyzer.df), 100)
        self.assertIn("close", self.analyzer.df.columns)

    #    def test_calculate_sma(self):
#        """Test the SMA calculation."""
#        window = 10
#        sma_series = self.analyzer._calculate_sma(window)
#        self.assertIsInstance(sma_series, pd.Series)
#        self.assertEqual(len(sma_series), len(self.df))
#        # The first (window-1) values should be NaN
#        self.assertTrue(sma_series.head(window - 1).isnull().all())
#        self.assertFalse(pd.isna(sma_series.iloc[-1]))
#
#    def test_calculate_ema(self):
#        """Test the EMA calculation."""
#        window = 10
#        ema_series = self.analyzer._calculate_ema(window)
#        self.assertIsInstance(ema_series, pd.Series)
#        self.assertEqual(len(ema_series), len(self.df))
#        self.assertFalse(pd.isna(ema_series.iloc[-1]))
#
#    def test_calculate_atr(self):
#        """Test the ATR calculation."""
#        window = 14
#        atr_series = self.analyzer._calculate_atr(window)
#        self.assertIsInstance(atr_series, pd.Series)
#        self.assertEqual(len(atr_series), len(self.df))
#        self.assertFalse(pd.isna(atr_series.iloc[-1]))
#        self.assertTrue(all(atr_series.dropna() >= 0))
#
#    def test_calculate_rsi(self):
#        """Test the RSI calculation."""
#        window = 14
#        rsi_series = self.analyzer._calculate_rsi(window)
#        self.assertIsInstance(rsi_series, pd.Series)
#        self.assertEqual(len(rsi_series), len(self.df))
#        self.assertFalse(pd.isna(rsi_series.iloc[-1]))
#        # RSI values should be between 0 and 100
#        self.assertTrue(all(rsi_series.dropna() >= 0))
#        self.assertTrue(all(rsi_series.dropna() <= 100))
#
#    def test_calculate_stoch_rsi(self):
#        """Test the Stochastic RSI calculation."""
#        stoch_rsi_df = self.analyzer._calculate_stoch_rsi()
#        self.assertIsInstance(stoch_rsi_df, pd.DataFrame)
#        self.assertIn('k', stoch_rsi_df.columns)
#        self.assertIn('d', stoch_rsi_df.columns)
#        self.assertEqual(len(stoch_rsi_df), len(self.df))
#        self.assertFalse(pd.isna(stoch_rsi_df['k'].iloc[-1]))
#        self.assertFalse(pd.isna(stoch_rsi_df['d'].iloc[-1]))
#
#    def test_calculate_stochastic_oscillator(self):
#        """Test the Stochastic Oscillator calculation."""
#        stoch_osc_df = self.analyzer._calculate_stochastic_oscillator()
#        self.assertIsInstance(stoch_osc_df, pd.DataFrame)
#        self.assertIn('k', stoch_osc_df.columns)
#        self.assertIn('d', stoch_osc_df.columns)
#        self.assertEqual(len(stoch_osc_df), len(self.df))
#        self.assertFalse(pd.isna(stoch_osc_df['k'].iloc[-1]))
#        self.assertFalse(pd.isna(stoch_osc_df['d'].iloc[-1]))
#
#    def test_calculate_macd(self):
#        """Test the MACD calculation."""
#        macd_df = self.analyzer._calculate_macd()
#        self.assertIsInstance(macd_df, pd.DataFrame)
#        self.assertIn('macd', macd_df.columns)
#        self.assertIn('signal', macd_df.columns)
#        self.assertIn('histogram', macd_df.columns)
#        self.assertEqual(len(macd_df), len(self.df))
#        self.assertFalse(pd.isna(macd_df['macd'].iloc[-1]))
#
#    def test_calculate_adx(self):
#        """Test the ADX calculation."""
#        window = 14
#        adx_value = self.analyzer._calculate_adx(window)
#        self.assertIsInstance(adx_value, float)
#        self.assertGreaterEqual(adx_value, 0)
#        self.assertLessEqual(adx_value, 100)
#
#    def test_calculate_obv(self):
#        """Test the OBV calculation."""
#        obv_series = self.analyzer._calculate_obv()
#        self.assertIsInstance(obv_series, pd.Series)
#        self.assertEqual(len(obv_series), len(self.df))
#        self.assertFalse(pd.isna(obv_series.iloc[-1]))
#
#    def test_calculate_adi(self):
#        """Test the ADI calculation."""
#        adi_series = self.analyzer._calculate_adi()
#        self.assertIsInstance(adi_series, pd.Series)
#        self.assertEqual(len(adi_series), len(self.df))
#        self.assertFalse(pd.isna(adi_series.iloc[-1]))
#
#    def test_calculate_cci(self):
#        """Test the CCI calculation."""
#        cci_series = self.analyzer._calculate_cci()
#        self.assertIsInstance(cci_series, pd.Series)
#        self.assertEqual(len(cci_series), len(self.df))
#        self.assertFalse(pd.isna(cci_series.iloc[-1]))
#
#    def test_calculate_williams_r(self):
#        """Test the Williams %R calculation."""
#        wr_series = self.analyzer._calculate_williams_r()
#        self.assertIsInstance(wr_series, pd.Series)
#        self.assertEqual(len(wr_series), len(self.df))
#        self.assertFalse(pd.isna(wr_series.iloc[-1]))
#        # Williams %R is between -100 and 0
#        self.assertTrue(all(wr_series.dropna() <= 0))
#        self.assertTrue(all(wr_series.dropna() >= -100))
#
#    def test_calculate_mfi(self):
#        """Test the MFI calculation."""
#        mfi_series = self.analyzer._calculate_mfi()
#        self.assertIsInstance(mfi_series, pd.Series)
#        self.assertEqual(len(mfi_series), len(self.df))
#        self.assertFalse(pd.isna(mfi_series.iloc[-1]))
#        # MFI is between 0 and 100
#        self.assertTrue(all(mfi_series.dropna() >= 0))
#        self.assertTrue(all(mfi_series.dropna() <= 100))
#
#    def test_calculate_psar(self):
#        """Test the PSAR calculation."""
#        psar_series = self.analyzer._calculate_psar()
#        self.assertIsInstance(psar_series, pd.Series)
#        self.assertEqual(len(psar_series), len(self.df))
#        self.assertFalse(pd.isna(psar_series.iloc[-1]))
#
#    def test_calculate_fve(self):
#        """Test the FVE calculation."""
#        # FVE is a custom indicator, so we mainly test for successful execution and correct output type
#        fve_series = self.analyzer._calculate_fve()
#        self.assertIsInstance(fve_series, pd.Series)
#        self.assertEqual(len(fve_series), len(self.df))
#        # It's okay if the last value is NaN if there's not enough data for all components
#        # but with 100 data points, it should calculate.
#        self.assertFalse(pd.isna(fve_series.iloc[-1]))

if __name__ == '__main__':
    unittest.main()
