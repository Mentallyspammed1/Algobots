import logging
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any

import numpy as np
import pandas as pd

# --- Constants ---
MIN_DATA_POINTS_TR = 2
MIN_DATA_POINTS_SMOOTHER = 2
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR = 2
MIN_DATA_POINTS_VOLATILITY = 2
MIN_DATA_POINTS_KAMA = 2
MIN_DATA_POINTS_SMOOTHER_INIT = 2
MIN_CANDLESTICK_PATTERNS_BARS = 2

# Initialize a logger
logger = logging.getLogger(__name__)

# --- Helper Functions for Precision and Safety ---

def _safe_divide_decimal(numerator: Decimal, denominator: Decimal, default: Decimal = Decimal("0")) -> Decimal:
    """Safely divides two Decimals, returning a default if denominator is zero or invalid."""
    try:
        if denominator.is_zero() or denominator.is_nan() or numerator.is_nan():
            return default
        return numerator / denominator
    except InvalidOperation:
        return default

def _clean_series(series: pd.Series | None, df_index: pd.Index, default_val: Any = np.nan) -> pd.Series:
    """Ensures a series is clean, re-indexed, and handles NaNs."""
    if series is None:
        return pd.Series(default_val, index=df_index)

    cleaned = series.reindex(df_index) # Re-index to match original DataFrame

    if not pd.isna(default_val): # Fill NaNs if a default is specified
        cleaned = cleaned.fillna(default_val)

    return cleaned

# --- Core Indicator Calculations ---

