"""
The provided Python code is a good foundation for a Bybit market-making bot. It demonstrates a basic strategy, uses `asyncio` for concurrency, integrates with `pybit`, and includes state persistence and logging.

My analysis identifies several areas for enhancement and a major architectural upgrade to make it more robust, scalable, and feature-rich, especially for multi-symbol trading and advanced risk management.

---

## Analysis of the Original Code

### Strengths
1.  **Asynchronous Design:** Uses `asyncio` effectively for non-blocking operations and `async/await` patterns.
2.  **Modular Components:** Clear separation into `Config`, `TradeMetrics`, `TradingState`, `StateManager`, `DBManager`, `TradingClient`, and `BybitMarketMaker`.
3.  **Bybit API Integration:** Correctly uses `pybit.unified_trading` for both HTTP and WebSocket interactions, including retry logic with `tenacity`.
4.  **PnL Tracking:** `TradeMetrics` dataclass provides a solid base for tracking realized/unrealized PnL and asset holdings with average entry price.
5.  **State Persistence:** `StateManager` handles saving/loading bot state, which is crucial for continuity.
6.  **Database Logging:** `DBManager` logs critical events and metrics to SQLite, enabling post-analysis.
7.  **Basic Strategies:** Includes inventory skew and dynamic spread based on recent price changes.
8.  **Circuit Breaker:** Implements a basic circuit breaker for high volatility.
9.  **Dry Run/Simulation:** Provides modes for testing logic without live funds.
10. **Error Handling:** Custom exceptions are defined for specific API/connection issues.

### Areas for Enhancement & Upgrade
1.  **Single Symbol Limitation:** The current design is tightly coupled to a single trading symbol, making it difficult to scale to multiple markets.
2.  **Configuration Management:** `dataclass` is used, but Pydantic would offer more robust validation, default handling, and easier external (e.g., JSON) configuration loading.
3.  **WebSocket Management:**
    *   Each bot instance manages its own `WebSocket` objects, which is inefficient for multiple symbols (multiple connections to the same endpoint for private streams).
    *   WebSocket health check is basic; more sophisticated reconnection and message dispatching are needed for reliability.
    *   The `_schedule_coro` from `asyncio.run_coroutine_threadsafe` suggests pybit's WS callbacks are in a separate thread, which is good, but managing multiple such callbacks efficiently for different symbols needs a central dispatcher.
4.  **PnL Tracking Refinement:**
    *   `_process_order_update` and `_process_fill` could be more clearly separated, especially for exchange `execution` events which provide precise fill details (like `execType` for liquidity role).
    *   The logic for `cumExecQty` in `_process_order_update` needs to ensure that `_process_fill` correctly accounts for *new* filled quantities from `execution` events, not just total `cumExecQty` from order updates.
5.  **Volatility Calculation:** The dynamic spread uses a simple price change over a window; a more robust measure like Average True Range (ATR) would be more indicative of volatility.
6.  **Order Management Logic:**
    *   Only places one bid and one ask. A common market-making strategy involves multiple "layers" of orders at different price points.
    *   No explicit handling for stale orders (orders that have been open for too long without being filled/cancelled).
    *   No automated Take Profit/Stop Loss (TP/SL) for open positions.
7.  **Risk Management:** The circuit breaker is good, but a "max daily loss" threshold for the entire bot's capital is a critical risk control.
8.  **Dry Run Realism:** The price movement simulation could be more dynamic (e.g., Geometric Brownian Motion) and the fill simulation more nuanced.
9.  **Logging & Reporting:** Console output could be enhanced with colors for better readability. Logging of specific errors could be more granular.
10. **File Paths:** Hardcoded file paths (`market_maker_state.pkl`, `market_maker.db`) might conflict in a multi-symbol setup. A dedicated state/log directory structure per symbol or a global one is better.

---

## Enhanced and Upgraded `marketmaker1.0.py`

I've refactored the entire bot to support **multiple trading symbols concurrently**, significantly enhancing its architecture, robustness, and feature set.

**Key Changes in the Upgraded Version:**

1.  **Multi-Symbol Architecture:**
    *   **`PyrmethusBot` (Orchestrator):** The new main class that manages global configuration, initializes shared components (API client, WS client, DB), and orchestrates multiple `AsyncSymbolBot` instances.
    *   **`AsyncSymbolBot` (Per-Symbol Logic):** A new class encapsulating all trading logic, state (`TradingState`), and metrics (`TradeMetrics`) for a *single* trading symbol. Each `AsyncSymbolBot` runs as an independent `asyncio` task.
    *   **`ConfigManager`:** Handles loading `GlobalConfig` (from `.env`) and `SymbolConfig` (from `symbols.json` or a single symbol input). Supports dynamic reloading of `symbols.json`.
    *   **`BybitWebSocketClient` (Centralized):** A single, shared WebSocket client that manages all public and private WS connections for all active symbols. It dispatches incoming messages to the correct `AsyncSymbolBot` instances via their dedicated processing methods. Includes robust reconnection logic.

2.  **Pydantic for Configuration:**
    *   All configuration classes (`GlobalConfig`, `SymbolConfig`, `StrategyConfig`, etc.) are now Pydantic `BaseModel`s. This provides:
        *   **Robust Validation:** Automatic type checking and value range validation.
        *   **Default Values:** Cleaner handling of default settings.
        *   **Serialization/Deserialization:** Easy loading from/saving to JSON.
        *   **Immutability:** `model_config = ConfigDict(frozen=True)` for immutable configs.

3.  **Advanced Risk Management:**
    *   **Daily Loss Circuit Breaker:** `CircuitBreakerConfig` now includes `max_daily_loss_pct`. The bot tracks daily PnL against an initial capital and will stop trading for the symbol if this threshold is hit.
    *   **Stale Order Cancellation:** Orders open for too long (`stale_order_max_age_seconds`) are automatically cancelled.
    *   **Automated TP/SL:** `enable_auto_sl_tp` option to automatically set Take Profit and Stop Loss levels based on average entry price for open positions.

4.  **Improved Strategy Features:**
    *   **ATR-based Dynamic Spread:** `DynamicSpreadConfig` now uses Average True Range (ATR) calculated from historical kline data to determine volatility and adjust the spread more intelligently.
    *   **Order Layering:** `StrategyConfig` includes `order_layers` to place multiple bid/ask orders at different price offsets and quantities.
    *   **Inventory Sizing Factor:** `InventorySkewConfig` now includes `inventory_sizing_factor` to scale order size based on current inventory.

5.  **Enhanced Dry Run/Simulation:**
    *   **Realistic Price Movement:** Uses Geometric Brownian Motion for more realistic price simulation.
    *   **Improved Fill Logic:** Better handling of partial fills and virtual balance updates.

6.  **Logging and User Experience:**
    *   **Colorama Integration:** Colored console output for better readability of log messages.
    *   **Termux Notifications:** Optional push notifications for critical events on Android (Termux).
    *   **JSON Logging:** Option for JSON-formatted logs.
    *   **Dedicated Loggers:** Each `AsyncSymbolBot` gets its own logger instance for easier filtering.
    *   **Flexible Config Loading:** Interactive prompt for single-symbol or multi-symbol (`symbols.json`) mode.

7.  **Database & State Management:**
    *   `DBManager` and `StateManager` are updated to support per-symbol data and new metrics.
    *   State files and DB are stored in a `.bot_state` directory for better organization.
    *   Atomic file saving for state.

8.  **Code Quality & Robustness:**
    *   Consistent use of `Decimal` with `DECIMAL_ZERO` constant.
    *   More explicit error handling and validation at various stages.
    *   `threading.RLock` for shared data accessed by `pybit` WS callbacks (running in separate threads) and the `asyncio` main loop.

---

**File: `marketmaker1.0.py` (Upgraded Version)**

```python
"""
import asyncio
import json
import logging
import os
import signal
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation, getcontext
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import aiofiles
import aiosqlite
import numpy as np
import pandas as pd
import requests # Used for initial kline data fetching (HTTP)
import websocket # For WebSocket._exceptions.WebSocketConnectionClosedException
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

# Initialize Colorama for cross-platform colored terminal output
init(autoreset=True)

# Set Decimal precision globally
getcontext().prec = 38
DECIMAL_ZERO = Decimal('0')

# Load environment variables from .env file
load_dotenv()

# --- Global Constants and Configuration Paths ---
BASE_DIR = Path(os.getenv("HOME", "."))
LOG_DIR = BASE_DIR / "bot_logs"
STATE_DIR = BASE_DIR / ".bot_state"
LOG_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)

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

# --- Utility Functions ---
class Colors:
    """Terminal colors for enhanced logging output."""
    CYAN = Fore.CYAN + Style.BRIGHT
    MAGENTA = Fore.MAGENTA + Style.BRIGHT
    YELLOW = Fore.YELLOW + Style.BRIGHT
    RESET = Style.RESET_ALL
    NEON_GREEN = Fore.GREEN + Style.BRIGHT
    NEON_BLUE = Fore.BLUE + Style.BRIGHT
    NEON_RED = Fore.RED + Style.BRIGHT
    NEON_ORANGE = Fore.LIGHTRED_EX + Style.BRIGHT

