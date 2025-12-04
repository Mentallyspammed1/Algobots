import hashlib
import hmac
import json
import logging
import os
import queue
import ssl
import sys
import threading
import time
import urllib.parse
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, getcontext
from pathlib import Path
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd
import requests
import websocket
from colorama import Fore, Style, init
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Scikit-learn is explicitly excluded as per user request.
SKLEARN_AVAILABLE = False

# Initialize colorama and set decimal precision
getcontext().prec = 28
init(autoreset=True)
load_dotenv()

# Neon Color Scheme
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
NEON_CYAN = Fore.CYAN
RESET = Style.RESET_ALL

# Indicator specific colors (enhanced for new indicators)
INDICATOR_COLORS = {
    "SMA_10": Fore.LIGHTBLUE_EX,
    "SMA_Long": Fore.BLUE,
    "EMA_Short": Fore.LIGHTMAGENTA_EX,
    "EMA_Long": Fore.MAGENTA,
    "ATR": Fore.YELLOW,
    "RSI": Fore.GREEN,
    "StochRSI_K": Fore.CYAN,
    "StochRSI_D": Fore.LIGHTCYAN_EX,
    "BB_Upper": Fore.RED,
    "BB_Middle": Fore.WHITE,
    "BB_Lower": Fore.RED,
    "CCI": Fore.LIGHTGREEN_EX,
    "WR": Fore.LIGHTRED_EX,
    "MFI": Fore.GREEN,
    "OBV": Fore.BLUE,
    "OBV_EMA": Fore.LIGHTBLUE_EX,
    "CMF": Fore.MAGENTA,
    "Tenkan_Sen": Fore.CYAN,
    "Kijun_Sen": Fore.LIGHTCYAN_EX,
    "Senkou_Span_A": Fore.GREEN,
    "Senkou_Span_B": Fore.RED,
    "Chikou_Span": Fore.YELLOW,
    "PSAR_Val": Fore.MAGENTA,
    "PSAR_Dir": Fore.LIGHTMAGENTA_EX,
    "VWAP": Fore.WHITE,
    "ST_Fast_Dir": Fore.BLUE,
    "ST_Fast_Val": Fore.LIGHTBLUE_EX,
    "ST_Slow_Dir": Fore.MAGENTA,
    "ST_Slow_Val": Fore.LIGHTMAGENTA_EX,
    "MACD_Line": Fore.GREEN,
    "MACD_Signal": Fore.LIGHTGREEN_EX,
    "MACD_Hist": Fore.YELLOW,
    "ADX": Fore.CYAN,
    "PlusDI": Fore.LIGHTCYAN_EX,
    "MinusDI": Fore.RED,
    "Volatility_Index": Fore.YELLOW,
    "Volume_Delta": Fore.LIGHTCYAN_EX,
    "VWMA": Fore.WHITE,
    "Avg_Volume": Fore.LIGHTCYAN_EX,  # New indicator for confirmation
}

# --- Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs/trading-bot/logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

# WebSocket URLs
WS_PUBLIC_BASE_URL = os.getenv(
    "BYBIT_WS_PUBLIC_BASE_URL",
    "wss://stream.bybit.com/v5/public/linear",
)
WS_PRIVATE_BASE_URL = os.getenv(
    "BYBIT_WS_PRIVATE_BASE_URL",
    "wss://stream.bybit.com/v5/private",
)

# WebSocket specific settings
WS_RECONNECT_ATTEMPTS = 5
WS_RECONNECT_DELAY_SECONDS = 10
DEFAULT_PUBLIC_TOPICS = []  # Will be dynamically populated
DEFAULT_PRIVATE_TOPICS = ["order", "position", "wallet"]

# Using UTC for consistency and to avoid timezone issues with API timestamps
TIMEZONE = UTC
MAX_API_RETRIES = 5
RETRY_DELAY_SECONDS = 7
REQUEST_TIMEOUT = 20
LOOP_DELAY_SECONDS = 15

# Magic Numbers as Constants (expanded)
MIN_DATA_POINTS_TR = 2
MIN_DATA_POINTS_SMOOTHER = 2
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR = 2
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20
MIN_DATA_POINTS_VWMA = 2
MIN_DATA_POINTS_VOLATILITY = 2


