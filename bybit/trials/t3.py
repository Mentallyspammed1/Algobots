# ==============================================================================
# REQUIREMENTS (pip install ...)
# ==============================================================================
# pybit
# uvloop
# numpy
# redis
# prometheus-client
# cryptography
# python-json-logger
# aiofiles
# ==============================================================================

import asyncio
import hashlib
import json
import logging
import os
import queue
import signal
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, getcontext
from enum import Enum, auto
from functools import lru_cache, wraps
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from typing import Any

import aiofiles
import numpy as np
import prometheus_client
import redis
import uvloop
from cryptography.fernet import Fernet
from pybit.unified_trading import HTTP, WebSocket
from pythonjsonlogger import jsonlogger

# --- High-Performance Event Loop ---
# IMPROVEMENT: Explicitly set uvloop policy for maximum async performance.
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

# --- Global Decimal Precision ---
# IMPROVEMENT: High precision is good, 50 is a robust choice for financial calculations.
getcontext().prec = 50


# --- Environment Variable Parsers ---
def _parse_env_bool(var_name: str, default: bool = False) -> bool:
    """Parses a boolean environment variable."""
    return os.getenv(var_name, str(default)).lower() == "true"


def _parse_env_int(var_name: str, default: int = 0) -> int:
    """Parses an integer environment variable."""
    try:
        return int(os.getenv(var_name, str(default)))
    except ValueError:
        logger.warning(f"Invalid integer for {var_name}, using default: {default}")
        return default


# --- Thread-Safe Singleton Pattern ---
class SingletonMeta(type):
    """Thread-safe Singleton metaclass."""

    _instances: dict[type, Any] = {}
    _lock: threading.Lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
        return cls._instances[cls]


# --- Advanced Retry Decorator ---
class RetryStrategy(Enum):
    """Retry strategies for different scenarios."""

    LINEAR = auto()
    EXPONENTIAL = auto()
    FIBONACCI = auto()


def advanced_retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
    max_delay: float = 60.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
):
    """Advanced retry decorator with multiple strategies."""

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            delays: list[float] = []
            if strategy == RetryStrategy.LINEAR:
                delays = [initial_delay] * max_retries
            elif strategy == RetryStrategy.EXPONENTIAL:
                delays = [
                    min(initial_delay * (2**i), max_delay) for i in range(max_retries)
                ]
            elif strategy == RetryStrategy.FIBONACCI:
                a, b = initial_delay, initial_delay
                for _ in range(max_retries):
                    delays.append(min(a, max_delay))
                    a, b = b, a + b

            for attempt, delay in enumerate(delays):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == len(delays) - 1:
                        logger.error(
                            f"Function {func.__name__} failed after {attempt + 1} attempts: {e}",
                            exc_info=True,
                        )
                        raise
                    logger.warning(
                        f"Attempt {attempt + 1}/{len(delays)} failed for {func.__name__}: {e}. Retrying in {delay:.2f}s...",
                    )
                    await asyncio.sleep(delay)
            return None  # Should ideally not be reached if max_retries > 0 and final attempt raises.

        # Sync wrapper is not typically used for Bybit API calls which are async.
        # It's kept for completeness but won't be called in this bot's structure.
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            raise NotImplementedError(
                "Sync wrapper for advanced_retry is not implemented for this context.",
            )

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# --- Enhanced Decimal Parser ---
# IMPROVEMENT #3: More robust Decimal parser with direct type handling and better cleaning, with exc_info on debug.
@lru_cache(maxsize=2048)
def _dec(value: Any, default: Decimal = Decimal(0)) -> Decimal:
    """Robust Decimal parser with caching, direct type handling, and validation."""
    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        # Convert float to string first to avoid floating point precision issues
        return Decimal(str(value))
    try:
        # Clean common currency/formatting symbols
        cleaned = str(value).strip().replace(",", "").replace("$", "").replace(" ", "")
        return Decimal(cleaned)
    except (InvalidOperation, ValueError, TypeError, AttributeError) as e:
        logger.debug(
            f"Decimal conversion failed for value: '{value}' (Type: {type(value)}): {e}",
            exc_info=True,
        )
        return default


# --- Configuration Class ---
@dataclass
class BotConfiguration:
    """Centralized bot configuration with validation and paper trading mode."""

    api_key: str
    api_secret: str
    use_testnet: bool = False
    paper_trading: bool = False  # IMPROVEMENT #4: Paper trading mode
    max_reconnect_attempts: int = 5
    ws_ping_interval: int = 20
    ws_liveness_timeout: int = 60  # IMPROVEMENT #9: Timeout for WebSocket liveness
    log_level: str = "INFO"
    max_open_positions: int = 5
    rate_limit_per_second: int = 10
    redis_host: str = "localhost"
    redis_port: int = 6379
    enable_metrics: bool = True
    enable_encryption: bool = True
    strategy_params_file: str = "strategy_params.json"
    api_call_timeout: float = 10.0  # IMPROVEMENT #2: Timeout for API calls

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.paper_trading and (not self.api_key or not self.api_secret):
            raise ValueError("API credentials are required for live trading.")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be at least 1.")
        if self.rate_limit_per_second < 1:
            raise ValueError("rate_limit_per_second must be at least 1.")
        if self.ws_ping_interval < 5:
            logger.warning("ws_ping_interval less than 5s might be too frequent.")
        if self.ws_liveness_timeout < self.ws_ping_interval * 2:
            logger.warning(
                "ws_liveness_timeout should ideally be at least twice ws_ping_interval.",
            )

        if self.paper_trading:
            logger.warning(
                "PAPER TRADING MODE IS ENABLED. NO REAL ORDERS WILL BE PLACED.",
            )


# --- Logging Setup ---
# IMPROVEMENT: Centralized logging setup in a dedicated function.
def setup_logging(log_level: str, log_queue: queue.Queue) -> QueueListener:
    """Configures structured, thread-safe, and asynchronous logging."""

    class CustomJsonFormatter(jsonlogger.JsonFormatter):
        def add_fields(self, log_record, record, message_dict):
            super().add_fields(log_record, record, message_dict)
            log_record["timestamp"] = (
                datetime.utcnow().isoformat() + "Z"
            )  # Consistent UTC
            log_record["level"] = record.levelname
            log_record["name"] = record.name
            log_record["module"] = record.module
            log_record["function"] = record.funcName
            log_record["line"] = record.lineno

    queue_handler = QueueHandler(log_queue)

    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    )
    console_handler.setFormatter(console_formatter)

    file_handler = RotatingFileHandler(
        "bybit_trading_bot.log", maxBytes=50 * 1024 * 1024, backupCount=10,
    )
    # Use the custom JSON formatter for file logs
    file_handler.setFormatter(
        CustomJsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(module)s %(funcName)s %(line)s %(message)s",
        ),
    )

    # QueueListener handles passing logs from the queue to the actual handlers
    listener = QueueListener(
        log_queue, console_handler, file_handler, respect_handler_level=True,
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))
    root_logger.addHandler(queue_handler)  # All log records go to the queue handler

    return listener


# --- Load Configuration & Initialize Logging ---
config = BotConfiguration(
    api_key=os.getenv("BYBIT_API_KEY", ""),
    api_secret=os.getenv("BYBIT_API_SECRET", ""),
    use_testnet=_parse_env_bool("BYBIT_USE_TESTNET", False),  # IMPROVEMENT #1
    paper_trading=_parse_env_bool("PAPER_TRADING", False),  # IMPROVEMENT #1
    max_reconnect_attempts=_parse_env_int(
        "MAX_RECONNECT_ATTEMPTS", 5,
    ),  # IMPROVEMENT #1
    ws_ping_interval=_parse_env_int("WS_PING_INTERVAL", 20),
    ws_liveness_timeout=_parse_env_int("WS_LIVENESS_TIMEOUT", 60),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    max_open_positions=_parse_env_int("MAX_OPEN_POSITIONS", 5),
    rate_limit_per_second=_parse_env_int("RATE_LIMIT_PER_SECOND", 10),
    redis_host=os.getenv("REDIS_HOST", "localhost"),
    redis_port=_parse_env_int("REDIS_PORT", 6379),
    enable_metrics=_parse_env_bool("ENABLE_METRICS", True),
    enable_encryption=_parse_env_bool("ENABLE_ENCRYPTION", True),
    api_call_timeout=float(os.getenv("API_CALL_TIMEOUT", "10.0")),
)

log_queue = queue.Queue(-1)  # Infinite size queue
log_listener = setup_logging(config.log_level, log_queue)
log_listener.start()
logger = logging.getLogger(__name__)

# --- Prometheus Metrics ---
if config.enable_metrics:
    metrics = {
        "total_trades": prometheus_client.Counter(
            "bot_total_trades", "Total number of trades initiated", ["mode"],
        ),  # IMPROVEMENT #13
        "successful_trades": prometheus_client.Counter(
            "bot_successful_trades", "Number of successful trades", ["mode"],
        ),  # IMPROVEMENT #13
        "failed_trades": prometheus_client.Counter(
            "bot_failed_trades", "Number of failed trades", ["mode"],
        ),  # IMPROVEMENT #13
        "api_calls": prometheus_client.Counter(
            "bot_api_calls", "Total API calls made", ["endpoint"],
        ),
        "ws_messages": prometheus_client.Counter(
            "bot_ws_messages", "WebSocket messages received", ["channel"],
        ),
        "order_latency": prometheus_client.Histogram(
            "bot_order_latency_seconds", "Order execution latency in seconds",
        ),
        "pnl": prometheus_client.Gauge("bot_pnl_total", "Current total P&L"),
        "open_positions": prometheus_client.Gauge(
            "bot_open_positions", "Number of open positions",
        ),
    }


