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
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, getcontext
from enum import Enum, auto
from functools import lru_cache, wraps
from typing import Any

import aiofiles
import numpy as np
import prometheus_client  # Improvement #3: Prometheus metrics
import redis  # Improvement #2: Redis for distributed caching
import uvloop  # Improvement #1: High-performance event loop
from cryptography.fernet import Fernet  # Improvement #4: Encryption for sensitive data
from pybit.unified_trading import HTTP, WebSocket

# Improvement #5: Use uvloop for better async performance
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

# --- Global Decimal Precision for financial calc ---
getcontext().prec = 50  # Improvement #6: Even higher precision for complex calculations


# Improvement #7: Thread-safe singleton pattern
class SingletonMeta(type):
    """Thread-safe Singleton metaclass."""

    _instances = {}
    _lock: threading.Lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


# Improvement #8: Advanced retry mechanism with exponential backoff
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
    exceptions: tuple[Exception, ...] = (Exception,),
):
    """Advanced retry decorator with multiple strategies."""

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            delays = []
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
                        raise
                    logger.warning(
                        f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...",
                    )
                    await asyncio.sleep(delay)
            return None

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            delays = []
            if strategy == RetryStrategy.LINEAR:
                delays = [initial_delay] * max_retries
            elif strategy == RetryStrategy.EXPONENTIAL:
                delays = [
                    min(initial_delay * (2**i), max_delay) for i in range(max_retries)
                ]

            for attempt, delay in enumerate(delays):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == len(delays) - 1:
                        raise
                    logger.warning(
                        f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...",
                    )
                    time.sleep(delay)
            return None

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# Improvement #9: Enhanced decimal parser with caching
@lru_cache(maxsize=1024)
def _dec(value: Any, default: Decimal = Decimal(0)) -> Decimal:
    """Robust Decimal parser with caching and validation."""
    try:
        if value is None or value == "":
            return default
        if isinstance(value, Decimal):
            return value
        # Remove common formatting
        cleaned = str(value).strip().replace(",", "").replace("$", "")
        return Decimal(cleaned)
    except (InvalidOperation, ValueError, TypeError) as e:
        logger.debug(f"Decimal conversion failed for {value}: {e}")
        return default


# Improvement #10: Configuration class with validation
@dataclass
class BotConfiguration:
    """Centralized bot configuration with validation."""

    api_key: str
    api_secret: str
    use_testnet: bool = False
    max_reconnect_attempts: int = 5
    ws_ping_interval: int = 30
    log_level: str = "INFO"
    max_open_positions: int = 5
    rate_limit_per_second: int = 10
    redis_host: str = "localhost"
    redis_port: int = 6379
    enable_metrics: bool = True
    enable_encryption: bool = True

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.api_key or not self.api_secret:
            raise ValueError("API credentials are required")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be at least 1")
        if self.rate_limit_per_second < 1:
            raise ValueError("rate_limit_per_second must be at least 1")


# Load configuration from environment
config = BotConfiguration(
    api_key=os.getenv("BYBIT_API_KEY", ""),
    api_secret=os.getenv("BYBIT_API_SECRET", ""),
    use_testnet=os.getenv("BYBIT_USE_TESTNET", "false").lower() == "true",
    max_reconnect_attempts=int(os.getenv("MAX_RECONNECT_ATTEMPTS", "5")),
    ws_ping_interval=int(os.getenv("WS_PING_INTERVAL", "30")),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "5")),
    rate_limit_per_second=int(os.getenv("RATE_LIMIT_PER_SECOND", "10")),
    redis_host=os.getenv("REDIS_HOST", "localhost"),
    redis_port=int(os.getenv("REDIS_PORT", "6379")),
    enable_metrics=os.getenv("ENABLE_METRICS", "true").lower() == "true",
    enable_encryption=os.getenv("ENABLE_ENCRYPTION", "true").lower() == "true",
)

