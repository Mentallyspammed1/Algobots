import numpy as np
import pandas as pd
import pytest
from indicators_api import calculate_ehlers_fisher_transform
from indicators_api import calculate_ema
from indicators_api import calculate_macd
from indicators_api import calculate_rsi
from indicators_api import calculate_supertrend


# Fixture for a basic DataFrame
@pytest.fixture
def sample_dataframe():
    data = {
        "open": [
            10,
            12,
            15,
            13,
            16,
            18,
            17,
            20,
            22,
            21,
            25,
            24,
            28,
            30,
            29,
            32,
            35,
            33,
            36,
            38,
        ],
        "high": [
            13,
            16,
            17,
            16,
            19,
            20,
            21,
            23,
            24,
            23,
            27,
            26,
            30,
            32,
            31,
            34,
            37,
            36,
            39,
            40,
        ],
        "low": [
            9,
            11,
            12,
            12,
            14,
            16,
            15,
            18,
            20,
            19,
            22,
            21,
            25,
            27,
            26,
            29,
            31,
            30,
            33,
            35,
        ],
        "close": [
            12,
            15,
            13,
            16,
            18,
            17,
            20,
            22,
            21,
            25,
            24,
            28,
            30,
            29,
            32,
            35,
            33,
            36,
            38,
            37,
        ],
    }
    df = pd.DataFrame(data)
    return df


# Fixture for a DataFrame with insufficient data
@pytest.fixture
def insufficient_dataframe():
    data = {
        "open": [10, 12, 15],
        "high": [13, 16, 17],
        "low": [9, 11, 12],
        "close": [12, 15, 13],
    }
    df = pd.DataFrame(data)
    return df


# Test for calculate_ema
def test_calculate_ema_basic(sample_dataframe):
    df_result = calculate_ema(sample_dataframe.copy(), period=3)
    assert "ema_3" in df_result.columns
    assert not df_result["ema_3"].isnull().all()  # Should have some non-NaN values
    # Check a known value (manual calculation for first few values)
    # EMA(3) = (Close * 2 / (3 + 1)) + (EMA_prev * (1 - 2 / (3 + 1)))
    # Close: 12, 15, 13, 16, 18
    # EMA_0 = NaN
    # EMA_1 = NaN
    # EMA_2 = NaN (or simple average for first 'period' values, depending on fillna=False)
    # ta.trend.ema_indicator with fillna=False will have NaNs for the first `period-1` values
    # For period=3, first 2 values are NaN. 3rd value is the start.
    # Let's check the first non-NaN value
    # For window=3, the first valid EMA is at index 2 (0-indexed)
    # The ta library's EMA calculation starts after the window.
    # For window=3, the first valid EMA is at index 2.
    # Let's check the last value, which should be a valid EMA.
    assert not np.isnan(df_result["ema_3"].iloc[-1])


def test_calculate_ema_insufficient_data(insufficient_dataframe):
    df_result = calculate_ema(insufficient_dataframe.copy(), period=10)
    assert "ema_10" in df_result.columns
    assert df_result["ema_10"].isnull().all()


def test_calculate_ema_value_error(sample_dataframe):
    with pytest.raises(ValueError):
        calculate_ema(sample_dataframe.copy(), column="non_existent_column")


# Test for calculate_rsi
def test_calculate_rsi_basic(sample_dataframe):
    df_result = calculate_rsi(sample_dataframe.copy(), period=3)
    assert "rsi_3" in df_result.columns
    assert not df_result["rsi_3"].isnull().all()
    assert (df_result["rsi_3"].dropna() >= 0).all() and (
        df_result["rsi_3"].dropna() <= 100
    ).all()


def test_calculate_rsi_insufficient_data(insufficient_dataframe):
    df_result = calculate_rsi(insufficient_dataframe.copy(), period=10)
    assert "rsi_10" in df_result.columns
    assert df_result["rsi_10"].isnull().all()


def test_calculate_rsi_value_error(sample_dataframe):
    with pytest.raises(ValueError):
        calculate_rsi(sample_dataframe.copy(), column="non_existent_column")


