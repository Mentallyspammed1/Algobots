import os
import asyncio
import pandas as pd
import logging
import importlib
import time
from typing import Any, Dict, List, Tuple, Union, Optional, Callable
from dotenv import load_dotenv
from decimal import Decimal, getcontext
from algobots_types import OrderBlock

# --- Set Decimal Precision ---
getcontext().prec = 38

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

# --- Import Configuration and Indicator Logic ---
try:
    from config import (
        SYMBOL, INTERVAL, USDT_AMOUNT_PER_TRADE, PIVOT_LEFT_BARS, PIVOT_RIGHT_BARS, PIVOT_TOLERANCE_PCT,
        STOCHRSI_K_PERIOD, STOCHRSI_D_PERIOD, STOCHRSI_OVERBOUGHT_LEVEL,
        STOCHRSI_OVERSOLD_LEVEL, USE_STOCHRSI_CROSSOVER, STOP_LOSS_PCT,
        TAKE_PROFIT_PCT, BYBIT_API_ENDPOINT, BYBIT_CATEGORY, CANDLE_FETCH_LIMIT,
        POLLING_INTERVAL_SECONDS, API_REQUEST_RETRIES, API_BACKOFF_FACTOR, ATR_PERIOD,
        ENABLE_FIB_PIVOT_ACTIONS, PIVOT_TIMEFRAME, FIB_LEVELS_TO_CALC, FIB_NEAREST_COUNT,
        FIB_ENTRY_CONFIRM_PERCENT, FIB_EXIT_WARN_PERCENT, FIB_EXIT_ACTION,
        ATR_MULTIPLIER_SL, ATR_MULTIPLIER_TP, SMA_PERIOD,
        SMA_LENGTH, EHLERS_FISHER_LENGTH, EHLERS_SUPERSMOOTHER_LENGTH, EHLERS_FISHER_SIGNAL_PERIOD,
        MAX_ACTIVE_OBS, HEDGE_MODE, USE_PERCENTAGE_ORDER_SIZING, ORDER_SIZE_PERCENT_OF_BALANCE
    )
    from indicators import (
        calculate_fibonacci_pivot_points, calculate_stochrsi, calculate_atr,
        calculate_sma, calculate_ehlers_fisher_transform, calculate_ehlers_super_smoother,
        find_pivots, handle_websocket_kline_data, calculate_order_book_imbalance
    )
    from bybit_api import BybitContractAPI
    from bot_ui import display_market_info
    from bot_logger import setup_logging, log_trade, log_metrics, log_exception
    from trade_metrics import TradeMetrics
    from utils import calculate_order_quantity
except ImportError as e:
    raise ImportError(f"Missing essential module: {e}. Ensure config.py, indicators.py, bybit_api.py, bot_ui.py, bot_logger.py, trade_metrics.py, utils.py, and algobots_types.py are present and correctly configured.")

# --- Strategy Management ---
from config import STRATEGY_NAME

# Dynamically load the selected strategy
try:
    strategy_module = importlib.import_module(f"strategies.{STRATEGY_NAME.lower()}")
    StrategyClass = getattr(strategy_module, STRATEGY_NAME)
except ImportError:
    raise ImportError(f"Could not import strategy '{STRATEGY_NAME}'. Make sure the file 'strategies/{STRATEGY_NAME.lower()}.py' exists and contains a class named '{STRATEGY_NAME}'.")
except AttributeError:
    raise AttributeError(f"Strategy module 'strategies.{STRATEGY_NAME.lower()}' found, but no class named '{STRATEGY_NAME}' within it.")


