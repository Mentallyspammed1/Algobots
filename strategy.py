import pandas as pd
import logging
from typing import List, Dict, Any, Tuple
from decimal import Decimal # Import Decimal

from bot_logger import setup_logging
from config import SMA_PERIOD, PIVOT_TOLERANCE_PCT # Import new config parameters

# Initialize logging for strategy
strategy_logger = logging.getLogger('strategy')
strategy_logger.setLevel(logging.INFO)
# Ensure handlers are not duplicated if setup_logging is called elsewhere
if not strategy_logger.handlers:
    setup_logging() # Call the centralized setup

def generate_signals(df: pd.DataFrame, resistance_levels: List[Dict[str, Any]], support_levels: List[Dict[str, Any]],
                    stoch_k_period: int, stoch_d_period: int,
                    overbought: int, oversold: int, use_crossover: bool) -> List[Tuple[str, Decimal, Any, Dict[str, Any]]]:
    """
    Generates trading signals based on StochRSI and optionally pivot points.

    Signals are returned as a list of tuples:
    ('BUY'/'SELL', price, timestamp, {indicator_info}).

    Args:
        df (pd.DataFrame): DataFrame with 'close' prices and DatetimeIndex.
        resistance_levels (list): List of detected resistance levels.
        support_levels (list): List of detected support levels.
        stoch_k_period (int): Period for RSI calculation within StochRSI.
        stoch_d_period (int): Smoothing period for StochRSI %K and %D lines.
        overbought (int): StochRSI overbought level.
        oversold (int): StochRSI oversold level.
        use_crossover (bool): True for K/D line crossover, False for K line crossing levels.
        pivot_tolerance_pct (float): Percentage tolerance for price proximity to pivot levels.

    Returns:
        list: A list of signal tuples.
    """
    signals = []

    if df.empty:
        strategy_logger.warning("Empty DataFrame provided to generate_signals.")
        return signals

    # StochRSI is now calculated in indicators.py and passed in the DataFrame
    # Ensure the DataFrame has the stoch_k and stoch_d columns
    if 'stoch_k' not in df.columns or 'stoch_d' not in df.columns:
        strategy_logger.error("DataFrame must contain 'stoch_k' and 'stoch_d' columns for signal generation.")
        return signals

    latest_close = df['close'].iloc[-1]
    latest_stoch_k = df['stoch_k'].iloc[-1]
    latest_stoch_d = df['stoch_d'].iloc[-1]
    current_timestamp = df.index[-1]

    prev_stoch_k = df['stoch_k'].iloc[-2] if len(df) > 1 else None
    prev_stoch_d = df['stoch_d'].iloc[-2] if len(df) > 1 else None

    # Convert overbought/oversold to Decimal for consistent comparison
    overbought_dec = Decimal(str(overbought))
    oversold_dec = Decimal(str(oversold))

    # --- StochRSI Signal Logic ---
    stoch_info = {'stoch_k': latest_stoch_k, 'stoch_d': latest_stoch_d}

    # Ensure the DataFrame has the sma, ehlers_fisher, and ehlers_supersmoother columns
    if 'sma' not in df.columns or 'ehlers_fisher' not in df.columns or 'ehlers_supersmoother' not in df.columns:
        strategy_logger.error("DataFrame must contain 'sma', 'ehlers_fisher', and 'ehlers_supersmoother' columns for signal generation.")
        return signals

    latest_sma = df['sma'].iloc[-1]
    latest_ehlers_fisher = df['ehlers_fisher'].iloc[-1]
    latest_ehlers_supersmoother = df['ehlers_supersmoother'].iloc[-1]

    # --- StochRSI Signal Logic ---
    stoch_info = {'stoch_k': latest_stoch_k, 'stoch_d': latest_stoch_d}
    ehlers_info = {'fisher': latest_ehlers_fisher, 'supersmoother': latest_ehlers_supersmoother}

    # Trend filter: Only trade in the direction of the SMA
    is_uptrend = latest_close > latest_sma
    is_downtrend = latest_close < latest_sma

    if prev_stoch_k is not None and prev_stoch_d is not None:
        # Buy signal conditions
        if is_uptrend: # Only consider buy signals in an uptrend
            if use_crossover:
                # %K crosses above %D, both below oversold
                if prev_stoch_k < prev_stoch_d and latest_stoch_k > latest_stoch_d and \
                   latest_stoch_k < oversold_dec:
                    # Check for confluence with support levels
                    near_support = False
                    for s_level in support_levels:
                        if abs(latest_close - s_level['price']) <= latest_close * Decimal(str(PIVOT_TOLERANCE_PCT)):
                            near_support = True
                            break
                    if near_support:
                        signals.append(('BUY', latest_close, current_timestamp, {**stoch_info, **ehlers_info, 'stoch_type': 'k_cross_d_buy', 'confluence': 'pivot_support'}))
                        strategy_logger.info(f"StochRSI Buy Signal (K cross D below {oversold_dec:.2f}) with Pivot Support: K={latest_stoch_k:.2f}, D={latest_stoch_d:.2f}")
            else:
                # %K crosses above oversold level
                if prev_stoch_k < oversold_dec and latest_stoch_k >= oversold_dec:
                    # Check for confluence with support levels
                    near_support = False
                    for s_level in support_levels:
                        if abs(latest_close - s_level['price']) <= latest_close * Decimal(str(PIVOT_TOLERANCE_PCT)):
                            near_support = True
                            break
                    if near_support:
                        signals.append(('BUY', latest_close, current_timestamp, {**stoch_info, **ehlers_info, 'stoch_type': 'k_oversold_bounce', 'confluence': 'pivot_support'}))
                        strategy_logger.info(f"StochRSI Buy Signal (K bounce from {oversold_dec:.2f}) with Pivot Support: K={latest_stoch_k:.2f}")

        # Sell signal conditions
        if is_downtrend: # Only consider sell signals in a downtrend
            if use_crossover:
                # %K crosses below %D, both above overbought
                if prev_stoch_k > prev_stoch_d and latest_stoch_k < latest_stoch_d and \
                   latest_stoch_k > overbought_dec:
                    # Check for confluence with resistance levels
                    near_resistance = False
                    for r_level in resistance_levels:
                        if abs(latest_close - r_level['price']) <= latest_close * Decimal(str(PIVOT_TOLERANCE_PCT)):
                            near_resistance = True
                            break
                    if near_resistance:
                        signals.append(('SELL', latest_close, current_timestamp, {**stoch_info, **ehlers_info, 'stoch_type': 'k_cross_d_sell', 'confluence': 'pivot_resistance'}))
                        strategy_logger.info(f"StochRSI Sell Signal (K cross D above {overbought_dec:.2f}) with Pivot Resistance: K={latest_stoch_k:.2f}, D={latest_stoch_d:.2f}")
            else:
                # %K crosses below overbought level
                if prev_stoch_k > overbought_dec and latest_stoch_k <= overbought_dec:
                    # Check for confluence with resistance levels
                    near_resistance = False
                    for r_level in resistance_levels:
                        if abs(latest_close - r_level['price']) <= latest_close * Decimal(str(PIVOT_TOLERANCE_PCT)):
                            near_resistance = True
                            break
                    if near_resistance:
                        signals.append(('SELL', latest_close, current_timestamp, {**stoch_info, **ehlers_info, 'stoch_type': 'k_overbought_rejection', 'confluence': 'pivot_resistance'}))
                        strategy_logger.info(f"StochRSI Sell Signal (K rejection from {overbought_dec:.2f}) with Pivot Resistance: K={latest_stoch_k:.2f}")

    return signals

