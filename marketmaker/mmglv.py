# Enhanced Market Making Bot for Bybit
# Incorporating best practices from all provided documents

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
import uuid
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal, InvalidOperation, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Literal

# External Libraries
try:
    import aiofiles
    import aiosqlite
    import numpy as np
    import pandas as pd
    import websocket
    from colorama import Fore, Style, init
    from dotenv import load_dotenv
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
    from tenacity import (
        before_sleep_log,
        retry,
        retry_if_exception,
        stop_after_attempt,
        wait_exponential_jitter,
    )

    EXTERNAL_LIBS_AVAILABLE = True
except ImportError as e:
    print(
        f"{Fore.RED}Error: Missing required library: {e}. Please install it using pip.{Style.RESET_ALL}"
    )
    EXTERNAL_LIBS_AVAILABLE = False

# Initialize Colorama
init(autoreset=True)

# Load environment variables
load_dotenv()

# Global Constants
getcontext().prec = 38
DECIMAL_ZERO: Decimal = Decimal("0")
BASE_DIR = Path(os.getenv("HOME", "."))
LOG_DIR: Path = BASE_DIR / "bot_logs"
STATE_DIR: Path = BASE_DIR / ".bot_state"
LOG_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)


# Custom Exceptions
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
    def __init__(self, message: str, ret_code: int = -1, ret_msg: str = "Unknown"):
        super().__init__(message)
        self.ret_code = ret_code
        self.ret_msg = ret_msg


class BybitRateLimitError(BybitAPIError):
    pass


class BybitInsufficientBalanceError(BybitAPIError):
    pass


# Utility Classes
class Colors:
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
    try:
        subprocess.run(
            ["termux-notification", "-h"], check=True, capture_output=True, timeout=2
        )
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
        logging.getLogger("BybitMarketMaker").warning(
            f"[NOTIFICATION FAILED] {title}: {message}"
        )
    except Exception as e:
        logging.getLogger("BybitMarketMaker").warning(
            f"Unexpected error with Termux notification: {e}"
        )


class JsonDecimalEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


# Pydantic Models for Configuration
class DynamicSpreadConfig(BaseModel):
    enabled: bool = True
    volatility_window_sec: PositiveInt = 60
    volatility_multiplier: PositiveFloat = 2.0
    min_spread_pct: PositiveFloat = 0.0005
    max_spread_pct: PositiveFloat = 0.01
    price_change_smoothing_factor: PositiveFloat = 0.2
    atr_update_interval_sec: PositiveInt = 300


class InventorySkewConfig(BaseModel):
    enabled: bool = True
    skew_intensity: PositiveFloat = 0.5
    max_inventory_ratio: PositiveFloat = 0.5
    inventory_sizing_factor: NonNegativeFloat = 0.5


class OrderLayer(BaseModel):
    spread_offset_pct: NonNegativeFloat = 0.0
    quantity_multiplier: PositiveFloat = 1.0
    cancel_threshold_pct: PositiveFloat = 0.01


class CircuitBreakerConfig(BaseModel):
    enabled: bool = True
    pause_threshold_pct: PositiveFloat = 0.02
    check_window_sec: PositiveInt = 10
    pause_duration_sec: PositiveInt = 60
    cool_down_after_trip_sec: PositiveInt = 300
    max_daily_loss_pct: PositiveFloat | None = None


class StrategyConfig(BaseModel):
    base_spread_pct: PositiveFloat = 0.001
    base_order_size_pct_of_balance: PositiveFloat = 0.005
    order_stale_threshold_pct: PositiveFloat = 0.0005
    min_profit_spread_after_fees_pct: PositiveFloat = 0.0002
    max_outstanding_orders: PositiveInt = 2
    market_data_stale_timeout_seconds: PositiveInt = 30
    enable_auto_sl_tp: bool = False
    take_profit_target_pct: PositiveFloat = 0.005
    stop_loss_trigger_pct: PositiveFloat = 0.005
    kline_interval: str = "1m"
    stale_order_max_age_seconds: PositiveInt = 300

    dynamic_spread: DynamicSpreadConfig = Field(default_factory=DynamicSpreadConfig)
    inventory_skew: InventorySkewConfig = Field(default_factory=InventorySkewConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    order_layers: list[OrderLayer] = Field(default_factory=lambda: [OrderLayer()])

    model_config = ConfigDict(validate_assignment=True)


class SystemConfig(BaseModel):
    loop_interval_sec: PositiveFloat = 0.5
    order_refresh_interval_sec: PositiveFloat = 5.0
    ws_heartbeat_sec: PositiveInt = 30
    cancellation_rate_limit_sec: PositiveFloat = 0.2
    status_report_interval_sec: PositiveInt = 30
    ws_reconnect_attempts: PositiveInt = 5
    ws_reconnect_initial_delay_sec: PositiveInt = 5
    ws_reconnect_max_delay_sec: PositiveInt = 60
    api_retry_attempts: PositiveInt = 5
    api_retry_initial_delay_sec: PositiveFloat = 0.5
    api_retry_max_delay_sec: PositiveFloat = 10.0
    health_check_interval_sec: PositiveInt = 10
    config_refresh_interval_sec: PositiveInt = 60

    model_config = ConfigDict(validate_assignment=True)


class FilesConfig(BaseModel):
    log_level: str = "INFO"
    log_file: str = "market_maker.log"
    state_file: str = "market_maker_state.json"
    db_file: str = "market_maker.db"
    symbol_config_file: str = "symbols.json"
    log_format: Literal["plain", "json"] = "plain"
    pybit_log_level: str = "WARNING"

    model_config = ConfigDict(validate_assignment=True)


class GlobalConfig(BaseModel):
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
    )

    system: SystemConfig = Field(default_factory=SystemConfig)
    files: FilesConfig = Field(default_factory=FilesConfig)

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
    symbol: str
    trade_enabled: bool = True
    leverage: PositiveInt = 10
    min_order_value_usd: PositiveFloat = 10.0
    max_order_size_pct: PositiveFloat = 0.1
    max_net_exposure_usd: PositiveFloat = 500.0
    trading_hours_start: str | None = None
    trading_hours_end: str | None = None

    strategy: StrategyConfig = Field(default_factory=StrategyConfig)

    price_precision: Decimal | None = None
    quantity_precision: Decimal | None = None
    min_order_qty: Decimal | None = None
    min_notional_value: Decimal | None = None
    maker_fee_rate: Decimal | None = None
    taker_fee_rate: Decimal | None = None

    base_currency: str | None = None
    quote_currency: str | None = None

    model_config = ConfigDict(validate_assignment=True)

    def __pydantic_post_init__(self, __context: Any) -> None:
        if self.symbol and ":" in self.symbol:
            parts = self.symbol.split(":")
            self.quote_currency = parts[1]
            self.base_currency = parts[0].split("/")[0]
        elif self.symbol and len(self.symbol) > 4 and self.symbol[-4:].isupper():
            self.base_currency = self.symbol[:-4]
            self.quote_currency = self.symbol[-4:]
        elif self.symbol and len(self.symbol) > 3 and self.symbol[-3:].isupper():
            self.base_currency = self.symbol[:-3]
            self.quote_currency = self.symbol[-3:]
        else:
            self.base_currency = "UNKNOWN"
            self.quote_currency = "UNKNOWN"
            logging.getLogger("BybitMarketMaker").warning(
                f"[{self.symbol}] Cannot parse base/quote currency from symbol: {self.symbol}. Using UNKNOWN."
            )

        # Additional validation
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
        if self.price_precision is None:
            logging.getLogger("BybitMarketMaker").warning(
                f"[{self.symbol}] Price precision not set. Using default 8 decimal places."
            )
            return p.quantize(Decimal("1e-8"), rounding=ROUND_DOWN)
        return p.quantize(self.price_precision, rounding=ROUND_DOWN)

    def format_quantity(self, q: Decimal) -> Decimal:
        if self.quantity_precision is None:
            logging.getLogger("BybitMarketMaker").warning(
                f"[{self.symbol}] Quantity precision not set. Using default 8 decimal places."
            )
            return q.quantize(Decimal("1e-8"), rounding=ROUND_DOWN)
        return q.quantize(self.quantity_precision, rounding=ROUND_DOWN)


