# PSG.py - Pyrmethus's Ultra Scalper Bot (Upgraded)
import os
import asyncio
import pandas as pd
import logging
from typing import Any, Dict, List, Tuple, Union, Optional, Callable
from dotenv import load_dotenv
from decimal import Decimal, getcontext
from algobots_types import OrderBlock # Import OrderBlock from new types scroll

# --- Set Decimal Precision ---
# High precision is crucial for financial calculations.
getcontext().prec = 38

# --- Pyrmethus's Color Codex ---
from color_codex import (
    COLOR_RESET, COLOR_BOLD, COLOR_DIM,
    COLOR_RED, COLOR_GREEN, COLOR_YELLOW, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN,
    PYRMETHUS_GREEN, PYRMETHUS_BLUE, PYRMETHUS_PURPLE, PYRMETHUS_ORANGE, PYRMETHUS_GREY
)

# --- Import Configuration and Indicator Logic ---
# These imports define the bot's behavior and analytical tools.
from config import (
    SYMBOL, INTERVAL, USDT_AMOUNT_PER_TRADE, PIVOT_LEFT_BARS, PIVOT_RIGHT_BARS, PIVOT_TOLERANCE_PCT,
    STOCHRSI_K_PERIOD, STOCHRSI_D_PERIOD, STOCHRSI_OVERBOUGHT_LEVEL,
    STOCHRSI_OVERSOLD_LEVEL, USE_STOCHRSI_CROSSOVER, STOP_LOSS_PCT,
    TAKE_PROFIT_PCT, BYBIT_API_ENDPOINT, BYBIT_CATEGORY, CANDLE_FETCH_LIMIT,
    POLLING_INTERVAL_SECONDS, API_REQUEST_RETRIES, API_BACKOFF_FACTOR, ATR_PERIOD,
    ENABLE_FIB_PIVOT_ACTIONS, PIVOT_TIMEFRAME, FIB_LEVELS_TO_CALC, FIB_NEAREST_COUNT,
    FIB_ENTRY_CONFIRM_PERCENT, FIB_EXIT_WARN_PERCENT, FIB_EXIT_ACTION,
    ATR_MULTIPLIER_SL, ATR_MULTIPLIER_TP,
    SMA_LENGTH, EHLERS_FISHER_LENGTH, EHLERS_SUPERSMOOTHER_LENGTH,
    MAX_ACTIVE_OBS
)
from indicators import (
    calculate_fibonacci_pivot_points, calculate_stochrsi, calculate_atr,
    calculate_sma, calculate_ehlers_fisher_transform, calculate_ehlers_super_smoother,
    find_pivots, handle_websocket_kline_data
)
from strategy import generate_signals, generate_exit_signals
from bybit_api import BybitContractAPI
from bot_ui import display_market_info

# --- Configure Logging ---
from bot_logger import setup_logging, log_trade, log_metrics, log_exception
from trade_metrics import TradeMetrics
from utils import calculate_order_quantity

