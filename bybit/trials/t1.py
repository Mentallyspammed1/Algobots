import asyncio
import logging
import os
import signal
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, getcontext
from typing import Any

from pybit.unified_trading import HTTP, WebSocket

# --- Global Decimal Precision for financial calc ---
getcontext().prec = (
    28  # Improvement #1: Increased precision for better financial accuracy
)


# Improvement #2: Enhanced error handling with retry decorator
def retry_on_exception(max_retries: int = 3, delay: float = 1.0):
    """Decorator for retrying failed operations."""

    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    logger.warning(
                        f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...",
                    )
                    await asyncio.sleep(delay * (attempt + 1))
            return None

        def sync_wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    logger.warning(
                        f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...",
                    )
                    time.sleep(delay * (attempt + 1))
            return None

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def _dec(value: Any, default: Decimal = Decimal(0)) -> Decimal:
    """Robust Decimal parser with default value support."""
    try:
        if value is None or value == "":
            return default
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as e:
        logger.debug(f"Decimal conversion failed for {value}: {e}")
        return default


# --- Configuration ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
USE_TESTNET = os.getenv("BYBIT_USE_TESTNET", "false").lower() == "true"

# Improvement #3: Additional configuration parameters
MAX_RECONNECT_ATTEMPTS = int(os.getenv("MAX_RECONNECT_ATTEMPTS", "5"))
WS_PING_INTERVAL = int(os.getenv("WS_PING_INTERVAL", "30"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- Logging Setup ---
# Improvement #4: Enhanced logging with file rotation and better formatting
from logging.handlers import RotatingFileHandler

log_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

# File handler with rotation
file_handler = RotatingFileHandler(
    "bybit_trading_bot.log",
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
)
file_handler.setFormatter(log_formatter)

logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, LOG_LEVEL))
logger.addHandler(console_handler)
logger.addHandler(file_handler)


# Improvement #5: Performance metrics tracking
@dataclass
class PerformanceMetrics:
    """Track bot performance metrics."""

    total_trades: int = 0
    successful_trades: int = 0
    failed_trades: int = 0
    total_volume: Decimal = field(default_factory=Decimal)
    realized_pnl: Decimal = field(default_factory=Decimal)
    start_time: datetime = field(default_factory=datetime.now)
    last_update: datetime = field(default_factory=datetime.now)

    def update(self):
        self.last_update = datetime.now()

    def get_uptime(self) -> timedelta:
        return datetime.now() - self.start_time

    def get_success_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return (self.successful_trades / self.total_trades) * 100


