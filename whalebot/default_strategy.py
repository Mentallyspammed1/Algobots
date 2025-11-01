# default_strategy.py

import logging
from typing import Any

import pandas as pd
from strategy_interface import BaseStrategy
from strategy_interface import Signal


class DefaultStrategy(BaseStrategy):
    """A default trading strategy using a combination of EMA crossover, RSI, and MACD."""

    def __init__(self, logger: logging.Logger, **kwargs):
        super().__init__("DefaultStrategy", logger, **kwargs)

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates and adds all necessary technical indicators to the DataFrame."""
        if df.empty:
            self.logger.warning("Empty DataFrame provided for indicator calculation.")
            return df

        df.ta.ema(
            length=self.strategy_ema_fast_period,
            append=True,
            col_names=(f"EMA_{self.strategy_ema_fast_period}",),
        )
        df.ta.ema(
            length=self.strategy_ema_slow_period,
            append=True,
            col_names=(f"EMA_{self.strategy_ema_slow_period}",),
        )
        df.ta.rsi(
            length=self.strategy_rsi_period,
            append=True,
            col_names=(f"RSI_{self.strategy_rsi_period}",),
        )
        df.ta.macd(
            fast=self.strategy_macd_fast_period,
            slow=self.strategy_macd_slow_period,
            signal=self.strategy_macd_signal_period,
            append=True,
        )
        df.ta.bbands(
            length=self.strategy_bb_period,
            std=self.strategy_bb_std,
            append=True,
        )
        df.ta.atr(
            length=self.strategy_atr_period,
            append=True,
            col_names=(f"ATR_{self.strategy_atr_period}",),
        )
        df.ta.adx(length=self.strategy_adx_period, append=True)

        df.rename(
            columns={
                f"EMA_{self.strategy_ema_fast_period}": "EMA_Fast",
                f"EMA_{self.strategy_ema_slow_period}": "EMA_Slow",
                f"RSI_{self.strategy_rsi_period}": "RSI",
                f"MACD_{self.strategy_macd_fast_period}_{self.strategy_macd_slow_period}_{self.strategy_macd_signal_period}": "MACD_Line",
                f"MACDh_{self.strategy_macd_fast_period}_{self.strategy_macd_slow_period}_{self.strategy_macd_signal_period}": "MACD_Hist",
                f"MACDs_{self.strategy_macd_fast_period}_{self.strategy_macd_slow_period}_{self.strategy_macd_signal_period}": "MACD_Signal",
                f"BBL_{self.strategy_bb_period}_{self.strategy_bb_std}": "BB_Lower",
                f"BBM_{self.strategy_bb_period}_{self.strategy_bb_std}": "BB_Middle",
                f"BBU_{self.strategy_bb_period}_{self.strategy_bb_std}": "BB_Upper",
                f"ATR_{self.strategy_atr_period}": "ATR",
                f"ADX_{self.strategy_adx_period}": "ADX",
                f"DMP_{self.strategy_adx_period}": "PlusDI",
                f"DMN_{self.strategy_adx_period}": "MinusDI",
            },
            inplace=True,
        )

        df.fillna(method="ffill", inplace=True)
        df.fillna(0, inplace=True)

        self.logger.debug("Indicators calculated for DefaultStrategy.")
        return df

    def generate_signal(
        self,
        df: pd.DataFrame,
        current_market_price: float,
        market_conditions: dict[str, Any],
    ) -> Signal:
        """Generates a trading signal based on calculated indicators and market conditions."""
        min_data_points = (
            max(
                self.strategy_ema_slow_period,
                self.strategy_rsi_period,
                self.strategy_macd_slow_period,
                self.strategy_bb_period,
                self.strategy_atr_period,
                self.strategy_adx_period,
            )
            + 2
        )
        if df.empty or len(df) < min_data_points:
            self.logger.warning(
                "Insufficient data for indicators in DefaultStrategy, returning HOLD.",
            )
            return Signal(
                type="HOLD",
                score=0,
                reasons=["Insufficient data for indicators"],
            )

        latest = df.iloc[-1]
        previous = df.iloc[-2]

        signal_score = 0.0
        reasons = []

        market_phase = market_conditions.get("market_phase", "UNKNOWN")
        market_volatility = market_conditions.get("volatility", "NORMAL")

        ema_weight = 1.0
        rsi_weight = 1.0
        macd_weight = 1.0
        bb_weight = 1.0

        if market_phase == "RANGING":
            bb_weight *= 1.5
            rsi_weight *= 1.2
            ema_weight *= 0.5
            macd_weight *= 0.7
            reasons.append("Adjusting weights for RANGING market.")
        elif market_phase in ["TRENDING_UP", "TRENDING_DOWN"]:
            ema_weight *= 1.5
            macd_weight *= 1.2
            bb_weight *= 0.5
            reasons.append(f"Adjusting weights for {market_phase} market.")

        signal_score_multiplier = 1.2 if market_volatility == "HIGH" else 1.0
        if market_volatility == "HIGH":
            reasons.append("High volatility detected, demanding stronger signals.")

        if (
            latest["EMA_Fast"] > latest["EMA_Slow"]
            and previous["EMA_Fast"] <= previous["EMA_Slow"]
        ):
            signal_score += ema_weight * 2.0
            reasons.append(
                f"EMA Bullish Crossover ({latest['EMA_Fast']:.2f} > {latest['EMA_Slow']:.2f})",
            )
        elif (
            latest["EMA_Fast"] < latest["EMA_Slow"]
            and previous["EMA_Fast"] >= previous["EMA_Slow"]
        ):
            signal_score -= ema_weight * 2.0
            reasons.append(
                f"EMA Bearish Crossover ({latest['EMA_Fast']:.2f} < {latest['EMA_Slow']:.2f})",
            )
        elif latest["EMA_Fast"] > latest["EMA_Slow"]:
            signal_score += ema_weight * 0.5
            reasons.append(
                f"EMA Bullish Trend Continuation ({latest['EMA_Fast']:.2f} > {latest['EMA_Slow']:.2f})",
            )
        elif latest["EMA_Fast"] < latest["EMA_Slow"]:
            signal_score -= ema_weight * 0.5
            reasons.append(
                f"EMA Bearish Trend Continuation ({latest['EMA_Fast']:.2f} < {latest['EMA_Slow']:.2f})",
            )

        if (
            latest["RSI"] < self.strategy_rsi_oversold
            and previous["RSI"] >= self.strategy_rsi_oversold
        ):
            signal_score += rsi_weight * 1.5
            reasons.append(f"RSI Entering Oversold ({latest['RSI']:.2f})")
        elif (
            latest["RSI"] > self.strategy_rsi_overbought
            and previous["RSI"] <= self.strategy_rsi_overbought
        ):
            signal_score -= rsi_weight * 1.5
            reasons.append(f"RSI Entering Overbought ({latest['RSI']:.2f})")

        if (
            latest["MACD_Line"] > latest["MACD_Signal"]
            and previous["MACD_Line"] <= previous["MACD_Signal"]
        ):
            signal_score += macd_weight * 1.5
            reasons.append("MACD Bullish Crossover")
        elif (
            latest["MACD_Line"] < latest["MACD_Signal"]
            and previous["MACD_Line"] >= previous["MACD_Signal"]
        ):
            signal_score -= macd_weight * 1.5
            reasons.append("MACD Bearish Crossover")

        if (
            current_market_price < latest["BB_Lower"]
            and previous["close"] >= previous["BB_Lower"]
        ):
            signal_score += bb_weight * 1.0
            reasons.append(f"Price Break Below BB_Lower ({current_market_price:.2f})")
        elif (
            current_market_price > latest["BB_Upper"]
            and previous["close"] <= previous["BB_Upper"]
        ):
            signal_score -= bb_weight * 1.0
            reasons.append(f"Price Break Above BB_Upper ({current_market_price:.2f})")
        elif (
            current_market_price < latest["BB_Middle"]
            and latest["BB_Middle"] > previous["BB_Middle"]
        ):
            signal_score += bb_weight * 0.2
            reasons.append("Price Below BB_Middle, Middle Rising")
        elif (
            current_market_price > latest["BB_Middle"]
            and latest["BB_Middle"] < previous["BB_Middle"]
        ):
            signal_score -= bb_weight * 0.2
            reasons.append("Price Above BB_Middle, Middle Falling")

        signal_score *= signal_score_multiplier

        if signal_score >= self.strategy_buy_score_threshold:
            signal_type = "BUY"
        elif signal_score <= self.strategy_sell_score_threshold:
            signal_type = "SELL"
        else:
            signal_type = "HOLD"

        self.logger.debug(
            f"DefaultStrategy Score: {signal_score:.2f}, Type: {signal_type}, Reasons: {reasons}",
        )
        return Signal(type=signal_type, score=signal_score, reasons=reasons)

    def get_indicator_values(self, df: pd.DataFrame) -> dict[str, float]:
        """Extracts the latest values of key indicators after calculation."""
        if df.empty:
            return {}

        latest_row = df.iloc[-1]
        indicators = {}

        for col in [
            "close",
            "open",
            "high",
            "low",
            "volume",
            "ATR",
            "RSI",
            "MACD_Line",
            "MACD_Hist",
            "MACD_Signal",
            "BB_Lower",
            "BB_Middle",
            "BB_Upper",
            "ADX",
            "PlusDI",
            "MinusDI",
        ]:
            if col in latest_row and pd.notna(latest_row[col]):
                indicators[col] = float(latest_row[col])
            else:
                indicators[col] = 0.0
        return indicators
