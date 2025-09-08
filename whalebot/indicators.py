
import numpy as np
import pandas as pd
from decimal import Decimal, ROUND_DOWN
from typing import Literal
import logging

# --- Constants for Indicators (can be moved to config later if needed) ---
MIN_DATA_POINTS_TR = 2
MIN_DATA_POINTS_SMOOTHER = 2
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR = 2
MIN_DATA_POINTS_VOLATILITY = 2


def calculate_sma(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Simple Moving Average (SMA)."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)
    return df["close"].rolling(window=period).mean()

def calculate_ema(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Exponential Moving Average (EMA)."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)
    return df["close"].ewm(span=period, adjust=False).mean()

def calculate_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Average True Range (ATR)."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)
    tr = calculate_true_range(df)
    return tr.ewm(span=period, adjust=False).mean()


def calculate_true_range(df: pd.DataFrame) -> pd.Series:
    """Calculate True Range (TR)."""
    if len(df) < MIN_DATA_POINTS_TR:
        return pd.Series(np.nan, index=df.index)
    high_low = df["high"] - df["low"]
    high_prev_close = (df["high"] - df["close"].shift()).abs()
    low_prev_close = (df["low"] - df["close"].shift()).abs()
    return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(
        axis=1
    )


def calculate_super_smoother(series: pd.Series, period: int) -> pd.Series:
    """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
    if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER:
        return pd.Series(np.nan, index=series.index)

    series = pd.to_numeric(series, errors="coerce").dropna()
    if len(series) < MIN_DATA_POINTS_SMOOTHER:
        return pd.Series(np.nan, index=series.index)

    a1 = np.exp(-np.sqrt(2) * np.pi / period)
    b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
    c1 = 1 - b1 + a1**2
    c2 = b1 - 2 * a1**2
    c3 = a1**2

    filt = pd.Series(0.0, index=series.index)
    if len(series) >= 1:
        filt.iloc[0] = series.iloc[0]
    if len(series) >= 2:
        filt.iloc[1] = (series.iloc[0] + series.iloc[1]) / 2

    for i in range(2, len(series)):
        filt.iloc[i] = (
            (c1 / 2) * (series.iloc[i] + series.iloc[i - 1])
            + c2 * filt.iloc[i - 1]
            - c3 * filt.iloc[i - 2]
        )
    return filt.reindex(series.index) # Reindex to original series index


def calculate_ehlers_supertrend(
    df: pd.DataFrame,
    period: int,
    multiplier: float,
) -> pd.DataFrame | None:
    """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
    if len(df) < period * 3:
        return None

    df_copy = df.copy()

    hl2 = (df_copy["high"] + df_copy["low"]) / 2
    smoothed_price = calculate_super_smoother(hl2, period)
    if smoothed_price is None or smoothed_price.empty or smoothed_price.isnull().all():
        return None

    tr = calculate_true_range(df_copy)
    smoothed_atr = calculate_super_smoother(tr, period)
    if smoothed_atr is None or smoothed_atr.empty or smoothed_atr.isnull().all():
        return None

    df_copy["smoothed_price"] = smoothed_price
    df_copy["smoothed_atr"] = smoothed_atr

    df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
    if df_copy.empty:
        return None

    upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
    lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

    direction = pd.Series(0, index=df_copy.index, dtype=int)
    supertrend = pd.Series(np.nan, index=df_copy.index)

    first_valid_idx_val = smoothed_price.first_valid_index()
    if first_valid_idx_val is None:
        return None
    first_valid_idx = df_copy.index.get_loc(first_valid_idx_val)
    if first_valid_idx >= len(df_copy):
        return None

    if df_copy["close"].iloc[first_valid_idx] > upper_band.iloc[first_valid_idx]:
        direction.iloc[first_valid_idx] = 1
        supertrend.iloc[first_valid_idx] = lower_band.iloc[first_valid_idx]
    elif (
        df_copy["close"].iloc[first_valid_idx] < lower_band.iloc[first_valid_idx]
    ):
        direction.iloc[first_valid_idx] = -1
        supertrend.iloc[first_valid_idx] = upper_band.iloc[first_valid_idx]
    else:
        direction.iloc[first_valid_idx] = 0
        supertrend.iloc[first_valid_idx] = lower_band.iloc[first_valid_idx]

    for i in range(first_valid_idx + 1, len(df_copy)):
        prev_direction = direction.iloc[i - 1]
        prev_supertrend = supertrend.iloc[i - 1]
        curr_close = df_copy["close"].iloc[i]

        if prev_direction == 1:
            if curr_close < prev_supertrend:
                direction.iloc[i] = -1
                supertrend.iloc[i] = upper_band.iloc[i]
            else:
                direction.iloc[i] = 1
                supertrend.iloc[i] = max(lower_band.iloc[i], prev_supertrend)
        elif prev_direction == -1:
            if curr_close > prev_supertrend:
                direction.iloc[i] = 1
                supertrend.iloc[i] = lower_band.iloc[i]
            else:
                direction.iloc[i] = -1
                supertrend.iloc[i] = min(upper_band.iloc[i], prev_supertrend)
        else:
            if curr_close > upper_band.iloc[i]:
                direction.iloc[i] = 1
                supertrend.iloc[i] = lower_band.iloc[i]
            elif curr_close < lower_band.iloc[i]:
                direction.iloc[i] = -1
                supertrend.iloc[i] = upper_band.iloc[i]
            else:
                direction.iloc[i] = prev_direction
                supertrend.iloc[i] = prev_supertrend

    result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
    return result.reindex(df.index)


def calculate_macd(
    df: pd.DataFrame,
    fast_period: int,
    slow_period: int,
    signal_period: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Moving Average Convergence Divergence (MACD)."""
    if len(df) < slow_period + signal_period:
        return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

    ema_fast = df["close"].ewm(span=fast_period, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow_period, adjust=False).mean()

    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def calculate_rsi(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Relative Strength Index (RSI)."""
    if len(df) <= period:
        return pd.Series(np.nan, index=df.index)
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_stoch_rsi(
    df: pd.DataFrame,
    period: int,
    k_period: int,
    d_period: int,
) -> tuple[pd.Series, pd.Series]:
    """Calculate Stochastic RSI."""
    if len(df) <= period:
        return pd.Series(np.nan, index=df.index), pd.Series(
            np.nan, index=df.index
        )
    rsi = calculate_rsi(df, period)

    lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
    highest_rsi = rsi.rolling(window=period, min_periods=period).max()

    denominator = highest_rsi - lowest_rsi
    denominator[denominator == 0] = np.nan
    stoch_rsi_k_raw = ((rsi - lowest_rsi) / denominator) * 100
    stoch_rsi_k_raw = stoch_rsi_k_raw.fillna(0).clip(0, 100)

    stoch_rsi_k = (
        stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period)
        .mean()
        .fillna(0)
    )
    stoch_rsi_d = (
        stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean().fillna(0)
    )

    return stoch_rsi_k, stoch_rsi_d


def calculate_adx(df: pd.DataFrame, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Average Directional Index (ADX)."""
    if len(df) < period * 2:
        return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

    tr = calculate_true_range(df)

    plus_dm = df["high"].diff()
    minus_dm = -df["low"].diff()

    plus_dm_final = pd.Series(0.0, index=df.index)
    minus_dm_final = pd.Series(0.0, index=df.index)

    for i in range(1, len(df)):
        if plus_dm.iloc[i] > minus_dm.iloc[i] and plus_dm.iloc[i] > 0:
            plus_dm_final.iloc[i] = plus_dm.iloc[i]
        if minus_dm.iloc[i] > plus_dm.iloc[i] and minus_dm.iloc[i] > 0:
            minus_dm_final.iloc[i] = minus_dm.iloc[i]

    atr = tr.ewm(span=period, adjust=False).mean()
    plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
    minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

    di_diff = abs(plus_di - minus_di)
    di_sum = plus_di + minus_di
    dx = (di_diff / di_sum.replace(0, np.nan)).fillna(0) * 100

    adx = dx.ewm(span=period, adjust=False).mean()

    return adx, plus_di, minus_di


def calculate_bollinger_bands(
    df: pd.DataFrame,
    period: int,
    std_dev: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Bollinger Bands."""
    if len(df) < period:
        return (
            pd.Series(np.nan, index=df.index),
            pd.Series(np.nan, index=df.index),
            pd.Series(np.nan, index=df.index),
        )
    middle_band = df["close"].rolling(window=period, min_periods=period).mean()
    std = df["close"].rolling(window=period, min_periods=period).std()
    upper_band = middle_band + (std * std_dev)
    lower_band = middle_band - (std * std_dev)
    return upper_band, middle_band, lower_band


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """Calculate Volume Weighted Average Price (VWAP)."""
    if df.empty:
        return pd.Series(np.nan, index=df.index)
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cumulative_tp_vol = (typical_price * df["volume"]).cumsum()
    cumulative_vol = df["volume"].cumsum()
    vwap = cumulative_tp_vol / cumulative_vol
    return vwap.reindex(df.index)


def calculate_cci(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Commodity Channel Index (CCI)."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = tp.rolling(window=period, min_periods=period).mean()
    mad = tp.rolling(window=period, min_periods=period).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=False
    )
    cci = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))
    return cci


def calculate_williams_r(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Williams %R."""
    if len(df) < period:
        return pd.Series(np.nan, index=df.index)
    highest_high = df["high"].rolling(window=period, min_periods=period).max()
    lowest_low = df["low"].rolling(window=period, min_periods=period).min()
    denominator = highest_high - lowest_low
    wr = -100 * ((highest_high - df["close"]) / denominator.replace(0, np.nan))
    return wr


def calculate_ichimoku_cloud(
    df: pd.DataFrame,
    tenkan_period: int,
    kijun_period: int,
    senkou_span_b_period: int,
    chikou_span_offset: int,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Calculate Ichimoku Cloud components."""
    if (
        len(df)
        < max(tenkan_period, kijun_period, senkou_span_b_period)
        + chikou_span_offset
    ):
        return (
            pd.Series(np.nan),
            pd.Series(np.nan),
            pd.Series(np.nan),
            pd.Series(np.nan),
            pd.Series(np.nan),
        )

    tenkan_sen = (
        df["high"].rolling(window=tenkan_period).max()
        + df["low"].rolling(window=tenkan_period).min()
    ) / 2

    kijun_sen = (
        df["high"].rolling(window=kijun_period).max()
        + df["low"].rolling(window=kijun_period).min()
    ) / 2

    senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)

    senkou_span_b = (
        (
            df["high"].rolling(window=senkou_span_b_period).max()
            + df["low"].rolling(window=senkou_span_b_period).min()
        )
        / 2
    ).shift(kijun_period)

    chikou_span = df["close"].shift(-chikou_span_offset)

    return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span


def calculate_mfi(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Money Flow Index (MFI)."""
    if len(df) <= period:
        return pd.Series(np.nan, index=df.index)
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    money_flow = typical_price * df["volume"]

    price_diff = typical_price.diff()
    positive_flow = money_flow.where(price_diff > 0, 0)
    negative_flow = money_flow.where(price_diff < 0, 0)

    positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
    negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

    mf_ratio = positive_mf_sum / negative_mf_sum.replace(0, np.nan)
    mfi = 100 - (100 / (1 + mf_ratio))
    return mfi


def calculate_obv(df: pd.DataFrame, ema_period: int) -> tuple[pd.Series, pd.Series]:
    """Calculate On-Balance Volume (OBV) and its EMA."""
    if len(df) < MIN_DATA_POINTS_OBV:
        return pd.Series(np.nan), pd.Series(np.nan)

    obv_direction = np.sign(df["close"].diff().fillna(0))
    obv = (obv_direction * df["volume"]).cumsum()

    obv_ema = obv.ewm(span=ema_period, adjust=False).mean()

    return obv, obv_ema


def calculate_cmf(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Chaikin Money Flow (CMF)."""
    if len(df) < period:
        return pd.Series(np.nan)

    high_low_range = df["high"] - df["low"]
    mfm = (
        (df["close"] - df["low"]) - (df["high"] - df["close"])
    ) / high_low_range.replace(0, np.nan)
    mfm = mfm.fillna(0)

    mfv = mfm * df["volume"]

    volume_sum = df["volume"].rolling(window=period).sum()
    cmf = mfv.rolling(window=period).sum() / volume_sum.replace(0, np.nan)
    cmf = cmf.fillna(0)

    return cmf


def calculate_psar(
    df: pd.DataFrame,
    acceleration: float,
    max_acceleration: float,
) -> tuple[pd.Series, pd.Series]:
    """Calculate Parabolic SAR."""
    if len(df) < MIN_DATA_POINTS_PSAR:
        return pd.Series(np.nan, index=df.index), pd.Series(
            np.nan, index=df.index
        )

    psar = df["close"].copy()
    bull = pd.Series(True, index=df.index)
    af = acceleration
    ep = (
        df["low"].iloc[0]
        if df["close"].iloc[0] < df["close"].iloc[1]
        else df["high"].iloc[0]
    )

    for i in range(1, len(df)):
        prev_bull = bull.iloc[i - 1]
        prev_psar = psar.iloc[i - 1]

        if prev_bull:
            psar.iloc[i] = prev_psar + af * (ep - prev_psar)
        else:
            psar.iloc[i] = prev_psar - af * (prev_psar - ep)

        reverse = False
        if prev_bull and df["low"].iloc[i] < psar.iloc[i]:
            bull.iloc[i] = False
            reverse = True
        elif not prev_bull and df["high"].iloc[i] > psar.iloc[i]:
            bull.iloc[i] = True
            reverse = True
        else:
            bull.iloc[i] = prev_bull

        if reverse:
            af = acceleration
            ep = df["high"].iloc[i] if bull.iloc[i] else df["low"].iloc[i]
            if bull.iloc[i]:
                psar.iloc[i] = min(df["low"].iloc[i], df["low"].iloc[i - 1])
            else:
                psar.iloc[i] = max(df["high"].iloc[i], df["high"].iloc[i - 1])

        elif bull.iloc[i]:
            if df["high"].iloc[i] > ep:
                ep = df["high"].iloc[i]
                af = min(af + acceleration, max_acceleration)
            psar.iloc[i] = min(psar.iloc[i], df["low"].iloc[i], df["low"].iloc[i - 1])
        else:
            if df["low"].iloc[i] < ep:
                ep = df["low"].iloc[i]
                af = min(af + acceleration, max_acceleration)
            psar.iloc[i] = max(psar.iloc[i], df["high"].iloc[i], df["high"].iloc[i - 1])

    direction = pd.Series(0, index=df.index, dtype=int)
    direction[psar < df["close"]] = 1
    direction[psar > df["close"]] = -1

    return psar, direction


def calculate_fibonacci_levels(df: pd.DataFrame, window: int) -> dict[str, Decimal] | None:
    """Calculate Fibonacci retracement levels based on a recent high-low swing."""
    if len(df) < window:
        return None

    recent_high = df["high"].iloc[-window:].max()
    recent_low = df["low"].iloc[-window:].min()

    diff = recent_high - recent_low

    if diff <= 0:
        return None

    fib_levels = {
        "0.0%": Decimal(str(recent_high)),
        "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(
            Decimal("0.00001"), rounding=ROUND_DOWN
        ),
        "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(
            Decimal("0.00001"), rounding=ROUND_DOWN
        ),
        "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(
            Decimal("0.00001"), rounding=ROUND_DOWN
        ),
        "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(
            Decimal("0.00001"), rounding=ROUND_DOWN
        ),
        "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(
            Decimal("0.00001"), rounding=ROUND_DOWN
        ),
        "100.0%": Decimal(str(recent_low)),
    }
    return fib_levels