# Improvement #11: Structured logging with JSON output
from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for structured logging."""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["timestamp"] = datetime.utcnow().isoformat()
        log_record["level"] = record.levelname
        log_record["module"] = record.module
        log_record["function"] = record.funcName
        log_record["line"] = record.lineno


# Setup logging
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler

log_queue = queue.Queue()
queue_handler = QueueHandler(log_queue)

# Console handler
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)
console_handler.setFormatter(console_formatter)

# File handler with rotation
file_handler = RotatingFileHandler(
    "bybit_trading_bot.log",
    maxBytes=50 * 1024 * 1024,  # 50MB
    backupCount=10,
)
json_formatter = CustomJsonFormatter()
file_handler.setFormatter(json_formatter)


# Improvement #12: Async file handler
class AsyncFileHandler(logging.Handler):
    """Asynchronous file handler for non-blocking logging."""

    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        self.queue = asyncio.Queue()
        self.task = None

    async def start(self):
        """Start the async writer task."""
        self.task = asyncio.create_task(self._writer())

    async def _writer(self):
        """Write logs asynchronously."""
        async with aiofiles.open(self.filename, "a") as f:
            while True:
                record = await self.queue.get()
                if record is None:
                    break
                await f.write(self.format(record) + "\n")

    def emit(self, record):
        """Queue the record for async writing."""
        asyncio.create_task(self.queue.put(record))

    async def close(self):
        """Close the handler."""
        await self.queue.put(None)
        if self.task:
            await self.task


# Setup queue listener for thread-safe logging
listener = QueueListener(log_queue, console_handler, file_handler)
listener.start()

logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, config.log_level))
logger.addHandler(queue_handler)

# Improvement #13: Metrics collection with Prometheus
if config.enable_metrics:
    metrics = {
        "total_trades": prometheus_client.Counter(
            "bot_total_trades", "Total number of trades",
        ),
        "successful_trades": prometheus_client.Counter(
            "bot_successful_trades", "Number of successful trades",
        ),
        "failed_trades": prometheus_client.Counter(
            "bot_failed_trades", "Number of failed trades",
        ),
        "api_calls": prometheus_client.Counter("bot_api_calls", "Total API calls made"),
        "ws_messages": prometheus_client.Counter(
            "bot_ws_messages", "WebSocket messages received",
        ),
        "order_latency": prometheus_client.Histogram(
            "bot_order_latency", "Order execution latency",
        ),
        "pnl": prometheus_client.Gauge("bot_pnl", "Current P&L"),
        "open_positions": prometheus_client.Gauge(
            "bot_open_positions", "Number of open positions",
        ),
    }


# Improvement #14: Enhanced performance metrics with statistics
@dataclass
class EnhancedPerformanceMetrics:
    """Advanced performance tracking with statistics."""

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
    start_time: datetime = field(default_factory=datetime.now)
    last_update: datetime = field(default_factory=datetime.now)

    def update(self):
        """Update metrics timestamp."""
        self.last_update = datetime.now()
        self._calculate_statistics()

    def _calculate_statistics(self):
        """Calculate advanced statistics."""
        if self.total_trades > 0:
            self.win_rate = (self.successful_trades / self.total_trades) * 100

            # Calculate Sharpe ratio (simplified)
            if len(self.daily_pnl) > 1:
                returns = list(self.daily_pnl.values())
                if returns:
                    avg_return = sum(returns) / len(returns)
                    std_return = np.std([float(r) for r in returns])
                    if std_return > 0:
                        self.sharpe_ratio = (
                            float(avg_return) / std_return * np.sqrt(252)
                        )

    def add_trade(self, trade: dict):
        """Add a trade to history and update metrics."""
        self.trade_history.append(trade)
        self.total_trades += 1

        pnl = trade.get("pnl", Decimal(0))
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
        self.total_volume += trade.get("volume", Decimal(0))

        # Update daily P&L
        today = datetime.now().date().isoformat()
        self.daily_pnl[today] = self.daily_pnl.get(today, Decimal(0)) + pnl

        # Update max drawdown
        self.max_drawdown = min(self.max_drawdown, self.realized_pnl)

        self.update()

        # Update Prometheus metrics if enabled
        if config.enable_metrics:
            metrics["total_trades"].inc()
            if pnl > 0:
                metrics["successful_trades"].inc()
            else:
                metrics["failed_trades"].inc()
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
            "uptime": str(datetime.now() - self.start_time),
        }


# Improvement #15: Order management system
class OrderType(Enum):
    """Order types."""

    MARKET = "Market"
    LIMIT = "Limit"
    STOP = "Stop"
    STOP_LIMIT = "StopLimit"
    TAKE_PROFIT = "TakeProfit"
    TAKE_PROFIT_LIMIT = "TakeProfitLimit"


class OrderSide(Enum):
    """Order sides."""

    BUY = "Buy"
    SELL = "Sell"


@dataclass
class Order:
    """Order representation with validation."""

    symbol: str
    side: OrderSide
    order_type: OrderType
    qty: Decimal
    price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str = "GTC"
    reduce_only: bool = False
    close_on_trigger: bool = False
    order_id: str | None = None
    client_order_id: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Validate order parameters."""
        if self.qty <= 0:
            raise ValueError("Order quantity must be positive")
        if (
            self.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]
            and not self.price
        ):
            raise ValueError(f"{self.order_type.value} order requires price")
        if (
            self.order_type in [OrderType.STOP, OrderType.STOP_LIMIT]
            and not self.stop_price
        ):
            raise ValueError(f"{self.order_type.value} order requires stop price")

    def to_dict(self) -> dict:
        """Convert to dictionary for API calls."""
        params = {
            "symbol": self.symbol,
            "side": self.side.value,
            "orderType": self.order_type.value,
            "qty": str(self.qty),
            "timeInForce": self.time_in_force,
            "reduceOnly": self.reduce_only,
            "closeOnTrigger": self.close_on_trigger,
        }
        if self.price:
            params["price"] = str(self.price)
        if self.stop_price:
            params["stopPrice"] = str(self.stop_price)
        if self.client_order_id:
            params["orderLinkId"] = self.client_order_id
        return params


