import unittest
import pandas as pd
from decimal import Decimal, getcontext
from unittest.mock import MagicMock, patch
import math
import sys

# Ensure the root directory is in the Python path for imports
sys.path.insert(0, '/data/data/com.termux/files/home/Algobots')

# Mock setup_logging to prevent actual log file creation during tests
with patch('bot_logger.setup_logging'):
    from indicators import (
        calculate_atr, calculate_fibonacci_pivot_points, calculate_stochrsi,
        calculate_sma, calculate_ehlers_fisher_transform, calculate_ehlers_super_smoother,
        find_pivots, handle_websocket_kline_data, calculate_vwap,
        calculate_order_book_imbalance, calculate_ehlers_fisher_strategy, calculate_supertrend
    )

# Set Decimal precision for tests
getcontext().prec = 38

# Helper function to create a sample DataFrame
def create_sample_kline_df(rows=100, start_timestamp_ms=None, has_tz=True):
    if start_timestamp_ms is None:
        start_timestamp_ms = int(pd.Timestamp.now().timestamp() * 1000) - (rows * 60 * 1000)

    timestamps = pd.to_datetime(range(start_timestamp_ms, start_timestamp_ms + rows * 60 * 1000, 60 * 1000), unit='ms')
    if has_tz:
        timestamps = timestamps.tz_localize('UTC')

    data = {
        'open': [Decimal(str(100 + i * 0.1)) for i in range(rows)],
        'high': [Decimal(str(101 + i * 0.1)) for i in range(rows)],
        'low': [Decimal(str(99 + i * 0.1)) for i in range(rows)],
        'close': [Decimal(str(100.5 + i * 0.1)) for i in range(rows)],
        'volume': [Decimal(str(1000 + i * 10)) for i in range(rows)],
        'tr1': [Decimal('0')] * rows, # Add dummy columns for supertrend
        'tr2': [Decimal('0')] * rows,
        'tr3': [Decimal('0')] * rows,
        'tr': [Decimal('0')] * rows,
        'atr': [Decimal('0')] * rows,
        'hl2': [Decimal('0')] * rows,
        'supertrend': [Decimal('0')] * rows,
        'supertrend_direction': [1] * rows,
        'min_low_ehlers': [Decimal('0')] * rows, # Add dummy columns for ehlers fisher
        'max_high_ehlers': [Decimal('0')] * rows,
        'ehlers_value1': [Decimal('0')] * rows,
        'ehlers_fisher': [Decimal('0')] * rows,
        'ehlers_signal': [Decimal('0')] * rows,
        'rsi': [Decimal('0')] * rows,
        'stoch_rsi': [Decimal('0')] * rows,
        'stoch_k': [Decimal('0')] * rows,
        'stoch_d': [Decimal('0')] * rows,
        'sma': [Decimal('0')] * rows
    }
    df = pd.DataFrame(data, index=timestamps)
    # Ensure Decimal types for all relevant columns
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].apply(Decimal)
    return df