# --- Performance Metrics Dataclass ---
@dataclass
class EnhancedPerformanceMetrics:
    """Advanced performance tracking with statistics."""

    # IMPROVEMENT #8: Use __slots__ for memory optimization on high-frequency objects.
    __slots__ = (
        "avg_loss",
        "avg_win",
        "daily_pnl",
        "failed_trades",
        "last_update",
        "max_drawdown",
        "realized_pnl",
        "sharpe_ratio",
        "start_time",
        "successful_trades",
        "total_trades",
        "total_volume",
        "trade_history",
        "unrealized_pnl",
        "win_rate",
    )

    total_trades: int = 0
    successful_trades: int = 0
    failed_trades: int = 0
    total_volume: Decimal = field(default_factory=Decimal)
    realized_pnl: Decimal = field(default_factory=Decimal)
    unrealized_pnl: Decimal = field(default_factory=Decimal)
    max_drawdown: Decimal = field(default_factory=Decimal)
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    avg_win: Decimal = field(default_factory=Decimal)
    avg_loss: Decimal = field(default_factory=Decimal)
    trade_history: list[dict] = field(default_factory=list)
    daily_pnl: dict[str, Decimal] = field(default_factory=dict)
    start_time: datetime = field(
        default_factory=datetime.utcnow,
    )  # IMPROVEMENT #11: UTC
    last_update: datetime = field(
        default_factory=datetime.utcnow,
    )  # IMPROVEMENT #11: UTC

    def update(self):
        """Update metrics timestamp."""
        self.last_update = datetime.utcnow()  # IMPROVEMENT #11: UTC
        self._calculate_statistics()

    def _calculate_statistics(self):
        """Calculate advanced statistics."""
        if self.total_trades > 0:
            self.win_rate = (self.successful_trades / self.total_trades) * 100

            # Calculate Sharpe ratio (simplified)
            if len(self.daily_pnl) > 1:
                returns = list(self.daily_pnl.values())
                if returns:
                    # Convert Decimal to float for numpy operations
                    float_returns = [float(r) for r in returns]
                    avg_return = np.mean(float_returns)
                    std_return = np.std(float_returns)
                    if std_return > 0:
                        self.sharpe_ratio = (avg_return / std_return) * np.sqrt(
                            252,
                        )  # Annualized

    def add_trade(self, trade: dict):
        """Add a trade to history and update metrics."""
        self.trade_history.append(trade)
        self.total_trades += 1

        pnl = _dec(trade.get("pnl", Decimal(0)))

        # Determine current trading mode for metrics
        trading_mode = "paper" if config.paper_trading else "live"

        if pnl > 0:
            self.successful_trades += 1
            self.avg_win = (
                (self.avg_win * (self.successful_trades - 1) + pnl)
                / self.successful_trades
                if self.successful_trades > 0
                else pnl
            )
        else:
            self.failed_trades += 1
            self.avg_loss = (
                (self.avg_loss * (self.failed_trades - 1) + abs(pnl))
                / self.failed_trades
                if self.failed_trades > 0
                else abs(pnl)
            )

        self.realized_pnl += pnl
        self.total_volume += _dec(trade.get("volume", Decimal(0)))

        # Update daily P&L
        today = datetime.utcnow().date().isoformat()  # IMPROVEMENT #11: UTC
        self.daily_pnl[today] = self.daily_pnl.get(today, Decimal(0)) + pnl

        # Update max drawdown (simple peak-to-trough)
        self.max_drawdown = min(self.max_drawdown, self.realized_pnl)

        self.update()  # Update timestamp and recalculate derived stats

        # Update Prometheus metrics if enabled
        if config.enable_metrics:
            metrics["total_trades"].labels(mode=trading_mode).inc()
            if pnl > 0:
                metrics["successful_trades"].labels(mode=trading_mode).inc()
            else:
                metrics["failed_trades"].labels(mode=trading_mode).inc()
            metrics["pnl"].set(float(self.realized_pnl))

    def get_statistics(self) -> dict:
        """Get comprehensive statistics."""
        return {
            "total_trades": self.total_trades,
            "win_rate": f"{self.win_rate:.2f}%",
            "realized_pnl": float(self.realized_pnl),
            "unrealized_pnl": float(self.unrealized_pnl),
            "max_drawdown": float(self.max_drawdown),
            "sharpe_ratio": self.sharpe_ratio,
            "avg_win": float(self.avg_win),
            "avg_loss": float(self.avg_loss),
            "total_volume": float(self.total_volume),
            "uptime": str(datetime.utcnow() - self.start_time),  # IMPROVEMENT #11: UTC
        }


# --- Order & Position Management ---
class OrderType(Enum):
    MARKET = "Market"
    LIMIT = "Limit"
    # STOP = "Stop" # Not always directly supported as primary order types via unified API, use byPrice/triggerPrice
    # STOP_LIMIT = "StopLimit"
    # TAKE_PROFIT = "TakeProfit"
    # TAKE_PROFIT_LIMIT = "TakeProfitLimit"


class OrderSide(Enum):
    BUY = "Buy"
    SELL = "Sell"


