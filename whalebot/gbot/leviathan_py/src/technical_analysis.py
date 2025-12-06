"""
Pure, vectorized Technical Analysis functions using NumPy and pandas.
Corresponds to the `TA` class in `aimm.cjs`.
"""
from typing import Optional
import numpy as np
import pandas as pd

# Define a common small number to avoid division by zero
EPSILON = 1e-9

def sma(source: np.ndarray, period: int) -> np.ndarray:
    """Calculates Simple Moving Average (SMA) using pandas for efficiency."""
    if period <= 0 or source.size < period:
        return np.full_like(source, np.nan)
    
    s = pd.Series(source)
    return s.rolling(window=period, min_periods=period).mean().to_numpy()

def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Calculates Average True Range (ATR)."""
    if period <= 0 or high.size < period:
        return np.full_like(high, np.nan)

    high_low = high - low
    high_close_prev = np.abs(high - np.roll(close, 1))
    low_close_prev = np.abs(low - np.roll(close, 1))

    tr = np.maximum.reduce([high_low, high_close_prev, low_close_prev])
    # For the first value, np.roll wraps around, which is incorrect for TR.
    # We recalculate the first TR value correctly.
    tr[0] = high[0] - low[0]

    # Use pandas ewm to calculate the Wilder's smoothing for ATR
    atr_series = pd.Series(tr).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    return atr_series.to_numpy()

def vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, lookback: int = 96) -> Optional[float]:
    """
    Calculates the Volume-Weighted Average Price (VWAP) for a rolling window.
    Corresponds to the session-based VWAP in aimm.cjs.
    """
    if close.size < lookback:
        lookback = close.size
    if lookback == 0:
        return None

    source_slice = np.s_[-lookback:]
    h_sliced, l_sliced, c_sliced, v_sliced = high[source_slice], low[source_slice], close[source_slice], volume[source_slice]

    typical_price = (h_sliced + l_sliced + c_sliced) / 3
    cumulative_pv = np.sum(typical_price * v_sliced)
    cumulative_v = np.sum(v_sliced)
    
    return cumulative_pv / cumulative_v if cumulative_v > 0 else close[-1]

def fisher(high: np.ndarray, low: np.ndarray, period: int = 9) -> np.ndarray:
    """
    Calculates the Fisher Transform, vectorized with NumPy.
    """
    if period <= 0 or high.size < period:
        return np.full_like(high, np.nan)
    
    # Create pandas Series for easier rolling operations
    high_s = pd.Series(high)
    low_s = pd.Series(low)
    
    # Calculate min/max over the rolling period
    min_low = low_s.rolling(window=period, min_periods=period).min()
    max_high = high_s.rolling(window=period, min_periods=period).max()
    
    mid_price = (high + low) / 2.0
    
    rng = max_high - min_low
    # Avoid division by zero
    rng[rng < EPSILON] = EPSILON
    
    # Calculate the raw value, normalized between -1 and 1
    raw = 2 * ((mid_price - min_low) / rng) - 1
    
    # Smooth the raw value (equivalent to the JS version's smoothing)
    # val[i] = 0.33 * raw + 0.67 * val[i-1] -> This is an EMA
    value = pd.Series(raw).ewm(alpha=(1.0/3.0), adjust=False).mean().to_numpy()

    # Clip values to prevent issues with log
    value = np.clip(value, -0.999, 0.999)
    
    # Fisher Transform calculation
    # fish[i] = 0.5 * log((1 + val) / (1 - val)) + 0.5 * fish[i-1] -> Another EMA
    fish_raw = 0.5 * np.log((1 + value) / (1 - value))
    fish = pd.Series(fish_raw).ewm(alpha=0.5, adjust=False).mean().to_numpy()
    
    # Set initial NaNs where calculation isn't possible
    fish[:period-1] = np.nan
    
    return fish
