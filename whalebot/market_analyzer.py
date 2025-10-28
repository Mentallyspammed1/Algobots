# market_analyzer.py

import logging
from typing import Any

import pandas as pd


class MarketAnalyzer:
    """Analyzes market data to determine current conditions such as trend and volatility.
    This helps in dynamically adapting trading strategies.
    """

    def __init__(self, logger: logging.Logger, **kwargs):
        self.logger = logger
        self.trend_detection_period: int = kwargs.get("trend_detection_period", 50)
        self.volatility_detection_atr_period: int = kwargs.get(
            "volatility_detection_atr_period",
            14,
        )
        self.volatility_threshold_high: float = kwargs.get(
            "volatility_threshold_high",
            1.5,
        )  # ATR > 1.5 * recent_ATR_avg => HIGH
        self.volatility_threshold_low: float = kwargs.get(
            "volatility_threshold_low",
            0.5,
        )  # ATR < 0.5 * recent_ATR_avg => LOW
        self.adx_period: int = kwargs.get("adx_period", 14)
        self.adx_trend_strong_threshold: int = kwargs.get(
            "adx_trend_strong_threshold",
            25,
        )
        self.adx_trend_weak_threshold: int = kwargs.get("adx_trend_weak_threshold", 20)

        self.recent_atr_avg: float = (
            0.0  # To track average ATR for volatility comparison
        )

        self.logger.info("MarketAnalyzer initialized.")

    def analyze_market_conditions(self, df: pd.DataFrame) -> dict[str, Any]:
        """Analyzes the market DataFrame to determine trend and volatility.

        Args:
            df: DataFrame containing OHLCV data.

        Returns:
            A dictionary with current market conditions (e.g., 'trend', 'volatility', 'trend_strength', 'market_phase').

        """
        conditions: dict[str, Any] = {
            "trend": "UNKNOWN",  # UPTREND, DOWNTREND, RANGING
            "volatility": "NORMAL",  # HIGH, NORMAL, LOW
            "trend_strength": "NEUTRAL",  # STRONG, MODERATE, WEAK
            "market_phase": "UNKNOWN",  # TRENDING_UP, TRENDING_DOWN, RANGING (more specific)
        }

        # Ensure numeric types and sufficient data
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df_cleaned = df.dropna(subset=["close"]).copy()

        required_periods = (
            max(
                self.trend_detection_period,
                self.volatility_detection_atr_period,
                self.adx_period,
            )
            + 2
        )
        if df_cleaned.empty or len(df_cleaned) < required_periods:
            self.logger.warning(
                f"Insufficient data ({len(df_cleaned)} bars) for market condition analysis. Need at least {required_periods} bars.",
            )
            return conditions

        # --- Calculate necessary indicators for analysis ---
        df_cleaned.ta.ema(
            length=self.trend_detection_period,
            append=True,
            col_names=(f"EMA_{self.trend_detection_period}",),
        )
        df_cleaned.ta.adx(length=self.adx_period, append=True)
        df_cleaned.ta.atr(
            length=self.volatility_detection_atr_period,
            append=True,
            col_names=(f"ATR_{self.volatility_detection_atr_period}",),
        )

        # Ensure indicators are calculated and not NaN for the latest row
        df_cleaned.fillna(method="ffill", inplace=True)
        df_cleaned.fillna(0, inplace=True)  # Fill any remaining with 0

        if df_cleaned.empty:
            self.logger.warning(
                "DataFrame became empty after indicator calculation and NaN handling in MarketAnalyzer.",
            )
            return conditions

        latest_close = df_cleaned["close"].iloc[-1]
        latest_ema = df_cleaned[f"EMA_{self.trend_detection_period}"].iloc[-1]
        latest_adx = df_cleaned[f"ADX_{self.adx_period}"].iloc[-1]
        latest_plus_di = df_cleaned[f"DMP_{self.adx_period}"].iloc[-1]  # +DI
        latest_minus_di = df_cleaned[f"DMN_{self.adx_period}"].iloc[-1]  # -DI
        latest_atr = df_cleaned[f"ATR_{self.volatility_detection_atr_period}"].iloc[-1]

        # --- Trend Direction (EMA & DI Crossover) ---
        if latest_close > latest_ema:
            conditions["trend"] = "UPTREND"
        elif latest_close < latest_ema:
            conditions["trend"] = "DOWNTREND"
        else:
            conditions["trend"] = "RANGING"

        # --- Trend Strength (ADX) & Market Phase ---
        if latest_adx > self.adx_trend_strong_threshold:
            conditions["trend_strength"] = "STRONG"
            if latest_plus_di > latest_minus_di:
                conditions["market_phase"] = "TRENDING_UP"
            else:
                conditions["market_phase"] = "TRENDING_DOWN"
        elif latest_adx < self.adx_trend_weak_threshold:
            conditions["trend_strength"] = "WEAK"
            conditions["market_phase"] = (
                "RANGING"  # Weak ADX usually means ranging or consolidation
            )
        else:  # ADX is moderate
            conditions["trend_strength"] = "MODERATE"
            if conditions["trend"] == "UPTREND":
                conditions["market_phase"] = "TRENDING_UP"
            elif conditions["trend"] == "DOWNTREND":
                conditions["market_phase"] = "TRENDING_DOWN"
            else:
                conditions["market_phase"] = "RANGING"

        # --- Volatility Detection (ATR) ---
        if latest_atr > 0:  # Avoid division by zero
            # Calculate recent average ATR for comparison (e.g., last 20 periods)
            recent_atr_series = (
                df_cleaned[f"ATR_{self.volatility_detection_atr_period}"]
                .iloc[-20:]
                .dropna()
            )
            if not recent_atr_series.empty:
                self.recent_atr_avg = recent_atr_series.mean()
            else:  # Fallback if not enough history for average
                self.recent_atr_avg = latest_atr

            if self.recent_atr_avg > 0:
                if latest_atr > self.recent_atr_avg * self.volatility_threshold_high:
                    conditions["volatility"] = "HIGH"
                elif latest_atr < self.recent_atr_avg * self.volatility_threshold_low:
                    conditions["volatility"] = "LOW"
                else:
                    conditions["volatility"] = "NORMAL"
            else:  # If recent_atr_avg is zero, cannot determine volatility dynamically
                conditions["volatility"] = "UNKNOWN"
        else:
            conditions["volatility"] = (
                "UNKNOWN"  # ATR is 0, implying no movement or insufficient data
            )

        self.logger.debug(f"Market Conditions: {conditions}")
        return conditions
