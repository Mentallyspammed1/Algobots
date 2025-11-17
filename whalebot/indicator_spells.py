
#
# Pyrmethus' Arcane Arts: Indicator Spells Module
#
# This module houses the core technical indicator calculations,
# crafted with standard pandas and numpy for efficiency and clarity,
# avoiding external libraries like pandas-ta.
#
# Essence: To provide robust, well-tested indicator functions that
# respect precision and handle edge cases gracefully.
#
# Core Values: Elegance, Efficiency, Clarity, Robustness.
# Mantra: Calculations must be pure; side effects are forbidden.
#

import logging
import sys
import os
from decimal import getcontext
from pathlib import Path

import numpy as np
import pandas as pd

# --- Colorama Initialization ---
# Although not strictly needed for the module itself, it's good practice
# to have it if the module might be used in a colored terminal context.
# For module reusability, we'll keep it minimal here.
from colorama import init as colorama_init

colorama_init(autoreset=True)  # Auto-reset styles after each print

# --- Placeholder for Logger ---
# In a real module, this would likely be passed in or configured externally.
# For self-containment, we'll use a basic logger setup.
logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler(sys.stdout)
    # Basic formatter without colors for module reusability
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logger._configured = True
# --- Custom Log Level Definition ---
# Ensure SUCCESS_LEVEL is defined if it's a custom level.
# In logging, levels are integers. Let's assign a value above CRITICAL.
SUCCESS_LEVEL = logging.CRITICAL + 1
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")  # Register the level name for display


# --- Global Constants (from whalebott.py) ---
# These are essential for indicator calculations and should be consistent.
# Ideally, these would be imported from a shared constants file.
# For self-containment, defining them here.
DEFAULT_PRIMARY_INTERVAL = "15m"
DEFAULT_LOOP_DELAY_SECONDS = 60
BASE_URL = "https://api.bybit.com"
WS_PUBLIC_BASE_URL = "wss://stream.bybit.com/v5"
WS_PRIVATE_BASE_URL = "wss://stream.bybit.com/v5"
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = SCRIPT_DIR / "config"
LOG_DIRECTORY = SCRIPT_DIR / "logs"
CONFIG_FILE_PATH = CONFIG_DIR / "config.json"


# --- Set global precision for Decimal calculations ---
getcontext().prec = 28  # Standard for financial precision


# --- Indicator Calculation Functions ---
# These functions are extracted from whalebott.py and use standard pandas/numpy.