@dataclass
class Order:
    """Represents a trade order with validation."""

    symbol: str
    side: OrderSide
    order_type: OrderType
    qty: Decimal
    price: Decimal | None = None  # Required for LIMIT
    time_in_force: str = "GTC"  # Good-Till-Canceled
    reduce_only: bool = False
    order_id: str | None = None
    client_order_id: str | None = field(
        default_factory=lambda: f"bot-{int(time.time() * 1000)}_{os.getpid()}",
    )  # Add PID for uniqueness
    created_at: datetime = field(
        default_factory=datetime.utcnow,
    )  # IMPROVEMENT #11: UTC

    def __post_init__(self):
        """Validate order parameters."""
        if self.qty <= 0:
            raise ValueError("Order quantity must be positive.")
        if self.order_type == OrderType.LIMIT and not self.price:
            raise ValueError(f"{self.order_type.value} order requires a price.")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Bybit API calls."""
        params: dict[str, Any] = {
            "symbol": self.symbol,
            "side": self.side.value,
            "orderType": self.order_type.value,
            "qty": str(self.qty),  # Quantity as string
            "timeInForce": self.time_in_force,
            "reduceOnly": 1 if self.reduce_only else 0,  # Bybit expects 0 or 1
            "orderLinkId": self.client_order_id,
            "isLeverage": 1,  # Always use leverage for derivatives
        }
        if self.price is not None:
            params["price"] = str(self.price)  # Price as string
        return params


@dataclass
class Position:
    """Represents an open position with P&L tracking."""

    # IMPROVEMENT #8: Use __slots__ for memory optimization on high-frequency objects.
    __slots__ = (
        "entry_price",
        "last_update",
        "leverage",
        "margin",
        "mark_price",
        "realized_pnl",
        "side",
        "size",
        "symbol",
        "unrealized_pnl",
    )
    symbol: str
    side: str  # "Buy" or "Sell"
    size: Decimal
    entry_price: Decimal
    mark_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    margin: Decimal
    leverage: int
    last_update: datetime = field(
        default_factory=datetime.utcnow,
    )  # IMPROVEMENT #11: UTC

    def get_pnl_percentage(self) -> float:
        """Calculate P&L percentage based on entry price."""
        if self.entry_price == 0 or self.size == 0:
            return 0.0
        # For long: (current_price - entry_price) / entry_price
        # For short: (entry_price - current_price) / entry_price

        current_value = self.size * self.mark_price
        entry_value = self.size * self.entry_price

        if self.side == "Buy":
            pnl_usd = current_value - entry_value
        else:  # Sell (short)
            pnl_usd = entry_value - current_value

        return float(pnl_usd / entry_value) * 100

    def should_close(
        self, take_profit_pct: float = 2.0, stop_loss_pct: float = 1.0,
    ) -> str | None:
        """Determine if position should be closed based on P&L percentages."""
        pnl_pct = self.get_pnl_percentage()
        if pnl_pct >= take_profit_pct:
            return "TAKE_PROFIT"
        if pnl_pct <= -stop_loss_pct:
            return "STOP_LOSS"
        return None


# --- Risk & Security Management ---
class RiskManager:
    """Comprehensive risk management system."""

    def __init__(
        self, max_position_size: Decimal, max_leverage: int, max_drawdown: Decimal,
    ):
        self.max_position_size = max_position_size
        self.max_leverage = max_leverage
        self.max_drawdown = max_drawdown
        self.current_exposure: Decimal = Decimal(0)
        # self.daily_loss_limit: Decimal = Decimal(0) # Not actively used yet
        self.position_limits: dict[str, Decimal] = {}  # Per-symbol limits

    # IMPROVEMENT #7: Check against available balance for a more accurate margin check, and use symbol_info for min/step.
    def check_order_risk(
        self, order: Order, account_info: dict, symbol_info: dict[str, Any],
    ) -> tuple[bool, str]:
        """Check if an order meets risk requirements using available balance and symbol info."""
        # Get available balance from account_info, assuming USDT as base currency
        available_balance = _dec(account_info.get("totalAvailableBalance", 0))

        # 1. Validate against symbol info
        info = symbol_info.get(order.symbol)
        if not info:
            return (
                False,
                f"Symbol information not available for {order.symbol}. Cannot validate order.",
            )

        # Apply quantity steps and min qty
        qty_step = _dec(info.get("qtyStep", "1"))
        min_qty = _dec(info.get("minOrderQty", "0"))

        # Round order quantity to nearest step
        if order.qty % qty_step != 0:
            return (
                False,
                f"Order quantity {order.qty} for {order.symbol} is not a multiple of qtyStep {qty_step}.",
            )
        if order.qty < min_qty:
            return (
                False,
                f"Order quantity {order.qty} for {order.symbol} is below minimum {min_qty}.",
            )

        # 2. Check maximum position size limit
        if order.qty > self.max_position_size:
            return (
                False,
                f"Order quantity {order.qty} exceeds general max position size {self.max_position_size}.",
            )

        # 3. Check symbol-specific limit
        symbol_limit = self.position_limits.get(order.symbol, self.max_position_size)
        if order.qty > symbol_limit:
            return (
                False,
                f"Order quantity {order.qty} exceeds symbol-specific limit for {order.symbol}: {symbol_limit}.",
            )

        # 4. Check margin usage (for limit/market orders, estimate required margin)
        # For market orders, use best ask/bid for estimation if order.price is None
        estimated_price = order.price
        if order.order_type == OrderType.MARKET and estimated_price is None:
            # Try to get current price from market data
            market_data = self.market_data.get(order.symbol)
            if market_data and "ticker" in market_data:
                estimated_price = _dec(market_data["ticker"].get("lastPrice"))
            if estimated_price == 0:  # Fallback if no market data price
                return False, f"Cannot estimate price for market order {order.symbol}."

        position_value = order.qty * estimated_price if estimated_price else Decimal(0)

        # If reducing only, margin check might not be critical, but better to be safe.
        if not order.reduce_only and position_value > 0:
            # Assuming isolated margin for simplicity, initial margin required is position_value / leverage
            # Pybit API docs state "initial margin" as order_value / leverage, where leverage is set on position.
            # We assume a default max_leverage for new orders.
            required_margin = position_value / self.max_leverage
            # For a new order, ensure the required margin doesn't exceed a prudent percentage of available balance.
            if required_margin > available_balance * Decimal(
                "0.8",
            ):  # Max 80% of available balance
                return (
                    False,
                    f"Order would use too much margin. Required: {required_margin:.2f}, Available: {available_balance:.2f}.",
                )

        return True, "Order approved"

    def update_exposure(self, positions: list[Position]):
        """Update current market exposure."""
        self.current_exposure = sum(pos.size * pos.mark_price for pos in positions)

    def get_position_size(
        self, account_balance: Decimal, risk_per_trade: Decimal = Decimal("0.02"),
    ) -> Decimal:
        """Calculate appropriate position size based on a simplified Kelly Criterion or fixed risk."""
        # Simplified Kelly Criterion: Risk per trade defines position sizing
        # Example: if 2% of account balance is risked, and stop loss is 1%, then position size is 2% / 1% * (account_balance)
        # For this simplified version, let's just use a percentage of available balance up to max_position_size.

        calculated_size = (
            account_balance * risk_per_trade * self.max_leverage
        )  # Max leverage can be used for max position size calc
        return min(calculated_size, self.max_position_size)


# IMPROVEMENT #6: Cache Manager with explicit Redis connection closure
class CacheManager(metaclass=SingletonMeta):
    """Distributed cache manager using Redis, with fallback to in-memory."""

    def __init__(self):
        self.redis_client: redis.Redis | None = None
        self.enabled = False
        self.memory_cache: dict[str, Any] = {}
        self.cache_timestamps: dict[str, datetime] = {}

        if config.redis_host and config.redis_port:
            try:
                self.redis_client = redis.Redis(
                    host=config.redis_host,
                    port=config.redis_port,
                    decode_responses=True,
                    socket_connect_timeout=2,  # Short timeout for initial connection
                    socket_keepalive=True,
                    socket_keepalive_options={
                        1: 30,  # TCP_KEEPIDLE (seconds of inactivity before sending keepalive probe)
                        2: 10,  # TCP_KEEPINTVL (seconds between keepalive probes)
                        3: 3,  # TCP_KEEPCNT (number of probes before declaring connection dead)
                    },
                )
                self.redis_client.ping()
                self.enabled = True
                logger.info("Redis cache connected successfully.")
            except redis.exceptions.ConnectionError as e:
                logger.warning(
                    f"Redis not available at {config.redis_host}:{config.redis_port}: {e}. Falling back to in-memory cache.",
                )
            except Exception as e:
                logger.error(
                    f"Failed to initialize Redis client: {e}. Falling back to in-memory cache.",
                )

    async def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache."""
        if self.enabled and self.redis_client:
            try:
                value = await asyncio.to_thread(self.redis_client.get, key)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.debug(f"Redis cache get error for key '{key}': {e}")
        else:  # Fallback to in-memory cache
            if key in self.cache_timestamps:
                # Default 5 min expiry for in-memory cache
                if (
                    datetime.utcnow() - self.cache_timestamps[key]
                ).total_seconds() > 300:
                    del self.memory_cache[key]
                    del self.cache_timestamps[key]
                    return default
            return self.memory_cache.get(key, default)
        return default

    async def set(self, key: str, value: Any, expire: int = 300):
        """Set value in cache with expiration (default 5 minutes)."""
        if self.enabled and self.redis_client:
            try:
                await asyncio.to_thread(
                    self.redis_client.setex, key, expire, json.dumps(value),
                )
            except Exception as e:
                logger.debug(f"Redis cache set error for key '{key}': {e}")
        else:  # Fallback to in-memory cache
            self.memory_cache[key] = value
            self.cache_timestamps[key] = datetime.utcnow()  # IMPROVEMENT #11: UTC

    async def delete(self, key: str):
        """Delete value from cache."""
        if self.enabled and self.redis_client:
            try:
                await asyncio.to_thread(self.redis_client.delete, key)
            except Exception as e:
                logger.debug(f"Redis cache delete error for key '{key}': {e}")
        else:
            self.memory_cache.pop(key, None)
            self.cache_timestamps.pop(key, None)

    async def _cache_maintenance(self, stop_event: threading.Event):
        """IMPROVEMENT #14: Periodic in-memory cache cleanup if Redis is not used."""
        if self.enabled:
            return  # Only relevant if Redis is disabled

        logger.info("Starting in-memory cache maintenance task...")
        while not stop_event.is_set():
            await asyncio.sleep(3600)  # Run hourly
            now = datetime.utcnow()
            keys_to_delete = [
                k
                for k, timestamp in self.cache_timestamps.items()
                if (now - timestamp).total_seconds()
                > 3600  # 1 hour expiry for background cleanup
            ]
            for key in keys_to_delete:
                self.memory_cache.pop(key, None)
                self.cache_timestamps.pop(key, None)
                logger.debug(f"Cleaned up expired in-memory cache entry: {key}")
        logger.info("In-memory cache maintenance task stopped.")

    def close(self):
        """IMPROVEMENT #6: Explicitly close the Redis connection."""
        if self.enabled and self.redis_client:
            try:
                self.redis_client.close()
                logger.info("Redis client connection closed.")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")


class SecurityManager(metaclass=SingletonMeta):
    """Handles encryption and security."""

    def __init__(self):
        self.fernet: Fernet | None = None
        if config.enable_encryption:
            key_str = os.getenv("ENCRYPTION_KEY")
            if not key_str:
                key = Fernet.generate_key()
                logger.warning(
                    f"ENCRYPTION_KEY environment variable not set. Generated a new temporary key: {key.decode()}. For production, set this environment variable for persistent encryption.",
                )
            else:
                try:
                    key = key_str.encode()
                    self.fernet = Fernet(key)
                except Exception as e:
                    logger.error(
                        f"Failed to initialize Fernet with provided ENCRYPTION_KEY: {e}. Encryption disabled.",
                        exc_info=True,
                    )
                    self.fernet = None
            if self.fernet:
                logger.info("Encryption enabled.")
        else:
            logger.info("Encryption disabled by configuration.")

    def encrypt(self, data: str) -> str:
        """Encrypt sensitive data."""
        if self.fernet:
            return self.fernet.encrypt(data.encode()).decode()
        return data  # Return original if encryption is off

    def decrypt(self, data: str) -> str:
        """Decrypt sensitive data."""
        if self.fernet:
            try:
                return self.fernet.decrypt(data.encode()).decode()
            except Exception as e:
                logger.error(
                    f"Failed to decrypt data: {e}. Returning original.", exc_info=True,
                )
                return data
        return data  # Return original if encryption is off

    def hash_api_key(self, api_key: str) -> str:
        """Create a short hash of API key for logging purposes (not for security)."""
        return hashlib.sha256(api_key.encode()).hexdigest()[:8]


