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
from decimal import Decimal, getcontext, ROUND_DOWN, ROUND_UP, InvalidOperation, ROUND_HALF_UP
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
        PositiveInt,
    )
    # Check for python-dotenv specifically
    try:
        from dotenv import load_dotenv
        DOTENV_AVAILABLE = True
    except ImportError:
        DOTENV_AVAILABLE = False
    
    EXTERNAL_LIBS_AVAILABLE = True
except ImportError as e:
    # Provide a clear message if essential libraries are missing
    print(f"{Fore.RED}Error: Missing required library: {e}. Please install it using pip.{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Install all dependencies with: pip install ccxt pandas requests websocket-client pydantic colorama python-dotenv{Style.RESET_ALL}")
    EXTERNAL_LIBS_AVAILABLE = False
    DOTENV_AVAILABLE = False # No dotenv if other libs are missing

    # Define dummy classes/functions to allow the script to load without immediate crashes,
    # but operations requiring these libraries will fail.
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
    class Style:
        BRIGHT = RESET_ALL = ""
    def init(autoreset=True): pass # Dummy init for colorama
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
    class field: pass
    class dataclass: pass
    class sys: pass
    class os: pass
    class hashlib: pass
    class hmac: pass
    class json: pass
    class logging: pass
    class PositiveInt(int): pass # Dummy for Pydantic type


# --- Initialize the terminal's chromatic essence ---
if EXTERNAL_LIBS_AVAILABLE:
    init(autoreset=True)
else:
    print("Colorama not available. Output will not be colored.")


# --- Weaving in Environment Secrets ---
if DOTENV_AVAILABLE:
    load_dotenv()
    if EXTERNAL_LIBS_AVAILABLE:
        print(f"{Fore.CYAN}# Secrets from the .env scroll have been channeled.{Style.RESET_ALL}")
else:
    if EXTERNAL_LIBS_AVAILABLE:
        print(f"{Fore.YELLOW}Warning: 'python-dotenv' not found. Install with: pip install python-dotenv{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Environment variables will not be loaded from .env file.{Style.RESET_ALL}")
    else:
        print("Warning: python-dotenv not available (due to missing dependencies). Environment variables will not be loaded from .env file.")


# --- Global Constants and Configuration ---
if EXTERNAL_LIBS_AVAILABLE:
    getcontext().prec = 38  # High precision for all magical calculations

class Colors:
    """ANSI escape codes for enchanted terminal output with a neon theme."""
    if EXTERNAL_LIBS_AVAILABLE:
        CYAN = Fore.CYAN + Style.BRIGHT
        MAGENTA = Fore.MAGENTA + Style.BRIGHT
        YELLOW = Fore.YELLOW + Style.BRIGHT
        RESET = Style.RESET_ALL
        NEON_GREEN = Fore.GREEN + Style.BRIGHT
        NEON_BLUE = Fore.BLUE + Style.BRIGHT
        NEON_RED = Fore.RED + Style.BRIGHT
        NEON_ORANGE = Fore.LIGHTRED_EX + Style.BRIGHT
    else: # Dummy colors if Colorama is not available
        CYAN = MAGENTA = YELLOW = NEON_GREEN = NEON_BLUE = NEON_RED = NEON_ORANGE = RESET = ""


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
DECIMAL_ZERO = Decimal("0") if EXTERNAL_LIBS_AVAILABLE else 0
MIN_TRADE_PNL_PERCENT = Decimal("-0.0005") if EXTERNAL_LIBS_AVAILABLE else -0.0005 # Don't open new trades if current position is worse than -0.05% PnL

# --- Pydantic Models for Configuration and State ---
if EXTERNAL_LIBS_AVAILABLE:
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

    class Trade(BaseModel):
        """Represents a single trade execution (fill event)."""
        side: str
        qty: Decimal
        price: Decimal
        profit: Decimal = DECIMAL_ZERO # Realized profit from this specific execution
        timestamp: int
        fee: Decimal
        trade_id: str
        entry_price: Optional[Decimal] = None # Entry price of the position at the time of trade
        model_config = ConfigDict(json_dumps=lambda v: json.dumps(v, cls=JsonDecimalEncoder), json_loads=json_loads_decimal, validate_assignment=True)

    class DynamicSpreadConfig(BaseModel):
        """Configuration for dynamic spread adjustment based on volatility (e.g., ATR)."""
        enabled: bool = True
        volatility_multiplier: PositiveFloat = 0.5
        atr_update_interval: NonNegativeInt = 300

    class InventorySkewConfig(BaseModel):
        """Configuration for skewing orders based on current inventory."""
        enabled: bool = True
        skew_factor: PositiveFloat = 0.1
        # Added max_skew to prevent extreme adjustments
        max_skew: Optional[PositiveFloat] = None

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
        kline_interval: str = "1m" # Default kline interval for ATR calculation

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
        def load_config(cls, prompt_for_symbol: bool = False, input_symbol: Optional[str] = None) -> Tuple[GlobalConfig, List[SymbolConfig]]:
            """
            Loads global and symbol-specific configurations.
            If prompt_for_symbol is True and input_symbol is provided, it creates a single
            SymbolConfig on-the-fly using global defaults.
            """
            # This check might prevent reloading if called multiple times without explicit need
            # However, for periodic config refresh, we always want to reload from file
            # if cls._global_config and cls._symbol_configs and not (prompt_for_symbol or input_symbol):
            #     return cls._global_config, cls._symbol_configs

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

            cls._symbol_configs = []
            if prompt_for_symbol and input_symbol:
                # Create a single SymbolConfig from default global values and input_symbol
                # Use default_factory for nested fields if they are not explicitly provided
                single_symbol_data = {
                    "symbol": input_symbol,
                    "trade_enabled": True, # Always enable for interactive session
                    "base_spread": cls._global_config.min_profitable_spread_pct * 2,
                    "order_amount": cls._global_config.default_order_amount,
                    "leverage": cls._global_config.default_leverage,
                    "order_refresh_time": cls._global_config.api_retry_delay * 5,
                    "max_spread": cls._global_config.default_max_spread,
                    "inventory_limit": cls._global_config.default_order_amount * 10,
                    "dynamic_spread": DynamicSpreadConfig(enabled=True, volatility_multiplier=cls._global_config.default_atr_multiplier, atr_update_interval=300),
                    "inventory_skew": InventorySkewConfig(enabled=True, skew_factor=cls._global_config.default_skew_factor, max_skew=0.0005),
                    "min_order_value_usd": 10.0,
                    "kline_interval": "1m", # Default for interactive symbol
                    "order_layers": [OrderLayer(spread_offset=0.0, quantity_multiplier=1.0, cancel_threshold_pct=0.01)],
                    "min_recent_trade_volume": 0.0, # Default for dynamic config
                    "market_data_stale_timeout_seconds": 30 # Default for dynamic config
                    # ... other default parameters needed for SymbolConfig, ensure all are covered
                }
                try:
                    cls._symbol_configs.append(SymbolConfig(**single_symbol_data))
                    cls._global_config.max_symbols_termux = 1 # Limit to 1 for interactive
                    main_logger.info(f"[{Colors.CYAN}Using single symbol mode for {input_symbol}.{Colors.RESET}]")
                except ValidationError as e:
                    logging.critical(f"Input symbol configuration validation error for {input_symbol}: {e}")
                    sys.exit(1)
            else:
                # Load symbol configurations from file as usual
                raw_symbol_configs = []
                try:
                    symbol_config_path = Path(cls._global_config.symbol_config_file)
                    with open(symbol_config_path, 'r') as f:
                        raw_symbol_configs = json.load(f)
                    if not isinstance(raw_symbol_configs, list):
                        raise ValueError("Symbol configuration file must contain a JSON list.")
                except FileNotFoundError:
                    logging.critical(f"Symbol configuration file '{cls._global_config.symbol_config_file}' not found. Please create it or use single symbol mode.")
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

                for s_cfg in raw_symbol_configs:
                    try:
                        # Merge with global defaults before validation
                        merged_config_data = {
                            "base_spread": cls._global_config.min_profitable_spread_pct * 2,
                            "order_amount": cls._global_config.default_order_amount,
                            "leverage": cls._global_config.default_leverage,
                            "order_refresh_time": cls._global_config.api_retry_delay * 5,
                            "max_spread": cls._global_config.default_max_spread,
                            "inventory_limit": cls._global_config.default_order_amount * 10,
                            "min_profitable_spread_pct": cls._global_config.min_profitable_spread_pct,
                            "depth_range_pct": cls._global_config.depth_range_pct,
                            "slippage_tolerance_pct": cls._global_config.slippage_tolerance_pct,
                            "funding_rate_threshold": cls._global_config.funding_rate_threshold,
                            "max_symbols_termux": cls._global_config.max_symbols_termux,
                            "min_recent_trade_volume": 0.0,
                            "trading_hours_start": None,
                            "trading_hours_end": None,
                            "enable_auto_sl_tp": False,
                            "take_profit_target_pct": 0.005,
                            "stop_loss_trigger_pct": 0.005,
                            "use_batch_orders_for_refresh": cls._global_config.use_batch_orders_for_refresh,
                            "recent_fill_rate_window": 60,
                            "cancel_partial_fill_threshold_pct": 0.15,
                            "stale_order_max_age_seconds": 300,
                            "momentum_trend_threshold": 0.0001,
                            "max_capital_at_risk_usd": 0.0,
                            "market_data_stale_timeout_seconds": 30,
                            "kline_interval": "1m", # Default for ATR calculation

                            "dynamic_spread": DynamicSpreadConfig(**s_cfg.get("dynamic_spread", {})) if isinstance(s_cfg.get("dynamic_spread"), dict) else s_cfg.get("dynamic_spread", DynamicSpreadConfig()),
                            "inventory_skew": InventorySkewConfig(**s_cfg.get("inventory_skew", {})) if isinstance(s_cfg.get("inventory_skew"), dict) else s_cfg.get("inventory_skew", InventorySkewConfig()),
                            "order_layers": [OrderLayer(**ol) if isinstance(ol, dict) else ol for ol in s_cfg.get("order_layers", [OrderLayer()])] if isinstance(s_cfg.get("order_layers"), list) else s_cfg.get("order_layers", [OrderLayer()]),

                            **s_cfg
                        }
                        
                        # Ensure nested models are Pydantic objects before passing to SymbolConfig
                        if isinstance(merged_config_data.get("dynamic_spread"), dict):
                            merged_config_data["dynamic_spread"] = DynamicSpreadConfig(**merged_config_data["dynamic_spread"])
                        if isinstance(merged_config_data.get("inventory_skew"), dict):
                            merged_config_data["inventory_skew"] = InventorySkewConfig(**merged_config_data["inventory_skew"])
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
else: # Dummy ConfigManager if EXTERNAL_LIBS_AVAILABLE is False
    class ConfigManager:
        @classmethod
        def load_config(cls, prompt_for_symbol: bool = False, input_symbol: Optional[str] = None) -> Tuple[Any, List[Any]]: # Return Any types
            print(f"{Fore.RED}Configuration management skipped due to missing external libraries.{Style.RESET_ALL}")
            sys.exit(1)


