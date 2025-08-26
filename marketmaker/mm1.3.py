
 
An unexpected critical error occurred during bot initialization or runtime: 'function' object has no attribute '__wrapped__'
2025-08-25 19:00:01,437 - CRITICAL - Unhandled exception in main: 'function' object has no attribute '__wrapped__'
Traceback (most recent call last):
  File "/data/data/com.termux/files/home/Algobots/marketmaker/mm1.3.py", line 1060, in <module>
    bot = BybitMarketMaker(config)
          ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/data/data/com.termux/files/home/Algobots/marketmaker/mm1.3.py", line 398, in __init__
    self.trading_client._initialize_api_retry_decorator() # Initialize tenacity decorator with live config
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/data/data/com.termux/files/home/Algobots/marketmaker/mm1.3.py", line 296, in _initialize_api_retry_decorator
    self.get_instruments_info = self.api_retry(self.get_instruments_info.__wrapped__)
                                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'function' object has no attribute '__wrapped__'
import asyncio
import logging
import os
import sys
import aiofiles
import pickle
import time
import aiosqlite
import numpy as np
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_DOWN, getcontext
from typing import Dict, List, Optional, Any, Coroutine, Callable
from pybit.unified_trading import HTTP, WebSocket
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type, wait_exponential, before_sleep_log

# --- Core Setup ---
getcontext().prec = 28
load_dotenv()

# --- Custom Exceptions ---
class APIAuthError(Exception):
    """Custom exception for API authentication/signature errors."""
    pass

class WebSocketConnectionError(Exception):
    """Custom exception for WebSocket connection failures."""
    pass

# =====================================================================
# CONFIGURATION & DATA CLASSES
# =====================================================================
@dataclass
class TradeMetrics:
    total_trades: int = 0
    gross_profit: Decimal = Decimal('0')
    gross_loss: Decimal = Decimal('0')
    total_fees: Decimal = Decimal('0')
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0

    @property
    def total_pnl(self) -> Decimal:
        return self.gross_profit - self.gross_loss - self.total_fees

    def update_win_rate(self):
        self.win_rate = (self.wins / self.total_trades * 100.0) if self.total_trades > 0 else 0.0

@dataclass
class InventoryStrategyConfig:
    enabled: bool = True
    skew_intensity: Decimal = Decimal('0.5')

@dataclass
class DynamicSpreadConfig:
    enabled: bool = True
    volatility_window_sec: int = 60
    volatility_multiplier: Decimal = Decimal('2.0')
    min_spread_pct: Decimal = Decimal('0.0005')
    max_spread_pct: Decimal = Decimal('0.01')

@dataclass
class CircuitBreakerConfig:
    enabled: bool = True
    pause_threshold_pct: Decimal = Decimal('0.02')
    check_interval_sec: int = 10
    pause_duration_sec: int = 60

@dataclass
class StrategyConfig:
    base_spread_pct: Decimal = Decimal('0.001')
    base_order_size_pct_of_balance: Decimal = Decimal('0.005')
    order_stale_threshold_pct: Decimal = Decimal('0.0005')
    min_profit_spread_after_fees_pct: Decimal = Decimal('0.0002')
    inventory: InventoryStrategyConfig = field(default_factory=InventoryStrategyConfig)
    dynamic_spread: DynamicSpreadConfig = field(default_factory=DynamicSpreadConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)

@dataclass
class SystemConfig:
    loop_interval_sec: int = 1
    order_refresh_interval_sec: int = 5
    ws_heartbeat_sec: int = 30
    cancellation_rate_limit_sec: float = 0.2
    status_report_interval_sec: int = 30
    ws_reconnect_attempts: int = 5
    ws_reconnect_initial_delay_sec: int = 5
    api_retry_attempts: int = 3
    api_retry_delay_sec: float = 1.0 # Fixed delay for simplicity, can be exponential

@dataclass
class FilesConfig:
    log_level: str = "INFO"
    log_file: str = "market_maker.log"
    state_file: str = "market_maker_state.pkl"
    db_file: str = "market_maker.db"

@dataclass
class Config:
    api_key: str = field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    testnet: bool = os.getenv("BYBIT_TESTNET", "true").lower() == "true"
    trading_mode: str = "DRY_RUN" # DRY_RUN, TESTNET, LIVE
    symbol: str = "XLMUSDT"
    category: str = "linear"
    leverage: Decimal = Decimal('1')
    min_order_value_usd: Decimal = Decimal('10')
    max_order_size_pct: Decimal = Decimal('0.1')
    max_net_exposure_usd: Decimal = Decimal('500')
    order_type: str = "Limit"
    time_in_force: str = "GTC"
    post_only: bool = True
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    system: SystemConfig = field(default_factory=SystemConfig)
    files: FilesConfig = field(default_factory=FilesConfig)
    metrics: TradeMetrics = field(default_factory=TradeMetrics)
    base_currency: str = field(init=False)
    quote_currency: str = field(init=False)

    def __post_init__(self):
        if self.symbol.endswith("USDT"):
            self.base_currency = self.symbol[:-4]
            self.quote_currency = "USDT"
        elif self.symbol.endswith("USD"):
            self.base_currency = self.symbol[:-3]
            self.quote_currency = "USD"
        else:
            self.base_currency = self.symbol[:3]
            self.quote_currency = self.symbol[3:]

        # Harmonize testnet setting based on trading_mode
        if self.trading_mode == "TESTNET":
            self.testnet = True
        elif self.trading_mode == "LIVE":
            self.testnet = False
        
        # Ensure API keys are present in non-DRY_RUN modes
        if self.trading_mode != "DRY_RUN" and (not self.api_key or not self.api_secret):
            raise ValueError("API_KEY and API_SECRET must be set in .env for TESTNET or LIVE trading_mode.")

@dataclass
class MarketInfo:
    symbol: str
    price_precision: Decimal
    quantity_precision: Decimal
    min_order_qty: Decimal
    min_notional_value: Decimal

    def format_price(self, p: Decimal) -> Decimal:
        return p.quantize(self.price_precision, rounding=ROUND_DOWN)

    def format_quantity(self, q: Decimal) -> Decimal:
        return q.quantize(self.quantity_precision, rounding=ROUND_DOWN)

