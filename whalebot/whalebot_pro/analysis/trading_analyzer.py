import logging
import time
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
from colorama import Fore, Style

# Import local modules
from whalebot_pro.analysis.indicators import IndicatorCalculator
from whalebot_pro.orderbook.advanced_orderbook_manager import AdvancedOrderbookManager

# Color Scheme
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
NEON_BLUE = Fore.CYAN
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_CYAN = Fore.CYAN
RESET = Style.RESET_ALL

# Magic Numbers as Constants (from original script)
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20
STOCH_RSI_MID_POINT = 50


class TradingAnalyzer:
    """Analyzes trading data and generates signals with MTF and Ehlers SuperTrend."""

    def __init__(
        self,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
        indicator_calculator: IndicatorCalculator,
    ):
        """Initializes the TradingAnalyzer."""
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.indicator_calculator = indicator_calculator
        self.df: pd.DataFrame = pd.DataFrame()  # Current DataFrame for calculations
        self.indicator_values: dict[str, float | str | Decimal] = {}
        self.fib_levels: dict[str, Decimal] = {}
        self.weights = config.get(
            "active_weights", {}
        )  # Use active_weights from config
        self.indicator_settings = config["indicator_settings"]
        self._last_signal_ts = 0  # Initialize last signal timestamp
        self._last_signal_score = 0.0  # Initialize last signal score

    def update_data(self, new_df: pd.DataFrame):
        """Updates the internal DataFrame and recalculates indicators."""
        if new_df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}TradingAnalyzer received an empty DataFrame. Skipping indicator recalculation.{RESET}"
            )
            return

        self.df = new_df.copy()
        self._calculate_all_indicators()
        if self.config["indicators"].get("fibonacci_levels", False):
            self.calculate_fibonacci_levels()

    def _safe_calculate(
        self, func: callable, name: str, min_data_points: int = 0, *args, **kwargs
    ) -> Any | None:
        """Safely calculate indicators and log errors, with min_data_points check."""
        if self.df.empty:
            self.logger.debug(f"Skipping indicator '{name}': DataFrame is empty.")
            return None
        if len(self.df) < min_data_points:
            self.logger.debug(
                f"Skipping indicator '{name}': Not enough data. Need {min_data_points}, have {len(self.df)}."
            )
            return None
        try:
            result = func(*args, **kwargs)
            if (
                result is None
                or (isinstance(result, pd.Series) and result.empty)
                or (isinstance(result, pd.DataFrame) and result.empty)
                or (
                    isinstance(result, tuple)
                    and all(
                        r is None
                        or (isinstance(r, pd.Series) and r.empty)
                        or (isinstance(r, pd.DataFrame) and r.empty)
                        for r in result
                    )
                )
            ):
                self.logger.warning(
                    f"{NEON_YELLOW}Indicator '{name}' returned empty or None after calculation. Not enough valid data?{RESET}"
                )
                return None
            return result
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}Error calculating indicator '{name}': {e}{RESET}"
            )
            return None

    def _calculate_all_indicators(self) -> None:
        """Calculate all enabled technical indicators, including Ehlers SuperTrend."""
        self.logger.debug("Calculating technical indicators...")
        cfg = self.config
        isd = self.indicator_settings

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}Cannot calculate indicators: DataFrame is empty.{RESET}"
            )
            return

        # SMA
        if cfg["indicators"].get("sma_10", False):
            self.df["SMA_10"] = self._safe_calculate(
                self.indicator_calculator.calculate_sma,
                "SMA_10",
                min_data_points=isd["sma_short_period"],
                df=self.df,
                period=isd["sma_short_period"],
            )
            if self.df["SMA_10"] is not None and not self.df["SMA_10"].empty:
                self.indicator_values["SMA_10"] = self.df["SMA_10"].iloc[-1]
        if cfg["indicators"].get("sma_trend_filter", False):
            self.df["SMA_Long"] = self._safe_calculate(
                self.indicator_calculator.calculate_sma,
                "SMA_Long",
                min_data_points=isd["sma_long_period"],
                df=self.df,
                period=isd["sma_long_period"],
            )
            if self.df["SMA_Long"] is not None and not self.df["SMA_Long"].empty:
                self.indicator_values["SMA_Long"] = self.df["SMA_Long"].iloc[-1]

        # EMA
        if cfg["indicators"].get("ema_alignment", False):
            self.df["EMA_Short"] = self._safe_calculate(
                self.indicator_calculator.calculate_ema,
                "EMA_Short",
                min_data_points=isd["ema_short_period"],
                df=self.df,
                period=isd["ema_short_period"],
            )
            self.df["EMA_Long"] = self._safe_calculate(
                self.indicator_calculator.calculate_ema,
                "EMA_Long",
                min_data_points=isd["ema_long_period"],
                df=self.df,
                period=isd["ema_long_period"],
            )
            if self.df["EMA_Short"] is not None and not self.df["EMA_Short"].empty:
                self.indicator_values["EMA_Short"] = self.df["EMA_Short"].iloc[-1]
            if self.df["EMA_Long"] is not None and not self.df["EMA_Long"].empty:
                self.indicator_values["EMA_Long"] = self.df["EMA_Long"].iloc[-1]

        # ATR
        self.df["TR"] = self._safe_calculate(
            self.indicator_calculator.calculate_true_range,
            "TR",
            min_data_points=2,
            df=self.df,
        )
        self.df["ATR"] = self._safe_calculate(
            self.indicator_calculator.calculate_atr,
            "ATR",
            min_data_points=isd["atr_period"],
            df=self.df,
            period=isd["atr_period"],
        )
        if self.df["ATR"] is not None and not self.df["ATR"].empty:
            self.indicator_values["ATR"] = self.df["ATR"].iloc[-1]

        # RSI
        if cfg["indicators"].get("rsi", False):
            self.df["RSI"] = self._safe_calculate(
                self.indicator_calculator.calculate_rsi,
                "RSI",
                min_data_points=isd["rsi_period"] + 1,
                df=self.df,
                period=isd["rsi_period"],
            )
            if self.df["RSI"] is not None and not self.df["RSI"].empty:
                self.indicator_values["RSI"] = self.df["RSI"].iloc[-1]

        # Stochastic RSI
        if cfg["indicators"].get("stoch_rsi", False):
            stoch_rsi_k, stoch_rsi_d = self._safe_calculate(
                self.indicator_calculator.calculate_stoch_rsi,
                "StochRSI",
                min_data_points=isd["stoch_rsi_period"]
                + isd["stoch_d_period"]
                + isd["stoch_k_period"],
                df=self.df,
                period=isd["stoch_rsi_period"],
                k_period=isd["stoch_k_period"],
                d_period=isd["stoch_d_period"],
            )
            if stoch_rsi_k is not None and not stoch_rsi_k.empty:
                self.df["StochRSI_K"] = stoch_rsi_k
                self.indicator_values["StochRSI_K"] = stoch_rsi_k.iloc[-1]
            if stoch_rsi_d is not None and not stoch_rsi_d.empty:
                self.df["StochRSI_D"] = stoch_rsi_d
                self.indicator_values["StochRSI_D"] = stoch_rsi_d.iloc[-1]

        # Bollinger Bands
        if cfg["indicators"].get("bollinger_bands", False):
            bb_upper, bb_middle, bb_lower = self._safe_calculate(
                self.indicator_calculator.calculate_bollinger_bands,
                "BollingerBands",
                min_data_points=isd["bollinger_bands_period"],
                df=self.df,
                period=isd["bollinger_bands_period"],
                std_dev=isd["bollinger_bands_std_dev"],
            )
            if bb_upper is not None and not bb_upper.empty:
                self.df["BB_Upper"] = bb_upper
                self.indicator_values["BB_Upper"] = bb_upper.iloc[-1]
            if bb_middle is not None and not bb_middle.empty:
                self.df["BB_Middle"] = bb_middle
                self.indicator_values["BB_Middle"] = bb_middle.iloc[-1]
            if bb_lower is not None and not bb_lower.empty:
                self.df["BB_Lower"] = bb_lower
                self.indicator_values["BB_Lower"] = bb_lower.iloc[-1]

        # CCI
        if cfg["indicators"].get("cci", False):
            self.df["CCI"] = self._safe_calculate(
                self.indicator_calculator.calculate_cci,
                "CCI",
                min_data_points=isd["cci_period"],
                df=self.df,
                period=isd["cci_period"],
            )
            if self.df["CCI"] is not None and not self.df["CCI"].empty:
                self.indicator_values["CCI"] = self.df["CCI"].iloc[-1]

        # Williams %R
        if cfg["indicators"].get("wr", False):
            self.df["WR"] = self._safe_calculate(
                self.indicator_calculator.calculate_williams_r,
                "WR",
                min_data_points=isd["williams_r_period"],
                df=self.df,
                period=isd["williams_r_period"],
            )
            if self.df["WR"] is not None and not self.df["WR"].empty:
                self.indicator_values["WR"] = self.df["WR"].iloc[-1]

        # MFI
        if cfg["indicators"].get("mfi", False):
            self.df["MFI"] = self._safe_calculate(
                self.indicator_calculator.calculate_mfi,
                "MFI",
                min_data_points=isd["mfi_period"] + 1,
                df=self.df,
                period=isd["mfi_period"],
            )
            if self.df["MFI"] is not None and not self.df["MFI"].empty:
                self.indicator_values["MFI"] = self.df["MFI"].iloc[-1]

        # OBV
        if cfg["indicators"].get("obv", False):
            obv_val, obv_ema = self._safe_calculate(
                self.indicator_calculator.calculate_obv,
                "OBV",
                min_data_points=isd["obv_ema_period"],
                df=self.df,
                ema_period=isd["obv_ema_period"],
            )
            if obv_val is not None and not obv_val.empty:
                self.df["OBV"] = obv_val
                self.indicator_values["OBV"] = obv_val.iloc[-1]
            if obv_ema is not None and not obv_ema.empty:
                self.df["OBV_EMA"] = obv_ema
                self.indicator_values["OBV_EMA"] = obv_ema.iloc[-1]

        # CMF
        if cfg["indicators"].get("cmf", False):
            cmf_val = self._safe_calculate(
                self.indicator_calculator.calculate_cmf,
                "CMF",
                min_data_points=isd["cmf_period"],
                df=self.df,
                period=isd["cmf_period"],
            )
            if cmf_val is not None and not cmf_val.empty:
                self.df["CMF"] = cmf_val
                self.indicator_values["CMF"] = cmf_val.iloc[-1]

        # Ichimoku Cloud
        if cfg["indicators"].get("ichimoku_cloud", False):
            tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span = (
                self._safe_calculate(
                    self.indicator_calculator.calculate_ichimoku_cloud,
                    "IchimokuCloud",
                    min_data_points=max(
                        isd["ichimoku_tenkan_period"],
                        isd["ichimoku_kijun_period"],
                        isd["ichimoku_senkou_span_b_period"],
                    )
                    + isd["ichimoku_chikou_span_offset"],
                    df=self.df,
                    tenkan_period=isd["ichimoku_tenkan_period"],
                    kijun_period=isd["ichimoku_kijun_period"],
                    senkou_span_b_period=isd["ichimoku_senkou_span_b_period"],
                    chikou_span_offset=isd["ichimoku_chikou_span_offset"],
                )
            )
            if tenkan_sen is not None and not tenkan_sen.empty:
                self.df["Tenkan_Sen"] = tenkan_sen
                self.indicator_values["Tenkan_Sen"] = tenkan_sen.iloc[-1]
            if kijun_sen is not None and not kijun_sen.empty:
                self.df["Kijun_Sen"] = kijun_sen
                self.indicator_values["Kijun_Sen"] = kijun_sen.iloc[-1]
            if senkou_span_a is not None and not senkou_span_a.empty:
                self.df["Senkou_Span_A"] = senkou_span_a
                self.indicator_values["Senkou_Span_A"] = senkou_span_a.iloc[-1]
            if senkou_span_b is not None and not senkou_span_b.empty:
                self.df["Senkou_Span_B"] = senkou_span_b
                self.indicator_values["Senkou_Span_B"] = senkou_span_b.iloc[-1]
            if chikou_span is not None and not chikou_span.empty:
                self.df["Chikou_Span"] = chikou_span
                self.indicator_values["Chikou_Span"] = chikou_span.fillna(0).iloc[-1]

        # PSAR
        if cfg["indicators"].get("psar", False):
            psar_val, psar_dir = self._safe_calculate(
                self.indicator_calculator.calculate_psar,
                "PSAR",
                min_data_points=isd["psar_acceleration"],
                df=self.df,
                acceleration=isd["psar_acceleration"],
                max_acceleration=isd["psar_max_acceleration"],
            )
            if psar_val is not None and not psar_val.empty:
                self.df["PSAR_Val"] = psar_val
                self.indicator_values["PSAR_Val"] = psar_val.iloc[-1]
            if psar_dir is not None and not psar_dir.empty:
                self.df["PSAR_Dir"] = psar_dir
                self.indicator_values["PSAR_Dir"] = psar_dir.iloc[-1]

        # VWAP
        if cfg["indicators"].get("vwap", False):
            self.df["VWAP"] = self._safe_calculate(
                self.indicator_calculator.calculate_vwap,
                "VWAP",
                min_data_points=1,
                df=self.df,
            )
            if self.df["VWAP"] is not None and not self.df["VWAP"].empty:
                self.indicator_values["VWAP"] = self.df["VWAP"].iloc[-1]

        # Ehlers SuperTrend Calculation
        if cfg["indicators"].get("ehlers_supertrend", False):
            st_fast_result = self._safe_calculate(
                self.indicator_calculator.calculate_ehlers_supertrend,
                "EhlersSuperTrendFast",
                min_data_points=isd["ehlers_fast_period"] * 3,
                df=self.df,
                period=isd["ehlers_fast_period"],
                multiplier=isd["ehlers_fast_multiplier"],
            )
            if st_fast_result is not None and not st_fast_result.empty:
                self.df["ST_Fast_Dir"] = st_fast_result["direction"]
                self.df["ST_Fast_Val"] = st_fast_result["supertrend"]
                self.indicator_values["ST_Fast_Dir"] = st_fast_result["direction"].iloc[
                    -1
                ]
                self.indicator_values["ST_Fast_Val"] = st_fast_result[
                    "supertrend"
                ].iloc[-1]

            st_slow_result = self._safe_calculate(
                self.indicator_calculator.calculate_ehlers_supertrend,
                "EhlersSuperTrendSlow",
                min_data_points=isd["ehlers_slow_period"] * 3,
                df=self.df,
                period=isd["ehlers_slow_period"],
                multiplier=isd["ehlers_slow_multiplier"],
            )
            if st_slow_result is not None and not st_slow_result.empty:
                self.df["ST_Slow_Dir"] = st_slow_result["direction"]
                self.df["ST_Slow_Val"] = st_slow_result["supertrend"]
                self.indicator_values["ST_Slow_Dir"] = st_slow_result["direction"].iloc[
                    -1
                ]
                self.indicator_values["ST_Slow_Val"] = st_slow_result[
                    "supertrend"
                ].iloc[-1]

        # MACD
        if cfg["indicators"].get("macd", False):
            macd_line, signal_line, histogram = self._safe_calculate(
                self.indicator_calculator.calculate_macd,
                "MACD",
                min_data_points=isd["macd_slow_period"] + isd["macd_signal_period"],
                df=self.df,
                fast_period=isd["macd_fast_period"],
                slow_period=isd["macd_slow_period"],
                signal_period=isd["macd_signal_period"],
            )
            if macd_line is not None and not macd_line.empty:
                self.df["MACD_Line"] = macd_line
                self.indicator_values["MACD_Line"] = macd_line.iloc[-1]
            if signal_line is not None and not signal_line.empty:
                self.df["MACD_Signal"] = signal_line
                self.indicator_values["MACD_Signal"] = signal_line.iloc[-1]
            if histogram is not None and not histogram.empty:
                self.df["MACD_Hist"] = histogram
                self.indicator_values["MACD_Hist"] = histogram.iloc[-1]

        # ADX
        if cfg["indicators"].get("adx", False):
            adx_val, plus_di, minus_di = self._safe_calculate(
                self.indicator_calculator.calculate_adx,
                "ADX",
                min_data_points=isd["adx_period"] * 2,
                df=self.df,
                period=isd["adx_period"],
            )
            if adx_val is not None and not adx_val.empty:
                self.df["ADX"] = adx_val
                self.indicator_values["ADX"] = adx_val.iloc[-1]
            if plus_di is not None and not plus_di.empty:
                self.df["PlusDI"] = plus_di
                self.indicator_values["PlusDI"] = plus_di.iloc[-1]
            if minus_di is not None and not minus_di.empty:
                self.df["MinusDI"] = minus_di
                self.indicator_values["MinusDI"] = minus_di.iloc[-1]

        # Volatility Index
        if cfg["indicators"].get("volatility_index", False):
            self.df["Volatility_Index"] = self._safe_calculate(
                self.indicator_calculator.calculate_volatility_index,
                "Volatility_Index",
                min_data_points=isd["volatility_index_period"],
                df=self.df,
                period=isd["volatility_index_period"],
            )
            if (
                self.df["Volatility_Index"] is not None
                and not self.df["Volatility_Index"].empty
            ):
                self.indicator_values["Volatility_Index"] = self.df[
                    "Volatility_Index"
                ].iloc[-1]

        # VWMA
        if cfg["indicators"].get("vwma", False):
            self.df["VWMA"] = self._safe_calculate(
                self.indicator_calculator.calculate_vwma,
                "VWMA",
                min_data_points=isd["vwma_period"],
                df=self.df,
                period=isd["vwma_period"],
            )
            if self.df["VWMA"] is not None and not self.df["VWMA"].empty:
                self.indicator_values["VWMA"] = self.df["VWMA"].iloc[-1]

        # Volume Delta
        if cfg["indicators"].get("volume_delta", False):
            self.df["Volume_Delta"] = self._safe_calculate(
                self.indicator_calculator.calculate_volume_delta,
                "Volume_Delta",
                min_data_points=isd["volume_delta_period"],
                df=self.df,
                period=isd["volume_delta_period"],
            )
            if (
                self.df["Volume_Delta"] is not None
                and not self.df["Volume_Delta"].empty
            ):
                self.indicator_values["Volume_Delta"] = self.df["Volume_Delta"].iloc[-1]

        # Kaufman's Adaptive Moving Average (KAMA)
        if cfg["indicators"].get("kaufman_ama", False):
            self.df["Kaufman_AMA"] = self._safe_calculate(
                self.indicator_calculator.calculate_kaufman_ama,
                "Kaufman_AMA",
                min_data_points=isd["kama_period"] + isd["kama_slow_period"],
                df=self.df,
                period=isd["kama_period"],
                fast_period=isd["kama_fast_period"],
                slow_period=isd["kama_slow_period"],
            )
            if self.df["Kaufman_AMA"] is not None and not self.df["Kaufman_AMA"].empty:
                self.indicator_values["Kaufman_AMA"] = self.df["Kaufman_AMA"].iloc[-1]

        # Relative Volume
        if cfg["indicators"].get("relative_volume", False):
            self.df["Relative_Volume"] = self._safe_calculate(
                self.indicator_calculator.calculate_relative_volume,
                "Relative_Volume",
                min_data_points=isd["relative_volume_period"],
                df=self.df,
                period=isd["relative_volume_period"],
            )
            if (
                self.df["Relative_Volume"] is not None
                and not self.df["Relative_Volume"].empty
            ):
                self.indicator_values["Relative_Volume"] = self.df[
                    "Relative_Volume"
                ].iloc[-1]

        # Market Structure
        if cfg["indicators"].get("market_structure", False):
            self.df["Market_Structure_Trend"] = self._safe_calculate(
                self.indicator_calculator.calculate_market_structure,
                "Market_Structure_Trend",
                min_data_points=isd["market_structure_lookback_period"] * 2,
                df=self.df,
                lookback_period=isd["market_structure_lookback_period"],
            )
            if (
                self.df["Market_Structure_Trend"] is not None
                and not self.df["Market_Structure_Trend"].empty
            ):
                self.indicator_values["Market_Structure_Trend"] = self.df[
                    "Market_Structure_Trend"
                ].iloc[-1]

        # DEMA
        if cfg["indicators"].get("dema", False):
            self.df["DEMA"] = self._safe_calculate(
                self.indicator_calculator.calculate_dema,
                "DEMA",
                min_data_points=isd["dema_period"] * 2,
                df=self.df,
                period=isd["dema_period"],
            )
            if self.df["DEMA"] is not None and not self.df["DEMA"].empty:
                self.indicator_values["DEMA"] = self.df["DEMA"].iloc[-1]

        # Keltner Channels
        if cfg["indicators"].get("keltner_channels", False):
            kc_upper, kc_middle, kc_lower = self._safe_calculate(
                self.indicator_calculator.calculate_keltner_channels,
                "Keltner_Channels",
                min_data_points=isd["keltner_period"] + isd["atr_period"],
                df=self.df,
                period=isd["keltner_period"],
                atr_multiplier=isd["keltner_atr_multiplier"],
            )
            if kc_upper is not None and not kc_upper.empty:
                self.df["Keltner_Upper"] = kc_upper
                self.indicator_values["Keltner_Upper"] = kc_upper.iloc[-1]
            if kc_middle is not None and not kc_middle.empty:
                self.df["Keltner_Middle"] = kc_middle
                self.indicator_values["Keltner_Middle"] = kc_middle.iloc[-1]
            if kc_lower is not None and not kc_lower.empty:
                self.df["Keltner_Lower"] = kc_lower
                self.indicator_values["Keltner_Lower"] = kc_lower.iloc[-1]

        # ROC
        if cfg["indicators"].get("roc", False):
            self.df["ROC"] = self._safe_calculate(
                self.indicator_calculator.calculate_roc,
                "ROC",
                min_data_points=isd["roc_period"] + 1,
                df=self.df,
                period=isd["roc_period"],
            )
            if self.df["ROC"] is not None and not self.df["ROC"].empty:
                self.indicator_values["ROC"] = self.df["ROC"].iloc[-1]

        # Candlestick Patterns
        if cfg["indicators"].get("candlestick_patterns", False):
            pattern = self._safe_calculate(
                self.indicator_calculator.detect_candlestick_patterns,
                "Candlestick_Pattern",
                min_data_points=isd["min_candlestick_patterns_bars"],
                df=self.df,
            )
            if pattern is not None:
                self.indicator_values["Candlestick_Pattern"] = pattern

        # Fibonacci Pivot Points
        if cfg["indicators"].get("fibonacci_pivot_points", False):
            fib_pivots = self._safe_calculate(
                self.indicator_calculator.calculate_fibonacci_pivot_points,
                "Fibonacci_Pivot_Points",
                min_data_points=2,
                df=self.df,
            )
            if fib_pivots is not None:
                self.indicator_values.update(fib_pivots)

        # Final cleanup for indicator columns
        initial_len = len(self.df)
        self.df.dropna(subset=["close"], inplace=True)

        for col in self.df.columns:
            if col not in ["open", "high", "low", "close", "volume", "turnover"]:
                self.df[col].fillna(method="ffill", inplace=True)
                self.df[col].fillna(0, inplace=True)

        if len(self.df) < initial_len:
            self.logger.debug(
                f"Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations."
            )

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}DataFrame is empty after calculating all indicators and dropping NaNs.{RESET}"
            )
        else:
            self.logger.debug(
                f"Indicators calculated. Final DataFrame size: {len(self.df)}"
            )

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(
                f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}"
            )
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()

        diff = recent_high - recent_low

        if diff <= 0:  # Handle cases where high and low are the same or inverted
            self.logger.warning(
                f"{NEON_YELLOW}Invalid high-low range for Fibonacci calculation. Diff: {diff}{RESET}"
            )
            return

        decimal_high = Decimal(str(recent_high))
        decimal_low = Decimal(str(recent_low))
        decimal_diff = Decimal(str(diff))

        self.fib_levels = {
            "0.0%": decimal_high,
            "23.6%": (decimal_high - Decimal("0.236") * decimal_diff),
            "38.2%": (decimal_high - Decimal("0.382") * decimal_diff),
            "50.0%": (decimal_high - Decimal("0.500") * decimal_diff),
            "61.8%": (decimal_high - Decimal("0.618") * decimal_diff),
            "78.6%": (decimal_high - Decimal("0.786") * decimal_diff),
            "100.0%": decimal_low,
        }
        # Quantize all Fibonacci levels to a reasonable precision (e.g., 5 decimal places)
        for level_name, level_price in self.fib_levels.items():
            self.fib_levels[level_name] = self.indicator_calculator.round_price(
                level_price, self.symbol
            )

        self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value from the stored dictionary."""
        return self.indicator_values.get(key, default)

    async def _check_orderbook(
        self, orderbook_manager: AdvancedOrderbookManager
    ) -> float:
        """Analyze orderbook imbalance."""
        bids, asks = await orderbook_manager.get_depth(self.config["orderbook_limit"])

        bid_volume = sum(Decimal(str(b.quantity)) for b in bids)
        ask_volume = sum(Decimal(str(a.quantity)) for a in asks)

        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return 0.0

        imbalance = (bid_volume - ask_volume) / total_volume
        self.logger.debug(
            f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})"
        )
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty:
            return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"MTF SMA: Not enough data for {period} period. Have {len(higher_tf_df)}."
                )
                return "UNKNOWN"
            sma = self.indicator_calculator.calculate_sma(higher_tf_df, period).iloc[-1]
            if last_close > sma:
                return "UP"
            if last_close < sma:
                return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ema":
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"MTF EMA: Not enough data for {period} period. Have {len(higher_tf_df)}."
                )
                return "UNKNOWN"
            ema = self.indicator_calculator.calculate_ema(higher_tf_df, period).iloc[-1]
            if last_close > ema:
                return "UP"
            if last_close < ema:
                return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ehlers_supertrend":
            st_result = self.indicator_calculator.calculate_ehlers_supertrend(
                higher_tf_df,
                period=self.indicator_settings["ehlers_slow_period"],
                multiplier=self.indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1:
                    return "UP"
                if st_dir == -1:
                    return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    async def _fetch_and_analyze_mtf(self, bybit_client) -> dict[str, str]:
        """Fetches data for higher timeframes and determines trends."""
        mtf_trends: dict[str, str] = {}
        if not self.config["mtf_analysis"]["enabled"]:
            return mtf_trends

        higher_timeframes = self.config["mtf_analysis"]["higher_timeframes"]
        trend_indicators = self.config["mtf_analysis"]["trend_indicators"]
        mtf_request_delay = self.config["mtf_analysis"]["mtf_request_delay_seconds"]

        for htf_interval in higher_timeframes:
            self.logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
            htf_df = await bybit_client.fetch_klines(htf_interval, 1000)

            if htf_df is not None and not htf_df.empty:
                for trend_ind in trend_indicators:
                    trend = self._get_mtf_trend(htf_df, trend_ind)
                    mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                    self.logger.debug(
                        f"MTF Trend ({htf_interval}, {trend_ind}): {trend}"
                    )
            else:
                self.logger.warning(
                    f"{NEON_YELLOW}Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}"
                )
            await asyncio.sleep(mtf_request_delay)
        return mtf_trends

    # --- Signal Scoring Helper Methods ---

    def _score_ema_alignment(
        self, signal_score: float, signal_breakdown: dict
    ) -> tuple[float, dict]:
        """Scores EMA alignment."""
        if not self.config["indicators"].get("ema_alignment", False):
            return signal_score, signal_breakdown

        ema_short = self._get_indicator_value("EMA_Short")
        ema_long = self._get_indicator_value("EMA_Long")
        weight = self.weights.get("ema_alignment", 0)

        if not pd.isna(ema_short) and not pd.isna(ema_long) and weight > 0:
            contrib = 0.0
            if ema_short > ema_long:
                contrib = weight
            elif ema_short < ema_long:
                contrib = -weight
            signal_score += contrib
            signal_breakdown["EMA_Alignment"] = contrib
        return signal_score, signal_breakdown

    def _score_sma_trend_filter(
        self, signal_score: float, signal_breakdown: dict, current_close: Decimal
    ) -> tuple[float, dict]:
        """Scores SMA trend filter."""
        if not self.config["indicators"].get("sma_trend_filter", False):
            return signal_score, signal_breakdown

        sma_long = self._get_indicator_value("SMA_Long")
        weight = self.weights.get("sma_trend_filter", 0)

        if not pd.isna(sma_long) and weight > 0:
            contrib = 0.0
            if current_close > sma_long:
                contrib = weight
            elif current_close < sma_long:
                contrib = -weight
            signal_score += contrib
            signal_breakdown["SMA_Trend_Filter"] = contrib
        return signal_score, signal_breakdown

    def _score_momentum(
        self, signal_score: float, signal_breakdown: dict
    ) -> tuple[float, dict]:
        """Scores momentum indicators (RSI, StochRSI, CCI, WR, MFI)."""
        if not self.config["indicators"].get("momentum", False):
            return signal_score, signal_breakdown

        momentum_weight = self.weights.get("momentum_rsi_stoch_cci_wr_mfi", 0)
        if momentum_weight == 0:
            return signal_score, signal_breakdown

        isd = self.indicator_settings

        # RSI
        if self.config["indicators"].get("rsi", False):
            rsi = self._get_indicator_value("RSI")
            if not pd.isna(rsi):
                contrib = 0.0
                if rsi < isd["rsi_oversold"]:
                    contrib = momentum_weight * 0.5
                elif rsi > isd["rsi_overbought"]:
                    contrib = -momentum_weight * 0.5
                signal_score += contrib
                signal_breakdown["RSI_Signal"] = contrib

        # StochRSI Crossover
        if self.config["indicators"].get("stoch_rsi", False):
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            if not pd.isna(stoch_k) and not pd.isna(stoch_d) and len(self.df) > 1:
                prev_stoch_k = self.df["StochRSI_K"].iloc[-2]
                prev_stoch_d = self.df["StochRSI_D"].iloc[-2]
                contrib = 0.0
                if (
                    stoch_k > stoch_d
                    and prev_stoch_k <= prev_stoch_d
                    and stoch_k < isd["stoch_rsi_oversold"]
                ):
                    contrib = momentum_weight * 0.6
                    self.logger.debug("StochRSI: Bullish crossover from oversold.")
                elif (
                    stoch_k < stoch_d
                    and prev_stoch_k >= prev_stoch_d
                    and stoch_k > isd["stoch_rsi_overbought"]
                ):
                    contrib = -momentum_weight * 0.6
                    self.logger.debug("StochRSI: Bearish crossover from overbought.")
                elif stoch_k > stoch_d and stoch_k < STOCH_RSI_MID_POINT:
                    contrib = momentum_weight * 0.2
                elif stoch_k < stoch_d and stoch_k > STOCH_RSI_MID_POINT:
                    contrib = -momentum_weight * 0.2
                signal_score += contrib
                signal_breakdown["StochRSI_Signal"] = contrib

        # CCI
        if self.config["indicators"].get("cci", False):
            cci = self._get_indicator_value("CCI")
            if not pd.isna(cci):
                contrib = 0.0
                if cci < isd["cci_oversold"]:
                    contrib = momentum_weight * 0.4
                elif cci > isd["cci_overbought"]:
                    contrib = -momentum_weight * 0.4
                signal_score += contrib
                signal_breakdown["CCI_Signal"] = contrib

        # Williams %R
        if self.config["indicators"].get("wr", False):
            wr = self._get_indicator_value("WR")
            if not pd.isna(wr):
                contrib = 0.0
                if wr < isd["williams_r_oversold"]:
                    contrib = momentum_weight * 0.4
                elif wr > isd["williams_r_overbought"]:
                    contrib = -momentum_weight * 0.4
                signal_score += contrib
                signal_breakdown["WR_Signal"] = contrib

        # MFI
        if self.config["indicators"].get("mfi", False):
            mfi = self._get_indicator_value("MFI")
            if not pd.isna(mfi):
                contrib = 0.0
                if mfi < isd["mfi_oversold"]:
                    contrib = momentum_weight * 0.4
                elif mfi > isd["mfi_overbought"]:
                    contrib = -momentum_weight * 0.4
                signal_score += contrib
                signal_breakdown["MFI_Signal"] = contrib

        return signal_score, signal_breakdown

    def _score_bollinger_bands(
        self, signal_score: float, signal_breakdown: dict, current_close: Decimal
    ) -> tuple[float, dict]:
        """Scores Bollinger Bands."""
        if not self.config["indicators"].get("bollinger_bands", False):
            return signal_score, signal_breakdown

        bb_upper = self._get_indicator_value("BB_Upper")
        bb_lower = self._get_indicator_value("BB_Lower")
        weight = self.weights.get("bollinger_bands", 0)

        if not pd.isna(bb_upper) and not pd.isna(bb_lower) and weight > 0:
            contrib = 0.0
            if current_close < bb_lower:
                contrib = weight * 0.5
            elif current_close > bb_upper:
                contrib = -weight * 0.5
            signal_score += contrib
            signal_breakdown["Bollinger_Bands_Signal"] = contrib
        return signal_score, signal_breakdown

    def _score_vwap(
        self,
        signal_score: float,
        signal_breakdown: dict,
        current_close: Decimal,
        prev_close: Decimal,
    ) -> tuple[float, dict]:
        """Scores VWAP."""
        if not self.config["indicators"].get("vwap", False):
            return signal_score, signal_breakdown

        vwap = self._get_indicator_value("VWAP")
        weight = self.weights.get("vwap", 0)

        if not pd.isna(vwap) and weight > 0:
            contrib = 0.0
            if current_close > vwap:
                contrib = weight * 0.2
            elif current_close < vwap:
                contrib = -weight * 0.2

            if len(self.df) > 1:
                prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                if current_close > vwap and prev_close <= prev_vwap:
                    contrib += weight * 0.3
                elif current_close < vwap and prev_close >= prev_vwap:
                    contrib -= weight * 0.3
            signal_score += contrib
            signal_breakdown["VWAP_Signal"] = contrib
        return signal_score, signal_breakdown

    def _score_psar(
        self,
        signal_score: float,
        signal_breakdown: dict,
        current_close: Decimal,
        prev_close: Decimal,
    ) -> tuple[float, dict]:
        """Scores PSAR."""
        if not self.config["indicators"].get("psar", False):
            return signal_score, signal_breakdown

        psar_val = self._get_indicator_value("PSAR_Val")
        psar_dir = self._get_indicator_value("PSAR_Dir")
        weight = self.weights.get("psar", 0)

        if not pd.isna(psar_val) and not pd.isna(psar_dir) and weight > 0:
            contrib = 0.0
            if psar_dir == 1:
                contrib = weight * 0.5
            elif psar_dir == -1:
                contrib = -weight * 0.5

            if len(self.df) > 1:
                prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                if current_close > psar_val and prev_close <= prev_psar_val:
                    contrib += weight * 0.4
                elif current_close < psar_val and prev_close >= prev_psar_val:
                    contrib -= weight * 0.4
            signal_score += contrib
            signal_breakdown["PSAR_Signal"] = contrib
        return signal_score, signal_breakdown

    async def _score_orderbook_imbalance(
        self,
        signal_score: float,
        signal_breakdown: dict,
        orderbook_manager: AdvancedOrderbookManager,
    ) -> tuple[float, dict]:
        """Scores orderbook imbalance."""
        if not self.config["indicators"].get("orderbook_imbalance", False):
            return signal_score, signal_breakdown

        imbalance = await self._check_orderbook(orderbook_manager)
        weight = self.weights.get("orderbook_imbalance", 0)

        if weight > 0:
            contrib = imbalance * weight
            signal_score += contrib
            signal_breakdown["Orderbook_Imbalance"] = contrib
        return signal_score, signal_breakdown

    def _score_fibonacci_levels(
        self,
        signal_score: float,
        signal_breakdown: dict,
        current_close: Decimal,
        prev_close: Decimal,
    ) -> tuple[float, dict]:
        """Scores Fibonacci levels confluence."""
        if (
            not self.config["indicators"].get("fibonacci_levels", False)
            or not self.fib_levels
        ):
            return signal_score, signal_breakdown

        weight = self.weights.get("fibonacci_levels", 0)
        if weight == 0:
            return signal_score, signal_breakdown

        contrib = 0.0
        for level_name, level_price in self.fib_levels.items():
            if (
                current_close != 0
                and level_name not in ["0.0%", "100.0%"]
                and abs(current_close - level_price) / current_close < Decimal("0.001")
            ):
                self.logger.debug(
                    f"Price near Fibonacci level {level_name}: {level_price.normalize()}. Current close: {current_close.normalize()}"
                )
                if len(self.df) > 1:
                    if current_close > prev_close and current_close > level_price:
                        contrib += weight * 0.1
                    elif current_close < prev_close and current_close < level_price:
                        contrib -= weight * 0.1
        signal_score += contrib
        signal_breakdown["Fibonacci_Levels_Signal"] = contrib
        return signal_score, signal_breakdown

    def _score_ehlers_supertrend(
        self, signal_score: float, signal_breakdown: dict
    ) -> tuple[float, dict]:
        """Scores Ehlers SuperTrend alignment."""
        if not self.config["indicators"].get("ehlers_supertrend", False):
            return signal_score, signal_breakdown

        st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
        st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
        prev_st_fast_dir = (
            self.df["ST_Fast_Dir"].iloc[-2]
            if "ST_Fast_Dir" in self.df.columns and len(self.df) > 1
            else np.nan
        )
        weight = self.weights.get("ehlers_supertrend_alignment", 0)

        if (
            not pd.isna(st_fast_dir)
            and not pd.isna(st_slow_dir)
            and not pd.isna(prev_st_fast_dir)
            and weight > 0
        ):
            contrib = 0.0
            if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
                contrib = weight
                self.logger.debug(
                    "Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend)."
                )
            elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
                contrib = -weight
                self.logger.debug(
                    "Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend)."
                )
            elif st_slow_dir == 1 and st_fast_dir == 1:
                contrib = weight * 0.3
            elif st_slow_dir == -1 and st_fast_dir == -1:
                contrib = -weight * 0.3
            signal_score += contrib
            signal_breakdown["Ehlers_SuperTrend_Alignment"] = contrib
        return signal_score, signal_breakdown

    def _score_macd(
        self, signal_score: float, signal_breakdown: dict
    ) -> tuple[float, dict]:
        """Scores MACD alignment."""
        if not self.config["indicators"].get("macd", False):
            return signal_score, signal_breakdown

        macd_line = self._get_indicator_value("MACD_Line")
        signal_line = self._get_indicator_value("MACD_Signal")
        histogram = self._get_indicator_value("MACD_Hist")
        weight = self.weights.get("macd_alignment", 0)

        if (
            not pd.isna(macd_line)
            and not pd.isna(signal_line)
            and not pd.isna(histogram)
            and len(self.df) > 1
            and weight > 0
        ):
            contrib = 0.0
            if (
                macd_line > signal_line
                and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]
            ):
                contrib = weight
                self.logger.debug(
                    "MACD: BUY signal (MACD line crossed above Signal line)."
                )
            elif (
                macd_line < signal_line
                and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]
            ):
                contrib = -weight
                self.logger.debug(
                    "MACD: SELL signal (MACD line crossed below Signal line)."
                )
            elif histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0:
                contrib = weight * 0.2
            elif histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0:
                contrib = -weight * 0.2
            signal_score += contrib
            signal_breakdown["MACD_Alignment"] = contrib
        return signal_score, signal_breakdown

    def _score_adx(
        self, signal_score: float, signal_breakdown: dict
    ) -> tuple[float, dict]:
        """Scores ADX strength."""
        if not self.config["indicators"].get("adx", False):
            return signal_score, signal_breakdown

        adx_val = self._get_indicator_value("ADX")
        plus_di = self._get_indicator_value("PlusDI")
        minus_di = self._get_indicator_value("MinusDI")
        weight = self.weights.get("adx_strength", 0)

        if (
            not pd.isna(adx_val)
            and not pd.isna(plus_di)
            and not pd.isna(minus_di)
            and weight > 0
        ):
            contrib = 0.0
            if adx_val > ADX_STRONG_TREND_THRESHOLD:
                if plus_di > minus_di:
                    contrib = weight
                    self.logger.debug(
                        f"ADX: Strong BUY trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, +DI > -DI)."
                    )
                elif minus_di > plus_di:
                    contrib = -weight
                    self.logger.debug(
                        f"ADX: Strong SELL trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, -DI > +DI)."
                    )
            elif adx_val < ADX_WEAK_TREND_THRESHOLD:
                contrib = 0
                self.logger.debug(
                    f"ADX: Weak trend (ADX < {ADX_WEAK_TREND_THRESHOLD}). Neutral signal."
                )
            signal_score += contrib
            signal_breakdown["ADX_Strength"] = contrib
        return signal_score, signal_breakdown

    def _score_ichimoku_cloud(
        self,
        signal_score: float,
        signal_breakdown: dict,
        current_close: Decimal,
        prev_close: Decimal,
    ) -> tuple[float, dict]:
        """Scores Ichimoku Cloud confluence."""
        if not self.config["indicators"].get("ichimoku_cloud", False):
            return signal_score, signal_breakdown

        tenkan_sen = self._get_indicator_value("Tenkan_Sen")
        kijun_sen = self._get_indicator_value("Kijun_Sen")
        senkou_span_a = self._get_indicator_value("Senkou_Span_A")
        senkou_span_b = self._get_indicator_value("Senkou_Span_B")
        chikou_span = self._get_indicator_value("Chikou_Span")
        weight = self.weights.get("ichimoku_confluence", 0)

        if (
            not pd.isna(tenkan_sen)
            and not pd.isna(kijun_sen)
            and not pd.isna(senkou_span_a)
            and not pd.isna(senkou_span_b)
            and not pd.isna(chikou_span)
            and len(self.df) > 1
            and weight > 0
        ):
            contrib = 0.0
            if (
                tenkan_sen > kijun_sen
                and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]
            ):
                contrib += weight * 0.5
                self.logger.debug(
                    "Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish)."
                )
            elif (
                tenkan_sen < kijun_sen
                and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]
            ):
                contrib -= weight * 0.5
                self.logger.debug(
                    "Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish)."
                )

            kumo_high = max(senkou_span_a, senkou_span_b)
            kumo_low = min(senkou_span_a, senkou_span_b)
            prev_kumo_high = (
                max(
                    self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
                )
                if len(self.df) > 1
                else kumo_high
            )
            prev_kumo_low = (
                min(
                    self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
                )
                if len(self.df) > 1
                else kumo_low
            )

            if (
                current_close > kumo_high
                and self.df["close"].iloc[-2] <= prev_kumo_high
            ):
                contrib += weight * 0.7
                self.logger.debug("Ichimoku: Price broke above Kumo (strong bullish).")
            elif (
                current_close < kumo_low and self.df["close"].iloc[-2] >= prev_kumo_low
            ):
                contrib -= weight * 0.7
                self.logger.debug("Ichimoku: Price broke below Kumo (strong bearish).")

            if (
                chikou_span > current_close
                and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]
            ):
                contrib += weight * 0.3
                self.logger.debug(
                    "Ichimoku: Chikou Span crossed above price (bullish confirmation)."
                )
            elif (
                chikou_span < current_close
                and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]
            ):
                contrib -= weight * 0.3
                self.logger.debug(
                    "Ichimoku: Chikou Span crossed below price (bearish confirmation)."
                )
            signal_score += contrib
            signal_breakdown["Ichimoku_Confluence"] = contrib
        return signal_score, signal_breakdown

    def _score_obv(
        self, signal_score: float, signal_breakdown: dict
    ) -> tuple[float, dict]:
        """Scores OBV momentum."""
        if not self.config["indicators"].get("obv", False):
            return signal_score, signal_breakdown

        obv_val = self._get_indicator_value("OBV")
        obv_ema = self._get_indicator_value("OBV_EMA")
        weight = self.weights.get("obv_momentum", 0)

        if (
            not pd.isna(obv_val)
            and not pd.isna(obv_ema)
            and len(self.df) > 1
            and weight > 0
        ):
            contrib = 0.0
            if (
                obv_val > obv_ema
                and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]
            ):
                contrib = weight * 0.5
                self.logger.debug("OBV: Bullish crossover detected.")
            elif (
                obv_val < obv_ema
                and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]
            ):
                contrib = -weight * 0.5
                self.logger.debug("OBV: Bearish crossover detected.")

            if len(self.df) > 2:
                if (
                    obv_val > self.df["OBV"].iloc[-2]
                    and obv_val > self.df["OBV"].iloc[-3]
                ):
                    contrib += weight * 0.2
                elif (
                    obv_val < self.df["OBV"].iloc[-2]
                    and obv_val < self.df["OBV"].iloc[-3]
                ):
                    contrib -= weight * 0.2
            signal_score += contrib
            signal_breakdown["OBV_Momentum"] = contrib
        return signal_score, signal_breakdown

    def _score_cmf(
        self, signal_score: float, signal_breakdown: dict
    ) -> tuple[float, dict]:
        """Scores CMF flow."""
        if not self.config["indicators"].get("cmf", False):
            return signal_score, signal_breakdown

        cmf_val = self._get_indicator_value("CMF")
        weight = self.weights.get("cmf_flow", 0)

        if not pd.isna(cmf_val) and weight > 0:
            contrib = 0.0
            if cmf_val > 0:
                contrib = weight * 0.5
            elif cmf_val < 0:
                contrib = -weight * 0.5

            if len(self.df) > 2:
                if (
                    cmf_val > self.df["CMF"].iloc[-2]
                    and cmf_val > self.df["CMF"].iloc[-3]
                ):
                    contrib += weight * 0.3
                elif (
                    cmf_val < self.df["CMF"].iloc[-2]
                    and cmf_val < self.df["CMF"].iloc[-3]
                ):
                    contrib -= weight * 0.3
            signal_score += contrib
            signal_breakdown["CMF_Flow"] = contrib
        return signal_score, signal_breakdown

    def _score_volatility_index(
        self, signal_score: float, signal_breakdown: dict
    ) -> tuple[float, dict]:
        """Scores Volatility Index."""
        if not self.config["indicators"].get("volatility_index", False):
            return signal_score, signal_breakdown

        vol_idx = self._get_indicator_value("Volatility_Index")
        weight = self.weights.get("volatility_index_signal", 0)

        if not pd.isna(vol_idx) and weight > 0:
            contrib = 0.0
            if len(self.df) > 2 and "Volatility_Index" in self.df.columns:
                prev_vol_idx = self.df["Volatility_Index"].iloc[-2]
                prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3]

                if vol_idx > prev_vol_idx > prev_prev_vol_idx:
                    if signal_score > 0:
                        contrib = weight * 0.2
                    elif signal_score < 0:
                        contrib = -weight * 0.2
                    self.logger.debug("Volatility Index: Increasing volatility.")
                elif vol_idx < prev_vol_idx < prev_prev_vol_idx:
                    if abs(signal_score) > 0:
                        contrib = signal_score * -0.2
                    self.logger.debug("Volatility Index: Decreasing volatility.")
            signal_score += contrib
            signal_breakdown["Volatility_Index_Signal"] = contrib
        return signal_score, signal_breakdown

    def _score_vwma(
        self,
        signal_score: float,
        signal_breakdown: dict,
        current_close: Decimal,
        prev_close: Decimal,
    ) -> tuple[float, dict]:
        """Scores VWMA cross."""
        if not self.config["indicators"].get("vwma", False):
            return signal_score, signal_breakdown

        vwma = self._get_indicator_value("VWMA")
        weight = self.weights.get("vwma_cross", 0)

        if not pd.isna(vwma) and len(self.df) > 1 and weight > 0:
            prev_vwma = self.df["VWMA"].iloc[-2]
            contrib = 0.0
            if current_close > vwma and prev_close <= prev_vwma:
                contrib = weight
                self.logger.debug("VWMA: Bullish crossover (price above VWMA).")
            elif current_close < vwma and prev_close >= prev_vwma:
                contrib = -weight
                self.logger.debug("VWMA: Bearish crossover (price below VWMA).")
            signal_score += contrib
            signal_breakdown["VWMA_Cross"] = contrib
        return signal_score, signal_breakdown

    def _score_volume_delta(
        self, signal_score: float, signal_breakdown: dict
    ) -> tuple[float, dict]:
        """Scores Volume Delta."""
        if not self.config["indicators"].get("volume_delta", False):
            return signal_score, signal_breakdown

        volume_delta = self._get_indicator_value("Volume_Delta")
        volume_delta_threshold = self.indicator_settings.get(
            "volume_delta_threshold", 0.2
        )
        weight = self.weights.get("volume_delta_signal", 0)

        if not pd.isna(volume_delta) and weight > 0:
            contrib = 0.0
            if volume_delta > volume_delta_threshold:
                contrib = weight
                self.logger.debug(
                    f"Volume Delta: Strong buying pressure detected ({volume_delta:.2f})."
                )
            elif volume_delta < -volume_delta_threshold:
                contrib = -weight
                self.logger.debug(
                    f"Volume Delta: Strong selling pressure detected ({volume_delta:.2f})."
                )
            elif volume_delta > 0:
                contrib = weight * 0.3
            elif volume_delta < 0:
                contrib = -weight * 0.3
            signal_score += contrib
            signal_breakdown["Volume_Delta_Signal"] = contrib
        return signal_score, signal_breakdown

    def _score_kaufman_ama(
        self,
        signal_score: float,
        signal_breakdown: dict,
        current_close: Decimal,
        prev_close: Decimal,
    ) -> tuple[float, dict]:
        """Scores Kaufman's Adaptive Moving Average (KAMA) cross."""
        if not self.config["indicators"].get("kaufman_ama", False):
            return signal_score, signal_breakdown

        kama = self._get_indicator_value("Kaufman_AMA")
        weight = self.weights.get("kaufman_ama_cross", 0)

        if not pd.isna(kama) and len(self.df) > 1 and weight > 0:
            prev_kama = self.df["Kaufman_AMA"].iloc[-2]
            contrib = 0.0
            if current_close > kama and prev_close <= prev_kama:
                contrib = weight
                self.logger.debug("KAMA: Bullish crossover (price above KAMA).")
            elif current_close < kama and prev_close >= prev_kama:
                contrib = -weight
                self.logger.debug("KAMA: Bearish crossover (price below KAMA).")
            signal_score += contrib
            signal_breakdown["Kaufman_AMA_Cross"] = contrib
        return signal_score, signal_breakdown

    def _score_relative_volume(
        self, signal_score: float, signal_breakdown: dict
    ) -> tuple[float, dict]:
        """Scores Relative Volume."""
        if not self.config["indicators"].get("relative_volume", False):
            return signal_score, signal_breakdown

        rvol = self._get_indicator_value("Relative_Volume")
        rvol_threshold = self.indicator_settings.get("relative_volume_threshold", 1.5)
        weight = self.weights.get("relative_volume_confirmation", 0)

        if not pd.isna(rvol) and weight > 0:
            contrib = 0.0
            if rvol >= rvol_threshold:
                contrib = weight
                self.logger.debug(
                    f"Relative Volume: High volume detected ({rvol:.2f})."
                )
            signal_score += contrib
            signal_breakdown["Relative_Volume_Confirmation"] = contrib
        return signal_score, signal_breakdown

    def _score_market_structure(
        self, signal_score: float, signal_breakdown: dict
    ) -> tuple[float, dict]:
        """Scores Market Structure Trend."""
        if not self.config["indicators"].get("market_structure", False):
            return signal_score, signal_breakdown

        ms_trend = self._get_indicator_value("Market_Structure_Trend")
        weight = self.weights.get("market_structure_confluence", 0)

        if ms_trend != "UNKNOWN" and weight > 0:
            contrib = 0.0
            if ms_trend == "UP":
                contrib = weight
                self.logger.debug("Market Structure: Uptrend detected.")
            elif ms_trend == "DOWN":
                contrib = -weight
                self.logger.debug("Market Structure: Downtrend detected.")
            signal_score += contrib
            signal_breakdown["Market_Structure_Confluence"] = contrib
        return signal_score, signal_breakdown

    def _score_dema(
        self,
        signal_score: float,
        signal_breakdown: dict,
        current_close: Decimal,
        prev_close: Decimal,
    ) -> tuple[float, dict]:
        """Scores DEMA crossover."""
        if not self.config["indicators"].get("dema", False):
            return signal_score, signal_breakdown

        dema = self._get_indicator_value("DEMA")
        weight = self.weights.get("dema_crossover", 0)

        if not pd.isna(dema) and len(self.df) > 1 and weight > 0:
            prev_dema = self.df["DEMA"].iloc[-2]
            contrib = 0.0
            if current_close > dema and prev_close <= prev_dema:
                contrib = weight
                self.logger.debug("DEMA: Bullish crossover (price above DEMA).")
            elif current_close < dema and prev_close >= prev_dema:
                contrib = -weight
                self.logger.debug("DEMA: Bearish crossover (price below DEMA).")
            signal_score += contrib
            signal_breakdown["DEMA_Crossover"] = contrib
        return signal_score, signal_breakdown

    def _score_keltner_channels(
        self, signal_score: float, signal_breakdown: dict, current_close: Decimal
    ) -> tuple[float, dict]:
        """Scores Keltner Channels breakout."""
        if not self.config["indicators"].get("keltner_channels", False):
            return signal_score, signal_breakdown

        kc_upper = self._get_indicator_value("Keltner_Upper")
        kc_lower = self._get_indicator_value("Keltner_Lower")
        weight = self.weights.get("keltner_breakout", 0)

        if not pd.isna(kc_upper) and not pd.isna(kc_lower) and weight > 0:
            contrib = 0.0
            if current_close > kc_upper:
                contrib = weight
                self.logger.debug("Keltner Channels: Bullish breakout.")
            elif current_close < kc_lower:
                contrib = -weight
                self.logger.debug("Keltner Channels: Bearish breakout.")
            signal_score += contrib
            signal_breakdown["Keltner_Breakout"] = contrib
        return signal_score, signal_breakdown

    def _score_roc(
        self, signal_score: float, signal_breakdown: dict
    ) -> tuple[float, dict]:
        """Scores Rate of Change (ROC)."""
        if not self.config["indicators"].get("roc", False):
            return signal_score, signal_breakdown

        roc = self._get_indicator_value("ROC")
        roc_oversold = self.indicator_settings.get("roc_oversold", -5.0)
        roc_overbought = self.indicator_settings.get("roc_overbought", 5.0)
        weight = self.weights.get("roc_signal", 0)

        if not pd.isna(roc) and weight > 0:
            contrib = 0.0
            if roc < roc_oversold:
                contrib = weight * 0.5
                self.logger.debug(f"ROC: Oversold ({roc:.2f}).")
            elif roc > roc_overbought:
                contrib = -weight * 0.5
                self.logger.debug(f"ROC: Overbought ({roc:.2f}).")
            signal_score += contrib
            signal_breakdown["ROC_Signal"] = contrib
        return signal_score, signal_breakdown

    def _score_candlestick_patterns(
        self, signal_score: float, signal_breakdown: dict
    ) -> tuple[float, dict]:
        """Scores Candlestick Patterns."""
        if not self.config["indicators"].get("candlestick_patterns", False):
            return signal_score, signal_breakdown

        pattern = self._get_indicator_value("Candlestick_Pattern")
        weight = self.weights.get("candlestick_confirmation", 0)

        if pattern != "No Pattern" and weight > 0:
            contrib = 0.0
            if "Bullish" in pattern:
                contrib = weight
                self.logger.debug(
                    f"Candlestick Pattern: {pattern} detected (bullish). "
                )
            elif "Bearish" in pattern:
                contrib = -weight
                self.logger.debug(
                    f"Candlestick Pattern: {pattern} detected (bearish). "
                )
            signal_score += contrib
            signal_breakdown["Candlestick_Confirmation"] = contrib
        return signal_score, signal_breakdown

    def _score_fibonacci_pivot_points(
        self, signal_score: float, signal_breakdown: dict, current_close: Decimal
    ) -> tuple[float, dict]:
        """Scores Fibonacci Pivot Points confluence."""
        if not self.config["indicators"].get("fibonacci_pivot_points", False):
            return signal_score, signal_breakdown

        pivot = self._get_indicator_value("Pivot")
        r1 = self._get_indicator_value("R1")
        r2 = self._get_indicator_value("R2")
        s1 = self._get_indicator_value("S1")
        s2 = self._get_indicator_value("S2")
        weight = self.weights.get("fibonacci_pivot_points_confluence", 0)

        if not pd.isna(pivot) and weight > 0:
            contrib = 0.0
            # Check proximity to pivot and resistance/support levels
            if current_close > pivot and current_close < r1:
                contrib += weight * 0.1  # Above pivot, below R1
            elif current_close < pivot and current_close > s1:
                contrib -= weight * 0.1  # Below pivot, above S1
            elif current_close > r1 and current_close < r2:
                contrib += weight * 0.2  # Between R1 and R2
            elif current_close < s1 and current_close > s2:
                contrib -= weight * 0.2  # Between S1 and S2
            elif current_close > r2:
                contrib += weight * 0.3  # Above R2
            elif current_close < s2:
                contrib -= weight * 0.3  # Below S2
            signal_score += contrib
            signal_breakdown["Fibonacci_Pivot_Points_Confluence"] = contrib
        return signal_score, signal_breakdown

    def _score_orderbook_support_resistance(
        self, signal_score: float, signal_breakdown: dict, current_close: Decimal
    ) -> tuple[float, dict]:
        """Scores based on orderbook-derived support/resistance levels."""
        if not self.config["indicators"].get(
            "orderbook_imbalance", False
        ):  # Using this flag for now
            return signal_score, signal_breakdown

        support_level = self._get_indicator_value("Support_Level")
        resistance_level = self._get_indicator_value("Resistance_Level")
        weight = self.weights.get(
            "orderbook_imbalance", 0
        )  # Using imbalance weight for now

        if not pd.isna(support_level) and not pd.isna(resistance_level) and weight > 0:
            contrib = 0.0
            # Price near support
            if current_close > support_level * Decimal(
                "0.999"
            ) and current_close < support_level * Decimal("1.001"):
                contrib += weight * 0.1  # Potential bounce
                self.logger.debug(
                    f"Price near Orderbook Support: {support_level.normalize()}"
                )
            # Price near resistance
            if current_close > resistance_level * Decimal(
                "0.999"
            ) and current_close < resistance_level * Decimal("1.001"):
                contrib -= weight * 0.1  # Potential rejection
                self.logger.debug(
                    f"Price near Orderbook Resistance: {resistance_level.normalize()}"
                )
            signal_score += contrib
            signal_breakdown["Orderbook_Support_Resistance"] = contrib
        return signal_score, signal_breakdown

    def _score_mtf_confluence(
        self, signal_score: float, signal_breakdown: dict, mtf_trends: dict[str, str]
    ) -> tuple[float, dict]:
        """Scores Multi-Timeframe trend confluence."""
        if not self.config["mtf_analysis"]["enabled"] or not mtf_trends:
            return signal_score, signal_breakdown

        mtf_buy_score = 0
        mtf_sell_score = 0
        for _tf_indicator, trend in mtf_trends.items():
            if trend == "UP":
                mtf_buy_score += 1
            elif trend == "DOWN":
                mtf_sell_score += 1

        weight = self.weights.get("mtf_trend_confluence", 0)
        if weight == 0:
            return signal_score, signal_breakdown

        contrib = 0.0
        if mtf_trends:
            normalized_mtf_score = (mtf_buy_score - mtf_sell_score) / len(mtf_trends)
            contrib = weight * normalized_mtf_score
            self.logger.debug(
                f"MTF Confluence: Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {mtf_sell_score}). Total MTF contribution: {contrib:.2f}"
            )
        signal_score += contrib
        signal_breakdown["MTF_Trend_Confluence"] = contrib
        return signal_score, signal_breakdown

    def _score_trade_confirmation(
        self, signal_score: float, signal_breakdown: dict
    ) -> tuple[float, dict]:
        """Applies score modifiers based on volume and volatility for trade confirmation."""
        isd = self.indicator_settings
        cfg = self.config
        current_volume = self.df["volume"].iloc[-1]

        if isd.get("enable_volume_confirmation", False) and cfg["indicators"].get(
            "volume_confirmation", False
        ):
            avg_volume = Decimal(str(self._get_indicator_value("Avg_Volume")))
            min_volume_multiplier = Decimal(str(isd.get("min_volume_multiplier", 1.0)))
            weight = self.weights.get("volume_confirmation", 0)

            if not pd.isna(avg_volume) and avg_volume > 0 and weight > 0:
                if current_volume >= (avg_volume * min_volume_multiplier):
                    signal_score += weight
                    signal_breakdown["Volume_Confirmation"] = weight
                    self.logger.debug(
                        f"Volume Confirmation: Volume ({current_volume:.2f}) above average ({avg_volume:.2f} * {min_volume_multiplier})."
                    )
                else:
                    signal_score -= weight * 0.5
                    signal_breakdown["Volume_Confirmation"] = -weight * 0.5
                    self.logger.debug(
                        f"Volume Confirmation: Volume ({current_volume:.2f}) below threshold. Penalizing."
                    )

        if isd.get("enable_volatility_filter", False) and cfg["indicators"].get(
            "volatility_filter", False
        ):
            vol_idx = self._get_indicator_value("Volatility_Index")
            optimal_min = Decimal(str(isd.get("optimal_volatility_min", 0.0)))
            optimal_max = Decimal(str(isd.get("optimal_volatility_max", 1.0)))
            weight = self.weights.get("volatility_filter", 0)

            if not pd.isna(vol_idx) and weight > 0:
                if optimal_min <= vol_idx <= optimal_max:
                    signal_score += weight
                    signal_breakdown["Volatility_Filter"] = weight
                    self.logger.debug(
                        f"Volatility Filter: Volatility Index ({vol_idx:.4f}) is within optimal range [{optimal_min:.4f}-{optimal_max:.4f}]."
                    )
                else:
                    signal_score -= weight * 0.5
                    signal_breakdown["Volatility_Filter"] = -weight * 0.5
                    self.logger.debug(
                        f"Volatility Filter: Volatility Index ({vol_idx:.4f}) is outside optimal range. Penalizing."
                    )

        return signal_score, signal_breakdown

    def _score_sentiment(
        self, signal_score: float, signal_breakdown: dict, sentiment_score: float | None
    ) -> tuple[float, dict]:
        """Scores based on external sentiment data."""
        ml_enhancement_cfg = self.config["ml_enhancement"]
        if not ml_enhancement_cfg.get("sentiment_analysis_enabled", False):
            return signal_score, signal_breakdown

        weight = self.weights.get("sentiment_signal", 0)
        bullish_threshold = ml_enhancement_cfg.get("bullish_sentiment_threshold", 0.6)
        bearish_threshold = ml_enhancement_cfg.get("bearish_sentiment_threshold", 0.4)

        if sentiment_score is not None and weight > 0:
            contrib = 0.0
            if sentiment_score >= bullish_threshold:
                contrib = weight
                self.logger.debug(f"Sentiment: Bullish ({sentiment_score:.2f}).")
            elif sentiment_score <= bearish_threshold:
                contrib = -weight
                self.logger.debug(f"Sentiment: Bearish ({sentiment_score:.2f}).")
            else:
                contrib = 0

            signal_score += contrib
            signal_breakdown["Sentiment_Signal"] = contrib
        return signal_score, signal_breakdown

    def assess_market_conditions(self) -> dict[str, Any]:
        """Assesses current market conditions based on key indicators."""
        adx = self._get_indicator_value("ADX")
        vol_idx = self._get_indicator_value("Volatility_Index")
        ema_short = self._get_indicator_value("EMA_Short")
        ema_long = self._get_indicator_value("EMA_Long")
        plus_di = self._get_indicator_value("PlusDI")
        minus_di = self._get_indicator_value("MinusDI")

        conditions: dict[str, Any] = {
            "trend_strength": "UNKNOWN",
            "trend_direction": "NEUTRAL",
            "volatility": "MODERATE",
            "adx_value": adx,
            "volatility_index_value": vol_idx,
        }

        isd = self.indicator_settings
        strong_adx = isd.get("ADX_STRONG_TREND_THRESHOLD", 25)
        weak_adx = isd.get("ADX_WEAK_TREND_THRESHOLD", 20)

        if not pd.isna(adx):
            if adx > strong_adx:
                conditions["trend_strength"] = "STRONG"
            elif adx < weak_adx:
                conditions["trend_strength"] = "WEAK"
            else:
                conditions["trend_strength"] = "MODERATE"

        if not pd.isna(plus_di) and not pd.isna(minus_di):
            if plus_di > minus_di and conditions["trend_strength"] in [
                "STRONG",
                "MODERATE",
            ]:
                conditions["trend_direction"] = "UP"
            elif minus_di > plus_di and conditions["trend_strength"] in [
                "STRONG",
                "MODERATE",
            ]:
                conditions["trend_direction"] = "DOWN"
            elif not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long:
                    conditions["trend_direction"] = "UP"
                elif ema_short < ema_long:
                    conditions["trend_direction"] = "DOWN"

        if not pd.isna(vol_idx):
            optimal_min = Decimal(str(isd.get("optimal_volatility_min", 0.0)))
            optimal_max = Decimal(str(isd.get("optimal_volatility_max", 1.0)))

            if vol_idx < optimal_min:
                conditions["volatility"] = "LOW"
            elif vol_idx > optimal_max:
                conditions["volatility"] = "HIGH"
            else:
                conditions["volatility"] = "MODERATE"

        self.logger.debug(f"Market Conditions: {conditions}")
        return conditions

    async def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_manager: AdvancedOrderbookManager,
        mtf_trends: dict[str, str],
        sentiment_score: float | None = None,
    ) -> tuple[str, float, dict]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend.
        Returns the final signal, the aggregated signal score, and a breakdown of contributions.
        """
        signal_score = 0.0
        signal_breakdown: dict[str, float] = {}

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}"
            )
            return "HOLD", 0.0, {}

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = (
            Decimal(str(self.df["close"].iloc[-2]))
            if len(self.df) > 1
            else current_close
        )

        # Apply Scoring for Each Indicator Group
        signal_score, signal_breakdown = self._score_ema_alignment(
            signal_score, signal_breakdown
        )
        signal_score, signal_breakdown = self._score_sma_trend_filter(
            signal_score, signal_breakdown, current_close
        )
        signal_score, signal_breakdown = self._score_momentum(
            signal_score, signal_breakdown
        )
        signal_score, signal_breakdown = self._score_bollinger_bands(
            signal_score, signal_breakdown, current_close
        )
        signal_score, signal_breakdown = self._score_vwap(
            signal_score, signal_breakdown, current_close, prev_close
        )
        signal_score, signal_breakdown = self._score_psar(
            signal_score, signal_breakdown, current_close, prev_close
        )
        signal_score, signal_breakdown = await self._score_orderbook_imbalance(
            signal_score, signal_breakdown, orderbook_manager
        )
        signal_score, signal_breakdown = self._score_fibonacci_levels(
            signal_score, signal_breakdown, current_close, prev_close
        )
        signal_score, signal_breakdown = self._score_ehlers_supertrend(
            signal_score, signal_breakdown
        )
        signal_score, signal_breakdown = self._score_macd(
            signal_score, signal_breakdown
        )
        signal_score, signal_breakdown = self._score_adx(signal_score, signal_breakdown)
        signal_score, signal_breakdown = self._score_ichimoku_cloud(
            signal_score, signal_breakdown, current_close, prev_close
        )
        signal_score, signal_breakdown = self._score_obv(signal_score, signal_breakdown)
        signal_score, signal_breakdown = self._score_cmf(signal_score, signal_breakdown)
        signal_score, signal_breakdown = self._score_volatility_index(
            signal_score, signal_breakdown
        )
        signal_score, signal_breakdown = self._score_vwma(
            signal_score, signal_breakdown, current_close, prev_close
        )
        signal_score, signal_breakdown = self._score_volume_delta(
            signal_score, signal_breakdown
        )
        signal_score, signal_breakdown = self._score_kaufman_ama(
            signal_score, signal_breakdown, current_close, prev_close
        )
        signal_score, signal_breakdown = self._score_relative_volume(
            signal_score, signal_breakdown
        )
        signal_score, signal_breakdown = self._score_market_structure(
            signal_score, signal_breakdown
        )
        signal_score, signal_breakdown = self._score_dema(
            signal_score, signal_breakdown, current_close, prev_close
        )
        signal_score, signal_breakdown = self._score_keltner_channels(
            signal_score, signal_breakdown, current_close
        )
        signal_score, signal_breakdown = self._score_roc(signal_score, signal_breakdown)
        signal_score, signal_breakdown = self._score_candlestick_patterns(
            signal_score, signal_breakdown
        )
        signal_score, signal_breakdown = self._score_fibonacci_pivot_points(
            signal_score, signal_breakdown, current_close
        )
        signal_score, signal_breakdown = self._score_orderbook_support_resistance(
            signal_score, signal_breakdown, current_close
        )

        threshold = self.config["signal_score_threshold"]
        cooldown_sec = self.config["cooldown_sec"]
        hysteresis_ratio = self.config["hysteresis_ratio"]

        final_signal = "HOLD"
        now_ts = int(time.time())

        is_strong_buy = signal_score >= threshold
        is_strong_sell = signal_score <= -threshold

        if (
            self._last_signal_score > 0
            and signal_score > -threshold * hysteresis_ratio
            and not is_strong_buy
        ):
            final_signal = "BUY"
        elif (
            self._last_signal_score < 0
            and signal_score < threshold * hysteresis_ratio
            and not is_strong_sell
        ):
            final_signal = "SELL"
        elif is_strong_buy:
            final_signal = "BUY"
        elif is_strong_sell:
            final_signal = "SELL"

        if final_signal != "HOLD":
            if now_ts - self._last_signal_ts < cooldown_sec:
                self.logger.info(
                    f"{NEON_YELLOW}Signal '{final_signal}' ignored due to cooldown ({cooldown_sec - (now_ts - self._last_signal_ts)}s remaining).{RESET}"
                )
                final_signal = "HOLD"
            else:
                self._last_signal_ts = now_ts

        self._last_signal_score = signal_score

        self.logger.info(
            f"{NEON_YELLOW}Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}"
        )
        return final_signal, signal_score, signal_breakdown

    def calculate_entry_tp_sl(
        self,
        current_price: Decimal,
        atr_value: Decimal,
        signal: str,
        precision_manager,  # Pass precision_manager here
    ) -> tuple[Decimal, Decimal]:
        """Calculate Take Profit and Stop Loss levels."""
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"])
        )

        if signal == "Buy":
            stop_loss = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit = current_price + (atr_value * take_profit_atr_multiple)
        elif signal == "Sell":
            stop_loss = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit = current_price - (atr_value * take_profit_atr_multiple)
        else:
            return Decimal("0"), Decimal("0")

        # Use precision manager to round SL/TP
        stop_loss = precision_manager.round_price(stop_loss, self.symbol)
        take_profit = precision_manager.round_price(take_profit, self.symbol)

        return take_profit, stop_loss


async def fetch_latest_sentiment(symbol: str, logger: logging.Logger) -> float | None:
    """Placeholder function for fetching market sentiment (e.g., from an external API).
    Returns a float between 0 (very bearish) and 1 (very bullish), or None if unavailable.
    """
    logger.debug(f"[{symbol}] Fetching latest sentiment (placeholder)...")

    current_minute = datetime.now().minute  # Use current time for simulation
    if current_minute % 5 == 0:
        return 0.8  # Bullish
    elif current_minute % 5 == 1:
        return 0.2  # Bearish
    else:
        return 0.5  # Neutral


async def display_indicator_values_and_price(
    config: dict[str, Any],
    logger: logging.Logger,
    current_price: Decimal,
    df: pd.DataFrame,
    orderbook_manager: AdvancedOrderbookManager,
    mtf_trends: dict[str, str],
    signal_breakdown: dict | None = None,
    indicator_calculator: IndicatorCalculator = None,  # Pass the instance
) -> None:
    """Display current price and calculated indicator values."""
    logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
    logger.info(f"{NEON_GREEN}Current Price: {current_price.normalize()}{RESET}")

    # Use the passed indicator_calculator instance
    analyzer = TradingAnalyzer(config, logger, config["symbol"], indicator_calculator)
    analyzer.update_data(df)  # Update data to ensure latest indicators are calculated

    if analyzer.df.empty:
        logger.warning(
            f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.{RESET}"
        )
        return

    logger.info(f"{NEON_CYAN}--- Indicator Values ---{RESET}")
    sorted_indicator_items = sorted(analyzer.indicator_values.items())
    for indicator_name, value in sorted_indicator_items:
        color = Fore.YELLOW  # Default color
        # Use INDICATOR_COLORS from the main script or define them here if needed
        # For now, using a simple default.
        if isinstance(value, Decimal):
            logger.info(f"  {color}{indicator_name}: {value.normalize()}{RESET}")
        elif isinstance(value, float):
            logger.info(f"  {color}{indicator_name}: {value:.8f}{RESET}")
        else:
            logger.info(f"  {color}{indicator_name}: {value}{RESET}")

    if analyzer.fib_levels:
        logger.info(f"{NEON_CYAN}--- Fibonacci Levels ---{RESET}")
        sorted_fib_levels = sorted(
            analyzer.fib_levels.items(),
            key=lambda item: float(item[0].replace("%", "")) / 100,
        )
        for level_name, level_price in sorted_fib_levels:
            logger.info(
                f"  {NEON_YELLOW}{level_name}: {level_price.normalize()}{RESET}"
            )

    if mtf_trends:
        logger.info(f"{NEON_CYAN}--- Multi-Timeframe Trends ---{RESET}")
        sorted_mtf_trends = sorted(mtf_trends.items())
        for tf_indicator, trend in sorted_mtf_trends:
            logger.info(f"  {NEON_YELLOW}{tf_indicator}: {trend}{RESET}")

    if signal_breakdown:
        logger.info(f"{NEON_CYAN}--- Signal Score Breakdown ---{RESET}")
        sorted_breakdown = sorted(
            signal_breakdown.items(), key=lambda item: abs(item[1]), reverse=True
        )
        for indicator, contribution in sorted_breakdown:
            color = (
                Fore.GREEN
                if contribution > 0
                else (Fore.RED if contribution < 0 else Fore.YELLOW)
            )
            logger.info(f"  {color}{indicator:<25}: {contribution: .2f}{RESET}")

    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")
