import asyncio
import logging
import os
import signal
import statistics
import time
import uuid
import warnings
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import (
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_UP,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    getcontext,
)
from pathlib import Path
from typing import Any, Literal

import orjson as json

# --- Third-party deps ---
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from rich.console import Console
from rich.live import Live
from rich.logging import RichHandler
from rich.table import Table
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# --- Optional TA deps (pandas + pandas_ta) ---
try:
    import pandas as pd
    import pandas_ta as pta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    pd = None
    pta = None
    PANDAS_TA_AVAILABLE = False
    warnings.warn("pandas or pandas_ta not found. Technical analysis features will be disabled.", ImportWarning)

# Optional: suppress pkg_resources deprecation warnings from dependencies
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pkg_resources")
warnings.filterwarnings("ignore", message="The pytz module is deprecated", module="pandas")

# Set Decimal precision
getcontext().prec = 30 # High precision for intermediate calculations

# =========================
# Logging setup (with symbol context)
# =========================
console = Console()

# Custom LogRecord factory to add 'symbol' attribute
_old_factory = logging.getLogRecordFactory()
def _record_factory(*args, **kwargs):
    record = _old_factory(*args, **kwargs)
    if not hasattr(record, "symbol"):
        record.symbol = "-"
    return record
logging.setLogRecordFactory(_record_factory)

# Rich logging handler configuration
logging.basicConfig(
    level="INFO",
    format="[%(asctime)s] [%(levelname)s] [%(symbol)s] %(message)s",
    datefmt="[%X]",
    handlers=[
        RichHandler(
            markup=True,
            rich_tracebacks=True,
            show_time=True,
            show_level=True,
            log_time_format="%H:%M:%S.%f", # Millisecond precision for log times
            console=console
        )
    ]
)
logger = logging.getLogger("rich")

class ContextFilter(logging.Filter):
    """A logging filter to inject a symbol into log records."""
    def __init__(self, symbol: str):
        super().__init__()
        self.symbol = symbol

    def filter(self, record):
        record.symbol = self.symbol
        return True

# =========================
# Helpers: Decimal math, rounding, tolerances
# =========================
def to_decimal(value: Any, default: str = "0") -> Decimal:
    """Safely converts a value to Decimal."""
    if value is None or value == "":
        return Decimal(default)
    try:
        return Decimal(str(value))
    except InvalidOperation:
        logger.warning(f"Could not convert '{value}' to Decimal. Using default '{default}'.")
        return Decimal(default)