def calculate_volatility_index(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate a simple Volatility Index based on ATR normalized by price."""
    if len(df) < period or "ATR" not in df.columns:
        return pd.Series(np.nan, index=df.index)

    normalized_atr = df["ATR"] / df["close"]
    volatility_index = normalized_atr.rolling(window=period).mean()
    return volatility_index


def calculate_vwma(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Volume Weighted Moving Average (VWMA)."""
    if len(df) < period or df["volume"].isnull().any():
        return pd.Series(np.nan, index=df.index)

    valid_volume = df["volume"].replace(0, np.nan)
    pv = df["close"] * valid_volume
    vwma = pv.rolling(window=period).sum() / valid_volume.rolling(
        window=period
    ).sum()
    return vwma


def calculate_volume_delta(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Volume Delta, indicating buying vs selling pressure."""
    if len(df) < MIN_DATA_POINTS_VOLATILITY:
        return pd.Series(np.nan, index=df.index)

    buy_volume = df["volume"].where(df["close"] > df["open"], 0)
    sell_volume = df["volume"].where(df["close"] < df["open"], 0)

    buy_volume_sum = buy_volume.rolling(window=period, min_periods=1).sum()
    sell_volume_sum = sell_volume.rolling(window=period, min_periods=1).sum()

    total_volume_sum = buy_volume_sum + sell_volume_sum
    volume_delta = (buy_volume_sum - sell_volume_sum) / total_volume_sum.replace(
        0, np.nan
    )
    return volume_delta.fillna(0)

def _get_mtf_trend(higher_tf_df: pd.DataFrame, config: dict, logger: logging.Logger, symbol: str, indicator_type: str) -> str:
    """Determine trend from higher timeframe using specified indicator."""
    if higher_tf_df.empty:
        return "UNKNOWN"

    last_close = higher_tf_df["close"].iloc[-1]
    period = config["mtf_analysis"]["trend_period"]
    indicator_settings = config["indicator_settings"]

    if indicator_type == "sma":
        if len(higher_tf_df) < period:
            return "UNKNOWN"
        sma = (
            higher_tf_df["close"]
            .rolling(window=period, min_periods=period)
            .mean()
            .iloc[-1]
        )
        if last_close > sma:
            return "UP"
        if last_close < sma:
            return "DOWN"
        return "SIDEWAYS"
    elif indicator_type == "ema":
        if len(higher_tf_df) < period:
            return "UNKNOWN"
        ema = (
            higher_tf_df["close"]
            .ewm(span=period, adjust=False, min_periods=period)
            .mean()
            .iloc[-1]
        )
        if last_close > ema:
            return "UP"
        if last_close < ema:
            return "DOWN"
        return "SIDEWAYS"
    elif indicator_type == "ehlers_supertrend":
        st_result = calculate_ehlers_supertrend(
            df=higher_tf_df,
            period=indicator_settings["ehlers_slow_period"],
            multiplier=indicator_settings["ehlers_slow_multiplier"],
        )
        if st_result is not None and not st_result.empty:
            st_dir = st_result["direction"].iloc[-1]
            if st_dir == 1:
                return "UP"
            if st_dir == -1:
                return "DOWN"
        return "UNKNOWN"
    return "UNKNOWN"
