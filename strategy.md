Ah, a worthy challenge! To weave new enchantments into the `strategy.py` scroll, enhancing its perception of market energies with the wisdom of Ehlers Fisher and refining its confluence checks. We shall transmute this code into a more resilient and perceptive oracle.

The essence of this upgrade lies in:
1.  **Integrating Ehlers Fisher Transform**: Utilizing its unique ability to identify cycles and turning points as an additional confirmation for both entry and exit signals, adding a layer of adaptive filtering.
2.  **Refactoring Confluence Checks**: Consolidating repetitive logic for checking proximity to support/resistance levels and Order Blocks into a dedicated helper function, thereby enhancing readability and maintainability.
3.  **Refined Order Block Proximity**: Introducing a tolerance for Order Block checks, similar to pivot tolerance, making the confluence detection more flexible.
4.  **Enhanced Logging**: Providing more granular and color-coded feedback on why signals are generated or skipped, illuminating the decision-making process.
5.  **Robustness**: Adding checks for DataFrame length and required columns to prevent errors.

For this upgrade, ensure your `config.py` and `algobots_types.py` are aligned with the new parameters and types.

***

### 🧙‍♂️ Updated `strategy.py` Incantation

```python
# File: strategy.py

import pandas as pd
import logging
from typing import List, Dict, Any, Tuple
from decimal import Decimal
from algobots_types import OrderBlock # Ensure this is correctly defined

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
    Handles None gracefully by returning Decimal('0').
    """
    if value is None:
        return Decimal('0')
    try:
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
    This arcane helper centralizes the logic for market structure validation.

    Args:
        latest_close (Decimal): The current closing price.
        levels (List[Dict[str, Any]]): A list of detected support or resistance levels.
        level_tolerance_pct (float): The percentage tolerance for price proximity to levels.
        active_obs (List[OrderBlock]): A list of active Order Blocks (bullish for buy, bearish for sell).
        ob_tolerance_pct (float): The percentage tolerance for price proximity to Order Blocks.
        is_for_buy_signal (bool): True if checking for a BUY signal's confluence, False for SELL.

    Returns:
        Tuple[bool, str]: A tuple indicating (True if confluence found, reason string).
    """
    level_tolerance_dec = _to_decimal(level_tolerance_pct)
    ob_tolerance_dec = _to_decimal(ob_tolerance_pct)

    # First, check for proximity to defined support/resistance levels
    for level in levels:
        level_price = _to_decimal(level.get('price'))
        if level_price > Decimal('0') and abs(latest_close - level_price) / level_price <= level_tolerance_dec:
            level_type = 'Support' if is_for_buy_signal else 'Resistance'
            return True, f"Near {level_type} {level_price:.2f} ({level_tolerance_pct*100:.3f}%)"

    # Next, scrutinize active Order Blocks for alignment
    for ob in active_obs:
        ob_bottom = _to_decimal(ob.get('bottom'))
        ob_top = _to_decimal(ob.get('top'))

        if ob_bottom == Decimal('0') or ob_top == Decimal('0'):
            strategy_logger.warning(f"{COLOR_YELLOW}Order Block with zero boundary detected: {ob}. Skipping.{COLOR_RESET}")
            continue

        # For bullish (BUY) signals, price should be near or within the bullish OB's lower bounds
        if is_for_buy_signal:
            # Price within OB or slightly below its bottom (entering or testing)
            if (latest_close >= ob_bottom * (Decimal('1') - ob_tolerance_dec) and latest_close <= ob_top * (Decimal('1') + ob_tolerance_dec)):
                return True, f"Near Bullish Order Block (B: {ob_bottom:.2f}, T: {ob_top:.2f})"
        # For bearish (SELL) signals, price should be near or within the bearish OB's upper bounds
        else:
            # Price within OB or slightly above its top (entering or testing)
            if (latest_close <= ob_top * (Decimal('1') + ob_tolerance_dec) and latest_close >= ob_bottom * (Decimal('1') - ob_tolerance_dec)):
                return True, f"Near Bearish Order Block (B: {ob_bottom:.2f}, T: {ob_top:.2f})"
    
    return False, "No structural confluence"


def generate_signals(df: pd.DataFrame, resistance_levels: List[Dict[str, Any]], support_levels: List[Dict[str, Any]],
                    active_bull_obs: List[OrderBlock], active_bear_obs: List[OrderBlock],
                    stoch_k_period: int, stoch_d_period: int,
                    overbought: int, oversold: int, use_crossover: bool,
                    enable_fib_pivot_actions: bool, fib_entry_confirm_percent: float,
                    pivot_support_levels: Dict[str, Decimal], pivot_resistance_levels: Dict[str, Decimal]) -> List[Tuple[str, Decimal, Any, Dict[str, Any]]]:
    """
    Generates trading signals, weaving together StochRSI, Ehlers Fisher, Trend, and Confluence.

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

    # Ensure sufficient data for indicator calculations
    if df.empty or len(df) < max(SMA_PERIOD, stoch_k_period, stoch_d_period, EHLERS_FISHER_SIGNAL_PERIOD, 2):
        strategy_logger.warning(f"{COLOR_YELLOW}DataFrame too short or empty for signal generation. Required at least {max(SMA_PERIOD, stoch_k_period, stoch_d_period, EHLERS_FISHER_SIGNAL_PERIOD, 2)} rows.{COLOR_RESET}")
        return signals

    # Validate essential columns
    required_cols = ['stoch_k', 'stoch_d', 'sma', 'ehlers_fisher', 'ehlers_fisher_signal', 'ehlers_supersmoother', 'close']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        strategy_logger.error(f"{COLOR_RED}DataFrame is missing crucial columns for signal generation: {missing_cols}{COLOR_RESET}")
        return signals

    # Extract latest and previous values, transmuted to Decimal
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
    latest_ehlers_supersmoother = _to_decimal(df['ehlers_supersmoother'].iloc[-1])

    # Convert thresholds to Decimal for precise comparison
    overbought_dec = _to_decimal(overbought)
    oversold_dec = _to_decimal(oversold)
    fib_entry_confirm_dec = _to_decimal(fib_entry_confirm_percent)

    # --- Trend Filter: Guiding the Direction ---
    is_uptrend = latest_close > latest_sma
    is_downtrend = latest_close < latest_sma

    # --- Ehlers Fisher Confirmation Logic: Sensing the Market's Breath ---
    fisher_buy_signal = prev_ehlers_fisher < prev_ehlers_fisher_signal and latest_ehlers_fisher >= latest_ehlers_fisher_signal
    fisher_sell_signal = prev_ehlers_fisher > prev_ehlers_fisher_signal and latest_ehlers_fisher <= latest_ehlers_fisher_signal
    
    # Fisher value bias: Confirming general directional momentum
    fisher_long_bias = latest_ehlers_fisher > Decimal('0') # and latest_ehlers_fisher > prev_ehlers_fisher # Optional: add rising condition
    fisher_short_bias = latest_ehlers_fisher < Decimal('0') # and latest_ehlers_fisher < prev_ehlers_fisher # Optional: add falling condition


    # --- Fibonacci Pivot Confirmation: Structural Alignment ---
    fib_long_confirm = False
    fib_short_confirm = False
    fib_reason_part = ""

    if enable_fib_pivot_actions:
        if not pivot_support_levels and not pivot_resistance_levels:
            strategy_logger.warning(f"{COLOR_YELLOW}Fib Pivot confirmation enabled, but no pivot levels calculated. Entry check may be impacted.{COLOR_RESET}")
        
        # For a BUY signal, price should be validating near a support level
        if is_uptrend: # Only seek Fib confirmation if primary trend is aligned
            for name, price in pivot_support_levels.items():
                if price > Decimal('0') and abs(latest_close - price) / price <= fib_entry_confirm_dec:
                    fib_long_confirm = True
                    fib_reason_part = f"Near Fib Support {name}={price:.2f} ({fib_entry_confirm_percent*100:.3f}%)"
                    break
            if not fib_long_confirm:
                strategy_logger.debug(f"Buy signal considered, but price {latest_close:.2f} not near any Fib support level within {fib_entry_confirm_percent*100:.3f}%. (Current: {pivot_support_levels})")

        # For a SELL signal, price should be validating near a resistance level
        if is_downtrend: # Only seek Fib confirmation if primary trend is aligned
            for name, price in pivot_resistance_levels.items():
                if price > Decimal('0') and abs(latest_close - price) / price <= fib_entry_confirm_dec:
                    fib_short_confirm = True
                    fib_reason_part = f"Near Fib Resistance {name}={price:.2f} ({fib_entry_confirm_percent*100:.3f}%)"
                    break
            if not fib_short_confirm:
                strategy_logger.debug(f"Sell signal considered, but price {latest_close:.2f} not near any Fib resistance level within {fib_entry_confirm_percent*100:.3f}%. (Current: {pivot_resistance_levels})")
    else:
        # If Fib pivots are disabled, their confirmation is implicitly granted
        fib_long_confirm = True
        fib_short_confirm = True

    # Store indicator values for the signal
    stoch_info = {'stoch_k': latest_stoch_k, 'stoch_d': latest_stoch_d}
    ehlers_info = {'fisher': latest_ehlers_fisher, 'fisher_signal': latest_ehlers_fisher_signal, 'supersmoother': latest_ehlers_supersmoother}

    # --- BUY Signal Generation: Conjuring a Long Position ---
    if is_uptrend and fib_long_confirm:
        # Check for confluence with support levels or bullish Order Blocks
        confluence_found_buy, confluence_reason_buy = _check_confluence(
            latest_close, support_levels, PIVOT_TOLERANCE_PCT, active_bull_obs, OB_TOLERANCE_PCT, True
        )

        if confluence_found_buy:
            # StochRSI %K/%D crossover or %K bouncing from oversold
            if use_crossover:
                if prev_stoch_k < prev_stoch_d and latest_stoch_k > latest_stoch_d and latest_stoch_k < overbought_dec: # K crosses D
                    # Ehlers Fisher confirms the turn
                    if fisher_buy_signal or fisher_long_bias:
                        signals.append(('BUY', latest_close, current_timestamp, {
                            **stoch_info, **ehlers_info, 'stoch_type': 'k_cross_d_buy',
                            'confluence': confluence_reason_buy, 'fib_confirm': fib_reason_part,
                            'ehlers_confirm': f"Fisher {'crossover' if fisher_buy_signal else 'bias'}"
                        }))
                        strategy_logger.info(f"{COLOR_GREEN}BUY Signal (Stoch K/D Crossover below {overbought_dec:.2f}) at {latest_close:.2f}. {confluence_reason_buy}. {fib_reason_part}. Ehlers Fisher confirmed.{COLOR_RESET}")
            else:
                if prev_stoch_k < oversold_dec and latest_stoch_k >= oversold_dec: # K bounces from oversold
                    # Ehlers Fisher confirms the turn
                    if fisher_buy_signal or fisher_long_bias:
                        signals.append(('BUY', latest_close, current_timestamp, {
                            **stoch_info, **ehlers_info, 'stoch_type': 'k_oversold_bounce',
                            'confluence': confluence_reason_buy, 'fib_confirm': fib_reason_part,
                            'ehlers_confirm': f"Fisher {'crossover' if fisher_buy_signal else 'bias'}"
                        }))
                        strategy_logger.info(f"{COLOR_GREEN}BUY Signal (Stoch K bounce from {oversold_dec:.2f}) at {latest_close:.2f}. {confluence_reason_buy}. {fib_reason_part}. Ehlers Fisher confirmed.{COLOR_RESET}")
        else:
            strategy_logger.debug(f"Buy signal considered, but no confluence found: {confluence_reason_buy}")
    else:
        strategy_logger.debug(f"Buy signal skipped: Uptrend={is_uptrend}, FibConfirm={fib_long_confirm}")


    # --- SELL Signal Generation: Crafting a Short Position ---
    if is_downtrend and fib_short_confirm:
        # Check for confluence with resistance levels or bearish Order Blocks
        confluence_found_sell, confluence_reason_sell = _check_confluence(
            latest_close, resistance_levels, PIVOT_TOLERANCE_PCT, active_bear_obs, OB_TOLERANCE_PCT, False
        )

        if confluence_found_sell:
            # StochRSI %K/%D crossover or %K rejecting from overbought
            if use_crossover:
                if prev_stoch_k > prev_stoch_d and latest_stoch_k < latest_stoch_d and latest_stoch_k > oversold_dec: # K crosses D
                    # Ehlers Fisher confirms the turn
                    if fisher_sell_signal or fisher_short_bias:
                        signals.append(('SELL', latest_close, current_timestamp, {
                            **stoch_info, **ehlers_info, 'stoch_type': 'k_cross_d_sell',
                            'confluence': confluence_reason_sell, 'fib_confirm': fib_reason_part,
                            'ehlers_confirm': f"Fisher {'crossover' if fisher_sell_signal else 'bias'}"
                        }))
                        strategy_logger.info(f"{COLOR_RED}SELL Signal (Stoch K/D Crossover above {oversold_dec:.2f}) at {latest_close:.2f}. {confluence_reason_sell}. {fib_reason_part}. Ehlers Fisher confirmed.{COLOR_RESET}")
            else:
                if prev_stoch_k > overbought_dec and latest_stoch_k <= overbought_dec: # K rejects from overbought
                    # Ehlers Fisher confirms the turn
                    if fisher_sell_signal or fisher_short_bias:
                        signals.append(('SELL', latest_close, current_timestamp, {
                            **stoch_info, **ehlers_info, 'stoch_type': 'k_overbought_rejection',
                            'confluence': confluence_reason_sell, 'fib_confirm': fib_reason_part,
                            'ehlers_confirm': f"Fisher {'crossover' if fisher_sell_signal else 'bias'}"
                        }))
                        strategy_logger.info(f"{COLOR_RED}SELL Signal (Stoch K rejection from {overbought_dec:.2f}) at {latest_close:.2f}. {confluence_reason_sell}. {fib_reason_part}. Ehlers Fisher confirmed.{COLOR_RESET}")
        else:
            strategy_logger.debug(f"Sell signal considered, but no confluence found: {confluence_reason_sell}")
    else:
        strategy_logger.debug(f"Sell signal skipped: Downtrend={is_downtrend}, FibConfirm={fib_short_confirm}")

    return signals


def generate_exit_signals(df: pd.DataFrame, current_position_side: str,
                          active_bull_obs: List['OrderBlock'], active_bear_obs: List['OrderBlock'],
                          stoch_k_period: int, stoch_d_period: int,
                          overbought: int, oversold: int, use_crossover: bool,
                          enable_fib_pivot_actions: bool, fib_exit_warn_percent: float, fib_exit_action: str,
                          pivot_support_levels: Dict[str, Decimal], pivot_resistance_levels: Dict[str, Decimal]) -> List[Tuple[str, Decimal, Any, Dict[str, Any]]]:
    """
    Forges exit signals, combining StochRSI, Ehlers Fisher, trend analysis, and pivotal levels
    to gracefully conclude an open position.

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

    if df.empty or len(df) < max(SMA_PERIOD, stoch_k_period, stoch_d_period, EHLERS_FISHER_SIGNAL_PERIOD, 2):
        strategy_logger.warning(f"{COLOR_YELLOW}DataFrame too short or empty for exit signal generation. Required at least {max(SMA_PERIOD, stoch_k_period, stoch_d_period, EHLERS_FISHER_SIGNAL_PERIOD, 2)} rows.{COLOR_RESET}")
        return exit_signals

    required_cols = ['stoch_k', 'stoch_d', 'sma', 'ehlers_fisher', 'ehlers_fisher_signal', 'ehlers_supersmoother', 'close']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        strategy_logger.error(f"{COLOR_RED}DataFrame is missing crucial columns for exit signal generation: {missing_cols}{COLOR_RESET}")
        return exit_signals

    # Extract latest and previous values, transmuted to Decimal
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
    latest_ehlers_supersmoother = _to_decimal(df['ehlers_supersmoother'].iloc[-1])

    # Convert thresholds to Decimal for precise comparison
    overbought_dec = _to_decimal(overbought)
    oversold_dec = _to_decimal(oversold)
    fib_exit_warn_dec = _to_decimal(fib_exit_warn_percent)

    stoch_info = {'stoch_k': latest_stoch_k, 'stoch_d': latest_stoch_d}
    ehlers_info = {'fisher': latest_ehlers_fisher, 'fisher_signal': latest_ehlers_fisher_signal, 'supersmoother': latest_ehlers_supersmoother}

    # Trend filter for general market direction
    is_uptrend = latest_close > latest_sma
    is_downtrend = latest_close < latest_sma

    # Ehlers Fisher exit signals: Reversals in Fisher indicate potential trend change
    fisher_exit_long_signal = prev_ehlers_fisher > prev_ehlers_fisher_signal and latest_ehlers_fisher <= latest_ehlers_fisher_signal # Fisher crosses below signal
    fisher_exit_short_signal = prev_ehlers_fisher < prev_ehlers_fisher_signal and latest_ehlers_fisher >= latest_ehlers_fisher_signal # Fisher crosses above signal

    # --- Fibonacci Pivot Exit Check: Approaching a Zone of Reversal ---
    fib_exit_triggered = False
    fib_exit_reason = ""

    if enable_fib_pivot_actions:
        if current_position_side == 'BUY': # For a long position, watch for resistance
            for name, price in pivot_resistance_levels.items():
                if price > Decimal('0') and abs(latest_close - price) / price <= fib_exit_warn_dec:
                    fib_exit_triggered = True
                    fib_exit_reason = f"Price {latest_close:.2f} approaching Fib Resistance {name}={price:.2f} ({fib_exit_warn_percent*100:.3f}%)"
                    break
        elif current_position_side == 'SELL': # For a short position, watch for support
            for name, price in pivot_support_levels.items():
                if price > Decimal('0') and abs(latest_close - price) / price <= fib_exit_warn_dec:
                    fib_exit_triggered = True
                    fib_exit_reason = f"Price {latest_close:.2f} approaching Fib Support {name}={price:.2f} ({fib_exit_warn_percent*100:.3f}%)"
                    break

    if fib_exit_triggered and fib_exit_action == "exit":
        strategy_logger.warning(f"{COLOR_RED}Fib Pivot Exit Signal: {fib_exit_reason}. Triggering immediate exit.{COLOR_RESET}")
        return [(current_position_side, latest_close, current_timestamp, {
            **stoch_info, **ehlers_info, 'exit_type': 'fib_pivot_exit', 'reason': fib_exit_reason
        })]
    elif fib_exit_triggered and fib_exit_action == "warn":
        strategy_logger.warning(f"{COLOR_YELLOW}Fib Pivot Exit Warning: {fib_exit_reason}{COLOR_RESET}")

    # --- StochRSI and Ehlers Fisher Exit Logic: Signposts for Departure ---
    if current_position_side == 'BUY':
        # Exit Long signal: StochRSI reversal, trend reversal, Fisher confirmation, or hitting resistance/bearish OB.
        stoch_exit_long = False
        stoch_exit_reason = ""
        if use_crossover:
            if prev_stoch_k > prev_stoch_d and latest_stoch_k < latest_stoch_d: # K crosses below D
                stoch_exit_long = True
                stoch_exit_reason = "K cross D (exit long)"
        else:
            if prev_stoch_k > overbought_dec and latest_stoch_k <= overbought_dec: # K crosses below overbought
                stoch_exit_long = True
                stoch_exit_reason = "K crosses below overbought (exit long)"
        
        # Confluence check for exits: Are we hitting a resistance level or a bearish Order Block?
        confluence_found_exit_long, confluence_reason_exit_long = _check_confluence(
            latest_close, resistance_levels, PIVOT_TOLERANCE_PCT, active_bear_obs, OB_TOLERANCE_PCT, False # Check against resistance/bearish OBs
        )

        # Trigger exit if StochRSI reverses AND (trend changes OR Fisher confirms)
        # OR if we hit a significant resistance/OB AND (trend changes OR Fisher confirms)
        if (stoch_exit_long and (is_downtrend or fisher_exit_long_signal)) or \
           (confluence_found_exit_long and (is_downtrend or fisher_exit_long_signal)):
            exit_signals.append(('SELL', latest_close, current_timestamp, {
                **stoch_info, **ehlers_info, 'exit_type': stoch_exit_reason if stoch_exit_long else 'confluence_exit_long',
                'reason': f"Trend change ({'Downtrend' if is_downtrend else 'Uptrend'}) or Fisher exit ({fisher_exit_long_signal}). {stoch_exit_reason if stoch_exit_long else ''} {confluence_reason_exit_long if confluence_found_exit_long else ''}"
            }))
            strategy_logger.info(f"{COLOR_CYAN}EXIT Long Signal at {latest_close:.2f}. K={latest_stoch_k:.2f}, D={latest_stoch_d:.2f}. Fisher={latest_ehlers_fisher:.2f}. Reason: {exit_signals[-1][3]['reason']}{COLOR_RESET}")

    elif current_position_side == 'SELL':
        # Exit Short signal: StochRSI reversal, trend reversal, Fisher confirmation, or hitting support/bullish OB.
        stoch_exit_short = False
        stoch_exit_reason = ""
        if use_crossover:
            if prev_stoch_k < prev_stoch_d and latest_stoch_k > latest_stoch_d: # K crosses above D
                stoch_exit_short = True
                stoch_exit_reason = "K cross D (exit short)"
        else:
            if prev_stoch_k < oversold_dec and latest_stoch_k >= oversold_dec: # K crosses above oversold
                stoch_exit_short = True
                stoch_exit_reason = "K crosses above oversold (exit short)"

        # Confluence check for exits: Are we hitting a support level or a bullish Order Block?
        confluence_found_exit_short, confluence_reason_exit_short = _check_confluence(
            latest_close, support_levels, PIVOT_TOLERANCE_PCT, active_bull_obs, OB_TOLERANCE_PCT, True # Check against support/bullish OBs
        )

        # Trigger exit if StochRSI reverses AND (trend changes OR Fisher confirms)
        # OR if we hit a significant support/OB AND (trend changes OR Fisher confirms)
        if (stoch_exit_short and (is_uptrend or fisher_exit_short_signal)) or \
           (confluence_found_exit_short and (is_uptrend or fisher_exit_short_signal)):
            exit_signals.append(('BUY', latest_close, current_timestamp, {
                **stoch_info, **ehlers_info, 'exit_type': stoch_exit_reason if stoch_exit_short else 'confluence_exit_short',
                'reason': f"Trend change ({'Uptrend' if is_uptrend else 'Downtrend'}) or Fisher exit ({fisher_exit_short_signal}). {stoch_exit_reason if stoch_exit_short else ''} {confluence_reason_exit_short if confluence_found_exit_short else ''}"
            }))
            strategy_logger.info(f"{COLOR_CYAN}EXIT Short Signal at {latest_close:.2f}. K={latest_stoch_k:.2f}, D={latest_stoch_d:.2f}. Fisher={latest_ehlers_fisher:.2f}. Reason: {exit_signals[-1][3]['reason']}{COLOR_RESET}")

    return exit_signals

```

