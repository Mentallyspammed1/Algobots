import asyncio
import logging
import os
import pickle
import sys
import time
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal, getcontext
from typing import Any

import aiofiles
import aiosqlite
import numpy as np
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

# --- Core Setup ---
getcontext().prec = 28  # High precision for financial calculations
load_dotenv()


# --- Custom Exceptions ---
class APIAuthError(Exception):
    """Custom exception for API authentication/signature errors."""


class WebSocketConnectionError(Exception):
    """Custom exception for WebSocket connection failures."""


class MarketInfoError(Exception):
    """Custom exception for market information retrieval failures."""


class InitialBalanceError(Exception):
    """Custom exception for initial balance/position retrieval failures."""


class ConfigurationError(Exception):
    """Custom exception for invalid configuration settings."""


# =====================================================================
# CONFIGURATION & DATA CLASSES
# =====================================================================
@dataclass
class TradeMetrics:
    total_trades: int = 0
    gross_profit: Decimal = Decimal("0")
    gross_loss: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    # PnL Tracking - Core additions
    realized_pnl: Decimal = Decimal("0")
    current_asset_holdings: Decimal = Decimal("0")
    average_entry_price: Decimal = Decimal(
        "0"
    )  # Weighted average price for current holdings
    last_pnl_update_timestamp: datetime | None = None

    @property
    def total_pnl(self) -> Decimal:
        # This property now reflects the true realized PnL from closed positions
        return self.realized_pnl - self.total_fees

    def update_win_rate(self):
        self.win_rate = (
            (self.wins / self.total_trades * 100.0) if self.total_trades > 0 else 0.0
        )

    def update_pnl_on_buy(self, quantity: Decimal, price: Decimal):
        """Updates average entry price on a buy."""
        if self.current_asset_holdings > 0:
            self.average_entry_price = (
                (self.average_entry_price * self.current_asset_holdings)
                + (price * quantity)
            ) / (self.current_asset_holdings + quantity)
        else:
            self.average_entry_price = price
        self.current_asset_holdings += quantity
        self.last_pnl_update_timestamp = datetime.now(timezone.utc)

    def update_pnl_on_sell(self, quantity: Decimal, price: Decimal):
        """Updates realized PnL and asset holdings on a sell."""
        if self.current_asset_holdings < quantity:
            # This should ideally not happen if bot logic is sound, but good for robustness
            raise ValueError(
                f"Attempted to sell {quantity} but only {self.current_asset_holdings} held."
            )

        # Calculate PnL for the portion being sold
        profit_loss_on_sale = (price - self.average_entry_price) * quantity
        self.realized_pnl += profit_loss_on_sale

        self.current_asset_holdings -= quantity
        if self.current_asset_holdings == Decimal("0"):
            self.average_entry_price = Decimal("0")  # Reset if all holdings are sold
        # If only part is sold, average_entry_price remains the same for the remaining holdings
        self.last_pnl_update_timestamp = datetime.now(timezone.utc)

    def calculate_unrealized_pnl(self, current_price: Decimal) -> Decimal:
        """Calculates unrealized PnL based on current market price."""
        if self.current_asset_holdings > 0 and self.average_entry_price > 0:
            return (
                current_price - self.average_entry_price
            ) * self.current_asset_holdings
        return Decimal("0")


@dataclass
class InventoryStrategyConfig:
    enabled: bool = True
    skew_intensity: Decimal = Decimal(
        "0.5"
    )  # How much inventory affects price, e.g., 0.5 means 1% inventory -> 0.5% price skew
    max_inventory_ratio: Decimal = Decimal(
        "0.5"
    )  # Max inventory percentage (e.g., 0.5 means 50% of max_net_exposure)


@dataclass
class DynamicSpreadConfig:
    enabled: bool = True
    volatility_window_sec: int = 60  # Window for calculating volatility in seconds
    volatility_multiplier: Decimal = Decimal(
        "2.0"
    )  # Multiplier for volatility to adjust spread
    min_spread_pct: Decimal = Decimal("0.0005")  # 0.05%
    max_spread_pct: Decimal = Decimal("0.01")  # 1%
    price_change_smoothing_factor: Decimal = Decimal(
        "0.2"
    )  # Factor for exponential moving average of mid_price for smoother volatility


@dataclass
class CircuitBreakerConfig:
    enabled: bool = True
    pause_threshold_pct: Decimal = Decimal("0.02")  # 2% price change
    check_window_sec: int = 10  # Check over this duration
    pause_duration_sec: int = 60  # Pause for this duration if tripped
    cool_down_after_trip_sec: int = (
        300  # Additional cooldown after pause ends before re-enabling
    )


@dataclass
class StrategyConfig:
    base_spread_pct: Decimal = Decimal("0.001")  # 0.1%
    base_order_size_pct_of_balance: Decimal = Decimal(
        "0.005"
    )  # 0.5% of available balance
    order_stale_threshold_pct: Decimal = Decimal(
        "0.0005"
    )  # 0.05% difference to consider order stale
    min_profit_spread_after_fees_pct: Decimal = Decimal(
        "0.0002"
    )  # Minimum profit spread after estimated fees
    inventory: InventoryStrategyConfig = field(default_factory=InventoryStrategyConfig)
    dynamic_spread: DynamicSpreadConfig = field(default_factory=DynamicSpreadConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)


@dataclass
class SystemConfig:
    loop_interval_sec: float = 0.5  # Faster loop for responsiveness
    order_refresh_interval_sec: float = 5.0
    ws_heartbeat_sec: int = (
        30  # Max time without WS message before considering it stale
    )
    cancellation_rate_limit_sec: float = 0.2
    status_report_interval_sec: int = 30
    ws_reconnect_attempts: int = 5
    ws_reconnect_initial_delay_sec: int = 5  # Initial delay for WS reconnect
    api_retry_attempts: int = 5
    api_retry_initial_delay_sec: float = 0.5  # Initial delay for API retries
    api_retry_max_delay_sec: float = (
        10.0  # Max delay for API retries with exponential backoff
    )
    health_check_interval_sec: int = 10  # Interval for internal health checks


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
    trading_mode: str = "DRY_RUN"  # DRY_RUN, TESTNET, LIVE
    symbol: str = "XLMUSDT"
    category: str = "linear"  # linear, inverse, spot
    leverage: Decimal = Decimal("1")  # Only applicable for linear/inverse
    min_order_value_usd: Decimal = Decimal("10")  # Minimum notional value for an order
    max_order_size_pct: Decimal = Decimal(
        "0.1"
    )  # Max percentage of effective capital for a single order
    max_net_exposure_usd: Decimal = Decimal(
        "500"
    )  # Max total exposure in USD (for linear contracts)
    order_type: str = "Limit"
    time_in_force: str = "GTC"
    post_only: bool = True
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    system: SystemConfig = field(default_factory=SystemConfig)
    files: FilesConfig = field(default_factory=FilesConfig)
    metrics: TradeMetrics = field(
        default_factory=TradeMetrics
    )  # Metrics now includes PnL tracking
    base_currency: str = field(init=False)
    quote_currency: str = field(init=False)
    initial_dry_run_capital: Decimal = Decimal("10000")  # For DRY_RUN mode

    def __post_init__(self):
        # Determine base and quote currencies from symbol
        if self.symbol.endswith("USDT"):
            self.base_currency = self.symbol[:-4]
            self.quote_currency = "USDT"
        elif self.symbol.endswith("USD"):
            self.base_currency = self.symbol[:-3]
            self.quote_currency = "USD"
        else:
            # Fallback for other symbols, e.g., BTCETH -> BTC, ETH
            if len(self.symbol) == 6:  # Heuristic for 3-char base/quote
                self.base_currency = self.symbol[:3]
                self.quote_currency = self.symbol[3:]
            else:
                raise ConfigurationError(
                    f"Could not parse base/quote currency from symbol: {self.symbol}"
                )

        # Harmonize testnet setting based on trading_mode
        if self.trading_mode == "TESTNET":
            self.testnet = True
        elif self.trading_mode == "LIVE":
            self.testnet = False

        # Ensure API keys are present in non-DRY_RUN modes
        if self.trading_mode not in ["DRY_RUN", "SIMULATION"] and (
            not self.api_key or not self.api_secret
        ):
            raise ConfigurationError(
                "API_KEY and API_SECRET must be set in .env for TESTNET or LIVE trading_mode."
            )

        # Validate leverage
        if self.category in ["linear", "inverse"] and self.leverage <= 0:
            raise ConfigurationError(
                "Leverage must be a positive decimal for linear/inverse categories."
            )

        # Ensure max_net_exposure_usd is positive if inventory strategy is enabled
        if self.strategy.inventory.enabled and self.max_net_exposure_usd <= 0:
            raise ConfigurationError(
                "max_net_exposure_usd must be positive when inventory strategy is enabled."
            )


