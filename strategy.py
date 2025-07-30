
# File: strategy.py

import pandas as pd
import logging
from typing import List, Dict, Any, Tuple
from decimal import Decimal
# Ensure this is correctly defined in algobots_types.py
from algobots_types import OrderBlock

from bot_logger import setup_logging # Assuming this sets up your logger
# Ensure these are defined in your config.py
from config import SMA_PERIOD, PIVOT_TOLERANCE_PCT, OB_TOLERANCE_PCT, EHLERS_FISHER_SIGNAL_PERIOD
from color_codex import COLOR_RED, COLOR_YELLOW, COLOR_GREEN, COLOR_CYAN, COLOR_RESET

# Initialize logging for strategy
strategy_logger = logging.getLogger('strategy')
strategy_logger.setLevel(logging.DEBUG) # Use DEBUG for detailed internal logic, INFO for signals

def _to_decimal(value: Any) -> Decimal:
    """
    Transmutes a value into a Decimal, ensuring precision for financial calculations.
    This prevents floating-point inaccuracies that can plague financial systems.
    Handles None gracefully by returning Decimal('0').
    """
    if value is None:
        return Decimal('0')
    try:
        # Convert to string first to avoid floating point inaccuracies during Decimal conversion
        return Decimal(str(value))
    except Exception as e:
        strategy_logger.error(f"{COLOR_RED}Failed to transmute '{value}' to Decimal: {e}{COLOR_RESET}")
        return Decimal('0')

def _check_confluence(latest_close: Decimal,
                      levels: List[Dict[str, Any]],
                      level_tolerance_pct: float,
                      active_obs: List[OrderBlock],
                      ob_tolerance_pct: float,
                      is_for_buy_signal: bool) -> Tuple[bool, str]:
    """
    Scans for confluence with pivotal levels (support/resistance) and active Order Blocks.
    This arcane helper centralizes the logic for market structure validation, determining
    if the current price aligns with key structural zones.

    Args:
        latest_close (Decimal): The current closing price.
        levels (List[Dict[str, Any]]): A list of detected support or resistance levels.
        level_tolerance_pct (float): The percentage tolerance for price proximity to levels.
        active_obs (List[OrderBlock]): A list of active Order Blocks (bullish for buy, bearish for sell/exit).
        ob_tolerance_pct (float): The percentage tolerance for price proximity to Order Blocks.
        is_for_buy_signal (bool): True if checking for a BUY signal's confluence, False for SELL/Exit.

    Returns:
        Tuple[bool, str]: A tuple indicating (True if confluence found, reason string).
    """
    level_tolerance_dec = _to_decimal(level_tolerance_pct)
    ob_tolerance_dec = _to_decimal(ob_tolerance_pct)

    # First, check for proximity to defined support/resistance levels
    for level in levels:
        level_price = _to_decimal(level.get('price'))
        if level_price > Decimal('0'): # Ensure level price is valid to avoid division by zero
            price_diff = abs(latest_close - level_price)
            if level_price != Decimal('0') and price_diff / level_price <= level_tolerance_dec:
                level_type = 'Support' if is_for_buy_signal else 'Resistance'
                return True, f"Near {level_type} {level_price:.2f} ({level_tolerance_pct*100:.3f}%)"

    # Next, scrutinize active Order Blocks for alignment
    for ob in active_obs:
        ob_bottom = _to_decimal(ob.get('bottom'))
        ob_top = _to_decimal(ob.get('top'))

        # Validate OB boundaries to prevent errors and illogical ranges
        if ob_bottom == Decimal('0') or ob_top == Decimal('0') or ob_bottom > ob_top:
            strategy_logger.warning(f"{COLOR_YELLOW}Order Block with invalid boundary detected: {ob}. Skipping.{COLOR_RESET}")
            continue

        # Calculate an extended range for the Order Block based on tolerance
        ob_range = ob_top - ob_bottom
        extended_ob_bottom = ob_bottom - ob_range * ob_tolerance_dec
        extended_ob_top = ob_top + ob_range * ob_tolerance_dec
        
        # Handle zero-range OBs (e.g., single price point) by extending proportionally
        if ob_range == Decimal('0'):
             extended_ob_bottom = ob_bottom * (Decimal('1') - ob_tolerance_dec)
             extended_ob_top = ob_top * (Decimal('1') + ob_tolerance_dec)

        # Check if the latest close price falls within the extended Order Block range
        if latest_close >= extended_ob_bottom and latest_close <= extended_ob_top:
            ob_label = "Bullish" if is_for_buy_signal else "Bearish"
            return True, f"Near {ob_label} Order Block (B: {ob_bottom:.2f}, T: {ob_top:.2f})"
    
    return False, "No structural confluence"


