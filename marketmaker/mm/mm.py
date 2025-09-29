# Note: UserWarning: pkg_resources is deprecated as an API. This is likely from a dependency.
# Consider pinning setuptools<81 or upgrading dependencies to resolve this.
import asyncio
import json
import logging
import os
import signal  # Import the signal module for graceful shutdown
import subprocess
import sys
import threading
import time
from asyncio import Lock  # For asynchronous locking
from collections import deque  # For storing recent trades/prices
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timezone  # Import dt_time for trading hours
from decimal import ROUND_DOWN, Decimal, InvalidOperation, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

# --- External Libraries ---
try:
    import numpy as np  # For dry run price simulation
    import pandas as pd
    import websocket  # For WebSocket._exceptions.WebSocketConnectionClosedException
    from colorama import Fore, Style, init
    from dotenv import load_dotenv  # For loading environment variables
    from pybit.unified_trading import HTTP, WebSocket
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

    # pandas_ta for ATR calculation
    try:
        import pandas_ta as ta
    except ImportError:
        print(
            f"{Fore.YELLOW}Warning: 'pandas_ta' not found. ATR calculation will use a basic rolling mean.{Style.RESET_ALL}"
        )
        ta = None  # Set to None if not available

    # Async file and DB operations
    import aiofiles
    import aiosqlite

    # Tenacity for retry logic
    from tenacity import (
        before_sleep_log,
        retry,
        retry_if_exception,
        stop_after_attempt,
        wait_exponential_jitter,
    )

    EXTERNAL_LIBS_AVAILABLE = True
except ImportError as e:
    # Provide a clear message if essential libraries are missing
    print(
        f"{Fore.RED}Error: Missing required library: {e}. Please install it using pip.{Style.RESET_ALL}"
    )
    print(
        f"{Fore.YELLOW}Install all dependencies with: pip install numpy pandas websocket-client pydantic colorama python-dotenv aiofiles aiosqlite pybit tenacity pandas_ta{Style.RESET_ALL}"
    )
    EXTERNAL_LIBS_AVAILABLE = False

    # Define dummy classes/functions to allow the script to load without immediate crashes,
    # but operations requiring these libraries will fail.
    class DummyModel:
        pass

    class BaseModel(DummyModel):
        pass

    class ConfigDict(dict):
        pass

    class Field(DummyModel):
        pass

    class ValidationError(Exception):
        pass

    class Decimal:
        pass

    class pd:
        DataFrame = object  # Dummy DataFrame

    class np:
        @staticmethod
        def exp(*args, **kwargs):
            return 1.0

        @staticmethod
        def sqrt(*args, **kwargs):
            return 1.0

        @staticmethod
        def random():
            class Random:
                @staticmethod
                def normal(*args, **kwargs):
                    return 0.0

            return Random()

    class websocket:
        pass

    class Fore:
        CYAN = MAGENTA = YELLOW = GREEN = BLUE = RED = LIGHTRED_EX = RESET = ""

    class Style:
        BRIGHT = RESET_ALL = ""

    class RotatingFileHandler:
        pass

    class subprocess:
        pass

    class threading:
        pass

    class time:
        pass

    class signal:
        pass

    class datetime:
        pass

    class timezone:
        pass

    class Path:
        pass

    class Optional:
        pass

    class Callable:
        pass

    class Dict:
        pass

    class List:
        pass

    class Tuple:
        pass

    class Union:
        pass

    class Any:
        pass

    class deque:
        pass

    class Coroutine:
        pass

    class aiofiles:
        @staticmethod
        async def open(*args, **kwargs):
            return DummyModel()

    class aiosqlite:
        @staticmethod
        async def connect(*args, **kwargs):
            return DummyModel()

        @staticmethod
        async def Row(*args, **kwargs):
            return DummyModel()

    class HTTP:
        pass

    class WebSocket:
        pass

    def retry(*args, **kwargs):
        return lambda f: f

    def stop_after_attempt(*args, **kwargs):
        return DummyModel()

    def wait_exponential_jitter(*args, **kwargs):
        return DummyModel()

    def retry_if_exception(*args, **kwargs):
        return DummyModel()

    def before_sleep_log(*args, **kwargs):
        return DummyModel()

    ta = None  # Ensure ta is None if pandas_ta import fails
    load_dotenv = lambda: None  # Dummy function

# Initialize Colorama for cross-platform colored terminal output
init(autoreset=True)

# Load environment variables from .env file
load_dotenv()

# --- Global Constants and Configuration Paths ---
# Decimal precision for all financial calculations
getcontext().prec = 38
DECIMAL_ZERO: Decimal = Decimal("0")

# Termux-aware paths for logs and state files
BASE_DIR = Path(os.getenv("HOME", "."))
LOG_DIR: Path = BASE_DIR / "bot_logs"
STATE_DIR: Path = BASE_DIR / ".bot_state"
LOG_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)


# --- Custom Exceptions ---
class ConfigurationError(Exception):
    pass


class APIAuthError(Exception):
    pass


class WebSocketConnectionError(Exception):
    pass


class MarketInfoError(Exception):
    pass


class InitialBalanceError(Exception):
    pass


class OrderPlacementError(Exception):
    pass


class BybitAPIError(Exception):
    """Custom exception for Bybit API errors, includes Bybit's error code and message."""

    def __init__(self, message: str, ret_code: int = -1, ret_msg: str = "Unknown"):
        super().__init__(message)
        self.ret_code = ret_code
        self.ret_msg = ret_msg


class BybitRateLimitError(BybitAPIError):
    """Raised when a Bybit API rate limit is exceeded."""


class BybitInsufficientBalanceError(BybitAPIError):
    """Raised when an API operation fails due to insufficient balance."""


# --- Utility Functions ---
class Colors:
    """ANSI escape codes for enchanted terminal output with a neon theme."""

    CYAN = Fore.CYAN + Style.BRIGHT
    MAGENTA = Fore.MAGENTA + Style.BRIGHT
    YELLOW = Fore.YELLOW + Style.BRIGHT
    RESET = Style.RESET_ALL
    NEON_GREEN = Fore.GREEN + Style.BRIGHT
    NEON_BLUE = Fore.BLUE + Style.BRIGHT
    NEON_RED = Fore.RED + Style.BRIGHT
    NEON_ORANGE = Fore.LIGHTRED_EX + Style.BRIGHT


def termux_notify(
    message: str, title: str = "Market Maker Bot", is_error: bool = False
) -> None:
    """Sends a notification via Termux:API if available."""
    try:
        # Check if termux-api is installed and accessible
        subprocess.run(
            ["termux-notification", "-h"], check=True, capture_output=True, timeout=2
        )

        # Construct the command
        cmd = ["termux-notification", "--title", title, "--content", message]
        if is_error:
            cmd.extend(["--priority", "max", "--sound", "default"])

        subprocess.run(cmd, check=False, capture_output=True, timeout=5)
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
        PermissionError,
    ):
        # Fallback to print if termux-api is not available or fails
        logging.getLogger("BybitMarketMaker").warning(
            f"[NOTIFICATION FAILED] {title}: {message}"
        )
    except Exception as e:
        logging.getLogger("BybitMarketMaker").warning(
            f"Unexpected error with Termux notification: {e}"
        )


class JsonDecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle Decimal objects."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def atr(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14
) -> pd.Series:
    """Calculates Average True Range (ATR)."""
    tr = pd.DataFrame()
    tr["h_l"] = high - low
    tr["h_pc"] = (high - close.shift(1)).abs()
    tr["l_pc"] = (low - close.shift(1)).abs()
    tr["tr"] = tr[["h_l", "h_pc", "l_pc"]].max(axis=1)
    return (
        tr["tr"].dropna().ewm(span=length, adjust=False).mean()
    )  # Using EWM for standard ATR calculation


# --- Pydantic Models for Configuration and State ---
class DynamicSpreadConfig(BaseModel):
    """Configuration for dynamic spread adjustment based on volatility (e.g., ATR)."""

    enabled: bool = True
    volatility_window_sec: PositiveInt = (
        60  # Window for price change to calculate volatility
    )
    volatility_multiplier: PositiveFloat = (
        2.0  # Multiplier for volatility to adjust spread
    )
    min_spread_pct: PositiveFloat = (
        0.0005  # Minimum allowed dynamic spread (e.g., 0.05%)
    )
    max_spread_pct: PositiveFloat = 0.01  # Maximum allowed dynamic spread (e.g., 1%)
    price_change_smoothing_factor: PositiveFloat = 0.2  # Alpha for EMA of mid-price
    atr_update_interval_sec: PositiveInt = 300  # How often to re-calculate ATR


class InventorySkewConfig(BaseModel):
    """Configuration for skewing orders based on current inventory."""

    enabled: bool = True
    skew_intensity: PositiveFloat = 0.5  # How strongly inventory affects spread
    max_inventory_ratio: PositiveFloat = (
        0.5  # Max inventory as ratio of max_net_exposure_usd to trigger full skew
    )
    inventory_sizing_factor: NonNegativeFloat = (
        0.5  # Factor to adjust order size based on inventory (0 to 1)
    )


class OrderLayer(BaseModel):
    """Defines a single layer for multi-layered order placement."""

    spread_offset_pct: NonNegativeFloat = (
        0.0  # Additional spread beyond base/dynamic spread
    )
    quantity_multiplier: PositiveFloat = 1.0  # Multiplier for base order quantity
    cancel_threshold_pct: PositiveFloat = (
        0.01  # Percentage price movement from placement price to trigger cancellation
    )


class CircuitBreakerConfig(BaseModel):
    """Configuration for bot's self-preservation mechanisms."""

    enabled: bool = True
    pause_threshold_pct: PositiveFloat = (
        0.02  # Price change % in window to trip circuit breaker
    )
    check_window_sec: PositiveInt = 10  # Time window for price change check
    pause_duration_sec: PositiveInt = 60  # How long to pause trading after tripping
    cool_down_after_trip_sec: PositiveInt = (
        300  # Cooldown period before re-enabling circuit breaker logic
    )
    max_daily_loss_pct: Optional[PositiveFloat] = Field(
        default=None,
        description="Max percentage loss of initial capital for the day. Bot will stop if hit.",
    )


class StrategyConfig(BaseModel):
    """Core market making strategy parameters."""

    base_spread_pct: PositiveFloat = 0.001  # Base spread for limit orders (e.g., 0.1%)
    base_order_size_pct_of_balance: PositiveFloat = (
        0.005  # Percentage of available balance for one order
    )
    order_stale_threshold_pct: PositiveFloat = (
        0.0005  # Price change % to consider an order stale and cancel
    )
    min_profit_spread_after_fees_pct: PositiveFloat = (
        0.0002  # Minimum spread to ensure profitability after fees
    )
    max_outstanding_orders: PositiveInt = (
        2  # Max number of active limit orders per side
    )
    market_data_stale_timeout_seconds: PositiveInt = (
        30  # Max age for orderbook/trade data before considered stale
    )
    enable_auto_sl_tp: bool = (
        False  # Enable automatic Stop-Loss and Take-Profit on market-making orders
    )
    take_profit_target_pct: PositiveFloat = (
        0.005  # Take-Profit percentage from entry price
    )
    stop_loss_trigger_pct: PositiveFloat = (
        0.005  # Stop-Loss percentage from entry price
    )
    kline_interval: str = "1m"  # Interval for OHLCV data for ATR calculation
    stale_order_max_age_seconds: PositiveInt = (
        300  # Max age for an order before it's considered stale and cancelled
    )

    dynamic_spread: DynamicSpreadConfig = Field(default_factory=DynamicSpreadConfig)
    inventory_skew: InventorySkewConfig = Field(default_factory=InventorySkewConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    order_layers: List[OrderLayer] = Field(default_factory=lambda: [OrderLayer()])

    model_config = ConfigDict(validate_assignment=True)


class SystemConfig(BaseModel):
    """System-wide operational parameters."""

    loop_interval_sec: PositiveFloat = 0.5  # Main bot loop sleep interval
    order_refresh_interval_sec: PositiveFloat = (
        5.0  # How often to refresh/reconcile orders
    )
    ws_heartbeat_sec: PositiveInt = 30  # WebSocket heartbeat interval
    cancellation_rate_limit_sec: PositiveFloat = (
        0.2  # Min delay between API cancellation requests
    )
    status_report_interval_sec: PositiveInt = 30  # How often to log status summary
    ws_reconnect_attempts: PositiveInt = 5  # Max attempts for WS reconnection
    ws_reconnect_initial_delay_sec: PositiveInt = 5  # Initial delay for WS reconnection
    ws_reconnect_max_delay_sec: PositiveInt = 60  # Max delay for WS reconnection
    api_retry_attempts: PositiveInt = 5  # Max attempts for API call retries
    api_retry_initial_delay_sec: PositiveFloat = (
        0.5  # Initial delay for API call retries
    )
    api_retry_max_delay_sec: PositiveFloat = 10.0  # Max delay for API call retries
    health_check_interval_sec: PositiveInt = (
        10  # How often to check account health (balance, position)
    )
    config_refresh_interval_sec: PositiveInt = (
        60  # How often to check for config file changes
    )

    model_config = ConfigDict(validate_assignment=True)


class FilesConfig(BaseModel):
    """File path and logging configurations."""

    log_level: str = "INFO"
    log_file: str = "market_maker.log"
    state_file: str = "market_maker_state.json"
    db_file: str = "market_maker.db"
    symbol_config_file: str = "symbols.json"
    log_format: Literal["plain", "json"] = "plain"
    pybit_log_level: str = "WARNING"

    model_config = ConfigDict(validate_assignment=True)


class GlobalConfig(BaseModel):
    """Global configuration for the market maker bot."""

    api_key: str = Field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    api_secret: str = Field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    testnet: bool = Field(
        default_factory=lambda: os.getenv("BYBIT_TESTNET", "true").lower() == "true"
    )
    trading_mode: Literal["DRY_RUN", "SIMULATION", "TESTNET", "LIVE"] = Field(
        default_factory=lambda: os.getenv("TRADING_MODE", "DRY_RUN")
    )
    category: Literal["linear", "inverse", "spot"] = Field(
        default_factory=lambda: os.getenv("TRADE_CATEGORY", "linear")
    )
    main_quote_currency: str = Field(
        default_factory=lambda: os.getenv("MAIN_QUOTE_CURRENCY", "USDT")
    )  # For overall balance tracking

    system: SystemConfig = Field(default_factory=SystemConfig)
    files: FilesConfig = Field(default_factory=FilesConfig)

    # Dry Run / Simulation specific settings
    initial_dry_run_capital: Decimal = Field(
        default_factory=lambda: Decimal(os.getenv("INITIAL_DRY_RUN_CAPITAL", "10000"))
    )
    dry_run_price_drift_mu: float = Field(
        default_factory=lambda: float(os.getenv("DRY_RUN_PRICE_DRIFT_MU", "0.0"))
    )
    dry_run_price_volatility_sigma: float = Field(
        default_factory=lambda: float(
            os.getenv("DRY_RUN_PRICE_VOLATILITY_SIGMA", "0.0001")
        )
    )
    dry_run_time_step_dt: float = Field(
        default_factory=lambda: float(os.getenv("DRY_RUN_TIME_STEP_DT", "1.0"))
    )

    model_config = ConfigDict(validate_assignment=True)

    def model_post_init(self, __context: Any) -> None:
        """Post-initialization hook for Pydantic model validation and logic."""
        if self.trading_mode == "TESTNET":
            object.__setattr__(self, "testnet", True)
        elif self.trading_mode == "LIVE":
            object.__setattr__(self, "testnet", False)

        if self.trading_mode not in ["DRY_RUN", "SIMULATION"] and (
            not self.api_key or not self.api_secret
        ):
            raise ConfigurationError(
                "API_KEY and API_SECRET must be set in .env for TESTNET or LIVE trading_mode."
            )


class SymbolConfig(BaseModel):
    """Configuration for a single trading symbol."""

    symbol: str  # e.g., "BTCUSDT" or "BTC/USDT:USDT"
    trade_enabled: bool = True
    leverage: PositiveInt = 10
    min_order_value_usd: PositiveFloat = 10.0
    max_order_size_pct: PositiveFloat = (
        0.1  # Max percentage of available balance for one order
    )
    max_net_exposure_usd: PositiveFloat = (
        500.0  # Max total value of open position in USD
    )
    trading_hours_start: Optional[str] = None  # e.g., "09:00" UTC
    trading_hours_end: Optional[str] = None  # e.g., "17:00" UTC

    strategy: StrategyConfig = Field(default_factory=StrategyConfig)

    # Market info (fetched dynamically from exchange, but can be overridden)
    price_precision: Optional[Decimal] = None  # e.g., Decimal('0.00001')
    quantity_precision: Optional[Decimal] = None  # e.g., Decimal('0.001')
    min_order_qty: Optional[Decimal] = None
    min_notional_value: Optional[Decimal] = None
    maker_fee_rate: Optional[Decimal] = None
    taker_fee_rate: Optional[Decimal] = None

    base_currency: Optional[str] = None
    quote_currency: Optional[str] = None

    model_config = ConfigDict(validate_assignment=True)

    def __pydantic_post_init__(self, __context: Any) -> None:
        """Post-initialization hook for Pydantic model validation and logic."""
        # Parse base and quote currency from symbol
        if self.symbol and ":" in self.symbol:  # CCXT style, e.g., BTC/USDT:USDT
            parts = self.symbol.split(":")
            self.quote_currency = parts[1]
            self.base_currency = parts[0].split("/")[0]
        elif (
            self.symbol and len(self.symbol) > 4 and self.symbol[-4:].isupper()
        ):  # e.g., BTCUSDT
            self.base_currency = self.symbol[:-4]
            self.quote_currency = self.symbol[-4:]
        elif (
            self.symbol and len(self.symbol) > 3 and self.symbol[-3:].isupper()
        ):  # e.g., BTCUSD (inverse)
            self.base_currency = self.symbol[:-3]
            self.quote_currency = self.symbol[-3:]
        else:
            self.base_currency = "UNKNOWN"
            self.quote_currency = "UNKNOWN"
            logging.getLogger("BybitMarketMaker").warning(
                f"[{self.symbol}] Cannot parse base/quote currency from symbol: {self.symbol}. Using UNKNOWN."
            )

        # Additional validation checks
        if self.strategy.inventory_skew.enabled and self.max_net_exposure_usd <= 0:
            raise ConfigurationError(
                f"[{self.symbol}] max_net_exposure_usd must be positive when inventory skew strategy is enabled."
            )
        if not (0 < self.max_order_size_pct <= 1):
            raise ConfigurationError(
                f"[{self.symbol}] max_order_size_pct must be between 0 and 1 (exclusive)."
            )
        if self.min_order_value_usd <= 0:
            raise ConfigurationError(
                f"[{self.symbol}] min_order_value_usd must be positive."
            )
        if self.max_net_exposure_usd < 0:
            raise ConfigurationError(
                f"[{self.symbol}] max_net_exposure_usd cannot be negative."
            )
        if self.strategy.base_spread_pct <= 0:
            raise ConfigurationError(
                f"[{self.symbol}] base_spread_pct must be positive."
            )
        if self.strategy.max_outstanding_orders < 0:
            raise ConfigurationError(
                f"[{self.symbol}] max_outstanding_orders cannot be negative."
            )
        if self.strategy.dynamic_spread.enabled:
            if not (
                0
                <= self.strategy.dynamic_spread.min_spread_pct
                <= self.strategy.dynamic_spread.max_spread_pct
            ):
                raise ConfigurationError(
                    f"[{self.symbol}] Dynamic spread min/max percentages are invalid."
                )
            if not (0 < self.strategy.dynamic_spread.price_change_smoothing_factor < 1):
                raise ConfigurationError(
                    f"[{self.symbol}] Price change smoothing factor must be between 0 and 1 (exclusive)."
                )
        if self.strategy.circuit_breaker.max_daily_loss_pct is not None and not (
            0 <= self.strategy.circuit_breaker.max_daily_loss_pct < 1
        ):
            raise ConfigurationError(
                f"[{self.symbol}] max_daily_loss_pct must be between 0 and 1 (exclusive) if set."
            )

    def format_price(self, p: Decimal) -> Decimal:
        """Rounds a Decimal price to the symbol's specified price precision."""
        if self.price_precision is None:
            logging.getLogger("BybitMarketMaker").warning(
                f"[{self.symbol}] Price precision not set. Using default 8 decimal places."
            )
            return p.quantize(Decimal("1e-8"), rounding=ROUND_DOWN)
        return p.quantize(self.price_precision, rounding=ROUND_DOWN)

    def format_quantity(self, q: Decimal) -> Decimal:
        """Rounds a Decimal quantity to the symbol's specified quantity precision."""
        if self.quantity_precision is None:
            logging.getLogger("BybitMarketMaker").warning(
                f"[{self.symbol}] Quantity precision not set. Using default 8 decimal places."
            )
            return q.quantize(Decimal("1e-8"), rounding=ROUND_DOWN)
        return q.quantize(self.quantity_precision, rounding=ROUND_DOWN)


class ConfigManager:
    """Manages loading and reloading of global and symbol configurations."""

    _global_config: GlobalConfig | None = None
    _symbol_configs: Dict[str, SymbolConfig] = {}  # Store as dict for easy lookup

    @classmethod
    def load_config(
        cls, single_symbol: Optional[str] = None
    ) -> Tuple[GlobalConfig, Dict[str, SymbolConfig]]:
        """
        Loads global config from .env and symbol configs from a JSON file.
        If single_symbol is provided, it generates a default config for that symbol.
        """
        try:
            cls._global_config = (
                GlobalConfig()
            )  # Pydantic v2 automatically loads from env
        except ValidationError as e:
            logging.critical(f"Global configuration validation error: {e}")
            raise ConfigurationError(f"Global configuration validation failed: {e}")

        cls._symbol_configs = {}
        if single_symbol:
            # Generate a default SymbolConfig for the single symbol
            default_symbol_data = {
                "symbol": single_symbol,
                "trade_enabled": True,
                "leverage": 10,
                "min_order_value_usd": 10.0,
                "max_order_size_pct": 0.1,
                "max_net_exposure_usd": 500.0,
                "strategy": StrategyConfig().model_dump(
                    mode="json_compatible"
                ),  # Convert to dict
            }
            try:
                cfg = SymbolConfig(**default_symbol_data)
                cls._symbol_configs[single_symbol] = cfg
                logging.getLogger("BybitMarketMaker").info(
                    f"[{Colors.CYAN}Using single symbol mode for {single_symbol}.{Colors.RESET}]"
                )
            except ValidationError as e:
                logging.critical(
                    f"Single symbol configuration validation error for {single_symbol}: {e}"
                )
                raise ConfigurationError(f"Single symbol configuration failed: {e}")
        else:
            # Load multiple symbols from file
            symbol_config_path = (
                Path(__file__).parent / cls._global_config.files.symbol_config_file
            )
            try:
                with open(symbol_config_path) as f:
                    raw_symbol_configs = json.loads(
                        f.read(), parse_float=Decimal, parse_int=Decimal
                    )
                if not isinstance(raw_symbol_configs, list):
                    raise ValueError(
                        "Symbol configuration file must contain a JSON list."
                    )

                for s_cfg_data in raw_symbol_configs:
                    try:
                        # Ensure 'strategy' key exists and merge default strategy settings if not provided
                        s_cfg_data.setdefault("strategy", {})
                        # Apply defaults for StrategyConfig fields if missing
                        default_strategy_config_dict = StrategyConfig().model_dump(
                            mode="json_compatible"
                        )
                        for (
                            strat_field,
                            default_value,
                        ) in default_strategy_config_dict.items():
                            if strat_field not in s_cfg_data["strategy"]:
                                s_cfg_data["strategy"][strat_field] = default_value
                            # Also apply defaults for nested strategy configs if they are dicts
                            elif isinstance(default_value, dict) and isinstance(
                                s_cfg_data["strategy"][strat_field], dict
                            ):
                                for (
                                    nested_field,
                                    nested_default_value,
                                ) in default_value.items():
                                    if (
                                        nested_field
                                        not in s_cfg_data["strategy"][strat_field]
                                    ):
                                        s_cfg_data["strategy"][strat_field][
                                            nested_field
                                        ] = nested_default_value

                        cfg = SymbolConfig(**s_cfg_data)
                        cls._symbol_configs[cfg.symbol] = cfg
                    except ValidationError as e:
                        logging.error(
                            f"Symbol configuration validation error for {s_cfg_data.get('symbol', 'N/A')}: {e}"
                        )
                    except Exception as e:
                        logging.error(
                            f"Unexpected error processing symbol config {s_cfg_data.get('symbol', 'N/A')}: {e}"
                        )

            except FileNotFoundError:
                logging.critical(
                    f"Symbol configuration file '{symbol_config_path}' not found. Please create it or use single symbol mode."
                )
                raise ConfigurationError(
                    f"Symbol config file not found: {symbol_config_path}"
                )
            except (json.JSONDecodeError, InvalidOperation, ValueError) as e:
                logging.critical(
                    f"Error decoding JSON from symbol configuration file '{symbol_config_path}': {e}"
                )
                raise ConfigurationError(f"Invalid symbol config file format: {e}")
            except Exception as e:
                logging.critical(f"Unexpected error loading symbol configs: {e}")
                raise ConfigurationError(f"Error loading symbol configs: {e}")

        return cls._global_config, cls._symbol_configs


# --- Logger Setup ---
class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "lineno": record.lineno,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_record["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(log_record)


def setup_logger(config: FilesConfig, name_suffix: str = "main") -> logging.Logger:
    """Configures a logger with console and file handlers."""
    logger_name = f"BybitMarketMaker.{name_suffix}"
    logger = logging.getLogger(logger_name)
    if logger.handlers:  # Avoid adding duplicate handlers if called multiple times
        for handler in logger.handlers:
            logger.removeHandler(handler)

    logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
    logger.propagate = False  # Prevent messages from bubbling up to root logger

    # Determine formatter based on config
    if config.log_format == "json":
        file_formatter = JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S")
        stream_formatter = JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S")
    else:  # "plain" format
        file_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s"
        )
        stream_formatter = logging.Formatter(
            f"{Colors.NEON_BLUE}%(asctime)s{Colors.RESET} - "
            f"{Colors.YELLOW}%(levelname)-8s{Colors.RESET} - "
            f"{Colors.MAGENTA}[%(name)s]{Colors.RESET} - %(message)s",
            datefmt="%H:%M:%S",
        )

    # File handler
    log_file_path = LOG_DIR / config.log_file
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Stream handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)

    # Set log level for pybit library
    pybit_logger = logging.getLogger("pybit")
    pybit_logger.setLevel(
        getattr(logging, config.pybit_log_level.upper(), logging.WARNING)
    )
    # Prevent pybit logs from being handled by the root logger if it's configured
    pybit_logger.propagate = False
    # Add handlers to pybit logger if it doesn't have any
    if not pybit_logger.handlers:
        pybit_logger.addHandler(file_handler)
        pybit_logger.addHandler(stream_handler)

    return logger


