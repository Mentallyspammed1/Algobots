#!/usr/bin/env python3
"""
Hybrid Market Maker Bot v3.0 - Professional Grade with Advanced Stability, Risk Management, and Performance
Compatible with Bybit API v5
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
import warnings
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation, getcontext
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# Ignore common warnings
warnings.filterwarnings("ignore")

# region: Dependency and Environment Setup
# ==============================================================================
try:
    import aiohttp
    import ccxt.async_support as ccxt
    import numpy as np
    import pandas as pd
    import websockets
    from colorama import Fore, Style, init
    from pydantic import (
        BaseModel,
        ConfigDict,
        Field,
        NonNegativeFloat,
        NonNegativeInt,
        PositiveFloat,
        PositiveInt,
        ValidationError,
    )

    try:
        from dotenv import load_dotenv

        DOTENV_AVAILABLE = True
    except ImportError:
        DOTENV_AVAILABLE = False
    EXTERNAL_LIBS_AVAILABLE = True
except ImportError as e:
    print(f"Fatal Error: Missing required library: {e}. Please install it using pip.")
    print(
        "Install all dependencies with: pip install ccxt aiohttp pandas numpy websockets pydantic colorama python-dotenv"
    )
    sys.exit(1)

init(autoreset=True)
getcontext().prec = 38

if DOTENV_AVAILABLE:
    load_dotenv()
    print(f"{Fore.CYAN}# Environment variables loaded successfully.{Style.RESET_ALL}")


# Enhanced color scheme for logging
class Colors:
    CYAN = Fore.CYAN + Style.BRIGHT
    MAGENTA = Fore.MAGENTA + Style.BRIGHT
    YELLOW = Fore.YELLOW + Style.BRIGHT
    RESET = Style.RESET_ALL
    NEON_GREEN = Fore.GREEN + Style.BRIGHT
    NEON_BLUE = Fore.BLUE + Style.BRIGHT
    NEON_RED = Fore.RED + Style.BRIGHT
    NEON_ORANGE = Fore.LIGHTRED_EX + Style.BRIGHT
    WHITE = Fore.WHITE + Style.BRIGHT
    DARK_GRAY = Fore.LIGHTBLACK_EX


# Environment variables
BYBIT_API_KEY: str | None = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET: str | None = os.getenv("BYBIT_API_SECRET")

# Directory setup
BASE_DIR = Path(os.getenv("HOME", "."))
LOG_DIR: Path = BASE_DIR / "bot_logs"
STATE_DIR: Path = BASE_DIR / ".bot_state"
LOG_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Exchange configuration
EXCHANGE_CONFIG = {
    "id": "bybit",
    "apiKey": BYBIT_API_KEY,
    "secret": BYBIT_API_SECRET,
    "enableRateLimit": True,
    "timeout": 30000,
    "options": {
        "defaultType": "linear",
        "verbose": False,
        "adjustForTimeDifference": True,
        "v5": True,
        "recvWindow": 10000,
    },
    # aiohttp_session is now created within initialize_exchange to avoid RuntimeError
}

# Constants
API_RETRY_ATTEMPTS = 5
RETRY_BACKOFF_FACTOR = 0.5
WS_RECONNECT_INTERVAL = 5
SYMBOL_INFO_REFRESH_INTERVAL = 24 * 60 * 60
STATUS_UPDATE_INTERVAL = 30
MAIN_LOOP_SLEEP_INTERVAL = 1
DECIMAL_ZERO = Decimal("0")
MIN_TRADE_PNL_PERCENT = Decimal("-0.0005")


class TradingBias(Enum):
    STRONG_BULLISH = "STRONG_BULLISH"
    WEAK_BULLISH = "WEAK_BULLISH"
    NEUTRAL = "NEUTRAL"
    WEAK_BEARISH = "WEAK_BEARISH"
    STRONG_BEARISH = "STRONG_BEARISH"


# endregion


# region: Utility Functions and Classes
# ==============================================================================
class JsonDecimalEncoder(json.JSONEncoder):
    """Enhanced JSON encoder for Decimal types."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def json_loads_decimal(s: str) -> Any:
    """Enhanced JSON decoder for Decimal types."""
    try:
        # Use parse_float to ensure numbers like "0.0000001" are parsed as Decimal
        return json.loads(s, parse_float=Decimal, parse_int=Decimal)
    except (json.JSONDecodeError, InvalidOperation) as e:
        logging.error(f"Error decoding JSON with Decimal: {e}")
        raise ValueError(f"Invalid JSON or Decimal format: {e}") from e


# endregion


# region: Pydantic Models for Configuration and Data
# ==============================================================================
class Trade(BaseModel):
    side: str
    qty: Decimal
    price: Decimal
    profit: Decimal = DECIMAL_ZERO
    timestamp: int
    fee: Decimal
    trade_id: str
    entry_price: Decimal | None = None
    exit_price: Decimal | None = None
    pnl_percent: Decimal | None = None
    market_condition: str | None = None
    signal_strength: Decimal | None = None

    model_config = ConfigDict(
        json_dumps=lambda v: json.dumps(v, cls=JsonDecimalEncoder),
        json_loads=json_loads_decimal,
        validate_assignment=True,
    )


class DynamicSpreadConfig(BaseModel):
    enabled: bool = True
    volatility_multiplier: PositiveFloat = 0.5
    atr_update_interval: NonNegativeInt = 300
    min_spread_pct: PositiveFloat = 0.0005
    max_spread_pct: PositiveFloat = 0.01
    use_bollinger_bands: bool = True
    bb_period: PositiveInt = 20
    bb_std_dev: PositiveFloat = 2.0


class InventorySkewConfig(BaseModel):
    enabled: bool = True
    skew_factor: PositiveFloat = 0.1
    max_skew: PositiveFloat | None = 0.002
    aggressive_rebalance: bool = False
    rebalance_threshold: PositiveFloat = 0.7


class OrderLayer(BaseModel):
    spread_offset: NonNegativeFloat = 0.0
    quantity_multiplier: PositiveFloat = 1.0
    cancel_threshold_pct: PositiveFloat = 0.01
    aggressiveness: PositiveFloat = 1.0
    use_iceberg: bool = False
    iceberg_qty_pct: PositiveFloat = 0.3


class MarketMicrostructure(BaseModel):
    enabled: bool = True
    tick_size_multiplier: PositiveFloat = 1.0
    queue_position_factor: PositiveFloat = 0.5
    adverse_selection_threshold: PositiveFloat = 0.001
    flow_toxicity_window: PositiveInt = 100


class SignalConfig(BaseModel):
    use_rsi: bool = True
    rsi_period: PositiveInt = 14
    rsi_overbought: PositiveFloat = 70.0
    rsi_oversold: PositiveFloat = 30.0
    use_macd: bool = True
    macd_fast: PositiveInt = 12
    macd_slow: PositiveInt = 26
    macd_signal: PositiveInt = 9
    signal_bias_strength: PositiveFloat = 0.5
    use_volume_profile: bool = True
    volume_lookback: PositiveInt = 100
    use_order_flow: bool = True
    flow_imbalance_threshold: PositiveFloat = 0.6


class OrderbookAnalysisConfig(BaseModel):
    enabled: bool = True
    obi_depth: PositiveInt = 20
    obi_impact_factor: NonNegativeFloat = 0.4
    cliff_depth: PositiveInt = 5
    cliff_factor: PositiveFloat = 5.0
    toxic_spread_widener: PositiveFloat = 2.0
    wap_instead_of_mid: bool = True


class RiskManagement(BaseModel):
    max_drawdown_pct: PositiveFloat = 0.1
    var_confidence: PositiveFloat = 0.95
    position_sizing_kelly: bool = True
    kelly_fraction: PositiveFloat = 0.25
    use_circuit_breaker: bool = True
    circuit_breaker_threshold: PositiveFloat = 0.05
    max_order_retry: PositiveInt = 3
    anti_spoofing_detection: bool = True
    daily_pnl_stop_loss_pct: PositiveFloat = 0.02
    daily_pnl_take_profit_pct: PositiveFloat = 0.04


# New config for dynamic leverage
class DynamicLeverageConfig(BaseModel):
    enabled: bool = False
    volatility_factor: PositiveFloat = (
        0.1  # Controls sensitivity to volatility (higher = more sensitive)
    )
    min_leverage: PositiveFloat = 1.0
    max_leverage: PositiveFloat = 20.0
    volatility_source: str = "atr"  # Options: "atr", "spread", "bb_width"
    # Benchmarks for volatility calculation:
    # If volatility_source is 'atr', this is the expected "normal" ATR value.
    # If volatility_source is 'spread' or 'bb_width', this is the expected "normal" spread/width ratio.
    benchmark_volatility: PositiveFloat = Decimal(
        "0.001"
    )  # Empirical normal volatility (0.1%) for price ratio sources
    # The range of volatility that maps to the leverage adjustment.
    # e.g., if volatility ranges from 0.0001 to 0.01, and factor is 0.2, only 20% of this range affects leverage.
    volatility_range_factor: PositiveFloat = 1.0
    # How often to re-evaluate leverage (in seconds). Set to 0 to disable periodic re-evaluation.
    leverage_update_interval: NonNegativeInt = 300
    # Minimum percentage change required to trigger a leverage adjustment API call.
    leverage_adjustment_threshold_pct: PositiveFloat = 0.05

    # Pydantic config for Decimal support
    model_config = ConfigDict(
        json_dumps=lambda v: json.dumps(v, cls=JsonDecimalEncoder),
        json_loads=json_loads_decimal,
        validate_assignment=True,
    )