# --- Configuration Management ---
def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    """Load configuration from JSON file, creating a default if not found."""
    default_config = {
        # Core Settings
        "symbol": "BTCUSDT",
        "interval": "15",  # Changed "15m" to "15" to match Bybit API requirement
        "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50,
        "signal_score_threshold": 2.0,
        "cooldown_sec": 60,
        "hysteresis_ratio": 0.85,
        "volume_confirmation_multiplier": 1.5,
        # Position & Risk Management
        "trade_management": {
            "enabled": True,
            "account_balance": 1000.0,
            "risk_per_trade_percent": 1.0,
            "stop_loss_atr_multiple": 1.5,
            "take_profit_atr_multiple": 2.0,
            "max_open_positions": 1,
            "order_precision": 5,  # New: Decimal places for order quantity
            "price_precision": 3,  # New: Decimal places for price
            "enable_trailing_stop": True,  # Enable trailing stop
            "trailing_stop_atr_multiple": 0.8,  # ATR multiple for trailing stop distance
            "break_even_atr_trigger": 0.5,  # Price must move this much in profit (in ATR multiples) to activate trailing stop
            # UPGRADE 1: Dynamic Stop Loss Adjustment
            "move_to_breakeven_atr_trigger": 1.0,  # Move SL to entry if price moves this much in profit
            "profit_lock_in_atr_multiple": 0.5,  # After breakeven, move SL to (current_price - ATR*multiple)
            # UPGRADE 4: Opposite Signal Position Closure/Reversal
            "close_on_opposite_signal": True,
            "reverse_position_on_opposite_signal": False,  # If true, closes and then opens new in opposite direction
        },
        # Multi-Timeframe Analysis
        "mtf_analysis": {
            "enabled": True,
            "higher_timeframes": ["60", "240"],  # Changed "1h", "4h" to "60", "240"
            "trend_indicators": ["ema", "ehlers_supertrend"],
            "trend_period": 50,
            "mtf_request_delay_seconds": 0.5,
        },
        # Machine Learning Enhancement (Explicitly disabled)
        "ml_enhancement": {
            "enabled": False,  # ML explicitly disabled
            "model_path": "ml_model.pkl",
            "retrain_on_startup": False,
            "training_data_limit": 5000,
            "prediction_lookahead": 12,
            "profit_target_percent": 0.5,
            "feature_lags": [1, 2, 3, 5],
            "cross_validation_folds": 5,
            # UPGRADE 3: News/Sentiment Integration Placeholder
            "sentiment_analysis_enabled": False,
            "bullish_sentiment_threshold": 0.6,  # 0 to 1 scale for sentiment
            "bearish_sentiment_threshold": 0.4,
        },
        # Strategy Profiles
        "current_strategy_profile": "default_scalping",  # New: Specifies the currently active strategy profile
        "adaptive_strategy_enabled": True,  # UPGRADE 5: Enable adaptive strategy selection
        "strategy_profiles": {  # New section to define various strategy profiles
            "default_scalping": {
                "description": "Standard scalping strategy for fast markets.",
                # UPGRADE 5: Market condition criteria for this strategy
                "market_condition_criteria": {
                    "adx_range": [0, 25],  # Suitable for ranging/weak trend
                    "volatility_range": [0.005, 0.02],  # Optimal volatility
                },
                "indicators_enabled": {
                    "ema_alignment": True,
                    "sma_trend_filter": True,
                    "momentum": True,  # Now a general category, individual momentum indicators are sub-checked
                    "volume_confirmation": True,  # UPGRADE 2
                    "volatility_filter": True,  # UPGRADE 2
                    "stoch_rsi": True,
                    "rsi": True,
                    "bollinger_bands": True,
                    "vwap": True,
                    "cci": True,
                    "wr": True,
                    "psar": True,
                    "sma_10": True,
                    "mfi": True,
                    "orderbook_imbalance": True,
                    "fibonacci_levels": True,
                    "ehlers_supertrend": True,
                    "macd": True,
                    "adx": True,
                    "ichimoku_cloud": True,
                    "obv": True,
                    "cmf": True,
                    "volatility_index": True,
                    "vwma": True,
                    "volume_delta": True,
                },
                "weights": {
                    "ema_alignment": 0.22,
                    "sma_trend_filter": 0.28,
                    "momentum_rsi_stoch_cci_wr_mfi": 0.18,
                    "volume_confirmation": 0.12,  # UPGRADE 2
                    "volatility_filter": 0.10,  # UPGRADE 2
                    "bollinger_bands": 0.22,
                    "vwap": 0.22,
                    "psar": 0.22,
                    "sma_10": 0.07,
                    "orderbook_imbalance": 0.07,
                    "ehlers_supertrend_alignment": 0.55,
                    "macd_alignment": 0.28,
                    "adx_strength": 0.18,
                    "ichimoku_confluence": 0.38,
                    "obv_momentum": 0.18,
                    "cmf_flow": 0.12,
                    "mtf_trend_confluence": 0.32,
                    "volatility_index_signal": 0.15,
                    "vwma_cross": 0.15,
                    "volume_delta_signal": 0.10,
                    "sentiment_signal": 0.15,  # UPGRADE 3
                },
            },
            "trend_following": {
                "description": "Strategy focused on capturing longer trends.",
                # UPGRADE 5: Market condition criteria for this strategy
                "market_condition_criteria": {
                    "adx_range": [25, 100],  # Suitable for strong trend
                    "volatility_range": [0.01, 0.05],  # Optimal volatility
                },
                "indicators_enabled": {
                    "ema_alignment": True,
                    "sma_trend_filter": True,
                    "macd": True,
                    "adx": True,
                    "ehlers_supertrend": True,
                    "ichimoku_cloud": True,
                    "mtf_analysis": True,
                    "volume_confirmation": True,  # UPGRADE 2
                    "volatility_filter": True,  # UPGRADE 2
                    "rsi": False,  # Example: Disable some indicators for this strategy
                    "stoch_rsi": False,
                },
                "weights": {
                    "ema_alignment": 0.30,
                    "sma_trend_filter": 0.20,
                    "macd_alignment": 0.40,
                    "adx_strength": 0.35,
                    "ehlers_supertrend_alignment": 0.60,
                    "ichimoku_confluence": 0.50,
                    "mtf_trend_confluence": 0.40,
                    "volume_confirmation": 0.15,  # UPGRADE 2
                    "volatility_filter": 0.15,  # UPGRADE 2
                    "sentiment_signal": 0.20,  # UPGRADE 3
                },
            },
        },
        # Indicator Periods & Thresholds
        "indicator_settings": {
            "atr_period": 14,
            "ema_short_period": 9,
            "ema_long_period": 21,
            "rsi_period": 14,
            "stoch_rsi_period": 14,
            "stoch_k_period": 3,
            "stoch_d_period": 3,
            "bollinger_bands_period": 20,
            "bollinger_bands_std_dev": 2.0,
            "cci_period": 20,
            "williams_r_period": 14,
            "mfi_period": 14,
            "psar_acceleration": 0.02,
            "psar_max_acceleration": 0.2,
            "sma_short_period": 10,
            "sma_long_period": 50,
            "fibonacci_window": 60,
            "ehlers_fast_period": 10,
            "ehlers_fast_multiplier": 2.0,
            "ehlers_slow_period": 20,
            "ehlers_slow_multiplier": 3.0,
            "macd_fast_period": 12,
            "macd_slow_period": 26,
            "macd_signal_period": 9,
            "adx_period": 14,
            "ichimoku_tenkan_period": 9,
            "ichimoku_kijun_period": 26,
            "ichimoku_senkou_span_b_period": 52,
            "ichimoku_chikou_span_offset": 26,
            "obv_ema_period": 20,
            "cmf_period": 20,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "stoch_rsi_oversold": 20,
            "stoch_rsi_overbought": 80,
            "cci_oversold": -100,
            "cci_overbought": 100,
            "williams_r_oversold": -80,
            "williams_r_overbought": -20,
            "mfi_oversold": 20,
            "mfi_overbought": 80,
            "volatility_index_period": 20,  # New: Volatility Index Period
            "vwma_period": 20,  # New: VWMA Period
            "volume_delta_period": 5,  # New: Volume Delta Period
            "volume_delta_threshold": 0.2,  # New: Volume Delta Threshold for signals
            # ADX thresholds moved to indicator_settings for better config management
            "ADX_STRONG_TREND_THRESHOLD": 25,
            "ADX_WEAK_TREND_THRESHOLD": 20,
            # UPGRADE 2: Trade Confirmation with Volume & Volatility Filters
            "enable_volume_confirmation": True,
            "volume_confirmation_period": 20,  # Period for average volume calculation
            "min_volume_multiplier": 1.2,  # Current volume must be >= Avg Volume * this multiplier for confirmation
            "enable_volatility_filter": True,
            "optimal_volatility_min": 0.005,  # Min value for Volatility_Index to consider trade
            "optimal_volatility_max": 0.03,  # Max value for Volatility_Index to consider trade
        },
        # Active Indicators & Weights (expanded)
        "indicators": {},  # These will be overwritten by active profile
        "active_weights": {},  # These will be overwritten by active profile
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(
                f"{NEON_YELLOW}Configuration file not found. Created default config at {filepath} for symbol {default_config['symbol']}{RESET}",
            )
            return default_config
        except OSError as e:
            logger.error(f"{NEON_RED}Error creating default config file: {e}{RESET}")
            # Fallback to default config even if file creation fails
            return default_config

    try:
        with Path(filepath).open(encoding="utf-8") as f:
            config = json.load(f)
        _ensure_config_keys(config, default_config)

        # NEW: Logic to load the active strategy profile
        active_profile_name = config.get("current_strategy_profile", "default_scalping")
        if active_profile_name in config.get("strategy_profiles", {}):
            active_profile = config["strategy_profiles"][active_profile_name]
            # Overwrite global 'indicators' and 'active_weights' with active profile's settings
            if "indicators_enabled" in active_profile:
                config["indicators"] = active_profile["indicators_enabled"]
            if "weights" in active_profile:
                config["active_weights"] = active_profile[
                    "weights"
                ]  # Store active weights here
            logger.info(
                f"{NEON_BLUE}Active strategy profile '{active_profile_name}' loaded successfully.{RESET}",
            )
        else:
            logger.warning(
                f"{NEON_YELLOW}Configured strategy profile '{active_profile_name}' not found. Falling back to default indicators and weight_sets from config directly.{RESET}",
            )
            # Fallback to previously existing `indicators` and `active_weights` if profile not found
            if "indicators" not in config:  # Ensure a default if not found at all
                config["indicators"] = default_config["strategy_profiles"][
                    "default_scalping"
                ]["indicators_enabled"]
            if "active_weights" not in config:  # Ensure a default if not found at all
                config["active_weights"] = default_config["strategy_profiles"][
                    "default_scalping"
                ]["weights"]

        # Save the merged config to ensure consistency and add any new default keys
        with Path(filepath).open("w", encoding="utf-8") as f_write:
            json.dump(config, f_write, indent=4)
        return config
    except (OSError, FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(
            f"{NEON_RED}Error loading config: {e}. Using default and attempting to save.{RESET}",
        )
        try:
            with Path(filepath).open("w", encoding="utf-8") as f_default:
                json.dump(default_config, f_default, indent=4)
        except OSError as e_save:
            logger.error(f"{NEON_RED}Could not save default config: {e_save}{RESET}")
        return default_config


def _ensure_config_keys(config: dict[str, Any], default_config: dict[str, Any]) -> None:
    """Recursively ensure all keys from default_config are in config."""
    for key, default_value in default_config.items():
        if key not in config:
            config[key] = default_value
        elif isinstance(default_value, dict) and isinstance(config.get(key), dict):
            _ensure_config_keys(config[key], default_value)
        # If config[key] exists but is not a dict, and default_value is a dict,
        # it means the config file has a non-dict value where a dict is expected.
        # This case is handled by overwriting with the default dict structure.
        elif isinstance(default_value, dict) and not isinstance(config.get(key), dict):
            config[key] = default_value


# A simple class to adapt the config dict to what setup_logger expects
class UnanimousLoggerConfig:
    def __init__(self, config_dict):
        # Extract log level from config, default to INFO
        self.LOG_LEVEL = config_dict.get("log_level", "INFO").upper()

        # Construct log file path from constants defined in the script
        log_filename = config_dict.get("log_filename", "wb.log")
        self.LOG_FILE_PATH = os.path.join(LOG_DIRECTORY, log_filename)

        # Pass color codes
        self.NEON_BLUE = NEON_BLUE
        self.RESET = RESET


# Create a temporary basic logger for the initial config loading
temp_logger = logging.getLogger("config_loader")
temp_logger.setLevel(logging.INFO)
if not temp_logger.handlers:
    temp_logger.addHandler(logging.StreamHandler(sys.stdout))

# Load the main configuration using the temporary logger
config = load_config(CONFIG_FILE, temp_logger)

# Determine if unanimous_logger is available and set up the logger
try:
    from unanimous_logger import setup_logger

    logger_config = UnanimousLoggerConfig(config)
    logger = setup_logger(logger_config, log_name="wb", json_log_file="wb.json.log")
except ImportError:
    print("unanimous_logger not found, using basic logging setup.")

    class BasicLoggerConfig:
        def __init__(self, config_dict):
            self.LOG_LEVEL = config_dict.get("log_level", "INFO").upper()
            log_filename = config_dict.get("log_filename", "wb.log")
            self.LOG_FILE_PATH = os.path.join(LOG_DIRECTORY, log_filename)

    def setup_basic_logger(config_obj, log_name="default", json_log_file=None):
        logger = logging.getLogger(log_name)
        logger.setLevel(getattr(logging, config_obj.LOG_LEVEL))

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        # Stream handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(getattr(logging, config_obj.LOG_LEVEL))
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        # File handler
        fh = logging.FileHandler(config_obj.LOG_FILE_PATH)
        fh.setLevel(getattr(logging, config_obj.LOG_LEVEL))
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        # Optional JSON file handler
        if json_log_file:
            json_formatter = logging.Formatter(
                '{"time": "%(asctime)s", "name": "%(name)s", "level": "%(levelname)s", "message": "%(message)s", "extra": %(extra)s}',
            )
            json_fh = logging.FileHandler(os.path.join(LOG_DIRECTORY, json_log_file))
            json_fh.setLevel(getattr(logging, config_obj.LOG_LEVEL))
            json_fh.setFormatter(json_formatter)
            logger.addHandler(json_fh)
        return logger

    logger_config = BasicLoggerConfig(config)
    logger = setup_basic_logger(
        logger_config,
        log_name="wb",
        json_log_file="wb.json.log",
    )
# --- End Logger Setup ---


# --- API Interaction ---
def create_session() -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    retries = Retry(
        total=MAX_API_RETRIES,
        backoff_factor=RETRY_DELAY_SECONDS,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def generate_signature(payload: str, api_secret: str) -> str:
    """Generate a Bybit API signature."""
    return hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def generate_ws_signature(api_key: str, api_secret: str, expires: int) -> str:
    """Generate a Bybit WebSocket authentication signature."""
    param_str = f"GET/realtime{expires}"
    signature = hmac.new(
        api_secret.encode(),
        param_str.encode(),
        hashlib.sha256,
    ).hexdigest()
    return signature


def bybit_request(
    method: Literal["GET", "POST"],
    endpoint: str,
    params: dict | None = None,
    signed: bool = False,
    logger: logging.Logger | None = None,
) -> dict | None:
    """Send a request to the Bybit API."""
    if logger is None:
        raise ValueError("Logger must be provided to bybit_request")
    session = create_session()
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}

    if signed:
        if not API_KEY or not API_SECRET:
            logger.error(
                f"{NEON_RED}API_KEY or API_SECRET not set for signed request.{RESET}",
            )
            return None

        timestamp = str(int(time.time() * 1000))
        recv_window = "20000"  # Standard recommended receive window

        if method == "GET":
            # For GET, params should be part of the query string and param_str is timestamp + API_KEY + recv_window + query_string
            query_string = urllib.parse.urlencode(params) if params else ""
            param_str = timestamp + API_KEY + recv_window + query_string
            signature = generate_signature(param_str, API_SECRET)
            headers.update(
                {
                    "X-BAPI-API-KEY": API_KEY,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": recv_window,
                },
            )
            logger.debug(f"GET Request: {url}?{query_string}")
            response = session.get(
                url,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
        else:  # POST
            # For POST, params should be JSON stringified and param_str is timestamp + API_KEY + recv_window + json_params
            json_params = json.dumps(params) if params else ""
            param_str = timestamp + API_KEY + recv_window + json_params
            signature = generate_signature(param_str, API_SECRET)
            headers.update(
                {
                    "X-BAPI-API-KEY": API_KEY,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": recv_window,
                },
            )
            logger.debug(f"POST Request: {url} with payload {json_params}")
            response = session.post(
                url,
                json=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
    else:
        logger.debug(f"Public Request: {url} with params {params}")
        response = session.get(
            url,
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

    try:
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") != 0:
            logger.error(
                f"{NEON_RED}Bybit API Error: {data.get('retMsg')} (Code: {data.get('retCode')}){RESET}",
            )
            return None
        return data
    except requests.exceptions.HTTPError as e:
        logger.error(
            f"{NEON_RED}HTTP Error: {e.response.status_code} - {e.response.text}{RESET}",
        )
    except requests.exceptions.ConnectionError as e:
        logger.error(f"{NEON_RED}Connection Error: {e}{RESET}")
    except requests.exceptions.Timeout:
        logger.error(
            f"{NEON_RED}Request timed out after {REQUEST_TIMEOUT} seconds.{RESET}",
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"{NEON_RED}Request Exception: {e}{RESET}")
    except json.JSONDecodeError:
        logger.error(
            f"{NEON_RED}Failed to decode JSON response: {response.text}{RESET}",
        )
    return None


def fetch_current_price(
    symbol: str,
    logger: logging.Logger,
    ws_manager: Optional["BybitWebSocketManager"] = None,
) -> Decimal | None:
    """Fetch the current market price for a symbol, preferring WebSocket data."""
    if ws_manager and ws_manager.is_connected_public:
        latest_ticker = ws_manager.get_latest_ticker()
        if (
            latest_ticker
            and latest_ticker.get("symbol") == symbol
            and latest_ticker.get("lastPrice") is not None
        ):
            price = latest_ticker["lastPrice"]  # Already Decimal from WS
            logger.debug(f"Fetched current price for {symbol} from WS: {price}")
            return price
        logger.debug(
            f"{NEON_YELLOW}WS ticker data not available for {symbol}. Falling back to REST.{RESET}",
        )

    endpoint = "/v5/market/tickers"
    params = {"category": "linear", "symbol": symbol}
    response = bybit_request("GET", endpoint, params, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        price = Decimal(response["result"]["list"][0]["lastPrice"])
        logger.debug(f"Fetched current price for {symbol} from REST: {price}")
        return price
    logger.warning(f"{NEON_YELLOW}[{symbol}] Could not fetch current price.{RESET}")
    return None


def fetch_klines(
    symbol: str,
    interval: str,
    limit: int,
    logger: logging.Logger,
    ws_manager: Optional["BybitWebSocketManager"] = None,
) -> pd.DataFrame | None:
    """Fetch kline data for a symbol and interval, preferring WebSocket data."""
    if (
        ws_manager
        and ws_manager.is_connected_public
        and ws_manager.config["interval"] == interval
        and ws_manager.symbol == symbol
    ):
        ws_df = ws_manager.get_latest_kline_df()
        if not ws_df.empty:
            if len(ws_df) >= limit:
                logger.debug(
                    f"Fetched {len(ws_df)} {interval} klines for {symbol} from WS.",
                )
                return ws_df.tail(limit).copy()
            logger.debug(
                f"{NEON_YELLOW}WS kline data has {len(ws_df)} bars, less than requested {limit}. Falling back to REST for full history.{RESET}",
            )

    endpoint = "/v5/market/kline"
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    response = bybit_request("GET", endpoint, params, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        df = pd.DataFrame(
            response["result"]["list"],
            columns=[
                "start_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
            ],
        )
        df["start_time"] = pd.to_datetime(
            df["start_time"].astype(int),
            unit="ms",
            utc=True,
        ).dt.tz_convert(TIMEZONE)
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.set_index("start_time", inplace=True)
        df.sort_index(inplace=True)

        if df.empty:
            logger.warning(
                f"{NEON_YELLOW}[{symbol}] Fetched klines for {interval} but DataFrame is empty after processing. Raw response: {response}{RESET}",
            )
            return None

        logger.debug(f"Fetched {len(df)} {interval} klines for {symbol} from REST.")
        return df
    logger.warning(
        f"{NEON_YELLOW}[{symbol}] Could not fetch klines for {interval}. API response might be empty or invalid. Raw response: {response}{RESET}",
    )
    return None


def fetch_orderbook(
    symbol: str,
    limit: int,
    logger: logging.Logger,
    ws_manager: Optional["BybitWebSocketManager"] = None,
) -> dict | None:
    """Fetch orderbook data for a symbol, preferring WebSocket data."""
    if ws_manager and ws_manager.is_connected_public and ws_manager.symbol == symbol:
        ws_orderbook = ws_manager.get_latest_orderbook_dict()
        if ws_orderbook and ws_orderbook["bids"] and ws_orderbook["asks"]:
            logger.debug(f"Fetched orderbook for {symbol} from WS.")
            return {
                "s": symbol,
                "b": ws_orderbook["bids"][
                    :limit
                ],  # WS provides already processed Bids/Asks as [[price, qty]]
                "a": ws_orderbook["asks"][:limit],
                "u": None,  # Not directly available or needed for basic usage
                "seq": None,  # Not directly available or needed for basic usage
            }
        logger.debug(
            f"{NEON_YELLOW}WS orderbook data not available for {symbol}. Falling back to REST.{RESET}",
        )

    endpoint = "/v5/market/orderbook"
    params = {"category": "linear", "symbol": symbol, "limit": limit}
    response = bybit_request("GET", endpoint, params, logger=logger)
    if response and response["result"]:
        logger.debug(f"Fetched orderbook for {symbol} with limit {limit} from REST.")
        result = response["result"]
        # Convert prices and quantities to Decimal for consistency
        result["b"] = [
            [Decimal(price), Decimal(qty)] for price, qty in result.get("b", [])
        ]
        result["a"] = [
            [Decimal(price), Decimal(qty)] for price, qty in result.get("a", [])
        ]
        return result
    logger.warning(f"{NEON_YELLOW}[{symbol}] Could not fetch orderbook.{RESET}")
    return None


# --- Trading Specific API Interactions ---


def place_market_order(
    symbol: str,
    side: Literal["Buy", "Sell"],
    qty: Decimal,
    logger: logging.Logger,
    order_type: Literal["Market", "Limit"] = "Market",
    price: Decimal | None = None,  # Required for Limit orders
    category: Literal["linear", "inverse"] = "linear",
) -> dict | None:
    """Places a market order on Bybit.
    https://bybit-exchange.github.io/docs/v5/order/create
    """
    endpoint = "/v5/order/create"

    # Ensure qty is a string with correct precision
    order_params = {
        "category": category,
        "symbol": symbol,
        "side": side,
        "orderType": order_type,
        "qty": str(qty.normalize()),  # Ensure Decimal is converted to string for API
    }

    if order_type == "Limit":
        if price is None:
            logger.error(
                f"{NEON_RED}[{symbol}] Price is required for a Limit order.{RESET}",
            )
            return None
        order_params["price"] = str(
            price.normalize(),
        )  # Ensure Decimal is converted to string

    logger.info(
        f"{NEON_BLUE}[{symbol}] Attempting to place {side} {order_type} order for {qty.normalize()} at {price.normalize() if price else 'Market'}...{RESET}",
    )
    response = bybit_request("POST", endpoint, order_params, signed=True, logger=logger)

    if response and response["result"]:
        logger.info(
            f"{NEON_GREEN}[{symbol}] Order placed successfully: {response['result']}{RESET}",
        )
        return response["result"]
    logger.error(
        f"{NEON_RED}[{symbol}] Failed to place order. Response: {response}{RESET}",
    )
    return None


def set_position_tpsl(
    symbol: str,
    take_profit: Decimal | None,
    stop_loss: Decimal | None,
    logger: logging.Logger,
    position_idx: int = 0,  # Assuming One-Way Mode (0 for both long/short)
    category: Literal["linear", "inverse"] = "linear",
) -> dict | None:
    """Sets or updates Take Profit and Stop Loss for an existing position.
    https://bybit-exchange.github.io/docs/v5/position/trading-stop
    """
    endpoint = "/v5/position/set-trading-stop"
    params = {
        "category": category,
        "symbol": symbol,
        "positionIdx": position_idx,
    }
    if take_profit is not None:
        params["takeProfit"] = str(take_profit.normalize())
    if stop_loss is not None:
        params["stopLoss"] = str(stop_loss.normalize())

    if take_profit is None and stop_loss is None:
        logger.warning(
            f"{NEON_YELLOW}[{symbol}] No TP or SL provided for set_position_tpsl. Skipping.{RESET}",
        )
        return None

    logger.debug(f"[{symbol}] Attempting to set TP/SL: {params}")
    response = bybit_request("POST", endpoint, params, signed=True, logger=logger)

    if response and response["retCode"] == 0:
        logger.info(
            f"{NEON_GREEN}[{symbol}] TP/SL for position updated successfully. SL: {stop_loss.normalize() if stop_loss else 'N/A'}, TP: {take_profit.normalize() if take_profit else 'N/A'}{RESET}",
        )
        return response["result"]
    logger.error(
        f"{NEON_RED}[{symbol}] Failed to set TP/SL. Response: {response}{RESET}",
    )
    return None


def get_open_positions_from_exchange(
    symbol: str,
    logger: logging.Logger,
    category: Literal["linear", "inverse"] = "linear",
    ws_manager: Optional["BybitWebSocketManager"] = None,
) -> list[dict]:
    """Fetches all open positions for a given symbol from the Bybit exchange, preferring WebSocket data."""
    if ws_manager and ws_manager.is_connected_private:
        # Check private updates queue for position updates first
        private_updates = ws_manager.get_private_updates()
        position_updates = [d for d in private_updates if d.get("topic") == "position"]
        if position_updates:
            # For simplicity, we'll take the latest position update.
            # A more robust system would merge deltas into a complete position state.
            # This is complex and usually requires maintaining a local copy of full position state.
            latest_position_data = position_updates[-1].get("data", [])
            open_positions = [
                p for p in latest_position_data if Decimal(p.get("size", "0")) > 0
            ]
            logger.debug(
                f"[{symbol}] Fetched {len(open_positions)} open positions from WS private stream.",
            )
            return open_positions
        logger.debug(
            f"{NEON_YELLOW}No new position updates from WS. Falling back to REST.{RESET}",
        )

    endpoint = "/v5/position/list"
    params = {
        "category": category,
        "symbol": symbol,
    }
    response = bybit_request("GET", endpoint, params, signed=True, logger=logger)

    if response and response["result"] and response["result"]["list"]:
        # Filter for truly open positions (size > 0)
        open_positions = [
            p for p in response["result"]["list"] if Decimal(p.get("size", "0")) > 0
        ]
        logger.debug(
            f"[{symbol}] Fetched {len(open_positions)} open positions from REST exchange.",
        )
        return open_positions
    logger.debug(
        f"[{symbol}] No open positions found on REST exchange or failed to fetch. Raw response: {response}",
    )
    return []


# --- Position Management ---
class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""

    def __init__(
        self,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
        ws_manager: Optional["BybitWebSocketManager"] = None,
    ):
        """Initializes the PositionManager."""
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.ws_manager = ws_manager
        # open_positions will now store detailed exchange-confirmed position data
        # {
        #   "positionIdx": int, # 0 for one-way, 1 for long, 2 for short (hedge)
        #   "side": str,        # "Buy" or "Sell"
        #   "entry_price": Decimal,
        #   "qty": Decimal,
        #   "stop_loss": Decimal,
        #   "take_profit": Decimal,
        #   "position_id": str, # Bybit's positionId (often positionIdx in one-way)
        #   "order_id": str,    # Bybit's orderId for the entry trade
        #   "entry_time": datetime,
        #   "initial_stop_loss": Decimal, # The SL set at entry, before TSL modifications
        #   "trailing_stop_activated": bool,
        #   "trailing_stop_price": Decimal | None # The actual trailing stop price set on exchange
        #   "breakeven_activated": bool # NEW: to track if breakeven has been applied
        # }
        self.open_positions: list[dict] = []
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]
        self.enable_trailing_stop = config["trade_management"].get(
            "enable_trailing_stop",
            False,
        )
        self.trailing_stop_atr_multiple = Decimal(
            str(config["trade_management"].get("trailing_stop_atr_multiple", 0.0)),
        )
        self.break_even_atr_trigger = Decimal(
            str(config["trade_management"].get("break_even_atr_trigger", 0.0)),
        )

        # UPGRADE 1: Dynamic Stop Loss Adjustment
        self.move_to_breakeven_atr_trigger = Decimal(
            str(config["trade_management"].get("move_to_breakeven_atr_trigger", 0.0)),
        )
        self.profit_lock_in_atr_multiple = Decimal(
            str(config["trade_management"].get("profit_lock_in_atr_multiple", 0.0)),
        )
        # UPGRADE 4: Opposite Signal Position Closure/Reversal
        self.close_on_opposite_signal = config["trade_management"].get(
            "close_on_opposite_signal",
            True,
        )
        self.reverse_position_on_opposite_signal = config["trade_management"].get(
            "reverse_position_on_opposite_signal",
            False,
        )

        # Define precision for quantization, e.g., 5 decimal places for crypto
        self.price_quantize_dec = Decimal("1e-" + str(self.price_precision))
        self.qty_quantize_dec = Decimal("1e-" + str(self.order_precision))

        # Initial sync of open positions from exchange
        self.sync_positions_from_exchange()

    def _get_current_balance(self) -> Decimal:
        """Fetch current account balance (simplified for simulation).
        In a real bot, this would query the exchange's wallet balance.
        """
        # Example API call for real balance (needs authentication):
        # endpoint = "/v5/account/wallet-balance"
        # params = {"accountType": "UNIFIED"} # Or "CONTRACT" depending on account type
        # response = bybit_request("GET", endpoint, params, signed=True, logger=self.logger)
        # if response and response["result"] and response["result"]["list"]:
        #     for coin_balance in response["result"]["list"][0]["coin"]:
        #         if coin_balance["coin"] == "USDT": # Assuming USDT as base currency
        #             return Decimal(coin_balance["walletBalance"])
        # Fallback to configured balance for simulation
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    def _calculate_order_size(
        self,
        current_price: Decimal,
        atr_value: Decimal,
    ) -> Decimal:
        """Calculate order size based on risk per trade and ATR."""
        if not self.trade_management_enabled:
            return Decimal("0")

        account_balance = self._get_current_balance()
        risk_per_trade_percent = (
            Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
            / 100
        )
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )

        risk_amount = account_balance * risk_per_trade_percent
        stop_loss_distance = atr_value * stop_loss_atr_multiple

        if stop_loss_distance <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated stop loss distance is zero or negative ({stop_loss_distance}). Cannot determine order size.{RESET}",
            )
            return Decimal("0")

        # Order size in USD value
        order_value = risk_amount / stop_loss_distance
        # Convert to quantity of the asset (e.g., BTC)
        order_qty = order_value / current_price

        # Round order_qty to appropriate precision for the symbol
        order_qty = order_qty.quantize(self.qty_quantize_dec, rounding=ROUND_DOWN)

        self.logger.info(
            f"[{self.symbol}] Calculated order size: {order_qty.normalize()} (Risk: {risk_amount.normalize():.2f} USD)",
        )
        return order_qty

    def sync_positions_from_exchange(self):
        """Fetches current open positions from the exchange and updates the internal list."""
        exchange_positions = get_open_positions_from_exchange(
            self.symbol,
            self.logger,
            ws_manager=self.ws_manager,
        )

        new_open_positions = []
        for ex_pos in exchange_positions:
            # Bybit API returns 'Buy' or 'Sell' for position side
            side = ex_pos["side"]
            qty = Decimal(ex_pos["size"])
            entry_price = Decimal(ex_pos["avgPrice"])
            stop_loss_price = (
                Decimal(ex_pos.get("stopLoss", "0"))
                if ex_pos.get("stopLoss")
                else Decimal("0")
            )
            take_profit_price = (
                Decimal(ex_pos.get("takeProfit", "0"))
                if ex_pos.get("takeProfit")
                else Decimal("0")
            )
            trailing_stop = (
                Decimal(ex_pos.get("trailingStop", "0"))
                if ex_pos.get("trailingStop")
                else Decimal("0")
            )

            # Use positionIdx (converted to string) as the primary unique ID for one-way positions
            # Bybit's positionId from /v5/position/list is often also the positionIdx
            position_id = str(ex_pos.get("positionId", ex_pos.get("positionIdx", 0)))
            position_idx_int = int(ex_pos.get("positionIdx", 0))

            # Check if this position is already in our tracked list
            existing_pos = next(
                (
                    p
                    for p in self.open_positions
                    if p.get("position_id") == position_id and p.get("side") == side
                ),
                None,
            )

            if existing_pos:
                # Update existing position details
                existing_pos.update(
                    {
                        "entry_price": entry_price.quantize(self.price_quantize_dec),
                        "qty": qty.quantize(self.qty_quantize_dec),
                        "stop_loss": stop_loss_price.quantize(self.price_quantize_dec),
                        "take_profit": take_profit_price.quantize(
                            self.price_quantize_dec,
                        ),
                        "trailing_stop_price": trailing_stop.quantize(
                            self.price_quantize_dec,
                        )
                        if trailing_stop
                        else None,
                        # Recalculate 'trailing_stop_activated' if needed based on `trailing_stop` field.
                        "trailing_stop_activated": trailing_stop > 0
                        if self.enable_trailing_stop
                        else False,
                        # Persist breakeven_activated status
                        "breakeven_activated": existing_pos.get(
                            "breakeven_activated",
                            False,
                        ),
                    },
                )
                new_open_positions.append(existing_pos)
            else:
                # Add new position detected on exchange
                self.logger.warning(
                    f"{NEON_YELLOW}[{self.symbol}] Detected new untracked position on exchange. Side: {side}, Qty: {qty}, Entry: {entry_price}. Adding to internal tracking.{RESET}",
                )
                # We can't determine original initial_stop_loss or entry_time easily, so estimate
                new_open_positions.append(
                    {
                        "positionIdx": position_idx_int,
                        "side": side,
                        "entry_price": entry_price.quantize(self.price_quantize_dec),
                        "qty": qty.quantize(self.qty_quantize_dec),
                        "stop_loss": stop_loss_price.quantize(self.price_quantize_dec),
                        "take_profit": take_profit_price.quantize(
                            self.price_quantize_dec,
                        ),
                        "position_id": position_id,
                        "order_id": "UNKNOWN",  # Cannot retrieve original order ID easily from position list
                        "entry_time": datetime.now(
                            TIMEZONE,
                        ),  # Estimate if not available
                        "initial_stop_loss": stop_loss_price.quantize(
                            self.price_quantize_dec,
                        ),  # Assume current SL is initial if not tracked
                        "trailing_stop_activated": trailing_stop > 0
                        if self.enable_trailing_stop
                        else False,
                        "trailing_stop_price": trailing_stop.quantize(
                            self.price_quantize_dec,
                        )
                        if trailing_stop
                        else None,
                        "breakeven_activated": False,  # New position, breakeven not yet activated
                    },
                )

        # Identify positions that were tracked internally but are no longer on the exchange
        # This means they were closed (by SL/TP hit or manual intervention)
        for tracked_pos in self.open_positions:
            is_still_open = any(
                str(ex_pos.get("positionId", ex_pos.get("positionIdx")))
                == tracked_pos.get("position_id")
                and ex_pos["side"] == tracked_pos["side"]
                for ex_pos in exchange_positions
            )
            if not is_still_open:
                self.logger.info(
                    f"{NEON_BLUE}[{self.symbol}] Position {tracked_pos['side']} (ID: {tracked_pos.get('position_id', 'N/A')}) no longer open on exchange. Marking as closed.{RESET}",
                )
                # Record this closure in performance_tracker if it was successfully opened by us
                # (This part would ideally be called by `manage_positions` when it detects an actual close event from exchange)

        self.open_positions = new_open_positions
        if not self.open_positions:
            self.logger.debug(
                f"[{self.symbol}] No active positions being tracked internally.",
            )

    def open_position(
        self,
        signal_side: Literal["Buy", "Sell"],
        current_price: Decimal,
        atr_value: Decimal,
    ) -> dict | None:
        """Open a new position if conditions allow, interacting with the Bybit API."""
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Trade management is disabled. Skipping opening position.{RESET}",
            )
            return None

        self.sync_positions_from_exchange()  # Always sync before opening to get latest count
        if len(self.get_open_positions()) >= self.max_open_positions:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}",
            )
            return None

        # Ensure we don't open multiple positions of the same side if in one-way mode.
        # Bybit's API might allow it, but conceptually for a bot, it's often one per side.
        if any(
            p["side"].upper() == signal_side.upper() for p in self.get_open_positions()
        ):
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Already have an open {signal_side} position. Skipping new entry.{RESET}",
            )
            return None

        order_qty = self._calculate_order_size(current_price, atr_value)
        if order_qty <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Order quantity is zero or negative ({order_qty}). Cannot open position.{RESET}",
            )
            return None

        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"]),
        )

        # Calculate initial SL and TP based on current price
        if signal_side == "Buy":
            initial_stop_loss = (
                current_price - (atr_value * stop_loss_atr_multiple)
            ).quantize(self.price_quantize_dec, rounding=ROUND_DOWN)
            take_profit = (
                current_price + (atr_value * take_profit_atr_multiple)
            ).quantize(self.price_quantize_dec, rounding=ROUND_DOWN)
        else:  # Sell
            initial_stop_loss = (
                current_price + (atr_value * stop_loss_atr_multiple)
            ).quantize(self.price_quantize_dec, rounding=ROUND_DOWN)
            take_profit = (
                current_price - (atr_value * take_profit_atr_multiple)
            ).quantize(self.price_quantize_dec, rounding=ROUND_DOWN)

        # --- Place Market Order ---
        order_result = place_market_order(
            self.symbol,
            signal_side,
            order_qty,
            self.logger,
        )

        if not order_result:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Failed to place market order for {signal_side} {order_qty.normalize()}.{RESET}",
            )
            return None

        # Extract actual filled price and quantity from order result
        # For a market order, the `price` in the response is usually the filled price.
        # If filledQty is available, use that.
        filled_qty = Decimal(
            order_result.get("qty", str(order_qty)),
        )  # Fallback to requested qty
        filled_price = Decimal(
            order_result.get("price", str(current_price)),
        )  # Fallback to current price if not explicitly returned
        order_id = order_result.get("orderId")

        # Bybit often returns `positionIdx` in the order result, or we assume 0 for one-way mode.
        # The positionId from /v5/position/list is also often 0 for one-way
        position_idx_on_exchange = int(order_result.get("positionIdx", 0))

        # --- Set TP/SL for the newly opened position ---
        # It's crucial to set TP/SL *after* the position is open on the exchange.
        # Bybit's set-trading-stop endpoint uses the position's `positionIdx`.
        tpsl_result = set_position_tpsl(
            self.symbol,
            take_profit=take_profit,
            stop_loss=initial_stop_loss,
            logger=self.logger,
            position_idx=position_idx_on_exchange,
        )

        if not tpsl_result:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Failed to set TP/SL for new position. Manual intervention needed!{RESET}",
            )
            # Consider closing the position if TP/SL cannot be set for risk management.
            # For this snippet, we proceed but log a severe warning.

        new_position = {
            "positionIdx": position_idx_on_exchange,
            "symbol": self.symbol,
            "side": signal_side,
            "entry_price": filled_price.quantize(self.price_quantize_dec),
            "qty": filled_qty.quantize(self.qty_quantize_dec),
            "stop_loss": initial_stop_loss,  # This will be the dynamic SL
            "take_profit": take_profit,
            "position_id": str(
                position_idx_on_exchange,
            ),  # Using positionIdx as its unique ID for one-way mode
            "order_id": order_id,
            "entry_time": datetime.now(TIMEZONE),
            "initial_stop_loss": initial_stop_loss,  # Store original SL
            "trailing_stop_activated": False,
            "trailing_stop_price": None,  # Will be set when TSL is activated on exchange
            "breakeven_activated": False,
        }
        self.open_positions.append(new_position)
        self.logger.info(
            f"{NEON_GREEN}[{self.symbol}] Successfully opened {signal_side} position and set initial TP/SL: {new_position}{RESET}",
        )
        return new_position

    def close_position(
        self,
        position: dict,
        current_price: Decimal,
        performance_tracker: Any,
        closed_by: str = "SIGNAL",
    ) -> None:
        """Closes an existing position by placing a market order in the opposite direction."""
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Trade management is disabled. Cannot close position.{RESET}",
            )
            return

        side_to_close = "Sell" if position["side"] == "Buy" else "Buy"
        qty_to_close = position["qty"]

        self.logger.info(
            f"{NEON_BLUE}[{self.symbol}] Attempting to close {position['side']} position (ID: {position['position_id']}) with {side_to_close} order for {qty_to_close.normalize()}...{RESET}",
        )

        # Place a market order to close the position
        order_result = place_market_order(
            self.symbol,
            side_to_close,
            qty_to_close,
            self.logger,
        )

        if order_result:
            self.logger.info(
                f"{NEON_GREEN}[{self.symbol}] Close order placed successfully: {order_result}{RESET}",
            )
            # Assume immediate fill for market order and record the trade
            exit_price = Decimal(
                order_result.get("price", str(current_price)),
            ).quantize(self.price_quantize_dec)

            pnl = (
                (exit_price - position["entry_price"]) * position["qty"]
                if position["side"] == "Buy"
                else (position["entry_price"] - exit_price) * position["qty"]
            )

            performance_tracker.record_trade(
                {
                    **position,
                    "exit_price": exit_price,
                    "exit_time": datetime.now(UTC),
                    "closed_by": closed_by,
                },
                pnl,
            )

            # Remove from internal tracking
            self.open_positions = [
                p
                for p in self.open_positions
                if p["position_id"] != position["position_id"]
                or p["side"] != position["side"]
            ]
            self.logger.info(
                f"{NEON_GREEN}[{self.symbol}] Position (ID: {position['position_id']}) removed from internal tracking.{RESET}",
            )
        else:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Failed to place close order for position (ID: {position['position_id']}). Manual intervention might be needed!{RESET}",
            )

    def manage_positions(
        self,
        current_price: Decimal,
        performance_tracker: Any,
        atr_value: Decimal,
    ) -> None:
        """Syncs open positions from the exchange and applies trailing stop logic.
        Records closed positions based on exchange updates.
        """
        if not self.trade_management_enabled:
            return

        # 1. Sync internal state with actual exchange positions
        self.sync_positions_from_exchange()

        # Create a copy to iterate, allowing modification of original list if positions are closed.
        current_internal_positions = list(self.open_positions)
        positions_closed_on_exchange_ids = set()

        # Define precision for quantization
        price_precision_exponent = max(
            0,
            self.config["trade_management"]["price_precision"] - 1,
        )
        quantize_dec = Decimal("0." + "0" * price_precision_exponent + "1")

        # Iterate through the internally tracked positions
        for position in current_internal_positions:
            # First, check if this position is still genuinely open on the exchange
            # This is implicitly handled by `sync_positions_from_exchange` which rebuilds `self.open_positions`
            # If a position exists in `self.open_positions` after sync, it means it's still open on the exchange.
            # If it's not in `self.open_positions` after sync, it means it was closed on the exchange.

            # Retrieve the latest version of the position from `self.open_positions` after sync
            # This is important to get the most up-to-date SL/TP/trailingStop values from Bybit
            latest_pos_from_sync = next(
                (
                    p
                    for p in self.open_positions
                    if p.get("position_id") == position.get("position_id")
                    and p.get("side") == position.get("side")
                ),
                None,
            )

            if not latest_pos_from_sync:
                # Position was closed on the exchange. Record it.
                # Since we don't get direct 'closed by' reason from just `position/list` for historical close,
                # we'll use our internal current_price vs. position's last known SL/TP to infer.
                # In a real bot, you'd check historical orders or webhooks for precise exit details.
                close_price = current_price
                closed_by = "UNKNOWN"
                if position["side"] == "Buy":
                    if current_price <= position["stop_loss"]:
                        closed_by = "STOP_LOSS"
                    elif current_price >= position["take_profit"]:
                        closed_by = "TAKE_PROFIT"
                elif current_price >= position["stop_loss"]:
                    closed_by = "STOP_LOSS"
                elif current_price <= position["take_profit"]:
                    closed_by = "TAKE_PROFIT"

                # Calculate PnL for recording
                pnl = (
                    (close_price - position["entry_price"]) * position["qty"]
                    if position["side"] == "Buy"
                    else (position["entry_price"] - close_price) * position["qty"]
                )

                # Ensure the trade is only recorded once
                # A more robust system would involve a persistent storage for positions and trades.
                performance_tracker.record_trade(
                    {
                        **position,
                        "exit_price": close_price.quantize(self.price_quantize_dec),
                        "exit_time": datetime.now(UTC),
                        "closed_by": closed_by,
                    },
                    pnl,
                )
                positions_closed_on_exchange_ids.add(position.get("position_id"))
                self.logger.info(
                    f"{NEON_BLUE}[{self.symbol}] Detected and recorded closure of {position['side']} position (ID: {position.get('position_id')}). PnL: {pnl.normalize():.2f}{RESET}",
                )
                continue  # Skip trailing stop logic for this position as it's closed

            # Use the latest synced position details for trailing stop logic
            position = latest_pos_from_sync

            side = position["side"]
            entry_price = position["entry_price"]
            current_stop_loss_on_exchange = position[
                "stop_loss"
            ]  # This is what Bybit has for SL
            # take_profit_on_exchange = position["take_profit"] # Not directly used for TSL logic, but could be for other checks

            # --- UPGRADE 1: Dynamic Stop Loss Adjustment (Breakeven / Profit Lock-in) ---
            potential_sl_update = None
            if atr_value > 0:
                profit_since_entry_atr = (
                    current_price - entry_price
                ).copy_abs() / atr_value

                # Breakeven trigger
                if (
                    self.move_to_breakeven_atr_trigger > 0
                    and not position.get("breakeven_activated", False)
                    and (
                        (
                            side == "Buy"
                            and current_price
                            >= (
                                entry_price
                                + atr_value * self.move_to_breakeven_atr_trigger
                            )
                        )
                        or (
                            side == "Sell"
                            and current_price
                            <= (
                                entry_price
                                - atr_value * self.move_to_breakeven_atr_trigger
                            )
                        )
                    )
                ):
                    breakeven_sl = entry_price  # Simple breakeven
                    if side == "Buy":
                        potential_sl_update = max(
                            current_stop_loss_on_exchange,
                            breakeven_sl,
                        ).quantize(quantize_dec)
                    else:  # Sell
                        potential_sl_update = min(
                            current_stop_loss_on_exchange,
                            breakeven_sl,
                        ).quantize(quantize_dec)

                    if potential_sl_update != current_stop_loss_on_exchange:
                        self.logger.info(
                            f"{NEON_BLUE}[{self.symbol}] Breakeven condition met for {side} position (ID: {position['position_id']}). Moving SL to {potential_sl_update.normalize()}.{RESET}",
                        )
                        position["breakeven_activated"] = (
                            True  # Mark as activated to avoid re-triggering
                        )
                    else:
                        potential_sl_update = None  # No actual update needed

                # Profit Lock-in trigger (after breakeven, or independently)
                # This can run even if trailing stop is active, but trailing stop logic might override it.
                if self.profit_lock_in_atr_multiple > 0:
                    profit_lock_sl_candidate = (
                        (current_price - (atr_value * self.profit_lock_in_atr_multiple))
                        if side == "Buy"
                        else (
                            current_price
                            + (atr_value * self.profit_lock_in_atr_multiple)
                        )
                    )
                    profit_lock_sl_candidate = profit_lock_sl_candidate.quantize(
                        quantize_dec,
                    )

                    should_update_profit_lock = False
                    if (
                        side == "Buy"
                        and profit_lock_sl_candidate > current_stop_loss_on_exchange
                        and profit_lock_sl_candidate > entry_price
                    ) or (
                        side == "Sell"
                        and profit_lock_sl_candidate < current_stop_loss_on_exchange
                        and profit_lock_sl_candidate < entry_price
                    ):
                        should_update_profit_lock = True

                    if should_update_profit_lock:
                        # If a breakeven update was already proposed, take the more favorable (higher for buy, lower for sell)
                        if potential_sl_update:
                            if side == "Buy":
                                potential_sl_update = max(
                                    potential_sl_update,
                                    profit_lock_sl_candidate,
                                )
                            else:  # Sell
                                potential_sl_update = min(
                                    potential_sl_update,
                                    profit_lock_sl_candidate,
                                )
                        else:
                            potential_sl_update = profit_lock_sl_candidate
                        self.logger.info(
                            f"{NEON_BLUE}[{self.symbol}] Profit lock-in condition met for {side} position (ID: {position['position_id']}). Moving SL to {potential_sl_update.normalize()}.{RESET}",
                        )

            # --- Trailing Stop Loss Logic ---
            if self.enable_trailing_stop and atr_value > 0:
                profit_trigger_level = (
                    entry_price + (atr_value * self.break_even_atr_trigger)
                    if side == "Buy"
                    else entry_price - (atr_value * self.break_even_atr_trigger)
                )

                # Check if price has moved sufficiently into profit to activate/adjust TSL
                if (side == "Buy" and current_price >= profit_trigger_level) or (
                    side == "Sell" and current_price <= profit_trigger_level
                ):
                    position["trailing_stop_activated"] = True

                    # Calculate new potential trailing stop based on current price and ATR multiple
                    new_trailing_stop_candidate = (
                        (
                            current_price
                            - (atr_value * self.trailing_stop_atr_multiple)
                        ).quantize(self.price_quantize_dec, rounding=ROUND_DOWN)
                        if side == "Buy"
                        else (
                            current_price
                            + (atr_value * self.trailing_stop_atr_multiple)
                        ).quantize(self.price_quantize_dec, rounding=ROUND_DOWN)
                    )

                    should_update_tsl = False

                    if side == "Buy":
                        # Move SL up, but not below its initial entry value
                        if new_trailing_stop_candidate > current_stop_loss_on_exchange:
                            # Prioritize the higher (more protective) SL between new TSL and existing dynamic SL/initial SL
                            proposed_sl = max(
                                new_trailing_stop_candidate,
                                position["initial_stop_loss"],
                            ).quantize(self.price_quantize_dec)
                            if (
                                potential_sl_update
                            ):  # If breakeven/profit-lock also proposed an update
                                proposed_sl = max(proposed_sl, potential_sl_update)
                            if proposed_sl > current_stop_loss_on_exchange:
                                should_update_tsl = True
                                potential_sl_update = (
                                    proposed_sl  # TSL logic overrides/takes precedence
                                )
                    elif side == "Sell":
                        # Move SL down, but not above its initial entry value
                        if new_trailing_stop_candidate < current_stop_loss_on_exchange:
                            # Prioritize the lower (more protective) SL
                            proposed_sl = min(
                                new_trailing_stop_candidate,
                                position["initial_stop_loss"],
                            ).quantize(self.price_quantize_dec)
                            if (
                                potential_sl_update
                            ):  # If breakeven/profit-lock also proposed an update
                                proposed_sl = min(proposed_sl, potential_sl_update)
                            if proposed_sl < current_stop_loss_on_exchange:
                                should_update_tsl = True
                                potential_sl_update = (
                                    proposed_sl  # TSL logic overrides/takes precedence
                                )

                    if not should_update_tsl and potential_sl_update is None:
                        # If TSL criteria not met for update, but breakeven/profit-lock proposed one, use it
                        pass  # potential_sl_update is already set, or None if no updates
                    elif should_update_tsl and potential_sl_update is not None:
                        pass  # potential_sl_update already correctly set by TSL logic
                    elif should_update_tsl and potential_sl_update is None:
                        potential_sl_update = (
                            proposed_sl  # Just use TSL if no previous update
                        )

            if (
                potential_sl_update is not None
                and potential_sl_update != current_stop_loss_on_exchange
            ):
                # Call Bybit API to update the stop loss
                tpsl_update_result = set_position_tpsl(
                    self.symbol,
                    take_profit=position["take_profit"],  # Keep TP the same
                    stop_loss=potential_sl_update,
                    logger=self.logger,
                    position_idx=position["positionIdx"],
                )
                if tpsl_update_result:
                    # Update internal tracking
                    position["stop_loss"] = potential_sl_update
                    position["trailing_stop_price"] = (
                        potential_sl_update  # Store the TSL value (or latest dynamic SL)
                    )
                    self.logger.info(
                        f"{NEON_GREEN}[{self.symbol}] Stop Loss Updated for {side} position (ID: {position['position_id']}): Entry: {entry_price.normalize()}, Current Price: {current_price.normalize()}, New SL: {potential_sl_update.normalize()}{RESET}",
                    )
                else:
                    self.logger.error(
                        f"{NEON_RED}[{self.symbol}] Failed to update SL for {side} position (ID: {position['position_id']}).{RESET}",
                    )

            # Note: The actual closing of the position (by SL or TP) is handled by the exchange.
            # Our `sync_positions_from_exchange` will detect if a position is no longer present.

        # After checking all positions, ensure `self.open_positions` only contains truly open ones.
        # This is already handled by `self.sync_positions_from_exchange()` at the start.
        # However, to be extra robust, one could filter out the `positions_closed_on_exchange_ids` here as well,
        # but `sync_positions_from_exchange` should already have removed them.
        self.open_positions = [
            pos
            for pos in self.open_positions
            if pos.get("position_id") not in positions_closed_on_exchange_ids
        ]

    def get_open_positions(self) -> list[dict]:
        """Return a list of currently open positions tracked internally."""
        # This is just returning the internal state, which is periodically synced with exchange
        return self.open_positions


