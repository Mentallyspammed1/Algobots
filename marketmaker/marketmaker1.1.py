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
import numpy as np  # Used for standard deviation calculation
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
# Set Decimal precision for financial calculations to avoid floating-point inaccuracies.
getcontext().prec = 28
# Load environment variables (e.g., API keys) from a .env file.
load_dotenv()


# --- Custom Exceptions ---
class APIAuthError(Exception):
    """Raised for API authentication or signature errors."""


class WebSocketConnectionError(Exception):
    """Raised when WebSocket connection fails or drops."""


class MarketInfoError(Exception):
    """Raised when market instrument information cannot be retrieved or parsed."""


class InitialBalanceError(Exception):
    """Raised when initial balance or position data cannot be fetched."""


class ConfigurationError(Exception):
    """Raised for invalid or missing configuration settings."""


class OrderPlacementError(Exception):
    """Raised when an order placement or modification fails."""


class BybitAPIError(Exception):
    """Generic exception for Bybit API errors, includes Bybit's error code and message."""

    def __init__(self, message: str, ret_code: int = -1, ret_msg: str = "Unknown"):
        super().__init__(message)
        self.ret_code = ret_code
        self.ret_msg = ret_msg


class BybitRateLimitError(BybitAPIError):
    """Raised when a Bybit API rate limit is exceeded."""


class BybitInsufficientBalanceError(BybitAPIError):
    """Raised when an API operation fails due to insufficient balance."""


# =====================================================================
# CONFIGURATION & DATA CLASSES
# =====================================================================
@dataclass
class TradeMetrics:
    """
    Tracks various trading metrics including PnL, trade counts, and asset holdings.
    PnL is primarily based on the bot's average entry price for its current holdings.
    """

    total_trades: int = 0
    gross_profit: Decimal = Decimal("0")
    gross_loss: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    realized_pnl: Decimal = Decimal("0")
    current_asset_holdings: Decimal = Decimal("0")
    average_entry_price: Decimal = Decimal("0")
    last_pnl_update_timestamp: datetime | None = None

    @property
    def net_realized_pnl(self) -> Decimal:
        """Calculates net realized PnL after deducting total fees."""
        return self.realized_pnl - self.total_fees

    def update_win_rate(self):
        """Recalculates the win rate based on total trades, wins, and losses."""
        self.win_rate = (
            (self.wins / self.total_trades * 100.0) if self.total_trades > 0 else 0.0
        )

    def update_pnl_on_buy(self, quantity: Decimal, price: Decimal):
        """
        Updates the average entry price and current asset holdings upon a buy.
        This affects the cost basis but not directly the realized PnL.
        """
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
        """
        Updates realized PnL and asset holdings upon a sell.
        Profit/loss for the sold portion is calculated against the average entry price.
        """
        if self.current_asset_holdings < quantity:
            raise ValueError(
                f"Attempted to sell {quantity} but only {self.current_asset_holdings} held."
            )

        profit_loss_on_sale = (price - self.average_entry_price) * quantity
        self.realized_pnl += profit_loss_on_sale

        self.current_asset_holdings -= quantity
        if self.current_asset_holdings == Decimal("0"):
            self.average_entry_price = Decimal(
                "0"
            )  # Reset average entry if all assets sold
        self.last_pnl_update_timestamp = datetime.now(timezone.utc)

    def calculate_unrealized_pnl(self, current_price: Decimal) -> Decimal:
        """
        Calculates unrealized PnL based on the current market price and average entry price.
        Returns 0 if there are no holdings or if prices are invalid.
        """
        if self.current_asset_holdings > 0 and self.average_entry_price > 0:
            return (
                current_price - self.average_entry_price
            ) * self.current_asset_holdings
        return Decimal("0")


@dataclass(frozen=True)
class InventoryStrategyConfig:
    """Configuration for the inventory management strategy."""

    enabled: bool = True
    skew_intensity: Decimal = Decimal("1.9666311123046691")
    max_inventory_ratio: Decimal = Decimal("0.25")


@dataclass(frozen=True)
class DynamicSpreadConfig:
    """Configuration for dynamic spread adjustment based on volatility."""

    enabled: bool = True
    volatility_window_sec: int = 60
    volatility_multiplier: Decimal = Decimal("4.001625807622517")
    min_spread_pct: Decimal = Decimal("0.0005")
    max_spread_pct: Decimal = Decimal("0.01")
    price_change_smoothing_factor: Decimal = Decimal("0.8")


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Configuration for the circuit breaker, pausing trading during high volatility."""

    enabled: bool = True
    pause_threshold_pct: Decimal = Decimal("0.02")  # Percentage price change to trigger
    check_window_sec: int = 10  # Time window for price change check
    pause_duration_sec: int = 60  # How long to pause trading
    cool_down_after_trip_sec: int = 300  # Additional cooldown after pause ends


@dataclass(frozen=True)
class StrategyConfig:
    """Overall trading strategy configuration."""

    base_spread_pct: Decimal = Decimal("0.0027797575729041285")
    base_order_size_pct_of_balance: Decimal = Decimal("0.006")
    order_stale_threshold_pct: Decimal = Decimal(
        "0.0005"
    )  # % change to consider an order stale
    min_profit_spread_after_fees_pct: Decimal = Decimal("0.00035300631182244954")
    max_outstanding_orders: int = 3
    inventory: InventoryStrategyConfig = field(default_factory=InventoryStrategyConfig)
    dynamic_spread: DynamicSpreadConfig = field(default_factory=DynamicSpreadConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)


@dataclass(frozen=True)
class SystemConfig:
    """System-level configuration for bot operation."""

    loop_interval_sec: float = 0.5  # Delay between main loop ticks
    order_refresh_interval_sec: float = 5.0  # How often to re-evaluate and place orders
    ws_heartbeat_sec: int = 30  # Max time without WS message before health check
    cancellation_rate_limit_sec: float = 0.2  # Min delay between API cancel calls
    status_report_interval_sec: int = 30  # How often to log status summary
    ws_reconnect_attempts: int = 5
    ws_reconnect_initial_delay_sec: int = 5
    ws_reconnect_max_delay_sec: int = 60
    api_retry_attempts: int = 5
    api_retry_initial_delay_sec: float = 0.5
    api_retry_max_delay_sec: float = 10.0
    health_check_interval_sec: int = (
        10  # How often to re-fetch balance/position via HTTP
    )


@dataclass(frozen=True)
class FilesConfig:
    """File-related configuration for logging and persistence."""

    log_level: str = "INFO"
    log_file: str = "market_maker.log"
    state_file: str = "market_maker_state.pkl"
    db_file: str = "market_maker.db"


@dataclass(frozen=True)
class Config:
    """Main configuration class for the market maker bot."""

    api_key: str = field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    testnet: bool = os.getenv("BYBIT_TESTNET", "true").lower() == "true"
    trading_mode: str = "DRY_RUN"  # Options: DRY_RUN, SIMULATION, TESTNET, LIVE
    symbol: str = "XLMUSDT"
    category: str = "linear"  # Options: linear, inverse, spot
    leverage: Decimal = Decimal("1")
    min_order_value_usd: Decimal = Decimal("10")  # Minimum notional value for an order
    max_order_size_pct: Decimal = Decimal(
        "0.1"
    )  # Max percentage of effective capital for a single order
    max_net_exposure_usd: Decimal = Decimal(
        "500"
    )  # Max total USD value of open position
    order_type: str = "Limit"
    time_in_force: str = "GTC"  # Good-Til-Cancelled
    post_only: bool = True  # Ensures order is not immediately filled as taker
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    system: SystemConfig = field(default_factory=SystemConfig)
    files: FilesConfig = field(default_factory=FilesConfig)
    initial_dry_run_capital: Decimal = Decimal(
        "10000"
    )  # Virtual capital for DRY_RUN/SIMULATION

    base_currency: str = field(init=False)
    quote_currency: str = field(init=False)

    def __post_init__(self):
        """Initializes derived attributes and performs initial configuration validation."""

        # Helper to set frozen dataclass fields
        def _set_attr(name, value):
            object.__setattr__(self, name, value)

        # Parse base and quote currencies from symbol
        if self.symbol.endswith("USDT"):
            _set_attr("base_currency", self.symbol[:-4])
            _set_attr("quote_currency", "USDT")
        elif self.symbol.endswith("USD"):
            _set_attr("base_currency", self.symbol[:-3])
            _set_attr("quote_currency", "USD")
        elif len(self.symbol) == 6:  # e.g., BTCUSD
            _set_attr("base_currency", self.symbol[:3])
            _set_attr("quote_currency", self.symbol[3:])
        else:
            raise ConfigurationError(
                f"Cannot parse base/quote currency from symbol: {self.symbol}. Use a standard format (e.g., BTCUSDT)."
            )

        # Adjust testnet setting based on trading_mode
        if self.trading_mode == "TESTNET":
            _set_attr("testnet", True)
        elif self.trading_mode == "LIVE":
            _set_attr("testnet", False)

        # Validate API keys for live trading modes
        if self.trading_mode not in ["DRY_RUN", "SIMULATION"] and (
            not self.api_key or not self.api_secret
        ):
            raise ConfigurationError(
                "API_KEY and API_SECRET must be set in .env for TESTNET or LIVE trading_mode."
            )

        # Validate leverage for different categories
        if self.category in ["linear", "inverse"]:
            if self.leverage <= 0:
                raise ConfigurationError(
                    "Leverage must be a positive decimal for linear/inverse categories."
                )
        elif self.category == "spot":
            if self.leverage != Decimal("1"):
                _set_attr("leverage", Decimal("1"))
                logging.getLogger("MarketMakerBot").warning(
                    "Leverage is not applicable for spot trading. Setting leverage to 1."
                )

        # Validate strategy and order parameters
        if self.strategy.inventory.enabled and self.max_net_exposure_usd <= 0:
            raise ConfigurationError(
                "max_net_exposure_usd must be positive when inventory strategy is enabled."
            )
        if not (Decimal("0") < self.max_order_size_pct <= Decimal("1")):
            raise ConfigurationError(
                "max_order_size_pct must be between 0 and 1 (exclusive)."
            )
        if self.min_order_value_usd <= Decimal("0"):
            raise ConfigurationError("min_order_value_usd must be positive.")
        if self.max_net_exposure_usd < Decimal("0"):
            raise ConfigurationError("max_net_exposure_usd cannot be negative.")
        if self.strategy.base_spread_pct <= Decimal("0"):
            raise ConfigurationError("base_spread_pct must be positive.")
        if self.category not in ["linear", "inverse", "spot"]:
            raise ConfigurationError(f"Unsupported category: {self.category}")
        if self.strategy.max_outstanding_orders < 0:
            raise ConfigurationError("max_outstanding_orders cannot be negative.")

        # Validate dynamic spread configuration
        if self.strategy.dynamic_spread.enabled:
            if not (
                Decimal("0")
                <= self.strategy.dynamic_spread.min_spread_pct
                <= self.strategy.dynamic_spread.max_spread_pct
            ):
                raise ConfigurationError(
                    "Dynamic spread min/max percentages are invalid."
                )
            if not (
                Decimal("0")
                < self.strategy.dynamic_spread.price_change_smoothing_factor
                < Decimal("1")
            ):
                raise ConfigurationError(
                    "Price change smoothing factor must be between 0 and 1 (exclusive)."
                )


@dataclass(frozen=True)
class MarketInfo:
    """Stores essential market information for a given trading symbol."""

    symbol: str
    price_precision: Decimal  # Smallest allowed price increment
    quantity_precision: Decimal  # Smallest allowed quantity increment
    min_order_qty: Decimal  # Minimum quantity for an order
    min_notional_value: Decimal  # Minimum total value (price * quantity) for an order
    maker_fee_rate: Decimal = Decimal("0")
    taker_fee_rate: Decimal = Decimal("0")

    def format_price(self, p: Decimal) -> Decimal:
        """Quantizes a price to the market's specified price precision, rounding down."""
        return p.quantize(self.price_precision, rounding=ROUND_DOWN)

    def format_quantity(self, q: Decimal) -> Decimal:
        """Quantizes a quantity to the market's specified quantity precision, rounding down."""
        return q.quantize(self.quantity_precision, rounding=ROUND_DOWN)


