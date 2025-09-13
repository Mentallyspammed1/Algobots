# bybit_trading_bot.py

import asyncio
import json
import logging
import time
import uuid # For generating unique client order IDs
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Any, Dict, List, Optional, Tuple, Union
import importlib # For dynamic strategy loading
from zoneinfo import ZoneInfo # For consistent timezone handling

import pandas as pd
from pybit.unified_trading import HTTP, WebSocket

# Import local modules
from config import Config
from unanimous_logger import setup_logger # Redundant here, but good for context
from precision_manager import PrecisionManager
from order_sizing import OrderSizingCalculator
from trailing_stop import TrailingStopManager
from trade_metrics import Trade, TradeMetricsTracker
from pnl_manager import PnLManager
from orderbook_manager import AdvancedOrderbookManager
from strategy_interface import BaseStrategy, Signal # Base strategy and Signal class
from market_analyzer import MarketAnalyzer # Market conditions analyzer
from alert_system import AlertSystem # Alerting system
from utilities import KlineDataFetcher, InMemoryCache # Utilities
from advanced_features import AdvancedFeatures # New Advanced Features class


# --- Main Trading Bot Class ---
class BybitTradingBot:
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger('TradingBot') # Logger already configured by setup_logger in main

        # --- Initialize Pybit HTTP client ---
        self.http_session = HTTP(
            testnet=self.config.TESTNET, 
            api_key=self.config.BYBIT_API_KEY, 
            api_secret=self.config.BYBIT_API_SECRET
        )
        
        # --- Initialize Core Managers ---
        self.precision_manager = PrecisionManager(self.http_session, self.logger)
        self.order_sizing_calculator = OrderSizingCalculator(self.precision_manager, self.logger)
        self.trailing_stop_manager = TrailingStopManager(self.http_session, self.precision_manager, self.logger)
        self.trade_metrics_tracker = TradeMetricsTracker(self.logger, config_file_path=self.config.TRADE_HISTORY_CSV)
        self.pnl_manager = PnLManager(self.http_session, self.precision_manager, self.trade_metrics_tracker, self.logger, initial_balance_usd=self.config.INITIAL_ACCOUNT_BALANCE)
        self.orderbook_manager = AdvancedOrderbookManager(self.config.SYMBOL, self.config.USE_SKIP_LIST_FOR_ORDERBOOK, self.logger)
        self.market_analyzer = MarketAnalyzer(self.logger, 
                                              trend_detection_period=self.config.TREND_DETECTION_PERIOD,
                                              volatility_detection_atr_period=self.config.VOLATILITY_DETECTION_ATR_PERIOD,
                                              adx_period=self.config.ADX_PERIOD,
                                              adx_trend_strong_threshold=self.config.ADX_TREND_STRONG_THRESHOLD,
                                              adx_trend_weak_threshold=self.config.ADX_TREND_WEAK_THRESHOLD)
        self.alert_system = AlertSystem(self.config, self.logger)
        self.kline_data_fetcher = KlineDataFetcher(self.http_session, self.logger, self.config) # New fetcher utility
        self.kline_cache = InMemoryCache(ttl_seconds=self.config.TRADING_LOGIC_LOOP_INTERVAL_SECONDS * 0.8, max_size=5) # Cache klines per interval

        # --- Advanced Features Module ---
        self.advanced_features = AdvancedFeatures(self.logger, self.config)


        # --- Dynamic Strategy Loading ---
        self.strategy: Optional[BaseStrategy] = None
        self._load_strategy()

        # --- WebSocket Clients ---
        self.ws_public: Optional[WebSocket] = None
        self.ws_private: Optional[WebSocket] = None
        
        # --- Bot State ---
        self.is_running = True
        self.loop_iteration = 0
        self.active_orders: Dict[str, Dict[str, Any]] = {}
        self.current_market_price: float = 0.0 # Updated from ticker/orderbook WS
        self.current_kline_data: pd.DataFrame = pd.DataFrame() # For indicators
        self.current_indicators: Dict[str, float] = {} # Latest indicator values from strategy
        self.daily_pnl_tracking_date: date = date.today() # For daily drawdown
        self.day_start_equity: Decimal = Decimal('0') # Equity at start of day

        self.logger.info(f"Bot initialized for {self.config.SYMBOL} (Category: {self.config.CATEGORY}, Leverage: {self.config.LEVERAGE}, Testnet: {self.config.TESTNET}).")

    def _load_strategy(self):
        """Dynamically loads the trading strategy specified in the config."""
        try:
            strategy_module_name = self.config.ACTIVE_STRATEGY_MODULE
            strategy_class_name = self.config.ACTIVE_STRATEGY_CLASS
            
            # Dynamically import the module
            module = importlib.import_module(strategy_module_name)
            
            # Get the class from the module
            strategy_class = getattr(module, strategy_class_name)
            
            # Instantiate the strategy (pass logger and any strategy-specific parameters from config)
            strategy_params = {
                'STRATEGY_EMA_FAST_PERIOD': self.config.STRATEGY_EMA_FAST_PERIOD,
                'STRATEGY_EMA_SLOW_PERIOD': self.config.STRATEGY_EMA_SLOW_PERIOD,
                'STRATEGY_RSI_PERIOD': self.config.STRATEGY_RSI_PERIOD,
                'STRATEGY_RSI_OVERSOLD': self.config.STRATEGY_RSI_OVERSOLD,
                'STRATEGY_RSI_OVERBOUGHT': self.config.STRATEGY_RSI_OVERBOUGHT,
                'STRATEGY_MACD_FAST_PERIOD': self.config.STRATEGY_MACD_FAST_PERIOD,
                'STRATEGY_MACD_SLOW_PERIOD': self.config.STRATEGY_MACD_SLOW_PERIOD,
                'STRATEGY_MACD_SIGNAL_PERIOD': self.config.STRATEGY_MACD_SIGNAL_PERIOD,
                'STRATEGY_BB_PERIOD': self.config.STRATEGY_BB_PERIOD,
                'STRATEGY_BB_STD': self.config.STRATEGY_BB_STD,
                'STRATEGY_ATR_PERIOD': self.config.STRATEGY_ATR_PERIOD,
                'STRATEGY_ADX_PERIOD': self.config.STRATEGY_ADX_PERIOD,
                'STRATEGY_BUY_SCORE_THRESHOLD': self.config.STRATEGY_BUY_SCORE_THRESHOLD,
                'STRATEGY_SELL_SCORE_THRESHOLD': self.config.STRATEGY_SELL_SCORE_THRESHOLD,
            }
            self.strategy = strategy_class(self.logger, **strategy_params)
            self.logger.info(f"Successfully loaded strategy: {self.strategy.strategy_name}")
        except Exception as e:
            self.logger.critical(f"Failed to load trading strategy '{self.config.ACTIVE_STRATEGY_CLASS}' from '{self.config.ACTIVE_STRATEGY_MODULE}': {e}", exc_info=True)
            self.is_running = False

    async def _handle_public_ws_message(self, message: str):
        """Callback for public WebSocket messages (orderbook, ticker)."""
        try:
            data = json.loads(message)
            topic = data.get('topic')

            if topic and 'orderbook' in topic:
                if data.get('type') == 'snapshot':
                    await self.orderbook_manager.update_snapshot(data['data'])
                elif data.get('type') == 'delta':
                    await self.orderbook_manager.update_delta(data['data'])
                
                best_bid, best_ask = await self.orderbook_manager.get_best_bid_ask()
                if best_bid and best_ask:
                    self.current_market_price = (best_bid + best_ask) / 2
                    self.logger.debug(f"Market Price from OB: {self.current_market_price:.4f}")

            elif topic and 'tickers' in topic:
                for ticker_entry in data.get('data', []):
                    if ticker_entry.get('symbol') == self.config.SYMBOL:
                        self.current_market_price = float(ticker_entry.get('lastPrice', self.current_market_price))
                        self.logger.debug(f"Ticker update: {self.current_market_price:.4f}")
                        break

        except json.JSONDecodeError:
            await self.alert_system.send_alert(f"Failed to decode public WS message: {message}", level="ERROR", alert_type="WS_PUBLIC_ERROR")
            self.logger.error(f"Failed to decode public WS message: {message}")
        except Exception as e:
            await self.alert_system.send_alert(f"Error processing public WS message: {e} | Message: {message[:100]}...", level="ERROR", alert_type="WS_PUBLIC_ERROR")
            self.logger.error(f"Error processing public WS message: {e} | Message: {message[:100]}...", exc_info=True)

    async def _handle_private_ws_message(self, message: str):
        """Callback for private WebSocket messages (position, order, execution, wallet)."""
        try:
            data = json.loads(message)
            await self.pnl_manager.update_account_state_from_ws(data)

            topic = data.get('topic')
            if topic == 'order':
                for order_entry in data.get('data', []):
                    if order_entry.get('symbol') == self.config.SYMBOL:
                        order_id = order_entry.get('orderId')
                        order_status = order_entry.get('orderStatus')
                        # Update active orders list
                        if order_id:
                            if order_status in ['New', 'PartiallyFilled', 'Untriggered', 'Created']:
                                self.active_orders[order_id] = order_entry
                            elif order_status in ['Filled', 'Cancelled', 'Rejected']:
                                # This is where you would link order_id to a Trade object and mark it closed
                                # and update TradeMetricsTracker. For now, it's done via PnLManager.
                                self.active_orders.pop(order_id, None) 
                            self.logger.info(f"Order {order_id} ({order_entry.get('side')} {order_entry.get('qty')} @ {order_entry.get('price')}) status: {order_status}")

        except json.JSONDecodeError:
            await self.alert_system.send_alert(f"Failed to decode private WS message: {message}", level="ERROR", alert_type="WS_PRIVATE_ERROR")
            self.logger.error(f"Failed to decode private WS message: {message}")
        except Exception as e:
            await self.alert_system.send_alert(f"Error processing private WS message: {e} | Message: {message[:100]}...", level="ERROR", alert_type="WS_PRIVATE_ERROR")
            self.logger.error(f"Error processing private WS message: {e} | Message: {message[:100]}...", exc_info=True)

    async def _start_websocket_listener(self, ws_client: WebSocket, handler_func, topics: List[str]):
        """Starts a WebSocket listener for a given pybit client, handling reconnections."""
        while self.is_running:
            try:
                self.logger.info(f"Attempting to connect and subscribe to {ws_client.channel_type} WebSocket...")
                
                # Subscribe to all relevant topics dynamically
                for topic_str in topics:
                    if topic_str == 'position': ws_client.position_stream(callback=handler_func)
                    elif topic_str == 'order': ws_client.order_stream(callback=handler_func)
                    elif topic_str == 'execution': ws_client.execution_stream(callback=handler_func)
                    elif topic_str == 'wallet': ws_client.wallet_stream(callback=handler_func)
                    elif 'orderbook' in topic_str: ws_client.orderbook_stream(depth=self.config.ORDERBOOK_DEPTH_LIMIT, symbol=self.config.SYMBOL, callback=handler_func)
                    elif 'tickers' in topic_str: ws_client.ticker_stream(symbol=self.config.SYMBOL, callback=handler_func)
                    # Add kline stream if you want to update DataFrame in real-time,
                    # but ensure robust merging logic to avoid data gaps.
                    # For now, fetching klines via REST is more suitable for historical data for indicators.
                    elif 'kline' in topic_str:
                        self.logger.warning(f"Kline stream '{topic_str}' is configured but not actively handled for data processing in this loop using WS.")
                    else:
                        self.logger.warning(f"Unknown or unhandled WebSocket topic: {topic_str}. Skipping subscription.")
                
                while self.is_running and ws_client.is_connected():
                    await asyncio.sleep(1)
                
                self.logger.warning(f"{ws_client.channel_type} WebSocket disconnected or connection lost. Attempting reconnect in {self.config.RECONNECT_DELAY_SECONDS}s.")
                await asyncio.sleep(self.config.RECONNECT_DELAY_SECONDS)

            except Exception as e:
                await self.alert_system.send_alert(f"Error in {ws_client.channel_type} WebSocket listener: {e}", level="ERROR", alert_type="WS_LISTENER_FAIL")
                self.logger.error(f"Error in {ws_client.channel_type} WebSocket listener: {e}", exc_info=True)
                await asyncio.sleep(self.config.RECONNECT_DELAY_SECONDS)

    async def setup_initial_state(self):
        """Performs initial setup, fetches account info, and sets leverage."""
        self.logger.info("Starting initial bot setup...")
        retries = 3
        for i in range(retries):
            try:
                # 0. Load Instruments and Fees
                await self.precision_manager.load_all_instruments(retry_delay=self.config.API_RETRY_DELAY_SECONDS, max_retries=retries)
                if not self.precision_manager.is_loaded:
                    raise Exception("Failed to load instrument specifications. Critical for precision.")
                await self.precision_manager.fetch_and_update_fee_rates(self.config.CATEGORY, self.config.SYMBOL)


                # 1. Initialize Balance
                await self.pnl_manager.initialize_balance(category=self.config.CATEGORY, retry_delay=self.config.API_RETRY_DELAY_SECONDS, max_retries=retries)
                if self.pnl_manager.initial_balance_usd == Decimal('0'):
                    raise Exception("Initial account balance is zero or failed to load.")
                self.day_start_equity = self.pnl_manager.current_balance_usd # Set initial daily equity


                # 2. Set Leverage (only for derivatives)
                if self.config.CATEGORY != 'spot':
                    response = self.http_session.set_leverage(
                        category=self.config.CATEGORY, symbol=self.config.SYMBOL,
                        buyLeverage=str(self.config.LEVERAGE), sellLeverage=str(self.config.LEVERAGE)
                    )
                    if response['retCode'] == 0:
                        self.logger.info(f"Leverage set to {self.config.LEVERAGE}x for {self.config.SYMBOL}.")
                    else:
                        self.logger.error(f"Failed to set leverage: {response['retMsg']} (Code: {response['retCode']}).")
                        raise Exception(f"Failed to set leverage: {response['retMsg']}")

                # 3. Get Current Positions and populate PnLManager
                position_resp = self.http_session.get_positions(category=self.config.CATEGORY, symbol=self.config.SYMBOL)
                if position_resp['retCode'] == 0 and position_resp['result']['list']:
                    for pos_data in position_resp['result']['list']:
                        await self.pnl_manager.update_account_state_from_ws({'topic': 'position', 'data': [pos_data]})
                    self.logger.info(f"Initial Position: {await self.pnl_manager.get_position_summary(self.config.SYMBOL)}")
                else:
                    self.logger.info(f"No initial position found for {self.config.SYMBOL}.")
                
                # 4. Get Open Orders and populate active_orders
                open_orders_resp = self.http_session.get_open_orders(category=self.config.CATEGORY, symbol=self.config.SYMBOL)
                if open_orders_resp['retCode'] == 0 and open_orders_resp['result']['list']:
                    for order in open_orders_resp['result']['list']:
                        self.active_orders[order['orderId']] = order
                    self.logger.info(f"Found {len(self.active_orders)} active orders on startup.")
                else:
                    self.logger.info("No initial active orders found.")

                self.logger.info("Bot initial setup complete.")
                return # Setup successful

            except Exception as e:
                await self.alert_system.send_alert(f"Critical error during initial setup: {e}", level="CRITICAL", alert_type="BOT_INIT_FAIL")
                self.logger.critical(f"Critical error during initial setup (Attempt {i+1}/{retries}): {e}", exc_info=True)
                if i < retries - 1:
                    await asyncio.sleep(self.config.API_RETRY_DELAY_SECONDS * (i + 1))
        
        self.logger.critical("Initial setup failed after multiple retries. Shutting down bot.")
        self.is_running = False

    async def place_order(
        self, 
        side: str, 
        qty: Decimal, 
        price: Optional[Decimal] = None, 
        order_type: str = 'Limit', 
        stop_loss_price: Optional[Decimal] = None,
        take_profit_price: Optional[Decimal] = None,
        client_order_id: Optional[str] = None,
        trade_id: Optional[str] = None, # Link to a Trade object
        is_reduce_only: bool = False
    ) -> Optional[str]:
        """Places a new order with retry mechanism, using Decimal types."""
        if not client_order_id:
            client_order_id = f"bot-{uuid.uuid4()}"

        retries = 3
        for i in range(retries):
            try:
                # Round quantities and prices using PrecisionManager
                # For BUY, quantity is typically rounded DOWN to avoid insufficient funds
                # For SELL, quantity is typically rounded DOWN to avoid over-selling (if closing)
                qty_rounded = self.precision_manager.round_quantity(self.config.SYMBOL, qty, rounding_mode=ROUND_DOWN) 
                
                # For limit orders: BUY price (bid) is rounded DOWN, SELL price (ask) is rounded UP.
                # For market orders or other types, just ensure consistent decimal
                price_rounded = None
                if price is not None:
                    if order_type == 'Limit':
                        price_rounded = self.precision_manager.round_price(self.config.SYMBOL, price, rounding_mode=ROUND_DOWN if side == 'Buy' else ROUND_UP)
                    else:
                        price_rounded = self.precision_manager.round_price(self.config.SYMBOL, price, rounding_mode=ROUND_DOWN)
                
                sl_price_rounded = self.precision_manager.round_price(self.config.SYMBOL, stop_loss_price) if stop_loss_price else None
                tp_price_rounded = self.precision_manager.round_price(self.config.SYMBOL, take_profit_price) if take_profit_price else None

                order_params = {
                    "category": self.config.CATEGORY, 
                    "symbol": self.config.SYMBOL, 
                    "side": side,
                    "orderType": order_type, 
                    "qty": str(qty_rounded),
                    "timeInForce": self.config.TIME_IN_FORCE, 
                    "orderLinkId": client_order_id,
                    "reduceOnly": is_reduce_only,
                    "closeOnTrigger": False # Typically False for initial orders, True for SL/TP on inverse
                }
                if price_rounded is not None:
                    order_params["price"] = str(price_rounded)
                if sl_price_rounded is not None:
                    order_params["stopLoss"] = str(sl_price_rounded)
                if tp_price_rounded is not None:
                    order_params["takeProfit"] = str(tp_price_rounded)

                response = self.http_session.place_order(**order_params)
                if response['retCode'] == 0:
                    order_id = response['result']['orderId']
                    self.logger.info(f"Placed {side} {order_type} order (ID: {order_id}, ClientID: {client_order_id}) for {qty_rounded:.4f} @ {price_rounded if price_rounded else 'Market'}.")
                    return order_id
                elif response['retCode'] == 10001: 
                    self.logger.warning(f"Order {client_order_id} already exists or duplicate detected. Checking active orders.")
                    # A more robust system would query active orders here to confirm.
                    return None 
                else:
                    await self.alert_system.send_alert(f"Failed to place order {client_order_id}: {response['retMsg']} (Code: {response['retCode']})", level="ERROR", alert_type="ORDER_PLACE_FAIL")
                    self.logger.error(f"Failed to place order {client_order_id}: {response['retMsg']} (Code: {response['retCode']}). Retrying {i+1}/{retries}...")
                    await asyncio.sleep(self.config.API_RETRY_DELAY_SECONDS)
            except Exception as e:
                await self.alert_system.send_alert(f"Error placing order {client_order_id}: {e}", level="ERROR", alert_type="ORDER_PLACE_EXCEPTION")
                self.logger.error(f"Error placing order {client_order_id}: {e}. Retrying {i+1}/{retries}...", exc_info=True)
                await asyncio.sleep(self.config.API_RETRY_DELAY_SECONDS)
        self.logger.critical(f"Failed to place order {client_order_id} after multiple retries.")
        return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancels an existing order by its order ID with retry mechanism."""
        retries = 3
        for i in range(retries):
            try:
                response = self.http_session.cancel_order(category=self.config.CATEGORY, symbol=self.config.SYMBOL, orderId=order_id)
                if response['retCode'] == 0:
                    self.logger.info(f"Cancelled order {order_id}.")
                    self.active_orders.pop(order_id, None)
                    return True
                elif response['retCode'] == 110001: 
                    self.logger.warning(f"Order {order_id} already in final state (cancelled/filled).")
                    self.active_orders.pop(order_id, None)
                    return True
                else:
                    self.logger.error(f"Failed to cancel order {order_id}: {response['retMsg']} (Code: {response['retCode']}). Retrying {i+1}/{retries}...")
                    await asyncio.sleep(self.config.API_RETRY_DELAY_SECONDS)
            except Exception as e:
                self.logger.error(f"Error cancelling order {order_id}: {e}. Retrying {i+1}/{retries}...", exc_info=True)
                await asyncio.sleep(self.config.API_RETRY_DELAY_SECONDS)
        self.logger.critical(f"Failed to cancel order {order_id} after multiple retries.")
        return False

    async def cancel_all_orders(self) -> int:
        """Cancels all active orders for the symbol with retry mechanism."""
        retries = 3
        for i in range(retries):
            try:
                response = self.http_session.cancel_all_orders(category=self.config.CATEGORY, symbol=self.config.SYMBOL)
                if response['retCode'] == 0:
                    cancelled_count = len(response['result']['list'])
                    self.logger.info(f"Cancelled {cancelled_count} all orders for {self.config.SYMBOL}.")
                    self.active_orders.clear()
                    return cancelled_count
                else:
                    self.logger.error(f"Failed to cancel all orders: {response['retMsg']} (Code: {response['retCode']}). Retrying {i+1}/{retries}...")
                    await asyncio.sleep(self.config.API_RETRY_DELAY_SECONDS)
            except Exception as e:
                self.logger.error(f"Error cancelling all orders: {e}. Retrying {i+1}/{retries}...", exc_info=True)
                await asyncio.sleep(self.config.API_RETRY_DELAY_SECONDS)
        self.logger.critical("Failed to cancel all orders after multiple retries.")
        return 0
    
    async def _get_total_active_orders_qty(self, side: str) -> Decimal:
        """Calculates total quantity of active orders for a given side."""
        total_qty = Decimal('0')
        for order in self.active_orders.values():
            if order.get('side') == side and order.get('symbol') == self.config.SYMBOL:
                total_qty += Decimal(order.get('qty', '0'))
        return total_qty

    async def trading_logic(
        self,
    ):
        """
        Implements the core trading strategy loop.
        This orchestrates data, signals, risk management, and order execution.
        """
        self.loop_iteration += 1

        # 0. Check for Config Reload (Suggestion 4: Dynamic Configuration Reloading)
        current_time = time.time()
        if (current_time - self.config.LAST_CONFIG_RELOAD_TIME) > self.config.CONFIG_RELOAD_INTERVAL_SECONDS:
            self.logger.info("Attempting to reload configuration...")
            try:
                # Re-import config module to get latest values
                importlib.reload(sys.modules['config'])
                new_config = sys.modules['config'].Config()
                
                # Update bot's config instance and strategy parameters
                self.config.__dict__.update(new_config.__dict__)
                self.config.LAST_CONFIG_RELOAD_TIME = current_time
                if self.strategy: # Also update strategy parameters
                    self.strategy.update_parameters(
                        STRATEGY_EMA_FAST_PERIOD=self.config.STRATEGY_EMA_FAST_PERIOD,
                        STRATEGY_EMA_SLOW_PERIOD=self.config.STRATEGY_EMA_SLOW_PERIOD,
                        STRATEGY_RSI_PERIOD=self.config.STRATEGY_RSI_PERIOD,
                        STRATEGY_RSI_OVERSOLD=self.config.STRATEGY_RSI_OVERSOLD,
                        STRATEGY_RSI_OVERBOUGHT=self.config.STRATEGY_RSI_OVERBOUGHT,
                        STRATEGY_MACD_FAST_PERIOD=self.config.STRATEGY_MACD_FAST_PERIOD,
                        STRATEGY_MACD_SLOW_PERIOD=self.config.STRATEGY_MACD_SLOW_PERIOD,
                        STRATEGY_MACD_SIGNAL_PERIOD=self.config.STRATEGY_MACD_SIGNAL_PERIOD,
                        STRATEGY_BB_PERIOD=self.config.STRATEGY_BB_PERIOD,
                        STRATEGY_BB_STD=self.config.STRATEGY_BB_STD,
                        STRATEGY_ATR_PERIOD=self.config.STRATEGY_ATR_PERIOD,
                        STRATEGY_ADX_PERIOD=self.config.STRATEGY_ADX_PERIOD,
                        STRATEGY_BUY_SCORE_THRESHOLD=self.config.STRATEGY_BUY_SCORE_THRESHOLD,
                        STRATEGY_SELL_SCORE_THRESHOLD=self.config.STRATEGY_SELL_SCORE_THRESHOLD,
                    )
                self.logger.info("Configuration reloaded successfully.")
                await self.alert_system.send_alert("Bot configuration reloaded.", level="INFO", alert_type="CONFIG_RELOAD")
            except Exception as e:
                self.logger.error(f"Failed to reload configuration: {e}")
                await self.alert_system.send_alert(f"Failed to reload config: {e}", level="WARNING", alert_type="CONFIG_RELOAD_FAIL")


        # 1. Fetch Market Data & Calculate Indicators
        # Use caching for kline fetching
        kline_cache_key = self.kline_cache.generate_kline_cache_key(
            self.config.SYMBOL, self.config.CATEGORY, self.config.KLINES_INTERVAL, 
            self.config.KLINES_LOOKBACK_LIMIT, self.config.KLINES_HISTORY_WINDOW_MINUTES
        )
        self.current_kline_data = self.kline_cache.get(kline_cache_key)

        if self.current_kline_data is None:
            self.current_kline_data = await self.kline_data_fetcher.fetch_klines(
                self.config.SYMBOL, self.config.CATEGORY, self.config.KLINES_INTERVAL, 
                self.config.KLINES_LOOKBACK_LIMIT, self.config.KLINES_HISTORY_WINDOW_MINUTES
            )
            if not self.current_kline_data.empty:
                self.kline_cache.set(kline_cache_key, self.current_kline_data)
        
        if self.current_kline_data.empty:
            self.logger.warning("No kline data available after fetch/cache. Skipping trading logic.")
            return

        if self.strategy:
            self.current_kline_data = self.strategy.calculate_indicators(self.current_kline_data)
            self.current_indicators = self.strategy.get_indicator_values(self.current_kline_data)
        else:
            self.logger.critical("No strategy loaded. Cannot calculate indicators or generate signals.")
            return

        best_bid, best_ask = await self.orderbook_manager.get_best_bid_ask()
        if best_bid is None or best_ask is None or self.current_market_price == 0:
            self.logger.warning("Orderbook not fully populated or market price missing. Waiting...")
            return

        current_price = Decimal(str(self.current_market_price))
        
        # 2. Market Condition Analysis (Suggestion 1: Dynamic Strategy Adaptation)
        market_conditions = {}
        if self.config.MARKET_ANALYZER_ENABLED:
            market_conditions = self.market_analyzer.analyze_market_conditions(self.current_kline_data)
            self.logger.debug(f"Market Conditions: {market_conditions}")

        # 3. Advanced Market Analysis (from advanced_features.py)
        advanced_analysis_results = await self.advanced_features.perform_advanced_analysis(
            df=self.current_kline_data,
            current_market_price=self.current_market_price,
            orderbook_data={'bids': (await self.orderbook_manager.get_depth(25))[0], 'asks': (await self.orderbook_manager.get_depth(25))[1]}, # Pass top 25 depth
            indicator_values=self.current_indicators
        )
        self.logger.debug(f"Advanced Analysis: {advanced_analysis_results}")


        # 4. Generate Trading Signal
        if self.strategy:
            signal = self.strategy.generate_signal(self.current_kline_data, self.current_market_price, market_conditions)
            self.logger.info(f"Generated Signal: Type={signal.type}, Score={signal.score:.2f}, Reasons={', '.join(signal.reasons)}")
        else:
            signal = Signal(type='HOLD', score=0, reasons=['No strategy loaded'])

        # 5. Update PnL and Metrics
        await self.pnl_manager.update_all_positions_pnl(current_prices={self.config.SYMBOL: self.current_market_price})
        total_pnl_summary = await self.pnl_manager.get_total_account_pnl_summary()
        self.logger.info(f"Current PnL: Realized={total_pnl_summary['total_realized_pnl_usd']:.2f}, Unrealized={total_pnl_summary['total_unrealized_pnl_usd']:.2f}, Total Account PnL={total_pnl_summary['overall_total_pnl_usd']:.2f}")
        self.logger.info("PnL updated", extra=total_pnl_summary)
        
        # 6. Daily Drawdown Check (Suggestion 2: Drawdown Management)
        await self._check_daily_drawdown(total_pnl_summary)
        if not self.is_running: # If bot paused due to drawdown
            await self.alert_system.send_alert("Bot paused due to daily drawdown limit hit. Manual intervention required.", level="CRITICAL", alert_type="BOT_PAUSED_DRAWDOWN")
            return

        # 7. Trailing Stop Management
        current_position_summary = await self.pnl_manager.get_position_summary(self.config.SYMBOL)
        current_position = current_position_summary if isinstance(current_position_summary, dict) else None

        if current_position and self.config.TRAILING_STOP_ENABLED:
            atr_val = Decimal(str(self.current_indicators.get('ATR', 0.0)))
            
            period_high = self.current_indicators.get('high', 0.0) # Placeholder for `high` over period.
            period_low = self.current_indicators.get('low', 0.0)   # Placeholder for `low` over period.
            
            # For Chandelier Exit, need highest/lowest over TSL_CHANDELIER_PERIOD
            if self.config.TSL_TYPE == "CHANDELIER" and len(self.current_kline_data) >= self.config.TSL_CHANDELIER_PERIOD:
                period_high = self.current_kline_data['high'].iloc[-self.config.TSL_CHANDELIER_PERIOD:].max()
                period_low = self.current_kline_data['low'].iloc[-self.config.TSL_CHANDELIER_PERIOD:].min()

            await self.trailing_stop_manager.update_trailing_stop(
                symbol=self.config.SYMBOL,
                current_price=self.current_market_price,
                atr_value=atr_val,
                period_high=period_high,
                period_low=period_low,
                update_exchange=True
            )
        
        # 8. Trading Logic (e.g., Market Making / Strategy Execution)
        current_buy_orders_qty = await self._get_total_active_orders_qty('Buy')
        current_sell_orders_qty = await self._get_total_active_orders_qty('Sell')

        # Check maximum position size limit (current_position_size_usd is notional)
        current_position_size_usd = current_position['value_usd'] if current_position else Decimal('0')
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot get instrument specs for {self.config.SYMBOL}. Skipping order placement checks.")
            can_place_buy_order = False
            can_place_sell_order = False
        else:
            can_place_buy_order = (current_position_size_usd < Decimal(str(self.config.MAX_POSITION_SIZE_QUOTE_VALUE)) and 
                                   current_buy_orders_qty < Decimal(str(self.config.MAX_OPEN_ORDERS_PER_SIDE)) * specs.qty_step)
            can_place_sell_order = (abs(current_position_size_usd) < Decimal(str(self.config.MAX_POSITION_SIZE_QUOTE_VALUE)) and 
                                    abs(current_sell_orders_qty) < Decimal(str(self.config.MAX_OPEN_ORDERS_PER_SIDE)) * specs.qty_step)
        
        # Strategy Execution: Close opposing position first, then open new if applicable
        if current_position and current_position['side'] == 'Buy' and signal.is_sell():
            self.logger.info(f"Closing existing LONG position due to SELL signal.")
            await self.close_position()
        elif current_position and current_position['side'] == 'Sell' and signal.is_buy():
            self.logger.info(f"Closing existing SHORT position due to BUY signal.")
            await self.close_position()
        elif not current_position and signal.is_buy() and can_place_buy_order:
            self.logger.info(f"Opening LONG position due to BUY signal.")
            await self._execute_long_entry(current_price)
        elif not current_position and signal.is_sell() and can_place_sell_order:
            self.logger.info(f"Opening SHORT position due to SELL signal.")
            await self._execute_short_entry(current_price)
        elif signal.is_hold():
            self.logger.debug("HOLD signal. Managing existing orders/position (e.g., market making).")
            # Repricing logic for existing market making orders
            await self._manage_market_making_orders(best_bid, best_ask, can_place_buy_order, can_place_sell_order)
        
        await asyncio.sleep(self.config.TRADING_LOGIC_LOOP_INTERVAL_SECONDS)

    async def _check_daily_drawdown(self, total_pnl_summary: Dict):
        """Checks if the daily drawdown limit has been reached and pauses the bot if it has."""
        current_date = date.today()
        
        # Reset `day_start_equity` at midnight
        if current_date != self.daily_pnl_tracking_date:
            self.daily_pnl_tracking_date = current_date
            # Recalculate day_start_equity based on actual wallet balance at day start
            self.day_start_equity = Decimal(str(total_pnl_summary['current_wallet_balance_usd']))
            self.logger.info(f"New day, resetting daily drawdown tracking. Day start equity: {self.day_start_equity:.2f}")

        current_equity = Decimal(str(total_pnl_summary['current_wallet_balance_usd']))
        
        if self.day_start_equity > Decimal('0'): # Avoid division by zero
            daily_drawdown_value = self.day_start_equity - current_equity
            daily_drawdown_percent = (daily_drawdown_value / self.day_start_equity * 100).quantize(Decimal('0.01'))

            if daily_drawdown_percent >= Decimal(str(self.config.MAX_DAILY_DRAWDOWN_PERCENT)):
                message = f"Daily drawdown limit of {self.config.MAX_DAILY_DRAWDOWN_PERCENT}% ({daily_drawdown_percent:.2f}%) reached! Bot pausing for the day."
                await self.alert_system.send_alert(message, level="CRITICAL", alert_type="DAILY_DRAWDOWN_HIT")
                self.logger.critical(message)
                self.is_running = False # Pause the bot
            else:
                self.logger.debug(f"Daily drawdown: {daily_drawdown_percent:.2f}% (Limit: {self.config.MAX_DAILY_DRAWDOWN_PERCENT}%))")


    async def _execute_long_entry(self, current_price: Decimal):
        """Executes a long entry based on current price and risk management."""
        atr_val = Decimal(str(self.current_indicators.get('ATR', 0.0)))
        
        if atr_val == Decimal('0'):
            self.logger.warning("ATR is 0 for dynamic TP/SL. Falling back to fixed percentage.")
            sl_distance_ratio = Decimal(str(self.config.MIN_STOP_LOSS_DISTANCE_RATIO))
            tp_distance_ratio = Decimal(str(self.config.RISK_PER_TRADE_PERCENT * 2 / 100))
            sl_price = current_price * (Decimal('1') - sl_distance_ratio)
            tp_price = current_price * (Decimal('1') + tp_distance_ratio)
        else:
            sl_price = current_price - (atr_val * Decimal(str(self.config.TSL_ATR_MULTIPLIER)))
            tp_price = current_price + (atr_val * Decimal(str(self.config.TSL_ATR_MULTIPLIER * 2))) # 2x ATR for TP

        # Calculate position size
        position_sizing_info = self.order_sizing_calculator.calculate_position_size_fixed_risk(
            symbol=self.config.SYMBOL,
            account_balance=float(self.pnl_manager.available_balance_usd),
            risk_per_trade_percent=self.config.RISK_PER_TRADE_PERCENT,
            entry_price=float(current_price),
            stop_loss_price=float(sl_price),
            leverage=self.config.LEVERAGE,
            order_value_usd_limit=self.config.ORDER_SIZE_USD_VALUE
        )
        qty = position_sizing_info['quantity']

        if qty > Decimal('0'):
            trade_id = f"trade-{uuid.uuid4()}"
            # Estimate entry fee
            specs = self.precision_manager.get_specs(self.config.SYMBOL)
            entry_fee_usd = (qty * current_price * specs.taker_fee) if specs else Decimal('0')

            order_id = await self.place_order(
                side='Buy',
                qty=qty,
                price=current_price,
                order_type='Limit', # Or Market, based on config
                stop_loss_price=sl_price,
                take_profit_price=tp_price,
                client_order_id=trade_id
            )
            if order_id: # Only add trade if order placement was successful
                new_trade = Trade(
                    trade_id=trade_id,
                    symbol=self.config.SYMBOL,
                    category=self.config.CATEGORY,
                    side='Buy',
                    entry_time=datetime.now(ZoneInfo(self.config.BYBIT_TIMEZONE)),
                    entry_price=current_price,
                    quantity=qty,
                    leverage=Decimal(str(self.config.LEVERAGE)),
                    stop_loss_price=sl_price,
                    take_profit_price=tp_price,
                    entry_fee_usd=entry_fee_usd
                )
                self.trade_metrics_tracker.add_trade(new_trade)
                
                # Initialize trailing stop
                if self.config.TRAILING_STOP_ENABLED:
                     await self.trailing_stop_manager.initialize_trailing_stop(
                        symbol=self.config.SYMBOL,
                        position_side='Buy',
                        entry_price=float(current_price),
                        current_price=float(current_price),
                        initial_stop_loss=float(sl_price),
                        trail_percent=self.config.TSL_TRAIL_PERCENT,
                        activation_profit_percent=self.config.TSL_ACTIVATION_PROFIT_PERCENT,
                        tsl_type=self.config.TSL_TYPE,
                        atr_value=atr_val,
                        atr_multiplier=self.config.TSL_ATR_MULTIPLIER,
                        period_high=self.current_indicators.get('high', 0.0), # Current high as placeholder for period high
                        period_low=self.current_indicators.get('low', 0.0),   # Current low as placeholder for period low
                        chandelier_multiplier=self.config.TSL_CHANDELIER_MULTIPLIER
                    )

    async def _execute_short_entry(self, current_price: Decimal):
        """Executes a short entry based on current price and risk management."""
        atr_val = Decimal(str(self.current_indicators.get('ATR', 0.0)))
        
        if atr_val == Decimal('0'):
            self.logger.warning("ATR is 0 for dynamic TP/SL. Falling back to fixed percentage.")
            sl_distance_ratio = Decimal(str(self.config.MIN_STOP_LOSS_DISTANCE_RATIO))
            tp_distance_ratio = Decimal(str(self.config.RISK_PER_TRADE_PERCENT * 2 / 100))
            sl_price = current_price * (Decimal('1') + sl_distance_ratio)
            tp_price = current_price * (Decimal('1') - tp_distance_ratio)
        else:
            sl_price = current_price + (atr_val * Decimal(str(self.config.TSL_ATR_MULTIPLIER)))
            tp_price = current_price - (atr_val * Decimal(str(self.config.TSL_ATR_MULTIPLIER * 2)))

        position_sizing_info = self.order_sizing_calculator.calculate_position_size_fixed_risk(
            symbol=self.config.SYMBOL,
            account_balance=float(self.pnl_manager.available_balance_usd),
            risk_per_trade_percent=self.config.RISK_PER_TRADE_PERCENT,
            entry_price=float(current_price),
            stop_loss_price=float(sl_price),
            leverage=self.config.LEVERAGE,
            order_value_usd_limit=self.config.ORDER_SIZE_USD_VALUE
        )
        qty = position_sizing_info['quantity']

        if qty > Decimal('0'):
            trade_id = f"trade-{uuid.uuid4()}"
            order_id = await self.place_order(
                side='Sell',
                qty=qty,
                price=current_price,
                order_type='Limit',
                stop_loss_price=sl_price,
                take_profit_price=tp_price,
                client_order_id=trade_id
            )
            if order_id:
                new_trade = Trade(
                    trade_id=trade_id,
                    symbol=self.config.SYMBOL,
                    category=self.config.CATEGORY,
                    side='Sell',
                    entry_time=datetime.now(),
                    entry_price=current_price,
                    quantity=qty,
                    leverage=Decimal(str(self.config.LEVERAGE)),
                    stop_loss_price=sl_price,
                    take_profit_price=tp_price
                )
                self.trade_metrics_tracker.add_trade(new_trade)

                # Initialize trailing stop
                if self.config.TRAILING_STOP_ENABLED:
                    await self.trailing_stop_manager.initialize_trailing_stop(
                        symbol=self.config.SYMBOL,
                        position_side='Sell',
                        entry_price=float(current_price),
                        current_price=float(current_price),
                        initial_stop_loss=float(sl_price),
                        trail_percent=self.config.TSL_TRAIL_PERCENT,
                        activation_profit_percent=self.config.TSL_ACTIVATION_PROFIT_PERCENT,
                        tsl_type=self.config.TSL_TYPE,
                        atr_value=self.current_indicators.get('ATR', 0.0),
                        atr_multiplier=self.config.TSL_ATR_MULTIPLIER,
                        period_high=self.current_indicators.get('high', 0.0), # Current high as placeholder for period high
                        period_low=self.current_indicators.get('low', 0.0),   # Current low as placeholder for period low
                        chandelier_multiplier=self.config.TSL_CHANDELIER_MULTIPLIER
                    )

    async def _manage_market_making_orders(self, best_bid: float, best_ask: float, can_place_buy: bool, can_place_sell: bool):
        """Manages outstanding market making orders (repricing/re-placing)."""
        target_bid_price = Decimal(str(best_bid)) * (Decimal('1') - Decimal(str(self.config.SPREAD_PERCENTAGE)))
        target_ask_price = Decimal(str(best_ask)) * (Decimal('1') + Decimal(str(self.config.SPREAD_PERCENTAGE)))
        
        target_bid_price_rounded = self.precision_manager.round_price(self.config.SYMBOL, target_bid_price, rounding_mode=ROUND_DOWN)
        target_ask_price_rounded = self.precision_manager.round_price(self.config.SYMBOL, target_ask_price, rounding_mode=ROUND_UP)

        # Ensure target prices maintain a valid spread
        if target_bid_price_rounded >= target_ask_price_rounded:
            self.logger.warning(f"Calculated target prices overlap or are too close for {self.config.SYMBOL}. Best Bid:{best_bid:.4f}, Best Ask:{best_ask:.4f}. Adjusting to minimum spread.")
            target_bid_price_rounded = self.precision_manager.round_price(self.config.SYMBOL, Decimal(str(best_bid)) * (Decimal('1') - Decimal(str(self.config.SPREAD_PERCENTAGE / 2))), rounding_mode=ROUND_DOWN)
            target_ask_price_rounded = self.precision_manager.round_price(self.config.SYMBOL, Decimal(str(best_ask)) * (Decimal('1') + Decimal(str(self.config.SPREAD_PERCENTAGE / 2))), rounding_mode=ROUND_UP)
            if target_bid_price_rounded >= target_ask_price_rounded:
                 target_ask_price_rounded = self.precision_manager.round_price(self.config.SYMBOL, target_bid_price_rounded * (Decimal('1') + Decimal('0.0001')), rounding_mode=ROUND_UP)

        # --- Manage Buy Orders ---
        existing_buy_orders = [o for o in self.active_orders.values() if o.get('side') == 'Buy' and o.get('symbol') == self.config.SYMBOL]
        
        if existing_buy_orders:
            for order_id, order_details in existing_buy_orders:
                existing_price = Decimal(order_details.get('price'))
                if abs(existing_price - target_bid_price_rounded) / target_bid_price_rounded > Decimal(str(self.config.ORDER_REPRICE_THRESHOLD_PCT)):
                    self.logger.info(f"Repricing Buy order {order_id}: {existing_price:.4f} -> {target_bid_price_rounded:.4f}")
                    await self.cancel_order(order_id)
                    await asyncio.sleep(0.1)
                    if can_place_buy:
                        await self.place_order(side='Buy', qty=Decimal(str(self.config.ORDER_SIZE_USD_VALUE)), price=target_bid_price_rounded)
                    break 
        elif can_place_buy:
            self.logger.debug(f"Placing new Buy order for {self.config.ORDER_SIZE_USD_VALUE:.4f} @ {target_bid_price_rounded:.4f}")
            await self.place_order(side='Buy', qty=Decimal(str(self.config.ORDER_SIZE_USD_VALUE)), price=target_bid_price_rounded)


        # --- Manage Sell Orders ---
        existing_sell_orders = [o for o in self.active_orders.values() if o.get('side') == 'Sell' and o.get('symbol') == self.config.SYMBOL]
        
        if existing_sell_orders:
            for order_id, order_details in existing_sell_orders:
                existing_price = Decimal(order_details.get('price'))
                if abs(existing_price - target_ask_price_rounded) / target_ask_price_rounded > Decimal(str(self.config.ORDER_REPRICE_THRESHOLD_PCT)):
                    self.logger.info(f"Repricing Sell order {order_id}: {existing_price:.4f} -> {target_ask_price_rounded:.4f}")
                    await self.cancel_order(order_id)
                    await asyncio.sleep(0.1)
                    if can_place_sell:
                        await self.place_order(side='Sell', qty=Decimal(str(self.config.ORDER_SIZE_USD_VALUE)), price=target_ask_price_rounded)
                    break 
        elif can_place_sell:
            self.logger.debug(f"Placing new Sell order for {self.config.ORDER_SIZE_USD_VALUE:.4f} @ {target_ask_price_rounded:.4f}")
            await self.place_order(side='Sell', qty=Decimal(str(self.config.ORDER_SIZE_USD_VALUE)), price=target_ask_price_rounded)

    async def fetch_klines(self, limit: int, interval: str) -> pd.DataFrame:
        """Fetches historical kline data for indicator calculations."""
        # This function now delegates to the KlineDataFetcher utility
        return await self.kline_data_fetcher.fetch_klines(
            symbol=self.config.SYMBOL, 
            category=self.config.CATEGORY, 
            interval=interval, 
            limit=limit, 
            history_window_minutes=self.config.KLINES_HISTORY_WINDOW_MINUTES
        )
            
    async def close_position(self) -> bool:
        """Closes the current open position."""
        position_summary = await self.pnl_manager.get_position_summary(self.config.SYMBOL)
        if not position_summary:
            self.logger.info(f"No open position found for {self.config.SYMBOL} to close.")
            return False

        if isinstance(position_summary, dict):
            current_position_side = position_summary['side']
            current_position_size = Decimal(str(position_summary['size']))

            side_to_close = 'Sell' if current_position_side == 'Buy' else 'Buy'
            
            trade_to_close: Optional[Trade] = None
            for trade_id, trade in self.trade_metrics_tracker.open_trades.items():
                if trade.symbol == self.config.SYMBOL and trade.side == current_position_side:
                    trade_to_close = trade
                    break
            
            # Use `orderLinkId` for the market close order to link it to the trade
            order_id = await self.place_order(
                side=side_to_close,
                qty=current_position_size,
                order_type='Market',
                is_reduce_only=True,
                client_order_id=trade_to_close.trade_id if trade_to_close else f"close-{uuid.uuid4()}"
            )
            if order_id:
                self.logger.info(f"Market order placed to close {self.config.SYMBOL} position.")
                # When order is filled, WebSocket execution stream would trigger PnLManager to update
                # For now, manually trigger trade_metrics_tracker update (estimation for fees)
                if trade_to_close:
                    specs = self.precision_manager.get_specs(self.config.SYMBOL)
                    exit_fee_usd = (current_position_size * Decimal(str(self.current_market_price)) * specs.taker_fee) if specs else Decimal('0')
                    self.trade_metrics_tracker.update_trade_exit(
                        trade_id=trade_to_close.trade_id,
                        exit_price=self.current_market_price,
                        exit_time=datetime.now(ZoneInfo(self.config.BYBIT_TIMEZONE)),
                        exit_fee_usd=float(exit_fee_usd)
                    )
                return True
            else:
                await self.alert_system.send_alert(f"Failed to place market order to close position for {self.config.SYMBOL}.", level="ERROR", alert_type="CLOSE_POSITION_FAIL")
                self.logger.error(f"Failed to place market order to close position for {self.config.SYMBOL}.")
                return False
        
        self.logger.warning(f"Unexpected position summary format for {self.config.SYMBOL}.")
        return False


    async def start(self):
        """Starts the bot's main loop and WebSocket listeners."""
        await self.setup_initial_state()

        if not self.is_running:
            self.logger.critical("Bot setup failed. Exiting.")
            return

        self.ws_public = WebSocket(channel_type=self.config.CATEGORY, testnet=self.config.TESTNET)
        self.ws_private = WebSocket(channel_type='private', testnet=self.config.TESTNET, api_key=self.config.BYBIT_API_KEY, api_secret=self.config.BYBIT_API_SECRET)

        # Start WebSocket listeners concurrently
        public_ws_topics = [f"orderbook.{self.config.ORDERBOOK_DEPTH_LIMIT}.{self.config.SYMBOL}", f"tickers.{self.config.SYMBOL}"]
        self.public_ws_task = asyncio.create_task(self._start_websocket_listener(
            self.ws_public, self._handle_public_ws_message, public_ws_topics))
        
        private_ws_topics = ['position', 'order', 'execution', 'wallet']
        self.private_ws_task = asyncio.create_task(self._start_websocket_listener(
            self.ws_private, self._handle_private_ws_message, private_ws_topics))

        self.logger.info("Bot main trading loop started.")
        while self.is_running:
            try:
                await self.trading_logic()
            except asyncio.CancelledError:
                self.logger.info("Trading logic task cancelled gracefully.")
                break
            except Exception as e:
                await self.alert_system.send_alert(f"Error in main trading loop: {e}", level="ERROR", alert_type="MAIN_LOOP_EXCEPTION")
                self.logger.error(f"Error in main trading loop: {e}", exc_info=True)
                await asyncio.sleep(self.config.API_RETRY_DELAY_SECONDS)

        await self.shutdown()

    async def shutdown(self):
        """Gracefully shuts down the bot, cancelling orders and closing connections."""
        self.logger.info("Shutting down bot...")
        self.is_running = False

        # Cancel all active orders
        if self.active_orders:
            self.logger.info(f"Cancelling {len(self.active_orders)} active orders...")
            await self.cancel_all_orders()
            await asyncio.sleep(2)

        # Close all open positions at market price (optional, depending on strategy)
        position_summary = await self.pnl_manager.get_position_summary(self.config.SYMBOL)
        if position_summary and isinstance(position_summary, dict) and Decimal(str(position_summary['size'])) > Decimal('0'):
            self.logger.info(f"Closing open position {self.config.SYMBOL} on shutdown...")
            await self.close_position()
            await asyncio.sleep(2) # Give time for market close to execute

        # Cancel WebSocket tasks
        if self.public_ws_task and not self.public_ws_task.done():
            self.public_ws_task.cancel()
            try: await self.public_ws_task
            except asyncio.CancelledError: pass
        
        if self.private_ws_task and not self.private_ws_task.done():
            self.private_ws_task.cancel()
            try: await self.private_ws_task
            except asyncio.CancelledError: pass

        if self.ws_public and self.ws_public.is_connected():
            await self.ws_public.close()
        if self.ws_private and self.ws_private.is_connected():
            await self.ws_private.close()

        # Export final trade metrics
        self.trade_metrics_tracker.export_trades_to_csv(self.config.TRADE_HISTORY_CSV)
        self.trade_metrics_tracker.export_daily_metrics_to_csv(self.config.DAILY_METRICS_CSV)
        
        self.logger.info("Bot shutdown complete.")
lete.")
gger.info("Bot shutdown complete.")