# --- Decorator for API Retries ---
def retry_api_call():
    """Decorator to apply Tenacity retry logic to API calls."""
    global_config = ConfigManager._global_config  # Access the loaded global config
    if (
        global_config is None
    ):  # Fallback if config not loaded yet (shouldn't happen in normal flow)
        return retry(
            stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=5)
        )

    return retry(
        stop=stop_after_attempt(global_config.system.api_retry_attempts),
        wait=wait_exponential_jitter(
            initial=global_config.system.api_retry_initial_delay_sec,
            max=global_config.system.api_retry_max_delay_sec,
        ),
        retry=retry_if_exception(
            lambda e: isinstance(e, BybitAPIError)
            and e.ret_code not in [10001, 10004, 110001, 110003, 12130, 12131]
        ),
        before_sleep=before_sleep_log(
            logging.getLogger("BybitMarketMaker.api_retry"),
            logging.WARNING,
            exc_info=False,
        ),
        reraise=True,
    )


# --- Data Classes for Trading State and Metrics ---
@dataclass
class TradeMetrics:
    """Aggregated trading performance metrics."""

    total_trades: int = 0
    gross_profit: Decimal = DECIMAL_ZERO
    gross_loss: Decimal = DECIMAL_ZERO
    total_fees: Decimal = DECIMAL_ZERO
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    realized_pnl: Decimal = DECIMAL_ZERO
    current_asset_holdings: Decimal = (
        DECIMAL_ZERO  # For spot, tracks base currency holdings
    )
    average_entry_price: Decimal = (
        DECIMAL_ZERO  # For spot, tracks average entry price of holdings
    )
    last_pnl_update_timestamp: datetime | None = None

    @property
    def net_realized_pnl(self) -> Decimal:
        return self.realized_pnl - self.total_fees

    def update_win_rate(self) -> None:
        self.win_rate = (
            (self.wins / self.total_trades * 100.0) if self.total_trades > 0 else 0.0
        )

    def update_pnl_on_buy(self, quantity: Decimal, price: Decimal) -> None:
        """Updates holdings and average entry price for a buy trade."""
        if self.current_asset_holdings > DECIMAL_ZERO:
            self.average_entry_price = (
                (self.average_entry_price * self.current_asset_holdings)
                + (price * quantity)
            ) / (self.current_asset_holdings + quantity)
        else:
            self.average_entry_price = price
        self.current_asset_holdings += quantity
        self.last_pnl_update_timestamp = datetime.now(timezone.utc)

    def update_pnl_on_sell(self, quantity: Decimal, price: Decimal) -> None:
        """Updates holdings and average entry price for a sell trade."""
        if self.current_asset_holdings < quantity:
            logging.getLogger("BybitMarketMaker").warning(
                f"Attempted to sell {quantity} but only {self.current_asset_holdings} held. Adjusting quantity."
            )
            quantity = self.current_asset_holdings
            if quantity <= DECIMAL_ZERO:
                return  # Nothing to sell

        self.realized_pnl += (
            price - self.average_entry_price
        ) * quantity  # Realized PnL from this specific sale

        self.current_asset_holdings -= quantity
        if self.current_asset_holdings <= DECIMAL_ZERO:
            self.average_entry_price = DECIMAL_ZERO
            self.current_asset_holdings = (
                DECIMAL_ZERO  # Ensure it's not negative due to precision
            )
        self.last_pnl_update_timestamp = datetime.now(timezone.utc)

    def calculate_unrealized_pnl(self, current_price: Decimal) -> Decimal:
        """Calculates unrealized PnL for spot holdings based on current market price."""
        if (
            self.current_asset_holdings > DECIMAL_ZERO
            and self.average_entry_price > DECIMAL_ZERO
            and current_price > DECIMAL_ZERO
        ):
            return (
                current_price - self.average_entry_price
            ) * self.current_asset_holdings
        return DECIMAL_ZERO


@dataclass
class TradingState:
    """Current dynamic state of a trading symbol bot."""

    mid_price: Decimal = DECIMAL_ZERO
    smoothed_mid_price: Decimal = DECIMAL_ZERO  # EMA of mid_price
    current_balance: Decimal = DECIMAL_ZERO  # For quote currency, e.g., USDT
    available_balance: Decimal = DECIMAL_ZERO
    current_position_qty: Decimal = (
        DECIMAL_ZERO  # For base currency, e.g., BTC (signed: +long, -short)
    )

    # For derivatives, this is the exchange-reported unrealized PnL
    unrealized_pnl_derivatives: Decimal = DECIMAL_ZERO

    active_orders: Dict[str, Dict[str, Any]] = field(
        default_factory=dict
    )  # {order_id: order_details}
    last_order_management_time: float = 0.0
    last_ws_message_time: float = field(default_factory=time.time)
    last_status_report_time: float = 0.0
    last_health_check_time: float = 0.0

    # For dynamic spread and circuit breaker (timestamp, high, low, close)
    price_candlestick_history: deque[Tuple[float, Decimal, Decimal, Decimal]] = field(
        default_factory=deque
    )
    circuit_breaker_price_points: deque[Tuple[float, Decimal]] = field(
        default_factory=deque
    )

    is_paused: bool = False
    pause_end_time: float = 0.0
    circuit_breaker_cooldown_end_time: float = 0.0
    ws_reconnect_attempts_left: int = 0

    metrics: TradeMetrics = field(default_factory=TradeMetrics)

    daily_initial_capital: Decimal = DECIMAL_ZERO
    daily_pnl_reset_date: datetime | None = None

    # For DRY_RUN simulation
    last_dry_run_price_update_time: float = field(default_factory=time.time)


# --- State and DB Managers ---
class StateManager:
    """Handles saving and loading bot state to/from a JSON file."""

    def __init__(self, file_path: Path, logger: logging.Logger):
        self.file_path = file_path
        self.logger = logger

    async def save_state(self, state: Dict[str, Any]) -> None:
        """Saves the bot's current state to a JSON file atomically."""
        try:
            temp_path = self.file_path.with_suffix(f".tmp_{os.getpid()}")
            async with aiofiles.open(temp_path, "w") as f:
                await f.write(json.dumps(state, indent=4, cls=JsonDecimalEncoder))
            os.replace(temp_path, self.file_path)  # Atomic replacement
            self.logger.info(f"State saved successfully to {self.file_path.name}.")
        except Exception as e:
            self.logger.error(
                f"Error saving state to {self.file_path.name}: {e}", exc_info=True
            )

    async def load_state(self) -> Dict[str, Any] | None:
        """Loads the bot's state from a JSON file. Returns None if file not found or error occurs."""
        if not self.file_path.exists():
            return None
        try:
            async with aiofiles.open(self.file_path) as f:
                return json.loads(
                    await f.read(), parse_float=Decimal, parse_int=Decimal
                )
        except Exception as e:
            self.logger.error(
                f"Error loading state from {self.file_path.name}: {e}. Starting fresh.",
                exc_info=True,
            )
            # Rename corrupted file to prevent continuous errors
            try:
                self.file_path.rename(
                    self.file_path.with_suffix(f".corrupted_{int(time.time())}")
                )
            except OSError as ose:
                self.logger.warning(
                    f"Could not rename corrupted state file {self.file_path.name}: {ose}"
                )
            return None