@dataclass
class MarketInfo:
    symbol: str
    price_precision: Decimal
    quantity_precision: Decimal
    min_order_qty: Decimal
    min_notional_value: Decimal
    maker_fee_rate: Decimal = Decimal("0")
    taker_fee_rate: Decimal = Decimal("0")

    def format_price(self, p: Decimal) -> Decimal:
        return p.quantize(self.price_precision, rounding=ROUND_DOWN)

    def format_quantity(self, q: Decimal) -> Decimal:
        return q.quantize(self.quantity_precision, rounding=ROUND_DOWN)


# =====================================================================
# LOGGING, STATE, and DB
# =====================================================================
def setup_logger(config: FilesConfig) -> logging.Logger:
    logger = logging.getLogger("MarketMakerBot")
    logger.setLevel(getattr(logging, config.log_level.upper()))
    if not logger.handlers:  # Prevent adding handlers multiple times if setup_logger is called more than once
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

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

    async def save_state(self, state: dict):
        try:
            async with aiofiles.open(self.file_path, "wb") as f:
                await f.write(pickle.dumps(state))
            self.logger.info("Bot state saved successfully.")
        except Exception as e:
            self.logger.error(f"Error saving state: {e}")

    async def load_state(self) -> dict | None:
        if not os.path.exists(self.file_path):
            return None
        try:
            async with aiofiles.open(self.file_path, "rb") as f:
                return pickle.loads(await f.read())
        except Exception as e:
            self.logger.error(
                f"Error loading state from {self.file_path}: {e}. Starting fresh."
            )
            return None