def clamp_decimal(x: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    """Clamps a Decimal value between a lower and upper bound."""
    return min(hi, max(lo, x))

def round_to_increment(x: Decimal, inc: Decimal, rounding=ROUND_HALF_UP) -> Decimal:
    """Rounds a Decimal value to the nearest increment."""
    if inc <= 0:
        return x
    try:
        # Use quantize for more robust rounding with Decimal
        return (x / inc).quantize(Decimal("1"), rounding=rounding) * inc
    except (InvalidOperation, DivisionByZero):
        logger.debug(f"Rounding error for {x} with increment {inc}. Returning original.")
        return x

def floor_to_increment(x: Decimal, inc: Decimal) -> Decimal:
    """Floors a Decimal value to the nearest increment."""
    return round_to_increment(x, inc, rounding=ROUND_FLOOR)

def ceil_to_increment(x: Decimal, inc: Decimal) -> Decimal:
    """Ceils a Decimal value to the nearest increment."""
    return round_to_increment(x, inc, rounding=ROUND_CEILING)

def approx_equal(a: Decimal, b: Decimal, tol: Decimal) -> bool:
    """Checks if two Decimal values are approximately equal within a tolerance."""
    return abs(a - b) <= tol

# =========================
# Configuration with Pydantic
# =========================
class BaseConfigModel(BaseModel):
    """Base model for configuration with Decimal validation."""
    model_config = ConfigDict(arbitrary_types_allowed=True, json_dumps=json.dumps, json_loads=json.loads)

    @field_validator('*', mode='before')
    @classmethod
    def convert_to_decimal_if_needed(cls, v, info):
        # Dynamically check if the field's annotation is Decimal
        # Pydantic V2 compatibility: Use info.field_name to get field details
        if info.field_name and cls.model_fields[info.field_name].annotation == Decimal and isinstance(v, (int, float, str)):
            return to_decimal(v)
        return v

class CredentialsConfig(BaseConfigModel):
    api_key: str = Field(..., min_length=1)
    api_secret: str = Field(..., min_length=1)

class MarketConfig(BaseConfigModel):
    symbol: str = Field(..., pattern=r"^[A-Z0-9]{5,15}$") # e.g., BTCUSDT
    testnet: bool = False
    dry_run: bool = False

class OrderManagementConfig(BaseConfigModel):
    base_order_size: Decimal = Field(..., gt=0)
    order_tiers: int = Field(..., ge=1, le=10)
    tier_spread_increase_bps: Decimal = Field(..., ge=0) # Basis points increase per tier
    tier_qty_multiplier: Decimal = Field(..., ge=0)
    order_reprice_delay_seconds: float = Field(..., gt=0.1)
    price_tolerance_ticks: Decimal = Field(Decimal("0.5"), ge=0) # Reprice if new price is more than N ticks away
    qty_tolerance_steps: Decimal = Field(Decimal("0"), ge=0) # Reprice if new qty is more than N steps away
    mid_drift_threshold_ticks: Decimal = Field(Decimal("0.5"), ge=0) # If mid price drifts this much from last known mid, reprice
    min_order_reprice_interval_ms: int = Field(200, ge=50, le=5000) # Minimum interval between reprice events
    max_outstanding_orders_per_side: int = Field(50, ge=1, le=100) # Max active orders per side

class RiskManagementConfig(BaseConfigModel):
    max_position_size: Decimal = Field(..., gt=0)
    take_profit_pct: Decimal = Field(..., gt=0) # E.g., 0.005 for 0.5%
    stop_loss_pct: Decimal = Field(..., gt=0)   # E.g., 0.01 for 1%
    circuit_breaker_threshold: int = Field(..., gt=0) # Consecutive API failures
    circuit_breaker_cooldown_seconds: float = Field(..., gt=0)
    max_daily_loss_pct: Decimal = Field(Decimal("0.05"), gt=0, lt=1) # E.g., 0.05 for 5% daily loss

class StrategyConfig(BaseConfigModel):
    base_spread_percentage: Decimal = Field(..., gt=0) # E.g., 0.001 for 0.1% spread
    volatility_spread_multiplier: Decimal = Field(Decimal("0"), ge=0)
    inventory_skew_intensity: Decimal = Field(Decimal("0"), ge=0, lt=1) # How much inventory pushes fair value
    inventory_skew_decay_rate_per_order: Decimal = Field(Decimal("0.1"), ge=0, lt=1) # How much skew decays with each order placed
    aggressiveness_multiplier: Decimal = Field(Decimal("1.0"), gt=0) # General multiplier for order sizes and spread
    max_spread_percentage: Decimal = Field(Decimal("0.05"), gt=0) # Cap the spread

class TechnicalConfig(BaseConfigModel):
    orderbook_depth: int = Field(20, ge=1, le=50) # WS orderbook depth
    vol_window_seconds: int = Field(60, ge=10) # Window for volatility calculation

class TAConfig(BaseConfigModel):
    enabled: bool = False
    rsi_length: int = Field(14, ge=2)
    ema_fast: int = Field(12, ge=2)
    ema_slow: int = Field(26, ge=2)
    bb_length: int = Field(20, ge=2)
    bb_std: float = Field(2.0, gt=0)
    signal_fair_value_bps: Decimal = Field(Decimal("2.0"), ge=0) # Max BPS shift from RSI signal
    bb_spread_mult: Decimal = Field(Decimal("0.5"), ge=0)       # Multiplier for BB width to spread
    qty_bias_max: Decimal = Field(Decimal("0.5"), ge=0, lt=1)    # Max +/- percentage change in quantity
    ema_cross_signal_multiplier: Decimal = Field(Decimal("0.1"), ge=0) # How much EMA cross impacts fair value
    rsi_overbought_threshold: Decimal = Field(Decimal("70"), ge=50, lt=100)
    rsi_oversold_threshold: Decimal = Field(Decimal("30"), gt=0, le=50)
    rsi_reversal_fair_value_bps: Decimal = Field(Decimal("5.0"), ge=0) # Max BPS shift on strong RSI reversal

    @model_validator(mode='after')
    def check_ta_availability(self) -> 'TAConfig':
        if self.enabled and not PANDAS_TA_AVAILABLE:
            warnings.warn("TA enabled in config but pandas/pandas_ta not installed. TA features will be disabled.", RuntimeWarning)
            self.enabled = False
        return self

class BotConfig(BaseConfigModel):
    credentials: CredentialsConfig
    market: MarketConfig
    order_management: OrderManagementConfig
    risk_management: RiskManagementConfig
    strategy: StrategyConfig
    technical: TechnicalConfig
    ta: TAConfig = Field(default_factory=TAConfig)

# =========================
# Data Structures & State
# =========================
@dataclass
class InstrumentInfo:
    tick_size: Decimal
    step_size: Decimal
    min_order_size: Decimal
    price_precision: int = field(init=False)
    qty_precision: int = field(init=False)

    def __post_init__(self):
        self.price_precision = max(0, abs(self.tick_size.as_tuple().exponent))
        self.qty_precision = max(0, abs(self.step_size.as_tuple().exponent))

@dataclass
class BotState:
    instrument_info: InstrumentInfo | None = None
    recent_prices: deque[tuple[Decimal, float]] = field(default_factory=lambda: deque(maxlen=10000)) # (price, timestamp)
    last_mid_price: Decimal | None = None
    last_known_best_bid: Decimal | None = None
    last_known_best_ask: Decimal | None = None
    daily_pnl_start_balance: Decimal = Decimal("0") # For daily loss tracking
    session_start_time: float = field(default_factory=time.time)
    daily_pnl_snapshot_time: datetime = field(default_factory=datetime.now)

@dataclass
class OrderTracker:
    order_id: str
    price: Decimal
    qty: Decimal
    side: Literal["Buy", "Sell"]
    is_virtual: bool = False
    timestamp: float = field(default_factory=time.time)
    order_link_id: str | None = None # To link place_batch_order responses

# =========================
# Bybit API Client (HTTP)
# =========================
class BybitHTTPClient:
    def __init__(self, config: BotConfig):
        self.config = config
        self.symbol = self.config.market.symbol
        self.testnet = self.config.market.testnet
        self.session = HTTP(
            testnet=self.testnet,
            api_key=self.config.credentials.api_key,
            api_secret=self.config.credentials.api_secret,
            recv_window=10000,
            timeout=30
        )
        self.circuit_breaker_active: bool = False
        self.consecutive_api_failures: int = 0
        self.rate_limit_backoff_sec: float = 2.0
        self.max_backoff_sec: float = 60.0 # Increased max backoff
        self.api_call_semaphore = asyncio.Semaphore(5) # Limit concurrent API calls to Bybit
        self.last_api_call_time: float = 0.0
        self.min_api_call_interval: float = 0.1 # To avoid spamming on retries/bursts

    async def _safe_api_call(self, method, *args, **kwargs):
        """
        Wrapper for Bybit API calls with retries, rate limiting, and circuit breaker.
        Uses asyncio.to_thread because pybit's HTTP client is blocking.
        """
        if self.circuit_breaker_active:
            logger.warning(f"API call to {method.__name__} blocked by circuit breaker.")
            return None

        async for attempt in AsyncRetrying(
            wait=wait_exponential(multiplier=1, min=self.rate_limit_backoff_sec, max=self.max_backoff_sec),
            stop=stop_after_attempt(self.config.risk_management.circuit_breaker_threshold),
            retry=retry_if_exception_type(Exception),
            reraise=True,
            before_sleep=before_sleep_log(logger, logging.WARNING, exc_info=False)
        ):
            with attempt:
                try:
                    now = time.time()
                    if (now - self.last_api_call_time) < self.min_api_call_interval:
                        await asyncio.sleep(self.min_api_call_interval - (now - self.last_api_call_time))

                    async with self.api_call_semaphore:
                        response = await asyncio.to_thread(method, *args, **kwargs)
                        self.last_api_call_time = time.time()

                    if response and response.get('retCode') == 0:
                        self.consecutive_api_failures = 0
                        self.rate_limit_backoff_sec = 2.0
                        return response['result']
                    else:
                        msg = response.get('retMsg', 'Unknown error') if response else "No response"
                        code = response.get('retCode') if response else None

                        if code == 10006 or (msg and "rate limit" in str(msg).lower()):
                            logger.warning(f"Rate limit hit ({method.__name__}). Retrying with backoff.")
                            raise Exception("Rate limit encountered")
                        elif code == 30042 or (msg and "order does not exist" in str(msg).lower()):
                            # Specific error for cancelling already filled/non-existent orders, not critical
                            logger.info(f"API Info ({method.__name__}): Order not found/already processed. {msg} (retCode: {code})")
                            return {'list': [{'orderId': kwargs.get('request', [{}])[0].get('orderId', 'unknown'), 'retCode': code, 'retMsg': msg}]} if 'cancel_batch_order' in method.__name__ else None
                        else:
                            logger.error(f"API Error ({method.__name__}): {msg} (retCode: {code})")
                            self.consecutive_api_failures += 1
                            await self._check_circuit_breaker()
                            return None

                except Exception as e:
                    logger.error(f"API request failed ({method.__name__}): {e}", exc_info=False)
                    self.consecutive_api_failures += 1
                    await self._check_circuit_breaker()
                    raise

        logger.critical(f"API call {method.__name__} failed after multiple retries. Circuit breaker likely active.")
        return None

    async def _check_circuit_breaker(self):
        """Activates circuit breaker if too many consecutive failures occur."""
        threshold = self.config.risk_management.circuit_breaker_threshold
        if self.consecutive_api_failures >= threshold:
            if not self.circuit_breaker_active:
                self.circuit_breaker_active = True
                logger.critical("[bold red]CIRCUIT BREAKER TRIGGERED[/bold red] due to excessive API failures.")
                cooldown = self.config.risk_management.circuit_breaker_cooldown_seconds
                logger.warning(f"Trading paused for {cooldown} seconds.")
                await asyncio.sleep(cooldown)
                self.consecutive_api_failures = 0
                self.circuit_breaker_active = False
                logger.info("[bold green]Circuit breaker reset. Resuming.[/bold green]")

    async def get_instrument_info(self) -> InstrumentInfo | None:
        """Fetches and parses instrument trading rules."""
        result = await self._safe_api_call(self.session.get_instruments_info, category='linear', symbol=self.symbol)
        if result and result.get('list'):
            info = result['list'][0]
            instrument_info = InstrumentInfo(
                tick_size=to_decimal(info['priceFilter']['tickSize'], "0.0001"),
                step_size=to_decimal(info['lotSizeFilter']['qtyStep'], "0.001"),
                min_order_size=to_decimal(info['lotSizeFilter']['minOrderQty'], "0.001")
            )
            logger.info(f"Instrument info: tick={instrument_info.tick_size}, step={instrument_info.step_size}, min={instrument_info.min_order_size}")
            return instrument_info
        logger.error(f"Failed to fetch instrument info for {self.symbol}")
        return None

    async def place_batch_orders(self, orders: list[dict]) -> list[dict]:
        """Places a batch of orders."""
        if not orders:
            return []

        # Assign orderLinkId if not present
        for o in orders:
            if 'orderLinkId' not in o:
                o['orderLinkId'] = f"mm_{uuid.uuid4().hex[:8]}"

        place_requests = [
            {
                "symbol": self.symbol,
                "side": o['side'],
                "orderType": "Limit",
                "qty": str(o['qty']),
                "price": str(o['price']),
                "orderLinkId": o['orderLinkId'],
                "timeInForce": "PostOnly",
                "reduceOnly": o.get('reduceOnly', False)
            } for o in orders
        ]
        result = await self._safe_api_call(self.session.place_batch_order, category="linear", request=place_requests)
        if result and result.get('list'):
            successes = [r for r in result['list'] if r.get('orderId')]
            failures = [r for r in result['list'] if not r.get('orderId')]
            if successes:
                logger.info(f"Placed {len(successes)}/{len(orders)} orders successfully.")
            if failures:
                logger.warning(f"Failed to place {len(failures)} orders: {failures}")
            return successes
        return []

    async def cancel_batch_orders(self, order_ids: list[str]) -> list[str]:
        """Cancels a batch of orders."""
        if not order_ids:
            return []
        cancel_requests = [{"symbol": self.symbol, "orderId": oid} for oid in order_ids]
        result = await self._safe_api_call(self.session.cancel_batch_order, category="linear", request=cancel_requests)
        if result and result.get('list'):
            successes = [r.get('orderId') for r in result['list'] if r.get('orderId')]
            failures = [r for r in result['list'] if not r.get('orderId')]
            if successes:
                logger.info(f"Cancelled {len(successes)}/{len(order_ids)} orders successfully.")
            if failures:
                # Log specific error for orders that might already be filled/cancelled
                for f in failures:
                    if f.get('retCode') == 30042: # Order does not exist
                        logger.debug(f"Order {f.get('orderId')} already cancelled or filled. {f.get('retMsg')}")
                    else:
                        logger.warning(f"Failed to cancel order {f.get('orderId')}: {f.get('retMsg')}")
            return successes
        return []

    async def close_position_market(self, side: Literal["Buy", "Sell"], qty: Decimal) -> bool:
        """Closes a position with a market order."""
        if qty <= 0:
            return False
        logger.warning(f"[bold yellow]Closing position via market order: {side} {qty}[/bold yellow]")
        result = await self._safe_api_call(
            self.session.place_order,
            category='linear',
            symbol=self.symbol,
            side=side,
            orderType='Market',
            qty=str(qty),
            reduceOnly=True
        )
        if result and result.get('orderId'):
            logger.info(f"Market close order placed: {side} {qty}")
            return True
        logger.error(f"Failed to close position: {side} {qty}. Result: {result}")
        return False

    async def cancel_all_orders(self) -> bool:
        """Cancels all active orders for the symbol."""
        result = await self._safe_api_call(self.session.cancel_all_orders, category='linear', symbol=self.symbol)
        if result:
            logger.info("All orders cancelled.")
            return True
        logger.error("Failed to cancel all orders.")
        return False

    async def get_wallet_balance(self, coin: str = "USDT") -> Decimal | None:
        """Fetches wallet balance for a specific coin."""
        result = await self._safe_api_call(self.session.get_wallet_balance, accountType='UNIFIED', coin=coin)
        if result and result.get('list'):
            for account in result['list']:
                for c in account['coin']:
                    if c['coin'] == coin:
                        return to_decimal(c['equity'])
        logger.error(f"Failed to fetch wallet balance for {coin}.")
        return None

# =========================
# Bybit WebSocket Manager
# =========================
class BybitWebSocketManager:
    def __init__(self, config: BotConfig, message_handler):
        self.config = config
        self.symbol = self.config.market.symbol
        self.testnet = self.config.market.testnet
        self.message_handler = message_handler
        self.public_ws: WebSocket | None = None
        self.private_ws: WebSocket | None = None
        self.main_event_loop: asyncio.AbstractEventLoop | None = None
        self._reconnect_lock = asyncio.Lock()
        self._public_monitor_task: asyncio.Task | None = None
        self._private_monitor_task: asyncio.Task | None = None

    def _ws_callback(self, message: dict):
        """
        Callback for pybit websockets. Runs in a separate thread.
        Dispatches to the main event loop for processing.
        """
        if self.main_event_loop and self.main_event_loop.is_running():
            try:
                # Use call_soon_threadsafe for immediate dispatch
                self.main_event_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self.message_handler(message))
                )
            except RuntimeError as e: # Catch case where loop is closing
                logger.warning(f"WS callback dispatch error (loop closing): {e}")
            except Exception as e:
                logger.error(f"WS callback dispatch error: {e}", exc_info=True)
        else:
            logger.warning("WS message received but main event loop not running or available.")

    async def _monitor_connection(self, ws: WebSocket, ws_type: str):
        """Monitors a WebSocket connection and attempts to reconnect on disconnection."""
        while True:
            await asyncio.sleep(5)
            if not ws.is_connected():
                logger.warning(f"{ws_type} WebSocket disconnected. Attempting to reconnect...")
                try:
                    await self.start_streams(force_reconnect=True)
                    logger.info(f"{ws_type} WebSocket reconnected successfully.")
                except Exception as e:
                    logger.error(f"Failed to reconnect {ws_type} WebSocket: {e}", exc_info=True)
                return # Exit this monitor, a new one will be spawned if successful

    async def start_streams(self, force_reconnect: bool = False):
        """Starts pybit-managed WebSocket subscriptions."""
        async with self._reconnect_lock:
            if not self.main_event_loop:
                self.main_event_loop = asyncio.get_running_loop()

            symbol = self.symbol
            depth = self.config.technical.orderbook_depth

            # Public WS
            if self.public_ws and self.public_ws.is_connected() and not force_reconnect:
                logger.debug("Public WS already connected.")
            else:
                if self.public_ws:
                    self.public_ws.exit()
                    if self._public_monitor_task:
                        self._public_monitor_task.cancel()
                        await asyncio.sleep(0.1) # Allow task to exit cleanly
                self.public_ws = WebSocket(testnet=self.testnet, channel_type="linear")
                try:
                    self.public_ws.orderbook_stream(depth=depth, symbol=symbol, callback=self._ws_callback)
                    self.public_ws.ticker_stream(symbol=symbol, callback=self._ws_callback)
                    logger.info("Public WS subscriptions set.")
                    self._public_monitor_task = asyncio.create_task(self._monitor_connection(self.public_ws, "Public"))
                except Exception as e:
                    logger.critical(f"Failed to start public WS subscriptions: {e}", exc_info=True)
                    raise

            # Private WS (only live trading, not dry run)
            if not self.config.market.dry_run:
                if self.private_ws and self.private_ws.is_connected() and not force_reconnect:
                    logger.debug("Private WS already connected.")
                else:
                    if self.private_ws:
                        self.private_ws.exit()
                        if self._private_monitor_task:
                            self._private_monitor_task.cancel()
                            await asyncio.sleep(0.1)
                    self.private_ws = WebSocket(
                        testnet=self.testnet,
                        channel_type="private",
                        api_key=self.config.credentials.api_key,
                        api_secret=self.config.credentials.api_secret
                    )
                    try:
                        self.private_ws.position_stream(callback=self._ws_callback)
                        self.private_ws.order_stream(callback=self._ws_callback)
                        self.private_ws.execution_stream(callback=self._ws_callback)
                        logger.info("Private WS subscriptions set.")
                        self._private_monitor_task = asyncio.create_task(self._monitor_connection(self.private_ws, "Private"))
                    except Exception as e:
                        logger.critical(f"Failed to start private WS subscriptions: {e}", exc_info=True)
                        raise
            else:
                if self.private_ws:
                    self.private_ws.exit()
                    if self._private_monitor_task:
                        self._private_monitor_task.cancel()
                    self.private_ws = None

    def stop_streams(self):
        """Stops all WebSocket connections."""
        if self.public_ws:
            self.public_ws.exit()
            self.public_ws = None
            if self._public_monitor_task:
                self._public_monitor_task.cancel()
            logger.info("Public WS stopped.")
        if self.private_ws:
            self.private_ws.exit()
            self.private_ws = None
            if self._private_monitor_task:
                self._private_monitor_task.cancel()
            logger.info("Private WS stopped.")

