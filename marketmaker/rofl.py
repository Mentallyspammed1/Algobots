import hashlib
import hmac
import json
import logging
import math
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, getcontext
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import ccxt
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
    print(f"Error: Missing required library: {e}. Please install it using pip.")
    print("Install all dependencies with: pip install ccxt pandas requests websocket-client pydantic colorama python-dotenv")
    EXTERNAL_LIBS_AVAILABLE = False
    DOTENV_AVAILABLE = False

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
        CYAN = MAGENTA = YELLOW = GREEN = BLUE = RED = LIGHTRED_EX = RESET = ""
    class Style:
        BRIGHT = RESET_ALL = ""
    def init(autoreset=True): pass
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
    class PositiveInt(int): pass


if EXTERNAL_LIBS_AVAILABLE:
    init(autoreset=True)
else:
    print("Colorama not available. Output will not be colored.")


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


if EXTERNAL_LIBS_AVAILABLE:
    getcontext().prec = 38

class Colors:
    if EXTERNAL_LIBS_AVAILABLE:
        CYAN = Fore.CYAN + Style.BRIGHT
        MAGENTA = Fore.MAGENTA + Style.BRIGHT
        YELLOW = Fore.YELLOW + Style.BRIGHT
        RESET = Style.RESET_ALL
        NEON_GREEN = Fore.GREEN + Style.BRIGHT
        NEON_BLUE = Fore.BLUE + Style.BRIGHT
        NEON_RED = Fore.RED + Style.BRIGHT
        NEON_ORANGE = Fore.LIGHTRED_EX + Style.BRIGHT
    else:
        CYAN = MAGENTA = YELLOW = NEON_GREEN = NEON_BLUE = NEON_RED = NEON_ORANGE = RESET = ""


BYBIT_API_KEY: Optional[str] = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET: Optional[str] = os.getenv("BYBIT_API_SECRET")

BASE_DIR = Path(os.getenv("HOME", "."))
LOG_DIR: Path = BASE_DIR / "bot_logs"
STATE_DIR: Path = BASE_DIR / ".bot_state"
LOG_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)

EXCHANGE_CONFIG = {
    "id": "bybit",
    "apiKey": BYBIT_API_KEY,
    "secret": BYBIT_API_SECRET,
    "enableRateLimit": True,
    "options": {"defaultType": "linear", "verbose": False, "adjustForTimeDifference": True, "v5": True, "recvWindow": 10000},
}

API_RETRY_ATTEMPTS = 5
RETRY_BACKOFF_FACTOR = 0.5
WS_RECONNECT_INTERVAL = 5
SYMBOL_INFO_REFRESH_INTERVAL = 24 * 60 * 60
STATUS_UPDATE_INTERVAL = 60
MAIN_LOOP_SLEEP_INTERVAL = 5
DECIMAL_ZERO = Decimal("0") if EXTERNAL_LIBS_AVAILABLE else 0
MIN_TRADE_PNL_PERCENT = Decimal("-0.0005") if EXTERNAL_LIBS_AVAILABLE else -0.0005