# Load configs immediately upon module import
GLOBAL_CONFIG = None
SYMBOL_CONFIGS = []
if EXTERNAL_LIBS_AVAILABLE:
    # Initial load will be empty, actual load happens after prompt
    pass 

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

    # Ensure GLOBAL_CONFIG is loaded before accessing its attributes
    log_level_str = GLOBAL_CONFIG.log_level.upper() if GLOBAL_CONFIG else "INFO"
    logger.setLevel(getattr(logging, log_level_str, logging.INFO))

    log_file_path = LOG_DIR / (GLOBAL_CONFIG.log_file if GLOBAL_CONFIG else "market_maker_live.log")

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

# Global logger instance for main operations (will be properly set up if libs available)
main_logger = logging.getLogger("market_maker_main")
if EXTERNAL_LIBS_AVAILABLE:
    # This ensures main_logger is configured even before PyrmethusBot is instantiated.
    # We call setup_logger here with dummy GLOBAL_CONFIG for early access if needed,
    # then later PyrmethusBot re-initializes it with proper GLOBAL_CONFIG.
    # For initial module load, GLOBAL_CONFIG is None, so we set a basic logger.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    main_logger = logging.getLogger("market_maker_main_fallback")


def termux_notify(message: str, title: str = "Pyrmethus Bot", is_error: bool = False):
    """Channels notifications through the Termux API with neon colors."""
    if not EXTERNAL_LIBS_AVAILABLE:
        main_logger.debug("Termux notification skipped: External libraries not available.")
        return
    
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
        main_logger.debug(f"Termux notification failed: {e}")
    except Exception as e:
        main_logger.warning(f"Unexpected error with Termux notification: {e}")


def initialize_exchange(logger: logging.Logger) -> Optional[Any]: # Return Any for ccxt.Exchange
    """Conjures the Bybit V5 exchange instance."""
    if not EXTERNAL_LIBS_AVAILABLE:
        logger.critical(f"{Colors.NEON_RED}Exchange initialization skipped: External libraries not available.{Colors.RESET}")
        return None
    
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


if EXTERNAL_LIBS_AVAILABLE:
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
        """Calculates the Average True Range, a measure of market volatility."""
        tr = pd.DataFrame()
        tr["h_l"] = high - low
        tr["h_pc"] = (high - close.shift(1)).abs()
        tr["l_pc"] = (low - close.shift(1)).abs()
        tr["tr"] = tr[["h_l", "h_pc", "l_pc"]].max(axis=1)
        return tr["tr"].rolling(window=length).mean()
else:
    def atr(high: Any, low: Any, close: Any, length: int = 14) -> Any: # Dummy atr
        return [DECIMAL_ZERO]