class DBManager:
    def __init__(self, db_file: str, logger: logging.Logger):
        self.db_file = db_file
        self.conn: aiosqlite.Connection | None = None
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
        if not self.conn:
            await self.connect()  # Ensure connection is open
        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS order_events (id INTEGER PRIMARY KEY, timestamp TEXT, order_id TEXT, order_link_id TEXT, symbol TEXT, side TEXT, order_type TEXT, price TEXT, qty TEXT, status TEXT, message TEXT);
            CREATE TABLE IF NOT EXISTS trade_fills (id INTEGER PRIMARY KEY, timestamp TEXT, order_id TEXT, trade_id TEXT, symbol TEXT, side TEXT, exec_price TEXT, exec_qty TEXT, fee TEXT, fee_currency TEXT, pnl TEXT, realized_pnl_impact TEXT);
            CREATE TABLE IF NOT EXISTS balance_updates (id INTEGER PRIMARY KEY, timestamp TEXT, currency TEXT, wallet_balance TEXT, available_balance TEXT);
            CREATE TABLE IF NOT EXISTS bot_metrics (id INTEGER PRIMARY KEY, timestamp TEXT, total_trades INTEGER, total_pnl TEXT, realized_pnl TEXT, unrealized_pnl TEXT, gross_profit TEXT, gross_loss TEXT, total_fees TEXT, wins INTEGER, losses INTEGER, win_rate REAL, current_asset_holdings TEXT, average_entry_price TEXT);
        """)
        await self.conn.commit()
        self.logger.info("Database tables checked/created.")

    async def log_order_event(self, o: dict, m: str | None = None):
        if not self.conn:
            return  # Don't log if DB connection failed
        try:
            await self.conn.execute(
                "INSERT INTO order_events (timestamp, order_id, order_link_id, symbol, side, order_type, price, qty, status, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    o.get("orderId"),
                    o.get("orderLinkId"),
                    o.get("symbol"),
                    o.get("side"),
                    o.get("orderType"),
                    str(o.get("price", "0")),
                    str(o.get("qty", "0")),
                    o.get("orderStatus"),
                    m,
                ),
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging order event to DB: {e}")

    async def log_trade_fill(self, t: dict, realized_pnl_impact: Decimal):
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT INTO trade_fills (timestamp, order_id, trade_id, symbol, side, exec_price, exec_qty, fee, fee_currency, pnl, realized_pnl_impact) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    t.get("orderId"),
                    t.get("execId"),
                    t.get("symbol"),
                    t.get("side"),
                    str(t.get("execPrice", "0")),
                    str(t.get("execQty", "0")),
                    str(t.get("execFee", "0")),
                    t.get("feeCurrency"),
                    str(t.get("pnl", "0")),
                    str(realized_pnl_impact),
                ),
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging trade fill to DB: {e}")

    async def log_balance_update(self, c: str, wb: Decimal, ab: Decimal | None = None):
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT INTO balance_updates (timestamp, currency, wallet_balance, available_balance) VALUES (?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    c,
                    str(wb),
                    str(ab) if ab else None,
                ),
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging balance update to DB: {e}")

    async def log_bot_metrics(self, m: TradeMetrics, unrealized_pnl: Decimal):
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT INTO bot_metrics (timestamp, total_trades, total_pnl, realized_pnl, unrealized_pnl, gross_profit, gross_loss, total_fees, wins, losses, win_rate, current_asset_holdings, average_entry_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    m.total_trades,
                    str(m.total_pnl + unrealized_pnl),
                    str(m.realized_pnl),
                    str(unrealized_pnl),
                    str(m.gross_profit),
                    str(m.gross_loss),
                    str(m.total_fees),
                    m.wins,
                    m.losses,
                    m.win_rate,
                    str(m.current_asset_holdings),
                    str(m.average_entry_price),
                ),
            )
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
        self.http_session = HTTP(
            testnet=self.config.testnet,
            api_key=self.config.api_key,
            api_secret=self.config.api_secret,
        )
        self.ws_public: WebSocket | None = None
        self.ws_private: WebSocket | None = None
        self.last_cancel_time = 0

        # Store original methods to apply tenacity decorator dynamically
        self._original_get_instruments_info = self.get_instruments_info_impl
        self._original_get_wallet_balance = self.get_wallet_balance_impl
        self._original_get_position_info = self.get_position_info_impl
        self._original_set_leverage = self.set_leverage_impl
        self._original_get_open_orders = self.get_open_orders_impl
        self._original_place_order = self.place_order_impl
        self._original_cancel_order = self.cancel_order_impl
        self._original_cancel_all_orders = self.cancel_all_orders_impl

        # Apply the decorator during initialization
        self._initialize_api_retry_decorator()

    def _get_api_retry_decorator(self):
        """Returns a tenacity retry decorator configured with current system settings."""
        return retry(
            stop=stop_after_attempt(self.config.system.api_retry_attempts),
            wait=wait_exponential_jitter(
                initial=self.config.system.api_retry_initial_delay_sec,
                max=self.config.system.api_retry_max_delay_sec,
            ),
            retry=retry_if_exception_type(Exception),
            before_sleep=before_sleep_log(self.logger, logging.WARNING),
            reraise=True,
        )

    def _initialize_api_retry_decorator(self):
        """Applies the dynamically configured retry decorator to API methods."""
        api_retry = self._get_api_retry_decorator()

        # Assign decorated versions to the public method names
        self.get_instruments_info = api_retry(self._original_get_instruments_info)
        self.get_wallet_balance = api_retry(self._original_get_wallet_balance)
        self.get_position_info = api_retry(self._original_get_position_info)
        self.set_leverage = api_retry(self._original_set_leverage)
        self.get_open_orders = api_retry(self._original_get_open_orders)
        self.place_order = api_retry(self._original_place_order)
        self.cancel_order = api_retry(self._original_cancel_order)
        self.cancel_all_orders = api_retry(self._original_cancel_all_orders)
        self.logger.debug("API retry decorators initialized and applied.")

    def _handle_response(self, response: Any, action: str):
        if not isinstance(response, dict):
            self.logger.error(
                f"API {action} failed: Invalid response format. Response: {response}"
            )
            raise ValueError(f"Invalid API response for {action}")
        ret_code = response.get("retCode", -1)
        if ret_code == 0:
            self.logger.debug(f"API {action} successful.")
            return response.get("result", {})
        ret_msg = response.get("retMsg", "Unknown error")
        self.logger.error(
            f"API {action} failed: {ret_msg} (ErrCode: {ret_code}). Full response: {response}"
        )
        if ret_code == 10004:
            raise APIAuthError(
                f"Authentication failed: {ret_msg}. Check API key permissions and validity."
            )
        # For other errors, raise a generic Exception so tenacity can retry
        raise Exception(f"API {action} failed: {ret_msg} (ErrCode: {ret_code})")

    # Original, undecorated API methods (implementation details)
    async def get_instruments_info_impl(self) -> dict | None:
        result = self._handle_response(
            self.http_session.get_instruments_info(
                category=self.config.category, symbol=self.config.symbol
            ),
            "get_instruments_info",
        )
        return result.get("list", [{}])[0] if result else None

    async def get_wallet_balance_impl(self) -> dict | None:
        account_type = (
            "UNIFIED" if self.config.category in ["linear", "inverse"] else "SPOT"
        )
        result = self._handle_response(
            self.http_session.get_wallet_balance(accountType=account_type),
            "get_wallet_balance",
        )
        return result.get("list", [{}])[0] if result else None

    async def get_position_info_impl(self) -> dict | None:
        if self.config.category not in ["linear", "inverse"]:
            return None
        response = self.http_session.get_positions(
            category=self.config.category, symbol=self.config.symbol
        )
        result = self._handle_response(response, "get_position_info")
        if result and result.get("list"):
            for position in result["list"]:
                if position["symbol"] == self.config.symbol:
                    return position
        return None

    async def set_leverage_impl(self, leverage: Decimal) -> bool:
        if self.config.category not in ["linear", "inverse"]:
            return True
        response = self.http_session.set_leverage(
            category=self.config.category,
            symbol=self.config.symbol,
            buyLeverage=str(leverage),
            sellLeverage=str(leverage),
        )
        return (
            self._handle_response(response, f"set_leverage to {leverage}") is not None
        )

    async def get_open_orders_impl(self) -> list[dict]:
        result = self._handle_response(
            self.http_session.get_open_orders(
                category=self.config.category, symbol=self.config.symbol, limit=50
            ),
            "get_open_orders",
        )
        return result.get("list", []) if result else []

    async def place_order_impl(self, params: dict) -> dict | None:
        return self._handle_response(
            self.http_session.place_order(**params),
            f"place_order ({params.get('side')} {params.get('qty')} @ {params.get('price')})",
        )

    async def cancel_order_impl(
        self, order_id: str, order_link_id: str | None = None
    ) -> bool:
        current_time = time.time()
        # Respect rate limit within the bot's logic, before API call
        if (
            current_time - self.last_cancel_time
        ) < self.config.system.cancellation_rate_limit_sec:
            await asyncio.sleep(
                self.config.system.cancellation_rate_limit_sec
                - (current_time - self.last_cancel_time)
            )
        params = {
            "category": self.config.category,
            "symbol": self.config.symbol,
            "orderId": order_id,
        }
        if order_link_id:
            params["orderLinkId"] = order_link_id
        response = self.http_session.cancel_order(**params)
        self.last_cancel_time = time.time()
        return self._handle_response(response, f"cancel_order {order_id}") is not None

    async def cancel_all_orders_impl(self) -> bool:
        params = {"category": self.config.category, "symbol": self.config.symbol}
        return (
            self._handle_response(
                self.http_session.cancel_all_orders(**params), "cancel_all_orders"
            )
            is not None
        )

    # Public methods, which will be decorated by tenacity
    get_instruments_info: Callable[[], Coroutine[Any, Any, dict | None]]
    get_wallet_balance: Callable[[], Coroutine[Any, Any, dict | None]]
    get_position_info: Callable[[], Coroutine[Any, Any, dict | None]]
    set_leverage: Callable[[Decimal], Coroutine[Any, Any, bool]]
    get_open_orders: Callable[[], Coroutine[Any, Any, list[dict]]]
    place_order: Callable[[dict], Coroutine[Any, Any, dict | None]]
    cancel_order: Callable[[str, str | None], Coroutine[Any, Any, bool]]
    cancel_all_orders: Callable[[], Coroutine[Any, Any, bool]]

    def _init_public_ws(self, callback: Callable):
        self.logger.info("Initializing PUBLIC orderbook stream...")
        self.ws_public = WebSocket(
            testnet=self.config.testnet, channel_type=self.config.category
        )
        self.ws_public.orderbook_stream(
            symbol=self.config.symbol, depth=1, callback=callback
        )

    def _init_private_ws(
        self, order_callback: Callable, position_callback: Callable | None = None
    ):
        self.logger.info("Initializing PRIVATE streams (orders, positions)...")
        self.ws_private = WebSocket(
            testnet=self.config.testnet,
            api_key=self.config.api_key,
            api_secret=self.config.api_secret,
            channel_type="private",
        )
        self.ws_private.order_stream(callback=order_callback)
        if position_callback and self.config.category in ["linear", "inverse"]:
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

        self.market_info: MarketInfo | None = None
        self.mid_price = Decimal("0")
        self.current_balance = Decimal("0")
        self.available_balance = Decimal("0")
        self.current_position_qty = Decimal(
            "0"
        )  # Positive for long, negative for short (for derivatives)
        self.unrealized_pnl_derivatives = Decimal("0")  # From exchange for derivatives

        self.active_orders: dict[
            str, dict
        ] = {}  # orderId -> {side, price, qty, status, orderLinkId, symbol}
        self.is_running = False
        self.last_order_management_time = 0
        self.last_ws_message_time = time.time()
        self.last_status_report_time = 0
        self.last_health_check_time = 0

        self.market_data_lock = asyncio.Lock()
        self.active_orders_lock = asyncio.Lock()
        self.balance_position_lock = asyncio.Lock()

        # History for dynamic spread and circuit breaker
        self.mid_price_history = deque(
            maxlen=self.config.strategy.dynamic_spread.volatility_window_sec * 2
        )  # Store more data than window length
        self.circuit_breaker_price_points: deque[tuple[float, Decimal]] = deque(
            maxlen=self.config.strategy.circuit_breaker.check_window_sec * 2
        )  # (timestamp, price)
        self.smoothed_mid_price: Decimal = Decimal("0")  # For EMA smoothing

        self.is_paused = False
        self.pause_end_time = 0
        self.circuit_breaker_cooldown_end_time = 0
        self.ws_reconnect_attempts_left = self.config.system.ws_reconnect_attempts
        self.loop: asyncio.AbstractEventLoop | None = None  # Captured at runtime

        self.logger.info(
            f"Market Maker Bot Initialized. Trading Mode: {self.config.trading_mode}"
        )
        if self.config.testnet:
            self.logger.info("Running on Bybit Testnet.")

    # --- Core Lifecycle & Setup ---
    async def run(self):
        self.is_running = True
        self.loop = asyncio.get_running_loop()  # Capture the running event loop
        try:
            await self._initialize_bot()
            if self.config.trading_mode not in ["DRY_RUN", "SIMULATION"]:
                await self._connect_websockets()  # Initial WS connection
            while self.is_running:
                await self._main_loop_tick()
                await asyncio.sleep(self.config.system.loop_interval_sec)
        except (
            APIAuthError,
            WebSocketConnectionError,
            asyncio.CancelledError,
            KeyboardInterrupt,
        ) as e:
            self.logger.info(f"Bot stopping due to: {type(e).__name__} - {e}")
        except Exception as e:
            self.logger.critical(
                f"An unhandled error occurred in the main loop: {e}", exc_info=True
            )
        finally:
            await self.stop()

    async def _initialize_bot(self):
        self.logger.info("Performing initial setup...")
        # Configuration validation
        self._validate_config()

        await self.db_manager.connect()
        await self.db_manager.create_tables()

        if not await self._fetch_market_info():
            raise MarketInfoError("Failed to fetch market info. Shutting down.")

        if not await self._update_balance_and_position():
            raise InitialBalanceError(
                "Failed to fetch initial balance/position. Shutting down."
            )

        if self.config.trading_mode not in ["DRY_RUN", "SIMULATION"]:
            if self.config.category in [
                "linear",
                "inverse",
            ] and not await self.trading_client.set_leverage(self.config.leverage):
                raise InitialBalanceError("Failed to set leverage. Shutting down.")
        else:
            self.logger.info(
                f"{self.config.trading_mode} mode: Skipping leverage setting."
            )

        await self._load_bot_state()
        await self._reconcile_orders_on_startup()
        self.logger.info("Initial setup successful.")

    def _validate_config(self):
        # Additional checks for configuration
        if self.config.strategy.dynamic_spread.enabled:
            if not (
                Decimal("0")
                <= self.config.strategy.dynamic_spread.min_spread_pct
                <= self.config.strategy.dynamic_spread.max_spread_pct
            ):
                raise ConfigurationError(
                    "Dynamic spread min/max percentages are invalid."
                )
        if self.config.leverage <= 0:
            raise ConfigurationError("Leverage must be a positive decimal.")
        if self.config.max_net_exposure_usd < 0:
            raise ConfigurationError("Max net exposure must be non-negative.")
        if self.config.category not in ["linear", "inverse", "spot"]:
            raise ConfigurationError(f"Unsupported category: {self.config.category}")
        self.logger.info("Configuration validated successfully.")

    async def _load_bot_state(self):
        state = await self.state_manager.load_state()
        if state:
            self.active_orders = state.get("active_orders", {})
            self.config.metrics = state.get("metrics", self.config.metrics)
            # Ensure Decimal types are restored correctly
            self.config.metrics.realized_pnl = Decimal(
                str(self.config.metrics.realized_pnl)
            )
            self.config.metrics.current_asset_holdings = Decimal(
                str(self.config.metrics.current_asset_holdings)
            )
            self.config.metrics.average_entry_price = Decimal(
                str(self.config.metrics.average_entry_price)
            )

            self.logger.info(
                f"Loaded state with {len(self.active_orders)} active orders and metrics: {self.config.metrics}"
            )
            # Restore any pause state
            self.is_paused = state.get("is_paused", False)
            self.pause_end_time = state.get("pause_end_time", 0)
            self.circuit_breaker_cooldown_end_time = state.get(
                "circuit_breaker_cooldown_end_time", 0
            )
        else:
            self.logger.info("No saved state found. Starting fresh.")

    async def _connect_websockets(self):
        self.logger.info("Connecting WebSockets...")
        try:
            self.trading_client._init_public_ws(self._handle_orderbook_update)
            self.trading_client._init_private_ws(
                self._handle_order_update, self._handle_position_update
            )
            self.ws_reconnect_attempts_left = (
                self.config.system.ws_reconnect_attempts
            )  # Reset attempts on successful connect
            self.logger.info("WebSockets connected and subscribed.")
        except Exception as e:
            self.logger.error(f"Failed to establish initial WebSocket connections: {e}")
            raise WebSocketConnectionError(f"Initial WS connection failed: {e}")

    async def _reconnect_websockets(self):
        if self.ws_reconnect_attempts_left <= 0:
            self.logger.critical(
                "Max WebSocket reconnection attempts reached. Shutting down."
            )
            self.is_running = False  # Trigger graceful shutdown
            return

        self.ws_reconnect_attempts_left -= 1
        delay = self.config.system.ws_reconnect_initial_delay_sec * (
            2
            ** (
                self.config.system.ws_reconnect_attempts
                - self.ws_reconnect_attempts_left
                - 1
            )
        )
        delay = min(delay, 60)  # Cap max delay to 60 seconds
        self.logger.warning(
            f"Attempting WebSocket reconnection in {delay:.1f} seconds... ({self.ws_reconnect_attempts_left} attempts left)"
        )
        await asyncio.sleep(delay)

        self.trading_client.close_websockets()  # Close existing connections
        try:
            await self._connect_websockets()
            self.logger.info("WebSocket reconnected successfully.")
        except WebSocketConnectionError:
            self.logger.error("WebSocket reconnection attempt failed.")
            # The loop will call this again if still disconnected

    async def _main_loop_tick(self):
        current_time = time.time()

        if self.config.trading_mode not in ["DRY_RUN", "SIMULATION"]:
            await self._websocket_health_check(current_time)
            if not self.is_running:
                return  # Check if health check decided to stop bot

        await self._periodic_health_check(current_time)

        if self.is_paused and current_time < self.pause_end_time:
            self.logger.debug(
                f"Bot is paused. Resuming in {int(self.pause_end_time - current_time)}s."
            )
            return  # Bot is paused
        elif self.is_paused:
            self.logger.info("Circuit breaker cooldown finished. Resuming trading.")
            self.is_paused = False
            self.circuit_breaker_cooldown_end_time = (
                current_time
                + self.config.strategy.circuit_breaker.cool_down_after_trip_sec
            )

        if current_time < self.circuit_breaker_cooldown_end_time:
            self.logger.debug(
                f"Circuit breaker in cooldown. Resuming trading in {int(self.circuit_breaker_cooldown_end_time - current_time)}s."
            )
            return

        await self._manage_orders()
        if (
            current_time - self.last_status_report_time
            > self.config.system.status_report_interval_sec
        ):
            await self._log_status_summary()
            self.last_status_report_time = current_time

    async def _websocket_health_check(self, current_time: float):
        # Robust health check for both WebSocket connections.
        # If disconnected, attempt to reconnect
        if not (
            self.trading_client.ws_public
            and self.trading_client.ws_public.is_connected()
        ):
            self.logger.warning(
                "Public WebSocket disconnected. Attempting reconnection."
            )
            await self._reconnect_websockets()
            return  # Skip trading logic this tick
        if not (
            self.trading_client.ws_private
            and self.trading_client.ws_private.is_connected()
        ):
            self.logger.warning(
                "Private WebSocket disconnected. Attempting reconnection."
            )
            await self._reconnect_websockets()
            return  # Skip trading logic this tick

        # Heartbeat check (applies to both public/private, assuming they both update last_ws_message_time)
        if (
            current_time - self.last_ws_message_time
            > self.config.system.ws_heartbeat_sec
        ):
            self.logger.warning(
                "WebSocket heartbeat lost (no new messages). Attempting reconnection."
            )
            await self._reconnect_websockets()
            return  # Skip trading logic this tick

    async def _periodic_health_check(self, current_time: float):
        if (
            current_time - self.last_health_check_time
        ) < self.config.system.health_check_interval_sec:
            return

        # Re-fetch balance and position periodically to ensure consistency
        # This is a fallback/double-check for WS updates
        await self._update_balance_and_position()
        self.last_health_check_time = current_time

    async def stop(self):
        if not self.is_running:
            return
        self.is_running = False
        self.logger.info("Initiating graceful shutdown...")
        if self.config.trading_mode not in ["DRY_RUN", "SIMULATION"]:
            await self._cancel_all_orders()

        # Save state including pause status
        state_to_save = {
            "active_orders": self.active_orders,
            "metrics": self.config.metrics,
            "is_paused": self.is_paused,
            "pause_end_time": self.pause_end_time,
            "circuit_breaker_cooldown_end_time": self.circuit_breaker_cooldown_end_time,
        }
        try:
            await self.state_manager.save_state(state_to_save)
        except Exception as e:
            self.logger.error(f"Error during state saving on shutdown: {e}")

        try:
            unrealized_pnl = self.config.metrics.calculate_unrealized_pnl(
                self.mid_price
            )
            await self.db_manager.log_bot_metrics(self.config.metrics, unrealized_pnl)
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
            self.logger.warning(
                "Event loop not available or not running for scheduling coroutine from background thread. Coroutine skipped."
            )

    def _handle_orderbook_update(self, message: dict):
        self.last_ws_message_time = time.time()
        try:
            if "data" in message and message["topic"].startswith("orderbook"):
                data = message["data"]
                if data.get("b") and data.get("a"):
                    # Only process if both bids and asks are available
                    self._schedule_coro(self._update_mid_price(data["b"], data["a"]))
        except Exception as e:
            self.logger.error(f"Error handling orderbook update: {e}", exc_info=True)

    async def _update_mid_price(self, bids: list, asks: list):
        async with self.market_data_lock:
            # Check if bids/asks are valid before conversion
            if (
                not bids
                or not asks
                or not bids[0]
                or not asks[0]
                or not bids[0][0]
                or not asks[0][0]
            ):
                self.logger.warning(
                    "Received invalid bids/asks in orderbook update. Skipping mid-price update."
                )
                return

            new_mid_price = (Decimal(bids[0][0]) + Decimal(asks[0][0])) / Decimal("2")

            if new_mid_price != self.mid_price:
                self.mid_price = new_mid_price
                self.mid_price_history.append(
                    float(self.mid_price)
                )  # Store float for numpy
                self.circuit_breaker_price_points.append(
                    (time.time(), self.mid_price)
                )  # Store Decimal for precision

                # Apply EMA smoothing for a more stable "current" price for calculations
                if self.smoothed_mid_price == Decimal("0"):
                    self.smoothed_mid_price = new_mid_price
                else:
                    alpha = self.config.strategy.dynamic_spread.price_change_smoothing_factor
                    self.smoothed_mid_price = (alpha * new_mid_price) + (
                        (Decimal("1") - alpha) * self.smoothed_mid_price
                    )

                self.logger.debug(
                    f"Mid-price updated to: {self.mid_price}, Smoothed: {self.smoothed_mid_price}"
                )

    def _handle_order_update(self, message: dict):
        self.last_ws_message_time = time.time()
        try:
            if "data" in message:
                for order_data in message["data"]:
                    if (
                        order_data.get("symbol") == self.config.symbol
                    ):  # Filter for our symbol
                        self._schedule_coro(self._process_order_update(order_data))
        except Exception as e:
            self.logger.error(f"Error handling order update: {e}", exc_info=True)

    async def _process_order_update(self, order_data: dict):
        order_id, status = order_data["orderId"], order_data["orderStatus"]
        self.logger.info(
            f"Order {order_id} status update: {status} (OrderLink: {order_data.get('orderLinkId')})"
        )
        await self.db_manager.log_order_event(order_data)  # Log event regardless

        async with self.active_orders_lock:
            if order_id in self.active_orders:
                self.active_orders[order_id]["status"] = status
                if status == "Filled":
                    # Only process fill if the order was known and is now filled
                    await self._process_fill(order_data)
                    del self.active_orders[order_id]
                elif status in ["Cancelled", "Rejected", "Deactivated", "Expired"]:
                    # Remove from active orders if it's no longer open
                    del self.active_orders[order_id]
            elif (
                status == "Filled"
            ):  # Handle fills for orders not tracked locally (e.g., manual orders or bot restart)
                self.logger.warning(
                    f"Received fill for untracked order {order_id}. Processing fill."
                )
                await self._process_fill(order_data)
            else:
                self.logger.debug(
                    f"Received update for untracked order {order_id} with status {status}. Ignoring."
                )

    def _handle_position_update(self, message: dict):
        self.last_ws_message_time = time.time()
        try:
            if "data" in message:
                for pos_data in message["data"]:
                    if pos_data["symbol"] == self.config.symbol:
                        self._schedule_coro(self._process_position_update(pos_data))
        except Exception as e:
            self.logger.error(f"Error handling position update: {e}", exc_info=True)

    async def _process_position_update(self, pos_data: dict):
        async with self.balance_position_lock:
            new_pos_qty = Decimal(pos_data["size"]) * (
                Decimal("1") if pos_data["side"] == "Buy" else Decimal("-1")
            )
            if new_pos_qty != self.current_position_qty:
                self.current_position_qty = new_pos_qty
                self.logger.info(
                    f"POSITION UPDATE (WS): Position is now {self.current_position_qty} {self.config.base_currency}"
                )

            if (
                self.config.category in ["linear", "inverse"]
                and "unrealisedPnl" in pos_data
            ):
                self.unrealized_pnl_derivatives = Decimal(pos_data["unrealisedPnl"])
                self.logger.debug(
                    f"UNREALIZED PNL (WS): {self.unrealized_pnl_derivatives:+.4f} {self.config.quote_currency}"
                )

    # --- Strategy & Order Management ---
    async def _manage_orders(self):
        current_time = time.time()
        if (
            current_time - self.last_order_management_time
        ) < self.config.system.order_refresh_interval_sec:
            return
        self.last_order_management_time = current_time

        if await self._check_circuit_breaker():
            self.logger.warning("Circuit breaker tripped. Skipping order management.")
            return

        async with self.market_data_lock, self.balance_position_lock:
            if self.mid_price == Decimal("0") or not self.market_info:
                self.logger.warning(
                    "Mid-price or market info not available, skipping order management."
                )
                return
            mid_price, pos_qty = (
                self.mid_price,
                self.config.metrics.current_asset_holdings,
            )  # Use bot's tracked holdings for inventory

        spread_pct = self._calculate_dynamic_spread()
        skew_factor = self._calculate_inventory_skew(mid_price, pos_qty)
        skewed_mid_price = mid_price * (Decimal("1") + skew_factor)
        target_bid_price = skewed_mid_price * (Decimal("1") - spread_pct)
        target_ask_price = skewed_mid_price * (Decimal("1") + spread_pct)
        target_bid_price, target_ask_price = self._enforce_min_profit_spread(
            mid_price, target_bid_price, target_ask_price
        )

        await self._reconcile_and_place_orders(target_bid_price, target_ask_price)

    async def _check_circuit_breaker(self) -> bool:
        cb_config = self.config.strategy.circuit_breaker
        if not cb_config.enabled:
            return False

        current_time = time.time()
        # Filter price points within the check window
        recent_prices_raw = [
            (t, p)
            for t, p in self.circuit_breaker_price_points
            if (current_time - t) <= cb_config.check_window_sec
        ]

        if len(recent_prices_raw) < 2:
            return False  # Not enough data for a meaningful check

        # Ensure prices are sorted by timestamp
        recent_prices_raw.sort(key=lambda x: x[0])
        start_price = recent_prices_raw[0][1]
        end_price = recent_prices_raw[-1][1]

        if start_price == Decimal("0"):
            return False  # Avoid division by zero

        price_change_pct = abs(end_price - start_price) / start_price

        if price_change_pct > cb_config.pause_threshold_pct:
            self.logger.warning(
                f"CIRCUIT BREAKER TRIPPED: Price changed {price_change_pct:.2%} in {cb_config.check_window_sec}s. Pausing trading for {cb_config.pause_duration_sec}s."
            )
            self.is_paused = True
            self.pause_end_time = current_time + cb_config.pause_duration_sec
            self.circuit_breaker_cooldown_end_time = (
                current_time
                + cb_config.pause_duration_sec
                + cb_config.cool_down_after_trip_sec
            )
            await self._cancel_all_orders()
            return True
        return False

    def _calculate_dynamic_spread(self) -> Decimal:
        ds_config = self.config.strategy.dynamic_spread

        # Filter prices within the volatility window
        current_time = time.time()
        volatility_window_prices = [
            p
            for t, p in self.circuit_breaker_price_points
            if (current_time - t) <= ds_config.volatility_window_sec
        ]

        if not ds_config.enabled or len(volatility_window_prices) < 2:
            return self.config.strategy.base_spread_pct

        # Convert to float for numpy calculation
        float_prices = [float(p) for p in volatility_window_prices]

        # Avoid calculating std on constant prices
        if np.all(np.array(float_prices) == float_prices[0]):
            volatility = 0.0
        else:
            volatility = np.std(float_prices) / np.mean(float_prices)

        dynamic_adjustment = Decimal(str(volatility)) * ds_config.volatility_multiplier
        clamped_spread = max(
            ds_config.min_spread_pct,
            min(
                ds_config.max_spread_pct,
                self.config.strategy.base_spread_pct + dynamic_adjustment,
            ),
        )
        self.logger.debug(
            f"Volatility: {volatility:.6f}, Dynamic Spread: {clamped_spread:.4%}"
        )
        return clamped_spread

    def _calculate_inventory_skew(
        self, mid_price: Decimal, pos_qty: Decimal
    ) -> Decimal:
        inv_config = self.config.strategy.inventory
        if not inv_config.enabled or self.config.max_net_exposure_usd <= 0:
            return Decimal("0")

        # Calculate current inventory value in quote currency
        current_inventory_value = pos_qty * mid_price

        # Calculate inventory ratio relative to max net exposure
        # Clamp ratio to prevent extreme skew from very large positions
        # Use abs for ratio, then apply sign based on pos_qty
        max_exposure_for_ratio = (
            self.config.max_net_exposure_usd * inv_config.max_inventory_ratio
        )
        if max_exposure_for_ratio <= 0:
            return Decimal("0")  # Avoid division by zero

        inventory_ratio = current_inventory_value / max_exposure_for_ratio
        inventory_ratio = max(
            Decimal("-1.0"), min(Decimal("1.0"), inventory_ratio)
        )  # Clamp between -1 and 1

        # Skew factor: if long (positive ratio), skew prices down (negative factor) to encourage sells.
        # if short (negative ratio), skew prices up (positive factor) to encourage buys.
        skew_factor = -inventory_ratio * inv_config.skew_intensity

        if abs(skew_factor) > Decimal("1e-6"):  # Log only if skew is significant
            self.logger.debug(
                f"Inventory skew active. Position Value: {current_inventory_value:.2f} {self.config.quote_currency}, Ratio: {inventory_ratio:.3f}, Skew: {skew_factor:.6f}"
            )
        return skew_factor

    def _enforce_min_profit_spread(
        self, mid_price: Decimal, bid_p: Decimal, ask_p: Decimal
    ) -> tuple[Decimal, Decimal]:
        if not self.market_info:
            return bid_p, ask_p

        # Use taker fees for minimum profit calculation, assuming orders might be filled as takers
        # If orders are always post-only, maker fees would be more appropriate
        estimated_fee_per_side_pct = self.market_info.taker_fee_rate
        # min_profit_spread_after_fees_pct already includes a buffer, so just ensure gross spread covers fees
        min_gross_spread_pct = self.config.strategy.min_profit_spread_after_fees_pct + (
            estimated_fee_per_side_pct * Decimal("2")
        )
        min_spread_val = mid_price * min_gross_spread_pct

        # Ensure ask is always greater than bid
        if ask_p <= bid_p:
            mid = (bid_p + ask_p) / Decimal("2")
            # Adjust to ensure minimum spread around the mid
            ask_p = mid + (min_spread_val / Decimal("2")).quantize(
                self.market_info.price_precision
            )
            bid_p = mid - (min_spread_val / Decimal("2")).quantize(
                self.market_info.price_precision
            )
            self.logger.debug(
                f"Adjusting inverted/zero spread. New Bid: {bid_p}, Ask: {ask_p}"
            )

        # Ensure the spread is at least min_spread_val
        current_spread = ask_p - bid_p
        if current_spread < min_spread_val:
            self.logger.debug(
                f"Adjusting spread to enforce min profit. Original Spread: {current_spread:.6f}, Min Spread: {min_spread_val:.6f}"
            )
            half_spread_adjustment = (
                (min_spread_val - current_spread) / Decimal("2")
            ).quantize(self.market_info.price_precision)
            bid_p = (bid_p - half_spread_adjustment).quantize(
                self.market_info.price_precision
            )
            ask_p = (ask_p + half_spread_adjustment).quantize(
                self.market_info.price_precision
            )
        return bid_p, ask_p

    async def _reconcile_and_place_orders(
        self, target_bid: Decimal, target_ask: Decimal
    ):
        if not self.market_info:
            return
        target_bid = self.market_info.format_price(target_bid)
        target_ask = self.market_info.format_price(target_ask)

        cur_bid_order: dict | None = None
        cur_ask_order: dict | None = None
        to_cancel_orders = []

        async with self.active_orders_lock:
            # Identify existing orders and mark for cancellation if stale or duplicates
            for oid, o in list(self.active_orders.items()):
                if o.get("symbol") != self.config.symbol:
                    self.logger.warning(
                        f"Found untracked symbol order {oid} in active_orders. Removing."
                    )
                    to_cancel_orders.append((oid, o.get("orderLinkId")))
                    continue

                is_stale = False
                if o["side"] == "Buy":
                    if abs(o["price"] - target_bid) > (
                        o["price"] * self.config.strategy.order_stale_threshold_pct
                    ):
                        is_stale = True
                    if not cur_bid_order and not is_stale:
                        cur_bid_order = o
                    else:
                        to_cancel_orders.append((oid, o.get("orderLinkId")))
                else:  # Sell order
                    if abs(o["price"] - target_ask) > (
                        o["price"] * self.config.strategy.order_stale_threshold_pct
                    ):
                        is_stale = True
                    if not cur_ask_order and not is_stale:
                        cur_ask_order = o
                    else:
                        to_cancel_orders.append((oid, o.get("orderLinkId")))

        # Execute cancellations
        for oid, olid in to_cancel_orders:
            order_info = self.active_orders.get(oid, {})
            self.logger.info(
                f"Cancelling stale/duplicate order {oid} (Side: {order_info.get('side')}, Price: {order_info.get('price')}). Target Bid: {target_bid}, Target Ask: {target_ask}"
            )
            await self._cancel_order(oid, olid)

        # Place new orders if none exist or if existing ones were cancelled
        if not cur_bid_order:
            buy_qty = await self._calculate_order_size("Buy", target_bid)
            if buy_qty > 0:
                self.logger.info(
                    f"No active bid, placing new bid order: Price={target_bid}, Qty={buy_qty}"
                )
                await self._place_limit_order("Buy", target_bid, buy_qty)
            else:
                self.logger.debug(
                    "Calculated buy quantity is zero or too small, skipping bid order placement."
                )

        if not cur_ask_order:
            sell_qty = await self._calculate_order_size("Sell", target_ask)
            if sell_qty > 0:
                self.logger.info(
                    f"No active ask, placing new ask order: Price={target_ask}, Qty={sell_qty}"
                )
                await self._place_limit_order("Sell", target_ask, sell_qty)
            else:
                self.logger.debug(
                    "Calculated sell quantity is zero or too small, skipping ask order placement."
                )

    async def _log_status_summary(self):
        async with self.balance_position_lock, self.active_orders_lock:
            metrics = self.config.metrics
            unrealized_pnl = metrics.calculate_unrealized_pnl(self.mid_price)
            total_current_pnl = (
                metrics.total_pnl + unrealized_pnl
            )  # Realized + Unrealized PnL

            # For derivatives, use exchange's unrealized PNL if available and bot's calculated PNL for holdings
            if self.config.category in ["linear", "inverse"]:
                display_unrealized_pnl = (
                    self.unrealized_pnl_derivatives
                )  # From exchange for derivatives
                # For derivatives, total PnL is realized_pnl + exchange_unrealized_pnl
                total_current_pnl = metrics.total_pnl + display_unrealized_pnl
            else:  # Spot
                display_unrealized_pnl = unrealized_pnl

            pos_qty = metrics.current_asset_holdings  # Use bot's tracked holdings

            exposure_usd = Decimal("0")
            if self.mid_price > 0:
                exposure_usd = pos_qty * self.mid_price

            pnl_summary = f"Realized PNL: {metrics.realized_pnl:+.4f} {self.config.quote_currency}"
            pnl_summary += f" | Unrealized PNL: {display_unrealized_pnl:+.4f} {self.config.quote_currency}"

            active_buys = sum(
                1 for o in self.active_orders.values() if o["side"] == "Buy"
            )
            active_sells = sum(
                1 for o in self.active_orders.values() if o["side"] == "Sell"
            )

        self.logger.info(
            f"STATUS | Total PNL: {total_current_pnl:+.4f} | {pnl_summary} | Win Rate: {metrics.win_rate:.2f}% | Position: {pos_qty} {self.config.base_currency} (Exposure: {exposure_usd:+.2f} {self.config.quote_currency}) | Orders: {active_buys} Buy / {active_sells} Sell"
        )
        await self.db_manager.log_bot_metrics(metrics, display_unrealized_pnl)

    async def _fetch_market_info(self) -> bool:
        if self.config.trading_mode == "SIMULATION":
            # Mock market info for simulation
            self.market_info = MarketInfo(
                symbol=self.config.symbol,
                price_precision=Decimal("0.0001"),  # Example precision
                quantity_precision=Decimal("0.001"),  # Example precision
                min_order_qty=Decimal("0.01"),
                min_notional_value=self.config.min_order_value_usd,
                maker_fee_rate=Decimal("0.0002"),  # Example maker fee
                taker_fee_rate=Decimal("0.0005"),  # Example taker fee
            )
            self.logger.info(
                f"SIMULATION mode: Mock market info loaded for {self.config.symbol}: {self.market_info}"
            )
            return True

        info = await self.trading_client.get_instruments_info()
        if not info:
            self.logger.error("Failed to retrieve instrument info from API.")
            return False

        try:
            self.market_info = MarketInfo(
                symbol=self.config.symbol,
                price_precision=Decimal(info["priceFilter"]["tickSize"]),
                quantity_precision=Decimal(info["lotSizeFilter"]["qtyStep"]),
                min_order_qty=Decimal(info["lotSizeFilter"]["minOrderQty"]),
                min_notional_value=Decimal(
                    info["lotSizeFilter"].get("minNotionalValue", "0")
                ),
                maker_fee_rate=Decimal(info["makerFeeRate"]),
                taker_fee_rate=Decimal(info["takerFeeRate"]),
            )
            if self.market_info.min_notional_value == Decimal("0"):
                self.logger.warning(
                    f"minNotionalValue not found or is 0 for {self.config.symbol}. Using config.min_order_value_usd as fallback."
                )
                self.market_info.min_notional_value = self.config.min_order_value_usd

            self.logger.info(
                f"Market info fetched for {self.config.symbol}: {self.market_info}"
            )
            return True
        except KeyError as e:
            self.logger.critical(
                f"Missing expected key in instrument info: {e}. Full info: {info}"
            )
            return False
        except Exception as e:
            self.logger.critical(f"Error parsing market info: {e}. Full info: {info}")
            return False

    async def _update_balance_and_position(self) -> bool:
        async with self.balance_position_lock:
            if (
                self.config.trading_mode == "DRY_RUN"
                or self.config.trading_mode == "SIMULATION"
            ):
                # Initialize DRY_RUN/SIMULATION balance if not set
                if self.current_balance == Decimal("0"):
                    self.current_balance = self.config.initial_dry_run_capital
                    self.available_balance = self.current_balance
                    self.logger.info(
                        f"{self.config.trading_mode}: Initialized virtual balance: {self.current_balance} {self.config.quote_currency}"
                    )
                return True

            balance_data = await self.trading_client.get_wallet_balance()
            if not balance_data:
                self.logger.error("Failed to fetch wallet balance.")
                return False

            found_quote_balance = False
            for coin in balance_data.get("coin", []):
                if coin["coin"] == self.config.quote_currency:
                    self.current_balance = Decimal(coin["walletBalance"])
                    self.available_balance = Decimal(
                        coin.get("availableToWithdraw", coin["walletBalance"])
                    )
                    self.logger.debug(
                        f"Balance: {self.current_balance} {self.config.quote_currency}, Available: {self.available_balance}"
                    )
                    await self.db_manager.log_balance_update(
                        self.config.quote_currency,
                        self.current_balance,
                        self.available_balance,
                    )
                    found_quote_balance = True
                    break

            if not found_quote_balance:
                self.logger.warning(
                    f"Could not find balance for {self.config.quote_currency}. This might affect order sizing."
                )

            if self.config.category in ["linear", "inverse"]:
                position_data = await self.trading_client.get_position_info()
                if position_data and position_data.get("size"):
                    self.current_position_qty = Decimal(position_data["size"]) * (
                        Decimal("1")
                        if position_data["side"] == "Buy"
                        else Decimal("-1")
                    )
                    self.unrealized_pnl_derivatives = Decimal(
                        position_data.get("unrealisedPnl", "0")
                    )
                else:
                    self.current_position_qty = Decimal("0")
                    self.unrealized_pnl_derivatives = Decimal("0")
            else:  # Spot trading doesn't have 'positions' in the same derivatives sense, bot's tracked holdings are the source of truth
                # For spot, current_position_qty is essentially metrics.current_asset_holdings
                self.current_position_qty = self.config.metrics.current_asset_holdings
                self.unrealized_pnl_derivatives = Decimal(
                    "0"
                )  # Not applicable for spot

            self.logger.info(
                f"Updated Balance: {self.current_balance} {self.config.quote_currency}, Position: {self.current_position_qty} {self.config.base_currency}, UPNL (Deriv): {self.unrealized_pnl_derivatives:+.4f}"
            )
            return True

    async def _process_fill(self, o: dict):
        side = o.get("side", "Unknown")
        exec_qty = Decimal(o.get("execQty", "0"))
        exec_price = Decimal(o.get("execPrice", "0"))
        exec_fee = Decimal(o.get("execFee", "0"))
        pnl_from_exchange = Decimal(o.get("pnl", "0"))  # PnL is usually for derivatives

        metrics = self.config.metrics
        realized_pnl_impact = Decimal("0")

        # Update bot's internal PnL tracking
        if side == "Buy":
            metrics.update_pnl_on_buy(exec_qty, exec_price)
            self.logger.info(
                f"Order FILLED: BUY {exec_qty} @ {exec_price}, Fee: {exec_fee}. Holdings: {metrics.current_asset_holdings}, Avg Entry: {metrics.average_entry_price}"
            )
        elif side == "Sell":
            # Calculate PnL for this specific sell against the bot's average entry price
            # This is the 'realized_pnl_impact' for the DB log
            profit_loss_on_sale = (exec_price - metrics.average_entry_price) * exec_qty
            metrics.update_pnl_on_sell(exec_qty, exec_price)
            realized_pnl_impact = profit_loss_on_sale
            self.logger.info(
                f"Order FILLED: SELL {exec_qty} @ {exec_price}, Fee: {exec_fee}. Realized PnL from sale: {profit_loss_on_sale:+.4f}. Holdings: {metrics.current_asset_holdings}, Avg Entry: {metrics.average_entry_price}"
            )
        else:
            self.logger.warning(
                f"Unknown side '{side}' for fill. Cannot update PnL metrics."
            )

        # Update general trade metrics
        metrics.total_trades += 1
        metrics.total_fees += exec_fee
        # For general metrics, use the PnL calculated by the bot, which accounts for spot vs derivatives.
        # If it's a sell, the realized_pnl_impact is the PnL. If it's a buy, PnL is 0 for this metric.
        if realized_pnl_impact > 0:
            metrics.gross_profit += realized_pnl_impact
            metrics.wins += 1
        elif realized_pnl_impact < 0:
            metrics.gross_loss += abs(realized_pnl_impact)
            metrics.losses += 1
        metrics.update_win_rate()

        await self.db_manager.log_trade_fill(o, realized_pnl_impact)
        # Explicitly update balance and position immediately after a fill
        await self._update_balance_and_position()

    async def _cancel_order(self, order_id: str, order_link_id: str | None = None):
        self.logger.info(
            f"Attempting to cancel order {order_id} (OrderLink: {order_link_id})..."
        )
        if (
            self.config.trading_mode == "DRY_RUN"
            or self.config.trading_mode == "SIMULATION"
        ):
            self.logger.info(
                f"{self.config.trading_mode}: Would cancel order {order_id}."
            )
            async with self.active_orders_lock:
                if order_id in self.active_orders:
                    del self.active_orders[order_id]
            return

        try:
            if await self.trading_client.cancel_order(order_id, order_link_id):
                self.logger.info(f"Order {order_id} cancelled successfully.")
                async with self.active_orders_lock:
                    if order_id in self.active_orders:
                        del self.active_orders[order_id]
            else:
                self.logger.error(
                    f"Failed to cancel order {order_id} via API after retries."
                )
        except Exception as e:
            self.logger.error(f"Error during cancellation of order {order_id}: {e}")

    async def _cancel_all_orders(self):
        self.logger.info("Canceling all open orders...")
        if (
            self.config.trading_mode == "DRY_RUN"
            or self.config.trading_mode == "SIMULATION"
        ):
            self.logger.info(
                f"{self.config.trading_mode}: Would cancel all open orders."
            )
        else:
            try:
                if await self.trading_client.cancel_all_orders():
                    self.logger.info("All orders cancelled successfully.")
                else:
                    self.logger.error(
                        "Failed to cancel all orders via API after retries."
                    )
            except Exception as e:
                self.logger.error(f"Error during cancellation of all orders: {e}")

        async with self.active_orders_lock:
            self.active_orders.clear()

    async def _calculate_order_size(self, side: str, price: Decimal) -> Decimal:
        async with self.balance_position_lock:
            # Use bot's current_balance for available capital for order sizing
            capital = (
                self.available_balance
                if self.config.category == "spot"
                else self.current_balance
            )
            metrics_pos_qty = (
                self.config.metrics.current_asset_holdings
            )  # Bot's view of holdings

        if capital <= 0 or self.mid_price <= 0 or not self.market_info:
            self.logger.debug(
                "Insufficient capital, zero mid_price, or no market info. Order size 0."
            )
            return Decimal("0")

        # Effective capital considering leverage for linear/inverse contracts
        eff_capital = (
            capital * self.config.leverage
            if self.config.category in ["linear", "inverse"]
            else capital
        )

        # Base order value derived from a percentage of effective capital
        order_val = eff_capital * self.config.strategy.base_order_size_pct_of_balance

        # Ensure order_val does not exceed max_order_size_pct of effective capital
        order_val = min(order_val, eff_capital * self.config.max_order_size_pct)

        # Consider max net exposure for linear/inverse contracts AND for spot if inventory strategy is enabled
        if (
            self.config.max_net_exposure_usd > 0
            and self.config.strategy.inventory.enabled
        ):
            current_net_exposure_usd = abs(metrics_pos_qty * self.mid_price)
            # Remaining exposure for a new order
            remaining_exposure_usd = (
                self.config.max_net_exposure_usd - current_net_exposure_usd
            )

            if remaining_exposure_usd <= self.config.min_order_value_usd:
                self.logger.debug(
                    f"Max net exposure ({self.config.max_net_exposure_usd} USD) reached. Current: {current_net_exposure_usd:.2f} USD. Order size 0."
                )
                return Decimal("0")

            # Only limit by remaining exposure if adding to the current direction
            if (side == "Buy" and metrics_pos_qty >= 0) or (
                side == "Sell" and metrics_pos_qty <= 0
            ):
                order_val = min(order_val, remaining_exposure_usd)
            # If trading against current position (reducing exposure), no cap by remaining_exposure_usd needed

        if order_val <= 0:
            self.logger.debug(
                "Calculated order value is zero or negative. Order size 0."
            )
            return Decimal("0")

        # Calculate quantity and format it
        qty = self.market_info.format_quantity(order_val / price)

        # Check against minimum order requirements
        if qty < self.market_info.min_order_qty:
            self.logger.debug(
                f"Calculated quantity {qty} is less than min_order_qty {self.market_info.min_order_qty}. Order size 0."
            )
            return Decimal("0")

        # Final check against minimum notional value
        order_notional_value = qty * price
        min_notional = max(
            self.market_info.min_notional_value, self.config.min_order_value_usd
        )
        if order_notional_value < min_notional:
            self.logger.debug(
                f"Calculated notional value {order_notional_value:.2f} is less than min_notional_value {min_notional:.2f}. Order size 0."
            )
            return Decimal("0")

        self.logger.debug(
            f"Calculated {side} order size: {qty} {self.config.base_currency} (Notional: {order_notional_value:.2f} {self.config.quote_currency})"
        )
        return qty

    async def _place_limit_order(self, side: str, price: Decimal, quantity: Decimal):
        if not self.market_info:
            self.logger.error("Cannot place order, market info not available.")
            return

        qty_f, price_f = (
            self.market_info.format_quantity(quantity),
            self.market_info.format_price(price),
        )
        if qty_f <= 0 or price_f <= 0:
            self.logger.warning(
                f"Attempted to place order with zero or negative quantity/price: Qty={qty_f}, Price={price_f}. Skipping."
            )
            return

        order_notional_value = qty_f * price_f
        min_notional = max(
            self.market_info.min_notional_value, self.config.min_order_value_usd
        )
        if order_notional_value < min_notional:
            self.logger.warning(
                f"Calculated order notional value {order_notional_value:.2f} is below minimum {min_notional:.2f}. Skipping order placement."
            )
            return

        time_in_force = (
            "PostOnly" if self.config.post_only else self.config.time_in_force
        )
        order_link_id = f"mm_{side}_{int(time.time() * 1000)}"
        params = {
            "category": self.config.category,
            "symbol": self.config.symbol,
            "side": side,
            "orderType": self.config.order_type,
            "qty": str(qty_f),
            "price": str(price_f),
            "timeInForce": time_in_force,
            "orderLinkId": order_link_id,
        }

        if (
            self.config.trading_mode == "DRY_RUN"
            or self.config.trading_mode == "SIMULATION"
        ):
            oid = f"DRY_{side}_{int(time.time() * 1000)}"
            self.logger.info(
                f"{self.config.trading_mode}: Would place {side} order: ID={oid}, Qty={qty_f}, Price={price_f}"
            )
            async with self.active_orders_lock:
                self.active_orders[oid] = {
                    "side": side,
                    "price": price_f,
                    "qty": qty_f,
                    "status": "New",
                    "orderLinkId": order_link_id,
                    "symbol": self.config.symbol,
                }
            await self.db_manager.log_order_event(
                {**params, "orderId": oid, "orderStatus": "New"},
                f"{self.config.trading_mode} Order placed",
            )
            return

        result = await self.trading_client.place_order(params)
        if result and result.get("orderId"):
            oid = result["orderId"]
            self.logger.info(
                f"Placed {side} order: ID={oid}, Price={price_f}, Qty={qty_f}"
            )
            async with self.active_orders_lock:
                self.active_orders[oid] = {
                    "side": side,
                    "price": price_f,
                    "qty": qty_f,
                    "status": "New",
                    "orderLinkId": order_link_id,
                    "symbol": self.config.symbol,
                }
            await self.db_manager.log_order_event(
                {**params, "orderId": oid, "orderStatus": "New"}, "Order placed"
            )
        else:
            self.logger.error(
                f"Failed to place {side} order after retries. Params: {params}"
            )

    async def _reconcile_orders_on_startup(self):
        if (
            self.config.trading_mode == "DRY_RUN"
            or self.config.trading_mode == "SIMULATION"
        ):
            self.logger.info(
                f"{self.config.trading_mode} mode: Skipping order reconciliation."
            )
            return

        self.logger.info("Reconciling active orders with exchange...")
        try:
            exchange_orders = {
                o["orderId"]: o for o in await self.trading_client.get_open_orders()
            }
        except Exception as e:
            self.logger.error(
                f"Failed to fetch open orders from exchange during reconciliation: {e}. Proceeding with local state only."
            )
            exchange_orders = {}

        async with self.active_orders_lock:
            local_ids = set(self.active_orders.keys())
            exchange_ids = set(exchange_orders.keys())

            # Orders in local state but not on exchange -> remove locally
            for oid in local_ids - exchange_ids:
                self.logger.warning(
                    f"Local order {oid} not found on exchange. Removing from local state."
                )
                del self.active_orders[oid]

            # Orders on exchange but not in local state -> add locally
            for oid in exchange_ids - local_ids:
                o = exchange_orders[oid]
                self.logger.warning(
                    f"Exchange order {oid} ({o['side']} {o['qty']} @ {o['price']}) not in local state. Adding."
                )
                self.active_orders[oid] = {
                    "side": o["side"],
                    "price": Decimal(o["price"]),
                    "qty": Decimal(o["qty"]),
                    "status": o["orderStatus"],
                    "orderLinkId": o.get("orderLinkId"),
                    "symbol": o.get("symbol"),
                }

            # Update status for orders present in both
            for oid in local_ids.intersection(exchange_ids):
                local_order = self.active_orders[oid]
                exchange_order = exchange_orders[oid]
                if local_order["status"] != exchange_order["orderStatus"]:
                    self.logger.info(
                        f"Order {oid} status mismatch. Updating from {local_order['status']} to {exchange_order['orderStatus']}."
                    )
                    local_order["status"] = exchange_order["orderStatus"]

        self.logger.info(
            f"Order reconciliation complete. {len(self.active_orders)} active orders after reconciliation."
        )


# =====================================================================
# MAIN ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    try:
        config = Config()
        bot = BybitMarketMaker(config)
        asyncio.run(bot.run())
    except (KeyboardInterrupt, SystemExit):
        print("\nBot stopped by user.")
    except (
        ValueError,
        APIAuthError,
        MarketInfoError,
        InitialBalanceError,
        WebSocketConnectionError,
        ConfigurationError,
    ) as e:
        print(f"\nCritical Initialization Error: {e}")
        logging.getLogger("MarketMakerBot").critical(
            f"Critical Initialization Error: {e}", exc_info=True
        )
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected critical error occurred during bot runtime: {e}")
        logging.getLogger("MarketMakerBot").critical(
            f"Unhandled exception in main: {e}", exc_info=True
        )
        sys.exit(1)