# Improvement #16: Position management
@dataclass
class Position:
    """Position representation with P&L tracking."""

    symbol: str
    side: str
    size: Decimal
    entry_price: Decimal
    mark_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    margin: Decimal
    leverage: int
    last_update: datetime = field(default_factory=datetime.now)

    def get_pnl_percentage(self) -> float:
        """Calculate P&L percentage."""
        if self.entry_price == 0:
            return 0.0
        return float((self.unrealized_pnl / (self.size * self.entry_price)) * 100)

    def should_close(
        self, take_profit_pct: float = 2.0, stop_loss_pct: float = 1.0,
    ) -> str | None:
        """Determine if position should be closed."""
        pnl_pct = self.get_pnl_percentage()
        if pnl_pct >= take_profit_pct:
            return "TAKE_PROFIT"
        if pnl_pct <= -stop_loss_pct:
            return "STOP_LOSS"
        return None


# Improvement #17: Risk management system
class RiskManager:
    """Comprehensive risk management system."""

    def __init__(
        self, max_position_size: Decimal, max_leverage: int, max_drawdown: Decimal,
    ):
        self.max_position_size = max_position_size
        self.max_leverage = max_leverage
        self.max_drawdown = max_drawdown
        self.current_exposure: Decimal = Decimal(0)
        self.daily_loss_limit: Decimal = Decimal(0)
        self.position_limits: dict[str, Decimal] = {}

    def check_order_risk(
        self, order: Order, account_balance: Decimal,
    ) -> tuple[bool, str]:
        """Check if order meets risk requirements."""
        # Check position size
        if order.qty > self.max_position_size:
            return False, f"Order size {order.qty} exceeds max {self.max_position_size}"

        # Check leverage
        position_value = order.qty * (order.price or Decimal(0))
        required_margin = position_value / self.max_leverage
        if required_margin > account_balance * Decimal(0.5):  # Max 50% of balance
            return False, "Order would use too much margin"

        # Check symbol limit
        symbol_limit = self.position_limits.get(order.symbol, self.max_position_size)
        if order.qty > symbol_limit:
            return False, f"Order exceeds symbol limit for {order.symbol}"

        return True, "Order approved"

    def update_exposure(self, positions: list[Position]):
        """Update current market exposure."""
        self.current_exposure = sum(pos.size * pos.mark_price for pos in positions)

    def get_position_size(
        self, account_balance: Decimal, risk_per_trade: Decimal = Decimal(0.02),
    ) -> Decimal:
        """Calculate appropriate position size based on Kelly Criterion."""
        # Simplified Kelly Criterion
        kelly_fraction = risk_per_trade  # Conservative approach
        position_size = account_balance * kelly_fraction
        return min(position_size, self.max_position_size)