# --- Performance Tracking ---
class PerformanceTracker:
    """Tracks and reports trading performance."""

    def __init__(self, logger: logging.Logger):
        """Initializes the PerformanceTracker."""
        self.logger = logger
        self.trades: list[dict] = []
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0

    def record_trade(self, position: dict, pnl: Decimal) -> None:
        """Record a completed trade."""
        trade_record = {
            "entry_time": position["entry_time"],
            "exit_time": position["exit_time"],
            "symbol": position["symbol"],
            "side": position["side"],
            "entry_price": position["entry_price"],
            "exit_price": position["exit_price"],
            "qty": position["qty"],
            "pnl": pnl,
            "closed_by": position["closed_by"],
        }
        self.trades.append(trade_record)
        self.total_pnl += pnl
        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.logger.info(
            f"{NEON_CYAN}[{position['symbol']}] Trade recorded. Current Total PnL: {self.total_pnl.normalize():.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}",
        )
        self.logger.info("Trade recorded", extra=trade_record)

    def get_summary(self) -> dict:
        """Return a summary of all recorded trades."""
        total_trades = len(self.trades)
        win_rate = (self.wins / total_trades) * 100 if total_trades > 0 else 0

        return {
            "total_trades": total_trades,
            "total_pnl": self.total_pnl,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": f"{win_rate:.2f}%",
        }


# --- Alert System ---
class AlertSystem:
    """Handles sending alerts for critical events."""

    def __init__(self, logger: logging.Logger):
        """Initializes the AlertSystem."""
        self.logger = logger

    def send_alert(
        self,
        message: str,
        level: Literal["INFO", "WARNING", "ERROR"],
    ) -> None:
        """Send an alert (currently logs it)."""
        if level == "INFO":
            self.logger.info(f"{NEON_BLUE}ALERT: {message}{RESET}")
        elif level == "WARNING":
            self.logger.warning(f"{NEON_YELLOW}ALERT: {message}{RESET}")
        elif level == "ERROR":
            self.logger.error(f"{NEON_RED}ALERT: {message}{RESET}")
        # In a real bot, integrate with Telegram, Discord, Email etc.


# UPGRADE 3: News/Sentiment Integration Placeholder
def fetch_latest_sentiment(symbol: str, logger: logging.Logger) -> float | None:
    """Placeholder function for fetching market sentiment (e.g., from an external API).
    Returns a float between 0 (very bearish) and 1 (very bullish), or None if unavailable.
    """
    # In a real scenario, this would involve API calls to news sentiment services
    # or social media analysis. For this exercise, it's a dummy value.
    logger.debug(f"[{symbol}] Fetching latest sentiment (placeholder)...")

    # Simulate some sentiment fluctuation for testing
    current_minute = datetime.now(TIMEZONE).minute
    if current_minute % 5 == 0:
        return 0.8  # Bullish
    if current_minute % 5 == 1:
        return 0.2  # Bearish
    return 0.5  # Neutral
    # return None # Or return None to simulate no sentiment data