# IMPROVEMENT #15: Simplified WebSocket Manager without a pool (Pybit handles multiplexing)
class EnhancedWebSocketManager:
    """Advanced WebSocket management with liveness checks and auto-reconnection."""

    def __init__(
        self, api_key: str, api_secret: str, testnet: bool, paper_trading: bool,
    ):
        self._testnet = testnet
        self._api_key = api_key
        self._api_secret = api_secret
        self._paper_trading = paper_trading

        self.ws_public: WebSocket | None = None
        self.ws_private: WebSocket | None = None

        self.market_data: dict[str, Any] = {}  # Stores orderbook, ticker, trades etc.
        self.positions: dict[str, Position] = {}  # Live positions from WS
        self.orders: dict[str, dict] = {}  # Live orders from WS

        self._last_message_time = time.monotonic()  # For liveness check
        self._reconnect_lock = asyncio.Lock()
        self._subscriptions: set[str] = set()  # To resubscribe on reconnect
        self._is_running = asyncio.Event()  # For graceful shutdown of internal loops

        # Performance tracking
        self._message_latency: deque = deque(maxlen=100)
        self._message_count = 0
        self._error_count = 0

    async def initialize(self):
        """Initialize WebSocket connections and start monitoring tasks."""
        logger.info("Initializing WebSocket Manager...")
        self.ws_public = WebSocket(testnet=self._testnet, channel_type="linear")
        if not self._paper_trading:
            self.ws_private = WebSocket(
                testnet=self._testnet,
                channel_type="private",
                api_key=self._api_key,
                api_secret=self._api_secret,
            )

        self._is_running.set()  # Mark as running
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._liveness_check_loop())
        logger.info("WebSocket Manager initialized.")

    async def _liveness_check_loop(self):
        """IMPROVEMENT #9: Periodically checks for message reception to detect zombie connections."""
        logger.debug("Starting WebSocket liveness check loop.")
        while self._is_running.is_set():
            await self._is_running.wait_for(
                config.ws_liveness_timeout,
            )  # Wait responsive to shutdown
            if (
                not self._is_running.is_set()
            ):  # Check again after wait_for for immediate shutdown
                break

            if time.monotonic() - self._last_message_time > config.ws_liveness_timeout:
                logger.warning(
                    "No WebSocket message received recently. Triggering reconnect.",
                )
                await self.reconnect()
        logger.debug("WebSocket liveness check loop stopped.")

    async def _heartbeat_loop(self):
        """Periodically send pings to maintain WebSocket connections."""
        logger.debug("Starting WebSocket heartbeat loop.")
        while self._is_running.is_set():
            try:
                if self.ws_public:
                    self.ws_public.ping()
                if self.ws_private:
                    self.ws_private.ping()
                await self._is_running.wait_for(
                    config.ws_ping_interval,
                )  # Wait responsive to shutdown
            except asyncio.CancelledError:
                logger.debug("Heartbeat loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}. Will retry.", exc_info=True)
                await asyncio.sleep(5)  # Prevent busy-loop on error
        logger.debug("WebSocket heartbeat loop stopped.")

    @advanced_retry(
        max_retries=config.max_reconnect_attempts, strategy=RetryStrategy.EXPONENTIAL,
    )
    async def reconnect(self):
        """Reconnects WebSockets and re-subscribes to all channels."""
        async with self._reconnect_lock:
            logger.info("Attempting to reconnect WebSockets...")
            # Close existing connections first
            if self.ws_public:
                self.ws_public.exit()
            if self.ws_private:
                self.ws_private.exit()

            # Create new instances to ensure clean state
            self.ws_public = WebSocket(testnet=self._testnet, channel_type="linear")
            if not self._paper_trading:
                self.ws_private = WebSocket(
                    testnet=self._testnet,
                    channel_type="private",
                    api_key=self._api_key,
                    api_secret=self._api_secret,
                )

            # Resubscribe to all previously subscribed channels
            current_subscriptions = list(
                self._subscriptions,
            )  # Copy to avoid modification during iteration
            self._subscriptions.clear()  # Clear and re-add as subscriptions are re-established
            for sub_key in current_subscriptions:
                channel, symbol_str = sub_key.split(":", 1)
                symbol = symbol_str if symbol_str != "None" else None
                await self.subscribe(
                    channel, symbol,
                )  # This will add them back to _subscriptions

            self._last_message_time = time.monotonic()  # Reset liveness timer
            logger.info("WebSocket reconnected and subscriptions restored.")

    async def subscribe(self, channel: str, symbol: str | None = None):
        """Subscribe to a channel with retry logic."""
        subscription_key = f"{channel}:{symbol}"
        if subscription_key in self._subscriptions:
            logger.debug(f"Already subscribed to {subscription_key}.")
            return

        callback = self._create_callback(channel, symbol)

        ws_instance: WebSocket | None = None
        if channel in ["position", "order", "execution"]:
            ws_instance = self.ws_private
        else:
            ws_instance = self.ws_public

        if not ws_instance:
            logger.warning(
                f"Cannot subscribe to channel '{channel}' (no {'private' if channel in ['position', 'order', 'execution'] else 'public'} WebSocket client available).",
            )
            return

        try:
            if channel == "orderbook":
                ws_instance.orderbook_stream(depth=50, symbol=symbol, callback=callback)
            elif channel == "trade":
                ws_instance.trade_stream(symbol=symbol, callback=callback)
            elif channel == "ticker":
                ws_instance.ticker_stream(symbol=symbol, callback=callback)
            elif channel == "position":
                ws_instance.position_stream(callback=callback)
            elif channel == "order":
                ws_instance.order_stream(callback=callback)
            elif channel == "execution":
                ws_instance.execution_stream(callback=callback)
            else:
                logger.error(f"Unknown channel to subscribe: {channel}")
                return

            self._subscriptions.add(subscription_key)
            logger.info(f"Subscribed to {subscription_key}.")

        except Exception as e:
            logger.error(
                f"Subscription failed for {subscription_key}: {e}", exc_info=True,
            )
            raise  # Re-raise to trigger advanced_retry

    def _create_callback(self, channel: str, symbol: str | None):
        """Creates a specialized callback function for WebSocket messages."""

        def callback(message: dict):
            self._last_message_time = time.monotonic()  # Update liveness timestamp
            try:
                # Track message latency
                receive_time = datetime.utcnow()  # IMPROVEMENT #11: UTC
                if "ts" in message:
                    # Bybit WS timestamps are in milliseconds
                    send_time = datetime.fromtimestamp(
                        message["ts"] / 1000, tz=None,
                    )  # Assume UTC from exchange
                    latency = (receive_time - send_time).total_seconds()
                    self._message_latency.append(latency)

                self._message_count += 1

                # Update Prometheus metrics with channel label
                if config.enable_metrics:
                    metrics["ws_messages"].labels(channel=channel).inc()

                # Process message based on channel
                if channel == "orderbook":
                    self._handle_orderbook(message, symbol)
                elif channel == "trade":
                    self._handle_trade(message, symbol)
                elif channel == "ticker":
                    self._handle_ticker(message, symbol)
                elif channel == "position":
                    self._handle_position(message)
                elif channel == "order":
                    self._handle_order(message)
                elif channel == "execution":
                    self._handle_execution(message)

            except Exception as e:
                self._error_count += 1
                logger.error(
                    f"Error processing {channel} message for symbol {symbol}: {e}",
                    exc_info=True,
                )

        return callback

    def _handle_orderbook(self, message: dict, symbol: str):
        """Process orderbook updates."""
        data = message.get("data", {})
        if not data or not symbol:
            logger.debug(f"Received empty or invalid orderbook data: {message}")
            return

        # Check for update sequence (u is updateId, U is prevUpdateId)
        # This basic check assumes "partial" or "delta" updates follow sequence.
        # For full orderbook management, a proper diff application is needed.
        current_update_id = _dec(data.get("u", 0))
        last_update_id = (
            self.market_data.get(symbol, {}).get("orderbook", {}).get("update_id", 0)
        )

        # For partial updates, it's crucial that U <= last_update_id < u.
        # For snapshot (partial=False or initial), u is just the current ID.
        if "U" in data and _dec(data["U"]) > last_update_id:
            logger.warning(
                f"Orderbook update for {symbol} out of sequence. Last: {last_update_id}, Prev: {data['U']}, Current: {current_update_id}. Requesting new snapshot.",
            )
            # In a real system, you might trigger a resync/snapshot request here.
            # For simplicity, we just log and process the current message.

        self.market_data.setdefault(symbol, {})["orderbook"] = {
            "bids": [[_dec(p), _dec(q)] for p, q in data.get("b", [])],
            "asks": [[_dec(p), _dec(q)] for p, q in data.get("a", [])],
            "timestamp": _dec(message.get("ts", 0)),
            "update_id": current_update_id,
        }
        self.market_data[symbol]["last_update"] = (
            datetime.utcnow()
        )  # IMPROVEMENT #11: UTC

        # Cache the data (async task)
        asyncio.create_task(
            CacheManager().set(
                f"orderbook:{symbol}", self.market_data[symbol]["orderbook"], expire=60,
            ),
        )

    def _handle_trade(self, message: dict, symbol: str):
        """Process trade updates."""
        if not symbol:
            return
        for trade in message.get("data", []):
            market_data = self.market_data.setdefault(symbol, {})

            if "trades" not in market_data:
                market_data["trades"] = deque(maxlen=100)  # Keep last 100 trades

            market_data["trades"].append(
                {
                    "price": _dec(trade.get("p")),
                    "qty": _dec(trade.get("v")),
                    "side": trade.get("S"),  # "Buy" or "Sell"
                    "timestamp": _dec(trade.get("T")),
                },
            )
            market_data["last_trade"] = trade
            market_data["last_update"] = datetime.utcnow()  # IMPROVEMENT #11: UTC

    def _handle_ticker(self, message: dict, symbol: str):
        """Process ticker updates."""
        data = message.get("data", {})
        if not data or not symbol:
            return
        self.market_data.setdefault(symbol, {})["ticker"] = {
            "last_price": _dec(data.get("lastPrice")),
            "bid": _dec(data.get("bid1Price")),
            "ask": _dec(data.get("ask1Price")),
            "volume_24h": _dec(data.get("volume24h")),
            "turnover_24h": _dec(data.get("turnover24h")),
            "high_24h": _dec(data.get("highPrice24h")),
            "low_24h": _dec(data.get("lowPrice24h")),
            "prev_close": _dec(data.get("prevPrice24h")),
        }
        self.market_data[symbol]["last_update"] = (
            datetime.utcnow()
        )  # IMPROVEMENT #11: UTC

    def _handle_position(self, message: dict):
        """Process position updates."""
        for pos_data in message.get("data", []):
            symbol = pos_data.get("symbol")
            if symbol:
                position = Position(
                    symbol=symbol,
                    side=pos_data.get("side"),
                    size=_dec(pos_data.get("size")),
                    entry_price=_dec(pos_data.get("avgPrice")),
                    mark_price=_dec(pos_data.get("markPrice")),
                    unrealized_pnl=_dec(pos_data.get("unrealisedPnl")),
                    realized_pnl=_dec(pos_data.get("realisedPnl")),
                    margin=_dec(pos_data.get("positionIM")),
                    leverage=int(pos_data.get("leverage", 1)),
                )
                self.positions[symbol] = position

                # Update metrics
                if config.enable_metrics:
                    metrics["open_positions"].set(
                        len([p for p in self.positions.values() if p.size > 0]),
                    )

                logger.debug(
                    f"Position update for {symbol}: Size={position.size}, PnL={position.unrealized_pnl:.2f}",
                )

    def _handle_order(self, message: dict):
        """Process order updates."""
        for order_data in message.get("data", []):
            order_id = order_data.get("orderId")
            if order_id:
                self.orders[order_id] = order_data  # Store full order info
                logger.info(
                    f"Order update: {order_id} - Symbol: {order_data.get('symbol')}, Status: {order_data.get('orderStatus')}, Qty: {order_data.get('qty')}, Filled: {order_data.get('cumExecQty')}",
                )

    def _handle_execution(self, message: dict):
        """Process execution (trade fill) updates."""
        for exec_data in message.get("data", []):
            logger.info(
                f"Execution: {exec_data.get('symbol')} - "
                f"Price: {exec_data.get('execPrice')}, "
                f"Qty: {exec_data.get('execQty')}, "
                f"Side: {exec_data.get('side')}, "
                f"Fee: {exec_data.get('execFee')}",
            )

            # Track execution latency
            if config.enable_metrics:
                if "T" in exec_data:  # Timestamp of execution in milliseconds
                    exec_time = datetime.fromtimestamp(
                        exec_data["T"] / 1000, tz=None,
                    )  # Assume UTC
                    latency = (
                        datetime.utcnow() - exec_time
                    ).total_seconds()  # IMPROVEMENT #11: UTC
                    metrics["order_latency"].observe(latency)

    def get_statistics(self) -> dict:
        """Get WebSocket statistics."""
        avg_latency_ms = (
            (sum(self._message_latency) / len(self._message_latency) * 1000)
            if self._message_latency
            else 0
        )
        return {
            "message_count": self._message_count,
            "error_count": self._error_count,
            "avg_latency_ms": f"{avg_latency_ms:.2f}",
            "active_subscriptions": len(self._subscriptions),
            "cached_symbols": len(self.market_data),
        }

    async def cleanup(self):
        """Gracefully close WebSocket connections."""
        self._is_running.clear()  # Signal loops to stop
        await asyncio.sleep(0.1)  # Give a moment for loops to pick up the signal
        if self.ws_public:
            self.ws_public.exit()
        if self.ws_private:
            self.ws_private.exit()
        logger.info("WebSocket connections closed.")