def calculate_sma(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculates the Simple Moving Average (SMA) for the 'close' price."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)
    return _clean_series(df["close"].rolling(window=period).mean(), df.index)

def calculate_ema(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculates the Exponential Moving Average (EMA) for the 'close' price."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)
    return _clean_series(df["close"].ewm(span=period, adjust=False).mean(), df.index)

def calculate_true_range(df: pd.DataFrame) -> pd.Series:
    """Calculates the True Range (TR), a component for ATR."""
    if len(df) < MIN_DATA_POINTS_TR:
        return pd.Series(np.nan, index=df.index)

    high_low = df["high"] - df["low"]
    high_prev_close = (df["high"] - df["close"].shift()).abs()
    low_prev_close = (df["low"] - df["close"].shift()).abs()

    # Take the maximum of the three ranges
    tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    return _clean_series(tr, df.index)

def calculate_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculates the Average True Range (ATR)."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)

    tr = calculate_true_range(df)
    if tr.isnull().all(): # If TR calculation failed or returned all NaNs
        return pd.Series(np.nan, index=df.index)

    atr = tr.ewm(span=period, adjust=False).mean()
    return _clean_series(atr, df.index)

def calculate_super_smoother(df: pd.DataFrame, series: pd.Series, period: int) -> pd.Series:
    """Applies Ehlers SuperSmoother filter to reduce lag and noise."""
    if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER:
        return pd.Series(np.nan, index=df.index)

    series_clean = pd.to_numeric(series, errors="coerce").dropna() # Clean input series
    if len(series_clean) < MIN_DATA_POINTS_SMOOTHER_INIT:
        return pd.Series(np.nan, index=df.index)

    # Calculate filter constants
    a1 = np.exp(-np.sqrt(2) * np.pi / period)
    b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
    c1 = (1 - b1 + a1**2) / 2
    c2 = b1 - 2 * a1**2
    c3 = a1**2

    filt = pd.Series(np.nan, index=series_clean.index) # Initialize with NaN

    # Initialize first two points safely
    if len(series_clean) >= 1: filt.iloc[0] = series_clean.iloc[0]
    if len(series_clean) >= 2: filt.iloc[1] = (series_clean.iloc[0] + series_clean.iloc[1]) / 2

    # Apply the SuperSmoother formula
    for i in range(2, len(series_clean)):
        filt.iloc[i] = (
            (c1 * (series_clean.iloc[i] + series_clean.iloc[i-1]))
            + c2 * filt.iloc[i-1]
            - c3 * filt.iloc[i-2]
        )

    return _clean_series(filt, df.index) # Re-index to original df index

def calculate_ehlers_supertrend(
    df: pd.DataFrame,
    period: int,
    multiplier: float,
) -> pd.DataFrame | None:
    """Calculates SuperTrend using Ehlers SuperSmoother for price and volatility."""
    required_len = period * 3 # Need sufficient data for smoothing and trend calculation
    # Ensure ATR is available and has valid data points
    if len(df) < required_len or "ATR" not in df.columns or df["ATR"].isnull().all():
        logger.debug(f"Not enough data or missing ATR for Ehlers SuperTrend (Need {required_len} bars).")
        return None

    hl2 = (df["high"] + df["low"]) / 2 # Midpoint price
    smoothed_price = calculate_super_smoother(df, hl2, period)
    if smoothed_price.isnull().all(): return None

    smoothed_atr = calculate_super_smoother(df, df["ATR"], period)
    if smoothed_atr.isnull().all(): return None

    # Create a temporary DataFrame for calculations, dropping NaNs from smoothed values
    calc_df = pd.DataFrame({
        "close": df["close"], "smoothed_price": smoothed_price, "smoothed_atr": smoothed_atr
    }).dropna()

    if calc_df.empty: return None # Exit if no valid data after cleaning

    # Calculate upper and lower bands
    upper_band = calc_df["smoothed_price"] + multiplier * calc_df["smoothed_atr"]
    lower_band = calc_df["smoothed_price"] - multiplier * calc_df["smoothed_atr"]

    direction = pd.Series(0, index=calc_df.index, dtype=int) # Store trend direction: 1=UP, -1=DOWN, 0=SIDEWAYS/UNDECIDED
    supertrend = pd.Series(np.nan, index=calc_df.index) # Store the SuperTrend line values

    # Initialize the first valid point
    first_valid_idx = calc_df.first_valid_index()
    if first_valid_idx is None: return None

    initial_close = calc_df.loc[first_valid_idx, "close"]
    initial_upper, initial_lower = upper_band.loc[first_valid_idx], lower_band.loc[first_valid_idx]

    # Determine initial trend direction and SuperTrend value
    if initial_close > initial_upper:
        direction.loc[first_valid_idx] = 1; supertrend.loc[first_valid_idx] = initial_lower
    elif initial_close < initial_lower:
        direction.loc[first_valid_idx] = -1; supertrend.loc[first_valid_idx] = initial_upper
    else: # Price within bands, initialize conservatively
        direction.loc[first_valid_idx] = 0
        supertrend.loc[first_valid_idx] = initial_lower # Default to lower band

    # Iterate through the rest of the DataFrame
    for i in calc_df.index[calc_df.index.get_loc(first_valid_idx) + 1:]:
        # Get previous values safely
        prev_idx = calc_df.index[calc_df.index.get_loc(i) - 1]
        prev_direction = direction.loc[prev_idx]
        prev_supertrend = supertrend.loc[prev_idx]
        curr_close, curr_upper, curr_lower = calc_df.loc[i, "close"], upper_band.loc[i], lower_band.loc[i]

        # Calculate current PSAR based on previous trend and EP
        current_psar = np.nan
        if prev_direction == 1: # Previous was UP
            current_psar = prev_supertrend + af * (prev_ep - prev_supertrend) # Note: EP logic is simplified here for SuperTrend
        elif prev_direction == -1: # Previous was DOWN
            current_psar = prev_supertrend - af * (prev_supertrend - prev_ep)
        else: # Undecided, use previous SuperTrend as a base
            current_psar = prev_supertrend

        # Determine trend reversal and update direction/SuperTrend value
        reverse = False
        if prev_direction == 1 and curr_close < prev_supertrend: # Bullish trend reversed down
            direction.loc[i] = -1; current_psar = curr_upper; reverse = True
        elif prev_direction == -1 and curr_close > prev_supertrend: # Bearish trend reversed up
            direction.loc[i] = 1; current_psar = curr_lower; reverse = True
        else: # No reversal, continue previous trend
            direction.loc[i] = prev_direction

        # Adjust SuperTrend value based on trend and bands
        if reverse:
            # Update EP for next calculation (simplified: use current band or price)
            if direction.loc[i] == 1: EP = curr_lower
            else: EP = curr_upper
        elif direction.loc[i] == 1: # Continue UP trend
            EP = curr_lower
        elif direction.loc[i] == -1: # Continue DOWN trend
            EP = curr_upper
        else: # Undecided, keep previous EP
            EP = prev_ep

        # Final SuperTrend value is the max/min of current band and previous SuperTrend
        if direction.loc[i] == 1: current_psar = max(EP, prev_supertrend)
        elif direction.loc[i] == -1: current_psar = min(EP, prev_supertrend)
        # else: current_psar remains as calculated or previous value if no clear direction

        supertrend.loc[i] = current_psar

    result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
    return result.reindex(df.index) # Reindex back to original df index

def calculate_macd(
    df: pd.DataFrame,
    fast_period: int,
    slow_period: int,
    signal_period: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates MACD Line, Signal Line, and Histogram."""
    if len(df) < slow_period + signal_period:
        return (pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index),
                pd.Series(np.nan, index=df.index))

    ema_fast = df["close"].ewm(span=fast_period, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow_period, adjust=False).mean()

    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    return (_clean_series(macd_line, df.index), _clean_series(signal_line, df.index),
            _clean_series(histogram, df.index))

def calculate_rsi(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculates the Relative Strength Index (RSI)."""
    if len(df) <= period:
        return pd.Series(np.nan, index=df.index)

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

    # Safe division for RS, handle zero loss case
    rs = _safe_divide_decimal(avg_gain, avg_loss.replace(0, Decimal("0")), default=Decimal("0"))
    rsi = 100 - (100 / (1 + rs))

    return _clean_series(rsi, df.index)

def calculate_stoch_rsi(
    df: pd.DataFrame,
    period: int,
    k_period: int,
    d_period: int,
) -> tuple[pd.Series, pd.Series]:
    """Calculates the Stochastic RSI."""
    if len(df) <= period:
        return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)

    rsi = calculate_rsi(df, period)
    if rsi.isnull().all(): # If base RSI is all NaN, return NaNs
        return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)

    lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
    highest_rsi = rsi.rolling(window=period, min_periods=period).max()

    # Handle zero denominator for Stochastic calculation
    denominator = highest_rsi - lowest_rsi
    denominator[denominator == 0] = np.nan # Replace zeros with NaN for safe division

    stoch_rsi_k_raw = (_safe_divide(rsi - lowest_rsi, denominator)) * 100
    stoch_rsi_k_raw = stoch_rsi_k_raw.fillna(0).clip(0, 100) # Fill NaNs and clip to [0, 100]

    stoch_rsi_k = stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period).mean().fillna(0)
    stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean().fillna(0)

    return _clean_series(stoch_rsi_k, df.index), _clean_series(stoch_rsi_d, df.index)