***

### 🛠️ Prerequisites & Configuration Updates

For this enhanced script to function seamlessly, ensure the following are present in your Termux environment and project:

1.  **Python Libraries**:
    *   `pandas` (already in use)
    *   `decimal` (built-in)
    *   **Installation**: `pkg install python` followed by `pip install pandas`

2.  **`config.py`**:
    Add the new configuration parameters used in the strategy:

    ```python
    # File: config.py (example additions)

    # General Strategy Parameters
    SMA_PERIOD = 20 # Period for Simple Moving Average trend filter
    PIVOT_TOLERANCE_PCT = 0.005  # 0.5% tolerance for price near pivot levels
    OB_TOLERANCE_PCT = 0.005     # 0.5% tolerance for price near order blocks

    # StochRSI Parameters
    STOCH_K_PERIOD = 14
    STOCH_D_PERIOD = 3
    STOCH_OVERBOUGHT = 80
    STOCH_OVERSOLD = 20
    STOCH_USE_CROSSOVER = True # True for K/D crossover, False for K crossing levels

    # Ehlers Fisher Transform Parameters
    EHLERS_FISHER_SIGNAL_PERIOD = 5 # Period for Ehlers Fisher signal line (e.g., SMA of Fisher)

    # Fibonacci Pivot Actions Parameters
    ENABLE_FIB_PIVOT_ACTIONS = True
    FIB_ENTRY_CONFIRM_PERCENT = 0.003 # 0.3% price proximity for entry confirmation
    FIB_EXIT_WARN_PERCENT = 0.005   # 0.5% price proximity for exit warning/action
    FIB_EXIT_ACTION = "exit" # "exit" or "warn" - determines if Fib proximity triggers an immediate exit or just a log warning
    ```