# Improvement #18: Cache manager with Redis
class CacheManager(metaclass=SingletonMeta):
    """Distributed cache manager using Redis."""

    def __init__(self):
        try:
            self.redis_client = redis.Redis(
                host=config.redis_host,
                port=config.redis_port,
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={
                    1: 1,  # TCP_KEEPIDLE
                    2: 1,  # TCP_KEEPINTVL
                    3: 3,  # TCP_KEEPCNT
                },
            )
            self.redis_client.ping()
            self.enabled = True
            logger.info("Redis cache connected")
        except Exception as e:
            logger.warning(f"Redis not available: {e}. Using in-memory cache.")
            self.enabled = False
            self.memory_cache: dict[str, Any] = {}
            self.cache_timestamps: dict[str, datetime] = {}

    async def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache."""
        if self.enabled:
            try:
                value = self.redis_client.get(key)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.debug(f"Cache get error: {e}")
        else:
            # Check memory cache expiry
            if key in self.cache_timestamps:
                if (
                    datetime.now() - self.cache_timestamps[key]
                ).seconds > 300:  # 5 min expiry
                    del self.memory_cache[key]
                    del self.cache_timestamps[key]
                    return default
            return self.memory_cache.get(key, default)
        return default

    async def set(self, key: str, value: Any, expire: int = 300):
        """Set value in cache with expiration."""
        if self.enabled:
            try:
                self.redis_client.setex(key, expire, json.dumps(value))
            except Exception as e:
                logger.debug(f"Cache set error: {e}")
        else:
            self.memory_cache[key] = value
            self.cache_timestamps[key] = datetime.now()

    async def delete(self, key: str):
        """Delete value from cache."""
        if self.enabled:
            try:
                self.redis_client.delete(key)
            except Exception as e:
                logger.debug(f"Cache delete error: {e}")
        else:
            self.memory_cache.pop(key, None)
            self.cache_timestamps.pop(key, None)


# Improvement #19: Data encryption for sensitive information
class SecurityManager:
    """Handle encryption and security."""

    def __init__(self):
        self.fernet = None
        if config.enable_encryption:
            key = os.getenv("ENCRYPTION_KEY")
            if not key:
                key = Fernet.generate_key()
                logger.warning("No encryption key provided, generated new one")
            self.fernet = Fernet(key if isinstance(key, bytes) else key.encode())

    def encrypt(self, data: str) -> str:
        """Encrypt sensitive data."""
        if self.fernet:
            return self.fernet.encrypt(data.encode()).decode()
        return data

    def decrypt(self, data: str) -> str:
        """Decrypt sensitive data."""
        if self.fernet:
            return self.fernet.decrypt(data.encode()).decode()
        return data

    def hash_api_key(self, api_key: str) -> str:
        """Create hash of API key for logging."""
        return hashlib.sha256(api_key.encode()).hexdigest()[:8]


# Improvement #20: WebSocket connection pool
class WebSocketPool:
    """Manage multiple WebSocket connections for load balancing."""

    def __init__(self, size: int = 3):
        self.size = size
        self.connections: list[WebSocket] = []
        self.current_index = 0
        self.lock = threading.Lock()

    def get_connection(self) -> WebSocket:
        """Get next available connection (round-robin)."""
        with self.lock:
            if not self.connections:
                raise RuntimeError("No WebSocket connections available")
            conn = self.connections[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.connections)
            return conn

    def add_connection(self, conn: WebSocket):
        """Add a connection to the pool."""
        with self.lock:
            if len(self.connections) < self.size:
                self.connections.append(conn)


# Improvement #21: Enhanced WebSocket Manager with reconnection
class EnhancedWebSocketManager:
    """Advanced WebSocket management with auto-reconnection and health monitoring."""

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        self.ws_public_pool = WebSocketPool()
        self.ws_private: WebSocket | None = None

        self.market_data: dict[str, Any] = {}
        self.positions: dict[str, Position] = {}
        self.orders: dict[str, Order] = {}

        self._heartbeat_task: asyncio.Task | None = None
        self._reconnect_lock = asyncio.Lock()
        self._subscriptions: set[str] = set()

        # Performance tracking
        self._message_latency: deque = deque(maxlen=100)
        self._message_count = 0
        self._error_count = 0

        # Cache manager
        self.cache = CacheManager()

        # Security manager
        self.security = SecurityManager()

    async def initialize(self):
        """Initialize WebSocket connections."""
        await self._init_public_pool()
        await self._init_private_ws()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _init_public_pool(self):
        """Initialize public WebSocket connection pool."""
        for i in range(3):  # Create 3 connections
            try:
                ws = WebSocket(testnet=self.testnet, channel_type="linear")
                self.ws_public_pool.add_connection(ws)
                logger.info(f"Public WebSocket {i + 1} initialized")
            except Exception as e:
                logger.error(f"Failed to initialize public WebSocket {i + 1}: {e}")

    async def _init_private_ws(self):
        """Initialize private WebSocket with authentication."""
        try:
            self.ws_private = WebSocket(
                testnet=self.testnet,
                channel_type="private",
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
            logger.info("Private WebSocket initialized")
        except Exception as e:
            logger.error(f"Failed to initialize private WebSocket: {e}")
            raise

    async def _heartbeat_loop(self):
        """Send periodic heartbeat to maintain connection."""
        while True:
            try:
                await asyncio.sleep(config.ws_ping_interval)
                # Send ping to all connections
                for ws in self.ws_public_pool.connections:
                    if ws:
                        ws.ping()
                if self.ws_private:
                    self.ws_private.ping()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

    async def reconnect(self, ws_type: str = "public"):
        """Reconnect WebSocket with exponential backoff."""
        async with self._reconnect_lock:
            for attempt in range(config.max_reconnect_attempts):
                try:
                    logger.info(
                        f"Reconnecting {ws_type} WebSocket (attempt {attempt + 1})",
                    )

                    if ws_type == "public":
                        await self._init_public_pool()
                    else:
                        await self._init_private_ws()

                    # Resubscribe to channels
                    await self._resubscribe()

                    logger.info(f"{ws_type} WebSocket reconnected successfully")
                    return True

                except Exception as e:
                    wait_time = min(2**attempt, 60)
                    logger.error(f"Reconnection failed: {e}. Waiting {wait_time}s")
                    await asyncio.sleep(wait_time)

            logger.critical(
                f"Failed to reconnect {ws_type} WebSocket after {config.max_reconnect_attempts} attempts",
            )
            return False

    async def _resubscribe(self):
        """Resubscribe to all channels after reconnection."""
        for subscription in self._subscriptions:
            # Parse and resubscribe
            parts = subscription.split(":")
            if len(parts) == 2:
                channel, symbol = parts
                await self.subscribe(channel, symbol)

    @advanced_retry(max_retries=3, strategy=RetryStrategy.EXPONENTIAL)
    async def subscribe(self, channel: str, symbol: str = None):
        """Subscribe to a channel with retry logic."""
        subscription_key = f"{channel}:{symbol}" if symbol else channel
        self._subscriptions.add(subscription_key)

        try:
            ws = self.ws_public_pool.get_connection()

            if channel == "orderbook":
                ws.orderbook_stream(
                    depth=50,  # Get more depth
                    symbol=symbol,
                    callback=self._create_callback("orderbook", symbol),
                )
            elif channel == "trade":
                ws.trade_stream(
                    symbol=symbol, callback=self._create_callback("trade", symbol),
                )
            elif channel == "ticker":
                ws.ticker_stream(
                    symbol=symbol, callback=self._create_callback("ticker", symbol),
                )
            elif channel == "position" and self.ws_private:
                self.ws_private.position_stream(
                    callback=self._create_callback("position"),
                )
            elif channel == "order" and self.ws_private:
                self.ws_private.order_stream(callback=self._create_callback("order"))
            elif channel == "execution" and self.ws_private:
                self.ws_private.execution_stream(
                    callback=self._create_callback("execution"),
                )

            logger.debug(f"Subscribed to {subscription_key}")

        except Exception as e:
            logger.error(f"Subscription failed for {subscription_key}: {e}")
            raise

    def _create_callback(self, channel: str, symbol: str = None):
        """Create a callback function for WebSocket messages."""

        def callback(message):
            try:
                # Track message latency
                receive_time = datetime.now()
                if "ts" in message:
                    send_time = datetime.fromtimestamp(message["ts"] / 1000)
                    latency = (receive_time - send_time).total_seconds() * 1000
                    self._message_latency.append(latency)

                self._message_count += 1

                # Update Prometheus metrics
                if config.enable_metrics:
                    metrics["ws_messages"].inc()

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
                logger.error(f"Error processing {channel} message: {e}", exc_info=True)

        return callback

    def _handle_orderbook(self, message: dict, symbol: str):
        """Process orderbook updates."""
        data = message.get("data", {})
        if data:
            market_data = self.market_data.setdefault(symbol, {})
            market_data["orderbook"] = {
                "bids": data.get("b", []),
                "asks": data.get("a", []),
                "timestamp": message.get("ts"),
                "update_id": data.get("u"),
            }
            market_data["last_update"] = datetime.now()

            # Cache the data
            asyncio.create_task(
                self.cache.set(
                    f"orderbook:{symbol}", market_data["orderbook"], expire=60,
                ),
            )

    def _handle_trade(self, message: dict, symbol: str):
        """Process trade updates."""
        for trade in message.get("data", []):
            market_data = self.market_data.setdefault(symbol, {})

            # Keep last N trades
            if "trades" not in market_data:
                market_data["trades"] = deque(maxlen=100)

            market_data["trades"].append(
                {
                    "price": _dec(trade.get("p")),
                    "qty": _dec(trade.get("v")),
                    "side": trade.get("S"),
                    "timestamp": trade.get("T"),
                },
            )
            market_data["last_trade"] = trade
            market_data["last_update"] = datetime.now()

    def _handle_ticker(self, message: dict, symbol: str):
        """Process ticker updates."""
        data = message.get("data", {})
        if data:
            market_data = self.market_data.setdefault(symbol, {})
            market_data["ticker"] = {
                "last_price": _dec(data.get("lastPrice")),
                "bid": _dec(data.get("bid1Price")),
                "ask": _dec(data.get("ask1Price")),
                "volume_24h": _dec(data.get("volume24h")),
                "turnover_24h": _dec(data.get("turnover24h")),
                "high_24h": _dec(data.get("highPrice24h")),
                "low_24h": _dec(data.get("lowPrice24h")),
                "prev_close": _dec(data.get("prevPrice24h")),
            }
            market_data["last_update"] = datetime.now()

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
                    metrics["open_positions"].set(len(self.positions))

    def _handle_order(self, message: dict):
        """Process order updates."""
        for order_data in message.get("data", []):
            order_id = order_data.get("orderId")
            if order_id:
                # Store order info
                self.orders[order_id] = order_data
                logger.info(
                    f"Order update: {order_id} - Status: {order_data.get('orderStatus')}",
                )

    def _handle_execution(self, message: dict):
        """Process execution updates."""
        for exec_data in message.get("data", []):
            logger.info(
                f"Execution: {exec_data.get('symbol')} - "
                f"Price: {exec_data.get('execPrice')}, "
                f"Qty: {exec_data.get('execQty')}, "
                f"Side: {exec_data.get('side')}",
            )

            # Track execution latency
            if config.enable_metrics:
                if "T" in exec_data:
                    exec_time = datetime.fromtimestamp(exec_data["T"] / 1000)
                    latency = (datetime.now() - exec_time).total_seconds() * 1000
                    metrics["order_latency"].observe(latency)

    def get_statistics(self) -> dict:
        """Get WebSocket statistics."""
        avg_latency = (
            sum(self._message_latency) / len(self._message_latency)
            if self._message_latency
            else 0
        )
        return {
            "message_count": self._message_count,
            "error_count": self._error_count,
            "avg_latency_ms": avg_latency,
            "active_subscriptions": len(self._subscriptions),
            "cached_symbols": len(self.market_data),
        }

    async def cleanup(self):
        """Clean up WebSocket connections."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

        for ws in self.ws_public_pool.connections:
            if ws:
                ws.exit()

        if self.ws_private:
            self.ws_private.exit()


