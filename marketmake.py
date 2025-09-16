The provided code (`mmbot.md`) is already quite comprehensive and well-structured for a market-making bot. It includes many advanced features like dynamic spreads, inventory skew, state persistence, WebSocket integration, and robust error handling.

However, we can make several improvements and enhancements to make it more robust, efficient, and feature-rich, while maintaining its structure and compatibility.

Here's an analysis of the code and a plan for upgrades and enhancements:

### Analysis of Existing Code

**Strengths:**
*   **Modularity**: Well-separated concerns into classes (BybitWebSocket, SymbolBot, ConfigManager, Strategies).
*   **Precision**: Uses `Decimal` for financial calculations.
*   **Configuration**: Uses Pydantic for robust configuration management, including loading from JSON.
*   **Error Handling**: Implements retry logic (`@retry_api_call`) and handles various exceptions.
*   **WebSocket**: Integrates real-time data via WebSockets.
*   **State Persistence**: Saves state to disk.
*   **Termux Integration**: Includes notifications for mobile alerts.
*   **Colorized Output**: Uses `colorama` for better readability.
*   **Strategy Pattern**: Designed to allow different strategies.

**Potential Areas for Improvement/Enhancement:**
1.  **Configuration Loading**: While Pydantic is used, the loading logic could be more flexible (e.g., command-line arguments, multiple config files).
2.  **Strategy Implementation**: The `MarketMakerStrategy` is a placeholder; a more concrete example or a clearer interface for custom strategies would be beneficial.
3.  **Order Management**:
    *   More granular control over order types (e.g., TWAP, IOC, FOK).
    *   Better handling of partial fills and order cancellations.
    *   Stale order detection and cancellation logic could be more robust.
4.  **Risk Management**:
    *   Daily PnL limits are basic; could be more dynamic.
    *   More sophisticated inventory management (e.g., dynamic target inventory).
    *   Slippage control for placing orders.
5.  **Performance Metrics**: More detailed tracking of metrics like fill rate, spread capture, and PnL over time.
6.  **WebSocket Handling**: Reconnection logic could be more sophisticated, and handling multiple subscriptions more efficiently.
7.  **Code Structure**: While modular, some parts could be further refined for clarity or efficiency.
8.  **Error Handling**: More specific handling for different CCXT errors.
9.  **Dependencies**: Ensure all necessary dependencies are clearly listed.
10. **Security**: API keys are loaded from environment variables, which is good, but further hardening might be considered for production.
11. **Testing**: While not explicitly requested, a robust bot would benefit from unit tests.

## Upgrade and Enhancement Plan

I will focus on enhancing the existing code structure and adding features that improve its robustness, flexibility, and functionality, while keeping it as a single script as requested.

**Key Enhancements:**

1.  **Configuration Loading**:
    *   Allow loading global and symbol configurations from a single JSON file specified by an environment variable or command-line argument.
    *   Add more default values and validation for better usability.
2.  **Strategy Flexibility**:
    *   Refine the `MarketMakerStrategy` to be more concrete or provide a clearer abstract base for custom strategies.
    *   Integrate a simple, runnable strategy example within the main script for demonstration.
3.  **Order Management Enhancements**:
    *   Implement more robust handling of partial fills (e.g., cancel remaining quantity if below a threshold).
    *   Add logic for automatically cancelling stale orders based on age.
    *   Improve the `place_batch_orders` to handle potential errors more gracefully.
4.  **Risk Management Enhancements**:
    *   Introduce `min_order_value_usd` and `max_capital_allocation_per_order_pct` to control order sizing more precisely.
    *   Add `market_data_stale_timeout_seconds` to pause trading if WebSocket data is too old.
    *   Refine daily PnL limits to be more dynamic or based on starting balance.
5.  **Performance Metrics**:
    *   Add basic tracking for fill rate and spread capture within `SymbolBot`.
    *   Implement state persistence for these metrics.
6.  **WebSocket Improvements**:
    *   Ensure robust reconnection logic for all WebSocket streams.
    *   Add handling for specific Bybit WebSocket error codes if known.
7.  **Error Handling Refinements**:
    *   Add more specific CCXT error handling (e.g., for `BadRequest` errors that might indicate configuration issues).
8.  **Code Clarity and Structure**:
    *   Add type hints where missing.
    *   Ensure consistent formatting and docstrings.
    *   Organize imports.
    *   Add constants for magic numbers where appropriate.
9.  **Dependencies**: Explicitly mention `python-dotenv`, `ccxt`, `pandas`, `requests`, `websocket-client`, `pydantic`, `colorama` in the initial comments.

---

**Plan:**
I will consolidate the provided code into a single script. I will ensure all imports are at the top, followed by configuration, then classes, and finally the main execution block. I will integrate the suggested enhancements as I go.

**No external search is needed for this task as all the code is provided.**

Let's start by restructuring and enhancing the code from `mmbot.md`.

