# pyrmethus_volumatic_bot.py
# Enhanced trading bot incorporating the Volumatic Trend and Pivot Order Block strategy
# with advanced position management (SL/TP, BE, TSL) for Bybit V5 (Linear/Inverse).
# Version 1.3.0: Implemented core strategy logic (VT, Pivots, OBs, Signals),
#               position management (BE, TSL activation), multi-request kline fetching,
#               order cancellation helper, SIGTERM handling, and general refinements.

"""
Pyrmethus Volumatic Bot: A Python Trading Bot for Bybit V5 (v1.3.0)

Implements Volumatic Trend + Pivot Order Block strategy with advanced management.

Key Features:
- Bybit V5 API (Linear/Inverse, Sandbox/Live)
- Volumatic Trend Calculation (EMA/SWMA, ATR Bands, Volume Norm)
- Pivot High/Low Detection (Wicks/Body, Lookbacks)
- Order Block Identification & Management (Active, Violated, Extend, Max Boxes)
- Signal Generation (Trend + OB Proximity/Violation)
- Risk-based Position Sizing (Decimal precision, Market Limits)
- Leverage Setting
- Market Order Execution
- Advanced Position Management:
    - Initial SL/TP (ATR-based)
    - Trailing Stop Loss (TSL) Activation (Percentage-based trigger, Callback rate distance)
    - Break-Even (BE) Stop Adjustment (ATR-based profit target, Tick offset)
- Robust API Interaction (Retries, Error Handling, Bybit Codes)
- Multi-Request Kline Fetching (Handles limits > API max)
- Secure Credentials (.env)
- Flexible Configuration (config.json, Validation, Defaults, Auto-Update)
- Detailed Logging (Neon Console, Rotating File Logs, Redaction)
- Graceful Shutdown (Ctrl+C, SIGTERM)
- Sequential Multi-Pair Processing
"""

# --- Core Libraries ---
import hashlib
import hmac
import json
import logging
import math
import os
import re # Needed for error code parsing
import signal # For SIGTERM handling
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP, getcontext, InvalidOperation
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional, Tuple, TypedDict, Union
# Use zoneinfo for modern timezone handling (requires tzdata package)
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    print(f"{Fore.YELLOW}Warning: 'zoneinfo' module not found. Falling back to UTC. "
          f"For timezone support, ensure Python 3.9+ and install 'tzdata' (`pip install tzdata`).{Style.RESET_ALL}")
    class ZoneInfo: # type: ignore
        def __init__(self, key: str):
            if key != "UTC":
                 print(f"{Fore.YELLOW}Requested timezone '{key}' unavailable, using UTC.{Style.RESET_ALL}")
            self._key = "UTC"
        def __call__(self, dt: Optional[datetime] = None) -> Optional[datetime]:
            if dt: return dt.replace(tzinfo=timezone.utc)
            return None
        def fromutc(self, dt: datetime) -> datetime:
            return dt.replace(tzinfo=timezone.utc)
        def utcoffset(self, dt: Optional[datetime]) -> Optional[timedelta]:
            return timedelta(0)
        def dst(self, dt: Optional[datetime]) -> Optional[timedelta]:
            return timedelta(0)
        def tzname(self, dt: Optional[datetime]) -> Optional[str]:
            return "UTC"
    class ZoneInfoNotFoundError(Exception): pass


# --- Dependencies (Install via pip) ---
import numpy as np # Requires numpy (pip install numpy)
import pandas as pd # Requires pandas (pip install pandas)
import pandas_ta as ta # Requires pandas_ta (pip install pandas_ta)
import requests # Requires requests (pip install requests)
import ccxt # Requires ccxt (pip install ccxt)
from colorama import Fore, Style, init as colorama_init # Requires colorama (pip install colorama)
from dotenv import load_dotenv # Requires python-dotenv (pip install python-dotenv)

# --- Initialize Environment and Settings ---
getcontext().prec = 28 # Set Decimal precision globally
colorama_init(autoreset=True) # Initialize Colorama
load_dotenv() # Load .env file

# --- Constants ---
BOT_VERSION = "1.3.0" # <<<< Version Updated >>>>

# API Credentials
API_KEY: Optional[str] = os.getenv("BYBIT_API_KEY")
API_SECRET: Optional[str] = os.getenv("BYBIT_API_SECRET")
if not API_KEY or not API_SECRET:
    print(f"{Fore.RED}{Style.BRIGHT}FATAL: BYBIT_API_KEY and BYBIT_API_SECRET must be set in the .env file. The arcane seals are incomplete! Exiting.{Style.RESET_ALL}")
    sys.exit(1)

# Configuration and Logging
CONFIG_FILE: str = "config.json"
LOG_DIRECTORY: str = "bot_logs"
DEFAULT_TIMEZONE_STR: str = "America/Chicago"
TIMEZONE_STR: str = os.getenv("TIMEZONE", DEFAULT_TIMEZONE_STR)
try:
    TIMEZONE = ZoneInfo(TIMEZONE_STR)
except ZoneInfoNotFoundError:
    print(f"{Fore.RED}Timezone '{TIMEZONE_STR}' not found. Install 'tzdata' (`pip install tzdata`) or check name. Using UTC fallback.{Style.RESET_ALL}")
    TIMEZONE = ZoneInfo("UTC")
    TIMEZONE_STR = "UTC"
except Exception as tz_err:
    print(f"{Fore.RED}Failed to initialize timezone '{TIMEZONE_STR}'. Error: {tz_err}. Using UTC fallback.{Style.RESET_ALL}")
    TIMEZONE = ZoneInfo("UTC")
    TIMEZONE_STR = "UTC"

# API Interaction Settings
MAX_API_RETRIES: int = 3
RETRY_DELAY_SECONDS: int = 5
POSITION_CONFIRM_DELAY_SECONDS: int = 8
LOOP_DELAY_SECONDS: int = 15
BYBIT_API_KLINE_LIMIT: int = 1000 # Max klines per Bybit V5 request

# Timeframes Mapping
VALID_INTERVALS: List[str] = ["1", "3", "5", "15", "30", "60", "120", "240", "D", "W", "M"]
CCXT_INTERVAL_MAP: Dict[str, str] = {
    "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
    "60": "1h", "120": "2h", "240": "4h", "D": "1d", "W": "1w", "M": "1M"
}

# Data Handling Limits
DEFAULT_FETCH_LIMIT: int = 750
MAX_DF_LEN: int = 2000 # Max DataFrame length to keep in memory

# Strategy Defaults
DEFAULT_VT_LENGTH: int = 40
DEFAULT_VT_ATR_PERIOD: int = 200
DEFAULT_VT_VOL_EMA_LENGTH: int = 950
DEFAULT_VT_ATR_MULTIPLIER: float = 3.0
DEFAULT_VT_STEP_ATR_MULTIPLIER: float = 4.0 # Unused
DEFAULT_OB_SOURCE: str = "Wicks" # "Wicks" or "Body"
DEFAULT_PH_LEFT: int = 10
DEFAULT_PH_RIGHT: int = 10
DEFAULT_PL_LEFT: int = 10
DEFAULT_PL_RIGHT: int = 10
DEFAULT_OB_EXTEND: bool = True
DEFAULT_OB_MAX_BOXES: int = 50

# Global Quote Currency (updated by load_config)
QUOTE_CURRENCY: str = "USDT"

# Logging Colors
NEON_GREEN: str = Fore.LIGHTGREEN_EX
NEON_BLUE: str = Fore.CYAN
NEON_PURPLE: str = Fore.MAGENTA
NEON_YELLOW: str = Fore.YELLOW
NEON_RED: str = Fore.LIGHTRED_EX
NEON_CYAN: str = Fore.CYAN
RESET: str = Style.RESET_ALL
BRIGHT: str = Style.BRIGHT
DIM: str = Style.DIM

# Ensure log directory exists
try:
    os.makedirs(LOG_DIRECTORY, exist_ok=True)
except OSError as e:
     print(f"{NEON_RED}{BRIGHT}FATAL: Could not create log directory '{LOG_DIRECTORY}': {e}. Ensure permissions are correct.{RESET}")
     sys.exit(1)

# Global flag for shutdown signal
_shutdown_requested = False

# --- Type Definitions ---
class OrderBlock(TypedDict):
    """Represents a bullish or bearish Order Block identified on the chart."""
    id: str                 # Unique identifier (e.g., "B_1678886400000")
    type: str               # 'bull' or 'bear'
    timestamp: pd.Timestamp # Timestamp of the candle that formed the OB (pivot candle)
    top: Decimal            # Top price level of the OB
    bottom: Decimal         # Bottom price level of the OB
    active: bool            # True if the OB is currently considered valid
    violated: bool          # True if the price has closed beyond the OB boundary
    violation_ts: Optional[pd.Timestamp] # Timestamp when violation occurred
    extended_to_ts: Optional[pd.Timestamp] # Timestamp the OB box currently extends to

class StrategyAnalysisResults(TypedDict):
    """Structured results from the strategy analysis process."""
    dataframe: pd.DataFrame             # The DataFrame with all calculated indicators (Decimal values)
    last_close: Decimal                 # The closing price of the most recent candle
    current_trend_up: Optional[bool]    # True if Volumatic Trend is up, False if down, None if undetermined
    trend_just_changed: bool            # True if the trend flipped on the last candle
    active_bull_boxes: List[OrderBlock] # List of currently active bullish OBs
    active_bear_boxes: List[OrderBlock] # List of currently active bearish OBs
    vol_norm_int: Optional[int]         # Normalized volume indicator (0-100+, integer) for the last candle
    atr: Optional[Decimal]              # ATR value for the last candle (must be positive)
    upper_band: Optional[Decimal]       # Volumatic Trend upper band value for the last candle
    lower_band: Optional[Decimal]       # Volumatic Trend lower band value for the last candle
    signal: str                         # "BUY", "SELL", "EXIT_LONG", "EXIT_SHORT", or "NONE"

class MarketInfo(TypedDict):
    """Standardized market information dictionary derived from ccxt.market."""
    id: str; symbol: str; base: str; quote: str; settle: Optional[str]
    baseId: str; quoteId: str; settleId: Optional[str]
    type: str; spot: bool; margin: bool; swap: bool; future: bool; option: bool; active: bool
    contract: bool; linear: Optional[bool]; inverse: Optional[bool]; quanto: Optional[bool]
    taker: float; maker: float; contractSize: Optional[Any]
    expiry: Optional[int]; expiryDatetime: Optional[str]; strike: Optional[float]; optionType: Optional[str]
    precision: Dict[str, Any]; limits: Dict[str, Any]; info: Dict[str, Any]
    # Custom added fields
    is_contract: bool; is_linear: bool; is_inverse: bool; contract_type_str: str
    min_amount_decimal: Optional[Decimal]; max_amount_decimal: Optional[Decimal]
    min_cost_decimal: Optional[Decimal]; max_cost_decimal: Optional[Decimal]
    amount_precision_step_decimal: Optional[Decimal]; price_precision_step_decimal: Optional[Decimal]
    contract_size_decimal: Decimal

class PositionInfo(TypedDict):
    """Standardized position information dictionary derived from ccxt.position."""
    id: Optional[str]; symbol: str; timestamp: Optional[int]; datetime: Optional[str]
    contracts: Optional[float]; contractSize: Optional[Any]; side: Optional[str]
    notional: Optional[Any]; leverage: Optional[Any]; unrealizedPnl: Optional[Any]; realizedPnl: Optional[Any]
    collateral: Optional[Any]; entryPrice: Optional[Any]; markPrice: Optional[Any]; liquidationPrice: Optional[Any]
    marginMode: Optional[str]; hedged: Optional[bool]; maintenanceMargin: Optional[Any]; maintenanceMarginPercentage: Optional[float]
    initialMargin: Optional[Any]; initialMarginPercentage: Optional[float]; marginRatio: Optional[float]
    lastUpdateTimestamp: Optional[int]; info: Dict[str, Any]
    # Custom added/parsed fields
    size_decimal: Decimal
    stopLossPrice: Optional[str]; takeProfitPrice: Optional[str]
    trailingStopLoss: Optional[str]; tslActivationPrice: Optional[str]
    # Custom flags for bot state tracking
    be_activated: bool # True if Break-Even has been set for this position instance
    tsl_activated: bool # True if Trailing Stop Loss has been set for this position instance


# --- Configuration Loading & Validation ---
class SensitiveFormatter(logging.Formatter):
    """Redacts sensitive API keys/secrets from log messages."""
    _api_key_placeholder = "***API_KEY***"
    _api_secret_placeholder = "***API_SECRET***"
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        key = API_KEY; secret = API_SECRET
        try:
            if key and isinstance(key, str) and key in msg: msg = msg.replace(key, self._api_key_placeholder)
            if secret and isinstance(secret, str) and secret in msg: msg = msg.replace(secret, self._api_secret_placeholder)
        except Exception: pass
        return msg

def setup_logger(name: str) -> logging.Logger:
    """Sets up a dedicated logger instance with console and file handlers."""
    safe_name = name.replace('/', '_').replace(':', '-')
    logger_name = f"pyrmethus_bot_{safe_name}"
    log_filename = os.path.join(LOG_DIRECTORY, f"{logger_name}.log")
    logger = logging.getLogger(logger_name)
    if logger.hasHandlers(): return logger
    logger.setLevel(logging.DEBUG)

    # File Handler (DEBUG, Rotating, Redaction, UTC)
    try:
        fh = RotatingFileHandler(log_filename, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        ff = SensitiveFormatter("%(asctime)s.%(msecs)03d %(levelname)-8s [%(name)s:%(lineno)d] %(message)s", datefmt='%Y-%m-%d %H:%M:%S')
        ff.converter = time.gmtime # type: ignore
        fh.setFormatter(ff); fh.setLevel(logging.DEBUG); logger.addHandler(fh)
    except Exception as e: print(f"{NEON_RED}Error setting up file logger '{log_filename}': {e}{RESET}")

    # Console Handler (Configurable Level, Neon Colors, Local Timezone)
    try:
        sh = logging.StreamHandler(sys.stdout)
        level_colors = { logging.DEBUG: NEON_CYAN + DIM, logging.INFO: NEON_BLUE, logging.WARNING: NEON_YELLOW, logging.ERROR: NEON_RED, logging.CRITICAL: NEON_RED + BRIGHT }
        class NeonConsoleFormatter(SensitiveFormatter):
            _level_colors = level_colors; _tz = TIMEZONE
            def format(self, record: logging.LogRecord) -> str:
                level_color = self._level_colors.get(record.levelno, NEON_BLUE)
                log_fmt = f"{NEON_BLUE}%(asctime)s{RESET} - {level_color}%(levelname)-8s{RESET} - {NEON_PURPLE}[%(name)s]{RESET} - %(message)s"
                formatter = logging.Formatter(log_fmt, datefmt='%H:%M:%S')
                formatter.converter = lambda *args: datetime.now(self._tz).timetuple() # type: ignore
                return super(NeonConsoleFormatter, self).format(record)
        sh.setFormatter(NeonConsoleFormatter())
        log_level_str = os.getenv("CONSOLE_LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        sh.setLevel(log_level); logger.addHandler(sh)
    except Exception as e: print(f"{NEON_RED}Error setting up console logger: {e}{RESET}")

    logger.propagate = False
    return logger

init_logger = setup_logger("init")
init_logger.info(f"{Fore.MAGENTA}Pyrmethus Volumatic Bot v{BOT_VERSION} awakening...{Style.RESET_ALL}")
init_logger.info(f"Using Timezone: {TIMEZONE_STR}")

def _ensure_config_keys(config: Dict[str, Any], default_config: Dict[str, Any], parent_key: str = "") -> Tuple[Dict[str, Any], bool]:
    """Recursively ensures config keys exist, adding defaults if missing."""
    updated_config = config.copy(); changed = False
    for key, default_value in default_config.items():
        full_key_path = f"{parent_key}.{key}" if parent_key else key
        if key not in updated_config:
            updated_config[key] = default_value; changed = True
            init_logger.info(f"{NEON_YELLOW}Config Spell: Added missing parameter '{full_key_path}' with default enchantment: {repr(default_value)}{RESET}")
        elif isinstance(default_value, dict) and isinstance(updated_config.get(key), dict):
            nested_config, nested_changed = _ensure_config_keys(updated_config[key], default_value, full_key_path)
            if nested_changed: updated_config[key] = nested_config; changed = True
    return updated_config, changed

def load_config(filepath: str) -> Dict[str, Any]:
    """Loads, validates, and potentially updates configuration from a JSON file."""
    init_logger.info(f"{Fore.CYAN}# Conjuring configuration from '{filepath}'...{Style.RESET_ALL}")
    default_config = {
        "trading_pairs": ["BTC/USDT"], "interval": "5", "retry_delay": RETRY_DELAY_SECONDS,
        "fetch_limit": DEFAULT_FETCH_LIMIT, "orderbook_limit": 25, "enable_trading": False,
        "use_sandbox": True, "risk_per_trade": 0.01, "leverage": 20, "max_concurrent_positions": 1,
        "quote_currency": "USDT", "loop_delay_seconds": LOOP_DELAY_SECONDS,
        "position_confirm_delay_seconds": POSITION_CONFIRM_DELAY_SECONDS,
        "strategy_params": {
            "vt_length": DEFAULT_VT_LENGTH, "vt_atr_period": DEFAULT_VT_ATR_PERIOD,
            "vt_vol_ema_length": DEFAULT_VT_VOL_EMA_LENGTH, "vt_atr_multiplier": float(DEFAULT_VT_ATR_MULTIPLIER),
            "vt_step_atr_multiplier": float(DEFAULT_VT_STEP_ATR_MULTIPLIER), # Unused
            "ob_source": DEFAULT_OB_SOURCE, "ph_left": DEFAULT_PH_LEFT, "ph_right": DEFAULT_PH_RIGHT,
            "pl_left": DEFAULT_PL_LEFT, "pl_right": DEFAULT_PL_RIGHT, "ob_extend": DEFAULT_OB_EXTEND,
            "ob_max_boxes": DEFAULT_OB_MAX_BOXES, "ob_entry_proximity_factor": 1.005,
            "ob_exit_proximity_factor": 1.001
        },
        "protection": {
             "enable_trailing_stop": True, "trailing_stop_callback_rate": 0.005,
             "trailing_stop_activation_percentage": 0.003, "enable_break_even": True,
             "break_even_trigger_atr_multiple": 1.0, "break_even_offset_ticks": 2,
             "initial_stop_loss_atr_multiple": 1.8, "initial_take_profit_atr_multiple": 0.7
        }
    }
    config_needs_saving: bool = False; loaded_config: Dict[str, Any] = {}

    if not os.path.exists(filepath):
        init_logger.warning(f"{NEON_YELLOW}Config scroll '{filepath}' not found. Crafting a default scroll.{RESET}")
        try:
            with open(filepath, "w", encoding="utf-8") as f: json.dump(default_config, f, indent=4, ensure_ascii=False)
            init_logger.info(f"{NEON_GREEN}Crafted default config scroll: {filepath}{RESET}")
            global QUOTE_CURRENCY; QUOTE_CURRENCY = default_config.get("quote_currency", "USDT")
            return default_config
        except IOError as e:
            init_logger.critical(f"{NEON_RED}FATAL: Error crafting default config scroll '{filepath}': {e}. The weave is broken!{RESET}")
            init_logger.warning("Using internal default configuration runes. Bot may falter.")
            QUOTE_CURRENCY = default_config.get("quote_currency", "USDT"); return default_config

    try:
        with open(filepath, "r", encoding="utf-8") as f: loaded_config = json.load(f)
        if not isinstance(loaded_config, dict): raise TypeError("Configuration scroll does not contain a valid arcane map (JSON object).")
    except json.JSONDecodeError as e:
        init_logger.error(f"{NEON_RED}Error deciphering JSON from '{filepath}': {e}. Recrafting default scroll.{RESET}")
        try:
            with open(filepath, "w", encoding="utf-8") as f_create: json.dump(default_config, f_create, indent=4, ensure_ascii=False)
            init_logger.info(f"{NEON_GREEN}Recrafted default config scroll due to corruption: {filepath}{RESET}")
            QUOTE_CURRENCY = default_config.get("quote_currency", "USDT"); return default_config
        except IOError as e_create:
            init_logger.critical(f"{NEON_RED}FATAL: Error recrafting default config scroll after corruption: {e_create}. Using internal defaults.{RESET}")
            QUOTE_CURRENCY = default_config.get("quote_currency", "USDT"); return default_config
    except Exception as e:
        init_logger.critical(f"{NEON_RED}FATAL: Unexpected rift loading config scroll '{filepath}': {e}{RESET}", exc_info=True)
        init_logger.warning("Using internal default configuration runes. Bot may falter.")
        QUOTE_CURRENCY = default_config.get("quote_currency", "USDT"); return default_config

    try:
        updated_config, added_keys = _ensure_config_keys(loaded_config, default_config)
        if added_keys: config_needs_saving = True

        def validate_numeric(cfg: Dict, key_path: str, min_val: Union[int, float, Decimal], max_val: Union[int, float, Decimal], is_strict_min: bool = False, is_int: bool = False, allow_zero: bool = False) -> bool:
            nonlocal config_needs_saving; keys = key_path.split('.'); current_level = cfg; default_level = default_config
            try:
                for key in keys[:-1]: current_level = current_level[key]; default_level = default_level[key]
                leaf_key = keys[-1]; original_val = current_level.get(leaf_key); default_val = default_level.get(leaf_key)
            except (KeyError, TypeError): init_logger.error(f"Config validation error: Invalid path '{key_path}'."); return False
            if original_val is None: init_logger.warning(f"Config validation: Rune missing at '{key_path}'. Using default: {repr(default_val)}"); current_level[leaf_key] = default_val; config_needs_saving = True; return True
            corrected = False; final_val = original_val
            try:
                num_val = Decimal(str(original_val)); min_dec = Decimal(str(min_val)); max_dec = Decimal(str(max_val))
                min_check = num_val > min_dec if is_strict_min else num_val >= min_dec
                range_check = min_check and num_val <= max_dec; zero_ok = allow_zero and num_val == Decimal(0)
                if not range_check and not zero_ok: raise ValueError("Value outside allowed arcane boundaries.")
                target_type = int if is_int else float; converted_val = target_type(num_val)
                needs_correction = False
                if isinstance(original_val, bool): raise TypeError("Boolean found where numeric essence expected.")
                elif is_int and not isinstance(original_val, int): needs_correction = True
                elif not is_int and not isinstance(original_val, float):
                    if isinstance(original_val, int): converted_val = float(original_val); needs_correction = True
                    else: needs_correction = True
                elif isinstance(original_val, float) and abs(original_val - converted_val) > 1e-9: needs_correction = True
                elif isinstance(original_val, int) and original_val != converted_val: needs_correction = True
                if needs_correction: init_logger.info(f"{NEON_YELLOW}Config Spell: Corrected essence/value for '{key_path}' from {repr(original_val)} to {repr(converted_val)}.{RESET}"); final_val = converted_val; corrected = True
            except (ValueError, InvalidOperation, TypeError) as e:
                range_str = f"{'(' if is_strict_min else '['}{min_val}, {max_val}{']'}" + (" or 0" if allow_zero else "")
                init_logger.warning(f"{NEON_YELLOW}Config rune '{key_path}': Invalid value '{repr(original_val)}'. Using default: {repr(default_val)}. Error: {e}. Expected: {'integer' if is_int else 'float'}, Boundaries: {range_str}{RESET}"); final_val = default_val; corrected = True
            if corrected: current_level[leaf_key] = final_val; config_needs_saving = True
            return corrected

        init_logger.debug("# Scrutinizing configuration runes...")
        # General Validations
        if not isinstance(updated_config.get("trading_pairs"), list) or not all(isinstance(s, str) and s for s in updated_config.get("trading_pairs", [])):
            init_logger.warning(f"{NEON_YELLOW}Invalid 'trading_pairs'. Must be list of non-empty strings. Using default {default_config['trading_pairs']}.{RESET}"); updated_config["trading_pairs"] = default_config["trading_pairs"]; config_needs_saving = True
        if updated_config.get("interval") not in VALID_INTERVALS:
            init_logger.warning(f"{NEON_YELLOW}Invalid 'interval' '{updated_config.get('interval')}'. Valid: {VALID_INTERVALS}. Using default '{default_config['interval']}'.{RESET}"); updated_config["interval"] = default_config["interval"]; config_needs_saving = True
        validate_numeric(updated_config, "retry_delay", 1, 60, is_int=True)
        validate_numeric(updated_config, "fetch_limit", 50, MAX_DF_LEN, is_int=True)
        validate_numeric(updated_config, "risk_per_trade", Decimal('0'), Decimal('1'), is_strict_min=True)
        validate_numeric(updated_config, "leverage", 0, 200, is_int=True, allow_zero=True)
        validate_numeric(updated_config, "loop_delay_seconds", 1, 3600, is_int=True)
        validate_numeric(updated_config, "position_confirm_delay_seconds", 1, 60, is_int=True)
        if not isinstance(updated_config.get("quote_currency"), str) or not updated_config.get("quote_currency"):
             init_logger.warning(f"Invalid 'quote_currency'. Must be non-empty string. Using default '{default_config['quote_currency']}'."); updated_config["quote_currency"] = default_config["quote_currency"]; config_needs_saving = True
        if not isinstance(updated_config.get("enable_trading"), bool):
             init_logger.warning(f"Invalid 'enable_trading'. Must be true/false. Using default '{default_config['enable_trading']}'."); updated_config["enable_trading"] = default_config["enable_trading"]; config_needs_saving = True
        if not isinstance(updated_config.get("use_sandbox"), bool):
             init_logger.warning(f"Invalid 'use_sandbox'. Must be true/false. Using default '{default_config['use_sandbox']}'."); updated_config["use_sandbox"] = default_config["use_sandbox"]; config_needs_saving = True
        # Strategy Param Validations
        validate_numeric(updated_config, "strategy_params.vt_length", 1, 500, is_int=True)
        validate_numeric(updated_config, "strategy_params.vt_atr_period", 1, MAX_DF_LEN, is_int=True)
        validate_numeric(updated_config, "strategy_params.vt_vol_ema_length", 1, MAX_DF_LEN, is_int=True)
        validate_numeric(updated_config, "strategy_params.vt_atr_multiplier", 0.1, 20.0)
        validate_numeric(updated_config, "strategy_params.ph_left", 1, 100, is_int=True)
        validate_numeric(updated_config, "strategy_params.ph_right", 1, 100, is_int=True)
        validate_numeric(updated_config, "strategy_params.pl_left", 1, 100, is_int=True)
        validate_numeric(updated_config, "strategy_params.pl_right", 1, 100, is_int=True)
        validate_numeric(updated_config, "strategy_params.ob_max_boxes", 1, 200, is_int=True)
        validate_numeric(updated_config, "strategy_params.ob_entry_proximity_factor", 1.0, 1.1)
        validate_numeric(updated_config, "strategy_params.ob_exit_proximity_factor", 1.0, 1.1)
        if updated_config["strategy_params"].get("ob_source") not in ["Wicks", "Body"]:
             init_logger.warning(f"Invalid strategy_params.ob_source. Must be 'Wicks' or 'Body'. Using default '{DEFAULT_OB_SOURCE}'."); updated_config["strategy_params"]["ob_source"] = DEFAULT_OB_SOURCE; config_needs_saving = True
        if not isinstance(updated_config["strategy_params"].get("ob_extend"), bool):
             init_logger.warning(f"Invalid strategy_params.ob_extend. Must be true/false. Using default '{DEFAULT_OB_EXTEND}'."); updated_config["strategy_params"]["ob_extend"] = DEFAULT_OB_EXTEND; config_needs_saving = True
        # Protection Param Validations
        if not isinstance(updated_config["protection"].get("enable_trailing_stop"), bool):
             init_logger.warning(f"Invalid protection.enable_trailing_stop. Must be true/false. Using default '{default_config['protection']['enable_trailing_stop']}'."); updated_config["protection"]["enable_trailing_stop"] = default_config["protection"]["enable_trailing_stop"]; config_needs_saving = True
        if not isinstance(updated_config["protection"].get("enable_break_even"), bool):
             init_logger.warning(f"Invalid protection.enable_break_even. Must be true/false. Using default '{default_config['protection']['enable_break_even']}'."); updated_config["protection"]["enable_break_even"] = default_config["protection"]["enable_break_even"]; config_needs_saving = True
        validate_numeric(updated_config, "protection.trailing_stop_callback_rate", Decimal('0.0001'), Decimal('0.5'), is_strict_min=True)
        validate_numeric(updated_config, "protection.trailing_stop_activation_percentage", Decimal('0'), Decimal('0.5'), allow_zero=True)
        validate_numeric(updated_config, "protection.break_even_trigger_atr_multiple", Decimal('0.1'), Decimal('10.0'))
        validate_numeric(updated_config, "protection.break_even_offset_ticks", 0, 1000, is_int=True, allow_zero=True)
        validate_numeric(updated_config, "protection.initial_stop_loss_atr_multiple", Decimal('0.1'), Decimal('100.0'), is_strict_min=True)
        validate_numeric(updated_config, "protection.initial_take_profit_atr_multiple", Decimal('0'), Decimal('100.0'), allow_zero=True)

        if config_needs_saving:
             try:
                 with open(filepath, "w", encoding="utf-8") as f_write: json.dump(updated_config, f_write, indent=4, ensure_ascii=False)
                 init_logger.info(f"{NEON_GREEN}Inscribed updated configuration runes to scroll: {filepath}{RESET}")
             except Exception as save_err:
                 init_logger.error(f"{NEON_RED}Error inscribing updated configuration to '{filepath}': {save_err}{RESET}", exc_info=True)
                 init_logger.warning("Proceeding with corrected runes in memory, but scroll update failed.")

        global QUOTE_CURRENCY; QUOTE_CURRENCY = updated_config.get("quote_currency", "USDT")
        init_logger.info(f"Quote currency focus set to: {NEON_YELLOW}{QUOTE_CURRENCY}{RESET}")
        init_logger.info(f"{Fore.CYAN}# Configuration conjuration complete.{Style.RESET_ALL}")
        return updated_config

    except Exception as e:
        init_logger.critical(f"{NEON_RED}FATAL: Unexpected vortex during configuration processing: {e}. Using internal defaults.{RESET}", exc_info=True)
        QUOTE_CURRENCY = default_config.get("quote_currency", "USDT"); return default_config

CONFIG = load_config(CONFIG_FILE)

# --- CCXT Exchange Setup ---
def initialize_exchange(logger: logging.Logger) -> Optional[ccxt.Exchange]:
    """Initializes and validates the CCXT Bybit exchange object."""
    lg = logger; lg.info(f"{Fore.CYAN}# Binding the arcane energies to the Bybit exchange...{Style.RESET_ALL}")
    try:
        exchange_options = { 'apiKey': API_KEY, 'secret': API_SECRET, 'enableRateLimit': True,
            'options': { 'defaultType': 'linear', 'adjustForTimeDifference': True, 'fetchTickerTimeout': 15000,
                         'fetchBalanceTimeout': 20000, 'createOrderTimeout': 30000, 'cancelOrderTimeout': 20000,
                         'fetchPositionsTimeout': 20000, 'fetchOHLCVTimeout': 60000 } }
        exchange = ccxt.bybit(exchange_options)
        is_sandbox = CONFIG.get('use_sandbox', True); exchange.set_sandbox_mode(is_sandbox)
        if is_sandbox: lg.warning(f"{NEON_YELLOW}<<< OPERATING IN SANDBOX REALM (Testnet Environment) >>>{RESET}")
        else: lg.warning(f"{NEON_RED}{BRIGHT}!!! <<< OPERATING IN LIVE REALM - REAL ASSETS AT STAKE >>> !!!{RESET}")

        lg.info(f"Summoning market knowledge for {exchange.id}...")
        markets_loaded = False; last_market_error = None
        for attempt in range(MAX_API_RETRIES + 1):
            try:
                lg.debug(f"Market summon attempt {attempt + 1}/{MAX_API_RETRIES + 1}...")
                exchange.load_markets(reload=(attempt > 0))
                if exchange.markets and len(exchange.markets) > 0:
                    lg.info(f"{NEON_GREEN}Market knowledge summoned successfully ({len(exchange.markets)} symbols charted).{RESET}"); markets_loaded = True; break
                else: last_market_error = ValueError("Market summoning returned an empty void"); lg.warning(f"Market summoning returned empty void (Attempt {attempt + 1}). Retrying...")
            except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e:
                last_market_error = e; lg.warning(f"Aetheric disturbance (Network Error) summoning markets (Attempt {attempt + 1}): {e}.")
                if attempt >= MAX_API_RETRIES: lg.critical(f"{NEON_RED}Max retries exceeded summoning markets. Last echo: {last_market_error}. Binding failed.{RESET}"); return None
            except ccxt.AuthenticationError as e: last_market_error = e; lg.critical(f"{NEON_RED}Authentication ritual failed: {e}. Check API seals. Binding failed.{RESET}"); return None
            except Exception as e: last_market_error = e; lg.critical(f"{NEON_RED}Unexpected rift summoning markets: {e}. Binding failed.{RESET}", exc_info=True); return None
            if not markets_loaded and attempt < MAX_API_RETRIES: delay = RETRY_DELAY_SECONDS * (attempt + 1); lg.warning(f"Retrying market summon in {delay}s..."); time.sleep(delay)
        if not markets_loaded: lg.critical(f"{NEON_RED}Failed to summon markets after all attempts. Last echo: {last_market_error}. Binding failed.{RESET}"); return None

        lg.info(f"Exchange binding established: {exchange.id} | Sandbox Realm: {is_sandbox}")
        lg.info(f"Scrying initial balance for quote currency ({QUOTE_CURRENCY})...")
        initial_balance: Optional[Decimal] = None
        try: initial_balance = fetch_balance(exchange, QUOTE_CURRENCY, lg)
        except ccxt.AuthenticationError as auth_err: lg.critical(f"{NEON_RED}Authentication Ritual Failed during balance scrying: {auth_err}. Binding failed.{RESET}"); return None
        except Exception as balance_err: lg.warning(f"{NEON_YELLOW}Initial balance scrying encountered a flicker: {balance_err}.{RESET}", exc_info=False)

        if initial_balance is not None:
            lg.info(f"{NEON_GREEN}Initial available essence: {initial_balance.normalize()} {QUOTE_CURRENCY}{RESET}")
            lg.info(f"{Fore.CYAN}# Exchange binding complete and validated.{Style.RESET_ALL}"); return exchange
        else:
            lg.error(f"{NEON_RED}Initial balance scrying FAILED for {QUOTE_CURRENCY}.{RESET}")
            if CONFIG.get('enable_trading', False): lg.critical(f"{NEON_RED}Trading rituals enabled, but balance scrying failed. Cannot proceed safely. Binding failed.{RESET}"); return None
            else: lg.warning(f"{NEON_YELLOW}Trading rituals disabled. Proceeding without confirmed balance, but spells may falter.{RESET}"); lg.info(f"{Fore.CYAN}# Exchange binding complete (balance unconfirmed).{Style.RESET_ALL}"); return exchange
    except Exception as e: lg.critical(f"{NEON_RED}Failed to bind to CCXT exchange: {e}{RESET}", exc_info=True); return None

# --- CCXT Data Fetching Helpers ---
def _safe_market_decimal(value: Optional[Any], field_name: str, allow_zero: bool = True) -> Optional[Decimal]:
    """Safely converts market info value to Decimal."""
    if value is None: return None
    try:
        s_val = str(value).strip();
        if not s_val: return None
        d_val = Decimal(s_val)
        if not allow_zero and d_val <= Decimal('0'): return None
        if allow_zero and d_val < Decimal('0'): return None
        return d_val
    except (InvalidOperation, TypeError, ValueError): return None

def _format_price(exchange: ccxt.Exchange, symbol: str, price: Union[Decimal, float, str]) -> Optional[str]:
    """Formats a price to the exchange's required precision string."""
    try:
        price_decimal = Decimal(str(price))
        if price_decimal <= 0: return None # Price must be positive
        # Use CCXT's helper for correct rounding/truncating
        formatted_str = exchange.price_to_precision(symbol, float(price_decimal))
        # Final check: ensure formatted price is still positive
        if Decimal(formatted_str) > 0:
            return formatted_str
        else:
            return None
    except (InvalidOperation, ValueError, TypeError, KeyError, AttributeError):
        return None

def fetch_current_price_ccxt(exchange: ccxt.Exchange, symbol: str, logger: logging.Logger) -> Optional[Decimal]:
    """Fetches the current market price using fetch_ticker with fallbacks."""
    lg = logger; attempts = 0; last_exception = None
    while attempts <= MAX_API_RETRIES:
        try:
            lg.debug(f"Fetching current price pulse for {symbol} (Attempt {attempts + 1})")
            ticker = exchange.fetch_ticker(symbol); price: Optional[Decimal] = None; source = "N/A"
            def safe_decimal_from_ticker(value: Optional[Any], field_name: str) -> Optional[Decimal]:
                if value is None: return None
                try: s_val = str(value).strip(); return Decimal(s_val) if s_val and Decimal(s_val) > 0 else None
                except (ValueError, InvalidOperation, TypeError): return None

            price = safe_decimal_from_ticker(ticker.get('last'), 'last'); source = "'last' price"
            if price is None:
                bid = safe_decimal_from_ticker(ticker.get('bid'), 'bid'); ask = safe_decimal_from_ticker(ticker.get('ask'), 'ask')
                if bid and ask: price = (bid + ask) / Decimal('2'); source = f"mid-price (B:{bid.normalize()}, A:{ask.normalize()})"
                elif ask: price = ask; source = f"'ask' price ({ask.normalize()})"
                elif bid: price = bid; source = f"'bid' price ({bid.normalize()})"
            if price: lg.debug(f"Price pulse captured ({symbol}) via {source}: {price.normalize()}"); return price.normalize()
            else: last_exception = ValueError("No valid price found in ticker"); lg.warning(f"No valid price pulse ({symbol}, Attempt {attempts + 1}). Retrying...")
        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e: last_exception = e; lg.warning(f"{NEON_YELLOW}Aetheric disturbance fetching price ({symbol}): {e}. Retry {attempts + 1}...{RESET}")
        except ccxt.RateLimitExceeded as e: last_exception = e; wait_time = RETRY_DELAY_SECONDS * 3; lg.warning(f"{NEON_YELLOW}Rate limit fetching price ({symbol}): {e}. Pausing {wait_time}s...{RESET}"); time.sleep(wait_time); continue
        except ccxt.AuthenticationError as e: last_exception = e; lg.critical(f"{NEON_RED}Auth ritual failed fetching price: {e}. Stopping.{RESET}"); return None
        except ccxt.ExchangeError as e: last_exception = e; lg.error(f"{NEON_RED}Exchange rift fetching price ({symbol}): {e}{RESET}")
        except Exception as e: last_exception = e; lg.error(f"{NEON_RED}Unexpected vortex fetching price ({symbol}): {e}{RESET}", exc_info=True); return None
        attempts += 1
        if attempts <= MAX_API_RETRIES: time.sleep(RETRY_DELAY_SECONDS * attempts)
    lg.error(f"{NEON_RED}Failed to capture price pulse ({symbol}) after {MAX_API_RETRIES + 1} attempts. Last echo: {last_exception}{RESET}"); return None

def fetch_klines_ccxt(exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int, logger: logging.Logger) -> pd.DataFrame:
    """Fetches OHLCV klines, handling multi-request fetching if needed."""
    lg = logger
    lg.info(f"{Fore.CYAN}# Gathering historical echoes (Klines) for {symbol} | TF: {timeframe} | Limit: {limit}...{Style.RESET_ALL}")
    if not hasattr(exchange, 'fetch_ohlcv') or not exchange.has.get('fetchOHLCV'):
        lg.error(f"Exchange {exchange.id} does not support fetchOHLCV."); return pd.DataFrame()

    # Calculate minimum required candles for strategy (rough estimate)
    min_required = 0
    try:
        sp = CONFIG.get('strategy_params', {})
        min_required = max(sp.get('vt_length', 0), sp.get('vt_atr_period', 0), sp.get('vt_vol_ema_length', 0),
                           sp.get('ph_left', 0) + sp.get('ph_right', 0) + 1,
                           sp.get('pl_left', 0) + sp.get('pl_right', 0) + 1) + 50 # Add buffer
        lg.debug(f"Estimated minimum candles required by strategy: {min_required}")
        if limit < min_required:
            lg.warning(f"{NEON_YELLOW}Requested limit ({limit}) is less than estimated strategy requirement ({min_required}). Indicator accuracy may be affected.{RESET}")
    except Exception as e: lg.warning(f"Could not estimate minimum required candles: {e}")

    # Determine category for Bybit V5
    category = 'spot' # Default
    market_id = symbol # Default
    try:
        market = exchange.market(symbol)
        market_id = market['id']
        category = 'linear' if market.get('linear') else 'inverse' if market.get('inverse') else 'spot'
        lg.debug(f"Using Bybit category: {category} for kline fetch.")
    except Exception as e: lg.warning(f"Could not determine market category for {symbol}: {e}. Using default.")

    all_ohlcv_data: List[List[Union[int, float, str]]] = []
    remaining_limit = limit
    end_timestamp_ms: Optional[int] = None # Fetch going backwards from current time

    while remaining_limit > 0:
        fetch_size = min(remaining_limit, BYBIT_API_KLINE_LIMIT)
        lg.debug(f"Fetching chunk of {fetch_size} klines for {symbol} (End TS: {end_timestamp_ms})...")
        attempts = 0
        last_exception = None
        chunk_data: Optional[List[List[Union[int, float, str]]]] = None

        while attempts <= MAX_API_RETRIES:
            try:
                params = {'category': category}
                # CCXT handles the 'until' parameter based on end_timestamp_ms
                fetch_args = {'symbol': symbol, 'timeframe': timeframe, 'limit': fetch_size, 'params': params}
                if end_timestamp_ms: fetch_args['until'] = end_timestamp_ms

                chunk_data = exchange.fetch_ohlcv(**fetch_args) # type: ignore
                fetched_count = len(chunk_data) if chunk_data else 0
                lg.debug(f"API returned {fetched_count} candles for this chunk.")

                if chunk_data:
                    # Basic validation (e.g., timestamp check on first fetch)
                    if not all_ohlcv_data: # Only check lag on the most recent chunk
                        try:
                            last_candle_timestamp_ms = chunk_data[-1][0]
                            last_ts = pd.to_datetime(last_candle_timestamp_ms, unit='ms', utc=True)
                            now_utc = pd.Timestamp.utcnow()
                            interval_seconds = exchange.parse_timeframe(timeframe)
                            if interval_seconds:
                                max_allowed_lag = interval_seconds * 2.5
                                actual_lag = (now_utc - last_ts).total_seconds()
                                if actual_lag > max_allowed_lag:
                                    last_exception = ValueError(f"Kline data potentially stale (Lag: {actual_lag:.1f}s > Max: {max_allowed_lag:.1f}s).")
                                    lg.warning(f"{NEON_YELLOW}Timestamp lag detected ({symbol}): {last_exception}. Retrying fetch...{RESET}")
                                    chunk_data = None # Discard and retry
                                    # No break here, let retry logic handle it
                            else: lg.warning("Could not parse timeframe for lag check.")
                        except Exception as ts_err: lg.warning(f"Could not validate timestamp lag ({symbol}): {ts_err}. Proceeding cautiously.")
                    # If validation passed or wasn't needed, break retry loop for this chunk
                    if chunk_data: break
                else:
                    # If API returns empty list, it might mean no more data available going back
                    lg.debug(f"API returned no data for chunk (End TS: {end_timestamp_ms}). Assuming end of history.")
                    remaining_limit = 0 # Stop fetching further chunks
                    break # Exit retry loop for this chunk

            # Error Handling (same as before, applied per chunk)
            except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e: last_exception = e; lg.warning(f"{NEON_YELLOW}Network error fetching kline chunk ({symbol}): {e}. Retry {attempts + 1}...{RESET}")
            except ccxt.RateLimitExceeded as e: last_exception = e; wait_time = RETRY_DELAY_SECONDS * 3; lg.warning(f"{NEON_YELLOW}Rate limit fetching kline chunk ({symbol}): {e}. Pausing {wait_time}s...{RESET}"); time.sleep(wait_time); continue
            except ccxt.AuthenticationError as e: last_exception = e; lg.critical(f"{NEON_RED}Auth ritual failed fetching klines: {e}. Stopping.{RESET}"); return pd.DataFrame()
            except ccxt.ExchangeError as e: last_exception = e; lg.error(f"{NEON_RED}Exchange rift fetching klines ({symbol}): {e}{RESET}"); # Check non-retryable?
            except Exception as e: last_exception = e; lg.error(f"{NEON_RED}Unexpected vortex fetching klines ({symbol}): {e}{RESET}", exc_info=True); return pd.DataFrame()

            attempts += 1
            if attempts <= MAX_API_RETRIES and chunk_data is None: time.sleep(RETRY_DELAY_SECONDS * attempts)

        # --- After chunk retry loop ---
        if chunk_data:
            # Prepend older data to the main list
            all_ohlcv_data = chunk_data + all_ohlcv_data
            remaining_limit -= len(chunk_data)
            # Set the end timestamp for the *next* fetch request (oldest timestamp - 1ms)
            end_timestamp_ms = chunk_data[0][0] - 1
            # Check if we received fewer candles than requested, implies end of history
            if len(chunk_data) < fetch_size:
                 lg.debug(f"Received fewer candles ({len(chunk_data)}) than requested ({fetch_size}). Assuming end of available history.")
                 remaining_limit = 0 # Stop fetching
        else:
            # Fetching chunk failed after retries
            lg.error(f"{NEON_RED}Failed to fetch kline chunk for {symbol} after {MAX_API_RETRIES + 1} attempts. Last echo: {last_exception}{RESET}")
            # Decide whether to proceed with partial data or fail entirely
            if not all_ohlcv_data: # Failed on the very first chunk
                 return pd.DataFrame()
            else:
                 lg.warning(f"Proceeding with {len(all_ohlcv_data)} candles fetched before error.")
                 break # Exit the main fetching loop

        # Small delay between fetches to be kind to the API
        if remaining_limit > 0: time.sleep(0.5)

    # --- Process Combined Data ---
    if not all_ohlcv_data:
        lg.error(f"No kline data could be fetched for {symbol} {timeframe}.")
        return pd.DataFrame()

    lg.info(f"Total klines fetched across all requests: {len(all_ohlcv_data)}")
    # Deduplicate based on timestamp (just in case of overlap, keep first occurrence)
    seen_timestamps = set()
    unique_data = []
    for candle in all_ohlcv_data:
        ts = candle[0]
        if ts not in seen_timestamps:
            unique_data.append(candle)
            seen_timestamps.add(ts)
    if len(unique_data) != len(all_ohlcv_data):
        lg.warning(f"Removed {len(all_ohlcv_data) - len(unique_data)} duplicate candle timestamps.")
    all_ohlcv_data = unique_data

    # Sort by timestamp just to be absolutely sure
    all_ohlcv_data.sort(key=lambda x: x[0])

    # Limit to the originally requested number of candles (most recent)
    if len(all_ohlcv_data) > limit:
        lg.debug(f"Fetched {len(all_ohlcv_data)} candles, trimming to requested limit {limit}.")
        all_ohlcv_data = all_ohlcv_data[-limit:]

    # Process into DataFrame (same logic as before)
    try:
        lg.debug(f"Processing {len(all_ohlcv_data)} final candles into DataFrame ({symbol})...")
        cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df = pd.DataFrame(all_ohlcv_data, columns=cols[:len(all_ohlcv_data[0])])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True, errors='coerce')
        df.dropna(subset=['timestamp'], inplace=True)
        if df.empty: lg.error(f"DataFrame empty after timestamp conversion ({symbol})."); return pd.DataFrame()
        df.set_index('timestamp', inplace=True)

        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            if col in df.columns:
                numeric_series = pd.to_numeric(df[col], errors='coerce')
                df[col] = numeric_series.apply(lambda x: Decimal(str(x)) if pd.notna(x) and np.isfinite(x) else Decimal('NaN'))
            else: lg.warning(f"Expected column '{col}' not found ({symbol}).")

        initial_len = len(df)
        essential_price_cols = ['open', 'high', 'low', 'close']
        df.dropna(subset=essential_price_cols, inplace=True)
        df = df[df['close'] > Decimal('0')]
        if 'volume' in df.columns: df.dropna(subset=['volume'], inplace=True); df = df[df['volume'] >= Decimal('0')]
        rows_dropped = initial_len - len(df)
        if rows_dropped > 0: lg.debug(f"Purged {rows_dropped} rows ({symbol}) during cleaning.")
        if df.empty: lg.warning(f"Kline DataFrame empty after cleaning ({symbol})."); return pd.DataFrame()
        if not df.index.is_monotonic_increasing: lg.warning(f"Kline index not monotonic ({symbol}), sorting..."); df.sort_index(inplace=True)
        if len(df) > MAX_DF_LEN: lg.debug(f"DataFrame length ({len(df)}) > max ({MAX_DF_LEN}). Trimming."); df = df.iloc[-MAX_DF_LEN:].copy()

        lg.info(f"{NEON_GREEN}Successfully gathered and processed {len(df)} kline echoes for {symbol} {timeframe}{RESET}")
        return df
    except Exception as e: lg.error(f"{NEON_RED}Error processing kline echoes ({symbol}): {e}{RESET}", exc_info=True); return pd.DataFrame()

def get_market_info(exchange: ccxt.Exchange, symbol: str, logger: logging.Logger) -> Optional[MarketInfo]:
    """Retrieves, validates, and standardizes market information."""
    lg = logger; lg.debug(f"Seeking market details for symbol: {symbol}...")
    attempts = 0; last_exception = None
    while attempts <= MAX_API_RETRIES:
        try:
            market: Optional[Dict] = None
            if not exchange.markets or symbol not in exchange.markets:
                lg.info(f"Market details for '{symbol}' not found. Refreshing market map...");
                try: exchange.load_markets(reload=True); lg.info("Market map refreshed.")
                except Exception as reload_err: last_exception = reload_err; lg.error(f"Failed to refresh market map: {reload_err}")
            try: market = exchange.market(symbol)
            except ccxt.BadSymbol: market = None
            except Exception as fetch_err: last_exception = fetch_err; lg.warning(f"Error fetching market dict for '{symbol}': {fetch_err}. Retrying...") ; market = None

            if market is None:
                if attempts < MAX_API_RETRIES: lg.warning(f"Symbol '{symbol}' not found or fetch failed (Attempt {attempts + 1}). Retrying check...")
                else: lg.error(f"{NEON_RED}Market '{symbol}' not found on {exchange.id} after retries. Last echo: {last_exception}{RESET}"); return None
            else:
                lg.debug(f"Market found for '{symbol}'. Standardizing details...")
                std_market = market.copy()
                is_spot = std_market.get('spot', False); is_swap = std_market.get('swap', False); is_future = std_market.get('future', False)
                is_linear = std_market.get('linear'); is_inverse = std_market.get('inverse')
                std_market['is_contract'] = is_swap or is_future or std_market.get('contract', False)
                std_market['is_linear'] = is_linear is True and std_market['is_contract']
                std_market['is_inverse'] = is_inverse is True and std_market['is_contract']
                std_market['contract_type_str'] = "Linear" if std_market['is_linear'] else "Inverse" if std_market['is_inverse'] else "Spot" if is_spot else "Unknown"

                precision = std_market.get('precision', {}); limits = std_market.get('limits', {})
                amount_limits = limits.get('amount', {}); cost_limits = limits.get('cost', {})
                std_market['amount_precision_step_decimal'] = _safe_market_decimal(precision.get('amount'), 'precision.amount', allow_zero=False)
                std_market['price_precision_step_decimal'] = _safe_market_decimal(precision.get('price'), 'precision.price', allow_zero=False)
                std_market['min_amount_decimal'] = _safe_market_decimal(amount_limits.get('min'), 'limits.amount.min')
                std_market['max_amount_decimal'] = _safe_market_decimal(amount_limits.get('max'), 'limits.amount.max', allow_zero=False)
                std_market['min_cost_decimal'] = _safe_market_decimal(cost_limits.get('min'), 'limits.cost.min')
                std_market['max_cost_decimal'] = _safe_market_decimal(cost_limits.get('max'), 'limits.cost.max', allow_zero=False)
                contract_size_val = std_market.get('contractSize', '1')
                std_market['contract_size_decimal'] = _safe_market_decimal(contract_size_val, 'contractSize', allow_zero=False) or Decimal('1')

                if std_market['amount_precision_step_decimal'] is None or std_market['price_precision_step_decimal'] is None:
                    lg.error(f"{NEON_RED}CRITICAL VALIDATION FAILED:{RESET} Market '{symbol}' missing essential precision runes."); lg.error(f"  Amount Step: {std_market['amount_precision_step_decimal']}, Price Step: {std_market['price_precision_step_decimal']}"); return None

                log_msg = ( f"Market Details ({symbol}): Type={std_market['contract_type_str']}, Active={std_market.get('active')}\n"
                            f"  Precision (Amt/Price): {std_market['amount_precision_step_decimal'].normalize()} / {std_market['price_precision_step_decimal'].normalize()}\n"
                            f"  Limits (Amt Min/Max): {std_market['min_amount_decimal'].normalize() if std_market['min_amount_decimal'] is not None else 'N/A'} / {std_market['max_amount_decimal'].normalize() if std_market['max_amount_decimal'] is not None else 'N/A'}\n"
                            f"  Limits (Cost Min/Max): {std_market['min_cost_decimal'].normalize() if std_market['min_cost_decimal'] is not None else 'N/A'} / {std_market['max_cost_decimal'].normalize() if std_market['max_cost_decimal'] is not None else 'N/A'}\n"
                            f"  Contract Size: {std_market['contract_size_decimal'].normalize()}" )
                lg.debug(log_msg)
                try: final_market_info: MarketInfo = std_market; return final_market_info # type: ignore
                except Exception as cast_err: lg.error(f"Error casting market dict to TypedDict: {cast_err}"); return std_market # type: ignore

        except ccxt.BadSymbol as e: lg.error(f"Symbol '{symbol}' is invalid on {exchange.id}: {e}"); return None
        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e: last_exception = e; lg.warning(f"{NEON_YELLOW}Aetheric disturbance retrieving market info ({symbol}): {e}. Retry {attempts + 1}...{RESET}"); if attempts >= MAX_API_RETRIES: lg.error(f"{NEON_RED}Max retries for NetworkError market info ({symbol}).{RESET}"); return None
        except ccxt.AuthenticationError as e: last_exception = e; lg.critical(f"{NEON_RED}Auth ritual failed getting market info: {e}. Stopping.{RESET}"); return None
        except ccxt.ExchangeError as e: last_exception = e; lg.error(f"{NEON_RED}Exchange rift retrieving market info ({symbol}): {e}{RESET}"); if attempts >= MAX_API_RETRIES: lg.error(f"{NEON_RED}Max retries for ExchangeError market info ({symbol}).{RESET}"); return None
        except Exception as e: last_exception = e; lg.error(f"{NEON_RED}Unexpected vortex retrieving market info ({symbol}): {e}{RESET}", exc_info=True); return None
        attempts += 1; time.sleep(RETRY_DELAY_SECONDS * attempts)
    lg.error(f"{NEON_RED}Failed to retrieve market info ({symbol}) after all attempts. Last echo: {last_exception}{RESET}"); return None

def fetch_balance(exchange: ccxt.Exchange, currency: str, logger: logging.Logger) -> Optional[Decimal]:
    """Fetches the available trading balance for a specific currency."""
    lg = logger; lg.debug(f"Scrying balance for currency: {currency}...")
    attempts = 0; last_exception = None
    while attempts <= MAX_API_RETRIES:
        try:
            balance_str: Optional[str] = None; found: bool = False; balance_info: Optional[Dict] = None
            account_types_to_check = ['UNIFIED', 'CONTRACT', ''] if 'bybit' in exchange.id.lower() else ['']
            for acc_type in account_types_to_check:
                try:
                    params = {'accountType': acc_type} if acc_type else {}; type_desc = f"Type: {acc_type}" if acc_type else "Default"
                    lg.debug(f"Fetching balance ({currency}, {type_desc}, Attempt {attempts + 1})...")
                    balance_info = exchange.fetch_balance(params=params)
                    if currency in balance_info and balance_info[currency].get('free') is not None: balance_str = str(balance_info[currency]['free']); lg.debug(f"Found balance in 'free' field ({type_desc}): {balance_str}"); found = True; break
                    elif 'info' in balance_info and 'result' in balance_info['info'] and isinstance(balance_info['info']['result'].get('list'), list):
                        for acc_details in balance_info['info']['result']['list']:
                             if (not acc_type or acc_details.get('accountType') == acc_type) and isinstance(acc_details.get('coin'), list):
                                for coin_data in acc_details['coin']:
                                    if coin_data.get('coin') == currency:
                                        balance_val = coin_data.get('availableToWithdraw') or coin_data.get('availableBalance') or coin_data.get('walletBalance')
                                        if balance_val is not None: balance_str = str(balance_val); source = 'availableToWithdraw' if coin_data.get('availableToWithdraw') else 'availableBalance' if coin_data.get('availableBalance') else 'walletBalance'; lg.debug(f"Found balance in Bybit V5 (Acc: {acc_details.get('accountType')}, Field: {source}): {balance_str}"); found = True; break
                                if found: break
                        if found: break
                except ccxt.ExchangeError as e:
                    if acc_type and ("account type does not exist" in str(e).lower() or "invalid account type" in str(e).lower()): lg.debug(f"Account type '{acc_type}' not found. Trying next...")
                    elif acc_type: lg.debug(f"Minor exchange rift fetching balance ({acc_type}): {e}. Trying next...")
                    else: raise e
                    continue
                except Exception as e: lg.warning(f"Unexpected flicker fetching balance ({acc_type or 'Default'}): {e}. Trying next..."); last_exception = e; continue
            if found and balance_str is not None:
                try: balance_decimal = Decimal(balance_str); final_balance = max(balance_decimal, Decimal('0')); lg.debug(f"Parsed balance ({currency}): {final_balance.normalize()}"); return final_balance
                except (ValueError, InvalidOperation, TypeError) as e: raise ccxt.ExchangeError(f"Failed to convert balance string '{balance_str}' ({currency}): {e}")
            elif not found and balance_info is not None: raise ccxt.ExchangeError(f"Could not find balance for '{currency}'. Last response info: {balance_info.get('info')}")
            elif not found and balance_info is None: raise ccxt.ExchangeError(f"Could not find balance for '{currency}'. Fetch failed.")
        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e: last_exception = e; lg.warning(f"{NEON_YELLOW}Aetheric disturbance fetching balance ({currency}): {e}. Retry {attempts + 1}...{RESET}")
        except ccxt.RateLimitExceeded as e: last_exception = e; wait_time = RETRY_DELAY_SECONDS * 3; lg.warning(f"{NEON_YELLOW}Rate limit fetching balance ({currency}): {e}. Pausing {wait_time}s...{RESET}"); time.sleep(wait_time); continue
        except ccxt.AuthenticationError as e: last_exception = e; lg.critical(f"{NEON_RED}Auth ritual failed fetching balance: {e}. Stopping.{RESET}"); raise e
        except ccxt.ExchangeError as e: last_exception = e; lg.warning(f"{NEON_YELLOW}Exchange rift fetching balance ({currency}): {e}. Retry {attempts + 1}...{RESET}")
        except Exception as e: last_exception = e; lg.error(f"{NEON_RED}Unexpected vortex fetching balance ({currency}): {e}{RESET}", exc_info=True); return None
        attempts += 1
        if attempts <= MAX_API_RETRIES: time.sleep(RETRY_DELAY_SECONDS * attempts)
    lg.error(f"{NEON_RED}Failed to scry balance ({currency}) after {MAX_API_RETRIES + 1} attempts. Last echo: {last_exception}{RESET}"); return None

# --- Position & Order Management ---
def get_open_position(exchange: ccxt.Exchange, symbol: str, logger: logging.Logger) -> Optional[PositionInfo]:
    """Checks for an existing open position for the symbol."""
    lg = logger; lg.debug(f"Seeking open position for symbol: {symbol}...")
    attempts = 0; last_exception = None; market_id: Optional[str] = None; category: Optional[str] = None
    try:
        market = exchange.market(symbol); market_id = market['id']
        category = 'linear' if market.get('linear') else 'inverse' if market.get('inverse') else 'spot'
        if category == 'spot': lg.info(f"Position check skipped for {symbol}: Spot market."); return None
        lg.debug(f"Using Market ID: {market_id}, Category: {category} for position check.")
    except KeyError: lg.error(f"Market '{symbol}' not found. Cannot check position."); return None
    except Exception as e: lg.error(f"Error determining market details for position check ({symbol}): {e}"); return None

    while attempts <= MAX_API_RETRIES:
        try:
            lg.debug(f"Fetching positions for {symbol} (Attempt {attempts + 1})...")
            positions: List[Dict] = []
            try:
                params = {'category': category, 'symbol': market_id}
                lg.debug(f"Fetching positions with params: {params}")
                if exchange.has.get('fetchPositions'):
                     all_positions = exchange.fetch_positions(params=params)
                     positions = [p for p in all_positions if p.get('symbol') == symbol or p.get('info', {}).get('symbol') == market_id]
                     lg.debug(f"Fetched {len(all_positions)} total positions ({category}), filtered to {len(positions)} for {symbol}.")
                else: raise ccxt.NotSupported("Exchange does not support fetchPositions.")
            except ccxt.ExchangeError as e:
                 no_pos_codes = [110025]; no_pos_messages = ["position not found", "no position", "position does not exist"]
                 err_str = str(e).lower(); code_str = ""; match = re.search(r'(retCode|ret_code)=(\d+)', str(e.args[0] if e.args else ''), re.IGNORECASE);
                 if match: code_str = match.group(2)
                 if not code_str: code_str = str(getattr(e, 'code', '') or getattr(e, 'retCode', ''))
                 code_match = any(str(c) in code_str for c in no_pos_codes) if code_str else False
                 if code_match or any(msg in err_str for msg in no_pos_messages): lg.info(f"No open position found for {symbol} (Exchange message: {e})."); return None
                 else: raise e

            active_position_raw: Optional[Dict] = None
            size_threshold = Decimal('1e-9');
            try: amt_step = Decimal(str(exchange.market(symbol)['precision']['amount'])); size_threshold = amt_step * Decimal('0.01') if amt_step > 0 else size_threshold
            except Exception: pass # Ignore precision errors for threshold
            lg.debug(f"Using position size threshold: {size_threshold.normalize()}")

            for pos in positions:
                size_str_info = str(pos.get('info', {}).get('size', '')).strip(); size_str_std = str(pos.get('contracts', '')).strip()
                size_str = size_str_info if size_str_info else size_str_std
                if not size_str: continue
                try:
                    size_decimal = Decimal(size_str)
                    if abs(size_decimal) > size_threshold: active_position_raw = pos; active_position_raw['size_decimal'] = size_decimal; lg.debug(f"Found active position entry ({symbol}): Size={size_decimal.normalize()}"); break
                    else: lg.debug(f"Skipping position entry near-zero size ({size_decimal.normalize()}): {pos.get('info', {})}")
                except (ValueError, InvalidOperation, TypeError) as parse_err: lg.warning(f"Could not parse position size '{size_str}' ({symbol}): {parse_err}. Skipping."); continue

            if active_position_raw:
                std_pos = active_position_raw.copy(); info = std_pos.get('info', {})
                side = std_pos.get('side'); size = std_pos['size_decimal']
                if side not in ['long', 'short']:
                    side_v5 = str(info.get('side', '')).lower()
                    if side_v5 == 'buy': side = 'long'
                    elif side_v5 == 'sell': side = 'short'
                    elif size > size_threshold: side = 'long'
                    elif size < -size_threshold: side = 'short'
                    else: side = None
                if not side: lg.error(f"Could not determine side for active position {symbol}. Size: {size}. Data: {info}"); return None
                std_pos['side'] = side

                std_pos['entryPrice'] = _safe_market_decimal(std_pos.get('entryPrice') or info.get('avgPrice') or info.get('entryPrice'), 'entryPrice')
                std_pos['leverage'] = _safe_market_decimal(std_pos.get('leverage') or info.get('leverage'), 'leverage', allow_zero=False)
                std_pos['liquidationPrice'] = _safe_market_decimal(std_pos.get('liquidationPrice') or info.get('liqPrice'), 'liquidationPrice', allow_zero=False)
                std_pos['unrealizedPnl'] = _safe_market_decimal(std_pos.get('unrealizedPnl') or info.get('unrealisedPnl') or info.get('unrealizedPnl'), 'unrealizedPnl', allow_zero=True)

                def get_protection_field(field_name: str) -> Optional[str]:
                    value = info.get(field_name); s_value = str(value).strip() if value is not None else None
                    try: return s_value if s_value and abs(Decimal(s_value)) > Decimal('1e-12') else None
                    except (InvalidOperation, ValueError, TypeError): return None
                std_pos['stopLossPrice'] = get_protection_field('stopLoss')
                std_pos['takeProfitPrice'] = get_protection_field('takeProfit')
                std_pos['trailingStopLoss'] = get_protection_field('trailingStop')
                std_pos['tslActivationPrice'] = get_protection_field('activePrice')
                # Initialize bot state flags
                std_pos['be_activated'] = False # Will be set by management logic if BE applied
                std_pos['tsl_activated'] = bool(std_pos['trailingStopLoss']) # True if TSL distance is already set

                def format_decimal_log(value: Optional[Any]) -> str: dec_val = _safe_market_decimal(value, 'log', True); return dec_val.normalize() if dec_val is not None else 'N/A'
                ep_str = format_decimal_log(std_pos.get('entryPrice')); size_str = std_pos['size_decimal'].normalize()
                sl_str = format_decimal_log(std_pos.get('stopLossPrice')); tp_str = format_decimal_log(std_pos.get('takeProfitPrice'))
                tsl_dist = format_decimal_log(std_pos.get('trailingStopLoss')); tsl_act = format_decimal_log(std_pos.get('tslActivationPrice'))
                tsl_log = f"Dist={tsl_dist}/Act={tsl_act}" if tsl_dist != 'N/A' or tsl_act != 'N/A' else "N/A"
                pnl_str = format_decimal_log(std_pos.get('unrealizedPnl')); liq_str = format_decimal_log(std_pos.get('liquidationPrice'))

                lg.info(f"{NEON_GREEN}{BRIGHT}Active {side.upper()} Position Found ({symbol}):{RESET} Size={size_str}, Entry={ep_str}, Liq={liq_str}, PnL={pnl_str}, SL={sl_str}, TP={tp_str}, TSL={tsl_log}")
                try: final_position_info: PositionInfo = std_pos; return final_position_info # type: ignore
                except Exception as cast_err: lg.error(f"Error casting position to TypedDict ({symbol}): {cast_err}"); return std_pos # type: ignore
            else: lg.info(f"No active position found for {symbol}."); return None

        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e: last_exception = e; lg.warning(f"{NEON_YELLOW}Aetheric disturbance fetching positions ({symbol}): {e}. Retry {attempts + 1}...{RESET}")
        except ccxt.RateLimitExceeded as e: last_exception = e; wait_time = RETRY_DELAY_SECONDS * 3; lg.warning(f"{NEON_YELLOW}Rate limit fetching positions ({symbol}): {e}. Pausing {wait_time}s...{RESET}"); time.sleep(wait_time); continue
        except ccxt.AuthenticationError as e: last_exception = e; lg.critical(f"{NEON_RED}Auth ritual failed fetching positions: {e}. Stopping.{RESET}"); return None
        except ccxt.ExchangeError as e: last_exception = e; lg.warning(f"{NEON_YELLOW}Exchange rift fetching positions ({symbol}): {e}. Retry {attempts + 1}...{RESET}")
        except Exception as e: last_exception = e; lg.error(f"{NEON_RED}Unexpected vortex fetching positions ({symbol}): {e}{RESET}", exc_info=True); return None
        attempts += 1
        if attempts <= MAX_API_RETRIES: time.sleep(RETRY_DELAY_SECONDS * attempts)
    lg.error(f"{NEON_RED}Failed to get position info ({symbol}) after {MAX_API_RETRIES + 1} attempts. Last echo: {last_exception}{RESET}"); return None

def set_leverage_ccxt(exchange: ccxt.Exchange, symbol: str, leverage: int, market_info: MarketInfo, logger: logging.Logger) -> bool:
    """Sets the leverage for a derivatives symbol."""
    lg = logger
    if not market_info.get('is_contract', False): lg.info(f"Leverage setting skipped ({symbol}): Not contract."); return True
    if not isinstance(leverage, int) or leverage <= 0: lg.warning(f"Leverage setting skipped ({symbol}): Invalid leverage {leverage}."); return False
    if not hasattr(exchange, 'set_leverage') or not exchange.has.get('setLeverage'): lg.error(f"Exchange {exchange.id} does not support setLeverage."); return False
    market_id = market_info['id']; attempts = 0; last_exception = None
    while attempts <= MAX_API_RETRIES:
        try:
            lg.info(f"Attempting leverage set ({market_id} to {leverage}x, Attempt {attempts + 1})...")
            params = {}; category = market_info.get('contract_type_str', 'Linear').lower()
            if 'bybit' in exchange.id.lower():
                 if category not in ['linear', 'inverse']: lg.warning(f"Leverage skipped: Invalid category '{category}' ({symbol})."); return False
                 params = {'category': category, 'buyLeverage': str(leverage), 'sellLeverage': str(leverage)}; lg.debug(f"Using Bybit V5 leverage params: {params}")
            response = exchange.set_leverage(leverage=leverage, symbol=market_id, params=params); lg.debug(f"set_leverage raw response ({symbol}): {response}")
            ret_code_str = None; ret_msg = "N/A"
            if isinstance(response, dict):
                 info_dict = response.get('info', {}); ret_code_info = info_dict.get('retCode'); ret_code_top = response.get('retCode')
                 if ret_code_info is not None and ret_code_info != 0: ret_code_str = str(ret_code_info)
                 elif ret_code_top is not None: ret_code_str = str(ret_code_top)
                 else: ret_code_str = str(ret_code_info) if ret_code_info is not None else str(ret_code_top)
                 ret_msg = info_dict.get('retMsg', response.get('retMsg', 'Unknown Bybit msg'))
            if ret_code_str == '0': lg.info(f"{NEON_GREEN}Leverage set ({market_id} to {leverage}x, Code: 0).{RESET}"); return True
            elif ret_code_str == '110045': lg.info(f"{NEON_YELLOW}Leverage already {leverage}x ({market_id}, Code: 110045).{RESET}"); return True
            elif ret_code_str is not None and ret_code_str not in ['None', '0']: raise ccxt.ExchangeError(f"Bybit API error setting leverage ({symbol}): {ret_msg} (Code: {ret_code_str})")
            else: lg.info(f"{NEON_GREEN}Leverage set/confirmed ({market_id} to {leverage}x, No specific error code).{RESET}"); return True
        except ccxt.ExchangeError as e:
            last_exception = e; err_code_str = ""; match = re.search(r'(retCode|ret_code)=(\d+)', str(e.args[0] if e.args else ''), re.IGNORECASE);
            if match: err_code_str = match.group(2)
            if not err_code_str: err_code_str = str(getattr(e, 'code', '') or getattr(e, 'retCode', ''))
            err_str = str(e).lower(); lg.error(f"{NEON_RED}Exchange rift setting leverage ({market_id}): {e} (Code: {err_code_str}){RESET}")
            if err_code_str == '110045' or "leverage not modified" in err_str: lg.info(f"{NEON_YELLOW}Leverage already set (via error). Success.{RESET}"); return True
            fatal_codes = ['10001', '10004', '110009', '110013', '110028', '110043', '110044', '110055', '3400045']
            fatal_messages = ["margin mode", "position exists", "risk limit", "parameter error", "insufficient balance", "invalid leverage"]
            if err_code_str in fatal_codes or any(msg in err_str for msg in fatal_messages): lg.error(f"{NEON_RED} >> Hint: NON-RETRYABLE leverage error ({symbol}). Aborting.{RESET}"); return False
            if attempts >= MAX_API_RETRIES: lg.error(f"{NEON_RED}Max retries for ExchangeError setting leverage ({symbol}).{RESET}"); return False
        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e: last_exception = e; lg.warning(f"{NEON_YELLOW}Aetheric disturbance setting leverage ({market_id}): {e}. Retry {attempts + 1}...{RESET}"); if attempts >= MAX_API_RETRIES: lg.error(f"{NEON_RED}Max retries for NetworkError setting leverage ({symbol}).{RESET}"); return False
        except ccxt.AuthenticationError as e: last_exception = e; lg.critical(f"{NEON_RED}Auth ritual failed setting leverage ({symbol}): {e}. Stopping.{RESET}"); return False
        except Exception as e: last_exception = e; lg.error(f"{NEON_RED}Unexpected vortex setting leverage ({market_id}): {e}{RESET}", exc_info=True); return False
        attempts += 1; time.sleep(RETRY_DELAY_SECONDS * attempts)
    lg.error(f"{NEON_RED}Failed leverage set ({market_id} to {leverage}x) after {MAX_API_RETRIES + 1} attempts. Last echo: {last_exception}{RESET}"); return False

def calculate_position_size(balance: Decimal, risk_per_trade: float, initial_stop_loss_price: Decimal, entry_price: Decimal, market_info: MarketInfo, exchange: ccxt.Exchange, logger: logging.Logger) -> Optional[Decimal]:
    """Calculates position size based on risk, SL, and market constraints."""
    lg = logger; symbol = market_info['symbol']; quote_currency = market_info.get('quote', 'QUOTE'); base_currency = market_info.get('base', 'BASE')
    is_inverse = market_info.get('is_inverse', False); size_unit = base_currency if market_info.get('spot', False) else "Contracts"
    lg.info(f"{BRIGHT}--- Position Sizing Calculation ({symbol}) ---{RESET}")
    if balance <= Decimal('0'): lg.error(f"Sizing failed ({symbol}): Invalid balance {balance.normalize()}."); return None
    try: risk_decimal = Decimal(str(risk_per_trade)); assert Decimal('0') < risk_decimal <= Decimal('1')
    except Exception as e: lg.error(f"Sizing failed ({symbol}): Invalid risk '{risk_per_trade}': {e}"); return None
    if initial_stop_loss_price <= Decimal('0') or entry_price <= Decimal('0'): lg.error(f"Sizing failed ({symbol}): Entry ({entry_price.normalize()}) / SL ({initial_stop_loss_price.normalize()}) must be positive."); return None
    if initial_stop_loss_price == entry_price: lg.error(f"Sizing failed ({symbol}): SL price equals Entry price."); return None
    try:
        amount_step = market_info['amount_precision_step_decimal']; price_step = market_info['price_precision_step_decimal']
        min_amount = market_info['min_amount_decimal'] or Decimal('0'); max_amount = market_info['max_amount_decimal'] or Decimal('inf')
        min_cost = market_info['min_cost_decimal'] or Decimal('0'); max_cost = market_info['max_cost_decimal'] or Decimal('inf')
        contract_size = market_info['contract_size_decimal']
        assert amount_step and amount_step > 0; assert price_step and price_step > 0; assert contract_size > 0
        lg.debug(f"  Market Constraints ({symbol}): AmtStep={amount_step.normalize()}, Min/Max Amt={min_amount.normalize()}/{max_amount.normalize()}, Min/Max Cost={min_cost.normalize()}/{max_cost.normalize()}, ContrSize={contract_size.normalize()}")
    except (KeyError, ValueError, TypeError, AssertionError) as e: lg.error(f"Sizing failed ({symbol}): Error validating market details: {e}"); lg.debug(f" MarketInfo: {market_info}"); return None

    risk_amount_quote = (balance * risk_decimal).quantize(Decimal('1e-8'), ROUND_DOWN)
    stop_loss_distance = abs(entry_price - initial_stop_loss_price)
    if stop_loss_distance <= Decimal('0'): lg.error(f"Sizing failed ({symbol}): SL distance zero."); return None
    lg.info(f"  Balance: {balance.normalize()} {quote_currency}, Risk: {risk_decimal:.2%} ({risk_amount_quote.normalize()} {quote_currency})")
    lg.info(f"  Entry: {entry_price.normalize()}, SL: {initial_stop_loss_price.normalize()}, SL Dist: {stop_loss_distance.normalize()}")
    lg.info(f"  Contract Type: {market_info['contract_type_str']}")

    calculated_size = Decimal('0')
    try:
        if not is_inverse: # Linear / Spot
            value_change_per_unit = stop_loss_distance * contract_size
            if value_change_per_unit <= Decimal('1e-18'): lg.error(f"Sizing failed ({symbol}, Lin/Spot): Value change per unit near zero."); return None
            calculated_size = risk_amount_quote / value_change_per_unit
            lg.debug(f"  Linear/Spot Calc: {risk_amount_quote} / {value_change_per_unit} = {calculated_size}")
        else: # Inverse
            if entry_price <= 0 or initial_stop_loss_price <= 0: lg.error(f"Sizing failed ({symbol}, Inv): Entry/SL zero/negative."); return None
            inverse_factor = abs( (Decimal('1') / entry_price) - (Decimal('1') / initial_stop_loss_price) )
            if inverse_factor <= Decimal('1e-18'): lg.error(f"Sizing failed ({symbol}, Inv): Inverse factor near zero."); return None
            risk_per_contract = contract_size * inverse_factor
            if risk_per_contract <= Decimal('1e-18'): lg.error(f"Sizing failed ({symbol}, Inv): Risk per contract near zero."); return None
            calculated_size = risk_amount_quote / risk_per_contract
            lg.debug(f"  Inverse Calc: {risk_amount_quote} / {risk_per_contract} = {calculated_size}")
    except (InvalidOperation, OverflowError, ZeroDivisionError) as calc_err: lg.error(f"Sizing failed ({symbol}): Calc error: {calc_err}."); return None
    if calculated_size <= Decimal('0'): lg.error(f"Sizing failed ({symbol}): Initial size zero/negative ({calculated_size.normalize()})."); return None
    lg.info(f"  Initial Calculated Size ({symbol}) = {calculated_size.normalize()} {size_unit}")

    adjusted_size = calculated_size
    def estimate_cost(size: Decimal, price: Decimal) -> Optional[Decimal]:
        if price <= 0 or size <= 0: return None
        try: return (size * price * contract_size) if not is_inverse else (size * contract_size) / price
        except Exception: return None

    if min_amount > 0 and adjusted_size < min_amount: lg.warning(f"{NEON_YELLOW}Sizing ({symbol}): Calc size {adjusted_size.normalize()} < min {min_amount.normalize()}. Adjusting UP.{RESET}"); adjusted_size = min_amount
    if max_amount < Decimal('inf') and adjusted_size > max_amount: lg.warning(f"{NEON_YELLOW}Sizing ({symbol}): Calc size {adjusted_size.normalize()} > max {max_amount.normalize()}. Adjusting DOWN.{RESET}"); adjusted_size = max_amount
    lg.debug(f"  Size after Amount Limits ({symbol}): {adjusted_size.normalize()} {size_unit}")

    cost_adj_applied = False
    est_cost = estimate_cost(adjusted_size, entry_price)
    if est_cost is not None:
        lg.debug(f"  Estimated Cost (after amount limits, {symbol}): {est_cost.normalize()} {quote_currency}")
        if min_cost > 0 and est_cost < min_cost:
            lg.warning(f"{NEON_YELLOW}Sizing ({symbol}): Est cost {est_cost.normalize()} < min cost {min_cost.normalize()}. Increasing size.{RESET}")
            try:
                req_size = (min_cost / (entry_price * contract_size)) if not is_inverse else (min_cost * entry_price / contract_size)
                if req_size <= 0: raise ValueError("Invalid required size for min cost")
                lg.info(f"  Size required for min cost ({symbol}): {req_size.normalize()} {size_unit}")
                if max_amount < Decimal('inf') and req_size > max_amount: lg.error(f"{NEON_RED}Sizing failed ({symbol}): Cannot meet min cost ({min_cost.normalize()}) without exceeding max amount ({max_amount.normalize()}).{RESET}"); return None
                adjusted_size = max(min_amount, req_size); cost_adj_applied = True
            except Exception as cost_calc_err: lg.error(f"{NEON_RED}Sizing failed ({symbol}): Failed min cost size calc: {cost_calc_err}.{RESET}"); return None
        elif max_cost < Decimal('inf') and est_cost > max_cost:
            lg.warning(f"{NEON_YELLOW}Sizing ({symbol}): Est cost {est_cost.normalize()} > max cost {max_cost.normalize()}. Reducing size.{RESET}")
            try:
                max_size = (max_cost / (entry_price * contract_size)) if not is_inverse else (max_cost * entry_price / contract_size)
                if max_size <= 0: raise ValueError("Invalid max size for max cost")
                lg.info(f"  Max size allowed by max cost ({symbol}): {max_size.normalize()} {size_unit}")
                adjusted_size = max(min_amount, min(adjusted_size, max_size)); cost_adj_applied = True
            except Exception as cost_calc_err: lg.error(f"{NEON_RED}Sizing failed ({symbol}): Failed max cost size calc: {cost_calc_err}.{RESET}"); return None
    elif min_cost > 0 or max_cost < Decimal('inf'): lg.warning(f"Could not estimate cost ({symbol}) for limit check.")
    if cost_adj_applied: lg.info(f"  Size after Cost Limits ({symbol}): {adjusted_size.normalize()} {size_unit}")

    final_size = adjusted_size
    try:
        if amount_step <= 0: raise ValueError("Amount step zero/negative.")
        final_size = (adjusted_size / amount_step).quantize(Decimal('1'), ROUND_DOWN) * amount_step
        if final_size != adjusted_size: lg.info(f"Applied amount precision ({symbol}, Rounded DOWN to {amount_step.normalize()}): {adjusted_size.normalize()} -> {final_size.normalize()} {size_unit}")
    except Exception as fmt_err: lg.error(f"{NEON_RED}Error applying amount precision ({symbol}): {fmt_err}. Using unrounded: {final_size.normalize()}{RESET}")

    if final_size <= Decimal('0'): lg.error(f"{NEON_RED}Sizing failed ({symbol}): Final size zero/negative ({final_size.normalize()}).{RESET}"); return None
    if min_amount > 0 and final_size < min_amount: lg.error(f"{NEON_RED}Sizing failed ({symbol}): Final size {final_size.normalize()} < min amount {min_amount.normalize()} after precision.{RESET}"); return None
    if max_amount < Decimal('inf') and final_size > max_amount: lg.error(f"{NEON_RED}Sizing failed ({symbol}): Final size {final_size.normalize()} > max amount {max_amount.normalize()} after precision.{RESET}"); return None

    final_cost = estimate_cost(final_size, entry_price)
    if final_cost is not None:
        lg.debug(f"  Final Estimated Cost ({symbol}): {final_cost.normalize()} {quote_currency}")
        if min_cost > 0 and final_cost < min_cost:
             lg.warning(f"{NEON_YELLOW}Sizing ({symbol}): Final cost {final_cost.normalize()} < min cost {min_cost.normalize()} after rounding.{RESET}")
             try:
                 next_size = final_size + amount_step; next_cost = estimate_cost(next_size, entry_price)
                 if next_cost is not None:
                     can_bump = (next_cost >= min_cost) and (max_amount == Decimal('inf') or next_size <= max_amount) and (max_cost == Decimal('inf') or next_cost <= max_cost)
                     if can_bump: lg.info(f"{NEON_YELLOW}Bumping final size ({symbol}) up one step to {next_size.normalize()} for min cost.{RESET}"); final_size = next_size; final_cost = estimate_cost(final_size, entry_price); lg.debug(f"  Final Cost after bump: {final_cost.normalize() if final_cost else 'N/A'}")
                     else: lg.error(f"{NEON_RED}Sizing failed ({symbol}): Cannot meet min cost even bumping size due to other limits.{RESET}"); return None
                 else: lg.error(f"{NEON_RED}Sizing failed ({symbol}): Could not estimate cost for bumped size.{RESET}"); return None
             except Exception as bump_err: lg.error(f"{NEON_RED}Sizing failed ({symbol}): Error bumping size: {bump_err}.{RESET}"); return None
        elif max_cost < Decimal('inf') and final_cost > max_cost: lg.error(f"{NEON_RED}Sizing failed ({symbol}): Final cost {final_cost.normalize()} > max cost {max_cost.normalize()} after precision.{RESET}"); return None
    elif min_cost > 0: lg.warning(f"Could not perform final cost check ({symbol}) after precision.")

    lg.info(f"{NEON_GREEN}{BRIGHT}>>> Final Calculated Position Size ({symbol}): {final_size.normalize()} {size_unit} <<< {RESET}")
    lg.info(f"{BRIGHT}--- End Position Sizing ({symbol}) ---{RESET}")
    return final_size

def cancel_order(exchange: ccxt.Exchange, order_id: str, symbol: str, logger: logging.Logger) -> bool:
    """Cancels an order by ID with retries."""
    lg = logger
    attempts = 0
    last_exception = None
    lg.info(f"Attempting to cancel order ID: {order_id} for {symbol}...")
    while attempts <= MAX_API_RETRIES:
        try:
            lg.debug(f"Cancel order attempt {attempts + 1} for ID {order_id} ({symbol})...")
            # Bybit V5 might need symbol even for cancel by ID
            params = {}
            if 'bybit' in exchange.id.lower():
                try:
                    market = exchange.market(symbol)
                    params['category'] = 'linear' if market.get('linear') else 'inverse' if market.get('inverse') else 'spot'
                    params['symbol'] = market['id']
                except Exception as e:
                    lg.warning(f"Could not determine category/market_id for cancel order {order_id} ({symbol}): {e}")

            exchange.cancel_order(order_id, symbol, params=params)
            lg.info(f"{NEON_GREEN}Successfully cancelled order ID: {order_id} for {symbol}.{RESET}")
            return True
        except ccxt.OrderNotFound:
            lg.warning(f"{NEON_YELLOW}Order ID {order_id} ({symbol}) not found. Already cancelled or filled? Treating as success.{RESET}")
            return True # Order doesn't exist, cancellation goal achieved
        except ccxt.NetworkError as e: last_exception = e; lg.warning(f"{NEON_YELLOW}Network error cancelling order {order_id} ({symbol}): {e}. Retry {attempts + 1}...{RESET}")
        except ccxt.RateLimitExceeded as e: last_exception = e; wait_time = RETRY_DELAY_SECONDS * 2; lg.warning(f"{NEON_YELLOW}Rate limit cancelling order {order_id} ({symbol}): {e}. Pausing {wait_time}s...{RESET}"); time.sleep(wait_time); continue
        except ccxt.ExchangeError as e: last_exception = e; lg.error(f"{NEON_RED}Exchange error cancelling order {order_id} ({symbol}): {e}{RESET}") # Assume retryable for now
        except Exception as e: last_exception = e; lg.error(f"{NEON_RED}Unexpected error cancelling order {order_id} ({symbol}): {e}{RESET}", exc_info=True); return False # Non-retryable
        attempts += 1
        if attempts <= MAX_API_RETRIES: time.sleep(RETRY_DELAY_SECONDS * attempts)
    lg.error(f"{NEON_RED}Failed to cancel order ID {order_id} ({symbol}) after {MAX_API_RETRIES + 1} attempts. Last echo: {last_exception}{RESET}"); return False

def place_trade(exchange: ccxt.Exchange, symbol: str, trade_signal: str, position_size: Decimal, market_info: MarketInfo, logger: logging.Logger, reduce_only: bool = False, params: Optional[Dict] = None) -> Optional[Dict]:
    """Places a market order (buy or sell)."""
    lg = logger; side_map = {"BUY": "buy", "SELL": "sell", "EXIT_SHORT": "buy", "EXIT_LONG": "sell"}; side = side_map.get(trade_signal.upper())
    if side is None: lg.error(f"Invalid trade signal '{trade_signal}' ({symbol})."); return None
    if not isinstance(position_size, Decimal) or position_size <= Decimal('0'): lg.error(f"Invalid position size '{position_size}' ({symbol})."); return None
    order_type = 'market'; is_contract = market_info.get('is_contract', False); base_currency = market_info.get('base', 'BASE')
    size_unit = base_currency if market_info.get('spot', False) else "Contracts"; action_desc = "Close/Reduce" if reduce_only else "Open/Increase"; market_id = market_info['id']
    try: amount_float = float(position_size); assert amount_float > 1e-15
    except Exception as float_err: lg.error(f"Failed to convert size {position_size.normalize()} ({symbol}) to float: {float_err}"); return None

    order_args = {'symbol': market_id, 'type': order_type, 'side': side, 'amount': amount_float}; order_params = {}
    if 'bybit' in exchange.id.lower() and is_contract:
        try:
            category = market_info.get('contract_type_str', 'Linear').lower(); assert category in ['linear', 'inverse']
            order_params = {'category': category, 'positionIdx': 0}
            if reduce_only: order_params['reduceOnly'] = True; order_params['timeInForce'] = 'IOC'
            lg.debug(f"Using Bybit V5 order params ({symbol}): {order_params}")
        except Exception as e: lg.error(f"Failed to set Bybit V5 params ({symbol}): {e}. Order might fail.")
    if params: order_params.update(params)
    if order_params: order_args['params'] = order_params

    lg.info(f"{BRIGHT}===> Attempting {action_desc} | {side.upper()} {order_type.upper()} Order | {symbol} | Size: {position_size.normalize()} {size_unit} <==={RESET}")
    if order_params: lg.debug(f"  with Params ({symbol}): {order_params}")

    attempts = 0; last_exception = None
    while attempts <= MAX_API_RETRIES:
        try:
            lg.debug(f"Executing exchange.create_order ({symbol}, Attempt {attempts + 1})...")
            order_result = exchange.create_order(**order_args)
            order_id = order_result.get('id', 'N/A'); status = order_result.get('status', 'N/A')
            avg_price = _safe_market_decimal(order_result.get('average'), 'order.avg', True)
            filled = _safe_market_decimal(order_result.get('filled'), 'order.filled', True)
            log_msg = f"{NEON_GREEN}{action_desc} Order Placed!{RESET} ID: {order_id}, Status: {status}"
            if avg_price: log_msg += f", AvgFill: ~{avg_price.normalize()}"
            if filled: log_msg += f", Filled: {filled.normalize()}"
            lg.info(log_msg); lg.debug(f"Full order result ({symbol}): {order_result}"); return order_result
        except ccxt.InsufficientFunds as e: last_exception = e; lg.error(f"{NEON_RED}Order Failed ({symbol} {action_desc}): Insufficient funds. {e}{RESET}"); return None
        except ccxt.InvalidOrder as e:
            last_exception = e; lg.error(f"{NEON_RED}Order Failed ({symbol} {action_desc}): Invalid order params. {e}{RESET}"); lg.error(f"  Args: {order_args}")
            err_lower = str(e).lower()
            if "minimum" in err_lower or "too small" in err_lower: lg.error(f"  >> Hint: Check size/cost vs market mins (MinAmt: {market_info.get('min_amount_decimal')}, MinCost: {market_info.get('min_cost_decimal')}).")
            elif "precision" in err_lower or "lot size" in err_lower: lg.error(f"  >> Hint: Check size vs amount step ({market_info.get('amount_precision_step_decimal')}).")
            elif "exceed" in err_lower or "too large" in err_lower: lg.error(f"  >> Hint: Check size/cost vs market maxs (MaxAmt: {market_info.get('max_amount_decimal')}, MaxCost: {market_info.get('max_cost_decimal')}).")
            elif "reduce only" in err_lower: lg.error(f"  >> Hint: Reduce-only failed. Check position size/direction.")
            return None
        except ccxt.ExchangeError as e:
            last_exception = e; err_code_str = ""; match = re.search(r'(retCode|ret_code)=(\d+)', str(e.args[0] if e.args else ''), re.IGNORECASE);
            if match: err_code_str = match.group(2)
            if not err_code_str: err_code_str = str(getattr(e, 'code', '') or getattr(e, 'retCode', ''))
            lg.error(f"{NEON_RED}Order Failed ({symbol} {action_desc}): Exchange rift. {e} (Code: {err_code_str}){RESET}")
            fatal_codes = ['10001','10004','110007','110013','110014','110017','110025','110040','30086','3303001','3303005','3400060','3400088']
            fatal_msgs = ["invalid parameter", "precision", "exceed limit", "risk limit", "invalid symbol", "reduce only check failed", "lot size"]
            if err_code_str in fatal_codes or any(msg in str(e).lower() for msg in fatal_msgs): lg.error(f"{NEON_RED} >> Hint: NON-RETRYABLE order error ({symbol}).{RESET}"); return None
            if attempts >= MAX_API_RETRIES: lg.error(f"{NEON_RED}Max retries for ExchangeError placing order ({symbol}).{RESET}"); return None
        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e: last_exception = e; lg.warning(f"{NEON_YELLOW}Aetheric disturbance placing order ({symbol}): {e}. Retry {attempts + 1}...{RESET}"); if attempts >= MAX_API_RETRIES: lg.error(f"{NEON_RED}Max retries for NetworkError placing order ({symbol}).{RESET}"); return None
        except ccxt.RateLimitExceeded as e: last_exception = e; wait_time = RETRY_DELAY_SECONDS * 3; lg.warning(f"{NEON_YELLOW}Rate limit placing order ({symbol}): {e}. Pausing {wait_time}s...{RESET}"); time.sleep(wait_time); continue
        except ccxt.AuthenticationError as e: last_exception = e; lg.critical(f"{NEON_RED}Auth ritual failed placing order ({symbol}): {e}. Stopping.{RESET}"); return None
        except Exception as e: last_exception = e; lg.error(f"{NEON_RED}Unexpected vortex placing order ({symbol}): {e}{RESET}", exc_info=True); return None
        attempts += 1
        if attempts <= MAX_API_RETRIES: time.sleep(RETRY_DELAY_SECONDS * attempts)
    lg.error(f"{NEON_RED}Failed to place {action_desc} order ({symbol}) after {MAX_API_RETRIES + 1} attempts. Last echo: {last_exception}{RESET}"); return None

def _set_position_protection(exchange: ccxt.Exchange, symbol: str, market_info: MarketInfo, position_info: PositionInfo, logger: logging.Logger, stop_loss_price: Optional[Decimal] = None, take_profit_price: Optional[Decimal] = None, trailing_stop_distance: Optional[Decimal] = None, tsl_activation_price: Optional[Decimal] = None) -> bool:
    """Internal helper: Sets SL/TP/TSL using Bybit's V5 private API."""
    lg = logger; endpoint = '/v5/position/set-trading-stop'
    if not market_info.get('is_contract', False): lg.warning(f"Protection skipped ({symbol}): Not contract."); return False
    if not position_info: lg.error(f"Protection failed ({symbol}): Missing position info."); return False
    pos_side = position_info.get('side'); entry_price_any = position_info.get('entryPrice')
    if pos_side not in ['long', 'short']: lg.error(f"Protection failed ({symbol}): Invalid side '{pos_side}'."); return False
    try: assert entry_price_any is not None; entry_price = Decimal(str(entry_price_any)); assert entry_price > 0
    except Exception as e: lg.error(f"Protection failed ({symbol}): Invalid entry price '{entry_price_any}': {e}"); return False
    try: price_tick = market_info['price_precision_step_decimal']; assert price_tick and price_tick > 0
    except Exception as e: lg.error(f"Protection failed ({symbol}): Invalid price precision: {e}"); return False

    params_to_set: Dict[str, Any] = {}; log_parts: List[str] = [f"{BRIGHT}Attempting protection set ({symbol} {pos_side.upper()} @ {entry_price.normalize()}):{RESET}"]
    any_requested = False; set_tsl_active = False

    try:
        def format_param(price_decimal: Optional[Decimal], param_name: str) -> Optional[str]:
            if price_decimal is None: return None
            if price_decimal == 0: return "0" # Allow clearing
            if price_decimal < 0: lg.warning(f"Invalid negative price {price_decimal.normalize()} for {param_name} ({symbol}). Ignoring."); return None
            fmt_str = _format_price(exchange, market_info['symbol'], price_decimal)
            if fmt_str: return fmt_str
            else: lg.error(f"Failed to format {param_name} ({symbol}) value {price_decimal.normalize()}."); return None

        # TSL
        if isinstance(trailing_stop_distance, Decimal):
            any_requested = True
            if trailing_stop_distance > 0:
                min_dist = max(trailing_stop_distance, price_tick)
                if not isinstance(tsl_activation_price, Decimal) or tsl_activation_price <= 0: lg.error(f"TSL failed ({symbol}): Valid activation price required for TSL distance > 0.")
                else:
                    is_valid_act = (pos_side == 'long' and tsl_activation_price > entry_price) or (pos_side == 'short' and tsl_activation_price < entry_price)
                    if not is_valid_act: lg.error(f"TSL failed ({symbol}): Activation {tsl_activation_price.normalize()} invalid vs entry {entry_price.normalize()} for {pos_side}.")
                    else:
                        fmt_dist = format_param(min_dist, "TSL Distance"); fmt_act = format_param(tsl_activation_price, "TSL Activation")
                        if fmt_dist and fmt_act: params_to_set['trailingStop'] = fmt_dist; params_to_set['activePrice'] = fmt_act; log_parts.append(f"  - Setting TSL: Dist={fmt_dist}, Act={fmt_act}"); set_tsl_active = True
                        else: lg.error(f"TSL failed ({symbol}): Could not format params (Dist: {fmt_dist}, Act: {fmt_act}).")
            elif trailing_stop_distance == 0: params_to_set['trailingStop'] = "0"; log_parts.append("  - Clearing TSL")
            else: lg.warning(f"Invalid negative TSL distance ({trailing_stop_distance.normalize()}) for {symbol}. Ignoring.")

        # SL (ignored if TSL active)
        if not set_tsl_active and isinstance(stop_loss_price, Decimal):
            any_requested = True
            if stop_loss_price > 0:
                is_valid_sl = (pos_side == 'long' and stop_loss_price < entry_price) or (pos_side == 'short' and stop_loss_price > entry_price)
                if not is_valid_sl: lg.error(f"SL failed ({symbol}): SL price {stop_loss_price.normalize()} invalid vs entry {entry_price.normalize()} for {pos_side}.")
                else:
                    fmt_sl = format_param(stop_loss_price, "Stop Loss")
                    if fmt_sl: params_to_set['stopLoss'] = fmt_sl; log_parts.append(f"  - Setting SL: {fmt_sl}")
                    else: lg.error(f"SL failed ({symbol}): Could not format SL price {stop_loss_price.normalize()}.")
            elif stop_loss_price == 0: params_to_set['stopLoss'] = "0"; log_parts.append("  - Clearing SL")

        # TP
        if isinstance(take_profit_price, Decimal):
            any_requested = True
            if take_profit_price > 0:
                is_valid_tp = (pos_side == 'long' and take_profit_price > entry_price) or (pos_side == 'short' and take_profit_price < entry_price)
                if not is_valid_tp: lg.error(f"TP failed ({symbol}): TP price {take_profit_price.normalize()} invalid vs entry {entry_price.normalize()} for {pos_side}.")
                else:
                    fmt_tp = format_param(take_profit_price, "Take Profit")
                    if fmt_tp: params_to_set['takeProfit'] = fmt_tp; log_parts.append(f"  - Setting TP: {fmt_tp}")
                    else: lg.error(f"TP failed ({symbol}): Could not format TP price {take_profit_price.normalize()}.")
            elif take_profit_price == 0: params_to_set['takeProfit'] = "0"; log_parts.append("  - Clearing TP")

    except Exception as validation_err: lg.error(f"Unexpected error during protection validation ({symbol}): {validation_err}", exc_info=True); return False

    if not params_to_set:
        if any_requested: lg.warning(f"Protection skipped ({symbol}): No valid parameters after validation."); return False
        else: lg.debug(f"No protection changes requested ({symbol}). Skipping API."); return True

    params_to_set['symbol'] = market_info['id']; params_to_set['category'] = market_info.get('contract_type_str', 'Linear').lower(); params_to_set['positionIdx'] = 0
    lg.info("\n".join(log_parts)); lg.debug(f"  Final API params for {endpoint} ({symbol}): {params_to_set}")

    attempts = 0; last_exception = None
    while attempts <= MAX_API_RETRIES:
        try:
            lg.debug(f"Executing private_post {endpoint} ({symbol}, Attempt {attempts + 1})...")
            response = exchange.private_post(endpoint, params=params_to_set); lg.debug(f"Raw response from {endpoint} ({symbol}): {response}")
            ret_code = response.get('retCode'); ret_msg = response.get('retMsg', 'Unknown msg')
            if ret_code == 0: lg.info(f"{NEON_GREEN}Protection set/updated successfully ({symbol}, Code: 0).{RESET}"); return True
            else: raise ccxt.ExchangeError(f"Bybit API error setting protection ({symbol}): {ret_msg} (Code: {ret_code})")
        except ccxt.ExchangeError as e:
            last_exception = e; err_code_str = ""; match = re.search(r'(retCode|ret_code)=(\d+)', str(e.args[0] if e.args else ''), re.IGNORECASE);
            if match: err_code_str = match.group(2)
            if not err_code_str: err_code_str = str(getattr(e, 'code', '') or getattr(e, 'retCode', ''))
            lg.error(f"{NEON_RED}Protection setting failed ({symbol}): Exchange rift. {e} (Code: {err_code_str}){RESET}")
            fatal_codes = ['10001','110013','110025','110043','3400048','3400051','3400052','3400070','3400071','3400072','3400073']
            fatal_msgs = ["parameter error", "invalid price", "position status", "cannot be the same", "activation price", "distance invalid"]
            if err_code_str in fatal_codes or any(msg in str(e).lower() for msg in fatal_msgs): lg.error(f"{NEON_RED} >> Hint: NON-RETRYABLE protection error ({symbol}).{RESET}"); return False
            if attempts >= MAX_API_RETRIES: lg.error(f"{NEON_RED}Max retries for ExchangeError setting protection ({symbol}).{RESET}"); return False
        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e: last_exception = e; lg.warning(f"{NEON_YELLOW}Aetheric disturbance setting protection ({symbol}): {e}. Retry {attempts + 1}...{RESET}"); if attempts >= MAX_API_RETRIES: lg.error(f"{NEON_RED}Max retries for NetworkError setting protection ({symbol}).{RESET}"); return False
        except ccxt.RateLimitExceeded as e: last_exception = e; wait_time = RETRY_DELAY_SECONDS * 3; lg.warning(f"{NEON_YELLOW}Rate limit setting protection ({symbol}): {e}. Pausing {wait_time}s...{RESET}"); time.sleep(wait_time); continue
        except ccxt.AuthenticationError as e: last_exception = e; lg.critical(f"{NEON_RED}Auth ritual failed setting protection ({symbol}): {e}. Stopping.{RESET}"); return False
        except Exception as e: last_exception = e; lg.error(f"{NEON_RED}Unexpected vortex setting protection ({symbol}): {e}{RESET}", exc_info=True); return False
        attempts += 1
        if attempts <= MAX_API_RETRIES: time.sleep(RETRY_DELAY_SECONDS * attempts)
    lg.error(f"{NEON_RED}Failed to set protection ({symbol}) after {MAX_API_RETRIES + 1} attempts. Last echo: {last_exception}{RESET}"); return False


# --- Strategy Implementation (Volumatic Trend + Pivot Order Blocks) ---
def find_pivots(df: pd.DataFrame, left: int, right: int, use_wicks: bool) -> Tuple[pd.Series, pd.Series]:
    """Identifies Pivot Highs and Lows based on lookback periods."""
    high_col = 'high' if use_wicks else 'close' # Use high/low for wicks, close/open for body pivots? Let's stick to high/low for simplicity now.
    low_col = 'low' if use_wicks else 'close'   # Or use 'open' if close is lower? Wick logic is simpler.

    # Ensure index is datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame index must be a DatetimeIndex for pivot calculation.")

    # Calculate rolling max/min over the lookback window (left + current + right)
    window_size = left + right + 1
    # Shift required to align window correctly for pivot identification
    # We need to compare candle 'i' with 'left' candles before and 'right' candles after.
    # rolling(center=False) looks back, so we need to shift the result forward by 'right' periods.
    rolling_max = df[high_col].rolling(window=window_size, closed='both').max().shift(-right)
    rolling_min = df[low_col].rolling(window=window_size, closed='both').min().shift(-right)

    # A pivot high occurs if the current high is the maximum in the window
    pivot_highs = df[high_col] == rolling_max
    # A pivot low occurs if the current low is the minimum in the window
    pivot_lows = df[low_col] == rolling_min

    # Filter out consecutive pivots (optional, but often desired)
    # Keep only the first pivot in a consecutive sequence
    # ph_filtered = pivot_highs & (~pivot_highs.shift(1).fillna(False))
    # pl_filtered = pivot_lows & (~pivot_lows.shift(1).fillna(False))
    # Re-evaluate: Simple consecutive filtering might remove valid pivots if price consolidates.
    # Let's return the raw pivots for now, OB logic can handle overlaps if needed.

    return pivot_highs, pivot_lows

def calculate_strategy_signals(df: pd.DataFrame, config: Dict[str, Any], logger: logging.Logger) -> StrategyAnalysisResults:
    """Calculates Volumatic Trend, Pivots, Order Blocks, and generates signals."""
    lg = logger
    lg.debug(f"Calculating strategy signals for DataFrame with {len(df)} candles...")
    # --- Parameter Extraction ---
    try:
        sp = config['strategy_params']
        vt_len = sp['vt_length']; vt_atr_period = sp['vt_atr_period']
        vt_vol_ema = sp['vt_vol_ema_length']; vt_atr_mult = Decimal(str(sp['vt_atr_multiplier']))
        ob_source = sp['ob_source']; ph_left, ph_right = sp['ph_left'], sp['ph_right']
        pl_left, pl_right = sp['pl_left'], sp['pl_right']; ob_extend = sp['ob_extend']
        ob_max_boxes = sp['ob_max_boxes']; ob_entry_prox_factor = Decimal(str(sp['ob_entry_proximity_factor']))
        ob_exit_prox_factor = Decimal(str(sp['ob_exit_proximity_factor']))
        use_wicks = ob_source.lower() == "wicks"
    except (KeyError, ValueError, InvalidOperation, TypeError) as e:
        lg.error(f"Strategy calc failed: Error accessing params: {e}"); return StrategyAnalysisResults(dataframe=df, last_close=Decimal('NaN'), current_trend_up=None, trend_just_changed=False, active_bull_boxes=[], active_bear_boxes=[], vol_norm_int=None, atr=None, upper_band=None, lower_band=None, signal="NONE")

    # --- Indicator Calculations ---
    df_calc = df.copy() # Work on a copy
    try:
        # Convert relevant columns to float for pandas_ta, store original Decimals
        float_cols = ['open', 'high', 'low', 'close', 'volume']
        df_float = pd.DataFrame(index=df_calc.index)
        for col in float_cols:
            if col in df_calc.columns:
                # Handle potential Decimal('NaN') before converting
                df_float[col] = pd.to_numeric(df_calc[col].apply(lambda x: x if x.is_finite() else np.nan), errors='coerce')
            else: df_float[col] = np.nan # Ensure column exists even if missing in input

        # 1. Volumatic Trend
        ema_col = f'EMA_{vt_len}'
        df_float[ema_col] = ta.ema(df_float['close'], length=vt_len)
        df_float['ATR'] = ta.atr(df_float['high'], df_float['low'], df_float['close'], length=vt_atr_period)
        df_float['VT_UpperBand'] = df_float[ema_col] + (df_float['ATR'] * float(vt_atr_mult))
        df_float['VT_LowerBand'] = df_float[ema_col] - (df_float['ATR'] * float(vt_atr_mult))
        if 'volume' in df_float.columns and df_float['volume'].sum() > 0:
            vol_ema_series = ta.ema(df_float['volume'], length=vt_vol_ema)
            df_float['VolNorm'] = (df_float['volume'] / vol_ema_series.replace(0, np.nan)) * 100
            df_float['VolNorm'].fillna(0, inplace=True)
            df_float['VolNormInt'] = df_float['VolNorm'].clip(0, 500).astype(int) # Example cap
        else: df_float['VolNormInt'] = 0
        df_float['TrendUp'] = df_float['close'] > df_float[ema_col]
        # Ensure TrendUp has valid booleans before diff(), handle initial NaNs
        df_float['TrendUp'] = df_float['TrendUp'].astype('boolean').fillna(method='bfill') # Forward fill first, then backfill? Or just backfill?
        df_float['TrendChanged'] = df_float['TrendUp'].diff() != False # Compare diff to False to handle NaN->True/False transitions

        # 2. Pivots
        df_calc['PivotHigh'], df_calc['PivotLow'] = find_pivots(df_calc, ph_left, ph_right, use_wicks)

        # --- Convert calculated float indicators back to Decimal in df_calc ---
        calculated_float_cols = [ema_col, 'ATR', 'VT_UpperBand', 'VT_LowerBand']
        for col in calculated_float_cols:
            if col in df_float.columns:
                df_calc[col] = df_float[col].apply(lambda x: Decimal(str(x)) if pd.notna(x) and np.isfinite(x) else Decimal('NaN'))
        # Add boolean/int columns
        if 'TrendUp' in df_float.columns: df_calc['TrendUp'] = df_float['TrendUp'].astype('boolean') # Keep as nullable boolean
        if 'TrendChanged' in df_float.columns: df_calc['TrendChanged'] = df_float['TrendChanged']
        if 'VolNormInt' in df_float.columns: df_calc['VolNormInt'] = df_float['VolNormInt']

    except Exception as e:
        lg.error(f"Error calculating indicators: {e}", exc_info=True)
        return StrategyAnalysisResults(dataframe=df, last_close=Decimal('NaN'), current_trend_up=None, trend_just_changed=False, active_bull_boxes=[], active_bear_boxes=[], vol_norm_int=None, atr=None, upper_band=None, lower_band=None, signal="NONE")

    # 3. Order Block Identification & Management
    active_bull_boxes: List[OrderBlock] = []
    active_bear_boxes: List[OrderBlock] = []
    try:
        pivot_high_indices = df_calc.index[df_calc['PivotHigh']]
        pivot_low_indices = df_calc.index[df_calc['PivotLow']]
        latest_ts = df_calc.index[-1]

        # Process Bearish OBs from Pivot Highs
        for ph_ts in pivot_high_indices:
            if len(active_bear_boxes) >= ob_max_boxes: break # Limit boxes
            pivot_candle = df_calc.loc[ph_ts]
            # Define OB based on source (Wicks or Body)
            ob_top = pivot_candle['high']
            ob_bottom = min(pivot_candle['open'], pivot_candle['close']) if not use_wicks else pivot_candle['low']
            # Check for valid OB (top > bottom)
            if ob_top <= ob_bottom: continue
            # Create OB
            ob_id = f"B_{ph_ts.value // 10**9}" # Unique ID based on timestamp
            new_ob = OrderBlock(id=ob_id, type='bear', timestamp=ph_ts, top=ob_top, bottom=ob_bottom, active=True, violated=False, violation_ts=None, extended_to_ts=ph_ts)
            active_bear_boxes.append(new_ob)
        # Sort by timestamp descending to easily manage max boxes (remove oldest if needed)
        active_bear_boxes.sort(key=lambda x: x['timestamp'], reverse=True)
        active_bear_boxes = active_bear_boxes[:ob_max_boxes]

        # Process Bullish OBs from Pivot Lows
        for pl_ts in pivot_low_indices:
            if len(active_bull_boxes) >= ob_max_boxes: break
            pivot_candle = df_calc.loc[pl_ts]
            ob_bottom = pivot_candle['low']
            ob_top = max(pivot_candle['open'], pivot_candle['close']) if not use_wicks else pivot_candle['high']
            if ob_top <= ob_bottom: continue
            ob_id = f"L_{pl_ts.value // 10**9}"
            new_ob = OrderBlock(id=ob_id, type='bull', timestamp=pl_ts, top=ob_top, bottom=ob_bottom, active=True, violated=False, violation_ts=None, extended_to_ts=pl_ts)
            active_bull_boxes.append(new_ob)
        active_bull_boxes.sort(key=lambda x: x['timestamp'], reverse=True)
        active_bull_boxes = active_bull_boxes[:ob_max_boxes]

        # Check Violations and Extend OBs
        for idx, candle in df_calc.iterrows():
            candle_close = candle['close']
            # Check Bear OB violations
            for ob in active_bear_boxes:
                if ob['active'] and idx > ob['timestamp']: # Only check candles after OB formation
                    if candle_close > ob['top']: # Violation condition
                        ob['active'] = False
                        ob['violated'] = True
                        ob['violation_ts'] = idx
                    elif ob_extend and not ob['violated']:
                         ob['extended_to_ts'] = idx # Extend active box
            # Check Bull OB violations
            for ob in active_bull_boxes:
                 if ob['active'] and idx > ob['timestamp']:
                     if candle_close < ob['bottom']: # Violation condition
                         ob['active'] = False
                         ob['violated'] = True
                         ob['violation_ts'] = idx
                     elif ob_extend and not ob['violated']:
                          ob['extended_to_ts'] = idx

        # Filter out inactive boxes for the final result
        active_bull_boxes = [ob for ob in active_bull_boxes if ob['active']]
        active_bear_boxes = [ob for ob in active_bear_boxes if ob['active']]
        lg.debug(f"OB Analysis: Found {len(active_bull_boxes)} active Bull OBs, {len(active_bear_boxes)} active Bear OBs.")

    except Exception as e:
        lg.error(f"Error during Pivot/OB processing: {e}", exc_info=True)
        # Continue without OBs if processing fails

    # --- Extract Last Values ---
    last_row = df_calc.iloc[-1] if not df_calc.empty else None
    last_close = last_row['close'] if last_row is not None and pd.notna(last_row['close']) else Decimal('NaN')
    current_trend_up = pd.NA if last_row is None or 'TrendUp' not in last_row or pd.isna(last_row['TrendUp']) else bool(last_row['TrendUp'])
    trend_just_changed = False # Default
    if last_row is not None and 'TrendChanged' in last_row and pd.notna(last_row['TrendChanged']):
         # Check the second to last row as well to confirm the change happened *on* the last candle
         if len(df_calc) > 1:
             second_last_row = df_calc.iloc[-2]
             if 'TrendUp' in second_last_row and pd.notna(second_last_row['TrendUp']):
                 trend_just_changed = bool(last_row['TrendUp']) != bool(second_last_row['TrendUp'])

    vol_norm_int = int(last_row['VolNormInt']) if last_row is not None and 'VolNormInt' in last_row and pd.notna(last_row['VolNormInt']) else None
    atr = last_row['ATR'] if last_row is not None and 'ATR' in last_row and pd.notna(last_row['ATR']) and last_row['ATR'] > 0 else None
    upper_band = last_row['VT_UpperBand'] if last_row is not None and 'VT_UpperBand' in last_row and pd.notna(last_row['VT_UpperBand']) else None
    lower_band = last_row['VT_LowerBand'] if last_row is not None and 'VT_LowerBand' in last_row and pd.notna(last_row['VT_LowerBand']) else None

    # --- Signal Generation ---
    signal = "NONE"
    if pd.notna(current_trend_up) and pd.notna(last_close):
        # Entry Signals
        if current_trend_up is True:
            for ob in active_bull_boxes: # Look for nearby Bull OB in uptrend
                # Price needs to be close to or inside the OB
                entry_threshold = ob['top'] * ob_entry_prox_factor
                if last_close <= entry_threshold and last_close >= ob['bottom']:
                    lg.debug(f"Potential BUY signal: Uptrend, price {last_close} near Bull OB {ob['id']} ({ob['bottom']}-{ob['top']})")
                    signal = "BUY"; break # Take first valid signal
        elif current_trend_up is False:
            for ob in active_bear_boxes: # Look for nearby Bear OB in downtrend
                entry_threshold = ob['bottom'] / ob_entry_prox_factor
                if last_close >= entry_threshold and last_close <= ob['top']:
                    lg.debug(f"Potential SELL signal: Downtrend, price {last_close} near Bear OB {ob['id']} ({ob['bottom']}-{ob['top']})")
                    signal = "SELL"; break

        # Exit Signals (Check only if no entry signal generated)
        if signal == "NONE":
            if trend_just_changed: # Exit on trend reversal
                if current_trend_up is False: signal = "EXIT_LONG" # Trend changed to down
                elif current_trend_up is True: signal = "EXIT_SHORT" # Trend changed to up
                lg.debug(f"Exit signal due to trend reversal: {signal}")
            else: # Check for OB violation as exit trigger
                if current_trend_up is True: # Currently in potential Long
                    for ob in active_bull_boxes: # Check if price broke below a supporting Bull OB
                        exit_threshold = ob['bottom'] * ob_exit_prox_factor
                        if last_close <= exit_threshold:
                             lg.debug(f"Potential EXIT_LONG signal: Price {last_close} violated Bull OB {ob['id']} ({ob['bottom']})")
                             signal = "EXIT_LONG"; break
                elif current_trend_up is False: # Currently in potential Short
                     for ob in active_bear_boxes: # Check if price broke above a supporting Bear OB
                         exit_threshold = ob['top'] / ob_exit_prox_factor
                         if last_close >= exit_threshold:
                              lg.debug(f"Potential EXIT_SHORT signal: Price {last_close} violated Bear OB {ob['id']} ({ob['top']})")
                              signal = "EXIT_SHORT"; break

    lg.debug(f"Strategy Calc Complete. Last Close: {last_close.normalize() if pd.notna(last_close) else 'N/A'}, TrendUp: {current_trend_up}, TrendChanged: {trend_just_changed}, VolNorm: {vol_norm_int}, ATR: {atr.normalize() if atr else 'N/A'}, Signal: {signal}")

    results = StrategyAnalysisResults(
        dataframe=df_calc, last_close=last_close, current_trend_up=current_trend_up,
        trend_just_changed=trend_just_changed, active_bull_boxes=active_bull_boxes,
        active_bear_boxes=active_bear_boxes, vol_norm_int=vol_norm_int, atr=atr,
        upper_band=upper_band, lower_band=lower_band, signal=signal
    )
    return results


# --- Trading Logic ---
def analyze_and_trade_symbol(exchange: ccxt.Exchange, symbol: str, config: Dict[str, Any], logger: logging.Logger):
    """Performs a full trading cycle for a single symbol."""
    lg = logger
    lg.info(f"{Fore.MAGENTA}=== Starting Analysis Cycle for {symbol} ===")

    # --- 1. Fetch Market Info ---
    market_info = get_market_info(exchange, symbol, lg)
    if not market_info: lg.error(f"Cannot proceed ({symbol}): Failed market info."); return
    price_tick = market_info['price_precision_step_decimal']
    if not price_tick or price_tick <= 0: lg.error(f"Cannot proceed ({symbol}): Invalid price tick size."); return

    # --- 2. Fetch Kline Data ---
    timeframe_key = config.get("interval", "5"); ccxt_timeframe = CCXT_INTERVAL_MAP.get(timeframe_key)
    if not ccxt_timeframe: lg.error(f"Invalid interval '{timeframe_key}' ({symbol})."); return
    fetch_limit = config.get("fetch_limit", DEFAULT_FETCH_LIMIT)
    df_raw = fetch_klines_ccxt(exchange, symbol, ccxt_timeframe, fetch_limit, lg)
    if df_raw.empty: lg.error(f"Cannot proceed ({symbol}): Failed kline fetch."); return

    # --- 3. Calculate Strategy Signals ---
    strategy_results = calculate_strategy_signals(df_raw, config, lg)
    if strategy_results['last_close'] is None or pd.isna(strategy_results['last_close']): lg.error(f"Cannot proceed ({symbol}): Strategy calc failed."); return
    df_analyzed = strategy_results['dataframe']; last_close = strategy_results['last_close']
    current_trend_up = strategy_results['current_trend_up']; atr = strategy_results['atr']
    trade_signal = strategy_results['signal'] # Now comes from strategy
    lg.info(f"Analysis Results ({symbol}): Last Close={last_close.normalize()}, TrendUp={current_trend_up}, ATR={atr.normalize() if atr else 'N/A'}, Signal='{trade_signal}'")

    # --- 4. Check Existing Position ---
    position_info = get_open_position(exchange, symbol, lg)

    # --- 5. Manage Existing Position ---
    if position_info:
        pos_side = position_info['side']; pos_size = position_info['size_decimal']
        entry_price = _safe_market_decimal(position_info['entryPrice'], 'pos.entry', False)
        be_activated = position_info.get('be_activated', False) # Get bot's state flag
        tsl_activated = position_info.get('tsl_activated', False) # Get bot's state flag

        if not entry_price: lg.error(f"Cannot manage position ({symbol}): Invalid entry price."); return # Should not happen if position exists

        lg.info(f"{Fore.CYAN}# Managing existing {pos_side} position ({symbol})... BE Active: {be_activated}, TSL Active: {tsl_activated}{Style.RESET_ALL}")

        # Check for Exit Signal FIRST
        should_exit = (pos_side == 'long' and trade_signal == "EXIT_LONG") or \
                      (pos_side == 'short' and trade_signal == "EXIT_SHORT")

        if should_exit:
            lg.warning(f"{BRIGHT}>>> Strategy Exit Signal '{trade_signal}' detected for {pos_side} position on {symbol} <<<")
            if config.get("enable_trading", False):
                # Attempt to cancel existing SL/TP orders before market exit
                sl_order_id = position_info.get('info', {}).get('stopLossOrderId') # Example, actual field may vary
                tp_order_id = position_info.get('info', {}).get('takeProfitOrderId')
                if sl_order_id: cancel_order(exchange, sl_order_id, symbol, lg)
                if tp_order_id: cancel_order(exchange, tp_order_id, symbol, lg)
                time.sleep(1) # Brief pause after cancellation attempt

                # Place market exit order
                close_size = abs(pos_size)
                order_result = place_trade(exchange, symbol, trade_signal, close_size, market_info, lg, reduce_only=True)
                if order_result: lg.info(f"{NEON_GREEN}Position exit order placed successfully for {symbol}.{RESET}")
                else: lg.error(f"{NEON_RED}Failed to place position exit order for {symbol}. Position remains open.{RESET}")
            else: lg.warning(f"Trading disabled: Would place {pos_side} exit order for {symbol}.")
            return # Stop management cycle if exit signal triggered

        # --- Protection Management (BE, TSL) ---
        protection_conf = config.get('protection', {})
        enable_be = protection_conf.get('enable_break_even', False) and not be_activated # Only run if not already active
        enable_tsl = protection_conf.get('enable_trailing_stop', False) and not tsl_activated # Only run if not already active

        if (enable_be or enable_tsl) and atr is not None and atr > 0:
             current_price = fetch_current_price_ccxt(exchange, symbol, lg)
             if current_price is None: lg.warning(f"Could not fetch current price ({symbol}). Skipping BE/TSL checks.")
             else:
                 # --- Break-Even Logic ---
                 if enable_be and not tsl_activated: # Don't set BE if TSL is already active
                     be_trigger_mult = Decimal(str(protection_conf.get('break_even_trigger_atr_multiple', 1.0)))
                     be_offset_ticks = int(protection_conf.get('break_even_offset_ticks', 2))
                     profit_target_price: Optional[Decimal] = None
                     be_stop_price: Optional[Decimal] = None

                     if pos_side == 'long':
                         profit_target_price = entry_price + (atr * be_trigger_mult)
                         if current_price >= profit_target_price:
                             be_stop_price = entry_price + (price_tick * be_offset_ticks)
                             lg.info(f"BE Triggered (Long, {symbol}): Current={current_price}, Target={profit_target_price}")
                     elif pos_side == 'short':
                         profit_target_price = entry_price - (atr * be_trigger_mult)
                         if current_price <= profit_target_price:
                             be_stop_price = entry_price - (price_tick * be_offset_ticks)
                             lg.info(f"BE Triggered (Short, {symbol}): Current={current_price}, Target={profit_target_price}")

                     if be_stop_price is not None and be_stop_price > 0:
                         # Check if current SL is worse than BE price
                         current_sl_str = position_info.get('stopLossPrice')
                         current_sl = _safe_market_decimal(current_sl_str, 'current_sl', False) if current_sl_str else None
                         needs_update = True
                         if current_sl:
                              if pos_side == 'long' and current_sl >= be_stop_price: needs_update = False # Current SL already at or better than BE
                              if pos_side == 'short' and current_sl <= be_stop_price: needs_update = False # Current SL already at or better than BE
                         if needs_update:
                              lg.warning(f"{BRIGHT}>>> Moving SL to Break-Even for {symbol} at {be_stop_price.normalize()} <<<")
                              if config.get("enable_trading", False):
                                   protect_success = _set_position_protection(exchange, symbol, market_info, position_info, lg, stop_loss_price=be_stop_price)
                                   if protect_success: position_info['be_activated'] = True # Mark BE as done for this position instance
                                   else: lg.error(f"{NEON_RED}Failed to set Break-Even SL for {symbol}!{RESET}")
                              else: lg.warning(f"Trading disabled: Would set BE SL to {be_stop_price.normalize()} for {symbol}.")
                         else: lg.info(f"BE ({symbol}): Current SL ({current_sl.normalize() if current_sl else 'N/A'}) already at or better than calculated BE ({be_stop_price.normalize()}). No update needed.")
                     elif profit_target_price: lg.debug(f"BE not triggered ({symbol}): Price {current_price} hasn't reached target {profit_target_price.normalize()}.")

                 # --- Trailing Stop Loss Activation Logic ---
                 # We only *activate* it here. Bybit handles the trailing.
                 if enable_tsl and not position_info.get('be_activated'): # Check BE flag again, maybe it was just set
                     tsl_activation_perc = Decimal(str(protection_conf.get('trailing_stop_activation_percentage', 0.003)))
                     tsl_callback_rate = Decimal(str(protection_conf.get('trailing_stop_callback_rate', 0.005)))
                     activation_trigger_price: Optional[Decimal] = None
                     tsl_distance: Optional[Decimal] = None

                     if tsl_activation_perc >= 0 and tsl_callback_rate > 0:
                         if pos_side == 'long':
                             activation_trigger_price = entry_price * (Decimal('1') + tsl_activation_perc)
                             if current_price >= activation_trigger_price:
                                 tsl_distance = activation_trigger_price * tsl_callback_rate # Distance based on activation price
                                 lg.info(f"TSL Activation Triggered (Long, {symbol}): Current={current_price}, Target={activation_trigger_price}")
                         elif pos_side == 'short':
                             activation_trigger_price = entry_price * (Decimal('1') - tsl_activation_perc)
                             if current_price <= activation_trigger_price:
                                 tsl_distance = activation_trigger_price * tsl_callback_rate # Distance based on activation price
                                 lg.info(f"TSL Activation Triggered (Short, {symbol}): Current={current_price}, Target={activation_trigger_price}")

                         if tsl_distance is not None and tsl_distance > 0 and activation_trigger_price is not None:
                             lg.warning(f"{BRIGHT}>>> Activating Trailing Stop Loss for {symbol} | Distance: {tsl_distance.normalize()}, Activation: {activation_trigger_price.normalize()} <<<")
                             if config.get("enable_trading", False):
                                 # Set TSL using the dedicated function
                                 protect_success = _set_position_protection(
                                     exchange, symbol, market_info, position_info, lg,
                                     trailing_stop_distance=tsl_distance,
                                     tsl_activation_price=activation_trigger_price
                                 )
                                 if protect_success: position_info['tsl_activated'] = True # Mark TSL as active
                                 else: lg.error(f"{NEON_RED}Failed to activate Trailing Stop Loss for {symbol}!{RESET}")
                             else: lg.warning(f"Trading disabled: Would activate TSL for {symbol} (Dist: {tsl_distance.normalize()}, Act: {activation_trigger_price.normalize()}).")
                         elif activation_trigger_price: lg.debug(f"TSL not activated ({symbol}): Price {current_price} hasn't reached activation {activation_trigger_price.normalize()}.")
                     else: lg.warning(f"TSL skipped ({symbol}): Invalid activation percentage ({tsl_activation_perc}) or callback rate ({tsl_callback_rate}).")

        else: lg.debug(f"Skipping BE/TSL checks ({symbol}): Disabled, or ATR/Price unavailable.")

    # --- 6. Enter New Position ---
    elif trade_signal in ["BUY", "SELL"]:
        lg.info(f"{Fore.CYAN}# Evaluating potential {trade_signal} entry for {symbol}...{Style.RESET_ALL}")
        if not config.get("enable_trading", False): lg.warning(f"Trading disabled: Would evaluate {trade_signal} entry for {symbol}."); return
        if atr is None or atr <= 0: lg.error(f"Cannot enter ({symbol}): Invalid ATR ({atr})."); return

        protection_conf = config.get('protection', {}); sl_atr_mult = Decimal(str(protection_conf.get('initial_stop_loss_atr_multiple', 1.8))); tp_atr_mult = Decimal(str(protection_conf.get('initial_take_profit_atr_multiple', 0.7)))
        initial_sl_price: Optional[Decimal] = None; initial_tp_price: Optional[Decimal] = Decimal('0') # Default TP disabled
        if trade_signal == "BUY": initial_sl_price = last_close - (atr * sl_atr_mult); initial_tp_price = last_close + (atr * tp_atr_mult) if tp_atr_mult > 0 else Decimal('0')
        elif trade_signal == "SELL": initial_sl_price = last_close + (atr * sl_atr_mult); initial_tp_price = last_close - (atr * tp_atr_mult) if tp_atr_mult > 0 else Decimal('0')

        if initial_sl_price is None or initial_sl_price <= 0: lg.error(f"Cannot enter ({symbol}): Invalid SL price ({initial_sl_price})."); return
        if initial_tp_price < 0: lg.warning(f"Calculated TP ({initial_tp_price}) negative ({symbol}). Disabling TP."); initial_tp_price = Decimal('0')
        lg.info(f"Calculated Entry Protections ({symbol}): SL={initial_sl_price.normalize()}, TP={initial_tp_price.normalize() if initial_tp_price != 0 else 'Disabled'}")

        balance = fetch_balance(exchange, QUOTE_CURRENCY, lg)
        if balance is None or balance <= 0: lg.error(f"Cannot enter ({symbol}): Invalid balance."); return
        risk_per_trade = config.get("risk_per_trade", 0.01)
        position_size = calculate_position_size(balance, risk_per_trade, initial_sl_price, last_close, market_info, exchange, lg)
        if position_size is None or position_size <= 0: lg.error(f"Cannot enter ({symbol}): Position sizing failed."); return

        leverage = config.get("leverage", 0)
        if market_info.get('is_contract') and leverage > 0:
            if not set_leverage_ccxt(exchange, symbol, leverage, market_info, lg): lg.error(f"Cannot enter ({symbol}): Failed leverage set."); return

        lg.warning(f"{BRIGHT}>>> Initiating {trade_signal} entry for {symbol} | Size: {position_size.normalize()} <<<")
        order_result = place_trade(exchange, symbol, trade_signal, position_size, market_info, lg, reduce_only=False)
        if not order_result: lg.error(f"Entry order failed ({symbol}). No position opened."); return

        lg.info(f"Waiting {config.get('position_confirm_delay_seconds')}s to confirm position opening ({symbol})...")
        time.sleep(config.get('position_confirm_delay_seconds', POSITION_CONFIRM_DELAY_SECONDS))
        confirmed_position = None
        for confirm_attempt in range(MAX_API_RETRIES + 1):
             temp_pos = get_open_position(exchange, symbol, lg)
             if temp_pos:
                 expected_side = 'long' if trade_signal == "BUY" else 'short'
                 if temp_pos.get('side') == expected_side: lg.info(f"{NEON_GREEN}Position opening confirmed ({symbol} {expected_side}).{RESET}"); confirmed_position = temp_pos; break
                 else: lg.warning(f"Position found ({symbol}), but side ({temp_pos.get('side')}) != expected ({expected_side}). Retrying confirm..."); temp_pos = None
             if confirm_attempt < MAX_API_RETRIES: lg.warning(f"Position not confirmed ({symbol}, Attempt {confirm_attempt + 1}). Retrying in {RETRY_DELAY_SECONDS}s..."); time.sleep(RETRY_DELAY_SECONDS)
             else: lg.error(f"{NEON_RED}Failed to confirm position opening ({symbol}) after entry.{RESET}")

        if confirmed_position:
            lg.info(f"Setting initial protection (SL/TP) for new {symbol} position...")
            protect_success = _set_position_protection(exchange, symbol, market_info, confirmed_position, lg, stop_loss_price=initial_sl_price, take_profit_price=initial_tp_price)
            if protect_success: lg.info(f"Initial SL/TP set successfully for {symbol}.")
            else: lg.error(f"{NEON_RED}Failed to set initial SL/TP for {symbol}! Position unprotected.{RESET}")
        elif order_result: # Order placed but position not confirmed
             lg.error(f"{NEON_RED}CRITICAL: Entry order placed ({symbol}, ID: {order_result.get('id')}), but position confirmation failed. Manual check required!{RESET}")

    # --- 7. No Action ---
    elif not position_info: # Only log holding if no position exists
        lg.info(f"No open position and no entry signal for {symbol}. Holding pattern.")

    lg.info(f"{Fore.MAGENTA}=== Completed Analysis Cycle for {symbol} ===")


# --- Main Execution Loop ---
def signal_handler(sig, frame):
    """Handles shutdown signals."""
    global _shutdown_requested
    if not _shutdown_requested:
        print(f"\n{NEON_YELLOW}{Style.BRIGHT}Shutdown signal ({signal.Signals(sig).name}) received! Initiating graceful exit...{RESET}")
        _shutdown_requested = True
    else:
        print(f"{NEON_RED}Second shutdown signal received. Forcing exit.{RESET}")
        sys.exit(1)

def main():
    """Main execution function."""
    global CONFIG, _shutdown_requested
    main_logger = setup_logger("main")
    main_logger.info(f"{Fore.MAGENTA}{Style.BRIGHT}--- Pyrmethus Volumatic Bot v{BOT_VERSION} Initializing ---{Style.RESET_ALL}")

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler) # Termination signal

    exchange = initialize_exchange(main_logger)
    if not exchange: main_logger.critical("Exchange init failed. Shutting down."); sys.exit(1)

    trading_pairs = CONFIG.get("trading_pairs", [])
    valid_pairs: List[str] = []; all_symbols_valid = True
    main_logger.info(f"Validating configured trading pairs: {trading_pairs}")
    for pair_symbol in trading_pairs:
         market_info = get_market_info(exchange, pair_symbol, main_logger)
         if market_info and market_info.get('active'): valid_pairs.append(pair_symbol); main_logger.info(f" -> {NEON_GREEN}{pair_symbol} is valid.{RESET}")
         else: main_logger.error(f" -> {NEON_RED}{pair_symbol} invalid/inactive. Skipping.{RESET}"); all_symbols_valid = False
    if not valid_pairs: main_logger.critical("No valid trading pairs. Shutting down."); sys.exit(1)
    if not all_symbols_valid: main_logger.warning(f"Proceeding with valid pairs only: {valid_pairs}")

    main_logger.info(f"{Fore.CYAN}# Entering main trading cycle loop... Press Ctrl+C or send SIGTERM to gracefully exit.{Style.RESET_ALL}")
    while not _shutdown_requested:
        try:
            start_time = time.monotonic()
            main_logger.info(f"{Fore.YELLOW}--- New Trading Cycle ---{RESET}")
            # Optional: Reload config dynamically here if needed
            for symbol in valid_pairs:
                if _shutdown_requested: break # Check before processing next symbol
                symbol_logger = setup_logger(symbol)
                symbol_logger.info(f"--- Processing Symbol: {symbol} ---")
                try: analyze_and_trade_symbol(exchange, symbol, CONFIG, symbol_logger)
                except Exception as symbol_err: symbol_logger.error(f"{NEON_RED}!! Unhandled error during analysis ({symbol}): {symbol_err} !!{RESET}", exc_info=True); symbol_logger.error(f"Skipping cycle for {symbol}.")
                finally: symbol_logger.info(f"--- Finished Processing Symbol: {symbol} ---")
            if _shutdown_requested: break # Check after processing all symbols

            end_time = time.monotonic(); cycle_duration = end_time - start_time
            loop_delay = CONFIG.get("loop_delay_seconds", LOOP_DELAY_SECONDS)
            wait_time = max(0, loop_delay - cycle_duration)
            main_logger.info(f"Cycle duration: {cycle_duration:.2f}s. Waiting {wait_time:.2f}s...")
            # Sleep in smaller intervals to check shutdown flag more frequently
            for _ in range(int(wait_time)):
                 if _shutdown_requested: break
                 time.sleep(1)
            if not _shutdown_requested and wait_time % 1 > 0: time.sleep(wait_time % 1) # Sleep remainder

        except KeyboardInterrupt: # Should be caught by signal handler now, but keep as fallback
            if not _shutdown_requested: main_logger.warning(f"{NEON_YELLOW}{Style.BRIGHT}KeyboardInterrupt! Initiating graceful shutdown...{RESET}"); _shutdown_requested = True
        except Exception as loop_err:
            main_logger.critical(f"{NEON_RED}!! Unhandled critical error in main loop: {loop_err} !!{RESET}", exc_info=True)
            if _shutdown_requested: break # Don't pause if already shutting down
            main_logger.warning("Pausing loop for 60s due to critical error...")
            time.sleep(60)

    main_logger.info(f"{Fore.MAGENTA}{Style.BRIGHT}--- Pyrmethus Volumatic Bot Shutting Down ---{Style.RESET_ALL}")
    # Optional: Add cleanup logic here (e.g., close open orders if configured)
    main_logger.info("Shutdown complete. The ether settles.")

if __name__ == "__main__":
    main()

```python
# pyrmethus_volumatic_bot.py
# Enhanced trading bot incorporating the Volumatic Trend and Pivot Order Block strategy
# with advanced position management (SL/TP, BE, TSL) for Bybit V5 (Linear/Inverse).
# Version 1.1.7: Comprehensive enhancements based on v1.1.6 review.
#               Improved docstrings, type hinting (TypedDict), error handling,
#               Decimal usage, API interaction robustness, config validation,
#               logging clarity, overall code structure, and completed main loop.

"""
Pyrmethus Volumatic Bot: A Python Trading Bot for Bybit V5

This bot implements a trading strategy based on the combination of:
1.  **Volumatic Trend:** An EMA/SWMA crossover system with ATR-based bands,
    incorporating normalized volume analysis.
2.  **Pivot Order Blocks (OBs):** Identifying potential support/resistance zones
    based on pivot highs and lows derived from candle wicks or bodies.

Key Features:
-   Connects to Bybit V5 API (Linear/Inverse contracts, Spot potentially adaptable).
-   Supports Sandbox (testnet) and Live trading environments.
-   Fetches OHLCV data and calculates strategy indicators using pandas and pandas-ta.
-   Identifies Volumatic Trend direction and changes.
-   Detects Pivot Highs/Lows and creates/manages Order Blocks.
-   Generates BUY/SELL/EXIT signals based on trend alignment and OB proximity.
-   Calculates position size based on risk percentage and stop-loss distance.
-   Sets leverage for contract markets.
-   Places market orders to enter and exit positions.
-   Advanced Position Management:
    -   Sets initial Stop Loss (SL) and Take Profit (TP) based on ATR multiples.
    -   Implements Trailing Stop Loss (TSL) with configurable activation and callback.
    -   Implements Break-Even (BE) stop adjustment based on profit targets.
-   Robust API interaction with retries and error handling (Network, Rate Limit, Auth).
-   Secure handling of API credentials via `.env` file.
-   Flexible configuration via `config.json` with validation and defaults.
-   Detailed logging with Neon color scheme for console output and rotating file logs.
-   Sensitive data redaction in logs.
-   Graceful shutdown handling.
-   Multi-symbol trading capability (processes symbols sequentially within the main loop).
"""

# --- Core Libraries ---
import hashlib
import hmac
import json
import logging
import math
import os
import sys
import time
from datetime import datetime
from decimal import Decimal, ROUND_DOWN, ROUND_UP, getcontext, InvalidOperation
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional, Tuple, TypedDict, Union
from zoneinfo import ZoneInfo # Requires tzdata package (pip install tzdata)

# --- Dependencies (Install via pip) ---
import numpy as np # Requires numpy (pip install numpy)
import pandas as pd # Requires pandas (pip install pandas)
import pandas_ta as ta # Requires pandas_ta (pip install pandas_ta)
import requests # Requires requests (pip install requests)
import ccxt # Requires ccxt (pip install ccxt)
from colorama import Fore, Style, init as colorama_init # Requires colorama (pip install colorama)
from dotenv import load_dotenv # Requires python-dotenv (pip install python-dotenv)

# --- Initialize Environment and Settings ---
getcontext().prec = 28 # Set Decimal precision globally for high-accuracy calculations
colorama_init(autoreset=True) # Initialize Colorama for console colors, resetting after each print
load_dotenv() # Load environment variables from a .env file in the project root

# --- Constants ---
# API Credentials (Loaded securely from .env file)
API_KEY: Optional[str] = os.getenv("BYBIT_API_KEY")
API_SECRET: Optional[str] = os.getenv("BYBIT_API_SECRET")
if not API_KEY or not API_SECRET:
    # Critical error if API keys are missing
    raise ValueError("BYBIT_API_KEY and BYBIT_API_SECRET must be set in the .env file")

# Configuration and Logging Files/Directories
CONFIG_FILE: str = "config.json"
LOG_DIRECTORY: str = "bot_logs"
TIMEZONE_STR: str = os.getenv("TIMEZONE", "America/Chicago") # Default timezone if not set in .env
try:
    # Attempt to load user-specified timezone, fallback to UTC if tzdata is not installed or invalid
    # Example: "America/Chicago", "Europe/London", "Asia/Tokyo", "UTC"
    TIMEZONE = ZoneInfo(TIMEZONE_STR)
except Exception as tz_err:
    print(f"{Fore.RED}Failed to initialize timezone '{TIMEZONE_STR}'. Error: {tz_err}. "
          f"Install 'tzdata' package (`pip install tzdata`) or check timezone name. Using UTC fallback.{Style.RESET_ALL}")
    TIMEZONE = ZoneInfo("UTC")
    TIMEZONE_STR = "UTC" # Update string to reflect fallback

# API Interaction Settings
MAX_API_RETRIES: int = 3        # Maximum number of consecutive retries for failed API calls
RETRY_DELAY_SECONDS: int = 5    # Base delay (in seconds) between API retries (may increase exponentially)
POSITION_CONFIRM_DELAY_SECONDS: int = 8 # Wait time after placing an order before fetching position details
LOOP_DELAY_SECONDS: int = 15    # Default delay between trading cycles (can be overridden in config.json)
BYBIT_API_KLINE_LIMIT: int = 1000 # Maximum number of Klines Bybit V5 API returns per request

# Timeframes Mapping
# Bybit API expects specific strings for intervals
VALID_INTERVALS: List[str] = ["1", "3", "5", "15", "30", "60", "120", "240", "D", "W", "M"]
CCXT_INTERVAL_MAP: Dict[str, str] = {
    "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
    "60": "1h", "120": "2h", "240": "4h", "D": "1d", "W": "1w", "M": "1M"
}

# Data Handling Limits
DEFAULT_FETCH_LIMIT: int = 750 # Default number of klines to fetch if not specified or less than strategy needs
MAX_DF_LEN: int = 2000         # Internal limit to prevent excessive memory usage by the Pandas DataFrame

# Strategy Defaults (Used if values are missing, invalid, or out of range in config.json)
DEFAULT_VT_LENGTH: int = 40             # Volumatic Trend EMA/SWMA length
DEFAULT_VT_ATR_PERIOD: int = 200        # ATR period for Volumatic Trend bands
DEFAULT_VT_VOL_EMA_LENGTH: int = 950    # Volume Normalization EMA length (Adjusted: 1000 often > API limit)
DEFAULT_VT_ATR_MULTIPLIER: float = 3.0  # ATR multiplier for Volumatic Trend bands
DEFAULT_VT_STEP_ATR_MULTIPLIER: float = 4.0 # Currently unused step ATR multiplier
DEFAULT_OB_SOURCE: str = "Wicks"        # Order Block source ("Wicks" or "Body")
DEFAULT_PH_LEFT: int = 10               # Pivot High lookback periods (left)
DEFAULT_PH_RIGHT: int = 10              # Pivot High lookback periods (right)
DEFAULT_PL_LEFT: int = 10               # Pivot Low lookback periods (left)
DEFAULT_PL_RIGHT: int = 10              # Pivot Low lookback periods (right)
DEFAULT_OB_EXTEND: bool = True          # Extend Order Block visuals to the latest candle
DEFAULT_OB_MAX_BOXES: int = 50          # Max number of active Order Blocks to track/display

# Dynamically loaded from config: QUOTE_CURRENCY (e.g., "USDT")
QUOTE_CURRENCY: str = "USDT" # Placeholder, will be updated by load_config()

# Logging Colors (Neon Theme for Console Output)
NEON_GREEN: str = Fore.LIGHTGREEN_EX
NEON_BLUE: str = Fore.CYAN
NEON_PURPLE: str = Fore.MAGENTA
NEON_YELLOW: str = Fore.YELLOW
NEON_RED: str = Fore.LIGHTRED_EX
NEON_CYAN: str = Fore.CYAN
RESET: str = Style.RESET_ALL
BRIGHT: str = Style.BRIGHT
DIM: str = Style.DIM

# Ensure log directory exists before setting up loggers
os.makedirs(LOG_DIRECTORY, exist_ok=True)

# --- Type Definitions for Structured Data ---
class OrderBlock(TypedDict):
    """Represents a bullish or bearish Order Block identified on the chart."""
    id: str                 # Unique identifier (e.g., "B_231026143000")
    type: str               # 'bull' or 'bear'
    left_idx: pd.Timestamp  # Timestamp of the candle that formed the OB
    right_idx: pd.Timestamp # Timestamp of the last candle the OB extends to (or violation candle)
    top: Decimal            # Top price level of the OB
    bottom: Decimal         # Bottom price level of the OB
    active: bool            # True if the OB is currently considered valid
    violated: bool          # True if the price has closed beyond the OB boundary

class StrategyAnalysisResults(TypedDict):
    """Structured results from the strategy analysis process."""
    dataframe: pd.DataFrame             # The DataFrame with all calculated indicators (Decimal values)
    last_close: Decimal                 # The closing price of the most recent candle
    current_trend_up: Optional[bool]    # True if Volumatic Trend is up, False if down, None if undetermined
    trend_just_changed: bool            # True if the trend flipped on the last candle
    active_bull_boxes: List[OrderBlock] # List of currently active bullish OBs
    active_bear_boxes: List[OrderBlock] # List of currently active bearish OBs
    vol_norm_int: Optional[int]         # Normalized volume indicator (0-100+, integer) for the last candle
    atr: Optional[Decimal]              # ATR value for the last candle (must be positive)
    upper_band: Optional[Decimal]       # Volumatic Trend upper band value for the last candle
    lower_band: Optional[Decimal]       # Volumatic Trend lower band value for the last candle

class MarketInfo(TypedDict):
    """Standardized market information dictionary derived from ccxt.market."""
    # Standard CCXT fields (may vary slightly by exchange)
    id: str                     # Exchange-specific market ID (e.g., 'BTCUSDT')
    symbol: str                 # Standardized symbol (e.g., 'BTC/USDT')
    base: str                   # Base currency code (e.g., 'BTC')
    quote: str                  # Quote currency code (e.g., 'USDT')
    settle: Optional[str]       # Settlement currency (usually quote for linear, base for inverse)
    baseId: str                 # Exchange-specific base ID
    quoteId: str                # Exchange-specific quote ID
    settleId: Optional[str]     # Exchange-specific settle ID
    type: str                   # 'spot', 'swap', 'future', etc.
    spot: bool
    margin: bool
    swap: bool
    future: bool
    option: bool
    active: bool                # Whether the market is currently active/tradable
    contract: bool              # True if it's a derivative contract (swap, future)
    linear: bool                # True if linear contract
    inverse: bool               # True if inverse contract
    quanto: bool                # True if quanto contract
    taker: float                # Taker fee rate
    maker: float                # Maker fee rate
    contractSize: Optional[Any] # Size of one contract (often float or int, convert to Decimal)
    expiry: Optional[int]       # Unix timestamp of expiry (milliseconds)
    expiryDatetime: Optional[str]# ISO8601 datetime string of expiry
    strike: Optional[float]     # Option strike price
    optionType: Optional[str]   # 'call' or 'put'
    precision: Dict[str, Any]   # {'amount': float/str, 'price': float/str, 'cost': float/str, 'base': float, 'quote': float} - Convert to Decimal steps
    limits: Dict[str, Any]      # {'leverage': {'min': float, 'max': float}, 'amount': {'min': float/str, 'max': float/str}, 'price': {'min': float, 'max': float}, 'cost': {'min': float/str, 'max': float/str}} - Convert to Decimal limits
    info: Dict[str, Any]        # Exchange-specific raw market info
    # Custom added fields for convenience
    is_contract: bool           # More reliable check for derivatives
    is_linear: bool             # True only if linear contract
    is_inverse: bool            # True only if inverse contract
    contract_type_str: str      # "Linear", "Inverse", "Spot", or "Unknown"
    min_amount_decimal: Optional[Decimal] # Parsed minimum order size (in base units or contracts)
    max_amount_decimal: Optional[Decimal] # Parsed maximum order size
    min_cost_decimal: Optional[Decimal]   # Parsed minimum order cost (in quote currency)
    max_cost_decimal: Optional[Decimal]   # Parsed maximum order cost
    amount_precision_step_decimal: Optional[Decimal] # Parsed step size for amount (e.g., 0.001)
    price_precision_step_decimal: Optional[Decimal]  # Parsed step size for price (e.g., 0.01)
    contract_size_decimal: Decimal  # Parsed contract size as Decimal (defaults to 1 if not applicable/found)

class PositionInfo(TypedDict):
    """Standardized position information dictionary derived from ccxt.position."""
    # Standard CCXT fields (availability varies by exchange)
    id: Optional[str]           # Position ID (often None or same as symbol)
    symbol: str                 # Standardized symbol (e.g., 'BTC/USDT')
    timestamp: Optional[int]    # Creation timestamp (milliseconds)
    datetime: Optional[str]     # ISO8601 creation datetime string
    contracts: Optional[float]  # Deprecated/inconsistent, use size_decimal instead
    contractSize: Optional[Any] # Size of one contract for this position (convert to Decimal)
    side: Optional[str]         # 'long' or 'short'
    notional: Optional[Any]     # Position value in quote currency (convert to Decimal)
    leverage: Optional[Any]     # Leverage used for this position (convert to Decimal)
    unrealizedPnl: Optional[Any]# Unrealized Profit/Loss (convert to Decimal)
    realizedPnl: Optional[Any]  # Realized Profit/Loss (convert to Decimal)
    collateral: Optional[Any]   # Collateral used (convert to Decimal)
    entryPrice: Optional[Any]   # Average entry price (convert to Decimal)
    markPrice: Optional[Any]    # Current mark price (convert to Decimal)
    liquidationPrice: Optional[Any] # Estimated liquidation price (convert to Decimal)
    marginMode: Optional[str]   # 'cross' or 'isolated'
    hedged: Optional[bool]      # Whether the position is part of a hedge
    maintenanceMargin: Optional[Any] # Maintenance margin required (convert to Decimal)
    maintenanceMarginPercentage: Optional[float] # Maintenance margin rate
    initialMargin: Optional[Any]# Initial margin used (convert to Decimal)
    initialMarginPercentage: Optional[float] # Initial margin rate
    marginRatio: Optional[float]# Margin ratio (maintenance / collateral)
    lastUpdateTimestamp: Optional[int] # Timestamp of last update (milliseconds)
    info: Dict[str, Any]        # Exchange-specific raw position info (crucial for Bybit V5 details)
    # Custom added/parsed fields
    size_decimal: Decimal       # Parsed position size as Decimal (positive for long, negative for short)
    stopLossPrice: Optional[str]# Parsed SL price from info (string format from Bybit)
    takeProfitPrice: Optional[str]# Parsed TP price from info (string format from Bybit)
    trailingStopLoss: Optional[str]# Parsed TSL distance from info (string format from Bybit)
    tslActivationPrice: Optional[str]# Parsed TSL activation price from info (string format from Bybit)


# --- Configuration Loading & Validation ---
class SensitiveFormatter(logging.Formatter):
    """
    Custom logging formatter that redacts sensitive API keys/secrets
    from log messages to prevent accidental exposure in log files or console.
    """
    def format(self, record: logging.LogRecord) -> str:
        """Formats the log record, replacing API keys/secrets with placeholders."""
        msg = super().format(record)
        # Ensure API keys exist and are strings before attempting replacement
        if API_KEY and isinstance(API_KEY, str):
            msg = msg.replace(API_KEY, "***API_KEY***")
        if API_SECRET and isinstance(API_SECRET, str):
            msg = msg.replace(API_SECRET, "***API_SECRET***")
        return msg

def setup_logger(name: str) -> logging.Logger:
    """
    Sets up a dedicated logger instance for a specific context (e.g., 'init', 'BTC/USDT').

    Configures both a console handler (with Neon colors, level filtering based on
    CONSOLE_LOG_LEVEL environment variable, and timezone-aware timestamps)
    and a rotating file handler (capturing DEBUG level and above, with sensitive
    data redaction).

    Args:
        name (str): The name for the logger (e.g., "init", "BTC/USDT"). Used for filtering
                    and naming the log file.

    Returns:
        logging.Logger: The configured logging.Logger instance. Returns existing instance if already configured.
    """
    safe_name = name.replace('/', '_').replace(':', '-') # Sanitize name for filenames/logger keys
    logger_name = f"pyrmethus_bot_{safe_name}"
    log_filename = os.path.join(LOG_DIRECTORY, f"{logger_name}.log")
    logger = logging.getLogger(logger_name)

    # Avoid adding handlers multiple times if logger instance already exists
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.DEBUG) # Capture all levels; handlers below will filter output

    # --- File Handler (DEBUG level, Rotating, Redaction) ---
    try:
        # Rotate log file when it reaches 10MB, keep 5 backup files
        fh = RotatingFileHandler(log_filename, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        # Use SensitiveFormatter for detailed file log, redacting API keys/secrets
        ff = SensitiveFormatter(
            "%(asctime)s - %(levelname)-8s - [%(name)s:%(lineno)d] - %(message)s",
            datefmt='%Y-%m-%d %H:%M:%S' # Standard date format for files
        )
        fh.setFormatter(ff)
        fh.setLevel(logging.DEBUG) # Log everything from DEBUG upwards to the file
        logger.addHandler(fh)
    except Exception as e:
        # Use print for errors during logger setup itself, as logger might not be functional
        print(f"{NEON_RED}Error setting up file logger '{log_filename}': {e}{RESET}")

    # --- Console Handler (Configurable Level, Neon Colors, Timezone) ---
    try:
        sh = logging.StreamHandler(sys.stdout) # Explicitly use stdout
        # Define color mapping for different log levels
        level_colors = {
            logging.DEBUG: NEON_CYAN + DIM,      # Dim Cyan for Debug
            logging.INFO: NEON_BLUE,             # Bright Cyan for Info
            logging.WARNING: NEON_YELLOW,        # Bright Yellow for Warning
            logging.ERROR: NEON_RED,             # Bright Red for Error
            logging.CRITICAL: NEON_RED + BRIGHT, # Bright Red + Bold for Critical
        }

        # Custom formatter for console output with colors and timezone-aware timestamps
        class NeonConsoleFormatter(SensitiveFormatter):
            """Applies Neon color scheme and configured timezone to console log messages."""
            def format(self, record: logging.LogRecord) -> str:
                level_color = level_colors.get(record.levelno, NEON_BLUE) # Default to Info color
                # Format: Time(TZ) - Level - [LoggerName] - Message
                log_fmt = (
                    f"{NEON_BLUE}%(asctime)s{RESET} - "
                    f"{level_color}%(levelname)-8s{RESET} - "
                    f"{NEON_PURPLE}[%(name)s]{RESET} - "
                    f"%(message)s"
                )
                # Create a formatter instance with the defined format and date style
                formatter = logging.Formatter(log_fmt, datefmt='%H:%M:%S') # Use Time only for console clarity
                # Ensure timestamps reflect the configured TIMEZONE
                formatter.converter = lambda *args: datetime.now(TIMEZONE).timetuple()
                # Apply sensitive data redaction before returning the final message
                # We inherit from SensitiveFormatter, so super().format handles redaction
                return super(NeonConsoleFormatter, self).format(record) # Explicitly call super()

        sh.setFormatter(NeonConsoleFormatter())
        # Get desired console log level from environment variable (e.g., DEBUG, INFO, WARNING), default to INFO
        log_level_str = os.getenv("CONSOLE_LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO) # Fallback to INFO if invalid level provided
        sh.setLevel(log_level)
        logger.addHandler(sh)
    except Exception as e:
        print(f"{NEON_RED}Error setting up console logger: {e}{RESET}")

    logger.propagate = False # Prevent log messages from bubbling up to the root logger
    return logger

# Initialize the 'init' logger early for messages during startup and configuration loading
init_logger = setup_logger("init")

def _ensure_config_keys(config: Dict[str, Any], default_config: Dict[str, Any], parent_key: str = "") -> Tuple[Dict[str, Any], bool]:
    """
    Recursively checks if all keys from `default_config` exist in `config`.
    If a key is missing, it's added to `config` with the default value from `default_config`.
    Logs any keys that were added using the `init_logger`.

    Args:
        config (Dict[str, Any]): The configuration dictionary loaded from the file.
        default_config (Dict[str, Any]): The dictionary containing default structure and values.
        parent_key (str): Used internally for tracking nested key paths for logging (e.g., "strategy_params.vt_length").

    Returns:
        Tuple[Dict[str, Any], bool]: A tuple containing:
            - The potentially updated configuration dictionary.
            - A boolean indicating whether any changes were made (True if keys were added).
    """
    updated_config = config.copy()
    changed = False
    for key, default_value in default_config.items():
        full_key_path = f"{parent_key}.{key}" if parent_key else key
        if key not in updated_config:
            # Key is missing, add it with the default value
            updated_config[key] = default_value
            changed = True
            init_logger.info(f"{NEON_YELLOW}Config: Added missing key '{full_key_path}' with default value: {repr(default_value)}{RESET}")
        elif isinstance(default_value, dict) and isinstance(updated_config.get(key), dict):
            # If both default and loaded values are dicts, recurse into nested dict
            nested_config, nested_changed = _ensure_config_keys(updated_config[key], default_value, full_key_path)
            if nested_changed:
                # If nested dict was changed, update the parent dict and mark as changed
                updated_config[key] = nested_config
                changed = True
        # Optional: Could add type mismatch check here, but validation below handles it more robustly.
    return updated_config, changed

def load_config(filepath: str) -> Dict[str, Any]:
    """
    Loads, validates, and potentially updates configuration from a JSON file.

    Steps:
    1. Checks if the config file exists. If not, creates a default one.
    2. Loads the JSON data from the file. Handles decoding errors by recreating the default file.
    3. Ensures all keys from the default structure exist in the loaded config, adding missing ones.
    4. Performs detailed type and range validation on critical numeric and string parameters.
       - Uses default values and logs warnings/corrections if validation fails.
       - Leverages Decimal for robust numeric comparisons.
    5. Validates the `trading_pairs` list.
    6. If any keys were added or values corrected, saves the updated config back to the file.
    7. Updates the global `QUOTE_CURRENCY` based on the validated config.
    8. Returns the validated (and potentially updated) configuration dictionary.

    Args:
        filepath (str): The path to the configuration JSON file (e.g., "config.json").

    Returns:
        Dict[str, Any]: The loaded and validated configuration dictionary. Returns default configuration
                        if the file cannot be read, created, or parsed, or if validation encounters
                        unexpected errors. Returns the internal default if file recreation fails.
    """
    # Define the default configuration structure and values
    default_config = {
        # General Settings
        "trading_pairs": ["BTC/USDT"],  # List of symbols to trade (e.g., ["BTC/USDT", "ETH/USDT"])
        "interval": "5",                # Default timeframe (e.g., "5" for 5 minutes)
        "retry_delay": RETRY_DELAY_SECONDS, # Base delay for API retries
        "fetch_limit": DEFAULT_FETCH_LIMIT, # Default klines to fetch per cycle
        "orderbook_limit": 25,          # (Currently Unused) Limit for order book fetching if implemented
        "enable_trading": False,        # Master switch for placing actual trades
        "use_sandbox": True,            # Use Bybit's testnet environment
        "risk_per_trade": 0.01,         # Fraction of balance to risk per trade (e.g., 0.01 = 1%)
        "leverage": 20,                 # Default leverage for contract trading (0 to disable setting)
        "max_concurrent_positions": 1,  # (Currently Unused) Max open positions allowed simultaneously
        "quote_currency": "USDT",       # The currency to calculate balance and risk against
        "loop_delay_seconds": LOOP_DELAY_SECONDS, # Delay between trading cycles
        "position_confirm_delay_seconds": POSITION_CONFIRM_DELAY_SECONDS, # Wait after order before checking position

        # Strategy Parameters (Volumatic Trend + OB)
        "strategy_params": {
            "vt_length": DEFAULT_VT_LENGTH,
            "vt_atr_period": DEFAULT_VT_ATR_PERIOD,
            "vt_vol_ema_length": DEFAULT_VT_VOL_EMA_LENGTH,
            "vt_atr_multiplier": float(DEFAULT_VT_ATR_MULTIPLIER), # Store as float in JSON
            "vt_step_atr_multiplier": float(DEFAULT_VT_STEP_ATR_MULTIPLIER), # Unused, store as float
            "ob_source": DEFAULT_OB_SOURCE, # "Wicks" or "Body"
            "ph_left": DEFAULT_PH_LEFT, "ph_right": DEFAULT_PH_RIGHT, # Pivot High lookbacks
            "pl_left": DEFAULT_PL_LEFT, "pl_right": DEFAULT_PL_RIGHT, # Pivot Low lookbacks
            "ob_extend": DEFAULT_OB_EXTEND,
            "ob_max_boxes": DEFAULT_OB_MAX_BOXES,
            "ob_entry_proximity_factor": 1.005, # Price must be <= OB top * factor (long) or >= OB bottom / factor (short)
            "ob_exit_proximity_factor": 1.001   # Exit if price >= Bear OB top / factor or <= Bull OB bottom * factor
        },
        # Position Protection Parameters
        "protection": {
             "enable_trailing_stop": True,      # Use trailing stop loss
             "trailing_stop_callback_rate": 0.005, # TSL distance as % of activation price (e.g., 0.005 = 0.5%)
             "trailing_stop_activation_percentage": 0.003, # Activate TSL when price moves this % from entry (e.g., 0.003 = 0.3%)
             "enable_break_even": True,         # Move SL to entry + offset when profit target hit
             "break_even_trigger_atr_multiple": 1.0, # Profit needed (in ATR multiples) to trigger BE
             "break_even_offset_ticks": 2,       # Move SL this many ticks beyond entry for BE
             "initial_stop_loss_atr_multiple": 1.8, # Initial SL distance in ATR multiples
             "initial_take_profit_atr_multiple": 0.7 # Initial TP distance in ATR multiples (0 to disable)
        }
    }
    config_needs_saving: bool = False
    loaded_config: Dict[str, Any] = {}

    # --- File Existence Check & Default Creation ---
    if not os.path.exists(filepath):
        init_logger.warning(f"{NEON_YELLOW}Config file '{filepath}' not found. Creating default config.{RESET}")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            init_logger.info(f"{NEON_GREEN}Created default config file: {filepath}{RESET}")
            # Update global QUOTE_CURRENCY immediately after creating default
            global QUOTE_CURRENCY
            QUOTE_CURRENCY = default_config.get("quote_currency", "USDT")
            return default_config # Return defaults immediately
        except IOError as e:
            init_logger.error(f"{NEON_RED}FATAL: Error creating default config file '{filepath}': {e}{RESET}")
            init_logger.warning("Using internal default configuration values. Bot may not function correctly.")
            QUOTE_CURRENCY = default_config.get("quote_currency", "USDT")
            return default_config # Use internal defaults if file creation fails

    # --- File Loading ---
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            loaded_config = json.load(f)
        if not isinstance(loaded_config, dict):
             raise TypeError("Configuration file does not contain a valid JSON object.")
    except json.JSONDecodeError as e:
        init_logger.error(f"{NEON_RED}Error decoding JSON from '{filepath}': {e}. Recreating default file.{RESET}")
        try: # Attempt to recreate the file with defaults if corrupted
            with open(filepath, "w", encoding="utf-8") as f_create:
                json.dump(default_config, f_create, indent=4, ensure_ascii=False)
            init_logger.info(f"{NEON_GREEN}Recreated default config file due to decode error: {filepath}{RESET}")
            QUOTE_CURRENCY = default_config.get("quote_currency", "USDT")
            return default_config
        except IOError as e_create:
            init_logger.error(f"{NEON_RED}FATAL: Error recreating default config file after decode error: {e_create}. Using internal defaults.{RESET}")
            QUOTE_CURRENCY = default_config.get("quote_currency", "USDT")
            return default_config
    except Exception as e:
        init_logger.error(f"{NEON_RED}FATAL: Unexpected error loading config file '{filepath}': {e}{RESET}", exc_info=True)
        init_logger.warning("Using internal default configuration values. Bot may not function correctly.")
        QUOTE_CURRENCY = default_config.get("quote_currency", "USDT")
        return default_config

    # --- Validation and Merging ---
    try:
        # Ensure all keys from default_config exist in loaded_config
        updated_config, added_keys = _ensure_config_keys(loaded_config, default_config)
        if added_keys:
            config_needs_saving = True # Mark for saving if keys were added

        # --- Type and Range Validation Helper ---
        def validate_numeric(cfg: Dict, key_path: str, min_val: Union[int, float, Decimal], max_val: Union[int, float, Decimal],
                             is_strict_min: bool = False, is_int: bool = False, allow_zero: bool = False) -> bool:
            """
            Validates a numeric config value at `key_path` (e.g., "protection.leverage").

            Checks type (int/float), range [min_val, max_val] or (min_val, max_val] if strict.
            Uses the default value from `default_config` and logs a warning/info if correction needed.
            Updates the `cfg` dictionary in place if correction is made.
            Uses Decimal for robust comparisons.

            Args:
                cfg (Dict): The config dictionary being validated (updated in place).
                key_path (str): The dot-separated path to the key (e.g., "protection.leverage").
                min_val (Union[int, float, Decimal]): Minimum allowed value (inclusive unless is_strict_min).
                max_val (Union[int, float, Decimal]): Maximum allowed value (inclusive).
                is_strict_min (bool): If True, value must be strictly greater than min_val.
                is_int (bool): If True, value must be an integer.
                allow_zero (bool): If True, zero is allowed even if outside min/max range.

            Returns:
                bool: True if a correction was made, False otherwise.
            """
            nonlocal config_needs_saving # Allow modification of the outer scope variable
            keys = key_path.split('.')
            current_level = cfg
            default_level = default_config
            try:
                # Traverse nested dictionaries to reach the target key
                for key in keys[:-1]:
                    current_level = current_level[key]
                    default_level = default_level[key]
                leaf_key = keys[-1]
                original_val = current_level.get(leaf_key)
                default_val = default_level.get(leaf_key)
            except (KeyError, TypeError):
                init_logger.error(f"Config validation error: Invalid path '{key_path}'. Cannot validate.")
                return False # Path itself is wrong

            if original_val is None:
                # This case should be rare due to _ensure_config_keys, but handle defensively
                init_logger.warning(f"Config validation: Key missing at '{key_path}' during numeric check. Using default: {repr(default_val)}")
                current_level[leaf_key] = default_val
                config_needs_saving = True
                return True

            corrected = False
            final_val = original_val # Start with the original value

            try:
                # Convert to Decimal for robust comparison, handle potential strings
                num_val = Decimal(str(original_val))
                min_dec = Decimal(str(min_val))
                max_dec = Decimal(str(max_val))

                # Check range
                min_check = num_val > min_dec if is_strict_min else num_val >= min_dec
                range_check = min_check and num_val <= max_dec
                # Check if zero is allowed and value is zero, bypassing range check if so
                zero_ok = allow_zero and num_val == Decimal(0)

                if not range_check and not zero_ok:
                    raise ValueError("Value out of allowed range.")

                # Check type and convert if necessary
                target_type = int if is_int else float
                # Attempt conversion to target type
                converted_val = target_type(num_val)

                # Check if type or value changed significantly after conversion
                # This ensures int remains int, float remains float (within tolerance)
                needs_correction = False
                if isinstance(original_val, bool): # Don't try to convert bools here
                     raise TypeError("Boolean value found where numeric expected.")
                elif is_int and not isinstance(original_val, int):
                    needs_correction = True
                elif not is_int and not isinstance(original_val, float):
                     # If float expected, allow int input but convert it
                    if isinstance(original_val, int):
                        converted_val = float(original_val) # Explicitly convert int to float
                        needs_correction = True
                    else: # Input is neither float nor int (e.g., string)
                        needs_correction = True
                elif isinstance(original_val, float) and abs(original_val - converted_val) > 1e-9:
                    # Check if float value changed significantly after potential Decimal conversion
                    needs_correction = True
                elif isinstance(original_val, int) and original_val != converted_val:
                     # Should not happen if is_int=True, but check defensively
                     needs_correction = True

                if needs_correction:
                    init_logger.info(f"{NEON_YELLOW}Config: Corrected type/value for '{key_path}' from {repr(original_val)} to {repr(converted_val)}.{RESET}")
                    final_val = converted_val
                    corrected = True

            except (ValueError, InvalidOperation, TypeError) as e:
                # Handle cases where value is non-numeric, out of range, or conversion fails
                range_str = f"{'(' if is_strict_min else '['}{min_val}, {max_val}{']'}"
                if allow_zero: range_str += " or 0"
                init_logger.warning(f"{NEON_YELLOW}Config '{key_path}': Invalid value '{repr(original_val)}'. Using default: {repr(default_val)}. Error: {e}. Expected type: {'int' if is_int else 'float'}, Range: {range_str}{RESET}")
                final_val = default_val # Use the default value
                corrected = True

            # If a correction occurred, update the config dictionary and mark for saving
            if corrected:
                current_level[leaf_key] = final_val
                config_needs_saving = True
            return corrected

        # --- Apply Validations to Specific Config Keys ---
        # General
        if not isinstance(updated_config.get("trading_pairs"), list) or \
           not all(isinstance(s, str) and s for s in updated_config.get("trading_pairs", [])):
            init_logger.warning(f"{NEON_YELLOW}Invalid config 'trading_pairs' value '{updated_config.get('trading_pairs')}'. Must be a non-empty list of non-empty strings. Using default {default_config['trading_pairs']}.{RESET}")
            updated_config["trading_pairs"] = default_config["trading_pairs"]
            config_needs_saving = True
        if updated_config.get("interval") not in VALID_INTERVALS:
            init_logger.warning(f"{NEON_YELLOW}Invalid config 'interval' '{updated_config.get('interval')}'. Valid: {VALID_INTERVALS}. Using default '{default_config['interval']}'.{RESET}")
            updated_config["interval"] = default_config["interval"]
            config_needs_saving = True
        validate_numeric(updated_config, "retry_delay", 1, 60, is_int=True)
        validate_numeric(updated_config, "fetch_limit", 50, MAX_DF_LEN, is_int=True) # Ensure minimum useful fetch limit
        validate_numeric(updated_config, "risk_per_trade", Decimal('0'), Decimal('1'), is_strict_min=True) # Risk must be > 0 and <= 1
        validate_numeric(updated_config, "leverage", 0, 200, is_int=True, allow_zero=True) # Leverage 0 means no setting attempt
        validate_numeric(updated_config, "loop_delay_seconds", 1, 3600, is_int=True)
        validate_numeric(updated_config, "position_confirm_delay_seconds", 1, 60, is_int=True)
        if not isinstance(updated_config.get("quote_currency"), str) or not updated_config.get("quote_currency"):
             init_logger.warning(f"Invalid 'quote_currency' '{updated_config.get('quote_currency')}'. Must be a non-empty string. Using default '{default_config['quote_currency']}'.")
             updated_config["quote_currency"] = default_config["quote_currency"]
             config_needs_saving = True
        if not isinstance(updated_config.get("enable_trading"), bool):
             init_logger.warning(f"Invalid 'enable_trading' value '{updated_config.get('enable_trading')}'. Must be true or false. Using default '{default_config['enable_trading']}'.")
             updated_config["enable_trading"] = default_config["enable_trading"]
             config_needs_saving = True
        if not isinstance(updated_config.get("use_sandbox"), bool):
             init_logger.warning(f"Invalid 'use_sandbox' value '{updated_config.get('use_sandbox')}'. Must be true or false. Using default '{default_config['use_sandbox']}'.")
             updated_config["use_sandbox"] = default_config["use_sandbox"]
             config_needs_saving = True

        # Strategy Params
        validate_numeric(updated_config, "strategy_params.vt_length", 1, 500, is_int=True)
        validate_numeric(updated_config, "strategy_params.vt_atr_period", 1, MAX_DF_LEN, is_int=True) # Allow long ATR period
        validate_numeric(updated_config, "strategy_params.vt_vol_ema_length", 1, MAX_DF_LEN, is_int=True) # Allow long Vol EMA
        validate_numeric(updated_config, "strategy_params.vt_atr_multiplier", 0.1, 20.0)
        validate_numeric(updated_config, "strategy_params.ph_left", 1, 100, is_int=True)
        validate_numeric(updated_config, "strategy_params.ph_right", 1, 100, is_int=True)
        validate_numeric(updated_config, "strategy_params.pl_left", 1, 100, is_int=True)
        validate_numeric(updated_config, "strategy_params.pl_right", 1, 100, is_int=True)
        validate_numeric(updated_config, "strategy_params.ob_max_boxes", 1, 200, is_int=True)
        validate_numeric(updated_config, "strategy_params.ob_entry_proximity_factor", 1.0, 1.1) # e.g., 1.005 = 0.5% proximity
        validate_numeric(updated_config, "strategy_params.ob_exit_proximity_factor", 1.0, 1.1) # e.g., 1.001 = 0.1% proximity
        if updated_config["strategy_params"].get("ob_source") not in ["Wicks", "Body"]:
             init_logger.warning(f"Invalid strategy_params.ob_source '{updated_config['strategy_params']['ob_source']}'. Must be 'Wicks' or 'Body'. Using default '{DEFAULT_OB_SOURCE}'.")
             updated_config["strategy_params"]["ob_source"] = DEFAULT_OB_SOURCE
             config_needs_saving = True
        if not isinstance(updated_config["strategy_params"].get("ob_extend"), bool):
             init_logger.warning(f"Invalid strategy_params.ob_extend value '{updated_config['strategy_params']['ob_extend']}'. Must be true or false. Using default '{DEFAULT_OB_EXTEND}'.")
             updated_config["strategy_params"]["ob_extend"] = DEFAULT_OB_EXTEND
             config_needs_saving = True

        # Protection Params
        if not isinstance(updated_config["protection"].get("enable_trailing_stop"), bool):
             init_logger.warning(f"Invalid protection.enable_trailing_stop value '{updated_config['protection']['enable_trailing_stop']}'. Must be true or false. Using default '{default_config['protection']['enable_trailing_stop']}'.")
             updated_config["protection"]["enable_trailing_stop"] = default_config["protection"]["enable_trailing_stop"]
             config_needs_saving = True
        if not isinstance(updated_config["protection"].get("enable_break_even"), bool):
             init_logger.warning(f"Invalid protection.enable_break_even value '{updated_config['protection']['enable_break_even']}'. Must be true or false. Using default '{default_config['protection']['enable_break_even']}'.")
             updated_config["protection"]["enable_break_even"] = default_config["protection"]["enable_break_even"]
             config_needs_saving = True
        validate_numeric(updated_config, "protection.trailing_stop_callback_rate", Decimal('0.0001'), Decimal('0.5'), is_strict_min=True) # Must be > 0
        validate_numeric(updated_config, "protection.trailing_stop_activation_percentage", Decimal('0'), Decimal('0.5'), allow_zero=True) # 0 means activate immediately
        validate_numeric(updated_config, "protection.break_even_trigger_atr_multiple", Decimal('0.1'), Decimal('10.0'))
        validate_numeric(updated_config, "protection.break_even_offset_ticks", 0, 1000, is_int=True, allow_zero=True) # 0 means move SL exactly to entry
        validate_numeric(updated_config, "protection.initial_stop_loss_atr_multiple", Decimal('0.1'), Decimal('100.0'), is_strict_min=True) # Must be > 0
        validate_numeric(updated_config, "protection.initial_take_profit_atr_multiple", Decimal('0'), Decimal('100.0'), allow_zero=True) # 0 disables initial TP

        # --- Save Updated Config if Necessary ---
        if config_needs_saving:
             try:
                 # Convert potentially corrected values back to standard types for JSON
                 # (e.g., if defaults were used which might be Decimals internally)
                 # json.dumps handles basic types (int, float, str, bool, list, dict)
                 with open(filepath, "w", encoding="utf-8") as f_write:
                     json.dump(updated_config, f_write, indent=4, ensure_ascii=False)
                 init_logger.info(f"{NEON_GREEN}Saved updated configuration with defaults/corrections to: {filepath}{RESET}")
             except Exception as save_err:
                 init_logger.error(f"{NEON_RED}Error saving updated configuration to '{filepath}': {save_err}{RESET}", exc_info=True)
                 init_logger.warning("Proceeding with corrected config in memory, but file update failed.")

        # Update the global QUOTE_CURRENCY from the validated config
        global QUOTE_CURRENCY
        QUOTE_CURRENCY = updated_config.get("quote_currency", "USDT")
        init_logger.debug(f"Quote currency set to: {QUOTE_CURRENCY}")

        return updated_config # Return the validated and potentially corrected config

    except Exception as e:
        init_logger.error(f"{NEON_RED}FATAL: Unexpected error processing configuration: {e}. Using internal defaults.{RESET}", exc_info=True)
        QUOTE_CURRENCY = default_config.get("quote_currency", "USDT")
        return default_config # Fallback to defaults on unexpected error

# --- Load Global Configuration ---
CONFIG = load_config(CONFIG_FILE)
# QUOTE_CURRENCY is updated inside load_config()

# --- CCXT Exchange Setup ---
def initialize_exchange(logger: logging.Logger) -> Optional[ccxt.Exchange]:
    """
    Initializes and validates the CCXT Bybit exchange object.

    Steps:
    1. Sets API keys, rate limiting, default type (linear), timeouts.
    2. Configures sandbox mode based on `config.json`.
    3. Loads exchange markets with retries, ensuring markets are actually populated.
    4. Performs an initial balance check for the configured `QUOTE_CURRENCY`.
       - If trading is enabled, a failed balance check is treated as a fatal error.
       - If trading is disabled, logs a warning but allows proceeding.

    Args:
        logger (logging.Logger): The logger instance to use for status messages.

    Returns:
        Optional[ccxt.Exchange]: The initialized ccxt.Exchange object if successful, otherwise None.
    """
    lg = logger # Alias for convenience
    try:
        # Common CCXT exchange options
        exchange_options = {
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True, # Enable CCXT's built-in rate limiter
            'options': {
                'defaultType': 'linear',         # Assume linear contracts by default
                'adjustForTimeDifference': True, # Auto-adjust for clock skew
                # Timeouts for various operations (in milliseconds)
                'fetchTickerTimeout': 15000,
                'fetchBalanceTimeout': 20000,
                'createOrderTimeout': 30000,
                'cancelOrderTimeout': 20000,
                'fetchPositionsTimeout': 20000,
                'fetchOHLCVTimeout': 60000,      # Longer timeout for potentially large kline fetches
            }
        }
        # Instantiate the Bybit exchange object
        exchange = ccxt.bybit(exchange_options)

        # Configure Sandbox Mode
        is_sandbox = CONFIG.get('use_sandbox', True)
        exchange.set_sandbox_mode(is_sandbox)
        if is_sandbox:
            lg.warning(f"{NEON_YELLOW}<<< USING SANDBOX MODE (Testnet Environment) >>>{RESET}")
        else:
            lg.warning(f"{NEON_RED}{BRIGHT}!!! <<< USING LIVE TRADING ENVIRONMENT - REAL FUNDS AT RISK >>> !!!{RESET}")

        # Load Markets with Retries
        lg.info(f"Attempting to load markets for {exchange.id}...")
        markets_loaded = False
        last_market_error = None
        for attempt in range(MAX_API_RETRIES + 1):
            try:
                # Force reload on retries to ensure fresh market data
                exchange.load_markets(reload=(attempt > 0))
                if exchange.markets and len(exchange.markets) > 0:
                    lg.info(f"{NEON_GREEN}Markets loaded successfully ({len(exchange.markets)} symbols found).{RESET}")
                    markets_loaded = True
                    break # Exit retry loop on success
                else:
                    last_market_error = ValueError("Market loading returned empty result")
                    lg.warning(f"Market loading returned empty result (Attempt {attempt + 1}/{MAX_API_RETRIES + 1}). Retrying...")
            except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e:
                last_market_error = e
                lg.warning(f"Network error loading markets (Attempt {attempt + 1}/{MAX_API_RETRIES + 1}): {e}.")
                if attempt >= MAX_API_RETRIES:
                    lg.critical(f"{NEON_RED}Maximum retries exceeded while loading markets due to network errors. Last error: {last_market_error}. Exiting.{RESET}")
                    return None
            except ccxt.AuthenticationError as e:
                 last_market_error = e
                 lg.critical(f"{NEON_RED}Authentication error loading markets: {e}. Check API Key/Secret/Permissions. Exiting.{RESET}")
                 return None
            except Exception as e:
                last_market_error = e
                lg.critical(f"{NEON_RED}Unexpected error loading markets: {e}. Exiting.{RESET}", exc_info=True)
                return None

            # Apply delay before retrying
            if not markets_loaded and attempt < MAX_API_RETRIES:
                 delay = RETRY_DELAY_SECONDS * (attempt + 1) # Exponential backoff
                 lg.warning(f"Retrying market load in {delay} seconds...")
                 time.sleep(delay)

        if not markets_loaded:
            lg.critical(f"{NEON_RED}Failed to load markets for {exchange.id} after all retries. Last error: {last_market_error}. Exiting.{RESET}")
            return None

        lg.info(f"CCXT exchange initialized: {exchange.id} | Sandbox: {is_sandbox}")

        # Initial Balance Check
        lg.info(f"Attempting initial balance fetch for quote currency ({QUOTE_CURRENCY})...")
        initial_balance: Optional[Decimal] = None
        try:
            initial_balance = fetch_balance(exchange, QUOTE_CURRENCY, lg)
        except ccxt.AuthenticationError as auth_err:
            # Handle auth errors specifically here as they are critical during balance check
            lg.critical(f"{NEON_RED}Authentication Error during initial balance fetch: {auth_err}. Check API Key/Secret/Permissions. Exiting.{RESET}")
            return None
        except Exception as balance_err:
             # Catch other potential errors during the initial balance check
             lg.warning(f"{NEON_YELLOW}Initial balance fetch encountered an error: {balance_err}.{RESET}", exc_info=True)
             # Let the logic below decide based on trading enabled status

        # Evaluate balance check result based on trading mode
        if initial_balance is not None:
            lg.info(f"{NEON_GREEN}Initial available balance: {initial_balance.normalize()} {QUOTE_CURRENCY}{RESET}")
            return exchange # Success!
        else:
            # Balance fetch failed (fetch_balance logs the failure reason)
            lg.error(f"{NEON_RED}Initial balance fetch FAILED for {QUOTE_CURRENCY}.{RESET}")
            if CONFIG.get('enable_trading', False):
                lg.critical(f"{NEON_RED}Trading is enabled, but initial balance check failed. Cannot proceed safely. Exiting.{RESET}")
                return None
            else:
                lg.warning(f"{NEON_YELLOW}Trading is disabled. Proceeding without confirmed initial balance, but errors might occur later.{RESET}")
                return exchange # Allow proceeding in non-trading mode

    except Exception as e:
        # Catch-all for errors during the initialization process itself
        lg.critical(f"{NEON_RED}Failed to initialize CCXT exchange: {e}{RESET}", exc_info=True)
        return None

# --- CCXT Data Fetching Helpers ---
def fetch_current_price_ccxt(exchange: ccxt.Exchange, symbol: str, logger: logging.Logger) -> Optional[Decimal]:
    """
    Fetches the current market price for a symbol using `fetch_ticker`.

    Prioritizes 'last' price. Falls back progressively:
    1. Mid-price ((bid + ask) / 2) if both bid and ask are valid.
    2. 'ask' price if only ask is valid.
    3. 'bid' price if only bid is valid.

    Includes retry logic for network errors and rate limits.

    Args:
        exchange (ccxt.Exchange): The initialized ccxt.Exchange object.
        symbol (str): The trading symbol (e.g., "BTC/USDT").
        logger (logging.Logger): The logger instance for status messages.

    Returns:
        Optional[Decimal]: The current price as a Decimal, or None if fetching fails after retries
                           or a non-retryable error occurs.
    """
    lg = logger
    attempts = 0
    last_exception = None
    while attempts <= MAX_API_RETRIES:
        try:
            lg.debug(f"Fetching ticker data for {symbol} (Attempt {attempts + 1}/{MAX_API_RETRIES + 1})")
            ticker = exchange.fetch_ticker(symbol)
            price: Optional[Decimal] = None

            # Helper to safely convert ticker values to Decimal
            def safe_decimal_from_ticker(value: Optional[Any], field_name: str) -> Optional[Decimal]:
                """Safely converts ticker field to positive Decimal."""
                if value is None: return None
                try:
                    s_val = str(value).strip()
                    if not s_val: return None
                    dec_val = Decimal(s_val)
                    return dec_val if dec_val > Decimal('0') else None
                except (ValueError, InvalidOperation, TypeError):
                    lg.debug(f"Could not parse ticker field '{field_name}' value '{value}' to Decimal.")
                    return None

            # 1. Try 'last' price
            price = safe_decimal_from_ticker(ticker.get('last'), 'last')

            # 2. Fallback to mid-price if 'last' is invalid
            if price is None:
                bid = safe_decimal_from_ticker(ticker.get('bid'), 'bid')
                ask = safe_decimal_from_ticker(ticker.get('ask'), 'ask')
                if bid and ask:
                    price = (bid + ask) / Decimal('2')
                    lg.debug(f"Using mid-price (Bid: {bid.normalize()}, Ask: {ask.normalize()}) -> {price.normalize()}")
                # 3. Fallback to 'ask' if only ask is valid
                elif ask:
                    price = ask
                    lg.debug(f"Using 'ask' price as fallback: {price.normalize()}")
                # 4. Fallback to 'bid' if only bid is valid
                elif bid:
                    price = bid
                    lg.debug(f"Using 'bid' price as fallback: {price.normalize()}")

            # Check if a valid price was obtained
            if price:
                lg.debug(f"Current price successfully fetched for {symbol}: {price.normalize()}")
                return price.normalize() # Ensure normalization
            else:
                last_exception = ValueError(f"No valid price ('last', 'mid', 'ask', 'bid') found in ticker data. Ticker: {ticker}")
                lg.warning(f"No valid price found in ticker (Attempt {attempts + 1}). Retrying...")

        # --- Error Handling with Retries ---
        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e:
            last_exception = e
            lg.warning(f"{NEON_YELLOW}Network error fetching price for {symbol}: {e}. Retry {attempts + 1}/{MAX_API_RETRIES + 1}...{RESET}")
        except ccxt.RateLimitExceeded as e:
            last_exception = e
            wait_time = RETRY_DELAY_SECONDS * 3 # Longer wait for rate limits
            lg.warning(f"{NEON_YELLOW}Rate limit exceeded fetching price for {symbol}: {e}. Waiting {wait_time}s...{RESET}")
            time.sleep(wait_time)
            # Don't increment attempts, just retry after waiting
            continue
        except ccxt.AuthenticationError as e:
             last_exception = e
             lg.critical(f"{NEON_RED}Authentication Error fetching price: {e}. Check API Key/Secret/Permissions. Stopping fetch.{RESET}")
             return None # Fatal error for this operation
        except ccxt.ExchangeError as e:
            last_exception = e
            lg.error(f"{NEON_RED}Exchange error fetching price for {symbol}: {e}{RESET}")
            # Could add checks for specific non-retryable error codes here if needed
            # For now, assume potentially retryable unless it's an auth error
        except Exception as e:
            last_exception = e
            lg.error(f"{NEON_RED}Unexpected error fetching price for {symbol}: {e}{RESET}", exc_info=True)
            return None # Exit on unexpected errors

        # Increment attempt counter and apply delay (only if not a rate limit wait)
        attempts += 1
        if attempts <= MAX_API_RETRIES:
            time.sleep(RETRY_DELAY_SECONDS * attempts) # Exponential backoff

    lg.error(f"{NEON_RED}Failed to fetch current price for {symbol} after {MAX_API_RETRIES + 1} attempts. Last error: {last_exception}{RESET}")
    return None

def fetch_klines_ccxt(exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int, logger: logging.Logger) -> pd.DataFrame:
    """
    Fetches OHLCV (kline) data using CCXT's `fetch_ohlcv` method with enhancements.

    - Handles Bybit V5 'category' parameter automatically based on market info.
    - Implements robust retry logic for network errors and rate limits.
    - Validates fetched data timestamp lag to detect potential staleness.
    - Processes data into a Pandas DataFrame with Decimal types for precision.
    - Cleans data (drops rows with NaNs in key columns, zero prices/volumes).
    - Trims DataFrame to `MAX_DF_LEN` to manage memory usage.
    - Ensures DataFrame is sorted by timestamp.

    Args:
        exchange (ccxt.Exchange): The initialized ccxt.Exchange object.
        symbol (str): The trading symbol (e.g., "BTC/USDT").
        timeframe (str): The CCXT timeframe string (e.g., "5m", "1h", "1d").
        limit (int): The desired number of klines. Will be capped by `BYBIT_API_KLINE_LIMIT`
                     per API request, but the function aims to fetch the `limit` specified
                     (currently single request, future versions might handle multiple).
        logger (logging.Logger): The logger instance for status messages.

    Returns:
        pd.DataFrame: A Pandas DataFrame containing the OHLCV data, indexed by timestamp (UTC),
                      with columns ['open', 'high', 'low', 'close', 'volume'] as Decimals.
                      Returns an empty DataFrame if fetching or processing fails critically.
    """
    lg = logger
    if not hasattr(exchange, 'fetch_ohlcv') or not exchange.has.get('fetchOHLCV'):
        lg.error(f"Exchange {exchange.id} does not support fetchOHLCV. Cannot fetch klines.")
        return pd.DataFrame()

    # Determine the actual number of klines to request in this single API call
    actual_request_limit = min(limit, BYBIT_API_KLINE_LIMIT)
    if limit > BYBIT_API_KLINE_LIMIT:
        lg.warning(f"Requested limit ({limit}) exceeds API limit ({BYBIT_API_KLINE_LIMIT}). Will request {BYBIT_API_KLINE_LIMIT}. "
                   f"Strategy might require more data than fetched in this single request.")
    elif limit < 50: # Warn if requesting very few candles, might impact indicators
        lg.warning(f"Requesting a small number of klines ({limit}). Ensure this is sufficient for all indicator calculations.")

    ohlcv_data: Optional[List[List[Union[int, float, str]]]] = None
    attempts = 0
    last_exception = None
    while attempts <= MAX_API_RETRIES:
        try:
            lg.debug(f"Fetching klines for {symbol} | TF: {timeframe} | Limit: {actual_request_limit} (Attempt {attempts + 1}/{MAX_API_RETRIES + 1})")
            params = {}
            # Add Bybit V5 specific parameters
            if 'bybit' in exchange.id.lower():
                 try:
                     # Determine category (linear/inverse/spot) for Bybit V5 API
                     market = exchange.market(symbol) # Assumes markets are loaded
                     category = 'linear' if market.get('linear') else 'inverse' if market.get('inverse') else 'spot'
                     params['category'] = category
                     lg.debug(f"Using Bybit category: {category} for kline fetch.")
                 except KeyError:
                     lg.warning(f"Market '{symbol}' not found in loaded markets during kline fetch. Cannot set Bybit category.")
                 except Exception as e:
                     lg.warning(f"Could not automatically determine market category for {symbol} kline fetch: {e}. Proceeding without category param.")

            # Fetch OHLCV data
            ohlcv_data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=actual_request_limit, params=params)
            fetched_count = len(ohlcv_data) if ohlcv_data else 0
            lg.debug(f"API returned {fetched_count} candles (requested {actual_request_limit}).")

            # --- Basic Validation on Fetched Data ---
            if ohlcv_data and fetched_count > 0:
                # Validate timestamp lag of the last candle
                try:
                    last_candle_timestamp_ms = ohlcv_data[-1][0]
                    last_ts = pd.to_datetime(last_candle_timestamp_ms, unit='ms', utc=True)
                    now_utc = pd.Timestamp.utcnow()
                    # Get timeframe duration in seconds
                    interval_seconds = exchange.parse_timeframe(timeframe) # CCXT provides this helper
                    if interval_seconds is None:
                         lg.warning(f"Could not parse timeframe '{timeframe}' to seconds for lag check. Skipping lag validation.")
                         break # Proceed without lag check if parsing fails

                    # Allow a lag of up to 2.5 intervals (generous)
                    max_allowed_lag_seconds = interval_seconds * 2.5
                    actual_lag_seconds = (now_utc - last_ts).total_seconds()

                    if actual_lag_seconds < 0: # Clock skew issue?
                         lg.warning(f"{NEON_YELLOW}Last kline timestamp {last_ts} is in the future? (Lag: {actual_lag_seconds:.1f}s). Check system clock/timezone. Proceeding cautiously.{RESET}")
                         break # Proceed but log warning
                    elif actual_lag_seconds <= max_allowed_lag_seconds:
                        lg.debug(f"Last kline timestamp {last_ts} seems recent (Lag: {actual_lag_seconds:.1f}s <= Max Allowed: {max_allowed_lag_seconds:.1f}s). Data OK.")
                        break # Successful fetch and basic validation passed, exit retry loop
                    else:
                        last_exception = ValueError(f"Kline data potentially stale. Last candle lag ({actual_lag_seconds:.1f}s) > max allowed ({max_allowed_lag_seconds:.1f}s).")
                        lg.warning(f"{NEON_YELLOW}Timestamp lag detected: {last_exception}. Retrying fetch...{RESET}")
                        ohlcv_data = None # Discard potentially stale data and retry

                except IndexError:
                    last_exception = IndexError("Received empty OHLCV data list, cannot validate timestamp.")
                    lg.warning(f"{last_exception}. Retrying fetch...")
                    ohlcv_data = None
                except Exception as ts_err:
                    last_exception = ts_err
                    lg.warning(f"Could not validate kline timestamp lag: {ts_err}. Proceeding with fetched data, but be cautious.")
                    break # Proceed even if validation fails, but log warning
            else:
                last_exception = ValueError(f"API returned no kline data (fetched_count={fetched_count}).")
                lg.warning(f"{last_exception} (Attempt {attempts + 1}). Retrying...")
                ohlcv_data = None # Ensure ohlcv_data is None if fetch failed

        # --- Error Handling with Retries ---
        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e:
            last_exception = e
            lg.warning(f"{NEON_YELLOW}Network error fetching klines for {symbol}: {e}. Retry {attempts + 1}/{MAX_API_RETRIES + 1}...{RESET}")
        except ccxt.RateLimitExceeded as e:
            last_exception = e
            wait_time = RETRY_DELAY_SECONDS * 3 # Longer wait for rate limits
            lg.warning(f"{NEON_YELLOW}Rate limit exceeded fetching klines for {symbol}: {e}. Waiting {wait_time}s...{RESET}")
            time.sleep(wait_time)
            continue # Continue loop without incrementing attempts for rate limit waits
        except ccxt.AuthenticationError as e:
             last_exception = e
             lg.critical(f"{NEON_RED}Authentication Error fetching klines: {e}. Check API Key/Secret/Permissions. Stopping fetch.{RESET}")
             return pd.DataFrame() # Fatal error
        except ccxt.ExchangeError as e:
            last_exception = e
            lg.error(f"{NEON_RED}Exchange error fetching klines for {symbol}: {e}{RESET}")
            # Check for specific non-retryable errors
            if "invalid timeframe" in str(e).lower() or "Interval is not supported" in str(e):
                lg.critical(f"{NEON_RED}Invalid timeframe '{timeframe}' specified for {exchange.id}. Exiting fetch.{RESET}")
                return pd.DataFrame()
            # Otherwise, assume retryable for now
        except Exception as e:
            last_exception = e
            lg.error(f"{NEON_RED}Unexpected error fetching klines for {symbol}: {e}{RESET}", exc_info=True)
            return pd.DataFrame() # Stop on unexpected errors

        # Increment attempt counter and apply delay (only if fetch failed and retries remain)
        attempts += 1
        if attempts <= MAX_API_RETRIES and ohlcv_data is None:
             time.sleep(RETRY_DELAY_SECONDS * attempts) # Exponential backoff

    # After retry loop, check if data was successfully fetched
    if not ohlcv_data:
        lg.error(f"{NEON_RED}Failed to fetch kline data for {symbol} {timeframe} after {MAX_API_RETRIES + 1} attempts. Last error: {last_exception}{RESET}")
        return pd.DataFrame()

    # --- Process Fetched Data into DataFrame ---
    try:
        lg.debug(f"Processing {len(ohlcv_data)} fetched candles into DataFrame...")
        # Define standard OHLCV column names
        cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        # Create DataFrame, ensure columns match the fetched data structure
        df = pd.DataFrame(ohlcv_data, columns=cols[:len(ohlcv_data[0])])

        # Convert timestamp to datetime objects (UTC) and set as index
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True, errors='coerce')
        df.dropna(subset=['timestamp'], inplace=True) # Drop rows with invalid timestamps
        if df.empty:
            lg.error("DataFrame became empty after timestamp conversion/dropna.")
            return pd.DataFrame()
        df.set_index('timestamp', inplace=True)

        # Convert OHLCV columns to Decimal, handling potential errors robustly
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            if col in df.columns:
                # Apply pd.to_numeric first, coercing errors to NaN
                numeric_series = pd.to_numeric(df[col], errors='coerce')
                # Convert valid finite numbers to Decimal, others become Decimal('NaN')
                df[col] = numeric_series.apply(
                    lambda x: Decimal(str(x)) if pd.notna(x) and np.isfinite(x) else Decimal('NaN')
                )
            else:
                 lg.warning(f"Expected column '{col}' not found in fetched kline data.")

        # --- Data Cleaning ---
        initial_len = len(df)
        # Drop rows with NaN in essential price columns or non-positive close price
        essential_price_cols = ['open', 'high', 'low', 'close']
        df.dropna(subset=essential_price_cols, inplace=True)
        df = df[df['close'] > Decimal('0')]
        # Drop rows with NaN volume or negative volume (if volume column exists)
        if 'volume' in df.columns:
            df.dropna(subset=['volume'], inplace=True)
            df = df[df['volume'] >= Decimal('0')] # Allow zero volume

        rows_dropped = initial_len - len(df)
        if rows_dropped > 0:
            lg.debug(f"Dropped {rows_dropped} rows during cleaning (NaNs, zero/neg prices, neg volume).")

        if df.empty:
            lg.warning(f"Kline DataFrame is empty after cleaning for {symbol} {timeframe}.")
            return pd.DataFrame()

        # Ensure DataFrame is sorted by timestamp index (should be from fetch_ohlcv, but verify)
        if not df.index.is_monotonic_increasing:
            lg.warning("Kline DataFrame index was not monotonic, sorting...")
            df.sort_index(inplace=True)

        # --- Memory Management ---
        # Trim DataFrame if it exceeds the maximum allowed length
        if len(df) > MAX_DF_LEN:
            lg.debug(f"DataFrame length ({len(df)}) exceeds maximum ({MAX_DF_LEN}). Trimming to most recent {MAX_DF_LEN} candles.")
            df = df.iloc[-MAX_DF_LEN:].copy() # Keep the latest N rows

        lg.info(f"Successfully fetched and processed {len(df)} klines for {symbol} {timeframe}")
        return df

    except Exception as e:
        lg.error(f"{NEON_RED}Error processing kline data into DataFrame for {symbol}: {e}{RESET}", exc_info=True)
        return pd.DataFrame()

def _safe_market_decimal(value: Optional[Any], field_name: str, allow_zero: bool = True) -> Optional[Decimal]:
    """
    Converts a market info value (potentially str, float, int) to Decimal.

    Handles None, empty strings, and invalid numeric formats.
    Logs debug messages for conversion issues.

    Args:
        value (Optional[Any]): The value to convert.
        field_name (str): The name of the field being converted (for logging).
        allow_zero (bool): Whether a value of zero is considered valid.

    Returns:
        Optional[Decimal]: The converted Decimal value, or None if conversion fails
                           or the value is invalid according to `allow_zero`.
    """
    if value is None:
        # init_logger.debug(f"Market info field '{field_name}' has None value.") # Too verbose for init
        return None
    try:
        s_val = str(value).strip()
        if not s_val:
            # init_logger.debug(f"Market info field '{field_name}' has empty string value.")
            return None
        d_val = Decimal(s_val)
        if not allow_zero and d_val <= Decimal('0'):
             #init_logger.debug(f"Market info field '{field_name}' has non-positive value '{d_val}' (zero not allowed), returning None.")
             return None
        if allow_zero and d_val < Decimal('0'):
             #init_logger.debug(f"Market info field '{field_name}' has negative value '{d_val}' (zero allowed), returning None.")
             return None
        return d_val
    except (InvalidOperation, TypeError, ValueError) as e:
        #init_logger.debug(f"Could not convert market info field '{field_name}' value '{value}' to Decimal: {e}")
        return None

def get_market_info(exchange: ccxt.Exchange, symbol: str, logger: logging.Logger) -> Optional[MarketInfo]:
    """
    Retrieves, validates, and standardizes market information for a symbol.

    - Reloads markets if the symbol is initially not found.
    - Extracts precision (price, amount), limits (min/max amount, cost),
      contract type (linear/inverse/spot), and contract size.
    - Adds convenience flags (`is_contract`, `is_linear`, etc.) and parsed
      Decimal values for precision/limits to the returned dictionary.
    - Includes retry logic for network errors.
    - Logs critical warnings and returns None if essential precision data is missing.

    Args:
        exchange (ccxt.Exchange): The initialized ccxt.Exchange object (must have markets loaded).
        symbol (str): The trading symbol (e.g., "BTC/USDT").
        logger (logging.Logger): The logger instance for status messages.

    Returns:
        Optional[MarketInfo]: A MarketInfo TypedDict containing standardized market details, including
                              parsed Decimal values for limits/precision, or None if the market is not found,
                              essential data is missing, or a critical error occurs.
    """
    lg = logger
    attempts = 0
    last_exception = None
    while attempts <= MAX_API_RETRIES:
        try:
            market: Optional[Dict] = None
            # Check if markets are loaded and the symbol exists
            if not exchange.markets or symbol not in exchange.markets:
                lg.info(f"Market info for '{symbol}' not found in loaded markets. Attempting to reload markets...")
                try:
                    exchange.load_markets(reload=True) # Force reload
                    lg.info("Markets reloaded.")
                except Exception as reload_err:
                     last_exception = reload_err
                     lg.error(f"Failed to reload markets while searching for {symbol}: {reload_err}")
                     # Continue to the retry logic below

            # Try fetching the market dictionary again after potential reload
            try:
                market = exchange.market(symbol)
            except ccxt.BadSymbol:
                 market = None # Handled below
            except Exception as fetch_err:
                 last_exception = fetch_err
                 lg.warning(f"Error fetching market dict for '{symbol}' after reload: {fetch_err}. Retrying...")
                 market = None

            if market is None:
                # Symbol not found or error fetching market dict
                if attempts < MAX_API_RETRIES:
                    lg.warning(f"Symbol '{symbol}' not found or market fetch failed (Attempt {attempts + 1}/{MAX_API_RETRIES + 1}). Retrying check...")
                    # Fall through to retry delay
                else:
                    lg.error(f"{NEON_RED}Market '{symbol}' not found on {exchange.id} after reload and retries. Last error: {last_exception}{RESET}")
                    return None # Symbol definitively not found or fetch failed
            else:
                # --- Market Found - Extract and Standardize Details ---
                lg.debug(f"Market found for '{symbol}'. Standardizing details...")
                std_market = market.copy() # Work on a copy

                # Add custom flags for easier logic later
                std_market['is_contract'] = std_market.get('contract', False) or std_market.get('type') in ['swap', 'future']
                std_market['is_linear'] = std_market.get('linear', False) and std_market['is_contract']
                std_market['is_inverse'] = std_market.get('inverse', False) and std_market['is_contract']
                std_market['contract_type_str'] = "Linear" if std_market['is_linear'] else \
                                                  "Inverse" if std_market['is_inverse'] else \
                                                  "Spot" if std_market.get('spot') else "Unknown"

                # Safely parse precision and limits into Decimal
                precision = std_market.get('precision', {})
                limits = std_market.get('limits', {})
                amount_limits = limits.get('amount', {})
                cost_limits = limits.get('cost', {})
                # price_limits = limits.get('price', {}) # Price limits less commonly used for validation

                # Parse precision steps (must be positive)
                std_market['amount_precision_step_decimal'] = _safe_market_decimal(precision.get('amount'), 'precision.amount', allow_zero=False)
                std_market['price_precision_step_decimal'] = _safe_market_decimal(precision.get('price'), 'precision.price', allow_zero=False)

                # Parse limits (allow zero for min, must be positive if set)
                std_market['min_amount_decimal'] = _safe_market_decimal(amount_limits.get('min'), 'limits.amount.min')
                std_market['max_amount_decimal'] = _safe_market_decimal(amount_limits.get('max'), 'limits.amount.max', allow_zero=False)
                std_market['min_cost_decimal'] = _safe_market_decimal(cost_limits.get('min'), 'limits.cost.min')
                std_market['max_cost_decimal'] = _safe_market_decimal(cost_limits.get('max'), 'limits.cost.max', allow_zero=False)

                # Parse contract size (must be positive, default to 1)
                contract_size_val = std_market.get('contractSize', '1')
                std_market['contract_size_decimal'] = _safe_market_decimal(contract_size_val, 'contractSize', allow_zero=False) or Decimal('1')

                # --- Critical Validation: Essential Precision ---
                if std_market['amount_precision_step_decimal'] is None or std_market['price_precision_step_decimal'] is None:
                    lg.error(f"{NEON_RED}CRITICAL VALIDATION FAILED:{RESET} Market '{symbol}' is missing essential positive precision data.")
                    lg.error(f"  Parsed Amount Precision Step: {std_market['amount_precision_step_decimal']}")
                    lg.error(f"  Parsed Price Precision Step: {std_market['price_precision_step_decimal']}")
                    lg.error(f"  Raw Precision Dict: {precision}")
                    lg.error("Trading calculations require valid positive amount and price precision steps. Cannot proceed safely.")
                    return None # Returning None is safer for the bot flow

                # Log extracted details for verification
                log_msg = (
                    f"Market Info ({symbol}): ID={std_market.get('id', 'N/A')}, Type={std_market.get('type', 'N/A')}, "
                    f"Contract Type={std_market['contract_type_str']}, Active={std_market.get('active', 'N/A')}\n"
                    f"  Precision Steps (Amount/Price): {std_market['amount_precision_step_decimal'].normalize()} / {std_market['price_precision_step_decimal'].normalize()}\n"
                    f"  Limits (Amount Min/Max): {std_market['min_amount_decimal'].normalize() if std_market['min_amount_decimal'] is not None else 'N/A'} / {std_market['max_amount_decimal'].normalize() if std_market['max_amount_decimal'] is not None else 'N/A'}\n"
                    f"  Limits (Cost Min/Max): {std_market['min_cost_decimal'].normalize() if std_market['min_cost_decimal'] is not None else 'N/A'} / {std_market['max_cost_decimal'].normalize() if std_market['max_cost_decimal'] is not None else 'N/A'}\n"
                    f"  Contract Size: {std_market['contract_size_decimal'].normalize()}"
                )
                lg.debug(log_msg)

                # Cast to MarketInfo TypedDict before returning
                try:
                    # Directly cast assuming the structure matches after parsing.
                    # If validation errors occur frequently, add explicit key mapping.
                    final_market_info: MarketInfo = std_market # type: ignore
                    return final_market_info
                except Exception as cast_err:
                     lg.error(f"Error casting market dictionary to MarketInfo TypedDict: {cast_err}")
                     # Fallback: Return the dictionary anyway if casting fails but data seems okay
                     return std_market # type: ignore

        # --- Error Handling with Retries ---
        except ccxt.BadSymbol as e:
            # Symbol is definitively invalid according to the exchange
            lg.error(f"Symbol '{symbol}' is invalid on {exchange.id}: {e}")
            return None
        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e:
            last_exception = e
            lg.warning(f"{NEON_YELLOW}Network error retrieving market info for {symbol}: {e}. Retry {attempts + 1}/{MAX_API_RETRIES + 1}...{RESET}")
            if attempts >= MAX_API_RETRIES:
                lg.error(f"{NEON_RED}Maximum retries exceeded retrieving market info for {symbol} due to network errors. Last error: {last_exception}{RESET}")
                return None
        except ccxt.AuthenticationError as e:
             last_exception = e
             lg.critical(f"{NEON_RED}Authentication Error getting market info: {e}. Check API Key/Secret/Permissions. Stopping fetch.{RESET}")
             return None # Fatal error for this operation
        except ccxt.ExchangeError as e:
            last_exception = e
            lg.error(f"{NEON_RED}Exchange error retrieving market info for {symbol}: {e}{RESET}")
            if attempts >= MAX_API_RETRIES:
                 lg.error(f"{NEON_RED}Maximum retries exceeded retrieving market info for {symbol} due to exchange errors. Last error: {last_exception}{RESET}")
                 return None
        except Exception as e:
            last_exception = e
            lg.error(f"{NEON_RED}Unexpected error retrieving market info for {symbol}: {e}{RESET}", exc_info=True)
            return None # Stop on unexpected errors

        # Increment attempt counter and delay before retrying
        attempts += 1
        time.sleep(RETRY_DELAY_SECONDS * attempts) # Exponential backoff

    # Should only be reached if all retries fail due to network/exchange errors
    lg.error(f"{NEON_RED}Failed to retrieve market info for {symbol} after all attempts. Last error: {last_exception}{RESET}")
    return None

def fetch_balance(exchange: ccxt.Exchange, currency: str, logger: logging.Logger) -> Optional[Decimal]:
    """
    Fetches the available trading balance for a specific currency (e.g., USDT).

    - Handles Bybit V5 account types (UNIFIED, CONTRACT) to find the correct balance.
    - Parses various potential balance fields ('free', 'availableToWithdraw', 'availableBalance').
    - Includes retry logic for network errors and rate limits.
    - Handles authentication errors critically.

    Args:
        exchange (ccxt.Exchange): The initialized ccxt.Exchange object.
        currency (str): The currency code to fetch the balance for (e.g., "USDT").
        logger (logging.Logger): The logger instance for status messages.

    Returns:
        Optional[Decimal]: The available balance as a Decimal (non-negative), or None if fetching fails
                           after retries or a critical error occurs.
    """
    lg = logger
    attempts = 0
    last_exception = None
    while attempts <= MAX_API_RETRIES:
        try:
            balance_str: Optional[str] = None
            found: bool = False
            balance_info: Optional[Dict] = None

            # Bybit V5 often requires specifying account type (Unified or Contract)
            # Check specific types first, then fallback to default request
            account_types_to_check = []
            if 'bybit' in exchange.id.lower():
                 # UNIFIED often holds assets for Linear USDT/USDC contracts
                 # CONTRACT is for Inverse contracts
                 # Check both if unsure, let the API return the relevant one
                 account_types_to_check = ['UNIFIED', 'CONTRACT']
            account_types_to_check.append('') # Always check default/unspecified type

            for acc_type in account_types_to_check:
                try:
                    params = {'accountType': acc_type} if acc_type else {}
                    type_desc = f"Account Type: {acc_type}" if acc_type else "Default Account Type"
                    lg.debug(f"Fetching balance for {currency} ({type_desc}, Attempt {attempts + 1}/{MAX_API_RETRIES + 1})...")
                    balance_info = exchange.fetch_balance(params=params)

                    # --- Try different ways to extract balance ---
                    # 1. Standard CCXT structure ('free' field)
                    if currency in balance_info and balance_info[currency].get('free') is not None:
                        balance_str = str(balance_info[currency]['free'])
                        lg.debug(f"Found balance for {currency} in standard 'free' field ({type_desc}): {balance_str}")
                        found = True; break

                    # 2. Bybit V5 structure (often nested in 'info') - Check specific fields
                    elif 'info' in balance_info and 'result' in balance_info['info'] and isinstance(balance_info['info']['result'].get('list'), list):
                        for account_details in balance_info['info']['result']['list']:
                             # Check if accountType matches the one requested (or if no type was requested)
                             # AND if the account details contain coin information
                             if (not acc_type or account_details.get('accountType') == acc_type) and isinstance(account_details.get('coin'), list):
                                for coin_data in account_details['coin']:
                                    if coin_data.get('coin') == currency:
                                        # Prioritize 'availableToWithdraw', then 'availableBalance', then 'walletBalance'
                                        # These fields often represent the usable balance for trading better than 'equity'
                                        balance_val = coin_data.get('availableToWithdraw')
                                        source_field = 'availableToWithdraw'
                                        if balance_val is None:
                                             balance_val = coin_data.get('availableBalance')
                                             source_field = 'availableBalance'
                                        if balance_val is None:
                                             balance_val = coin_data.get('walletBalance') # Less preferred, might include frozen assets
                                             source_field = 'walletBalance'

                                        if balance_val is not None:
                                            balance_str = str(balance_val)
                                            lg.debug(f"Found balance for {currency} in Bybit V5 structure (Account: {account_details.get('accountType')}, Field: {source_field}): {balance_str}")
                                            found = True; break # Found in coin list
                                if found: break # Found in account details list
                        if found: break # Found across account types

                except ccxt.ExchangeError as e:
                    # Errors like "account type does not exist" are expected when checking multiple types
                    if acc_type and "account type does not exist" in str(e):
                        lg.debug(f"Account type '{acc_type}' not found or not applicable for balance fetch. Trying next...")
                    elif acc_type: # Other errors for specific types
                        lg.debug(f"Minor exchange error fetching balance for type '{acc_type}': {e}. Trying next type...")
                    else: # Raise error if default fetch fails
                        raise e
                    continue # Try the next account type
                except Exception as e:
                    # Catch other unexpected errors during a specific account type check
                    lg.warning(f"Unexpected error fetching balance for type '{acc_type or 'Default'}': {e}. Trying next step...")
                    last_exception = e # Store for potential final error message
                    continue # Try the next account type

            # --- Process the result ---
            if found and balance_str is not None:
                try:
                    balance_decimal = Decimal(balance_str)
                    # Ensure balance is not negative
                    final_balance = max(balance_decimal, Decimal('0'))
                    lg.debug(f"Successfully parsed balance for {currency}: {final_balance.normalize()}")
                    return final_balance # Success
                except (ValueError, InvalidOperation, TypeError) as e:
                    # Raise an error if the found balance string cannot be converted
                    raise ccxt.ExchangeError(f"Failed to convert fetched balance string '{balance_str}' for {currency} to Decimal: {e}")
            elif not found and balance_info is not None:
                # If not found after checking all types, but we got some response
                raise ccxt.ExchangeError(f"Could not find balance information for currency '{currency}' in any checked account type or response structure. Last response info: {balance_info.get('info')}")
            elif not found and balance_info is None:
                # If fetch_balance itself failed to return anything meaningful
                raise ccxt.ExchangeError(f"Could not find balance information for currency '{currency}'. Fetch operation failed.")

        # --- Error Handling with Retries ---
        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e:
            last_exception = e
            lg.warning(f"{NEON_YELLOW}Network error fetching balance for {currency}: {e}. Retry {attempts + 1}/{MAX_API_RETRIES + 1}...{RESET}")
        except ccxt.RateLimitExceeded as e:
            last_exception = e
            wait_time = RETRY_DELAY_SECONDS * 3
            lg.warning(f"{NEON_YELLOW}Rate limit exceeded fetching balance for {currency}: {e}. Waiting {wait_time}s...{RESET}")
            time.sleep(wait_time)
            continue # Continue loop without incrementing attempts
        except ccxt.AuthenticationError as e:
            last_exception = e
            lg.critical(f"{NEON_RED}Authentication Error fetching balance: {e}. Check API Key/Secret/Permissions. Stopping fetch.{RESET}")
            # Raise the exception to be caught by the caller (initialize_exchange) for critical handling
            raise e
        except ccxt.ExchangeError as e:
            last_exception = e
            # Log exchange errors (like currency not found, conversion errors) and retry
            lg.warning(f"{NEON_YELLOW}Exchange error fetching balance for {currency}: {e}. Retry {attempts + 1}/{MAX_API_RETRIES + 1}...{RESET}")
        except Exception as e:
            last_exception = e
            lg.error(f"{NEON_RED}Unexpected error fetching balance for {currency}: {e}{RESET}", exc_info=True)
            return None # Stop on unexpected errors

        # Increment attempt counter and delay before retrying
        attempts += 1
        if attempts <= MAX_API_RETRIES:
            time.sleep(RETRY_DELAY_SECONDS * attempts) # Exponential backoff

    lg.error(f"{NEON_RED}Failed to fetch balance for {currency} after {MAX_API_RETRIES + 1} attempts. Last error: {last_exception}{RESET}")
    return None

# --- Position & Order Management ---
def get_open_position(exchange: ccxt.Exchange, symbol: str, logger: logging.Logger) -> Optional[PositionInfo]:
    """
    Checks for an existing open position for the given symbol using `fetch_positions`.

    - Handles Bybit V5 specifics (category, symbol filtering, parsing `info` field).
    - Determines position side ('long'/'short') and size accurately using Decimal.
    - Parses key position details (entry price, leverage, SL/TP, TSL) into a standardized format.
    - Includes retry logic for network errors and rate limits.
    - Returns a standardized `PositionInfo` dictionary if an active position is found,
      otherwise returns None. Returns None on failure.

    Args:
        exchange (ccxt.Exchange): The initialized ccxt.Exchange object.
        symbol (str): The trading symbol (e.g., "BTC/USDT").
        logger (logging.Logger): The logger instance for status messages.

    Returns:
        Optional[PositionInfo]: A PositionInfo TypedDict containing details of the open position if found,
                                otherwise None.
    """
    lg = logger
    attempts = 0
    last_exception = None
    market_id: Optional[str] = None
    category: Optional[str] = None

    # --- Determine Market ID and Category ---
    try:
        market = exchange.market(symbol)
        market_id = market['id']
        category = 'linear' if market.get('linear') else 'inverse' if market.get('inverse') else 'spot'
        lg.debug(f"Using Market ID: {market_id}, Category: {category} for position check.")
    except KeyError:
        lg.error(f"Market '{symbol}' not found in loaded markets. Cannot check position.")
        return None
    except Exception as e:
        lg.error(f"Error determining market details for position check: {e}")
        return None

    while attempts <= MAX_API_RETRIES:
        try:
            lg.debug(f"Fetching positions for {symbol} (Attempt {attempts + 1}/{MAX_API_RETRIES + 1})...")
            positions: List[Dict] = []

            # --- Fetch Positions (Handling Bybit V5 Specifics) ---
            try:
                # Attempt to fetch positions for the specific symbol and category
                params = {'category': category, 'symbol': market_id}
                lg.debug(f"Fetching positions with specific params: {params}")
                # Request only specific symbol if possible, otherwise fetch all and filter
                if exchange.has.get('fetchPositionsForSymbol'):
                     positions = exchange.fetch_positions_for_symbol(symbol, params=params) # Use dedicated method if available
                elif exchange.has.get('fetchPositions'):
                     all_positions = exchange.fetch_positions(params=params)
                     # Filter the results manually by symbol or market ID
                     positions = [
                         p for p in all_positions
                         if p.get('symbol') == symbol or p.get('info', {}).get('symbol') == market_id
                     ]
                     lg.debug(f"Fetched {len(all_positions)} total positions, filtered down to {len(positions)} for {symbol}.")
                else:
                     raise ccxt.NotSupported("Exchange does not support fetchPositions or fetchPositionsForSymbol.")

            except ccxt.ExchangeError as e:
                 # Bybit often returns specific codes for "no position" or related issues
                 no_pos_codes = [110025] # e.g., "position idx not match position mode" can indicate no pos in one-way
                 no_pos_messages = ["position not found", "no position", "position does not exist"]
                 err_str = str(e).lower()
                 code_str = str(getattr(e, 'code', '') or getattr(e, 'retCode', '')) # Check different code attributes
                 code_match = any(str(c) in code_str for c in no_pos_codes) if code_str else False

                 if code_match or any(msg in err_str for msg in no_pos_messages):
                     lg.info(f"No open position found for {symbol} (Exchange message: {e}).")
                     return None # No position exists
                 else:
                     # Re-raise other exchange errors to be handled by the main retry loop
                     raise e

            # --- Process Fetched Positions ---
            active_position_raw: Optional[Dict] = None
            # Define a small threshold based on amount precision to consider a position "open"
            size_threshold = Decimal('1e-9') # Default small value
            try:
                amount_precision_str = exchange.market(symbol)['precision']['amount']
                if amount_precision_str:
                    # Use a fraction of the minimum amount step as the threshold (e.g., 1% of step)
                    size_threshold = Decimal(str(amount_precision_str)) * Decimal('0.01')
            except Exception as prec_err:
                lg.warning(f"Could not get amount precision for {symbol} to set size threshold: {prec_err}. Using default: {size_threshold}")
            lg.debug(f"Using position size threshold (absolute): {size_threshold.normalize()}")

            # Iterate through the filtered positions to find an active one
            for pos in positions:
                # Extract size from 'info' (exchange-specific) or standard 'contracts' field
                # Bybit V5 uses 'size' in info, CCXT might map to 'contracts' or parse it itself
                size_str_info = str(pos.get('info', {}).get('size', '')).strip()
                size_str_std = str(pos.get('contracts', '')).strip() # Standard field (often float)
                size_str = size_str_info if size_str_info else size_str_std # Prioritize info['size'] if available

                if not size_str:
                    lg.debug(f"Skipping position entry with missing size data: {pos.get('info', {})}")
                    continue

                try:
                    # Convert size to Decimal and check against threshold (absolute value)
                    size_decimal = Decimal(size_str)
                    if abs(size_decimal) > size_threshold:
                        # Found an active position with significant size
                        active_position_raw = pos
                        active_position_raw['size_decimal'] = size_decimal # Store the parsed Decimal size
                        lg.debug(f"Found active position entry: Size={size_decimal.normalize()}")
                        break # Stop searching once an active position is found
                except (ValueError, InvalidOperation, TypeError) as parse_err:
                     # Log error if size string cannot be parsed, skip this entry
                     lg.warning(f"Could not parse/check position size string '{size_str}': {parse_err}. Skipping this position entry.")
                     continue # Move to the next position entry

            # --- Format and Return Active Position ---
            if active_position_raw:
                # Standardize the position dictionary using PositionInfo structure
                std_pos = active_position_raw.copy() # Work on a copy
                info = std_pos.get('info', {}) # Exchange-specific details

                # Determine Side (long/short) reliably
                side = std_pos.get('side') # Standard CCXT field
                size = std_pos['size_decimal'] # Use the parsed Decimal size

                if side not in ['long', 'short']:
                    # Fallback using Bybit V5 'side' field ('Buy'/'Sell') or inferred from size
                    side_v5 = str(info.get('side', '')).lower()
                    if side_v5 == 'buy': side = 'long'
                    elif side_v5 == 'sell': side = 'short'
                    elif size > size_threshold: side = 'long' # Infer from positive size
                    elif size < -size_threshold: side = 'short' # Infer from negative size
                    else: side = None # Cannot determine side

                if not side:
                    lg.error(f"Could not determine side for active position {symbol}. Size: {size}. Data: {info}")
                    return None # Cannot proceed without side
                std_pos['side'] = side # Update the standardized dict

                # Standardize other key fields (prefer standard CCXT, fallback to info)
                std_pos['entryPrice'] = std_pos.get('entryPrice') or info.get('avgPrice') or info.get('entryPrice')
                std_pos['leverage'] = std_pos.get('leverage') or info.get('leverage')
                std_pos['liquidationPrice'] = std_pos.get('liquidationPrice') or info.get('liqPrice')
                std_pos['unrealizedPnl'] = std_pos.get('unrealizedPnl') or info.get('unrealisedPnl') or info.get('unrealizedPnl')

                # Parse protection levels from 'info' (Bybit V5 specific fields)
                # Ensure they are non-empty strings and represent non-zero values before storing
                def get_protection_field(field_name: str) -> Optional[str]:
                    """Extracts protection field if valid non-zero number string."""
                    value = info.get(field_name)
                    if value is None: return None
                    s_value = str(value).strip()
                    try:
                         # Check if it's a valid number and not zero
                         if s_value and Decimal(s_value) != Decimal('0'):
                             return s_value
                    except (InvalidOperation, ValueError, TypeError):
                         return None # Ignore if not a valid non-zero number string
                    return None

                std_pos['stopLossPrice'] = get_protection_field('stopLoss')
                std_pos['takeProfitPrice'] = get_protection_field('takeProfit')
                std_pos['trailingStopLoss'] = get_protection_field('trailingStop') # TSL distance
                std_pos['tslActivationPrice'] = get_protection_field('activePrice') # TSL activation price

                # Helper for formatting Decimal values for logging
                def format_decimal(value: Optional[Any]) -> str:
                    if value is None: return 'N/A'
                    try: return str(Decimal(str(value)).normalize())
                    except (InvalidOperation, TypeError, ValueError): return 'Invalid'

                # Log summary of the found position
                ep_str = format_decimal(std_pos.get('entryPrice'))
                size_str = std_pos['size_decimal'].normalize()
                sl_str = format_decimal(std_pos.get('stopLossPrice'))
                tp_str = format_decimal(std_pos.get('takeProfitPrice'))
                tsl_dist_str = format_decimal(std_pos.get('trailingStopLoss'))
                tsl_act_str = format_decimal(std_pos.get('tslActivationPrice'))
                tsl_log = f"({tsl_dist_str or 'N/A'}/{tsl_act_str or 'N/A'})" if tsl_dist_str or tsl_act_str else "(N/A)"
                pnl_str = format_decimal(std_pos.get('unrealizedPnl'))
                liq_str = format_decimal(std_pos.get('liquidationPrice'))

                lg.info(f"{NEON_GREEN}{BRIGHT}Active {side.upper()} Position Found ({symbol}):{RESET} "
                        f"Size={size_str}, Entry={ep_str}, Liq={liq_str}, PnL={pnl_str}, "
                        f"SL={sl_str}, TP={tp_str}, TSL={tsl_log}")

                # Cast to PositionInfo TypedDict before returning
                try:
                    # Assume structure matches after parsing
                    final_position_info: PositionInfo = std_pos # type: ignore
                    return final_position_info
                except Exception as cast_err:
                     lg.error(f"Error casting position dictionary to PositionInfo TypedDict: {cast_err}")
                     return std_pos # type: ignore # Return raw dict if cast fails
            else:
                # No position with size > threshold was found after filtering
                lg.info(f"No active position found for {symbol} (checked {len(positions)} filtered entries).")
                return None

        # --- Error Handling with Retries ---
        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e:
            last_exception = e
            lg.warning(f"{NEON_YELLOW}Network error fetching positions for {symbol}: {e}. Retry {attempts + 1}/{MAX_API_RETRIES + 1}...{RESET}")
        except ccxt.RateLimitExceeded as e:
            last_exception = e
            wait_time = RETRY_DELAY_SECONDS * 3
            lg.warning(f"{NEON_YELLOW}Rate limit exceeded fetching positions for {symbol}: {e}. Waiting {wait_time}s...{RESET}")
            time.sleep(wait_time)
            continue # Continue loop without incrementing attempts
        except ccxt.AuthenticationError as e:
            last_exception = e
            lg.critical(f"{NEON_RED}Authentication Error fetching positions: {e}. Check API Key/Secret/Permissions. Stopping fetch.{RESET}")
            return None # Fatal error for this operation
        except ccxt.ExchangeError as e:
            last_exception = e
            lg.warning(f"{NEON_YELLOW}Exchange error fetching positions for {symbol}: {e}. Retry {attempts + 1}/{MAX_API_RETRIES + 1}...{RESET}")
            # Could add checks for specific non-retryable errors here
        except Exception as e:
            last_exception = e
            lg.error(f"{NEON_RED}Unexpected error fetching/processing positions for {symbol}: {e}{RESET}", exc_info=True)
            return None # Stop on unexpected errors

        # Increment attempt counter and delay before retrying
        attempts += 1
        if attempts <= MAX_API_RETRIES:
            time.sleep(RETRY_DELAY_SECONDS * attempts) # Exponential backoff

    lg.error(f"{NEON_RED}Failed to get position info for {symbol} after {MAX_API_RETRIES + 1} attempts. Last error: {last_exception}{RESET}")
    return None

def set_leverage_ccxt(exchange: ccxt.Exchange, symbol: str, leverage: int, market_info: MarketInfo, logger: logging.Logger) -> bool:
    """
    Sets the leverage for a derivatives symbol using `set_leverage`.

    - Skips if the market is not a contract (spot) or leverage is invalid (<= 0).
    - Handles Bybit V5 specific parameters (category, buy/sell leverage).
    - Includes retry logic for network/exchange errors.
    - Checks for specific Bybit codes indicating success (`0`) or leverage already set (`110045`).
    - Identifies and handles known non-retryable leverage errors.

    Args:
        exchange (ccxt.Exchange): The initialized ccxt.Exchange object.
        symbol (str): The trading symbol (e.g., "BTC/USDT").
        leverage (int): The desired integer leverage level.
        market_info (MarketInfo): The standardized MarketInfo dictionary.
        logger (logging.Logger): The logger instance for status messages.

    Returns:
        bool: True if leverage was set successfully or was already set correctly, False otherwise.
    """
    lg = logger
    # Validate input and market type
    if not market_info.get('is_contract', False):
        lg.info(f"Leverage setting skipped for {symbol}: Not a contract market.")
        return True # Consider success as no action needed for spot
    if not isinstance(leverage, int) or leverage <= 0:
        lg.warning(f"Leverage setting skipped for {symbol}: Invalid leverage value ({leverage}). Must be a positive integer.")
        return False
    if not hasattr(exchange, 'set_leverage') or not exchange.has.get('setLeverage'):
        lg.error(f"Exchange {exchange.id} does not support setLeverage method.")
        return False

    market_id = market_info['id'] # Use the exchange-specific market ID

    attempts = 0
    last_exception = None
    while attempts <= MAX_API_RETRIES:
        try:
            lg.info(f"Attempting to set leverage for {market_id} to {leverage}x (Attempt {attempts + 1}/{MAX_API_RETRIES + 1})...")
            params = {}
            # --- Bybit V5 Specific Parameters ---
            if 'bybit' in exchange.id.lower():
                 # Determine category and set buy/sell leverage explicitly for Bybit V5
                 category = market_info.get('contract_type_str', 'Linear').lower() # 'linear' or 'inverse'
                 if category not in ['linear', 'inverse']:
                      lg.warning(f"Leverage setting skipped: Cannot determine valid category ('linear'/'inverse') for {symbol}. Detected: {category}")
                      return False
                 params = {
                     'category': category,
                     #'symbol': market_id, # Symbol passed separately to set_leverage
                     'buyLeverage': str(leverage), # Bybit expects strings
                     'sellLeverage': str(leverage)
                 }
                 lg.debug(f"Using Bybit V5 setLeverage params: {params}")

            # --- Execute set_leverage call ---
            # Pass market_id as the symbol argument
            response = exchange.set_leverage(leverage=leverage, symbol=market_id, params=params)
            lg.debug(f"set_leverage raw response: {response}")

            # --- Check Response (Bybit V5 specific codes) ---
            # CCXT might parse some responses, but Bybit often returns structured info
            ret_code_str = None
            ret_msg = "N/A"
            if isinstance(response, dict):
                 ret_code_str = str(response.get('retCode', response.get('code'))) # Check both common keys
                 ret_msg = response.get('retMsg', response.get('message', 'Unknown Bybit API message'))

            if ret_code_str == '0':
                 lg.info(f"{NEON_GREEN}Leverage successfully set for {market_id} to {leverage}x (Bybit Code: 0).{RESET}")
                 return True
            elif ret_code_str == '110045': # "Leverage not modified"
                 lg.info(f"{NEON_YELLOW}Leverage for {market_id} is already {leverage}x (Bybit Code: 110045).{RESET}")
                 return True
            elif ret_code_str is not None and ret_code_str != 'None': # Check if a non-zero code was returned
                 # Raise an error for other non-zero Bybit return codes
                 raise ccxt.ExchangeError(f"Bybit API error setting leverage: {ret_msg} (Code: {ret_code_str})")
            else:
                # Assume success if no specific error code structure is found and no exception was raised by CCXT
                lg.info(f"{NEON_GREEN}Leverage set/confirmed for {market_id} to {leverage}x (No specific Bybit error code found in response).{RESET}")
                return True

        # --- Error Handling with Retries ---
        except ccxt.ExchangeError as e:
            last_exception = e
            err_code_str = str(getattr(e, 'code', '') or getattr(e, 'retCode', '')) # Check different code attributes
            err_str = str(e).lower()
            lg.error(f"{NEON_RED}Exchange error setting leverage for {market_id}: {e} (Code: {err_code_str}){RESET}")

            # Check for non-retryable conditions based on code or message
            if err_code_str == '110045' or "leverage not modified" in err_str:
                lg.info(f"{NEON_YELLOW}Leverage already set (detected via error). Treating as success.{RESET}")
                return True # Already set is considered success

            # List of known fatal Bybit error codes for leverage setting
            # Based on Bybit API docs and common issues
            fatal_codes = [
                '10001', # Parameter error
                '10004', # Sign check error
                '110009',# Margin mode cannot be modified when position exists
                '110013',# Parameter error (generic)
                '110028',# Leverage cannot be greater/less than risk limit leverage
                '110043',# Position status is not normal (e.g., closing)
                '110044',# Leverage cannot be modified when position exists (cross margin)
                '110055',# Risk limit cannot be modified when position exists
                '3400045',# Set margin mode failed
            ]
            # Common fatal message fragments
            fatal_messages = ["margin mode", "position exists", "risk limit", "parameter error", "insufficient balance", "invalid leverage"]

            if err_code_str in fatal_codes or any(msg in err_str for msg in fatal_messages):
                lg.error(f"{NEON_RED} >> Hint: This appears to be a NON-RETRYABLE leverage error. Aborting leverage set.{RESET}")
                return False # Fatal error

            # If error is potentially retryable and retries remain
            if attempts >= MAX_API_RETRIES:
                lg.error(f"{NEON_RED}Maximum retries exceeded for ExchangeError setting leverage. Last error: {last_exception}{RESET}")
                return False

        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e:
            last_exception = e
            lg.warning(f"{NEON_YELLOW}Network error setting leverage for {market_id}: {e}. Retry {attempts + 1}/{MAX_API_RETRIES + 1}...{RESET}")
            if attempts >= MAX_API_RETRIES:
                lg.error(f"{NEON_RED}Maximum retries exceeded for NetworkError setting leverage. Last error: {last_exception}{RESET}")
                return False

        except ccxt.AuthenticationError as e:
             last_exception = e
             lg.critical(f"{NEON_RED}Authentication Error setting leverage: {e}. Check API Key/Secret/Permissions. Stopping leverage set.{RESET}")
             return False # Fatal error for this operation

        except Exception as e:
            last_exception = e
            lg.error(f"{NEON_RED}Unexpected error setting leverage for {market_id}: {e}{RESET}", exc_info=True)
            return False # Stop on unexpected errors

        # Increment attempt counter and delay before retrying
        attempts += 1
        time.sleep(RETRY_DELAY_SECONDS * attempts) # Exponential backoff

    lg.error(f"{NEON_RED}Failed to set leverage for {market_id} to {leverage}x after {MAX_API_RETRIES + 1} attempts. Last error: {last_exception}{RESET}")
    return False

def calculate_position_size(balance: Decimal, risk_per_trade: float, initial_stop_loss_price: Decimal, entry_price: Decimal,
                            market_info: MarketInfo, exchange: ccxt.Exchange, logger: logging.Logger) -> Optional[Decimal]:
    """
    Calculates the appropriate position size based on risk parameters and market constraints.

    Uses Decimal for all financial calculations to ensure precision. Handles both
    linear and inverse contracts. Applies market precision and limits (amount, cost)
    to the calculated size, rounding the final size DOWN to the nearest valid step.

    Args:
        balance (Decimal): Available trading balance (in quote currency, e.g., USDT). Must be positive.
        risk_per_trade (float): Fraction of balance to risk (e.g., 0.01 for 1%). Must be > 0 and <= 1.
        initial_stop_loss_price (Decimal): The calculated initial stop loss price. Must be positive and different from entry.
        entry_price (Decimal): The intended entry price (or current price). Must be positive.
        market_info (MarketInfo): The standardized MarketInfo dictionary containing precision, limits, contract type, etc.
        exchange (ccxt.Exchange): The initialized ccxt.Exchange object (used for precision formatting).
        logger (logging.Logger): The logger instance for status messages.

    Returns:
        Optional[Decimal]: The calculated position size as a Decimal, adjusted for market rules (positive value),
                           or None if sizing is not possible (e.g., invalid inputs, insufficient balance for min size,
                           cannot meet limits, calculation errors).
    """
    lg = logger
    symbol = market_info['symbol']
    quote_currency = market_info.get('quote', 'QUOTE')
    base_currency = market_info.get('base', 'BASE')
    is_contract = market_info.get('is_contract', False)
    is_inverse = market_info.get('is_inverse', False)
    # Determine the unit of the size (Contracts for derivatives, Base currency for Spot)
    size_unit = base_currency if market_info.get('spot', False) else "Contracts"

    lg.info(f"{BRIGHT}--- Position Sizing Calculation ({symbol}) ---{RESET}")

    # --- Input Validation ---
    if balance <= Decimal('0'):
        lg.error(f"Sizing failed: Invalid balance ({balance.normalize()} {quote_currency}). Must be positive.")
        return None
    try:
        risk_decimal = Decimal(str(risk_per_trade))
        if not (Decimal('0') < risk_decimal <= Decimal('1')):
            raise ValueError("Risk per trade must be between 0 (exclusive) and 1 (inclusive).")
    except (ValueError, InvalidOperation, TypeError) as e:
        lg.error(f"Sizing failed: Invalid risk_per_trade value '{risk_per_trade}': {e}")
        return None
    if initial_stop_loss_price <= Decimal('0') or entry_price <= Decimal('0'):
        lg.error(f"Sizing failed: Entry price ({entry_price.normalize()}) and Stop Loss price ({initial_stop_loss_price.normalize()}) must be positive.")
        return None
    if initial_stop_loss_price == entry_price:
        lg.error(f"Sizing failed: Stop Loss price ({initial_stop_loss_price.normalize()}) cannot be equal to Entry price ({entry_price.normalize()}).")
        return None

    # --- Extract Market Constraints (using pre-parsed Decimal values from MarketInfo) ---
    try:
        amount_precision_step = market_info['amount_precision_step_decimal']
        price_precision_step = market_info['price_precision_step_decimal'] # Needed for cost estimation/validation
        min_amount = market_info['min_amount_decimal']
        max_amount = market_info['max_amount_decimal']
        min_cost = market_info['min_cost_decimal']
        max_cost = market_info['max_cost_decimal']
        contract_size = market_info['contract_size_decimal']

        # Check if essential constraints are valid
        if amount_precision_step is None or amount_precision_step <= 0:
             raise ValueError(f"Invalid or missing amount precision step: {amount_precision_step}")
        if price_precision_step is None or price_precision_step <= 0:
             raise ValueError(f"Invalid or missing price precision step: {price_precision_step}")
        if contract_size <= Decimal('0'):
             raise ValueError(f"Invalid contract size: {contract_size}")

        # Set defaults for optional limits if they are None
        min_amount = min_amount if min_amount is not None else Decimal('0')
        max_amount = max_amount if max_amount is not None else Decimal('inf')
        min_cost = min_cost if min_cost is not None else Decimal('0')
        max_cost = max_cost if max_cost is not None else Decimal('inf')

        lg.debug(f"  Market Constraints: Amount Step={amount_precision_step.normalize()}, Min/Max Amount={min_amount.normalize()}/{max_amount.normalize()}, "
                 f"Min/Max Cost={min_cost.normalize()}/{max_cost.normalize()}, Contract Size={contract_size.normalize()}")

    except (KeyError, ValueError, TypeError) as e:
        lg.error(f"Sizing failed: Error extracting or validating market details for {symbol}: {e}")
        lg.debug(f"  MarketInfo received: {market_info}")
        return None

    # --- Calculate Risk Amount and Stop Loss Distance ---
    risk_amount_quote = (balance * risk_decimal).quantize(Decimal('1e-8'), ROUND_DOWN) # Quantize risk amount
    stop_loss_distance_price = abs(entry_price - initial_stop_loss_price)

    if stop_loss_distance_price <= Decimal('0'):
        # This should be caught earlier, but double-check
        lg.error(f"Sizing failed: Stop Loss distance is zero or negative ({stop_loss_distance_price.normalize()}).")
        return None

    lg.info(f"  Balance: {balance.normalize()} {quote_currency}")
    lg.info(f"  Risk Per Trade: {risk_decimal:.2%}")
    lg.info(f"  Risk Amount: {risk_amount_quote.normalize()} {quote_currency}")
    lg.info(f"  Entry Price: {entry_price.normalize()}")
    lg.info(f"  Stop Loss Price: {initial_stop_loss_price.normalize()}")
    lg.info(f"  Stop Loss Distance (Price): {stop_loss_distance_price.normalize()}")
    lg.info(f"  Contract Type: {market_info['contract_type_str']}")

    # --- Calculate Initial Position Size (based on risk) ---
    calculated_size = Decimal('0')
    try:
        if not is_inverse: # Linear Contracts or Spot
            # Risk per unit = Price distance * Contract Size (value change per contract/base unit per $1 price move)
            # For Spot, contract_size is typically 1 (1 unit of base currency)
            value_change_per_unit = stop_loss_distance_price * contract_size
            if value_change_per_unit <= Decimal('1e-18'): # Use tolerance for zero check
                 lg.error("Sizing failed (Linear/Spot): Calculated value change per unit is effectively zero.")
                 return None
            # Size = Total Risk Amount / Value Change Per Unit
            calculated_size = risk_amount_quote / value_change_per_unit
            lg.debug(f"  Linear/Spot Calc: RiskAmt={risk_amount_quote} / ValueChangePerUnit={value_change_per_unit} = {calculated_size}")

        else: # Inverse Contracts
            # Risk per contract = Contract Size * |(1 / Entry) - (1 / SL)| (change in value of 1 contract in quote currency)
            if entry_price <= 0 or initial_stop_loss_price <= 0:
                 lg.error("Sizing failed (Inverse): Entry or SL price is zero or negative.")
                 return None
            # Use Decimal for inverse calculation
            inverse_factor = abs( (Decimal('1') / entry_price) - (Decimal('1') / initial_stop_loss_price) )
            if inverse_factor <= Decimal('1e-18'): # Tolerance for zero check
                 lg.error("Sizing failed (Inverse): Calculated inverse factor is effectively zero.")
                 return None
            risk_per_contract_quote = contract_size * inverse_factor
            if risk_per_contract_quote <= Decimal('1e-18'): # Tolerance for zero check
                 lg.error("Sizing failed (Inverse): Calculated risk per contract is effectively zero.")
                 return None
            # Size = Total Risk Amount / Risk per Contract
            calculated_size = risk_amount_quote / risk_per_contract_quote
            lg.debug(f"  Inverse Calc: RiskAmt={risk_amount_quote} / RiskPerContract={risk_per_contract_quote} = {calculated_size}")

    except (InvalidOperation, OverflowError, ZeroDivisionError) as calc_err:
        lg.error(f"Sizing failed: Error during initial size calculation: {calc_err}.")
        return None

    if calculated_size <= Decimal('0'):
        lg.error(f"Sizing failed: Initial calculated size is zero or negative ({calculated_size.normalize()}). Check inputs/risk/market data.")
        return None

    lg.info(f"  Initial Calculated Size = {calculated_size.normalize()} {size_unit}")

    # --- Apply Market Limits and Precision ---
    adjusted_size = calculated_size

    # Helper function to estimate cost
    def estimate_cost(size: Decimal, price: Decimal) -> Optional[Decimal]:
        """Estimates order cost based on size, price, contract type."""
        if price <= 0 or size <= 0: return None
        try:
             # Cost = Size * Price * ContractSize (Linear) or Size * ContractSize / Price (Inverse)
             # For Spot, ContractSize is 1
             if not is_inverse:
                 return (size * price * contract_size)
             else:
                 return (size * contract_size) / price
        except (InvalidOperation, OverflowError, ZeroDivisionError):
            return None

    # 1. Apply Amount Limits (Min/Max Size)
    if min_amount > 0 and adjusted_size < min_amount:
        lg.warning(f"{NEON_YELLOW}Calculated size {adjusted_size.normalize()} is below minimum amount {min_amount.normalize()}. Adjusting UP to minimum.{RESET}")
        adjusted_size = min_amount
    if max_amount < Decimal('inf') and adjusted_size > max_amount:
        lg.warning(f"{NEON_YELLOW}Calculated size {adjusted_size.normalize()} exceeds maximum amount {max_amount.normalize()}. Adjusting DOWN to maximum.{RESET}")
        adjusted_size = max_amount
    lg.debug(f"  Size after Amount Limits: {adjusted_size.normalize()} {size_unit}")

    # 2. Apply Cost Limits (Min/Max Order Value)
    estimated_cost_after_amount_limits = estimate_cost(adjusted_size, entry_price)
    cost_adjustment_applied = False

    if estimated_cost_after_amount_limits is not None:
        lg.debug(f"  Estimated Cost (after amount limits): {estimated_cost_after_amount_limits.normalize()} {quote_currency}")

        # Check Minimum Cost
        if min_cost > 0 and estimated_cost_after_amount_limits < min_cost:
            lg.warning(f"{NEON_YELLOW}Estimated cost {estimated_cost_after_amount_limits.normalize()} is below minimum cost {min_cost.normalize()}. Attempting to increase size.{RESET}")
            required_size_for_min_cost = None
            try:
                # Calculate size needed to meet min cost: MinCost / (Price * ContrSize) [Lin/Spot] or MinCost * Price / ContrSize [Inv]
                if not is_inverse:
                    denominator = entry_price * contract_size
                    if denominator <= Decimal('1e-18'): raise ZeroDivisionError("Linear/Spot cost calc denominator near zero")
                    required_size_for_min_cost = min_cost / denominator
                else:
                    if entry_price <= Decimal('1e-18') or contract_size <= 0: raise ValueError("Invalid price/contract size for inverse cost calc")
                    required_size_for_min_cost = (min_cost * entry_price) / contract_size

                if required_size_for_min_cost is None or required_size_for_min_cost <= 0: raise ValueError("Invalid required size calculation for min cost")
                lg.info(f"  Size required to meet min cost: {required_size_for_min_cost.normalize()} {size_unit}")

                # Check if this required size exceeds max amount limit
                if max_amount < Decimal('inf') and required_size_for_min_cost > max_amount:
                    lg.error(f"{NEON_RED}Sizing failed: Cannot meet minimum cost ({min_cost.normalize()}) without exceeding maximum amount limit ({max_amount.normalize()}).{RESET}")
                    return None

                # Adjust size up, ensuring it's still meets the original min_amount if that was larger
                adjusted_size = max(min_amount, required_size_for_min_cost)
                cost_adjustment_applied = True

            except (InvalidOperation, OverflowError, ZeroDivisionError, ValueError) as cost_calc_err:
                lg.error(f"{NEON_RED}Sizing failed: Failed to calculate size needed for minimum cost: {cost_calc_err}.{RESET}")
                return None

        # Check Maximum Cost
        elif max_cost < Decimal('inf') and estimated_cost_after_amount_limits > max_cost:
            lg.warning(f"{NEON_YELLOW}Estimated cost {estimated_cost_after_amount_limits.normalize()} exceeds maximum cost {max_cost.normalize()}. Attempting to reduce size.{RESET}")
            max_size_for_max_cost = None
            try:
                # Calculate max size allowed by max cost: MaxCost / (Price * ContrSize) [Lin/Spot] or MaxCost * Price / ContrSize [Inv]
                if not is_inverse:
                    denominator = entry_price * contract_size
                    if denominator <= Decimal('1e-18'): raise ZeroDivisionError("Linear/Spot cost calc denominator near zero")
                    max_size_for_max_cost = max_cost / denominator
                else:
                    if entry_price <= Decimal('1e-18') or contract_size <= 0: raise ValueError("Invalid price/contract size for inverse cost calc")
                    max_size_for_max_cost = (max_cost * entry_price) / contract_size

                if max_size_for_max_cost is None or max_size_for_max_cost <= 0: raise ValueError("Invalid max size calculation for max cost")
                lg.info(f"  Maximum size allowed by max cost: {max_size_for_max_cost.normalize()} {size_unit}")

                # Adjust size down, ensuring it's still at least the minimum amount
                # Take the smaller of current adjusted size OR max allowed by cost, but never less than min_amount
                adjusted_size = max(min_amount, min(adjusted_size, max_size_for_max_cost))
                cost_adjustment_applied = True

            except (InvalidOperation, OverflowError, ZeroDivisionError, ValueError) as cost_calc_err:
                lg.error(f"{NEON_RED}Sizing failed: Failed to calculate maximum size allowed by maximum cost: {cost_calc_err}.{RESET}")
                return None

    elif min_cost > 0 or max_cost < Decimal('inf'):
        lg.warning("Could not estimate cost for limit check. Proceeding without cost limit adjustments.")

    if cost_adjustment_applied:
        lg.info(f"  Size after Cost Limits: {adjusted_size.normalize()} {size_unit}")

    # 3. Apply Amount Precision (Rounding DOWN to step size for safety)
    final_size = adjusted_size
    try:
        if amount_precision_step <= 0:
            raise ValueError("Amount precision step is zero or negative, cannot apply precision.")

        # Manual Rounding Down: size = floor(value / step) * step
        final_size = (adjusted_size / amount_precision_step).quantize(Decimal('1'), ROUND_DOWN) * amount_precision_step

        if final_size != adjusted_size:
            lg.info(f"Applied amount precision (Rounded DOWN to step {amount_precision_step.normalize()}): {adjusted_size.normalize()} -> {final_size.normalize()} {size_unit}")
            # Optional: Log CCXT's version for comparison if needed
            # try:
            #    amount_str_formatted_ccxt = exchange.amount_to_precision(symbol, float(adjusted_size))
            #    final_size_ccxt = Decimal(amount_str_formatted_ccxt)
            #    if abs(final_size_ccxt - final_size) > Decimal('1e-18'):
            #        lg.debug(f"  (CCXT amount_to_precision suggested: {final_size_ccxt.normalize()})")
            # except Exception as fmt_err_ccxt:
            #    lg.debug(f"Could not get CCXT amount_to_precision value: {fmt_err_ccxt}")

    except (InvalidOperation, ValueError, TypeError) as fmt_err:
        lg.error(f"{NEON_RED}Error applying amount precision: {fmt_err}. Using unrounded size: {final_size.normalize()}{RESET}")
        # Continue with the unrounded size, but subsequent checks might fail

    # --- Final Validation after Precision ---
    if final_size <= Decimal('0'):
        lg.error(f"{NEON_RED}Sizing failed: Final size after precision is zero or negative ({final_size.normalize()}).{RESET}")
        return None
    # Check Min Amount again after rounding down
    if min_amount > 0 and final_size < min_amount:
        lg.error(f"{NEON_RED}Sizing failed: Final size {final_size.normalize()} is below minimum amount {min_amount.normalize()} after precision adjustment.{RESET}")
        # Option: Could bump up to min_amount here, but that slightly violates risk/precision. Aborting is safer.
        return None
    # Check Max Amount again (should be fine if rounded down, but check)
    if max_amount < Decimal('inf') and final_size > max_amount:
         lg.error(f"{NEON_RED}Sizing failed: Final size {final_size.normalize()} exceeds maximum amount {max_amount.normalize()} after precision.{RESET}")
         return None

    # Final check on cost after precision applied (especially if rounded down)
    final_cost = estimate_cost(final_size, entry_price)
    if final_cost is not None:
        lg.debug(f"  Final Estimated Cost: {final_cost.normalize()} {quote_currency}")
        if min_cost > 0 and final_cost < min_cost:
             lg.warning(f"{NEON_YELLOW}Final cost {final_cost.normalize()} is slightly below min cost {min_cost.normalize()} after precision rounding.{RESET}")
             # Option: Try bumping size up by one step if possible within other limits
             try:
                 next_step_size = final_size + amount_precision_step
                 next_step_cost = estimate_cost(next_step_size, entry_price)

                 if next_step_cost is not None:
                     # Check if bumping up is valid (meets min cost, doesn't exceed max amount/cost)
                     can_bump_up = (next_step_cost >= min_cost) and \
                                   (max_amount == Decimal('inf') or next_step_size <= max_amount) and \
                                   (max_cost == Decimal('inf') or next_step_cost <= max_cost)

                     if can_bump_up:
                         lg.info(f"{NEON_YELLOW}Bumping final size up by one step to {next_step_size.normalize()} to meet minimum cost.{RESET}")
                         final_size = next_step_size
                         # Recalculate final cost for logging
                         final_cost = estimate_cost(final_size, entry_price)
                         lg.debug(f"  Final Estimated Cost (after bump): {final_cost.normalize() if final_cost else 'N/A'} {quote_currency}")
                     else:
                         lg.error(f"{NEON_RED}Sizing failed: Cannot meet minimum cost even by bumping size one step due to other limits (Max Amount/Cost).{RESET}")
                         return None
                 else:
                      lg.error(f"{NEON_RED}Sizing failed: Could not estimate cost for bumped size {next_step_size.normalize()}. Cannot verify min cost.{RESET}")
                      return None

             except Exception as bump_err:
                 lg.error(f"{NEON_RED}Sizing failed: Error trying to bump size for min cost: {bump_err}.{RESET}")
                 return None
        elif max_cost < Decimal('inf') and final_cost > max_cost:
            # This shouldn't happen if rounding down, but check defensively
             lg.error(f"{NEON_RED}Sizing failed: Final cost {final_cost.normalize()} exceeds maximum cost {max_cost.normalize()} after precision.{RESET}")
             return None
    elif min_cost > 0:
         lg.warning("Could not perform final cost check after precision adjustment.")


    # --- Success ---
    lg.info(f"{NEON_GREEN}{BRIGHT}>>> Final Calculated Position Size: {final_size.normalize()} {size_unit} <<< {RESET}")
    lg.info(f"{BRIGHT}--- End Position Sizing ---{RESET}")
    return final_size

def place_trade(exchange: ccxt.Exchange, symbol: str, trade_signal: str, position_size: Decimal, market_info: MarketInfo,
                logger: logging.Logger, reduce_only: bool = False, params: Optional[Dict] = None) -> Optional[Dict]:
    """
    Places a market order (buy or sell) using `create_order`.

    - Maps trade signals ("BUY", "SELL", "EXIT_LONG", "EXIT_SHORT") to order sides ("buy", "sell").
    - Handles Bybit V5 specific parameters (category, positionIdx, reduceOnly, timeInForce).
    - Includes retry logic for network/exchange errors and rate limits.
    - Identifies and handles non-retryable order errors (e.g., insufficient funds, invalid parameters).
    - Logs order details clearly.

    Args:
        exchange (ccxt.Exchange): The initialized ccxt.Exchange object.
        symbol (str): The trading symbol (e.g., "BTC/USDT").
        trade_signal (str): The signal driving the trade ("BUY", "SELL", "EXIT_LONG", "EXIT_SHORT").
        position_size (Decimal): The calculated position size (must be positive Decimal).
        market_info (MarketInfo): The standardized MarketInfo dictionary.
        logger (logging.Logger): The logger instance for status messages.
        reduce_only (bool): Set to True for closing orders to ensure they only reduce/close a position.
        params (Optional[Dict]): Optional additional parameters to pass to create_order's `params` argument.

    Returns:
        Optional[Dict]: The order dictionary returned by CCXT upon successful placement, or None if the
                        order fails after retries or due to fatal errors.
    """
    lg = logger
    # Map signal to CCXT side ('buy' or 'sell')
    side_map = {"BUY": "buy", "SELL": "sell", "EXIT_SHORT": "buy", "EXIT_LONG": "sell"}
    side = side_map.get(trade_signal.upper())

    # --- Input Validation ---
    if side is None:
        lg.error(f"Invalid trade signal '{trade_signal}' provided to place_trade. Must be BUY, SELL, EXIT_LONG, or EXIT_SHORT.")
        return None
    if not isinstance(position_size, Decimal) or position_size <= Decimal('0'):
        lg.error(f"Invalid position size provided to place_trade: {position_size}. Must be a positive Decimal.")
        return None

    order_type = 'market' # This bot currently only uses market orders
    is_contract = market_info.get('is_contract', False)
    base_currency = market_info.get('base', 'BASE')
    # Determine size unit for logging
    size_unit = base_currency if market_info.get('spot', False) else "Contracts"

    action_desc = "Close/Reduce" if reduce_only else "Open/Increase"
    market_id = market_info['id'] # Use the exchange-specific market ID

    # --- Prepare Order Arguments ---
    # CCXT typically expects float amount, convert Decimal carefully
    try:
         amount_float = float(position_size)
         # Additional check: ensure float conversion didn't lose too much precision or become zero
         if amount_float <= 1e-15: # Use a small tolerance
             raise ValueError("Position size became zero or negligible after float conversion.")
    except (ValueError, TypeError) as float_err:
         lg.error(f"Failed to convert position size {position_size.normalize()} to valid positive float for API call: {float_err}")
         return None

    order_args = {
        'symbol': market_id, # Use market_id here
        'type': order_type,
        'side': side,
        'amount': amount_float,
    }
    order_params = {} # For exchange-specific parameters

    # --- Bybit V5 Specific Parameters ---
    if 'bybit' in exchange.id.lower() and is_contract:
        try:
            category = market_info.get('contract_type_str', 'Linear').lower()
            if category not in ['linear', 'inverse']:
                 raise ValueError(f"Invalid category '{category}' determined for Bybit order.")
            order_params = {
                'category': category,
                'positionIdx': 0  # Use 0 for one-way mode (required by Bybit V5 for non-hedge mode)
            }
            if reduce_only:
                order_params['reduceOnly'] = True
                # Use IOC for reduceOnly market orders to prevent resting if market moves away quickly
                # (FOK might also work, but IOC is safer if partial fill is acceptable for closing)
                order_params['timeInForce'] = 'IOC' # Immediate Or Cancel
            lg.debug(f"Using Bybit V5 order params: {order_params}")
        except Exception as e:
            lg.error(f"Failed to set Bybit V5 parameters for order: {e}. Order might fail.")
            # Proceed cautiously without params if setting failed

    # Merge any additional custom parameters provided by the caller
    if params:
        order_params.update(params)

    if order_params:
        order_args['params'] = order_params # Add exchange-specific params to the main args

    # Log the trade attempt
    lg.info(f"{BRIGHT}===> Attempting {action_desc} | {side.upper()} {order_type.upper()} Order | {symbol} | Size: {position_size.normalize()} {size_unit} <==={RESET}")
    if order_params: lg.debug(f"  with Params: {order_params}")

    # --- Execute Order with Retries ---
    attempts = 0
    last_exception = None
    while attempts <= MAX_API_RETRIES:
        try:
            lg.debug(f"Executing exchange.create_order (Attempt {attempts + 1}/{MAX_API_RETRIES + 1})...")
            order_result = exchange.create_order(**order_args)

            # Log Success
            order_id = order_result.get('id', 'N/A')
            status = order_result.get('status', 'N/A')
            # Safely format potential Decimal/float/str values from result
            avg_price_str = _safe_market_decimal(order_result.get('average'), 'order_result.average', allow_zero=False)
            filled_amount_str = _safe_market_decimal(order_result.get('filled'), 'order_result.filled', allow_zero=True) # Allow zero filled initially
            log_msg = (
                f"{NEON_GREEN}{action_desc} Order Placed Successfully!{RESET} "
                f"ID: {order_id}, Status: {status}"
            )
            if avg_price_str: log_msg += f", Avg Fill Price: ~{avg_price_str.normalize()}"
            if filled_amount_str: log_msg += f", Filled Amount: {filled_amount_str.normalize()}"
            lg.info(log_msg)
            lg.debug(f"Full order result: {order_result}")
            return order_result # Return the successful order details

        # --- Error Handling with Retries ---
        except ccxt.InsufficientFunds as e:
            last_exception = e
            lg.error(f"{NEON_RED}Order Failed ({action_desc}): Insufficient funds for {symbol} {side} {position_size}. Error: {e}{RESET}")
            return None # Non-retryable
        except ccxt.InvalidOrder as e:
            last_exception = e
            lg.error(f"{NEON_RED}Order Failed ({action_desc}): Invalid order parameters for {symbol}. Error: {e}{RESET}")
            lg.error(f"  Order arguments used: {order_args}")
            # Add hints based on common causes
            err_lower = str(e).lower()
            if "minimum" in err_lower or "too small" in err_lower or "lower than limit" in err_lower:
                 lg.error(f"  >> Hint: Check size/cost ({position_size.normalize()}) against market minimum limits (MinAmount: {market_info.get('min_amount_decimal')}, MinCost: {market_info.get('min_cost_decimal')}).")
            elif "precision" in err_lower or "lot size" in err_lower or "step size" in err_lower:
                 lg.error(f"  >> Hint: Check size ({position_size.normalize()}) against amount precision step ({market_info.get('amount_precision_step_decimal')}).")
            elif "exceed" in err_lower or "too large" in err_lower or "greater than limit" in err_lower:
                 lg.error(f"  >> Hint: Check size/cost ({position_size.normalize()}) against market maximum limits (MaxAmount: {market_info.get('max_amount_decimal')}, MaxCost: {market_info.get('max_cost_decimal')}).")
            elif "reduce only" in err_lower:
                 lg.error(f"  >> Hint: Reduce-only order failed. Check if position size is correct or if order would increase position.")
            return None # Non-retryable
        except ccxt.ExchangeError as e:
            last_exception = e
            err_code_str = str(getattr(e, 'code', '') or getattr(e, 'retCode', ''))
            lg.error(f"{NEON_RED}Order Failed ({action_desc}): Exchange error placing order for {symbol}. Error: {e} (Code: {err_code_str}){RESET}")

            # Check for known fatal Bybit error codes related to orders
            # Based on Bybit V5 API docs and common issues
            fatal_order_codes = [
                '10001', # Parameter error
                '10004', # Sign check error
                '110007',# Qty exceed max limit per order
                '110013',# Parameter error (generic)
                '110014',# Qty must be greater than 0
                '110017',# Order price/qty violates contract rules (precision?)
                '110025',# Position idx not match position mode (can happen if mode changed externally)
                '110040',# Order cost exceed limit
                '30086', # reduceOnly check failed - TIF is not IOC/FOK or size issue
                '3303001',# Invalid symbol
                '3303005',# Price is too high/low compared to mark price (for limit orders, less likely for market)
                '3400060',# Order qty exceeds risk limit level
                '3400088',# The order quantity is invalid (lot size?)
            ]
            # Common fatal message fragments
            fatal_messages = ["invalid parameter", "precision", "exceed limit", "risk limit", "invalid symbol", "reduce only check failed", "lot size"]

            if err_code_str in fatal_order_codes or any(msg in str(e).lower() for msg in fatal_messages):
                lg.error(f"{NEON_RED} >> Hint: This appears to be a NON-RETRYABLE order error.{RESET}")
                return None # Non-retryable

            # Assume other exchange errors might be temporary and retry if attempts remain
            if attempts >= MAX_API_RETRIES:
                 lg.error(f"{NEON_RED}Maximum retries exceeded for ExchangeError placing order. Last error: {last_exception}{RESET}")
                 return None

        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e:
            last_exception = e
            lg.warning(f"{NEON_YELLOW}Network error placing order for {symbol}: {e}. Retry {attempts + 1}/{MAX_API_RETRIES + 1}...{RESET}")
            if attempts >= MAX_API_RETRIES:
                lg.error(f"{NEON_RED}Maximum retries exceeded for NetworkError placing order. Last error: {last_exception}{RESET}")
                return None

        except ccxt.RateLimitExceeded as e:
            last_exception = e
            wait_time = RETRY_DELAY_SECONDS * 3
            lg.warning(f"{NEON_YELLOW}Rate limit exceeded placing order for {symbol}: {e}. Waiting {wait_time}s...{RESET}")
            time.sleep(wait_time)
            continue # Continue loop without incrementing attempts

        except ccxt.AuthenticationError as e:
             last_exception = e
             lg.critical(f"{NEON_RED}Authentication Error placing order: {e}. Check API Key/Secret/Permissions. Stopping order placement.{RESET}")
             return None # Fatal error for this operation

        except Exception as e:
            last_exception = e
            lg.error(f"{NEON_RED}Unexpected error placing order for {symbol}: {e}{RESET}", exc_info=True)
            return None # Stop on unexpected errors

        # Increment attempt counter (only if not a rate limit wait) and delay before retrying
        attempts += 1
        if attempts <= MAX_API_RETRIES:
            time.sleep(RETRY_DELAY_SECONDS * attempts) # Exponential backoff

    lg.error(f"{NEON_RED}Failed to place {action_desc} order for {symbol} after {MAX_API_RETRIES + 1} attempts. Last error: {last_exception}{RESET}")
    return None

def _set_position_protection(exchange: ccxt.Exchange, symbol: str, market_info: MarketInfo, position_info: PositionInfo, logger: logging.Logger,
                             stop_loss_price: Optional[Decimal] = None, take_profit_price: Optional[Decimal] = None,
                             trailing_stop_distance: Optional[Decimal] = None, tsl_activation_price: Optional[Decimal] = None) -> bool:
    """
    Internal helper: Sets Stop Loss (SL), Take Profit (TP), and/or Trailing Stop Loss (TSL)
    for an existing position using Bybit's V5 private API endpoint `/v5/position/set-trading-stop`.

    **Important:** This uses a direct API call (`private_post`) and relies on Bybit's specific
    V5 endpoint and parameters. It might break if Bybit changes its API structure. CCXT's
    standard methods might not fully support Bybit's V5 combined TSL/SL/TP parameters.

    Handles parameter validation (e.g., SL/TP/Activation relative to entry), price formatting
    to market precision, and API response checking. TSL settings take precedence over fixed SL.

    Args:
        exchange (ccxt.Exchange): The initialized ccxt.Exchange object.
        symbol (str): The trading symbol (e.g., "BTC/USDT").
        market_info (MarketInfo): The standardized MarketInfo dictionary.
        position_info (PositionInfo): The standardized PositionInfo dictionary for the open position.
        logger (logging.Logger): The logger instance for status messages.
        stop_loss_price (Optional[Decimal]): Desired fixed SL price. Set to 0 or None to clear/ignore.
        take_profit_price (Optional[Decimal]): Desired fixed TP price. Set to 0 or None to clear/ignore.
        trailing_stop_distance (Optional[Decimal]): Desired TSL distance (in price units). Set to 0 or None to clear/ignore. Must be positive if setting TSL.
        tsl_activation_price (Optional[Decimal]): Price at which TSL should activate. Required if distance > 0.

    Returns:
        bool: True if the protection was set/updated successfully via API or if no change was needed.
              False if validation fails, API call fails after retries, or a critical error occurs.
    """
    lg = logger
    endpoint = '/v5/position/set-trading-stop' # Bybit V5 endpoint

    # --- Input and State Validation ---
    if not market_info.get('is_contract', False):
        lg.warning(f"Protection setting skipped for {symbol}: Not a contract market.")
        return False # Cannot set SL/TP/TSL on spot
    if not position_info:
        lg.error(f"Protection setting failed for {symbol}: Missing position information.")
        return False
    pos_side = position_info.get('side')
    entry_price_str = position_info.get('entryPrice')
    if pos_side not in ['long', 'short']:
        lg.error(f"Protection setting failed for {symbol}: Invalid position side ('{pos_side}').")
        return False
    try:
        if entry_price_str is None: raise ValueError("Missing entry price")
        entry_price = Decimal(str(entry_price_str))
        if entry_price <= 0: raise ValueError("Entry price must be positive")
    except (ValueError, InvalidOperation, TypeError) as e:
        lg.error(f"Protection setting failed for {symbol}: Invalid or missing entry price ('{entry_price_str}'): {e}")
        return False
    try:
        price_tick = market_info['price_precision_step_decimal']
        if price_tick is None or price_tick <= 0: raise ValueError("Invalid price tick size")
    except (KeyError, ValueError, TypeError) as e:
         lg.error(f"Protection setting failed for {symbol}: Could not get valid price precision from market info: {e}")
         return False

    params_to_set: Dict[str, Any] = {} # Parameters to send in the API request
    log_parts: List[str] = [f"{BRIGHT}Attempting to set protection for {symbol} ({pos_side.upper()} @ {entry_price.normalize()}):{RESET}"]
    any_protection_requested = False # Flag to check if any valid protection was requested
    set_tsl_active = False # Flag if TSL distance > 0 is being set

    # --- Format and Validate Protection Parameters ---
    try:
        # Helper to format price to exchange precision string
        def format_price_param(price_decimal: Optional[Decimal], param_name: str) -> Optional[str]:
            """Formats price to string, respecting exchange precision. Returns None if invalid."""
            if price_decimal is None: return None
            # Allow "0" to clear protection
            if price_decimal == 0: return "0"
            # Reject negative prices immediately
            if price_decimal < 0:
                lg.warning(f"Invalid negative price {price_decimal.normalize()} provided for {param_name}. Ignoring.")
                return None
            try:
                # Use CCXT's price_to_precision for correct rounding/truncating
                formatted_str = exchange.price_to_precision(symbol=market_info['symbol'], price=float(price_decimal))
                # Final check: ensure formatted price is still positive after formatting
                if Decimal(formatted_str) > 0:
                     return formatted_str
                else:
                     lg.warning(f"Formatted {param_name} '{formatted_str}' resulted in zero or negative value. Ignoring.")
                     return None
            except Exception as e:
                lg.error(f"Failed to format {param_name} value {price_decimal.normalize()} to exchange precision: {e}.")
                return None

        # --- Trailing Stop Loss (TSL) ---
        # Bybit requires TSL distance (trailingStop) and activation price (activePrice)
        if isinstance(trailing_stop_distance, Decimal):
            any_protection_requested = True
            if trailing_stop_distance > 0: # Setting an active TSL
                # Ensure distance is at least one tick
                min_valid_distance = max(trailing_stop_distance, price_tick)

                if not isinstance(tsl_activation_price, Decimal) or tsl_activation_price <= 0:
                    lg.error(f"TSL request failed: Valid positive activation price ({tsl_activation_price}) is required when TSL distance ({min_valid_distance.normalize()}) > 0.")
                else:
                    # Validate activation price makes sense relative to entry (must be beyond entry)
                    is_valid_activation = (pos_side == 'long' and tsl_activation_price > entry_price) or \
                                          (pos_side == 'short' and tsl_activation_price < entry_price)
                    if not is_valid_activation:
                        lg.error(f"TSL request failed: Activation price {tsl_activation_price.normalize()} must be beyond entry price {entry_price.normalize()} for a {pos_side} position.")
                    else:
                        fmt_distance = format_price_param(min_valid_distance, "TSL Distance")
                        fmt_activation = format_price_param(tsl_activation_price, "TSL Activation Price")

                        if fmt_distance and fmt_activation:
                            params_to_set['trailingStop'] = fmt_distance
                            params_to_set['activePrice'] = fmt_activation
                            log_parts.append(f"  - Setting TSL: Distance={fmt_distance}, Activation={fmt_activation}")
                            set_tsl_active = True # Mark TSL as being actively set
                        else:
                            lg.error(f"TSL request failed: Could not format TSL parameters (Distance: {fmt_distance}, Activation: {fmt_activation}). Check precision/values.")

            elif trailing_stop_distance == 0: # Clearing TSL
                params_to_set['trailingStop'] = "0"
                # Also clear activation price when clearing TSL distance for Bybit
                params_to_set['activePrice'] = "0"
                log_parts.append("  - Clearing TSL (Distance and Activation Price set to 0)")
                # set_tsl_active remains False

        # --- Fixed Stop Loss (SL) ---
        # Can only set fixed SL if TSL is *not* being actively set (Bybit limitation)
        if not set_tsl_active:
            if isinstance(stop_loss_price, Decimal):
                any_protection_requested = True
                if stop_loss_price > 0: # Setting an active SL
                    # Validate SL price makes sense relative to entry (must be beyond entry)
                    is_valid_sl = (pos_side == 'long' and stop_loss_price < entry_price) or \
                                  (pos_side == 'short' and stop_loss_price > entry_price)
                    if not is_valid_sl:
                        lg.error(f"Fixed SL request failed: SL price {stop_loss_price.normalize()} must be beyond entry price {entry_price.normalize()} for a {pos_side} position.")
                    else:
                        fmt_sl = format_price_param(stop_loss_price, "Stop Loss")
                        if fmt_sl:
                            params_to_set['stopLoss'] = fmt_sl
                            log_parts.append(f"  - Setting Fixed SL: {fmt_sl}")
                        else:
                            lg.error(f"Fixed SL request failed: Could not format SL price {stop_loss_price.normalize()}.")
                elif stop_loss_price == 0: # Clearing SL
                    # Only send "0" if SL field wasn't already populated by TSL logic (which it shouldn't be if set_tsl_active is False)
                    if 'stopLoss' not in params_to_set:
                         params_to_set['stopLoss'] = "0"
                         log_parts.append("  - Clearing Fixed SL (set to 0)")
        elif isinstance(stop_loss_price, Decimal) and stop_loss_price > 0:
             # TSL is active, cannot set fixed SL
             lg.warning(f"Ignoring fixed SL request ({stop_loss_price.normalize()}) because active TSL is being set.")


        # --- Fixed Take Profit (TP) ---
        # TP can usually be set alongside SL or TSL
        if isinstance(take_profit_price, Decimal):
            any_protection_requested = True
            if take_profit_price > 0: # Setting an active TP
                # Validate TP price makes sense relative to entry (must be beyond entry)
                is_valid_tp = (pos_side == 'long' and take_profit_price > entry_price) or \
                              (pos_side == 'short' and take_profit_price < entry_price)
                if not is_valid_tp:
                    lg.error(f"Fixed TP request failed: TP price {take_profit_price.normalize()} must be beyond entry price {entry_price.normalize()} for a {pos_side} position.")
                else:
                    fmt_tp = format_price_param(take_profit_price, "Take Profit")
                    if fmt_tp:
                        params_to_set['takeProfit'] = fmt_tp
                        log_parts.append(f"  - Setting Fixed TP: {fmt_tp}")
                    else:
                        lg.error(f"Fixed TP request failed: Could not format TP price {take_profit_price.normalize()}.")
            elif take_profit_price == 0: # Clearing TP
                 if 'takeProfit' not in params_to_set:
                     params_to_set['takeProfit'] = "0"
                     log_parts.append("  - Clearing Fixed TP (set to 0)")

    except Exception as fmt_err:
        lg.error(f"Error during protection parameter formatting/validation: {fmt_err}", exc_info=True)
        return False

    # --- Check if any valid parameters were actually prepared for the API call ---
    if not params_to_set:
        if any_protection_requested:
            lg.warning(f"{NEON_YELLOW}No valid protection parameters to set for {symbol} after formatting/validation. No API call made.{RESET}")
            # Return False because the requested action couldn't be fulfilled due to validation errors
            return False
        else:
            lg.debug(f"No protection changes requested or needed for {symbol}. No API call required.")
            return True # Success, as no action was needed

    # --- Prepare Final API Parameters ---
    category = market_info.get('contract_type_str', 'Linear').lower()
    market_id = market_info['id']
    # Get position index (should be 0 for one-way mode)
    position_idx = 0 # Default to one-way mode
    try:
        # Attempt to get positionIdx from position info if available (might indicate hedge mode)
        pos_idx_val = position_info.get('info', {}).get('positionIdx')
        if pos_idx_val is not None:
            position_idx = int(pos_idx_val)
            if position_idx != 0:
                 lg.warning(f"Detected positionIdx={position_idx}. Ensure this matches your Bybit account mode (One-Way vs Hedge). Using detected index.")
    except (ValueError, TypeError):
        lg.debug("Could not parse positionIdx from position info, defaulting to 0 (one-way mode).")
        position_idx = 0

    # Construct the final parameters dictionary for the API call
    final_api_params = {
        'category': category,
        'symbol': market_id,
        'tpslMode': 'Full', # Use 'Full' for setting SL/TP on the entire position (Partial not handled here)
        # Common trigger prices: LastPrice, MarkPrice, IndexPrice
        'slTriggerBy': 'LastPrice', # Trigger SL based on Last Price (configurable maybe later)
        'tpTriggerBy': 'LastPrice', # Trigger TP based on Last Price
        # Order types when triggered: Market, Limit (Limit requires slLimitPrice/tpLimitPrice)
        'slOrderType': 'Market',    # Use Market order when SL is triggered
        'tpOrderType': 'Market',    # Use Market order when TP is triggered
        'positionIdx': position_idx # Specify position index (0 for one-way)
    }
    final_api_params.update(params_to_set) # Add the specific SL/TP/TSL values

    # Log the attempt only if there are parameters to set
    lg.info("\n".join(log_parts)) # Log what is being attempted
    lg.debug(f"  Final API parameters for {endpoint}: {final_api_params}")

    # --- Execute API Call with Retries ---
    attempts = 0
    last_exception = None
    while attempts <= MAX_API_RETRIES:
        try:
            lg.debug(f"Executing private_post to {endpoint} (Attempt {attempts + 1}/{MAX_API_RETRIES + 1})...")
            # Use exchange.private_post for endpoints not directly mapped by CCXT standard methods
            response = exchange.private_post(endpoint, params=final_api_params)
            lg.debug(f"Set protection raw API response: {response}")

            # --- Check Bybit V5 Response ---
            ret_code_str = None
            ret_msg = "Unknown message"
            if isinstance(response, dict):
                 ret_code_str = str(response.get('retCode', response.get('code'))) # Check both keys
                 ret_msg = response.get('retMsg', response.get('message', 'Unknown Bybit API message'))

            if ret_code_str == '0':
                 # Check message for "not modified" cases which are still success
                 # Bybit messages can vary, check common fragments
                 no_change_msgs = ["not modified", "no need to modify", "parameter not change", "order is not modified"]
                 if any(m in ret_msg.lower() for m in no_change_msgs):
                     lg.info(f"{NEON_YELLOW}Protection parameters already set or no change needed. (Message: {ret_msg}){RESET}")
                 else:
                     lg.info(f"{NEON_GREEN}Protection parameters successfully set/updated for {symbol}.{RESET}")
                 return True # Success

            else:
                 # Log the specific Bybit error and raise ExchangeError for retry or handling
                 error_message = f"Bybit API error setting protection: {ret_msg} (Code: {ret_code_str})"
                 lg.error(f"{NEON_RED}{error_message}{RESET}")
                 raise ccxt.ExchangeError(error_message) # Let retry logic handle it

        # --- Standard CCXT Error Handling with Retries ---
        except ccxt.ExchangeError as e: # Catches re-raised Bybit errors or other CCXT exchange errors
            last_exception = e
            err_code_str = str(getattr(e, 'code', '') or getattr(e, 'retCode', ''))
            err_str = str(e).lower()
            lg.warning(f"{NEON_YELLOW}Exchange error setting protection for {symbol}: {e}. Retry {attempts + 1}/{MAX_API_RETRIES + 1}...{RESET}")

            # Check for known fatal/non-retryable error codes/messages
            # Based on Bybit V5 API docs and common issues for set-trading-stop
            fatal_protect_codes = [
                '10001', # Parameter error
                '10002', # API key invalid
                '110013',# Parameter error (generic)
                '110036',# SL price cannot be higher/lower than entry/mark price (depending on trigger)
                '110043',# Position status is not normal (e.g., closing, liquidating)
                '110084',# SL price invalid / out of range / precision error
                '110085',# TP price invalid / out of range / precision error
                '110086',# TP price cannot be lower/higher than entry/mark price
                '110103',# TSL activation price invalid
                '110104',# TSL distance invalid (e.g., too small)
                '110110',# TP/SL cannot be set for Spot margin trading (if attempted)
                '3400045',# Set margin mode failed (indirectly related)
            ]
            fatal_messages = ["invalid parameter", "invalid price", "cannot be higher", "cannot be lower", "position status", "precision error", "activation price", "distance invalid"]

            if err_code_str in fatal_protect_codes or any(msg in err_str for msg in fatal_messages):
                 lg.error(f"{NEON_RED} >> Hint: This appears to be a NON-RETRYABLE protection setting error. Aborting protection set.{RESET}")
                 return False # Fatal error for this operation

            if attempts >= MAX_API_RETRIES:
                 lg.error(f"{NEON_RED}Maximum retries exceeded for ExchangeError setting protection. Last error: {last_exception}{RESET}")
                 return False

        except (ccxt.NetworkError, ccxt.RequestTimeout, requests.exceptions.RequestException) as e:
            last_exception = e
            lg.warning(f"{NEON_YELLOW}Network error setting protection for {symbol}: {e}. Retry {attempts + 1}/{MAX_API_RETRIES + 1}...{RESET}")
            if attempts >= MAX_API_RETRIES:
                lg.error(f"{NEON_RED}Maximum retries exceeded for NetworkError setting protection. Last error: {last_exception}{RESET}")
                return False

        except ccxt.RateLimitExceeded as e:
            last_exception = e
            wait_time = RETRY_DELAY_SECONDS * 3
            lg.warning(f"{NEON_YELLOW}Rate limit exceeded setting protection for {symbol}: {e}. Waiting {wait_time}s...{RESET}")
            time.sleep(wait_time)
            continue # Continue loop without incrementing attempts

        except ccxt.AuthenticationError as e:
            last_exception = e
            lg.critical(f"{NEON_RED}Authentication Error setting protection: {e}. Check API Key/Secret/Permissions. Stopping protection set.{RESET}")
            return False # Fatal error for this operation

        except Exception as e:
            last_exception = e
            lg.error(f"{NEON_RED}Unexpected error setting protection for {symbol} (Attempt {attempts + 1}): {e}{RESET}", exc_info=True)
            # Unexpected errors are likely fatal for this operation
            return False

        # Increment attempt counter and delay before retrying (only for retryable errors)
        attempts += 1
        time.sleep(RETRY_DELAY_SECONDS * attempts) # Exponential backoff

    lg.error(f"{NEON_RED}Failed to set protection for {symbol} after {MAX_API_RETRIES + 1} attempts. Last error: {last_exception}{RESET}")
    return False

def set_trailing_stop_loss(exchange: ccxt.Exchange, symbol: str, market_info: MarketInfo, position_info: PositionInfo, config: Dict[str, Any],
                             logger: logging.Logger, take_profit_price: Optional[Decimal] = None) -> bool:
    """
    Calculates Trailing Stop Loss (TSL) parameters based on configuration settings
    (callback rate, activation percentage) and the current position's entry price.
    It then calls the internal `_set_position_protection` function to apply the TSL
    and optionally a fixed Take Profit.

    Args:
        exchange (ccxt.Exchange): The initialized ccxt.Exchange object.
        symbol (str): The trading symbol.
        market_info (MarketInfo): The standardized MarketInfo dictionary.
        position_info (PositionInfo): The standardized PositionInfo dictionary for the open position.
        config (Dict[str, Any]): The main configuration dictionary containing protection settings.
        logger (logging.Logger): The logger instance.
        take_profit_price (Optional[Decimal]): An optional fixed Take Profit price (Decimal) to set simultaneously.
                                               Set to 0 or None to clear/ignore existing TP.

    Returns:
        bool: True if the TSL (and optional TP) was successfully calculated and the API call
              to set protection was initiated successfully (returned True), False otherwise.
    """
    lg = logger
    prot_cfg = config.get("protection", {}) # Get protection sub-dictionary

    # --- Input Validation ---
    if not market_info or not position_info:
        lg.error(f"TSL calculation failed for {symbol}: Missing market or position info.")
        return False
    pos_side = position_info.get('side')
    entry_price_str = position_info.get('entryPrice')
    if pos_side not in ['long', 'short']:
        lg.error(f"TSL calculation failed for {symbol}: Invalid position side ('{pos_side}').")
        return False

    try:
        # Extract parameters and convert to Decimal
        if entry_price_str is None: raise ValueError("Missing entry price")
        entry_price = Decimal(str(entry_price_str))
        callback_rate = Decimal(str(prot_cfg["trailing_stop_callback_rate"])) # e.g., 0.005 for 0.5%
        activation_percentage = Decimal(str(prot_cfg["trailing_stop_activation_percentage"])) # e.g., 0.003 for 0.3%
        price_tick = market_info['price_precision_step_decimal']

        # Validate parameters
        if not (entry_price > 0 and callback_rate > 0 and activation_percentage >= 0 and price_tick and price_tick > 0):
             raise ValueError("Invalid input values (entry, callback rate > 0, activation % >= 0, or positive tick size).")

    except (KeyError, ValueError, InvalidOperation, TypeError) as e:
        lg.error(f"TSL calculation failed for {symbol}: Invalid configuration or market/position info: {e}")
        lg.debug(f"  Problematic Inputs: Entry='{entry_price_str}', Config={prot_cfg}, Tick={market_info.get('price_precision_step_decimal')}")
        return False

    # --- Calculate TSL Activation Price and Distance ---
    try:
        lg.info(f"Calculating TSL for {symbol} ({pos_side.upper()}): Entry={entry_price.normalize()}, Act%={activation_percentage:.3%}, CB%={callback_rate:.3%}")

        # 1. Calculate Activation Price
        activation_offset = entry_price * activation_percentage
        raw_activation_price = (entry_price + activation_offset) if pos_side == 'long' else (entry_price - activation_offset)

        # Quantize activation price to the nearest tick (away from entry)
        if pos_side == 'long':
            # Round up for long activation to ensure it's strictly beyond entry
            quantized_activation_price = (raw_activation_price / price_tick).quantize(Decimal('1'), ROUND_UP) * price_tick
            # Ensure activation is strictly greater than entry by at least one tick
            tsl_activation_price = max(quantized_activation_price, entry_price + price_tick)
        else: # Short position
            # Round down for short activation to ensure it's strictly beyond entry
            quantized_activation_price = (raw_activation_price / price_tick).quantize(Decimal('1'), ROUND_DOWN) * price_tick
            # Ensure activation is strictly less than entry by at least one tick
            tsl_activation_price = min(quantized_activation_price, entry_price - price_tick)

        # Final check on activation price validity
        if tsl_activation_price <= 0 or \
           (pos_side == 'long' and tsl_activation_price <= entry_price) or \
           (pos_side == 'short' and tsl_activation_price >= entry_price):
            lg.error(f"TSL calculation failed: Calculated Activation Price ({tsl_activation_price.normalize()}) is invalid relative to entry ({entry_price.normalize()}).")
            return False

        # 2. Calculate Trailing Distance (based on activation price and callback rate)
        # Distance = Activation Price * Callback Rate
        # Use abs() in case activation price somehow became negative (shouldn't happen)
        raw_trailing_distance = abs(tsl_activation_price) * callback_rate

        # Quantize distance UP to the nearest tick and ensure it's at least one tick
        tsl_trailing_distance = max((raw_trailing_distance / price_tick).quantize(Decimal('1'), ROUND_UP) * price_tick, price_tick)

        if tsl_trailing_distance <= 0:
            lg.error(f"TSL calculation failed: Calculated Trailing Distance ({tsl_trailing_distance.normalize()}) is zero or negative.")
            return False

        lg.info(f"  => Calculated TSL Activation Price: {tsl_activation_price.normalize()}")
        lg.info(f"  => Calculated TSL Trailing Distance: {tsl_trailing_distance.normalize()}")
        tp_action = "None"
        if isinstance(take_profit_price, Decimal):
             tp_action = f"{take_profit_price.normalize()}" if take_profit_price != 0 else "Clear TP"
        lg.info(f"  => Setting alongside Fixed TP: {tp_action}")

        # --- Call Internal Function to Set Protection ---
        # Pass None for fixed stop_loss_price as TSL takes precedence when distance > 0
        return _set_position_protection(
            exchange=exchange,
            symbol=symbol,
            market_info=market_info,
            position_info=position_info,
            logger=lg,
            stop_loss_price=None, # TSL overrides fixed SL when active
            take_profit_price=take_profit_price, # Pass through TP setting/clearing
            trailing_stop_distance=tsl_trailing_distance,
            tsl_activation_price=tsl_activation_price
        )

    except Exception as e:
        lg.error(f"{NEON_RED}Unexpected error during TSL calculation or setting: {e}{RESET}", exc_info=True)
        return False

# --- Volumatic Trend + OB Strategy Implementation ---
class VolumaticOBStrategy:
    """
    Implements the core logic for the Volumatic Trend and Pivot Order Block strategy.

    Responsibilities:
    - Calculates Volumatic Trend indicators (EMAs, ATR Bands, Volume Normalization).
    - Identifies Pivot Highs/Lows based on configuration.
    - Creates Order Blocks (OBs) from pivots using configured source (Wicks/Body).
    - Manages the state of OBs (active, violated, extends).
    - Prunes the list of active OBs to a maximum number per type.
    - Returns structured analysis results including the processed DataFrame.
    """
    def __init__(self, config: Dict[str, Any], market_info: MarketInfo, logger: logging.Logger):
        """
        Initializes the strategy engine with parameters from the config.

        Args:
            config (Dict[str, Any]): The main configuration dictionary.
            market_info (MarketInfo): The standardized MarketInfo dictionary.
            logger (logging.Logger): The logger instance for this strategy instance.

        Raises:
            ValueError: If critical configuration parameters are invalid or missing.
        """
        self.config = config
        self.market_info = market_info
        self.logger = logger
        self.lg = logger # Alias for convenience

        strategy_cfg = config.get("strategy_params", {})
        # Protection config not directly used here but could be for future features

        # Load strategy parameters (already validated by load_config)
        try:
            self.vt_length = int(strategy_cfg["vt_length"])
            self.vt_atr_period = int(strategy_cfg["vt_atr_period"])
            self.vt_vol_ema_length = int(strategy_cfg["vt_vol_ema_length"])
            self.vt_atr_multiplier = Decimal(str(strategy_cfg["vt_atr_multiplier"]))

            self.ob_source = str(strategy_cfg["ob_source"]) # "Wicks" or "Body"
            self.ph_left = int(strategy_cfg["ph_left"])
            self.ph_right = int(strategy_cfg["ph_right"])
            self.pl_left = int(strategy_cfg["pl_left"])
            self.pl_right = int(strategy_cfg["pl_right"])
            self.ob_extend = bool(strategy_cfg["ob_extend"])
            self.ob_max_boxes = int(strategy_cfg["ob_max_boxes"])

            # Basic sanity checks on loaded values
            if not (self.vt_length > 0 and self.vt_atr_period > 0 and self.vt_vol_ema_length > 0 and \
                    self.vt_atr_multiplier > 0 and self.ph_left > 0 and self.ph_right > 0 and \
                    self.pl_left > 0 and self.pl_right > 0 and self.ob_max_boxes > 0):
                raise ValueError("One or more strategy parameters are invalid (must be positive).")
            if self.ob_source not in ["Wicks", "Body"]:
                 raise ValueError(f"Invalid ob_source '{self.ob_source}'. Must be 'Wicks' or 'Body'.")

        except (KeyError, ValueError, TypeError) as e:
            self.lg.error(f"FATAL: Failed to initialize VolumaticOBStrategy due to invalid config: {e}")
            self.lg.debug(f"Strategy Config received: {strategy_cfg}")
            raise ValueError(f"Strategy initialization failed: {e}") from e

        # Initialize Order Block storage
        self.bull_boxes: List[OrderBlock] = []
        self.bear_boxes: List[OrderBlock] = []

        # Calculate minimum data length required based on longest lookback period
        # EMA needs length, SWMA needs 4, ATR needs period, Vol Norm needs length
        # Pivots need left + right + 1
        # Add buffer for indicator stabilization (e.g., 50 candles)
        required_for_vt = max(self.vt_length * 2, self.vt_atr_period, self.vt_vol_ema_length) # Use *2 for EMA stability buffer
        required_for_pivots = max(self.ph_left + self.ph_right + 1, self.pl_left + self.pl_right + 1)
        stabilization_buffer = 50
        self.min_data_len = max(required_for_vt, required_for_pivots) + stabilization_buffer

        # Log initialized parameters
        self.lg.info(f"{NEON_CYAN}--- Initializing VolumaticOB Strategy Engine ({market_info['symbol']}) ---{RESET}")
        self.lg.info(f"  VT Params: Length={self.vt_length}, ATR Period={self.vt_atr_period}, Vol EMA Length={self.vt_vol_ema_length}, ATR Multiplier={self.vt_atr_multiplier.normalize()}")
        self.lg.info(f"  OB Params: Source='{self.ob_source}', PH Lookback={self.ph_left}/{self.ph_right}, PL Lookback={self.pl_left}/{self.pl_right}, Extend OBs={self.ob_extend}, Max Active OBs={self.ob_max_boxes}")
        self.lg.info(f"  Minimum Historical Data Required: ~{self.min_data_len} candles")

        # Warning if required data exceeds typical API limits significantly
        if self.min_data_len > BYBIT_API_KLINE_LIMIT + 10: # Add small buffer to limit check
            self.lg.warning(f"{NEON_YELLOW}CONFIGURATION NOTE:{RESET} Strategy requires {self.min_data_len} candles, which might exceed the API fetch limit ({BYBIT_API_KLINE_LIMIT}) in a single request. "
                          f"Ensure 'fetch_limit' in config.json is sufficient or consider reducing long lookback periods (vt_atr_period, vt_vol_ema_length).")

    def _ema_swma(self, series: pd.Series, length: int) -> pd.Series:
        """
        Calculates EMA(SWMA(series, 4), length).

        SWMA(4) uses weights [1, 2, 2, 1] / 6. This combination provides smoothing.
        Handles NaN inputs gracefully. Uses float internally for performance.

        Args:
            series (pd.Series): The input Pandas Series (typically 'close' prices as float).
            length (int): The length for the final EMA calculation.

        Returns:
            pd.Series: A Pandas Series containing the calculated indicator (as float).
        """
        if not isinstance(series, pd.Series) or len(series) < 4 or length <= 0:
            return pd.Series(np.nan, index=series.index, dtype=float) # Return NaNs if input is invalid

        # Ensure numeric type (already done in update, but double check)
        numeric_series = pd.to_numeric(series, errors='coerce')
        if numeric_series.isnull().all(): # Check if all values are NaN after conversion
            return pd.Series(np.nan, index=series.index, dtype=float)

        # Calculate SWMA(4) using rolling apply with dot product
        # Weights: [1, 2, 2, 1] / 6
        weights = np.array([1.0, 2.0, 2.0, 1.0]) / 6.0
        # min_periods=4 ensures we only calculate where 4 data points are available
        swma = numeric_series.rolling(window=4, min_periods=4).apply(lambda x: np.dot(x, weights), raw=True)

        # Calculate EMA of the SWMA result using pandas_ta
        # fillna=np.nan prevents forward-filling issues if EMA starts later
        ema_of_swma = ta.ema(swma, length=length, fillna=np.nan)
        return ema_of_swma # Returns float Series

    def _find_pivots(self, series: pd.Series, left_bars: int, right_bars: int, is_high: bool) -> pd.Series:
        """
        Identifies Pivot Highs or Pivot Lows in a series.

        A Pivot High is a value strictly higher than `left_bars` values to its left
        and `right_bars` values to its right.
        A Pivot Low is a value strictly lower than `left_bars` values to its left
        and `right_bars` values to its right.
        Uses strict inequality ('>' or '<'). Handles NaNs. Uses float internally.

        Args:
            series (pd.Series): The Pandas Series (float) to search for pivots (e.g., 'high' or 'low').
            left_bars (int): The number of bars to look back to the left (must be >= 1).
            right_bars (int): The number of bars to look forward to the right (must be >= 1).
            is_high (bool): True to find Pivot Highs, False to find Pivot Lows.

        Returns:
            pd.Series: A boolean Pandas Series, True where a pivot point is identified.
        """
        if not isinstance(series, pd.Series) or series.empty or left_bars < 1 or right_bars < 1:
            return pd.Series(False, index=series.index, dtype=bool) # Return all False if input invalid

        # Ensure numeric type
        num_series = pd.to_numeric(series, errors='coerce')
        if num_series.isnull().all():
            return pd.Series(False, index=series.index, dtype=bool)

        # Initialize all points as potential pivots (where value is not NaN)
        pivot_conditions = num_series.notna()

        # Check left bars: current >(or <) previous bars
        for i in range(1, left_bars + 1):
            shifted = num_series.shift(i)
            if is_high:
                pivot_conditions &= (num_series > shifted)
            else:
                pivot_conditions &= (num_series < shifted)
            # Handle NaNs introduced by shift or in original data
            pivot_conditions = pivot_conditions.fillna(False)


        # Check right bars: current >(or <) future bars
        for i in range(1, right_bars + 1):
            shifted = num_series.shift(-i)
            if is_high:
                pivot_conditions &= (num_series > shifted)
            else:
                pivot_conditions &= (num_series < shifted)
            # Handle NaNs introduced by shift or in original data
            pivot_conditions = pivot_conditions.fillna(False)

        # Final fillna for any remaining edge cases
        return pivot_conditions.fillna(False)

    def update(self, df_input: pd.DataFrame) -> StrategyAnalysisResults:
        """
        Processes historical OHLCV data to calculate indicators and manage Order Blocks.

        Steps:
        1. Validates input DataFrame.
        2. Converts relevant columns to float for TA library compatibility.
        3. Calculates indicators: ATR, Volumatic EMAs, Trend, Bands, Volume Normalization, Pivots.
        4. Converts calculated float indicators back to Decimal format in the main DataFrame.
        5. Cleans the final DataFrame (drops rows with essential NaNs).
        6. Identifies new Order Blocks based on pivots and configuration.
        7. Updates existing Order Blocks (checks for violations, extends if configured).
        8. Prunes active Order Blocks to `ob_max_boxes`.
        9. Compiles and returns the `StrategyAnalysisResults`.

        Args:
            df_input (pd.DataFrame): The input Pandas DataFrame containing OHLCV data (index=Timestamp,
                                     columns including 'open', 'high', 'low', 'close', 'volume' as Decimals).

        Returns:
            StrategyAnalysisResults: A TypedDict containing the processed DataFrame,
                                     current trend, active OBs, and other key indicator values for the latest candle.
                                     Returns default/empty results if processing fails critically.
        """
        symbol = self.market_info.get('symbol', 'UnknownSymbol')
        # Prepare a default/empty result structure for failure cases
        empty_results = StrategyAnalysisResults(
            dataframe=pd.DataFrame(), last_close=Decimal('0'), current_trend_up=None,
            trend_just_changed=False, active_bull_boxes=[], active_bear_boxes=[],
            vol_norm_int=None, atr=None, upper_band=None, lower_band=None
        )

        if df_input.empty:
            self.lg.error(f"Strategy update failed ({symbol}): Input DataFrame is empty.")
            return empty_results

        # Work on a copy to avoid modifying the original DataFrame passed in
        df = df_input.copy()

        # --- Input Data Validation ---
        if not isinstance(df.index, pd.DatetimeIndex):
            self.lg.error(f"Strategy update failed ({symbol}): DataFrame index is not a DatetimeIndex.")
            return empty_results
        if not df.index.is_monotonic_increasing:
             self.lg.warning(f"Input DataFrame index ({symbol}) is not monotonic. Sorting index...")
             df.sort_index(inplace=True)
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_cols):
            self.lg.error(f"Strategy update failed ({symbol}): Missing one or more required columns: {required_cols}.")
            return empty_results
        if len(df) < self.min_data_len:
            self.lg.warning(f"Strategy update ({symbol}): Insufficient data ({len(df)} candles < ~{self.min_data_len} required). Results may be inaccurate or incomplete, especially for initial candles.")
            # Proceed but warn

        self.lg.debug(f"Starting strategy analysis ({symbol}) on {len(df)} candles (minimum required: {self.min_data_len}).")

        # --- Convert to Float for TA Libraries ---
        # pandas_ta and numpy work best with floats.
        try:
            df_float = pd.DataFrame(index=df.index)
            for col in required_cols:
                # Convert Decimal/Object to float, coercing errors to NaN
                df_float[col] = pd.to_numeric(df[col], errors='coerce')

            # Drop rows where essential float columns became NaN during conversion
            initial_float_len = len(df_float)
            df_float.dropna(subset=['open', 'high', 'low', 'close'], inplace=True)
            if len(df_float) < initial_float_len:
                 self.lg.debug(f"Dropped {initial_float_len - len(df_float)} rows ({symbol}) due to NaN in OHLC after float conversion.")
            if df_float.empty:
                self.lg.error(f"Strategy update failed ({symbol}): DataFrame became empty after float conversion and NaN drop.")
                return empty_results
        except Exception as e:
            self.lg.error(f"Strategy update failed ({symbol}): Error during conversion to float: {e}", exc_info=True)
            return empty_results

        # --- Indicator Calculations (using df_float) ---
        try:
            self.lg.debug(f"Calculating indicators ({symbol}) (ATR, EMAs, Bands, Volume Norm, Pivots)...")
            # Average True Range (ATR)
            df_float['atr'] = ta.atr(df_float['high'], df_float['low'], df_float['close'], length=self.vt_atr_period, fillna=np.nan)

            # Volumatic Trend EMAs
            df_float['ema1'] = self._ema_swma(df_float['close'], length=self.vt_length) # EMA(SWMA(close))
            df_float['ema2'] = ta.ema(df_float['close'], length=self.vt_length, fillna=np.nan) # Standard EMA(close)

            # Determine Trend Direction (ema2 crosses ema1 of the *previous* bar)
            # Ensure comparison happens only when both values are valid
            valid_comparison = df_float['ema2'].notna() & df_float['ema1'].shift(1).notna()
            trend_up_series = pd.Series(np.nan, index=df_float.index, dtype=object) # Use object to store bool/NaN
            trend_up_series[valid_comparison] = df_float['ema2'] > df_float['ema1'].shift(1)
            # Fill forward initial NaNs to establish trend earlier for change detection
            trend_up_series.ffill(inplace=True)

            # Identify Trend Changes (where trend differs from previous bar's trend)
            # Compare current boolean trend to previous boolean trend
            trend_changed_series = (trend_up_series != trend_up_series.shift(1)) & \
                                   trend_up_series.notna() & trend_up_series.shift(1).notna()
            df_float['trend_changed'] = trend_changed_series.fillna(False).astype(bool) # Store as pure boolean

            # Store the boolean trend (after potentially filling NaNs if desired, but NaN handling below is safer)
            df_float['trend_up'] = trend_up_series.astype(bool) # Convert ffilled series to bool

            # Capture EMA1 and ATR values at the exact point the trend changed
            df_float['ema1_at_change'] = np.where(df_float['trend_changed'], df_float['ema1'], np.nan)
            df_float['atr_at_change'] = np.where(df_float['trend_changed'], df_float['atr'], np.nan)

            # Forward fill these values to get the relevant EMA/ATR for the current trend segment
            # This ensures bands are based on the values when the current trend started
            df_float['ema1_for_bands'] = df_float['ema1_at_change'].ffill()
            df_float['atr_for_bands'] = df_float['atr_at_change'].ffill()

            # Calculate Volumatic Trend Bands only where underlying values are valid
            atr_multiplier_float = float(self.vt_atr_multiplier)
            valid_band_calc = df_float['ema1_for_bands'].notna() & df_float['atr_for_bands'].notna()
            df_float['upper_band'] = np.where(valid_band_calc, df_float['ema1_for_bands'] + (df_float['atr_for_bands'] * atr_multiplier_float), np.nan)
            df_float['lower_band'] = np.where(valid_band_calc, df_float['ema1_for_bands'] - (df_float['atr_for_bands'] * atr_multiplier_float), np.nan)


            # Volume Normalization
            volume_numeric = df_float['volume'].fillna(0.0) # Use float volume, handle NaNs
            # Use a reasonable min_periods for the rolling max to avoid NaN at the start
            min_periods_vol = max(1, min(self.vt_vol_ema_length // 2, len(df_float))) # Dynamic min periods
            df_float['vol_max'] = volume_numeric.rolling(window=self.vt_vol_ema_length, min_periods=min_periods_vol).max().fillna(method='bfill') # Backfill early NaNs
            # Calculate normalized volume (0-100 range, potentially > 100)
            # Use small epsilon to avoid division by zero/near-zero
            epsilon = 1e-18
            df_float['vol_norm'] = np.where(df_float['vol_max'] > epsilon,
                                            (volume_numeric / df_float['vol_max'] * 100.0),
                                            0.0) # Assign 0 if max volume is zero or negative
            # Handle potential NaNs and clip unreasonable values (e.g., > 200%)
            df_float['vol_norm'] = df_float['vol_norm'].fillna(0.0).clip(0.0, 200.0)

            # Pivot High/Low Calculation
            # Select source series based on config ('Wicks' or 'Body')
            if self.ob_source == "Wicks":
                high_series = df_float['high']
                low_series = df_float['low']
            else: # Use candle body ("Body")
                high_series = df_float[['open', 'close']].max(axis=1)
                low_series = df_float[['open', 'close']].min(axis=1)
            # Find pivots using the helper function
            df_float['is_ph'] = self._find_pivots(high_series, self.ph_left, self.ph_right, is_high=True)
            df_float['is_pl'] = self._find_pivots(low_series, self.pl_left, self.pl_right, is_high=False)

            self.lg.debug(f"Indicator calculations complete ({symbol}) (float).")

        except Exception as e:
            self.lg.error(f"Strategy update failed ({symbol}): Error during indicator calculation: {e}", exc_info=True)
            return empty_results

        # --- Copy Calculated Float Results back to Original Decimal DataFrame ---
        try:
            self.lg.debug(f"Converting calculated indicators back to Decimal format ({symbol})...")
            indicator_cols_numeric = ['atr', 'ema1', 'ema2', 'upper_band', 'lower_band', 'vol_norm']
            indicator_cols_bool = ['trend_up', 'trend_changed', 'is_ph', 'is_pl']

            for col in indicator_cols_numeric:
                if col in df_float.columns:
                    # Reindex to align with original Decimal DataFrame's index (handles NaNs introduced)
                    source_series = df_float[col].reindex(df.index)
                    # Convert numeric (float) back to Decimal, preserving NaNs
                    df[col] = source_series.apply(
                        lambda x: Decimal(str(x)) if pd.notna(x) and np.isfinite(x) else Decimal('NaN')
                    )
            for col in indicator_cols_bool:
                 if col in df_float.columns:
                    source_series = df_float[col].reindex(df.index)
                    # Convert potential object/NaN bool series to proper bool, filling NaNs as False
                    if col == 'trend_up':
                         # Special handling for trend_up: keep NaN if calculation failed, else bool
                         df[col] = source_series.apply(lambda x: bool(x) if pd.notna(x) else None)
                    else:
                         df[col] = source_series.fillna(False).astype(bool)

        except Exception as e:
            self.lg.error(f"Strategy update failed ({symbol}): Error converting calculated indicators back to Decimal: {e}", exc_info=True)
            # Continue if possible, OB management might still work partially

        # --- Clean Final Decimal DataFrame ---
        # Drop rows where essential indicators might be NaN (e.g., at the start of the series)
        # Trend_up can be None initially, so don't drop based on it here. ATR, Bands are crucial.
        initial_len_final = len(df)
        required_indicator_cols = ['close', 'atr', 'upper_band', 'lower_band', 'is_ph', 'is_pl']
        # Also drop if trend_up could not be determined (None) for a valid candle (should be rare unless data starts with NaN)
        df.dropna(subset=required_indicator_cols, inplace=True)
        df = df[df['trend_up'].notna()] # Be strict: require a trend determination

        rows_dropped_final = initial_len_final - len(df)
        if rows_dropped_final > 0:
            self.lg.debug(f"Dropped {rows_dropped_final} rows ({symbol}) from final DataFrame due to missing essential indicators (likely at start).")

        if df.empty:
            self.lg.warning(f"Strategy update ({symbol}): DataFrame became empty after final indicator cleaning. Cannot process Order Blocks.")
            empty_results['dataframe'] = df # Return the empty df
            return empty_results

        self.lg.debug(f"Indicators finalized in Decimal DataFrame ({symbol}). Processing Order Blocks...")

        # --- Order Block Management ---
        try:
            new_ob_count = 0
            violated_ob_count = 0
            last_candle_idx = df.index[-1]
            active_bull_boxes_before = [b for b in self.bull_boxes if b['active']]
            active_bear_boxes_before = [b for b in self.bear_boxes if b['active']]

            # 1. Identify New Order Blocks from Pivots on *all* historical candles in the df
            # This rebuilds OBs based on the current lookback settings each time
            # Consider optimizing later if performance is an issue (only check recent pivots)
            new_bull_candidates = []
            new_bear_candidates = []
            for timestamp, candle in df.iterrows():
                try:
                    # Create Bearish OB from Pivot High
                    if candle.get('is_ph'):
                        # Check if an OB from this exact candle already exists in the *current* list (prevent duplicates per run)
                        # Or if it existed before but was violated (don't recreate violated)
                        if not any((ob['left_idx'] == timestamp and ob['type'] == 'bear') for ob in self.bear_boxes + new_bear_candidates):
                            ob_top = candle['high'] if self.ob_source == "Wicks" else max(candle['open'], candle['close'])
                            ob_bottom = candle['open'] if self.ob_source == "Wicks" else min(candle['open'], candle['close'])
                            # Ensure valid Decimal values and top > bottom, check for NaN
                            if isinstance(ob_top, Decimal) and isinstance(ob_bottom, Decimal) and \
                               pd.notna(ob_top) and pd.notna(ob_bottom) and ob_top > ob_bottom:
                                ob_id = f"B_{timestamp.strftime('%y%m%d%H%M%S')}" # Unique ID
                                new_bear_candidates.append(OrderBlock(
                                    id=ob_id, type='bear', left_idx=timestamp, right_idx=timestamp, # Initial right_idx
                                    top=ob_top, bottom=ob_bottom, active=True, violated=False
                                ))
                                new_ob_count += 1
                            # else: self.lg.debug(f"Skipped Bear OB at {timestamp}: Invalid top/bottom ({ob_top}/{ob_bottom}).")

                    # Create Bullish OB from Pivot Low
                    if candle.get('is_pl'):
                        if not any((ob['left_idx'] == timestamp and ob['type'] == 'bull') for ob in self.bull_boxes + new_bull_candidates):
                            ob_top = candle['open'] if self.ob_source == "Wicks" else max(candle['open'], candle['close'])
                            ob_bottom = candle['low'] if self.ob_source == "Wicks" else min(candle['open'], candle['close'])
                            if isinstance(ob_top, Decimal) and isinstance(ob_bottom, Decimal) and \
                               pd.notna(ob_top) and pd.notna(ob_bottom) and ob_top > ob_bottom:
                                ob_id = f"L_{timestamp.strftime('%y%m%d%H%M%S')}"
                                new_bull_candidates.append(OrderBlock(
                                    id=ob_id, type='bull', left_idx=timestamp, right_idx=timestamp,
                                    top=ob_top, bottom=ob_bottom, active=True, violated=False
                                ))
                                new_ob_count += 1
                            # else: self.lg.debug(f"Skipped Bull OB at {timestamp}: Invalid top/bottom ({ob_top}/{ob_bottom}).")

                except Exception as pivot_proc_err:
                    self.lg.warning(f"Error processing potential pivot ({symbol}) at {timestamp}: {pivot_proc_err}", exc_info=False) # Less verbose exc_info

            # Add new candidates to the main lists
            self.bull_boxes.extend(new_bull_candidates)
            self.bear_boxes.extend(new_bear_candidates)
            if new_ob_count > 0:
                self.lg.debug(f"Identified {new_ob_count} new potential Order Blocks ({symbol}).")

            # 2. Manage Existing and New Order Blocks (Check Violations, Extend) across relevant history
            # Iterate through candles *after* the OB was formed up to the latest
            active_bull_boxes_after_add = [b for b in self.bull_boxes if b['active']]
            active_bear_boxes_after_add = [b for b in self.bear_boxes if b['active']]

            for box in active_bull_boxes_after_add:
                 # Find candles after the box was formed
                 relevant_candles = df[df.index > box['left_idx']]
                 for ts, candle in relevant_candles.iterrows():
                      close_price = candle.get('close')
                      if isinstance(close_price, Decimal) and pd.notna(close_price):
                           # Violation check: Close below the bottom of a bull OB
                           if close_price < box['bottom']:
                                box['active'] = False
                                box['violated'] = True
                                box['right_idx'] = ts # Mark violation time
                                violated_ob_count +=1
                                self.lg.debug(f"Bullish OB {box['id']} VIOLATED ({symbol}) at {ts.strftime('%H:%M')} by close {close_price.normalize()} < {box['bottom'].normalize()}")
                                break # Stop checking this box once violated
                           else:
                                # Update right_idx if still active
                                box['right_idx'] = ts
                      # else: lg.warning(f"Invalid close price at {ts} for OB check.")

            for box in active_bear_boxes_after_add:
                 relevant_candles = df[df.index > box['left_idx']]
                 for ts, candle in relevant_candles.iterrows():
                      close_price = candle.get('close')
                      if isinstance(close_price, Decimal) and pd.notna(close_price):
                           # Violation check: Close above the top of a bear OB
                           if close_price > box['top']:
                                box['active'] = False
                                box['violated'] = True
                                box['right_idx'] = ts
                                violated_ob_count += 1
                                self.lg.debug(f"Bearish OB {box['id']} VIOLATED ({symbol}) at {ts.strftime('%H:%M')} by close {close_price.normalize()} > {box['top'].normalize()}")
                                break
                           else:
                                box['right_idx'] = ts
                      # else: lg.warning(f"Invalid close price at {ts} for OB check.")

            # Extend active, non-violated boxes to the last candle if enabled
            if self.ob_extend:
                for box in self.bull_boxes + self.bear_boxes:
                     if box['active'] and not box['violated']:
                          box['right_idx'] = last_candle_idx

            if violated_ob_count > 0:
                 self.lg.debug(f"Processed violations for {violated_ob_count} Order Blocks ({symbol}).")

            # 3. Prune Order Blocks (Keep only the most recent 'ob_max_boxes' *active* ones)
            # Filter only active boxes, sort by creation time (descending), take the top N
            self.bull_boxes = sorted([b for b in self.bull_boxes if b['active']], key=lambda b: b['left_idx'], reverse=True)[:self.ob_max_boxes]
            self.bear_boxes = sorted([b for b in self.bear_boxes if b['active']], key=lambda b: b['left_idx'], reverse=True)[:self.ob_max_boxes]
            self.lg.debug(f"Pruned Order Blocks ({symbol}). Kept Active: Bulls={len(self.bull_boxes)}, Bears={len(self.bear_boxes)} (Max per type: {self.ob_max_boxes}).")

        except Exception as e:
            self.lg.error(f"Strategy update failed ({symbol}): Error during Order Block processing: {e}", exc_info=True)
            # Continue to return results, but OBs might be inaccurate/incomplete

        # --- Prepare Final StrategyAnalysisResults ---
        last_candle_final = df.iloc[-1] if not df.empty else None

        # Helper to safely extract Decimal values from the last candle
        def safe_decimal_from_candle(candle_data: Optional[pd.Series], col_name: str, positive_only: bool = False) -> Optional[Decimal]:
            """Safely extracts a Decimal value from a Series, returns None if invalid/NaN."""
            if candle_data is None: return None
            value = candle_data.get(col_name)
            # Check type and isnan *before* comparison
            if isinstance(value, Decimal) and value.is_finite(): # is_finite handles NaN, Inf
                 # Check positivity constraint if required
                 if not positive_only or value > Decimal('0'):
                     return value
            # lg.debug(f"safe_decimal: Value for '{col_name}' is invalid or failed check: {value}")
            return None

        # Helper to safely extract Boolean values (handling None/NaN)
        def safe_bool_from_candle(candle_data: Optional[pd.Series], col_name: str) -> Optional[bool]:
            """Safely extracts a boolean, returns None if NaN/missing."""
            if candle_data is None: return None
            value = candle_data.get(col_name)
            if pd.isna(value) or value is None: # pd.isna handles None, np.nan, pd.NA
                return None
            return bool(value)


        # Construct the results dictionary
        final_dataframe = df # Return the fully processed DataFrame with Decimals
        last_close_val = safe_decimal_from_candle(last_candle_final, 'close') or Decimal('0')
        current_trend_val = safe_bool_from_candle(last_candle_final, 'trend_up') # Can be None if undetermined
        trend_changed_val = bool(safe_bool_from_candle(last_candle_final, 'trend_changed')) # Default False if None
        vol_norm_dec = safe_decimal_from_candle(last_candle_final, 'vol_norm')
        vol_norm_int_val = int(vol_norm_dec.to_integral_value(ROUND_DOWN)) if vol_norm_dec is not None else None
        atr_val = safe_decimal_from_candle(last_candle_final, 'atr', positive_only=True) # ATR must be positive
        upper_band_val = safe_decimal_from_candle(last_candle_final, 'upper_band')
        lower_band_val = safe_decimal_from_candle(last_candle_final, 'lower_band')

        analysis_results = StrategyAnalysisResults(
            dataframe=final_dataframe,
            last_close=last_close_val,
            current_trend_up=current_trend_val,
            trend_just_changed=trend_changed_val,
            active_bull_boxes=self.bull_boxes, # Return the pruned list of active OBs
            active_bear_boxes=self.bear_boxes,
            vol_norm_int=vol_norm_int_val,
            atr=atr_val,
            upper_band=upper_band_val,
            lower_band=lower_band_val
        )

        # Log summary of the final results for the *last* candle
        trend_str = f"{NEON_GREEN}UP{RESET}" if analysis_results['current_trend_up'] is True else \
                    f"{NEON_RED}DOWN{RESET}" if analysis_results['current_trend_up'] is False else \
                    f"{NEON_YELLOW}Undetermined{RESET}"
        atr_str = f"{analysis_results['atr'].normalize()}" if analysis_results['atr'] else "N/A"
        time_str = last_candle_final.name.strftime('%Y-%m-%d %H:%M:%S %Z') if last_candle_final is not None else "N/A"

        self.lg.debug(f"--- Strategy Analysis Results ({symbol} @ {time_str}) ---")
        self.lg.debug(f"  Last Close: {analysis_results['last_close'].normalize()}")
        self.lg.debug(f"  Trend: {trend_str} (Changed on this candle: {analysis_results['trend_just_changed']})")
        self.lg.debug(f"  ATR: {atr_str}")
        self.lg.debug(f"  Volume Norm (%): {analysis_results['vol_norm_int']}")
        self.lg.debug(f"  Bands (Upper/Lower): {analysis_results['upper_band'].normalize() if analysis_results['upper_band'] else 'N/A'} / {analysis_results['lower_band'].normalize() if analysis_results['lower_band'] else 'N/A'}")
        self.lg.debug(f"  Active OBs (Bull/Bear): {len(analysis_results['active_bull_boxes'])} / {len(analysis_results['active_bear_boxes'])}")
        # Optionally log the details of the active OBs at DEBUG level
        # for ob in analysis_results['active_bull_boxes']: self.lg.debug(f"    Bull OB: {ob['id']} [{ob['bottom'].normalize()} - {ob['top'].normalize()}]")
        # for ob in analysis_results['active_bear_boxes']: self.lg.debug(f"    Bear OB: {ob['id']} [{ob['bottom'].normalize()} - {ob['top'].normalize()}]")
        self.lg.debug(f"---------------------------------------------")

        return analysis_results

# --- Signal Generation based on Strategy Results ---
class SignalGenerator:
    """
    Generates trading signals based on strategy analysis and position state.

    Responsibilities:
    - Evaluates `StrategyAnalysisResults` against entry/exit rules.
    - Considers the current open position (if any).
    - Generates signals: "BUY", "SELL", "EXIT_LONG", "EXIT_SHORT", "HOLD".
    - Calculates initial Stop Loss (SL) and Take Profit (TP) levels for new entries.
    """
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        """
        Initializes the Signal Generator with parameters from the config.

        Args:
            config (Dict[str, Any]): The main configuration dictionary.
            logger (logging.Logger): The logger instance.

        Raises:
            ValueError: If critical configuration parameters are invalid or missing.
        """
        self.config = config
        self.logger = logger
        self.lg = logger # Alias
        strategy_cfg = config.get("strategy_params", {})
        protection_cfg = config.get("protection", {})

        try:
            # Load parameters used for signal generation and SL/TP calculation
            self.ob_entry_proximity_factor = Decimal(str(strategy_cfg["ob_entry_proximity_factor"]))
            self.ob_exit_proximity_factor = Decimal(str(strategy_cfg["ob_exit_proximity_factor"]))
            self.initial_tp_atr_multiple = Decimal(str(protection_cfg["initial_take_profit_atr_multiple"]))
            self.initial_sl_atr_multiple = Decimal(str(protection_cfg["initial_stop_loss_atr_multiple"]))

            # Basic validation
            if not (self.ob_entry_proximity_factor >= 1): raise ValueError("ob_entry_proximity_factor must be >= 1.0")
            if not (self.ob_exit_proximity_factor >= 1): raise ValueError("ob_exit_proximity_factor must be >= 1.0")
            if not (self.initial_tp_atr_multiple >= 0): raise ValueError("initial_take_profit_atr_multiple must be >= 0")
            if not (self.initial_sl_atr_multiple > 0): raise ValueError("initial_stop_loss_atr_multiple must be > 0")

            self.lg.info(f"{NEON_CYAN}--- Initializing Signal Generator ---{RESET}")
            self.lg.info(f"  OB Entry Proximity Factor: {self.ob_entry_proximity_factor.normalize()}")
            self.lg.info(f"  OB Exit Proximity Factor: {self.ob_exit_proximity_factor.normalize()}")
            self.lg.info(f"  Initial TP ATR Multiple: {self.initial_tp_atr_multiple.normalize()}")
            self.lg.info(f"  Initial SL ATR Multiple: {self.initial_sl_atr_multiple.normalize()}")
            self.lg.info(f"-----------------------------------")

        except (KeyError, ValueError, InvalidOperation, TypeError) as e:
             self.lg.error(f"{NEON_RED}FATAL: Error initializing SignalGenerator parameters from config: {e}.{RESET}", exc_info=True)
             raise ValueError(f"SignalGenerator initialization failed: {e}") from e

    def generate_signal(self, analysis_results: StrategyAnalysisResults, open_position: Optional[PositionInfo]) -> str:
        """
        Determines the trading signal based on strategy analysis and current position.

        Logic Flow:
        1. Validate inputs.
        2. If position exists, check for Exit conditions (trend flip, OB proximity).
        3. If no position exists, check for Entry conditions (trend alignment, OB proximity).
        4. Default to HOLD if no entry/exit conditions met.

        Args:
            analysis_results (StrategyAnalysisResults): The results from `VolumaticOBStrategy.update()`.
            open_position (Optional[PositionInfo]): Standardized `PositionInfo` dict, or None if no position.

        Returns:
            str: The generated signal string: "BUY", "SELL", "EXIT_LONG", "EXIT_SHORT", or "HOLD".
        """
        lg = self.logger
        symbol = analysis_results['dataframe'].attrs.get('symbol', 'UnknownSymbol') # Get symbol if attached

        # --- Validate Input ---
        # Check for essential valid results from analysis
        if not analysis_results or \
           analysis_results['current_trend_up'] is None or \
           analysis_results['last_close'] <= 0 or \
           analysis_results['atr'] is None or analysis_results['atr'] <= 0:
            lg.warning(f"{NEON_YELLOW}Signal Generation ({symbol}): Invalid or incomplete strategy analysis results. Defaulting to HOLD.{RESET}")
            lg.debug(f"  Problematic Analysis: Trend={analysis_results.get('current_trend_up')}, Close={analysis_results.get('last_close')}, ATR={analysis_results.get('atr')}")
            return "HOLD"

        # Extract key values for easier access
        last_close = analysis_results['last_close']
        trend_is_up = analysis_results['current_trend_up'] # This is boolean (cannot be None after checks)
        trend_changed = analysis_results['trend_just_changed']
        active_bull_obs = analysis_results['active_bull_boxes']
        active_bear_obs = analysis_results['active_bear_boxes']
        position_side = open_position['side'] if open_position else None

        signal: str = "HOLD" # Default signal

        lg.debug(f"--- Signal Generation Check ({symbol}) ---")
        trend_log = 'UP' if trend_is_up else 'DOWN'
        lg.debug(f"  Input: Close={last_close.normalize()}, Trend={trend_log}, TrendChanged={trend_changed}, Position={position_side or 'None'}")
        lg.debug(f"  Active OBs: Bull={len(active_bull_obs)}, Bear={len(active_bear_obs)}")

        # --- 1. Check Exit Conditions (if position exists) ---
        if position_side == 'long':
            # Exit Long if trend flips down *on the last candle*
            if trend_is_up is False and trend_changed:
                signal = "EXIT_LONG"
                lg.warning(f"{NEON_YELLOW}{BRIGHT}EXIT LONG Signal ({symbol}): Trend flipped to DOWN on last candle.{RESET}")
            # Exit Long if price nears a bearish OB (use exit proximity factor)
            elif active_bear_obs and signal == "HOLD": # Check only if not already exiting
                try:
                    # Find the closest bear OB (based on top edge proximity)
                    closest_bear_ob = min(active_bear_obs, key=lambda ob: abs(ob['top'] - last_close))
                    # Exit threshold: Price >= OB Top / Exit Proximity Factor
                    # Ensure factor is > 0 before division
                    exit_threshold = closest_bear_ob['top'] / self.ob_exit_proximity_factor if self.ob_exit_proximity_factor > 0 else closest_bear_ob['top']
                    if last_close >= exit_threshold:
                        signal = "EXIT_LONG"
                        lg.warning(f"{NEON_YELLOW}{BRIGHT}EXIT LONG Signal ({symbol}): Price {last_close.normalize()} >= Bear OB exit threshold {exit_threshold.normalize()} (OB ID: {closest_bear_ob['id']}, Top: {closest_bear_ob['top'].normalize()}){RESET}")
                except (ZeroDivisionError, InvalidOperation, Exception) as e:
                    lg.warning(f"Error during Bearish OB exit check ({symbol}, long): {e}")

        elif position_side == 'short':
            # Exit Short if trend flips up *on the last candle*
            if trend_is_up is True and trend_changed:
                signal = "EXIT_SHORT"
                lg.warning(f"{NEON_YELLOW}{BRIGHT}EXIT SHORT Signal ({symbol}): Trend flipped to UP on last candle.{RESET}")
            # Exit Short if price nears a bullish OB (use exit proximity factor)
            elif active_bull_obs and signal == "HOLD": # Check only if not already exiting
                try:
                    # Find the closest bull OB (based on bottom edge proximity)
                    closest_bull_ob = min(active_bull_obs, key=lambda ob: abs(ob['bottom'] - last_close))
                    # Exit threshold: Price <= OB Bottom * Exit Proximity Factor
                    exit_threshold = closest_bull_ob['bottom'] * self.ob_exit_proximity_factor
                    if last_close <= exit_threshold:
                        signal = "EXIT_SHORT"
                        lg.warning(f"{NEON_YELLOW}{BRIGHT}EXIT SHORT Signal ({symbol}): Price {last_close.normalize()} <= Bull OB exit threshold {exit_threshold.normalize()} (OB ID: {closest_bull_ob['id']}, Bottom: {closest_bull_ob['bottom'].normalize()}){RESET}")
                except Exception as e:
                    lg.warning(f"Error during Bullish OB exit check ({symbol}, short): {e}")

        # If an exit signal was generated, return it immediately
        if signal != "HOLD":
            lg.debug(f"--- Signal Result ({symbol}): {signal} (Exit Condition Met) ---")
            return signal

        # --- 2. Check Entry Conditions (if NO position exists) ---
        if position_side is None:
            # Check for BUY signal: Trend is UP and price is within a Bullish OB's proximity
            if trend_is_up is True and active_bull_obs:
                for ob in active_bull_obs:
                    try:
                        # Entry zone: OB Bottom <= Price <= OB Top * Entry Proximity Factor
                        entry_zone_bottom = ob['bottom']
                        entry_zone_top = ob['top'] * self.ob_entry_proximity_factor
                        if entry_zone_bottom <= last_close <= entry_zone_top:
                            signal = "BUY"
                            lg.info(f"{NEON_GREEN}{BRIGHT}BUY Signal ({symbol}): Trend UP & Price {last_close.normalize()} within Bull OB entry zone [{entry_zone_bottom.normalize()} - {entry_zone_top.normalize()}] (OB ID: {ob['id']}){RESET}")
                            break # Take the first valid entry signal found
                    except (InvalidOperation, Exception) as e:
                         lg.warning(f"Error checking Bull OB {ob.get('id')} ({symbol}) for entry: {e}")


            # Check for SELL signal: Trend is DOWN and price is within a Bearish OB's proximity
            elif trend_is_up is False and active_bear_obs:
                for ob in active_bear_obs:
                    try:
                        # Entry zone: OB Bottom / Entry Proximity Factor <= Price <= OB Top
                        # Safe division check
                        entry_zone_bottom = ob['bottom'] / self.ob_entry_proximity_factor if self.ob_entry_proximity_factor > 0 else ob['bottom']
                        entry_zone_top = ob['top']
                        if entry_zone_bottom <= last_close <= entry_zone_top:
                            signal = "SELL"
                            lg.info(f"{NEON_RED}{BRIGHT}SELL Signal ({symbol}): Trend DOWN & Price {last_close.normalize()} within Bear OB entry zone [{entry_zone_bottom.normalize()} - {entry_zone_top.normalize()}] (OB ID: {ob['id']}){RESET}")
                            break # Take the first valid entry signal found
                    except (ZeroDivisionError, InvalidOperation, Exception) as e:
                         lg.warning(f"Error checking Bear OB {ob.get('id')} ({symbol}) for entry: {e}")


        # --- 3. Default to HOLD ---
        if signal == "HOLD":
            lg.debug(f"Signal ({symbol}): HOLD - No valid entry or exit conditions met.")

        lg.debug(f"--- Signal Result ({symbol}): {signal} ---")
        return signal

    def calculate_initial_tp_sl(self, entry_price: Decimal, signal: str, atr: Decimal, market_info: MarketInfo, exchange: ccxt.Exchange) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """
        Calculates initial Take Profit (TP) and Stop Loss (SL) levels for a new entry.

        Uses entry price, current ATR, configured multipliers, and market price precision.
        Ensures SL/TP levels are strictly beyond the entry price after formatting.

        Args:
            entry_price (Decimal): The estimated or actual entry price (positive Decimal).
            signal (str): The entry signal ("BUY" or "SELL").
            atr (Decimal): The current Average True Range value (positive Decimal).
            market_info (MarketInfo): The standardized MarketInfo dictionary.
            exchange (ccxt.Exchange): The initialized ccxt.Exchange object (for price formatting).

        Returns:
            Tuple[Optional[Decimal], Optional[Decimal]]: A tuple containing:
                - Calculated Take Profit price (Decimal), or None if disabled or calculation fails.
                - Calculated Stop Loss price (Decimal), or None if calculation fails critically.
            Returns (None, None) if inputs are invalid or critical errors occur.
        """
        lg = self.logger
        symbol = market_info['symbol']
        lg.debug(f"Calculating Initial TP/SL ({symbol}) for {signal} signal at entry {entry_price.normalize()} with ATR {atr.normalize()}")

        # --- Input Validation ---
        if signal not in ["BUY", "SELL"]:
            lg.error(f"TP/SL Calc Failed ({symbol}): Invalid signal '{signal}'.")
            return None, None
        if not isinstance(entry_price, Decimal) or entry_price <= 0:
             lg.error(f"TP/SL Calc Failed ({symbol}): Entry price ({entry_price}) must be a positive Decimal.")
             return None, None
        if not isinstance(atr, Decimal) or atr <= 0:
            lg.error(f"TP/SL Calc Failed ({symbol}): ATR ({atr}) must be a positive Decimal.")
            return None, None
        try:
            price_tick = market_info['price_precision_step_decimal']
            if price_tick is None or price_tick <= 0: raise ValueError("Invalid price tick size")
        except (KeyError, ValueError, TypeError) as e:
            lg.error(f"TP/SL Calc Failed ({symbol}): Could not get valid price precision from market info: {e}")
            return None, None

        # --- Calculate Raw TP/SL ---
        try:
            tp_atr_multiple = self.initial_tp_atr_multiple # Already Decimal from init
            sl_atr_multiple = self.initial_sl_atr_multiple # Already Decimal from init

            # Calculate offsets
            tp_offset = atr * tp_atr_multiple
            sl_offset = atr * sl_atr_multiple

            # Calculate raw levels
            take_profit_raw: Optional[Decimal] = None
            if tp_atr_multiple > 0: # Only calculate TP if multiplier is positive
                 take_profit_raw = (entry_price + tp_offset) if signal == "BUY" else (entry_price - tp_offset)

            stop_loss_raw = (entry_price - sl_offset) if signal == "BUY" else (entry_price + sl_offset)

            lg.debug(f"  Raw Levels ({symbol}): TP={take_profit_raw.normalize() if take_profit_raw else 'N/A'}, SL={stop_loss_raw.normalize()}")

            # --- Format Levels to Market Precision ---
            # Helper function to format and validate price level
            def format_level(price_decimal: Optional[Decimal], level_name: str) -> Optional[Decimal]:
                """Formats price to exchange precision, returns positive Decimal or None."""
                if price_decimal is None or price_decimal <= 0:
                    lg.debug(f"Calculated {level_name} ({symbol}) is invalid or zero/negative ({price_decimal}).")
                    return None
                try:
                    # Use CCXT's price_to_precision for correct rounding/truncating
                    formatted_str = exchange.price_to_precision(symbol=symbol, price=float(price_decimal))
                    formatted_decimal = Decimal(formatted_str)
                    # Final check: ensure formatted price is still positive
                    if formatted_decimal > 0:
                         return formatted_decimal
                    else:
                         lg.warning(f"Formatted {level_name} ({symbol}, '{formatted_str}') resulted in zero or negative value. Ignoring {level_name}.")
                         return None
                except Exception as e:
                    lg.error(f"Error formatting {level_name} ({symbol}) value {price_decimal.normalize()} to exchange precision: {e}.")
                    return None

            # Format TP and SL
            take_profit_final = format_level(take_profit_raw, "Take Profit")
            stop_loss_final = format_level(stop_loss_raw, "Stop Loss")

            # --- Final Adjustments and Validation ---
            # Ensure SL is strictly beyond entry after formatting
            if stop_loss_final is not None:
                sl_invalid = (signal == "BUY" and stop_loss_final >= entry_price) or \
                             (signal == "SELL" and stop_loss_final <= entry_price)
                if sl_invalid:
                    lg.warning(f"Formatted {signal} Stop Loss ({symbol}) {stop_loss_final.normalize()} is not strictly beyond entry {entry_price.normalize()}. Adjusting by one tick.")
                    # Adjust SL by one tick further away from entry
                    adjusted_sl_raw = (stop_loss_final - price_tick) if signal == "BUY" else (stop_loss_final + price_tick)
                    stop_loss_final = format_level(adjusted_sl_raw, "Adjusted Stop Loss") # Reformat after adjustment
                    if stop_loss_final is None or stop_loss_final <= 0:
                         lg.error(f"{NEON_RED}CRITICAL ({symbol}): Failed to calculate valid adjusted SL after initial SL was invalid.{RESET}")
                         return take_profit_final, None # Return None for SL is critical failure

            # Ensure TP is strictly beyond entry (if TP is enabled and calculated)
            if take_profit_final is not None:
                tp_invalid = (signal == "BUY" and take_profit_final <= entry_price) or \
                             (signal == "SELL" and take_profit_final >= entry_price)
                if tp_invalid:
                    lg.warning(f"Formatted {signal} Take Profit ({symbol}) {take_profit_final.normalize()} is not strictly beyond entry {entry_price.normalize()}. Disabling TP for this entry.")
                    take_profit_final = None # Disable TP if it ends up on the wrong side

            # Log final calculated levels
            tp_log = take_profit_final.normalize() if take_profit_final else "None (Disabled or Calc Failed)"
            sl_log = stop_loss_final.normalize() if stop_loss_final else "None (Calc Failed!)"
            lg.info(f"  >>> Calculated Initial Levels ({symbol}): TP={tp_log}, SL={sl_log}")

            # Critical check: Ensure SL calculation was successful
            if stop_loss_final is None:
                lg.error(f"{NEON_RED}Stop Loss calculation failed critically ({symbol}). Cannot determine position size or place trade safely.{RESET}")
                return take_profit_final, None # Return None for SL

            return take_profit_final, stop_loss_final

        except Exception as e:
            lg.error(f"{NEON_RED}Unexpected error calculating initial TP/SL ({symbol}): {e}{RESET}", exc_info=True)
            return None, None

# --- Main Analysis and Trading Loop Function ---
def analyze_and_trade_symbol(exchange: ccxt.Exchange, symbol: str, config: Dict[str, Any], logger: logging.Logger,
                             strategy_engine: VolumaticOBStrategy, signal_generator: SignalGenerator, market_info: MarketInfo) -> None:
    """
    Performs one full cycle of analysis and trading logic for a single symbol.

    Steps:
    1. Logs cycle start and key configurations.
    2. Fetches and validates kline data, ensuring sufficient length.
    3. Runs the strategy analysis using `strategy_engine`.
    4. Validates analysis results (trend, close, ATR).
    5. Gets current market state (live price, open position).
    6. Generates a trading signal using `signal_generator`.
    7. Executes trading actions based on the signal and `enable_trading` flag:
        - **Entry:** If no position and BUY/SELL signal:
            - Checks balance.
            - Calculates initial SL/TP.
            - Sets leverage (if applicable).
            - Calculates position size.
            - Places market order.
            - Confirms position opens (with retry).
            - Sets initial protection (TSL or Fixed SL/TP).
        - **Exit:** If position exists and EXIT signal:
            - Places reduce-only market order to close.
        - **Management:** If position exists and HOLD signal:
            - Checks and applies Break-Even adjustment if conditions met.
            - Checks and attempts to set TSL if enabled but not active.
    8. Logs cycle end and duration.

    Args:
        exchange (ccxt.Exchange): The initialized ccxt.Exchange object.
        symbol (str): The trading symbol to analyze and trade.
        config (Dict[str, Any]): The main configuration dictionary.
        logger (logging.Logger): The logger instance for this symbol's trading activity.
        strategy_engine (VolumaticOBStrategy): The initialized VolumaticOBStrategy instance.
        signal_generator (SignalGenerator): The initialized SignalGenerator instance.
        market_info (MarketInfo): The standardized MarketInfo dictionary for the symbol.
    """
    lg = logger
    lg.info(f"\n{BRIGHT}---=== Cycle Start: Analyzing {symbol} ({config['interval']} TF) ===---{RESET}")
    cycle_start_time = time.monotonic()

    # Log key config settings for this cycle for easier debugging
    prot_cfg = config.get("protection", {})
    strat_cfg = config.get("strategy_params", {})
    lg.debug(f"Cycle Config ({symbol}): Trading={'ENABLED' if config.get('enable_trading') else 'DISABLED'}, Sandbox={config.get('use_sandbox')}, "
             f"Risk={config.get('risk_per_trade'):.2%}, Lev={config.get('leverage')}x, "
             f"TSL={'ON' if prot_cfg.get('enable_trailing_stop') else 'OFF'} (Act%={prot_cfg.get('trailing_stop_activation_percentage'):.3%}, CB%={prot_cfg.get('trailing_stop_callback_rate'):.3%}), "
             f"BE={'ON' if prot_cfg.get('enable_break_even') else 'OFF'} (TrigATR={prot_cfg.get('break_even_trigger_atr_multiple')}, Offset={prot_cfg.get('break_even_offset_ticks')} ticks), "
             f"InitSL Mult={prot_cfg.get('initial_stop_loss_atr_multiple')}, InitTP Mult={prot_cfg.get('initial_take_profit_atr_multiple')}, "
             f"OB Source={strat_cfg.get('ob_source')}")

    # --- 1. Fetch Kline Data ---
    ccxt_interval = CCXT_INTERVAL_MAP.get(config["interval"])
    if not ccxt_interval:
        # This should not happen if config validation worked, but check defensively
        lg.critical(f"Invalid interval '{config['interval']}' in config ({symbol}). Cannot map to CCXT timeframe. Skipping cycle.")
        return

    # Determine how many klines to fetch
    min_required_data = strategy_engine.min_data_len
    fetch_limit_from_config = config.get("fetch_limit", DEFAULT_FETCH_LIMIT)
    # Need at least what the strategy requires, but fetch user preference if it's more
    fetch_limit_needed = max(min_required_data, fetch_limit_from_config)
    # Actual request limit is capped by the API
    fetch_limit_request = min(fetch_limit_needed, BYBIT_API_KLINE_LIMIT)

    lg.info(f"Requesting {fetch_limit_request} klines for {symbol} ({ccxt_interval}). "
            f"(Strategy requires min: {min_required_data}, Config requests: {fetch_limit_from_config}, API limit: {BYBIT_API_KLINE_LIMIT})")
    klines_df = fetch_klines_ccxt(exchange, symbol, ccxt_interval, limit=fetch_limit_request, logger=lg)
    fetched_count = len(klines_df)

    # --- 2. Validate Fetched Data ---
    if klines_df.empty or fetched_count < min_required_data:
        # Check if failure was due to hitting API limit but still not getting enough data
        hit_api_limit_but_insufficient = (fetch_limit_request == BYBIT_API_KLINE_LIMIT and
                                          fetched_count == BYBIT_API_KLINE_LIMIT and
                                          fetched_count < min_required_data)
        if hit_api_limit_but_insufficient:
            lg.error(f"{NEON_RED}CRITICAL DATA ISSUE ({symbol}):{RESET} Fetched maximum {fetched_count} klines allowed by API, "
                     f"but strategy requires {min_required_data}. Analysis will be inaccurate or fail. "
                     f"{NEON_YELLOW}ACTION REQUIRED: Reduce lookback periods in strategy config (e.g., vt_atr_period, vt_vol_ema_length)! Skipping cycle.{RESET}")
        elif klines_df.empty:
            lg.error(f"Failed to fetch any kline data for {symbol} {ccxt_interval}. Cannot proceed. Skipping cycle.")
        else: # Fetched some data, but not enough
            lg.error(f"Fetched only {fetched_count} klines for {symbol}, but strategy requires {min_required_data}. "
                     f"Analysis may be inaccurate or fail. Skipping cycle.")
        return # Cannot proceed without sufficient data

    # --- 3. Run Strategy Analysis ---
    lg.debug(f"Running strategy analysis engine ({symbol})...")
    # Add symbol attribute to DataFrame for potential use in signal generator logging
    klines_df.attrs['symbol'] = symbol
    try:
        analysis_results = strategy_engine.update(klines_df)
    except Exception as analysis_err:
        lg.error(f"{NEON_RED}Strategy analysis update failed unexpectedly ({symbol}): {analysis_err}{RESET}", exc_info=True)
        return # Stop cycle if analysis fails

    # Validate essential analysis results needed for signal generation and trading
    if not analysis_results or \
       analysis_results['current_trend_up'] is None or \
       analysis_results['last_close'] <= 0 or \
       analysis_results['atr'] is None or analysis_results['atr'] <= 0:
        lg.error(f"{NEON_RED}Strategy analysis ({symbol}) did not produce valid essential results (missing/invalid trend, close price, or ATR). Skipping cycle.{RESET}")
        lg.debug(f"Problematic Analysis Results ({symbol}): Trend={analysis_results.get('current_trend_up')}, Close={analysis_results.get('last_close')}, ATR={analysis_results.get('atr')}")
        return
    latest_close = analysis_results['last_close']
    current_atr = analysis_results['atr'] # Guaranteed positive Decimal here
    lg.info(f"Strategy Analysis Complete ({symbol}): Trend={'UP' if analysis_results['current_trend_up'] else 'DOWN'}, "
            f"Last Close={latest_close.normalize()}, ATR={current_atr.normalize()}")

    # --- 4. Get Current Market State (Price & Position) ---
    lg.debug(f"Fetching current market price and checking for open positions ({symbol})...")
    current_market_price = fetch_current_price_ccxt(exchange, symbol, lg)
    open_position: Optional[PositionInfo] = get_open_position(exchange, symbol, lg) # Returns standardized dict or None

    # Determine price to use for real-time checks (prefer live price, fallback to last close)
    # Ensure the price used is valid and positive
    price_for_checks: Optional[Decimal] = None
    if current_market_price and current_market_price > 0:
         price_for_checks = current_market_price
    elif latest_close > 0:
         price_for_checks = latest_close
         lg.debug(f"Using last kline close price ({symbol}, {latest_close.normalize()}) for checks as live price is unavailable/invalid.")
    else:
         lg.error(f"{NEON_RED}Cannot determine a valid current price ({symbol}, Live={current_market_price}, LastClose={latest_close}). Skipping cycle.{RESET}")
         return

    # --- 5. Generate Trading Signal ---
    lg.debug(f"Generating trading signal ({symbol}) based on analysis and position...")
    try:
        signal = signal_generator.generate_signal(analysis_results, open_position)
    except Exception as signal_err:
        lg.error(f"{NEON_RED}Signal generation failed unexpectedly ({symbol}): {signal_err}{RESET}", exc_info=True)
        return # Stop cycle if signal generation fails

    lg.info(f"Generated Signal ({symbol}): {BRIGHT}{signal}{RESET}")

    # --- 6. Trading Logic Execution ---
    trading_enabled = config.get("enable_trading", False)

    # --- Scenario: Trading Disabled (Analysis/Logging Only) ---
    if not trading_enabled:
        lg.info(f"{NEON_YELLOW}Trading is DISABLED ({symbol}).{RESET} Analysis complete. Signal was: {signal}")
        # Log potential action if trading were enabled
        if open_position is None and signal in ["BUY", "SELL"]:
            lg.info(f"  (Action if enabled: Would attempt to {signal} {symbol})")
        elif open_position and signal in ["EXIT_LONG", "EXIT_SHORT"]:
            lg.info(f"  (Action if enabled: Would attempt to {signal} current {open_position['side']} position on {symbol})")
        elif open_position:
             lg.info(f"  (Action if enabled: Would manage existing {open_position['side']} position on {symbol})")
        else: # HOLD signal, no position
            lg.info(f"  (Action if enabled: No entry/exit action indicated for {symbol})")
        # End cycle here if trading disabled
        cycle_end_time = time.monotonic()
        lg.debug(f"---=== Analysis-Only Cycle End ({symbol}, Duration: {cycle_end_time - cycle_start_time:.2f}s) ===---\n")
        return # Stop further processing

    # ======================================
    # --- Trading IS Enabled Below Here ---
    # ======================================
    lg.info(f"{BRIGHT}Trading is ENABLED ({symbol}). Processing signal '{signal}'...{RESET}")

    # --- Scenario 1: No Position -> Consider Entry ---
    if open_position is None and signal in ["BUY", "SELL"]:
        lg.info(f"{BRIGHT}*** {signal} Signal & No Position ({symbol}): Initiating Entry Sequence... ***{RESET}")

        # Fetch current balance
        balance = fetch_balance(exchange, QUOTE_CURRENCY, lg)
        if balance is None or balance <= 0:
            lg.error(f"{NEON_RED}Trade Aborted ({symbol} {signal}): Cannot fetch valid positive balance ({balance}) for {QUOTE_CURRENCY}.{RESET}")
            return

        # Calculate initial SL/TP based on latest close and current ATR
        # Use latest_close for initial calculation as it corresponds to the signal generation candle
        initial_tp_calc, initial_sl_calc = signal_generator.calculate_initial_tp_sl(latest_close, signal, current_atr, market_info, exchange)

        if initial_sl_calc is None:
            lg.error(f"{NEON_RED}Trade Aborted ({symbol} {signal}): Failed to calculate a valid initial Stop Loss. Cannot size position.{RESET}")
            return
        if initial_tp_calc is None:
            lg.info(f"{NEON_YELLOW}Initial Take Profit calculation failed or is disabled ({symbol}, TP Mult = 0). Proceeding without initial TP.{RESET}")

        # Set Leverage (if contract market and leverage > 0 in config)
        if market_info['is_contract']:
            leverage_to_set = int(config.get('leverage', 0))
            if leverage_to_set > 0:
                lg.info(f"Setting leverage to {leverage_to_set}x for {symbol}...")
                leverage_ok = set_leverage_ccxt(exchange, symbol, leverage_to_set, market_info, lg)
                if not leverage_ok:
                    lg.error(f"{NEON_RED}Trade Aborted ({symbol} {signal}): Failed to set leverage to {leverage_to_set}x.{RESET}")
                    return
            else:
                lg.info(f"Leverage setting skipped ({symbol}): config leverage is 0. Using exchange default or previously set leverage.")

        # Calculate Position Size
        # Use latest_close for sizing calculation as it corresponds to the SL calculation price
        position_size = calculate_position_size(balance, config["risk_per_trade"], initial_sl_calc, latest_close, market_info, exchange, lg)
        if position_size is None or position_size <= 0:
            lg.error(f"{NEON_RED}Trade Aborted ({symbol} {signal}): Position sizing failed or resulted in zero/negative size ({position_size}).{RESET}")
            return

        # Place Market Order
        lg.warning(f"{BRIGHT}===> PLACING {signal} MARKET ORDER ({symbol}) | Size: {position_size.normalize()} <==={RESET}")
        trade_order = place_trade(exchange, symbol, signal, position_size, market_info, lg, reduce_only=False)

        # --- Post-Trade Actions (Confirmation and Protection) ---
        if trade_order and trade_order.get('id'):
            confirm_delay = config.get("position_confirm_delay_seconds", POSITION_CONFIRM_DELAY_SECONDS)
            lg.info(f"Order {trade_order['id']} placed ({symbol}). Waiting {confirm_delay}s for position confirmation...")
            time.sleep(confirm_delay)

            # Confirm position opened (with retry)
            confirmed_position: Optional[PositionInfo] = None
            for confirm_attempt in range(2): # Try twice with short delay
                 confirmed_position = get_open_position(exchange, symbol, lg)
                 if confirmed_position: break
                 if confirm_attempt == 0:
                      lg.warning(f"Position confirmation ({symbol}) attempt 1 failed, retrying in 3s...")
                      time.sleep(3)

            if confirmed_position:
                try:
                    # Get actual entry price if available, fallback to latest close used for sizing
                    entry_price_actual: Optional[Decimal] = None
                    entry_price_actual_str = confirmed_position.get('entryPrice')
                    if entry_price_actual_str:
                         entry_price_actual = _safe_market_decimal(entry_price_actual_str, 'confirmed_position.entryPrice', allow_zero=False)

                    if entry_price_actual is None:
                        lg.warning(f"{NEON_YELLOW}Could not get actual entry price from confirmed position ({symbol}). Using original price ({latest_close.normalize()}) for protection calculation.{RESET}")
                        entry_price_actual = latest_close # Fallback

                    lg.info(f"{NEON_GREEN}Position Confirmed ({symbol})! Actual/Estimated Entry: ~{entry_price_actual.normalize()}{RESET}")

                    # Recalculate SL/TP based on actual/fallback entry price and current ATR for setting protection
                    # Use current_atr from the analysis results of the signal candle
                    prot_tp_calc, prot_sl_calc = signal_generator.calculate_initial_tp_sl(entry_price_actual, signal, current_atr, market_info, exchange)

                    if prot_sl_calc is None:
                        # This is critical - position is open but SL cannot be set
                        lg.error(f"{NEON_RED}{BRIGHT}CRITICAL ERROR ({symbol}): Position entered, but failed to recalculate SL based on entry price {entry_price_actual.normalize()}! POSITION IS UNPROTECTED! Manual SL required!{RESET}")
                    else:
                        # Set protection (TSL or Fixed SL/TP)
                        protection_set_success = False
                        if prot_cfg.get("enable_trailing_stop", True):
                            lg.info(f"Setting Trailing Stop Loss (TSL) ({symbol}) based on entry {entry_price_actual.normalize()}...")
                            protection_set_success = set_trailing_stop_loss(
                                exchange, symbol, market_info, confirmed_position, config, lg,
                                take_profit_price=prot_tp_calc # Set TP alongside TSL if calculated
                            )
                        # Only set fixed SL/TP if TSL is disabled AND either SL or TP is valid
                        elif not prot_cfg.get("enable_trailing_stop", True) and (prot_sl_calc or prot_tp_calc):
                            lg.info(f"Setting Fixed Stop Loss / Take Profit ({symbol}) based on entry {entry_price_actual.normalize()}...")
                            protection_set_success = _set_position_protection(
                                exchange, symbol, market_info, confirmed_position, lg,
                                stop_loss_price=prot_sl_calc,
                                take_profit_price=prot_tp_calc
                            )
                        else:
                            lg.info(f"No protection (TSL or Fixed SL/TP) enabled or calculated ({symbol}). Position entered without API protection.")
                            protection_set_success = True # Considered success as no action was needed

                        # Log final status
                        if protection_set_success:
                            lg.info(f"{NEON_GREEN}{BRIGHT}=== ENTRY & INITIAL PROTECTION SETUP COMPLETE ({symbol} {signal}) ==={RESET}")
                        else:
                            lg.error(f"{NEON_RED}{BRIGHT}=== TRADE PLACED ({symbol} {signal}), BUT FAILED TO SET PROTECTION. MANUAL MONITORING REQUIRED! ==={RESET}")

                except Exception as post_trade_err:
                    lg.error(f"{NEON_RED}Error during post-trade setup ({symbol}, protection setting): {post_trade_err}{RESET}", exc_info=True)
                    lg.warning(f"{NEON_YELLOW}Position is confirmed open for {symbol}, but protection setup failed! Manual check recommended!{RESET}")
            else:
                # Order placed but position not found after delay and retries
                lg.error(f"{NEON_RED}Order {trade_order['id']} was placed ({symbol}), but FAILED TO CONFIRM open position after {confirm_delay + 3}s delay! Manual check required! Order might have failed to fill or API issue.{RESET}")
        else:
            # Order placement itself failed
            lg.error(f"{NEON_RED}=== TRADE EXECUTION FAILED ({symbol} {signal}). No order was placed. ===")

    # --- Scenario 2: Existing Position -> Consider Exit or Manage ---
    elif open_position:
        pos_side = open_position['side'] # 'long' or 'short'
        pos_size_decimal = open_position.get('size_decimal', Decimal('0')) # Get parsed Decimal size

        # Check if position size is effectively zero (e.g., due to previous partial close or stale data)
        amount_precision = market_info.get('amount_precision_step_decimal', Decimal('1e-8'))
        if abs(pos_size_decimal) < amount_precision:
             lg.info(f"Existing position data found for {symbol}, but size ({pos_size_decimal.normalize()}) is effectively zero. Treating as no position.")
             open_position = None # Treat as no position for subsequent logic
             # Re-evaluate entry signal if applicable (this would require restructuring the if/elif chain)
             # For simplicity here, just log and end this path for the cycle.
             lg.warning(f"Size zero detected ({symbol}). Re-running checks next cycle might be needed if an entry signal is present.")

        # Proceed only if position size is significant
        elif pos_size_decimal != Decimal('0'):
            lg.info(f"Existing {pos_side.upper()} position found ({symbol}, Size: {pos_size_decimal.normalize()}). Signal: {signal}")

            # Check if the signal triggers an exit
            exit_triggered = (signal == "EXIT_LONG" and pos_side == 'long') or \
                             (signal == "EXIT_SHORT" and pos_side == 'short')

            if exit_triggered:
                # --- Handle Exit Signal ---
                lg.warning(f"{NEON_YELLOW}{BRIGHT}*** {signal} Signal Received ({symbol})! Closing {pos_side} position... ***{RESET}")
                try:
                    # Ensure size is positive for the closing order amount
                    size_to_close = abs(pos_size_decimal)

                    lg.info(f"===> Placing {signal} MARKET Order (Reduce Only) ({symbol}) | Size: {size_to_close.normalize()} <===")
                    # Pass the original EXIT signal to place_trade for logging clarity
                    close_order = place_trade(exchange, symbol, signal, size_to_close, market_info, lg, reduce_only=True)

                    if close_order and close_order.get('id'):
                        lg.info(f"{NEON_GREEN}Position CLOSE order ({close_order['id']}) placed successfully for {symbol}.{RESET}")
                        # Optional: Wait and confirm position is actually closed here later
                    else:
                        lg.error(f"{NEON_RED}Failed to place CLOSE order for {symbol}. Manual intervention may be required!{RESET}")
                except Exception as close_err:
                    lg.error(f"{NEON_RED}Error encountered while trying to close {pos_side} position for {symbol}: {close_err}{RESET}", exc_info=True)
                    lg.warning(f"{NEON_YELLOW}Manual closing of position {symbol} may be needed!{RESET}")

            else: # Signal allows holding position
                # --- Handle Position Management (Break-Even, TSL Recovery) ---
                lg.debug(f"Signal ({signal}) allows holding {pos_side} position ({symbol}). Performing position management checks...")

                # Extract current protection levels and entry price safely
                try:
                    tsl_dist_str = open_position.get('trailingStopLoss')
                    tsl_active = tsl_dist_str and Decimal(tsl_dist_str) > 0
                except (KeyError, ValueError, InvalidOperation, TypeError): tsl_active = False

                current_sl: Optional[Decimal] = _safe_market_decimal(open_position.get('stopLossPrice'), 'pos.stopLossPrice', allow_zero=False)
                current_tp: Optional[Decimal] = _safe_market_decimal(open_position.get('takeProfitPrice'), 'pos.takeProfitPrice', allow_zero=False)
                entry_price: Optional[Decimal] = _safe_market_decimal(open_position.get('
This is an excellent foundation for a trading bot! It's well-structured, includes crucial features like logging, retry mechanisms, state management, and a modular strategy.

Here's an enhanced version focusing on:

1.  **Readability and Maintainability:** Adding type hints, more consistent docstrings, and clarifying comments.
2.  **Robustness:** Minor improvements in error handling and edge case considerations.
3.  **Clarity:** Ensuring variable names are descriptive and logic flows clearly.
4.  **Minor Refinements:** Small quality-of-life improvements, including the use of constants/enums.

I've kept the core strategy logic as is, as it's the user's domain, but enhanced the surrounding code.

---

```python
import os
import json
import time
import logging
import uuid # For generating unique client order IDs
from dotenv import load_dotenv
from colorama import init, Fore, Style
from datetime import datetime, timedelta
import pytz # For timezone handling
import math # For precision calculations (e.g., floor for quantities)
import sys # For graceful exit
from abc import ABC, abstractmethod # For abstract base class for strategy
from typing import Dict, Any, List, Optional, Union, Tuple

# Import pybit specific modules and exceptions
from pybit.unified_trading import HTTP, WebSocket
from pybit.exceptions import PybitAPIException, PybitRequestException, PybitAuthException

# Pandas and Pandas_TA for indicator calculations
import pandas as pd
import pandas_ta as ta

# Initialize colorama for colored terminal output
init(autoreset=True)

# --- Constants and Enums (for better readability and avoiding magic strings) ---
class OrderSide:
    """Defines standard order sides."""
    BUY = "Buy"
    SELL = "Sell"

class OrderType:
    """Defines standard order types."""
    MARKET = "Market"
    LIMIT = "Limit"

class Category:
    """Defines Bybit API categories."""
    LINEAR = "linear" # For perpetual futures

class AccountType:
    """Defines Bybit account types."""
    UNIFIED = "UNIFIED"

class TriggerBy:
    """Defines trigger types for stop orders on Bybit."""
    MARK_PRICE = "MarkPrice"
    LAST_PRICE = "LastPrice"
    INDEX_PRICE = "IndexPrice"

# Default ATR length used by pandas_ta and for SL/TP calculations if not specified in config
DEFAULT_ATR_LENGTH = 14 

# --- Logging Configuration ---
def setup_logging() -> None:
    """
    Configures the logging for the bot.
    Logs messages to both a file ('xrscalper.log') and the console.
    Suppresses excessive logging from external libraries like urllib3 and pybit.
    """
    log_file = 'xrscalper.log'
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file), # Log to file
            logging.StreamHandler()        # Log to console
        ]
    )
    # Silence excessive logging from external libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('pybit').setLevel(logging.WARNING) # Adjust if pybit is too verbose

setup_logging()

# --- Centralized API Call Retry and Error Handling ---
def retry_api_call(client_method: callable, *args, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Wrapper function to handle API call retries and error management.
    Applies exponential backoff for transient errors and exits for fatal ones.

    Args:
        client_method (callable): The pybit client method to call (e.g., client.get_kline).
        *args: Positional arguments for the client_method.
        **kwargs: Keyword arguments for the client_method.

    Returns:
        Optional[Dict[str, Any]]: The successful API response dictionary, or None if all retries fail.
    """
    max_retries = 3
    
    for i in range(max_retries):
        try:
            response = client_method(*args, **kwargs)
            if response and response.get('retCode') == 0:
                return response
            else:
                ret_code = response.get('retCode', 'N/A')
                error_msg = response.get('retMsg', 'Unknown API error')
                logging.warning(f"API returned error {ret_code} during {client_method.__name__}: {error_msg}. Retrying {i+1}/{max_retries}...")
                time.sleep(2 ** i) # Exponential backoff for API-returned errors
        except (PybitRequestException, PybitAPIException) as e:
            # These are transient errors like network issues, rate limits, etc.
            logging.warning(f"Transient API error during {client_method.__name__}: {e}. Retrying {i+1}/{max_retries}...")
            time.sleep(2 ** i) # Exponential backoff
        except PybitAuthException as e:
            # Authentication errors are fatal and require user intervention
            logging.critical(Fore.RED + f"FATAL AUTHENTICATION ERROR: {e}. Please check your API keys/permissions. Exiting." + Style.RESET_ALL)
            sys.exit(1) # Critical error, exit immediately
        except Exception as e:
            # Catch any other unexpected errors
            logging.critical(Fore.RED + f"Unhandled critical error during {client_method.__name__}: {e}" + Style.RESET_ALL, exc_info=True)
            sys.exit(1) # Unhandled critical error, exit immediately
    logging.error(Fore.RED + f"Max retries exhausted for {client_method.__name__}. Failed to get successful response." + Style.RESET_ALL)
    return None # Indicate failure after retries

# --- Bot State Management Class ---
class BotState:
    """
    Manages the persistent state of the bot, saving and loading from a JSON file.
    This ensures that open positions and initial balance are retained across restarts.
    """
    def __init__(self, state_file: str = 'bot_state.json') -> None:
        self.state_file = state_file
        self.data: Dict[str, Any] = {
            'open_positions': {}, # Stores details of currently open positions
            'initial_balance': None, # Initial balance for global loss tracking
            'last_run_time': None # Timestamp of the last successful bot loop iteration
        }
        self._load_state()

    def _load_state(self) -> None:
        """Loads the bot's state from the configured JSON file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    loaded_data = json.load(f)
                    # Convert timestamps back to datetime objects if needed, or store them as strings/ints
                    if 'last_run_time' in loaded_data and loaded_data['last_run_time'] is not None:
                        # Assuming timestamps are saved as Unix seconds for simplicity
                        loaded_data['last_run_time'] = datetime.fromtimestamp(loaded_data['last_run_time'], tz=pytz.utc) 
                    
                    # Ensure loaded data keys match expected structure, add defaults if missing
                    for key, default_val in self.data.items():
                        if key not in loaded_data:
                            loaded_data[key] = default_val
                    self.data.update(loaded_data)
                logging.info(f"Bot state loaded from {self.state_file}.")
            except json.JSONDecodeError as e:
                logging.error(Fore.RED + f"Error decoding bot state file {self.state_file}: {e}. Starting with clean state." + Style.RESET_ALL)
            except Exception as e:
                logging.error(Fore.RED + f"Unexpected error loading bot state file {self.state_file}: {e}. Starting with clean state." + Style.RESET_ALL)
        else:
            logging.info(f"No bot state file found at {self.state_file}. Starting with clean state.")

    def save_state(self) -> None:
        """Saves the current bot's state to the configured JSON file."""
        try:
            # Prepare data for serialization (e.g., convert datetime to timestamp)
            serializable_data = self.data.copy()
            if 'last_run_time' in serializable_data and serializable_data['last_run_time'] is not None:
                serializable_data['last_run_time'] = int(serializable_data['last_run_time'].timestamp())
            
            with open(self.state_file, 'w') as f:
                json.dump(serializable_data, f, indent=4)
            logging.info(f"Bot state saved to {self.state_file}.")
        except Exception as e:
            logging.error(Fore.RED + f"Error saving bot state to {self.state_file}: {e}" + Style.RESET_ALL)

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieves a value from the bot's state."""
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Sets a value in the bot's state."""
        self.data[key] = value

# --- Configuration and Environment Variable Loading ---
def load_config() -> Dict[str, Any]:
    """
    Loads configuration from 'config.json' or creates a default if not found.
    If a new default config is created, the bot will exit to prompt user review.
    """
    config_file = 'config.json'
    default_config: Dict[str, Any] = {
        "symbols_to_trade": ["BTCUSDT", "ETHUSDT"], # List of symbols to trade (e.g., "BTCUSDT", "ETHUSDT")
        "interval": "5", # Candlestick timeframe (e.g., "1", "5", "60" for hours, "D" for daily)
        "enable_trading": False, # Set to True to enable live trading and order placement
        "use_sandbox": True,    # Set to False for real money trading on Bybit mainnet
        "risk_per_trade": 0.01, # Max percentage of total balance to risk per trade (e.g., 0.01 = 1%)
        "leverage": 10,         # Desired leverage for derivatives trades
        "max_positions": 2,     # Maximum number of simultaneous open positions allowed
        "order_type": OrderType.MARKET, # "Market" or "Limit" for entry orders
        "limit_order_price_offset_percentage": 0.0005, # 0.05% offset for limit orders (e.g., buy below market, sell above)
        "indicators": { # Enable/disable specific technical indicators
            "ema": True, "momentum": True, "stochrsi": True, "rsi": True,
            "bbands": True, "vwap": True, "cci": True, "williamsr": True,
            "mfi": True, "psar": True, "sma": True,
            "fibonacci_pivots": True # Enable/disable Fibonacci Pivots calculation
        },
        "indicator_params": { # Configurable parameters for technical indicators
            "ema_lengths": [9, 20, 50], # Short, Medium, Long EMA lengths
            "rsi_length": 14,
            "stochrsi_lengths": [14, 14, 3, 3], # (rsi_length, k_length, d_length, smooth_k_length)
            "bbands_settings": [20, 2], # (length, standard_deviations)
            "momentum_length": 14,
            "cci_length": 14,
            "williamsr_length": 14,
            "mfi_length": 14,
            "psar_settings": [0.02, 0.2], # (initial_acceleration_factor, max_acceleration_factor)
            "sma_lengths": [10, 30] # Short, Long SMA lengths
        },
        "weight_sets": { # Different sets of weights for strategy scoring
            "scalping": { # Example weight set for a scalping strategy
                "ema_weight": 0.2, "momentum_weight": 0.15, "stochrsi_weight": 0.15,
                "rsi_weight": 0.1, "bbands_weight": 0.1, "vwap_weight": 0.05,
                "cci_weight": 0.05, "williamsr_weight": 0.05, "mfi_weight": 0.05,
                "psar_weight": 0.05, "sma_weight": 0.05, "order_book_weight": 0.1,
                "fibonacci_pivots_weight": 0.1
            },
            "default": { # Default weight set
                "ema_weight": 0.2, "momentum_weight": 0.1, "stochrsi_weight": 0.1,
                "rsi_weight": 0.15, "bbands_weight": 0.1, "vwap_weight": 0.05,
                "cci_weight": 0.05, "williamsr_weight": 0.05, "mfi_weight": 0.05,
                "psar_weight": 0.05, "sma_weight": 0.05, "order_book_weight": 0.1,
                "fibonacci_pivots_weight": 0.1
            }
        },
        "active_weight_set": "scalping", # The name of the weight set to use from "weight_sets"
        "signal_threshold": 0.15, # Minimum difference between buy/sell scores to trigger a signal
        "stop_loss_atr_multiple": 1.5,      # Initial Stop Loss distance as a multiple of ATR
        "take_profit_atr_multiple": 3.0,    # Initial Take Profit distance as a multiple of ATR (for final TP)
        "trailing_stop_callback_rate": 0.005, # 0.5% callback rate for Trailing Stop Loss (0 to disable)
        "break_even_trigger_atr_multiple": 1.0, # Move SL to BE when profit reaches this ATR multiple (0 to disable)
        "break_even_buffer_atr_percentage": 0.05, # % of ATR to add as buffer for break-even SL (to cover fees)
        "partial_take_profit_levels": [     # List of [ATR_multiple, percentage_of_position_to_close]
            [1.5, 0.25], # Take 25% profit at 1.5x ATR
            [2.5, 0.50]  # Take 50% profit (of remaining contracts) at 2.5x ATR
        ],
        "time_based_exit_minutes": 120,     # Optional: exit after X minutes if no other exit (0 to disable)
        "loop_delay_seconds": 10,           # Delay between main bot loop iterations
        "heartbeat_interval_minutes": 60,   # Log a heartbeat message every X minutes
        "max_total_loss_percentage": 0.10,  # Stop bot if total balance drops by this percentage (0.10 = 10%)
        "close_positions_on_exit": False,    # Attempt to close all open positions on graceful shutdown
        "state_file": "bot_state.json"      # File to save/load bot state
    }

    if not os.path.exists(config_file):
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=4)
        logging.info(f"Created default '{config_file}'. {Fore.YELLOW}Please review and customize it before enabling live trading.{Style.RESET_ALL}")
        # Exit if config is newly created to force user review and prevent accidental live trading
        sys.exit(0)
    else:
        with open(config_file, 'r') as f:
            config = json.load(f)
        logging.info(f"Loaded '{config_file}'.")
        # Merge default config with loaded config to ensure all keys exist
        # This allows adding new config options without breaking existing user configs
        merged_config = {**default_config, **config}
        # For nested dictionaries like 'indicators' or 'indicator_params', a deeper merge might be needed
        # For simplicity, if a top-level key exists in config, it overrides default_config entirely.
        # If granular control is needed, implement a recursive merge.
        # For now, let's just ensure nested dicts are updated if they exist in the loaded config
        for key in ['indicators', 'indicator_params', 'weight_sets']:
            if key in config and isinstance(config[key], dict):
                merged_config[key] = {**default_config.get(key, {}), **config[key]}

        validate_config(merged_config)
        return merged_config

def validate_config(config: Dict[str, Any]) -> None:
    """
    Validates critical configuration parameters to ensure safe operation.
    Exits the program if a critical validation fails.
    """
    if not (0 < config.get('risk_per_trade', 0) <= 0.1): # Max 10% risk
        logging.error(Fore.RED + "Config Error: 'risk_per_trade' must be between 0 and 0.1 (0% to 10%).")
        sys.exit(1)
    if not (config.get('leverage', 0) > 0):
        logging.error(Fore.RED + "Config Error: 'leverage' must be a positive number.")
        sys.exit(1)
    if not isinstance(config.get('symbols_to_trade'), list) or not config['symbols_to_trade']:
        logging.error(Fore.RED + "Config Error: 'symbols_to_trade' must be a non-empty list of strings.")
        sys.exit(1)
    if config.get('active_weight_set') not in config.get('weight_sets', {}):
        logging.error(Fore.RED + f"Config Error: 'active_weight_set' '{config['active_weight_set']}' not found in 'weight_sets'.")
        sys.exit(1)
    if config.get('order_type') not in [OrderType.MARKET, OrderType.LIMIT]:
        logging.error(Fore.RED + f"Config Error: 'order_type' must be '{OrderType.MARKET}' or '{OrderType.LIMIT}'.")
        sys.exit(1)
    for level, percentage in config.get('partial_take_profit_levels', []):
        if not (0 < level) or not (0 < percentage <= 1):
            logging.error(Fore.RED + "Config Error: 'partial_take_profit_levels' must have positive ATR multiples and percentages between 0 and 1.")
            sys.exit(1)
    if not (0 <= config.get('max_total_loss_percentage', 0) <= 1):
        logging.error(Fore.RED + "Config Error: 'max_total_loss_percentage' must be between 0 and 1 (0% to 100%).")
        sys.exit(1)
    if not isinstance(config.get('loop_delay_seconds'), (int, float)) or config['loop_delay_seconds'] <= 0:
        logging.error(Fore.RED + "Config Error: 'loop_delay_seconds' must be a positive number.")
        sys.exit(1)
    if not isinstance(config.get('heartbeat_interval_minutes'), (int, float)) or config['heartbeat_interval_minutes'] < 0:
        logging.error(Fore.RED + "Config Error: 'heartbeat_interval_minutes' must be a non-negative number.")
        sys.exit(1)
    if config.get('stop_loss_atr_multiple', 0) <= 0 and config.get('trailing_stop_callback_rate', 0) <= 0:
        logging.warning(Fore.YELLOW + "Warning: Neither 'stop_loss_atr_multiple' nor 'trailing_stop_callback_rate' is set. Positions will not have automatic stops." + Style.RESET_ALL)

    logging.info(Fore.GREEN + "Configuration validated successfully." + Style.RESET_ALL)


def load_env_vars() -> Tuple[str, str, pytz.tzinfo.BaseTzInfo]:
    """
    Loads environment variables for API keys and timezone from a .env file.
    Requires BYBIT_API_KEY and BYBIT_API_SECRET.
    """
    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    timezone_str = os.getenv("TIMEZONE", "UTC") # Default to UTC if not set

    if not api_key or not api_secret:
        logging.error(Fore.RED + "BYBIT_API_KEY and BYBIT_API_SECRET must be set in the .env file." + Style.RESET_ALL)
        sys.exit(1)

    try:
        timezone = pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        logging.warning(Fore.YELLOW + f"Unknown timezone '{timezone_str}'. Defaulting to UTC." + Style.RESET_ALL)
        timezone = pytz.utc

    return api_key, api_secret, timezone

# --- Strategy Base Class ---
class BaseStrategy(ABC):
    """
    Abstract Base Class for trading strategies.
    All concrete strategies must inherit from this class and implement `generate_signal`.
    """
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.weights = self.config['weight_sets'][self.config['active_weight_set']]
        self.indicator_params = self.config['indicator_params']

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame, order_book_sentiment: float, fib_pivots: Dict[str, float]) -> Dict[str, Any]:
        """
        Generates a trading signal based on market data, order book sentiment, and Fibonacci pivots.
        Must be implemented by subclasses.

        Args:
            df (pd.DataFrame): Historical candlestick data with indicators.
            order_book_sentiment (float): Sentiment score from order book analysis.
            fib_pivots (dict): Dictionary of calculated Fibonacci pivot points (P, R1, S1, etc.).

        Returns:
            dict: {
                'signal': int (1 for Buy, -1 for Sell, 0 for No Signal),
                'strategy_info': dict (any additional info to log, e.g., indicator values)
            }
        """
        pass

# --- Example Concrete Strategy (Your Strategy Goes Here!) ---
class MyScalpingStrategy(BaseStrategy):
    """
    An example scalping strategy that generates buy/sell signals based on
    a combination of technical indicators, order book sentiment, and Fibonacci pivots.
    This strategy is designed to be a starting point and should be customized.
    """
    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        logging.info(Fore.GREEN + "MyScalpingStrategy initialized." + Style.RESET_ALL)

    def generate_signal(self, df: pd.DataFrame, order_book_sentiment: float, fib_pivots: Dict[str, float]) -> Dict[str, Any]:
        """
        Generates a trading signal based on a weighted scoring system of various indicators,
        order book sentiment, and Fibonacci pivot point interactions.
        """
        if df.empty or len(df) < 2: # Ensure enough data for indicators and previous candle comparison
            return {'signal': 0, 'strategy_info': {'reason': 'Insufficient data for signal generation'}}

        current_data = df.iloc[-1]
        previous_data = df.iloc[-2]
        current_price = current_data['close']
        
        buy_score = 0.0
        sell_score = 0.0
        strategy_info: Dict[str, Any] = {'current_price': round(current_price, 4)}

        # Helper to safely get indicator value and add to strategy_info, handling NaN
        def get_indicator_val(data_row: pd.Series, col: str, decimal_places: int = 4) -> Optional[float]:
            if col in data_row and pd.notna(data_row[col]):
                val = data_row[col]
                strategy_info[col] = round(val, decimal_places)
                return val
            return None

        # --- Indicator-based scoring (EXAMPLE LOGIC - REPLACE WITH YOURS) ---
        # Access indicator parameters dynamically from self.indicator_params

        # EMA Crossover (e.g., EMA9 crosses above EMA20 for buy)
        if self.config['indicators'].get('ema'):
            ema_short_len = self.indicator_params['ema_lengths'][0]
            ema_long_len = self.indicator_params['ema_lengths'][1]
            ema_short_col = f'EMA_{ema_short_len}'
            ema_long_col = f'EMA_{ema_long_len}'
            curr_ema_short = get_indicator_val(current_data, ema_short_col)
            curr_ema_long = get_indicator_val(current_data, ema_long_col)
            prev_ema_short = get_indicator_val(previous_data, ema_short_col) # Get from previous data
            prev_ema_long = get_indicator_val(previous_data, ema_long_col) # Get from previous data

            if all(v is not None for v in [curr_ema_short, curr_ema_long, prev_ema_short, prev_ema_long]):
                if curr_ema_short > curr_ema_long and prev_ema_short <= prev_ema_long:
                    buy_score += self.weights.get('ema_weight', 0.0)
                    strategy_info['ema_crossover'] = 'bullish'
                elif curr_ema_short < curr_ema_long and prev_ema_short >= prev_ema_long:
                    sell_score += self.weights.get('ema_weight', 0.0)
                    strategy_info['ema_crossover'] = 'bearish'

        # RSI (Oversold/Overbought)
        if self.config['indicators'].get('rsi'):
            rsi_len = self.indicator_params['rsi_length']
            rsi_col = f'RSI_{rsi_len}'
            rsi_val = get_indicator_val(current_data, rsi_col, 2)
            if rsi_val is not None:
                if rsi_val < 30: # Oversold
                    buy_score += self.weights.get('rsi_weight', 0.0) * (1 - rsi_val / 30) # Stronger signal if deeper oversold
                    strategy_info['rsi_state'] = 'oversold'
                elif rsi_val > 70: # Overbought
                    sell_score += self.weights.get('rsi_weight', 0.0) * ((rsi_val - 70) / 30) # Stronger signal if deeper overbought
                    strategy_info['rsi_state'] = 'overbought'

        # Stochastic RSI (Oversold/Overbought confirmation)
        if self.config['indicators'].get('stochrsi'):
            stochrsi_lens = self.indicator_params['stochrsi_lengths']
            # pandas_ta names: STOCHRSIk_{length}_{rsi_length}_{k}_{d}, STOCHRSId_{length}_{rsi_length}_{k}_{d}
            stochrsi_k_col = f'STOCHRSIk_{stochrsi_lens[0]}_{stochrsi_lens[1]}_{stochrsi_lens[2]}_{stochrsi_lens[3]}'
            stochrsi_d_col = f'STOCHRSId_{stochrsi_lens[0]}_{stochrsi_lens[1]}_{stochrsi_lens[2]}_{stochrsi_lens[3]}'
            k_val = get_indicator_val(current_data, stochrsi_k_col, 2)
            d_val = get_indicator_val(current_data, stochrsi_d_col, 2)
            if k_val is not None and d_val is not None:
                if k_val < 20 and d_val < 20 and k_val > d_val: # Oversold and K crosses above D
                    buy_score += self.weights.get('stochrsi_weight', 0.0)
                    strategy_info['stochrsi_state'] = 'bullish_cross_oversold'
                elif k_val > 80 and d_val > 80 and k_val < d_val: # Overbought and K crosses below D
                    sell_score += self.weights.get('stochrsi_weight', 0.0)
                    strategy_info['stochrsi_state'] = 'bearish_cross_overbought'

        # Bollinger Bands (Price breaking out of bands)
        if self.config['indicators'].get('bbands'):
            bb_len, bb_std = self.indicator_params['bbands_settings']
            bbl_col = f'BBL_{bb_len}_{bb_std}.0'
            bbu_col = f'BBU_{bb_len}_{bb_std}.0'
            bbl = get_indicator_val(current_data, bbl_col)
            bbu = get_indicator_val(current_data, bbu_col)
            
            if bbl is not None and bbu is not None:
                if current_price < bbl and previous_data['close'] >= bbl: # Price breaks below lower band (reversal)
                    buy_score += self.weights.get('bbands_weight', 0.0) * 0.5 
                    strategy_info['bbands_break'] = 'lower_band_break'
                elif current_price > bbu and previous_data['close'] <= bbu: # Price breaks above upper band (reversal)
                    sell_score += self.weights.get('bbands_weight', 0.0) * 0.5 
                    strategy_info['bbands_break'] = 'upper_band_break'

        # PSAR (Parabolic SAR reversal)
        if self.config['indicators'].get('psar'):
            psar_af0, psar_af_max = self.indicator_params['psar_settings']
            # pandas_ta returns PSARr (reversal), PSARl (long), PSARs (short)
            # PSARr is typically the one indicating actual reversal point.
            psar_r_col = f'PSARr_{psar_af0}_{psar_af_max}'
            psar_val = get_indicator_val(current_data, psar_r_col)

            if psar_val is not None:
                if current_price > psar_val and previous_data['close'] <= psar_val: # Price crosses above PSAR (bullish reversal)
                    buy_score += self.weights.get('psar_weight', 0.0)
                    strategy_info['psar_reversal'] = 'bullish'
                elif current_price < psar_val and previous_data['close'] >= psar_val: # Price crosses below PSAR (bearish reversal)
                    sell_score += self.weights.get('psar_weight', 0.0)
                    strategy_info['psar_reversal'] = 'bearish'
                # Also log if PSARl or PSARs indicate current trend
                if f'PSARl_{psar_af0}_{psar_af_max}' in current_data and pd.notna(current_data[f'PSARl_{psar_af0}_{psar_af_max}']):
                    strategy_info['psar_l'] = round(current_data[f'PSARl_{psar_af0}_{psar_af_max}'], 4)
                if f'PSARs_{psar_af0}_{psar_af_max}' in current_data and pd.notna(current_data[f'PSARs_{psar_af0}_{psar_af_max}']):
                    strategy_info['psar_s'] = round(current_data[f'PSARs_{psar_af0}_{psar_af_max}'], 4)


        # Momentum
        if self.config['indicators'].get('momentum'):
            mom_len = self.indicator_params['momentum_length']
            mom_col = f'MOM_{mom_len}'
            mom_val = get_indicator_val(current_data, mom_col)
            prev_mom_val = get_indicator_val(previous_data, mom_col) # Get from previous data
            if mom_val is not None and prev_mom_val is not None:
                if mom_val > 0 and prev_mom_val <= 0: # Momentum turning positive (crossing zero line)
                    buy_score += self.weights.get('momentum_weight', 0.0) * 0.5
                    strategy_info['momentum_cross'] = 'positive'
                elif mom_val < 0 and prev_mom_val >= 0: # Momentum turning negative (crossing zero line)
                    sell_score += self.weights.get('momentum_weight', 0.0) * 0.5
                    strategy_info['momentum_cross'] = 'negative'

        # VWAP (Price above/below VWAP)
        if self.config['indicators'].get('vwap') and 'VWAP' in current_data: # VWAP column name is fixed
            vwap_val = get_indicator_val(current_data, 'VWAP')
            if vwap_val is not None:
                if current_price > vwap_val: # Price above VWAP (bullish)
                    buy_score += self.weights.get('vwap_weight', 0.0) * 0.2
                    strategy_info['vwap_state'] = 'above'
                elif current_price < vwap_val: # Price below VWAP (bearish)
                    sell_score += self.weights.get('vwap_weight', 0.0) * 0.2
                    strategy_info['vwap_state'] = 'below'

        # CCI (Overbought/Oversold)
        if self.config['indicators'].get('cci'):
            cci_len = self.indicator_params['cci_length']
            cci_col = f'CCI_{cci_len}_0.015' # Default cci uses 0.015
            cci_val = get_indicator_val(current_data, cci_col, 2)
            if cci_val is not None:
                if cci_val < -100: # Oversold
                    buy_score += self.weights.get('cci_weight', 0.0) * 0.5
                    strategy_info['cci_state'] = 'oversold'
                elif cci_val > 100: # Overbought
                    sell_score += self.weights.get('cci_weight', 0.0) * 0.5
                    strategy_info['cci_state'] = 'overbought'

        # Williams %R
        if self.config['indicators'].get('williamsr'):
            willr_len = self.indicator_params['williamsr_length']
            willr_col = f'WLLR_{willr_len}'
            willr_val = get_indicator_val(current_data, willr_col, 2)
            if willr_val is not None:
                if willr_val < -80: # Oversold
                    buy_score += self.weights.get('williamsr_weight', 0.0) * 0.5
                    strategy_info['williamsr_state'] = 'oversold'
                elif willr_val > -20: # Overbought
                    sell_score += self.weights.get('williamsr_weight', 0.0) * 0.5
                    strategy_info['williamsr_state'] = 'overbought'

        # MFI
        if self.config['indicators'].get('mfi'):
            mfi_len = self.indicator_params['mfi_length']
            mfi_col = f'MFI_{mfi_len}'
            mfi_val = get_indicator_val(current_data, mfi_col, 2)
            if mfi_val is not None:
                if mfi_val < 20: # Oversold
                    buy_score += self.weights.get('mfi_weight', 0.0) * 0.5
                    strategy_info['mfi_state'] = 'oversold'
                elif mfi_val > 80: # Overbought
                    sell_score += self.weights.get('mfi_weight', 0.0) * 0.5
                    strategy_info['mfi_state'] = 'overbought'

        # SMA Crossover (e.g., SMA10 crosses above SMA30)
        if self.config['indicators'].get('sma'):
            sma_short_len = self.indicator_params['sma_lengths'][0]
            sma_long_len = self.indicator_params['sma_lengths'][1]
            sma_short_col = f'SMA_{sma_short_len}'
            sma_long_col = f'SMA_{sma_long_len}'
            curr_sma_short = get_indicator_val(current_data, sma_short_col)
            curr_sma_long = get_indicator_val(current_data, sma_long_col)
            prev_sma_short = get_indicator_val(previous_data, sma_short_col) # Get from previous data
            prev_sma_long = get_indicator_val(previous_data, sma_long_col) # Get from previous data

            if all(v is not None for v in [curr_sma_short, curr_sma_long, prev_sma_short, prev_sma_long]):
                if curr_sma_short > curr_sma_long and prev_sma_short <= prev_sma_long:
                    buy_score += self.weights.get('sma_weight', 0.0)
                    strategy_info['sma_crossover'] = 'bullish'
                elif curr_sma_short < curr_sma_long and prev_sma_short >= prev_sma_long:
                    sell_score += self.weights.get('sma_weight', 0.0)
                    strategy_info['sma_crossover'] = 'bearish'

        # --- Order Book Sentiment Integration ---
        strategy_info['order_book_sentiment'] = round(order_book_sentiment, 4)
        buy_score += self.weights.get('order_book_weight', 0.0) * max(0, order_book_sentiment) # Positive sentiment boosts buy
        sell_score += self.weights.get('order_book_weight', 0.0) * max(0, -order_book_sentiment) # Negative sentiment boosts sell

        # --- Fibonacci Pivot Points Integration (EXAMPLE LOGIC) ---
        if self.config['indicators'].get('fibonacci_pivots') and fib_pivots:
            strategy_info['fib_pivots'] = {k: round(v, 4) for k, v in fib_pivots.items()} # Log rounded pivots
            pivot_buffer_pct = 0.0005 # 0.05% buffer around pivot levels for interaction

            # Check for price interaction with Support levels (potential buy signals)
            if 'S1' in fib_pivots and fib_pivots['S1'] > 0: # Ensure valid pivot value
                s1_low_bound = fib_pivots['S1'] * (1 - pivot_buffer_pct)
                s1_high_bound = fib_pivots['S1'] * (1 + pivot_buffer_pct)
                if s1_low_bound <= current_price <= s1_high_bound:
                    # Price is near S1
                    if previous_data['close'] < fib_pivots['S1'] and current_data['close'] > fib_pivots['S1']: # Bounce from S1
                        buy_score += self.weights.get('fibonacci_pivots_weight', 0.0) * 0.75 # Stronger contribution for bounce
                        strategy_info['fib_pivot_interaction'] = 'bounce_from_S1'
                    elif current_price > fib_pivots['S1'] and previous_data['close'] <= fib_pivots['S1']: # Break above S1 (continuation)
                        # This could be a retest of S1 and continuation upwards
                        buy_score += self.weights.get('fibonacci_pivots_weight', 0.0) * 0.25
                        strategy_info['fib_pivot_interaction'] = 'break_above_S1'
            
            # Check for price interaction with Resistance levels (potential sell signals)
            if 'R1' in fib_pivots and fib_pivots['R1'] > 0: # Ensure valid pivot value
                r1_low_bound = fib_pivots['R1'] * (1 - pivot_buffer_pct)
                r1_high_bound = fib_pivots['R1'] * (1 + pivot_buffer_pct)
                if r1_low_bound <= current_price <= r1_high_bound:
                    # Price is near R1
                    if previous_data['close'] > fib_pivots['R1'] and current_data['close'] < fib_pivots['R1']: # Bounce from R1
                        sell_score += self.weights.get('fibonacci_pivots_weight', 0.0) * 0.75
                        strategy_info['fib_pivot_interaction'] = 'bounce_from_R1'
                    elif current_price < fib_pivots['R1'] and previous_data['close'] >= fib_pivots['R1']: # Break below R1 (continuation)
                        # This could be a retest of R1 and continuation downwards
                        sell_score += self.weights.get('fibonacci_pivots_weight', 0.0) * 0.25
                        strategy_info['fib_pivot_interaction'] = 'break_below_R1'

            # Example for R3 Break (Strong Bullish)
            if 'R3' in fib_pivots and fib_pivots['R3'] > 0:
                if current_price > fib_pivots['R3'] * (1 + pivot_buffer_pct) and previous_data['close'] <= fib_pivots['R3']:
                    buy_score += self.weights.get('fibonacci_pivots_weight', 0.0) * 1.5 # Very strong signal
                    strategy_info['fib_pivot_interaction'] = 'strong_break_above_R3'

            # Example for S3 Break (Strong Bearish)
            if 'S3' in fib_pivots and fib_pivots['S3'] > 0:
                if current_price < fib_pivots['S3'] * (1 - pivot_buffer_pct) and previous_data['close'] >= fib_pivots['S3']:
                    sell_score += self.weights.get('fibonacci_pivots_weight', 0.0) * 1.5 # Very strong signal
                    strategy_info['fib_pivot_interaction'] = 'strong_break_below_S3'


        # --- Final Signal Decision ---
        signal_threshold = self.config.get('signal_threshold', 0.15) # Get from config
        if buy_score > sell_score + signal_threshold: # If buy score significantly higher
            strategy_info['final_score_buy'] = round(buy_score, 2)
            strategy_info['final_score_sell'] = round(sell_score, 2)
            strategy_info['decision'] = 'BUY'
            return {'signal': 1, 'strategy_info': strategy_info}
        elif sell_score > buy_score + signal_threshold: # If sell score significantly higher
            strategy_info['final_score_buy'] = round(buy_score, 2)
            strategy_info['final_score_sell'] = round(sell_score, 2)
            strategy_info['decision'] = 'SELL'
            return {'signal': -1, 'strategy_info': strategy_info}
        else: # No clear signal
            strategy_info['final_score_buy'] = round(buy_score, 2)
            strategy_info['final_score_sell'] = round(sell_score, 2)
            strategy_info['decision'] = 'NONE'
            return {'signal': 0, 'strategy_info': strategy_info}

# --- XR Scalper Bot Class (Core Logic) ---
class XRScalperBot:
    """
    The main class for the XR Scalper Bot, orchestrating data fetching,
    indicator calculation, strategy execution, and trade management.
    """
    def __init__(self) -> None:
        self.config: Dict[str, Any] = load_config()
        self.api_key, self.api_secret, self.timezone = load_env_vars()

        self.http_client: HTTP = self._initialize_http_client()
        self.instrument_info_cache: Dict[str, Dict[str, float]] = {} # Cache for symbol precision info

        self.bot_state = BotState(state_file=self.config['state_file'])
        # Load open positions and initial balance from state
        self.open_positions: Dict[str, Dict[str, Any]] = self.bot_state.get('open_positions', {})
        self.initial_balance: Optional[float] = self.bot_state.get('initial_balance')
        
        self.last_heartbeat: datetime = datetime.now(self.timezone)

        # Initialize the trading strategy
        self.strategy: BaseStrategy = MyScalpingStrategy(self.config) # You can swap this with other strategies

        logging.info(Fore.CYAN + "XR Scalper Bot Initialized." + Style.RESET_ALL)
        logging.info(f"Trading Enabled: {self.config['enable_trading']}")
        logging.info(f"Using Sandbox: {self.config['use_sandbox']}")
        logging.info(f"Symbols to Trade: {self.config['symbols_to_trade']}")
        logging.info(f"Candlestick Interval: {self.config['interval']}")
        logging.info(f"Risk per Trade: {self.config['risk_per_trade'] * 100}%")
        logging.info(f"Leverage: {self.config['leverage']}x")
        logging.info(f"Active Weight Set: {self.config['active_weight_set']}")
        logging.info(f"Bot state file: {self.config['state_file']}")

    def _initialize_http_client(self) -> HTTP:
        """
        Initializes the pybit HTTP client and tests connectivity.
        Fetches and sets initial account balance if not already loaded from state.
        """
        client = HTTP(
            testnet=self.config['use_sandbox'],
            api_key=self.api_key,
            api_secret=self.api_secret,
            # pybit handles rate limiting internally by default.
            # recv_window can be set if needed in pybit constructor, but default is usually fine.
        )

        if self.config['use_sandbox']:
            logging.warning(Fore.YELLOW + "Running in Sandbox Mode. No real funds will be used." + Style.RESET_ALL)
        else:
            logging.info(Fore.GREEN + "Running in Live Trading Mode. Use with caution!" + Style.RESET_ALL)

        try:
            # Test connection and fetch time
            server_time_response = retry_api_call(client.get_server_time)
            if server_time_response:
                server_time_ms = server_time_response.get('result', {}).get('timeSecond', 0) * 1000 # Convert to ms
                logging.info(f"Successfully connected to Bybit. Server time: {datetime.fromtimestamp(server_time_ms / 1000, tz=self.timezone)}")
            else:
                logging.error(Fore.RED + "Failed to get server time. Check API connection. Exiting." + Style.RESET_ALL)
                sys.exit(1)
        except Exception as e:
            logging.error(Fore.RED + f"Failed to connect to Bybit: {e}. Exiting." + Style.RESET_ALL)
            sys.exit(1)

        # If initial_balance not loaded from state, fetch it
        if self.initial_balance is None and self.config['enable_trading'] and not self.config['use_sandbox']:
            self.initial_balance = self.get_account_balance()
            if self.initial_balance <= 0:
                logging.error(Fore.RED + "Initial account balance is zero or negative. Cannot proceed with live trading." + Style.RESET_ALL)
                sys.exit(1)
            self.bot_state.set('initial_balance', self.initial_balance) # Save to state
            logging.info(f"Initial account balance: {self.initial_balance:.2f} USDT for loss tracking.")

        return client

    def _get_symbol_precision(self, symbol: str, category: str = Category.LINEAR) -> Optional[Dict[str, float]]:
        """
        Fetches and caches instrument info (precision) for a given symbol.
        This info is crucial for correct order sizing and pricing.
        """
        if symbol in self.instrument_info_cache:
            return self.instrument_info_cache[symbol]

        response = retry_api_call(self.http_client.get_instrument_info, category=category, symbol=symbol)
        if response and response.get('retCode') == 0:
            instrument_list = response.get('result', {}).get('list', [])
            if instrument_list:
                info = instrument_list[0]
                precision_data = {
                    'basePrecision': float(info.get('lotSizeFilter', {}).get('basePrecision', '0.000001')),
                    'minOrderQty': float(info.get('lotSizeFilter', {}).get('minOrderQty', '0')),
                    'maxOrderQty': float(info.get('lotSizeFilter', {}).get('maxOrderQty', '99999999')),
                    'tickSize': float(info.get('priceFilter', {}).get('tickSize', '0.000001'))
                }
                self.instrument_info_cache[symbol] = precision_data
                logging.info(f"Cached precision info for {symbol}: {precision_data}")
                return precision_data
            else:
                logging.error(Fore.RED + f"No instrument info found for {symbol}." + Style.RESET_ALL)
        else:
            logging.error(Fore.RED + f"Failed to fetch instrument info for {symbol}: {response.get('retMsg', 'Unknown error') if response else 'No response'}" + Style.RESET_ALL)
        return None

    def _apply_qty_precision(self, symbol: str, qty: float) -> float:
        """
        Applies quantity precision based on instrument info fetched from the exchange.
        Also checks against min/max order quantities. Uses math.floor to be conservative.
        """
        precision_info = self._get_symbol_precision(symbol)
        if not precision_info:
            logging.error(Fore.RED + f"Could not get precision info for {symbol}. Cannot apply quantity precision." + Style.RESET_ALL)
            return 0.0 # Critical for trading, return 0 to prevent bad orders

        base_precision = precision_info['basePrecision']
        min_qty = precision_info['minOrderQty']
        max_qty = precision_info['maxOrderQty']

        # Adjust quantity to the nearest multiple of basePrecision, using floor to be conservative
        adjusted_qty = math.floor(qty / base_precision) * base_precision
        
        # Ensure quantity is within min/max limits
        if adjusted_qty < min_qty:
            logging.warning(f"Adjusted quantity {adjusted_qty:.6f} for {symbol} is less than minOrderQty {min_qty}. Setting to 0.")
            return 0.0
        if adjusted_qty > max_qty:
            logging.warning(f"Adjusted quantity {adjusted_qty:.6f} for {symbol} is greater than maxOrderQty {max_qty}. Capping at max.")
            return max_qty

        return adjusted_qty

    def _apply_price_precision(self, symbol: str, price: float) -> float:
        """
        Applies price precision (tick size) based on instrument info.
        """
        precision_info = self._get_symbol_precision(symbol)
        if not precision_info:
            logging.error(Fore.RED + f"Could not get precision info for {symbol}. Cannot apply price precision." + Style.RESET_ALL)
            return price # Return original, but this might lead to errors

        tick_size = precision_info['tickSize']
        adjusted_price = round(price / tick_size) * tick_size
        return adjusted_price

    def fetch_kline_data(self, symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
        """
        Fetches historical candlestick data for a given symbol and interval.
        Pulls more data than strictly needed for indicators to ensure enough history.
        """
        response = retry_api_call(self.http_client.get_kline, category=Category.LINEAR, symbol=symbol, interval=interval, limit=limit)
        if not response: # Handle API call failure
            return pd.DataFrame() # Return empty on API call failure

        ohlcv = response.get('result', {}).get('list', [])
        if not ohlcv:
            logging.warning(f"No kline data found for {symbol} with interval {interval}.")
            return pd.DataFrame() # Return empty if list is empty

        # pybit returns data from newest to oldest, so reverse for pandas_ta
        ohlcv.reverse()
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms', utc=True).dt.tz_convert(self.timezone)
        df.set_index('timestamp', inplace=True)
        
        # Ensure numeric types and handle potential conversion errors
        for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df.dropna(inplace=True) # Drop any rows that couldn't be converted
        return df

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates various technical indicators using pandas_ta based on config settings.
        Ensures data is numeric and handles initial NaN values from indicator calculations.
        """
        if df.empty:
            logging.warning("Empty DataFrame passed to calculate_indicators.")
            return df

        # Ensure essential columns are present and numeric before proceeding
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                logging.warning(f"Missing required column '{col}' in DataFrame for indicator calculation.")
                return df # Cannot proceed without essential columns
            df[col] = pd.to_numeric(df[col], errors='coerce') # Ensure numeric, coerce errors to NaN

        # Drop any rows with NaN values that might result from initial data loading or coercion
        initial_rows = len(df)
        df.dropna(inplace=True)
        if len(df) < initial_rows:
            logging.debug(f"Dropped {initial_rows - len(df)} rows due to NaN values before indicator calculation.")
        if df.empty:
            logging.warning("DataFrame became empty after initial NaN drop (likely insufficient data for indicators).")
            return df

        # Access indicator parameters dynamically
        indicator_params = self.config['indicator_params']

        # EMA (e.g., 9, 20, 50)
        if self.config['indicators'].get('ema'):
            for length in indicator_params.get('ema_lengths', []):
                df.ta.ema(close='close', length=length, append=True)

        # Momentum (e.g., 14 periods)
        if self.config['indicators'].get('momentum'):
            df.ta.mom(close='close', length=indicator_params.get('momentum_length', 14), append=True)

        # Stochastic RSI
        if self.config['indicators'].get('stochrsi'):
            stochrsi_lens = indicator_params.get('stochrsi_lengths', [14, 14, 3, 3])
            if len(stochrsi_lens) >= 4: # Ensure all 4 parameters are present
                df.ta.stochrsi(close='close', length=stochrsi_lens[0], rsi_length=stochrsi_lens[1], k=stochrsi_lens[2], d=stochrsi_lens[3], append=True)
            else:
                logging.warning("StochRSI lengths in config are incomplete (expecting 4). Skipping StochRSI.")

        # RSI
        if self.config['indicators'].get('rsi'):
            df.ta.rsi(close='close', length=indicator_params.get('rsi_length', 14), append=True)

        # Bollinger Bands
        if self.config['indicators'].get('bbands'):
            bb_len, bb_std = indicator_params.get('bbands_settings', [20, 2])
            df.ta.bbands(close='close', length=bb_len, std=bb_std, append=True)

        # VWAP (requires 'volume' column)
        if self.config['indicators'].get('vwap'):
            if 'volume' in df.columns:
                df.ta.vwap(append=True)
            else:
                logging.warning("VWAP calculation skipped: 'volume' column not found.")

        # CCI
        if self.config['indicators'].get('cci'):
            df.ta.cci(close='close', length=indicator_params.get('cci_length', 14), append=True)

        # Williams %R
        if self.config['indicators'].get('williamsr'):
            df.ta.willr(close='close', length=indicator_params.get('williamsr_length', 14), append=True)

        # MFI
        if self.config['indicators'].get('mfi'):
            if 'volume' in df.columns:
                df.ta.mfi(close='close', volume='volume', length=indicator_params.get('mfi_length', 14), append=True)
            else:
                logging.warning("MFI calculation skipped: 'volume' column not found.")

        # PSAR
        if self.config['indicators'].get('psar'):
            psar_af0, psar_af_max = indicator_params.get('psar_settings', [0.02, 0.2])
            df.ta.psar(af0=psar_af0, af_max=psar_af_max, append=True)

        # SMA (e.g., 10, 30 periods)
        if self.config['indicators'].get('sma'):
            for length in indicator_params.get('sma_lengths', []):
                df.ta.sma(close='close', length=length, append=True)

        # ATR (needed for position sizing and stop loss) - always calculate
        df.ta.atr(length=DEFAULT_ATR_LENGTH, append=True)

        # Drop any rows with NaN values that might result from indicator calculations
        final_rows = len(df)
        df.dropna(inplace=True)
        if len(df) < final_rows:
            logging.debug(f"Dropped {final_rows - len(df)} rows due to NaN values after indicator calculation.")
        
        return df

    def calculate_fibonacci_pivots(self, df: pd.DataFrame, symbol: str) -> Dict[str, float]:
        """
        Calculates Fibonacci pivot points (P, R1, R2, R3, S1, S2, S3)
        based on the previous complete candle's High, Low, and Close.
        """
        # Need at least 2 candles: current and previous complete candle
        if len(df) < 2: 
            logging.warning(f"Not enough data for Fibonacci pivot calculation for {symbol} (need at least 2 candles).")
            return {}

        # Use the previous complete candle's data (iloc[-2]) for pivot calculation
        prev_candle = df.iloc[-2]
        high = prev_candle['high']
        low = prev_candle['low']
        close = prev_candle['close']

        if not all(pd.notna(v) for v in [high, low, close]) or high <= low: # Defensive check for invalid candle data
            logging.warning(f"Invalid candle data for Fibonacci pivot calculation for {symbol} (High <= Low or NaN values).")
            return {}

        pivot_points: Dict[str, float] = {}

        # Basic Pivot Point
        P = (high + low + close) / 3
        pivot_points['P'] = self._apply_price_precision(symbol, P)

        # Range
        Range = high - low

        # Resistance Levels
        pivot_points['R1'] = self._apply_price_precision(symbol, P + (Range * 0.382))
        pivot_points['R2'] = self._apply_price_precision(symbol, P + (Range * 0.618))
        pivot_points['R3'] = self._apply_price_precision(symbol, P + (Range * 1.000))

        # Support Levels
        pivot_points['S1'] = self._apply_price_precision(symbol, P - (Range * 0.382))
        pivot_points['S2'] = self._apply_price_precision(symbol, P - (Range * 0.618))
        pivot_points['S3'] = self._apply_price_precision(symbol, P - (Range * 1.000))

        return pivot_points

    def fetch_order_book(self, symbol: str, limit: int = 20) -> Optional[Dict[str, Any]]:
        """Fetches order book data for a given symbol."""
        response = retry_api_call(self.http_client.get_orderbook, category=Category.LINEAR, symbol=symbol, limit=limit)
        if not response: # Handle API call failure
            return None
        return response.get('result', {}) # pybit returns result directly here

    def analyze_order_book(self, order_book: Optional[Dict[str, Any]]) -> float:
        """
        Analyzes order book for market sentiment and liquidity.
        Returns a simple sentiment score (e.g., >0 for bullish, <0 for bearish).
        """
        if not order_book or not order_book.get('bids') or not order_book.get('asks'):
            return 0.0

        # Sum volumes of top N bids and asks
        num_levels = 5 # Consider top 5 levels
        try:
            bid_volume = sum([float(b[1]) for b in order_book['bids'][:num_levels]])
            ask_volume = sum([float(a[1]) for a in order_book['asks'][:num_levels]])
        except (ValueError, TypeError) as e:
            logging.warning(f"Error parsing order book volumes: {e}. Returning 0 sentiment.")
            return 0.0

        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return 0.0

        # Normalized imbalance: (Bid Volume - Ask Volume) / (Total Volume)
        sentiment = (bid_volume - ask_volume) / total_volume
        return sentiment

    def get_account_balance(self, coin: str = 'USDT') -> float:
        """Fetches the available balance for a specific coin."""
        response = retry_api_call(self.http_client.get_wallet_balance, accountType=AccountType.UNIFIED)
        if response and response.get('retCode') == 0:
            balance_list = response.get('result', {}).get('list', [])
            if balance_list:
                # Find the specific coin balance in the list
                for bal in balance_list[0].get('coin', []): # Assuming 'coin' list is within the first account entry
                    if bal.get('coin') == coin:
                        return float(bal.get('availableToWithdraw', 0.0)) # Use availableToWithdraw for trading
            logging.warning(f"Balance for {coin} not found in wallet balance response.")
        else:
            logging.error(Fore.RED + f"Failed to get wallet balance: {response.get('retMsg', 'Unknown error') if response else 'No response'}" + Style.RESET_ALL)
        return 0.0

    def get_current_positions(self, symbol: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Fetches open positions for a given symbol or all positions,
        and updates the internal tracking dictionary `self.open_positions`.
        This method is crucial for keeping the bot's internal state synchronized with the exchange.
        """
        response = retry_api_call(self.http_client.get_positions, category=Category.LINEAR, symbol=symbol)
        
        # Create a new dictionary to store updated positions for this cycle.
        # This approach ensures that positions no longer open on the exchange are removed from our tracking.
        updated_positions: Dict[str, Dict[str, Any]] = {}

        if response and response.get('retCode') == 0:
            positions_raw = response.get('result', {}).get('list', [])
            for p in positions_raw:
                contracts_size = float(p.get('size', 0))
                if contracts_size != 0: # Only consider active positions
                    sym = p.get('symbol')
                    if sym: # Ensure symbol is valid
                        # Get existing tracked info or initialize new for persistent data
                        tracked_pos_info = self.open_positions.get(sym, {})
                        
                        # Use initial_contracts from tracked_pos_info if it exists, otherwise set from current size
                        # This ensures initial_contracts reflects the size at entry, not after partial TPs
                        initial_contracts = tracked_pos_info.get('initial_contracts', contracts_size)

                        updated_positions[sym] = {
                            'symbol': sym,
                            'side': p.get('side', 'N/A'), # 'Long' or 'Short'
                            'initial_contracts': initial_contracts, # Contracts at position entry
                            'current_contracts': contracts_size, # Current contracts on exchange
                            'entryPrice': float(p.get('avgPrice', 0)),
                            'timestamp': tracked_pos_info.get('timestamp', int(p.get('createdTime', 0))), # Keep original entry time (pybit gives createdTime as string)
                            'positionIdx': int(p.get('positionIdx', 0)), # 0 for one-way mode
                            'stopLoss': float(p.get('stopLoss', 0)) if p.get('stopLoss') else None,
                            'takeProfit': float(p.get('takeProfit', 0)) if p.get('takeProfit') else None,
                            'trailingStop': float(p.get('trailingStop', 0)) if p.get('trailingStop') else None, # This is the callback rate
                            'ptp_levels_hit': tracked_pos_info.get('ptp_levels_hit', []) # Track hit partial TP levels
                        }
        else:
            logging.error(Fore.RED + f"Failed to retrieve positions: {response.get('retMsg', 'Unknown error') if response else 'No response'}" + Style.RESET_ALL)
        
        # Update the main open_positions dictionary with the fetched data
        self.open_positions = updated_positions
        self.bot_state.set('open_positions', self.open_positions) # Save to state
        logging.debug(f"Updated open positions: {self.open_positions}")
        return self.open_positions

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches current open orders for a symbol or all symbols."""
        response = retry_api_call(self.http_client.get_open_orders, category=Category.LINEAR, symbol=symbol)
        if response and response.get('retCode') == 0:
            return response.get('result', {}).get('list', [])
        else:
            logging.error(Fore.RED + f"Failed to get open orders: {response.get('retMsg', 'Unknown error') if response else 'No response'}" + Style.RESET_ALL)
            return []

    def cancel_all_open_orders(self, symbol: Optional[str] = None) -> None:
        """Cancels all open orders for a given symbol or all symbols."""
        logging.info(Fore.YELLOW + f"Attempting to cancel all open orders for {symbol if symbol else 'all symbols'}..." + Style.RESET_ALL)
        response = retry_api_call(self.http_client.cancel_all_orders, category=Category.LINEAR, symbol=symbol)
        if response and response.get('retCode') == 0:
            logging.info(Fore.GREEN + f"Successfully sent cancel all orders request. Result: {response.get('result')}" + Style.RESET_ALL)
        else:
            logging.error(Fore.RED + f"Failed to cancel all orders: {response.get('retMsg', 'Unknown error') if response else 'No response'}" + Style.RESET_ALL)

    def set_leverage(self, symbol: str) -> bool:
        """Sets the leverage for a given symbol."""
        # Check current leverage first to avoid unnecessary API calls
        positions_response = retry_api_call(self.http_client.get_positions, category=Category.LINEAR, symbol=symbol)
        if positions_response and positions_response.get('retCode') == 0:
            position_list = positions_response.get('result', {}).get('list', [])
            if position_list:
                # Bybit returns leverage per position, check if any position has the desired leverage
                # For one-way mode, there should only be one position for the symbol
                current_leverage = float(position_list[0].get('leverage', '0'))
                if current_leverage == self.config['leverage']:
                    logging.info(f"Leverage for {symbol} is already {self.config['leverage']}x.")
                    return True
            # If no position or leverage is different, set it
            logging.info(f"Setting leverage for {symbol} to {self.config['leverage']}x...")
            response = retry_api_call(self.http_client.set_leverage, category=Category.LINEAR, symbol=symbol, buyLeverage=str(self.config['leverage']), sellLeverage=str(self.config['leverage']))
            if response and response.get('retCode') == 0:
                logging.info(Fore.GREEN + f"Leverage for {symbol} set to {self.config['leverage']}x successfully." + Style.RESET_ALL)
                return True
            else:
                logging.error(Fore.RED + f"Failed to set leverage for {symbol}: {response.get('retMsg', 'Unknown error')}" + Style.RESET_ALL)
                return False
        else:
            logging.error(Fore.RED + f"Failed to get position info for {symbol} to check leverage: {positions_response.get('retMsg', 'Unknown error') if positions_response else 'No response'}" + Style.RESET_ALL)
            return False

    def calculate_position_size(self, symbol: str, current_price: float, atr_value: float) -> float:
        """
        Calculates the position size in contracts based on ATR, risk percentage, and leverage.
        Applies market precision.
        """
        precision_info = self._get_symbol_precision(symbol)
        if not precision_info:
            logging.error(Fore.RED + f"Could not get precision info for {symbol}. Cannot calculate position size." + Style.RESET_ALL)
            return 0.0

        account_balance = self.get_account_balance()
        if account_balance <= 0:
            logging.warning("Account balance is zero or negative. Cannot calculate position size.")
            return 0.0

        risk_per_trade_usd = account_balance * self.config['risk_per_trade']
        stop_loss_distance_usd = atr_value * self.config['stop_loss_atr_multiple']

        if stop_loss_distance_usd <= 0: # Avoid division by zero or negative distance
            logging.warning(f"ATR value ({atr_value:.4f}) or stop loss multiple ({self.config['stop_loss_atr_multiple']}) is zero/negative for {symbol}. Cannot calculate position size.")
            return 0.0

        # Calculate base quantity (e.g., BTC amount for BTCUSDT)
        # This is the quantity of the base asset (e.g., BTC) that can be bought/sold
        # for the risk amount given the stop loss distance.
        base_qty_asset = risk_per_trade_usd / stop_loss_distance_usd

        # Apply leverage to get the contract quantity (for derivatives)
        contract_qty_raw = base_qty_asset * self.config['leverage']

        # Apply amount precision from instrument info
        contract_qty = self._apply_qty_precision(symbol, contract_qty_raw)

        if contract_qty == 0.0:
            logging.warning(f"Calculated quantity {contract_qty_raw:.6f} for {symbol} rounded to zero after precision or is too small. Returning 0.")
            return 0.0

        logging.info(f"Calculated position size for {symbol}: {contract_qty:.6f} (Risk: ${risk_per_trade_usd:.2f}, SL Distance: ${stop_loss_distance_usd:.2f})")
        return contract_qty

    def place_order(self, symbol: str, side: str, qty: float, price: Optional[float] = None, reduce_only: bool = False) -> Optional[Dict[str, Any]]:
        """
        Places a market or limit order with precision.
        Includes safeguards for trading enablement and existing open orders.
        """
        if not self.config['enable_trading']:
            logging.info(f"Trading disabled. Would have placed {side} order for {qty:.6f} {symbol} at {self.config['order_type']} price {price}, reduceOnly={reduce_only}.")
            return None

        # Check for existing open orders if placing a new entry order (not reduce_only)
        if not reduce_only:
            open_orders = self.get_open_orders(symbol=symbol)
            if open_orders:
                logging.warning(f"Found {len(open_orders)} open orders for {symbol}. Not placing new entry order to avoid over-trading.")
                return None

        # Apply precision to quantity
        qty = self._apply_qty_precision(symbol, qty)
        if qty == 0.0:
            logging.warning(f"Quantity for {symbol} rounded to zero after precision. Not placing order.")
            return None

        order_type_to_use = self.config['order_type']
        params: Dict[str, Any] = {'category': Category.LINEAR, 'positionIdx': 0} # Bybit V5 specific for perpetuals, one-way mode
        
        if reduce_only: # Force market for reduceOnly orders for simplicity and quick fills
            order_type_to_use = OrderType.MARKET
            params['reduceOnly'] = True
            if price: # For limit reduce-only orders, if needed
                price = self._apply_price_precision(symbol, price)
        elif order_type_to_use == OrderType.LIMIT: # For entry limit orders
            if price is None:
                logging.error("Limit order requires a price.")
                return None
            price = self._apply_price_precision(symbol, price)
            params['timeInForce'] = 'GTC' # Good Till Cancel

        # Generate a unique client order ID
        client_order_id = str(uuid.uuid4())
        params['orderLinkId'] = client_order_id # pybit uses orderLinkId for clientOrderId

        try:
            order_response = retry_api_call(
                self.http_client.place_order,
                symbol=symbol,
                side=side,
                orderType=order_type_to_use,
                qty=str(qty), # pybit expects string quantity
                price=str(price) if price is not None else None, # pybit expects string price
                **params
            )
            
            if order_response:
                order_result = order_response.get('result', {})
                order_id = order_result.get('orderId', 'N/A')
                client_order_id_resp = order_result.get('orderLinkId', 'N/A')
                order_status_resp = order_result.get('orderStatus', 'Unknown') # Get actual status from response
                filled_price_resp = float(order_result.get('avgPrice', price if price else '0')) # Use avgPrice if available

                logging.info(Fore.GREEN + f"Placed {side} {order_type_to_use} order for {qty:.6f} {symbol} at {filled_price_resp:.4f}, reduceOnly={reduce_only}. Order ID: {order_id}, Client Order ID: {client_order_id_resp}, Status: {order_status_resp}" + Style.RESET_ALL)
                
                return {
                    'id': order_id,
                    'clientOrderId': client_order_id_resp,
                    'symbol': symbol,
                    'side': side,
                    'type': order_type_to_use,
                    'status': 'filled' if order_status_resp == 'Filled' else 'open', # More accurate internal status
                    'amount': qty,
                    'price': filled_price_resp,
                    'timestamp': int(time.time() * 1000) # Current time as placement time
                }
            else:
                logging.error(Fore.RED + "Failed to place order after multiple attempts." + Style.RESET_ALL)
        except Exception as e:
            logging.error(Fore.RED + f"Error placing order for {symbol}: {e}" + Style.RESET_ALL, exc_info=True)
        return None

    def set_trading_stop(self, symbol: str, side: str, entry_price: float, current_price: float, atr_value: float, position_idx: int, stop_loss: Optional[float] = None, take_profit: Optional[float] = None, trailing_stop_callback_rate: Optional[float] = None) -> None:
        """
        Sets or updates Stop Loss, Take Profit, and Trailing Stop for a position
        using Bybit V5's set_trading_stop endpoint.
        """
        if not self.config['enable_trading']:
            logging.info(f"Trading disabled. Would have set trading stops for {symbol}.")
            return

        params: Dict[str, Any] = {
            'category': Category.LINEAR, # Assuming perpetuals
            'symbol': symbol,
            'positionIdx': position_idx # 0 for one-way mode, 1 for long, 2 for short in hedge mode
        }

        update_params: Dict[str, str] = {}

        # Calculate SL/TP if not provided (e.g., initial setup) or if updating
        if stop_loss is not None:
            sl_price = self._apply_price_precision(symbol, stop_loss)
            update_params['stopLoss'] = str(sl_price)
            params['slTriggerBy'] = TriggerBy.MARK_PRICE # Default trigger by MarkPrice
        elif self.config['stop_loss_atr_multiple'] > 0 and atr_value > 0: # Initial SL calculation based on ATR
            if side == OrderSide.BUY:
                sl_price = entry_price - (atr_value * self.config['stop_loss_atr_multiple'])
            else: # Short
                sl_price = entry_price + (atr_value * self.config['stop_loss_atr_multiple'])
            update_params['stopLoss'] = str(self._apply_price_precision(symbol, sl_price))
            params['slTriggerBy'] = TriggerBy.MARK_PRICE

        if take_profit is not None:
            tp_price = self._apply_price_precision(symbol, take_profit)
            update_params['takeProfit'] = str(tp_price)
            params['tpTriggerBy'] = TriggerBy.MARK_PRICE # Default trigger by MarkPrice
        elif self.config['take_profit_atr_multiple'] > 0 and atr_value > 0: # Initial TP calculation based on ATR
            if side == OrderSide.BUY:
                tp_price = entry_price + (atr_value * self.config['take_profit_atr_multiple'])
            else: # Short
                tp_price = entry_price - (atr_value * self.config['take_profit_atr_multiple'])
            update_params['takeProfit'] = str(self._apply_price_precision(symbol, tp_price))
            params['tpTriggerBy'] = TriggerBy.MARK_PRICE

        # Trailing Stop: Bybit V5 takes a callback rate
        if trailing_stop_callback_rate is not None:
            update_params['trailingStop'] = str(trailing_stop_callback_rate) # Needs to be string for Bybit
        elif self.config['trailing_stop_callback_rate'] > 0:
            update_params['trailingStop'] = str(self.config['trailing_stop_callback_rate'])

        if not update_params:
            logging.info(f"No trading stop parameters to update for {symbol}.")
            return

        try:
            # pybit's set_trading_stop combines these
            response = retry_api_call(
                self.http_client.set_trading_stop,
                **params,
                **update_params # Pass stopLoss, takeProfit, trailingStop here
            )
            if response and response.get('retCode') == 0:
                logging.info(Fore.GREEN + f"Successfully set trading stops for {symbol}. SL: {update_params.get('stopLoss', 'N/A')}, TP: {update_params.get('takeProfit', 'N/A')}, TSL: {update_params.get('trailingStop', 'N/A')}" + Style.RESET_ALL)
                # Update internal position tracking with new SL/TP values
                if symbol in self.open_positions:
                    if 'stopLoss' in update_params: self.open_positions[symbol]['stopLoss'] = float(update_params['stopLoss'])
                    if 'takeProfit' in update_params: self.open_positions[symbol]['takeProfit'] = float(update_params['takeProfit'])
                    if 'trailingStop' in update_params: self.open_positions[symbol]['trailingStop'] = float(update_params['trailingStop'])
                    self.bot_state.set('open_positions', self.open_positions) # Save to state
            else:
                logging.error(Fore.RED + f"Failed to set trading stops for {symbol}: {response.get('retMsg', 'Unknown error')}" + Style.RESET_ALL)
        except Exception as e:
            logging.error(Fore.RED + f"Error setting trading stops for {symbol}: {e}" + Style.RESET_ALL, exc_info=True)

    def manage_position(self, symbol: str, position_info: Dict[str, Any], current_price: float, atr_value: float) -> None:
        """
        Manages open positions, including break-even adjustment, partial take-profit,
        and time-based exit.
        """
        if not self.config['enable_trading']:
            return

        entry_price = position_info.get('entryPrice')
        side = position_info.get('side') # 'Long' or 'Short'
        position_idx = position_info.get('positionIdx', 0)
        contracts = position_info.get('current_contracts')
        current_sl = position_info.get('stopLoss')
        ptp_levels_hit = position_info.get('ptp_levels_hit', [])

        if not entry_price or not side or contracts is None or contracts <= 0:
            logging.warning(f"Incomplete or zero-size position info for {symbol}. Cannot manage.")
            # If contracts are 0, it means position is closed, remove it from tracking
            if symbol in self.open_positions and (contracts is None or contracts <= 0):
                logging.info(f"Position for {symbol} has 0 contracts. Removing from tracking.")
                del self.open_positions[symbol]
                self.bot_state.set('open_positions', self.open_positions)
            return

        # Calculate current profit in terms of ATR multiples
        price_diff = (current_price - entry_price) if side == OrderSide.BUY else (entry_price - current_price)
        profit_atr_multiples = price_diff / atr_value if atr_value > 0 else 0.0

        # Determine if position is in profit or loss
        is_in_profit = (side == OrderSide.BUY and current_price > entry_price) or \
                       (side == OrderSide.SELL and current_price < entry_price)

        # --- Break-Even Stop Loss Adjustment ---
        if self.config['break_even_trigger_atr_multiple'] > 0 and is_in_profit and \
           profit_atr_multiples >= self.config['break_even_trigger_atr_multiple']:

            # Calculate new break-even price (slightly into profit to cover fees)
            be_buffer = self._apply_price_precision(symbol, atr_value * self.config['break_even_buffer_atr_percentage'])
            if side == OrderSide.BUY:
                new_stop_loss = entry_price + be_buffer
            else: # Short
                new_stop_loss = entry_price - be_buffer

            # Ensure new SL is better than current SL (closer to entry or already in profit)
            # and that we don't try to move SL to a worse position
            should_update_sl = False
            if current_sl is None: # No SL set yet
                should_update_sl = True
            elif side == OrderSide.BUY and new_stop_loss > current_sl: # Only update if SL moves higher (for long)
                should_update_sl = True
            elif side == OrderSide.SELL and new_stop_loss < current_sl: # Only update if SL moves lower (for short)
                should_update_sl = True

            if should_update_sl:
                logging.info(Fore.MAGENTA + f"Moving SL to Break-Even for {symbol}. New SL: {new_stop_loss:.4f} (Current profit: {profit_atr_multiples:.2f} ATR)" + Style.RESET_ALL)
                self.set_trading_stop(
                    symbol=symbol,
                    side=side,
                    entry_price=entry_price,
                    current_price=current_price,
                    atr_value=atr_value,
                    position_idx=position_idx,
                    stop_loss=new_stop_loss, # Pass the specific new SL price
                    take_profit=position_info.get('takeProfit'), # Keep existing TP
                    trailing_stop_callback_rate=position_info.get('trailingStop') # Keep existing TSL
                )

        # --- Partial Take Profit ---
        if is_in_profit and self.config['partial_take_profit_levels'] and contracts > 0:
            # Sort levels to ensure they are triggered in order (e.g., 1.5x ATR before 2.5x ATR)
            for level_atr, percentage_to_close in sorted(self.config['partial_take_profit_levels']):
                if level_atr not in ptp_levels_hit and profit_atr_multiples >= level_atr:
                    qty_to_close_raw = contracts * percentage_to_close
                    qty_to_close = self._apply_qty_precision(symbol, qty_to_close_raw)

                    if qty_to_close > 0:
                        logging.info(Fore.GREEN + f"Partial Take Profit triggered for {symbol} at {level_atr}x ATR. Closing {percentage_to_close*100:.2f}% ({qty_to_close:.6f} contracts)." + Style.RESET_ALL)
                        order = self.place_order(symbol, OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY, qty_to_close, reduce_only=True)
                        
                        if order: # Only mark as hit if order was successfully placed
                            # Add level to hit list to prevent re-triggering
                            self.open_positions[symbol]['ptp_levels_hit'].append(level_atr)
                            logging.info(f"PTP order for {symbol} at {level_atr}x ATR placed. Remaining contracts are subject to exchange fill.")
                            self.bot_state.set('open_positions', self.open_positions) # Save to state
                            # The actual remaining contracts will be refreshed by get_current_positions in the next loop.
                        else:
                            logging.warning(f"PTP order for {symbol} failed to place.")
                    else:
                        logging.warning(f"Calculated partial take profit quantity for {symbol} ({qty_to_close_raw:.6f}) is zero after precision. Skipping.")

        # --- Time-Based Position Exit ---
        if self.config['time_based_exit_minutes'] > 0 and contracts > 0: # Check if still open after PTP
            open_time_ms = position_info.get('timestamp')
            if open_time_ms:
                open_time = datetime.fromtimestamp(open_time_ms / 1000, tz=self.timezone)
                if datetime.now(self.timezone) - open_time > timedelta(minutes=self.config['time_based_exit_minutes']):
                    logging.info(Fore.YELLOW + f"Time-based exit triggered for {symbol}. Closing remaining position ({contracts:.6f} contracts)." + Style.RESET_ALL)
                    self.close_position(symbol, side, contracts)
                    return # Position closed, no further management needed

    def close_position(self, symbol: str, side: str, qty: float, reduce_only: bool = True) -> None:
        """Closes an open position by placing a market order in the opposite direction."""
        if not self.config['enable_trading']:
            logging.info(f"Trading disabled. Would have closed {symbol} position.")
            return

        try:
            opposite_side = OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY
            order = self.place_order(symbol, opposite_side, qty, reduce_only=reduce_only)
            
            if order: # Order successfully placed
                logging.info(Fore.GREEN + f"Close order for {symbol} placed. Order ID: {order.get('id', 'N/A')}" + Style.RESET_ALL)
                # Position will be removed from internal tracking in the next get_current_positions call
                # if the order fills.
            else:
                logging.error(Fore.RED + f"Failed to place close order for {symbol}." + Style.RESET_ALL)
        except Exception as e:
            logging.error(Fore.RED + f"Error closing position for {symbol}: {e}" + Style.RESET_ALL, exc_info=True)

    def _check_global_loss_limit(self) -> bool:
        """
        Checks if the total account balance has dropped below the configured loss limit.
        Triggers graceful shutdown if limit is reached.
        """
        if self.initial_balance is None or self.config['max_total_loss_percentage'] <= 0:
            return False

        current_balance = self.get_account_balance()
        if current_balance <= 0: # Avoid division by zero
            logging.critical(Fore.RED + "Account balance is zero or negative. Stopping bot." + Style.RESET_ALL)
            return True

        loss_percentage = (self.initial_balance - current_balance) / self.initial_balance
        if loss_percentage >= self.config['max_total_loss_percentage']:
            logging.critical(Fore.RED + f"Global loss limit of {self.config['max_total_loss_percentage']*100:.2f}% reached! "+\
                             f"Initial: {self.initial_balance:.2f} USDT, Current: {current_balance:.2f} USDT, Loss: {loss_percentage*100:.2f}%. Stopping bot." + Style.RESET_ALL)
            return True
        return False

    def _reload_config(self) -> None:
        """
        Reloads the configuration from config.json.
        Only updates parameters that are safe to change dynamically.
        """
        try:
            new_config = load_config() # This will re-validate the new config
            # Only update mutable parts of config that are safe to change on the fly
            # Exclude sensitive or initialization-only parameters that require a full restart
            updatable_keys = [
                "symbols_to_trade", "interval", "enable_trading", "risk_per_trade",
                "leverage", "max_positions", "order_type", "limit_order_price_offset_percentage",
                "indicators", "indicator_params", "weight_sets", "active_weight_set",
                "signal_threshold", "stop_loss_atr_multiple", "take_profit_atr_multiple", 
                "trailing_stop_callback_rate", "break_even_trigger_atr_multiple", 
                "break_even_buffer_atr_percentage", "partial_take_profit_levels",
                "time_based_exit_minutes", "loop_delay_seconds", "heartbeat_interval_minutes",
                "max_total_loss_percentage", "close_positions_on_exit"
            ]
            for key in updatable_keys:
                if key in new_config:
                    # Special handling for nested dictionaries to merge them properly
                    if isinstance(self.config.get(key), dict) and isinstance(new_config[key], dict):
                        self.config[key].update(new_config[key])
                    else:
                        self.config[key] = new_config[key]

            # Also update strategy config if it holds a reference
            self.strategy.config = self.config
            self.strategy.weights = self.config['weight_sets'][self.config['active_weight_set']]
            self.strategy.indicator_params = self.config['indicator_params'] # Update indicator params in strategy
            logging.info(Fore.BLUE + "Configuration reloaded." + Style.RESET_ALL)
        except Exception as e:
            logging.error(Fore.RED + f"Error reloading config: {e}" + Style.RESET_ALL)

    def graceful_shutdown(self) -> None:
        """
        Handles graceful shutdown of the bot, optionally closing all open positions
        and canceling pending orders.
        """
        logging.info(Fore.CYAN + "Initiating graceful shutdown..." + Style.RESET_ALL)
        if self.config['close_positions_on_exit']:
            logging.info(Fore.YELLOW + "Attempting to close all open positions and cancel all open orders..." + Style.RESET_ALL)
            # Fetch latest positions to ensure we have accurate info before closing
            self.get_current_positions() # This also saves state
            for symbol, pos_info in list(self.open_positions.items()): # Iterate over a copy to allow modification
                try:
                    if pos_info['current_contracts'] > 0: # Only close if still open
                        logging.info(f"Closing {pos_info['side']} position for {symbol} ({pos_info['current_contracts']:.6f} contracts)...")
                        self.close_position(symbol, pos_info['side'], pos_info['current_contracts'])
                        time.sleep(1) # Small delay between closing positions to avoid rate limits
                except Exception as e:
                    logging.error(Fore.RED + f"Error closing position for {symbol} during shutdown: {e}" + Style.RESET_ALL)
            
            # Cancel any remaining open orders (e.g., limit orders that didn't fill)
            self.cancel_all_open_orders()

        self.bot_state.save_state() # Ensure final state is saved
        logging.info(Fore.CYAN + "Bot has shut down gracefully. Goodbye!" + Style.RESET_ALL)
        sys.exit(0)

    def run(self) -> None:
        """
        Main loop of the trading bot.
        Continuously fetches data, calculates indicators, generates signals,
        and manages trades based on the configured strategy and risk parameters.
        """
        logging.info(Fore.GREEN + "XR Scalper Bot starting main loop..." + Style.RESET_ALL)
        try:
            while True:
                current_loop_time = datetime.now(self.timezone)

                # Heartbeat log and optional config reload
                if (current_loop_time - self.last_heartbeat).total_seconds() / 60 >= self.config['heartbeat_interval_minutes']:
                    logging.info(Fore.BLUE + f"Bot Heartbeat: Still running at {current_loop_time.strftime('%Y-%m-%d %H:%M:%S %Z')}" + Style.RESET_ALL)
                    self.last_heartbeat = current_loop_time
                    self._reload_config() # Reload config periodically to pick up external changes

                # Check global loss limit before processing any trades
                if self._check_global_loss_limit():
                    self.graceful_shutdown()

                # Refresh open positions from exchange and save state
                # This ensures `self.open_positions` is always up-to-date with exchange
                self.get_current_positions() 
                logging.info(f"Currently tracking {len(self.open_positions)} open positions.")

                for symbol in self.config['symbols_to_trade']:
                    logging.info(f"\n--- Processing {symbol} ---")

                    # 1. Ensure leverage is set for the symbol
                    if not self.set_leverage(symbol):
                        logging.error(f"Failed to set leverage for {symbol}. Skipping symbol for this cycle.")
                        continue

                    # 2. Fetch and prepare data
                    df = self.fetch_kline_data(symbol, self.config['interval'])
                    # Ensure enough data for indicators and previous candle comparison
                    min_candles_needed = max(self.config['indicator_params'].get('ema_lengths', [0]) + 
                                             self.config['indicator_params'].get('rsi_length', [0]) + 
                                             [DEFAULT_ATR_LENGTH]) + 2 # +2 for prev candle and safe indicator calc
                    if df.empty or len(df) < min_candles_needed: 
                        logging.warning(f"Not enough kline data for {symbol}. Skipping. Need at least {min_candles_needed} candles.")
                        continue

                    df = self.calculate_indicators(df)
                    # After calculation, ensure DataFrame is not empty and has ATR
                    atr_col_name = f'ATR_{DEFAULT_ATR_LENGTH}'
                    if df.empty or atr_col_name not in df.columns or pd.isna(df[atr_col_name].iloc[-1]):
                        logging.warning(f"Indicators or ATR ({atr_col_name}) not calculated for {symbol} or data is invalid. Skipping.")
                        continue

                    current_price = df['close'].iloc[-1]
                    atr_value = df[atr_col_name].iloc[-1]
                    if atr_value <= 0: # Defensive check for zero/negative ATR
                        logging.warning(f"Calculated ATR value ({atr_value:.4f}) for {symbol} is zero or negative. Skipping trade logic.")
                        continue

                    # 3. Calculate Fibonacci Pivot Points
                    fib_pivots: Dict[str, float] = {}
                    if self.config['indicators'].get('fibonacci_pivots'):
                        fib_pivots = self.calculate_fibonacci_pivots(df, symbol)
                        if not fib_pivots:
                            logging.warning(f"Fibonacci pivots could not be calculated for {symbol}. Skipping pivot-based strategy logic.")

                    # 4. Fetch and analyze order book
                    order_book = self.fetch_order_book(symbol)
                    order_book_sentiment = self.analyze_order_book(order_book)
                    logging.info(f"Order Book Sentiment for {symbol}: {order_book_sentiment:.2f}")

                    # 5. Manage existing position if any
                    if symbol in self.open_positions and self.open_positions[symbol]['current_contracts'] > 0: # Check if position is actually open
                        logging.info(f"Managing existing position for {symbol} ({self.open_positions[symbol]['side']} {self.open_positions[symbol]['current_contracts']:.6f})...")
                        self.manage_position(symbol, self.open_positions[symbol], current_price, atr_value)
                        # After managing, re-fetch positions to see if PTPs closed it, etc.
                        self.get_current_positions(symbol=symbol) # Update specific symbol's state
                        if symbol not in self.open_positions: # Position might have been fully closed
                            logging.info(f"Position for {symbol} was fully closed during management.")
                            continue # Move to next symbol, no new signal needed for this symbol
                    else:
                        # 6. Generate signal only if no open position for this symbol and max positions not reached
                        if len(self.open_positions) < self.config['max_positions']:
                            
                            # --- STRATEGY CALL ---
                            signal_result = self.strategy.generate_signal(df, order_book_sentiment, fib_pivots)
                            signal = signal_result['signal']
                            strategy_info = signal_result['strategy_info']
                            logging.info(f"Strategy Signal for {symbol}: {signal} ({strategy_info.get('decision', 'N/A')}). Info: {json.dumps(strategy_info, indent=2)}")

                            if signal != 0:
                                side = OrderSide.BUY if signal == 1 else OrderSide.SELL
                                qty = self.calculate_position_size(symbol, current_price, atr_value)

                                if qty > 0: # Ensure calculated quantity is valid
                                    logging.info(f"Attempting to place {side} order for {qty:.6f} {symbol}...")
                                    order_price: Optional[float] = None
                                    if self.config['order_type'] == OrderType.LIMIT:
                                        if side == OrderSide.BUY:
                                            order_price = current_price * (1 - self.config['limit_order_price_offset_percentage'])
                                        else: # Sell
                                            order_price = current_price * (1 + self.config['limit_order_price_offset_percentage'])
                                        order_price = self._apply_price_precision(symbol, order_price)
                                        logging.info(f"Limit order price set to: {order_price:.4f}")

                                    placed_order_info = self.place_order(symbol, side, qty, order_price)

                                    if placed_order_info and placed_order_info.get('status') == 'filled': # Order filled
                                        logging.info(Fore.GREEN + f"Order for {symbol} filled. Entry Price: {placed_order_info.get('price', 'N/A'):.4f}" + Style.RESET_ALL)
                                        # Update internal tracking with the new position (get_current_positions will do this more robustly)
                                        # For immediate SL/TP setting, we can use the filled info
                                        self.set_trading_stop(
                                            symbol=symbol,
                                            side=side,
                                            entry_price=placed_order_info.get('price', current_price), # Use actual fill price for stop calculation
                                            current_price=placed_order_info.get('price', current_price), # Use actual fill price for initial setup
                                            atr_value=atr_value,
                                            position_idx=0, # Assuming one-way mode
                                            stop_loss=None, # Calculate based on ATR
                                            take_profit=None, # Calculate based on ATR
                                            trailing_stop_callback_rate=None # Use config value
                                        )
                                    elif placed_order_info: # Order placed but not yet filled (e.g., Limit order)
                                        logging.info(f"Order for {symbol} placed but not yet filled (Status: {placed_order_info.get('status', 'N/A')}). Will monitor.")
                                else:
                                    logging.warning(f"Calculated quantity for {symbol} is zero or too small. Not placing order.")
                        else:
                            logging.info(f"Max positions ({self.config['max_positions']}) reached. Not opening new trades for {symbol}.")
            
                # Update last run time in state and save it after each full loop iteration
                self.bot_state.set('last_run_time', current_loop_time)
                self.bot_state.save_state()

                logging.info(f"Sleeping for {self.config['loop_delay_seconds']} seconds...")
                time.sleep(self.config['loop_delay_seconds'])

        except KeyboardInterrupt:
            logging.info(Fore.CYAN + "KeyboardInterrupt detected. Shutting down..." + Style.RESET_ALL)
            self.graceful_shutdown()
        except Exception as e:
            logging.critical(Fore.RED + f"Critical unexpected error in main loop: {e}" + Style.RESET_ALL, exc_info=True)
            self.graceful_shutdown() # Attempt graceful shutdown even on unexpected errors

# --- Main Execution Block ---
def main() -> None:
    """Main function to initialize and run the bot."""
    bot = XRScalperBot()
    bot.run()

if __name__ == "__main__":
    main()
```

---

## Enhanced JSON Structure for "XR Scalper (Enterprise Edition)"

This expanded JSON outlines a comprehensive, modular architecture for an advanced algorithmic trading bot, building upon the provided Python code's foundation. It envisions over 100 functions across various domains, illustrating the complexity and depth required for a production-grade system.

```json
{
  "bot_name": "XR Scalper (Enterprise Edition)",
  "version": "1.0.0",
  "summary": "A conceptual blueprint for an advanced, fully-featured algorithmic trading bot. This expanded template illustrates the modular architecture required for comprehensive market interaction, strategy execution, risk management, data analysis, and operational resilience. It builds upon the core functionalities of the previous XR Scalper, extending into areas like advanced order types, portfolio management, backtesting, alerting, and infrastructure.",
  "modules_and_functions": [
    {
      "module": "Core Bot Setup & Control",
      "description": "Fundamental functions for bot initialization, configuration loading, environment setup, and graceful operation lifecycle management.",
      "functions": [
        {
          "name": "setup_logging",
          "description": "Configures Python's logging module to direct output to both a console stream (with Colorama support) and a persistent log file ('xrscalper.log'). It also sets warning levels for verbose external libraries."
        },
        {
          "name": "load_config",
          "description": "Loads bot configuration from 'config.json'. If the file doesn't exist, a default configuration is created and saved. Calls `validate_config` to ensure critical parameters are correctly set, exiting if a new config is created or validation fails."
        },
        {
          "name": "validate_config",
          "description": "Performs stringent validation checks on essential configuration parameters such as risk percentage, leverage, symbol list, active weight set, order type, partial take-profit levels, and global loss limit. Exits the bot if any critical misconfiguration is detected."
        },
        {
          "name": "load_env_vars",
          "description": "Loads sensitive API credentials (API key, API secret) and timezone settings from a '.env' file using `python-dotenv`. Ensures credentials are present; exits if not. Handles unknown timezone strings by defaulting to UTC."
        },
        {
          "name": "XRScalperBot.__init__",
          "description": "Constructor for the main bot class. Initializes all core components: loads configuration and environment variables, sets up the `pybit` HTTP client, loads persistent bot state (including existing positions and initial balance), and instantiates the chosen trading strategy."
        },
        {
          "name": "XRScalperBot._initialize_http_client",
          "description": "Initializes the `pybit.unified_trading.HTTP` client with API keys and sandbox settings. It performs a connectivity test by fetching server time and retrieves the initial account balance for global loss tracking if in live trading mode and not already loaded from state."
        },
        {
          "name": "XRScalperBot._reload_config",
          "description": "Allows for dynamic reloading of the bot's configuration from `config.json` during runtime. Updates active settings in the bot and its strategy instance, carefully excluding sensitive or immutable parameters that require a full restart."
        },
        {
          "name": "XRScalperBot.run",
          "description": "The main event loop of the trading bot. It orchestrates the entire trading process: logs periodic heartbeats, checks for global loss limit breaches, refreshes internal open positions from the exchange, iterates through configured trading symbols, manages leverage, fetches and processes market data, analyzes sentiment, calculates pivots, generates signals, manages existing positions (SL/TP/BE/PTP/Time-based exit), and places new orders. Includes robust error handling and a loop delay."
        },
        {
          "name": "XRScalperBot.graceful_shutdown",
          "description": "Manages the orderly termination of the bot. Optionally attempts to close all currently open positions and cancel all outstanding open orders based on configuration (`close_positions_on_exit`). Ensures the final bot state is saved before exiting the program."
        },
        {
          "name": "XRScalperBot.start_bot_process",
          "description": "Initializes and starts the main bot process, possibly in a separate thread/process for responsiveness."
        },
        {
          "name": "XRScalperBot.stop_bot_process",
          "description": "Sends a signal to gracefully stop the bot process, triggering `graceful_shutdown`."
        },
        {
          "name": "XRScalperBot.pause_trading",
          "description": "Temporarily pauses all new order placement and position management activities, while keeping market data fetching active."
        },
        {
          "name": "XRScalperBot.resume_trading",
          "description": "Resumes trading activities after a pause, re-enabling order placement and management."
        },
        {
          "name": "main",
          "description": "The entry point of the application, responsible for initializing and running the `XRScalperBot` instance."
        }
      ]
    },
    {
      "module": "API Interaction & Error Handling",
      "description": "Functions dedicated to secure and resilient communication with the Bybit API, managing retries, authentication, and various error types.",
      "functions": [
        {
          "name": "retry_api_call",
          "description": "A robust wrapper function for all `pybit` API calls. It implements an exponential backoff retry mechanism for transient network or API-specific errors (`PybitRequestException`, `PybitAPIException`). Fatal authentication errors (`PybitAuthException`) trigger an immediate bot exit. Logs warning messages for retryable errors and critical errors for unhandled exceptions."
        },
        {
          "name": "XRScalperBot._get_symbol_precision",
          "description": "Fetches and caches instrument-specific precision data (e.g., `basePrecision` for quantity, `tickSize` for price) for a given trading symbol using `pybit`'s `get_instrument_info`. This information is critical for submitting orders with correct precision and is cached to reduce redundant API calls."
        },
        {
          "name": "XRScalperBot._apply_qty_precision",
          "description": "Applies the precise quantity rules (base precision, min/max order quantity) to a calculated trade size. Rounds the quantity down (`math.floor`) to the nearest valid step and checks against exchange limits to avoid over-risking."
        },
        {
          "name": "XRScalperBot._apply_price_precision",
          "description": "Applies the precise price rules (tick size) to a calculated price. Rounds the price to the nearest valid tick required by the exchange."
        },
        {
          "name": "XRScalperBot.get_server_time",
          "description": "Fetches and validates exchange server time, crucial for ensuring local clock synchronization and avoiding `recv_window` errors."
        },
        {
          "name": "XRScalperBot.get_exchange_info",
          "description": "Fetches general exchange information, trading rules, and symbol statuses."
        },
        {
          "name": "XRScalperBot.check_api_permissions",
          "description": "Verifies that the provided API key has the necessary permissions (e.g., read, trade) for bot operations."
        },
        {
          "name": "XRScalperBot.handle_rate_limit_exceeded",
          "description": "Implements specific, more advanced logic for handling persistent rate limit errors (beyond simple retry), potentially by dynamically adjusting request frequency."
        },
        {
          "name": "XRScalperBot.handle_api_connection_loss",
          "description": "Manages reconnections and state recovery on WebSocket or HTTP connection drops, ensuring minimal disruption."
        },
        {
          "name": "XRScalperBot.get_api_status_updates",
          "description": "Fetches Bybit's system status or maintenance announcements."
        }
      ]
    },
    {
      "module": "Market Data Acquisition",
      "description": "Functions for fetching and processing real-time and historical market data from the exchange.",
      "functions": [
        {
          "name": "XRScalperBot.fetch_kline_data",
          "description": "Fetches historical candlestick (OHLCV) data for a specified symbol and interval using `pybit`'s `get_kline` endpoint. Transforms the raw data into a Pandas DataFrame, converting timestamps, setting the index, and ensuring numeric types."
        },
        {
          "name": "XRScalperBot.fetch_order_book",
          "description": "Fetches the current order book (top N bids and asks) for a specified symbol using `pybit`'s `get_orderbook` endpoint."
        },
        {
          "name": "XRScalperBot.fetch_tickers",
          "description": "Fetches latest price snapshots (last traded price, 24h volume, etc.) for multiple symbols."
        },
        {
          "name": "XRScalperBot.fetch_funding_rate_history",
          "description": "Retrieves historical funding rates for perpetual contracts, useful for market analysis and carry trade strategies."
        },
        {
          "name": "XRScalperBot.fetch_recent_trades",
          "description": "Fetches recent public trades for a symbol, used for real-time volume analysis or high-frequency strategies."
        },
        {
          "name": "XRScalperBot.fetch_mark_price_kline",
          "description": "Fetches kline data specifically based on the mark price, important for derivatives trading and liquidation calculations."
        },
        {
          "name": "XRScalperBot.fetch_index_price_kline",
          "description": "Fetches kline data based on the index price, representing the average price across multiple exchanges."
        },
        {
          "name": "XRScalperBot.subscribe_public_websocket",
          "description": "Manages public WebSocket connections for real-time market data streams (e.g., trades, order book updates, kline updates)."
        },
        {
          "name": "XRScalperBot.handle_public_websocket_message",
          "description": "Processes incoming public WebSocket messages, parsing data and routing it to appropriate handlers or data caches."
        },
        {
          "name": "XRScalperBot.update_realtime_data_cache",
          "description": "Updates an in-memory cache with real-time market data received from WebSockets, providing low-latency access for strategy execution."
        },
        {
          "name": "XRScalperBot.get_realtime_order_book_depth",
          "description": "Provides real-time aggregated order book depth from WebSocket data."
        }
      ]
    },
    {
      "module": "Indicator Calculation",
      "description": "Functions for computing various technical indicators from market data, supporting dynamic parameter loading and robust data handling.",
      "functions": [
        {
          "name": "XRScalperBot.calculate_indicators",
          "description": "Calculates a comprehensive suite of technical indicators (EMAs, Momentum, StochRSI, RSI, Bollinger Bands, VWAP, CCI, Williams %R, MFI, PSAR, SMAs, ATR) on the provided kline DataFrame using the `pandas_ta` library. Indicator parameters are dynamically loaded from the bot's configuration (`indicator_params`). Handles missing data (NaN) by dropping rows to ensure clean calculations."
        },
        {
          "name": "XRScalperBot.calculate_fibonacci_pivots",
          "description": "Calculates Fibonacci pivot points (Pivot Point, R1-R3 Resistance, S1-S3 Support) using the High, Low, and Close prices of the *previous complete candle*. Applies price precision to all calculated pivot levels. Returns an empty dictionary if insufficient data or invalid candle found."
        },
        {
          "name": "XRScalperBot.analyze_order_book",
          "description": "Analyzes the fetched order book to compute a simple market sentiment score based on the volume imbalance between top bids and asks. A positive score indicates bullish sentiment, negative indicates bearish, aiding in signal generation."
        },
        {
          "name": "XRScalperBot.calculate_vwap_realtime",
          "description": "Calculates VWAP for the current, incomplete candle using real-time tick data from WebSockets for more immediate analysis."
        },
        {
          "name": "XRScalperBot.calculate_custom_indicator_X",
          "description": "Placeholder for a custom technical indicator calculation, allowing for proprietary signal generation."
        },
        {
          "name": "XRScalperBot.apply_indicator_smoothing",
          "description": "Applies various smoothing techniques (e.g., moving average, exponential smoothing) to indicator outputs to reduce noise."
        },
        {
          "name": "XRScalperBot.detect_indicator_divergence",
          "description": "Identifies divergences between price action and indicator movements (e.g., RSI divergence) as potential reversal signals."
        },
        {
          "name": "XRScalperBot.calculate_volume_profile",
          "description": "Computes volume profile for a given price range, identifying areas of high liquidity."
        },
        {
          "name": "XRScalperBot.calculate_on_balance_volume",
          "description": "Calculates On-Balance Volume (OBV) to confirm price trends with volume flow."
        }
      ]
    },
    {
      "module": "Order Execution & Risk Management",
      "description": "Functions for placing, modifying, and canceling orders, along with core risk control mechanisms and comprehensive position lifecycle management.",
      "functions": [
        {
          "name": "XRScalperBot.get_account_balance",
          "description": "Retrieves the available trading balance for a specific coin (default 'USDT') from the Bybit Unified Trading Account using `pybit`'s `get_wallet_balance`. Focuses on 'availableToWithdraw' for actionable balance, crucial for position sizing."
        },
        {
          "name": "XRScalperBot.get_current_positions",
          "description": "Fetches all active open positions (or for a specific symbol) from Bybit using `pybit`'s `get_positions`. It parses detailed position metrics (size, entry, mark price, PnL, leverage, liquidation price, creation/update times) and robustly updates the bot's internal `self.open_positions` dictionary. The updated state is saved to `bot_state.json`."
        },
        {
          "name": "XRScalperBot.get_open_orders",
          "description": "Fetches all current open orders for a specified symbol or all symbols using `pybit`'s `get_open_orders` endpoint."
        },
        {
          "name": "XRScalperBot.cancel_all_open_orders",
          "description": "Sends a request to cancel all open orders for a specific symbol or all symbols in the 'linear' category using `pybit`'s `cancel_all_orders` endpoint. Primarily used for risk management during bot shutdown or before new entries."
        },
        {
          "name": "XRScalperBot.set_leverage",
          "description": "Sets the desired leverage for a given trading symbol using `pybit`'s `set_leverage` endpoint. It first checks the current leverage of any existing positions to avoid redundant API calls. Configures leverage for both 'Buy' and 'Sell' sides."
        },
        {
          "name": "XRScalperBot.calculate_position_size",
          "description": "Calculates the optimal trade quantity (in contracts) for a new position. The calculation is based on the available account balance, the configured `risk_per_trade` percentage, the leverage, and the ATR-defined `stop_loss_atr_multiple`. Ensures the calculated quantity adheres to exchange-specific precision rules (`_apply_qty_precision`)."
        },
        {
          "name": "XRScalperBot.place_order",
          "description": "Executes a trade order (Market or Limit, Buy or Sell). It applies quantity and price precision using internal helper methods. For new entry orders (not `reduce_only`), it checks for existing open orders for the symbol to prevent over-trading. Generates a unique `orderLinkId` for tracking. Returns a simplified dictionary representing the placed order with key metrics (`id`, `clientOrderId`, `symbol`, `side`, `type`, `status`, `amount`, `price`, `timestamp`)."
        },
        {
          "name": "XRScalperBot.set_trading_stop",
          "description": "Sets or updates take-profit (TP), stop-loss (SL), and trailing stop-loss (TSL) for an active position using `pybit`'s `set_trading_stop` endpoint. It calculates initial TP/SL based on ATR multiples if not explicitly provided, applies price precision, and uses 'MarkPrice' as the default trigger. Updates the internal `open_positions` state after successful modification."
        },
        {
          "name": "XRScalperBot.manage_position",
          "description": "Manages an existing open position through its lifecycle. This includes dynamic adjustments to risk parameters like: Break-Even (BE) Stop-Loss (moves SL to entry price once a predefined ATR-based profit is reached), Partial Take-Profits (PTP) (closes a percentage of the position at configured ATR-based profit levels), and Time-Based Exit (closes the position if it has been open for longer than a specified duration). Updates internal position state and saves it."
        },
        {
          "name": "XRScalperBot.close_position",
          "description": "Closes a specified quantity of an open position by placing a market order in the opposite direction, utilizing `reduceOnly=True` for proper position closure. Updates the internal `open_positions` state via `get_current_positions` in the next loop. Used for both full and partial exits."
        },
        {
          "name": "XRScalperBot._check_global_loss_limit",
          "description": "Monitors the overall account balance (total equity) against a configured maximum total loss percentage (`max_total_loss_percentage`). If the current balance drops below this threshold relative to the `initial_balance`, it triggers a critical warning and initiates a graceful shutdown to prevent further losses."
        },
        {
          "name": "XRScalperBot.cancel_order_by_id",
          "description": "Cancels a specific order by its unique exchange or client ID."
        },
        {
          "name": "XRScalperBot.amend_order",
          "description": "Modifies an existing open order (e.g., changes price or quantity for a limit order)."
        },
        {
          "name": "XRScalperBot.set_margin_mode",
          "description": "Sets isolated or cross margin mode for a specific symbol or account."
        },
        {
          "name": "XRScalperBot.set_position_mode",
          "description": "Sets one-way or hedge mode for a symbol, affecting how long/short positions are handled."
        },
        {
          "name": "XRScalperBot.get_order_history",
          "description": "Fetches past order history (filled, canceled, rejected orders)."
        },
        {
          "name": "XRScalperBot.get_trade_history",
          "description": "Fetches executed trade history, including fees and realized PnL."
        },
        {
          "name": "XRScalperBot.calculate_max_drawdown",
          "description": "Calculates the bot's maximum historical drawdown based on account equity."
        },
        {
          "name": "XRScalperBot.get_funding_fee_rate",
          "description": "Fetches current funding fee rate for a symbol, important for perpetual contracts."
        },
        {
          "name": "XRScalperBot.calculate_slippage",
          "description": "Estimates potential slippage for market orders based on order book depth."
        },
        {
          "name": "XRScalperBot.check_liquidation_risk",
          "description": "Monitors a position's proximity to its liquidation price and alerts if risk is high."
        },
        {
          "name": "XRScalperBot.adjust_leverage_dynamically",
          "description": "Dynamically adjusts leverage based on market conditions or strategy risk."
        }
      ]
    },
    {
      "module": "Strategy Logic",
      "description": "Abstract base class for trading strategies and a concrete example, demonstrating robust signal generation with dynamic indicator parameters.",
      "functions": [
        {
          "name": "BaseStrategy.__init__",
          "description": "Constructor for the abstract `BaseStrategy` class. Initializes common strategy attributes such as configuration, indicator parameters, and weight sets for signal scoring."
        },
        {
          "name": "BaseStrategy.generate_signal",
          "description": "Abstract method defining the core interface for trading strategies. Subclasses must implement this to analyze market data, order book sentiment, and Fibonacci pivots to generate a trading signal and relevant strategy information."
        },
        {
          "name": "MyScalpingStrategy.__init__",
          "description": "Constructor for the concrete `MyScalpingStrategy` class, inheriting from `BaseStrategy`. Performs any specific initialization for this particular strategy, logging its readiness."
        },
        {
          "name": "MyScalpingStrategy.generate_signal",
          "description": "Implements a detailed example trading strategy. It calculates buy/sell scores based on a weighted combination of: EMA crossovers, RSI overbought/oversold, Stochastic RSI confirmations, Bollinger Band breakouts/reversals, PSAR trend changes, Momentum shifts, VWAP bias, CCI extremes, Williams %R extremes, SMA crossovers, Order Book sentiment, and Fibonacci pivot point interactions (bounces/breaks). Returns a signal (1, -1, or 0) and a rich `strategy_info` dictionary detailing indicator values and decision factors. Includes a helper for safe indicator value retrieval."
        },
        {
          "name": "MyScalpingStrategy.confirm_trend_with_volume",
          "description": "Adds volume-based confirmation to trend signals, ensuring stronger validation."
        },
        {
          "name": "MyScalpingStrategy.filter_signals_by_volatility",
          "description": "Filters or adjusts signals based on current market volatility (e.g., using ATR), avoiding trades in excessively calm or chaotic markets."
        },
        {
          "name": "MyScalpingStrategy.evaluate_multiple_timeframes",
          "description": "Integrates signals or trend confirmations from higher timeframes to provide a broader market context."
        },
        {
          "name": "MyScalpingStrategy.check_market_regime",
          "description": "Identifies the current market regime (e.g., trending, ranging, volatile) to adapt strategy parameters or enable/disable specific strategies."
        },
        {
          "name": "MyScalpingStrategy.adjust_signal_strength_dynamically",
          "description": "Dynamically adjusts the `signal_threshold` based on market conditions, potentially requiring stronger confluence in uncertain times."
        },
        {
          "name": "MyScalpingStrategy.implement_news_filter",
          "description": "Avoids trading during high-impact news events (requires integration with an external news API)."
        },
        {
          "name": "MyScalpingStrategy.optimize_entry_timing",
          "description": "Refines entry timing based on micro-structure or lower timeframe confirmations."
        },
        {
          "name": "MyScalpingStrategy.analyze_correlations",
          "description": "Considers correlations between symbols to avoid over-exposure or identify pairs trading opportunities."
        }
      ]
    },
    {
      "module": "Bot State & Persistence",
      "description": "Functions for saving and loading the bot's operational state to ensure continuity across restarts and recover from interruptions.",
      "functions": [
        {
          "name": "BotState.__init__",
          "description": "Constructor for the `BotState` class. Initializes the state data structure (`open_positions`, `initial_balance`, `last_run_time`) and attempts to load previous bot state from `bot_state.json` upon startup."
        },
        {
          "name": "BotState._load_state",
          "description": "Private method to load `open_positions`, `initial_balance`, and `last_run_time` from the state JSON file. Includes robust error handling for file operations and JSON decoding, ensuring a clean start if the file is corrupted or missing."
        },
        {
          "name": "BotState.save_state",
          "description": "Saves the current `open_positions`, `initial_balance`, and other bot-specific runtime data to the state JSON file, ensuring persistence across restarts. Converts `datetime` objects to Unix timestamps for serialization."
        },
        {
          "name": "BotState.get",
          "description": "Retrieves a value from the bot's internal state data by key, with an optional default value if the key is not found, preventing KeyError exceptions."
        },
        {
          "name": "BotState.set",
          "description": "Sets or updates a key-value pair within the bot's internal state data, providing a controlled interface for state modification."
        }
      ]
    },
    {
      "module": "Advanced Portfolio Management",
      "description": "Functions for managing multiple assets, accounts, and overall portfolio health beyond single-position control, focusing on capital allocation and risk aggregation.",
      "functions": [
        {
          "name": "PortfolioManager.get_total_equity",
          "description": "Calculates total portfolio equity across all assets/accounts, considering both available balance and open position PnL."
        },
        {
          "name": "PortfolioManager.rebalance_portfolio",
          "description": "Automatically rebalances asset allocation based on target percentages or risk exposure, potentially closing or opening positions."
        },
        {
          "name": "PortfolioManager.calculate_portfolio_pnl",
          "description": "Tracks and reports overall portfolio profit/loss (realized and unrealized) over various timeframes."
        },
        {
          "name": "PortfolioManager.manage_multi_symbol_exposure",
          "description": "Limits total capital exposure across all open positions, preventing over-leveraging across multiple symbols."
        },
        {
          "name": "PortfolioManager.diversify_trades",
          "description": "Ensures trades are diversified across uncorrelated assets or strategies to reduce systemic risk."
        },
        {
          "name": "PortfolioManager.track_commissions_and_fees",
          "description": "Monitors and logs all trading-related fees (trading fees, funding fees) for accurate PnL calculation."
        },
        {
          "name": "PortfolioManager.generate_performance_report",
          "description": "Creates detailed performance reports including metrics like Sharpe Ratio, Sortino Ratio, Calmar Ratio, max drawdown, and win rate."
        },
        {
          "name": "PortfolioManager.calculate_value_at_risk",
          "description": "Estimates the potential loss of the portfolio over a specified timeframe and confidence level."
        },
        {
          "name": "PortfolioManager.implement_circuit_breakers",
          "description": "Automatically pauses or stops trading if certain PnL or drawdown thresholds are hit within a session."
        }
      ]
    },
    {
      "module": "Execution Algorithms (Algos)",
      "description": "Functions for implementing sophisticated order execution strategies to minimize market impact, optimize fills, and handle large orders.",
      "functions": [
        {
          "name": "AlgoExecutor.execute_twap",
          "description": "Executes a Time-Weighted Average Price (TWAP) order, splitting a large order into smaller chunks over a defined time period."
        },
        {
          "name": "AlgoExecutor.execute_vwap_algo",
          "description": "Executes a Volume-Weighted Average Price (VWAP) order, attempting to match the market's historical volume profile over a period."
        },
        {
          "name": "AlgoExecutor.execute_iceberg_order",
          "description": "Manages an iceberg order, revealing only small portions of a large order to the market at a time to conceal true size."
        },
        {
          "name": "AlgoExecutor.manage_order_fills",
          "description": "Monitors and confirms partial and full order fills, updating internal state and initiating subsequent actions."
        },
        {
          "name": "AlgoExecutor.optimize_limit_order_placement",
          "description": "Dynamically adjusts limit order price based on order book depth, volatility, and desired fill probability for better fill rates."
        },
        {
          "name": "AlgoExecutor.minimize_slippage",
          "description": "Implements strategies to reduce slippage on market orders, such as splitting orders or using adaptive market orders."
        },
        {
          "name": "AlgoExecutor.handle_partial_fills",
          "description": "Manages the remaining quantity of partially filled orders, deciding whether to re-submit or cancel."
        },
        {
          "name": "AlgoExecutor.cancel_unfilled_orders_on_timeout",
          "description": "Automatically cancels limit orders that remain unfilled after a configured timeout period."
        }
      ]
    },
    {
      "module": "Backtesting & Optimization",
      "description": "Functions for historical simulation, strategy testing, and parameter optimization, essential for strategy development and validation.",
      "functions": [
        {
          "name": "Backtester.load_historical_data",
          "description": "Loads historical data for backtesting from local storage, a database, or direct exchange API calls for a specified period."
        },
        {
          "name": "Backtester.run_simulation",
          "description": "Executes a trading strategy against historical data, simulating trades and position management over time."
        },
        {
          "name": "Backtester.calculate_backtest_metrics",
          "description": "Computes detailed performance metrics from a backtest, including PnL, drawdown, win rate, Sharpe ratio, Sortino ratio, etc."
        },
        {
          "name": "Backtester.visualize_results",
          "description": "Generates interactive charts and graphs of backtest performance, equity curves, and trade visualizations."
        },
        {
          "name": "Optimizer.run_parameter_optimization",
          "description": "Searches for optimal strategy parameters using various techniques like grid search, random search, or genetic algorithms to maximize performance metrics."
        },
        {
          "name": "Optimizer.perform_walk_forward_analysis",
          "description": "Tests strategy robustness over out-of-sample data periods by repeatedly optimizing on in-sample data and testing on subsequent out-of-sample data."
        },
        {
          "name": "Optimizer.evaluate_overfitting",
          "description": "Assesses strategy for signs of overfitting to historical data, using techniques like Monte Carlo simulation or permutation tests."
        },
        {
          "name": "Optimizer.save_optimized_parameters",
          "description": "Saves the best-performing set of parameters found during optimization to a configuration file."
        },
        {
          "name": "Backtester.generate_trade_list",
          "description": "Outputs a detailed list of all simulated trades during a backtest for granular analysis."
        }
      ]
    },
    {
      "module": "Alerting & Notifications",
      "description": "Functions for sending critical alerts and performance updates to various communication channels, ensuring timely awareness of bot status and market events.",
      "functions": [
        {
          "name": "Notifier.send_email_alert",
          "description": "Sends email notifications for critical events like errors, shutdowns, or significant PnL changes."
        },
        {
          "name": "Notifier.send_telegram_message",
          "description": "Sends messages to a configured Telegram bot/channel for real-time alerts and status updates."
        },
        {
          "name": "Notifier.send_discord_webhook",
          "description": "Sends notifications via Discord webhook to a specified channel."
        },
        {
          "name": "Notifier.alert_on_pnl_threshold",
          "description": "Triggers alerts when PnL (daily, weekly, total) hits predefined profit or loss thresholds."
        },
        {
          "name": "Notifier.alert_on_api_error",
          "description": "Notifies on persistent API errors, connection issues, or authentication failures."
        },
        {
          "name": "Notifier.alert_on_liquidation_risk",
          "description": "Warns when a position approaches its liquidation price, allowing for manual intervention."
        },
        {
          "name": "Notifier.alert_on_new_position",
          "description": "Notifies when a new position is successfully opened."
        },
        {
          "name": "Notifier.alert_on_position_closed",
          "description": "Notifies when a position is closed, including realized PnL."
        },
        {
          "name": "Notifier.alert_on_system_resource_warning",
          "description": "Warns if CPU, memory, or disk usage exceeds predefined limits."
        }
      ]
    },
    {
      "module": "Database & Data Management",
      "description": "Functions for storing, retrieving, and managing large volumes of market and bot operational data in a persistent database (e.g., SQLite, PostgreSQL).",
      "functions": [
        {
          "name": "DatabaseManager.connect_db",
          "description": "Establishes and manages connection to a chosen database (e.g., SQLite for local, PostgreSQL for remote)."
        },
        {
          "name": "DatabaseManager.store_kline_data",
          "description": "Stores historical kline data in the database for long-term storage and backtesting."
        },
        {
          "name": "DatabaseManager.retrieve_kline_data",
          "description": "Retrieves kline data from the database for indicator calculations or backtesting."
        },
        {
          "name": "DatabaseManager.store_trade_data",
          "description": "Stores executed trade details (entry, exit, fees, PnL) for performance analysis."
        },
        {
          "name": "DatabaseManager.store_order_data",
          "description": "Stores order placement, modification, and status updates for auditing and debugging."
        },
        {
          "name": "DatabaseManager.store_position_data",
          "description": "Stores position lifecycle events and periodic PnL snapshots for detailed position tracking."
        },
        {
          "name": "DatabaseManager.clean_old_data",
          "description": "Removes outdated or unnecessary data from the database to optimize storage and query performance."
        },
        {
          "name": "DatabaseManager.backup_database",
          "description": "Performs a scheduled or manual backup of the entire database to a secure location."
        },
        {
          "name": "DatabaseManager.get_last_kline_timestamp",
          "description": "Retrieves the timestamp of the most recent kline stored for a symbol, to avoid fetching duplicate data."
        },
        {
          "name": "DatabaseManager.store_indicator_values",
          "description": "Optionally stores calculated indicator values for historical analysis or debugging."
        }
      ]
    },
    {
      "module": "Monitoring & Health Checks",
      "description": "Functions for continuous monitoring of bot health, performance, and external dependencies, ensuring operational stability.",
      "functions": [
        {
          "name": "HealthMonitor.check_api_connectivity",
          "description": "Periodically pings the exchange API to ensure continuous connectivity and responsiveness."
        },
        {
          "name": "HealthMonitor.check_disk_space",
          "description": "Monitors available disk space on the host system, alerting if storage runs critically low."
        },
        {
          "name": "HealthMonitor.check_memory_usage",
          "description": "Tracks the bot's memory consumption, identifying potential memory leaks or excessive resource usage."
        },
        {
          "name": "HealthMonitor.check_cpu_utilization",
          "description": "Monitors CPU usage by the bot process, detecting if the bot is consuming too many resources."
        },
        {
          "name": "HealthMonitor.log_performance_metrics",
          "description": "Logs internal bot performance metrics such as main loop duration, API response times, and processing times for various tasks."
        },
        {
          "name": "HealthMonitor.send_health_report",
          "description": "Compiles and sends periodic health reports via configured notification channels, summarizing bot status and resource usage."
        },
        {
          "name": "HealthMonitor.auto_restart_on_failure",
          "description": "Attempts to automatically restart the bot process on unrecoverable errors or critical failures, with configurable retry limits."
        },
        {
          "name": "HealthMonitor.check_system_clock_sync",
          "description": "Verifies that the system clock is synchronized with NTP servers to avoid timestamp-related API errors."
        },
        {
          "name": "HealthMonitor.monitor_trade_execution_latency",
          "description": "Measures the time taken from signal generation to order placement and fill confirmation."
        }
      ]
    },
    {
      "module": "User Interface & Interaction",
      "description": "Functions for command-line or web-based interaction with the bot, providing control and monitoring capabilities.",
      "functions": [
        {
          "name": "CLI.display_status_summary",
          "description": "Shows a concise overview of bot status, open positions, current PnL, and recent activities directly in the command line."
        },
        {
          "name": "CLI.execute_manual_order",
          "description": "Allows manual placement of orders (market/limit, buy/sell) for any symbol via command line, bypassing strategy logic."
        },
        {
          "name": "CLI.cancel_all_orders_manual",
          "description": "Provides a manual override to cancel all outstanding orders on the exchange."
        },
        {
          "name": "CLI.toggle_trading_mode",
          "description": "Switches between live trading and dry run (paper trading) modes, allowing for safe testing."
        },
        {
          "name": "WebUI.render_dashboard",
          "description": "Renders a web-based dashboard for real-time bot monitoring, including charts, metrics, and position details."
        },
        {
          "name": "WebUI.display_charts",
          "description": "Integrates charting libraries (e.g., Plotly, TradingView Lightweight Charts) to display market data, indicators, and trade entries/exits on a web interface."
        },
        {
          "name": "WebUI.manage_strategy_settings",
          "description": "Allows modification of strategy parameters and risk settings via a user-friendly web interface, triggering dynamic config reloads."
        },
        {
          "name": "WebUI.view_logs",
          "description": "Provides a real-time view of the bot's logs through the web interface."
        },
        {
          "name": "WebUI.send_manual_notification",
          "description": "Allows sending a test notification to configured channels from the UI."
        }
      ]
    }
  ]
}
```
#!/usr/bin/env python

# ██████╗ ██╗   ██╗███████╗███╗   ███╗███████╗████████╗██╗   ██╗██╗   ██╗███████╗
# ██╔══██╗╚██╗ ██╔╝██╔════╝████╗ ████║██╔════╝╚══██╔══╝██║   ██║██║   ██║██╔════╝
# ██████╔╝ ╚████╔╝ ███████╗██╔████╔██║███████╗   ██║   ██║   ██║██║   ██║███████╗
# ██╔═══╝   ╚██╔╝  ╚════██║██║╚██╔╝██║╚════██║   ██║   ██║   ██║██║   ██║╚════██║
# ██║        ██║   ███████║██║ ╚═╝ ██║███████║   ██║   ╚██████╔╝╚██████╔╝███████║
# ╚═╝        ╚═╝   ╚══════╝╚═╝     ╚═╝╚══════╝   ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝
# Pyrmethus - Unified Scalping Spell v2.0.1 (Enhanced Robustness & Clarity)
# Conjures high-frequency trades on Bybit Futures with enhanced precision and adaptable strategies.

"""High-Frequency Trading Bot (Scalping) for Bybit USDT Futures
Version: 2.0.1 (Unified: Selectable Strategies + Precision + Native SL/TSL + Enhancements).

Features:
- Multiple strategies selectable via config: "DUAL_SUPERTREND", "STOCHRSI_MOMENTUM", "EHLERS_FISHER", "EHLERS_MA_CROSS".
- Enhanced Precision: Uses Decimal for critical financial calculations.
- Exchange-native Trailing Stop Loss (TSL) placed immediately after entry.
- Exchange-native fixed Stop Loss placed immediately after entry.
- ATR for volatility measurement and initial Stop-Loss calculation.
- Optional Volume spike and Order Book pressure confirmation.
- Risk-based position sizing with margin checks.
- Termux SMS alerts for critical events and trade actions.
- Robust error handling and logging with Neon color support.
- Graceful shutdown on KeyboardInterrupt with position/order closing attempt.
- Stricter position detection logic (Bybit V5 API).
- Improved data validation and handling of edge cases.

Disclaimer:
- **EXTREME RISK**: Educational purposes ONLY. High-risk. Use at own absolute risk.
- **EXCHANGE-NATIVE SL/TSL DEPENDENCE**: Relies on exchange-native orders. Subject to exchange performance, slippage, API reliability.
- Parameter Sensitivity: Requires significant tuning and testing.
- API Rate Limits: Monitor usage.
- Slippage: Market orders are prone to slippage.
- Test Thoroughly: **DO NOT RUN LIVE WITHOUT EXTENSIVE TESTNET/DEMO TESTING.**
- Termux Dependency: Requires Termux:API.
- API Changes: Code targets Bybit V5 via CCXT, updates may be needed.
"""

# Standard Library Imports
import logging
import os
import subprocess
import sys
import time
import traceback
from decimal import ROUND_HALF_UP, Decimal, DivisionByZero, InvalidOperation, getcontext
from typing import Any

# Third-party Libraries
try:
    import ccxt
    import pandas as pd
    import pandas_ta as ta  # type: ignore[import]
    from colorama import Back, Fore, Style
    from colorama import init as colorama_init
    from dotenv import load_dotenv
except ImportError as e:
    missing_pkg = e.name
    sys.exit(1)

# --- Initializations ---
colorama_init(autoreset=True)
load_dotenv()
getcontext().prec = (
    18  # Set Decimal precision (adjust as needed for higher precision assets)
)


# --- Configuration Class ---
class Config:
    """Loads and validates configuration parameters from environment variables.

    Attributes are dynamically set based on environment variables defined below.
    Provides type casting, default values, and validation for required parameters.
    """

    def __init__(self) -> None:
        """Initializes the configuration by loading environment variables."""
        logger.info(
            f"{Fore.MAGENTA}--- Summoning Configuration Runes ---{Style.RESET_ALL}"
        )
        # --- API Credentials ---
        self.api_key: str | None = self._get_env(
            "BYBIT_API_KEY", required=True, color=Fore.RED
        )
        self.api_secret: str | None = self._get_env(
            "BYBIT_API_SECRET", required=True, color=Fore.RED
        )

        # --- Trading Parameters ---
        self.symbol: str = self._get_env("SYMBOL", "BTC/USDT:USDT", color=Fore.YELLOW)
        self.interval: str = self._get_env("INTERVAL", "1m", color=Fore.YELLOW)
        self.leverage: int = self._get_env(
            "LEVERAGE", 10, cast_type=int, color=Fore.YELLOW
        )
        self.sleep_seconds: int = self._get_env(
            "SLEEP_SECONDS", 10, cast_type=int, color=Fore.YELLOW
        )

        # --- Strategy Selection ---
        self.strategy_name: str = self._get_env(
            "STRATEGY_NAME", "DUAL_SUPERTREND", color=Fore.CYAN
        ).upper()
        self.valid_strategies: list[str] = [
            "DUAL_SUPERTREND",
            "STOCHRSI_MOMENTUM",
            "EHLERS_FISHER",
            "EHLERS_MA_CROSS",
        ]
        if self.strategy_name not in self.valid_strategies:
            logger.critical(
                f"Invalid STRATEGY_NAME '{self.strategy_name}'. Valid options are: {self.valid_strategies}"
            )
            raise ValueError(
                f"Invalid STRATEGY_NAME '{self.strategy_name}'. Valid: {self.valid_strategies}"
            )
        logger.info(
            f"Selected Strategy: {Fore.CYAN}{self.strategy_name}{Style.RESET_ALL}"
        )

        # --- Risk Management ---
        self.risk_per_trade_percentage: Decimal = self._get_env(
            "RISK_PER_TRADE_PERCENTAGE", "0.005", cast_type=Decimal, color=Fore.GREEN
        )  # 0.5%
        self.atr_stop_loss_multiplier: Decimal = self._get_env(
            "ATR_STOP_LOSS_MULTIPLIER", "1.5", cast_type=Decimal, color=Fore.GREEN
        )
        self.max_order_usdt_amount: Decimal = self._get_env(
            "MAX_ORDER_USDT_AMOUNT", "500.0", cast_type=Decimal, color=Fore.GREEN
        )
        self.required_margin_buffer: Decimal = self._get_env(
            "REQUIRED_MARGIN_BUFFER", "1.05", cast_type=Decimal, color=Fore.GREEN
        )  # 5% buffer

        # --- Trailing Stop Loss (Exchange Native) ---
        self.trailing_stop_percentage: Decimal = self._get_env(
            "TRAILING_STOP_PERCENTAGE", "0.005", cast_type=Decimal, color=Fore.GREEN
        )  # 0.5% trail
        self.trailing_stop_activation_offset_percent: Decimal = self._get_env(
            "TRAILING_STOP_ACTIVATION_PRICE_OFFSET_PERCENT",
            "0.001",
            cast_type=Decimal,
            color=Fore.GREEN,
        )  # 0.1% offset

        # --- Dual Supertrend Parameters ---
        self.st_atr_length: int = self._get_env(
            "ST_ATR_LENGTH", 7, cast_type=int, color=Fore.CYAN
        )
        self.st_multiplier: Decimal = self._get_env(
            "ST_MULTIPLIER", "2.5", cast_type=Decimal, color=Fore.CYAN
        )
        self.confirm_st_atr_length: int = self._get_env(
            "CONFIRM_ST_ATR_LENGTH", 5, cast_type=int, color=Fore.CYAN
        )
        self.confirm_st_multiplier: Decimal = self._get_env(
            "CONFIRM_ST_MULTIPLIER", "2.0", cast_type=Decimal, color=Fore.CYAN
        )

        # --- StochRSI + Momentum Parameters ---
        self.stochrsi_rsi_length: int = self._get_env(
            "STOCHRSI_RSI_LENGTH", 14, cast_type=int, color=Fore.CYAN
        )
        self.stochrsi_stoch_length: int = self._get_env(
            "STOCHRSI_STOCH_LENGTH", 14, cast_type=int, color=Fore.CYAN
        )
        self.stochrsi_k_period: int = self._get_env(
            "STOCHRSI_K_PERIOD", 3, cast_type=int, color=Fore.CYAN
        )
        self.stochrsi_d_period: int = self._get_env(
            "STOCHRSI_D_PERIOD", 3, cast_type=int, color=Fore.CYAN
        )
        self.stochrsi_overbought: Decimal = self._get_env(
            "STOCHRSI_OVERBOUGHT", "80.0", cast_type=Decimal, color=Fore.CYAN
        )
        self.stochrsi_oversold: Decimal = self._get_env(
            "STOCHRSI_OVERSOLD", "20.0", cast_type=Decimal, color=Fore.CYAN
        )
        self.momentum_length: int = self._get_env(
            "MOMENTUM_LENGTH", 5, cast_type=int, color=Fore.CYAN
        )

        # --- Ehlers Fisher Transform Parameters ---
        self.ehlers_fisher_length: int = self._get_env(
            "EHLERS_FISHER_LENGTH", 10, cast_type=int, color=Fore.CYAN
        )
        self.ehlers_fisher_signal_length: int = self._get_env(
            "EHLERS_FISHER_SIGNAL_LENGTH", 1, cast_type=int, color=Fore.CYAN
        )  # Default to 1

        # --- Ehlers MA Cross Parameters ---
        self.ehlers_fast_period: int = self._get_env(
            "EHLERS_FAST_PERIOD", 10, cast_type=int, color=Fore.CYAN
        )
        self.ehlers_slow_period: int = self._get_env(
            "EHLERS_SLOW_PERIOD", 30, cast_type=int, color=Fore.CYAN
        )

        # --- Volume Analysis ---
        self.volume_ma_period: int = self._get_env(
            "VOLUME_MA_PERIOD", 20, cast_type=int, color=Fore.YELLOW
        )
        self.volume_spike_threshold: Decimal = self._get_env(
            "VOLUME_SPIKE_THRESHOLD", "1.5", cast_type=Decimal, color=Fore.YELLOW
        )
        self.require_volume_spike_for_entry: bool = self._get_env(
            "REQUIRE_VOLUME_SPIKE_FOR_ENTRY", "false", cast_type=bool, color=Fore.YELLOW
        )

        # --- Order Book Analysis ---
        self.order_book_depth: int = self._get_env(
            "ORDER_BOOK_DEPTH", 10, cast_type=int, color=Fore.YELLOW
        )
        self.order_book_ratio_threshold_long: Decimal = self._get_env(
            "ORDER_BOOK_RATIO_THRESHOLD_LONG",
            "1.2",
            cast_type=Decimal,
            color=Fore.YELLOW,
        )
        self.order_book_ratio_threshold_short: Decimal = self._get_env(
            "ORDER_BOOK_RATIO_THRESHOLD_SHORT",
            "0.8",
            cast_type=Decimal,
            color=Fore.YELLOW,
        )
        self.fetch_order_book_per_cycle: bool = self._get_env(
            "FETCH_ORDER_BOOK_PER_CYCLE", "false", cast_type=bool, color=Fore.YELLOW
        )

        # --- ATR Calculation (for Initial SL) ---
        self.atr_calculation_period: int = self._get_env(
            "ATR_CALCULATION_PERIOD", 14, cast_type=int, color=Fore.GREEN
        )

        # --- Termux SMS Alerts ---
        self.enable_sms_alerts: bool = self._get_env(
            "ENABLE_SMS_ALERTS", "false", cast_type=bool, color=Fore.MAGENTA
        )
        self.sms_recipient_number: str | None = self._get_env(
            "SMS_RECIPIENT_NUMBER", None, color=Fore.MAGENTA
        )
        self.sms_timeout_seconds: int = self._get_env(
            "SMS_TIMEOUT_SECONDS", 30, cast_type=int, color=Fore.MAGENTA
        )

        # --- CCXT / API Parameters ---
        self.default_recv_window: int = 10000
        self.order_book_fetch_limit: int = max(
            25, self.order_book_depth
        )  # Ensure fetch limit is at least 25 for L2 OB
        self.shallow_ob_fetch_depth: int = 5
        self.order_fill_timeout_seconds: int = self._get_env(
            "ORDER_FILL_TIMEOUT_SECONDS", 15, cast_type=int, color=Fore.YELLOW
        )

        # --- Internal Constants ---
        self.SIDE_BUY: str = "buy"
        self.SIDE_SELL: str = "sell"
        self.POS_LONG: str = "Long"
        self.POS_SHORT: str = "Short"
        self.POS_NONE: str = "None"
        self.USDT_SYMBOL: str = "USDT"
        self.RETRY_COUNT: int = 3
        self.RETRY_DELAY_SECONDS: int = 2
        self.API_FETCH_LIMIT_BUFFER: int = (
            10  # Extra candles to fetch beyond indicator needs
        )
        self.POSITION_QTY_EPSILON: Decimal = Decimal(
            "1e-9"
        )  # Small value to treat quantities near zero
        self.POST_CLOSE_DELAY_SECONDS: int = (
            3  # Wait time after closing position before next action
        )

        logger.info(
            f"{Fore.MAGENTA}--- Configuration Runes Summoned Successfully ---{Style.RESET_ALL}"
        )

    def _get_env(
        self,
        key: str,
        default: Any = None,
        cast_type: type = str,
        required: bool = False,
        color: str = Fore.WHITE,
    ) -> Any:
        """Fetches an environment variable, casts its type, logs the value, and handles defaults or errors.

        Args:
            key: The environment variable key name.
            default: The default value to use if the environment variable is not set.
            cast_type: The type to cast the environment variable value to (e.g., int, float, bool, Decimal).
            required: If True, raises a ValueError if the environment variable is not set and no default is provided.
            color: The colorama Fore color to use for logging this parameter.

        Returns:
            The environment variable value, cast to the specified type, or the default value.

        Raises:
            ValueError: If a required environment variable is not set.
        """
        value_str = os.getenv(key)
        value = None
        log_source = ""

        if value_str is not None:
            log_source = f"(from env: '{value_str}')"
            try:
                if cast_type == bool:
                    value = value_str.lower() in ["true", "1", "yes", "y"]
                elif cast_type == Decimal:
                    value = Decimal(value_str)
                elif cast_type is not None:
                    value = cast_type(value_str)
                else:
                    value = value_str  # Keep as string if cast_type is None
            except (ValueError, TypeError, InvalidOperation) as e:
                logger.error(
                    f"{Fore.RED}Invalid type/value for {key}: '{value_str}'. Expected {cast_type.__name__}. Error: {e}. Using default: '{default}'{Style.RESET_ALL}"
                )
                value = default  # Fallback to default on casting error
                log_source = f"(env parse error, using default: '{default}')"
        else:
            value = default
            log_source = (
                f"(not set, using default: '{default}')"
                if default is not None
                else "(not set, no default)"
            )

        if value is None and required:
            critical_msg = f"CRITICAL: Required environment variable '{key}' not set and no default value provided."
            logger.critical(
                f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}{critical_msg}{Style.RESET_ALL}"
            )
            raise ValueError(critical_msg)

        logger.debug(f"{color}Config {key}: {value} {log_source}{Style.RESET_ALL}")
        return value


# --- Logger Setup ---
LOGGING_LEVEL: int = (
    logging.DEBUG if os.getenv("DEBUG", "false").lower() == "true" else logging.INFO
)
logging.basicConfig(
    level=LOGGING_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],  # Ensure logs go to stdout
)
logger: logging.Logger = logging.getLogger(__name__)

# Custom SUCCESS level and Neon Color Formatting
SUCCESS_LEVEL: int = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


def log_success(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """Adds a custom 'success' log level."""
    if self.isEnabledFor(SUCCESS_LEVEL):
        # pylint: disable=protected-access
        self._log(SUCCESS_LEVEL, message, args, **kwargs)


logging.Logger.success = log_success  # type: ignore[attr-defined]

# Apply colors only if output is a TTY (console)
if sys.stdout.isatty():
    logging.addLevelName(
        logging.DEBUG,
        f"{Fore.CYAN}{logging.getLevelName(logging.DEBUG)}{Style.RESET_ALL}",
    )
    logging.addLevelName(
        logging.INFO,
        f"{Fore.BLUE}{logging.getLevelName(logging.INFO)}{Style.RESET_ALL}",
    )
    logging.addLevelName(
        SUCCESS_LEVEL,
        f"{Fore.MAGENTA}{logging.getLevelName(SUCCESS_LEVEL)}{Style.RESET_ALL}",
    )
    logging.addLevelName(
        logging.WARNING,
        f"{Fore.YELLOW}{logging.getLevelName(logging.WARNING)}{Style.RESET_ALL}",
    )
    logging.addLevelName(
        logging.ERROR,
        f"{Fore.RED}{logging.getLevelName(logging.ERROR)}{Style.RESET_ALL}",
    )
    logging.addLevelName(
        logging.CRITICAL,
        f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}{logging.getLevelName(logging.CRITICAL)}{Style.RESET_ALL}",
    )

# --- Global Objects ---
try:
    CONFIG = Config()
except ValueError as e:
    logger.critical(
        f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}Configuration Error: {e}{Style.RESET_ALL}"
    )
    sys.exit(1)
except Exception as e:
    logger.critical(
        f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}Unexpected Error initializing configuration: {e}{Style.RESET_ALL}"
    )
    logger.debug(traceback.format_exc())
    sys.exit(1)


# --- Helper Functions ---
def safe_decimal_conversion(value: Any, default: Decimal = Decimal("0.0")) -> Decimal:
    """Safely converts a value to Decimal, returning a default if conversion fails.

    Args:
        value: The value to convert (can be string, float, int, Decimal, etc.).
        default: The Decimal value to return if conversion fails.

    Returns:
        The converted Decimal value or the default.
    """
    if value is None:
        return default
    try:
        # Explicitly convert to string first to handle floats accurately
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        logger.warning(
            f"Could not convert '{value}' (type: {type(value).__name__}) to Decimal, using default {default}"
        )
        return default


def format_order_id(order_id: str | int | None) -> str:
    """Returns the last 6 characters of an order ID or 'N/A' if None.

    Args:
        order_id: The order ID string or integer.

    Returns:
        A shortened representation of the order ID or 'N/A'.
    """
    return str(order_id)[-6:] if order_id else "N/A"


# --- Precision Formatting ---
def format_price(
    exchange: ccxt.Exchange, symbol: str, price: float | Decimal | str
) -> str:
    """Formats a price according to the market's precision rules using CCXT.

    Args:
        exchange: The CCXT exchange instance.
        symbol: The market symbol (e.g., 'BTC/USDT:USDT').
        price: The price value to format.

    Returns:
        The price formatted as a string according to market rules.
    """
    try:
        # CCXT formatting methods often expect float input, convert Decimal safely
        price_float = float(price)
        return exchange.price_to_precision(symbol, price_float)
    except (ValueError, TypeError, OverflowError, ccxt.ExchangeError, Exception) as e:
        logger.error(
            f"{Fore.RED}Error formatting price '{price}' for {symbol}: {e}{Style.RESET_ALL}"
        )
        # Fallback to Decimal string representation with normalization
        try:
            return str(Decimal(str(price)).normalize())
        except (InvalidOperation, TypeError, ValueError):
            return str(price)  # Absolute fallback


def format_amount(
    exchange: ccxt.Exchange, symbol: str, amount: float | Decimal | str
) -> str:
    """Formats an amount (quantity) according to the market's precision rules using CCXT.

    Args:
        exchange: The CCXT exchange instance.
        symbol: The market symbol (e.g., 'BTC/USDT:USDT').
        amount: The amount value to format.

    Returns:
        The amount formatted as a string according to market rules.
    """
    try:
        # CCXT formatting methods often expect float input, convert Decimal safely
        amount_float = float(amount)
        return exchange.amount_to_precision(symbol, amount_float)
    except (ValueError, TypeError, OverflowError, ccxt.ExchangeError, Exception) as e:
        logger.error(
            f"{Fore.RED}Error formatting amount '{amount}' for {symbol}: {e}{Style.RESET_ALL}"
        )
        # Fallback to Decimal string representation with normalization
        try:
            return str(Decimal(str(amount)).normalize())
        except (InvalidOperation, TypeError, ValueError):
            return str(amount)  # Absolute fallback


# --- Termux SMS Alert Function ---
def send_sms_alert(message: str) -> bool:
    """Sends an SMS alert using the Termux:API command-line tool.

    Args:
        message: The text message content to send.

    Returns:
        True if the command executed successfully (return code 0), False otherwise.
    """
    if not CONFIG.enable_sms_alerts:
        logger.debug("SMS alerts disabled via config.")
        return False
    if not CONFIG.sms_recipient_number:
        logger.warning(
            "SMS alerts enabled, but SMS_RECIPIENT_NUMBER is not set in config."
        )
        return False

    try:
        # Use shlex.quote for message safety if needed, but direct passing is usually fine for simple messages
        # quoted_message = shlex.quote(message)
        command: list[str] = [
            "termux-sms-send",
            "-n",
            CONFIG.sms_recipient_number,
            message,
        ]
        logger.info(
            f'{Fore.MAGENTA}Attempting SMS to {CONFIG.sms_recipient_number} (Timeout: {CONFIG.sms_timeout_seconds}s): "{message[:50]}..."{Style.RESET_ALL}'
        )

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,  # Don't raise exception on non-zero exit code
            timeout=CONFIG.sms_timeout_seconds,
        )

        if result.returncode == 0:
            logger.success(
                f"{Fore.MAGENTA}SMS command executed successfully.{Style.RESET_ALL}"
            )
            return True
        else:
            stderr_msg = result.stderr.strip() if result.stderr else "No stderr output"
            logger.error(
                f"{Fore.RED}SMS command failed. RC: {result.returncode}, Stderr: {stderr_msg}{Style.RESET_ALL}"
            )
            return False
    except FileNotFoundError:
        logger.error(
            f"{Fore.RED}SMS failed: 'termux-sms-send' command not found. Is Termux:API app installed and configured?{Style.RESET_ALL}"
        )
        return False
    except subprocess.TimeoutExpired:
        logger.error(
            f"{Fore.RED}SMS failed: Command timed out after {CONFIG.sms_timeout_seconds}s.{Style.RESET_ALL}"
        )
        return False
    except Exception as e:
        logger.error(
            f"{Fore.RED}SMS failed: Unexpected error during execution: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        return False


# --- Exchange Initialization ---
def initialize_exchange() -> ccxt.Exchange | None:
    """Initializes and returns the CCXT Bybit exchange instance using API keys from config.

    Performs basic checks like loading markets and fetching balance.

    Returns:
        A configured CCXT Bybit exchange instance, or None if initialization fails.
    """
    logger.info(f"{Fore.BLUE}Initializing CCXT Bybit connection...{Style.RESET_ALL}")
    if not CONFIG.api_key or not CONFIG.api_secret:
        logger.critical("API Key or Secret is missing in configuration.")
        send_sms_alert("[ScalpBot] CRITICAL: API keys missing. Bot stopped.")
        return None
    try:
        exchange = ccxt.bybit(
            {
                "apiKey": CONFIG.api_key,
                "secret": CONFIG.api_secret,
                "enableRateLimit": True,  # Enable built-in rate limiting
                "options": {
                    "defaultType": "linear",  # Default to linear contracts (USDT margined)
                    "recvWindow": CONFIG.default_recv_window,
                    "adjustForTimeDifference": True,  # Auto-adjust timestamp if needed
                    # 'verbose': True, # Uncomment for detailed API request/response logging
                },
            }
        )
        logger.debug("Loading markets (forced reload)...")
        exchange.load_markets(True)  # Force reload to get latest info
        logger.debug("Performing initial balance check...")
        exchange.fetch_balance()  # Check if API keys are valid by fetching balance
        logger.success(
            f"{Fore.GREEN}{Style.BRIGHT}CCXT Bybit Session Initialized (LIVE SCALPING MODE - EXTREME CAUTION!).{Style.RESET_ALL}"
        )
        send_sms_alert("[ScalpBot] Initialized & authenticated successfully.")
        return exchange

    except ccxt.AuthenticationError as e:
        logger.critical(
            f"Authentication failed: {e}. Check API keys, IP whitelist, and permissions on Bybit."
        )
        send_sms_alert(f"[ScalpBot] CRITICAL: Authentication FAILED: {e}. Bot stopped.")
    except ccxt.NetworkError as e:
        logger.critical(
            f"Network error during initialization: {e}. Check internet connection and Bybit status."
        )
        send_sms_alert(f"[ScalpBot] CRITICAL: Network Error on Init: {e}. Bot stopped.")
    except ccxt.ExchangeError as e:
        logger.critical(
            f"Exchange error during initialization: {e}. Check Bybit status or API documentation."
        )
        send_sms_alert(
            f"[ScalpBot] CRITICAL: Exchange Error on Init: {e}. Bot stopped."
        )
    except Exception as e:
        logger.critical(f"Unexpected error during exchange initialization: {e}")
        logger.debug(traceback.format_exc())
        send_sms_alert(
            f"[ScalpBot] CRITICAL: Unexpected Init Error: {type(e).__name__}. Bot stopped."
        )

    return None


# --- Indicator Calculation Functions ---
def calculate_supertrend(
    df: pd.DataFrame, length: int, multiplier: Decimal, prefix: str = ""
) -> pd.DataFrame:
    """Calculates the Supertrend indicator using pandas_ta.

    Args:
        df: DataFrame with 'high', 'low', 'close' columns.
        length: The ATR lookback period for Supertrend.
        multiplier: The ATR multiplier for Supertrend.
        prefix: Optional prefix for the resulting columns (e.g., "confirm_").

    Returns:
        The input DataFrame with added Supertrend columns:
        - f'{prefix}supertrend': The Supertrend line value (Decimal).
        - f'{prefix}trend': Boolean, True if uptrend (price > Supertrend), False otherwise.
        - f'{prefix}st_long': Boolean, True if a long entry signal (trend flipped up) occurred.
        - f'{prefix}st_short': Boolean, True if a short entry signal (trend flipped down) occurred.
    """
    col_prefix = f"{prefix}" if prefix else ""
    target_cols = [
        f"{col_prefix}supertrend",
        f"{col_prefix}trend",
        f"{col_prefix}st_long",
        f"{col_prefix}st_short",
    ]
    # pandas_ta uses float in the generated column name string representation
    st_col = f"SUPERT_{length}_{float(multiplier)}"
    st_trend_col = f"SUPERTd_{length}_{float(multiplier)}"
    st_long_col = f"SUPERTl_{length}_{float(multiplier)}"
    st_short_col = f"SUPERTs_{length}_{float(multiplier)}"
    required_input_cols = ["high", "low", "close"]
    min_required_len = (
        length + 1
    )  # Need at least 'length' periods for ATR + 1 for comparison

    # Initialize target columns to NA
    for col in target_cols:
        df[col] = pd.NA

    if (
        df is None
        or df.empty
        or not all(c in df.columns for c in required_input_cols)
        or len(df) < min_required_len
    ):
        logger.warning(
            f"{Fore.YELLOW}Indicator Calc ({col_prefix}ST): Input invalid or too short (Len: {len(df) if df is not None else 0}, Need: {min_required_len}).{Style.RESET_ALL}"
        )
        return df

    try:
        # pandas_ta expects float multiplier, calculate in place
        df.ta.supertrend(length=length, multiplier=float(multiplier), append=True)

        # Check if pandas_ta created the expected raw columns
        if st_col not in df.columns or st_trend_col not in df.columns:
            raise KeyError(
                f"pandas_ta failed to create expected raw columns: {st_col}, {st_trend_col}"
            )

        # Convert Supertrend value to Decimal
        df[f"{col_prefix}supertrend"] = df[st_col].apply(
            lambda x: safe_decimal_conversion(x, default=Decimal("NaN"))
        )
        df[f"{col_prefix}trend"] = (
            df[st_trend_col] == 1
        )  # Boolean: True for uptrend (1), False for downtrend (-1)

        # Calculate flip signals (requires previous trend value)
        prev_trend = df[st_trend_col].shift(1)
        df[f"{col_prefix}st_long"] = (prev_trend == -1) & (
            df[st_trend_col] == 1
        )  # Flipped from down to up
        df[f"{col_prefix}st_short"] = (prev_trend == 1) & (
            df[st_trend_col] == -1
        )  # Flipped from up to down

        # Drop the raw columns generated by pandas_ta
        raw_st_cols_to_drop = [st_col, st_trend_col, st_long_col, st_short_col]
        df.drop(
            columns=[col for col in raw_st_cols_to_drop if col in df.columns],
            inplace=True,
        )

        # Log last calculated values for debugging
        last_st_val = df[f"{col_prefix}supertrend"].iloc[-1]
        if pd.notna(last_st_val):
            last_trend = "Up" if df[f"{col_prefix}trend"].iloc[-1] else "Down"
            signal = (
                "LONG"
                if df[f"{col_prefix}st_long"].iloc[-1]
                else ("SHORT" if df[f"{col_prefix}st_short"].iloc[-1] else "None")
            )
            logger.debug(
                f"Indicator Calc ({col_prefix}ST({length},{multiplier})): Trend={last_trend}, Val={last_st_val:.4f}, Signal={signal}"
            )
        else:
            logger.debug(
                f"Indicator Calc ({col_prefix}ST({length},{multiplier})): Resulted in NA for last candle."
            )

    except KeyError as e:
        logger.error(
            f"{Fore.RED}Indicator Calc ({col_prefix}ST): Missing column during calculation: {e}{Style.RESET_ALL}"
        )
        for col in target_cols:
            df[col] = pd.NA  # Ensure columns exist even on error
    except Exception as e:
        logger.error(
            f"{Fore.RED}Indicator Calc ({col_prefix}ST): Unexpected error: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        for col in target_cols:
            df[col] = pd.NA  # Ensure columns exist even on error
    return df


def analyze_volume_atr(
    df: pd.DataFrame, atr_len: int, vol_ma_len: int
) -> dict[str, Decimal | None]:
    """Calculates ATR, Volume Moving Average, and checks for volume spikes.

    Args:
        df: DataFrame with 'high', 'low', 'close', 'volume' columns.
        atr_len: The lookback period for ATR calculation.
        vol_ma_len: The lookback period for the Volume Moving Average.

    Returns:
        A dictionary containing:
        - 'atr': Calculated ATR value (Decimal), or None if calculation failed.
        - 'volume_ma': Volume Moving Average (Decimal), or None.
        - 'last_volume': Last candle's volume (Decimal), or None.
        - 'volume_ratio': Ratio of last volume to volume MA (Decimal), or None.
    """
    results: dict[str, Decimal | None] = {
        "atr": None,
        "volume_ma": None,
        "last_volume": None,
        "volume_ratio": None,
    }
    required_cols = ["high", "low", "close", "volume"]
    min_len = max(atr_len, vol_ma_len) + 1  # Need sufficient lookback

    if (
        df is None
        or df.empty
        or not all(c in df.columns for c in required_cols)
        or len(df) < min_len
    ):
        logger.warning(
            f"{Fore.YELLOW}Indicator Calc (Vol/ATR): Input invalid or too short (Len: {len(df) if df is not None else 0}, Need: {min_len}).{Style.RESET_ALL}"
        )
        return results

    try:
        # Calculate ATR using pandas_ta
        atr_col = f"ATRr_{atr_len}"  # Default ATR column name from pandas_ta
        df.ta.atr(length=atr_len, append=True)
        if atr_col in df.columns:
            last_atr = df[atr_col].iloc[-1]
            if pd.notna(last_atr):
                results["atr"] = safe_decimal_conversion(
                    last_atr, default=Decimal("NaN")
                )
            df.drop(
                columns=[atr_col], errors="ignore", inplace=True
            )  # Clean up raw column
        else:
            logger.warning(
                f"{Fore.YELLOW}Indicator Calc (ATR): Column '{atr_col}' not found after calculation.{Style.RESET_ALL}"
            )

        # Calculate Volume MA using pandas rolling mean
        volume_ma_col = "volume_ma"
        # Use min_periods to get a value even if window isn't full initially
        df[volume_ma_col] = (
            df["volume"]
            .rolling(window=vol_ma_len, min_periods=max(1, vol_ma_len // 2))
            .mean()
        )
        last_vol_ma = df[volume_ma_col].iloc[-1]
        last_vol = df["volume"].iloc[-1]

        if pd.notna(last_vol_ma):
            results["volume_ma"] = safe_decimal_conversion(
                last_vol_ma, default=Decimal("NaN")
            )
        if pd.notna(last_vol):
            results["last_volume"] = safe_decimal_conversion(
                last_vol, default=Decimal("NaN")
            )

        # Calculate Volume Ratio safely
        if (
            results["volume_ma"] is not None
            and results["volume_ma"] > CONFIG.POSITION_QTY_EPSILON
            and results["last_volume"] is not None
        ):
            try:
                results["volume_ratio"] = results["last_volume"] / results["volume_ma"]
            except (DivisionByZero, InvalidOperation):
                logger.warning(
                    "Indicator Calc (Vol/ATR): Division by zero or invalid operation calculating volume ratio."
                )
                results["volume_ratio"] = None
        else:
            results["volume_ratio"] = (
                None  # Set to None if MA is zero/negligible or volume is missing
            )

        if volume_ma_col in df.columns:
            df.drop(
                columns=[volume_ma_col], errors="ignore", inplace=True
            )  # Clean up temp column

        # Log results
        atr_str = (
            f"{results['atr']:.5f}"
            if results["atr"] is not None and not results["atr"].is_nan()
            else "N/A"
        )
        vol_ma_str = (
            f"{results['volume_ma']:.2f}"
            if results["volume_ma"] is not None and not results["volume_ma"].is_nan()
            else "N/A"
        )
        last_vol_str = (
            f"{results['last_volume']:.2f}"
            if results["last_volume"] is not None
            and not results["last_volume"].is_nan()
            else "N/A"
        )
        vol_ratio_str = (
            f"{results['volume_ratio']:.2f}"
            if results["volume_ratio"] is not None
            and not results["volume_ratio"].is_nan()
            else "N/A"
        )
        logger.debug(
            f"Indicator Calc: ATR({atr_len})={atr_str}, Vol={last_vol_str}, VolMA({vol_ma_len})={vol_ma_str}, VolRatio={vol_ratio_str}"
        )

    except KeyError as e:
        logger.error(
            f"{Fore.RED}Indicator Calc (Vol/ATR): Missing column: {e}{Style.RESET_ALL}"
        )
        results = dict.fromkeys(results)
    except Exception as e:
        logger.error(
            f"{Fore.RED}Indicator Calc (Vol/ATR): Unexpected error: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        results = dict.fromkeys(results)  # Reset on error
    return results


def calculate_stochrsi_momentum(
    df: pd.DataFrame, rsi_len: int, stoch_len: int, k: int, d: int, mom_len: int
) -> pd.DataFrame:
    """Calculates StochRSI (K and D lines) and Momentum indicator using pandas_ta.

    Args:
        df: DataFrame with 'close' column.
        rsi_len: Lookback period for RSI calculation within StochRSI.
        stoch_len: Lookback period for Stochastic calculation within StochRSI.
        k: Smoothing period for StochRSI %K line.
        d: Smoothing period for StochRSI %D line.
        mom_len: Lookback period for Momentum indicator.

    Returns:
        The input DataFrame with added columns:
        - 'stochrsi_k': StochRSI %K line value (Decimal).
        - 'stochrsi_d': StochRSI %D line value (Decimal).
        - 'momentum': Momentum value (Decimal).
    """
    target_cols = ["stochrsi_k", "stochrsi_d", "momentum"]
    # Estimate minimum length needed - StochRSI needs RSI + Stoch periods + smoothing
    min_len = max(rsi_len + stoch_len + max(k, d), mom_len) + 5  # Add buffer
    for col in target_cols:
        df[col] = pd.NA  # Initialize columns

    if df is None or df.empty or "close" not in df.columns or len(df) < min_len:
        logger.warning(
            f"{Fore.YELLOW}Indicator Calc (StochRSI/Mom): Input invalid or too short (Len: {len(df) if df is not None else 0}, Need ~{min_len}).{Style.RESET_ALL}"
        )
        return df
    try:
        # Calculate StochRSI - use append=False to get predictable column names
        stochrsi_df = df.ta.stochrsi(
            length=stoch_len, rsi_length=rsi_len, k=k, d=d, append=False
        )
        k_col = f"STOCHRSIk_{stoch_len}_{rsi_len}_{k}_{d}"
        d_col = f"STOCHRSId_{stoch_len}_{rsi_len}_{k}_{d}"

        if k_col in stochrsi_df.columns:
            df["stochrsi_k"] = stochrsi_df[k_col].apply(
                lambda x: safe_decimal_conversion(x, default=Decimal("NaN"))
            )
        else:
            logger.warning(
                f"{Fore.YELLOW}StochRSI K column '{k_col}' not found after calculation.{Style.RESET_ALL}"
            )

        if d_col in stochrsi_df.columns:
            df["stochrsi_d"] = stochrsi_df[d_col].apply(
                lambda x: safe_decimal_conversion(x, default=Decimal("NaN"))
            )
        else:
            logger.warning(
                f"{Fore.YELLOW}StochRSI D column '{d_col}' not found after calculation.{Style.RESET_ALL}"
            )

        # Calculate Momentum
        mom_col = f"MOM_{mom_len}"
        df.ta.mom(length=mom_len, append=True)  # Append momentum directly
        if mom_col in df.columns:
            df["momentum"] = df[mom_col].apply(
                lambda x: safe_decimal_conversion(x, default=Decimal("NaN"))
            )
            df.drop(
                columns=[mom_col], errors="ignore", inplace=True
            )  # Clean up raw column
        else:
            logger.warning(
                f"{Fore.YELLOW}Momentum column '{mom_col}' not found after calculation.{Style.RESET_ALL}"
            )

        # Log last values
        k_val, d_val, mom_val = (
            df["stochrsi_k"].iloc[-1],
            df["stochrsi_d"].iloc[-1],
            df["momentum"].iloc[-1],
        )
        if pd.notna(k_val) and pd.notna(d_val) and pd.notna(mom_val):
            logger.debug(
                f"Indicator Calc (StochRSI/Mom): K={k_val:.2f}, D={d_val:.2f}, Mom={mom_val:.4f}"
            )
        else:
            logger.debug(
                "Indicator Calc (StochRSI/Mom): Resulted in NA for last candle."
            )

    except KeyError as e:
        logger.error(
            f"{Fore.RED}Indicator Calc (StochRSI/Mom): Missing column: {e}{Style.RESET_ALL}"
        )
        for col in target_cols:
            df[col] = pd.NA
    except Exception as e:
        logger.error(
            f"{Fore.RED}Indicator Calc (StochRSI/Mom): Unexpected error: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        for col in target_cols:
            df[col] = pd.NA
    return df


def calculate_ehlers_fisher(df: pd.DataFrame, length: int, signal: int) -> pd.DataFrame:
    """Calculates the Ehlers Fisher Transform indicator using pandas_ta.

    Args:
        df: DataFrame with 'high', 'low' columns.
        length: The lookback period for the Fisher Transform.
        signal: The smoothing period for the signal line (usually 1).

    Returns:
        The input DataFrame with added columns:
        - 'ehlers_fisher': Fisher Transform value (Decimal).
        - 'ehlers_signal': Fisher Transform signal line value (Decimal).
    """
    target_cols = ["ehlers_fisher", "ehlers_signal"]
    min_len = length + signal  # Approximate minimum length
    for col in target_cols:
        df[col] = pd.NA  # Initialize columns

    if (
        df is None
        or df.empty
        or not all(c in df.columns for c in ["high", "low"])
        or len(df) < min_len
    ):
        logger.warning(
            f"{Fore.YELLOW}Indicator Calc (EhlersFisher): Input invalid or too short (Len: {len(df) if df is not None else 0}, Need ~{min_len}).{Style.RESET_ALL}"
        )
        return df
    try:
        # Calculate Fisher Transform - use append=False
        fisher_df = df.ta.fisher(length=length, signal=signal, append=False)
        fish_col = f"FISHERT_{length}_{signal}"
        signal_col = f"FISHERTs_{length}_{signal}"

        if fish_col in fisher_df.columns:
            df["ehlers_fisher"] = fisher_df[fish_col].apply(
                lambda x: safe_decimal_conversion(x, default=Decimal("NaN"))
            )
        else:
            logger.warning(
                f"{Fore.YELLOW}Ehlers Fisher column '{fish_col}' not found after calculation.{Style.RESET_ALL}"
            )

        if signal_col in fisher_df.columns:
            df["ehlers_signal"] = fisher_df[signal_col].apply(
                lambda x: safe_decimal_conversion(x, default=Decimal("NaN"))
            )
        else:
            logger.warning(
                f"{Fore.YELLOW}Ehlers Signal column '{signal_col}' not found after calculation.{Style.RESET_ALL}"
            )

        # Log last values
        fish_val, sig_val = df["ehlers_fisher"].iloc[-1], df["ehlers_signal"].iloc[-1]
        if pd.notna(fish_val) and pd.notna(sig_val):
            logger.debug(
                f"Indicator Calc (EhlersFisher({length},{signal})): Fisher={fish_val:.4f}, Signal={sig_val:.4f}"
            )
        else:
            logger.debug(
                "Indicator Calc (EhlersFisher): Resulted in NA for last candle."
            )

    except KeyError as e:
        logger.error(
            f"{Fore.RED}Indicator Calc (EhlersFisher): Missing column: {e}{Style.RESET_ALL}"
        )
        for col in target_cols:
            df[col] = pd.NA
    except Exception as e:
        logger.error(
            f"{Fore.RED}Indicator Calc (EhlersFisher): Unexpected error: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        for col in target_cols:
            df[col] = pd.NA
    return df


def calculate_ehlers_ma(df: pd.DataFrame, fast_len: int, slow_len: int) -> pd.DataFrame:
    """Calculates Ehlers-style Moving Averages (placeholder using EMA).

    Args:
        df: DataFrame with 'close' column.
        fast_len: Lookback period for the fast moving average.
        slow_len: Lookback period for the slow moving average.

    Returns:
        The input DataFrame with added columns:
        - 'fast_ema': Fast EMA value (Decimal).
        - 'slow_ema': Slow EMA value (Decimal).
    """
    target_cols = ["fast_ema", "slow_ema"]
    min_len = max(fast_len, slow_len) + 5  # Add buffer
    for col in target_cols:
        df[col] = pd.NA  # Initialize columns

    if df is None or df.empty or "close" not in df.columns or len(df) < min_len:
        logger.warning(
            f"{Fore.YELLOW}Indicator Calc (EhlersMA): Input invalid or too short (Len: {len(df) if df is not None else 0}, Need ~{min_len}).{Style.RESET_ALL}"
        )
        return df
    try:
        # WARNING: Placeholder Implementation!
        # pandas_ta.supersmoother might not exist or be reliable.
        # Using standard EMA as a substitute. Replace with a proper Ehlers filter
        # implementation (e.g., from another library or custom code) if true Ehlers MA is needed.
        logger.warning(
            f"{Fore.YELLOW}Using standard EMA as placeholder for Ehlers Super Smoother MAs. Review if accurate Ehlers MA is required.{Style.RESET_ALL}"
        )
        df["fast_ema"] = df.ta.ema(length=fast_len).apply(
            lambda x: safe_decimal_conversion(x, default=Decimal("NaN"))
        )
        df["slow_ema"] = df.ta.ema(length=slow_len).apply(
            lambda x: safe_decimal_conversion(x, default=Decimal("NaN"))
        )

        # Log last values
        fast_val, slow_val = df["fast_ema"].iloc[-1], df["slow_ema"].iloc[-1]
        if pd.notna(fast_val) and pd.notna(slow_val):
            logger.debug(
                f"Indicator Calc (EhlersMA({fast_len},{slow_len})): Fast={fast_val:.4f}, Slow={slow_val:.4f}"
            )
        else:
            logger.debug("Indicator Calc (EhlersMA): Resulted in NA for last candle.")

    except KeyError as e:
        logger.error(
            f"{Fore.RED}Indicator Calc (EhlersMA): Missing column: {e}{Style.RESET_ALL}"
        )
        for col in target_cols:
            df[col] = pd.NA
    except Exception as e:
        logger.error(
            f"{Fore.RED}Indicator Calc (EhlersMA): Unexpected error: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        for col in target_cols:
            df[col] = pd.NA
    return df


def analyze_order_book(
    exchange: ccxt.Exchange, symbol: str, depth: int, fetch_limit: int
) -> dict[str, Decimal | None]:
    """Fetches and analyzes the L2 order book for bid/ask pressure and spread.

    Args:
        exchange: The CCXT exchange instance.
        symbol: The market symbol.
        depth: The number of price levels (bids/asks) to consider for volume summation.
        fetch_limit: The number of price levels to request from the API (>= depth).

    Returns:
        A dictionary containing:
        - 'bid_ask_ratio': Ratio of cumulative bid volume to ask volume within the specified depth (Decimal), or None.
        - 'spread': Difference between best ask and best bid (Decimal), or None.
        - 'best_bid': Best bid price (Decimal), or None.
        - 'best_ask': Best ask price (Decimal), or None.
    """
    results: dict[str, Decimal | None] = {
        "bid_ask_ratio": None,
        "spread": None,
        "best_bid": None,
        "best_ask": None,
    }
    logger.debug(
        f"Order Book: Fetching L2 {symbol} (Depth:{depth}, Limit:{fetch_limit})..."
    )

    if not exchange.has.get("fetchL2OrderBook"):
        logger.warning(
            f"{Fore.YELLOW}Order Book: fetchL2OrderBook is not supported by {exchange.id}. Cannot analyze.{Style.RESET_ALL}"
        )
        return results
    try:
        # Fetch L2 order book data
        order_book = exchange.fetch_l2_order_book(symbol, limit=fetch_limit)
        bids: list[list[float | str]] = order_book.get("bids", [])
        asks: list[list[float | str]] = order_book.get("asks", [])

        if not bids or not asks:
            logger.warning(
                f"{Fore.YELLOW}Order Book: Fetched empty bids or asks for {symbol}.{Style.RESET_ALL}"
            )
            return results

        # Extract best bid/ask using safe conversion
        best_bid = (
            safe_decimal_conversion(bids[0][0], default=Decimal("NaN"))
            if len(bids[0]) > 0
            else Decimal("NaN")
        )
        best_ask = (
            safe_decimal_conversion(asks[0][0], default=Decimal("NaN"))
            if len(asks[0]) > 0
            else Decimal("NaN")
        )
        results["best_bid"] = best_bid if not best_bid.is_nan() else None
        results["best_ask"] = best_ask if not best_ask.is_nan() else None

        # Calculate spread
        if results["best_bid"] is not None and results["best_ask"] is not None:
            if results["best_ask"] > results["best_bid"]:  # Sanity check
                results["spread"] = results["best_ask"] - results["best_bid"]
                logger.debug(
                    f"OB: Bid={results['best_bid']:.4f}, Ask={results['best_ask']:.4f}, Spread={results['spread']:.4f}"
                )
            else:
                logger.warning(
                    f"{Fore.YELLOW}Order Book: Best bid ({results['best_bid']}) >= best ask ({results['best_ask']}). Spread calculation invalid.{Style.RESET_ALL}"
                )
                results["spread"] = None
        else:
            logger.debug(
                f"OB: Bid={results['best_bid'] or 'N/A'}, Ask={results['best_ask'] or 'N/A'} (Spread N/A)"
            )

        # Sum volumes within the specified depth using Decimal
        bid_vol = sum(
            safe_decimal_conversion(bid[1], default=Decimal("0"))
            for bid in bids[:depth]
            if len(bid) > 1
        )
        ask_vol = sum(
            safe_decimal_conversion(ask[1], default=Decimal("0"))
            for ask in asks[:depth]
            if len(ask) > 1
        )
        logger.debug(f"OB (Depth {depth}): BidVol={bid_vol:.4f}, AskVol={ask_vol:.4f}")

        # Calculate bid/ask ratio safely
        if ask_vol > CONFIG.POSITION_QTY_EPSILON:
            try:
                results["bid_ask_ratio"] = bid_vol / ask_vol
                logger.debug(f"OB Ratio: {results['bid_ask_ratio']:.3f}")
            except (DivisionByZero, InvalidOperation):
                logger.warning(
                    "Order Book: Error calculating OB ratio (division by zero or invalid operation)."
                )
                results["bid_ask_ratio"] = None
        else:
            logger.debug("OB Ratio: N/A (Ask volume zero or negligible)")
            results["bid_ask_ratio"] = None  # Explicitly set to None

    except (ccxt.NetworkError, ccxt.ExchangeError) as e:
        logger.warning(
            f"{Fore.YELLOW}Order Book: API Error fetching for {symbol}: {type(e).__name__} - {e}{Style.RESET_ALL}"
        )
    except (IndexError, TypeError, KeyError) as e:
        logger.warning(
            f"{Fore.YELLOW}Order Book: Error parsing data for {symbol}: {type(e).__name__} - {e}{Style.RESET_ALL}"
        )
    except Exception as e:
        logger.error(
            f"{Fore.RED}Order Book: Unexpected error for {symbol}: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())

    # Ensure None is returned for keys if any error occurred during calculation
    if any(
        v is not None and isinstance(v, Decimal) and v.is_nan()
        for v in results.values()
    ):
        results = {
            k: (v if not (isinstance(v, Decimal) and v.is_nan()) else None)
            for k, v in results.items()
        }

    return results


# --- Data Fetching ---
def get_market_data(
    exchange: ccxt.Exchange, symbol: str, interval: str, limit: int
) -> pd.DataFrame | None:
    """Fetches and prepares OHLCV data from the exchange.

    Args:
        exchange: The CCXT exchange instance.
        symbol: The market symbol.
        interval: The timeframe interval (e.g., '1m', '5m').
        limit: The maximum number of candles to fetch.

    Returns:
        A pandas DataFrame containing OHLCV data with a datetime index,
        or None if fetching or processing fails.
    """
    if not exchange.has.get("fetchOHLCV"):
        logger.error(
            f"{Fore.RED}Data Fetch: Exchange '{exchange.id}' does not support fetchOHLCV.{Style.RESET_ALL}"
        )
        return None
    try:
        logger.debug(
            f"Data Fetch: Fetching {limit} OHLCV candles for {symbol} ({interval})..."
        )
        # Fetch OHLCV data: [timestamp, open, high, low, close, volume]
        ohlcv: list[list[int | float | str]] = exchange.fetch_ohlcv(
            symbol, timeframe=interval, limit=limit
        )

        if not ohlcv:
            logger.warning(
                f"{Fore.YELLOW}Data Fetch: No OHLCV data returned for {symbol} ({interval}). Might be an invalid symbol or timeframe.{Style.RESET_ALL}"
            )
            return None

        # Create DataFrame
        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        if df.empty:
            logger.warning(
                f"{Fore.YELLOW}Data Fetch: OHLCV data for {symbol} resulted in an empty DataFrame.{Style.RESET_ALL}"
            )
            return None

        # Convert timestamp to datetime and set as index
        try:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df.set_index("timestamp", inplace=True)
        except Exception as e:
            logger.error(
                f"{Fore.RED}Data Fetch: Error processing timestamps: {e}{Style.RESET_ALL}"
            )
            return None

        # Convert OHLCV columns to numeric, coercing errors to NaN
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Check for and handle NaNs robustly
        if df.isnull().values.any():
            nan_counts = df.isnull().sum()
            logger.warning(
                f"{Fore.YELLOW}Data Fetch: OHLCV contains NaNs after conversion:\n{nan_counts[nan_counts > 0]}\nAttempting forward fill...{Style.RESET_ALL}"
            )
            df.ffill(inplace=True)  # Forward fill first (common for missing data)
            if df.isnull().values.any():  # Check again, backfill if needed
                logger.warning(
                    f"{Fore.YELLOW}NaNs remain after ffill, attempting backward fill...{Style.RESET_ALL}"
                )
                df.bfill(inplace=True)
                if df.isnull().values.any():
                    logger.error(
                        f"{Fore.RED}Data Fetch: NaNs persist even after ffill and bfill. Cannot proceed with this data.{Style.RESET_ALL}"
                    )
                    return None  # Cannot reliably use data with remaining NaNs

        logger.debug(
            f"Data Fetch: Successfully processed {len(df)} OHLCV candles for {symbol}."
        )
        return df

    except (ccxt.NetworkError, ccxt.ExchangeError) as e:
        logger.warning(
            f"{Fore.YELLOW}Data Fetch: API Error fetching OHLCV for {symbol}: {type(e).__name__} - {e}{Style.RESET_ALL}"
        )
    except (ValueError, TypeError, KeyError, Exception) as e:
        logger.error(
            f"{Fore.RED}Data Fetch: Error processing OHLCV data for {symbol}: {type(e).__name__} - {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())

    return None


# --- Position & Order Management ---
def get_current_position(exchange: ccxt.Exchange, symbol: str) -> dict[str, Any]:
    """Fetches the current position details for a given symbol, focusing on Bybit V5 API structure.

    Assumes One-Way Mode on Bybit.

    Args:
        exchange: The CCXT exchange instance.
        symbol: The market symbol (e.g., 'BTC/USDT:USDT').

    Returns:
        A dictionary containing:
        - 'side': Position side ('Long', 'Short', or 'None').
        - 'qty': Position quantity (Decimal), absolute value.
        - 'entry_price': Average entry price (Decimal).
        Returns default values (side='None', qty=0.0, entry_price=0.0) if no position or error.
    """
    default_pos: dict[str, Any] = {
        "side": CONFIG.POS_NONE,
        "qty": Decimal("0.0"),
        "entry_price": Decimal("0.0"),
    }
    market: dict | None = None
    market_id: str | None = None

    try:
        market = exchange.market(symbol)
        market_id = market[
            "id"
        ]  # Get the exchange-specific market ID (e.g., 'BTCUSDT')
    except (ccxt.BadSymbol, KeyError, Exception) as e:
        logger.error(
            f"{Fore.RED}Position Check: Failed to get market info for '{symbol}': {e}{Style.RESET_ALL}"
        )
        return default_pos

    if not market:  # Should not happen if above try succeeded, but check anyway
        logger.error(
            f"{Fore.RED}Position Check: Market info for '{symbol}' is unexpectedly None.{Style.RESET_ALL}"
        )
        return default_pos

    try:
        if not exchange.has.get("fetchPositions"):
            logger.warning(
                f"{Fore.YELLOW}Position Check: fetchPositions method not supported by {exchange.id}. Cannot check position.{Style.RESET_ALL}"
            )
            return default_pos

        # Determine category for Bybit V5 API call (linear or inverse)
        category = (
            "linear"
            if market.get("linear")
            else ("inverse" if market.get("inverse") else None)
        )
        if not category:
            logger.warning(
                f"{Fore.YELLOW}Position Check: Could not determine category (linear/inverse) for {symbol}. Assuming linear.{Style.RESET_ALL}"
            )
            category = "linear"  # Default assumption

        params = {"category": category}
        logger.debug(
            f"Position Check: Fetching positions for {symbol} (MarketID: {market_id}) with params: {params}"
        )

        # Fetch positions for the specific symbol
        fetched_positions = exchange.fetch_positions(symbols=[symbol], params=params)

        # Filter for the active position in One-Way mode
        active_pos_data = None
        for pos in fetched_positions:
            pos_info = pos.get("info", {})
            pos_market_id = pos_info.get("symbol")
            # Bybit V5 One-Way mode uses positionIdx 0. Hedge mode uses 1 for Buy, 2 for Sell.
            position_idx = pos_info.get(
                "positionIdx", -1
            )  # Use -1 default to indicate if not found
            pos_side_v5 = pos_info.get(
                "side", "None"
            )  # 'Buy' for long, 'Sell' for short, 'None' if flat
            size_str = pos_info.get("size")

            # Match market ID, check for One-Way mode (idx 0), and ensure side is not 'None' (means position exists)
            if (
                pos_market_id == market_id
                and position_idx == 0
                and pos_side_v5 != "None"
            ):
                size = safe_decimal_conversion(size_str)
                # Check if size is significant (greater than epsilon)
                if abs(size) > CONFIG.POSITION_QTY_EPSILON:
                    active_pos_data = (
                        pos  # Found the active position for this symbol in One-Way mode
                    )
                    break  # Assume only one such position exists per symbol in One-Way mode

        if active_pos_data:
            try:
                info = active_pos_data.get("info", {})
                size = safe_decimal_conversion(info.get("size"))
                # Use 'avgPrice' from info for V5 entry price
                entry_price = safe_decimal_conversion(info.get("avgPrice"))
                # Determine side based on V5 'side' field ('Buy' -> Long, 'Sell' -> Short)
                side = (
                    CONFIG.POS_LONG if info.get("side") == "Buy" else CONFIG.POS_SHORT
                )

                position_qty = abs(size)
                if position_qty <= CONFIG.POSITION_QTY_EPSILON:
                    logger.info(
                        f"Position Check: Found position for {market_id}, but size ({size}) is negligible. Treating as flat."
                    )
                    return default_pos

                logger.info(
                    f"{Fore.YELLOW}Position Check: Found ACTIVE {side} position: Qty={position_qty:.8f} @ Entry={entry_price:.4f}{Style.RESET_ALL}"
                )
                return {"side": side, "qty": position_qty, "entry_price": entry_price}
            except (KeyError, TypeError, Exception) as parse_err:
                logger.warning(
                    f"{Fore.YELLOW}Position Check: Error parsing active position data: {parse_err}. Data: {active_pos_data}{Style.RESET_ALL}"
                )
                return default_pos  # Return default on parsing error
        else:
            logger.info(
                f"Position Check: No active One-Way position found for {market_id}."
            )
            return default_pos

    except (ccxt.NetworkError, ccxt.ExchangeError) as e:
        logger.warning(
            f"{Fore.YELLOW}Position Check: API Error fetching positions for {symbol}: {type(e).__name__} - {e}{Style.RESET_ALL}"
        )
    except Exception as e:
        logger.error(
            f"{Fore.RED}Position Check: Unexpected error fetching positions for {symbol}: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())

    return default_pos  # Return default if any error occurs


def set_leverage(exchange: ccxt.Exchange, symbol: str, leverage: int) -> bool:
    """Sets leverage for a futures symbol, handling Bybit V5 API specifics.

    Args:
        exchange: The CCXT exchange instance.
        symbol: The market symbol.
        leverage: The desired leverage value (integer).

    Returns:
        True if leverage was set successfully or already set, False otherwise.
    """
    logger.info(
        f"{Fore.CYAN}Leverage Setting: Attempting to set {leverage}x for {symbol}...{Style.RESET_ALL}"
    )
    try:
        market = exchange.market(symbol)
        if not market.get("contract"):
            logger.error(
                f"{Fore.RED}Leverage Setting: Cannot set leverage for non-contract market: {symbol}.{Style.RESET_ALL}"
            )
            return False
    except (ccxt.BadSymbol, KeyError, Exception) as e:
        logger.error(
            f"{Fore.RED}Leverage Setting: Failed to get market info for '{symbol}': {e}{Style.RESET_ALL}"
        )
        return False

    for attempt in range(CONFIG.RETRY_COUNT):
        try:
            # Bybit V5 requires setting buyLeverage and sellLeverage separately via params
            # The main 'leverage' argument might also be needed depending on CCXT version/implementation
            params = {"buyLeverage": str(leverage), "sellLeverage": str(leverage)}
            logger.debug(
                f"Leverage Setting: Calling set_leverage with leverage={leverage}, symbol={symbol}, params={params}"
            )
            response = exchange.set_leverage(
                leverage=leverage, symbol=symbol, params=params
            )
            logger.success(
                f"{Fore.GREEN}Leverage Setting: Successfully set to {leverage}x for {symbol}. Response: {response}{Style.RESET_ALL}"
            )
            return True
        except ccxt.ExchangeError as e:
            # Check for common Bybit messages indicating leverage is already set or not modified
            err_str = str(e).lower()
            # Example error codes/messages from Bybit V5 (these might change):
            # 110044: "Set leverage not modified"
            # Specific string checks:
            if (
                "set leverage not modified" in err_str
                or "leverage is same as requested" in err_str
            ):
                logger.info(
                    f"{Fore.CYAN}Leverage Setting: Leverage already set to {leverage}x for {symbol}.{Style.RESET_ALL}"
                )
                return True
            logger.warning(
                f"{Fore.YELLOW}Leverage Setting: Exchange error (Attempt {attempt + 1}/{CONFIG.RETRY_COUNT}): {e}{Style.RESET_ALL}"
            )
            if attempt < CONFIG.RETRY_COUNT - 1:
                time.sleep(CONFIG.RETRY_DELAY_SECONDS)
            else:
                logger.error(
                    f"{Fore.RED}Leverage Setting: Failed after {CONFIG.RETRY_COUNT} attempts due to ExchangeError.{Style.RESET_ALL}"
                )
        except (ccxt.NetworkError, Exception) as e:
            logger.warning(
                f"{Fore.YELLOW}Leverage Setting: Network/Other error (Attempt {attempt + 1}/{CONFIG.RETRY_COUNT}): {e}{Style.RESET_ALL}"
            )
            if attempt < CONFIG.RETRY_COUNT - 1:
                time.sleep(CONFIG.RETRY_DELAY_SECONDS)
            else:
                logger.error(
                    f"{Fore.RED}Leverage Setting: Failed after {CONFIG.RETRY_COUNT} attempts due to {type(e).__name__}.{Style.RESET_ALL}"
                )
    return False


def close_position(
    exchange: ccxt.Exchange,
    symbol: str,
    position_to_close: dict[str, Any],
    reason: str = "Signal",
) -> dict[str, Any] | None:
    """Closes the specified active position by placing a market order with reduceOnly=True.
    Re-validates the position just before closing.

    Args:
        exchange: The CCXT exchange instance.
        symbol: The market symbol.
        position_to_close: A dictionary representing the position to close (from get_current_position).
        reason: A string indicating the reason for closing (for logging/alerts).

    Returns:
        The CCXT order dictionary if the close order was successfully placed, None otherwise.
    """
    initial_side = position_to_close.get("side", CONFIG.POS_NONE)
    initial_qty = position_to_close.get("qty", Decimal("0.0"))
    market_base = symbol.split("/")[0] if "/" in symbol else symbol
    logger.info(
        f"{Fore.YELLOW}Close Position: Initiated for {symbol}. Reason: {reason}. Initial state: {initial_side} Qty={initial_qty:.8f}{Style.RESET_ALL}"
    )

    # === Re-validate the position just before closing ===
    logger.debug("Close Position: Re-validating current position state...")
    live_position = get_current_position(exchange, symbol)
    live_position_side = live_position["side"]
    live_amount_to_close = live_position["qty"]

    if (
        live_position_side == CONFIG.POS_NONE
        or live_amount_to_close <= CONFIG.POSITION_QTY_EPSILON
    ):
        logger.warning(
            f"{Fore.YELLOW}Close Position: Re-validation shows NO active position (or negligible size) for {symbol}. Aborting close attempt.{Style.RESET_ALL}"
        )
        if initial_side != CONFIG.POS_NONE:
            logger.warning(
                f"{Fore.YELLOW}Close Position: Discrepancy detected (Bot thought position was {initial_side}, but exchange reports None/Zero).{Style.RESET_ALL}"
            )
        return None  # Nothing to close

    if live_position_side != initial_side:
        logger.warning(
            f"{Fore.YELLOW}Close Position: Discrepancy detected! Initial side was {initial_side}, live side is {live_position_side}. Closing live position.{Style.RESET_ALL}"
        )
        # Continue with closing the actual live position

    # Determine the side needed to close the position
    side_to_execute_close = (
        CONFIG.SIDE_SELL if live_position_side == CONFIG.POS_LONG else CONFIG.SIDE_BUY
    )

    try:
        # Format amount according to market precision
        amount_str = format_amount(exchange, symbol, live_amount_to_close)
        amount_decimal = safe_decimal_conversion(
            amount_str
        )  # Convert formatted string back to Decimal for check
        amount_float = float(amount_decimal)  # CCXT create order often expects float

        if amount_decimal <= CONFIG.POSITION_QTY_EPSILON:
            logger.error(
                f"{Fore.RED}Close Position: Closing amount '{amount_str}' after precision formatting is negligible. Aborting.{Style.RESET_ALL}"
            )
            return None

        logger.warning(
            f"{Back.YELLOW}{Fore.BLACK}Close Position: Attempting to CLOSE {live_position_side} ({reason}): "
            f"Exec {side_to_execute_close.upper()} MARKET {amount_str} {symbol} (reduce_only=True)...{Style.RESET_ALL}"
        )

        # Set reduceOnly parameter for closing orders
        params = {"reduceOnly": True}
        order = exchange.create_market_order(
            symbol=symbol,
            side=side_to_execute_close,
            amount=amount_float,
            params=params,
        )

        # Parse order response safely using Decimal
        order_id = order.get("id")
        order_id_short = format_order_id(order_id)
        status = order.get("status", "unknown")
        filled_qty = safe_decimal_conversion(order.get("filled"))
        avg_fill_price = safe_decimal_conversion(order.get("average"))
        cost = safe_decimal_conversion(order.get("cost"))

        logger.success(
            f"{Fore.GREEN}{Style.BRIGHT}Close Position: Order ({reason}) submitted for {symbol}. "
            f"ID:...{order_id_short}, Status: {status}, Filled: {filled_qty:.8f}/{amount_str}, AvgFill: {avg_fill_price:.4f}, Cost: {cost:.2f} USDT.{Style.RESET_ALL}"
        )
        # Note: Market orders might fill immediately, but status might be 'open' initially.
        # We don't wait for fill confirmation here, assuming reduceOnly works reliably.

        send_sms_alert(
            f"[{market_base}] Closed {live_position_side} {amount_str} @ ~{avg_fill_price:.4f} ({reason}). ID:...{order_id_short}"
        )
        return order  # Return the order details

    except ccxt.InsufficientFunds as e:
        logger.error(
            f"{Fore.RED}Close Position ({reason}): Insufficient funds for {symbol}: {e}{Style.RESET_ALL}"
        )
        send_sms_alert(
            f"[{market_base}] ERROR Closing ({reason}): Insufficient Funds. Check margin/position."
        )
    except ccxt.ExchangeError as e:
        # Check for specific Bybit errors indicating the position might already be closed or closing
        err_str = str(e).lower()
        # Example Bybit V5 error codes/messages (may change):
        # 110025: "Position size is zero" (or similar variations)
        # 110053: "The order would not reduce the position size"
        if (
            "position size is zero" in err_str
            or "order would not reduce position size" in err_str
            or "position is already zero" in err_str
        ):  # Add more known messages if needed
            logger.warning(
                f"{Fore.YELLOW}Close Position ({reason}): Exchange indicates position likely already closed/zero: {e}. Assuming closed.{Style.RESET_ALL}"
            )
            # Don't send error SMS, treat as effectively closed.
            return None  # Treat as success (nothing to close) in this specific case
        else:
            logger.error(
                f"{Fore.RED}Close Position ({reason}): Exchange error for {symbol}: {e}{Style.RESET_ALL}"
            )
            send_sms_alert(
                f"[{market_base}] ERROR Closing ({reason}): Exchange Error: {type(e).__name__}. Check logs."
            )
    except (ccxt.NetworkError, ValueError, TypeError, Exception) as e:
        logger.error(
            f"{Fore.RED}Close Position ({reason}): Failed for {symbol}: {type(e).__name__} - {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        send_sms_alert(
            f"[{market_base}] ERROR Closing ({reason}): {type(e).__name__}. Check logs."
        )

    return None  # Return None if closing failed


def calculate_position_size(
    equity: Decimal,
    risk_per_trade_pct: Decimal,
    entry_price: Decimal,
    stop_loss_price: Decimal,
    leverage: int,
    symbol: str,
    exchange: ccxt.Exchange,
) -> tuple[Decimal | None, Decimal | None]:
    """Calculates the position size based on risk percentage, entry/stop prices, and equity.

    Args:
        equity: Total available equity in USDT (Decimal).
        risk_per_trade_pct: The fraction of equity to risk per trade (e.g., 0.01 for 1%).
        entry_price: Estimated entry price (Decimal).
        stop_loss_price: Calculated stop-loss price (Decimal).
        leverage: The leverage used for the trade (int).
        symbol: The market symbol.
        exchange: The CCXT exchange instance.

    Returns:
        A tuple containing:
        - Calculated position quantity (Decimal), formatted to market precision, or None if calculation fails.
        - Estimated required margin for the position (Decimal), or None.
    """
    logger.debug(
        f"Risk Calc: Equity={equity:.4f}, Risk%={risk_per_trade_pct:.4%}, Entry={entry_price:.4f}, SL={stop_loss_price:.4f}, Lev={leverage}x"
    )

    # --- Input Validation ---
    if not (entry_price > 0 and stop_loss_price > 0):
        logger.error(
            f"{Fore.RED}Risk Calc Error: Invalid entry price ({entry_price}) or SL price ({stop_loss_price}). Must be positive.{Style.RESET_ALL}"
        )
        return None, None
    price_diff = abs(entry_price - stop_loss_price)
    if price_diff < CONFIG.POSITION_QTY_EPSILON:
        logger.error(
            f"{Fore.RED}Risk Calc Error: Entry price ({entry_price}) and SL price ({stop_loss_price}) are too close (Diff: {price_diff:.8f}).{Style.RESET_ALL}"
        )
        return None, None
    if not (0 < risk_per_trade_pct < 1):
        logger.error(
            f"{Fore.RED}Risk Calc Error: Invalid risk percentage: {risk_per_trade_pct:.4%}. Must be between 0 and 1 (exclusive).{Style.RESET_ALL}"
        )
        return None, None
    if equity <= 0:
        logger.error(
            f"{Fore.RED}Risk Calc Error: Invalid equity: {equity:.4f}. Must be positive.{Style.RESET_ALL}"
        )
        return None, None
    if leverage <= 0:
        logger.error(
            f"{Fore.RED}Risk Calc Error: Invalid leverage: {leverage}. Must be positive.{Style.RESET_ALL}"
        )
        return None, None

    try:
        # --- Calculation ---
        risk_amount_usdt: Decimal = equity * risk_per_trade_pct
        # For linear contracts (like BTC/USDT:USDT), the value of 1 unit of base currency (BTC) is its price in quote currency (USDT).
        # The risk per unit of the base currency is the price difference between entry and stop-loss.
        # Quantity = (Total Risk Amount) / (Risk Per Unit)
        quantity_raw: Decimal = risk_amount_usdt / price_diff

        # --- Apply Precision ---
        # Format the raw quantity according to market rules *then* convert back to Decimal for further use
        quantity_precise_str = format_amount(exchange, symbol, quantity_raw)
        quantity_precise = safe_decimal_conversion(quantity_precise_str)

        if quantity_precise <= CONFIG.POSITION_QTY_EPSILON:
            logger.warning(
                f"{Fore.YELLOW}Risk Calc Warning: Calculated quantity ({quantity_precise:.8f}) is negligible or zero. "
                f"RiskAmt={risk_amount_usdt:.4f}, PriceDiff={price_diff:.4f}. Cannot place order.{Style.RESET_ALL}"
            )
            return None, None

        # --- Calculate Estimated Margin ---
        position_value_usdt = quantity_precise * entry_price
        required_margin = position_value_usdt / Decimal(leverage)

        logger.debug(
            f"Risk Calc Result: RawQty={quantity_raw:.8f} -> PreciseQty={quantity_precise:.8f}, EstValue={position_value_usdt:.4f}, EstMargin={required_margin:.4f}"
        )
        return quantity_precise, required_margin

    except (DivisionByZero, InvalidOperation, OverflowError, Exception) as e:
        logger.error(
            f"{Fore.RED}Risk Calc Error: Unexpected exception during calculation: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        return None, None


def wait_for_order_fill(
    exchange: ccxt.Exchange, order_id: str, symbol: str, timeout_seconds: int
) -> dict[str, Any] | None:
    """Waits for a specific order to reach a 'closed' (filled) status by polling the exchange.

    Args:
        exchange: The CCXT exchange instance.
        order_id: The ID of the order to wait for.
        symbol: The market symbol of the order.
        timeout_seconds: Maximum time to wait in seconds.

    Returns:
        The filled order dictionary if the order status becomes 'closed' within the timeout,
        None if the order fails, is cancelled, or times out.
    """
    start_time = time.monotonic()
    order_id_short = format_order_id(order_id)
    logger.info(
        f"{Fore.CYAN}Waiting for order ...{order_id_short} ({symbol}) fill (Timeout: {timeout_seconds}s)...{Style.RESET_ALL}"
    )

    while time.monotonic() - start_time < timeout_seconds:
        try:
            # Fetch the order status
            order = exchange.fetch_order(order_id, symbol)
            status = order.get("status")
            logger.debug(f"Order ...{order_id_short} status: {status}")

            if status == "closed":
                logger.success(
                    f"{Fore.GREEN}Order ...{order_id_short} confirmed FILLED.{Style.RESET_ALL}"
                )
                return order
            elif status in ["canceled", "rejected", "expired"]:
                logger.error(
                    f"{Fore.RED}Order ...{order_id_short} reached failure status: '{status}'.{Style.RESET_ALL}"
                )
                return None  # Failed state
            # Continue polling if status is 'open', 'partiallyFilled', None, or other intermediate state

            time.sleep(0.5)  # Poll every 500ms

        except ccxt.OrderNotFound:
            # Can happen briefly after placing if the exchange hasn't registered it yet. Keep trying.
            elapsed = time.monotonic() - start_time
            logger.warning(
                f"{Fore.YELLOW}Order ...{order_id_short} not found yet (after {elapsed:.1f}s). Retrying...{Style.RESET_ALL}"
            )
            time.sleep(1)  # Wait a bit longer if not found initially
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            elapsed = time.monotonic() - start_time
            logger.warning(
                f"{Fore.YELLOW}API Error checking order ...{order_id_short} (after {elapsed:.1f}s): {type(e).__name__} - {e}. Retrying...{Style.RESET_ALL}"
            )
            time.sleep(CONFIG.RETRY_DELAY_SECONDS)  # Wait longer on API errors
        except Exception as e:
            elapsed = time.monotonic() - start_time
            logger.error(
                f"{Fore.RED}Unexpected error checking order ...{order_id_short} (after {elapsed:.1f}s): {e}. Stopping wait.{Style.RESET_ALL}"
            )
            logger.debug(traceback.format_exc())
            return None  # Stop waiting on unexpected errors

    # If loop finishes without returning, it timed out
    logger.error(
        f"{Fore.RED}Order ...{order_id_short} did NOT fill within the {timeout_seconds}s timeout.{Style.RESET_ALL}"
    )
    return None  # Timeout


def place_risked_market_order(
    exchange: ccxt.Exchange,
    symbol: str,
    side: str,  # CONFIG.SIDE_BUY or CONFIG.SIDE_SELL
    risk_percentage: Decimal,
    current_atr: Decimal | None,
    sl_atr_multiplier: Decimal,
    leverage: int,
    max_order_cap_usdt: Decimal,
    margin_check_buffer: Decimal,
    tsl_percent: Decimal,
    tsl_activation_offset_percent: Decimal,
) -> dict[str, Any] | None:
    """Manages the full process of placing a market entry order with risk management,
    waiting for fill, and then placing exchange-native fixed Stop Loss and Trailing Stop Loss.

    Args:
        exchange: CCXT exchange instance.
        symbol: Market symbol.
        side: Order side ('buy' or 'sell').
        risk_percentage: Risk per trade as a decimal (e.g., 0.01 for 1%).
        current_atr: Current ATR value (Decimal) for SL calculation.
        sl_atr_multiplier: Multiplier for ATR to set initial SL distance.
        leverage: Leverage to use.
        max_order_cap_usdt: Maximum position value in USDT (Decimal).
        margin_check_buffer: Buffer multiplier for margin check (e.g., 1.05 for 5%).
        tsl_percent: Trailing stop percentage as a decimal (e.g., 0.005 for 0.5%).
        tsl_activation_offset_percent: Activation offset percentage from entry for TSL (Decimal).

    Returns:
        The filled entry order dictionary if the entry was successful, None otherwise.
        Note: Success/failure of SL/TSL placement is logged/alerted but doesn't change the return value
              if the entry itself was filled. Check logs for SL/TSL status.
    """
    market_base = symbol.split("/")[0] if "/" in symbol else symbol
    log_prefix = f"Place Order ({side.upper()})"
    logger.info(
        f"{Fore.BLUE}{Style.BRIGHT}{log_prefix}: Initiating for {symbol}...{Style.RESET_ALL}"
    )

    # --- Preliminary Checks ---
    if current_atr is None or current_atr <= Decimal("0"):
        logger.error(
            f"{Fore.RED}{log_prefix}: Invalid ATR ({current_atr}). Cannot calculate SL or place order.{Style.RESET_ALL}"
        )
        return None
    if side not in [CONFIG.SIDE_BUY, CONFIG.SIDE_SELL]:
        logger.error(
            f"{Fore.RED}{log_prefix}: Invalid order side '{side}'.{Style.RESET_ALL}"
        )
        return None

    entry_price_estimate: Decimal | None = None
    initial_sl_price_estimate: Decimal | None = None
    final_quantity: Decimal | None = None
    market: dict | None = None
    filled_entry_order: dict[str, Any] | None = None  # Store the filled entry order

    try:
        # === Step 1: Get Balance, Market Info, Limits ===
        logger.debug(f"{log_prefix}: Fetching balance & market details...")
        balance = exchange.fetch_balance()
        market = exchange.market(symbol)  # Fetch market details once
        limits = market.get("limits", {})
        amount_limits = limits.get("amount", {})
        price_limits = limits.get("price", {})
        min_qty_str = amount_limits.get("min")
        max_qty_str = amount_limits.get("max")
        min_price_str = price_limits.get("min")
        min_qty = (
            safe_decimal_conversion(min_qty_str, default=Decimal("0"))
            if min_qty_str
            else Decimal("0")
        )
        max_qty = (
            safe_decimal_conversion(max_qty_str) if max_qty_str else None
        )  # Can be None if no max limit
        min_price = (
            safe_decimal_conversion(min_price_str, default=Decimal("0"))
            if min_price_str
            else Decimal("0")
        )

        # Get USDT balance (adjust symbol if using different quote currency)
        usdt_balance = balance.get(CONFIG.USDT_SYMBOL, {})
        # Prefer 'total' equity, fallback to 'free' if 'total' isn't available/zero
        usdt_total = safe_decimal_conversion(usdt_balance.get("total"))
        usdt_free = safe_decimal_conversion(usdt_balance.get("free"))
        usdt_equity = usdt_total if usdt_total > 0 else usdt_free

        if usdt_equity <= 0:
            logger.error(
                f"{Fore.RED}{log_prefix}: Zero or negative equity ({usdt_equity:.4f}). Cannot place order.{Style.RESET_ALL}"
            )
            return None
        if usdt_free < 0:  # Free margin should not be negative
            logger.error(
                f"{Fore.RED}{log_prefix}: Negative free margin ({usdt_free:.4f}). Cannot place order.{Style.RESET_ALL}"
            )
            return None
        logger.debug(
            f"{log_prefix}: Equity={usdt_equity:.4f} USDT, Free={usdt_free:.4f} USDT"
        )

        # === Step 2: Estimate Entry Price (for size calculation) ===
        # Use shallow OB fetch for a quick estimate, fallback to ticker
        logger.debug(f"{log_prefix}: Estimating entry price...")
        ob_data = analyze_order_book(
            exchange,
            symbol,
            CONFIG.shallow_ob_fetch_depth,
            CONFIG.shallow_ob_fetch_depth,
        )
        best_ask = ob_data.get("best_ask")
        best_bid = ob_data.get("best_bid")
        if side == CONFIG.SIDE_BUY and best_ask:
            entry_price_estimate = best_ask
        elif side == CONFIG.SIDE_SELL and best_bid:
            entry_price_estimate = best_bid
        else:
            try:
                ticker = exchange.fetch_ticker(symbol)
                entry_price_estimate = safe_decimal_conversion(ticker.get("last"))
                if not entry_price_estimate or entry_price_estimate <= 0:
                    raise ValueError("Invalid last price from ticker")
                logger.debug(
                    f"{log_prefix}: Used last ticker price for estimate: {entry_price_estimate:.4f}"
                )
            except (
                ccxt.NetworkError,
                ccxt.ExchangeError,
                ValueError,
                KeyError,
                Exception,
            ) as e:
                logger.error(
                    f"{Fore.RED}{log_prefix}: Failed to fetch valid ticker price for estimate: {e}{Style.RESET_ALL}"
                )
                return None
        logger.info(f"{log_prefix}: Estimated Entry Price ~ {entry_price_estimate:.4f}")

        # === Step 3: Calculate Initial Stop Loss Price (Estimate) ===
        sl_distance = current_atr * sl_atr_multiplier
        if side == CONFIG.SIDE_BUY:
            initial_sl_price_raw = entry_price_estimate - sl_distance
        else:  # side == CONFIG.SIDE_SELL
            initial_sl_price_raw = entry_price_estimate + sl_distance

        # Ensure SL is not below minimum price tick (or zero)
        if min_price > 0 and initial_sl_price_raw < min_price:
            logger.warning(
                f"{Fore.YELLOW}{log_prefix}: Raw SL price {initial_sl_price_raw:.4f} below min price {min_price:.4f}. Adjusting SL to min price.{Style.RESET_ALL}"
            )
            initial_sl_price_raw = min_price
        elif initial_sl_price_raw <= 0:
            logger.error(
                f"{Fore.RED}{log_prefix}: Calculated initial SL price is zero or negative ({initial_sl_price_raw:.4f}). Cannot proceed.{Style.RESET_ALL}"
            )
            return None

        # Format estimated SL price
        initial_sl_price_estimate_str = format_price(
            exchange, symbol, initial_sl_price_raw
        )
        initial_sl_price_estimate = safe_decimal_conversion(
            initial_sl_price_estimate_str
        )
        logger.info(
            f"{log_prefix}: Calculated Initial SL Price (Estimate) ~ {initial_sl_price_estimate:.4f} (Dist: {sl_distance:.4f})"
        )

        # === Step 4: Calculate Position Size based on Risk ===
        logger.debug(f"{log_prefix}: Calculating position size based on risk...")
        calc_qty, req_margin_estimate = calculate_position_size(
            usdt_equity,
            risk_percentage,
            entry_price_estimate,
            initial_sl_price_estimate,
            leverage,
            symbol,
            exchange,
        )
        if calc_qty is None or req_margin_estimate is None:
            logger.error(
                f"{Fore.RED}{log_prefix}: Failed risk calculation. Cannot determine position size.{Style.RESET_ALL}"
            )
            return None
        final_quantity = calc_qty  # Start with risk-based quantity

        # === Step 5: Apply Max Order Value Cap ===
        pos_value_estimate = final_quantity * entry_price_estimate
        if pos_value_estimate > max_order_cap_usdt:
            logger.warning(
                f"{Fore.YELLOW}{log_prefix}: Estimated position value {pos_value_estimate:.4f} USDT exceeds cap {max_order_cap_usdt:.4f} USDT. Capping quantity.{Style.RESET_ALL}"
            )
            capped_quantity_raw = max_order_cap_usdt / entry_price_estimate
            # Format the capped quantity according to market precision
            capped_quantity_str = format_amount(exchange, symbol, capped_quantity_raw)
            final_quantity = safe_decimal_conversion(capped_quantity_str)
            # Recalculate estimated margin based on capped quantity
            req_margin_estimate = (final_quantity * entry_price_estimate) / Decimal(
                leverage
            )
            logger.info(
                f"{log_prefix}: Quantity capped to {final_quantity:.8f}, New Est. Margin ~{req_margin_estimate:.4f} USDT"
            )

        # === Step 6: Check Limits & Final Margin Check ===
        if final_quantity <= CONFIG.POSITION_QTY_EPSILON:
            logger.error(
                f"{Fore.RED}{log_prefix}: Final quantity ({final_quantity:.8f}) is negligible or zero after calculations/caps. Aborting.{Style.RESET_ALL}"
            )
            return None
        if min_qty > 0 and final_quantity < min_qty:
            logger.error(
                f"{Fore.RED}{log_prefix}: Final quantity {final_quantity:.8f} is below market minimum {min_qty:.8f}. Cannot place order.{Style.RESET_ALL}"
            )
            # Consider adjusting risk % or raising an alert if this happens often
            return None
        if max_qty is not None and final_quantity > max_qty:
            logger.warning(
                f"{Fore.YELLOW}{log_prefix}: Final quantity {final_quantity:.8f} exceeds market maximum {max_qty:.8f}. Capping to max.{Style.RESET_ALL}"
            )
            final_quantity = max_qty
            # Re-format capped amount (important if max_qty wasn't already precise)
            final_quantity = safe_decimal_conversion(
                format_amount(exchange, symbol, final_quantity)
            )
            # Recalculate estimated margin based on max quantity
            req_margin_estimate = (final_quantity * entry_price_estimate) / Decimal(
                leverage
            )
            logger.info(
                f"{log_prefix}: Quantity capped to {final_quantity:.8f}, New Est. Margin ~{req_margin_estimate:.4f} USDT"
            )

        # Final margin check with buffer
        final_req_margin_buffered = req_margin_estimate * margin_check_buffer
        if usdt_free < final_req_margin_buffered:
            logger.error(
                f"{Fore.RED}{log_prefix}: Insufficient FREE margin. Need ~{final_req_margin_buffered:.4f} USDT (incl. buffer), Have {usdt_free:.4f} USDT.{Style.RESET_ALL}"
            )
            send_sms_alert(
                f"[{market_base}] ORDER FAIL ({side.upper()}): Insufficient Free Margin (Need ~{final_req_margin_buffered:.2f}, Have {usdt_free:.2f})"
            )
            return None
        logger.info(
            f"{Fore.GREEN}{log_prefix}: Final Order Quantity={final_quantity:.8f}, Est. Value={final_quantity * entry_price_estimate:.4f}, Est. Margin={req_margin_estimate:.4f}. Margin check OK.{Style.RESET_ALL}"
        )

        # === Step 7: Place Entry Market Order ===
        entry_order_id: str | None = None
        try:
            qty_float = float(final_quantity)  # CCXT create order often expects float
            logger.warning(
                f"{Back.GREEN}{Fore.BLACK}{Style.BRIGHT}*** {log_prefix}: Placing MARKET ENTRY: {qty_float:.8f} {symbol} ***{Style.RESET_ALL}"
            )
            # Use reduce_only=False explicitly for entry orders
            entry_order = exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=qty_float,
                params={"reduce_only": False},
            )
            entry_order_id = entry_order.get("id")
            if not entry_order_id:
                logger.error(
                    f"{Fore.RED}{log_prefix}: Entry order placed but no ID was returned! Response: {entry_order}{Style.RESET_ALL}"
                )
                # Attempt cleanup if possible, but state is uncertain
                return None
            logger.success(
                f"{Fore.GREEN}{log_prefix}: Market Entry Order submitted. ID: ...{format_order_id(entry_order_id)}. Waiting for fill confirmation...{Style.RESET_ALL}"
            )
        except (
            ccxt.InsufficientFunds,
            ccxt.ExchangeError,
            ccxt.NetworkError,
            ValueError,
            Exception,
        ) as e:
            logger.error(
                f"{Fore.RED}{Style.BRIGHT}{log_prefix}: FAILED TO PLACE ENTRY ORDER: {e}{Style.RESET_ALL}"
            )
            logger.debug(traceback.format_exc())
            send_sms_alert(
                f"[{market_base}] ORDER FAIL ({side.upper()}): Entry placement failed: {type(e).__name__}"
            )
            return None  # Stop process if entry order fails

        # === Step 8: Wait for Entry Order Fill ===
        filled_entry_order = wait_for_order_fill(
            exchange, entry_order_id, symbol, CONFIG.order_fill_timeout_seconds
        )
        if not filled_entry_order:
            logger.error(
                f"{Fore.RED}{log_prefix}: Entry order ...{format_order_id(entry_order_id)} did not fill or failed.{Style.RESET_ALL}"
            )
            send_sms_alert(
                f"[{market_base}] ORDER FAIL ({side.upper()}): Entry ...{format_order_id(entry_order_id)} fill timeout/fail."
            )
            # Try to cancel the potentially stuck order (best effort)
            try:
                logger.warning(
                    f"{log_prefix}: Attempting to cancel unfilled/failed entry order ...{format_order_id(entry_order_id)}."
                )
                exchange.cancel_order(entry_order_id, symbol)
            except Exception as cancel_err:
                logger.warning(
                    f"{log_prefix}: Failed to cancel stuck entry order: {cancel_err}"
                )
            return None  # Stop process if entry doesn't fill

        # === Step 9: Extract Actual Fill Details ===
        # CRITICAL: Use details from the *actual filled order*, not estimates
        avg_fill_price = safe_decimal_conversion(filled_entry_order.get("average"))
        filled_qty = safe_decimal_conversion(filled_entry_order.get("filled"))
        cost = safe_decimal_conversion(filled_entry_order.get("cost"))

        # Validate fill details
        if avg_fill_price <= 0 or filled_qty <= CONFIG.POSITION_QTY_EPSILON:
            logger.error(
                f"{Fore.RED}{log_prefix}: Invalid fill details for entry ...{format_order_id(entry_order_id)}: Price={avg_fill_price}, Qty={filled_qty}. Position state uncertain!{Style.RESET_ALL}"
            )
            send_sms_alert(
                f"[{market_base}] ORDER FAIL ({side.upper()}): Invalid fill details for entry ...{format_order_id(entry_order_id)}."
            )
            # Return the problematic order details, but signal that subsequent steps failed
            return filled_entry_order  # Indicate entry happened but subsequent steps might fail

        logger.success(
            f"{Back.GREEN}{Fore.BLACK}{Style.BRIGHT}{log_prefix}: ENTRY CONFIRMED FILLED: ...{format_order_id(entry_order_id)}. FilledQty: {filled_qty:.8f} @ AvgPrice: {avg_fill_price:.4f}, Cost: {cost:.4f} USDT{Style.RESET_ALL}"
        )

        # --- Post-Entry: Place SL and TSL ---
        sl_order_id_short = "N/A"
        tsl_order_id_short = "N/A"
        actual_sl_price_str = "N/A"
        tsl_act_price_str = "N/A"

        # === Step 10: Calculate ACTUAL Stop Loss Price based on Actual Fill ===
        if side == CONFIG.SIDE_BUY:
            actual_sl_price_raw = avg_fill_price - sl_distance
        else:  # side == CONFIG.SIDE_SELL
            actual_sl_price_raw = avg_fill_price + sl_distance

        # Ensure SL is valid after using actual fill price
        if min_price > 0 and actual_sl_price_raw < min_price:
            logger.warning(
                f"{Fore.YELLOW}{log_prefix}: Actual SL price {actual_sl_price_raw:.4f} below min price {min_price:.4f}. Adjusting SL to min price.{Style.RESET_ALL}"
            )
            actual_sl_price_raw = min_price
        elif actual_sl_price_raw <= 0:
            logger.error(
                f"{Fore.RED}{Style.BRIGHT}{log_prefix}: Invalid ACTUAL SL price calculated ({actual_sl_price_raw:.4f}) based on fill price {avg_fill_price:.4f}. Cannot place SL!{Style.RESET_ALL}"
            )
            # CRITICAL SITUATION: Position is open without a calculated SL. Attempt emergency close.
            send_sms_alert(
                f"[{market_base}] CRITICAL ({side.upper()}): Invalid ACTUAL SL price ({actual_sl_price_raw:.4f})! Attempting emergency close."
            )
            # Determine position side based on entry order side
            position_side = (
                CONFIG.POS_LONG if side == CONFIG.SIDE_BUY else CONFIG.POS_SHORT
            )
            close_position(
                exchange,
                symbol,
                {"side": position_side, "qty": filled_qty},
                reason="Invalid SL Calc Post-Entry",
            )
            return filled_entry_order  # Return filled entry, but indicate failure state

        # Format the valid actual SL price
        actual_sl_price_str = format_price(exchange, symbol, actual_sl_price_raw)
        actual_sl_price_float = float(actual_sl_price_str)  # For CCXT param

        # === Step 11: Place Initial Fixed Stop Loss ===
        try:
            sl_side = CONFIG.SIDE_SELL if side == CONFIG.SIDE_BUY else CONFIG.SIDE_BUY
            # Use the actual filled quantity for the SL order
            sl_qty_str = format_amount(exchange, symbol, filled_qty)
            sl_qty_float = float(sl_qty_str)

            logger.info(
                f"{Fore.CYAN}{log_prefix}: Placing Initial Fixed SL ({sl_atr_multiplier}*ATR)... Side: {sl_side.upper()}, Qty: {sl_qty_float:.8f}, StopPx: {actual_sl_price_str}{Style.RESET_ALL}"
            )
            # Bybit V5 stop order params: 'stopPrice' (trigger price), 'reduceOnly': True
            sl_params = {"stopPrice": actual_sl_price_float, "reduceOnly": True}
            # Use 'stopMarket' type for market stop loss order
            sl_order = exchange.create_order(
                symbol, "stopMarket", sl_side, sl_qty_float, params=sl_params
            )
            sl_order_id = sl_order.get("id")
            sl_order_id_short = format_order_id(sl_order_id)
            logger.success(
                f"{Fore.GREEN}{log_prefix}: Initial Fixed SL order placed. ID: ...{sl_order_id_short}, Trigger: {actual_sl_price_str}{Style.RESET_ALL}"
            )
        except (
            ccxt.InsufficientFunds,
            ccxt.ExchangeError,
            ccxt.NetworkError,
            ValueError,
            Exception,
        ) as e:
            logger.error(
                f"{Fore.RED}{Style.BRIGHT}{log_prefix}: FAILED to place Initial Fixed SL order: {e}{Style.RESET_ALL}"
            )
            logger.debug(traceback.format_exc())
            send_sms_alert(
                f"[{market_base}] ERROR ({side.upper()}): Failed initial SL placement ({type(e).__name__}). Pos unprotected by fixed SL!"
            )
            # Don't necessarily close here, TSL might still work, or manual intervention needed.

        # === Step 12: Place Trailing Stop Loss ===
        try:
            # Calculate TSL activation price based on actual fill price
            act_offset = avg_fill_price * tsl_activation_offset_percent
            if side == CONFIG.SIDE_BUY:
                act_price_raw = avg_fill_price + act_offset
            else:  # side == CONFIG.SIDE_SELL
                act_price_raw = avg_fill_price - act_offset

            # Ensure activation price is valid
            if min_price > 0 and act_price_raw < min_price:
                act_price_raw = min_price
            if act_price_raw <= 0:
                raise ValueError(
                    f"Invalid TSL activation price calculated: {act_price_raw:.4f}"
                )

            tsl_act_price_str = format_price(exchange, symbol, act_price_raw)
            tsl_act_price_float = float(tsl_act_price_str)
            tsl_side = CONFIG.SIDE_SELL if side == CONFIG.SIDE_BUY else CONFIG.SIDE_BUY
            # Bybit V5 uses 'trailingStop' for percentage distance (e.g., "0.5" for 0.5%)
            # Convert decimal percentage (0.005) to string percentage ("0.5")
            tsl_trail_value_str = str(
                (tsl_percent * Decimal("100")).quantize(Decimal("0.01"))
            )  # Adjust precision as needed by Bybit
            # Use the actual filled quantity for the TSL order
            tsl_qty_str = format_amount(exchange, symbol, filled_qty)
            tsl_qty_float = float(tsl_qty_str)

            logger.info(
                f"{Fore.CYAN}{log_prefix}: Placing Trailing SL ({tsl_percent:.2%})... Side: {tsl_side.upper()}, Qty: {tsl_qty_float:.8f}, TrailValue: {tsl_trail_value_str}%, ActPx: {tsl_act_price_str}{Style.RESET_ALL}"
            )

            # Bybit V5 TSL parameters via CCXT:
            # 'trailingStop': The trailing percentage/distance as a string (check Bybit docs for exact format).
            # 'activePrice': The price at which the trailing stop activates.
            # 'reduceOnly': True
            tsl_params = {
                "trailingStop": tsl_trail_value_str,  # String percentage for Bybit V5
                "activePrice": tsl_act_price_float,
                "reduceOnly": True,
            }
            # Use 'stopMarket' type with TSL params for Bybit V5 via CCXT (check CCXT Bybit overrides if needed)
            tsl_order = exchange.create_order(
                symbol, "stopMarket", tsl_side, tsl_qty_float, params=tsl_params
            )
            tsl_order_id = tsl_order.get("id")
            tsl_order_id_short = format_order_id(tsl_order_id)
            logger.success(
                f"{Fore.GREEN}{log_prefix}: Trailing SL order placed. ID: ...{tsl_order_id_short}, Trail: {tsl_trail_value_str}%, ActPx: {tsl_act_price_str}{Style.RESET_ALL}"
            )

            # Final comprehensive SMS Alert after successful entry and SL/TSL placement attempts
            sms_msg = (
                f"[{market_base}] ENTERED {side.upper()} {filled_qty:.8f} @ {avg_fill_price:.4f}. "
                f"Init SL ~{actual_sl_price_str} (ID:...{sl_order_id_short}). "
                f"TSL {tsl_percent:.2%} act@{tsl_act_price_str} (ID:...{tsl_order_id_short}). "
                f"EntryID:...{format_order_id(entry_order_id)}"
            )
            send_sms_alert(sms_msg)

        except (
            ccxt.InsufficientFunds,
            ccxt.ExchangeError,
            ccxt.NetworkError,
            ValueError,
            Exception,
        ) as e:
            logger.error(
                f"{Fore.RED}{Style.BRIGHT}{log_prefix}: FAILED to place Trailing SL order: {e}{Style.RESET_ALL}"
            )
            logger.debug(traceback.format_exc())
            send_sms_alert(
                f"[{market_base}] ERROR ({side.upper()}): Failed TSL placement ({type(e).__name__}). Pos may lack TSL protection."
            )
            # If TSL fails but initial SL was placed, the position is still protected initially.

        return filled_entry_order  # Return filled entry order details regardless of SL/TSL placement success/failure

    except (
        ccxt.InsufficientFunds,
        ccxt.NetworkError,
        ccxt.ExchangeError,
        ValueError,
        Exception,
    ) as e:
        # Catch errors occurring before entry order placement or during initial setup
        logger.error(
            f"{Fore.RED}{Style.BRIGHT}{log_prefix}: Overall process failed before/during entry: {type(e).__name__} - {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        send_sms_alert(
            f"[{market_base}] ORDER FAIL ({side.upper()}): Pre-entry/Setup failed: {type(e).__name__}"
        )
        return None  # Indicate failure


def cancel_open_orders(
    exchange: ccxt.Exchange, symbol: str, reason: str = "Cleanup"
) -> None:
    """Attempts to cancel all open orders for the specified symbol on the exchange.

    Args:
        exchange: The CCXT exchange instance.
        symbol: The market symbol for which to cancel orders.
        reason: A string indicating why orders are being cancelled (for logging).
    """
    logger.info(
        f"{Fore.CYAN}Order Cancel: Attempting for {symbol} (Reason: {reason})...{Style.RESET_ALL}"
    )
    try:
        if not exchange.has.get("fetchOpenOrders"):
            logger.warning(
                f"{Fore.YELLOW}Order Cancel: fetchOpenOrders not supported by {exchange.id}. Cannot cancel automatically.{Style.RESET_ALL}"
            )
            return

        # Fetch only open orders for the specific symbol
        open_orders = exchange.fetch_open_orders(symbol)

        if not open_orders:
            logger.info(
                f"{Fore.CYAN}Order Cancel: No open orders found for {symbol}.{Style.RESET_ALL}"
            )
            return

        logger.warning(
            f"{Fore.YELLOW}Order Cancel: Found {len(open_orders)} open order(s) for {symbol}. Cancelling (Reason: {reason})...{Style.RESET_ALL}"
        )
        cancelled_count = 0
        failed_count = 0
        for order in open_orders:
            order_id = order.get("id")
            order_info_str = f"ID:...{format_order_id(order_id)} ({order.get('type')} {order.get('side')} Qty:{order.get('amount')} Px:{order.get('price') or order.get('stopPrice')})"
            if order_id:
                try:
                    logger.debug(
                        f"Order Cancel: Attempting to cancel order {order_info_str}"
                    )
                    exchange.cancel_order(order_id, symbol)
                    logger.info(
                        f"{Fore.CYAN}Order Cancel: Successfully cancelled order {order_info_str}{Style.RESET_ALL}"
                    )
                    cancelled_count += 1
                    time.sleep(
                        0.1
                    )  # Small delay between cancel calls to avoid rate limits
                except ccxt.OrderNotFound:
                    # If the order is not found, it might have been filled or cancelled already.
                    logger.warning(
                        f"{Fore.YELLOW}Order Cancel: Order not found (already closed/cancelled?): {order_info_str}{Style.RESET_ALL}"
                    )
                    cancelled_count += (
                        1  # Count it as effectively cancelled if not found
                    )
                except (ccxt.NetworkError, ccxt.ExchangeError) as e:
                    logger.error(
                        f"{Fore.RED}Order Cancel: FAILED to cancel order {order_info_str}: {type(e).__name__} - {e}{Style.RESET_ALL}"
                    )
                    failed_count += 1
                except Exception as e:
                    logger.error(
                        f"{Fore.RED}Order Cancel: Unexpected error cancelling {order_info_str}: {e}{Style.RESET_ALL}"
                    )
                    logger.debug(traceback.format_exc())
                    failed_count += 1
            else:
                logger.warning(
                    f"{Fore.YELLOW}Order Cancel: Found an open order without an ID: {order}. Skipping cancellation.{Style.RESET_ALL}"
                )

        log_level = logging.INFO if failed_count == 0 else logging.WARNING
        logger.log(
            log_level,
            f"{Fore.CYAN}Order Cancel: Finished for {symbol}. Cancelled/Not Found: {cancelled_count}, Failed: {failed_count}.{Style.RESET_ALL}",
        )

        if failed_count > 0:
            market_base = symbol.split("/")[0] if "/" in symbol else symbol
            send_sms_alert(
                f"[{market_base}] WARNING: Failed to cancel {failed_count} open order(s) during {reason}. Manual check may be needed."
            )

    except (ccxt.NetworkError, ccxt.ExchangeError) as e:
        logger.error(
            f"{Fore.RED}Order Cancel: Failed to fetch open orders for {symbol}: {type(e).__name__} - {e}{Style.RESET_ALL}"
        )
    except Exception as e:
        logger.error(
            f"{Fore.RED}Order Cancel: Unexpected error during open order fetch/cancel process for {symbol}: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())


# --- Strategy Signal Generation ---
def generate_signals(df: pd.DataFrame, strategy_name: str) -> dict[str, Any]:
    """Generates entry and exit signals based on the selected strategy and calculated indicators in the DataFrame.

    Args:
        df: DataFrame containing OHLCV data and calculated indicator columns.
        strategy_name: The name of the strategy to use (from CONFIG.strategy_name).

    Returns:
        A dictionary containing boolean signals:
        - 'enter_long': True to enter a long position.
        - 'enter_short': True to enter a short position.
        - 'exit_long': True to exit an existing long position.
        - 'exit_short': True to exit an existing short position.
        - 'exit_reason': A string describing the reason for the exit signal.
    """
    signals = {
        "enter_long": False,
        "enter_short": False,
        "exit_long": False,
        "exit_short": False,
        "exit_reason": "Strategy Exit",
    }
    log_prefix = f"Signal Gen ({strategy_name})"

    # Need at least 2 rows for comparisons (current and previous candle)
    if df is None or len(df) < 2:
        logger.debug(
            f"{log_prefix}: Insufficient data length ({len(df) if df is not None else 0}) for signal generation."
        )
        return signals

    last = df.iloc[-1]  # Current (latest) candle data
    prev = df.iloc[-2]  # Previous candle data

    try:
        # --- Dual Supertrend Logic ---
        if strategy_name == "DUAL_SUPERTREND":
            # Entry: Primary ST flips long AND confirmation ST is also long (trend=True)
            if (
                pd.notna(last["st_long"])
                and last["st_long"]
                and pd.notna(last["confirm_trend"])
                and last["confirm_trend"]
            ):
                signals["enter_long"] = True
            # Entry: Primary ST flips short AND confirmation ST is also short (trend=False)
            if (
                pd.notna(last["st_short"])
                and last["st_short"]
                and pd.notna(last["confirm_trend"])
                and not last["confirm_trend"]
            ):
                signals["enter_short"] = True
            # Exit Long: Primary ST flips short
            if pd.notna(last["st_short"]) and last["st_short"]:
                signals["exit_long"] = True
                signals["exit_reason"] = "Primary ST Short Flip"
            # Exit Short: Primary ST flips long
            if pd.notna(last["st_long"]) and last["st_long"]:
                signals["exit_short"] = True
                signals["exit_reason"] = "Primary ST Long Flip"

        # --- StochRSI + Momentum Logic ---
        elif strategy_name == "STOCHRSI_MOMENTUM":
            k_now, d_now, mom_now = (
                last.get("stochrsi_k"),
                last.get("stochrsi_d"),
                last.get("momentum"),
            )
            k_prev, d_prev = prev.get("stochrsi_k"), prev.get("stochrsi_d")

            # Check if all required values are valid Decimals
            required_vals = [k_now, d_now, mom_now, k_prev, d_prev]
            if any(
                v is None or not isinstance(v, Decimal) or v.is_nan()
                for v in required_vals
            ):
                logger.debug(
                    f"{log_prefix}: Skipping due to missing/NaN StochRSI/Momentum values."
                )
                return signals

            # Entry Long: K crosses above D from below, K is below oversold, Momentum is positive
            if (
                k_prev <= d_prev
                and k_now > d_now
                and k_now < CONFIG.stochrsi_oversold
                and mom_now > CONFIG.POSITION_QTY_EPSILON
            ):
                signals["enter_long"] = True
            # Entry Short: K crosses below D from above, K is above overbought, Momentum is negative
            if (
                k_prev >= d_prev
                and k_now < d_now
                and k_now > CONFIG.stochrsi_overbought
                and mom_now < -CONFIG.POSITION_QTY_EPSILON
            ):
                signals["enter_short"] = True
            # Exit Long: K crosses below D
            if k_prev >= d_prev and k_now < d_now:
                signals["exit_long"] = True
                signals["exit_reason"] = "StochRSI K crossed below D"
            # Exit Short: K crosses above D
            if k_prev <= d_prev and k_now > d_now:
                signals["exit_short"] = True
                signals["exit_reason"] = "StochRSI K crossed above D"

        # --- Ehlers Fisher Logic ---
        elif strategy_name == "EHLERS_FISHER":
            fish_now, sig_now = last.get("ehlers_fisher"), last.get("ehlers_signal")
            fish_prev, sig_prev = prev.get("ehlers_fisher"), prev.get("ehlers_signal")

            required_vals = [fish_now, sig_now, fish_prev, sig_prev]
            if any(
                v is None or not isinstance(v, Decimal) or v.is_nan()
                for v in required_vals
            ):
                logger.debug(
                    f"{log_prefix}: Skipping due to missing/NaN Ehlers Fisher values."
                )
                return signals

            # Entry Long: Fisher crosses above Signal line
            if fish_prev <= sig_prev and fish_now > sig_now:
                signals["enter_long"] = True
            # Entry Short: Fisher crosses below Signal line
            if fish_prev >= sig_prev and fish_now < sig_now:
                signals["enter_short"] = True
            # Exit Long: Fisher crosses below Signal line
            if fish_prev >= sig_prev and fish_now < sig_now:
                signals["exit_long"] = True
                signals["exit_reason"] = "Ehlers Fisher crossed below Signal"
            # Exit Short: Fisher crosses above Signal line
            if fish_prev <= sig_prev and fish_now > sig_now:
                signals["exit_short"] = True
                signals["exit_reason"] = "Ehlers Fisher crossed above Signal"

        # --- Ehlers MA Cross Logic (Using EMA placeholder) ---
        elif strategy_name == "EHLERS_MA_CROSS":
            fast_ma_now, slow_ma_now = last.get("fast_ema"), last.get("slow_ema")
            fast_ma_prev, slow_ma_prev = prev.get("fast_ema"), prev.get("slow_ema")

            required_vals = [fast_ma_now, slow_ma_now, fast_ma_prev, slow_ma_prev]
            if any(
                v is None or not isinstance(v, Decimal) or v.is_nan()
                for v in required_vals
            ):
                logger.debug(
                    f"{log_prefix}: Skipping due to missing/NaN Ehlers MA (EMA placeholder) values."
                )
                return signals

            # Entry Long: Fast MA crosses above Slow MA
            if fast_ma_prev <= slow_ma_prev and fast_ma_now > slow_ma_now:
                signals["enter_long"] = True
            # Entry Short: Fast MA crosses below Slow MA
            if fast_ma_prev >= slow_ma_prev and fast_ma_now < slow_ma_now:
                signals["enter_short"] = True
            # Exit Long: Fast MA crosses below Slow MA
            if fast_ma_prev >= slow_ma_prev and fast_ma_now < slow_ma_now:
                signals["exit_long"] = True
                signals["exit_reason"] = "Fast MA crossed below Slow MA"
            # Exit Short: Fast MA crosses above Slow MA
            if fast_ma_prev <= slow_ma_prev and fast_ma_now > slow_ma_now:
                signals["exit_short"] = True
                signals["exit_reason"] = "Fast MA crossed above Slow MA"

        else:
            logger.warning(
                f"{log_prefix}: Unknown strategy name '{strategy_name}' provided."
            )

    except KeyError as e:
        logger.error(
            f"{Fore.RED}{log_prefix} Error: Missing expected indicator column in DataFrame: {e}. Ensure indicators are calculated correctly.{Style.RESET_ALL}"
        )
        # Reset signals to False if a required column is missing
        signals = {k: (v if k == "exit_reason" else False) for k, v in signals.items()}
    except Exception as e:
        logger.error(
            f"{Fore.RED}{log_prefix} Error: Unexpected exception during signal generation: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        signals = {k: (v if k == "exit_reason" else False) for k, v in signals.items()}

    return signals


# --- Trading Logic ---
def trade_logic(exchange: ccxt.Exchange, symbol: str, df: pd.DataFrame) -> None:
    """Executes the main trading logic for one cycle:
    1. Calculates all indicators.
    2. Checks current position and market state.
    3. Generates strategy signals.
    4. Executes exit or entry actions based on signals and confirmations.

    Args:
        exchange: The CCXT exchange instance.
        symbol: The market symbol.
        df: DataFrame containing the latest OHLCV data.
    """
    cycle_time_str = (
        df.index[-1].strftime("%Y-%m-%d %H:%M:%S %Z") if not df.empty else "N/A"
    )
    logger.info(
        f"{Fore.BLUE}{Style.BRIGHT}========== New Check Cycle ({CONFIG.strategy_name}): {symbol} | Candle: {cycle_time_str} =========={Style.RESET_ALL}"
    )

    # --- Determine Minimum Required Data Length ---
    # Find the longest lookback period required by any *potentially* used indicator based on config
    # Add a buffer for safety and potential multi-step calculations
    required_rows = (
        max(
            CONFIG.st_atr_length,
            CONFIG.confirm_st_atr_length,
            CONFIG.stochrsi_rsi_length
            + CONFIG.stochrsi_stoch_length
            + max(
                CONFIG.stochrsi_k_period, CONFIG.stochrsi_d_period
            ),  # StochRSI lookback estimate
            CONFIG.momentum_length,
            CONFIG.ehlers_fisher_length
            + CONFIG.ehlers_fisher_signal_length,  # Fisher lookback estimate
            CONFIG.ehlers_fast_period,
            CONFIG.ehlers_slow_period,
            CONFIG.atr_calculation_period,
            CONFIG.volume_ma_period,
        )
        + 10
    )  # General buffer

    if df is None or len(df) < required_rows:
        logger.warning(
            f"{Fore.YELLOW}Trade Logic: Insufficient data ({len(df) if df is not None else 0} rows, need ~{required_rows} for indicators). Skipping cycle.{Style.RESET_ALL}"
        )
        return

    try:
        # === Step 1: Calculate ALL Required Indicators ===
        # Calculate indicators needed for the selected strategy and potentially for confirmations/SL.
        # It's often simpler to calculate a common set and let the signal function use what it needs.
        logger.debug("Calculating indicators...")
        # Always calculate ATR/Volume for SL and potential confirmation
        vol_atr_data = analyze_volume_atr(
            df, CONFIG.atr_calculation_period, CONFIG.volume_ma_period
        )
        current_atr = vol_atr_data.get("atr")

        # Calculate strategy-specific indicators
        if CONFIG.strategy_name == "DUAL_SUPERTREND":
            df = calculate_supertrend(df, CONFIG.st_atr_length, CONFIG.st_multiplier)
            df = calculate_supertrend(
                df,
                CONFIG.confirm_st_atr_length,
                CONFIG.confirm_st_multiplier,
                prefix="confirm_",
            )
        elif CONFIG.strategy_name == "STOCHRSI_MOMENTUM":
            df = calculate_stochrsi_momentum(
                df,
                CONFIG.stochrsi_rsi_length,
                CONFIG.stochrsi_stoch_length,
                CONFIG.stochrsi_k_period,
                CONFIG.stochrsi_d_period,
                CONFIG.momentum_length,
            )
        elif CONFIG.strategy_name == "EHLERS_FISHER":
            df = calculate_ehlers_fisher(
                df, CONFIG.ehlers_fisher_length, CONFIG.ehlers_fisher_signal_length
            )
        elif CONFIG.strategy_name == "EHLERS_MA_CROSS":
            df = calculate_ehlers_ma(
                df, CONFIG.ehlers_fast_period, CONFIG.ehlers_slow_period
            )
        # Add other strategy indicator calculations here if needed

        # === Step 2: Validate Base Requirements for Trading ===
        last_candle = df.iloc[-1]
        current_price = safe_decimal_conversion(
            last_candle.get("close"), default=Decimal("NaN")
        )

        if current_price.is_nan() or current_price <= 0:
            logger.warning(
                f"{Fore.YELLOW}Trade Logic: Last candle close price is invalid ({current_price}). Skipping cycle.{Style.RESET_ALL}"
            )
            return

        # Check if ATR is valid for placing new orders (needed for SL calculation)
        can_place_new_order = (
            current_atr is not None
            and not current_atr.is_nan()
            and current_atr > Decimal("0")
        )
        if not can_place_new_order:
            logger.warning(
                f"{Fore.YELLOW}Trade Logic: Invalid ATR ({current_atr}). Cannot calculate SL, new order placement disabled this cycle.{Style.RESET_ALL}"
            )
            # Note: Exits might still be possible if triggered by strategy without needing ATR.

        # === Step 3: Get Current Position & Optional Order Book Data ===
        position = get_current_position(exchange, symbol)
        position_side = position["side"]
        position_qty = position["qty"]
        position_entry_price = position["entry_price"]

        ob_data: dict[str, Decimal | None] | None = None
        if (
            CONFIG.fetch_order_book_per_cycle or CONFIG.require_volume_spike_for_entry
        ):  # Fetch if needed for entry confirmation
            ob_data = analyze_order_book(
                exchange, symbol, CONFIG.order_book_depth, CONFIG.order_book_fetch_limit
            )

        # === Step 4: Log Current State ===
        vol_ratio = vol_atr_data.get("volume_ratio")
        vol_spike = (
            vol_ratio is not None
            and not vol_ratio.is_nan()
            and vol_ratio > CONFIG.volume_spike_threshold
        )
        bid_ask_ratio = ob_data.get("bid_ask_ratio") if ob_data else None
        spread = ob_data.get("spread") if ob_data else None

        atr_str = f"{current_atr:.5f}" if can_place_new_order else "N/A"
        logger.info(
            f"State | Price: {current_price:.4f}, ATR({CONFIG.atr_calculation_period}): {atr_str}"
        )
        vol_ratio_str = (
            f"{vol_ratio:.2f}"
            if vol_ratio is not None and not vol_ratio.is_nan()
            else "N/A"
        )
        logger.info(
            f"State | Volume: Ratio={vol_ratio_str}, Spike={vol_spike} (RequiredForEntry={CONFIG.require_volume_spike_for_entry})"
        )
        ob_ratio_str = (
            f"{bid_ask_ratio:.3f}"
            if bid_ask_ratio is not None and not bid_ask_ratio.is_nan()
            else "N/A"
        )
        spread_str = (
            f"{spread:.4f}" if spread is not None and not spread.is_nan() else "N/A"
        )
        logger.info(
            f"State | OrderBook: Ratio={ob_ratio_str}, Spread={spread_str} (Fetched={ob_data is not None})"
        )
        logger.info(
            f"State | Position: Side={position_side}, Qty={position_qty:.8f}, Entry={position_entry_price:.4f}"
        )

        # === Step 5: Generate Strategy Signals ===
        strategy_signals = generate_signals(df, CONFIG.strategy_name)
        logger.debug(f"Strategy Signals ({CONFIG.strategy_name}): {strategy_signals}")

        # === Step 6: Execute Exit Actions (If in Position) ===
        if position_side != CONFIG.POS_NONE:
            should_exit = False
            exit_reason = ""
            if (
                position_side == CONFIG.POS_LONG
                and strategy_signals["exit_long"]
                or position_side == CONFIG.POS_SHORT
                and strategy_signals["exit_short"]
            ):
                should_exit = True
                exit_reason = strategy_signals["exit_reason"]

            if should_exit:
                logger.warning(
                    f"{Back.YELLOW}{Fore.BLACK}*** TRADE EXIT SIGNAL: Closing {position_side} due to '{exit_reason}' ***{Style.RESET_ALL}"
                )
                # Cancel existing SL/TSL orders *before* attempting to close the position
                cancel_open_orders(
                    exchange, symbol, f"Cancel SL/TSL before {exit_reason} Exit"
                )
                time.sleep(0.5)  # Short delay to allow cancellations to process

                close_result = close_position(
                    exchange, symbol, position, reason=exit_reason
                )
                if close_result:
                    logger.info(
                        f"Pausing for {CONFIG.POST_CLOSE_DELAY_SECONDS}s after closing position..."
                    )
                    time.sleep(CONFIG.POST_CLOSE_DELAY_SECONDS)
                # Regardless of close success, exit the logic for this cycle after an exit signal
                return
            else:
                # No strategy exit signal, holding position
                logger.info(
                    f"Holding {position_side} position. No strategy exit signal. Waiting for SL/TSL or next signal."
                )
                return  # End cycle logic, wait for next candle or SL/TSL hit

        # === Step 7: Check & Execute Entry Actions (Only if Flat) ===
        if position_side == CONFIG.POS_NONE:
            if not can_place_new_order:
                logger.warning(
                    f"{Fore.YELLOW}Holding Cash. Cannot enter: Invalid ATR prevents SL calculation.{Style.RESET_ALL}"
                )
                return  # Cannot enter without valid ATR

            logger.debug("Holding Cash. Checking entry signals...")
            enter_long_signal = strategy_signals["enter_long"]
            enter_short_signal = strategy_signals["enter_short"]

            # --- Check Confirmation Conditions ---
            passes_volume_confirm = (
                not CONFIG.require_volume_spike_for_entry or vol_spike
            )
            vol_log = f"VolConfirm OK (Pass:{passes_volume_confirm}, Spike={vol_spike}, Req={CONFIG.require_volume_spike_for_entry})"

            # Fetch OB now if not fetched earlier and needed for confirmation
            if (enter_long_signal or enter_short_signal) and ob_data is None:
                logger.debug("Potential entry signal, fetching OB for confirmation...")
                ob_data = analyze_order_book(
                    exchange,
                    symbol,
                    CONFIG.order_book_depth,
                    CONFIG.order_book_fetch_limit,
                )
                bid_ask_ratio = (
                    ob_data.get("bid_ask_ratio") if ob_data else None
                )  # Update ratio

            ob_available = (
                ob_data is not None
                and bid_ask_ratio is not None
                and not bid_ask_ratio.is_nan()
            )
            passes_long_ob_confirm = not ob_available or (
                bid_ask_ratio >= CONFIG.order_book_ratio_threshold_long
            )
            passes_short_ob_confirm = not ob_available or (
                bid_ask_ratio <= CONFIG.order_book_ratio_threshold_short
            )
            # Note: If OB is unavailable, confirmation passes by default (can be configured otherwise if needed)
            ob_log = f"OBConfirm OK (L:{passes_long_ob_confirm},S:{passes_short_ob_confirm}, Ratio={ob_ratio_str}, Available={ob_available})"

            # --- Combine Strategy Signal with Confirmations ---
            final_enter_long = (
                enter_long_signal and passes_volume_confirm and passes_long_ob_confirm
            )
            final_enter_short = (
                enter_short_signal and passes_volume_confirm and passes_short_ob_confirm
            )
            logger.debug(
                f"Final Entry Check (Long): Strategy={enter_long_signal}, {vol_log}, {ob_log} => Enter={final_enter_long}"
            )
            logger.debug(
                f"Final Entry Check (Short): Strategy={enter_short_signal}, {vol_log}, {ob_log} => Enter={final_enter_short}"
            )

            # --- Execute Entry ---
            entry_side: str | None = None
            if final_enter_long:
                entry_side = CONFIG.SIDE_BUY
                logger.success(
                    f"{Back.GREEN}{Fore.BLACK}{Style.BRIGHT}*** TRADE SIGNAL: CONFIRMED LONG ENTRY ({CONFIG.strategy_name}) for {symbol} ***{Style.RESET_ALL}"
                )
            elif final_enter_short:
                entry_side = CONFIG.SIDE_SELL
                logger.success(
                    f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}*** TRADE SIGNAL: CONFIRMED SHORT ENTRY ({CONFIG.strategy_name}) for {symbol} ***{Style.RESET_ALL}"
                )

            if entry_side:
                # Cancel any lingering orders before entering (shouldn't be any if flat, but good practice)
                cancel_open_orders(
                    exchange, symbol, f"Before {entry_side.upper()} Entry"
                )
                time.sleep(0.5)

                place_result = place_risked_market_order(
                    exchange=exchange,
                    symbol=symbol,
                    side=entry_side,
                    risk_percentage=CONFIG.risk_per_trade_percentage,
                    current_atr=current_atr,  # Already validated that it's not None/zero
                    sl_atr_multiplier=CONFIG.atr_stop_loss_multiplier,
                    leverage=CONFIG.leverage,
                    max_order_cap_usdt=CONFIG.max_order_usdt_amount,
                    margin_check_buffer=CONFIG.required_margin_buffer,
                    tsl_percent=CONFIG.trailing_stop_percentage,
                    tsl_activation_offset_percent=CONFIG.trailing_stop_activation_offset_percent,
                )
                if place_result:
                    pass
                # End cycle after attempting entry
                return
            else:
                # No confirmed entry signal
                logger.info("Holding Cash. No confirmed entry signal this cycle.")

    except Exception as e:
        # Catch-all for unexpected errors within the main logic block
        logger.error(
            f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}CRITICAL UNEXPECTED ERROR in trade_logic cycle: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        market_base = symbol.split("/")[0] if "/" in symbol else symbol
        send_sms_alert(
            f"[{market_base}] CRITICAL ERROR in trade_logic: {type(e).__name__}. Check logs!"
        )
    finally:
        # Log end of cycle regardless of outcome
        logger.info(
            f"{Fore.BLUE}{Style.BRIGHT}========== Cycle Check End: {symbol} =========={Style.RESET_ALL}\n"
        )


# --- Graceful Shutdown ---
def graceful_shutdown(exchange: ccxt.Exchange | None, symbol: str | None) -> None:
    """Attempts to gracefully shut down the bot by cancelling open orders and closing any active position.

    Args:
        exchange: The CCXT exchange instance (can be None if init failed).
        symbol: The market symbol being traded (can be None if setup failed).
    """
    logger.warning(
        f"{Fore.YELLOW}{Style.BRIGHT}Shutdown requested. Initiating graceful exit sequence...{Style.RESET_ALL}"
    )
    market_base = symbol.split("/")[0] if symbol and "/" in symbol else "Bot"
    send_sms_alert(f"[{market_base}] Shutdown requested. Attempting cleanup...")

    if not exchange or not symbol:
        logger.warning(
            f"{Fore.YELLOW}Shutdown: Exchange instance or symbol is not available. Cannot perform cleanup.{Style.RESET_ALL}"
        )
        return

    try:
        # --- Step 1: Cancel All Open Orders FIRST ---
        # This prevents SL/TSL orders interfering with the manual close attempt.
        logger.info(
            f"{Fore.CYAN}Shutdown: Cancelling all open orders for {symbol}...{Style.RESET_ALL}"
        )
        cancel_open_orders(exchange, symbol, reason="Graceful Shutdown")
        time.sleep(
            CONFIG.RETRY_DELAY_SECONDS
        )  # Allow time for cancellations to be processed by the exchange

        # --- Step 2: Check and Close Active Position ---
        logger.info(
            f"{Fore.CYAN}Shutdown: Checking for active position for {symbol}...{Style.RESET_ALL}"
        )
        position = get_current_position(exchange, symbol)

        if (
            position["side"] != CONFIG.POS_NONE
            and position["qty"] > CONFIG.POSITION_QTY_EPSILON
        ):
            logger.warning(
                f"{Fore.YELLOW}Shutdown: Active {position['side']} position found (Qty: {position['qty']:.8f}). Attempting to close...{Style.RESET_ALL}"
            )
            close_result = close_position(exchange, symbol, position, reason="Shutdown")

            if close_result:
                logger.info(
                    f"{Fore.CYAN}Shutdown: Close order placed. Waiting {CONFIG.POST_CLOSE_DELAY_SECONDS * 2}s for confirmation...{Style.RESET_ALL}"
                )
                time.sleep(
                    CONFIG.POST_CLOSE_DELAY_SECONDS * 2
                )  # Wait a bit longer for final check
                # --- Final Confirmation Check ---
                final_pos = get_current_position(exchange, symbol)
                if (
                    final_pos["side"] == CONFIG.POS_NONE
                    or final_pos["qty"] <= CONFIG.POSITION_QTY_EPSILON
                ):
                    logger.success(
                        f"{Fore.GREEN}{Style.BRIGHT}Shutdown: Position successfully confirmed CLOSED.{Style.RESET_ALL}"
                    )
                    send_sms_alert(
                        f"[{market_base}] Position confirmed CLOSED on shutdown."
                    )
                else:
                    logger.error(
                        f"{Back.RED}{Fore.WHITE}Shutdown Error: FAILED TO CONFIRM position closure after waiting. Final state: {final_pos['side']} Qty={final_pos['qty']:.8f}{Style.RESET_ALL}"
                    )
                    send_sms_alert(
                        f"[{market_base}] ERROR: Failed confirm closure! Final: {final_pos['side']} Qty={final_pos['qty']:.8f}. MANUAL CHECK REQUIRED!"
                    )
            else:
                # Close order placement failed
                logger.error(
                    f"{Back.RED}{Fore.WHITE}Shutdown Error: Failed to place close order for active position. MANUAL INTERVENTION REQUIRED.{Style.RESET_ALL}"
                )
                send_sms_alert(
                    f"[{market_base}] ERROR: Failed PLACE close order on shutdown. MANUAL CHECK REQUIRED!"
                )
        else:
            # No active position found
            logger.info(
                f"{Fore.GREEN}Shutdown: No active position found for {symbol}. No close action needed.{Style.RESET_ALL}"
            )
            send_sms_alert(f"[{market_base}] No active position found on shutdown.")

    except Exception as e:
        logger.error(
            f"{Fore.RED}Shutdown Error: Unexpected error during cleanup sequence: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        send_sms_alert(
            f"[{market_base}] Error during shutdown cleanup sequence: {type(e).__name__}"
        )

    logger.info(
        f"{Fore.YELLOW}{Style.BRIGHT}--- Scalping Bot Shutdown Sequence Complete ---{Style.RESET_ALL}"
    )


# --- Main Execution ---
def main() -> None:
    """Main function to initialize the bot, set up the exchange and symbol,
    and run the main trading loop. Handles setup errors and graceful shutdown.
    """
    start_time = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    logger.info(
        f"{Back.BLUE}{Fore.WHITE}{Style.BRIGHT}--- Pyrmethus Bybit Scalping Spell v2.0.1 Initializing ({start_time}) ---{Style.RESET_ALL}"
    )
    logger.info(
        f"{Fore.CYAN}--- Strategy Enchantment: {CONFIG.strategy_name} ---{Style.RESET_ALL}"
    )
    logger.info(
        f"{Fore.GREEN}--- Warding Rune: Initial ATR({CONFIG.atr_calculation_period}) SL + Exchange TSL ({CONFIG.trailing_stop_percentage:.2%}) ---{Style.RESET_ALL}"
    )
    logger.warning(
        f"{Back.YELLOW}{Fore.BLACK}{Style.BRIGHT}--- !!! LIVE FUTURES SCALPING MODE - EXTREME RISK INVOLVED !!! ---{Style.RESET_ALL}"
    )

    exchange: ccxt.Exchange | None = None
    symbol: str | None = None
    market_base: str = "Bot"  # Default for early alerts
    run_bot: bool = True
    cycle_count: int = 0

    try:
        # === Initialize Exchange ===
        exchange = initialize_exchange()
        if not exchange:
            logger.critical("Exchange initialization failed. Exiting.")
            return  # Exit if exchange setup fails

        # === Setup Symbol and Leverage ===
        try:
            # Allow user input for symbol or use default from config
            sym_input = input(
                f"{Fore.YELLOW}Enter symbol {Style.DIM}(Default: [{CONFIG.symbol}]){Style.NORMAL}: {Style.RESET_ALL}"
            ).strip()
            symbol_to_use = sym_input or CONFIG.symbol

            # Validate symbol and get unified market info from CCXT
            logger.debug(f"Validating symbol: {symbol_to_use}")
            market = exchange.market(symbol_to_use)
            symbol = market["symbol"]  # Use the unified symbol (e.g., BTC/USDT:USDT)
            market_base = (
                symbol.split("/")[0] if "/" in symbol else symbol
            )  # For alerts

            # Ensure it's a contract market suitable for leverage/futures
            if not market.get("contract"):
                raise ValueError(f"Market '{symbol}' is not a contract/futures market.")
            logger.info(
                f"{Fore.GREEN}Using Symbol: {symbol} (Type: {market.get('type', 'N/A')}, ID: {market.get('id')}){Style.RESET_ALL}"
            )

            # Set leverage
            if not set_leverage(exchange, symbol, CONFIG.leverage):
                # set_leverage logs errors internally
                raise RuntimeError(
                    f"Failed to set leverage to {CONFIG.leverage}x for {symbol}."
                )

        except (ccxt.BadSymbol, KeyError, ValueError, RuntimeError) as e:
            logger.critical(f"Symbol/Leverage setup failed: {e}")
            send_sms_alert(
                f"[{market_base}] CRITICAL: Symbol/Leverage setup FAILED ({e}). Exiting."
            )
            return  # Exit if symbol/leverage setup fails
        except Exception as e:
            logger.critical(f"Unexpected error during symbol/leverage setup: {e}")
            logger.debug(traceback.format_exc())
            send_sms_alert(
                f"[{market_base}] CRITICAL: Unexpected setup error ({type(e).__name__}). Exiting."
            )
            return

        # === Log Configuration Summary ===
        logger.info(
            f"{Fore.MAGENTA}{Style.BRIGHT}{'--- Configuration Summary ---':^50}{Style.RESET_ALL}"
        )
        logger.info(
            f"{Fore.WHITE}Symbol: {symbol}, Interval: {CONFIG.interval}, Leverage: {CONFIG.leverage}x"
        )
        logger.info(f"{Fore.CYAN}Strategy: {CONFIG.strategy_name}")
        # Log relevant strategy parameters based on selection
        if CONFIG.strategy_name == "DUAL_SUPERTREND":
            logger.info(
                f"  Params: ST={CONFIG.st_atr_length}/{CONFIG.st_multiplier}, ConfirmST={CONFIG.confirm_st_atr_length}/{CONFIG.confirm_st_multiplier}"
            )
        elif CONFIG.strategy_name == "STOCHRSI_MOMENTUM":
            logger.info(
                f"  Params: StochRSI={CONFIG.stochrsi_rsi_length}/{CONFIG.stochrsi_stoch_length}/{CONFIG.stochrsi_k_period}/{CONFIG.stochrsi_d_period} (OB={CONFIG.stochrsi_overbought},OS={CONFIG.stochrsi_oversold}), Mom={CONFIG.momentum_length}"
            )
        elif CONFIG.strategy_name == "EHLERS_FISHER":
            logger.info(
                f"  Params: Fisher={CONFIG.ehlers_fisher_length}, Signal={CONFIG.ehlers_fisher_signal_length}"
            )
        elif CONFIG.strategy_name == "EHLERS_MA_CROSS":
            logger.info(
                f"  Params: FastMA={CONFIG.ehlers_fast_period}, SlowMA={CONFIG.ehlers_slow_period}"
            )
        logger.info(
            f"{Fore.GREEN}Risk: {CONFIG.risk_per_trade_percentage:.3%} per trade"
        )
        logger.info(
            f"{Fore.GREEN}Max Position Value (Cap): {CONFIG.max_order_usdt_amount:.2f} USDT"
        )
        logger.info(
            f"{Fore.GREEN}Initial SL: {CONFIG.atr_stop_loss_multiplier} * ATR({CONFIG.atr_calculation_period})"
        )
        logger.info(
            f"{Fore.GREEN}Trailing SL: {CONFIG.trailing_stop_percentage:.2%}, Activation Offset: {CONFIG.trailing_stop_activation_offset_percent:.2%}"
        )
        logger.info(
            f"{Fore.YELLOW}Volume Confirm: {CONFIG.require_volume_spike_for_entry} (MA={CONFIG.volume_ma_period}, Thr={CONFIG.volume_spike_threshold})"
        )
        logger.info(
            f"{Fore.YELLOW}OB Confirm (Per Cycle): {CONFIG.fetch_order_book_per_cycle} (Depth={CONFIG.order_book_depth}, L>={CONFIG.order_book_ratio_threshold_long}, S<={CONFIG.order_book_ratio_threshold_short})"
        )
        logger.info(
            f"{Fore.WHITE}Sleep: {CONFIG.sleep_seconds}s, Margin Buffer: {CONFIG.required_margin_buffer:.1%}, Fill Timeout: {CONFIG.order_fill_timeout_seconds}s"
        )
        logger.info(
            f"{Fore.MAGENTA}SMS Alerts: {CONFIG.enable_sms_alerts} (To: {'*****' + CONFIG.sms_recipient_number[-4:] if CONFIG.sms_recipient_number else 'N/A'})"
        )
        logger.info(f"{Fore.CYAN}Logging Level: {logging.getLevelName(logger.level)}")
        logger.info(
            f"{Fore.MAGENTA}{Style.BRIGHT}{'----------------------------':^50}{Style.RESET_ALL}"
        )

        send_sms_alert(
            f"[{market_base}] Bot configured ({CONFIG.strategy_name}, {symbol}, {CONFIG.interval}, {CONFIG.leverage}x). SL: ATR+TSL. Starting main loop."
        )

        # === Main Trading Loop ===
        while run_bot:
            cycle_start_time = time.monotonic()
            cycle_count += 1
            logger.debug(
                f"{Fore.CYAN}--- Cycle {cycle_count} Start ({time.strftime('%H:%M:%S')}) ---{Style.RESET_ALL}"
            )

            try:
                # Determine required data length dynamically based on config
                # Fetch enough data for the longest lookback + buffer
                data_limit = (
                    max(
                        150,  # Base minimum
                        CONFIG.st_atr_length * 2,
                        CONFIG.confirm_st_atr_length * 2,
                        CONFIG.stochrsi_rsi_length
                        + CONFIG.stochrsi_stoch_length
                        + max(CONFIG.stochrsi_k_period, CONFIG.stochrsi_d_period)
                        + 5,
                        CONFIG.momentum_length * 2,
                        CONFIG.ehlers_fisher_length * 2
                        + CONFIG.ehlers_fisher_signal_length,
                        CONFIG.ehlers_fast_period * 2,
                        CONFIG.ehlers_slow_period * 2,
                        CONFIG.atr_calculation_period * 2,
                        CONFIG.volume_ma_period * 2,
                    )
                    + CONFIG.API_FETCH_LIMIT_BUFFER
                )

                # Fetch market data for the current cycle
                df = get_market_data(
                    exchange, symbol, CONFIG.interval, limit=data_limit
                )

                if df is not None and not df.empty:
                    # Pass a copy of the DataFrame to trade_logic to avoid modifying the original df used elsewhere
                    trade_logic(exchange, symbol, df.copy())
                else:
                    logger.warning(
                        f"{Fore.YELLOW}No valid market data returned for {symbol}. Skipping trade logic this cycle.{Style.RESET_ALL}"
                    )
                    # Consider a longer sleep or different handling if data is consistently unavailable

            # --- Robust Error Handling within the Loop ---
            except ccxt.RateLimitExceeded as e:
                logger.warning(
                    f"{Back.YELLOW}{Fore.BLACK}Rate Limit Exceeded: {e}. Sleeping for {CONFIG.sleep_seconds * 5}s...{Style.RESET_ALL}"
                )
                send_sms_alert(
                    f"[{market_base}] WARNING: Rate limit hit! Sleeping longer."
                )
                time.sleep(CONFIG.sleep_seconds * 5)
            except ccxt.NetworkError as e:
                # Includes connection errors, timeouts, etc. Usually recoverable.
                logger.warning(
                    f"{Fore.YELLOW}Network error: {e}. Check connection. Retrying next cycle after sleep.{Style.RESET_ALL}"
                )
                # Standard sleep is usually sufficient here
                time.sleep(CONFIG.sleep_seconds)
            except ccxt.ExchangeNotAvailable as e:
                # Exchange maintenance or severe issues. Sleep longer.
                logger.error(
                    f"{Back.RED}{Fore.WHITE}Exchange Not Available: {e}. Sleeping for {CONFIG.sleep_seconds * 10}s...{Style.RESET_ALL}"
                )
                send_sms_alert(
                    f"[{market_base}] ERROR: Exchange unavailable! Sleeping much longer."
                )
                time.sleep(CONFIG.sleep_seconds * 10)
            except ccxt.AuthenticationError as e:
                # API keys likely invalid or expired. Critical - Stop the bot.
                logger.critical(
                    f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}Authentication Error: {e}. API keys may be invalid/revoked. Stopping bot NOW.{Style.RESET_ALL}"
                )
                send_sms_alert(
                    f"[{market_base}] CRITICAL: Authentication Error! Bot stopped."
                )
                run_bot = False  # Terminate the loop
            except ccxt.ExchangeError as e:
                # Catch other specific exchange errors not handled above.
                logger.error(
                    f"{Fore.RED}Unhandled Exchange Error: {e}{Style.RESET_ALL}"
                )
                logger.debug(traceback.format_exc())
                send_sms_alert(
                    f"[{market_base}] ERROR: Unhandled Exchange error: {type(e).__name__}. Check logs."
                )
                # Standard sleep before retrying
                time.sleep(CONFIG.sleep_seconds)
            except Exception as e:
                # Catch any other unexpected error. Critical - Stop the bot.
                logger.exception(
                    f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}!!! UNEXPECTED CRITICAL ERROR in main loop: {e} !!!{Style.RESET_ALL}"
                )
                send_sms_alert(
                    f"[{market_base}] CRITICAL UNEXPECTED ERROR: {type(e).__name__}! Stopping bot NOW."
                )
                run_bot = False  # Terminate the loop

            # --- Loop Delay ---
            if run_bot:
                elapsed = time.monotonic() - cycle_start_time
                sleep_duration = max(0, CONFIG.sleep_seconds - elapsed)
                logger.debug(
                    f"Cycle {cycle_count} completed in {elapsed:.2f}s. Sleeping for {sleep_duration:.2f}s."
                )
                if sleep_duration > 0:
                    time.sleep(sleep_duration)

    except KeyboardInterrupt:
        logger.warning(
            f"\n{Fore.YELLOW}{Style.BRIGHT}KeyboardInterrupt received. Stopping bot...{Style.RESET_ALL}"
        )
        run_bot = (
            False  # Ensure loop terminates if Ctrl+C is pressed during setup/sleep
        )
    finally:
        # --- Graceful Shutdown ---
        # This block executes whether the loop finished normally,
        # was interrupted, or exited due to a critical error.
        graceful_shutdown(exchange, symbol)
        final_alert_market = (
            market_base
            if market_base != "Bot"
            else (symbol.split("/")[0] if symbol and "/" in symbol else "Bot")
        )
        send_sms_alert(f"[{final_alert_market}] Bot process terminated.")
        logger.info(
            f"{Back.BLUE}{Fore.WHITE}{Style.BRIGHT}--- Pyrmethus Scalping Spell Deactivated ---{Style.RESET_ALL}"
        )


if __name__ == "__main__":
    main()

# !/usr/bin/env python
# -*- coding: utf-8 -*-

# ██████╗ ██╗   ██╗███████╗███╗   ███╗███████╗████████╗██╗   ██╗██╗   ██╗███████╗
# ██╔══██╗╚██╗ ██╔╝██╔════╝████╗ ████║██╔════╝╚══██╔══╝██║   ██║██║   ██║██╔════╝
# ██████╔╝ ╚████╔╝ ███████╗██╔████╔██║███████╗   ██║   ██║   ██║██║   ██║███████╗
# ██╔═══╝   ╚██╔╝  ╚════██║██║╚██╔╝██║╚════██║   ██║   ██║   ██║██║   ██║╚════██║
# ██║        ██║   ███████║██║ ╚═╝ ██║███████║   ██║   ╚██████╔╝╚██████╔╝███████║
# ╚═╝        ╚═╝   ╚══════╝╚═╝     ╚═╝╚══════╝   ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝
# Pyrmethus - Unified Scalping Spell v2.0.1 (Syntax Fix)
# Conjures high-frequency trades on Bybit Futures with enhanced precision and adaptable strategies.

"""
High-Frequency Trading Bot (Scalping) for Bybit USDT Futures
Version: 2.0.1 (Unified: Selectable Strategies + Precision + Native SL/TSL + Syntax Fix)

Features:
- Multiple strategies selectable via config: "DUAL_SUPERTREND", "STOCHRSI_MOMENTUM", "EHLERS_FISHER", "EHLERS_MA_CROSS".
- Enhanced Precision: Uses Decimal for critical financial calculations.
- Exchange-native Trailing Stop Loss (TSL) placed immediately after entry.
- Exchange-native fixed Stop Loss placed immediately after entry.
- ATR for volatility measurement and initial Stop-Loss calculation.
- Optional Volume spike and Order Book pressure confirmation.
- Risk-based position sizing with margin checks.
- Termux SMS alerts for critical events and trade actions.
- Robust error handling and logging with Neon color support.
- Graceful shutdown on KeyboardInterrupt with position/order closing attempt.
- Stricter position detection logic (Bybit V5 API).

Disclaimer:
- **EXTREME RISK**: Educational purposes ONLY. High-risk. Use at own absolute risk.
- **EXCHANGE-NATIVE SL/TSL DEPENDENCE**: Relies on exchange-native orders. Subject to exchange performance, slippage, API reliability.
- Parameter Sensitivity: Requires significant tuning and testing.
- API Rate Limits: Monitor usage.
- Slippage: Market orders are prone to slippage.
- Test Thoroughly: **DO NOT RUN LIVE WITHOUT EXTENSIVE TESTNET/DEMO TESTING.**
- Termux Dependency: Requires Termux:API.
- API Changes: Code targets Bybit V5 via CCXT, updates may be needed.
"""

# Standard Library Imports
import logging
import os
import sys
import traceback
from decimal import Decimal, getcontext
from typing import Any

# Third-party Libraries
try:
    import ccxt
    import pandas as pd
    import pandas_ta as ta  # type: ignore[import]
    from colorama import Back, Fore, Style
    from colorama import init as colorama_init
    from dotenv import load_dotenv
except ImportError as e:
    missing_pkg = e.name
    sys.exit(1)

# --- Initializations ---
colorama_init(autoreset=True)
load_dotenv()
getcontext().prec = 18  # Set Decimal precision (adjust as needed)


# --- Configuration Class ---
class Config:
    """Loads and validates configuration parameters from environment variables."""

    def __init__(self) -> None:
        logger.info(
            f"{Fore.MAGENTA}--- Summoning Configuration Runes ---{Style.RESET_ALL}"
        )
        # --- API Credentials ---
        self.api_key: str | None = self._get_env(
            "BYBIT_API_KEY", required=True, color=Fore.RED
        )
        self.api_secret: str | None = self._get_env(
            "BYBIT_API_SECRET", required=True, color=Fore.RED
        )

        # --- Trading Parameters ---
        self.symbol: str = self._get_env("SYMBOL", "BTC/USDT:USDT", color=Fore.YELLOW)
        self.interval: str = self._get_env("INTERVAL", "1m", color=Fore.YELLOW)
        self.leverage: int = self._get_env(
            "LEVERAGE", 10, cast_type=int, color=Fore.YELLOW
        )
        self.sleep_seconds: int = self._get_env(
            "SLEEP_SECONDS", 10, cast_type=int, color=Fore.YELLOW
        )

        # --- Strategy Selection ---
        self.strategy_name: str = self._get_env(
            "STRATEGY_NAME", "DUAL_SUPERTREND", color=Fore.CYAN
        ).upper()
        self.valid_strategies: list[str] = [
            "DUAL_SUPERTREND",
            "STOCHRSI_MOMENTUM",
            "EHLERS_FISHER",
            "EHLERS_MA_CROSS",
        ]
        if self.strategy_name not in self.valid_strategies:
            raise ValueError(
                f"Invalid STRATEGY_NAME '{self.strategy_name}'. Valid: {self.valid_strategies}"
            )

        # --- Risk Management ---
        self.risk_per_trade_percentage: Decimal = self._get_env(
            "RISK_PER_TRADE_PERCENTAGE", "0.005", cast_type=Decimal, color=Fore.GREEN
        )  # 0.5%
        self.atr_stop_loss_multiplier: Decimal = self._get_env(
            "ATR_STOP_LOSS_MULTIPLIER", "1.5", cast_type=Decimal, color=Fore.GREEN
        )
        self.max_order_usdt_amount: Decimal = self._get_env(
            "MAX_ORDER_USDT_AMOUNT", "500.0", cast_type=Decimal, color=Fore.GREEN
        )
        self.required_margin_buffer: Decimal = self._get_env(
            "REQUIRED_MARGIN_BUFFER", "1.05", cast_type=Decimal, color=Fore.GREEN
        )  # 5% buffer

        # --- Trailing Stop Loss (Exchange Native) ---
        self.trailing_stop_percentage: Decimal = self._get_env(
            "TRAILING_STOP_PERCENTAGE", "0.005", cast_type=Decimal, color=Fore.GREEN
        )  # 0.5% trail
        self.trailing_stop_activation_offset_percent: Decimal = self._get_env(
            "TRAILING_STOP_ACTIVATION_PRICE_OFFSET_PERCENT",
            "0.001",
            cast_type=Decimal,
            color=Fore.GREEN,
        )  # 0.1% offset

        # --- Dual Supertrend Parameters ---
        self.st_atr_length: int = self._get_env(
            "ST_ATR_LENGTH", 7, cast_type=int, color=Fore.CYAN
        )
        self.st_multiplier: Decimal = self._get_env(
            "ST_MULTIPLIER", "2.5", cast_type=Decimal, color=Fore.CYAN
        )
        self.confirm_st_atr_length: int = self._get_env(
            "CONFIRM_ST_ATR_LENGTH", 5, cast_type=int, color=Fore.CYAN
        )
        self.confirm_st_multiplier: Decimal = self._get_env(
            "CONFIRM_ST_MULTIPLIER", "2.0", cast_type=Decimal, color=Fore.CYAN
        )

        # --- StochRSI + Momentum Parameters ---
        self.stochrsi_rsi_length: int = self._get_env(
            "STOCHRSI_RSI_LENGTH", 14, cast_type=int, color=Fore.CYAN
        )
        self.stochrsi_stoch_length: int = self._get_env(
            "STOCHRSI_STOCH_LENGTH", 14, cast_type=int, color=Fore.CYAN
        )
        self.stochrsi_k_period: int = self._get_env(
            "STOCHRSI_K_PERIOD", 3, cast_type=int, color=Fore.CYAN
        )
        self.stochrsi_d_period: int = self._get_env(
            "STOCHRSI_D_PERIOD", 3, cast_type=int, color=Fore.CYAN
        )
        self.stochrsi_overbought: Decimal = self._get_env(
            "STOCHRSI_OVERBOUGHT", "80.0", cast_type=Decimal, color=Fore.CYAN
        )
        self.stochrsi_oversold: Decimal = self._get_env(
            "STOCHRSI_OVERSOLD", "20.0", cast_type=Decimal, color=Fore.CYAN
        )
        self.momentum_length: int = self._get_env(
            "MOMENTUM_LENGTH", 5, cast_type=int, color=Fore.CYAN
        )

        # --- Ehlers Fisher Transform Parameters ---
        self.ehlers_fisher_length: int = self._get_env(
            "EHLERS_FISHER_LENGTH", 10, cast_type=int, color=Fore.CYAN
        )
        self.ehlers_fisher_signal_length: int = self._get_env(
            "EHLERS_FISHER_SIGNAL_LENGTH", 1, cast_type=int, color=Fore.CYAN
        )  # Default to 1

        # --- Ehlers MA Cross Parameters ---
        self.ehlers_fast_period: int = self._get_env(
            "EHLERS_FAST_PERIOD", 10, cast_type=int, color=Fore.CYAN
        )
        self.ehlers_slow_period: int = self._get_env(
            "EHLERS_SLOW_PERIOD", 30, cast_type=int, color=Fore.CYAN
        )

        # --- Volume Analysis ---
        self.volume_ma_period: int = self._get_env(
            "VOLUME_MA_PERIOD", 20, cast_type=int, color=Fore.YELLOW
        )
        self.volume_spike_threshold: Decimal = self._get_env(
            "VOLUME_SPIKE_THRESHOLD", "1.5", cast_type=Decimal, color=Fore.YELLOW
        )
        self.require_volume_spike_for_entry: bool = self._get_env(
            "REQUIRE_VOLUME_SPIKE_FOR_ENTRY", "false", cast_type=bool, color=Fore.YELLOW
        )

        # --- Order Book Analysis ---
        self.order_book_depth: int = self._get_env(
            "ORDER_BOOK_DEPTH", 10, cast_type=int, color=Fore.YELLOW
        )
        self.order_book_ratio_threshold_long: Decimal = self._get_env(
            "ORDER_BOOK_RATIO_THRESHOLD_LONG",
            "1.2",
            cast_type=Decimal,
            color=Fore.YELLOW,
        )
        self.order_book_ratio_threshold_short: Decimal = self._get_env(
            "ORDER_BOOK_RATIO_THRESHOLD_SHORT",
            "0.8",
            cast_type=Decimal,
            color=Fore.YELLOW,
        )
        self.fetch_order_book_per_cycle: bool = self._get_env(
            "FETCH_ORDER_BOOK_PER_CYCLE", "false", cast_type=bool, color=Fore.YELLOW
        )

        # --- ATR Calculation (for Initial SL) ---
        self.atr_calculation_period: int = self._get_env(
            "ATR_CALCULATION_PERIOD", 14, cast_type=int, color=Fore.GREEN
        )

        # --- Termux SMS Alerts ---
        self.enable_sms_alerts: bool = self._get_env(
            "ENABLE_SMS_ALERTS", "false", cast_type=bool, color=Fore.MAGENTA
        )
        self.sms_recipient_number: str | None = self._get_env(
            "SMS_RECIPIENT_NUMBER", None, color=Fore.MAGENTA
        )
        self.sms_timeout_seconds: int = self._get_env(
            "SMS_TIMEOUT_SECONDS", 30, cast_type=int, color=Fore.MAGENTA
        )

        # --- CCXT / API Parameters ---
        self.default_recv_window: int = 10000
        self.order_book_fetch_limit: int = max(25, self.order_book_depth)
        self.shallow_ob_fetch_depth: int = 5
        self.order_fill_timeout_seconds: int = self._get_env(
            "ORDER_FILL_TIMEOUT_SECONDS", 15, cast_type=int, color=Fore.YELLOW
        )

        # --- Internal Constants ---
        self.side_buy: str = "buy"
        self.side_sell: str = "sell"
        self.pos_long: str = "Long"
        self.pos_short: str = "Short"
        self.pos_none: str = "None"
        self.usdt_symbol: str = "USDT"
        self.retry_count: int = 3
        self.retry_delay_seconds: int = 2
        self.api_fetch_limit_buffer: int = 10
        self.position_qty_epsilon: Decimal = Decimal("1e-9")
        self.post_close_delay_seconds: int = 3

        logger.info(
            f"{Fore.MAGENTA}--- Configuration Runes Summoned ---{Style.RESET_ALL}"
        )

    def _get_env(
        self,
        key: str,
        default: Any = None,
        cast_type: type = str,
        required: bool = False,
        color: str = Fore.WHITE,
    ) -> Any:
        """Fetches env var, casts type, logs, handles defaults/errors."""
        value = os.getenv(key)
        log_value = (
            f"'{value}'"
            if value is not None
            else f"Not Set (Using Default: '{default}')"
        )
        logger.debug(f"{color}Summoning {key}: {log_value}{Style.RESET_ALL}")

        if value is None:
            if required:
                raise ValueError(
                    f"CRITICAL: Required environment variable '{key}' not set."
                )
            value = default
        elif cast_type == bool:
            value = value.lower() in ["true", "1", "yes", "y"]
        elif cast_type == Decimal:
            try:
                value = Decimal(value)
            except InvalidOperation:
                logger.error(
                    f"{Fore.RED}Invalid Decimal value for {key}: '{value}'. Using default: '{default}'{Style.RESET_ALL}"
                )
                value = Decimal(str(default)) if default is not None else None
        elif cast_type is not None:
            try:
                value = cast_type(value)
            except (ValueError, TypeError):
                logger.error(
                    f"{Fore.RED}Invalid type for {key}: '{value}'. Expected {cast_type.__name__}. Using default: '{default}'{Style.RESET_ALL}"
                )
                value = default

        if value is None and required:  # Check again if default was None
            raise ValueError(
                f"CRITICAL: Required environment variable '{key}' has no value or default."
            )

        return value


# --- Logger Setup ---
LOGGING_LEVEL: int = (
    logging.DEBUG if os.getenv("DEBUG", "false").lower() == "true" else logging.INFO
)
logging.basicConfig(
    level=LOGGING_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger: logging.Logger = logging.getLogger(__name__)

# Custom SUCCESS level and Neon Color Formatting
SUCCESS_LEVEL: int = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


def log_success(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(
            SUCCESS_LEVEL, message, args, **kwargs
        )  # pylint: disable=protected-access


logging.Logger.success = log_success

if sys.stdout.isatty():
    logging.addLevelName(
        logging.DEBUG,
        f"{Fore.CYAN}{logging.getLevelName(logging.DEBUG)}{Style.RESET_ALL}",
    )
    logging.addLevelName(
        logging.INFO,
        f"{Fore.BLUE}{logging.getLevelName(logging.INFO)}{Style.RESET_ALL}",
    )
    logging.addLevelName(
        SUCCESS_LEVEL,
        f"{Fore.MAGENTA}{logging.getLevelName(SUCCESS_LEVEL)}{Style.RESET_ALL}",
    )
    logging.addLevelName(
        logging.WARNING,
        f"{Fore.YELLOW}{logging.getLevelName(logging.WARNING)}{Style.RESET_ALL}",
    )
    logging.addLevelName(
        logging.ERROR,
        f"{Fore.RED}{logging.getLevelName(logging.ERROR)}{Style.RESET_ALL}",
    )
    logging.addLevelName(
        logging.CRITICAL,
        f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}{logging.getLevelName(logging.CRITICAL)}{Style.RESET_ALL}",
    )

# --- Global Objects ---
try:
    CONFIG = Config()
except ValueError as e:
    logger.critical(
        f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}Configuration Error: {e}{Style.RESET_ALL}"
    )
    sys.exit(1)


# --- Helper Functions ---
def safe_decimal_conversion(value: Any, default: Decimal = Decimal("0.0")) -> Decimal:
    """Safely converts a value to Decimal, returning default if conversion fails."""
    try:
        return Decimal(str(value)) if value is not None else default
    except (InvalidOperation, TypeError, ValueError):
        logger.warning(
            f"Could not convert '{value}' to Decimal, using default {default}"
        )
        return default


def format_order_id(order_id: str | int | None) -> str:
    """Returns the last 6 characters of an order ID or 'N/A'."""
    return str(order_id)[-6:] if order_id else "N/A"


# --- Precision Formatting ---
def format_price(exchange: ccxt.Exchange, symbol: str, price: float | Decimal) -> str:
    """Formats price according to market precision rules."""
    try:
        # CCXT formatting methods often expect float input
        return exchange.price_to_precision(symbol, float(price))
    except Exception as e:
        logger.error(
            f"{Fore.RED}Error formatting price {price} for {symbol}: {e}{Style.RESET_ALL}"
        )
        return str(Decimal(str(price)).normalize())  # Fallback to Decimal string


def format_amount(exchange: ccxt.Exchange, symbol: str, amount: float | Decimal) -> str:
    """Formats amount according to market precision rules."""
    try:
        # CCXT formatting methods often expect float input
        return exchange.amount_to_precision(symbol, float(amount))
    except Exception as e:
        logger.error(
            f"{Fore.RED}Error formatting amount {amount} for {symbol}: {e}{Style.RESET_ALL}"
        )
        return str(Decimal(str(amount)).normalize())  # Fallback to Decimal string


# --- Termux SMS Alert Function ---
def send_sms_alert(message: str) -> bool:
    """Sends an SMS alert using Termux API."""
    if not CONFIG.enable_sms_alerts:
        logger.debug("SMS alerts disabled.")
        return False
    if not CONFIG.sms_recipient_number:
        logger.warning("SMS alerts enabled, but SMS_RECIPIENT_NUMBER not set.")
        return False
    try:
        # Use shlex.quote for message safety, though direct passing is usually fine
        # quoted_message = shlex.quote(message)
        command: list[str] = [
            "termux-sms-send",
            "-n",
            CONFIG.sms_recipient_number,
            message,
        ]
        logger.info(
            f"{Fore.MAGENTA}Attempting SMS to {CONFIG.sms_recipient_number} (Timeout: {CONFIG.sms_timeout_seconds}s)...{Style.RESET_ALL}"
        )
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=CONFIG.sms_timeout_seconds,
        )
        if result.returncode == 0:
            logger.success(
                f"{Fore.MAGENTA}SMS command executed successfully.{Style.RESET_ALL}"
            )
            return True
        else:
            logger.error(
                f"{Fore.RED}SMS command failed. RC: {result.returncode}, Stderr: {result.stderr.strip()}{Style.RESET_ALL}"
            )
            return False
    except FileNotFoundError:
        logger.error(
            f"{Fore.RED}SMS failed: 'termux-sms-send' not found. Install Termux:API.{Style.RESET_ALL}"
        )
        return False
    except subprocess.TimeoutExpired:
        logger.error(
            f"{Fore.RED}SMS failed: command timed out after {CONFIG.sms_timeout_seconds}s.{Style.RESET_ALL}"
        )
        return False
    except Exception as e:
        logger.error(f"{Fore.RED}SMS failed: Unexpected error: {e}{Style.RESET_ALL}")
        logger.debug(traceback.format_exc())
        return False


# --- Exchange Initialization ---
def initialize_exchange() -> ccxt.Exchange | None:
    """Initializes and returns the CCXT Bybit exchange instance."""
    logger.info(f"{Fore.BLUE}Initializing CCXT Bybit connection...{Style.RESET_ALL}")
    if not CONFIG.api_key or not CONFIG.api_secret:
        logger.critical("API keys missing in .env file.")
        send_sms_alert("[ScalpBot] CRITICAL: API keys missing. Bot stopped.")
        return None
    try:
        exchange = ccxt.bybit(
            {
                "apiKey": CONFIG.api_key,
                "secret": CONFIG.api_secret,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "linear",  # Assuming USDT perpetuals
                    "recvWindow": CONFIG.default_recv_window,
                    "adjustForTimeDifference": True,
                },
            }
        )
        logger.debug("Loading markets...")
        exchange.load_markets(True)  # Force reload
        logger.debug("Fetching initial balance...")
        exchange.fetch_balance()  # Initial check
        logger.success(
            f"{Fore.GREEN}{Style.BRIGHT}CCXT Bybit Session Initialized (LIVE SCALPING MODE - EXTREME CAUTION!).{Style.RESET_ALL}"
        )
        send_sms_alert("[ScalpBot] Initialized & authenticated successfully.")
        return exchange
    except ccxt.AuthenticationError as e:
        logger.critical(f"Authentication failed: {e}. Check keys/IP/permissions.")
        send_sms_alert(f"[ScalpBot] CRITICAL: Authentication FAILED: {e}. Bot stopped.")
    except ccxt.NetworkError as e:
        logger.critical(f"Network error on init: {e}. Check connection/Bybit status.")
        send_sms_alert(f"[ScalpBot] CRITICAL: Network Error on Init: {e}. Bot stopped.")
    except ccxt.ExchangeError as e:
        logger.critical(f"Exchange error on init: {e}. Check Bybit status/API docs.")
        send_sms_alert(
            f"[ScalpBot] CRITICAL: Exchange Error on Init: {e}. Bot stopped."
        )
    except Exception as e:
        logger.critical(f"Unexpected error during init: {e}")
        logger.debug(traceback.format_exc())
        send_sms_alert(
            f"[ScalpBot] CRITICAL: Unexpected Init Error: {type(e).__name__}. Bot stopped."
        )
    return None


# --- Indicator Calculation Functions ---
def calculate_supertrend(
    df: pd.DataFrame, length: int, multiplier: Decimal, prefix: str = ""
) -> pd.DataFrame:
    """Calculates the Supertrend indicator using pandas_ta, returns Decimal where applicable."""
    col_prefix = f"{prefix}" if prefix else ""
    target_cols = [
        f"{col_prefix}supertrend",
        f"{col_prefix}trend",
        f"{col_prefix}st_long",
        f"{col_prefix}st_short",
    ]
    st_col = f"SUPERT_{length}_{float(multiplier)}"  # pandas_ta uses float in name
    st_trend_col = f"SUPERTd_{length}_{float(multiplier)}"
    st_long_col = f"SUPERTl_{length}_{float(multiplier)}"
    st_short_col = f"SUPERTs_{length}_{float(multiplier)}"
    required_input_cols = ["high", "low", "close"]

    if (
        df is None
        or df.empty
        or not all(c in df.columns for c in required_input_cols)
        or len(df) < length + 1
    ):
        logger.warning(
            f"{Fore.YELLOW}Indicator Calc ({col_prefix}ST): Invalid input (Len: {len(df) if df is not None else 0}, Need: {length + 1}).{Style.RESET_ALL}"
        )
        for col in target_cols:
            df[col] = pd.NA
        return df

    try:
        # pandas_ta expects float multiplier
        df.ta.supertrend(length=length, multiplier=float(multiplier), append=True)
        if st_col not in df.columns or st_trend_col not in df.columns:
            raise KeyError(
                f"pandas_ta failed to create expected raw columns: {st_col}, {st_trend_col}"
            )

        # Convert Supertrend value to Decimal
        df[f"{col_prefix}supertrend"] = df[st_col].apply(safe_decimal_conversion)
        df[f"{col_prefix}trend"] = df[st_trend_col] == 1  # Boolean
        prev_trend = df[st_trend_col].shift(1)
        df[f"{col_prefix}st_long"] = (prev_trend == -1) & (
            df[st_trend_col] == 1
        )  # Boolean
        df[f"{col_prefix}st_short"] = (prev_trend == 1) & (
            df[st_trend_col] == -1
        )  # Boolean

        raw_st_cols = [st_col, st_trend_col, st_long_col, st_short_col]
        df.drop(columns=raw_st_cols, errors="ignore", inplace=True)

        last_st_val = df[f"{col_prefix}supertrend"].iloc[-1]
        if pd.notna(last_st_val):
            last_trend = "Up" if df[f"{col_prefix}trend"].iloc[-1] else "Down"
            signal = (
                "LONG"
                if df[f"{col_prefix}st_long"].iloc[-1]
                else ("SHORT" if df[f"{col_prefix}st_short"].iloc[-1] else "None")
            )
            logger.debug(
                f"Indicator Calc ({col_prefix}ST({length},{multiplier})): Trend={last_trend}, Val={last_st_val:.4f}, Signal={signal}"
            )
        else:
            logger.debug(
                f"Indicator Calc ({col_prefix}ST({length},{multiplier})): Resulted in NA for last candle."
            )

    except Exception as e:
        logger.error(
            f"{Fore.RED}Indicator Calc ({col_prefix}ST): Error: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        for col in target_cols:
            df[col] = pd.NA
    return df


def analyze_volume_atr(
    df: pd.DataFrame, atr_len: int, vol_ma_len: int
) -> dict[str, Decimal | None]:
    """Calculates ATR, Volume MA, checks spikes. Returns Decimals."""
    results: dict[str, Decimal | None] = {
        "atr": None,
        "volume_ma": None,
        "last_volume": None,
        "volume_ratio": None,
    }
    required_cols = ["high", "low", "close", "volume"]
    min_len = max(atr_len, vol_ma_len)

    if (
        df is None
        or df.empty
        or not all(c in df.columns for c in required_cols)
        or len(df) < min_len
    ):
        logger.warning(
            f"{Fore.YELLOW}Indicator Calc (Vol/ATR): Invalid input (Len: {len(df) if df is not None else 0}, Need: {min_len}).{Style.RESET_ALL}"
        )
        return results

    try:
        # Calculate ATR
        atr_col = f"ATRr_{atr_len}"
        df.ta.atr(length=atr_len, append=True)
        if atr_col in df.columns:
            last_atr = df[atr_col].iloc[-1]
            if pd.notna(last_atr):
                results["atr"] = safe_decimal_conversion(last_atr)
            df.drop(columns=[atr_col], errors="ignore", inplace=True)

        # Calculate Volume MA
        volume_ma_col = "volume_ma"
        df[volume_ma_col] = (
            df["volume"]
            .rolling(window=vol_ma_len, min_periods=max(1, vol_ma_len // 2))
            .mean()
        )
        last_vol_ma = df[volume_ma_col].iloc[-1]
        last_vol = df["volume"].iloc[-1]

        if pd.notna(last_vol_ma):
            results["volume_ma"] = safe_decimal_conversion(last_vol_ma)
        if pd.notna(last_vol):
            results["last_volume"] = safe_decimal_conversion(last_vol)

        if (
            results["volume_ma"] is not None
            and results["volume_ma"] > CONFIG.position_qty_epsilon
            and results["last_volume"] is not None
        ):
            try:
                results["volume_ratio"] = results["last_volume"] / results["volume_ma"]
            except Exception:  # Handles potential division by zero if MA is epsilon
                results["volume_ratio"] = None

        if volume_ma_col in df.columns:
            df.drop(columns=[volume_ma_col], errors="ignore", inplace=True)

        # Log results
        atr_str = f"{results['atr']:.5f}" if results["atr"] else "N/A"
        vol_ma_str = f"{results['volume_ma']:.2f}" if results["volume_ma"] else "N/A"
        vol_ratio_str = (
            f"{results['volume_ratio']:.2f}" if results["volume_ratio"] else "N/A"
        )
        logger.debug(
            f"Indicator Calc: ATR({atr_len})={atr_str}, VolMA({vol_ma_len})={vol_ma_str}, VolRatio={vol_ratio_str}"
        )

    except Exception as e:
        logger.error(f"{Fore.RED}Indicator Calc (Vol/ATR): Error: {e}{Style.RESET_ALL}")
        logger.debug(traceback.format_exc())
        results = dict.fromkeys(results)
    return results


def calculate_stochrsi_momentum(
    df: pd.DataFrame, rsi_len: int, stoch_len: int, k: int, d: int, mom_len: int
) -> pd.DataFrame:
    """Calculates StochRSI and Momentum, returns Decimals."""
    target_cols = ["stochrsi_k", "stochrsi_d", "momentum"]
    min_len = max(rsi_len + stoch_len, mom_len) + 5  # Add buffer
    if (
        df is None
        or df.empty
        or not all(c in df.columns for c in ["close"])
        or len(df) < min_len
    ):
        logger.warning(
            f"{Fore.YELLOW}Indicator Calc (StochRSI/Mom): Invalid input (Len: {len(df) if df is not None else 0}, Need ~{min_len}).{Style.RESET_ALL}"
        )
        for col in target_cols:
            df[col] = pd.NA
        return df
    try:
        # StochRSI
        stochrsi_df = df.ta.stochrsi(
            length=stoch_len, rsi_length=rsi_len, k=k, d=d, append=False
        )
        k_col, d_col = (
            f"STOCHRSIk_{stoch_len}_{rsi_len}_{k}_{d}",
            f"STOCHRSId_{stoch_len}_{rsi_len}_{k}_{d}",
        )
        if k_col in stochrsi_df.columns:
            df["stochrsi_k"] = stochrsi_df[k_col].apply(safe_decimal_conversion)
        else:
            logger.warning("StochRSI K column not found")
            df["stochrsi_k"] = pd.NA
        if d_col in stochrsi_df.columns:
            df["stochrsi_d"] = stochrsi_df[d_col].apply(safe_decimal_conversion)
        else:
            logger.warning("StochRSI D column not found")
            df["stochrsi_d"] = pd.NA

        # Momentum
        mom_col = f"MOM_{mom_len}"
        df.ta.mom(length=mom_len, append=True)
        if mom_col in df.columns:
            df["momentum"] = df[mom_col].apply(safe_decimal_conversion)
            df.drop(columns=[mom_col], errors="ignore", inplace=True)
        else:
            logger.warning("Momentum column not found")
            df["momentum"] = pd.NA

        k_val, d_val, mom_val = (
            df["stochrsi_k"].iloc[-1],
            df["stochrsi_d"].iloc[-1],
            df["momentum"].iloc[-1],
        )
        if pd.notna(k_val) and pd.notna(d_val) and pd.notna(mom_val):
            logger.debug(
                f"Indicator Calc (StochRSI/Mom): K={k_val:.2f}, D={d_val:.2f}, Mom={mom_val:.4f}"
            )
        else:
            logger.debug(
                "Indicator Calc (StochRSI/Mom): Resulted in NA for last candle."
            )

    except Exception as e:
        logger.error(
            f"{Fore.RED}Indicator Calc (StochRSI/Mom): Error: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        for col in target_cols:
            df[col] = pd.NA
    return df


def calculate_ehlers_fisher(df: pd.DataFrame, length: int, signal: int) -> pd.DataFrame:
    """Calculates Ehlers Fisher Transform, returns Decimals."""
    target_cols = ["ehlers_fisher", "ehlers_signal"]
    if (
        df is None
        or df.empty
        or not all(c in df.columns for c in ["high", "low"])
        or len(df) < length + 1
    ):
        logger.warning(
            f"{Fore.YELLOW}Indicator Calc (EhlersFisher): Invalid input (Len: {len(df) if df is not None else 0}, Need {length + 1}).{Style.RESET_ALL}"
        )
        for col in target_cols:
            df[col] = pd.NA
        return df
    try:
        fisher_df = df.ta.fisher(length=length, signal=signal, append=False)
        fish_col, signal_col = (
            f"FISHERT_{length}_{signal}",
            f"FISHERTs_{length}_{signal}",
        )
        if fish_col in fisher_df.columns:
            df["ehlers_fisher"] = fisher_df[fish_col].apply(safe_decimal_conversion)
        else:
            logger.warning("Ehlers Fisher column not found")
            df["ehlers_fisher"] = pd.NA
        if signal_col in fisher_df.columns:
            df["ehlers_signal"] = fisher_df[signal_col].apply(safe_decimal_conversion)
        else:
            logger.warning("Ehlers Signal column not found")
            df["ehlers_signal"] = pd.NA

        fish_val, sig_val = df["ehlers_fisher"].iloc[-1], df["ehlers_signal"].iloc[-1]
        if pd.notna(fish_val) and pd.notna(sig_val):
            logger.debug(
                f"Indicator Calc (EhlersFisher({length},{signal})): Fisher={fish_val:.4f}, Signal={sig_val:.4f}"
            )
        else:
            logger.debug(
                "Indicator Calc (EhlersFisher): Resulted in NA for last candle."
            )
    except Exception as e:
        logger.error(
            f"{Fore.RED}Indicator Calc (EhlersFisher): Error: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        for col in target_cols:
            df[col] = pd.NA
    return df


def calculate_ehlers_ma(df: pd.DataFrame, fast_len: int, slow_len: int) -> pd.DataFrame:
    """Calculates Ehlers Super Smoother Moving Averages, returns Decimals."""
    target_cols = ["fast_ema", "slow_ema"]
    min_len = max(fast_len, slow_len) + 5  # Add buffer
    if (
        df is None
        or df.empty
        or not all(c in df.columns for c in ["close"])
        or len(df) < min_len
    ):
        logger.warning(
            f"{Fore.YELLOW}Indicator Calc (EhlersMA): Invalid input (Len: {len(df) if df is not None else 0}, Need ~{min_len}).{Style.RESET_ALL}"
        )
        for col in target_cols:
            df[col] = pd.NA
        return df
    try:
        # pandas_ta.supersmoother might not exist, use custom or alternative like Ehlers Filter if needed
        # Assuming ta.ema as a placeholder if supersmoother is unavailable or buggy
        # Replace with actual Ehlers filter implementation if required
        logger.warning(
            f"{Fore.YELLOW}Using EMA as placeholder for Ehlers Super Smoother. Replace with actual implementation if needed.{Style.RESET_ALL}"
        )
        df["fast_ema"] = df.ta.ema(length=fast_len).apply(safe_decimal_conversion)
        df["slow_ema"] = df.ta.ema(length=slow_len).apply(safe_decimal_conversion)

        fast_val, slow_val = df["fast_ema"].iloc[-1], df["slow_ema"].iloc[-1]
        if pd.notna(fast_val) and pd.notna(slow_val):
            logger.debug(
                f"Indicator Calc (EhlersMA({fast_len},{slow_len})): Fast={fast_val:.4f}, Slow={slow_val:.4f}"
            )
        else:
            logger.debug("Indicator Calc (EhlersMA): Resulted in NA for last candle.")
    except Exception as e:
        logger.error(
            f"{Fore.RED}Indicator Calc (EhlersMA): Error: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        for col in target_cols:
            df[col] = pd.NA
    return df


def analyze_order_book(
    exchange: ccxt.Exchange, symbol: str, depth: int, fetch_limit: int
) -> dict[str, Decimal | None]:
    """Fetches and analyzes L2 order book pressure and spread. Returns Decimals."""
    results: dict[str, Decimal | None] = {
        "bid_ask_ratio": None,
        "spread": None,
        "best_bid": None,
        "best_ask": None,
    }
    logger.debug(
        f"Order Book: Fetching L2 {symbol} (Depth:{depth}, Limit:{fetch_limit})..."
    )
    if not exchange.has.get("fetchL2OrderBook"):
        logger.warning(
            f"{Fore.YELLOW}fetchL2OrderBook not supported by {exchange.id}.{Style.RESET_ALL}"
        )
        return results
    try:
        order_book = exchange.fetch_l2_order_book(symbol, limit=fetch_limit)
        bids: list[list[float | str]] = order_book.get("bids", [])
        asks: list[list[float | str]] = order_book.get("asks", [])

        best_bid = (
            safe_decimal_conversion(bids[0][0]) if bids and len(bids[0]) > 0 else None
        )
        best_ask = (
            safe_decimal_conversion(asks[0][0]) if asks and len(asks[0]) > 0 else None
        )
        results["best_bid"] = best_bid
        results["best_ask"] = best_ask

        if (
            best_bid is not None
            and best_ask is not None
            and best_bid > 0
            and best_ask > 0
        ):
            results["spread"] = best_ask - best_bid
            logger.debug(
                f"OB: Bid={best_bid:.4f}, Ask={best_ask:.4f}, Spread={results['spread']:.4f}"
            )
        else:
            logger.debug(
                f"OB: Bid={best_bid or 'N/A'}, Ask={best_ask or 'N/A'} (Spread N/A)"
            )

        # Sum volumes using Decimal
        bid_vol = sum(
            safe_decimal_conversion(bid[1]) for bid in bids[:depth] if len(bid) > 1
        )
        ask_vol = sum(
            safe_decimal_conversion(ask[1]) for ask in asks[:depth] if len(ask) > 1
        )
        logger.debug(f"OB (Depth {depth}): BidVol={bid_vol:.4f}, AskVol={ask_vol:.4f}")

        if ask_vol > CONFIG.position_qty_epsilon:
            try:
                results["bid_ask_ratio"] = bid_vol / ask_vol
                logger.debug(f"OB Ratio: {results['bid_ask_ratio']:.3f}")
            except Exception:
                logger.warning("Error calculating OB ratio.")
                results["bid_ask_ratio"] = None
        else:
            logger.debug("OB Ratio: N/A (Ask volume zero or negligible)")

    except (ccxt.NetworkError, ccxt.ExchangeError, IndexError, Exception) as e:
        logger.warning(
            f"{Fore.YELLOW}Order Book Error for {symbol}: {type(e).__name__} - {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        results = dict.fromkeys(results)  # Reset on error
    return results


# --- Data Fetching ---
def get_market_data(
    exchange: ccxt.Exchange, symbol: str, interval: str, limit: int
) -> pd.DataFrame | None:
    """Fetches and prepares OHLCV data, ensuring numeric types."""
    if not exchange.has.get("fetchOHLCV"):
        logger.error(
            f"{Fore.RED}Data Fetch: Exchange '{exchange.id}' does not support fetchOHLCV.{Style.RESET_ALL}"
        )
        return None
    try:
        logger.debug(
            f"Data Fetch: Fetching {limit} OHLCV candles for {symbol} ({interval})..."
        )
        ohlcv: list[list[int | float | str]] = exchange.fetch_ohlcv(
            symbol, timeframe=interval, limit=limit
        )
        if not ohlcv:
            logger.warning(
                f"{Fore.YELLOW}Data Fetch: No OHLCV data returned for {symbol} ({interval}).{Style.RESET_ALL}"
            )
            return None

        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)

        # Convert to numeric, coercing errors, check NaNs robustly
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        if df.isnull().values.any():
            nan_counts = df.isnull().sum()
            logger.warning(
                f"{Fore.YELLOW}Data Fetch: OHLCV contains NaNs after conversion:\n{nan_counts[nan_counts > 0]}\nAttempting ffill...{Style.RESET_ALL}"
            )
            df.ffill(inplace=True)  # Forward fill first
            if df.isnull().values.any():  # Check again, maybe backfill needed?
                logger.warning(
                    f"{Fore.YELLOW}NaNs remain after ffill, attempting bfill...{Style.RESET_ALL}"
                )
                df.bfill(inplace=True)
                if df.isnull().values.any():
                    logger.error(
                        f"{Fore.RED}Data Fetch: NaNs persist after ffill/bfill. Cannot proceed.{Style.RESET_ALL}"
                    )
                    return None

        logger.debug(f"Data Fetch: Processed {len(df)} OHLCV candles for {symbol}.")
        return df

    except (ccxt.NetworkError, ccxt.ExchangeError, Exception) as e:
        logger.warning(
            f"{Fore.YELLOW}Data Fetch: Error fetching OHLCV for {symbol}: {type(e).__name__} - {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
    return None


# --- Position & Order Management ---
def get_current_position(exchange: ccxt.Exchange, symbol: str) -> dict[str, Any]:
    """Fetches current position details (Bybit V5 focus), returns Decimals."""
    default_pos: dict[str, Any] = {
        "side": CONFIG.pos_none,
        "qty": Decimal("0.0"),
        "entry_price": Decimal("0.0"),
    }
    market_id = None
    market = None
    try:
        market = exchange.market(symbol)
        market_id = market["id"]
    except Exception as e:
        logger.error(
            f"{Fore.RED}Position Check: Failed to get market info for '{symbol}': {e}{Style.RESET_ALL}"
        )
        return default_pos

    try:
        if not exchange.has.get("fetchPositions"):
            logger.warning(
                f"{Fore.YELLOW}Position Check: fetchPositions not supported by {exchange.id}.{Style.RESET_ALL}"
            )
            return default_pos

        # Bybit V5 uses 'category' parameter
        params = (
            {"category": "linear"}
            if market.get("linear")
            else ({"category": "inverse"} if market.get("inverse") else {})
        )
        logger.debug(
            f"Position Check: Fetching positions for {symbol} (MarketID: {market_id}) with params: {params}"
        )

        fetched_positions = exchange.fetch_positions(symbols=[symbol], params=params)

        # Bybit V5 might return multiple entries even for one-way mode sometimes, find the active one
        active_pos = None
        for pos in fetched_positions:
            pos_info = pos.get("info", {})
            pos_market_id = pos_info.get("symbol")
            position_idx = pos_info.get("positionIdx", 0)  # 0 for One-Way mode
            pos_side_v5 = pos_info.get(
                "side", "None"
            )  # 'Buy' for long, 'Sell' for short
            size_str = pos_info.get("size")

            # Filter for the correct symbol and One-Way mode active position
            if (
                pos_market_id == market_id
                and position_idx == 0
                and pos_side_v5 != "None"
            ):
                size = safe_decimal_conversion(size_str)
                if abs(size) > CONFIG.position_qty_epsilon:
                    active_pos = pos  # Found the active position
                    break  # Assume only one active position in One-Way mode

        if active_pos:
            try:
                size = safe_decimal_conversion(active_pos.get("info", {}).get("size"))
                # Use 'avgPrice' from info for V5 entry price
                entry_price = safe_decimal_conversion(
                    active_pos.get("info", {}).get("avgPrice")
                )
                # Determine side based on V5 'side' field
                side = (
                    CONFIG.pos_long
                    if active_pos.get("info", {}).get("side") == "Buy"
                    else CONFIG.pos_short
                )

                logger.info(
                    f"{Fore.YELLOW}Position Check: Found ACTIVE {side} position: Qty={abs(size):.8f} @ Entry={entry_price:.4f}{Style.RESET_ALL}"
                )
                return {"side": side, "qty": abs(size), "entry_price": entry_price}
            except Exception as parse_err:
                logger.warning(
                    f"{Fore.YELLOW}Position Check: Error parsing active position data: {parse_err}. Data: {active_pos}{Style.RESET_ALL}"
                )
                return default_pos
        else:
            logger.info(
                f"Position Check: No active One-Way position found for {market_id}."
            )
            return default_pos

    except (ccxt.NetworkError, ccxt.ExchangeError, Exception) as e:
        logger.warning(
            f"{Fore.YELLOW}Position Check: Error fetching positions for {symbol}: {type(e).__name__} - {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
    return default_pos


def set_leverage(exchange: ccxt.Exchange, symbol: str, leverage: int) -> bool:
    """Sets leverage for a futures symbol (Bybit V5 focus)."""
    logger.info(
        f"{Fore.CYAN}Leverage Setting: Attempting to set {leverage}x for {symbol}...{Style.RESET_ALL}"
    )
    try:
        market = exchange.market(symbol)
        if not market.get("contract"):
            logger.error(
                f"{Fore.RED}Leverage Setting: Cannot set for non-contract market: {symbol}.{Style.RESET_ALL}"
            )
            return False
    except Exception as e:
        logger.error(
            f"{Fore.RED}Leverage Setting: Failed to get market info for '{symbol}': {e}{Style.RESET_ALL}"
        )
        return False

    for attempt in range(CONFIG.retry_count):
        try:
            # Bybit V5 requires setting buy and sell leverage separately
            params = {"buyLeverage": str(leverage), "sellLeverage": str(leverage)}
            response = exchange.set_leverage(
                leverage=leverage, symbol=symbol, params=params
            )
            logger.success(
                f"{Fore.GREEN}Leverage Setting: Set to {leverage}x for {symbol}. Response: {response}{Style.RESET_ALL}"
            )
            return True
        except ccxt.ExchangeError as e:
            # Check for common "already set" messages
            err_str = str(e).lower()
            if (
                "leverage not modified" in err_str
                or "leverage is same as requested" in err_str
            ):
                logger.info(
                    f"{Fore.CYAN}Leverage Setting: Already set to {leverage}x for {symbol}.{Style.RESET_ALL}"
                )
                return True
            logger.warning(
                f"{Fore.YELLOW}Leverage Setting: Exchange error (Attempt {attempt + 1}/{CONFIG.retry_count}): {e}{Style.RESET_ALL}"
            )
            if attempt < CONFIG.retry_count - 1:
                time.sleep(CONFIG.retry_delay_seconds)
            else:
                logger.error(
                    f"{Fore.RED}Leverage Setting: Failed after {CONFIG.retry_count} attempts.{Style.RESET_ALL}"
                )
        except (ccxt.NetworkError, Exception) as e:
            logger.warning(
                f"{Fore.YELLOW}Leverage Setting: Network/Other error (Attempt {attempt + 1}/{CONFIG.retry_count}): {e}{Style.RESET_ALL}"
            )
            if attempt < CONFIG.retry_count - 1:
                time.sleep(CONFIG.retry_delay_seconds)
            else:
                logger.error(
                    f"{Fore.RED}Leverage Setting: Failed after {CONFIG.retry_count} attempts.{Style.RESET_ALL}"
                )
    return False


def close_position(
    exchange: ccxt.Exchange,
    symbol: str,
    position_to_close: dict[str, Any],
    reason: str = "Signal",
) -> dict[str, Any] | None:
    """Closes the specified active position with re-validation, uses Decimal."""
    initial_side = position_to_close.get("side", CONFIG.pos_none)
    initial_qty = position_to_close.get("qty", Decimal("0.0"))
    market_base = symbol.split("/")[0]
    logger.info(
        f"{Fore.YELLOW}Close Position: Initiated for {symbol}. Reason: {reason}. Initial state: {initial_side} Qty={initial_qty:.8f}{Style.RESET_ALL}"
    )

    # Re-validate the position just before closing
    live_position = get_current_position(exchange, symbol)
    if live_position["side"] == CONFIG.pos_none:
        logger.warning(
            f"{Fore.YELLOW}Close Position: Re-validation shows NO active position for {symbol}. Aborting.{Style.RESET_ALL}"
        )
        if initial_side != CONFIG.pos_none:
            logger.warning(
                f"{Fore.YELLOW}Close Position: Discrepancy detected (was {initial_side}, now None).{Style.RESET_ALL}"
            )
        return None

    live_amount_to_close = live_position["qty"]
    live_position_side = live_position["side"]
    side_to_execute_close = (
        CONFIG.side_sell if live_position_side == CONFIG.pos_long else CONFIG.side_buy
    )

    try:
        amount_str = format_amount(exchange, symbol, live_amount_to_close)
        amount_float = float(amount_str)  # CCXT create order expects float
        if amount_float <= float(CONFIG.position_qty_epsilon):
            logger.error(
                f"{Fore.RED}Close Position: Closing amount after precision is negligible ({amount_str}). Aborting.{Style.RESET_ALL}"
            )
            return None

        logger.warning(
            f"{Back.YELLOW}{Fore.BLACK}Close Position: Attempting to CLOSE {live_position_side} ({reason}): "
            f"Exec {side_to_execute_close.upper()} MARKET {amount_str} {symbol} (reduce_only=True)...{Style.RESET_ALL}"
        )
        params = {"reduceOnly": True}
        order = exchange.create_market_order(
            symbol=symbol,
            side=side_to_execute_close,
            amount=amount_float,
            params=params,
        )

        # Parse order response safely using Decimal
        fill_price = safe_decimal_conversion(order.get("average"))
        filled_qty = safe_decimal_conversion(order.get("filled"))
        cost = safe_decimal_conversion(order.get("cost"))
        order_id_short = format_order_id(order.get("id"))

        logger.success(
            f"{Fore.GREEN}{Style.BRIGHT}Close Position: Order ({reason}) placed for {symbol}. "
            f"Filled: {filled_qty:.8f}/{amount_str}, AvgFill: {fill_price:.4f}, Cost: {cost:.2f} USDT. ID:...{order_id_short}{Style.RESET_ALL}"
        )
        send_sms_alert(
            f"[{market_base}] Closed {live_position_side} {amount_str} @ ~{fill_price:.4f} ({reason}). ID:...{order_id_short}"
        )
        return order

    except (
        ccxt.InsufficientFunds,
        ccxt.NetworkError,
        ccxt.ExchangeError,
        ValueError,
        Exception,
    ) as e:
        logger.error(
            f"{Fore.RED}Close Position ({reason}): Failed for {symbol}: {type(e).__name__} - {e}{Style.RESET_ALL}"
        )
        # Check for specific Bybit errors indicating already closed
        err_str = str(e).lower()
        if isinstance(e, ccxt.ExchangeError) and (
            "order would not reduce position size" in err_str
            or "position is zero" in err_str
            or "position size is zero" in err_str
        ):
            logger.warning(
                f"{Fore.YELLOW}Close Position: Exchange indicates position already closed/closing. Assuming closed.{Style.RESET_ALL}"
            )
            return None  # Treat as success in this case
        send_sms_alert(
            f"[{market_base}] ERROR Closing ({reason}): {type(e).__name__}. Check logs."
        )
    return None


def calculate_position_size(
    equity: Decimal,
    risk_per_trade_pct: Decimal,
    entry_price: Decimal,
    stop_loss_price: Decimal,
    leverage: int,
    symbol: str,
    exchange: ccxt.Exchange,
) -> tuple[Decimal | None, Decimal | None]:
    """Calculates position size and estimated margin based on risk, using Decimal."""
    logger.debug(
        f"Risk Calc: Equity={equity:.4f}, Risk%={risk_per_trade_pct:.4%}, Entry={entry_price:.4f}, SL={stop_loss_price:.4f}, Lev={leverage}x"
    )
    if not (entry_price > 0 and stop_loss_price > 0):
        logger.error(f"{Fore.RED}Risk Calc: Invalid entry/SL price.{Style.RESET_ALL}")
        return None, None
    price_diff = abs(entry_price - stop_loss_price)
    if price_diff < CONFIG.position_qty_epsilon:
        logger.error(
            f"{Fore.RED}Risk Calc: Entry/SL prices too close ({price_diff:.8f}).{Style.RESET_ALL}"
        )
        return None, None
    if not 0 < risk_per_trade_pct < 1:
        logger.error(
            f"{Fore.RED}Risk Calc: Invalid risk %: {risk_per_trade_pct:.4%}.{Style.RESET_ALL}"
        )
        return None, None
    if equity <= 0:
        logger.error(
            f"{Fore.RED}Risk Calc: Invalid equity: {equity:.4f}{Style.RESET_ALL}"
        )
        return None, None
    if leverage <= 0:
        logger.error(
            f"{Fore.RED}Risk Calc: Invalid leverage: {leverage}{Style.RESET_ALL}"
        )
        return None, None

    risk_amount_usdt = equity * risk_per_trade_pct
    # Assuming linear contract where 1 unit = 1 base currency (e.g., 1 BTC)
    # Risk per unit = price_diff
    quantity_raw = risk_amount_usdt / price_diff

    try:
        # Format according to market precision *then* convert back to Decimal
        quantity_precise_str = format_amount(exchange, symbol, quantity_raw)
        quantity_precise = Decimal(quantity_precise_str)
    except Exception as e:
        logger.warning(
            f"{Fore.YELLOW}Risk Calc: Failed precision formatting for quantity {quantity_raw:.8f}. Using raw. Error: {e}{Style.RESET_ALL}"
        )
        quantity_precise = quantity_raw.quantize(
            Decimal("1e-8"), rounding=ROUND_HALF_UP
        )  # Fallback quantization

    if quantity_precise <= CONFIG.position_qty_epsilon:
        logger.warning(
            f"{Fore.YELLOW}Risk Calc: Calculated quantity negligible ({quantity_precise:.8f}). RiskAmt={risk_amount_usdt:.4f}, PriceDiff={price_diff:.4f}{Style.RESET_ALL}"
        )
        return None, None

    pos_value_usdt = quantity_precise * entry_price
    required_margin = pos_value_usdt / Decimal(leverage)
    logger.debug(
        f"Risk Calc Result: Qty={quantity_precise:.8f}, EstValue={pos_value_usdt:.4f}, EstMargin={required_margin:.4f}"
    )
    return quantity_precise, required_margin


def wait_for_order_fill(
    exchange: ccxt.Exchange, order_id: str, symbol: str, timeout_seconds: int
) -> dict[str, Any] | None:
    """Waits for a specific order to be filled (status 'closed')."""
    start_time = time.time()
    logger.info(
        f"{Fore.CYAN}Waiting for order ...{format_order_id(order_id)} ({symbol}) fill (Timeout: {timeout_seconds}s)...{Style.RESET_ALL}"
    )
    while time.time() - start_time < timeout_seconds:
        try:
            order = exchange.fetch_order(order_id, symbol)
            status = order.get("status")
            logger.debug(f"Order ...{format_order_id(order_id)} status: {status}")
            if status == "closed":
                logger.success(
                    f"{Fore.GREEN}Order ...{format_order_id(order_id)} confirmed FILLED.{Style.RESET_ALL}"
                )
                return order
            elif status in ["canceled", "rejected", "expired"]:
                logger.error(
                    f"{Fore.RED}Order ...{format_order_id(order_id)} failed with status '{status}'.{Style.RESET_ALL}"
                )
                return None  # Failed state
            # Continue polling if 'open' or 'partially_filled' or None
            time.sleep(0.5)  # Check every 500ms
        except ccxt.OrderNotFound:
            # This might happen briefly after placing, keep trying
            logger.warning(
                f"{Fore.YELLOW}Order ...{format_order_id(order_id)} not found yet. Retrying...{Style.RESET_ALL}"
            )
            time.sleep(1)
        except (ccxt.NetworkError, ccxt.ExchangeError, Exception) as e:
            logger.warning(
                f"{Fore.YELLOW}Error checking order ...{format_order_id(order_id)}: {type(e).__name__} - {e}. Retrying...{Style.RESET_ALL}"
            )
            time.sleep(1)  # Wait longer on error
    logger.error(
        f"{Fore.RED}Order ...{format_order_id(order_id)} did not fill within {timeout_seconds}s timeout.{Style.RESET_ALL}"
    )
    return None  # Timeout


def place_risked_market_order(
    exchange: ccxt.Exchange,
    symbol: str,
    side: str,
    risk_percentage: Decimal,
    current_atr: Decimal | None,
    sl_atr_multiplier: Decimal,
    leverage: int,
    max_order_cap_usdt: Decimal,
    margin_check_buffer: Decimal,
    tsl_percent: Decimal,
    tsl_activation_offset_percent: Decimal,
) -> dict[str, Any] | None:
    """Places market entry, waits for fill, then places exchange-native fixed SL and TSL using Decimal."""
    market_base = symbol.split("/")[0]
    logger.info(
        f"{Fore.BLUE}{Style.BRIGHT}Place Order: Initiating {side.upper()} for {symbol}...{Style.RESET_ALL}"
    )
    if current_atr is None or current_atr <= Decimal("0"):
        logger.error(
            f"{Fore.RED}Place Order ({side.upper()}): Invalid ATR ({current_atr}). Cannot place order.{Style.RESET_ALL}"
        )
        return None

    entry_price_estimate: Decimal | None = None
    initial_sl_price_estimate: Decimal | None = None
    final_quantity: Decimal | None = None
    market: dict | None = None

    try:
        # === 1. Get Balance, Market Info, Limits ===
        logger.debug("Fetching balance & market details...")
        balance = exchange.fetch_balance()
        market = exchange.market(symbol)
        limits = market.get("limits", {})
        amount_limits = limits.get("amount", {})
        price_limits = limits.get("price", {})
        min_qty_str = amount_limits.get("min")
        max_qty_str = amount_limits.get("max")
        min_price_str = price_limits.get("min")
        min_qty = safe_decimal_conversion(min_qty_str) if min_qty_str else None
        max_qty = safe_decimal_conversion(max_qty_str) if max_qty_str else None
        min_price = safe_decimal_conversion(min_price_str) if min_price_str else None

        usdt_balance = balance.get(CONFIG.usdt_symbol, {})
        usdt_total = safe_decimal_conversion(usdt_balance.get("total"))
        usdt_free = safe_decimal_conversion(usdt_balance.get("free"))
        usdt_equity = (
            usdt_total if usdt_total > 0 else usdt_free
        )  # Use total if available, else free

        if usdt_equity <= Decimal("0"):
            logger.error(
                f"{Fore.RED}Place Order ({side.upper()}): Zero/Invalid equity ({usdt_equity:.4f}).{Style.RESET_ALL}"
            )
            return None
        if usdt_free < Decimal("0"):
            logger.error(
                f"{Fore.RED}Place Order ({side.upper()}): Invalid free margin ({usdt_free:.4f}).{Style.RESET_ALL}"
            )
            return None
        logger.debug(f"Equity={usdt_equity:.4f}, Free={usdt_free:.4f} USDT")

        # === 2. Estimate Entry Price ===
        ob_data = analyze_order_book(
            exchange,
            symbol,
            CONFIG.shallow_ob_fetch_depth,
            CONFIG.shallow_ob_fetch_depth,
        )
        best_ask = ob_data.get("best_ask")
        best_bid = ob_data.get("best_bid")
        if side == CONFIG.side_buy and best_ask:
            entry_price_estimate = best_ask
        elif side == CONFIG.side_sell and best_bid:
            entry_price_estimate = best_bid
        else:
            try:
                entry_price_estimate = safe_decimal_conversion(
                    exchange.fetch_ticker(symbol).get("last")
                )
            except Exception as e:
                logger.error(
                    f"{Fore.RED}Failed to fetch ticker price: {e}{Style.RESET_ALL}"
                )
                return None
        if not entry_price_estimate or entry_price_estimate <= 0:
            logger.error(
                f"{Fore.RED}Invalid entry price estimate ({entry_price_estimate}).{Style.RESET_ALL}"
            )
            return None
        logger.debug(f"Estimated Entry Price ~ {entry_price_estimate:.4f}")

        # === 3. Calculate Initial Stop Loss Price (Estimate) ===
        sl_distance = current_atr * sl_atr_multiplier
        initial_sl_price_raw = (
            (entry_price_estimate - sl_distance)
            if side == CONFIG.side_buy
            else (entry_price_estimate + sl_distance)
        )
        if min_price is not None and initial_sl_price_raw < min_price:
            initial_sl_price_raw = min_price
        if initial_sl_price_raw <= 0:
            logger.error(
                f"{Fore.RED}Invalid Initial SL price calc: {initial_sl_price_raw:.4f}{Style.RESET_ALL}"
            )
            return None
        initial_sl_price_estimate = safe_decimal_conversion(
            format_price(exchange, symbol, initial_sl_price_raw)
        )  # Format estimate
        logger.info(
            f"Calculated Initial SL Price (Estimate) ~ {initial_sl_price_estimate:.4f} (Dist: {sl_distance:.4f})"
        )

        # === 4. Calculate Position Size ===
        calc_qty, req_margin = calculate_position_size(
            usdt_equity,
            risk_percentage,
            entry_price_estimate,
            initial_sl_price_estimate,
            leverage,
            symbol,
            exchange,
        )
        if calc_qty is None or req_margin is None:
            logger.error(f"{Fore.RED}Failed risk calculation.{Style.RESET_ALL}")
            return None
        final_quantity = calc_qty

        # === 5. Apply Max Order Cap ===
        pos_value = final_quantity * entry_price_estimate
        if pos_value > max_order_cap_usdt:
            logger.warning(
                f"{Fore.YELLOW}Order value {pos_value:.4f} > Cap {max_order_cap_usdt:.4f}. Capping qty.{Style.RESET_ALL}"
            )
            final_quantity = max_order_cap_usdt / entry_price_estimate
            # Format capped quantity
            final_quantity = safe_decimal_conversion(
                format_amount(exchange, symbol, final_quantity)
            )
            req_margin = max_order_cap_usdt / Decimal(
                leverage
            )  # Recalculate margin based on cap

        # === 6. Check Limits & Margin ===
        if final_quantity <= CONFIG.position_qty_epsilon:
            logger.error(
                f"{Fore.RED}Final Qty negligible: {final_quantity:.8f}{Style.RESET_ALL}"
            )
            return None
        if min_qty is not None and final_quantity < min_qty:
            logger.error(
                f"{Fore.RED}Final Qty {final_quantity:.8f} < Min {min_qty}{Style.RESET_ALL}"
            )
            return None
        if max_qty is not None and final_quantity > max_qty:
            logger.warning(
                f"{Fore.YELLOW}Final Qty {final_quantity:.8f} > Max {max_qty}. Capping.{Style.RESET_ALL}"
            )
            final_quantity = max_qty
            final_quantity = safe_decimal_conversion(
                format_amount(exchange, symbol, final_quantity)
            )  # Re-format capped amount

        final_req_margin = (final_quantity * entry_price_estimate) / Decimal(
            leverage
        )  # Final margin estimate
        req_margin_buffered = final_req_margin * margin_check_buffer

        if usdt_free < req_margin_buffered:
            logger.error(
                f"{Fore.RED}Insufficient FREE margin. Need ~{req_margin_buffered:.4f}, Have {usdt_free:.4f}{Style.RESET_ALL}"
            )
            send_sms_alert(
                f"[{market_base}] ORDER FAIL ({side.upper()}): Insufficient Free Margin"
            )
            return None
        logger.info(
            f"{Fore.GREEN}Final Order: Qty={final_quantity:.8f}, EstValue={final_quantity * entry_price_estimate:.4f}, EstMargin={final_req_margin:.4f}. Margin check OK.{Style.RESET_ALL}"
        )

        # === 7. Place Entry Market Order ===
        entry_order: dict[str, Any] | None = None
        order_id: str | None = None
        try:
            qty_float = float(final_quantity)  # CCXT expects float
            logger.warning(
                f"{Back.GREEN}{Fore.BLACK}{Style.BRIGHT}*** Placing {side.upper()} MARKET ENTRY: {qty_float:.8f} {symbol} ***{Style.RESET_ALL}"
            )
            entry_order = exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=qty_float,
                params={"reduce_only": False},
            )
            order_id = entry_order.get("id")
            if not order_id:
                logger.error(
                    f"{Fore.RED}Entry order placed but no ID returned! Response: {entry_order}{Style.RESET_ALL}"
                )
                return None
            logger.success(
                f"{Fore.GREEN}Market Entry Order submitted. ID: ...{format_order_id(order_id)}. Waiting for fill...{Style.RESET_ALL}"
            )
        except Exception as e:
            logger.error(
                f"{Fore.RED}{Style.BRIGHT}FAILED TO PLACE ENTRY ORDER: {e}{Style.RESET_ALL}"
            )
            logger.debug(traceback.format_exc())
            send_sms_alert(
                f"[{market_base}] ORDER FAIL ({side.upper()}): Entry placement failed: {type(e).__name__}"
            )
            return None

        # === 8. Wait for Entry Fill ===
        filled_entry = wait_for_order_fill(
            exchange, order_id, symbol, CONFIG.order_fill_timeout_seconds
        )
        if not filled_entry:
            logger.error(
                f"{Fore.RED}Entry order ...{format_order_id(order_id)} did not fill/failed.{Style.RESET_ALL}"
            )
            send_sms_alert(
                f"[{market_base}] ORDER FAIL ({side.upper()}): Entry ...{format_order_id(order_id)} fill timeout/fail."
            )
            # Try to cancel the potentially stuck order (Corrected Block)
            try:
                logger.info(
                    f"{Fore.CYAN}Attempting cancellation of potentially stuck order ...{format_order_id(order_id)}.{Style.RESET_ALL}"
                )
                exchange.cancel_order(order_id, symbol)
            except Exception as cancel_e:
                # Log the cancellation error, but proceed to return None as the entry failed
                logger.warning(
                    f"{Fore.YELLOW}Failed to cancel potentially stuck order ...{format_order_id(order_id)}: {cancel_e}{Style.RESET_ALL}"
                )
                pass  # Allow the function to return None below
            return None  # Return None as the entry failed

        # === 9. Extract Fill Details (Crucial: Use Actual Fill) ===
        avg_fill_price = safe_decimal_conversion(filled_entry.get("average"))
        filled_qty = safe_decimal_conversion(filled_entry.get("filled"))
        cost = safe_decimal_conversion(filled_entry.get("cost"))

        if avg_fill_price <= 0 or filled_qty <= CONFIG.position_qty_epsilon:
            logger.error(
                f"{Fore.RED}Invalid fill details for ...{format_order_id(order_id)}: Price={avg_fill_price}, Qty={filled_qty}{Style.RESET_ALL}"
            )
            send_sms_alert(
                f"[{market_base}] ORDER FAIL ({side.upper()}): Invalid fill details ...{format_order_id(order_id)}."
            )
            return filled_entry  # Return problematic order

        logger.success(
            f"{Back.GREEN}{Fore.BLACK}{Style.BRIGHT}ENTRY CONFIRMED: ...{format_order_id(order_id)}. Filled: {filled_qty:.8f} @ {avg_fill_price:.4f}, Cost: {cost:.4f} USDT{Style.RESET_ALL}"
        )

        # === 10. Calculate ACTUAL Stop Loss Price based on Fill ===
        # Recalculate sl_distance using the confirmed ATR value used for sizing
        sl_distance = current_atr * sl_atr_multiplier
        actual_sl_price_raw = (
            (avg_fill_price - sl_distance)
            if side == CONFIG.side_buy
            else (avg_fill_price + sl_distance)
        )
        if min_price is not None and actual_sl_price_raw < min_price:
            actual_sl_price_raw = min_price
        if actual_sl_price_raw <= 0:
            logger.error(
                f"{Fore.RED}Invalid ACTUAL SL price calc based on fill: {actual_sl_price_raw:.4f}. Cannot place SL!{Style.RESET_ALL}"
            )
            # CRITICAL: Position is open without SL. Attempt emergency close.
            send_sms_alert(
                f"[{market_base}] CRITICAL ({side.upper()}): Invalid ACTUAL SL price! Attempting emergency close."
            )
            close_position(
                exchange,
                symbol,
                {"side": side, "qty": filled_qty},
                reason="Invalid SL Calc",
            )
            return filled_entry  # Return filled entry, but indicate failure state
        actual_sl_price_str = format_price(exchange, symbol, actual_sl_price_raw)
        actual_sl_price_float = float(actual_sl_price_str)  # For CCXT param

        # === 11. Place Initial Fixed Stop Loss ===
        sl_order_id = "N/A"
        try:
            sl_side = CONFIG.side_sell if side == CONFIG.side_buy else CONFIG.side_buy
            sl_qty_str = format_amount(exchange, symbol, filled_qty)
            sl_qty_float = float(sl_qty_str)

            logger.info(
                f"{Fore.CYAN}Placing Initial Fixed SL ({sl_atr_multiplier}*ATR)... Side: {sl_side.upper()}, Qty: {sl_qty_float:.8f}, StopPx: {actual_sl_price_str}{Style.RESET_ALL}"
            )
            # Bybit V5 stop order params: stopPrice (trigger), reduceOnly
            sl_params = {"stopPrice": actual_sl_price_float, "reduceOnly": True}
            sl_order = exchange.create_order(
                symbol, "stopMarket", sl_side, sl_qty_float, params=sl_params
            )
            sl_order_id = format_order_id(sl_order.get("id"))
            logger.success(
                f"{Fore.GREEN}Initial Fixed SL order placed. ID: ...{sl_order_id}, Trigger: {actual_sl_price_str}{Style.RESET_ALL}"
            )
        except Exception as e:
            logger.error(
                f"{Fore.RED}{Style.BRIGHT}FAILED to place Initial Fixed SL order: {e}{Style.RESET_ALL}"
            )
            logger.debug(traceback.format_exc())
            send_sms_alert(
                f"[{market_base}] ERROR ({side.upper()}): Failed initial SL placement: {type(e).__name__}"
            )
            # Don't necessarily close here, TSL might still work, or user might want manual intervention

        # === 12. Place Trailing Stop Loss ===
        tsl_order_id = "N/A"
        tsl_act_price_str = "N/A"
        try:
            # Calculate TSL activation price based on actual fill
            act_offset = avg_fill_price * tsl_activation_offset_percent
            act_price_raw = (
                (avg_fill_price + act_offset)
                if side == CONFIG.side_buy
                else (avg_fill_price - act_offset)
            )
            if min_price is not None and act_price_raw < min_price:
                act_price_raw = min_price
            if act_price_raw <= 0:
                raise ValueError(f"Invalid TSL activation price {act_price_raw:.4f}")

            tsl_act_price_str = format_price(exchange, symbol, act_price_raw)
            tsl_act_price_float = float(tsl_act_price_str)
            tsl_side = CONFIG.side_sell if side == CONFIG.side_buy else CONFIG.side_buy
            # Bybit V5 uses 'trailingStop' for percentage distance (e.g., "0.5" for 0.5%)
            tsl_trail_value_str = str(tsl_percent * Decimal("100"))
            tsl_qty_str = format_amount(exchange, symbol, filled_qty)
            tsl_qty_float = float(tsl_qty_str)

            logger.info(
                f"{Fore.CYAN}Placing Trailing SL ({tsl_percent:.2%})... Side: {tsl_side.upper()}, Qty: {tsl_qty_float:.8f}, Trail%: {tsl_trail_value_str}, ActPx: {tsl_act_price_str}{Style.RESET_ALL}"
            )
            # Bybit V5 TSL params: trailingStop (percent string), activePrice (activation trigger), reduceOnly
            tsl_params = {
                "trailingStop": tsl_trail_value_str,
                "activePrice": tsl_act_price_float,
                "reduceOnly": True,
            }
            # Use 'stopMarket' type with TSL params for Bybit V5 via CCXT
            tsl_order = exchange.create_order(
                symbol, "stopMarket", tsl_side, tsl_qty_float, params=tsl_params
            )
            tsl_order_id = format_order_id(tsl_order.get("id"))
            logger.success(
                f"{Fore.GREEN}Trailing SL order placed. ID: ...{tsl_order_id}, Trail%: {tsl_trail_value_str}, ActPx: {tsl_act_price_str}{Style.RESET_ALL}"
            )

            # Final comprehensive SMS
            sms_msg = (
                f"[{market_base}] ENTERED {side.upper()} {filled_qty:.8f} @ {avg_fill_price:.4f}. "
                f"Init SL ~{actual_sl_price_str}. TSL {tsl_percent:.2%} act@{tsl_act_price_str}. "
                f"IDs E:...{format_order_id(order_id)}, SL:...{sl_order_id}, TSL:...{tsl_order_id}"
            )
            send_sms_alert(sms_msg)

        except Exception as e:
            logger.error(
                f"{Fore.RED}{Style.BRIGHT}FAILED to place Trailing SL order: {e}{Style.RESET_ALL}"
            )
            logger.debug(traceback.format_exc())
            send_sms_alert(
                f"[{market_base}] ERROR ({side.upper()}): Failed TSL placement: {type(e).__name__}"
            )
            # If TSL fails but initial SL was placed, the position is still protected initially.

        return filled_entry  # Return filled entry order details regardless of SL/TSL placement success

    except (
        ccxt.InsufficientFunds,
        ccxt.NetworkError,
        ccxt.ExchangeError,
        ValueError,
        Exception,
    ) as e:
        logger.error(
            f"{Fore.RED}{Style.BRIGHT}Place Order ({side.upper()}): Overall process failed: {type(e).__name__} - {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        send_sms_alert(
            f"[{market_base}] ORDER FAIL ({side.upper()}): Overall process failed: {type(e).__name__}"
        )
    return None


def cancel_open_orders(
    exchange: ccxt.Exchange, symbol: str, reason: str = "Cleanup"
) -> None:
    """Attempts to cancel all open orders for the specified symbol."""
    logger.info(
        f"{Fore.CYAN}Order Cancel: Attempting for {symbol} (Reason: {reason})...{Style.RESET_ALL}"
    )
    try:
        if not exchange.has.get("fetchOpenOrders"):
            logger.warning(
                f"{Fore.YELLOW}Order Cancel: fetchOpenOrders not supported.{Style.RESET_ALL}"
            )
            return
        open_orders = exchange.fetch_open_orders(symbol)
        if not open_orders:
            logger.info(
                f"{Fore.CYAN}Order Cancel: No open orders found for {symbol}.{Style.RESET_ALL}"
            )
            return

        logger.warning(
            f"{Fore.YELLOW}Order Cancel: Found {len(open_orders)} open orders for {symbol}. Cancelling...{Style.RESET_ALL}"
        )
        cancelled_count, failed_count = 0, 0
        for order in open_orders:
            order_id = order.get("id")
            order_info = f"...{format_order_id(order_id)} ({order.get('type')} {order.get('side')})"
            if order_id:
                try:
                    exchange.cancel_order(order_id, symbol)
                    logger.info(
                        f"{Fore.CYAN}Order Cancel: Success for {order_info}{Style.RESET_ALL}"
                    )
                    cancelled_count += 1
                    time.sleep(0.1)  # Small delay between cancels
                except ccxt.OrderNotFound:
                    logger.warning(
                        f"{Fore.YELLOW}Order Cancel: Not found (already closed/cancelled?): {order_info}{Style.RESET_ALL}"
                    )
                    cancelled_count += 1  # Treat as cancelled if not found
                except (ccxt.NetworkError, ccxt.ExchangeError, Exception) as e:
                    logger.error(
                        f"{Fore.RED}Order Cancel: FAILED for {order_info}: {type(e).__name__} - {e}{Style.RESET_ALL}"
                    )
                    failed_count += 1
        logger.info(
            f"{Fore.CYAN}Order Cancel: Finished. Cancelled: {cancelled_count}, Failed: {failed_count}.{Style.RESET_ALL}"
        )
        if failed_count > 0:
            send_sms_alert(
                f"[{symbol.split('/')[0]}] WARNING: Failed to cancel {failed_count} orders during {reason}."
            )
    except (ccxt.NetworkError, ccxt.ExchangeError, Exception) as e:
        logger.error(
            f"{Fore.RED}Order Cancel: Failed fetching open orders for {symbol}: {type(e).__name__} - {e}{Style.RESET_ALL}"
        )


# --- Strategy Signal Generation ---
def generate_signals(df: pd.DataFrame, strategy_name: str) -> dict[str, Any]:
    """Generates entry/exit signals based on the selected strategy."""
    signals = {
        "enter_long": False,
        "enter_short": False,
        "exit_long": False,
        "exit_short": False,
        "exit_reason": "Strategy Exit",
    }
    if len(df) < 2:
        return signals  # Need previous candle for comparisons/crosses

    last = df.iloc[-1]
    prev = df.iloc[-2]

    try:
        # --- Dual Supertrend Logic ---
        if strategy_name == "DUAL_SUPERTREND":
            # Check if columns exist and are not NA before accessing boolean value
            if (
                "st_long" in last
                and pd.notna(last["st_long"])
                and last["st_long"]
                and "confirm_trend" in last
                and pd.notna(last["confirm_trend"])
                and last["confirm_trend"]
            ):
                signals["enter_long"] = True
            if (
                "st_short" in last
                and pd.notna(last["st_short"])
                and last["st_short"]
                and "confirm_trend" in last
                and pd.notna(last["confirm_trend"])
                and not last["confirm_trend"]
            ):
                signals["enter_short"] = True
            if "st_short" in last and pd.notna(last["st_short"]) and last["st_short"]:
                signals["exit_long"] = True
                signals["exit_reason"] = "Primary ST Short Flip"
            if "st_long" in last and pd.notna(last["st_long"]) and last["st_long"]:
                signals["exit_short"] = True
                signals["exit_reason"] = "Primary ST Long Flip"

        # --- StochRSI + Momentum Logic ---
        elif strategy_name == "STOCHRSI_MOMENTUM":
            required_cols = ["stochrsi_k", "stochrsi_d", "momentum"]
            if not all(
                col in last and pd.notna(last[col]) for col in required_cols
            ) or not all(
                col in prev and pd.notna(prev[col])
                for col in ["stochrsi_k", "stochrsi_d"]
            ):
                logger.debug("StochRSI/Mom signals skipped due to NA values.")
                return signals  # Not enough data or indicator failed

            k_now, d_now, mom_now = (
                last["stochrsi_k"],
                last["stochrsi_d"],
                last["momentum"],
            )
            k_prev, d_prev = prev["stochrsi_k"], prev["stochrsi_d"]

            if (
                k_prev <= d_prev
                and k_now > d_now
                and k_now < CONFIG.stochrsi_oversold
                and mom_now > CONFIG.position_qty_epsilon
            ):
                signals["enter_long"] = True
            if (
                k_prev >= d_prev
                and k_now < d_now
                and k_now > CONFIG.stochrsi_overbought
                and mom_now < -CONFIG.position_qty_epsilon
            ):
                signals["enter_short"] = True
            if k_prev >= d_prev and k_now < d_now:
                signals["exit_long"] = True
                signals["exit_reason"] = "StochRSI K below D"
            if k_prev <= d_prev and k_now > d_now:
                signals["exit_short"] = True
                signals["exit_reason"] = "StochRSI K above D"

        # --- Ehlers Fisher Logic ---
        elif strategy_name == "EHLERS_FISHER":
            required_cols = ["ehlers_fisher", "ehlers_signal"]
            if not all(
                col in last and pd.notna(last[col]) for col in required_cols
            ) or not all(col in prev and pd.notna(prev[col]) for col in required_cols):
                logger.debug("Ehlers Fisher signals skipped due to NA values.")
                return signals

            fish_now, sig_now = last["ehlers_fisher"], last["ehlers_signal"]
            fish_prev, sig_prev = prev["ehlers_fisher"], prev["ehlers_signal"]

            if fish_prev <= sig_prev and fish_now > sig_now:
                signals["enter_long"] = True
            if fish_prev >= sig_prev and fish_now < sig_now:
                signals["enter_short"] = True
            if fish_prev >= sig_prev and fish_now < sig_now:
                signals["exit_long"] = True
                signals["exit_reason"] = "Ehlers Fisher Short Cross"
            if fish_prev <= sig_prev and fish_now > sig_now:
                signals["exit_short"] = True
                signals["exit_reason"] = "Ehlers Fisher Long Cross"

        # --- Ehlers MA Cross Logic ---
        elif strategy_name == "EHLERS_MA_CROSS":
            required_cols = ["fast_ema", "slow_ema"]
            if not all(
                col in last and pd.notna(last[col]) for col in required_cols
            ) or not all(col in prev and pd.notna(prev[col]) for col in required_cols):
                logger.debug("Ehlers MA signals skipped due to NA values.")
                return signals

            fast_ma_now, slow_ma_now = last["fast_ema"], last["slow_ema"]
            fast_ma_prev, slow_ma_prev = prev["fast_ema"], prev["slow_ema"]

            if fast_ma_prev <= slow_ma_prev and fast_ma_now > slow_ma_now:
                signals["enter_long"] = True
            if fast_ma_prev >= slow_ma_prev and fast_ma_now < slow_ma_now:
                signals["enter_short"] = True
            if fast_ma_prev >= slow_ma_prev and fast_ma_now < slow_ma_now:
                signals["exit_long"] = True
                signals["exit_reason"] = "Ehlers MA Short Cross"
            if fast_ma_prev <= slow_ma_prev and fast_ma_now > slow_ma_now:
                signals["exit_short"] = True
                signals["exit_reason"] = "Ehlers MA Long Cross"

    except KeyError as e:
        logger.error(
            f"{Fore.RED}Signal Generation Error: Missing expected column in DataFrame: {e}{Style.RESET_ALL}"
        )
    except Exception as e:
        logger.error(
            f"{Fore.RED}Signal Generation Error: Unexpected exception: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())

    return signals


# --- Trading Logic ---
def trade_logic(exchange: ccxt.Exchange, symbol: str, df: pd.DataFrame) -> None:
    """Executes the main trading logic for one cycle based on selected strategy."""
    cycle_time_str = (
        df.index[-1].strftime("%Y-%m-%d %H:%M:%S %Z") if not df.empty else "N/A"
    )
    logger.info(
        f"{Fore.BLUE}{Style.BRIGHT}========== New Check Cycle ({CONFIG.strategy_name}): {symbol} | Candle: {cycle_time_str} =========={Style.RESET_ALL}"
    )

    # Determine required rows based on the longest lookback needed by any indicator used
    required_rows = (
        max(
            CONFIG.st_atr_length,
            CONFIG.confirm_st_atr_length,
            CONFIG.stochrsi_rsi_length + CONFIG.stochrsi_stoch_length,
            CONFIG.momentum_length,  # Estimate
            CONFIG.ehlers_fisher_length,
            CONFIG.ehlers_fisher_signal_length,
            CONFIG.ehlers_fast_period,
            CONFIG.ehlers_slow_period,
            CONFIG.atr_calculation_period,
            CONFIG.volume_ma_period,
        )
        + 10
    )  # Add buffer

    if df is None or len(df) < required_rows:
        logger.warning(
            f"{Fore.YELLOW}Trade Logic: Insufficient data ({len(df) if df is not None else 0}, need ~{required_rows}). Skipping.{Style.RESET_ALL}"
        )
        return

    action_taken_this_cycle: bool = False
    try:
        # === 1. Calculate ALL Indicators ===
        # It's often simpler to calculate all potential indicators needed by any strategy
        # and let the signal generation function pick the ones it needs.
        logger.debug("Calculating indicators...")
        df = calculate_supertrend(df, CONFIG.st_atr_length, CONFIG.st_multiplier)
        df = calculate_supertrend(
            df,
            CONFIG.confirm_st_atr_length,
            CONFIG.confirm_st_multiplier,
            prefix="confirm_",
        )
        df = calculate_stochrsi_momentum(
            df,
            CONFIG.stochrsi_rsi_length,
            CONFIG.stochrsi_stoch_length,
            CONFIG.stochrsi_k_period,
            CONFIG.stochrsi_d_period,
            CONFIG.momentum_length,
        )
        df = calculate_ehlers_fisher(
            df, CONFIG.ehlers_fisher_length, CONFIG.ehlers_fisher_signal_length
        )
        df = calculate_ehlers_ma(
            df, CONFIG.ehlers_fast_period, CONFIG.ehlers_slow_period
        )
        vol_atr_data = analyze_volume_atr(
            df, CONFIG.atr_calculation_period, CONFIG.volume_ma_period
        )
        current_atr = vol_atr_data.get("atr")

        # === 2. Validate Base Requirements ===
        last = df.iloc[-1]
        current_price = safe_decimal_conversion(
            last.get("close")
        )  # Use .get for safety
        if pd.isna(current_price) or current_price <= 0:
            logger.warning(
                f"{Fore.YELLOW}Last candle close price is invalid ({current_price}). Skipping.{Style.RESET_ALL}"
            )
            return
        can_place_order = current_atr is not None and current_atr > Decimal("0")
        if not can_place_order:
            logger.warning(
                f"{Fore.YELLOW}Invalid ATR ({current_atr}). Cannot calculate SL or place new orders.{Style.RESET_ALL}"
            )

        # === 3. Get Position & Analyze OB ===
        position = get_current_position(exchange, symbol)
        position_side = position["side"]
        ob_data = (
            analyze_order_book(
                exchange, symbol, CONFIG.order_book_depth, CONFIG.order_book_fetch_limit
            )
            if CONFIG.fetch_order_book_per_cycle
            else None
        )

        # === 4. Log State ===
        vol_ratio = vol_atr_data.get("volume_ratio")
        vol_spike = vol_ratio is not None and vol_ratio > CONFIG.volume_spike_threshold
        bid_ask_ratio = ob_data.get("bid_ask_ratio") if ob_data else None
        spread = ob_data.get("spread") if ob_data else None

        logger.info(
            f"State | Price: {current_price:.4f}, ATR({CONFIG.atr_calculation_period}): {current_atr:.5f}"
            if current_atr
            else f"State | Price: {current_price:.4f}, ATR({CONFIG.atr_calculation_period}): N/A"
        )
        logger.info(
            f"State | Volume: Ratio={vol_ratio:.2f if vol_ratio else 'N/A'}, Spike={vol_spike} (Req={CONFIG.require_volume_spike_for_entry})"
        )
        # Log specific strategy indicators
        # ... (Add logging for relevant indicators based on CONFIG.strategy_name if needed, or rely on debug logs from calc functions) ...
        logger.info(
            f"State | OrderBook: Ratio={bid_ask_ratio:.3f if bid_ask_ratio else 'N/A'}, Spread={spread:.4f if spread else 'N/A'}"
        )
        logger.info(
            f"State | Position: Side={position_side}, Qty={position['qty']:.8f}, Entry={position['entry_price']:.4f}"
        )

        # === 5. Generate Strategy Signals ===
        strategy_signals = generate_signals(df, CONFIG.strategy_name)
        logger.debug(f"Strategy Signals ({CONFIG.strategy_name}): {strategy_signals}")

        # === 6. Execute Exit Actions ===
        should_exit_long = (
            position_side == CONFIG.pos_long and strategy_signals["exit_long"]
        )
        should_exit_short = (
            position_side == CONFIG.pos_short and strategy_signals["exit_short"]
        )

        if should_exit_long or should_exit_short:
            exit_reason = strategy_signals["exit_reason"]
            logger.warning(
                f"{Back.YELLOW}{Fore.BLACK}*** TRADE EXIT SIGNAL: Closing {position_side} due to {exit_reason} ***{Style.RESET_ALL}"
            )
            cancel_open_orders(exchange, symbol, f"SL/TSL before {exit_reason} Exit")
            close_result = close_position(
                exchange, symbol, position, reason=exit_reason
            )
            if close_result:
                action_taken_this_cycle = True
            # Add delay after closing before allowing new entry
            if action_taken_this_cycle:
                logger.info(
                    f"Pausing for {CONFIG.post_close_delay_seconds}s after closing position..."
                )
                time.sleep(CONFIG.post_close_delay_seconds)
            return  # Exit cycle after attempting close

        # === 7. Check & Execute Entry Actions (Only if Flat & Can Place Order) ===
        if position_side != CONFIG.pos_none:
            logger.info(
                f"Holding {position_side} position. Waiting for SL/TSL or Strategy Exit."
            )
            return
        if not can_place_order:
            logger.warning(
                f"{Fore.YELLOW}Holding Cash. Cannot enter due to invalid ATR for SL calculation.{Style.RESET_ALL}"
            )
            return

        logger.debug("Checking entry signals...")
        # --- Define Confirmation Conditions ---
        potential_entry = (
            strategy_signals["enter_long"] or strategy_signals["enter_short"]
        )
        if (
            not CONFIG.fetch_order_book_per_cycle
            and potential_entry
            and ob_data is None
        ):
            logger.debug("Potential entry signal, fetching OB for confirmation...")
            ob_data = analyze_order_book(
                exchange, symbol, CONFIG.order_book_depth, CONFIG.order_book_fetch_limit
            )
            bid_ask_ratio = (
                ob_data.get("bid_ask_ratio") if ob_data else None
            )  # Update ratio

        # Check OB confirmation only if required
        ob_check_required = potential_entry  # Always check OB if entry signal exists? Or make configurable? Let's assume yes for now.
        ob_available = ob_data is not None and bid_ask_ratio is not None
        passes_long_ob = not ob_check_required or (
            ob_available and bid_ask_ratio >= CONFIG.order_book_ratio_threshold_long
        )
        passes_short_ob = not ob_check_required or (
            ob_available and bid_ask_ratio <= CONFIG.order_book_ratio_threshold_short
        )
        ob_log = f"OB OK (L:{passes_long_ob},S:{passes_short_ob}, Ratio={bid_ask_ratio:.3f if bid_ask_ratio else 'N/A'}, Req={ob_check_required})"

        # Check Volume confirmation only if required
        vol_check_required = CONFIG.require_volume_spike_for_entry
        passes_volume = not vol_check_required or (vol_spike)
        vol_log = f"Vol OK (Pass:{passes_volume}, Spike={vol_spike}, Req={vol_check_required})"

        # --- Combine Strategy Signal with Confirmations ---
        enter_long = strategy_signals["enter_long"] and passes_long_ob and passes_volume
        enter_short = (
            strategy_signals["enter_short"] and passes_short_ob and passes_volume
        )
        logger.debug(
            f"Final Entry Check (Long): Strategy={strategy_signals['enter_long']}, {ob_log}, {vol_log} => Enter={enter_long}"
        )
        logger.debug(
            f"Final Entry Check (Short): Strategy={strategy_signals['enter_short']}, {ob_log}, {vol_log} => Enter={enter_short}"
        )

        # --- Execute ---
        if enter_long:
            logger.success(
                f"{Back.GREEN}{Fore.BLACK}{Style.BRIGHT}*** TRADE SIGNAL: CONFIRMED LONG ENTRY ({CONFIG.strategy_name}) for {symbol} ***{Style.RESET_ALL}"
            )
            cancel_open_orders(
                exchange, symbol, "Before Long Entry"
            )  # Cancel previous SL/TSL just in case
            place_result = place_risked_market_order(
                exchange,
                symbol,
                CONFIG.side_buy,
                CONFIG.risk_per_trade_percentage,
                current_atr,
                CONFIG.atr_stop_loss_multiplier,
                CONFIG.leverage,
                CONFIG.max_order_usdt_amount,
                CONFIG.required_margin_buffer,
                CONFIG.trailing_stop_percentage,
                CONFIG.trailing_stop_activation_offset_percent,
            )
            if place_result:
                action_taken_this_cycle = True

        elif enter_short:
            logger.success(
                f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}*** TRADE SIGNAL: CONFIRMED SHORT ENTRY ({CONFIG.strategy_name}) for {symbol} ***{Style.RESET_ALL}"
            )
            cancel_open_orders(exchange, symbol, "Before Short Entry")
            place_result = place_risked_market_order(
                exchange,
                symbol,
                CONFIG.side_sell,
                CONFIG.risk_per_trade_percentage,
                current_atr,
                CONFIG.atr_stop_loss_multiplier,
                CONFIG.leverage,
                CONFIG.max_order_usdt_amount,
                CONFIG.required_margin_buffer,
                CONFIG.trailing_stop_percentage,
                CONFIG.trailing_stop_activation_offset_percent,
            )
            if place_result:
                action_taken_this_cycle = True

        else:
            if not action_taken_this_cycle:
                logger.info("No confirmed entry signal. Holding cash.")

    except Exception as e:
        logger.error(
            f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}CRITICAL UNEXPECTED ERROR in trade_logic: {e}{Style.RESET_ALL}"
        )
        logger.debug(traceback.format_exc())
        send_sms_alert(
            f"[{symbol.split('/')[0]}] CRITICAL ERROR in trade_logic: {type(e).__name__}"
        )
    finally:
        logger.info(
            f"{Fore.BLUE}{Style.BRIGHT}========== Cycle Check End: {symbol} =========={Style.RESET_ALL}\n"
        )


# --- Graceful Shutdown ---
def graceful_shutdown(exchange: ccxt.Exchange | None, symbol: str | None) -> None:
    """Attempts to close position and cancel orders before exiting."""
    logger.warning(
        f"{Fore.YELLOW}{Style.BRIGHT}Shutdown requested. Initiating graceful exit...{Style.RESET_ALL}"
    )
    market_base = symbol.split("/")[0] if symbol else "Bot"
    send_sms_alert(f"[{market_base}] Shutdown requested. Attempting cleanup...")
    if not exchange or not symbol:
        logger.warning(
            f"{Fore.YELLOW}Shutdown: Exchange/Symbol not available.{Style.RESET_ALL}"
        )
        return

    try:
        # 1. Cancel All Open Orders
        cancel_open_orders(exchange, symbol, reason="Graceful Shutdown")
        time.sleep(1)  # Allow cancellations to process

        # 2. Check and Close Position
        position = get_current_position(exchange, symbol)
        if position["side"] != CONFIG.pos_none:
            logger.warning(
                f"{Fore.YELLOW}Shutdown: Active {position['side']} position found (Qty: {position['qty']:.8f}). Closing...{Style.RESET_ALL}"
            )
            close_result = close_position(exchange, symbol, position, reason="Shutdown")
            if close_result:
                logger.info(
                    f"{Fore.CYAN}Shutdown: Close order placed. Waiting {CONFIG.post_close_delay_seconds * 2}s for confirmation...{Style.RESET_ALL}"
                )
                time.sleep(CONFIG.post_close_delay_seconds * 2)
                # Final check
                final_pos = get_current_position(exchange, symbol)
                if final_pos["side"] == CONFIG.pos_none:
                    logger.success(
                        f"{Fore.GREEN}{Style.BRIGHT}Shutdown: Position confirmed CLOSED.{Style.RESET_ALL}"
                    )
                    send_sms_alert(
                        f"[{market_base}] Position confirmed CLOSED on shutdown."
                    )
                else:
                    logger.error(
                        f"{Back.RED}{Fore.WHITE}Shutdown: FAILED TO CONFIRM closure. Final state: {final_pos['side']} Qty={final_pos['qty']:.8f}{Style.RESET_ALL}"
                    )
                    send_sms_alert(
                        f"[{market_base}] ERROR: Failed confirm closure! Final: {final_pos['side']} Qty={final_pos['qty']:.8f}. MANUAL CHECK!"
                    )
            else:
                logger.error(
                    f"{Back.RED}{Fore.WHITE}Shutdown: Failed to place close order. MANUAL INTERVENTION NEEDED.{Style.RESET_ALL}"
                )
                send_sms_alert(
                    f"[{market_base}] ERROR: Failed PLACE close order on shutdown. MANUAL CHECK!"
                )
        else:
            logger.info(
                f"{Fore.GREEN}Shutdown: No active position found.{Style.RESET_ALL}"
            )
            send_sms_alert(f"[{market_base}] No active position found on shutdown.")
    except Exception as e:
        logger.error(f"{Fore.RED}Shutdown: Error during cleanup: {e}{Style.RESET_ALL}")
        logger.debug(traceback.format_exc())
        send_sms_alert(
            f"[{market_base}] Error during shutdown sequence: {type(e).__name__}"
        )
    logger.info(
        f"{Fore.YELLOW}{Style.BRIGHT}--- Scalping Bot Shutdown Complete ---{Style.RESET_ALL}"
    )


# --- Main Execution ---
def main() -> None:
    """Main function to initialize, set up, and run the trading loop."""
    start_time = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    logger.info(
        f"{Back.BLUE}{Fore.WHITE}{Style.BRIGHT}--- Pyrmethus Bybit Scalping Spell v2.0.1 Initializing ({start_time}) ---{Style.RESET_ALL}"
    )
    logger.info(
        f"{Fore.CYAN}--- Strategy Enchantment: {CONFIG.strategy_name} ---{Style.RESET_ALL}"
    )
    logger.info(
        f"{Fore.GREEN}--- Warding Rune: Initial ATR + Exchange Trailing Stop ---{Style.RESET_ALL}"
    )
    logger.warning(
        f"{Back.YELLOW}{Fore.BLACK}{Style.BRIGHT}--- !!! LIVE FUTURES SCALPING MODE - EXTREME RISK INVOLVED !!! ---{Style.RESET_ALL}"
    )

    exchange: ccxt.Exchange | None = None
    symbol: str | None = None
    run_bot: bool = True
    cycle_count: int = 0

    try:
        # Initialize Exchange
        exchange = initialize_exchange()
        if not exchange:
            return

        # Setup Symbol and Leverage
        try:
            # Allow user input or use default from config
            sym_input = input(
                f"{Fore.YELLOW}Enter symbol {Style.DIM}(Default [{CONFIG.symbol}]){Style.NORMAL}: {Style.RESET_ALL}"
            ).strip()
            symbol_to_use = sym_input or CONFIG.symbol
            market = exchange.market(symbol_to_use)
            symbol = market["symbol"]  # Use the unified symbol from CCXT
            if not market.get("contract"):
                raise ValueError("Not a contract/futures market")
            logger.info(
                f"{Fore.GREEN}Using Symbol: {symbol} (Type: {market.get('type')}){Style.RESET_ALL}"
            )
            if not set_leverage(exchange, symbol, CONFIG.leverage):
                raise RuntimeError("Leverage setup failed")
        except (ccxt.BadSymbol, KeyError, ValueError, RuntimeError) as e:
            logger.critical(f"Symbol/Leverage setup failed: {e}")
            send_sms_alert(
                f"[ScalpBot] CRITICAL: Symbol/Leverage setup FAILED ({e}). Exiting."
            )
            return
        except Exception as e:
            logger.critical(f"Unexpected error during setup: {e}")
            send_sms_alert("[ScalpBot] CRITICAL: Unexpected setup error. Exiting.")
            return

        # Log Config Summary
        logger.info(f"{Fore.MAGENTA}--- Configuration Summary ---{Style.RESET_ALL}")
        logger.info(
            f"{Fore.WHITE}Symbol: {symbol}, Interval: {CONFIG.interval}, Leverage: {CONFIG.leverage}x"
        )
        logger.info(f"{Fore.CYAN}Strategy: {CONFIG.strategy_name}")
        # Log relevant strategy params
        if CONFIG.strategy_name == "DUAL_SUPERTREND":
            logger.info(
                f"  Params: ST={CONFIG.st_atr_length}/{CONFIG.st_multiplier}, ConfirmST={CONFIG.confirm_st_atr_length}/{CONFIG.confirm_st_multiplier}"
            )
        elif CONFIG.strategy_name == "STOCHRSI_MOMENTUM":
            logger.info(
                f"  Params: StochRSI={CONFIG.stochrsi_rsi_length}/{CONFIG.stochrsi_stoch_length}/{CONFIG.stochrsi_k_period}/{CONFIG.stochrsi_d_period} (OB={CONFIG.stochrsi_overbought},OS={CONFIG.stochrsi_oversold}), Mom={CONFIG.momentum_length}"
            )
        elif CONFIG.strategy_name == "EHLERS_FISHER":
            logger.info(
                f"  Params: Fisher={CONFIG.ehlers_fisher_length}, Signal={CONFIG.ehlers_fisher_signal_length}"
            )
        elif CONFIG.strategy_name == "EHLERS_MA_CROSS":
            logger.info(
                f"  Params: FastMA={CONFIG.ehlers_fast_period}, SlowMA={CONFIG.ehlers_slow_period}"
            )
        logger.info(
            f"{Fore.GREEN}Risk: {CONFIG.risk_per_trade_percentage:.3%}/trade, MaxPosValue: {CONFIG.max_order_usdt_amount:.4f} USDT"
        )
        logger.info(
            f"{Fore.GREEN}Initial SL: {CONFIG.atr_stop_loss_multiplier} * ATR({CONFIG.atr_calculation_period})"
        )
        logger.info(
            f"{Fore.GREEN}Trailing SL: {CONFIG.trailing_stop_percentage:.2%}, Activation Offset: {CONFIG.trailing_stop_activation_offset_percent:.2%}"
        )
        logger.info(
            f"{Fore.YELLOW}Vol Confirm: {CONFIG.require_volume_spike_for_entry} (MA={CONFIG.volume_ma_period}, Thr={CONFIG.volume_spike_threshold})"
        )
        logger.info(
            f"{Fore.YELLOW}OB Confirm: {CONFIG.fetch_order_book_per_cycle} (Depth={CONFIG.order_book_depth}, L>={CONFIG.order_book_ratio_threshold_long}, S<={CONFIG.order_book_ratio_threshold_short})"
        )
        logger.info(
            f"{Fore.WHITE}Sleep: {CONFIG.sleep_seconds}s, Margin Buffer: {CONFIG.required_margin_buffer:.1%}, SMS: {CONFIG.enable_sms_alerts}"
        )
        logger.info(f"{Fore.CYAN}Logging Level: {logging.getLevelName(logger.level)}")
        logger.info(f"{Fore.MAGENTA}{'-' * 30}{Style.RESET_ALL}")
        market_base = symbol.split("/")[0]
        send_sms_alert(
            f"[{market_base}] Bot configured ({CONFIG.strategy_name}). SL: ATR+TSL. Starting loop."
        )

        # Main Trading Loop
        while run_bot:
            cycle_start_time = time.monotonic()
            cycle_count += 1
            logger.debug(
                f"{Fore.CYAN}--- Cycle {cycle_count} Start ---{Style.RESET_ALL}"
            )
            try:
                # Determine required data length based on longest possible indicator lookback
                data_limit = (
                    max(
                        100,
                        CONFIG.st_atr_length * 2,
                        CONFIG.confirm_st_atr_length * 2,
                        CONFIG.stochrsi_rsi_length + CONFIG.stochrsi_stoch_length + 5,
                        CONFIG.momentum_length * 2,
                        CONFIG.ehlers_fisher_length * 2,
                        CONFIG.ehlers_fisher_signal_length * 2,
                        CONFIG.ehlers_fast_period * 2,
                        CONFIG.ehlers_slow_period * 2,
                        CONFIG.atr_calculation_period * 2,
                        CONFIG.volume_ma_period * 2,
                    )
                    + CONFIG.api_fetch_limit_buffer
                )

                df = get_market_data(
                    exchange, symbol, CONFIG.interval, limit=data_limit
                )

                if df is not None and not df.empty:
                    trade_logic(
                        exchange, symbol, df.copy()
                    )  # Pass copy to avoid modifying original in logic
                else:
                    logger.warning(
                        f"{Fore.YELLOW}No valid market data for {symbol}. Skipping cycle.{Style.RESET_ALL}"
                    )

            # --- Robust Error Handling ---
            except ccxt.RateLimitExceeded as e:
                logger.warning(
                    f"{Back.YELLOW}{Fore.BLACK}Rate Limit Exceeded: {e}. Sleeping longer...{Style.RESET_ALL}"
                )
                time.sleep(CONFIG.sleep_seconds * 5)
                send_sms_alert(f"[{market_base}] WARNING: Rate limit hit!")
            except ccxt.NetworkError as e:
                logger.warning(
                    f"{Fore.YELLOW}Network error: {e}. Retrying next cycle.{Style.RESET_ALL}"
                )
                time.sleep(
                    CONFIG.sleep_seconds
                )  # Standard sleep on recoverable network errors
            except ccxt.ExchangeNotAvailable as e:
                logger.error(
                    f"{Back.RED}{Fore.WHITE}Exchange unavailable: {e}. Sleeping much longer...{Style.RESET_ALL}"
                )
                time.sleep(CONFIG.sleep_seconds * 10)
                send_sms_alert(f"[{market_base}] ERROR: Exchange unavailable!")
            except ccxt.AuthenticationError as e:
                logger.critical(
                    f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}Authentication Error: {e}. Stopping NOW.{Style.RESET_ALL}"
                )
                run_bot = False
                send_sms_alert(
                    f"[{market_base}] CRITICAL: Authentication Error! Stopping NOW."
                )
            except ccxt.ExchangeError as e:  # Catch broader exchange errors
                logger.error(
                    f"{Fore.RED}Unhandled Exchange error: {e}{Style.RESET_ALL}"
                )
                logger.debug(traceback.format_exc())
                send_sms_alert(
                    f"[{market_base}] ERROR: Unhandled Exchange error: {type(e).__name__}"
                )
                time.sleep(
                    CONFIG.sleep_seconds
                )  # Sleep before retrying after general exchange error
            except Exception as e:
                logger.exception(
                    f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}!!! UNEXPECTED CRITICAL ERROR: {e} !!!{Style.RESET_ALL}"
                )
                run_bot = False
                send_sms_alert(
                    f"[{market_base}] CRITICAL UNEXPECTED ERROR: {type(e).__name__}! Stopping NOW."
                )

            # --- Loop Delay ---
            if run_bot:
                elapsed = time.monotonic() - cycle_start_time
                sleep_dur = max(0, CONFIG.sleep_seconds - elapsed)
                logger.debug(
                    f"Cycle {cycle_count} time: {elapsed:.2f}s. Sleeping: {sleep_dur:.2f}s."
                )
                if sleep_dur > 0:
                    time.sleep(sleep_dur)

    except KeyboardInterrupt:
        logger.warning(
            f"{Fore.YELLOW}{Style.BRIGHT}KeyboardInterrupt received. Arcane energies withdrawing...{Style.RESET_ALL}"
        )
        run_bot = False  # Ensure loop terminates
    finally:
        # --- Graceful Shutdown ---
        graceful_shutdown(exchange, symbol)
        market_base_final = symbol.split("/")[0] if symbol else "Bot"
        send_sms_alert(f"[{market_base_final}] Bot process terminated.")
        logger.info(
            f"{Back.BLUE}{Fore.WHITE}{Style.BRIGHT}--- Pyrmethus Scalping Spell Deactivated ---{Style.RESET_ALL}"
        )


if __name__ == "__main__":
    main()