# --- WebSocket Manager for real-time data ---
class BybitWebSocketManager:
    """Manages WebSocket connections to Bybit for real-time market and private data."""

    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.symbol = config["symbol"]
        self.api_key = API_KEY
        self.api_secret = API_SECRET

        self._ws_public_thread = None
        self._ws_private_thread = None
        self.ws_public = None
        self.ws_private = None

        # Data storage with locks for thread safety
        self.latest_klines: pd.DataFrame = pd.DataFrame()
        self._klines_lock = threading.Lock()
        self.latest_orderbook: dict[str, Any] = {"bids": [], "asks": []}
        self._orderbook_lock = threading.Lock()
        # self.latest_trades: deque = deque(maxlen=config.get("orderbook_limit", 50)) # Trades not currently used by Analyzer
        # self._trades_lock = threading.Lock()
        self.latest_ticker: dict[str, Any] = {}
        self._ticker_lock = threading.Lock()

        # Queue for private updates to be processed by main thread
        self.private_updates_queue: queue.Queue = queue.Queue()
        self._private_updates_lock = threading.Lock()

        # Events to signal initial data receipt
        self.initial_kline_received = threading.Event()
        self.initial_orderbook_received = threading.Event()
        self.initial_private_data_received = threading.Event()

        # Topics to subscribe to
        self.public_topics = [
            f"kline.{self.config['interval']}.{self.symbol}",
            f"orderbook.{self.config['orderbook_limit']}.{self.symbol}",
            # f"publicTrade.{self.symbol}", # Trades not currently used by Analyzer
            f"tickers.{self.symbol}",
        ]
        self.private_topics = DEFAULT_PRIVATE_TOPICS  # "order", "position", "wallet"

        self.is_connected_public = False
        self.is_connected_private = False
        self._stop_event = (
            threading.Event()
        )  # Event to gracefully stop WebSocket threads

    def _on_open_public(self, ws):
        self.logger.info(f"{NEON_BLUE}[WS Public] Connection opened.{RESET}")
        self._subscribe(ws, self.public_topics)
        self.is_connected_public = True

    def _on_open_private(self, ws):
        self.logger.info(
            f"{NEON_BLUE}[WS Private] Connection opened. Authenticating...{RESET}",
        )
        expires = int(time.time() * 1000) + 10000  # Auth valid for 10 seconds
        signature = generate_ws_signature(self.api_key, self.api_secret, expires)
        auth_message = {"op": "auth", "args": [self.api_key, expires, signature]}
        ws.send(json.dumps(auth_message))
        self.logger.debug(f"[WS Private] Auth message sent: {auth_message}")
        # Subscribe after a short delay to allow auth to complete
        threading.Timer(1, self._subscribe, args=(ws, self.private_topics)).start()
        self.is_connected_private = True

    def _on_message_public(self, ws, message):
        data = json.loads(message)
        op = data.get("op")
        topic = data.get("topic")

        if op == "subscribe":
            self.logger.debug(
                f"{NEON_BLUE}[WS Public] Subscribed to {data.get('success_topics')}{RESET}",
            )
            return
        if op == "pong":
            self.logger.debug(f"{NEON_BLUE}[WS Public] Received pong.{RESET}")
            return
        if data.get("type") == "snapshot" and topic.startswith("kline"):
            self._update_klines(data["data"], is_snapshot=True)
            self.initial_kline_received.set()
        elif data.get("type") == "delta" and topic.startswith("kline"):
            self._update_klines(data["data"], is_snapshot=False)
        elif data.get("type") == "snapshot" and topic.startswith("orderbook"):
            self._update_orderbook(data["data"], is_snapshot=True)
            self.initial_orderbook_received.set()
        elif data.get("type") == "delta" and topic.startswith("orderbook"):
            self._update_orderbook(data["data"], is_snapshot=False)
        # elif topic.startswith("publicTrade"): # Trades not currently used by Analyzer
        #    self._update_trades(data["data"])
        elif topic.startswith("tickers"):
            if data.get("data"):  # Ensure data is not empty
                self._update_ticker(data["data"])
        else:
            self.logger.debug(
                f"{NEON_BLUE}[WS Public] Unhandled message: {data}{RESET}",
            )

    def _on_message_private(self, ws, message):
        data = json.loads(message)
        op = data.get("op")

        if op == "auth":
            if data.get("success"):
                self.logger.info(
                    f"{NEON_GREEN}[WS Private] Authentication successful.{RESET}",
                )
            else:
                self.logger.error(
                    f"{NEON_RED}[WS Private] Authentication failed: {data.get('retMsg')}. Reconnecting.{RESET}",
                )
                self.ws_private.close()  # Close to trigger reconnect and re-auth
            return
        if op == "subscribe":
            self.logger.debug(
                f"{NEON_BLUE}[WS Private] Subscribed to {data.get('success_topics')}{RESET}",
            )
            return
        if op == "pong":
            self.logger.debug(f"{NEON_BLUE}[WS Private] Received pong.{RESET}")
            return

        category = data.get("topic")
        if category in self.private_topics:
            self.logger.debug(
                f"{NEON_BLUE}[WS Private] Received {category} update: {data['data']}{RESET}",
            )
            with self._private_updates_lock:
                self.private_updates_queue.put(data)
            self.initial_private_data_received.set()
        else:
            self.logger.debug(
                f"{NEON_BLUE}[WS Private] Unhandled private message: {data}{RESET}",
            )

    def _on_error(self, ws, error):
        ws_name = ws.url.split("/")[-1]
        # The error argument can be an exception or a status code.
        # Bybit's websocket can send a status code of 0 for an OK event, which can be caught by on_error.
        if isinstance(error, (int, float)) and error == 0:
            self.logger.debug(
                f"{NEON_BLUE}[WS {ws_name}] Received Bybit 'OK' status (error code 0).{RESET}",
            )
            return

        # The websocket-client library may pass the string "0" as an error.
        if isinstance(error, str) and error == "0":
            self.logger.debug(
                f"{NEON_BLUE}[WS {ws_name}] Received Bybit 'OK' status (error string '0').{RESET}",
            )
            return

        if isinstance(error, websocket.WebSocketConnectionClosedException):
            self.logger.warning(
                f"{NEON_YELLOW}[WS {ws_name}] Connection closed: {error}{RESET}",
            )
            return

        # Log other exceptions as errors.
        self.logger.error(
            f"{NEON_RED}[WS {ws_name}] Unhandled WebSocket Error: {error}{RESET}",
            exc_info=True,
        )

    def _on_close(self, ws, close_status_code, close_msg):
        url_type = "Public" if "public" in ws.url else "Private"
        self.logger.warning(
            f"{NEON_YELLOW}[WS {url_type}] Connection closed: {close_status_code} - {close_msg}{RESET}",
        )
        if url_type == "Public":
            self.is_connected_public = False
        else:
            self.is_connected_private = False

        if not self._stop_event.is_set():
            self.logger.info(
                f"{NEON_BLUE}[WS {url_type}] Attempting to reconnect...{RESET}",
            )
            time.sleep(WS_RECONNECT_DELAY_SECONDS)
            if url_type == "Public":
                self._ws_public_thread = threading.Thread(
                    target=self._connect_ws_thread,
                    args=(
                        WS_PUBLIC_BASE_URL,
                        self._on_message_public,
                        self._on_open_public,
                    ),
                )
                self._ws_public_thread.daemon = True
                self._ws_public_thread.start()
            else:  # Private
                self._ws_private_thread = threading.Thread(
                    target=self._connect_ws_thread,
                    args=(
                        WS_PRIVATE_BASE_URL,
                        self._on_message_private,
                        self._on_open_private,
                    ),
                )
                self._ws_private_thread.daemon = True
                self._ws_private_thread.start()

    def _connect_ws_thread(self, url, on_message_handler, on_open_handler):
        retries = 0
        while not self._stop_event.is_set() and retries < WS_RECONNECT_ATTEMPTS:
            try:
                ws = websocket.WebSocketApp(
                    url,
                    on_open=on_open_handler,
                    on_message=on_message_handler,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                if "public" in url:
                    self.ws_public = ws
                else:
                    self.ws_private = ws

                ws.run_forever(
                    ping_interval=20,
                    ping_timeout=10,
                    sslopt={"cert_reqs": ssl.CERT_NONE},
                )
            except Exception as e:
                self.logger.error(
                    f"{NEON_RED}[WS {url.split('/')[-1]}] Failed to connect: {e}. Retrying...{RESET}",
                )
                retries += 1
                time.sleep(WS_RECONNECT_DELAY_SECONDS)

        if retries == WS_RECONNECT_ATTEMPTS and not self._stop_event.is_set():
            self.logger.error(
                f"{NEON_RED}[WS {url.split('/')[-1]}] Max reconnection attempts reached. Giving up.{RESET}",
            )

    def _subscribe(self, ws, topics: list[str]):
        """Sends subscription messages for the given topics."""
        for topic in topics:
            sub_message = {"op": "subscribe", "args": [topic]}
            try:
                ws.send(json.dumps(sub_message))
                self.logger.debug(
                    f"{NEON_BLUE}[WS] Sent subscription for: {topic}{RESET}",
                )
            except websocket.WebSocketConnectionClosedException:
                self.logger.warning(
                    f"{NEON_YELLOW}[WS] Failed to send subscription for {topic}: Connection closed.{RESET}",
                )
            except Exception as e:
                self.logger.error(
                    f"{NEON_RED}[WS] Error sending subscription for {topic}: {e}{RESET}",
                )

    def start_public_stream(self):
        """Starts the public WebSocket stream in a separate thread."""
        self._stop_event.clear()
        if not self._ws_public_thread or not self._ws_public_thread.is_alive():
            self._ws_public_thread = threading.Thread(
                target=self._connect_ws_thread,
                args=(
                    WS_PUBLIC_BASE_URL,
                    self._on_message_public,
                    self._on_open_public,
                ),
            )
            self._ws_public_thread.daemon = True
            self._ws_public_thread.start()
            self.logger.info(
                f"{NEON_BLUE}Public WebSocket stream started for {self.symbol}.{RESET}",
            )

    def start_private_stream(self):
        """Starts the private WebSocket stream in a separate thread, with authentication."""
        if not API_KEY or not API_SECRET:
            self.logger.warning(
                f"{NEON_YELLOW}API_KEY or API_SECRET not set. Skipping private WebSocket stream.{RESET}",
            )
            return
        self._stop_event.clear()
        if not self._ws_private_thread or not self._ws_private_thread.is_alive():
            self._ws_private_thread = threading.Thread(
                target=self._connect_ws_thread,
                args=(
                    WS_PRIVATE_BASE_URL,
                    self._on_message_private,
                    self._on_open_private,
                ),
            )
            self._ws_private_thread.daemon = True
            self._ws_private_thread.start()
            self.logger.info(f"{NEON_BLUE}Private WebSocket stream started.{RESET}")

    def stop_all_streams(self):
        """Stops all active WebSocket connections and their threads."""
        self.logger.info(f"{NEON_BLUE}Stopping all WebSocket streams...{RESET}")
        self._stop_event.set()  # Signal threads to stop
        if self.ws_public:
            self.ws_public.close()
        if self.ws_private:
            self.ws_private.close()
        # Join threads to ensure they terminate cleanly
        if self._ws_public_thread and self._ws_public_thread.is_alive():
            self._ws_public_thread.join(timeout=5)
        if self._ws_private_thread and self._ws_private_thread.is_alive():
            self._ws_private_thread.join(timeout=5)
        self.logger.info(f"{NEON_BLUE}All WebSocket streams stopped.{RESET}")

    def _update_klines(self, kline_data_list: list[dict], is_snapshot: bool):
        """Processes incoming kline data from WebSocket."""
        if not kline_data_list:
            return

        new_data = []
        for item in kline_data_list:
            new_data.append(
                {
                    "start_time": pd.to_datetime(
                        item["start"],
                        unit="ms",
                        utc=True,
                    ).tz_convert(TIMEZONE),
                    "open": Decimal(item["open"]),
                    "high": Decimal(item["high"]),
                    "low": Decimal(item["low"]),
                    "close": Decimal(item["close"]),
                    "volume": Decimal(item["volume"]),
                    "turnover": Decimal(item["turnover"]),
                },
            )

        df_new = pd.DataFrame(new_data).set_index("start_time")

        with self._klines_lock:
            if is_snapshot:
                self.latest_klines = df_new
                self.logger.debug(
                    f"{NEON_BLUE}[WS Klines] Snapshot received. New df size: {len(self.latest_klines)}{RESET}",
                )
            else:
                for index, row in df_new.iterrows():
                    if index in self.latest_klines.index:
                        self.latest_klines.loc[index] = row
                    else:
                        # Append new bar only if it's strictly newer than the last bar
                        if (
                            not self.latest_klines.empty
                            and index <= self.latest_klines.index[-1]
                        ):
                            self.logger.warning(
                                f"{NEON_YELLOW}[WS Klines] Received out-of-order or duplicate kline for {index}. Skipping.{RESET}",
                            )
                            continue
                        self.latest_klines = pd.concat(
                            [self.latest_klines, pd.DataFrame([row])],
                        )
                        self.logger.debug(
                            f"{NEON_BLUE}[WS Klines] Appended new kline for {index}. New df size: {len(self.latest_klines)}{RESET}",
                        )
            self.latest_klines.sort_index(inplace=True)
            max_kline_history = 1000  # Keep a reasonable history
            if len(self.latest_klines) > max_kline_history:
                self.latest_klines = self.latest_klines.iloc[-max_kline_history:]

            # Ensure all numeric columns are Decimal type after updates
            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                self.latest_klines[col] = self.latest_klines[col].apply(Decimal)

    def _update_orderbook(self, orderbook_data: dict, is_snapshot: bool):
        """Processes incoming orderbook data from WebSocket."""
        with self._orderbook_lock:
            if is_snapshot:
                self.latest_orderbook = {
                    "bids": [
                        [Decimal(price), Decimal(qty)]
                        for price, qty in orderbook_data.get("b", [])
                    ],
                    "asks": [
                        [Decimal(price), Decimal(qty)]
                        for price, qty in orderbook_data.get("a", [])
                    ],
                    "timestamp": datetime.now(TIMEZONE),
                }
                self.logger.debug(
                    f"{NEON_BLUE}[WS Orderbook] Snapshot received. Bids: {len(self.latest_orderbook['bids'])}, Asks: {len(self.latest_orderbook['asks'])}{RESET}",
                )
            else:
                # Bybit's V5 orderbook uses full snapshots for deltas if 'u' (update_id) is used.
                # If it's a "delta" event, the structure indicates what to update.
                # The provided "delta" event type for orderbook is not standard for Bybit's V5 public stream.
                # It's more common to receive full snapshots or update lists based on sequence numbers.
                # This implementation assumes complete bid/ask lists are sent with each "delta" for simplicity,
                # if the actual Bybit V5 delta parsing is more complex, this needs to be adapted.
                # Currently, the public orderbook stream sends full `b` and `a` arrays on update.
                if not self.initial_orderbook_received.is_set():
                    self.logger.warning(
                        f"{NEON_YELLOW}[WS Orderbook] Received delta but no snapshot. Requesting resync or waiting for snapshot.{RESET}",
                    )
                    return

                # Assuming the 'b' and 'a' fields in delta are the new full state
                new_bids = [
                    [Decimal(price), Decimal(qty)]
                    for price, qty in orderbook_data.get("b", [])
                ]
                new_asks = [
                    [Decimal(price), Decimal(qty)]
                    for price, qty in orderbook_data.get("a", [])
                ]

                self.latest_orderbook["bids"] = new_bids
                self.latest_orderbook["asks"] = new_asks
                self.latest_orderbook["timestamp"] = datetime.now(TIMEZONE)
                self.logger.debug(
                    f"{NEON_BLUE}[WS Orderbook] Delta/Update received. Bids: {len(self.latest_orderbook['bids'])}, Asks: {len(self.latest_orderbook['asks'])}{RESET}",
                )

    # def _update_trades(self, trades_data: list[dict]): # Trades not currently used by Analyzer
    #    """Processes incoming trade data from WebSocket."""
    #    with self._trades_lock:
    #        for trade in trades_data:
    #            self.latest_trades.append(
    #                {
    #                    "timestamp": pd.to_datetime(trade["timestamp"], unit="ms", utc=True).tz_convert(TIMEZONE),
    #                    "side": trade["side"],
    #                    "qty": Decimal(trade["size"]),
    #                    "price": Decimal(trade["price"]),
    #                }
    #            )
    #    self.logger.debug(f"{NEON_BLUE}[WS Trades] Updated. Current trades count: {len(self.latest_trades)}{RESET}")

    def _update_ticker(self, ticker_data: dict):
        """Processes incoming ticker data from WebSocket."""
        with self._ticker_lock:
            # Safely access 'lastPrice' and 'ask1Price' using .get() with a default value
            last_price = ticker_data.get("lastPrice", "0")
            ask_price = ticker_data.get(
                "ask1Price",
                "0",
            )  # Assuming ask1Price is the correct key for ask price

            self.latest_ticker = {
                "symbol": ticker_data.get(
                    "symbol",
                    self.symbol,
                ),  # Safely get symbol too
                "lastPrice": Decimal(last_price),
                "bidPrice": Decimal(
                    ticker_data.get("bid1Price", "0"),
                ),  # Safely get bidPrice
                "askPrice": Decimal(ask_price),
                "timestamp": datetime.now(TIMEZONE),
            }
        self.logger.debug(
            f"{NEON_BLUE}[WS Ticker] Updated. Last Price: {self.latest_ticker['lastPrice']}{RESET}",
        )

    def get_latest_kline_df(self) -> pd.DataFrame:
        """Retrieves a copy of the latest kline DataFrame."""
        with self._klines_lock:
            return self.latest_klines.copy()

    def get_latest_orderbook_dict(self) -> dict[str, Any]:
        """Retrieves a copy of the latest orderbook dictionary."""
        with self._orderbook_lock:
            return self.latest_orderbook.copy()

    def get_latest_ticker(self) -> dict[str, Any]:
        """Retrieves a copy of the latest ticker data."""
        with self._ticker_lock:
            return self.latest_ticker.copy()

    def get_private_updates(self) -> list[dict]:
        """Retrieves all accumulated private updates from the queue."""
        updates = []
        with self._private_updates_lock:
            while not self.private_updates_queue.empty():
                updates.append(self.private_updates_queue.get())
        return updates

    def wait_for_initial_data(self, timeout: int = 30):
        """Waits for initial WebSocket data (klines, orderbook, private) to be received."""
        self.logger.info(
            f"{NEON_BLUE}Waiting for initial WebSocket data... (Timeout: {timeout}s){RESET}",
        )

        kline_ready = self.initial_kline_received.wait(timeout)
        orderbook_ready = self.initial_orderbook_received.wait(timeout)
        private_ready = self.initial_private_data_received.wait(timeout)

        if not kline_ready:
            self.logger.warning(
                f"{NEON_YELLOW}Initial KLINE data not received within {timeout}s. Continuing without full WS data.{RESET}",
            )
        if not orderbook_ready:
            self.logger.warning(
                f"{NEON_YELLOW}Initial ORDERBOOK data not received within {timeout}s. Continuing without full WS data.{RESET}",
            )
        if not private_ready:
            self.logger.warning(
                f"{NEON_YELLOW}Initial PRIVATE data not received within {timeout}s. Position Manager might rely on REST for first sync.{RESET}",
            )

        if kline_ready and orderbook_ready:
            self.logger.info(
                f"{NEON_GREEN}Initial public WebSocket data received.{RESET}",
            )
        if private_ready:
            self.logger.info(
                f"{NEON_GREEN}Initial private WebSocket data received.{RESET}",
            )


# --- Trading Analysis (Upgraded with Ehlers SuperTrend and more) ---
class TradingAnalyzer:
    """Analyzes trading data and generates signals with MTF, Ehlers SuperTrend, and other new indicators."""

    def __init__(
        self,
        df: pd.DataFrame,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
    ):
        """Initializes the TradingAnalyzer."""
        self.df = df.copy()
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.indicator_values: dict[str, float | str | Decimal] = {}
        self.fib_levels: dict[str, Decimal] = {}
        self.weights = config.get(
            "active_weights",
            {},
        )  # NEW: Load active weights from the 'active_weights' key
        self.indicator_settings = config["indicator_settings"]
        self._last_signal_ts = 0  # Initialize last signal timestamp
        self._last_signal_score = 0.0  # Initialize last signal score

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.{RESET}",
            )
            return

        self._calculate_all_indicators()
        if self.config["indicators"].get("fibonacci_levels", False):
            self.calculate_fibonacci_levels()

    def _safe_calculate(
        self,
        func: callable,
        name: str,
        min_data_points: int = 0,
        *args,
        **kwargs,
    ) -> Any | None:
        """Safely calculate indicators and log errors, with min_data_points check."""
        if len(self.df) < min_data_points:
            self.logger.debug(
                f"[{self.symbol}] Skipping indicator '{name}': Not enough data. Need {min_data_points}, have {len(self.df)}.",
            )
            return None
        try:
            result = func(*args, **kwargs)
            if (
                result is None
                or (isinstance(result, pd.Series) and result.empty)
                or (
                    isinstance(result, tuple)
                    and all(
                        r is None or (isinstance(r, pd.Series) and r.empty)
                        for r in result
                    )
                )
            ):
                self.logger.warning(
                    f"{NEON_YELLOW}[{self.symbol}] Indicator '{name}' returned empty or None after calculation. Not enough valid data?{RESET}",
                )
                return None
            return result
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Error calculating indicator '{name}': {e}{RESET}",
            )
            return None

    def _calculate_all_indicators(self) -> None:
        """Calculate all enabled technical indicators, including Ehlers SuperTrend."""
        self.logger.debug(f"[{self.symbol}] Calculating technical indicators...")
        cfg = self.config
        isd = self.indicator_settings

        # SMA
        if cfg["indicators"].get("sma_10", False):
            self.df["SMA_10"] = self._safe_calculate(
                lambda: self.df["close"].rolling(window=isd["sma_short_period"]).mean(),
                "SMA_10",
                min_data_points=isd["sma_short_period"],
            )
            if self.df["SMA_10"] is not None:
                self.indicator_values["SMA_10"] = self.df["SMA_10"].iloc[-1]
        if cfg["indicators"].get("sma_trend_filter", False):
            self.df["SMA_Long"] = self._safe_calculate(
                lambda: self.df["close"].rolling(window=isd["sma_long_period"]).mean(),
                "SMA_Long",
                min_data_points=isd["sma_long_period"],
            )
            if self.df["SMA_Long"] is not None:
                self.indicator_values["SMA_Long"] = self.df["SMA_Long"].iloc[-1]

        # EMA
        if cfg["indicators"].get("ema_alignment", False):
            self.df["EMA_Short"] = self._safe_calculate(
                lambda: self.df["close"]
                .ewm(span=isd["ema_short_period"], adjust=False)
                .mean(),
                "EMA_Short",
                min_data_points=isd["ema_short_period"],
            )
            self.df["EMA_Long"] = self._safe_calculate(
                lambda: self.df["close"]
                .ewm(span=isd["ema_long_period"], adjust=False)
                .mean(),
                "EMA_Long",
                min_data_points=isd["ema_long_period"],
            )
            if self.df["EMA_Short"] is not None:
                self.indicator_values["EMA_Short"] = self.df["EMA_Short"].iloc[-1]
            if self.df["EMA_Long"] is not None:
                self.indicator_values["EMA_Long"] = self.df["EMA_Long"].iloc[-1]

        # ATR
        self.df["TR"] = self._safe_calculate(
            self.calculate_true_range,
            "TR",
            min_data_points=MIN_DATA_POINTS_TR,
        )
        self.df["ATR"] = self._safe_calculate(
            lambda: self.df["TR"].ewm(span=isd["atr_period"], adjust=False).mean(),
            "ATR",
            min_data_points=isd["atr_period"],
        )
        if self.df["ATR"] is not None:
            self.indicator_values["ATR"] = self.df["ATR"].iloc[-1]

        # RSI
        if cfg["indicators"].get("rsi", False):
            self.df["RSI"] = self._safe_calculate(
                self.calculate_rsi,
                "RSI",
                min_data_points=isd["rsi_period"] + 1,
                period=isd["rsi_period"],
            )
            if self.df["RSI"] is not None:
                self.indicator_values["RSI"] = self.df["RSI"].iloc[-1]

        # Stochastic RSI
        if cfg["indicators"].get("stoch_rsi", False):
            stoch_rsi_k, stoch_rsi_d = self._safe_calculate(
                self.calculate_stoch_rsi,
                "StochRSI",
                min_data_points=isd["stoch_rsi_period"]
                + isd["stoch_d_period"]
                + isd["stoch_k_period"],
                period=isd["stoch_rsi_period"],
                k_period=isd["stoch_k_period"],
                d_period=isd["stoch_d_period"],
            )
            if stoch_rsi_k is not None:
                self.df["StochRSI_K"] = stoch_rsi_k
            if stoch_rsi_d is not None:
                self.df["StochRSI_D"] = stoch_rsi_d
            if stoch_rsi_k is not None:
                self.indicator_values["StochRSI_K"] = stoch_rsi_k.iloc[-1]
            if stoch_rsi_d is not None:
                self.indicator_values["StochRSI_D"] = stoch_rsi_d.iloc[-1]

        # Bollinger Bands
        if cfg["indicators"].get("bollinger_bands", False):
            bb_upper, bb_middle, bb_lower = self._safe_calculate(
                self.calculate_bollinger_bands,
                "BollingerBands",
                min_data_points=isd["bollinger_bands_period"],
                period=isd["bollinger_bands_period"],
                std_dev=isd["bollinger_bands_std_dev"],
            )
            if bb_upper is not None:
                self.df["BB_Upper"] = bb_upper
            if bb_middle is not None:
                self.df["BB_Middle"] = bb_middle
            if bb_lower is not None:
                self.df["BB_Lower"] = bb_lower
            if bb_upper is not None:
                self.indicator_values["BB_Upper"] = bb_upper.iloc[-1]
            if bb_middle is not None:
                self.indicator_values["BB_Middle"] = bb_middle.iloc[-1]
            if bb_lower is not None:
                self.indicator_values["BB_Lower"] = bb_lower.iloc[-1]

        # CCI
        if cfg["indicators"].get("cci", False):
            self.df["CCI"] = self._safe_calculate(
                self.calculate_cci,
                "CCI",
                min_data_points=isd["cci_period"],
                period=isd["cci_period"],
            )
            if self.df["CCI"] is not None:
                self.indicator_values["CCI"] = self.df["CCI"].iloc[-1]

        # Williams %R
        if cfg["indicators"].get("wr", False):
            self.df["WR"] = self._safe_calculate(
                self.calculate_williams_r,
                "WR",
                min_data_points=isd["williams_r_period"],
                period=isd["williams_r_period"],
            )
            if self.df["WR"] is not None:
                self.indicator_values["WR"] = self.df["WR"].iloc[-1]

        # MFI
        if cfg["indicators"].get("mfi", False):
            self.df["MFI"] = self._safe_calculate(
                self.calculate_mfi,
                "MFI",
                min_data_points=isd["mfi_period"] + 1,
                period=isd["mfi_period"],
            )
            if self.df["MFI"] is not None:
                self.indicator_values["MFI"] = self.df["MFI"].iloc[-1]

        # OBV
        if cfg["indicators"].get("obv", False):
            obv_val, obv_ema = self._safe_calculate(
                self.calculate_obv,
                "OBV",
                min_data_points=isd["obv_ema_period"],
                ema_period=isd["obv_ema_period"],
            )
            if obv_val is not None:
                self.df["OBV"] = obv_val
            if obv_ema is not None:
                self.df["OBV_EMA"] = obv_ema
            if obv_val is not None:
                self.indicator_values["OBV"] = obv_val.iloc[-1]
            if obv_ema is not None:
                self.indicator_values["OBV_EMA"] = obv_ema.iloc[-1]

        # CMF
        if cfg["indicators"].get("cmf", False):
            cmf_val = self._safe_calculate(
                self.calculate_cmf,
                "CMF",
                min_data_points=isd["cmf_period"],
                period=isd["cmf_period"],
            )
            if cmf_val is not None:
                self.df["CMF"] = cmf_val
            if cmf_val is not None:
                self.indicator_values["CMF"] = cmf_val.iloc[-1]

        # Ichimoku Cloud
        if cfg["indicators"].get("ichimoku_cloud", False):
            (
                tenkan_sen,
                kijun_sen,
                senkou_span_a,
                senkou_span_b,
                chikou_span,
            ) = self._safe_calculate(
                self.calculate_ichimoku_cloud,
                "IchimokuCloud",
                min_data_points=max(
                    isd["ichimoku_tenkan_period"],
                    isd["ichimoku_kijun_period"],
                    isd["ichimoku_senkou_span_b_period"],
                )
                + isd["ichimoku_chikou_span_offset"],
                tenkan_period=isd["ichimoku_tenkan_period"],
                kijun_period=isd["ichimoku_kijun_period"],
                senkou_span_b_period=isd["ichimoku_senkou_span_b_period"],
                chikou_span_offset=isd["ichimoku_chikou_span_offset"],
            )
            if tenkan_sen is not None:
                self.df["Tenkan_Sen"] = tenkan_sen
            if kijun_sen is not None:
                self.df["Kijun_Sen"] = kijun_sen
            if senkou_span_a is not None:
                self.df["Senkou_Span_A"] = senkou_span_a
            if senkou_span_b is not None:
                self.df["Senkou_Span_B"] = senkou_span_b
            if chikou_span is not None:
                self.df["Chikou_Span"] = chikou_span

            if tenkan_sen is not None:
                self.indicator_values["Tenkan_Sen"] = tenkan_sen.iloc[-1]
            if kijun_sen is not None:
                self.indicator_values["Kijun_Sen"] = kijun_sen.iloc[-1]
            if senkou_span_a is not None:
                self.indicator_values["Senkou_Span_A"] = senkou_span_a.iloc[-1]
            if senkou_span_b is not None:
                self.indicator_values["Senkou_Span_B"] = senkou_span_b.iloc[-1]
            if chikou_span is not None:
                self.indicator_values["Chikou_Span"] = chikou_span.fillna(0).iloc[-1]

        # PSAR
        if cfg["indicators"].get("psar", False):
            psar_val, psar_dir = self._safe_calculate(
                self.calculate_psar,
                "PSAR",
                min_data_points=MIN_DATA_POINTS_PSAR,
                acceleration=isd["psar_acceleration"],
                max_acceleration=isd["psar_max_acceleration"],
            )
            if psar_val is not None:
                self.df["PSAR_Val"] = psar_val
            if psar_dir is not None:
                self.df["PSAR_Dir"] = psar_dir
            if psar_val is not None:
                self.indicator_values["PSAR_Val"] = psar_val.iloc[-1]
            if psar_dir is not None:
                self.indicator_values["PSAR_Dir"] = psar_dir.iloc[-1]

        # VWAP (requires volume and turnover, which are in df)
        if cfg["indicators"].get("vwap", False):
            self.df["VWAP"] = self._safe_calculate(
                self.calculate_vwap,
                "VWAP",
                min_data_points=1,
            )
            if self.df["VWAP"] is not None:
                self.indicator_values["VWAP"] = self.df["VWAP"].iloc[-1]

        # --- Ehlers SuperTrend Calculation ---
        if cfg["indicators"].get("ehlers_supertrend", False):
            st_fast_result = self._safe_calculate(
                self.calculate_ehlers_supertrend,
                "EhlersSuperTrendFast",
                min_data_points=isd["ehlers_fast_period"]
                * 3,  # Heuristic for sufficient data
                period=isd["ehlers_fast_period"],
                multiplier=isd["ehlers_fast_multiplier"],
            )
            if st_fast_result is not None and not st_fast_result.empty:
                self.df["st_fast_dir"] = st_fast_result["direction"]
                self.df["st_fast_val"] = st_fast_result["supertrend"]
                self.indicator_values["ST_Fast_Dir"] = st_fast_result["direction"].iloc[
                    -1
                ]
                self.indicator_values["ST_Fast_Val"] = st_fast_result[
                    "supertrend"
                ].iloc[-1]

            st_slow_result = self._safe_calculate(
                self.calculate_ehlers_supertrend,
                "EhlersSuperTrendSlow",
                min_data_points=isd["ehlers_slow_period"]
                * 3,  # Heuristic for sufficient data
                period=isd["ehlers_slow_period"],
                multiplier=isd["ehlers_slow_multiplier"],
            )
            if st_slow_result is not None and not st_slow_result.empty:
                self.df["st_slow_dir"] = st_slow_result["direction"]
                self.df["st_slow_val"] = st_slow_result["supertrend"]
                self.indicator_values["ST_Slow_Dir"] = st_slow_result["direction"].iloc[
                    -1
                ]
                self.indicator_values["ST_Slow_Val"] = st_slow_result[
                    "supertrend"
                ].iloc[-1]

        # MACD
        if cfg["indicators"].get("macd", False):
            macd_line, signal_line, histogram = self._safe_calculate(
                self.calculate_macd,
                "MACD",
                min_data_points=isd["macd_slow_period"] + isd["macd_signal_period"],
                fast_period=isd["macd_fast_period"],
                slow_period=isd["macd_slow_period"],
                signal_period=isd["macd_signal_period"],
            )
            if macd_line is not None:
                self.df["MACD_Line"] = macd_line
            if signal_line is not None:
                self.df["MACD_Signal"] = signal_line
            if histogram is not None:
                self.df["MACD_Hist"] = histogram
            if macd_line is not None:
                self.indicator_values["MACD_Line"] = macd_line.iloc[-1]
            if signal_line is not None:
                self.indicator_values["MACD_Signal"] = signal_line.iloc[-1]
            if histogram is not None:
                self.indicator_values["MACD_Hist"] = histogram.iloc[-1]

        # ADX
        if cfg["indicators"].get("adx", False):
            adx_val, plus_di, minus_di = self._safe_calculate(
                self.calculate_adx,
                "ADX",
                min_data_points=isd["adx_period"]
                * 2,  # ADX requires at least 2*period for smoothing
                period=isd["adx_period"],
            )
            if adx_val is not None:
                self.df["ADX"] = adx_val
            if plus_di is not None:
                self.df["PlusDI"] = plus_di
            if minus_di is not None:
                self.df["MinusDI"] = minus_di
            if adx_val is not None:
                self.indicator_values["ADX"] = adx_val.iloc[-1]
            if plus_di is not None:
                self.indicator_values["PlusDI"] = plus_di.iloc[-1]
            if minus_di is not None:
                self.indicator_values["MinusDI"] = minus_di.iloc[-1]

        # --- New Indicators ---
        # Volatility Index
        if cfg["indicators"].get("volatility_index", False) or cfg[
            "indicator_settings"
        ].get(
            "enable_volatility_filter",
            False,
        ):  # Also calculate if volatility filter is enabled for UPGRADE 2
            self.df["Volatility_Index"] = self._safe_calculate(
                self.calculate_volatility_index,
                "Volatility_Index",
                min_data_points=isd["volatility_index_period"],
                period=isd["volatility_index_period"],
            )
            if self.df["Volatility_Index"] is not None:
                self.indicator_values["Volatility_Index"] = self.df[
                    "Volatility_Index"
                ].iloc[-1]

        # VWMA
        if cfg["indicators"].get("vwma", False):
            self.df["VWMA"] = self._safe_calculate(
                self.calculate_vwma,
                "VWMA",
                min_data_points=isd["vwma_period"],
                period=isd["vwma_period"],
            )
            if self.df["VWMA"] is not None:
                self.indicator_values["VWMA"] = self.df["VWMA"].iloc[-1]

        # Volume Delta
        if cfg["indicators"].get("volume_delta", False):
            self.df["Volume_Delta"] = self._safe_calculate(
                self.calculate_volume_delta,
                "Volume_Delta",
                min_data_points=isd["volume_delta_period"],
                period=isd["volume_delta_period"],
            )
            if self.df["Volume_Delta"] is not None:
                self.indicator_values["Volume_Delta"] = self.df["Volume_Delta"].iloc[-1]

        # UPGRADE 2: Average Volume for Trade Confirmation
        if cfg["indicator_settings"].get("enable_volume_confirmation", False):
            self.df["Avg_Volume"] = self._safe_calculate(
                lambda: self.df["volume"]
                .rolling(window=isd["volume_confirmation_period"])
                .mean(),
                "Avg_Volume",
                min_data_points=isd["volume_confirmation_period"],
            )
            if self.df["Avg_Volume"] is not None:
                self.indicator_values["Avg_Volume"] = self.df["Avg_Volume"].iloc[-1]

        # Final dropna after all indicators are calculated
        initial_len = len(self.df)
        self.df.dropna(subset=["close"], inplace=True)  # Ensure close price is valid
        # Fill remaining NaNs in indicator columns with 0 or a sensible default if appropriate.
        # For signal generation, NaNs might be better handled as 'no signal contribution'.
        # However, for simplicity in this refactor, we'll fill with 0 for now, and scoring methods handle NaNs.
        self.df.fillna(0, inplace=True)

        if len(self.df) < initial_len:
            self.logger.debug(
                f"[{self.symbol}] Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations.",
            )

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty after calculating all indicators and dropping NaNs.{RESET}",
            )
        else:
            self.logger.debug(
                f"[{self.symbol}] Indicators calculated. Final DataFrame size: {len(self.df)}",
            )

    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TR:
            return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(
            axis=1,
        )

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER:
            return pd.Series(np.nan, index=series.index)

        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER:
            return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1:
            filt.iloc[0] = series.iloc[0]
        if len(series) >= 2:
            filt.iloc[1] = (series.iloc[0] + series.iloc[1]) / 2

        for i in range(2, len(series)):
            filt.iloc[i] = (
                (c1 / 2) * (series.iloc[i] + series.iloc[i - 1])
                + c2 * filt.iloc[i - 1]
                - c3 * filt.iloc[i - 2]
            )
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(
        self,
        period: int,
        multiplier: float,
    ) -> pd.DataFrame | None:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        # Ensure enough data points for calculation
        min_bars_required = period * 3  # A common heuristic
        if len(self.df) < min_bars_required:
            self.logger.debug(
                f"[{self.symbol}] Not enough data for Ehlers SuperTrend (period={period}). Need at least {min_bars_required} bars.",
            )
            return None

        df_copy = self.df.copy()

        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)

        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr

        if df_copy.empty:
            self.logger.debug(
                f"[{self.symbol}] Ehlers SuperTrend: DataFrame empty after smoothing. Returning None.",
            )
            return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        # Find the first valid index after smoothing
        first_valid_idx_val = smoothed_price.first_valid_index()
        if first_valid_idx_val is None:
            return None
        first_valid_idx = df_copy.index.get_loc(first_valid_idx_val)
        if first_valid_idx >= len(df_copy):
            return None

        # Initialize the first valid supertrend value based on the first valid close price relative to bands
        if df_copy["close"].iloc[first_valid_idx] > upper_band.iloc[first_valid_idx]:
            direction.iloc[first_valid_idx] = 1
            supertrend.iloc[first_valid_idx] = lower_band.iloc[first_valid_idx]
        elif df_copy["close"].iloc[first_valid_idx] < lower_band.iloc[first_valid_idx]:
            direction.iloc[first_valid_idx] = -1
            supertrend.iloc[first_valid_idx] = upper_band.iloc[first_valid_idx]
        else:  # Price is within bands, initialize with lower band, neutral direction
            direction.iloc[first_valid_idx] = 0
            supertrend.iloc[first_valid_idx] = lower_band.iloc[first_valid_idx]

        for i in range(first_valid_idx + 1, len(df_copy)):
            prev_direction = direction.iloc[i - 1]
            prev_supertrend = supertrend.iloc[i - 1]
            curr_close = df_copy["close"].iloc[i]

            if prev_direction == 1:  # Previous was an UP trend
                # If current close drops below the prev_supertrend, flip to DOWN
                if curr_close < prev_supertrend:
                    direction.iloc[i] = -1
                    supertrend.iloc[i] = upper_band.iloc[i]  # New ST is upper band
                else:  # Continue UP trend
                    direction.iloc[i] = 1
                    # New ST is max of current lower_band and prev_supertrend
                    supertrend.iloc[i] = max(lower_band.iloc[i], prev_supertrend)
            elif prev_direction == -1:  # Previous was a DOWN trend
                # If current close rises above the prev_supertrend, flip to UP
                if curr_close > prev_supertrend:
                    direction.iloc[i] = 1
                    supertrend.iloc[i] = lower_band.iloc[i]  # New ST is lower band
                else:  # Continue DOWN trend
                    direction.iloc[i] = -1
                    # New ST is min of current upper_band and prev_supertrend
                    supertrend.iloc[i] = min(upper_band.iloc[i], prev_supertrend)
            elif curr_close > upper_band.iloc[i]:
                direction.iloc[i] = 1
                supertrend.iloc[i] = lower_band.iloc[i]
            elif curr_close < lower_band.iloc[i]:
                direction.iloc[i] = -1
                supertrend.iloc[i] = upper_band.iloc[i]
            else:  # Still within bands or undecided, stick to previous or default
                direction.iloc[i] = prev_direction  # Maintain previous direction
                supertrend.iloc[i] = prev_supertrend  # Maintain previous supertrend

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(
        self,
        fast_period: int,
        slow_period: int,
        signal_period: int,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        # Handle division by zero for rs where avg_loss is 0
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(
        self,
        period: int,
        k_period: int,
        d_period: int,
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index), pd.Series(
                np.nan,
                index=self.df.index,
            )
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        # Avoid division by zero if highest_rsi == lowest_rsi
        denominator = highest_rsi - lowest_rsi
        denominator[denominator == 0] = np.nan  # Replace 0 with NaN for division
        stoch_rsi_k_raw = ((rsi - lowest_rsi) / denominator) * 100
        stoch_rsi_k_raw = stoch_rsi_k_raw.fillna(0).clip(
            0,
            100,
        )  # Clip to [0, 100] and fill remaining NaNs with 0

        stoch_rsi_k = (
            stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period)
            .mean()
            .fillna(0)
        )
        stoch_rsi_d = (
            stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean().fillna(0)
        )

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        # True Range
        tr = self.calculate_true_range()

        # Directional Movement
        plus_dm = self.df["high"].diff()
        minus_dm = -self.df["low"].diff()

        plus_dm_final = pd.Series(0.0, index=self.df.index)
        minus_dm_final = pd.Series(0.0, index=self.df.index)

        # Apply +DM and -DM logic
        for i in range(1, len(self.df)):
            if plus_dm.iloc[i] > minus_dm.iloc[i] and plus_dm.iloc[i] > 0:
                plus_dm_final.iloc[i] = plus_dm.iloc[i]
            if minus_dm.iloc[i] > plus_dm.iloc[i] and minus_dm.iloc[i] > 0:
                minus_dm_final.iloc[i] = minus_dm.iloc[i]

        # Smoothed True Range, +DM, -DM
        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (
            plus_dm_final.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan)
        ) * 100
        minus_di = (
            minus_dm_final.ewm(span=period, adjust=False).mean()
            / atr.replace(0, np.nan)
        ) * 100

        # DX
        di_diff = abs(plus_di - minus_di)
        di_sum = plus_di + minus_di
        # Handle division by zero
        dx = (di_diff / di_sum.replace(0, np.nan)).fillna(0) * 100

        # ADX
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(
        self,
        period: int,
        std_dev: float,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period:
            return (
                pd.Series(np.nan, index=self.df.index),
                pd.Series(np.nan, index=self.df.index),
                pd.Series(np.nan, index=self.df.index),
            )
        middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
        std = self.df["close"].rolling(window=period, min_periods=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band

    def calculate_vwap(self) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty:
            return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        # Ensure cumulative sum starts from valid data, reindex to original df index
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol.replace(
            0,
            np.nan,
        )  # Handle division by zero
        return vwap.reindex(self.df.index)

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        mad = tp.rolling(window=period, min_periods=period).apply(
            lambda x: np.abs(x - x.mean()).mean(),
            raw=False,
        )
        # Handle potential division by zero for mad
        cci = (tp - sma_tp) / (Decimal("0.015") * mad.replace(0, np.nan))
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
        # Handle division by zero
        denominator = highest_high - lowest_low
        wr = -100 * ((highest_high - self.df["close"]) / denominator.replace(0, np.nan))
        return wr

    def calculate_ichimoku_cloud(
        self,
        tenkan_period: int,
        kijun_period: int,
        senkou_span_b_period: int,
        chikou_span_offset: int,
    ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        # Ensure enough data points for all components and the shift
        required_len = (
            max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset
        )
        if len(self.df) < required_len:
            self.logger.debug(
                f"[{self.symbol}] Not enough data for Ichimoku Cloud. Need {required_len}, have {len(self.df)}.",
            )
            return (
                pd.Series(np.nan),
                pd.Series(np.nan),
                pd.Series(np.nan),
                pd.Series(np.nan),
                pd.Series(np.nan),
            )

        tenkan_sen = (
            self.df["high"].rolling(window=tenkan_period).max()
            + self.df["low"].rolling(window=tenkan_period).min()
        ) / 2

        kijun_sen = (
            self.df["high"].rolling(window=kijun_period).max()
            + self.df["low"].rolling(window=kijun_period).min()
        ) / 2

        # Senkou Span A is calculated based on Tenkan and Kijun, then shifted forward
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)

        # Senkou Span B is calculated based on highest high and lowest low over its period, then shifted forward
        senkou_span_b = (
            (
                self.df["high"].rolling(window=senkou_span_b_period).max()
                + self.df["low"].rolling(window=senkou_span_b_period).min()
            )
            / 2
        ).shift(kijun_period)

        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        money_flow = typical_price * self.df["volume"]

        positive_flow = pd.Series(0.0, index=self.df.index)
        negative_flow = pd.Series(0.0, index=self.df.index)

        # Calculate positive and negative money flow
        price_diff = typical_price.diff()
        positive_flow = money_flow.where(price_diff > 0, 0)
        negative_flow = money_flow.where(price_diff < 0, 0)

        # Rolling sum for period
        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        # Avoid division by zero
        mf_ratio = positive_mf_sum / negative_mf_sum.replace(0, np.nan)
        mfi = 100 - (100 / (1 + mf_ratio))
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV:
            return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        # Calculate OBV direction change and cumulative sum
        obv_direction = np.sign(self.df["close"].diff().fillna(0))
        obv = (obv_direction * self.df["volume"]).cumsum()

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()

        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period:
            return pd.Series(np.nan)

        # Money Flow Multiplier (MFM)
        high_low_range = self.df["high"] - self.df["low"]
        # Handle division by zero for high_low_range
        mfm = (
            (self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])
        ) / high_low_range.replace(0, np.nan)
        mfm = mfm.fillna(0)

        # Money Flow Volume (MFV)
        mfv = mfm * self.df["volume"]

        # CMF
        volume_sum = self.df["volume"].rolling(window=period).sum()
        # Handle division by zero for volume_sum
        cmf = mfv.rolling(window=period).sum() / volume_sum.replace(0, np.nan)
        cmf = cmf.fillna(0)

        return cmf

    def calculate_psar(
        self,
        acceleration: float,
        max_acceleration: float,
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR:
            return pd.Series(np.nan, index=self.df.index), pd.Series(
                np.nan,
                index=self.df.index,
            )

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        # Initialize EP based on the direction of the first two bars
        ep = (
            self.df["low"].iloc[0]
            if len(self.df) > 1 and self.df["close"].iloc[0] < self.df["close"].iloc[1]
            else self.df["high"].iloc[0]
        )

        for i in range(1, len(self.df)):
            prev_bull = bull.iloc[i - 1]
            prev_psar = psar.iloc[i - 1]

            # Calculate current PSAR value
            if prev_bull:  # Bullish trend
                psar.iloc[i] = prev_psar + af * (ep - prev_psar)
            else:  # Bearish trend
                psar.iloc[i] = prev_psar - af * (prev_psar - ep)

            # Check for reversal conditions
            reverse = False
            if prev_bull and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False  # Reverse to bearish
                reverse = True
            elif not prev_bull and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True  # Reverse to bullish
                reverse = True
            else:
                bull.iloc[i] = prev_bull  # Continue previous trend

            # Update AF and EP
            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
                # Ensure PSAR does not cross price on reversal
                if bull.iloc[
                    i
                ]:  # if reversing to bullish, PSAR should be below current low
                    psar.iloc[i] = min(
                        self.df["low"].iloc[i],
                        self.df["low"].iloc[i - 1],
                    )
                else:  # if reversing to bearish, PSAR should be above current high
                    psar.iloc[i] = max(
                        self.df["high"].iloc[i],
                        self.df["high"].iloc[i - 1],
                    )

            elif bull.iloc[i]:  # Continuing bullish
                if self.df["high"].iloc[i] > ep:
                    ep = self.df["high"].iloc[i]
                    af = min(af + acceleration, max_acceleration)
                # Keep PSAR below the lowest low of the last two bars
                psar.iloc[i] = min(
                    psar.iloc[i],
                    self.df["low"].iloc[i],
                    self.df["low"].iloc[i - 1],
                )
            else:  # Continuing bearish
                if self.df["low"].iloc[i] < ep:
                    ep = self.df["low"].iloc[i]
                    af = min(af + acceleration, max_acceleration)
                # Keep PSAR above the highest high of the last two bars
                psar.iloc[i] = max(
                    psar.iloc[i],
                    self.df["high"].iloc[i],
                    self.df["high"].iloc[i - 1],
                )

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1  # Bullish
        direction[psar > self.df["close"]] = -1  # Bearish

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Not enough data for Fibonacci levels (need {window} bars).{RESET}",
            )
            return

        # Use the last 'window' number of bars for calculation
        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()

        diff = recent_high - recent_low

        if diff <= 0:  # Handle cases where high and low are the same or inverted
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Invalid high-low range for Fibonacci calculation. Diff: {diff}{RESET}",
            )
            return

        # Use Decimal for precision
        diff_dec = Decimal(str(diff))
        recent_high_dec = Decimal(str(recent_high))

        # Define Fibonacci ratios
        fib_ratios = {
            "0.0%": Decimal("0.0"),
            "23.6%": Decimal("0.236"),
            "38.2%": Decimal("0.382"),
            "50.0%": Decimal("0.500"),
            "61.8%": Decimal("0.618"),
            "78.6%": Decimal("0.786"),
            "100.0%": Decimal("1.0"),
        }

        self.fib_levels = {}
        # Define precision for quantization, e.g., 5 decimal places for crypto
        price_precision_exponent = max(
            0,
            self.config["trade_management"]["price_precision"] - 1,
        )
        quantize_str = "0." + "0" * price_precision_exponent + "1"
        quantize_dec = Decimal(quantize_str)

        for level_name, ratio in fib_ratios.items():
            level_price = recent_high_dec - (diff_dec * ratio)
            self.fib_levels[level_name] = level_price.quantize(
                quantize_dec,
                rounding=ROUND_DOWN,
            )

        self.logger.debug(
            f"[{self.symbol}] Calculated Fibonacci levels: {self.fib_levels}",
        )

    def calculate_volatility_index(self, period: int) -> pd.Series:
        """Calculate a simple Volatility Index based on ATR normalized by price."""
        if (
            len(self.df) < period
            or "ATR" not in self.df.columns
            or self.df["ATR"].isnull().all()
        ):
            self.logger.debug(
                f"[{self.symbol}] Not enough data or ATR missing for Volatility Index.",
            )
            return pd.Series(np.nan, index=self.df.index)

        # ATR is already calculated in _calculate_all_indicators
        # Normalize ATR by closing price to get a relative measure of volatility
        normalized_atr = self.df["ATR"] / self.df["close"].replace(0, np.nan)
        # Calculate a moving average of the normalized ATR
        volatility_index = normalized_atr.rolling(window=period).mean()
        return volatility_index

    def calculate_vwma(self, period: int) -> pd.Series:
        """Calculate Volume Weighted Moving Average (VWMA)."""
        if len(self.df) < period or self.df["volume"].isnull().any():
            return pd.Series(np.nan, index=self.df.index)

        # Ensure volume is numeric and not zero for calculation
        valid_volume = self.df["volume"].replace(0, np.nan)
        pv = self.df["close"] * valid_volume  # Price * Volume
        # Sum of (Price * Volume) over the period
        sum_pv = pv.rolling(window=period).sum()
        # Sum of Volume over the period
        sum_vol = valid_volume.rolling(window=period).sum()
        vwma = sum_pv / sum_vol.replace(0, np.nan)  # Handle division by zero
        return vwma

    def calculate_volume_delta(self, period: int) -> pd.Series:
        """Calculate Volume Delta, indicating buying vs selling pressure."""
        if len(self.df) < MIN_DATA_POINTS_VOLATILITY:
            return pd.Series(np.nan, index=self.df.index)

        # Approximate buy/sell volume based on close relative to open
        # If close > open, it's considered buying pressure (bullish candle)
        buy_volume = self.df["volume"].where(self.df["close"] > self.df["open"], 0)
        # If close < open, it's considered selling pressure (bearish candle)
        sell_volume = self.df["volume"].where(self.df["close"] < self.df["open"], 0)

        # Rolling sum of buy/sell volume over the specified period
        buy_volume_sum = buy_volume.rolling(window=period, min_periods=1).sum()
        sell_volume_sum = sell_volume.rolling(window=period, min_periods=1).sum()

        total_volume_sum = buy_volume_sum + sell_volume_sum
        # Calculate delta: (Buy Volume - Sell Volume) / Total Volume
        # This gives a ratio indicating net buying or selling pressure
        volume_delta = (buy_volume_sum - sell_volume_sum) / total_volume_sum.replace(
            0,
            np.nan,
        )
        return volume_delta.fillna(0)

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value from the stored dictionary."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance.
        Returns imbalance score between -1 (all asks) and +1 (all bids).
        """
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b[1]) for b in bids)
        ask_volume = sum(Decimal(a[1]) for a in asks)

        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return 0.0

        # Imbalance: (Bid Volume - Ask Volume) / Total Volume
        imbalance = (bid_volume - ask_volume) / total_volume
        self.logger.debug(
            f"[{self.symbol}] Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})",
        )
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty:
            return "UNKNOWN"

        # Ensure we have enough data for the indicator's period
        period = self.config["mtf_analysis"]["trend_period"]
        if len(higher_tf_df) < period:
            self.logger.debug(
                f"[{self.symbol}] MTF Trend ({indicator_type}): Not enough data. Need {period}, have {len(higher_tf_df)}.",
            )
            return "UNKNOWN"

        last_close = Decimal(str(higher_tf_df["close"].iloc[-1]))

        if indicator_type == "sma":
            sma = (
                higher_tf_df["close"]
                .rolling(window=period, min_periods=period)
                .mean()
                .iloc[-1]
            )
            if last_close > sma:
                return "UP"
            if last_close < sma:
                return "DOWN"
            return "SIDEWAYS"
        if indicator_type == "ema":
            ema = (
                higher_tf_df["close"]
                .ewm(span=period, adjust=False, min_periods=period)
                .mean()
                .iloc[-1]
            )
            if last_close > ema:
                return "UP"
            if last_close < ema:
                return "DOWN"
            return "SIDEWAYS"
        if indicator_type == "ehlers_supertrend":
            # This is inefficient as it recalculates the indicator.
            # A better approach would be to pass pre-calculated indicator values or a pre-instantiated analyzer.
            # For now, keeping it as is but noting the inefficiency.
            temp_analyzer = TradingAnalyzer(
                higher_tf_df,
                self.config,
                self.logger,
                self.symbol,
            )
            # Use the slow SuperTrend for MTF trend determination as per common practice
            st_period = self.indicator_settings["ehlers_slow_period"]
            st_multiplier = self.indicator_settings["ehlers_slow_multiplier"]
            # Ensure enough data for ST calculation
            if len(higher_tf_df) < st_period * 3:  # Heuristic for sufficient data
                self.logger.debug(
                    f"[{self.symbol}] MTF Ehlers SuperTrend: Not enough data for ST calculation (period={st_period}).",
                )
                return "UNKNOWN"

            st_result = temp_analyzer.calculate_ehlers_supertrend(
                period=st_period,
                multiplier=st_multiplier,
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1:
                    return "UP"
                if st_dir == -1:
                    return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def _fetch_and_analyze_mtf(
        self,
        ws_manager: Optional["BybitWebSocketManager"] = None,
    ) -> dict[str, str]:
        """Fetches data for higher timeframes and determines trends."""
        mtf_trends: dict[str, str] = {}
        if not self.config["mtf_analysis"]["enabled"]:
            return mtf_trends

        higher_timeframes = self.config["mtf_analysis"]["higher_timeframes"]
        trend_indicators = self.config["mtf_analysis"]["trend_indicators"]
        mtf_request_delay = self.config["mtf_analysis"]["mtf_request_delay_seconds"]

        for htf_interval in higher_timeframes:
            self.logger.debug(
                f"[{self.symbol}] Fetching klines for MTF interval: {htf_interval}",
            )
            # Fetch enough data for the longest indicator period on MTF
            # Fetching a larger number (e.g., 1000) is good practice
            htf_df = fetch_klines(
                self.symbol,
                htf_interval,
                1000,
                self.logger,
                ws_manager=ws_manager,
            )

            if htf_df is not None and not htf_df.empty:
                for trend_ind in trend_indicators:
                    trend = self._get_mtf_trend(htf_df, trend_ind)
                    mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                    self.logger.debug(
                        f"[{self.symbol}] MTF Trend ({htf_interval}, {trend_ind}): {trend}",
                    )
            else:
                self.logger.warning(
                    f"{NEON_YELLOW}[{self.symbol}] Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}",
                )
            time.sleep(mtf_request_delay)  # Delay between MTF requests
        return mtf_trends

    # --- Signal Scoring Helper Methods ---

    def _score_ema_alignment(
        self,
        signal_score: float,
        signal_breakdown: dict,
    ) -> tuple[float, dict]:
        """Scores EMA alignment."""
        if not self.config["indicators"].get("ema_alignment", False):
            return signal_score, signal_breakdown

        ema_short = self._get_indicator_value("EMA_Short")
        ema_long = self._get_indicator_value("EMA_Long")
        weight = self.weights.get("ema_alignment", 0)

        if not pd.isna(ema_short) and not pd.isna(ema_long) and weight > 0:
            contrib = 0.0
            if ema_short > ema_long:
                contrib = weight
            elif ema_short < ema_long:
                contrib = -weight
            signal_score += contrib
            signal_breakdown["EMA_Alignment"] = contrib
        return signal_score, signal_breakdown

    def _score_sma_trend_filter(
        self,
        signal_score: float,
        signal_breakdown: dict,
        current_close: Decimal,
    ) -> tuple[float, dict]:
        """Scores SMA trend filter."""
        if not self.config["indicators"].get("sma_trend_filter", False):
            return signal_score, signal_breakdown

        sma_long = self._get_indicator_value("SMA_Long")
        weight = self.weights.get("sma_trend_filter", 0)

        if not pd.isna(sma_long) and weight > 0:
            contrib = 0.0
            if current_close > sma_long:
                contrib = weight
            elif current_close < sma_long:
                contrib = -weight
            signal_score += contrib
            signal_breakdown["SMA_Trend_Filter"] = contrib
        return signal_score, signal_breakdown

    def _score_momentum(
        self,
        signal_score: float,
        signal_breakdown: dict,
        current_close: Decimal,
        prev_close: Decimal,
    ) -> tuple[float, dict]:
        """Scores momentum indicators (RSI, StochRSI, CCI, WR, MFI)."""
        if not self.config["indicators"].get("momentum", False):
            return signal_score, signal_breakdown

        momentum_weight = self.weights.get("momentum_rsi_stoch_cci_wr_mfi", 0)
        if momentum_weight == 0:
            return signal_score, signal_breakdown

        isd = self.indicator_settings

        # RSI
        if self.config["indicators"].get("rsi", False):
            rsi = self._get_indicator_value("RSI")
            if not pd.isna(rsi):
                # Normalize RSI to a -1 to +1 scale (50 is neutral)
                normalized_rsi = (float(rsi) - 50) / 50
                contrib = (
                    normalized_rsi * momentum_weight * 0.5
                )  # Assign a portion of momentum weight
                signal_score += contrib
                signal_breakdown["RSI_Signal"] = contrib

        # StochRSI Crossover
        if self.config["indicators"].get("stoch_rsi", False):
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            if not pd.isna(stoch_k) and not pd.isna(stoch_d) and len(self.df) > 1:
                prev_stoch_k = self.df["StochRSI_K"].iloc[-2]
                prev_stoch_d = self.df["StochRSI_D"].iloc[-2]
                contrib = 0.0
                # Bullish crossover from oversold
                if (
                    stoch_k > stoch_d
                    and prev_stoch_k <= prev_stoch_d
                    and stoch_k < isd["stoch_rsi_oversold"]
                ):
                    contrib = momentum_weight * 0.6
                    self.logger.debug(
                        f"[{self.symbol}] StochRSI: Bullish crossover from oversold.",
                    )
                # Bearish crossover from overbought
                elif (
                    stoch_k < stoch_d
                    and prev_stoch_k >= prev_stoch_d
                    and stoch_k > isd["stoch_rsi_overbought"]
                ):
                    contrib = -momentum_weight * 0.6
                    self.logger.debug(
                        f"[{self.symbol}] StochRSI: Bearish crossover from overbought.",
                    )
                # General momentum based on K line position relative to D line and midpoint
                elif stoch_k > stoch_d and stoch_k < 50:  # General bullish momentum
                    contrib = momentum_weight * 0.2
                elif stoch_k < stoch_d and stoch_k > 50:  # General bearish momentum
                    contrib = -momentum_weight * 0.2
                signal_score += contrib
                signal_breakdown["StochRSI_Signal"] = contrib

        # CCI
        if self.config["indicators"].get("cci", False):
            cci = self._get_indicator_value("CCI")
            if not pd.isna(cci):
                # Normalize CCI (assuming typical range of -200 to 200, normalize to -1 to +1)
                normalized_cci = float(cci) / 200
                contrib = 0.0
                if cci < isd["cci_oversold"]:
                    contrib = momentum_weight * 0.4
                elif cci > isd["cci_overbought"]:
                    contrib = -momentum_weight * 0.4
                signal_score += contrib
                signal_breakdown["CCI_Signal"] = contrib

        # Williams %R
        if self.config["indicators"].get("wr", False):
            wr = self._get_indicator_value("WR")
            if not pd.isna(wr):
                # Normalize WR to -1 to +1 scale (-100 to 0, so (WR + 50) / 50)
                normalized_wr = (float(wr) + 50) / 50
                contrib = 0.0
                if wr < isd["williams_r_oversold"]:
                    contrib = momentum_weight * 0.4
                elif wr > isd["williams_r_overbought"]:
                    contrib = -momentum_weight * 0.4
                signal_score += contrib
                signal_breakdown["WR_Signal"] = contrib

        # MFI
        if self.config["indicators"].get("mfi", False):
            mfi = self._get_indicator_value("MFI")
            if not pd.isna(mfi):
                # Normalize MFI to -1 to +1 scale (0 to 100, so (MFI - 50) / 50)
                normalized_mfi = (float(mfi) - 50) / 50
                contrib = 0.0
                if mfi < isd["mfi_oversold"]:
                    contrib = momentum_weight * 0.4
                elif mfi > isd["mfi_overbought"]:
                    contrib = -momentum_weight * 0.4
                signal_score += contrib
                signal_breakdown["MFI_Signal"] = contrib

        return signal_score, signal_breakdown

    def _score_bollinger_bands(
        self,
        signal_score: float,
        signal_breakdown: dict,
        current_close: Decimal,
    ) -> tuple[float, dict]:
        """Scores Bollinger Bands."""
        if not self.config["indicators"].get("bollinger_bands", False):
            return signal_score, signal_breakdown

        bb_upper = self._get_indicator_value("BB_Upper")
        bb_lower = self._get_indicator_value("BB_Lower")
        weight = self.weights.get("bollinger_bands", 0)

        if not pd.isna(bb_upper) and not pd.isna(bb_lower) and weight > 0:
            contrib = 0.0
            if (
                current_close < bb_lower
            ):  # Price below lower band - potential buy signal
                contrib = weight * 0.5
            elif (
                current_close > bb_upper
            ):  # Price above upper band - potential sell signal
                contrib = -weight * 0.5
            signal_score += contrib
            signal_breakdown["Bollinger_Bands_Signal"] = contrib
        return signal_score, signal_breakdown

    def _score_vwap(
        self,
        signal_score: float,
        signal_breakdown: dict,
        current_close: Decimal,
        prev_close: Decimal,
    ) -> tuple[float, dict]:
        """Scores VWAP."""
        if not self.config["indicators"].get("vwap", False):
            return signal_score, signal_breakdown

        vwap = self._get_indicator_value("VWAP")
        weight = self.weights.get("vwap", 0)

        if not pd.isna(vwap) and weight > 0:
            contrib = 0.0
            # Basic score based on price relative to VWAP
            if current_close > vwap:
                contrib = weight * 0.2
            elif current_close < vwap:
                contrib = -weight * 0.2

            # Add score for VWAP crossover if available
            if len(self.df) > 1:
                prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                # VWAP crossover
                if current_close > vwap and prev_close <= prev_vwap:
                    contrib += weight * 0.3  # Additional bullish weight on crossover
                    self.logger.debug(
                        f"[{self.symbol}] VWAP: Bullish crossover detected.",
                    )
                elif current_close < vwap and prev_close >= prev_vwap:
                    contrib -= weight * 0.3  # Additional bearish weight on crossover
                    self.logger.debug(
                        f"[{self.symbol}] VWAP: Bearish crossover detected.",
                    )
            signal_score += contrib
            signal_breakdown["VWAP_Signal"] = contrib
        return signal_score, signal_breakdown

    def _score_psar(
        self,
        signal_score: float,
        signal_breakdown: dict,
        current_close: Decimal,
        prev_close: Decimal,
    ) -> tuple[float, dict]:
        """Scores PSAR."""
        if not self.config["indicators"].get("psar", False):
            return signal_score, signal_breakdown

        psar_val = self._get_indicator_value("PSAR_Val")
        psar_dir = self._get_indicator_value("PSAR_Dir")
        weight = self.weights.get("psar", 0)

        if not pd.isna(psar_val) and not pd.isna(psar_dir) and weight > 0:
            contrib = 0.0
            # PSAR direction is a primary signal
            if psar_dir == 1:  # Bullish PSAR
                contrib = weight * 0.5
            elif psar_dir == -1:  # Bearish PSAR
                contrib = -weight * 0.5

            # PSAR crossover with price adds confirmation
            if len(self.df) > 1:
                prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                if current_close > psar_val and prev_close <= prev_psar_val:
                    contrib += weight * 0.4  # Additional bullish weight on crossover
                    self.logger.debug(
                        f"[{self.symbol}] PSAR: Bullish reversal detected.",
                    )
                elif current_close < psar_val and prev_close >= prev_psar_val:
                    contrib -= weight * 0.4  # Additional bearish weight on crossover
                    self.logger.debug(
                        f"[{self.symbol}] PSAR: Bearish reversal detected.",
                    )
            signal_score += contrib
            signal_breakdown["PSAR_Signal"] = contrib
        return signal_score, signal_breakdown

    def _score_orderbook_imbalance(
        self,
        signal_score: float,
        signal_breakdown: dict,
        orderbook_data: dict | None,
    ) -> tuple[float, dict]:
        """Scores orderbook imbalance."""
        if (
            not self.config["indicators"].get("orderbook_imbalance", False)
            or not orderbook_data
        ):
            return signal_score, signal_breakdown

        imbalance = self._check_orderbook(
            Decimal(0),
            orderbook_data,
        )  # Price not used in imbalance calculation here
        weight = self.weights.get("orderbook_imbalance", 0)

        if weight > 0:
            contrib = imbalance * weight
            signal_score += contrib
            signal_breakdown["Orderbook_Imbalance"] = contrib
        return signal_score, signal_breakdown

    def _score_fibonacci_levels(
        self,
        signal_score: float,
        signal_breakdown: dict,
        current_close: Decimal,
        prev_close: Decimal,
    ) -> tuple[float, dict]:
        """Scores Fibonacci levels confluence."""
        if (
            not self.config["indicators"].get("fibonacci_levels", False)
            or not self.fib_levels
        ):
            return signal_score, signal_breakdown

        weight = self.weights.get("fibonacci_levels", 0)
        if weight == 0:
            return signal_score, signal_breakdown

        contrib = 0.0
        for level_name, level_price in self.fib_levels.items():
            # Check if price is near a Fibonacci level (within 0.1% of current price)
            # Ensure current_close is not zero to avoid division by zero
            if (
                current_close != 0
                and level_name not in ["0.0%", "100.0%"]
                and abs(current_close - level_price) / current_close < Decimal("0.001")
            ):
                self.logger.debug(
                    f"[{self.symbol}] Price near Fibonacci level {level_name}: {level_price.normalize()}. Current close: {current_close.normalize()}",
                )
                # Price crossing the level can act as support/resistance
                if len(self.df) > 1:
                    if (
                        current_close > prev_close and current_close > level_price
                    ):  # Bullish breakout above level
                        contrib += weight * 0.1
                    elif (
                        current_close < prev_close and current_close < level_price
                    ):  # Bearish breakdown below level
                        contrib -= weight * 0.1
        signal_score += contrib
        signal_breakdown["Fibonacci_Levels_Signal"] = contrib
        return signal_score, signal_breakdown

    def _score_ehlers_supertrend(
        self,
        signal_score: float,
        signal_breakdown: dict,
    ) -> tuple[float, dict]:
        """Scores Ehlers SuperTrend alignment."""
        if not self.config["indicators"].get("ehlers_supertrend", False):
            return signal_score, signal_breakdown

        st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
        st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
        prev_st_fast_dir = (
            self.df["st_fast_dir"].iloc[-2]
            if "st_fast_dir" in self.df.columns and len(self.df) > 1
            else np.nan
        )
        weight = self.weights.get("ehlers_supertrend_alignment", 0)

        if (
            not pd.isna(st_fast_dir)
            and not pd.isna(st_slow_dir)
            and not pd.isna(prev_st_fast_dir)
            and weight > 0
        ):
            contrib = 0.0
            # Strong buy signal: fast ST flips up and aligns with slow ST (which is also up)
            if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
                contrib = weight
                self.logger.debug(
                    f"[{self.symbol}] Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend).",
                )
            # Strong sell signal: fast ST flips down and aligns with slow ST (which is also down)
            elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
                contrib = -weight
                self.logger.debug(
                    f"[{self.symbol}] Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend).",
                )
            # General alignment: both fast and slow ST are in the same direction
            elif st_slow_dir == 1 and st_fast_dir == 1:
                contrib = weight * 0.3
            elif st_slow_dir == -1 and st_fast_dir == -1:
                contrib = -weight * 0.3
            signal_score += contrib
            signal_breakdown["Ehlers_SuperTrend_Alignment"] = contrib
        return signal_score, signal_breakdown

    def _score_macd(
        self,
        signal_score: float,
        signal_breakdown: dict,
    ) -> tuple[float, dict]:
        """Scores MACD alignment."""
        if not self.config["indicators"].get("macd", False):
            return signal_score, signal_breakdown

        macd_line = self._get_indicator_value("MACD_Line")
        signal_line = self._get_indicator_value("MACD_Signal")
        histogram = self._get_indicator_value("MACD_Hist")
        weight = self.weights.get("macd_alignment", 0)

        if (
            not pd.isna(macd_line)
            and not pd.isna(signal_line)
            and not pd.isna(histogram)
            and len(self.df) > 1
            and weight > 0
        ):
            contrib = 0.0
            # Bullish crossover: MACD line crosses above Signal line
            if (
                macd_line > signal_line
                and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]
            ):
                contrib = weight
                self.logger.debug(
                    f"[{self.symbol}] MACD: BUY signal (MACD line crossed above Signal line).",
                )
            # Bearish crossover: MACD line crosses below Signal line
            elif (
                macd_line < signal_line
                and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]
            ):
                contrib = -weight
                self.logger.debug(
                    f"[{self.symbol}] MACD: SELL signal (MACD line crossed below Signal line).",
                )
            # Histogram turning positive/negative from zero line
            elif histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0:
                contrib = weight * 0.2
            elif histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0:
                contrib = -weight * 0.2
            signal_score += contrib
            signal_breakdown["MACD_Alignment"] = contrib
        return signal_score, signal_breakdown

    def _score_adx(
        self,
        signal_score: float,
        signal_breakdown: dict,
    ) -> tuple[float, dict]:
        """Scores ADX strength."""
        if not self.config["indicators"].get("adx", False):
            return signal_score, signal_breakdown

        adx_val = self._get_indicator_value("ADX")
        plus_di = self._get_indicator_value("PlusDI")
        minus_di = self._get_indicator_value("MinusDI")
        weight = self.weights.get("adx_strength", 0)
        # Retrieve thresholds from indicator_settings for better configuration
        ADX_STRONG_TREND_THRESHOLD = self.indicator_settings.get(
            "ADX_STRONG_TREND_THRESHOLD",
            25,
        )
        ADX_WEAK_TREND_THRESHOLD = self.indicator_settings.get(
            "ADX_WEAK_TREND_THRESHOLD",
            20,
        )

        if (
            not pd.isna(adx_val)
            and not pd.isna(plus_di)
            and not pd.isna(minus_di)
            and weight > 0
        ):
            contrib = 0.0
            # Strong trend confirmation
            if adx_val > ADX_STRONG_TREND_THRESHOLD:
                if plus_di > minus_di:  # Bullish trend
                    contrib = weight
                    self.logger.debug(
                        f"[{self.symbol}] ADX: Strong BUY trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, +DI > -DI).",
                    )
                elif minus_di > plus_di:  # Bearish trend
                    contrib = -weight
                    self.logger.debug(
                        f"[{self.symbol}] ADX: Strong SELL trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, -DI > +DI).",
                    )
            elif adx_val < ADX_WEAK_TREND_THRESHOLD:
                contrib = 0  # Neutral signal, no contribution from ADX
                self.logger.debug(
                    f"[{self.symbol}] ADX: Weak trend (ADX < {ADX_WEAK_TREND_THRESHOLD}). Neutral signal.",
                )
            signal_score += contrib
            signal_breakdown["ADX_Strength"] = contrib
        return signal_score, signal_breakdown

    def _score_ichimoku_cloud(
        self,
        signal_score: float,
        signal_breakdown: dict,
        current_close: Decimal,
        prev_close: Decimal,
    ) -> tuple[float, dict]:
        """Scores Ichimoku Cloud confluence."""
        if not self.config["indicators"].get("ichimoku_cloud", False):
            return signal_score, signal_breakdown

        tenkan_sen = self._get_indicator_value("Tenkan_Sen")
        kijun_sen = self._get_indicator_value("Kijun_Sen")
        senkou_span_a = self._get_indicator_value("Senkou_Span_A")
        senkou_span_b = self._get_indicator_value("Senkou_Span_B")
        chikou_span = self._get_indicator_value("Chikou_Span")
        weight = self.weights.get("ichimoku_confluence", 0)

        if (
            not pd.isna(tenkan_sen)
            and not pd.isna(kijun_sen)
            and not pd.isna(senkou_span_a)
            and not pd.isna(senkou_span_b)
            and not pd.isna(chikou_span)
            and len(self.df) > 1
            and weight > 0
        ):
            contrib = 0.0
            # Tenkan-sen / Kijun-sen crossover
            if (
                tenkan_sen > kijun_sen
                and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]
            ):
                contrib += weight * 0.5  # Bullish crossover
                self.logger.debug(
                    f"[{self.symbol}] Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish).",
                )
            elif (
                tenkan_sen < kijun_sen
                and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]
            ):
                contrib -= weight * 0.5  # Bearish crossover
                self.logger.debug(
                    f"[{self.symbol}] Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish).",
                )

            # Price breaking above/below Kumo (cloud)
            kumo_high = max(senkou_span_a, senkou_span_b)
            kumo_low = min(senkou_span_a, senkou_span_b)
            # Get previous kumo values, handle potential NaNs if data is sparse
            prev_kumo_high = (
                max(
                    self.df["Senkou_Span_A"].iloc[-2],
                    self.df["Senkou_Span_B"].iloc[-2],
                )
                if len(self.df) > 1
                else kumo_high
            )
            prev_kumo_low = (
                min(
                    self.df["Senkou_Span_A"].iloc[-2],
                    self.df["Senkou_Span_B"].iloc[-2],
                )
                if len(self.df) > 1
                else kumo_low
            )

            if (
                current_close > kumo_high
                and self.df["close"].iloc[-2] <= prev_kumo_high
            ):
                contrib += weight * 0.7  # Strong bullish breakout
                self.logger.debug(
                    f"[{self.symbol}] Ichimoku: Price broke above Kumo (strong bullish).",
                )
            elif (
                current_close < kumo_low and self.df["close"].iloc[-2] >= prev_kumo_low
            ):
                contrib -= weight * 0.7  # Strong bearish breakdown
                self.logger.debug(
                    f"[{self.symbol}] Ichimoku: Price broke below Kumo (strong bearish).",
                )

            # Chikou Span crossover with price
            if (
                chikou_span > current_close
                and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]
            ):
                contrib += weight * 0.3  # Bullish confirmation
                self.logger.debug(
                    f"[{self.symbol}] Ichimoku: Chikou Span crossed above price (bullish confirmation).",
                )
            elif (
                chikou_span < current_close
                and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]
            ):
                contrib -= weight * 0.3  # Bearish confirmation
                self.logger.debug(
                    f"[{self.symbol}] Ichimoku: Chikou Span crossed below price (bearish confirmation).",
                )
            signal_score += contrib
            signal_breakdown["Ichimoku_Confluence"] = contrib
        return signal_score, signal_breakdown

    def _score_obv(
        self,
        signal_score: float,
        signal_breakdown: dict,
    ) -> tuple[float, dict]:
        """Scores OBV momentum."""
        if not self.config["indicators"].get("obv", False):
            return signal_score, signal_breakdown

        obv_val = self._get_indicator_value("OBV")
        obv_ema = self._get_indicator_value("OBV_EMA")
        weight = self.weights.get("obv_momentum", 0)

        if (
            not pd.isna(obv_val)
            and not pd.isna(obv_ema)
            and len(self.df) > 1
            and weight > 0
        ):
            contrib = 0.0
            # OBV crossing its EMA
            if (
                obv_val > obv_ema
                and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]
            ):
                contrib = weight * 0.5  # Bullish crossover
                self.logger.debug(f"[{self.symbol}] OBV: Bullish crossover detected.")
            elif (
                obv_val < obv_ema
                and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]
            ):
                contrib = -weight * 0.5  # Bearish crossover
                self.logger.debug(f"[{self.symbol}] OBV: Bearish crossover detected.")

            # OBV trend confirmation (simplified: check if current OBV is higher/lower than previous two)
            if len(self.df) > 2:
                if (
                    obv_val > self.df["OBV"].iloc[-2]
                    and obv_val > self.df["OBV"].iloc[-3]
                ):
                    contrib += weight * 0.2  # OBV making higher highs
                elif (
                    obv_val < self.df["OBV"].iloc[-2]
                    and obv_val < self.df["OBV"].iloc[-3]
                ):
                    contrib -= weight * 0.2  # OBV making lower lows
            signal_score += contrib
            signal_breakdown["OBV_Momentum"] = contrib
        return signal_score, signal_breakdown

    def _score_cmf(
        self,
        signal_score: float,
        signal_breakdown: dict,
    ) -> tuple[float, dict]:
        """Scores CMF flow."""
        if not self.config["indicators"].get("cmf", False):
            return signal_score, signal_breakdown

        cmf_val = self._get_indicator_value("CMF")
        weight = self.weights.get("cmf_flow", 0)

        if not pd.isna(cmf_val) and weight > 0:
            contrib = 0.0
            # CMF above/below zero line
            if cmf_val > 0:
                contrib = weight * 0.5  # Bullish money flow
            elif cmf_val < 0:
                contrib = -weight * 0.5  # Bearish money flow

            # CMF trend confirmation (simplified: check if current CMF is higher/lower than previous two)
            if len(self.df) > 2:
                if (
                    cmf_val > self.df["CMF"].iloc[-2]
                    and cmf_val > self.df["CMF"].iloc[-3]
                ):
                    contrib += weight * 0.3  # CMF making higher highs
                elif (
                    cmf_val < self.df["CMF"].iloc[-2]
                    and cmf_val < self.df["CMF"].iloc[-3]
                ):
                    contrib -= weight * 0.3  # CMF making lower lows
            signal_score += contrib
            signal_breakdown["CMF_Flow"] = contrib
        return signal_score, signal_breakdown

    def _score_volatility_index(
        self,
        signal_score: float,
        signal_breakdown: dict,
    ) -> tuple[float, dict]:
        """Scores Volatility Index."""
        if not self.config["indicators"].get("volatility_index", False):
            return signal_score, signal_breakdown

        vol_idx = self._get_indicator_value("Volatility_Index")
        weight = self.weights.get("volatility_index_signal", 0)

        if not pd.isna(vol_idx) and weight > 0:
            contrib = 0.0
            if len(self.df) > 2 and "Volatility_Index" in self.df.columns:
                prev_vol_idx = self.df["Volatility_Index"].iloc[-2]
                prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3]

                if vol_idx > prev_vol_idx > prev_prev_vol_idx:  # Increasing volatility
                    # Increasing volatility can amplify existing signals
                    if signal_score > 0:  # If current score is bullish, amplify it
                        contrib = weight * 0.2
                    elif signal_score < 0:  # If current score is bearish, amplify it
                        contrib = -weight * 0.2
                    self.logger.debug(
                        f"[{self.symbol}] Volatility Index: Increasing volatility.",
                    )
                elif (
                    vol_idx < prev_vol_idx < prev_prev_vol_idx
                ):  # Decreasing volatility
                    # Decreasing volatility might reduce confidence in strong signals
                    if (
                        abs(signal_score) > 0
                    ):  # If there's an existing signal, slightly reduce its confidence
                        contrib = signal_score * -0.2  # Reduce score by 20% (example)
                    self.logger.debug(
                        f"[{self.symbol}] Volatility Index: Decreasing volatility.",
                    )
            signal_score += contrib
            signal_breakdown["Volatility_Index_Signal"] = contrib
        return signal_score, signal_breakdown

    def _score_vwma(
        self,
        signal_score: float,
        signal_breakdown: dict,
        current_close: Decimal,
        prev_close: Decimal,
    ) -> tuple[float, dict]:
        """Scores VWMA cross."""
        if not self.config["indicators"].get("vwma", False):
            return signal_score, signal_breakdown

        vwma = self._get_indicator_value("VWMA")
        weight = self.weights.get("vwma_cross", 0)

        if not pd.isna(vwma) and len(self.df) > 1 and weight > 0:
            prev_vwma = self.df["VWMA"].iloc[-2]
            contrib = 0.0
            # Price crossing VWMA
            if current_close > vwma and prev_close <= prev_vwma:
                contrib = weight  # Bullish crossover
                self.logger.debug(
                    f"[{self.symbol}] VWMA: Bullish crossover (price above VWMA).",
                )
            elif current_close < vwma and prev_close >= prev_vwma:
                contrib = -weight  # Bearish crossover
                self.logger.debug(
                    f"[{self.symbol}] VWMA: Bearish crossover (price below VWMA).",
                )
            signal_score += contrib
            signal_breakdown["VWMA_Cross"] = contrib
        return signal_score, signal_breakdown

    def _score_volume_delta(
        self,
        signal_score: float,
        signal_breakdown: dict,
    ) -> tuple[float, dict]:
        """Scores Volume Delta."""
        if not self.config["indicators"].get("volume_delta", False):
            return signal_score, signal_breakdown

        volume_delta = self._get_indicator_value("Volume_Delta")
        volume_delta_threshold = self.indicator_settings.get(
            "volume_delta_threshold",
            0.2,
        )
        weight = self.weights.get("volume_delta_signal", 0)

        if not pd.isna(volume_delta) and weight > 0:
            contrib = 0.0
            if volume_delta > volume_delta_threshold:  # Strong buying pressure
                contrib = weight
                self.logger.debug(
                    f"[{self.symbol}] Volume Delta: Strong buying pressure detected ({volume_delta:.2f}).",
                )
            elif volume_delta < -volume_delta_threshold:  # Strong selling pressure
                contrib = -weight
                self.logger.debug(
                    f"[{self.symbol}] Volume Delta: Strong selling pressure detected ({volume_delta:.2f}).",
                )
            # Weaker signals for moderate delta
            elif volume_delta > 0:
                contrib = weight * 0.3
            elif volume_delta < 0:
                contrib = -weight * 0.3
            signal_score += contrib
            signal_breakdown["Volume_Delta_Signal"] = contrib
        return signal_score, signal_breakdown

    def _score_mtf_confluence(
        self,
        signal_score: float,
        signal_breakdown: dict,
        mtf_trends: dict[str, str],
    ) -> tuple[float, dict]:
        """Scores Multi-Timeframe trend confluence."""
        if not self.config["mtf_analysis"]["enabled"] or not mtf_trends:
            return signal_score, signal_breakdown

        mtf_buy_score = 0
        mtf_sell_score = 0
        for _tf_indicator, trend in mtf_trends.items():
            if trend == "UP":
                mtf_buy_score += 1
            elif trend == "DOWN":
                mtf_sell_score += 1

        weight = self.weights.get("mtf_trend_confluence", 0)
        if weight == 0:
            return signal_score, signal_breakdown

        contrib = 0.0
        if mtf_trends:
            # Calculate a normalized score based on the balance of buy/sell trends
            # Max possible score is 1 (all UP), min is -1 (all DOWN)
            normalized_mtf_score = (mtf_buy_score - mtf_sell_score) / len(mtf_trends)
            contrib = weight * normalized_mtf_score
            self.logger.debug(
                f"[{self.symbol}] MTF Confluence: Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {mtf_sell_score}). Total MTF contribution: {contrib:.2f}",
            )
        signal_score += contrib
        signal_breakdown["MTF_Trend_Confluence"] = contrib
        return signal_score, signal_breakdown

    # UPGRADE 2: Trade Confirmation with Volume & Volatility Filters
    def _score_trade_confirmation(
        self,
        signal_score: float,
        signal_breakdown: dict,
    ) -> tuple[float, dict]:
        """Applies score modifiers based on volume and volatility for trade confirmation."""
        isd = self.indicator_settings
        cfg = self.config
        current_volume = self.df["volume"].iloc[-1]

        # Volume Confirmation
        if isd.get("enable_volume_confirmation", False) and cfg["indicators"].get(
            "volume_confirmation",
            False,
        ):
            avg_volume = Decimal(str(self._get_indicator_value("Avg_Volume")))
            min_volume_multiplier = Decimal(str(isd.get("min_volume_multiplier", 1.0)))
            weight = self.weights.get("volume_confirmation", 0)

            if not pd.isna(avg_volume) and avg_volume > 0 and weight > 0:
                if current_volume >= (avg_volume * min_volume_multiplier):
                    signal_score += weight
                    signal_breakdown["Volume_Confirmation"] = weight
                    self.logger.debug(
                        f"[{self.symbol}] Volume Confirmation: Volume ({current_volume:.2f}) above average ({avg_volume:.2f} * {min_volume_multiplier}).",
                    )
                else:
                    signal_score -= weight * 0.5  # Penalize if volume is too low
                    signal_breakdown["Volume_Confirmation"] = -weight * 0.5
                    self.logger.debug(
                        f"[{self.symbol}] Volume Confirmation: Volume ({current_volume:.2f}) below threshold. Penalizing.",
                    )

        # Volatility Filter
        if isd.get("enable_volatility_filter", False) and cfg["indicators"].get(
            "volatility_filter",
            False,
        ):
            vol_idx = self._get_indicator_value("Volatility_Index")
            optimal_min = Decimal(str(isd.get("optimal_volatility_min", 0.0)))
            optimal_max = Decimal(str(isd.get("optimal_volatility_max", 1.0)))
            weight = self.weights.get("volatility_filter", 0)

            if not pd.isna(vol_idx) and weight > 0:
                if optimal_min <= vol_idx <= optimal_max:
                    signal_score += weight
                    signal_breakdown["Volatility_Filter"] = weight
                    self.logger.debug(
                        f"[{self.symbol}] Volatility Filter: Volatility Index ({vol_idx:.4f}) is within optimal range [{optimal_min:.4f}-{optimal_max:.4f}].",
                    )
                else:
                    signal_score -= (
                        weight * 0.5
                    )  # Penalize if volatility is outside optimal range
                    signal_breakdown["Volatility_Filter"] = -weight * 0.5
                    self.logger.debug(
                        f"[{self.symbol}] Volatility Filter: Volatility Index ({vol_idx:.4f}) is outside optimal range. Penalizing.",
                    )

        return signal_score, signal_breakdown

    # UPGRADE 3: News/Sentiment Integration Placeholder
    def _score_sentiment(
        self,
        signal_score: float,
        signal_breakdown: dict,
        sentiment_score: float | None,
    ) -> tuple[float, dict]:
        """Scores based on external sentiment data."""
        ml_enhancement_cfg = self.config["ml_enhancement"]
        if not ml_enhancement_cfg.get("sentiment_analysis_enabled", False):
            return signal_score, signal_breakdown

        weight = self.weights.get("sentiment_signal", 0)
        bullish_threshold = ml_enhancement_cfg.get("bullish_sentiment_threshold", 0.6)
        bearish_threshold = ml_enhancement_cfg.get("bearish_sentiment_threshold", 0.4)

        if sentiment_score is not None and weight > 0:
            contrib = 0.0
            if sentiment_score >= bullish_threshold:
                contrib = weight
                self.logger.debug(
                    f"[{self.symbol}] Sentiment: Bullish ({sentiment_score:.2f}).",
                )
            elif sentiment_score <= bearish_threshold:
                contrib = -weight
                self.logger.debug(
                    f"[{self.symbol}] Sentiment: Bearish ({sentiment_score:.2f}).",
                )
            else:
                contrib = 0  # Neutral sentiment

            signal_score += contrib
            signal_breakdown["Sentiment_Signal"] = contrib
        return signal_score, signal_breakdown

    # UPGRADE 5: Market Condition Adaptive Strategy Selection Helper
    def assess_market_conditions(self) -> dict[str, Any]:
        """Assesses current market conditions based on key indicators."""
        adx = self._get_indicator_value("ADX")
        vol_idx = self._get_indicator_value("Volatility_Index")
        ema_short = self._get_indicator_value("EMA_Short")
        ema_long = self._get_indicator_value("EMA_Long")
        plus_di = self._get_indicator_value("PlusDI")
        minus_di = self._get_indicator_value("MinusDI")

        conditions: dict[str, Any] = {
            "trend_strength": "UNKNOWN",
            "trend_direction": "NEUTRAL",
            "volatility": "MODERATE",
            "adx_value": adx,
            "volatility_index_value": vol_idx,
        }

        isd = self.indicator_settings
        strong_adx = isd.get("ADX_STRONG_TREND_THRESHOLD", 25)
        weak_adx = isd.get("ADX_WEAK_TREND_THRESHOLD", 20)

        # Trend Strength (from ADX)
        if not pd.isna(adx):
            if adx > strong_adx:
                conditions["trend_strength"] = "STRONG"
            elif adx < weak_adx:
                conditions["trend_strength"] = "WEAK"
            else:
                conditions["trend_strength"] = "MODERATE"

        # Trend Direction (from ADX and EMA)
        if not pd.isna(plus_di) and not pd.isna(minus_di):
            if plus_di > minus_di and conditions["trend_strength"] in [
                "STRONG",
                "MODERATE",
            ]:
                conditions["trend_direction"] = "UP"
            elif minus_di > plus_di and conditions["trend_strength"] in [
                "STRONG",
                "MODERATE",
            ]:
                conditions["trend_direction"] = "DOWN"
            elif not pd.isna(ema_short) and not pd.isna(
                ema_long,
            ):  # Fallback to EMA if ADX direction is unclear
                if ema_short > ema_long:
                    conditions["trend_direction"] = "UP"
                elif ema_short < ema_long:
                    conditions["trend_direction"] = "DOWN"

        # Volatility (from Volatility Index)
        if not pd.isna(vol_idx):
            optimal_min = Decimal(str(isd.get("optimal_volatility_min", 0.0)))
            optimal_max = Decimal(str(isd.get("optimal_volatility_max", 1.0)))

            if vol_idx < optimal_min:
                conditions["volatility"] = "LOW"
            elif vol_idx > optimal_max:
                conditions["volatility"] = "HIGH"
            else:
                conditions["volatility"] = "MODERATE"

        self.logger.debug(f"[{self.symbol}] Market Conditions: {conditions}")
        return conditions

    def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_data: dict | None,
        mtf_trends: dict[str, str],
        sentiment_score: float | None = None,  # UPGRADE 3: Add sentiment score
    ) -> tuple[str, float, dict]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend.
        Returns the final signal, the aggregated signal score, and a breakdown of contributions.
        """
        signal_score = 0.0
        signal_breakdown: dict[str, float] = {}  # Initialize breakdown dictionary

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}",
            )
            return "HOLD", 0.0, {}

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        # Get previous close price, handle case with only one data point
        prev_close = (
            Decimal(str(self.df["close"].iloc[-2]))
            if len(self.df) > 1
            else current_close
        )

        # --- Apply Scoring for Each Indicator Group ---
        signal_score, signal_breakdown = self._score_ema_alignment(
            signal_score,
            signal_breakdown,
        )
        signal_score, signal_breakdown = self._score_sma_trend_filter(
            signal_score,
            signal_breakdown,
            current_close,
        )
        signal_score, signal_breakdown = self._score_momentum(
            signal_score,
            signal_breakdown,
            current_close,
            prev_close,
        )
        signal_score, signal_breakdown = self._score_bollinger_bands(
            signal_score,
            signal_breakdown,
            current_close,
        )
        signal_score, signal_breakdown = self._score_vwap(
            signal_score,
            signal_breakdown,
            current_close,
            prev_close,
        )
        signal_score, signal_breakdown = self._score_psar(
            signal_score,
            signal_breakdown,
            current_close,
            prev_close,
        )
        signal_score, signal_breakdown = self._score_orderbook_imbalance(
            signal_score,
            signal_breakdown,
            orderbook_data,
        )
        signal_score, signal_breakdown = self._score_fibonacci_levels(
            signal_score,
            signal_breakdown,
            current_close,
            prev_close,
        )
        signal_score, signal_breakdown = self._score_ehlers_supertrend(
            signal_score,
            signal_breakdown,
        )
        signal_score, signal_breakdown = self._score_macd(
            signal_score,
            signal_breakdown,
        )
        signal_score, signal_breakdown = self._score_adx(signal_score, signal_breakdown)
        signal_score, signal_breakdown = self._score_ichimoku_cloud(
            signal_score,
            signal_breakdown,
            current_close,
            prev_close,
        )
        signal_score, signal_breakdown = self._score_obv(signal_score, signal_breakdown)
        signal_score, signal_breakdown = self._score_cmf(signal_score, signal_breakdown)
        signal_score, signal_breakdown = self._score_volatility_index(
            signal_score,
            signal_breakdown,
        )
        signal_score, signal_breakdown = self._score_vwma(
            signal_score,
            signal_breakdown,
            current_close,
            prev_close,
        )
        signal_score, signal_breakdown = self._score_volume_delta(
            signal_score,
            signal_breakdown,
        )
        signal_score, signal_breakdown = self._score_mtf_confluence(
            signal_score,
            signal_breakdown,
            mtf_trends,
        )

        # UPGRADE 2: Trade Confirmation Scoring
        signal_score, signal_breakdown = self._score_trade_confirmation(
            signal_score,
            signal_breakdown,
        )
        # UPGRADE 3: Sentiment Scoring
        signal_score, signal_breakdown = self._score_sentiment(
            signal_score,
            signal_breakdown,
            sentiment_score,
        )

        # --- Final Signal Determination with Hysteresis and Cooldown ---
        threshold = self.config["signal_score_threshold"]
        cooldown_sec = self.config["cooldown_sec"]
        hysteresis_ratio = self.config["hysteresis_ratio"]

        final_signal = "HOLD"
        now_ts = int(time.time())

        is_strong_buy = signal_score >= threshold
        is_strong_sell = signal_score <= -threshold

        # Apply hysteresis to prevent immediate flip-flops
        # If the bot previously issued a BUY signal and the current score is not a strong SELL, and not a strong BUY, it holds the BUY signal.
        # This prevents it from flipping to HOLD or SELL too quickly if the score dips slightly.
        if (
            self._last_signal_score > 0
            and signal_score > -threshold * hysteresis_ratio
            and not is_strong_buy
        ):
            final_signal = "BUY"
        # If the bot previously issued a SELL signal and the current score is not a strong BUY, and not a strong SELL, it holds the SELL signal.
        elif (
            self._last_signal_score < 0
            and signal_score < threshold * hysteresis_ratio
            and not is_strong_sell
        ):
            final_signal = "SELL"
        elif is_strong_buy:
            final_signal = "BUY"
        elif is_strong_sell:
            final_signal = "SELL"

        # Apply cooldown period
        if final_signal != "HOLD":
            if now_ts - self._last_signal_ts < cooldown_sec:
                self.logger.info(
                    f"{NEON_YELLOW}[{self.symbol}] Signal '{final_signal}' ignored due to cooldown ({cooldown_sec - (now_ts - self._last_signal_ts)}s remaining).{RESET}",
                )
                final_signal = "HOLD"
            else:
                self._last_signal_ts = (
                    now_ts  # Update timestamp only if signal is issued
                )

        # Update last signal score for next iteration's hysteresis
        self._last_signal_score = signal_score

        self.logger.info(
            f"{NEON_YELLOW}[{self.symbol}] Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}",
        )
        return final_signal, signal_score, signal_breakdown

    def calculate_entry_tp_sl(
        self,
        current_price: Decimal,
        atr_value: Decimal,
        signal: Literal["Buy", "Sell"],
    ) -> tuple[Decimal, Decimal]:
        """Calculate Take Profit and Stop Loss levels."""
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"]),
        )
        # Ensure price precision is at least 1 (e.g., 0.1, 0.01, etc.)
        price_precision_exponent = max(
            0,
            self.config["trade_management"]["price_precision"] - 1,
        )
        price_precision_str = "0." + "0" * price_precision_exponent + "1"
        quantize_dec = Decimal(price_precision_str)

        if signal == "Buy":
            stop_loss = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit = current_price + (atr_value * take_profit_atr_multiple)
        elif signal == "Sell":
            stop_loss = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit = current_price - (atr_value * take_profit_atr_multiple)
        else:  # Should not happen for valid signals
            return Decimal("0"), Decimal("0")

        return take_profit.quantize(
            quantize_dec,
            rounding=ROUND_DOWN,
        ), stop_loss.quantize(quantize_dec, rounding=ROUND_DOWN)