# =========================
# Technical Analysis Manager
# =========================
class TAManager:
    def __init__(self, config: TAConfig):
        self.config = config
        self.ta_state: dict[str, float | None] = {
            "rsi": None,
            "ema_fast": None,
            "ema_slow": None,
            "bb_width_pct": None,
            "macd": None,
            "macdh": None,
            "macds": None,
        }
        self.enabled = config.enabled

    def update_ta(self, prices_with_timestamps: deque[tuple[Decimal, float]]):
        """Computes technical indicators from a deque of (price, timestamp) tuples."""
        if not self.enabled or not PANDAS_TA_AVAILABLE:
            return

        try:
            prices = [float(p) for p, _ in prices_with_timestamps]
            if not prices:
                return

            rsi_len = self.config.rsi_length
            ema_fast = self.config.ema_fast
            ema_slow = self.config.ema_slow
            bb_len = self.config.bb_length
            bb_std = self.config.bb_std

            # For MACD
            macd_fast = self.config.ema_fast
            macd_slow = self.config.ema_slow
            macd_signal = 9 # Common default

            min_len = max(rsi_len, ema_slow, bb_len, macd_slow + macd_signal) + 2
            if len(prices) < min_len:
                logger.debug(f"Not enough price data for TA. Need {min_len}, have {len(prices)}")
                return

            s = pd.Series(prices, dtype="float64")

            # RSI
            rsi_series = pta.rsi(s, length=rsi_len)
            self.ta_state["rsi"] = float(rsi_series.iloc[-1]) if rsi_series is not None and not pd.isna(rsi_series.iloc[-1]) else None

            # EMA
            ema_f_series = pta.ema(s, length=ema_fast)
            ema_s_series = pta.ema(s, length=ema_slow)
            self.ta_state["ema_fast"] = float(ema_f_series.iloc[-1]) if ema_f_series is not None and not pd.isna(ema_f_series.iloc[-1]) else None
            self.ta_state["ema_slow"] = float(ema_s_series.iloc[-1]) if ema_s_series is not None and not pd.isna(ema_s_series.iloc[-1]) else None

            # Bollinger Bands Width Percentage
            bb = pta.bbands(s, length=bb_len, std=bb_std)
            bb_width_pct = None
            if bb is not None and not bb.empty:
                upper_col = [c for c in bb.columns if c.startswith("BBU_")]
                lower_col = [c for c in bb.columns if c.startswith("BBL_")]
                mid_col   = [c for c in bb.columns if c.startswith("BBM_")]
                if upper_col and lower_col and mid_col:
                    u, l, m = bb[upper_col[0]].iloc[-1], bb[lower_col[0]].iloc[-1], bb[mid_col[0]].iloc[-1]
                    if m and not any(pd.isna([u, l, m])):
                        bb_width_pct = float((u - l) / m) if m != 0 else None
            self.ta_state["bb_width_pct"] = bb_width_pct

            # MACD
            macd = pta.macd(s, fast=macd_fast, slow=macd_slow, signal=macd_signal)
            if macd is not None and not macd.empty:
                macd_col = [c for c in macd.columns if "MACD_" in c and c.endswith("_"+str(macd_fast))]
                hist_col = [c for c in macd.columns if "MACDH_" in c and c.endswith("_"+str(macd_fast))]
                signal_col = [c for c in macd.columns if "MACDS_" in c and c.endswith("_"+str(macd_fast))]
                if macd_col and hist_col and signal_col:
                    self.ta_state["macd"] = float(macd[macd_col[0]].iloc[-1]) if not pd.isna(macd[macd_col[0]].iloc[-1]) else None
                    self.ta_state["macdh"] = float(macd[hist_col[0]].iloc[-1]) if not pd.isna(macd[hist_col[0]].iloc[-1]) else None
                    self.ta_state["macds"] = float(macd[signal_col[0]].iloc[-1]) if not pd.isna(macd[signal_col[0]].iloc[-1]) else None

        except Exception as e:
            logger.warning(f"TA update failed: {e}", exc_info=False)