def calculate_adx(df: pd.DataFrame, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates the Average Directional Index (ADX), +DI, and -DI."""
    if len(df) < period * 2: # Need sufficient history for ADX calculation
        return (pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index),
                pd.Series(np.nan, index=df.index))

    tr = calculate_true_range(df)
    if tr.isnull().all(): return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

    plus_dm = df["high"].diff()
    minus_dm = -df["low"].diff()

    # Initialize DM series with zeros
    plus_dm_final = pd.Series(0.0, index=df.index)
    minus_dm_final = pd.Series(0.0, index=df.index)

    # Determine positive and negative directional movement using vectorized operations
    cond_plus = (plus_dm > minus_dm) & (plus_dm > 0)
    plus_dm_final[cond_plus] = plus_dm[cond_plus]
    cond_minus = (minus_dm > plus_dm) & (minus_dm > 0)
    minus_dm_final[cond_minus] = minus_dm[cond_minus]

    # Smoothed True Range, +DM, -DM using EMA
    atr = tr.ewm(span=period, adjust=False).mean()
    # Calculate Directional Indicators (+DI, -DI), handling division by zero
    plus_di = (_safe_divide(plus_dm_final.ewm(span=period, adjust=False).mean(), atr.replace(0, np.nan))) * 100
    minus_di = (_safe_divide(minus_dm_final.ewm(span=period, adjust=False).mean(), atr.replace(0, np.nan))) * 100

    # DX calculation (Directional Index)
    di_diff = abs(plus_di - minus_di)
    di_sum = plus_di + minus_di
    dx = (_safe_divide(di_diff, di_sum.replace(0, np.nan))) * 100

    # ADX calculation (smoothed DX)
    adx = dx.ewm(span=period, adjust=False).mean()

    return (_clean_series(adx, df.index), _clean_series(plus_di, df.index),
            _clean_series(minus_di, df.index))

def calculate_bollinger_bands(
    df: pd.DataFrame,
    period: int,
    std_dev: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates Bollinger Bands (Upper, Middle, Lower)."""
    if len(df) < period:
        return (pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index),
                pd.Series(np.nan, index=df.index))

    middle_band = df["close"].rolling(window=period, min_periods=period).mean()
    std = df["close"].rolling(window=period, min_periods=period).std()

    upper_band = middle_band + (std * std_dev)
    lower_band = middle_band - (std * std_dev)

    return (_clean_series(upper_band, df.index), _clean_series(middle_band, df.index),
            _clean_series(lower_band, df.index))

def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """Calculates the Volume Weighted Average Price (VWAP)."""
    if df.empty or "volume" not in df.columns or "close" not in df.columns:
        return pd.Series(np.nan, index=df.index)

    df_temp = df.copy()
    df_temp["volume"] = pd.to_numeric(df_temp["volume"], errors='coerce').fillna(0)
    df_temp = df_temp[df_temp["volume"] > 0] # Filter for positive volume

    if df_temp.empty: return pd.Series(np.nan, index=df.index)

    typical_price = (df_temp["high"] + df_temp["low"] + df_temp["close"]) / 3
    pv = typical_price * df_temp["volume"] # Price * Volume

    cumulative_pv = pv.cumsum()
    cumulative_vol = df_temp["volume"].cumsum()

    vwap = _safe_divide_decimal(cumulative_pv, cumulative_vol.replace(0, Decimal("0")))

    return _clean_series(vwap, df.index)