if EXTERNAL_LIBS_AVAILABLE:
    class JsonDecimalEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Decimal):
                return str(obj)
            return super().default(obj)

    def json_loads_decimal(s: str) -> Any:
        try:
            return json.loads(s, parse_float=Decimal, parse_int=Decimal)
        except (json.JSONDecodeError, InvalidOperation) as e:
            main_logger.error(f"Error decoding JSON with Decimal: {e} for input: {s[:100]}...")
            raise ValueError(f"Invalid JSON or Decimal format: {e}") from e

    class Trade(BaseModel):
        side: str
        qty: Decimal
        price: Decimal
        profit: Decimal = DECIMAL_ZERO
        timestamp: int
        fee: Decimal
        trade_id: str
        entry_price: Optional[Decimal] = None
        model_config = ConfigDict(json_dumps=lambda v: json.dumps(v, cls=JsonDecimalEncoder), json_loads=json_loads_decimal, validate_assignment=True)

    class DynamicSpreadConfig(BaseModel):
        enabled: bool = True
        volatility_multiplier: PositiveFloat = 0.5
        atr_update_interval: NonNegativeInt = 300

    class InventorySkewConfig(BaseModel):
        enabled: bool = True
        skew_factor: PositiveFloat = 0.1
        max_skew: Optional[PositiveFloat] = None

    class OrderLayer(BaseModel):
        spread_offset: NonNegativeFloat = 0.0
        quantity_multiplier: PositiveFloat = 1.0
        cancel_threshold_pct: PositiveFloat = 0.01

    class SymbolConfig(BaseModel):
        symbol: str
        trade_enabled: bool = True
        base_spread: PositiveFloat = 0.001
        order_amount: PositiveFloat = 0.001
        leverage: PositiveFloat = 10.0
        order_refresh_time: NonNegativeInt = 5
        max_spread: PositiveFloat = 0.005
        inventory_limit: PositiveFloat = 0.01
        dynamic_spread: DynamicSpreadConfig = Field(default_factory=DynamicSpreadConfig)
        inventory_skew: InventorySkewConfig = Field(default_factory=InventorySkewConfig)
        momentum_window: NonNegativeInt = 10
        take_profit_percentage: PositiveFloat = 0.002
        stop_loss_percentage: PositiveFloat = 0.001
        inventory_sizing_factor: NonNegativeFloat = 0.5
        min_liquidity_depth: PositiveFloat = 1000.0
        depth_multiplier: PositiveFloat = 2.0
        imbalance_threshold: NonNegativeFloat = 0.3
        slippage_tolerance_pct: NonNegativeFloat = 0.002
        funding_rate_threshold: NonNegativeFloat = 0.0005
        backtest_mode: bool = False
        max_symbols_termux: NonNegativeInt = 5
        trailing_stop_pct: NonNegativeFloat = 0.005
        min_recent_trade_volume: NonNegativeFloat = 0.0
        trading_hours_start: Optional[str] = None
        trading_hours_end: Optional[str] = None
        order_layers: List[OrderLayer] = Field(default_factory=lambda: [OrderLayer()])
        min_order_value_usd: PositiveFloat = Field(default=10.0, description="Minimum order value in USD.")
        max_capital_allocation_per_order_pct: PositiveFloat = Field(default=0.01, description="Max percentage of available capital to allocate per single order.")
        atr_qty_multiplier: PositiveFloat = Field(default=0.1, description="Multiplier for ATR's impact on order quantity.")
        enable_auto_sl_tp: bool = Field(default=False, description="Enable automatic Stop-Loss and Take-Profit on market-making orders.")
        take_profit_target_pct: PositiveFloat = Field(default=0.005, description="Take-Profit percentage from entry price (e.g., 0.005 for 0.5%).")
        stop_loss_trigger_pct: PositiveFloat = Field(default=0.005, description="Stop-Loss percentage from entry price (e.g., 0.005 for 0.5%).")
        use_batch_orders_for_refresh: bool = True
        recent_fill_rate_window: NonNegativeInt = 60
        cancel_partial_fill_threshold_pct: NonNegativeFloat = 0.15
        stale_order_max_age_seconds: NonNegativeInt = 300
        momentum_trend_threshold: NonNegativeFloat = 0.0001
        max_capital_at_risk_usd: NonNegativeFloat = 0.0
        market_data_stale_timeout_seconds: NonNegativeInt = 30
        kline_interval: str = "1m"

        min_qty: Optional[Decimal] = None
        max_qty: Optional[Decimal] = None
        qty_precision: Optional[int] = None
        price_precision: Optional[int] = None
        min_notional: Optional[Decimal] = None

        model_config = ConfigDict(json_dumps=lambda v: json.dumps(v, cls=JsonDecimalEncoder), json_loads=json_loads_decimal, validate_assignment=True)

        def __eq__(self, other: Any) -> bool:
            if not isinstance(other, SymbolConfig):
                return NotImplemented
            self_dict = self.model_dump(
                exclude={"min_qty", "max_qty", "qty_precision", "price_precision", "min_notional"}
            )
            other_dict = other.model_dump(
                exclude={"min_qty", "max_qty", "qty_precision", "price_precision", "min_notional"}
            )
            return self_dict == other_dict

        def __hash__(self) -> int:
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
        category: str = "linear"
        api_max_retries: PositiveInt = 5
        api_retry_delay: PositiveInt = 1
        orderbook_depth_limit: PositiveInt = 100
        orderbook_analysis_levels: PositiveInt = 30
        imbalance_threshold: PositiveFloat = 0.25
        depth_range_pct: PositiveFloat = 0.008
        slippage_tolerance_pct: PositiveFloat = 0.003
        min_profitable_spread_pct: PositiveFloat = 0.0005
        funding_rate_threshold: PositiveFloat = 0.0004
        backtest_mode: bool = False
        max_symbols_termux: PositiveInt = 2
        log_level: str = "INFO"
        log_file: str = "market_maker_live.log"
        state_file: str = "state.json"
        use_batch_orders_for_refresh: bool = True
        strategy: str = "MarketMakerStrategy"
        bb_width_threshold: PositiveFloat = 0.15
        min_liquidity_per_level: PositiveFloat = 0.001
        depth_multiplier_for_qty: PositiveFloat = 1.5
        default_order_amount: PositiveFloat = 0.003
        default_leverage: PositiveInt = 10
        default_max_spread: PositiveFloat = 0.005
        default_skew_factor: PositiveFloat = 0.1
        default_atr_multiplier: PositiveFloat = 0.5
        symbol_config_file: str = "symbols.json"
        telegram_bot_token: Optional[str] = None
        telegram_chat_id: Optional[str] = None
        daily_pnl_stop_loss_pct: Optional[PositiveFloat] = Field(default=None, description="Percentage loss threshold for daily PnL (e.g., 0.05 for 5%).")
        daily_pnl_take_profit_pct: Optional[PositiveFloat] = Field(default=None, description="Percentage profit threshold for daily PnL (e.g., 0.10 for 10%).")

        model_config = ConfigDict(json_dumps=lambda v: json.dumps(v, cls=JsonDecimalEncoder), json_loads=json_loads_decimal, validate_assignment=True)

    class ConfigManager:
        _global_config: Optional[GlobalConfig] = None
        _symbol_configs: List[SymbolConfig] = []

        @classmethod
        def load_config(cls, prompt_for_symbol: bool = False, input_symbol: Optional[str] = None) -> Tuple[GlobalConfig, List[SymbolConfig]]:
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
                single_symbol_data = {
                    "symbol": input_symbol,
                    "trade_enabled": True,
                    "base_spread": cls._global_config.min_profitable_spread_pct * 2,
                    "order_amount": cls._global_config.default_order_amount,
                    "leverage": cls._global_config.default_leverage,
                    "order_refresh_time": cls._global_config.api_retry_delay * 5,
                    "max_spread": cls._global_config.default_max_spread,
                    "inventory_limit": cls._global_config.default_order_amount * 10,
                    "dynamic_spread": DynamicSpreadConfig(enabled=True, volatility_multiplier=cls._global_config.default_atr_multiplier, atr_update_interval=300),
                    "inventory_skew": InventorySkewConfig(enabled=True, skew_factor=cls._global_config.default_skew_factor, max_skew=0.0005),
                    "min_order_value_usd": 10.0,
                    "kline_interval": "1m",
                    "order_layers": [OrderLayer(spread_offset=0.0, quantity_multiplier=1.0, cancel_threshold_pct=0.01)],
                    "min_recent_trade_volume": 0.0,
                    "market_data_stale_timeout_seconds": 30,
                    "enable_auto_sl_tp": False,
                    "take_profit_target_pct": 0.005,
                    "stop_loss_trigger_pct": 0.005,
                    "use_batch_orders_for_refresh": cls._global_config.use_batch_orders_for_refresh,
                    "recent_fill_rate_window": 60,
                    "cancel_partial_fill_threshold_pct": 0.15,
                    "stale_order_max_age_seconds": 300,
                    "momentum_trend_threshold": 0.0001,
                    "max_capital_at_risk_usd": 0.0
                }
                try:
                    cls._symbol_configs.append(SymbolConfig(**single_symbol_data))
                    cls._global_config.max_symbols_termux = 1
                    main_logger.info(f"[{Colors.CYAN}Using single symbol mode for {input_symbol}.{Colors.RESET}]")
                except ValidationError as e:
                    logging.critical(f"Input symbol configuration validation error for {input_symbol}: {e}")
                    sys.exit(1)
            else:
                raw_symbol_configs = []
                try:
                    symbol_config_path = Path(cls._global_config.symbol_config_file)
                    with open(symbol_config_path) as f:
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
                            "kline_interval": "1m",

                            "dynamic_spread": s_cfg.get("dynamic_spread", {}),
                            "inventory_skew": s_cfg.get("inventory_skew", {}),
                            "order_layers": s_cfg.get("order_layers", []),

                            **s_cfg
                        }

                        if isinstance(merged_config_data.get("dynamic_spread"), dict):
                            merged_config_data["dynamic_spread"] = DynamicSpreadConfig(**merged_config_data["dynamic_spread"])
                        else:
                             merged_config_data["dynamic_spread"] = DynamicSpreadConfig()

                        if isinstance(merged_config_data.get("inventory_skew"), dict):
                            merged_config_data["inventory_skew"] = InventorySkewConfig(**merged_config_data["inventory_skew"])
                        else:
                            merged_config_data["inventory_skew"] = InventorySkewConfig()

                        if isinstance(merged_config_data.get("order_layers"), list):
                            merged_config_data["order_layers"] = [OrderLayer(**ol) if isinstance(ol, dict) else ol for ol in merged_config_data["order_layers"]]
                        else:
                            merged_config_data["order_layers"] = [OrderLayer()]


                        cls._symbol_configs.append(SymbolConfig(**merged_config_data))

                    except ValidationError as e:
                        logging.critical(f"Symbol configuration validation error for {s_cfg.get('symbol', 'N/A')}: {e}")
                        sys.exit(1)
                    except Exception as e:
                        logging.critical(f"Unexpected error processing symbol config {s_cfg.get('symbol', 'N/A')}: {e}")
                        sys.exit(1)

            return cls._global_config, cls._symbol_configs
else:
    class ConfigManager:
        @classmethod
        def load_config(cls, prompt_for_symbol: bool = False, input_symbol: Optional[str] = None) -> Tuple[Any, List[Any]]:
            print("Configuration management skipped due to missing external libraries.")
            sys.exit(1)