# Configuration Manager
class ConfigManager:
    _global_config: GlobalConfig | None = None
    _symbol_configs: dict[str, SymbolConfig] = {}

    @classmethod
    def load_config(
        cls, single_symbol: str | None = None
    ) -> tuple[GlobalConfig, dict[str, SymbolConfig]]:
        try:
            cls._global_config = GlobalConfig()
        except ValidationError as e:
            logging.critical(f"Global configuration validation error: {e}")
            raise ConfigurationError(f"Global configuration validation failed: {e}")

        cls._symbol_configs = {}
        if single_symbol:
            default_symbol_data = {
                "symbol": single_symbol,
                "trade_enabled": True,
                "leverage": 10,
                "min_order_value_usd": 10.0,
                "max_order_size_pct": 0.1,
                "max_net_exposure_usd": 500.0,
                "strategy": StrategyConfig().model_dump(mode="json_compatible"),
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
                        s_cfg_data.setdefault("strategy", {})
                        default_strategy_config_dict = StrategyConfig().model_dump(
                            mode="json_compatible"
                        )
                        for (
                            strat_field,
                            default_value,
                        ) in default_strategy_config_dict.items():
                            if strat_field not in s_cfg_data["strategy"]:
                                s_cfg_data["strategy"][strat_field] = default_value
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


# Logger Setup
class JsonFormatter(logging.Formatter):
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
    logger_name = f"BybitMarketMaker.{name_suffix}"
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)

    logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
    logger.propagate = False

    if config.log_format == "json":
        file_formatter = JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S")
        stream_formatter = JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S")
    else:
        file_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s"
        )
        stream_formatter = logging.Formatter(
            f"{Colors.NEON_BLUE}%(asctime)s{Colors.RESET} - "
            f"{Colors.YELLOW}%(levelname)-8s{Colors.RESET} - "
            f"{Colors.MAGENTA}[%(name)s]{Colors.RESET} - %(message)s",
            datefmt="%H:%M:%S",
        )

    log_file_path = LOG_DIR / config.log_file
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)

    pybit_logger = logging.getLogger("pybit")
    pybit_logger.setLevel(
        getattr(logging, config.pybit_log_level.upper(), logging.WARNING)
    )
    pybit_logger.propagate = False
    if not pybit_logger.handlers:
        pybit_logger.addHandler(file_handler)
        pybit_logger.addHandler(stream_handler)

    return logger


# API Retry Decorator
def retry_api_call():
    global_config = ConfigManager._global_config
    if global_config is None:
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


# Data Classes for Trading State and Metrics
@dataclass
class TradeMetrics:
    total_trades: int = 0
    gross_profit: Decimal = DECIMAL_ZERO
    gross_loss: Decimal = DECIMAL_ZERO
    total_fees: Decimal = DECIMAL_ZERO
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    realized_pnl: Decimal = DECIMAL_ZERO
    current_asset_holdings: Decimal = DECIMAL_ZERO
    average_entry_price: Decimal = DECIMAL_ZERO
    last_pnl_update_timestamp: datetime | None = None

    @property
    def net_realized_pnl(self) -> Decimal:
        return self.realized_pnl - self.total_fees

    def update_win_rate(self) -> None:
        self.win_rate = (
            (self.wins / self.total_trades * 100.0) if self.total_trades > 0 else 0.0
        )

    def update_pnl_on_buy(self, quantity: Decimal, price: Decimal) -> None:
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
        if self.current_asset_holdings < quantity:
            logging.getLogger("BybitMarketMaker").warning(
                f"Attempted to sell {quantity} but only {self.current_asset_holdings} held. Adjusting quantity."
            )
            quantity = self.current_asset_holdings
            if quantity <= DECIMAL_ZERO:
                return

        self.realized_pnl += (price - self.average_entry_price) * quantity
        self.current_asset_holdings -= quantity
        if self.current_asset_holdings <= DECIMAL_ZERO:
            self.average_entry_price = DECIMAL_ZERO
            self.current_asset_holdings = DECIMAL_ZERO
        self.last_pnl_update_timestamp = datetime.now(timezone.utc)

    def calculate_unrealized_pnl(self, current_price: Decimal) -> Decimal:
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
    mid_price: Decimal = DECIMAL_ZERO
    smoothed_mid_price: Decimal = DECIMAL_ZERO
    current_balance: Decimal = DECIMAL_ZERO
    available_balance: Decimal = DECIMAL_ZERO
    current_position_qty: Decimal = DECIMAL_ZERO
    unrealized_pnl_derivatives: Decimal = DECIMAL_ZERO
    active_orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_order_management_time: float = 0.0
    last_ws_message_time: float = field(default_factory=time.time)
    last_status_report_time: float = 0.0
    last_health_check_time: float = 0.0
    price_candlestick_history: deque[tuple[float, Decimal, Decimal, Decimal]] = field(
        default_factory=deque
    )
    circuit_breaker_price_points: deque[tuple[float, Decimal]] = field(
        default_factory=deque
    )
    is_paused: bool = False
    pause_end_time: float = 0.0
    circuit_breaker_cooldown_end_time: float = 0.0
    ws_reconnect_attempts_left: int = 0
    metrics: TradeMetrics = field(default_factory=TradeMetrics)
    daily_initial_capital: Decimal = DECIMAL_ZERO
    daily_pnl_reset_date: datetime | None = None
    last_dry_run_price_update_time: float = field(default_factory=time.time)