def calculate_sma(data: pd.Series, period: int) -> pd.Series:
    """Calculates Simple Moving Average."""
    if period <= 0:
        return pd.Series(np.nan, index=data.index)
    try:
        return data.rolling(window=period).mean()
    except Exception as e:
        logger.warning(f"Error calculating SMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)


def calculate_ema(data: pd.Series, period: int) -> pd.Series:
    """Calculates Exponential Moving Average."""
    if period <= 0:
        return pd.Series(np.nan, index=data.index)
    try:
        return data.ewm(span=period, adjust=False).mean()
    except Exception as e:
        logger.warning(f"Error calculating EMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)


def calculate_vwma(
    close_data: pd.Series, volume_data: pd.Series, period: int,
) -> pd.Series:
    """Calculates Volume Weighted Moving Average."""
    if period <= 0:
        return pd.Series(np.nan, index=close_data.index)
    try:
        # Calculate Typical Price (H+L+C)/3 - using close for simplicity if H/L not critical
        typical_price = (
            close_data + close_data.shift(1) + close_data.shift(2)
        ) / 3
        if typical_price.isnull().all():
            typical_price = close_data  # Fallback if H/L not available

        # Calculate VWAP for the period
        vwap_series = (typical_price * volume_data).rolling(
            window=period,
        ).sum() / volume_data.rolling(window=period).sum()
        return vwap_series
    except Exception as e:
        logger.warning(f"Error calculating VWMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=close_data.index)


def calculate_kama(
    data: pd.Series, period: int, fast_period: int, slow_period: int,
) -> pd.Series:
    """Calculates Kaufman's Adaptive Moving Average (KAMA)."""
    if period <= 0 or fast_period <= 0 or slow_period <= 0:
        return pd.Series(np.nan, index=data.index)
    try:
        # Step 1: Calculate the Efficiency Ratio (ER)
        # ER = ( (Close - Prior Close) / (High - Low) ) * 100
        # Handle potential division by zero or NaN
        price_change = data - data.shift(1)
        h_l_diff = data.rolling(window=period).max() - data.rolling(window=period).min()
        h_l_diff = h_l_diff.replace(0, 1e-9)  # Avoid division by zero
        er = (price_change / h_l_diff) * 100
        er = er.fillna(0)  # Fill initial NaNs

        # Step 2: Calculate the Noise Ratio (NR)
        # NR = 100 - ER
        nr = 100 - er

        # Step 3: Calculate the Smoothing Constant (SC)
        # SC = ER / (period * Noise_Ratio)
        # Use SC_fast = 2 / (fast_period + 1) and SC_slow = 2 / (slow_period + 1) for calculation basis
        sc_fast_base = 2 / (fast_period + 1)
        sc_slow_base = 2 / (slow_period + 1)
        sc = (er / period) * (sc_fast_base - sc_slow_base) + sc_slow_base

        # Step 4: Calculate KAMA
        # KAMA = Prior KAMA + SC * (Close - Prior KAMA)
        kama = pd.Series(np.nan, index=data.index)
        # Initialize with the first valid price as KAMA
        kama.iloc[period - 1] = data.iloc[period - 1]

        for i in range(period, len(data)):
            if pd.isna(kama.iloc[i - 1]):  # If previous KAMA is NaN, re-initialize
                kama.iloc[i] = data.iloc[i]
            else:
                kama.iloc[i] = kama.iloc[i - 1] + sc.iloc[i] * (
                    data.iloc[i] - kama.iloc[i - 1]
                )
        return kama

    except Exception as e:
        logger.warning(
            f"Error calculating KAMA({period}, fast={fast_period}, slow={slow_period}): {e}",
            exc_info=True,
        )
        return pd.Series(np.nan, index=data.index)


def calculate_rsi(data: pd.Series, period: int) -> pd.Series:
    """Calculates Relative Strength Index."""
    if period <= 0:
        return pd.Series(np.nan, index=data.index)
    try:
        delta = data.diff()
        gain = (delta.where(delta > 0)).fillna(0)
        loss = (-delta.where(delta < 0)).fillna(0)

        avg_gain = gain.ewm(span=period, adjust=False).mean()
        avg_loss = loss.ewm(span=period, adjust=False).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except Exception as e:
        logger.warning(f"Error calculating RSI({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)


def calculate_stoch_rsi(
    data: pd.Series, period: int, k_period: int, d_period: int,
) -> tuple[pd.Series, pd.Series]:
    """Calculates Stochastic RSI."""
    if period <= 0 or k_period <= 0 or d_period <= 0:
        return pd.Series(np.nan, index=data.index), pd.Series(np.nan, index=data.index)
    try:
        rsi = calculate_rsi(data, period=period)
        if rsi.isnull().all():
            return pd.Series(np.nan, index=data.index), pd.Series(np.nan, index=data.index)

        min_rsi = rsi.rolling(window=period).min()
        max_rsi = rsi.rolling(window=period).max()

        stoch_rsi = 100 * ((rsi - min_rsi) / (max_rsi - min_rsi))
        stoch_rsi = stoch_rsi.fillna(0)  # Fill initial NaNs

        # Calculate %K and %D
        stoch_k = stoch_rsi.rolling(window=k_period).mean()
        stoch_d = stoch_k.rolling(window=d_period).mean()

        return stoch_k, stoch_d
    except Exception as e:
        logger.warning(
            f"Error calculating Stochastic RSI (Period={period}, K={k_period}, D={d_period}): {e}",
            exc_info=True,
        )
        return pd.Series(np.nan, index=data.index), pd.Series(np.nan, index=data.index)


def calculate_cci(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int,
) -> pd.Series:
    """Calculates Commodity Channel Index."""
    if period <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        typical_price = (high + low + close) / 3
        # Using ta-lib for accuracy if available, otherwise fallback to manual implementation
        # Note: ta-lib is not guaranteed to be available in all environments.
        # For broader compatibility, a manual implementation is preferred if ta-lib is not a hard dependency.
        # The following is a manual implementation fallback.
        tp_mean = typical_price.rolling(window=period).mean()
        tp_dev = abs(typical_price - tp_mean).rolling(window=period).sum() / period
        # Avoid division by zero
        tp_dev = tp_dev.replace(0, 1e-9)
        cci = (typical_price - tp_mean) / (0.015 * tp_dev)  # 0.015 is a common constant multiplier
        return cci
    except Exception as e:
        logger.warning(f"Error calculating CCI({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)


def calculate_williams_r(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int,
) -> pd.Series:
    """Calculates Williams %R."""
    if period <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()
        wr = -100 * ((highest_high - close) / (highest_high - lowest_low))
        return wr
    except Exception as e:
        logger.warning(f"Error calculating Williams %R({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)


def calculate_mfi(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int,
) -> pd.Series:
    """Calculates Money Flow Index."""
    if period <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        typical_price = (high + low + close) / 3
        money_flow = typical_price * volume
        positive_mf = money_flow.where(typical_price > typical_price.shift(1)).fillna(0)
        negative_mf = money_flow.where(typical_price < typical_price.shift(1)).fillna(0)

        positive_mf_sum = positive_mf.rolling(window=period).sum()
        negative_mf_sum = negative_mf.rolling(window=period).sum()

        money_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + money_ratio))
        return mfi
    except Exception as e:
        logger.warning(f"Error calculating MFI({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)


def calculate_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int,
) -> pd.Series:
    """Calculates Average True Range."""
    if period <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        # Calculate True Range (TR)
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Calculate ATR using EMA
        atr = true_range.ewm(span=period, adjust=False).mean()
        return atr
    except Exception as e:
        logger.warning(f"Error calculating ATR({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)


def calculate_psar(
    high: pd.Series, low: pd.Series, close: pd.Series, af_start: float, af_max: float,
) -> pd.Series:
    """Calculates Parabolic Stop and Reverse (PSAR)."""
    # Using a simplified manual implementation as ta-lib might not be available
    # A full implementation requires careful state management (AF, EP, trend)
    # This is a placeholder and might need refinement or ta-lib integration.
    if af_start <= 0 or af_max <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        # Placeholder: Return NaNs or a very basic calculation
        # A proper implementation would be much more complex.
        # For now, we return NaNs to signify it's not reliably calculated here.
        logger.warning(
            "Manual PSAR calculation is a placeholder and may not be accurate. Consider using a library like TA-Lib.",
        )
        return pd.Series(np.nan, index=high.index)
    except Exception as e:
        logger.warning(
            f"Error calculating PSAR (AF_Start={af_start}): {e}", exc_info=True,
        )
        return pd.Series(np.nan, index=high.index)


def calculate_bollinger_bands(
    data: pd.Series, period: int, std_dev: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates Bollinger Bands (Basis, Upper, Lower)."""
    if period <= 0 or std_dev <= 0:
        return (
            pd.Series(np.nan, index=data.index),
            pd.Series(np.nan, index=data.index),
            pd.Series(np.nan, index=data.index),
        )
    try:
        basis = calculate_sma(data, period=period)
        if basis.isnull().all():
            return (
                pd.Series(np.nan, index=data.index),
                pd.Series(np.nan, index=data.index),
                pd.Series(np.nan, index=data.index),
            )

        std_dev_prices = data.rolling(window=period).std()
        upper = basis + (std_dev_prices * std_dev)
        lower = basis - (std_dev_prices * std_dev)
        return basis, upper, lower
    except Exception as e:
        logger.warning(
            f"Error calculating Bollinger Bands (Period={period}, StdDev={std_dev}): {e}",
            exc_info=True,
        )
        return (
            pd.Series(np.nan, index=data.index),
            pd.Series(np.nan, index=data.index),
            pd.Series(np.nan, index=data.index),
        )


def calculate_keltner_channels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int,
    atr_multiplier: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates Keltner Channels."""
    if period <= 0 or atr_multiplier <= 0:
        return (
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
        )
    try:
        basis = calculate_ema(close, period=period)  # EMA is common for Keltner basis
        if basis.isnull().all():
            return (
                pd.Series(np.nan, index=high.index),
                pd.Series(np.nan, index=high.index),
                pd.Series(np.nan, index=high.index),
            )

        atr = calculate_atr(high, low, close, period=period)
        upper = basis + (atr * atr_multiplier)
        lower = basis - (atr * atr_multiplier)
        return basis, upper, lower
    except Exception as e:
        logger.warning(
            f"Error calculating Keltner Channels (Period={period}, ATRMult={atr_multiplier}): {e}",
            exc_info=True,
        )
        return (
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
        )


def calculate_adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int,
) -> dict[str, pd.Series]:
    """Calculates ADX, PlusDI, MinusDI."""
    if period <= 0:
        return {
            "ADX": pd.Series(np.nan, index=high.index),
            "PlusDI": pd.Series(np.nan, index=high.index),
            "MinusDI": pd.Series(np.nan, index=high.index),
        }
    try:
        # Calculate Directional Movement (+DM, -DM)
        up_move = high.diff()
        down_move = low.diff()
        plus_dm = pd.Series(np.nan, index=high.index)
        minus_dm = pd.Series(np.nan, index=high.index)

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), -down_move, 0)

        # Smoothed Directional Indicators (+DI, -DI) using Wilder's smoothing (similar to EMA but different factor)
        # Smoothed value = Prior Smoothed + (Current Value - Prior Smoothed) / Period
        # Or using EMA with period: TR = EMA(TR, period)
        # Using EMA for simplicity here. Wilder's smoothing uses period / (period + 1) instead of 2/(period+1).
        plus_di = plus_dm.ewm(span=period, adjust=False).mean()
        minus_di = minus_dm.ewm(span=period, adjust=False).mean()

        # Calculate Directional Index (DX)
        di_sum = plus_di + minus_di
        di_diff = abs(plus_di - minus_di)
        # Avoid division by zero
        di_sum = di_sum.replace(0, 1e-9)
        dx = (di_diff / di_sum) * 100

        # Calculate ADX from DX using EMA
        adx = dx.ewm(span=period, adjust=False).mean()

        return {"ADX": adx, "PlusDI": plus_di, "MinusDI": minus_di}
    except Exception as e:
        logger.warning(f"Error calculating ADX({period}): {e}", exc_info=True)
        return {
            "ADX": pd.Series(np.nan, index=high.index),
            "PlusDI": pd.Series(np.nan, index=high.index),
            "MinusDI": pd.Series(np.nan, index=high.index),
        }


def calculate_volume_delta(
    close: pd.Series, volume: pd.Series, period: int,
) -> pd.Series:
    """Calculates Volume Delta (Buy Volume - Sell Volume) over a period."""
    if period <= 0:
        return pd.Series(np.nan, index=close.index)
    try:
        # Simple approach: assume volume is buy volume if close > open, sell volume if close < open
        # This is a simplification; actual buy/sell volume requires order book or tick data.
        buy_volume = volume.where(close > close.shift(1)).fillna(0)
        sell_volume = volume.where(close < close.shift(1)).fillna(0)

        volume_delta_per_candle = buy_volume - sell_volume
        # Calculate rolling sum of volume delta
        volume_delta_rolled = volume_delta_per_candle.rolling(window=period).sum()
        return volume_delta_rolled
    except Exception as e:
        logger.warning(f"Error calculating Volume Delta({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=close.index)


def calculate_relative_volume(volume: pd.Series, period: int) -> pd.Series:
    """Calculates Relative Volume (Current Volume / Average Volume)."""
    if period <= 0:
        return pd.Series(np.nan, index=volume.index)
    try:
        avg_volume = volume.rolling(window=period).mean()
        # Avoid division by zero
        avg_volume = avg_volume.replace(0, 1e-9)
        relative_vol = volume / avg_volume
        return relative_vol
    except Exception as e:
        logger.warning(
            f"Error calculating Relative Volume({period}): {e}", exc_info=True,
        )
        return pd.Series(np.nan, index=volume.index)


def calculate_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """Calculates On-Balance Volume."""
    try:
        obv = pd.Series(index=close.index, dtype="float64")
        obv.iloc[0] = 0  # Initialize OBV

        for i in range(1, len(close)):
            if close.iloc[i] > close.iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] + volume.iloc[i]
            elif close.iloc[i] < close.iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] - volume.iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i - 1]
        return obv
    except Exception as e:
        logger.warning(f"Error calculating OBV: {e}", exc_info=True)
        return pd.Series(np.nan, index=close.index)


def calculate_cmf(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int,
) -> pd.Series:
    """Calculates Chaikin Money Flow."""
    if period <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        # Calculate Money Flow Multiplier (MFM)
        mfm = ((close - low) - (high - close)) / (high - low)
        # Avoid division by zero or NaN in (high - low)
        mfm = mfm.replace([np.inf, -np.inf], 0)
        mfm = mfm.fillna(0)

        # Calculate Money Flow (MF)
        mf = mfm * volume

        # Calculate CMF over the period using rolling sum
        cmf = mf.rolling(window=period).sum() / volume.rolling(window=period).sum()
        return cmf
    except Exception as e:
        logger.warning(f"Error calculating CMF({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)


def calculate_macd(
    close: pd.Series, fast_period: int, slow_period: int, signal_period: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates MACD (MACD Line, Signal Line, Histogram)."""
    if (
        fast_period <= 0
        or slow_period <= 0
        or signal_period <= 0
        or fast_period >= slow_period
    ):
        return (
            pd.Series(np.nan, index=close.index),
            pd.Series(np.nan, index=close.index),
            pd.Series(np.nan, index=close.index),
        )
    try:
        ema_fast = calculate_ema(close, period=fast_period)
        ema_slow = calculate_ema(close, period=slow_period)

        macd_line = ema_fast - ema_slow
        signal_line = calculate_ema(macd_line, period=signal_period)
        macd_hist = macd_line - signal_line

        return macd_line, signal_line, macd_hist
    except Exception as e:
        logger.warning(
            f"Error calculating MACD (Fast={fast_period}, Slow={slow_period}, Signal={signal_period}): {e}",
            exc_info=True,
        )
        return (
            pd.Series(np.nan, index=close.index),
            pd.Series(np.nan, index=close.index),
            pd.Series(np.nan, index=close.index),
        )


# Ehlers Indicator Calculations (Simplified placeholders, might require external libraries or detailed implementation)
# These are complex and require precise state management. Using basic logic for demonstration.


def calculate_ehlers_supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr_len: int,
    multiplier: float,
    ss_len: int | None = None,
) -> tuple[pd.Series, pd.Series]:
    """Placeholder for Ehlers SuperTrend calculation. Requires precise implementation."""
    # A true SuperTrend implementation involves ATR and trend direction tracking.
    # This placeholder returns NaNs.
    logger.warning(
        "Ehlers SuperTrend calculation is a placeholder. Requires detailed implementation.",
    )
    return pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index)


def calculate_fisher_transform(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int,
) -> tuple[pd.Series, pd.Series]:
    """Placeholder for Ehlers Fisher Transform calculation."""
    # Requires calculation of Highest High and Lowest Low over `length` period.
    logger.warning(
        "Ehlers Fisher Transform calculation is a placeholder. Requires detailed implementation.",
    )
    return pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index)


def calculate_ehlers_stochrsi(
    close: pd.Series, rsi_len: int, stoch_len: int, fast_len: int, slow_len: int,
) -> pd.Series:
    """Placeholder for Ehlers Stochastic RSI calculation."""
    # StochRSI calculation is already implemented above, this function might aim for Ehlers' specific version.
    logger.warning(
        "Ehlers Stochastic RSI calculation is a placeholder. Consider using the standard StochRSI or verify Ehlers' method.",
    )
    # For now, defer to the standard implementation. If Ehlers' version differs significantly,
    # this would need its own logic.
    stoch_k, _ = calculate_stoch_rsi(close, rsi_len, stoch_len, fast_len)
    return stoch_k  # Returning StochRSI %K as a proxy


def calculate_ichimoku_cloud(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    tenkan_period: int,
    kijun_period: int,
    senkou_span_b_period: int,
    chikou_offset: int,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Calculates Ichimoku Cloud components."""
    if tenkan_period <= 0 or kijun_period <= 0 or senkou_span_b_period <= 0:
        return (
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
        )
    try:
        # Conversion periods
        tenkan_sen = (
            high.rolling(window=tenkan_period).max()
            + low.rolling(window=tenkan_period).min()
        ) / 2
        kijun_sen = (
            high.rolling(window=kijun_period).max()
            + low.rolling(window=kijun_period).min()
        ) / 2

        # Senkou Span A (Leading Span 1)
        senkou_span_a = (tenkan_sen + kijun_sen) / 2

        # Senkou Span B (Leading Span 2)
        senkou_span_b = (
            high.rolling(window=senkou_span_b_period).max()
            + low.rolling(window=senkou_span_b_period).min()
        ) / 2

        # Chikou Span (Lagging Span) - shifted back by kijun_period (common offset)
        # The offset is applied in the data frame itself, so here we just return close series.
        # The dataframe merge/lookup handles the offset.
        chikou_span = close

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span
    except Exception as e:
        logger.warning(f"Error calculating Ichimoku Cloud: {e}", exc_info=True)
        return (
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
            pd.Series(np.nan, index=high.index),
        )


def calculate_pivot_points_fibonacci(
    daily_df: pd.DataFrame, window: int,
) -> pd.DataFrame:
    """Calculates Fibonacci Pivot Points based on daily High, Low, Close."""
    if daily_df.empty or window <= 0:
        return pd.DataFrame()
    try:
        # Ensure required columns are present and numeric
        required_cols = ["high", "low", "close"]
        if not all(col in daily_df.columns for col in required_cols):
            logger.error("Daily DataFrame missing required columns for Pivot calculation.")
            return pd.DataFrame()

        # Calculate Standard Pivots (P)
        P = (daily_df["high"] + daily_df["low"] + daily_df["close"]) / 3

        # Calculate Resistance (R) and Support (S) levels
        R1 = (2 * P) - daily_df["low"]
        S1 = (2 * P) - daily_df["high"]

        R2 = P + (daily_df["high"] - daily_df["low"])
        S2 = P - (df["high"] - df["low"])

        R3 = P + 2 * (daily_df["high"] - daily_df["low"])
        S3 = P - 2 * (df["high"] - df["low"])

        # Calculate Camilla Boyer (BC) and Bollinger Support (BS) - often derived from pivots
        # These might need specific definitions; using common interpretations:
        BC = P - (df["high"] - df["low"])  # Simplified BC
        BS = P + (df["high"] - df["low"])  # Simplified BS

        # Create DataFrame for pivot points, ensure timestamp alignment
        pivot_df = pd.DataFrame(
            {
                "timestamp": daily_df["timestamp"],
                "Pivot": P,
                "R1": R1,
                "R2": R2,
                "R3": R3,
                "S1": S1,
                "S2": S2,
                "S3": S3,
                "BC": BC,
                "BS": BS,
            },
        )

        # Apply rolling window to get pivots for the lookback period
        # This calculates pivots based on the last `window` days' data.
        # We need to apply this rolling calculation carefully.
        # A common approach is to calculate pivots for each day based on the previous N days' data.
        # For simplicity here, let's assume `daily_df` is already aligned and we want pivots for each day.
        # If a rolling calculation is needed, it implies calculating pivots N days in the past for each current bar.

        # For real-time, pivots are typically based on the previous day's data.
        # If `daily_df` represents daily data, we might just return it directly for use.
        # Let's assume `daily_df` is suitable for direct use, and the `window` parameter
        # implies how many days of history were used to derive `daily_df` itself.
        # If the intent is to calculate pivots dynamically based on a rolling window of `daily_df`,
        # that requires more complex application.

        # Let's just return the calculated pivots for each day in `daily_df` for now.
        # The `window` parameter might be more relevant if `daily_df` itself was a rolling window.
        return pivot_df

    except Exception as e:
        logger.warning(
            f"Error calculating Fibonacci Pivot Points (Window={window}): {e}",
            exc_info=True,
        )
        return pd.DataFrame()


def calculate_volatility_index(
    high: pd.Series, low: pd.Series, period: int,
) -> pd.Series:
    """Calculates a simple Volatility Index (e.g., based on Average Range)."""
    if period <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        # Using ATR as a proxy for volatility
        volatility = calculate_atr(
            high, low, high, period=period,
        )  # Using high for close placeholder in ATR
        return volatility
    except Exception as e:
        logger.warning(
            f"Error calculating Volatility Index ({period}): {e}", exc_info=True,
        )
        return pd.Series(np.nan, index=high.index)


def detect_market_structure(
    high: pd.Series, low: pd.Series, lookback: int,
) -> pd.Series:
    """Detects Market Structure points (HH, HL, LH, LL) - simplified logic."""
    if lookback <= 0:
        return pd.Series(np.nan, index=high.index)
    try:
        structure = pd.Series(np.nan, index=high.index)
        # Simplified logic: A high is higher than previous highs, low is higher than previous lows etc.
        # This requires comparing current pivot points to prior ones over the lookback window.
        # A proper implementation involves finding pivot points first.

        # Placeholder: returns NaN, needs significant implementation.
        logger.warning(
            "Market Structure detection is a placeholder. Requires pivot point identification.",
        )
        return structure
    except Exception as e:
        logger.warning(
            f"Error detecting Market Structure (Lookback={lookback}): {e}",
            exc_info=True,
        )
        return pd.Series(np.nan, index=high.index)


def detect_candlestick_patterns(df: pd.DataFrame) -> pd.Series:
    """Detects common candlestick patterns - Placeholder function."""
    # This would involve analyzing Open, High, Low, Close relationships for specific patterns.
    # e.g., Doji, Engulfing, Hammer, etc.
    # Requires significant pattern recognition logic.
    logger.warning(
        "Candlestick pattern detection is a placeholder. Requires specific pattern recognition logic.",
    )
    return pd.Series(np.nan, index=df.index)


def calculate_roc(close: pd.Series, period: int) -> pd.Series:
    """Calculates Rate of Change."""
    if period <= 0:
        return pd.Series(np.nan, index=close.index)
    try:
        roc = ((close - close.shift(period)) / close.shift(period)) * 100
        return roc
    except Exception as e:
        logger.warning(f"Error calculating ROC({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=close.index)