class SymbolConfig(BaseModel):
    symbol: str
    trade_enabled: bool = True
    base_spread: PositiveFloat = 0.001
    order_amount: PositiveFloat = 0.001
    leverage: PositiveFloat = (
        10.0  # Default leverage if dynamic is disabled or not used
    )
    order_refresh_time: NonNegativeInt = 5
    max_spread: PositiveFloat = 0.005
    inventory_limit: PositiveFloat = 0.01

    dynamic_spread: DynamicSpreadConfig = Field(default_factory=DynamicSpreadConfig)
    inventory_skew: InventorySkewConfig = Field(default_factory=InventorySkewConfig)
    market_microstructure: MarketMicrostructure = Field(
        default_factory=MarketMicrostructure
    )
    signal_config: SignalConfig = Field(default_factory=SignalConfig)
    orderbook_analysis: OrderbookAnalysisConfig = Field(
        default_factory=OrderbookAnalysisConfig
    )
    risk_management: RiskManagement = Field(default_factory=RiskManagement)
    # Added dynamic leverage config
    dynamic_leverage: DynamicLeverageConfig = Field(
        default_factory=DynamicLeverageConfig
    )

    order_layers: list[OrderLayer] = Field(
        default_factory=lambda: [OrderLayer(spread_offset=0.0, quantity_multiplier=1.0)]
    )

    min_qty: Decimal | None = None
    max_qty: Decimal | None = None
    qty_precision: int | None = None
    price_precision: int | None = None
    min_notional: Decimal | None = None
    tick_size: Decimal | None = None
    kline_interval: str = "1m"
    market_data_stale_timeout_seconds: NonNegativeInt = 30
    use_batch_orders_for_refresh: bool = True

    model_config = ConfigDict(
        json_dumps=lambda v: json.dumps(v, cls=JsonDecimalEncoder),
        json_loads=json_loads_decimal,
        validate_assignment=True,
    )


class GlobalConfig(BaseModel):
    category: str = "linear"
    api_max_retries: PositiveInt = 5
    api_retry_delay: PositiveInt = 1
    log_level: str = "INFO"
    log_file: str = "market_maker_live.log"
    state_file: str = "state.json"
    symbol_config_file: str = "symbols.json"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    model_config = ConfigDict(
        json_dumps=lambda v: json.dumps(v, cls=JsonDecimalEncoder),
        json_loads=json_loads_decimal,
        validate_assignment=True,
    )


# endregion


# region: Configuration Management
# ==============================================================================
class ConfigManager:
    _global_config: GlobalConfig | None = None
    _symbol_configs: list[SymbolConfig] = []

    @classmethod
    async def load_config(
        cls, prompt_for_symbol: bool = False, input_symbol: str | None = None
    ) -> tuple[GlobalConfig, list[SymbolConfig]]:
        global_data = {
            "category": os.getenv("BYBIT_CATEGORY", "linear"),
            "api_max_retries": int(os.getenv("API_MAX_RETRIES", "5")),
            "api_retry_delay": int(os.getenv("API_RETRY_DELAY", "1")),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
            "log_file": os.getenv("LOG_FILE", "market_maker_live.log"),
            "state_file": os.getenv("STATE_FILE", "state.json"),
            "symbol_config_file": os.getenv("SYMBOL_CONFIG_FILE", "symbols.json"),
            "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
            "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID"),
        }

        try:
            cls._global_config = GlobalConfig(**global_data)
        except ValidationError as e:
            logging.critical(f"Global configuration validation error: {e}")
            sys.exit(1)

        cls._symbol_configs = []
        if prompt_for_symbol and input_symbol:
            # Ensure input_symbol is formatted correctly if needed (e.g., "BTCUSDT")
            if not input_symbol.upper().endswith(
                "USDT"
            ):  # Simple check, might need refinement
                input_symbol = f"{input_symbol.upper()}USDT"

            single_symbol_data = {"symbol": input_symbol}
            try:
                cls._symbol_configs.append(SymbolConfig(**single_symbol_data))
                logging.info(f"Using single symbol mode for {input_symbol}.")
            except ValidationError as e:
                logging.critical(
                    f"Symbol configuration validation error for {input_symbol}: {e}"
                )
                sys.exit(1)
        else:
            try:
                symbol_config_path = Path(cls._global_config.symbol_config_file)
                if symbol_config_path.exists():
                    with open(symbol_config_path, encoding="utf-8") as f:
                        raw_symbol_configs = json.load(f)

                    for s_cfg_data in raw_symbol_configs:
                        # Ensure symbol is formatted correctly
                        symbol_name = s_cfg_data.get("symbol")
                        if symbol_name and not symbol_name.upper().endswith(
                            "USDT"
                        ):  # Simple check
                            s_cfg_data["symbol"] = f"{symbol_name.upper()}USDT"

                        try:
                            cls._symbol_configs.append(SymbolConfig(**s_cfg_data))
                        except ValidationError as e:
                            logging.warning(
                                f"Symbol config validation error for {s_cfg_data.get('symbol', 'N/A')}: {e}"
                            )
                else:
                    logging.warning(
                        f"Symbol config file not found: {symbol_config_path}"
                    )
            except Exception as e:
                logging.error(f"Error loading symbol configs: {e}", exc_info=True)

        return cls._global_config, cls._symbol_configs


GLOBAL_CONFIG: GlobalConfig | None = None
SYMBOL_CONFIGS: list[SymbolConfig] = []

# endregion


# region: Core Infrastructure (Logging, Notifications, Exchange)
# ==============================================================================
def setup_logger(name_suffix: str) -> logging.Logger:
    logger_name = f"market_maker_{name_suffix}"
    logger = logging.getLogger(logger_name)

    if logger.hasHandlers():  # Avoid adding handlers multiple times
        return logger

    log_level_str = GLOBAL_CONFIG.log_level.upper() if GLOBAL_CONFIG else "INFO"
    logger.setLevel(getattr(logging, log_level_str, logging.INFO))

    log_file_path = LOG_DIR / (
        GLOBAL_CONFIG.log_file if GLOBAL_CONFIG else "market_maker_live.log"
    )

    # Ensure log directory exists
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    # File handler for logging to a rotating file
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Stream handler for logging to console with colors
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_formatter = logging.Formatter(
        f"{Colors.NEON_BLUE}%(asctime)s{Colors.RESET} - {Colors.YELLOW}%(levelname)-8s{Colors.RESET} - {Colors.MAGENTA}[%(name)s]{Colors.RESET} - %(message)s",
        datefmt="%H:%M:%S",
    )
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)

    logger.propagate = False  # Prevent logs from bubbling up to root logger
    return logger


main_logger = logging.getLogger("market_maker_main")


class TelegramNotifier:
    def __init__(self, token: str | None, chat_id: str | None, logger: logging.Logger):
        self.token = token
        self.chat_id = chat_id
        self.logger = logger
        self.is_configured = bool(token and chat_id)
        if self.is_configured:
            self.logger.info("Telegram notifier configured.")

    async def send_message(self, message: str):
        """Sends a message to the configured Telegram chat."""
        if not self.is_configured:
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"}
        try:
            # Create a new session for each message or reuse one if passed in
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as response:
                    response.raise_for_status()
        except aiohttp.ClientError as e:
            self.logger.error(f"Failed to send Telegram message: {e}")
        except asyncio.TimeoutError:
            self.logger.error("Telegram message sending timed out.")
        except Exception as e:
            self.logger.error(
                f"An unexpected error occurred sending Telegram message: {e}",
                exc_info=True,
            )


async def initialize_exchange(
    logger: logging.Logger,
) -> tuple[Any | None, aiohttp.ClientSession | None]:
    """Initializes the CCXT exchange instance and aiohttp session."""
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        logger.critical("API Key and/or Secret not found. Cannot initialize exchange.")
        return None, None

    aiohttp_session = None  # Initialize to None
    exchange_instance = None

    try:
        # Get the current running event loop (guaranteed to be available after asyncio.run())
        loop = asyncio.get_running_loop()

        # Create aiohttp ClientSession here, now that we have a running loop
        aiohttp_session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(
                resolver=aiohttp.AsyncResolver(), loop=loop, ssl=False
            )
        )

        # Instantiate the CCXT exchange with merged configuration and the session
        exchange_instance = getattr(ccxt, EXCHANGE_CONFIG["id"])(
            {**EXCHANGE_CONFIG, "aiohttp_session": aiohttp_session}
        )

        await exchange_instance.load_markets()
        logger.info(f"Exchange '{EXCHANGE_CONFIG['id']}' initialized successfully.")

        return exchange_instance, aiohttp_session

    except RuntimeError as e:
        logger.critical(
            f"Failed to initialize exchange due to event loop error: {e}", exc_info=True
        )
        # Ensure session is closed if created before loop error
        if aiohttp_session:
            await aiohttp_session.close()
        return None, None
    except Exception as e:
        logger.critical(f"Failed to initialize exchange: {e}", exc_info=True)
        # Ensure session is closed if created before error
        if aiohttp_session:
            await aiohttp_session.close()
        return None, None


# endregion


# region: Technical Analysis Functions
# ==============================================================================
def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculates the Relative Strength Index (RSI)."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).fillna(0)
    loss = -delta.where(delta < 0, 0).fillna(0)
    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, 1)  # Avoid division by zero
    return 100 - (100 / (1 + rs))