def generate_exit_signals(df: pd.DataFrame, current_position_side: str,
                          stoch_k_period: int, stoch_d_period: int,
                          overbought: int, oversold: int, use_crossover: bool) -> List[Tuple[str, Decimal, Any, Dict[str, Any]]]:
    """
    Generates exit signals based on StochRSI for an open position.

    Args:
        df (pd.DataFrame): DataFrame with 'close' prices and DatetimeIndex.
        current_position_side (str): The side of the current open position ('BUY' or 'SELL').
        stoch_k_period (int): Period for RSI calculation within StochRSI.
        stoch_d_period (int): Smoothing period for StochRSI %K and %D lines.
        overbought (int): StochRSI overbought level.
        oversold (int): StochRSI oversold level.
        use_crossover (bool): True for K/D line crossover, False for K line crossing levels.

    Returns:
        list: A list of exit signal tuples.
    """
    exit_signals = []

    if df.empty:
        strategy_logger.warning("Empty DataFrame provided to generate_exit_signals.")
        return exit_signals

    # StochRSI is now calculated in indicators.py and passed in the DataFrame
    # Ensure the DataFrame has the stoch_k and stoch_d columns
    if 'stoch_k' not in df.columns or 'stoch_d' not in df.columns:
        strategy_logger.error("DataFrame must contain 'stoch_k' and 'stoch_d' columns for exit signal generation.")
        return exit_signals

    latest_close = df['close'].iloc[-1]
    latest_stoch_k = df['stoch_k'].iloc[-1]
    latest_stoch_d = df['stoch_d'].iloc[-1]
    current_timestamp = df.index[-1]

    prev_stoch_k = df['stoch_k'].iloc[-2] if len(df) > 1 else None
    prev_stoch_d = df['stoch_d'].iloc[-2] if len(df) > 1 else None

    # Convert overbought/oversold to Decimal for consistent comparison
    overbought_dec = Decimal(str(overbought))
    oversold_dec = Decimal(str(oversold))

    # Ensure the DataFrame has the sma, ehlers_fisher, and ehlers_supersmoother columns
    if 'sma' not in df.columns or 'ehlers_fisher' not in df.columns or 'ehlers_supersmoother' not in df.columns:
        strategy_logger.error("DataFrame must contain 'sma', 'ehlers_fisher', and 'ehlers_supersmoother' columns for exit signal generation.")
        return exit_signals

    latest_sma = df['sma'].iloc[-1]
    latest_ehlers_fisher = df['ehlers_fisher'].iloc[-1]
    latest_ehlers_supersmoother = df['ehlers_supersmoother'].iloc[-1]

    stoch_info = {'stoch_k': latest_stoch_k, 'stoch_d': latest_stoch_d}
    ehlers_info = {'fisher': latest_ehlers_fisher, 'supersmoother': latest_ehlers_supersmoother}

    # Trend filter: Only exit in the direction of the SMA (or against if reversal)
    is_uptrend = latest_close > latest_sma
    is_downtrend = latest_close < latest_sma

    if prev_stoch_k is not None and prev_stoch_d is not None:
        if current_position_side == 'BUY':
            # Exit Long signal: StochRSI becomes overbought or crosses down
            # Consider exiting if in downtrend or StochRSI indicates reversal
            if is_downtrend or (use_crossover and prev_stoch_k > prev_stoch_d and latest_stoch_k < latest_stoch_d and latest_stoch_k > overbought_dec): # K crosses below D from overbought
                exit_signals.append(('SELL', latest_close, current_timestamp, {**stoch_info, **ehlers_info, 'stoch_type': 'k_cross_d_exit_long'}))
                strategy_logger.info(f"StochRSI Exit Long Signal (K cross D from overbought) or Downtrend: K={latest_stoch_k:.2f}, D={latest_stoch_d:.2f}")
            elif not use_crossover and prev_stoch_k > overbought_dec and latest_stoch_k <= overbought_dec: # K crosses below overbought
                exit_signals.append(('SELL', latest_close, current_timestamp, {**stoch_info, **ehlers_info, 'stoch_type': 'k_overbought_exit_long'}))
                strategy_logger.info(f"StochRSI Exit Long Signal (K crosses below overbought): K={latest_stoch_k:.2f}")

        elif current_position_side == 'SELL':
            # Exit Short signal: StochRSI becomes oversold or crosses up
            # Consider exiting if in uptrend or StochRSI indicates reversal
            if is_uptrend or (use_crossover and prev_stoch_k < prev_stoch_d and latest_stoch_k > latest_stoch_d and latest_stoch_k < oversold_dec): # K crosses above D from oversold
                exit_signals.append(('BUY', latest_close, current_timestamp, {**stoch_info, **ehlers_info, 'stoch_type': 'k_cross_d_exit_short'}))
                strategy_logger.info(f"StochRSI Exit Short Signal (K cross D from oversold) or Uptrend: K={latest_stoch_k:.2f}, D={latest_stoch_d:.2f}")
            elif not use_crossover and prev_stoch_k < oversold_dec and latest_stoch_k >= oversold_dec: # K crosses above oversold
                exit_signals.append(('BUY', latest_close, current_timestamp, {**stoch_info, **ehlers_info, 'stoch_type': 'k_oversold_exit_short'}))
                strategy_logger.info(f"StochRSI Exit Short Signal (K crosses above oversold): K={latest_stoch_k:.2f}")

    return exit_signals