```python
# --- Imports ---
import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
import threading
import time
import signal  # Import the signal module
from datetime import datetime, timezone
from decimal import Decimal, getcontext, ROUND_DOWN, ROUND_UP, InvalidOperation
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field

# --- External Libraries ---
try:
    import ccxt  # Using synchronous CCXT for simplicity with threading
    import pandas as pd
    import requests
    import websocket
    from colorama import Fore, Style, init
    from pydantic import (
        BaseModel,
        ConfigDict,
        Field,
        NonNegativeFloat,
        NonNegativeInt,
        PositiveFloat,
        ValidationError,
    )
    EXTERNAL_LIBS_AVAILABLE = True
except ImportError as e:
    print(f"{Fore.RED}Error: Missing required library: {e}. Please install it using pip.{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Install all dependencies with: pip install ccxt pandas requests websocket-client pydantic colorama python-dotenv{Style.RESET_ALL}")
    EXTERNAL_LIBS_AVAILABLE = False
    # Define dummy classes/functions if libraries are missing to allow script to load without crashing immediately
    class DummyModel: pass
    class BaseModel(DummyModel): pass
    class ConfigDict(dict): pass
    class Field(DummyModel): pass
    class ValidationError(Exception): pass
    class Decimal: pass
    class ccxt: pass
    class pd: pass
    class requests: pass
    class websocket: pass
    class Fore:
        CYAN = MAGENTA = YELLOW = NEON_GREEN = NEON_BLUE = NEON_RED = NEON_ORANGE = RESET = ""
    class RotatingFileHandler: pass
    class subprocess: pass
    class threading: pass
    class time: pass
    class signal: pass
    class datetime: pass
    class timezone: pass
    class Path: pass
    class Optional: pass
    class Callable: pass
    class Dict: pass
    class List: pass
    class Tuple: pass
    class Union: pass
    class Any: pass
    class Callable: pass
    class field: pass
    class dataclass: pass
    class sys: pass
    class os: pass
    class hashlib: pass
    class hmac: pass
    class json: pass
    class logging: pass
    class sys: pass
    class subprocess: pass
    class threading: pass
    class time: pass
    class datetime: pass
    class timezone: pass
    class Decimal: pass
    class getcontext: pass
    class ROUND_DOWN: pass
    class ROUND_UP: pass
    class InvalidOperation: pass
    class wraps: pass
    class RotatingFileHandler: pass
    class Path: pass
    class Optional: pass
    class Callable: pass
    class Dict: pass
    class List: pass
    class Tuple: pass
    class Union: pass
    class Any: pass
    class Callable: pass
    class field: pass
    class dataclass: pass
    class logging: pass
    class sys: pass
    class subprocess: pass
    class websocket: pass
    class requests: pass
    class hashlib: pass
    class hmac: pass
    class json: pass
    class time: pass
    class datetime: pass
    class timezone: pass


# --- Initialize the terminal's chromatic essence ---
init(autoreset=True)

# --- Weaving in Environment Secrets ---
try:
    from dotenv import load_dotenv
    load_dotenv()
    print(f"{Fore.CYAN}# Secrets from the .env scroll have been channeled.{Style.RESET_ALL}")
except ImportError:
    print(f"{Fore.YELLOW}Warning: 'python-1dotenv' not found. Install with: pip install python-dotenv{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Environment variables will not be loaded from .env file.{Style.RESET_ALL}")

# --- Global Constants and Configuration ---
getcontext().prec = 38  # High precision for all magical calculations

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

# API Credentials from the environment
BYBIT_API_KEY: Optional[str] = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET: Optional[str] = os.getenv("BYBIT_API_SECRET")

# --- Termux-Aware Paths and Directories ---
BASE_DIR = Path(os.getenv("HOME", "."))
LOG_DIR: Path = BASE_DIR / "bot_logs"
STATE_DIR: Path = BASE_DIR / ".bot_state"
LOG_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Bybit V5 Exchange Configuration for CCXT
EXCHANGE_CONFIG = {
    "id": "bybit",
    "apiKey": BYBIT_API_KEY,
    "secret": BYBIT_API_SECRET,
    "enableRateLimit": True,
    "options": {"defaultType": "linear", "verbose": False, "adjustForTimeDifference": True, "v5": True},
}

# Bot Configuration Constants
API_RETRY_ATTEMPTS = 5
RETRY_BACKOFF_FACTOR = 0.5
WS_RECONNECT_INTERVAL = 5
SYMBOL_INFO_REFRESH_INTERVAL = 24 * 60 * 60
STATUS_UPDATE_INTERVAL = 60
MAIN_LOOP_SLEEP_INTERVAL = 5
DECIMAL_ZERO = Decimal("0")
MIN_TRADE_PNL_PERCENT = Decimal("-0.0005") # Don't open new trades if current position is worse than -0.05% PnL

# --- Pydantic Models for Configuration and State ---
class JsonDecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle Decimal objects."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)

def json_loads_decimal(s: str) -> Any:
    """Custom JSON decoder to parse floats/ints as Decimal."""
    # Handle potential errors during parsing, e.g., empty strings or invalid numbers
    try:
        return json.loads(s, parse_float=Decimal, parse_int=Decimal)
    except (json.JSONDecodeError, InvalidOperation) as e:
        # Log the error and return a default or raise a more specific error
        main_logger.error(f"Error decoding JSON with Decimal: {e} for input: {s[:100]}...")
        raise ValueError(f"Invalid JSON or Decimal format: {e}") from e

class OrderLayer(BaseModel):
    """Defines a single layer for multi-layered order placement."""
    spread_offset: NonNegativeFloat = 0.0
    quantity_multiplier: PositiveFloat = 1.0
    cancel_threshold_pct: PositiveFloat = 0.01 # Percentage price movement from placement price to trigger cancellation

class SymbolConfig(BaseModel):
    """Configuration for a single trading symbol."""
    symbol: str
    trade_enabled: bool = True
    base_spread: PositiveFloat = 0.001
    order_amount: PositiveFloat = 0.001
    leverage: PositiveFloat = 10.0
    order_refresh_time: NonNegativeInt = 5
    max_spread: PositiveFloat = 0.005 # Max allowed spread before pausing quotes
    inventory_limit: PositiveFloat = 0.01 # Max inventory (absolute value) before aggressive rebalancing
    dynamic_spread: DynamicSpreadConfig = Field(default_factory=DynamicSpreadConfig)
    inventory_skew: InventorySkewConfig = Field(default_factory=InventorySkewConfig)
    momentum_window: NonNegativeInt = 10 # Number of recent trades/prices to check for momentum
    take_profit_percentage: PositiveFloat = 0.002
    stop_loss_percentage: PositiveFloat = 0.001
    inventory_sizing_factor: NonNegativeFloat = 0.5 # Factor to adjust order size based on inventory (0 to 1)
    min_liquidity_depth: PositiveFloat = 1000.0 # Minimum volume at best bid/ask to consider liquid
    depth_multiplier: PositiveFloat = 2.0 # Multiplier for base_qty to determine required cumulative depth
    imbalance_threshold: NonNegativeFloat = 0.3 # Imbalance threshold for dynamic spread adjustment (0 to 1)
    slippage_tolerance_pct: NonNegativeFloat = 0.002 # Max slippage for market orders (0.2%)
    funding_rate_threshold: NonNegativeFloat = 0.0005 # Avoid holding if funding rate > 0.05%
    backtest_mode: bool = False
    max_symbols_termux: NonNegativeInt = 5 # Limit active symbols for Termux resource management
    trailing_stop_pct: NonNegativeFloat = 0.005 # 0.5% trailing stop distance (for future use/custom conditional orders)
    min_recent_trade_volume: NonNegativeFloat = 0.0 # Minimum recent trade volume (notional value) to enable trading
    trading_hours_start: Optional[str] = None # Start of active trading hours (HH:MM) in UTC
    trading_hours_end: Optional[str] = None # End of active trading hours (HH:MM) in UTC
    order_layers: List[OrderLayer] = Field(default_factory=lambda: [OrderLayer()])
    min_order_value_usd: PositiveFloat = Field(default=10.0, description="Minimum order value in USD.")
    max_capital_allocation_per_order_pct: PositiveFloat = Field(default=0.01, description="Max percentage of available capital to allocate per single order.")
    atr_qty_multiplier: PositiveFloat = Field(default=0.1, description="Multiplier for ATR's impact on order quantity.")
    enable_auto_sl_tp: bool = Field(default=False, description="Enable automatic Stop-Loss and Take-Profit on market-making orders.")
    take_profit_target_pct: PositiveFloat = Field(default=0.005, description="Take-Profit percentage from entry price (e.g., 0.005 for 0.5%).")
    stop_loss_trigger_pct: PositiveFloat = Field(default=0.005, description="Stop-Loss percentage from entry price (e.g., 0.005 for 0.5%).")
    use_batch_orders_for_refresh: bool = True # Use batch order API for cancelling/placing main limit orders
    recent_fill_rate_window: NonNegativeInt = 60 # Window for calculating recent fill rate (minutes)
    cancel_partial_fill_threshold_pct: NonNegativeFloat = 0.15 # If a partial fill is less than this %, cancel remaining
    stale_order_max_age_seconds: NonNegativeInt = 300 # Automatically cancels any limit order that has been open for longer than this duration
    momentum_trend_threshold: NonNegativeFloat = 0.0001 # Price change % to indicate strong trend for pausing
    max_capital_at_risk_usd: NonNegativeFloat = 0.0 # Max notional value to commit for this symbol. Set to 0 for unlimited.
    market_data_stale_timeout_seconds: NonNegativeInt = 30 # Timeout for considering market data stale

    # Fields populated at runtime from exchange info
    min_qty: Optional[Decimal] = None
    max_qty: Optional[Decimal] = None
    qty_precision: Optional[int] = None
    price_precision: Optional[int] = None
    min_notional: Optional[Decimal] = None

    model_config = ConfigDict(json_dumps=lambda v: json.dumps(v, cls=JsonDecimalEncoder), json_loads=json_loads_decimal, validate_assignment=True)

    def __eq__(self, other: Any) -> bool:
        """Enables comparison of SymbolConfig objects for dynamic updates."""
        if not isinstance(other, SymbolConfig):
            return NotImplemented
        # Compare dictionaries, excluding runtime-populated fields
        self_dict = self.model_dump(
            exclude={"min_qty", "max_qty", "qty_precision", "price_precision", "min_notional"}
        )
        other_dict = other.model_dump(
            exclude={"min_qty", "max_qty", "qty_precision", "price_precision", "min_notional"}
        )
        return self_dict == other_dict

    def __hash__(self) -> int:
        """Enables hashing of SymbolConfig objects for set operations."""
        return hash(
            json.dumps(
                self.model_dump(
                    exclude={
                        "min_qty",
                        "max_qty",
                        "qty_precision",
                        "price_precision",
                        "min_notional",
                    }
                ),
                sort_keys=True,
                cls=JsonDecimalEncoder,
            )
        )

class GlobalConfig(BaseModel):
    """Global configuration for the market maker bot."""
    category: str = "linear" # "linear" for perpetual, "spot" for spot trading
    api_max_retries: PositiveInt = 5
    api_retry_delay: PositiveInt = 1
    orderbook_depth_limit: PositiveInt = 100 # Number of levels to fetch for orderbook
    orderbook_analysis_levels: PositiveInt = 30 # Number of levels to analyze for depth
    imbalance_threshold: PositiveFloat = 0.25 # Threshold for orderbook imbalance
    depth_range_pct: PositiveFloat = 0.008 # Percentage range around mid-price to consider orderbook depth
    slippage_tolerance_pct: PositiveFloat = 0.003 # Max slippage for market orders
    min_profitable_spread_pct: PositiveFloat = 0.0005 # Minimum spread to ensure profitability
    funding_rate_threshold: PositiveFloat = 0.0004 # Funding rate threshold to avoid holding positions
    backtest_mode: bool = False
    max_symbols_termux: PositiveInt = 2 # Max concurrent symbols for Termux
    log_level: str = "INFO"
    log_file: str = "market_maker_live.log"
    state_file: str = "state.json"
    use_batch_orders_for_refresh: bool = True
    strategy: str = "MarketMakerStrategy" # Default strategy
    bb_width_threshold: PositiveFloat = 0.15 # For BollingerBandsStrategy
    min_liquidity_per_level: PositiveFloat = 0.001 # Minimum liquidity per level for order placement
    depth_multiplier_for_qty: PositiveFloat = 1.5 # Multiplier for quantity based on depth
    default_order_amount: PositiveFloat = 0.003
    default_leverage: PositiveInt = 10
    default_max_spread: PositiveFloat = 0.005
    default_skew_factor: PositiveFloat = 0.1
    default_atr_multiplier: PositiveFloat = 0.5
    symbol_config_file: str = "symbols.json" # Path to symbol config file
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    daily_pnl_stop_loss_pct: Optional[PositiveFloat] = Field(default=None, description="Percentage loss threshold for daily PnL (e.g., 0.05 for 5%).")
    daily_pnl_take_profit_pct: Optional[PositiveFloat] = Field(default=None, description="Percentage profit threshold for daily PnL (e.g., 0.10 for 10%).")
    
    model_config = ConfigDict(json_dumps=lambda v: json.dumps(v, cls=JsonDecimalEncoder), json_loads=json_loads_decimal, validate_assignment=True)

class ConfigManager:
    """Manages loading and validating global and symbol-specific configurations."""
    _global_config: Optional[GlobalConfig] = None
    _symbol_configs: List[SymbolConfig] = []

    @classmethod
    def load_config(cls) -> Tuple[GlobalConfig, List[SymbolConfig]]:
        if cls._global_config and cls._symbol_configs:
            return cls._global_config, cls._symbol_configs

        # Initialize GlobalConfig with environment variables or hardcoded defaults
        global_data = {
            "category": os.getenv("BYBIT_CATEGORY", "linear"),
            "api_max_retries": int(os.getenv("API_MAX_RETRIES", "5")),
            "api_retry_delay": int(os.getenv("API_RETRY_DELAY", "1")),
            "orderbook_depth_limit": int(os.getenv("ORDERBOOK_DEPTH_LIMIT", "100")),
            "orderbook_analysis_levels": int(os.getenv("ORDERBOOK_ANALYSIS_LEVELS", "30")),
            "imbalance_threshold": float(os.getenv("IMBALANCE_THRESHOLD", "0.25")),
            "depth_range_pct": float(os.getenv("DEPTH_RANGE_PCT", "0.008")),
            "slippage_tolerance_pct": float(os.getenv("SLIPPAGE_TOLERANCE_PCT", "0.003")),
            "min_profitable_spread_pct": float(os.getenv("MIN_PROFITABLE_SPREAD_PCT", "0.0005")),
            "funding_rate_threshold": float(os.getenv("FUNDING_RATE_THRESHOLD", "0.0004")),
            "backtest_mode": os.getenv("BACKTEST_MODE", "False").lower() == "true",
            "max_symbols_termux": int(os.getenv("MAX_SYMBOLS_TERMUX", "2")),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
            "log_file": os.getenv("LOG_FILE", "market_maker_live.log"),
            "state_file": os.getenv("STATE_FILE", "state.json"),
            "use_batch_orders_for_refresh": os.getenv("USE_BATCH_ORDERS_FOR_REFRESH", "True").lower() == "true",
            "strategy": os.getenv("TRADING_STRATEGY", "MarketMakerStrategy"),
            "bb_width_threshold": float(os.getenv("BB_WIDTH_THRESHOLD", "0.15")),
            "min_liquidity_per_level": float(os.getenv("MIN_LIQUIDITY_PER_LEVEL", "0.001")),
            "depth_multiplier_for_qty": float(os.getenv("DEPTH_MULTIPLIER_FOR_QTY", "1.5")),
            "default_order_amount": float(os.getenv("DEFAULT_ORDER_AMOUNT", "0.003")),
            "default_leverage": int(os.getenv("DEFAULT_LEVERAGE", "10")),
            "default_max_spread": float(os.getenv("DEFAULT_MAX_SPREAD", "0.005")),
            "default_skew_factor": float(os.getenv("DEFAULT_SKEW_FACTOR", "0.1")),
            "default_atr_multiplier": float(os.getenv("DEFAULT_ATR_MULTIPLIER", "0.5")),
            "symbol_config_file": os.getenv("SYMBOL_CONFIG_FILE", "symbols.json"),
            "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
            "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID"),
            "daily_pnl_stop_loss_pct": float(os.getenv("DAILY_PNL_STOP_LOSS_PCT")) if os.getenv("DAILY_PNL_STOP_LOSS_PCT") else None,
            "daily_pnl_take_profit_pct": float(os.getenv("DAILY_PNL_TAKE_PROFIT_PCT")) if os.getenv("DAILY_PNL_TAKE_PROFIT_PCT") else None,
        }

        try:
            cls._global_config = GlobalConfig(**global_data)
        except ValidationError as e:
            logging.critical(f"Global configuration validation error: {e}")
            sys.exit(1)

        # Load symbol configurations from file
        raw_symbol_configs = []
        try:
            symbol_config_path = Path(cls._global_config.symbol_config_file) # Use Path object
            with open(symbol_config_path, 'r') as f:
                raw_symbol_configs = json.load(f)
            if not isinstance(raw_symbol_configs, list):
                raise ValueError("Symbol configuration file must contain a JSON list.")
        except FileNotFoundError:
            logging.critical(f"Symbol configuration file '{cls._global_config.symbol_config_file}' not found. Please create it.")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logging.critical(f"Error decoding JSON from symbol configuration file '{cls._global_config.symbol_config_file}': {e}")
            sys.exit(1)
        except ValueError as e:
            logging.critical(f"Invalid format in symbol configuration file: {e}")
            sys.exit(1)
        except Exception as e:
            logging.critical(f"Unexpected error loading symbol config: {e}")
            sys.exit(1)

        cls._symbol_configs = []
        for s_cfg in raw_symbol_configs:
            try:
                # Merge with global defaults before validation
                # Ensure nested models are correctly represented if they come from .yaml or dict
                merged_config_data = {
                    "base_spread": cls._global_config.min_profitable_spread_pct * 2, # Example: default to 2x min profitable spread
                    "order_amount": cls._global_config.default_order_amount,
                    "leverage": cls._global_config.default_leverage,
                    "order_refresh_time": cls._global_config.api_retry_delay * 5, # Example: 5x API retry delay
                    "max_spread": cls._global_config.default_max_spread,
                    "inventory_limit": cls._global_config.default_order_amount * 10, # Example: 10x order amount
                    "min_profitable_spread_pct": cls._global_config.min_profitable_spread_pct,
                    "depth_range_pct": cls._global_config.depth_range_pct,
                    "slippage_tolerance_pct": cls._global_config.slippage_tolerance_pct,
                    "funding_rate_threshold": cls._global_config.funding_rate_threshold,
                    "max_symbols_termux": cls._global_config.max_symbols_termux,
                    "min_recent_trade_volume": 0.0,
                    "trading_hours_start": None,
                    "trading_hours_end": None,
                    "enable_auto_sl_tp": False, # Default to false unless specified in symbol config
                    "take_profit_target_pct": 0.005,
                    "stop_loss_trigger_pct": 0.005,
                    "use_batch_orders_for_refresh": cls._global_config.use_batch_orders_for_refresh,
                    "recent_fill_rate_window": 60,
                    "cancel_partial_fill_threshold_pct": 0.15,
                    "stale_order_max_age_seconds": 300,
                    "momentum_trend_threshold": 0.0001,
                    "max_capital_at_risk_usd": 0.0,
                    "market_data_stale_timeout_seconds": 30,

                    # Default nested configs if not provided in symbol config
                    "dynamic_spread": DynamicSpreadConfig(**s_cfg.get("dynamic_spread", {})) if isinstance(s_cfg.get("dynamic_spread"), dict) else s_cfg.get("dynamic_spread", DynamicSpreadConfig()),
                    "inventory_skew": InventorySkewConfig(**s_cfg.get("inventory_skew", {})) if isinstance(s_cfg.get("inventory_skew"), dict) else s_cfg.get("inventory_skew", InventorySkewConfig()),
                    "order_layers": [OrderLayer(**ol) if isinstance(ol, dict) else ol for ol in s_cfg.get("order_layers", [OrderLayer()])] if isinstance(s_cfg.get("order_layers"), list) else s_cfg.get("order_layers", [OrderLayer()]),

                    **s_cfg # Override with symbol-specific values
                }
                
                # Ensure nested models are Pydantic objects before passing to SymbolConfig
                if isinstance(merged_config_data.get("dynamic_spread"), dict):
                    merged_config_data["dynamic_spread"] = DynamicSpreadConfig(**merged_config_data["dynamic_spread"])
                if isinstance(merged_config_data.get("inventory_skew"), dict):
                    merged_config_data["inventory_skew"] = InventorySkewConfig(**merged_config_data["inventory_skew"])
                
                # Ensure order_layers is a list of OrderLayer objects
                if isinstance(merged_config_data.get("order_layers"), list):
                    merged_config_data["order_layers"] = [OrderLayer(**ol) if isinstance(ol, dict) else ol for ol in merged_config_data["order_layers"]]
                
                cls._symbol_configs.append(SymbolConfig(**merged_config_data))

            except ValidationError as e:
                logging.critical(f"Symbol configuration validation error for {s_cfg.get('symbol', 'N/A')}: {e}")
                sys.exit(1)
            except Exception as e:
                logging.critical(f"Unexpected error processing symbol config {s_cfg.get('symbol', 'N/A')}: {e}")
                sys.exit(1)

        return cls._global_config, cls._symbol_configs

# Load configs immediately upon module import
GLOBAL_CONFIG, SYMBOL_CONFIGS = ConfigManager.load_config()

# --- Utility Functions & Decorators ---
def setup_logger(name_suffix: str) -> logging.Logger:
    """
    Summons a logger to weave logs into the digital tapestry.
    Ensures loggers are configured once per name.
    """
    logger_name = f"market_maker_{name_suffix}"
    logger = logging.getLogger(logger_name)
    if logger.hasHandlers():
        return logger

    logger.setLevel(getattr(logging, GLOBAL_CONFIG.log_level.upper(), logging.INFO))
    log_file_path = LOG_DIR / GLOBAL_CONFIG.log_file

    # File handler for persistent logs
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Stream handler for console output with neon theme
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_formatter = logging.Formatter(
        f"{Colors.NEON_BLUE}%(asctime)s{Colors.RESET} - "
        f"{Colors.YELLOW}%(levelname)-8s{Colors.RESET} - "
        f"{Colors.MAGENTA}[%(name)s]{Colors.RESET} - %(message)s",
        datefmt="%H:%M:%S",
    )
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)

    logger.propagate = False  # Prevent logs from going to root logger
    return logger

# Global logger instance for main operations
main_logger = setup_logger("main")


def termux_notify(message: str, title: str = "Pyrmethus Bot", is_error: bool = False):
    """Channels notifications through the Termux API with neon colors."""
    bg_color = "#000000"  # Black background
    if is_error:
        text_color = "#FF0000"  # Red for errors
        vibrate_duration = "1000"
    else:
        text_color = "#00FFFF"  # Cyan for success/info
        vibrate_duration = "200"  # Shorter vibrate for info
    try:
        subprocess.run(
            [
                "termux-toast",
                "-g",
                "middle",
                "-c",
                text_color,
                "-b",
                bg_color,
                f"{title}: {message}",
            ],
            check=False,  # Don't raise CalledProcessError if termux-api not found
            timeout=2,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["termux-vibrate", "-d", vibrate_duration, "-f"],
            check=False,
            timeout=2,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError) as e:
        # Termux API not available or timed out, fail silently.
        # Log this silently to avoid spamming if termux-api is just not installed
        main_logger.debug(f"Termux notification failed: {e}")
    except Exception as e:
        main_logger.warning(f"Unexpected error with Termux notification: {e}")


def initialize_exchange(logger: logging.Logger) -> Optional[ccxt.Exchange]:
    """Conjures the Bybit V5 exchange instance."""
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        logger.critical(
            f"{Colors.NEON_RED}API Key and/or Secret not found in .env. "
            f"Cannot initialize exchange.{Colors.RESET}"
        )
        termux_notify("API Keys Missing!", title="Error", is_error=True)
        return None
    try:
        exchange = getattr(ccxt, EXCHANGE_CONFIG["id"])(EXCHANGE_CONFIG)
        exchange.set_sandbox_mode(False)  # Ensure not in sandbox
        logger.info(
            f"{Colors.CYAN}Exchange '{EXCHANGE_CONFIG['id']}' summoned in live mode with V5 API.{Colors.RESET}"
        )
        return exchange
    except Exception as e:
        logger.critical(f"{Colors.NEON_RED}Failed to summon exchange: {e}{Colors.RESET}", exc_info=True)
        termux_notify(f"Exchange init failed: {e}", title="Error", is_error=True)
        return None


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """Calculates the Average True Range, a measure of market volatility."""
    tr = pd.DataFrame()
    tr["h_l"] = high - low
    tr["h_pc"] = (high - close.shift(1)).abs()
    tr["l_pc"] = (low - close.shift(1)).abs()
    tr["tr"] = tr[["h_l", "h_pc", "l_pc"]].max(axis=1)
    return tr["tr"].rolling(window=length).mean()


def retry_api_call(
    attempts: int = API_RETRY_ATTEMPTS,
    backoff_factor: float = RETRY_BACKOFF_FACTOR,
    fatal_exceptions: Tuple[type, ...] = (ccxt.AuthenticationError, ccxt.ArgumentsRequired, ccxt.ExchangeError),
):
    """A spell to retry API calls with exponential backoff."""

    def decorator(func: Callable[..., Any]):
        @wraps(func)
        def wrapper(self, *args: Any, **kwargs: Any) -> Any:
            # Use the instance's logger if available, otherwise a generic one
            logger = self.logger if hasattr(self, "logger") else main_logger
            for i in range(attempts):
                try:
                    return func(self, *args, **kwargs)
                except fatal_exceptions as e:
                    logger.critical(
                        f"{Colors.NEON_RED}Fatal API error in {func.__name__}: {e}. No retry.{Colors.RESET}",
                        exc_info=True,
                    )
                    termux_notify(f"Fatal API Error: {str(e)[:50]}...", is_error=True)
                    raise  # Re-raise fatal errors
                except ccxt.BadRequest as e:
                    # Specific Bybit errors that might not be actual issues or require user intervention
                    if "110043" in str(e):  # Leverage not modified (often not an error)
                        logger.warning(
                            f"BadRequest (Leverage unchanged) in {func.__name__}: {e}"
                        )
                        return None  # Or return True if this is acceptable as "done"
                    elif "position mode" in str(e).lower() or "margin mode" in str(e).lower():
                        logger.error(
                            f"BadRequest: Position/Margin mode error in {func.__name__}: {e}. "
                            f"This often requires manual intervention or configuration review."
                        )
                        termux_notify(f"API Error: {str(e)[:50]}...", is_error=True)
                        raise  # Re-raise for configuration errors that need attention
                    logger.error(f"BadRequest in {func.__name__}: {e}")
                    termux_notify(f"API Error: {str(e)[:50]}...", is_error=True)
                    raise  # Re-raise for specific bad requests that shouldn't be retried
                except (
                    ccxt.NetworkError,
                    ccxt.DDoSProtection,
                    ccxt.ExchangeNotAvailable,
                    requests.exceptions.ConnectionError,
                    websocket._exceptions.WebSocketConnectionClosedException,
                ) as e:
                    logger.warning(
                        f"Network/Connection error in {func.__name__} (attempt {i+1}/{attempts}): {e}"
                    )
                    if i == attempts - 1:
                        logger.error(
                            f"Failed {func.__name__} after {attempts} attempts. "
                            f"Check internet/API status."
                        )
                        termux_notify(f"API Failed: {func.__name__}", is_error=True)
                        return None
                except Exception as e:
                    logger.error(
                        f"Unexpected error in {func.__name__}: {e}", exc_info=True
                    )
                    if i == attempts - 1:
                        termux_notify(f"Unexpected Error: {func.__name__}", is_error=True)
                        return None
                sleep_time = backoff_factor * (2**i)
                logger.info(f"Retrying {func.__name__} in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
            return None

        return wrapper

    return decorator


# --- Bybit V5 WebSocket Client ---
class BybitWebSocket:
    """A mystical WebSocket conduit to Bybit's V5 streams."""

    def __init__(
        self, api_key: Optional[str], api_secret: Optional[str], testnet: bool, logger: logging.Logger
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.logger = logger
        self.testnet = testnet

        self.public_url = (
            "wss://stream.bybit.com/v5/public/linear"
            if not testnet
            else "wss://stream-testnet.bybit.com/v5/public/linear"
        )
        self.private_url = (
            "wss://stream.bybit.com/v5/private"
            if not testnet
            else "wss://stream-testnet.bybit.com/v5/private"
        )
        # Trading WebSocket for order operations
        self.trade_url = (
            "wss://stream.bybit.com/v5/trade"
            if not testnet
            else "wss://stream-testnet.bybit.com/v5/trade"
        )

        self.ws_public: Optional[websocket.WebSocketApp] = None
        self.ws_private: Optional[websocket.WebSocketApp] = None
        self.ws_trade: Optional[websocket.WebSocketApp] = None

        self.public_subscriptions: List[str] = []
        self.private_subscriptions: List[str] = []
        self.trade_subscriptions: List[str] = [] # Not directly used for subscriptions in this structure, but for connection management

        # Shared data structures for SymbolBots, protected by self.lock
        self.order_books: Dict[str, Dict[str, List[List[Decimal]]]] = {}  # Store prices as Decimal
        self.recent_trades: Dict[str, List[Tuple[Decimal, Decimal, str]]] = {}  # Storing (price, qty, side)

        self._stop_event = threading.Event()  # Event to signal threads to stop
        self.public_thread: Optional[threading.Thread] = None
        self.private_thread: Optional[threading.Thread] = None
        self.trade_thread: Optional[threading.Thread] = None

        # List of active SymbolBot instances to route updates
        self.symbol_bots: List["SymbolBot"] = []

        # Lock for protecting shared data like symbol_bots, order_books, recent_trades
        self.lock = threading.Lock()
        self.last_orderbook_update_time: Dict[str, float] = {}
        self.last_trades_update_time: Dict[str, float] = {}

    def _generate_auth_params(self) -> Dict[str, Any]:
        """Generates authentication parameters for private WebSocket."""
        expires = int((time.time() + 60) * 1000)  # Valid for 60 seconds
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            f"GET/realtime{expires}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {"op": "auth", "args": [self.api_key, expires, signature]}

    def _on_message(self, ws: websocket.WebSocketApp, message: str, is_private: bool, is_trade: bool = False):
        """Generic message handler for all WebSocket streams."""
        try:
            data = json_loads_decimal(message)
            if "topic" in data:
                with self.lock: # Protect shared data access
                    if is_trade: self._process_trade_message(data)
                    elif is_private: self._process_private_message(data)
                    else: self._process_public_message(data)
            elif "ping" in data:
                ws.send(json.dumps({"op": "pong"})) # Respond to ping with pong
            elif "pong" in data:
                self.logger.debug("# WS Pong received.")
        except InvalidOperation as e:
            self.logger.error(f"{Colors.NEON_RED}# WS {'Private' if is_private else 'Public'}: Decimal conversion error: {e} in message: {message[:100]}...{Colors.RESET}", exc_info=True)
        except json.JSONDecodeError as e:
            self.logger.error(f"{Colors.NEON_RED}# WS {'Private' if is_private else 'Public'}: JSON decoding error: {e} in message: {message[:100]}...{Colors.RESET}", exc_info=True)
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# WS {'Private' if is_private else 'Public'}: Unexpected error processing message: {e}{Colors.RESET}", exc_info=True)

    def _normalize_symbol_ws(self, bybit_symbol_ws: str) -> str:
        """
        Normalizes Bybit's WebSocket symbol format (e.g., BTCUSDT)
        to CCXT format (e.g., BTC/USDT:USDT).
        """
        # Bybit V5 public topics often use the format 'SYMBOL' like 'BTCUSDT'.
        # For WS, we need to match Bybit's format.
        
        # Simple normalization for common formats
        if len(bybit_symbol_ws) > 4 and bybit_symbol_ws[-4:].isupper(): # e.g., BTCUSDT
             base = bybit_symbol_ws[:-4]
             quote = bybit_symbol_ws[-4:]
             return f"{base}/{quote}:{quote}" # CCXT format
        elif len(bybit_symbol_ws) > 3 and bybit_symbol_ws[-3:].isupper(): # e.g. BTCUSD (inverse)
            # For inverse, Bybit's WS might use BTCUSD. CCXT might normalize this differently.
            # For WS routing, we usually need the format Bybit sends.
            return bybit_symbol_ws
        
        # Fallback for unexpected formats or if no normalization is needed for the specific topic
        return bybit_symbol_ws

    def _process_public_message(self, data: Dict[str, Any]):
        """Processes messages from public WebSocket streams."""
        topic = data["topic"]
        if topic.startswith("orderbook."):
            # Example topic: "orderbook.50.BTCUSDT" (depth 50, symbol)
            parts = topic.split(".")
            if len(parts) >= 3:
                symbol_id_ws = parts[2] # Extract symbol from topic
                self._update_order_book(symbol_id_ws, data["data"])
            else:
                self.logger.warning(f"WS Public: Unrecognized orderbook topic format: {topic}")
        elif topic.startswith("publicTrade."):
            # Example topic: "publicTrade.BTCUSDT"
            parts = topic.split(".")
            if len(parts) >= 2:
                symbol_id_ws = parts[1] # Extract symbol from topic
                for trade_data in data["data"]:
                    price = Decimal(str(trade_data.get("p", "0")))
                    qty = Decimal(str(trade_data.get("v", "0")))
                    side = trade_data.get("S", "unknown") # 'Buy' or 'Sell'
                    self.recent_trades.setdefault(symbol_id_ws, []).append((price, qty, side))
                    # Keep a reasonable buffer (e.g., 200 trades) for momentum/volume
                    if len(self.recent_trades[symbol_id_ws]) > 200:
                        self.recent_trades[symbol_id_ws].pop(0)
                    self.last_trades_update_time[symbol_id_ws] = time.time()
            else:
                self.logger.warning(f"WS Public: Unrecognized publicTrade topic format: {topic}")

    def _process_trade_message(self, data: Dict[str, Any]):
        """Processes messages from Trade WebSocket streams."""
        # The 'Trade' WebSocket stream might contain different data structures than publicTrade.
        # For example, it might include order fills directly.
        # This needs to be mapped to SymbolBot's specific update handlers.
        # For now, let's assume it might include order status updates or execution reports.
        
        # Example: Process execution reports from the trade stream (if applicable)
        if data.get("topic") == "execution" and data.get("data"):
            for exec_data in data["data"]:
                exec_type = exec_data.get("execType")
                if exec_type in ["Trade", "AdlTrade", "BustTrade"]:
                    exec_side = exec_data.get("side").lower()
                    exec_qty = Decimal(str(exec_data.get("execQty", "0")))
                    exec_price = Decimal(str(exec_data.get("execPrice", "0")))
                    exec_fee = Decimal(str(exec_data.get("execFee", "0")))
                    exec_time = int(exec_data.get("execTime", time.time() * 1000))
                    exec_id = exec_data.get("execId")
                    closed_pnl = Decimal(str(exec_data.get("closedPnl", "0")))

                    symbol_ws = exec_data.get("symbol")
                    if symbol_ws:
                        normalized_symbol = self._normalize_symbol_ws(symbol_ws)
                        for bot in self.symbol_bots: # Iterate through registered SymbolBot instances
                            if bot.symbol == normalized_symbol:
                                # This execution might be related to closing a position,
                                # which affects PnL. It should be handled by the bot.
                                bot._handle_execution_update(exec_data)
                                break

        elif data.get("topic") == "order":
            for order_data in data.get("data", []):
                symbol_ws = order_data.get("symbol")
                if symbol_ws:
                    normalized_symbol = self._normalize_symbol_ws(symbol_ws)
                    for bot in self.symbol_bots:
                        if bot.symbol == normalized_symbol:
                            bot._handle_order_update(order_data)
                            break
        elif data.get("topic") == "position":
            for pos_data in data.get("data", []):
                symbol_ws = pos_data.get("symbol")
                if symbol_ws:
                    normalized_symbol = self._normalize_symbol_ws(symbol_ws)
                    for bot in self.symbol_bots:
                        if bot.symbol == normalized_symbol:
                            bot._handle_position_update(pos_data)
                            break

    def _process_private_message(self, data: Dict[str, Any]):
        """Processes messages from private WebSocket streams and routes to SymbolBots."""
        topic = data["topic"]
        if topic in ["order", "execution", "position", "wallet"]: # Add wallet for balance updates if needed
            for item_data in data["data"]:
                symbol_ws = item_data.get("symbol")
                if symbol_ws:
                    normalized_symbol = self._normalize_symbol_ws(symbol_ws)
                    for bot in self.symbol_bots: # Iterate through registered SymbolBot instances
                        if bot.symbol == normalized_symbol:
                            if topic == "order": bot._handle_order_update(item_data)
                            elif topic == "position": bot._handle_position_update(item_data)
                            elif topic == "execution" and item_data.get("execType") in ["Trade", "AdlTrade", "BustTrade"]: bot._handle_execution_update(item_data)
                            elif topic == "wallet": pass # Handle wallet updates if needed by bots
                            break
                    else: # If no bot found for the symbol
                        self.logger.debug(f"Received {topic} update for unmanaged symbol: {normalized_symbol}")

    def _update_order_book(self, symbol_id_ws: str, data: Dict[str, Any]):
        """Updates the local order book cache."""
        if "b" in data and "a" in data:
            # Store prices and quantities as Decimal for accuracy
            self.order_books[symbol_id_ws] = {
                "b": [[Decimal(str(item[0])), Decimal(str(item[1]))] for item in data["b"]], # Bybit sends price, qty as strings/floats
                "a": [[Decimal(str(item[0])), Decimal(str(item[1]))] for item in data["a"]],
            }
            self.last_orderbook_update_time[symbol_id_ws] = time.time()

    def get_order_book_snapshot(self, symbol_id_ws: str) -> Optional[Dict[str, List[List[Decimal]]]]:
        """Retrieves a snapshot of the order book for a symbol."""
        with self.lock:  # Protect access to order_books
            return self.order_books.get(symbol_id_ws)

    def get_recent_trades_for_momentum(
        self, symbol_id_ws: str, limit: int = 100
    ) -> List[Tuple[Decimal, Decimal, str]]:
        """Retrieves recent trades for momentum/volume calculation."""
        with self.lock:  # Protect access to recent_trades
            return self.recent_trades.get(symbol_id_ws, [])[-limit:]

    def _on_error(self, ws: websocket.WebSocketApp, error: Any):
        """Callback for WebSocket errors."""
        self.logger.error(f"{Colors.NEON_RED}# WS Error: {error}{Colors.RESET}")

    def _on_close(self, ws: websocket.WebSocketApp, code: int, msg: str):
        """Callback for WebSocket close events."""
        if not self._stop_event.is_set(): # Only log as warning if not intentionally stopped
            self.logger.warning(f"{Colors.YELLOW}# WS Closed: {code} - {msg}. Reconnecting...{Colors.RESET}")
        else:
            self.logger.info(f"{Colors.CYAN}# WS Closed intentionally: {code} - {msg}{Colors.RESET}")

    def _on_open(self, ws: websocket.WebSocketApp, is_private: bool, is_trade: bool = False):
        """Callback when WebSocket connection opens."""
        stream_type = "Trade" if is_trade else ("Private" if is_private else "Public")
        self.logger.info(f"{Colors.CYAN}# WS {stream_type} stream connected.{Colors.RESET}")
        
        if is_trade:
            self.ws_trade = ws
            # Trade stream usually doesn't need auth here as it's for placing orders,
            # but if it were for private data, auth would be similar to ws_private.
            # If trade stream needs auth, implement similar logic to ws_private.
            if self.trade_subscriptions: ws.send(json.dumps({"op": "subscribe", "args": self.trade_subscriptions}))
        elif is_private:
            self.ws_private = ws
            if self.api_key and self.api_secret:
                auth_params = self._generate_auth_params()
                self.logger.debug(f"Sending auth message: {auth_params}")
                ws.send(json.dumps(auth_params))
                # Give a moment for auth to process, then subscribe
                ws.call_later(0.5, lambda: ws.send(json.dumps({"op": "subscribe", "args": self.private_subscriptions})))
            else:
                self.logger.warning(f"{Colors.YELLOW}# Private WebSocket streams not started due to missing API keys.{Colors.RESET}")
        else: # Public
            self.ws_public = ws
            if self.public_subscriptions: ws.send(json.dumps({"op": "subscribe", "args": self.public_subscriptions}))

    def _connect_websocket(self, url: str, is_private: bool, is_trade: bool = False):
        """Manages a single WebSocket connection and its reconnection attempts."""
        on_message_callback = lambda ws, msg: self._on_message(ws, msg, is_private, is_trade)
        on_open_callback = lambda ws: self._on_open(ws, is_private, is_trade)
        
        while not self._stop_event.is_set():
            try:
                ws_app = websocket.WebSocketApp(
                    url,
                    on_message=on_message_callback,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_open=on_open_callback
                )
                # Use ping_interval and ping_timeout to keep connection alive and detect failures
                ws_app.run_forever(ping_interval=20, ping_timeout=10, sslopt={"check_hostname": False})
                
                # If run_forever exits, and we are not intentionally stopping, attempt reconnect
                if not self._stop_event.is_set():
                    self.logger.info(f"WebSocket for {url} exited, attempting reconnect in {WS_RECONNECT_INTERVAL} seconds...")
                    self._stop_event.wait(WS_RECONNECT_INTERVAL) # Wait before reconnecting
            except Exception as e:
                self.logger.error(f"{Colors.NEON_RED}# WS Connection Error for {url}: {e}{Colors.RESET}", exc_info=True)
                if not self._stop_event.is_set():
                    self._stop_event.wait(WS_RECONNECT_INTERVAL) # Wait before reconnecting

    def start_streams(self, public_topics: List[str], private_topics: Optional[List[str]] = None):
        """Starts public, private, and trade WebSocket streams."""
        # Ensure previous streams are fully stopped before starting new ones
        self.stop_streams() # This also sets _stop_event, so clear it for new threads
        self._stop_event.clear()

        self.public_subscriptions, self.private_subscriptions = public_topics, private_topics or []
        
        # Start Public WebSocket
        self.public_thread = threading.Thread(target=self._connect_websocket, args=(self.public_url, False, False), daemon=True, name="PublicWSThread")
        self.public_thread.start()
        
        # Start Private WebSocket (if API keys are present)
        if self.api_key and self.api_secret:
            self.private_thread = threading.Thread(target=self._connect_websocket, args=(self.private_url, True, False), daemon=True, name="PrivateWSThread")
            self.private_thread.start()
        else:
            self.logger.warning(f"{Colors.YELLOW}# Private WebSocket streams not started due to missing API keys.{Colors.RESET}")
            
        # Start Trade WebSocket (for order operations, if needed)
        # Note: The provided SymbolBot class handles order creation/cancellation via CCXT (REST).
        # If you want direct WebSocket order placement, you'd need to manage ws_trade and its messages.
        # For this bot's current structure, ws_trade is not actively used for order ops, but kept for completeness.
        self.trade_thread = threading.Thread(target=self._connect_websocket, args=(self.trade_url, False, True), daemon=True, name="TradeWSThread")
        self.trade_thread.start()

        self.logger.info(f"{Colors.NEON_GREEN}# WebSocket streams have been summoned.{Colors.RESET}")

    def stop_streams(self):
        """Stops all WebSocket streams gracefully."""
        if self._stop_event.is_set(): # Already signaled to stop or never started
            return

        self.logger.info(f"{Colors.YELLOW}# Signaling WebSocket streams to stop...{Colors.RESET}")
        self._stop_event.set() # Signal threads to stop

        # Close WebSocketApp instances
        if self.ws_public:
            try: self.ws_public.close()
            except Exception as e: self.logger.debug(f"Error closing public WS: {e}")
            self.ws_public = None
        if self.ws_private:
            try: self.ws_private.close()
            except Exception as e: self.logger.debug(f"Error closing private WS: {e}")
            self.ws_private = None
        if self.ws_trade:
            try: self.ws_trade.close()
            except Exception as e: self.logger.debug(f"Error closing trade WS: {e}")
            self.ws_trade = None

        # Wait for threads to finish
        if self.public_thread and self.public_thread.is_alive():
            self.public_thread.join(timeout=5)
        if self.private_thread and self.private_thread.is_alive():
            self.private_thread.join(timeout=5)
        if self.trade_thread and self.trade_thread.is_alive():
            self.trade_thread.join(timeout=5)
        
        self.public_thread = None
        self.private_thread = None
        self.trade_thread = None
        self.logger.info(f"{Colors.CYAN}# WebSocket streams have been extinguished.{Colors.RESET}")


# --- Market Maker Strategy ---
class MarketMakerStrategy:
    def __init__(self, bot: 'SymbolBot'):
        self.bot = bot
        self.logger = bot.logger # Use the bot's contextual logger

    def generate_orders(self, symbol: str, mid_price: Decimal, orderbook: Dict[str, Any]):
        self.logger.info(f"[{symbol}] Generating orders using MarketMakerStrategy.")

        # Cancel all existing orders before placing new ones
        self.bot.cancel_all_orders(symbol)
        time.sleep(0.5) # Give API a moment to process cancellations

        orders_to_place: List[Dict[str, Any]] = []
        
        # Calculate dynamic order quantity
        current_order_qty = self.bot.get_dynamic_order_amount(mid_price)

        if current_order_qty <= Decimal("0"):
            self.logger.warning(f"[{symbol}] Calculated order quantity is zero or negative. Skipping order placement.")
            return

        price_precision = self.bot.config.price_precision
        qty_precision = self.bot.config.qty_precision

        # Calculate dynamic spread based on ATR and inventory skew
        dynamic_spread_pct = self.bot.config.base_spread
        if self.bot.config.dynamic_spread.enabled:
            atr_component = self.bot._calculate_atr(mid_price)
            dynamic_spread_pct += atr_component
            self.logger.debug(f"[{symbol}] ATR component for spread: {atr_component:.8f}")

        if self.bot.config.inventory_skew.enabled:
            inventory_skew_component = self.bot._calculate_inventory_skew(mid_price)
            dynamic_spread_pct += inventory_skew_component
            self.logger.debug(f"[{symbol}] Inventory skew component for spread: {inventory_skew_component:.8f}")

        # Ensure spread does not exceed max_spread
        dynamic_spread_pct = min(dynamic_spread_pct, self.bot.config.max_spread)

        self.logger.info(f"[{symbol}] Dynamic Spread: {dynamic_spread_pct * 100:.4f}%")

        # Check for sufficient liquidity at desired price levels
        bids = orderbook.get("b", [])
        asks = orderbook.get("a", [])

        # Calculate cumulative depth for bids and asks
        cumulative_bids = []
        current_cumulative_qty = Decimal("0")
        for price, qty in bids:
            current_cumulative_qty += qty
            cumulative_bids.append({"price": price, "cumulative_qty": current_cumulative_qty})

        cumulative_asks = []
        current_cumulative_qty = Decimal("0")
        for price, qty in asks:
            current_cumulative_qty += qty
            cumulative_asks.append({"price": price, "cumulative_qty": current_cumulative_qty})

        # Place multiple layers of orders
        for i, layer in enumerate(self.bot.config.order_layers):
            layer_spread = dynamic_spread_pct + Decimal(str(layer.spread_offset))
            layer_qty = current_order_qty * Decimal(str(layer.quantity_multiplier))

            # Bid order
            bid_price = mid_price * (Decimal("1") - layer_spread)
            bid_price = self.bot._round_to_precision(bid_price, price_precision)
            bid_qty = self.bot._round_to_precision(layer_qty, qty_precision)

            # Check for sufficient liquidity for bid order
            sufficient_bid_liquidity = False
            # Find the first level in cumulative bids that meets criteria
            for depth_level in cumulative_bids:
                if depth_level["price"] >= bid_price and depth_level["cumulative_qty"] >= bid_qty:
                    sufficient_bid_liquidity = True
                    break
            
            if not sufficient_bid_liquidity:
                self.logger.warning(f"[{symbol}] Insufficient bid liquidity for layer {i+1} at price {bid_price:.{price_precision}f}. Skipping bid order.")
            elif bid_qty > Decimal("0"):
                orders_to_place.append({
                    'category': GLOBAL_CONFIG.category,
                    'symbol': symbol.replace("/", "").replace(":", ""), # Bybit format
                    'side': 'Buy',
                    'orderType': 'Limit',
                    'qty': str(bid_qty),
                    'price': str(bid_price),
                    'timeInForce': 'PostOnly',
                    'orderLinkId': f"MM_BUY_{symbol.replace('/', '')}_{int(time.time() * 1000)}_{i}",
                    'isLeverage': 1 if GLOBAL_CONFIG.category == 'linear' else 0, # Not strictly needed for REST POST, but good for context
                    'triggerDirection': 1 # For TP/SL - not used here
                })

            # Ask order
            sell_price = mid_price * (Decimal("1") + layer_spread)
            sell_price = self.bot._round_to_precision(sell_price, price_precision)
            sell_qty = self.bot._round_to_precision(layer_qty, qty_precision)

            # Check for sufficient liquidity for ask order
            sufficient_ask_liquidity = False
            # Find the first level in cumulative asks that meets criteria
            for depth_level in cumulative_asks:
                if depth_level["price"] <= sell_price and depth_level["cumulative_qty"] >= sell_qty:
                    sufficient_ask_liquidity = True
                    break

            if not sufficient_ask_liquidity:
                self.logger.warning(f"[{symbol}] Insufficient ask liquidity for layer {i+1} at price {sell_price:.{price_precision}f}. Skipping ask order.")
            elif sell_qty > Decimal("0"):
                orders_to_place.append({
                    'category': GLOBAL_CONFIG.category,
                    'symbol': symbol.replace("/", "").replace(":", ""), # Bybit format
                    'side': 'Sell',
                    'orderType': 'Limit',
                    'qty': str(sell_qty),
                    'price': str(sell_price),
                    'timeInForce': 'PostOnly',
                    'orderLinkId': f"MM_SELL_{symbol.replace('/', '')}_{int(time.time() * 1000)}_{i}",
                    'isLeverage': 1 if GLOBAL_CONFIG.category == 'linear' else 0,
                    'triggerDirection': 2 # For TP/SL - not used here
                })

        if orders_to_place:
            self.bot.place_batch_orders(orders_to_place)
        else:
            self.logger.info(f"[{symbol}] No orders placed due to liquidity or quantity constraints.")


# --- Symbol Bot ---
class SymbolBot(threading.Thread):
    """A sorcerous entity managing market making for a single symbol."""
    def __init__(self, config: SymbolConfig, exchange: ccxt.Exchange, ws_client: BybitWebSocket, logger: logging.Logger):
        super().__init__(name=f"SymbolBot-{config.symbol.replace('/', '_').replace(':', '')}")
        self.config = config
        self.exchange = exchange
        self.ws_client = ws_client
        self.logger = logger
        self.symbol = config.symbol
        self._stop_event = threading.Event() # Controls the lifecycle of this SymbolBot's thread
        self.open_orders: Dict[str, Dict[str, Any]] = {} # Track orders placed by this bot {client_order_id: {side, price, amount, status, layer_key, exchange_id, placement_price}}
        self.inventory: Decimal = DECIMAL_ZERO # Current position size for this symbol (positive for long, negative for short)
        self.unrealized_pnl: Decimal = DECIMAL_ZERO
        self.entry_price: Decimal = DECIMAL_ZERO
        self.symbol_info: Optional[Dict[str, Any]] = None
        self.last_atr_update: float = 0.0
        self.cached_atr: Optional[Decimal] = None
        self.last_symbol_info_refresh: float = 0.0
        self.current_leverage: Optional[int] = None
        self.last_imbalance: Decimal = DECIMAL_ZERO
        self.state_file = STATE_DIR / f"{self.symbol.replace('/', '_').replace(':', '')}_state.json"
        self._load_state() # Summon memories from the past
        with self.ws_client.lock: self.ws_client.symbol_bots.append(self) # Register with WS client for message routing
        self.last_order_management_time = 0.0
        self.last_fill_time: float = 0.0 # For initial_position_grace_period_seconds
        self.fill_tracker: List[bool] = [] # Track recent fills for fill rate calculation
        self.today_date: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.daily_metrics: Dict[str, Any] = {} # For daily PnL tracking
        self.pnl_history_snapshots: List[Dict[str, Any]] = [] # For visualization
        self.trade_history: List[Trade] = [] # For visualization
        self.open_positions: List[Trade] = [] # For granular PnL tracking (FIFO)
        self.strategy = MarketMakerStrategy(self) # Initialize strategy

    def _load_state(self):
        """Summons past performance and trade history from its state file."""
        self.performance_metrics = {"trades": 0, "profit": DECIMAL_ZERO, "fees": DECIMAL_ZERO, "net_pnl": DECIMAL_ZERO}
        self.trade_history = []
        self.daily_metrics = {}
        self.pnl_history_snapshots = []

        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    state_data = json_loads_decimal(f.read())
                    metrics = state_data.get("performance_metrics", {})
                    for key in ["profit", "fees", "net_pnl"]: self.performance_metrics[key] = Decimal(str(metrics.get(key, "0")))
                    self.performance_metrics["trades"] = int(metrics.get("trades", 0))
                    
                    for trade_dict in state_data.get("trade_history", []):
                        try: self.trade_history.append(Trade(**trade_dict))
                        except ValidationError as e: self.logger.error(f"[{self.symbol}] Error loading trade from state: {e}")
                    
                    for date_str, daily_metric_dict in state_data.get("daily_metrics", {}).items():
                        try: self.daily_metrics[date_str] = daily_metric_dict # Store as dict, convert to BaseModel on access if needed
                        except ValidationError as e: self.logger.error(f"[{self.symbol}] Error loading daily metrics for {date_str}: {e}")
                    
                    self.pnl_history_snapshots = state_data.get("pnl_history_snapshots", [])

                self.logger.info(f"[{self.symbol}] State summoned from the archives.")
            except Exception as e:
                self.logger.error(f"{Colors.NEON_ORANGE}# Failed to summon state for {self.symbol} from '{self.state_file}'. Starting fresh. Error: {e}{Colors.RESET}", exc_info=True)
                try: # Attempt to rename corrupted file
                    self.state_file.rename(f"{self.state_file}.corrupted_{int(time.time())}")
                    self.logger.warning(f"[{self.symbol}] Renamed corrupted state file.")
                except OSError as ose:
                    self.logger.warning(f"[{self.symbol}] Could not rename corrupted state file: {ose}")
        self._reset_daily_metrics_if_new_day() # Ensure today's metrics are fresh


    def _save_state(self):
        """Enshrines the bot's memories into its state file."""
        try:
            state_data = {
                "performance_metrics": self.performance_metrics,
                "trade_history": [trade.model_dump() for trade in self.trade_history],
                "daily_metrics": {date: metric for date, metric in self.daily_metrics.items()},
                "pnl_history_snapshots": self.pnl_history_snapshots
            }
            # Use atomic write: write to temp file, then rename
            temp_path = self.state_file.with_suffix(f".tmp_{os.getpid()}")
            with open(temp_path, "w") as f:
                json.dump(state_data, f, indent=4, cls=JsonDecimalEncoder)
            os.replace(temp_path, self.state_file)
            self.logger.info(f"[{self.symbol}] State enshrined to {self.state_file}")
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# Failed to enshrine state for {self.symbol}: {e}{Colors.RESET}", exc_info=True)

    def _reset_daily_metrics_if_new_day(self):
        """Resets daily metrics if a new UTC day has started."""
        current_utc_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.today_date != current_utc_date:
            self.logger.info(f"[{self.symbol}] New day detected. Resetting daily PnL from {self.today_date} to {current_utc_date}.")
            # Store previous day's snapshot if not already stored
            if self.today_date in self.daily_metrics:
                self.daily_metrics[self.today_date]["unrealized_pnl_snapshot"] = str(self.unrealized_pnl) # Snapshot UPL at day end
            self.today_date = current_utc_date
            self.daily_metrics.setdefault(self.today_date, {"date": self.today_date, "realized_pnl": "0", "unrealized_pnl_snapshot": "0", "total_fees": "0", "trades_count": 0})


    @retry_api_call()
    def _fetch_symbol_info(self) -> bool:
        """Fetches and updates market symbol information and precision."""
        try:
            market = self.exchange.market(self.symbol)
            if not market or not market.get("active"):
                self.logger.warning(f"[{self.symbol}] Symbol {self.symbol} is not active or market info missing. Pausing.")
                return False

            self.symbol_info = market
            # Convert limits to Decimal for precision
            self.config.min_qty = (
                Decimal(str(market["limits"]["amount"]["min"]))
                if market["limits"]["amount"]["min"] is not None
                else Decimal("0") # Default to 0 if not specified
            )
            self.config.max_qty = (
                Decimal(str(market["limits"]["amount"]["max"]))
                if market["limits"]["amount"]["max"] is not None
                else Decimal("999999999") # Default to a large number
            )
            self.config.qty_precision = market["precision"]["amount"]
            self.config.price_precision = market["precision"]["price"]
            self.config.min_notional = (
                Decimal(str(market["limits"]["cost"]["min"]))
                if market["limits"]["cost"]["min"] is not None
                else Decimal("0") # Default to 0 if not specified
            )
            self.last_symbol_info_refresh = time.time()
            self.logger.info(
                f"[{self.symbol}] Symbol info fetched: Min Qty={self.config.min_qty}, "
                f"Price Prec={self.config.price_precision}, Min Notional={self.config.min_notional}"
            )
            return True
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# Failed to fetch symbol info for {self.symbol}: {e}{Colors.RESET}", exc_info=True)
            return False

    @retry_api_call()
    def _set_leverage_if_needed(self) -> bool:
        """Ensures the correct leverage is set for the symbol."""
        try:
            positions = self.exchange.fetch_positions([self.symbol])
            current_leverage = None
            for p in positions:
                if p["symbol"] == self.symbol and "info" in p and p["info"].get("leverage"):
                    current_leverage = int(float(p["info"]["leverage"]))
                    break

            if current_leverage == int(self.config.leverage):
                self.logger.info(f"[{self.symbol}] Leverage already set to {self.config.leverage}.")
                self.current_leverage = int(self.config.leverage)
                return True

            self.exchange.set_leverage(
                float(self.config.leverage), self.symbol
            )  # Cast to float for ccxt
            self.current_leverage = int(self.config.leverage)
            self.logger.info(f"{Colors.NEON_GREEN}# Leverage for {self.symbol} set to {self.config.leverage}.{Colors.RESET}")
            termux_notify(f"{self.symbol}: Leverage set to {self.config.leverage}", title="Config Update")
            return True
        except Exception as e:
            if "leverage not modified" in str(e).lower():
                self.logger.warning(
                    f"[{self.symbol}] Leverage unchanged (might be already applied but not reflected): {e}"
                )
                return True
            self.logger.error(f"{Colors.NEON_RED}# Error setting leverage for {self.symbol}: {e}{Colors.RESET}", exc_info=True)
            return False

    @retry_api_call()
    def _set_margin_mode_and_position_mode(self) -> bool:
        """Ensures Isolated Margin and One-Way position mode are set."""
        normalized_symbol_bybit = self.symbol.replace("/", "").replace(":", "")  # e.g., BTCUSDT
        try:
            # Check and set Margin Mode to ISOLATED
            current_margin_mode = None
            positions_info = self.exchange.fetch_positions([self.symbol])
            if positions_info:
                for p in positions_info:
                    if p["symbol"] == self.symbol and "info" in p and "tradeMode" in p["info"]:
                        current_margin_mode = p["info"]["tradeMode"]
                        break

            if current_margin_mode != "IsolatedMargin":
                self.logger.info(
                    f"[{self.symbol}] Current margin mode is not Isolated ({current_margin_mode}). "
                    f"Attempting to switch to Isolated."
                )
                self.exchange.set_margin_mode("isolated", self.symbol)
                self.logger.info(f"[{self.symbol}] Successfully set margin mode to Isolated.")
                termux_notify(f"{self.symbol}: Set to Isolated Margin", title="Config Update")
            else:
                self.logger.info(f"[{self.symbol}] Margin mode already Isolated.")

            # Check and set Position Mode to One-Way (Merged Single)
            current_position_mode_idx = None
            if positions_info:
                for p in positions_info:
                    if p["symbol"] == self.symbol and "info" in p and "positionIdx" in p["info"]:
                        current_position_mode_idx = int(p["info"]["positionIdx"])
                        break

            if current_position_mode_idx != 0:  # 0 for Merged Single/One-Way
                self.logger.info(
                    f"[{self.symbol}] Current position mode is not One-Way ({current_position_mode_idx}). "
                    f"Attempting to switch to One-Way (mode 0)."
                )
                # Use ccxt's private_post_position_switch_mode for Bybit V5
                self.exchange.private_post_position_switch_mode(
                    {
                        "category": GLOBAL_CONFIG.category, # Use global config category
                        "symbol": normalized_symbol_bybit,
                        "mode": 0, # 0 for One-Way, 1 for Hedge
                    }
                )
                self.logger.info(f"[{self.symbol}] Successfully set position mode to One-Way.")
                termux_notify(f"{self.symbol}: Set to One-Way Mode", title="Config Update")
            else:
                self.logger.info(f"[{self.symbol}] Position mode already One-Way.")

            return True
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# Error setting margin/position mode for {self.symbol}: {e}{Colors.RESET}", exc_info=True)
            termux_notify(f"{self.symbol}: Failed to set margin/pos mode!", is_error=True)
            return False

    @retry_api_call()
    def _fetch_funding_rate(self) -> Optional[Decimal]:
        """Fetches the current funding rate for the symbol."""
        try:
            # Bybit's fetch_funding_rate might need specific parameters for V5
            # CCXT unified method `fetch_funding_rate` should handle it.
            funding_rates = self.exchange.fetch_funding_rate(self.symbol)
            
            # The structure might vary based on CCXT version and exchange implementation details.
            # Accessing 'info' might be necessary to get raw exchange data.
            if funding_rates and funding_rates.get("info") and funding_rates["info"].get("list"):
                # Bybit V5 structure might have 'fundingRate' directly in 'list' or nested.
                # Need to check CCXT's specific handling for Bybit V5 funding rates.
                # Assuming 'fundingRate' is directly accessible or within 'list'
                funding_rate_str = funding_rates["info"]["list"][0].get("fundingRate", "0") # Safely get fundingRate
                funding_rate = Decimal(str(funding_rate_str))
                self.logger.debug(f"[{self.symbol}] Fetched funding rate: {funding_rate}")
                return funding_rate
            elif funding_rates and funding_rates.get("rate") is not None: # Fallback if structure differs
                 funding_rate = Decimal(str(funding_rates.get("rate")))
                 self.logger.debug(f"[{self.symbol}] Fetched funding rate (fallback): {funding_rate}")
                 return funding_rate
            else:
                self.logger.warning(f"[{self.symbol}] No funding rate found for {self.symbol}.")
                return Decimal("0")
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# Error fetching funding rate for {self.symbol}: {e}{Colors.RESET}", exc_info=True)
            return Decimal("0") # Return zero if error occurs

    def _handle_order_update(self, order_data: Dict[str, Any]):
        """Processes order updates received from WebSocket."""
        order_id = order_data.get("orderId")
        client_order_id = order_data.get("orderLinkId") # Bybit's clientOrderId
        status = order_data.get("orderStatus")

        # Ensure we are only processing for this bot's symbol
        normalized_symbol_data = self._normalize_symbol_ws(order_data.get("symbol", ""))
        if normalized_symbol_data != self.symbol:
            self.logger.debug(
                f"[{self.symbol}] Received order update for different symbol "
                f"{normalized_symbol_data}. Skipping."
            )
            return

        with self.ws_client.lock:  # Protect open_orders
            # Use client_order_id for tracking if available, fall back to order_id
            tracked_order_id = client_order_id if client_order_id else order_id

            if status == "Filled":
                qty = Decimal(str(order_data.get("cumExecQty", "0")))
                price = Decimal(str(order_data.get("avgPrice", order_data.get("price", "0"))))
                fee = Decimal(str(order_data.get("cumExecFee", "0")))
                side = order_data.get("side").lower()

                trade_profit = Decimal("0") # Will be updated when position is closed

                trade = Trade(
                    side=side,
                    qty=qty,
                    price=price,
                    profit=trade_profit,
                    timestamp=int(order_data.get("updatedTime", time.time() * 1000)),
                    fee=fee,
                    trade_id=order_id,
                    entry_price=self.entry_price,  # Entry price is position-level at time of fill
                )

                self.trade_history.append(trade)
                self.performance_metrics["trades"] += 1
                self.performance_metrics["fees"] += fee

                self.logger.info(
                    f"{Colors.NEON_GREEN}[{self.symbol}] Market making trade executed: "
                    f"{side.upper()} {qty:.{self.config.qty_precision}f} @ {price:.{self.config.price_precision}f}, "
                    f"Fee: {fee:.8f}{Colors.RESET}"
                )
                termux_notify(
                    f"{self.symbol}: {side.upper()} {qty:.4f} @ {price:.4f} (Fee: {fee:.8f})",
                    title="Trade Executed",
                )
                self.last_fill_time = time.time() # Update last fill time
                self.fill_tracker.append(True) # Track successful fill

                if tracked_order_id in self.open_orders:
                    self.logger.debug(f"[{self.symbol}] Removing filled order {tracked_order_id} from open_orders.")
                    del self.open_orders[tracked_order_id]

            elif status in ["Canceled", "Deactivated", "Rejected"]:
                if tracked_order_id in self.open_orders:
                    self.logger.info(
                        f"[{self.symbol}] Order {tracked_order_id} ({self.open_orders[tracked_order_id]['side'].upper()} "
                        f"{self.open_orders[tracked_order_id]['amount']:.4f}) status: {status}"
                    )
                    del self.open_orders[tracked_order_id]
                    if status == "Rejected":
                        self.fill_tracker.append(False) # Track rejection as failure
                else:
                    self.logger.debug(f"[{self.symbol}] Received status '{status}' for untracked order {tracked_order_id}.")
            else: # Other statuses like New, PartiallyFilled, etc.
                if tracked_order_id in self.open_orders:
                    self.open_orders[tracked_order_id]["status"] = status  # Update status
                self.logger.debug(f"[{self.symbol}] Order {tracked_order_id} status update: {status}")

    def _handle_position_update(self, pos_data: Dict[str, Any]):
        """Processes position updates received from WebSocket."""
        size_str = pos_data.get("size", "0")
        size = Decimal(str(size_str)) if size_str is not None else Decimal("0")

        # Convert to signed inventory (positive for long, negative for short)
        if pos_data.get("side") == "Sell":
            size = -size

        current_inventory = self.inventory
        current_entry_price = self.entry_price

        self.inventory = size
        self.unrealized_pnl = Decimal(str(pos_data.get("unrealisedPnl", "0")))
        # Only update entry price if there's an actual position
        self.entry_price = (
            Decimal(str(pos_data.get("avgPrice", "0")))
            if abs(size) > Decimal("0")
            else Decimal("0")
        )

        self.logger.debug(
            f"[{self.symbol}] Position updated via WS: {self.inventory:+.4f}, "
            f"UPL: {self.unrealized_pnl:+.4f}, "
            f"Entry: {self.entry_price:.{self.config.price_precision if self.config.price_precision is not None else 8}f}"
        )

        # Trigger TP/SL update if position size or entry price has significantly changed
        epsilon_qty = Decimal("1e-8")  # Small epsilon for Decimal quantity comparison
        epsilon_price_pct = Decimal("1e-5")  # 0.001% change for price comparison

        position_size_changed = abs(current_inventory - self.inventory) > epsilon_qty
        entry_price_changed = (
            abs(self.inventory) > Decimal("0")
            and abs(current_entry_price) > Decimal("0") # Ensure current_entry_price is not zero to avoid division by zero
            and abs(self.entry_price) > Decimal("0") # Ensure new entry price is not zero
            and abs(current_entry_price - self.entry_price) / current_entry_price
            > epsilon_price_pct
        )

        if position_size_changed or entry_price_changed:
            self.logger.info(
                f"[{self.symbol}] Position changed ({current_inventory:+.4f} "
                f"-> {self.inventory:+.4f}). Triggering TP/SL update."
            )
            self.update_take_profit_stop_loss()
        
        # Update daily metrics with current PnL
        self._reset_daily_metrics_if_new_day()
        current_daily_metrics = self.daily_metrics[self.today_date]
        current_daily_metrics["unrealized_pnl_snapshot"] = str(self.unrealized_pnl) # Snapshot UPL

    def _handle_execution_update(self, exec_data: Dict[str, Any]):
        """
        Processes execution updates, which contain realized PnL.
        This is typically for closing positions.
        """
        exec_side = exec_data.get("side").lower()
        exec_qty = Decimal(str(exec_data.get("execQty", "0")))
        exec_price = Decimal(str(exec_data.get("execPrice", "0")))
        exec_fee = Decimal(str(exec_data.get("execFee", "0")))
        exec_time = int(exec_data.get("execTime", time.time() * 1000))
        exec_id = exec_data.get("execId")
        closed_pnl = Decimal(str(exec_data.get("closedPnl", "0")))

        # Update overall performance metrics
        self.performance_metrics["profit"] += closed_pnl
        self.performance_metrics["fees"] += exec_fee
        self.performance_metrics["net_pnl"] = self.performance_metrics["profit"] - self.performance_metrics["fees"]

        # Update daily metrics
        self._reset_daily_metrics_if_new_day()
        current_daily_metrics = self.daily_metrics[self.today_date]
        current_daily_metrics["realized_pnl"] = str(Decimal(current_daily_metrics.get("realized_pnl", "0")) + closed_pnl)
        current_daily_metrics["total_fees"] = str(Decimal(current_daily_metrics.get("total_fees", "0")) + exec_fee)
        current_daily_metrics["trades_count"] += 1

        self.logger.info(
            f"{Colors.MAGENTA}[{self.symbol}] Execution update: {exec_side.upper()} {exec_qty:.4f} @ {exec_price:.4f}, "
            f"Closed PnL: {closed_pnl:+.4f}, Total Realized PnL: {self.performance_metrics['profit']:+.4f}{Colors.RESET}"
        )
        termux_notify(f"{self.symbol}: Executed {exec_side.upper()} {exec_qty:.4f}. PnL: {closed_pnl:+.4f}", title="Execution")


    @retry_api_call()
    def _close_profitable_entities(self, current_price: Decimal):
        """
        Closes profitable open positions with a market order, with slippage check.
        This serves as a backup/additional profit-taking mechanism,
        as primary TP/SL is handled by Bybit's `set_trading_stop`.
        """
        if not self.config.trade_enabled:
            return

        try:
            positions = self.exchange.fetch_positions([self.symbol])
            for pos in positions:
                # Check if there's an open position and it belongs to this bot's symbol
                if pos["symbol"] == self.symbol and abs( Decimal(str(pos.get("info", {}).get("size", "0"))) ) > Decimal("0"):
                    position_size = Decimal(str(pos.get("info", {}).get("size", "0")))
                    entry_price = Decimal(str(pos.get("entryPrice", "0")))
                    unrealized_pnl_percent = Decimal("0")
                    unrealized_pnl_amount = Decimal("0")

                    if entry_price > Decimal("0"):
                        if pos["side"] == "long":
                            unrealized_pnl_percent = (current_price - entry_price) / entry_price
                            unrealized_pnl_amount = (current_price - entry_price) * position_size
                        elif pos["side"] == "short":
                            unrealized_pnl_percent = (entry_price - current_price) / current_price
                            unrealized_pnl_amount = (entry_price - current_price) * position_size

                    # Only attempt to close if PnL is above TP threshold
                    if unrealized_pnl_percent >= Decimal(str(self.config.take_profit_percentage)):
                        self.logger.info(
                            f"[{self.symbol}] Position ({pos['side'].upper()} {position_size:+.4f} "
                            f"@ {entry_price:.{self.config.price_precision}f}) is profitable "
                            f"({unrealized_pnl_percent:.4f}%). Checking for slippage to close..."
                        )
                        close_side = "sell" if pos["side"] == "long" else "buy"

                        # --- Slippage Check for Closing Position ---
                        symbol_id_ws = self.symbol.replace("/", "").replace(":", "")
                        orderbook = self.ws_client.get_order_book_snapshot(symbol_id_ws)
                        if not orderbook or not orderbook.get("b") or not orderbook.get("a"):
                            self.logger.warning(
                                f"{Colors.NEON_ORANGE}[{self.symbol}] No order book data for slippage check. "
                                f"Skipping profitable position close.{Colors.RESET}"
                            )
                            continue
                        
                        # Use pandas for easier depth analysis
                        bids_df = pd.DataFrame(orderbook["b"], columns=["price", "quantity"])
                        asks_df = pd.DataFrame(orderbook["a"], columns=["price", "quantity"])
                        bids_df["cum_qty"] = bids_df["quantity"].cumsum()
                        asks_df["cum_qty"] = asks_df["quantity"].cumsum()
                        
                        required_qty = abs(position_size)
                        estimated_slippage_pct = Decimal("0")
                        exec_price = current_price # Default to current price if no sufficient depth is found

                        if close_side == "sell": # Closing a long position with a market sell
                            # Find bids that are greater than or equal to the current mid-price (or slightly adjusted)
                            # And check cumulative quantity
                            valid_bids = bids_df[bids_df["price"] >= mid_price] # Use mid_price for reference
                            if valid_bids.empty:
                                self.logger.warning(
                                    f"{Colors.NEON_ORANGE}[{self.symbol}] No valid bids found for slippage check. Skipping.{Colors.RESET}"
                                )
                                continue
                            sufficient_bids = valid_bids[valid_bids["cum_qty"] >= required_qty]
                            if sufficient_bids.empty:
                                self.logger.warning(
                                    f"{Colors.NEON_ORANGE}[{self.symbol}] Insufficient bid cumulative quantity for closing long "
                                    f"position. Skipping.{Colors.RESET}"
                                )
                                continue
                            exec_price = sufficient_bids["price"].iloc[0] # Get the price of the first bid that meets criteria
                            
                            estimated_slippage_pct = (
                                (current_price - exec_price) / current_price * Decimal("100")
                                if current_price > Decimal("0") else Decimal("0")
                            )
                        elif close_side == "buy": # Closing a short position with a market buy
                            # Find asks that are less than or equal to the current mid-price (or slightly adjusted)
                            # And check cumulative quantity
                            valid_asks = asks_df[asks_df["price"] <= mid_price] # Use mid_price for reference
                            if valid_asks.empty:
                                self.logger.warning(
                                    f"{Colors.NEON_ORANGE}[{self.symbol}] No valid asks found for slippage check. Skipping.{Colors.RESET}"
                                )
                                continue
                            sufficient_asks = valid_asks[valid_asks["cum_qty"] >= required_qty]
                            if sufficient_asks.empty:
                                self.logger.warning(
                                    f"{Colors.NEON_ORANGE}[{self.symbol}] Insufficient ask cumulative quantity for closing short "
                                    f"position. Skipping.{Colors.RESET}"
                                )
                                continue
                            exec_price = sufficient_asks["price"].iloc[0] # Get the price of the first ask that meets criteria
                            
                            estimated_slippage_pct = (
                                (exec_price - current_price) / current_price * Decimal("100")
                                if current_price > Decimal("0") else Decimal("0")
                            )

                        if estimated_slippage_pct > Decimal(str(self.config.slippage_tolerance_pct)) * Decimal( "100" ):
                            self.logger.warning(
                                f"{Colors.NEON_ORANGE}[{self.symbol}] Estimated slippage "
                                f"({estimated_slippage_pct:.2f}%) exceeds tolerance "
                                f"({self.config.slippage_tolerance_pct * 100:.2f}%). "
                                f"Skipping profitable position close.{Colors.RESET}"
                            )
                            continue

                        try:
                            # Use create_market_order for closing
                            closed_order = self.exchange.create_market_order(self.symbol, close_side, float(required_qty))
                            self.logger.info(
                                f"[{self.symbol}] Successfully placed market order to close profitable position "
                                f"with estimated slippage {estimated_slippage_pct:.2f}%."
                            )
                            termux_notify(
                                f"{self.symbol}: Closed profitable {pos['side'].upper()} position!", title="Profit Closed",
                            )
                        except Exception as e:
                            self.logger.error(
                                f"[{self.symbol}] Error closing profitable position with market order: {e}", exc_info=True,
                            )
                            termux_notify(f"{self.symbol}: Failed to close profitable position!", is_error=True)

        except Exception as e:
            self.logger.error(
                f"[{self.symbol}] Error fetching or processing positions for profit closing: {e}", exc_info=True,
            )

    def _calculate_atr(self, mid_price: Decimal) -> Decimal:
        """Calculates the ATR-based dynamic spread component."""
        if not self.config.dynamic_spread.enabled or (
            time.time() - self.last_atr_update < self.config.dynamic_spread.atr_update_interval
            and self.cached_atr is not None
        ):
            return self.cached_atr if self.cached_atr is not None else Decimal("0")
        try:
            # Fetch OHLCV candles for ATR calculation. CCXT requires interval string like '1m', '5m', etc.
            # We need to map the config's kline_interval to CCXT's format.
            # Assuming self.config.kline_interval is set and is compatible (e.g., '1m', '5m', '15m', '1h', '1d')
            # If not set, we might need a default or fetch it from exchange info.
            # For now, let's assume a default or use a common interval like '1m' or '5m'.
            # If config.kline_interval is not available, we might need to fetch it or set a default.
            # Let's assume a default of '1m' if not specified in config.
            ohlcv_interval = self.config.kline_interval if hasattr(self.config, 'kline_interval') and self.config.kline_interval else '1m'
            
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, ohlcv_interval, limit=20)
            if not ohlcv or len(ohlcv) < 20:
                self.logger.warning(f"[{self.symbol}] Not enough OHLCV data ({len(ohlcv)}/{20}) for ATR. Using cached or 0.")
                return self.cached_atr if self.cached_atr is not None else Decimal("0")
            
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            # Ensure columns are Decimal type for calculations
            df["high"] = df["high"].apply(Decimal)
            df["low"] = df["low"].apply(Decimal)
            df["close"] = df["close"].apply(Decimal)
            
            # Ensure all necessary columns for atr calculation are present
            if "high" not in df.columns or "low" not in df.columns or "close" not in df.columns:
                self.logger.warning(f"[{self.symbol}] Missing columns for ATR calculation in OHLCV data.")
                return self.cached_atr if self.cached_atr is not None else Decimal("0")

            atr_val = atr(df["high"], df["low"], df["close"]).iloc[-1]
            if pd.isna(atr_val):
                self.logger.warning(f"[{self.symbol}] ATR calculation resulted in NaN. Using cached or 0.")
                return self.cached_atr if self.cached_atr is not None else Decimal("0")

            # Normalize ATR by mid_price and apply multiplier
            self.cached_atr = (Decimal(str(atr_val)) / mid_price) * Decimal(
                str(self.config.dynamic_spread.volatility_multiplier)
            )
            self.last_atr_update = time.time()
            self.logger.debug(
                f"[{self.symbol}] Calculated ATR: {atr_val:.8f}, Normalized ATR for spread: {self.cached_atr:.8f}"
            )
            return self.cached_atr
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# [{self.symbol}] ATR Error: {e}{Colors.RESET}", exc_info=True)
            return self.cached_atr if self.cached_atr is not None else Decimal("0")

    def _calculate_inventory_skew(self, mid_price: Decimal) -> Decimal:
        """Calculates the inventory skew component for spread adjustment."""
        if not self.config.inventory_skew.enabled or self.inventory == DECIMAL_ZERO:
            return DECIMAL_ZERO
        
        # Normalize inventory by inventory_limit.
        normalized_inventory = self.inventory / Decimal(str(self.config.inventory_limit))
        
        # Apply skew factor
        skew_component = normalized_inventory * Decimal(str(self.config.inventory_skew.skew_factor))
        
        # Limit the maximum skew
        max_skew_abs = Decimal(str(self.config.inventory_skew.max_skew)) if self.config.inventory_skew.max_skew is not None else Decimal("0.001") # Default max skew if not set
        skew_component = max(min(skew_component, max_skew_abs), -max_skew_abs)
        
        # For simplicity, return the absolute value to widen the spread symmetrically.
        # A more complex logic could apply asymmetric spreads (e.g., tighten ask if long).
        return abs(skew_component)

    def get_dynamic_order_amount(self, mid_price: Decimal) -> Decimal:
        """Calculates dynamic order amount based on ATR and inventory sizing factor."""
        base_qty = Decimal(str(self.config.order_amount))
        
        # Adjust quantity based on ATR (volatility)
        # This logic is commented out as ATR is used for spread in this implementation.
        # If you want ATR to affect quantity, implement logic here.
        # if self.config.dynamic_spread.enabled and self.cached_atr is not None:
        #     normalized_atr = self.cached_atr * self.config.atr_qty_multiplier
        #     # Example: Higher ATR -> lower quantity
        #     qty_multiplier = max(Decimal("0.2"), Decimal("1") - normalized_atr)
        #     base_qty *= qty_qty_multiplier
        
        # Adjust quantity based on inventory sizing factor
        if self.inventory != DECIMAL_ZERO:
            # Calculate inventory pressure: closer to limit, smaller orders
            inventory_pressure = abs(self.inventory) / Decimal(str(self.config.inventory_limit))
            inventory_factor = Decimal("1") - (inventory_pressure * Decimal(str(self.config.inventory_sizing_factor)))
            base_qty *= max(Decimal("0.1"), inventory_factor) # Ensure quantity doesn't drop too low

        # Validate against min/max quantity and min notional
        if self.config.min_qty is not None and base_qty < self.config.min_qty:
            self.logger.warning(f"[{self.symbol}] Calculated quantity {base_qty:.8f} is below min_qty {self.config.min_qty:.8f}. Adjusting to min_qty.")
            base_qty = self.config.min_qty
        
        if self.config.max_qty is not None and base_qty > self.config.max_qty:
            self.logger.warning(f"[{self.symbol}] Calculated quantity {base_qty:.8f} is above max_qty {self.config.max_qty:.8f}. Adjusting to max_qty.")
            base_qty = self.config.max_qty

        # Check against min_order_value_usd
        if mid_price > DECIMAL_ZERO and self.config.min_order_value_usd > 0:
            current_order_value_usd = base_qty * mid_price
            if current_order_value_usd < Decimal(str(self.config.min_order_value_usd)):
                required_qty_for_min_value = Decimal(str(self.config.min_order_value_usd)) / mid_price
                base_qty = max(base_qty, required_qty_for_min_value)
                self.logger.warning(f"[{self.symbol}] Order value {current_order_value_usd:.2f} USD is below min {self.config.min_order_value_usd} USD. Adjusting quantity to {base_qty:.8f}.")

        return base_qty

    def _round_to_precision(self, value: Union[float, Decimal], precision: Optional[int]) -> Decimal:
        """Rounds a Decimal value to the specified number of decimal places."""
        value_dec = Decimal(str(value)) # Ensure it's Decimal
        if precision is not None and precision >= 0:
            # Using quantize for proper rounding to decimal places
            # ROUND_HALF_UP is common, but ROUND_HALF_EVEN is default in Decimal context
            # Let's use ROUND_HALF_UP for clearer financial rounding.
            return value_dec.quantize(Decimal(f'1e-{precision}'))
        return value_dec.quantize(Decimal('1')) # For zero or negative precision (e.g., integer rounding)

    @retry_api_call()
    def place_batch_orders(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Places a batch of orders (limit orders for market making)."""
        if not orders:
            return []
        
        # Filter out orders that are too small based on min_notional
        filtered_orders = []
        for order in orders:
            qty = Decimal(order['qty'])
            price = Decimal(order['price'])
            notional = qty * price
            if self.config.min_notional is not None and notional < self.config.min_notional:
                self.logger.warning(f"[{self.symbol}] Skipping order {order.get('orderLinkId', '')} due to low notional value: {notional:.4f} < {self.config.min_notional:.4f}")
                continue
            filtered_orders.append(order)

        if not filtered_orders:
            return []

        try:
            # Bybit V5 batch order endpoint: privatePostOrderCreateBatch
            # The structure for create_orders is a list of order parameters
            # CCXT's create_orders method takes a list of order dicts.
            responses = self.exchange.create_orders(filtered_orders)
            
            successful_orders = []
            for resp in responses:
                # CCXT's unified response structure often has 'info' field for raw exchange data.
                # Bybit's retCode indicates success.
                if resp.get("info", {}).get("retCode") == 0:
                    order_info = resp.get("info", {})
                    client_order_id = order_info.get("orderLinkId")
                    exchange_id = order_info.get("orderId")
                    side = order_info.get("side") # Should be from the response data
                    amount = Decimal(str(order_info.get("qty", "0")))
                    price = Decimal(str(order_info.get("price", "0")))
                    status = order_info.get("orderStatus")
                    
                    # Store order details for tracking
                    self.open_orders[client_order_id] = {
                        "side": side,
                        "amount": amount,
                        "price": price,
                        "status": status,
                        "timestamp": time.time() * 1000, # Use milliseconds
                        "exchange_id": exchange_id,
                        "placement_price": price # Store price at placement for stale order check
                    }
                    successful_orders.append(resp)
                    self.logger.info(f"[{self.symbol}] Placed {side} limit order: {amount:.{self.config.qty_precision}f} @ {price:.{self.config.price_precision}f} (ID: {client_order_id})")
                else:
                    self.logger.error(f"[{self.symbol}] Failed to place order: {resp.get('info', {}).get('retMsg', 'Unknown error')}")
            return successful_orders
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# [{self.symbol}] Error placing batch orders: {e}{Colors.RESET}", exc_info=True)
            return []

    @retry_api_call()
    def cancel_all_orders(self, symbol: str):
        """Cancels all open orders for a given symbol."""
        try:
            # Bybit V5: POST /v5/order/cancel-all
            # ccxt unified method: cancel_all_orders
            # Need to specify category and symbol
            self.exchange.cancel_all_orders(symbol, params={'category': GLOBAL_CONFIG.category})
            with self.ws_client.lock: # Protect open_orders
                self.open_orders.clear() # Clear local cache immediately
            self.logger.info(f"[{symbol}] All open orders cancelled.")
            termux_notify(f"{symbol}: All orders cancelled.", title="Orders Cancelled")
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# [{symbol}] Error cancelling all orders: {e}{Colors.RESET}", exc_info=True)
            termux_notify(f"{symbol}: Failed to cancel orders!", is_error=True)

    @retry_api_call()
    def cancel_order(self, order_id: str, client_order_id: str):
        """Cancels a specific order by order_id or client_order_id."""
        try:
            # Bybit V5: POST /v5/order/cancel
            # ccxt unified method: cancel_order
            # Bybit requires symbol and category for cancel_order
            self.exchange.cancel_order(order_id, self.symbol, params={'category': GLOBAL_CONFIG.category, 'orderLinkId': client_order_id})
            with self.ws_client.lock: # Protect open_orders
                if client_order_id in self.open_orders:
                    del self.open_orders[client_order_id]
            self.logger.info(f"[{self.symbol}] Order {client_order_id} cancelled.")
            termux_notify(f"{self.symbol}: Order {client_order_id} cancelled.", title="Order Cancelled")
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# [{self.symbol}] Error cancelling order {client_order_id}: {e}{Colors.RESET}", exc_info=True)
            termux_notify(f"{self.symbol}: Failed to cancel order {client_order_id}!", is_error=True)

    def update_take_profit_stop_loss(self):
        """
        Sets or updates Take Profit and Stop Loss for the current position.
        This uses Bybit's unified trading `set_trading_stop` endpoint.
        """
        if not self.config.enable_auto_sl_tp:
            return

        if abs(self.inventory) == DECIMAL_ZERO:
            self.logger.debug(f"[{self.symbol}] No open position to set TP/SL for.")
            return

        side = "Buy" if self.inventory < DECIMAL_ZERO else "Sell" # Side of the TP/SL order (opposite of position)
        
        # Calculate TP/SL prices based on entry price
        take_profit_price = DECIMAL_ZERO
        stop_loss_price = DECIMAL_ZERO

        if self.inventory > DECIMAL_ZERO: # Long position
            take_profit_price = self.entry_price * (Decimal("1") + Decimal(str(self.config.take_profit_target_pct)))
            stop_loss_price = self.entry_price * (Decimal("1") - Decimal(str(self.config.stop_loss_trigger_pct)))
        elif self.inventory < DECIMAL_ZERO: # Short position
            take_profit_price = self.entry_price * (Decimal("1") - Decimal(str(self.config.take_profit_target_pct)))
            stop_loss_price = self.entry_price * (Decimal("1") + Decimal(str(self.config.stop_loss_trigger_pct)))
        
        # Round to symbol's price precision
        price_precision = self.config.price_precision
        take_profit_price = self._round_to_precision(take_profit_price, price_precision)
        stop_loss_price = self._round_to_precision(stop_loss_price, price_precision)

        try:
            # Bybit V5 set_trading_stop requires symbol, category, and TP/SL values
            # It also requires position_idx (0 for One-Way mode, which we enforce)
            params = {
                'category': GLOBAL_CONFIG.category,
                'symbol': self.symbol.replace("/", "").replace(":", ""), # Bybit format
                'takeProfit': str(take_profit_price),
                'stopLoss': str(stop_loss_price),
                'tpTriggerBy': 'LastPrice', # Or 'MarkPrice', 'IndexPrice'
                'slTriggerBy': 'LastPrice', # Or 'MarkPrice', 'IndexPrice'
                'positionIdx': 0 # For One-Way mode
            }
            # CCXT's set_trading_stop is for unified TP/SL.
            # For Bybit V5, it maps to `set_trading_stop` which is the correct endpoint.
            self.exchange.set_trading_stop(
                self.symbol,
                float(take_profit_price), # CCXT expects float
                float(stop_loss_price), # CCXT expects float
                params=params
            )
            self.logger.info(
                f"[{self.symbol}] Set TP: {take_profit_price:.{price_precision}f}, "
                f"SL: {stop_loss_price:.{price_precision}f} for {self.inventory:+.4f} position."
            )
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# [{self.symbol}] Error setting TP/SL: {e}{Colors.RESET}", exc_info=True)
            termux_notify(f"{self.symbol}: Failed to set TP/SL!", is_error=True)

    def _check_and_handle_stale_orders(self):
        """Cancels limit orders that have been open for too long."""
        current_time = time.time()
        orders_to_cancel = []
        with self.ws_client.lock: # Protect open_orders during iteration
            for client_order_id, order_info in list(self.open_orders.items()): # Iterate on a copy
                # Check if order is still active and if its age exceeds the threshold
                if order_info.get("status") not in ["FILLED", "Canceled", "REJECTED"] and \
                   (current_time - order_info.get("timestamp", current_time) / 1000) > self.config.stale_order_max_age_seconds:
                    self.logger.info(f"[{self.symbol}] Stale order detected: {client_order_id}. Cancelling.")
                    orders_to_cancel.append((order_info.get("exchange_id"), client_order_id))
        
        for exchange_id, client_order_id in orders_to_cancel:
            self.cancel_order(exchange_id, client_order_id)

    def _check_daily_pnl_limits(self):
        """Checks daily PnL against configured stop-loss and take-profit limits."""
        if not self.daily_metrics:
            return

        current_daily_metrics = self.daily_metrics.get(self.today_date)
        if not current_daily_metrics:
            return

        realized_pnl = Decimal(current_daily_metrics.get("realized_pnl", "0"))
        total_fees = Decimal(current_daily_metrics.get("total_fees", "0"))
        net_realized_pnl = realized_pnl - total_fees

        # Daily PnL Stop Loss
        if self.config.daily_pnl_stop_loss_pct is not None and net_realized_pnl < DECIMAL_ZERO:
            # For simplicity, interpret daily_pnl_stop_loss_pct as a direct percentage of some base capital.
            # A more robust implementation would link this to actual available capital or a specific daily capital target.
            # Example: If daily_pnl_stop_loss_pct = 0.05 (5%), and we assume a base capital of $10000, threshold is $500.
            # Using a simpler interpretation: if net_realized_pnl drops below a certain negative value.
            # Let's scale it relative to the current balance or a large fixed number for demonstration.
            # A more practical approach might be a fixed daily loss limit in USD.
            # For now, we'll use a simple threshold interpretation.
            # Let's use a simplified fixed USD threshold derived from config if balance is not available or large.
            # If balance is available, we could use: threshold_usd = balance * config.daily_pnl_stop_loss_pct
            # For demonstration, let's assume a fixed baseline if balance is not readily used for this check.
            # A better way is to normalize against the starting balance of the day or peak balance.
            
            # Using current balance for relative stop loss:
            current_balance_for_stop = self.get_account_balance() # Fetch latest balance
            if current_balance_for_stop <= 0: current_balance_for_stop = Decimal("10000") # Fallback to a reasonable default if balance is zero or unavailable
            
            loss_threshold_usd = -Decimal(str(self.config.daily_pnl_stop_loss_pct)) * current_balance_for_stop

            if net_realized_pnl <= loss_threshold_usd:
                self.logger.critical(
                    f"{Colors.NEON_RED}# [{self.symbol}] Daily PnL Stop Loss triggered! "
                    f"Net Realized PnL: {net_realized_pnl:+.4f} USD. Stopping trading for this symbol.{Colors.RESET}"
                )
                termux_notify(f"{self.symbol}: DAILY STOP LOSS HIT! {net_realized_pnl:+.2f} USD", is_error=True)
                self.config.trade_enabled = False # Disable trading for this symbol
                self.cancel_all_orders(self.symbol)
                return

        # Daily PnL Take Profit
        if self.config.daily_pnl_take_profit_pct is not None and net_realized_pnl > DECIMAL_ZERO:
            current_balance_for_profit = self.get_account_balance() # Fetch latest balance
            if current_balance_for_profit <= 0: current_balance_for_profit = Decimal("10000") # Fallback
            
            profit_threshold_usd = Decimal(str(self.config.daily_pnl_take_profit_pct)) * current_balance_for_profit
            
            if net_realized_pnl >= profit_threshold_usd:
                self.logger.info(
                    f"{Colors.NEON_GREEN}# [{self.symbol}] Daily PnL Take Profit triggered! "
                    f"Net Realized PnL: {net_realized_pnl:+.4f} USD. Stopping trading for this symbol.{Colors.RESET}"
                )
                termux_notify(f"{self.symbol}: DAILY TAKE PROFIT HIT! {net_realized_pnl:+.2f} USD", is_error=False)
                self.config.trade_enabled = False # Disable trading for this symbol
                self.cancel_all_orders(self.symbol)
                return

    def _check_market_data_freshness(self) -> bool:
        """Checks if WebSocket market data is stale."""
        current_time = time.time()
        symbol_id_ws = self.symbol.replace("/", "").replace(":", "")

        last_ob_update = self.ws_client.last_orderbook_update_time.get(symbol_id_ws, 0)
        last_trades_update = self.ws_client.last_trades_update_time.get(symbol_id_ws, 0)

        if (current_time - last_ob_update > self.config.market_data_stale_timeout_seconds) or \
           (current_time - last_trades_update > self.config.market_data_stale_timeout_seconds):
            self.logger.warning(
                f"[{self.symbol}] Market data is stale! Last OB: {current_time - last_ob_update:.1f}s ago, "
                f"Last Trades: {current_time - last_trades_update:.1f}s ago. Pausing trading."
            )
            termux_notify(f"{self.symbol}: Market data stale! Pausing.", is_error=True)
            return False
        return True

    def run(self):
        """The main ritual loop for the SymbolBot."""
        self.logger.info(f"[{self.symbol}] Pyrmethus SymbolBot ritual initiated.")

        # Initial setup and verification
        if not self._fetch_symbol_info():
            self.logger.critical(f"[{self.symbol}] Failed initial symbol info fetch. Halting bot.")
            termux_notify(f"{self.symbol}: Init failed (symbol info)!", is_error=True)
            return
        if GLOBAL_CONFIG.category == "linear": # Only for perpetuals
            if not self._set_leverage_if_needed():
                self.logger.critical(f"[{self.symbol}] Failed to set leverage. Halting bot.")
                termux_notify(f"{self.symbol}: Init failed (leverage)!", is_error=True)
                return
            if not self._set_margin_mode_and_position_mode():
                self.logger.critical(f"[{self.symbol}] Failed to set margin/position mode. Halting bot.")
                termux_notify(f"{self.symbol}: Init failed (margin mode)!", is_error=True)
                return

        # Main market making loop
        while not self._stop_event.is_set():
            try:
                self._reset_daily_metrics_if_new_day() # Daily PnL reset check

                if not self.config.trade_enabled:
                    self.logger.info(f"[{self.symbol}] Trading disabled for this symbol. Waiting...")
                    self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL)
                    continue
                
                if not self._check_market_data_freshness():
                    self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL)
                    continue

                # Fetch current price and orderbook from WebSocket cache
                symbol_id_ws = self.symbol.replace("/", "").replace(":", "")
                orderbook = self.ws_client.get_order_book_snapshot(symbol_id_ws)
                recent_trades = self.ws_client.get_recent_trades_for_momentum(symbol_id_ws, limit=self.config.momentum_window)

                if not orderbook or not orderbook.get("b") or not orderbook.get("a"):
                    self.logger.warning(f"[{self.symbol}] Order book data not available from WebSocket. Retrying in {MAIN_LOOP_SLEEP_INTERVAL}s.")
                    self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL)
                    continue
                
                # Calculate mid-price from orderbook
                best_bid_price = orderbook["b"][0][0] if orderbook["b"] else Decimal("0")
                best_ask_price = orderbook["a"][0][0] if orderbook["a"] else Decimal("0")
                mid_price = (best_bid_price + best_ask_price) / Decimal("2")

                if mid_price == DECIMAL_ZERO:
                    self.logger.warning(f"[{self.symbol}] Mid-price is zero. Skipping cycle.")
                    self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL)
                    continue

                # Check for sufficient recent trade volume
                # Calculate notional value of recent trades
                total_recent_volume_notional = sum(trade[0] * trade[1] for trade in recent_trades) # price * qty
                if total_recent_volume_notional < Decimal(str(self.config.min_recent_trade_volume)):
                    self.logger.warning(f"[{self.symbol}] Recent trade volume ({total_recent_volume_notional:.2f} USD) below threshold ({self.config.min_recent_trade_volume:.2f} USD). Pausing quoting.")
                    self.cancel_all_orders(self.symbol)
                    self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL)
                    continue

                # Check for funding rate if applicable
                if GLOBAL_CONFIG.category == "linear":
                    funding_rate = self._fetch_funding_rate()
                    if funding_rate is not None and abs(funding_rate) > Decimal(str(self.config.funding_rate_threshold)):
                        self.logger.warning(f"[{self.symbol}] High funding rate ({funding_rate:+.6f}) detected. Cancelling orders to avoid holding position.")
                        self.cancel_all_orders(self.symbol)
                        self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL)
                        continue

                # Check daily PnL limits
                self._check_daily_pnl_limits()
                if not self.config.trade_enabled: # Check again if disabled by PnL limit
                    self.logger.info(f"[{self.symbol}] Trading disabled by daily PnL limit. Waiting...")
                    self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL)
                    continue

                # Check for stale orders and cancel them
                self._check_and_handle_stale_orders()

                # Execute the chosen strategy to generate and place orders
                self.strategy.generate_orders(self.symbol, mid_price, orderbook)
                
                # Update TP/SL for current position (if any)
                self.update_take_profit_stop_loss()

                # Save state periodically
                if time.time() - self.last_order_management_time > STATUS_UPDATE_INTERVAL:
                    self._save_state()
                    self.last_order_management_time = time.time()

                self._stop_event.wait(self.config.order_refresh_time) # Wait for next refresh cycle

            except InvalidOperation as e:
                self.logger.error(f"{Colors.NEON_RED}# [{self.symbol}] Decimal operation error: {e}. Skipping cycle.{Colors.RESET}", exc_info=True)
                self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL)
            except Exception as e:
                self.logger.critical(f"{Colors.NEON_RED}# [{self.symbol}] Unhandled critical error in main loop: {e}{Colors.RESET}", exc_info=True)
                termux_notify(f"{self.symbol}: Critical Error! {str(e)[:50]}", is_error=True)
                self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL * 2) # Longer wait on critical error

    def stop(self):
        """Signals the SymbolBot to gracefully cease its ritual."""
        self.logger.info(f"[{self.symbol}] Signaling SymbolBot to stop...")
        self._stop_event.set()
        # Cancel all open orders when stopping
        self.cancel_all_orders(self.symbol)
        self._save_state() # Final state save


# --- Main Bot Orchestrator ---
class PyrmethusBot:
    """The grand orchestrator, summoning and managing SymbolBots."""
    def __init__(self):
        self.global_config = GLOBAL_CONFIG
        self.symbol_configs = SYMBOL_CONFIGS
        self.exchange = initialize_exchange(main_logger)
        if not self.exchange:
            main_logger.critical(f"{Colors.NEON_RED}# Failed to initialize exchange. Exiting.{Colors.RESET}")
            sys.exit(1)
        
        self.ws_client = BybitWebSocket(
            api_key=BYBIT_API_KEY,
            api_secret=BYBIT_API_SECRET,
            testnet=self.exchange.options.get("testnet", False), # Use testnet status from exchange config
            logger=main_logger
        )
        self.active_symbol_bots: Dict[str, SymbolBot] = {}
        self._main_stop_event = threading.Event() # Event for the main bot loop to stop

    def _setup_signal_handlers(self):
        """Sets up signal handlers for graceful shutdown."""
        # Handle SIGINT (Ctrl+C) and SIGTERM (termination signal)
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)
        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
        main_logger.info(f"{Colors.CYAN}# Signal handlers for graceful shutdown attuned.{Colors.RESET}")

    def _handle_shutdown_signal(self, signum, frame):
        """Handles OS signals for graceful shutdown."""
        main_logger.info(f"{Colors.YELLOW}\\n# Ritual interrupted by seeker (Signal {signum}). Initiating final shutdown sequence...{Colors.RESET}")
        self._main_stop_event.set() # Signal the main loop to stop

    def run(self):
        """Initiates the grand market-making ritual."""
        self._setup_signal_handlers()

        # Start WebSocket streams
        # Public topics for order book and trades for all configured symbols
        public_topics = [f"orderbook.50.{s.symbol.replace('/', '').replace(':', '')}" for s in self.symbol_configs] + \
                        [f"publicTrade.{s.symbol.replace('/', '').replace(':', '')}" for s in self.symbol_configs]
        private_topics = ["order", "execution", "position"] # Wallet can be added if needed
        self.ws_client.start_streams(public_topics, private_topics)
        
        # Launch SymbolBots for each configured symbol, respecting Termux limits
        active_bots_count = 0
        for s_config in self.symbol_configs:
            if active_bots_count >= self.global_config.max_symbols_termux:
                main_logger.warning(f"{Colors.YELLOW}# Max symbols ({self.global_config.max_symbols_termux}) reached for Termux. Skipping {s_config.symbol}.{Colors.RESET}")
                continue
            
            main_logger.info(f"{Colors.CYAN}# Summoning SymbolBot for {s_config.symbol}...{Colors.RESET}")
            bot_logger = setup_logger(f"symbol_{s_config.symbol.replace('/', '_').replace(':', '')}")
            bot = SymbolBot(s_config, self.exchange, self.ws_client, bot_logger)
            self.active_symbol_bots[s_config.symbol] = bot
            bot.start() # Start the SymbolBot thread
            active_bots_count += 1

        main_logger.info(f"{Colors.NEON_GREEN}# Pyrmethus Market Maker Bot is now weaving its magic across {len(self.active_symbol_bots)} symbols.{Colors.RESET}")
        termux_notify(f"Bot started for {len(self.active_symbol_bots)} symbols!", title="Pyrmethus Bot Online")

        # Keep main thread alive until shutdown signal
        while not self._main_stop_event.is_set():
            time.sleep(1) # Small sleep to prevent busy-waiting

        self.shutdown()

    def shutdown(self):
        """Performs a graceful shutdown of all bot components."""
        main_logger.info(f"{Colors.YELLOW}# Initiating graceful shutdown of all SymbolBots...{Colors.RESET}")
        # Iterate over a copy of the dictionary keys to allow modification during iteration
        for symbol in list(self.active_symbol_bots.keys()):
            bot = self.active_symbol_bots[symbol]
            bot.stop()
            bot.join(timeout=10) # Wait for bot thread to finish
            if bot.is_alive():
                main_logger.warning(f"{Colors.NEON_ORANGE}# SymbolBot for {symbol} did not terminate gracefully.{Colors.RESET}")
            else:
                main_logger.info(f"{Colors.CYAN}# SymbolBot for {symbol} has ceased its ritual.{Colors.RESET}")
        
        main_logger.info(f"{Colors.YELLOW}# Extinguishing WebSocket streams...{Colors.RESET}")
        self.ws_client.stop_streams()

        main_logger.info(f"{Colors.NEON_GREEN}# Pyrmethus Market Maker Bot has completed its grand ritual. Farewell, seeker.{Colors.RESET}")
        termux_notify("Bot has shut down.", title="Pyrmethus Bot Offline")
        sys.exit(0)


# --- Main Execution Block ---
if __name__ == "__main__":
    # Ensure logs directory exists
    if not LOG_DIR.exists():
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            main_logger.info(f"Created log directory: {LOG_DIR}")
        except OSError as e:
            main_logger.critical(f"Failed to create log directory {LOG_DIR}: {e}")
            sys.exit(1)

    # Ensure state directory exists
    if not STATE_DIR.exists():
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            main_logger.info(f"Created state directory: {STATE_DIR}")
        except OSError as e:
            main_logger.critical(f"Failed to create state directory {STATE_DIR}: {e}")
            sys.exit(1)

    # Create a default symbol config file if it doesn't exist
    config_file_path = Path(GLOBAL_CONFIG.symbol_config_file) # Use Path object from global config
    if not config_file_path.exists():
        default_config_content = [
            {
                "symbol": "BTC/USDT:USDT", # Example symbol, ensure this matches Bybit's format for CCXT
                "trade_enabled": True,
                "base_spread": 0.001,
                "order_amount": 0.001,
                "leverage": 10.0,
                "order_refresh_time": 10,
                "max_spread": 0.005,
                "inventory_limit": 0.01,
                "dynamic_spread": {"enabled": True, "volatility_multiplier": 0.5, "atr_update_interval": 300},
                "inventory_skew": {"enabled": True, "skew_factor": 0.1, "max_skew": 0.0005}, # Added max_skew
                "momentum_window": 10,
                "take_profit_percentage": 0.002,
                "stop_loss_percentage": 0.001,
                "inventory_sizing_factor": 0.5,
                "min_liquidity_depth": 1000.0,
                "depth_multiplier": 2.0,
                "imbalance_threshold": 0.3,
                "slippage_tolerance_pct": 0.002,
                "funding_rate_threshold": 0.0005,
                "max_symbols_termux": 1,
                "min_recent_trade_volume": 0.0,
                "trading_hours_start": None,
                "trading_hours_end": None,
                "enable_auto_sl_tp": True,
                "take_profit_target_pct": 0.005,
                "stop_loss_trigger_pct": 0.005,
                "use_batch_orders_for_refresh": True,
                "recent_fill_rate_window": 60,
                "cancel_partial_fill_threshold_pct": 0.15,
                "stale_order_max_age_seconds": 300,
                "momentum_trend_threshold": 0.0001,
                "max_capital_at_risk_usd": 0.0,
                "market_data_stale_timeout_seconds": 30,
                "kline_interval": "1m" # Added for ATR calculation
            }
        ]
        try:
            with open(config_file_path, "w") as f:
                json.dump(default_config_content, f, indent=4, cls=JsonDecimalEncoder)
            main_logger.info(f"{Colors.NEON_GREEN}Created default symbol config file: {config_file_path}{Colors.RESET}")
            main_logger.info(f"{Colors.YELLOW}Please review and adjust {config_file_path} with your desired symbols and settings.{Colors.RESET}")
            # It might be better not to exit, but let the user know and proceed with default if symbols.json is missing.
            # However, for initial setup, exiting to prompt user to create config is safer.
            # sys.exit(0) # Exit to allow user to edit config
        except Exception as e:
            main_logger.critical(f"{Colors.NEON_RED}Error creating default config file: {e}{Colors.RESET}", exc_info=True)
            sys.exit(1)

    try:
        bot = PyrmethusBot()
        bot.run()
    except KeyboardInterrupt:
        main_logger.info(f"{Colors.YELLOW}\\n# Ritual interrupted by seeker. Initiating final shutdown sequence...{Colors.RESET}")
        # The signal handler in PyrmethusBot will take care of shutdown
    except Exception as e:
        main_logger.critical(f"{Colors.NEON_RED}An unhandled critical error occurred in main execution: {e}{Colors.RESET}", exc_info=True)
        termux_notify(f"Critical Bot Error: {str(e)[:50]}", is_error=True)
        sys.exit(1)
```
Google Search Suggestions
Display of Search Suggestions is required when using Grounding with Google Search. Learn more
Bybit V5 API ccxt python example
ccxt python bybit V5 market making strategy
pybit market making bot example
python ccxt trailing stop loss implementation
python ccxt order book analysis for market making
python ccxt dynamic spread calculation ATR
python ccxt inventory management for market making
python ccxt state persistence
python ccxt WebSocket integration example
python ccxt error handling and retries
python ccxt PnL calculation
python ccxt funding rate handling
python ccxt order management batch operations
python ccxt orderbook depth analysis for market making
python ccxt orderbook imbalance calculation
python ccxt orderbook depth multiplier
python ccxt orderbook minimum liquidity per level
python ccxt orderbook stale order detection
python ccxt orderbook momentum trend threshold
python ccxt orderbook slippage tolerance
python ccxt orderbook cancel partial fill threshold
python ccxt orderbook trading hours
python ccxt orderbook minimum order value
python ccxt orderbook maximum capital allocation per order
python ccxt orderbook ATR quantity multiplier
python ccxt orderbook enable auto SL/TP
python ccxt orderbook take profit target percentage
python ccxt orderbook stop loss trigger percentage
python ccxt orderbook use batch orders for refresh
python ccxt orderbook recent fill rate window
python ccxt orderbook stale order max age seconds
python ccxt orderbook max capital at risk usd
python ccxt market data stale timeout seconds
python ccxt API retry attempts
python ccxt API retry backoff factor
python ccxt WebSocket reconnect interval
python ccxt symbol info refresh interval
python ccxt status update interval
python ccxt main loop sleep interval
python ccxt decimal zero
python ccxt minimum trade PnL percentage
python ccxt initialize exchange
python ccxt ATR calculation
python ccxt retry API call decorator
python ccxt BybitWebSocket class
python ccxt BybitWebSocket _on_message
python ccxt BybitWebSocket _normalize_symbol_ws
python ccxt BybitWebSocket _process_public_message
python ccxt BybitWebSocket _process_private_message
python ccxt BybitWebSocket _update_order_book
python ccxt BybitWebSocket get_order_book_snapshot
python ccxt BybitWebSocket get_recent_trades_for_momentum
python ccxt BybitWebSocket _on_error
python ccxt BybitWebSocket _on_close
python ccxt BybitWebSocket _on_open
python ccxt BybitWebSocket _connect_websocket
python ccxt BybitWebSocket start_streams
python ccxt BybitWebSocket stop_streams
python ccxt MarketMakerStrategy class
python ccxt MarketMakerStrategy generate_orders
python ccxt SymbolBot class
python ccxt SymbolBot _load_state
python ccxt SymbolBot _save_state
python ccxt SymbolBot _reset_daily_metrics_if_new_day
python ccxt SymbolBot _fetch_symbol_info
python ccxt SymbolBot _set_leverage_if_needed
python ccxt SymbolBot _set_margin_mode_and_position_mode
python ccxt SymbolBot _fetch_funding_rate
python ccxt SymbolBot _handle_order_update
python ccxt SymbolBot _handle_position_update
python ccxt SymbolBot _handle_execution_update
python ccxt SymbolBot _close_profitable_entities
python ccxt SymbolBot _calculate_atr
python ccxt SymbolBot _calculate_inventory_skew
python ccxt SymbolBot get_dynamic_order_amount
python ccxt SymbolBot _round_to_precision
python ccxt SymbolBot place_batch_orders
python ccxt SymbolBot cancel_all_orders
python ccxt SymbolBot cancel_order
python ccxt SymbolBot update_take_profit_stop_loss
python ccxt SymbolBot _check_and_handle_stale_orders
python ccxt SymbolBot _check_daily_pnl_limits
python ccxt SymbolBot _check_market_data_freshness
python ccxt SymbolBot run
python ccxt SymbolBot stop
python ccxt PyrmethusBot class
python ccxt PyrmethusBot _setup_signal_handlers
python ccxt PyrmethusBot _handle_shutdown_signal
python ccxt PyrmethusBot run
python ccxt PyrmethusBot shutdown
python ccxt main execution block
python ccxt default symbol config file creation
python ccxt termux notification setup