GLOBAL_CONFIG = None
SYMBOL_CONFIGS = []
if EXTERNAL_LIBS_AVAILABLE:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    main_logger = logging.getLogger("market_maker_main_fallback")


def setup_logger(name_suffix: str) -> logging.Logger:
    logger_name = f"market_maker_{name_suffix}"
    logger = logging.getLogger(logger_name)
    if logger.hasHandlers():
        return logger

    log_level_str = GLOBAL_CONFIG.log_level.upper() if GLOBAL_CONFIG else "INFO"
    logger.setLevel(getattr(logging, log_level_str, logging.INFO))

    log_file_path = LOG_DIR / (GLOBAL_CONFIG.log_file if GLOBAL_CONFIG else "market_maker_live.log")

    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_formatter = logging.Formatter(
        f"{Colors.NEON_BLUE}%(asctime)s{Colors.RESET} - "
        f"{Colors.YELLOW}%(levelname)-8s{Colors.RESET} - "
        f"{Colors.MAGENTA}[%(name)s]{Colors.RESET} - %(message)s",
        datefmt="%H:%M:%S",
    )
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)

    logger.propagate = False
    return logger


def termux_notify(message: str, title: str = "Pyrmethus Bot", is_error: bool = False):
    if not EXTERNAL_LIBS_AVAILABLE:
        main_logger.debug("Termux notification skipped: External libraries not available.")
        return

    bg_color = "#000000"
    if is_error:
        text_color = "#FF0000"
        vibrate_duration = "1000"
    else:
        text_color = "#00FFFF"
        vibrate_duration = "200"
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
            check=False,
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
        main_logger.debug(f"Termux notification failed: {e}")
    except Exception as e:
        main_logger.warning(f"Unexpected error with Termux notification: {e}")


def initialize_exchange(logger: logging.Logger) -> Optional[Any]:
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
        exchange.set_sandbox_mode(False)
        exchange.load_markets()
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
        tr = pd.DataFrame()
        tr["h_l"] = high - low
        tr["h_pc"] = (high - close.shift(1)).abs()
        tr["l_pc"] = (low - close.shift(1)).abs()
        tr["tr"] = tr[["h_l", "h_pc", "l_pc"]].max(axis=1)
        return tr["tr"].rolling(window=length).mean()
else:
    def atr(high: Any, low: Any, close: Any, length: int = 14) -> Any:
        return [DECIMAL_ZERO]


def retry_api_call(
    attempts: int = API_RETRY_ATTEMPTS,
    backoff_factor: float = RETRY_BACKOFF_FACTOR,
    fatal_exceptions: Tuple[type, ...] = (ccxt.AuthenticationError, ccxt.ArgumentsRequired, ccxt.ExchangeError) if EXTERNAL_LIBS_AVAILABLE else (Exception,),
):
    def decorator(func: Callable[..., Any]):
        @wraps(func)
        def wrapper(self, *args: Any, **kwargs: Any) -> Any:
            if not EXTERNAL_LIBS_AVAILABLE:
                self.logger.critical(f"{Colors.NEON_RED}API call '{func.__name__}' skipped: External libraries not available.{Colors.RESET}")
                return None

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
                    raise
                except ccxt.BadRequest as e:
                    if "110043" in str(e):
                        logger.warning(
                            f"BadRequest (Leverage unchanged) in {func.__name__}: {e}"
                        )
                        return None
                    elif "position mode" in str(e).lower() or "margin mode" in str(e).lower():
                        logger.error(
                            f"BadRequest: Position/Margin mode error in {func.__name__}: {e}. "
                            f"This often requires manual intervention or configuration review."
                        )
                        termux_notify(f"API Error: {str(e)[:50]}...", is_error=True)
                        raise
                    logger.error(f"BadRequest in {func.__name__}: {e}")
                    termux_notify(f"API Error: {str(e)[:50]}...", is_error=True)
                    raise
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