class PyrmethusBot:
    """
    The core trading bot logic, encapsulating state, API interactions,
    and trading decisions. It manages its own state, retrieves market data,
    generates trading signals, and executes orders.
    """
    def __init__(self):
        self.bot_logger = setup_logging()
        self.trade_metrics = TradeMetrics()
        self.bybit_client: Optional[BybitContractAPI] = None

        # --- Bot State Variables (using Decimal for precision) ---
        # `inventory` is the single source of truth for the bot's position.
        # >0 for long, <0 for short, 0 for no position.
        self.inventory: Decimal = Decimal('0')
        self.entry_price: Decimal = Decimal('0') # Average entry price of the current open position
        self.unrealized_pnl: Decimal = Decimal('0') # Current unrealized PnL of the open position
        
        # Trade-specific metrics for logging a completed trade accurately
        self.entry_price_for_trade_metrics: Decimal = Decimal('0')
        self.entry_fee_for_trade_metrics: Decimal = Decimal('0')
        
        self.current_price: Decimal = Decimal('0') # Last known current market price
        self.klines_df: Optional[pd.DataFrame] = None # DataFrame storing historical kline data and indicators
        self.cached_atr: Optional[Decimal] = None # Last calculated ATR value

        # --- Order Block Tracking ---
        # Lists to store active bullish (demand) and bearish (supply) order blocks.
        self.active_bull_obs: List[OrderBlock] = []
        self.active_bear_obs: List[OrderBlock] = []

    @property
    def has_open_position(self) -> bool:
        """Determines if the bot currently holds an open position."""
        return abs(self.inventory) > Decimal('0')

    @property
    def current_position_side(self) -> Optional[str]:
        """Returns the side of the current open position ('Buy', 'Sell', or None)."""
        if self.inventory > Decimal('0'):
            return 'Buy'
        elif self.inventory < Decimal('0'):
            return 'Sell'
        return None

    def _reset_position_state(self):
        """Resets all internal state variables related to an open position to their defaults."""
        self.inventory = Decimal('0')
        self.entry_price = Decimal('0')
        self.unrealized_pnl = Decimal('0')
        self.entry_price_for_trade_metrics = Decimal('0')
        self.entry_fee_for_trade_metrics = Decimal('0')
        self.bot_logger.debug(f"{PYRMETHUS_GREY}Position state reset.{COLOR_RESET}")

    def _identify_and_manage_order_blocks(self):
        """
        Identifies new Pivot High/Low based Order Blocks and manages existing ones.
        This function should be called after `klines_df` is updated with the latest candle.
        It uses the last *complete* candle for pivot identification.
        """
        if self.klines_df is None or self.klines_df.empty:
            self.bot_logger.debug("No klines_df to identify Order Blocks from.")
            return

        # Ensure we're using the last *complete* candle for pivot identification.
        # klines_df might contain the current incomplete candle at index -1.
        # Pivots are typically formed on completed candles.
        if len(self.klines_df) < 2: # Need at least two candles to identify a pivot on the last *complete* one
            self.bot_logger.debug("Not enough kline data for pivot identification.")
            return

        last_complete_candle_df = self.klines_df.iloc[-2:-1] # Get the second-to-last candle as a DataFrame slice
        last_complete_candle = self.klines_df.iloc[-2] # Get the second-to-last candle as a Series
        last_complete_candle_idx = last_complete_candle.name # Get its timestamp index

        # Find pivots using the `find_pivots` function on the relevant portion of the DataFrame.
        # It's crucial to pass enough data for `find_pivots` to correctly identify patterns.
        # We need at least PIVOT_LEFT_BARS + PIVOT_RIGHT_BARS + 1 candles for a central pivot.
        required_pivot_data = PIVOT_LEFT_BARS + PIVOT_RIGHT_BARS + 1
        if len(self.klines_df) < required_pivot_data:
            self.bot_logger.debug(f"Not enough data ({len(self.klines_df)} candles) for pivot calculation. Need at least {required_pivot_data}.")
            return

        # Pass a sufficient subset of the DataFrame to find_pivots
        pivot_highs, pivot_lows = find_pivots(self.klines_df.iloc[-required_pivot_data:], PIVOT_LEFT_BARS, PIVOT_RIGHT_BARS, use_wicks=True)

        # Check if the last *complete* candle in our window is a pivot
        if not pivot_highs.empty and pivot_highs.iloc[-1]: # If the second-to-last candle is a Pivot High
            ob_top = last_complete_candle['high']
            ob_bottom = last_complete_candle['low']
            # Ensure the OB has a valid range and isn't a duplicate of a very recent, active OB
            if ob_top > ob_bottom and not any(ob['timestamp'] == last_complete_candle_idx for ob in self.active_bear_obs):
                new_ob: OrderBlock = {
                    'id': f"BEAR_OB_{last_complete_candle_idx.isoformat()}",
                    'type': 'bear',
                    'timestamp': last_complete_candle_idx,
                    'top': ob_top,
                    'bottom': ob_bottom,
                    'active': True,
                    'violated': False,
                    'violation_ts': None,
                    'extended_to_ts': last_complete_candle_idx
                }
                self.active_bear_obs.append(new_ob)
                self.bot_logger.info(f"{PYRMETHUS_PURPLE}New Bearish OB identified: {new_ob['id']} at {ob_top:.4f}-{ob_bottom:.4f}{COLOR_RESET}")

        if not pivot_lows.empty and pivot_lows.iloc[-1]: # If the second-to-last candle is a Pivot Low
            ob_bottom = last_complete_candle['low']
            ob_top = last_complete_candle['high']
            # Ensure the OB has a valid range and isn't a duplicate of a very recent, active OB
            if ob_top > ob_bottom and not any(ob['timestamp'] == last_complete_candle_idx for ob in self.active_bull_obs):
                new_ob: OrderBlock = {
                    'id': f"BULL_OB_{last_complete_candle_idx.isoformat()}",
                    'type': 'bull',
                    'timestamp': last_complete_candle_idx,
                    'top': ob_top,
                    'bottom': ob_bottom,
                    'active': True,
                    'violated': False,
                    'violation_ts': None,
                    'extended_to_ts': last_complete_candle_idx
                }
                self.active_bull_obs.append(new_ob)
                self.bot_logger.info(f"{PYRMETHUS_PURPLE}New Bullish OB identified: {new_ob['id']} at {ob_top:.4f}-{ob_bottom:.4f}{COLOR_RESET}")

        # Manage existing Order Blocks (violation and extension)
        current_price = self.current_price
        
        # Filter out inactive/violated OBs first for efficiency
        self.active_bull_obs = [ob for ob in self.active_bull_obs if ob['active']]
        self.active_bear_obs = [ob for ob in self.active_bear_obs if ob['active']]

        # Process active Order Blocks for violations or extensions
        for ob in self.active_bull_obs:
            if current_price < ob['bottom']: # Price has moved below the bullish OB
                ob['active'] = False
                ob['violated'] = True
                ob['violation_ts'] = last_complete_candle_idx # Mark violation time
                self.bot_logger.info(f"{PYRMETHUS_RED}Bullish OB {ob['id']} violated by price {current_price:.4f}{COLOR_RESET}")
            else:
                ob['extended_to_ts'] = last_complete_candle_idx # Extend active OB's relevance

        for ob in self.active_bear_obs:
            if current_price > ob['top']: # Price has moved above the bearish OB
                ob['active'] = False
                ob['violated'] = True
                ob['violation_ts'] = last_complete_candle_idx # Mark violation time
                self.bot_logger.info(f"{PYRMETHUS_RED}Bearish OB {ob['id']} violated by price {current_price:.4f}{COLOR_RESET}")
            else:
                ob['extended_to_ts'] = last_complete_candle_idx # Extend active OB's relevance

        # Re-filter after potential violations to keep only truly active ones
        self.active_bull_obs = [ob for ob in self.active_bull_obs if ob['active']]
        self.active_bear_obs = [ob for ob in self.active_bear_obs if ob['active']]

        # Limit the number of active OBs to prevent excessive memory usage and focus on recent ones.
        self.active_bull_obs.sort(key=lambda x: x['timestamp'], reverse=True)
        self.active_bull_obs = self.active_bull_obs[:MAX_ACTIVE_OBS]
        self.active_bear_obs.sort(key=lambda x: x['timestamp'], reverse=True)
        self.active_bear_obs = self.active_bear_obs[:MAX_ACTIVE_OBS]

        self.bot_logger.debug(f"Active OBs after management: Bull={len(self.active_bull_obs)}, Bear={len(self.active_bear_obs)}")

    async def _handle_position_update(self, message: Dict[str, Any]):
        """
        Asynchronous handler for WebSocket position updates.
        This is the single source of truth for the bot's open position state,
        synchronizing `self.inventory` and related metrics.
        """
        if message.get("topic") != "position" or not message.get("data"):
            self.bot_logger.debug(f"Received non-position or empty WS update: {message}")
            return

        # Bybit WS sends a list of positions, typically only one for SYMBOL
        pos_data_list = message["data"]
        pos = next((p for p in pos_data_list if p.get('symbol') == SYMBOL), None)

        if not pos or Decimal(pos.get('size', '0')) == Decimal('0'):
            # If WS indicates no position or zero size
            if self.has_open_position: # If bot thought it had a position, but WS says no (position closed)
                self.bot_logger.info(f"{PYRMETHUS_GREEN}🎉 Position for {SYMBOL} closed successfully (inferred from WS data)!{COLOR_RESET}")
                exit_price = self.current_price # Use last known price for metrics
                # Ensure inventory is not zero before calculating fee
                exit_fee = self.trade_metrics.calculate_fee(abs(self.inventory), exit_price, is_maker=False)
                
                # Record the completed trade for performance analysis
                self.trade_metrics.record_trade(
                    self.entry_price_for_trade_metrics, exit_price,
                    abs(self.inventory), self.current_position_side, # Use derived current_position_side
                    self.entry_fee_for_trade_metrics, exit_fee, asyncio.get_event_loop().time()
                )
                log_metrics(self.bot_logger, "Overall Trade Statistics", self.trade_metrics.get_trade_statistics())

            self._reset_position_state() # Always reset if no position is detected
            self.bot_logger.info(f"{PYRMETHUS_GREY}✅ No open position for {SYMBOL} (WS). Seeking new trade opportunities...{COLOR_RESET}")
            return

        # Position is open
        symbol = pos.get('symbol')
        size_str = pos.get('size', '0')
        side = pos.get('side')
        avg_price_str = pos.get('avgPrice', '0')
        unrealized_pnl_str = pos.get('unrealisedPnl', '0')

        new_size = Decimal(size_str)
        new_entry_price = Decimal(avg_price_str)
        new_unrealized_pnl = Decimal(unrealized_pnl_str) if unrealized_pnl_str else Decimal('0')

        # Determine signed inventory based on side
        signed_inventory = new_size if side == 'Buy' else -new_size

        # Check if position details have truly changed to avoid unnecessary updates/logs
        position_size_changed = self.inventory != signed_inventory
        entry_price_changed = self.entry_price != new_entry_price and new_size > 0 # Only relevant if position exists

        # If a position just opened or was modified (e.g., partial fill, average price change)
        if not self.has_open_position and new_size > 0:
            self.bot_logger.info(f"{PYRMETHUS_GREEN}🎉 Position detected and tracked via WebSocket for {symbol}.{COLOR_RESET}")
            # Capture entry details for trade metrics when position first opens
            self.entry_price_for_trade_metrics = new_entry_price
            self.entry_fee_for_trade_metrics = self.trade_metrics.calculate_fee(new_size, new_entry_price, is_maker=False)
        elif self.has_open_position and (position_size_changed or entry_price_changed):
            self.bot_logger.info(f"{PYRMETHUS_BLUE}💼 Position details updated via WS for {symbol}.{COLOR_RESET}")

        # Update core state variables
        self.inventory = signed_inventory
        self.entry_price = new_entry_price
        self.unrealized_pnl = new_unrealized_pnl
        
        if self.has_open_position:
            self.bot_logger.info(
                f"{PYRMETHUS_BLUE}💼 Open Position (WS): {self.current_position_side} {abs(self.inventory):.4f} {symbol} "
                f"at {self.entry_price:.4f}. Unrealized PnL: {self.unrealized_pnl:.4f}{COLOR_RESET}"
            )
            # If position details changed, re-evaluate and update TP/SL
            if position_size_changed or entry_price_changed:
                await self._update_take_profit_stop_loss()
        # No 'else' needed here, as the 'no position' case is handled at the beginning.

    async def _update_take_profit_stop_loss(self):
        """Sets or updates Take Profit and Stop Loss for the current position."""
        if not self.has_open_position:
            self.bot_logger.debug(f"[{SYMBOL}] No open position to set TP/SL for.")
            return

        # Check if any TP/SL configuration is present in config or derived from ATR
        if (STOP_LOSS_PCT is None and TAKE_PROFIT_PCT is None) and \
           (self.cached_atr is None or ATR_MULTIPLIER_SL is None or ATR_MULTIPLIER_TP is None):
            self.bot_logger.debug(f"[{SYMBOL}] No static TP/SL percentage or sufficient ATR configuration. Skipping TP/SL setup.")
            return

        take_profit_price = None
        stop_loss_price = None

        # Dynamic TP/SL using ATR (if multipliers are defined and ATR is cached)
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
        else: # Fallback to static TP/SL if ATR is not available or multipliers not set
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

            # Only log if static TP/SL is actually configured
            if take_profit_price or stop_loss_price:
                self.bot_logger.info(f"{PYRMETHUS_ORANGE}Static TP/SL (Percentage-based) for {SYMBOL}: TP={take_profit_price}, SL={stop_loss_price}{COLOR_RESET}")
            else:
                self.bot_logger.debug(f"[{SYMBOL}] No static TP/SL percentages configured. Skipping.")
                return # No TP/SL to set

        # Only set if a valid price is calculated for either TP or SL
        if take_profit_price or stop_loss_price:
            try:
                await self.bybit_client.set_trading_stop(
                    category=BYBIT_CATEGORY,
                    symbol=SYMBOL,
                    take_profit=f"{take_profit_price:.4f}" if take_profit_price else None,
                    stop_loss=f"{stop_loss_price:.4f}" if stop_loss_price else None,
                    positionIdx=0 # For unified margin / inverse perpetual
                )
                self.bot_logger.info(f"{PYRMETHUS_GREEN}TP/SL orders submitted for {SYMBOL}.{COLOR_RESET}")
            except Exception as e:
                log_exception(self.bot_logger, f"Failed to set TP/SL for {SYMBOL}: {e}", e)

    async def _handle_kline_update(self, message: Dict[str, Any]):
        """
        Asynchronous handler for WebSocket kline updates.
        Updates the internal `klines_df` and derived indicators in real-time.
        """
        if message.get("topic") != f"kline.{INTERVAL}.{SYMBOL}" or not message.get("data"):
            self.bot_logger.debug(f"Received non-kline or empty WS update: {message}")
            return

        # Use the handle_websocket_kline_data from indicators.py to update the DataFrame
        updated_df = handle_websocket_kline_data(self.klines_df, message)
        if updated_df is not None and not updated_df.empty:
            self.klines_df = updated_df
            
            # Recalculate all necessary indicators on the updated DataFrame
            # Ensure enough data points are available before calculating
            min_data_needed_for_indicators = max(STOCHRSI_K_PERIOD, ATR_PERIOD, SMA_LENGTH, EHLERS_FISHER_LENGTH, EHLERS_SUPERSMOOTHER_LENGTH)
            if len(self.klines_df) >= min_data_needed_for_indicators:
                self.klines_df = calculate_stochrsi(self.klines_df.copy(), rsi_period=STOCHRSI_K_PERIOD, stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD)
                self.klines_df['atr'] = calculate_atr(self.klines_df)
                self.klines_df['sma'] = calculate_sma(self.klines_df, length=SMA_LENGTH)
                self.klines_df['ehlers_fisher'] = calculate_ehlers_fisher_transform(self.klines_df, length=EHLERS_FISHER_LENGTH)
                self.klines_df['ehlers_supersmoother'] = calculate_ehlers_super_smoother(self.klines_df, length=EHLERS_SUPERSMOOTHER_LENGTH)

                # Update cached values from the latest complete candle (or current for price)
                self.cached_atr = self.klines_df['atr'].iloc[-1] if 'atr' in self.klines_df.columns and not self.klines_df['atr'].empty else Decimal('0')
                self.current_price = self.klines_df['close'].iloc[-1] # The last 'close' is the current price for an incomplete candle
                
                # Identify and manage Order Blocks *after* indicators are updated
                self._identify_and_manage_order_blocks()
                self.bot_logger.debug(f"{PYRMETHUS_CYAN}Kline updated via WebSocket. Current price: {self.current_price:.4f}{COLOR_RESET}")
            else:
                self.bot_logger.warning(f"{COLOR_YELLOW}Not enough kline data ({len(self.klines_df)} candles) for full indicator calculation. Waiting for more data.{COLOR_RESET}")
                # Still update current price if possible
                if not self.klines_df['close'].empty:
                    self.current_price = self.klines_df['close'].iloc[-1]
        else:
            self.bot_logger.warning(f"{COLOR_YELLOW}Failed to update klines_df from WebSocket message: {message}{COLOR_RESET}")

    async def _initial_kline_fetch(self) -> bool:
        """
        Fetches initial historical kline data to populate the DataFrame.
        This ensures the bot has enough historical context for indicator calculations.
        """
        try:
            self.bot_logger.info(f"{PYRMETHUS_ORANGE}Fetching initial kline data for {SYMBOL} ({INTERVAL})...{COLOR_RESET}")
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

            # Ensure enough data for all indicators to avoid NaN issues
            min_data_needed = max(STOCHRSI_K_PERIOD, ATR_PERIOD, SMA_LENGTH, EHLERS_FISHER_LENGTH, EHLERS_SUPERSMOOTHER_LENGTH)
            if len(df) < min_data_needed:
                self.bot_logger.warning(
                    f"{COLOR_YELLOW}Insufficient initial data for all indicators ({len(df)} candles). "
                    f"Need at least {min_data_needed}. Indicators might be NaN initially.{COLOR_RESET}"
                )
                # For critical indicators, consider exiting here: `return False`

            # Calculate initial indicators
            self.klines_df = calculate_stochrsi(df.copy(), rsi_period=STOCHRSI_K_PERIOD, stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD)
            self.klines_df['atr'] = calculate_atr(self.klines_df)
            self.klines_df['sma'] = calculate_sma(self.klines_df, length=SMA_LENGTH)
            self.klines_df['ehlers_fisher'] = calculate_ehlers_fisher_transform(self.klines_df, length=EHLERS_FISHER_LENGTH)
            self.klines_df['ehlers_supersmoother'] = calculate_ehlers_super_smoother(self.klines_df, length=EHLERS_SUPERSMOOTHER_LENGTH)

            # Update cached values from the latest complete candle
            self.cached_atr = self.klines_df['atr'].iloc[-1] if 'atr' in self.klines_df.columns and not self.klines_df['atr'].empty else Decimal('0')
            self.current_price = self.klines_df['close'].iloc[-1] if not self.klines_df['close'].empty else Decimal('0')

            self.bot_logger.info(f"{PYRMETHUS_GREEN}Initial kline data fetched and processed. Current price: {self.current_price:.4f}{COLOR_RESET}")
            return True
        except Exception as e:
            log_exception(self.bot_logger, f"Error during initial kline fetch: {e}", e)
            return False

    async def _execute_entry(self, signal_type: str, signal_price: Decimal, signal_timestamp: Any, signal_info: Dict[str, Any]):
        """Executes an entry trade based on a signal."""
        self.bot_logger.info(f"{PYRMETHUS_PURPLE}💡 Detected {signal_type.upper()} signal at {signal_price:.4f} (Info: {signal_info.get('stoch_type', 'N/A')}){COLOR_RESET}")

        # Fetch instrument info to get min_qty and qty_step for precise order sizing
        instrument_info_resp = await self.bybit_client.get_instruments_info(category=BYBIT_CATEGORY, symbol=SYMBOL)
        if not instrument_info_resp or not instrument_info_resp.get('result') or not instrument_info_resp['result'].get('list'):
            self.bot_logger.error(f"{COLOR_RED}Could not fetch instrument info for {SYMBOL}. Cannot place entry order.{COLOR_RESET}")
            return False

        instrument_details = instrument_info_resp['result']['list'][0]
        min_qty = Decimal(instrument_details.get('lotSizeFilter', {}).get('minOrderQty', '0'))
        qty_step = Decimal(instrument_details.get('lotSizeFilter', {}).get('qtyStep', '0'))

        # Calculate the order quantity based on USDT amount and current price, respecting exchange rules
        calculated_quantity = calculate_order_quantity(USDT_AMOUNT_PER_TRADE, self.current_price, min_qty, qty_step)
        if calculated_quantity <= Decimal('0'):
            self.bot_logger.error(f"{COLOR_RED}Calculated entry quantity is zero or negative: {calculated_quantity}. Cannot place order.{COLOR_RESET}")
            return False

        order_kwargs = {
            "category": BYBIT_CATEGORY,
            "symbol": SYMBOL,
            "side": signal_type.capitalize(), # 'Buy' or 'Sell'
            "order_type": "Market",
            "qty": str(calculated_quantity), # Quantity must be a string for API
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
                "quantity": calculated_quantity
            })
            # The actual position state and TP/SL will be updated by the WebSocket callback
            return True
        return False

    async def _execute_exit(self, exit_type: str, exit_price: Decimal, exit_timestamp: Any, exit_info: Dict[str, Any]):
        """Executes an exit trade based on a signal."""
        self.bot_logger.info(f"{PYRMETHUS_PURPLE}💡 Detected {exit_type.upper()} exit signal at {exit_price:.4f} (Info: {exit_info.get('stoch_type', 'N/A')}){COLOR_RESET}")

        if not self.has_open_position:
            self.bot_logger.warning(f"{COLOR_YELLOW}Attempted to exit, but no current open position. Skipping exit order.{COLOR_RESET}")
            return False

        # Determine the correct side for the exit order (opposite of current position side)
        side_for_exit = 'Sell' if self.inventory > 0 else 'Buy'

        exit_order_kwargs = {
            "category": BYBIT_CATEGORY,
            "symbol": SYMBOL,
            "side": side_for_exit,
            "order_type": "Market",
            "qty": str(abs(self.inventory)), # Exit the full current position size
        }

        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Attempting to place {side_for_exit} exit order for {abs(self.inventory):.4f} {SYMBOL} at market price...{COLOR_RESET}")
        if await self.bybit_client.create_order(**exit_order_kwargs):
            log_trade(self.bot_logger, "Exit trade executed", {
                "exit_type": exit_type.upper(),
                "price": self.current_price,
                "timestamp": str(exit_timestamp),
                "stoch_k": exit_info.get('stoch_k'),
                "stoch_d": exit_info.get('stoch_d'),
                "exit_quantity": str(abs(self.inventory)),
                "order_type": "Market"
            })
            # The actual position state will be updated by the WebSocket callback
            return True
        return False

    async def run(self):
        """Main execution loop for the trading bot."""
        self.bot_logger.info("Starting Pyrmethus's Ultra Scalper Bot.")

        print(f"{PYRMETHUS_PURPLE}{COLOR_BOLD}\n🚀 Pyrmethus's Ultra Scalper Bot - Awakened{COLOR_RESET}")
        print(f"{PYRMETHUS_PURPLE}{COLOR_BOLD}=========================================={COLOR_RESET}")
        print(f"{PYRMETHUS_ORANGE}\n⚡ Initializing scalping engine and calibrating sensors...{COLOR_RESET}")

        self.bybit_client = BybitContractAPI(
            testnet="testnet" in BYBIT_API_ENDPOINT # Determine testnet status from endpoint
        )
        self.bot_logger.info("BybitContractAPI initialized.")

        # Start WebSocket listeners for real-time updates
        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Starting private WebSocket listener for position updates...{COLOR_RESET}")
        private_listener_task = self.bybit_client.start_private_websocket_listener(self._handle_position_update)
        await self.bybit_client.subscribe_ws_private_topic("position")
        self.bot_logger.info(f"{PYRMETHUS_GREEN}Subscribed to private 'position' topic.{COLOR_RESET}")

        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Starting public WebSocket listener for kline updates...{COLOR_RESET}")
        public_listener_task = self.bybit_client.start_public_websocket_listener(self._handle_kline_update)
        await self.bybit_client.subscribe_ws_public_topic(f"kline.{INTERVAL}.{SYMBOL}")
        self.bot_logger.info(f"{PYRMETHUS_GREEN}Subscribed to public 'kline.{INTERVAL}.{SYMBOL}' topic.{COLOR_RESET}")

        # Initial fetch of historical kline data to build context
        if not await self._initial_kline_fetch():
            self.bot_logger.critical(f"{COLOR_RED}Failed to fetch initial kline data. Exiting bot.{COLOR_RESET}")
            # Ensure listeners are cancelled if we exit early
            for task in [private_listener_task, public_listener_task]:
                task.cancel()
            await asyncio.gather(*[private_listener_task, public_listener_task], return_exceptions=True)
            return

        # Fetch initial position from REST API to synchronize state upon startup
        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Synchronizing initial position state via REST API...{COLOR_RESET}")
        initial_pos_response = await self.bybit_client.get_positions(category=BYBIT_CATEGORY, symbol=SYMBOL)
        if initial_pos_response and initial_pos_response.get('result') and initial_pos_response['result'].get('list'):
            # Simulate a WS message to use the unified position handler
            simulated_message = {"topic": "position", "data": initial_pos_response['result']['list']}
            await self._handle_position_update(simulated_message)
        else:
            # If no position found via REST, explicitly handle as no position
            await self._handle_position_update({"topic": "position", "data": []})
        self.bot_logger.info(f"{PYRMETHUS_GREEN}Initial position synchronization complete.{COLOR_RESET}")

        # Gather all listener tasks to run concurrently with the main trading loop
        listener_tasks = [private_listener_task, public_listener_task]

        async with self.bybit_client: # Ensures WebSocket connections are properly managed (opened/closed)
            try:
                while True:
                    # Ensure `klines_df` is not None and has sufficient data for calculations
                    min_data_needed_for_strategy = max(STOCHRSI_K_PERIOD, ATR_PERIOD, PIVOT_LEFT_BARS + PIVOT_RIGHT_BARS + 1)
                    if self.klines_df is None or len(self.klines_df) < min_data_needed_for_strategy:
                        self.bot_logger.warning(f"{COLOR_YELLOW}Insufficient kline data for strategy calculations. Waiting for more data...{COLOR_RESET}")
                        await asyncio.sleep(POLLING_INTERVAL_SECONDS)
                        continue

                    # --- Calculate Fibonacci Pivot Levels (if enabled) ---
                    pivot_support_levels: Dict[str, Decimal] = {}
                    pivot_resistance_levels: Dict[str, Decimal] = {}

                    if ENABLE_FIB_PIVOT_ACTIONS:
                        self.bot_logger.debug(f"Calculating Fibonacci Pivots based on {PIVOT_TIMEFRAME} timeframe...")
                        try:
                            # Fetch data for the pivot timeframe. We need the last *completed* candle.
                            # Fetch 2 candles to ensure we have the completed previous one (iloc[-2]).
                            pivot_ohlcv_response = await self.bybit_client.get_kline_rest_fallback(
                                category=BYBIT_CATEGORY, symbol=SYMBOL, interval=PIVOT_TIMEFRAME, limit=2
                            )
                            if pivot_ohlcv_response and pivot_ohlcv_response.get('result') and pivot_ohlcv_response['result'].get('list'):
                                pivot_data = []
                                for kline in pivot_ohlcv_response['result']['list']:
                                    pivot_data.append({
                                        'timestamp': pd.to_datetime(int(kline[0]), unit='ms', utc=True),
                                        'open': Decimal(kline[1]),
                                        'high': Decimal(kline[2]),
                                        'low': Decimal(kline[3]),
                                        'close': Decimal(kline[4]),
                                        'volume': Decimal(kline[5]),
                                    })
                                pivot_ohlcv_df = pd.DataFrame(pivot_data).set_index('timestamp').sort_index()

                                if len(pivot_ohlcv_df) >= 2:
                                    # Use the second to last row (index -2) which is the *last completed* candle for pivot calculation
                                    prev_pivot_candle = pivot_ohlcv_df.iloc[-2]
                                    # Pass a DataFrame with a single row for the calculation
                                    temp_df_for_fib = pd.DataFrame([prev_pivot_candle]).set_index('timestamp')
                                    fib_resistance, fib_support = calculate_fibonacci_pivot_points(temp_df_for_fib)

                                    # Extract and store the calculated Fibonacci levels
                                    for r_level in fib_resistance:
                                        pivot_resistance_levels[r_level['type']] = r_level['price']
                                    for s_level in fib_support:
                                        pivot_support_levels[s_level['type']] = s_level['price']

                                    self.bot_logger.debug(f"Calculated Fib Support Pivots: {pivot_support_levels}")
                                    self.bot_logger.debug(f"Calculated Fib Resistance Pivots: {pivot_resistance_levels}")
                                else:
                                    self.bot_logger.warning(f"{COLOR_YELLOW}Could not fetch sufficient data ({len(pivot_ohlcv_df)} candles) for {PIVOT_TIMEFRAME} pivots.{COLOR_RESET}")
                            else:
                                self.bot_logger.warning(f"{COLOR_YELLOW}Failed to fetch pivot data for {PIVOT_TIMEFRAME}. Response: {pivot_ohlcv_response}{COLOR_RESET}")
                        except Exception as pivot_e:
                            log_exception(self.bot_logger, f"Error during Fibonacci Pivot calculation: {pivot_e}", pivot_e)
                    
                    # Display current market information (from bot_ui)
                    display_market_info(self.klines_df, self.current_price, SYMBOL, pivot_resistance_levels, pivot_support_levels, self.bot_logger)

                    if not self.has_open_position:
                        signals = generate_signals(self.klines_df, pivot_resistance_levels, pivot_support_levels,
                                                   self.active_bull_obs, self.active_bear_obs,
                                                   stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD,
                                                   overbought=STOCHRSI_OVERBOUGHT_LEVEL, oversold=STOCHRSI_OVERSOLD_LEVEL,
                                                   use_crossover=USE_STOCHRSI_CROSSOVER,
                                                   enable_fib_pivot_actions=ENABLE_FIB_PIVOT_ACTIONS,
                                                   fib_entry_confirm_percent=FIB_ENTRY_CONFIRM_PERCENT)
                        
                        for signal in signals:
                            signal_type, signal_price, signal_timestamp, signal_info = signal
                            if await self._execute_entry(signal_type, signal_price, signal_timestamp, signal_info):
                                # If an entry order is successfully placed, break to avoid placing multiple orders in one loop cycle
                                break 
                    else:
                        self.bot_logger.info(f"{PYRMETHUS_BLUE}🚫 Position already open: {self.current_position_side} {SYMBOL}. Checking for exit signals...{COLOR_RESET}")
                        exit_signals = generate_exit_signals(self.klines_df, self.current_position_side,
                                                             self.active_bull_obs, self.active_bear_obs,
                                                             stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD,
                                                             overbought=STOCHRSI_OVERBOUGHT_LEVEL, oversold=STOCHRSI_OVERSOLD_LEVEL,
                                                             use_crossover=USE_STOCHRSI_CROSSOVER,
                                                             enable_fib_pivot_actions=ENABLE_FIB_PIVOT_ACTIONS,
                                                             fib_exit_warn_percent=FIB_EXIT_WARN_PERCENT,
                                                             fib_exit_action=FIB_EXIT_ACTION)
                        if exit_signals:
                            for exit_signal in exit_signals:
                                exit_type, exit_price, exit_timestamp, exit_info = exit_signal
                                if await self._execute_exit(exit_type, exit_price, exit_timestamp, exit_info):
                                    # If an exit order is successfully placed, break
                                    break
                        else:
                            self.bot_logger.info(f"{PYRMETHUS_GREY}No exit signals detected for {self.current_position_side} position.{COLOR_RESET}")

                    self.bot_logger.info(f"{PYRMETHUS_ORANGE}Sleeping for {POLLING_INTERVAL_SECONDS} seconds...{COLOR_RESET}")
                    await asyncio.sleep(POLLING_INTERVAL_SECONDS)

            except KeyboardInterrupt:
                self.bot_logger.info(f"{COLOR_YELLOW}Bot stopped by user (KeyboardInterrupt).{COLOR_RESET}")
            except Exception as e:
                log_exception(self.bot_logger, f"Critical error in main loop: {str(e)}", e)
                self.bot_logger.info(f"{COLOR_YELLOW}🔄 Attempting to recover and restart main loop after 10 seconds...{COLOR_RESET}")
                await asyncio.sleep(10)
            finally:
                # Ensure all background listener tasks are cancelled and awaited upon bot shutdown
                self.bot_logger.info(f"{COLOR_YELLOW}Initiating shutdown: Cancelling listener tasks...{COLOR_RESET}")
                for task in listener_tasks:
                    task.cancel()
                # Use return_exceptions=True to ensure all tasks are gathered even if one fails during cancellation
                await asyncio.gather(*listener_tasks, return_exceptions=True) 
                self.bot_logger.info(f"{COLOR_YELLOW}All listener tasks cancelled and awaited. Bot shutdown complete.{COLOR_RESET}")

async def main():
    """Entry point for the Pyrmethus Bot, handling environment setup and bot execution."""
    load_dotenv() # Load environment variables from .env file
    bot = PyrmethusBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        # Catch KeyboardInterrupt here to prevent unhandled exception on graceful exit
        pass
    except Exception as e:
        setup_logging().critical(f"Unhandled exception in main execution: {e}", exc_info=True)
        print(f"{COLOR_RED}A critical error occurred: {e}. Check logs for details.{COLOR_RESET}")

if __name__ == "__main__":
    asyncio.run(main())