# =====================================================================
# LOGGING, STATE, and DB
# =====================================================================
def setup_logger(config: FilesConfig) -> logging.Logger:
    logger = logging.getLogger('MarketMakerBot')
    logger.setLevel(getattr(logging, config.log_level.upper()))
    if not logger.handlers: # Prevent adding handlers multiple times if setup_logger is called more than once
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
        # File handler
        fh = logging.FileHandler(config.log_file)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    return logger

class StateManager:
    def __init__(self, file_path: str, logger: logging.Logger):
        self.file_path = file_path
        self.logger = logger

    async def save_state(self, state: Dict):
        try:
            async with aiofiles.open(self.file_path, 'wb') as f:
                await f.write(pickle.dumps(state))
            self.logger.info("Bot state saved successfully.")
        except Exception as e:
            self.logger.error(f"Error saving state: {e}")

    async def load_state(self) -> Optional[Dict]:
        if not os.path.exists(self.file_path):
            return None
        try:
            async with aiofiles.open(self.file_path, 'rb') as f:
                return pickle.loads(await f.read())
        except Exception as e:
            self.logger.error(f"Error loading state: {e}. Starting fresh.")
            return None

class DBManager:
    def __init__(self, db_file: str, logger: logging.Logger):
        self.db_file = db_file
        self.conn: Optional[aiosqlite.Connection] = None
        self.logger = logger

    async def connect(self):
        try:
            self.conn = await aiosqlite.connect(self.db_file)
            self.conn.row_factory = aiosqlite.Row
            self.logger.info(f"Connected to database: {self.db_file}")
        except Exception as e:
            self.logger.critical(f"Failed to connect to database: {e}")
            sys.exit(1)

    async def close(self):
        if self.conn:
            await self.conn.close()
            self.logger.info("Database connection closed.")

    async def create_tables(self):
        if not self.conn: await self.connect() # Ensure connection is open
        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS order_events (id INTEGER PRIMARY KEY, timestamp TEXT, order_id TEXT, order_link_id TEXT, symbol TEXT, side TEXT, order_type TEXT, price TEXT, qty TEXT, status TEXT, message TEXT);
            CREATE TABLE IF NOT EXISTS trade_fills (id INTEGER PRIMARY KEY, timestamp TEXT, order_id TEXT, trade_id TEXT, symbol TEXT, side TEXT, exec_price TEXT, exec_qty TEXT, fee TEXT, fee_currency TEXT, pnl TEXT);
            CREATE TABLE IF NOT EXISTS balance_updates (id INTEGER PRIMARY KEY, timestamp TEXT, currency TEXT, wallet_balance TEXT, available_balance TEXT);
            CREATE TABLE IF NOT EXISTS bot_metrics (id INTEGER PRIMARY KEY, timestamp TEXT, total_trades INTEGER, total_pnl TEXT, gross_profit TEXT, gross_loss TEXT, total_fees TEXT, wins INTEGER, losses INTEGER, win_rate REAL);
        """)
        await self.conn.commit()
        self.logger.info("Database tables checked/created.")

    async def log_order_event(self, o: Dict, m: Optional[str] = None):
        if not self.conn: return # Don't log if DB connection failed
        try:
            await self.conn.execute("INSERT INTO order_events (timestamp, order_id, order_link_id, symbol, side, order_type, price, qty, status, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (datetime.now().isoformat(), o.get('orderId'), o.get('orderLinkId'), o.get('symbol'), o.get('side'), o.get('orderType'), str(o.get('price','0')), str(o.get('qty','0')), o.get('orderStatus'), m))
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging order event to DB: {e}")

    async def log_trade_fill(self, t: Dict):
        if not self.conn: return
        try:
            await self.conn.execute("INSERT INTO trade_fills (timestamp, order_id, trade_id, symbol, side, exec_price, exec_qty, fee, fee_currency, pnl) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (datetime.now().isoformat(), t.get('orderId'), t.get('execId'), t.get('symbol'), t.get('side'), str(t.get('execPrice','0')), str(t.get('execQty','0')), str(t.get('execFee','0')), t.get('feeCurrency'), str(t.get('pnl','0'))))
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging trade fill to DB: {e}")

    async def log_balance_update(self, c: str, wb: Decimal, ab: Optional[Decimal] = None):
        if not self.conn: return
        try:
            await self.conn.execute("INSERT INTO balance_updates (timestamp, currency, wallet_balance, available_balance) VALUES (?, ?, ?, ?)", (datetime.now().isoformat(), c, str(wb), str(ab) if ab else None))
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging balance update to DB: {e}")

    async def log_bot_metrics(self, m: TradeMetrics):
        if not self.conn: return
        try:
            await self.conn.execute("INSERT INTO bot_metrics (timestamp, total_trades, total_pnl, gross_profit, gross_loss, total_fees, wins, losses, win_rate) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (datetime.now().isoformat(), m.total_trades, str(m.total_pnl), str(m.gross_profit), str(m.gross_loss), str(m.total_fees), m.wins, m.losses, m.win_rate))
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging bot metrics to DB: {e}")

# =====================================================================
# TRADING CLIENT
# =====================================================================
class TradingClient:
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.http_session = HTTP(testnet=self.config.testnet, api_key=self.config.api_key, api_secret=self.config.api_secret)
        self.ws_public: Optional[WebSocket] = None
        self.ws_private: Optional[WebSocket] = None
        self.last_cancel_time = 0

    # Tenacity retry decorator for API calls
    # Note: `config` is an instance, not a class, so access system config directly.
    api_retry = retry(
        stop=stop_after_attempt(3), # Using a hardcoded value here, as config is instance-specific. Will fix this.
        wait=wait_fixed(1.0), # Same here.
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(logging.getLogger('MarketMakerBot'), logging.WARNING),
        reraise=True
    )

    # Re-initialize the decorator with the actual config values after config is fully loaded
    def _initialize_api_retry_decorator(self):
        self.api_retry = retry(
            stop=stop_after_attempt(self.config.system.api_retry_attempts),
            wait=wait_fixed(self.config.system.api_retry_delay_sec),
            retry=retry_if_exception_type(Exception),
            before_sleep=before_sleep_log(self.logger, logging.WARNING),
            reraise=True
        )
        # Apply the decorator to methods
        self.get_instruments_info = self.api_retry(self.get_instruments_info.__wrapped__)
        self.get_wallet_balance = self.api_retry(self.get_wallet_balance.__wrapped__)
        self.get_position_info = self.api_retry(self.get_position_info.__wrapped__)
        self.set_leverage = self.api_retry(self.set_leverage.__wrapped__)
        self.get_open_orders = self.api_retry(self.get_open_orders.__wrapped__)
        self.place_order = self.api_retry(self.place_order.__wrapped__)
        self.cancel_order = self.api_retry(self.cancel_order.__wrapped__)
        self.cancel_all_orders = self.api_retry(self.cancel_all_orders.__wrapped__)


    def _handle_response(self, response: Any, action: str):
        if not isinstance(response, dict):
            self.logger.error(f"API {action} failed: Invalid response format. Response: {response}")
            return None
        ret_code = response.get('retCode', -1)
        if ret_code == 0:
            self.logger.debug(f"API {action} successful.")
            return response.get('result', {})
        ret_msg = response.get('retMsg', 'Unknown error')
        self.logger.error(f"API {action} failed: {ret_msg} (ErrCode: {ret_code}).")
        if ret_code == 10004:
            raise APIAuthError(f"Authentication failed: {ret_msg}. Check API key permissions and validity.")
        # For other errors, we just return None and log, allowing retries to handle transient issues
        return None

    async def get_instruments_info(self) -> Optional[Dict]:
        result = self._handle_response(self.http_session.get_instruments_info(category=self.config.category, symbol=self.config.symbol), "get_instruments_info")
        return result.get('list', [{}])[0] if result else None

    async def get_wallet_balance(self) -> Optional[Dict]:
        account_type = "UNIFIED" if self.config.category in ['linear', 'inverse'] else "SPOT"
        result = self._handle_response(self.http_session.get_wallet_balance(accountType=account_type), "get_wallet_balance")
        return result.get('list', [{}])[0] if result else None

    async def get_position_info(self) -> Optional[Dict]:
        if self.config.category != 'linear': return None
        response = self.http_session.get_positions(category=self.config.category, settleCoin=self.config.quote_currency)
        result = self._handle_response(response, "get_position_info")
        if result and result.get('list'):
            for position in result['list']:
                if position['symbol'] == self.config.symbol: return position
        return None

    async def set_leverage(self, leverage: Decimal) -> bool:
        if self.config.category != 'linear': return True
        response = self.http_session.set_leverage(category=self.config.category, symbol=self.config.symbol, buyLeverage=str(leverage), sellLeverage=str(leverage))
        return self._handle_response(response, f"set_leverage to {leverage}") is not None

    async def get_open_orders(self) -> List[Dict]:
        result = self._handle_response(self.http_session.get_open_orders(category=self.config.category, symbol=self.config.symbol, limit=50), "get_open_orders")
        return result.get('list', []) if result else []

    async def place_order(self, params: Dict) -> Optional[Dict]:
        return self._handle_response(self.http_session.place_order(**params), f"place_order ({params.get('side')} {params.get('qty')} @ {params.get('price')})")

    async def cancel_order(self, order_id: str, order_link_id: Optional[str] = None) -> bool:
        current_time = time.time()
        # Respect rate limit within the bot's logic, before API call
        if (current_time - self.last_cancel_time) < self.config.system.cancellation_rate_limit_sec:
            await asyncio.sleep(self.config.system.cancellation_rate_limit_sec - (current_time - self.last_cancel_time))
        params = {"category": self.config.category, "symbol": self.config.symbol, "orderId": order_id}
        if order_link_id: params["orderLinkId"] = order_link_id
        response = self.http_session.cancel_order(**params)
        self.last_cancel_time = time.time()
        return self._handle_response(response, f"cancel_order {order_id}") is not None

    async def cancel_all_orders(self) -> bool:
        params = {"category": self.config.category}
        if self.config.category in ['linear', 'inverse']: params['settleCoin'] = self.config.quote_currency
        return self._handle_response(self.http_session.cancel_all_orders(**params), "cancel_all_orders") is not None

    def _init_public_ws(self, callback: Callable):
        self.logger.info("Initializing PUBLIC orderbook stream...")
        self.ws_public = WebSocket(testnet=self.config.testnet, channel_type=self.config.category)
        self.ws_public.orderbook_stream(symbol=self.config.symbol, depth=1, callback=callback)

    def _init_private_ws(self, order_callback: Callable, position_callback: Optional[Callable] = None):
        self.logger.info("Initializing PRIVATE streams (orders, positions)...")
        self.ws_private = WebSocket(testnet=self.config.testnet, api_key=self.config.api_key, api_secret=self.config.api_secret, channel_type="private")
        self.ws_private.order_stream(callback=order_callback)
        if position_callback and self.config.category == 'linear':
            self.ws_private.position_stream(callback=position_callback)

    def close_websockets(self):
        self.logger.info("Closing WebSocket connections...")
        if self.ws_public:
            self.ws_public.exit()
            self.ws_public = None
        if self.ws_private:
            self.ws_private.exit()
            self.ws_private = None

# =====================================================================
# CORE MARKET MAKER BOT CLASS
# =====================================================================
class BybitMarketMaker:
    def __init__(self, config: Config):
        self.config = config
        self.logger = setup_logger(config.files)
        self.state_manager = StateManager(config.files.state_file, self.logger)
        self.db_manager = DBManager(config.files.db_file, self.logger)
        self.trading_client = TradingClient(self.config, self.logger)
        self.trading_client._initialize_api_retry_decorator() # Initialize tenacity decorator with live config

        self.market_info: Optional[MarketInfo] = None
        self.mid_price = Decimal('0')
        self.current_balance = Decimal('0')
        self.available_balance = Decimal('0')
        self.current_position_qty = Decimal('0')
        self.unrealized_pnl = Decimal('0') # For linear contracts
        self.active_orders: Dict[str, Dict] = {}
        self.is_running = False
        self.last_order_management_time = 0
        self.last_ws_message_time = time.time()
        self.last_status_report_time = 0

        self.market_data_lock = asyncio.Lock()
        self.active_orders_lock = asyncio.Lock()
        self.balance_position_lock = asyncio.Lock()

        self.mid_price_history = deque(maxlen=self.config.strategy.dynamic_spread.volatility_window_sec)
        self.circuit_breaker_history = deque(maxlen=self.config.strategy.circuit_breaker.check_interval_sec)
        self.is_paused = False
        self.pause_end_time = 0
        self.ws_reconnect_attempts_left = self.config.system.ws_reconnect_attempts
        self.loop: Optional[asyncio.AbstractEventLoop] = None # Captured at runtime

        self.logger.info(f"Market Maker Bot Initialized. Trading Mode: {self.config.trading_mode}")
        if self.config.testnet: self.logger.info("Running on Bybit Testnet.")

    # --- Core Lifecycle & Setup ---
    async def run(self):
        self.is_running = True
        self.loop = asyncio.get_running_loop() # Capture the running event loop
        try:
            await self._initialize_bot()
            await self._connect_websockets() # Initial WS connection
            while self.is_running:
                await self._main_loop_tick()
                await asyncio.sleep(self.config.system.loop_interval_sec)
        except (APIAuthError, asyncio.CancelledError, KeyboardInterrupt) as e:
            self.logger.info(f"Bot stopping due to: {type(e).__name__} - {e}")
        except Exception as e:
            self.logger.critical(f"An unhandled error occurred in the main loop: {e}", exc_info=True)
        finally:
            await self.stop()

    async def _initialize_bot(self):
        self.logger.info("Performing initial setup...")
        # Configuration validation
        self._validate_config()

        await self.db_manager.connect()
        await self.db_manager.create_tables()

        if not await self._fetch_market_info():
            self.logger.critical("Failed to fetch market info. Shutting down.")
            sys.exit(1)

        if not await self._update_balance_and_position():
            self.logger.critical("Failed to fetch initial balance/position. Shutting down.")
            sys.exit(1)

        if self.config.trading_mode != "DRY_RUN":
            if self.config.category == 'linear' and not await self.trading_client.set_leverage(self.config.leverage):
                self.logger.critical("Failed to set leverage. Shutting down.")
                sys.exit(1)
        else:
            self.logger.info("DRY_RUN mode: Skipping leverage setting.")

        state = await self.state_manager.load_state()
        if state:
            self.active_orders = state.get('active_orders', {})
            self.config.metrics = state.get('metrics', self.config.metrics)
            self.logger.info(f"Loaded state with {len(self.active_orders)} active orders.")
        
        await self._reconcile_orders_on_startup()
        self.logger.info("Initial setup successful.")

    def _validate_config(self):
        if self.config.strategy.dynamic_spread.enabled:
            if not (Decimal('0') <= self.config.strategy.dynamic_spread.min_spread_pct <= self.config.strategy.dynamic_spread.max_spread_pct):
                raise ValueError("Dynamic spread min/max percentages are invalid.")
        if self.config.trading_mode != "DRY_RUN" and (not self.config.api_key or not self.config.api_secret):
            raise ValueError("API_KEY and API_SECRET must be set for non-DRY_RUN modes.")
        if self.config.leverage <= 0:
            raise ValueError("Leverage must be a positive decimal.")
        self.logger.info("Configuration validated successfully.")

    async def _connect_websockets(self):
        self.logger.info("Connecting WebSockets...")
        try:
            self.trading_client._init_public_ws(self._handle_orderbook_update)
            self.trading_client._init_private_ws(self._handle_order_update, self._handle_position_update)
            self.ws_reconnect_attempts_left = self.config.system.ws_reconnect_attempts # Reset attempts on successful connect
            self.logger.info("WebSockets connected and subscribed.")
        except Exception as e:
            self.logger.error(f"Failed to establish initial WebSocket connections: {e}")
            raise WebSocketConnectionError(f"Initial WS connection failed: {e}")

    async def _reconnect_websockets(self):
        if self.ws_reconnect_attempts_left <= 0:
            self.logger.critical("Max WebSocket reconnection attempts reached. Shutting down.")
            self.is_running = False # Trigger graceful shutdown
            return

        self.ws_reconnect_attempts_left -= 1
        delay = self.config.system.ws_reconnect_initial_delay_sec * (self.config.system.ws_reconnect_attempts - self.ws_reconnect_attempts_left)
        self.logger.warning(f"Attempting WebSocket reconnection in {delay} seconds... ({self.ws_reconnect_attempts_left} attempts left)")
        await asyncio.sleep(delay)

        self.trading_client.close_websockets() # Close existing connections
        try:
            await self._connect_websockets()
            self.logger.info("WebSocket reconnected successfully.")
        except WebSocketConnectionError:
            self.logger.error("WebSocket reconnection attempt failed.")
            # The loop will call this again if still disconnected

    async def _main_loop_tick(self):
        current_time = time.time()
        
        # Robust health check for both WebSocket connections.
        # If disconnected, attempt to reconnect
        if not (self.trading_client.ws_public and self.trading_client.ws_public.is_connected()):
            self.logger.warning("Public WebSocket disconnected. Attempting reconnection.")
            await self._reconnect_websockets()
            return # Skip trading logic this tick
        if not (self.trading_client.ws_private and self.trading_client.ws_private.is_connected()):
            self.logger.warning("Private WebSocket disconnected. Attempting reconnection.")
            await self._reconnect_websockets()
            return # Skip trading logic this tick

        # Heartbeat check
        if current_time - self.last_ws_message_time > self.config.system.ws_heartbeat_sec:
            self.logger.warning("WebSocket heartbeat lost (no new messages). Attempting reconnection.")
            await self._reconnect_websockets()
            return # Skip trading logic this tick
        
        if self.is_paused and current_time < self.pause_end_time: return
        elif self.is_paused:
            self.logger.info("Circuit breaker cooldown finished. Resuming trading.")
            self.is_paused = False
            
        await self._manage_orders()
        if current_time - self.last_status_report_time > self.config.system.status_report_interval_sec:
            await self._log_status_summary()
            self.last_status_report_time = current_time

    async def stop(self):
        if not self.is_running: return
        self.is_running = False
        self.logger.info("Initiating graceful shutdown...")
        if self.config.trading_mode != "DRY_RUN":
            await self._cancel_all_orders()
        
        # Ensure state is saved even if there's a problem with DB logging
        try:
            await self.state_manager.save_state({'active_orders': self.active_orders, 'metrics': self.config.metrics})
        except Exception as e:
            self.logger.error(f"Error during state saving on shutdown: {e}")

        try:
            await self.db_manager.log_bot_metrics(self.config.metrics)
        except Exception as e:
            self.logger.error(f"Could not log final metrics to DB. Error: {e}")
        
        self.trading_client.close_websockets()
        await self.db_manager.close()
        self.logger.info("Bot shut down successfully.")

    # --- WebSocket Handlers (Thread-safe) ---
    def _schedule_coro(self, coro: Coroutine):
        """Schedules a coroutine to be executed on the main event loop from a background thread."""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self.loop)
        else:
            self.logger.warning("Event loop not available or not running for scheduling coroutine from background thread. Coroutine skipped.")

    def _handle_orderbook_update(self, message: Dict):
        self.last_ws_message_time = time.time()
        try:
            if 'data' in message and message['topic'].startswith("orderbook"):
                data = message['data']
                if data.get('b') and data.get('a'):
                    self._schedule_coro(self._update_mid_price(data['b'], data['a']))
        except Exception as e:
            self.logger.error(f"Error handling orderbook update: {e}")
    
    async def _update_mid_price(self, bids: List, asks: List):
        async with self.market_data_lock:
            # Check if bids/asks are valid before conversion
            if not bids or not asks or not bids[0] or not asks[0] or not bids[0][0] or not asks[0][0]:
                self.logger.warning("Received invalid bids/asks in orderbook update. Skipping mid-price update.")
                return

            self.mid_price = (Decimal(bids[0][0]) + Decimal(asks[0][0])) / Decimal('2')
            self.mid_price_history.append(float(self.mid_price))
            self.circuit_breaker_history.append(float(self.mid_price))
            self.logger.debug(f"Mid-price updated to: {self.mid_price}")

    def _handle_order_update(self, message: Dict):
        self.last_ws_message_time = time.time()
        try:
            if 'data' in message:
                for order_data in message['data']:
                    self._schedule_coro(self._process_order_update(order_data))
        except Exception as e:
            self.logger.error(f"Error handling order update: {e}")

    async def _process_order_update(self, order_data: Dict):
        order_id, status = order_data['orderId'], order_data['orderStatus']
        self.logger.info(f"Order {order_id} status update: {status}")
        await self.db_manager.log_order_event(order_data)
        async with self.active_orders_lock:
            if order_id in self.active_orders:
                self.active_orders[order_id]['status'] = status
                if status == 'Filled':
                    await self._process_fill(order_data)
                    del self.active_orders[order_id]
                elif status in ['Cancelled', 'Rejected']:
                    del self.active_orders[order_id]

    def _handle_position_update(self, message: Dict):
        self.last_ws_message_time = time.time()
        try:
            if 'data' in message:
                for pos_data in message['data']:
                    if pos_data['symbol'] == self.config.symbol:
                        self._schedule_coro(self._process_position_update(pos_data))
        except Exception as e:
            self.logger.error(f"Error handling position update: {e}")

    async def _process_position_update(self, pos_data: Dict):
        async with self.balance_position_lock:
            new_pos_qty = Decimal(pos_data['size']) * (Decimal('1') if pos_data['side'] == 'Buy' else Decimal('-1'))
            if new_pos_qty != self.current_position_qty:
                self.current_position_qty = new_pos_qty
                self.logger.info(f"POSITION UPDATE (WS): Position is now {self.current_position_qty} {self.config.base_currency}")
            
            # Update unrealized PNL if applicable
            if self.config.category == 'linear' and 'unrealisedPnl' in pos_data:
                self.unrealized_pnl = Decimal(pos_data['unrealisedPnl'])
                self.logger.debug(f"UNREALIZED PNL (WS): {self.unrealized_pnl} {self.config.quote_currency}")

    # --- Strategy & Order Management ---
    async def _manage_orders(self):
        current_time = time.time()
        if (current_time - self.last_order_management_time) < self.config.system.order_refresh_interval_sec: return
        self.last_order_management_time = current_time
        if await self._check_circuit_breaker(): return
        
        async with self.market_data_lock, self.balance_position_lock:
            if self.mid_price == 0 or not self.market_info:
                self.logger.warning("Mid-price or market info not available, skipping order management.")
                return
            mid_price, pos_qty = self.mid_price, self.current_position_qty
        
        spread_pct = self._calculate_dynamic_spread()
        skew_factor = self._calculate_inventory_skew(mid_price, pos_qty)
        skewed_mid_price = mid_price * (Decimal('1') + skew_factor)
        target_bid_price = skewed_mid_price * (Decimal('1') - spread_pct)
        target_ask_price = skewed_mid_price * (Decimal('1') + spread_pct)
        target_bid_price, target_ask_price = self._enforce_min_profit_spread(mid_price, target_bid_price, target_ask_price)
        
        await self._reconcile_and_place_orders(target_bid_price, target_ask_price)

    async def _check_circuit_breaker(self) -> bool:
        cb_config = self.config.strategy.circuit_breaker
        if not cb_config.enabled: return False
        if len(self.circuit_breaker_history) < cb_config.check_interval_sec: return False # Not enough data

        # Calculate price change from the start to the end of the window
        # Ensure there's enough data for a meaningful comparison
        if len(self.circuit_breaker_history) > 1:
            start_price = self.circuit_breaker_history[0]
            end_price = self.circuit_breaker_history[-1]
            if start_price == 0: return False # Avoid division by zero
            price_change_pct = abs(end_price - start_price) / start_price
            
            if price_change_pct > float(cb_config.pause_threshold_pct):
                self.logger.warning(f"CIRCUIT BREAKER TRIPPED: Price changed {price_change_pct:.2%} in {cb_config.check_interval_sec}s. Pausing trading for {cb_config.pause_duration_sec}s.")
                self.is_paused = True
                self.pause_end_time = time.time() + cb_config.pause_duration_sec
                await self._cancel_all_orders()
                return True
        return False

    def _calculate_dynamic_spread(self) -> Decimal:
        ds_config = self.config.strategy.dynamic_spread
        if not ds_config.enabled or len(self.mid_price_history) < ds_config.volatility_window_sec:
            return self.config.strategy.base_spread_pct
        
        # Avoid calculating std on constant prices or single entry
        if len(self.mid_price_history) < 2 or np.all(np.array(list(self.mid_price_history)) == self.mid_price_history[0]):
            volatility = 0.0
        else:
            volatility = np.std(list(self.mid_price_history)) / np.mean(list(self.mid_price_history))
        
        dynamic_adjustment = Decimal(volatility) * ds_config.volatility_multiplier
        clamped_spread = max(ds_config.min_spread_pct, min(ds_config.max_spread_pct, self.config.strategy.base_spread_pct + dynamic_adjustment))
        self.logger.debug(f"Volatility: {volatility:.6f}, Dynamic Spread: {clamped_spread:.4%}")
        return clamped_spread

    def _calculate_inventory_skew(self, mid_price: Decimal, pos_qty: Decimal) -> Decimal:
        inv_config = self.config.strategy.inventory
        if not inv_config.enabled or self.config.max_net_exposure_usd <= 0: return Decimal('0')
        
        # Calculate current inventory value in quote currency
        current_inventory_value = pos_qty * mid_price
        
        # Calculate inventory ratio relative to max net exposure
        # Positive ratio means long, negative means short
        inventory_ratio = current_inventory_value / self.config.max_net_exposure_usd
        
        # Skew factor: if long (positive ratio), skew prices down (negative factor) to encourage sells.
        # if short (negative ratio), skew prices up (positive factor) to encourage buys.
        skew_factor = -inventory_ratio * inv_config.skew_intensity
        
        if abs(skew_factor) > 1e-6: # Log only if skew is significant
            self.logger.debug(f"Inventory skew active. Position Value: {current_inventory_value:.2f} {self.config.quote_currency}, Ratio: {inventory_ratio:.3f}, Skew: {skew_factor:.6f}")
        return skew_factor

    def _enforce_min_profit_spread(self, mid_price: Decimal, bid_p: Decimal, ask_p: Decimal) -> (Decimal, Decimal):
        if not self.market_info: return bid_p, ask_p
        min_spread_val = mid_price * self.config.strategy.min_profit_spread_after_fees_pct
        
        # Ensure ask is always greater than bid
        if ask_p <= bid_p:
            mid = (bid_p + ask_p) / 2
            ask_p = mid + (min_spread_val / Decimal('2')).quantize(self.market_info.price_precision)
            bid_p = mid - (min_spread_val / Decimal('2')).quantize(self.market_info.price_precision)

        if (ask_p - bid_p) < min_spread_val:
            self.logger.debug(f"Adjusting spread to enforce min profit. Original: {ask_p - bid_p:.6f}, Min: {min_spread_val:.6f}")
            half_spread = (min_spread_val / Decimal('2')).quantize(self.market_info.price_precision)
            mid = (bid_p + ask_p) / Decimal('2') # Recalculate mid
            return mid - half_spread, mid + half_spread
        return bid_p, ask_p

    async def _reconcile_and_place_orders(self, target_bid: Decimal, target_ask: Decimal):
        if not self.market_info: return
        target_bid = self.market_info.format_price(target_bid)
        target_ask = self.market_info.format_price(target_ask)
        
        cur_bid_order: Optional[Dict] = None
        cur_ask_order: Optional[Dict] = None
        to_cancel_orders = []

        async with self.active_orders_lock:
            # Identify existing orders and mark for cancellation if stale or duplicates
            for oid, o in list(self.active_orders.items()):
                is_stale = False
                if o['side'] == 'Buy':
                    # Check if the existing bid order is significantly different from the target bid
                    if abs(o['price'] - target_bid) > (o['price'] * self.config.strategy.order_stale_threshold_pct):
                        is_stale = True
                    if not cur_bid_order and not is_stale:
                        cur_bid_order = o
                    else:
                        to_cancel_orders.append((oid, o.get('orderLinkId')))
                else: # Sell order
                    if abs(o['price'] - target_ask) > (o['price'] * self.config.strategy.order_stale_threshold_pct):
                        is_stale = True
                    if not cur_ask_order and not is_stale:
                        cur_ask_order = o
                    else:
                        to_cancel_orders.append((oid, o.get('orderLinkId')))
        
        # Execute cancellations
        for oid, olid in to_cancel_orders:
            self.logger.info(f"Cancelling stale/duplicate order {oid} (Side: {self.active_orders.get(oid, {}).get('side')}, Price: {self.active_orders.get(oid, {}).get('price')}). Target Bid: {target_bid}, Target Ask: {target_ask}")
            await self._cancel_order(oid, olid)

        # Place new orders if none exist or if existing ones were cancelled
        if not cur_bid_order:
            buy_qty = await self._calculate_order_size("Buy", target_bid)
            if buy_qty > 0:
                self.logger.info(f"No active bid, placing new bid order: Price={target_bid}, Qty={buy_qty}")
                await self._place_limit_order("Buy", target_bid, buy_qty)
            else:
                self.logger.debug("Calculated buy quantity is zero, skipping bid order placement.")

        if not cur_ask_order:
            sell_qty = await self._calculate_order_size("Sell", target_ask)
            if sell_qty > 0:
                self.logger.info(f"No active ask, placing new ask order: Price={target_ask}, Qty={sell_qty}")
                await self._place_limit_order("Sell", target_ask, sell_qty)
            else:
                self.logger.debug("Calculated sell quantity is zero, skipping ask order placement.")

    async def _log_status_summary(self):
        async with self.balance_position_lock, self.active_orders_lock:
            pnl, win_rate, pos_qty = self.config.metrics.total_pnl, self.config.metrics.win_rate, self.current_position_qty
            
            # Calculate total exposure (including unrealized PNL for linear)
            exposure_usd = Decimal('0')
            if self.mid_price > 0:
                exposure_usd = pos_qty * self.mid_price
            
            pnl_summary = f"Realized PNL: {pnl:+.4f} {self.config.quote_currency}"
            if self.config.category == 'linear':
                pnl_summary += f" | Unrealized PNL: {self.unrealized_pnl:+.4f} {self.config.quote_currency}"

            active_buys = sum(1 for o in self.active_orders.values() if o['side'] == 'Buy')
            active_sells = sum(1 for o in self.active_orders.values() if o['side'] == 'Sell')
        
        self.logger.info(f"STATUS | {pnl_summary} | Win Rate: {win_rate:.2f}% | Position: {pos_qty} {self.config.base_currency} (Exposure: {exposure_usd:+.2f} {self.config.quote_currency}) | Orders: {active_buys} Buy / {active_sells} Sell")
        await self.db_manager.log_bot_metrics(self.config.metrics)


    async def _fetch_market_info(self) -> bool:
        info = await self.trading_client.get_instruments_info()
        if not info: return False
        self.market_info = MarketInfo(
            symbol=self.config.symbol,
            price_precision=Decimal(info['priceFilter']['tickSize']),
            quantity_precision=Decimal(info['lotSizeFilter']['qtyStep']),
            min_order_qty=Decimal(info['lotSizeFilter']['minOrderQty']),
            min_notional_value=Decimal(info['lotSizeFilter'].get('minNotionalValue', '0'))
        )
        self.logger.info(f"Market info fetched for {self.config.symbol}: {self.market_info}")
        return True

    async def _update_balance_and_position(self) -> bool:
        async with self.balance_position_lock:
            if self.config.trading_mode == "DRY_RUN":
                # Initialize DRY_RUN balance if not set
                if self.current_balance == Decimal('0'):
                    self.current_balance = Decimal('10000') # Starting capital for DRY_RUN
                    self.available_balance = self.current_balance
                return True

            balance_data = await self.trading_client.get_wallet_balance()
            if not balance_data:
                self.logger.error("Failed to fetch wallet balance.")
                return False

            found_quote_balance = False
            for coin in balance_data.get('coin', []):
                if coin['coin'] == self.config.quote_currency:
                    self.current_balance = Decimal(coin['walletBalance'])
                    self.available_balance = Decimal(coin.get('availableToWithdraw', coin['walletBalance']))
                    self.logger.debug(f"Balance: {self.current_balance} {self.config.quote_currency}, Available: {self.available_balance}")
                    await self.db_manager.log_balance_update(self.config.quote_currency, self.current_balance, self.available_balance)
                    found_quote_balance = True
                    break
            
            if not found_quote_balance:
                self.logger.warning(f"Could not find balance for {self.config.quote_currency}.")
                # Decide if this is a critical failure. For now, we allow it but log.

            if self.config.category == 'linear':
                position_data = await self.trading_client.get_position_info()
                if position_data and position_data.get('size'):
                    self.current_position_qty = Decimal(position_data['size']) * (Decimal('1') if position_data['side'] == 'Buy' else Decimal('-1'))
                    self.unrealized_pnl = Decimal(position_data.get('unrealisedPnl', '0'))
                else:
                    self.current_position_qty = Decimal('0')
                    self.unrealized_pnl = Decimal('0')
            else:
                self.current_position_qty = Decimal('0') # Spot doesn't typically have 'positions' in the same way
                self.unrealized_pnl = Decimal('0')

            self.logger.info(f"Updated Balance: {self.current_balance} {self.config.quote_currency}, Position: {self.current_position_qty} {self.config.base_currency}, UPNL: {self.unrealized_pnl}")
            return True

    async def _process_fill(self, o: Dict):
        side = o.get('side', 'Unknown')
        qty = Decimal(o.get('execQty', '0'))
        price = Decimal(o.get('execPrice', '0'))
        fee = Decimal(o.get('execFee', '0'))
        pnl = Decimal(o.get('pnl', '0'))
        
        self.logger.info(f"Order FILLED: {side} {qty} @ {price}, Fee: {fee}, PnL: {pnl}")
        await self.db_manager.log_trade_fill(o)
        await self._update_state_after_fill(fee, pnl)

    async def _update_state_after_fill(self, fee: Decimal, pnl: Decimal):
        self.logger.debug("Fill processed. Awaiting WS position update for confirmation of final balance/position.")
        m = self.config.metrics
        m.total_trades += 1
        m.total_fees += fee
        if pnl > 0:
            m.gross_profit += pnl
            m.wins += 1
        else:
            m.gross_loss += abs(pnl)
            m.losses += 1
        m.update_win_rate()
        # Trigger an explicit balance/position update to ensure consistency,
        # in case WS updates are delayed or missed.
        await self._update_balance_and_position()

    async def _cancel_order(self, order_id: str, order_link_id: Optional[str] = None):
        self.logger.info(f"Attempting to cancel order {order_id}...")
        if self.config.trading_mode == "DRY_RUN":
            self.logger.info(f"DRY_RUN: Would cancel order {order_id}.")
            async with self.active_orders_lock:
                if order_id in self.active_orders:
                    del self.active_orders[order_id]
            return

        if await self.trading_client.cancel_order(order_id, order_link_id):
            self.logger.info(f"Order {order_id} cancelled successfully.")
            async with self.active_orders_lock:
                if order_id in self.active_orders:
                    del self.active_orders[order_id]
        else:
            self.logger.error(f"Failed to cancel order {order_id} via API after retries.")

    async def _cancel_all_orders(self):
        self.logger.info("Canceling all open orders...")
        if self.config.trading_mode == "DRY_RUN":
            self.logger.info("DRY_RUN: Would cancel all open orders.")
        elif await self.trading_client.cancel_all_orders():
            self.logger.info("All orders cancelled successfully.")
        else:
            self.logger.error("Failed to cancel all orders via API after retries.")
        
        async with self.active_orders_lock:
            self.active_orders.clear()

    async def _calculate_order_size(self, side: str, price: Decimal) -> Decimal:
        async with self.balance_position_lock:
            capital = self.available_balance if self.config.category == 'spot' else self.current_balance
            pos_qty = self.current_position_qty
        
        if capital <= 0 or self.mid_price <= 0 or not self.market_info:
            self.logger.debug("Insufficient capital, zero mid_price, or no market info. Order size 0.")
            return Decimal('0')

        # Effective capital considering leverage for linear contracts
        eff_capital = capital * self.config.leverage if self.config.category == 'linear' else capital
        
        # Base order value derived from a percentage of effective capital
        order_val = min(
            eff_capital * self.config.strategy.base_order_size_pct_of_balance,
            eff_capital * self.config.max_order_size_pct
        )

        # Consider max net exposure for linear contracts
        if self.config.category == 'linear' and self.config.max_net_exposure_usd > 0:
            current_net_exposure_usd = abs(pos_qty * self.mid_price)
            remaining_exposure_usd = self.config.max_net_exposure_usd - current_net_exposure_usd
            
            if remaining_exposure_usd <= 0:
                self.logger.debug(f"Max net exposure ({self.config.max_net_exposure_usd} USD) reached. Current: {current_net_exposure_usd:.2f} USD. Order size 0.")
                return Decimal('0')
            
            order_val = min(order_val, remaining_exposure_usd)

        if order_val <= 0:
            self.logger.debug("Calculated order value is zero or negative. Order size 0.")
            return Decimal('0')

        qty = self.market_info.format_quantity(order_val / price)

        # Check against minimum order requirements
        if qty < self.market_info.min_order_qty:
            self.logger.debug(f"Calculated quantity {qty} is less than min_order_qty {self.market_info.min_order_qty}. Order size 0.")
            return Decimal('0')
        
        order_notional_value = qty * price
        min_notional = max(self.market_info.min_notional_value, self.config.min_order_value_usd)
        if order_notional_value < min_notional:
            self.logger.debug(f"Calculated notional value {order_notional_value:.2f} is less than min_notional_value {min_notional:.2f}. Order size 0.")
            return Decimal('0')

        self.logger.debug(f"Calculated {side} order size: {qty} {self.config.base_currency} (Notional: {order_notional_value:.2f} {self.config.quote_currency})")
        return qty

    async def _place_limit_order(self, side: str, price: Decimal, quantity: Decimal):
        if self.config.trading_mode == "DRY_RUN":
            oid = f"DRY_{side}_{int(time.time() * 1000)}"
            self.logger.info(f"DRY_RUN: Would place {side} order: ID={oid}, Qty={quantity}, Price={price}")
            async with self.active_orders_lock:
                self.active_orders[oid] = {'side': side, 'price': price, 'qty': quantity, 'status': 'New', 'orderLinkId': f"mm_{side}_{int(time.time() * 1000)}"}
            return
        
        if not self.market_info:
            self.logger.error("Cannot place order, market info not available.")
            return

        qty_f, price_f = self.market_info.format_quantity(quantity), self.market_info.format_price(price)
        if qty_f <= 0 or price_f <= 0:
            self.logger.warning(f"Attempted to place order with zero or negative quantity/price: Qty={qty_f}, Price={price_f}")
            return
        
        # Double check min order value before placing
        order_notional_value = qty_f * price_f
        min_notional = max(self.market_info.min_notional_value, self.config.min_order_value_usd)
        if order_notional_value < min_notional:
            self.logger.warning(f"Calculated order notional value {order_notional_value:.2f} is below minimum {min_notional:.2f}. Skipping order placement.")
            return

        time_in_force = "PostOnly" if self.config.post_only else self.config.time_in_force
        order_link_id = f"mm_{side}_{int(time.time() * 1000)}"
        params = {
            "category": self.config.category,
            "symbol": self.config.symbol,
            "side": side,
            "orderType": self.config.order_type,
            "qty": str(qty_f),
            "price": str(price_f),
            "timeInForce": time_in_force,
            "orderLinkId": order_link_id
        }
        
        result = await self.trading_client.place_order(params)
        if result and result.get('orderId'):
            oid = result['orderId']
            self.logger.info(f"Placed {side} order: ID={oid}, Price={price_f}, Qty={qty_f}")
            async with self.active_orders_lock:
                self.active_orders[oid] = {'side': side, 'price': price_f, 'qty': qty_f, 'status': 'New', 'orderLinkId': order_link_id}
            await self.db_manager.log_order_event({**params, 'orderId': oid, 'orderStatus': 'New'}, "Order placed")
        else:
            self.logger.error(f"Failed to place {side} order after retries. Params: {params}")

    async def _reconcile_orders_on_startup(self):
        if self.config.trading_mode == "DRY_RUN":
            self.logger.info("DRY_RUN mode: Skipping order reconciliation.")
            return
        
        self.logger.info("Reconciling active orders with exchange...")
        exchange_orders = {o['orderId']: o for o in await self.trading_client.get_open_orders()}
        
        async with self.active_orders_lock:
            local_ids = set(self.active_orders.keys())
            exchange_ids = set(exchange_orders.keys())

            # Orders in local state but not on exchange -> remove locally
            for oid in local_ids - exchange_ids:
                self.logger.warning(f"Local order {oid} not found on exchange. Removing from local state.")
                del self.active_orders[oid]

            # Orders on exchange but not in local state -> add locally
            for oid in exchange_ids - local_ids:
                o = exchange_orders[oid]
                self.logger.warning(f"Exchange order {oid} ({o['side']} {o['qty']} @ {o['price']}) not in local state. Adding.")
                self.active_orders[oid] = {
                    'side': o['side'],
                    'price': Decimal(o['price']),
                    'qty': Decimal(o['qty']),
                    'status': o['orderStatus'],
                    'orderLinkId': o.get('orderLinkId')
                }
            
            # Update status for orders present in both
            for oid in local_ids.intersection(exchange_ids):
                local_order = self.active_orders[oid]
                exchange_order = exchange_orders[oid]
                if local_order['status'] != exchange_order['orderStatus']:
                    self.logger.info(f"Order {oid} status mismatch. Updating from {local_order['status']} to {exchange_order['orderStatus']}.")
                    local_order['status'] = exchange_order['orderStatus']

        self.logger.info(f"Order reconciliation complete. {len(self.active_orders)} active orders after reconciliation.")

# =====================================================================
# MAIN ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    try:
        config = Config() # Config validation happens in __post_init__
        bot = BybitMarketMaker(config)
        asyncio.run(bot.run())
    except (KeyboardInterrupt, SystemExit):
        print("\nBot stopped by user.")
    except ValueError as e:
        print(f"\nConfiguration Error: {e}")
        sys.exit(1)
    except APIAuthError as e:
        print(f"\nAPI Authentication Error: {e}\nPlease check your API Key and Secret, their permissions, and ensure IP Whitelisting is correctly configured on Bybit.")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected critical error occurred during bot initialization or runtime: {e}")
        logging.getLogger('MarketMakerBot').critical(f"Unhandled exception in main: {e}", exc_info=True)
        sys.exit(1)