class TestIndicators(unittest.TestCase):

    def setUp(self):
        self.df = create_sample_kline_df(rows=200)

    def test_calculate_atr(self):
        atr_series = calculate_atr(self.df, length=14)
        self.assertIsInstance(atr_series, pd.Series)
        self.assertFalse(atr_series.isnull().all())
        self.assertTrue(len(atr_series) > 0)
        # Check if the last value is a Decimal
        self.assertIsInstance(atr_series.iloc[-1], Decimal)

    def test_calculate_atr_missing_columns(self):
        df_invalid = self.df.drop(columns=['high', 'low'])
        atr_series = calculate_atr(df_invalid)
        self.assertTrue(atr_series.empty)

    def test_calculate_fibonacci_pivot_points(self):
        resistance, support = calculate_fibonacci_pivot_points(self.df)
        self.assertIsInstance(resistance, list)
        self.assertIsInstance(support, list)
        self.assertTrue(len(resistance) > 0)
        self.assertTrue(len(support) > 0)
        self.assertIsInstance(resistance[0]['price'], Decimal)

    def test_calculate_fibonacci_pivot_points_empty_df(self):
        resistance, support = calculate_fibonacci_pivot_points(pd.DataFrame())
        self.assertEqual(resistance, [])
        self.assertEqual(support, [])

    def test_calculate_stochrsi(self):
        df_stochrsi = calculate_stochrsi(self.df, rsi_period=14, stoch_k_period=14, stoch_d_period=3)
        self.assertIn('stoch_rsi', df_stochrsi.columns)
        self.assertIn('stoch_k', df_stochrsi.columns)
        self.assertIn('stoch_d', df_stochrsi.columns)
        self.assertFalse(df_stochrsi['stoch_rsi'].isnull().all())
        self.assertIsInstance(df_stochrsi['stoch_rsi'].iloc[-1], Decimal)

    def test_calculate_stochrsi_missing_close(self):
        df_invalid = self.df.drop(columns=['close'])
        df_stochrsi = calculate_stochrsi(df_invalid)
        self.assertNotIn('stoch_rsi', df_stochrsi.columns)

    def test_calculate_sma(self):
        sma_series = calculate_sma(self.df, length=10)
        self.assertIsInstance(sma_series, pd.Series)
        self.assertFalse(sma_series.isnull().all())
        self.assertIsInstance(sma_series.iloc[-1], Decimal)

    def test_calculate_sma_missing_close(self):
        df_invalid = self.df.drop(columns=['close'])
        sma_series = calculate_sma(df_invalid, length=10)
        self.assertTrue(sma_series.empty)

    def test_calculate_ehlers_fisher_transform(self):
        fisher, signal = calculate_ehlers_fisher_transform(self.df, length=9, signal_length=1)
        self.assertIsInstance(fisher, pd.Series)
        self.assertIsInstance(signal, pd.Series)
        self.assertFalse(fisher.isnull().all())
        self.assertFalse(signal.isnull().all())
        self.assertIsInstance(fisher.iloc[-1], Decimal)

    def test_calculate_ehlers_fisher_transform_missing_columns(self):
        df_invalid = self.df.drop(columns=['high'])
        fisher, signal = calculate_ehlers_fisher_transform(df_invalid)
        self.assertTrue(fisher.empty)
        self.assertTrue(signal.empty)

    def test_calculate_ehlers_super_smoother(self):
        smoother_series = calculate_ehlers_super_smoother(self.df, length=10)
        self.assertIsInstance(smoother_series, pd.Series)
        self.assertFalse(smoother_series.isnull().all())
        self.assertIsInstance(smoother_series.iloc[-1], Decimal)

    def test_calculate_ehlers_super_smoother_missing_close(self):
        df_invalid = self.df.drop(columns=['close'])
        smoother_series = calculate_ehlers_super_smoother(df_invalid, length=10)
        self.assertTrue(smoother_series.empty)

    def test_find_pivots(self):
        pivot_highs, pivot_lows = find_pivots(self.df, left=5, right=5, use_wicks=True)
        self.assertIsInstance(pivot_highs, pd.Series)
        self.assertIsInstance(pivot_lows, pd.Series)
        self.assertEqual(len(pivot_highs), len(self.df))
        self.assertEqual(len(pivot_lows), len(self.df))

    def test_find_pivots_insufficient_data(self):
        df_small = create_sample_kline_df(rows=5)
        pivot_highs, pivot_lows = find_pivots(df_small, left=5, right=5, use_wicks=True)
        self.assertTrue(pivot_highs.empty)
        self.assertTrue(pivot_lows.empty)

    def test_handle_websocket_kline_data_single_kline(self):
        initial_df = create_sample_kline_df(rows=5)
        message = {
            "data": [{
                "start": str(int(initial_df.index[-1].timestamp() * 1000) + 60000),
                "open": "105.0", "high": "105.5", "low": "104.5", "close": "105.2", "volume": "1200"
            }]
        }
        updated_df = handle_websocket_kline_data(initial_df, message)
        self.assertEqual(len(updated_df), len(initial_df) + 1)
        self.assertTrue(updated_df.index.is_monotonic_increasing)
        self.assertEqual(updated_df.iloc[-1]['close'], Decimal('105.2'))
        self.assertTrue(updated_df.index.tz is not None) # Check for timezone awareness

    def test_handle_websocket_kline_data_multiple_klines(self):
        initial_df = create_sample_kline_df(rows=5)
        message = {
            "data": [
                {"start": str(int(initial_df.index[-1].timestamp() * 1000) + 60000), "open": "105.0", "high": "105.5", "low": "104.5", "close": "105.2", "volume": "1200"},
                {"start": str(int(initial_df.index[-1].timestamp() * 1000) + 120000), "open": "105.2", "high": "106.0", "low": "105.0", "close": "105.8", "volume": "1300"}
            ]
        }
        updated_df = handle_websocket_kline_data(initial_df, message)
        self.assertEqual(len(updated_df), len(initial_df) + 2)
        self.assertTrue(updated_df.index.is_monotonic_increasing)
        self.assertEqual(updated_df.iloc[-1]['close'], Decimal('105.8'))

    def test_handle_websocket_kline_data_update_existing(self):
        initial_df = create_sample_kline_df(rows=5)
        # Message for the last existing kline, but with updated close
        message = {
            "data": [{
                "start": str(int(initial_df.index[-1].timestamp() * 1000)),
                "open": str(initial_df['open'].iloc[-1]),
                "high": str(initial_df['high'].iloc[-1]),
                "low": str(initial_df['low'].iloc[-1]),
                "close": "999.9", # Updated close price
                "volume": str(initial_df['volume'].iloc[-1])
            }]
        }
        updated_df = handle_websocket_kline_data(initial_df, message)
        self.assertEqual(len(updated_df), len(initial_df)) # Length should not change
        self.assertEqual(updated_df.iloc[-1]['close'], Decimal('999.9'))

    def test_handle_websocket_kline_data_empty_initial_df(self):
        message = {
            "data": [{
                "start": "1678886400000", "open": "100", "high": "101", "low": "99", "close": "100.5", "volume": "1000"
            }]
        }
        updated_df = handle_websocket_kline_data(pd.DataFrame(), message)
        self.assertEqual(len(updated_df), 1)
        self.assertEqual(updated_df.iloc[-1]['close'], Decimal('100.5'))

    def test_calculate_vwap(self):
        vwap_series = calculate_vwap(self.df)
        self.assertIsInstance(vwap_series, pd.Series)
        self.assertFalse(vwap_series.isnull().all())
        self.assertIsInstance(vwap_series.iloc[-1], Decimal)

    def test_calculate_vwap_missing_columns(self):
        df_invalid = self.df.drop(columns=['volume'])
        vwap_series = calculate_vwap(df_invalid)
        self.assertTrue(vwap_series.empty)

    def test_calculate_order_book_imbalance(self):
        order_book_data = {
            'b': [["100.0", "10"], ["99.9", "5"]],
            'a': [["100.1", "8"], ["100.2", "7"]]
        }
        imbalance, total_volume = calculate_order_book_imbalance(order_book_data)
        self.assertIsInstance(imbalance, Decimal)
        self.assertIsInstance(total_volume, Decimal)
        self.assertNotEqual(total_volume, Decimal('0'))
        # Expected calculation: (100*10 + 99.9*5) - (100.1*8 + 100.2*7) / total_volume
        # bid_vol = 1000 + 499.5 = 1499.5
        # ask_vol = 800.8 + 701.4 = 1502.2
        # total_vol = 3001.7
        # imbalance = (1499.5 - 1502.2) / 3001.7 = -2.7 / 3001.7 = -0.000899...
        self.assertAlmostEqual(float(imbalance), -0.0008994236665559556, places=5)

    def test_calculate_order_book_imbalance_empty(self):
        imbalance, total_volume = calculate_order_book_imbalance({'b': [], 'a': []})
        self.assertEqual(imbalance, Decimal('0'))
        self.assertEqual(total_volume, Decimal('0'))

    def test_calculate_ehlers_fisher_strategy(self):
        df_fisher = calculate_ehlers_fisher_strategy(self.df, length=10)
        self.assertIn('ehlers_fisher', df_fisher.columns)
        self.assertIn('ehlers_signal', df_fisher.columns)
        self.assertFalse(df_fisher['ehlers_fisher'].isnull().all())
        self.assertIsInstance(df_fisher['ehlers_fisher'].iloc[-1], Decimal)

    def test_calculate_ehlers_fisher_strategy_missing_columns(self):
        df_invalid = self.df.drop(columns=['high'])
        df_fisher = calculate_ehlers_fisher_strategy(df_invalid, length=10)
        self.assertNotIn('ehlers_fisher', df_fisher.columns)

    def test_calculate_supertrend(self):
        df_supertrend = calculate_supertrend(self.df, period=10, multiplier=3.0)
        self.assertIn('supertrend', df_supertrend.columns)
        self.assertIn('supertrend_direction', df_supertrend.columns)
        self.assertFalse(df_supertrend['supertrend'].isnull().all())
        self.assertIsInstance(df_supertrend['supertrend'].iloc[-1], Decimal)

    def test_calculate_supertrend_missing_columns(self):
        df_invalid = self.df.drop(columns=['high', 'low'])
        df_supertrend = calculate_supertrend(df_invalid, period=10, multiplier=3.0)
        self.assertNotIn('supertrend', df_supertrend.columns)


if __name__ == '__main__':
    unittest.main()