@dataclass
class TradingState:
    """Holds all mutable runtime state for the market maker bot."""

    mid_price: Decimal = Decimal("0")
    smoothed_mid_price: Decimal = Decimal("0")  # Smoothed mid-price for stability
    current_balance: Decimal = Decimal("0")  # Total wallet balance of quote currency
    available_balance: Decimal = Decimal("0")  # Available balance for trading
    current_position_qty: Decimal = Decimal(
        "0"
    )  # Current position in base currency (positive for long, negative for short)
    unrealized_pnl_derivatives: Decimal = Decimal(
        "0"
    )  # Unrealized PnL from derivatives, reported by exchange

    active_orders: dict[str, dict] = field(default_factory=dict)  # Tracked open orders
    last_order_management_time: float = 0.0
    last_ws_message_time: float = field(default_factory=time.time)
    last_status_report_time: float = 0.0
    last_health_check_time: float = 0.0

    # Deques for price history, used for volatility and circuit breaker
    mid_price_history: deque[float] = field(default_factory=deque)
    circuit_breaker_price_points: deque[tuple[float, Decimal]] = field(
        default_factory=deque
    )

    is_paused: bool = False  # True if circuit breaker is active
    pause_end_time: float = 0.0  # Timestamp when pause ends
    circuit_breaker_cooldown_end_time: float = (
        0.0  # Timestamp when cooldown after pause ends
    )
    ws_reconnect_attempts_left: int = 0  # Remaining reconnection attempts

    metrics: TradeMetrics = field(
        default_factory=TradeMetrics
    )  # Trading performance metrics


# =====================================================================
# LOGGING, STATE, and DB MANAGEMENT
# =====================================================================
def setup_logger(config: FilesConfig) -> logging.Logger:
    """Configures and returns the application-wide logger."""
    logger = logging.getLogger("MarketMakerBot")
    logger.setLevel(getattr(logging, config.log_level.upper()))
    if not logger.handlers:  # Prevent adding handlers multiple times
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
    """Manages saving and loading of the bot's internal state to a pickle file."""

    def __init__(self, file_path: str, logger: logging.Logger):
        self.file_path = file_path
        self.logger = logger

    async def save_state(self, state: dict):
        """Saves the bot's current state to a pickle file."""
        try:
            async with aiofiles.open(self.file_path, "wb") as f:
                await f.write(pickle.dumps(state))
            self.logger.info("Bot state saved successfully.")
        except Exception as e:
            self.logger.error(f"Error saving state: {e}")

    async def load_state(self) -> dict | None:
        """Loads the bot's state from a pickle file. Returns None if file not found or error occurs."""
        if not os.path.exists(self.file_path):
            return None
        try:
            async with aiofiles.open(self.file_path, "rb") as f:
                return pickle.loads(await f.read())
        except Exception as e:
            self.logger.error(
                f"Error loading state from {self.file_path}: {e}. Starting fresh.",
                exc_info=True,
            )
            return None


class DBManager:
    """Manages database connection and logging of trading events and metrics."""

    def __init__(self, db_file: str, logger: logging.Logger):
        self.db_file = db_file
        self.conn: aiosqlite.Connection | None = None
        self.logger = logger

    async def connect(self):
        """Establishes a connection to the SQLite database."""
        try:
            self.conn = await aiosqlite.connect(self.db_file)
            self.conn.row_factory = aiosqlite.Row  # Access columns by name
            self.logger.info(f"Connected to database: {self.db_file}")
        except Exception as e:
            self.logger.critical(f"Failed to connect to database: {e}", exc_info=True)
            sys.exit(1)

    async def close(self):
        """Closes the database connection."""
        if self.conn:
            await self.conn.close()
            self.logger.info("Database connection closed.")

    async def create_tables(self):
        """
        Creates necessary tables if they do not already exist and performs schema migrations.
        """
        if not self.conn:
            await self.connect()  # Ensure connection is open

        # Define tables
        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS order_events (id INTEGER PRIMARY KEY, timestamp TEXT, order_id TEXT, order_link_id TEXT, symbol TEXT, side TEXT, order_type TEXT, price TEXT, qty TEXT, status TEXT, message TEXT);
            CREATE TABLE IF NOT EXISTS trade_fills (id INTEGER PRIMARY KEY, timestamp TEXT, order_id TEXT, trade_id TEXT, symbol TEXT, side TEXT, exec_price TEXT, exec_qty TEXT, fee TEXT, fee_currency TEXT, pnl TEXT, realized_pnl_impact TEXT);
            CREATE TABLE IF NOT EXISTS balance_updates (id INTEGER PRIMARY KEY, timestamp TEXT, currency TEXT, wallet_balance TEXT, available_balance TEXT);
            CREATE TABLE IF NOT EXISTS bot_metrics (id INTEGER PRIMARY KEY, timestamp TEXT, total_trades INTEGER, net_realized_pnl TEXT, realized_pnl TEXT, unrealized_pnl TEXT, gross_profit TEXT, gross_loss TEXT, total_fees TEXT, wins INTEGER, losses INTEGER, win_rate REAL, current_asset_holdings TEXT, average_entry_price TEXT);
        """)

        # Schema migration: Add new columns if they don't exist
        async def _add_column_if_not_exists(
            table: str, column: str, type: str, default: str
        ):
            cursor = await self.conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in await cursor.fetchall()]
            if column not in columns:
                self.logger.warning(
                    f"Adding '{column}' column to '{table}' table for existing database."
                )
                await self.conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {type} DEFAULT {default}"
                )
                await self.conn.commit()

        # Apply migrations for bot_metrics table
        await _add_column_if_not_exists("bot_metrics", "realized_pnl", "TEXT", "'0'")
        await _add_column_if_not_exists(
            "bot_metrics", "net_realized_pnl", "TEXT", "'0'"
        )
        await _add_column_if_not_exists("bot_metrics", "unrealized_pnl", "TEXT", "'0'")
        await _add_column_if_not_exists("bot_metrics", "gross_profit", "TEXT", "'0'")
        await _add_column_if_not_exists("bot_metrics", "gross_loss", "TEXT", "'0'")
        await _add_column_if_not_exists("bot_metrics", "total_fees", "TEXT", "'0'")
        await _add_column_if_not_exists("bot_metrics", "wins", "INTEGER", "0")
        await _add_column_if_not_exists("bot_metrics", "losses", "INTEGER", "0")
        await _add_column_if_not_exists("bot_metrics", "win_rate", "REAL", "0.0")
        await _add_column_if_not_exists(
            "bot_metrics", "current_asset_holdings", "TEXT", "'0'"
        )
        await _add_column_if_not_exists(
            "bot_metrics", "average_entry_price", "TEXT", "'0'"
        )

        await self.conn.commit()
        self.logger.info("Database tables checked/created and migrated.")

    async def log_order_event(self, order_data: dict, message: str | None = None):
        """Logs an order event to the database."""
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT INTO order_events (timestamp, order_id, order_link_id, symbol, side, order_type, price, qty, status, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    order_data.get("orderId"),
                    order_data.get("orderLinkId"),
                    order_data.get("symbol"),
                    order_data.get("side"),
                    order_data.get("orderType"),
                    str(order_data.get("price", "0")),
                    str(order_data.get("qty", "0")),
                    order_data.get("orderStatus"),
                    message,
                ),
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging order event to DB: {e}", exc_info=True)

    async def log_trade_fill(self, trade_data: dict, realized_pnl_impact: Decimal):
        """Logs a trade fill event to the database."""
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT INTO trade_fills (timestamp, order_id, trade_id, symbol, side, exec_price, exec_qty, fee, fee_currency, pnl, realized_pnl_impact) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    trade_data.get("orderId"),
                    trade_data.get("execId"),
                    trade_data.get("symbol"),
                    trade_data.get("side"),
                    str(trade_data.get("execPrice", "0")),
                    str(trade_data.get("execQty", "0")),
                    str(trade_data.get("execFee", "0")),
                    trade_data.get("feeCurrency"),
                    str(trade_data.get("pnl", "0")),
                    str(realized_pnl_impact),
                ),
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging trade fill to DB: {e}", exc_info=True)

    async def log_balance_update(
        self,
        currency: str,
        wallet_balance: Decimal,
        available_balance: Decimal | None = None,
    ):
        """Logs a balance update to the database."""
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT INTO balance_updates (timestamp, currency, wallet_balance, available_balance) VALUES (?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    currency,
                    str(wallet_balance),
                    str(available_balance) if available_balance else None,
                ),
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging balance update to DB: {e}", exc_info=True)

    async def log_bot_metrics(self, metrics: TradeMetrics, unrealized_pnl: Decimal):
        """Logs the bot's current trade metrics to the database."""
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT INTO bot_metrics (timestamp, total_trades, net_realized_pnl, realized_pnl, unrealized_pnl, gross_profit, gross_loss, total_fees, wins, losses, win_rate, current_asset_holdings, average_entry_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    metrics.total_trades,
                    str(metrics.net_realized_pnl),
                    str(metrics.realized_pnl),
                    str(unrealized_pnl),
                    str(metrics.gross_profit),
                    str(metrics.gross_loss),
                    str(metrics.total_fees),
                    metrics.wins,
                    metrics.losses,
                    metrics.win_rate,
                    str(metrics.current_asset_holdings),
                    str(metrics.average_entry_price),
                ),
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging bot metrics to DB: {e}", exc_info=True)


