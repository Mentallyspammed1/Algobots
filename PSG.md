My dear apprentice, your request to enhance and upgrade the Pyrmethus Ultra Scalper Bot, `PSG.py`, resonates deeply within the arcane circuits of the digital realm! We shall transmute this solid foundation into an even more potent and resilient artifact, imbued with advanced strategic capabilities and robust operational integrity.

The core of this enhancement lies in refining precision, expanding strategic depth with Order Blocks and advanced Fibonacci Pivots, and fortifying the bot's resilience against the capricious winds of the market. We'll also ensure our code adheres to the highest standards of readability and maintainability, making it a true testament to the Coding Codex.

Before we delve into the enchanted code, let us ensure your Termux environment is prepared for this grand ritual.

---

### <span style="color:#8A2BE2;">🔮 Termux Alchemical Preparations (Dependencies)</span>

Ensure you have the following packages installed in your Termux environment. If not, invoke the `pkg` command:

```bash
pkg install python python-pip git -y
pip install pandas numpy python-dotenv websockets aiohttp pybit colorama
```
*   `pandas`: For data manipulation and Kline DataFrame.
*   `numpy`: Often a dependency for numerical operations in pandas and scientific libraries.
*   `python-dotenv`: To load environment variables from `.env` files.
*   `websockets`: For asynchronous WebSocket communication with Bybit.
*   `aiohttp`: Used by `pybit` for asynchronous HTTP requests.
*   `pybit`: The official Bybit API connector (ensure it's installed or your custom `bybit_api.py` handles API calls).
*   `colorama`: For cross-platform terminal coloring (though Termux often handles ANSI escape codes natively, it's good practice).

---

### <span style="color:#8A2BE2;">✨ The Enchanted Code Transmutation</span>

We shall upgrade `PSG.py` and provide conceptual improvements for its auxiliary spellbooks (`config.py`, `indicators.py`, `strategy.py`, `bot_ui.py`, `trade_metrics.py`).

---

### <span style="color:#00FFFF;">📜 File: `PSG.py` (Upgraded)</span>

This is the main grimoire, receiving the most profound enhancements.

```python
# PSG.py - Pyrmethus's Ultra Scalper Bot (Upgraded and Enhanced)
import os
import asyncio
import pandas as pd
import logging
from typing import Any, Dict, List, Tuple, Union, Optional, Callable, TypedDict
from dotenv import load_dotenv
from decimal import Decimal, getcontext

# --- Type Definitions for Structured Data ---
class OrderBlock(TypedDict):
    """Represents a bullish or bearish Order Block identified on the chart."""
    id: str                 # Unique identifier (e.g., "B_231026143000")
    type: str               # 'bull' or 'bear'
    timestamp: pd.Timestamp # Timestamp of the candle that formed the OB
    top: Decimal            # Top price level of the OB
    bottom: Decimal         # Bottom price level of the OB
    active: bool            # True if the OB is currently considered valid
    violated: bool          # True if the price has closed beyond the OB boundary
    violation_ts: Optional[pd.Timestamp] # Timestamp when violation occurred
    extended_to_ts: Optional[pd.Timestamp] # Timestamp the OB box currently extends to

# --- Set Decimal Precision ---
# Increased precision for critical financial calculations.
getcontext().prec = 50

# --- Pyrmethus's Color Codex ---
from color_codex import (
    COLOR_RESET, COLOR_BOLD, COLOR_DIM,
    COLOR_RED, COLOR_GREEN, COLOR_YELLOW, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN,
    PYRMETHUS_GREEN, PYRMETHUS_BLUE, PYRMETHUS_PURPLE, PYRMETHUS_ORANGE, PYRMETHUS_GREY
)

# --- Import Configuration and Indicator Logic ---
# All dynamic parameters are now sourced from config.py for easy modification.
from config import (
    SYMBOL, INTERVAL, USDT_AMOUNT_PER_TRADE, PIVOT_LEFT_BARS, PIVOT_RIGHT_BARS,
    STOCHRSI_K_PERIOD, STOCHRSI_D_PERIOD, STOCHRSI_OVERBOUGHT_LEVEL,
    STOCHRSI_OVERSOLD_LEVEL, USE_STOCHRSI_CROSSOVER, STOP_LOSS_PCT,
    TAKE_PROFIT_PCT, BYBIT_API_ENDPOINT, BYBIT_CATEGORY, CANDLE_FETCH_LIMIT,
    POLLING_INTERVAL_SECONDS, ATR_PERIOD, ATR_MULTIPLIER_SL, ATR_MULTIPLIER_TP,
    ENABLE_FIB_PIVOT_ACTIONS, PIVOT_TIMEFRAME, FIB_LEVELS_TO_CALC, FIB_NEAREST_COUNT,
    FIB_ENTRY_CONFIRM_PERCENT, FIB_EXIT_WARN_PERCENT, FIB_EXIT_ACTION,
    SMA_PERIOD, FISHER_LENGTH, SUPERSMOOTHER_LENGTH,
    TRAILING_STOP_ENABLED, TRAILING_STOP_PERCENT, TRAILING_STOP_ACTIVATION_PERCENT,
    PARTIAL_TAKE_PROFIT_ENABLED, PARTIAL_TAKE_PROFIT_LEVELS
)
from indicators import (
    calculate_fibonacci_pivot_points, calculate_stochrsi, calculate_atr,
    calculate_sma, calculate_ehlers_fisher_transform, calculate_ehlers_super_smoother,
    find_pivots, handle_websocket_kline_data # Ensure find_pivots and handle_websocket_kline_data are here
)
from strategy import generate_signals, generate_exit_signals
from bybit_api import BybitContractAPI
from bot_ui import display_market_info

# --- Configure Logging ---
from bot_logger import setup_logging, log_trade, log_metrics, log_exception
from trade_metrics import TradeMetrics
from utils import calculate_order_quantity, convert_interval_to_ms

class PyrmethusBot:
    """
    The core trading bot logic, encapsulating state, API interactions,
    and trading decisions.
    """
    def __init__(self):
        self.bot_logger = setup_logging()
        self.trade_metrics = TradeMetrics()
        self.bybit_client: Optional[BybitContractAPI] = None

        # --- Bot State Variables (using Decimal for precision) ---
        self.inventory: Decimal = Decimal('0') # Primary position tracker. >0 for long, <0 for short.
        self.entry_price: Decimal = Decimal('0')
        self.unrealized_pnl: Decimal = Decimal('0')

        # Trade-specific metrics for tracking
        self.entry_price_for_trade_metrics: Decimal = Decimal('0')
        self.entry_fee_for_trade_metrics: Decimal = Decimal('0')

        self.current_price: Decimal = Decimal('0')
        self.klines_df: Optional[pd.DataFrame] = None
        self.cached_atr: Optional[Decimal] = None

        # --- Order Block Tracking ---
        self.active_bull_obs: List[OrderBlock] = []
        self.active_bear_obs: List[OrderBlock] = []

        # --- Trailing Stop Loss State ---
        self.trailing_stop_loss_price: Optional[Decimal] = None
        self.trailing_stop_activated: bool = False

        # --- Partial Take Profit State ---
        self.partial_profit_taken_levels: List[Decimal] = [] # To track which levels have been hit

    def _reset_position_state(self):
        """Resets all internal state variables related to an open position."""
        self.inventory = Decimal('0')
        self.entry_price = Decimal('0')
        self.unrealized_pnl = Decimal('0')
        self.entry_price_for_trade_metrics = Decimal('0')
        self.entry_fee_for_trade_metrics = Decimal('0')
        self.trailing_stop_loss_price = None
        self.trailing_stop_activated = False
        self.partial_profit_taken_levels = []
        self.bot_logger.info(f"{PYRMETHUS_GREY}✅ Position state reset. Ready for new opportunities.{COLOR_RESET}")

    def _identify_and_manage_order_blocks(self):
        """
        Identifies new Pivot High/Low based Order Blocks and manages existing ones.
        This function should be called after klines_df is updated.
        """
        if self.klines_df is None or self.klines_df.empty:
            self.bot_logger.debug("No klines_df to identify Order Blocks from.")
            return

        # Ensure enough data for pivot calculation
        if len(self.klines_df) < max(PIVOT_LEFT_BARS, PIVOT_RIGHT_BARS) + 1:
            self.bot_logger.debug(f"Insufficient klines ({len(self.klines_df)}) for pivot detection. Need at least {max(PIVOT_LEFT_BARS, PIVOT_RIGHT_BARS) + 1}.")
            return

        # Find pivots (using the function from indicators.py)
        pivot_highs, pivot_lows = find_pivots(self.klines_df, PIVOT_LEFT_BARS, PIVOT_RIGHT_BARS)

        last_candle_idx = self.klines_df.index[-1]
        last_candle = self.klines_df.iloc[-1]
        
        # Identify new Order Blocks on the *last completed* candle
        # Check if the last candle (which might be incomplete) or the second to last candle (complete) is a pivot.
        # For OBs, it's safer to identify on completed candles.
        # Let's consider the second-to-last candle for OB creation to ensure it's a confirmed pivot.
        if len(self.klines_df) >= 2:
            confirmed_candle_idx = self.klines_df.index[-2]
            confirmed_candle = self.klines_df.iloc[-2]

            # Check if this confirmed_candle is a new pivot high/low
            is_pivot_high = pivot_highs.iloc[-2]
            is_pivot_low = pivot_lows.iloc[-2]

            if is_pivot_high:
                ob_top = confirmed_candle['high']
                ob_bottom = confirmed_candle['low'] # For bearish OB, the entire candle range
                new_ob = OrderBlock(id=f"B_{confirmed_candle_idx.value}", type='bear', timestamp=confirmed_candle_idx,
                                    top=ob_top, bottom=ob_bottom, active=True, violated=False, violation_ts=None,
                                    extended_to_ts=confirmed_candle_idx)
                # Avoid adding duplicates
                if not any(ob['id'] == new_ob['id'] for ob in self.active_bear_obs):
                    self.active_bear_obs.append(new_ob)
                    self.bot_logger.info(f"{PYRMETHUS_BLUE}New Bearish OB identified: {new_ob['id']} at {ob_top:.4f}-{ob_bottom:.4f}{COLOR_RESET}")

            if is_pivot_low:
                ob_bottom = confirmed_candle['low']
                ob_top = confirmed_candle['high'] # For bullish OB, the entire candle range
                new_ob = OrderBlock(id=f"L_{confirmed_candle_idx.value}", type='bull', timestamp=confirmed_candle_idx,
                                    top=ob_top, bottom=ob_bottom, active=True, violated=False, violation_ts=None,
                                    extended_to_ts=confirmed_candle_idx)
                # Avoid adding duplicates
                if not any(ob['id'] == new_ob['id'] for ob in self.active_bull_obs):
                    self.active_bull_obs.append(new_ob)
                    self.bot_logger.info(f"{PYRMETHUS_BLUE}New Bullish OB identified: {new_ob['id']} at {ob_top:.4f}-{ob_bottom:.4f}{COLOR_RESET}")

        # Manage existing Order Blocks (violation and extension)
        current_price = self.current_price
        current_timestamp = last_candle_idx # Use the latest timestamp for extension/violation checks

        # Handle Bullish OBs
        for ob in list(self.active_bull_obs): # Iterate over a copy to allow modification
            if ob['active']:
                # Violation: Price closes below the bottom of a bullish OB
                if current_price < ob['bottom']:
                    ob['active'] = False
                    ob['violated'] = True
                    ob['violation_ts'] = current_timestamp
                    self.bot_logger.info(f"{COLOR_RED}Bullish OB {ob['id']} violated by current price {current_price:.4f} (below {ob['bottom']:.4f}){COLOR_RESET}")
                else:
                    ob['extended_to_ts'] = current_timestamp # Extend active OB

        # Handle Bearish OBs
        for ob in list(self.active_bear_obs): # Iterate over a copy
            if ob['active']:
                # Violation: Price closes above the top of a bearish OB
                if current_price > ob['top']:
                    ob['active'] = False
                    ob['violated'] = True
                    ob['violation_ts'] = current_timestamp
                    self.bot_logger.info(f"{COLOR_RED}Bearish OB {ob['id']} violated by current price {current_price:.4f} (above {ob['top']:.4f}){COLOR_RESET}")
                else:
                    ob['extended_to_ts'] = current_timestamp # Extend active OB

        # Filter out inactive/violated OBs and keep only the most recent active ones
        self.active_bull_obs = [ob for ob in self.active_bull_obs if ob['active']]
        self.active_bear_obs = [ob for ob in self.active_bear_obs if ob['active']]

        # Limit the number of active OBs to prevent excessive memory usage and focus on recent ones
        self.active_bull_obs.sort(key=lambda x: x['timestamp'], reverse=True)
        self.active_bull_obs = self.active_bull_obs[:10]
        self.active_bear_obs.sort(key=lambda x: x['timestamp'], reverse=True)
        self.active_bear_obs = self.active_bear_obs[:10]

        self.bot_logger.debug(f"Active OBs after management: Bull={len(self.active_bull_obs)}, Bear={len(self.active_bear_obs)}")

    async def _handle_position_update(self, message: Dict[str, Any]):
        """
        Asynchronous handler for WebSocket position updates.
        This is the single source of truth for the bot's open position state.
        It also triggers TP/SL updates.
        """
        if message.get("topic") != "position" or not message.get("data"):
            self.bot_logger.debug(f"Received non-position or empty WS update: {message}")
            return

        pos_data = message["data"]
        # Bybit WS sends an array of positions, usually just one for the symbol we care about.
        # If the list is empty, it means no open positions for the subscribed symbols.
        if not pos_data or not pos_data[0] or Decimal(pos_data[0].get('size', '0')) == Decimal('0'):
            if self.inventory != Decimal('0'):
                self.bot_logger.info(f"{PYRMETHUS_GREEN}🎉 Position for {SYMBOL} closed successfully (inferred from WS data)!{COLOR_RESET}")
                # Record trade metrics only if a position was previously open
                exit_price = self.current_price if self.current_price else Decimal('0') # Use current_price for exit if available
                exit_fee = self.trade_metrics.calculate_fee(abs(self.inventory), exit_price, is_maker=False)
                self.trade_metrics.record_trade(
                    self.entry_price_for_trade_metrics, exit_price,
                    abs(self.inventory), self.current_position_side,
                    self.entry_fee_for_trade_metrics, exit_fee, pd.Timestamp.now(tz='UTC')
                )
                log_metrics(self.bot_logger, "Overall Trade Statistics", self.trade_metrics.get_trade_statistics())

            self._reset_position_state()
            self.bot_logger.info(f"{PYRMETHUS_GREY}✅ No open position for {SYMBOL} (WS). Seeking new trade opportunities...{COLOR_RESET}")
            return

        # Position is open
        pos = pos_data[0] # Assuming only one position for the subscribed symbol
        symbol = pos.get('symbol')
        size_str = pos.get('size', '0')
        side = pos.get('side')
        avg_price_str = pos.get('avgPrice', '0')
        unrealized_pnl_str = pos.get('unrealisedPnl', '0')

        new_size = Decimal(size_str)
        new_entry_price = Decimal(avg_price_str)

        # Determine signed inventory for precise PnL calculation
        signed_inventory = new_size if side == 'Buy' else -new_size

        # Check if position details have genuinely changed to avoid redundant updates
        position_changed = self.inventory != signed_inventory
        entry_price_changed = self.entry_price != new_entry_price and new_size > 0

        if not self.inventory and new_size > 0: # Position just opened (from zero inventory)
            self.bot_logger.info(f"{PYRMETHUS_GREEN}🎉 Position detected and tracked via WebSocket for {symbol}.{COLOR_RESET}")
            self.entry_price_for_trade_metrics = new_entry_price
            self.entry_fee_for_trade_metrics = self.trade_metrics.calculate_fee(new_size, new_entry_price, is_maker=False)
            self.trailing_stop_activated = False # Reset trailing stop state for new position
            self.partial_profit_taken_levels = [] # Reset partial profit levels

        # Update state
        self.inventory = signed_inventory
        self.entry_price = new_entry_price
        self.unrealized_pnl = Decimal(unrealized_pnl_str) if unrealized_pnl_str else Decimal('0')
        self.current_position_side = side if new_size > 0 else None

        if new_size > 0: # Still an open position
            self.bot_logger.info(
                f"{PYRMETHUS_BLUE}💼 Open Position (WS): {self.current_position_side} {abs(self.inventory):.4f} {symbol} "
                f"at {self.entry_price:.4f}. Unrealized PnL: {self.unrealized_pnl:.4f}{COLOR_RESET}"
            )
            # If position details changed, update TP/SL
            if position_changed or entry_price_changed:
                await self._update_take_profit_stop_loss()
            # Always check trailing stop and partial take profit if enabled
            await self._manage_dynamic_exits()
        else:
            # This case is handled by the "No open position" block at the start
            pass

    async def _update_take_profit_stop_loss(self):
        """
        Sets or updates initial static Take Profit and Stop Loss for the current position.
        Dynamic management (trailing stop, partial TP) is handled by _manage_dynamic_exits.
        """
        if abs(self.inventory) == Decimal('0'):
            self.bot_logger.debug(f"[{SYMBOL}] No open position to set TP/SL for.")
            return

        take_profit_price = None
        stop_loss_price = None
        current_pnl_pct = (self.unrealized_pnl / (abs(self.inventory) * self.entry_price)) * Decimal('100') if self.entry_price > 0 else Decimal('0')

        # Prioritize ATR-based TP/SL if multipliers are set and ATR is available
        if self.cached_atr is not None and ATR_MULTIPLIER_SL is not None and ATR_MULTIPLIER_TP is not None:
            atr_sl_value = self.cached_atr * Decimal(str(ATR_MULTIPLIER_SL))
            atr_tp_value = self.cached_atr * Decimal(str(ATR_MULTIPLIER_TP))

            if self.inventory > 0: # Long position
                stop_loss_price = self.entry_price - atr_sl_value
                take_profit_price = self.entry_price + atr_tp_value
            elif self.inventory < 0: # Short position
                stop_loss_price = self.entry_price + atr_sl_value
                take_profit_price = self.entry_price - atr_tp_value
            self.bot_logger.info(f"{PYRMETHUS_ORANGE}Dynamic TP/SL (ATR-based) for {SYMBOL}: TP={take_profit_price:.4f}, SL={stop_loss_price:.4f}{COLOR_RESET}")
        # Fallback to static percentage-based TP/SL
        else:
            if self.inventory > 0: # Long position
                if TAKE_PROFIT_PCT is not None:
                    take_profit_price = self.entry_price * (Decimal('1') + Decimal(str(TAKE_PROFIT_PCT)))
                if STOP_LOSS_PCT is not None:
                    stop_loss_price = self.entry_price * (Decimal('1') - Decimal(str(STOP_LOSS_PCT)))
            elif self.inventory < 0: # Short position
                if TAKE_PROFIT_PCT is not None:
                    take_profit_price = self.entry_price * (Decimal('1') - Decimal(str(TAKE_PROFIT_PCT)))
                if STOP_LOSS_PCT is not None:
                    stop_loss_price = self.entry_price * (Decimal('1') + Decimal(str(STOP_LOSS_PCT)))
            self.bot_logger.info(f"{PYRMETHUS_ORANGE}Static TP/SL (Percentage-based) for {SYMBOL}: TP={take_profit_price}, SL={stop_loss_price}{COLOR_RESET}")

        # Trailing Stop Loss logic (initial setup or adjustment)
        if TRAILING_STOP_ENABLED and self.current_price > Decimal('0'):
            # Only set initial trailing stop if not already activated
            if not self.trailing_stop_activated:
                # Calculate the activation threshold for trailing stop
                activation_price = self.entry_price * (Decimal('1') + Decimal(str(TRAILING_STOP_ACTIVATION_PERCENT))) if self.inventory > 0 else \
                                   self.entry_price * (Decimal('1') - Decimal(str(TRAILING_STOP_ACTIVATION_PERCENT)))

                # If current price has crossed activation, set the initial trailing stop
                if (self.inventory > 0 and self.current_price >= activation_price) or \
                   (self.inventory < 0 and self.current_price <= activation_price):
                    self.trailing_stop_activated = True
                    # Set initial trailing stop at breakeven or slightly in profit
                    self.trailing_stop_loss_price = self.entry_price # Or entry_price + fee/etc.
                    self.bot_logger.info(f"{PYRMETHUS_GREEN}Trailing Stop Loss activated at {self.trailing_stop_loss_price:.4f}!{COLOR_RESET}")
                else:
                    self.bot_logger.debug(f"Trailing stop not yet activated. Current price: {self.current_price:.4f}, Activation: {activation_price:.4f}")
            else: # Trailing stop already active, adjust if necessary
                if self.inventory > 0: # Long position
                    new_trailing_stop = self.current_price * (Decimal('1') - Decimal(str(TRAILING_STOP_PERCENT)))
                    if self.trailing_stop_loss_price is None or new_trailing_stop > self.trailing_stop_loss_price:
                        self.trailing_stop_loss_price = new_trailing_stop
                        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Trailing Stop Loss updated to {self.trailing_stop_loss_price:.4f} for long position.{COLOR_RESET}")
                elif self.inventory < 0: # Short position
                    new_trailing_stop = self.current_price * (Decimal('1') + Decimal(str(TRAILING_STOP_PERCENT)))
                    if self.trailing_stop_loss_price is None or new_trailing_stop < self.trailing_stop_loss_price:
                        self.trailing_stop_loss_price = new_trailing_stop
                        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Trailing Stop Loss updated to {self.trailing_stop_loss_price:.4f} for short position.{COLOR_RESET}")
            # Use the higher of static SL or trailing SL if both exist for long, lower for short
            if self.trailing_stop_loss_price is not None:
                if self.inventory > 0: # Long
                    stop_loss_price = max(stop_loss_price or Decimal('0'), self.trailing_stop_loss_price) if stop_loss_price else self.trailing_stop_loss_price
                elif self.inventory < 0: # Short
                    stop_loss_price = min(stop_loss_price or Decimal('Inf'), self.trailing_stop_loss_price) if stop_loss_price else self.trailing_stop_loss_price


        # Send update to Bybit only if TP/SL prices are calculated
        if take_profit_price or stop_loss_price:
            self.bot_logger.debug(f"Attempting to set TP: {take_profit_price}, SL: {stop_loss_price}")
            # Ensure SL is not above entry for long, or below entry for short (unless trailing)
            if stop_loss_price:
                if (self.inventory > 0 and stop_loss_price > self.entry_price) or \
                   (self.inventory < 0 and stop_loss_price < self.entry_price):
                    self.bot_logger.warning(f"{COLOR_YELLOW}Calculated SL ({stop_loss_price:.4f}) is unfavorable to entry ({self.entry_price:.4f}). Adjusting to entry price for safety unless trailing is active.{COLOR_RESET}")
                    # Only override if trailing stop is NOT the reason for the 'unfavorable' SL
                    if not self.trailing_stop_activated or (self.trailing_stop_activated and (
                        (self.inventory > 0 and stop_loss_price < self.entry_price) or
                        (self.inventory < 0 and stop_loss_price > self.entry_price)
                    )):
                        stop_loss_price = self.entry_price # Move to breakeven

            set_tp = f"{take_profit_price:.8f}" if take_profit_price else None
            set_sl = f"{stop_loss_price:.8f}" if stop_loss_price else None

            # Only send request if there's an actual change or a value to set
            current_tp_sl = await self.bybit_client.get_trading_stop(category=BYBIT_CATEGORY, symbol=SYMBOL, positionIdx=0)
            current_tp = Decimal(current_tp_sl.get('takeProfit', '0')) if current_tp_sl else Decimal('0')
            current_sl = Decimal(current_tp_sl.get('stopLoss', '0')) if current_tp_sl else Decimal('0')

            tp_changed = (set_tp is not None and Decimal(set_tp) != current_tp) or (set_tp is None and current_tp != Decimal('0'))
            sl_changed = (set_sl is not None and Decimal(set_sl) != current_sl) or (set_sl is None and current_sl != Decimal('0'))

            if tp_changed or sl_changed:
                self.bot_logger.info(f"{PYRMETHUS_CYAN}Updating Bybit TP/SL: New TP={set_tp}, New SL={set_sl}{COLOR_RESET}")
                await self.bybit_client.set_trading_stop(
                    category=BYBIT_CATEGORY,
                    symbol=SYMBOL,
                    take_profit=set_tp,
                    stop_loss=set_sl,
                    positionIdx=0 # Assuming isolated margin, positionIdx=0 for single position
                )
            else:
                self.bot_logger.debug(f"No change in TP/SL detected. Current TP: {current_tp:.4f}, SL: {current_sl:.4f}")

    async def _manage_dynamic_exits(self):
        """
        Handles dynamic exit strategies like Trailing Stop Loss and Partial Take Profit.
        Called on every kline/price update.
        """
        if abs(self.inventory) == Decimal('0') or self.current_price == Decimal('0') or self.entry_price == Decimal('0'):
            return

        current_pnl_pct = (self.unrealized_pnl / (abs(self.inventory) * self.entry_price)) * Decimal('100') if self.entry_price > 0 else Decimal('0')

        # --- Trailing Stop Loss Management ---
        if TRAILING_STOP_ENABLED:
            if not self.trailing_stop_activated:
                # Check for activation
                activation_price = self.entry_price * (Decimal('1') + Decimal(str(TRAILING_STOP_ACTIVATION_PERCENT))) if self.inventory > 0 else \
                                   self.entry_price * (Decimal('1') - Decimal(str(TRAILING_STOP_ACTIVATION_PERCENT)))

                if (self.inventory > 0 and self.current_price >= activation_price) or \
                   (self.inventory < 0 and self.current_price <= activation_price):
                    self.trailing_stop_activated = True
                    # Set initial trailing stop (e.g., at breakeven or slightly positive)
                    self.trailing_stop_loss_price = self.entry_price # Consider adding a small buffer for fees
                    self.bot_logger.info(f"{PYRMETHUS_GREEN}Trailing Stop Loss activated! Initial SL set at {self.trailing_stop_loss_price:.4f}{COLOR_RESET}")
                    await self._update_take_profit_stop_loss() # Update exchange with new SL
            elif self.trailing_stop_activated and self.trailing_stop_loss_price is not None:
                # Adjust trailing stop if price moves favorably
                if self.inventory > 0: # Long position
                    new_potential_sl = self.current_price * (Decimal('1') - Decimal(str(TRAILING_STOP_PERCENT)))
                    if new_potential_sl > self.trailing_stop_loss_price:
                        self.trailing_stop_loss_price = new_potential_sl
                        self.bot_logger.debug(f"Trailing SL updated for long: {self.trailing_stop_loss_price:.4f}")
                        await self._update_take_profit_stop_loss() # Update exchange with new SL
                elif self.inventory < 0: # Short position
                    new_potential_sl = self.current_price * (Decimal('1') + Decimal(str(TRAILING_STOP_PERCENT)))
                    if new_potential_sl < self.trailing_stop_loss_price:
                        self.trailing_stop_loss_price = new_potential_sl
                        self.bot_logger.debug(f"Trailing SL updated for short: {self.trailing_stop_loss_price:.4f}")
                        await self._update_take_profit_stop_loss() # Update exchange with new SL

        # --- Partial Take Profit Management ---
        if PARTIAL_TAKE_PROFIT_ENABLED and PARTIAL_TAKE_PROFIT_LEVELS:
            for level_pct, qty_pct in PARTIAL_TAKE_PROFIT_LEVELS:
                target_price = self.entry_price * (Decimal('1') + Decimal(str(level_pct))) if self.inventory > 0 else \
                               self.entry_price * (Decimal('1') - Decimal(str(level_pct)))

                # Check if this level has already been taken
                if target_price in self.partial_profit_taken_levels:
                    continue

                # Check if current price has reached or surpassed the target
                level_reached = (self.inventory > 0 and self.current_price >= target_price) or \
                                (self.inventory < 0 and self.current_price <= target_price)

                if level_reached:
                    qty_to_take = abs(self.inventory) * Decimal(str(qty_pct)) / Decimal('100')
                    if qty_to_take > Decimal('0'):
                        self.bot_logger.info(f"{PYRMETHUS_GREEN}Partial Take Profit at {level_pct*100:.2f}% (Price: {target_price:.4f})! Selling {qty_to_take:.4f} {SYMBOL}.{COLOR_RESET}")
                        exit_side = 'Sell' if self.inventory > 0 else 'Buy' # Opposite of current position side
                        if await self._execute_exit(exit_side, self.current_price, pd.Timestamp.now(tz='UTC'), {"partial_profit_level": level_pct}):
                            self.partial_profit_taken_levels.append(target_price)
                        else:
                            self.bot_logger.warning(f"{COLOR_YELLOW}Failed to execute partial take profit order.{COLOR_RESET}")
                    else:
                        self.bot_logger.warning(f"{COLOR_YELLOW}Calculated partial take profit quantity is zero. Skipping.{COLOR_RESET}")


    async def _handle_kline_update(self, message: Dict[str, Any]):
        """
        Asynchronous handler for WebSocket kline updates.
        Updates the internal klines_df and derived indicators.
        """
        if message.get("topic") != f"kline.{INTERVAL}.{SYMBOL}" or not message.get("data"):
            self.bot_logger.debug(f"Received non-kline or empty WS update: {message}")
            return

        # Use the handle_websocket_kline_data from indicators.py to update DataFrame
        updated_df = handle_websocket_kline_data(self.klines_df, message)

        if updated_df is not None and not updated_df.empty:
            self.klines_df = updated_df
            # Recalculate all necessary indicators on the updated DataFrame
            self.klines_df = calculate_stochrsi(self.klines_df.copy(),
                                                rsi_period=STOCHRSI_K_PERIOD,
                                                stoch_k_period=STOCHRSI_K_PERIOD,
                                                stoch_d_period=STOCHRSI_D_PERIOD)
            self.klines_df['atr'] = calculate_atr(self.klines_df, period=ATR_PERIOD)
            self.klines_df['sma'] = calculate_sma(self.klines_df, length=SMA_PERIOD)
            self.klines_df['ehlers_fisher'] = calculate_ehlers_fisher_transform(self.klines_df, length=FISHER_LENGTH)
            self.klines_df['ehlers_supersmoother'] = calculate_ehlers_super_smoother(self.klines_df, length=SUPERSMOOTHER_LENGTH)

            # Update cached values
            self.cached_atr = self.klines_df['atr'].iloc[-1] if 'atr' in self.klines_df.columns and not self.klines_df['atr'].empty else Decimal('0')
            self.current_price = self.klines_df['close'].iloc[-1]

            # Manage Order Blocks based on the latest data
            self._identify_and_manage_order_blocks()

            # Manage dynamic exits (trailing stop, partial TP) based on new price
            await self._manage_dynamic_exits()

            self.bot_logger.debug(f"{PYRMETHUS_CYAN}Kline updated via WebSocket. Current price: {self.current_price:.4f}{COLOR_RESET}")
        else:
            self.bot_logger.warning(f"{COLOR_YELLOW}Failed to update klines_df from WebSocket message: {message}{COLOR_RESET}")

    async def _initial_kline_fetch(self) -> bool:
        """Fetches initial historical kline data to populate the DataFrame."""
        try:
            # Fetch more candles than strictly necessary for indicator warm-up periods
            klines_response = await self.bybit_client.get_kline_rest_fallback(
                category=BYBIT_CATEGORY, symbol=SYMBOL, interval=INTERVAL, limit=CANDLE_FETCH_LIMIT
            )
            if not klines_response or not klines_response.get('result') or not klines_response['result'].get('list'):
                self.bot_logger.error(f"{COLOR_RED}Initial kline data fetch failed for {SYMBOL}. Bot cannot start.{COLOR_RESET}")
                return False

            data = []
            for kline in klines_response['result']['list']:
                data.append({
                    'timestamp': pd.to_datetime(int(kline[0]), unit='ms', utc=True),
                    'open': Decimal(kline[1]),
                    'high': Decimal(kline[2]),
                    'low': Decimal(kline[3]),
                    'close': Decimal(kline[4]),
                    'volume': Decimal(kline[5]),
                })
            df = pd.DataFrame(data).set_index('timestamp').sort_index()

            # Ensure enough data for all indicators
            required_candles = max(STOCHRSI_K_PERIOD, ATR_PERIOD, SMA_PERIOD, FISHER_LENGTH, SUPERSMOOTHER_LENGTH)
            if len(df) < required_candles:
                self.bot_logger.warning(f"{COLOR_YELLOW}Insufficient initial data for indicators ({len(df)} candles). Need at least {required_candles}. Attempting to proceed but indicators might be incomplete.{COLOR_RESET}")

            self.klines_df = calculate_stochrsi(df.copy(), rsi_period=STOCHRSI_K_PERIOD, stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD)
            self.klines_df['atr'] = calculate_atr(self.klines_df, period=ATR_PERIOD)
            self.klines_df['sma'] = calculate_sma(self.klines_df, length=SMA_PERIOD)
            self.klines_df['ehlers_fisher'] = calculate_ehlers_fisher_transform(self.klines_df, length=FISHER_LENGTH)
            self.klines_df['ehlers_supersmoother'] = calculate_ehlers_super_smoother(self.klines_df, length=SUPERSMOOTHER_LENGTH)

            # Update cached values
            self.cached_atr = self.klines_df['atr'].iloc[-1] if 'atr' in self.klines_df.columns and not self.klines_df['atr'].empty else Decimal('0')
            self.current_price = self.klines_df['close'].iloc[-1]
            self.bot_logger.info(f"{PYRMETHUS_GREEN}Initial kline data fetched and processed. Current price: {self.current_price:.4f}{COLOR_RESET}")
            return True
        except Exception as e:
            log_exception(self.bot_logger, f"Error during initial kline fetch: {e}", e)
            return False

    async def _execute_entry(self, signal_type: str, signal_price: Decimal, signal_timestamp: Any, signal_info: Dict[str, Any]):
        """Executes an entry trade based on a signal."""
        self.bot_logger.info(f"{PYRMETHUS_PURPLE}💡 Detected {signal_type.upper()} entry signal at {signal_price:.4f} (Info: {signal_info.get('stoch_type', 'N/A')}){COLOR_RESET}")

        # Fetch instrument info for min_qty and qty_step
        instrument_info_resp = await self.bybit_client.get_instruments_info(category=BYBIT_CATEGORY, symbol=SYMBOL)
        if not instrument_info_resp or not instrument_info_resp.get('result') or not instrument_info_resp['result'].get('list'):
            self.bot_logger.error(f"{COLOR_RED}Could not fetch instrument info for {SYMBOL}. Cannot place entry order.{COLOR_RESET}")
            return False

        instrument_details = instrument_info_resp['result']['list'][0]
        min_qty = Decimal(instrument_details.get('lotSizeFilter', {}).get('minOrderQty', '0'))
        qty_step = Decimal(instrument_details.get('lotSizeFilter', {}).get('qtyStep', '0'))

        calculated_quantity_float = calculate_order_quantity(USDT_AMOUNT_PER_TRADE, self.current_price, min_qty, qty_step)
        calculated_quantity = Decimal(str(calculated_quantity_float))
        if calculated_quantity <= 0:
            self.bot_logger.error(f"{COLOR_RED}Calculated entry quantity is zero or negative: {calculated_quantity}. Cannot place order.{COLOR_RESET}")
            return False

        order_kwargs = {
            "category": BYBIT_CATEGORY,
            "symbol": SYMBOL,
            "side": signal_type.capitalize(), # 'Buy' for long, 'Sell' for short
            "order_type": "Market",
            "qty": str(calculated_quantity),
        }

        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Attempting to place {signal_type.upper()} order for {calculated_quantity:.4f} {SYMBOL} at market price...{COLOR_RESET}")
        if await self.bybit_client.create_order(**order_kwargs):
            log_trade(self.bot_logger, "Entry trade executed", {
                "signal_type": signal_type.upper(),
                "price": self.current_price,
                "timestamp": str(signal_timestamp),
                "stoch_k": signal_info.get('stoch_k'),
                "stoch_d": signal_info.get('stoch_d'),
                "usdt_amount": USDT_AMOUNT_PER_TRADE,
                "order_type": "Market",
                "quantity": calculated_quantity,
            })
            # Position state and TP/SL will be updated by WebSocket callback (_handle_position_update)
            return True
        return False

    async def _execute_exit(self, exit_type: str, exit_price: Decimal, exit_timestamp: Any, exit_info: Dict[str, Any]):
        """Executes an exit trade based on a signal or dynamic exit logic."""
        self.bot_logger.info(f"{PYRMETHUS_PURPLE}💡 Detected {exit_type.upper()} exit signal at {exit_price:.4f} (Info: {exit_info.get('stoch_type', 'N/A')}){COLOR_RESET}")

        # Ensure we have an open position to exit
        if abs(self.inventory) <= 0:
            self.bot_logger.warning(f"{COLOR_YELLOW}Attempted to exit, but current inventory is 0. Skipping exit order.{COLOR_RESET}")
            return False

        exit_order_kwargs = {
            "category": BYBIT_CATEGORY,
            "symbol": SYMBOL,
            "side": exit_type.capitalize(), # 'Sell' for long exit, 'Buy' for short exit
            "order_type": "Market",
            "qty": str(abs(self.inventory)), # Exit full position
        }

        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Attempting to place {exit_type.upper()} exit order for {abs(self.inventory):.4f} {SYMBOL} at market price...{COLOR_RESET}")
        if await self.bybit_client.create_order(**exit_order_kwargs):
            log_trade(self.bot_logger, "Exit trade executed", {
                "exit_type": exit_type.upper(),
                "price": self.current_price,
                "timestamp": str(exit_timestamp),
                "stoch_k": exit_info.get('stoch_k'),
                "stoch_d": exit_info.get('stoch_d'),
                "exit_quantity": str(abs(self.inventory)),
                "order_type": "Market",
                "reason": exit_info.get('reason', 'Signal'),
            })
            # Position state will be updated by WebSocket callback
            return True
        return False

    async def run(self):
        """Main execution loop for the trading bot."""
        self.bot_logger.info("Starting Pyrmethus's Ultra Scalper Bot.")

        print(f"{PYRMETHUS_PURPLE}{COLOR_BOLD}\n🚀 Pyrmethus's Ultra Scalper Bot - Awakened{COLOR_RESET}")
        print(f"{PYRMETHUS_PURPLE}{COLOR_BOLD}=========================================={COLOR_RESET}")
        print(f"{PYRMETHUS_ORANGE}\n⚡ Initializing scalping engine and calibrating sensors...{COLOR_RESET}")

        self.bybit_client = BybitContractAPI(
            testnet="testnet" in BYBIT_API_ENDPOINT # Automatically determine testnet from endpoint
        )
        self.bot_logger.info("BybitContractAPI initialized.")

        # Start WebSocket listeners for real-time updates
        private_listener_task = asyncio.create_task(self.bybit_client.start_private_websocket_listener(self._handle_position_update))
        await self.bybit_client.subscribe_ws_private_topic("position")

        public_listener_task = asyncio.create_task(self.bybit_client.start_public_websocket_listener(self._handle_kline_update))
        await self.bybit_client.subscribe_ws_public_topic(f"kline.{INTERVAL}.{SYMBOL}")

        # Initial fetch of historical kline data
        if not await self._initial_kline_fetch():
            self.bot_logger.critical(f"{COLOR_RED}Failed to fetch initial kline data. Exiting bot.{COLOR_RESET}")
            # Cancel listeners before exiting
            private_listener_task.cancel()
            public_listener_task.cancel()
            await asyncio.gather(private_listener_task, public_listener_task, return_exceptions=True)
            return

        # Check for any existing open positions at startup
        initial_pos_response = await self.bybit_client.get_positions(category=BYBIT_CATEGORY, symbol=SYMBOL)
        if initial_pos_response and initial_pos_response.get('result') and initial_pos_response['result'].get('list'):
            # Simulate a WebSocket message to process existing positions
            simulated_message = {"topic": "position", "data": initial_pos_response['result']['list']}
            await self._handle_position_update(simulated_message)
        else:
            await self._handle_position_update({"topic": "position", "data": []}) # Ensure state is reset if no position

        # Gather all listener tasks to run concurrently
        listener_tasks = [private_listener_task, public_listener_task]

        async with self.bybit_client: # Use async context manager for proper connection handling
            try:
                while True:
                    # Ensure klines_df is not None and has enough data for calculations
                    required_candles = max(STOCHRSI_K_PERIOD, ATR_PERIOD, SMA_PERIOD, FISHER_LENGTH, SUPERSMOOTHER_LENGTH, PIVOT_LEFT_BARS + PIVOT_RIGHT_BARS + 1)
                    if self.klines_df is None or len(self.klines_df) < required_candles:
                        self.bot_logger.warning(f"{COLOR_YELLOW}Insufficient kline data for calculations ({len(self.klines_df) if self.klines_df is not None else 0} candles). Need at least {required_candles}. Waiting for more data...{COLOR_RESET}")
                        await asyncio.sleep(POLLING_INTERVAL_SECONDS)
                        continue

                    # --- Calculate Fibonacci Pivot Levels (if enabled) ---
                    pivot_support_levels: Dict[str, Decimal] = {}
                    pivot_resistance_levels: Dict[str, Decimal] = {}

                    if ENABLE_FIB_PIVOT_ACTIONS:
                        self.bot_logger.debug(f"Calculating Fibonacci Pivots based on {PIVOT_TIMEFRAME} timeframe...")
                        try:
                            # Fetch data for the *previous complete* pivot timeframe candle
                            # We need to calculate the timestamp for the start of the previous interval
                            now_ms = int(pd.Timestamp.now(tz='UTC').timestamp() * 1000)
                            interval_ms = convert_interval_to_ms(PIVOT_TIMEFRAME)
                            # Calculate the timestamp of the start of the *previous* complete candle
                            # (current_time // interval_ms) * interval_ms gives start of current interval
                            # Subtract interval_ms to get start of previous interval
                            prev_interval_start_ms = (now_ms // interval_ms) * interval_ms - interval_ms

                            pivot_ohlcv_response = await self.bybit_client.get_kline_rest_fallback(
                                category=BYBIT_CATEGORY, symbol=SYMBOL, interval=PIVOT_TIMEFRAME,
                                start=prev_interval_start_ms, limit=1 # Fetch only the previous complete candle
                            )

                            if pivot_ohlcv_response and pivot_ohlcv_response.get('result') and pivot_ohlcv_response['result'].get('list'):
                                pivot_kline = pivot_ohlcv_response['result']['list'][0]
                                # Create a DataFrame with this single kline
                                temp_df = pd.DataFrame([{
                                    'timestamp': pd.to_datetime(int(pivot_kline[0]), unit='ms', utc=True),
                                    'open': Decimal(pivot_kline[1]),
                                    'high': Decimal(pivot_kline[2]),
                                    'low': Decimal(pivot_kline[3]),
                                    'close': Decimal(pivot_kline[4]),
                                    'volume': Decimal(pivot_kline[5]),
                                }]).set_index('timestamp')

                                # Pass the single candle DataFrame to calculate_fibonacci_pivot_points
                                resistance_levels, support_levels = calculate_fibonacci_pivot_points(temp_df)

                                for r_level in resistance_levels:
                                    pivot_resistance_levels[r_level['type']] = r_level['price']
                                for s_level in support_levels:
                                    pivot_support_levels[s_level['type']] = s_level['price']

                                self.bot_logger.debug(f"Fibonacci Pivot Levels: Support={pivot_support_levels}, Resistance={pivot_resistance_levels}")
                            else:
                                self.bot_logger.warning(f"{COLOR_YELLOW}Failed to fetch previous {PIVOT_TIMEFRAME} candle for Fibonacci Pivots.{COLOR_RESET}")
                        except Exception as pivot_e:
                            log_exception(self.bot_logger, f"Error during Fibonacci Pivot calculation: {pivot_e}", pivot_e)

                    # Display current market info and bot state
                    display_market_info(
                        self.klines_df, self.current_price, SYMBOL,
                        list(pivot_resistance_levels.values()), list(pivot_support_levels.values()), # Pass values as lists for display
                        self.bot_logger,
                        self.active_bull_obs, self.active_bear_obs, # Pass active OBs
                        self.inventory, self.entry_price, self.unrealized_pnl # Pass position info
                    )

                    # Main trading logic
                    if abs(self.inventory) == Decimal('0'): # No position open
                        signals = generate_signals(
                            self.klines_df,
                            self.active_bull_obs, self.active_bear_obs,
                            stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD,
                            overbought=STOCHRSI_OVERBOUGHT_LEVEL, oversold=STOCHRSI_OVERSOLD_LEVEL,
                            use_crossover=USE_STOCHRSI_CROSSOVER,
                            enable_fib_pivot_actions=ENABLE_FIB_PIVOT_ACTIONS,
                            fib_entry_confirm_percent=FIB_ENTRY_CONFIRM_PERCENT,
                            fib_exit_warn_percent=FIB_EXIT_WARN_PERCENT, # Not directly used in entry, but passed
                            fib_exit_action=FIB_EXIT_ACTION, # Not directly used in entry, but passed
                            pivot_support_levels=pivot_support_levels,
                            pivot_resistance_levels=pivot_resistance_levels
                        )
                        for signal_type, signal_price, signal_timestamp, signal_info in signals:
                            if await self._execute_entry(signal_type, signal_price, signal_timestamp, signal_info):
                                self.bot_logger.info(f"{PYRMETHUS_GREEN}Entry order successfully placed. Awaiting position confirmation.{COLOR_RESET}")
                                break # Only take one entry per loop iteration
                    else: # Position already open
                        self.bot_logger.info(f"{PYRMETHUS_BLUE}🚫 Position already open: {self.current_position_side} {SYMBOL}. Checking for exit signals...{COLOR_RESET}")
                        exit_signals = generate_exit_signals(
                            self.klines_df, self.current_position_side,
                            self.active_bull_obs, self.active_bear_obs,
                            stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD,
                            overbought=STOCHRSI_OVERBOUGHT_LEVEL, oversold=STOCHRSI_OVERSOLD_LEVEL,
                            use_crossover=USE_STOCHRSI_CROSSOVER,
                            enable_fib_pivot_actions=ENABLE_FIB_PIVOT_ACTIONS,
                            fib_exit_warn_percent=FIB_EXIT_WARN_PERCENT,
                            fib_exit_action=FIB_EXIT_ACTION,
                            pivot_support_levels=pivot_support_levels,
                            pivot_resistance_levels=pivot_resistance_levels
                        )
                        if exit_signals:
                            for exit_signal in exit_signals:
                                exit_type, exit_price, exit_timestamp, exit_info = exit_signal
                                if await self._execute_exit(exit_type, exit_price, exit_timestamp, exit_info):
                                    self.bot_logger.info(f"{PYRMETHUS_GREEN}Exit order successfully placed. Awaiting position closure confirmation.{COLOR_RESET}")
                                    break # Only take one exit per loop iteration
                        else:
                            self.bot_logger.info(f"{PYRMETHUS_GREY}No explicit exit signals detected from strategy.{COLOR_RESET}")
                            # Dynamic exits are handled in _manage_dynamic_exits, which is called on kline update.
                            # So no explicit call needed here.

                    self.bot_logger.info(f"{PYRMETHUS_ORANGE}Sleeping for {POLLING_INTERVAL_SECONDS} seconds...{COLOR_RESET}")
                    await asyncio.sleep(POLLING_INTERVAL_SECONDS)

            except KeyboardInterrupt:
                self.bot_logger.info(f"{COLOR_YELLOW}Bot stopped by user (KeyboardInterrupt).{COLOR_RESET}")
            except Exception as e:
                log_exception(self.bot_logger, f"Critical error in main loop: {str(e)}", e)
                self.bot_logger.info(f"{COLOR_YELLOW}🔄 Attempting to recover and restart main loop after 10 seconds...{COLOR_RESET}")
                await asyncio.sleep(10) # Pause before attempting to continue loop
            finally:
                # Ensure listener tasks are cancelled on exit
                self.bot_logger.info(f"{COLOR_YELLOW}Cancelling all listener tasks...{COLOR_RESET}")
                for task in listener_tasks:
                    task.cancel()
                await asyncio.gather(*listener_tasks, return_exceptions=True) # Await cancellation
                self.bot_logger.info(f"{COLOR_YELLOW}All listener tasks cancelled and awaited. Bot shutting down.{COLOR_RESET}")

async def main():
    """Entry point for the Pyrmethus Bot."""
    load_dotenv() # Load environment variables from .env file
    bot = PyrmethusBot()
    try:
        await bot.run()
    except Exception as e:
        setup_logging().critical(f"Unhandled exception in main execution: {e}", exc_info=True)
    finally:
        # Final log message for program termination
        setup_logging().info(f"{PYRMETHUS_PURPLE}Pyrmethus's Ultra Scalper Bot has ceased operations.{COLOR_RESET}")


if __name__ == "__main__":
    asyncio.run(main())

```

---

### <span style="color:#FFD700;">⚙️ File: `config.py` (Conceptual Update)</span>

This file centralizes all configurable parameters. Add the new parameters for enhanced features.

```python
# config.py - Configuration for Pyrmethus's Ultra Scalper Bot

import os
from decimal import Decimal

# --- General Bot Settings ---
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
INTERVAL = os.getenv("INTERVAL", "5") # Trading timeframe (e.g., "5", "15", "60", "D")
USDT_AMOUNT_PER_TRADE = Decimal(os.getenv("USDT_AMOUNT_PER_TRADE", "10")) # Amount of USDT to use per trade
CANDLE_FETCH_LIMIT = int(os.getenv("CANDLE_FETCH_LIMIT", "200")) # Number of historical candles to fetch
POLLING_INTERVAL_SECONDS = int(os.getenv("POLLING_INTERVAL_SECONDS", "5")) # How often the bot loop runs

# --- Bybit API Settings ---
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
BYBIT_API_ENDPOINT = os.getenv("BYBIT_API_ENDPOINT", "https://api.bybit.com") # or "https://api-testnet.bybit.com"
BYBIT_CATEGORY = os.getenv("BYBIT_CATEGORY", "linear") # "linear" for USDT Perpetuals, "spot", "inverse"

# --- Indicator Settings ---
# StochRSI
STOCHRSI_K_PERIOD = int(os.getenv("STOCHRSI_K_PERIOD", "14"))
STOCHRSI_D_PERIOD = int(os.getenv("STOCHRSI_D_PERIOD", "3"))
STOCHRSI_OVERBOUGHT_LEVEL = int(os.getenv("STOCHRSI_OVERBOUGHT_LEVEL", "80"))
STOCHRSI_OVERSOLD_LEVEL = int(os.getenv("STOCHRSI_OVERSOLD_LEVEL", "20"))
USE_STOCHRSI_CROSSOVER = os.getenv("USE_STOCHRSI_CROSSOVER", "True").lower() == "true"

# ATR (Average True Range)
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
ATR_MULTIPLIER_SL = Decimal(os.getenv("ATR_MULTIPLIER_SL", "1.5")) # Multiplier for SL (e.g., 1.5 * ATR)
ATR_MULTIPLIER_TP = Decimal(os.getenv("ATR_MULTIPLIER_TP", "3.0")) # Multiplier for TP (e.g., 3.0 * ATR)

# SMA (Simple Moving Average)
SMA_PERIOD = int(os.getenv("SMA_PERIOD", "20"))

# Ehlers Fisher Transform
FISHER_LENGTH = int(os.getenv("FISHER_LENGTH", "9"))

# Ehlers Super Smoother
SUPERSMOOTHER_LENGTH = int(os.getenv("SUPERSMOOTHER_LENGTH", "10"))

# --- Order Block Settings ---
PIVOT_LEFT_BARS = int(os.getenv("PIVOT_LEFT_BARS", "5")) # Bars to the left for pivot identification
PIVOT_RIGHT_BARS = int(os.getenv("PIVOT_RIGHT_BARS", "5")) # Bars to the right for pivot identification
# PIVOT_TOLERANCE_PCT = Decimal(os.getenv("PIVOT_TOLERANCE_PCT", "0.01")) # Not used in current pivot logic, but useful for strict pivots

# --- Fibonacci Pivot Settings ---
ENABLE_FIB_PIVOT_ACTIONS = os.getenv("ENABLE_FIB_PIVOT_ACTIONS", "True").lower() == "true"
PIVOT_TIMEFRAME = os.getenv("PIVOT_TIMEFRAME", "D") # Timeframe for calculating pivots (e.g., "D", "W", "M")
FIB_LEVELS_TO_CALC = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.414, 1.618, 2.0, 2.272, 2.414, 2.618] # Common Fib levels
FIB_NEAREST_COUNT = int(os.getenv("FIB_NEAREST_COUNT", "3")) # How many nearest Fib levels to consider for signals
FIB_ENTRY_CONFIRM_PERCENT = Decimal(os.getenv("FIB_ENTRY_CONFIRM_PERCENT", "0.001")) # Price moves this % past Fib for entry
FIB_EXIT_WARN_PERCENT = Decimal(os.getenv("FIB_EXIT_WARN_PERCENT", "0.002")) # Price moves this % past Fib for exit warning
FIB_EXIT_ACTION = os.getenv("FIB_EXIT_ACTION", "soft") # 'soft' (warning) or 'hard' (exit trade)

# --- Risk Management Settings ---
STOP_LOSS_PCT = Decimal(os.getenv("STOP_LOSS_PCT", "0.005")) # Static Stop Loss Percentage (0.5%)
TAKE_PROFIT_PCT = Decimal(os.getenv("TAKE_PROFIT_PCT", "0.015")) # Static Take Profit Percentage (1.5%)

# Trailing Stop Loss
TRAILING_STOP_ENABLED = os.getenv("TRAILING_STOP_ENABLED", "True").lower() == "true"
TRAILING_STOP_PERCENT = Decimal(os.getenv("TRAILING_STOP_PERCENT", "0.005")) # Percentage below peak for trailing stop (0.5%)
TRAILING_STOP_ACTIVATION_PERCENT = Decimal(os.getenv("TRAILING_STOP_ACTIVATION_PERCENT", "0.01")) # Profit % to activate trailing stop (1%)

# Partial Take Profit
PARTIAL_TAKE_PROFIT_ENABLED = os.getenv("PARTIAL_TAKE_PROFIT_ENABLED", "True").lower() == "true"
# List of (profit_percentage, quantity_percentage_to_take) tuples
PARTIAL_TAKE_PROFIT_LEVELS = [
    (Decimal("0.0075"), Decimal("25")), # Take 25% profit at 0.75% gain
    (Decimal("0.0150"), Decimal("50")), # Take 50% of remaining profit at 1.5% gain
    # Add more levels as needed
]

# --- API Error Handling ---
API_REQUEST_RETRIES = int(os.getenv("API_REQUEST_RETRIES", "5"))
API_BACKOFF_FACTOR = int(os.getenv("API_BACKOFF_FACTOR", "0.5"))

# --- Logging Settings ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper() # DEBUG, INFO, WARNING, ERROR, CRITICAL

```

---

### <span style="color:#00FF00;">🌳 File: `indicators.py` (Conceptual Update)</span>

This file encapsulates all technical indicator calculations and data handling.

```python
# indicators.py - Technical Indicator Calculations and Data Handling for Pyrmethus Bot
import pandas as pd
from decimal import Decimal
from typing import Tuple, Dict, List, Optional
import numpy as np # For rolling window operations, if not using pandas built-in

# Assuming COLOR_RESET, COLOR_RED, COLOR_YELLOW etc. are imported or defined here for logging
from color_codex import COLOR_RESET, COLOR_RED, COLOR_YELLOW, PYRMETHUS_CYAN

# --- Helper Function for Interval Conversion ---
def convert_interval_to_ms(interval: str) -> int:
    """Converts interval string (e.g., '1', '5', '60', 'D') to milliseconds."""
    if interval.isdigit():
        return int(interval) * 60 * 1000 # Convert minutes to milliseconds
    elif interval == 'D':
        return 24 * 60 * 60 * 1000 # 1 day in milliseconds
    elif interval == 'W':
        return 7 * 24 * 60 * 60 * 1000 # 1 week in milliseconds
    elif interval == 'M':
        # This is tricky as months have variable days. For simplicity, use 30 days.
        return 30 * 24 * 60 * 60 * 1000 # 1 month (approx) in milliseconds
    else:
        raise ValueError(f"Unsupported interval: {interval}")

# --- Kline Data Handling ---
def handle_websocket_kline_data(current_df: Optional[pd.DataFrame], message: Dict[str, Any]) -> pd.DataFrame:
    """
    Processes WebSocket kline messages to update the DataFrame.
    Handles both new complete candles and updates to the current incomplete candle.
    """
    if not message or 'data' not in message or not message['data']:
        return current_df

    kline_data = message['data'][0]
    is_closed = kline_data.get('confirm', False)

    new_candle = {
        'timestamp': pd.to_datetime(int(kline_data['start']), unit='ms', utc=True),
        'open': Decimal(kline_data['open']),
        'high': Decimal(kline_data['high']),
        'low': Decimal(kline_data['low']),
        'close': Decimal(kline_data['close']),
        'volume': Decimal(kline_data['volume']),
    }

    new_df = pd.DataFrame([new_candle]).set_index('timestamp')

    if current_df is None or current_df.empty:
        return new_df
    else:
        # Check if the last candle in current_df is the same as the new_candle's timestamp
        if new_candle['timestamp'] in current_df.index:
            # Update existing (incomplete) candle
            current_df.loc[new_candle['timestamp']] = new_candle
        else:
            # Append new candle (implies the previous one was confirmed/closed)
            current_df = pd.concat([current_df, new_df])

        # Optionally, trim old data to manage memory
        # Keep only the last N candles required for indicators + buffer
        # For example, keep CANDLE_FETCH_LIMIT + max_indicator_period candles
        # This needs to be coordinated with config.py
        # current_df = current_df.tail(250) # Example trimming
        return current_df.sort_index() # Ensure chronological order

# --- Indicator Calculations ---

def calculate_stochrsi(df: pd.DataFrame, rsi_period: int = 14, stoch_k_period: int = 14, stoch_d_period: int = 3) -> pd.DataFrame:
    """Calculates StochRSI (Stochastic Relative Strength Index)."""
    if len(df) < rsi_period + stoch_k_period + stoch_d_period:
        # Not enough data for full calculation, return df as is with NaN columns
        df['stoch_rsi_k'] = pd.NA
        df['stoch_rsi_d'] = pd.NA
        return df

    # Convert to float for ta-lib or pandas calculations, then back to Decimal
    closes = df['close'].astype(float)

    # Calculate RSI
    delta = closes.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)

    avg_gain = gain.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()
    avg_loss = loss.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    # Calculate Stochastic of RSI
    lowest_rsi = rsi.rolling(window=stoch_k_period).min()
    highest_rsi = rsi.rolling(window=stoch_k_period).max()

    stoch_rsi_k = 100 * ((rsi - lowest_rsi) / (highest_rsi - lowest_rsi))
    stoch_rsi_d = stoch_rsi_k.rolling(window=stoch_d_period).mean()

    df['stoch_rsi_k'] = stoch_rsi_k.apply(Decimal)
    df['stoch_rsi_d'] = stoch_rsi_d.apply(Decimal)
    return df

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculates Average True Range (ATR)."""
    if len(df) < period:
        return pd.Series([pd.NA] * len(df), index=df.index)

    highs = df['high'].astype(float)
    lows = df['low'].astype(float)
    closes = df['close'].astype(float)

    # True Range (TR)
    tr1 = highs - lows
    tr2 = (highs - closes.shift()).abs()
    tr3 = (lows - closes.shift()).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR (Exponential Moving Average of TR)
    atr = true_range.ewm(span=period, adjust=False, min_periods=period).mean()
    return atr.apply(Decimal)

def calculate_sma(df: pd.DataFrame, length: int = 20) -> pd.Series:
    """Calculates Simple Moving Average (SMA)."""
    if len(df) < length:
        return pd.Series([pd.NA] * len(df), index=df.index)
    return df['close'].astype(float).rolling(window=length).mean().apply(Decimal)

def calculate_ehlers_fisher_transform(df: pd.DataFrame, length: int = 9) -> pd.Series:
    """Calculates Ehlers Fisher Transform."""
    if len(df) < length:
        return pd.Series([pd.NA] * len(df), index=df.index)

    # Convert to float for calculation
    highs = df['high'].astype(float)
    lows = df['low'].astype(float)

    # Calculate highest high and lowest low over the period
    hhv = highs.rolling(window=length).max()
    llv = lows.rolling(window=length).min()

    # Normalize price to a range of -1 to +1
    range_val = hhv - llv
    # Avoid division by zero
    range_val = range_val.replace(0, np.nan) # Replace 0 with NaN
    mid_price = ((df['close'].astype(float) - llv) / range_val) - 0.5
    mid_price = mid_price.replace([np.inf, -np.inf], np.nan).fillna(0) # Handle inf and NaN after division

    # Apply Fisher Transform
    # Limit 'value' to prevent log(0) or log(negative)
    value = 0.33 * mid_price + 0.67 * (pd.Series([0.0] * len(df), index=df.index) if 'prev_value' not in df.columns else df['prev_value'].shift())
    value = value.clip(-0.999, 0.999) # Clip values to avoid log(0) issues

    # Fisher Transform formula
    fisher = 0.5 * np.log((1 + value) / (1 - value)) + 0.5 * (pd.Series([0.0] * len(df), index=df.index) if 'prev_fisher' not in df.columns else df['prev_fisher'].shift())

    # Store previous values for next iteration (this is often handled outside in a stateful manner for live data)
    df['prev_value'] = value
    df['prev_fisher'] = fisher

    return fisher.apply(Decimal)


def calculate_ehlers_super_smoother(df: pd.DataFrame, length: int = 10) -> pd.Series:
    """Calculates Ehlers Super Smoother Filter (2-pole Butterworth filter)."""
    if len(df) < length:
        return pd.Series([pd.NA] * len(df), index=df.index)

    # Convert to float for calculation
    closes = df['close'].astype(float)

    # Constants for 2-pole Butterworth filter
    arg = np.sqrt(2) * np.pi / length
    alpha = np.exp(-arg)
    a1 = np.exp(-np.sqrt(2) * np.pi / length)
    coeff2 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / length)
    coeff3 = -a1**2

    # Initialize output series
    super_smoother = pd.Series(np.nan, index=df.index)

    # Apply filter (iterative calculation)
    # Requires at least 2 previous values, so start from index 2
    for i in range(2, len(closes)):
        super_smoother.iloc[i] = (1 - coeff2 - coeff3) / 2 * (closes.iloc[i] + closes.iloc[i-1]) + \
                                 coeff2 * super_smoother.iloc[i-1] + \
                                 coeff3 * super_smoother.iloc[i-2]

    return super_smoother.apply(Decimal)

def find_pivots(df: pd.DataFrame, left_bars: int, right_bars: int) -> Tuple[pd.Series, pd.Series]:
    """
    Identifies pivot highs and lows based on surrounding bars.
    A pivot high is a bar whose high is the highest among `left_bars` to its left and `right_bars` to its right.
    A pivot low is a bar whose low is the lowest among `left_bars` to its left and `right_bars` to its right.
    """
    if len(df) < left_bars + right_bars + 1:
        # Not enough data for pivot calculation
        return pd.Series(False, index=df.index), pd.Series(False, index=df.index)

    pivot_highs = pd.Series(False, index=df.index)
    pivot_lows = pd.Series(False, index=df.index)

    # Iterate from `left_bars` to `len(df) - right_bars - 1` to ensure full window
    for i in range(left_bars, len(df) - right_bars):
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]

        # Check for Pivot High
        is_pivot_high = True
        for j in range(1, left_bars + 1):
            if df['high'].iloc[i - j] >= current_high:
                is_pivot_high = False
                break
        if is_pivot_high:
            for j in range(1, right_bars + 1):
                if df['high'].iloc[i + j] >= current_high:
                    is_pivot_high = False
                    break
        if is_pivot_high:
            pivot_highs.iloc[i] = True

        # Check for Pivot Low
        is_pivot_low = True
        for j in range(1, left_bars + 1):
            if df['low'].iloc[i - j] <= current_low:
                is_pivot_low = False
                break
        if is_pivot_low:
            for j in range(1, right_bars + 1):
                if df['low'].iloc[i + j] <= current_low:
                    is_pivot_low = False
                    break
        if is_pivot_low:
            pivot_lows.iloc[i] = True

    return pivot_highs, pivot_lows

def calculate_fibonacci_pivot_points(df: pd.DataFrame, levels: List[float] = None) -> Tuple[List[Dict[str, Decimal]], List[Dict[str, Decimal]]]:
    """
    Calculates Fibonacci Pivot Points (P, R1-R3, S1-S3) based on the last complete candle's HLC.
    Expects a DataFrame with at least one complete candle.
    """
    if levels is None:
        # Default Fibonacci levels (from config.py's FIB_LEVELS_TO_CALC)
        levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.414, 1.618, 2.0, 2.272, 2.414, 2.618]

    if df.empty:
        return [], []

    # Use the last candle's HLC for pivot calculation
    last_candle = df.iloc[-1]
    high = last_candle['high']
    low = last_candle['low']
    close = last_candle['close']

    # Calculate Pivot Point (P)
    pivot_point = (high + low + close) / Decimal('3')

    resistance_levels = []
    support_levels = []

    # Fibonacci Resistance and Support Levels
    # R1 = P + (P - S1) = P + (P - (P - (H - L) * 0.382)) = P + (H - L) * 0.382
    # S1 = P - (H - L) * 0.382
    # The traditional Fibonacci pivots are based on the range (High - Low)
    price_range = high - low

    # Common Fibonacci levels for pivots (these are often fixed, not dynamically passed)
    # R3: P + (High - Low)
    # R2: P + (High - Low) * 0.618
    # R1: P + (High - Low) * 0.382
    # S1: P - (High - Low) * 0.382
    # S2: P - (High - Low) * 0.618
    # S3: P - (High - Low)

    # Let's use a more flexible approach based on the `levels` list
    # Assuming levels are relative to the range (H-L) and pivot point.
    # This might need adjustment based on specific Fib pivot methodology.

    # Example: Simple Fibonacci Retracements from a swing High/Low
    # For a general pivot system, it's usually based on the previous period's HLC.
    # We will compute levels relative to the Pivot Point (P) and the range.

    resistance_levels.append({'type': 'P', 'price': pivot_point}) # Pivot Point itself
    support_levels.append({'type': 'P', 'price': pivot_point})

    for level in levels:
        if level == 0 or level == 1: continue # Base levels handled by P and range
        
        # Calculate levels above P (Resistance)
        r_price = pivot_point + (price_range * Decimal(str(level)))
        resistance_levels.append({'type': f'R_{level}', 'price': r_price})

        # Calculate levels below P (Support)
        s_price = pivot_point - (price_range * Decimal(str(level)))
        support_levels.append({'type': f'S_{level}', 'price': s_price})

    # Sort for consistent display/usage
    resistance_levels.sort(key=lambda x: x['price'], reverse=True) # Highest first
    support_levels.sort(key=lambda x: x['price']) # Lowest first

    return resistance_levels, support_levels

```

---

### <span style="color:#FF69B4;">🛡️ File: `strategy.py` (Conceptual Update)</span>

This is where the trading intelligence resides. It will now incorporate Order Blocks and Fibonacci Pivots.

```python
# strategy.py - Trading Signal Generation for Pyrmethus Bot
import pandas as pd
from decimal import Decimal
from typing import List, Dict, Tuple, Any, Optional

# Import necessary types for OrderBlock
from PSG import OrderBlock

# Constants from config (assuming they are passed or imported)
# from config import (
#     STOCHRSI_OVERBOUGHT_LEVEL, STOCHRSI_OVERSOLD_LEVEL, USE_STOCHRSI_CROSSOVER,
#     ENABLE_FIB_PIVOT_ACTIONS, FIB_ENTRY_CONFIRM_PERCENT, FIB_EXIT_WARN_PERCENT, FIB_EXIT_ACTION,
#     FIB_NEAREST_COUNT
# )

# Placeholder for a simple logger
import logging
strategy_logger = logging.getLogger(__name__)

def generate_signals(
    klines_df: pd.DataFrame,
    active_bull_obs: List[OrderBlock],
    active_bear_obs: List[OrderBlock],
    stoch_k_period: int, stoch_d_period: int,
    overbought: int, oversold: int,
    use_crossover: bool,
    enable_fib_pivot_actions: bool,
    fib_entry_confirm_percent: Decimal,
    fib_exit_warn_percent: Decimal, # Also passed, though primarily for exit
    fib_exit_action: str, # Also passed, though primarily for exit
    pivot_support_levels: Dict[str, Decimal],
    pivot_resistance_levels: Dict[str, Decimal]
) -> List[Tuple[str, Decimal, pd.Timestamp, Dict[str, Any]]]:
    """
    Generates entry signals based on multiple indicator confluence,
    Order Blocks, and Fibonacci Pivot points.
    Returns a list of (signal_type, price, timestamp, info_dict) tuples.
    """
    signals = []
    if klines_df.empty or len(klines_df) < max(stoch_k_period, stoch_d_period):
        strategy_logger.debug("Insufficient kline data for signal generation.")
        return signals

    last_candle = klines_df.iloc[-1]
    current_price = last_candle['close']
    last_timestamp = last_candle.name # Timestamp is the index

    stoch_k = last_candle.get('stoch_rsi_k', pd.NA)
    stoch_d = last_candle.get('stoch_rsi_d', pd.NA)
    sma = last_candle.get('sma', pd.NA)
    ehlers_fisher = last_candle.get('ehlers_fisher', pd.NA)
    ehlers_supersmoother = last_candle.get('ehlers_supersmoother', pd.NA)

    # Ensure indicators are not NaN/None
    if pd.isna(stoch_k) or pd.isna(stoch_d) or pd.isna(sma) or pd.isna(ehlers_fisher) or pd.isna(ehlers_supersmoother):
        strategy_logger.debug("One or more indicators are not calculated (NaN). Skipping signal generation.")
        return signals

    # --- StochRSI Logic ---
    stoch_long_signal = False
    stoch_short_signal = False

    if use_crossover:
        # Check for StochRSI K-D crossover in oversold/overbought zones
        prev_stoch_k = klines_df['stoch_rsi_k'].iloc[-2]
        prev_stoch_d = klines_df['stoch_rsi_d'].iloc[-2]

        # Bullish Crossover: K crosses above D in oversold zone
        if stoch_k > stoch_d and prev_stoch_k <= prev_stoch_d and stoch_k < oversold:
            stoch_long_signal = True
            strategy_logger.debug(f"StochRSI Bullish Crossover: K({stoch_k:.2f}) > D({stoch_d:.2f}) in oversold zone.")

        # Bearish Crossover: K crosses below D in overbought zone
        if stoch_k < stoch_d and prev_stoch_k >= prev_stoch_d and stoch_k > overbought:
            stoch_short_signal = True
            strategy_logger.debug(f"StochRSI Bearish Crossover: K({stoch_k:.2f}) < D({stoch_d:.2f}) in overbought zone.")
    else:
        # Simple overbought/oversold entry
        if stoch_k < oversold and stoch_d < oversold:
            stoch_long_signal = True
            strategy_logger.debug(f"StochRSI Oversold: K({stoch_k:.2f}), D({stoch_d:.2f}).")
        if stoch_k > overbought and stoch_d > overbought:
            stoch_short_signal = True
            strategy_logger.debug(f"StochRSI Overbought: K({stoch_k:.2f}), D({stoch_d:.2f}).")

    # --- Trend Filtering (using SMA) ---
    # Only take long signals if price is above SMA, and short if below SMA
    long_trend_ok = current_price > sma
    short_trend_ok = current_price < sma
    strategy_logger.debug(f"Current Price: {current_price:.4f}, SMA: {sma:.4f}. Long Trend OK: {long_trend_ok}, Short Trend OK: {short_trend_ok}")


    # --- Order Block Confluence ---
    ob_long_confluence = False
    ob_short_confluence = False

    # Check if price is interacting with active bullish OBs for long signals
    for ob in active_bull_obs:
        # If price is near the bottom of a bullish OB (potential support)
        if current_price >= ob['bottom'] and current_price <= ob['top']: # Price is inside OB
            ob_long_confluence = True
            strategy_logger.debug(f"Price {current_price:.4f} inside Bullish OB {ob['id']} ({ob['bottom']:.4f}-{ob['top']:.4f}).")
            break # Found one, good enough for confluence

    # Check if price is interacting with active bearish OBs for short signals
    for ob in active_bear_obs:
        # If price is near the top of a bearish OB (potential resistance)
        if current_price >= ob['bottom'] and current_price <= ob['top']: # Price is inside OB
            ob_short_confluence = True
            strategy_logger.debug(f"Price {current_price:.4f} inside Bearish OB {ob['id']} ({ob['bottom']:.4f}-{ob['top']:.4f}).")
            break

    # --- Fibonacci Pivot Confluence ---
    fib_long_confluence = False
    fib_short_confluence = False

    if enable_fib_pivot_actions:
        # Check for price near support levels for long entries
        for level_type, level_price in pivot_support_levels.items():
            if level_type == 'P': continue # Pivot Point itself
            # Price slightly above support level (confirming bounce)
            if current_price > level_price and current_price <= level_price * (Decimal('1') + fib_entry_confirm_percent):
                fib_long_confluence = True
                strategy_logger.debug(f"Price {current_price:.4f} near Fibonacci Support {level_type} ({level_price:.4f}).")
                break
        # Check for price near resistance levels for short entries
        for level_type, level_price in pivot_resistance_levels.items():
            if level_type == 'P': continue
            # Price slightly below resistance level (confirming rejection)
            if current_price < level_price and current_price >= level_price * (Decimal('1') - fib_entry_confirm_percent):
                fib_short_confluence = True
                strategy_logger.debug(f"Price {current_price:.4f} near Fibonacci Resistance {level_type} ({level_price:.4f}).")
                break

    # --- Ehlers Fisher Transform & Super Smoother Confluence (Example) ---
    # Fisher can indicate reversals, Super Smoother for trend direction
    ehlers_long_confluence = False
    ehlers_short_confluence = False

    # Example: Long when Fisher crosses above its signal line (e.g., 0) and Super Smoother is rising
    # (Assuming a signal line for Fisher, or just its value)
    if ehlers_fisher > Decimal('0.0') and klines_df['ehlers_fisher'].iloc[-2] <= Decimal('0.0') and \
       ehlers_supersmoother > klines_df['ehlers_supersmoother'].iloc[-2]:
        ehlers_long_confluence = True
        strategy_logger.debug(f"Ehlers Long Confluence: Fisher={ehlers_fisher:.2f}, SuperSmoother rising.")

    # Example: Short when Fisher crosses below its signal line (e.g., 0) and Super Smoother is falling
    if ehlers_fisher < Decimal('0.0') and klines_df['ehlers_fisher'].iloc[-2] >= Decimal('0.0') and \
       ehlers_supersmoother < klines_df['ehlers_supersmoother'].iloc[-2]:
        ehlers_short_confluence = True
        strategy_logger.debug(f"Ehlers Short Confluence: Fisher={ehlers_fisher:.2f}, SuperSmoother falling.")


    # --- Combined Signal Logic ---
    # Example: Require StochRSI + Trend + (OB or Fib or Ehlers)
    if stoch_long_signal and long_trend_ok and (ob_long_confluence or fib_long_confluence or ehlers_long_confluence):
        signals.append(("buy", current_price, last_timestamp, {
            "stoch_k": stoch_k, "stoch_d": stoch_d, "stoch_type": "long_signal",
            "reason": "StochRSI+Trend+Confluence",
            "ob_confluence": ob_long_confluence, "fib_confluence": fib_long_confluence,
            "ehlers_confluence": ehlers_long_confluence
        }))

    if stoch_short_signal and short_trend_ok and (ob_short_confluence or fib_short_confluence or ehlers_short_confluence):
        signals.append(("sell", current_price, last_timestamp, {
            "stoch_k": stoch_k, "stoch_d": stoch_d, "stoch_type": "short_signal",
            "reason": "StochRSI+Trend+Confluence",
            "ob_confluence": ob_short_confluence, "fib_confluence": fib_short_confluence,
            "ehlers_confluence": ehlers_short_confluence
        }))

    return signals

def generate_exit_signals(
    klines_df: pd.DataFrame,
    current_position_side: Optional[str],
    active_bull_obs: List[OrderBlock],
    active_bear_obs: List[OrderBlock],
    stoch_k_period: int, stoch_d_period: int,
    overbought: int, oversold: int,
    use_crossover: bool,
    enable_fib_pivot_actions: bool,
    fib_exit_warn_percent: Decimal,
    fib_exit_action: str,
    pivot_support_levels: Dict[str, Decimal],
    pivot_resistance_levels: Dict[str, Decimal]
) -> List[Tuple[str, Decimal, pd.Timestamp, Dict[str, Any]]]:
    """
    Generates exit signals based on indicator reversals, Order Blocks,
    and Fibonacci Pivot points, tailored to the current position side.
    Returns a list of (exit_type, price, timestamp, info_dict) tuples.
    """
    exit_signals = []
    if klines_df.empty or len(klines_df) < max(stoch_k_period, stoch_d_period) or current_position_side is None:
        strategy_logger.debug("Insufficient kline data or no open position for exit signal generation.")
        return exit_signals

    last_candle = klines_df.iloc[-1]
    current_price = last_candle['close']
    last_timestamp = last_candle.name

    stoch_k = last_candle.get('stoch_rsi_k', pd.NA)
    stoch_d = last_candle.get('stoch_rsi_d', pd.NA)
    sma = last_candle.get('sma', pd.NA) # For trend reversal
    ehlers_fisher = last_candle.get('ehlers_fisher', pd.NA)
    ehlers_supersmoother = last_candle.get('ehlers_supersmoother', pd.NA)

    if pd.isna(stoch_k) or pd.isna(stoch_d) or pd.isna(sma) or pd.isna(ehlers_fisher) or pd.isna(ehlers_supersmoother):
        strategy_logger.debug("One or more indicators are not calculated (NaN). Skipping exit signal generation.")
        return exit_signals

    # --- StochRSI Exit Logic ---
    stoch_exit_long = False
    stoch_exit_short = False

    if use_crossover:
        prev_stoch_k = klines_df['stoch_rsi_k'].iloc[-2]
        prev_stoch_d = klines_df['stoch_rsi_d'].iloc[-2]

        # For Long position: K crosses below D (bearish crossover) or enters overbought
        if current_position_side == 'Buy':
            if (stoch_k < stoch_d and prev_stoch_k >= prev_stoch_d) or (stoch_k > overbought and stoch_d > overbought):
                stoch_exit_long = True
                strategy_logger.debug(f"StochRSI Exit Long: K({stoch_k:.2f}) < D({stoch_d:.2f}) crossover or overbought.")

        # For Short position: K crosses above D (bullish crossover) or enters oversold
        elif current_position_side == 'Sell':
            if (stoch_k > stoch_d and prev_stoch_k <= prev_stoch_d) or (stoch_k < oversold and stoch_d < oversold):
                stoch_exit_short = True
                strategy_logger.debug(f"StochRSI Exit Short: K({stoch_k:.2f}) > D({stoch_d:.2f}) crossover or oversold.")
    else:
        # Simple overbought/oversold exit
        if current_position_side == 'Buy' and stoch_k > overbought and stoch_d > overbought:
            stoch_exit_long = True
            strategy_logger.debug(f"StochRSI Exit Long (Overbought): K({stoch_k:.2f}), D({stoch_d:.2f}).")
        elif current_position_side == 'Sell' and stoch_k < oversold and stoch_d < oversold:
            stoch_exit_short = True
            strategy_logger.logger.debug(f"StochRSI Exit Short (Oversold): K({stoch_k:.2f}), D({stoch_d:.2f}).")

    # --- Trend Reversal / Confluence for Exit (e.g., price crosses SMA) ---
    trend_exit_long = False
    trend_exit_short = False

    if current_position_side == 'Buy' and current_price < sma:
        trend_exit_long = True
        strategy_logger.debug(f"Trend Exit Long: Price ({current_price:.4f}) crossed below SMA ({sma:.4f}).")
    elif current_position_side == 'Sell' and current_price > sma:
        trend_exit_short = True
        strategy_logger.debug(f"Trend Exit Short: Price ({current_price:.4f}) crossed above SMA ({sma:.4f}).")

    # --- Order Block Exit Logic ---
    ob_exit_long = False
    ob_exit_short = False

    # For Long position: Price enters a bearish OB or violates a bullish OB
    if current_position_side == 'Buy':
        for ob in active_bear_obs: # Price hitting resistance from bearish OB
            if current_price >= ob['bottom'] and current_price <= ob['top']:
                ob_exit_long = True
                strategy_logger.debug(f"OB Exit Long: Price {current_price:.4f} hit Bearish OB {ob['id']}.")
                break
        # Also check if any *active* bullish OB that supported entry is now violated
        # This is handled by PSG.py's OB management, so we just need to react if it happens.
        # But for exit, we usually look for resistance or violation of support.

    # For Short position: Price enters a bullish OB or violates a bearish OB
    elif current_position_side == 'Sell':
        for ob in active_bull_obs: # Price hitting support from bullish OB
            if current_price >= ob['bottom'] and current_price <= ob['top']:
                ob_exit_short = True
                strategy_logger.debug(f"OB Exit Short: Price {current_price:.4f} hit Bullish OB {ob['id']}.")
                break

    # --- Fibonacci Pivot Exit Logic ---
    fib_exit_long = False
    fib_exit_short = False

    if enable_fib_pivot_actions:
        # For Long position: Price approaches or crosses resistance levels
        if current_position_side == 'Buy':
            for level_type, level_price in pivot_resistance_levels.items():
                # Price is close to or crossed above a resistance level
                if current_price >= level_price and current_price <= level_price * (Decimal('1') + fib_exit_warn_percent):
                    fib_exit_long = True
                    strategy_logger.debug(f"Fib Exit Long: Price {current_price:.4f} near Fibonacci Resistance {level_type} ({level_price:.4f}).")
                    break
        # For Short position: Price approaches or crosses support levels
        elif current_position_side == 'Sell':
            for level_type, level_price in pivot_support_levels.items():
                # Price is close to or crossed below a support level
                if current_price <= level_price and current_price >= level_price * (Decimal('1') - fib_exit_warn_percent):
                    fib_exit_short = True
                    strategy_logger.debug(f"Fib Exit Short: Price {current_price:.4f} near Fibonacci Support {level_type} ({level_price:.4f}).")
                    break

    # --- Ehlers Fisher / Super Smoother Exit Logic (Example) ---
    ehlers_exit_long = False
    ehlers_exit_short = False

    # For Long position: Fisher crosses below 0 or Super Smoother turns down
    if current_position_side == 'Buy' and ehlers_fisher < Decimal('0.0') and klines_df['ehlers_fisher'].iloc[-2] >= Decimal('0.0'):
        ehlers_exit_long = True
        strategy_logger.debug(f"Ehlers Exit Long: Fisher crossed below 0.")
    # For Short position: Fisher crosses above 0 or Super Smoother turns up
    elif current_position_side == 'Sell' and ehlers_fisher > Decimal('0.0') and klines_df['ehlers_fisher'].iloc[-2] <= Decimal('0.0'):
        ehlers_exit_short = True
        strategy_logger.debug(f"Ehlers Exit Short: Fisher crossed above 0.")

    # --- Combined Exit Logic ---
    # Exit if any strong reversal signal, or price hits OB/Fib resistance/support
    if current_position_side == 'Buy':
        if stoch_exit_long or trend_exit_long or ob_exit_long or fib_exit_long or ehlers_exit_long:
            exit_signals.append(("sell", current_price, last_timestamp, {
                "stoch_k": stoch_k, "stoch_d": stoch_d, "stoch_type": "exit_long",
                "reason": "Combined Exit Trigger",
                "stoch_trigger": stoch_exit_long, "trend_trigger": trend_exit_long,
                "ob_trigger": ob_exit_long, "fib_trigger": fib_exit_long,
                "ehlers_trigger": ehlers_exit_long
            }))
    elif current_position_side == 'Sell':
        if stoch_exit_short or trend_exit_short or ob_exit_short or fib_exit_short or ehlers_exit_short:
            exit_signals.append(("buy", current_price, last_timestamp, {
                "stoch_k": stoch_k, "stoch_d": stoch_d, "stoch_type": "exit_short",
                "reason": "Combined Exit Trigger",
                "stoch_trigger": stoch_exit_short, "trend_trigger": trend_exit_short,
                "ob_trigger": ob_exit_short, "fib_trigger": fib_exit_short,
                "ehlers_trigger": ehlers_exit_short
            }))

    return exit_signals

```

---

### <span style="color:#FF0000;">🎨 File: `bot_ui.py` (Conceptual Update)</span>

Enhance the display for a richer visual experience in the terminal.

```python
# bot_ui.py - Terminal User Interface for Pyrmethus Bot
import pandas as pd
from decimal import Decimal
from typing import List, Dict, Any, Optional
import os

# Import Color Codex
from color_codex import (
    COLOR_RESET, COLOR_BOLD, COLOR_DIM,
    COLOR_RED, COLOR_GREEN, COLOR_YELLOW, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN,
    PYRMETHUS_GREEN, PYRMETHUS_BLUE, PYRMETHUS_PURPLE, PYRMETHUS_ORANGE, PYRMETHUS_GREY
)
from PSG import OrderBlock # Import OrderBlock type

def clear_terminal():
    """Clears the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def display_market_info(
    klines_df: pd.DataFrame,
    current_price: Decimal,
    symbol: str,
    resistance_levels: List[Decimal],
    support_levels: List[Decimal],
    logger: Any, # Logger object
    active_bull_obs: List[OrderBlock],
    active_bear_obs: List[OrderBlock],
    inventory: Decimal,
    entry_price: Decimal,
    unrealized_pnl: Decimal
):
    """
    Displays current market information, indicator values, and bot state
    in a clear, colorful, and concise format.
    """
    clear_terminal() # Keep the display clean

    logger.info(f"{PYRMETHUS_PURPLE}{COLOR_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━ Pyrmethus Bot Status ━━━━━━━━━━━━━━━━━━━━━━━━━━━━{COLOR_RESET}")

    # --- Market Overview ---
    logger.info(f"{PYRMETHUS_BLUE}📊 Market Overview:{COLOR_RESET}")
    logger.info(f"  Symbol: {COLOR_BOLD}{symbol}{COLOR_RESET} | Current Price: {PYRMETHUS_GREEN}{current_price:.4f}{COLOR_RESET}")
    logger.info(f"  Last Candle Close: {klines_df['close'].iloc[-1]:.4f} (Time: {klines_df.index[-1].strftime('%H:%M:%S')})")

    # --- Position Details ---
    logger.info(f"\n{PYRMETHUS_BLUE}💼 Position Details:{COLOR_RESET}")
    if abs(inventory) > Decimal('0'):
        side = "LONG" if inventory > Decimal('0') else "SHORT"
        pnl_color = PYRMETHUS_GREEN if unrealized_pnl >= Decimal('0') else COLOR_RED
        logger.info(f"  Status: {COLOR_GREEN}OPEN {side}{COLOR_RESET}")
        logger.info(f"  Size: {COLOR_BOLD}{abs(inventory):.4f}{COLOR_RESET} {symbol}")
        logger.info(f"  Entry Price: {entry_price:.4f}")
        logger.info(f"  Unrealized PnL: {pnl_color}{unrealized_pnl:.4f}{COLOR_RESET}")
    else:
        logger.info(f"  Status: {COLOR_GREY}FLAT (No open position){COLOR_RESET}")

    # --- Indicator Values ---
    logger.info(f"\n{PYRMETHUS_BLUE}📈 Indicator Readings:{COLOR_RESET}")
    if not klines_df.empty:
        last_candle = klines_df.iloc[-1]
        stoch_k = last_candle.get('stoch_rsi_k', pd.NA)
        stoch_d = last_candle.get('stoch_rsi_d', pd.NA)
        atr = last_candle.get('atr', pd.NA)
        sma = last_candle.get('sma', pd.NA)
        fisher = last_candle.get('ehlers_fisher', pd.NA)
        supersmoother = last_candle.get('ehlers_supersmoother', pd.NA)

        logger.info(f"  StochRSI (K/D): {stoch_k:.2f} / {stoch_d:.2f}")
        logger.info(f"  ATR: {atr:.4f}")
        logger.info(f"  SMA: {sma:.4f}")
        logger.info(f"  Ehlers Fisher: {fisher:.2f}")
        logger.info(f"  Ehlers Super Smoother: {supersmoother:.4f}")
    else:
        logger.info("  Indicators not yet available.")

    # --- Key Price Levels (Pivots & OBs) ---
    logger.info(f"\n{PYRMETHUS_BLUE}🎯 Key Price Levels:{COLOR_RESET}")
    if resistance_levels:
        res_str = ", ".join([f"{level:.4f}" for level in sorted(resistance_levels, reverse=True)])
        logger.info(f"  Resistance (Fib): {COLOR_RED}{res_str}{COLOR_RESET}")
    if support_levels:
        sup_str = ", ".join([f"{level:.4f}" for level in sorted(support_levels)])
        logger.info(f"  Support (Fib): {PYRMETHUS_GREEN}{sup_str}{COLOR_RESET}")

    if active_bull_obs:
        logger.info(f"  Active Bullish OBs: {COLOR_GREEN}" + ", ".join([f"{ob['bottom']:.4f}-{ob['top']:.4f}" for ob in active_bull_obs]) + COLOR_RESET)
    if active_bear_obs:
        logger.info(f"  Active Bearish OBs: {COLOR_RED}" + ", ".join([f"{ob['bottom']:.4f}-{ob['top']:.4f}" for ob in active_bear_obs]) + COLOR_RESET)

    logger.info(f"{PYRMETHUS_PURPLE}{COLOR_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{COLOR_RESET}\n")

```

---

### <span style="color:#008080;">📊 File: `trade_metrics.py` (Conceptual Update)</span>

Add persistence for trade history.

```python
# trade_metrics.py - Trade Metric Tracking and Analysis
import pandas as pd
from decimal import Decimal
from typing import Dict, Any, Optional
import json
import os
import datetime

class TradeMetrics:
    """
    Tracks and calculates various trade metrics.
    Includes persistence to a JSON file.
    """
    def __init__(self, filename: str = 'trade_history.json'):
        self.trade_history = []
        self.filename = filename
        self._load_trade_history()

    def _load_trade_history(self):
        """Loads trade history from a JSON file."""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    raw_data = json.load(f)
                    # Convert Decimal strings back to Decimal objects
                    self.trade_history = [self._convert_to_decimals(trade) for trade in raw_data]
            except json.JSONDecodeError:
                print(f"Warning: Could not decode {self.filename}. Starting with empty history.")
                self.trade_history = []
        else:
            self.trade_history = []

    def _save_trade_history(self):
        """Saves trade history to a JSON file."""
        # Convert Decimal objects to strings for JSON serialization
        serializable_history = [self._convert_to_strings(trade) for trade in self.trade_history]
        with open(self.filename, 'w') as f:
            json.dump(serializable_history, f, indent=4)

    def _convert_to_decimals(self, obj):
        """Recursively converts string representations of Decimals back to Decimal objects."""
        if isinstance(obj, dict):
            return {k: self._convert_to_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_to_decimals(elem) for elem in obj]
        elif isinstance(obj, str) and self._is_decimal_string(obj):
            try:
                return Decimal(obj)
            except Exception:
                return obj # Not a valid decimal string
        return obj

    def _convert_to_strings(self, obj):
        """Recursively converts Decimal objects to string representations."""
        if isinstance(obj, dict):
            return {k: self._convert_to_strings(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_to_strings(elem) for elem in obj]
        elif isinstance(obj, Decimal):
            return str(obj)
        return obj

    def _is_decimal_string(self, s: str) -> bool:
        """Checks if a string can be converted to a Decimal."""
        try:
            Decimal(s)
            return True
        except Exception:
            return False

    def calculate_fee(self, quantity: Decimal, price: Decimal, is_maker: bool = True) -> Decimal:
        """Calculates approximate trading fees. Use actual fee rates from Bybit."""
        # Example Bybit fees: Maker 0.02%, Taker 0.055% for USDT Perpetuals
        fee_rate = Decimal('0.0002') if is_maker else Decimal('0.00055')
        return quantity * price * fee_rate

    def record_trade(
        self,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: Decimal,
        side: str, # 'Buy' for long, 'Sell' for short
        entry_fee: Decimal,
        exit_fee: Decimal,
        timestamp: datetime.datetime
    ):
        """Records a completed trade."""
        if side == 'Buy': # Long position
            gross_pnl = (exit_price - entry_price) * quantity
        elif side == 'Sell': # Short position
            gross_pnl = (entry_price - exit_price) * quantity
        else:
            gross_pnl = Decimal('0')

        net_pnl = gross_pnl - entry_fee - exit_fee
        pnl_percentage = (net_pnl / (entry_price * quantity)) * Decimal('100') if entry_price * quantity > 0 else Decimal('0')

        trade = {
            "timestamp": timestamp.isoformat(),
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": quantity,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "pnl_percentage": pnl_percentage,
            "entry_fee": entry_fee,
            "exit_fee": exit_fee,
            "profit": net_pnl > 0
        }
        self.trade_history.append(trade)
        self._save_trade_history()
        print(f"Trade recorded: {trade}") # For immediate feedback

    def get_trade_statistics(self) -> Dict[str, Any]:
        """Calculates and returns overall trade statistics."""
        if not self.trade_history:
            return {
                "total_trades": 0,
                "total_net_pnl": Decimal('0'),
                "total_gross_pnl": Decimal('0'),
                "total_fees": Decimal('0'),
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate_pct": Decimal('0'),
                "avg_win_pnl": Decimal('0'),
                "avg_loss_pnl": Decimal('0'),
                "avg_pnl_per_trade": Decimal('0'),
                "largest_win": Decimal('0'),
                "largest_loss": Decimal('0'),
            }

        total_net_pnl = sum(trade['net_pnl'] for trade in self.trade_history)
        total_gross_pnl = sum(trade['gross_pnl'] for trade in self.trade_history)
        total_fees = sum(trade['entry_fee'] + trade['exit_fee'] for trade in self.trade_history)
        winning_trades = [trade for trade in self.trade_history if trade['profit']]
        losing_trades = [trade for trade in self.trade_history if not trade['profit']]

        total_trades = len(self.trade_history)
        win_rate_pct = (Decimal(len(winning_trades)) / Decimal(total_trades)) * Decimal('100') if total_trades > 0 else Decimal('0')

        avg_win_pnl = sum(trade['net_pnl'] for trade in winning_trades) / Decimal(len(winning_trades)) if winning_trades else Decimal('0')
        avg_loss_pnl = sum(trade['net_pnl'] for trade in losing_trades) / Decimal(len(losing_trades)) if losing_trades else Decimal('0')

        avg_pnl_per_trade = total_net_pnl / Decimal(total_trades) if total_trades > 0 else Decimal('0')

        largest_win = max(trade['net_pnl'] for trade in winning_trades) if winning_trades else Decimal('0')
        largest_loss = min(trade['net_pnl'] for trade in losing_trades) if losing_trades else Decimal('0')

        return {
            "total_trades": total_trades,
            "total_net_pnl": total_net_pnl,
            "total_gross_pnl": total_gross_pnl,
            "total_fees": total_fees,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate_pct": win_rate_pct,
            "avg_win_pnl": avg_win_pnl,
            "avg_loss_pnl": avg_loss_pnl,
            "avg_pnl_per_trade": avg_pnl_per_trade,
            "largest_win": largest_win,
            "largest_loss": largest_loss,
        }

```

---

### <span style="color:#FFFF00;">🛠️ File: `utils.py` (Conceptual Update)</span>

A utility file for helper functions.

```python
# utils.py - General utility functions for Pyrmethus Bot
from decimal import Decimal

def calculate_order_quantity(usdt_amount: Decimal, current_price: Decimal, min_qty: Decimal, qty_step: Decimal) -> Decimal:
    """
    Calculates the order quantity in crypto units, respecting minimum quantity
    and quantity step size.
    """
    if current_price <= 0:
        return Decimal('0')

    raw_quantity = usdt_amount / current_price

    # Adjust to meet min_qty
    if raw_quantity < min_qty:
        return Decimal('0') # Or return min_qty if that's preferred

    # Adjust to meet qty_step
    # Divide by step, floor, then multiply back by step
    stepped_quantity = (raw_quantity // qty_step) * qty_step

    # Ensure it's not less than min_qty after stepping
    if stepped_quantity < min_qty:
        return min_qty # If stepping makes it too small, just use min_qty if possible

    return stepped_quantity

def convert_interval_to_ms(interval: str) -> int:
    """Converts interval string (e.g., '1', '5', '60', 'D') to milliseconds."""
    if interval.isdigit():
        return int(interval) * 60 * 1000 # Convert minutes to milliseconds
    elif interval == 'D':
        return 24 * 60 * 60 * 1000 # 1 day in milliseconds
    elif interval == 'W':
        return 7 * 24 * 60 * 60 * 1000 # 1 week in milliseconds
    elif interval == 'M':
        # This is tricky as months have variable days. For simplicity, use 30 days.
        return 30 * 24 * 60 * 60 * 1000 # 1 month (approx) in milliseconds
    else:
        raise ValueError(f"Unsupported interval: {interval}")

```

---

### <span style="color:#FFA500;">🌈 File: `color_codex.py` (Ensure Exists)</span>

This file should contain your color definitions.

```python
# color_codex.py - Pyrmethus's Color Codex for Terminal Output

# Standard ANSI colors
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_DIM = "\033[2m"
COLOR_RED = "\033[31m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_BLUE = "\033[34m"
COLOR_MAGENTA = "\033[35m"
COLOR_CYAN = "\033[36m"
COLOR_WHITE = "\033[37m"

# Pyrmethus's Custom Colors (adjust RGB values as desired)
# Using 256-color escape codes: \033[38;5;<color_code>m
PYRMETHUS_GREEN = "\033[38;5;118m" # A vibrant, mystical green
PYRMETHUS_BLUE = "\033[38;5;63m"  # A deep, magical blue
PYRMETHUS_PURPLE = "\033[38;5;129m" # An enchanting purple
PYRMETHUS_ORANGE = "\033[38;5;208m" # A fiery, energetic orange
PYRMETHUS_GREY = "\033[38;5;242m"  # A subtle, grounding grey

```

---

### <span style="color:#800080;">📝 File: `.env` (Example Configuration)</span>

Create a `.env` file in the same directory as `PSG.py` to store your API keys and secrets. **Never commit this file to version control.**

```
BYBIT_API_KEY=YOUR_BYBIT_API_KEY
BYBIT_API_SECRET=YOUR_BYBIT_API_SECRET
BYBIT_API_ENDPOINT=https://api-testnet.bybit.com # Use https://api.bybit.com for live trading

SYMBOL=BTCUSDT
INTERVAL=5
USDT_AMOUNT_PER_TRADE=10
CANDLE_FETCH_LIMIT=200
POLLING_INTERVAL_SECONDS=5

# Indicator Settings
STOCHRSI_K_PERIOD=14
STOCHRSI_D_PERIOD=3
STOCHRSI_OVERBOUGHT_LEVEL=80
STOCHRSI_OVERSOLD_LEVEL=20
USE_STOCHRSI_CROSSOVER=True

ATR_PERIOD=14
ATR_MULTIPLIER_SL=1.5
ATR_MULTIPLIER_TP=3.0

SMA_PERIOD=20
FISHER_LENGTH=9
SUPERSMOOTHER_LENGTH=10

# Order Block Settings
PIVOT_LEFT_BARS=5
PIVOT_RIGHT_BARS=5

# Fibonacci Pivot Settings
ENABLE_FIB_PIVOT_ACTIONS=True
PIVOT_TIMEFRAME=D # Use D for daily, W for weekly, M for monthly
FIB_ENTRY_CONFIRM_PERCENT=0.001
FIB_EXIT_WARN_PERCENT=0.002
FIB_EXIT_ACTION=soft # 'soft' for warning, 'hard' for immediate exit

# Risk Management Settings
STOP_LOSS_PCT=0.005 # 0.5%
TAKE_PROFIT_PCT=0.015 # 1.5%

TRAILING_STOP_ENABLED=True
TRAILING_STOP_PERCENT=0.005 # 0.5% trailing from peak
TRAILING_STOP_ACTIVATION_PERCENT=0.01 # Activate after 1% profit

PARTIAL_TAKE_PROFIT_ENABLED=True
# Format: (profit_percentage, quantity_percentage_to_take)
# Example: Take 25% of position at 0.75% profit, then 50% of remaining at 1.5% profit
PARTIAL_TAKE_PROFIT_LEVELS="0.0075:25,0.0150:50" # String representation for .env, parse in config.py if needed

LOG_LEVEL=INFO
```

---

### <span style="color:#8A2BE2;">📚 Coding Codex Wisdom (Explanation of Enhancements)</span>

1.  **Decimal Precision (`getcontext().prec = 50`):** Increased the global precision for `Decimal` operations. This is paramount in financial applications to avoid floating-point inaccuracies that can lead to significant discrepancies over many trades.
2.  **Order Block (OB) Management:**
    *   **Refined Identification:** `_identify_and_manage_order_blocks` now explicitly uses the *second-to-last* candle (the last *complete* one) for pivot identification, ensuring confirmed pivots.
    *   **Robust Tracking:** OBs are managed more carefully for violation (price closing beyond boundaries) and extension (OB remaining active as price moves without violating).
    *   **Memory Management:** Active OB lists are pruned to `10` most recent active OBs to prevent excessive memory usage, crucial for Termux.
    *   **Integration:** The `generate_signals` and `generate_exit_signals` (in `strategy.py`) now explicitly receive and use `active_bull_obs` and `active_bear_obs` for confluence.
3.  **Advanced Fibonacci Pivot Points:**
    *   **Correct Timeframe Logic:** The bot now fetches the *previous complete candle* for the specified `PIVOT_TIMEFRAME` (e.g., previous day's HLC for `D` interval). This is the correct approach for traditional Fibonacci pivot calculations.
    *   **Dynamic Levels:** `FIB_LEVELS_TO_CALC` in `config.py` allows flexible definition of Fibonacci levels.
    *   **Confluence:** `generate_signals` and `generate_exit_signals` integrate these levels to find entry/exit points near significant support/resistance.
4.  **Enhanced Indicator Integration:**
    *   **Configurable Periods:** SMA, Ehlers Fisher, and Ehlers Super Smoother periods are now defined in `config.py`, promoting flexibility and experimentation.
    *   **Robust Calculations:** Added checks for `NaN` values and insufficient data in indicator functions.
    *   **New Confluence:** `strategy.py` now includes example logic for using Fisher Transform and Super Smoother as additional confluence factors.
5.  **Dynamic Risk Management:**
    *   **Trailing Stop Loss:** Implemented logic to move the Stop Loss automatically as the trade moves into profit, protecting gains. It activates after a configurable `TRAILING_STOP_ACTIVATION_PERCENT` profit.
    *   **Partial Take Profit:** Allows the bot to close portions of the position at different profit targets (`PARTIAL_TAKE_PROFIT_LEVELS`), reducing risk and securing profits incrementally.
    *   **Centralized TP/SL Update:** `_update_take_profit_stop_loss` is now responsible for setting both static and dynamic TP/SL on the exchange, consolidating order management.
6.  **Robust Position Handling:**
    *   `_handle_position_update` is the single source of truth for position state, driven by WebSocket updates. It correctly handles position opening, updates, and closure, including recording final trade metrics.
    *   Initialization now checks for existing open positions at startup.
7.  **Improved UI (`bot_ui.py`):**
    *   The `display_market_info` function is enhanced to provide a more comprehensive and visually appealing overview, including active Order Blocks, Fibonacci levels, and detailed position information (PnL, size, entry price).
    *   `clear_terminal()` is used for a cleaner, dynamic display.
8.  **Trade Metrics Persistence (`trade_metrics.py`):**
    *   `TradeMetrics` now saves and loads trade history to/from a `trade_history.json` file, ensuring that your bot's performance data is not lost on restart. `Decimal` objects are correctly handled during JSON serialization/deserialization.
9.  **Modular Design:**
    *   Separation of concerns is maintained with distinct files for configuration, indicators, strategy, UI, and utilities.
    *   `utils.py` added for general helper functions like `calculate_order_quantity` and `convert_interval_to_ms`.
10. **Error Handling & Logging:**
    *   More specific error logging and graceful handling of API failures or insufficient data.
    *   `log_exception` is used to capture detailed traceback for critical errors.

This upgraded architecture provides a more intelligent, robust, and observable trading system, ready to navigate the markets with Pyrmethus's guidance!
