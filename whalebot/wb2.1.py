import json
import logging
import os
import random
import sys
import time
import threading
from datetime import datetime, timezone, timedelta
from decimal import ROUND_DOWN, Decimal, getcontext, InvalidOperation
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Literal, Optional, Tuple, Dict, List, Callable

import numpy as np
import pandas as pd
import websocket
import traceback

# --- Guarded Import for Pybit ---
try:
    from pybit.unified_trading import HTTP as PybitHTTP
    import pybit.exceptions
    PYBIT_AVAILABLE = True
except ImportError:
    PYBIT_AVAILABLE = False

from colorama import Fore, Style, init
from dotenv import load_dotenv

# --- Custom Modules ---
try:
    import indicators
except ImportError:
    logging.basicConfig(level=logging.ERROR)
    logger_mod_err = logging.getLogger(__name__)
    logger_mod_err.error("indicators.py not found. Please ensure it's in the same directory or accessible via PYTHONPATH.")
    sys.exit(1)

try:
    from alert_system import AlertSystem
except ImportError:
    logging.basicConfig(level=logging.ERROR)
    logger_mod_err = logging.getLogger(__name__)
    logger_mod_err.error("alert_system.py not found. Please ensure it's in the same directory or accessible via PYTHONPATH.")
    sys.exit(1)

# --- Initialization ---
getcontext().prec = 28  # Set Decimal precision globally
init(autoreset=True) # Initialize Colorama

# Load environment variables from .env file
script_dir = Path(__file__).resolve().parent
dotenv_path = script_dir / '.env'
load_dotenv(dotenv_path=dotenv_path)

# --- Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
# Base URL for REST API will be determined by PybitHTTP client's testnet flag
# WS_URL is now specific to public/private streams and derived dynamically if needed for authentication
CONFIG_FILE = "config.json"
STATE_FILE = "bot_state.json"
LOG_DIRECTORY = "bot_logs/trading-bot/logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

TIMEZONE = timezone.utc
MAX_API_RETRIES = 5
RETRY_DELAY_SECONDS = 7
REQUEST_TIMEOUT = 20
LOOP_DELAY_SECONDS = 15
HEARTBEAT_INTERVAL_MS = 5000
EXECUTION_POLL_INTERVAL_MS = 2500

# Magic Numbers for Indicators & Logic
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20
STOCH_RSI_MID_POINT = 50
MIN_CANDLESTICK_PATTERNS_BARS = 2

# Color Palette
NEON_GREEN, NEON_BLUE, NEON_PURPLE, NEON_YELLOW, NEON_RED, NEON_CYAN = Fore.LIGHTGREEN_EX, Fore.CYAN, Fore.MAGENTA, Fore.YELLOW, Fore.LIGHTRED_EX, Fore.CYAN
RESET = Style.RESET_ALL

# Indicator Colors (mapping for display)
INDICATOR_COLORS = {
    "SMA_10": NEON_BLUE, "SMA_Long": Fore.BLUE, "EMA_Short": NEON_PURPLE,
    "EMA_Long": Fore.MAGENTA, "ATR": NEON_YELLOW, "RSI": NEON_GREEN, "StochRSI_K": NEON_CYAN,
    "StochRSI_D": Fore.LIGHTCYAN_EX, "BB_Upper": NEON_RED, "BB_Middle": Fore.WHITE,
    "BB_Lower": NEON_RED, "CCI": NEON_GREEN, "WR": NEON_RED, "MFI": NEON_GREEN,
    "OBV": Fore.BLUE, "OBV_EMA": NEON_BLUE, "CMF": NEON_PURPLE, "Tenkan_Sen": NEON_CYAN,
    "Kijun_Sen": Fore.LIGHTCYAN_EX, "Senkou_Span_A": NEON_GREEN, "Senkou_Span_B": NEON_RED,
    "Chikou_Span": NEON_YELLOW, "PSAR_Val": NEON_PURPLE, "PSAR_Dir": Fore.LIGHTMAGENTA_EX,
    "VWAP": Fore.WHITE, "ST_Fast_Dir": Fore.BLUE, "ST_Fast_Val": NEON_BLUE,
    "ST_Slow_Dir": NEON_PURPLE, "ST_Slow_Val": Fore.LIGHTMAGENTA_EX, "MACD_Line": NEON_GREEN,
    "MACD_Signal": Fore.LIGHTGREEN_EX, "MACD_Hist": NEON_YELLOW, "ADX": NEON_CYAN,
    "PlusDI": Fore.LIGHTCYAN_EX, "MinusDI": NEON_RED, "Volatility_Index": NEON_YELLOW,
    "Volume_Delta": Fore.LIGHTCYAN_EX, "VWMA": Fore.WHITE, "Kaufman_AMA": NEON_GREEN,
    "Relative_Volume": NEON_PURPLE, "Market_Structure_Trend": Fore.LIGHTCYAN_EX,
    "DEMA": Fore.BLUE, "Keltner_Upper": NEON_PURPLE, "Keltner_Middle": Fore.WHITE,
    "Keltner_Lower": NEON_PURPLE, "ROC": NEON_GREEN, "Pivot": Fore.WHITE,
    "R1": NEON_CYAN, "R2": Fore.LIGHTCYAN_EX, "S1": NEON_PURPLE, "S2": Fore.LIGHTMAGENTA_EX,
    "Candlestick_Pattern": Fore.LIGHTYELLOW_EX, "Support_Level": NEON_CYAN,
    "Resistance_Level": NEON_RED,
}

# --- Global Logger Instance ---
# Logger will be properly configured in setup_logger called by main()
global_logger = logging.getLogger("whalebot")

# --- Helper Functions for Precision and Safety ---
def round_qty(qty: Decimal, qty_step: Decimal) -> Decimal:
    """Rounds quantity down to the nearest multiple of qty_step."""
    if qty_step is None or qty_step.is_zero():
        return qty.quantize(Decimal("1e-6"), rounding=ROUND_DOWN) # Default to 6 decimal places
    return (qty // qty_step) * qty_step

def round_price(price: Decimal, price_precision: int) -> Decimal:
    """Rounds price to the correct number of decimal places."""
    if price_precision < 0: price_precision = 0
    return price.quantize(Decimal(f"1e-{price_precision}"), rounding=ROUND_DOWN)

def _safe_divide_decimal(numerator: Decimal, denominator: Decimal, default: Decimal = Decimal("0")) -> Decimal:
    """Safely divides two Decimals, returning default on zero/NaN denominator or InvalidOperation."""
    try:
        if denominator.is_zero() or denominator.is_nan() or numerator.is_nan():
            return default
        return numerator / denominator
    except InvalidOperation:
        return default

def _clean_series(series: Optional[pd.Series], df_index: pd.Index, default_val: Any = np.nan) -> pd.Series:
    """Cleans a Pandas Series: re-indexes, handles NaNs, and returns as Series."""
    if series is None:
        return pd.Series(default_val, index=df_index)
    
    cleaned = series.reindex(df_index) # Align with original DataFrame index
    if not pd.isna(default_val):
        cleaned = cleaned.fillna(default_val) # Fill NaNs if a default is specified
    return cleaned

# --- Configuration Management ---
def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    """Loads config from JSON, creates default if missing, ensures all keys exist."""
    default_config = {
        "symbol": "BTCUSDT", "interval": "15", "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50, "signal_score_threshold": 2.0, "cooldown_sec": 60,
        "hysteresis_ratio": 0.85, "volume_confirmation_multiplier": 1.5,
        "trade_management": {
            "enabled": True, "account_balance": 1000.0, "risk_per_trade_percent": 1.0,
            "stop_loss_atr_multiple": 1.5, "take_profit_atr_multiple": 2.0,
            "max_open_positions": 1, "order_precision": 5, "price_precision": 3,
            "slippage_percent": 0.001, "trading_fee_percent": 0.0005,
        },
        "risk_guardrails": {
            "enabled": True, "max_day_loss_pct": 3.0, "max_drawdown_pct": 8.0,
            "cooldown_after_kill_min": 120, "spread_filter_bps": 5.0, "ev_filter_enabled": True,
        },
        "session_filter": {
            "enabled": False, "utc_allowed": [["00:00", "08:00"], ["13:00", "20:00"]],
        },
        "pyramiding": {
            "enabled": False, "max_adds": 2, "step_atr": 0.7, "size_pct_of_initial": 0.5,
        },
        "mtf_analysis": {
            "enabled": True, "higher_timeframes": ["60", "240"],
            "trend_indicators": ["ema", "ehlers_supertrend"], "trend_period": 50,
            "mtf_request_delay_seconds": 0.5,
        },
        "ml_enhancement": {"enabled": False},
        "indicator_settings": {
            "atr_period": 14, "ema_short_period": 9, "ema_long_period": 21, "rsi_period": 14,
            "stoch_rsi_period": 14, "stoch_k_period": 3, "stoch_d_period": 3,
            "bollinger_bands_period": 20, "bollinger_bands_std_dev": 2.0, "cci_period": 20,
            "williams_r_period": 14, "mfi_period": 14, "psar_acceleration": 0.02,
            "psar_max_acceleration": 0.2, "sma_short_period": 10, "sma_long_period": 50,
            "fibonacci_window": 60, "ehlers_fast_period": 10, "ehlers_fast_multiplier": 2.0,
            "ehlers_slow_period": 20, "ehlers_slow_multiplier": 3.0, "macd_fast_period": 12,
            "macd_slow_period": 26, "macd_signal_period": 9, "adx_period": 14,
            "ichimoku_tenkan_period": 9, "ichimoku_kijun_period": 26,
            "ichimoku_senkou_span_b_period": 52, "ichimoku_chikou_span_offset": 26,
            "obv_ema_period": 20, "cmf_period": 20, "rsi_oversold": 30, "rsi_overbought": 70,
            "stoch_rsi_oversold": 20, "stoch_rsi_overbought": 80, "cci_oversold": -100,
            "cci_overbought": 100, "williams_r_oversold": -80, "williams_r_overbought": -20,
            "mfi_oversold": 20, "mfi_overbought": 80, "volatility_index_period": 20,
            "vwma_period": 20, "volume_delta_period": 5, "volume_delta_threshold": 0.2,
            "kama_period": 10, "kama_fast_period": 2, "kama_slow_period": 30,
            "relative_volume_period": 20, "relative_volume_threshold": 1.5,
            "market_structure_lookback_period": 20, "dema_period": 14,
            "keltner_period": 20, "keltner_atr_multiplier": 2.0, "roc_period": 12,
            "roc_oversold": -5.0, "roc_overbought": 5.0,
        },
        "indicators": { # Flags to enable/disable indicators
            "atr": True, "ema_alignment": True, "sma_trend_filter": True, "momentum": True,
            "volume_confirmation": True, "stoch_rsi": True, "rsi": True, "bollinger_bands": True,
            "vwap": True, "cci": True, "wr": True, "psar": True, "sma_10": True, "mfi": True,
            "orderbook_imbalance": True, "fibonacci_levels": True, "ehlers_supertrend": True,
            "macd": True, "adx": True, "ichimoku_cloud": True, "obv": True, "cmf": True,
            "volatility_index": True, "vwma": True, "volume_delta": True,
            "kaufman_ama": True, "relative_volume": True, "market_structure": True,
            "dema": True, "keltner_channels": True, "roc": True, "candlestick_patterns": True,
            "fibonacci_pivot_points": True,
        },
        "weight_sets": { # Weights for scoring indicators
            "default_scalping": {
                "ema_alignment": 0.30, "sma_trend_filter": 0.20, "ehlers_supertrend_alignment": 0.40,
                "macd_alignment": 0.30, "adx_strength": 0.25, "ichimoku_confluence": 0.35,
                "psar": 0.15, "vwap": 0.15, "vwma_cross": 0.10, "sma_10": 0.05,
                "bollinger_bands": 0.25, "momentum_rsi_stoch_cci_wr_mfi": 0.35,
                "volume_confirmation": 0.10, "obv_momentum": 0.15, "cmf_flow": 0.10,
                "volume_delta_signal": 0.10, "orderbook_imbalance": 0.10,
                "mtf_trend_confluence": 0.25, "volatility_index_signal": 0.10,
                "kaufman_ama_cross": 0.20, "relative_volume_confirmation": 0.10,
                "market_structure_confluence": 0.25, "dema_crossover": 0.18,
                "keltner_breakout": 0.20, "roc_signal": 0.12, "candlestick_confirmation": 0.15,
                "fibonacci_pivot_points_confluence": 0.20,
            }
        },
        "execution": { # Execution parameters for live trading
            "use_pybit": False, "testnet": False, "account_type": "UNIFIED", "category": "linear",
            "position_mode": "ONE_WAY", "tpsl_mode": "Partial", "buy_leverage": "3",
            "sell_leverage": "3", "tp_trigger_by": "LastPrice", "sl_trigger_by": "LastPrice",
            "default_time_in_force": "GoodTillCancel", "reduce_only_default": False,
            "post_only_default": False,
            "position_idx_overrides": {"ONE_WAY": 0, "HEDGE_BUY": 1, "HEDGE_SELL": 2},
            "proxies": { # Proxies handled in PybitHTTP client init
                "enabled": False, "http": "", "https": ""
            },
            "tp_scheme": { # Take Profit order structure
                "mode": "atr_multiples",
                "targets": [
                    {"name": "TP1", "atr_multiple": 1.0, "size_pct": 0.40, "order_type": "Limit", "tif": "PostOnly", "post_only": True},
                    {"name": "TP2", "atr_multiple": 1.5, "size_pct": 0.40, "order_type": "Limit", "tif": "IOC", "post_only": False},
                    {"name": "TP3", "atr_multiple": 2.0, "size_pct": 0.20, "order_type": "Limit", "tif": "GoodTillCancel", "post_only": False},
                ],
            },
            "sl_scheme": { # Stop Loss order structure
                "type": "atr_multiple", "atr_multiple": 1.5, "percent": 1.0,
                "use_conditional_stop": True, "stop_order_type": "Market",
            },
            "breakeven_after_tp1": { # Breakeven logic settings
                "enabled": True, "offset_type": "atr", "offset_value": 0.10,
                "lock_in_min_percent": 0, "sl_trigger_by": "LastPrice",
            },
            "live_sync": { # Settings for live trading synchronization
                "enabled": True, "poll_ms": EXECUTION_POLL_INTERVAL_MS, "max_exec_fetch": 200,
                "only_track_linked": True, "heartbeat": {"enabled": True, "interval_ms": HEARTBEAT_INTERVAL_MS},
            },
        },
        # Transient state variables (managed at runtime, saved if necessary)
        "_last_score": 0.0,
        "_last_signal_ts": 0,
        "_last_atr_value": "0.1",
    }
    
    # Create config file if it doesn't exist
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(f"{NEON_YELLOW}Created default config at {filepath}{RESET}")
            return default_config
        except OSError as e:
            logger.error(f"{NEON_RED}Error creating default config file: {e}{RESET}")
            return default_config # Return default if creation fails
            
    # Load existing config and merge with defaults
    try:
        with Path(filepath).open("r", encoding="utf-8") as f:
            config = json.load(f)
        _ensure_config_keys(config, default_config) # Ensure all keys are present
        # Save the merged config back to ensure consistency
        with Path(filepath).open("w", encoding="utf-8") as f_write:
            json.dump(config, f_write, indent=4)
        logger.info(f"Configuration loaded and updated from {filepath}")
        return config
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"{NEON_RED}Error loading config file '{filepath}': {e}. Using default configuration.{RESET}")
        return default_config # Fallback to default if loading fails

def _ensure_config_keys(config: dict[str, Any], default_config: dict[str, Any]) -> None:
    """Recursively ensures all keys from default_config exist in config."""
    for key, default_value in default_config.items():
        if key not in config:
            config[key] = default_value
        elif isinstance(default_value, dict) and isinstance(config.get(key), dict):
            # Recurse into nested dictionaries
            _ensure_config_keys(config[key], default_value)

# --- Logging Setup ---
class SensitiveFormatter(logging.Formatter):
    """Custom formatter to redact sensitive information in logs."""
    SENSITIVE_WORDS: ClassVar[list[str]] = ["API_KEY", "API_SECRET"]

    def format(self, record):
        original_message = super().format(record)
        # Redact sensitive words
        for word in self.SENSITIVE_WORDS:
            if word in original_message:
                original_message = original_message.replace(word, "*" * len(word))
        return original_message