# =====================================================================
# TRADING CLIENT
# =====================================================================
class TradingClient:
    """
    Handles all interactions with the Bybit API (HTTP and WebSocket).
    Includes retry logic for HTTP API calls and centralized response handling.
    """

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
        self.last_cancel_time = 0.0  # To enforce API rate limits for cancellations

        # Store original methods to apply tenacity decorators dynamically
        self._original_methods = {
            "get_instruments_info": self.get_instruments_info_impl,
            "get_wallet_balance": self.get_wallet_balance_impl,
            "get_position_info": self.get_position_info_impl,
            "set_leverage": self.set_leverage_impl,
            "get_open_orders": self.get_open_orders_impl,
            "place_order": self.place_order_impl,
            "cancel_order": self.cancel_order_impl,
            "cancel_all_orders": self.cancel_all_orders_impl,
        }
        self._initialize_api_retry_decorator()

    def _get_api_retry_decorator(self):
        """Returns a tenacity retry decorator configured with current system settings."""
        return retry(
            stop=stop_after_attempt(self.config.system.api_retry_attempts),
            wait=wait_exponential_jitter(
                initial=self.config.system.api_retry_initial_delay_sec,
                max=self.config.system.api_retry_max_delay_sec,
            ),
            # Retry on generic API errors, but not auth, value, rate limit, or insufficient balance errors
            retry=retry_if_exception_type(BybitAPIError)
            & ~retry_if_exception_type(APIAuthError)
            & ~retry_if_exception_type(ValueError)
            & ~retry_if_exception_type(BybitRateLimitError)
            & ~retry_if_exception_type(BybitInsufficientBalanceError),
            before_sleep=before_sleep_log(self.logger, logging.WARNING, exc_info=False),
            reraise=True,  # Re-raise the last exception if retries are exhausted
        )

    def _initialize_api_retry_decorator(self):
        """Applies the dynamically configured retry decorator to API methods."""
        api_retry = self._get_api_retry_decorator()
        for name, method in self._original_methods.items():
            setattr(self, name, api_retry(method))
        self.logger.debug("API retry decorators initialized and applied.")

    def _handle_response(self, response: Any, action: str):
        """
        Processes API responses, checks for errors, and raises specific exceptions.
        Returns the 'result' dictionary on success.
        """
        if not isinstance(response, dict):
            self.logger.error(
                f"API {action} failed: Invalid response format. Response: {response}"
            )
            raise BybitAPIError(
                f"Invalid API response for {action}",
                ret_code=-1,
                ret_msg="Invalid format",
            )

        ret_code = response.get("retCode", -1)
        ret_msg = response.get("retMsg", "Unknown error")

        if ret_code == 0:
            self.logger.debug(f"API {action} successful.")
            return response.get("result", {})

        # Map common Bybit error codes to custom exceptions
        if ret_code == 10004:
            raise APIAuthError(
                f"Authentication failed: {ret_msg}. Check API key permissions and validity."
            )
        elif ret_code in [10006, 10007, 10016, 120004, 120005]:
            raise BybitRateLimitError(
                f"API rate limit hit for {action}: {ret_msg}",
                ret_code=ret_code,
                ret_msg=ret_msg,
            )
        elif ret_code in [10001, 110001, 110003, 12130, 12131]:
            raise BybitInsufficientBalanceError(
                f"Insufficient balance for {action}: {ret_msg}",
                ret_code=ret_code,
                ret_msg=ret_msg,
            )
        elif ret_code == 10002:
            raise ValueError(
                f"API {action} parameter error: {ret_msg} (ErrCode: {ret_code})"
            )

        # Fallback for other Bybit API errors
        raise BybitAPIError(
            f"API {action} failed: {ret_msg}", ret_code=ret_code, ret_msg=ret_msg
        )

    async def get_instruments_info_impl(self) -> dict | None:
        """Retrieves instrument information for the configured symbol."""
        result = self._handle_response(
            self.http_session.get_instruments_info(
                category=self.config.category, symbol=self.config.symbol
            ),
            "get_instruments_info",
        )
        return result.get("list", [{}])[0] if result else None

    async def get_wallet_balance_impl(self) -> dict | None:
        """Retrieves wallet balance information."""
        account_type = (
            "UNIFIED" if self.config.category in ["linear", "inverse"] else "SPOT"
        )
        result = self._handle_response(
            self.http_session.get_wallet_balance(accountType=account_type),
            "get_wallet_balance",
        )
        return result.get("list", [{}])[0] if result else None

    async def get_position_info_impl(self) -> dict | None:
        """Retrieves position information for derivatives (linear/inverse)."""
        if self.config.category not in ["linear", "inverse"]:
            return None
        response = self.http_session.get_positions(
            category=self.config.category, symbol=self.config.symbol
        )
        result = self._handle_response(response, "get_position_info")
        if result and result.get("list"):
            # Find the position specific to the configured symbol
            for position in result["list"]:
                if position["symbol"] == self.config.symbol:
                    return position
        return None

    async def set_leverage_impl(self, leverage: Decimal) -> bool:
        """Sets the leverage for derivatives trading."""
        if self.config.category not in ["linear", "inverse"]:
            return True  # Leverage not applicable for spot
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
        """Retrieves all open orders for the configured symbol."""
        result = self._handle_response(
            self.http_session.get_open_orders(
                category=self.config.category, symbol=self.config.symbol, limit=50
            ),
            "get_open_orders",
        )
        return result.get("list", []) if result else []

    async def place_order_impl(self, params: dict) -> dict | None:
        """Places a new order on the exchange."""
        return self._handle_response(
            self.http_session.place_order(**params),
            f"place_order ({params.get('side')} {params.get('qty')} @ {params.get('price')})",
        )

    async def cancel_order_impl(
        self, order_id: str, order_link_id: str | None = None
    ) -> bool:
        """Cancels a specific order by ID, respecting a rate limit."""
        current_time = time.time()
        # Enforce a minimum delay between cancellation requests
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
        self.last_cancel_time = time.time()  # Update last cancellation time
        return self._handle_response(response, f"cancel_order {order_id}") is not None

    async def cancel_all_orders_impl(self) -> bool:
        """Cancels all open orders for the configured symbol."""
        params = {"category": self.config.category, "symbol": self.config.symbol}
        return (
            self._handle_response(
                self.http_session.cancel_all_orders(**params), "cancel_all_orders"
            )
            is not None
        )

    # Type hints for the methods wrapped by tenacity, for clarity
    get_instruments_info: Callable[[], Coroutine[Any, Any, dict | None]]
    get_wallet_balance: Callable[[], Coroutine[Any, Any, dict | None]]
    get_position_info: Callable[[], Coroutine[Any, Any, dict | None]]
    set_leverage: Callable[[Decimal], Coroutine[Any, Any, bool]]
    get_open_orders: Callable[[], Coroutine[Any, Any, list[dict]]]
    place_order: Callable[[dict], Coroutine[Any, Any, dict | None]]
    cancel_order: Callable[[str, str | None], Coroutine[Any, Any, bool]]
    cancel_all_orders: Callable[[], Coroutine[Any, Any, bool]]

    def _init_public_ws(self, callback: Callable):
        """Initializes the public WebSocket stream for orderbook data."""
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
        """Initializes the private WebSocket streams for order and position updates."""
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
        """Closes all active WebSocket connections."""
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
    """
    Main class for the Bybit Market Maker bot. Orchestrates market data,
    strategy execution, order management, and state persistence.
    """

    def __init__(self, config: Config):
        self.config = config
        self.logger = setup_logger(config.files)
        self.state_manager = StateManager(config.files.state_file, self.logger)
        self.db_manager = DBManager(config.files.db_file, self.logger)
        self.trading_client = TradingClient(self.config, self.logger)

        # Initialize trading state with deque maxlen for historical data
        self.state = TradingState(
            ws_reconnect_attempts_left=self.config.system.ws_reconnect_attempts,
            mid_price_history=deque(
                maxlen=self.config.strategy.dynamic_spread.volatility_window_sec * 2
            ),
            circuit_breaker_price_points=deque(
                maxlen=self.config.strategy.circuit_breaker.check_window_sec * 2
            ),
        )

        self.market_info: MarketInfo | None = (
            None  # Stores symbol-specific market rules
        )
        self.is_running = False  # Flag to control the main loop

        # Queues for processing WebSocket messages asynchronously
        self.orderbook_queue: asyncio.Queue = asyncio.Queue()
        self.private_ws_queue: asyncio.Queue = asyncio.Queue()

        # Locks to protect shared state accessed by multiple coroutines/threads
        self.market_data_lock = asyncio.Lock()
        self.active_orders_lock = asyncio.Lock()
        self.balance_position_lock = asyncio.Lock()

        self.loop: asyncio.AbstractEventLoop | None = (
            None  # Reference to the main event loop
        )

        self.logger.info(
            f"Market Maker Bot Initialized. Trading Mode: {self.config.trading_mode}"
        )
        if self.config.testnet:
            self.logger.info("Running on Bybit Testnet.")

    # --- Core Lifecycle & Setup ---
    async def run(self):
        """Main entry point for the bot, manages its lifecycle."""
        self.is_running = True
        self.loop = asyncio.get_running_loop()  # Get the current running event loop
        try:
            await self._initialize_bot()
            if self.config.trading_mode not in ["DRY_RUN", "SIMULATION"]:
                await self._connect_websockets()

            # Main bot loop
            while self.is_running:
                await self._main_loop_tick()
                await asyncio.sleep(self.config.system.loop_interval_sec)

        except (
            APIAuthError,
            WebSocketConnectionError,
            asyncio.CancelledError,
            KeyboardInterrupt,
            BybitAPIError,
        ) as e:
            self.logger.info(
                f"Bot stopping gracefully due to: {type(e).__name__} - {e}"
            )
        except Exception as e:
            self.logger.critical(
                f"An unhandled critical error occurred in the main loop: {e}",
                exc_info=True,
            )
        finally:
            await self.stop()  # Ensure graceful shutdown even after unexpected errors

    async def _initialize_bot(self):
        """Performs all necessary setup before the main trading loop begins."""
        self.logger.info("Performing initial setup...")

        await self.db_manager.connect()
        await self.db_manager.create_tables()

        if not await self._fetch_market_info():
            raise MarketInfoError("Failed to fetch market info. Shutting down.")

        if not await self._update_balance_and_position():
            raise InitialBalanceError(
                "Failed to fetch initial balance/position. Shutting down."
            )

        # Set leverage for derivatives if not in dry run mode
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

    async def _load_bot_state(self):
        """
        Loads the bot's state from the state file, if available.
        Handles deserialization of Decimal objects from string representation.
        """
        state_data = await self.state_manager.load_state()
        if state_data:
            async with self.active_orders_lock:
                self.state.active_orders = state_data.get("active_orders", {})
            self.state.metrics = state_data.get("metrics", self.state.metrics)
            # Convert Decimal fields back from string if they were stored as such (e.g., in JSON or generic pickle)
            for attr in [
                "realized_pnl",
                "gross_profit",
                "gross_loss",
                "total_fees",
                "current_asset_holdings",
                "average_entry_price",
            ]:
                current_value = getattr(self.state.metrics, attr)
                if isinstance(
                    current_value, (str, float)
                ):  # Check for string or float if not Decimal already
                    setattr(self.state.metrics, attr, Decimal(str(current_value)))

            self.state.metrics.last_pnl_update_timestamp = state_data.get(
                "metrics_last_pnl_update_timestamp"
            )

            self.state.is_paused = state_data.get("is_paused", False)
            self.state.pause_end_time = state_data.get("pause_end_time", 0.0)
            self.state.circuit_breaker_cooldown_end_time = state_data.get(
                "circuit_breaker_cooldown_end_time", 0.0
            )

            async with self.market_data_lock:
                # Ensure mid_price values are Decimal
                self.state.mid_price = Decimal(str(state_data.get("mid_price", "0")))
                self.state.smoothed_mid_price = Decimal(
                    str(state_data.get("smoothed_mid_price", "0"))
                )
                self.state.mid_price_history.extend(
                    state_data.get("mid_price_history", [])
                )
                # Convert price points to Decimal where necessary
                self.state.circuit_breaker_price_points.extend(
                    [
                        (t, Decimal(str(p)))
                        for t, p in state_data.get("circuit_breaker_price_points", [])
                    ]
                )

            self.logger.info(
                f"Loaded state with {len(self.state.active_orders)} active orders and metrics: {self.state.metrics}"
            )
        else:
            self.logger.info("No saved state found. Starting fresh.")

    async def _connect_websockets(self):
        """Establishes connections to public and private WebSockets."""
        self.logger.info("Connecting WebSockets...")
        try:
            self.trading_client._init_public_ws(
                lambda msg: self._schedule_coro(self.orderbook_queue.put(msg))
            )
            self.trading_client._init_private_ws(
                lambda msg: self._schedule_coro(self.private_ws_queue.put(msg)),
                lambda msg: self._schedule_coro(self.private_ws_queue.put(msg)),
            )
            self.state.ws_reconnect_attempts_left = (
                self.config.system.ws_reconnect_attempts
            )
            self.logger.info("WebSockets connected and subscribed. Queues active.")
        except Exception as e:
            self.logger.error(
                f"Failed to establish initial WebSocket connections: {e}", exc_info=True
            )
            raise WebSocketConnectionError(f"Initial WS connection failed: {e}")

    async def _reconnect_websockets(self):
        """
        Attempts to reconnect WebSockets with exponential backoff and a maximum delay.
        If attempts are exhausted, the bot will shut down.
        """
        if self.state.ws_reconnect_attempts_left <= 0:
            self.logger.critical(
                "Max WebSocket reconnection attempts reached. Shutting down."
            )
            self.is_running = False
            return

        self.state.ws_reconnect_attempts_left -= 1
        # Calculate exponential backoff delay
        delay = self.config.system.ws_reconnect_initial_delay_sec * (
            2
            ** (
                self.config.system.ws_reconnect_attempts
                - self.state.ws_reconnect_attempts_left
                - 1
            )
        )
        delay = min(delay, self.config.system.ws_reconnect_max_delay_sec)
        self.logger.warning(
            f"Attempting WebSocket reconnection in {delay:.1f} seconds... ({self.state.ws_reconnect_attempts_left} attempts left)"
        )
        await asyncio.sleep(delay)

        self.trading_client.close_websockets()  # Close existing connections before retrying
        try:
            await self._connect_websockets()
            self.logger.info("WebSocket reconnected successfully.")
        except WebSocketConnectionError:
            self.logger.error("WebSocket reconnection attempt failed.")

    async def _main_loop_tick(self):
        """Executes a single tick of the main trading loop."""
        current_time = time.time()

        await self._process_ws_queues()

        if self.config.trading_mode not in ["DRY_RUN", "SIMULATION"]:
            await self._websocket_health_check(current_time)
            if not self.is_running:
                return  # Bot might have stopped during WS check

        await self._periodic_health_check(current_time)

        # Handle circuit breaker pause
        if self.state.is_paused and current_time < self.state.pause_end_time:
            self.logger.debug(
                f"Bot is paused due to circuit breaker. Resuming in {int(self.state.pause_end_time - current_time)}s."
            )
            return
        elif self.state.is_paused:  # Pause just ended
            self.logger.info("Circuit breaker pause finished. Resuming trading.")
            self.state.is_paused = False
            self.state.circuit_breaker_cooldown_end_time = (
                current_time
                + self.config.strategy.circuit_breaker.cool_down_after_trip_sec
            )

        # Handle circuit breaker cooldown
        if current_time < self.state.circuit_breaker_cooldown_end_time:
            self.logger.debug(
                f"Circuit breaker in cooldown. Resuming trading in {int(self.state.circuit_breaker_cooldown_end_time - current_time)}s."
            )
            return

        await self._manage_orders()

        # Log status summary periodically
        if (
            current_time - self.state.last_status_report_time
            > self.config.system.status_report_interval_sec
        ):
            await self._log_status_summary()
            self.state.last_status_report_time = current_time

    async def _process_ws_queues(self):
        """Processes all pending messages from WebSocket queues."""
        # Process public orderbook messages
        while True:
            try:
                message = self.orderbook_queue.get_nowait()
                await self._process_orderbook_message(message)
            except asyncio.QueueEmpty:
                break

        # Process private order/position messages
        while True:
            try:
                message = self.private_ws_queue.get_nowait()
                await self._process_private_ws_message(message)
            except asyncio.QueueEmpty:
                break

    async def _process_orderbook_message(self, message: dict):
        """Processes a single orderbook message from the queue to update mid-price."""
        self.state.last_ws_message_time = (
            time.time()
        )  # Update last received WS message time
        try:
            # Ensure message contains valid orderbook data
            if "data" in message and message["topic"].startswith("orderbook"):
                data = message["data"]
                bids = data.get("b")
                asks = data.get("a")
                if bids and asks and bids[0] and asks[0] and bids[0][0] and asks[0][0]:
                    await self._update_mid_price(bids, asks)
                else:
                    self.logger.debug(
                        "Received empty or incomplete orderbook data. Skipping mid-price update."
                    )
        except Exception as e:
            self.logger.error(f"Error processing orderbook message: {e}", exc_info=True)

    async def _process_private_ws_message(self, message: dict):
        """Processes a single private WebSocket message (order or position update)."""
        self.state.last_ws_message_time = (
            time.time()
        )  # Update last received WS message time
        try:
            if "data" in message:
                topic = message.get("topic", "")
                if topic == "order":
                    for order_data in message["data"]:
                        if (
                            order_data.get("symbol") == self.config.symbol
                        ):  # Only process for configured symbol
                            await self._process_order_update(order_data)
                elif topic == "position":
                    for pos_data in message["data"]:
                        if (
                            pos_data["symbol"] == self.config.symbol
                        ):  # Only process for configured symbol
                            await self._process_position_update(pos_data)
                else:
                    self.logger.debug(f"Received unknown private WS topic: {topic}")
        except Exception as e:
            self.logger.error(
                f"Error processing private WS message: {e}", exc_info=True
            )

    async def _websocket_health_check(self, current_time: float):
        """
        Checks the health of WebSocket connections and initiates reconnection if necessary.
        Triggers if a WS is disconnected or no messages are received for too long.
        """
        # Check connection status of both public and private WebSockets
        ws_public_connected = (
            self.trading_client.ws_public
            and self.trading_client.ws_public.is_connected()
        )
        ws_private_connected = (
            self.trading_client.ws_private
            and self.trading_client.ws_private.is_connected()
        )

        if not ws_public_connected or not ws_private_connected:
            self.logger.warning(
                f"WebSocket {'Public' if not ws_public_connected else 'Private'} disconnected. Attempting reconnection."
            )
            await self._reconnect_websockets()
            return

        # Check for recent activity (heartbeat)
        if (
            current_time - self.state.last_ws_message_time
            > self.config.system.ws_heartbeat_sec
        ):
            self.logger.warning(
                "WebSocket heartbeat lost (no new messages received). Attempting reconnection."
            )
            await self._reconnect_websockets()
            return

    async def _periodic_health_check(self, current_time: float):
        """
        Performs periodic health checks, such as re-fetching balance and position
        information via HTTP, to ensure consistency with the exchange.
        """
        if (
            current_time - self.state.last_health_check_time
        ) < self.config.system.health_check_interval_sec:
            return

        await self._update_balance_and_position()
        self.state.last_health_check_time = current_time

    async def stop(self):
        """Initiates a graceful shutdown of the bot."""
        if not self.is_running:
            return  # Already stopped
        self.is_running = False
        self.logger.info("Initiating graceful shutdown...")

        # Cancel all open orders if not in dry run mode
        if self.config.trading_mode not in ["DRY_RUN", "SIMULATION"]:
            await self._cancel_all_orders()

        # Save current state
        state_to_save = {
            "active_orders": self.state.active_orders,
            "metrics": self.state.metrics,
            "metrics_last_pnl_update_timestamp": self.state.metrics.last_pnl_update_timestamp,
            "is_paused": self.state.is_paused,
            "pause_end_time": self.state.pause_end_time,
            "circuit_breaker_cooldown_end_time": self.state.circuit_breaker_cooldown_end_time,
            "mid_price": str(
                self.state.mid_price
            ),  # Store Decimals as strings for safe serialization
            "smoothed_mid_price": str(self.state.smoothed_mid_price),
            "mid_price_history": list(self.state.mid_price_history),
            "circuit_breaker_price_points": [
                (t, str(p)) for t, p in self.state.circuit_breaker_price_points
            ],  # Convert Decimals to strings
        }
        try:
            await self.state_manager.save_state(state_to_save)
        except Exception as e:
            self.logger.error(
                f"Error during state saving on shutdown: {e}", exc_info=True
            )

        # Log final metrics
        try:
            unrealized_pnl = self.state.metrics.calculate_unrealized_pnl(
                self.state.mid_price
            )
            await self.db_manager.log_bot_metrics(self.state.metrics, unrealized_pnl)
        except Exception as e:
            self.logger.error(
                f"Could not log final metrics to DB. Error: {e}", exc_info=True
            )

        self.trading_client.close_websockets()
        await self.db_manager.close()
        self.logger.info("Bot shut down successfully.")

    def _schedule_coro(self, coro: Coroutine):
        """
        Schedules a coroutine to be executed on the main event loop.
        Useful when a callback from a background thread (e.g., WebSocket) needs to
        perform operations on the main loop's state.
        """
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self.loop)
        else:
            self.logger.warning(
                "Event loop not available or not running for scheduling coroutine from background thread. Coroutine skipped."
            )

    async def _update_mid_price(self, bids: list[list[str]], asks: list[list[str]]):
        """
        Updates the bot's internal mid-price and its history.
        Applies Exponential Moving Average (EMA) smoothing for stability.
        """
        async with self.market_data_lock:
            # Safely parse bid/ask prices
            best_bid = Decimal(bids[0][0])
            best_ask = Decimal(asks[0][0])
            new_mid_price = (best_bid + best_ask) / Decimal("2")

            if new_mid_price != self.state.mid_price:
                self.state.mid_price = new_mid_price
                self.state.mid_price_history.append(
                    float(self.state.mid_price)
                )  # For volatility calculation
                self.state.circuit_breaker_price_points.append(
                    (time.time(), self.state.mid_price)
                )  # For circuit breaker

                # Apply EMA smoothing
                if self.state.smoothed_mid_price == Decimal("0"):
                    self.state.smoothed_mid_price = new_mid_price
                else:
                    alpha = self.config.strategy.dynamic_spread.price_change_smoothing_factor
                    self.state.smoothed_mid_price = (alpha * new_mid_price) + (
                        (Decimal("1") - alpha) * self.state.smoothed_mid_price
                    )

                self.logger.debug(
                    f"Mid-price updated to: {self.state.mid_price}, Smoothed: {self.state.smoothed_mid_price}"
                )

    async def _process_order_update(self, order_data: dict):
        """Processes a single order update from the WebSocket stream."""
        order_id, status = order_data["orderId"], order_data["orderStatus"]
        self.logger.info(
            f"Order {order_id} status update: {status} (OrderLink: {order_data.get('orderLinkId')})"
        )
        await self.db_manager.log_order_event(order_data)

        async with self.active_orders_lock:
            if order_id in self.state.active_orders:
                self.state.active_orders[order_id]["status"] = status
                if status == "Filled":
                    await self._process_fill(order_data)
                    del self.state.active_orders[order_id]
                elif status in ["Cancelled", "Rejected", "Deactivated", "Expired"]:
                    self.logger.info(
                        f"Order {order_id} removed from active orders due to status: {status}."
                    )
                    del self.state.active_orders[order_id]
            elif status == "Filled":
                self.logger.warning(
                    f"Received fill for untracked order {order_id}. Processing fill anyway."
                )
                await self._process_fill(order_data)
            else:
                self.logger.debug(
                    f"Received update for untracked order {order_id} with status {status}. Ignoring."
                )

    async def _process_position_update(self, pos_data: dict):
        """Processes a single position update from the WebSocket stream."""
        async with self.balance_position_lock:
            # For derivatives, 'size' indicates quantity, 'side' indicates direction
            new_pos_qty = Decimal(pos_data["size"]) * (
                Decimal("1") if pos_data["side"] == "Buy" else Decimal("-1")
            )
            if new_pos_qty != self.state.current_position_qty:
                self.state.current_position_qty = new_pos_qty
                self.logger.info(
                    f"POSITION UPDATE (WS): Position is now {self.state.current_position_qty} {self.config.base_currency}"
                )

            # Update unrealized PnL for derivatives
            if (
                self.config.category in ["linear", "inverse"]
                and "unrealisedPnl" in pos_data
            ):
                self.state.unrealized_pnl_derivatives = Decimal(
                    pos_data["unrealisedPnl"]
                )
                self.logger.debug(
                    f"UNREALIZED PNL (WS): {self.state.unrealized_pnl_derivatives:+.4f} {self.config.quote_currency}"
                )

    # --- Strategy & Order Management ---
    async def _manage_orders(self):
        """
        Main method for managing active orders. Calculates target prices,
        applies strategy adjustments, and reconciles orders with the exchange.
        """
        current_time = time.time()
        if (
            current_time - self.state.last_order_management_time
        ) < self.config.system.order_refresh_interval_sec:
            return  # Respect order refresh interval
        self.state.last_order_management_time = current_time

        if await self._check_circuit_breaker():
            self.logger.warning("Circuit breaker tripped. Skipping order management.")
            return

        async with self.market_data_lock, self.balance_position_lock:
            # Ensure we have valid price and market info before proceeding
            if self.state.smoothed_mid_price == Decimal("0") or not self.market_info:
                self.logger.warning(
                    "Smoothed mid-price or market info not available, skipping order management."
                )
                return
            mid_price_for_strategy = self.state.smoothed_mid_price
            pos_qty = (
                self.state.metrics.current_asset_holdings
            )  # Use bot's internal holdings for strategy

        # Calculate dynamic spread and inventory skew
        spread_pct = self._calculate_dynamic_spread()
        skew_factor = self._calculate_inventory_skew(mid_price_for_strategy, pos_qty)
        skewed_mid_price = mid_price_for_strategy * (Decimal("1") + skew_factor)

        # Determine target bid and ask prices
        target_bid_price = skewed_mid_price * (Decimal("1") - spread_pct)
        target_ask_price = skewed_mid_price * (Decimal("1") + spread_pct)
        target_bid_price, target_ask_price = self._enforce_min_profit_spread(
            mid_price_for_strategy, target_bid_price, target_ask_price
        )

        await self._reconcile_and_place_orders(target_bid_price, target_ask_price)

    async def _check_circuit_breaker(self) -> bool:
        """
        Checks if the circuit breaker conditions are met (rapid price change).
        If tripped, pauses trading and cancels all open orders.
        Returns True if tripped, False otherwise.
        """
        cb_config = self.config.strategy.circuit_breaker
        if not cb_config.enabled:
            return False

        current_time = time.time()
        # Filter price points within the check window
        async with self.market_data_lock:
            recent_prices_window = [
                (t, p)
                for t, p in self.state.circuit_breaker_price_points
                if (current_time - t) <= cb_config.check_window_sec
            ]

        if len(recent_prices_window) < 2:
            return False  # Need at least two points to calculate change

        # Sort by timestamp to get start and end prices
        recent_prices_window.sort(key=lambda x: x[0])
        start_price = recent_prices_window[0][1]
        end_price = recent_prices_window[-1][1]

        if start_price == Decimal("0"):
            return False  # Avoid division by zero

        price_change_pct = abs(end_price - start_price) / start_price

        if price_change_pct > cb_config.pause_threshold_pct:
            self.logger.warning(
                f"CIRCUIT BREAKER TRIPPED: Price changed {price_change_pct:.2%} in {cb_config.check_window_sec}s. Pausing trading for {cb_config.pause_duration_sec}s."
            )
            self.state.is_paused = True
            self.state.pause_end_time = current_time + cb_config.pause_duration_sec
            self.state.circuit_breaker_cooldown_end_time = (
                self.state.pause_end_time + cb_config.cool_down_after_trip_sec
            )
            await self._cancel_all_orders()
            return True
        return False

    async def _calculate_dynamic_spread(self) -> Decimal:
        """
        Calculates the spread dynamically based on recent market volatility.
        If dynamic spread is disabled, returns the base spread.
        """
        ds_config = self.config.strategy.dynamic_spread
        current_time = time.time()

        async with self.market_data_lock:
            # Get prices within the volatility calculation window
            volatility_window_prices = [
                p
                for t, p in self.state.circuit_breaker_price_points
                if (current_time - t) <= ds_config.volatility_window_sec
            ]

        if not ds_config.enabled or len(volatility_window_prices) < 2:
            return self.config.strategy.base_spread_pct

        float_prices = [float(p) for p in volatility_window_prices]

        # Calculate standard deviation (volatility)
        if np.all(
            np.array(float_prices) == float_prices[0]
        ):  # Handle case of no price change
            volatility = 0.0
        else:
            volatility = np.std(float_prices) / np.mean(
                float_prices
            )  # Coefficient of variation

        dynamic_adjustment = Decimal(str(volatility)) * ds_config.volatility_multiplier
        # Clamp the calculated spread within min/max bounds
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
        """
        Calculates a price skew factor based on the current inventory (position quantity).
        This encourages trading against the current position to balance inventory.
        """
        inv_config = self.config.strategy.inventory
        if (
            not inv_config.enabled
            or self.config.max_net_exposure_usd <= 0
            or mid_price <= 0
        ):
            return Decimal("0")

        current_inventory_value = pos_qty * mid_price
        max_exposure_for_ratio = (
            self.config.max_net_exposure_usd * inv_config.max_inventory_ratio
        )
        if max_exposure_for_ratio <= 0:
            return Decimal("0")  # Avoid division by zero

        # Calculate inventory ratio (-1 for max short, 1 for max long)
        inventory_ratio = current_inventory_value / max_exposure_for_ratio
        inventory_ratio = max(
            Decimal("-1.0"), min(Decimal("1.0"), inventory_ratio)
        )  # Clamp between -1 and 1

        # Skew factor is negative of inventory ratio to push prices against current position
        skew_factor = -inventory_ratio * inv_config.skew_intensity

        if abs(skew_factor) > Decimal("1e-6"):
            self.logger.debug(
                f"Inventory skew active. Position Value: {current_inventory_value:.2f} {self.config.quote_currency}, Ratio: {inventory_ratio:.3f}, Skew: {skew_factor:.6f}"
            )
        return skew_factor

    def _enforce_min_profit_spread(
        self, mid_price: Decimal, bid_p: Decimal, ask_p: Decimal
    ) -> tuple[Decimal, Decimal]:
        """
        Ensures that the bid and ask prices maintain a minimum profitable spread
        after accounting for estimated fees. Adjusts prices outwards if necessary.
        """
        if not self.market_info or mid_price <= Decimal("0"):
            self.logger.warning(
                "Mid-price or market info not available for enforcing minimum profit spread. Returning original bid/ask."
            )
            return bid_p, ask_p

        # Estimate total fees for a round trip (taker buy + taker sell)
        estimated_fee_per_side_pct = self.market_info.taker_fee_rate
        min_gross_spread_pct = self.config.strategy.min_profit_spread_after_fees_pct + (
            estimated_fee_per_side_pct * Decimal("2")
        )
        min_spread_val = mid_price * min_gross_spread_pct

        # If bid is higher than ask or spread is too small, adjust outwards from mid-price
        if ask_p <= bid_p or (ask_p - bid_p) < min_spread_val:
            self.logger.debug(
                f"Adjusting spread. Original Bid: {bid_p}, Ask: {ask_p}, Mid: {mid_price}, Current Spread: {ask_p - bid_p:.6f}, Min Spread: {min_spread_val:.6f}"
            )
            half_min_spread = (min_spread_val / Decimal("2")).quantize(
                self.market_info.price_precision
            )
            bid_p = (mid_price - half_min_spread).quantize(
                self.market_info.price_precision
            )
            ask_p = (mid_price + half_min_spread).quantize(
                self.market_info.price_precision
            )
            self.logger.debug(f"Adjusted to Bid: {bid_p}, Ask: {ask_p}")
        return bid_p, ask_p

    async def _reconcile_and_place_orders(
        self, target_bid: Decimal, target_ask: Decimal
    ):
        """
        Compares desired order book state with current active orders.
        Cancels stale/duplicate orders and places new ones to match targets.
        """
        if not self.market_info:
            return

        # Quantize target prices to market precision
        target_bid = self.market_info.format_price(target_bid)
        target_ask = self.market_info.format_price(target_ask)

        current_active_orders_by_side = {"Buy": [], "Sell": []}
        orders_to_cancel = []

        async with self.active_orders_lock:
            # Categorize existing orders and identify stale ones
            for order_id, order_data in list(self.state.active_orders.items()):
                if order_data.get("symbol") != self.config.symbol:
                    self.logger.warning(
                        f"Found untracked symbol order {order_id} in active_orders. Cancelling."
                    )
                    orders_to_cancel.append((order_id, order_data.get("orderLinkId")))
                    continue

                is_stale = False
                if order_data["side"] == "Buy":
                    if abs(order_data["price"] - target_bid) > (
                        order_data["price"]
                        * self.config.strategy.order_stale_threshold_pct
                    ):
                        is_stale = True
                    current_active_orders_by_side["Buy"].append(
                        (order_id, order_data, is_stale)
                    )
                else:  # Sell order
                    if abs(order_data["price"] - target_ask) > (
                        order_data["price"]
                        * self.config.strategy.order_stale_threshold_pct
                    ):
                        is_stale = True
                    current_active_orders_by_side["Sell"].append(
                        (order_id, order_data, is_stale)
                    )

            # Determine which existing orders to keep or cancel
            bid_order_to_keep = None
            for oid, odata, is_stale in current_active_orders_by_side["Buy"]:
                if not is_stale and bid_order_to_keep is None:
                    bid_order_to_keep = odata  # Keep the first non-stale bid order
                else:
                    orders_to_cancel.append(
                        (oid, odata.get("orderLinkId"))
                    )  # Cancel other bids

            ask_order_to_keep = None
            for oid, odata, is_stale in current_active_orders_by_side["Sell"]:
                if not is_stale and ask_order_to_keep is None:
                    ask_order_to_keep = odata  # Keep the first non-stale ask order
                else:
                    orders_to_cancel.append(
                        (oid, odata.get("orderLinkId"))
                    )  # Cancel other asks

        # Execute cancellations
        for oid, olid in orders_to_cancel:
            order_info = self.state.active_orders.get(oid, {})
            self.logger.info(
                f"Cancelling stale/duplicate order {oid} (Side: {order_info.get('side')}, Price: {order_info.get('price')}). Target Bid: {target_bid}, Target Ask: {target_ask}"
            )
            await self._cancel_order(oid, olid)

        # Plan new orders
        new_orders_to_place = []
        current_outstanding_orders = len(self.state.active_orders) - len(
            orders_to_cancel
        )  # Orders that will remain after cancellation

        if (
            not bid_order_to_keep
            and current_outstanding_orders < self.config.strategy.max_outstanding_orders
        ):
            buy_qty = await self._calculate_order_size("Buy", target_bid)
            if buy_qty > 0:
                new_orders_to_place.append(("Buy", target_bid, buy_qty))
                current_outstanding_orders += 1  # Account for this potential order
            else:
                self.logger.debug(
                    "Calculated buy quantity is zero or too small, skipping bid order placement."
                )

        if (
            not ask_order_to_keep
            and current_outstanding_orders < self.config.strategy.max_outstanding_orders
        ):
            sell_qty = await self._calculate_order_size("Sell", target_ask)
            if sell_qty > 0:
                new_orders_to_place.append(("Sell", target_ask, sell_qty))
            else:
                self.logger.debug(
                    "Calculated sell quantity is zero or too small, skipping ask order placement."
                )
        elif not ask_order_to_keep:  # Not enough slots even if buy order was planned
            self.logger.warning(
                f"Skipping ask order placement: Max outstanding orders ({self.config.strategy.max_outstanding_orders}) reached or will be exceeded."
            )

        # Place new orders
        for side, price, qty in new_orders_to_place:
            self.logger.info(f"Placing new {side} order: Price={price}, Qty={qty}")
            await self._place_limit_order(side, price, qty)

    async def _log_status_summary(self):
        """Logs a summary of the bot's current status, PnL, and orders."""
        async with (
            self.balance_position_lock,
            self.active_orders_lock,
            self.market_data_lock,
        ):
            metrics = self.state.metrics
            current_market_price = (
                self.state.mid_price
                if self.state.mid_price > Decimal("0")
                else self.state.smoothed_mid_price
            )

            # Calculate unrealized PnL based on category
            if current_market_price == Decimal("0"):
                self.logger.warning(
                    "Cannot calculate unrealized PnL, current market price is zero."
                )
                unrealized_pnl_bot_calculated = Decimal("0")
            else:
                unrealized_pnl_bot_calculated = metrics.calculate_unrealized_pnl(
                    current_market_price
                )

            if self.config.category in ["linear", "inverse"]:
                display_unrealized_pnl = (
                    self.state.unrealized_pnl_derivatives
                )  # Use exchange-reported UPNL for derivatives
            else:
                display_unrealized_pnl = (
                    unrealized_pnl_bot_calculated  # Use bot-calculated UPNL for spot
                )

            total_current_pnl = metrics.net_realized_pnl + display_unrealized_pnl
            pos_qty = metrics.current_asset_holdings
            exposure_usd = (
                pos_qty * current_market_price
                if current_market_price > Decimal("0")
                else Decimal("0")
            )

            pnl_summary = (
                f"Realized PNL: {metrics.realized_pnl:+.4f} {self.config.quote_currency} | "
                f"Unrealized PNL: {display_unrealized_pnl:+.4f} {self.config.quote_currency}"
            )

            active_buys = sum(
                1 for o in self.state.active_orders.values() if o["side"] == "Buy"
            )
            active_sells = sum(
                1 for o in self.state.active_orders.values() if o["side"] == "Sell"
            )

        self.logger.info(
            f"STATUS | Total Current PNL: {total_current_pnl:+.4f} | {pnl_summary} | "
            f"Net Realized PNL: {metrics.net_realized_pnl:+.4f} | Win Rate: {metrics.win_rate:.2f}% | "
            f"Position: {pos_qty} {self.config.base_currency} (Exposure: {exposure_usd:+.2f} {self.config.quote_currency}) | "
            f"Orders: {active_buys} Buy / {active_sells} Sell"
        )
        await self.db_manager.log_bot_metrics(metrics, display_unrealized_pnl)

    async def _fetch_market_info(self) -> bool:
        """Retrieves and parses market information (precision, min qty, fees) for the symbol."""
        if self.config.trading_mode == "SIMULATION":
            # Provide mock market info for simulation mode
            self.market_info = MarketInfo(
                symbol=self.config.symbol,
                price_precision=Decimal("0.00001"),
                quantity_precision=Decimal("1"),
                min_order_qty=Decimal("1"),
                min_notional_value=self.config.min_order_value_usd,  # Use config for min notional in simulation
                maker_fee_rate=Decimal("0.0002"),
                taker_fee_rate=Decimal("0.0005"),
            )
            self.logger.info(
                f"SIMULATION mode: Mock market info loaded for {self.config.symbol}: {self.market_info}"
            )
            return True

        info = await self.trading_client.get_instruments_info()
        if not info:
            self.logger.critical(
                "Failed to retrieve instrument info from API. Check symbol and connectivity."
            )
            return False

        try:
            # Parse fee rates, handling potential missing takerFeeRate
            maker_fee_rate_str = info.get("makerFeeRate")
            taker_fee_rate_str = info.get("takerFeeRate")

            if maker_fee_rate_str is None:
                self.logger.critical(
                    f"Missing 'makerFeeRate' for {self.config.symbol}. Full info: {info}"
                )
                raise MarketInfoError(
                    f"Critical fee information missing for {self.config.symbol}: makerFeeRate."
                )

            maker_fee_rate = Decimal(maker_fee_rate_str)
            taker_fee_rate = (
                Decimal(taker_fee_rate_str) if taker_fee_rate_str else maker_fee_rate
            )  # Fallback if taker rate is missing

            self.market_info = MarketInfo(
                symbol=self.config.symbol,
                price_precision=Decimal(info["priceFilter"]["tickSize"]),
                quantity_precision=Decimal(info["lotSizeFilter"]["qtyStep"]),
                min_order_qty=Decimal(info["lotSizeFilter"]["minOrderQty"]),
                min_notional_value=Decimal(
                    info["lotSizeFilter"].get("minNotionalValue", "0")
                ),
                maker_fee_rate=maker_fee_rate,
                taker_fee_rate=taker_fee_rate,
            )
            # Use configured min_order_value_usd if API's minNotionalValue is zero or missing
            if self.market_info.min_notional_value == Decimal("0"):
                self.logger.warning(
                    f"minNotionalValue not found or is 0 for {self.config.symbol}. Using config.min_order_value_usd as fallback."
                )
                self.market_info.min_notional_value = self.config.min_order_value_usd

            self.logger.info(
                f"Market info fetched for {self.config.symbol}: {self.market_info}"
            )
            return True
        except (KeyError, ValueError) as e:
            self.logger.critical(
                f"Error parsing market info (missing key or invalid format): {e}. Full info: {info}",
                exc_info=True,
            )
            return False
        except Exception as e:
            self.logger.critical(
                f"Unexpected error while parsing market info: {e}. Full info: {info}",
                exc_info=True,
            )
            return False

    async def _update_balance_and_position(self) -> bool:
        """
        Fetches and updates the bot's current balance and position.
        Handles DRY_RUN/SIMULATION modes with virtual capital.
        """
        async with self.balance_position_lock:
            if self.config.trading_mode in ["DRY_RUN", "SIMULATION"]:
                # Initialize virtual capital if not already set
                if self.state.current_balance == Decimal("0"):
                    self.state.current_balance = self.config.initial_dry_run_capital
                    self.state.available_balance = self.state.current_balance
                    self.logger.info(
                        f"{self.config.trading_mode}: Initialized virtual balance: {self.state.current_balance} {self.config.quote_currency}"
                    )
                # In dry run, bot's internal holdings are its 'position'
                self.state.current_position_qty = (
                    self.state.metrics.current_asset_holdings
                )
                self.state.unrealized_pnl_derivatives = Decimal(
                    "0"
                )  # No derivatives PnL in dry run
                return True

            # Fetch live balance from API
            balance_data = await self.trading_client.get_wallet_balance()
            if not balance_data:
                self.logger.error("Failed to fetch wallet balance.")
                return False

            found_quote_balance = False
            for coin in balance_data.get("coin", []):
                if coin["coin"] == self.config.quote_currency:
                    self.state.current_balance = Decimal(coin["walletBalance"])
                    self.state.available_balance = Decimal(
                        coin.get("availableToWithdraw", coin["walletBalance"])
                    )
                    self.logger.debug(
                        f"Balance: {self.state.current_balance} {self.config.quote_currency}, Available: {self.state.available_balance}"
                    )
                    await self.db_manager.log_balance_update(
                        self.config.quote_currency,
                        self.state.current_balance,
                        self.state.available_balance,
                    )
                    found_quote_balance = True
                    break

            if not found_quote_balance:
                self.logger.warning(
                    f"Could not find balance for {self.config.quote_currency}. This might affect order sizing."
                )

            # Fetch live position for derivatives or use internal holdings for spot
            if self.config.category in ["linear", "inverse"]:
                position_data = await self.trading_client.get_position_info()
                if position_data and position_data.get("size"):
                    self.state.current_position_qty = Decimal(position_data["size"]) * (
                        Decimal("1")
                        if position_data["side"] == "Buy"
                        else Decimal("-1")
                    )
                    self.state.unrealized_pnl_derivatives = Decimal(
                        position_data.get("unrealisedPnl", "0")
                    )
                else:
                    self.state.current_position_qty = Decimal("0")
                    self.state.unrealized_pnl_derivatives = Decimal("0")
            else:  # For spot, position is simply bot's holdings
                self.state.current_position_qty = (
                    self.state.metrics.current_asset_holdings
                )
                self.state.unrealized_pnl_derivatives = Decimal(
                    "0"
                )  # No separate unrealized PnL from exchange for spot

            self.logger.info(
                f"Updated Balance: {self.state.current_balance} {self.config.quote_currency}, Position: {self.state.current_position_qty} {self.config.base_currency}, UPNL (Deriv): {self.state.unrealized_pnl_derivatives:+.4f}"
            )
            return True

    async def _process_fill(self, order_data: dict):
        """
        Processes an order fill, updates trade metrics, PnL, and triggers balance/position refresh.
        """
        side = order_data.get("side", "Unknown")
        exec_qty = Decimal(order_data.get("execQty", "0"))
        exec_price = Decimal(order_data.get("execPrice", "0"))
        exec_fee = Decimal(order_data.get("execFee", "0"))

        metrics = self.state.metrics
        realized_pnl_impact = Decimal("0")

        if side == "Buy":
            metrics.update_pnl_on_buy(exec_qty, exec_price)
            self.logger.info(
                f"Order FILLED: BUY {exec_qty} @ {exec_price}, Fee: {exec_fee}. Holdings: {metrics.current_asset_holdings}, Avg Entry: {metrics.average_entry_price}"
            )
        elif side == "Sell":
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
        if realized_pnl_impact > 0:
            metrics.gross_profit += realized_pnl_impact
            metrics.wins += 1
        elif realized_pnl_impact < 0:
            metrics.gross_loss += abs(realized_pnl_impact)
            metrics.losses += 1
        metrics.update_win_rate()

        await self.db_manager.log_trade_fill(order_data, realized_pnl_impact)
        await (
            self._update_balance_and_position()
        )  # Refresh balance/position after a fill

    async def _cancel_order(self, order_id: str, order_link_id: str | None = None):
        """Attempts to cancel a specific order on the exchange."""
        self.logger.info(
            f"Attempting to cancel order {order_id} (OrderLink: {order_link_id})..."
        )
        if self.config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            self.logger.info(
                f"{self.config.trading_mode}: Would cancel order {order_id}."
            )
            async with self.active_orders_lock:
                if order_id in self.state.active_orders:
                    del self.state.active_orders[order_id]
            return

        try:
            if await self.trading_client.cancel_order(order_id, order_link_id):
                self.logger.info(f"Order {order_id} cancelled successfully.")
                async with self.active_orders_lock:
                    if order_id in self.state.active_orders:
                        del self.state.active_orders[order_id]
            else:
                self.logger.error(
                    f"Failed to cancel order {order_id} via API after retries."
                )
        except Exception as e:
            self.logger.error(
                f"Error during cancellation of order {order_id}: {e}", exc_info=True
            )

    async def _cancel_all_orders(self):
        """Attempts to cancel all open orders for the configured symbol on the exchange."""
        self.logger.info("Canceling all open orders...")
        if self.config.trading_mode in ["DRY_RUN", "SIMULATION"]:
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
                self.logger.error(
                    f"Error during cancellation of all orders: {e}", exc_info=True
                )

        async with self.active_orders_lock:
            self.state.active_orders.clear()  # Clear local tracking of active orders

    async def _calculate_order_size(self, side: str, price: Decimal) -> Decimal:
        """
        Calculates the appropriate order quantity based on available capital,
        max net exposure, and market requirements. Returns 0 if no valid quantity.
        """
        async with self.balance_position_lock:
            # Effective capital depends on trading category (leverage for derivatives)
            capital = (
                self.state.available_balance
                if self.config.category == "spot"
                else self.state.current_balance
            )
            metrics_pos_qty = (
                self.state.metrics.current_asset_holdings
            )  # Bot's internal tracked position

        if capital <= Decimal("0") or price <= Decimal("0") or not self.market_info:
            self.logger.debug(
                "Insufficient capital, zero price, or no market info. Order size 0."
            )
            return Decimal("0")

        effective_capital = (
            capital * self.config.leverage
            if self.config.category in ["linear", "inverse"]
            else capital
        )

        # Calculate quantity based on percentage of balance
        base_order_value = (
            effective_capital * self.config.strategy.base_order_size_pct_of_balance
        )
        qty_from_base_pct = base_order_value / price

        max_order_value_abs = effective_capital * self.config.max_order_size_pct
        qty_from_max_pct = max_order_value_abs / price

        target_qty = min(qty_from_base_pct, qty_from_max_pct)

        # Apply max net exposure constraint if inventory strategy is enabled
        if (
            self.config.strategy.inventory.enabled
            and self.config.max_net_exposure_usd > Decimal("0")
        ):
            async with self.market_data_lock:
                current_mid_price = self.state.mid_price
            if current_mid_price == Decimal("0"):
                self.logger.warning(
                    "Mid-price is zero, cannot calculate max net exposure. Skipping exposure check."
                )
                return Decimal("0")

            max_allowed_pos_qty_abs = (
                self.config.max_net_exposure_usd / current_mid_price
            )

            if side == "Buy":
                # Limit buy quantity to not exceed max long exposure
                qty_to_reach_max_long = max_allowed_pos_qty_abs - metrics_pos_qty
                if qty_to_reach_max_long <= Decimal("0"):
                    self.logger.debug(
                        f"Cannot place buy order: Current position {metrics_pos_qty} already at or above max long exposure ({max_allowed_pos_qty_abs})."
                    )
                    return Decimal("0")
                target_qty = min(target_qty, qty_to_reach_max_long)
            else:  # Sell side
                # Limit sell quantity to not exceed max short exposure
                qty_to_reach_max_short = (
                    -max_allowed_pos_qty_abs - metrics_pos_qty
                )  # This will be negative if current position is not yet max short
                if qty_to_reach_max_short >= Decimal("0"):
                    self.logger.debug(
                        f"Cannot place sell order: Current position {metrics_pos_qty} already at or below max short exposure ({-max_allowed_pos_qty_abs})."
                    )
                    return Decimal("0")
                target_qty = min(target_qty, abs(qty_to_reach_max_short))

        if target_qty <= Decimal("0"):
            self.logger.debug(
                "Calculated target quantity is zero or negative after exposure adjustments. Order size 0."
            )
            return Decimal("0")

        # Quantize quantity to market precision
        qty = self.market_info.format_quantity(target_qty)

        # Enforce minimum order quantity and notional value
        if qty < self.market_info.min_order_qty:
            self.logger.debug(
                f"Calculated quantity {qty} is less than min_order_qty {self.market_info.min_order_qty}. Order size 0."
            )
            return Decimal("0")

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
        """Places a limit order on the exchange or simulates it in DRY_RUN/SIMULATION mode."""
        if not self.market_info:
            self.logger.error("Cannot place order, market info not available.")
            raise OrderPlacementError("Market information is not available.")

        # Quantize quantity and price
        qty_f, price_f = (
            self.market_info.format_quantity(quantity),
            self.market_info.format_price(price),
        )
        if qty_f <= Decimal("0") or price_f <= Decimal("0"):
            self.logger.warning(
                f"Attempted to place order with zero or negative quantity/price: Qty={qty_f}, Price={price_f}. Skipping."
            )
            return

        # Check final notional value against minimums
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
        order_link_id = f"mm_{side}_{int(time.time() * 1000)}"  # Unique client order ID

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

        # Add reduceOnly flag for derivatives if applicable
        if self.config.category in ["linear", "inverse"]:
            async with self.balance_position_lock:
                current_position = self.state.current_position_qty
            # Set reduceOnly if selling when long, or buying when short
            if (side == "Sell" and current_position > Decimal("0")) or (
                side == "Buy" and current_position < Decimal("0")
            ):
                params["reduceOnly"] = True
                self.logger.debug(
                    f"Setting reduceOnly=True for {side} order (current position: {current_position})."
                )

        if self.config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            # Simulate order placement
            oid = f"DRY_{side}_{int(time.time() * 1000)}"
            self.logger.info(
                f"{self.config.trading_mode}: Would place {side} order: ID={oid}, Qty={qty_f}, Price={price_f}"
            )
            async with self.active_orders_lock:
                self.state.active_orders[oid] = {
                    "side": side,
                    "price": price_f,
                    "qty": qty_f,
                    "status": "New",
                    "orderLinkId": order_link_id,
                    "symbol": self.config.symbol,
                    "reduceOnly": params.get("reduceOnly", False),
                }
            await self.db_manager.log_order_event(
                {**params, "orderId": oid, "orderStatus": "New"},
                f"{self.config.trading_mode} Order placed",
            )
            return

        # Place order via API
        result = await self.trading_client.place_order(params)
        if result and result.get("orderId"):
            oid = result["orderId"]
            self.logger.info(
                f"Placed {side} order: ID={oid}, Price={price_f}, Qty={qty_f}"
            )
            async with self.active_orders_lock:
                self.state.active_orders[oid] = {
                    "side": side,
                    "price": price_f,
                    "qty": qty_f,
                    "status": "New",
                    "orderLinkId": order_link_id,
                    "symbol": self.config.symbol,
                    "reduceOnly": params.get("reduceOnly", False),
                }
            await self.db_manager.log_order_event(
                {**params, "orderId": oid, "orderStatus": "New"}, "Order placed"
            )
        else:
            self.logger.error(
                f"Failed to place {side} order after retries. Params: {params}"
            )
            raise OrderPlacementError(f"Failed to place {side} order.")

    async def _reconcile_orders_on_startup(self):
        """
        Reconciles the bot's internal active orders with the exchange's open orders
        during startup to ensure consistency.
        """
        if self.config.trading_mode in ["DRY_RUN", "SIMULATION"]:
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
                f"Failed to fetch open orders from exchange during reconciliation: {e}. Proceeding with local state only.",
                exc_info=True,
            )
            exchange_orders = {}

        async with self.active_orders_lock:
            local_ids = set(self.state.active_orders.keys())
            exchange_ids = set(exchange_orders.keys())

            # Remove local orders not found on exchange
            for oid in local_ids - exchange_ids:
                self.logger.warning(
                    f"Local order {oid} not found on exchange. Removing from local state."
                )
                del self.state.active_orders[oid]

            # Add exchange orders not found locally
            for oid in exchange_ids - local_ids:
                o = exchange_orders[oid]
                self.logger.warning(
                    f"Exchange order {oid} ({o['side']} {o['qty']} @ {o['price']}) not in local state. Adding."
                )
                self.state.active_orders[oid] = {
                    "side": o["side"],
                    "price": Decimal(o["price"]),
                    "qty": Decimal(o["qty"]),
                    "status": o["orderStatus"],
                    "orderLinkId": o.get("orderLinkId"),
                    "symbol": o.get("symbol"),
                }

            # Update status for orders present in both
            for oid in local_ids.intersection(exchange_ids):
                local_order = self.state.active_orders[oid]
                exchange_order = exchange_orders[oid]
                if local_order["status"] != exchange_order["orderStatus"]:
                    self.logger.info(
                        f"Order {oid} status mismatch. Updating from {local_order['status']} to {exchange_order['orderStatus']}."
                    )
                    local_order["status"] = exchange_order["orderStatus"]

        self.logger.info(
            f"Order reconciliation complete. {len(self.state.active_orders)} active orders after reconciliation."
        )


# =====================================================================
# MAIN ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    bot = None
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
        OrderPlacementError,
        BybitAPIError,
        BybitRateLimitError,
        BybitInsufficientBalanceError,
    ) as e:
        error_type = type(e).__name__
        # Use bot's logger if available, otherwise get a default one
        logger = bot.logger if bot else logging.getLogger("MarketMakerBot")
        logger.critical(f"Critical Error ({error_type}): {e}", exc_info=True)
        print(f"\nCritical Error ({error_type}): {e}. Check log file for details.")
        sys.exit(1)
    except Exception as e:
        # Catch any other unexpected exceptions
        logger = bot.logger if bot else logging.getLogger("MarketMakerBot")
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
        print(
            f"\nAn unexpected critical error occurred during bot runtime: {e}. Check log file for details."
        )
        sys.exit(1)
