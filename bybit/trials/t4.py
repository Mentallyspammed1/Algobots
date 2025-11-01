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
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from decimal import ROUND_DOWN
from decimal import Decimal
from decimal import InvalidOperation
from decimal import getcontext
from enum import Enum
from enum import auto
from functools import lru_cache
from functools import wraps
from logging.handlers import QueueHandler
from logging.handlers import QueueListener
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiofiles
import numpy as np
import prometheus_client
import redis
import uvloop
from cryptography.fernet import Fernet
from pybit.unified_trading import HTTP
from pybit.unified_trading import WebSocket
from pythonjsonlogger import jsonlogger

# --- High-Performance Event Loop ---
# Set uvloop policy early for maximum async performance.
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

# --- Early logger to avoid NameError during bootstrap ---
logger = logging.getLogger(__name__)

# --- Global Decimal Precision ---
getcontext().prec = 50


# --- Helpers: rounding to exchange step sizes ---
def round_to_step(value: Decimal, step: Decimal, rounding=ROUND_DOWN) -> Decimal:
    """Round a value to the nearest step multiple down/up as per rounding argument.
    e.g., value=123.456, step=0.01 -> 123.45 (ROUND_DOWN)
    """
    if step == 0:
        return value
    # Use quantize when step is decimal like 0.001, else fallback to floor division
    try:
        # quantize only works cleanly with power-of-10 steps
        exp = Decimal(str(step)).normalize().as_tuple().exponent
        return (
            (value // step) * step
            if exp > 0
            else value.quantize(step, rounding=rounding)
        )
    except Exception:
        # Fallback to floor multiple
        return (value // step) * step


def is_multiple_of_step(value: Decimal, step: Decimal) -> bool:
    if step == 0:
        return True
    try:
        return (value / step) == (value // step)
    except Exception:
        return False


# --- Environment Variable Parsers ---
def _parse_env_bool(var_name: str, default: bool = False) -> bool:
    """Parses a boolean environment variable."""
    return os.getenv(var_name, str(default)).strip().lower() in {
        "true",
        "1",
        "yes",
        "y",
        "on",
    }


def _parse_env_int(var_name: str, default: int = 0) -> int:
    """Parses an integer environment variable."""
    try:
        return int(os.getenv(var_name, str(default)))
    except ValueError:
        logging.getLogger(__name__).warning(
            f"Invalid integer for {var_name}, using default: {default}"
        )
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
                        f"Attempt {attempt + 1}/{len(delays)} failed for {func.__name__}: {e}. Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
            return None

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            raise NotImplementedError(
                "Sync wrapper for advanced_retry is not implemented for this context."
            )

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# --- Enhanced Decimal Parser ---
@lru_cache(maxsize=4096)
def _dec(value: Any, default: Decimal = Decimal(0)) -> Decimal:
    """Robust Decimal parser with caching, direct type handling, and validation."""
    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    try:
        cleaned = str(value).strip().replace(",", "").replace("$", "").replace(" ", "")
        return Decimal(cleaned)
    except (InvalidOperation, ValueError, TypeError, AttributeError) as e:
        logging.getLogger(__name__).debug(
            f"Decimal conversion failed for value: '{value}' (Type: {type(value)}): {e}",
            exc_info=True,
        )
        return default


# --- Configuration Class ---
@dataclass
class BotConfiguration:
    api_key: str
    api_secret: str
    use_testnet: bool = False
    paper_trading: bool = False
    max_reconnect_attempts: int = 5
    ws_ping_interval: int = 20
    ws_liveness_timeout: int = 60
    log_level: str = "INFO"
    max_open_positions: int = 5
    rate_limit_per_second: int = 10
    redis_host: str = "localhost"
    redis_port: int = 6379
    enable_metrics: bool = True
    enable_encryption: bool = True
    strategy_params_file: str = "strategy_params.json"
    api_call_timeout: float = 10.0
    shutdown_cancel_orders: bool = True
    shutdown_close_positions: bool = False

    def __post_init__(self):
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
                "ws_liveness_timeout should ideally be at least twice ws_ping_interval."
            )
        if self.paper_trading:
            logger.warning(
                "PAPER TRADING MODE IS ENABLED. NO REAL ORDERS WILL BE PLACED."
            )


# --- Logging Setup ---
def setup_logging(log_level: str, log_queue: queue.Queue) -> QueueListener:
    """Configures structured, thread-safe, asynchronous logging."""

    class CustomJsonFormatter(jsonlogger.JsonFormatter):
        def add_fields(self, log_record, record, message_dict):
            super().add_fields(log_record, record, message_dict)
            log_record["timestamp"] = datetime.utcnow().isoformat() + "Z"
            log_record["level"] = record.levelname
            log_record["name"] = record.name
            log_record["module"] = record.module
            log_record["function"] = record.funcName
            log_record["line"] = record.lineno

    queue_handler = QueueHandler(log_queue)

    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    )
    console_handler.setFormatter(console_formatter)

    file_handler = RotatingFileHandler(
        "bybit_trading_bot.log", maxBytes=50 * 1024 * 1024, backupCount=10
    )
    file_handler.setFormatter(
        CustomJsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(module)s %(funcName)s %(line)s %(message)s"
        )
    )

    listener = QueueListener(
        log_queue, console_handler, file_handler, respect_handler_level=True
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))
    root_logger.addHandler(queue_handler)
    return listener


# --- Load Configuration & Initialize Logging ---
config = BotConfiguration(
    api_key=os.getenv("BYBIT_API_KEY", ""),
    api_secret=os.getenv("BYBIT_API_SECRET", ""),
    use_testnet=_parse_env_bool("BYBIT_USE_TESTNET", False),
    paper_trading=_parse_env_bool("PAPER_TRADING", False),
    max_reconnect_attempts=_parse_env_int("MAX_RECONNECT_ATTEMPTS", 5),
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
    shutdown_cancel_orders=_parse_env_bool("CANCEL_ON_SHUTDOWN", True),
    shutdown_close_positions=_parse_env_bool("CLOSE_ON_SHUTDOWN", False),
)

log_queue = queue.Queue(-1)
log_listener = setup_logging(config.log_level, log_queue)
log_listener.start()
logger = logging.getLogger(__name__)
logger.info("Logging initialized.")

# --- Prometheus Metrics ---
metrics: dict[str, Any] = {}
if config.enable_metrics:
    metrics = {
        "total_trades": prometheus_client.Counter(
            "bot_total_trades", "Total number of trades (fills)", ["mode"]
        ),
        "successful_trades": prometheus_client.Counter(
            "bot_successful_trades", "Number of profitable fills", ["mode"]
        ),
        "failed_trades": prometheus_client.Counter(
            "bot_failed_trades", "Number of losing fills", ["mode"]
        ),
        "api_calls": prometheus_client.Counter(
            "bot_api_calls", "Total API calls made", ["endpoint"]
        ),
        "ws_messages": prometheus_client.Counter(
            "bot_ws_messages", "WebSocket messages received", ["channel"]
        ),
        "order_latency": prometheus_client.Histogram(
            "bot_order_latency_seconds", "Order execution latency in seconds"
        ),
        "pnl": prometheus_client.Gauge("bot_pnl_total", "Current total P&L"),
        "open_positions": prometheus_client.Gauge(
            "bot_open_positions", "Number of open positions"
        ),
    }


