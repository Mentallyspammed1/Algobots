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
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
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
    warnings.warn(
        "pandas or pandas_ta not found. Technical analysis features will be disabled.",
        ImportWarning,
    )

# Optional: suppress pkg_resources deprecation warnings from dependencies
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pkg_resources")
warnings.filterwarnings(
    "ignore", message="The pytz module is deprecated", module="pandas"
)

# Set Decimal precision
getcontext().prec = 30  # High precision for intermediate calculations

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
    datefmt="[%X]",  # Use Rich's default time format or custom like "%H:%M:%S"
    handlers=[
        RichHandler(
            markup=True,
            rich_tracebacks=True,
            show_time=True,
            show_level=True,
            log_time_format="%H:%M:%S.%f",  # Millisecond precision for log times
            console=console,
        )
    ],
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
        logger.warning(
            f"Could not convert '{value}' to Decimal. Using default '{default}'."
        )
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
        logger.debug(
            f"Rounding error for {x} with increment {inc}. Returning original."
        )
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

    class Config:
        arbitrary_types_allowed = True
        json_dumps = json.dumps
        json_loads = json.loads

    @field_validator("*", mode="before")
    @classmethod
    def convert_to_decimal_if_needed(cls, v):
        if isinstance(v, (int, float, str)) and "Decimal" in str(
            cls.model_fields.get(v).annotation
        ):
            return to_decimal(v)
        return v


class CredentialsConfig(BaseConfigModel):
    api_key: str = Field(..., min_length=1)
    api_secret: str = Field(..., min_length=1)


class MarketConfig(BaseConfigModel):
    symbol: str = Field(..., pattern=r"^[A-Z0-9]{5,15}$")  # e.g., BTCUSDT
    testnet: bool = False
    dry_run: bool = False


class OrderManagementConfig(BaseConfigModel):
    base_order_size: Decimal = Field(..., gt=0)
    order_tiers: int = Field(..., ge=1, le=10)
    tier_spread_increase_bps: Decimal = Field(
        ..., ge=0
    )  # Basis points increase per tier
    tier_qty_multiplier: Decimal = Field(..., ge=0)
    order_reprice_delay_seconds: float = Field(..., gt=0.1)
    price_tolerance_ticks: Decimal = Field(
        Decimal("0.5"), ge=0
    )  # Reprice if new price is more than N ticks away
    qty_tolerance_steps: Decimal = Field(
        Decimal("0"), ge=0
    )  # Reprice if new qty is more than N steps away
    mid_drift_threshold_ticks: Decimal = Field(
        Decimal("0.5"), ge=0
    )  # If mid price drifts this much from last known mid, reprice


class RiskManagementConfig(BaseConfigModel):
    max_position_size: Decimal = Field(..., gt=0)
    take_profit_pct: Decimal = Field(..., gt=0)  # E.g., 0.005 for 0.5%
    stop_loss_pct: Decimal = Field(..., gt=0)  # E.g., 0.01 for 1%
    circuit_breaker_threshold: int = Field(..., gt=0)  # Consecutive API failures
    circuit_breaker_cooldown_seconds: float = Field(..., gt=0)


class StrategyConfig(BaseConfigModel):
    base_spread_percentage: Decimal = Field(..., gt=0)  # E.g., 0.001 for 0.1% spread
    volatility_spread_multiplier: Decimal = Field(Decimal("0"), ge=0)
    inventory_skew_intensity: Decimal = Field(
        Decimal("0"), ge=0, lt=1
    )  # How much inventory pushes fair value


class TechnicalConfig(BaseConfigModel):
    orderbook_depth: int = Field(20, ge=1, le=50)  # WS orderbook depth
    vol_window: int = Field(60, ge=10)  # Window for volatility calculation


class TAConfig(BaseConfigModel):
    enabled: bool = False
    rsi_length: int = Field(14, ge=2)
    ema_fast: int = Field(12, ge=2)
    ema_slow: int = Field(26, ge=2)
    bb_length: int = Field(20, ge=2)
    bb_std: float = Field(2.0, gt=0)
    signal_fair_value_bps: Decimal = Field(
        Decimal("2.0"), ge=0
    )  # Max BPS shift from RSI signal
    bb_spread_mult: Decimal = Field(
        Decimal("0.5"), ge=0
    )  # Multiplier for BB width to spread
    qty_bias_max: Decimal = Field(
        Decimal("0.5"), ge=0, lt=1
    )  # Max +/- percentage change in quantity

    @model_validator(mode="after")
    def check_ta_availability(self) -> "TAConfig":
        if self.enabled and not PANDAS_TA_AVAILABLE:
            warnings.warn(
                "TA enabled in config but pandas/pandas_ta not installed. TA features will be disabled.",
                RuntimeWarning,
            )
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
        # Calculate precision from tick/step size (number of decimal places)
        self.price_precision = max(0, abs(self.tick_size.as_tuple().exponent))
        self.qty_precision = max(0, abs(self.step_size.as_tuple().exponent))


@dataclass
class BotState:
    instrument_info: InstrumentInfo | None = None
    recent_prices: deque[Decimal] = field(
        default_factory=lambda: deque(maxlen=240)
    )  # last ~4 minutes @1s
    last_mid_price: Decimal | None = None
    last_known_best_bid: Decimal | None = None
    last_known_best_ask: Decimal | None = None


@dataclass
class OrderTracker:
    order_id: str
    price: Decimal
    qty: Decimal
    side: Literal["Buy", "Sell"]
    is_virtual: bool = False
    timestamp: float = field(default_factory=time.time)