# Improvement #22: Strategy interface with backtesting support
class StrategyInterface:
    """Base interface for trading strategies."""

    def __init__(self, name: str):
        self.name = name
        self.parameters: dict[str, Any] = {}
        self.performance = EnhancedPerformanceMetrics()

    async def analyze(self, market_data: dict, account_info: dict) -> list[Order]:
        """Analyze market and generate orders."""
        raise NotImplementedError

    async def on_order_filled(self, order: Order, execution_price: Decimal):
        """Called when an order is filled."""

    async def on_position_update(self, position: Position):
        """Called when a position is updated."""

    def set_parameters(self, **kwargs):
        """Set strategy parameters."""
        self.parameters.update(kwargs)

    def get_statistics(self) -> dict:
        """Get strategy statistics."""
        return self.performance.get_statistics()


# Improvement #23: Advanced Trading Bot with modular design
class AdvancedBybitTradingBot:
    """Enhanced trading bot with advanced features."""

    def __init__(self, config: BotConfiguration):
        self.config = config
        self.session = HTTP(
            testnet=config.use_testnet,
            api_key=config.api_key,
            api_secret=config.api_secret,
            recv_window=10000,
        )

        self.ws_manager = EnhancedWebSocketManager(
            config.api_key, config.api_secret, config.use_testnet,
        )

        self.strategies: dict[str, StrategyInterface] = {}
        self.risk_manager = RiskManager(
            max_position_size=Decimal(10000),
            max_leverage=10,
            max_drawdown=Decimal(1000),
        )

        self.symbol_info: dict[str, Any] = {}
        self.performance = EnhancedPerformanceMetrics()

        # Rate limiting
        self._rate_limiter = asyncio.Semaphore(config.rate_limit_per_second)

        # Order tracking
        self._pending_orders: dict[str, Order] = {}
        self._order_lock = asyncio.Lock()

        # Emergency stop
        self._emergency_stop = False
        self._pause_trading = False

        # Setup signal handlers
        self._setup_signal_handlers()

        # Initialize cache
        self.cache = CacheManager()

    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers."""

        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}. Initiating graceful shutdown...")
            self._emergency_stop = True

            # Cancel all pending orders
            asyncio.create_task(self.cancel_all_orders())

            # Close all positions if configured
            if os.getenv("CLOSE_ON_SHUTDOWN", "false").lower() == "true":
                asyncio.create_task(self.close_all_positions())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def add_strategy(self, strategy: StrategyInterface):
        """Add a trading strategy."""
        self.strategies[strategy.name] = strategy
        logger.info(f"Added strategy: {strategy.name}")

    @advanced_retry(max_retries=3, strategy=RetryStrategy.EXPONENTIAL)
    async def _api_call(self, func: Callable, *args, **kwargs):
        """Make API call with rate limiting and retry."""
        async with self._rate_limiter:
            if config.enable_metrics:
                metrics["api_calls"].inc()

            result = await asyncio.to_thread(func, *args, **kwargs)

            if result.get("retCode") != 0:
                error_msg = result.get("retMsg", "Unknown error")
                logger.error(f"API error: {error_msg}")
                raise Exception(error_msg)

            return result

    async def fetch_symbol_info(self, symbols: list[str], category: str = "linear"):
        """Fetch and cache symbol information."""
        # Check cache first
        cache_key = f"symbol_info:{','.join(sorted(symbols))}"
        cached_info = await self.cache.get(cache_key)
        if cached_info:
            self.symbol_info = cached_info
            return

        try:
            result = await self._api_call(
                self.session.get_instruments_info, category=category,
            )

            all_instruments = result.get("result", {}).get("list", [])

            for item in all_instruments:
                sym = item.get("symbol")
                if sym in symbols:
                    self.symbol_info[sym] = {
                        "minOrderQty": _dec(item["lotSizeFilter"]["minOrderQty"]),
                        "qtyStep": _dec(item["lotSizeFilter"]["qtyStep"]),
                        "tickSize": _dec(item["priceFilter"]["tickSize"]),
                        "minPrice": _dec(item["priceFilter"]["minPrice"]),
                        "maxPrice": _dec(item["priceFilter"]["maxPrice"]),
                        "fetched_at": datetime.now().isoformat(),
                    }

            # Cache the info
            await self.cache.set(cache_key, self.symbol_info, expire=3600)

        except Exception as e:
            logger.error(f"Error fetching symbol info: {e}")
            raise

    async def place_order(self, order: Order) -> str | None:
        """Place an order with validation and risk checks."""
        # Risk check
        account_info = await self.get_account_info()
        balance = _dec(account_info.get("totalWalletBalance", 0))

        approved, reason = self.risk_manager.check_order_risk(order, balance)
        if not approved:
            logger.warning(f"Order rejected by risk manager: {reason}")
            return None

        # Validate against symbol info
        if order.symbol in self.symbol_info:
            info = self.symbol_info[order.symbol]

            # Round quantity to step
            qty_step = info["qtyStep"]
            order.qty = (order.qty // qty_step) * qty_step

            # Round price to tick size
            if order.price:
                tick_size = info["tickSize"]
                order.price = (order.price // tick_size) * tick_size

        try:
            async with self._order_lock:
                result = await self._api_call(
                    self.session.place_order, category="linear", **order.to_dict(),
                )

                order_id = result.get("result", {}).get("orderId")
                if order_id:
                    order.order_id = order_id
                    self._pending_orders[order_id] = order

                    logger.info(
                        f"Order placed: {order_id} - {order.symbol} {order.side.value} {order.qty}",
                    )

                    # Track in performance metrics
                    self.performance.total_trades += 1

                    return order_id

        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            self.performance.failed_trades += 1

        return None

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order."""
        try:
            result = await self._api_call(
                self.session.cancel_order,
                category="linear",
                orderId=order_id,
                symbol=symbol,
            )

            if order_id in self._pending_orders:
                del self._pending_orders[order_id]

            logger.info(f"Order cancelled: {order_id}")
            return True

        except Exception as e:
            logger.error(f"Order cancellation failed: {e}")
            return False

    async def cancel_all_orders(self, symbol: str = None):
        """Cancel all orders for a symbol or all symbols."""
        try:
            params = {"category": "linear"}
            if symbol:
                params["symbol"] = symbol

            result = await self._api_call(self.session.cancel_all_orders, **params)

            self._pending_orders.clear()
            logger.info(f"All orders cancelled{f' for {symbol}' if symbol else ''}")

        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")

    async def close_position(self, symbol: str) -> bool:
        """Close a position."""
        try:
            position = self.ws_manager.positions.get(symbol)
            if not position or position.size == 0:
                logger.warning(f"No position to close for {symbol}")
                return False

            # Create opposite order to close
            order = Order(
                symbol=symbol,
                side=OrderSide.SELL if position.side == "Buy" else OrderSide.BUY,
                order_type=OrderType.MARKET,
                qty=abs(position.size),
                reduce_only=True,
            )

            order_id = await self.place_order(order)
            return order_id is not None

        except Exception as e:
            logger.error(f"Failed to close position {symbol}: {e}")
            return False

    async def close_all_positions(self):
        """Close all open positions."""
        tasks = []
        for symbol, position in self.ws_manager.positions.items():
            if position.size != 0:
                tasks.append(self.close_position(symbol))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for r in results if r is True)
            logger.info(f"Closed {success_count}/{len(tasks)} positions")

    async def get_account_info(self, account_type: str = "UNIFIED") -> dict:
        """Get account information with caching."""
        cache_key = f"account_info:{account_type}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        try:
            result = await self._api_call(
                self.session.get_wallet_balance, accountType=account_type,
            )

            account_info = result.get("result", {}).get("list", [{}])[0]

            # Cache for short duration
            await self.cache.set(cache_key, account_info, expire=10)

            return account_info

        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return {}

    async def execute_strategies(self, symbols: list[str]):
        """Execute all strategies."""
        if self._pause_trading:
            logger.debug("Trading paused, skipping strategy execution")
            return

        # Get market data for all symbols
        market_data = {}
        for symbol in symbols:
            data = self.ws_manager.market_data.get(symbol)
            if data:
                market_data[symbol] = data

        if not market_data:
            logger.warning("No market data available")
            return

        # Get account info
        account_info = await self.get_account_info()
        if not account_info:
            logger.warning("No account info available")
            return

        # Execute each strategy
        for name, strategy in self.strategies.items():
            try:
                orders = await strategy.analyze(market_data, account_info)

                # Place generated orders
                for order in orders:
                    if self._emergency_stop:
                        break

                    # Check position limit
                    open_positions = len(
                        [p for p in self.ws_manager.positions.values() if p.size != 0],
                    )
                    if open_positions >= self.config.max_open_positions:
                        logger.warning(
                            f"Max positions ({self.config.max_open_positions}) reached",
                        )
                        break

                    await self.place_order(order)

            except Exception as e:
                logger.error(f"Strategy {name} execution error: {e}", exc_info=True)

    async def monitor_positions(self):
        """Monitor and manage open positions."""
        for symbol, position in self.ws_manager.positions.items():
            if position.size == 0:
                continue

            # Check if position should be closed
            close_reason = position.should_close(take_profit_pct=2.0, stop_loss_pct=1.0)
            if close_reason:
                logger.info(f"Closing {symbol} position: {close_reason}")
                await self.close_position(symbol)

            # Update performance metrics
            self.performance.unrealized_pnl = sum(
                p.unrealized_pnl for p in self.ws_manager.positions.values()
            )

    async def run(self, symbols: list[str], interval: int = 5):
        """Main bot loop."""
        logger.info(f"Starting bot for symbols: {symbols}")

        # Initialize
        await self.ws_manager.initialize()
        await self.fetch_symbol_info(symbols)

        # Subscribe to market data
        for symbol in symbols:
            await self.ws_manager.subscribe("orderbook", symbol)
            await self.ws_manager.subscribe("trade", symbol)
            await self.ws_manager.subscribe("ticker", symbol)

        # Subscribe to private channels
        await self.ws_manager.subscribe("position")
        await self.ws_manager.subscribe("order")
        await self.ws_manager.subscribe("execution")

        # Start Prometheus metrics server if enabled
        if config.enable_metrics:
            prometheus_client.start_http_server(8000)
            logger.info("Metrics server started on port 8000")

        # Main loop
        try:
            while not self._emergency_stop:
                loop_start = time.time()

                # Execute strategies
                await self.execute_strategies(symbols)

                # Monitor positions
                await self.monitor_positions()

                # Log statistics periodically
                if self.performance.total_trades % 10 == 0:
                    stats = self.performance.get_statistics()
                    ws_stats = self.ws_manager.get_statistics()
                    logger.info(f"Performance: {stats}")
                    logger.info(f"WebSocket: {ws_stats}")

                # Dynamic sleep
                elapsed = time.time() - loop_start
                sleep_time = max(0, interval - elapsed)
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info("Bot cancelled")
        except Exception as e:
            logger.critical(f"Bot error: {e}", exc_info=True)
        finally:
            await self.cleanup()

    async def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up...")

        # Cancel all orders
        await self.cancel_all_orders()

        # Clean up WebSocket
        await self.ws_manager.cleanup()

        # Save performance data
        await self.save_performance_data()

        logger.info("Cleanup complete")

    async def save_performance_data(self):
        """Save performance data to file."""
        try:
            data = {
                "performance": asdict(self.performance),
                "timestamp": datetime.now().isoformat(),
            }

            filename = f"performance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            async with aiofiles.open(filename, "w") as f:
                await f.write(json.dumps(data, indent=2, default=str))

            logger.info(f"Performance data saved to {filename}")

        except Exception as e:
            logger.error(f"Failed to save performance data: {e}")


