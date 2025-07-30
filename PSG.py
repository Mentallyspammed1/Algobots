# PSG.py - Pyrmethus's Ultra Scalper Bot (Upgraded)
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
getcontext().prec = 38

# --- Pyrmethus's Color Codex ---
from color_codex import (
    COLOR_RESET, COLOR_BOLD, COLOR_DIM,
    COLOR_RED, COLOR_GREEN, COLOR_YELLOW, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN,
    PYRMETHUS_GREEN, PYRMETHUS_BLUE, PYRMETHUS_PURPLE, PYRMETHUS_ORANGE, PYRMETHUS_GREY
)

# --- Import Configuration and Indicator Logic ---
from config import (
    SYMBOL, INTERVAL, USDT_AMOUNT_PER_TRADE, PIVOT_LEFT_BARS, PIVOT_RIGHT_BARS, PIVOT_TOLERANCE_PCT,
    STOCHRSI_K_PERIOD, STOCHRSI_D_PERIOD, STOCHRSI_OVERBOUGHT_LEVEL,
    STOCHRSI_OVERSOLD_LEVEL, USE_STOCHRSI_CROSSOVER, STOP_LOSS_PCT,
    TAKE_PROFIT_PCT, BYBIT_API_ENDPOINT, BYBIT_CATEGORY, CANDLE_FETCH_LIMIT,
    POLLING_INTERVAL_SECONDS, API_REQUEST_RETRIES, API_BACKOFF_FACTOR, ATR_PERIOD,
    ENABLE_FIB_PIVOT_ACTIONS, PIVOT_TIMEFRAME, FIB_LEVELS_TO_CALC, FIB_NEAREST_COUNT,
    FIB_ENTRY_CONFIRM_PERCENT, FIB_EXIT_WARN_PERCENT, FIB_EXIT_ACTION
)
from indicators import calculate_fibonacci_pivot_points, calculate_stochrsi, calculate_atr, calculate_sma, calculate_ehlers_fisher_transform, calculate_ehlers_super_smoother
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
        
        # Legacy state variables, to be harmonized or deprecated
        self.position_open: bool = False
        self.current_position_side: Optional[str] = None # 'Buy' or 'Sell'
        
        # Trade-specific metrics
        self.entry_price_for_trade_metrics: Decimal = Decimal('0')
        self.entry_fee_for_trade_metrics: Decimal = Decimal('0')
        
        self.current_price: Decimal = Decimal('0')
        self.klines_df: Optional[pd.DataFrame] = None
        self.cached_atr: Optional[Decimal] = None

        # --- Order Block Tracking (Placeholder for future implementation) ---
        self.active_bull_obs: List[Any] = []
        self.active_bear_obs: List[Any] = []
        self.active_bull_obs: List[OrderBlock] = []
        self.active_bear_obs: List[OrderBlock] = []

    def _reset_position_state(self):
        """Resets all internal state variables related to an open position."""
        self.inventory = Decimal('0')
        self.entry_price = Decimal('0')
        self.unrealized_pnl = Decimal('0')
        self.position_open = False
        self.current_position_side = None
        self.entry_price_for_trade_metrics = Decimal('0')
        self.entry_fee_for_trade_metrics = Decimal('0')

    def _identify_and_manage_order_blocks(self):
        """
        Identifies new Pivot High/Low based Order Blocks and manages existing ones.
        This function should be called after klines_df is updated.
        """
        if self.klines_df is None or self.klines_df.empty:
            self.bot_logger.debug("No klines_df to identify Order Blocks from.")
            return

        # Use the last complete candle for OB identification
        last_candle_idx = self.klines_df.index[-1]
        last_candle = self.klines_df.iloc[-1]
        
        # Find pivots (using the function from indicators.py)
        # Note: find_pivots expects the full DataFrame and returns boolean series
        pivot_highs, pivot_lows = find_pivots(self.klines_df, PIVOT_LEFT_BARS, PIVOT_RIGHT_BARS, use_wicks=True) # Assuming wicks for now

        # Identify new Order Blocks
        if pivot_highs.iloc[-1]: # If the last candle is a Pivot High
            ob_top = last_candle['high']
            ob_bottom = last_candle['low'] # For bearish OB, body or wick low
            if ob_top > ob_bottom:
                new_ob = OrderBlock(id=f"B_{last_candle_idx.value}", type='bear', timestamp=last_candle_idx, top=ob_top, bottom=ob_bottom, active=True, violated=False, violation_ts=None, extended_to_ts=last_candle_idx)
                self.active_bear_obs.append(new_ob)
                self.bot_logger.info(f"New Bearish OB identified: {new_ob['id']} at {ob_top:.4f}-{ob_bottom:.4f}")

        if pivot_lows.iloc[-1]: # If the last candle is a Pivot Low
            ob_bottom = last_candle['low']
            ob_top = last_candle['high'] # For bullish OB, body or wick high
            if ob_top > ob_bottom:
                new_ob = OrderBlock(id=f"L_{last_candle_idx.value}", type='bull', timestamp=last_candle_idx, top=ob_top, bottom=ob_bottom, active=True, violated=False, violation_ts=None, extended_to_ts=last_candle_idx)
                self.active_bull_obs.append(new_ob)
                self.bot_logger.info(f"New Bullish OB identified: {new_ob['id']} at {ob_top:.4f}-{ob_bottom:.4f}")

        # Manage existing Order Blocks (violation and extension)
        current_price = self.current_price
        for ob in self.active_bull_obs:
            if ob['active']:
                if current_price < ob['bottom']:
                    ob['active'] = False
                    ob['violated'] = True
                    ob['violation_ts'] = last_candle_idx
                    self.bot_logger.info(f"Bullish OB {ob['id']} violated by price {current_price:.4f}")
                else:
                    ob['extended_to_ts'] = last_candle_idx # Extend active OB
        
        for ob in self.active_bear_obs:
            if ob['active']:
                if current_price > ob['top']:
                    ob['active'] = False
                    ob['violated'] = True
                    ob['violation_ts'] = last_candle_idx
                    self.bot_logger.info(f"Bearish OB {ob['id']} violated by price {current_price:.4f}")
                else:
                    ob['extended_to_ts'] = last_candle_idx # Extend active OB

        # Filter out inactive/violated OBs (optional, but good for performance)
        self.active_bull_obs = [ob for ob in self.active_bull_obs if ob['active']]
        self.active_bear_obs = [ob for ob in self.active_bear_obs if ob['active']]

        # Limit the number of active OBs to prevent excessive memory usage
        # Sort by timestamp and keep only the most recent ones
        self.active_bull_obs.sort(key=lambda x: x['timestamp'], reverse=True)
        self.active_bull_obs = self.active_bull_obs[:10] # Limit to 10 for now
        self.active_bear_obs.sort(key=lambda x: x['timestamp'], reverse=True)
        self.active_bear_obs = self.active_bear_obs[:10] # Limit to 10 for now

        self.bot_logger.debug(f"Active OBs after management: Bull={len(self.active_bull_obs)}, Bear={len(self.active_bear_obs)}")

    async def _handle_position_update(self, message: Dict[str, Any]):
        """
        Asynchronous handler for WebSocket position updates.
        This is the single source of truth for the bot's open position state.
        """
        if message.get("topic") != "position" or not message.get("data"):
            self.bot_logger.debug(f"Received non-position or empty WS update: {message}")
            return

        pos_data = message["data"]
        if not pos_data or not pos_data[0]: # No open position
            if self.inventory != Decimal('0'):
                self.bot_logger.info(f"{PYRMETHUS_GREEN}🎉 Position for {SYMBOL} closed successfully (inferred from empty WS data)!{COLOR_RESET}")
                exit_price = self.current_price
                exit_fee = self.trade_metrics.calculate_fee(abs(self.inventory), exit_price, is_maker=False)
                self.trade_metrics.record_trade(
                    self.entry_price_for_trade_metrics, exit_price,
                    abs(self.inventory), self.current_position_side,
                    self.entry_fee_for_trade_metrics, exit_fee, asyncio.get_event_loop().time()
                )
                log_metrics(self.bot_logger, "Overall Trade Statistics", self.trade_metrics.get_trade_statistics())
            
            self._reset_position_state()
            self.bot_logger.info(f"{PYRMETHUS_GREY}✅ No open position for {SYMBOL} (WS). Seeking new trade opportunities...{COLOR_RESET}")
            return

        # Position is open
        pos = pos_data[0]
        symbol = pos.get('symbol')
        size_str = pos.get('size', '0')
        side = pos.get('side')
        avg_price_str = pos.get('avgPrice', '0')
        unrealized_pnl_str = pos.get('unrealisedPnl', '0')

        new_size = Decimal(size_str)
        new_entry_price = Decimal(avg_price_str)
        
        # Determine signed inventory
        signed_inventory = new_size if side == 'Buy' else -new_size
        
        position_changed = self.inventory != signed_inventory
        entry_price_changed = self.entry_price != new_entry_price and new_size > 0

        if not self.position_open and new_size > 0: # Position just opened
            self.bot_logger.info(f"{PYRMETHUS_GREEN}🎉 Position detected and tracked via WebSocket for {symbol}.{COLOR_RESET}")
            self.entry_price_for_trade_metrics = new_entry_price
            self.entry_fee_for_trade_metrics = self.trade_metrics.calculate_fee(new_size, new_entry_price, is_maker=False)

        # Update state
        self.inventory = signed_inventory
        self.entry_price = new_entry_price
        self.unrealized_pnl = Decimal(unrealized_pnl_str) if unrealized_pnl_str else Decimal('0')
        self.position_open = new_size > 0
        self.current_position_side = side if new_size > 0 else None

        if self.position_open:
            self.bot_logger.info(
                f"{PYRMETHUS_BLUE}💼 Open Position (WS): {self.current_position_side} {abs(self.inventory):.4f} {symbol} "
                f"at {self.entry_price:.4f}. Unrealized PnL: {self.unrealized_pnl:.4f}{COLOR_RESET}"
            )
            # If position details changed, update TP/SL
            if position_changed or entry_price_changed:
                await self._update_take_profit_stop_loss()
        else:
            # This case is handled by the "No open position" block at the start
            pass

    async def _update_take_profit_stop_loss(self):
        """Sets or updates Take Profit and Stop Loss for the current position."""
        if not self.position_open or self.inventory == Decimal('0'):
            self.bot_logger.debug(f"[{SYMBOL}] No open position to set TP/SL for.")
            return

        if STOP_LOSS_PCT is None and TAKE_PROFIT_PCT is None and self.cached_atr is None:
            self.bot_logger.debug(f"[{SYMBOL}] No static TP/SL percentage or ATR configured. Skipping.")
            return

        take_profit_price = None
        stop_loss_price = None

        # Dynamic TP/SL using ATR
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
        # Fallback to static TP/SL if ATR is not available or multipliers not set
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

        # Only set if a valid price is calculated
        if take_profit_price or stop_loss_price:
            await self.bybit_client.set_trading_stop(
                category=BYBIT_CATEGORY,
                symbol=SYMBOL,
                take_profit=f"{take_profit_price:.4f}" if take_profit_price else None,
                stop_loss=f"{stop_loss_price:.4f}" if stop_loss_price else None,
                positionIdx=0
            )

    async def _handle_kline_update(self, message: Dict[str, Any]):
        """
        Asynchronous handler for WebSocket kline updates.
        Updates the internal klines_df and derived indicators.
        """
        if message.get("topic") != f"kline.{INTERVAL}.{SYMBOL}" or not message.get("data"):
            self.bot_logger.debug(f"Received non-kline or empty WS update: {message}")
            return

        # Use the handle_websocket_kline_data from indicators.py
        updated_df = handle_websocket_kline_data(self.klines_df, message)
        
        if updated_df is not None and not updated_df.empty:
            self.klines_df = updated_df
            # Recalculate indicators on the updated DataFrame
            self.klines_df = calculate_stochrsi(self.klines_df.copy(), rsi_period=STOCHRSI_K_PERIOD, stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD)
            self.klines_df['atr'] = calculate_atr(self.klines_df)
            self.klines_df['sma'] = calculate_sma(self.klines_df, length=10) # Default SMA length
            self.klines_df['ehlers_fisher'] = calculate_ehlers_fisher_transform(self.klines_df, length=9) # Default Fisher length
            self.klines_df['ehlers_supersmoother'] = calculate_ehlers_super_smoother(self.klines_df, length=10) # Default Super Smoother length
            self.klines_df['sma'] = calculate_sma(self.klines_df, SMA_PERIOD)
            self.klines_df['ehlers_fisher'] = calculate_ehlers_fisher_transform(self.klines_df)
            self.klines_df['ehlers_supersmoother'] = calculate_ehlers_super_smoother(self.klines_df)
            self._identify_and_manage_order_blocks() # Call OB management here
            self.cached_atr = self.klines_df['atr'].iloc[-1]
            self.current_price = self.klines_df['close'].iloc[-1]
            self.bot_logger.debug(f"{PYRMETHUS_CYAN}Kline updated via WebSocket. Current price: {self.current_price:.4f}{COLOR_RESET}")
        else:
            self.bot_logger.warning(f"{COLOR_YELLOW}Failed to update klines_df from WebSocket message: {message}{COLOR_RESET}")

    async def _initial_kline_fetch(self) -> bool:
        """Fetches initial historical kline data to populate the DataFrame."""
        try:
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

            if len(df) < max(STOCHRSI_K_PERIOD, ATR_PERIOD):
                self.bot_logger.warning(f"{COLOR_YELLOW}Insufficient initial data for indicators ({len(df)} candles). Need at least {max(STOCHRSI_K_PERIOD, ATR_PERIOD)}.{COLOR_RESET}")
                return False

            self.klines_df = calculate_stochrsi(df.copy(), rsi_period=STOCHRSI_K_PERIOD, stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD)
            self.klines_df['atr'] = calculate_atr(self.klines_df)
            self.klines_df['sma'] = calculate_sma(self.klines_df, length=10) # Default SMA length
            self.klines_df['ehlers_fisher'] = calculate_ehlers_fisher_transform(self.klines_df, length=9) # Default Fisher length
            self.klines_df['ehlers_supersmoother'] = calculate_ehlers_super_smoother(self.klines_df, length=10) # Default Super Smoother length
            self.cached_atr = self.klines_df['atr'].iloc[-1]
            self.current_price = self.klines_df['close'].iloc[-1]
            self.bot_logger.info(f"{PYRMETHUS_GREEN}Initial kline data fetched and processed. Current price: {self.current_price:.4f}{COLOR_RESET}")
            return True
        except Exception as e:
            log_exception(self.bot_logger, f"Error during initial kline fetch: {e}", e)
            return False

    async def _execute_entry(self, signal_type: str, signal_price: Decimal, signal_timestamp: Any, signal_info: Dict[str, Any]):
        """Executes an entry trade based on a signal."""
        self.bot_logger.info(f"{PYRMETHUS_PURPLE}💡 Detected {signal_type.upper()} signal at {signal_price:.4f} (Info: {signal_info.get('stoch_type', 'N/A')}){COLOR_RESET}")

        instrument_info_resp = await self.bybit_client.get_instruments_info(category=BYBIT_CATEGORY, symbol=SYMBOL)
        if not instrument_info_resp or not instrument_info_resp.get('result') or not instrument_info_resp['result'].get('list'):
            self.bot_logger.error(f"{COLOR_RED}Could not fetch instrument info for {SYMBOL}. Cannot place entry order.{COLOR_RESET}")
            return

        instrument_details = instrument_info_resp['result']['list'][0]
        min_qty = Decimal(instrument_details.get('lotSizeFilter', {}).get('minOrderQty', '0'))
        qty_step = Decimal(instrument_details.get('lotSizeFilter', {}).get('qtyStep', '0'))

        calculated_quantity_float = calculate_order_quantity(USDT_AMOUNT_PER_TRADE, self.current_price, min_qty, qty_step)
        calculated_quantity = Decimal(str(calculated_quantity_float)) # Convert to Decimal immediately
        if calculated_quantity <= 0:
            self.bot_logger.error(f"{COLOR_RED}Calculated entry quantity is zero or negative: {calculated_quantity}. Cannot place order.{COLOR_RESET}")
            return

        order_kwargs = {
            "category": BYBIT_CATEGORY,
            "symbol": SYMBOL,
            "side": signal_type.capitalize(),
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
            })
            # Position state and TP/SL will be updated by WebSocket callback
            return True
        return False

    async def _execute_exit(self, exit_type: str, exit_price: Decimal, exit_timestamp: Any, exit_info: Dict[str, Any]):
        """Executes an exit trade based on a signal."""
        self.bot_logger.info(f"{PYRMETHUS_PURPLE}💡 Detected {exit_type.upper()} exit signal at {exit_price:.4f} (Info: {exit_info.get('stoch_type', 'N/A')}){COLOR_RESET}")

        if abs(self.inventory) <= 0:
            self.bot_logger.warning(f"{COLOR_YELLOW}Attempted to exit, but current inventory is 0. Skipping exit order.{COLOR_RESET}")
            return False

        exit_order_kwargs = {
            "category": BYBIT_CATEGORY,
            "symbol": SYMBOL,
            "side": exit_type.capitalize(),
            "order_type": "Market",
            "qty": str(abs(self.inventory)),
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
                "order_type": "Market"
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
            testnet="testnet" in BYBIT_API_ENDPOINT
        )
        self.bot_logger.info("BybitContractAPI initialized.")

        private_listener_task = asyncio.create_task(self.bybit_client.start_private_websocket_listener(self._handle_position_update))
        await self.bybit_client.subscribe_ws_private_topic("position")

        public_listener_task = asyncio.create_task(self.bybit_client.start_public_websocket_listener(self._handle_kline_update))
        await self.bybit_client.subscribe_ws_public_topic(f"kline.{INTERVAL}.{SYMBOL}")

        # Initial fetch of historical kline data
        if not await self._initial_kline_fetch():
            self.bot_logger.critical(f"{COLOR_RED}Failed to fetch initial kline data. Exiting bot.{COLOR_RESET}")
            return

        initial_pos_response = await self.bybit_client.get_positions(category=BYBIT_CATEGORY, symbol=SYMBOL)
        if initial_pos_response and initial_pos_response.get('result') and initial_pos_response['result'].get('list'):
            simulated_message = {"topic": "position", "data": initial_pos_response['result']['list']}
            await self._handle_position_update(simulated_message)
        else:
            await self._handle_position_update({"topic": "position", "data": []})

        # Gather all listener tasks to run concurrently
        listener_tasks = [private_listener_task, public_listener_task]

        async with self.bybit_client:
            try:
                while True:
                    # Ensure klines_df is not None and has enough data for calculations
                    if self.klines_df is None or len(self.klines_df) < max(STOCHRSI_K_PERIOD, ATR_PERIOD):
                        self.bot_logger.warning(f"{COLOR_YELLOW}Insufficient kline data for calculations. Waiting for more data...{COLOR_RESET}")
                        await asyncio.sleep(POLLING_INTERVAL_SECONDS)
                        continue

                    resistance, support = calculate_fibonacci_pivot_points(self.klines_df)

                    # --- Calculate Fibonacci Pivot Levels (if enabled) ---
                    nearest_pivots: Dict[str, Decimal] = {}
                    pivot_support_levels: Dict[str, Decimal] = {}
                    pivot_resistance_levels: Dict[str, Decimal] = {}

                    if ENABLE_FIB_PIVOT_ACTIONS:
                        self.bot_logger.debug(f"Calculating Fibonacci Pivots based on {PIVOT_TIMEFRAME} timeframe...")
                        try:
                            # Fetch data for the pivot timeframe (need previous closed candle)
                            # Fetch 2 candles to ensure we have the completed previous one
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
                                    # Use the second to last row (index -2) which is the *last completed* candle
                                    prev_pivot_candle = pivot_ohlcv_df.iloc[-2]
                                    # Pass a DataFrame with a single row to calculate_fibonacci_pivot_points
                                    temp_df = pd.DataFrame([prev_pivot_candle]).set_index('timestamp')
                                    resistance, support = calculate_fibonacci_pivot_points(temp_df)

                                    # Separate into support and resistance relative to current price
                                    # (This logic is now handled within calculate_fibonacci_pivot_points)
                                    # We just need to extract the levels from the returned lists
                                    for r_level in resistance:
                                        pivot_resistance_levels[r_level['type']] = r_level['price']
                                    for s_level in support:
                                        pivot_support_levels[s_level['type']] = s_level['price']

                                    self.bot_logger.debug(f"Nearest Support Pivots: {pivot_support_levels}")
                                    self.bot_logger.debug(f"Nearest Resistance Pivots: {pivot_resistance_levels}")
                                else:
                                    self.bot_logger.warning(f"{COLOR_YELLOW}Could not fetch sufficient data ({len(pivot_ohlcv_df)} candles) for {PIVOT_TIMEFRAME} pivots.{COLOR_RESET}")
                            else:
                                self.bot_logger.warning(f"{COLOR_YELLOW}Failed to fetch pivot data for {PIVOT_TIMEFRAME}.{COLOR_RESET}")
                        except Exception as pivot_e:
                            log_exception(self.bot_logger, f"Error during Fibonacci Pivot calculation: {pivot_e}", pivot_e)

                    display_market_info(self.klines_df, self.current_price, SYMBOL, resistance, support, self.bot_logger)

                    if not self.position_open:
                        signals = generate_signals(self.klines_df, resistance, support,
                                                   self.active_bull_obs, self.active_bear_obs,
                                                   stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD,
                                                   overbought=STOCHRSI_OVERBOUGHT_LEVEL, oversold=STOCHRSI_OVERSOLD_LEVEL,
                                                   use_crossover=USE_STOCHRSI_CROSSOVER,
                                                   enable_fib_pivot_actions=ENABLE_FIB_PIVOT_ACTIONS,
                                                   fib_entry_confirm_percent=FIB_ENTRY_CONFIRM_PERCENT,
                                                   fib_exit_warn_percent=FIB_EXIT_WARN_PERCENT,
                                                   fib_exit_action=FIB_EXIT_ACTION,
                                                   pivot_support_levels=pivot_support_levels,
                                                   pivot_resistance_levels=pivot_resistance_levels)
                        for signal in signals:
                            signal_type, signal_price, signal_timestamp, signal_info = signal
                            if await self._execute_entry(signal_type, signal_price, signal_timestamp, signal_info):
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
                                                             fib_exit_action=FIB_EXIT_ACTION,
                                                             pivot_support_levels=pivot_support_levels,
                                                             pivot_resistance_levels=pivot_resistance_levels)
                        if exit_signals:
                            for exit_signal in exit_signals:
                                exit_type, exit_price, exit_timestamp, exit_info = exit_signal
                                if await self._execute_exit(exit_type, exit_price, exit_timestamp, exit_info):
                                    break
                        else:
                            self.bot_logger.info(f"{PYRMETHUS_GREY}No exit signals detected for {self.current_position_side} position.{COLOR_RESET}")

                    self.bot_logger.info(f"{PYRMETHUS_ORANGE}Sleeping for {POLLING_INTERVAL_SECONDS} seconds...{COLOR_RESET}")
                    await asyncio.sleep(POLLING_INTERVAL_SECONDS)

            except KeyboardInterrupt:
                self.bot_logger.info(f"{COLOR_YELLOW}Bot stopped by user (KeyboardInterrupt).{COLOR_RESET}")
            except Exception as e:
                log_exception(self.bot_logger, f"Critical error in main loop: {str(e)}", e)
                self.bot_logger.info(f"{COLOR_YELLOW}🔄 Recovering and restarting main loop after 10 seconds...{COLOR_RESET}")
                await asyncio.sleep(10)
            finally:
                # Ensure listener tasks are cancelled on exit
                for task in listener_tasks:
                    task.cancel()
                await asyncio.gather(*listener_tasks, return_exceptions=True) # Await cancellation
                self.bot_logger.info(f"{COLOR_YELLOW}All listener tasks cancelled and awaited.{COLOR_RESET}")

async def main():
    """Entry point for the Pyrmethus Bot."""
    load_dotenv()
    bot = PyrmethusBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        setup_logging().critical(f"Unhandled exception in main execution: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())