# Test for calculate_macd
def test_calculate_macd_basic(sample_dataframe):
    df_result = calculate_macd(sample_dataframe.copy())
    assert "macd_12_26" in df_result.columns
    assert "macd_signal_12_26_9" in df_result.columns
    assert "macd_diff_12_26_9" in df_result.columns
    assert not df_result["macd_12_26"].isnull().all()
    assert not df_result["macd_signal_12_26_9"].isnull().all()
    assert not df_result["macd_diff_12_26_9"].isnull().all()


def test_calculate_macd_insufficient_data(insufficient_dataframe):
    df_result = calculate_macd(insufficient_dataframe.copy())
    assert df_result["macd_12_26"].isnull().all()
    assert df_result["macd_signal_12_26_9"].isnull().all()
    assert df_result["macd_diff_12_26_9"].isnull().all()


def test_calculate_macd_value_error(sample_dataframe):
    with pytest.raises(ValueError):
        calculate_macd(sample_dataframe.copy(), column="non_existent_column")


# Test for calculate_ehlers_fisher_transform
def test_calculate_ehlers_fisher_transform_basic(sample_dataframe):
    df_result = calculate_ehlers_fisher_transform(sample_dataframe.copy())
    assert "fisher_9" in df_result.columns
    assert "fisher_signal_9" in df_result.columns
    assert not df_result["fisher_9"].isnull().all()
    assert not df_result["fisher_signal_9"].isnull().all()
    # Fisher values can be large, but should not be infinite unless there's an issue
    assert not np.isinf(df_result["fisher_9"].dropna()).any()


def test_calculate_ehlers_fisher_transform_insufficient_data(insufficient_dataframe):
    df_result = calculate_ehlers_fisher_transform(
        insufficient_dataframe.copy(), period=10
    )
    assert df_result["fisher_10"].isnull().all()
    assert df_result["fisher_signal_10"].isnull().all()


def test_calculate_ehlers_fisher_transform_value_error(sample_dataframe):
    with pytest.raises(ValueError):
        calculate_ehlers_fisher_transform(
            sample_dataframe.copy(), column="non_existent_column"
        )


# Test for calculate_supertrend
def test_calculate_supertrend_basic(sample_dataframe):
    df_result = calculate_supertrend(sample_dataframe.copy(), period=7, multiplier=3.0)
    assert "supertrend" in df_result.columns
    assert "supertrend_direction" in df_result.columns
    assert not df_result["supertrend"].isnull().all()
    assert not df_result["supertrend_direction"].isnull().all()
    # Direction should be 1 or -1
    assert df_result["supertrend_direction"].dropna().isin([1, -1]).all()


def test_calculate_supertrend_insufficient_data(insufficient_dataframe):
    df_result = calculate_supertrend(insufficient_dataframe.copy(), period=10)
    assert df_result["supertrend"].isnull().all()
    assert df_result["supertrend_direction"].isnull().all()


def test_calculate_supertrend_value_error_missing_columns(sample_dataframe):
    df_missing_high = sample_dataframe.drop(columns=["high"])
    with pytest.raises(ValueError):
        calculate_supertrend(df_missing_high.copy())

    df_missing_low = sample_dataframe.drop(columns=["low"])
    with pytest.raises(ValueError):
        calculate_supertrend(df_missing_low.copy())

    df_missing_close = sample_dataframe.drop(columns=["close"])
    with pytest.raises(ValueError):
        calculate_supertrend(df_missing_close.copy())


# Test for trend change detection (conceptual, requires specific data)
def test_calculate_supertrend_trend_change():
    # Create a DataFrame that clearly shows a trend change
    data = {
        "open": [10, 11, 12, 13, 12, 11, 10, 9, 10, 11],
        "high": [11, 12, 13, 14, 13, 12, 11, 10, 11, 12],
        "low": [9, 10, 11, 12, 11, 10, 9, 8, 9, 10],
        "close": [10.5, 11.5, 12.5, 13.5, 11.5, 10.5, 9.5, 8.5, 10.5, 11.5],
    }
    df_trend_change = pd.DataFrame(data)

    df_result = calculate_supertrend(df_trend_change.copy(), period=3, multiplier=2.0)

    # Expect a change in direction. The exact index depends on the data and period/multiplier.
    # We'll check if both 1 and -1 appear in the direction column after NaNs.
    directions = df_result["supertrend_direction"].dropna().unique()
    assert 1 in directions and -1 in directions, (
        "Supertrend direction should show both uptrend and downtrend."
    )