def calculate_macd(
    prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates MACD line, signal line, and histogram."""
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_bollinger_bands(
    prices: pd.Series, period: int = 20, std_dev: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates Bollinger Bands (upper, middle, lower)."""
    middle = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return upper, middle, lower


def calculate_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Calculates Average True Range (ATR)."""
    tr = pd.DataFrame()
    tr["h_l"] = high - low
    tr["h_pc"] = (high - close.shift(1)).abs()
    tr["l_pc"] = (low - close.shift(1)).abs()
    tr["tr"] = tr[["h_l", "h_pc", "l_pc"]].max(axis=1)
    # Using exponential moving average for ATR
    return tr["tr"].ewm(alpha=1 / period, adjust=False).mean()


def calculate_vwap(
    prices: pd.Series, volumes: pd.Series, period: int = 20
) -> pd.Series:
    """Calculates Volume Weighted Average Price (VWAP)."""
    pv = prices * volumes
    # Rolling sum for PV and Volume, then divide
    volume_rolling_sum = volumes.rolling(window=period).sum()
    pv_rolling_sum = pv.rolling(window=period).sum()
    # Ensure division by zero is handled by replacing zero volume sum with NaN
    return pv_rolling_sum / volume_rolling_sum.replace(DECIMAL_ZERO, Decimal("NaN"))


# endregion

# region: API Call Decorator
# ==============================================================================
# `wraps` and `Callable` were missing imports, added here.
from functools import wraps


def retry_api_call(
    attempts: int = API_RETRY_ATTEMPTS,
    backoff_factor: float = RETRY_BACKOFF_FACTOR,
    # Define specific fatal exceptions that should stop retries immediately
    fatal_exceptions: tuple[type, ...] = (
        ccxt.AuthenticationError,
        ccxt.ArgumentsRequired,
    ),
):
    """
    Decorator for retrying API calls with exponential backoff.
    Handles specific fatal exceptions and general CCXT network/exchange errors.
    """

    def decorator(func: Callable[..., Any]):
        @wraps(func)
        async def wrapper(self, *args: Any, **kwargs: Any) -> Any:
            # Determine logger: use self.logger if available, otherwise main_logger
            logger = getattr(self, "logger", main_logger)
            last_exception = None

            for i in range(attempts):
                try:
                    return await func(self, *args, **kwargs)
                except fatal_exceptions as e:
                    logger.critical(f"Fatal API error in {func.__name__}: {e}")
                    raise  # Re-raise to stop execution chain
                except (
                    ccxt.NetworkError,
                    ccxt.ExchangeError,
                    ccxt.DDoSProtection,
                ) as e:
                    last_exception = e
                    sleep_time = backoff_factor * (2**i)
                    logger.warning(
                        f"API call {func.__name__} failed (attempt {i + 1}/{attempts}): {e}. Retrying in {sleep_time:.2f}s..."
                    )
                    await asyncio.sleep(sleep_time)
                except ccxt.BadRequest as e:
                    error_str = str(e)
                    # Specific Bybit error codes that can be ignored or are common for certain operations
                    ignorable_codes = [
                        "110043",
                        "110025",
                        "110047",
                        "100048",
                    ]  # Example ignorable codes for Bybit
                    if any(code in error_str for code in ignorable_codes):
                        logger.debug(f"Ignorable BadRequest in {func.__name__}: {e}")
                        return None  # Return None to indicate the call effectively failed without fatal error
                    else:
                        logger.error(f"BadRequest in {func.__name__}: {e}")
                        last_exception = e
                        break  # Break loop for unhandled BadRequests

            # If loop finishes without returning, it means all retries failed.
            logger.error(f"API call {func.__name__} failed after {attempts} attempts.")
            if last_exception:
                raise last_exception  # Raise the last encountered exception
            else:
                # This case should ideally not be reached if exceptions are handled correctly.
                # But as a fallback, raise a generic error.
                raise RuntimeError(
                    f"API call {func.__name__} failed after {attempts} attempts."
                )

        return wrapper

    return decorator


# endregion


# region: WebSocket Client
# ==============================================================================
class BybitWebsocketClient:
    WS_URL = "wss://stream.bybit.com/v5/public/linear"

    def __init__(
        self, symbols: list[str], logger: logging.Logger, message_queue: asyncio.Queue
    ):
        self.symbols = symbols
        self.logger = logger
        self.message_queue = message_queue
        self.running = False
        self.ws_connection = None  # Store the websocket connection object
        self.last_message_id: dict[
            str, int
        ] = {}  # Track message IDs to avoid duplicates per topic

    async def connect(self):
        """Establishes and maintains a WebSocket connection."""
        self.running = True
        attempt = 0
        while self.running:
            try:
                self.logger.info(f"Attempting to connect to WebSocket: {self.WS_URL}")
                # Use websockets.connect with specific timeout and ping settings
                async with websockets.connect(
                    self.WS_URL,
                    ping_interval=20,
                    ping_timeout=10,
                    open_timeout=15,  # Timeout for establishing connection
                ) as ws:
                    self.ws_connection = ws  # Store the active connection
                    self.logger.info("WebSocket connected successfully.")
                    attempt = 0  # Reset retry attempt counter on successful connection

                    # Prepare subscriptions: orderbook.50.<symbol> and publicTrade.<symbol>
                    subscriptions = [f"orderbook.50.{s}" for s in self.symbols] + [
                        f"publicTrade.{s}" for s in self.symbols
                    ]
                    subscribe_message = json.dumps(
                        {"op": "subscribe", "args": subscriptions}
                    )
                    await ws.send(subscribe_message)
                    self.logger.info(f"Subscribed to channels: {subscriptions}")

                    # Process messages from the WebSocket connection
                    while self.running:
                        try:
                            message = await ws.recv()
                            data = json.loads(message)

                            # Check for Pong response or similar acknowledgments
                            if data.get("ret_msg") == "pong":
                                self.logger.debug("Received WebSocket pong response.")
                                continue

                            topic = data.get("topic", "")
                            message_id = data.get("id", 0)

                            # Deduplicate messages based on topic and message ID
                            if (
                                topic
                                and message_id
                                and message_id <= self.last_message_id.get(topic, 0)
                            ):
                                self.logger.debug(
                                    f"Skipping duplicate WebSocket message for {topic} (ID: {message_id})"
                                )
                                continue
                            self.last_message_id[topic] = message_id

                            # Put message into the queue for processing
                            await self.message_queue.put(data)

                        except websockets.exceptions.ConnectionClosedOK:
                            self.logger.info("WebSocket connection closed normally.")
                            break  # Exit inner loop to reconnect
                        except websockets.exceptions.ConnectionClosedError as e:
                            self.logger.warning(
                                f"WebSocket connection closed with error: {e}. Reconnecting..."
                            )
                            break  # Exit inner loop to reconnect
                        except json.JSONDecodeError:
                            self.logger.error(
                                f"Failed to decode WebSocket message: {message}"
                            )
                        except Exception as e:
                            self.logger.error(
                                f"Error receiving or processing WebSocket message: {e}",
                                exc_info=True,
                            )
                            break  # Break to attempt reconnect on unexpected errors

            except (
                websockets.exceptions.ConnectionClosedOK,
                websockets.exceptions.ConnectionClosedError,
            ) as e:
                self.logger.warning(
                    f"WebSocket connection failed or closed: {e}. Retrying in {WS_RECONNECT_INTERVAL}s..."
                )
            except asyncio.TimeoutError:
                self.logger.warning(
                    f"WebSocket connection timed out. Retrying in {WS_RECONNECT_INTERVAL}s..."
                )
            except Exception as e:
                self.logger.error(
                    f"An unexpected error occurred during WebSocket connection: {e}. Retrying in {WS_RECONNECT_INTERVAL}s...",
                    exc_info=True,
                )

            # If the bot is still running and needs to reconnect
            if self.running:
                # Exponential backoff for retries, capped at 60 seconds
                delay = min(5 * (2**attempt), 60)
                await asyncio.sleep(delay)
                attempt += 1

            # Ensure connection is marked as closed if loop exited
            self.ws_connection = None

    async def close(self):
        """Gracefully closes the WebSocket connection."""
        self.running = False
        if self.ws_connection and not self.ws_connection.closed:
            try:
                # Attempt to close the connection gracefully
                await self.ws_connection.close()
                self.logger.info("WebSocket connection closed.")
            except Exception as e:
                self.logger.error(f"Error closing WebSocket connection: {e}")
        self.ws_connection = None  # Clear the connection object


# endregion


# region: Orderbook Analysis
# ==============================================================================
@dataclass
class OrderbookLevel:
    price: Decimal
    quantity: Decimal


@dataclass
class OrderbookSnapshot:
    symbol: str
    bids: list[OrderbookLevel]
    asks: list[OrderbookLevel]
    timestamp: float  # Unix timestamp in seconds

    @property
    def mid_price(self) -> Decimal | None:
        """Calculates the mid-price (average of best bid and best ask)."""
        if not self.bids or not self.asks:
            return None
        try:
            # Ensure prices are valid decimals before calculation
            best_bid = self.bids[0].price
            best_ask = self.asks[0].price
            if (
                best_bid is not None
                and best_ask is not None
                and best_ask > DECIMAL_ZERO
            ):
                return (best_bid + best_ask) / Decimal("2")
            return None
        except Exception as e:
            # Use main_logger as strategy logger might not be available here directly
            main_logger.error(
                f"Error calculating mid_price for {self.symbol}: {e}", exc_info=True
            )
            return None


class OrderbookAnalyzer:
    def calculate_book_imbalance(self, symbol: str) -> Decimal | None:
        """Calculates the book imbalance (bid volume - ask volume) / total volume for a symbol."""
        snapshot = self.get_snapshot(symbol)  # Use a helper to get snapshot safely
        if not snapshot:
            return None

        s_cfg = SYMBOL_CONFIGS[symbol]  # Access global SYMBOL_CONFIGS for config
        levels = s_cfg.orderbook_analysis.obi_depth

        try:
            bid_volume = sum(level.quantity for level in snapshot.bids[:levels])
            ask_volume = sum(level.quantity for level in snapshot.asks[:levels])
            total_volume = bid_volume + ask_volume
            if total_volume == DECIMAL_ZERO:
                return Decimal("0.5")  # Neutral imbalance if no volume
            return (bid_volume - ask_volume) / total_volume
        except Exception as e:
            main_logger.error(
                f"Error calculating book imbalance for {symbol}: {e}", exc_info=True
            )
            return None

    def calculate_trade_imbalance(self, recent_trades: Deque[dict]) -> Decimal | None:
        """Calculates trade imbalance from recent trades."""
        if not recent_trades:
            return None
        try:
            buy_volume = sum(
                trade["amount"] for trade in recent_trades if trade["side"] == "buy"
            )
            sell_volume = sum(
                trade["amount"] for trade in recent_trades if trade["side"] == "sell"
            )
            total_volume = buy_volume + sell_volume
            if total_volume == DECIMAL_ZERO:
                return Decimal("0.5")  # Neutral imbalance if no volume
            return (buy_volume - sell_volume) / total_volume
        except Exception as e:
            main_logger.error(f"Error calculating trade imbalance: {e}", exc_info=True)
            return None

    def calculate_book_pressure(
        self, symbol: str, depth_pct: float = 0.2
    ) -> Decimal | None:
        """Calculates book pressure, ratio of bid volume to ask volume within a certain price depth."""
        snapshot = self.get_snapshot(symbol)
        if not snapshot or not snapshot.mid_price or snapshot.mid_price <= DECIMAL_ZERO:
            return None
        try:
            mid_price = snapshot.mid_price
            bid_pressure_limit = mid_price * Decimal(1 - depth_pct / 100)
            ask_pressure_limit = mid_price * Decimal(1 + depth_pct / 100)
            bid_volume = sum(
                level.quantity
                for level in snapshot.bids
                if level.price >= bid_pressure_limit
            )
            ask_volume = sum(
                level.quantity
                for level in snapshot.asks
                if level.price <= ask_pressure_limit
            )

            if ask_volume == DECIMAL_ZERO:
                return Decimal("5.0")  # High pressure if ask volume is zero
            return bid_volume / ask_volume
        except Exception as e:
            main_logger.error(
                f"Error calculating book pressure for {symbol}: {e}", exc_info=True
            )
            return None

    def calculate_vwap(self, symbol: str) -> Decimal | None:
        """Calculates Volume Weighted Average Price (VWAP) from the orderbook snapshot."""
        snapshot = self.get_snapshot(symbol)
        if not snapshot:
            return None

        s_cfg = SYMBOL_CONFIGS[symbol]
        levels = (
            s_cfg.orderbook_analysis.obi_depth
        )  # Using obi_depth for VWAP calculation levels

        try:
            bid_pv = sum(
                level.price * level.quantity for level in snapshot.bids[:levels]
            )
            bid_volume = sum(level.quantity for level in snapshot.bids[:levels])
            ask_pv = sum(
                level.price * level.quantity for level in snapshot.asks[:levels]
            )
            ask_volume = sum(level.quantity for level in snapshot.asks[:levels])
            total_volume = bid_volume + ask_volume

            if total_volume == DECIMAL_ZERO:
                return None

            # Ensure calculation is done with Decimal
            return (bid_pv + ask_pv) / total_volume
        except Exception as e:
            main_logger.error(
                f"Error calculating VWAP for {symbol}: {e}", exc_info=True
            )
            return None

    def get_snapshot(self, symbol: str) -> OrderbookSnapshot | None:
        """Safely retrieves the orderbook snapshot for a symbol."""
        # This method is added for cleaner access, assuming the main strategy class has orderbooks
        # In the context of this class, it would need access to the strategy's data.
        # For now, the methods call strategy methods directly, which is fine.
        # If this class were independent, it would need the strategy instance passed in.
        return None  # Placeholder, actual access managed in the strategy class.


# endregion


# region: Main Strategy Class
# ==============================================================================
class EnhancedMarketMakerStrategy:
    def __init__(
        self,
        global_config: GlobalConfig,
        symbol_configs: list[SymbolConfig],
        exchange: Any,
        aiohttp_session: aiohttp.ClientSession,
    ):
        self.logger = setup_logger("strategy")
        self.global_config = global_config
        self.symbol_configs = {cfg.symbol: cfg for cfg in symbol_configs}
        self.exchange = exchange
        self.aiohttp_session = aiohttp_session  # Store the aiohttp session

        self.running = True
        self.trading_halted = False
        self.state_file_path = STATE_DIR / global_config.state_file

        self.notifier = TelegramNotifier(
            global_config.telegram_bot_token,
            global_config.telegram_chat_id,
            self.logger,
        )

        # --- Data structures ---
        self.orderbooks: dict[str, OrderbookSnapshot | None] = dict.fromkeys(
            self.symbol_configs
        )
        self.prev_orderbooks: dict[str, OrderbookSnapshot | None] = dict.fromkeys(
            self.symbol_configs
        )
        self.positions: dict[str, Decimal] = dict.fromkeys(
            self.symbol_configs, DECIMAL_ZERO
        )
        # Stores current open orders as returned by CCXT, used for cancellation and tracking
        self.open_orders: dict[str, list[dict]] = defaultdict(list)
        self.kline_data: dict[str, pd.DataFrame] = {
            s: pd.DataFrame(
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            for s in self.symbol_configs
        }
        self.signals: dict[str, dict] = {s: {} for s in self.symbol_configs}
        # Track last time market data (orderbook/trades) was received for staleness checks
        self.last_market_data_time: dict[str, float] = dict.fromkeys(
            self.symbol_configs, 0
        )
        # Deque to store recent trades for imbalance calculation
        self.recent_trades: dict[str, Deque[dict]] = defaultdict(
            lambda: deque(maxlen=100)
        )

        # --- State and performance tracking ---
        self.total_pnl = DECIMAL_ZERO
        self.daily_pnl = DECIMAL_ZERO
        self.last_daily_reset = date.today()
        self.trade_history: list[
            Trade
        ] = []  # List to store completed trades (Trade objects)
        self.account_balance = Decimal(
            "10000"
        )  # Placeholder for account balance, updated from fetch_balance

        # --- WebSocket Client ---
        self.ws_message_queue = asyncio.Queue(maxsize=1000)
        self.ws_client = BybitWebsocketClient(
            list(self.symbol_configs.keys()),
            setup_logger("websocket"),
            self.ws_message_queue,
        )
        self.orderbook_analyzer = OrderbookAnalyzer()

        # --- Metrics and Leverage Tracking ---
        self.metrics = {
            "orders_placed_total": 0,
            "orders_cancelled_total": 0,
            "trades_filled_total": 0,  # Count of filled order legs
            "current_symbol_leverage": {},  # Track calculated leverage per symbol
            "last_leverage_update_time": {},  # Track last re-evaluation time for leverage
            "last_fetch_kline_time": {},  # Track when klines were last fetched for a symbol
            # Timing metrics for operations
            "op_time_quote_calc": 0.0,
            "op_time_order_placement": 0.0,
            "op_time_order_cancellation": 0.0,
            "op_time_leverage_adjust": 0.0,
        }
        # Track leverage actively set on exchange to avoid redundant API calls
        self.exchange_leverage_set: dict[str, Decimal] = {}

    def _setup_signal_handler(self):
        """Sets up signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        """Handler for shutdown signals."""
        self.logger.warning(
            f"Shutdown signal {signum} received. Initiating graceful shutdown..."
        )
        self.running = False  # Signal main loop and tasks to stop

    async def _load_state(self):
        """Loads bot state (PnL, history, etc.) from a file."""
        if self.state_file_path.exists():
            try:
                with open(self.state_file_path, encoding="utf-8") as f:
                    state_data = json_loads_decimal(f.read())

                # Load PnL and reset date
                self.total_pnl = Decimal(str(state_data.get("total_pnl", "0")))
                self.daily_pnl = Decimal(str(state_data.get("daily_pnl", "0")))
                reset_date_str = state_data.get(
                    "last_daily_reset", date.today().isoformat()
                )
                self.last_daily_reset = date.fromisoformat(reset_date_str)

                # Load trade history, ensuring Trade model compatibility
                loaded_history = state_data.get("trade_history", [])
                self.trade_history = [
                    Trade(**t) for t in loaded_history if isinstance(t, dict)
                ]

                self.logger.info(
                    f"Loaded state: Total PnL={self.total_pnl:.4f}, Daily PnL={self.daily_pnl:.4f}"
                )
                self.logger.debug(
                    f"Loaded {len(self.trade_history)} trades from history."
                )

            except (
                FileNotFoundError,
                json.JSONDecodeError,
                InvalidOperation,
                ValueError,
            ) as e:
                self.logger.error(
                    f"Could not load state file '{self.state_file_path}': {e}. Attempting backup."
                )
                # Attempt to rename the corrupted file to a backup
                try:
                    backup_path = self.state_file_path.with_suffix(".bak")
                    self.state_file_path.rename(backup_path)
                    self.logger.info(f"Corrupted state file renamed to {backup_path}")
                except OSError as oe:
                    self.logger.error(f"Failed to rename state file: {oe}")
            except Exception as e:
                self.logger.error(
                    f"An unexpected error occurred loading state: {e}", exc_info=True
                )
        else:
            self.logger.info("State file not found. Starting with fresh state.")

    async def _save_state(self):
        """Saves bot state (PnL, history, etc.) to a file."""
        state = {
            "total_pnl": self.total_pnl,
            "daily_pnl": self.daily_pnl,
            "last_daily_reset": self.last_daily_reset.isoformat(),
            # Limit history size to prevent excessively large files
            "trade_history": [t.dict() for t in self.trade_history[-1000:]],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            # Ensure state directory exists
            self.state_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file_path, "w", encoding="utf-8") as f:
                json.dump(state, f, cls=JsonDecimalEncoder, indent=4)
            self.logger.debug("Successfully saved state.")
        except Exception as e:
            self.logger.error(f"Could not save state: {e}", exc_info=True)

    @retry_api_call()
    async def _update_symbol_info(self):
        """Refreshes market information for all configured symbols."""
        self.logger.info("Refreshing symbol information from exchange...")
        try:
            await self.exchange.load_markets()
            markets_updated = 0
            for symbol, s_cfg in self.symbol_configs.items():
                market = self.exchange.markets.get(symbol)
                if market:
                    s_cfg.min_qty = (
                        Decimal(
                            str(market.get("limits", {}).get("amount", {}).get("min"))
                        )
                        if market.get("limits") and market["limits"].get("amount")
                        else None
                    )
                    s_cfg.qty_precision = (
                        int(market.get("precision", {}).get("amount"))
                        if market.get("precision")
                        else None
                    )
                    s_cfg.price_precision = (
                        int(market.get("precision", {}).get("price"))
                        if market.get("precision")
                        else None
                    )
                    s_cfg.tick_size = (
                        Decimal(str(market.get("precision", {}).get("price")))
                        if market.get("precision") and market["precision"].get("price")
                        else None
                    )
                    s_cfg.min_notional = (
                        Decimal(
                            str(market.get("limits", {}).get("cost", {}).get("min"))
                        )
                        if market.get("limits") and market["limits"].get("cost")
                        else None
                    )

                    self.logger.info(
                        f"Updated info for {symbol}: Min Qty {s_cfg.min_qty}, Qty Precision {s_cfg.qty_precision}, Price Precision {s_cfg.price_precision}, Tick Size {s_cfg.tick_size}, Min Notional {s_cfg.min_notional}"
                    )
                    markets_updated += 1
                else:
                    self.logger.warning(
                        f"Market information not found for symbol: {symbol}. Skipping updates."
                    )
            self.logger.info(
                f"Finished refreshing symbol info. {markets_updated}/{len(self.symbol_configs)} symbols updated."
            )
        except Exception as e:
            self.logger.error(f"Error updating symbol info: {e}", exc_info=True)

    async def _process_ws_messages(self):
        """Processes messages received from WebSocket in a loop."""
        while self.running:
            try:
                msg = await self.ws_message_queue.get()
                topic = msg.get("topic", "")

                if "orderbook" in topic:
                    symbol_from_topic = topic.split(".")[
                        -1
                    ]  # Extract symbol from topic like 'orderbook.50.BTCUSDT'
                    if symbol_from_topic not in self.symbol_configs:
                        continue  # Skip if we are not tracking this symbol

                    symbol_data = msg.get("data", {})
                    bids_raw = symbol_data.get("b", [])
                    asks_raw = symbol_data.get("a", [])

                    bids = [
                        OrderbookLevel(Decimal(p), Decimal(q))
                        for p, q in bids_raw
                        if p is not None and q is not None
                    ]
                    asks = [
                        OrderbookLevel(Decimal(p), Decimal(q))
                        for p, q in asks_raw
                        if p is not None and q is not None
                    ]

                    # Store the snapshot and update last data time
                    self.orderbooks[symbol_from_topic] = OrderbookSnapshot(
                        symbol_from_topic,
                        bids,
                        asks,
                        msg.get("ts", time.time() * 1000) / 1000.0,
                    )
                    self.last_market_data_time[symbol_from_topic] = time.time()

                elif "publicTrade" in topic:
                    # Public trades arrive as a list within 'data'
                    trades_data = msg.get("data", [])
                    if not trades_data:
                        continue  # Skip if no trade data

                    # Assuming all trades in a message are for the same symbol
                    symbol_from_topic = trades_data[0].get("s")
                    if symbol_from_topic not in self.symbol_configs:
                        continue  # Skip if we are not tracking this symbol

                    for trade in trades_data:
                        # Add trade to recent_trades deque for imbalance calculation
                        self.recent_trades[symbol_from_topic].append(
                            {
                                "amount": Decimal(
                                    str(trade.get("v", 0))
                                ),  # 'v' is volume/quantity
                                "side": "buy" if trade.get("S") == "Buy" else "sell",
                            }
                        )

            except asyncio.CancelledError:
                self.logger.debug("WebSocket message processing task cancelled.")
                break  # Exit loop if task is cancelled
            except Exception as e:
                self.logger.error(
                    f"Error processing WebSocket message: {e}", exc_info=True
                )
                # On major processing errors, might want to break to force reconnect
                # For now, just log and continue to potentially process next message.
                # If the loop encounters repeated errors, the outer connect() loop will handle reconnect.

    # region: Orderbook Analysis Methods
    def _get_vwap_for_symbol(self, symbol: str) -> Decimal | None:
        """Helper to get VWAP for a symbol, using the analyzer."""
        return self.orderbook_analyzer.calculate_vwap(symbol)

    def _get_book_imbalance_for_symbol(self, symbol: str) -> Decimal | None:
        """Helper to get book imbalance for a symbol."""
        return self.orderbook_analyzer.calculate_book_imbalance(symbol)

    def _analyze_liquidity_cliffs(self, symbol: str) -> tuple[bool, bool]:
        """Detects liquidity cliffs on bid and ask sides of the orderbook."""
        s_cfg = self.symbol_configs[symbol]
        snapshot = self.orderbooks.get(symbol)
        depth = s_cfg.orderbook_analysis.cliff_depth
        factor = Decimal(str(s_cfg.orderbook_analysis.cliff_factor))

        if not snapshot or len(snapshot.bids) < depth or len(snapshot.asks) < depth:
            return False, False

        try:
            top_bid_qty = snapshot.bids[0].quantity
            # Average quantity of bids from the second level up to `depth`
            next_bids_avg_qty = (
                sum(q.quantity for q in snapshot.bids[1:depth]) / (depth - 1)
                if depth > 1
                else snapshot.bids[1].quantity
            )

            # A cliff occurs if the top bid quantity is significantly smaller than average of subsequent bids
            is_bid_cliff = next_bids_avg_qty > DECIMAL_ZERO and (
                top_bid_qty / next_bids_avg_qty
            ) < (1 / factor)

            top_ask_qty = snapshot.asks[0].quantity
            next_asks_avg_qty = (
                sum(q.quantity for q in snapshot.asks[1:depth]) / (depth - 1)
                if depth > 1
                else snapshot.asks[1].quantity
            )

            # A cliff occurs if the top ask quantity is significantly smaller than average of subsequent asks
            is_ask_cliff = next_asks_avg_qty > DECIMAL_ZERO and (
                top_ask_qty / next_asks_avg_qty
            ) < (1 / factor)

            if is_bid_cliff:
                self.logger.debug(f"Liquidity cliff detected on BID side for {symbol}")
            if is_ask_cliff:
                self.logger.debug(f"Liquidity cliff detected on ASK side for {symbol}")
            return is_bid_cliff, is_ask_cliff
        except Exception as e:
            self.logger.error(
                f"Error analyzing liquidity cliffs for {symbol}: {e}", exc_info=True
            )
            return False, False

    def _detect_toxic_flow(self, symbol: str) -> tuple[bool, bool]:
        """Detects potential toxic flow by comparing consecutive orderbook snapshots."""
        is_toxic_on_bid, is_toxic_on_ask = False, False
        prev_ob, curr_ob = self.prev_orderbooks.get(symbol), self.orderbooks.get(symbol)

        # Need at least two snapshots to compare
        if not prev_ob or not curr_ob:
            self.prev_orderbooks[symbol] = (
                curr_ob  # Store current as previous for next iteration
            )
            return is_toxic_on_bid, is_toxic_on_ask

        try:
            # Toxic flow on bid side: best bid price decreased
            if curr_ob.bids[0].price < prev_ob.bids[0].price:
                is_toxic_on_bid = True
            # Toxic flow on ask side: best ask price increased
            if curr_ob.asks[0].price > prev_ob.asks[0].price:
                is_toxic_on_ask = True

            if is_toxic_on_bid:
                self.logger.warning(
                    f"Potential toxic flow detected on BID side for {symbol}"
                )
            if is_toxic_on_ask:
                self.logger.warning(
                    f"Potential toxic flow detected on ASK side for {symbol}"
                )

        except IndexError:  # Handle cases where snapshot might be empty
            self.logger.warning(
                f"Orderbook snapshot data insufficient for toxic flow detection for {symbol}"
            )
        except Exception as e:
            self.logger.error(
                f"Error detecting toxic flow for {symbol}: {e}", exc_info=True
            )

        self.prev_orderbooks[symbol] = curr_ob  # Update previous snapshot
        return is_toxic_on_bid, is_toxic_on_ask

    # endregion

    # region: Signal and Bias Calculation
    def _update_technical_signals(self, symbol: str):
        """Calculates technical indicators and stores them in self.signals."""
        s_cfg = self.symbol_configs[symbol]
        klines_df = self.kline_data.get(symbol)

        if klines_df is None or klines_df.empty:
            # Optionally log if kline data is missing
            # self.logger.debug(f"No kline data available for {symbol}. Skipping technical signal calculation.")
            return

        try:
            # RSI calculation
            if s_cfg.signal_config.use_rsi:
                # Ensure enough data points for RSI calculation
                if len(klines_df) >= s_cfg.signal_config.rsi_period:
                    self.signals[symbol]["rsi"] = calculate_rsi(
                        klines_df["close"], s_cfg.signal_config.rsi_period
                    ).iloc[-1]
                else:
                    self.signals[symbol]["rsi"] = None  # Not enough data

            # MACD calculation
            if s_cfg.signal_config.use_macd:
                # Ensure enough data points for MACD calculation
                required_macd_points = (
                    s_cfg.signal_config.macd_slow + s_cfg.signal_config.macd_signal
                )
                if len(klines_df) >= required_macd_points:
                    _, _, macd_hist = calculate_macd(
                        klines_df["close"],
                        s_cfg.signal_config.macd_fast,
                        s_cfg.signal_config.macd_slow,
                        s_cfg.signal_config.macd_signal,
                    )
                    self.signals[symbol]["macd_hist"] = macd_hist.iloc[-1]
                else:
                    self.signals[symbol]["macd_hist"] = None

            # Bollinger Bands calculation
            if s_cfg.dynamic_spread.use_bollinger_bands:
                bb_period = s_cfg.dynamic_spread.bb_period
                if len(klines_df) >= bb_period:
                    upper, middle, lower = calculate_bollinger_bands(
                        klines_df["close"], bb_period, s_cfg.dynamic_spread.bb_std_dev
                    )
                    self.signals[symbol]["bb_upper"] = upper.iloc[-1]
                    self.signals[symbol]["bb_middle"] = middle.iloc[-1]
                    self.signals[symbol]["bb_lower"] = lower.iloc[-1]
                else:
                    self.signals[symbol]["bb_upper"] = None
                    self.signals[symbol]["bb_middle"] = None
                    self.signals[symbol]["bb_lower"] = None

            # ATR calculation
            if (
                s_cfg.dynamic_spread.enabled
                and s_cfg.dynamic_spread.atr_update_interval > 0
            ):  # Check if enabled and has update interval
                # ATR uses a fixed period (e.g., 14) or configurable. Assume 14 here.
                if len(klines_df) >= 14:  # Assuming ATR period of 14
                    self.signals[symbol]["atr"] = calculate_atr(
                        klines_df["high"], klines_df["low"], klines_df["close"], 14
                    ).iloc[-1]
                else:
                    self.signals[symbol]["atr"] = None

            # VWAP calculation for volume profile signal
            if s_cfg.signal_config.use_volume_profile:
                vwap_period = s_cfg.signal_config.volume_lookback
                if len(klines_df) >= vwap_period:
                    self.signals[symbol]["vwap"] = calculate_vwap(
                        klines_df["close"], klines_df["volume"], vwap_period
                    ).iloc[-1]
                else:
                    self.signals[symbol]["vwap"] = None
        except Exception as e:
            self.logger.error(
                f"Error calculating technical signals for {symbol}: {e}", exc_info=True
            )

    def _get_directional_bias(self, symbol: str) -> TradingBias:
        """Determines the trading bias based on technical signals."""
        s_cfg = self.symbol_configs[symbol]
        signals = self.signals.get(symbol, {})
        score = 0

        try:
            # RSI Bias
            if (
                s_cfg.signal_config.use_rsi
                and "rsi" in signals
                and signals["rsi"] is not None
            ):
                rsi = signals["rsi"]
                if rsi < s_cfg.signal_config.rsi_oversold:
                    score += 1  # Bullish signal
                if rsi > s_cfg.signal_config.rsi_overbought:
                    score -= 1  # Bearish signal

            # MACD Histogram Bias
            if (
                s_cfg.signal_config.use_macd
                and "macd_hist" in signals
                and signals["macd_hist"] is not None
            ):
                if signals["macd_hist"] > DECIMAL_ZERO:
                    score += 1  # Bullish signal
                if signals["macd_hist"] < DECIMAL_ZERO:
                    score -= 1  # Bearish signal

        except Exception as e:
            self.logger.error(
                f"Error assessing directional bias for {symbol}: {e}", exc_info=True
            )
            return TradingBias.NEUTRAL  # Default to neutral on error

        # Map score to TradingBias enum
        if score >= 2:
            return TradingBias.STRONG_BULLISH
        if score == 1:
            return TradingBias.WEAK_BULLISH
        if score == -1:
            return TradingBias.WEAK_BEARISH
        if score <= -2:
            return TradingBias.STRONG_BEARISH
        return TradingBias.NEUTRAL

    # endregion

    # --- Leverage Management ---
    def _calculate_volatility(self, symbol: str) -> Decimal | None:
        """Calculates volatility metric based on configured source for dynamic leverage."""
        s_cfg = self.symbol_configs[symbol]
        vol_cfg = s_cfg.dynamic_leverage

        if not vol_cfg.enabled:
            return None

        source = vol_cfg.volatility_source

        try:
            if source == "atr":
                # Use pre-calculated ATR from signals
                return self.signals.get(symbol, {}).get("atr")

            elif source == "spread":
                snapshot = self.orderbooks.get(symbol)
                if (
                    snapshot
                    and snapshot.mid_price
                    and snapshot.mid_price > DECIMAL_ZERO
                ):
                    # Calculate spread as a ratio
                    return (
                        snapshot.asks[0].price - snapshot.bids[0].price
                    ) / snapshot.mid_price

            elif source == "bb_width":
                # Use Bollinger Band width (upper - lower) normalized by middle price
                bb_upper = self.signals.get(symbol, {}).get("bb_upper")
                bb_lower = self.signals.get(symbol, {}).get("bb_lower")
                mid = self.signals.get(symbol, {}).get("bb_middle")

                if bb_upper and bb_lower and mid and mid > DECIMAL_ZERO:
                    return (bb_upper - bb_lower) / mid
            else:
                self.logger.warning(
                    f"Unknown volatility source '{source}' configured for symbol {symbol}"
                )
                return None
        except Exception as e:
            self.logger.error(
                f"Error calculating volatility for {symbol} using source '{source}': {e}",
                exc_info=True,
            )
            return None
        return None

    def _calculate_target_leverage(self, symbol: str) -> Decimal:
        """Calculates the target leverage based on volatility, config, and current market data."""
        s_cfg = self.symbol_configs[symbol]
        vol_cfg = s_cfg.dynamic_leverage

        # If dynamic leverage is disabled, return default leverage from config
        if not vol_cfg.enabled:
            return Decimal(str(s_cfg.leverage))

        volatility = self._calculate_volatility(symbol)

        # If volatility cannot be determined, revert to base leverage
        if volatility is None:
            self.logger.debug(
                f"Volatility calculation failed or disabled for {symbol}. Reverting to base leverage."
            )
            return Decimal(str(s_cfg.leverage))

        # --- Leverage Calculation Logic ---
        # Goal: Lower volatility -> higher leverage; Higher volatility -> lower leverage.
        # Use linear interpolation between min_leverage and max_leverage based on normalized volatility.

        min_vol_benchmark = Decimal("0.0001")  # Volatility value considered "low"
        max_vol_benchmark = Decimal("0.01")  # Volatility value considered "high"

        # Use the configured benchmark volatility
        benchmark_vol = vol_cfg.benchmark_volatility
        if benchmark_vol <= DECIMAL_ZERO:
            benchmark_vol = Decimal("0.00001")  # Prevent division by zero

        # Normalize volatility value to a 0-1 scale based on benchmarks
        # Clamp volatility to the range [min_vol_benchmark, max_vol_benchmark] first
        clamped_volatility = max(min_vol_benchmark, min(volatility, max_vol_benchmark))

        # Calculate the normalized volatility within the defined range
        # If volatility is below min_vol_benchmark, normalized_volatility_0_1 will be 0.
        # If volatility is above max_vol_benchmark, normalized_volatility_0_1 will be 1.
        # Otherwise, it's interpolated linearly.
        normalized_volatility_0_1 = (clamped_volatility - min_vol_benchmark) / (
            max_vol_benchmark - min_vol_benchmark
        )

        # Apply the volatility range factor to control how much of the leverage range is affected
        # This factor scales the impact of volatility. A factor of 1 uses the full range.
        # A factor of 0.2 means only 20% of the min/max leverage range is influenced by volatility.
        effective_vol_scale = min(
            Decimal("1.0"), normalized_volatility_0_1 * vol_cfg.volatility_range_factor
        )

        # Interpolate leverage:
        # If effective_vol_scale is 0 (low volatility), target leverage should be max_leverage.
        # If effective_vol_scale is 1 (high volatility), target leverage should be min_leverage.
        # Leverage = MaxLeverage * (1 - effective_vol_scale) + MinLeverage * effective_vol_scale

        target_leverage = (
            vol_cfg.max_leverage * (1 - effective_vol_scale)
            + vol_cfg.min_leverage * effective_vol_scale
        )

        # Ensure the calculated target leverage is clamped within the configured min/max leverage limits.
        target_leverage = max(
            vol_cfg.min_leverage, min(target_leverage, vol_cfg.max_leverage)
        )

        return target_leverage

    async def _adjust_leverage_if_needed(self, symbol: str):
        """Checks if leverage needs adjustment based on config and market conditions, and calls exchange.set_leverage if necessary."""
        s_cfg = self.symbol_configs[symbol]
        vol_cfg = s_cfg.dynamic_leverage

        # Skip if dynamic leverage is disabled or update interval is zero
        if not vol_cfg.enabled or vol_cfg.leverage_update_interval == 0:
            # Ensure current tracked leverage matches config default if dynamic is off
            if symbol in self.exchange_leverage_set and self.exchange_leverage_set[
                symbol
            ] != Decimal(str(s_cfg.leverage)):
                self.logger.debug(
                    f"Dynamic leverage disabled for {symbol}, resetting leverage to config default: {s_cfg.leverage}x"
                )
                # Update internal tracking if it differs. Actual reset via exchange.set_leverage would be needed if desired.
                self.metrics["current_symbol_leverage"][symbol] = Decimal(
                    str(s_cfg.leverage)
                )
                self.exchange_leverage_set[symbol] = Decimal(str(s_cfg.leverage))
            return

        # Check if it's time to re-evaluate leverage based on interval
        last_update_time = self.metrics.get("last_leverage_update_time", {}).get(
            symbol, 0.0
        )
        if time.time() - last_update_time < vol_cfg.leverage_update_interval:
            return  # Not enough time passed since last evaluation

        # Ensure kline data is sufficiently fresh for volatility calculation
        last_kline_update_time = self.metrics.get("last_fetch_kline_time", {}).get(
            symbol, 0.0
        )
        # Fetch klines if they are older than, say, 10 minutes (600 seconds)
        if time.time() - last_kline_update_time > 600:
            self.logger.debug(
                f"Kline data for {symbol} is old ({time.time() - last_kline_update_time:.0f}s ago). Fetching fresh data for leverage calculation."
            )
            # Call _fetch_data which will update kline data and last_fetch_kline_time
            await self._fetch_data()

        # Calculate the target leverage based on current market conditions
        target_leverage = self._calculate_target_leverage(symbol)

        # Get the leverage currently set on the exchange for this symbol
        current_set_leverage = self.exchange_leverage_set.get(
            symbol, Decimal(str(s_cfg.leverage))
        )  # Default to config if not yet tracked

        # Define the threshold for making an API call (e.g., 5% change)
        threshold_pct = Decimal(str(vol_cfg.leverage_adjustment_threshold_pct))

        # Check if the target leverage differs significantly from the currently set leverage
        if (
            abs(target_leverage - current_set_leverage)
            >= threshold_pct * current_set_leverage
        ):
            self.logger.info(
                f"Leverage adjustment needed for {symbol}: Current={current_set_leverage:.2f}x, Target={target_leverage:.2f}x (Threshold: {threshold_pct * 100:.1f}%)"
            )

            # Call exchange.set_leverage. CCXT might require integer for some exchanges, but Bybit v5 uses float.
            # Ensure target_leverage is compatible with exchange API.
            try:
                adjust_start_time = time.time()
                # Bybit API v5 expects leverage as a string or float. Passing as float.
                await self.exchange.set_leverage(target_leverage, symbol)

                # Update internal tracking
                self.exchange_leverage_set[symbol] = target_leverage
                self.metrics["current_symbol_leverage"][symbol] = (
                    target_leverage  # Update tracked leverage
                )
                self.metrics["last_leverage_update_time"][symbol] = time.time()
                self.metrics["op_time_leverage_adjust"] = (
                    time.time() - adjust_start_time
                )

                self.logger.info(
                    f"Successfully set leverage for {symbol} to {target_leverage:.2f}x"
                )
                # Notify via Telegram
                await self.notifier.send_message(
                    f"📈 Leverage adjusted for {symbol} to **{target_leverage:.2f}x**"
                )

            except Exception as e:
                self.logger.error(
                    f"Failed to set leverage for {symbol} to {target_leverage:.2f}x: {e}",
                    exc_info=True,
                )
                # Update metrics even on failure to reflect the attempt and time
                self.metrics["op_time_leverage_adjust"] = (
                    time.time() - adjust_start_time
                )
                # Do not update tracked leverage if the call failed
        else:
            # If no adjustment was needed, still update the tracked leverage and time for consistency
            # This ensures that if config changes, the system eventually reflects it.
            self.metrics["current_symbol_leverage"][symbol] = target_leverage
            self.metrics["last_leverage_update_time"][symbol] = time.time()
            self.logger.debug(
                f"Leverage for {symbol} ({current_set_leverage:.2f}x) is within target ({target_leverage:.2f}x) and threshold. No adjustment made."
            )

    # --- PnL and Trade History Placeholder ---
    def _process_executed_trades(self, symbol: str, placed_orders_results: list[dict]):
        """
        Processes executed orders (fills) to update PnL, trade history, and metrics.
        This is a placeholder for a more robust trade reconciliation system.
        It focuses on updating metrics related to fills.
        """
        if not placed_orders_results:
            return

        filled_legs_count = 0
        for order_result in placed_orders_results:
            # CCXT order results usually have 'status', 'filled', 'avg_price', 'fee', 'side', 'symbol'
            # Check if the order was closed or had a filled amount
            if order_result and (
                order_result.get("status") == "closed"
                or order_result.get("filled", 0) > 0
            ):
                # This indicates at least a partial fill
                filled_legs_count += 1

                # --- Placeholder for PnL Calculation and Trade History Update ---
                # A real implementation would:
                # 1. Extract filled_qty, avg_price, fee, side, symbol.
                # 2. Match this fill against open positions or prior legs to calculate PnL.
                # 3. Create a `Trade` object if a complete leg or round-trip is recognized.
                # 4. Update `self.total_pnl`, `self.daily_pnl`, and `self.trade_history`.

                # For now, we only increment the metric for filled legs.
                # self.logger.debug(f"Processed fill for {symbol}: {order_result.get('side')} {order_result.get('filled')}@{order_result.get('avg_price')}")
                # No PnL updates for now.

        self.metrics["trades_filled_total"] += filled_legs_count
        # Note: total_pnl and daily_pnl are NOT updated here as PnL calculation is complex.
        # They are loaded from state and saved, but not updated dynamically in this version.
        # This is a known limitation and an area for future improvement.

    # --- Main Strategy Update Logic ---
    async def _update_status_for_symbol(self, symbol: str):
        """
        Main loop function for updating a single symbol's market maker strategy.
        Includes leverage adjustment, quote calculation, order placement, and metrics.
        """
        s_cfg = self.symbol_configs[symbol]

        # --- 1. Leverage Adjustment ---
        if s_cfg.dynamic_leverage.enabled:
            await self._adjust_leverage_if_needed(symbol)

        # --- 2. Pre-checks: Halting, Stale Data ---
        # Stop processing if trading is halted globally or for this symbol
        if self.trading_halted or not s_cfg.trade_enabled:
            # Cancel any open orders if the symbol is disabled or trading is halted
            if self.open_orders.get(symbol):
                cancel_start_time = time.time()
                try:
                    await self.exchange.cancel_all_orders(symbol)
                    self.logger.info(
                        f"Trading halted or disabled for {symbol}. Cancelled {len(self.open_orders[symbol])} open orders."
                    )
                    self.metrics["orders_cancelled_total"] += len(
                        self.open_orders[symbol]
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed to cancel orders for {symbol} during halt/disable: {e}"
                    )
                finally:
                    self.open_orders[symbol] = []  # Clear list
                    self.metrics["op_time_order_cancellation"] = (
                        time.time() - cancel_start_time
                    )
            return  # Skip further processing for this symbol

        # Check if market data is stale
        last_market_data_time = self.last_market_data_time.get(symbol, 0.0)
        if (
            time.time() - last_market_data_time
            > s_cfg.market_data_stale_timeout_seconds
        ):
            self.logger.warning(
                f"Market data for {symbol} is stale (last updated > {s_cfg.market_data_stale_timeout_seconds}s ago). Skipping quote update."
            )
            # Optionally cancel orders here if they might be based on stale data
            # if self.open_orders.get(symbol): await self.exchange.cancel_all_orders(symbol)
            return  # Skip quote generation

        # --- 3. Calculate Quotes ---
        quote_start_time = time.time()

        # Update technical signals based on latest kline data
        self._update_technical_signals(symbol)
        # Calculate the desired orders (quotes)
        quotes = await self._calculate_quotes(symbol)

        # Record time taken for quote calculation
        self.metrics["op_time_quote_calc"] = time.time() - quote_start_time

        # --- 4. Manage Open Orders ---
        open_orders_for_symbol = self.open_orders.get(symbol, [])

        # Cancel existing orders before placing new ones
        if open_orders_for_symbol:
            cancel_start_time = time.time()
            try:
                await self.exchange.cancel_all_orders(symbol)
                self.logger.debug(
                    f"Cancelled {len(open_orders_for_symbol)} existing orders for {symbol} to refresh quotes."
                )
                self.metrics["orders_cancelled_total"] += len(open_orders_for_symbol)
            except Exception as e:
                self.logger.error(f"Failed to cancel orders for {symbol}: {e}")
            finally:
                self.open_orders[
                    symbol
                ] = []  # Clear the list after cancellation attempt
                self.metrics["op_time_order_cancellation"] = (
                    time.time() - cancel_start_time
                )

        # --- 5. Place New Orders ---
        orders_to_place = []
        # Filter quotes and prepare them for CCXT
        for quote in quotes:
            # Ensure quantity is valid and not zero
            if quote.get("qty", DECIMAL_ZERO) > DECIMAL_ZERO:
                # Check against minimum notional value if configured
                min_notional = s_cfg.min_notional
                if (
                    min_notional is not None
                    and quote["price"] * quote["qty"] < min_notional
                ):
                    self.logger.warning(
                        f"Skipping order for {symbol}: Notional value ({quote['price'] * quote['qty']:.4f}) is below minimum notional ({min_notional:.4f})."
                    )
                    continue

                # Prepare order parameters for CCXT
                orders_to_place.append(
                    {
                        "symbol": symbol,
                        "type": "limit",  # Always limit orders for market making
                        "side": quote["side"],
                        "amount": float(
                            quote["qty"]
                        ),  # CCXT often expects float for amount/price
                        "price": float(quote["price"]),
                    }
                )

        # If there are valid orders to place
        if orders_to_place:
            self.logger.info(
                f"Placing {len(orders_to_place)} orders for {symbol}: {[f'{o["side"]} {o["amount"]}@{o["price"]}' for o in orders_to_place]}"
            )
            placement_start_time = time.time()

            try:
                placed_orders_results = []  # To store results from exchange

                # Use batch orders if enabled and multiple orders are to be placed
                if s_cfg.use_batch_orders_for_refresh and len(orders_to_place) > 1:
                    placed_orders_results = await self.exchange.create_orders(
                        orders_to_place
                    )
                else:  # Place orders one by one if batching is off or only one order
                    for order_params in orders_to_place:
                        placed_order = await self.exchange.create_order(**order_params)
                        placed_orders_results.append(placed_order)

                # --- Process Results ---
                successfully_placed_count = 0
                open_orders_for_processing = []  # List to hold orders that are still open

                # Iterate through the results from the exchange
                for order_result in placed_orders_results:
                    if order_result:  # Ensure the result is valid
                        # Check if the order was successfully placed and is still open or partially filled
                        if order_result.get("status") != "closed":
                            successfully_placed_count += 1
                            open_orders_for_processing.append(
                                order_result
                            )  # Store open/partially filled orders

                        # Update total orders placed metric
                        self.metrics["orders_placed_total"] += 1
                    else:
                        self.logger.warning(
                            f"Received empty or invalid order result for {symbol} placement."
                        )

                # Update the self.open_orders for this symbol with the currently open/partially filled orders
                self.open_orders[symbol] = open_orders_for_processing

                # --- Placeholder for processing executed trades ---
                # Call the placeholder method to update metrics related to fills.
                self._process_executed_trades(symbol, placed_orders_results)
                # --- End Placeholder ---

            except Exception as e:
                self.logger.error(
                    f"Failed to place orders for {symbol}: {e}", exc_info=True
                )
                # If order placement fails, clear the open orders list for this symbol
                self.open_orders[symbol] = []
            finally:
                # Record time taken for order placement operation
                self.metrics["op_time_order_placement"] = (
                    time.time() - placement_start_time
                )
        # else:
        #     self.logger.debug(f"No valid quotes generated for {symbol} this cycle. No orders to place.")

    # --- Dashboard Display ---
    async def _print_status_dashboard(self):
        """Displays real-time status and metrics in the console."""
        while self.running:
            try:
                # Clear console for a cleaner dashboard view
                os.system("cls" if os.name == "nt" else "clear")

                # --- Header ---
                print(
                    f"{Style.BRIGHT}{Fore.CYAN}--- Hybrid Market Maker Status Dashboard ---{Style.RESET_ALL}"
                )
                print(
                    f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
                print(f"Trading Halted: {'YES' if self.trading_halted else 'NO'}")
                print(f"Account Balance: {self.account_balance:.2f} USDT")

                # --- Performance Metrics ---
                print(f"\n{Style.BRIGHT}{Fore.YELLOW}Performance:{Style.RESET_ALL}")
                print(f"  Daily PnL: {self.daily_pnl:.4f} USDT")
                print(f"  Total PnL: {self.total_pnl:.4f} USDT")

                # --- General Bot Metrics ---
                print(f"\n{Style.BRIGHT}{Fore.CYAN}Bot Metrics:{Style.RESET_ALL}")
                print(
                    f"  Total Orders Placed: {self.metrics.get('orders_placed_total', 0)}"
                )
                print(
                    f"  Total Orders Cancelled: {self.metrics.get('orders_cancelled_total', 0)}"
                )
                print(
                    f"  Total Filled Legs: {self.metrics.get('trades_filled_total', 0)}"
                )
                print(
                    f"  Quote Calc Time: {self.metrics.get('op_time_quote_calc', 0.0):.4f}s"
                )
                print(
                    f"  Order Placement Time: {self.metrics.get('op_time_order_placement', 0.0):.4f}s"
                )
                print(
                    f"  Order Cancellation Time: {self.metrics.get('op_time_order_cancellation', 0.0):.4f}s"
                )
                print(
                    f"  Leverage Adjustment Time: {self.metrics.get('op_time_leverage_adjust', 0.0):.4f}s"
                )

                # --- Per-Symbol Details ---
                for symbol in self.symbol_configs:
                    print(
                        f"\n{Style.BRIGHT}{Fore.GREEN}--- {symbol} ---{Style.RESET_ALL}"
                    )
                    snapshot = self.orderbooks.get(symbol)
                    pos = self.positions.get(symbol, DECIMAL_ZERO)
                    open_ord_count = len(self.open_orders.get(symbol, []))

                    # Display Leverage
                    current_leverage_val = self.metrics.get(
                        "current_symbol_leverage", {}
                    ).get(symbol, "N/A")
                    print(f"  Leverage: {current_leverage_val}x")

                    # Display market data if available
                    if snapshot and snapshot.mid_price:
                        book_imb = self.orderbook_analyzer.calculate_book_imbalance(
                            symbol
                        )
                        trade_imb = self.orderbook_analyzer.calculate_trade_imbalance(
                            self.recent_trades[symbol]
                        )
                        vwap_val = self.orderbook_analyzer.calculate_vwap(symbol)

                        print(f"  Mid Price: {snapshot.mid_price:.4f}")
                        print(f"  VWAP: {vwap_val:.4f}" if vwap_val else "  VWAP: N/A")
                        print(
                            f"  Book Imbalance: {book_imb:.3f}"
                            if book_imb is not None
                            else "  Book Imbalance: N/A"
                        )
                        print(
                            f"  Trade Imbalance: {trade_imb:.3f}"
                            if trade_imb is not None
                            else "  Trade Imbalance: N/A"
                        )
                        print(f"  Position: {pos:.4f}")
                        print(f"  Open Orders: {open_ord_count}")
                    else:
                        print(
                            "  Market Data: Not available (check WS connection or symbol config)"
                        )

            except Exception as e:
                self.logger.error(f"Error printing dashboard: {e}", exc_info=True)

            # Wait for the next dashboard update interval
            await asyncio.sleep(STATUS_UPDATE_INTERVAL)

    # --- Utility Methods for Price/Quantity Rounding ---
    def round_price(self, symbol: str, price: Decimal) -> Decimal:
        """Rounds price to the correct precision for the given symbol."""
        s_cfg = self.symbol_configs.get(symbol)
        if not s_cfg or s_cfg.tick_size is None:
            self.logger.warning(
                f"Tick size not available for {symbol}. Cannot round price."
            )
            return price

        try:
            # Use ROUND_HALF_UP for standard rounding
            rounded_price = (price / s_cfg.tick_size).quantize(
                DECIMAL_ZERO, rounding=ROUND_HALF_UP
            ) * s_cfg.tick_size
            return rounded_price
        except Exception as e:
            self.logger.error(
                f"Error rounding price {price} for {symbol} with tick size {s_cfg.tick_size}: {e}",
                exc_info=True,
            )
            return price  # Return original price on error

    def round_quantity(self, symbol: str, quantity: Decimal) -> Decimal:
        """Rounds quantity to the correct precision for the given symbol."""
        s_cfg = self.symbol_configs.get(symbol)
        if not s_cfg or s_cfg.qty_precision is None:
            self.logger.warning(
                f"Quantity precision not available for {symbol}. Cannot round quantity."
            )
            return quantity

        try:
            # Calculate the factor for rounding based on precision (e.g., 10^-precision)
            precision_factor = Decimal(str(10**-s_cfg.qty_precision))
            # Round down to the nearest tick
            rounded_quantity = quantity.quantize(precision_factor, rounding=ROUND_DOWN)
            return rounded_quantity
        except Exception as e:
            self.logger.error(
                f"Error rounding quantity {quantity} for {symbol} with precision {s_cfg.qty_precision}: {e}",
                exc_info=True,
            )
            return quantity  # Return original quantity on error

    # --- Main Bot Execution Loop ---
    async def run(self):
        """Starts the main bot execution loop."""
        self._setup_signal_handler()
        self.logger.info("Starting Hybrid Market Maker Bot v3.0 with Enhancements...")
        await self.notifier.send_message(
            "🚀 Hybrid Market Maker Bot v3.0 (Enhanced) Started"
        )

        # Load initial state and configuration
        await self._load_state()
        await self._update_symbol_info()  # Fetch market details
        await self._update_symbol_leverage_config()  # Initialize leverage tracking

        # Start background tasks
        # WebSocket client task
        ws_task = asyncio.create_task(self.ws_client.connect())
        # WebSocket message processing task
        ws_processor_task = asyncio.create_task(self._process_ws_messages())
        # Status dashboard task
        dashboard_task = asyncio.create_task(self._print_status_dashboard())

        self.logger.info(
            "Waiting 10 seconds for initial data and WebSocket connection..."
        )
        await asyncio.sleep(10)

        # Initialize timers for periodic tasks
        last_data_fetch_time = 0.0
        last_symbol_info_update_time = time.time()

        try:
            # Main execution loop
            while self.running:
                current_time = time.time()

                # --- Periodic Data Fetch and Risk Checks ---
                # Fetch core data (balance, positions, open orders, klines) periodically
                if current_time - last_data_fetch_time > STATUS_UPDATE_INTERVAL:
                    self.logger.debug("Fetching core data and checking risk limits...")
                    await self._fetch_data()
                    await self._check_risk_limits()
                    last_data_fetch_time = current_time

                # --- Per-Symbol Updates ---
                # Process each symbol concurrently
                symbol_update_tasks = [
                    self._update_status_for_symbol(s) for s in self.symbol_configs
                ]
                await asyncio.gather(*symbol_update_tasks)

                # --- Periodic Symbol Info Refresh ---
                # Refresh symbol information (e.g., if exchange adds new symbols or changes limits)
                if (
                    current_time - last_symbol_info_update_time
                    > SYMBOL_INFO_REFRESH_INTERVAL
                ):
                    self.logger.info("Refreshing symbol information periodically...")
                    await self._update_symbol_info()
                    last_symbol_info_update_time = current_time

                # --- Periodic State Saving ---
                # Save bot state to disk to ensure continuity
                await self._save_state()

                # --- Main Loop Delay ---
                # Sleep for a short interval to prevent busy-waiting and control loop frequency
                await asyncio.sleep(MAIN_LOOP_SLEEP_INTERVAL)

        except KeyboardInterrupt:
            self.logger.info("Shutdown signal received (KeyboardInterrupt).")
        except Exception as e:
            self.logger.critical(
                f"An unhandled error occurred in the main loop: {e}", exc_info=True
            )
            await self.notifier.send_message(f"❌ Bot encountered critical error: {e}")
        finally:
            # Perform cleanup operations before exiting
            await self._cleanup()

    # --- Cleanup Operations ---
    async def _cleanup(self):
        """Performs necessary cleanup operations before bot exits."""
        self.logger.info("Performing cleanup operations...")
        self.running = False  # Signal all running tasks to stop

        # --- Close WebSocket Connection ---
        if self.ws_client:
            await self.ws_client.close()

        # --- Cancel Background Tasks ---
        # Cancel tasks gracefully if they are still running
        tasks_to_cancel = []
        # Check if tasks were defined before attempting to cancel
        if "ws_task" in locals() and ws_task and not ws_task.done():
            tasks_to_cancel.append(ws_task)
        if (
            "ws_processor_task" in locals()
            and ws_processor_task
            and not ws_processor_task.done()
        ):
            tasks_to_cancel.append(ws_processor_task)
        if (
            "dashboard_task" in locals()
            and dashboard_task
            and not dashboard_task.done()
        ):
            tasks_to_cancel.append(dashboard_task)

        if tasks_to_cancel:
            for task in tasks_to_cancel:
                task.cancel()
            try:
                await asyncio.gather(
                    *tasks_to_cancel, return_exceptions=True
                )  # Wait for tasks to finish cancellation
            except Exception as e:
                self.logger.error(f"Error during task cancellation: {e}")

        # --- Cancel All Open Orders on Exchange ---
        for symbol in self.symbol_configs:
            try:
                if self.open_orders.get(symbol):  # Check if there are orders to cancel
                    self.logger.info(
                        f"Cancelling all open orders for {symbol} during cleanup..."
                    )
                    await self.exchange.cancel_all_orders(symbol)
                    self.metrics["orders_cancelled_total"] += len(
                        self.open_orders.get(symbol, [])
                    )  # Update metrics
                    self.open_orders[symbol] = []  # Clear local tracking
            except Exception as e:
                self.logger.error(
                    f"Error cancelling orders for {symbol} during cleanup: {e}"
                )

        # --- Close Exchange Connection ---
        if self.exchange:
            await self.exchange.close()
            self.logger.info("Exchange connection closed.")

        # --- Close aiohttp Session ---
        if self.aiohttp_session:
            try:
                await self.aiohttp_session.close()
                self.logger.info("aiohttp session closed.")
            except Exception as e:
                self.logger.error(f"Error closing aiohttp session: {e}")

        # --- Save Final State ---
        await self._save_state()

        self.logger.info("Bot has been shut down gracefully.")
        await self.notifier.send_message(
            "🛑 Hybrid Market Maker Bot v3.0 (Enhanced) Stopped"
        )


# endregion


# region: Main Execution Block
# ==============================================================================
async def main():
    parser = argparse.ArgumentParser(
        description="Hybrid Bybit Market Maker Bot v3.0 - Enhanced"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        help="Run the bot for a single symbol (e.g., BTC), ignoring the symbols.json config file.",
    )
    args = parser.parse_args()

    # Load configuration first
    global GLOBAL_CONFIG, SYMBOL_CONFIGS
    GLOBAL_CONFIG, SYMBOL_CONFIGS = await ConfigManager.load_config(
        prompt_for_symbol=bool(args.symbol), input_symbol=args.symbol
    )

    # Initialize main logger after config is loaded
    global main_logger
    main_logger = setup_logger("main")

    # Validate configuration
    if not SYMBOL_CONFIGS:
        main_logger.critical(
            "No symbols configured. Please add symbols to your symbols.json or use the --symbol flag. Exiting."
        )
        sys.exit(1)

    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        main_logger.critical(
            "BYBIT_API_KEY and BYBIT_API_SECRET environment variables must be set. Exiting."
        )
        sys.exit(1)

    # Initialize exchange and aiohttp session
    exchange_instance, aiohttp_session_instance = await initialize_exchange(main_logger)
    if not exchange_instance or not aiohttp_session_instance:
        main_logger.critical(
            "Exchange or aiohttp session initialization failed. Exiting."
        )
        sys.exit(1)

    # Create and run the strategy
    strategy = EnhancedMarketMakerStrategy(
        GLOBAL_CONFIG, SYMBOL_CONFIGS, exchange_instance, aiohttp_session_instance
    )
    await strategy.run()


if __name__ == "__main__":
    if not EXTERNAL_LIBS_AVAILABLE:
        sys.exit(1)
    # Run the main async function
    asyncio.run(main())