# =========================
# Bybit API Client (HTTP)
# =========================
class BybitHTTPClient:
    def __init__(self, config: BotConfig):
        self.config = config.market
        self.api_key = config.credentials.api_key
        self.api_secret = config.credentials.api_secret
        self.symbol = self.config.symbol
        self.testnet = self.config.testnet
        self.session = HTTP(
            testnet=self.testnet,
            api_key=self.api_key,
            api_secret=self.api_secret,
            recv_window=10000,
            timeout=30,
        )
        self.circuit_breaker_active: bool = False
        self.consecutive_api_failures: int = 0
        self.rate_limit_backoff_sec: float = 2.0
        self.max_backoff_sec: float = 30.0
        self.api_call_semaphore = asyncio.Semaphore(
            5
        )  # Limit concurrent API calls to Bybit

    async def _safe_api_call(self, method, *args, **kwargs):
        """
        Wrapper for Bybit API calls with retries, rate limiting, and circuit breaker.
        Uses asyncio.to_thread because pybit's HTTP client is blocking.
        """
        if self.circuit_breaker_active:
            logger.warning(f"API call to {method.__name__} blocked by circuit breaker.")
            return None

        async for attempt in AsyncRetrying(
            wait=wait_exponential(
                multiplier=1, min=self.rate_limit_backoff_sec, max=self.max_backoff_sec
            ),
            stop=stop_after_attempt(
                self.config.risk_management.circuit_breaker_threshold
            ),
            retry=retry_if_exception_type(
                Exception
            ),  # Catch all exceptions for retries
            reraise=True,
            before_sleep=before_sleep_log(logger, logging.WARNING, exc_info=False),
        ):
            with attempt:
                try:
                    async with self.api_call_semaphore:  # Limit concurrency
                        response = await asyncio.to_thread(method, *args, **kwargs)

                    if response and response.get("retCode") == 0:
                        self.consecutive_api_failures = 0
                        self.rate_limit_backoff_sec = 2.0  # Reset backoff
                        return response["result"]
                    else:
                        msg = (
                            response.get("retMsg", "Unknown error")
                            if response
                            else "No response"
                        )
                        code = response.get("retCode") if response else None

                        if code == 10006 or (msg and "rate limit" in str(msg).lower()):
                            logger.warning(
                                f"Rate limit hit ({method.__name__}). Retrying with backoff."
                            )
                            raise Exception("Rate limit encountered")  # Trigger retry
                        else:
                            logger.error(
                                f"API Error ({method.__name__}): {msg} (retCode: {code})"
                            )
                            self.consecutive_api_failures += 1
                            await self._check_circuit_breaker()
                            return None  # Non-retriable API error

                except Exception as e:
                    logger.error(
                        f"API request failed ({method.__name__}): {e}", exc_info=False
                    )
                    self.consecutive_api_failures += 1
                    await self._check_circuit_breaker()
                    raise  # Re-raise to trigger tenacity retry or final failure

        logger.critical(
            f"API call {method.__name__} failed after multiple retries. Circuit breaker likely active."
        )
        return None  # Should only be reached if retries exhausted

    async def _check_circuit_breaker(self):
        """Activates circuit breaker if too many consecutive failures occur."""
        threshold = self.config.risk_management.circuit_breaker_threshold
        if self.consecutive_api_failures >= threshold:
            if not self.circuit_breaker_active:
                self.circuit_breaker_active = True
                logger.critical(
                    "[bold red]CIRCUIT BREAKER TRIGGERED[/bold red] due to excessive API failures."
                )
                cooldown = self.config.risk_management.circuit_breaker_cooldown_seconds
                logger.warning(f"Trading paused for {cooldown} seconds.")
                await asyncio.sleep(
                    cooldown
                )  # Blocking sleep is fine for circuit breaker
                self.consecutive_api_failures = 0
                self.circuit_breaker_active = False
                logger.info("[bold green]Circuit breaker reset. Resuming.[/bold green]")

    async def get_instrument_info(self) -> InstrumentInfo | None:
        """Fetches and parses instrument trading rules."""
        result = await self._safe_api_call(
            self.session.get_instruments_info, category="linear", symbol=self.symbol
        )
        if result and result.get("list"):
            info = result["list"][0]
            instrument_info = InstrumentInfo(
                tick_size=to_decimal(info["priceFilter"]["tickSize"], "0.0001"),
                step_size=to_decimal(info["lotSizeFilter"]["qtyStep"], "0.001"),
                min_order_size=to_decimal(
                    info["lotSizeFilter"]["minOrderQty"], "0.001"
                ),
            )
            logger.info(
                f"Instrument info: tick={instrument_info.tick_size}, step={instrument_info.step_size}, min={instrument_info.min_order_size}"
            )
            return instrument_info
        logger.error(f"Failed to fetch instrument info for {self.symbol}")
        return None

    async def place_batch_orders(self, orders: list[dict]) -> list[dict]:
        """Places a batch of orders."""
        if not orders:
            return []
        place_requests = [
            {
                "symbol": self.symbol,
                "side": o["side"],
                "orderType": "Limit",
                "qty": str(o["qty"]),
                "price": str(o["price"]),
                "orderLinkId": f"mm_{uuid.uuid4().hex[:8]}",  # Unique link ID for each order
                "timeInForce": "PostOnly",
                "reduceOnly": o.get("reduceOnly", False),
            }
            for o in orders
        ]
        result = await self._safe_api_call(
            self.session.place_batch_order, category="linear", request=place_requests
        )
        if result and result.get("list"):
            successes = [r for r in result["list"] if r.get("orderId")]
            failures = [r for r in result["list"] if not r.get("orderId")]
            if successes:
                logger.info(
                    f"Placed {len(successes)}/{len(orders)} orders successfully."
                )
            if failures:
                logger.warning(f"Failed to place {len(failures)} orders: {failures}")
            return successes
        return []

    async def cancel_batch_orders(self, order_ids: list[str]) -> list[str]:
        """Cancels a batch of orders."""
        if not order_ids:
            return []
        cancel_requests = [{"symbol": self.symbol, "orderId": oid} for oid in order_ids]
        result = await self._safe_api_call(
            self.session.cancel_batch_order, category="linear", request=cancel_requests
        )
        if result and result.get("list"):
            successes = [r.get("orderId") for r in result["list"] if r.get("orderId")]
            failures = [r for r in result["list"] if not r.get("orderId")]
            if successes:
                logger.info(
                    f"Cancelled {len(successes)}/{len(order_ids)} orders successfully."
                )
            if failures:
                logger.warning(f"Failed to cancel {len(failures)} orders: {failures}")
            return successes
        return []

    async def close_position_market(
        self, side: Literal["Buy", "Sell"], qty: Decimal
    ) -> bool:
        """Closes a position with a market order."""
        if qty <= 0:
            return False
        logger.warning(
            f"[bold yellow]Closing position via market order: {side} {qty}[/bold yellow]"
        )
        result = await self._safe_api_call(
            self.session.place_order,
            category="linear",
            symbol=self.symbol,
            side=side,
            orderType="Market",
            qty=str(qty),
            reduceOnly=True,
        )
        if result and result.get("orderId"):
            logger.info(f"Market close order placed: {side} {qty}")
            return True
        logger.error(f"Failed to close position: {side} {qty}. Result: {result}")
        return False

    async def cancel_all_orders(self) -> bool:
        """Cancels all active orders for the symbol."""
        result = await self._safe_api_call(
            self.session.cancel_all_orders, category="linear", symbol=self.symbol
        )
        if result:
            logger.info("All orders cancelled.")
            return True
        logger.error("Failed to cancel all orders.")
        return False