def calculate_cci(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculates the Commodity Channel Index (CCI)."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)

    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = tp.rolling(window=period, min_periods=period).mean()

    # Mean Absolute Deviation (MAD)
    mad = tp.rolling(window=period, min_periods=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=False)

    # CCI calculation, safe division
    cci = _safe_divide_decimal((tp - sma_tp), (mad.replace(0, Decimal("0")) / Decimal("0.015")))

    return _clean_series(cci, df.index)

def calculate_williams_r(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculates Williams %R."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)

    highest_high = df["high"].rolling(window=period, min_periods=period).max()
    lowest_low = df["low"].rolling(window=period, min_periods=period).min()

    denominator = highest_high - lowest_low
    # Safe division for Williams %R
    wr = -100 * _safe_divide_decimal((highest_high - df["close"]), denominator.replace(0, Decimal("0")))

    return _clean_series(wr, df.index)

def calculate_ichimoku_cloud(
    df: pd.DataFrame,
    tenkan_period: int,
    kijun_period: int,
    senkou_span_b_period: int,
    chikou_span_offset: int,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Calculates Ichimoku Cloud components: Tenkan-sen, Kijun-sen, Senkou Span A/B, Chikou Span."""
    required_len = max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset
    if len(df) < required_len:
        return (pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index),
                pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index),
                pd.Series(np.nan, index=df.index))

    # Calculate base lines (Tenkan, Kijun)
    tenkan_sen = ((df["high"].rolling(window=tenkan_period).max() + df["low"].rolling(window=tenkan_period).min()) / 2).shift(kijun_period)
    kijun_sen = ((df["high"].rolling(window=kijun_period).max() + df["low"].rolling(window=kijun_period).min()) / 2).shift(kijun_period)

    # Calculate Senkou Spans (shifted forward)
    senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
    senkou_span_b = ((df["high"].rolling(window=senkou_span_b_period).max() + df["low"].rolling(window=senkou_span_b_period).min()) / 2).shift(kijun_period)

    # Calculate Chikou Span (shifted backward relative to current price)
    chikou_span = df["close"].shift(-chikou_span_offset)

    return (tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span)

def calculate_mfi(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculates the Money Flow Index (MFI)."""
    if len(df) <= period:
        return pd.Series(np.nan, index=df.index)

    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    money_flow = typical_price * df["volume"]
    price_diff = typical_price.diff()

    # Calculate positive and negative money flow
    positive_flow = money_flow.where(price_diff > 0, 0)
    negative_flow = money_flow.where(price_diff < 0, 0)

    positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
    negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

    # Calculate Money Flow Ratio, handling division by zero
    mf_ratio = _safe_divide_decimal(positive_mf_sum, negative_mf_sum.replace(0, Decimal("0")))
    mfi = 100 - (100 / (1 + mf_ratio))

    return _clean_series(mfi, df.index)

def calculate_obv(df: pd.DataFrame, ema_period: int) -> tuple[pd.Series, pd.Series]:
    """Calculates On-Balance Volume (OBV) and its EMA."""
    if len(df) < MIN_DATA_POINTS_OBV:
        return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)

    # Calculate OBV direction change
    obv_direction = np.sign(df["close"].diff().fillna(0))
    obv = (obv_direction * df["volume"]).cumsum() # Cumulative sum for OBV

    obv_ema = obv.ewm(span=ema_period, adjust=False).mean() # EMA of OBV

    return _clean_series(obv, df.index), _clean_series(obv_ema, df.index)

def calculate_cmf(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculates the Chaikin Money Flow (CMF)."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)

    high_low_range = df["high"] - df["low"]
    # Money Flow Multiplier (MFM), safe division
    mfm = _safe_divide_decimal(((df["close"] - df["low"]) - (df["high"] - df["close"])), high_low_range.replace(0, Decimal("0")), default=Decimal("0.0"))
    mfm = mfm.fillna(0.0) # Fill potential NaNs from division

    mfv = mfm * df["volume"] # Money Flow Volume

    volume_sum = df["volume"].rolling(window=period).sum()
    # CMF calculation, safe division
    cmf = _safe_divide_decimal(mfv.rolling(window=period).sum(), volume_sum.replace(0, Decimal("0")))
    cmf = cmf.fillna(0.0) # Fill NaNs from division

    return _clean_series(cmf, df.index)

def calculate_psar(
    df: pd.DataFrame,
    acceleration: float,
    max_acceleration: float,
) -> tuple[pd.Series, pd.Series]:
    """Calculates the Parabolic SAR (Stop and Reverse) and trend direction."""
    if len(df) < MIN_DATA_POINTS_PSAR:
        return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)

    psar = pd.Series(np.nan, index=df.index)
    bull = pd.Series(True, index=df.index) # Stores trend direction (True for bullish)
    af = pd.Series(acceleration, index=df.index) # Acceleration Factor
    ep = pd.Series(np.nan, index=df.index) # Extreme Point

    # Initialize trend and EP based on first two bars to establish a starting point
    if len(df) >= 2:
        # If price increased from bar 0 to 1, assume bullish start
        if df["close"].iloc[0] < df["close"].iloc[1]:
            bull.iloc[0], ep.iloc[0] = True, df["high"].iloc[0]
        else: # Otherwise, assume bearish start
            bull.iloc[0], ep.iloc[0] = False, df["low"].iloc[0]
    elif len(df) == 1: # Handle single bar case
        bull.iloc[0], ep.iloc[0] = True, df["high"].iloc[0] # Default to bullish

    # Iterate through the DataFrame to calculate PSAR
    for i in range(1, len(df)):
        prev_bull = bull.iloc[i - 1]
        prev_psar = psar.iloc[i - 1]
        prev_af = af.iloc[i - 1]
        prev_ep = ep.iloc[i - 1]

        current_low, current_high = df["low"].iloc[i], df["high"].iloc[i]

        # Calculate current PSAR based on previous trend and EP
        if prev_bull: current_psar = prev_psar + prev_af * (prev_ep - prev_psar)
        else: current_psar = prev_psar - prev_af * (prev_psar - prev_ep)

        # Check for trend reversal conditions
        reverse = False
        if prev_bull and current_low < current_psar: # Bullish trend reversed down
            bull.iloc[i] = False; reverse = True
        elif not prev_bull and current_high > current_psar: # Bearish trend reversed up
            bull.iloc[i] = True; reverse = True
        else: # Continue previous trend
            bull.iloc[i] = prev_bull

        # Update EP and AF
        if reverse:
            af.iloc[i] = acceleration # Reset AF
            ep.iloc[i] = current_high if bull.iloc[i] else current_low # New EP based on reversal direction
            # Adjust PSAR if it crossed the price during reversal
            if bull.iloc[i]: current_psar = min(current_low, df["low"].iloc[i-1]) # PSAR below Low
            else: current_psar = max(current_high, df["high"].iloc[i-1]) # PSAR above High
        else:
            ep.iloc[i] = prev_ep # Keep previous EP if no reversal
            if bull.iloc[i]: # Continue bullish trend
                if current_high > prev_ep: # New high reached, update EP and accelerate AF
                    ep.iloc[i] = current_high
                    af.iloc[i] = min(prev_af + acceleration, max_acceleration)
                else: af.iloc[i] = prev_af # Keep previous AF
                current_psar = min(current_psar, current_low, df["low"].iloc[i-1]) # PSAR below lowest low
            else: # Continue bearish trend
                if current_low < prev_ep: # New low reached, update EP and accelerate AF
                    ep.iloc[i] = current_low
                    af.iloc[i] = min(prev_af + acceleration, max_acceleration)
                else: af.iloc[i] = prev_af # Keep previous AF
                current_psar = max(current_psar, current_high, df["high"].iloc[i-1]) # PSAR above highest high

        psar.iloc[i] = current_psar

    # Determine PSAR direction (1 for bullish, -1 for bearish)
    direction = pd.Series(0, index=df.index, dtype=int)
    direction[psar < df["close"]] = 1 # PSAR below close indicates bullish trend
    direction[psar > df["close"]] = -1 # PSAR above close indicates bearish trend

    return (_clean_series(psar, df.index), _clean_series(direction, df.index))

def calculate_fibonacci_levels(df: pd.DataFrame, window: int) -> dict[str, Decimal] | None:
    """Calculates Fibonacci retracement levels based on the high-low range of the last 'window' periods."""
    if len(df) < window: return None

    # Find the highest high and lowest low within the lookback window
    recent_high = df["high"].iloc[-window:].max()
    recent_low = df["low"].iloc[-window:].min()
    diff = recent_high - recent_low

    if diff <= 0: return None # Prevent calculations if range is invalid

    # Define Fibonacci levels as Decimals for precision
    fib_levels = {
        "0.0%": Decimal(str(recent_high)), # High
        "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
        "100.0%": Decimal(str(recent_low)), # Low
    }
    return fib_levels

def calculate_fibonacci_pivot_points(df: pd.DataFrame) -> dict[str, float] | None:
    """Calculates Fibonacci Pivot Points (Pivot, R1, R2, S1, S2)."""
    if df.empty or len(df) < 2: return None # Need at least previous bar's data

    # Use the previous bar's OHLC for calculation
    prev_high, prev_low, prev_close = df["high"].iloc[-2], df["low"].iloc[-2], df["close"].iloc[-2]
    # Ensure previous data is valid
    if pd.isna(prev_high) or pd.isna(prev_low) or pd.isna(prev_close): return None

    pivot = (prev_high + prev_low + prev_close) / 3
    range_prev = prev_high - prev_low

    if range_prev <= 0: # Handle zero or negative range
        return {"pivot": pivot, "r1": pivot, "r2": pivot, "s1": pivot, "s2": pivot}

    # Calculate levels using standard Fibonacci ratios
    r1 = pivot + (range_prev * 0.382)
    r2 = pivot + (range_prev * 0.618)
    s1 = pivot - (range_prev * 0.382)
    s2 = pivot - (range_prev * 0.618)

    return {"pivot": pivot, "r1": r1, "r2": r2, "s1": s1, "s2": s2}

def calculate_volatility_index(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculates a Volatility Index, normalized by ATR and price."""
    if len(df) < period or "ATR" not in df.columns or df["ATR"].isnull().all():
        return pd.Series(np.nan, index=df.index)

    # Normalize ATR by closing price, handling division by zero
    normalized_atr = _safe_divide_decimal(df["ATR"], df["close"].replace(0, Decimal("0")))

    # Calculate the rolling mean of normalized ATR
    volatility_index = normalized_atr.rolling(window=period).mean()

    return _clean_series(volatility_index, df.index)

def calculate_vwma(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculates the Volume Weighted Moving Average (VWMA)."""
    if len(df) < period or "volume" not in df.columns or df["volume"].isnull().any():
        return pd.Series(np.nan, index=df.index)

    # Ensure volume is numeric and positive, replacing 0s and NaNs with NaN for calculations
    valid_volume = pd.to_numeric(df["volume"], errors='coerce').replace(0, np.nan)
    pv = df["close"] * valid_volume # Price * Volume

    # Calculate VWMA by summing (Price * Volume) / Sum (Volume) over the window
    vwma = _safe_divide_decimal(pv.rolling(window=period).sum(), valid_volume.rolling(window=period).sum())

    return _clean_series(vwma, df.index)

def calculate_volume_delta(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculates Volume Delta, indicating buying vs. selling pressure."""
    if len(df) < MIN_DATA_POINTS_VOLATILITY:
        return pd.Series(np.nan, index=df.index)

    # Approximate buy/sell volume based on whether close > open
    buy_volume = df["volume"].where(df["close"] > df["open"], 0)
    sell_volume = df["volume"].where(df["close"] < df["open"], 0)

    buy_volume_sum = buy_volume.rolling(window=period, min_periods=1).sum()
    sell_volume_sum = sell_volume.rolling(window=period, min_periods=1).sum()

    total_volume_sum = buy_volume_sum + sell_volume_sum
    # Calculate Volume Delta, handling division by zero
    volume_delta = _safe_divide_decimal(buy_volume_sum - sell_volume_sum, total_volume_sum.replace(0, Decimal("0")))

    return _clean_series(volume_delta.fillna(0.0), df.index) # Fill resulting NaNs with 0

def calculate_kaufman_ama(
    df: pd.DataFrame, period: int, fast_period: int, slow_period: int
) -> pd.Series:
    """Calculates Kaufman's Adaptive Moving Average (KAMA)."""
    if len(df) < period + slow_period: return pd.Series(np.nan, index=df.index)

    close_prices = df["close"].values
    kama = np.full_like(close_prices, np.nan)

    # Efficiency Ratio (ER) calculation
    price_change = np.abs(np.diff(close_prices, prepend=close_prices[0]))
    volatility = pd.Series(close_prices).diff().abs().rolling(window=period).sum()
    volatility_values = volatility.values

    er = np.full_like(close_prices, np.nan)
    valid_vol_indices = np.where(volatility_values != 0)[0] # Indices where volatility is non-zero
    er[valid_vol_indices] = price_change[valid_vol_indices] / volatility_values[valid_vol_indices]
    er = np.clip(er, 0, 1) # Clip ER to range [0, 1]

    # Smoothing Constant (SC) calculation
    fast_alpha = 2 / (fast_period + 1)
    slow_alpha = 2 / (slow_period + 1)
    sc = (er * (fast_alpha - slow_alpha) + slow_alpha) ** 2

    # KAMA calculation loop
    first_valid_idx = period # Starting index for KAMA calculation
    while first_valid_idx < len(close_prices) and (np.isnan(close_prices[first_valid_idx]) or np.isnan(sc[first_valid_idx])):
        first_valid_idx += 1

    if first_valid_idx >= len(close_prices): return pd.Series(np.nan, index=df.index) # No valid start point

    kama[first_valid_idx] = close_prices[first_valid_idx] # Initialize KAMA with the first valid close price

    for i in range(first_valid_idx + 1, len(close_prices)):
        if not np.isnan(sc[i]) and not np.isnan(kama[i-1]):
            kama[i] = kama[i - 1] + sc[i] * (close_prices[i] - kama[i - 1])
        else: # Handle NaNs in SC or previous KAMA value
            kama[i] = kama[i - 1] if not np.isnan(kama[i-1]) else close_prices[i]

    return pd.Series(kama, index=df.index)

def calculate_relative_volume(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculates Relative Volume, comparing current volume to its average over 'period'."""
    if len(df) < period: return pd.Series(np.nan, index=df.index)

    avg_volume = df["volume"].rolling(window=period, min_periods=period).mean()
    # Calculate relative volume, handling division by zero
    relative_volume = _safe_divide_decimal(df["volume"], avg_volume.replace(0, Decimal("0")), default=Decimal("1.0"))

    return _clean_series(relative_volume, df.index)

def calculate_market_structure(df: pd.DataFrame, lookback_period: int) -> pd.Series:
    """Detects market structure trend (UP, DOWN, SIDEWAYS) based on recent highs/lows."""
    min_bars = lookback_period * 2 # Need two segments to compare
    if len(df) < min_bars:
        return pd.Series("SIDEWAYS", index=df.index, dtype="object")

    recent_df = df.iloc[-min_bars:] # Consider the last 'min_bars'
    if len(recent_df) < min_bars: return pd.Series("SIDEWAYS", index=df.index, dtype="object")

    # Split into previous and current segments for comparison
    prev_segment = recent_df.iloc[:-lookback_period]
    current_segment = recent_df.iloc[-lookback_period:]

    # Find highs/lows in each segment, handling potential NaNs
    recent_high, recent_low = current_segment["high"].max(), current_segment["low"].min()
    prev_high, prev_low = prev_segment["high"].max(), prev_segment["low"].min()

    trend = "SIDEWAYS" # Default to sideways
    # Proceed only if all high/low values are valid
    if not pd.isna(recent_high) and not pd.isna(recent_low) and \
       not pd.isna(prev_high) and not pd.isna(prev_low):

        is_higher_high = recent_high > prev_high
        is_higher_low = recent_low > prev_low
        is_lower_high = recent_high < prev_high
        is_lower_low = recent_low < prev_low

        if is_higher_high and is_higher_low: trend = "UP" # Higher highs and higher lows
        elif is_lower_high and is_lower_low: trend = "DOWN" # Lower highs and lower lows

    return pd.Series(trend, index=df.index, dtype="object") # Return trend as a Series aligned with df index

def calculate_dema(df: pd.DataFrame, series: pd.Series, period: int) -> pd.Series:
    """Calculates the Double Exponential Moving Average (DEMA)."""
    if len(series) < 2 * period: return pd.Series(np.nan, index=df.index) # DEMA needs more history

    ema1 = series.ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean() # EMA of EMA1
    dema = 2 * ema1 - ema2

    return _clean_series(dema, df.index)

def calculate_keltner_channels(
    df: pd.DataFrame, period: int, atr_multiplier: float, atr_period: int
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates Keltner Channels (Upper Band, Middle Line, Lower Band)."""
    # Check for ATR availability and validity
    if "ATR" not in df.columns or df["ATR"].isnull().all() or len(df) < period:
        logger.debug("Missing ATR or insufficient data for Keltner Channels.")
        return (pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index),
                pd.Series(np.nan, index=df.index))

    ema = df["close"].ewm(span=period, adjust=False).mean() # Middle line is EMA of close
    atr = df["ATR"] # Use pre-calculated ATR

    upper_band = ema + (atr * atr_multiplier)
    lower_band = ema - (atr * atr_multiplier)

    return (_clean_series(upper_band, df.index), _clean_series(ema, df.index),
            _clean_series(lower_band, df.index))

def calculate_roc(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculates the Rate of Change (ROC) percentage."""
    if len(df) < period + 1: return pd.Series(np.nan, index=df.index) # Need period + 1 data points

    # Calculate ROC, handling division by zero for the shifted close price
    roc = (_safe_divide_decimal((df["close"] - df["close"].shift(period)), df["close"].shift(period).replace(0, Decimal("0")))) * 100

    return _clean_series(roc, df.index)

def detect_candlestick_patterns(df: pd.DataFrame) -> pd.Series:
    """Detects common bullish/bearish candlestick patterns on the latest bar."""
    if len(df) < MIN_CANDLESTICK_PATTERNS_BARS: # Need at least 2 bars for most patterns
        return pd.Series("No Pattern", index=df.index, dtype="object")

    patterns = pd.Series("No Pattern", index=df.index, dtype="object")
    i = len(df) - 1 # Index of the latest bar

    # Check if necessary data exists for the current and previous bars
    cols_needed = ["open", "close", "high", "low"]
    if not all(col in df.columns and not df[col].isnull().iloc[i] for col in cols_needed) or \
       (len(df) > 1 and not all(col in df.columns and not df[col].isnull().iloc[i-1] for col in cols_needed)):
        return patterns # Return default if data is insufficient or invalid

    current_bar = df.iloc[i]
    prev_bar = df.iloc[i-1] if len(df) > 1 else None # Handle case with only one bar

    # Calculate properties for the current bar
    body_current = abs(current_bar["close"] - current_bar["open"])
    range_current = current_bar["high"] - current_bar["low"]
    upper_shadow_current = current_bar["high"] - max(current_bar["open"], current_bar["close"])
    lower_shadow_current = min(current_bar["open"], current_bar["close"]) - current_bar["low"]

    # Pattern detection logic
    if prev_bar is not None: # Requires comparison with previous bar
        body_prev = abs(prev_bar["close"] - prev_bar["open"])

        # Bullish Engulfing: Current bullish candle engulfs previous bearish candle
        if (current_bar["close"] > current_bar["open"] and # Current bullish
            prev_bar["close"] < prev_bar["open"] and # Previous bearish
            current_bar["open"] < prev_bar["close"] and # Current open below prev close
            current_bar["close"] > prev_bar["open"]): # Current close above prev open
            patterns.iloc[i] = "Bullish Engulfing"

        # Bearish Engulfing: Current bearish candle engulfs previous bullish candle
        elif (current_bar["close"] < current_bar["open"] and # Current bearish
              prev_bar["close"] > prev_bar["open"] and # Previous bullish
              current_bar["open"] > prev_bar["close"] and # Current open above prev close
              current_bar["close"] < prev_bar["open"]): # Current close below prev open
            patterns.iloc[i] = "Bearish Engulfing"

    # Patterns that don't require comparison with previous bar
    # Hammer (Bullish): Small body at top, long lower shadow, little/no upper shadow
    if (current_bar["close"] > current_bar["open"] and # Bullish candle
        body_current > 0 and # Ensure body exists
        lower_shadow_current >= 2 * body_current and # Long lower shadow
        upper_shadow_current <= 0.5 * body_current): # Small upper shadow
        patterns.iloc[i] = "Bullish Hammer"

    # Shooting Star (Bearish): Small body at bottom, long upper shadow, little/no lower shadow
    elif (current_bar["close"] < current_bar["open"] and # Bearish candle
          body_current > 0 and
          upper_shadow_current >= 2 * body_current and # Long upper shadow
          lower_shadow_current <= 0.5 * body_current): # Small lower shadow
        patterns.iloc[i] = "Bearish Shooting Star"

    return patterns

def _get_mtf_trend(higher_tf_df: pd.DataFrame, config: dict, logger: logging.Logger, symbol: str, indicator_type: str) -> str:
    """Determines the trend direction (UP, DOWN, SIDEWAYS, UNKNOWN) from a higher timeframe using a specified indicator."""
    if higher_tf_df.empty:
        logger.debug(f"[{symbol}] MTF trend: Higher timeframe DataFrame is empty.")
        return "UNKNOWN"

    last_close = higher_tf_df["close"].iloc[-1] # Get the latest closing price
    period = config["mtf_analysis"]["trend_period"] # Period for trend indicators like SMA/EMA
    indicator_settings = config["indicator_settings"]

    try:
        if indicator_type == "sma":
            sma_val = calculate_sma(higher_tf_df, period=period)
            if not sma_val.isnull().all() and not pd.isna(sma_val.iloc[-1]):
                if last_close > sma_val.iloc[-1]: return "UP"
                if last_close < sma_val.iloc[-1]: return "DOWN"
            return "SIDEWAYS"

        if indicator_type == "ema":
            ema_val = calculate_ema(higher_tf_df, period=period)
            if not ema_val.isnull().all() and not pd.isna(ema_val.iloc[-1]):
                if last_close > ema_val.iloc[-1]: return "UP"
                if last_close < ema_val.iloc[-1]: return "DOWN"
            return "SIDEWAYS"

        if indicator_type == "ehlers_supertrend":
            st_result = calculate_ehlers_supertrend(
                df=higher_tf_df,
                period=indicator_settings["ehlers_slow_period"],
                multiplier=indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1] # Get direction from the last valid calculation
                if st_dir == 1: return "UP"
                if st_dir == -1: return "DOWN"
            return "UNKNOWN" # If ST calculation failed or returned no direction

        logger.warning(f"[{symbol}] MTF trend: Unknown indicator type '{indicator_type}' specified.")
        return "UNKNOWN"

    except Exception as e:
        logger.error(f"[{symbol}] MTF trend calculation error for indicator '{indicator_type}': {e}\n{traceback.format_exc()}")
        return "UNKNOWN"


