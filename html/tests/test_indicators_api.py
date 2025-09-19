import pandas as pd
import numpy as np
import pytest
from indicators_api import calculate_ema, calculate_rsi, calculate_supertrend

# Fixture for a basic DataFrame
@pytest.fixture
def sample_dataframe():
    data = {
        'open': [10, 12, 15, 13, 16, 18, 17, 20, 22, 21, 24, 23, 26, 25, 28, 27, 30, 29, 32, 31],
        'high': [12, 15, 17, 16, 19, 20, 19, 23, 24, 23, 26, 25, 28, 27, 30, 29, 32, 31, 34, 33],
        'low': [9, 11, 12, 11, 14, 16, 15, 18, 20, 19, 22, 21, 24, 23, 26, 25, 28, 27, 30, 29],
        'close': [11, 14, 13, 15, 17, 19, 18, 21, 20, 22, 25, 24, 27, 26, 29, 28, 31, 30, 33, 32]
    }
    return pd.DataFrame(data)

# Test for calculate_ema
def test_calculate_ema(sample_dataframe):
    df = sample_dataframe.copy()
    period = 3
    df_ema = calculate_ema(df, period=period)
    assert f'ema_{period}' in df_ema.columns
    assert not df_ema[f'ema_{period}'].isnull().all() # Ensure some values are calculated
    assert pd.isna(df_ema[f'ema_{period}'].iloc[period-2]) # First (period-1) values are NaN
    assert not pd.isna(df_ema[f'ema_{period}'].iloc[period-1]) # First calculated value

def test_calculate_ema_insufficient_data(sample_dataframe):
    df_short = sample_dataframe.head(1).copy() # Only 1 row
    period = 3
    df_ema = calculate_ema(df_short, period=period)
    assert f'ema_{period}' in df_ema.columns
    assert df_ema[f'ema_{period}'].isnull().all() # All should be NaN

def test_calculate_ema_missing_column(sample_dataframe):
    df_no_close = sample_dataframe.drop(columns=['close']).copy()
    with pytest.raises(ValueError, match="Column 'close' not found"):
        calculate_ema(df_no_close)

# Test for calculate_rsi
def test_calculate_rsi(sample_dataframe):
    df = sample_dataframe.copy()
    period = 3
    df_rsi = calculate_rsi(df, period=period)
    assert f'rsi_{period}' in df_rsi.columns
    assert not df_rsi[f'rsi_{period}'].isnull().all() # Ensure some values are calculated
    assert pd.isna(df_rsi[f'rsi_{period}'].iloc[period-2]) # First (period-1) values are NaN
    assert not pd.isna(df_rsi[f'rsi_{period}'].iloc[period-1]) # First calculated value
    assert (df_rsi[f'rsi_{period}'].dropna() >= 0).all() and (df_rsi[f'rsi_{period}'].dropna() <= 100).all() # RSI bounds

def test_calculate_rsi_insufficient_data(sample_dataframe):
    df_short = sample_dataframe.head(1).copy()
    period = 3
    df_rsi = calculate_rsi(df_short, period=period)
    assert f'rsi_{period}' in df_rsi.columns
    assert df_rsi[f'rsi_{period}'].isnull().all() # All should be NaN

def test_calculate_rsi_missing_column(sample_dataframe):
    df_no_close = sample_dataframe.drop(columns=['close']).copy()
    with pytest.raises(ValueError, match="Column 'close' not found"):
        calculate_rsi(df_no_close)

# Test for calculate_supertrend
def test_calculate_supertrend(sample_dataframe):
    df = sample_dataframe.copy()
    period = 7
    multiplier = 3.0
    df_st = calculate_supertrend(df, period=period, multiplier=multiplier)
    assert 'supertrend' in df_st.columns
    assert 'supertrend_direction' in df_st.columns
    assert not df_st['supertrend'].isnull().all() # Ensure some values are calculated
    
    # Assert that there are some NaNs at the beginning
    assert df_st['supertrend'].head(period - 1).isnull().any() # At least one NaN in the first (period-1) values
    # Assert that there are some non-NaNs later
    assert df_st['supertrend'].tail(len(df) - (period - 1)).notnull().any() # At least one non-NaN after (period-1) values

    assert df_st['supertrend_direction'].dropna().isin([-1, 1]).all() # Direction should be -1 or 1

def test_calculate_supertrend_insufficient_data(sample_dataframe):
    df_short = sample_dataframe.head(5).copy()
    period = 7
    multiplier = 3.0
    df_st = calculate_supertrend(df_short, period=period, multiplier=multiplier)
    assert 'supertrend' in df_st.columns
    assert 'supertrend_direction' in df_st.columns
    assert df_st['supertrend'].isnull().all() # All should be NaN
    assert df_st['supertrend_direction'].isnull().all() # All should be NaN

def test_calculate_supertrend_missing_columns(sample_dataframe):
    df_no_high = sample_dataframe.drop(columns=['high']).copy()
    with pytest.raises(ValueError, match="DataFrame must contain 'high', 'low', and 'close' columns"):
        calculate_supertrend(df_no_high)