# =========================
# Bybit WebSocket Manager
# =========================
class BybitWebSocketManager:
    def __init__(self, config: BotConfig, message_handler):
        self.config = config.market
        self.credentials = config.credentials
        self.symbol = self.config.symbol
        self.testnet = self.config.testnet
        self.message_handler = message_handler
        self.public_ws: WebSocket | None = None
        self.private_ws: WebSocket | None = None
        self.main_event_loop: asyncio.AbstractEventLoop | None = None
        self._reconnect_lock = asyncio.Lock()  # Prevent multiple reconnect attempts

    def _ws_callback(self, message: dict):
        """
        Callback for pybit websockets. Runs in a separate thread.
        Dispatches to the main event loop for processing.
        """
        if self.main_event_loop and self.main_event_loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    self.message_handler(message), self.main_event_loop
                )
            except Exception as e:
                logger.error(f"WS callback dispatch error: {e}", exc_info=True)
        else:
            logger.warning(
                "WS message received but main event loop not running or available."
            )

    async def _monitor_connection(self, ws: WebSocket, ws_type: str):
        """Monitors a WebSocket connection and attempts to reconnect on disconnection."""
        while True:
            await asyncio.sleep(5)  # Check connection status periodically
            if not ws.is_connected():
                logger.warning(
                    f"{ws_type} WebSocket disconnected. Attempting to reconnect..."
                )
                await self.start_streams(force_reconnect=True)
                return  # Exit this monitor, a new one will be spawned if successful

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
                    self.public_ws.exit()  # Ensure old connection is closed
                    await asyncio.sleep(0.5)
                self.public_ws = WebSocket(testnet=self.testnet, channel_type="linear")
                try:
                    self.public_ws.orderbook_stream(
                        depth=depth, symbol=symbol, callback=self._ws_callback
                    )
                    self.public_ws.ticker_stream(
                        symbol=symbol, callback=self._ws_callback
                    )
                    logger.info("Public WS subscriptions set.")
                    asyncio.create_task(
                        self._monitor_connection(self.public_ws, "Public")
                    )
                except Exception as e:
                    logger.critical(
                        f"Failed to start public WS subscriptions: {e}", exc_info=True
                    )
                    raise

            # Private WS (only live trading, not dry run)
            if not self.config.dry_run:
                if (
                    self.private_ws
                    and self.private_ws.is_connected()
                    and not force_reconnect
                ):
                    logger.debug("Private WS already connected.")
                else:
                    if self.private_ws:
                        self.private_ws.exit()  # Ensure old connection is closed
                        await asyncio.sleep(0.5)
                    self.private_ws = WebSocket(
                        testnet=self.testnet,
                        channel_type="private",
                        api_key=self.credentials.api_key,
                        api_secret=self.credentials.api_secret,
                    )
                    try:
                        self.private_ws.position_stream(callback=self._ws_callback)
                        self.private_ws.order_stream(callback=self._ws_callback)
                        self.private_ws.execution_stream(callback=self._ws_callback)
                        logger.info("Private WS subscriptions set.")
                        asyncio.create_task(
                            self._monitor_connection(self.private_ws, "Private")
                        )
                    except Exception as e:
                        logger.critical(
                            f"Failed to start private WS subscriptions: {e}",
                            exc_info=True,
                        )
                        raise
            else:
                if self.private_ws:
                    self.private_ws.exit()
                    self.private_ws = None

    def stop_streams(self):
        """Stops all WebSocket connections."""
        if self.public_ws:
            self.public_ws.exit()
            self.public_ws = None
            logger.info("Public WS stopped.")
        if self.private_ws:
            self.private_ws.exit()
            self.private_ws = None
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
        }
        self.enabled = config.enabled

    def update_ta(self, prices: deque[Decimal]):
        """Computes technical indicators from a deque of prices."""
        if not self.enabled or not PANDAS_TA_AVAILABLE:
            return

        try:
            prices_list = list(prices)
            if not prices_list:
                return

            rsi_len = self.config.rsi_length
            ema_fast = self.config.ema_fast
            ema_slow = self.config.ema_slow
            bb_len = self.config.bb_length
            bb_std = self.config.bb_std

            min_len = (
                max(rsi_len, ema_slow, bb_len) + 2
            )  # Ensure enough data for all indicators
            if len(prices_list) < min_len:
                logger.debug(
                    f"Not enough price data for TA. Need {min_len}, have {len(prices_list)}"
                )
                return

            s = pd.Series([float(x) for x in prices_list], dtype="float64")

            # RSI
            rsi_series = pta.rsi(s, length=rsi_len)
            self.ta_state["rsi"] = (
                float(rsi_series.iloc[-1])
                if rsi_series is not None and not pd.isna(rsi_series.iloc[-1])
                else None
            )

            # EMA
            ema_f_series = pta.ema(s, length=ema_fast)
            ema_s_series = pta.ema(s, length=ema_slow)
            self.ta_state["ema_fast"] = (
                float(ema_f_series.iloc[-1])
                if ema_f_series is not None and not pd.isna(ema_f_series.iloc[-1])
                else None
            )
            self.ta_state["ema_slow"] = (
                float(ema_s_series.iloc[-1])
                if ema_s_series is not None and not pd.isna(ema_s_series.iloc[-1])
                else None
            )

            # Bollinger Bands Width Percentage
            bb = pta.bbands(s, length=bb_len, std=bb_std)
            bb_width_pct = None
            if bb is not None and not bb.empty:
                upper_col = [c for c in bb.columns if c.startswith("BBU_")]
                lower_col = [c for c in bb.columns if c.startswith("BBL_")]
                mid_col = [c for c in bb.columns if c.startswith("BBM_")]
                if upper_col and lower_col and mid_col:
                    u, l, m = (
                        bb[upper_col[0]].iloc[-1],
                        bb[lower_col[0]].iloc[-1],
                        bb[mid_col[0]].iloc[-1],
                    )
                    if m and not any(pd.isna([u, l, m])):
                        bb_width_pct = float((u - l) / m) if m != 0 else None
            self.ta_state["bb_width_pct"] = bb_width_pct

        except Exception as e:
            logger.warning(f"TA update failed: {e}", exc_info=False)