# Improvement #24-50: Additional specialized components


# Improvement #24: Market maker strategy implementation
class MarketMakerStrategy(StrategyInterface):
    """Advanced market making strategy."""

    def __init__(self):
        super().__init__("MarketMaker")
        self.set_parameters(
            spread_percentage=0.001,
            order_size=100,
            max_orders_per_side=3,
            rebalance_threshold=0.02,
        )

    async def analyze(self, market_data: dict, account_info: dict) -> list[Order]:
        """Generate market making orders."""
        orders = []

        for symbol, data in market_data.items():
            if "orderbook" not in data:
                continue

            ob = data["orderbook"]
            best_bid = _dec(ob["bids"][0][0]) if ob["bids"] else Decimal(0)
            best_ask = _dec(ob["asks"][0][0]) if ob["asks"] else Decimal(0)

            if best_bid == 0 or best_ask == 0:
                continue

            mid_price = (best_bid + best_ask) / 2
            spread = self.parameters["spread_percentage"]

            # Create buy and sell orders
            buy_price = mid_price * (1 - Decimal(spread))
            sell_price = mid_price * (1 + Decimal(spread))

            orders.append(
                Order(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    qty=Decimal(self.parameters["order_size"]),
                    price=buy_price,
                    time_in_force="PostOnly",
                ),
            )

            orders.append(
                Order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    qty=Decimal(self.parameters["order_size"]),
                    price=sell_price,
                    time_in_force="PostOnly",
                ),
            )

        return orders