# =========================
# Order Manager
# =========================
class OrderManager:
    def __init__(self, bot_config: BotConfig, http_client: BybitHTTPClient, instrument_info: InstrumentInfo):
        self.config = bot_config
        self.http_client = http_client
        self.instrument_info = instrument_info

        self.active_orders: dict[str, OrderTracker] = {}
        self.virtual_orders: dict[str, OrderTracker] = {}
        self.last_reprice_time: float = 0.0

    @property
    def current_orders(self) -> dict[str, OrderTracker]:
        return self.virtual_orders if self.config.market.dry_run else self.active_orders

    def _format_price(self, p: Decimal) -> Decimal:
        return round_to_increment(p, self.instrument_info.tick_size, ROUND_HALF_UP)

    def _format_qty(self, q: Decimal) -> Decimal:
        q = floor_to_increment(q, self.instrument_info.step_size)
        return max(q, self.instrument_info.min_order_size)

    def _quotes_significantly_changed(self, current_quotes: list[tuple[Decimal, Decimal, str]], new_quotes: list[dict], mid_price: Decimal, last_known_mid: Decimal) -> bool:
        """Determines if the new set of quotes differs significantly from the current ones."""
        if len(current_quotes) != len(new_quotes):
            return True

        price_tol = self.instrument_info.tick_size * self.config.order_management.price_tolerance_ticks
        qty_tol = self.instrument_info.step_size * self.config.order_management.qty_tolerance_steps

        # Check mid-price drift
        if self.config.order_management.mid_drift_threshold_ticks > 0 and last_known_mid != Decimal("0"):
            price_drift_threshold = self.instrument_info.tick_size * self.config.order_management.mid_drift_threshold_ticks
            if not approx_equal(mid_price, last_known_mid, price_drift_threshold):
                logger.debug(f"Mid price drifted significantly (old: {last_known_mid}, new: {mid_price}), re-evaluating orders.")
                return True

        # Sort for consistent comparison (convert new_quotes to tuple format first)
        new_quotes_tuple = [(o['price'], o['qty'], o['side']) for o in new_quotes]

        current_sorted = sorted(current_quotes, key=lambda x: (x[2], x[0], x[1]))
        new_sorted = sorted(new_quotes_tuple, key=lambda x: (x[2], x[0], x[1]))

        for (cp, cq, cs), (np, nq, ns) in zip(current_sorted, new_sorted, strict=False):
            if cs != ns: # Should not happen if sorting is correct, but good safety
                return True
            if not approx_equal(cp, np, price_tol):
                return True
            if not approx_equal(cq, nq, qty_tol):
                return True
        return False

    async def manage_orders(self, desired_buy_orders: list[dict], desired_sell_orders: list[dict], mid_price: Decimal, last_known_mid: Decimal):
        """Compares desired orders with current open orders and updates accordingly."""
        now = time.time()
        if (now - self.last_reprice_time) < (self.config.order_management.min_order_reprice_interval_ms / 1000):
            return # Too soon for reprice

        new_target_orders = desired_buy_orders + desired_sell_orders
        current_open_orders_list = [(o.price, o.qty, o.side) for o in self.current_orders.values()]

        if not self._quotes_significantly_changed(current_open_orders_list, new_target_orders, mid_price, last_known_mid):
            return # No significant change, no action needed

        orders_to_cancel_ids = []
        orders_to_place_data = []

        # Identify orders to cancel (current orders not in new target)
        for order_id, current_order in self.current_orders.items():
            if not any(approx_equal(current_order.price, to['price'], self.instrument_info.tick_size * self.config.order_management.price_tolerance_ticks) and
                       approx_equal(current_order.qty, to['qty'], self.instrument_info.step_size * self.config.order_management.qty_tolerance_steps) and
                       current_order.side == to['side'] for to in new_target_orders):
                orders_to_cancel_ids.append(order_id)

        # Identify orders to place (new target orders not in current)
        for target_order in new_target_orders:
            if not any(approx_equal(target_order['price'], co.price, self.instrument_info.tick_size * self.config.order_management.price_tolerance_ticks) and
                       approx_equal(target_order['qty'], co.qty, self.instrument_info.step_size * self.config.order_management.qty_tolerance_steps) and
                       target_order['side'] == co.side for co in self.current_orders.values()):
                orders_to_place_data.append(target_order)

        # Apply max outstanding orders per side limit
        current_buy_orders = [o for o in self.current_orders.values() if o.side == 'Buy']
        current_sell_orders = [o for o in self.current_orders.values() if o.side == 'Sell']

        max_orders = self.config.order_management.max_outstanding_orders_per_side

        # Filter orders to place if limits would be exceeded
        filtered_orders_to_place = []
        temp_buy_count = len(current_buy_orders) - len([oid for oid in orders_to_cancel_ids if self.current_orders.get(oid) and self.current_orders[oid].side == 'Buy'])
        temp_sell_count = len(current_sell_orders) - len([oid for oid in orders_to_cancel_ids if self.current_orders.get(oid) and self.current_orders[oid].side == 'Sell'])

        for order_data in orders_to_place_data:
            if order_data['side'] == 'Buy' and temp_buy_count < max_orders:
                filtered_orders_to_place.append(order_data)
                temp_buy_count += 1
            elif order_data['side'] == 'Sell' and temp_sell_count < max_orders:
                filtered_orders_to_place.append(order_data)
                temp_sell_count += 1
            else:
                logger.debug(f"Skipping place order {order_data['side']} {order_data['price']} due to max_outstanding_orders_per_side limit.")

        if orders_to_cancel_ids or filtered_orders_to_place:
            if self.config.market.dry_run:
                self._execute_virtual_orders(orders_to_cancel_ids, filtered_orders_to_place)
            else:
                await self._execute_live_orders(orders_to_cancel_ids, filtered_orders_to_place)
            self.last_reprice_time = now

    def _execute_virtual_orders(self, orders_to_cancel_ids: list[str], orders_to_place_data: list[dict]):
        """Simulates order placement and cancellation for dry run."""
        if orders_to_cancel_ids or orders_to_place_data:
            logger.info(f"[DRY RUN] Orders: Cancelling {len(orders_to_cancel_ids)}, Placing {len(orders_to_place_data)}")

        for order_id in orders_to_cancel_ids:
            self.virtual_orders.pop(order_id, None)

        for order_data in orders_to_place_data:
            order_id = f"dryrun_{uuid.uuid4().hex[:8]}"
            self.virtual_orders[order_id] = OrderTracker(
                order_id=order_id,
                price=order_data['price'],
                qty=order_data['qty'],
                side=order_data['side'],
                is_virtual=True,
                order_link_id=order_data.get('orderLinkId') # Preserve if present
            )

    async def _execute_live_orders(self, orders_to_cancel_ids: list[str], orders_to_place_data: list[dict]):
        """Executes actual order placement and cancellation on the exchange."""
        if orders_to_cancel_ids or orders_to_place_data:
            logger.info(f"Executing: Cancelling {len(orders_to_cancel_ids)} orders, Placing {len(orders_to_place_data)} orders.")

        # Cancel orders first
        if orders_to_cancel_ids:
            cancelled_ids = await self.http_client.cancel_batch_orders(orders_to_cancel_ids)
            for oid in cancelled_ids:
                self.active_orders.pop(oid, None)

        # Place new orders
        if orders_to_place_data:
            placed_orders_info = await self.http_client.place_batch_orders(orders_to_place_data)
            for info in placed_orders_info:
                order_id = info.get('orderId')
                order_link_id = info.get('orderLinkId')
                if order_id:
                    original_order = next((o for o in orders_to_place_data if o.get('orderLinkId') == order_link_id), None)
                    if original_order:
                        self.active_orders[order_id] = OrderTracker(
                            order_id=order_id,
                            price=to_decimal(original_order['price']),
                            qty=to_decimal(original_order['qty']),
                            side=original_order['side'],
                            order_link_id=order_link_id
                        )

    async def cancel_all_open_orders(self):
        """Cancels all currently tracked orders."""
        if self.config.market.dry_run:
            if self.virtual_orders:
                logger.info(f"[DRY RUN] Cancelling {len(self.virtual_orders)} virtual orders.")
                self.virtual_orders.clear()
        else:
            if await self.http_client.cancel_all_orders():
                self.active_orders.clear()

    def update_from_websocket(self, order_data: dict):
        """Updates active orders based on WebSocket messages."""
        oid = order_data.get('orderId')
        status = order_data.get('orderStatus')
        if not oid:
            return

        if status in ['New', 'PartiallyFilled']:
            try:
                # Update existing or add new order
                self.active_orders[oid] = OrderTracker(
                    order_id=oid,
                    price=to_decimal(order_data['price']),
                    qty=to_decimal(order_data['qty']),
                    side=order_data['side'],
                    order_link_id=order_data.get('orderLinkId')
                )
            except Exception as e:
                logger.error(f"Error parsing order data from WS: {e}, data: {order_data}")
        elif status in ['Filled', 'Cancelled', 'Rejected']:
            if oid in self.active_orders:
                self.active_orders.pop(oid, None)
                logger.info(f"Order {oid} {status}.")

    def get_open_buy_qty(self) -> Decimal:
        return sum(o.qty for o in self.current_orders.values() if o.side == 'Buy')

    def get_open_sell_qty(self) -> Decimal:
        return sum(o.qty for o in self.current_orders.values() if o.side == 'Sell')