# =========================
# Order Manager
# =========================
class OrderManager:
    def __init__(
        self,
        bot_config: BotConfig,
        http_client: BybitHTTPClient,
        instrument_info: InstrumentInfo,
    ):
        self.config = bot_config
        self.http_client = http_client
        self.instrument_info = instrument_info  # Reference to the bot's instrument info

        self.active_orders: dict[str, OrderTracker] = {}  # Live orders
        self.virtual_orders: dict[str, OrderTracker] = {}  # Dry-run orders
        self.orders_to_place: list[dict] = []
        self.orders_to_cancel: list[str] = []

    @property
    def current_orders(self) -> dict[str, OrderTracker]:
        return self.virtual_orders if self.config.market.dry_run else self.active_orders

    def _format_price(self, p: Decimal) -> Decimal:
        return round_to_increment(p, self.instrument_info.tick_size, ROUND_HALF_UP)

    def _format_qty(self, q: Decimal) -> Decimal:
        q = floor_to_increment(q, self.instrument_info.step_size)
        return max(q, self.instrument_info.min_order_size)

    def _quotes_significantly_changed(
        self,
        current_quotes: list[tuple[Decimal, Decimal, str]],
        new_quotes: list[tuple[Decimal, Decimal, str]],
    ) -> bool:
        """Determines if the new set of quotes differs significantly from the current ones."""
        if len(current_quotes) != len(new_quotes):
            return True

        price_tol = (
            self.instrument_info.tick_size
            * self.config.order_management.price_tolerance_ticks
        )
        qty_tol = (
            self.instrument_info.step_size
            * self.config.order_management.qty_tolerance_steps
        )

        # Sort for consistent comparison
        current_sorted = sorted(current_quotes, key=lambda x: (x[2], x[0], x[1]))
        new_sorted = sorted(new_quotes, key=lambda x: (x[2], x[0], x[1]))

        for (cp, cq, cs), (np, nq, ns) in zip(current_sorted, new_sorted, strict=False):
            if cs != ns:
                return True
            if not approx_equal(cp, np, price_tol):
                return True
            if not approx_equal(cq, nq, qty_tol):
                return True
        return False

    async def manage_orders(
        self, desired_buy_orders: list[dict], desired_sell_orders: list[dict]
    ):
        """Compares desired orders with current open orders and updates accordingly."""
        new_target_orders = desired_buy_orders + desired_sell_orders
        current_open_orders = self.current_orders

        # Convert to tuples for easy comparison
        current_quotes_tuple = [
            (o.price, o.qty, o.side) for o in current_open_orders.values()
        ]
        new_target_quotes_tuple = [
            (o["price"], o["qty"], o["side"]) for o in new_target_orders
        ]

        if not self._quotes_significantly_changed(
            current_quotes_tuple, new_target_quotes_tuple
        ):
            # Also check if mid price has drifted significantly
            if (
                self.config.market.last_mid_price
                and self.config.order_management.mid_drift_threshold_ticks > 0
            ):
                price_drift_threshold = (
                    self.instrument_info.tick_size
                    * self.config.order_management.mid_drift_threshold_ticks
                )
                if not approx_equal(
                    self.config.market.last_mid_price,
                    (
                        self.config.market.last_known_best_bid
                        + self.config.market.last_known_best_ask
                    )
                    / Decimal(2),
                    price_drift_threshold,
                ):
                    logger.debug(
                        "Mid price drifted significantly, re-evaluating orders."
                    )
                else:
                    return  # No significant change, no action needed

        # Determine orders to cancel and orders to place
        self.orders_to_cancel.clear()
        self.orders_to_place.clear()

        # Identify orders to cancel (current orders not in new target)
        for order_id, current_order in current_open_orders.items():
            if not any(
                approx_equal(
                    current_order.price,
                    to["price"],
                    self.instrument_info.tick_size
                    * self.config.order_management.price_tolerance_ticks,
                )
                and approx_equal(
                    current_order.qty,
                    to["qty"],
                    self.instrument_info.step_size
                    * self.config.order_management.qty_tolerance_steps,
                )
                and current_order.side == to["side"]
                for to in new_target_orders
            ):
                self.orders_to_cancel.append(order_id)

        # Identify orders to place (new target orders not in current)
        for target_order in new_target_orders:
            if not any(
                approx_equal(
                    target_order["price"],
                    co.price,
                    self.instrument_info.tick_size
                    * self.config.order_management.price_tolerance_ticks,
                )
                and approx_equal(
                    target_order["qty"],
                    co.qty,
                    self.instrument_info.step_size
                    * self.config.order_management.qty_tolerance_steps,
                )
                and target_order["side"] == co.side
                for co in current_open_orders.values()
            ):
                self.orders_to_place.append(target_order)

        if self.config.market.dry_run:
            self._execute_virtual_orders()
        else:
            await self._execute_live_orders()

    def _execute_virtual_orders(self):
        """Simulates order placement and cancellation for dry run."""
        if self.orders_to_cancel or self.orders_to_place:
            logger.info(
                f"[DRY RUN] Orders: Cancelling {len(self.orders_to_cancel)}, Placing {len(self.orders_to_place)}"
            )

        for order_id in self.orders_to_cancel:
            self.virtual_orders.pop(order_id, None)

        for order_data in self.orders_to_place:
            order_id = f"dryrun_{uuid.uuid4().hex[:8]}"
            self.virtual_orders[order_id] = OrderTracker(
                order_id=order_id,
                price=order_data["price"],
                qty=order_data["qty"],
                side=order_data["side"],
                is_virtual=True,
            )
        self.orders_to_cancel.clear()
        self.orders_to_place.clear()

    async def _execute_live_orders(self):
        """Executes actual order placement and cancellation on the exchange."""
        if self.orders_to_cancel or self.orders_to_place:
            logger.info(
                f"Executing: Cancelling {len(self.orders_to_cancel)} orders, Placing {len(self.orders_to_place)} orders."
            )

        # Cancel orders first
        if self.orders_to_cancel:
            cancelled_ids = await self.http_client.cancel_batch_orders(
                self.orders_to_cancel
            )
            for oid in cancelled_ids:
                self.active_orders.pop(oid, None)
            self.orders_to_cancel.clear()

        # Place new orders
        if self.orders_to_place:
            placed_orders_info = await self.http_client.place_batch_orders(
                self.orders_to_place
            )
            for info in placed_orders_info:
                order_id = info.get("orderId")
                if order_id:
                    original_order = next(
                        (
                            o
                            for o in self.orders_to_place
                            if o.get("orderLinkId") == info.get("orderLinkId")
                        ),
                        None,
                    )
                    if original_order:
                        self.active_orders[order_id] = OrderTracker(
                            order_id=order_id,
                            price=to_decimal(original_order["price"]),
                            qty=to_decimal(original_order["qty"]),
                            side=original_order["side"],
                        )
            self.orders_to_place.clear()

    async def cancel_all_open_orders(self):
        """Cancels all currently tracked orders."""
        if self.config.market.dry_run:
            if self.virtual_orders:
                logger.info(
                    f"[DRY RUN] Cancelling {len(self.virtual_orders)} virtual orders."
                )
                self.virtual_orders.clear()
        else:
            if await self.http_client.cancel_all_orders():
                self.active_orders.clear()

    def update_from_websocket(self, order_data: dict):
        """Updates active orders based on WebSocket messages."""
        oid = order_data.get("orderId")
        status = order_data.get("orderStatus")
        if not oid:
            return

        if status in ["New", "PartiallyFilled"]:
            try:
                self.active_orders[oid] = OrderTracker(
                    order_id=oid,
                    price=to_decimal(order_data["price"]),
                    qty=to_decimal(order_data["qty"]),
                    side=order_data["side"],
                )
            except Exception as e:
                logger.error(
                    f"Error parsing order data from WS: {e}, data: {order_data}"
                )
        elif status in ["Filled", "Cancelled", "Rejected"]:
            if oid in self.active_orders:
                self.active_orders.pop(oid, None)
                logger.info(f"Order {oid} {status}.")

    def get_open_buy_qty(self) -> Decimal:
        return sum(o.qty for o in self.current_orders.values() if o.side == "Buy")

    def get_open_sell_qty(self) -> Decimal:
        return sum(o.qty for o in self.current_orders.values() if o.side == "Sell")