def retry_api_call(
    attempts: int = API_RETRY_ATTEMPTS,
    backoff_factor: float = RETRY_BACKOFF_FACTOR,
    fatal_exceptions: Tuple[type, ...] = (ccxt.AuthenticationError, ccxt.ArgumentsRequired, ccxt.ExchangeError) if EXTERNAL_LIBS_AVAILABLE else (Exception,),
):
    """A spell to retry API calls with exponential backoff."""

    def decorator(func: Callable[..., Any]):
        @wraps(func)
        def wrapper(self, *args: Any, **kwargs: Any) -> Any:
            if not EXTERNAL_LIBS_AVAILABLE:
                self.logger.critical(f"{Colors.NEON_RED}API call '{func.__name__}' skipped: External libraries not available.{Colors.RESET}")
                return None
            
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
            # Trade stream usually requires authentication, and subscriptions are sent after.
            # However, the current code structure doesn't explicitly subscribe to `trade_subscriptions` here.
            # If `trade_subscriptions` are meant to be for private topics on the trade stream,
            # then authentication might be needed here too, similar to `is_private` block.
            # For simplicity, assuming no direct subscriptions are needed on `ws_trade` initially.
            if self.api_key and self.api_secret:
                auth_params = self._generate_auth_params()
                self.logger.debug(f"Sending auth message to Trade WS: {auth_params}")
                ws.send(json.dumps(auth_params))
                # If there are specific trade topics (e.g., execution, order) that only work on this stream,
                # they should be subscribed here after auth.
                # For now, these topics are handled by the 'private' stream.
                ws.call_later(0.5, lambda: ws.send(json.dumps({"op": "subscribe", "args": self.trade_subscriptions})))
            else:
                self.logger.warning(f"{Colors.YELLOW}# Trade WebSocket streams not started due to missing API keys (if private topics).{Colors.RESET}")
        elif is_private:
            self.ws_private = ws
            if self.api_key and self.api_secret:
                auth_params = self._generate_auth_params()
                self.logger.debug(f"Sending auth message to Private WS: {auth_params}")
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
                self.logger.info(f"Attempting to connect WebSocket for {url}...")
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

    def start_streams(self, public_topics: List[str], private_topics: Optional[List[str]] = None, trade_topics: Optional[List[str]] = None):
        """Starts public, private, and trade WebSocket streams."""
        if not EXTERNAL_LIBS_AVAILABLE:
            self.logger.critical(f"{Colors.NEON_RED}WebSocket streams skipped: External libraries not available.{Colors.RESET}")
            return
        
        # Ensure previous streams are fully stopped before starting new ones
        self.stop_streams() # This also sets _stop_event, so clear it for new threads
        self._stop_event.clear()

        self.public_subscriptions = public_topics
        self.private_subscriptions = private_topics or []
        self.trade_subscriptions = trade_topics or [] # Assign trade topics

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
        # If trade_topics are passed, this stream will attempt to subscribe to them.
        self.trade_thread = threading.Thread(target=self._connect_websocket, args=(self.trade_url, False, True), daemon=True, name="TradeWSThread")
        self.trade_thread.start()

        self.logger.info(f"{Colors.NEON_GREEN}# WebSocket streams have been summoned.{Colors.RESET}")

    def stop_streams(self):
        """Stops all WebSocket streams gracefully."""
        if not EXTERNAL_LIBS_AVAILABLE:
            return # Nothing to stop if not started
        
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
    """Base class for market making strategies."""
    def __init__(self, bot: 'SymbolBot'):
        self.bot = bot
        self.logger = bot.logger # Use the bot's contextual logger

    def generate_orders(self, symbol: str, mid_price: Decimal, orderbook: Dict[str, Any]):
        """Generates and places market making orders based on strategy logic."""
        self.logger.info(f"[{symbol}] Generating orders using MarketMakerStrategy.")

        # Cancel all existing orders before placing new ones
        self.bot.cancel_all_orders(symbol)
        time.sleep(0.5) # Give API a moment to process cancellations

        orders_to_place: List[Dict[str, Any]] = []
        
        # Calculate dynamic order quantity
        current_order_qty = self.bot.get_dynamic_order_amount(mid_price)

        if current_order_qty <= DECIMAL_ZERO:
            self.logger.warning(f"[{symbol}] Calculated order quantity is zero or negative. Skipping order placement.")
            return

        price_precision = self.bot.config.price_precision
        qty_precision = self.bot.config.qty_precision

        # Calculate dynamic spread based on ATR and inventory skew
        dynamic_spread_pct = Decimal(str(self.bot.config.base_spread))
        if self.bot.config.dynamic_spread.enabled:
            atr_component = self.bot._calculate_atr(mid_price)
            dynamic_spread_pct += atr_component
            self.logger.debug(f"[{symbol}] ATR component for spread: {atr_component:.8f}")

        if self.bot.config.inventory_skew.enabled:
            inventory_skew_component = self.bot._calculate_inventory_skew(mid_price)
            dynamic_spread_pct += inventory_skew_component
            self.logger.debug(f"[{symbol}] Inventory skew component for spread: {inventory_skew_component:.8f}")

        # Ensure spread does not exceed max_spread
        dynamic_spread_pct = min(dynamic_spread_pct, Decimal(str(self.bot.config.max_spread)))

        self.logger.info(f"[{symbol}] Dynamic Spread: {dynamic_spread_pct * 100:.4f}%")

        # Check for sufficient liquidity at desired price levels
        bids = orderbook.get("b", [])
        asks = orderbook.get("a", [])

        # Calculate cumulative depth for bids and asks
        cumulative_bids = []
        current_cumulative_qty = DECIMAL_ZERO
        for price, qty in bids:
            current_cumulative_qty += qty
            cumulative_bids.append({"price": price, "cumulative_qty": current_cumulative_qty})

        cumulative_asks = []
        current_cumulative_qty = DECIMAL_ZERO
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
                self.logger.warning(f"[{symbol}] Insufficient bid liquidity for layer {i+1} at price {bid_price:.{price_precision if price_precision is not None else 8}f}. Skipping bid order.")
            elif bid_qty > DECIMAL_ZERO:
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
                self.logger.warning(f"[{symbol}] Insufficient ask liquidity for layer {i+1} at price {sell_price:.{price_precision if price_precision is not None else 8}f}. Skipping ask order.")
            elif sell_qty > DECIMAL_ZERO:
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
    def __init__(self, config: SymbolConfig, exchange: Any, ws_client: BybitWebSocket, logger: logging.Logger):
        super().__init__(name=f"SymbolBot-{config.symbol.replace('/', '_').replace(':', '')}")
        self.config: SymbolConfig = config
        self.exchange: Any = exchange # ccxt.Exchange type
        self.ws_client: BybitWebSocket = ws_client
        self.logger: logging.Logger = logger
        self.symbol: str = config.symbol
        self._stop_event: threading.Event = threading.Event() # Controls the lifecycle of this SymbolBot's thread
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
        self.state_file: Path = STATE_DIR / f"{self.symbol.replace('/', '_').replace(':', '')}_state.json"
        self._load_state() # Summon memories from the past
        with self.ws_client.lock: self.ws_client.symbol_bots.append(self) # Register with WS client for message routing
        self.last_order_management_time: float = 0.0
        self.last_fill_time: float = 0.0 # For initial_position_grace_period_seconds
        self.fill_tracker: List[bool] = [] # Track recent fills for fill rate calculation
        self.today_date: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.daily_metrics: Dict[str, Any] = {} # For daily PnL tracking
        self.pnl_history_snapshots: List[Dict[str, Any]] = [] # For visualization
        self.trade_history: List[Trade] = [] # For visualization
        self.open_positions: List[Trade] = [] # For granular PnL tracking (FIFO)
        self.strategy: MarketMakerStrategy = MarketMakerStrategy(self) # Initialize strategy

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
                        except (ValidationError, TypeError, InvalidOperation) as e: self.logger.error(f"[{self.symbol}] Error loading trade from state: {e}")
                    
                    for date_str, daily_metric_dict in state_data.get("daily_metrics", {}).items():
                        # Convert Decimal values back from string for daily_metric_dict
                        converted_daily_metric_dict = {k: Decimal(v) if isinstance(v, str) and v.replace('.', '', 1).isdigit() else v for k, v in daily_metric_dict.items()}
                        self.daily_metrics[date_str] = converted_daily_metric_dict
                    
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
            # Convert Decimal values in daily_metrics to string for JSON serialization
            daily_metrics_serializable = {}
            for date, metrics in self.daily_metrics.items():
                daily_metrics_serializable[date] = {k: str(v) if isinstance(v, Decimal) else v for k, v in metrics.items()}

            state_data = {
                "performance_metrics": {k: str(v) if isinstance(v, Decimal) else v for k, v in self.performance_metrics.items()},
                "trade_history": [trade.model_dump() for trade in self.trade_history],
                "daily_metrics": daily_metrics_serializable,
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
                self.daily_metrics[self.today_date]["unrealized_pnl_snapshot"] = self.unrealized_pnl # Snapshot UPL at day end
            self.today_date = current_utc_date
            self.daily_metrics.setdefault(self.today_date, {"date": self.today_date, "realized_pnl": DECIMAL_ZERO, "unrealized_pnl_snapshot": DECIMAL_ZERO, "total_fees": DECIMAL_ZERO, "trades_count": 0})


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
                else DECIMAL_ZERO # Default to 0 if not specified
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
                else DECIMAL_ZERO # Default to 0 if not specified
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
                for p in positions_info: # Use positions_info, not 'positions' which might be undefined
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
            funding_rates = self.exchange.fetch_funding_rate(self.symbol)
            
            if funding_rates and funding_rates.get("info") and funding_rates["info"].get("list"):
                funding_rate_str = funding_rates["info"]["list"][0].get("fundingRate", "0") 
                funding_rate = Decimal(str(funding_rate_str))
                self.logger.debug(f"[{self.symbol}] Fetched funding rate: {funding_rate}")
                return funding_rate
            elif funding_rates and funding_rates.get("rate") is not None:
                 funding_rate = Decimal(str(funding_rates.get("rate")))
                 self.logger.debug(f"[{self.symbol}] Fetched funding rate (fallback): {funding_rate}")
                 return funding_rate
            else:
                self.logger.warning(f"[{self.symbol}] No funding rate found for {self.symbol}.")
                return DECIMAL_ZERO
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# Error fetching funding rate for {self.symbol}: {e}{Colors.RESET}", exc_info=True)
            return DECIMAL_ZERO # Return zero if error occurs

    def _handle_order_update(self, order_data: Dict[str, Any]):
        """Processes order updates received from WebSocket."""
        order_id = order_data.get("orderId")
        client_order_id = order_data.get("orderLinkId")
        status = order_data.get("orderStatus")

        normalized_symbol_data = self._normalize_symbol_ws(order_data.get("symbol", ""))
        if normalized_symbol_data != self.symbol:
            self.logger.debug(
                f"[{self.symbol}] Received order update for different symbol "
                f"{normalized_symbol_data}. Skipping."
            )
            return

        with self.ws_client.lock:
            tracked_order_id = client_order_id if client_order_id else order_id

            if status == "Filled":
                qty = Decimal(str(order_data.get("cumExecQty", "0")))
                price = Decimal(str(order_data.get("avgPrice", order_data.get("price", "0"))))
                fee = Decimal(str(order_data.get("cumExecFee", "0")))
                side = order_data.get("side").lower()

                trade_profit = DECIMAL_ZERO 

                trade = Trade(
                    side=side,
                    qty=qty,
                    price=price,
                    profit=trade_profit,
                    timestamp=int(order_data.get("updatedTime", time.time() * 1000)),
                    fee=fee,
                    trade_id=order_id,
                    entry_price=self.entry_price,
                )

                self.trade_history.append(trade)
                self.performance_metrics["trades"] += 1
                self.performance_metrics["fees"] += fee

                self.logger.info(
                    f"{Colors.NEON_GREEN}[{self.symbol}] Market making trade executed: "
                    f"{side.upper()} {qty:.{self.config.qty_precision if self.config.qty_precision is not None else 8}f} @ {price:.{self.config.price_precision if self.config.price_precision is not None else 8}f}, "
                    f"Fee: {fee:.8f}{Colors.RESET}"
                )
                termux_notify(
                    f"{self.symbol}: {side.upper()} {qty:.4f} @ {price:.4f} (Fee: {fee:.8f})",
                    title="Trade Executed",
                )
                self.last_fill_time = time.time()
                self.fill_tracker.append(True)

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
                        self.fill_tracker.append(False)
                else:
                    self.logger.debug(f"[{self.symbol}] Received status '{status}' for untracked order {tracked_order_id}.")
            else:
                if tracked_order_id in self.open_orders:
                    self.open_orders[tracked_order_id]["status"] = status
                self.logger.debug(f"[{self.symbol}] Order {tracked_order_id} status update: {status}")

    def _handle_position_update(self, pos_data: Dict[str, Any]):
        """Processes position updates received from WebSocket."""
        size_str = pos_data.get("size", "0")
        size = Decimal(str(size_str)) if size_str is not None else DECIMAL_ZERO

        if pos_data.get("side") == "Sell":
            size = -size

        current_inventory = self.inventory
        current_entry_price = self.entry_price

        self.inventory = size
        self.unrealized_pnl = Decimal(str(pos_data.get("unrealisedPnl", "0")))
        self.entry_price = (
            Decimal(str(pos_data.get("avgPrice", "0")))
            if abs(size) > DECIMAL_ZERO
            else DECIMAL_ZERO
        )

        self.logger.debug(
            f"[{self.symbol}] Position updated via WS: {self.inventory:+.4f}, "
            f"UPL: {self.unrealized_pnl:+.4f}, "
            f"Entry: {self.entry_price:.{self.config.price_precision if self.config.price_precision is not None else 8}f}"
        )

        epsilon_qty = Decimal("1e-8")
        epsilon_price_pct = Decimal("1e-5")

        position_size_changed = abs(current_inventory - self.inventory) > epsilon_qty
        entry_price_changed = (
            abs(self.inventory) > DECIMAL_ZERO
            and abs(current_entry_price) > DECIMAL_ZERO
            and abs(self.entry_price) > DECIMAL_ZERO
            and abs(current_entry_price - self.entry_price) / current_entry_price
            > epsilon_price_pct
        )

        if position_size_changed or entry_price_changed:
            self.logger.info(
                f"[{self.symbol}] Position changed ({current_inventory:+.4f} "
                f"-> {self.inventory:+.4f}). Triggering TP/SL update."
            )
            self.update_take_profit_stop_loss()
        
        self._reset_daily_metrics_if_new_day()
        current_daily_metrics = self.daily_metrics.setdefault(self.today_date, {"date": self.today_date, "realized_pnl": DECIMAL_ZERO, "unrealized_pnl_snapshot": DECIMAL_ZERO, "total_fees": DECIMAL_ZERO, "trades_count": 0})
        current_daily_metrics["unrealized_pnl_snapshot"] = self.unrealized_pnl

    def _handle_execution_update(self, exec_data: Dict[str, Any]):
        """
        Processes execution updates, which contain realized PnL.
        This is typically for closing positions.
        """
        exec_side = exec_data.get("side").lower()
        exec_qty = Decimal(str(exec_data.get("execQty", "0")))
        exec_price = Decimal(str(exec_data.get("execPrice", "0")))
        exec_fee = Decimal(str(exec_data.get("execFee", "0")))
        closed_pnl = Decimal(str(exec_data.get("closedPnl", "0")))

        self.performance_metrics["profit"] += closed_pnl
        self.performance_metrics["fees"] += exec_fee
        self.performance_metrics["net_pnl"] = self.performance_metrics["profit"] - self.performance_metrics["fees"]

        self._reset_daily_metrics_if_new_day()
        current_daily_metrics = self.daily_metrics.setdefault(self.today_date, {"date": self.today_date, "realized_pnl": DECIMAL_ZERO, "unrealized_pnl_snapshot": DECIMAL_ZERO, "total_fees": DECIMAL_ZERO, "trades_count": 0})
        current_daily_metrics["realized_pnl"] += closed_pnl
        current_daily_metrics["total_fees"] += exec_fee
        current_daily_metrics["trades_count"] += 1

        self.logger.info(
            f"{Colors.MAGENTA}[{self.symbol}] Execution update: {exec_side.upper()} {exec_qty:.4f} @ {exec_price:.4f}, "
            f"Closed PnL: {closed_pnl:+.4f}, Total Realized PnL: {self.performance_metrics['profit']:+.4f}{Colors.RESET}"
        )
        termux_notify(f"{self.symbol}: Executed {exec_side.upper()} {exec_qty:.4f}. PnL: {closed_pnl:+.4f}", title="Execution")


    @retry_api_call()
    def _close_profitable_entities(self, mid_price: Decimal):
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
                if pos["symbol"] == self.symbol and abs( Decimal(str(pos.get("info", {}).get("size", "0"))) ) > DECIMAL_ZERO:
                    position_size = Decimal(str(pos.get("info", {}).get("size", "0")))
                    entry_price = Decimal(str(pos.get("entryPrice", "0")))
                    unrealized_pnl_percent = DECIMAL_ZERO

                    if entry_price > DECIMAL_ZERO and mid_price > DECIMAL_ZERO:
                        if pos["side"] == "long":
                            unrealized_pnl_percent = (mid_price - entry_price) / entry_price
                        elif pos["side"] == "short":
                            unrealized_pnl_percent = (entry_price - mid_price) / mid_price

                    if unrealized_pnl_percent >= Decimal(str(self.config.take_profit_target_pct)):
                        self.logger.info(
                            f"[{self.symbol}] Position ({pos['side'].upper()} {position_size:+.4f} "
                            f"@ {entry_price:.{self.config.price_precision if self.config.price_precision is not None else 8}f}) is profitable "
                            f"({unrealized_pnl_percent:.4f}%). Checking for slippage to close..."
                        )
                        close_side = "sell" if pos["side"] == "long" else "buy"

                        symbol_id_ws = self.symbol.replace("/", "").replace(":", "")
                        orderbook = self.ws_client.get_order_book_snapshot(symbol_id_ws)
                        if not orderbook or not orderbook.get("b") or not orderbook.get("a"):
                            self.logger.warning(
                                f"{Colors.NEON_ORANGE}[{self.symbol}] No order book data for slippage check. "
                                f"Skipping profitable position close.{Colors.RESET}"
                            )
                            continue
                        
                        bids_df = pd.DataFrame(orderbook["b"], columns=["price", "quantity"]) if orderbook["b"] else pd.DataFrame(columns=["price", "quantity"])
                        asks_df = pd.DataFrame(orderbook["a"], columns=["price", "quantity"]) if orderbook["a"] else pd.DataFrame(columns=["price", "quantity"])
                        
                        required_qty = abs(position_size)
                        estimated_slippage_pct = DECIMAL_ZERO
                        
                        if close_side == "sell": # Closing a long position with a market sell
                            # Ensure bids are sorted descending by price for accurate fill simulation
                            valid_bids = bids_df[bids_df["price"] >= mid_price * Decimal("0.99")].sort_values(by="price", ascending=False) # Slight buffer
                            if valid_bids.empty or valid_bids["quantity"].sum() < required_qty:
                                self.logger.warning(f"[{self.symbol}] Insufficient bid liquidity or bad bids for market sell (long close). Skipping.")
                                continue
                            
                            filled_qty = DECIMAL_ZERO
                            total_cost = DECIMAL_ZERO
                            for _, row in valid_bids.iterrows():
                                qty_to_fill = min(required_qty - filled_qty, row['quantity'])
                                total_cost += qty_to_fill * row['price']
                                filled_qty += qty_to_fill
                                if filled_qty >= required_qty:
                                    break
                            
                            if filled_qty >= required_qty:
                                exec_price_estimate = total_cost / required_qty
                                estimated_slippage_pct = (
                                    (mid_price - exec_price_estimate) / mid_price
                                    if mid_price > DECIMAL_ZERO else DECIMAL_ZERO
                                )
                            else:
                                self.logger.warning(f"[{self.symbol}] Could not find full required quantity in bids for market sell. Skipping.")
                                continue

                        elif close_side == "buy": # Closing a short position with a market buy
                            # Ensure asks are sorted ascending by price for accurate fill simulation
                            valid_asks = asks_df[asks_df["price"] <= mid_price * Decimal("1.01")].sort_values(by="price", ascending=True)
                            if valid_asks.empty or valid_asks["quantity"].sum() < required_qty:
                                self.logger.warning(f"[{self.symbol}] Insufficient ask liquidity or bad asks for market buy (short close). Skipping.")
                                continue
                            
                            filled_qty = DECIMAL_ZERO
                            total_cost = DECIMAL_ZERO
                            for _, row in valid_asks.iterrows():
                                qty_to_fill = min(required_qty - filled_qty, row['quantity'])
                                total_cost += qty_to_fill * row['price']
                                filled_qty += qty_to_fill
                                if filled_qty >= required_qty:
                                    break
                            
                            if filled_qty >= required_qty:
                                exec_price_estimate = total_cost / required_qty
                                estimated_slippage_pct = (
                                    (exec_price_estimate - mid_price) / mid_price
                                    if mid_price > DECIMAL_ZERO else DECIMAL_ZERO
                                )
                            else:
                                self.logger.warning(f"[{self.symbol}] Could not find full required quantity in asks for market buy. Skipping.")
                                continue

                        if estimated_slippage_pct > Decimal(str(self.config.slippage_tolerance_pct)):
                            self.logger.warning(
                                f"{Colors.NEON_ORANGE}[{self.symbol}] Estimated slippage "
                                f"({estimated_slippage_pct * 100:.2f}%) exceeds tolerance "
                                f"({self.config.slippage_tolerance_pct * 100:.2f}%). "
                                f"Skipping profitable position close.{Colors.RESET}"
                            )
                            continue

                        try:
                            closed_order = self.exchange.create_market_order(self.symbol, close_side, float(required_qty))
                            self.logger.info(
                                f"[{self.symbol}] Successfully placed market order to close profitable position "
                                f"with estimated slippage {estimated_slippage_pct * 100:.2f}%."
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

    @retry_api_call()
    def get_account_balance(self, coin: str = "USDT") -> Decimal:
        """Fetches the current available balance for a specified coin."""
        try:
            balances = self.exchange.fetch_balance(params={'accountType': 'UNIFIED'})
            
            if balances and balances.get(coin) and balances[coin].get('free') is not None:
                balance_amount = Decimal(str(balances[coin]['free']))
                return balance_amount
            else:
                self.logger.warning(f"[{self.symbol}] Could not fetch free balance for {coin}. Returning {DECIMAL_ZERO}.")
                return DECIMAL_ZERO
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# [{self.symbol}] Error fetching account balance for {coin}: {e}{Colors.RESET}", exc_info=True)
            return DECIMAL_ZERO


    def _calculate_atr(self, mid_price: Decimal) -> Decimal:
        """Calculates the ATR-based dynamic spread component."""
        if not self.config.dynamic_spread.enabled or (
            time.time() - self.last_atr_update < self.config.dynamic_spread.atr_update_interval
            and self.cached_atr is not None
        ):
            return self.cached_atr if self.cached_atr is not None else DECIMAL_ZERO
        
        if mid_price == DECIMAL_ZERO:
            self.logger.warning(f"[{self.symbol}] Mid-price is zero, cannot calculate ATR. Using cached or {DECIMAL_ZERO}.")
            return self.cached_atr if self.cached_atr is not None else DECIMAL_ZERO

        try:
            ohlcv_interval = self.config.kline_interval
            
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, ohlcv_interval, limit=20)
            if not ohlcv or len(ohlcv) < 20:
                self.logger.warning(f"[{self.symbol}] Not enough OHLCV data ({len(ohlcv)}/{20}) for ATR. Using cached or {DECIMAL_ZERO}.")
                return self.cached_atr if self.cached_atr is not None else DECIMAL_ZERO
            
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["high"] = df["high"].apply(lambda x: Decimal(str(x)))
            df["low"] = df["low"].apply(lambda x: Decimal(str(x)))
            df["close"] = df["close"].apply(lambda x: Decimal(str(x)))
            
            if "high" not in df.columns or "low" not in df.columns or "close" not in df.columns:
                self.logger.warning(f"[{self.symbol}] Missing columns for ATR calculation in OHLCV data. Using cached or {DECIMAL_ZERO}.")
                return self.cached_atr if self.cached_atr is not None else DECIMAL_ZERO

            atr_series = atr(df["high"], df["low"], df["close"])
            atr_val = atr_series.iloc[-1]
            if pd.isna(atr_val) or atr_val <= DECIMAL_ZERO:
                self.logger.warning(f"[{self.symbol}] ATR calculation resulted in NaN or non-positive value. Using cached or {DECIMAL_ZERO}.")
                return self.cached_atr if self.cached_atr is not None else DECIMAL_ZERO

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
            return self.cached_atr if self.cached_atr is not None else DECIMAL_ZERO

    def _calculate_inventory_skew(self, mid_price: Decimal) -> Decimal:
        """Calculates the inventory skew component for spread adjustment."""
        if not self.config.inventory_skew.enabled or self.inventory == DECIMAL_ZERO:
            return DECIMAL_ZERO
        
        normalized_inventory = self.inventory / Decimal(str(self.config.inventory_limit))
        skew_component = normalized_inventory * Decimal(str(self.config.inventory_skew.skew_factor))
        
        max_skew_abs = Decimal(str(self.config.inventory_skew.max_skew)) if self.config.inventory_skew.max_skew is not None else Decimal("0.001")
        skew_component = max(min(skew_component, max_skew_abs), -max_skew_abs)
        
        return abs(skew_component)

    def get_dynamic_order_amount(self, mid_price: Decimal) -> Decimal:
        """Calculates dynamic order amount based on ATR and inventory sizing factor."""
        base_qty = Decimal(str(self.config.order_amount))
        
        if self.inventory != DECIMAL_ZERO and self.config.inventory_limit > 0:
            inventory_pressure = abs(self.inventory) / Decimal(str(self.config.inventory_limit))
            inventory_factor = Decimal("1") - (inventory_pressure * Decimal(str(self.config.inventory_sizing_factor)))
            base_qty *= max(Decimal("0.1"), inventory_factor)

        if self.config.min_qty is not None and base_qty < self.config.min_qty:
            self.logger.warning(f"[{self.symbol}] Calculated quantity {base_qty:.8f} is below min_qty {self.config.min_qty:.8f}. Adjusting to min_qty.")
            base_qty = self.config.min_qty
        
        if self.config.max_qty is not None and base_qty > self.config.max_qty:
            self.logger.warning(f"[{self.symbol}] Calculated quantity {base_qty:.8f} is above max_qty {self.config.max_qty:.8f}. Adjusting to max_qty.")
            base_qty = self.config.max_qty

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
            # Using quantize for proper rounding to decimal places.
            # ROUND_HALF_UP is a common financial rounding method.
            # `Decimal(10) ** -precision` creates a Decimal object like 0.001 for precision 3.
            return value_dec.quantize(Decimal(f'1e-{precision}'), rounding=ROUND_HALF_UP)
        return value_dec.quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    @retry_api_call()
    def place_batch_orders(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Places a batch of orders (limit orders for market making)."""
        if not orders:
            self.logger.debug(f"[{self.symbol}] No orders to place in batch. Returning empty list.")
            return []
        
        filtered_orders = []
        for order in orders:
            try:
                qty = Decimal(order['qty'])
                price = Decimal(order['price'])
                notional = qty * price
                if self.config.min_notional is not None and notional < self.config.min_notional:
                    self.logger.warning(f"[{self.symbol}] Skipping order {order.get('orderLinkId', '')} due to low notional value: {notional:.4f} < {self.config.min_notional:.4f}")
                    continue
                filtered_orders.append(order)
            except InvalidOperation as e:
                self.logger.error(f"[{self.symbol}] Decimal conversion error for order {order.get('orderLinkId', '')}: {e}. Skipping.", exc_info=True)
                continue

        if not filtered_orders:
            self.logger.debug(f"[{self.symbol}] No valid orders after notional filtering. Returning empty list.")
            return []

        try:
            # Bybit's create_orders expects a list of order parameters directly, not a nested 'requests' key
            # However, CCXT's unified create_orders may or may not support batch for all exchanges.
            # For Bybit V5, it's often 'private_post_v5_order_create_batch' or similar.
            # Assuming CCXT's create_orders handles it or we'd make individual calls.
            # For robustness, we will create individual orders if batch fails or is not supported.
            
            # Try batch first (if GLOBAL_CONFIG.use_batch_orders_for_refresh is True)
            if GLOBAL_CONFIG.use_batch_orders_for_refresh and hasattr(self.exchange, 'create_orders'):
                responses = self.exchange.create_orders(filtered_orders)
            else: # Fallback to individual orders
                responses = []
                for order_params in filtered_orders:
                    try:
                        resp = self.exchange.create_order(
                            symbol=self.symbol,
                            type='limit',
                            side=order_params['side'].lower(),
                            amount=float(order_params['qty']),
                            price=float(order_params['price']),
                            params={
                                'category': order_params['category'],
                                'timeInForce': order_params['timeInForce'],
                                'orderLinkId': order_params['orderLinkId']
                            }
                        )
                        responses.append(resp)
                    except Exception as e_single:
                        self.logger.error(f"[{self.symbol}] Failed to place single order {order_params.get('orderLinkId', '')}: {e_single}", exc_info=True)
                        responses.append({'info': {'retCode': -1, 'retMsg': str(e_single)}}) # Mimic error response

            successful_orders = []
            with self.ws_client.lock:
                for resp in responses:
                    if resp and resp.get("info", {}).get("retCode") == 0:
                        order_info = resp.get("info", {})
                        client_order_id = order_info.get("orderLinkId")
                        exchange_id = order_info.get("orderId")
                        side = order_info.get("side")
                        amount = Decimal(str(order_info.get("qty", "0")))
                        price = Decimal(str(order_info.get("price", "0")))
                        status = order_info.get("orderStatus")
                        
                        self.open_orders[client_order_id] = {
                            "side": side,
                            "amount": amount,
                            "price": price,
                            "status": status,
                            "timestamp": time.time() * 1000,
                            "exchange_id": exchange_id,
                            "placement_price": price
                        }
                        successful_orders.append(resp)
                        self.logger.info(f"[{self.symbol}] Placed {side} limit order: {amount:.{self.config.qty_precision if self.config.qty_precision is not None else 8}f} @ {price:.{self.config.price_precision if self.config.price_precision is not None else 8}f} (ID: {client_order_id})")
                    else:
                        error_msg = resp.get('info', {}).get('retMsg', 'Unknown error') if resp else 'No response info'
                        self.logger.error(f"[{self.symbol}] Failed to place order: {error_msg}")
            return successful_orders
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# [{self.symbol}] Error placing batch orders: {e}{Colors.RESET}", exc_info=True)
            return []

    @retry_api_call()
    def cancel_all_orders(self, symbol: str):
        """Cancels all open orders for a given symbol."""
        try:
            self.exchange.cancel_all_orders(symbol, params={'category': GLOBAL_CONFIG.category})
            with self.ws_client.lock:
                self.open_orders.clear()
            self.logger.info(f"[{symbol}] All open orders cancelled.")
            termux_notify(f"{symbol}: All orders cancelled.", title="Orders Cancelled")
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# [{symbol}] Error cancelling all orders: {e}{Colors.RESET}", exc_info=True)
            termux_notify(f"{symbol}: Failed to cancel orders!", is_error=True)

    @retry_api_call()
    def cancel_order(self, order_id: str, client_order_id: str):
        """Cancels a specific order by order_id or client_order_id."""
        try:
            # For Bybit V5, cancel_order requires 'orderId' or 'orderLinkId' and 'category'.
            # We are passing both, CCXT should handle it.
            self.exchange.cancel_order(
                order_id, 
                self.symbol, 
                params={'category': GLOBAL_CONFIG.category, 'orderLinkId': client_order_id}
            )
            with self.ws_client.lock:
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

        take_profit_price = DECIMAL_ZERO
        stop_loss_price = DECIMAL_ZERO

        if self.inventory > DECIMAL_ZERO: # Long position
            take_profit_price = self.entry_price * (Decimal("1") + Decimal(str(self.config.take_profit_target_pct)))
            stop_loss_price = self.entry_price * (Decimal("1") - Decimal(str(self.config.stop_loss_trigger_pct)))
        elif self.inventory < DECIMAL_ZERO: # Short position
            take_profit_price = self.entry_price * (Decimal("1") - Decimal(str(self.config.take_profit_target_pct)))
            stop_loss_price = self.entry_price * (Decimal("1") + Decimal(str(self.config.stop_loss_trigger_pct)))
        
        price_precision = self.config.price_precision
        take_profit_price = self._round_to_precision(take_profit_price, price_precision)
        stop_loss_price = self._round_to_precision(stop_loss_price, price_precision)

        try:
            params = {
                'category': GLOBAL_CONFIG.category,
                'symbol': self.symbol.replace("/", "").replace(":", ""),
                'tpTriggerBy': 'LastPrice',
                'slTriggerBy': 'LastPrice',
                'positionIdx': 0 # For One-Way Mode
            }
            # CCXT's set_trading_stop signature: set_trading_stop(symbol, price, stopLossPrice=None, takeProfitPrice=None, params={})
            # The 'price' argument is usually for an order, not for position TP/SL.
            # We pass takeProfitPrice and stopLossPrice directly.
            self.exchange.set_trading_stop(
                self.symbol,
                price=None, # Not used when takeProfitPrice/stopLossPrice are specified
                stopLossPrice=float(stop_loss_price),
                takeProfitPrice=float(take_profit_price),
                params=params # Other parameters specific to Bybit V5
            )
            self.logger.info(
                f"{Colors.NEON_GREEN}[{self.symbol}] Set TP: {take_profit_price:.{price_precision if price_precision is not None else 8}f}, "
                f"SL: {stop_loss_price:.{price_precision if price_precision is not None else 8}f} for current position.{Colors.RESET}"
            )
            termux_notify(
                f"{self.symbol}: TP: {take_profit_price:.4f}, SL: {stop_loss_price:.4f}", title="TP/SL Updated"
            )
        except Exception as e:
            self.logger.error(
                f"{Colors.NEON_RED}# [{self.symbol}] Error setting TP/SL: {e}{Colors.RESET}", exc_info=True
            )
            termux_notify(f"{self.symbol}: Failed to set TP/SL!", is_error=True)

    def _check_market_data_freshness(self) -> bool:
        """
        Checks if market data (order book and trades) is fresh.
        If data is stale, the bot pauses quoting and cancels orders.
        """
        symbol_id_ws = self.symbol.replace("/", "").replace(":", "")
        current_time = time.time()
        
        orderbook_stale = False
        if symbol_id_ws not in self.ws_client.last_orderbook_update_time or \
           (current_time - self.ws_client.last_orderbook_update_time[symbol_id_ws] > self.config.market_data_stale_timeout_seconds):
            orderbook_stale = True
            
        trades_stale = False
        if symbol_id_ws not in self.ws_client.last_trades_update_time or \
           (current_time - self.ws_client.last_trades_update_time[symbol_id_ws] > self.config.market_data_stale_timeout_seconds):
            trades_stale = True

        if orderbook_stale or trades_stale:
            if self.config.trade_enabled: # Only log if trading was enabled
                self.logger.warning(
                    f"{Colors.NEON_ORANGE}[{self.symbol}] Market data stale! "
                    f"Order book stale: {orderbook_stale}, Trades stale: {trades_stale}. "
                    f"Pausing quoting and cancelling orders.{Colors.RESET}"
                )
                self.cancel_all_orders(self.symbol)
            return False
        return True

    def _check_and_handle_stale_orders(self):
        """
        Automatically cancels any limit order that has been open for longer than
        `stale_order_max_age_seconds`.
        """
        current_time = time.time()
        orders_to_cancel = []
        with self.ws_client.lock:
            for client_order_id, order_info in list(self.open_orders.items()):
                placement_time_seconds = order_info["timestamp"] / 1000 # Convert ms to seconds
                if (current_time - placement_time_seconds) > self.config.stale_order_max_age_seconds:
                    orders_to_cancel.append((order_info["exchange_id"], client_order_id))
        
        for exchange_id, client_order_id in orders_to_cancel:
            self.logger.warning(
                f"[{self.symbol}] Order {client_order_id} is stale (open for "
                f"> {self.config.stale_order_max_age_seconds} seconds). Cancelling."
            )
            self.cancel_order(exchange_id, client_order_id) # Uses retry_api_call

    def _check_daily_pnl_limits(self) -> bool:
        """
        Checks if daily PnL (Realized + Unrealized) exceeds stop-loss or take-profit limits.
        If a limit is hit, it disables trading for the symbol for the rest of the day.
        Returns True if limits are hit, False otherwise.
        """
        if not GLOBAL_CONFIG.daily_pnl_stop_loss_pct and not GLOBAL_CONFIG.daily_pnl_take_profit_pct:
            return False # No limits configured

        self._reset_daily_metrics_if_new_day()
        current_daily_metrics = self.daily_metrics.setdefault(self.today_date, {"date": self.today_date, "realized_pnl": DECIMAL_ZERO, "unrealized_pnl_snapshot": DECIMAL_ZERO, "total_fees": DECIMAL_ZERO, "trades_count": 0})
        
        realized_pnl_today = current_daily_metrics.get("realized_pnl", DECIMAL_ZERO)
        # Unrealized PnL is dynamic, use current self.unrealized_pnl
        total_pnl_today = realized_pnl_today + self.unrealized_pnl
        
        # Get account balance for percentage calculation
        total_balance = self.get_account_balance() # Assumes USDT for now
        if total_balance <= DECIMAL_ZERO:
            self.logger.warning(f"[{self.symbol}] Total balance is zero or negative, cannot check daily PnL limits.")
            return False

        pnl_percent = total_pnl_today / total_balance
        
        if GLOBAL_CONFIG.daily_pnl_stop_loss_pct and pnl_percent <= -Decimal(str(GLOBAL_CONFIG.daily_pnl_stop_loss_pct)):
            self.logger.critical(
                f"{Colors.NEON_RED}[{self.symbol}] Daily Stop-Loss hit! PnL: {pnl_percent*100:.2f}%, "
                f"Limit: {-Decimal(str(GLOBAL_CONFIG.daily_pnl_stop_loss_pct))*100:.2f}%. Disabling trading for this symbol.{Colors.RESET}"
            )
            self.config.trade_enabled = False
            self.cancel_all_orders(self.symbol)
            termux_notify(f"{self.symbol}: Daily SL HIT! PnL: {pnl_percent*100:.2f}%", is_error=True)
            return True
        
        if GLOBAL_CONFIG.daily_pnl_take_profit_pct and pnl_percent >= Decimal(str(GLOBAL_CONFIG.daily_pnl_take_profit_pct)):
            self.logger.info(
                f"{Colors.NEON_GREEN}[{self.symbol}] Daily Take-Profit hit! PnL: {pnl_percent*100:.2f}%, "
                f"Limit: {Decimal(str(GLOBAL_CONFIG.daily_pnl_take_profit_pct))*100:.2f}%. Disabling trading for this symbol.{Colors.RESET}"
            )
            self.config.trade_enabled = False
            self.cancel_all_orders(self.symbol)
            termux_notify(f"{self.symbol}: Daily TP HIT! PnL: {pnl_percent*100:.2f}%", is_error=False)
            return True
        
        return False

    def _display_status(self):
        """Displays real-time status of the bot in the console."""
        symbol_id_ws = self.symbol.replace("/", "").replace(":", "")
        orderbook = self.ws_client.get_order_book_snapshot(symbol_id_ws)
        
        best_bid = orderbook["b"][0][0] if orderbook and orderbook.get("b") else DECIMAL_ZERO
        best_ask = orderbook["a"][0][0] if orderbook and orderbook.get("a") else DECIMAL_ZERO
        mid_price = (best_bid + best_ask) / Decimal("2") if best_bid and best_ask and best_bid > DECIMAL_ZERO and best_ask > DECIMAL_ZERO else DECIMAL_ZERO

        pnl_color = Colors.NEON_GREEN if self.unrealized_pnl >= DECIMAL_ZERO else Colors.NEON_RED
        pos_color = Colors.NEON_GREEN if self.inventory >= DECIMAL_ZERO else Colors.NEON_RED
        
        current_daily_metrics = self.daily_metrics.get(self.today_date, {"realized_pnl": DECIMAL_ZERO, "unrealized_pnl_snapshot": DECIMAL_ZERO, "total_fees": DECIMAL_ZERO, "trades_count": 0})
        realized_pnl_today = current_daily_metrics.get("realized_pnl", DECIMAL_ZERO)
        fees_today = current_daily_metrics.get("total_fees", DECIMAL_ZERO)
        
        # Total daily PnL (realized + current unrealized - fees)
        total_daily_pnl = realized_pnl_today + self.unrealized_pnl - fees_today
        daily_pnl_color = Colors.NEON_GREEN if total_daily_pnl >= DECIMAL_ZERO else Colors.NEON_RED

        status_str = (
            f"{Colors.CYAN}--- {self.symbol} Status ({'Enabled' if self.config.trade_enabled else 'Disabled'}) ---\n"
            f"  {Colors.YELLOW}Mid: {mid_price:.{self.config.price_precision if self.config.price_precision is not None else 8}f} "
            f"Bid: {best_bid:.{self.config.price_precision if self.config.price_precision is not None else 8}f} "
            f"Ask: {best_ask:.{self.config.price_precision if self.config.price_precision is not None else 8}f}{Colors.RESET}\n"
            f"  {pos_color}Position: {self.inventory:+.{self.config.qty_precision if self.config.qty_precision is not None else 8}f} "
            f"({self.entry_price:.{self.config.price_precision if self.config.price_precision is not None else 8}f}){Colors.RESET}\n"
            f"  {pnl_color}UPL: {self.unrealized_pnl:+.4f}{Colors.RESET}\n"
            f"  {Colors.MAGENTA}Total Realized PnL: {self.performance_metrics['profit']:+.4f} (Fees: {self.performance_metrics['fees']:+.4f}) "
            f"Net PnL: {self.performance_metrics['net_pnl']:+.4f} (Trades: {self.performance_metrics['trades']}){Colors.RESET}\n"
            f"  {daily_pnl_color}Daily Net PnL (Today): {total_daily_pnl:+.4f} (R: {realized_pnl_today:+.4f} U: {self.unrealized_pnl:+.4f} F: {fees_today:+.4f}){Colors.RESET}\n"
            f"  {Colors.NEON_BLUE}Open Orders: {len(self.open_orders)}{Colors.RESET}\n"
            f"{Colors.CYAN}--------------------------------------{Colors.RESET}"
        )
        self.logger.info(status_str)

    def run(self):
        """The main loop for the SymbolBot."""
        self.logger.info(f"{Colors.CYAN}[{self.symbol}] SymbolBot starting.{Colors.RESET}")
        
        # Initial setup
        if not self._fetch_symbol_info():
            self.logger.critical(f"{Colors.NEON_RED}[{self.symbol}] Failed to fetch symbol info. Stopping bot.{Colors.RESET}")
            termux_notify(f"{self.symbol}: Init Failed (Symbol Info)", is_error=True)
            self._stop_event.set()
            return
        
        if GLOBAL_CONFIG.category == "linear": # Only for perpetuals
            if not self._set_margin_mode_and_position_mode():
                self.logger.critical(f"{Colors.NEON_RED}[{self.symbol}] Failed to set margin/position mode. Stopping bot.{Colors.RESET}")
                termux_notify(f"{self.symbol}: Init Failed (Margin Mode)", is_error=True)
                self._stop_event.set()
                return
            if not self._set_leverage_if_needed():
                self.logger.critical(f"{Colors.NEON_RED}[{self.symbol}] Failed to set leverage. Stopping bot.{Colors.RESET}")
                termux_notify(f"{self.symbol}: Init Failed (Leverage)", is_error=True)
                self._stop_event.set()
                return

        last_status_display_time = time.time()
        last_order_refresh_time = time.time()
        
        while not self._stop_event.is_set():
            try:
                current_time = time.time()
                
                # Check market data freshness
                if not self._check_market_data_freshness():
                    self.logger.warning(f"[{self.symbol}] Stale market data. Skipping order generation cycle.")
                    self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL)
                    continue

                symbol_id_ws = self.symbol.replace("/", "").replace(":", "")
                orderbook = self.ws_client.get_order_book_snapshot(symbol_id_ws)
                if not orderbook or not orderbook.get("b") or not orderbook.get("a"):
                    self.logger.warning(f"[{self.symbol}] Order book not available yet. Waiting...")
                    self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL)
                    continue

                best_bid = orderbook["b"][0][0]
                best_ask = orderbook["a"][0][0]
                mid_price = (best_bid + best_ask) / Decimal("2")
                
                if mid_price == DECIMAL_ZERO:
                    self.logger.warning(f"[{self.symbol}] Mid price is zero, cannot proceed with order placement. Waiting...")
                    self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL)
                    continue

                # Check daily PnL limits
                if self._check_daily_pnl_limits():
                    self.logger.warning(f"[{self.symbol}] Daily PnL limits hit. Trading disabled for today.")
                    self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL)
                    continue # Skip further trading logic for this cycle

                # Main market making logic
                if self.config.trade_enabled:
                    # Check if it's time to refresh orders
                    if (current_time - last_order_refresh_time) >= self.config.order_refresh_time:
                        self.strategy.generate_orders(self.symbol, mid_price, orderbook)
                        last_order_refresh_time = current_time
                    
                    # Check for stale orders
                    self._check_and_handle_stale_orders()

                    # Additional profit taking (optional, as TP/SL is set via exchange)
                    # self._close_profitable_entities(mid_price) 
                else:
                    self.logger.debug(f"[{self.symbol}] Trading disabled. Skipping order generation.")
                    self.cancel_all_orders(self.symbol) # Ensure no old orders are left if trading becomes disabled

                # Display status periodically
                if (current_time - last_status_display_time) >= STATUS_UPDATE_INTERVAL:
                    self._display_status()
                    last_status_display_time = current_time
                    self._save_state() # Save state after status update

            except Exception as e:
                self.logger.error(f"{Colors.NEON_RED}[{self.symbol}] Unexpected error in main loop: {e}{Colors.RESET}", exc_info=True)
                termux_notify(f"{self.symbol}: Bot Error: {str(e)[:50]}...", is_error=True)
            
            self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL) # Use wait with timeout for graceful shutdown

        self.logger.info(f"{Colors.CYAN}[{self.symbol}] SymbolBot stopping. Cancelling all orders and saving state.{Colors.RESET}")
        self.cancel_all_orders(self.symbol)
        self._save_state()
        with self.ws_client.lock: # Remove self from WS client's list
            if self in self.ws_client.symbol_bots:
                self.ws_client.symbol_bots.remove(self)

    def stop(self):
        """Signals the SymbolBot thread to stop."""
        self.logger.info(f"{Colors.YELLOW}[{self.symbol}] Signaling SymbolBot to stop.{Colors.RESET}")
        self._stop_event.set()


# --- Pyrmethus Market Maker Bot ---
class PyrmethusBot:
    """The grand orchestrator of market making, managing multiple symbols."""

    def __init__(self):
        # Initial logger setup. This will be re-configured once GLOBAL_CONFIG is loaded in run().
        global main_logger
        if EXTERNAL_LIBS_AVAILABLE:
            main_logger = setup_logger("main")
        self.logger = main_logger

        self.exchange: Optional[Any] = None # ccxt.Exchange
        self.ws_client: Optional[BybitWebSocket] = None
        self.symbol_bots: Dict[str, SymbolBot] = {} # {symbol: SymbolBot_instance}
        self.active_symbol_configs: Dict[str, SymbolConfig] = {} # {symbol: SymbolConfig_instance}
        self._stop_event = threading.Event()
        self.config_manager_thread: Optional[threading.Thread] = None
        self.last_config_check_time: float = 0.0

    def _initialize_exchange_and_ws(self):
        """Initializes the CCXT exchange and WebSocket client."""
        self.exchange = initialize_exchange(self.logger)
        if not self.exchange:
            self.logger.critical(f"{Colors.NEON_RED}Exchange initialization failed. Exiting.{Colors.RESET}")
            sys.exit(1)

        # Determine if testnet based on API key or environment variable
        is_testnet = os.getenv("BYBIT_TESTNET", "False").lower() == "true"
        if is_testnet:
            self.logger.warning(f"{Colors.YELLOW}Running in TESTNET mode!{Colors.RESET}")
            self.exchange.set_sandbox_mode(True)

        self.ws_client = BybitWebSocket(BYBIT_API_KEY, BYBIT_API_SECRET, is_testnet, self.logger)

    def _start_symbol_bots(self, symbol_configs: List[SymbolConfig]):
        """Starts SymbolBot threads for the given configurations."""
        if not self.exchange or not self.ws_client:
            self.logger.critical(f"{Colors.NEON_RED}Exchange or WebSocket client not initialized. Cannot start SymbolBots.{Colors.RESET}")
            return
        
        new_public_topics: List[str] = []
        new_private_topics: List[str] = ["order", "execution", "position"] # Always subscribe to these
        new_trade_topics: List[str] = ["execution", "order", "position"] # If trade stream is used for these

        # Filter for unique and active symbols, respect max_symbols_termux
        active_configs_to_start = []
        for cfg in symbol_configs:
            if cfg.trade_enabled:
                active_configs_to_start.append(cfg)
        
        # Sort by symbol for consistent behavior, then take up to max_symbols_termux
        active_configs_to_start = sorted(active_configs_to_start, key=lambda x: x.symbol)[:GLOBAL_CONFIG.max_symbols_termux]

        # Identify symbols that should be active based on new config
        symbols_in_new_config = {cfg.symbol for cfg in active_configs_to_start}

        # Stop bots for symbols no longer in the config or disabled
        symbols_to_stop = [s for s in self.symbol_bots if s not in symbols_in_new_config]
        for symbol in symbols_to_stop:
            self.logger.info(f"{Colors.YELLOW}Stopping SymbolBot for {symbol} (no longer active or disabled)...{Colors.RESET}")
            self.symbol_bots[symbol].stop()
            self.symbol_bots[symbol].join(timeout=10)
            if self.symbol_bots[symbol].is_alive():
                self.logger.warning(f"[{symbol}] SymbolBot did not stop gracefully.")
            del self.symbol_bots[symbol]
            del self.active_symbol_configs[symbol]

        for config in active_configs_to_start:
            if config.symbol not in self.symbol_bots:
                self.logger.info(f"{Colors.CYAN}Starting SymbolBot for {config.symbol}...{Colors.RESET}")
                bot = SymbolBot(config, self.exchange, self.ws_client, setup_logger(config.symbol.replace('/', '_').replace(':', '')))
                self.symbol_bots[config.symbol] = bot
                self.active_symbol_configs[config.symbol] = config # Track active config
                bot.start()
                
            elif self.active_symbol_configs.get(config.symbol) != config:
                # Configuration for an existing bot changed, need to restart it
                self.logger.info(f"{Colors.YELLOW}Configuration for {config.symbol} changed. Restarting SymbolBot...{Colors.RESET}")
                self.symbol_bots[config.symbol].stop()
                self.symbol_bots[config.symbol].join(timeout=10) # Wait for it to stop
                if self.symbol_bots[config.symbol].is_alive():
                    self.logger.warning(f"[{config.symbol}] SymbolBot did not stop gracefully.")
                
                del self.symbol_bots[config.symbol]
                
                # Create and start new bot with updated config
                bot = SymbolBot(config, self.exchange, self.ws_client, setup_logger(config.symbol.replace('/', '_').replace(':', '')))
                self.symbol_bots[config.symbol] = bot
                self.active_symbol_configs[config.symbol] = config
                bot.start()
            
            # Add WS topics for this symbol (after any restarts)
            symbol_id_ws = config.symbol.replace("/", "").replace(":", "")
            new_public_topics.append(f"orderbook.50.{symbol_id_ws}") # Order book depth 50
            new_public_topics.append(f"publicTrade.{symbol_id_ws}") # Public trades
        
        # Update WebSocket subscriptions if topics have changed
        current_public_subscriptions = sorted(self.ws_client.public_subscriptions)
        current_private_subscriptions = sorted(self.ws_client.private_subscriptions)
        current_trade_subscriptions = sorted(self.ws_client.trade_subscriptions) # Added for trade stream

        # Ensure only unique topics and sort for comparison
        new_public_topics_set = sorted(list(set(new_public_topics)))
        new_private_topics_set = sorted(list(set(new_private_topics)))
        new_trade_topics_set = sorted(list(set(new_trade_topics))) # Added for trade stream

        if new_public_topics_set != current_public_subscriptions or \
           new_private_topics_set != current_private_subscriptions or \
           new_trade_topics_set != current_trade_subscriptions: # Compare trade topics too
            self.logger.info(f"{Colors.MAGENTA}Updating WebSocket subscriptions...{Colors.RESET}")
            self.ws_client.stop_streams() # Stop all streams
            self.ws_client.start_streams(new_public_topics_set, new_private_topics_set, new_trade_topics_set) # Start with new subscriptions
        else:
            self.logger.debug("WebSocket subscriptions are up to date.")

    def _stop_symbol_bots(self):
        """Signals all SymbolBot threads to stop and waits for them to finish."""
        self.logger.info(f"{Colors.YELLOW}Signaling all SymbolBots to stop...{Colors.RESET}")
        for symbol, bot in list(self.symbol_bots.items()): # Iterate over copy as dict changes
            bot.stop()
            bot.join(timeout=10)
            if bot.is_alive():
                self.logger.warning(f"[{symbol}] SymbolBot did not stop gracefully.")
            del self.symbol_bots[symbol]
            del self.active_symbol_configs[symbol]
        self.logger.info(f"{Colors.CYAN}All SymbolBots have been extinguished.{Colors.RESET}")
        if self.ws_client:
            self.ws_client.stop_streams()

    def _manage_active_symbol_bots_periodically(self):
        """Periodically reloads configuration and manages active SymbolBots."""
        while not self._stop_event.is_set():
            try:
                # Check for config changes more frequently than symbol info refresh, but not too often
                if (time.time() - self.last_config_check_time) > 60: # Check config file every 60 seconds
                    self.logger.info(f"{Colors.CYAN}Periodically checking for symbol configuration changes...{Colors.RESET}")
                    
                    # Reload global config and symbol configs from file
                    global GLOBAL_CONFIG, SYMBOL_CONFIGS
                    global_cfg_reloaded, symbol_configs_reloaded = ConfigManager.load_config(prompt_for_symbol=False)
                    
                    # Update GLOBAL_CONFIG if it changed (important for daily PnL limits, etc.)
                    if global_cfg_reloaded != GLOBAL_CONFIG:
                        self.logger.info(f"{Colors.YELLOW}Global configuration changed. Applying updates.{Colors.RESET}")
                        GLOBAL_CONFIG = global_cfg_reloaded
                        self.logger = setup_logger("main") # Reconfigure main logger with new global settings

                    # Update SYMBOL_CONFIGS
                    SYMBOL_CONFIGS = symbol_configs_reloaded

                    # Manage active bots based on reloaded symbol configurations
                    self._start_symbol_bots(SYMBOL_CONFIGS)
                    self.last_config_check_time = time.time()

            except Exception as e:
                self.logger.error(f"{Colors.NEON_RED}Error in config manager thread: {e}{Colors.RESET}", exc_info=True)
            
            self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL * 5) # Check less frequently than main bot loops

    def run(self):
        """Initiates the Pyrmethus Market Maker Bot."""
        self.logger.info(f"{Colors.NEON_GREEN}Pyrmethus Market Maker Bot starting...{Colors.RESET}")
        
        # --- User Interaction for Symbol Selection ---
        selected_mode = input(
            f"{Colors.CYAN}Choose mode:\n"
            f"  [f]rom file (symbols.json) - for multi-symbol operation\n"
            f"  [s]ingle symbol (e.g., BTC/USDT:USDT) - for interactive, quick run\n"
            f"Enter choice (f/s): {Colors.RESET}"
        ).lower().strip()

        input_symbol: Optional[str] = None
        if selected_mode == 's':
            input_symbol = input(f"{Colors.CYAN}Enter single symbol (e.g., BTC/USDT:USDT): {Colors.RESET}").upper().strip()
            if not input_symbol:
                self.logger.critical(f"{Colors.NEON_RED}No symbol entered. Exiting.{Colors.RESET}")
                sys.exit(1)
            
        # Load configuration (global and symbol-specific) based on user choice
        global GLOBAL_CONFIG, SYMBOL_CONFIGS
        try:
            GLOBAL_CONFIG, SYMBOL_CONFIGS = ConfigManager.load_config(
                prompt_for_symbol=(selected_mode == 's'),
                input_symbol=input_symbol
            )
            # Re-initialize logger with the now loaded GLOBAL_CONFIG
            self.logger = setup_logger("main")
        except SystemExit: # ConfigManager might call sys.exit()
            self.logger.critical(f"{Colors.NEON_RED}Configuration loading failed. Exiting.{Colors.RESET}")
            sys.exit(1)
        except Exception as e:
            self.logger.critical(f"{Colors.NEON_RED}Unexpected error during configuration loading: {e}. Exiting.{Colors.RESET}", exc_info=True)
            sys.exit(1)

        # Initialize CCXT exchange and WebSocket client
        self._initialize_exchange_and_ws()

        # Start the periodic config manager thread
        self.config_manager_thread = threading.Thread(target=self._manage_active_symbol_bots_periodically, daemon=True, name="ConfigManagerThread")
        self.config_manager_thread.start()

        # Initial start of symbol bots
        self._start_symbol_bots(SYMBOL_CONFIGS)

        # Main bot loop (just keeps the main thread alive and handles graceful shutdown)
        try:
            self.logger.info(f"{Colors.NEON_GREEN}Pyrmethus Bot is now operational. Press Ctrl+C to stop.{Colors.RESET}")
            # Keep the main thread alive, allowing worker threads to run
            while not self._stop_event.is_set():
                time.sleep(1) # Small sleep to reduce CPU usage
        except KeyboardInterrupt:
            self.logger.info(f"{Colors.YELLOW}Ctrl+C detected. Initiating graceful shutdown...{Colors.RESET}")
        except Exception as e:
            self.logger.critical(f"{Colors.NEON_RED}An unhandled error occurred in the main bot process: {e}{Colors.RESET}", exc_info=True)
            termux_notify("Pyrmethus Bot CRASHED!", is_error=True)
        finally:
            self._stop_event.set() # Signal all threads to stop
            self.logger.info(f"{Colors.CYAN}Stopping all SymbolBots and WebSocket streams.{Colors.RESET}")
            self._stop_symbol_bots() # This will also stop WS streams
            if self.config_manager_thread and self.config_manager_thread.is_alive():
                self.config_manager_thread.join(timeout=10)
            self.logger.info(f"{Colors.NEON_GREEN}Pyrmethus Market Maker Bot gracefully shut down.{Colors.RESET}")


# --- Main Execution ---
if __name__ == "__main__":
    # Set up a basic logger for early messages before GLOBAL_CONFIG is fully loaded
    if not EXTERNAL_LIBS_AVAILABLE:
        print("Required libraries are not available. Cannot run the bot.")
        sys.exit(1)

    # Temporary logger for initial setup, replaced by setup_logger later
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    main_logger = logging.getLogger("market_maker_main_temp")

    # Signal handler for graceful shutdown (e.g., systemd stop)
    def handle_sigterm(signum, frame):
        main_logger.info(f"{Colors.YELLOW}SIGTERM ({signum}) received. Initiating graceful shutdown...{Colors.RESET}")
        if 'bot_instance' in globals() and bot_instance is not None:
            bot_instance._stop_event.set()
        else:
            main_logger.warning("Bot instance not found for SIGTERM handling.")

    signal.signal(signal.SIGTERM, handle_sigterm)

    bot_instance: Optional[PyrmethusBot] = None
    try:
        bot_instance = PyrmethusBot()
        bot_instance.run()
    except Exception as e:
        main_logger.critical(f"{Colors.NEON_RED}Pyrmethus Bot encountered a critical error: {e}{Colors.RESET}", exc_info=True)
        termux_notify("Pyrmethus Bot CRASHED!", is_error=True)
        sys.exit(1)