def setup_logger(log_name: str, level=logging.INFO) -> logging.Logger:
    """Configures and returns a logger instance with console and file handlers."""
    logger = logging.getLogger(log_name)
    if not logger.handlers: # Avoid duplicate handlers
        logger.setLevel(level)
        logger.propagate = False # Prevent logs from propagating to root logger

        # Console Handler with sensitive formatting
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(SensitiveFormatter(f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}"))
        logger.addHandler(console_handler)

        # File Handler with rotation and sensitive formatting
        log_file = Path(LOG_DIRECTORY) / f"{log_name}.log"
        file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)
        file_handler.setFormatter(SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(file_handler)
    return logger

# --- Pybit Trading Client ---
class PybitTradingClient:
    """Manages REST API interactions with Bybit, including WebSocket client setup."""
    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.cfg = config
        self.logger = logger
        self.enabled = bool(config.get("execution", {}).get("use_pybit", False))
        self.category = config.get("execution", {}).get("category", "linear")
        self.testnet = bool(config.get("execution", {}).get("testnet", False))

        self.session: Optional[PybitHTTP] = None # REST client instance
        self.ws_manager: Optional[WebSocketManager] = None # WebSocket manager instance
        self.stop_event = threading.Event() # Shared event for stopping threads
        self.state_data: Dict = {} # Holds loaded state data

        if not self.enabled:
            self.logger.info(f"{NEON_YELLOW}PyBit execution disabled in config.{RESET}")
            return
        if not PYBIT_AVAILABLE:
            self.enabled = False; self.logger.error(f"{NEON_RED}PyBit library not found. Please install it: pip install pybit.{RESET}")
            return
        if not API_KEY or not API_SECRET:
            self.enabled = False; self.logger.error(f"{NEON_RED}API keys (BYBIT_API_KEY, BYBIT_API_SECRET) not set in .env.{RESET}")
            return

        # Prepare proxies if enabled in config
        proxies = {}
        proxy_conf = self.cfg.get("execution", {}).get("proxies", {})
        if proxy_conf.get("enabled", False):
            if proxy_conf.get("http"): proxies["http"] = proxy_conf["http"]
            if proxy_conf.get("https"): proxies["https"] = proxy_conf["https"]
            if proxies: self.logger.info(f"{NEON_BLUE}Using proxies: {proxies}.{RESET}")
            else: self.logger.warning(f"{NEON_YELLOW}Proxy enabled but no URLs provided.{RESET}")

        try:
            # Initialize PybitHTTP client - removed `base_url` argument as it's handled by `testnet` flag
            self.session = PybitHTTP(
                api_key=API_KEY, api_secret=API_SECRET,
                testnet=self.testnet, # Controls mainnet/testnet URL
                timeout=REQUEST_TIMEOUT,
                proxies=proxies if proxies else None # Pass proxies if configured
            )
            actual_base_url = self.session.base_url if self.session else "N/A"
            self.logger.info(f"{NEON_GREEN}PyBit HTTP client initialized. Testnet={self.testnet}, Base URL={actual_base_url}{RESET}")
            
            self._initialize_websocket() # Initialize WebSocket manager
        except (pybit.exceptions.FailedRequestError, TypeError, Exception) as e:
            self.enabled = False # Disable client if initialization fails
            self.logger.error(f"{NEON_RED}Failed to initialize PyBit client: {e}\n{traceback.format_exc()}{RESET}")
            self.session = None # Ensure session is None on failure

    # --- Utility Methods ---
    def _log_api(self, action: str, resp: dict | None, log_level: str = "error"):
        """Logs API response status using specified level."""
        if not resp:
            getattr(self.logger, log_level)(f"{NEON_RED}{action}: No response received.{RESET}")
            return
        if not self._ok(resp):
            getattr(self.logger, log_level)(f"{NEON_RED}{action}: Failed with code {resp.get('retCode')} - {resp.get('retMsg')}{RESET}")

    def _ok(self, resp: dict | None) -> bool:
        """Checks if API response indicates success (retCode == 0)."""
        return bool(resp and resp.get("retCode") == 0)
    
    def _q(self, x: Any) -> str: return str(x) # Helper to convert value to string for API params

    def _side_to_bybit(self, side: str) -> Literal["Buy", "Sell"]:
        """Converts internal BUY/SELL to Bybit's 'Buy'/'Sell'."""
        return "Buy" if side == "BUY" else "Sell"

    def _pos_idx(self, side: str) -> Literal[0, 1, 2]:
        """Returns positionIdx for Bybit, considering ONE_WAY vs HEDGE mode."""
        pos_mode = self.cfg["execution"].get("position_mode", "ONE_WAY")
        if pos_mode == "ONE_WAY": return 0
        return self.cfg["execution"]["position_idx_overrides"].get(f"HEDGE_{side}", 0)

    def _handle_403_error(self, e: Exception):
        """Specifically handles 403 Forbidden errors for API calls."""
        if isinstance(e, pybit.exceptions.FailedRequestError) and e.status_code == 403:
            self.logger.error(f"{NEON_RED}API Error 403 Forbidden: Check API key permissions and IP whitelist settings on Bybit. Disabling Pybit client temporarily.{RESET}")
            self.enabled = False # Temporarily disable to prevent spamming
            self.stop_event.set() # Signal shutdown for other components as well

    # --- REST API Methods ---
    def set_leverage(self, symbol: str, buy: str, sell: str) -> bool:
        if not self.enabled or not self.session: return False
        try:
            resp = self.session.set_leverage(category=self.category, symbol=symbol, buyLeverage=self._q(buy), sellLeverage=self._q(sell))
            self._log_api("set_leverage", resp, "debug")
            return self._ok(resp)
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(f"set_leverage failed for {symbol}: {e}\n{traceback.format_exc()}")
            self._handle_403_error(e)
            return False

    def get_positions(self, symbol: str | None = None) -> dict | None:
        if not self.enabled or not self.session: return None
        try:
            params = {"category": self.category}
            if symbol: params["symbol"] = symbol
            resp = self.session.get_positions(**params)
            self._log_api("get_positions", resp, "debug")
            return resp
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"get_positions exception: {e}\n{traceback.format_exc()}")
            self._handle_403_error(e)
            return None
            
    def get_wallet_balance(self, coin: str = "USDT") -> dict | None:
        if not self.enabled or not self.session: return None
        try:
            resp = self.session.get_wallet_balance(accountType=self.cfg["execution"]["account_type"], coin=coin)
            self._log_api("get_wallet_balance", resp, "debug")
            return resp
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"get_wallet_balance exception: {e}\n{traceback.format_exc()}")
            self._handle_403_error(e)
            return None

    def place_order(self, **kwargs) -> dict | None:
        if not self.enabled or not self.session: return None
        try:
            resp = self.session.place_order(category=self.category, **kwargs)
            self._log_api("place_order", resp)
            return resp
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"place_order exception: {e}\n{traceback.format_exc()}")
            self._handle_403_error(e)
            return None
            
    def batch_place_orders(self, orders: List[Dict]) -> dict | None:
        """Places multiple orders in a single batch request."""
        if not self.enabled or not self.session: return None
        if not orders: return {"retCode": 0, "retMsg": "No orders to place."}
        try:
            # Ensure each order in the batch has 'category' for unified trading
            for order in orders:
                if "category" not in order: order["category"] = self.category
            resp = self.session.batch_place_orders(request=orders)
            self._log_api("batch_place_orders", resp)
            return resp
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"batch_place_orders exception: {e}\n{traceback.format_exc()}")
            self._handle_403_error(e)
            return None

    def cancel_order(self, symbol: str, order_id: str | None = None, order_link_id: str | None = None) -> dict | None:
        if not self.enabled or not self.session: return None
        try:
            params = {"category": self.category, "symbol": symbol}
            if order_id: params["orderId"] = order_id
            elif order_link_id: params["orderLinkId"] = order_link_id
            else:
                self.logger.warning("No orderId or orderLinkId provided for cancel_order.")
                return None
            resp = self.session.cancel_order(**params)
            self._log_api("cancel_order", resp, "debug")
            return resp
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"cancel_order exception for {symbol}: {e}\n{traceback.format_exc()}")
            self._handle_403_error(e)
            return None

    def get_open_orders(self, symbol: str | None = None) -> List[Dict]:
        if not self.enabled or not self.session: return []
        try:
            params = {"category": self.category, "openOnly": 0} # 0 for all active orders, 1 for open only
            if symbol: params["symbol"] = symbol
            resp = self.session.get_open_orders(**params)
            self._log_api("get_open_orders", resp, "debug")
            if self._ok(resp) and resp.get("result", {}).get("list"):
                return resp["result"]["list"]
            return []
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"get_open_orders exception: {e}\n{traceback.format_exc()}")
            self._handle_403_error(e)
            return []

    def fetch_current_price(self, symbol: str) -> Decimal | None:
        if not self.enabled or not self.session: return None
        try:
            params = {"category": self.category, "symbol": symbol}
            response = self.session.get_tickers(**params)
            if self._ok(response) and response.get("result", {}).get("list"):
                price = Decimal(response["result"]["list"][0]["lastPrice"])
                return price
            self.logger.warning(f"Could not fetch current price for {symbol}. Response: {response}")
            return None
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"fetch_current_price exception for {symbol}: {e}\n{traceback.format_exc()}")
            self._handle_403_error(e)
            return None

    def fetch_klines(self, symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
        if not self.enabled or not self.session: return None
        try:
            resp = self.session.get_kline(category=self.category, symbol=symbol, interval=interval, limit=limit)
            if self._ok(resp) and resp.get("result", {}).get("list"):
                df = pd.DataFrame(resp["result"]["list"], columns=["start", "open", "high", "low", "close", "volume", "turnover"])
                df["start"] = pd.to_datetime(df["start"], unit="ms")
                df = df.set_index("start")
                for col in ["open", "high", "low", "close", "volume", "turnover"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df.dropna(inplace=True) # Drop rows with any NaN values after conversion
                return df
            self.logger.warning(f"Failed to fetch klines for {symbol} {interval}. Response: {resp}")
            return None
        except (pybit.exceptions.FailedRequestError, KeyError, ValueError) as e:
            self.logger.error(f"fetch_klines exception for {symbol} {interval}: {e}\n{traceback.format_exc()}")
            self._handle_403_error(e)
            return None

    def fetch_orderbook(self, symbol: str, limit: int) -> dict | None:
        if not self.enabled or not self.session: return None
        try:
            resp = self.session.get_orderbook(category=self.category, symbol=symbol, limit=limit)
            if self._ok(resp) and resp.get("result"):
                return resp["result"]
            self.logger.warning(f"Failed to fetch orderbook for {symbol}. Response: {resp}")
            return None
        except (pybit.exceptions.FailedRequestError, KeyError) as e:
            self.logger.error(f"fetch_orderbook exception for {symbol}: {e}\n{traceback.format_exc()}")
            self._handle_403_error(e)
            return None

    def fetch_instrument_info(self, symbol: str) -> dict | None:
        if not self.enabled or not self.session: return None
        try:
            resp = self.session.get_instruments_info(category=self.category, symbol=symbol)
            if self._ok(resp) and resp.get("result", {}).get("list"):
                return resp["result"]["list"][0]
            self.logger.warning(f"Failed to fetch instrument info for {symbol}. Response: {resp}")
            return None
        except (pybit.exceptions.FailedRequestError, KeyError) as e:
            self.logger.error(f"fetch_instrument_info exception for {symbol}: {e}\n{traceback.format_exc()}")
            self._handle_403_error(e)
            return None

    def get_executions(self, symbol: str, start_time_ms: int, limit: int) -> dict | None:
        if not self.enabled or not self.session: return None
        try:
            resp = self.session.get_executions(category=self.category, symbol=symbol, startTime=start_time_ms, limit=limit)
            self._log_api("get_executions", resp, "debug")
            return resp
        except pybit.exceptions.FailedRequestError as e:
            self.logger.error(f"get_executions exception: {e}\n{traceback.format_exc()}")
            self._handle_403_error(e)
            return None

    def get_private_url(self) -> dict | None:
        """Fetches the listen key required for user data WebSocket streams."""
        if not self.enabled or not self.session: return None
        try:
            # Pybit unified trading API does not use a "listenKey" in the same way as some other exchanges.
            # User data streams are authenticated directly through a signed request upon connection.
            # The Pybit client handles this internally. This method is a placeholder if a specific endpoint
            # for "user stream" listen key were to be introduced or for compatibility.
            # For the unified trading WS, authentication is part of the `subscribe` message or initial connection.
            # Returning a dummy structure or adjusting based on Pybit's actual authentication mechanism.
            self.logger.debug("Pybit unified trading WebSocket authentication typically uses signed messages, not a separate 'listenKey' endpoint.")
            # If the Pybit library has an equivalent for a 'user stream URL' or token, implement it here.
            # For now, return a placeholder that the WS manager can handle if it expects a specific format.
            return {"retCode": 0, "result": {"listenKey": "dummy_listen_key_pybit"}} # Placeholder
        except Exception as e:
            self.logger.error(f"get_private_url (placeholder) exception: {e}\n{traceback.format_exc()}")
            self._handle_403_error(e)
            return None

    # --- WebSocket Management ---
    def _initialize_websocket(self):
        """Initializes and starts the WebSocket Manager."""
        if not self.enabled: return
        try:
            # Pass config, logger, and stop_event to WebSocketManager
            self.ws_manager = WebSocketManager(self, self.cfg, self.logger)
            self.ws_manager.start() # Start the WS thread
        except Exception as e:
            self.logger.error(f"Failed to initialize WebSocket Manager: {e}\n{traceback.format_exc()}")

    def shutdown(self):
        """Initiates shutdown sequence for client and its components."""
        self.stop_event.set()
        if self.ws_manager:
            self.ws_manager.shutdown()
        self.save_state() # Save state before exiting
        self.logger.info("PybitTradingClient shutdown complete.")

    def save_state(self):
        """Saves current bot state (positions, orders, last exec time)."""
        state_data = {
            "positions": self.ws_manager.positions if self.ws_manager else {},
            "orders": self.ws_manager.orders if self.ws_manager else {},
            "last_exec_time_ms": self.ws_manager.last_exec_time_ms if self.ws_manager else 0,
            # Performance tracker state is managed by PerformanceTracker itself
        }
        try:
            with Path(STATE_FILE).open("w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=4)
            self.logger.info(f"{NEON_GREEN}Bot state saved to {STATE_FILE}{RESET}")
        except OSError as e:
            self.logger.error(f"{NEON_RED}Error saving bot state: {e}{RESET}")

    def load_state(self):
        """Loads bot state from file and populates relevant managers."""
        if not Path(STATE_FILE).exists(): return False
        try:
            with Path(STATE_FILE).open("r", encoding="utf-8") as f:
                state_data = json.load(f)
            
            # Load state into WS Manager
            if self.ws_manager:
                self.ws_manager.positions = state_data.get("positions", {})
                self.ws_manager.orders = state_data.get("orders", {})
                self.ws_manager.last_exec_time_ms = state_data.get("last_exec_time_ms", 0)
                self.state_data = state_data # Store loaded data for other components if needed
                self.logger.info(f"Bot state loaded. Positions: {len(self.ws_manager.positions)}, Orders: {len(self.ws_manager.orders)}")
            return True
        except (OSError, json.JSONDecodeError) as e:
            self.logger.error(f"Error loading bot state: {e}{RESET}")
            return False

# --- WebSocket Manager ---
class WebSocketManager:
    """Manages WebSocket connections, subscriptions, and message routing."""
    def __init__(self, api_client: PybitTradingClient, config: dict, logger: logging.Logger):
        self.api_client, self.cfg, self.logger = api_client, config, logger
        self.stop_event = api_client.stop_event # Use parent client's stop event
        # Bybit Unified Trading WS URL for public data
        self.public_ws_url = "wss://stream.bybit.com/v5/public/linear" if not api_client.testnet else "wss://stream-testnet.bybit.com/v5/public/linear"
        # Bybit Unified Trading WS URL for private data (user data)
        self.private_ws_url = "wss://stream.bybit.com/v5/private" if not api_client.testnet else "wss://stream-testnet.bybit.com/v5/private"

        self.ws_public: Optional[websocket.WebSocketApp] = None
        self.ws_private: Optional[websocket.WebSocketApp] = None
        self.public_ws_thread: Optional[threading.Thread] = None
        self.private_ws_thread: Optional[threading.Thread] = None
        self.connect_delay = 1 # Reconnection delay in seconds

        # State caches (thread-safe access required)
        self.positions: Dict[str, Dict] = {}
        self.orders: Dict[str, Dict] = {}
        self.last_exec_time_ms = 0
        self.state_lock = threading.Lock() # Lock for accessing positions and orders

        self.listeners = { # Callbacks for different event types
            "position_update": [], "order_update": [], "execution": [], "account_update": [],
            "kline_update": [], "orderbook_update": [],
        }

    def start(self):
        """Starts the WebSocket connection threads."""
        self.public_ws_thread = threading.Thread(target=self._run_ws, args=(self.public_ws_url, "public"), daemon=True, name="BybitPublicWS")
        self.public_ws_thread.start()
        self.logger.info("Public WebSocket Manager started.")
        
        # Only start private WS if Pybit client is enabled for actual trading
        if self.api_client.enabled:
            self.private_ws_thread = threading.Thread(target=self._run_ws, args=(self.private_ws_url, "private"), daemon=True, name="BybitPrivateWS")
            self.private_ws_thread.start()
            self.logger.info("Private WebSocket Manager started.")

    def shutdown(self):
        """Closes the WebSocket connection gracefully."""
        self.stop_event.set()
        if self.ws_public: self.ws_public.close()
        if self.ws_private: self.ws_private.close()

        if self.public_ws_thread and self.public_ws_thread.is_alive():
            self.public_ws_thread.join()
        if self.private_ws_thread and self.private_ws_thread.is_alive():
            self.private_ws_thread.join()
        self.logger.info("WebSocket Manager shut down.")

    def _run_ws(self, url: str, ws_type: Literal["public", "private"]):
        """Main loop for managing WebSocket connection life cycle and reconnection."""
        ws_app_attr = f"ws_{ws_type}"
        while not self.stop_event.is_set():
            ws_app = getattr(self, ws_app_attr)
            if ws_app and ws_app.connected: # Check if already connected (websocket-client library attribute)
                try: ws_app.send(json.dumps({"op": "ping"})) # Send ping for keepalive
                except Exception: ws_app.close() # Force reconnect on ping failure
                time.sleep(HEARTBEAT_INTERVAL_MS / 1000.0) # Wait for next ping interval
                continue

            # Attempt to connect if not connected or connection lost
            try:
                self.logger.info(f"Attempting {ws_type} WebSocket connection to {url}...")
                ws = websocket.WebSocketApp(
                    url,
                    on_message=self.on_message, on_error=self.on_error,
                    on_close=lambda ws, status, msg, ws_type=ws_type: self.on_close(ws, status, msg, ws_type),
                    on_open=lambda ws, ws_type=ws_type: self.on_open(ws, ws_type)
                )
                setattr(self, ws_app_attr, ws) # Store the WebSocketApp instance
                ws.run_forever(ping_interval=HEARTBEAT_INTERVAL_MS/1000.0, ping_timeout=HEARTBEAT_INTERVAL_MS/2000.0) # Blocks
            except Exception as e:
                self.logger.error(f"WebSocket run_forever error ({ws_type}): {e}. Retrying in {self.connect_delay}s.\n{traceback.format_exc()}")
                time.sleep(self.connect_delay)
                self.connect_delay = min(self.connect_delay * 2, 60) # Exponential backoff

    def on_message(self, ws, message):
        """Processes incoming WebSocket messages."""
        try:
            data = json.loads(message)
            self._process_ws_message(data)
        except Exception: self.logger.exception("Error processing WS message")

    def on_error(self, ws, error):
        """Handles WebSocket errors."""
        self.logger.error(f"WebSocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg, ws_type: str):
        """Handles WebSocket closure, triggering reconnection."""
        self.logger.warning(f"{ws_type} WebSocket closed: {close_status_code} {close_msg}. Reconnecting...")
        if ws_type == "public": self.ws_public = None
        else: self.ws_private = None # Clear WS object to trigger reconnect logic in _run_ws

    def on_open(self, ws, ws_type: str):
        """Callback executed when WebSocket connection is established."""
        self.logger.info(f"{ws_type} WebSocket connection opened.")
        self.connect_delay = 1 # Reset delay on successful connection
        self._subscribe_channels(ws, ws_type) # Subscribe to necessary data streams
        self._sync_initial_state() # Fetch initial state from REST API

    def _subscribe_channels(self, ws: websocket.WebSocketApp, ws_type: str):
        """Subscribes to relevant Bybit WebSocket channels."""
        subscriptions = []
        symbol = self.cfg["symbol"]

        if ws_type == "public":
            # Public topics: kline, orderbook
            subscriptions.append(f"kline.{self.cfg['interval']}.{symbol}")
            subscriptions.append(f"orderbook.1.{symbol}") # Level 1 orderbook, check config for limit
            self.logger.info(f"Subscribing to public WS topics for {symbol}: {', '.join(subscriptions)}")
        elif ws_type == "private":
            # Private topics: position, order, execution, wallet
            subscriptions.extend([
                "position", # All position updates
                "order",    # All order updates
                "execution",# All execution updates
                "wallet",   # Account balance updates
            ])
            self.logger.info(f"Subscribing to private WS topics: {', '.join(subscriptions)}")
        
        if subscriptions:
            # For Unified Trading, authentication is usually handled by the Pybit library
            # during connection or within the subscribe message.
            # The 'op': 'subscribe' message with 'args' is the standard for Bybit v5.
            payload = {"op": "subscribe", "args": [f"{self.cfg['execution']['category']}.{s}" if ws_type == "private" else s for s in subscriptions]}
            try:
                ws.send(json.dumps(payload))
                self.logger.info(f"Sent subscription payload for {ws_type} topics.")
            except Exception as e:
                self.logger.error(f"Error sending WS subscription for {ws_type} topics: {e}\n{traceback.format_exc()}")

    def _sync_initial_state(self):
        """Fetches initial positions and orders via REST API to populate local cache."""
        symbol = self.cfg["symbol"]
        
        # Sync positions
        pos_data = self.api_client.get_positions(symbol)
        if pos_data and self.api_client._ok(pos_data):
            for p in pos_data["result"]["list"]:
                if p["symbol"] == symbol:
                    with self.state_lock:
                        self.positions[symbol] = p # Update local position cache
                    self.notify_listeners("position_update", p)
                    break
        else: self.logger.warning(f"Could not sync initial positions for {symbol}. Response: {pos_data}")
        
        # Sync open orders
        open_orders_data = self.api_client.get_open_orders(symbol)
        if open_orders_data:
            with self.state_lock:
                for order in open_orders_data:
                    self.orders[order["orderId"]] = order
            self.notify_listeners("order_update", order)
        else: self.logger.info(f"No open orders found for {symbol} during initial sync.")

        # Initialize last_exec_time_ms for fetching executions
        now_ms = int(time.time() * 1000)
        self.last_exec_time_ms = max(self.last_exec_time_ms, now_ms - 5 * 60 * 1000) # Start fetch from 5 mins ago

    def _process_ws_message(self, data):
        """Routes incoming WebSocket messages to appropriate handlers."""
        if not isinstance(data, dict): return # Ignore malformed messages

        topic = data.get("topic")
        
        # Check for error or success messages directly from Bybit's API response structure
        if "op" in data and data["op"] == "subscribe":
            if data.get("success"): self.logger.info(f"WS Subscription successful for args: {data.get('req_id')}")
            else: self.logger.error(f"WS Subscription failed for args: {data.get('req_id')} - {data.get('retMsg')}")
            return
        
        # Handle authenticated topic messages (private streams)
        if topic and topic.startswith(f"{self.cfg['execution']['category']}."):
            if "order" in topic: self._handle_order_update(data.get("data", []))
            elif "position" in topic: self._handle_position_update(data.get("data", []))
            elif "execution" in topic: self._handle_execution_update(data.get("data", []))
            elif "wallet" in topic: self._handle_account_update(data.get("data", {}))
        # Handle public topic messages
        elif topic:
            if topic.startswith("kline."): self._handle_kline_update(data.get("data", []))
            elif topic.startswith("orderbook."): self._handle_orderbook_update(data.get("data", {}))
        elif data.get("retCode") == 0: self.logger.debug(f"WS General Success: {data.get('retMsg', 'OK')}")
        elif data.get("retCode") is not None and data.get("retCode") != 0:
            self.logger.error(f"WS Error Response: {data.get('retCode')} - {data.get('retMsg')}")

    def _handle_order_update(self, order_list: List[Dict]):
        """Updates the local order cache and notifies listeners."""
        for order_info in order_list:
            order_id = order_info.get("orderId")
            if order_id:
                with self.state_lock: # Protect access to shared state
                    self.orders[order_id] = order_info
                self.notify_listeners("order_update", order_info)

    def _handle_position_update(self, position_list: List[Dict]):
        """Updates the local position cache and notifies listeners."""
        for pos_info in position_list:
            symbol = pos_info.get("symbol")
            if symbol:
                with self.state_lock: # Protect access to shared state
                    self.positions[symbol] = pos_info
                self.notify_listeners("position_update", pos_info)

    def _handle_execution_update(self, execution_list: List[Dict]):
        """Processes execution updates and notifies listeners."""
        for exec_info in execution_list:
            exec_time_ms = int(exec_info.get("execTime", 0))
            if exec_time_ms > self.last_exec_time_ms: # Process only new executions
                self.last_exec_time_ms = exec_time_ms
                # Optionally store executions if needed for detailed analysis
                self.notify_listeners("execution", exec_info)

    def _handle_account_update(self, account_data: Dict):
        """Handles account updates and notifies listeners."""
        self.notify_listeners("account_update", account_data)

    def _handle_kline_update(self, kline_data: List[Dict]):
        """Processes real-time kline updates and notifies listeners."""
        # Bybit kline data often comes as a list of dictionaries, one for each candle update.
        # The 'confirm' field indicates if the candle is closed.
        for candle_info in kline_data:
            if candle_info.get('confirm') is True: # Only process confirmed/closed candles
                self.notify_listeners("kline_update", candle_info)

    def _handle_orderbook_update(self, orderbook_data: Dict):
        """Processes real-time orderbook updates and notifies listeners."""
        # Bybit orderbook updates can be snapshot or delta.
        # We're primarily interested in the 'b' (bids) and 'a' (asks) lists.
        self.notify_listeners("orderbook_update", orderbook_data)


    def add_listener(self, event_type: str, callback: Callable):
        """Registers a callback function for a specific event type."""
        if event_type in self.listeners:
            self.listeners[event_type].append(callback)
        else:
            self.logger.warning(f"Attempted to add listener for unknown event type: {event_type}")

    def notify_listeners(self, event_type: str, data):
        """Calls all registered listeners for the given event type, ensuring thread safety."""
        for callback in self.listeners.get(event_type, []):
            try:
                callback(data) # Call the listener function
            except Exception:
                self.logger.exception(f"Error executing listener for event '{event_type}'")

# --- Position Management ---
class PositionManager:
    """Manages the bot's local state of open positions and handles order creation/management."""
    def __init__(self, config: dict, logger: logging.Logger, symbol: str, pybit_client: PybitTradingClient):
        self.config, self.logger, self.symbol = config, logger, symbol
        self.pybit = pybit_client
        self.live = bool(config.get("execution", {}).get("use_pybit", False))
        
        self.open_positions: List[Dict] = [] # Local cache of open positions
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        # Precision and step values, fetched from exchange or defaults
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]
        self.qty_step = Decimal("0.000001")
        self.slippage_percent = Decimal(str(config["trade_management"].get("slippage_percent", 0.0)))
        self.stop_loss_atr_multiple = Decimal(str(config["trade_management"]["stop_loss_atr_multiple"]))
        self.take_profit_atr_multiple = Decimal(str(config["trade_management"]["take_profit_atr_multiple"]))
        
        self._update_precision_from_exchange() # Fetch precision settings from exchange
        self._load_state() # Load initial position state if available

    def _load_state(self):
        """Loads initial position state from WS manager's cache."""
        if self.pybit.ws_manager and self.symbol in self.pybit.ws_manager.positions:
            ws_pos_data = self.pybit.ws_manager.positions[self.symbol]
            # Convert WS position data to internal format. Assumes one position per symbol for simplicity.
            # Adjust if multiple positions per symbol are managed differently.
            self.open_positions = [self._convert_ws_position_to_local(ws_pos_data)]
            self.logger.info(f"Loaded initial position state from WS for {self.symbol}.")

    def _convert_ws_position_to_local(self, ws_pos: Dict) -> Dict:
        """Maps WebSocket position data structure to the internal local format."""
        # Ensure mapping keys match the actual data structure from Bybit's WS position updates.
        # Adjust based on the precise format of 'pos_info' from _handle_position_update.
        return {
            "entry_time": datetime.fromtimestamp(int(ws_pos.get("createdTime", 0)) / 1000, tz=TIMEZONE), # 'time' is deprecated, use 'createdTime'
            "symbol": ws_pos.get("symbol"),
            "side": "BUY" if ws_pos.get("side") == "Buy" else "SELL",
            "entry_price": Decimal(ws_pos.get("avgPrice", "0")),
            "qty": Decimal(ws_pos.get("size", "0")),
            "stop_loss": Decimal(ws_pos.get("stopLoss", "0")), # Note: SL/TP might need separate tracking if not in position update
            "take_profit": Decimal(ws_pos.get("takeProfit", "0")),
            "status": "OPEN", # Assume OPEN if it's in the positions list
            "link_prefix": f"ws_{int(time.time()*1000)}", # Generate a prefix for WS-managed positions
            "adds": 0, "order_id": None, "stop_loss_order_id": None, "take_profit_order_ids": [],
            "breakeven_set": False # Flag for breakeven stop logic
        }

    def _update_precision_from_exchange(self):
        """Fetches instrument info to get accurate quantity step and price precision."""
        if not self.live or not self.pybit or not self.pybit.enabled:
            self.logger.warning(f"Pybit client not ready. Cannot fetch precision for {self.symbol}. Using config values.")
            return
        
        info = self.pybit.fetch_instrument_info(self.symbol)
        if info:
            lot_size_filter = info.get("lotSizeFilter", {})
            self.qty_step = Decimal(str(lot_size_filter.get("qtyStep", "0.000001")))
            if not self.qty_step.is_zero():
                self.order_precision = abs(self.qty_step.as_tuple().exponent)
            self.logger.info(f"Updated qty_step: {self.qty_step}, order_precision: {self.order_precision}")

            price_filter = info.get("priceFilter", {})
            tick_size = Decimal(str(price_filter.get("tickSize", "0.001")))
            if not tick_size.is_zero():
                self.price_precision = abs(tick_size.as_tuple().exponent)
            self.logger.info(f"Updated price_precision: {self.price_precision}")
        else:
            self.logger.warning(f"Could not fetch instrument info for {self.symbol}. Using config values.")

    def _get_current_balance(self) -> Decimal:
        """Retrieves the current USDT balance, prioritizing live exchange data."""
        if self.live and self.pybit and self.pybit.enabled:
            resp = self.pybit.get_wallet_balance(coin="USDT")
            if resp and self.pybit._ok(resp) and resp.get("result", {}).get("list"):
                for coin_balance in resp["result"]["list"][0]["coin"]:
                    if coin_balance["coin"] == "USDT":
                        return Decimal(coin_balance["walletBalance"])
        # Fallback to configured account balance if live data fails or is disabled
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    def _calculate_order_size(self, current_price: Decimal, atr_value: Decimal, conviction: float = 1.0) -> Decimal:
        """Calculates the order quantity based on risk parameters, ATR, and conviction level."""
        if not self.config["trade_management"]["enabled"]: return Decimal("0")
        
        account_balance = self._get_current_balance()
        base_risk_pct = Decimal(str(self.config["trade_management"]["risk_per_trade_percent"])) / 100
        # Scale risk based on conviction (0.5x to 1.5x of base risk)
        risk_multiplier = Decimal(str(np.clip(0.5 + conviction, 0.5, 1.5)))
        risk_pct = base_risk_pct * risk_multiplier
        
        stop_loss_distance = atr_value * self.stop_loss_atr_multiple
        
        # Validate inputs to prevent division by zero or invalid calculations
        if stop_loss_distance <= 0 or current_price <= 0:
            self.logger.warning(f"Invalid SL distance ({stop_loss_distance}) or current price ({current_price}). Cannot calculate order size.")
            return Decimal("0")
        
        order_value = (account_balance * risk_pct) / stop_loss_distance # USD risked per unit price
        order_qty = order_value / current_price # Convert USD risk to quantity
        
        return round_qty(order_qty, self.qty_step) # Round quantity to nearest valid step

    def _compute_stop_loss_price(self, side: Literal["BUY", "SELL"], entry_price: Decimal, atr_value: Decimal) -> Decimal:
        """Computes the Stop Loss price based on configuration (ATR multiple or percentage)."""
        sl_cfg = self.config["execution"]["sl_scheme"]
        sl = Decimal("0")
        if sl_cfg["type"] == "atr_multiple":
            sl = (entry_price - atr_value * self.stop_loss_atr_multiple) if side == "BUY" else (entry_price + atr_value * self.stop_loss_atr_multiple)
        elif sl_cfg["type"] == "percent":
            sl_pct = Decimal(str(sl_cfg["percent"])) / 100
            sl = (entry_price * (Decimal("1") - sl_pct)) if side == "BUY" else (entry_price * (Decimal("1") + sl_pct))
        return round_price(sl, self.price_precision)

    def _calculate_take_profit_price(self, side: Literal["BUY", "SELL"], entry_price: Decimal, atr_value: Decimal) -> Decimal:
        """Computes the Take Profit price based on ATR multiples."""
        tp = (entry_price + atr_value * self.take_profit_atr_multiple) if side == "BUY" else (entry_price - atr_value * self.take_profit_atr_multiple)
        return round_price(tp, self.price_precision)

    def _get_position_by_link_prefix(self, link_prefix: str) -> Optional[Dict]:
        """Finds a local position entry using its unique link prefix."""
        return next((p for p in self.open_positions if p.get("link_prefix") == link_prefix), None)

    def open_position(self, signal: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal, conviction: float) -> Optional[Dict]:
        """Opens a new position, either live via API or simulated."""
        if not self.config["trade_management"]["enabled"] or len(self.get_open_positions()) >= self.max_open_positions:
            self.logger.info(f"Cannot open position: Max limits reached ({len(self.get_open_positions())}/{self.max_open_positions}) or trade management disabled.")
            return None
        
        order_qty = self._calculate_order_size(current_price, atr_value, conviction)
        if order_qty <= 0:
            self.logger.warning("Order quantity calculated as zero. Cannot open position.")
            return None
        
        stop_loss = self._compute_stop_loss_price(signal, current_price, atr_value)
        take_profit = self._calculate_take_profit_price(signal, current_price, atr_value)

        # Adjust entry price for slippage in simulated trades
        adjusted_entry_price_sim = current_price
        if not self.live:
            adj = self.slippage_percent if signal == "BUY" else -self.slippage_percent
            adjusted_entry_price_sim = current_price * (Decimal("1") + adj)

        position_data = {
            "entry_time": datetime.now(TIMEZONE), "symbol": self.symbol, "side": signal,
            "entry_price": round_price(adjusted_entry_price_sim, self.price_precision), "qty": order_qty,
            "stop_loss": stop_loss, "take_profit": round_price(take_profit, self.price_precision),
            "status": "OPEN", "link_prefix": f"wgx_{int(time.time()*1000)}", "adds": 0,
            "order_id": None, "stop_loss_order_id": None, "take_profit_order_ids": [],
            "breakeven_set": False # Flag for breakeven stop logic
        }

        if self.live and self.pybit and self.pybit.enabled:
            entry_link_id = f"{position_data['link_prefix']}_entry"
            try:
                resp = self.pybit.place_order(
                    category=self.pybit.category, symbol=self.symbol,
                    side=self.pybit._side_to_bybit(signal), orderType="Market",
                    qty=self.pybit._q(order_qty), orderLinkId=entry_link_id,
                    isLeverage=1, tpSlMode="Partial" # Specify Partial mode for TP/SL
                )
                if self.pybit._ok(resp):
                    position_data["order_id"] = resp["result"]["orderId"]
                    self.logger.info(f"Live entry submitted (Order ID: {position_data['order_id']}). Setting TP/SL.")
                    # Set TP/SL orders immediately after successful entry
                    self.set_tpsl_for_position(position_data, current_price, atr_value)
                else:
                    self.logger.error(f"Live entry failed. Simulating only. Response: {resp}")
            except Exception as e:
                self.logger.error(f"Exception during live entry: {e}\n{traceback.format_exc()}. Simulating only.")

        self.open_positions.append(position_data) # Add to local state
        self.logger.info(f"Opened {signal} position (local/simulated): {position_data}")
        return position_data

    def set_tpsl_for_position(self, position: dict, current_price: Decimal, atr_value: Decimal):
        """Sets Take Profit and Stop Loss orders for a live position using partial TP/SL schemes."""
        if not self.live or not self.pybit or not self.pybit.enabled: return

        sl_cfg = self.config["execution"]["sl_scheme"]
        tp_scheme = self.config["execution"]["tp_scheme"]
        pos_idx = self.pybit._pos_idx(position["side"]) # Get correct positionIdx if hedge mode

        # --- Place Stop Loss Order ---
        if sl_cfg["use_conditional_stop"]:
            sl_price = self._compute_stop_loss_price(position["side"], position["entry_price"], atr_value)
            sl_link_id = f"{position.get('link_prefix', 'pos')}_sl" # Generate unique link ID
            
            self.logger.info(f"Placing conditional SL for {self.symbol} at {sl_price}...")
            sl_resp = self.pybit.place_order(
                category=self.pybit.category, symbol=self.symbol,
                side=self.pybit._side_to_bybit("SELL" if position["side"] == "BUY" else "BUY"),
                orderType=sl_cfg["stop_order_type"], qty=self.pybit._q(position["qty"]),
                reduceOnly=True, orderLinkId=sl_link_id,
                triggerPrice=self.pybit._q(sl_price),
                triggerDirection=(2 if position["side"] == "BUY" else 1), # Trigger condition based on side
                orderFilter="Stop", slTriggerBy=sl_cfg["sl_trigger_by"],
            )
            if self.pybit._ok(sl_resp):
                position["stop_loss_order_id"] = sl_resp["result"]["orderId"]
                self.logger.info(f"Conditional SL placed successfully at {sl_price} (Order ID: {position['stop_loss_order_id']}).")
            else:
                self.logger.error(f"Failed to place conditional SL: {sl_resp.get('retMsg')}")

        # --- Place Take Profit Orders (Partial TP) ---
        if tp_scheme["mode"] == "atr_multiples" and tp_scheme.get("targets"):
            # build_partial_tp_targets should be a helper function defined elsewhere
            tp_requests = self.build_partial_tp_targets(
                position["side"], position["entry_price"], atr_value, position["qty"],
                self.config, self.qty_step, self.price_precision, position["link_prefix"]
            )
            
            batch_orders = []
            for target_detail in tp_requests:
                payload = {
                    "symbol": self.symbol,
                    "side": self.pybit._side_to_bybit("SELL" if position["side"] == "BUY" else "BUY"),
                    "orderType": target_detail["order_type"], "qty": self.pybit._q(target_detail["qty"]),
                    "price": self.pybit._q(target_detail["price"]), "timeInForce": target_detail["tif"],
                    "reduceOnly": True, "positionIdx": pos_idx, "orderLinkId": target_detail["order_link_id"],
                    "isPostOnly": target_detail["post_only"], "tpSlMode": "Partial" # Ensure Partial mode
                }
                batch_orders.append(payload)

            if batch_orders:
                self.logger.info(f"Placing {len(batch_orders)} partial TP orders for {self.symbol}...")
                batch_resp = self.pybit.batch_place_orders(batch_orders)
                if self.pybit._ok(batch_resp):
                    for res in batch_resp["result"]["list"]:
                        if res.get("orderId"):
                            position["take_profit_order_ids"].append(res["orderId"])
                            self.logger.info(f"Partial TP placed successfully (Order ID: {res['orderId']}).")
                        else:
                            self.logger.warning(f"Failed to place one partial TP: {res.get('retMsg')}")
                else:
                    self.logger.error(f"Batch TP placement failed: {batch_resp.get('retMsg')}")
            else: self.logger.info("No valid partial TP targets generated.")

    def build_partial_tp_targets(self, side: Literal["BUY", "SELL"], entry_price: Decimal, atr_value: Decimal,
                                 total_qty: Decimal, config: Dict, qty_step: Decimal, price_precision: int,
                                 link_prefix: str) -> List[Dict]:
        """Builds a list of partial take profit order requests based on configuration."""
        tp_targets_config = config["execution"]["tp_scheme"]["targets"]
        tp_requests = []
        cumulative_qty_pct = Decimal("0")

        for i, target_cfg in enumerate(tp_targets_config):
            if cumulative_qty_pct >= Decimal("1.0"): break # All quantity allocated

            target_qty_pct = Decimal(str(target_cfg.get("size_pct", 0)))
            if target_qty_pct <= 0: continue

            qty_for_target = round_qty(total_qty * target_qty_pct, qty_step)
            if qty_for_target <= 0: continue

            # Calculate target price
            tp_price = (entry_price + atr_value * Decimal(str(target_cfg["atr_multiple"]))) if side == "BUY" else \
                       (entry_price - atr_value * Decimal(str(target_cfg["atr_multiple"])))
            tp_price = round_price(tp_price, price_precision)

            tp_requests.append({
                "order_type": target_cfg.get("order_type", "Limit"),
                "qty": qty_for_target,
                "price": tp_price,
                "tif": target_cfg.get("tif", "GoodTillCancel"),
                "post_only": target_cfg.get("post_only", False),
                "order_link_id": f"{link_prefix}_tp{i+1}"
            })
            cumulative_qty_pct += target_qty_pct
        
        # Adjust last TP to ensure total quantity is covered if there's a small remainder due to rounding
        if cumulative_qty_pct < Decimal("1.0") and tp_requests:
            remaining_qty = total_qty - sum(req["qty"] for req in tp_requests)
            if remaining_qty > 0:
                tp_requests[-1]["qty"] += remaining_qty # Add remaining to the last target
                tp_requests[-1]["qty"] = round_qty(tp_requests[-1]["qty"], qty_step) # Re-round
        
        return tp_requests

    def manage_positions(self, current_price: Decimal, performance_tracker: Any):
        """Manages simulated positions: closes them if SL/TP is hit."""
        if self.live or not self.config["trade_management"]["enabled"] or not self.open_positions: return
        
        indices_to_remove = []
        for i, pos in enumerate(self.open_positions):
            if pos["status"] == "OPEN":
                closed_by, adjusted_exit_price_sim = "", current_price
                
                # Check for simulated TP/SL hit
                if pos["side"] == "BUY":
                    if current_price <= pos["stop_loss"]: closed_by = "STOP_LOSS"
                    elif current_price >= pos["take_profit"]: closed_by = "TAKE_PROFIT"
                    adjusted_exit_price_sim = current_price * (Decimal("1") - self.slippage_percent) # Apply slippage
                elif pos["side"] == "SELL":
                    if current_price >= pos["stop_loss"]: closed_by = "STOP_LOSS"
                    elif current_price <= pos["take_profit"]: closed_by = "TAKE_PROFIT"
                    adjusted_exit_price_sim = current_price * (Decimal("1") + self.slippage_percent) # Apply slippage

                if closed_by: # If TP or SL hit in simulation
                    pos.update({
                        "status": "CLOSED", "exit_time": datetime.now(TIMEZONE),
                        "exit_price": round_price(adjusted_exit_price_sim, self.price_precision),
                        "closed_by": closed_by,
                    })
                    # Calculate PnL for the simulated trade
                    pnl = ( (pos["exit_price"] - pos["entry_price"]) * pos["qty"] if pos["side"] == "BUY"
                            else (pos["entry_price"] - pos["exit_price"]) * pos["qty"] )
                    
                    performance_tracker.record_trade(pos, pnl) # Record in performance tracker
                    self.logger.info(f"Closed {pos['side']} simulated position by {closed_by}. PnL: {pnl.normalize():.4f}")
                    indices_to_remove.append(i)
        
        # Remove closed positions from the local list
        self.open_positions = [p for i, p in enumerate(self.open_positions) if i not in indices_to_remove]

    def trail_stop(self, pos: dict, current_price: Decimal, atr_value: Decimal):
        """Adjusts trailing stop loss for simulated positions."""
        if pos.get('status') != 'OPEN' or self.live: return # Only for simulated, open positions
        
        side, atr_mult = pos["side"], self.stop_loss_atr_multiple
        pos["best_price"] = pos.get("best_price", pos["entry_price"]) # Track best price achieved
        
        new_sl = pos["stop_loss"] # Current stop loss
        if side == "BUY":
            pos["best_price"] = max(pos["best_price"], current_price) # Update best price if higher
            calculated_sl = pos["best_price"] - atr_mult * atr_value # Calculate new SL
            if calculated_sl > new_sl: # Only raise SL
                new_sl = calculated_sl
                self.logger.debug(f"Trailing BUY SL to {new_sl:.4f}")
        else: # SELL
            pos["best_price"] = min(pos["best_price"], current_price) # Update best price if lower
            calculated_sl = pos["best_price"] + atr_mult * atr_value # Calculate new SL
            if calculated_sl < new_sl: # Only lower SL
                new_sl = calculated_sl
                self.logger.debug(f"Trailing SELL SL to {new_sl:.4f}")

        pos["stop_loss"] = round_price(new_sl, self.price_precision) # Update local SL

    def try_pyramid(self, current_price: Decimal, atr_value: Decimal):
        """Attempts to add to existing simulated positions based on pyramiding rules."""
        if not self.config["trade_management"]["enabled"] or not self.open_positions or self.live: return
        py_cfg = self.config.get("pyramiding", {})
        if not py_cfg.get("enabled", False): return

        for pos in self.open_positions:
            if pos.get("status") != "OPEN": continue
            adds = pos.get("adds", 0)
            if adds >= int(py_cfg.get("max_adds", 0)): continue # Max pyramiding adds reached

            step_atr_mult = Decimal(str(py_cfg.get("step_atr", 0.7)))
            step_distance = step_atr_mult * atr_value
            # Calculate target price for the next pyramiding step
            target_price = pos["entry_price"] + step_distance * (adds + 1) if pos["side"] == "BUY" else pos["entry_price"] - step_distance * (adds + 1)
            
            # Check if current price has reached the target price for an add
            should_add = (pos["side"] == "BUY" and current_price >= target_price) or \
                         (pos["side"] == "SELL" and current_price <= target_price)
            
            if should_add:
                size_pct_of_initial = Decimal(str(py_cfg.get("size_pct_of_initial", 0.5)))
                add_qty = round_qty(pos['qty'] * size_pct_of_initial, self.qty_step) # Calculate quantity for the add
                
                if add_qty > 0:
                    # Update position details: average entry price and total quantity
                    total_cost = (pos['qty'] * pos['entry_price']) + (add_qty * current_price)
                    pos['qty'] += add_qty
                    pos['entry_price'] = total_cost / pos['qty'] # New average entry price
                    pos["adds"] = adds + 1 # Increment add count
                    self.logger.info(f"Pyramiding add #{pos['adds']} qty={add_qty.normalize()}. New avg price: {pos['entry_price'].normalize():.4f}")

    def get_open_positions(self) -> List[Dict]:
        """Returns the list of currently open positions."""
        return [pos for pos in self.open_positions if pos.get("status") == "OPEN"]

# --- Performance Tracking ---
class PerformanceTracker:
    """Tracks and reports trading performance metrics."""
    def __init__(self, logger: logging.Logger, config: dict):
        self.logger = logger
        self.config = config
        self.trades: List[Dict] = [] # List to store completed trade records
        self.total_pnl = Decimal("0")
        self.gross_profit = Decimal("0")
        self.gross_loss = Decimal("0")
        self.wins = 0
        self.losses = 0
        self.peak_pnl = Decimal("0") # Tracks highest cumulative PnL
        self.max_drawdown = Decimal("0") # Tracks maximum drawdown from peak PnL
        self.trading_fee_percent = Decimal(str(config["trade_management"].get("trading_fee_percent", 0.0)))
        self._daily_pnl = Decimal("0") # PnL accumulated for the current day
        self._last_day_reset = datetime.now(TIMEZONE).date() # Date when daily stats were last reset

    def _reset_daily_stats(self):
        """Resets daily PnL and related metrics if the day has changed."""
        today = datetime.now(TIMEZONE).date()
        if today != self._last_day_reset:
            self._daily_pnl = Decimal("0")
            self._last_day_reset = today
            self.logger.info("Resetting daily performance statistics.")

    def record_trade(self, position: Dict, pnl: Decimal):
        """Records a completed trade, calculates net PnL (after fees), and updates metrics."""
        self._reset_daily_stats() # Ensure daily stats are up-to-date
        
        trade_record = {
            "entry_time": position.get("entry_time"), "exit_time": position.get("exit_time"),
            "symbol": position.get("symbol"), "side": position.get("side"),
            "entry_price": position.get("entry_price"), "exit_price": position.get("exit_price"),
            "qty": position.get("qty"), "pnl_gross": pnl, "closed_by": position.get("closed_by"),
        }
        
        # Calculate fees based on entry/exit price and quantity
        entry_fee = Decimal(str(position.get("entry_price", 0))) * Decimal(str(position.get("qty", 0))) * self.trading_fee_percent
        exit_fee = Decimal(str(position.get("exit_price", 0))) * Decimal(str(position.get("qty", 0))) * self.trading_fee_percent
        total_fees = entry_fee + exit_fee
        
        pnl_net = pnl - total_fees # Net PnL after deducting fees
        trade_record["fees"] = total_fees
        trade_record["pnl_net"] = pnl_net
        
        self.trades.append(trade_record) # Add trade to history
        self.total_pnl += pnl_net
        self._daily_pnl += pnl_net # Accumulate for daily PnL tracking
        
        # Update peak PnL and maximum drawdown
        if self.total_pnl > self.peak_pnl: self.peak_pnl = self.total_pnl
        drawdown = self.peak_pnl - self.total_pnl
        if drawdown > self.max_drawdown: self.max_drawdown = drawdown

        # Update win/loss counts and gross profit/loss
        if pnl_net > 0:
            self.wins += 1
            self.gross_profit += pnl_net
        else:
            self.losses += 1
            self.gross_loss += abs(pnl_net)

        self.logger.info(
            f"{NEON_CYAN}Trade recorded. Gross PnL: {pnl.normalize():.4f}, Fees: {total_fees.normalize():.4f}, Net PnL: {pnl_net.normalize():.4f}. "
            f"Total PnL: {self.total_pnl.normalize():.4f}, Daily PnL: {self._daily_pnl.normalize():.4f}{RESET}"
        )

    def day_pnl(self) -> Decimal:
        """Returns the net PnL accumulated for the current trading day."""
        self._reset_daily_stats() # Ensure stats are current
        return self._daily_pnl

    def get_summary(self) -> dict:
        """Returns a dictionary summarizing all performance metrics."""
        total_trades = len(self.trades)
        win_rate = (self.wins / total_trades) * 100 if total_trades > 0 else 0
        profit_factor = self.gross_profit / self.gross_loss if self.gross_loss > 0 else Decimal("inf")
        avg_win = self.gross_profit / self.wins if self.wins > 0 else Decimal("0")
        avg_loss = self.gross_loss / self.losses if self.losses > 0 else Decimal("0")
        
        # Format summary metrics for display
        summary = {
            "total_trades": total_trades, "total_pnl": f"{self.total_pnl:.4f}",
            "gross_profit": f"{self.gross_profit:.4f}", "gross_loss": f"{self.gross_loss:.4f}",
            "profit_factor": f"{profit_factor:.2f}", "max_drawdown": f"{self.max_drawdown:.4f}",
            "wins": self.wins, "losses": self.losses, "win_rate": f"{win_rate:.2f}%",
            "avg_win": f"{avg_win:.4f}", "avg_loss": f"{avg_loss:.4f}",
            "daily_pnl": f"{self.day_pnl():.4f}",
        }
        return summary
        
    def load_state(self, state_data: Dict) -> bool:
        """Loads performance tracker state from a dictionary (e.g., from file)."""
        if not state_data: return False
        summary = state_data.get("performance_tracker", {}) # Assume performance tracker state is nested
        try:
            self.total_pnl = Decimal(summary.get("total_pnl", "0"))
            self.gross_profit = Decimal(summary.get("gross_profit", "0"))
            self.gross_loss = Decimal(summary.get("gross_loss", "0"))
            self.peak_pnl = Decimal(summary.get("peak_pnl", "0"))
            self.max_drawdown = Decimal(summary.get("max_drawdown", "0"))
            self.wins = summary.get("wins", 0)
            self.losses = summary.get("losses", 0)
            # Note: Full trade history (self.trades) is not loaded here for simplicity.
            # Bot will start calculating performance from scratch after restart, using loaded PnL totals.
            self.logger.info(f"Performance tracker state loaded. Total PnL: {self.total_pnl:.4f}")
            return True
        except (InvalidOperation, TypeError, ValueError, KeyError) as e:
            self.logger.error(f"Error loading performance tracker state: {e}. Starting fresh.{traceback.format_exc()}")
            return False

    def get_state(self) -> Dict:
        """Returns the current state of the performance tracker for saving."""
        return {
            "total_pnl": str(self.total_pnl), # Convert Decimals to string for JSON serialization
            "gross_profit": str(self.gross_profit),
            "gross_loss": str(self.gross_loss),
            "peak_pnl": str(self.peak_pnl),
            "max_drawdown": str(self.max_drawdown),
            "wins": self.wins,
            "losses": self.losses,
            # Current daily_pnl is dynamic, _last_day_reset tracks its validity
        }

# --- Live Execution Synchronization ---
class ExchangeExecutionSync:
    """Polls the exchange for recent trade fills, updates local state, and manages TP/SL events."""
    def __init__(self, symbol: str, pybit_client: PybitTradingClient, cfg: dict, pm: PositionManager, pt: PerformanceTracker):
        self.symbol, self.pybit, self.cfg, self.pm, self.pt = symbol, pybit_client, cfg, pm, pt
        # Initialize timestamp for fetching executions
        self.last_exec_time_ms = (pybit_client.ws_manager.last_exec_time_ms
                                  if pybit_client.ws_manager else int(time.time() * 1000) - 5 * 60 * 1000)

    def _is_ours(self, link_id: str | None) -> bool:
        """Checks if an orderLinkId belongs to this bot's tracked orders."""
        if not link_id: return False
        if not self.cfg["execution"]["live_sync"]["only_track_linked"]: return True # If not tracking linked, assume all are ours
        return link_id.startswith("wgx_") or link_id.startswith("ws_") # Check known prefixes

    def _compute_breakeven_price(self, side: str, entry_price: Decimal, atr_value: Decimal) -> Decimal:
        """Calculates the breakeven stop loss price with configured offset."""
        be_cfg = self.cfg["execution"]["breakeven_after_tp1"]
        offset_type = str(be_cfg.get("offset_type", "atr")).lower()
        offset_value = Decimal(str(be_cfg.get("offset_value", 0)))
        lock_in_min_percent = Decimal(str(be_cfg.get("lock_in_min_percent", 0))) / 100
        
        offset_amount = Decimal("0")
        if offset_type == "atr": offset_amount = atr_value * offset_value
        elif offset_type == "percent": offset_amount = entry_price * offset_value
        else: offset_amount = offset_value # Use as absolute value if type is unrecognized
        
        # Ensure minimum profit is locked in
        adjustment = max(offset_amount, entry_price * lock_in_min_percent)
        
        if side == "BUY": return round_price(entry_price + adjustment, self.pm.price_precision)
        else: return round_price(entry_price - adjustment, self.pm.price_precision)

    def _move_stop_to_breakeven(self, open_pos: dict, atr_value: Decimal):
        """Moves the stop loss to breakeven after TP1 is hit (if enabled)."""
        if not self.cfg["execution"]["breakeven_after_tp1"].get("enabled", False): return
        if open_pos.get("breakeven_set", False): return # Already set

        try:
            entry, side = Decimal(str(open_pos["entry_price"])), open_pos["side"]
            new_sl_price = self._compute_breakeven_price(side, entry, atr_value)

            # Cancel the existing stop loss order
            old_sl_id, old_sl_link = open_pos.get("stop_loss_order_id"), f"{open_pos.get('link_prefix')}_sl"
            if old_sl_id: self.pybit.cancel_order(self.symbol, order_id=old_sl_id)
            elif old_sl_link: self.pybit.cancel_order(self.symbol, order_link_id=old_sl_link) # Try cancel by link ID
            else: self.pybit.logger.warning(f"Could not find order ID or link ID for old SL of position {open_pos.get('link_prefix')}.")

            # Place the new breakeven stop loss order
            new_sl_link_id = f"{open_pos['link_prefix']}_sl_be"
            # Use the remaining quantity on the position for the new stop loss
            remaining_qty = open_pos.get("qty", Decimal("0"))
            if remaining_qty <= 0:
                self.pybit.logger.warning(f"No remaining quantity for position {open_pos.get('link_prefix')} to place breakeven SL.")
                return

            sresp = self.pybit.place_order(
                category=self.pybit.category, symbol=self.symbol,
                side=self.pybit._side_to_bybit("SELL" if side == "BUY" else "BUY"),
                orderType=self.cfg["execution"]["sl_scheme"]["stop_order_type"],
                qty=self.pybit._q(remaining_qty), reduceOnly=True, # Use remaining quantity
                orderLinkId=new_sl_link_id,
                triggerPrice=self.pybit._q(new_sl_price),
                triggerDirection=(2 if side == "BUY" else 1), orderFilter="Stop",
                slTriggerBy=self.cfg["execution"]["breakeven_after_tp1"]["sl_trigger_by"],
            )
            if self.pybit._ok(sresp):
                open_pos["stop_loss"] = new_sl_price # Update local stop loss price
                open_pos["stop_loss_order_id"] = sresp["result"]["orderId"]
                open_pos["breakeven_set"] = True # Mark breakeven as set
                self.pybit.logger.info(f"Moved SL to breakeven at {new_sl_price} (Order ID: {open_pos['stop_loss_order_id']}).")
            else:
                self.pybit.logger.error(f"Failed to place breakeven SL: {sresp.get('retMsg')}")

        except Exception as e:
            self.pybit.logger.error(f"Breakeven move exception for {self.symbol}: {e}\n{traceback.format_exc()}")

    def poll(self):
        """Polls the exchange for recent trade executions and updates local state."""
        if not (self.pybit and self.pybit.enabled and self.cfg["execution"]["live_sync"]["enabled"]): return

        try:
            resp = self.pybit.get_executions(
                self.symbol, self.last_exec_time_ms, self.cfg["execution"]["live_sync"]["max_exec_fetch"],
            )
            if not self.pybit._ok(resp): return

            rows = resp.get("result", {}).get("list", [])
            rows.sort(key=lambda r: int(r.get("execTime", 0))) # Process chronologically

            for r in rows:
                link, exec_time_ms = r.get("orderLinkId"), int(r.get("execTime", 0))
                # Only process new executions, and if it's ours or if not tracking by link ID
                if exec_time_ms < self.last_exec_time_ms or (self.cfg["execution"]["live_sync"]["only_track_linked"] and not self._is_ours(link)): continue
                
                self.last_exec_time_ms = exec_time_ms + 1 # Advance timestamp

                tag = "UNKNOWN" # Determine if it's entry, SL, TP
                pos_prefix = None
                if link:
                    parts = link.split('_')
                    if len(parts) >= 2: # Expecting format like wgx_timestamp_type
                        pos_prefix = "_".join(parts[:2])
                        if link.endswith("_entry"): tag = "ENTRY"
                        elif "_sl" in link: tag = "SL"
                        elif "_tp" in link: tag = "TP"
                
                # Find the corresponding local position entry
                open_pos = self.pm._get_position_by_link_prefix(pos_prefix) if pos_prefix else None
                
                # Process TP or SL executions that affect open positions
                if tag in ("TP", "SL") and open_pos and open_pos["status"] == "OPEN":
                    exec_qty = Decimal(str(r.get("execQty", "0")))
                    exec_price = Decimal(str(r.get("execPrice", "0")))
                    
                    # Calculate PnL for this specific execution segment
                    pnl = ( (exec_price - open_pos["entry_price"]) * exec_qty if open_pos["side"] == "BUY"
                            else (open_pos["entry_price"] - exec_price) * exec_qty )
                    
                    # Record this trade segment in the performance tracker
                    self.pt.record_trade(
                        {**open_pos, "exit_time": datetime.fromtimestamp(exec_time_ms / 1000, tz=TIMEZONE),
                         "exit_price": exec_price, "qty": exec_qty, "closed_by": tag},
                        pnl,
                    )
                    
                    # Update remaining quantity in the local position state
                    open_pos["qty"] -= exec_qty
                    if open_pos["qty"] <= 0: # Position fully closed
                        open_pos.update({
                            "status": "CLOSED", "exit_time": datetime.fromtimestamp(exec_time_ms / 1000, tz=TIMEZONE),
                            "exit_price": exec_price, "closed_by": tag
                        })
                        self.pybit.logger.info(f"Position for {self.symbol} fully closed by {tag}.")
                    else:
                        self.pybit.logger.info(f"Partial execution for {self.symbol} by {tag}. Remaining Qty: {open_pos['qty'].normalize()}")
                    
                    # Trigger breakeven logic if TP1 was hit and enabled
                    if tag == "TP" and link and link.endswith("_tp1") and not open_pos.get("breakeven_set", False):
                        # Retrieve last known ATR for breakeven calculation
                        atr_val = Decimal(str(self.cfg.get("_last_atr_value", "0.1"))) # Default ATR if unavailable
                        self._move_stop_to_breakeven(open_pos, atr_val)
                        
            # Remove fully closed positions from the local manager state
            self.pm.open_positions = [p for p in self.pm.open_positions if p.get("status") == "OPEN"]
        
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.pybit.logger.error(f"Execution sync error for {self.symbol}: {e}\n{traceback.format_exc()}")

# --- Position Heartbeat ---
class PositionHeartbeat:
    """Periodically checks and reconciles local position state with the exchange state."""
    def __init__(self, symbol: str, pybit_client: PybitTradingClient, cfg: dict, pm: PositionManager):
        self.symbol, self.pybit, self.cfg, self.pm = symbol, pybit_client, cfg, pm
        self._last_heartbeat_ms = 0

    def tick(self):
        """Executes a heartbeat check if the interval has passed."""
        hb_cfg = self.cfg["execution"]["live_sync"]["heartbeat"]
        if not (hb_cfg.get("enabled", True) and self.pybit and self.pybit.enabled): return
        
        now_ms = int(time.time() * 1000)
        if now_ms - self._last_heartbeat_ms < int(hb_cfg.get("interval_ms", 5000)): return # Wait for interval
        
        self._last_heartbeat_ms = now_ms
        self.pybit.logger.debug(f"Performing position heartbeat for {self.symbol}...")

        try:
            resp = self.pybit.get_positions(self.symbol) # Fetch positions from exchange
            if not self.pybit._ok(resp):
                self.pybit.logger.warning(f"Heartbeat: Failed to fetch positions for {self.symbol}. Response: {resp}")
                return

            exchange_positions = resp.get("result", {}).get("list", [])
            
            net_qty_exchange = Decimal("0")
            avg_price_exchange = Decimal("0")
            
            # Calculate net position details from exchange data
            if isinstance(exchange_positions, list):
                for p in exchange_positions:
                    if p.get("symbol") == self.symbol and float(p.get("size", 0)) > 0:
                        pos_size = Decimal(p.get("size", "0"))
                        if p.get("side") == "Buy":
                            net_qty_exchange += pos_size
                            avg_price_exchange = Decimal(p.get("avgPrice", "0")) # Use avgPrice from exchange
                        elif p.get("side") == "Sell":
                            net_qty_exchange -= pos_size
                            avg_price_exchange = Decimal(p.get("avgPrice", "0"))
            
            local_open_positions = self.pm.get_open_positions()
            has_local_pos = len(local_open_positions) > 0
            
            # Scenario 1: Exchange is flat, but local position exists -> Close local position
            if net_qty_exchange == 0 and has_local_pos:
                for pos in local_open_positions: # Mark all local open positions as closed
                    pos.update({"status": "CLOSED", "closed_by": "HEARTBEAT_SYNC"})
                self.pybit.logger.info(f"Heartbeat: Closed local position(s) for {self.symbol} (exchange is flat).")
                self.pm.open_positions = [] # Clear local state

            # Scenario 2: Exchange has a position, but no local position -> Create synthetic local position
            elif net_qty_exchange != 0 and not has_local_pos:
                side_exchange = "BUY" if net_qty_exchange > 0 else "SELL"
                # Create a synthetic position to match exchange state
                synthetic_pos = {
                    "entry_time": datetime.now(TIMEZONE), "symbol": self.symbol, "side": side_exchange,
                    "entry_price": round_price(avg_price_exchange, self.pm.price_precision),
                    "qty": round_qty(abs(net_qty_exchange), self.pm.qty_step),
                    "stop_loss": Decimal("0"), "take_profit": Decimal("0"), # SL/TP need manual sync or logic
                    "status": "OPEN", "link_prefix": f"hb_{int(time.time()*1000)}", "adds": 0,
                    "order_id": None, "stop_loss_order_id": None, "take_profit_order_ids": [],
                    "breakeven_set": False
                }
                self.pm.open_positions.append(synthetic_pos)
                self.pybit.logger.warning(f"Heartbeat: Created synthetic local position for {self.symbol} to match exchange state.")
            
            # Scenario 3: Both have positions; compare and log mismatches
            elif net_qty_exchange != 0 and has_local_pos:
                local_pos = local_open_positions[0] # Assume single position for simplicity
                # Compare quantities and log if they differ
                if abs(net_qty_exchange) != local_pos["qty"]:
                    self.pybit.logger.warning(f"Heartbeat: Quantity mismatch for {self.symbol}. Local: {local_pos['qty'].normalize()}, Exchange: {abs(net_qty_exchange).normalize()}.")
                # Add more checks here if needed (e.g., avgPrice, SL/TP)

        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.pybit.logger.error(f"Heartbeat error for {self.symbol}: {e}\n{traceback.format_exc()}")

# --- Trading Analysis ---
class TradingAnalyzer:
    """Analyzes market data using technical indicators to generate trading signals."""
    def __init__(self, df: pd.DataFrame, config: dict, logger: logging.Logger, symbol: str):
        self.df = df.copy()
        self.config, self.logger, self.symbol = config, logger, symbol
        self.indicator_values: Dict[str, Any] = {} # Stores latest indicator values
        self.fib_levels: Dict[str, Decimal] = {} # Stores Fibonacci levels
        self.weights = config["weight_sets"]["default_scalping"]
        self.indicator_settings = config["indicator_settings"]
        # Load transient state for hysteresis and cooldown
        self._last_score = float(config.get("_last_score", 0.0))
        self._last_signal_ts = int(config.get("_last_signal_ts", 0))

        if self.df.empty:
            self.logger.warning(f"[{self.symbol}] Initialized with empty DataFrame. Indicators cannot be calculated.")
            return
        
        self._calculate_all_indicators()
        # Calculate Fibonacci levels if enabled
        if self.config["indicators"].get("fibonacci_levels", False): self.calculate_fibonacci_levels()
        if self.config["indicators"].get("fibonacci_pivot_points", False): self.calculate_fibonacci_pivot_points()

    def _safe_calculate(self, func: Callable, name: str, min_data_points: int = 0, *args, **kwargs) -> Any | None:
        """Safely calculates an indicator, handling errors and insufficient data."""
        if len(self.df) < min_data_points:
            self.logger.debug(f"[{self.symbol}] Skipping indicator '{name}': Not enough data (need {min_data_points}, have {len(self.df)}).")
            return None
        try:
            result = func(self.df, *args, **kwargs) # Execute the indicator calculation function
            # Check if the result is effectively empty or all NaNs
            is_empty_or_nan = (result is None or
                               (isinstance(result, pd.Series) and result.empty) or
                               (isinstance(result, pd.DataFrame) and result.empty) or
                               (isinstance(result, tuple) and all(r is None or (isinstance(r, pd.Series) and r.empty) for r in result)) or
                               (isinstance(result, pd.Series) and result.isnull().all()))
            if is_empty_or_nan:
                self.logger.warning(f"[{self.symbol}] Indicator '{name}' returned empty or all NaNs. Check data quality or parameters.")
            return result
        except Exception as e:
            self.logger.error(f"Error calculating indicator '{name}': {e}\n{traceback.format_exc()}")
            return None

    def _calculate_all_indicators(self):
        """Calculates all enabled indicators and stores their latest values."""
        self.logger.debug(f"[{self.symbol}] Calculating all technical indicators...")
        cfg, isd = self.config, self.indicator_settings

        # Calculate ATR first as it's a dependency for many other indicators
        if self.config["indicators"].get("atr", False) or any(k in isd and "atr" in k for k in ["atr_period", "keltner_atr_multiplier"]):
            self.df["ATR"] = self._safe_calculate(indicators.calculate_atr, "ATR", isd["atr_period"], period=isd["atr_period"])
            if "ATR" in self.df.columns and self.df["ATR"].iloc[-1] is not None and not pd.isna(self.df["ATR"].iloc[-1]):
                self.indicator_values["ATR"] = Decimal(str(self.df["ATR"].iloc[-1]))
        
        # --- Calculate other indicators based on config ---
        if cfg["indicators"].get("ema_alignment", False):
            self.df["EMA_Short"] = self._safe_calculate(indicators.calculate_ema, "EMA_Short", isd["ema_short_period"], period=isd["ema_short_period"])
            self.df["EMA_Long"] = self._safe_calculate(indicators.calculate_ema, "EMA_Long", isd["ema_long_period"], period=isd["ema_long_period"])
            if "EMA_Short" in self.df.columns and not pd.isna(self.df["EMA_Short"].iloc[-1]): self.indicator_values["EMA_Short"] = Decimal(str(self.df["EMA_Short"].iloc[-1]))
            if "EMA_Long" in self.df.columns and not pd.isna(self.df["EMA_Long"].iloc[-1]): self.indicator_values["EMA_Long"] = Decimal(str(self.df["EMA_Long"].iloc[-1]))

        if cfg["indicators"].get("sma_trend_filter", False):
            self.df["SMA_Short"] = self._safe_calculate(indicators.calculate_sma, "SMA_Short", isd["sma_short_period"], period=isd["sma_short_period"])
            self.df["SMA_Long"] = self._safe_calculate(indicators.calculate_sma, "SMA_Long", isd["sma_long_period"], period=isd["sma_long_period"])
            if "SMA_Short" in self.df.columns and not pd.isna(self.df["SMA_Short"].iloc[-1]): self.indicator_values["SMA_Short"] = Decimal(str(self.df["SMA_Short"].iloc[-1]))
            if "SMA_Long" in self.df.columns and not pd.isna(self.df["SMA_Long"].iloc[-1]): self.indicator_values["SMA_Long"] = Decimal(str(self.df["SMA_Long"].iloc[-1]))

        if cfg["indicators"].get("rsi", False):
            self.df["RSI"] = self._safe_calculate(indicators.calculate_rsi, "RSI", isd["rsi_period"], period=isd["rsi_period"])
            if "RSI" in self.df.columns and not pd.isna(self.df["RSI"].iloc[-1]): self.indicator_values["RSI"] = Decimal(str(self.df["RSI"].iloc[-1]))

        if cfg["indicators"].get("stoch_rsi", False):
            stoch_rsi_res = self._safe_calculate(indicators.calculate_stoch_rsi, "StochRSI", isd["stoch_rsi_period"], period=isd["stoch_rsi_period"], k_period=isd["stoch_k_period"], d_period=isd["stoch_d_period"])
            if stoch_rsi_res is not None and not stoch_rsi_res.empty:
                self.df["StochRSI_K"] = stoch_rsi_res["K"]
                self.df["StochRSI_D"] = stoch_rsi_res["D"]
                if not pd.isna(self.df["StochRSI_K"].iloc[-1]): self.indicator_values["StochRSI_K"] = Decimal(str(self.df["StochRSI_K"].iloc[-1]))
                if not pd.isna(self.df["StochRSI_D"].iloc[-1]): self.indicator_values["StochRSI_D"] = Decimal(str(self.df["StochRSI_D"].iloc[-1]))

        if cfg["indicators"].get("bollinger_bands", False):
            bb_res = self._safe_calculate(indicators.calculate_bollinger_bands, "BollingerBands", isd["bollinger_bands_period"], period=isd["bollinger_bands_period"], std_dev=isd["bollinger_bands_std_dev"])
            if bb_res is not None and not bb_res.empty:
                self.df["BB_Upper"] = bb_res["Upper"]
                self.df["BB_Middle"] = bb_res["Middle"]
                self.df["BB_Lower"] = bb_res["Lower"]
                if not pd.isna(self.df["BB_Upper"].iloc[-1]): self.indicator_values["BB_Upper"] = Decimal(str(self.df["BB_Upper"].iloc[-1]))
                if not pd.isna(self.df["BB_Middle"].iloc[-1]): self.indicator_values["BB_Middle"] = Decimal(str(self.df["BB_Middle"].iloc[-1]))
                if not pd.isna(self.df["BB_Lower"].iloc[-1]): self.indicator_values["BB_Lower"] = Decimal(str(self.df["BB_Lower"].iloc[-1]))

        if cfg["indicators"].get("cci", False):
            self.df["CCI"] = self._safe_calculate(indicators.calculate_cci, "CCI", isd["cci_period"], period=isd["cci_period"])
            if "CCI" in self.df.columns and not pd.isna(self.df["CCI"].iloc[-1]): self.indicator_values["CCI"] = Decimal(str(self.df["CCI"].iloc[-1]))

        if cfg["indicators"].get("wr", False):
            self.df["WR"] = self._safe_calculate(indicators.calculate_williams_r, "WR", isd["williams_r_period"], period=isd["williams_r_period"])
            if "WR" in self.df.columns and not pd.isna(self.df["WR"].iloc[-1]): self.indicator_values["WR"] = Decimal(str(self.df["WR"].iloc[-1]))

        if cfg["indicators"].get("mfi", False):
            self.df["MFI"] = self._safe_calculate(indicators.calculate_mfi, "MFI", isd["mfi_period"], period=isd["mfi_period"])
            if "MFI" in self.df.columns and not pd.isna(self.df["MFI"].iloc[-1]): self.indicator_values["MFI"] = Decimal(str(self.df["MFI"].iloc[-1]))

        if cfg["indicators"].get("psar", False):
            psar_res = self._safe_calculate(indicators.calculate_psar, "PSAR", min_data_points=2, acceleration=isd["psar_acceleration"], maximum=isd["psar_max_acceleration"])
            if psar_res is not None and not psar_res.empty:
                self.df["PSAR_Val"] = psar_res["PSAR"]
                self.df["PSAR_Dir"] = psar_res["Direction"]
                if not pd.isna(self.df["PSAR_Val"].iloc[-1]): self.indicator_values["PSAR_Val"] = Decimal(str(self.df["PSAR_Val"].iloc[-1]))
                if not pd.isna(self.df["PSAR_Dir"].iloc[-1]): self.indicator_values["PSAR_Dir"] = self.df["PSAR_Dir"].iloc[-1]

        if cfg["indicators"].get("vwap", False):
            self.df["VWAP"] = self._safe_calculate(indicators.calculate_vwap, "VWAP", min_data_points=1)
            if "VWAP" in self.df.columns and not pd.isna(self.df["VWAP"].iloc[-1]): self.indicator_values["VWAP"] = Decimal(str(self.df["VWAP"].iloc[-1]))

        if cfg["indicators"].get("ehlers_supertrend", False):
            est_res = self._safe_calculate(indicators.calculate_ehlers_supertrend, "EhlersSuperTrend", isd["ehlers_fast_period"],
                                       fast_period=isd["ehlers_fast_period"], fast_multiplier=isd["ehlers_fast_multiplier"],
                                       slow_period=isd["ehlers_slow_period"], slow_multiplier=isd["ehlers_slow_multiplier"])
            if est_res is not None and not est_res.empty:
                self.df["ST_Fast_Val"] = est_res["ST_Fast_Val"]
                self.df["ST_Fast_Dir"] = est_res["ST_Fast_Dir"]
                self.df["ST_Slow_Val"] = est_res["ST_Slow_Val"]
                self.df["ST_Slow_Dir"] = est_res["ST_Slow_Dir"]
                if not pd.isna(self.df["ST_Slow_Dir"].iloc[-1]): self.indicator_values["ST_Slow_Dir"] = self.df["ST_Slow_Dir"].iloc[-1]
                if not pd.isna(self.df["ST_Slow_Val"].iloc[-1]): self.indicator_values["ST_Slow_Val"] = Decimal(str(self.df["ST_Slow_Val"].iloc[-1]))

        if cfg["indicators"].get("macd", False):
            macd_res = self._safe_calculate(indicators.calculate_macd, "MACD", isd["macd_slow_period"],
                                        fast_period=isd["macd_fast_period"], slow_period=isd["macd_slow_period"], signal_period=isd["macd_signal_period"])
            if macd_res is not None and not macd_res.empty:
                self.df["MACD_Line"] = macd_res["MACD"]
                self.df["MACD_Signal"] = macd_res["Signal"]
                self.df["MACD_Hist"] = macd_res["Histogram"]
                if not pd.isna(self.df["MACD_Line"].iloc[-1]): self.indicator_values["MACD_Line"] = Decimal(str(self.df["MACD_Line"].iloc[-1]))
                if not pd.isna(self.df["MACD_Signal"].iloc[-1]): self.indicator_values["MACD_Signal"] = Decimal(str(self.df["MACD_Signal"].iloc[-1]))
                if not pd.isna(self.df["MACD_Hist"].iloc[-1]): self.indicator_values["MACD_Hist"] = Decimal(str(self.df["MACD_Hist"].iloc[-1]))

        if cfg["indicators"].get("adx", False):
            adx_res = self._safe_calculate(indicators.calculate_adx, "ADX", isd["adx_period"], period=isd["adx_period"])
            if adx_res is not None and not adx_res.empty:
                self.df["ADX"] = adx_res["ADX"]
                self.df["PlusDI"] = adx_res["+DI"]
                self.df["MinusDI"] = adx_res["-DI"]
                if not pd.isna(self.df["ADX"].iloc[-1]): self.indicator_values["ADX"] = Decimal(str(self.df["ADX"].iloc[-1]))
                if not pd.isna(self.df["PlusDI"].iloc[-1]): self.indicator_values["PlusDI"] = Decimal(str(self.df["PlusDI"].iloc[-1]))
                if not pd.isna(self.df["MinusDI"].iloc[-1]): self.indicator_values["MinusDI"] = Decimal(str(self.df["MinusDI"].iloc[-1]))

        if cfg["indicators"].get("ichimoku_cloud", False):
            ichimoku_res = self._safe_calculate(indicators.calculate_ichimoku, "Ichimoku", isd["ichimoku_senkou_span_b_period"],
                                            tenkan_period=isd["ichimoku_tenkan_period"], kijun_period=isd["ichimoku_kijun_period"],
                                            senkou_span_b_period=isd["ichimoku_senkou_span_b_period"], chikou_span_offset=isd["ichimoku_chikou_span_offset"])
            if ichimoku_res is not None and not ichimoku_res.empty:
                self.df["Tenkan_Sen"] = ichimoku_res["Tenkan_Sen"]
                self.df["Kijun_Sen"] = ichimoku_res["Kijun_Sen"]
                self.df["Senkou_Span_A"] = ichimoku_res["Senkou_Span_A"]
                self.df["Senkou_Span_B"] = ichimoku_res["Senkou_Span_B"]
                self.df["Chikou_Span"] = ichimoku_res["Chikou_Span"]
                if not pd.isna(self.df["Tenkan_Sen"].iloc[-1]): self.indicator_values["Tenkan_Sen"] = Decimal(str(self.df["Tenkan_Sen"].iloc[-1]))
                if not pd.isna(self.df["Kijun_Sen"].iloc[-1]): self.indicator_values["Kijun_Sen"] = Decimal(str(self.df["Kijun_Sen"].iloc[-1]))
                if not pd.isna(self.df["Senkou_Span_A"].iloc[-1]): self.indicator_values["Senkou_Span_A"] = Decimal(str(self.df["Senkou_Span_A"].iloc[-1]))
                if not pd.isna(self.df["Senkou_Span_B"].iloc[-1]): self.indicator_values["Senkou_Span_B"] = Decimal(str(self.df["Senkou_Span_B"].iloc[-1]))
                if not pd.isna(self.df["Chikou_Span"].iloc[-1]): self.indicator_values["Chikou_Span"] = Decimal(str(self.df["Chikou_Span"].iloc[-1]))

        if cfg["indicators"].get("obv", False):
            self.df["OBV"] = self._safe_calculate(indicators.calculate_obv, "OBV")
            self.df["OBV_EMA"] = self._safe_calculate(indicators.calculate_ema, "OBV_EMA", isd["obv_ema_period"], series=self.df["OBV"], period=isd["obv_ema_period"])
            if "OBV" in self.df.columns and not pd.isna(self.df["OBV"].iloc[-1]): self.indicator_values["OBV"] = Decimal(str(self.df["OBV"].iloc[-1]))
            if "OBV_EMA" in self.df.columns and not pd.isna(self.df["OBV_EMA"].iloc[-1]): self.indicator_values["OBV_EMA"] = Decimal(str(self.df["OBV_EMA"].iloc[-1]))

        if cfg["indicators"].get("cmf", False):
            self.df["CMF"] = self._safe_calculate(indicators.calculate_cmf, "CMF", isd["cmf_period"], period=isd["cmf_period"])
            if "CMF" in self.df.columns and not pd.isna(self.df["CMF"].iloc[-1]): self.indicator_values["CMF"] = Decimal(str(self.df["CMF"].iloc[-1]))
        
        if cfg["indicators"].get("volatility_index", False):
            self.df["Volatility_Index"] = self._safe_calculate(indicators.calculate_volatility_index, "Volatility_Index", isd["volatility_index_period"], period=isd["volatility_index_period"])
            if "Volatility_Index" in self.df.columns and not pd.isna(self.df["Volatility_Index"].iloc[-1]): self.indicator_values["Volatility_Index"] = Decimal(str(self.df["Volatility_Index"].iloc[-1]))

        if cfg["indicators"].get("vwma", False):
            self.df["VWMA"] = self._safe_calculate(indicators.calculate_vwma, "VWMA", isd["vwma_period"], period=isd["vwma_period"])
            if "VWMA" in self.df.columns and not pd.isna(self.df["VWMA"].iloc[-1]): self.indicator_values["VWMA"] = Decimal(str(self.df["VWMA"].iloc[-1]))

        if cfg["indicators"].get("volume_delta", False):
            self.df["Volume_Delta"] = self._safe_calculate(indicators.calculate_volume_delta, "Volume_Delta", isd["volume_delta_period"], period=isd["volume_delta_period"])
            if "Volume_Delta" in self.df.columns and not pd.isna(self.df["Volume_Delta"].iloc[-1]): self.indicator_values["Volume_Delta"] = Decimal(str(self.df["Volume_Delta"].iloc[-1]))
        
        if cfg["indicators"].get("kaufman_ama", False):
            self.df["Kaufman_AMA"] = self._safe_calculate(indicators.calculate_kama, "Kaufman_AMA", isd["kama_period"],
                                                      period=isd["kama_period"], fast_period=isd["kama_fast_period"], slow_period=isd["kama_slow_period"])
            if "Kaufman_AMA" in self.df.columns and not pd.isna(self.df["Kaufman_AMA"].iloc[-1]): self.indicator_values["Kaufman_AMA"] = Decimal(str(self.df["Kaufman_AMA"].iloc[-1]))

        if cfg["indicators"].get("relative_volume", False):
            self.df["Relative_Volume"] = self._safe_calculate(indicators.calculate_relative_volume, "Relative_Volume", isd["relative_volume_period"], period=isd["relative_volume_period"])
            if "Relative_Volume" in self.df.columns and not pd.isna(self.df["Relative_Volume"].iloc[-1]): self.indicator_values["Relative_Volume"] = Decimal(str(self.df["Relative_Volume"].iloc[-1]))

        if cfg["indicators"].get("market_structure", False):
            ms_res = self._safe_calculate(indicators.analyze_market_structure, "Market_Structure", isd["market_structure_lookback_period"], lookback_period=isd["market_structure_lookback_period"])
            if ms_res is not None:
                self.indicator_values["Market_Structure_Trend"] = ms_res["Market_Structure_Trend"]

        if cfg["indicators"].get("dema", False):
            self.df["DEMA"] = self._safe_calculate(indicators.calculate_dema, "DEMA", isd["dema_period"], period=isd["dema_period"])
            if "DEMA" in self.df.columns and not pd.isna(self.df["DEMA"].iloc[-1]): self.indicator_values["DEMA"] = Decimal(str(self.df["DEMA"].iloc[-1]))

        if cfg["indicators"].get("keltner_channels", False):
            kc_res = self._safe_calculate(indicators.calculate_keltner_channels, "Keltner_Channels", isd["keltner_period"],
                                      period=isd["keltner_period"], atr_multiplier=isd["keltner_atr_multiplier"], atr_period=isd["atr_period"])
            if kc_res is not None and not kc_res.empty:
                self.df["Keltner_Upper"] = kc_res["Upper"]
                self.df["Keltner_Middle"] = kc_res["Middle"]
                self.df["Keltner_Lower"] = kc_res["Lower"]
                if not pd.isna(self.df["Keltner_Upper"].iloc[-1]): self.indicator_values["Keltner_Upper"] = Decimal(str(self.df["Keltner_Upper"].iloc[-1]))
                if not pd.isna(self.df["Keltner_Middle"].iloc[-1]): self.indicator_values["Keltner_Middle"] = Decimal(str(self.df["Keltner_Middle"].iloc[-1]))
                if not pd.isna(self.df["Keltner_Lower"].iloc[-1]): self.indicator_values["Keltner_Lower"] = Decimal(str(self.df["Keltner_Lower"].iloc[-1]))

        if cfg["indicators"].get("roc", False):
            self.df["ROC"] = self._safe_calculate(indicators.calculate_roc, "ROC", isd["roc_period"], period=isd["roc_period"])
            if "ROC" in self.df.columns and not pd.isna(self.df["ROC"].iloc[-1]): self.indicator_values["ROC"] = Decimal(str(self.df["ROC"].iloc[-1]))

        if cfg["indicators"].get("candlestick_patterns", False):
            self.df["Candlestick_Pattern"] = self._safe_calculate(indicators.detect_candlestick_patterns, "Candlestick_Pattern", MIN_CANDLESTICK_PATTERNS_BARS)
            if "Candlestick_Pattern" in self.df.columns and self.df["Candlestick_Pattern"].iloc[-1] is not None: self.indicator_values["Candlestick_Pattern"] = self.df["Candlestick_Pattern"].iloc[-1]


        # --- DataFrame Cleanup ---
        initial_len = len(self.df)
        # Drop rows with NaNs in essential columns like price data or key indicators (e.g., ATR)
        essential_cols = ["close", "high", "low", "open", "volume"]
        for col in essential_cols:
            if col in self.df.columns:
                self.df.dropna(subset=[col], inplace=True)
        
        # Ensure 'ATR' is treated as essential if it was calculated, before filling other NaNs
        if "ATR" in self.df.columns:
            self.df.dropna(subset=["ATR"], inplace=True)

        self.df.fillna(0, inplace=True) # Fill remaining NaNs, potentially after calculations
        
        # Log cleanup results
        if len(self.df) < initial_len:
            self.logger.debug(f"Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations.")
        if self.df.empty:
            self.logger.warning(f"DataFrame became empty after calculations and cleanup. Cannot proceed.")
        else:
            self.logger.debug(f"Indicator calculations complete. Final DataFrame shape: {self.df.shape}")

    def calculate_fibonacci_levels(self) -> None:
        """Calculates Fibonacci retracement levels for the recent price swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        fib_levels = indicators.calculate_fibonacci_levels(self.df, window)
        if fib_levels:
            price_precision = self.config["trade_management"]["price_precision"]
            self.fib_levels = {k: Decimal(str(v)).quantize(Decimal(f"1e-{price_precision}"), rounding=ROUND_DOWN) for k,v in fib_levels.items()}
        else: self.logger.warning("Fibonacci retracement levels could not be calculated.")

    def calculate_fibonacci_pivot_points(self) -> None:
        """Calculates Fibonacci Pivot Points (Pivot, R1, R2, S1, S2)."""
        pivot_data = indicators.calculate_fibonacci_pivot_points(self.df)
        if pivot_data:
            # Store pivot points with correct Decimal precision
            price_precision = self.config["trade_management"]["price_precision"]
            for key, value in pivot_data.items():
                try:
                    self.indicator_values[key.upper()] = Decimal(str(value)).quantize(Decimal(f"1e-{price_precision}"), rounding=ROUND_DOWN)
                except InvalidOperation:
                    self.logger.warning(f"Could not convert pivot point value '{value}' to Decimal. Skipping.")
            self.logger.debug("Calculated Fibonacci Pivot Points.")
        else:
            self.logger.warning("Fibonacci Pivot Points could not be calculated.")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieves the latest indicator value, returning default if not found."""
        return self.indicator_values.get(key, default)

    # --- Signal Generation Methods ---
    def _score_adx(self, trend_strength_multiplier_in: float) -> Tuple[float, Dict]:
        """Scores ADX for trend strength and returns multiplier/breakdown."""
        adx = self._get_indicator_value("ADX")
        plus_di = self._get_indicator_value("PlusDI")
        minus_di = self._get_indicator_value("MinusDI")

        score = 0.0
        breakdown = {}
        trend_strength_multiplier = trend_strength_multiplier_in # Initialize with input

        if not pd.isna(adx) and not pd.isna(plus_di) and not pd.isna(minus_di):
            adx_weight = self.weights.get("adx_strength", 0.0)

            if adx >= ADX_STRONG_TREND_THRESHOLD:
                trend_strength_multiplier = 1.2 # Stronger trend, increase multiplier
                if plus_di > minus_di: # Strong uptrend
                    score += adx_weight * 1.0
                    breakdown["ADX Strong Uptrend"] = adx_weight * 1.0
                elif minus_di > plus_di: # Strong downtrend
                    score -= adx_weight * 1.0
                    breakdown["ADX Strong Downtrend"] = -adx_weight * 1.0
                self.logger.debug(f"ADX: Strong Trend ({adx:.2f})")
            elif adx <= ADX_WEAK_TREND_THRESHOLD:
                trend_strength_multiplier = 0.8 # Weaker trend, decrease multiplier
                breakdown["ADX Weak Trend"] = 0.0 # No strong signal, but notes regime
                self.logger.debug(f"ADX: Weak/Ranging Trend ({adx:.2f})")
            else: # Moderate trend
                breakdown["ADX Moderate Trend"] = 0.0
                self.logger.debug(f"ADX: Moderate Trend ({adx:.2f})")

        return score, {"breakdown": breakdown, "trend_strength_multiplier": trend_strength_multiplier}

    def _score_ema_alignment(self, current_close: Decimal, trend_multiplier: float) -> Tuple[float, Dict]:
        """Scores EMA alignment, adjusted by trend multiplier."""
        ema_short = self._get_indicator_value("EMA_Short")
        ema_long = self._get_indicator_value("EMA_Long")

        score = 0.0
        breakdown = {}

        if not pd.isna(ema_short) and not pd.isna(ema_long) and ema_long != 0:
            ema_weight = self.weights.get("ema_alignment", 0.0)
            if ema_short > ema_long: # Bullish alignment
                score_contrib = ema_weight * trend_multiplier
                score += score_contrib
                breakdown["EMA Alignment (Bull)"] = score_contrib
            elif ema_short < ema_long: # Bearish alignment
                score_contrib = -ema_weight * trend_multiplier
                score += score_contrib
                breakdown["EMA Alignment (Bear)"] = score_contrib

        return score, {"breakdown": breakdown}

    def _score_sma_trend_filter(self, current_close: Decimal) -> Tuple[float, Dict]:
        """Scores SMA trend filter based on short and long SMA crossing."""
        sma_short = self._get_indicator_value("SMA_Short")
        sma_long = self._get_indicator_value("SMA_Long")
        
        score = 0.0
        breakdown = {}

        if not pd.isna(sma_short) and not pd.isna(sma_long):
            sma_weight = self.weights.get("sma_trend_filter", 0.0)
            if sma_short > sma_long:
                score += sma_weight
                breakdown["SMA Trend (Bull)"] = sma_weight
            elif sma_short < sma_long:
                score -= sma_weight
                breakdown["SMA Trend (Bear)"] = -sma_weight

        return score, {"breakdown": breakdown}

    def _score_momentum_indicators(self) -> Tuple[float, Dict]:
        """Aggregates scores from RSI, StochRSI, CCI, Williams %R, MFI."""
        rsi = self._get_indicator_value("RSI")
        stoch_k = self._get_indicator_value("StochRSI_K")
        stoch_d = self._get_indicator_value("StochRSI_D")
        cci = self._get_indicator_value("CCI")
        wr = self._get_indicator_value("WR")
        mfi = self._get_indicator_value("MFI")

        total_momentum_score = 0.0
        breakdown = {}
        momentum_weight = self.weights.get("momentum_rsi_stoch_cci_wr_mfi", 0.0)
        
        # RSI
        if not pd.isna(rsi):
            if rsi < self.indicator_settings["rsi_oversold"]:
                total_momentum_score += 0.25 * momentum_weight
                breakdown["RSI Oversold"] = 0.25 * momentum_weight
            elif rsi > self.indicator_settings["rsi_overbought"]:
                total_momentum_score -= 0.25 * momentum_weight
                breakdown["RSI Overbought"] = -0.25 * momentum_weight
            self.logger.debug(f"RSI: {rsi:.2f}")

        # StochRSI
        if not pd.isna(stoch_k) and not pd.isna(stoch_d):
            if stoch_k < self.indicator_settings["stoch_rsi_oversold"] and stoch_k > stoch_d: # Bullish cross from oversold
                total_momentum_score += 0.25 * momentum_weight
                breakdown["StochRSI Bull Cross"] = 0.25 * momentum_weight
            elif stoch_k > self.indicator_settings["stoch_rsi_overbought"] and stoch_k < stoch_d: # Bearish cross from overbought
                total_momentum_score -= 0.25 * momentum_weight
                breakdown["StochRSI Bear Cross"] = -0.25 * momentum_weight
            self.logger.debug(f"StochRSI K: {stoch_k:.2f}, D: {stoch_d:.2f}")

        # CCI
        if not pd.isna(cci):
            if cci < self.indicator_settings["cci_oversold"]:
                total_momentum_score += 0.15 * momentum_weight
                breakdown["CCI Oversold"] = 0.15 * momentum_weight
            elif cci > self.indicator_settings["cci_overbought"]:
                total_momentum_score -= 0.15 * momentum_weight
                breakdown["CCI Overbought"] = -0.15 * momentum_weight
            self.logger.debug(f"CCI: {cci:.2f}")

        # Williams %R
        if not pd.isna(wr):
            if wr > self.indicator_settings["williams_r_oversold"]: # Note: WR is inverted, -80 is oversold
                total_momentum_score += 0.15 * momentum_weight
                breakdown["WR Oversold (Bull)"] = 0.15 * momentum_weight
            elif wr < self.indicator_settings["williams_r_overbought"]: # -20 is overbought
                total_momentum_score -= 0.15 * momentum_weight
                breakdown["WR Overbought (Bear)"] = -0.15 * momentum_weight
            self.logger.debug(f"WR: {wr:.2f}")

        # MFI
        if not pd.isna(mfi):
            if mfi < self.indicator_settings["mfi_oversold"]:
                total_momentum_score += 0.20 * momentum_weight
                breakdown["MFI Oversold"] = 0.20 * momentum_weight
            elif mfi > self.indicator_settings["mfi_overbought"]:
                total_momentum_score -= 0.20 * momentum_weight
                breakdown["MFI Overbought"] = -0.20 * momentum_weight
            self.logger.debug(f"MFI: {mfi:.2f}")

        return total_momentum_score, {"breakdown": breakdown}
        
    def _score_bollinger_bands(self, current_close: Decimal) -> Tuple[float, Dict]:
        """Scores based on Bollinger Bands breakout/reversion."""
        bb_upper = self._get_indicator_value("BB_Upper")
        bb_middle = self._get_indicator_value("BB_Middle")
        bb_lower = self._get_indicator_value("BB_Lower")

        score = 0.0
        breakdown = {}

        if not pd.isna(bb_upper) and not pd.isna(bb_middle) and not pd.isna(bb_lower):
            bb_weight = self.weights.get("bollinger_bands", 0.0)
            if current_close > bb_upper: # Price above upper band (potential bearish reversion or strong breakout)
                if self.df["close"].iloc[-2] <= bb_upper: # Just crossed above
                    score += -bb_weight * 0.5 # Initial bearish signal (reversion)
                    breakdown["BB Upper Breakout (Bear)"] = -bb_weight * 0.5
                else: # Continuing above upper band (strong bullish, but risky for reversion strategy)
                    score += bb_weight * 0.2 # Small bullish momentum, but cautious
                    breakdown["BB Above Upper (Bull)"] = bb_weight * 0.2
            elif current_close < bb_lower: # Price below lower band (potential bullish reversion or strong breakout)
                if self.df["close"].iloc[-2] >= bb_lower: # Just crossed below
                    score += bb_weight * 0.5 # Initial bullish signal (reversion)
                    breakdown["BB Lower Breakout (Bull)"] = bb_weight * 0.5
                else: # Continuing below lower band (strong bearish, but risky for reversion strategy)
                    score -= bb_weight * 0.2 # Small bearish momentum, but cautious
                    breakdown["BB Below Lower (Bear)"] = -bb_weight * 0.2
            elif current_close > bb_middle: # Between middle and upper band (bullish tendency)
                score += bb_weight * 0.1
                breakdown["BB Mid-Upper (Bull)"] = bb_weight * 0.1
            elif current_close < bb_middle: # Between middle and lower band (bearish tendency)
                score -= bb_weight * 0.1
                breakdown["BB Mid-Lower (Bear)"] = -bb_weight * 0.1

        return score, {"breakdown": breakdown}
        
    def _score_vwap(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, Dict]:
        """Scores based on VWAP crossover."""
        vwap = self._get_indicator_value("VWAP")
        
        score = 0.0
        breakdown = {}

        if not pd.isna(vwap):
            vwap_weight = self.weights.get("vwap", 0.0)
            if current_close > vwap and prev_close <= vwap: # Bullish crossover
                score += vwap_weight
                breakdown["VWAP Cross (Bull)"] = vwap_weight
            elif current_close < vwap and prev_close >= vwap: # Bearish crossover
                score -= vwap_weight
                breakdown["VWAP Cross (Bear)"] = -vwap_weight
            elif current_close > vwap:
                score += vwap_weight * 0.2
                breakdown["VWAP Above (Bull)"] = vwap_weight * 0.2
            elif current_close < vwap:
                score -= vwap_weight * 0.2
                breakdown["VWAP Below (Bear)"] = -vwap_weight * 0.2
        return score, {"breakdown": breakdown}

    def _score_psar(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, Dict]:
        """Scores based on PSAR direction and crossover."""
        psar_val = self._get_indicator_value("PSAR_Val")
        psar_dir = self._get_indicator_value("PSAR_Dir") # 1 for uptrend, -1 for downtrend

        score = 0.0
        breakdown = {}

        if not pd.isna(psar_val) and not pd.isna(psar_dir):
            psar_weight = self.weights.get("psar", 0.0)
            if psar_dir == 1: # Uptrend, PSAR below price
                score += psar_weight
                breakdown["PSAR Uptrend"] = psar_weight
            elif psar_dir == -1: # Downtrend, PSAR above price
                score -= psar_weight
                breakdown["PSAR Downtrend"] = -psar_weight

            # Check for recent crossover (more aggressive signal)
            if len(self.df) >= 2:
                prev_psar_val = self.df["PSAR_Val"].iloc[-2]
                prev_psar_dir = self.df["PSAR_Dir"].iloc[-2]
                if psar_dir == 1 and prev_psar_dir == -1: # PSAR flipped to bullish
                    score += psar_weight * 0.5 # Add extra weight for flip
                    breakdown["PSAR Flip Bullish"] = psar_weight * 0.5
                elif psar_dir == -1 and prev_psar_dir == 1: # PSAR flipped to bearish
                    score -= psar_weight * 0.5
                    breakdown["PSAR Flip Bearish"] = -psar_weight * 0.5
        return score, {"breakdown": breakdown}

    def _score_fibonacci_levels(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, Dict]:
        """Scores based on interaction with Fibonacci retracement levels."""
        score = 0.0
        breakdown = {}
        fib_weight = self.weights.get("fibonacci_levels", 0.0)

        if self.fib_levels:
            # Check for bounce off support/resistance
            for level_name, level_price in self.fib_levels.items():
                if level_price == 0: continue
                # Define a small tolerance around the level
                tolerance = self.df["ATR"].iloc[-1] * Decimal("0.1") if "ATR" in self.df.columns and not pd.isna(self.df["ATR"].iloc[-1]) else current_close * Decimal("0.001")
                
                if level_name in ["Support 1", "Support 2", "Support 3"] and current_close >= level_price - tolerance and current_close <= level_price + tolerance:
                    # Price near support, check for bounce (previous candle below, current above or strongly bouncing)
                    if prev_close < level_price - tolerance and current_close > level_price:
                        score += fib_weight * 0.5
                        breakdown[f"Fibonacci {level_name} Bounce (Bull)"] = fib_weight * 0.5
                
                if level_name in ["Resistance 1", "Resistance 2", "Resistance 3"] and current_close >= level_price - tolerance and current_close <= level_price + tolerance:
                    # Price near resistance, check for rejection
                    if prev_close > level_price + tolerance and current_close < level_price:
                        score -= fib_weight * 0.5
                        breakdown[f"Fibonacci {level_name} Rejection (Bear)"] = -fib_weight * 0.5

        return score, {"breakdown": breakdown}

    def _score_fibonacci_pivot_points(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, Dict]:
        """Scores based on interaction with Fibonacci Pivot Points (Pivot, R1, R2, S1, S2)."""
        score = 0.0
        breakdown = {}
        pivot_weight = self.weights.get("fibonacci_pivot_points_confluence", 0.0)

        pivot = self._get_indicator_value("PIVOT")
        r1 = self._get_indicator_value("R1")
        s1 = self._get_indicator_value("S1")

        if not pd.isna(pivot) and not pd.isna(r1) and not pd.isna(s1):
            tolerance = current_close * Decimal("0.0005") # Small price-relative tolerance

            if current_close > pivot and prev_close <= pivot: # Cross above Pivot
                score += pivot_weight * 0.3
                breakdown["Pivot Cross Up"] = pivot_weight * 0.3
            elif current_close < pivot and prev_close >= pivot: # Cross below Pivot
                score -= pivot_weight * 0.3
                breakdown["Pivot Cross Down"] = -pivot_weight * 0.3

            if current_close > r1 and prev_close <= r1: # Break above R1
                score += pivot_weight * 0.4
                breakdown["R1 Breakout (Bull)"] = pivot_weight * 0.4
            elif current_close < s1 and prev_close >= s1: # Break below S1
                score -= pivot_weight * 0.4
                breakdown["S1 Breakout (Bear)"] = -pivot_weight * 0.4
            
            # Rejection from R1/S1
            if current_close < r1 and prev_close > r1 and abs(current_close - r1) < tolerance: # Rejection from R1
                score -= pivot_weight * 0.2
                breakdown["R1 Rejection (Bear)"] = -pivot_weight * 0.2
            if current_close > s1 and prev_close < s1 and abs(current_close - s1) < tolerance: # Rejection from S1
                score += pivot_weight * 0.2
                breakdown["S1 Rejection (Bull)"] = pivot_weight * 0.2

        return score, {"breakdown": breakdown}

    def _score_ehlers_supertrend(self, trend_multiplier: float) -> Tuple[float, Dict]:
        """Scores based on Ehlers Supertrend direction and crossover."""
        st_slow_dir = self._get_indicator_value("ST_Slow_Dir")

        score = 0.0
        breakdown = {}

        if not pd.isna(st_slow_dir):
            est_weight = self.weights.get("ehlers_supertrend_alignment", 0.0)
            # Use iloc[-2] for previous direction to detect change
            prev_st_slow_dir = self.df["ST_Slow_Dir"].iloc[-2] if len(self.df) > 1 else np.nan

            if st_slow_dir == 1: # Uptrend
                score_contrib = est_weight * trend_multiplier
                score += score_contrib
                breakdown["Ehlers ST Uptrend"] = score_contrib
                if prev_st_slow_dir == -1: # Just flipped to bullish
                    score += est_weight * 0.5 # Extra weight for fresh signal
                    breakdown["Ehlers ST Flip Bullish"] = est_weight * 0.5
            elif st_slow_dir == -1: # Downtrend
                score_contrib = -est_weight * trend_multiplier
                score += score_contrib
                breakdown["Ehlers ST Downtrend"] = score_contrib
                if prev_st_slow_dir == 1: # Just flipped to bearish
                    score -= est_weight * 0.5
                    breakdown["Ehlers ST Flip Bearish"] = -est_weight * 0.5
        return score, {"breakdown": breakdown}

    def _score_macd(self, trend_multiplier: float) -> Tuple[float, Dict]:
        """Scores based on MACD line and signal crossover, and histogram direction."""
        macd_line = self._get_indicator_value("MACD_Line")
        macd_signal = self._get_indicator_value("MACD_Signal")
        macd_hist = self._get_indicator_value("MACD_Hist")

        score = 0.0
        breakdown = {}

        if not pd.isna(macd_line) and not pd.isna(macd_signal) and not pd.isna(macd_hist):
            macd_weight = self.weights.get("macd_alignment", 0.0)
            
            # MACD Line / Signal Crossover
            if len(self.df) > 1:
                prev_macd_line = self.df["MACD_Line"].iloc[-2]
                prev_macd_signal = self.df["MACD_Signal"].iloc[-2]
                if macd_line > macd_signal and prev_macd_line <= prev_macd_signal: # Bullish cross
                    score_contrib = macd_weight * trend_multiplier
                    score += score_contrib
                    breakdown["MACD Bullish Cross"] = score_contrib
                elif macd_line < macd_signal and prev_macd_line >= prev_macd_signal: # Bearish cross
                    score_contrib = -macd_weight * trend_multiplier
                    score += score_contrib
                    breakdown["MACD Bearish Cross"] = score_contrib

            # MACD Histogram momentum
            if macd_hist > 0:
                score += macd_weight * 0.2
                breakdown["MACD Hist Bullish"] = macd_weight * 0.2
            elif macd_hist < 0:
                score -= macd_weight * 0.2
                breakdown["MACD Hist Bearish"] = -macd_weight * 0.2

        return score, {"breakdown": breakdown}

    def _score_ichimoku_cloud(self, current_close: Decimal) -> Tuple[float, Dict]:
        """Scores based on Ichimoku Cloud signals."""
        tenkan = self._get_indicator_value("Tenkan_Sen")
        kijun = self._get_indicator_value("Kijun_Sen")
        senkou_a = self._get_indicator_value("Senkou_Span_A")
        senkou_b = self._get_indicator_value("Senkou_Span_B")
        chikou = self._get_indicator_value("Chikou_Span")

        score = 0.0
        breakdown = {}

        if all(not pd.isna(x) for x in [tenkan, kijun, senkou_a, senkou_b, chikou]):
            ichimoku_weight = self.weights.get("ichimoku_confluence", 0.0)

            # Tenkan/Kijun cross
            if tenkan > kijun:
                score += ichimoku_weight * 0.3
                breakdown["Ichimoku Tenkan > Kijun (Bull)"] = ichimoku_weight * 0.3
            elif tenkan < kijun:
                score -= ichimoku_weight * 0.3
                breakdown["Ichimoku Tenkan < Kijun (Bear)"] = -ichimoku_weight * 0.3

            # Price relative to Cloud
            kumo_upper = max(senkou_a, senkou_b)
            kumo_lower = min(senkou_a, senkou_b)

            if current_close > kumo_upper:
                score += ichimoku_weight * 0.4
                breakdown["Ichimoku Price Above Cloud (Bull)"] = ichimoku_weight * 0.4
            elif current_close < kumo_lower:
                score -= ichimoku_weight * 0.4
                breakdown["Ichimoku Price Below Cloud (Bear)"] = -ichimoku_weight * 0.4

            # Cloud twist (Senkou A vs B)
            if senkou_a > senkou_b:
                score += ichimoku_weight * 0.1 # Bullish cloud
                breakdown["Ichimoku Bullish Cloud"] = ichimoku_weight * 0.1
            elif senkou_a < senkou_b:
                score -= ichimoku_weight * 0.1 # Bearish cloud
                breakdown["Ichimoku Bearish Cloud"] = -ichimoku_weight * 0.1

            # Chikou Span relative to price
            if chikou > self.df["close"].iloc[-isd["ichimoku_chikou_span_offset"]]: # Chikou above past price (bullish)
                score += ichimoku_weight * 0.2
                breakdown["Ichimoku Chikou Above (Bull)"] = ichimoku_weight * 0.2
            elif chikou < self.df["close"].iloc[-isd["ichimoku_chikou_span_offset"]]: # Chikou below past price (bearish)
                score -= ichimoku_weight * 0.2
                breakdown["Ichimoku Chikou Below (Bear)"] = -ichimoku_weight * 0.2

        return score, {"breakdown": breakdown}

    def _score_obv(self) -> Tuple[float, Dict]:
        """Scores based on OBV and its EMA crossover."""
        obv = self._get_indicator_value("OBV")
        obv_ema = self._get_indicator_value("OBV_EMA")

        score = 0.0
        breakdown = {}

        if not pd.isna(obv) and not pd.isna(obv_ema):
            obv_weight = self.weights.get("obv_momentum", 0.0)
            if len(self.df) > 1:
                prev_obv = self.df["OBV"].iloc[-2]
                prev_obv_ema = self.df["OBV_EMA"].iloc[-2]
                if obv > obv_ema and prev_obv <= prev_obv_ema: # OBV bullish cross
                    score += obv_weight
                    breakdown["OBV Bullish Cross"] = obv_weight
                elif obv < obv_ema and prev_obv >= prev_obv_ema: # OBV bearish cross
                    score -= obv_weight
                    breakdown["OBV Bearish Cross"] = -obv_weight
        return score, {"breakdown": breakdown}

    def _score_cmf(self) -> Tuple[float, Dict]:
        """Scores based on Chaikin Money Flow (CMF)."""
        cmf = self._get_indicator_value("CMF")

        score = 0.0
        breakdown = {}

        if not pd.isna(cmf):
            cmf_weight = self.weights.get("cmf_flow", 0.0)
            if cmf > 0: # Positive money flow
                score += cmf_weight
                breakdown["CMF Positive Flow"] = cmf_weight
            elif cmf < 0: # Negative money flow
                score -= cmf_weight
                breakdown["CMF Negative Flow"] = -cmf_weight
        return score, {"breakdown": breakdown}

    def _score_volatility_index(self, signal_score_current: float) -> Tuple[float, Dict]:
        """Adjusts signal score based on Volatility Index. High volatility can amplify or suppress."""
        volatility_index = self._get_indicator_value("Volatility_Index")
        
        score = 0.0
        breakdown = {}

        if not pd.isna(volatility_index):
            vol_weight = self.weights.get("volatility_index_signal", 0.0)
            # Example logic: Amplify signals during moderate volatility, reduce during extreme or very low.
            # This is a conceptual example, actual implementation might involve non-linear adjustments.
            
            # Assuming average volatility around 1.0 (normalized index)
            if volatility_index > 1.5: # Very high volatility
                # Potentially reduce score to avoid whipsaws, or increase for strong breakouts
                score -= vol_weight * 0.5 * np.sign(signal_score_current) # Reduce signal confidence
                breakdown["Volatility Very High"] = -vol_weight * 0.5 * np.sign(signal_score_current)
            elif volatility_index < 0.5: # Very low volatility
                # Also reduce score as markets might be illiquid or consolidating
                score -= vol_weight * 0.2 * np.sign(signal_score_current)
                breakdown["Volatility Very Low"] = -vol_weight * 0.2 * np.sign(signal_score_current)
            else: # Moderate volatility - maybe amplify
                score += vol_weight * 0.1 * np.sign(signal_score_current)
                breakdown["Volatility Moderate"] = vol_weight * 0.1 * np.sign(signal_score_current)
        return score, {"breakdown": breakdown}

    def _score_vwma_cross(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, Dict]:
        """Scores based on VWMA crossover with price."""
        vwma = self._get_indicator_value("VWMA")

        score = 0.0
        breakdown = {}

        if not pd.isna(vwma):
            vwma_weight = self.weights.get("vwma_cross", 0.0)
            if current_close > vwma and prev_close <= vwma: # Bullish cross
                score += vwma_weight
                breakdown["VWMA Bullish Cross"] = vwma_weight
            elif current_close < vwma and prev_close >= vwma: # Bearish cross
                score -= vwma_weight
                breakdown["VWMA Bearish Cross"] = -vwma_weight
        return score, {"breakdown": breakdown}

    def _score_volume_delta(self) -> Tuple[float, Dict]:
        """Scores based on volume delta indicating buying/selling pressure."""
        volume_delta = self._get_indicator_value("Volume_Delta")
        
        score = 0.0
        breakdown = {}

        if not pd.isna(volume_delta):
            vol_delta_weight = self.weights.get("volume_delta_signal", 0.0)
            threshold = Decimal(str(self.indicator_settings["volume_delta_threshold"]))
            if volume_delta > threshold: # Strong buying pressure
                score += vol_delta_weight
                breakdown["Volume Delta High Buy"] = vol_delta_weight
            elif volume_delta < -threshold: # Strong selling pressure
                score -= vol_delta_weight
                breakdown["Volume Delta High Sell"] = -vol_delta_weight
        return score, {"breakdown": breakdown}
    
    def _score_kaufman_ama_cross(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, Dict]:
        """Scores based on Kaufman Adaptive Moving Average (KAMA) crossover with price."""
        kama = self._get_indicator_value("Kaufman_AMA")

        score = 0.0
        breakdown = {}

        if not pd.isna(kama):
            kama_weight = self.weights.get("kaufman_ama_cross", 0.0)
            if current_close > kama and prev_close <= kama: # Bullish cross
                score += kama_weight
                breakdown["KAMA Bullish Cross"] = kama_weight
            elif current_close < kama and prev_close >= kama: # Bearish cross
                score -= kama_weight
                breakdown["KAMA Bearish Cross"] = -kama_weight
        return score, {"breakdown": breakdown}

    def _score_relative_volume(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, Dict]:
        """Scores based on Relative Volume (above average volume)."""
        relative_volume = self._get_indicator_value("Relative_Volume")
        
        score = 0.0
        breakdown = {}

        if not pd.isna(relative_volume):
            rv_weight = self.weights.get("relative_volume_confirmation", 0.0)
            threshold = Decimal(str(self.indicator_settings["relative_volume_threshold"]))
            if relative_volume > threshold: # High relative volume confirms current price movement
                if current_close > prev_close: # Bullish candle
                    score += rv_weight * 0.5
                    breakdown["Relative Volume (Bull)"] = rv_weight * 0.5
                elif current_close < prev_close: # Bearish candle
                    score -= rv_weight * 0.5
                    breakdown["Relative Volume (Bear)"] = -rv_weight * 0.5
        return score, {"breakdown": breakdown}

    def _score_market_structure(self) -> Tuple[float, Dict]:
        """Scores based on detected market structure (e.g., higher highs/lows)."""
        market_structure_trend = self._get_indicator_value("Market_Structure_Trend")
        
        score = 0.0
        breakdown = {}

        if market_structure_trend == "Uptrend":
            ms_weight = self.weights.get("market_structure_confluence", 0.0)
            score += ms_weight
            breakdown["Market Structure Uptrend"] = ms_weight
        elif market_structure_trend == "Downtrend":
            ms_weight = self.weights.get("market_structure_confluence", 0.0)
            score -= ms_weight
            breakdown["Market Structure Downtrend"] = -ms_weight
        
        return score, {"breakdown": breakdown}

    def _score_dema_crossover(self) -> Tuple[float, Dict]:
        """Scores based on DEMA crossover with price or another moving average."""
        dema = self._get_indicator_value("DEMA")
        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close

        score = 0.0
        breakdown = {}

        if not pd.isna(dema):
            dema_weight = self.weights.get("dema_crossover", 0.0)
            if current_close > dema and prev_close <= dema: # Bullish cross
                score += dema_weight
                breakdown["DEMA Bullish Cross"] = dema_weight
            elif current_close < dema and prev_close >= dema: # Bearish cross
                score -= dema_weight
                breakdown["DEMA Bearish Cross"] = -dema_weight
        return score, {"breakdown": breakdown}

    def _score_keltner_channels(self, current_close: Decimal, prev_close: Decimal) -> Tuple[float, Dict]:
        """Scores based on Keltner Channels breakout/reversion."""
        kc_upper = self._get_indicator_value("Keltner_Upper")
        kc_middle = self._get_indicator_value("Keltner_Middle")
        kc_lower = self._get_indicator_value("Keltner_Lower")

        score = 0.0
        breakdown = {}

        if not pd.isna(kc_upper) and not pd.isna(kc_middle) and not pd.isna(kc_lower):
            kc_weight = self.weights.get("keltner_breakout", 0.0)
            if current_close > kc_upper and prev_close <= kc_upper: # Bullish breakout
                score += kc_weight
                breakdown["Keltner Breakout (Bull)"] = kc_weight
            elif current_close < kc_lower and prev_close >= kc_lower: # Bearish breakout
                score -= kc_weight
                breakdown["Keltner Breakout (Bear)"] = -kc_weight
            elif current_close > kc_middle:
                score += kc_weight * 0.2
                breakdown["Keltner Above Middle (Bull)"] = kc_weight * 0.2
            elif current_close < kc_middle:
                score -= kc_weight * 0.2
                breakdown["Keltner Below Middle (Bear)"] = -kc_weight * 0.2
        return score, {"breakdown": breakdown}

    def _score_roc_signals(self) -> Tuple[float, Dict]:
        """Scores based on Rate of Change (ROC) signals (oversold/overbought)."""
        roc = self._get_indicator_value("ROC")
        
        score = 0.0
        breakdown = {}

        if not pd.isna(roc):
            roc_weight = self.weights.get("roc_signal", 0.0)
            if roc < self.indicator_settings["roc_oversold"]:
                score += roc_weight * 0.5 # Bullish signal
                breakdown["ROC Oversold (Bull)"] = roc_weight * 0.5
            elif roc > self.indicator_settings["roc_overbought"]:
                score -= roc_weight * 0.5 # Bearish signal
                breakdown["ROC Overbought (Bear)"] = -roc_weight * 0.5
            
            # ROC cross zero line (momentum shift)
            if len(self.df) > 1:
                prev_roc = Decimal(str(self.df["ROC"].iloc[-2]))
                if roc > 0 and prev_roc <= 0: # Bullish momentum shift
                    score += roc_weight * 0.3
                    breakdown["ROC Bullish Cross Zero"] = roc_weight * 0.3
                elif roc < 0 and prev_roc >= 0: # Bearish momentum shift
                    score -= roc_weight * 0.3
                    breakdown["ROC Bearish Cross Zero"] = -roc_weight * 0.3
        return score, {"breakdown": breakdown}

    def _score_candlestick_patterns(self) -> Tuple[float, Dict]:
        """Scores based on detected candlestick patterns."""
        pattern = self._get_indicator_value("Candlestick_Pattern")
        
        score = 0.0
        breakdown = {}

        if pattern and pattern != "NO_PATTERN":
            cs_weight = self.weights.get("candlestick_confirmation", 0.0)
            # Assign weights based on pattern type (example)
            bullish_patterns = ["Hammer", "Bullish Engulfing", "Morning Star", "Piercing Line", "Three White Soldiers"]
            bearish_patterns = ["Hanging Man", "Bearish Engulfing", "Evening Star", "Dark Cloud Cover", "Three Black Crows"]

            if pattern in bullish_patterns:
                score += cs_weight
                breakdown[f"Candlestick: {pattern} (Bull)"] = cs_weight
            elif pattern in bearish_patterns:
                score -= cs_weight
                breakdown[f"Candlestick: {pattern} (Bear)"] = -cs_weight
            else: # Neutral or less strong patterns, still provides info
                breakdown[f"Candlestick: {pattern} (Neutral)"] = 0.0
        return score, {"breakdown": breakdown}

    def _score_orderbook_imbalance(self, orderbook_data: Optional[dict]) -> Tuple[float, Dict]:
        """Scores order book imbalance and identifies potential Support/Resistance levels."""
        imbalance_contrib = 0.0
        signal_breakdown_contrib = {}
        if self.config["indicators"].get("orderbook_imbalance", False) and orderbook_data:
            try:
                bids, asks = orderbook_data.get("b", []), orderbook_data.get("a", [])
                bid_volume = sum(Decimal(b[1]) for b in bids if b[1])
                ask_volume = sum(Decimal(a[1]) for a in asks if a[1])
                total_volume = bid_volume + ask_volume
                
                if total_volume > 0:
                    imbalance = _safe_divide_decimal(bid_volume - ask_volume, total_volume)
                    imbalance_contrib = imbalance * self.weights.get("orderbook_imbalance", 0)
                    self.logger.debug(f"Orderbook Imbalance: {imbalance:.4f}")
                
                # Calculate S/R levels from order book depth
                self.calculate_support_resistance_from_orderbook(orderbook_data)
                signal_breakdown_contrib["Orderbook Imbalance"] = imbalance_contrib
            except Exception as e:
                self.logger.error(f"Error processing orderbook data for scoring: {e}\n{traceback.format_exc()}")
        return imbalance_contrib, signal_breakdown_contrib

    def calculate_support_resistance_from_orderbook(self, orderbook_data: dict) -> None:
        """Identifies Support/Resistance levels from order book volume peaks."""
        bids, asks = orderbook_data.get("b", []), orderbook_data.get("a", [])
        max_bid_volume, support_level = Decimal("0"), Decimal("0")
        max_ask_volume, resistance_level = Decimal("0"), Decimal("0")

        # Find highest volume bid for Support Level
        for bid_price_str, bid_volume_str in bids:
            bid_volume = Decimal(bid_volume_str)
            if bid_volume > max_bid_volume:
                max_bid_volume = bid_volume
                support_level = Decimal(bid_price_str)

        # Find highest volume ask for Resistance Level
        for ask_price_str, ask_volume_str in asks:
            ask_volume = Decimal(ask_volume_str)
            if ask_volume > max_ask_volume:
                max_ask_volume = ask_volume
                resistance_level = Decimal(ask_price_str)

        price_precision = self.config["trade_management"]["price_precision"]
        if support_level > 0:
            self.indicator_values["Support_Level"] = support_level.quantize(Decimal(f"1e-{price_precision}"), rounding=ROUND_DOWN)
            self.logger.debug(f"Identified Support Level: {support_level}")
        if resistance_level > 0:
            self.indicator_values["Resistance_Level"] = resistance_level.quantize(Decimal(f"1e-{price_precision}"), rounding=ROUND_DOWN)
            self.logger.debug(f"Identified Resistance Level: {resistance_level}")

    def _score_mtf_confluence(self, mtf_trends: Dict[str, str]) -> Tuple[float, Dict]:
        """Scores the confluence of trends across multiple timeframes."""
        mtf_contribution = 0.0
        signal_breakdown_contrib = {}
        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_count = sum(1 for trend in mtf_trends.values() if trend == "UP")
            mtf_sell_count = sum(1 for trend in mtf_trends.values() if trend == "DOWN")
            total_mtf_indicators = len(mtf_trends)

            if total_mtf_indicators > 0:
                mtf_weight = self.weights.get("mtf_trend_confluence", 0.0)
                # Calculate score proportionally to the agreement
                normalized_mtf_score = (mtf_buy_count - mtf_sell_count) / total_mtf_indicators
                mtf_contribution = mtf_weight * normalized_mtf_score
                
                self.logger.debug(f"MTF Confluence: Buy={mtf_buy_count}, Sell={mtf_sell_count}, Total={total_mtf_indicators}. Score contribution: {mtf_contribution:.2f}")
                signal_breakdown_contrib["MTF Confluence"] = mtf_contribution
        return mtf_contribution, signal_breakdown_contrib

    def _dynamic_threshold(self, base_threshold: float) -> float:
        """Adjusts the signal threshold dynamically based on ATR volatility."""
        atr_now = self._get_indicator_value("ATR", Decimal("0.0"))
        # Ensure ATR data is valid and we have enough history for rolling calculations
        if "ATR" not in self.df.columns or self.df["ATR"].isnull().all() or len(self.df["ATR"]) < 50:
            return base_threshold
        
        atr_ma_series = self.df["ATR"].rolling(50).mean()
        if atr_ma_series.empty or atr_ma_series.iloc[-1] <= 0: return base_threshold
        
        atr_ma = float(atr_ma_series.iloc[-1])
        # Calculate volatility ratio, clipping it to avoid extreme adjustments
        ratio = float(np.clip(float(atr_now) / atr_ma, 0.9, 1.5))
        return base_threshold * ratio

    def _market_regime(self) -> str:
        """Determines market regime (TRENDING, RANGING, SIDEWAYS) using ADX and Bollinger Bands."""
        adx, bb_u, bb_m, bb_l = self._get_indicator_value("ADX"), self._get_indicator_value("BB_Upper"), self._get_indicator_value("BB_Middle"), self._get_indicator_value("BB_Lower")
        
        # Check for valid data before calculation
        if pd.isna(adx) or pd.isna(bb_u) or pd.isna(bb_m) or pd.isna(bb_l) or bb_m == Decimal("0"):
            return "UNKNOWN"
        
        band_width_pct = float((bb_u - bb_l) / bb_m) if bb_m != Decimal("0") else 0 # Calculate Bollinger Band width percentage

        # Determine regime based on ADX and Bandwidth
        if float(adx) >= ADX_STRONG_TREND_THRESHOLD or band_width_pct >= 0.03: return "TRENDING"
        elif float(adx) <= ADX_WEAK_TREND_THRESHOLD and band_width_pct <= 0.01: return "RANGING"
        return "SIDEWAYS"

    def generate_trading_signal(self, current_price: Decimal, orderbook_data: Optional[dict], mtf_trends: Dict[str, str]) -> Tuple[str, float, Dict[str, float]]:
        """Generates a trading signal (BUY, SELL, HOLD) based on aggregated indicator scores."""
        signal_score = 0.0
        signal_breakdown: Dict[str, float] = {}
        if self.df.empty: return "HOLD", 0.0, {} # Cannot generate signal if DataFrame is empty

        # Get current and previous close prices safely
        current_close = Decimal(str(self.df["close"].iloc[-1])) if not self.df.empty else Decimal("0")
        prev_close = Decimal(str(self.df["close"].iloc[-2]) if len(self.df) > 1 else current_close)
        
        trend_strength_multiplier = 1.0 # Initial multiplier

        # --- Score indicators ---
        # Score ADX first to establish trend strength multiplier
        adx_score, adx_info = self._score_adx(trend_strength_multiplier)
        signal_score += adx_score
        signal_breakdown.update(adx_info["breakdown"])
        trend_strength_multiplier = adx_info["trend_strength_multiplier"] # Update multiplier based on ADX

        # Aggregate scores from all enabled indicators
        scorers_config = [
            (self._score_ema_alignment, [current_close, trend_strength_multiplier]),
            (self._score_sma_trend_filter, [current_close]),
            (self._score_momentum_indicators, []),
            (self._score_bollinger_bands, [current_close]),
            (self._score_vwap, [current_close, prev_close]),
            (self._score_psar, [current_close, prev_close]),
            (self._score_fibonacci_levels, [current_close, prev_close]),
            (self._score_fibonacci_pivot_points, [current_close, prev_close]),
            (self._score_ehlers_supertrend, [trend_strength_multiplier]),
            (self._score_macd, [trend_strength_multiplier]),
            (self._score_ichimoku_cloud, [current_close]),
            (self._score_obv, []), (self._score_cmf, []),
            (self._score_vwma_cross, [current_close, prev_close]),
            (self._score_volume_delta, []),
            (self._score_kaufman_ama_cross, [current_close, prev_close]),
            (self._score_relative_volume, [current_close, prev_close]),
            (self._score_market_structure, []),
            (self._score_dema_crossover, []),
            (self._score_keltner_channels, [current_close, prev_close]),
            (self._score_roc_signals, []),
            (self._score_candlestick_patterns, []),
        ]
        for scorer_func, args in scorers_config:
            contrib, breakdown_dict = scorer_func(*args)
            signal_score += contrib
            signal_breakdown.update(breakdown_dict)

        # --- Post-indicator aggregation scores ---
        vol_contrib, vol_breakdown = self._score_volatility_index(signal_score)
        signal_score += vol_contrib; signal_breakdown.update(vol_breakdown)
        imbalance_score, imbalance_breakdown = self._score_orderbook_imbalance(orderbook_data)
        signal_score += imbalance_score; signal_breakdown.update(imbalance_breakdown)
        mtf_score, mtf_breakdown = self._score_mtf_confluence(mtf_trends)
        signal_score += mtf_score; signal_breakdown.update(mtf_breakdown)

        # --- Final Signal Decision ---
        base_threshold = max(float(self.config.get("signal_score_threshold", 2.0)), 1.0)
        dynamic_threshold = self._dynamic_threshold(base_threshold) # Adjust threshold based on volatility
        
        final_signal = "HOLD" # Default signal
        now_ts = int(time.time())
        cooldown_sec = int(self.config.get("cooldown_sec", 0))
        hysteresis_ratio = float(self.config.get("hysteresis_ratio", 0.85))

        # Determine BUY/SELL signal based on score and threshold
        is_strong_buy = signal_score >= dynamic_threshold
        is_strong_sell = signal_score <= -dynamic_threshold
        
        # Apply hysteresis: only switch signal if score crosses threshold significantly
        # or if the previous state wasn't HOLD.
        should_override_hold = True # Assume we want to always consider the signal if strong enough
        
        # Apply hysteresis only if the direction is changing and the score is relatively close to the threshold
        # and the previous score was in the "other" direction.
        if (self.config["_last_score"] > 0 and is_strong_sell and signal_score > (-dynamic_threshold * hysteresis_ratio)) or \
           (self.config["_last_score"] < 0 and is_strong_buy and signal_score < (dynamic_threshold * hysteresis_ratio)):
            self.logger.debug(f"Hysteresis check: Prev score {self.config['_last_score']:.2f}, Current score {signal_score:.2f}, Threshold {dynamic_threshold:.2f}, Hysteresis ratio {hysteresis_ratio}. Signal might be filtered.")
            should_override_hold = False # Do not issue a signal if hysteresis prevents it

        if is_strong_buy and should_override_hold: final_signal = "BUY"
        elif is_strong_sell and should_override_hold: final_signal = "SELL"
        
        # Apply cooldown period: ignore new signals if within cooldown window
        if final_signal != "HOLD":
            if now_ts - self._last_signal_ts < cooldown_sec:
                self.logger.info(f"Signal '{final_signal}' ignored due to cooldown ({cooldown_sec - (now_ts - self._last_signal_ts)}s remaining).")
                final_signal = "HOLD"
            else:
                self._last_signal_ts = now_ts # Update signal timestamp only if signal is issued

        # Update transient state variables for next loop's analysis
        self.config["_last_score"] = float(signal_score)
        self.config["_last_signal_ts"] = self._last_signal_ts
        
        self.logger.info(f"Generated Signal: {final_signal} (Score: {signal_score:.2f}, Threshold: {dynamic_threshold:.2f})")
        return final_signal, float(signal_score), signal_breakdown

    # --- Helper methods for display ---
    def _market_regime(self) -> str:
        """Determines market regime (TRENDING, RANGING, SIDEWAYS) using ADX and Bollinger Bands."""
        adx, bb_u, bb_m, bb_l = self._get_indicator_value("ADX"), self._get_indicator_value("BB_Upper"), self._get_indicator_value("BB_Middle"), self._get_indicator_value("BB_Lower")
        
        if pd.isna(adx) or pd.isna(bb_u) or pd.isna(bb_m) or pd.isna(bb_l) or bb_m == Decimal("0"): return "UNKNOWN"
        band_width_pct = float((bb_u - bb_l) / bb_m) if bb_m != Decimal("0") else 0

        if float(adx) >= ADX_STRONG_TREND_THRESHOLD or band_width_pct >= 0.03: return "TRENDING"
        elif float(adx) <= ADX_WEAK_TREND_THRESHOLD and band_width_pct <= 0.01: return "RANGING"
        return "SIDEWAYS"

# --- Guardrails and Filters ---
def in_allowed_session(config: Dict) -> bool:
    """Checks if the current UTC time falls within allowed trading sessions."""
    if not config["session_filter"]["enabled"]: return True
    
    now_utc = datetime.now(timezone.utc).time()
    
    for start_str, end_str in config["session_filter"]["utc_allowed"]:
        start_time = datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.strptime(end_str, "%H:%M").time()
        
        if start_time <= end_time:
            if start_time <= now_utc <= end_time: return True
        else: # Overnight session (e.g., 22:00 - 04:00)
            if now_utc >= start_time or now_utc <= end_time: return True
            
    return False

def get_spread_bps(orderbook_data: dict) -> float:
    """Calculates the bid-ask spread in basis points (bps)."""
    if not orderbook_data or not orderbook_data.get("bids") or not orderbook_data.get("asks"): return float('inf')
    
    best_bid = Decimal(orderbook_data["bids"][0][0])
    best_ask = Decimal(orderbook_data["asks"][0][0])
    
    if best_bid.is_zero() or best_ask.is_zero(): return float('inf')
    
    spread = (best_ask - best_bid) / best_bid
    return float(spread * Decimal("10000")) # Convert to basis points

def expected_value(performance_tracker: PerformanceTracker) -> Decimal:
    """Calculates the Expected Value (EV) of a trade based on historical performance."""
    if performance_tracker.wins + performance_tracker.losses == 0: return Decimal("0")

    win_rate = Decimal(performance_tracker.wins) / (performance_tracker.wins + performance_tracker.losses)
    loss_rate = Decimal(performance_tracker.losses) / (performance_tracker.wins + performance_tracker.losses)

    avg_win = performance_tracker.gross_profit / performance_tracker.wins if performance_tracker.wins > 0 else Decimal("0")
    avg_loss = performance_tracker.gross_loss / performance_tracker.losses if performance_tracker.losses > 0 else Decimal("0")
    
    ev = (win_rate * avg_win) - (loss_rate * avg_loss)
    return ev

def adapt_exit_params(performance_tracker: PerformanceTracker, config: Dict) -> Tuple[Decimal, Decimal]:
    """Dynamically adapts TP/SL multiples based on recent performance."""
    base_tp = Decimal(str(config["trade_management"]["take_profit_atr_multiple"]))
    base_sl = Decimal(str(config["trade_management"]["stop_loss_atr_multiple"]))

    # Simple adaptation: if win rate is high, try slightly higher TP and tighter SL.
    # If win rate is low, revert to base or try tighter TP/wider SL.
    # More advanced logic would involve average R:R, profit factor, etc.
    
    total_trades = performance_tracker.wins + performance_tracker.losses
    if total_trades < 10: # Need sufficient trades for meaningful stats
        return base_tp, base_sl

    win_rate = performance_tracker.wins / total_trades
    
    if win_rate > 0.6: # Good win rate, try to capture more profit and cut losses faster
        return base_tp * Decimal("1.1"), base_sl * Decimal("0.9")
    elif win_rate < 0.4: # Poor win rate, maybe adjust to avoid being stopped out too early
        return base_tp * Decimal("0.9"), base_sl * Decimal("1.1")
    
    return base_tp, base_sl

# --- Display Functions ---
def display_indicator_values_and_price(config: dict, logger: logging.Logger, current_price: Decimal, analyzer: TradingAnalyzer, mtf_trends: dict, signal_breakdown: Optional[dict] = None):
    """Displays current market data, indicator values, and a concise trend summary."""
    logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
    logger.info(f"{NEON_GREEN}Current Price: {current_price.normalize()}{RESET}")

    if analyzer.df.empty:
        logger.warning(f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.{RESET}")
        return

    logger.info(f"{NEON_CYAN}--- Indicator Values ---{RESET}")
    # Display latest values for each calculated indicator
    for indicator_name, value in analyzer.indicator_values.items():
        color = INDICATOR_COLORS.get(indicator_name, NEON_YELLOW)
        if isinstance(value, Decimal): logger.info(f"  {color}{indicator_name:<20}: {value.normalize()}{RESET}")
        elif isinstance(value, float): logger.info(f"  {color}{indicator_name:<20}: {value:.8f}{RESET}")
        else: logger.info(f"  {color}{indicator_name:<20}: {value}{RESET}")

    # Display Fibonacci Levels if calculated and enabled
    if analyzer.fib_levels:
        logger.info(f"{NEON_CYAN}--- Fibonacci Retracement Levels ---{RESET}")
        for level_name, level_price in analyzer.fib_levels.items(): logger.info(f"  {NEON_YELLOW}{level_name:<20}: {level_price.normalize()}{RESET}")

    # Display Fibonacci Pivot Points if enabled and calculated
    if config["indicators"].get("fibonacci_pivot_points", False) and any(k in analyzer.indicator_values for k in ["PIVOT", "R1", "S1"]):
        logger.info(f"{NEON_CYAN}--- Fibonacci Pivot Points ---{RESET}")
        for key in ["PIVOT", "R1", "R2", "S1", "S2"]:
            if key in analyzer.indicator_values:
                logger.info(f"  {INDICATOR_COLORS.get(key, NEON_YELLOW)}{key:<20}: {analyzer.indicator_values[key].normalize()}{RESET}")

    # Display Orderbook Support/Resistance Levels if found
    if ("Support_Level" in analyzer.indicator_values or "Resistance_Level" in analyzer.indicator_values):
        logger.info(f"{NEON_CYAN}--- Orderbook S/R Levels ---{RESET}")
        if "Support_Level" in analyzer.indicator_values: logger.info(f"  {INDICATOR_COLORS.get('Support_Level', NEON_YELLOW)}{'Support Level':<20}: {analyzer.indicator_values['Support_Level'].normalize()}{RESET}")
        if "Resistance_Level" in analyzer.indicator_values: logger.info(f"  {INDICATOR_COLORS.get('Resistance_Level', NEON_YELLOW)}{'Resistance Level':<20}: {analyzer.indicator_values['Resistance_Level'].normalize()}{RESET}")

    # Display Multi-Timeframe Trend Confluence
    if mtf_trends:
        logger.info(f"{NEON_CYAN}--- Multi-Timeframe Trends ---{RESET}")
        for tf_indicator, trend in mtf_trends.items(): logger.info(f"  {NEON_YELLOW}{tf_indicator:<20}: {trend}{RESET}")

    # Display Signal Score Breakdown (sorted by contribution magnitude)
    if signal_breakdown:
        logger.info(f"{NEON_CYAN}--- Signal Score Breakdown ---{RESET}")
        sorted_breakdown = sorted(signal_breakdown.items(), key=lambda item: abs(item[1]), reverse=True)
        for indicator, contribution in sorted_breakdown:
            color = (Fore.GREEN if contribution > 0 else (Fore.RED if contribution < 0 else Fore.YELLOW))
            logger.info(f"  {color}{indicator:<25}: {contribution: .2f}{RESET}")

    # --- Concise Trend Summary ---
    logger.info(f"{NEON_PURPLE}--- Current Trend Summary ---{RESET}")
    trend_summary_lines = []
    ema_short, ema_long = analyzer._get_indicator_value("EMA_Short"), analyzer._get_indicator_value("EMA_Long")
    if not pd.isna(ema_short) and not pd.isna(ema_long):
        trend_summary_lines.append(f"{Fore.GREEN if ema_short > ema_long else (Fore.RED if ema_short < ema_long else Fore.YELLOW)}EMA Cross  : {'▲ Up' if ema_short > ema_long else ('▼ Down' if ema_short < ema_long else '↔ Sideways')}{RESET}")

    st_slow_dir = analyzer._get_indicator_value("ST_Slow_Dir")
    if not pd.isna(st_slow_dir):
        trend_summary_lines.append(f"{Fore.GREEN if st_slow_dir == 1 else (Fore.RED if st_slow_dir == -1 else Fore.YELLOW)}SuperTrend : {'▲ Up' if st_slow_dir == 1 else ('▼ Down' if st_slow_dir == -1 else '↔ Sideways')}{RESET}")

    macd_hist = analyzer._get_indicator_value("MACD_Hist")
    if not pd.isna(macd_hist) and "MACD_Hist" in analyzer.df.columns and len(analyzer.df) > 1:
        prev_macd_hist = Decimal(str(analyzer.df["MACD_Hist"].iloc[-2]))
        if macd_hist > 0 and prev_macd_hist <= 0: trend_summary_lines.append(f"{Fore.GREEN}MACD Hist  : ↑ Bullish Cross{RESET}")
        elif macd_hist < 0 and prev_macd_hist >= 0: trend_summary_lines.append(f"{Fore.RED}MACD Hist  : ↓ Bearish Cross{RESET}")
        elif macd_hist > 0: trend_summary_lines.append(f"{Fore.LIGHTGREEN_EX}MACD Hist  : Above 0{RESET}")
        elif macd_hist < 0: trend_summary_lines.append(f"{Fore.LIGHTRED_EX}MACD Hist  : Below 0{RESET}")
    
    adx_val = analyzer._get_indicator_value("ADX")
    if not pd.isna(adx_val):
        strength = f"({adx_val:.0f})"
        if adx_val >= ADX_STRONG_TREND_THRESHOLD:
            plus_di, minus_di = analyzer._get_indicator_value("PlusDI"), analyzer._get_indicator_value("MinusDI")
            if not pd.isna(plus_di) and not pd.isna(minus_di):
                if plus_di > minus_di: trend_summary_lines.append(f"{Fore.LIGHTGREEN_EX}ADX Trend  : Strong Up {strength}{RESET}")
                else: trend_summary_lines.append(f"{Fore.LIGHTRED_EX}ADX Trend  : Strong Down {strength}{RESET}")
        elif adx_val <= ADX_WEAK_TREND_THRESHOLD: trend_summary_lines.append(f"{Fore.YELLOW}ADX Trend  : Weak/Ranging ({adx_val:.0f}){RESET}")
        else: trend_summary_lines.append(f"{Fore.CYAN}ADX Trend  : Moderate ({adx_val:.0f}){RESET}")

    senkou_span_a, senkou_span_b = analyzer._get_indicator_value("Senkou_Span_A"), analyzer._get_indicator_value("Senkou_Span_B")
    if not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b):
        kumo_upper, kumo_lower = max(senkou_span_a, senkou_span_b), min(senkou_span_a, senkou_span_b)
        if current_price > kumo_upper: trend_summary_lines.append(f"{Fore.GREEN}Ichimoku   : Above Kumo{RESET}")
        elif current_price < kumo_lower: trend_summary_lines.append(f"{Fore.RED}Ichimoku   : Below Kumo{RESET}")
        else: trend_summary_lines.append(f"{Fore.YELLOW}Ichimoku   : Inside Kumo{RESET}")

    if mtf_trends: # Summarize MTF confluence
        up_count = sum(1 for t in mtf_trends.values() if t == "UP")
        down_count = sum(1 for t in mtf_trends.values() if t == "DOWN")
        total = len(mtf_trends)
        if total > 0:
            if up_count == total: trend_summary_lines.append(f"{Fore.GREEN}MTF Confl. : All Bullish ({up_count}/{total}){RESET}")
            elif down_count == total: trend_summary_lines.append(f"{Fore.RED}MTF Confl. : All Bearish ({down_count}/{total}){RESET}")
            elif up_count > down_count: trend_summary_lines.append(f"{Fore.LIGHTGREEN_EX}MTF Confl. : Mostly Bullish ({up_count}/{total}){RESET}")
            elif down_count > up_count: trend_summary_lines.append(f"{Fore.LIGHTRED_EX}MTF Confl. : Mostly Bearish ({down_count}/{total}){RESET}")
            else: trend_summary_lines.append(f"{Fore.YELLOW}MTF Confl. : Mixed ({up_count}/{total} Bull, {down_count}/{total} Bear){RESET}")

    for line in trend_summary_lines: logger.info(f"  {line}")
    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")

# --- Main Bot Logic ---
def main():
    """Main function orchestrating the bot's execution cycle."""
    global global_logger, pybit_client, position_manager, performance_tracker, exec_sync, heartbeat, analyzer # Declare globals

    # Setup logger early
    global_logger = setup_logger("whalebot", logging.INFO)
    
    # Validate API keys early to prevent unnecessary startup
    if not API_KEY or not API_SECRET:
        global_logger.error(f"{NEON_RED}BYBIT_API_KEY and BYBIT_API_SECRET must be set in .env. Exiting.{RESET}")
        sys.exit(1)

    # Load configuration
    config = load_config(CONFIG_FILE, global_logger)
    alert_system = AlertSystem(global_logger) # Initialize alert system

    # Validate configuration intervals
    valid_bybit_intervals = ["1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"]
    if config["interval"] not in valid_bybit_intervals:
        global_logger.error(f"{NEON_RED}Invalid primary interval '{config['interval']}'. Use Bybit formats. Exiting.{RESET}")
        sys.exit(1)
    for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
        if htf_interval not in valid_bybit_intervals:
            global_logger.error(f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}'. Exiting.{RESET}")
            sys.exit(1)

    global_logger.info(f"{NEON_GREEN}--- Wgwhalex Trading Bot Initialized ---{RESET}")
    global_logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
    global_logger.info(f"Live Trading Enabled: {config['execution']['use_pybit']}")
    global_logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")

    # Initialize API Client (also initializes WS Manager)
    pybit_client = PybitTradingClient(config, global_logger)
    
    # Initialize Position Manager and Performance Tracker
    position_manager = PositionManager(config, global_logger, config["symbol"], pybit_client)
    performance_tracker = PerformanceTracker(global_logger, config)

    # Load state for managers (Pybit client must be initialized before this)
    if pybit_client.enabled and pybit_client.session:
        ws_state_loaded = pybit_client.load_state() # Loads into WS manager and populates pybit_client.state_data
        if not ws_state_loaded: global_logger.warning("Failed to load WS state, continuing without it.")
        
        # Load performance state using pybit_client.state_data
        if not performance_tracker.load_state(pybit_client.state_data):
            global_logger.warning("Failed to load performance tracker state, starting fresh.")
        
        # Set leverage on startup if live trading is enabled
        leverage_set = pybit_client.set_leverage(
            config["symbol"], config["execution"]["buy_leverage"], config["execution"]["sell_leverage"],
        )
        if leverage_set: global_logger.info(f"{NEON_GREEN}Leverage set successfully.{RESET}")
        else:
            global_logger.error(f"{NEON_RED}Failed to set leverage. Check API permissions or account status.{RESET}")
            alert_system.send_alert(f"Failed to set leverage for {config['symbol']}. Check API settings.", "ERROR")

        # Initialize live sync components if enabled
        exec_sync, heartbeat = None, None
        if config["execution"]["live_sync"]["enabled"]:
            exec_sync = ExchangeExecutionSync(config["symbol"], pybit_client, config, position_manager, performance_tracker)
            heartbeat = PositionHeartbeat(config["symbol"], pybit_client, config, position_manager)
        else:
            global_logger.info("Live sync components (Execution Poll, Heartbeat) are disabled.")
    else: # If Pybit client is not enabled or failed to initialize
        global_logger.error(f"{NEON_RED}Pybit client is not enabled or failed to initialize. Cannot proceed with live trading.{RESET}")
        exec_sync, heartbeat = None, None # Ensure sync components are None


    # --- Main Trading Loop ---
    while not pybit_client.stop_event.is_set():
        try:
            global_logger.info(f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}")
            
            # --- Risk Guardrails & Filters ---
            guard = config.get("risk_guardrails", {})
            if guard.get("enabled", False):
                # Calculate equity (balance + total PnL) for guardrail calculations
                current_account_balance = position_manager._get_current_balance()
                equity = current_account_balance + performance_tracker.total_pnl
                
                day_loss = performance_tracker.day_pnl()
                max_day_loss = (Decimal(str(guard.get("max_day_loss_pct", 3.0))) / 100) * equity
                max_dd = (Decimal(str(guard.get("max_drawdown_pct", 8.0))) / 100) * equity
                
                # Check if risk limits (daily loss or max drawdown) are breached
                if (max_day_loss > 0 and day_loss <= -max_day_loss) or (performance_tracker.max_drawdown >= max_dd):
                    global_logger.critical(f"{NEON_RED}KILL SWITCH ACTIVATED: Risk limits hit! Day PnL: {day_loss.normalize():.2f} / Max Allowed: {max_day_loss.normalize():.2f}. Max DD: {performance_tracker.max_drawdown.normalize():.2f} / Allowed: {max_dd.normalize():.2f}. Cooling down.{RESET}")
                    alert_system.send_alert(f"KILL SWITCH: Risk limits hit for {config['symbol']}. Cooling down.", "ERROR")
                    time.sleep(int(guard.get("cooldown_after_kill_min", 120)) * 60) # Long cooldown period
                    continue # Skip the rest of the loop and wait

            # Check if current time is within allowed trading sessions
            if not in_allowed_session(config):
                global_logger.info(f"{NEON_BLUE}Outside allowed trading session. Holding.{RESET}")
                time.sleep(config["loop_delay"])
                continue

            # --- Data Fetching ---
            current_price = pybit_client.fetch_current_price(config["symbol"])
            if current_price is None:
                alert_system.send_alert(f"[{config['symbol']}] Failed to fetch current price. Skipping loop.", "WARNING")
                time.sleep(config["loop_delay"])
                continue
            
            # Fetch historical klines for analysis
            df = pybit_client.fetch_klines(config["symbol"], config["interval"], 1000) # Fetch sufficient history
            if df is None or df.empty:
                alert_system.send_alert(f"[{config['symbol']}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.", "WARNING")
                time.sleep(config["loop_delay"])
                continue

            # Fetch orderbook data if required by indicators
            orderbook_data = None
            if config["indicators"].get("orderbook_imbalance", False):
                orderbook_data = pybit_client.fetch_orderbook(config["symbol"], config["orderbook_limit"])
                if orderbook_data is None: global_logger.warning("Failed to fetch orderbook data.")
            
            # Apply Spread Filter if enabled
            if guard.get("enabled", False) and orderbook_data:
                spread_bps = get_spread_bps(orderbook_data)
                if spread_bps > float(guard.get("spread_filter_bps", 5.0)):
                    global_logger.warning(f"Spread too high ({spread_bps:.1f} bps). Holding.{RESET}")
                    time.sleep(config["loop_delay"])
                    continue
            
            # Apply EV Filter if enabled
            if guard.get("ev_filter_enabled", True):
                current_ev = expected_value(performance_tracker)
                if current_ev <= 0:
                    global_logger.warning(f"Negative Expected Value ({current_ev:.2f}) detected. Holding.{RESET}")
                    time.sleep(config["loop_delay"])
                    continue

            # --- Adaptive Parameters ---
            # Dynamically adjust TP/SL multiples based on recent performance
            tp_mult_adapted, sl_mult_adapted = adapt_exit_params(performance_tracker, config)
            config["trade_management"]["take_profit_atr_multiple"] = float(tp_mult_adapted)
            config["trade_management"]["stop_loss_atr_multiple"] = float(sl_mult_adapted)

            # --- Multi-Timeframe Analysis ---
            mtf_trends: Dict[str, str] = {}
            if config["mtf_analysis"]["enabled"]:
                for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                    htf_df = pybit_client.fetch_klines(config["symbol"], htf_interval, 1000) # Fetch historical data
                    if htf_df is not None and not htf_df.empty:
                        for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                            # Use the indicator module's MTF trend function
                            trend = indicators._get_mtf_trend(htf_df, config, global_logger, config["symbol"], trend_ind)
                            mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                            global_logger.debug(f"MTF Trend ({htf_interval}, {trend_ind}): {trend}")
                    else:
                        global_logger.warning(f"Could not fetch klines for MTF {htf_interval} or it was empty. Skipping.")
                    time.sleep(config["mtf_analysis"]["mtf_request_delay_seconds"]) # Delay between MTF requests

            # --- Analysis and Signal Generation ---
            analyzer = TradingAnalyzer(df, config, global_logger, config["symbol"])
            if analyzer.df.empty: # Check if DataFrame became empty after analysis
                alert_system.send_alert(f"[{config['symbol']}] TradingAnalyzer DataFrame is empty. Cannot generate signal.", "WARNING")
                time.sleep(config["loop_delay"])
                continue
            
            # Retrieve ATR value for potential use in position management (e.g., breakeven)
            atr_value = Decimal(str(analyzer._get_indicator_value("ATR", Decimal("0.1"))))
            config["_last_atr_value"] = str(atr_value) # Store for potential use by other modules

            trading_signal, signal_score, signal_breakdown = analyzer.generate_trading_signal(current_price, orderbook_data, mtf_trends)

            # --- Display Current State ---
            display_indicator_values_and_price(config, global_logger, current_price, analyzer, mtf_trends, signal_breakdown)

            # --- Position Management ---
            # Update trailing stops for simulated open positions
            for pos in position_manager.get_open_positions():
                position_manager.trail_stop(pos, current_price, atr_value)
            # Manage simulated positions (close if SL/TP hit)
            position_manager.manage_positions(current_price, performance_tracker)
            # Attempt pyramiding for simulated positions
            position_manager.try_pyramid(current_price, atr_value)

            # --- Trade Execution ---
            if trading_signal in ("BUY", "SELL"):
                # Calculate conviction based on signal score relative to threshold
                conviction = float(min(1.0, max(0.0, (abs(signal_score) - config["signal_score_threshold"]) / config["signal_score_threshold"])))
                if conviction < 0.1 and abs(signal_score) >= config["signal_score_threshold"]: conviction = 0.1 # Minimum conviction for valid signal
                
                # Open position only if score significantly exceeds threshold
                if abs(signal_score) >= config["signal_score_threshold"]:
                    position_manager.open_position(trading_signal, current_price, atr_value, conviction)
                else:
                    global_logger.info(f"Signal ({trading_signal}) below threshold ({config['signal_score_threshold']:.2f}). Holding. Score: {signal_score:.2f}")
            else:
                global_logger.info(f"No strong trading signal. Holding. Score: {signal_score:.2f}")

            # --- Live Synchronization & Heartbeat ---
            if exec_sync: exec_sync.poll() # Process recent executions from REST API polling
            if heartbeat: heartbeat.tick() # Perform heartbeat check to reconcile state with exchange

            # --- Log Status Summary ---
            open_positions_summary = position_manager.get_open_positions()
            if open_positions_summary:
                global_logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions_summary)}{RESET}")
                for pos in open_positions_summary: # Log details of open positions
                    global_logger.info(f"  - {pos['side']} {pos['qty'].normalize()} {pos['symbol']} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}, Adds: {pos['adds']}){RESET}")
            else:
                global_logger.info(f"{NEON_CYAN}No open positions.{RESET}")

            perf_summary = performance_tracker.get_summary() # Get performance summary
            global_logger.info(f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl']}, Daily PnL: {perf_summary['daily_pnl']}, Win Rate: {perf_summary['win_rate']}, Max Drawdown: {perf_summary['max_drawdown']}{RESET}")

            global_logger.info(f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}")
            time.sleep(config["loop_delay"]) # Wait before next loop iteration

        except Exception as e:
            # Catch any unhandled exceptions in the main loop for graceful recovery
            alert_system.send_alert(f"[{config['symbol']}] Unhandled error in main loop: {e}", "ERROR")
            global_logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
            time.sleep(config["loop_delay"] * 2) # Wait longer after an error before retrying

        finally:
            # Save state on shutdown or periodically
            # The `pybit_client.shutdown()` in `if __name__ == "__main__":` handles saving.
            # If you want periodic saving during runtime, add it here.
            pass

if __name__ == "__main__":
    # Setup the global logger instance early
    global_logger = setup_logger("whalebot", logging.INFO)
    
    # Check for essential configuration early
    if not API_KEY or not API_SECRET:
        global_logger.error(f"{NEON_RED}BYBIT_API_KEY and BYBIT_API_SECRET must be set in .env. Exiting.{RESET}")
        sys.exit(1)

    # Optional: Trigger weight tuning script (uncomment to enable)
    # try:
    #     from tuning_module import random_tune_weights # Assumes tuning logic is in tuning_module.py
    #     random_tune_weights(CONFIG_FILE) # Example call
    # except ImportError:
    #     global_logger.warning("Tuning module not found. Skipping weight tuning.")
    # except Exception as e:
    #     global_logger.error(f"Error during weight tuning: {e}")

    # Start the main bot execution loop
    try:
        main()
    except KeyboardInterrupt:
        global_logger.info(f"{NEON_YELLOW}Bot stopped by user (KeyboardInterrupt). Shutting down...{RESET}")
    except Exception as e:
        global_logger.exception(f"{NEON_RED}An unhandled error occurred outside the main loop: {e}{RESET}")
    finally:
        if 'pybit_client' in globals() and pybit_client.enabled:
            pybit_client.shutdown() # Ensure proper shutdown and state saving
        else:
            global_logger.info("Pybit client not initialized or enabled, skipping client shutdown.")