class BybitWebSocket:
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
        self.trade_subscriptions: List[str] = []

        self.order_books: Dict[str, Dict[str, List[List[Decimal]]]] = {}
        self.recent_trades: Dict[str, List[Tuple[Decimal, Decimal, str]]] = {}

        self._stop_event = threading.Event()
        self.public_thread: Optional[threading.Thread] = None
        self.private_thread: Optional[threading.Thread] = None
        self.trade_thread: Optional[threading.Thread] = None

        self.symbol_bots: List[SymbolBot] = []

        self.lock = threading.Lock()
        self.last_orderbook_update_time: Dict[str, float] = {}
        self.last_trades_update_time: Dict[str, float] = {}

    def _generate_auth_params(self) -> Dict[str, Any]:
        expires = int((time.time() + 60) * 1000)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            f"GET/realtime{expires}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return {"op": "auth", "args": [self.api_key, expires, signature]}

    def _on_message(self, ws: websocket.WebSocketApp, message: str, is_private: bool, is_trade: bool = False):
        try:
            data = json_loads_decimal(message)
            if "topic" in data:
                with self.lock:
                    if is_trade: self._process_trade_message(data)
                    elif is_private: self._process_private_message(data)
                    else: self._process_public_message(data)
            elif "ping" in data:
                ws.send(json.dumps({"op": "pong"}))
            elif "pong" in data:
                self.logger.debug("# WS Pong received.")
        except InvalidOperation as e:
            self.logger.error(f"{Colors.NEON_RED}# WS {'Private' if is_private else 'Public'}: Decimal conversion error: {e} in message: {message[:100]}...{Colors.RESET}", exc_info=True)
        except json.JSONDecodeError as e:
            self.logger.error(f"{Colors.NEON_RED}# WS {'Private' if is_private else 'Public'}: JSON decoding error: {e} in message: {message[:100]}...{Colors.RESET}", exc_info=True)
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# WS {'Private' if is_private else 'Public'}: Unexpected error processing message: {e}{Colors.RESET}", exc_info=True)

    def _normalize_symbol_ws(self, bybit_symbol_ws: str) -> str:
        if len(bybit_symbol_ws) > 4 and bybit_symbol_ws[-4:].isupper():
             base = bybit_symbol_ws[:-4]
             quote = bybit_symbol_ws[-4:]
             return f"{base}/{quote}:{quote}"
        elif len(bybit_symbol_ws) > 3 and bybit_symbol_ws[-3:].isupper():
            return bybit_symbol_ws
        return bybit_symbol_ws

    def _process_public_message(self, data: Dict[str, Any]):
        topic = data["topic"]
        if topic.startswith("orderbook."):
            parts = topic.split(".")
            if len(parts) >= 3:
                symbol_id_ws = parts[2]
                self._update_order_book(symbol_id_ws, data["data"])
            else:
                self.logger.warning(f"WS Public: Unrecognized orderbook topic format: {topic}")
        elif topic.startswith("publicTrade."):
            parts = topic.split(".")
            if len(parts) >= 2:
                symbol_id_ws = parts[1]
                for trade_data in data["data"]:
                    price = Decimal(str(trade_data.get("p", "0")))
                    qty = Decimal(str(trade_data.get("v", "0")))
                    side = trade_data.get("S", "unknown")
                    self.recent_trades.setdefault(symbol_id_ws, []).append((price, qty, side))
                    if len(self.recent_trades[symbol_id_ws]) > 200:
                        self.recent_trades[symbol_id_ws].pop(0)
                self.last_trades_update_time[symbol_id_ws] = time.time()
            else:
                self.logger.warning(f"WS Public: Unrecognized publicTrade topic format: {topic}")

    def _process_trade_message(self, data: Dict[str, Any]):
        if data.get("topic") == "execution" and data.get("data"):
            for exec_data in data["data"]:
                exec_type = exec_data.get("execType")
                if exec_type in ["Trade", "AdlTrade", "BustTrade"]:
                    symbol_ws = exec_data.get("symbol")
                    if symbol_ws:
                        normalized_symbol = self._normalize_symbol_ws(symbol_ws)
                        for bot in self.symbol_bots:
                            if bot.symbol == normalized_symbol:
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
        topic = data["topic"]
        if topic in ["order", "execution", "position", "wallet"]:
            for item_data in data["data"]:
                symbol_ws = item_data.get("symbol")
                if symbol_ws:
                    normalized_symbol = self._normalize_symbol_ws(symbol_ws)
                    for bot in self.symbol_bots:
                        if bot.symbol == normalized_symbol:
                            if topic == "order": bot._handle_order_update(item_data)
                            elif topic == "position": bot._handle_position_update(item_data)
                            elif topic == "execution" and item_data.get("execType") in ["Trade", "AdlTrade", "BustTrade"]: bot._handle_execution_update(item_data)
                            elif topic == "wallet": pass
                            break
                    else:
                        self.logger.debug(f"Received {topic} update for unmanaged symbol: {normalized_symbol}")

    def _update_order_book(self, symbol_id_ws: str, data: Dict[str, Any]):
        if "b" in data and "a" in data:
            self.order_books[symbol_id_ws] = {
                "b": [[Decimal(str(item[0])), Decimal(str(item[1]))] for item in data["b"]],
                "a": [[Decimal(str(item[0])), Decimal(str(item[1]))] for item in data["a"]],
            }
        self.last_orderbook_update_time[symbol_id_ws] = time.time()

    def get_order_book_snapshot(self, symbol_id_ws: str) -> Optional[Dict[str, List[List[Decimal]]]]:
        with self.lock:
            return self.order_books.get(symbol_id_ws)

    def get_recent_trades_for_momentum(
        self, symbol_id_ws: str, limit: int = 100
    ) -> List[Tuple[Decimal, Decimal, str]]:
        with self.lock:
            return self.recent_trades.get(symbol_id_ws, [])[-limit:]

    def _on_error(self, ws: websocket.WebSocketApp, error: Any):
        self.logger.error(f"{Colors.NEON_RED}# WS Error: {error}{Colors.RESET}")

    def _on_close(self, ws: websocket.WebSocketApp, code: int, msg: str):
        if not self._stop_event.is_set():
            self.logger.warning(f"{Colors.YELLOW}# WS Closed: {code} - {msg}. Reconnecting...{Colors.RESET}")
        else:
            self.logger.info(f"{Colors.CYAN}# WS Closed intentionally: {code} - {msg}{Colors.RESET}")

    def _on_open(self, ws: websocket.WebSocketApp, is_private: bool, is_trade: bool = False):
        stream_type = "Trade" if is_trade else ("Private" if is_private else "Public")
        self.logger.info(f"{Colors.CYAN}# WS {stream_type} stream connected.{Colors.RESET}")

        if is_trade:
            self.ws_trade = ws
            if self.api_key and self.api_secret:
                auth_params = self._generate_auth_params()
                self.logger.debug(f"Sending auth message to Trade WS: {auth_params}")
                ws.send(json.dumps(auth_params))
                ws.send(json.dumps({"op": "subscribe", "args": self.trade_subscriptions}))
            else:
                self.logger.warning(f"{Colors.YELLOW}# Trade WebSocket streams not started due to missing API keys (if private topics).{Colors.RESET}")
        elif is_private:
            self.ws_private = ws
            if self.api_key and self.api_secret:
                auth_params = self._generate_auth_params()
                self.logger.debug(f"Sending auth message to Private WS: {auth_params}")
                ws.send(json.dumps(auth_params))
                ws.send(json.dumps({"op": "subscribe", "args": self.private_subscriptions}))
            else:
                self.logger.warning(f"{Colors.YELLOW}# Private WebSocket streams not started due to missing API keys.{Colors.RESET}")
        else:
            self.ws_public = ws
            if self.public_subscriptions: ws.send(json.dumps({"op": "subscribe", "args": self.public_subscriptions}))

    def _connect_websocket(self, url: str, is_private: bool, is_trade: bool = False):
        if self.logger.level <= logging.DEBUG: # Enable WebSocket trace logging for debugging
            websocket.enableTrace(True)
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
                ws_app.run_forever(ping_interval=20, ping_timeout=10, sslopt={"check_hostname": False})

                if not self._stop_event.is_set():
                    self.logger.info(f"WebSocket for {url} exited, attempting reconnect in {WS_RECONNECT_INTERVAL} seconds...")
                    self._stop_event.wait(WS_RECONNECT_INTERVAL)
            except Exception as e:
                self.logger.error(f"{Colors.NEON_RED}# WS Connection Error for {url}: {e}{Colors.RESET}", exc_info=True)
                if not self._stop_event.is_set():
                    self._stop_event.wait(WS_RECONNECT_INTERVAL)

    def start_streams(self, public_topics: List[str], private_topics: Optional[List[str]] = None, trade_topics: Optional[List[str]] = None):
        if not EXTERNAL_LIBS_AVAILABLE:
            self.logger.critical(f"{Colors.NEON_RED}WebSocket streams skipped: External libraries not available.{Colors.RESET}")
            return

        self.stop_streams()
        self._stop_event.clear()

        self.public_subscriptions = public_topics
        self.private_subscriptions = private_topics or []
        self.trade_subscriptions = trade_topics or []

        self.public_thread = threading.Thread(target=self._connect_websocket, args=(self.public_url, False, False), daemon=True, name="PublicWSThread")
        self.public_thread.start()

        if self.api_key and self.api_secret:
            self.private_thread = threading.Thread(target=self._connect_websocket, args=(self.private_url, True, False), daemon=True, name="PrivateWSThread")
            self.private_thread.start()
        else:
            self.logger.warning(f"{Colors.YELLOW}# Private WebSocket streams not started due to missing API keys.{Colors.RESET}")

        self.trade_thread = threading.Thread(target=self._connect_websocket, args=(self.trade_url, False, True), daemon=True, name="TradeWSThread")
        self.trade_thread.start()

        self.logger.info(f"{Colors.NEON_GREEN}# WebSocket streams have been summoned.{Colors.RESET}")

    def stop_streams(self):
        if not EXTERNAL_LIBS_AVAILABLE:
            return

        if self._stop_event.is_set():
            return

        self.logger.info(f"{Colors.YELLOW}# Signaling WebSocket streams to stop...{Colors.RESET}")
        self._stop_event.set()

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