def display_indicator_values_and_price(
    config: dict[str, Any],
    logger: logging.Logger,
    current_price: Decimal,
    df: pd.DataFrame,
    orderbook_data: dict | None,
    mtf_trends: dict[str, str],
    signal_breakdown: dict | None = None,  # New parameter for displaying breakdown
) -> None:
    """Display current price and calculated indicator values."""
    logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
    logger.info(f"{NEON_GREEN}Current Price: {current_price.normalize()}{RESET}")

    # Re-initialize TradingAnalyzer to get the latest indicator values for display
    # This might be slightly redundant if called after signal generation, but ensures display is up-to-date.
    analyzer = TradingAnalyzer(df, config, logger, config["symbol"])

    if analyzer.df.empty:
        logger.warning(
            f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.{RESET}",
        )
        return

    logger.info(f"{NEON_CYAN}--- Indicator Values ---{RESET}")
    # Sort indicators alphabetically for consistent display
    sorted_indicator_items = sorted(analyzer.indicator_values.items())
    for indicator_name, value in sorted_indicator_items:
        color = INDICATOR_COLORS.get(indicator_name, NEON_YELLOW)
        # Format Decimal values for consistent display
        if isinstance(value, Decimal):
            logger.info(f"  {color}{indicator_name}: {value.normalize()}{RESET}")
        elif isinstance(value, float):
            logger.info(
                f"  {color}{indicator_name}: {value:.8f}{RESET}",
            )  # Use higher precision for floats
        else:
            logger.info(f"  {color}{indicator_name}: {value}{RESET}")

    if analyzer.fib_levels:
        logger.info(f"{NEON_CYAN}--- Fibonacci Levels ---{RESET}")
        logger.info("")  # Added newline for spacing
        # Sort Fibonacci levels by ratio for consistent display
        sorted_fib_levels = sorted(
            analyzer.fib_levels.items(),
            key=lambda item: float(item[0].replace("%", "")) / 100,
        )
        for level_name, level_price in sorted_fib_levels:
            logger.info(
                f"  {NEON_YELLOW}{level_name}: {level_price.normalize()}{RESET}",
            )

    if mtf_trends:
        logger.info(f"{NEON_CYAN}--- Multi-Timeframe Trends ---{RESET}")
        logger.info("")  # Added newline for spacing
        # Sort MTF trends by timeframe for consistent display
        sorted_mtf_trends = sorted(mtf_trends.items())
        for tf_indicator, trend in sorted_mtf_trends:
            logger.info(f"  {NEON_YELLOW}{tf_indicator}: {trend}{RESET}")

    if signal_breakdown:
        logger.info(f"{NEON_CYAN}--- Signal Score Breakdown ---{RESET}")
        # Sort by absolute contribution for better readability
        sorted_breakdown = sorted(
            signal_breakdown.items(),
            key=lambda item: abs(item[1]),
            reverse=True,
        )
        for indicator, contribution in sorted_breakdown:
            color = (
                Fore.GREEN
                if contribution > 0
                else (Fore.RED if contribution < 0 else Fore.YELLOW)
            )
            logger.info(f"  {color}{indicator:<25}: {contribution: .2f}{RESET}")

    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")


