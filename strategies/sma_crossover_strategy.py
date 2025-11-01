from decimal import Decimal
from typing import Any

import pandas as pd
from algobots_types import OrderBlock
from color_codex import COLOR_CYAN
from color_codex import COLOR_GREEN
from color_codex import COLOR_RED
from color_codex import COLOR_RESET
from color_codex import COLOR_YELLOW
from config import SMA_PERIOD  # Assuming SMA_PERIOD is defined in config.py
from strategies.strategy_template import StrategyTemplate


class SMA_Crossover_Strategy(StrategyTemplate):
    def __init__(self, logger):
        super().__init__(logger)
        self.logger.info("SMA_Crossover_Strategy initialized.")

    def _calculate_sma(self, df: pd.DataFrame, length: int) -> pd.Series:
        if "close" not in df.columns:
            self.logger.error(
                "DataFrame must contain a 'close' column for SMA calculation."
            )
            return pd.Series(dtype="object")
        close_prices = df["close"].apply(Decimal)
        sma = close_prices.rolling(window=length).mean()
        return sma

    def generate_signals(
        self,
        df: pd.DataFrame,
        resistance_levels: list[dict[str, Any]],
        support_levels: list[dict[str, Any]],
        active_bull_obs: list[OrderBlock],
        active_bear_obs: list[OrderBlock],
        **kwargs,
    ) -> list[tuple[str, Decimal, Any, dict[str, Any]]]:
        signals = []

        if (
            df.empty or len(df) < SMA_PERIOD + 1
        ):  # Need at least SMA_PERIOD + 1 for crossover
            self.logger.warning(
                f"{COLOR_YELLOW}DataFrame too short for SMA Crossover signal generation. Required at least {SMA_PERIOD + 1} rows.{COLOR_RESET}"
            )
            return signals

        # Calculate SMA
        df["sma"] = self._calculate_sma(df, SMA_PERIOD)

        # Ensure SMA values are not NaN for the last two candles
        if pd.isna(df["sma"].iloc[-1]) or pd.isna(df["sma"].iloc[-2]):
            self.logger.debug(
                "SMA values are NaN for recent candles. Skipping signal generation."
            )
            return signals

        latest_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]
        latest_sma = df["sma"].iloc[-1]
        prev_sma = df["sma"].iloc[-2]
        current_timestamp = df.index[-1]

        # Buy signal: Price crosses above SMA
        if prev_close < prev_sma and latest_close > latest_sma:
            signals.append(
                ("BUY", latest_close, current_timestamp, {"strategy": "SMA_Crossover"})
            )
            self.logger.info(
                f"{COLOR_GREEN}BUY Signal (SMA Crossover) at {latest_close:.2f}.{COLOR_RESET}"
            )

        # Sell signal: Price crosses below SMA
        elif prev_close > prev_sma and latest_close < latest_sma:
            signals.append(
                ("SELL", latest_close, current_timestamp, {"strategy": "SMA_Crossover"})
            )
            self.logger.info(
                f"{COLOR_RED}SELL Signal (SMA Crossover) at {latest_close:.2f}.{COLOR_RESET}"
            )

        return signals

    def generate_exit_signals(
        self,
        df: pd.DataFrame,
        current_position_side: str,
        active_bull_obs: list[OrderBlock],
        active_bear_obs: list[OrderBlock],
        **kwargs,
    ) -> list[tuple[str, Decimal, Any, dict[str, Any]]]:
        exit_signals = []

        if df.empty or len(df) < SMA_PERIOD + 1:
            return exit_signals

        df["sma"] = self._calculate_sma(df, SMA_PERIOD)

        if pd.isna(df["sma"].iloc[-1]) or pd.isna(df["sma"].iloc[-2]):
            return exit_signals

        latest_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]
        latest_sma = df["sma"].iloc[-1]
        prev_sma = df["sma"].iloc[-2]
        current_timestamp = df.index[-1]

        if current_position_side == "BUY":
            # Exit long: Price crosses below SMA
            if prev_close > prev_sma and latest_close < latest_sma:
                exit_signals.append(
                    (
                        "EXIT_BUY",
                        latest_close,
                        current_timestamp,
                        {"strategy": "SMA_Crossover_Exit"},
                    )
                )
                self.logger.info(
                    f"{COLOR_CYAN}EXIT BUY Signal (SMA Crossover) at {latest_close:.2f}.{COLOR_RESET}"
                )
        elif current_position_side == "SELL":
            # Exit short: Price crosses above SMA
            if prev_close < prev_sma and latest_close > latest_sma:
                exit_signals.append(
                    (
                        "EXIT_SELL",
                        latest_close,
                        current_timestamp,
                        {"strategy": "SMA_Crossover_Exit"},
                    )
                )
                self.logger.info(
                    f"{COLOR_CYAN}EXIT SELL Signal (SMA Crossover) at {latest_close:.2f}.{COLOR_RESET}"
                )

        return exit_signals
