# strategy.py
import pandas as pd
import logging
from typing import List, Dict, Any, Tuple

from bot_logger import setup_logging

# Initialize logging for strategy
strategy_logger = logging.getLogger('strategy')
strategy_logger.setLevel(logging.INFO)
# Ensure handlers are not duplicated if setup_logging is called elsewhere
if not strategy_logger.handlers:
    setup_logging() # Call the centralized setup

def generate_signals(df: pd.DataFrame, resistance_levels: List[Dict[str, Any]], support_levels: List[Dict[str, Any]],
                    stoch_k_period: int, stoch_d_period: int,
                    overbought: int, oversold: int, use_crossover: bool) -> List[Tuple[str, float, Any, Dict[str, Any]]]:
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

    # --- StochRSI Signal Logic ---
    stoch_info = {'stoch_k': latest_stoch_k, 'stoch_d': latest_stoch_d}

    if prev_stoch_k is not None and prev_stoch_d is not None:
        if use_crossover:
            # Buy signal: %K crosses above %D, both below oversold
            if prev_stoch_k < prev_stoch_d and latest_stoch_k > latest_stoch_d and \
               latest_stoch_k < oversold:
                signals.append(('BUY', latest_close, current_timestamp, {**stoch_info, 'stoch_type': 'k_cross_d_buy'}))
                strategy_logger.info(f"StochRSI Buy Signal (K cross D below {oversold}): K={latest_stoch_k:.2f}, D={latest_stoch_d:.2f}")

            # Sell signal: %K crosses below %D, both above overbought
            elif prev_stoch_k > prev_stoch_d and latest_stoch_k < latest_stoch_d and \
                 latest_stoch_k > overbought:
                signals.append(('SELL', latest_close, current_timestamp, {**stoch_info, 'stoch_type': 'k_cross_d_sell'}))
                strategy_logger.info(f"StochRSI Sell Signal (K cross D above {overbought}): K={latest_stoch_k:.2f}, D={latest_stoch_d:.2f}")
        else:
            # Buy signal: %K crosses above oversold level
            if prev_stoch_k < oversold and latest_stoch_k >= oversold:
                signals.append(('BUY', latest_close, current_timestamp, {**stoch_info, 'stoch_type': 'k_oversold_bounce'}))
                strategy_logger.info(f"StochRSI Buy Signal (K bounce from {oversold}): K={latest_stoch_k:.2f}")

            # Sell signal: %K crosses below overbought level
            elif prev_stoch_k > overbought and latest_stoch_k <= overbought:
                signals.append(('SELL', latest_close, current_timestamp, {**stoch_info, 'stoch_type': 'k_overbought_rejection'}))
                strategy_logger.info(f"StochRSI Sell Signal (K rejection from {overbought}): K={latest_stoch_k:.2f}")

    # --- Optional: Pivot Point Confirmation (Fibonacci) ---
    # For Fibonacci pivots, we don't use tolerance percentage in the same way.
    # We can check if the current price is near any of the levels.
    # This part might need more sophisticated logic depending on how you want to use Fibonacci pivots.
    # For now, we'll just log them.
    if resistance_levels:
        for r_level in resistance_levels:
            strategy_logger.debug(f"Fibonacci Resistance {r_level['type']}: {r_level['price']:.2f}")
    if support_levels:
        for s_level in support_levels:
            strategy_logger.debug(f"Fibonacci Support {s_level['type']}: {s_level['price']:.2f}")

    # Example: If price is near R1 and StochRSI is overbought, consider a sell signal
    # This is a placeholder and needs to be refined based on your strategy
    # For now, the primary signals come from StochRSI crossovers/levels.

    return signals

def generate_exit_signals(df: pd.DataFrame, current_position_side: str,
                          stoch_k_period: int, stoch_d_period: int,
                          overbought: int, oversold: int, use_crossover: bool) -> List[Tuple[str, float, Any, Dict[str, Any]]]:
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

    stoch_info = {'stoch_k': latest_stoch_k, 'stoch_d': latest_stoch_d}

    if prev_stoch_k is not None and prev_stoch_d is not None:
        if current_position_side == 'BUY':
            # Exit Long signal: StochRSI becomes overbought or crosses down
            if use_crossover:
                if prev_stoch_k > prev_stoch_d and latest_stoch_k < latest_stoch_d and \
                   latest_stoch_k > overbought: # K crosses below D from overbought
                    exit_signals.append(('SELL', latest_close, current_timestamp, {**stoch_info, 'stoch_type': 'k_cross_d_exit_long'}))
                    strategy_logger.info(f"StochRSI Exit Long Signal (K cross D from overbought): K={latest_stoch_k:.2f}, D={latest_stoch_d:.2f}")
            else:
                if prev_stoch_k > overbought and latest_stoch_k <= overbought: # K crosses below overbought
                    exit_signals.append(('SELL', latest_close, current_timestamp, {**stoch_info, 'stoch_type': 'k_overbought_exit_long'}))
                    strategy_logger.info(f"StochRSI Exit Long Signal (K crosses below overbought): K={latest_stoch_k:.2f}")

        elif current_position_side == 'SELL':
            # Exit Short signal: StochRSI becomes oversold or crosses up
            if use_crossover:
                if prev_stoch_k < prev_stoch_d and latest_stoch_k > latest_stoch_d and \
                   latest_stoch_k < oversold: # K crosses above D from oversold
                    exit_signals.append(('BUY', latest_close, current_timestamp, {**stoch_info, 'stoch_type': 'k_cross_d_exit_short'}))
                    strategy_logger.info(f"StochRSI Exit Short Signal (K cross D from oversold): K={latest_stoch_k:.2f}, D={latest_stoch_d:.2f}")
            else:
                if prev_stoch_k < oversold and latest_stoch_k >= oversold: # K crosses above oversold
                    exit_signals.append(('BUY', latest_close, current_timestamp, {**stoch_info, 'stoch_type': 'k_oversold_exit_short'}))
                    strategy_logger.info(f"StochRSI Exit Short Signal (K crosses above oversold): K={latest_stoch_k:.2f}")

    return exit_signals