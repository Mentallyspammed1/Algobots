
from decimal import Decimal
import logging
import logging
import numpy as np
import pandas as pd
import pandas_ta as ta
from typing import Optional, Dict

# Constants from the original script, can be moved to a central config
MIN_DATA_POINTS_TR = 2
MIN_DATA_POINTS_SMOOTHER = 2
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR = 2
MIN_CANDLESTICK_PATTERNS_BARS = 2

class IndicatorCalculator:
    """Calculates various technical indicators."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def _safe_series_op(self, series: pd.Series, op_name: str) -> pd.Series:
        """Safely handle series operations that might result in NaN or inf."""
        if series.empty:
            self.logger.debug(f"Input series for {op_name} is empty.")
            return pd.Series(np.nan, index=[])
        series = pd.to_numeric(series, errors='coerce')
        series.replace([np.inf, -np.inf], np.nan, inplace=True)
        return series

    def calculate_sma(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Simple Moving Average (SMA)."""
        if len(df) < period:
            return pd.Series(np.nan, index=df.index)
        sma = ta.sma(df["close"], length=period)
        return self._safe_series_op(sma, f"SMA_{period}")

    def calculate_ema(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Exponential Moving Average (EMA)."""
        if len(df) < period:
            return pd.Series(np.nan, index=df.index)
        ema = ta.ema(df["close"], length=period)
        return self._safe_series_op(ema, f"EMA_{period}")

    def calculate_true_range(self, df: pd.DataFrame) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(df) < MIN_DATA_POINTS_TR:
            return pd.Series(np.nan, index=df.index)
        high_low = self._safe_series_op(df["high"] - df["low"], "TR_high_low")
        high_prev_close = self._safe_series_op((df["high"] - df["close"].shift()).abs(), "TR_high_prev_close")
        low_prev_close = self._safe_series_op((df["low"] - df["close"].shift()).abs(), "TR_low_prev_close")
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    def calculate_atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Average True Range (ATR)."""
        if len(df) < period:
            return pd.Series(np.nan, index=df.index)
        atr = ta.atr(df["high"], df["low"], df["close"], length=period)
        return self._safe_series_op(atr, f"ATR_{period}")

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER:
            return pd.Series(np.nan, index=series.index)

        series = self._safe_series_op(series, "SuperSmoother_input").dropna()
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
        return filt.reindex(series.index)

    def calculate_ehlers_supertrend(
        self, df: pd.DataFrame, period: int, multiplier: float
    ) -> pd.DataFrame | None:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(df) < period * 3:
            self.logger.debug(
                f"Not enough data for Ehlers SuperTrend (period={period}). Need at least {period*3} bars."
            )
            return None

        df_copy = df.copy()

        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)

        tr = self.calculate_true_range(df_copy)
        smoothed_atr = self.calculate_super_smoother(tr, period)

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr
        
        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty:
            self.logger.debug(
                "Ehlers SuperTrend: DataFrame empty after smoothing. Returning None."
            )
            return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        if df_copy.empty:
            return None

        first_valid_idx = df_copy.index[0]
        supertrend.loc[first_valid_idx] = lower_band.loc[first_valid_idx] if df_copy["close"].loc[first_valid_idx] > lower_band.loc[first_valid_idx] else upper_band.loc[first_valid_idx]
        direction.loc[first_valid_idx] = 1 if df_copy["close"].loc[first_valid_idx] > supertrend.loc[first_valid_idx] else -1


        for i in range(1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 1:
                supertrend.loc[current_idx] = max(lower_band.loc[current_idx], prev_supertrend)
                if curr_close < supertrend.loc[current_idx]:
                    direction.loc[current_idx] = -1
            else:
                supertrend.loc[current_idx] = min(upper_band.loc[current_idx], prev_supertrend)
                if curr_close > supertrend.loc[current_idx]:
                    direction.loc[current_idx] = 1

            if pd.isna(supertrend.loc[current_idx]):
                 supertrend.loc[current_idx] = lower_band.loc[current_idx] if curr_close > lower_band.loc[current_idx] else upper_band.loc[current_idx]


        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(df.index)

    def calculate_macd(
        self, df: pd.DataFrame, fast_period: int, slow_period: int, signal_period: int
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        macd_result = ta.macd(df["close"], fast=fast_period, slow=slow_period, signal=signal_period)
        if macd_result.empty:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        macd_line = self._safe_series_op(macd_result[f'MACD_{fast_period}_{slow_period}_{signal_period}'], "MACD_Line")
        signal_line = self._safe_series_op(macd_result[f'MACDs_{fast_period}_{slow_period}_{signal_period}'], "MACD_Signal")
        histogram = self._safe_series_op(macd_result[f'MACDh_{fast_period}_{slow_period}_{signal_period}'], "MACD_Hist")
        
        return macd_line, signal_line, histogram

    def calculate_rsi(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(df) <= period:
            return pd.Series(np.nan, index=df.index)
        rsi = ta.rsi(df["close"], length=period)
        return self._safe_series_op(rsi, "RSI")

    def calculate_stoch_rsi(
        self, df: pd.DataFrame, period: int, k_period: int, d_period: int
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(df) <= period:
            return pd.Series(np.nan, index=df.index), pd.Series(
                np.nan, index=df.index
            )
        stochrsi = ta.stochrsi(df["close"], length=period, rsi_length=period, k=k_period, d=d_period)
        
        stoch_rsi_k = self._safe_series_op(stochrsi[f'STOCHRSIk_{period}_{period}_{k_period}_{d_period}'], "StochRSI_K")
        stoch_rsi_d = self._safe_series_op(stochrsi[f'STOCHRSId_{period}_{period}_{k_period}_{d_period}'], "StochRSI_D")

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, df: pd.DataFrame, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(df) < period * 2:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        adx_result = ta.adx(df["high"], df["low"], df["close"], length=period)
        
        adx_val = self._safe_series_op(adx_result[f'ADX_{period}'], "ADX")
        plus_di = self._safe_series_op(adx_result[f'DMP_{period}'], "PlusDI")
        minus_di = self._safe_series_op(adx_result[f'DMN_{period}'], "MinusDI")
        
        return adx_val, plus_di, minus_di

    def calculate_bollinger_bands(
        self, df: pd.DataFrame, period: int, std_dev: float
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(df) < period:
            return (
                pd.Series(np.nan, index=df.index),
                pd.Series(np.nan, index=df.index),
                pd.Series(np.nan, index=df.index),
            )
        bbands = ta.bbands(df["close"], length=period, std=std_dev)
        
        upper_band = self._safe_series_op(bbands[f'BBU_{period}_{std_dev}'], "BB_Upper")
        middle_band = self._safe_series_op(bbands[f'BBM_{period}_{std_dev}'], "BB_Middle")
        lower_band = self._safe_series_op(bbands[f'BBL_{period}_{std_dev}'], "BB_Lower")
        
        return upper_band, middle_band, lower_band

    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if df.empty:
            return pd.Series(np.nan, index=df.index)
        
        vwap = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
        return self._safe_series_op(vwap, "VWAP")

    def calculate_cci(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(df) < period:
            return pd.Series(np.nan, index=df.index)
        cci = ta.cci(df["high"], df["low"], df["close"], length=period)
        return self._safe_series_op(cci, "CCI")

    def calculate_williams_r(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(df) < period:
            return pd.Series(np.nan, index=df.index)
        wr = ta.willr(df["high"], df["low"], df["close"], length=period)
        return self._safe_series_op(wr, "WR")

    def calculate_ichimoku_cloud(
        self, df: pd.DataFrame, tenkan_period: int, kijun_period: int, senkou_span_b_period: int, chikou_span_offset: int
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

        ichimoku = ta.ichimoku(
            df["high"], df["low"], df["close"],
            tenkan=tenkan_period,
            kijun=kijun_period,
            senkou=senkou_span_b_period,
            offset=chikou_span_offset,
        )
        
        tenkan_sen = self._safe_series_op(ichimoku[f'ITS_{tenkan_period}_{kijun_period}_{senkou_span_b_period}'], "Tenkan_Sen")
        kijun_sen = self._safe_series_op(ichimoku[f'IKS_{tenkan_period}_{kijun_period}_{senkou_span_b_period}'], "Kijun_Sen")
        senkou_span_a = self._safe_series_op(ichimoku[f'ISA_{tenkan_period}_{kijun_period}_{senkou_span_b_period}'], "Senkou_Span_A")
        senkou_span_b = self._safe_series_op(ichimoku[f'ISB_{tenkan_period}_{kijun_period}_{senkou_span_b_period}'], "Senkou_Span_B")
        chikou_span = self._safe_series_op(ichimoku[f'ICH_B_{tenkan_period}_{kijun_period}_{senkou_span_b_period}'], "Chikou_Span")

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(df) <= period:
            return pd.Series(np.nan, index=df.index)
        mfi = ta.mfi(df["high"], df["low"], df["close"], df["volume"], length=period)
        return self._safe_series_op(mfi, "MFI")

    def calculate_obv(self, df: pd.DataFrame, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(df) < MIN_DATA_POINTS_OBV:
            return pd.Series(np.nan), pd.Series(np.nan)

        obv = ta.obv(df["close"], df["volume"])
        obv_ema = ta.ema(obv, length=ema_period)

        return self._safe_series_op(obv, "OBV"), self._safe_series_op(obv_ema, "OBV_EMA")

    def calculate_cmf(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(df) < period:
            return pd.Series(np.nan)

        cmf = ta.cmf(df["high"], df["low"], df["close"], df["volume"], length=period)
        return self._safe_series_op(cmf, "CMF")

    def calculate_psar(
        self, df: pd.DataFrame, acceleration: float, max_acceleration: float
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(df) < MIN_DATA_POINTS_PSAR:
            return pd.Series(np.nan, index=df.index), pd.Series(
                np.nan, index=df.index
            )
        
        psar_result = ta.psar(df["high"], df["low"], df["close"], af0=acceleration, af=acceleration, max_af=max_acceleration)
        
        psar_val = self._safe_series_op(psar_result[f'PSAR_{acceleration}_{max_acceleration}'], "PSAR_Val")
        psar_long = psar_result[f'PSARl_{acceleration}_{max_acceleration}']
        psar_short = psar_result[f'PSARs_{acceleration}_{max_acceleration}']

        psar_dir = pd.Series(0, index=df.index, dtype=int)
        psar_dir[df['close'] > psar_long.fillna(0)] = 1
        psar_dir[df['close'] < psar_short.fillna(0)] = -1
        psar_dir.mask(psar_dir == 0, psar_dir.shift(1), inplace=True)
        psar_dir.fillna(0, inplace=True);

        return psar_val, psar_dir

    def calculate_volatility_index(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate a simple Volatility Index based on ATR normalized by price."""
        if len(df) < period or "ATR" not in df.columns or df["ATR"].isnull().all():
            return pd.Series(np.nan, index=df.index)

        normalized_atr = df["ATR"] / df["close"].replace(0, np.nan)
        volatility_index = normalized_atr.rolling(window=period).mean()
        return volatility_index

    def calculate_vwma(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Volume Weighted Moving Average (VWMA)."""
        if len(df) < period or df["volume"].isnull().any():
            return pd.Series(np.nan, index=df.index)

        valid_volume = df["volume"].replace(0, np.nan)
        pv = df["close"] * valid_volume
        vwma = pv.rolling(window=period).sum() / valid_volume.rolling(window=period).sum()
        return vwma

    def calculate_volume_delta(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Volume Delta, indicating buying vs selling pressure."""
        if len(df) < 2: # MIN_DATA_POINTS_VOLATILITY is 2
            return pd.Series(np.nan, index=df.index)

        buy_volume = df["volume"].where(df["close"] > df["open"], 0)
        sell_volume = df["volume"].where(df["close"] < df["open"], 0)

        buy_volume_sum = buy_volume.rolling(window=period, min_periods=1).sum()
        sell_volume_sum = sell_volume.rolling(window=period, min_periods=1).sum()

        total_volume_sum = buy_volume_sum + sell_volume_sum
        volume_delta = (buy_volume_sum - sell_volume_sum) / total_volume_sum.replace(0, np.nan)
        return volume_delta.fillna(0)

    def calculate_kaufman_ama(self, df: pd.DataFrame, period: int, fast_period: int, slow_period: int) -> pd.Series:
        """Calculate Kaufman's Adaptive Moving Average (KAMA)."""
        if len(df) < period + slow_period:
            return pd.Series(np.nan, index=df.index)

        kama = ta.kama(df["close"], length=period, fast=fast_period, slow=slow_period)
        return self._safe_series_op(kama, "Kaufman_AMA")

    def calculate_relative_volume(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Relative Volume (RVOL)."""
        if len(df) < period:
            return pd.Series(np.nan, index=df.index)

        avg_volume = df["volume"].rolling(window=period, min_periods=period).mean()
        relative_volume = (df["volume"] / avg_volume.replace(0, np.nan)).fillna(1.0)
        return self._safe_series_op(relative_volume, "Relative_Volume")

    def calculate_market_structure(self, df: pd.DataFrame, lookback_period: int) -> pd.Series:
        """Determine market structure (uptrend, downtrend, sideways) based on higher highs/lows."""
        if len(df) < lookback_period * 2:
            return pd.Series("UNKNOWN", index=df.index, dtype="object")

        # Identify swing highs and lows (simplified for demonstration)
        # A more robust implementation would use fractal analysis or similar
        is_swing_high = (df["high"] > df["high"].shift(1)) & (df["high"] > df["high"].shift(-1))
        is_swing_low = (df["low"] < df["low"].shift(1)) & (df["low"] < df["low"].shift(-1))

        swing_highs = df["high"][is_swing_high]
        swing_lows = df["low"][is_swing_low]

        trend_series = pd.Series("SIDEWAYS", index=df.index, dtype="object")

        for i in range(lookback_period, len(df)):
            recent_swing_highs = swing_highs.loc[df.index[i-lookback_period]:df.index[i]]
            recent_swing_lows = swing_lows.loc[df.index[i-lookback_period]:df.index[i]]

            if len(recent_swing_highs) >= 2 and len(recent_swing_lows) >= 2:
                latest_high = recent_swing_highs.iloc[-1]
                second_latest_high = recent_swing_highs.iloc[-2]
                latest_low = recent_swing_lows.iloc[-1]
                second_latest_low = recent_swing_lows.iloc[-2]

                if latest_high > second_latest_high and latest_low > second_latest_low:
                    trend_series.iloc[i] = "UP"
                elif latest_high < second_latest_high and latest_low < second_latest_low:
                    trend_series.iloc[i] = "DOWN"
                else:
                    trend_series.iloc[i] = "SIDEWAYS"
            else:
                trend_series.iloc[i] = "UNKNOWN" # Not enough swing points

        return trend_series

    def calculate_dema(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Double Exponential Moving Average (DEMA)."""
        if len(df) < 2 * period:
            return pd.Series(np.nan, index=df.index)

        dema = ta.dema(df["close"], length=period)
        return self._safe_series_op(dema, "DEMA")

    def calculate_keltner_channels(
        self, df: pd.DataFrame, period: int, atr_multiplier: float
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Keltner Channels."""
        if len(df) < period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        keltner = ta.kc(df["high"], df["low"], df["close"], length=period, atr_length=period, scalar=atr_multiplier)
        
        upper_band = self._safe_series_op(keltner[f'KCU_{period}_{atr_multiplier}'], "Keltner_Upper")
        middle_band = self._safe_series_op(keltner[f'KCM_{period}_{atr_multiplier}'], "Keltner_Middle")
        lower_band = self._safe_series_op(keltner[f'KCL_{period}_{atr_multiplier}'], "Keltner_Lower")

        return upper_band, middle_band, lower_band

    def calculate_roc(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Rate of Change (ROC)."""
        if len(df) <= period:
            return pd.Series(np.nan, index=df.index)

        roc = ta.roc(df["close"], length=period)
        return self._safe_series_op(roc, "ROC")

    def detect_candlestick_patterns(self, df: pd.DataFrame) -> str:
        """Detect common candlestick patterns."""
        if len(df) < MIN_CANDLESTICK_PATTERNS_BARS:
            return "No Pattern"

        i = len(df) - 1
        current_bar = df.iloc[i]
        prev_bar = df.iloc[i - 1]

        if any(pd.isna(val) for val in [current_bar["open"], current_bar["close"], current_bar["high"], current_bar["low"],
                                        prev_bar["open"], prev_bar["close"], prev_bar["high"], prev_bar["low"]]):
            return "No Pattern"

        # Bullish Engulfing
        if (
            current_bar["open"] < prev_bar["close"]
            and current_bar["close"] > prev_bar["open"]
            and current_bar["close"] > current_bar["open"]
            and prev_bar["close"] < prev_bar["open"]
        ):
            return "Bullish Engulfing"
        # Bearish Engulfing
        if (
            current_bar["open"] > prev_bar["close"]
            and current_bar["close"] < prev_bar["open"]
            and current_bar["close"] < current_bar["open"]
            and prev_bar["close"] > prev_bar["open"]
        ):
            return "Bearish Engulfing"
        # Bullish Hammer
        if (
            current_bar["close"] > current_bar["open"]
            and abs(current_bar["close"] - current_bar["open"])
            <= (current_bar["high"] - current_bar["low"]) * 0.3
            and (current_bar["open"] - current_bar["low"])
            >= 2 * abs(current_bar["close"] - current_bar["open"])
            and (current_bar["high"] - current_bar["close"])
            <= 0.5 * abs(current_bar["close"] - current_bar["open"])
        ):
            return "Bullish Hammer"
        # Bearish Shooting Star
        if (
            current_bar["close"] < current_bar["open"]
            and abs(current_bar["close"] - current_bar["open"])
            <= (current_bar["high"] - current_bar["low"]) * 0.3
            and (current_bar["high"] - current_bar["open"])
            >= 2 * abs(current_bar["close"] - current_bar["open"])
            and (current_bar["close"] - current_bar["low"])
            <= 0.5 * abs(current_bar["close"] - current_bar["open"])
        ):
            return "Bearish Shooting Star"

        return "No Pattern"

    def calculate_fibonacci_pivot_points(self, df: pd.DataFrame) -> dict[str, Decimal]:
        """Calculate Fibonacci Pivot Points (Pivot, R1, R2, S1, S2)."""
        if df.empty or len(df) < 2:
            return {}

        prev_high = df["high"].iloc[-2]
        prev_low = df["low"].iloc[-2]
        prev_close = df["close"].iloc[-2]

        pivot = (prev_high + prev_low + prev_close) / 3

        r1 = pivot + (prev_high - prev_low) * 0.382
        r2 = pivot + (prev_high - prev_low) * 0.618
        s1 = pivot - (prev_high - prev_low) * 0.382
        s2 = pivot - (prev_high - prev_low) * 0.618

        # Return as a dictionary, will be quantized by TradingAnalyzer
        return {
            "Pivot": Decimal(str(pivot)),
            "R1": Decimal(str(r1)),
            "R2": Decimal(str(r2)),
            "S1": Decimal(str(s1)),
            "S2": Decimal(str(s2)),
        }

    def calculate_support_resistance_from_orderbook(self, bids: list, asks: list) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """Calculates support and resistance levels from orderbook data based on volume concentration.
        Identifies the highest volume bid as support and highest volume ask as resistance.
        """
        max_bid_volume = Decimal("0")
        support_level = None
        for bid_price_str, bid_volume_str in bids:
            bid_volume_decimal = Decimal(bid_volume_str)
            if bid_volume_decimal > max_bid_volume:
                max_bid_volume = bid_volume_decimal
                support_level = Decimal(bid_price_str)

        max_ask_volume = Decimal("0")
        resistance_level = None
        for ask_price_str, ask_volume_str in asks:
            ask_volume_decimal = Decimal(ask_volume_str)
            if ask_volume_decimal > max_ask_volume:
                max_ask_volume = ask_volume_decimal
                resistance_level = Decimal(ask_price_str)

        return support_level, resistance_level
