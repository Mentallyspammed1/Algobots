import numpy as np
import pandas as pd
import logging
from typing import Optional, Tuple, Dict, Callable
from decimal import Decimal

# Set up a logger for the indicator module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # Set default log level for the module

# --- Core Helper Functions ---

def calculate_sma(data: pd.Series, period: int) -> pd.Series:
    """Calculates Simple Moving Average."""
    if period <= 0: return pd.Series(np.nan, index=data.index)
    try:
        return data.rolling(window=period).mean()
    except Exception as e:
        logger.warning(f"Error calculating SMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)

def calculate_ema(data: pd.Series, period: int) -> pd.Series:
    """Calculates Exponential Moving Average."""
    if period <= 0: return pd.Series(np.nan, index=data.index)
    try:
        return data.ewm(span=period, adjust=False).mean()
    except Exception as e:
        logger.warning(f"Error calculating EMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)

def calculate_dema(data: pd.Series, period: int) -> pd.Series:
    """Calculates Double Exponential Moving Average (DEMA)."""
    if period <= 0: return pd.Series(np.nan, index=data.index)
    try:
        ema1 = calculate_ema(data, period)
        ema2 = calculate_ema(ema1, period)
        return 2 * ema1 - ema2
    except Exception as e:
        logger.warning(f"Error calculating DEMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)

def calculate_vwma(close_data: pd.Series, volume_data: pd.Series, period: int) -> pd.Series:
    """Calculates Volume Weighted Moving Average (VWMA)."""
    if period <= 0: return pd.Series(np.nan, index=close_data.index)
    try:
        typical_price = close_data
        vwap_series = (typical_price * volume_data).rolling(window=period).sum() / volume_data.rolling(window=period).sum()
        return vwap_series
    except Exception as e:
        logger.warning(f"Error calculating VWMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=close_data.index)

def calculate_kama(data: pd.Series, period: int, fast_period: int, slow_period: int) -> pd.Series:
    """Calculates Kaufman's Adaptive Moving Average (KAMA)."""
    if period <= 0 or fast_period <= 0 or slow_period <= 0: return pd.Series(np.nan, index=data.index)
    try:
        change = data.diff(period).abs()
        volatility = data.diff().abs().rolling(window=period).sum()
        er = change / volatility.replace(0, 1e-9).clip(lower=1e-9)
        er = er.fillna(0).clip(0, 1)

        sc_fast = 2 / (fast_period + 1)
        sc_slow = 2 / (slow_period + 1)
        sc = (er * (sc_fast - sc_slow) + sc_slow)**2

        kama = pd.Series(np.nan, index=data.index)
        first_valid_idx = sc.first_valid_index()
        if first_valid_idx is None: return pd.Series(np.nan, index=data.index)
        
        kama.iloc[data.index.get_loc(first_valid_idx)] = data.loc[first_valid_idx]

        for i in range(data.index.get_loc(first_valid_idx) + 1, len(data)):
             idx = data.index[i]
             prev_idx = data.index[i-1]
             if pd.notna(sc.loc[idx]) and pd.notna(kama.loc[prev_idx]):
                  kama.loc[idx] = kama.loc[prev_idx] + sc.loc[idx] * (data.loc[idx] - kama.loc[prev_idx])
             else:
                  kama.loc[idx] = kama.loc[prev_idx]

        return kama.reindex(data.index)
    except Exception as e:
        logger.warning(f"Error calculating KAMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)

def calculate_rsi(data: pd.Series, period: int) -> pd.Series:
    """Calculates Relative Strength Index (RSI)."""
    if period <= 0: return pd.Series(np.nan, index=data.index)
    try:
        delta = data.diff()
        gain = (delta.where(delta > 0)).fillna(0)
        loss = (-delta.where(delta < 0)).fillna(0)

        avg_gain = gain.ewm(span=period, adjust=False).mean()
        avg_loss = loss.ewm(span=period, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except Exception as e:
        logger.warning(f"Error calculating RSI({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)

def calculate_stoch_rsi(data: pd.Series, period: int, k_period: int, d_period: int) -> Tuple[pd.Series, pd.Series]:
    """Calculates Stochastic RSI."""
    if period <= 0 or k_period <= 0 or d_period <= 0: return pd.Series(np.nan), pd.Series(np.nan)
    try:
        rsi = calculate_rsi(data, period=period)
        min_rsi = rsi.rolling(window=period).min()
        max_rsi = rsi.rolling(window=period).max()
        denominator = (max_rsi - min_rsi).replace(0, np.nan) 

        stoch_rsi_raw = 100 * ((rsi - min_rsi) / denominator)
        stoch_rsi_raw = stoch_rsi_raw.fillna(0).clip(0, 100) 

        stoch_k = stoch_rsi_raw.rolling(window=k_period).mean()
        stoch_d = stoch_k.rolling(window=d_period).mean()

        return stoch_k.reindex(data.index), stoch_d.reindex(data.index)
    except Exception as e:
        logger.warning(f"Error calculating Stochastic RSI: {e}", exc_info=True)
        return pd.Series(np.nan), pd.Series(np.nan)

def calculate_cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Calculates Commodity Channel Index (CCI) - Pure Python/Pandas implementation."""
    if period <= 0: return pd.Series(np.nan, index=high.index)
    try:
        typical_price = (high + low + close) / 3
        tp_mean = typical_price.rolling(window=period).mean()
        tp_mad = typical_price.rolling(window=period).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)

        denominator = (0.015 * tp_mad).replace(0, np.nan)
        cci = (typical_price - tp_mean) / denominator
        return cci.reindex(high.index)
    except Exception as e:
        logger.warning(f"Error calculating CCI({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)

def calculate_williams_r(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Calculates Williams %R."""
    if period <= 0: return pd.Series(np.nan, index=high.index)
    try:
        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()
        denominator = (highest_high - lowest_low).replace(0, np.nan)
        wr = -100 * ((highest_high - close) / denominator)
        return wr.reindex(high.index)
    except Exception as e:
        logger.warning(f"Error calculating Williams %R({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)

def calculate_mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int) -> pd.Series:
    """Calculates Money Flow Index (MFI)."""
    if period <= 0: return pd.Series(np.nan, index=high.index)
    try:
        typical_price = (high + low + close) / 3
        money_flow = typical_price * volume
        tp_diff = typical_price.diff()
        positive_mf = money_flow.where(tp_diff > 0, 0)
        negative_mf = money_flow.where(tp_diff < 0, 0).abs()

        positive_mf_sum = positive_mf.rolling(window=period).sum()
        negative_mf_sum = negative_mf.rolling(window=period).sum()

        money_ratio = (positive_mf_sum / negative_mf_sum.replace(0, np.nan)).fillna(0)
        mfi = 100 - (100 / (1 + money_ratio))
        return mfi.reindex(high.index)
    except Exception as e:
        logger.warning(f"Error calculating MFI({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)

def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Calculates Average True Range (ATR)."""
    if period <= 0: return pd.Series(np.nan, index=high.index)
    try:
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = true_range.ewm(span=period, adjust=False).mean()
        return atr.reindex(high.index)
    except Exception as e:
        logger.warning(f"Error calculating ATR({period}): {e}", exc_info=True)
        return pd