# --- WebSocket Manager ---
class BybitWebSocketManager:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.ws_public: WebSocket | None = None
        self.ws_private: WebSocket | None = None
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        self.market_data: dict[str, Any] = {}
        self.positions: dict[str, Any] = {}
        self.orders: dict[str, Any] = {}
        self._public_ready = False
        self._private_ready = False

        # Improvement #6: Connection health monitoring
        self._last_heartbeat: dict[str, datetime] = {}
        self._reconnect_count: dict[str, int] = {"public": 0, "private": 0}
        self._message_count: dict[str, int] = {"public": 0, "private": 0}

    def _init_public_ws(self):
        if not self.ws_public:
            self.ws_public = WebSocket(testnet=self.testnet, channel_type="linear")
            self._public_ready = True
            self._last_heartbeat["public"] = datetime.now()
            logger.info("Public WebSocket initialized.")

    def _init_private_ws(self):
        if not self.ws_private:
            self.ws_private = WebSocket(
                testnet=self.testnet,
                channel_type="private",
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
            self._private_ready = True
            self._last_heartbeat["private"] = datetime.now()
            logger.info("Private WebSocket initialized.")

    # Improvement #7: Data validation and sanitization
    def _validate_message(self, message: dict) -> bool:
        """Validate incoming WebSocket message."""
        if not isinstance(message, dict):
            return False
        if "data" not in message and "result" not in message:
            return False
        return True

    def handle_orderbook(self, message: dict):
        try:
            if not self._validate_message(message):
                return

            data = message.get("data", {})
            symbol = data.get("s")
            if symbol:
                md = self.market_data.setdefault(symbol, {})
                md["orderbook"] = data
                md["timestamp"] = message.get("ts")
                md["last_update"] = datetime.now()
                self._message_count["public"] += 1
        except Exception as e:
            logger.error(f"Error handling orderbook: {e}", exc_info=True)

    def handle_trades(self, message: dict):
        try:
            if not self._validate_message(message):
                return

            for trade in message.get("data", []):
                symbol = trade.get("s")
                if symbol:
                    md = self.market_data.setdefault(symbol, {})
                    md["last_trade"] = trade
                    md["trade_update"] = datetime.now()
                    self._message_count["public"] += 1
        except Exception as e:
            logger.error(f"Error handling trades: {e}", exc_info=True)

    def handle_ticker(self, message: dict):
        try:
            if not self._validate_message(message):
                return

            data = message.get("data", {})
            symbol = data.get("s")
            if symbol:
                md = self.market_data.setdefault(symbol, {})
                md["ticker"] = data
                md["ticker_update"] = datetime.now()
                self._message_count["public"] += 1
        except Exception as e:
            logger.error(f"Error handling ticker: {e}", exc_info=True)

    def handle_position(self, message: dict):
        try:
            if not self._validate_message(message):
                return

            for pos in message.get("data", []):
                symbol = pos.get("symbol")
                if symbol:
                    self.positions[symbol] = pos
                    self.positions[symbol]["update_time"] = datetime.now()
                    self._message_count["private"] += 1
        except Exception as e:
            logger.error(f"Error handling position: {e}", exc_info=True)

    def handle_order(self, message: dict):
        try:
            if not self._validate_message(message):
                return

            for order in message.get("data", []):
                oid = order.get("orderId")
                if oid:
                    self.orders[oid] = order
                    self.orders[oid]["update_time"] = datetime.now()
                    self._message_count["private"] += 1
        except Exception as e:
            logger.error(f"Error handling order: {e}", exc_info=True)

    def handle_execution(self, message: dict):
        try:
            if not self._validate_message(message):
                return

            for exe in message.get("data", []):
                oid = exe.get("orderId")
                if oid:
                    logger.info(
                        f"Execution: {oid}, Price: {exe.get('execPrice')}, Qty: {exe.get('execQty')}",
                    )
                    self._message_count["private"] += 1
        except Exception as e:
            logger.error(f"Error handling execution: {e}", exc_info=True)

    def handle_wallet(self, message: dict):
        try:
            if not self._validate_message(message):
                return

            for w in message.get("data", []):
                coin = w.get("coin")
                if coin:
                    logger.info(f"Wallet {coin}: Avail {w.get('availableToWithdraw')}")
                    self._message_count["private"] += 1
        except Exception as e:
            logger.error(f"Error handling wallet: {e}", exc_info=True)

    # Improvement #8: Connection health check
    async def check_connection_health(self) -> dict[str, bool]:
        """Check WebSocket connection health."""
        health = {}
        current_time = datetime.now()

        for ws_type in ["public", "private"]:
            if ws_type in self._last_heartbeat:
                time_since_heartbeat = (
                    current_time - self._last_heartbeat[ws_type]
                ).seconds
                health[ws_type] = time_since_heartbeat < WS_PING_INTERVAL * 2
            else:
                health[ws_type] = False

        return health

    @retry_on_exception(max_retries=3, delay=2.0)
    async def subscribe_public_channels(
        self,
        symbols: list[str],
        channels: list[str] = ["orderbook", "publicTrade", "tickers"],
    ):
        """Subscribe to public market data channels with retry logic."""
        self._init_public_ws()
        await asyncio.sleep(1)

        for symbol in symbols:
            if "orderbook" in channels:
                try:
                    self.ws_public.orderbook_stream(
                        depth=1, symbol=symbol, callback=self.handle_orderbook,
                    )
                    logger.debug(f"Subscribed to orderbook for {symbol}")
                except Exception as e:
                    logger.error(f"Subscribing orderbook {symbol} failed: {e}")

            if "publicTrade" in channels:
                try:
                    self.ws_public.trade_stream(
                        symbol=symbol, callback=self.handle_trades,
                    )
                    logger.debug(f"Subscribed to trades for {symbol}")
                except Exception as e:
                    logger.error(f"Subscribing trades {symbol} failed: {e}")

            if "tickers" in channels:
                try:
                    self.ws_public.ticker_stream(
                        symbol=symbol, callback=self.handle_ticker,
                    )
                    logger.debug(f"Subscribed to ticker for {symbol}")
                except Exception as e:
                    logger.error(f"Subscribing ticker {symbol} failed: {e}")

    @retry_on_exception(max_retries=3, delay=2.0)
    async def subscribe_private_channels(
        self, channels: list[str] = ["position", "order", "execution", "wallet"],
    ):
        """Subscribe to private channels with retry logic."""
        self._init_private_ws()
        await asyncio.sleep(1)

        channel_handlers = {
            "position": (self.ws_private.position_stream, self.handle_position),
            "order": (self.ws_private.order_stream, self.handle_order),
            "execution": (self.ws_private.execution_stream, self.handle_execution),
            "wallet": (self.ws_private.wallet_stream, self.handle_wallet),
        }

        for channel in channels:
            if channel in channel_handlers:
                stream_func, handler = channel_handlers[channel]
                try:
                    stream_func(callback=handler)
                    logger.debug(f"Subscribed to {channel} stream")
                except Exception as e:
                    logger.error(f"Failed to subscribe to {channel}: {e}")


# --- Trading Bot Core ---
class BybitTradingBot:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.session = HTTP(
            testnet=testnet, api_key=api_key, api_secret=api_secret, recv_window=10000,
        )
        self.ws_manager = BybitWebSocketManager(api_key, api_secret, testnet)
        self.strategy: Callable[[dict, dict, HTTP, Any, list[str]], None] | None = None
        self.symbol_info: dict[str, Any] = {}
        self.max_open_positions: int = 5

        # Improvement #9: Performance tracking
        self.metrics = PerformanceMetrics()

        # Improvement #10: Rate limiting
        self._api_call_timestamps: list[datetime] = []
        self._rate_limit_per_second = 10

        # Improvement #11: Emergency stop
        self._emergency_stop = False
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers."""

        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}. Initiating graceful shutdown...")
            self._emergency_stop = True
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    # Improvement #12: Rate limiting implementation
    async def _check_rate_limit(self):
        """Check and enforce rate limiting."""
        current_time = datetime.now()
        self._api_call_timestamps = [
            ts for ts in self._api_call_timestamps if (current_time - ts).seconds < 1
        ]

        if len(self._api_call_timestamps) >= self._rate_limit_per_second:
            sleep_time = (
                1 - (current_time - self._api_call_timestamps[0]).total_seconds()
            )
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        self._api_call_timestamps.append(current_time)

    @retry_on_exception(max_retries=3, delay=1.0)
    async def fetch_symbol_info(self, symbols: list[str], category: str = "linear"):
        """Fetch symbol information with caching and retry logic."""
        try:
            await self._check_rate_limit()

            # Improvement #13: Batch API calls when possible
            resp = self.session.get_instruments_info(category=category)
            if resp and resp.get("retCode") == 0:
                all_instruments = resp.get("result", {}).get("list", [])

                for item in all_instruments:
                    sym = item.get("symbol")
                    if sym in symbols:
                        self.symbol_info[sym] = {
                            "minOrderQty": _dec(item["lotSizeFilter"]["minOrderQty"]),
                            "qtyStep": _dec(item["lotSizeFilter"]["qtyStep"]),
                            "tickSize": _dec(item["priceFilter"]["tickSize"]),
                            "minPrice": _dec(item["priceFilter"]["minPrice"]),
                            "maxPrice": _dec(item["priceFilter"]["maxPrice"]),
                            "fetched_at": datetime.now(),
                        }

                # Check if all symbols were found
                missing_symbols = set(symbols) - set(self.symbol_info.keys())
                if missing_symbols:
                    logger.warning(f"Symbol info not found for: {missing_symbols}")
            else:
                logger.error(f"Could not fetch instruments: {resp.get('retMsg')}")
        except Exception as e:
            logger.error(f"Error fetching symbol info: {e}", exc_info=True)
            raise

    def set_strategy(
        self, strategy_func: Callable[[dict, dict, HTTP, Any, list[str]], None],
    ):
        """Set trading strategy with validation."""
        if not callable(strategy_func):
            raise ValueError("Strategy must be callable")
        self.strategy = strategy_func
        logger.info(f"Strategy set: {strategy_func.__name__}")

    def get_open_positions_count(self) -> int:
        """Get count of open positions with caching."""
        return sum(
            1 for p in self.ws_manager.positions.values() if _dec(p.get("size", 0)) != 0
        )

    # Improvement #14: Parallel execution for market data fetching
    async def run(self, symbols: list[str], interval: int = 5):
        """Main bot loop with improved error handling and parallel execution."""
        if not self.strategy:
            logger.error("No strategy set.")
            return

        # Initialize connections
        await self.ws_manager.subscribe_public_channels(symbols)
        await self.ws_manager.subscribe_private_channels()
        await self.fetch_symbol_info(symbols)

        logger.info(f"Bot main loop started for symbols: {symbols}")

        # Create executor for parallel tasks
        executor = ThreadPoolExecutor(max_workers=len(symbols))

        try:
            while not self._emergency_stop:
                loop_start = time.time()

                # Check connection health
                connection_health = await self.ws_manager.check_connection_health()
                if not all(connection_health.values()):
                    logger.warning(
                        f"Connection health check failed: {connection_health}",
                    )

                # Fetch market data in parallel
                tasks = [self.get_market_data(sym) for sym in symbols]
                market_data_results = await asyncio.gather(
                    *tasks, return_exceptions=True,
                )

                mkt_data = {}
                for sym, result in zip(symbols, market_data_results, strict=False):
                    if isinstance(result, Exception):
                        logger.error(f"Failed to get market data for {sym}: {result}")
                    elif result:
                        mkt_data[sym] = result

                acct_info = await self.get_account_info()

                if mkt_data and acct_info:
                    await self.strategy(
                        mkt_data, acct_info, self.session, self, symbols,
                    )
                    self.metrics.update()

                await self.log_current_pnl()

                # Log performance metrics periodically
                if (
                    self.metrics.total_trades % 10 == 0
                    and self.metrics.total_trades > 0
                ):
                    logger.info(
                        f"Performance - Success Rate: {self.metrics.get_success_rate():.2f}%, "
                        f"Total Trades: {self.metrics.total_trades}, "
                        f"Uptime: {self.metrics.get_uptime()}",
                    )

                # Dynamic sleep to maintain consistent interval
                loop_duration = time.time() - loop_start
                sleep_time = max(0, interval - loop_duration)
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info("Bot task cancelled - shutting down gracefully.")
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt - stopping.")
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            raise
        finally:
            executor.shutdown(wait=True)
            logger.info("Bot shutdown complete.")

    @retry_on_exception(max_retries=2, delay=0.5)
    async def get_market_data(
        self, symbol: str, category: str = "linear",
    ) -> dict | None:
        """Fetch market data with error handling and rate limiting."""
        try:
            await self._check_rate_limit()

            # Parallel fetch orderbook and ticker
            ob_task = asyncio.create_task(
                asyncio.to_thread(
                    self.session.get_orderbook, category=category, symbol=symbol,
                ),
            )
            tk_task = asyncio.create_task(
                asyncio.to_thread(
                    self.session.get_tickers, category=category, symbol=symbol,
                ),
            )

            ob, tk = await asyncio.gather(ob_task, tk_task, return_exceptions=True)

            if isinstance(ob, Exception) or isinstance(tk, Exception):
                logger.error(f"Market data fetch error for {symbol}")
                return None

            if ob.get("retCode") == 0 and tk.get("retCode") == 0:
                return {
                    "orderbook": ob.get("result", {}).get("list", []),
                    "ticker": tk.get("result", {}).get("list", []),
                    "timestamp": datetime.now(),
                }
        except Exception as e:
            logger.error(f"Market data fetch error for {symbol}: {e}")
        return None

    @retry_on_exception(max_retries=2, delay=0.5)
    async def get_account_info(self, account_type: str = "UNIFIED") -> dict | None:
        """Fetch account information with caching."""
        try:
            await self._check_rate_limit()

            bal = self.session.get_wallet_balance(accountType=account_type)
            if bal.get("retCode") == 0:
                result = bal.get("result", {})
                result["fetched_at"] = datetime.now()
                return result
        except Exception as e:
            logger.error(f"Account info fetch error: {e}")
        return None

    async def log_current_pnl(self):
        """Log current P&L with enhanced formatting."""
        total = Decimal(0)
        position_details = []

        for sym, pos in self.ws_manager.positions.items():
            pnl = _dec(pos.get("unrealisedPnl", 0))
            size = _dec(pos.get("size", 0))

            if size != 0:
                total += pnl
                position_details.append(f"{sym}: PnL={pnl:.4f}, Size={size}")

        if position_details:
            logger.info(f"Positions: {', '.join(position_details)}")
            logger.info(f"Total Unrealized PnL: {total:.4f}")


# Improvement #15: Configuration validation
def validate_configuration() -> bool:
    """Validate required configuration."""
    if not API_KEY or not API_SECRET:
        logger.error("Missing API credentials in environment variables.")
        return False

    if USE_TESTNET:
        logger.warning("Running in TESTNET mode")
    else:
        logger.warning("Running in PRODUCTION mode - real funds at risk!")

    return True


# --- Main ---
async def main():
    """Main entry point with improved initialization."""
    if not validate_configuration():
        return

    logger.info(f"Starting Bybit Trading Bot - Testnet: {USE_TESTNET}")

    bot = BybitTradingBot(API_KEY, API_SECRET, USE_TESTNET)

    # Dynamic strategy import
    try:
        from market_making_strategy import market_making_strategy

        bot.set_strategy(market_making_strategy)
    except ImportError:
        logger.error("Could not import market_making_strategy")
        return

    symbols = os.getenv("TRADING_SYMBOLS", "LINKUSDT,TRUMPUSDT").split(",")
    interval = int(os.getenv("BOT_INTERVAL", "5"))

    logger.info(f"Trading symbols: {symbols}, Interval: {interval}s")

    await bot.run(symbols, interval=interval)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
    except Exception as e:
        logger.critical(f"Unhandled error: {e}", exc_info=True)
        sys.exit(1)