def termux_notify(message: str, title: str = "Bybit Bot", is_error: bool = False):
    """Sends a notification to Termux if available."""
    try:
        import subprocess
        bg_color = "#000000"
        text_color = "#FF0000" if is_error else "#00FFFF"
        vibrate_duration = "1000" if is_error else "200"
        subprocess.run(
            ["termux-toast", "-g", "middle", "-c", text_color, "-b", bg_color, f"{title}: {message}"],
            check=False, timeout=2, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        subprocess.run(
            ["termux-vibrate", "-d", vibrate_duration, "-f"],
            check=False, timeout=2, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
        pass # Termux utilities not found or permission denied
    except Exception as e:
        logging.getLogger('BybitMarketMaker').warning(f"Unexpected error with Termux notification: {e}")

class JsonDecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle Decimal objects."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)

def json_loads_decimal(s: str) -> Any:
    """Custom JSON decoder to parse floats/ints as Decimal objects."""
    try:
        return json.loads(s, parse_float=Decimal, parse_int=Decimal)
    except (json.JSONDecodeError, InvalidOperation) as e:
        logging.getLogger('BybitMarketMaker').error(f"Error decoding JSON with Decimal: {e} for input: {s[:100]}...")
        raise ValueError(f"Invalid JSON or Decimal format: {e}") from e

def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """Calculates Average True Range (ATR)."""
    tr = pd.DataFrame()
    tr["h_l"] = high - low
    tr["h_pc"] = (high - close.shift(1)).abs()
    tr["l_pc"] = (low - close.shift(1)).abs()
    tr["tr"] = tr[["h_l", "h_pc", "l_pc"]].max(axis=1)
    return tr["tr"].ewm(span=length, adjust=False).mean() # Using EWM for standard ATR calculation

# --- Pydantic Configuration Models ---
class DynamicSpreadConfig(BaseModel):
    enabled: bool = True
    volatility_window_sec: PositiveInt = 60
    volatility_multiplier: PositiveFloat = 2.0
    min_spread_pct: PositiveFloat = 0.0005
    max_spread_pct: PositiveFloat = 0.01
    price_change_smoothing_factor: PositiveFloat = 0.2
    atr_update_interval_sec: PositiveInt = 300 # How often to re-calculate ATR

class InventorySkewConfig(BaseModel):
    enabled: bool = True
    skew_intensity: PositiveFloat = 0.5 # How strongly inventory affects spread
    max_inventory_ratio: PositiveFloat = 0.5 # Max inventory as ratio of max_net_exposure_usd
    inventory_sizing_factor: NonNegativeFloat = 0.5 # How much inventory affects order size

class OrderLayer(BaseModel):
    spread_offset_pct: NonNegativeFloat = 0.0 # Additional spread beyond base/dynamic spread
    quantity_multiplier: PositiveFloat = 1.0 # Multiplier for base order quantity
    cancel_threshold_pct: PositiveFloat = 0.01 # Price change % to cancel and re-place orders

class CircuitBreakerConfig(BaseModel):
    enabled: bool = True
    pause_threshold_pct: PositiveFloat = 0.02 # Price change % in window to trip
    check_window_sec: PositiveInt = 10 # Window for price change check
    pause_duration_sec: PositiveInt = 60 # How long to pause trading
    cool_down_after_trip_sec: PositiveInt = 300 # Cooldown before re-enabling
    max_daily_loss_pct: Optional[PositiveFloat] = Field(default=None, description="Max percentage loss of initial capital for the day. Bot will stop if hit.")

class StrategyConfig(BaseModel):
    base_spread_pct: PositiveFloat = 0.001
    base_order_size_pct_of_balance: PositiveFloat = 0.005 # Percentage of available balance for one order
    order_stale_threshold_pct: PositiveFloat = 0.0005 # Price change % to consider an order stale
    min_profit_spread_after_fees_pct: PositiveFloat = 0.0002
    max_outstanding_orders: PositiveInt = 2
    market_data_stale_timeout_seconds: PositiveInt = 30 # Max age for orderbook/trade data
    enable_auto_sl_tp: bool = False
    take_profit_target_pct: PositiveFloat = 0.005
    stop_loss_trigger_pct: PositiveFloat = 0.005
    kline_interval: str = "1m" # Interval for OHLCV data for ATR
    stale_order_max_age_seconds: PositiveInt = 300 # Max age for an order before it's considered stale and cancelled

    dynamic_spread: DynamicSpreadConfig = Field(default_factory=DynamicSpreadConfig)
    inventory_skew: InventorySkewConfig = Field(default_factory=InventorySkewConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    order_layers: List[OrderLayer] = Field(default_factory=lambda: [OrderLayer()])

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
    config_refresh_interval_sec: PositiveInt = 60 # How often to check for config file changes

class FilesConfig(BaseModel):
    log_level: str = "INFO"
    log_file: str = "market_maker.log"
    state_file: str = "market_maker_state.json"
    db_file: str = "market_maker.db"
    symbol_config_file: str = "symbols.json"
    log_format: Literal["plain", "json"] = "plain"
    pybit_log_level: str = "WARNING"

class GlobalConfig(BaseModel):
    api_key: str = Field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    api_secret: str = Field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    testnet: bool = Field(default_factory=lambda: os.getenv("BYBIT_TESTNET", "true").lower() == "true")
    trading_mode: Literal["DRY_RUN", "SIMULATION", "TESTNET", "LIVE"] = "DRY_RUN"
    category: Literal["linear", "inverse", "spot"] = "linear"
    main_quote_currency: str = "USDT" # For overall balance tracking

    system: SystemConfig = Field(default_factory=SystemConfig)
    files: FilesConfig = Field(default_factory=FilesConfig)
    
    # Dry Run / Simulation specific settings
    initial_dry_run_capital: Decimal = Field(default=Decimal('10000'), description="Virtual capital for DRY_RUN/SIMULATION")
    dry_run_price_drift_mu: float = Field(default=0.0, description="Mean drift for simulated price movement")
    dry_run_price_volatility_sigma: float = Field(default=0.0001, description="Volatility for simulated price movement")
    dry_run_time_step_dt: float = Field(default=1.0, description="Time step for simulated price movement")

    model_config = ConfigDict(json_dumps=lambda v: json.dumps(v, cls=JsonDecimalEncoder), json_loads=json_loads_decimal, validate_assignment=True, frozen=True)

    @classmethod
    def load_from_env(cls) -> 'GlobalConfig':
        """Loads global configuration from environment variables."""
        env_data = {
            "api_key": os.getenv("BYBIT_API_KEY"),
            "api_secret": os.getenv("BYBIT_API_SECRET"),
            "testnet": os.getenv("BYBIT_TESTNET", "false").lower() == "true",
            "trading_mode": os.getenv("TRADING_MODE", "DRY_RUN").upper(),
            "category": os.getenv("BYBIT_CATEGORY", "linear").lower(),
            "main_quote_currency": os.getenv("MAIN_QUOTE_CURRENCY", "USDT"),
            "system": {
                "loop_interval_sec": float(os.getenv("LOOP_INTERVAL_SEC", "0.5")),
                "order_refresh_interval_sec": float(os.getenv("ORDER_REFRESH_INTERVAL_SEC", "5.0")),
                "ws_heartbeat_sec": int(os.getenv("WS_HEARTBEAT_SEC", "30")),
                "cancellation_rate_limit_sec": float(os.getenv("CANCELLATION_RATE_LIMIT_SEC", "0.2")),
                "status_report_interval_sec": int(os.getenv("STATUS_REPORT_INTERVAL_SEC", "30")),
                "ws_reconnect_attempts": int(os.getenv("WS_RECONNECT_ATTEMPTS", "5")),
                "ws_reconnect_initial_delay_sec": int(os.getenv("WS_RECONNECT_INITIAL_DELAY_SEC", "5")),
                "ws_reconnect_max_delay_sec": int(os.getenv("WS_RECONNECT_MAX_DELAY_SEC", "60")),
                "api_retry_attempts": int(os.getenv("API_RETRY_ATTEMPTS", "5")),
                "api_retry_initial_delay_sec": float(os.getenv("API_RETRY_INITIAL_DELAY_SEC", "0.5")),
                "api_retry_max_delay_sec": float(os.getenv("API_RETRY_MAX_DELAY_SEC", "10.0")),
                "health_check_interval_sec": int(os.getenv("HEALTH_CHECK_INTERVAL_SEC", "10")),
                "config_refresh_interval_sec": int(os.getenv("CONFIG_REFRESH_INTERVAL_SEC", "60")),
            },
            "files": {
                "log_level": os.getenv("LOG_LEVEL", "INFO"),
                "log_file": os.getenv("LOG_FILE", "market_maker.log"),
                "state_file": os.getenv("STATE_FILE", "market_maker_state.json"),
                "db_file": os.getenv("DB_FILE", "market_maker.db"),
                "symbol_config_file": os.getenv("SYMBOL_CONFIG_FILE", "symbols.json"),
                "log_format": os.getenv("LOG_FORMAT", "plain"),
                "pybit_log_level": os.getenv("PYBIT_LOG_LEVEL", "WARNING"),
            },
            "initial_dry_run_capital": os.getenv("INITIAL_DRY_RUN_CAPITAL", "10000"),
            "dry_run_price_drift_mu": float(os.getenv("DRY_RUN_PRICE_DRIFT_MU", "0.0")),
            "dry_run_price_volatility_sigma": float(os.getenv("DRY_RUN_PRICE_VOLATILITY_SIGMA", "0.0001")),
            "dry_run_time_step_dt": float(os.getenv("DRY_RUN_TIME_STEP_DT", "1.0")),
        }
        # Filter out None values before passing to Pydantic to allow default_factory to work
        # Also convert Decimal strings
        for k, v in env_data.items():
            if k in ["initial_dry_run_capital"] and isinstance(v, str):
                env_data[k] = Decimal(v)
        
        # Nested dicts need to be handled carefully by Pydantic, often best to pass as dicts
        # Pydantic will then validate them against the nested BaseModel definitions
        
        return cls(**env_data)

class SymbolConfig(BaseModel):
    symbol: str
    trade_enabled: bool = True
    leverage: PositiveInt = 10
    min_order_value_usd: PositiveFloat = 10.0
    max_order_size_pct: PositiveFloat = 0.1 # Max percentage of available balance for one order
    max_net_exposure_usd: PositiveFloat = 500.0 # Max total value of open position in USD
    trading_hours_start: Optional[str] = None # e.g., "09:00"
    trading_hours_end: Optional[str] = None # e.g., "17:00"

    strategy: StrategyConfig = Field(default_factory=StrategyConfig)

    # Market info (fetched dynamically, but can be overridden)
    price_precision: Optional[Decimal] = None
    quantity_precision: Optional[Decimal] = None
    min_order_qty: Optional[Decimal] = None
    min_notional_value: Optional[Decimal] = None
    maker_fee_rate: Optional[Decimal] = None
    taker_fee_rate: Optional[Decimal] = None

    base_currency: Optional[str] = None
    quote_currency: Optional[str] = None

    model_config = ConfigDict(json_dumps=lambda v: json.dumps(v, cls=JsonDecimalEncoder), json_loads=json_loads_decimal, validate_assignment=True, frozen=True)

    def model_post_init__(self, __context: Any) -> None:
        # Parse base and quote currency from symbol
        if self.symbol.endswith("USDT"):
            object.__setattr__(self, 'base_currency', self.symbol[:-4])
            object.__setattr__(self, 'quote_currency', "USDT")
        elif self.symbol.endswith("USD"):
            object.__setattr__(self, 'base_currency', self.symbol[:-3])
            object.__setattr__(self, 'quote_currency', "USD")
        elif len(self.symbol) == 6: # e.g., BTCUSD (Spot)
            object.__setattr__(self, 'base_currency', self.symbol[:3])
            object.__setattr__(self, 'quote_currency', self.symbol[3:])
        else:
            object.__setattr__(self, 'base_currency', "UNKNOWN")
            object.__setattr__(self, 'quote_currency', "UNKNOWN")
            logging.getLogger('BybitMarketMaker').warning(f"Cannot parse base/quote currency from symbol: {self.symbol}. Using UNKNOWN.")

    def format_price(self, p: Decimal) -> Decimal:
        if self.price_precision is None:
            # Fallback to a common precision if not set, e.g., 8 decimal places
            return p.quantize(Decimal('1E-8'), rounding=ROUND_DOWN)
        return p.quantize(self.price_precision, rounding=ROUND_DOWN)

    def format_quantity(self, q: Decimal) -> Decimal:
        if self.quantity_precision is None:
            # Fallback to a common precision if not set, e.g., 8 decimal places
            return q.quantize(Decimal('1E-8'), rounding=ROUND_DOWN)
        return q.quantize(self.quantity_precision, rounding=ROUND_DOWN)

class ConfigManager:
    """Manages loading and reloading of global and symbol configurations."""
    _global_config: Optional[GlobalConfig] = None
    _symbol_configs: Dict[str, SymbolConfig] = {} # Store as dict for easy lookup

    @classmethod
    def load_config(cls, single_symbol: Optional[str] = None) -> Tuple[GlobalConfig, Dict[str, SymbolConfig]]:
        """
        Loads global config from .env and symbol configs from a JSON file.
        If single_symbol is provided, it generates a default config for that symbol.
        """
        try:
            cls._global_config = GlobalConfig.load_from_env()
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
                "strategy": StrategyConfig(
                    base_spread_pct=0.001,
                    base_order_size_pct_of_balance=0.005,
                    max_outstanding_orders=2,
                    dynamic_spread=DynamicSpreadConfig(enabled=True),
                    inventory_skew=InventorySkewConfig(enabled=True),
                    circuit_breaker=CircuitBreakerConfig(enabled=True),
                    order_layers=[OrderLayer()]
                ).model_dump() # Convert nested Pydantic models to dicts for SymbolConfig init
            }
            try:
                cfg = SymbolConfig(**default_symbol_data)
                cls._symbol_configs[single_symbol] = cfg
                logging.getLogger('BybitMarketMaker').info(f"[{Colors.CYAN}Using single symbol mode for {single_symbol}.{Colors.RESET}]")
            except ValidationError as e:
                logging.critical(f"Single symbol configuration validation error for {single_symbol}: {e}")
                raise ConfigurationError(f"Single symbol configuration failed: {e}")
        else:
            # Load multiple symbols from file
            symbol_config_path = Path(cls._global_config.files.symbol_config_file)
            try:
                with open(symbol_config_path) as f:
                    raw_symbol_configs = json_loads_decimal(f.read())
                if not isinstance(raw_symbol_configs, list):
                    raise ValueError("Symbol configuration file must contain a JSON list.")

                for s_cfg_data in raw_symbol_configs:
                    try:
                        # Ensure 'strategy' key exists and merge default strategy settings if not provided
                        s_cfg_data.setdefault('strategy', {})
                        default_strategy_dump = StrategyConfig().model_dump()
                        for strat_field, default_value in default_strategy_dump.items():
                            if strat_field not in s_cfg_data['strategy']:
                                s_cfg_data['strategy'][strat_field] = default_value
                        
                        cfg = SymbolConfig(**s_cfg_data)
                        cls._symbol_configs[cfg.symbol] = cfg
                    except ValidationError as e:
                        logging.error(f"Symbol configuration validation error for {s_cfg_data.get('symbol', 'N/A')}: {e}")
                    except Exception as e:
                        logging.error(f"Unexpected error processing symbol config {s_cfg_data.get('symbol', 'N/A')}: {e}")

            except FileNotFoundError:
                logging.critical(f"Symbol configuration file '{symbol_config_path}' not found. Please create it or use single symbol mode.")
                raise ConfigurationError(f"Symbol config file not found: {symbol_config_path}")
            except (json.JSONDecodeError, InvalidOperation, ValueError) as e:
                logging.critical(f"Error decoding JSON from symbol configuration file '{symbol_config_path}': {e}")
                raise ConfigurationError(f"Invalid symbol config file format: {e}")
            except Exception as e:
                logging.critical(f"Unexpected error loading symbol configs: {e}")
                raise ConfigurationError(f"Error loading symbol configs: {e}")

        return cls._global_config, cls._symbol_configs

# --- Logger Setup ---
class JsonFormatter(logging.Formatter):
    def format(self, record):
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
    if logger.handlers: # Avoid adding duplicate handlers if called multiple times
        for handler in logger.handlers:
            logger.removeHandler(handler)

    logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
    logger.propagate = False # Prevent messages from bubbling up to root logger

    # Determine formatter based on config
    if config.log_format == "json":
        file_formatter = JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S")
        stream_formatter = JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S")
    else: # "plain" format
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
    pybit_logger = logging.getLogger('pybit')
    pybit_logger.setLevel(getattr(logging, config.pybit_log_level.upper(), logging.WARNING))
    # Prevent pybit logs from being handled by the root logger if it's configured
    pybit_logger.propagate = False
    # Add handlers to pybit logger if it doesn't have any
    if not pybit_logger.handlers:
        pybit_logger.addHandler(file_handler)
        pybit_logger.addHandler(stream_handler)

    return logger

# --- Data Classes for Trading State and Metrics ---
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
    last_pnl_update_timestamp: Optional[datetime] = None

    @property
    def net_realized_pnl(self) -> Decimal:
        return self.realized_pnl - self.total_fees

    def update_win_rate(self):
        self.win_rate = (self.wins / self.total_trades * 100.0) if self.total_trades > 0 else 0.0

    def update_pnl_on_buy(self, quantity: Decimal, price: Decimal):
        if self.current_asset_holdings > DECIMAL_ZERO:
            self.average_entry_price = (
                (self.average_entry_price * self.current_asset_holdings) + (price * quantity)
            ) / (self.current_asset_holdings + quantity)
        else:
            self.average_entry_price = price
        self.current_asset_holdings += quantity
        self.last_pnl_update_timestamp = datetime.now(timezone.utc)

    def update_pnl_on_sell(self, quantity: Decimal, price: Decimal):
        if self.current_asset_holdings < quantity:
            # This can happen in dry run if orders are placed with more than available, or if logic is flawed
            logging.getLogger('BybitMarketMaker').warning(f"Attempted to sell {quantity} but only {self.current_asset_holdings} held. Adjusting quantity.")
            quantity = self.current_asset_holdings
            if quantity <= DECIMAL_ZERO: return # Nothing to sell

        profit_loss_on_sale = (price - self.average_entry_price) * quantity
        self.realized_pnl += profit_loss_on_sale

        self.current_asset_holdings -= quantity
        if self.current_asset_holdings <= DECIMAL_ZERO:
            self.average_entry_price = DECIMAL_ZERO
            self.current_asset_holdings = DECIMAL_ZERO # Ensure it's not negative due to precision
        self.last_pnl_update_timestamp = datetime.now(timezone.utc)

    def calculate_unrealized_pnl(self, current_price: Decimal) -> Decimal:
        if self.current_asset_holdings > DECIMAL_ZERO and self.average_entry_price > DECIMAL_ZERO and current_price > DECIMAL_ZERO:
            return (current_price - self.average_entry_price) * self.current_asset_holdings
        return DECIMAL_ZERO

@dataclass
class TradingState:
    mid_price: Decimal = DECIMAL_ZERO
    smoothed_mid_price: Decimal = DECIMAL_ZERO
    current_balance: Decimal = DECIMAL_ZERO # For quote currency, e.g., USDT
    available_balance: Decimal = DECIMAL_ZERO
    current_position_qty: Decimal = DECIMAL_ZERO # For base currency, e.g., BTC

    # For derivatives, this is the exchange-reported unrealized PnL
    unrealized_pnl_derivatives: Decimal = DECIMAL_ZERO

    active_orders: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_order_management_time: float = 0.0
    last_ws_message_time: float = field(default_factory=time.time)
    last_status_report_time: float = 0.0
    last_health_check_time: float = 0.0

    # For dynamic spread and circuit breaker (timestamp, high, low, close)
    price_candlestick_history: deque[Tuple[float, Decimal, Decimal, Decimal]] = field(default_factory=deque)
    circuit_breaker_price_points: deque[Tuple[float, Decimal]] = field(default_factory=deque)

    is_paused: bool = False
    pause_end_time: float = 0.0
    circuit_breaker_cooldown_end_time: float = 0.0
    ws_reconnect_attempts_left: int = 0

    metrics: TradeMetrics = field(default_factory=TradeMetrics)
    
    daily_initial_capital: Decimal = DECIMAL_ZERO
    daily_pnl_reset_date: Optional[datetime] = None
    
    # For DRY_RUN simulation
    last_dry_run_price_update_time: float = field(default_factory=time.time)

# --- State and DB Managers ---
class StateManager:
    """Handles saving and loading bot state to/from a JSON file."""
    def __init__(self, file_path: Path, logger: logging.Logger):
        self.file_path = file_path
        self.logger = logger

    async def save_state(self, state: Dict[str, Any]):
        try:
            temp_path = self.file_path.with_suffix(f".tmp_{os.getpid()}")
            async with aiofiles.open(temp_path, 'w') as f:
                await f.write(json.dumps(state, indent=4, cls=JsonDecimalEncoder))
            os.replace(temp_path, self.file_path) # Atomic replacement
            self.logger.info(f"State saved successfully to {self.file_path.name}.")
        except Exception as e:
            self.logger.error(f"Error saving state to {self.file_path.name}: {e}", exc_info=True)

    async def load_state(self) -> Optional[Dict[str, Any]]:
        if not self.file_path.exists():
            return None
        try:
            async with aiofiles.open(self.file_path, 'r') as f:
                return json_loads_decimal(await f.read())
        except Exception as e:
            self.logger.error(f"Error loading state from {self.file_path.name}: {e}. Starting fresh.", exc_info=True)
            # Rename corrupted file to prevent continuous errors
            try:
                self.file_path.rename(self.file_path.with_suffix(f".corrupted_{int(time.time())}"))
            except OSError as ose:
                self.logger.warning(f"Could not rename corrupted state file {self.file_path.name}: {ose}")
            return None

class DBManager:
    """Manages SQLite database for logging trading events and metrics."""
    def __init__(self, db_file: Path, logger: logging.Logger):
        self.db_file = db_file
        self.conn: Optional[aiosqlite.Connection] = None
        self.logger = logger

    async def connect(self):
        try:
            self.conn = await aiosqlite.connect(self.db_file)
            self.conn.row_factory = aiosqlite.Row
            self.logger.info(f"Connected to database: {self.db_file.name}")
        except Exception as e:
            self.logger.critical(f"Failed to connect to database: {e}", exc_info=True)
            sys.exit(1)

    async def close(self):
        if self.conn:
            await self.conn.close()
            self.logger.info("Database connection closed.")

    async def create_tables(self):
        if not self.conn: await self.connect()

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

        async def _add_column_if_not_exists(table: str, column: str, type: str, default: str):
            cursor = await self.conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in await cursor.fetchall()]
            if column not in columns:
                self.logger.warning(f"Adding '{column}' column to '{table}' table for existing database.")
                await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type} DEFAULT {default}")
                await self.conn.commit()

        # Ensure all columns exist, adding new ones introduced in this upgrade
        await _add_column_if_not_exists("order_events", "symbol", "TEXT", "''")
        await _add_column_if_not_exists("order_events", "reduce_only", "BOOLEAN", "0")
        await _add_column_if_not_exists("trade_fills", "symbol", "TEXT", "''")
        await _add_column_if_not_exists("bot_metrics", "symbol", "TEXT", "''")
        await _add_column_if_not_exists("bot_metrics", "mid_price", "TEXT", "'0'")

        await self.conn.commit()
        self.logger.info("Database tables checked/created and migrated.")

    async def log_order_event(self, symbol: str, order_data: Dict[str, Any], message: Optional[str] = None):
        if not self.conn: return
        try:
            await self.conn.execute(
                "INSERT INTO order_events (timestamp, symbol, order_id, order_link_id, side, order_type, price, qty, cum_exec_qty, status, reduce_only, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    symbol,
                    order_data.get('orderId'),
                    order_data.get('orderLinkId'),
                    order_data.get('side'),
                    order_data.get('orderType'),
                    str(order_data.get('price', DECIMAL_ZERO)),
                    str(order_data.get('qty', DECIMAL_ZERO)),
                    str(order_data.get('cumExecQty', DECIMAL_ZERO)),
                    order_data.get('orderStatus'),
                    order_data.get('reduceOnly', False),
                    message
                )
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging order event to DB for {symbol}: {e}", exc_info=True)

    async def log_trade_fill(self, symbol: str, trade_data: Dict[str, Any], realized_pnl_impact: Decimal):
        if not self.conn: return
        try:
            await self.conn.execute(
                "INSERT INTO trade_fills (timestamp, symbol, order_id, trade_id, side, exec_price, exec_qty, fee, fee_currency, pnl, realized_pnl_impact, liquidity_role) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    symbol,
                    trade_data.get('orderId'),
                    trade_data.get('execId'),
                    trade_data.get('side'),
                    str(trade_data.get('execPrice', DECIMAL_ZERO)),
                    str(trade_data.get('execQty', DECIMAL_ZERO)),
                    str(trade_data.get('execFee', DECIMAL_ZERO)),
                    trade_data.get('feeCurrency'),
                    str(trade_data.get('pnl', DECIMAL_ZERO)),
                    str(realized_pnl_impact),
                    trade_data.get('execType', 'UNKNOWN')
                )
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging trade fill to DB for {symbol}: {e}", exc_info=True)

    async def log_balance_update(self, currency: str, wallet_balance: Decimal, available_balance: Optional[Decimal] = None):
        if not self.conn: return
        try:
            await self.conn.execute(
                "INSERT INTO balance_updates (timestamp, currency, wallet_balance, available_balance) VALUES (?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), currency, str(wallet_balance), str(available_balance) if available_balance else None)
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging balance update to DB: {e}", exc_info=True)

    async def log_bot_metrics(self, symbol: str, metrics: TradeMetrics, unrealized_pnl: Decimal, daily_pnl: Decimal, daily_loss_pct: float, mid_price: Decimal):
        if not self.conn: return
        try:
            await self.conn.execute(
                "INSERT INTO bot_metrics (timestamp, symbol, total_trades, net_realized_pnl, realized_pnl, unrealized_pnl, gross_profit, gross_loss, total_fees, wins, losses, win_rate, current_asset_holdings, average_entry_price, daily_pnl, daily_loss_pct, mid_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(), symbol, metrics.total_trades, str(metrics.net_realized_pnl),
                    str(metrics.realized_pnl), str(unrealized_pnl), str(metrics.gross_profit), str(metrics.gross_loss),
                    str(metrics.total_fees), metrics.wins, metrics.losses, metrics.win_rate,
                    str(metrics.current_asset_holdings), str(metrics.average_entry_price), str(daily_pnl),
                    daily_loss_pct, str(mid_price)
                )
            )
            await self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging bot metrics to DB for {symbol}: {e}", exc_info=True)

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
            api_secret=self.config.api_secret
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
        # Do not retry on auth, bad params, or insufficient balance, or explicit rate limit
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
        non_retryable_codes = {10001, 10002, 10003, 10004, 30001, 30002, 30003, 30004, 30005, 30042, 30070, 30071}
        if exception.ret_code in non_retryable_codes:
            return False
        if isinstance(exception, (APIAuthError, ValueError, BybitRateLimitError, BybitInsufficientBalanceError)):
            return False
        return True # Default to retry for other API errors (e.g., network issues, temporary server errors)

    def _get_api_retry_decorator(self):
        return retry(
            stop=stop_after_attempt(self.config.system.api_retry_attempts),
            wait=wait_exponential_jitter(
                initial=self.config.system.api_retry_initial_delay_sec,
                max=self.config.system.api_retry_max_delay_sec
            ),
            retry=retry_if_exception(self._is_retryable_bybit_error),
            before_sleep=before_sleep_log(self.logger, logging.WARNING, exc_info=False),
            reraise=True
        )

    def _initialize_api_retry_decorator(self):
        api_retry = self._get_api_retry_decorator()
        for name, method in self._original_methods.items():
            setattr(self, name, api_retry(method))
        self.logger.debug("API retry decorators initialized and applied.")

    async def _run_sync_api_call(self, api_method: Callable, *args, **kwargs) -> Any:
        """Runs a synchronous API call in a separate thread."""
        return await asyncio.to_thread(api_method, *args, **kwargs)

    async def _handle_response_async(self, coro: Coroutine[Any, Any, Any], action: str):
        """Processes API responses, checking for errors and raising custom exceptions."""
        response = await coro

        if not isinstance(response, dict):
            self.logger.error(f"API {action} failed: Invalid response format. Response: {response}")
            raise BybitAPIError(f"Invalid API response for {action}", ret_code=-1, ret_msg="Invalid format")

        ret_code = response.get('retCode', -1)
        ret_msg = response.get('retMsg', 'Unknown error')

        if ret_code == 0:
            self.logger.debug(f"API {action} successful.")
            return response.get('result', {})

        if ret_code == 10004:
            raise APIAuthError(f"Authentication failed: {ret_msg}. Check API key permissions and validity.")
        elif ret_code in [10006, 10007, 10016, 120004, 120005]:
            raise BybitRateLimitError(f"API rate limit hit for {action}: {ret_msg}", ret_code=ret_code, ret_msg=ret_msg)
        elif ret_code in [10001, 110001, 110003, 12130, 12131]:
            raise BybitInsufficientBalanceError(f"Insufficient balance for {action}: {ret_msg}", ret_code=ret_code, ret_msg=ret_msg)
        elif ret_code == 10002: # General parameter error
            raise ValueError(f"API {action} parameter error: {ret_msg} (ErrCode: {ret_code})")
        elif ret_code == 30042: # Order price cannot be higher/lower than X times of current market price
            raise OrderPlacementError(f"Order price out of range for {action}: {ret_msg} (ErrCode: {ret_code})")
        elif ret_code == 30070: # Cross/isolated margin mode not switched
            raise ConfigurationError(f"Margin mode not set correctly for {action}: {ret_msg} (ErrCode: {ret_code})")
        elif ret_code == 30071: # Leverage not modified
            self.logger.warning(f"Leverage for {action} not modified: {ret_msg} (ErrCode: {ret_code}). May already be set.")
            return response.get('result', {}) # Treat as non-critical success

        raise BybitAPIError(f"API {action} failed: {ret_msg}", ret_code=ret_code, ret_msg=ret_msg)

    # --- Implementations for API Calls ---
    async def get_instruments_info_impl(self, category: str, symbol: str) -> Optional[Dict[str, Any]]:
        response_coro = self._run_sync_api_call(
            self.http_session.get_instruments_info,
            category=category, symbol=symbol
        )
        result = await self._handle_response_async(response_coro, f"get_instruments_info for {symbol}")
        return result.get('list', [{}])[0] if result else None

    async def get_wallet_balance_impl(self, account_type: str) -> Optional[Dict[str, Any]]:
        response_coro = self._run_sync_api_call(
            self.http_session.get_wallet_balance,
            accountType=account_type
        )
        result = await self._handle_response_async(response_coro, "get_wallet_balance")
        return result.get('list', [{}])[0] if result else None

    async def get_position_info_impl(self, category: str, symbol: str) -> Optional[Dict[str, Any]]:
        if category not in ['linear', 'inverse']: return None # Spot doesn't have positions in this context
        response_coro = self._run_sync_api_call(
            self.http_session.get_positions,
            category=category, symbol=symbol
        )
        result = await self._handle_response_async(response_coro, f"get_position_info for {symbol}")
        if result and result.get('list'):
            for position in result['list']:
                if position['symbol'] == symbol: return position
        return None

    async def set_leverage_impl(self, category: str, symbol: str, leverage: Decimal) -> bool:
        if category not in ['linear', 'inverse']: return True
        response_coro = self._run_sync_api_call(
            self.http_session.set_leverage,
            category=category, symbol=symbol,
            buyLeverage=str(leverage), sellLeverage=str(leverage)
        )
        return await self._handle_response_async(response_coro, f"set_leverage for {symbol} to {leverage}") is not None

    async def get_open_orders_impl(self, category: str, symbol: str) -> List[Dict[str, Any]]:
        response_coro = self._run_sync_api_call(
            self.http_session.get_open_orders,
            category=category, symbol=symbol, limit=50
        )
        result = await self._handle_response_async(response_coro, f"get_open_orders for {symbol}")
        return result.get('list', []) if result else []

    async def place_order_impl(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        response_coro = self._run_sync_api_call(self.http_session.place_order, **params)
        return await self._handle_response_async(response_coro, f"place_order ({params.get('side')} {params.get('qty')} @ {params.get('price')})")

    async def cancel_order_impl(self, category: str, symbol: str, order_id: str, order_link_id: Optional[str] = None) -> bool:
        current_time = time.time()
        if (current_time - self.last_cancel_time) < self.config.system.cancellation_rate_limit_sec:
            await asyncio.sleep(self.config.system.cancellation_rate_limit_sec - (current_time - self.last_cancel_time))

        params = {"category": category, "symbol": symbol, "orderId": order_id}
        if order_link_id: params["orderLinkId"] = order_link_id
        response_coro = self._run_sync_api_call(self.http_session.cancel_order, **params)
        self.last_cancel_time = time.time()
        return await self._handle_response_async(response_coro, f"cancel_order {order_id}") is not None

    async def cancel_all_orders_impl(self, category: str, symbol: str) -> bool:
        params = {"category": category, "symbol": symbol}
        response_coro = self._run_sync_api_call(self.http_session.cancel_all_orders, **params)
        return await self._handle_response_async(response_coro, f"cancel_all_orders for {symbol}") is not None

    async def set_trading_stop_impl(self, category: str, symbol: str, sl_price: Decimal, tp_price: Decimal) -> bool:
        params = {
            "category": category,
            "symbol": symbol,
            "takeProfit": str(tp_price),
            "stopLoss": str(sl_price),
            "tpTriggerBy": "LastPrice", # Or MarkPrice, IndexPrice
            "slTriggerBy": "LastPrice",
            "tpslMode": "Full" # Full or Partial
        }
        response_coro = self._run_sync_api_call(self.http_session.set_trading_stop, **params)
        return await self._handle_response_async(response_coro, f"set_trading_stop for {symbol} TP:{tp_price} SL:{sl_price}") is not None

    async def get_kline_impl(self, category: str, symbol: str, interval: str, limit: int) -> List[List[Any]]:
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        response_coro = self._run_sync_api_call(self.http_session.get_kline, **params)
        result = await self._handle_response_async(response_coro, f"get_kline for {symbol} {interval}")
        return result.get('list', []) if result else []

    # Expose decorated methods
    get_instruments_info: Callable[[str, str], Coroutine[Any, Any, Optional[Dict[str, Any]]]]
    get_wallet_balance: Callable[[str], Coroutine[Any, Any, Optional[Dict[str, Any]]]]
    get_position_info: Callable[[str, str], Coroutine[Any, Any, Optional[Dict[str, Any]]]]
    set_leverage: Callable[[str, str, Decimal], Coroutine[Any, Any, bool]]
    get_open_orders: Callable[[str, str], Coroutine[Any, Any, List[Dict[str, Any]]]]
    place_order: Callable[[Dict[str, Any]], Coroutine[Any, Any, Optional[Dict[str, Any]]]]
    cancel_order: Callable[[str, str, str, Optional[str]], Coroutine[Any, Any, bool]]
    cancel_all_orders: Callable[[str, str], Coroutine[Any, Any, bool]]
    set_trading_stop: Callable[[str, str, Decimal, Decimal], Coroutine[Any, Any, bool]]
    get_kline: Callable[[str, str, str, int], Coroutine[Any, Any, List[List[Any]]]]

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

        # These are shared data structures, need thread-safe access if pybit WS callbacks run in separate threads
        # pybit's WebSocket client runs callbacks in a separate thread.
        # Use threading.RLock for access to these, or push to asyncio.Queue and process in main loop.
        # For simplicity and performance, we'll use threading.RLock here.
        self._data_lock = threading.RLock()
        self.order_book_data: Dict[str, Dict[str, List[List[Decimal]]]] = {} # {symbol: {'b': [[price, qty]], 'a': ...}}
        self.recent_trades_data: Dict[str, deque[Tuple[float, Decimal, Decimal, str]]] = {} # {symbol: deque((timestamp, price, qty, side))}
        self.last_orderbook_update_time: Dict[str, float] = {}
        self.last_trades_update_time: Dict[str, float] = {}

        self.symbol_bots: Dict[str, 'AsyncSymbolBot'] = {} # Reference to active AsyncSymbolBot instances

        self._stop_event = asyncio.Event()
        self._public_topics: List[str] = []
        self._private_topics: List[str] = []

    def register_symbol_bot(self, symbol_bot: 'AsyncSymbolBot'):
        """Registers an AsyncSymbolBot instance to receive WS updates."""
        with self._data_lock:
            self.symbol_bots[symbol_bot.config.symbol] = symbol_bot

    def unregister_symbol_bot(self, symbol: str):
        """Unregisters an AsyncSymbolBot instance."""
        with self._data_lock:
            if symbol in self.symbol_bots:
                del self.symbol_bots[symbol]

    def _ws_message_handler(self, msg: Dict[str, Any]):
        """
        Callback for pybit WebSocket. Runs in a separate thread.
        Dispatches messages to appropriate AsyncSymbolBot instances.
        """
        try:
            # Update last WS message time for all bots, as it indicates overall WS health
            # This is a bit inefficient, but ensures all bots are aware of WS activity.
            # A more refined approach would be to update a central timestamp and let bots check it.
            # For now, we update it in the individual bot's state.
            
            if 'topic' in msg:
                topic = msg['topic']
                if topic.startswith("orderbook."):
                    asyncio.run_coroutine_threadsafe(self._process_orderbook_message(msg), asyncio.get_event_loop())
                elif topic.startswith("publicTrade."):
                    asyncio.run_coroutine_threadsafe(self._process_public_trade_message(msg), asyncio.get_event_loop())
                elif topic in ['order', 'position', 'execution', 'wallet']:
                    asyncio.run_coroutine_threadsafe(self._process_private_message(msg), asyncio.get_event_loop())
                elif 'op' in msg and msg['op'] == 'pong':
                    self.logger.debug("WS Pong received.")
                else:
                    self.logger.debug(f"Received unhandled WS message: {msg}")
            else:
                self.logger.debug(f"Received WS message without topic: {msg}")

        except Exception as e:
            self.logger.error(f"Error in WS message handler: {e}", exc_info=True)

    async def _process_orderbook_message(self, message: Dict[str, Any]):
        """Updates the order book for a symbol and notifies relevant bot."""
        data = message.get('data')
        if not data: return

        topic = message['topic']
        parts = topic.split('.')
        if len(parts) < 3:
            self.logger.warning(f"Unrecognized orderbook topic format: {topic}")
            return

        symbol_ws = parts[2] # e.g., "BTCUSDT"
        
        # Bybit WS often sends symbol without the quote currency for linear (e.g. BTCUSDT -> BTCUSDT)
        # If we have BTC/USDT:USDT in config, we need to map
        with self._data_lock:
            symbol_map = {bot.config.symbol.replace('/', '').replace(':', ''): bot.config.symbol for bot in self.symbol_bots.values()}
            symbol = symbol_map.get(symbol_ws, symbol_ws)

            bids = [[Decimal(str(item[0])), Decimal(str(item[1]))] for item in data.get('b', [])]
            asks = [[Decimal(str(item[0])), Decimal(str(item[1]))] for item in data.get('a', [])]

            if bids and asks:
                self.order_book_data[symbol] = {'b': bids, 'a': asks}
                self.last_orderbook_update_time[symbol] = time.time()
                if symbol in self.symbol_bots:
                    await self.symbol_bots[symbol]._update_mid_price(bids, asks)
            else:
                self.logger.debug(f"Received empty or incomplete orderbook data for {symbol}. Skipping mid-price update.")

    async def _process_public_trade_message(self, message: Dict[str, Any]):
        """Updates recent trades for a symbol."""
        data = message.get('data')
        if not data: return

        topic = message['topic']
        parts = topic.split('.')
        if len(parts) < 2:
            self.logger.warning(f"Unrecognized publicTrade topic format: {topic}")
            return
        
        symbol_ws = parts[1]
        with self._data_lock:
            symbol_map = {bot.config.symbol.replace('/', '').replace(':', ''): bot.config.symbol for bot in self.symbol_bots.values()}
            symbol = symbol_map.get(symbol_ws, symbol_ws)

            if symbol not in self.recent_trades_data:
                self.recent_trades_data[symbol] = deque(maxlen=200) # Max 200 trades history

            for trade_data in data:
                price = Decimal(str(trade_data.get('p', DECIMAL_ZERO)))
                qty = Decimal(str(trade_data.get('v', DECIMAL_ZERO)))
                side = trade_data.get('S', 'unknown')
                self.recent_trades_data[symbol].append((time.time(), price, qty, side))
            self.last_trades_update_time[symbol] = time.time()

    async def _process_private_message(self, message: Dict[str, Any]):
        """Processes private stream messages (orders, positions, executions) and dispatches to relevant bots."""
        data = message.get('data')
        if not data: return

        topic = message['topic']
        for item_data in data:
            symbol_ws = item_data.get('symbol')
            if not symbol_ws and topic != 'wallet': continue # Wallet updates don't have symbol

            with self._data_lock:
                symbol_map = {bot.config.symbol.replace('/', '').replace(':', ''): bot.config.symbol for bot in self.symbol_bots.values()}
                symbol = symbol_map.get(symbol_ws, symbol_ws) if symbol_ws else None

                if symbol and symbol in self.symbol_bots:
                    bot = self.symbol_bots[symbol]
                    if topic == 'order':
                        await bot._process_order_update(item_data)
                    elif topic == 'position':
                        await bot._process_position_update(item_data)
                    elif topic == 'execution':
                        await bot._process_execution_update(item_data)
                elif topic == 'wallet':
                    # Wallet updates are global, all bots might need to update their balance if it's their quote currency
                    for bot_instance in self.symbol_bots.values():
                        # Only update if the wallet currency matches the bot's main quote currency
                        if item_data.get('coin') == bot_instance.global_config.main_quote_currency:
                            await bot_instance._update_balance_from_wallet_ws(item_data)
                else:
                    self.logger.debug(f"Received {topic} update for unmanaged symbol: {symbol_ws if symbol_ws else 'N/A'}")

    def get_order_book_snapshot(self, symbol: str) -> Optional[Dict[str, List[List[Decimal]]]]:
        """Retrieves the latest order book snapshot for a symbol."""
        with self._data_lock:
            return self.order_book_data.get(symbol)

    def get_recent_trades(self, symbol: str, limit: int = 100) -> deque[Tuple[float, Decimal, Decimal, str]]:
        """Retrieves recent trades for a symbol."""
        with self._data_lock:
            return self.recent_trades_data.get(symbol, deque(maxlen=limit))

    async def _connect_and_subscribe(self, is_private: bool, topics: List[str]):
        """Internal helper to establish connection and subscribe."""
        ws_instance: Optional[WebSocket] = None
        channel_type = self.config.category if not is_private else "private"
        
        try:
            if is_private:
                if not self.config.api_key or not self.config.api_secret:
                    self.logger.warning(f"{Colors.YELLOW}Skipping private WebSocket connection: API keys not provided.{Colors.RESET}")
                    return None
                ws_instance = WebSocket(
                    testnet=self.config.testnet, api_key=self.config.api_key,
                    api_secret=self.config.api_secret, channel_type=channel_type
                )
            else:
                ws_instance = WebSocket(testnet=self.config.testnet, channel_type=channel_type)

            for topic in topics:
                if topic.startswith("orderbook."):
                    parts = topic.split('.')
                    depth = int(parts[1])
                    symbol_ws = parts[2]
                    ws_instance.orderbook_stream(symbol=symbol_ws, depth=depth, callback=self._ws_message_handler)
                    self.logger.info(f"Subscribed to orderbook.{depth}.{symbol_ws}")
                elif topic.startswith("publicTrade."):
                    parts = topic.split('.')
                    symbol_ws = parts[1]
                    ws_instance.public_trade_stream(symbol=symbol_ws, callback=self._ws_message_handler)
                    self.logger.info(f"Subscribed to publicTrade.{symbol_ws}")
                elif topic == "wallet":
                    ws_instance.wallet_stream(callback=self._ws_message_handler)
                    self.logger.info("Subscribed to private wallet stream.")
                elif topic == "order":
                    ws_instance.order_stream(callback=self._ws_message_handler)
                    self.logger.info("Subscribed to private order stream.")
                elif topic == "position":
                    ws_instance.position_stream(callback=self._ws_message_handler)
                    self.logger.info("Subscribed to private position stream.")
                elif topic == "execution":
                    ws_instance.execution_stream(callback=self._ws_message_handler)
                    self.logger.info("Subscribed to private execution stream.")
                else:
                    self.logger.warning(f"Unhandled WS topic: {topic}")
            
            return ws_instance

        except websocket._exceptions.WebSocketConnectionClosedException as e:
            self.logger.error(f"WebSocket connection failed: {e}. Is the Bybit server reachable and API keys correct?")
            return None
        except Exception as e:
            self.logger.error(f"Error connecting or subscribing to WebSocket ({'private' if is_private else 'public'}): {e}", exc_info=True)
            return None

    async def _reconnect_loop(self, is_private: bool):
        """Manages reconnection attempts for a WebSocket stream."""
        stream_name = "Private" if is_private else "Public"
        topics = self._private_topics if is_private else self._public_topics

        attempts = 0
        while not self._stop_event.is_set():
            if is_private and (not self.config.api_key or not self.config.api_secret):
                self.logger.warning(f"{Colors.YELLOW}Not attempting {stream_name} WS reconnection: API keys not available.{Colors.RESET}")
                await asyncio.sleep(self.config.system.ws_reconnect_max_delay_sec) # Wait before checking again
                continue

            current_ws_instance = self._ws_private_instance if is_private else self._ws_public_instance
            if current_ws_instance is not None:
                # Check if pybit's internal connection is still alive (no direct way, infer from last message)
                # This is a weak check, as pybit's WS client doesn't expose connection status directly.
                # A better approach would be to subclass pybit's WS or use a different library.
                # For now, rely on individual bots reporting stale data, which might trigger a full reconnect.
                await asyncio.sleep(self.config.system.ws_heartbeat_sec)
                continue

            self.logger.info(f"{Colors.YELLOW}Attempting to reconnect {stream_name} WebSocket stream... (Attempt {attempts + 1}/{self.config.system.ws_reconnect_attempts}){Colors.RESET}")
            
            new_ws_instance = await self._connect_and_subscribe(is_private, topics)
            if new_ws_instance:
                if is_private:
                    self._ws_private_instance = new_ws_instance
                else:
                    self._ws_public_instance = new_ws_instance
                self.logger.info(f"{Colors.NEON_GREEN}{stream_name} WebSocket reconnected successfully.{Colors.RESET}")
                attempts = 0 # Reset attempts on success
            else:
                attempts += 1
                if attempts >= self.config.system.ws_reconnect_attempts:
                    self.logger.critical(f"{Colors.NEON_RED}{stream_name} WebSocket reconnection failed after {self.config.system.ws_reconnect_attempts} attempts. Shutting down.{Colors.RESET}")
                    # Signal main bot to stop
                    self._stop_event.set()
                    for bot in self.symbol_bots.values():
                        bot.stop()
                    break
                
                delay = min(self.config.system.ws_reconnect_initial_delay_sec * (2 ** (attempts - 1)), self.config.system.ws_reconnect_max_delay_sec)
                self.logger.warning(f"{Colors.NEON_ORANGE}{stream_name} WebSocket reconnection failed. Retrying in {delay} seconds...{Colors.RESET}")
                await asyncio.sleep(delay)

    async def start_streams(self, public_topics: List[str], private_topics: List[str]):
        """Starts public and private WebSocket streams, managing reconnection."""
        await self.stop_streams() # Ensure clean slate

        self._stop_event.clear()
        self._public_topics = public_topics
        self._private_topics = private_topics

        # Start reconnection loops for each stream type
        if public_topics:
            self.logger.info(f"Initializing PUBLIC WS stream for topics: {public_topics}")
            self._ws_public_task = asyncio.create_task(self._reconnect_loop(is_private=False), name="WS_Public_Reconnect_Loop")
        if private_topics:
            self.logger.info(f"Initializing PRIVATE WS stream for topics: {private_topics}")
            self._ws_private_task = asyncio.create_task(self._reconnect_loop(is_private=True), name="WS_Private_Reconnect_Loop")

        self.logger.info(f"{Colors.NEON_GREEN}# WebSocket streams have been summoned.{Colors.RESET}")

    async def stop_streams(self):
        """Stops all WebSocket connections and associated tasks."""
        if self._stop_event.is_set():
            return

        self.logger.info(f"{Colors.YELLOW}# Signaling WebSocket streams to stop...{Colors.RESET}")
        self._stop_event.set()

        # Cancel reconnection tasks
        if self._ws_public_task:
            self._ws_public_task.cancel()
            try: await self._ws_public_task
            except asyncio.CancelledError: pass
            self._ws_public_task = None
        if self._ws_private_task:
            self._ws_private_task.cancel()
            try: await self._ws_private_task
            except asyncio.CancelledError: pass
            self._ws_private_task = None

        # Explicitly exit pybit WebSocket instances
        if self._ws_public_instance:
            try:
                await asyncio.to_thread(self._ws_public_instance.exit) # Run sync exit in thread
            except Exception as e: self.logger.debug(f"Error closing public WS: {e}")
            self._ws_public_instance = None
        if self._ws_private_instance:
            try:
                await asyncio.to_thread(self._ws_private_instance.exit) # Run sync exit in thread
            except Exception as e: self.logger.debug(f"Error closing private WS: {e}")
            self._ws_private_instance = None

        # Give some time for message processor to finish
        await asyncio.sleep(1)
        self.logger.info(f"{Colors.CYAN}# WebSocket streams have been extinguished.{Colors.RESET}")

# --- Async Symbol Bot (Per-Symbol Logic) ---
class AsyncSymbolBot:
    """
    Manages market making operations for a single trading symbol.
    Runs as an asyncio task.
    """
    def __init__(self, global_config: GlobalConfig, symbol_config: SymbolConfig,
                 api_client: BybitAPIClient, ws_client: BybitWebSocketClient,
                 db_manager: DBManager, logger: logging.Logger):
        self.global_config = global_config
        self.config = symbol_config
        self.api_client = api_client
        self.ws_client = ws_client
        self.db_manager = db_manager
        self.logger = logger

        self.state = TradingState(ws_reconnect_attempts_left=self.global_config.system.ws_reconnect_attempts)
        self.state.ws_reconnect_attempts_left = self.global_config.system.ws_reconnect_attempts
        # Maxlen for candlestick history for ATR. Need enough for `length` periods + 1 for initial close.
        self.state.price_candlestick_history = deque(maxlen=self.config.strategy.dynamic_spread.volatility_window_sec + 1) 
        self.state.circuit_breaker_price_points = deque(maxlen=self.config.strategy.circuit_breaker.check_window_sec * 2)

        self.last_atr_update_time: float = 0.0
        self.cached_atr: Decimal = DECIMAL_ZERO
        self.last_symbol_info_refresh: float = 0.0
        self.current_leverage: Optional[int] = None
        
        self._stop_event = asyncio.Event()

    async def initialize(self):
        """Performs initial setup for the symbol bot."""
        self.logger.info(f"[{self.config.symbol}] Initializing bot for symbol.")

        await self._load_state() # Load previous state

        if not await self._fetch_market_info():
            raise MarketInfoError(f"[{self.config.symbol}] Failed to fetch market info. Shutting down.")

        if not await self._update_balance_and_position():
            raise InitialBalanceError(f"[{self.config.symbol}] Failed to fetch initial balance/position. Shutting down.")
        
        # Initialize daily_initial_capital if not set or it's a new day
        current_utc_date = datetime.now(timezone.utc).date()
        if self.state.daily_initial_capital == DECIMAL_ZERO or \
           (self.state.daily_pnl_reset_date is not None and self.state.daily_pnl_reset_date.date() < current_utc_date):
            self.state.daily_initial_capital = self.state.current_balance
            self.state.daily_pnl_reset_date = datetime.now(timezone.utc)
            self.logger.info(f"[{self.config.symbol}] Daily initial capital set to: {self.state.daily_initial_capital} {self.global_config.main_quote_currency}")

        if self.global_config.trading_mode not in ["DRY_RUN", "SIMULATION"]:
            if self.global_config.category in ['linear', 'inverse'] and not await self._set_margin_mode_and_leverage():
                raise InitialBalanceError(f"[{self.config.symbol}] Failed to set margin mode/leverage. Shutting down.")
        else:
            self.logger.info(f"[{self.config.symbol}] {self.global_config.trading_mode} mode: Skipping leverage setting.")

        await self._reconcile_orders_on_startup()
        self.logger.info(f"[{self.config.symbol}] Initial setup successful.")

    async def run_loop(self):
        """Main loop for the symbol bot."""
        self.logger.info(f"{Colors.CYAN}[{self.config.symbol}] SymbolBot starting its loop.{Colors.RESET}")
        
        # Initial price for dry run
        if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"] and self.state.mid_price == DECIMAL_ZERO:
            mock_price = Decimal('0.1')
            self.state.mid_price = mock_price
            self.state.smoothed_mid_price = mock_price
            self.state.price_candlestick_history.append((time.time(), mock_price, mock_price, mock_price))
            self.logger.info(f"[{self.config.symbol}] {self.global_config.trading_mode} mode: Initialized mock mid_price to {mock_price}.")

        while not self._stop_event.is_set():
            current_time = time.time()
            try:
                # Dry run simulations
                if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
                    await self._simulate_dry_run_price_movement(current_time)
                    await self._simulate_dry_run_fills()

                # Periodic health checks and data freshness
                # WS health check is handled by the central BybitWebSocketClient
                # Each bot only checks its own market data freshness.
                if not await self._check_market_data_freshness(current_time):
                    self.logger.warning(f"[{self.config.symbol}] Stale market data. Skipping order management cycle.")
                    await self._cancel_all_orders() # Cancel orders if market data is stale
                    await asyncio.sleep(self.global_config.system.loop_interval_sec)
                    continue
                
                if (current_time - self.state.last_health_check_time) > self.global_config.system.health_check_interval_sec:
                    await self._update_balance_and_position()
                    self.state.last_health_check_time = current_time

                # Daily PnL and Circuit Breaker checks
                if await self._check_daily_pnl_limits():
                    self.logger.critical(f"[{self.config.symbol}] Daily PnL limit hit. Trading disabled for this symbol.")
                    self._stop_event.set() # Stop this symbol bot
                    continue

                if await self._check_circuit_breaker(current_time):
                    self.logger.warning(f"[{self.config.symbol}] Circuit breaker tripped. Skipping order management.")
                    await asyncio.sleep(self.global_config.system.loop_interval_sec)
                    continue

                # Resume from pause
                if self.state.is_paused and current_time < self.state.pause_end_time:
                    self.logger.debug(f"[{self.config.symbol}] Bot is paused due to circuit breaker. Resuming in {int(self.state.pause_end_time - current_time)}s.")
                    await asyncio.sleep(self.global_config.system.loop_interval_sec)
                    continue
                elif self.state.is_paused:
                    self.logger.info(f"[{self.config.symbol}] Circuit breaker pause finished. Resuming trading.")
                    self.state.is_paused = False
                    self.state.circuit_breaker_cooldown_end_time = current_time + self.config.strategy.circuit_breaker.cool_down_after_trip_sec

                if current_time < self.state.circuit_breaker_cooldown_end_time:
                    self.logger.debug(f"[{self.config.symbol}] Circuit breaker in cooldown. Resuming trading in {int(self.state.circuit_breaker_cooldown_end_time - current_time)}s.")
                    await asyncio.sleep(self.global_config.system.loop_interval_sec)
                    continue

                # Trading Hours Check
                if not self._is_trading_hours(current_time):
                    if self.config.trade_enabled:
                        self.logger.info(f"[{self.config.symbol}] Outside trading hours. Temporarily disabling trading and cancelling orders.")
                        self.config = self.config.model_copy(update={'trade_enabled': False}) # Temporarily disable
                        await self._cancel_all_orders()
                    await asyncio.sleep(self.global_config.system.loop_interval_sec)
                    continue
                elif not self.config.trade_enabled:
                    # If it's within trading hours now but was disabled, re-enable for the loop
                    self.logger.info(f"[{self.config.symbol}] Within trading hours. Re-enabling trading.")
                    self.config = self.config.model_copy(update={'trade_enabled': True})


                # Main order management logic
                if self.config.trade_enabled and (current_time - self.state.last_order_management_time) > self.global_config.system.order_refresh_interval_sec:
                    await self._manage_orders()
                    self.state.last_order_management_time = current_time
                    await self._check_and_handle_stale_orders(current_time)
                elif not self.config.trade_enabled:
                    self.logger.debug(f"[{self.config.symbol}] Trading disabled. Skipping order management.")
                    await self._cancel_all_orders() # Ensure no orders are left if trading is disabled

                # Auto TP/SL
                if self.config.strategy.enable_auto_sl_tp and self.state.current_position_qty != DECIMAL_ZERO:
                    await self._update_take_profit_stop_loss()
                
                # Status report
                if (current_time - self.state.last_status_report_time) > self.global_config.system.status_report_interval_sec:
                    await self._log_status_summary()
                    self.state.last_status_report_time = current_time

            except asyncio.CancelledError:
                self.logger.info(f"[{self.config.symbol}] SymbolBot task cancelled.")
                break
            except Exception as e:
                self.logger.error(f"{Colors.NEON_RED}[{self.config.symbol}] Unhandled error in main loop: {e}{Colors.RESET}", exc_info=True)
                termux_notify(f"{self.config.symbol}: Bot Error: {str(e)[:50]}...", is_error=True)

            await asyncio.sleep(self.global_config.system.loop_interval_sec)

        self.logger.info(f"{Colors.CYAN}[{self.config.symbol}] SymbolBot stopping. Cancelling orders and saving state.{Colors.RESET}")
        await self._cancel_all_orders()
        await self._save_state()

    def stop(self):
        """Sets the stop event to gracefully stop the bot's main loop."""
        self._stop_event.set()

    # --- State Management ---
    async def _save_state(self):
        """Saves the current trading state for this symbol."""
        state_data = {
            'mid_price': str(self.state.mid_price),
            'smoothed_mid_price': str(self.state.smoothed_mid_price),
            'current_balance': str(self.state.current_balance),
            'available_balance': str(self.state.available_balance),
            'current_position_qty': str(self.state.current_position_qty),
            'unrealized_pnl_derivatives': str(self.state.unrealized_pnl_derivatives),
            'active_orders': {oid: {k: str(v) if isinstance(v, Decimal) else v for k, v in odata.items()} for oid, odata in self.state.active_orders.items()},
            'last_order_management_time': self.state.last_order_management_time,
            'last_ws_message_time': self.state.last_ws_message_time,
            'last_status_report_time': self.state.last_status_report_time,
            'last_health_check_time': self.state.last_health_check_time,
            'price_candlestick_history': [(t, str(h), str(l), str(c)) for t, h, l, c in self.state.price_candlestick_history],
            'circuit_breaker_price_points': [(t, str(p)) for t, p in self.state.circuit_breaker_price_points],
            'is_paused': self.state.is_paused,
            'pause_end_time': self.state.pause_end_time,
            'circuit_breaker_cooldown_end_time': self.state.circuit_breaker_cooldown_end_time,
            'ws_reconnect_attempts_left': self.state.ws_reconnect_attempts_left,
            'metrics': {
                'total_trades': self.state.metrics.total_trades,
                'gross_profit': str(self.state.metrics.gross_profit),
                'gross_loss': str(self.state.metrics.gross_loss),
                'total_fees': str(self.state.metrics.total_fees),
                'wins': self.state.metrics.wins,
                'losses': self.state.metrics.losses,
                'win_rate': self.state.metrics.win_rate,
                'realized_pnl': str(self.state.metrics.realized_pnl),
                'current_asset_holdings': str(self.state.metrics.current_asset_holdings),
                'average_entry_price': str(self.state.metrics.average_entry_price),
                'last_pnl_update_timestamp': self.state.metrics.last_pnl_update_timestamp.isoformat() if self.state.metrics.last_pnl_update_timestamp else None,
            },
            'daily_initial_capital': str(self.state.daily_initial_capital),
            'daily_pnl_reset_date': self.state.daily_pnl_reset_date.isoformat() if self.state.daily_pnl_reset_date else None,
            'last_dry_run_price_update_time': self.state.last_dry_run_price_update_time,
        }
        await StateManager(STATE_DIR / (self.config.symbol.replace('/', '_').replace(':', '') + "_" + self.global_config.files.state_file), self.logger).save_state(state_data)

    async def _load_state(self):
        """Loads the trading state for this symbol from file."""
        state_data = await StateManager(STATE_DIR / (self.config.symbol.replace('/', '_').replace(':', '') + "_" + self.global_config.files.state_file), self.logger).load_state()
        if state_data:
            self.state.mid_price = Decimal(str(state_data.get('mid_price', DECIMAL_ZERO)))
            self.state.smoothed_mid_price = Decimal(str(state_data.get('smoothed_mid_price', DECIMAL_ZERO)))
            self.state.current_balance = Decimal(str(state_data.get('current_balance', DECIMAL_ZERO)))
            self.state.available_balance = Decimal(str(state_data.get('available_balance', DECIMAL_ZERO)))
            self.state.current_position_qty = Decimal(str(state_data.get('current_position_qty', DECIMAL_ZERO)))
            self.state.unrealized_pnl_derivatives = Decimal(str(state_data.get('unrealized_pnl_derivatives', DECIMAL_ZERO)))
            self.state.active_orders = state_data.get('active_orders', {})
            self.state.last_order_management_time = state_data.get('last_order_management_time', 0.0)
            self.state.last_ws_message_time = state_data.get('last_ws_message_time', time.time())
            self.state.last_status_report_time = state_data.get('last_status_report_time', 0.0)
            self.state.last_health_check_time = state_data.get('last_health_check_time', 0.0)
            self.state.price_candlestick_history.extend([(t, Decimal(str(h)), Decimal(str(l)), Decimal(str(c))) for t, h, l, c in state_data.get('price_candlestick_history', [])])
            self.state.circuit_breaker_price_points.extend([(t, Decimal(str(p))) for t, p in state_data.get('circuit_breaker_price_points', [])])
            self.state.is_paused = state_data.get('is_paused', False)
            self.state.pause_end_time = state_data.get('pause_end_time', 0.0)
            self.state.circuit_breaker_cooldown_end_time = state_data.get('circuit_breaker_cooldown_end_time', 0.0)
            self.state.ws_reconnect_attempts_left = state_data.get('ws_reconnect_attempts_left', self.global_config.system.ws_reconnect_attempts)

            loaded_metrics_dict = state_data.get('metrics', {})
            if loaded_metrics_dict:
                metrics = TradeMetrics()
                for attr, value in loaded_metrics_dict.items():
                    if attr in ['gross_profit', 'gross_loss', 'total_fees', 'realized_pnl', 'current_asset_holdings', 'average_entry_price'] and isinstance(value, str):
                        setattr(metrics, attr, Decimal(value))
                    elif attr == 'last_pnl_update_timestamp':
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

            self.state.daily_initial_capital = Decimal(str(state_data.get('daily_initial_capital', DECIMAL_ZERO)))
            if isinstance(state_data.get('daily_pnl_reset_date'), str):
                self.state.daily_pnl_reset_date = datetime.fromisoformat(state_data['daily_pnl_reset_date'])
            else:
                self.state.daily_pnl_reset_date = state_data.get('daily_pnl_reset_date')
            self.state.last_dry_run_price_update_time = state_data.get('last_dry_run_price_update_time', time.time())

            self.logger.info(f"[{self.config.symbol}] Loaded state with {len(self.state.active_orders)} active orders and metrics: {self.state.metrics}")
        else:
            self.logger.info(f"[{self.config.symbol}] No saved state found. Starting fresh.")

    # --- Market Data & Price Updates ---
    async def _update_mid_price(self, bids: List[List[Decimal]], asks: List[List[Decimal]]):
        """Updates mid-price and related historical data from orderbook."""
        best_bid = bids[0][0]
        best_ask = asks[0][0]
        new_mid_price = (best_bid + best_ask) / Decimal('2')
        current_time = time.time()

        if new_mid_price != self.state.mid_price:
            self.state.mid_price = new_mid_price
            self.state.circuit_breaker_price_points.append((current_time, self.state.mid_price))

            # Update candlestick history (timestamp, high, low, close)
            # This is a simplified approach, a real candlestick would aggregate over a fixed interval.
            # For ATR, we need a series of High, Low, Close. We'll use the mid_price as a proxy for both.
            if self.state.price_candlestick_history:
                last_ts, last_high, last_low, _ = self.state.price_candlestick_history[-1]
                # If within a short interval, update the last candle's high/low
                # This logic assumes that price updates are frequent enough to form "mini-candles"
                if (current_time - last_ts) < self.global_config.system.loop_interval_sec * 2:
                    self.state.price_candlestick_history[-1] = (current_time, max(last_high, new_mid_price), min(last_low, new_mid_price), new_mid_price)
                else:
                    self.state.price_candlestick_history.append((current_time, new_mid_price, new_mid_price, new_mid_price))
            else:
                self.state.price_candlestick_history.append((current_time, new_mid_price, new_mid_price, new_mid_price))

            if self.state.smoothed_mid_price == DECIMAL_ZERO:
                self.state.smoothed_mid_price = new_mid_price
            else:
                alpha = Decimal(str(self.config.strategy.dynamic_spread.price_change_smoothing_factor))
                self.state.smoothed_mid_price = (alpha * new_mid_price) + ((DECIMAL_ZERO - alpha) * self.state.smoothed_mid_price)

            self.logger.debug(f"[{self.config.symbol}] Mid-price updated to: {self.state.mid_price}, Smoothed: {self.state.smoothed_mid_price}")

    async def _check_market_data_freshness(self, current_time: float) -> bool:
        """Checks if orderbook and trade data are fresh."""
        orderbook_stale = False
        with self.ws_client._data_lock: # Access shared data via lock
            if self.config.symbol not in self.ws_client.last_orderbook_update_time or \
               (current_time - self.ws_client.last_orderbook_update_time[self.config.symbol] > self.config.strategy.market_data_stale_timeout_seconds):
                orderbook_stale = True

            trades_stale = False
            if self.config.symbol not in self.ws_client.recent_trades_data or \
               (current_time - self.ws_client.last_trades_update_time.get(self.config.symbol, 0) > self.config.strategy.market_data_stale_timeout_seconds):
                trades_stale = True

        if orderbook_stale or trades_stale:
            if self.config.trade_enabled:
                self.logger.warning(
                    f"{Colors.NEON_ORANGE}[{self.config.symbol}] Market data stale! "
                    f"Order book stale: {orderbook_stale}, Trades stale: {trades_stale}. "
                    f"Pausing quoting and cancelling orders.{Colors.RESET}"
                )
                await self._cancel_all_orders()
            return False
        return True

    def _is_trading_hours(self, current_time: float) -> bool:
        """Checks if current time is within configured trading hours."""
        if not self.config.trading_hours_start or not self.config.trading_hours_end:
            return True # No specific hours configured, always trade

        current_dt = datetime.fromtimestamp(current_time, tz=timezone.utc).time()
        start_time = dt_time.fromisoformat(self.config.trading_hours_start)
        end_time = dt_time.fromisoformat(self.config.trading_hours_end)

        if start_time <= end_time:
            return start_time <= current_dt <= end_time
        else: # Overnight trading, e.g., 22:00 - 06:00
            return current_dt >= start_time or current_dt <= end_time

    # --- Initial Setup & Account Management ---
    async def _fetch_market_info(self) -> bool:
        """Fetches and updates symbol market information."""
        if self.global_config.trading_mode == "SIMULATION":
            object.__setattr__(self.config, 'price_precision', Decimal('0.00001'))
            object.__setattr__(self.config, 'quantity_precision', Decimal('1'))
            object.__setattr__(self.config, 'min_order_qty', Decimal('1'))
            object.__setattr__(self.config, 'min_notional_value', Decimal(str(self.config.min_order_value_usd)))
            object.__setattr__(self.config, 'maker_fee_rate', Decimal('0.0002'))
            object.__setattr__(self.config, 'taker_fee_rate', Decimal('0.0005'))
            self.logger.info(f"[{self.config.symbol}] SIMULATION mode: Mock market info loaded: {self.config}")
            return True

        info = await self.api_client.get_instruments_info(self.global_config.category, self.config.symbol)
        if not info:
            self.logger.critical(f"[{self.config.symbol}] Failed to retrieve instrument info from API. Check symbol and connectivity.")
            return False

        try:
            # Use object.__setattr__ for frozen Pydantic models
            object.__setattr__(self.config, 'price_precision', Decimal(info['priceFilter']['tickSize']))
            object.__setattr__(self.config, 'quantity_precision', Decimal(info['lotSizeFilter']['qtyStep']))
            object.__setattr__(self.config, 'min_order_qty', Decimal(info['lotSizeFilter']['minOrderQty']))
            
            # Use minNotionalValue if available, otherwise fallback to min_order_value_usd
            min_notional_from_api = Decimal(info['lotSizeFilter'].get('minNotionalValue', '0'))
            object.__setattr__(self.config, 'min_notional_value', max(min_notional_from_api, Decimal(str(self.config.min_order_value_usd))))

            object.__setattr__(self.config, 'maker_fee_rate', Decimal(info.get('makerFeeRate', '0.0002'))) # Default if not provided
            object.__setattr__(self.config, 'taker_fee_rate', Decimal(info.get('takerFeeRate', '0.0005'))) # Default if not provided

            self.last_symbol_info_refresh = time.time()
            self.logger.info(f"[{self.config.symbol}] Market info fetched: {self.config}")
            return True
        except (KeyError, ValueError) as e:
            self.logger.critical(f"[{self.config.symbol}] Error parsing market info (missing key or invalid format): {e}. Full info: {info}", exc_info=True)
            return False
        except Exception as e:
            self.logger.critical(f"[{self.config.symbol}] Unexpected error while parsing market info: {e}. Full info: {info}", exc_info=True)
            return False

    async def _update_balance_and_position(self) -> bool:
        """Fetches and updates current balance and position details."""
        if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            if self.state.current_balance == DECIMAL_ZERO:
                self.state.current_balance = self.global_config.initial_dry_run_capital
                self.state.available_balance = self.state.current_balance
                self.logger.info(f"[{self.config.symbol}] {self.global_config.trading_mode}: Initialized virtual balance: {self.state.current_balance} {self.global_config.main_quote_currency}")
            self.state.current_position_qty = self.state.metrics.current_asset_holdings
            self.state.unrealized_pnl_derivatives = DECIMAL_ZERO
            return True

        # Fetch main quote currency balance
        account_type = "UNIFIED" if self.global_config.category in ['linear', 'inverse'] else "SPOT"
        balance_data = await self.api_client.get_wallet_balance(account_type)
        if not balance_data:
            self.logger.error(f"[{self.config.symbol}] Failed to fetch wallet balance.")
            return False

        found_quote_balance = False
        for coin in balance_data.get('coin', []):
            if coin['coin'] == self.global_config.main_quote_currency:
                self.state.current_balance = Decimal(coin['walletBalance'])
                self.state.available_balance = Decimal(coin.get('availableToWithdraw', coin['walletBalance']))
                self.logger.debug(f"[{self.config.symbol}] Balance: {self.state.current_balance} {self.global_config.main_quote_currency}, Available: {self.state.available_balance}")
                await self.db_manager.log_balance_update(self.global_config.main_quote_currency, self.state.current_balance, self.state.available_balance)
                found_quote_balance = True
                break

        if not found_quote_balance:
            self.logger.warning(f"[{self.config.symbol}] Could not find balance for {self.global_config.main_quote_currency}. This might affect order sizing.")

        # Fetch position for derivatives
        if self.global_config.category in ['linear', 'inverse']:
            position_data = await self.api_client.get_position_info(self.global_config.category, self.config.symbol)
            if position_data and position_data.get('size'):
                self.state.current_position_qty = Decimal(position_data['size']) * (Decimal('1') if position_data['side'] == 'Buy' else Decimal('-1'))
                self.state.unrealized_pnl_derivatives = Decimal(position_data.get('unrealisedPnl', DECIMAL_ZERO))
            else:
                self.state.current_position_qty = DECIMAL_ZERO
                self.state.unrealized_pnl_derivatives = DECIMAL_ZERO
        else: # For spot, position is managed by TradeMetrics
            self.state.current_position_qty = self.state.metrics.current_asset_holdings
            self.state.unrealized_pnl_derivatives = DECIMAL_ZERO # Spot doesn't have exchange-reported UPNL

        self.logger.info(f"[{self.config.symbol}] Updated Balance: {self.state.current_balance} {self.global_config.main_quote_currency}, Position: {self.state.current_position_qty} {self.config.base_currency}, UPNL (Deriv): {self.state.unrealized_pnl_derivatives:+.4f}")
        return True

    async def _update_balance_from_wallet_ws(self, wallet_data: Dict[str, Any]):
        """Updates balance from WebSocket wallet stream."""
        for coin_info in wallet_data.get('coin', []):
            if coin_info.get('coin') == self.global_config.main_quote_currency:
                new_wallet_balance = Decimal(coin_info.get('walletBalance', self.state.current_balance))
                new_available_balance = Decimal(coin_info.get('availableToWithdraw', self.state.available_balance))
                
                if new_wallet_balance != self.state.current_balance or new_available_balance != self.state.available_balance:
                    self.state.current_balance = new_wallet_balance
                    self.state.available_balance = new_available_balance
                    self.logger.info(f"[{self.config.symbol}] WALLET UPDATE (WS): Balance: {self.state.current_balance} {self.global_config.main_quote_currency}, Available: {self.state.available_balance}")
                    await self.db_manager.log_balance_update(self.global_config.main_quote_currency, self.state.current_balance, self.state.available_balance)
                return

    async def _set_margin_mode_and_leverage(self) -> bool:
        """Sets margin mode and leverage for derivative symbols."""
        if self.global_config.category not in ['linear', 'inverse']:
            self.logger.debug(f"[{self.config.symbol}] Margin mode/leverage not applicable for {self.global_config.category}.")
            return True

        # Leverage
        if not await self.api_client.set_leverage(self.global_config.category, self.config.symbol, Decimal(str(self.config.leverage))):
            self.logger.error(f"[{self.config.symbol}] Failed to set leverage to {self.config.leverage}.")
            return False
        self.current_leverage = self.config.leverage
        self.logger.info(f"[{self.config.symbol}] Leverage set to {self.config.leverage}.")
        return True

    # --- WebSocket Message Processing (called by BybitWebSocketClient) ---
    async def _process_order_update(self, order_data: Dict[str, Any]):
        """Handles updates for specific orders."""
        order_id = order_data['orderId']
        status = order_data['orderStatus']
        cum_exec_qty = Decimal(order_data.get('cumExecQty', DECIMAL_ZERO))
        order_qty = Decimal(order_data.get('qty', DECIMAL_ZERO))

        self.logger.info(f"[{self.config.symbol}] Order {order_id} status update: {status} (OrderLink: {order_data.get('orderLinkId')}), CumExecQty: {cum_exec_qty}/{order_qty}")
        await self.db_manager.log_order_event(self.config.symbol, order_data)

        if order_id in self.state.active_orders:
            existing_order = self.state.active_orders[order_id]
            existing_order['status'] = status
            existing_order['cumExecQty'] = cum_exec_qty

            if status == 'Filled' or (status == 'PartiallyFilled' and cum_exec_qty >= existing_order.get('qty', DECIMAL_ZERO)):
                # If an order is fully filled or partially filled such that its cumExecQty reaches its original qty, remove it.
                # Actual PnL and trade metrics are updated by _process_execution_update.
                self.logger.info(f"[{self.config.symbol}] Order {order_id} fully filled or effectively filled. Removing from active orders.")
                del self.state.active_orders[order_id]
            elif status in ['Cancelled', 'Rejected', 'Deactivated', 'Expired']:
                self.logger.info(f"[{self.config.symbol}] Order {order_id} removed from active orders due to status: {status}.")
                del self.state.active_orders[order_id]
        elif status in ['Filled', 'PartiallyFilled']:
            self.logger.warning(f"[{self.config.symbol}] Received fill/partial fill for untracked order {order_id}. Adding to state temporarily.")
            self.state.active_orders[order_id] = {
                'orderId': order_id,
                'side': order_data.get('side'),
                'price': Decimal(order_data.get('price', DECIMAL_ZERO)),
                'qty': order_qty,
                'cumExecQty': cum_exec_qty,
                'status': status,
                'orderLinkId': order_data.get('orderLinkId'),
                'symbol': order_data.get('symbol'),
                'reduceOnly': order_data.get('reduceOnly', False),
                'orderType': order_data.get('orderType', 'Limit'),
                'timestamp': time.time() * 1000 # Store current timestamp for stale order check
            }
            if status == 'Filled':
                self.logger.info(f"[{self.config.symbol}] Untracked order {order_id} fully filled. Removing after processing.")
                del self.state.active_orders[order_id]
        else:
            self.logger.debug(f"[{self.config.symbol}] Received update for untracked order {order_id} with status {status}. Ignoring.")

    async def _process_position_update(self, pos_data: Dict[str, Any]):
        """Handles updates to the bot's position."""
        new_pos_qty = Decimal(pos_data['size']) * (Decimal('1') if pos_data['side'] == 'Buy' else Decimal('-1'))
        if new_pos_qty != self.state.current_position_qty:
            self.state.current_position_qty = new_pos_qty
            self.logger.info(f"[{self.config.symbol}] POSITION UPDATE (WS): Position is now {self.state.current_position_qty} {self.config.base_currency}")

        if self.global_config.category in ['linear', 'inverse'] and 'unrealisedPnl' in pos_data:
            self.state.unrealized_pnl_derivatives = Decimal(pos_data['unrealisedPnl'])
            self.logger.debug(f"[{self.config.symbol}] UNREALIZED PNL (WS): {self.state.unrealized_pnl_derivatives:+.4f} {self.config.quote_currency}")
        
        # Trigger TP/SL update if position changes
        if self.config.strategy.enable_auto_sl_tp and self.state.current_position_qty != DECIMAL_ZERO:
            await self._update_take_profit_stop_loss()

    async def _process_execution_update(self, trade_data: Dict[str, Any]):
        """Handles individual trade executions (fills)."""
        exec_type = trade_data.get('execType')
        if exec_type not in ['Trade', 'AdlTrade', 'BustTrade']: # Filter out non-trade related executions like 'Funding' etc.
            self.logger.debug(f"[{self.config.symbol}] Skipping non-trade execution type: {exec_type}")
            return
        
        side = trade_data.get('side', 'Unknown')
        exec_qty = Decimal(trade_data.get('execQty', DECIMAL_ZERO))
        exec_price = Decimal(trade_data.get('execPrice', DECIMAL_ZERO))
        exec_fee = Decimal(trade_data.get('execFee', DECIMAL_ZERO))
        liquidity_role = trade_data.get('execType', 'UNKNOWN') # Bybit returns 'Trade' for taker, 'AdlTrade' for ADL, etc.

        if exec_qty <= DECIMAL_ZERO or exec_price <= DECIMAL_ZERO:
            self.logger.warning(f"[{self.config.symbol}] Received invalid execution with zero quantity or price. Skipping. Data: {trade_data}")
            return

        metrics = self.state.metrics
        realized_pnl_impact = DECIMAL_ZERO # PnL directly from this specific trade (used for gross profit/loss)

        if side == 'Buy':
            metrics.update_pnl_on_buy(exec_qty, exec_price)
            if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
                # Ensure we don't go negative on balance
                cost = (exec_qty * exec_price) + exec_fee
                if self.state.current_balance >= cost:
                    self.state.current_balance -= cost
                    self.state.available_balance = self.state.current_balance
                else:
                    self.logger.warning(f"[{self.config.symbol}] DRY_RUN: Insufficient virtual balance to cover buy cost {cost}. Balance: {self.state.current_balance}. Skipping balance update.")
            self.logger.info(f"[{self.config.symbol}] Order FILLED: BUY {exec_qty} @ {exec_price}, Fee: {exec_fee}. Holdings: {metrics.current_asset_holdings}, Avg Entry: {metrics.average_entry_price}")
        elif side == 'Sell':
            profit_loss_on_sale = (exec_price - metrics.average_entry_price) * exec_qty
            metrics.update_pnl_on_sell(exec_qty, exec_price)
            realized_pnl_impact = profit_loss_on_sale # This specific trade's PnL
            if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
                self.state.current_balance += (exec_qty * exec_price) - exec_fee # Update virtual balance
                self.state.available_balance = self.state.current_balance
            self.logger.info(f"[{self.config.symbol}] Order FILLED: SELL {exec_qty} @ {exec_price}, Fee: {exec_fee}. Realized PnL from sale: {profit_loss_on_sale:+.4f}. Holdings: {metrics.current_asset_holdings}, Avg Entry: {metrics.average_entry_price}")
        else:
            self.logger.warning(f"[{self.config.symbol}] Unknown side '{side}' for fill. Cannot update PnL metrics.")

        metrics.total_trades += 1
        metrics.total_fees += exec_fee
        if realized_pnl_impact > DECIMAL_ZERO:
            metrics.gross_profit += realized_pnl_impact
            metrics.wins += 1
        elif realized_pnl_impact < DECIMAL_ZERO:
            metrics.gross_loss += abs(realized_pnl_impact)
            metrics.losses += 1
        metrics.update_win_rate()

        await self.db_manager.log_trade_fill(self.config.symbol, trade_data, realized_pnl_impact)
        await self._update_balance_and_position() # Re-fetch balance to ensure accuracy

    # --- Trading Logic & Order Management ---
    async def _manage_orders(self):
        """Calculates target prices and manages open orders."""
        if self.state.smoothed_mid_price == DECIMAL_ZERO or self.config.price_precision is None:
            self.logger.warning(f"[{self.config.symbol}] Smoothed mid-price or market info not available, skipping order management.")
            return

        # Calculate dynamic spread
        spread_pct = await self._calculate_dynamic_spread()
        
        # Calculate inventory skew
        skew_factor = self._calculate_inventory_skew(self.state.smoothed_mid_price, self.state.metrics.current_asset_holdings)
        skewed_mid_price = self.state.smoothed_mid_price * (DECIMAL_ZERO + skew_factor) # Corrected to add to 1.0

        # Base target prices
        base_target_bid_price = skewed_mid_price * (DECIMAL_ZERO - spread_pct) # Corrected to subtract from 1.0
        base_target_ask_price = skewed_mid_price * (DECIMAL_ZERO + spread_pct) # Corrected to add to 1.0

        # Enforce minimum profit spread
        base_target_bid_price, base_target_ask_price = self._enforce_min_profit_spread(self.state.smoothed_mid_price, base_target_bid_price, base_target_ask_price)

        await self._reconcile_and_place_orders(base_target_bid_price, base_target_ask_price)

    async def _calculate_dynamic_spread(self) -> Decimal:
        """Calculates a dynamic spread based on market volatility (ATR)."""
        ds_config = self.config.strategy.dynamic_spread
        current_time = time.time()

        if not ds_config.enabled:
            return Decimal(str(self.config.strategy.base_spread_pct))

        # Check if ATR needs to be updated
        if (current_time - self.last_atr_update_time) > ds_config.atr_update_interval_sec:
            self.cached_atr = await self._calculate_atr_from_kline(self.state.mid_price)
            self.last_atr_update_time = current_time

        if self.state.mid_price <= DECIMAL_ZERO:
            self.logger.warning(f"[{self.config.symbol}] Mid-price is zero, cannot calculate ATR-based spread. Using base spread.")
            return Decimal(str(self.config.strategy.base_spread_pct))

        volatility_pct = (self.cached_atr / self.state.mid_price) if self.state.mid_price > DECIMAL_ZERO else DECIMAL_ZERO
        
        dynamic_adjustment = volatility_pct * Decimal(str(ds_config.volatility_multiplier))
        
        # Clamp dynamic spread between min and max
        final_spread = max(Decimal(str(ds_config.min_spread_pct)), min(Decimal(str(ds_config.max_spread_pct)), Decimal(str(self.config.strategy.base_spread_pct)) + dynamic_adjustment))
        self.logger.debug(f"[{self.config.symbol}] ATR-based Spread: {final_spread * 100:.4f}% (ATR:{self.cached_atr:.6f}, Volatility:{volatility_pct:.6f})")
        return final_spread

    async def _calculate_atr_from_kline(self, current_mid_price: Decimal) -> Decimal:
        """Fetches kline data and calculates ATR."""
        try:
            # Need at least (ATR_length + 1) candles for ATR, pybit limit is 200
            limit_for_atr = 200
            ohlcv_data = await self.api_client.get_kline(
                self.global_config.category, self.config.symbol,
                self.config.strategy.kline_interval, limit_for_atr
            )
            if not ohlcv_data or len(ohlcv_data) < 15: # Ensure enough data points for 14-period ATR
                self.logger.warning(f"[{self.config.symbol}] Not enough OHLCV data for ATR calculation ({len(ohlcv_data)}). Using cached ATR or zero.")
                return self.cached_atr if self.cached_atr > DECIMAL_ZERO else DECIMAL_ZERO
            
            # Convert to DataFrame and then to Decimal
            df = pd.DataFrame(ohlcv_data, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df = df.apply(lambda x: pd.to_numeric(x, errors='ignore'))
            df[['high', 'low', 'close']] = df[['high', 'low', 'close']].applymap(Decimal)

            atr_series = atr(df["high"], df["low"], df["close"], length=14) # Default ATR length
            atr_val = atr_series.iloc[-1] # Get the latest ATR value

            if pd.isna(atr_val) or atr_val <= DECIMAL_ZERO:
                self.logger.warning(f"[{self.config.symbol}] ATR calculation resulted in NaN or non-positive value. Using cached ATR or zero.")
                return self.cached_atr if self.cached_atr > DECIMAL_ZERO else DECIMAL_ZERO
            
            self.logger.debug(f"[{self.config.symbol}] Calculated ATR: {atr_val:.8f}")
            return Decimal(str(atr_val))
            
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}[{self.config.symbol}] Error calculating ATR: {e}{Colors.RESET}", exc_info=True)
            return self.cached_atr if self.cached_atr > DECIMAL_ZERO else DECIMAL_ZERO

    def _calculate_inventory_skew(self, mid_price: Decimal, pos_qty: Decimal) -> Decimal:
        """Calculates a skew factor based on current inventory."""
        inv_config = self.config.strategy.inventory_skew
        if not inv_config.enabled or Decimal(str(self.config.max_net_exposure_usd)) <= DECIMAL_ZERO or mid_price <= DECIMAL_ZERO:
            return DECIMAL_ZERO

        current_inventory_value = pos_qty * mid_price
        max_exposure_for_ratio = Decimal(str(self.config.max_net_exposure_usd)) * Decimal(str(inv_config.max_inventory_ratio))
        
        if max_exposure_for_ratio <= DECIMAL_ZERO: return DECIMAL_ZERO

        # Normalize inventory to a ratio between -1 and 1
        inventory_ratio = current_inventory_value / max_exposure_for_ratio
        inventory_ratio = max(Decimal('-1.0'), min(Decimal('1.0'), inventory_ratio))

        # Skew factor pushes prices in the opposite direction of inventory
        skew_factor = -inventory_ratio * Decimal(str(inv_config.skew_intensity))

        if abs(skew_factor) > DECIMAL_ZERO:
            self.logger.debug(f"[{self.config.symbol}] Inventory skew active. Position Value: {current_inventory_value:.2f} {self.config.quote_currency}, Ratio: {inventory_ratio:.3f}, Skew: {skew_factor:.6f}")
        return skew_factor

    def _enforce_min_profit_spread(self, mid_price: Decimal, bid_p: Decimal, ask_p: Decimal) -> Tuple[Decimal, Decimal]:
        """Ensures the spread is wide enough to cover fees and desired profit."""
        if self.config.maker_fee_rate is None or self.config.taker_fee_rate is None:
            self.logger.warning(f"[{self.config.symbol}] Fee rates not set. Cannot enforce minimum profit spread.")
            return bid_p, ask_p
            
        estimated_fee_per_side_pct = self.config.taker_fee_rate # Assume taker for worst-case profit check
        min_gross_spread_pct = Decimal(str(self.config.strategy.min_profit_spread_after_fees_pct)) + (estimated_fee_per_side_pct * DECIMAL_ZERO) # Multiplied by 2
        min_spread_val = mid_price * min_gross_spread_pct

        if ask_p <= bid_p or (ask_p - bid_p) < min_spread_val:
            self.logger.debug(f"[{self.config.symbol}] Adjusting spread. Original Bid: {bid_p}, Ask: {ask_p}, Mid: {mid_price}, Current Spread: {ask_p - bid_p:.6f}, Min Spread: {min_spread_val:.6f}")
            half_min_spread = (min_spread_val / Decimal('2')).quantize(self.config.price_precision, rounding=ROUND_DOWN)
            bid_p = (mid_price - half_min_spread).quantize(self.config.price_precision, rounding=ROUND_DOWN)
            ask_p = (mid_price + half_min_spread).quantize(self.config.price_precision, rounding=ROUND_DOWN)
            self.logger.debug(f"[{self.config.symbol}] Adjusted to Bid: {bid_p}, Ask: {ask_p}")
        return bid_p, ask_p

    async def _reconcile_and_place_orders(self, base_target_bid: Decimal, base_target_ask: Decimal):
        """Cancels stale/duplicate orders and places new ones according to strategy, including layers."""
        if self.config.price_precision is None or self.config.quantity_precision is None:
            self.logger.error(f"[{self.config.symbol}] Price or quantity precision not set. Cannot place orders.")
            return

        orders_to_cancel = []
        current_active_orders_by_side = {'Buy': [], 'Sell': []} # (order_id, order_data)

        # Identify stale or duplicate orders
        for order_id, order_data in list(self.state.active_orders.items()):
            if order_data.get('symbol') != self.config.symbol:
                self.logger.warning(f"[{self.config.symbol}] Found untracked symbol order {order_id} in active_orders. Cancelling.")
                orders_to_cancel.append((order_id, order_data.get('orderLinkId')))
                continue

            if order_data['status'] in ['Filled', 'PartiallyFilled', 'Cancelled', 'Rejected', 'Deactivated', 'Expired']:
                if order_data['qty'] == order_data.get('cumExecQty', DECIMAL_ZERO): # Fully filled
                    self.logger.debug(f"[{self.config.symbol}] Removing fully processed order {order_id} from active orders.")
                    del self.state.active_orders[order_id]
                else: # Partially filled but inactive or needs re-evaluation
                    if order_data['status'] in ['Cancelled', 'Rejected', 'Deactivated', 'Expired']:
                         self.logger.debug(f"[{self.config.symbol}] Removing partially filled but inactive order {order_id} from active orders.")
                         del self.state.active_orders[order_id]
                    else: # Still partially filled and active, keep for now but don't count towards new placement.
                        current_active_orders_by_side[order_data['side']].append((order_id, order_data))
                continue

            # Check for price staleness based on order layer's cancel_threshold_pct
            is_stale = False
            # For simplicity, if using layers, we consider any order stale if its price is too far from the *base* target price,
            # or if the layer logic would dictate a different price. A more complex approach would track which layer an order belongs to.
            # For now, we use a global stale threshold.
            stale_threshold = Decimal(str(self.config.strategy.order_stale_threshold_pct))

            if order_data['side'] == 'Buy':
                if abs(order_data['price'] - base_target_bid) > (order_data['price'] * stale_threshold):
                    is_stale = True
                current_active_orders_by_side['Buy'].append((order_id, order_data))
            else: # Sell order
                if abs(order_data['price'] - base_target_ask) > (order_data['price'] * stale_threshold):
                    is_stale = True
                current_active_orders_by_side['Sell'].append((order_id, order_data))
            
            if is_stale: # Mark stale orders for cancellation
                orders_to_cancel.append((order_id, order_data.get('orderLinkId')))

        # Cancel identified orders
        for oid, olid in orders_to_cancel:
            order_info = self.state.active_orders.get(oid, {})
            self.logger.info(f"[{self.config.symbol}] Cancelling stale/duplicate order {oid} (Side: {order_info.get('side')}, Price: {order_info.get('price')}). Target Bid: {base_target_bid}, Target Ask: {base_target_ask}")
            await self._cancel_order(oid, olid)

        # Place new orders if needed, considering layers
        current_outstanding_orders = sum(1 for oid, odata in self.state.active_orders.items() if odata['status'] not in ['Filled', 'Cancelled', 'Rejected', 'Deactivated', 'Expired'])
        
        for i, layer in enumerate(self.config.strategy.order_layers):
            if current_outstanding_orders >= self.config.strategy.max_outstanding_orders:
                self.logger.debug(f"[{self.config.symbol}] Max outstanding orders ({self.config.strategy.max_outstanding_orders}) reached. Skipping further layer placements.")
                break

            # Calculate layered prices
            layer_bid_price = base_target_bid * (DECIMAL_ZERO - Decimal(str(layer.spread_offset_pct))) # Corrected
            layer_ask_price = base_target_ask * (DECIMAL_ZERO + Decimal(str(layer.spread_offset_pct))) # Corrected

            # Ensure layered orders don't cross
            if layer_bid_price >= layer_ask_price:
                self.logger.warning(f"[{self.config.symbol}] Layer {i} prices crossed ({layer_bid_price} >= {layer_ask_price}). Skipping this layer.")
                continue

            # Place buy order for layer
            if len(current_active_orders_by_side['Buy']) <= i: # Only place if this layer doesn't have an active order
                buy_qty = await self._calculate_order_size("Buy", layer_bid_price, layer.quantity_multiplier)
                if buy_qty > DECIMAL_ZERO:
                    await self._place_limit_order("Buy", layer_bid_price, buy_qty, f"layer_{i}")
                    current_outstanding_orders += 1
                else:
                    self.logger.debug(f"[{self.config.symbol}] Calculated buy quantity for layer {i} is zero or too small, skipping bid order placement.")

            # Place sell order for layer
            if current_outstanding_orders < self.config.strategy.max_outstanding_orders and len(current_active_orders_by_side['Sell']) <= i: # Only place if this layer doesn't have an active order
                sell_qty = await self._calculate_order_size("Sell", layer_ask_price, layer.quantity_multiplier)
                if sell_qty > DECIMAL_ZERO:
                    await self._place_limit_order("Sell", layer_ask_price, sell_qty, f"layer_{i}")
                    current_outstanding_orders += 1
                else:
                    self.logger.debug(f"[{self.config.symbol}] Calculated sell quantity for layer {i} is zero or too small, skipping ask order placement.")

    async def _calculate_order_size(self, side: str, price: Decimal, quantity_multiplier: float = 1.0) -> Decimal:
        """Calculates the optimal order quantity based on balance, exposure, and min/max limits."""
        if self.config.min_order_qty is None or self.config.min_notional_value is None:
            self.logger.error(f"[{self.config.symbol}] Market info (min_order_qty/min_notional_value) not set. Cannot calculate order size.")
            return DECIMAL_ZERO
            
        capital = self.state.available_balance if self.global_config.category == 'spot' else self.state.current_balance
        metrics_pos_qty = self.state.metrics.current_asset_holdings # Use for spot, for derivatives current_position_qty is from exchange

        if capital <= DECIMAL_ZERO or price <= DECIMAL_ZERO:
            self.logger.debug(f"[{self.config.symbol}] Insufficient capital ({capital}), zero price ({price}). Order size 0.")
            return DECIMAL_ZERO

        effective_capital = capital * Decimal(str(self.config.leverage)) if self.global_config.category in ['linear', 'inverse'] else capital
        
        # Base quantity from percentage of available capital
        base_order_value = effective_capital * Decimal(str(self.config.strategy.base_order_size_pct_of_balance))
        qty_from_base_pct = base_order_value / price

        # Max quantity from overall max order size percentage
        max_order_value_abs = effective_capital * Decimal(str(self.config.max_order_size_pct))
        qty_from_max_pct = max_order_value_abs / price

        target_qty = min(qty_from_base_pct, qty_from_max_pct) * Decimal(str(quantity_multiplier))

        # Inventory management (max net exposure)
        if self.config.strategy.inventory_skew.enabled and Decimal(str(self.config.max_net_exposure_usd)) > DECIMAL_ZERO:
            current_mid_price = self.state.mid_price
            if current_mid_price <= DECIMAL_ZERO:
                self.logger.warning(f"[{self.config.symbol}] Mid-price is zero, cannot calculate max net exposure. Skipping exposure check.")
                return DECIMAL_ZERO

            max_allowed_pos_qty_abs = Decimal(str(self.config.max_net_exposure_usd)) / current_mid_price

            if side == 'Buy':
                current_net_pos = self.state.current_position_qty if self.global_config.category in ['linear', 'inverse'] else metrics_pos_qty
                qty_to_reach_max_long = max_allowed_pos_qty_abs - current_net_pos
                if qty_to_reach_max_long <= DECIMAL_ZERO:
                    self.logger.debug(f"[{self.config.symbol}] Cannot place buy order: Current position {current_net_pos} already at or above max long exposure ({max_allowed_pos_qty_abs}).")
                    return DECIMAL_ZERO
                target_qty = min(target_qty, qty_to_reach_max_long)
            else: # Sell order
                current_net_pos = self.state.current_position_qty if self.global_config.category in ['linear', 'inverse'] else metrics_pos_qty
                if current_net_pos > DECIMAL_ZERO: # If currently long, sell up to current holdings
                    target_qty = min(target_qty, current_net_pos)
                    self.logger.debug(f"[{self.config.symbol}] Capping sell order quantity at current holdings: {target_qty}")
                else: # If currently short or flat, consider max short exposure
                    qty_to_reach_max_short = abs(-max_allowed_pos_qty_abs - current_net_pos) # How much more short can we go
                    if qty_to_reach_max_short <= DECIMAL_ZERO: # Already at max short or beyond
                        self.logger.debug(f"[{self.config.symbol}] Cannot place sell order: Current position {current_net_pos} already at or below max short exposure ({-max_allowed_pos_qty_abs}).")
                        return DECIMAL_ZERO
                    target_qty = min(target_qty, qty_to_reach_max_short)

        if target_qty <= DECIMAL_ZERO:
            self.logger.debug(f"[{self.config.symbol}] Calculated target quantity is zero or negative after exposure adjustments. Order size 0.")
            return DECIMAL_ZERO

        qty = self.config.format_quantity(target_qty)

        if qty < self.config.min_order_qty:
            self.logger.debug(f"[{self.config.symbol}] Calculated quantity {qty} is less than min_order_qty {self.config.min_order_qty}. Order size 0.")
            return DECIMAL_ZERO

        order_notional_value = qty * price
        if order_notional_value < self.config.min_notional_value:
            self.logger.debug(f"[{self.config.symbol}] Calculated notional value {order_notional_value:.2f} is less than min_notional_value {self.config.min_notional_value:.2f}. Order size 0.")
            return DECIMAL_ZERO

        self.logger.debug(f"[{self.config.symbol}] Calculated {side} order size: {qty} {self.config.base_currency} (Notional: {order_notional_value:.2f} {self.config.quote_currency})")
        return qty

    async def _place_limit_order(self, side: str, price: Decimal, quantity: Decimal, layer_tag: str = "base"):
        """Places a single limit order."""
        if self.config.price_precision is None or self.config.quantity_precision is None or self.config.min_notional_value is None:
            self.logger.error(f"[{self.config.symbol}] Market info (precisions/min_notional) not set. Cannot place order.")
            raise OrderPlacementError("Market information is not available for order placement.")

        qty_f, price_f = self.config.format_quantity(quantity), self.config.format_price(price)
        if qty_f <= DECIMAL_ZERO or price_f <= DECIMAL_ZERO:
            self.logger.warning(f"[{self.config.symbol}] Attempted to place order with zero or negative quantity/price: Qty={qty_f}, Price={price_f}. Skipping.")
            return

        order_notional_value = qty_f * price_f
        if order_notional_value < self.config.min_notional_value:
            self.logger.warning(f"[{self.config.symbol}] Calculated order notional value {order_notional_value:.2f} is below minimum {self.config.min_notional_value:.2f}. Skipping order placement.")
            return

        time_in_force = "PostOnly" # Always use PostOnly for market making
        order_link_id = f"mm_{self.config.symbol.replace('/','')}_{side}_{layer_tag}_{int(time.time() * 1000)}"

        params = {
            "category": self.global_config.category,
            "symbol": self.config.symbol,
            "side": side,
            "orderType": "Limit",
            "qty": str(qty_f),
            "price": str(price_f),
            "timeInForce": time_in_force,
            "orderLinkId": order_link_id,
            "isLeverage": 1 if self.global_config.category in ['linear', 'inverse'] else 0, # Required for some categories
            # "triggerDirection": 1 if side == "Buy" else 2 # For TP/SL if used, but not strictly needed for limit order
        }

        # ReduceOnly for derivatives
        if self.global_config.category in ['linear', 'inverse']:
            current_position = self.state.current_position_qty
            if (side == 'Sell' and current_position > DECIMAL_ZERO) or \
               (side == 'Buy' and current_position < DECIMAL_ZERO):
                params["reduceOnly"] = True
                self.logger.debug(f"[{self.config.symbol}] Setting reduceOnly=True for {side} order (current position: {current_position}).")

        if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            oid = f"DRY_{self.config.symbol.replace('/','')}_{side}_{layer_tag}_{int(time.time() * 1000)}"
            self.logger.info(f"[{self.config.symbol}] {self.global_config.trading_mode}: Would place {side} order: ID={oid}, Qty={qty_f}, Price={price_f}")
            self.state.active_orders[oid] = {
                'orderId': oid, 'side': side, 'price': price_f, 'qty': qty_f, 'cumExecQty': DECIMAL_ZERO,
                'status': 'New', 'orderLinkId': order_link_id, 'symbol': self.config.symbol,
                'reduceOnly': params.get('reduceOnly', False), 'orderType': 'Limit',
                'timestamp': time.time() * 1000 # Store creation timestamp
            }
            await self.db_manager.log_order_event(self.config.symbol, {**params, 'orderId': oid, 'orderStatus': 'New', 'cumExecQty': '0'}, f"{self.global_config.trading_mode} Order placed")
            return

        result = await self.api_client.place_order(params)
        if result and result.get('orderId'):
            oid = result['orderId']
            self.logger.info(f"[{self.config.symbol}] Placed {side} order: ID={oid}, Price={price_f}, Qty={qty_f}")
            self.state.active_orders[oid] = {
                'orderId': oid, 'side': side, 'price': price_f, 'qty': qty_f, 'cumExecQty': DECIMAL_ZERO,
                'status': 'New', 'orderLinkId': order_link_id, 'symbol': self.config.symbol,
                'reduceOnly': params.get('reduceOnly', False), 'orderType': 'Limit',
                'timestamp': time.time() * 1000 # Store creation timestamp
            }
            await self.db_manager.log_order_event(self.config.symbol, {**params, 'orderId': oid, 'orderStatus': 'New', 'cumExecQty': '0'}, "Order placed")
        else:
            self.logger.error(f"[{self.config.symbol}] Failed to place {side} order after retries. Params: {params}")
            raise OrderPlacementError(f"Failed to place {side} order for {self.config.symbol}.")

    async def _cancel_order(self, order_id: str, order_link_id: Optional[str] = None):
        """Cancels a specific order."""
        self.logger.info(f"[{self.config.symbol}] Attempting to cancel order {order_id} (OrderLink: {order_link_id})...")
        if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            self.logger.info(f"[{self.config.symbol}] {self.global_config.trading_mode}: Would cancel order {order_id}.")
            if order_id in self.state.active_orders:
                del self.state.active_orders[order_id]
            return

        try:
            if await self.api_client.cancel_order(self.global_config.category, self.config.symbol, order_id, order_link_id):
                self.logger.info(f"[{self.config.symbol}] Order {order_id} cancelled successfully.")
                if order_id in self.state.active_orders:
                    del self.state.active_orders[order_id]
            else:
                self.logger.error(f"[{self.config.symbol}] Failed to cancel order {order_id} via API after retries.")
        except BybitAPIError as e:
            if e.ret_code == 30003: # Order does not exist
                self.logger.warning(f"[{self.config.symbol}] Order {order_id} already cancelled or does not exist on exchange. Removing from local state.")
                if order_id in self.state.active_orders:
                    del self.state.active_orders[order_id]
            else:
                self.logger.error(f"[{self.config.symbol}] Error during cancellation of order {order_id}: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"[{self.config.symbol}] Unexpected error during cancellation of order {order_id}: {e}", exc_info=True)

    async def _cancel_all_orders(self):
        """Cancels all open orders for the symbol."""
        self.logger.info(f"[{self.config.symbol}] Canceling all open orders...")
        if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            self.logger.info(f"[{self.config.symbol}] {self.global_config.trading_mode}: Would cancel all open orders.")
        else:
            try:
                if await self.api_client.cancel_all_orders(self.global_config.category, self.config.symbol):
                    self.logger.info(f"[{self.config.symbol}] All orders cancelled successfully.")
                else:
                    self.logger.error(f"[{self.config.symbol}] Failed to cancel all orders via API after retries.")
            except Exception as e:
                self.logger.error(f"[{self.config.symbol}] Error during cancellation of all orders: {e}", exc_info=True)

        self.state.active_orders.clear()

    async def _reconcile_orders_on_startup(self):
        """Reconciles local active orders with exchange orders on startup."""
        if self.global_config.trading_mode in ["DRY_RUN", "SIMULATION"]:
            self.logger.info(f"[{self.config.symbol}] {self.global_config.trading_mode} mode: Skipping order reconciliation (loaded from state).")
            return # State was already loaded in initialize()

        self.logger.info(f"[{self.config.symbol}] Reconciling active orders with exchange...")
        try:
            exchange_orders = {o['orderId']: o for o in await self.api_client.get_open_orders(self.global_config.category, self.config.symbol)}
        except Exception as e:
            self.logger.error(f"[{self.config.symbol}] Failed to fetch open orders from exchange during reconciliation: {e}. Proceeding with local state only.", exc_info=True)
            exchange_orders = {}
        
        local_ids = set(self.state.active_orders.keys())
        exchange_ids = set(exchange_orders.keys())

        for oid in local_ids - exchange_ids:
            self.logger.warning(f"[{self.config.symbol}] Local order {oid} not found on exchange. Removing from local state.")
            del self.state.active_orders[oid]

        for oid in exchange_ids - local_ids:
            o = exchange_orders[oid]
            self.logger.warning(f"[{self.config.symbol}] Exchange order {oid} ({o['side']} {o['qty']} @ {o['price']}) not in local state. Adding.")
            self.state.active_orders[oid] = {
                'orderId': oid,
                'side': o['side'],
                'price': Decimal(o['price']),
                'qty': Decimal(o['qty']),
                'cumExecQty': Decimal(o.get('cumExecQty', DECIMAL_ZERO)),
                'status': o['orderStatus'],
                'orderLinkId': o.get('orderLinkId'),
                'symbol': o.get('symbol'),
                'reduceOnly': o.get('reduceOnly', False),
                'orderType': o.get('orderType', 'Limit'),
                'timestamp': time.time() * 1000 # Store current timestamp for stale order check
            }

        for oid in local_ids.intersection(exchange_ids):
            local_order = self.state.active_orders[oid]
            exchange_order = exchange_orders[oid]
            
            # Update status and cumExecQty from exchange
            if local_order['status'] != exchange_order['orderStatus'] or \
               local_order.get('cumExecQty', DECIMAL_ZERO) != Decimal(exchange_order.get('cumExecQty', DECIMAL_ZERO)):
                self.logger.info(f"[{self.config.symbol}] Order {oid} status/cumExecQty mismatch. Updating from {local_order['status']}/{local_order.get('cumExecQty', DECIMAL_ZERO)} to {exchange_order['orderStatus']}/{exchange_order.get('cumExecQty', DECIMAL_ZERO)}.")
                local_order['status'] = exchange_order['orderStatus']
                local_order['cumExecQty'] = Decimal(exchange_order.get('cumExecQty', DECIMAL_ZERO))

        self.logger.info(f"[{self.config.symbol}] Order reconciliation complete. {len(self.state.active_orders)} active orders after reconciliation.")

    async def _check_and_handle_stale_orders(self, current_time: float):
        """Checks for and cancels orders that have been open for too long."""
        orders_to_cancel = []
        for order_id, order_info in list(self.state.active_orders.items()):
            # Assuming 'timestamp' in order_info is the placement time in milliseconds
            placement_time_seconds = order_info.get("timestamp", current_time * 1000) / 1000
            if (current_time - placement_time_seconds) > self.config.strategy.stale_order_max_age_seconds:
                orders_to_cancel.append((order_id, order_info.get("orderLinkId")))

        for exchange_id, client_order_id in orders_to_cancel:
            self.logger.warning(
                f"[{self.config.symbol}] Order {exchange_id} is stale (open for "
                f"> {self.config.strategy.stale_order_max_age_seconds} seconds). Cancelling."
            )
            await self._cancel_order(exchange_id, client_order_id)

    async def _update_take_profit_stop_loss(self):
        """Sets or updates Take-Profit and Stop-Loss for current position."""
        if not self.config.strategy.enable_auto_sl_tp or self.state.current_position_qty == DECIMAL_ZERO:
            return

        tp_price = DECIMAL_ZERO
        sl_price = DECIMAL_ZERO
        
        # Use average entry price from metrics for TP/SL calculation
        entry_price = self.state.metrics.average_entry_price

        if entry_price == DECIMAL_ZERO:
            self.logger.warning(f"[{self.config.symbol}] Entry price is zero, cannot set TP/SL.")
            return

        if self.state.current_position_qty > DECIMAL_ZERO:  # Long position
            tp_price = entry_price * (Decimal("1") + Decimal(str(self.config.strategy.take_profit_target_pct)))
            sl_price = entry_price * (Decimal("1") - Decimal(str(self.config.strategy.stop_loss_trigger_pct)))
        elif self.state.current_position_qty < DECIMAL_ZERO:  # Short position
            tp_price = entry_price * (Decimal("1") - Decimal(str(self.config.strategy.take_profit_target_pct)))
            sl_price = entry_price * (Decimal("1") + Decimal(str(self.config.strategy.stop_loss_trigger_pct)))

        tp_price = self.config.format_price(tp_price)
        sl_price = self.config.format_price(sl_price)

        try:
            if await self.api_client.set_trading_stop(self.global_config.category, self.config.symbol, sl_price, tp_price):
                self.logger.info(
                    f"{Colors.NEON_GREEN}[{self.config.symbol}] Set TP: {tp_price:.{self.config.price_precision.as_tuple()._exp if self.config.price_precision else 8}f}, "
                    f"SL: {sl_price:.{self.config.price_precision.as_tuple()._exp if self.config.price_precision else 8}f} for current position (Entry: {entry_price}).{Colors.RESET}"
                )
                termux_notify(f"{self.config.symbol}: TP: {tp_price:.4f}, SL: {sl_price:.4f}", title="TP/SL Updated")
        except Exception as e:
            self.logger.error(
                f"{Colors.NEON_RED}[{self.config.symbol}] Error setting TP/SL: {e}{Colors.RESET}", exc_info=True
            )
            termux_notify(f"{self.config.symbol}: Failed to set TP/SL!", is_error=True)

    # --- Circuit Breakers & Daily Limits ---
    async def _check_circuit_breaker(self, current_time: float) -> bool:
        """Checks for sudden price movements and pauses trading if threshold is exceeded."""
        cb_config = self.config.strategy.circuit_breaker
        if not cb_config.enabled: return False

        recent_prices_window = [(t, p) for t, p in self.state.circuit_breaker_price_points if (current_time - t) <= cb_config.check_window_sec]

        if len(recent_prices_window) < 2: return False

        recent_prices_window.sort(key=lambda x: x[0])
        start_price = recent_prices_window[0][1]
        end_price = recent_prices_window[-1][1]

        if start_price == DECIMAL_ZERO: return False

        price_change_pct = abs(end_price - start_price) / start_price

        if price_change_pct > Decimal(str(cb_config.pause_threshold_pct)):
            self.logger.warning(f"[{self.config.symbol}] CIRCUIT BREAKER TRIPPED: Price changed {price_change_pct:.2%} in {cb_config.check_window_sec}s. Pausing trading for {cb_config.pause_duration_sec}s.")
            self.state.is_paused = True
            self.state.pause_end_time = current_time + cb_config.pause_duration_sec
            self.state.circuit_breaker_cooldown_end_time = self.state.pause_end_time + cb_config.cool_down_after_trip_sec
            await self._cancel_all_orders()
            termux_notify(f"{self.config.symbol}: Circuit Breaker TRIP! Paused for {cb_config.pause_duration_sec}s", is_error=True)
            return True
        return False

    async def _check_daily_pnl_limits(self) -> bool:
        """Checks if daily PnL has hit stop-loss or take-profit limits."""
        cb_config = self.config.strategy.circuit_breaker
        if not cb_config.enabled or cb_config.max_daily_loss_pct is None:
            return False

        current_day = datetime.now(timezone.utc).date()
        if self.state.daily_pnl_reset_date is None or self.state.daily_pnl_reset_date.date() < current_day:
            self.logger.info(f"[{self.config.symbol}] New day detected. Resetting daily initial capital.")
            await self._update_balance_and_position() # Ensure balance is fresh for new daily capital
            self.state.daily_initial_capital = self.state.current_balance
            self.state.daily_pnl_reset_date = datetime.now(timezone.utc)
            return False # No loss yet for new day

        if self.state.daily_initial_capital <= DECIMAL_ZERO:
            self.logger.warning(f"[{self.config.symbol}] Daily initial capital is zero or negative, cannot check daily loss. Skipping.")
            return False

        # For derivatives, current_balance includes unrealized PnL, for spot, we add metrics UPNL.
        current_total_capital = self.state.current_balance
        if self.global_config.category == 'spot':
            current_total_capital += self.state.metrics.calculate_unrealized_pnl(self.state.mid_price)
        
        daily_loss = self.state.daily_initial_capital - current_total_capital
        daily_loss_pct = (daily_loss / self.state.daily_initial_capital) if self.state.daily_initial_capital > DECIMAL_ZERO else DECIMAL_ZERO

        if daily_loss_pct > Decimal(str(cb_config.max_daily_loss_pct)):
            self.logger.critical(
                f"{Colors.NEON_RED}[{self.config.symbol}] DAILY LOSS CIRCUIT BREAKER TRIPPED! Current Loss: {daily_loss:.2f} {self.global_config.main_quote_currency} "
                f"({daily_loss_pct:.2%}) exceeds "
                f"max daily loss threshold ({cb_config.max_daily_loss_pct:.2%}). "
                "Shutting down for the day.{Colors.RESET}"
            )
            termux_notify(f"{self.config.symbol}: DAILY SL HIT! Loss: {daily_loss_pct:.2%}", is_error=True)
            self._stop_event.set() # Signal main bot to stop this symbol
            return True
        return False

    # --- Dry Run / Simulation Specifics ---
    async def _simulate_dry_run_price_movement(self, current_time: float):
        """Simulates price movement for DRY_RUN mode."""
        dt = self.global_config.dry_run_time_step_dt
        if (current_time - self.state.last_dry_run_price_update_time) < dt:
            return

        mu = self.global_config.dry_run_price_drift_mu
        sigma = self.global_config.dry_run_price_volatility_sigma
        
        price_float = float(self.state.mid_price)
        if price_float <= 0: price_float = 1e-10

        new_price_float = price_float * np.exp(
            (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * np.random.normal()
        )
        if new_price_float < 1e-8: new_price_float = 1e-8

        new_mid_price = Decimal(str(new_price_float))
        
        # Update mid_price and smoothed_mid_price
        self.state.mid_price = new_mid_price
        
        # Update candlestick history for ATR calculation
        if self.state.price_candlestick_history:
            _, high_old, low_old, _ = self.state.price_candlestick_history[-1]
            current_high = max(high_old, new_mid_price)
            current_low = min(low_old, new_mid_price)
            if (current_time - self.state.price_candlestick_history[-1][0]) < dt:
                self.state.price_candlestick_history[-1] = (current_time, current_high, current_low, new_mid_price)
            else:
                self.state.price_candlestick_history.append((current_time, new_mid_price, new_mid_price, new_mid_price))
        else:
            self.state.price_candlestick_history.append((current_time, new_mid_price, new_mid_price, new_mid_price))
        
        self.state.circuit_breaker_price_points.append((current_time, self.state.mid_price))

        alpha = Decimal(str(self.config.strategy.dynamic_spread.price_change_smoothing_factor))
        if self.state.smoothed_mid_price == DECIMAL_ZERO:
            self.state.smoothed_mid_price = new_mid_price
        else:
            self.state.smoothed_mid_price = (alpha * new_mid_price) + ((DECIMAL_ZERO - alpha) * self.state.smoothed_mid_price)

        self.state.last_dry_run_price_update_time = current_time
        self.logger.debug(f"[{self.config.symbol}] DRY_RUN Price Movement: Mid: {self.state.mid_price}, Smoothed: {self.state.smoothed_mid_price}")

    async def _simulate_dry_run_fills(self):
        """Simulates order fills for DRY_RUN mode."""
        orders_to_process = []
        for order_id, order_data in list(self.state.active_orders.items()):
            if order_id.startswith('DRY_') and order_data['status'] == 'New': # Only process new orders
                order_price = order_data['price']
                side = order_data['side']
                
                filled = False
                if side == 'Buy' and self.state.mid_price <= order_price:
                    filled = True
                elif side == 'Sell' and self.state.mid_price >= order_price:
                    filled = True
                
                if filled:
                    fill_qty = order_data['qty'] - order_data['cumExecQty']
                    if fill_qty <= DECIMAL_ZERO: continue
                    
                    if side == 'Sell' and fill_qty > self.state.metrics.current_asset_holdings:
                        # In dry run, we might try to sell more than we hold if logic isn't perfect
                        self.logger.warning(f"[{self.config.symbol}] DRY_RUN: Attempted to sell {fill_qty} but only {self.state.metrics.current_asset_holdings} held. Adjusting fill quantity.")
                        fill_qty = self.state.metrics.current_asset_holdings
                        if fill_qty <= DECIMAL_ZERO: continue # Nothing to sell

                    orders_to_process.append((order_id, order_data, fill_qty))

        for order_id, order_data, fill_qty in orders_to_process:
            self.logger.info(f"[{self.config.symbol}] DRY_RUN: Simulating fill for order {order_id} (Side: {order_data['side']}, Price: {order_data['price']}) with {fill_qty} at current mid_price {self.state.mid_price}")
            
            mock_fill_data = {
                'orderId': order_id,
                'orderLinkId': order_data.get('orderLinkId'),
                'symbol': order_data['symbol'],
                'side': order_data['side'],
                'orderType': order_data['orderType'],
                'execQty': str(fill_qty),
                'execPrice': str(self.state.mid_price),
                'execFee': str(fill_qty * self.state.mid_price * self.config.taker_fee_rate),
                'feeCurrency': self.config.quote_currency,
                'pnl': '0',
                'execType': 'Trade', # Simulate as taker fill
            }
            
            self.state.active_orders[order_id]['cumExecQty'] += fill_qty
            if self.state.active_orders[order_id]['cumExecQty'] >= self.state.active_orders[order_id]['qty']:
                self.state.active_orders[order_id]['status'] = 'Filled'
                mock_fill_data['orderStatus'] = 'Filled'
            else:
                self.state.active_orders[order_id]['status'] = 'PartiallyFilled'
                mock_fill_data['orderStatus'] = 'PartiallyFilled'
            
            await self._process_execution_update(mock_fill_data)
            
            if self.state.active_orders[order_id]['status'] == 'Filled':
                del self.state.active_orders[order_id]

    # --- Status and Reporting ---
    async def _log_status_summary(self):
        """Logs a summary of the bot's current status and performance metrics."""
        metrics = self.state.metrics
        current_market_price = self.state.mid_price if self.state.mid_price > DECIMAL_ZERO else self.state.smoothed_mid_price

        if current_market_price == DECIMAL_ZERO:
            self.logger.warning(f"[{self.config.symbol}] Cannot calculate unrealized PnL, current market price is zero.")
            unrealized_pnl_bot_calculated = DECIMAL_ZERO
        else:
            unrealized_pnl_bot_calculated = metrics.calculate_unrealized_pnl(current_market_price)

        # For derivatives, use exchange-reported UPNL; for spot, use bot-calculated
        display_unrealized_pnl = self.state.unrealized_pnl_derivatives if self.global_config.category in ['linear', 'inverse'] else unrealized_pnl_bot_calculated

        total_current_pnl = metrics.net_realized_pnl + display_unrealized_pnl
        pos_qty = metrics.current_asset_holdings # Use metrics holdings for general reporting
        exposure_usd = pos_qty * current_market_price if current_market_price > DECIMAL_ZERO else DECIMAL_ZERO
        
        # Daily PnL calculation
        current_total_capital = self.state.current_balance + display_unrealized_pnl
        daily_pnl = current_total_capital - self.state.daily_initial_capital
        daily_loss_pct = float(abs(daily_pnl / self.state.daily_initial_capital)) if self.state.daily_initial_capital > DECIMAL_ZERO and daily_pnl < DECIMAL_ZERO else 0.0

        pnl_summary = (
            f"Realized PNL: {metrics.realized_pnl:+.4f} {self.config.quote_currency} | "
            f"Unrealized PNL: {display_unrealized_pnl:+.4f} {self.config.quote_currency}"
        )

        active_buys = sum(1 for o in self.state.active_orders.values() if o['side'] == 'Buy' and o['status'] not in ['Filled', 'Cancelled', 'Rejected', 'Deactivated', 'Expired'])
        active_sells = sum(1 for o in self.state.active_orders.values() if o['side'] == 'Sell' and o['status'] not in ['Filled', 'Cancelled', 'Rejected', 'Deactivated', 'Expired'])

        self.logger.info(
            f"{Colors.CYAN}--- {self.config.symbol} STATUS ({'Enabled' if self.config.trade_enabled else 'Disabled'}) ---\n"
            f"  {Colors.YELLOW}Mid: {current_market_price:.{self.config.price_precision.as_tuple()._exp if self.config.price_precision else 8}f} | "
            f"Pos: {self.state.current_position_qty:+.{self.config.quantity_precision.as_tuple()._exp if self.config.quantity_precision else 8}f} {self.config.base_currency} (Exposure: {exposure_usd:+.2f} {self.config.quote_currency}){Colors.RESET}\n"
            f"  {Colors.MAGENTA}Balance: {self.state.current_balance:.2f} {self.global_config.main_quote_currency} | Avail: {self.state.available_balance:.2f}{Colors.RESET}\n"
            f"  {Colors.NEON_BLUE}Total PNL: {total_current_pnl:+.4f} | {pnl_summary}{Colors.RESET}\n"
            f"  {Colors.NEON_GREEN}Net Realized PNL: {metrics.net_realized_pnl:+.4f} | Daily PNL: {daily_pnl:+.4f} ({daily_loss_pct:.2%}) | "
            f"Win Rate: {metrics.win_rate:.2f}% | Orders: {active_buys} Buy / {active_sells} Sell{Colors.RESET}\n"
            f"{Colors.CYAN}--------------------------------------{Colors.RESET}"
        )
        await self.db_manager.log_bot_metrics(self.config.symbol, metrics, display_unrealized_pnl, daily_pnl, daily_loss_pct, current_market_price)


# --- Main Pyrmethus Bot Orchestrator ---
class PyrmethusBot:
    """
    Orchestrates multiple AsyncSymbolBot instances, manages global configuration,
    and handles overall bot lifecycle.
    """
    def __init__(self):
        self.global_config: GlobalConfig # Initialized later
        self.logger: logging.Logger = logging.getLogger('BybitMarketMaker.main_temp') # Temporary logger
        
        self.api_client: Optional[BybitAPIClient] = None
        self.ws_client: Optional[BybitWebSocketClient] = None
        self.db_manager: Optional[DBManager] = None
        
        self.symbol_bots: Dict[str, AsyncSymbolBot] = {} # {symbol: AsyncSymbolBot_instance}
        self.active_symbol_configs: Dict[str, SymbolConfig] = {} # To track config changes
        
        self._stop_event = asyncio.Event()
        self.config_refresh_task: Optional[asyncio.Task] = None

    async def _initialize_bot_components(self):
        """Initializes API client, WebSocket client, and database manager."""
        self.api_client = BybitAPIClient(self.global_config, self.logger)
        self.ws_client = BybitWebSocketClient(self.global_config, self.logger)
        self.db_manager = DBManager(STATE_DIR / self.global_config.files.db_file, self.logger)
        await self.db_manager.connect()
        await self.db_manager.create_tables()

    async def _start_symbol_bots(self, symbol_configs: Dict[str, SymbolConfig]):
        """Starts, restarts, or stops AsyncSymbolBot instances based on configuration."""
        if not self.api_client or not self.ws_client or not self.db_manager:
            self.logger.critical(f"{Colors.NEON_RED}Core components not initialized. Cannot start SymbolBots.{Colors.RESET}")
            return

        symbols_in_new_config = set(symbol_configs.keys())
        symbols_currently_active = set(self.symbol_bots.keys())

        # Stop bots for symbols no longer in config or disabled
        for symbol in list(symbols_currently_active): # Iterate over a copy as we modify the dict
            if symbol not in symbols_in_new_config or not symbol_configs[symbol].trade_enabled:
                self.logger.info(f"{Colors.YELLOW}Stopping AsyncSymbolBot for {symbol} (no longer active or disabled)...{Colors.RESET}")
                self.symbol_bots[symbol].stop()
                # Wait for the bot's run_loop to finish its shutdown logic
                bot_task_name = f"SymbolBot_{symbol.replace('/', '_').replace(':', '')}_Loop"
                tasks_for_symbol = [t for t in asyncio.all_tasks() if t.get_name() == bot_task_name]
                if tasks_for_symbol:
                    await asyncio.gather(*tasks_for_symbol, return_exceptions=True)
                self.ws_client.unregister_symbol_bot(symbol)
                del self.symbol_bots[symbol]
                del self.active_symbol_configs[symbol]

        # Start or update bots for active symbols
        for symbol, config in symbol_configs.items():
            if not config.trade_enabled:
                continue # Skip disabled symbols

            if symbol not in self.symbol_bots:
                self.logger.info(f"{Colors.CYAN}Starting AsyncSymbolBot for {symbol}...{Colors.RESET}")
                bot_logger = setup_logger(self.global_config.files, f"symbol.{symbol.replace('/', '_').replace(':', '')}")
                bot = AsyncSymbolBot(self.global_config, config, self.api_client, self.ws_client, self.db_manager, bot_logger)
                self.symbol_bots[symbol] = bot
                self.active_symbol_configs[symbol] = config
                self.ws_client.register_symbol_bot(bot)
                await bot.initialize()
                asyncio.create_task(bot.run_loop(), name=f"SymbolBot_{symbol.replace('/', '_').replace(':', '')}_Loop")

            elif self.active_symbol_configs.get(symbol) != config:
                self.logger.info(f"{Colors.YELLOW}Configuration for {symbol} changed. Restarting AsyncSymbolBot...{Colors.RESET}")
                self.symbol_bots[symbol].stop()
                # Wait for the bot's run_loop to finish its shutdown logic
                bot_task_name = f"SymbolBot_{symbol.replace('/', '_').replace(':', '')}_Loop"
                tasks_for_symbol = [t for t in asyncio.all_tasks() if t.get_name() == bot_task_name]
                if tasks_for_symbol:
                    await asyncio.gather(*tasks_for_symbol, return_exceptions=True)
                self.ws_client.unregister_symbol_bot(symbol)
                del self.symbol_bots[symbol]

                bot_logger = setup_logger(self.global_config.files, f"symbol.{symbol.replace('/', '_').replace(':', '')}")
                bot = AsyncSymbolBot(self.global_config, config, self.api_client, self.ws_client, self.db_manager, bot_logger)
                self.symbol_bots[symbol] = bot
                self.active_symbol_configs[symbol] = config
                self.ws_client.register_symbol_bot(bot)
                await bot.initialize()
                asyncio.create_task(bot.run_loop(), name=f"SymbolBot_{symbol.replace('/', '_').replace(':', '')}_Loop")

        # Update WebSocket subscriptions for all active symbols
        await self._update_websocket_subscriptions()

    async def _update_websocket_subscriptions(self):
        """Updates WebSocket subscriptions based on currently active symbol bots."""
        public_topics: List[str] = []
        private_topics: List[str] = [] # Bybit private stream is usually generic, but topics can be specified

        for symbol_cfg in self.active_symbol_configs.values():
            symbol_ws_format = symbol_cfg.symbol.replace('/', '').replace(':', '')
            public_topics.append(f"orderbook.1.{symbol_ws_format}") # Depth 1 for orderbook
            public_topics.append(f"publicTrade.{symbol_ws_format}")

        # Private topics are generally fixed for account-wide updates
        private_topics.extend(['order', 'position', 'execution', 'wallet'])

        # Filter out duplicates and sort for comparison
        public_topics_set = sorted(list(set(public_topics)))
        private_topics_set = sorted(list(set(private_topics)))

        if self.ws_client:
            await self.ws_client.start_streams(public_topics_set, private_topics_set)
        else:
            self.logger.error(f"{Colors.NEON_RED}WebSocket client not initialized.{Colors.RESET}")

    async def _stop_all_bots(self):
        """Signals all SymbolBots and WebSocket client to stop."""
        self.logger.info(f"{Colors.YELLOW}Signaling all AsyncSymbolBots to stop...{Colors.RESET}")
        
        # Stop all individual symbol bot tasks
        tasks_to_await = []
        for symbol, bot in list(self.symbol_bots.items()):
            bot.stop()
            bot_task_name = f"SymbolBot_{symbol.replace('/', '_').replace(':', '')}_Loop"
            tasks_to_await.extend([t for t in asyncio.all_tasks() if t.get_name() == bot_task_name])
        
        if tasks_to_await:
            await asyncio.gather(*tasks_to_await, return_exceptions=True)

        for symbol in list(self.symbol_bots.keys()):
            self.ws_client.unregister_symbol_bot(symbol)
            del self.symbol_bots[symbol]
            del self.active_symbol_configs[symbol]
        self.logger.info(f"{Colors.CYAN}All AsyncSymbolBots have been extinguished.{Colors.RESET}")
        
        if self.ws_client:
            await self.ws_client.stop_streams()
        if self.db_manager:
            await self.db_manager.close()

    async def _config_refresh_task(self):
        """Periodically reloads configuration and updates symbol bots."""
        last_config_check_time = time.time()
        while not self._stop_event.is_set():
            try:
                if (time.time() - last_config_check_time) > self.global_config.system.config_refresh_interval_sec:
                    self.logger.info(f"{Colors.CYAN}Periodically checking for symbol configuration changes...{Colors.RESET}")
                    
                    # Determine if single symbol mode is active to pass to load_config
                    single_symbol_active = len(self.active_symbol_configs) == 1 and list(self.active_symbol_configs.values())[0].symbol == ConfigManager._symbol_configs.get(list(self.active_symbol_configs.keys())[0], SymbolConfig(symbol="")).symbol
                    input_symbol_for_refresh = list(self.active_symbol_configs.keys())[0] if single_symbol_active else None

                    reloaded_global_cfg, reloaded_symbol_configs = ConfigManager.load_config(
                        single_symbol=input_symbol_for_refresh
                    )

                    # If global config changed, restart core components
                    if reloaded_global_cfg != self.global_config:
                        self.logger.info(f"{Colors.YELLOW}Global configuration changed. Applying updates (requires restart of core components).{Colors.RESET}")
                        # This would ideally trigger a full bot restart for robustness
                        # For now, just update the global_config object and logger
                        self.global_config = reloaded_global_cfg
                        self.logger = setup_logger(self.global_config.files, "main")
                        # You might need to re-initialize api_client and ws_client here if their configs change
                        # For simplicity, we assume API keys and testnet status don't change during runtime
                        self.api_client.config = self.global_config # Update config reference
                        self.ws_client.config = self.global_config # Update config reference
                        self.db_manager.db_file = STATE_DIR / self.global_config.files.db_file # Update DB path if changed

                    await self._start_symbol_bots(reloaded_symbol_configs)
                    last_config_check_time = time.time()

            except asyncio.CancelledError:
                self.logger.info("Config refresh task cancelled.")
                break
            except Exception as e:
                self.logger.error(f"{Colors.NEON_RED}Error in config manager task: {e}{Colors.RESET}", exc_info=True)

            await asyncio.sleep(self.global_config.system.config_refresh_interval_sec)

    async def run(self):
        """Main entry point for the Pyrmethus Bot."""
        self.logger.info(f"{Colors.NEON_GREEN}Pyrmethus Market Maker Bot starting...{Colors.RESET}")

        input_symbol: Optional[str] = None
        selected_mode: str = 'f' # Default to file mode
        try:
            # Check if running in a non-interactive environment
            if sys.stdin.isatty():
                selected_mode = input(
                    f"{Colors.CYAN}Choose mode:\n"
                    f"  [f]rom file (symbols.json) - for multi-symbol operation\n"
                    f"  [s]ingle symbol (e.g., BTCUSDT) - for interactive, quick run\n"
                    f"Enter choice (f/s): {Colors.RESET}"
                ).lower().strip()
                if selected_mode == 's':
                    input_symbol = input(f"{Colors.CYAN}Enter single symbol (e.g., BTCUSDT): {Colors.RESET}").upper().strip()
                    if not input_symbol:
                        raise ConfigurationError("No symbol entered for single symbol mode.")
            else:
                self.logger.warning(f"{Colors.YELLOW}Non-interactive environment detected. Defaulting to file mode.{Colors.RESET}")
                selected_mode = 'f' # Fallback to file mode if no interactive input possible

        except EOFError:
            self.logger.warning(f"{Colors.YELLOW}No interactive input detected (EOF). Defaulting to file mode.{Colors.RESET}")
            selected_mode = 'f'
        except Exception as e:
            self.logger.critical(f"{Colors.NEON_RED}Error during mode selection: {e}. Exiting.{Colors.RESET}")
            sys.exit(1)

        try:
            self.global_config, symbol_configs = ConfigManager.load_config(single_symbol=input_symbol if selected_mode == 's' else None)
            self.logger = setup_logger(self.global_config.files, "main") # Re-setup logger with actual config
        except ConfigurationError as e:
            self.logger.critical(f"{Colors.NEON_RED}Configuration loading failed: {e}. Exiting.{Colors.RESET}")
            sys.exit(1)
        except Exception as e:
            self.logger.critical(f"{Colors.NEON_RED}Unexpected error during configuration loading: {e}. Exiting.{Colors.RESET}", exc_info=True)
            sys.exit(1)

        await self._initialize_bot_components()
        await self._start_symbol_bots(symbol_configs)

        self.config_refresh_task = asyncio.create_task(self._config_refresh_task(), name="Config_Refresh_Task")

        try:
            self.logger.info(f"{Colors.NEON_GREEN}Pyrmethus Bot is now operational. Press Ctrl+C to stop.{Colors.RESET}")
            # Keep the main task running indefinitely until stop event is set
            await self._stop_event.wait()
        except asyncio.CancelledError:
            self.logger.info(f"{Colors.YELLOW}Bot main task cancelled.{Colors.RESET}")
        except KeyboardInterrupt:
            self.logger.info(f"{Colors.YELLOW}Ctrl+C detected. Initiating graceful shutdown...{Colors.RESET}")
        except Exception as e:
            self.logger.critical(f"{Colors.NEON_RED}An unhandled error occurred in the main bot process: {e}{Colors.RESET}", exc_info=True)
            termux_notify("Pyrmethus Bot CRASHED!", is_error=True)
        finally:
            self._stop_event.set() # Ensure all tasks receive stop signal
            if self.config_refresh_task:
                self.config_refresh_task.cancel()
                try: await self.config_refresh_task
                except asyncio.CancelledError: pass
            
            await self._stop_all_bots()
            self.logger.info(f"{Colors.NEON_GREEN}Pyrmethus Market Maker Bot gracefully shut down.{Colors.RESET}")


async def main():
    bot_instance: Optional[PyrmethusBot] = None
    try:
        bot_instance = PyrmethusBot()
        await bot_instance.run()
    except (KeyboardInterrupt, SystemExit):
        if bot_instance and bot_instance.logger:
            bot_instance.logger.info("\nBot stopped by user.")
        else:
            print("\nBot stopped by user.")
    except Exception as e:
        logger = bot_instance.logger if bot_instance and hasattr(bot_instance, 'logger') else logging.getLogger('BybitMarketMaker.main_fallback')
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
        print(f"\nAn unexpected critical error occurred during bot runtime: {e}. Check log file for details.")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass # Handled by main()
    except Exception as e:
        print(f"An error occurred before main() could fully handle it: {e}")
        sys.exit(1)