class MarketMakerStrategy:
    def __init__(self, bot: 'SymbolBot'):
        self.bot = bot
        self.logger = bot.logger

    def generate_orders(self, symbol: str, mid_price: Decimal, orderbook: Dict[str, Any]):
        self.logger.info(f"[{symbol}] Generating orders using MarketMakerStrategy.")

        self.bot.cancel_all_orders(symbol)
        time.sleep(0.5)

        orders_to_place: List[Dict[str, Any]] = []

        current_order_qty = self.bot.get_dynamic_order_amount(mid_price)

        if current_order_qty <= DECIMAL_ZERO:
            self.logger.warning(f"[{symbol}] Calculated order quantity is zero or negative. Skipping order placement.")
            return

        price_precision = self.bot.config.price_precision
        qty_precision = self.bot.config.qty_precision

        dynamic_spread_pct = Decimal(str(self.bot.config.base_spread))
        if self.bot.config.dynamic_spread.enabled:
            atr_component = self.bot._calculate_atr(mid_price)
            dynamic_spread_pct += atr_component
            self.logger.debug(f"[{symbol}] ATR component for spread: {atr_component:.8f}")

        if self.bot.config.inventory_skew.enabled:
            inventory_skew_component = self.bot._calculate_inventory_skew(mid_price)
            dynamic_spread_pct += inventory_skew_component
            self.logger.debug(f"[{symbol}] Inventory skew component for spread: {inventory_skew_component:.8f}")

        dynamic_spread_pct = min(dynamic_spread_pct, Decimal(str(self.bot.config.max_spread)))

        self.logger.info(f"[{symbol}] Dynamic Spread: {dynamic_spread_pct * 100:.4f}%")

        bids = orderbook.get("b", [])
        asks = orderbook.get("a", [])

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

        for i, layer in enumerate(self.bot.config.order_layers):
            layer_spread = dynamic_spread_pct + Decimal(str(layer.spread_offset))
            layer_qty = current_order_qty * Decimal(str(layer.quantity_multiplier))

            bid_price = mid_price * (Decimal("1") - layer_spread)
            bid_price = self.bot._round_to_precision(bid_price, price_precision)
            bid_qty = self.bot._round_to_precision(layer_qty, qty_precision)

            sufficient_bid_liquidity = False
            for depth_level in cumulative_bids:
                if depth_level["price"] >= bid_price and depth_level["cumulative_qty"] >= bid_qty:
                    sufficient_bid_liquidity = True
                    break

            if not sufficient_bid_liquidity:
                self.logger.warning(f"[{symbol}] Insufficient bid liquidity for layer {i+1} at price {bid_price:.{price_precision if price_precision is not None else 8}f}. Skipping bid order.")
            elif bid_qty > DECIMAL_ZERO:
                orders_to_place.append({
                    'category': GLOBAL_CONFIG.category,
                    'symbol': symbol.replace("/", "").replace(":", ""),
                    'side': 'Buy',
                    'orderType': 'Limit',
                    'qty': str(bid_qty),
                    'price': str(bid_price),
                    'timeInForce': 'PostOnly',
                    'orderLinkId': f"MM_BUY_{symbol.replace('/', '')}_{int(time.time() * 1000)}_{i}",
                    'isLeverage': 1 if GLOBAL_CONFIG.category == 'linear' else 0,
                    'triggerDirection': 1
                })

            sell_price = mid_price * (Decimal("1") + layer_spread)
            sell_price = self.bot._round_to_precision(sell_price, price_precision)
            sell_qty = self.bot._round_to_precision(layer_qty, qty_precision)

            sufficient_ask_liquidity = False
            for depth_level in cumulative_asks:
                if depth_level["price"] <= sell_price and depth_level["cumulative_qty"] >= sell_qty:
                    sufficient_ask_liquidity = True
                    break

            if not sufficient_ask_liquidity:
                self.logger.warning(f"[{symbol}] Insufficient ask liquidity for layer {i+1} at price {sell_price:.{price_precision if price_precision is not None else 8}f}. Skipping ask order.")
            elif sell_qty > DECIMAL_ZERO:
                orders_to_place.append({
                    'category': GLOBAL_CONFIG.category,
                    'symbol': symbol.replace("/", "").replace(":", ""),
                    'side': 'Sell',
                    'orderType': 'Limit',
                    'qty': str(sell_qty),
                    'price': str(sell_price),
                    'timeInForce': 'PostOnly',
                    'orderLinkId': f"MM_SELL_{symbol.replace('/', '')}_{int(time.time() * 1000)}_{i}",
                    'isLeverage': 1 if GLOBAL_CONFIG.category == 'linear' else 0,
                    'triggerDirection': 2
                })

        if orders_to_place:
            self.bot.place_batch_orders(orders_to_place)
        else:
            self.logger.info(f"[{symbol}] No orders placed due to liquidity or quantity constraints.")