def generate_signals(df: pd.DataFrame, resistance_levels: List[Dict[str, Any]], support_levels: List[Dict[str, Any]],
                    active_bull_obs: List[OrderBlock], active_bear_obs: List[OrderBlock],
                    stoch_k_period: int, stoch_d_period: int,
                    overbought: int, oversold: int, use_crossover: bool,
                    enable_fib_pivot_actions: bool, fib_entry_confirm_percent: float,
                    pivot_support_levels: Dict[str, Decimal], pivot_resistance_levels: Dict[str, Decimal]) -> List[Tuple[str, Decimal, Any, Dict[str, Any]]]:
    """
    Generates trading signals, weaving together StochRSI, Ehlers Fisher, Trend, and Confluence.
    Each signal is a potential opportunity, validated by multiple market dimensions.

    Signals are returned as a list of tuples: ('BUY'/'SELL', price, timestamp, {indicator_info}).

    Args:
        df (pd.DataFrame): DataFrame with 'close' prices and DatetimeIndex. Must contain
                           'stoch_k', 'stoch_d', 'sma', 'ehlers_fisher', 'ehlers_fisher_signal',
                           and 'ehlers_supersmoother' columns.
        resistance_levels (list): List of detected resistance levels.
        support_levels (list): List of detected support levels.
        active_bull_obs (List[OrderBlock]): List of currently active bullish order blocks.
        active_bear_obs (List[OrderBlock]): List of currently active bearish order blocks.
        stoch_k_period (int): Period for RSI calculation within StochRSI.
        stoch_d_period (int): Smoothing period for StochRSI %K and %D lines.
        overbought (int): StochRSI overbought level.
        oversold (int): StochRSI oversold level.
        use_crossover (bool): True for K/D line crossover, False for K line crossing levels.
        enable_fib_pivot_actions (bool): Whether Fibonacci pivot actions are enabled.
        fib_entry_confirm_percent (float): Percentage for Fibonacci entry confirmation.
        pivot_support_levels (dict): Dictionary of Fibonacci support levels.
        pivot_resistance_levels (dict): Dictionary of Fibonacci resistance levels.

    Returns:
        list: A list of signal tuples.
    """
    signals = []

    # Ensure sufficient data for indicator calculations (at least 2 rows for previous values)
    min_rows_needed = max(SMA_PERIOD, stoch_k_period, stoch_d_period, EHLERS_FISHER_SIGNAL_PERIOD, 2)
    if df.empty or len(df) < min_rows_needed:
        strategy_logger.warning(f"{COLOR_YELLOW}DataFrame too short or empty for signal generation. Required at least {min_rows_needed} rows.{COLOR_RESET}")
        return signals

    # Validate essential columns for robust operation
    required_cols = ['stoch_k', 'stoch_d', 'sma', 'ehlers_fisher', 'ehlers_fisher_signal', 'ehlers_supersmoother', 'close']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        strategy_logger.error(f"{COLOR_RED}DataFrame is missing crucial columns for signal generation: {missing_cols}{COLOR_RESET}")
        return signals

    # Extract latest and previous values, transmuted to Decimal for precision
    latest_close = _to_decimal(df['close'].iloc[-1])
    current_timestamp = df.index[-1]

    latest_stoch_k = _to_decimal(df['stoch_k'].iloc[-1])
    latest_stoch_d = _to_decimal(df['stoch_d'].iloc[-1])
    prev_stoch_k = _to_decimal(df['stoch_k'].iloc[-2])
    prev_stoch_d = _to_decimal(df['stoch_d'].iloc[-2])

    latest_ehlers_fisher = _to_decimal(df['ehlers_fisher'].iloc[-1])
    prev_ehlers_fisher = _to_decimal(df['ehlers_fisher'].iloc[-2])
    latest_ehlers_fisher_signal = _to_decimal(df['ehlers_fisher_signal'].iloc[-1])
    prev_ehlers_fisher_signal = _to_decimal(df['ehlers_fisher_signal'].iloc[-2])

    latest_sma = _to_decimal(df['sma'].iloc[-1])
    # Ehlers Supersmoother is available but not explicitly used in signal logic here,
    # though it could be a secondary trend filter.
    latest_ehlers_supersmoother = _to_decimal(df['ehlers_supersmoother'].iloc[-1])

    # Convert thresholds to Decimal for precise comparison
    overbought_dec = _to_decimal(overbought)
    oversold_dec = _to_decimal(oversold)
    fib_entry_confirm_dec = _to_decimal(fib_entry_confirm_percent)

    # --- Trend Filter: Guiding the Direction ---
    # Primary trend defined by price relation to SMA
    current_trend_is_up = latest_close > latest_sma
    current_trend_is_down = latest_close < latest_sma

    # --- Ehlers Fisher Confirmation Logic: Sensing the Market's Breath ---
    # Crossover signals indicate a potential reversal in momentum
    fisher_buy_signal = prev_ehlers_fisher < prev_ehlers_fisher_signal and latest_ehlers_fisher >= latest_ehlers_fisher_signal
    fisher_sell_signal = prev_ehlers_fisher > prev_ehlers_fisher_signal and latest_ehlers_fisher <= latest_ehlers_fisher_signal
    
    # Fisher value bias: Confirming general directional momentum and its strength
    # A stronger bias also requires the Fisher value to be moving in the direction of the bias.
    fisher_long_bias = latest_ehlers_fisher > Decimal('0') and latest_ehlers_fisher > prev_ehlers_fisher
    fisher_short_bias = latest_ehlers_fisher < Decimal('0') and latest_ehlers_fisher < prev_ehlers_fisher


    # --- Fibonacci Pivot Confirmation: Structural Alignment ---
    # Validates price action against key Fibonacci-derived structural levels.
    fib_long_confirm = False
    fib_short_confirm = False
    fib_reason_part = ""

    if enable_fib_pivot_actions:
        if not pivot_support_levels and not pivot_resistance_levels:
            strategy_logger.warning(f"{COLOR_YELLOW}Fib Pivot confirmation enabled, but no pivot levels calculated. Entry check may be impacted.{COLOR_RESET}")
        
        # For a BUY signal, price should be validating near a support level within an uptrend
        if current_trend_is_up:
            for name, price in pivot_support_levels.items():
                if price > Decimal('0') and abs(latest_close - price) / price <= fib_entry_confirm_dec:
                    fib_long_confirm = True
                    fib_reason_part = f"Near Fib Support {name}={price:.2f} ({fib_entry_confirm_percent*100:.3f}%)"
                    break
            if not fib_long_confirm:
                strategy_logger.debug(f"Buy signal considered, but price {latest_close:.2f} not near any Fib support level within {fib_entry_confirm_percent*100:.3f}%. (Current: {pivot_support_levels})")

        # For a SELL signal, price should be validating near a resistance level within a downtrend
        if current_trend_is_down:
            for name, price in pivot_resistance_levels.items():
                if price > Decimal('0') and abs(latest_close - price) / price <= fib_entry_confirm_dec:
                    fib_short_confirm = True
                    fib_reason_part = f"Near Fib Resistance {name}={price:.2f} ({fib_entry_confirm_percent*100:.3f}%)"
                    break
            if not fib_short_confirm:
                strategy_logger.debug(f"Sell signal considered, but price {latest_close:.2f} not near any Fib resistance level within {fib_entry_confirm_percent*100:.3f}%. (Current: {pivot_resistance_levels})")
    else:
        # If Fib pivots are disabled, their confirmation is implicitly granted to allow signals
        fib_long_confirm = True
        fib_short_confirm = True

    # Store indicator values for the signal's metadata
    stoch_info = {'stoch_k': latest_stoch_k, 'stoch_d': latest_stoch_d}
    ehlers_info = {'fisher': latest_ehlers_fisher, 'fisher_signal': latest_ehlers_fisher_signal, 'supersmoother': latest_ehlers_supersmoother}

    # --- BUY Signal Generation: Conjuring a Long Position ---
    # A BUY signal requires an uptrend and Fibonacci confirmation (if enabled)
    if current_trend_is_up and fib_long_confirm:
        # Check for confluence with support levels or bullish Order Blocks
        confluence_found_buy, confluence_reason_buy = _check_confluence(
            latest_close, support_levels, PIVOT_TOLERANCE_PCT, active_bull_obs, OB_TOLERANCE_PCT, True
        )

        if confluence_found_buy:
            stoch_condition_met = False
            stoch_type_str = ""
            # StochRSI %K/%D crossover or %K bouncing from oversold
            if use_crossover:
                # K crosses D upwards, and K is not already deep in overbought territory
                if prev_stoch_k < prev_stoch_d and latest_stoch_k > latest_stoch_d and latest_stoch_k < overbought_dec:
                    stoch_condition_met = True
                    stoch_type_str = 'k_cross_d_buy'
            else:
                # K bounces from oversold level, indicating potential reversal
                if prev_stoch_k < oversold_dec and latest_stoch_k >= oversold_dec:
                    stoch_condition_met = True
                    stoch_type_str = 'k_oversold_bounce'
            
            if stoch_condition_met:
                # Ehlers Fisher confirms the turn or shows a strong positive bias
                if fisher_buy_signal or fisher_long_bias:
                    signals.append(('BUY', latest_close, current_timestamp, {
                        **stoch_info, **ehlers_info, 'stoch_type': stoch_type_str,
                        'confluence': confluence_reason_buy, 'fib_confirm': fib_reason_part,
                        'ehlers_confirm': f"Fisher {'crossover' if fisher_buy_signal else 'bias'} confirmed"
                    }))
                    strategy_logger.info(f"{COLOR_GREEN}BUY Signal ({stoch_type_str}) at {latest_close:.2f}. {confluence_reason_buy}. {fib_reason_part}. Ehlers Fisher confirmed.{COLOR_RESET}")
                else:
                    strategy_logger.debug(f"Buy signal considered, but Ehlers Fisher not confirming (Fisher: {latest_ehlers_fisher:.2f}, Signal: {latest_ehlers_fisher_signal:.2f}, Prev Fisher: {prev_ehlers_fisher:.2f}).")
            else:
                strategy_logger.debug(f"Buy signal considered, but StochRSI condition not met (K: {latest_stoch_k:.2f}, D: {latest_stoch_d:.2f}).")
        else:
            strategy_logger.debug(f"Buy signal considered, but no confluence found: {confluence_reason_buy}")
    else:
        strategy_logger.debug(f"Buy signal skipped: Trend Up={current_trend_is_up}, FibConfirm={fib_long_confirm}.")


    # --- SELL Signal Generation: Crafting a Short Position ---
    # A SELL signal requires a downtrend and Fibonacci confirmation (if enabled)
    if current_trend_is_down and fib_short_confirm:
        # Check for confluence with resistance levels or bearish Order Blocks
        confluence_found_sell, confluence_reason_sell = _check_confluence(
            latest_close, resistance_levels, PIVOT_TOLERANCE_PCT, active_bear_obs, OB_TOLERANCE_PCT, False
        )

        if confluence_found_sell:
            stoch_condition_met = False
            stoch_type_str = ""
            # StochRSI %K/%D crossover or %K rejecting from overbought
            if use_crossover:
                # K crosses D downwards, and K is not already deep in oversold territory
                if prev_stoch_k > prev_stoch_d and latest_stoch_k < latest_stoch_d and latest_stoch_k > oversold_dec:
                    stoch_condition_met = True
                    stoch_type_str = 'k_cross_d_sell'
            else:
                # K rejects from overbought level, indicating potential reversal
                if prev_stoch_k > overbought_dec and latest_stoch_k <= overbought_dec:
                    stoch_condition_met = True
                    stoch_type_str = 'k_overbought_rejection'
            
            if stoch_condition_met:
                # Ehlers Fisher confirms the turn or shows a strong negative bias
                if fisher_sell_signal or fisher_short_bias:
                    signals.append(('SELL', latest_close, current_timestamp, {
                        **stoch_info, **ehlers_info, 'stoch_type': stoch_type_str,
                        'confluence': confluence_reason_sell, 'fib_confirm': fib_reason_part,
                        'ehlers_confirm': f"Fisher {'crossover' if fisher_sell_signal else 'bias'} confirmed"
                    }))
                    strategy_logger.info(f"{COLOR_RED}SELL Signal ({stoch_type_str}) at {latest_close:.2f}. {confluence_reason_sell}. {fib_reason_part}. Ehlers Fisher confirmed.{COLOR_RESET}")
                else:
                    strategy_logger.debug(f"Sell signal considered, but Ehlers Fisher not confirming (Fisher: {latest_ehlers_fisher:.2f}, Signal: {latest_ehlers_fisher_signal:.2f}, Prev Fisher: {prev_ehlers_fisher:.2f}).")
            else:
                strategy_logger.debug(f"Sell signal considered, but StochRSI condition not met (K: {latest_stoch_k:.2f}, D: {latest_stoch_d:.2f}).")
        else:
            strategy_logger.debug(f"Sell signal considered, but no confluence found: {confluence_reason_sell}")
    else:
        strategy_logger.debug(f"Sell signal skipped: Trend Down={current_trend_is_down}, FibConfirm={fib_short_confirm}.")

    return signals