# --- Performance Metrics Dataclass ---
@dataclass
class EnhancedPerformanceMetrics:
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
    start_time: datetime = field(default_factory=datetime.utcnow)
    last_update: datetime = field(default_factory=datetime.utcnow)

    def update(self):
        self.last_update = datetime.utcnow()
        self._calculate_statistics()

    def _calculate_statistics(self):
        if self.total_trades > 0:
            self.win_rate = (self.successful_trades / self.total_trades) * 100
            if len(self.daily_pnl) > 1:
                returns = list(self.daily_pnl.values())
                if returns:
                    float_returns = [float(r) for r in returns]
                    avg_return = np.mean(float_returns)
                    std_return = np.std(float_returns)
                    if std_return > 0:
                        self.sharpe_ratio = (avg_return / std_return) * np.sqrt(252)

    def add_trade(self, trade: dict):
        """Call this on fills only."""
        self.trade_history.append(trade)
        self.total_trades += 1

        pnl = _dec(trade.get("pnl", Decimal(0)))
        trading_mode = "paper" if config.paper_trading else "live"

        if pnl > 0:
            self.successful_trades += 1
            self.avg_win = (
                self.avg_win * (self.successful_trades - 1) + pnl
            ) / self.successful_trades
        else:
            self.failed_trades += 1
            self.avg_loss = (
                self.avg_loss * (self.failed_trades - 1) + abs(pnl)
            ) / self.failed_trades

        self.realized_pnl += pnl
        self.total_volume += _dec(trade.get("volume", Decimal(0)))

        today = datetime.utcnow().date().isoformat()
        self.daily_pnl[today] = self.daily_pnl.get(today, Decimal(0)) + pnl

        self.max_drawdown = min(self.max_drawdown, self.realized_pnl)

        self.update()

        if config.enable_metrics:
            metrics["total_trades"].labels(mode=trading_mode).inc()
            if pnl > 0:
                metrics["successful_trades"].labels(mode=trading_mode).inc()
            else:
                metrics["failed_trades"].labels(mode=trading_mode).inc()
            metrics["pnl"].set(float(self.realized_pnl))

    def get_statistics(self) -> dict:
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
            "uptime": str(datetime.utcnow() - self.start_time),
        }


# --- Order & Position Management ---
class OrderType(Enum):
    MARKET = "Market"
    LIMIT = "Limit"


class OrderSide(Enum):
    BUY = "Buy"
    SELL = "Sell"


@dataclass
class Order:
    symbol: str
    side: OrderSide
    order_type: OrderType
    qty: Decimal
    price: Decimal | None = None
    time_in_force: str = "GTC"
    reduce_only: bool = False
    order_id: str | None = None
    client_order_id: str | None = field(
        default_factory=lambda: f"bot-{int(time.time() * 1000)}_{os.getpid()}_{uuid4().hex[:6]}"
    )
    created_at: datetime = field(default_factory=datetime.utcnow)
    strategy_name: str | None = None  # Helps route fills back to strategy

    def __post_init__(self):
        if self.qty <= 0:
            raise ValueError("Order quantity must be positive.")
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError(f"{self.order_type.value} order requires a price.")

    def to_dict(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": self.symbol,
            "side": self.side.value,
            "orderType": self.order_type.value,
            "qty": str(self.qty),
            "timeInForce": self.time_in_force,
            "reduceOnly": 1 if self.reduce_only else 0,
            "orderLinkId": self.client_order_id,
            "isLeverage": 1,
        }
        if self.price is not None:
            params["price"] = str(self.price)
        return params


