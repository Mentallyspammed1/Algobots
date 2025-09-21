
import pytest
import pandas as pd
import numpy as np
import time
from unittest.mock import MagicMock

from whalebot_pro.analysis.indicators import IndicatorCalculator

@pytest.fixture
def mock_logger():
    return MagicMock(spec=logging.Logger)

@pytest.fixture
def indicator_calculator(mock_logger):
    return IndicatorCalculator(mock_logger)

@pytest.fixture
def large_sample_df():
    # Create a large DataFrame for performance testing
    num_rows = 10000 # 10,000 candles
    data = {
        'open': np.random.rand(num_rows) * 100 + 1000,
        'high': np.random.rand(num_rows) * 100 + 1050,
        'low': np.random.rand(num_rows) * 100 + 950,
        'close': np.random.rand(num_rows) * 100 + 1000,
        'volume': np.random.rand(num_rows) * 1000 + 10000,
        'turnover': np.random.rand(num_rows) * 100000 + 1000000,
    }
    df = pd.DataFrame(data, index=pd.to_datetime(pd.date_range(start='2023-01-01', periods=num_rows, freq='min')))
    return df

def test_all_indicators_performance(indicator_calculator, large_sample_df):
    # This test measures the time it takes to calculate all indicators
    # It's a benchmark, not a strict pass/fail based on time, but helps identify regressions.
    
    # Temporarily add ATR for indicators that depend on it
    large_sample_df["ATR"] = indicator_calculator.calculate_atr(large_sample_df, period=14)

    start_time = time.perf_counter()

    # Call each indicator calculation function
    indicator_calculator.calculate_sma(large_sample_df, period=10)
    indicator_calculator.calculate_ema(large_sample_df, period=21)
    indicator_calculator.calculate_true_range(large_sample_df)
    indicator_calculator.calculate_atr(large_sample_df, period=14)
    indicator_calculator.calculate_super_smoother(large_sample_df["close"], period=10)
    indicator_calculator.calculate_ehlers_supertrend(large_sample_df, period=10, multiplier=2.0)
    indicator_calculator.calculate_macd(large_sample_df, fast_period=12, slow_period=26, signal_period=9)
    indicator_calculator.calculate_rsi(large_sample_df, period=14)
    indicator_calculator.calculate_stoch_rsi(large_sample_df, period=14, k_period=3, d_period=3)
    indicator_calculator.calculate_adx(large_sample_df, period=14)
    indicator_calculator.calculate_bollinger_bands(large_sample_df, period=20, std_dev=2.0)
    indicator_calculator.calculate_vwap(large_sample_df)
    indicator_calculator.calculate_cci(large_sample_df, period=20)
    indicator_calculator.calculate_williams_r(large_sample_df, period=14)
    indicator_calculator.calculate_ichimoku_cloud(large_sample_df, tenkan_period=9, kijun_period=26, senkou_span_b_period=52, chikou_span_offset=26)
    indicator_calculator.calculate_mfi(large_sample_df, period=14)
    indicator_calculator.calculate_obv(large_sample_df, ema_period=20)
    indicator_calculator.calculate_cmf(large_sample_df, period=20)
    indicator_calculator.calculate_psar(large_sample_df, acceleration=0.02, max_acceleration=0.2)
    indicator_calculator.calculate_volatility_index(large_sample_df, period=20)
    indicator_calculator.calculate_vwma(large_sample_df, period=20)
    indicator_calculator.calculate_volume_delta(large_sample_df, period=5)
    indicator_calculator.calculate_kaufman_ama(large_sample_df, period=10, fast_period=2, slow_period=30)
    indicator_calculator.calculate_relative_volume(large_sample_df, period=20)
    indicator_calculator.calculate_market_structure(large_sample_df, lookback_period=10)
    indicator_calculator.calculate_dema(large_sample_df, period=14)
    indicator_calculator.calculate_keltner_channels(large_sample_df, period=20, atr_multiplier=2.0)
    indicator_calculator.calculate_roc(large_sample_df, period=12)
    indicator_calculator.detect_candlestick_patterns(large_sample_df)
    indicator_calculator.calculate_fibonacci_pivot_points(large_sample_df)
    indicator_calculator.calculate_support_resistance_from_orderbook([["1","1"]],[["2","1"]])

    end_time = time.perf_counter()
    duration = end_time - start_time

    indicator_calculator.logger.info(f"Calculated all indicators for {len(large_sample_df)} rows in {duration:.4f} seconds.")

    # Assert that the duration is within a reasonable limit (e.g., < 1 second for 10,000 rows)
    # This threshold might need adjustment based on hardware and exact implementation.
    assert duration < 1.0
