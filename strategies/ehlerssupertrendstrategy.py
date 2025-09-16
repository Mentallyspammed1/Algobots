from decimal import Decimal
from typing import Any

import pandas as pd
from algobots_types import OrderBlock
from indicators import (
    calculate_ehlers_fisher_strategy,
    calculate_sma,
    calculate_supertrend,
)


class EhlersSupertrendStrategy:
    """Ehlers Supertrend Strategy for generating entry and exit signals.
    This version is updated to use centralized indicator functions for consistency and robustness.
    """
    def __init__(self, logger,
                 ehlers_period: int = 10,
                 supertrend_period: int = 10,
                 supertrend_multiplier: float = 3.0,
                 stop_loss_percentage: float = 0.02,
                 take_profit_percentage: float = 0.04,
                 sma_period: int = 20):

        self.logger = logger
        self.ehlers_period = ehlers_period
        self.supertrend_period = supertrend_period
        self.supertrend_multiplier = supertrend_multiplier
        self.stop_loss_percentage = Decimal(str(stop_loss_percentage))
        self.take_profit_percentage = Decimal(str(take_profit_percentage))
        self.sma_period = sma_period

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates all necessary indicators for the strategy using centralized functions.
        """
        df = calculate_ehlers_fisher_strategy(df, length=self.ehlers_period)
        df = calculate_supertrend(df, period=self.supertrend_period, multiplier=self.supertrend_multiplier)
        df['sma'] = calculate_sma(df, length=self.sma_period)
        return df

    def generate_signals(self,
                         df: pd.DataFrame,
                         resistance_levels: list[dict[str, Any]],
                         support_levels: list[dict[str, Any]],
                         active_bull_obs: list[OrderBlock],
                         active_bear_obs: list[OrderBlock],
                         **kwargs) -> list[tuple[str, Decimal, Any, dict[str, Any]]]:
        """Generates entry signals based on the Ehlers Supertrend strategy.
        """
        signals = []
        if df.empty:
            self.logger.warning("DataFrame is empty, cannot generate signals.")
            return []

        min_required_bars = max(self.ehlers_period, self.supertrend_period, self.sma_period) + 2
        if len(df) < min_required_bars:
            self.logger.debug(f"Not enough data for signals. Need {min_required_bars}, have {len(df)}.")
            return []

        df_copy = self._calculate_indicators(df.copy())

        last_bar = df_copy.iloc[-1]
        prev_bar = df_copy.iloc[-2]

        # --- Ensure all required data is present ---
        required_cols = ['supertrend_direction', 'ehlers_fisher', 'ehlers_signal', 'sma', 'close']
        if any(col not in last_bar or pd.isna(last_bar[col]) for col in required_cols) or \
           any(col not in prev_bar or pd.isna(prev_bar[col]) for col in required_cols):
            self.logger.debug("Missing indicator values on last or previous bar, skipping signal generation.")
            return []

        # --- Signal Logic ---
        is_supertrend_bullish_turn = last_bar['supertrend_direction'] == 1 and prev_bar['supertrend_direction'] == -1
        is_fisher_bullish_cross = last_bar['ehlers_fisher'] > last_bar['ehlers_signal'] and prev_bar['ehlers_fisher'] <= prev_bar['ehlers_signal']
        is_above_sma = last_bar['close'] > last_bar['sma']

        if is_supertrend_bullish_turn and is_fisher_bullish_cross and is_above_sma:
            entry_price = last_bar['close']
            signal_info = {
                'indicator': 'Ehlers Supertrend', 'trend_filter': 'SMA',
                'supertrend_direction': int(last_bar['supertrend_direction']),
                'ehlers_fisher': float(last_bar['ehlers_fisher']),
                'current_sma': float(last_bar['sma'])
            }
            self.logger.info(f"Generated BUY signal at {entry_price:.4f}")
            signals.append(("BUY", entry_price, pd.Timestamp(last_bar.name), signal_info))

        is_supertrend_bearish_turn = last_bar['supertrend_direction'] == -1 and prev_bar['supertrend_direction'] == 1
        is_fisher_bearish_cross = last_bar['ehlers_fisher'] < last_bar['ehlers_signal'] and prev_bar['ehlers_fisher'] >= prev_bar['ehlers_signal']
        is_below_sma = last_bar['close'] < last_bar['sma']

        if is_supertrend_bearish_turn and is_fisher_bearish_cross and is_below_sma:
            entry_price = last_bar['close']
            signal_info = {
                'indicator': 'Ehlers Supertrend', 'trend_filter': 'SMA',
                'supertrend_direction': int(last_bar['supertrend_direction']),
                'ehlers_fisher': float(last_bar['ehlers_fisher']),
                'current_sma': float(last_bar['sma'])
            }
            self.logger.info(f"Generated SELL signal at {entry_price:.4f}")
            signals.append(("SELL", entry_price, pd.Timestamp(last_bar.name), signal_info))

        return signals

    def generate_exit_signals(self,
                              df: pd.DataFrame,
                              current_position_side: str,
                              active_bull_obs: list[OrderBlock],
                              active_bear_obs: list[OrderBlock],
                              **kwargs) -> list[tuple[str, Decimal, Any, dict[str, Any]]]:
        """Generates exit signals based on a change in the Supertrend direction or a Fisher Transform cross.
        """
        exit_signals = []
        if df.empty or current_position_side not in ['Buy', 'Sell']:
            return []

        min_required_bars = max(self.ehlers_period, self.supertrend_period) + 2
        if len(df) < min_required_bars:
            self.logger.debug(f"Not enough data for exit signals. Need {min_required_bars}, have {len(df)}.")
            return []

        df_copy = self._calculate_indicators(df.copy())

        last_bar = df_copy.iloc[-1]
        prev_bar = df_copy.iloc[-2]

        required_cols = ['supertrend_direction', 'ehlers_fisher', 'ehlers_signal', 'close']
        if any(col not in last_bar or pd.isna(last_bar[col]) for col in required_cols) or \
           any(col not in prev_bar or pd.isna(prev_bar[col]) for col in required_cols):
            self.logger.debug("Missing indicator values for exit signal generation.")
            return []

        current_price = last_bar['close']
        exit_reason = None

        if current_position_side == 'Buy':
            if last_bar['supertrend_direction'] == -1 and prev_bar['supertrend_direction'] == 1:
                exit_reason = 'Supertrend turned bearish'
            elif last_bar['ehlers_fisher'] < last_bar['ehlers_signal'] and prev_bar['ehlers_fisher'] >= prev_bar['ehlers_signal']:
                exit_reason = 'Ehlers Fisher crossed below signal'

            if exit_reason:
                exit_info = {'indicator': 'Ehlers Supertrend', 'reason': exit_reason}
                self.logger.info(f"Generated SELL_TO_CLOSE signal at {current_price:.4f}. Reason: {exit_reason}")
                exit_signals.append(("SELL_TO_CLOSE", current_price, pd.Timestamp(last_bar.name), exit_info))

        elif current_position_side == 'Sell':
            if last_bar['supertrend_direction'] == 1 and prev_bar['supertrend_direction'] == -1:
                exit_reason = 'Supertrend turned bullish'
            elif last_bar['ehlers_fisher'] > last_bar['ehlers_signal'] and prev_bar['ehlers_fisher'] <= prev_bar['ehlers_signal']:
                exit_reason = 'Ehlers Fisher crossed above signal'

            if exit_reason:
                exit_info = {'indicator': 'Ehlers Supertrend', 'reason': exit_reason}
                self.logger.info(f"Generated BUY_TO_CLOSE signal at {current_price:.4f}. Reason: {exit_reason}")
                exit_signals.append(("BUY_TO_CLOSE", current_price, pd.Timestamp(last_bar.name), exit_info))

        return exit_signals