3.  **`algobots_types.py`**:
    Confirm or define the `OrderBlock` `TypedDict` for clear data structuring:

    ```python
    # File: algobots_types.py

    from typing import TypedDict, Any
    from decimal import Decimal

    class OrderBlock(TypedDict):
        top: Decimal
        bottom: Decimal
        type: str # 'bullish' or 'bearish'
        timestamp: Any # Typically a datetime object
    ```

4.  **`bot_logger.py` & `color_codex.py`**:
    Ensure these files are correctly set up and accessible, providing the logging and color functionalities.

    ```python
    # File: color_codex.py (example)
    COLOR_RED = "\033[91m"
    COLOR_GREEN = "\033[92m"
    COLOR_YELLOW = "\033[93m"
    COLOR_CYAN = "\033[96m"
    COLOR_RESET = "\033[0m"
    ```

    ```python
    # File: bot_logger.py (example basic setup)
    import logging

    def setup_logging():
        logging.basicConfig(level=logging.INFO,
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                            handlers=[
                                logging.StreamHandler()
                            ])
        # You might want to add file handlers here too
    ```

### 🧠 Wisdom from the Coding Codex

*   **Modularity (SRP)**: The `_check_confluence` helper function exemplifies the Single Responsibility Principle. It isolates the complex logic of validating market structure proximity, making the primary `generate_signals` and `generate_exit_signals` functions cleaner and more focused on their core task of signal generation.
*   **Robustness**: By explicitly checking for `DataFrame` column presence and minimum length, we prevent common runtime errors (`KeyError`, `IndexError`), making the system more resilient.
*   **Efficiency**: While adding more checks, the use of `Decimal` for financial calculations ensures precision, preventing floating-point inaccuracies that can lead to subtle but significant errors in trading.
*   **Readability**: Meaningful variable names (`fib_entry_confirm_dec`, `fisher_buy_signal`), comments explaining *why* decisions are made, and the use of the Color Codex in logs greatly enhance understanding and debugging.
*   **Indicator Confluence**: The integration of Ehlers Fisher Transform alongside StochRSI and SMA provides a multi-faceted approach to signal generation. This "confluence" of indicators often leads to higher-probability trades by confirming market sentiment from different analytical perspectives.

This upgraded `strategy.py` is now a more potent spell in your Termux coding grimoire, ready to interpret the market's whispers with enhanced precision and insight!