# =========================
# Position Manager
# =========================
class PositionManager:
    def __init__(self, bot_config: BotConfig, http_client: BybitHTTPClient, order_manager: OrderManager, bot_state: BotState):
        self.config = bot_config
        self.http_client = http_client
        self.order_manager = order_manager
        self.bot_state = bot_state # Reference to the shared bot state
        self.size: Decimal = Decimal("0")
        self.avg_entry_price: Decimal = Decimal("0")
        self.unrealized_pnl: Decimal = Decimal("0")
        self.realized_pnl: Decimal = Decimal("0")
        self.initial_balance: Decimal | None = None # To track daily loss
        self.last_balance_check_time: float = 0.0

    async def initialize_balance(self):
        """Fetches and sets the initial balance for daily PnL tracking."""
        if self.config.market.dry_run:
            self.initial_balance = Decimal("10000") # Start with a virtual balance
            self.bot_state.daily_pnl_start_balance = self.initial_balance
            logger.info(f"[DRY RUN] Initial virtual balance set to {self.initial_balance}")
            return

        balance = await self.http_client.get_wallet_balance(coin=self.config.market.symbol[:-4]) # e.g., BTCUSDT -> BTC
        if balance is None: # Fallback to USDT
             balance = await self.http_client.get_wallet_balance(coin="USDT")

        if balance is not None:
            self.initial_balance = balance
            self.bot_state.daily_pnl_start_balance = balance
            logger.info(f"Initial wallet balance for PnL tracking: {self.initial_balance:.4f}")
        else:
            logger.error("Could not fetch initial wallet balance. Daily PnL tracking will be limited.")
            self.initial_balance = Decimal("0")

    async def update_daily_pnl_snapshot(self):
        """Updates the daily PnL starting balance if a new day has started."""
        now = datetime.now()
        if now.date() > self.bot_state.daily_pnl_snapshot_time.date():
            current_balance = await self.http_client.get_wallet_balance(coin=self.config.market.symbol[:-4]) or await self.http_client.get_wallet_balance(coin="USDT")
            if current_balance is not None:
                self.bot_state.daily_pnl_start_balance = current_balance
                self.bot_state.daily_pnl_snapshot_time = now
                logger.info(f"Daily PnL snapshot updated. New start balance: {current_balance:.4f}")
            else:
                logger.warning("Failed to get current balance for daily PnL snapshot update.")

    def update_position(self, data: dict):
        """Updates position details from WebSocket (live) or simulates (dry-run)."""
        # Bybit's WS provides 'liqPrice', 'positionIdx' etc. but we only need core PnL info
        self.size = to_decimal(data.get('size'))
        self.avg_entry_price = to_decimal(data.get('avgPrice'))
        self.unrealized_pnl = to_decimal(data.get('unrealisedPnl'))
        logger.debug(f"Position updated: Size={self.size}, AvgPrice={self.avg_entry_price}, UPNL={self.unrealized_pnl}")

    def process_real_fill(self, trade: dict):
        """Processes real trade executions from WebSocket."""
        closed_pnl = to_decimal(trade.get('closedPnl'))
        if closed_pnl != Decimal("0"):
            self.realized_pnl += closed_pnl
            logger.info(f"Trade executed. Closed PnL: {closed_pnl:.4f}, Total Realized: {self.realized_pnl:.4f}")

    def process_virtual_fill(self, side: Literal["Buy", "Sell"], price: Decimal, qty: Decimal):
        """Simulates fills for dry-run mode."""
        if qty <= 0:
            return

        old_size = self.size
        current_value = self.size * self.avg_entry_price if self.size != 0 else Decimal("0")
        direction_factor = Decimal("1") if side == "Buy" else Decimal("-1")
        fill_value = direction_factor * qty * price

        # Calculate new_position_size carefully, accounting for direction
        if self.size == 0:
            new_position_size = direction_factor * qty
        elif (self.size > 0 and side == "Buy") or (self.size < 0 and side == "Sell"): # Increasing position
            new_position_size = self.size + (qty if side == "Buy" else -qty)
        else: # Reducing or flipping position
            remaining_qty = qty - abs(self.size)
            if remaining_qty >= 0: # Position flips or closes exactly
                self.realized_pnl += (price - self.avg_entry_price) * self.size if self.size > 0 else (self.avg_entry_price - price) * abs(self.size)
                new_position_size = direction_factor * remaining_qty
            else: # Position reduces without flipping
                pnl_realized_part = (price - self.avg_entry_price) * qty if self.size > 0 else (self.avg_entry_price - price) * qty
                self.realized_pnl += pnl_realized_part
                new_position_size = self.size + (qty if side == "Buy" else -qty)

        # Update avg_entry_price
        if new_position_size == 0:
            self.avg_entry_price = Decimal("0")
        elif (old_size * new_position_size <= 0): # Direction flipped or new position from zero
            self.avg_entry_price = price
        else: # Same direction, update average
            try:
                self.avg_entry_price = (abs(current_value) + qty * price) / abs(new_position_size)
            except (InvalidOperation, DivisionByZero):
                self.avg_entry_price = price # Fallback

        self.size = new_position_size
        logger.info(f"[DRY RUN] Fill: {side} {qty} @ {price}. Position: {old_size:.4f} -> {self.size:.4f}, Realized PnL: {self.realized_pnl:.4f}")


    def refresh_unrealized_pnl(self, mid: Decimal):
        """Recalculates unrealized PnL based on current mid-price."""
        if self.size == 0 or self.avg_entry_price == 0:
            self.unrealized_pnl = Decimal("0")
            return
        self.unrealized_pnl = (mid - self.avg_entry_price) * self.size

    async def check_and_manage_risk(self, current_mid_price: Decimal | None) -> bool:
        """Checks position PnL against stop-loss/take-profit and acts if triggered."""
        if not current_mid_price:
            logger.warning("Cannot manage risk, no current mid price available.")
            return False

        # Daily Loss Check
        await self.update_daily_pnl_snapshot()
        current_wallet_balance = await self.http_client.get_wallet_balance(coin=self.config.market.symbol[:-4]) or await self.http_client.get_wallet_balance(coin="USDT")

        if self.initial_balance is not None and self.initial_balance > 0 and current_wallet_balance is not None:
            # Need to consider unrealized PnL for accurate current balance for daily loss
            # This is a simplification; a full calculation involves current capital, initial margin, etc.
            # For this context, we will use total PnL relative to initial balance

            # Estimate current equity (simplistic for futures)
            estimated_current_equity = self.bot_state.daily_pnl_start_balance + self.realized_pnl + self.unrealized_pnl

            if self.bot_state.daily_pnl_start_balance > 0:
                daily_loss_pct = (self.bot_state.daily_pnl_start_balance - estimated_current_equity) / self.bot_state.daily_pnl_start_balance
                if daily_loss_pct >= self.config.risk_management.max_daily_loss_pct:
                    logger.critical(f"[bold red]DAILY LOSS LIMIT REACHED! ({daily_loss_pct:.2%})[/bold red]")
                    logger.critical("Shutting down bot to prevent further losses.")
                    # Trigger a full shutdown or emergency stop
                    raise Exception("Daily loss limit triggered.") # Will be caught in main loop

        if self.size == Decimal("0"):
            return False

        self.refresh_unrealized_pnl(current_mid_price)

        risk_cfg = self.config.risk_management
        try:
            position_value = abs(self.size * (self.avg_entry_price if self.avg_entry_price != 0 else current_mid_price))
            pnl_pct = self.unrealized_pnl / position_value if position_value > 0 else Decimal("0")
        except (InvalidOperation, DivisionByZero):
            pnl_pct = Decimal("0")

        should_close, reason = False, ""
        if pnl_pct >= risk_cfg.take_profit_pct:
            should_close, reason = True, f"Take Profit ({float(pnl_pct):.2%})"
        elif pnl_pct <= -risk_cfg.stop_loss_pct:
            should_close, reason = True, f"Stop Loss ({float(pnl_pct):.2%})"

        if should_close:
            logger.warning(f"[bold yellow]Risk Manager: Closing position - {reason}[/bold yellow]")
            logger.warning(f"Position: {self.size:.4f}, Unrealized PnL: {self.unrealized_pnl:.4f}")
            side_to_close = "Buy" if self.size < 0 else "Sell"
            qty_to_close = abs(self.size)

            await self.order_manager.cancel_all_open_orders()
            await self.http_client.close_position_market(side_to_close, qty_to_close)
            return True
        return False