class SymbolBot(threading.Thread):
    def __init__(self, config: SymbolConfig, exchange: Any, ws_client: BybitWebSocket, logger: logging.Logger):
        super().__init__(name=f"SymbolBot-{config.symbol.replace('/', '_').replace(':', '')}")
        self.config: SymbolConfig = config
        self.exchange: Any = exchange
        self.ws_client: BybitWebSocket = ws_client
        self.logger: logging.Logger = logger
        self.symbol: str = config.symbol
        self._stop_event: threading.Event = threading.Event()
        self.open_orders: Dict[str, Dict[str, Any]] = {}
        self.inventory: Decimal = DECIMAL_ZERO
        self.unrealized_pnl: Decimal = DECIMAL_ZERO
        self.entry_price: Decimal = DECIMAL_ZERO
        self.symbol_info: Optional[Dict[str, Any]] = None
        self.last_atr_update: float = 0.0
        self.cached_atr: Optional[Decimal] = None
        self.last_symbol_info_refresh: float = 0.0
        self.current_leverage: Optional[int] = None
        self.last_imbalance: Decimal = DECIMAL_ZERO
        self.state_file: Path = STATE_DIR / f"{self.symbol.replace('/', '_').replace(':', '')}_state.json"
        self.today_date: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._load_state()
        with self.ws_client.lock: self.ws_client.symbol_bots.append(self)
        self.last_order_management_time: float = 0.0
        self.last_fill_time: float = 0.0
        self.fill_tracker: List[bool] = []
        self.daily_metrics: Dict[str, Any] = {}
        self.pnl_history_snapshots: List[Dict[str, Any]] = []
        self.trade_history: List[Trade] = []
        self.open_positions: List[Trade] = []
        self.strategy: MarketMakerStrategy = MarketMakerStrategy(self)

    def _load_state(self):
        self.performance_metrics = {"trades": 0, "profit": DECIMAL_ZERO, "fees": DECIMAL_ZERO, "net_pnl": DECIMAL_ZERO}
        self.trade_history = []
        self.daily_metrics = {}
        self.pnl_history_snapshots = []

        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    state_data = json_loads_decimal(f.read())
                    metrics = state_data.get("performance_metrics", {})
                    for key in ["profit", "fees", "net_pnl"]: self.performance_metrics[key] = Decimal(str(metrics.get(key, "0")))
                    self.performance_metrics["trades"] = int(metrics.get("trades", 0))

                    for trade_dict in state_data.get("trade_history", []):
                        try: self.trade_history.append(Trade(**trade_dict))
                        except (ValidationError, TypeError, InvalidOperation) as e: self.logger.error(f"[{self.symbol}] Error loading trade from state: {e}")

                    for date_str, daily_metric_dict in state_data.get("daily_metrics", {}).items():
                        converted_daily_metric_dict = {k: Decimal(v) if isinstance(v, str) and v.replace('.', '', 1).replace('-', '', 1).isdigit() else v for k, v in daily_metric_dict.items()}
                        self.daily_metrics[date_str] = converted_daily_metric_dict

                    self.pnl_history_snapshots = state_data.get("pnl_history_snapshots", [])

                self.logger.info(f"[{self.symbol}] State summoned from the archives.")
            except Exception as e:
                self.logger.error(f"{Colors.NEON_ORANGE}# Failed to summon state for {self.symbol} from '{self.state_file}'. Starting fresh. Error: {e}{Colors.RESET}", exc_info=True)
                try:
                    self.state_file.rename(f"{self.state_file}.corrupted_{int(time.time())}")
                    self.logger.warning(f"[{self.symbol}] Renamed corrupted state file.")
                except OSError as ose:
                    self.logger.warning(f"[{self.symbol}] Could not rename corrupted state file: {ose}")
        self._reset_daily_metrics_if_new_day()


    def _save_state(self):
        try:
            daily_metrics_serializable = {}
            for date, metrics in self.daily_metrics.items():
                daily_metrics_serializable[date] = {k: str(v) if isinstance(v, Decimal) else v for k, v in metrics.items()}

            state_data = {
                "performance_metrics": {k: str(v) if isinstance(v, Decimal) else v for k, v in self.performance_metrics.items()},
                "trade_history": [trade.model_dump() for trade in self.trade_history],
                "daily_metrics": daily_metrics_serializable,
                "pnl_history_snapshots": self.pnl_history_snapshots
            }
            temp_path = self.state_file.with_suffix(f".tmp_{os.getpid()}")
            with open(temp_path, "w") as f:
                json.dump(state_data, f, indent=4, cls=JsonDecimalEncoder)
            os.replace(temp_path, self.state_file)
            self.logger.info(f"[{self.symbol}] State enshrined to {self.state_file}")
        except Exception as e:
            self.logger.error(f"{Colors.NEON_RED}# Failed to enshrine state for {self.symbol}: {e}{Colors.RESET}", exc_info=True)

    def _reset_daily_metrics_if_new_day(self):
        current_utc_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not hasattr(self, 'today_date'):
            self.today_date = current_utc_date
            self.logger.warning(f"[{self.symbol}] 'today_date' not found, initializing to {self.today_date}.")

        if self.today_date != current_utc_date:
            self.logger.info(f"[{self.symbol}] New day detected. Resetting daily PnL from {self.today_date} to {current_utc_date}.")
            if self.today_date in self.daily_metrics:
                self.daily_metrics[self.today_date]["unrealized_pnl_snapshot"] = self.unrealized_pnl
            self.today_date = current_utc_date
            self.daily_metrics.setdefault(self.today_date, {"date": self.today_date, "realized_pnl": DECIMAL_ZERO, "unrealized_pnl_snapshot": DECIMAL_ZERO, "total_fees": DECIMAL_ZERO, "trades_count": 0})


    @retry_api_call()
    def _fetch_symbol_info(self) -> bool:
        try:
            market = self.exchange.market(self.symbol)
            if not market or not market.get("active"):
                self.logger.warning(f"[{self.symbol}] Symbol {self.symbol} is not active or market info missing. Pausing.")
                return False

            self.symbol_info = market
            self.config.min_qty = (
                Decimal(str(market["limits"]["amount"]["min"]))
                if market["limits"]["amount"]["min"] is not None
                else DECIMAL_ZERO
            )
            self.config.max_qty = (
                Decimal(str(market["limits"]["amount"]["max"]))
                if market["limits"]["amount"]["max"] is not None
                else Decimal("999999999")
            )
            self.config.qty_precision = int(abs(math.log10(market["precision"]["amount"])))
            self.config.price_precision = int(abs(math.log10(market["precision"]["price"])))
            self.config.min_notional = (
                Decimal(str(market["limits"]["cost"]["min"]))
                if market["limits"]["cost"]["min"] is not None
                else DECIMAL_ZERO
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
            )
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
        normalized_symbol_bybit = self.symbol.replace("/", "").replace(":", "")
        try:
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

            current_position_mode_idx = None
            if positions_info:
                for p in positions_info:
                    if p["symbol"] == self.symbol and "info" in p and "positionIdx" in p["info"]:
                        current_position_mode_idx = int(p["info"]["positionIdx"])
                        break

            if current_position_mode_idx != 0:
                self.logger.info(
                    f"[{self.symbol}] Current position mode is not One-Way ({current_position_mode_idx}). "
                    f"Attempting to switch to One-Way (mode 0)."
                )
                self.exchange.set_position_mode(hedged=False, symbol=self.symbol)
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
            return DECIMAL_ZERO

    def _handle_order_update(self, order_data: Dict[str, Any]):
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

                        if close_side == "sell":
                            valid_bids = bids_df[bids_df["price"] >= mid_price * Decimal("0.99")].sort_values(by="price", ascending=False)
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

                        elif close_side == "buy":
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
        if not self.config.inventory_skew.enabled or self.inventory == DECIMAL_ZERO:
            return DECIMAL_ZERO

        normalized_inventory = self.inventory / Decimal(str(self.config.inventory_limit))
        skew_component = normalized_inventory * Decimal(str(self.config.inventory_skew.skew_factor))

        max_skew_abs = Decimal(str(self.config.inventory_skew.max_skew)) if self.config.inventory_skew.max_skew is not None else Decimal("0.001")
        skew_component = max(min(skew_component, max_skew_abs), -max_skew_abs)

        return abs(skew_component)

    def get_dynamic_order_amount(self, mid_price: Decimal) -> Decimal:
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
        value_dec = Decimal(str(value))
        if precision is not None and precision >= 0:
            return value_dec.quantize(Decimal(f'1e-{precision}'), rounding=ROUND_HALF_UP)
        return value_dec.quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    @retry_api_call()
    def place_batch_orders(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
            if GLOBAL_CONFIG.use_batch_orders_for_refresh and hasattr(self.exchange, 'create_orders'):
                responses = self.exchange.create_orders(filtered_orders)
            else:
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
                        responses.append({'info': {'retCode': -1, 'retMsg': str(e_single)}})

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
        try:
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
        if not self.config.enable_auto_sl_tp:
            return

        if abs(self.inventory) == DECIMAL_ZERO:
            self.logger.debug(f"[{self.symbol}] No open position to set TP/SL for.")
            return

        take_profit_price = DECIMAL_ZERO
        stop_loss_price = DECIMAL_ZERO

        if self.inventory > DECIMAL_ZERO:
            take_profit_price = self.entry_price * (Decimal("1") + Decimal(str(self.config.take_profit_target_pct)))
            stop_loss_price = self.entry_price * (Decimal("1") - Decimal(str(self.config.stop_loss_trigger_pct)))
        elif self.inventory < DECIMAL_ZERO:
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
                'positionIdx': 0
            }
            self.exchange.set_trading_stop(
                self.symbol,
                price=None,
                stopLossPrice=float(stop_loss_price),
                takeProfitPrice=float(take_profit_price),
                params=params
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
            if self.config.trade_enabled:
                self.logger.warning(
                    f"{Colors.NEON_ORANGE}[{self.symbol}] Market data stale! "
                    f"Order book stale: {orderbook_stale}, Trades stale: {trades_stale}. "
                    f"Pausing quoting and cancelling orders.{Colors.RESET}"
                )
                self.cancel_all_orders(self.symbol)
            return False
        return True

    def _check_and_handle_stale_orders(self):
        current_time = time.time()
        orders_to_cancel = []
        with self.ws_client.lock:
            for client_order_id, order_info in list(self.open_orders.items()):
                placement_time_seconds = order_info["timestamp"] / 1000
                if (current_time - placement_time_seconds) > self.config.stale_order_max_age_seconds:
                    orders_to_cancel.append((order_info["exchange_id"], client_order_id))

        for exchange_id, client_order_id in orders_to_cancel:
            self.logger.warning(
                f"[{self.symbol}] Order {client_order_id} is stale (open for "
                f"> {self.config.stale_order_max_age_seconds} seconds). Cancelling."
            )
            self.cancel_order(exchange_id, client_order_id)

    def _check_daily_pnl_limits(self) -> bool:
        if not GLOBAL_CONFIG.daily_pnl_stop_loss_pct and not GLOBAL_CONFIG.daily_pnl_take_profit_pct:
            return False

        self._reset_daily_metrics_if_new_day()
        current_daily_metrics = self.daily_metrics.setdefault(self.today_date, {"date": self.today_date, "realized_pnl": DECIMAL_ZERO, "unrealized_pnl_snapshot": DECIMAL_ZERO, "total_fees": DECIMAL_ZERO, "trades_count": 0})

        realized_pnl_today = current_daily_metrics.get("realized_pnl", DECIMAL_ZERO)
        total_pnl_today = realized_pnl_today + self.unrealized_pnl - current_daily_metrics.get("total_fees", DECIMAL_ZERO)

        total_balance = self.get_account_balance()
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
        self.logger.info(f"{Colors.CYAN}[{self.symbol}] SymbolBot starting.{Colors.RESET}")

        if not self._fetch_symbol_info():
            self.logger.critical(f"{Colors.NEON_RED}[{self.symbol}] Failed to fetch symbol info. Stopping bot.{Colors.RESET}")
            termux_notify(f"{self.symbol}: Init Failed (Symbol Info)", is_error=True)
            self._stop_event.set()
            return

        if GLOBAL_CONFIG.category == "linear":
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

        input_symbol = None
        last_status_display_time = time.time()
        last_order_refresh_time = time.time()

        while not self._stop_event.is_set():
            try:
                current_time = time.time()

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

                if self._check_daily_pnl_limits():
                    self.logger.warning(f"[{self.symbol}] Daily PnL limits hit. Trading disabled for today.")
                    self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL)
                    continue

                if self.config.trade_enabled:
                    if (current_time - last_order_refresh_time) >= self.config.order_refresh_time:
                        self.strategy.generate_orders(self.symbol, mid_price, orderbook)
                        last_order_refresh_time = current_time

                    self._check_and_handle_stale_orders()

                else:
                    self.logger.debug(f"[{self.symbol}] Trading disabled. Skipping order generation.")
                    self.cancel_all_orders(self.symbol)

                if (current_time - last_status_display_time) >= STATUS_UPDATE_INTERVAL:
                    self._display_status()
                    last_status_display_time = current_time
                    self._save_state()

            except Exception as e:
                self.logger.error(f"{Colors.NEON_RED}[{self.symbol}] Unexpected error in main loop: {e}{Colors.RESET}", exc_info=True)
                termux_notify(f"{self.symbol}: Bot Error: {str(e)[:50]}...", is_error=True)

            self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL)

        self.logger.info(f"{Colors.CYAN}[{self.symbol}] SymbolBot stopping. Cancelling all orders and saving state.{Colors.RESET}")
        self.cancel_all_orders(self.symbol)
        self._save_state()
        with self.ws_client.lock:
            if self in self.ws_client.symbol_bots:
                self.ws_client.symbol_bots.remove(self)

    def stop(self):
        self.logger.info(f"{Colors.YELLOW}[{self.symbol}] Signaling SymbolBot to stop.{Colors.RESET}")
        self._stop_event.set()