# --- Strategy Interface ---
class StrategyInterface:
    """Base interface for trading strategies."""

    def __init__(self, name: str, bot_instance: "AdvancedBybitTradingBot"):
        self.name = name
        self.bot = bot_instance  # Reference to the main bot instance
        self.parameters: dict[str, Any] = {}

    def set_parameters(self, **kwargs):
        """Set or update strategy parameters."""
        self.parameters.update(kwargs)

    async def analyze(
        self, market_data: dict[str, Any], account_info: dict[str, Any],
    ) -> list[Order]:
        """Analyze market data and generate orders."""
        raise NotImplementedError

    async def on_order_filled(
        self, order: Order, execution_price: Decimal, filled_qty: Decimal, pnl: Decimal,
    ):
        """Called when one of this strategy's orders is filled."""
        logger.info(
            f"Strategy '{self.name}': Order {order.order_id} filled for {order.symbol} at {execution_price} (Qty: {filled_qty}). PnL: {pnl}",
        )
        # Update strategy's internal state or metrics if needed

    async def on_position_update(self, position: Position):
        """Called when a position relevant to this strategy is updated."""
        logger.debug(
            f"Strategy '{self.name}': Position update for {position.symbol}. Size: {position.size}, Unrealized PnL: {position.unrealized_pnl:.2f}",
        )