# Enhanced WebSocket Manager with Reconnection and Batch Operations
class WebSocketManager:
    def __init__(self, global_config: GlobalConfig, logger: logging.Logger):
        self.config = global_config
        self.logger = logger
        self.public_ws = None
        self.private_ws = None
        self.public_subscriptions = []
        self.private_subscriptions = []
        self.reconnect_tasks = []
        self.heartbeat_tasks = []
        self.is_running = False

    async def start(self, public_callback: Callable, private_callback: Callable):
        """Start WebSocket connections with automatic reconnection"""
        self.is_running = True
        self.public_subscriptions.append(public_callback)
        self.private_subscriptions.append(private_callback)

        # Start public WebSocket
        asyncio.create_task(self._manage_public_websocket())

        # Start private WebSocket
        asyncio.create_task(self._manage_private_websocket())

        # Start heartbeat tasks
        asyncio.create_task(self._public_heartbeat())
        asyncio.create_task(self._private_heartbeat())

        self.logger.info("WebSocket manager started")

    async def stop(self):
        """Stop all WebSocket connections"""
        self.is_running = False

        # Cancel reconnect tasks
        for task in self.reconnect_tasks:
            task.cancel()

        # Cancel heartbeat tasks
        for task in self.heartbeat_tasks:
            task.cancel()

        # Close WebSocket connections
        if self.public_ws:
            await self._close_websocket(self.public_ws)

        if self.private_ws:
            await self._close_websocket(self.private_ws)

        self.logger.info("WebSocket manager stopped")

    async def _manage_public_websocket(self):
        """Manage public WebSocket with reconnection logic"""
        while self.is_running:
            try:
                self.logger.info("Connecting to public WebSocket...")
                self.public_ws = WebSocket(
                    testnet=self.config.testnet, channel_type="linear"
                )

                # Subscribe to all public channels
                for callback in self.public_subscriptions:
                    self.public_ws.orderbook_stream(200, "BTCUSDT", callback)
                    self.public_ws.kline_stream("1m", "BTCUSDT", callback)

                self.logger.info("Public WebSocket connected and subscribed")

                # Run WebSocket
                await self._run_websocket(self.public_ws)

            except Exception as e:
                self.logger.error(
                    f"Public WebSocket error: {e}. Reconnecting in {self.config.system.ws_reconnect_initial_delay_sec} seconds..."
                )
                await asyncio.sleep(self.config.system.ws_reconnect_initial_delay_sec)

    async def _manage_private_websocket(self):
        """Manage private WebSocket with reconnection logic"""
        while self.is_running:
            try:
                self.logger.info("Connecting to private WebSocket...")
                self.private_ws = WebSocket(
                    testnet=self.config.testnet,
                    channel_type="private",
                    api_key=self.config.api_key,
                    api_secret=self.config.api_secret,
                )

                # Subscribe to all private channels
                for callback in self.private_subscriptions:
                    self.private_ws.position_stream(callback)
                    self.private_ws.order_stream(callback)
                    self.private_ws.wallet_stream(callback)

                self.logger.info("Private WebSocket connected and subscribed")

                # Run WebSocket
                await self._run_websocket(self.private_ws)

            except Exception as e:
                self.logger.error(
                    f"Private WebSocket error: {e}. Reconnecting in {self.config.system.ws_reconnect_initial_delay_sec} seconds..."
                )
                await asyncio.sleep(self.config.system.ws_reconnect_initial_delay_sec)

    async def _run_websocket(self, ws: WebSocket):
        """Run WebSocket with reconnection logic"""
        reconnect_delay = self.config.system.ws_reconnect_initial_delay_sec

        while self.is_running:
            try:
                # Run WebSocket in background
                ws_task = asyncio.create_task(ws.run_forever())

                # Wait for WebSocket to finish or error
                await ws_task

            except Exception as e:
                self.logger.error(f"WebSocket connection lost: {e}")

                # Exponential backoff for reconnection
                if reconnect_delay < self.config.system.ws_reconnect_max_delay_sec:
                    reconnect_delay *= 2

                self.logger.info(f"Reconnecting in {reconnect_delay} seconds...")
                await asyncio.sleep(reconnect_delay)

    async def _close_websocket(self, ws: WebSocket):
        """Close WebSocket connection"""
        try:
            if ws:
                ws.close()
        except Exception as e:
            self.logger.error(f"Error closing WebSocket: {e}")

    async def _public_heartbeat(self):
        """Send heartbeat to public WebSocket"""
        while self.is_running:
            try:
                if self.public_ws:
                    self.public_ws.ping()
                await asyncio.sleep(self.config.system.ws_heartbeat_sec)
            except Exception as e:
                self.logger.error(f"Public WebSocket heartbeat error: {e}")

    async def _private_heartbeat(self):
        """Send heartbeat to private WebSocket"""
        while self.is_running:
            try:
                if self.private_ws:
                    self.private_ws.ping()
                await asyncio.sleep(self.config.system.ws_heartbeat_sec)
            except Exception as e:
                self.logger.error(f"Private WebSocket heartbeat error: {e}")

    async def place_batch_orders(
        self, orders: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Place multiple orders in a single batch request"""
        if not orders:
            return []

        results = []

        # Split orders into chunks of 10 (Bybit's batch limit)
        for i in range(0, len(orders), 10):
            chunk = orders[i : i + 10]
            try:
                response = await asyncio.to_thread(
                    self.private_ws.place_batch_order,
                    category="linear",
                    orderList=chunk,
                )
                results.append(response)
                self.logger.info(f"Batch order placed: {len(chunk)} orders")
            except Exception as e:
                self.logger.error(f"Error placing batch orders: {e}")

        return results

    async def cancel_batch_orders(self, order_ids: list[str]) -> list[dict[str, Any]]:
        """Cancel multiple orders in a single batch request"""
        if not order_ids:
            return []

        results = []

        # Split orders into chunks of 10 (Bybit's batch limit)
        for i in range(0, len(order_ids), 10):
            chunk = order_ids[i : i + 10]
            try:
                response = await asyncio.to_thread(
                    self.private_ws.cancel_batch_order,
                    category="linear",
                    request=[{"orderId": order_id} for order_id in chunk],
                )
                results.append(response)
                self.logger.info(f"Batch order cancelled: {len(chunk)} orders")
            except Exception as e:
                self.logger.error(f"Error cancelling batch orders: {e}")

        return results


# Enhanced Bybit API Client with Batch Operations and Improved Error Handling
class BybitAPIClient:
    def __init__(self, global_config: GlobalConfig, logger: logging.Logger):
        self.config = global_config
        self.logger = logger
        self.http_session = HTTP(
            testnet=self.config.testnet,
            api_key=self.config.api_key,
            api_secret=self.config.api_secret,
        )
        self.last_cancel_time = 0.0
        self.rate_limiter = RateLimiter(
            max_requests=60, time_window=60, logger=self.logger
        )

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

        return True

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
        """Runs a synchronous API call in a separate thread"""
        return await asyncio.to_thread(api_method, *args, **kwargs)

    async def _handle_response_async(
        self, coro: Coroutine[Any, Any, Any], action: str
    ) -> dict[str, Any]:
        """Processes API responses, checking for errors and raising custom exceptions"""
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
        elif ret_code == 10002:
            raise BybitAPIError(
                f"API {action} failed: {ret_msg}", ret_code=ret_code, ret_msg=ret_msg
            )
        else:
            raise BybitAPIError(
                f"API {action} failed: {ret_msg}", ret_code=ret_code, ret_msg=ret_msg
            )

    @retry_api_call()
    async def get_instruments_info_impl(
        self, category: str, symbol: str = None
    ) -> dict[str, Any]:
        """Get instrument info with retry logic"""
        return await self._handle_response_async(
            asyncio.to_thread(
                self.http_session.get_instruments_info, category=category, symbol=symbol
            ),
            "get_instruments_info",
        )

    @retry_api_call()
    async def get_wallet_balance_impl(
        self, account_type: str = "UNIFIED"
    ) -> dict[str, Any]:
        """Get wallet balance with retry logic"""
        return await self._handle_response_async(
            asyncio.to_thread(
                self.http_session.get_wallet_balance, accountType=account_type
            ),
            "get_wallet_balance",
        )

    @retry_api_call()
    async def get_position_info_impl(
        self, category: str, symbol: str = None
    ) -> dict[str, Any]:
        """Get position info with retry logic"""
        return await self._handle_response_async(
            asyncio.to_thread(
                self.http_session.get_position_info, category=category, symbol=symbol
            ),
            "get_position_info",
        )

    @retry_api_call()
    async def set_leverage_impl(
        self, category: str, symbol: str, buy_leverage: int, sell_leverage: int
    ) -> dict[str, Any]:
        """Set leverage with retry logic"""
        return await self._handle_response_async(
            asyncio.to_thread(
                self.http_session.set_leverage,
                category=category,
                symbol=symbol,
                buyLeverage=buy_leverage,
                sellLeverage=sell_leverage,
            ),
            "set_leverage",
        )

    @retry_api_call()
    async def get_open_orders_impl(
        self, category: str, symbol: str = None
    ) -> dict[str, Any]:
        """Get open orders with retry logic"""
        return await self._handle_response_async(
            asyncio.to_thread(
                self.http_session.get_open_orders, category=category, symbol=symbol
            ),
            "get_open_orders",
        )

    @retry_api_call()
    async def place_order_impl(
        self,
        category: str,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        price: str = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Place order with retry logic"""
        order_params = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
            **kwargs,
        }
        if price:
            order_params["price"] = price

        return await self._handle_response_async(
            asyncio.to_thread(self.http_session.place_order, **order_params),
            "place_order",
        )

    @retry_api_call()
    async def cancel_order_impl(
        self, category: str, symbol: str, order_id: str
    ) -> dict[str, Any]:
        """Cancel order with retry logic"""
        return await self._handle_response_async(
            asyncio.to_thread(
                self.http_session.cancel_order,
                category=category,
                symbol=symbol,
                orderId=order_id,
            ),
            "cancel_order",
        )

    @retry_api_call()
    async def cancel_all_orders_impl(
        self, category: str, symbol: str
    ) -> dict[str, Any]:
        """Cancel all orders with retry logic"""
        return await self._handle_response_async(
            asyncio.to_thread(
                self.http_session.cancel_all_orders, category=category, symbol=symbol
            ),
            "cancel_all_orders",
        )

    @retry_api_call()
    async def set_trading_stop_impl(
        self, category: str, symbol: str, **kwargs
    ) -> dict[str, Any]:
        """Set trading stop with retry logic"""
        return await self._handle_response_async(
            asyncio.to_thread(
                self.http_session.set_trading_stop,
                category=category,
                symbol=symbol,
                **kwargs,
            ),
            "set_trading_stop",
        )

    @retry_api_call()
    async def get_kline_impl(
        self, category: str, symbol: str, interval: str, limit: int = 100
    ) -> dict[str, Any]:
        """Get kline data with retry logic"""
        return await self._handle_response_async(
            asyncio.to_thread(
                self.http_session.get_kline,
                category=category,
                symbol=symbol,
                interval=interval,
                limit=limit,
            ),
            "get_kline",
        )

    async def place_batch_orders(
        self, orders: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Place multiple orders in a single batch request"""
        if not orders:
            return []

        results = []

        # Split orders into chunks of 10 (Bybit's batch limit)
        for i in range(0, len(orders), 10):
            chunk = orders[i : i + 10]
            try:
                response = await self._handle_response_async(
                    asyncio.to_thread(
                        self.http_session.place_batch_order,
                        category="linear",
                        orderList=chunk,
                    ),
                    "place_batch_order",
                )
                results.append(response)
                self.logger.info(f"Batch order placed: {len(chunk)} orders")
            except Exception as e:
                self.logger.error(f"Error placing batch orders: {e}")

        return results

    async def cancel_batch_orders(self, order_ids: list[str]) -> list[dict[str, Any]]:
        """Cancel multiple orders in a single batch request"""
        if not order_ids:
            return []

        results = []

        # Split orders into chunks of 10 (Bybit's batch limit)
        for i in range(0, len(order_ids), 10):
            chunk = order_ids[i : i + 10]
            try:
                response = await self._handle_response_async(
                    asyncio.to_thread(
                        self.http_session.cancel_batch_order,
                        category="linear",
                        request=[{"orderId": order_id} for order_id in chunk],
                    ),
                    "cancel_batch_order",
                )
                results.append(response)
                self.logger.info(f"Batch order cancelled: {len(chunk)} orders")
            except Exception as e:
                self.logger.error(f"Error cancelling batch orders: {e}")

        return results


# Rate Limiter
class RateLimiter:
    def __init__(self, max_requests: int, time_window: int, logger: logging.Logger):
        self.max_requests = max_requests
        self.time_window = time_window
        self.logger = logger
        self.requests = deque()
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = time.time()

            # Remove old requests
            while self.requests and self.requests[0] <= now - self.time_window:
                self.requests.popleft()

            # Check if we've exceeded the limit
            if len(self.requests) >= self.max_requests:
                sleep_time = self.time_window + self.requests[0] - now
                self.logger.warning(
                    f"Rate limit reached. Sleeping for {sleep_time:.2f} seconds"
                )
                await asyncio.sleep(sleep_time)
                # Remove expired requests after sleep
                while self.requests and self.requests[0] <= now - self.time_window:
                    self.requests.popleft()

            # Add current request
            self.requests.append(now)


# Enhanced Order Manager with Batch Operations and Risk Controls
class OrderManager:
    def __init__(
        self,
        global_config: GlobalConfig,
        symbol_config: SymbolConfig,
        api_client: BybitAPIClient,
        logger: logging.Logger,
    ):
        self.global_config = global_config
        self.symbol_config = symbol_config
        self.api_client = api_client
        self.logger = logger
        self.active_orders = {}
        self.last_order_time = 0
        self.order_lock = asyncio.Lock()

    async def place_orders(self, orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Place multiple orders with rate limiting and error handling"""
        async with self.order_lock:
            # Apply rate limiting
            await self.api_client.rate_limiter.acquire()

            try:
                # Place orders in batches
                results = await self.api_client.place_batch_orders(orders)

                # Update active orders
                for result in results:
                    if "orderId" in result:
                        self.active_orders[result["orderId"]] = {
                            "symbol": self.symbol_config.symbol,
                            "timestamp": time.time(),
                            **result,
                        }

                return results
            except Exception as e:
                self.logger.error(f"Error placing orders: {e}")
                return []

    async def cancel_orders(self, order_ids: list[str]) -> list[dict[str, Any]]:
        """Cancel multiple orders with rate limiting and error handling"""
        async with self.order_lock:
            # Apply rate limiting
            await self.api_client.rate_limiter.acquire()

            try:
                # Cancel orders in batches
                results = await self.api_client.cancel_batch_orders(order_ids)

                # Remove cancelled orders from active orders
                for result in results:
                    if "orderId" in result:
                        self.active_orders.pop(result["orderId"], None)

                return results
            except Exception as e:
                self.logger.error(f"Error cancelling orders: {e}")
                return []

    async def cancel_all_orders(self) -> list[dict[str, Any]]:
        """Cancel all active orders"""
        order_ids = list(self.active_orders.keys())
        if order_ids:
            return await self.cancel_orders(order_ids)
        return []

    async def get_active_orders(self) -> dict[str, dict[str, Any]]:
        """Get all active orders"""
        return self.active_orders

    async def update_order_status(self, order_id: str, status: str, **kwargs):
        """Update the status of an order"""
        if order_id in self.active_orders:
            self.active_orders[order_id]["status"] = status
            self.active_orders[order_id].update(kwargs)

    async def remove_order(self, order_id: str):
        """Remove an order from active orders"""
        self.active_orders.pop(order_id, None)

    async def get_order_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get order history with error handling"""
        try:
            response = await self.api_client.get_open_orders_impl(
                category=self.global_config.category, symbol=self.symbol_config.symbol
            )
            return response.get("list", [])
        except Exception as e:
            self.logger.error(f"Error getting order history: {e}")
            return []


# Enhanced Risk Manager with Trailing Stop Loss and Break-Even
class RiskManager:
    def __init__(
        self,
        global_config: GlobalConfig,
        symbol_config: SymbolConfig,
        api_client: BybitAPIClient,
        logger: logging.Logger,
    ):
        self.global_config = global_config
        self.symbol_config = symbol_config
        self.api_client = api_client
        self.logger = logger
        self.position = None
        self.entry_price = None
        self.stop_loss_price = None
        self.take_profit_price = None
        self.trailing_stop_distance = None
        self.break_even_price = None
        self.is_hedge_mode = False

    async def update_position(self, position_data: dict[str, Any]):
        """Update position information"""
        self.position = position_data
        if self.position and self.position.get("size", 0) != 0:
            self.entry_price = Decimal(str(self.position.get("avgPrice", 0)))
            self.logger.info(
                f"Position updated: size={self.position['size']}, entry_price={self.entry_price}"
            )
        else:
            self.entry_price = None
            self.stop_loss_price = None
            self.take_profit_price = None
            self.trailing_stop_distance = None
            self.break_even_price = None

    async def set_trailing_stop(
        self, distance: Decimal, activate_profit_bps: Decimal = Decimal("0")
    ):
        """Set trailing stop loss with activation condition"""
        if not self.position or self.position.get("size", 0) == 0:
            return

        position_side = "Long" if float(self.position["size"]) > 0 else "Short"
        trigger_direction = 2 if position_side == "Long" else 1
        qty = abs(Decimal(str(self.position["size"])))

        # Calculate activation price
        activate_price = None
        if activate_profit_bps > 0:
            if position_side == "Long":
                activate_price = self.entry_price * (
                    1 + activate_profit_bps / Decimal("10000")
                )
            else:
                activate_price = self.entry_price * (
                    1 - activate_profit_bps / Decimal("10000")
                )

        try:
            response = await self.api_client.set_trading_stop_impl(
                category=self.global_config.category,
                symbol=self.symbol_config.symbol,
                stopLoss="",
                takeProfit="",
                trailingStop=str(distance),
                triggerBy="MarkPrice",
                triggerDirection=trigger_direction,
                positionIdx=1 if self.is_hedge_mode else 0,
                activePrice=str(activate_price) if activate_price else "",
            )

            self.trailing_stop_distance = distance
            self.logger.info(
                f"Trailing stop set: distance={distance}, activate_price={activate_price}"
            )
        except Exception as e:
            self.logger.error(f"Error setting trailing stop: {e}")

    async def set_break_even(self, profit_bps: Decimal, offset_ticks: int = 1):
        """Set break-even stop loss"""
        if not self.position or self.position.get("size", 0) == 0:
            return

        position_side = "Long" if float(self.position["size"]) > 0 else "Short"

        # Calculate break-even price
        if position_side == "Long":
            be_price = self.entry_price * (1 + profit_bps / Decimal("10000"))
            # Add offset ticks
            tick_size = Decimal("0.1")  # Should be fetched from symbol config
            be_price += tick_size * offset_ticks
        else:
            be_price = self.entry_price * (1 - profit_bps / Decimal("10000"))
            # Subtract offset ticks
            tick_size = Decimal("0.1")  # Should be fetched from symbol config
            be_price -= tick_size * offset_ticks

        try:
            response = await self.api_client.set_trading_stop_impl(
                category=self.global_config.category,
                symbol=self.symbol_config.symbol,
                stopLoss=str(be_price),
                takeProfit="",
                trailingStop="",
                triggerBy="MarkPrice",
                triggerDirection=1 if position_side == "Long" else 2,
                positionIdx=1 if self.is_hedge_mode else 0,
            )

            self.break_even_price = be_price
            self.logger.info(f"Break-even set: price={be_price}")
        except Exception as e:
            self.logger.error(f"Error setting break-even: {e}")

    async def clear_stops(self):
        """Clear all stop losses"""
        try:
            response = await self.api_client.set_trading_stop_impl(
                category=self.global_config.category,
                symbol=self.symbol_config.symbol,
                stopLoss="",
                takeProfit="",
                trailingStop="",
                triggerBy="MarkPrice",
                triggerDirection=1,
                positionIdx=1 if self.is_hedge_mode else 0,
            )

            self.stop_loss_price = None
            self.take_profit_price = None
            self.trailing_stop_distance = None
            self.break_even_price = None
            self.logger.info("All stops cleared")
        except Exception as e:
            self.logger.error(f"Error clearing stops: {e}")

    async def check_risk_limits(self, proposed_position: Decimal) -> bool:
        """Check if proposed position exceeds risk limits"""
        current_position = (
            Decimal(str(self.position.get("size", 0)))
            if self.position
            else Decimal("0")
        )
        new_position = current_position + proposed_position

        # Check max position size
        if abs(new_position) > self.symbol_config.max_net_exposure_usd / Decimal(
            str(self.position.get("markPrice", 10000))
        ):
            self.logger.warning(
                f"Proposed position {new_position} exceeds max position size"
            )
            return False

        # Check circuit breaker
        if self.symbol_config.strategy.circuit_breaker.enabled:
            # Implement circuit breaker logic here
            pass

        return True


# Enhanced Market Data Manager with ATR Calculation
class MarketDataManager:
    def __init__(
        self,
        global_config: GlobalConfig,
        symbol_config: SymbolConfig,
        api_client: BybitAPIClient,
        logger: logging.Logger,
    ):
        self.global_config = global_config
        self.symbol_config = symbol_config
        self.api_client = api_client
        self.logger = logger
        self.mid_price = None
        self.bid_price = None
        self.ask_price = None
        self.last_update_time = 0
        self.kline_data = deque(maxlen=100)
        self.atr_value = None
        self.volatility = None
        self.price_history = deque(maxlen=100)

    async def update_market_data(self, data: dict[str, Any]):
        """Update market data from WebSocket"""
        try:
            if "topic" in data and data["topic"].startswith("orderbook.200."):
                book_data = data.get("data", {})
                if "b" in book_data and "a" in book_data:
                    self.bid_price = Decimal(str(book_data["b"][0][0]))
                    self.ask_price = Decimal(str(book_data["a"][0][0]))
                    self.mid_price = (self.bid_price + self.ask_price) / 2
                    self.last_update_time = time.time()

                    # Add to price history
                    self.price_history.append((time.time(), self.mid_price))

                    # Update volatility
                    self._calculate_volatility()

            elif "topic" in data and data["topic"].startswith("kline."):
                kline_data = data.get("data", {})
                if kline_data:
                    close_price = Decimal(str(kline_data["close"]))
                    self.kline_data.append(
                        {
                            "timestamp": kline_data["start"],
                            "open": Decimal(str(kline_data["open"])),
                            "high": Decimal(str(kline_data["high"])),
                            "low": Decimal(str(kline_data["low"])),
                            "close": close_price,
                            "volume": Decimal(str(kline_data["volume"])),
                        }
                    )

                    # Update ATR
                    self._calculate_atr()

        except Exception as e:
            self.logger.error(f"Error updating market data: {e}")

    def _calculate_volatility(self):
        """Calculate price volatility"""
        if len(self.price_history) < 10:
            return

        prices = [p[1] for p in list(self.price_history)[-10:]]
        returns = [
            (prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))
        ]
        self.volatility = np.std(returns) * 100  # Convert to percentage

    def _calculate_atr(self):
        """Calculate Average True Range"""
        if len(self.kline_data) < 14:
            return

        try:
            highs = [k["high"] for k in list(self.kline_data)[-14:]]
            lows = [k["low"] for k in list(self.kline_data)[-14:]]
            closes = [k["close"] for k in list(self.kline_data)[-14:]]

            tr = []
            for i in range(1, len(highs)):
                tr.append(
                    max(
                        highs[i] - lows[i],
                        abs(highs[i] - closes[i - 1]),
                        abs(lows[i] - closes[i - 1]),
                    )
                )

            self.atr_value = sum(tr) / len(tr)
        except Exception as e:
            self.logger.error(f"Error calculating ATR: {e}")

    async def get_spread(self) -> Decimal:
        """Calculate current spread with dynamic adjustment"""
        if not self.mid_price or not self.bid_price or not self.ask_price:
            return Decimal("0")

        base_spread = self.symbol_config.strategy.base_spread_pct

        # Apply dynamic spread based on volatility
        if self.symbol_config.strategy.dynamic_spread.enabled and self.volatility:
            dynamic_spread = min(
                self.symbol_config.strategy.dynamic_spread.max_spread_pct,
                max(
                    self.symbol_config.strategy.dynamic_spread.min_spread_pct,
                    base_spread
                    + (
                        self.volatility
                        * self.symbol_config.strategy.dynamic_spread.volatility_multiplier
                        / 100
                    ),
                ),
            )
        else:
            dynamic_spread = base_spread

        # Apply inventory skew
        if self.symbol_config.strategy.inventory_skew.enabled:
            # Implement inventory skew logic here
            pass

        return dynamic_spread

    async def get_order_prices(self) -> tuple[Decimal, Decimal]:
        """Get bid and ask prices for order placement"""
        if not self.mid_price:
            return Decimal("0"), Decimal("0")

        spread = await self.get_spread()
        half_spread = spread / 2

        bid_price = self.mid_price * (1 - half_spread)
        ask_price = self.mid_price * (1 + half_spread)

        return self.symbol_config.format_price(
            bid_price
        ), self.symbol_config.format_price(ask_price)

    async def get_order_quantity(self, price: Decimal) -> Decimal:
        """Calculate order quantity based on available balance"""
        try:
            balance_data = await self.api_client.get_wallet_balance_impl(
                account_type="UNIFIED"
            )
            usdt_balance = Decimal(
                str(balance_data.get("USDT", {}).get("walletBalance", 0))
            )

            # Calculate order size as percentage of balance
            order_value = (
                usdt_balance
                * self.symbol_config.strategy.base_order_size_pct_of_balance
            )
            quantity = order_value / price

            return self.symbol_config.format_quantity(quantity)
        except Exception as e:
            self.logger.error(f"Error calculating order quantity: {e}")
            return Decimal("0")


# Enhanced Market Making Strategy
class MarketMakingStrategy:
    def __init__(
        self,
        global_config: GlobalConfig,
        symbol_config: SymbolConfig,
        order_manager: OrderManager,
        risk_manager: RiskManager,
        market_data: MarketDataManager,
        logger: logging.Logger,
    ):
        self.global_config = global_config
        self.symbol_config = symbol_config
        self.order_manager = order_manager
        self.risk_manager = risk_manager
        self.market_data = market_data
        self.logger = logger
        self.is_running = False
        self.last_order_time = 0

    async def run(self):
        """Main market making strategy loop"""
        self.is_running = True
        self.logger.info(
            f"Starting market making strategy for {self.symbol_config.symbol}"
        )

        while self.is_running:
            try:
                # Check if we should pause
                if self._should_pause():
                    await asyncio.sleep(self.global_config.system.loop_interval_sec)
                    continue

                # Get market data
                if not self.market_data.mid_price:
                    await asyncio.sleep(self.global_config.system.loop_interval_sec)
                    continue

                # Get order prices and quantities
                bid_price, ask_price = await self.market_data.get_order_prices()
                bid_qty = await self.market_data.get_order_quantity(bid_price)
                ask_qty = await self.market_data.get_order_quantity(ask_price)

                # Check if we need to adjust orders
                await self._adjust_orders(bid_price, ask_price, bid_qty, ask_qty)

                # Update risk management
                await self._update_risk_management()

                # Sleep until next iteration
                await asyncio.sleep(self.global_config.system.loop_interval_sec)

            except Exception as e:
                self.logger.error(f"Error in market making strategy: {e}")
                await asyncio.sleep(self.global_config.system.loop_interval_sec)

    async def stop(self):
        """Stop market making strategy"""
        self.is_running = False
        self.logger.info(
            f"Stopping market making strategy for {self.symbol_config.symbol}"
        )

        # Cancel all orders
        await self.order_manager.cancel_all_orders()

        # Clear risk management stops
        await self.risk_manager.clear_stops()

    def _should_pause(self) -> bool:
        """Check if we should pause trading"""
        if self.symbol_config.strategy.circuit_breaker.enabled:
            # Implement circuit breaker logic here
            pass

        # Check if we're in trading hours
        if (
            self.symbol_config.trading_hours_start
            and self.symbol_config.trading_hours_end
        ):
            now = datetime.now(timezone.utc).time()
            start_time = datetime.strptime(
                self.symbol_config.trading_hours_start, "%H:%M"
            ).time()
            end_time = datetime.strptime(
                self.symbol_config.trading_hours_end, "%H:%M"
            ).time()

            if not (start_time <= now <= end_time):
                return True

        return False

    async def _adjust_orders(
        self, bid_price: Decimal, ask_price: Decimal, bid_qty: Decimal, ask_qty: Decimal
    ):
        """Adjust orders based on market conditions"""
        try:
            # Get current orders
            active_orders = await self.order_manager.get_active_orders()

            # Check if we need to cancel stale orders
            stale_orders = []
            for order_id, order in active_orders.items():
                order_price = Decimal(str(order.get("price", 0)))
                if (
                    abs(order_price - bid_price) / bid_price
                    > self.symbol_config.strategy.order_stale_threshold_pct
                ):
                    stale_orders.append(order_id)

            # Cancel stale orders
            if stale_orders:
                await self.order_manager.cancel_orders(stale_orders)

            # Place new orders if needed
            current_bid_orders = [
                o for o in active_orders.values() if o.get("side") == "Buy"
            ]
            current_ask_orders = [
                o for o in active_orders.values() if o.get("side") == "Sell"
            ]

            # Place bid orders if needed
            if (
                len(current_bid_orders)
                < self.symbol_config.strategy.max_outstanding_orders
            ):
                new_bid_orders = []
                for i in range(
                    self.symbol_config.strategy.max_outstanding_orders
                    - len(current_bid_orders)
                ):
                    order_id = str(uuid.uuid4())
                    new_bid_orders.append(
                        {
                            "symbol": self.symbol_config.symbol,
                            "side": "Buy",
                            "orderType": "Limit",
                            "qty": str(bid_qty),
                            "price": str(bid_price),
                            "timeInForce": "GoodTillCancel",
                            "orderLinkId": f"BID_{order_id}",
                        }
                    )

                if new_bid_orders:
                    await self.order_manager.place_orders(new_bid_orders)

            # Place ask orders if needed
            if (
                len(current_ask_orders)
                < self.symbol_config.strategy.max_outstanding_orders
            ):
                new_ask_orders = []
                for i in range(
                    self.symbol_config.strategy.max_outstanding_orders
                    - len(current_ask_orders)
                ):
                    order_id = str(uuid.uuid4())
                    new_ask_orders.append(
                        {
                            "symbol": self.symbol_config.symbol,
                            "side": "Sell",
                            "orderType": "Limit",
                            "qty": str(ask_qty),
                            "price": str(ask_price),
                            "timeInForce": "GoodTillCancel",
                            "orderLinkId": f"ASK_{order_id}",
                        }
                    )

                if new_ask_orders:
                    await self.order_manager.place_orders(new_ask_orders)

        except Exception as e:
            self.logger.error(f"Error adjusting orders: {e}")

    async def _update_risk_management(self):
        """Update risk management based on current position"""
        try:
            # Get position data
            position_data = await self.api_client.get_position_info(
                category=self.global_config.category, symbol=self.symbol_config.symbol
            )

            # Update risk manager
            await self.risk_manager.update_position(position_data)

            # Set trailing stop if enabled
            if (
                self.symbol_config.strategy.enable_auto_sl_tp
                and position_data.get("size", 0) != 0
            ):
                if not self.risk_manager.trailing_stop_distance:
                    # Set initial trailing stop
                    trailing_distance = (
                        self.symbol_config.strategy.stop_loss_trigger_pct
                        * self.market_data.mid_price
                        / 100
                    )
                    await self.risk_manager.set_trailing_stop(trailing_distance)
                elif (
                    self.risk_manager.break_even_price
                    and self.market_data.mid_price > self.risk_manager.break_even_price
                ):
                    # Move to break-even if in profit
                    await self.risk_manager.set_break_even(
                        self.symbol_config.strategy.take_profit_target_pct,
                        offset_ticks=1,
                    )

        except Exception as e:
            self.logger.error(f"Error updating risk management: {e}")


# Enhanced State Manager with Persistence
class StateManager:
    def __init__(self, file_path: Path, logger: logging.Logger):
        self.file_path = file_path
        self.logger = logger

    async def save_state(self, state: dict[str, Any]) -> None:
        """Saves the bot's current state to a JSON file atomically"""
        try:
            temp_path = self.file_path.with_suffix(f".tmp_{os.getpid()}")
            async with aiofiles.open(temp_path, "w") as f:
                await f.write(json.dumps(state, indent=4, cls=JsonDecimalEncoder))
            os.replace(temp_path, self.file_path)
            self.logger.info(f"State saved successfully to {self.file_path.name}.")
        except Exception as e:
            self.logger.error(
                f"Error saving state to {self.file_path.name}: {e}", exc_info=True
            )

    async def load_state(self) -> dict[str, Any] | None:
        """Loads the bot's state from a JSON file"""
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
            try:
                self.file_path.rename(
                    self.file_path.with_suffix(f".corrupted_{int(time.time())}")
                )
            except OSError as ose:
                self.logger.warning(
                    f"Could not rename corrupted state file {self.file_path.name}: {ose}"
                )
            return None


# Enhanced Database Manager
class DBManager:
    def __init__(self, db_file: Path, logger: logging.Logger):
        self.db_file = db_file
        self.conn: aiosqlite.Connection | None = None
        self.logger = logger

    async def connect(self) -> None:
        """Establishes a connection to the SQLite database"""
        try:
            self.conn = await aiosqlite.connect(self.db_file)
            self.conn.row_factory = aiosqlite.Row
            self.logger.info(f"Connected to database: {self.db_file.name}")
        except Exception as e:
            self.logger.critical(f"Failed to connect to database: {e}", exc_info=True)
            sys.exit(1)

    async def close(self) -> None:
        """Closes the database connection"""
        if self.conn:
            await self.conn.close()
            self.logger.info("Database connection closed.")

    async def create_tables(self) -> None:
        """Creates necessary tables if they do not already exist"""
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

        # Ensure all columns exist
        await _add_column_if_not_exists("order_events", "symbol", "TEXT", "''")
        await _add_column_if_not_exists("order_events", "reduce_only", "BOOLEAN", "0")
        await _add_column_if_not_exists("trade_fills", "symbol", "TEXT", "''")
        await _add_column_if_not_exists("bot_metrics", "symbol", "TEXT", "''")
        await _add_column_if_not_exists("bot_metrics", "mid_price", "TEXT", "'0'")

        await self.conn.commit()
        self.logger.info("Database tables checked/created and migrated.")

    async def log_order_event(
        self, symbol: str, order_data: dict[str, Any], message: str | None = None
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
        self, symbol: str, trade_data: dict[str, Any], realized_pnl_impact: Decimal
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
        available_balance: Decimal | None = None,
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


# Enhanced Main Bot Class
class MarketMakerBot:
    def __init__(self, single_symbol: str | None = None):
        # Load configuration
        self.global_config, self.symbol_configs = ConfigManager.load_config(
            single_symbol
        )
        self.symbol = (
            single_symbol if single_symbol else next(iter(self.symbol_configs.keys()))
        )
        self.symbol_config = self.symbol_configs[self.symbol]

        # Setup logger
        self.logger = setup_logger(self.global_config.files, f"bot_{self.symbol}")

        # Initialize components
        self.api_client = BybitAPIClient(self.global_config, self.logger)
        self.ws_manager = WebSocketManager(self.global_config, self.logger)
        self.order_manager = OrderManager(
            self.global_config, self.symbol_config, self.api_client, self.logger
        )
        self.risk_manager = RiskManager(
            self.global_config, self.symbol_config, self.api_client, self.logger
        )
        self.market_data = MarketDataManager(
            self.global_config, self.symbol_config, self.api_client, self.logger
        )
        self.strategy = MarketMakingStrategy(
            self.global_config,
            self.symbol_config,
            self.order_manager,
            self.risk_manager,
            self.market_data,
            self.logger,
        )
        self.state_manager = StateManager(
            STATE_DIR / self.global_config.files.state_file, self.logger
        )
        self.db_manager = DBManager(
            LOG_DIR / self.global_config.files.db_file, self.logger
        )

        # Trading state
        self.trading_state = TradingState()
        self.is_running = False
        self.shutdown_event = asyncio.Event()

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.shutdown_event.set()

    async def initialize(self):
        """Initialize the bot"""
        try:
            # Connect to database
            await self.db_manager.connect()
            await self.db_manager.create_tables()

            # Get initial market data
            await self._load_market_data()

            # Set initial leverage (only for TESTNET or LIVE modes)
            if self.global_config.trading_mode in ["TESTNET", "LIVE"]:
                await self.api_client.set_leverage_impl(
                    category=self.global_config.category,
                    symbol=self.symbol_config.symbol,
                    buy_leverage=self.symbol_config.leverage,
                    sell_leverage=self.symbol_config.leverage,
                )
            else:
                self.logger.info(
                    f"Skipping leverage setting in {self.global_config.trading_mode} mode."
                )

            # Load saved state if available
            saved_state = await self.state_manager.load_state()
            if saved_state:
                self.logger.info("Loaded saved state")
                # Apply saved state to trading state
                # ...

            self.logger.info(f"Bot initialized for {self.symbol_config.symbol}")

        except Exception as e:
            self.logger.critical(f"Error during initialization: {e}", exc_info=True)
            raise

    async def _load_market_data(self):
        """Load initial market data"""
        try:
            # Get order book
            orderbook = await self.api_client.get_instruments_info_impl(
                category=self.global_config.category, symbol=self.symbol_config.symbol
            )

            # Get kline data for ATR calculation
            kline = await self.api_client.get_kline_impl(
                category=self.global_config.category,
                symbol=self.symbol_config.symbol,
                interval=self.symbol_config.strategy.kline_interval,
                limit=100,
            )

            # Process initial data
            # ...

        except Exception as e:
            self.logger.error(f"Error loading initial market data: {e}")

    async def run(self):
        """Main bot loop"""
        try:
            await self.initialize()
            self.is_running = True

            # Start WebSocket connections
            await self.ws_manager.start(
                public_callback=self._handle_public_message,
                private_callback=self._handle_private_message,
            )

            # Start strategy
            strategy_task = asyncio.create_task(self.strategy.run())

            # Start status reporting
            status_task = asyncio.create_task(self._status_reporter())

            # Wait for shutdown event
            await self.shutdown_event.wait()

        except Exception as e:
            self.logger.critical(f"Error in main loop: {e}", exc_info=True)
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Gracefully shutdown the bot"""
        self.logger.info("Shutting down bot...")

        # Stop strategy
        await self.strategy.stop()

        # Stop WebSocket manager
        await self.ws_manager.stop()

        # Cancel all orders
        await self.order_manager.cancel_all_orders()

        # Clear risk management stops
        await self.risk_manager.clear_stops()

        # Save state
        await self.state_manager.save_state(self._get_state_dict())

        # Close database connection
        await self.db_manager.close()

        self.logger.info("Bot shutdown complete")
        self.is_running = False

    def _get_state_dict(self) -> dict[str, Any]:
        """Get current state as dictionary"""
        return {
            "symbol": self.symbol,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trading_state": dataclasses.asdict(self.trading_state),
            # Add other state information as needed
        }

    async def _handle_public_message(self, msg: dict[str, Any]):
        """Handle public WebSocket messages"""
        try:
            await self.market_data.update_market_data(msg)
        except Exception as e:
            self.logger.error(f"Error handling public message: {e}")

    async def _handle_private_message(self, msg: dict[str, Any]):
        """Handle private WebSocket messages"""
        try:
            if "topic" in msg:
                if msg["topic"] == "position":
                    # Update position
                    position_data = msg.get("data", {})
                    await self.risk_manager.update_position(position_data)

                elif msg["topic"] == "order":
                    # Update order status
                    order_data = msg.get("data", {})
                    order_id = order_data.get("orderId")
                    status = order_data.get("orderStatus")

                    if order_id:
                        if status == "Filled":
                            # Handle fill
                            await self._handle_order_fill(order_data)
                        elif status in ["Cancelled", "Rejected"]:
                            # Remove order
                            await self.order_manager.remove_order(order_id)
                        else:
                            # Update order status
                            await self.order_manager.update_order_status(
                                order_id, status
                            )

        except Exception as e:
            self.logger.error(f"Error handling private message: {e}")

    async def _handle_order_fill(self, order_data: dict[str, Any]):
        """Handle order fill"""
        try:
            # Calculate realized PnL
            side = order_data.get("side")
            qty = Decimal(str(order_data.get("cumExecQty", 0)))
            price = Decimal(str(order_data.get("price", 0)))

            if side == "Buy":
                self.trading_state.metrics.update_pnl_on_buy(qty, price)
            else:
                self.trading_state.metrics.update_pnl_on_sell(qty, price)

            # Log to database
            await self.db_manager.log_trade_fill(
                symbol=self.symbol,
                trade_data=order_data,
                realized_pnl_impact=Decimal("0"),  # Calculate actual PnL
            )

            # Log metrics
            unrealized_pnl = self.trading_state.metrics.calculate_unrealized_pnl(
                self.market_data.mid_price
            )
            await self.db_manager.log_bot_metrics(
                symbol=self.symbol,
                metrics=self.trading_state.metrics,
                unrealized_pnl=unrealized_pnl,
                daily_pnl=self.trading_state.metrics.realized_pnl,
                daily_loss_pct=0.0,  # Calculate actual daily loss percentage
                mid_price=self.market_data.mid_price,
            )

        except Exception as e:
            self.logger.error(f"Error handling order fill: {e}")

    async def _status_reporter(self):
        """Periodically report bot status"""
        while self.is_running:
            try:
                # Calculate metrics
                unrealized_pnl = self.trading_state.metrics.calculate_unrealized_pnl(
                    self.market_data.mid_price
                )

                # Log status
                self.logger.info(
                    f"Status - Mid: {self.market_data.mid_price:.2f}, "
                    f"Position: {self.trading_state.current_position_qty:.4f}, "
                    f"PnL: {self.trading_state.metrics.net_realized_pnl:.2f}, "
                    f"Unrealized: {unrealized_pnl:.2f}, "
                    f"Orders: {len(self.order_manager.active_orders)}"
                )

                # Sleep until next report
                await asyncio.sleep(
                    self.global_config.system.status_report_interval_sec
                )

            except Exception as e:
                self.logger.error(f"Error in status reporter: {e}")
                await asyncio.sleep(
                    self.global_config.system.status_report_interval_sec
                )


# Main entry point
async def main():
    # Parse command line arguments
    single_symbol = None
    if len(sys.argv) > 1:
        single_symbol = sys.argv[1]

    # Create and run bot
    bot = MarketMakerBot(single_symbol)
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