class PyrmethusBot:
    def __init__(self):
        global main_logger
        if EXTERNAL_LIBS_AVAILABLE:
            if main_logger.name == "market_maker_main_fallback":
                main_logger = setup_logger("main")
        self.logger = main_logger

        self.exchange: Optional[Any] = None
        self.ws_client: Optional[BybitWebSocket] = None
        self.symbol_bots: Dict[str, SymbolBot] = {}
        self.active_symbol_configs: Dict[str, SymbolConfig] = {}
        self._stop_event = threading.Event()
        self.config_manager_thread: Optional[threading.Thread] = None
        self.last_config_check_time: float = 0.0

    def _initialize_exchange_and_ws(self):
        self.exchange = initialize_exchange(self.logger)
        if not self.exchange:
            self.logger.critical(f"{Colors.NEON_RED}Exchange initialization failed. Exiting.{Colors.RESET}")
            sys.exit(1)

        is_testnet = os.getenv("BYBIT_TESTNET", "False").lower() == "true"
        if is_testnet:
            self.logger.warning(f"{Colors.YELLOW}Running in TESTNET mode!{Colors.RESET}")
            self.exchange.set_sandbox_mode(True)

        self.ws_client = BybitWebSocket(BYBIT_API_KEY, BYBIT_API_SECRET, is_testnet, self.logger)

    def _start_symbol_bots(self, symbol_configs: List[SymbolConfig]):
        if not self.exchange or not self.ws_client:
            self.logger.critical(f"{Colors.NEON_RED}Exchange or WebSocket client not initialized. Cannot start SymbolBots.{Colors.RESET}")
            return

        new_public_topics: List[str] = []
        new_private_topics: List[str] = ["order", "execution", "position"]
        new_trade_topics: List[str] = ["execution", "order", "position"]

        active_configs_to_start = []
        for cfg in symbol_configs:
            if cfg.trade_enabled:
                active_configs_to_start.append(cfg)

        active_configs_to_start = sorted(active_configs_to_start, key=lambda x: x.symbol)[:GLOBAL_CONFIG.max_symbols_termux]

        symbols_in_new_config = {cfg.symbol for cfg in active_configs_to_start}

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
                self.active_symbol_configs[config.symbol] = config
                bot.start()

            elif self.active_symbol_configs.get(config.symbol) != config:
                self.logger.info(f"{Colors.YELLOW}Configuration for {config.symbol} changed. Restarting SymbolBot...{Colors.RESET}")
                self.symbol_bots[config.symbol].stop()
                self.symbol_bots[config.symbol].join(timeout=10)
                if self.symbol_bots[config.symbol].is_alive():
                    self.logger.warning(f"[{config.symbol}] SymbolBot did not stop gracefully.")

                del self.symbol_bots[config.symbol]

                bot = SymbolBot(config, self.exchange, self.ws_client, setup_logger(config.symbol.replace('/', '_').replace(':', '')))
                self.symbol_bots[config.symbol] = bot
                self.active_symbol_configs[config.symbol] = config
                bot.start()

            symbol_id_ws = config.symbol.replace("/", "").replace(":", "")
            new_public_topics.append(f"orderbook.50.{symbol_id_ws}")
            new_public_topics.append(f"publicTrade.{symbol_id_ws}")

        current_public_subscriptions = sorted(self.ws_client.public_subscriptions)
        current_private_subscriptions = sorted(self.ws_client.private_subscriptions)
        current_trade_subscriptions = sorted(self.ws_client.trade_subscriptions)

        new_public_topics_set = sorted(list(set(new_public_topics)))
        new_private_topics_set = sorted(list(set(new_private_topics)))
        new_trade_topics_set = sorted(list(set(new_trade_topics)))

        if new_public_topics_set != current_public_subscriptions or \
           new_private_topics_set != current_private_subscriptions or \
           new_trade_topics_set != current_trade_subscriptions:
            self.logger.info(f"{Colors.MAGENTA}Updating WebSocket subscriptions...{Colors.RESET}")
            self.ws_client.stop_streams()
            self.ws_client.start_streams(new_public_topics_set, new_private_topics_set, new_trade_topics_set)
        else:
            self.logger.debug("WebSocket subscriptions are up to date.")

    def _stop_symbol_bots(self):
        self.logger.info(f"{Colors.YELLOW}Signaling all SymbolBots to stop...{Colors.RESET}")
        for symbol, bot in list(self.symbol_bots.items()):
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
        while not self._stop_event.is_set():
            try:
                if (time.time() - self.last_config_check_time) > 60:
                    self.logger.info(f"{Colors.CYAN}Periodically checking for symbol configuration changes...{Colors.RESET}")

                    global GLOBAL_CONFIG, SYMBOL_CONFIGS
                    global_cfg_reloaded, symbol_configs_reloaded = ConfigManager.load_config(prompt_for_symbol=False)

                    if global_cfg_reloaded != GLOBAL_CONFIG:
                        self.logger.info(f"{Colors.YELLOW}Global configuration changed. Applying updates.{Colors.RESET}")
                        GLOBAL_CONFIG = global_cfg_reloaded
                        self.logger = setup_logger("main")

                    SYMBOL_CONFIGS = symbol_configs_reloaded

                    self._start_symbol_bots(SYMBOL_CONFIGS)
                    self.last_config_check_time = time.time()

            except Exception as e:
                self.logger.error(f"{Colors.NEON_RED}Error in config manager thread: {e}{Colors.RESET}", exc_info=True)

            self._stop_event.wait(MAIN_LOOP_SLEEP_INTERVAL * 5)

    def run(self):
        self.logger.info(f"{Colors.NEON_GREEN}Pyrmethus Market Maker Bot starting...{Colors.RESET}")

        try:
            selected_mode = input(
                f"{Colors.CYAN}Choose mode:\n"
                f"  [f]rom file (symbols.json) - for multi-symbol operation\n"
                f"  [s]ingle symbol (e.g., BTC/USDT:USDT) - for interactive, quick run\n"
                f"Enter choice (f/s): {Colors.RESET}"
            ).lower().strip()
        except EOFError:
            self.logger.warning(f"{Colors.YELLOW}No interactive input detected. Using default single symbol mode (BTC/USDT:USDT).{Colors.RESET}")
            selected_mode = 's'
            input_symbol: Optional[str] = 'BTC/USDT:USDT'

        if selected_mode == 's':
            if 'input_symbol' not in locals() or input_symbol is None:
                try:
                    input_symbol = input(f"{Colors.CYAN}Enter single symbol (e.g., BTC/USDT:USDT): {Colors.RESET}").upper().strip()
                except EOFError:
                    self.logger.warning(f"{Colors.YELLOW}No interactive input for symbol. Using default BTC/USDT:USDT.{Colors.RESET}")
                    input_symbol = 'BTC/USDT:USDT'

            if not input_symbol:
                self.logger.critical(f"{Colors.NEON_RED}No symbol entered. Exiting.{Colors.RESET}")
                sys.exit(1)

        global GLOBAL_CONFIG, SYMBOL_CONFIGS
        try:
            GLOBAL_CONFIG, SYMBOL_CONFIGS = ConfigManager.load_config(
                prompt_for_symbol=(selected_mode == 's'),
                input_symbol=input_symbol
            )
            self.logger = setup_logger("main")
        except SystemExit:
            self.logger.critical(f"{Colors.NEON_RED}Configuration loading failed. Exiting.{Colors.RESET}")
            sys.exit(1)
        except Exception as e:
            self.logger.critical(f"{Colors.NEON_RED}Unexpected error during configuration loading: {e}. Exiting.{Colors.RESET}", exc_info=True)
            sys.exit(1)

        self._initialize_exchange_and_ws()

        initial_public_topics = []
        initial_private_topics = ["position", "execution", "order"]
        initial_trade_topics = ["execution", "order", "position"]

        for symbol_config in SYMBOL_CONFIGS:
            normalized_symbol = symbol_config.symbol.replace("/", "").replace(":", "")
            initial_public_topics.append(f"orderbook.50.{normalized_symbol}")
            initial_public_topics.append(f"publicTrade.{normalized_symbol}")

        self.ws_client.start_streams(initial_public_topics, initial_private_topics, initial_trade_topics)

        self.config_manager_thread = threading.Thread(target=self._manage_active_symbol_bots_periodically, daemon=True, name="ConfigManagerThread")
        self.config_manager_thread.start()

        self._start_symbol_bots(SYMBOL_CONFIGS)

        try:
            self.logger.info(f"{Colors.NEON_GREEN}Pyrmethus Bot is now operational. Press Ctrl+C to stop.{Colors.RESET}")
            while not self._stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info(f"{Colors.YELLOW}Ctrl+C detected. Initiating graceful shutdown...{Colors.RESET}")
        except Exception as e:
            self.logger.critical(f"{Colors.NEON_RED}An unhandled error occurred in the main bot process: {e}{Colors.RESET}", exc_info=True)
            termux_notify("Pyrmethus Bot CRASHED!", is_error=True)
        finally:
            self._stop_event.set()
            self.logger.info(f"{Colors.CYAN}Stopping all SymbolBots and WebSocket streams.{Colors.RESET}")
            self._stop_symbol_bots()
            if self.config_manager_thread and self.config_manager_thread.is_alive():
                self.config_manager_thread.join(timeout=10)
            self.logger.info(f"{Colors.NEON_GREEN}Pyrmethus Market Maker Bot gracefully shut down.{Colors.RESET}")


if __name__ == "__main__":
    if not EXTERNAL_LIBS_AVAILABLE:
        print("Required libraries are not available. Cannot run the bot.")
        sys.exit(1)

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    main_logger = logging.getLogger("market_maker_main_temp")

    bot_instance: Optional[PyrmethusBot] = None
    def handle_sigterm(signum, frame):
        main_logger.info(f"{Colors.YELLOW}SIGTERM ({signum}) received. Initiating graceful shutdown...{Colors.RESET}")
        if bot_instance is not None:
            bot_instance._stop_event.set()
        else:
            main_logger.warning("Bot instance not found for SIGTERM handling.")

    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        bot_instance = PyrmethusBot()
        bot_instance.run()
    except Exception as e:
        main_logger.critical(f"{Colors.NEON_RED}Pyrmethus Bot encountered a critical error: {e}{Colors.RESET}", exc_info=True)
        termux_notify("Pyrmethus Bot CRASHED!", is_error=True)
        sys.exit(1)