# --- Main Execution Logic ---
def main() -> None:
    """Orchestrate the bot's operation."""
    global config  # Declare config as global to allow modification by adaptive strategy
    # The logger is now initialized globally.
    config = load_config(CONFIG_FILE, logger)
    alert_system = AlertSystem(logger)

    # These are standard Bybit intervals. It's good practice to keep them consistent.
    valid_bybit_intervals = [
        "1",
        "3",
        "5",
        "15",
        "30",
        "60",
        "120",
        "240",
        "360",
        "720",
        "D",
        "W",
        "M",
    ]

    if config["interval"] not in valid_bybit_intervals:
        logger.error(
            f"{NEON_RED}Invalid primary interval '{config['interval']}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.{RESET}",
        )
        sys.exit(1)

    for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
        if htf_interval not in valid_bybit_intervals:
            logger.error(
                f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}' in config.json. Please use Bybit's valid string formats (e.g., '60', '240'). Exiting.{RESET}",
            )
            sys.exit(1)

    logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Initialized ---{RESET}")
    logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
    logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")

    # Initialize WebSocket Manager and start streams
    ws_manager = BybitWebSocketManager(config, logger)
    ws_manager.start_public_stream()
    ws_manager.start_private_stream()
    ws_manager.wait_for_initial_data(timeout=45)  # Wait for initial data from WS

    position_manager = PositionManager(config, logger, config["symbol"], ws_manager)
    performance_tracker = PerformanceTracker(logger)

    current_strategy_profile = config["current_strategy_profile"]

    try:
        while True:
            logger.info(
                f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}",
            )

            # --- Fetch Market Data ---
            current_price = fetch_current_price(
                config["symbol"],
                logger,
                ws_manager=ws_manager,
            )
            if current_price is None:
                alert_system.send_alert(
                    f"[{config['symbol']}] Failed to fetch current price. Skipping loop.",
                    "WARNING",
                )
                time.sleep(config["loop_delay"])
                continue

            df = fetch_klines(
                config["symbol"],
                config["interval"],
                1000,
                logger,
                ws_manager=ws_manager,
            )
            if df is None or df.empty:
                alert_system.send_alert(
                    f"[{config['symbol']}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
                    "WARNING",
                )
                time.sleep(config["loop_delay"])
                continue

            orderbook_data = None
            if config["indicators"].get("orderbook_imbalance", False):
                orderbook_data = fetch_orderbook(
                    config["symbol"],
                    config["orderbook_limit"],
                    logger,
                    ws_manager=ws_manager,
                )

            mtf_trends: dict[str, str] = {}
            if config["mtf_analysis"]["enabled"]:
                # Pass ws_manager to MTF analysis to enable WS data fetching for higher TFs
                temp_analyzer_for_mtf = TradingAnalyzer(
                    df,
                    config,
                    logger,
                    config["symbol"],
                )
                mtf_trends = temp_analyzer_for_mtf._fetch_and_analyze_mtf(
                    ws_manager=ws_manager,
                )

            # UPGRADE 3: Fetch Sentiment Score
            sentiment_score: float | None = None
            if config["ml_enhancement"].get("sentiment_analysis_enabled", False):
                sentiment_score = fetch_latest_sentiment(config["symbol"], logger)

            # --- Initialize Analyzer and Assess Market Conditions (for Adaptive Strategy) ---
            analyzer = TradingAnalyzer(df, config, logger, config["symbol"])

            if analyzer.df.empty:
                alert_system.send_alert(
                    f"[{config['symbol']}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                    "WARNING",
                )
                time.sleep(config["loop_delay"])
                continue

            # UPGRADE 5: Adaptive Strategy Selection Logic
            if config.get("adaptive_strategy_enabled", False):
                market_conditions = analyzer.assess_market_conditions()
                suggested_strategy = config[
                    "current_strategy_profile"
                ]  # Default to current

                for profile_name, profile_details in config[
                    "strategy_profiles"
                ].items():
                    criteria = profile_details.get("market_condition_criteria")
                    if not criteria:
                        continue  # Skip profiles without criteria

                    # Check ADX range
                    adx_match = True
                    if (
                        "adx_range" in criteria
                        and market_conditions["adx_value"] is not np.nan
                    ):
                        adx_min, adx_max = criteria["adx_range"]
                        if not (adx_min <= market_conditions["adx_value"] <= adx_max):
                            adx_match = False

                    # Check Volatility range
                    vol_match = True
                    if (
                        "volatility_range" in criteria
                        and market_conditions["volatility_index_value"] is not np.nan
                    ):
                        vol_min, vol_max = criteria["volatility_range"]
                        # Convert config float to Decimal for comparison
                        vol_min_dec = Decimal(str(vol_min))
                        vol_max_dec = Decimal(str(vol_max))
                        market_vol_dec = Decimal(
                            str(market_conditions["volatility_index_value"]),
                        )  # Ensure comparison with Decimal
                        if not (vol_min_dec <= market_vol_dec <= vol_max_dec):
                            vol_match = False

                    if adx_match and vol_match:  # Add more conditions as needed
                        if profile_name != current_strategy_profile:
                            suggested_strategy = profile_name
                            break  # Found a match, prioritize first match

                if suggested_strategy != current_strategy_profile:
                    logger.info(
                        f"{NEON_YELLOW}[{config['symbol']}] Market conditions suggest switching strategy from '{current_strategy_profile}' to '{suggested_strategy}'. Reloading config.{RESET}",
                    )
                    config["current_strategy_profile"] = suggested_strategy
                    config = load_config(
                        CONFIG_FILE,
                        logger,
                    )  # Reload config to apply new strategy profile
                    analyzer = TradingAnalyzer(
                        df,
                        config,
                        logger,
                        config["symbol"],
                    )  # Re-initialize analyzer
                    current_strategy_profile = (
                        suggested_strategy  # Update tracked strategy name
                    )

            # Get ATR for position sizing and SL/TP calculation
            atr_value = Decimal(
                str(analyzer._get_indicator_value("ATR", Decimal("0.0001"))),
            )
            if atr_value <= 0:  # Ensure ATR is positive for calculations
                atr_value = Decimal("0.0001")
                logger.warning(
                    f"{NEON_YELLOW}[{config['symbol']}] ATR value was zero or negative, defaulting to {atr_value}.{RESET}",
                )

            # Generate trading signal
            # UPGRADE 3: Pass sentiment_score to signal generation
            trading_signal, signal_score, signal_breakdown = (
                analyzer.generate_trading_signal(
                    current_price,
                    orderbook_data,
                    mtf_trends,
                    sentiment_score,
                )
            )

            # Manage open positions (sync with exchange, check/update TSL/Breakeven/Profit-lock)
            position_manager.manage_positions(
                current_price,
                performance_tracker,
                atr_value,
            )

            # Display current state after analysis and signal generation, including breakdown
            display_indicator_values_and_price(
                config,
                logger,
                current_price,
                df,
                orderbook_data,
                mtf_trends,
                signal_breakdown,
            )

            # Execute trades based on strong signals
            signal_threshold = config["signal_score_threshold"]

            has_buy_position = any(
                p["side"].upper() == "BUY"
                for p in position_manager.get_open_positions()
            )
            has_sell_position = any(
                p["side"].upper() == "SELL"
                for p in position_manager.get_open_positions()
            )

            if trading_signal == "BUY" and signal_score >= signal_threshold:
                logger.info(
                    f"{NEON_GREEN}[{config['symbol']}] Strong BUY signal detected! Score: {signal_score:.2f}{RESET}",
                )
                if has_sell_position:
                    # UPGRADE 4: Handle opposite signal
                    if position_manager.close_on_opposite_signal:
                        logger.warning(
                            f"{NEON_YELLOW}[{config['symbol']}] Detected strong BUY signal while a SELL position is open. Attempting to close SELL position.{RESET}",
                        )
                        sell_pos = next(
                            p
                            for p in position_manager.get_open_positions()
                            if p["side"].upper() == "SELL"
                        )
                        position_manager.close_position(
                            sell_pos,
                            current_price,
                            performance_tracker,
                            closed_by="OPPOSITE_SIGNAL",
                        )
                        if position_manager.reverse_position_on_opposite_signal:
                            logger.info(
                                f"{NEON_GREEN}[{config['symbol']}] Reversing position: Opening new BUY position after closing SELL.{RESET}",
                            )
                            position_manager.open_position(
                                "Buy",
                                current_price,
                                atr_value,
                            )
                    else:
                        logger.info(
                            f"{NEON_YELLOW}[{config['symbol']}] Close on opposite signal is disabled. Holding SELL position.{RESET}",
                        )
                elif not has_buy_position:  # Only open if no BUY position exists
                    position_manager.open_position("Buy", current_price, atr_value)
                else:
                    logger.info(
                        f"{NEON_YELLOW}[{config['symbol']}] Already have a BUY position. Not opening another.{RESET}",
                    )

            elif trading_signal == "SELL" and signal_score <= -signal_threshold:
                logger.info(
                    f"{NEON_RED}[{config['symbol']}] Strong SELL signal detected! Score: {signal_score:.2f}{RESET}",
                )
                if has_buy_position:
                    # UPGRADE 4: Handle opposite signal
                    if position_manager.close_on_opposite_signal:
                        logger.warning(
                            f"{NEON_YELLOW}[{config['symbol']}] Detected strong SELL signal while a BUY position is open. Attempting to close BUY position.{RESET}",
                        )
                        buy_pos = next(
                            p
                            for p in position_manager.get_open_positions()
                            if p["side"].upper() == "BUY"
                        )
                        position_manager.close_position(
                            buy_pos,
                            current_price,
                            performance_tracker,
                            closed_by="OPPOSITE_SIGNAL",
                        )
                        if position_manager.reverse_position_on_opposite_signal:
                            logger.info(
                                f"{NEON_RED}[{config['symbol']}] Reversing position: Opening new SELL position after closing BUY.{RESET}",
                            )
                            position_manager.open_position(
                                "Sell",
                                current_price,
                                atr_value,
                            )
                    else:
                        logger.info(
                            f"{NEON_YELLOW}[{config['symbol']}] Close on opposite signal is disabled. Holding BUY position.{RESET}",
                        )
                elif not has_sell_position:  # Only open if no SELL position exists
                    position_manager.open_position("Sell", current_price, atr_value)
                else:
                    logger.info(
                        f"{NEON_YELLOW}[{config['symbol']}] Already have a SELL position. Not opening another.{RESET}",
                    )
            else:
                logger.info(
                    f"{NEON_BLUE}[{config['symbol']}] No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}",
                )

            # Log current open positions and performance summary
            open_positions = (
                position_manager.get_open_positions()
            )  # Get the *internally tracked* positions
            if open_positions:
                logger.info(
                    f"{NEON_CYAN}[{config['symbol']}] Open Positions: {len(open_positions)}{RESET}",
                )
                for pos in open_positions:
                    # Access dictionary elements directly instead of using .normalize() on Decimal which is already done during quantization
                    logger.info(
                        f"  - {pos['side']} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}, TSL Active: {pos['trailing_stop_activated']}){RESET}",
                    )
            else:
                logger.info(
                    f"{NEON_CYAN}[{config['symbol']}] No open positions.{RESET}",
                )

            perf_summary = performance_tracker.get_summary()
            logger.info(
                f"{NEON_YELLOW}[{config['symbol']}] Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}",
            )

            logger.info(
                f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}",
            )
            time.sleep(config["loop_delay"])

    except KeyboardInterrupt:
        logger.info(f"{NEON_YELLOW}Bot stopping due to KeyboardInterrupt.{RESET}")
    except Exception as e:
        alert_system.send_alert(
            f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}",
            "ERROR",
        )
        logger.exception(
            f"{NEON_RED}[{config['symbol']}] Unhandled exception in main loop:{RESET}",
        )
        time.sleep(config["loop_delay"] * 2)  # Longer sleep after an error
    finally:
        ws_manager.stop_all_streams()  # Ensure WebSocket connections are closed
        logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Shut Down ---{RESET}")


if __name__ == "__main__":
    main()