class DBManager:
    """Manages SQLite database for logging trading events and metrics."""

    def __init__(self, db_file: Path, logger: logging.Logger):
        self.db_file = db_file
        self.conn: Optional[aiosqlite.Connection] = None
        self.logger = logger

    async def connect(self) -> None:
        """Establishes a connection to the SQLite database."""
        try:
            self.conn = await aiosqlite.connect(self.db_file)
            self.conn.row_factory = aiosqlite.Row
            self.logger.info(f"Connected to database: {self.db_file.name}")
        except Exception as e:
            self.logger.critical(f"Failed to connect to database: {e}", exc_info=True)
            sys.exit(1)

    async def close(self) -> None:
        """Closes the database connection."""
        if self.conn:
            await self.conn.close()
            self.logger.info("Database connection closed.")

    async def create_tables(self) -> None:
        """
        Creates necessary tables if they do not already exist and performs schema migrations.
        """
        if not self.conn:
            await self.connect()

        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS order_events (
                id INTEGER PRIMARY KEY, timestamp TEXT, symbol TEXT,
                order_id TEXT, order_link_id TEXT, side TEXT, order_type TEXT,
                price TEXT, qty TEXT, cum_exec_qty TEXT, status TEXT,
                reduce_only BOOLEAN, message TEXT
            );
            CREATE TABLE IF NOT EXISTS trade_fills (
                id INTEGER PRIMARY KEY, timestamp TEXT, symbol TEXT,
                order_id TEXT, trade_id TEXT, side TEXT, exec_price TEXT,
                exec_qty TEXT, fee TEXT, fee_currency TEXT, pnl TEXT,
                realized_pnl_impact TEXT, liquidity_role TEXT
            );
            CREATE TABLE IF NOT EXISTS balance_updates (
                id INTEGER PRIMARY KEY, timestamp TEXT, currency TEXT,
                wallet_balance TEXT, available_balance TEXT
            );
            CREATE TABLE IF NOT EXISTS bot_metrics (
                id INTEGER PRIMARY KEY, timestamp TEXT, symbol TEXT,
                total_trades INTEGER, net_realized_pnl TEXT, realized_pnl TEXT,
                unrealized_pnl TEXT, gross_profit TEXT, gross_loss TEXT,
                total_fees TEXT, wins INTEGER, losses INTEGER, win_rate REAL,
                current_asset_holdings TEXT, average_entry_price TEXT,
                daily_pnl TEXT, daily_loss_pct REAL,
                mid_price TEXT
            );
        """)

        async def _add_column_if_not_exists(
            table: str, column: str, type: str, default: str
        ) -> None:
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

        # Ensure all columns exist, adding new ones introduced in this upgrade
        await _add_column_if_not_exists("order_events", "symbol", "TEXT", "''")
        await _add_column_if_not_exists("order_events", "reduce_only", "BOOLEAN", "0")
        await _add_column_if_not_exists("trade_fills", "symbol", "TEXT", "''")
        await _add_column_if_not_exists("bot_metrics", "symbol", "TEXT", "''")
        await _add_column_if_not_exists("bot_metrics", "mid_price", "TEXT", "'0'")

        await self.conn.commit()
        self.logger.info("Database tables checked/created and migrated.")

    async def log_order_event(
        self, symbol: str, order_data: Dict[str, Any], message: Optional[str] = None
    ) -> None:
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT INTO order_events (timestamp, symbol, order_id, order_link_id, side, order_type, price, qty, cum_exec_qty, status, reduce_only, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    symbol,
                    order_data.get("orderId"),
                    order_data.get("orderLinkId"),
                    order_data.get("side"),
                    order_data.get("orderType"),
                    str(order_data.get("price", DECIMAL_ZERO)),
                    str(order_data.get("qty", DECIMAL_ZERO)),
                    str(order_data.get("cumExecQty", DECIMAL_ZERO)),
                    order_data.get("orderStatus"),
                    order_data.get("reduceOnly", False),
                    message,
                ),
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(
                f"Error logging order event to DB for {symbol}: {e}", exc_info=True
            )

    async def log_trade_fill(
        self, symbol: str, trade_data: Dict[str, Any], realized_pnl_impact: Decimal
    ) -> None:
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT INTO trade_fills (timestamp, symbol, order_id, trade_id, side, exec_price, exec_qty, fee, fee_currency, pnl, realized_pnl_impact, liquidity_role) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    symbol,
                    trade_data.get("orderId"),
                    trade_data.get("execId"),
                    trade_data.get("side"),
                    str(trade_data.get("execPrice", DECIMAL_ZERO)),
                    str(trade_data.get("execQty", DECIMAL_ZERO)),
                    str(trade_data.get("execFee", DECIMAL_ZERO)),
                    trade_data.get("feeCurrency"),
                    str(trade_data.get("pnl", DECIMAL_ZERO)),
                    str(realized_pnl_impact),
                    trade_data.get("execType", "UNKNOWN"),
                ),
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(
                f"Error logging trade fill to DB for {symbol}: {e}", exc_info=True
            )

    async def log_balance_update(
        self,
        currency: str,
        wallet_balance: Decimal,
        available_balance: Optional[Decimal] = None,
    ) -> None:
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

    async def log_bot_metrics(
        self,
        symbol: str,
        metrics: TradeMetrics,
        unrealized_pnl: Decimal,
        daily_pnl: Decimal,
        daily_loss_pct: float,
        mid_price: Decimal,
    ) -> None:
        if not self.conn:
            return
        try:
            await self.conn.execute(
                "INSERT INTO bot_metrics (timestamp, symbol, total_trades, net_realized_pnl, realized_pnl, unrealized_pnl, gross_profit, gross_loss, total_fees, wins, losses, win_rate, current_asset_holdings, average_entry_price, daily_pnl, daily_loss_pct, mid_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    symbol,
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
                    str(daily_pnl),
                    daily_loss_pct,
                    str(mid_price),
                ),
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(
                f"Error logging bot metrics to DB for {symbol}: {e}", exc_info=True
            )


# --- Bybit API Client (HTTP) ---
class BybitAPIClient:
    """
    Asynchronous Bybit HTTP client with retry logic.
    Wraps synchronous pybit HTTP calls with asyncio.to_thread.
    """

    def __init__(self, global_config: GlobalConfig, logger: logging.Logger):
        self.config = global_config
        self.logger = logger
        self.http_session = HTTP(
            testnet=self.config.testnet,
            api_key=self.config.api_key,
            api_secret=self.config.api_secret,
        )
        self.last_cancel_time = 0.0

        # Store original methods to apply tenacity decorator
        self._original_methods = {
            "get_instruments_info": self.get_instruments_info_impl,
            "get_wallet_balance": self.get_wallet_balance_impl,
            "get_position_info": self.get_position_info_impl,
            "set_leverage": self.set_leverage_impl,
            "get_open_orders": self.get_open_orders_impl,
            "place_order": self.place_order_impl,
            "cancel_order": self.cancel_order_impl,
            "cancel_all_orders": self.cancel_all_orders_impl,
            "set_trading_stop": self.set_trading_stop_impl,
            "get_kline": self.get_kline_impl,
        }
        self._initialize_api_retry_decorator()

    def _is_retryable_bybit_error(self, exception: Exception) -> bool:
        if not isinstance(exception, BybitAPIError):
            return False
        # Do not retry on auth, bad params, insufficient balance, or explicit rate limit
        # Common Bybit non-retryable error codes:
        # 10001: Parameters error
        # 10002: Unknown error (sometimes transient, but often means bad request)
        # 10003: Recv window error (often a client-side clock sync issue or bad timestamp)
        # 10004: Authentication failed
        # 10006, 10007, 10016, 120004, 120005: Rate limit (handled by BybitRateLimitError)
        # 110001, 110003, 12130, 12131: Insufficient balance (handled by BybitInsufficientBalanceError)
        # 30001-30005: Order related errors (e.g., invalid price, qty)
        # 30042: Order price cannot be higher/lower than X times of current market price
        # 30070: Cross/isolated margin mode not switched
        # 30071: Leverage not modified (often means it's already set)
        non_retryable_codes = {
            10001,
            10002,
            10003,
            10004,
            30001,
            30002,
            30003,
            30004,
            30005,
            30042,
            30070,
            30071,
        }
        if exception.ret_code in non_retryable_codes:
            return False
        if isinstance(
            exception,
            (
                APIAuthError,
                ValueError,
                BybitRateLimitError,
                BybitInsufficientBalanceError,
            ),
        ):
            return False
        return True  # Default to retry for other API errors (e.g., network issues, temporary server errors)

    def _get_api_retry_decorator(self) -> Callable[..., Any]:
        return retry(
            stop=stop_after_attempt(self.config.system.api_retry_attempts),
            wait=wait_exponential_jitter(
                initial=self.config.system.api_retry_initial_delay_sec,
                max=self.config.system.api_retry_max_delay_sec,
            ),
            retry=retry_if_exception(self._is_retryable_bybit_error),
            before_sleep=before_sleep_log(self.logger, logging.WARNING, exc_info=False),
            reraise=True,
        )

    def _initialize_api_retry_decorator(self) -> None:
        api_retry = self._get_api_retry_decorator()
        for name, method in self._original_methods.items():
            setattr(self, name, api_retry(method))
        self.logger.debug("API retry decorators initialized and applied.")

    async def _run_sync_api_call(
        self, api_method: Callable, *args: Any, **kwargs: Any
    ) -> Any:
        """Runs a synchronous API call in a separate thread."""
        return await asyncio.to_thread(api_method, *args, **kwargs)

    async def _handle_response_async(
        self, coro: Coroutine[Any, Any, Any], action: str
    ) -> Dict[str, Any]:
        """Processes API responses, checking for errors and raising custom exceptions."""
        response = await coro

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
        elif ret_code == 10002:  # General parameter error
            raise ValueError(
                f"API {action} parameter error: {ret_msg} (ErrCode: {ret_code})"
            )
        elif (
            ret_code == 30042
        ):  # Order price cannot be higher/lower than X times of current market price
            raise OrderPlacementError(
                f"Order price out of range for {action}: {ret_msg} (ErrCode: {ret_code})"
            )
        elif ret_code == 30070:  # Cross/isolated margin mode not switched
            raise ConfigurationError(
                f"Margin mode not set correctly for {action}: {ret_msg} (ErrCode: {ret_code})"
            )
        elif ret_code == 30071:  # Leverage not modified
            self.logger.warning(
                f"Leverage for {action} not modified: {ret_msg} (ErrCode: {ret_code}). May already be set."
            )
            return response.get("result", {})  # Treat as non-critical success

        raise BybitAPIError(
            f"API {action} failed: {ret_msg}", ret_code=ret_code, ret_msg=ret_msg
        )

    # --- Implementations for API Calls ---
    async def get_instruments_info_impl(
        self, category: str, symbol: str
    ) -> Dict[str, Any] | None:
        response_coro = self._run_sync_api_call(
            self.http_session.get_instruments_info, category=category, symbol=symbol
        )
        result = await self._handle_response_async(
            response_coro, f"get_instruments_info for {symbol}"
        )
        return result.get("list", [{}])[0] if result else None

    async def get_wallet_balance_impl(self, account_type: str) -> Dict[str, Any] | None:
        response_coro = self._run_sync_api_call(
            self.http_session.get_wallet_balance, accountType=account_type
        )
        result = await self._handle_response_async(response_coro, "get_wallet_balance")
        return result.get("list", [{}])[0] if result else None

    async def get_position_info_impl(
        self, category: str, symbol: str
    ) -> Dict[str, Any] | None:
        if category not in ["linear", "inverse"]:
            return None  # Spot doesn't have positions in this context
        response_coro = self._run_sync_api_call(
            self.http_session.get_positions, category=category, symbol=symbol
        )
        result = await self._handle_response_async(
            response_coro, f"get_position_info for {symbol}"
        )
        if result and result.get("list"):
            for position in result["list"]:
                if position["symbol"] == symbol:
                    return position
        return None

    async def set_leverage_impl(
        self, category: str, symbol: str, leverage: Decimal
    ) -> bool:
        if category not in ["linear", "inverse"]:
            return True
        response_coro = self._run_sync_api_call(
            self.http_session.set_leverage,
            category=category,
            symbol=symbol,
            buyLeverage=str(leverage),
            sellLeverage=str(leverage),
        )
        return (
            await self._handle_response_async(
                response_coro, f"set_leverage for {symbol} to {leverage}"
            )
            is not None
        )

    async def get_open_orders_impl(
        self, category: str, symbol: str
    ) -> List[Dict[str, Any]]:
        response_coro = self._run_sync_api_call(
            self.http_session.get_open_orders,
            category=category,
            symbol=symbol,
            limit=50,
        )
        result = await self._handle_response_async(
            response_coro, f"get_open_orders for {symbol}"
        )
        return result.get("list", []) if result else []

    async def place_order_impl(self, params: Dict[str, Any]) -> Dict[str, Any] | None:
        response_coro = self._run_sync_api_call(self.http_session.place_order, **params)
        return await self._handle_response_async(
            response_coro,
            f"place_order ({params.get('side')} {params.get('qty')} @ {params.get('price')})",
        )

    async def cancel_order_impl(
        self,
        category: str,
        symbol: str,
        order_id: str,
        order_link_id: str | None = None,
    ) -> bool:
        current_time = time.time()
        if (
            current_time - self.last_cancel_time
        ) < self.config.system.cancellation_rate_limit_sec:
            await asyncio.sleep(
                self.config.system.cancellation_rate_limit_sec
                - (current_time - self.last_cancel_time)
            )

        params = {"category": category, "symbol": symbol, "orderId": order_id}
        if order_link_id:
            params["orderLinkId"] = order_link_id
        response_coro = self._run_sync_api_call(
            self.http_session.cancel_order, **params
        )
        self.last_cancel_time = time.time()
        return (
            await self._handle_response_async(response_coro, f"cancel_order {order_id}")
            is not None
        )

    async def cancel_all_orders_impl(self, category: str, symbol: str) -> bool:
        params = {"category": category, "symbol": symbol}
        response_coro = self._run_sync_api_call(
            self.http_session.cancel_all_orders, **params
        )
        return (
            await self._handle_response_async(
                response_coro, f"cancel_all_orders for {symbol}"
            )
            is not None
        )

    async def set_trading_stop_impl(
        self, category: str, symbol: str, sl_price: Decimal, tp_price: Decimal
    ) -> bool:
        params = {
            "category": category,
            "symbol": symbol,
            "takeProfit": str(tp_price),
            "stopLoss": str(sl_price),
            "tpTriggerBy": "LastPrice",  # Or MarkPrice, IndexPrice
            "slTriggerBy": "LastPrice",
            "tpslMode": "Full",  # Full or Partial
        }
        response_coro = self._run_sync_api_call(
            self.http_session.set_trading_stop, **params
        )
        return (
            await self._handle_response_async(
                response_coro,
                f"set_trading_stop for {symbol} TP:{tp_price} SL:{sl_price}",
            )
            is not None
        )

    async def get_kline_impl(
        self, category: str, symbol: str, interval: str, limit: int
    ) -> List[List[Any]]:
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        response_coro = self._run_sync_api_call(self.http_session.get_kline, **params)
        result = await self._handle_response_async(
            response_coro, f"get_kline for {symbol} {interval}"
        )
        return result.get("list", []) if result else []

    # Expose decorated methods
    get_instruments_info: Callable[
        [str, str], Coroutine[Any, Any, Dict[str, Any] | None]
    ] = field(init=False)
    get_wallet_balance: Callable[[str], Coroutine[Any, Any, Dict[str, Any] | None]] = (
        field(init=False)
    )
    get_position_info: Callable[
        [str, str], Coroutine[Any, Any, Dict[str, Any] | None]
    ] = field(init=False)
    set_leverage: Callable[[str, str, Decimal], Coroutine[Any, Any, bool]] = field(
        init=False
    )
    get_open_orders: Callable[[str, str], Coroutine[Any, Any, List[Dict[str, Any]]]] = (
        field(init=False)
    )
    place_order: Callable[
        [Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any] | None]
    ] = field(init=False)
    cancel_order: Callable[[str, str, str, str | None], Coroutine[Any, Any, bool]] = (
        field(init=False)
    )
    cancel_all_orders: Callable[[str, str], Coroutine[Any, Any, bool]] = field(
        init=False
    )
    set_trading_stop: Callable[
        [str, str, Decimal, Decimal], Coroutine[Any, Any, bool]
    ] = field(init=False)
    get_kline: Callable[[str, str, str, int], Coroutine[Any, Any, List[List[Any]]]] = (
        field(init=False)
    )


# --- Bybit WebSocket Client ---
class BybitWebSocketClient:
    """
    Manages WebSocket connections for multiple symbols using pybit's WebSocket client.
    Handles public orderbook/trades and private order/position/execution updates.
    Includes reconnection logic.
    """

    def __init__(self, global_config: GlobalConfig, logger: logging.Logger):
        self.config = global_config
        self.logger = logger

        self._ws_public_instance: Optional[WebSocket] = None
        self._ws_private_instance: Optional[WebSocket] = None
        self._ws_public_task: Optional[asyncio.Task] = None
        self._ws_private_task: Optional[asyncio.Task] = None

        self.order_book_data: Dict[
            str, Dict[str, List[List[Decimal]]]
        ] = {}  # {symbol: {'b': [[price, qty]], 'a': ...}}
        self.recent_trades_data: Dict[
            str, deque[Tuple[float, Decimal, Decimal, str]]
        ] = {}  # {symbol: deque((timestamp, price, qty, side))}
        self.last_orderbook_update_time: Dict[str, float] = {}
        self.last_trades_update_time: Dict[str, float] = {}
        self.last_kline_update_time: Dict[str, float] = {}  # For kline data updates

        self.symbol_bots: Dict[
            str, AsyncSymbolBot
        ] = {}  # Reference to active SymbolBot instances

        self.message_queue: asyncio.Queue = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._public_topics: List[str] = []
        self._private_topics: List[str] = []

        # Lock for protecting shared data like symbol_bots, order_books, recent_trades
        self.data_lock = Lock()

    async def register_symbol_bot(self, symbol_bot: "AsyncSymbolBot") -> None:
        """Registers an AsyncSymbolBot instance to receive WS updates."""
        async with self.data_lock:
            self.symbol_bots[symbol_bot.config.symbol] = symbol_bot

    async def unregister_symbol_bot(self, symbol: str) -> None:
        """Unregisters an AsyncSymbolBot instance."""
        async with self.data_lock:
            if symbol in self.symbol_bots:
                del self.symbol_bots[symbol]

    async def _ws_message_handler(self, msg: Dict[str, Any]) -> None:
        """Puts incoming WebSocket messages into a queue for processing."""
        await self.message_queue.put(msg)

    async def _process_ws_messages(self) -> None:
        """Processes messages from the WebSocket queue."""
        while not self._stop_event.is_set():
            try:
                message = await asyncio.wait_for(
                    self.message_queue.get(), timeout=1.0
                )  # Small timeout to check stop_event
                # Update last WS message time for all bots, as it indicates overall WS health
                async with self.data_lock:
                    for bot in self.symbol_bots.values():
                        bot.state.last_ws_message_time = time.time()

                if "topic" in message:
                    topic = message["topic"]
                    if topic.startswith("orderbook."):
                        await self._process_orderbook_message(message)
                    elif topic.startswith("publicTrade."):
                        await self._process_public_trade_message(message)
                    elif topic.startswith("kline."):
                        await self._process_kline_message(message)
                    elif topic in ["order", "position", "execution", "wallet"]:
                        await self._process_private_message(message)
                    else:
                        self.logger.debug(f"Received unknown WS topic: {topic}")
                elif "op" in message and message["op"] == "pong":
                    self.logger.debug("WS Pong received.")
                else:
                    self.logger.debug(f"Received unhandled WS message: {message}")
            except asyncio.TimeoutError:
                pass  # Queue was empty, check stop_event and continue
            except Exception as e:
                self.logger.error(f"Error processing WS message: {e}", exc_info=True)

    def _normalize_symbol_ws(self, bybit_symbol_ws: str) -> str:
        """
        Normalizes Bybit's WebSocket symbol format (e.g., BTCUSDT)
        to the internal CCXT-like format (e.g., BTC/USDT:USDT) used in SymbolConfig.
        """
        if self.config.category == "spot":
            # Spot symbols are often like "BTCUSDT" or "ETHUSDC"
            if (
                len(bybit_symbol_ws) >= 6
                and bybit_symbol_ws[-4:].isupper()
                and bybit_symbol_ws[:-4].isupper()
            ):
                return f"{bybit_symbol_ws[:-4]}/{bybit_symbol_ws[-4:]}"
            elif (
                len(bybit_symbol_ws) >= 5
                and bybit_symbol_ws[-3:].isupper()
                and bybit_symbol_ws[:-3].isupper()
            ):
                return f"{bybit_symbol_ws[:-3]}/{bybit_symbol_ws[-3:]}"
            return bybit_symbol_ws  # Fallback

        # For derivatives (linear/inverse), pybit WS uses e.g., BTCUSDT
        # Our internal config might use BTC/USDT:USDT
        if bybit_symbol_ws.endswith("USDT"):
            return (
                f"{bybit_symbol_ws[:-4]}/{bybit_symbol_ws[-4:]}:{bybit_symbol_ws[-4:]}"
            )
        elif bybit_symbol_ws.endswith("USD"):  # Inverse
            return bybit_symbol_ws
        return bybit_symbol_ws  # Fallback for other cases

    async def _process_orderbook_message(self, message: Dict[str, Any]) -> None:
        """Updates the order book for a symbol and notifies relevant bot."""
        data = message.get("data")
        if not data:
            return

        topic = message["topic"]
        parts = topic.split(".")
        if len(parts) < 3:
            self.logger.warning(f"Unrecognized orderbook topic format: {topic}")
            return

        symbol_ws = parts[2]  # e.g., "BTCUSDT"
        symbol = self._normalize_symbol_ws(symbol_ws)

        bids = [
            [Decimal(str(item[0])), Decimal(str(item[1]))] for item in data.get("b", [])
        ]
        asks = [
            [Decimal(str(item[0])), Decimal(str(item[1]))] for item in data.get("a", [])
        ]

        if bids or asks:  # Update even if only one side has changes
            async with self.data_lock:  # Protect shared order_book_data
                self.order_book_data[symbol] = {"b": bids, "a": asks}
                self.last_orderbook_update_time[symbol] = time.time()
            async with self.data_lock:  # Access symbol_bots safely
                if symbol in self.symbol_bots:
                    await self.symbol_bots[symbol]._update_mid_price(bids, asks)
        else:
            self.logger.debug(
                f"Received empty or incomplete orderbook data for {symbol}. Skipping mid-price update."
            )

    async def _process_public_trade_message(self, message: Dict[str, Any]) -> None:
        """Updates recent trades for a symbol."""
        data = message.get("data")
        if not data:
            return

        topic = message["topic"]
        parts = topic.split(".")
        if len(parts) < 2:
            self.logger.warning(f"Unrecognized publicTrade topic format: {topic}")
            return

        symbol_ws = parts[1]
        symbol = self._normalize_symbol_ws(symbol_ws)

        async with self.data_lock:  # Protect shared recent_trades_data
            if symbol not in self.recent_trades_data:
                self.recent_trades_data[symbol] = deque(
                    maxlen=200
                )  # Max 200 trades history

            for trade_data in data:
                price = Decimal(str(trade_data.get("p", DECIMAL_ZERO)))
                qty = Decimal(str(trade_data.get("v", DECIMAL_ZERO)))
                side = trade_data.get("S", "unknown")  # 'Buy' or 'Sell'
                self.recent_trades_data[symbol].append((time.time(), price, qty, side))
            self.last_trades_update_time[symbol] = time.time()

    async def _process_kline_message(self, message: Dict[str, Any]) -> None:
        """Processes kline updates for ATR calculation."""
        data = message.get("data")
        if not data:
            return

        topic = message["topic"]
        parts = topic.split(".")
        if len(parts) < 3:
            self.logger.warning(f"Unrecognized kline topic format: {topic}")
            return

        interval = parts[1]
        symbol_ws = parts[2]
        symbol = self._normalize_symbol_ws(symbol_ws)

        for kline_data in data:
            if kline_data.get("confirm"):  # Only process confirmed (closed) candles
                open_price = Decimal(kline_data.get("open", DECIMAL_ZERO))
                high_price = Decimal(kline_data.get("high", DECIMAL_ZERO))
                low_price = Decimal(kline_data.get("low", DECIMAL_ZERO))
                close_price = Decimal(kline_data.get("close", DECIMAL_ZERO))
                timestamp = (
                    float(kline_data.get("timestamp", time.time() * 1000)) / 1000
                )  # Convert ms to sec

                async with self.data_lock:
                    if symbol in self.symbol_bots:
                        self.symbol_bots[symbol].state.price_candlestick_history.append(
                            (timestamp, high_price, low_price, close_price)
                        )
                        self.last_kline_update_time[symbol] = time.time()
                        self.logger.debug(
                            f"[{symbol}] Kline updated (interval: {interval}): C={close_price}, H={high_price}, L={low_price}"
                        )

    async def _process_private_message(self, message: Dict[str, Any]) -> None:
        """Processes private stream messages (orders, positions, executions) and dispatches to relevant bots."""
        topic = message["topic"]
        if topic in ["order", "execution", "position", "wallet"]:
            for item_data in message["data"]:
                symbol_ws = item_data.get("symbol")
                if symbol_ws:
                    normalized_symbol = self._normalize_symbol_ws(symbol_ws)
                    async with self.data_lock:  # Access symbol_bots safely
                        for bot in (
                            self.symbol_bots.values()
                        ):  # Iterate through registered SymbolBot instances
                            if bot.config.symbol == normalized_symbol:
                                if topic == "order":
                                    await bot._process_order_update(item_data)
                                elif topic == "position":
                                    await bot._process_position_update(item_data)
                                elif topic == "execution" and item_data.get(
                                    "execType"
                                ) in ["Trade", "AdlTrade", "BustTrade"]:
                                    await bot._process_execution_update(item_data)
                                elif topic == "wallet":
                                    await bot._update_balance_from_wallet_ws(item_data)
                                break
                        else:  # If no bot found for the symbol
                            self.logger.debug(
                                f"Received {topic} update for unmanaged symbol: {normalized_symbol}"
                            )

    async def get_order_book_snapshot(
        self, symbol: str
    ) -> Optional[Dict[str, List[List[Decimal]]]]:
        """Retrieves a snapshot of the order book for a symbol."""
        async with self.data_lock:  # Protect access to order_book_data
            return self.order_book_data.get(symbol)

    async def get_recent_trades(
        self, symbol: str, limit: int = 100
    ) -> deque[Tuple[float, Decimal, Decimal, str]]:
        """Retrieves recent trades for a symbol."""
        async with self.data_lock:  # Protect access to recent_trades_data
            return self.recent_trades_data.get(symbol, deque(maxlen=limit))

    async def _connect_and_subscribe(self, is_private: bool, topics: List[str]):
        """Internal helper to establish connection and subscribe."""
        ws_instance: Optional[WebSocket] = None
        channel_type = self.config.category if not is_private else "private"

        try:
            if is_private:
                if not self.config.api_key or not self.config.api_secret:
                    self.logger.warning(
                        f"{Colors.YELLOW}Skipping private WebSocket connection: API keys not provided.{Colors.RESET}"
                    )
                    return None
                ws_instance = WebSocket(
                    testnet=self.config.testnet,
                    api_key=self.config.api_key,
                    api_secret=self.config.api_secret,
                    channel_type=channel_type,
                )
            else:
                ws_instance = WebSocket(
                    testnet=self.config.testnet, channel_type=channel_type
                )

            if topics:
                self.logger.debug(f"Subscribing to WS topics: {topics}")
                for topic_full_string in topics:
                    # Parse topic to get topic_name and symbol
                    parts = topic_full_string.split(".")
                    if len(parts) > 1:
                        # For public topics, topic_name is everything before the last dot, symbol is after
                        topic_name = ".".join(
                            parts[:-1]
                        )  # e.g., "kline.1m", "orderbook.1", "publicTrade"
                        symbol = parts[-1]  # e.g., "XLMUSDT"
                    else:
                        # For private topics (no symbol in topic string)
                        topic_name = topic_full_string
                        symbol = None

                    if symbol:
                        ws_instance.subscribe(
                            topic=topic_name,
                            symbol=symbol,
                            callback=self._ws_message_handler,
                        )
                    else:
                        ws_instance.subscribe(
                            topic=topic_name, callback=self._ws_message_handler
                        )
                self.logger.info(f"Subscribed to WS topics: {', '.join(topics)}")

            return ws_instance

        except websocket._exceptions.WebSocketConnectionClosedException as e:
            self.logger.error(
                f"WebSocket connection failed: {e}. Is the Bybit server reachable and API keys correct?"
            )
            return None
        except Exception as e:
            self.logger.error(
                f"Error connecting or subscribing to WebSocket ({'private' if is_private else 'public'}): {e}",
                exc_info=True,
            )
            return None

    async def _reconnect_loop(self, is_private: bool):
        """Manages reconnection attempts for a WebSocket stream."""
        stream_name = "Private" if is_private else "Public"
        topics = self._private_topics if is_private else self._public_topics

        attempts = 0
        while not self._stop_event.is_set():
            if is_private and (not self.config.api_key or not self.config.api_secret):
                self.logger.warning(
                    f"{Colors.YELLOW}Not attempting {stream_name} WS reconnection: API keys not available.{Colors.RESET}"
                )
                await asyncio.sleep(
                    self.config.system.ws_reconnect_max_delay_sec
                )  # Wait before checking again
                continue

            current_ws_instance = (
                self._ws_private_instance if is_private else self._ws_public_instance
            )
            if current_ws_instance is not None:
                # pybit's WebSocket client doesn't expose connection status directly.
                # Rely on individual bots reporting stale data, which might trigger a full reconnect.
                await asyncio.sleep(self.config.system.ws_heartbeat_sec)
                continue

            self.logger.info(
                f"{Colors.YELLOW}Attempting to reconnect {stream_name} WebSocket stream... (Attempt {attempts + 1}/{self.config.system.ws_reconnect_attempts}){Colors.RESET}"
            )

            new_ws_instance = await self._connect_and_subscribe(is_private, topics)
            if new_ws_instance:
                if is_private:
                    self._ws_private_instance = new_ws_instance
                else:
                    self._ws_public_instance = new_ws_instance
                self.logger.info(
                    f"{Colors.NEON_GREEN}{stream_name} WebSocket reconnected successfully.{Colors.RESET}"
                )
                attempts = 0  # Reset attempts on success
            else:
                attempts += 1
                if attempts >= self.config.system.ws_reconnect_attempts:
                    self.logger.critical(
                        f"{Colors.NEON_RED}{stream_name} WebSocket reconnection failed after {self.config.system.ws_reconnect_attempts} attempts. Signalling shutdown.{Colors.RESET}"
                    )
                    self._stop_event.set()  # Signal main bot to stop
                    break

                delay = min(
                    self.config.system.ws_reconnect_initial_delay_sec
                    * (2 ** (attempts - 1)),
                    self.config.system.ws_reconnect_max_delay_sec,
                )
                self.logger.warning(
                    f"{Colors.NEON_ORANGE}{stream_name} WebSocket reconnection failed. Retrying in {delay} seconds...{Colors.RESET}"
                )
                await asyncio.sleep(delay)

    async def start_streams(
        self, public_topics: List[str], private_topics: List[str]
    ) -> None:
        """Starts public and private WebSocket streams, managing reconnection."""
        await self.stop_streams()  # Ensure clean slate

        self._stop_event.clear()
        self._public_topics = public_topics
        self._private_topics = private_topics

        # Start message processing task
        asyncio.create_task(self._process_ws_messages(), name="WS_Message_Processor")
        self.logger.info(
            f"{Colors.NEON_GREEN}# WebSocket message processor started.{Colors.RESET}"
        )

        # Start reconnection loops for each stream type
        if public_topics:
            self.logger.info(
                f"Initializing PUBLIC WS stream for topics: {public_topics}"
            )
            self._ws_public_task = asyncio.create_task(
                self._reconnect_loop(is_private=False), name="WS_Public_Reconnect_Loop"
            )
        if private_topics:
            self.logger.info(
                f"Initializing PRIVATE WS stream for topics: {private_topics}"
            )
            self._ws_private_task = asyncio.create_task(
                self._reconnect_loop(is_private=True), name="WS_Private_Reconnect_Loop"
            )

        self.logger.info(
            f"{Colors.NEON_GREEN}# WebSocket streams have been summoned.{Colors.RESET}"
        )

    async def stop_streams(self) -> None:
        """Stops all WebSocket connections and associated tasks."""
        if self._stop_event.is_set():
            return

        self.logger.info(
            f"{Colors.YELLOW}# Signaling WebSocket streams to stop...{Colors.RESET}"
        )
        self._stop_event.set()

        # Cancel reconnection tasks
        if self._ws_public_task:
            self._ws_public_task.cancel()
            try:
                await self._ws_public_task
            except asyncio.CancelledError:
                pass
            self._ws_public_task = None
        if self._ws_private_task:
            self._ws_private_task.cancel()
            try:
                await self._ws_private_task
            except asyncio.CancelledError:
                pass
            self._ws_private_task = None

        # Explicitly exit pybit WebSocket instances
        if self._ws_public_instance:
            try:
                await asyncio.to_thread(
                    self._ws_public_instance.exit
                )  # Run sync exit in thread
            except Exception as e:
                self.logger.debug(f"Error closing public WS: {e}")
            self._ws_public_instance = None
        if self._ws_private_instance:
            try:
                await asyncio.to_thread(
                    self._ws_private_instance.exit
                )  # Run sync exit in thread
            except Exception as e:
                self.logger.debug(f"Error closing private WS: {e}")
            self._ws_private_instance = None

        # Give some time for message processor to finish
        await asyncio.sleep(1)
        self.logger.info(
            f"{Colors.CYAN}# WebSocket streams have been extinguished.{Colors.RESET}"
        )


# --- Async Symbol Bot (Per-Symbol Logic) ---
class AsyncSymbolBot:
    """
    Manages market making operations for a single trading symbol.
    Runs as an asyncio task.
    """

    def __init__(
        self,
        global_config: GlobalConfig,
        symbol_config: SymbolConfig,
        api_client: BybitAPIClient,
        ws_client: BybitWebSocketClient,
        db_manager: DBManager,
        logger: logging.Logger,
    ):
        self.global_config = global_config
        self.config = symbol_config
        self.api_client = api_client
        self.ws_client = ws_client
        self.db_manager = db_manager
        self.logger = logger

        self.state = TradingState(
            ws_reconnect_attempts_left=self.global_config.system.ws_reconnect_attempts
        )
        self.state.price_candlestick_history = deque(
            maxlen=200
        )  # Keep enough history for ATR
        self.state.circuit_breaker_price_points = deque(
            maxlen=self.config.strategy.circuit_breaker.check_window_sec * 2
        )

        self.last_atr_update_time: float = 0.0
        self.cached_atr: Decimal = DECIMAL_ZERO
        self.last_symbol_info_refresh: float = 0.0
        self.current_leverage: int | None = None

        self._stop_event = asyncio.Event()

    async def initialize(self):
        """Performs initial setup for the symbol bot."""
        self.logger.info(f"[{self.config.symbol}] Initializing bot for symbol.")

        await self._load_state()  # Load previous state

        if not await self._fetch_market_info():
            raise MarketInfoError(
                f"[{self.config.symbol}] Failed to fetch market info. Shutting down."
            )

        if not await self._update_balance_and_position():
            raise InitialBalanceError(
                f"[{self.config.symbol}] Failed to fetch initial balance/position. Shutting down."
            )

        # Initialize daily_initial_capital if not set or it's a new day
        current_utc_date = datetime.now(timezone.utc).date()
        if self.state.daily_initial_capital == DECIMAL_ZERO or (
            self.state.daily_pnl_reset_date is not None
            and self.state.daily_pnl_reset_date.date() < current_utc_date
        ):
            self.state.daily_initial_capital = self.state.current_balance
            self.state.daily_pnl_reset_date = datetime.now(timezone.utc)
            self.logger.info(
                f"[{self.config.symbol}] Daily initial capital set to: {self.state.daily_initial_capital} {self.global_config.main_quote_currency}"
            )

        if self.global_config.trading_mode not in ["DRY_RUN", "SIMULATION"]:
            if (
                self.global_config.category in ["linear", "inverse"]
                and not await self._set_margin_mode_and_leverage()
            ):
                raise InitialBalanceError(
                    f"[{self.config.symbol}] Failed to set margin mode/leverage. Shutting down."
                )
        else:
            self.logger.info(
                f"[{self.config.symbol}] {self.global_config.trading_mode} mode: Skipping leverage setting."
            )

        await self._reconcile_orders_on_startup()
        self.logger.info(f"[{self.config.symbol}] Initial setup successful.")

    async def run_loop(self):
        """Main loop for the symbol bot."""
        self.logger.info(
            f"{Colors.CYAN}[{self.config.symbol}] SymbolBot starting its loop.{Colors.RESET}"
        )

        # Initial price for dry run
        if (
            self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]
            and self.state.mid_price == DECIMAL_ZERO
        ):
            mock_price = Decimal("0.1")
            self.state.mid_price = mock_price
            self.state.smoothed_mid_price = mock_price
            self.state.price_candlestick_history.append(
                (time.time(), mock_price, mock_price, mock_price)
            )
            self.logger.info(
                f"[{self.config.symbol}] {self.global_config.trading_mode} mode: Initialized mock mid_price to {mock_price}."
            )

        while not self._stop_event.is_set():
            current_time = time.time()
            try:
                # Dry run simulations
                if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
                    await self._simulate_dry_run_price_movement(current_time)
                    await self._simulate_dry_run_fills()

                # Check trading hours
                if not self._is_trading_hours(datetime.now(timezone.utc)):
                    self.logger.info(
                        f"[{self.config.symbol}] Outside trading hours. Cancelling all orders and pausing."
                    )
                    await self._cancel_all_orders()
                    await asyncio.sleep(self.global_config.system.loop_interval_sec)
                    continue

                # Periodic health checks and data freshness
                if not await self._check_market_data_freshness(current_time):
                    self.logger.warning(
                        f"[{self.config.symbol}] Stale market data. Skipping order management cycle."
                    )
                    await (
                        self._cancel_all_orders()
                    )  # Cancel orders if market data is stale
                    await asyncio.sleep(self.global_config.system.loop_interval_sec)
                    continue

                if (
                    current_time - self.state.last_health_check_time
                ) > self.global_config.system.health_check_interval_sec:
                    await self._update_balance_and_position()
                    self.state.last_health_check_time = current_time

                # Daily PnL and Circuit Breaker checks
                if await self._check_daily_pnl_limits():
                    self.logger.critical(
                        f"[{self.config.symbol}] Daily PnL limit hit. Trading disabled for this symbol."
                    )
                    self._stop_event.set()  # Stop this symbol bot
                    continue

                if await self._check_circuit_breaker(current_time):
                    self.logger.warning(
                        f"[{self.config.symbol}] Circuit breaker tripped. Skipping order management."
                    )
                    await asyncio.sleep(self.global_config.system.loop_interval_sec)
                    continue

                # Resume from pause
                if self.state.is_paused and current_time < self.state.pause_end_time:
                    self.logger.debug(
                        f"[{self.config.symbol}] Bot is paused due to circuit breaker. Resuming in {int(self.state.pause_end_time - current_time)}s."
                    )
                    await asyncio.sleep(self.global_config.system.loop_interval_sec)
                    continue
                elif self.state.is_paused:
                    self.logger.info(
                        f"[{self.config.symbol}] Circuit breaker pause finished. Resuming trading."
                    )
                    self.state.is_paused = False
                    self.state.circuit_breaker_cooldown_end_time = (
                        current_time
                        + self.config.strategy.circuit_breaker.cool_down_after_trip_sec
                    )

                if current_time < self.state.circuit_breaker_cooldown_end_time:
                    self.logger.debug(
                        f"[{self.config.symbol}] Circuit breaker in cooldown. Resuming trading in {int(self.state.circuit_breaker_cooldown_end_time - current_time)}s."
                    )
                    await asyncio.sleep(self.global_config.system.loop_interval_sec)
                    continue

                # Main order management logic
                if (
                    self.config.trade_enabled
                    and (current_time - self.state.last_order_management_time)
                    > self.global_config.system.order_refresh_interval_sec
                ):
                    await self._manage_orders()
                    self.state.last_order_management_time = current_time
                    await self._check_and_handle_stale_orders(current_time)
                elif not self.config.trade_enabled:
                    self.logger.debug(
                        f"[{self.config.symbol}] Trading disabled. Skipping order management."
                    )
                    await (
                        self._cancel_all_orders()
                    )  # Ensure no orders are left if trading is disabled

                # Auto TP/SL
                if (
                    self.config.strategy.enable_auto_sl_tp
                    and self.state.current_position_qty != DECIMAL_ZERO
                ):
                    await self._update_take_profit_stop_loss()

                # Status report
                if (
                    current_time - self.state.last_status_report_time
                ) > self.global_config.system.status_report_interval_sec:
                    await self._log_status_summary()
                    self.state.last_status_report_time = current_time

            except asyncio.CancelledError:
                self.logger.info(f"[{self.config.symbol}] SymbolBot task cancelled.")
                break
            except Exception as e:
                self.logger.error(
                    f"{Colors.NEON_RED}[{self.config.symbol}] Unhandled error in main loop: {e}{Colors.RESET}",
                    exc_info=True,
                )
                termux_notify(
                    f"{self.config.symbol}: Bot Error: {str(e)[:50]}...", is_error=True
                )

            await asyncio.sleep(self.global_config.system.loop_interval_sec)

        self.logger.info(
            f"{Colors.CYAN}[{self.config.symbol}] SymbolBot stopping. Cancelling orders and saving state.{Colors.RESET}"
        )
        await self._cancel_all_orders()
        await self._save_state()

    def stop(self):
        """Sets the stop event to gracefully stop the bot's main loop."""
        self._stop_event.set()

    # --- State Management ---
    async def _save_state(self):
        """Saves the current trading state for this symbol."""
        state_data = {
            "mid_price": str(self.state.mid_price),
            "smoothed_mid_price": str(self.state.smoothed_mid_price),
            "current_balance": str(self.state.current_balance),
            "available_balance": str(self.state.available_balance),
            "current_position_qty": str(self.state.current_position_qty),
            "unrealized_pnl_derivatives": str(self.state.unrealized_pnl_derivatives),
            # Convert Decimal values in active_orders to string for JSON serialization
            "active_orders": {
                oid: {
                    k: str(v) if isinstance(v, Decimal) else v for k, v in odata.items()
                }
                for oid, odata in self.state.active_orders.items()
            },
            "last_order_management_time": self.state.last_order_management_time,
            "last_ws_message_time": self.state.last_ws_message_time,
            "last_status_report_time": self.state.last_status_report_time,
            "last_health_check_time": self.state.last_health_check_time,
            "price_candlestick_history": [
                (t, str(h), str(l), str(c))
                for t, h, l, c in self.state.price_candlestick_history
            ],
            "circuit_breaker_price_points": [
                (t, str(p)) for t, p in self.state.circuit_breaker_price_points
            ],
            "is_paused": self.state.is_paused,
            "pause_end_time": self.state.pause_end_time,
            "circuit_breaker_cooldown_end_time": self.state.circuit_breaker_cooldown_end_time,
            "ws_reconnect_attempts_left": self.state.ws_reconnect_attempts_left,
            "metrics": {
                "total_trades": self.state.metrics.total_trades,
                "gross_profit": str(self.state.metrics.gross_profit),
                "gross_loss": str(self.state.metrics.gross_loss),
                "total_fees": str(self.state.metrics.total_fees),
                "wins": self.state.metrics.wins,
                "losses": self.state.metrics.losses,
                "win_rate": self.state.metrics.win_rate,
                "realized_pnl": str(self.state.metrics.realized_pnl),
                "current_asset_holdings": str(
                    self.state.metrics.current_asset_holdings
                ),
                "average_entry_price": str(self.state.metrics.average_entry_price),
                "last_pnl_update_timestamp": self.state.metrics.last_pnl_update_timestamp.isoformat()
                if self.state.metrics.last_pnl_update_timestamp
                else None,
            },
            "daily_initial_capital": str(self.state.daily_initial_capital),
            "daily_pnl_reset_date": self.state.daily_pnl_reset_date.isoformat()
            if self.state.daily_pnl_reset_date
            else None,
            "last_dry_run_price_update_time": self.state.last_dry_run_price_update_time,
        }
        await StateManager(
            STATE_DIR
            / (
                self.config.symbol.replace("/", "_").replace(":", "")
                + "_"
                + self.global_config.files.state_file
            ),
            self.logger,
        ).save_state(state_data)

    async def _load_state(self):
        """Loads the trading state for this symbol from file."""
        state_data = await StateManager(
            STATE_DIR
            / (
                self.config.symbol.replace("/", "_").replace(":", "")
                + "_"
                + self.global_config.files.state_file
            ),
            self.logger,
        ).load_state()
        if state_data:
            self.state.mid_price = Decimal(
                str(state_data.get("mid_price", DECIMAL_ZERO))
            )
            self.state.smoothed_mid_price = Decimal(
                str(state_data.get("smoothed_mid_price", DECIMAL_ZERO))
            )
            self.state.current_balance = Decimal(
                str(state_data.get("current_balance", DECIMAL_ZERO))
            )
            self.state.available_balance = Decimal(
                str(state_data.get("available_balance", DECIMAL_ZERO))
            )
            self.state.current_position_qty = Decimal(
                str(state_data.get("current_position_qty", DECIMAL_ZERO))
            )
            self.state.unrealized_pnl_derivatives = Decimal(
                str(state_data.get("unrealized_pnl_derivatives", DECIMAL_ZERO))
            )

            # Convert Decimal strings back to Decimal objects in active_orders
            loaded_active_orders = state_data.get("active_orders", {})
            self.state.active_orders = {
                oid: {
                    k: Decimal(v)
                    if isinstance(v, str) and k in ["price", "qty", "cumExecQty"]
                    else v
                    for k, v in odata.items()
                }
                for oid, odata in loaded_active_orders.items()
            }

            self.state.last_order_management_time = state_data.get(
                "last_order_management_time", 0.0
            )
            self.state.last_ws_message_time = state_data.get(
                "last_ws_message_time", time.time()
            )
            self.state.last_status_report_time = state_data.get(
                "last_status_report_time", 0.0
            )
            self.state.last_health_check_time = state_data.get(
                "last_health_check_time", 0.0
            )
            self.state.price_candlestick_history.extend(
                [
                    (float(t), Decimal(str(h)), Decimal(str(l)), Decimal(str(c)))
                    for t, h, l, c in state_data.get("price_candlestick_history", [])
                ]
            )
            self.state.circuit_breaker_price_points.extend(
                [
                    (t, Decimal(str(p)))
                    for t, p in state_data.get("circuit_breaker_price_points", [])
                ]
            )
            self.state.is_paused = state_data.get("is_paused", False)
            self.state.pause_end_time = state_data.get("pause_end_time", 0.0)
            self.state.circuit_breaker_cooldown_end_time = state_data.get(
                "circuit_breaker_cooldown_end_time", 0.0
            )
            self.state.ws_reconnect_attempts_left = state_data.get(
                "ws_reconnect_attempts_left",
                self.global_config.system.ws_reconnect_attempts,
            )

            loaded_metrics_dict = state_data.get("metrics", {})
            if loaded_metrics_dict:
                metrics = TradeMetrics()
                for attr, value in loaded_metrics_dict.items():
                    if attr in [
                        "gross_profit",
                        "gross_loss",
                        "total_fees",
                        "realized_pnl",
                        "current_asset_holdings",
                        "average_entry_price",
                    ] and isinstance(value, str):
                        setattr(metrics, attr, Decimal(value))
                    elif attr == "last_pnl_update_timestamp":
                        if isinstance(value, str):
                            try:
                                setattr(metrics, attr, datetime.fromisoformat(value))
                            except ValueError:
                                setattr(metrics, attr, None)
                        else:
                            setattr(metrics, attr, value)
                    else:
                        setattr(metrics, attr, value)
                self.state.metrics = metrics

            self.state.daily_initial_capital = Decimal(
                str(state_data.get("daily_initial_capital", DECIMAL_ZERO))
            )
            if isinstance(state_data.get("daily_pnl_reset_date"), str):
                self.state.daily_pnl_reset_date = datetime.fromisoformat(
                    state_data["daily_pnl_reset_date"]
                )
            else:
                self.state.daily_pnl_reset_date = state_data.get("daily_pnl_reset_date")
            self.state.last_dry_run_price_update_time = float(
                state_data.get("last_dry_run_price_update_time", time.time())
            )

            self.logger.info(
                f"[{self.config.symbol}] Loaded state with {len(self.state.active_orders)} active orders and metrics: {self.state.metrics}"
            )
        else:
            self.logger.info(
                f"[{self.config.symbol}] No saved state found. Starting fresh."
            )

    # --- Market Data & Price Updates ---
    async def _update_mid_price(
        self, bids: List[List[Decimal]], asks: List[List[Decimal]]
    ) -> None:
        """Updates mid-price and related historical data from orderbook."""
        if not bids or not asks:
            self.logger.debug(
                f"[{self.config.symbol}] Orderbook empty or incomplete. Cannot update mid-price."
            )
            return

        best_bid = bids[0][0]
        best_ask = asks[0][0]
        new_mid_price = (best_bid + best_ask) / Decimal("2")
        current_time = time.time()

        if new_mid_price != self.state.mid_price:
            self.state.mid_price = new_mid_price
            self.state.circuit_breaker_price_points.append(
                (current_time, self.state.mid_price)
            )

            # Update candlestick history (timestamp, high, low, close)
            # This is primarily for ATR calculation. We use kline stream for more accurate candles.
            # This logic here is a fallback/supplement for immediate price changes.
            if self.state.price_candlestick_history:
                last_ts, last_high, last_low, _ = self.state.price_candlestick_history[
                    -1
                ]
                # If within a short interval, update the last candle's high/low
                if (
                    (current_time - last_ts)
                    < self.global_config.system.loop_interval_sec * 2
                ):  # Arbitrary small window
                    self.state.price_candlestick_history[-1] = (
                        current_time,
                        max(last_high, new_mid_price),
                        min(last_low, new_mid_price),
                        new_mid_price,
                    )
                else:
                    self.state.price_candlestick_history.append(
                        (current_time, new_mid_price, new_mid_price, new_mid_price)
                    )
            else:
                self.state.price_candlestick_history.append(
                    (current_time, new_mid_price, new_mid_price, new_mid_price)
                )

            # Exponential Moving Average (EMA) for smoothed mid-price
            alpha = Decimal(
                str(self.config.strategy.dynamic_spread.price_change_smoothing_factor)
            )
            if self.state.smoothed_mid_price == DECIMAL_ZERO:
                self.state.smoothed_mid_price = new_mid_price
            else:
                self.state.smoothed_mid_price = (alpha * new_mid_price) + (
                    (Decimal("1") - alpha) * self.state.smoothed_mid_price
                )

            self.logger.debug(
                f"[{self.config.symbol}] Mid-price updated to: {self.state.mid_price}, Smoothed: {self.state.smoothed_mid_price}"
            )

    async def _check_market_data_freshness(self, current_time: float) -> bool:
        """Checks if orderbook, trade, and kline data are fresh."""
        orderbook_stale = False
        if self.config.symbol not in self.ws_client.last_orderbook_update_time or (
            current_time - self.ws_client.last_orderbook_update_time[self.config.symbol]
            > self.config.strategy.market_data_stale_timeout_seconds
        ):
            orderbook_stale = True

        trades_stale = False
        if self.config.symbol not in self.ws_client.recent_trades_data or (
            current_time
            - self.ws_client.last_trades_update_time.get(self.config.symbol, 0)
            > self.config.strategy.market_data_stale_timeout_seconds
        ):
            trades_stale = True

        kline_stale = False
        if self.config.symbol not in self.ws_client.last_kline_update_time or (
            current_time
            - self.ws_client.last_kline_update_time.get(self.config.symbol, 0)
            > self.config.strategy.market_data_stale_timeout_seconds * 2
        ):  # Allow kline to be a bit older
            kline_stale = True

        if orderbook_stale or trades_stale or kline_stale:
            if self.config.trade_enabled:
                self.logger.warning(
                    f"{Colors.NEON_ORANGE}[{self.config.symbol}] Market data stale! "
                    f"Order book stale: {orderbook_stale}, Trades stale: {trades_stale}, Kline stale: {kline_stale}. "
                    f"Pausing quoting and cancelling orders.{Colors.RESET}"
                )
                await self._cancel_all_orders()  # Cancel orders if market data is stale
            return False
        return True

    # --- Initial Setup & Account Management ---
    async def _fetch_market_info(self) -> bool:
        """Fetches and updates symbol market information."""
        if self.global_config.trading_mode == "SIMULATION":
            self.config.price_precision = Decimal("0.00001")
            self.config.quantity_precision = Decimal("1")
            self.config.min_order_qty = Decimal("1")
            self.config.min_notional_value = Decimal(
                str(self.config.min_order_value_usd)
            )
            self.config.maker_fee_rate = Decimal("0.0002")
            self.config.taker_fee_rate = Decimal("0.0005")
            self.logger.info(
                f"[{self.config.symbol}] SIMULATION mode: Mock market info loaded: {self.config}"
            )
            return True

        info = await self.api_client.get_instruments_info(
            self.global_config.category, self.config.symbol
        )
        if not info:
            self.logger.critical(
                f"[{self.config.symbol}] Failed to retrieve instrument info from API. Check symbol and connectivity."
            )
            return False

        try:
            self.config.price_precision = Decimal(info["priceFilter"]["tickSize"])
            self.config.quantity_precision = Decimal(info["lotSizeFilter"]["qtyStep"])
            self.config.min_order_qty = Decimal(info["lotSizeFilter"]["minOrderQty"])

            # Use minNotionalValue if available, otherwise fallback to min_order_value_usd
            min_notional_from_api = Decimal(
                info["lotSizeFilter"].get("minNotionalValue", "0")
            )
            self.config.min_notional_value = max(
                min_notional_from_api, Decimal(str(self.config.min_order_value_usd))
            )

            # Bybit Fee Rates are typically for Taker/Maker from get_fee_rates or from instrument info
            self.config.maker_fee_rate = Decimal(
                info.get("makerFeeRate", "0.0002")
            )  # Default if not provided
            self.config.taker_fee_rate = Decimal(
                info.get("takerFeeRate", "0.0005")
            )  # Default if not provided

            self.last_symbol_info_refresh = time.time()
            self.logger.info(
                f"[{self.config.symbol}] Market info fetched: {self.config}"
            )
            return True
        except (KeyError, ValueError) as e:
            self.logger.critical(
                f"[{self.config.symbol}] Error parsing market info (missing key or invalid format): {e}. Full info: {info}",
                exc_info=True,
            )
            return False
        except Exception as e:
            self.logger.critical(
                f"[{self.config.symbol}] Unexpected error while parsing market info: {e}. Full info: {info}",
                exc_info=True,
            )
            return False

    async def _update_balance_and_position(self) -> bool:
        """Fetches and updates current balance and position details."""
        if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            if self.state.current_balance == DECIMAL_ZERO:
                self.state.current_balance = self.global_config.initial_dry_run_capital
                self.state.available_balance = self.state.current_balance
                self.logger.info(
                    f"[{self.config.symbol}] {self.global_config.trading_mode}: Initialized virtual balance: {self.state.current_balance} {self.global_config.main_quote_currency}"
                )
            self.state.current_position_qty = self.state.metrics.current_asset_holdings
            self.state.unrealized_pnl_derivatives = DECIMAL_ZERO
            return True

        # Fetch main quote currency balance
        account_type = (
            "UNIFIED"
            if self.global_config.category in ["linear", "inverse"]
            else "SPOT"
        )
        balance_data = await self.api_client.get_wallet_balance(account_type)
        if not balance_data:
            self.logger.error(f"[{self.config.symbol}] Failed to fetch wallet balance.")
            return False

        found_quote_balance = False
        for coin in balance_data.get("coin", []):
            if coin["coin"] == self.global_config.main_quote_currency:
                self.state.current_balance = Decimal(coin["walletBalance"])
                self.state.available_balance = Decimal(
                    coin.get("availableToWithdraw", coin["walletBalance"])
                )
                self.logger.debug(
                    f"[{self.config.symbol}] Balance: {self.state.current_balance} {self.global_config.main_quote_currency}, Available: {self.state.available_balance}"
                )
                await self.db_manager.log_balance_update(
                    self.global_config.main_quote_currency,
                    self.state.current_balance,
                    self.state.available_balance,
                )
                found_quote_balance = True
                break

        if not found_quote_balance:
            self.logger.warning(
                f"[{self.config.symbol}] Could not find balance for {self.global_config.main_quote_currency}. This might affect order sizing."
            )

        # Fetch position for derivatives
        if self.global_config.category in ["linear", "inverse"]:
            position_data = await self.api_client.get_position_info(
                self.global_config.category, self.config.symbol
            )
            if position_data and position_data.get("size"):
                self.state.current_position_qty = Decimal(position_data["size"]) * (
                    Decimal("1") if position_data["side"] == "Buy" else Decimal("-1")
                )
                self.state.unrealized_pnl_derivatives = Decimal(
                    position_data.get("unrealisedPnl", DECIMAL_ZERO)
                )
            else:
                self.state.current_position_qty = DECIMAL_ZERO
                self.state.unrealized_pnl_derivatives = DECIMAL_ZERO
        else:  # For spot, position is managed by TradeMetrics
            self.state.current_position_qty = self.state.metrics.current_asset_holdings
            self.state.unrealized_pnl_derivatives = (
                DECIMAL_ZERO  # Spot doesn't have exchange-reported UPNL
            )

        self.logger.info(
            f"[{self.config.symbol}] Updated Balance: {self.state.current_balance} {self.global_config.main_quote_currency}, Position: {self.state.current_position_qty} {self.config.base_currency}, UPNL (Deriv): {self.state.unrealized_pnl_derivatives:+.4f}"
        )
        return True

    async def _update_balance_from_wallet_ws(self, wallet_data: Dict[str, Any]):
        """Updates balance from WebSocket wallet stream."""
        for coin_info in wallet_data.get("coin", []):
            if coin_info.get("coin") == self.global_config.main_quote_currency:
                new_wallet_balance = Decimal(
                    coin_info.get("walletBalance", self.state.current_balance)
                )
                new_available_balance = Decimal(
                    coin_info.get("availableToWithdraw", self.state.available_balance)
                )

                if (
                    new_wallet_balance != self.state.current_balance
                    or new_available_balance != self.state.available_balance
                ):
                    self.state.current_balance = new_wallet_balance
                    self.state.available_balance = new_available_balance
                    self.logger.info(
                        f"[{self.config.symbol}] WALLET UPDATE (WS): Balance: {self.state.current_balance} {self.global_config.main_quote_currency}, Available: {self.state.available_balance}"
                    )
                    await self.db_manager.log_balance_update(
                        self.global_config.main_quote_currency,
                        self.state.current_balance,
                        self.state.available_balance,
                    )
                return

    async def _set_margin_mode_and_leverage(self) -> bool:
        """Sets margin mode and leverage for derivative symbols."""
        if self.global_config.category not in ["linear", "inverse"]:
            self.logger.debug(
                f"[{self.config.symbol}] Margin mode/leverage not applicable for {self.global_config.category}."
            )
            return True

        # Leverage
        if not await self.api_client.set_leverage(
            self.global_config.category,
            self.config.symbol,
            Decimal(str(self.config.leverage)),
        ):
            self.logger.error(
                f"[{self.config.symbol}] Failed to set leverage to {self.config.leverage}."
            )
            return False
        self.current_leverage = self.config.leverage
        self.logger.info(
            f"[{self.config.symbol}] Leverage set to {self.config.leverage}."
        )
        return True

    # --- WebSocket Message Processing (called by BybitWebSocketClient) ---
    async def _process_order_update(self, order_data: Dict[str, Any]):
        """Handles updates for specific orders."""
        order_id = order_data["orderId"]
        status = order_data["orderStatus"]
        cum_exec_qty = Decimal(order_data.get("cumExecQty", DECIMAL_ZERO))
        order_qty = Decimal(order_data.get("qty", DECIMAL_ZERO))

        self.logger.info(
            f"[{self.config.symbol}] Order {order_id} status update: {status} (OrderLink: {order_data.get('orderLinkId')}), CumExecQty: {cum_exec_qty}/{order_qty}"
        )
        await self.db_manager.log_order_event(self.config.symbol, order_data)

        if order_id in self.state.active_orders:
            existing_order = self.state.active_orders[order_id]
            existing_order["status"] = status
            existing_order["cumExecQty"] = cum_exec_qty

            if status == "Filled" or (
                status == "PartiallyFilled"
                and cum_exec_qty >= existing_order.get("qty", DECIMAL_ZERO)
            ):
                # If an order is fully filled or partially filled such that its cumExecQty reaches its original qty, remove it.
                self.logger.info(
                    f"[{self.config.symbol}] Order {order_id} fully filled or effectively filled. Removing from active orders."
                )
                del self.state.active_orders[order_id]
            elif status in ["Cancelled", "Rejected", "Deactivated", "Expired"]:
                self.logger.info(
                    f"[{self.config.symbol}] Order {order_id} removed from active orders due to status: {status}."
                )
                del self.state.active_orders[order_id]
        elif status in ["Filled", "PartiallyFilled"]:
            self.logger.warning(
                f"[{self.config.symbol}] Received fill/partial fill for untracked order {order_id}. Adding to state temporarily."
            )
            self.state.active_orders[order_id] = {
                "orderId": order_id,
                "side": order_data.get("side"),
                "price": Decimal(order_data.get("price", DECIMAL_ZERO)),
                "qty": order_qty,
                "cumExecQty": cum_exec_qty,
                "status": status,
                "orderLinkId": order_data.get("orderLinkId"),
                "symbol": order_data.get("symbol"),
                "reduceOnly": order_data.get("reduceOnly", False),
                "orderType": order_data.get("orderType", "Limit"),
                "timestamp": time.time()
                * 1000,  # Store current timestamp for stale order check
            }
            if status == "Filled":
                self.logger.info(
                    f"[{self.config.symbol}] Untracked order {order_id} fully filled. Removing after processing."
                )
                del self.state.active_orders[order_id]
        else:
            self.logger.debug(
                f"[{self.config.symbol}] Received update for untracked order {order_id} with status {status}. Ignoring."
            )

    async def _process_position_update(self, pos_data: Dict[str, Any]):
        """Handles updates to the bot's position."""
        new_pos_qty = Decimal(pos_data["size"]) * (
            Decimal("1") if pos_data["side"] == "Buy" else Decimal("-1")
        )
        if new_pos_qty != self.state.current_position_qty:
            self.state.current_position_qty = new_pos_qty
            self.logger.info(
                f"[{self.config.symbol}] POSITION UPDATE (WS): Position is now {self.state.current_position_qty} {self.config.base_currency}"
            )

        if (
            self.global_config.category in ["linear", "inverse"]
            and "unrealisedPnl" in pos_data
        ):
            self.state.unrealized_pnl_derivatives = Decimal(pos_data["unrealisedPnl"])
            self.logger.debug(
                f"[{self.config.symbol}] UNREALIZED PNL (WS): {self.state.unrealized_pnl_derivatives:+.4f} {self.global_config.main_quote_currency}"
            )

        # Trigger TP/SL update if position changes
        if (
            self.config.strategy.enable_auto_sl_tp
            and self.state.current_position_qty != DECIMAL_ZERO
        ):
            await self._update_take_profit_stop_loss()

    async def _process_execution_update(self, trade_data: Dict[str, Any]):
        """
        Handles individual trade executions (fills), updating PnL and metrics.
        This is typically for closing positions or partial fills.
        """
        exec_type = trade_data.get("execType")
        if exec_type not in [
            "Trade",
            "AdlTrade",
            "BustTrade",
            "Funding",
        ]:  # Filter out non-trade related executions
            self.logger.debug(
                f"[{self.config.symbol}] Skipping non-trade execution type: {exec_type}"
            )
            return

        side = trade_data.get("side", "Unknown")
        exec_qty = Decimal(trade_data.get("execQty", DECIMAL_ZERO))
        exec_price = Decimal(trade_data.get("execPrice", DECIMAL_ZERO))
        exec_fee = Decimal(trade_data.get("execFee", DECIMAL_ZERO))
        # closed_pnl is the realized PnL from this specific execution.
        closed_pnl = Decimal(trade_data.get("closedPnl", DECIMAL_ZERO))

        if exec_qty <= DECIMAL_ZERO or exec_price <= DECIMAL_ZERO:
            self.logger.warning(
                f"[{self.config.symbol}] Received invalid execution with zero quantity or price. Skipping. Data: {trade_data}"
            )
            return

        metrics = self.state.metrics

        # Update metrics based on trade side
        if side == "Buy":
            metrics.update_pnl_on_buy(exec_qty, exec_price)
            if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
                cost = (exec_qty * exec_price) + exec_fee
                if self.state.current_balance >= cost:
                    self.state.current_balance -= cost
                    self.state.available_balance = self.state.current_balance
                else:
                    self.logger.warning(
                        f"[{self.config.symbol}] DRY_RUN: Insufficient virtual balance to cover buy cost {cost}. Balance: {self.state.current_balance}. Skipping balance update."
                    )
            self.logger.info(
                f"[{self.config.symbol}] Order FILLED: BUY {exec_qty} @ {exec_price}, Fee: {exec_fee}. Holdings: {metrics.current_asset_holdings}, Avg Entry: {metrics.average_entry_price}"
            )
        elif side == "Sell":
            metrics.update_pnl_on_sell(exec_qty, exec_price)
            if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
                self.state.current_balance += (
                    exec_qty * exec_price
                ) - exec_fee  # Update virtual balance
                self.state.available_balance = self.state.current_balance
            self.logger.info(
                f"[{self.config.symbol}] Order FILLED: SELL {exec_qty} @ {exec_price}, Fee: {exec_fee}. Realized PnL from sale: {closed_pnl:+.4f}. Holdings: {metrics.current_asset_holdings}, Avg Entry: {metrics.average_entry_price}"
            )
        else:
            self.logger.warning(
                f"[{self.config.symbol}] Unknown side '{side}' for fill. Cannot update PnL metrics."
            )

        metrics.total_trades += 1
        metrics.total_fees += exec_fee
        if closed_pnl > DECIMAL_ZERO:
            metrics.gross_profit += closed_pnl
            metrics.wins += 1
        elif closed_pnl < DECIMAL_ZERO:
            metrics.gross_loss += abs(closed_pnl)
            metrics.losses += 1
        metrics.update_win_rate()

        await self.db_manager.log_trade_fill(self.config.symbol, trade_data, closed_pnl)
        await self._update_balance_and_position()  # Re-fetch balance to ensure accuracy

    # --- Trading Logic & Order Management ---
    async def _manage_orders(self):
        """Calculates target prices and manages open orders."""
        if (
            self.state.smoothed_mid_price == DECIMAL_ZERO
            or not self.config.price_precision
        ):
            self.logger.warning(
                f"[{self.config.symbol}] Smoothed mid-price or market info not available, skipping order management."
            )
            return

        # Calculate dynamic spread
        spread_pct = await self._calculate_dynamic_spread()

        # Calculate inventory skew
        skew_factor = self._calculate_inventory_skew(
            self.state.smoothed_mid_price, self.state.current_position_qty
        )
        skewed_mid_price = self.state.smoothed_mid_price * (Decimal("1") + skew_factor)

        # Base target prices
        base_target_bid_price = skewed_mid_price * (Decimal("1") - spread_pct)
        base_target_ask_price = skewed_mid_price * (Decimal("1") + spread_pct)

        # Enforce minimum profit spread
        base_target_bid_price, base_target_ask_price = self._enforce_min_profit_spread(
            self.state.smoothed_mid_price, base_target_bid_price, base_target_ask_price
        )

        await self._reconcile_and_place_orders(
            base_target_bid_price, base_target_ask_price
        )

    async def _calculate_dynamic_spread(self) -> Decimal:
        """Calculates a dynamic spread based on market volatility (ATR)."""
        ds_config = self.config.strategy.dynamic_spread
        current_time = time.time()

        if not ds_config.enabled:
            return Decimal(str(self.config.strategy.base_spread_pct))

        # Check if ATR needs to be updated
        if (
            current_time - self.last_atr_update_time
        ) > ds_config.atr_update_interval_sec:
            self.cached_atr = await self._calculate_atr_from_kline(self.state.mid_price)
            self.last_atr_update_time = current_time

        if self.state.mid_price <= DECIMAL_ZERO:
            self.logger.warning(
                f"[{self.config.symbol}] Mid-price is zero, cannot calculate ATR-based spread. Using base spread."
            )
            return Decimal(str(self.config.strategy.base_spread_pct))

        volatility_pct = (
            (self.cached_atr / self.state.mid_price)
            if self.state.mid_price > DECIMAL_ZERO
            else DECIMAL_ZERO
        )

        dynamic_adjustment = volatility_pct * Decimal(
            str(ds_config.volatility_multiplier)
        )

        # Clamp dynamic spread between min and max
        final_spread = max(
            Decimal(str(ds_config.min_spread_pct)),
            min(
                Decimal(str(ds_config.max_spread_pct)),
                Decimal(str(self.config.strategy.base_spread_pct)) + dynamic_adjustment,
            ),
        )
        self.logger.debug(
            f"[{self.config.symbol}] ATR-based Spread: {final_spread * 100:.4f}% (ATR:{self.cached_atr:.6f}, Volatility:{volatility_pct:.6f})"
        )
        return final_spread

    async def _calculate_atr_from_kline(self, current_mid_price: Decimal) -> Decimal:
        """Fetches kline data and calculates ATR."""
        if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            # In dry run, we use the internal price_candlestick_history
            if (
                len(self.state.price_candlestick_history) < 15
            ):  # Need enough data points for 14-period ATR
                self.logger.debug(
                    f"[{self.config.symbol}] Not enough internal OHLCV data for ATR in dry run ({len(self.state.price_candlestick_history)}). Returning cached or zero."
                )
                return (
                    self.cached_atr if self.cached_atr > DECIMAL_ZERO else DECIMAL_ZERO
                )

            # Convert deque to pandas DataFrame
            df = pd.DataFrame(
                list(self.state.price_candlestick_history),
                columns=["timestamp", "high", "low", "close"],
            )
        else:
            try:
                ohlcv_data = await self.api_client.get_kline(
                    self.global_config.category,
                    self.config.symbol,
                    self.config.strategy.kline_interval,
                    20,  # Need enough data for ATR (e.g., 14 periods)
                )
                if (
                    not ohlcv_data or len(ohlcv_data) < 15
                ):  # Ensure enough data points for 14-period ATR
                    self.logger.warning(
                        f"[{self.config.symbol}] Not enough OHLCV data for ATR calculation ({len(ohlcv_data)}). Using cached ATR or zero."
                    )
                    return (
                        self.cached_atr
                        if self.cached_atr > DECIMAL_ZERO
                        else DECIMAL_ZERO
                    )

                # Convert to DataFrame and then to Decimal
                df = pd.DataFrame(
                    ohlcv_data,
                    columns=["timestamp", "open", "high", "low", "close", "volume"],
                )
                df = df.apply(lambda x: pd.to_numeric(x, errors="ignore"))
            except Exception as e:
                self.logger.error(
                    f"{Colors.NEON_RED}[{self.config.symbol}] Error fetching kline data for ATR: {e}{Colors.RESET}",
                    exc_info=True,
                )
                return (
                    self.cached_atr if self.cached_atr > DECIMAL_ZERO else DECIMAL_ZERO
                )

        # Ensure columns are Decimal type for calculations
        df["high"] = df["high"].apply(Decimal)
        df["low"] = df["low"].apply(Decimal)
        df["close"] = df["close"].apply(Decimal)

        # Ensure all necessary columns for atr calculation are present
        if (
            "high" not in df.columns
            or "low" not in df.columns
            or "close" not in df.columns
        ):
            self.logger.warning(
                f"[{self.config.symbol}] Missing columns for ATR calculation in OHLCV data."
            )
            return self.cached_atr if self.cached_atr > DECIMAL_ZERO else DECIMAL_ZERO

        # Use pandas_ta.atr if available, otherwise fallback to local implementation
        if ta is not None:
            atr_series = ta.atr(
                df["high"], df["low"], df["close"], length=14
            )  # Default ATR length
            atr_val = atr_series.iloc[-1]  # Get the latest ATR value
        else:
            atr_val = atr(df["high"], df["low"], df["close"], length=14).iloc[
                -1
            ]  # Use local atr

        if pd.isna(atr_val) or atr_val <= DECIMAL_ZERO:
            self.logger.warning(
                f"[{self.config.symbol}] ATR calculation resulted in NaN or non-positive value. Using cached ATR or zero."
            )
            return self.cached_atr if self.cached_atr > DECIMAL_ZERO else DECIMAL_ZERO

        self.logger.debug(f"[{self.config.symbol}] Calculated ATR: {atr_val:.8f}")
        return Decimal(str(atr_val))

    def _calculate_inventory_skew(
        self, mid_price: Decimal, pos_qty: Decimal
    ) -> Decimal:
        """Calculates a skew factor based on current inventory."""
        inv_config = self.config.strategy.inventory_skew
        if (
            not inv_config.enabled
            or Decimal(str(self.config.max_net_exposure_usd)) <= DECIMAL_ZERO
            or mid_price <= DECIMAL_ZERO
        ):
            return DECIMAL_ZERO

        current_inventory_value = pos_qty * mid_price
        max_exposure_for_ratio = Decimal(
            str(self.config.max_net_exposure_usd)
        ) * Decimal(str(inv_config.max_inventory_ratio))

        if max_exposure_for_ratio <= DECIMAL_ZERO:
            return DECIMAL_ZERO

        # Normalize inventory to a ratio between -1 and 1
        # Positive ratio means long position, negative means short
        inventory_ratio = current_inventory_value / max_exposure_for_ratio
        inventory_ratio = max(Decimal("-1.0"), min(Decimal("1.0"), inventory_ratio))

        # Skew factor pushes prices in the opposite direction of inventory
        # If long (positive ratio), skew is negative, pushing bid lower and ask higher
        # If short (negative ratio), skew is positive, pushing bid higher and ask lower
        skew_factor = -inventory_ratio * Decimal(str(inv_config.skew_intensity))

        if abs(skew_factor) > Decimal("1e-6"):
            self.logger.debug(
                f"[{self.config.symbol}] Inventory skew active. Position Value: {current_inventory_value:.2f} {self.config.quote_currency}, Ratio: {inventory_ratio:.3f}, Skew: {skew_factor:.6f}"
            )
        return skew_factor

    def _enforce_min_profit_spread(
        self, mid_price: Decimal, bid_p: Decimal, ask_p: Decimal
    ) -> Tuple[Decimal, Decimal]:
        """Ensures the spread is wide enough to cover fees and desired profit."""
        if self.config.maker_fee_rate is None or self.config.taker_fee_rate is None:
            self.logger.warning(
                f"[{self.config.symbol}] Fee rates not set. Cannot enforce minimum profit spread."
            )
            return bid_p, ask_p

        # For market making, we are typically makers on both sides.
        # However, to be conservative, we can assume taker fees for the "profit" side.
        # Minimum gross spread needs to cover fees on both legs (buy and sell) plus desired profit.
        # Assuming maker fee for initial order, taker fee for closing/filling opposite.
        # Simplified: two maker fees for round trip, plus min profit.
        estimated_fee_per_side_pct = self.config.maker_fee_rate
        min_gross_spread_pct = Decimal(
            str(self.config.strategy.min_profit_spread_after_fees_pct)
        ) + (estimated_fee_per_side_pct * Decimal("2"))
        min_spread_val = mid_price * min_gross_spread_pct

        if ask_p <= bid_p or (ask_p - bid_p) < min_spread_val:
            self.logger.debug(
                f"[{self.config.symbol}] Adjusting spread. Original Bid: {bid_p}, Ask: {ask_p}, Mid: {mid_price}, Current Spread: {ask_p - bid_p:.6f}, Min Spread: {min_spread_val:.6f}"
            )
            half_min_spread = (min_spread_val / Decimal("2")).quantize(
                self.config.price_precision, rounding=ROUND_DOWN
            )
            bid_p = (mid_price - half_min_spread).quantize(
                self.config.price_precision, rounding=ROUND_DOWN
            )
            ask_p = (mid_price + half_min_spread).quantize(
                self.config.price_precision, rounding=ROUND_DOWN
            )
            self.logger.debug(
                f"[{self.config.symbol}] Adjusted to Bid: {bid_p}, Ask: {ask_p}"
            )
        return bid_p, ask_p

    async def _reconcile_and_place_orders(
        self, base_target_bid: Decimal, base_target_ask: Decimal
    ):
        """Cancels stale/duplicate orders and places new ones according to strategy, including layers."""
        if (
            self.config.price_precision is None
            or self.config.quantity_precision is None
        ):
            self.logger.error(
                f"[{self.config.symbol}] Price or quantity precision not set. Cannot place orders."
            )
            return

        orders_to_cancel = []
        # Group active orders by side and layer for easier management
        current_active_orders_by_side_layer: Dict[
            str, Dict[str, List[Tuple[str, Dict[str, Any]]]]
        ] = {"Buy": defaultdict(list), "Sell": defaultdict(list)}

        # Identify stale or duplicate orders
        for order_id, order_data in list(self.state.active_orders.items()):
            if order_data.get("symbol") != self.config.symbol:
                self.logger.warning(
                    f"[{self.config.symbol}] Found untracked symbol order {order_id} in active_orders. Cancelling."
                )
                orders_to_cancel.append((order_id, order_data.get("orderLinkId")))
                continue

            # Check for terminal statuses
            if order_data["status"] in [
                "Filled",
                "Cancelled",
                "Rejected",
                "Deactivated",
                "Expired",
            ]:
                if order_data.get("cumExecQty", DECIMAL_ZERO) >= order_data.get(
                    "qty", DECIMAL_ZERO
                ):  # Fully filled or effectively filled
                    self.logger.debug(
                        f"[{self.config.symbol}] Removing fully processed order {order_id} from active orders."
                    )
                    # Order will be removed from state.active_orders by the _process_order_update
                else:  # Partially filled but inactive or needs re-evaluation
                    self.logger.debug(
                        f"[{self.config.symbol}] Removing partially filled but inactive order {order_id} from active orders."
                    )
                continue  # Skip further processing for terminal orders

            # Check for price staleness based on order layer's cancel_threshold_pct
            is_stale = False
            stale_threshold = Decimal(
                str(self.config.strategy.order_stale_threshold_pct)
            )

            # Determine which layer this order belongs to (by parsing orderLinkId)
            order_link_id = order_data.get("orderLinkId", "")
            layer_tag = "base"
            for i in range(len(self.config.strategy.order_layers)):
                if f"layer_{i}" in order_link_id:
                    layer_tag = f"layer_{i}"
                    break

            # Calculate target prices for this layer
            layer_config = next(
                (
                    l
                    for l in self.config.strategy.order_layers
                    if f"layer_{self.config.strategy.order_layers.index(l)}"
                    == layer_tag
                ),
                self.config.strategy.order_layers[0],
            )

            layer_bid_price_target = base_target_bid * (
                Decimal("1") - Decimal(str(layer_config.spread_offset_pct))
            )
            layer_ask_price_target = base_target_ask * (
                Decimal("1") + Decimal(str(layer_config.spread_offset_pct))
            )

            if order_data["side"] == "Buy":
                if abs(order_data["price"] - layer_bid_price_target) > (
                    order_data["price"] * stale_threshold
                ):
                    is_stale = True
                current_active_orders_by_side_layer["Buy"][layer_tag].append(
                    (order_id, order_data)
                )
            else:  # Sell order
                if abs(order_data["price"] - layer_ask_price_target) > (
                    order_data["price"] * stale_threshold
                ):
                    is_stale = True
                current_active_orders_by_side_layer["Sell"][layer_tag].append(
                    (order_id, order_data)
                )

            if is_stale:  # Mark stale orders for cancellation
                orders_to_cancel.append((order_id, order_data.get("orderLinkId")))

        # Cancel identified orders
        for oid, olid in orders_to_cancel:
            order_info = self.state.active_orders.get(oid, {})
            self.logger.info(
                f"[{self.config.symbol}] Cancelling stale/duplicate order {oid} (Side: {order_info.get('side')}, Price: {order_info.get('price')}). Target Bid: {base_target_bid}, Target Ask: {base_target_ask}"
            )
            await self._cancel_order(oid, olid)

        # Place new orders if needed, considering layers
        current_outstanding_orders = len(self.state.active_orders)

        for i, layer in enumerate(self.config.strategy.order_layers):
            if (
                current_outstanding_orders
                >= self.config.strategy.max_outstanding_orders * 2
            ):  # Max outstanding orders for both sides
                self.logger.debug(
                    f"[{self.config.symbol}] Max outstanding orders ({self.config.strategy.max_outstanding_orders * 2}) reached. Skipping further layer placements."
                )
                break

            layer_tag = f"layer_{i}"

            # Calculate layered prices
            layer_bid_price = base_target_bid * (
                Decimal("1") - Decimal(str(layer.spread_offset_pct))
            )
            layer_ask_price = base_target_ask * (
                Decimal("1") + Decimal(str(layer.spread_offset_pct))
            )

            # Ensure layered orders don't cross
            if layer_bid_price >= layer_ask_price:
                self.logger.warning(
                    f"[{self.config.symbol}] Layer {i} prices crossed ({layer_bid_price} >= {layer_ask_price}). Skipping this layer."
                )
                continue

            # Place buy order for layer if no active order for this layer exists
            if not current_active_orders_by_side_layer["Buy"][layer_tag]:
                buy_qty = await self._calculate_order_size(
                    "Buy", layer_bid_price, layer.quantity_multiplier
                )
                if buy_qty > DECIMAL_ZERO:
                    await self._place_limit_order(
                        "Buy", layer_bid_price, buy_qty, layer_tag
                    )
                    current_outstanding_orders += 1
                else:
                    self.logger.debug(
                        f"[{self.config.symbol}] Calculated buy quantity for layer {i} is zero or too small, skipping bid order placement."
                    )

            # Place sell order for layer if no active order for this layer exists
            if (
                current_outstanding_orders
                < self.config.strategy.max_outstanding_orders * 2
                and not current_active_orders_by_side_layer["Sell"][layer_tag]
            ):
                sell_qty = await self._calculate_order_size(
                    "Sell", layer_ask_price, layer.quantity_multiplier
                )
                if sell_qty > DECIMAL_ZERO:
                    await self._place_limit_order(
                        "Sell", layer_ask_price, sell_qty, layer_tag
                    )
                    current_outstanding_orders += 1
                else:
                    self.logger.debug(
                        f"[{self.config.symbol}] Calculated sell quantity for layer {i} is zero or too small, skipping ask order placement."
                    )

    async def _calculate_order_size(
        self, side: str, price: Decimal, quantity_multiplier: float = 1.0
    ) -> Decimal:
        """Calculates the optimal order quantity based on balance, exposure, and min/max limits."""
        if self.config.min_order_qty is None or self.config.min_notional_value is None:
            self.logger.error(
                f"[{self.config.symbol}] Market info (min_order_qty/min_notional_value) not set. Cannot calculate order size."
            )
            return DECIMAL_ZERO

        capital = (
            self.state.available_balance
            if self.global_config.category == "spot"
            else self.state.current_balance
        )
        metrics_pos_qty = (
            self.state.metrics.current_asset_holdings
        )  # Use for spot, for derivatives current_position_qty is from exchange

        if capital <= DECIMAL_ZERO or price <= DECIMAL_ZERO:
            self.logger.debug(
                f"[{self.config.symbol}] Insufficient capital ({capital}), zero price ({price}). Order size 0."
            )
            return DECIMAL_ZERO

        effective_capital = (
            capital * Decimal(str(self.config.leverage))
            if self.global_config.category in ["linear", "inverse"]
            else capital
        )

        # Base quantity from percentage of available capital
        base_order_value = effective_capital * Decimal(
            str(self.config.strategy.base_order_size_pct_of_balance)
        )
        qty_from_base_pct = base_order_value / price

        # Max quantity from overall max order size percentage
        max_order_value_abs = effective_capital * Decimal(
            str(self.config.max_order_size_pct)
        )
        qty_from_max_pct = max_order_value_abs / price

        target_qty = min(qty_from_base_pct, qty_from_max_pct) * Decimal(
            str(quantity_multiplier)
        )

        current_net_pos = (
            self.state.current_position_qty
            if self.global_config.category in ["linear", "inverse"]
            else metrics_pos_qty
        )

        if (
            self.config.strategy.inventory_skew.enabled
            and Decimal(str(self.config.max_net_exposure_usd)) > DECIMAL_ZERO
        ):
            current_mid_price = self.state.mid_price
            if current_mid_price <= DECIMAL_ZERO:
                self.logger.warning(
                    f"[{self.config.symbol}] Mid-price is zero, cannot calculate max net exposure. Skipping exposure check."
                )
                return DECIMAL_ZERO

            max_allowed_pos_qty_abs = (
                Decimal(str(self.config.max_net_exposure_usd)) / current_mid_price
            )

            if side == "Buy":
                qty_to_reach_max_long = max_allowed_pos_qty_abs - current_net_pos
                if qty_to_reach_max_long <= DECIMAL_ZERO:
                    self.logger.debug(
                        f"[{self.config.symbol}] Cannot place buy order: Current position {current_net_pos} already at or above max long exposure ({max_allowed_pos_qty_abs})."
                    )
                    return DECIMAL_ZERO
                target_qty = min(target_qty, qty_to_reach_max_long)
            else:  # Sell order
                if (
                    current_net_pos > DECIMAL_ZERO
                ):  # If currently long, sell up to current holdings
                    target_qty = min(target_qty, current_net_pos)
                    self.logger.debug(
                        f"[{self.config.symbol}] Capping sell order quantity at current holdings: {target_qty}"
                    )
                else:  # If currently short or flat, consider max short exposure
                    qty_to_reach_max_short = abs(
                        -max_allowed_pos_qty_abs - current_net_pos
                    )  # How much more short can we go
                    if (
                        qty_to_reach_max_short <= DECIMAL_ZERO
                    ):  # Already at max short or beyond
                        self.logger.debug(
                            f"[{self.config.symbol}] Cannot place sell order: Current position {current_net_pos} already at or below max short exposure ({-max_allowed_pos_qty_abs})."
                        )
                        return DECIMAL_ZERO
                    target_qty = min(target_qty, qty_to_reach_max_short)

        if target_qty <= DECIMAL_ZERO:
            self.logger.debug(
                f"[{self.config.symbol}] Calculated target quantity is zero or negative after exposure adjustments. Order size 0."
            )
            return DECIMAL_ZERO

        qty = self.config.format_quantity(target_qty)

        if qty < self.config.min_order_qty:
            self.logger.debug(
                f"[{self.config.symbol}] Calculated quantity {qty} is less than min_order_qty {self.config.min_order_qty}. Order size 0."
            )
            return DECIMAL_ZERO

        order_notional_value = qty * price
        if order_notional_value < self.config.min_notional_value:
            self.logger.debug(
                f"[{self.config.symbol}] Calculated notional value {order_notional_value:.2f} is less than min_notional_value {self.config.min_notional_value:.2f}. Order size 0."
            )
            return DECIMAL_ZERO

        self.logger.debug(
            f"[{self.config.symbol}] Calculated {side} order size: {qty} {self.config.base_currency} (Notional: {order_notional_value:.2f} {self.config.quote_currency})"
        )
        return qty

    async def _place_limit_order(
        self, side: str, price: Decimal, quantity: Decimal, layer_tag: str = "base"
    ):
        """Places a single limit order."""
        if (
            self.config.price_precision is None
            or self.config.quantity_precision is None
            or self.config.min_notional_value is None
        ):
            self.logger.error(
                f"[{self.config.symbol}] Market info (precisions/min_notional) not set. Cannot place order."
            )
            raise OrderPlacementError(
                "Market information is not available for order placement."
            )

        qty_f, price_f = (
            self.config.format_quantity(quantity),
            self.config.format_price(price),
        )
        if qty_f <= DECIMAL_ZERO or price_f <= DECIMAL_ZERO:
            self.logger.warning(
                f"[{self.config.symbol}] Attempted to place order with zero or negative quantity/price: Qty={qty_f}, Price={price_f}. Skipping."
            )
            return

        order_notional_value = qty_f * price_f
        if order_notional_value < self.config.min_notional_value:
            self.logger.warning(
                f"[{self.config.symbol}] Calculated order notional value {order_notional_value:.2f} is below minimum {self.config.min_notional_value:.2f}. Skipping order placement."
            )
            return

        time_in_force = "PostOnly"  # Always use PostOnly for market making
        # Bybit expects symbol without / or : for order placement
        bybit_symbol = self.config.symbol.replace("/", "").replace(":", "")
        order_link_id = (
            f"mm_{bybit_symbol}_{side}_{layer_tag}_{int(time.time() * 1000)}"
        )

        params = {
            "category": self.global_config.category,
            "symbol": bybit_symbol,
            "side": side,
            "orderType": "Limit",
            "qty": str(qty_f),
            "price": str(price_f),
            "timeInForce": time_in_force,
            "orderLinkId": order_link_id,
            "isLeverage": 1
            if self.global_config.category in ["linear", "inverse"]
            else 0,  # Required for some categories
            "triggerDirection": 1
            if side == "Buy"
            else 2,  # For TP/SL if used, but not strictly needed for limit order
        }

        # ReduceOnly for derivatives
        if self.global_config.category in ["linear", "inverse"]:
            current_position = self.state.current_position_qty
            if (side == "Sell" and current_position > DECIMAL_ZERO) or (
                side == "Buy" and current_position < DECIMAL_ZERO
            ):
                params["reduceOnly"] = True
                self.logger.debug(
                    f"[{self.config.symbol}] Setting reduceOnly=True for {side} order (current position: {current_position})."
                )

        if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            oid = f"DRY_{bybit_symbol}_{side}_{layer_tag}_{int(time.time() * 1000)}"
            self.logger.info(
                f"[{self.config.symbol}] {self.global_config.trading_mode}: Would place {side} order: ID={oid}, Qty={qty_f}, Price={price_f}"
            )
            self.state.active_orders[oid] = {
                "orderId": oid,
                "side": side,
                "price": price_f,
                "qty": qty_f,
                "cumExecQty": DECIMAL_ZERO,
                "status": "New",
                "orderLinkId": order_link_id,
                "symbol": self.config.symbol,
                "reduceOnly": params.get("reduceOnly", False),
                "orderType": "Limit",
                "timestamp": time.time() * 1000,  # Store creation timestamp
            }
            await self.db_manager.log_order_event(
                self.config.symbol,
                {**params, "orderId": oid, "orderStatus": "New", "cumExecQty": "0"},
                f"{self.global_config.trading_mode} Order placed",
            )
            return

        result = await self.api_client.place_order(params)
        if result and result.get("orderId"):
            oid = result["orderId"]
            self.logger.info(
                f"[{self.config.symbol}] Placed {side} order: ID={oid}, Price={price_f}, Qty={qty_f}"
            )
            self.state.active_orders[oid] = {
                "orderId": oid,
                "side": side,
                "price": price_f,
                "qty": qty_f,
                "cumExecQty": DECIMAL_ZERO,
                "status": "New",
                "orderLinkId": order_link_id,
                "symbol": self.config.symbol,
                "reduceOnly": params.get("reduceOnly", False),
                "orderType": "Limit",
                "timestamp": time.time() * 1000,  # Store creation timestamp
            }
            await self.db_manager.log_order_event(
                self.config.symbol,
                {**params, "orderId": oid, "orderStatus": "New", "cumExecQty": "0"},
                "Order placed",
            )
        else:
            self.logger.error(
                f"[{self.config.symbol}] Failed to place {side} order after retries. Params: {params}"
            )
            raise OrderPlacementError(
                f"Failed to place {side} order for {self.config.symbol}."
            )

    async def _cancel_order(self, order_id: str, order_link_id: str | None = None):
        """Cancels a specific order."""
        self.logger.info(
            f"[{self.config.symbol}] Attempting to cancel order {order_id} (OrderLink: {order_link_id})..."
        )
        if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            self.logger.info(
                f"[{self.config.symbol}] {self.global_config.trading_mode}: Would cancel order {order_id}."
            )
            if order_id in self.state.active_orders:
                del self.state.active_orders[order_id]
            return

        try:
            # Bybit expects symbol without / or : for order placement
            bybit_symbol = self.config.symbol.replace("/", "").replace(":", "")
            if await self.api_client.cancel_order(
                self.global_config.category, bybit_symbol, order_id, order_link_id
            ):
                self.logger.info(
                    f"[{self.config.symbol}] Order {order_id} cancelled successfully."
                )
                if order_id in self.state.active_orders:
                    del self.state.active_orders[order_id]
            else:
                self.logger.error(
                    f"[{self.config.symbol}] Failed to cancel order {order_id} via API after retries."
                )
        except BybitAPIError as e:
            if e.ret_code == 30003:  # Order does not exist
                self.logger.warning(
                    f"[{self.config.symbol}] Order {order_id} already cancelled or does not exist on exchange. Removing from local state."
                )
                if order_id in self.state.active_orders:
                    del self.state.active_orders[order_id]
            else:
                self.logger.error(
                    f"[{self.config.symbol}] Error during cancellation of order {order_id}: {e}",
                    exc_info=True,
                )
        except Exception as e:
            self.logger.error(
                f"[{self.config.symbol}] Unexpected error during cancellation of order {order_id}: {e}",
                exc_info=True,
            )

    async def _cancel_all_orders(self):
        """Cancels all open orders for the symbol."""
        self.logger.info(f"[{self.config.symbol}] Canceling all open orders...")
        if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            self.logger.info(
                f"[{self.config.symbol}] {self.global_config.trading_mode}: Would cancel all open orders."
            )
        else:
            try:
                # Bybit expects symbol without / or : for order placement
                bybit_symbol = self.config.symbol.replace("/", "").replace(":", "")
                if await self.api_client.cancel_all_orders(
                    self.global_config.category, bybit_symbol
                ):
                    self.logger.info(
                        f"[{self.config.symbol}] All orders cancelled successfully."
                    )
                else:
                    self.logger.error(
                        f"[{self.config.symbol}] Failed to cancel all orders via API after retries."
                    )
            except Exception as e:
                self.logger.error(
                    f"[{self.config.symbol}] Error during cancellation of all orders: {e}",
                    exc_info=True,
                )

        self.state.active_orders.clear()

    async def _reconcile_orders_on_startup(self):
        """Reconciles local active orders with exchange orders on startup."""
        if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            self.logger.info(
                f"[{self.config.symbol}] {self.global_config.trading_mode} mode: Skipping order reconciliation (loaded from state)."
            )
            return  # State was already loaded in initialize()

        self.logger.info(
            f"[{self.config.symbol}] Reconciling active orders with exchange..."
        )
        try:
            # Bybit expects symbol without / or : for order placement
            bybit_symbol = self.config.symbol.replace("/", "").replace(":", "")
            exchange_orders = {
                o["orderId"]: o
                for o in await self.api_client.get_open_orders(
                    self.global_config.category, bybit_symbol
                )
            }
        except Exception as e:
            self.logger.error(
                f"[{self.config.symbol}] Failed to fetch open orders from exchange during reconciliation: {e}. Proceeding with local state only.",
                exc_info=True,
            )
            exchange_orders = {}

        local_ids = set(self.state.active_orders.keys())
        exchange_ids = set(exchange_orders.keys())

        for oid in local_ids - exchange_ids:
            self.logger.warning(
                f"[{self.config.symbol}] Local order {oid} not found on exchange. Removing from local state."
            )
            del self.state.active_orders[oid]

        for oid in exchange_ids - local_ids:
            o = exchange_orders[oid]
            self.logger.warning(
                f"[{self.config.symbol}] Exchange order {oid} ({o['side']} {o['qty']} @ {o['price']}) not in local state. Adding."
            )
            self.state.active_orders[oid] = {
                "orderId": oid,
                "side": o["side"],
                "price": Decimal(o["price"]),
                "qty": Decimal(o["qty"]),
                "cumExecQty": Decimal(o.get("cumExecQty", DECIMAL_ZERO)),
                "status": o["orderStatus"],
                "orderLinkId": o.get("orderLinkId"),
                "symbol": o.get("symbol"),
                "reduceOnly": o.get("reduceOnly", False),
                "orderType": o.get("orderType", "Limit"),
                "timestamp": time.time()
                * 1000,  # Store current timestamp for stale order check
            }

        for oid in local_ids.intersection(exchange_ids):
            local_order = self.state.active_orders[oid]
            exchange_order = exchange_orders[oid]

            # Update status and cumExecQty from exchange
            if local_order["status"] != exchange_order[
                "orderStatus"
            ] or local_order.get("cumExecQty", DECIMAL_ZERO) != Decimal(
                exchange_order.get("cumExecQty", DECIMAL_ZERO)
            ):
                self.logger.info(
                    f"[{self.config.symbol}] Order {oid} status/cumExecQty mismatch. Updating from {local_order['status']}/{local_order.get('cumExecQty', DECIMAL_ZERO)} to {exchange_order['orderStatus']}/{exchange_order.get('cumExecQty', DECIMAL_ZERO)}."
                )
                local_order["status"] = exchange_order["orderStatus"]
                local_order["cumExecQty"] = Decimal(
                    exchange_order.get("cumExecQty", DECIMAL_ZERO)
                )

        self.logger.info(
            f"[{self.config.symbol}] Order reconciliation complete. {len(self.state.active_orders)} active orders after reconciliation."
        )

    async def _check_and_handle_stale_orders(self, current_time: float):
        """Checks for and cancels orders that have been open for too long."""
        orders_to_cancel = []
        for order_id, order_info in list(self.state.active_orders.items()):
            # Assuming 'timestamp' in order_info is the placement time in milliseconds
            placement_time_seconds = (
                order_info.get("timestamp", current_time * 1000) / 1000
            )
            if (
                current_time - placement_time_seconds
            ) > self.config.strategy.stale_order_max_age_seconds:
                orders_to_cancel.append((order_id, order_info.get("orderLinkId")))

        for exchange_id, client_order_id in orders_to_cancel:
            self.logger.warning(
                f"[{self.config.symbol}] Order {exchange_id} is stale (open for "
                f"> {self.config.strategy.stale_order_max_age_seconds} seconds). Cancelling."
            )
            await self._cancel_order(exchange_id, client_order_id)

    async def _update_take_profit_stop_loss(self):
        """Sets or updates Take-Profit and Stop-Loss for current position."""
        if (
            not self.config.strategy.enable_auto_sl_tp
            or self.state.current_position_qty == DECIMAL_ZERO
        ):
            return

        tp_price = DECIMAL_ZERO
        sl_price = DECIMAL_ZERO

        # Use average entry price from metrics for TP/SL calculation
        entry_price = self.state.metrics.average_entry_price

        if entry_price == DECIMAL_ZERO:
            self.logger.warning(
                f"[{self.config.symbol}] Entry price is zero, cannot set TP/SL."
            )
            return

        if self.state.current_position_qty > DECIMAL_ZERO:  # Long position
            tp_price = entry_price * (
                Decimal("1") + Decimal(str(self.config.strategy.take_profit_target_pct))
            )
            sl_price = entry_price * (
                Decimal("1") - Decimal(str(self.config.strategy.stop_loss_trigger_pct))
            )
        elif self.state.current_position_qty < DECIMAL_ZERO:  # Short position
            tp_price = entry_price * (
                Decimal("1") - Decimal(str(self.config.strategy.take_profit_target_pct))
            )
            sl_price = entry_price * (
                Decimal("1") + Decimal(str(self.config.strategy.stop_loss_trigger_pct))
            )

        tp_price = self.config.format_price(tp_price)
        sl_price = self.config.format_price(sl_price)

        try:
            # Bybit expects symbol without / or : for order placement
            bybit_symbol = self.config.symbol.replace("/", "").replace(":", "")
            if await self.api_client.set_trading_stop(
                self.global_config.category, bybit_symbol, sl_price, tp_price
            ):
                self.logger.info(
                    f"{Colors.NEON_GREEN}[{self.config.symbol}] Set TP: {tp_price:.{self.config.price_precision.as_tuple()._exp if self.config.price_precision else 8}f}, "
                    f"SL: {sl_price:.{self.config.price_precision.as_tuple()._exp if self.config.price_precision else 8}f} for current position (Entry: {entry_price}).{Colors.RESET}"
                )
                termux_notify(
                    f"{self.config.symbol}: TP: {tp_price:.4f}, SL: {sl_price:.4f}",
                    title="TP/SL Updated",
                )
        except Exception as e:
            self.logger.error(
                f"{Colors.NEON_RED}[{self.config.symbol}] Error setting TP/SL: {e}{Colors.RESET}",
                exc_info=True,
            )
            termux_notify(f"{self.config.symbol}: Failed to set TP/SL!", is_error=True)

    # --- Circuit Breakers & Daily Limits ---
    async def _check_circuit_breaker(self, current_time: float) -> bool:
        """Checks for sudden price movements and pauses trading if threshold is exceeded."""
        cb_config = self.config.strategy.circuit_breaker
        if not cb_config.enabled:
            return False

        # Ensure we are not in cooldown from a previous trip
        if current_time < self.state.circuit_breaker_cooldown_end_time:
            self.logger.debug(
                f"[{self.config.symbol}] Circuit breaker in cooldown. Not checking for new trip."
            )
            return False

        recent_prices_window = [
            (t, p)
            for t, p in self.state.circuit_breaker_price_points
            if (current_time - t) <= cb_config.check_window_sec
        ]

        if len(recent_prices_window) < 2:
            return False

        recent_prices_window.sort(key=lambda x: x[0])
        start_price = recent_prices_window[0][1]
        end_price = recent_prices_window[-1][1]

        if start_price == DECIMAL_ZERO:
            return False

        price_change_pct = abs(end_price - start_price) / start_price

        if price_change_pct > Decimal(str(cb_config.pause_threshold_pct)):
            self.logger.warning(
                f"[{self.config.symbol}] CIRCUIT BREAKER TRIPPED: Price changed {price_change_pct:.2%} in {cb_config.check_window_sec}s. Pausing trading for {cb_config.pause_duration_sec}s."
            )
            self.state.is_paused = True
            self.state.pause_end_time = current_time + cb_config.pause_duration_sec
            self.state.circuit_breaker_cooldown_end_time = (
                self.state.pause_end_time + cb_config.cool_down_after_trip_sec
            )
            await self._cancel_all_orders()
            termux_notify(
                f"{self.config.symbol}: Circuit Breaker TRIP! Paused for {cb_config.pause_duration_sec}s",
                is_error=True,
            )
            return True
        return False

    async def _check_daily_pnl_limits(self) -> bool:
        """Checks if daily PnL has hit stop-loss or take-profit limits."""
        cb_config = self.config.strategy.circuit_breaker
        if not cb_config.enabled or cb_config.max_daily_loss_pct is None:
            return False

        current_day = datetime.now(timezone.utc).date()
        # Ensure daily_pnl_reset_date is a date for comparison
        reset_date = (
            self.state.daily_pnl_reset_date.date()
            if self.state.daily_pnl_reset_date
            else None
        )

        if reset_date is None or reset_date < current_day:
            self.logger.info(
                f"[{self.config.symbol}] New day detected. Resetting daily initial capital."
            )
            await (
                self._update_balance_and_position()
            )  # Ensure balance is fresh for new daily capital
            self.state.daily_initial_capital = self.state.current_balance
            self.state.daily_pnl_reset_date = datetime.now(timezone.utc)
            return False  # No loss yet for new day

        if self.state.daily_initial_capital <= DECIMAL_ZERO:
            self.logger.warning(
                f"[{self.config.symbol}] Daily initial capital is zero or negative, cannot check daily loss. Skipping."
            )
            return False

        # For derivatives, current_balance includes unrealized PnL, for spot, we add metrics UPNL.
        current_total_capital = self.state.current_balance
        if self.global_config.category == "spot":
            current_total_capital += self.state.metrics.calculate_unrealized_pnl(
                self.state.mid_price
            )

        daily_pnl = current_total_capital - self.state.daily_initial_capital
        daily_loss_pct = (
            (daily_pnl / self.state.daily_initial_capital)
            if self.state.daily_initial_capital > DECIMAL_ZERO
            and daily_pnl < DECIMAL_ZERO
            else DECIMAL_ZERO
        )

        if daily_loss_pct > Decimal(str(cb_config.max_daily_loss_pct)):
            self.logger.critical(
                f"{Colors.NEON_RED}[{self.config.symbol}] DAILY LOSS CIRCUIT BREAKER TRIPPED! Current Loss: {daily_loss_pct:.2%} exceeds "
                f"max daily loss threshold ({cb_config.max_daily_loss_pct:.2%}). "
                "Shutting down for the day.{Colors.RESET}"
            )
            termux_notify(
                f"{self.config.symbol}: DAILY SL HIT! Loss: {daily_loss_pct:.2%}",
                is_error=True,
            )
            self._stop_event.set()  # Signal main bot to stop this symbol
            return True
        return False

    # --- Trading Hours Check ---
    def _is_trading_hours(self, current_time_utc: datetime) -> bool:
        """Checks if the current time is within the configured trading hours."""
        if not self.config.trading_hours_start or not self.config.trading_hours_end:
            return True  # Always trade if no hours are set

        try:
            start_time = datetime.strptime(
                self.config.trading_hours_start, "%H:%M"
            ).time()
            end_time = datetime.strptime(self.config.trading_hours_end, "%H:%M").time()
            current_time = current_time_utc.time()

            if start_time <= end_time:
                return start_time <= current_time <= end_time
            else:  # Overnight trading (e.g., 22:00 - 04:00)
                return current_time >= start_time or current_time <= end_time
        except ValueError as e:
            self.logger.error(
                f"[{self.config.symbol}] Invalid trading hours format: {e}. Trading hours check skipped.",
                exc_info=True,
            )
            return True  # If format is invalid, assume always trading

    # --- Dry Run / Simulation Specifics ---
    async def _simulate_dry_run_price_movement(self, current_time: float) -> None:
        """Simulates price movement for DRY_RUN mode using Geometric Brownian Motion."""
        dt = self.global_config.dry_run_time_step_dt
        if (current_time - self.state.last_dry_run_price_update_time) < dt:
            return

        mu = self.global_config.dry_run_price_drift_mu
        sigma = self.global_config.dry_run_price_volatility_sigma

        price_float = float(self.state.mid_price)
        if price_float <= 0:
            price_float = 1e-10  # Prevent division by zero or negative prices

        new_price_float = price_float * np.exp(
            (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * np.random.normal()
        )
        if new_price_float < 1e-8:
            new_price_float = 1e-8  # Prevent extremely low prices

        new_mid_price = Decimal(str(new_price_float))

        self.state.mid_price = new_mid_price  # Update actual mid_price

        # Update candlestick history for ATR calculation
        if self.state.price_candlestick_history:
            last_ts, last_high, last_low, _ = self.state.price_candlestick_history[-1]
            current_high = max(last_high, new_mid_price)
            current_low = min(last_low, new_mid_price)
            if (current_time - last_ts) < dt:  # Still within the same "candle"
                self.state.price_candlestick_history[-1] = (
                    current_time,
                    current_high,
                    current_low,
                    new_mid_price,
                )
            else:  # New "candle"
                self.state.price_candlestick_history.append(
                    (current_time, new_mid_price, new_mid_price, new_mid_price)
                )
        else:
            self.state.price_candlestick_history.append(
                (current_time, new_mid_price, new_mid_price, new_mid_price)
            )

        self.state.circuit_breaker_price_points.append(
            (current_time, self.state.mid_price)
        )

        alpha = Decimal(
            str(self.config.strategy.dynamic_spread.price_change_smoothing_factor)
        )
        if self.state.smoothed_mid_price == DECIMAL_ZERO:
            self.state.smoothed_mid_price = new_mid_price
        else:
            self.state.smoothed_mid_price = (alpha * new_mid_price) + (
                (Decimal("1") - alpha) * self.state.smoothed_mid_price
            )

        self.state.last_dry_run_price_update_time = current_time
        self.logger.debug(
            f"[{self.config.symbol}] DRY_RUN Price Movement: Mid: {self.state.mid_price}, Smoothed: {self.state.smoothed_mid_price}"
        )

    async def _simulate_dry_run_fills(self) -> None:
        """Simulates order fills for DRY_RUN mode."""
        orders_to_process = []
        for order_id, order_data in list(self.state.active_orders.items()):
            if (
                order_id.startswith("DRY_") and order_data["status"] == "New"
            ):  # Only process new orders
                order_price = order_data["price"]
                side = order_data["side"]

                filled = False
                if (side == "Buy" and self.state.mid_price <= order_price) or (
                    side == "Sell" and self.state.mid_price >= order_price
                ):
                    filled = True

                if filled:
                    fill_qty = order_data["qty"] - order_data["cumExecQty"]
                    if fill_qty <= DECIMAL_ZERO:
                        continue

                    if (
                        side == "Sell"
                        and fill_qty > self.state.metrics.current_asset_holdings
                    ):
                        self.logger.warning(
                            f"[{self.config.symbol}] DRY_RUN: Attempted to sell {fill_qty} but only {self.state.metrics.current_asset_holdings} held. Adjusting fill quantity."
                        )
                        fill_qty = self.state.metrics.current_asset_holdings
                        if fill_qty <= DECIMAL_ZERO:
                            continue

                    orders_to_process.append((order_id, order_data, fill_qty))

        for order_id, order_data, fill_qty in orders_to_process:
            self.logger.info(
                f"[{self.config.symbol}] DRY_RUN: Simulating fill for order {order_id} (Side: {order_data['side']}, Price: {order_data['price']}) with {fill_qty} at current mid_price {self.state.mid_price}"
            )

            mock_fill_data = {
                "orderId": order_id,
                "orderLinkId": order_data.get("orderLinkId"),
                "symbol": order_data["symbol"],
                "side": order_data["side"],
                "orderType": order_data["orderType"],
                "execQty": str(fill_qty),
                "execPrice": str(self.state.mid_price),
                "execFee": str(
                    fill_qty
                    * self.state.mid_price
                    * (
                        self.config.taker_fee_rate
                        if self.config.taker_fee_rate
                        else DECIMAL_ZERO
                    )
                ),
                "feeCurrency": self.config.quote_currency,
                "pnl": "0",  # PnL will be calculated by _process_execution_update
                "execType": "Trade",  # Simulate as taker fill
            }

            # Update local order state
            self.state.active_orders[order_id]["cumExecQty"] += fill_qty
            if (
                self.state.active_orders[order_id]["cumExecQty"]
                >= self.state.active_orders[order_id]["qty"]
            ):
                self.state.active_orders[order_id]["status"] = "Filled"
            else:
                self.state.active_orders[order_id]["status"] = "PartiallyFilled"

            await self._process_execution_update(
                mock_fill_data
            )  # Process as a real execution update

            if self.state.active_orders[order_id]["status"] == "Filled":
                del self.state.active_orders[order_id]

    # --- Status and Reporting ---
    async def _log_status_summary(self) -> None:
        """Logs a summary of the bot's current status and performance metrics."""
        metrics = self.state.metrics
        current_market_price = (
            self.state.mid_price
            if self.state.mid_price > DECIMAL_ZERO
            else self.state.smoothed_mid_price
        )

        if current_market_price == DECIMAL_ZERO:
            self.logger.warning(
                f"[{self.config.symbol}] Cannot calculate unrealized PnL, current market price is zero."
            )
            unrealized_pnl_bot_calculated = DECIMAL_ZERO
        else:
            unrealized_pnl_bot_calculated = metrics.calculate_unrealized_pnl(
                current_market_price
            )

        # For derivatives, use exchange-reported UPNL; for spot, use bot-calculated
        display_unrealized_pnl = (
            self.state.unrealized_pnl_derivatives
            if self.global_config.category in ["linear", "inverse"]
            else unrealized_pnl_bot_calculated
        )

        total_current_pnl = metrics.net_realized_pnl + display_unrealized_pnl
        pos_qty = (
            self.state.current_position_qty
        )  # Use current_position_qty for general reporting
        exposure_usd = (
            pos_qty * current_market_price
            if current_market_price > DECIMAL_ZERO
            else DECIMAL_ZERO
        )

        # Daily PnL calculation
        current_total_capital = self.state.current_balance + display_unrealized_pnl
        daily_pnl = current_total_capital - self.state.daily_initial_capital
        daily_loss_pct = (
            float(abs(daily_pnl / self.state.daily_initial_capital))
            if self.state.daily_initial_capital > DECIMAL_ZERO
            and daily_pnl < DECIMAL_ZERO
            else 0.0
        )
        daily_profit_pct = (
            float(daily_pnl / self.state.daily_initial_capital)
            if self.state.daily_initial_capital > DECIMAL_ZERO
            and daily_pnl > DECIMAL_ZERO
            else 0.0
        )

        pnl_summary = (
            f"Realized PNL: {metrics.realized_pnl:+.4f} {self.config.quote_currency} | "
            f"Unrealized PNL: {display_unrealized_pnl:+.4f} {self.config.quote_currency}"
        )

        active_buys = sum(
            1
            for o in self.state.active_orders.values()
            if o["side"] == "Buy"
            and o["status"]
            not in ["Filled", "Cancelled", "Rejected", "Deactivated", "Expired"]
        )
        active_sells = sum(
            1
            for o in self.state.active_orders.values()
            if o["side"] == "Sell"
            and o["status"]
            not in ["Filled", "Cancelled", "Rejected", "Deactivated", "Expired"]
        )

        self.logger.info(
            f"""{Colors.CYAN}--- {self.config.symbol} STATUS ({"Enabled" if self.config.trade_enabled else "Disabled"}) ---
  {Colors.YELLOW}Mid: {current_market_price:.{self.config.price_precision.as_tuple()._exp if self.config.price_precision else 8}f} | Pos: {self.state.current_position_qty:+.{self.config.quantity_precision.as_tuple()._exp if self.config.quantity_precision else 8}f} {self.config.base_currency} (Exposure: {exposure_usd:+.2f} {self.global_config.main_quote_currency}){Colors.RESET}
  {Colors.MAGENTA}Balance: {self.state.current_balance:.2f} {self.global_config.main_quote_currency} | Avail: {self.state.available_balance:.2f}{Colors.RESET}
  {Colors.NEON_BLUE}Total PNL: {total_current_pnl:+.4f} | {pnl_summary}{Colors.RESET}
  {Colors.NEON_GREEN}Net Realized PNL: {metrics.net_realized_pnl:+.4f} | Daily PNL: {daily_pnl:+.4f} ({daily_profit_pct:.2%} Profit / {daily_loss_pct:.2%} Loss) | Win Rate: {metrics.win_rate:.2f}% | Orders: {active_buys} Buy / {active_sells} Sell{Colors.RESET}
{Colors.CYAN}--------------------------------------{Colors.RESET}"""
        )
        await self.db_manager.log_bot_metrics(
            self.config.symbol,
            metrics,
            display_unrealized_pnl,
            daily_pnl,
            daily_loss_pct,
            current_market_price,
        )


# --- Main Pyrmethus Bot Orchestrator ---
class PyrmethusBot:
    """
    Orchestrates multiple AsyncSymbolBot instances, manages global configuration,
    and handles overall bot lifecycle.
    """

    def __init__(self):
        self.global_config: GlobalConfig  # Initialized after loading
        self.logger: logging.Logger = logging.getLogger(
            "BybitMarketMaker.main_temp"
        )  # Temporary logger

        self.api_client: Optional[BybitAPIClient] = None
        self.ws_client: Optional[BybitWebSocketClient] = None
        self.db_manager: Optional[DBManager] = None

        self.symbol_bots: Dict[
            str, AsyncSymbolBot
        ] = {}  # {symbol: AsyncSymbolBot_instance}
        self.active_symbol_configs: Dict[str, SymbolConfig] = {}  # To track changes

        self._stop_event = asyncio.Event()  # Event to signal main bot loop to stop
        self.config_refresh_task: Optional[asyncio.Task] = None

    def _setup_signal_handlers(self) -> None:
        """Sets up signal handlers for graceful shutdown."""

        async def handle_shutdown(signum, frame):
            self.logger.info(
                f"{Colors.YELLOW}\\n# Ritual interrupted by seeker (Signal {signum}). Initiating final shutdown sequence...{Colors.RESET}"
            )
            self._stop_event.set()  # Signal the main loop to stop

        # Register async handler for SIGINT/SIGTERM
        # asyncio.create_task is safe to call from a signal handler
        signal.signal(
            signal.SIGINT,
            lambda signum, frame: asyncio.create_task(handle_shutdown(signum, frame)),
        )
        signal.signal(
            signal.SIGTERM,
            lambda signum, frame: asyncio.create_task(handle_shutdown(signum, frame)),
        )
        self.logger.info(
            f"{Colors.CYAN}# Signal handlers for graceful shutdown attuned.{Colors.RESET}"
        )

    async def _initialize_bot_components(self) -> None:
        """Initializes API client, WebSocket client, and database manager."""
        self.api_client = BybitAPIClient(self.global_config, self.logger)
        self.ws_client = BybitWebSocketClient(self.global_config, self.logger)
        self.db_manager = DBManager(
            STATE_DIR / self.global_config.files.db_file, self.logger
        )
        await self.db_manager.connect()
        await self.db_manager.create_tables()

    async def _start_symbol_bots(self, symbol_configs: Dict[str, SymbolConfig]) -> None:
        """Starts, restarts, or stops AsyncSymbolBot instances based on configuration."""
        if not self.api_client or not self.ws_client or not self.db_manager:
            self.logger.critical(
                f"{Colors.NEON_RED}Core components not initialized. Cannot start SymbolBots.{Colors.RESET}"
            )
            return

        symbols_in_new_config = set(symbol_configs.keys())
        symbols_currently_active = set(self.symbol_bots.keys())

        # Stop bots for symbols no longer in config or disabled
        for symbol in list(
            symbols_currently_active
        ):  # Iterate over a copy as we modify the dict
            if (
                symbol not in symbols_in_new_config
                or not symbol_configs[symbol].trade_enabled
            ):
                self.logger.info(
                    f"{Colors.YELLOW}Stopping AsyncSymbolBot for {symbol} (no longer active or disabled)...{Colors.RESET}"
                )
                self.symbol_bots[symbol].stop()
                # Wait for the bot's run_loop to finish its shutdown logic
                bot_task_name = (
                    f"SymbolBot_{symbol.replace('/', '_').replace(':', '')}_Loop"
                )
                tasks_for_symbol = [
                    t for t in asyncio.all_tasks() if t.get_name() == bot_task_name
                ]
                if tasks_for_symbol:
                    await asyncio.gather(*tasks_for_symbol, return_exceptions=True)
                self.ws_client.unregister_symbol_bot(symbol)
                del self.symbol_bots[symbol]
                del self.active_symbol_configs[symbol]
                self.logger.info(
                    f"{Colors.CYAN}# SymbolBot for {symbol} has ceased its ritual.{Colors.RESET}"
                )

        # Start or update bots for active symbols
        for symbol, config in symbol_configs.items():
            if not config.trade_enabled:
                continue  # Skip disabled symbols

            if symbol not in self.symbol_bots:
                self.logger.info(
                    f"{Colors.CYAN}Summoning AsyncSymbolBot for {symbol}...{Colors.RESET}"
                )
                bot_logger = setup_logger(
                    self.global_config.files,
                    f"symbol.{symbol.replace('/', '_').replace(':', '')}",
                )
                bot = AsyncSymbolBot(
                    self.global_config,
                    config,
                    self.api_client,
                    self.ws_client,
                    self.db_manager,
                    bot_logger,
                )
                self.symbol_bots[symbol] = bot
                self.active_symbol_configs[symbol] = config
                self.ws_client.register_symbol_bot(bot)
                await bot.initialize()
                asyncio.create_task(
                    bot.run_loop(),
                    name=f"SymbolBot_{symbol.replace('/', '_').replace(':', '')}_Loop",
                )

            elif self.active_symbol_configs.get(symbol) != config:
                self.logger.info(
                    f"{Colors.YELLOW}Configuration for {symbol} changed. Restarting AsyncSymbolBot...{Colors.RESET}"
                )
                self.symbol_bots[symbol].stop()
                # Wait for the bot's run_loop to finish its shutdown logic
                bot_task_name = (
                    f"SymbolBot_{symbol.replace('/', '_').replace(':', '')}_Loop"
                )
                tasks_for_symbol = [
                    t for t in asyncio.all_tasks() if t.get_name() == bot_task_name
                ]
                if tasks_for_symbol:
                    await asyncio.gather(*tasks_for_symbol, return_exceptions=True)
                self.ws_client.unregister_symbol_bot(symbol)
                del self.symbol_bots[symbol]

                bot_logger = setup_logger(
                    self.global_config.files,
                    f"symbol.{symbol.replace('/', '_').replace(':', '')}",
                )
                bot = AsyncSymbolBot(
                    self.global_config,
                    config,
                    self.api_client,
                    self.ws_client,
                    self.db_manager,
                    bot_logger,
                )
                self.symbol_bots[symbol] = bot
                self.active_symbol_configs[symbol] = config
                self.ws_client.register_symbol_bot(bot)
                await bot.initialize()
                asyncio.create_task(
                    bot.run_loop(),
                    name=f"SymbolBot_{symbol.replace('/', '_').replace(':', '')}_Loop",
                )

        # Update WebSocket subscriptions for all active symbols
        await self._update_websocket_subscriptions()

    async def _update_websocket_subscriptions(self) -> None:
        """Updates WebSocket subscriptions based on currently active symbol bots."""
        public_topics: List[str] = []
        private_topics: List[str] = []

        for symbol_cfg in self.active_symbol_configs.values():
            symbol_ws_format = symbol_cfg.symbol.replace("/", "").replace(":", "")
            public_topics.append(
                f"orderbook.1.{symbol_ws_format}"
            )  # Depth 1 for orderbook
            public_topics.append(f"publicTrade.{symbol_ws_format}")
            public_topics.append(
                f"kline.{symbol_cfg.strategy.kline_interval}.{symbol_ws_format}"
            )

        # Private topics are generally fixed for account-wide updates
        private_topics.extend(["order", "execution", "position", "wallet"])

        # Filter out duplicates and sort for comparison
        public_topics_set = sorted(list(set(public_topics)))
        private_topics_set = sorted(list(set(private_topics)))

        if self.ws_client:
            await self.ws_client.start_streams(public_topics_set, private_topics_set)
        else:
            self.logger.error(
                f"{Colors.NEON_RED}WebSocket client not initialized.{Colors.RESET}"
            )

    async def _stop_all_bots(self) -> None:
        """Signals all SymbolBots and WebSocket client to stop."""
        self.logger.info(
            f"{Colors.YELLOW}# Initiating graceful shutdown of all SymbolBots...{Colors.RESET}"
        )

        # Signal all individual symbol bot tasks to stop and await their completion
        tasks_to_await = []
        for symbol, bot in list(self.symbol_bots.items()):
            bot.stop()
            bot_task_name = (
                f"SymbolBot_{symbol.replace('/', '_').replace(':', '')}_Loop"
            )
            tasks_to_await.extend(
                [t for t in asyncio.all_tasks() if t.get_name() == bot_task_name]
            )

        if tasks_to_await:
            await asyncio.gather(*tasks_to_await, return_exceptions=True)

        # Clean up from WS client
        for symbol in list(self.symbol_bots.keys()):
            self.ws_client.unregister_symbol_bot(symbol)
            del self.symbol_bots[symbol]
            del self.active_symbol_configs[symbol]

        self.logger.info(
            f"{Colors.CYAN}All AsyncSymbolBots have been extinguished.{Colors.RESET}"
        )

        # Stop WebSocket streams
        if self.ws_client:
            await self.ws_client.stop_streams()

        # Close DB connection
        if self.db_manager:
            await self.db_manager.close()

    async def _config_refresh_task(self) -> None:
        """Periodically reloads configuration and updates symbol bots."""
        last_config_check_time = time.time()
        while not self._stop_event.is_set():
            try:
                if (
                    time.time() - last_config_check_time
                ) > self.global_config.system.config_refresh_interval_sec:
                    self.logger.info(
                        f"{Colors.CYAN}Periodically checking for configuration changes...{Colors.RESET}"
                    )

                    # Determine if single symbol mode is active to pass to load_config
                    single_symbol_active = len(self.active_symbol_configs) == 1
                    input_symbol_for_refresh = (
                        list(self.active_symbol_configs.keys())[0]
                        if single_symbol_active
                        else None
                    )

                    reloaded_global_cfg, reloaded_symbol_configs_dict = (
                        ConfigManager.load_config(
                            single_symbol=input_symbol_for_refresh
                        )
                    )

                    # If global config changed, update references and re-initialize components if needed
                    if reloaded_global_cfg != self.global_config:
                        self.logger.info(
                            f"{Colors.YELLOW}Global configuration changed. Updating references. (Full restart might be needed for some changes).{Colors.RESET}"
                        )
                        object.__setattr__(
                            self, "global_config", reloaded_global_cfg
                        )  # Update global_config
                        self.logger = setup_logger(
                            self.global_config.files, "main"
                        )  # Re-setup logger

                        # Update configs for API/WS/DB clients
                        if self.api_client:
                            self.api_client.config = self.global_config
                        if self.ws_client:
                            self.ws_client.config = self.global_config
                        if self.db_manager:
                            self.db_manager.db_file = (
                                STATE_DIR / self.global_config.files.db_file
                            )
                        # Note: Changes to API keys or testnet status in global_config would require re-instantiating
                        # BybitAPIClient and BybitWebSocketClient for them to take effect.
                        # This is a simplification; for production, consider a full restart or more granular updates.

                    # Identify changes and update bots
                    await self._start_symbol_bots(
                        reloaded_symbol_configs_dict
                    )  # Pass dict directly
                    last_config_check_time = time.time()

            except asyncio.CancelledError:
                self.logger.info("Config refresh task cancelled.")
                break
            except Exception as e:
                self.logger.error(
                    f"{Colors.NEON_RED}Error in config manager task: {e}{Colors.RESET}",
                    exc_info=True,
                )

            await asyncio.sleep(self.global_config.system.config_refresh_interval_sec)

    async def run(self) -> None:
        """Initiates the grand market-making ritual."""
        self.logger.info(
            f"{Colors.NEON_GREEN}Pyrmethus Market Maker Bot starting...{Colors.RESET}"
        )

        self._setup_signal_handlers()

        input_symbol: Optional[str] = None
        selected_mode: str = "f"  # Default to file mode

        # Determine if running in an interactive terminal
        if sys.stdin.isatty():
            try:
                selected_mode = (
                    input(
                        f"{Colors.CYAN}Choose mode:\n"
                        f"  [f]rom file (symbols.json) - for multi-symbol operation\n"
                        f"  [s]ingle symbol (e.g., BTC/USDT:USDT) - for interactive, quick run\n"
                        f"Enter choice (f/s): {Colors.RESET}"
                    )
                    .lower()
                    .strip()
                )
                if selected_mode == "s":
                    input_symbol = (
                        input(
                            f"{Colors.CYAN}Enter single symbol (e.g., BTC/USDT:USDT): {Colors.RESET}"
                        )
                        .upper()
                        .strip()
                    )
                    if not input_symbol:
                        raise ConfigurationError(
                            "No symbol entered for single symbol mode."
                        )
                elif selected_mode != "f":
                    self.logger.warning(
                        f"{Colors.YELLOW}Invalid mode selected. Defaulting to file mode.{Colors.RESET}"
                    )
                    selected_mode = "f"
            except EOFError:
                self.logger.warning(
                    f"{Colors.YELLOW}No interactive input detected (EOF). Defaulting to file mode.{Colors.RESET}"
                )
                selected_mode = "f"
            except Exception as e:
                self.logger.critical(
                    f"{Colors.NEON_RED}Error during mode selection: {e}. Exiting.{Colors.RESET}"
                )
                sys.exit(1)
        else:
            self.logger.warning(
                f"{Colors.YELLOW}Non-interactive environment detected. Defaulting to file mode.{Colors.RESET}"
            )
            selected_mode = (
                "f"  # Fallback to file mode if no interactive input possible
            )

        try:
            self.global_config, symbol_configs_dict = ConfigManager.load_config(
                single_symbol=input_symbol if selected_mode == "s" else None
            )
            # Re-setup the main logger with the actual global config's file settings
            self.logger = setup_logger(self.global_config.files, "main")
        except ConfigurationError as e:
            self.logger.critical(
                f"{Colors.NEON_RED}Configuration loading failed: {e}. Exiting.{Colors.RESET}"
            )
            sys.exit(1)
        except Exception as e:
            self.logger.critical(
                f"{Colors.NEON_RED}Unexpected error during configuration loading: {e}. Exiting.{Colors.RESET}",
                exc_info=True,
            )
            sys.exit(1)

        await self._initialize_bot_components()
        await self._start_symbol_bots(symbol_configs_dict)  # Pass dict directly

        self.config_refresh_task = asyncio.create_task(
            self._config_refresh_task(), name="Config_Refresh_Task"
        )

        try:
            self.logger.info(
                f"{Colors.NEON_GREEN}Pyrmethus Bot is now operational. Press Ctrl+C to stop.{Colors.RESET}"
            )
            await self._stop_event.wait()  # Wait until stop event is set
        except asyncio.CancelledError:
            self.logger.info(
                f"[{self.global_config.category}] Bot main task cancelled."
            )
        except KeyboardInterrupt:
            self.logger.info(
                f"{Colors.YELLOW}Ctrl+C detected. Initiating graceful shutdown...{Colors.RESET}"
            )
        except Exception as e:
            self.logger.critical(
                f"{Colors.NEON_RED}An unhandled error occurred in the main bot process: {e}{Colors.RESET}",
                exc_info=True,
            )
            termux_notify("Pyrmethus Bot CRASHED!", is_error=True)
        finally:
            self.logger.info(
                f"{Colors.YELLOW}# Finalizing shutdown sequence...{Colors.RESET}"
            )
            if self.config_refresh_task:
                self.config_refresh_task.cancel()
                try:
                    await self.config_refresh_task
                except asyncio.CancelledError:
                    pass

            await self._stop_all_bots()
            self.logger.info(
                f"{Colors.NEON_GREEN}Pyrmethus Market Maker Bot has completed its grand ritual. Farewell, seeker.{Colors.RESET}"
            )
            termux_notify("Bot has shut down.", title="Pyrmethus Bot Offline")
            sys.exit(0)


async def main():
    """Asynchronous entry point for the bot."""
    bot_instance: Optional[PyrmethusBot] = None
    try:
        # Ensure logs directory exists
        if not LOG_DIR.exists():
            try:
                LOG_DIR.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logging.critical(f"Failed to create log directory {LOG_DIR}: {e}")
                sys.exit(1)

        # Ensure state directory exists
        if not STATE_DIR.exists():
            try:
                STATE_DIR.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logging.critical(f"Failed to create state directory {STATE_DIR}: {e}")
                sys.exit(1)

        # Initialize a temporary logger for early messages before full config load
        temp_logger = logging.getLogger("BybitMarketMaker.init")
        if not temp_logger.handlers:
            logging.basicConfig(
                level=logging.INFO,
                format=f"{Colors.YELLOW}%(asctime)s - %(levelname)s - %(message)s{Colors.RESET}",
                stream=sys.stdout,
            )
            temp_logger = logging.getLogger("BybitMarketMaker.init")

        # Before loading config, check for symbol config file existence to create a default if missing
        # This requires a preliminary GLOBAL_CONFIG instance, which Pydantic can provide from defaults/env
        try:
            temp_global_config = GlobalConfig()
            config_file_path = (
                Path(__file__).parent / temp_global_config.files.symbol_config_file
            )
            if not config_file_path.exists():
                default_config_content = [
                    {
                        "symbol": "BTC/USDT:USDT",  # Example symbol, ensure this matches Bybit's format for pybit
                        "trade_enabled": True,
                        "leverage": 10,
                        "min_order_value_usd": 10.0,
                        "max_order_size_pct": 0.1,
                        "max_net_exposure_usd": 500.0,
                        "trading_hours_start": None,
                        "trading_hours_end": None,
                        "strategy": StrategyConfig().model_dump(
                            mode="json_compatible"
                        ),  # Use default strategy config
                    }
                ]
                with open(config_file_path, "w") as f:
                    json.dump(
                        default_config_content, f, indent=4, cls=JsonDecimalEncoder
                    )
                temp_logger.info(
                    f"{Colors.NEON_GREEN}Created default symbol config file: {config_file_path}{Colors.RESET}"
                )
                temp_logger.info(
                    f"{Colors.YELLOW}Please review and adjust {config_file_path} with your desired symbols and settings.{Colors.RESET}"
                )
                # It might be better not to exit, but let the user know and proceed with default if symbols.json is missing.
                # However, for initial setup, exiting to prompt user to create config is safer.
                # sys.exit(0) # Exit to allow user to edit config
        except Exception as e:
            temp_logger.critical(
                f"{Colors.NEON_RED}Error creating default config file: {e}{Colors.RESET}",
                exc_info=True,
            )
            sys.exit(1)

        bot_instance = PyrmethusBot()
        await bot_instance.run()  # Await the async run method
    except (KeyboardInterrupt, SystemExit):
        if bot_instance and bot_instance.logger:
            bot_instance.logger.info("\nBot stopped by user or system.")
        else:
            print("\nBot stopped by user or system.")
    except Exception as e:
        logger = (
            bot_instance.logger
            if bot_instance and hasattr(bot_instance, "logger")
            else logging.getLogger("BybitMarketMaker.main_fallback")
        )
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
        print(
            f"\nAn unexpected critical error occurred during bot runtime: {e}. Check log file for details."
        )
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass  # Handled by main()
    except Exception as e:
        print(f"An error occurred before main() could fully handle it: {e}")
        sys.exit(1)