def generate_exit_signals(df: pd.DataFrame, current_position_side: str,
                          active_bull_obs: List['OrderBlock'], active_bear_obs: List['OrderBlock'],
                          stoch_k_period: int, stoch_d_period: int,
                          overbought: int, oversold: int, use_crossover: bool,
                          enable_fib_pivot_actions: bool, fib_exit_warn_percent: float, fib_exit_action: str,
                          pivot_support_levels: Dict[str, Decimal], pivot_resistance_levels: Dict[str, Decimal]) -> List[Tuple[str, Decimal, Any, Dict[str, Any]]]:
    """
    Forges exit signals, combining StochRSI, Ehlers Fisher, trend analysis, and pivotal levels
    to gracefully conclude an open position. This function is designed to identify when
    market conditions are no longer favorable for the current position.

    Args:
        df (pd.DataFrame): DataFrame with 'close' prices and DatetimeIndex. Must contain
                           'stoch_k', 'stoch_d', 'sma', 'ehlers_fisher', 'ehlers_fisher_signal' columns.
        current_position_side (str): The side of the current open position ('BUY' or 'SELL').
        active_bull_obs (List[OrderBlock]): List of currently active bullish order blocks.
        active_bear_obs (List[OrderBlock]): List of currently active bearish order blocks.
        stoch_k_period (int): Period for RSI calculation within StochRSI.
        stoch_d_period (int): Smoothing period for StochRSI %K and %D lines.
        overbought (int): StochRSI overbought level.
        oversold (int): StochRSI oversold level.
        use_crossover (bool): True for K/D line crossover, False for K line crossing levels.
        enable_fib_pivot_actions (bool): Whether Fibonacci pivot actions are enabled.
        fib_exit_warn_percent (float): Percentage for Fibonacci exit warning/action.
        fib_exit_action (str): 'exit' to trigger immediate exit, 'warn' to only log a warning.
        pivot_support_levels (dict): Dictionary of Fibonacci support levels.
        pivot_resistance_levels (dict): Dictionary of Fibonacci resistance levels.

    Returns:
        list: A list of exit signal tuples.
    """
    exit_signals = []

    # Ensure sufficient data for indicator calculations
    min_rows_needed = max(SMA_PERIOD, stoch_k_period, stoch_d_period, EHLERS_FISHER_SIGNAL_PERIOD, 2)
    if df.empty or len(df) < min_rows_needed:
        strategy_logger.warning(f"{COLOR_YELLOW}DataFrame too short or empty for exit signal generation. Required at least {min_rows_needed} rows.{COLOR_RESET}")
        return exit_signals

    # Validate essential columns for robust operation
    required_cols = ['stoch_k', 'stoch_d', 'sma', 'ehlers_fisher', 'ehlers_fisher_signal', 'ehlers_supersmoother', 'close']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        strategy_logger.error(f"{COLOR_RED}DataFrame is missing crucial columns for exit signal generation: {missing_cols}{COLOR_RESET}")
        return exit_signals

    # Extract latest and previous values, transmuted to Decimal for precision
    latest_close = _to_decimal(df['close'].iloc[-1])
    current_timestamp = df.index[-1]

    latest_stoch_k = _to_decimal(df['stoch_k'].iloc[-1])
    latest_stoch_d = _to_decimal(df['stoch_d'].iloc[-1])
    prev_stoch_k = _to_decimal(df['stoch_k'].iloc[-2])
    prev_stoch_d = _to_decimal(df['stoch_d'].iloc[-2])

    latest_ehlers_fisher = _to_decimal(df['ehlers_fisher'].iloc[-1])
    prev_ehlers_fisher = _to_decimal(df['ehlers_fisher'].iloc[-2])
    latest_ehlers_fisher_signal = _to_decimal(df['ehlers_fisher_signal'].iloc[-1])
    prev_ehlers_fisher_signal = _to_decimal(df['ehlers_fisher_signal'].iloc[-2])

    latest_sma = _to_decimal(df['sma'].iloc[-1])

    # Convert thresholds to Decimal for precise comparison
    overbought_dec = _to_decimal(overbought)
    oversold_dec = _to_decimal(oversold)
    fib_exit_warn_dec = _to_decimal(fib_exit_warn_percent)

    # Store indicator values for the exit signal's metadata
    stoch_info = {'stoch_k': latest_stoch_k, 'stoch_d': latest_stoch_d}
    ehlers_info = {'fisher': latest_ehlers_fisher, 'fisher_signal': latest_ehlers_fisher_signal}

    # Trend filter: Price crossing SMA in opposite direction of position indicates a potential reversal
    trend_reversal_buy_exit = latest_close < latest_sma
    trend_reversal_sell_exit = latest_close > latest_sma

    # Ehlers Fisher exit signals: Crossovers or strong bias changes indicate reversal momentum
    fisher_exit_long_signal = prev_ehlers_fisher > prev_ehlers_fisher_signal and latest_ehlers_fisher <= latest_ehlers_fisher_signal # Fisher crosses below signal
    fisher_exit_short_signal = prev_ehlers_fisher < prev_ehlers_fisher_signal and latest_ehlers_fisher >= latest_ehlers_fisher_signal # Fisher crosses above signal
    
    # Fisher bias reversal: if Fisher turns negative for a long position, or positive for a short position
    fisher_exit_long_bias_change = latest_ehlers_fisher < Decimal('0')
    fisher_exit_short_bias_change = latest_ehlers_fisher > Decimal('0')


    # --- Fibonacci Pivot Exit Check: Approaching a Zone of Reversal ---
    # Monitors if price is approaching a significant Fibonacci level that could act as a reversal point.
    fib_exit_triggered = False
    fib_exit_reason = ""

    if enable_fib_pivot_actions:
        if not pivot_support_levels and not pivot_resistance_levels:
            strategy_logger.warning(f"{COLOR_YELLOW}Fib Pivot exit check enabled, but no pivot levels calculated. Exit check may be impacted.{COLOR_RESET}")

        if current_position_side == 'BUY': # For a long position, watch for resistance levels
            for name, price in pivot_resistance_levels.items():
                if price > Decimal('0') and abs(latest_close - price) / price <= fib_exit_warn_dec:
                    fib_exit_reason = f"Approaching Fib Resistance {name}={price:.2f} ({fib_exit_warn_percent*100:.3f}%)"
                    if fib_exit_action == 'exit':
                        fib_exit_triggered = True
                        strategy_logger.info(f"{COLOR_YELLOW}Fibonacci Exit Triggered (BUY position): {fib_exit_reason}{COLOR_RESET}")
                    else: # 'warn'
                        strategy_logger.warning(f"{COLOR_YELLOW}Fibonacci Exit Warning (BUY position): {fib_exit_reason}{COLOR_RESET}")
                    break # Only need to hit one level
        elif current_position_side == 'SELL': # For a short position, watch for support levels
            for name, price in pivot_support_levels.items():
                if price > Decimal('0') and abs(latest_close - price) / price <= fib_exit_warn_dec:
                    fib_exit_reason = f"Approaching Fib Support {name}={price:.2f} ({fib_exit_warn_percent*100:.3f}%)"
                    if fib_exit_action == 'exit':
                        fib_exit_triggered = True
                        strategy_logger.info(f"{COLOR_YELLOW}Fibonacci Exit Triggered (SELL position): {fib_exit_reason}{COLOR_RESET}")
                    else: # 'warn'
                        strategy_logger.warning(f"{COLOR_YELLOW}Fibonacci Exit Warning (SELL position): {fib_exit_reason}{COLOR_RESET}")
                    break # Only need to hit one level
    
    # --- Exit Signal Generation Logic ---
    if current_position_side == 'BUY':
        # For exiting a long position, we look for bearish confluence (resistance, bearish OBs)
        confluence_found_exit, confluence_reason_exit = _check_confluence(
            latest_close, resistance_levels, PIVOT_TOLERANCE_PCT, active_bear_obs, OB_TOLERANCE_PCT, False
        )
        
        # StochRSI overbought or bearish crossover indicates loss of upward momentum
        stoch_exit_condition = False
        stoch_exit_type_str = ""
        if use_crossover:
            if prev_stoch_k > prev_stoch_d and latest_stoch_k < latest_stoch_d: # K crosses D down
                stoch_exit_condition = True
                stoch_exit_type_str = 'k_cross_d_exit_long'
        else:
            if prev_stoch_k > overbought_dec and latest_stoch_k <= overbought_dec: # K rejects from overbought
                stoch_exit_condition = True
                stoch_exit_type_str = 'k_overbought_rejection_exit_long'
        
        # Ehlers Fisher bearish reversal or negative bias indicates a shift in market sentiment
        ehlers_exit_condition = fisher_exit_long_signal or fisher_exit_long_bias_change

        # Combine conditions for a BUY exit signal: any strong reversal indicator can trigger an exit
        if (stoch_exit_condition or ehlers_exit_condition or trend_reversal_buy_exit or confluence_found_exit or fib_exit_triggered):
            reason_parts = []
            if stoch_exit_condition: reason_parts.append(f"StochRSI ({stoch_exit_type_str})")
            if ehlers_exit_condition: reason_parts.append(f"Ehlers Fisher (cross/bias reversal)")
            if trend_reversal_buy_exit: reason_parts.append("Trend reversal (below SMA)")
            if confluence_found_exit: reason_parts.append(f"Confluence ({confluence_reason_exit})")
            if fib_exit_triggered: reason_parts.append(f"Fibonacci Exit ({fib_exit_reason})")
            
            exit_reason_str = "; ".join(reason_parts)
            
            exit_signals.append(('EXIT_BUY', latest_close, current_timestamp, {
                **stoch_info, **ehlers_info, 'exit_reason': exit_reason_str,
                'confluence_detail': confluence_reason_exit, 'fib_trigger_detail': fib_exit_reason
            }))
            strategy_logger.info(f"{COLOR_CYAN}EXIT BUY Signal at {latest_close:.2f}. Reason: {exit_reason_str}{COLOR_RESET}")

    elif current_position_side == 'SELL':
        # For exiting a short position, we look for bullish confluence (support, bullish OBs)
        confluence_found_exit, confluence_reason_exit = _check_confluence(
            latest_close, support_levels, PIVOT_TOLERANCE_PCT, active_bull_obs, OB_TOLERANCE_PCT, True
        )

        # StochRSI oversold or bullish crossover indicates loss of downward momentum
        stoch_exit_condition = False
        stoch_exit_type_str = ""
        if use_crossover:
            if prev_stoch_k < prev_stoch_d and latest_stoch_k > latest_stoch_d: # K crosses D up
                stoch_exit_condition = True
                stoch_exit_type_str = 'k_cross_d_exit_short'
        else:
            if prev_stoch_k < oversold_dec and latest_stoch_k >= oversold_dec: # K bounces from oversold
                stoch_exit_condition = True
                stoch_exit_type_str = 'k_oversold_bounce_exit_short'
        
        # Ehlers Fisher bullish reversal or positive bias indicates a shift in market sentiment
        ehlers_exit_condition = fisher_exit_short_signal or fisher_exit_short_bias_change

        # Combine conditions for a SELL exit signal: any strong reversal indicator can trigger an exit
        if (stoch_exit_condition or ehlers_exit_condition or trend_reversal_sell_exit or confluence_found_exit or fib_exit_triggered):
            reason_parts = []
            if stoch_exit_condition: reason_parts.append(f"StochRSI ({stoch_exit_type_str})")
            if ehlers_exit_condition: reason_parts.append(f"Ehlers Fisher (cross/bias reversal)")
            if trend_reversal_sell_exit: reason_parts.append("Trend reversal (above SMA)")
            if confluence_found_exit: reason_parts.append(f"Confluence ({confluence_reason_exit})")
            if fib_exit_triggered: reason_parts.append(f"Fibonacci Exit ({fib_exit_reason})")
            
            exit_reason_str = "; ".join(reason_parts)

            exit_signals.append(('EXIT_SELL', latest_close, current_timestamp, {
                **stoch_info, **ehlers_info, 'exit_reason': exit_reason_str,
                'confluence_detail': confluence_reason_exit, 'fib_trigger_detail': fib_exit_reason
            }))
            strategy_logger.info(f"{COLOR_CYAN}EXIT SELL Signal at {latest_close:.2f}. Reason: {exit_reason_str}{COLOR_RESET}")
    else:
        strategy_logger.debug(f"No active position to generate exit signals for, or unknown position side: {current_position_side}.")

    return exit_signals