# --- Main Trading Bot Class ---
class AdvancedBybitTradingBot:
    """Enhanced trading bot with advanced features."""

    def __init__(self, config: BotConfiguration):
        self.config = config
        # IMPROVEMENT #2: Dedicated ThreadPoolExecutor for blocking API calls
        self._api_executor = ThreadPoolExecutor(
            max_workers=config.rate_limit_per_second * 2,
        )

        self.session: HTTP | None = None
        if not config.paper_trading:
            self.session = HTTP(
                testnet=config.use_testnet,
                api_key=config.api_key,
                api_secret=config.api_secret,
                recv_window=10000,
            )

        self.ws_manager = EnhancedWebSocketManager(
            config.api_key, config.api_secret, config.use_testnet, config.paper_trading,
        )

        self.strategies: dict[str, StrategyInterface] = {}
        self.risk_manager = RiskManager(
            max_position_size=Decimal("100"),  # Example default
            max_leverage=10,  # Example default
            max_drawdown=Decimal("-5000"),  # Example default
        )

        self.symbol_info: dict[str, Any] = {}
        self.performance = EnhancedPerformanceMetrics()
        self.cache = CacheManager()

        self._emergency_stop = (
            threading.Event()
        )  # IMPROVEMENT #3: Use threading.Event for cross-thread shutdown
        self._setup_signal_handlers()

        # Paper trading state (IMPROVEMENT #5)
        self._paper_balance: dict[str, dict[str, Decimal]] = {
            "USDT": {
                "walletBalance": Decimal("100000"),
                "availableToWithdraw": Decimal("100000"),
            },
        }
        self._paper_positions: dict[str, Position] = {}
        self._paper_orders: dict[str, Order] = {}  # Pending limit orders in paper mode

        # Metrics mode
        self._metrics_mode = "paper" if config.paper_trading else "live"

    def _setup_signal_handlers(self):
        """IMPROVEMENT #3: Setup graceful shutdown handlers for SIGINT and SIGTERM."""

        def signal_handler(sig, frame):
            logger.warning(f"Signal {sig} received. Initiating graceful shutdown...")
            self._emergency_stop.set()  # Set the event to signal all tasks to stop

            # Async cleanup needs to be scheduled on the event loop
            asyncio.create_task(self.cleanup())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def add_strategy(self, strategy: StrategyInterface):
        """Add a trading strategy and load its parameters."""
        self.strategies[strategy.name] = strategy
        # IMPROVEMENT #12: Load strategy parameters from a central file after strategy initializes its defaults.
        try:
            strategy_params_path = Path(self.config.strategy_params_file)
            if strategy_params_path.exists():
                with open(strategy_params_path) as f:
                    all_params = json.load(f)
                    if strategy.name in all_params:
                        strategy.set_parameters(**all_params[strategy.name])
                        logger.info(
                            f"Strategy '{strategy.name}' loaded parameters from {self.config.strategy_params_file}: {strategy.parameters}",
                        )
            else:
                logger.warning(
                    f"Strategy params file not found at '{self.config.strategy_params_file}'. Using strategy defaults.",
                )
        except (json.JSONDecodeError, KeyError, Exception) as e:
            logger.error(
                f"Error loading parameters for strategy '{strategy.name}' from {self.config.strategy_params_file}: {e}",
                exc_info=True,
            )
            logger.warning(
                f"Strategy '{strategy.name}' will use its default parameters.",
            )
        logger.info(f"Added strategy: {strategy.name}")

    @advanced_retry(max_retries=3, exceptions=(ConnectionError, TimeoutError))
    async def _api_call(self, func: Callable, *args, **kwargs):
        """IMPROVEMENT #2: Make API call using ThreadPoolExecutor with rate limiting, timeout, and retry."""
        if self.config.paper_trading:
            logger.debug(f"PAPER TRADING: Suppressed API call to {func.__name__}")
            return {"retCode": 0, "retMsg": "OK", "result": {}}  # Simulate success

        # Rate limiting logic (e.g., using an asyncio.Semaphore as a simple token bucket)
        # For more complex rate limiting, a TokenBucket class would be better here.
        await asyncio.sleep(
            1 / self.config.rate_limit_per_second,
        )  # Simple rate limiting for demo

        if config.enable_metrics:
            metrics["api_calls"].labels(endpoint=func.__name__).inc()

        try:
            # Run blocking API call in a separate thread
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    self._api_executor, func, *args, **kwargs,
                ),
                timeout=self.config.api_call_timeout,
            )

            if result.get("retCode") != 0:
                error_msg = result.get("retMsg", "Unknown API error")
                logger.error(f"API Error in {func.__name__}: {error_msg}")
                raise ConnectionError(error_msg)  # Raise to trigger retry

            return result
        except TimeoutError:
            logger.error(
                f"API call to {func.__name__} timed out after {self.config.api_call_timeout}s.",
            )
            raise TimeoutError(f"API call to {func.__name__} timed out.")
        except Exception as e:
            logger.error(
                f"Unexpected error during API call {func.__name__}: {e}", exc_info=True,
            )
            raise

    async def fetch_symbol_info(self, symbols: list[str], category: str = "linear"):
        """IMPROVEMENT #6: Fetch and cache symbol information."""
        # Check cache first
        cache_key = f"symbol_info:{','.join(sorted(symbols))}"
        cached_info = await self.cache.get(cache_key)
        if cached_info:
            # We want to refresh periodically even if cached, so use cached only for initial boot/fallback
            self.symbol_info = cached_info
            logger.debug(f"Loaded symbol info from cache for {', '.join(symbols)}.")

        try:
            result = await self._api_call(
                self.session.get_instruments_info
                if self.session
                else (lambda category: {"retCode": 0, "result": {"list": []}}),
                category=category,
            )

            all_instruments = result.get("result", {}).get("list", [])
            updated_info = {}
            for item in all_instruments:
                sym = item.get("symbol")
                if sym in symbols:
                    updated_info[sym] = {
                        "minOrderQty": _dec(item["lotSizeFilter"]["minOrderQty"]),
                        "qtyStep": _dec(item["lotSizeFilter"]["qtyStep"]),
                        "tickSize": _dec(item["priceFilter"]["tickSize"]),
                        "minPrice": _dec(item["priceFilter"]["minPrice"]),
                        "maxPrice": _dec(item["priceFilter"]["maxPrice"]),
                        "baseCoin": item.get("baseCoin"),
                        "quoteCoin": item.get("quoteCoin"),
                        "innovation": item.get("innovation"),
                        "status": item.get("status"),
                        "fetched_at": datetime.utcnow().isoformat(),  # IMPROVEMENT #11: UTC
                    }

            if updated_info:  # Only update if new info was actually fetched
                self.symbol_info.update(updated_info)
                await self.cache.set(
                    cache_key, self.symbol_info, expire=3600 * 24,
                )  # Cache for 24 hours
                logger.info(
                    f"Refreshed symbol info for {len(self.symbol_info)} symbols.",
                )
            else:
                logger.warning("No symbol info fetched. Using existing or empty.")

        except Exception as e:
            logger.error(f"Error fetching symbol info: {e}", exc_info=True)
            # If fetching fails, we continue with potentially stale or empty info.
            if not self.symbol_info:
                logger.critical(
                    "Failed to get ANY symbol info. Bot might not function correctly.",
                )
            raise  # Re-raise to trigger retry from _periodic_task

    async def place_order(self, order: Order) -> Order | None:
        """IMPROVEMENT #5: Place an order with validation, risk checks, and paper trading simulation."""
        # Pre-validation
        try:
            # Note: We are using a simplified validation within this method.
            # A more robust system would have a dedicated OrderValidator class.
            if order.qty <= 0:
                raise ValueError("Order quantity must be positive.")
            if order.order_type == OrderType.LIMIT and order.price is None:
                raise ValueError("Limit order requires a price.")

        except ValueError as e:
            logger.error(
                f"Pre-validation failed for order {order.symbol} {order.side.value} {order.qty}: {e}",
            )
            self.performance.failed_trades += 1
            return None

        # Risk check
        account_info = await self.get_account_info()
        approved, reason = self.risk_manager.check_order_risk(
            order, account_info, self.symbol_info,
        )  # IMPROVEMENT #7
        if not approved:
            logger.warning(
                f"Order rejected by risk manager ({order.symbol} {order.side.value} {order.qty}): {reason}",
            )
            self.performance.failed_trades += 1
            return None

        # Paper Trading Simulation (IMPROVEMENT #5)
        if self.config.paper_trading:
            logger.info(
                f"PAPER TRADING: Simulating order placement for {order.symbol} {order.side.value} {order.qty} @ {order.price or 'MARKET'}",
            )
            order.order_id = f"PAPER_{order.client_order_id}"

            # Simulate market order fill immediately
            if order.order_type == OrderType.MARKET:
                try:
                    current_price = _dec(
                        self.ws_manager.market_data.get(order.symbol, {})
                        .get("ticker", {})
                        .get("last_price"),
                    )
                    if current_price == 0:
                        logger.error(
                            f"PAPER TRADING: Cannot simulate market order fill for {order.symbol}, no current price.",
                        )
                        self.performance.failed_trades += 1
                        return None

                    fill_price = current_price
                    # Simulate slight slippage for market orders
                    if order.side == OrderSide.BUY:
                        fill_price = fill_price * Decimal(
                            "1.0001",
                        )  # Buy slightly higher
                    else:
                        fill_price = fill_price * Decimal(
                            "0.9999",
                        )  # Sell slightly lower

                    cost = order.qty * fill_price
                    if order.side == OrderSide.BUY:
                        if self._paper_balance["USDT"]["availableToWithdraw"] < cost:
                            logger.warning(
                                f"PAPER TRADING: Insufficient balance to simulate buy order for {order.symbol}.",
                            )
                            self.performance.failed_trades += 1
                            return None
                        self._paper_balance["USDT"]["availableToWithdraw"] -= cost
                    else:  # Sell
                        # For selling/shorting, just assume liquidity for now
                        self._paper_balance["USDT"]["availableToWithdraw"] += cost

                    # Update paper position
                    pos = self._paper_positions.get(
                        order.symbol,
                        Position(
                            order.symbol,
                            order.side.value,
                            Decimal(0),
                            Decimal(0),
                            Decimal(0),
                            Decimal(0),
                            Decimal(0),
                            Decimal(0),
                            1,
                        ),
                    )

                    if pos.size == 0:  # New position
                        pos.side = order.side.value
                        pos.entry_price = fill_price
                        pos.size = order.qty
                    elif pos.side == order.side.value:  # Same direction, average
                        total_cost_old = pos.size * pos.entry_price
                        total_cost_new = order.qty * fill_price
                        pos.size += order.qty
                        pos.entry_price = (total_cost_old + total_cost_new) / pos.size
                    elif order.qty >= pos.size:
                        # Closing or flipping
                        pnl = (
                            (pos.mark_price - pos.entry_price)
                            * pos.size
                            * (1 if pos.side == "Buy" else -1)
                        )
                        pos.realized_pnl += pnl
                        self._paper_balance["USDT"]["walletBalance"] += (
                            pnl  # Add realized PnL to balance
                        )

                        remaining_qty = order.qty - pos.size
                        if remaining_qty > 0:  # Flipped position
                            pos.side = order.side.value
                            pos.size = remaining_qty
                            pos.entry_price = fill_price
                        else:  # Fully closed
                            pos.size = Decimal(0)
                            pos.entry_price = Decimal(0)
                    else:  # Partial close
                        # Proportional PnL
                        pnl = (
                            (pos.mark_price - pos.entry_price)
                            * order.qty
                            * (1 if pos.side == "Buy" else -1)
                        )
                        pos.realized_pnl += pnl
                        self._paper_balance["USDT"]["walletBalance"] += pnl
                        pos.size -= order.qty

                    pos.mark_price = fill_price  # Update mark price after fill
                    pos.last_update = datetime.utcnow()
                    self._paper_positions[order.symbol] = pos
                    self.ws_manager.positions[order.symbol] = (
                        pos  # Also update WS manager's view
                    )

                    self.performance.add_trade(
                        {
                            "symbol": order.symbol,
                            "side": order.side.value,
                            "qty": order.qty,
                            "price": fill_price,
                            "pnl": pnl
                            if "pnl" in locals()
                            else Decimal(0),  # Only for closing trades
                            "volume": order.qty * fill_price,
                        },
                    )
                    logger.info(
                        f"PAPER TRADING: Market order {order.symbol} filled at {fill_price:.8f}. Current balance: {self._paper_balance['USDT']['availableToWithdraw']:.2f}",
                    )
                    return order
                except Exception as e:
                    logger.error(
                        f"PAPER TRADING: Error simulating market order fill: {e}",
                        exc_info=True,
                    )
                    self.performance.failed_trades += 1
                    return None
            else:  # Limit orders in paper trading are currently just stored, not actively matched
                self._paper_orders[order.order_id] = order
                logger.info(
                    f"PAPER TRADING: Limit order {order.symbol} placed (not yet filled).",
                )
                return order

        # Live Trading Logic
        try:
            result = await self._api_call(
                self.session.place_order, category="linear", **order.to_dict(),
            )

            order_id = result.get("result", {}).get("orderId")
            if order_id:
                order.order_id = order_id
                # Note: Actual fill handling happens via WebSocket _handle_execution
                logger.info(
                    f"Order placed: {order_id} - {order.symbol} {order.side.value} {order.qty} @ {order.price or 'MARKET'}",
                )
                self.performance.total_trades += 1  # Increment total trades here
                return order
            logger.error(f"Order placement failed, no orderId in response: {result}")
            self.performance.failed_trades += 1
            return None

        except Exception as e:
            logger.error(
                f"Order placement failed for {order.symbol}: {e}", exc_info=True,
            )
            self.performance.failed_trades += 1
            return None

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order."""
        if self.config.paper_trading:
            if order_id in self._paper_orders:
                del self._paper_orders[order_id]
                logger.info(f"PAPER TRADING: Order {order_id} cancelled.")
                return True
            logger.warning(
                f"PAPER TRADING: Order {order_id} not found for cancellation.",
            )
            return False

        try:
            result = await self._api_call(
                self.session.cancel_order,
                category="linear",
                orderId=order_id,
                symbol=symbol,
            )
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(
                f"Order cancellation failed for {order_id}: {e}", exc_info=True,
            )
            return False

    async def cancel_all_orders(self, symbol: str | None = None):
        """Cancel all open orders for a specific symbol or all symbols."""
        if self.config.paper_trading:
            if symbol:
                keys_to_cancel = [
                    k for k, v in self._paper_orders.items() if v.symbol == symbol
                ]
            else:
                keys_to_cancel = list(self._paper_orders.keys())

            for key in keys_to_cancel:
                del self._paper_orders[key]
            logger.info(f"PAPER TRADING: Cancelled {len(keys_to_cancel)} orders.")
            return

        try:
            params = {"category": "linear"}
            if symbol:
                params["symbol"] = symbol

            await self._api_call(self.session.cancel_all_orders, **params)
            logger.info(f"All orders cancelled{f' for {symbol}' if symbol else ''}.")

        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}", exc_info=True)

    async def close_position(self, symbol: str) -> bool:
        """Close a position by placing an opposite market order."""
        if self.config.paper_trading:
            position = self._paper_positions.get(symbol)
            if not position or position.size == 0:
                logger.warning(f"PAPER TRADING: No position to close for {symbol}.")
                return False

            # Simulate closing the position
            order = Order(
                symbol=symbol,
                side=OrderSide.SELL if position.side == "Buy" else OrderSide.BUY,
                order_type=OrderType.MARKET,
                qty=position.size,  # Close full size
                reduce_only=True,
            )
            simulated_order = await self.place_order(order)

            if simulated_order:
                # Assuming paper trading place_order immediately updates paper_positions
                logger.info(f"PAPER TRADING: Closed position for {symbol}.")
                return True
            return False

        try:
            position = self.ws_manager.positions.get(symbol)
            if not position or position.size == 0:
                logger.warning(f"No position to close for {symbol}.")
                return False

            # Create opposite market order to close position
            order = Order(
                symbol=symbol,
                side=OrderSide.SELL if position.side == "Buy" else OrderSide.BUY,
                order_type=OrderType.MARKET,
                qty=abs(position.size),  # Ensure positive quantity
                reduce_only=True,
            )

            placed_order = await self.place_order(order)
            return placed_order is not None

        except Exception as e:
            logger.error(f"Failed to close position {symbol}: {e}", exc_info=True)
            return False

    async def close_all_positions(self):
        """Close all open positions."""
        # This will be primarily used during graceful shutdown if enabled.
        if self.config.paper_trading:
            logger.info("PAPER TRADING: Closing all simulated positions...")
            for symbol in list(self._paper_positions.keys()):
                if self._paper_positions[symbol].size != 0:
                    await self.close_position(symbol)
            return

        tasks = []
        # Iterate over a copy of items because `ws_manager.positions` might change during iteration
        for symbol, position in list(self.ws_manager.positions.items()):
            if position.size != 0:
                tasks.append(self.close_position(symbol))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for r in results if r is True)
            logger.info(f"Closed {success_count}/{len(tasks)} positions.")
        else:
            logger.info("No open positions to close.")

    async def get_account_info(self, account_type: str = "UNIFIED") -> dict[str, Any]:
        """IMPROVEMENT #5: Get account information with caching or paper trading state."""
        if self.config.paper_trading:
            return self._paper_balance  # Return simulated balance

        cache_key = f"account_info:{account_type}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        try:
            result = await self._api_call(
                self.session.get_wallet_balance,  # Will fail if self.session is None in paper mode, but handled above.
                accountType=account_type,
            )

            account_info = result.get("result", {}).get("list", [{}])[0]

            # Cache for short duration (e.g., 10 seconds)
            await self.cache.set(cache_key, account_info, expire=10)

            return account_info

        except Exception as e:
            logger.error(f"Failed to get account info: {e}", exc_info=True)
            return {}

    async def execute_strategies(self, symbols: list[str]):
        """Execute all strategies and process generated orders."""
        if self._emergency_stop.is_set():
            logger.debug("Emergency stop triggered, skipping strategy execution.")
            return

        # Get relevant market data for symbols the strategies care about
        # Only pass market data that is complete enough for the strategy
        filtered_market_data = {
            sym: data
            for sym, data in self.ws_manager.market_data.items()
            if sym in symbols and "orderbook" in data and "ticker" in data
        }

        if not filtered_market_data:
            logger.warning("No complete market data available for strategy execution.")
            return

        # Get account info (will be paper_balance if in paper_trading)
        account_info = await self.get_account_info()
        if not account_info:
            logger.warning("No account info available for strategy execution.")
            return

        # Execute each strategy
        for name, strategy in self.strategies.items():
            if self._emergency_stop.is_set():
                break  # Stop if signal received during strategy iteration
            try:
                # IMPROVEMENT #7: Resilient strategy execution
                orders_to_place = await strategy.analyze(
                    filtered_market_data, account_info,
                )

                # Place generated orders
                for order in orders_to_place:
                    if self._emergency_stop.is_set():
                        logger.info(
                            "Emergency stop received, abandoning further order placement.",
                        )
                        break

                    # Check max open positions (a general bot-wide limit)
                    open_positions_count = len(
                        [
                            p
                            for p in self.ws_manager.positions.values()
                            if p.size != Decimal(0)
                        ],
                    )
                    if open_positions_count >= self.config.max_open_positions:
                        logger.warning(
                            f"Max positions ({self.config.max_open_positions}) reached. Skipping new order for {order.symbol}.",
                        )
                        continue  # Skip this order, try next strategy or next loop

                    await self.place_order(order)

            except Exception as e:
                logger.error(f"Strategy '{name}' execution error: {e}", exc_info=True)
                # Depending on severity, might set self._emergency_stop.set() here

    async def monitor_positions(self):
        """Monitor and manage open positions based on predefined rules (e.g., TP/SL)."""
        if self._emergency_stop.is_set():
            logger.debug("Emergency stop triggered, skipping position monitoring.")
            return

        positions_to_close = []
        for symbol, position in list(
            self.ws_manager.positions.items(),
        ):  # Iterate over copy
            if position.size == Decimal(0):
                continue  # Skip closed positions

            # Update mark price in position for accurate PnL calculation if ticker data is available
            ticker_data = self.ws_manager.market_data.get(symbol, {}).get("ticker")
            if ticker_data:
                current_mark_price = _dec(ticker_data.get("last_price"))
                if current_mark_price != 0:
                    position.mark_price = current_mark_price
                    # Re-calculate unrealized PnL using the latest mark price
                    if position.side == "Buy":
                        position.unrealized_pnl = (
                            position.mark_price - position.entry_price
                        ) * position.size
                    else:  # Sell
                        position.unrealized_pnl = (
                            position.entry_price - position.mark_price
                        ) * position.size

            # Check if position should be closed by strategy rules
            close_reason = position.should_close(take_profit_pct=2.0, stop_loss_pct=1.0)
            if close_reason:
                logger.info(
                    f"Initiating close for {symbol} position ({position.side} {position.size}) due to: {close_reason}",
                )
                positions_to_close.append(symbol)

            # Notify strategy about position update
            for strategy in self.strategies.values():
                await strategy.on_position_update(position)

        # Execute close operations outside the loop to avoid modifying dict while iterating
        for symbol in positions_to_close:
            await self.close_position(symbol)

        # Update overall unrealized P&L for bot's performance metrics
        self.performance.unrealized_pnl = sum(
            p.unrealized_pnl
            for p in self.ws_manager.positions.values()
            if p.size != Decimal(0)
        )

    async def _periodic_task(
        self, period_seconds: int, task_func: Callable, *args: Any,
    ):
        """IMPROVEMENT #3: Helper to run a task periodically, respecting emergency stop."""
        task_name = task_func.__name__
        logger.debug(
            f"Starting periodic task: {task_name}, interval: {period_seconds}s",
        )
        while not self._emergency_stop.is_set():
            try:
                await task_func(*args)
            except asyncio.CancelledError:
                logger.debug(f"Periodic task {task_name} cancelled.")
                break
            except Exception as e:
                logger.error(
                    f"Error in periodic task '{task_name}': {e}", exc_info=True,
                )

            # Wait for next interval, responsive to shutdown signal
            await self._emergency_stop.wait_for(period_seconds)
        logger.debug(f"Periodic task {task_name} stopped.")

    async def run(self, symbols: list[str], interval: int = 5):
        """Main bot execution loop."""
        logger.info(
            f"Starting bot for symbols: {symbols} with interval: {interval}s (Mode: {self._metrics_mode})",
        )

        # Initialize components
        await self.ws_manager.initialize()
        await self.fetch_symbol_info(symbols)  # Initial fetch

        # Subscribe to market data for all symbols
        for symbol in symbols:
            await self.ws_manager.subscribe("ticker", symbol)
            await self.ws_manager.subscribe("orderbook", symbol)
            await self.ws_manager.subscribe(
                "trade", symbol,
            )  # Optional: if strategy needs trade stream

        # Subscribe to private channels if not in paper trading
        if not self.config.paper_trading:
            await self.ws_manager.subscribe("position")
            await self.ws_manager.subscribe("order")
            await self.ws_manager.subscribe("execution")

        # Start Prometheus metrics server if enabled
        if config.enable_metrics:
            try:
                prometheus_client.start_http_server(8000)
                logger.info("Prometheus metrics server started on port 8000.")
            except OSError as e:
                logger.error(
                    f"Failed to start Prometheus server (port 8000 likely in use): {e}",
                )

        # Start periodic background tasks (IMPROVEMENT #5, #6)
        asyncio.create_task(
            self._periodic_task(3600, self.fetch_symbol_info, symbols),
        )  # Refresh symbol info hourly
        asyncio.create_task(
            self._periodic_task(3600, self.save_performance_data),
        )  # Save performance data hourly
        asyncio.create_task(
            self._periodic_task(
                300, self.cache._cache_maintenance, self._emergency_stop,
            ),
        )  # Cache cleanup

        # Main trading loop
        try:
            while not self._emergency_stop.is_set():
                loop_start = time.monotonic()

                await self.execute_strategies(symbols)
                await self.monitor_positions()

                # Log statistics periodically
                if (
                    self.performance.total_trades % 5 == 0
                    or self.performance.total_trades == 0
                ):
                    stats = self.performance.get_statistics()
                    ws_stats = self.ws_manager.get_statistics()
                    logger.info(f"Bot Performance: {stats}")
                    logger.info(f"WS Statistics: {ws_stats}")

                # Dynamic sleep to maintain interval
                elapsed = time.monotonic() - loop_start
                sleep_time = max(0, interval - elapsed)

                # IMPROVEMENT #3: Use wait_for to be responsive to emergency stop
                await self._emergency_stop.wait_for(sleep_time)

        except asyncio.CancelledError:
            logger.info("Bot main loop cancelled.")
        except Exception as e:
            logger.critical(f"Bot main loop fatal error: {e}", exc_info=True)
        finally:
            await self.cleanup()  # Ensure cleanup is called

    async def cleanup(self):
        """IMPROVEMENT #3: Clean up resources during graceful shutdown."""
        if (
            self._emergency_stop.is_set()
        ):  # Only proceed if shutdown signal was received
            logger.info("Initiating cleanup sequence...")
        else:  # Called directly, e.g., from main()'s finally block
            logger.info("Bot finishing, starting cleanup.")
            self._emergency_stop.set()  # Ensure signal is set for other tasks

        # 1. Cancel all outstanding orders if configured (e.g., from env var)
        if _parse_env_bool("CANCEL_ON_SHUTDOWN", True):
            await self.cancel_all_orders()

        # 2. Close all positions if configured
        if _parse_env_bool("CLOSE_ON_SHUTDOWN", False):
            await self.close_all_positions()

        # 3. Signal internal loops (WS manager, periodic tasks) to stop
        # Their own cleanup will be triggered by `_emergency_stop` being set.
        await self.ws_manager.cleanup()  # Calls ws_manager._is_running.clear()

        # 4. Save final performance data
        await self.save_performance_data()

        # 5. Shut down ThreadPoolExecutor (IMPROVEMENT #2)
        if self._api_executor:
            logger.info("Shutting down API ThreadPoolExecutor...")
            self._api_executor.shutdown(wait=True)
            logger.info("API ThreadPoolExecutor shut down.")

        # 6. Close cache connection
        self.cache.close()

        # 7. Cancel all remaining asyncio tasks
        current_task = asyncio.current_task()
        tasks = [
            t for t in asyncio.all_tasks() if t is not current_task and not t.done()
        ]
        logger.info(f"Cancelling {len(tasks)} remaining asyncio tasks...")
        for task in tasks:
            task.cancel()

        # IMPROVEMENT #3: Wait for tasks to complete with a timeout
        with suppress(
            asyncio.CancelledError,
        ):  # Suppress CancelledError here as we expect it
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=5,
            )
        logger.info("Remaining asyncio tasks cancelled/finished.")

        logger.info("Bot cleanup complete.")

    async def save_performance_data(self):
        """IMPROVEMENT #5: Save performance data to file."""
        try:
            data = {
                "performance": asdict(self.performance),
                "timestamp": datetime.utcnow().isoformat()
                + "Z",  # IMPROVEMENT #11: UTC
            }

            # Ensure the performance_data directory exists
            output_dir = Path("performance_data")
            output_dir.mkdir(parents=True, exist_ok=True)

            filename = (
                output_dir
                / f"performance_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            )
            async with aiofiles.open(filename, "w") as f:
                await f.write(
                    json.dumps(data, indent=2, default=str),
                )  # Use default=str for Decimal/datetime

            logger.info(f"Performance data saved to {filename}")

        except Exception as e:
            logger.error(f"Failed to save performance data: {e}", exc_info=True)


# --- Example Strategy ---
class MarketMakerStrategy(StrategyInterface):
    """IMPROVEMENT #10: A stateful market-making strategy that manages its own orders."""

    def __init__(self, bot_instance: "AdvancedBybitTradingBot"):
        super().__init__("MarketMaker", bot_instance)
        # Store currently placed orders by this strategy
        self.pending_orders: dict[str, Order] = {}  # order_id -> Order object
        # Set default parameters (can be overridden by load_parameters)
        self.set_parameters(
            spread_percentage=0.001,  # 0.1% spread
            order_qty=Decimal("0.001"),  # Small order size
            order_timeout_seconds=10,  # Cancel orders if not filled within this time
        )

    async def analyze(
        self, market_data: dict[str, Any], account_info: dict[str, Any],
    ) -> list[Order]:
        """Generate market making orders."""
        orders_to_place: list[Order] = []
        orders_to_cancel: list[tuple[str, str]] = []  # (order_id, symbol)

        # 1. Monitor and manage existing orders
        current_time = datetime.utcnow()  # IMPROVEMENT #11: UTC
        for order_id, order in list(self.pending_orders.items()):  # Iterate over copy
            # Check if order has timed out
            if (current_time - order.created_at).total_seconds() > self.parameters[
                "order_timeout_seconds"
            ]:
                logger.info(
                    f"MarketMaker: Order {order.order_id} for {order.symbol} timed out. Cancelling.",
                )
                orders_to_cancel.append((order_id, order.symbol))
            # In a real scenario, you'd also check if the order is already filled/cancelled via WS updates
            # For simplicity, this example relies solely on the timeout.

        # Execute cancellations
        for order_id, symbol in orders_to_cancel:
            await self.bot.cancel_order(order_id, symbol)
            self.pending_orders.pop(order_id, None)

        # 2. Create new market-making orders
        for symbol, data in market_data.items():
            if symbol not in self.bot.symbol_info:
                logger.debug(
                    f"MarketMaker: Skipping {symbol}, no symbol info available.",
                )
                continue

            ob = data.get("orderbook")
            ticker = data.get("ticker")

            if not ob or not ob["bids"] or not ob["asks"] or not ticker:
                logger.debug(
                    f"MarketMaker: Skipping {symbol}, insufficient market data (orderbook/ticker missing).",
                )
                continue

            best_bid = _dec(ob["bids"][0][0])
            best_ask = _dec(ob["asks"][0][0])

            if best_bid == 0 or best_ask == 0 or best_ask <= best_bid:
                logger.warning(
                    f"MarketMaker: Invalid bid/ask prices for {symbol}. Bid: {best_bid}, Ask: {best_ask}. Skipping.",
                )
                continue

            mid_price = (best_bid + best_ask) / 2
            spread = Decimal(str(self.parameters["spread_percentage"]))

            # Calculate desired prices for new limit orders
            buy_price = mid_price * (1 - spread)
            sell_price = mid_price * (1 + spread)

            # Adjust prices to tick size
            tick_size = self.bot.symbol_info[symbol]["tickSize"]
            buy_price = (buy_price // tick_size) * tick_size
            sell_price = (sell_price // tick_size) * tick_size

            order_qty = _dec(self.parameters["order_qty"])
            # Adjust quantity to qtyStep
            qty_step = self.bot.symbol_info[symbol]["qtyStep"]
            order_qty = (order_qty // qty_step) * qty_step
            if order_qty == Decimal(0):
                logger.warning(
                    f"MarketMaker: Calculated order quantity for {symbol} is zero after adjusting to qtyStep. Skipping.",
                )
                continue

            # Check if we already have orders around these prices to avoid over-placing
            # This is a simplified check. A more advanced MM would manage order books.
            has_buy_order = any(
                o.side == OrderSide.BUY
                for o in self.pending_orders.values()
                if o.symbol == symbol
            )
            has_sell_order = any(
                o.side == OrderSide.SELL
                for o in self.pending_orders.values()
                if o.symbol == symbol
            )

            if not has_buy_order:
                buy_order = Order(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    qty=order_qty,
                    price=buy_price,
                    time_in_force="PostOnly",  # Ensures order doesn't immediately execute as taker
                )
                orders_to_place.append(buy_order)

            if not has_sell_order:
                sell_order = Order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    qty=order_qty,
                    price=sell_price,
                    time_in_force="PostOnly",
                )
                orders_to_place.append(sell_order)

        # For a stateful strategy, `place_order` needs to update `self.pending_orders`
        # We modify the main bot's place_order to return the full Order object after placement
        for order in orders_to_place:
            placed_order = await self.bot.place_order(order)
            if placed_order and placed_order.order_id:
                self.pending_orders[placed_order.order_id] = placed_order

        return []  # Orders are placed directly by the strategy now, not returned to bot for batching.


# Main entry point
async def main():
    """Enhanced main entry point."""
    # Ensure logging is setup early.
    global logger

    try:
        # Create bot
        bot = AdvancedBybitTradingBot(config)

        # Add strategies
        # Pass the bot instance to the strategy for direct interaction
        mm_strategy = MarketMakerStrategy(bot)
        bot.add_strategy(mm_strategy)

        # Get symbols from environment or use default
        symbols_str = os.getenv("TRADING_SYMBOLS", "BTCUSDT,ETHUSDT")
        symbols = [
            s.strip() for s in symbols_str.split(",") if s.strip()
        ]  # Clean and filter empty

        # Main bot interval from environment, default to 5 seconds
        interval = _parse_env_int("BOT_INTERVAL", 5)

        logger.info(
            f"Bot Configuration: Testnet={config.use_testnet}, Paper_Trading={config.paper_trading}, Symbols={symbols}, Interval={interval}s",
        )

        # Run bot
        await bot.run(symbols, interval)

    except KeyboardInterrupt:
        logger.info("Shutdown requested by user (KeyboardInterrupt).")
    except ValueError as e:
        logger.critical(f"Configuration or Initialization Error: {e}", exc_info=True)
        sys.exit(1)  # Exit immediately if configuration is bad
    except Exception as e:
        logger.critical(f"A fatal error occurred in main execution: {e}", exc_info=True)
        sys.exit(1)  # Exit on unhandled fatal errors
    finally:
        # Ensure the QueueListener is stopped to flush logs
        if "log_listener" in globals() and log_listener.is_alive():
            logger.info("Stopping log listener...")
            log_listener.stop()
            # Give listener a moment to process final logs
            time.sleep(1)


if __name__ == "__main__":
    # Wrap asyncio.run in a try-except to catch top-level errors and ensure graceful exit
    try:
        asyncio.run(main())
    except Exception as e:
        # If something goes wrong before `main()` can catch it or during its cleanup,
        # this ensures final logging and clean exit.
        print(f"Unhandled exception outside asyncio.run: {e}")
        logging.getLogger(__name__).critical(
            f"Unhandled exception outside asyncio.run: {e}", exc_info=True,
        )
        sys.exit(1)