# =========================
# Core Bot Class
# =========================
class EnhancedBybitMarketMaker:
    def __init__(self, config: BotConfig):
        self.config = config
        self.bot_state = BotState()

        # The API keys are now loaded and validated in the main() function
        # before the BotConfig is created. This check remains as a safeguard.
        if not self.config.credentials.api_key or not self.config.credentials.api_secret:
            raise ValueError("API keys are missing or empty. Ensure BYBIT_API_KEY and BYBIT_API_SECRET are set in your .env file or config.json.")

        self.http_client = BybitHTTPClient(self.config)
        self.websocket_manager = BybitWebSocketManager(self.config, self._handle_websocket_message)
        self.ta_manager = TAManager(self.config.ta)

        self.order_manager: OrderManager | None = None
        self.position_manager: PositionManager | None = None

        self.orderbook: dict[str, dict[Decimal, Decimal]] = {"bids": {}, "asks": {}}

        logger.addFilter(ContextFilter(self.config.market.symbol))
        self.loop: asyncio.AbstractEventLoop | None = None

    async def _handle_websocket_message(self, msg: dict):
        """Processes incoming messages from Bybit WebSocket."""
        topic = msg.get('topic', '')
        data = msg.get('data')

        if topic.startswith("orderbook"):
            book_data = data[0] if isinstance(data, list) else data
            try:
                self.orderbook['bids'] = {to_decimal(p): to_decimal(q) for p, q in book_data.get('b', [])}
                self.orderbook['asks'] = {to_decimal(p): to_decimal(q) for p, q in book_data.get('a', [])}
                if self.orderbook['bids'] and self.orderbook['asks']:
                    self.bot_state.last_known_best_bid = max(self.orderbook['bids'].keys())
                    self.bot_state.last_known_best_ask = min(self.orderbook['asks'].keys())
            except Exception as e:
                logger.error(f"Error parsing orderbook: {e}, data: {book_data}")

        elif topic.startswith("tickers"):
            if isinstance(data, dict) and data.get('midPrice') is not None:
                mid = to_decimal(data['midPrice'])
                self.bot_state.recent_prices.append((mid, time.time()))
                self.bot_state.last_mid_price = mid
                if self.config.market.dry_run and self.position_manager:
                    self.position_manager.refresh_unrealized_pnl(mid)
                self.ta_manager.update_ta(self.bot_state.recent_prices)

        elif not self.config.market.dry_run:
            if self.position_manager:
                if topic == "position":
                    for pos_data in (data if isinstance(data, list) else [data]):
                        if pos_data.get('symbol') == self.config.market.symbol:
                            self.position_manager.update_position(pos_data)

                elif topic == "order" and self.order_manager:
                    for order in (data if isinstance(data, list) else [data]):
                        if order.get('symbol') == self.config.market.symbol:
                            self.order_manager.update_from_websocket(order)

                elif topic == "execution" and self.position_manager:
                    for trade in (data if isinstance(data, list) else [data]):
                        if trade.get('execType') == 'Trade' and trade.get('symbol') == self.config.market.symbol:
                            self.position_manager.process_real_fill(trade)

    def _calculate_tiered_quotes(self) -> tuple[list[dict], list[dict]]:
        """Calculates buy and sell quotes based on strategy and TA."""
        bids = self.orderbook['bids']
        asks = self.orderbook['asks']

        if not bids or not asks:
            return [], []

        best_bid = self.bot_state.last_known_best_bid
        best_ask = self.bot_state.last_known_best_ask

        if best_bid is None or best_ask is None or best_bid >= best_ask:
            logger.debug(f"Market crossed or no best bid/ask: bid={best_bid}, ask={best_ask}. Skipping quotes.")
            return [], []

        mid_price = (best_bid + best_ask) / Decimal("2")
        fair_value = mid_price

        # Volatility Calculation (last X seconds of data)
        volatility = Decimal("0")
        current_time = time.time()
        vol_data_points = [(p, t) for p, t in self.bot_state.recent_prices if current_time - t <= self.config.technical.vol_window_seconds]

        if len(vol_data_points) >= self.config.technical.vol_window_seconds // 5: # Require a reasonable number of points
            try:
                prices_f = [float(p) for p, _ in vol_data_points]
                if len(set(prices_f)) > 1:
                    volatility = to_decimal(statistics.stdev(prices_f) / float(mid_price))
            except Exception as e:
                logger.debug(f"Volatility calc error: {e}")

        # Dynamic spread
        base_spread = self.config.strategy.base_spread_percentage
        vol_mult = self.config.strategy.volatility_spread_multiplier
        total_spread_pct = base_spread + (volatility * vol_mult)
        total_spread_pct = clamp_decimal(total_spread_pct, Decimal("0"), self.config.strategy.max_spread_percentage)

        # ---- TA-driven adjustments ----
        signal = Decimal("0") # Main signal in [-1, 1]

        if self.ta_manager.enabled:
            rsi = self.ta_manager.ta_state["rsi"]
            ema_f = self.ta_manager.ta_state["ema_fast"]
            ema_s = self.ta_manager.ta_state["ema_slow"]
            bbw = self.ta_manager.ta_state["bb_width_pct"]
            macd_hist = self.ta_manager.ta_state["macdh"]

            if rsi is not None:
                # RSI-based signal, strong reversals get stronger signal
                if rsi >= float(self.config.ta.rsi_overbought_threshold):
                    signal = Decimal("-1") * (to_decimal(rsi) - self.config.ta.rsi_overbought_threshold) / (Decimal("100") - self.config.ta.rsi_overbought_threshold)
                elif rsi <= float(self.config.ta.rsi_oversold_threshold):
                    signal = Decimal("1") * (self.config.ta.rsi_oversold_threshold - to_decimal(rsi)) / self.config.ta.rsi_oversold_threshold
                else:
                    signal = clamp_decimal(to_decimal((rsi - 50.0) / 50.0), Decimal("-1"), Decimal("1"))

                # Further adjustment for strong RSI reversal points
                if (rsi >= float(self.config.ta.rsi_overbought_threshold) and self.bot_state.last_mid_price > mid_price) or \
                   (rsi <= float(self.config.ta.rsi_oversold_threshold) and self.bot_state.last_mid_price < mid_price):
                    fair_value = fair_value * (Decimal("1") + signal * self.config.ta.rsi_reversal_fair_value_bps / Decimal("10000"))

            # EMA Cross signal
            if ema_f is not None and ema_s is not None:
                if ema_f > ema_s and self.bot_state.last_mid_price < mid_price: # Bullish cross
                    fair_value *= (Decimal("1") + self.config.ta.ema_cross_signal_multiplier)
                elif ema_f < ema_s and self.bot_state.last_mid_price > mid_price: # Bearish cross
                    fair_value *= (Decimal("1") - self.config.ta.ema_cross_signal_multiplier)

            # Fair value shift by RSI signal (bps)
            fv_bps = self.config.ta.signal_fair_value_bps
            fair_value = fair_value * (Decimal("1") + signal * fv_bps / Decimal("10000"))

            # Spread widening by BB width (% of mid)
            if bbw is not None:
                try:
                    bbw_dec = to_decimal(bbw)
                    total_spread_pct += bbw_dec * self.config.ta.bb_spread_mult
                except Exception:
                    pass

        # Aggressiveness multiplier applied to spread
        total_spread_pct /= self.config.strategy.aggressiveness_multiplier

        # Inventory skew
        max_pos_size = self.config.risk_management.max_position_size
        skew_intensity = self.config.strategy.inventory_skew_intensity
        current_pos_size = self.position_manager.size if self.position_manager else Decimal("0")

        if max_pos_size > 0 and skew_intensity > 0:
            # Ratio is current_pos_size / max_pos_size, clamped to [-1, 1]
            ratio = clamp_decimal(current_pos_size / max_pos_size, Decimal("-1"), Decimal("1"))
            # If we are long (ratio > 0), fair_value is pushed down to incentivize selling.
            # If we are short (ratio < 0), fair_value is pushed up to incentivize buying.
            inv_skew_factor = Decimal("1") - ratio * skew_intensity
            fair_value = fair_value * inv_skew_factor

        # Ensure fair_value is not negative or zero
        if fair_value <= 0:
            logger.warning(f"Calculated fair value {fair_value} is invalid. Resetting to mid_price.")
            fair_value = mid_price

        # Order params
        base_size = self.config.order_management.base_order_size * self.config.strategy.aggressiveness_multiplier
        tiers = self.config.order_management.order_tiers
        tier_spread_bps = self.config.order_management.tier_spread_increase_bps
        tier_qty_mult = self.config.order_management.tier_qty_multiplier

        # TA quantity bias
        qty_bias_max = self.config.ta.qty_bias_max
        buy_bias_factor = Decimal("1")
        sell_bias_factor = Decimal("1")

        if self.ta_manager.enabled:
            rsi = self.ta_manager.ta_state["rsi"]
            ema_f = self.ta_manager.ta_state["ema_fast"]
            ema_s = self.ta_manager.ta_state["ema_slow"]
            macd_hist = self.ta_manager.ta_state["macdh"]

            # Trend detection: EMA cross or strong RSI or MACD Histogram
            trend_up_signal = False
            if ema_f is not None and ema_s is not None and ema_f > ema_s:
                trend_up_signal = True
            if rsi is not None and rsi > float(self.config.ta.rsi_overbought_threshold) * 0.8: # Less strict for trend
                trend_up_signal = True
            if macd_hist is not None and macd_hist > 0:
                trend_up_signal = True

            trend_down_signal = False
            if ema_f is not None and ema_s is not None and ema_f < ema_s:
                trend_down_signal = True
            if rsi is not None and rsi < float(self.config.ta.rsi_oversold_threshold) * 1.2: # Less strict for trend
                trend_down_signal = True
            if macd_hist is not None and macd_hist < 0:
                trend_down_signal = True

            # Map combined signal to bias (signal is already in [-1,1])
            if trend_up_signal and not trend_down_signal:
                buy_bias_factor = Decimal("1") + qty_bias_max * abs(signal)
                sell_bias_factor = Decimal("1") - qty_bias_max * abs(signal) * Decimal("0.5") # Reduce selling
            elif trend_down_signal and not trend_up_signal:
                sell_bias_factor = Decimal("1") + qty_bias_max * abs(signal)
                buy_bias_factor = Decimal("1") - qty_bias_max * abs(signal) * Decimal("0.5") # Reduce buying

            # Ensure biases are not negative or excessively small
            buy_bias_factor = max(Decimal("0.1"), buy_bias_factor)
            sell_bias_factor = max(Decimal("0.1"), sell_bias_factor)

        buy_orders, sell_orders = [], []
        open_buy_qty = self.order_manager.get_open_buy_qty() if self.order_manager else Decimal("0")
        open_sell_qty = self.order_manager.get_open_sell_qty() if self.order_manager else Decimal("0")
        current_net_position = current_pos_size + open_buy_qty - open_sell_qty

        for i in range(tiers):
            tier_adj = (Decimal(i) * tier_spread_bps) / Decimal("10000")

            bid_price_raw = fair_value * (Decimal("1") - total_spread_pct - tier_adj)
            ask_price_raw = fair_value * (Decimal("1") + total_spread_pct + tier_adj)

            bid_price = self.order_manager._format_price(bid_price_raw)
            ask_price = self.order_manager._format_price(ask_price_raw)

            qty_raw = base_size * (Decimal("1") + Decimal(i) * tier_qty_mult)
            qty_buy = self.order_manager._format_qty(qty_raw * buy_bias_factor)
            qty_sell = self.order_manager._format_qty(qty_raw * sell_bias_factor)

            # Check position limits
            # This check is conservative, assuming all current open orders might fill.
            # A more advanced check could differentiate between active and passive orders.
            potential_long_position_if_fill = current_net_position + qty_buy
            potential_short_position_if_fill = current_net_position - qty_sell

            if potential_long_position_if_fill <= max_pos_size:
                buy_orders.append({'price': bid_price, 'qty': qty_buy, 'side': 'Buy'})
            else:
                logger.debug(f"Skipping buy order tier {i} due to max position limit ({potential_long_position_if_fill} > {max_pos_size})")

            if potential_short_position_if_fill >= -max_pos_size:
                sell_orders.append({'price': ask_price, 'qty': qty_sell, 'side': 'Sell'})
            else:
                logger.debug(f"Skipping sell order tier {i} due to max position limit ({potential_short_position_if_fill} < {-max_pos_size})")

        return buy_orders, sell_orders

    async def _simulate_fills(self):
        """Simulates order fills based on current orderbook for dry-run mode."""
        if not self.order_manager or not self.order_manager.virtual_orders or not self.orderbook['bids'] or not self.orderbook['asks']:
            return

        best_bid = self.bot_state.last_known_best_bid
        best_ask = self.bot_state.last_known_best_ask

        if best_bid is None or best_ask is None:
            return

        filled_order_ids = []
        for order_id, order in list(self.order_manager.virtual_orders.items()):
            if order.side == 'Buy' and order.price >= best_ask:
                self.position_manager.process_virtual_fill('Buy', best_ask, order.qty)
                filled_order_ids.append(order_id)
            elif order.side == 'Sell' and order.price <= best_bid:
                self.position_manager.process_virtual_fill('Sell', best_bid, order.qty)
                filled_order_ids.append(order_id)

        for order_id in filled_order_ids:
            self.order_manager.virtual_orders.pop(order_id)

    def generate_status_table(self) -> Table:
        """Generates a Rich Table for displaying bot status."""
        title = f"Bybit Market Maker - {self.config.market.symbol} ({datetime.now().strftime('%H:%M:%S.%f')[:-3]})"
        if self.config.market.dry_run:
            title += " [bold yellow](DRY RUN)[/bold yellow]"

        table = Table(title=title, style="cyan", title_justify="left", header_style="bold green")
        table.add_column("Metric", style="bold magenta", min_width=20)
        table.add_column("Value", min_width=30)

        status_color = "red" if self.http_client.circuit_breaker_active else "green"
        status_text = "CIRCUIT BREAKER" if self.http_client.circuit_breaker_active else "Active"
        table.add_row("Bot Status", f"[{status_color}]{status_text}[/{status_color}]")

        if self.bot_state.instrument_info:
            price_prec = self.bot_state.instrument_info.price_precision
            qty_prec = self.bot_state.instrument_info.qty_precision
        else:
            price_prec = 4
            qty_prec = 4


        if self.bot_state.last_known_best_bid and self.bot_state.last_known_best_ask:
            best_bid = self.bot_state.last_known_best_bid
            best_ask = self.bot_state.last_known_best_ask
            spread = best_ask - best_bid
            spread_bps = (spread / best_bid * 10000) if best_bid > 0 else Decimal("0")
            table.add_row("Best Bid/Ask", f"{best_bid:.{price_prec}f} / {best_ask:.{price_prec}f}")
            table.add_row("Spread", f"{spread:.{price_prec}f} ([bold]{spread_bps:.1f}[/bold] bps)")
        else:
            table.add_row("Best Bid/Ask", "No data")
            table.add_row("Spread", "No data")

        pos_color = "green" if self.position_manager and self.position_manager.size > 0 else "red" if self.position_manager and self.position_manager.size < 0 else "white"
        position_size_str = f"[{pos_color}]{self.position_manager.size:.{qty_prec}f}[/{pos_color}]" if self.position_manager else "N/A"
        avg_entry_str = f"{self.position_manager.avg_entry_price:.{price_prec}f}" if self.position_manager and self.position_manager.avg_entry_price != Decimal("0") else "N/A"
        table.add_row("Position Size", position_size_str)
        table.add_row("Avg Entry Price", avg_entry_str)

        if self.position_manager:
            unreal_color = "green" if self.position_manager.unrealized_pnl >= 0 else "red"
            real_color = "green" if self.position_manager.realized_pnl >= 0 else "red"
            table.add_row("Unrealized PnL", f"[{unreal_color}]{self.position_manager.unrealized_pnl:.4f}[/{unreal_color}]")
            table.add_row("Realized PnL", f"[{real_color}]{self.position_manager.realized_pnl:.4f}[/{real_color}]")

            if self.position_manager.initial_balance is not None and self.position_manager.initial_balance > 0:
                # This estimation is complex, for display simplicity, we use total_pnl vs start_balance
                daily_pnl = self.position_manager.realized_pnl + self.position_manager.unrealized_pnl
                daily_pnl_pct = (daily_pnl / self.bot_state.daily_pnl_start_balance) * 100
                pnl_color = "green" if daily_pnl >= 0 else "red"
                table.add_row("Daily PnL", f"[{pnl_color}]{daily_pnl:.4f} ({daily_pnl_pct:.2f}%)[/{pnl_color}]")
        else:
            table.add_row("Unrealized PnL", "N/A")
            table.add_row("Realized PnL", "N/A")
            table.add_row("Daily PnL", "N/A")


        if self.order_manager:
            open_orders = self.order_manager.current_orders
            buys = len([o for o in open_orders.values() if o.side == 'Buy'])
            sells = len([o for o in open_orders.values() if o.side == 'Sell'])
            table.add_row("Open Orders", f"{buys} buys / {sells} sells")
        else:
            table.add_row("Open Orders", "N/A")

        # TA readout
        if self.ta_manager.enabled:
            rsi = self.ta_manager.ta_state["rsi"]
            ema_f = self.ta_manager.ta_state["ema_fast"]
            ema_s = self.ta_manager.ta_state["ema_slow"]
            bbw = self.ta_manager.ta_state["bb_width_pct"]
            macd = self.ta_manager.ta_state["macd"]
            macdh = self.ta_manager.ta_state["macdh"]

            rsi_txt = f"{rsi:.1f}" if isinstance(rsi, float) else "N/A"
            ema_trend = "Up" if (isinstance(ema_f, float) and isinstance(ema_s, float) and ema_f > ema_s) else \
                        "Down" if (isinstance(ema_f, float) and isinstance(ema_s, float) and ema_f < ema_s) else "Neutral"
            bbw_txt = f"{bbw*100:.2f}%" if isinstance(bbw, float) else "N/A"
            macd_signal = "Bullish" if (isinstance(macdh, float) and macdh > 0) else "Bearish" if (isinstance(macdh, float) and macdh < 0) else "Neutral"

            table.add_row("RSI", rsi_txt)
            table.add_row("EMA Trend", ema_trend)
            table.add_row("BB Width", bbw_txt)
            table.add_row("MACD Signal", macd_signal)
        else:
            table.add_row("TA", "Disabled")

        # Volatility (last X seconds)
        current_time = time.time()
        recent_prices_only = [p for p, t in self.bot_state.recent_prices if current_time - t <= self.config.technical.vol_window_seconds]
        if len(recent_prices_only) >= 30: # At least 30 seconds of data for volatility
            try:
                prices_f = [float(p) for p in recent_prices_only]
                if len(set(prices_f)) > 1:
                    vol = statistics.stdev(prices_f) / statistics.mean(prices_f)
                    table.add_row(f"Volatility ({self.config.technical.vol_window_seconds}s)", f"{vol:.4%}")
                else:
                    table.add_row(f"Volatility ({self.config.technical.vol_window_seconds}s)", "0.00%")
            except Exception:
                table.add_row(f"Volatility ({self.config.technical.vol_window_seconds}s)", "N/A")
        else:
            table.add_row(f"Volatility ({self.config.technical.vol_window_seconds}s)", "Insufficient data")

        return table

    async def _setup_initial_state(self):
        """Fetches instrument info and initializes managers."""
        instrument_info = await self.http_client.get_instrument_info()
        if not instrument_info:
            raise RuntimeError("Failed to fetch instrument info. Cannot start bot.")
        self.bot_state.instrument_info = instrument_info

        self.order_manager = OrderManager(self.config, self.http_client, self.bot_state.instrument_info)
        self.position_manager = PositionManager(self.config, self.http_client, self.order_manager, self.bot_state)

        await self.position_manager.initialize_balance()
        await self.order_manager.cancel_all_open_orders()

    async def run(self):
        """Main execution loop of the bot."""
        mode = "[bold yellow]DRY RUN[/bold yellow]" if self.config.market.dry_run else "[bold green]LIVE[/bold green]"
        env = "Testnet" if self.config.market.testnet else "Mainnet"
        logger.info(f"Starting bot: {self.config.market.symbol} on {env} in {mode} mode")

        self.loop = asyncio.get_running_loop()

        try:
            await self._setup_initial_state()
            await self.websocket_manager.start_streams()

            logger.info("Waiting for initial market data to populate...")
            timeout_start = time.time()
            while (not self.orderbook['bids'] or not self.orderbook['asks'] or not self.bot_state.last_mid_price) and \
                  (time.time() - timeout_start < 30):
                await asyncio.sleep(0.5)

            if not self.bot_state.last_mid_price:
                logger.critical("Failed to receive initial market data within timeout. Exiting.")
                return

        except Exception as e:
            logger.critical(f"Initial setup failed: {e}", exc_info=True)
            return

        with Live(self.generate_status_table(), screen=True, refresh_per_second=2, console=console) as live:
            while True:
                try:
                    live.update(self.generate_status_table())

                    if self.http_client.circuit_breaker_active:
                        await asyncio.sleep(1)
                        continue

                    # Risk management check first
                    if self.position_manager:
                        try:
                            if await self.position_manager.check_and_manage_risk(self.bot_state.last_mid_price):
                                logger.info("Position closed by risk manager, pausing for cooldown.")
                                await asyncio.sleep(self.config.risk_management.circuit_breaker_cooldown_seconds)
                                continue
                        except Exception as e:
                            logger.critical(f"Critical error from risk manager: {e}", exc_info=True)
                            # If daily loss is hit, propagate shutdown
                            raise asyncio.CancelledError("Bot shutdown due to critical risk event.")

                    if self.config.market.dry_run:
                        await self._simulate_fills()

                    # Only proceed if we have valid market data and initialized managers
                    if not self.bot_state.last_mid_price or not self.bot_state.last_known_best_bid or \
                       not self.bot_state.last_known_best_ask or self.order_manager is None or self.position_manager is None:
                        logger.debug("No valid mid price/orderbook or managers not initialized, skipping quote calculation.")
                        await asyncio.sleep(0.5)
                        continue

                    now = time.time()
                    if (now - self.order_manager.last_reprice_time) < self.config.order_management.order_reprice_delay_seconds:
                        await asyncio.sleep(0.1)
                        continue

                    buy_orders, sell_orders = self._calculate_tiered_quotes()

                    if not buy_orders and not sell_orders:
                        if self.order_manager.current_orders:
                            logger.info("No quotes generated, cancelling existing orders.")
                            await self.order_manager.cancel_all_open_orders()
                        await asyncio.sleep(0.5)
                        continue

                    await self.order_manager.manage_orders(
                        buy_orders, sell_orders,
                        self.bot_state.last_mid_price,
                        self.bot_state.last_mid_price # Pass current mid as last_known_mid for current cycle
                    )

                    await asyncio.sleep(0.1)

                except asyncio.CancelledError:
                    logger.info("Main loop cancelled (external request or critical event).")
                    break
                except Exception as e:
                    logger.error(f"Unhandled main loop error: {e}", exc_info=True)
                    await asyncio.sleep(5)

        logger.info("Bot main loop exited.")

    async def shutdown(self):
        """Performs graceful shutdown of the bot."""
        logger.info("Initiating graceful shutdown...")
        # Ensure all tasks are cancelled before exiting pybit's internal threads
        if self.websocket_manager._public_monitor_task:
            self.websocket_manager._public_monitor_task.cancel()
            await asyncio.sleep(0.1)
        if self.websocket_manager._private_monitor_task:
            self.websocket_manager._private_monitor_task.cancel()
            await asyncio.sleep(0.1)

        if self.order_manager:
            await self.order_manager.cancel_all_open_orders()
        self.websocket_manager.stop_streams()
        logger.info("Shutdown complete.")