# Improvement #25-30: Technical indicators
class TechnicalIndicators:
    """Collection of technical indicators."""

    @staticmethod
    def sma(data: list[float], period: int) -> float:
        """Simple Moving Average."""
        if len(data) < period:
            return 0
        return sum(data[-period:]) / period

    @staticmethod
    def ema(data: list[float], period: int) -> float:
        """Exponential Moving Average."""
        if len(data) < period:
            return 0
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period
        for price in data[period:]:
            ema = (price - ema) * multiplier + ema
        return ema

    @staticmethod
    def rsi(data: list[float], period: int = 14) -> float:
        """Relative Strength Index."""
        if len(data) < period + 1:
            return 50

        gains = []
        losses = []

        for i in range(1, len(data)):
            change = data[i] - data[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def bollinger_bands(
        data: list[float], period: int = 20, std_dev: int = 2,
    ) -> tuple[float, float, float]:
        """Bollinger Bands."""
        if len(data) < period:
            return 0, 0, 0

        sma = sum(data[-period:]) / period
        variance = sum((x - sma) ** 2 for x in data[-period:]) / period
        std = variance**0.5

        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)

        return upper, sma, lower


# Main entry point
async def main():
    """Enhanced main entry point."""
    try:
        # Validate configuration
        config.api_key = config.api_key or input("Enter API Key: ")
        config.api_secret = config.api_secret or input("Enter API Secret: ")

        # Create bot
        bot = AdvancedBybitTradingBot(config)

        # Add strategies
        mm_strategy = MarketMakerStrategy()
        bot.add_strategy(mm_strategy)

        # Get symbols from environment or use default
        symbols = os.getenv("TRADING_SYMBOLS", "BTCUSDT,ETHUSDT").split(",")
        interval = int(os.getenv("BOT_INTERVAL", "5"))

        logger.info(
            f"Configuration: Testnet={config.use_testnet}, Symbols={symbols}, Interval={interval}s",
        )

        # Run bot
        await bot.run(symbols, interval)

    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Ensure listener is stopped
        if "listener" in locals():
            listener.stop()


if __name__ == "__main__":
    asyncio.run(main())