@dataclass
class Position:
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
    last_update: datetime = field(default_factory=datetime.utcnow)

    def get_pnl_percentage(self) -> float:
        if self.entry_price == 0 or self.size == 0:
            return 0.0
        current_value = self.size * self.mark_price
        entry_value = self.size * self.entry_price
        pnl_usd = (
            (current_value - entry_value)
            if self.side == "Buy"
            else (entry_value - current_value)
        )
        return float(pnl_usd / entry_value) * 100

    def should_close(
        self, take_profit_pct: float = 2.0, stop_loss_pct: float = 1.0
    ) -> str | None:
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
        self, max_position_size: Decimal, max_leverage: int, max_drawdown: Decimal
    ):
        self.max_position_size = max_position_size
        self.max_leverage = max_leverage
        self.max_drawdown = max_drawdown
        self.current_exposure: Decimal = Decimal(0)
        self.position_limits: dict[str, Decimal] = {}

    def check_order_risk(
        self,
        order: Order,
        account_info: dict,
        symbol_info: dict[str, Any],
        market_data: dict[str, Any],
    ) -> tuple[bool, str]:
        """Check if an order meets risk requirements using available balance and symbol info."""
        available_balance = _dec(account_info.get("totalAvailableBalance", 0))
        info = symbol_info.get(order.symbol)
        if not info:
            return (
                False,
                f"Symbol information not available for {order.symbol}. Cannot validate order.",
            )

        qty_step = _dec(info.get("qtyStep", "1"))
        min_qty = _dec(info.get("minOrderQty", "0"))
        if not is_multiple_of_step(order.qty, qty_step):
            return (
                False,
                f"Order quantity {order.qty} for {order.symbol} is not a multiple of qtyStep {qty_step}.",
            )
        if order.qty < min_qty:
            return (
                False,
                f"Order quantity {order.qty} for {order.symbol} is below minimum {min_qty}.",
            )

        if order.qty > self.max_position_size:
            return (
                False,
                f"Order quantity {order.qty} exceeds general max position size {self.max_position_size}.",
            )

        symbol_limit = self.position_limits.get(order.symbol, self.max_position_size)
        if order.qty > symbol_limit:
            return (
                False,
                f"Order quantity {order.qty} exceeds symbol-specific limit for {order.symbol}: {symbol_limit}.",
            )

        estimated_price = order.price
        if order.order_type == OrderType.MARKET and estimated_price is None:
            md = market_data.get(order.symbol, {})
            tick = md.get("ticker", {})
            estimated_price = (
                _dec(tick.get("last_price"))
                or _dec(tick.get("bid"))
                or _dec(tick.get("ask"))
            )
            if estimated_price == 0:
                return False, f"Cannot estimate price for market order {order.symbol}."

        position_value = order.qty * estimated_price if estimated_price else Decimal(0)
        if not order.reduce_only and position_value > 0:
            required_margin = position_value / max(1, self.max_leverage)
            if available_balance == 0:
                # If account info is sparse, allow but warn
                logger.warning(
                    "Available balance is zero or missing in account info. Risk checks limited."
                )
            elif required_margin > available_balance * Decimal("0.8"):
                return (
                    False,
                    f"Order would use too much margin. Required: {required_margin:.2f}, Available: {available_balance:.2f}.",
                )

        return True, "Order approved"

    def update_exposure(self, positions: list[Position]):
        self.current_exposure = sum(
            pos.size * pos.mark_price for pos in positions if pos.size
        )

    def get_position_size(
        self, account_balance: Decimal, risk_per_trade: Decimal = Decimal("0.02")
    ) -> Decimal:
        calculated_size = account_balance * risk_per_trade * self.max_leverage
        return min(calculated_size, self.max_position_size)


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
                    socket_connect_timeout=2,
                    socket_keepalive=True,
                )
                self.redis_client.ping()
                self.enabled = True
                logger.info("Redis cache connected successfully.")
            except redis.exceptions.ConnectionError as e:
                logger.warning(
                    f"Redis not available at {config.redis_host}:{config.redis_port}: {e}. Falling back to in-memory cache."
                )
            except Exception as e:
                logger.error(
                    f"Failed to initialize Redis client: {e}. Falling back to in-memory cache."
                )

    async def get(self, key: str, default: Any = None) -> Any:
        if self.enabled and self.redis_client:
            try:
                value = await asyncio.to_thread(self.redis_client.get, key)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.debug(f"Redis cache get error for key '{key}': {e}")
        else:
            if key in self.cache_timestamps:
                if (
                    datetime.utcnow() - self.cache_timestamps[key]
                ).total_seconds() > 300:
                    self.memory_cache.pop(key, None)
                    self.cache_timestamps.pop(key, None)
                    return default
            return self.memory_cache.get(key, default)
        return default

    async def set(self, key: str, value: Any, expire: int = 300):
        if self.enabled and self.redis_client:
            try:
                await asyncio.to_thread(
                    self.redis_client.setex, key, expire, json.dumps(value)
                )
            except Exception as e:
                logger.debug(f"Redis cache set error for key '{key}': {e}")
        else:
            self.memory_cache[key] = value
            self.cache_timestamps[key] = datetime.utcnow()

    async def delete(self, key: str):
        if self.enabled and self.redis_client:
            try:
                await asyncio.to_thread(self.redis_client.delete, key)
            except Exception as e:
                logger.debug(f"Redis cache delete error for key '{key}': {e}")
        else:
            self.memory_cache.pop(key, None)
            self.cache_timestamps.pop(key, None)

    async def _cache_maintenance(self, stop_event: threading.Event):
        if self.enabled:
            return
        logger.info("Starting in-memory cache maintenance task...")
        while not stop_event.is_set():
            await asyncio.sleep(3600)
            now = datetime.utcnow()
            keys_to_delete = [
                k
                for k, timestamp in list(self.cache_timestamps.items())
                if (now - timestamp).total_seconds() > 3600
            ]
            for key in keys_to_delete:
                self.memory_cache.pop(key, None)
                self.cache_timestamps.pop(key, None)
                logger.debug(f"Cleaned up expired in-memory cache entry: {key}")
        logger.info("In-memory cache maintenance task stopped.")

    def close(self):
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
            try:
                if not key_str:
                    key = Fernet.generate_key()
                    logger.warning(
                        f"ENCRYPTION_KEY not set. Generated a temporary key: {key.decode()}. For production, set ENCRYPTION_KEY for persistence."
                    )
                    self.fernet = Fernet(key)
                else:
                    self.fernet = Fernet(key_str.encode())
                logger.info("Encryption enabled.")
            except Exception as e:
                logger.error(
                    f"Failed to initialize Fernet: {e}. Encryption disabled.",
                    exc_info=True,
                )
                self.fernet = None
        else:
            logger.info("Encryption disabled by configuration.")

    def encrypt(self, data: str) -> str:
        if self.fernet:
            return self.fernet.encrypt(data.encode()).decode()
        return data

    def decrypt(self, data: str) -> str:
        if self.fernet:
            try:
                return self.fernet.decrypt(data.encode()).decode()
            except Exception as e:
                logger.error(
                    f"Failed to decrypt data: {e}. Returning original.", exc_info=True
                )
                return data
        return data

    def hash_api_key(self, api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()[:8]


# --- Async utilities ---
async def sleep_until_stop(
    stop_event: threading.Event, timeout: float, check_interval: float = 0.2
):
    """Async sleep that wakes early if a threading.Event is set."""
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not stop_event.is_set():
        remaining = end - loop.time()
        if remaining <= 0:
            return
        await asyncio.sleep(min(check_interval, remaining))


async def sleep_or_stop(async_stop_event: asyncio.Event, timeout: float):
    """Sleep up to timeout or return early if async stop event is set."""
    try:
        await asyncio.wait_for(async_stop_event.wait(), timeout)
    except TimeoutError:
        pass


# --- Async Rate Limiter (Token Bucket) ---
class AsyncRateLimiter:
    def __init__(self, rate: float, capacity: float):
        self._rate = rate  # tokens per second
        self._capacity = capacity
        self._tokens = capacity
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            if tokens <= self._tokens:
                self._tokens -= tokens
                return
            needed = tokens - self._tokens
            wait_time = needed / self._rate
        await asyncio.sleep(wait_time)
        # After sleeping, try again (simple recursion/loop)
        await self.acquire(tokens)


# --- WebSocket Manager ---
class EnhancedWebSocketManager:
    """Advanced WebSocket management with liveness checks and auto-reconnection."""

    def __init__(
        self, api_key: str, api_secret: str, testnet: bool, paper_trading: bool
    ):
        self._testnet = testnet
        self._api_key = api_key
        self._api_secret = api_secret
        self._paper_trading = paper_trading

        self.ws_public: WebSocket | None = None
        self.ws_private: WebSocket | None = None

        self.market_data: dict[str, Any] = {}
        self.positions: dict[str, Position] = {}
        self.orders: dict[str, dict] = {}

        self._last_message_time = time.monotonic()
        self._reconnect_lock = asyncio.Lock()
        self._subscriptions: set[str] = set()
        self._stop_event = asyncio.Event()

        self._message_latency: deque = deque(maxlen=100)
        self._message_count = 0
        self._error_count = 0

    async def initialize(self):
        logger.info("Initializing WebSocket Manager...")
        self.ws_public = WebSocket(testnet=self._testnet, channel_type="linear")
        if not self._paper_trading:
            self.ws_private = WebSocket(
                testnet=self._testnet,
                channel_type="private",
                api_key=self._api_key,
                api_secret=self._api_secret,
            )
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._liveness_check_loop())
        logger.info("WebSocket Manager initialized.")

    async def _liveness_check_loop(self):
        logger.debug("Starting WebSocket liveness check loop.")
        while not self._stop_event.is_set():
            await sleep_or_stop(self._stop_event, config.ws_liveness_timeout)
            if self._stop_event.is_set():
                break
            if time.monotonic() - self._last_message_time > config.ws_liveness_timeout:
                logger.warning(
                    "No WebSocket message received recently. Triggering reconnect."
                )
                await self.reconnect()
        logger.debug("WebSocket liveness check loop stopped.")

    async def _heartbeat_loop(self):
        logger.debug("Starting WebSocket heartbeat loop.")
        while not self._stop_event.is_set():
            try:
                if self.ws_public:
                    self.ws_public.ping()
                if self.ws_private:
                    self.ws_private.ping()
                await sleep_or_stop(self._stop_event, config.ws_ping_interval)
            except asyncio.CancelledError:
                logger.debug("Heartbeat loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}. Will retry.", exc_info=True)
                await asyncio.sleep(5)
        logger.debug("WebSocket heartbeat loop stopped.")

    @advanced_retry(
        max_retries=config.max_reconnect_attempts, strategy=RetryStrategy.EXPONENTIAL
    )
    async def reconnect(self):
        async with self._reconnect_lock:
            logger.info("Attempting to reconnect WebSockets...")
            if self.ws_public:
                self.ws_public.exit()
            if self.ws_private:
                self.ws_private.exit()

            self.ws_public = WebSocket(testnet=self._testnet, channel_type="linear")
            if not self._paper_trading:
                self.ws_private = WebSocket(
                    testnet=self._testnet,
                    channel_type="private",
                    api_key=self._api_key,
                    api_secret=self._api_secret,
                )

            current_subscriptions = list(self._subscriptions)
            self._subscriptions.clear()
            for sub_key in current_subscriptions:
                channel, symbol_str = sub_key.split(":", 1)
                symbol = symbol_str if symbol_str != "None" else None
                await self.subscribe(channel, symbol)

            self._last_message_time = time.monotonic()
            logger.info("WebSocket reconnected and subscriptions restored.")

    async def subscribe(self, channel: str, symbol: str | None = None):
        subscription_key = f"{channel}:{symbol}"
        if subscription_key in self._subscriptions:
            logger.debug(f"Already subscribed to {subscription_key}.")
            return

        callback = self._create_callback(channel, symbol)

        ws_instance: WebSocket | None = (
            self.ws_private
            if channel in ["position", "order", "execution"]
            else self.ws_public
        )
        if not ws_instance:
            logger.warning(
                f"Cannot subscribe to channel '{channel}' (no {'private' if channel in ['position', 'order', 'execution'] else 'public'} WebSocket client available)."
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
                f"Subscription failed for {subscription_key}: {e}", exc_info=True
            )
            raise

    def _create_callback(self, channel: str, symbol: str | None):
        def callback(message: dict):
            self._last_message_time = time.monotonic()
            try:
                receive_time = datetime.utcnow()
                if "ts" in message:
                    send_time = datetime.utcfromtimestamp(message["ts"] / 1000)
                    latency = (receive_time - send_time).total_seconds()
                    self._message_latency.append(latency)

                self._message_count += 1
                if config.enable_metrics:
                    metrics["ws_messages"].labels(channel=channel).inc()

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

    def _handle_orderbook(self, message: dict, symbol: str | None):
        data = message.get("data", {})
        if not data or not symbol:
            logger.debug(f"Received empty/invalid orderbook data: {message}")
            return

        current_update_id = _dec(data.get("u", 0))
        last_update_id = (
            self.market_data.get(symbol, {}).get("orderbook", {}).get("update_id", 0)
        )

        if "U" in data and _dec(data["U"]) > last_update_id:
            logger.warning(
                f"Orderbook update for {symbol} out of sequence. Last: {last_update_id}, Prev: {data.get('U')}, Current: {current_update_id}."
            )

        self.market_data.setdefault(symbol, {})["orderbook"] = {
            "bids": [[_dec(p), _dec(q)] for p, q in data.get("b", [])],
            "asks": [[_dec(p), _dec(q)] for p, q in data.get("a", [])],
            "timestamp": _dec(message.get("ts", 0)),
            "update_id": current_update_id,
        }
        self.market_data[symbol]["last_update"] = datetime.utcnow()
        asyncio.create_task(
            CacheManager().set(
                f"orderbook:{symbol}", self.market_data[symbol]["orderbook"], expire=60
            )
        )

    def _handle_trade(self, message: dict, symbol: str | None):
        if not symbol:
            return
        for trade in message.get("data", []):
            market_data = self.market_data.setdefault(symbol, {})
            if "trades" not in market_data:
                market_data["trades"] = deque(maxlen=200)
            market_data["trades"].append(
                {
                    "price": _dec(trade.get("p")),
                    "qty": _dec(trade.get("v")),
                    "side": trade.get("S"),
                    "timestamp": _dec(trade.get("T")),
                }
            )
            market_data["last_trade"] = trade
            market_data["last_update"] = datetime.utcnow()

    def _handle_ticker(self, message: dict, symbol: str | None):
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
        self.market_data[symbol]["last_update"] = datetime.utcnow()

    def _handle_position(self, message: dict):
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

                if config.enable_metrics:
                    metrics["open_positions"].set(
                        len([p for p in self.positions.values() if p.size > 0])
                    )

                logger.debug(
                    f"Position update for {symbol}: Size={position.size}, PnL={position.unrealized_pnl:.2f}"
                )

    def _handle_order(self, message: dict):
        for order_data in message.get("data", []):
            order_id = order_data.get("orderId")
            if order_id:
                self.orders[order_id] = order_data
                logger.info(
                    f"Order update: {order_id} - Symbol: {order_data.get('symbol')}, Status: {order_data.get('orderStatus')}, Qty: {order_data.get('qty')}, Filled: {order_data.get('cumExecQty')}"
                )

    def _handle_execution(self, message: dict):
        for exec_data in message.get("data", []):
            try:
                symbol = exec_data.get("symbol")
                exec_price = _dec(exec_data.get("execPrice"))
                exec_qty = _dec(exec_data.get("execQty"))
                side = exec_data.get("side")
                fee = _dec(exec_data.get("execFee"))
                pnl = (
                    _dec(exec_data.get("execValue", 0)) - fee
                )  # rough placeholder if needed
                logger.info(
                    f"Execution: {symbol} - Price: {exec_price}, Qty: {exec_qty}, Side: {side}, Fee: {fee}"
                )

                if config.enable_metrics and "T" in exec_data:
                    exec_time = datetime.utcfromtimestamp(exec_data["T"] / 1000)
                    latency = (datetime.utcnow() - exec_time).total_seconds()
                    metrics["order_latency"].observe(latency)
            except Exception as e:
                logger.error(f"Error handling execution message: {e}", exc_info=True)

    def get_statistics(self) -> dict:
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
        self._stop_event.set()
        await asyncio.sleep(0.1)
        if self.ws_public:
            self.ws_public.exit()
        if self.ws_private:
            self.ws_private.exit()
        logger.info("WebSocket connections closed.")