# =========================
# Position Manager
# =========================
class PositionManager:
    def __init__(
        self,
        bot_config: BotConfig,
        http_client: BybitHTTPClient,
        order_manager: OrderManager,
    ):
        self.config = bot_config
        self.http_client = http_client
        self.order_manager = order_manager
        self.size: Decimal = Decimal("0")
        self.avg_entry_price: Decimal = Decimal("0")
        self.unrealized_pnl: Decimal = Decimal("0")
        self.realized_pnl: Decimal = Decimal("0")

    def update_position(self, data: dict):
        """Updates position details from WebSocket (live) or simulates (dry-run)."""
        self.size = to_decimal(data.get("size"))
        self.avg_entry_price = to_decimal(data.get("avgPrice"))
        self.unrealized_pnl = to_decimal(data.get("unrealisedPnl"))
        logger.debug(
            f"Position updated: Size={self.size}, AvgPrice={self.avg_entry_price}, UPNL={self.unrealized_pnl}"
        )

    def process_real_fill(self, trade: dict):
        """Processes real trade executions from WebSocket."""
        closed_pnl = to_decimal(trade.get("closedPnl"))
        if closed_pnl != Decimal("0"):
            self.realized_pnl += closed_pnl
            logger.info(
                f"Trade executed. Closed PnL: {closed_pnl:.4f}, Total Realized: {self.realized_pnl:.4f}"
            )

    def process_virtual_fill(
        self, side: Literal["Buy", "Sell"], price: Decimal, qty: Decimal
    ):
        """Simulates fills for dry-run mode."""
        if qty <= 0:
            return

        old_size = self.size
        current_value = (
            self.size * self.avg_entry_price if self.size != 0 else Decimal("0")
        )
        direction = Decimal("1") if side == "Buy" else Decimal("-1")
        fill_value = direction * qty * price
        new_position_size = self.size + (qty if side == "Buy" else -qty)

        # Realize partial PnL on reductions
        if (self.size > 0 and new_position_size < self.size) or (
            self.size < 0 and new_position_size > self.size
        ):
            reduce_qty = min(abs(self.size), qty)
            if reduce_qty > 0 and self.avg_entry_price > 0:
                pnl_per_unit = (
                    (price - self.avg_entry_price)
                    if self.size > 0
                    else (self.avg_entry_price - price)
                )
                realized_component = pnl_per_unit * reduce_qty
                self.realized_pnl += realized_component
                logger.info(
                    f"[DRY RUN] Realized PnL: {realized_component:.4f}, Total: {self.realized_pnl:.4f}"
                )

        if new_position_size == 0:
            self.unrealized_pnl = Decimal("0")
            self.avg_entry_price = Decimal("0")
        else:
            # If direction changes, reset avg entry to fill price
            if (self.size >= 0 and new_position_size < 0) or (
                self.size <= 0 and new_position_size > 0
            ):
                self.avg_entry_price = price
            else:  # If position increases or reduces in same direction, update avg price
                try:
                    self.avg_entry_price = abs(
                        (current_value + fill_value) / new_position_size
                    )
                except (InvalidOperation, DivisionByZero):
                    self.avg_entry_price = price  # Fallback if division by zero

        self.size = new_position_size
        logger.info(
            f"[DRY RUN] Fill: {side} {qty} @ {price}. Position: {old_size:.4f} → {self.size:.4f}"
        )

    def refresh_unrealized_pnl(self, mid: Decimal):
        """Recalculates unrealized PnL based on current mid-price."""
        if self.size == 0 or self.avg_entry_price == 0:
            self.unrealized_pnl = Decimal("0")
            return
        self.unrealized_pnl = (mid - self.avg_entry_price) * self.size

    async def check_and_manage_risk(self, current_mid_price: Decimal | None) -> bool:
        """Checks position PnL against stop-loss/take-profit and acts if triggered."""
        if self.size == Decimal("0"):
            return False

        if not current_mid_price:
            logger.warning("Cannot manage risk, no current mid price available.")
            return False

        self.refresh_unrealized_pnl(current_mid_price)

        risk_cfg = self.config.risk_management
        try:
            position_value = abs(
                self.size
                * (
                    self.avg_entry_price
                    if self.avg_entry_price != 0
                    else current_mid_price
                )
            )
            pnl_pct = (
                self.unrealized_pnl / position_value
                if position_value > 0
                else Decimal("0")
            )
        except (InvalidOperation, DivisionByZero):
            pnl_pct = Decimal("0")

        should_close, reason = False, ""
        if pnl_pct >= risk_cfg.take_profit_pct:
            should_close, reason = True, f"Take Profit ({float(pnl_pct):.2%})"
        elif pnl_pct <= -risk_cfg.stop_loss_pct:
            should_close, reason = True, f"Stop Loss ({float(pnl_pct):.2%})"

        if should_close:
            logger.warning(
                f"[bold yellow]Risk Manager: Closing position - {reason}[/bold yellow]"
            )
            logger.warning(
                f"Position: {self.size:.4f}, Unrealized PnL: {self.unrealized_pnl:.4f}"
            )
            side_to_close = "Buy" if self.size < 0 else "Sell"
            qty_to_close = abs(self.size)

            # Cancel all orders before closing position
            await self.order_manager.cancel_all_open_orders()
            # Execute close
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

        # Load environment variables
        script_dir = Path(__file__).parent
        env_path = script_dir / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            logger.info(f"Loaded .env from {env_path}")
        else:
            load_dotenv()
            logger.warning(f".env not found at {env_path}, trying default locations")

        # Override config credentials with env vars if present
        self.config.credentials.api_key = os.getenv(
            "BYBIT_API_KEY", self.config.credentials.api_key
        )
        self.config.credentials.api_secret = os.getenv(
            "BYBIT_API_SECRET", self.config.credentials.api_secret
        )

        if (
            not self.config.credentials.api_key
            or not self.config.credentials.api_secret
        ):
            raise ValueError(
                "API keys not found. Ensure BYBIT_API_KEY and BYBIT_API_SECRET are set in .env or config.json."
            )

        # Initialize core components
        self.http_client = BybitHTTPClient(self.config)
        self.websocket_manager = BybitWebSocketManager(
            self.config, self._handle_websocket_message
        )
        self.ta_manager = TAManager(self.config.ta)

        # Order Manager and Position Manager initialized later, after instrument info
        self.order_manager: OrderManager | None = None
        self.position_manager: PositionManager | None = None

        self.orderbook: dict[str, dict[Decimal, Decimal]] = {"bids": {}, "asks": {}}
        self.last_reprice_time = 0.0

        # Add symbol context filter to logger
        logger.addFilter(ContextFilter(self.config.market.symbol))

        # Main event loop reference
        self.loop: asyncio.AbstractEventLoop | None = None

    async def _handle_websocket_message(self, msg: dict):
        """Processes incoming messages from Bybit WebSocket."""
        topic = msg.get("topic", "")
        data = msg.get("data")

        if topic.startswith("orderbook"):
            book_data = data[0] if isinstance(data, list) else data
            try:
                self.orderbook["bids"] = {
                    to_decimal(p): to_decimal(q) for p, q in book_data.get("b", [])
                }
                self.orderbook["asks"] = {
                    to_decimal(p): to_decimal(q) for p, q in book_data.get("a", [])
                }
                if self.orderbook["bids"] and self.orderbook["asks"]:
                    self.bot_state.last_known_best_bid = max(
                        self.orderbook["bids"].keys()
                    )
                    self.bot_state.last_known_best_ask = min(
                        self.orderbook["asks"].keys()
                    )
            except Exception as e:
                logger.error(f"Error parsing orderbook: {e}, data: {book_data}")

        elif topic.startswith("tickers"):
            if isinstance(data, dict) and data.get("midPrice") is not None:
                mid = to_decimal(data["midPrice"])
                self.bot_state.recent_prices.append(mid)
                self.bot_state.last_mid_price = mid
                if self.config.market.dry_run and self.position_manager:
                    self.position_manager.refresh_unrealized_pnl(mid)
                self.ta_manager.update_ta(
                    self.bot_state.recent_prices
                )  # Update TA on each new mid price

        elif not self.config.market.dry_run:  # Private topics
            if self.position_manager:
                if topic == "position":
                    for pos_data in data if isinstance(data, list) else [data]:
                        if pos_data.get("symbol") == self.config.market.symbol:
                            self.position_manager.update_position(pos_data)

                elif topic == "order" and self.order_manager:
                    for order in data if isinstance(data, list) else [data]:
                        if order.get("symbol") == self.config.market.symbol:
                            self.order_manager.update_from_websocket(order)

                elif topic == "execution" and self.position_manager:
                    for trade in data if isinstance(data, list) else [data]:
                        if (
                            trade.get("execType") == "Trade"
                            and trade.get("symbol") == self.config.market.symbol
                        ):
                            self.position_manager.process_real_fill(trade)

    def _calculate_tiered_quotes(self) -> tuple[list[dict], list[dict]]:
        """Calculates buy and sell quotes based on strategy and TA."""
        bids = self.orderbook["bids"]
        asks = self.orderbook["asks"]

        if not bids or not asks:
            return [], []

        best_bid = max(bids.keys())
        best_ask = min(asks.keys())

        if best_bid >= best_ask:
            logger.debug(
                f"Market crossed: bid={best_bid}, ask={best_ask}. Skipping quotes."
            )
            return [], []

        mid_price = (best_bid + best_ask) / Decimal("2")
        # Initialize fair_value with mid_price before adjustments
        fair_value = mid_price

        # Volatility Calculation
        volatility = Decimal("0")
        vol_window = self.config.technical.vol_window
        if len(self.bot_state.recent_prices) >= vol_window:
            try:
                prices_f = [
                    float(p) for p in list(self.bot_state.recent_prices)[-vol_window:]
                ]
                if len(set(prices_f)) > 1:
                    volatility = to_decimal(
                        statistics.stdev(prices_f) / float(mid_price)
                    )
            except Exception as e:
                logger.debug(f"Volatility calc error: {e}")

        # Dynamic spread
        base_spread = self.config.strategy.base_spread_percentage
        vol_mult = self.config.strategy.volatility_spread_multiplier
        total_spread_pct = base_spread + (volatility * vol_mult)

        # ---- TA-driven adjustments ----
        if self.ta_manager.enabled:
            rsi = self.ta_manager.ta_state["rsi"]
            ema_f = self.ta_manager.ta_state["ema_fast"]
            ema_s = self.ta_manager.ta_state["ema_slow"]
            bbw = self.ta_manager.ta_state["bb_width_pct"]

            # RSI-based signal in [-1, 1]
            signal = Decimal("0")
            if rsi is not None:
                signal = clamp_decimal(
                    to_decimal((rsi - 50.0) / 50.0), Decimal("-1"), Decimal("1")
                )

            # Fair value shift by RSI signal (bps)
            fv_bps = self.config.ta.signal_fair_value_bps
            fair_value = fair_value * (
                Decimal("1") + signal * fv_bps / Decimal("10000")
            )

            # Spread widening by BB width (% of mid)
            if bbw is not None:
                try:
                    bbw_dec = to_decimal(bbw)
                    total_spread_pct += bbw_dec * self.config.ta.bb_spread_mult
                except Exception:
                    pass

        # Inventory skew
        max_pos_size = self.config.risk_management.max_position_size
        skew_intensity = self.config.strategy.inventory_skew_intensity
        current_pos_size = (
            self.position_manager.size if self.position_manager else Decimal("0")
        )

        if max_pos_size > 0:
            # Ratio is current_pos_size / max_pos_size, clamped to [-1, 1]
            ratio = clamp_decimal(
                current_pos_size / max_pos_size, Decimal("-1"), Decimal("1")
            )
            inv_skew_factor = Decimal("1") - ratio * skew_intensity
            fair_value = fair_value * inv_skew_factor

        # Ensure fair_value is not negative or zero
        if fair_value <= 0:
            logger.warning(
                f"Calculated fair value {fair_value} is invalid. Resetting to mid_price."
            )
            fair_value = mid_price

        # Order params
        base_size = self.config.order_management.base_order_size
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

            # Trend detection: EMA cross or strong RSI
            trend_up = (ema_f is not None and ema_s is not None and ema_f > ema_s) or (
                rsi is not None and rsi > 55
            )
            trend_down = (
                ema_f is not None and ema_s is not None and ema_f < ema_s
            ) or (rsi is not None and rsi < 45)

            # Map signal magnitude to bias (e.g., from RSI's distance from 50)
            signal_magnitude = (
                abs(signal)
                if self.ta_manager.ta_state["rsi"] is not None
                else Decimal("0")
            )

            if trend_up:
                buy_bias_factor = Decimal("1") + qty_bias_max * signal_magnitude
                sell_bias_factor = Decimal(
                    "1"
                ) - qty_bias_max * signal_magnitude * Decimal("0.5")  # Reduce selling
            elif trend_down:
                sell_bias_factor = Decimal("1") + qty_bias_max * signal_magnitude
                buy_bias_factor = Decimal(
                    "1"
                ) - qty_bias_max * signal_magnitude * Decimal("0.5")  # Reduce buying

            # Ensure biases are not negative
            buy_bias_factor = max(Decimal("0.1"), buy_bias_factor)
            sell_bias_factor = max(Decimal("0.1"), sell_bias_factor)

        buy_orders, sell_orders = [], []
        open_buy_qty = (
            self.order_manager.get_open_buy_qty()
            if self.order_manager
            else Decimal("0")
        )
        open_sell_qty = (
            self.order_manager.get_open_sell_qty()
            if self.order_manager
            else Decimal("0")
        )

        for i in range(tiers):
            tier_adj = (Decimal(i) * tier_spread_bps) / Decimal("10000")
            bid_price_raw = fair_value * (Decimal("1") - total_spread_pct - tier_adj)
            ask_price_raw = fair_value * (Decimal("1") + total_spread_pct + tier_adj)

            bid_price = self.order_manager._format_price(bid_price_raw)
            ask_price = self.order_manager._format_price(ask_price_raw)

            qty_raw = base_size * (Decimal("1") + Decimal(i) * tier_qty_mult)
            qty_buy = self.order_manager._format_qty(qty_raw * buy_bias_factor)
            qty_sell = self.order_manager._format_qty(qty_raw * sell_bias_factor)

            # Check position limits before adding orders
            # Note: This is an approximation. Real limits should consider current pending orders.
            # A more robust solution might require fetching open orders from API/WS.
            current_net_position = current_pos_size + open_buy_qty - open_sell_qty

            potential_long_position_if_fill = current_net_position + qty_buy
            potential_short_position_if_fill = current_net_position - qty_sell

            # Only place if within max position limits (absolute value)
            if potential_long_position_if_fill <= max_pos_size:
                buy_orders.append({"price": bid_price, "qty": qty_buy, "side": "Buy"})
            else:
                logger.debug(
                    f"Skipping buy order tier {i} due to max position limit ({potential_long_position_if_fill} > {max_pos_size})"
                )

            if potential_short_position_if_fill >= -max_pos_size:
                sell_orders.append(
                    {"price": ask_price, "qty": qty_sell, "side": "Sell"}
                )
            else:
                logger.debug(
                    f"Skipping sell order tier {i} due to max position limit ({potential_short_position_if_fill} < {-max_pos_size})"
                )

        return buy_orders, sell_orders

    async def _simulate_fills(self):
        """Simulates order fills based on current orderbook for dry-run mode."""
        if (
            not self.order_manager
            or not self.order_manager.virtual_orders
            or not self.orderbook["bids"]
            or not self.orderbook["asks"]
        ):
            return

        best_bid = max(self.orderbook["bids"].keys())
        best_ask = min(self.orderbook["asks"].keys())

        filled_order_ids = []
        for order_id, order in list(self.order_manager.virtual_orders.items()):
            if order["side"] == "Buy" and order["price"] >= best_ask:
                self.position_manager.process_virtual_fill(
                    "Buy", best_ask, order["qty"]
                )
                filled_order_ids.append(order_id)
            elif order["side"] == "Sell" and order["price"] <= best_bid:
                self.position_manager.process_virtual_fill(
                    "Sell", best_bid, order["qty"]
                )
                filled_order_ids.append(order_id)

        for order_id in filled_order_ids:
            self.order_manager.virtual_orders.pop(order_id)  # Use pop for clean removal

    def generate_status_table(self) -> Table:
        """Generates a Rich Table for displaying bot status."""
        title = f"Bybit Market Maker - {self.config.market.symbol} ({datetime.now().strftime('%H:%M:%S')})"
        if self.config.market.dry_run:
            title += " [bold yellow](DRY RUN)[/bold yellow]"

        table = Table(title=title, style="cyan", title_justify="left")
        table.add_column("Metric", style="bold magenta", min_width=20)
        table.add_column("Value", min_width=30)

        status_color = "red" if self.http_client.circuit_breaker_active else "green"
        status_text = (
            "CIRCUIT BREAKER" if self.http_client.circuit_breaker_active else "Active"
        )
        table.add_row("Bot Status", f"[{status_color}]{status_text}[/{status_color}]")

        if self.bot_state.last_known_best_bid and self.bot_state.last_known_best_ask:
            best_bid = self.bot_state.last_known_best_bid
            best_ask = self.bot_state.last_known_best_ask
            spread = best_ask - best_bid
            spread_bps = (spread / best_bid * 10000) if best_bid > 0 else Decimal("0")
            table.add_row(
                "Best Bid/Ask",
                f"{best_bid:.{self.bot_state.instrument_info.price_precision}f} / {best_ask:.{self.bot_state.instrument_info.price_precision}f}",
            )
            table.add_row(
                "Spread",
                f"{spread:.{self.bot_state.instrument_info.price_precision}f} ([bold]{spread_bps:.1f}[/bold] bps)",
            )
        else:
            table.add_row("Best Bid/Ask", "No data")
            table.add_row("Spread", "No data")

        pos_color = (
            "green"
            if self.position_manager and self.position_manager.size > 0
            else "red"
            if self.position_manager and self.position_manager.size < 0
            else "white"
        )
        position_size_str = (
            f"[{pos_color}]{self.position_manager.size:.{self.bot_state.instrument_info.qty_precision}f}[/{pos_color}]"
            if self.position_manager
            else "N/A"
        )
        avg_entry_str = (
            f"{self.position_manager.avg_entry_price:.{self.bot_state.instrument_info.price_precision}f}"
            if self.position_manager
            else "N/A"
        )
        table.add_row("Position Size", position_size_str)
        table.add_row("Avg Entry Price", avg_entry_str)

        if self.position_manager:
            unreal_color = (
                "green" if self.position_manager.unrealized_pnl >= 0 else "red"
            )
            real_color = "green" if self.position_manager.realized_pnl >= 0 else "red"
            table.add_row(
                "Unrealized PnL",
                f"[{unreal_color}]{self.position_manager.unrealized_pnl:.4f}[/{unreal_color}]",
            )
            table.add_row(
                "Realized PnL",
                f"[{real_color}]{self.position_manager.realized_pnl:.4f}[/{real_color}]",
            )
        else:
            table.add_row("Unrealized PnL", "N/A")
            table.add_row("Realized PnL", "N/A")

        if self.order_manager:
            open_orders = self.order_manager.current_orders
            buys = len([o for o in open_orders.values() if o.side == "Buy"])
            sells = len([o for o in open_orders.values() if o.side == "Sell"])
            table.add_row("Open Orders", f"{buys} buys / {sells} sells")
        else:
            table.add_row("Open Orders", "N/A")

        # TA readout
        if self.ta_manager.enabled:
            rsi = self.ta_manager.ta_state["rsi"]
            ema_f = self.ta_manager.ta_state["ema_fast"]
            ema_s = self.ta_manager.ta_state["ema_slow"]
            bbw = self.ta_manager.ta_state["bb_width_pct"]

            rsi_txt = f"{rsi:.1f}" if isinstance(rsi, float) else "N/A"
            ema_trend = (
                "Up"
                if (
                    isinstance(ema_f, float)
                    and isinstance(ema_s, float)
                    and ema_f > ema_s
                )
                else "Down"
                if (
                    isinstance(ema_f, float)
                    and isinstance(ema_s, float)
                    and ema_f < ema_s
                )
                else "N/A"
            )
            bbw_txt = f"{bbw * 100:.2f}%" if isinstance(bbw, float) else "N/A"

            table.add_row("RSI", rsi_txt)
            table.add_row("EMA Trend", ema_trend)
            table.add_row("BB Width", bbw_txt)
        else:
            table.add_row("TA", "Disabled")

        # Volatility
        if len(self.bot_state.recent_prices) >= 30:
            try:
                prices_f = [float(p) for p in list(self.bot_state.recent_prices)[-60:]]
                if len(set(prices_f)) > 1:
                    vol = statistics.stdev(prices_f) / statistics.mean(prices_f)
                    table.add_row("Volatility (1m)", f"{vol:.4%}")
                else:
                    table.add_row("Volatility (1m)", "0.00%")
            except Exception:
                table.add_row("Volatility (1m)", "N/A")
        else:
            table.add_row("Volatility (1m)", "Insufficient data")

        return table

    async def _setup_initial_state(self):
        """Fetches instrument info and initializes managers."""
        instrument_info = await self.http_client.get_instrument_info()
        if not instrument_info:
            raise RuntimeError("Failed to fetch instrument info. Cannot start bot.")
        self.bot_state.instrument_info = instrument_info

        # Initialize OrderManager and PositionManager now that we have instrument info
        self.order_manager = OrderManager(
            self.config, self.http_client, self.bot_state.instrument_info
        )
        self.position_manager = PositionManager(
            self.config, self.http_client, self.order_manager
        )

        # Ensure all existing orders are cancelled at startup
        await self.order_manager.cancel_all_open_orders()

    async def run(self):
        """Main execution loop of the bot."""
        mode = (
            "[bold yellow]DRY RUN[/bold yellow]"
            if self.config.market.dry_run
            else "[bold green]LIVE[/bold green]"
        )
        env = "Testnet" if self.config.market.testnet else "Mainnet"
        logger.info(
            f"Starting bot: {self.config.market.symbol} on {env} in {mode} mode"
        )

        self.loop = asyncio.get_running_loop()  # Store reference to main event loop

        try:
            await self._setup_initial_state()
            await self.websocket_manager.start_streams()

            logger.info("Waiting for initial market data to populate...")
            # Wait until we have at least some orderbook data and a mid price
            timeout_start = time.time()
            while (
                not self.orderbook["bids"]
                or not self.orderbook["asks"]
                or not self.bot_state.last_mid_price
            ) and (time.time() - timeout_start < 15):  # Max 15s wait
                await asyncio.sleep(0.5)

            if not self.bot_state.last_mid_price:
                logger.error(
                    "Failed to receive initial market data within timeout. Exiting."
                )
                return

        except Exception as e:
            logger.critical(f"Initial setup failed: {e}", exc_info=True)
            return

        with Live(
            self.generate_status_table(),
            screen=True,
            refresh_per_second=2,
            console=console,
        ) as live:
            while True:
                try:
                    live.update(self.generate_status_table())

                    if self.http_client.circuit_breaker_active:
                        await asyncio.sleep(
                            1
                        )  # Sleep briefly while circuit breaker is active
                        continue

                    # Risk management check first
                    if (
                        self.position_manager
                        and await self.position_manager.check_and_manage_risk(
                            self.bot_state.last_mid_price
                        )
                    ):
                        logger.info(
                            "Position closed by risk manager, pausing for cooldown."
                        )
                        # Position manager would have cancelled orders and closed position.
                        # We might want to clear bot state or wait for a full reset.
                        await asyncio.sleep(
                            self.config.risk_management.circuit_breaker_cooldown_seconds
                        )  # Use circuit breaker cooldown
                        continue

                    if self.config.market.dry_run:
                        await self._simulate_fills()

                    now = time.time()
                    if (
                        now - self.last_reprice_time
                        < self.config.order_management.order_reprice_delay_seconds
                    ):
                        await asyncio.sleep(0.1)
                        continue

                    # Only proceed if we have a valid mid price from market data
                    if (
                        not self.bot_state.last_mid_price
                        or not self.bot_state.last_known_best_bid
                        or not self.bot_state.last_known_best_ask
                    ):
                        logger.debug(
                            "No valid mid price/orderbook, skipping quote calculation."
                        )
                        await asyncio.sleep(0.5)
                        continue

                    buy_orders, sell_orders = self._calculate_tiered_quotes()

                    if not buy_orders and not sell_orders:
                        if (
                            self.order_manager.current_orders
                        ):  # If no quotes, but orders are open, cancel them
                            logger.info(
                                "No quotes generated, cancelling existing orders."
                            )
                            await self.order_manager.cancel_all_open_orders()
                        await asyncio.sleep(0.5)
                        continue

                    await self.order_manager.manage_orders(buy_orders, sell_orders)
                    self.last_reprice_time = now

                    await asyncio.sleep(0.1)  # Small sleep to yield control

                except asyncio.CancelledError:
                    logger.info("Main loop cancelled.")
                    break
                except Exception as e:
                    logger.error(f"Unhandled main loop error: {e}", exc_info=True)
                    await asyncio.sleep(5)  # Pause on unhandled errors

        logger.info("Bot main loop exited.")

    async def shutdown(self):
        """Performs graceful shutdown of the bot."""
        logger.info("Initiating graceful shutdown...")
        if self.order_manager:
            await self.order_manager.cancel_all_open_orders()
        self.websocket_manager.stop_streams()
        logger.info("Shutdown complete.")


# =========================
# Entry point
# =========================
async def main():
    """Main entry point for the application."""
    config_path = Path(__file__).parent / "config.json"
    try:
        with open(config_path, "rb") as f:
            raw_config = json.loads(f.read())
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
        logger.info("Shutdown signal received (SIGINT/SIGTERM).")
        main_task.cancel()  # Request main bot task to cancel

    if hasattr(signal, "SIGINT"):
        try:
            loop.add_signal_handler(signal.SIGINT, _signal_handler)
            loop.add_signal_handler(signal.SIGTERM, _signal_handler)
        except NotImplementedError:
            logger.warning("Signal handlers not available on this platform.")

    try:
        await main_task
    except asyncio.CancelledError:
        logger.info("Bot task was cancelled.")
    finally:
        await bot.shutdown()  # Ensure shutdown logic runs
        logger.info("Application exiting.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application interrupted by user (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Fatal unhandled error in application: {e}", exc_info=True)