# =========================
# Entry point
# =========================
async def main():
    """Main entry point for the application."""
    # Load environment variables FIRST to ensure they are available for validation
    script_dir = Path(__file__).parent
    env_path = script_dir / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"Loaded .env from {env_path}")
    else:
        load_dotenv()
        logger.warning(f".env not found at {env_path}, trying default locations")

    config_path = Path(__file__).parent / 'config.json'
    try:
        with open(config_path, 'rb') as f:
            raw_config = json.loads(f.read())

        # Override config with environment variables before validation
        if 'credentials' not in raw_config:
            raw_config['credentials'] = {}
        raw_config['credentials']['api_key'] = os.getenv('BYBIT_API_KEY', raw_config.get('credentials', {}).get('api_key', ''))
        raw_config['credentials']['api_secret'] = os.getenv('BYBIT_API_SECRET', raw_config.get('credentials', {}).get('api_secret', ''))

        config = BotConfig(**raw_config)
    except FileNotFoundError:
        logger.critical(f"config.json not found at {config_path}")
        return
    except (json.JSONDecodeError, ValidationError) as e:
        logger.critical(f"Error parsing or validating config.json: {e}")
        return

    bot = EnhancedBybitMarketMaker(config)
    loop = asyncio.get_running_loop()
    main_task = asyncio.create_task(bot.run())

    def _signal_handler():
        logger.info("Shutdown signal received (SIGINT/SIGTERM). Requesting bot shutdown.")
        main_task.cancel()

    for signame in ('SIGINT', 'SIGTERM'):
        if hasattr(signal, signame):
            try:
                loop.add_signal_handler(getattr(signal, signame), _signal_handler)
            except NotImplementedError:
                logger.warning(f"Signal handler for {signame} not available on this platform.")

    try:
        await main_task
    except asyncio.CancelledError:
        logger.info("Bot main task was cancelled.")
    except Exception as e:
        logger.critical(f"Fatal unhandled error caught by main entry point: {e}", exc_info=True)
    finally:
        await bot.shutdown()
        logger.info("Application exiting.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application interrupted by user (KeyboardInterrupt from main thread).")
    except Exception as e:
        logger.critical(f"Top-level unhandled error in application: {e}", exc_info=True)