class PyrmethusBot:
    """
    The core trading bot logic, encapsulating state, API interactions,
    and trading decisions. It manages its own state, retrieves market data,
    generates trading signals, and executes orders. This version enhances
    robustness, clarity, and incorporates advanced features like ATR-based
    trailing stops and refined order block management.
    """
    def __init__(self):
        self.bot_logger = setup_logging()
        self.trade_metrics = TradeMetrics()
        self.bybit_client: Optional[BybitContractAPI] = None
        self.strategy = StrategyClass(self.bot_logger)

        # --- Bot State Variables (using Decimal for precision) ---
        self.inventory: Decimal = Decimal('0')
        self.entry_price: Decimal = Decimal('0')
        self.unrealized_pnl: Decimal = Decimal('0')
        
        self.entry_price_for_trade_metrics: Decimal = Decimal('0')
        self.entry_fee_for_trade_metrics: Decimal = Decimal('0')
        
        self.current_price: Decimal = Decimal('0') # This will be updated by WS and fetched directly when needed
        self.klines_df: Optional[pd.DataFrame] = None
        self.cached_atr: Optional[Decimal] = None

        # --- Order Block Tracking ---
        self.active_bull_obs: List[OrderBlock] = []
        self.active_bear_obs: List[OrderBlock] = []

        # --- Additional State Variables for Enhancements ---
        self.trailing_stop_active: bool = False
        self.trailing_stop_distance: Decimal = Decimal('0')
        self.last_signal_timestamp: Optional[pd.Timestamp] = None
        self.last_signal_time = time.time()

    @property
    def has_open_position(self) -> bool:
        """Determines if the bot currently holds an open position."""
        return abs(self.inventory) > Decimal('0')

    @property
    def current_position_side(self) -> Optional[str]:
        """Returns the side of the current open position ('Buy', 'Sell', or None)."""
        if self.inventory > Decimal('0'): return 'Buy'
        elif self.inventory < Decimal('0'): return 'Sell'
        return None

    def _reset_position_state(self):
        """Resets all internal state variables related to an open position to their defaults."""
        self.inventory = Decimal('0')
        self.entry_price = Decimal('0')
        self.unrealized_pnl = Decimal('0')
        self.entry_price_for_trade_metrics = Decimal('0')
        self.entry_fee_for_trade_metrics = Decimal('0')
        self.current_price = Decimal('0') # Reset current price as well
        self.trailing_stop_active = False
        self.trailing_stop_distance = Decimal('0')
        self.bot_logger.debug(f"{PYRMETHUS_GREY}Position state reset.{COLOR_RESET}")

    def _identify_and_manage_order_blocks(self):
        """
        Identifies new Pivot High/Low based Order Blocks and manages existing ones using a sliding window approach.
        """
        if self.klines_df is None or self.klines_df.empty:
            self.bot_logger.debug("No klines_df to identify Order Blocks from.")
            return

        window_size = PIVOT_LEFT_BARS + PIVOT_RIGHT_BARS + 1
        if len(self.klines_df) < window_size:
            self.bot_logger.debug(f"Not enough data ({len(self.klines_df)} candles) for pivot calculation. Need at least {window_size}.")
            return

        recent_data = self.klines_df.iloc[-window_size:]
        pivot_highs, pivot_lows = find_pivots(recent_data, PIVOT_LEFT_BARS, PIVOT_RIGHT_BARS, use_wicks=True)

        avg_volume = self.klines_df['volume'].mean() if not self.klines_df.empty else Decimal('0')

        for idx in pivot_highs.index:
            if pivot_highs.loc[idx]:
                candle = self.klines_df.loc[idx]
                ob_top, ob_bottom, volume = candle['high'], candle['low'], candle['volume']
                if ob_top > ob_bottom and volume > avg_volume and not any(ob['timestamp'] == idx for ob in self.active_bear_obs):
                    new_ob: OrderBlock = {
                        'id': f"BEAR_OB_{idx.isoformat()}", 'type': 'bear', 'timestamp': idx,
                        'top': ob_top, 'bottom': ob_bottom, 'active': True, 'violated': False,
                        'violation_ts': None, 'extended_to_ts': idx, 'volume': volume
                    }
                    self.active_bear_obs.append(new_ob)
                    self.bot_logger.info(f"{PYRMETHUS_PURPLE}New Bearish OB identified: {new_ob['id']} at {ob_top:.4f}-{ob_bottom:.4f}, Volume: {volume:.2f}{COLOR_RESET}")

        for idx in pivot_lows.index:
            if pivot_lows.loc[idx]:
                candle = self.klines_df.loc[idx]
                ob_bottom, ob_top, volume = candle['low'], candle['high'], candle['volume']
                if ob_top > ob_bottom and volume > avg_volume and not any(ob['timestamp'] == idx for ob in self.active_bull_obs):
                    new_ob: OrderBlock = {
                        'id': f"BULL_OB_{idx.isoformat()}", 'type': 'bull', 'timestamp': idx,
                        'top': ob_top, 'bottom': ob_bottom, 'active': True, 'violated': False,
                        'violation_ts': None, 'extended_to_ts': idx, 'volume': volume
                    }
                    self.active_bull_obs.append(new_ob)
                    self.bot_logger.info(f"{PYRMETHUS_PURPLE}New Bullish OB identified: {new_ob['id']} at {ob_top:.4f}-{ob_bottom:.4f}, Volume: {volume:.2f}{COLOR_RESET}")

        current_price = self.current_price
        self.active_bull_obs = [ob for ob in self.active_bull_obs if ob['active']]
        self.active_bear_obs = [ob for ob in self.active_bear_obs if ob['active']]

        for ob in self.active_bull_obs:
            if current_price < ob['bottom']:
                ob['active'] = False; ob['violated'] = True; ob['violation_ts'] = self.klines_df.index[-1]
                self.bot_logger.info(f"{PYRMETHUS_RED}Bullish OB {ob['id']} violated by price {current_price:.4f}{COLOR_RESET}")
            else:
                ob['extended_to_ts'] = self.klines_df.index[-1]

        for ob in self.active_bear_obs:
            if current_price > ob['top']:
                ob['active'] = False; ob['violated'] = True; ob['violation_ts'] = self.klines_df.index[-1]
                self.bot_logger.info(f"{PYRMETHUS_RED}Bearish OB {ob['id']} violated by price {current_price:.4f}{COLOR_RESET}")
            else:
                ob['extended_to_ts'] = self.klines_df.index[-1]

        self.active_bull_obs = sorted(self.active_bull_obs, key=lambda x: x['timestamp'], reverse=True)[:MAX_ACTIVE_OBS]
        self.active_bear_obs = sorted(self.active_bear_obs, key=lambda x: x['timestamp'], reverse=True)[:MAX_ACTIVE_OBS]

        self.bot_logger.debug(f"Active OBs after management: Bull={len(self.active_bull_obs)}, Bear={len(self.active_bear_obs)}")

    async def _handle_position_update(self, message: Dict[str, Any]):
        """
        Asynchronous handler for WebSocket position updates.
        """
        if message.get("topic") != "position" or not message.get("data"):
            self.bot_logger.debug(f"Received non-position or empty WS update: {message}")
            return

        pos_data_list = message["data"]
        pos = next((p for p in pos_data_list if p.get('symbol') == SYMBOL), None)

        if not pos or Decimal(pos.get('size', '0')) == Decimal('0'):
            if self.has_open_position:
                self.bot_logger.info(f"{PYRMETHUS_GREEN}🎉 Position for {SYMBOL} closed successfully (inferred from WS data)!{COLOR_RESET}")
                exit_price = self.current_price # Use the last known price
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

        symbol = pos.get('symbol')
        size = Decimal(str(pos.get('size', '0')))
        side = pos.get('side')
        avg_price = Decimal(str(pos.get('avgPrice', '0')))
        unrealized_pnl = Decimal(str(pos.get('unrealisedPnl', '0'))) if pos.get('unrealisedPnl') is not None else Decimal('0')

        signed_inventory = size if side == 'Buy' else -size
        position_size_changed = self.inventory != signed_inventory
        entry_price_changed = self.entry_price != avg_price and size > 0

        if not self.has_open_position and size > 0:
            self.bot_logger.info(f"{PYRMETHUS_GREEN}🎉 Position detected and tracked via WebSocket for {symbol}.{COLOR_RESET}")
            self.entry_price_for_trade_metrics = avg_price
            self.entry_fee_for_trade_metrics = self.trade_metrics.calculate_fee(size, avg_price, is_maker=False)
        elif self.has_open_position and (position_size_changed or entry_price_changed):
            self.bot_logger.info(f"{PYRMETHUS_BLUE}💼 Position details updated via WS for {symbol}.{COLOR_RESET}")

        self.inventory = signed_inventory
        self.entry_price = avg_price
        self.unrealized_pnl = unrealized_pnl
        
        if self.has_open_position:
            self.bot_logger.info(
                f"{PYRMETHUS_BLUE}💼 Open Position (WS): {self.current_position_side} {abs(self.inventory):.4f} {symbol} "
                f"at {self.entry_price:.4f}. Unrealized PnL: {self.unrealized_pnl:.4f}{COLOR_RESET}"
            )
            if position_size_changed or entry_price_changed:
                await self._update_take_profit_stop_loss()

    async def _update_take_profit_stop_loss(self):
        """
        Sets or updates Take Profit and Stop Loss orders, including ATR-based trailing stops.
        """
        if not self.has_open_position:
            self.bot_logger.debug(f"[{SYMBOL}] No open position to set TP/SL for.")
            return

        use_atr_tp_sl = self.cached_atr is not None and ATR_MULTIPLIER_SL is not None and ATR_MULTIPLIER_TP is not None
        use_static_tp_sl = STOP_LOSS_PCT is not None or TAKE_PROFIT_PCT is not None

        if not use_atr_tp_sl and not use_static_tp_sl:
            self.bot_logger.debug(f"[{SYMBOL}] No TP/SL configuration available or applicable.")
            return

        take_profit_price = None
        stop_loss_price = None

        if use_atr_tp_sl:
            try:
                atr_sl_value = self.cached_atr * Decimal(str(ATR_MULTIPLIER_SL))
                atr_tp_value = self.cached_atr * Decimal(str(ATR_MULTIPLIER_TP))

                if self.inventory > 0:  # Long position
                    stop_loss_price = self.entry_price - atr_sl_value
                    take_profit_price = self.entry_price + atr_tp_value
                    if self.trailing_stop_active:
                        new_stop_loss = self.current_price - self.trailing_stop_distance
                        stop_loss_price = max(stop_loss_price, new_stop_loss)
                    else:
                        if stop_loss_price > 0:
                            self.trailing_stop_active = True
                            self.trailing_stop_distance = self.entry_price - (self.entry_price - atr_sl_value)
                            self.bot_logger.info(f"{PYRMETHUS_BLUE}Trailing stop activated for long position. Initial Distance: {self.trailing_stop_distance:.4f}{COLOR_RESET}")

                elif self.inventory < 0:  # Short position
                    stop_loss_price = self.entry_price + atr_sl_value
                    take_profit_price = self.entry_price - atr_sl_value
                    if self.trailing_stop_active:
                        new_stop_loss = self.current_price + self.trailing_stop_distance
                        stop_loss_price = min(stop_loss_price, new_stop_loss)
                    else:
                        if stop_loss_price > 0:
                            self.trailing_stop_active = True
                            self.trailing_stop_distance = (self.entry_price + atr_sl_value) - self.entry_price
                            self.bot_logger.info(f"{PYRMETHUS_BLUE}Trailing stop activated for short position. Initial Distance: {self.trailing_stop_distance:.4f}{COLOR_RESET}")

                self.bot_logger.info(f"{PYRMETHUS_ORANGE}Dynamic TP/SL (ATR-based) for {SYMBOL}: TP={take_profit_price:.4f}, SL={stop_loss_price:.4f}{COLOR_RESET}")
            except Exception as e:
                log_exception(self.bot_logger, f"Error calculating ATR-based TP/SL for {SYMBOL}: {e}", e)
                use_atr_tp_sl = False

        if not use_atr_tp_sl and use_static_tp_sl:
            if self.inventory > 0: # Long position
                if TAKE_PROFIT_PCT: take_profit_price = self.entry_price * (Decimal('1') + Decimal(str(TAKE_PROFIT_PCT)))
                if STOP_LOSS_PCT: stop_loss_price = self.entry_price * (Decimal('1') - Decimal(str(STOP_LOSS_PCT)))
            elif self.inventory < 0: # Short position
                if TAKE_PROFIT_PCT: take_profit_price = self.entry_price * (Decimal('1') - Decimal(str(TAKE_PROFIT_PCT)))
                if STOP_LOSS_PCT: stop_loss_price = self.entry_price * (Decimal('1') + Decimal(str(STOP_LOSS_PCT)))
            
            if take_profit_price or stop_loss_price:
                self.bot_logger.info(f"{PYRMETHUS_ORANGE}Static TP/SL for {SYMBOL}: TP={take_profit_price}, SL={stop_loss_price}{COLOR_RESET}")
            else:
                return

        if take_profit_price or stop_loss_price:
            try:
                tp_sl_kwargs = {
                    "category": BYBIT_CATEGORY, "symbol": SYMBOL,
                    "take_profit": f"{take_profit_price:.4f}" if take_profit_price else None,
                    "stop_loss": f"{stop_loss_price:.4f}" if stop_loss_price else None,
                }
                if HEDGE_MODE: tp_sl_kwargs['positionIdx'] = 1 if self.inventory > 0 else 2
                else: tp_sl_kwargs['positionIdx'] = 0

                if tp_sl_kwargs["take_profit"] and Decimal(tp_sl_kwargs["take_profit"]) <= 0: tp_sl_kwargs["take_profit"] = None
                if tp_sl_kwargs["stop_loss"] and Decimal(tp_sl_kwargs["stop_loss"]) <= 0: tp_sl_kwargs["stop_loss"] = None

                if tp_sl_kwargs["take_profit"] or tp_sl_kwargs["stop_loss"]:
                    await self.bybit_client.set_trading_stop(**tp_sl_kwargs)
                    self.bot_logger.info(f"{PYRMETHUS_GREEN}TP/SL orders submitted for {SYMBOL}. TP: {tp_sl_kwargs['take_profit']}, SL: {tp_sl_kwargs['stop_loss']}{COLOR_RESET}")
            except Exception as e:
                log_exception(self.bot_logger, f"Failed to set TP/SL for {SYMBOL}: {e}", e)

    async def _handle_kline_update(self, message: Dict[str, Any]):
        """
        Asynchronous handler for WebSocket kline updates with optimized DataFrame handling.
        """
        if message.get("topic") != f"kline.{INTERVAL}.{SYMBOL}" or not message.get("data"):
            self.bot_logger.debug(f"Received non-kline or empty WS update: {message}")
            return

        updated_df = handle_websocket_kline_data(self.klines_df, message)
        if updated_df is not None and not updated_df.empty:
            self.klines_df = updated_df
            
            min_data_needed = max(
                STOCHRSI_K_PERIOD + STOCHRSI_D_PERIOD, ATR_PERIOD, SMA_LENGTH,
                EHLERS_FISHER_LENGTH + EHLERS_FISHER_SIGNAL_PERIOD, EHLERS_SUPERSMOOTHER_LENGTH
            )
            
            if len(self.klines_df) >= min_data_needed:
                self.klines_df = calculate_stochrsi(self.klines_df.copy(), rsi_period=STOCHRSI_K_PERIOD, stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD)
                self.klines_df['atr'] = calculate_atr(self.klines_df)
                self.klines_df['sma'] = calculate_sma(self.klines_df, length=SMA_LENGTH)
                self.klines_df['ehlers_fisher'], self.klines_df['ehlers_fisher_signal'] = calculate_ehlers_fisher_transform(self.klines_df, length=EHLERS_FISHER_LENGTH, signal_length=EHLERS_FISHER_SIGNAL_PERIOD)
                self.klines_df['ehlers_supersmoother'] = calculate_ehlers_super_smoother(self.klines_df, length=EHLERS_SUPERSMOOTHER_LENGTH)

                if 'atr' in self.klines_df.columns and not pd.isna(self.klines_df['atr'].iloc[-1]):
                    self.cached_atr = self.klines_df['atr'].iloc[-1]
                else:
                    self.cached_atr = Decimal('0')

                if not self.klines_df['close'].empty:
                    self.current_price = self.klines_df['close'].iloc[-1]
                
                self._identify_and_manage_order_blocks()
                self.bot_logger.debug(f"{PYRMETHUS_CYAN}Kline updated via WebSocket. Current price: {self.current_price:.4f}, ATR: {self.cached_atr:.4f}{COLOR_RESET}")
            else:
                if not self.klines_df['close'].empty:
                    self.current_price = self.klines_df['close'].iloc[-1]
                    self.bot_logger.debug(f"Kline data updated, but insufficient for full indicator calculation. Current price: {self.current_price:.4f}")

    async def _initial_kline_fetch(self) -> bool:
        """
        Fetches initial historical kline data with error recovery and indicator calculation.
        """
        for attempt in range(API_REQUEST_RETRIES + 1):
            try:
                self.bot_logger.info(f"{PYRMETHUS_ORANGE}Fetching initial kline data for {SYMBOL} ({INTERVAL})... Attempt {attempt + 1}{COLOR_RESET}")
                klines_response = await self.bybit_client.get_kline_rest_fallback(
                    category=BYBIT_CATEGORY, symbol=SYMBOL, interval=INTERVAL, limit=CANDLE_FETCH_LIMIT
                )
                
                if not klines_response or klines_response.get('retCode') != 0 or not klines_response.get('result', {}).get('list'):
                    raise ValueError(f"Invalid kline response structure or retCode: {klines_response.get('retMsg', 'N/A')}")

                data = [
                    {
                        'timestamp': pd.to_datetime(int(kline[0]), unit='ms', utc=True),
                        'open': Decimal(str(kline[1])), 'high': Decimal(str(kline[2])), 'low': Decimal(str(kline[3])),
                        'close': Decimal(str(kline[4])), 'volume': Decimal(str(kline[5])),
                    }
                    for kline in klines_response['result']['list']
                ]
                df = pd.DataFrame(data).set_index('timestamp').sort_index()

                min_data_needed = max(
                    STOCHRSI_K_PERIOD + STOCHRSI_D_PERIOD, ATR_PERIOD, SMA_LENGTH,
                    EHLERS_FISHER_LENGTH + EHLERS_FISHER_SIGNAL_PERIOD, EHLERS_SUPERSMOOTHER_LENGTH
                )
                if len(df) < min_data_needed:
                    self.bot_logger.warning(f"{COLOR_YELLOW}Insufficient initial data: {len(df)} candles fetched, but {min_data_needed} are needed for full indicator calculation.{COLOR_RESET}")

                self.klines_df = calculate_stochrsi(df.copy(), rsi_period=STOCHRSI_K_PERIOD, stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD)
                self.klines_df['atr'] = calculate_atr(self.klines_df)
                self.klines_df['sma'] = calculate_sma(self.klines_df, length=SMA_LENGTH)
                self.klines_df['ehlers_fisher'], self.klines_df['ehlers_fisher_signal'] = calculate_ehlers_fisher_transform(self.klines_df, length=EHLERS_FISHER_LENGTH, signal_length=EHLERS_FISHER_SIGNAL_PERIOD)
                self.klines_df['ehlers_supersmoother'] = calculate_ehlers_super_smoother(self.klines_df, length=EHLERS_SUPERSMOOTHER_LENGTH)

                if 'atr' in self.klines_df.columns and not pd.isna(self.klines_df['atr'].iloc[-1]):
                    self.cached_atr = self.klines_df['atr'].iloc[-1]
                else:
                    self.cached_atr = Decimal('0')

                if not self.klines_df['close'].empty:
                    self.current_price = self.klines_df['close'].iloc[-1]
                else:
                    self.current_price = Decimal('0') # Ensure current_price is initialized

                self.bot_logger.info(f"{PYRMETHUS_GREEN}Initial kline data fetched and indicators calculated. Current price: {self.current_price:.4f}, ATR: {self.cached_atr:.4f}{COLOR_RESET}")
                return True
            
            except Exception as e:
                log_exception(self.bot_logger, f"Kline fetch attempt {attempt + 1} failed: {e}", e)
                if attempt < API_REQUEST_RETRIES:
                    await asyncio.sleep(API_BACKOFF_FACTOR * (2 ** attempt))
                else:
                    self.bot_logger.error(f"{COLOR_RED}Failed to fetch initial kline data after {API_REQUEST_RETRIES} retries.{COLOR_RESET}")
                    return False

    async def _execute_entry(self, signal_type: str, signal_price: Decimal, signal_timestamp: Any, signal_info: Dict[str, Any]) -> bool:
        """
        Executes an entry trade with dynamic position sizing based on account balance and volatility.
        """
        self.bot_logger.info(f"{PYRMETHUS_PURPLE}💡 Detected {signal_type.upper()} signal at {signal_price:.4f} (Info: {signal_info}){COLOR_RESET}")

        current_time = time.time()
        if current_time - self.last_signal_time < POLLING_INTERVAL_SECONDS:
             self.bot_logger.warning(f"{PYRMETHUS_YELLOW}Signal received too quickly. Skipping entry.{COLOR_RESET}")
             return False
        self.last_signal_time = current_time

        # --- Fetch current price directly from API for execution ---
        try:
            ticker_info = await self.bybit_client.get_symbol_ticker(category=BYBIT_CATEGORY, symbol=SYMBOL)
            if not ticker_info or ticker_info.get('retCode') != 0 or not ticker_info.get('result', {}).get('list'):
                raise ValueError(f"Failed to fetch ticker info for {SYMBOL}: {ticker_info.get('retMsg', 'N/A')}")
            current_execution_price = Decimal(str(ticker_info['result']['list'][0]['lastPrice']))
            self.bot_logger.debug(f"{PYRMETHUS_CYAN}Fetched current execution price: {current_execution_price:.4f}{COLOR_RESET}")
        except Exception as e:
            log_exception(self.bot_logger, f"Failed to fetch current price for {SYMBOL} before execution: {e}", e)
            return False
        # --- End Fetch ---

        # Use the fetched price for calculations, but keep self.current_price updated by WS
        if current_execution_price <= 0:
            self.bot_logger.error(f"{COLOR_RED}Invalid current execution price ({current_execution_price}) detected. Cannot calculate order quantity or place order.{COLOR_RESET}")
            return False

        try:
            instrument_info_resp = await self.bybit_client.get_instruments_info(category=BYBIT_CATEGORY, symbol=SYMBOL)
            if not instrument_info_resp or instrument_info_resp.get('retCode') != 0 or not instrument_info_resp.get('result', {}).get('list'):
                raise ValueError(f"Failed to fetch instrument info for {SYMBOL}: {instrument_info_resp.get('retMsg', 'N/A')}")
            
            instrument = instrument_info_resp['result']['list'][0]
            min_qty = Decimal(instrument.get('lotSizeFilter', {}).get('minOrderQty', '0'))
            qty_step = Decimal(instrument.get('lotSizeFilter', {}).get('qtyStep', '0'))
            min_order_value = Decimal(instrument.get('lotSizeFilter', {}).get('minOrderIv', '0'))
            
            if min_qty <= 0:
                 self.bot_logger.warning(f"{COLOR_YELLOW}Instrument info missing or invalid minOrderQty for {SYMBOL}. Using default 0.001.{COLOR_RESET}")
                 min_qty = Decimal('0.001') 
            if qty_step <= 0:
                 self.bot_logger.warning(f"{COLOR_YELLOW}Instrument info missing or invalid qtyStep for {SYMBOL}. Using default 0.001.{COLOR_RESET}")
                 qty_step = Decimal('0.001') 
            if min_order_value <= 0:
                 self.bot_logger.warning(f"{COLOR_YELLOW}Instrument info missing or invalid minOrderIv for {SYMBOL}. Using default 10 USDT.{COLOR_RESET}")
                 min_order_value = Decimal('10')

        except Exception as e:
            log_exception(self.bot_logger, f"Error fetching or parsing instrument info for {SYMBOL}: {e}", e)
            return False

        target_usdt_value = USDT_AMOUNT_PER_TRADE
        if USE_PERCENTAGE_ORDER_SIZING:
            try:
                balance_response = await self.bybit_client.get_wallet_balance(accountType="UNIFIED", coin="USDT")
                if balance_response and balance_response.get('retCode') == 0 and balance_response.get('result', {}).get('list'):
                    usdt_balance_data = next((item for item in balance_response['result']['list'] if item['coin'][0]['coin'] == 'USDT'), None)
                    if usdt_balance_data:
                        usdt_balance = Decimal(usdt_balance_data['coin'][0]['walletBalance'])
                        
                        volatility_factor = Decimal('1')
                        # Use the fetched execution price for volatility calculation if available
                        effective_price = current_execution_price if current_execution_price > 0 else self.current_price
                        if self.cached_atr and effective_price > 0:
                            volatility_factor = min(Decimal('1'), Decimal(str(self.cached_atr)) / Decimal(str(effective_price)) if effective_price != 0 else Decimal('1'))
                        
                        target_usdt_value = usdt_balance * (Decimal(str(ORDER_SIZE_PERCENT_OF_BALANCE)) / Decimal('100')) * volatility_factor
                        self.bot_logger.info(f"{PYRMETHUS_BLUE}Dynamic sizing: Balance={usdt_balance:.2f}, Volatility Factor={volatility_factor:.3f}, Target USDT={target_usdt_value:.2f}{COLOR_RESET}")
                    else:
                        self.bot_logger.warning(f"{COLOR_YELLOW}USDT balance not found in wallet response. Using default USDT_AMOUNT_PER_TRADE.{COLOR_RESET}")
                else:
                    self.bot_logger.warning(f"{COLOR_YELLOW}Failed to fetch USDT balance. Using default USDT_AMOUNT_PER_TRADE. Response: {balance_response.get('retMsg', 'N/A')}{COLOR_RESET}")
            except Exception as e:
                log_exception(self.bot_logger, f"Error fetching USDT balance for dynamic sizing: {e}", e)

        if target_usdt_value < min_order_value:
            target_usdt_value = min_order_value
            self.bot_logger.debug(f"{PYRMETHUS_BLUE}Adjusted target USDT to minimum order value: {target_usdt_value:.2f}{COLOR_RESET}")

        quantity = target_usdt_value / current_execution_price # Use fetched price here
        
        if qty_step > 0:
            steps = float(quantity) / float(qty_step)
            quantity = Decimal(str(round(steps))) * qty_step
            
        if quantity < min_qty:
            quantity = min_qty
            self.bot_logger.debug(f"{PYRMETHUS_BLUE}Adjusted quantity to minimum lot size: {quantity:.4f}{COLOR_RESET}")

        order_type = "Market" if "MARKET" in signal_type else "Limit"
        side = "Buy" if "BUY" in signal_type else "Sell"

        order_kwargs = {
            "category": BYBIT_CATEGORY, "symbol": SYMBOL, "side": side,
            "order_type": order_type, "qty": f"{quantity:.8f}",
        }
        if order_type == "Limit": order_kwargs['price'] = f"{signal_price:.4f}"
        
        if HEDGE_MODE: order_kwargs['positionIdx'] = 1 if side == 'Buy' else 2
        else: order_kwargs['positionIdx'] = 0

        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Placing {signal_type.upper()} order: Qty={quantity:.4f} {SYMBOL}, Price={order_kwargs.get('price', 'N/A')}{COLOR_RESET}")
        
        try:
            response = await self.bybit_client.create_order(**order_kwargs)
            
            if response and response.get('retCode') == 0:
                order_id = response.get('result', {}).get('orderId')
                filled_qty = Decimal(response.get('result', {}).get('qty', '0'))
                # Use the actual filled price from the response if available, otherwise fallback
                filled_price = Decimal(response.get('result', {}).get('avgPrice', '0')) if response.get('result', {}).get('avgPrice') else current_execution_price
                
                log_trade(self.bot_logger, "Entry trade executed", {
                    "signal_type": signal_type.upper(), "order_id": order_id, "price": filled_price,
                    "timestamp": str(signal_timestamp), "quantity": filled_qty,
                    "usdt_value": filled_qty * filled_price
                })

                if order_type == "Limit" and order_id:
                    asyncio.create_task(self.chase_limit_order(order_id, SYMBOL, side))
                
                return True
            else:
                self.bot_logger.error(f"{COLOR_RED}Order placement failed for {SYMBOL}. Response: {response.get('retMsg', 'Unknown error')}{COLOR_RESET}")
                return False
        except Exception as e:
            log_exception(self.bot_logger, f"Exception during order execution for {SYMBOL}: {e}", e)
            return False

    async def chase_limit_order(self, order_id: str, symbol: str, side: str, chase_aggressiveness: float = 0.0005):
        """
        Chases a limit order to keep it competitive in the order book.
        """
        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Chasing limit order {order_id} for {symbol} with aggressiveness {chase_aggressiveness:.4f}...{COLOR_RESET}")
        
        max_amendments = 10 
        amendment_count = 0

        while amendment_count < max_amendments:
            await asyncio.sleep(POLLING_INTERVAL_SECONDS)

            try:
                order_status_resp = await self.bybit_client.get_order_status(order_id=order_id, symbol=symbol)
                current_order_status = order_status_resp.get('result', {}).get('list', [{}])[0].get('orderStatus')
                if current_order_status not in ['New', 'PartiallyFilled']:
                    self.bot_logger.info(f"{PYRMETHUS_GREEN}Order {order_id} is no longer active ({current_order_status}). Stopping chase.{COLOR_RESET}")
                    break

                order_book_resp = await self.bybit_client.get_orderbook(category=BYBIT_CATEGORY, symbol=SYMBOL)
                if not order_book_resp or order_book_resp.get('retCode') != 0 or not order_book_resp.get('result'):
                    self.bot_logger.warning(f"{COLOR_YELLOW}Could not fetch order book for chasing order {order_id}.{COLOR_RESET}")
                    continue

                best_bid = Decimal(order_book_resp['result']['b'][0][0])
                best_ask = Decimal(order_book_resp['result']['a'][0][0])
                current_limit_price = Decimal(order_status_resp['result']['list'][0]['price'])

                new_price = None
                if side == 'Buy':
                    if current_limit_price < best_bid * (Decimal('1') - Decimal(chase_aggressiveness)):
                        new_price = best_bid
                elif side == 'Sell':
                    if current_limit_price > best_ask * (Decimal('1') + Decimal(chase_aggressiveness)):
                        new_price = best_ask

                if new_price:
                    amendment_result = await self.bybit_client.amend_order(
                        category=BYBIT_CATEGORY, symbol=symbol, orderId=order_id, price=f"{new_price:.4f}"
                    )
                    if amendment_result and amendment_result.get('retCode') == 0:
                        self.bot_logger.info(f"{PYRMETHUS_BLUE}Amended order {order_id} to price {new_price:.4f}{COLOR_RESET}")
                        amendment_count += 1
                    else:
                        self.bot_logger.error(f"{COLOR_RED}Failed to amend order {order_id}: {amendment_result.get('retMsg', 'Unknown error')}{COLOR_RESET}")
                        if amendment_count > 3: break 
                
            except Exception as e:
                log_exception(self.bot_logger, f"Error chasing order {order_id} for {symbol}: {e}", e)
                if "order not found" in str(e).lower(): break 
                if amendment_count > 5: break

        if amendment_count == max_amendments:
            self.bot_logger.warning(f"{COLOR_YELLOW}Reached maximum amendments ({max_amendments}) for order {order_id}. Stopping chase.{COLOR_RESET}")


    async def _execute_exit(self, exit_type: str, exit_price: Decimal, exit_timestamp: Any, exit_info: Dict[str, Any]) -> bool:
        """
        Executes an exit trade for the current open position.
        """
        self.bot_logger.info(f"{PYRMETHUS_PURPLE}💡 Detected {exit_type.upper()} exit signal at {exit_price:.4f} (Info: {exit_info}){COLOR_RESET}")

        if not self.has_open_position:
            self.bot_logger.warning(f"{COLOR_YELLOW}No open position to exit for {SYMBOL}. Signal ignored.{COLOR_RESET}")
            return False

        side_for_exit = 'Sell' if self.inventory > 0 else 'Buy'
        exit_quantity = abs(self.inventory)

        exit_order_kwargs = {
            "category": BYBIT_CATEGORY, "symbol": SYMBOL, "side": side_for_exit,
            "order_type": "Market", "qty": f"{exit_quantity:.8f}", "positionIdx": 0,
        }
        if HEDGE_MODE: exit_order_kwargs['positionIdx'] = 1 if side_for_exit == 'Buy' else 2

        self.bot_logger.info(f"{PYRMETHUS_ORANGE}Placing {side_for_exit} Market exit order for {exit_quantity:.4f} {SYMBOL}{COLOR_RESET}")
        
        try:
            response = await self.bybit_client.create_order(**exit_order_kwargs)
            
            if response and response.get('retCode') == 0:
                filled_qty = Decimal(response.get('result', {}).get('qty', '0'))
                filled_price = Decimal(response.get('result', {}).get('avgPrice', '0')) if response.get('result', {}).get('avgPrice') else self.current_price 
                
                log_trade(self.bot_logger, "Exit trade executed", {
                    "exit_type": exit_type.upper(), "price": filled_price,
                    "timestamp": str(exit_timestamp), "quantity": filled_qty
                })
                
                self._reset_position_state() 
                
                return True
            else:
                self.bot_logger.error(f"{COLOR_RED}Exit order placement failed for {SYMBOL}. Response: {response.get('retMsg', 'Unknown error')}{COLOR_RESET}")
                return False
        except Exception as e:
            log_exception(self.bot_logger, f"Exception during exit order execution for {SYMBOL}: {e}", e)
            return False

    async def run(self):
        """
        Main execution loop for the Pyrmethus trading bot.
        """
        self.bot_logger.info("Starting Pyrmethus's Ultra Scalper Bot.")

        print(f"{PYRMETHUS_PURPLE}{COLOR_BOLD}\n🚀 Pyrmethus's Ultra Scalper Bot - Awakened{COLOR_RESET}")
        print(f"{PYRMETHUS_PURPLE}{COLOR_BOLD}=========================================={COLOR_RESET}")
        print(f"{PYRMETHUS_ORANGE}\n⚡ Initializing scalping engine...{COLOR_RESET}")

        self.bybit_client = BybitContractAPI(testnet="testnet" in BYBIT_API_ENDPOINT)
        self.bot_logger.info("BybitContractAPI initialized.")

        private_listener_task = asyncio.create_task(self.bybit_client.start_private_websocket_listener(self._handle_position_update))
        await self.bybit_client.subscribe_ws_private_topic("position")

        public_listener_task = asyncio.create_task(self.bybit_client.start_public_websocket_listener(self._handle_kline_update))
        await self.bybit_client.subscribe_ws_public_topic(f"kline.{INTERVAL}.{SYMBOL}")

        if not await self._initial_kline_fetch():
            self.bot_logger.critical(f"{COLOR_RED}Failed to fetch initial kline data. Bot cannot start.{COLOR_RESET}")
            for task in [private_listener_task, public_listener_task]: task.cancel()
            await asyncio.gather(*[private_listener_task, public_listener_task], return_exceptions=True)
            return

        try:
            initial_pos_response = await self.bybit_client.get_positions(category=BYBIT_CATEGORY, symbol=SYMBOL)
            if initial_pos_response and initial_pos_response.get('retCode') == 0 and initial_pos_response.get('result', {}).get('list'):
                await self._handle_position_update({"topic": "position", "data": initial_pos_response['result']['list']})
            else:
                await self._handle_position_update({"topic": "position", "data": []})
        except Exception as e:
            log_exception(self.bot_logger, f"Error fetching initial positions: {e}", e)
            await self._handle_position_update({"topic": "position", "data": []})

        listener_tasks = [private_listener_task, public_listener_task]

        async with self.bybit_client:
            try:
                while True:
                    min_data_needed = max(
                        STOCHRSI_K_PERIOD + STOCHRSI_D_PERIOD, ATR_PERIOD, SMA_LENGTH,
                        EHLERS_FISHER_LENGTH + EHLERS_FISHER_SIGNAL_PERIOD, EHLERS_SUPERSMOOTHER_LENGTH,
                        PIVOT_LEFT_BARS + PIVOT_RIGHT_BARS + 1
                    )
                    if self.klines_df is None or len(self.klines_df) < min_data_needed:
                        self.bot_logger.warning(f"{COLOR_YELLOW}Insufficient kline data: {len(self.klines_df) if self.klines_df is not None else 'None'} candles. Waiting for more data...{COLOR_RESET}")
                        await asyncio.sleep(POLLING_INTERVAL_SECONDS)
                        continue

                    pivot_support_levels: Dict[str, Decimal] = {}
                    pivot_resistance_levels: Dict[str, Decimal] = {}

                    if ENABLE_FIB_PIVOT_ACTIONS:
                        try:
                            pivot_ohlcv_response = await self.bybit_client.get_kline_rest_fallback(
                                category=BYBIT_CATEGORY, symbol=SYMBOL, interval=PIVOT_TIMEFRAME, limit=2
                            )
                            if pivot_ohlcv_response and pivot_ohlcv_response.get('retCode') == 0 and pivot_ohlcv_response['result'].get('list'):
                                pivot_data = [
                                    {
                                        'timestamp': pd.to_datetime(int(kline[0]), unit='ms', utc=True),
                                        'open': Decimal(kline[1]), 'high': Decimal(kline[2]), 'low': Decimal(kline[3]),
                                        'close': Decimal(kline[4]), 'volume': Decimal(kline[5]),
                                    }
                                    for kline in pivot_ohlcv_response['result']['list']
                                ]
                                pivot_ohlcv_df = pd.DataFrame(pivot_data).set_index('timestamp').sort_index()
                                
                                if len(pivot_ohlcv_df) >= 2:
                                    prev_pivot_candle = pivot_ohlcv_df.iloc[-2]
                                    temp_df = pd.DataFrame([prev_pivot_candle]).set_index('timestamp')
                                    
                                    fib_resistance, fib_support = calculate_fibonacci_pivot_points(temp_df)

                                    all_fib_levels = [
                                        {'type': r['type'], 'price': r['price'], 'is_resistance': True} for r in fib_resistance
                                    ] + [
                                        {'type': s['type'], 'price': s['price'], 'is_resistance': False} for s in fib_support
                                    ]
                                    filtered_fib_levels = [level for level in all_fib_levels if any(str(fib_val) in level['type'] for fib_val in FIB_LEVELS_TO_CALC)]
                                    filtered_fib_levels.sort(key=lambda x: abs(x['price'] - self.current_price))
                                    selected_fib_levels = filtered_fib_levels[:FIB_NEAREST_COUNT]

                                    for level in selected_fib_levels:
                                        if level['is_resistance']: pivot_resistance_levels[level['type']] = level['price']
                                        else: pivot_support_levels[level['type']] = level['price']
                        except Exception as e:
                            log_exception(self.bot_logger, f"Error calculating Fibonacci Pivot Points: {e}", e)

                    order_book_imbalance = Decimal('0')
                    try:
                        order_book_response = await self.bybit_client.get_orderbook(category=BYBIT_CATEGORY, symbol=SYMBOL)
                        if order_book_response and order_book_response.get('retCode') == 0 and order_book_response.get('result'):
                            order_book_imbalance, _ = calculate_order_book_imbalance(order_book_response['result'])
                    except Exception as e:
                        log_exception(self.bot_logger, f"Order book fetch error: {e}", e)

                    display_market_info(self.klines_df, self.current_price, SYMBOL, pivot_resistance_levels, pivot_support_levels, order_book_imbalance, self.bot_logger)

                    if not self.has_open_position:
                        signals = self.strategy.generate_signals(
                            self.klines_df, pivot_resistance_levels, pivot_support_levels,
                            self.active_bull_obs, self.active_bear_obs,
                            stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD,
                            overbought=STOCHRSI_OVERBOUGHT_LEVEL, oversold=STOCHRSI_OVERSOLD_LEVEL,
                            use_crossover=USE_STOCHRSI_CROSSOVER,
                            enable_fib_pivot_actions=ENABLE_FIB_PIVOT_ACTIONS,
                            fib_entry_confirm_percent=FIB_ENTRY_CONFIRM_PERCENT,
                            pivot_support_levels=pivot_support_levels, pivot_resistance_levels=pivot_resistance_levels
                        )
                        for signal in signals:
                            signal_type, signal_price, signal_timestamp, signal_info = signal
                            if await self._execute_entry(signal_type, signal_price, signal_timestamp, signal_info):
                                break
                    else:
                        exit_signals = self.strategy.generate_exit_signals(
                            self.klines_df, self.current_position_side,
                            self.active_bull_obs, self.active_bear_obs,
                            stoch_k_period=STOCHRSI_K_PERIOD, stoch_d_period=STOCHRSI_D_PERIOD,
                            overbought=STOCHRSI_OVERBOUGHT_LEVEL, oversold=STOCHRSI_OVERSOLD_LEVEL,
                            use_crossover=USE_STOCHRSI_CROSSOVER,
                            enable_fib_pivot_actions=ENABLE_FIB_PIVOT_ACTIONS,
                            fib_exit_warn_percent=FIB_EXIT_WARN_PERCENT,
                            fib_exit_action=FIB_EXIT_ACTION,
                            pivot_support_levels=pivot_support_levels, pivot_resistance_levels=pivot_resistance_levels
                        )
                        if exit_signals:
                            for exit_signal in exit_signals:
                                exit_type, exit_price, exit_timestamp, exit_info = exit_signal
                                if await self._execute_exit(exit_type, exit_price, exit_timestamp, exit_info):
                                    break

                    await asyncio.sleep(POLLING_INTERVAL_SECONDS)

            except KeyboardInterrupt:
                self.bot_logger.info(f"{COLOR_YELLOW}Bot execution interrupted by user (Ctrl+C).{COLOR_RESET}")
            except Exception as e:
                log_exception(self.bot_logger, f"An unexpected error occurred in the main trading loop: {e}", e)
                await asyncio.sleep(10) 
            finally:
                self.bot_logger.info("Shutting down WebSocket listeners...")
                for task in listener_tasks: task.cancel()
                await asyncio.gather(*listener_tasks, return_exceptions=True)
                self.bot_logger.info("WebSocket listeners stopped.")

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