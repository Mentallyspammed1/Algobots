import os
import asyncio
import pandas as pd
import logging
import importlib
import time
import inspect
from typing import Any, Dict, List, Tuple, Union, Optional, Callable
from dotenv import load_dotenv
from decimal import Decimal, getcontext
from algobots_types import OrderBlock
from datetime import datetime, timedelta
from collections import deque
import traceback
from functools import lru_cache
import numpy as np
from asyncio import Queue
import signal
import sys
import json

# --- Set Decimal Precision ---
getcontext().prec = 38

# --- State Manager Class ---
class StateManager:
    def __init__(self, file_path):
        self.file_path = file_path
        self.state = self.load_state()

    def load_state(self):
        try:
            with open(self.file_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            logging.warning(f"Corrupted state file: {self.file_path}. Starting with empty state.")
            return {}

    def save_state(self):
        with open(self.file_path, 'w') as f:
            json.dump(self.state, f)

    def update_state(self, key, value):
        self.state[key] = value
        self.save_state()

# --- Pyrmethus's Color Codex ---
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_DIM = "\033[2m"
COLOR_RED = "\033[31m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_BLUE = "\033[34m"
COLOR_MAGENTA = "\033[35m"
COLOR_CYAN = "\033[36m"
PYRMETHUS_GREEN = COLOR_GREEN
PYRMETHUS_BLUE = COLOR_BLUE
PYRMETHUS_PURPLE = COLOR_MAGENTA
PYRMETHUS_ORANGE = COLOR_YELLOW
PYRMETHUS_GREY = COLOR_DIM
PYRMETHUS_YELLOW = COLOR_YELLOW
PYRMETHUS_CYAN = COLOR_CYAN

# --- Constants for Stale Data Check ---
MAX_STALENESS_SECONDS = 10  # Max age of data before considered stale
MAX_DATAFRAME_SIZE = 5000  # Maximum rows to keep in DataFrame to prevent memory issues
HEALTH_CHECK_INTERVAL = 300  # Health check every 5 minutes
MAX_CONSECUTIVE_ERRORS = 10  # Max errors before restart

def is_fresh(df: pd.DataFrame) -> bool:
    """
    Checks if the latest data in the DataFrame is fresh.
    Enhanced with better error handling and timezone awareness.
    """
    if df is None or df.empty:
        return False
    
    try:
        if isinstance(df.index, pd.DatetimeIndex):
            latest_ts = df.index[-1]
        else:
            # If index is not DatetimeIndex, try to find timestamp column
            if 'timestamp' in df.columns:
                latest_ts = pd.to_datetime(df['timestamp'].iloc[-1])
            else:
                return False
        
        # Ensure timezone awareness
        if latest_ts.tzinfo is None:
            latest_ts = latest_ts.tz_localize('UTC')
        
        current_time = pd.Timestamp.utcnow()
        age = (current_time - latest_ts).total_seconds()
        return age < MAX_STALENESS_SECONDS
    except Exception as e:
        logging.error(f"Error checking data freshness: {e}")
        return False

# --- Import Configuration and Indicator Logic ---
import config
from indicators import (
    calculate_fibonacci_pivot_points, calculate_stochrsi, calculate_atr,
    calculate_sma, calculate_ehlers_fisher_transform, calculate_ehlers_super_smoother,
    find_pivots, handle_websocket_kline_data, calculate_order_book_imbalance,
    calculate_ehlers_fisher_strategy, calculate_supertrend
)
from bybit_api import BybitContractAPI, BybitAPIError
from bot_ui import display_market_info
from bot_logger import setup_logging, log_trade, log_metrics, log_exception
from trade_metrics import TradeMetrics
from utils import calculate_order_quantity, OrderBook
from order_manager import OrderManager

# --- Strategy Management ---
try:
    strategy_module = importlib.import_module(f"strategies.{config.STRATEGY_NAME.lower()}")
    StrategyClass = getattr(strategy_module, config.STRATEGY_NAME)
except ImportError:
    raise ImportError(f"Could not import strategy '{config.STRATEGY_NAME}'. Make sure the file 'strategies/{config.STRATEGY_NAME.lower()}.py' exists and contains a class named '{config.STRATEGY_NAME}'.")
except AttributeError:
    raise AttributeError(f"Strategy module 'strategies.{config.STRATEGY_NAME.lower()}' found, but no class named '{config.STRATEGY_NAME}' within it.")

def websocket_message_handler(func: Callable):
    """Decorator for handling WebSocket messages with common error handling and metrics."""
    async def wrapper(self, message: Dict[str, Any]):
        self.performance_metrics['ws_messages_received'] += 1
        if not message.get("data"):
            self.bot_logger.debug(f"Received empty update for topic {message.get('topic')}: {message}")
            return
        try:
            await func(self, message)
            self.consecutive_errors = 0  # Reset consecutive error count on success
        except Exception as e:
            self.performance_metrics['ws_errors'] += 1
            self.consecutive_errors += 1
            log_exception(self.bot_logger, f"Error handling WS message in {func.__name__}: {e}", e)
            if self.consecutive_errors > MAX_CONSECUTIVE_ERRORS:
                self.bot_logger.critical(f"{COLOR_RED}Maximum consecutive errors reached. Triggering restart.{COLOR_RESET}")
                asyncio.create_task(self._handle_restart())
    return wrapper


class PyrmethusBot:
    """
    Enhanced core trading bot with improved error handling, data management, and robustness.
    """
    def __init__(self):
        self.bot_logger = setup_logging()
        self.trade_metrics = TradeMetrics()
        self.bybit_client: Optional[BybitContractAPI] = None
        self.order_manager: Optional[OrderManager] = None
        
        # --- Dynamic Strategy Initialization ---
        init_signature = inspect.signature(StrategyClass.__init__)
        strategy_params = {}
        for param in init_signature.parameters.values():
            if param.name in ['self', 'logger']:
                continue
            config_param_name = param.name.upper()
            if hasattr(config, config_param_name):
                strategy_params[param.name] = getattr(config, config_param_name)
        
        self.bot_logger.info(f"Initializing strategy '{config.STRATEGY_NAME}' with parameters: {strategy_params}")
        self.strategy = StrategyClass(self.bot_logger, **strategy_params)
        
        self.order_book = OrderBook(self.bot_logger)
        self.state_manager = StateManager('bot_state.json')

        # --- Bot State Variables (using Decimal for precision) ---
        self.inventory: Decimal = Decimal(self.state_manager.state.get('inventory', '0'))
        self.entry_price: Decimal = Decimal(self.state_manager.state.get('entry_price', '0'))
        self.unrealized_pnl: Decimal = Decimal(self.state_manager.state.get('unrealized_pnl', '0'))
        
        self.entry_price_for_trade_metrics: Decimal = Decimal(self.state_manager.state.get('entry_price_for_trade_metrics', '0'))
        self.entry_fee_for_trade_metrics: Decimal = Decimal(self.state_manager.state.get('entry_fee_for_trade_metrics', '0'))
        
        self.current_price: Decimal = Decimal('0')
        self.klines_df: Optional[pd.DataFrame] = None
        self.cached_atr: Optional[Decimal] = None
        self.last_signal: Optional[Dict[str, Any]] = None
        
        # --- Order Block & Pivot Point Tracking ---
        self.active_bull_obs: List[OrderBlock] = self.state_manager.state.get('active_bull_obs', [])
        self.active_bear_obs: List[OrderBlock] = self.state_manager.state.get('active_bear_obs', [])
        self.last_pivot_calc_timestamp: Optional[pd.Timestamp] = None
        self.pivot_support_levels: Dict[str, Decimal] = {}
        self.pivot_resistance_levels: Dict[str, Decimal] = {}

        # --- Additional State Variables ---
        self.trailing_stop_active: bool = self.state_manager.state.get('trailing_stop_active', False)
        self.trailing_stop_distance: Decimal = Decimal(self.state_manager.state.get('trailing_stop_distance', '0'))
        self.last_signal_timestamp: Optional[pd.Timestamp] = None
        self.last_signal_time = time.time()
        
        # --- Performance Tracking ---
        self.ws_error_count = self.state_manager.state.get('ws_error_count', 0)
        self.max_ws_errors = 50
        self.last_kline_update = time.time()
        self.position_sync_interval = 60  # seconds
        self.last_position_sync = 0
        self.consecutive_errors = self.state_manager.state.get('consecutive_errors', 0)
        self.last_health_check = time.time()
        
        # --- Data Management ---
        self.price_history = deque(self.state_manager.state.get('price_history', []), maxlen=100)  # Keep last 100 prices for analysis
        self.signal_queue = Queue(maxsize=10)  # Queue for signal processing
        self.is_running = True
        self.listener_tasks: List[asyncio.Task] = [] # Store Listener Tasks

        # --- Performance Metrics ---
        self.performance_metrics = self.state_manager.state.get('performance_metrics', {
            'ws_messages_received': 0,
            'ws_errors': 0,
            'orders_placed': 0,
            'orders_filled': 0,
            'signals_generated': 0,
            'last_update': time.time()
        })

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
        """Resets all internal state variables related to an open position."""
        self.inventory = Decimal('0')
        self.entry_price = Decimal('0')
        self.unrealized_pnl = Decimal('0')
        self.entry_price_for_trade_metrics = Decimal('0')
        self.entry_fee_for_trade_metrics = Decimal('0')
        self.trailing_stop_active = False
        self.trailing_stop_distance = Decimal('0')
        self.bot_logger.debug(f"{PYRMETHUS_GREY}Position state reset.{COLOR_RESET}")
        self.state_manager.update_state('inventory', str(self.inventory))
        self.state_manager.update_state('entry_price', str(self.entry_price))
        self.state_manager.update_state('unrealized_pnl', str(self.unrealized_pnl))
        self.state_manager.update_state('entry_price_for_trade_metrics', str(self.entry_price_for_trade_metrics))
        self.state_manager.update_state('entry_fee_for_trade_metrics', str(self.entry_fee_for_trade_metrics))
        self.state_manager.update_state('trailing_stop_active', self.trailing_stop_active)
        self.state_manager.update_state('trailing_stop_distance', str(self.trailing_stop_distance))

    def _manage_dataframe_size(self):
        """Ensures DataFrame doesn't grow too large to prevent memory issues."""
        if self.klines_df is not None and len(self.klines_df) > MAX_DATAFRAME_SIZE:
            self.klines_df = self.klines_df.iloc[-MAX_DATAFRAME_SIZE:]
            self.bot_logger.debug(f"Trimmed DataFrame to {MAX_DATAFRAME_SIZE} rows")

    async def _handle_api_error(self, e: BybitAPIError, context: str = "API call"):
        """
        Centralized API error handling.
        """
        self.bot_logger.error(f"{COLOR_RED}API Error during {context}: {e.ret_code} - {e.ret_msg}{COLOR_RESET}")
        # Specific error codes that might warrant a restart or special handling
        if e.ret_code in [10001, 30034, 30035]:  # Examples: Invalid API Key, Insufficient Balance, Order Not Found
            self.bot_logger.critical(f"{COLOR_RED}Critical API error {e.ret_code}. Triggering restart.{COLOR_RESET}")
            asyncio.create_task(self._handle_restart())
        elif e.ret_code in [10006]: # API rate limit exceeded
            self.bot_logger.warning(f"{COLOR_YELLOW}API rate limit exceeded. Backing off...{COLOR_RESET}")
            await asyncio.sleep(config.API_BACKOFF_FACTOR * 5) # Longer backoff for rate limits
        # Add more specific error handling as needed

    @lru_cache(maxsize=128)
    def _calculate_volatility_factor(self, atr: float, price: float) -> Decimal:
        """Cached volatility factor calculation for performance."""
        if price > 0:
            return min(Decimal('1'), Decimal(str(atr)) / Decimal(str(price)))
        return Decimal('1')

    def _identify_and_manage_order_blocks(self):
        """
        Enhanced order block identification with better error handling and performance.
        """
        if self.klines_df is None or self.klines_df.empty:
            self.bot_logger.debug("No klines_df to identify Order Blocks from.")
            return

        try:
            window_size = config.PIVOT_LEFT_BARS + config.PIVOT_RIGHT_BARS + 1
            if len(self.klines_df) < window_size:
                self.bot_logger.debug(f"Not enough data ({len(self.klines_df)} candles) for pivot calculation. Need at least {window_size}.")
                return

            recent_data = self.klines_df.iloc[-window_size:]
            pivot_highs, pivot_lows = find_pivots(recent_data, config.PIVOT_LEFT_BARS, config.PIVOT_RIGHT_BARS, use_wicks=True)

            avg_volume = self.klines_df['volume'].rolling(window=50).mean().iloc[-1] if self.klines_df is not None and not self.klines_df.empty and len(self.klines_df) >= 50 else Decimal('0')

            bull_ob_timestamps = {ob['timestamp'] for ob in self.active_bull_obs}
            bear_ob_timestamps = {ob['timestamp'] for ob in self.active_bear_obs}

            # Process pivot highs for bearish order blocks
            for idx in pivot_highs.index:
                if pivot_highs.loc[idx].any():
                    candle = self.klines_df.loc[idx]
                    ob_top, ob_bottom, volume = candle['high'], candle['low'], candle['volume']
                    if ob_top > ob_bottom and volume > avg_volume and idx not in bear_ob_timestamps:
                        new_ob: OrderBlock = {
                            'id': f"BEAR_OB_{idx.isoformat()}", 'type': 'bear', 'timestamp': idx,
                            'top': ob_top, 'bottom': ob_bottom, 'active': True, 'violated': False,
                            'violation_ts': None, 'extended_to_ts': idx, 'volume': volume
                        }
                        self.active_bear_obs.append(new_ob)
                        self.bot_logger.info(f"{COLOR_MAGENTA}New Bearish OB identified: {new_ob['id']} at {ob_top:.4f}-{ob_bottom:.4f}, Volume: {volume:.2f}{COLOR_RESET}")

            # Process pivot lows for bullish order blocks
            for idx in pivot_lows.index:
                if pivot_lows.loc[idx].any():
                    candle = self.klines_df.loc[idx]
                    ob_bottom, ob_top, volume = candle['low'], candle['high'], candle['volume']
                    if ob_top > ob_bottom and volume > avg_volume and idx not in bull_ob_timestamps:
                        new_ob: OrderBlock = {
                            'id': f"BULL_OB_{idx.isoformat()}", 'type': 'bull', 'timestamp': idx,
                            'top': ob_top, 'bottom': ob_bottom, 'active': True, 'violated': False,
                            'violation_ts': None, 'extended_to_ts': idx, 'volume': volume
                        }
                        self.active_bull_obs.append(new_ob)
                        self.bot_logger.info(f"{COLOR_MAGENTA}New Bullish OB identified: {new_ob['id']} at {ob_top:.4f}-{ob_bottom:.4f}, Volume: {volume:.2f}{COLOR_RESET}")

            # Manage existing order blocks
            current_price = self.current_price
            self.active_bull_obs = [ob for ob in self.active_bull_obs if ob['active']]
            self.active_bear_obs = [ob for ob in self.active_bear_obs if ob['active']]

            # Check for violations
            for ob in self.active_bull_obs[:]:
                if current_price < ob['bottom']:
                    ob['active'] = False
                    ob['violated'] = True
                    ob['violation_ts'] = self.klines_df.index[-1]
                    self.bot_logger.info(f"{COLOR_RED}Bullish OB {ob['id']} violated by price {current_price:.4f}{COLOR_RESET}")
                else:
                    ob['extended_to_ts'] = self.klines_df.index[-1]

            for ob in self.active_bear_obs[:]:
                if current_price > ob['top']:
                    ob['active'] = False
                    ob['violated'] = True
                    ob['violation_ts'] = self.klines_df.index[-1]
                    self.bot_logger.info(f"{COLOR_RED}Bearish OB {ob['id']} violated by price {current_price:.4f}{COLOR_RESET}")
                else:
                    ob['extended_to_ts'] = self.klines_df.index[-1]

            # Keep only the most recent active order blocks
            self.active_bull_obs = sorted(self.active_bull_obs, key=lambda x: x['timestamp'], reverse=True)[:config.MAX_ACTIVE_OBS]
            self.active_bear_obs = sorted(self.active_bear_obs, key=lambda x: x['timestamp'], reverse=True)[:config.MAX_ACTIVE_OBS]

            self.bot_logger.debug(f"Active OBs after management: Bull={len(self.active_bull_obs)}, Bear={len(self.active_bear_obs)}")
            
        except Exception as e:
            log_exception(self.bot_logger, f"Error in order block management: {e}", e)

    @websocket_message_handler
    async def _handle_orderbook_update(self, message: Dict[str, Any]):
        """
        Enhanced order book update handler with better error handling.
        """
        if not isinstance(self.order_book, OrderBook):
            self.order_book = OrderBook(self.bot_logger)
            self.bot_logger.warning("OrderBook instance was invalid, re-initialized.")

        data = message.get('data', {})
        message_type = message.get('type', 'delta')
        
        if message_type == "snapshot":
            self.order_book.handle_snapshot(data)
        else:
            self.order_book.apply_delta(data)
        self.bot_logger.debug("Order book updated.")

    @websocket_message_handler
    async def _handle_position_update(self, message: Dict[str, Any]):
        """
        Enhanced position update handler with better validation and error handling.
        """
        if message.get("topic") != "position" or not message.get("data"):
            self.bot_logger.debug(f"Received non-position or empty WS update: {message}")
            return

        pos_data_list = message["data"]
        pos = next((p for p in pos_data_list if p.get('symbol') == config.SYMBOL), None)

        if not pos or Decimal(str(pos.get('size', '0'))) == Decimal('0'):
            if self.has_open_position:
                self.bot_logger.info(f"{PYRMETHUS_GREEN}🎉 Position for {config.SYMBOL} closed successfully!{COLOR_RESET}")
                exit_price = self.current_price
                exit_fee = self.trade_metrics.calculate_fee(abs(self.inventory), exit_price, is_maker=False)
                self.trade_metrics.record_trade(
                    self.entry_price_for_trade_metrics, exit_price,
                    abs(self.inventory), self.current_position_side,
                    self.entry_fee_for_trade_metrics, exit_fee, asyncio.get_event_loop().time()
                )
                log_metrics(self.bot_logger, "Overall Trade Statistics", self.trade_metrics.get_trade_statistics())
            self._reset_position_state()
            self.bot_logger.info(f"{PYRMETHUS_GREY}✅ No open position for {config.SYMBOL}. Seeking new opportunities...{COLOR_RESET}")
            return

        # Extract and validate position data
        symbol = pos.get('symbol')
        size = Decimal(str(pos.get('size', '0')))
        side = pos.get('side')
        avg_price = Decimal(str(pos.get('avgPrice', '0')))
        unrealized_pnl = Decimal(str(pos.get('unrealisedPnl', '0'))) if pos.get('unrealisedPnl') is not None else Decimal('0')

        signed_inventory = size if side == 'Buy' else -size
        position_size_changed = self.inventory != signed_inventory
        entry_price_changed = self.entry_price != avg_price and size > 0

        if not self.has_open_position and size > 0:
            self.bot_logger.info(f"{PYRMETHUS_GREEN}🎉 New position detected for {symbol}.{COLOR_RESET}")
            self.entry_price_for_trade_metrics = avg_price
            self.entry_fee_for_trade_metrics = self.trade_metrics.calculate_fee(size, avg_price, is_maker=False)
        elif self.has_open_position and (position_size_changed or entry_price_changed):
            self.bot_logger.info(f"{PYRMETHUS_BLUE}💼 Position updated for {symbol}.{COLOR_RESET}")

        self.inventory = signed_inventory
        self.entry_price = avg_price
        self.unrealized_pnl = unrealized_pnl
        
        if self.has_open_position:
            self.bot_logger.info(
                f"{PYRMETHUS_BLUE}💼 Position: {self.current_position_side} {abs(self.inventory):.4f} {symbol} "
                f"@ {self.entry_price:.4f} | PnL: {self.unrealized_pnl:.4f}{COLOR_RESET}"
            )
            if position_size_changed or entry_price_changed:
                await self._update_take_profit_stop_loss()

    async def _update_take_profit_stop_loss(self):
        """
        Enhanced TP/SL management with better validation and error recovery.
        """
        if not self.has_open_position:
            self.bot_logger.debug(f"No open position to set TP/SL for.")
            return

        try:
            use_atr_tp_sl = (self.cached_atr is not None and 
                           config.ATR_MULTIPLIER_SL is not None and 
                           config.ATR_MULTIPLIER_TP is not None and
                           self.cached_atr > 0)
            use_static_tp_sl = config.STOP_LOSS_PCT is not None or config.TAKE_PROFIT_PCT is not None

            if not use_atr_tp_sl and not use_static_tp_sl:
                self.bot_logger.debug(f"No TP/SL configuration available.")
                return

            take_profit_price = None
            stop_loss_price = None

            if use_atr_tp_sl:
                atr_sl_value = self.cached_atr * Decimal(str(config.ATR_MULTIPLIER_SL))
                atr_tp_value = self.cached_atr * Decimal(str(config.ATR_MULTIPLIER_TP))

                if self.inventory > 0:  # Long position
                    stop_loss_price = self.entry_price - atr_sl_value
                    take_profit_price = self.entry_price + atr_tp_value
                    
                    # Trailing stop logic
                    if self.trailing_stop_active and self.current_price > self.entry_price:
                        new_stop_loss = self.current_price - self.trailing_stop_distance
                        stop_loss_price = max(stop_loss_price, new_stop_loss)
                    elif not self.trailing_stop_active and stop_loss_price > 0:
                        self.trailing_stop_active = True
                        self.trailing_stop_distance = atr_sl_value
                        self.bot_logger.info(f"{PYRMETHUS_BLUE}Trailing stop activated. Distance: {self.trailing_stop_distance:.4f}{COLOR_RESET}")

                elif self.inventory < 0:  # Short position
                    stop_loss_price = self.entry_price + atr_sl_value
                    take_profit_price = self.entry_price - atr_tp_value
                    
                    # Trailing stop logic
                    if self.trailing_stop_active and self.current_price < self.entry_price:
                        new_stop_loss = self.current_price + self.trailing_stop_distance
                        stop_loss_price = min(stop_loss_price, new_stop_loss)
                    elif not self.trailing_stop_active and stop_loss_price > 0:
                        self.trailing_stop_active = True
                        self.trailing_stop_distance = atr_sl_value
                        self.bot_logger.info(f"{PYRMETHUS_BLUE}Trailing stop activated. Distance: {self.trailing_stop_distance:.4f}{COLOR_RESET}")

                self.bot_logger.info(f"{PYRMETHUS_ORANGE}Dynamic TP/SL: TP={take_profit_price:.4f}, SL={stop_loss_price:.4f}{COLOR_RESET}")

            if not use_atr_tp_sl and use_static_tp_sl:
                if self.inventory > 0:  # Long position
                    if config.TAKE_PROFIT_PCT: 
                        take_profit_price = self.entry_price * (Decimal('1') + Decimal(str(config.TAKE_PROFIT_PCT)))
                    if config.STOP_LOSS_PCT: 
                        stop_loss_price = self.entry_price * (Decimal('1') - Decimal(str(config.STOP_LOSS_PCT)))
                elif self.inventory < 0:  # Short position
                    if config.TAKE_PROFIT_PCT: 
                        take_profit_price = self.entry_price * (Decimal('1') - Decimal(str(config.TAKE_PROFIT_PCT)))
                    if config.STOP_LOSS_PCT: 
                        stop_loss_price = self.entry_price * (Decimal('1') + Decimal(str(config.STOP_LOSS_PCT)))
                
                if take_profit_price or stop_loss_price:
                    self.bot_logger.info(f"{PYRMETHUS_ORANGE}Static TP/SL: TP={take_profit_price:.4f if take_profit_price else 'None'}, SL={stop_loss_price:.4f if stop_loss_price else 'None'}{COLOR_RESET}")

            # Execute TP/SL orders
            if take_profit_price or stop_loss_price:
                # Validate prices
                ticker_info = await self.bybit_client.get_symbol_ticker(category=config.BYBIT_CATEGORY, symbol=config.SYMBOL)
                if ticker_info and ticker_info.get('retCode') == 0 and ticker_info.get('result', {}).get('list'):
                    last_price = Decimal(str(ticker_info['result']['list'][0]['lastPrice']))
                    
                    # Adjust SL if too close to current price
                    if self.inventory > 0 and stop_loss_price and stop_loss_price >= last_price * Decimal('0.999'):
                        stop_loss_price = last_price * Decimal('0.995')
                        self.bot_logger.warning(f"{PYRMETHUS_YELLOW}Adjusted SL to {stop_loss_price:.4f}{COLOR_RESET}")
                    elif self.inventory < 0 and stop_loss_price and stop_loss_price <= last_price * Decimal('1.001'):
                        stop_loss_price = last_price * Decimal('1.005')
                        self.bot_logger.warning(f"{PYRMETHUS_YELLOW}Adjusted SL to {stop_loss_price:.4f}{COLOR_RESET}")

                tp_sl_kwargs = {
                    "category": config.BYBIT_CATEGORY, 
                    "symbol": config.SYMBOL,
                    "take_profit": f"{take_profit_price:.4f}" if take_profit_price and take_profit_price > 0 else None,
                    "stop_loss": f"{stop_loss_price:.4f}" if stop_loss_price and stop_loss_price > 0 else None,
                }
                
                if config.HEDGE_MODE:
                    tp_sl_kwargs['positionIdx'] = 1 if self.inventory > 0 else 2
                else:
                    tp_sl_kwargs['positionIdx'] = 0

                if tp_sl_kwargs["take_profit"] or tp_sl_kwargs["stop_loss"]:
                    await self.bybit_client.trading_stop(**tp_sl_kwargs)
                    self.bot_logger.info(f"{PYRMETHUS_GREEN}TP/SL set successfully{COLOR_RESET}")
                    
        except BybitAPIError as e:
            await self._handle_api_error(e, "setting TP/SL")
        except Exception as e:
            log_exception(self.bot_logger, f"Failed to set TP/SL: {e}", e)

    @websocket_message_handler
    async def _handle_public_ws_update(self, message: Dict[str, Any]):
        """
        Enhanced public WebSocket update handler with better error recovery.
        """
        topic = message.get("topic", "")
        if topic.startswith("kline"):
            await self._handle_kline_update(message)
        elif topic.startswith("orderbook"):
            await self._handle_orderbook_update(message)
            
    @websocket_message_handler
    async def _handle_kline_update(self, message: Dict[str, Any]):
        """
        Fixed kline update handler that properly handles timestamp as index.
        """
        topic = message.get("topic", "")
        expected_topic = f"kline.{config.INTERVAL}.{config.SYMBOL}"
        
        if topic != expected_topic or not message.get("data"):
            self.bot_logger.debug(f"Received non-matching or empty kline update")
            return

        # Process the kline data
        updated_df = handle_websocket_kline_data(self.klines_df, message)
        
        if updated_df is not None and not updated_df.empty:
            # Check if timestamp is already the index
            if isinstance(updated_df.index, pd.DatetimeIndex):
                # Timestamp is already the index, no need to convert
                self.klines_df = updated_df
            else:
                # If timestamp is a column, convert it to index
                if 'timestamp' in updated_df.columns:
                    updated_df['timestamp'] = pd.to_datetime(updated_df['timestamp'], unit='ms')
                    updated_df.set_index('timestamp', inplace=True)
                    updated_df.sort_index(inplace=True)
                    self.klines_df = updated_df
                else:
                    self.bot_logger.error("Updated DataFrame has neither timestamp index nor column")
                    return
            
            # Manage DataFrame size
            self._manage_dataframe_size()
            
            # Update price and indicators
            min_data_needed = max(
                config.STOCHRSI_K_PERIOD + config.STOCHRSI_D_PERIOD, 
                config.ATR_PERIOD, 
                config.SMA_LENGTH,
                config.EHLERS_FISHER_LENGTH + config.EHLERS_FISHER_SIGNAL_PERIOD, 
                config.EHLERS_SUPERSMOOTHER_LENGTH
            )
            
            if len(self.klines_df) >= min_data_needed:
                # Calculate ATR and other indicators
                self.klines_df['atr'] = calculate_atr(self.klines_df, length=config.ATR_PERIOD)

                # Update ATR cache
                if not self.klines_df['atr'].empty and not pd.isna(self.klines_df['atr'].iloc[-1]):
                    self.cached_atr = Decimal(str(self.klines_df['atr'].iloc[-1]))
                else:
                    self.bot_logger.warning(f"{COLOR_YELLOW}ATR is NaN or empty after calculation. Setting to 0.{COLOR_RESET}")
                    self.cached_atr = Decimal('0')

                # Update current price
                if 'close' in self.klines_df.columns and not self.klines_df['close'].empty:
                    self.current_price = Decimal(str(self.klines_df['close'].iloc[-1]))
                    self.price_history.append(self.current_price)
                
                # Update order blocks
                self._identify_and_manage_order_blocks()
                
                self.last_kline_update = time.time()
                self.bot_logger.info(f"{COLOR_CYAN}Kline updated. Price: {self.current_price:.4f}, ATR: {self.cached_atr:.4f}{COLOR_RESET}")
            else:
                if 'close' in self.klines_df.columns and not self.klines_df['close'].empty:
                    self.current_price = Decimal(str(self.klines_df['close'].iloc[-1]))
                    self.bot_logger.debug(f"Insufficient data for indicators. Price: {self.current_price:.4f}")
                    
    async def _initial_kline_fetch(self) -> bool:
        """
        Enhanced initial kline fetch with better error handling and retry logic.
        """
        for attempt in range(config.API_REQUEST_RETRIES + 1):
            try:
                self.bot_logger.info(f"{PYRMETHUS_ORANGE}Fetching initial kline data (Attempt {attempt + 1}/{config.API_REQUEST_RETRIES + 1})...{COLOR_RESET}")
                klines_response = await self.bybit_client.get_kline_rest_fallback(
                    category=config.BYBIT_CATEGORY, symbol=config.SYMBOL, interval=config.INTERVAL, limit=config.CANDLE_FETCH_LIMIT
                )

                if not klines_response or klines_response.get('retCode') != 0 or not klines_response.get('result', {}).get('list'):
                    raise ValueError(f"Invalid kline response: {klines_response}")

                data = [{
                    'timestamp': pd.to_datetime(int(kline[0]), unit='ms', utc=True),
                    'open': Decimal(str(kline[1])), 'high': Decimal(str(kline[2])),
                    'low': Decimal(str(kline[3])), 'close': Decimal(str(kline[4])),
                    'volume': Decimal(str(kline[5]))
                } for kline in klines_response['result']['list']]
                
                df = pd.DataFrame(data).set_index('timestamp')
                df.sort_index(inplace=True)
                self.klines_df = df

                min_data_needed = max(
                    config.STOCHRSI_K_PERIOD + config.STOCHRSI_D_PERIOD, 
                    config.ATR_PERIOD, config.SMA_LENGTH,
                    config.EHLERS_FISHER_LENGTH + config.EHLERS_FISHER_SIGNAL_PERIOD, 
                    config.EHLERS_SUPERSMOOTHER_LENGTH
                )
                if len(self.klines_df) < min_data_needed:
                    self.bot_logger.warning(f"{COLOR_YELLOW}Insufficient data fetched ({len(self.klines_df)} candles, {min_data_needed} needed).{COLOR_RESET}")
                
                if 'atr' in self.klines_df.columns and not pd.isna(self.klines_df['atr'].iloc[-1]):
                    self.cached_atr = Decimal(str(self.klines_df['atr'].iloc[-1]))
                else:
                    self.cached_atr = Decimal('0')

                if 'close' in self.klines_df.columns and not self.klines_df['close'].empty:
                    self.current_price = Decimal(str(self.klines_df['close'].iloc[-1]))
                
                self.bot_logger.info(f"{PYRMETHUS_GREEN}Initial kline data fetched successfully. Current price: {self.current_price:.4f}, ATR: {self.cached_atr:.4f}{COLOR_RESET}")
                return True
            except BybitAPIError as e:
                await self._handle_api_error(e, f"fetching initial klines (Attempt {attempt + 1})")
                if attempt < config.API_REQUEST_RETRIES:
                    await asyncio.sleep(config.API_BACKOFF_FACTOR * (2 ** attempt))
                else:
                    self.bot_logger.error(f"{COLOR_RED}Failed to fetch initial kline data after multiple retries.{COLOR_RESET}")
                    return False
            except Exception as e:
                log_exception(self.bot_logger, f"Error fetching initial klines (Attempt {attempt + 1}): {e}", e)
                if attempt < config.API_REQUEST_RETRIES:
                    await asyncio.sleep(config.API_BACKOFF_FACTOR * (2 ** attempt))
                else:
                    self.bot_logger.error(f"{COLOR_RED}Failed to fetch initial kline data after multiple retries.{COLOR_RESET}")
                    return False
    

    async def _update_pivot_points_if_needed(self):
        """
        Calculates Fibonacci pivot points only when a new candle for the pivot timeframe has closed.
        This is a major optimization to prevent redundant API calls and calculations.
        """
        if not config.ENABLE_FIB_PIVOT_ACTIONS:
            return

        try:
            # Fetch the last 2 candles of the pivot timeframe to get the most recently closed one
            pivot_ohlcv_response = await self.bybit_client.get_kline_rest_fallback(
                category=config.BYBIT_CATEGORY, symbol=config.SYMBOL, interval=config.PIVOT_TIMEFRAME, limit=2
            )

            if not (pivot_ohlcv_response and pivot_ohlcv_response.get('retCode') == 0 and pivot_ohlcv_response['result'].get('list')):
                self.bot_logger.warning("Could not fetch pivot point data.")
                return

            # The second to last candle is the most recently closed one
            last_closed_pivot_candle_data = pivot_ohlcv_response['result']['list'][-2]
            candle_timestamp = pd.to_datetime(int(last_closed_pivot_candle_data[0]), unit='ms', utc=True)

            # If we haven't calculated pivots before, or if a new candle has appeared
            if self.last_pivot_calc_timestamp is None or candle_timestamp > self.last_pivot_calc_timestamp:
                self.bot_logger.info(f"{PYRMETHUS_BLUE}New {config.PIVOT_TIMEFRAME} candle detected. Recalculating Fibonacci pivot points...{COLOR_RESET}")
                
                # Create a temporary DataFrame for the calculation
                temp_df = pd.DataFrame([{
                    'timestamp': candle_timestamp,
                    'open': Decimal(last_closed_pivot_candle_data[1]), 
                    'high': Decimal(last_closed_pivot_candle_data[2]), 
                    'low': Decimal(last_closed_pivot_candle_data[3]),
                    'close': Decimal(last_closed_pivot_candle_data[4]), 
                    'volume': Decimal(last_closed_pivot_candle_data[5]),
                }]).set_index('timestamp')

                fib_resistance, fib_support = calculate_fibonacci_pivot_points(temp_df)

                # Reset and update the bot's pivot level state
                self.pivot_resistance_levels = {r['type']: r['price'] for r in fib_resistance}
                self.pivot_support_levels = {s['type']: s['price'] for s in fib_support}
                self.last_pivot_calc_timestamp = candle_timestamp

                self.bot_logger.info(f"Pivot Points Updated: R={self.pivot_resistance_levels}, S={self.pivot_support_levels}")

        except Exception as e:
            log_exception(self.bot_logger, f"Error updating Fibonacci Pivot Points: {e}", e)


    async def _handle_restart(self):
        """Handles bot restart by stopping and starting the main loop."""
        self.bot_logger.info(f"{PYRMETHUS_YELLOW}Initiating bot restart...{COLOR_RESET}")
        await self.shutdown()
        await asyncio.sleep(10)  # Give some time before restarting
        asyncio.create_task(self.run())  # Start a new main loop task

    async def shutdown(self):
        """Gracefully shuts down the bot and its WebSocket listeners."""
        self.bot_logger.info("Shutting down WebSocket listeners...")
        for task in self.listener_tasks:
            task.cancel()
        await asyncio.gather(*self.listener_tasks, return_exceptions=True)
        self.bot_logger.info("WebSocket listeners stopped.")
        self.state_manager.save_state()
        self.bot_logger.info("Bot state saved.")

    async def run(self):
        """
        Main execution loop for the Pyrmethus trading bot.
        """
        self.bot_logger.info("Starting Pyrmethus's Ultra Scalper Bot.")

        print(f"{PYRMETHUS_PURPLE}{COLOR_BOLD}\n🚀 Pyrmethus's Ultra Scalper Bot - Awakened{COLOR_RESET}")
        print(f"{PYRMETHUS_PURPLE}{COLOR_BOLD}=========================================={COLOR_RESET}")
        print(f"{PYRMETHUS_ORANGE}\n⚡ Initializing scalping engine...{COLOR_RESET}")

        self.bybit_client = BybitContractAPI(testnet="testnet" in config.BYBIT_API_ENDPOINT)
        self.order_manager = OrderManager(self.bybit_client, self)
        self.bot_logger.info("BybitContractAPI and OrderManager initialized.")

        private_listener_task = asyncio.create_task(self.bybit_client.start_private_websocket_listener(self._handle_position_update))
        await self.bybit_client.subscribe_ws_private_topic("position")

        public_listener_task = asyncio.create_task(self.bybit_client.start_public_websocket_listener(self._handle_public_ws_update))
        await self.bybit_client.subscribe_ws_public_topic(f"kline.{config.INTERVAL}.{config.SYMBOL}")
        await self.bybit_client.subscribe_ws_public_topic(f"orderbook.50.{config.SYMBOL}")

        self.listener_tasks = [private_listener_task, public_listener_task] # Store Listener tasks

        if not await self._initial_kline_fetch():
            self.bot_logger.critical(f"{COLOR_RED}Failed to fetch initial kline data. Bot cannot start.{COLOR_RESET}")
            await self.shutdown()
            return

        try:
            initial_pos_response = await self.bybit_client.get_positions(category=config.BYBIT_CATEGORY, symbol=config.SYMBOL)
            if initial_pos_response and initial_pos_response.get('retCode') == 0 and initial_pos_response.get('result', {}).get('list'):
                await self._handle_position_update({"topic": "position", "data": initial_pos_response['result']['list']})
            else:
                await self._handle_position_update({"topic": "position", "data": []})
        except Exception as e:
            log_exception(self.bot_logger, f"Error fetching initial positions: {e}", e)
            await self._handle_position_update({"topic": "position", "data": []})


        async with self.bybit_client:
            try:
                while True:
                    # --- Data Sufficiency Check ---
                    min_data_needed = max(
                        config.STOCHRSI_K_PERIOD + config.STOCHRSI_D_PERIOD, 
                        config.ATR_PERIOD, 
                        config.SMA_LENGTH,
                        config.EHLERS_FISHER_LENGTH + config.EHLERS_FISHER_SIGNAL_PERIOD, 
                        config.EHLERS_SUPERSMOOTHER_LENGTH,
                        config.PIVOT_LEFT_BARS + config.PIVOT_RIGHT_BARS + 1,
                        config.WARMUP_PERIOD  # Ensure a minimum number of candles for stability
                    )

                    if self.klines_df is None or len(self.klines_df) < min_data_needed:
                        if self.klines_df is not None:
                            self.bot_logger.warning(f"{COLOR_YELLOW}Warming up... Need {min_data_needed} candles, have {len(self.klines_df)}. Waiting for more data...{COLOR_RESET}")
                        else:
                            self.bot_logger.warning(f"{COLOR_YELLOW}Kline data not yet available. Waiting...{COLOR_RESET}")
                        await asyncio.sleep(config.POLLING_INTERVAL_SECONDS)
                        continue

                    # --- Data Freshness Check ---
                    if not is_fresh(self.klines_df):
                        self.bot_logger.warning(f"{PYRMETHUS_YELLOW}Stale kline data detected. Skipping this cycle.{COLOR_RESET}")
                        await asyncio.sleep(config.POLLING_INTERVAL_SECONDS)
                        continue

                    # --- Indicator Sanity Check ---
                    critical_indicators = {
                        'close': self.klines_df.get('close'),
                        'atr': self.klines_df.get('atr'),
                        'ehlers_supersmoother': self.klines_df.get('ehlers_supersmoother')
                    }

                    indicators_valid = True
                    for name, series in critical_indicators.items():
                        if series is None or series.empty or pd.isna(series.iloc[-1]):
                            self.bot_logger.warning(f"{COLOR_YELLOW}Latest '{name}' value is missing or NaN. Waiting for valid data...{COLOR_RESET}")
                            indicators_valid = False
                            break
                    
                    if not indicators_valid:
                        await asyncio.sleep(config.POLLING_INTERVAL_SECONDS)
                        continue

                    # --- Pivot Point Calculation (Optimized) ---
                    await self._update_pivot_points_if_needed()

                    order_book_imbalance, total_volume = self.order_book.get_imbalance()

                    display_market_info(self.klines_df, self.current_price, config.SYMBOL, self.pivot_resistance_levels, self.pivot_support_levels, self.bot_logger, order_book_imbalance, self.last_signal)

                    if not self.has_open_position:
                        signals = self.strategy.generate_signals(
                            self.klines_df, self.pivot_resistance_levels, self.pivot_support_levels,
                            self.active_bull_obs, self.active_bear_obs,
                            current_position_side=self.current_position_side or 'NONE',
                            current_position_size=abs(self.inventory),
                            order_book_imbalance=order_book_imbalance
                        )
                        for signal in signals:
                            signal_type, signal_price, signal_timestamp, signal_info = signal
                            if await self.order_manager.execute_entry(signal_type, signal_price, signal_timestamp, signal_info):
                                break
                    else:
                        exit_signals = self.strategy.generate_exit_signals(
                            self.klines_df, self.current_position_side,
                            self.active_bull_obs, self.active_bear_obs,
                            entry_price=self.entry_price,
                            pnl=self.unrealized_pnl,
                            current_position_size=abs(self.inventory),
                            order_book_imbalance=order_book_imbalance
                        )

                    await asyncio.sleep(config.POLLING_INTERVAL_SECONDS)

            except KeyboardInterrupt:
                self.bot_logger.info(f"{COLOR_YELLOW}Bot execution interrupted by user (Ctrl+C).{COLOR_RESET}")
            except Exception as e:
                log_exception(self.bot_logger, f"An unexpected error occurred in the main trading loop: {e}", e)
                await asyncio.sleep(10)
            finally:
                await self.shutdown()

async def main():
    """
    Entry point for the Pyrmethus Bot.
    """
    load_dotenv()
    bot = PyrmethusBot()
    try:
        await bot.run()
    except Exception as e:
        setup_logging().critical(f"Critical error in main execution: {e}", exc_info=True)
        print(f"{COLOR_RED}Critical error encountered. Please check the logs for details.{COLOR_RESET}")

if __name__ == "__main__":
    asyncio.run(main())