# --- Strategy Interface ---
class StrategyInterface:
    def __init__(self, name: str, bot_instance: "AdvancedBybitTradingBot"):
        self.name = name
        self.bot = bot_instance
        self.parameters: dict[str, Any] = {}

    def set_parameters(self, **kwargs):
        self.parameters.update(kwargs)

    async def analyze(
        self, market_data: dict[str, Any], account_info: dict[str, Any]
    ) -> list[Order]:
        raise NotImplementedError

    async def on_order_filled(
        self, order: Order, execution_price: Decimal, filled_qty: Decimal, pnl: Decimal
    ):
        logger.info(
            f"Strategy '{self.name}': Order {order.order_id} filled for {order.symbol} at {execution_price} (Qty: {filled_qty}). PnL: {pnl}"
        )

    async def on_position_update(self, position: Position):
        logger.debug(
            f"Strategy '{self.name}': Position update for {position.symbol}. Size: {position.size}, Unrealized PnL: {position.unrealized_pnl:.2f}"
        )


# --- Main Trading Bot Class ---
class AdvancedBybitTradingBot:
    def __init__(self, config: BotConfiguration):
        self.config = config
        self._api_executor = ThreadPoolExecutor(
            max_workers=max(2, config.rate_limit_per_second * 2)
        )
        self._rate_limiter = AsyncRateLimiter(
            rate=config.rate_limit_per_second, capacity=config.rate_limit_per_second
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
            config.api_key, config.api_secret, config.use_testnet, config.paper_trading
        )

        self.strategies: dict[str, StrategyInterface] = {}
        self.risk_manager = RiskManager(
            max_position_size=Decimal("100"),
            max_leverage=10,
            max_drawdown=Decimal("-5000"),
        )

        self.symbol_info: dict[str, Any] = {}
        self.performance = EnhancedPerformanceMetrics()
        self.cache = CacheManager()

        self._emergency_stop = threading.Event()
        self._setup_signal_handlers()

        # Paper trading state
        self._paper_balance: dict[str, dict[str, Decimal]] = {
            "USDT": {
                "walletBalance": Decimal("100000"),
                "availableToWithdraw": Decimal("100000"),
            }
        }
        self._paper_positions: dict[str, Position] = {}
        self._paper_orders: dict[str, Order] = {}

        self._metrics_mode = "paper" if config.paper_trading else "live"

    def _setup_signal_handlers(self):
        def signal_handler(sig, frame):
            logger.warning(f"Signal {sig} received. Initiating graceful shutdown...")
            self._emergency_stop.set()
            asyncio.create_task(self.cleanup())

        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        except Exception:
            # Some environments (Windows, some notebooks) don't allow signal override
            pass

    def add_strategy(self, strategy: StrategyInterface):
        self.strategies[strategy.name] = strategy
        try:
            strategy_params_path = Path(self.config.strategy_params_file)
            if strategy_params_path.exists():
                with open(strategy_params_path) as f:
                    all_params = json.load(f)
                    if strategy.name in all_params:
                        strategy.set_parameters(**all_params[strategy.name])
                        logger.info(
                            f"Strategy '{strategy.name}' loaded parameters: {strategy.parameters}"
                        )
            else:
                logger.warning(
                    f"Strategy params file not found at '{self.config.strategy_params_file}'. Using strategy defaults."
                )
        except Exception as e:
            logger.error(
                f"Error loading parameters for strategy '{strategy.name}': {e}",
                exc_info=True,
            )
            logger.warning(
                f"Strategy '{strategy.name}' will use its default parameters."
            )
        logger.info(f"Added strategy: {strategy.name}")

    @advanced_retry(max_retries=3, exceptions=(ConnectionError, TimeoutError))
    async def _api_call(self, func: Callable, *args, **kwargs):
        """Run blocking API call in a thread with rate limiting and timeout."""
        if self.config.paper_trading:
            logger.debug(f"PAPER TRADING: Suppressed API call to {func.__name__}")
            return {"retCode": 0, "retMsg": "OK", "result": {}}

        await self._rate_limiter.acquire()

        if config.enable_metrics:
            metrics["api_calls"].labels(endpoint=func.__name__).inc()

        try:
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(self._api_executor, func, *args, **kwargs),
                timeout=self.config.api_call_timeout,
            )
            if result.get("retCode") != 0:
                error_msg = result.get("retMsg", "Unknown API error")
                logger.error(f"API Error in {func.__name__}: {error_msg}")
                raise ConnectionError(error_msg)
            return result
        except TimeoutError:
            logger.error(
                f"API call to {func.__name__} timed out after {self.config.api_call_timeout}s."
            )
            raise TimeoutError(f"API call to {func.__name__} timed out.")
        except Exception as e:
            logger.error(
                f"Unexpected error during API call {func.__name__}: {e}", exc_info=True
            )
            raise

    async def fetch_symbol_info(self, symbols: list[str], category: str = "linear"):
        """Fetch and cache symbol information."""
        cache_key = f"symbol_info:{','.join(sorted(symbols))}"
        cached_info = await self.cache.get(cache_key)
        if cached_info:
            self.symbol_info.update(cached_info)
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
                        "fetched_at": datetime.utcnow().isoformat(),
                    }
            if updated_info:
                self.symbol_info.update(updated_info)
                await self.cache.set(cache_key, updated_info, expire=3600 * 24)
                logger.info(f"Refreshed symbol info for {len(updated_info)} symbols.")
            else:
                logger.warning("No symbol info fetched. Using existing or empty.")
        except Exception as e:
            logger.error(f"Error fetching symbol info: {e}", exc_info=True)
            if not self.symbol_info:
                logger.critical(
                    "Failed to get ANY symbol info. Bot might not function correctly."
                )
            raise

    async def place_order(self, order: Order) -> Order | None:
        """Place an order with validation, risk checks, and paper trading simulation."""
        try:
            if order.qty <= 0:
                raise ValueError("Order quantity must be positive.")
            if order.order_type == OrderType.LIMIT and order.price is None:
                raise ValueError("Limit order requires a price.")
        except ValueError as e:
            logger.error(
                f"Pre-validation failed for order {order.symbol} {order.side.value} {order.qty}: {e}"
            )
            return None

        account_info = await self.get_account_info()
        approved, reason = self.risk_manager.check_order_risk(
            order, account_info, self.symbol_info, self.ws_manager.market_data
        )
        if not approved:
            logger.warning(
                f"Order rejected by risk manager ({order.symbol} {order.side.value} {order.qty}): {reason}"
            )
            return None

        if self.config.paper_trading:
            logger.info(
                f"PAPER TRADING: Simulating order placement for {order.symbol} {order.side.value} {order.qty} @ {order.price or 'MARKET'}"
            )
            order.order_id = f"PAPER_{order.client_order_id}"

            if order.order_type == OrderType.MARKET:
                try:
                    ticker = self.ws_manager.market_data.get(order.symbol, {}).get(
                        "ticker", {}
                    )
                    current_price = (
                        _dec(ticker.get("last_price"))
                        or _dec(ticker.get("ask"))
                        or _dec(ticker.get("bid"))
                    )
                    if current_price == 0:
                        logger.error(
                            f"PAPER TRADING: Cannot simulate market order fill for {order.symbol}, no current price."
                        )
                        return None

                    fill_price = current_price
                    if order.side == OrderSide.BUY:
                        fill_price = fill_price * Decimal("1.0001")
                    else:
                        fill_price = fill_price * Decimal("0.9999")

                    cost = order.qty * fill_price
                    if order.side == OrderSide.BUY:
                        if self._paper_balance["USDT"]["availableToWithdraw"] < cost:
                            logger.warning(
                                f"PAPER TRADING: Insufficient balance to simulate buy order for {order.symbol}."
                            )
                            return None
                        self._paper_balance["USDT"]["availableToWithdraw"] -= cost
                    else:
                        self._paper_balance["USDT"]["availableToWithdraw"] += cost

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

                    pnl = Decimal(0)
                    if pos.size == 0:
                        pos.side = order.side.value
                        pos.entry_price = fill_price
                        pos.size = order.qty
                    elif pos.side == order.side.value:
                        total_cost_old = pos.size * pos.entry_price
                        total_cost_new = order.qty * fill_price
                        pos.size += order.qty
                        pos.entry_price = (total_cost_old + total_cost_new) / pos.size
                    elif order.qty >= pos.size:
                        pnl = (
                            (pos.mark_price - pos.entry_price)
                            * pos.size
                            * (1 if pos.side == "Buy" else -1)
                        )
                        pos.realized_pnl += pnl
                        self._paper_balance["USDT"]["walletBalance"] += pnl
                        remaining_qty = order.qty - pos.size
                        if remaining_qty > 0:
                            pos.side = order.side.value
                            pos.size = remaining_qty
                            pos.entry_price = fill_price
                        else:
                            pos.size = Decimal(0)
                            pos.entry_price = Decimal(0)
                    else:
                        pnl = (
                            (pos.mark_price - pos.entry_price)
                            * order.qty
                            * (1 if pos.side == "Buy" else -1)
                        )
                        pos.realized_pnl += pnl
                        self._paper_balance["USDT"]["walletBalance"] += pnl
                        pos.size -= order.qty

                    pos.mark_price = fill_price
                    pos.last_update = datetime.utcnow()
                    self._paper_positions[order.symbol] = pos
                    self.ws_manager.positions[order.symbol] = pos

                    self.performance.add_trade(
                        {
                            "symbol": order.symbol,
                            "side": order.side.value,
                            "qty": order.qty,
                            "price": fill_price,
                            "pnl": pnl,
                            "volume": order.qty * fill_price,
                        }
                    )
                    logger.info(
                        f"PAPER TRADING: Market order {order.symbol} filled at {fill_price:.8f}. Balance: {self._paper_balance['USDT']['availableToWithdraw']:.2f}"
                    )
                    return order
                except Exception as e:
                    logger.error(
                        f"PAPER TRADING: Error simulating market order fill: {e}",
                        exc_info=True,
                    )
                    return None
            else:
                self._paper_orders[order.order_id] = order
                logger.info(
                    f"PAPER TRADING: Limit order {order.symbol} placed (not yet filled)."
                )
                return order

        try:
            result = await self._api_call(
                self.session.place_order, category="linear", **order.to_dict()
            )
            order_id = result.get("result", {}).get("orderId")
            if order_id:
                order.order_id = order_id
                logger.info(
                    f"Order placed: {order_id} - {order.symbol} {order.side.value} {order.qty} @ {order.price or 'MARKET'}"
                )
                return order
            logger.error(f"Order placement failed, no orderId in response: {result}")
            return None
        except Exception as e:
            logger.error(
                f"Order placement failed for {order.symbol}: {e}", exc_info=True
            )
            return None

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        if self.config.paper_trading:
            if order_id in self._paper_orders:
                del self._paper_orders[order_id]
                logger.info(f"PAPER TRADING: Order {order_id} cancelled.")
                return True
            logger.warning(
                f"PAPER TRADING: Order {order_id} not found for cancellation."
            )
            return False

        try:
            await self._api_call(
                self.session.cancel_order,
                category="linear",
                orderId=order_id,
                symbol=symbol,
            )
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(
                f"Order cancellation failed for {order_id}: {e}", exc_info=True
            )
            return False

    async def cancel_all_orders(self, symbol: str | None = None):
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
        if self.config.paper_trading:
            position = self._paper_positions.get(symbol)
            if not position or position.size == 0:
                logger.warning(f"PAPER TRADING: No position to close for {symbol}.")
                return False
            order = Order(
                symbol=symbol,
                side=OrderSide.SELL if position.side == "Buy" else OrderSide.BUY,
                order_type=OrderType.MARKET,
                qty=position.size,
                reduce_only=True,
            )
            simulated_order = await self.place_order(order)
            return simulated_order is not None

        try:
            position = self.ws_manager.positions.get(symbol)
            if not position or position.size == 0:
                logger.warning(f"No position to close for {symbol}.")
                return False
            order = Order(
                symbol=symbol,
                side=OrderSide.SELL if position.side == "Buy" else OrderSide.BUY,
                order_type=OrderType.MARKET,
                qty=abs(position.size),
                reduce_only=True,
            )
            placed_order = await self.place_order(order)
            return placed_order is not None
        except Exception as e:
            logger.error(f"Failed to close position {symbol}: {e}", exc_info=True)
            return False

    async def close_all_positions(self):
        if self.config.paper_trading:
            logger.info("PAPER TRADING: Closing all simulated positions...")
            for symbol in list(self._paper_positions.keys()):
                if self._paper_positions[symbol].size != 0:
                    await self.close_position(symbol)
            return

        tasks = []
        for symbol, position in list(self.ws_manager.positions.items()):
            if position.size != Decimal(0):
                tasks.append(self.close_position(symbol))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for r in results if r is True)
            logger.info(f"Closed {success_count}/{len(tasks)} positions.")
        else:
            logger.info("No open positions to close.")

    async def get_account_info(self, account_type: str = "UNIFIED") -> dict[str, Any]:
        if self.config.paper_trading:
            # Map to unified structure for consistency
            return {
                "totalAvailableBalance": self._paper_balance["USDT"][
                    "availableToWithdraw"
                ]
            }

        cache_key = f"account_info:{account_type}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        try:
            result = await self._api_call(
                self.session.get_wallet_balance, accountType=account_type
            )
            account_info = {}
            lst = result.get("result", {}).get("list", [])
            if lst:
                # accumulate totalAvailableBalance across coins
                total_available = Decimal(0)
                for wallet in lst:
                    for coin in wallet.get("coin", []):
                        total_available += _dec(coin.get("availableToWithdraw", 0))
                account_info["totalAvailableBalance"] = total_available
            await self.cache.set(cache_key, account_info, expire=10)
            return account_info
        except Exception as e:
            logger.error(f"Failed to get account info: {e}", exc_info=True)
            return {}

    async def execute_strategies(self, symbols: list[str]):
        if self._emergency_stop.is_set():
            logger.debug("Emergency stop triggered, skipping strategy execution.")
            return

        filtered_market_data = {
            sym: data
            for sym, data in self.ws_manager.market_data.items()
            if sym in symbols and "orderbook" in data and "ticker" in data
        }
        if not filtered_market_data:
            logger.warning("No complete market data available for strategy execution.")
            return

        account_info = await self.get_account_info()
        if not account_info:
            logger.warning("No account info available for strategy execution.")
            return

        # Optional circuit breaker on drawdown
        if self.performance.realized_pnl <= self.risk_manager.max_drawdown:
            logger.critical("Max drawdown reached. Stopping trading.")
            self._emergency_stop.set()
            return

        for name, strategy in self.strategies.items():
            if self._emergency_stop.is_set():
                break
            try:
                orders_to_place = await strategy.analyze(
                    filtered_market_data, account_info
                )
                # For backward compatibility: if strategy returns orders, place them
                for order in orders_to_place or []:
                    if self._emergency_stop.is_set():
                        logger.info(
                            "Emergency stop received, abandoning further order placement."
                        )
                        break
                    open_positions_count = len(
                        [
                            p
                            for p in self.ws_manager.positions.values()
                            if p.size != Decimal(0)
                        ]
                    )
                    if open_positions_count >= self.config.max_open_positions:
                        logger.warning(
                            f"Max positions ({self.config.max_open_positions}) reached. Skipping new order for {order.symbol}."
                        )
                        continue
                    await self.place_order(order)
            except Exception as e:
                logger.error(f"Strategy '{name}' execution error: {e}", exc_info=True)

    async def monitor_positions(self):
        if self._emergency_stop.is_set():
            logger.debug("Emergency stop triggered, skipping position monitoring.")
            return

        positions_to_close = []
        for symbol, position in list(self.ws_manager.positions.items()):
            if position.size == Decimal(0):
                continue

            ticker_data = self.ws_manager.market_data.get(symbol, {}).get("ticker")
            if ticker_data:
                current_mark_price = _dec(ticker_data.get("last_price"))
                if current_mark_price != 0:
                    position.mark_price = current_mark_price
                    if position.side == "Buy":
                        position.unrealized_pnl = (
                            position.mark_price - position.entry_price
                        ) * position.size
                    else:
                        position.unrealized_pnl = (
                            position.entry_price - position.mark_price
                        ) * position.size

            close_reason = position.should_close(take_profit_pct=2.0, stop_loss_pct=1.0)
            if close_reason:
                logger.info(
                    f"Initiating close for {symbol} position ({position.side} {position.size}) due to: {close_reason}"
                )
                positions_to_close.append(symbol)

            for strategy in self.strategies.values():
                await strategy.on_position_update(position)

        for symbol in positions_to_close:
            await self.close_position(symbol)

        self.performance.unrealized_pnl = sum(
            p.unrealized_pnl
            for p in self.ws_manager.positions.values()
            if p.size != Decimal(0)
        )

    async def _periodic_task(
        self, period_seconds: int, task_func: Callable, *args: Any
    ):
        task_name = task_func.__name__
        logger.debug(
            f"Starting periodic task: {task_name}, interval: {period_seconds}s"
        )
        while not self._emergency_stop.is_set():
            try:
                await task_func(*args)
            except asyncio.CancelledError:
                logger.debug(f"Periodic task {task_name} cancelled.")
                break
            except Exception as e:
                logger.error(
                    f"Error in periodic task '{task_name}': {e}", exc_info=True
                )
            await sleep_until_stop(self._emergency_stop, period_seconds)
        logger.debug(f"Periodic task {task_name} stopped.")

    async def run(self, symbols: list[str], interval: int = 5):
        logger.info(
            f"Starting bot for symbols: {symbols} with interval: {interval}s (Mode: {self._metrics_mode})"
        )

        await self.ws_manager.initialize()
        await self.fetch_symbol_info(symbols)

        for symbol in symbols:
            await self.ws_manager.subscribe("ticker", symbol)
            await self.ws_manager.subscribe("orderbook", symbol)
            await self.ws_manager.subscribe("trade", symbol)

        if not self.config.paper_trading:
            await self.ws_manager.subscribe("position")
            await self.ws_manager.subscribe("order")
            await self.ws_manager.subscribe("execution")

        if config.enable_metrics:
            try:
                prometheus_client.start_http_server(8000)
                logger.info("Prometheus metrics server started on port 8000.")
            except OSError as e:
                logger.error(
                    f"Failed to start Prometheus server (port 8000 likely in use): {e}"
                )

        asyncio.create_task(self._periodic_task(3600, self.fetch_symbol_info, symbols))
        asyncio.create_task(self._periodic_task(3600, self.save_performance_data))
        asyncio.create_task(
            self._periodic_task(
                300, self.cache._cache_maintenance, self._emergency_stop
            )
        )

        try:
            while not self._emergency_stop.is_set():
                loop_start = time.monotonic()
                await self.execute_strategies(symbols)
                await self.monitor_positions()

                if self.performance.total_trades % 5 == 0:
                    stats = self.performance.get_statistics()
                    ws_stats = self.ws_manager.get_statistics()
                    logger.info(f"Bot Performance: {stats}")
                    logger.info(f"WS Statistics: {ws_stats}")

                elapsed = time.monotonic() - loop_start
                sleep_time = max(0, interval - elapsed)
                await sleep_until_stop(self._emergency_stop, sleep_time)
        except asyncio.CancelledError:
            logger.info("Bot main loop cancelled.")
        except Exception as e:
            logger.critical(f"Bot main loop fatal error: {e}", exc_info=True)
        finally:
            await self.cleanup()

    async def cleanup(self):
        if self._emergency_stop.is_set():
            logger.info("Initiating cleanup sequence...")
        else:
            logger.info("Bot finishing, starting cleanup.")
            self._emergency_stop.set()

        if self.config.shutdown_cancel_orders:
            await self.cancel_all_orders()

        if self.config.shutdown_close_positions:
            await self.close_all_positions()

        await self.ws_manager.cleanup()
        await self.save_performance_data()

        if self._api_executor:
            logger.info("Shutting down API ThreadPoolExecutor...")
            self._api_executor.shutdown(wait=True)
            logger.info("API ThreadPoolExecutor shut down.")

        self.cache.close()

        current_task = asyncio.current_task()
        tasks = [
            t for t in asyncio.all_tasks() if t is not current_task and not t.done()
        ]
        logger.info(f"Cancelling {len(tasks)} remaining asyncio tasks...")
        for task in tasks:
            task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=5
            )
        logger.info("Remaining asyncio tasks cancelled/finished.")
        logger.info("Bot cleanup complete.")

    async def save_performance_data(self):
        try:
            data = {
                "performance": asdict(self.performance),
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
            output_dir = Path("performance_data")
            output_dir.mkdir(parents=True, exist_ok=True)
            filename = (
                output_dir
                / f"performance_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            )
            async with aiofiles.open(filename, "w") as f:
                await f.write(json.dumps(data, indent=2, default=str))
            logger.info(f"Performance data saved to {filename}")
        except Exception as e:
            logger.error(f"Failed to save performance data: {e}", exc_info=True)


# --- Example Strategy ---
class MarketMakerStrategy(StrategyInterface):
    """Stateful market-making strategy that manages its own orders."""

    def __init__(self, bot_instance: "AdvancedBybitTradingBot"):
        super().__init__("MarketMaker", bot_instance)
        self.pending_orders: dict[str, Order] = {}
        self.set_parameters(
            spread_percentage=Decimal("0.001"),  # 0.1%
            order_qty=Decimal("0.001"),
            order_timeout_seconds=10,
            requote_bps=5,  # cancel/repost if drift > 5 bps from target
        )

    async def analyze(
        self, market_data: dict[str, Any], account_info: dict[str, Any]
    ) -> list[Order]:
        orders_to_cancel: list[tuple[str, str]] = []
        current_time = datetime.utcnow()
        # 1) Cancel timed-out orders
        for order_id, order in list(self.pending_orders.items()):
            if (current_time - order.created_at).total_seconds() > self.parameters[
                "order_timeout_seconds"
            ]:
                logger.info(
                    f"MarketMaker: Order {order.order_id} for {order.symbol} timed out. Cancelling."
                )
                orders_to_cancel.append((order_id, order.symbol))
        for order_id, symbol in orders_to_cancel:
            await self.bot.cancel_order(order_id, symbol)
            self.pending_orders.pop(order_id, None)

        # 2) Place/refresh new quotes
        for symbol, data in market_data.items():
            if symbol not in self.bot.symbol_info:
                logger.debug(
                    f"MarketMaker: Skipping {symbol}, no symbol info available."
                )
                continue

            ob = data.get("orderbook")
            ticker = data.get("ticker")
            if not ob or not ob["bids"] or not ob["asks"] or not ticker:
                logger.debug(
                    f"MarketMaker: Skipping {symbol}, insufficient market data."
                )
                continue

            best_bid = _dec(ob["bids"][0][0])
            best_ask = _dec(ob["asks"][0][0])
            if best_bid == 0 or best_ask == 0 or best_ask <= best_bid:
                logger.warning(
                    f"MarketMaker: Invalid bid/ask for {symbol}. Bid: {best_bid}, Ask: {best_ask}."
                )
                continue

            mid_price = (best_bid + best_ask) / 2
            spread = _dec(self.parameters["spread_percentage"])
            buy_price = mid_price * (1 - spread)
            sell_price = mid_price * (1 + spread)

            tick_size = self.bot.symbol_info[symbol]["tickSize"]
            buy_price = round_to_step(buy_price, tick_size, ROUND_DOWN)
            sell_price = round_to_step(sell_price, tick_size, ROUND_DOWN)

            order_qty = _dec(self.parameters["order_qty"])
            qty_step = self.bot.symbol_info[symbol]["qtyStep"]
            order_qty = round_to_step(order_qty, qty_step, ROUND_DOWN)
            if order_qty == Decimal(0):
                logger.warning(
                    f"MarketMaker: Calculated order quantity for {symbol} is zero after step adjust. Skipping."
                )
                continue

            # Check if existing quotes need re-quote (drift > threshold)
            def drift_bps(old: Decimal, new: Decimal) -> Decimal:
                if new == 0:
                    return Decimal(0)
                return abs((old - new) / new) * Decimal(10000)

            requote_bps = Decimal(str(self.parameters.get("requote_bps", 5)))

            # Identify existing buy/sell
            existing_buys = [
                o
                for o in self.pending_orders.values()
                if o.symbol == symbol and o.side == OrderSide.BUY
            ]
            existing_sells = [
                o
                for o in self.pending_orders.values()
                if o.symbol == symbol and o.side == OrderSide.SELL
            ]

            # Cancel/re-quote if drifted
            for o in existing_buys:
                if o.price and drift_bps(o.price, buy_price) > requote_bps:
                    await self.bot.cancel_order(o.order_id, o.symbol)
                    self.pending_orders.pop(o.order_id, None)
            for o in existing_sells:
                if o.price and drift_bps(o.price, sell_price) > requote_bps:
                    await self.bot.cancel_order(o.order_id, o.symbol)
                    self.pending_orders.pop(o.order_id, None)

            # Re-check after cancellations
            has_buy_order = any(
                o
                for o in self.pending_orders.values()
                if o.symbol == symbol and o.side == OrderSide.BUY
            )
            has_sell_order = any(
                o
                for o in self.pending_orders.values()
                if o.symbol == symbol and o.side == OrderSide.SELL
            )

            if not has_buy_order:
                buy_order = Order(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    qty=order_qty,
                    price=buy_price,
                    time_in_force="PostOnly",
                    strategy_name=self.name,
                )
                placed = await self.bot.place_order(buy_order)
                if placed and placed.order_id:
                    self.pending_orders[placed.order_id] = placed

            if not has_sell_order:
                sell_order = Order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    qty=order_qty,
                    price=sell_price,
                    time_in_force="PostOnly",
                    strategy_name=self.name,
                )
                placed = await self.bot.place_order(sell_order)
                if placed and placed.order_id:
                    self.pending_orders[placed.order_id] = placed

        return []  # Strategy now places orders directly


# Main entry point
async def main():
    global logger
    try:
        bot = AdvancedBybitTradingBot(config)
        mm_strategy = MarketMakerStrategy(bot)
        bot.add_strategy(mm_strategy)

        symbols_str = os.getenv("TRADING_SYMBOLS", "BTCUSDT,ETHUSDT")
        symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]
        interval = _parse_env_int("BOT_INTERVAL", 5)

        logger.info(
            f"Bot Configuration: Testnet={config.use_testnet}, Paper_Trading={config.paper_trading}, Symbols={symbols}, Interval={interval}s"
        )
        await bot.run(symbols, interval)
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user (KeyboardInterrupt).")
    except ValueError as e:
        logger.critical(f"Configuration or Initialization Error: {e}", exc_info=True)
        sys.exit(1)
    except Exception as e:
        logger.critical(f"A fatal error occurred in main execution: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if "log_listener" in globals():
            try:
                logger.info("Stopping log listener...")
                log_listener.stop()
                time.sleep(0.5)
            except Exception:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Unhandled exception outside asyncio.run: {e}")
        logging.getLogger(__name__).critical(
            f"Unhandled exception outside asyncio.run: {e}", exc_info=True
        )
        sys.exit(1)
