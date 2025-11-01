import hashlib
import hmac
import json
import logging
import os
import sys
import time
import urllib.parse
from datetime import UTC
from datetime import datetime
from decimal import ROUND_DOWN
from decimal import Decimal
from decimal import getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from typing import ClassVar
from typing import Literal

import numpy as np
import pandas as pd
import requests
from colorama import Fore
from colorama import Style
from colorama import init
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Whalebot: An advanced cryptocurrency trading bot for Bybit.
#
# This bot integrates various technical indicators, including Ehlers SuperTrend,
# MACD, RSI, Bollinger Bands, Ichimoku Cloud, and more, to generate trading signals.
# It features robust position management, performance tracking, and a flexible
# configuration system.


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
    "Kaufman_AMA": Fore.GREEN,
    "Relative_Volume": Fore.LIGHTMAGENTA_EX,
    "Market_Structure_Trend": Fore.LIGHTCYAN_EX,
    "DEMA": Fore.BLUE,
    "Keltner_Upper": Fore.LIGHTMAGENTA_EX,
    "Keltner_Middle": Fore.WHITE,
    "Keltner_Lower": Fore.MAGENTA,
    "ROC": Fore.LIGHTGREEN_EX,
    "Pivot": Fore.WHITE,
    "R1": Fore.CYAN,
    "R2": Fore.LIGHTCYAN_EX,
    "S1": Fore.MAGENTA,
    "S2": Fore.LIGHTMAGENTA_EX,
    "Candlestick_Pattern": Fore.LIGHTYELLOW_EX,
    "Support_Level": Fore.LIGHTCYAN_EX,
    "Resistance_Level": Fore.RED,
}

# --- Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs/trading-bot/logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

# Using UTC for consistency and to avoid timezone issues with API timestamps
TIMEZONE = UTC
MAX_API_RETRIES = 5
RETRY_DELAY_SECONDS = 7
REQUEST_TIMEOUT = 20
LOOP_DELAY_SECONDS = 15

# Magic Numbers as Constants (expanded)
MIN_DATA_POINTS_TR = 2
MIN_DATA_POINTS_SMOOTHER_INIT = 2  # For SuperSmoother initialization
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR = 2
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20
STOCH_RSI_MID_POINT = 50
MIN_CANDLESTICK_PATTERNS_BARS = 2  # Minimum bars needed for pattern detection


# --- Configuration Management ---
def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    """Load configuration from JSON file, creating a default if not found."""
    default_config = {
        # Core Settings
        "symbol": "BTCUSDT",
        "interval": "15",  # Changed "15m" to "15" to match Bybit API requirement
        "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50,
        # Signal Generation
        "signal_score_threshold": 2.0,
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
            "slippage_percent": 0.001,  # 0.1% slippage for entry/exit
            "trading_fee_percent": 0.0005,  # 0.05% for maker/taker (example)
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
            "kama_period": 10,  # New: KAMA Period
            "kama_fast_period": 2,  # New: KAMA Fast EMA Period
            "kama_slow_period": 30,  # New: KAMA Slow EMA Period
            "relative_volume_period": 20,  # New: Relative Volume Period
            "relative_volume_threshold": 1.5,
            "market_structure_lookback_period": 20,  # New: Market Structure Lookback
            "dema_period": 14,  # New: DEMA Period
            "keltner_period": 20,  # New: Keltner Channels Period (for EMA)
            "keltner_atr_multiplier": 2.0,  # New: Keltner Channels ATR multiplier
            "roc_period": 12,  # New: ROC Period
            "roc_oversold": -5.0,
            "roc_overbought": 5.0,
        },
        # Active Indicators & Weights (expanded)
        "indicators": {
            "ema_alignment": True,
            "sma_trend_filter": True,
            "momentum": True,  # Now a general category,
            # individual momentum indicators are sub-checked
            "volume_confirmation": True,
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
            "volatility_index": True,  # New
            "vwma": True,  # New
            "volume_delta": True,  # New
            "kaufman_ama": True,  # New
            "relative_volume": True,
            "market_structure": True,
            "dema": True,
            "keltner_channels": True,
            "roc": True,
            "candlestick_patterns": True,
            "fibonacci_pivot_points": True,  # New
        },
        "weight_sets": {
            "default_scalping": {
                "ema_alignment": 0.22,
                "sma_trend_filter": 0.28,
                "momentum_rsi_stoch_cci_wr_mfi": 0.18,  # Combined weight for momentum
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
                "volatility_index_signal": 0.15,  # New
                "vwma_cross": 0.15,  # New
                "volume_delta_signal": 0.10,  # New
                "kaufman_ama_cross": 0.20,  # New
                "relative_volume_confirmation": 0.10,
                "market_structure_confluence": 0.25,
                "dema_crossover": 0.18,
                "keltner_breakout": 0.20,
                "roc_signal": 0.12,
                "candlestick_confirmation": 0.15,
                "fibonacci_pivot_points_confluence": 0.20,
            },
        },
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(
                f"{NEON_YELLOW}Configuration file not found. "
                f"Created default config at {filepath} for symbol {default_config['symbol']}{RESET}",
            )
            return default_config
        except OSError as e:
            logger.error(f"{NEON_RED}Error creating default config file: {e}{RESET}")
            return default_config

    try:
        with Path(filepath).open(encoding="utf-8") as f:
            config = json.load(f)
        _ensure_config_keys(config, default_config)
        with Path(filepath).open("w", encoding="utf-8") as f_write:
            json.dump(config, f_write, indent=4)
        return config
    except (OSError, FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(
            f"{NEON_RED}Error loading config: {e}. "
            f"Using default and attempting to save.{RESET}",
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


# --- Logging Setup ---
class SensitiveFormatter(logging.Formatter):
    """Formatter that redacts API keys from log records."""

    SENSITIVE_WORDS: ClassVar[list[str]] = ["API_KEY", "API_SECRET"]

    def __init__(self, fmt=None, datefmt=None, style="%"):
        """Initialize the SensitiveFormatter."""
        super().__init__(fmt, datefmt, style)
        self._fmt = fmt if fmt else self.default_fmt()

    def default_fmt(self):
        """Return the default log format string."""
        return "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def format(self, record):
        """Format the log record, redacting sensitive words."""
        original_message = super().format(record)
        redacted_message = original_message
        for word in self.SENSITIVE_WORDS:
            if word in redacted_message:
                redacted_message = redacted_message.replace(word, "*" * len(word))
        return redacted_message


def setup_logger(log_name: str, level=logging.INFO) -> logging.Logger:
    """Configure and return a logger with file and console handlers."""
    logger = logging.getLogger(log_name)
    logger.setLevel(level)
    logger.propagate = False

    # Ensure handlers are not duplicated
    if not logger.handlers:
        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            SensitiveFormatter(
                f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}",
            ),
        )
        logger.addHandler(console_handler)

        # File Handler
        log_file = Path(LOG_DIRECTORY) / f"{log_name}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        )
        file_handler.setFormatter(
            SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
        )
        logger.addHandler(file_handler)

    return logger


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


def _send_signed_request(
    method: Literal["GET", "POST"],
    url: str,
    params: dict | None,
    session: requests.Session,
    logger: logging.Logger,
) -> requests.Response | None:
    """Send a signed request to the Bybit API."""
    if not API_KEY or not API_SECRET:
        logger.error(
            f"{NEON_RED}API_KEY or API_SECRET not set for signed request.{RESET}",
        )
        return None

    timestamp = str(int(time.time() * 1000))
    recv_window = "20000"  # Standard recommended receive window
    headers = {"Content-Type": "application/json"}

    if method == "GET":
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
        return session.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
    # POST
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
    return session.post(url, json=params, headers=headers, timeout=REQUEST_TIMEOUT)


def _handle_api_response(
    response: requests.Response,
    logger: logging.Logger,
) -> dict | None:
    """Helper to handle API responses and common errors."""
    try:
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") != 0:
            logger.error(
                f"{NEON_RED}Bybit API Error: {data.get('retMsg')} "
                f"(Code: {data.get('retCode')}){RESET}",
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


def bybit_request(
    method: Literal["GET", "POST"],
    endpoint: str,
    params: dict | None = None,
    signed: bool = False,
    logger: logging.Logger | None = None,
) -> dict | None:
    """Send a request to the Bybit API."""
    if logger is None:
        logger = setup_logger("bybit_api")
    session = create_session()
    url = f"{BASE_URL}{endpoint}"

    if signed:
        response = _send_signed_request(method, url, params, session, logger)
    else:
        logger.debug(f"Public Request: {url} with params {params}")
        response = session.get(url, params=params, timeout=REQUEST_TIMEOUT)

    if response:
        return _handle_api_response(response, logger)
    return None


def fetch_current_price(symbol: str, logger: logging.Logger) -> Decimal | None:
    """Fetch the current market price for a symbol."""
    endpoint = "/v5/market/tickers"
    params = {"category": "linear", "symbol": symbol}
    response = bybit_request("GET", endpoint, params, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        price = Decimal(response["result"]["list"][0]["lastPrice"])
        logger.debug(f"Fetched current price for {symbol}: {price}")
        return price
    logger.warning(f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}")
    return None


def fetch_klines(
    symbol: str,
    interval: str,
    limit: int,
    logger: logging.Logger,
) -> pd.DataFrame | None:
    """Fetch kline data for a symbol and interval."""
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
                f"{NEON_YELLOW}Fetched klines for {symbol} {interval} but DataFrame is empty after processing. Raw response: {response}{RESET}",
            )
            return None

        logger.debug(f"Fetched {len(df)} {interval} klines for {symbol}.")
        return df
    logger.warning(
        f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}. API response might be empty or invalid. Raw response: {response}{RESET}",
    )
    return None


def fetch_orderbook(symbol: str, limit: int, logger: logging.Logger) -> dict | None:
    """Fetch orderbook data for a symbol."""
    endpoint = "/v5/market/orderbook"
    params = {"category": "linear", "symbol": symbol, "limit": limit}
    response = bybit_request("GET", endpoint, params, logger=logger)
    if response and response["result"]:
        logger.debug(f"Fetched orderbook for {symbol} with limit {limit}.")
        return response["result"]
    logger.warning(f"{NEON_YELLOW}Could not fetch orderbook for {symbol}.{RESET}")
    return None


# --- Position Management ---
class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""

    def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str):
        """Initialize the PositionManager."""
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.open_positions: list[dict] = []  # Stores active positions
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]
        self.slippage_percent = Decimal(
            str(config["trade_management"].get("slippage_percent", 0.0)),
        )

    def _get_current_balance(self) -> Decimal:
        """Fetch current account balance (simplified for simulation)."""
        # In a real bot, this would query the exchange.
        # For simulation, use configured account balance.
        # Example API call for real balance (needs authentication):

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
                f"{NEON_YELLOW}Calculated stop loss distance is zero or negative. Cannot determine order size.{RESET}",
            )
            return Decimal("0")

        # Order size in USD value
        order_value = risk_amount / stop_loss_distance
        # Convert to quantity of the asset (e.g., BTC)
        order_qty = order_value / current_price

        # Round order_qty to appropriate precision for the symbol
        precision_str = "0." + "0" * (self.order_precision - 1) + "1"
        order_qty = order_qty.quantize(Decimal(precision_str), rounding=ROUND_DOWN)

        self.logger.info(
            f"[{self.symbol}] Calculated order size: {order_qty.normalize()} (Risk: {risk_amount.normalize():.2f} USD)",
        )
        return order_qty

    def open_position(
        self,
        signal: Literal["BUY", "SELL"],
        current_price: Decimal,
        atr_value: Decimal,
    ) -> dict | None:
        """Open a new position if conditions allow.

        Returns the new position details or None.
        """
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Trade management is disabled. Skipping opening position.{RESET}",
            )
            return None

        if len(self.open_positions) >= self.max_open_positions:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}",
            )
            return None

        order_qty = self._calculate_order_size(current_price, atr_value)
        if order_qty <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Order quantity is zero or negative. Cannot open position.{RESET}",
            )
            return None

        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"]),
        )

        if signal == "BUY":
            adjusted_entry_price = current_price * (
                Decimal("1") + self.slippage_percent
            )
            stop_loss = adjusted_entry_price - (atr_value * stop_loss_atr_multiple)
            take_profit = adjusted_entry_price + (atr_value * take_profit_atr_multiple)
        else:  # SELL
            adjusted_entry_price = current_price * (
                Decimal("1") - self.slippage_percent
            )
            stop_loss = adjusted_entry_price + (atr_value * stop_loss_atr_multiple)
            take_profit = adjusted_entry_price - (atr_value * take_profit_atr_multiple)

        price_precision_str = "0." + "0" * (self.price_precision - 1) + "1"

        position = {
            "entry_time": datetime.now(TIMEZONE),
            "symbol": self.symbol,
            "side": signal,
            "entry_price": adjusted_entry_price.quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            ),
            "qty": order_qty,
            "stop_loss": stop_loss.quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            ),
            "take_profit": take_profit.quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            ),
            "status": "OPEN",
        }
        self.open_positions.append(position)
        self.logger.info(
            f"{NEON_GREEN}[{self.symbol}] Opened {signal} position: {position}{RESET}",
        )
        return position

    def _check_and_close_position(
        self,
        position: dict,
        current_price: Decimal,
        slippage_percent: Decimal,
        price_precision: int,
        logger: logging.Logger,
    ) -> tuple[bool, Decimal, str]:
        """Helper to check if a position needs to be closed due to SL/TP."""
        side = position["side"]
        stop_loss = position["stop_loss"]
        take_profit = position["take_profit"]

        closed_by = None
        close_price = Decimal("0")

        if side == "BUY":
            if current_price <= stop_loss:
                closed_by = "STOP_LOSS"
                close_price = current_price * (Decimal("1") - slippage_percent)
            elif current_price >= take_profit:
                closed_by = "TAKE_PROFIT"
                close_price = current_price * (Decimal("1") - slippage_percent)
        elif side == "SELL":
            if current_price >= stop_loss:
                closed_by = "STOP_LOSS"
                close_price = current_price * (Decimal("1") + slippage_percent)
            elif current_price <= take_profit:
                closed_by = "TAKE_PROFIT"
                close_price = current_price * (Decimal("1") + slippage_percent)

        if closed_by:
            price_precision_str = "0." + "0" * (price_precision - 1) + "1"
            adjusted_close_price = close_price.quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            )
            return True, adjusted_close_price, closed_by
        return False, Decimal("0"), ""

    def manage_positions(
        self,
        current_price: Decimal,
        performance_tracker: Any,
    ) -> None:
        """Check and manage all open positions (SL/TP).

        In a real bot, this would interact with exchange orders.
        """
        if not self.trade_management_enabled or not self.open_positions:
            return

        positions_to_close = []
        for i, position in enumerate(self.open_positions):
            if position["status"] == "OPEN":
                is_closed, adjusted_close_price, closed_by = (
                    self._check_and_close_position(
                        position,
                        current_price,
                        self.slippage_percent,
                        self.price_precision,
                        self.logger,
                    )
                )

                if closed_by:
                    position["status"] = "CLOSED"
                    position["exit_time"] = datetime.now(TIMEZONE)
                    position["exit_price"] = adjusted_close_price
                    position["closed_by"] = closed_by
                    positions_to_close.append(i)

                    pnl = (
                        (adjusted_close_price - position["entry_price"])
                        * position["qty"]
                        if position["side"] == "BUY"
                        else (position["entry_price"] - adjusted_close_price)
                        * position["qty"]
                    )
                    performance_tracker.record_trade(position, pnl)
                    self.logger.info(
                        f"{NEON_PURPLE}[{self.symbol}] Closed {position['side']} position by {closed_by}: {position}. PnL: {pnl.normalize():.2f}{RESET}",
                    )

        # Remove closed positions
        self.open_positions = [
            pos
            for i, pos in enumerate(self.open_positions)
            if i not in positions_to_close
        ]

    def get_open_positions(self) -> list[dict]:
        """Return a list of currently open positions."""
        return [pos for pos in self.open_positions if pos["status"] == "OPEN"]


# --- Performance Tracking ---
class PerformanceTracker:
    """Tracks and reports trading performance."""

    def __init__(self, logger: logging.Logger, config: dict[str, Any]):
        """Initializes the PerformanceTracker."""
        self.logger = logger
        self.config = config
        self.trades: list[dict] = []
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0
        self.trading_fee_percent = Decimal(
            str(config["trade_management"].get("trading_fee_percent", 0.0)),
        )

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

        # Deduct fees for both entry and exit
        # Fees are calculated on the notional value (price * quantity)
        entry_fee = position["entry_price"] * position["qty"] * self.trading_fee_percent
        exit_fee = position["exit_price"] * position["qty"] * self.trading_fee_percent
        total_fees = entry_fee + exit_fee
        self.total_pnl -= total_fees

        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.logger.info(
            f"{NEON_CYAN}[{position['symbol']}] Trade recorded. PnL (before fees): {pnl.normalize():.2f}, Total Fees: {total_fees.normalize():.2f}, Current Total PnL (after fees): {self.total_pnl.normalize():.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}",
        )

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
        self.fib_levels: dict[str, Decimal] = {}  # For Fibonacci Retracement Levels
        self.weights = config["weight_sets"]["default_scalping"]
        self.indicator_settings = config["indicator_settings"]

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.{RESET}",
            )
            return

        self._calculate_all_indicators()

        if self.config["indicators"].get("fibonacci_levels", False):
            self.calculate_fibonacci_levels()
        if self.config["indicators"].get("fibonacci_pivot_points", False):
            self.calculate_fibonacci_pivot_points()

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
        """Orchestrates the calculation of all enabled technical indicators."""
        self.logger.debug(f"[{self.symbol}] Calculating technical indicators...\n")
        cfg = self.config
        isd = self.indicator_settings

        # Define indicator calculation methods and their parameters
        # (calc_func, func_kwargs, result_keys, min_data_points_override)
        # Note: 'series' argument for some functions like DEMA is passed dynamically during iteration
        indicator_map: dict[str, tuple[callable, dict, Any, int | None]] = {
            "sma_10": (
                lambda: self.df["close"].rolling(window=isd["sma_short_period"]).mean(),
                {},
                "SMA_10",
                isd["sma_short_period"],
            ),
            "sma_trend_filter": (
                lambda: self.df["close"].rolling(window=isd["sma_long_period"]).mean(),
                {},
                "SMA_Long",
                isd["sma_long_period"],
            ),
            "ema_alignment": (
                self._calculate_emas,
                {
                    "short_period": isd["ema_short_period"],
                    "long_period": isd["ema_long_period"],
                },
                ["EMA_Short", "EMA_Long"],
                max(isd["ema_short_period"], isd["ema_long_period"]),
            ),
            "atr_indicator": (
                self._calculate_atr_internal,
                {"period": isd["atr_period"]},
                "ATR",
                isd["atr_period"],
            ),  # Internal ATR calculation
            "rsi": (
                self.calculate_rsi,
                {"period": isd["rsi_period"]},
                "RSI",
                isd["rsi_period"] + 1,
            ),
            "stoch_rsi": (
                self.calculate_stoch_rsi,
                {
                    "period": isd["stoch_rsi_period"],
                    "k_period": isd["stoch_k_period"],
                    "d_period": isd["stoch_d_period"],
                },
                ["StochRSI_K", "StochRSI_D"],
                isd["stoch_rsi_period"] + isd["stoch_k_period"] + isd["stoch_d_period"],
            ),
            "bollinger_bands": (
                self.calculate_bollinger_bands,
                {
                    "period": isd["bollinger_bands_period"],
                    "std_dev": isd["bollinger_bands_std_dev"],
                },
                ["BB_Upper", "BB_Middle", "BB_Lower"],
                isd["bollinger_bands_period"],
            ),
            "cci": (
                self.calculate_cci,
                {"period": isd["cci_period"]},
                "CCI",
                isd["cci_period"],
            ),
            "wr": (
                self.calculate_williams_r,
                {"period": isd["williams_r_period"]},
                "WR",
                isd["williams_r_period"],
            ),
            "mfi": (
                self.calculate_mfi,
                {"period": isd["mfi_period"]},
                "MFI",
                isd["mfi_period"] + 1,
            ),
            "obv": (
                self.calculate_obv,
                {"ema_period": isd["obv_ema_period"]},
                ["OBV", "OBV_EMA"],
                isd["obv_ema_period"],
            ),
            "cmf": (
                self.calculate_cmf,
                {"period": isd["cmf_period"]},
                "CMF",
                isd["cmf_period"],
            ),
            "ichimoku_cloud": (
                self.calculate_ichimoku_cloud,
                {
                    "tenkan_period": isd["ichimoku_tenkan_period"],
                    "kijun_period": isd["ichimoku_kijun_period"],
                    "senkou_span_b_period": isd["ichimoku_senkou_span_b_period"],
                    "chikou_span_offset": isd["ichimoku_chikou_span_offset"],
                },
                [
                    "Tenkan_Sen",
                    "Kijun_Sen",
                    "Senkou_Span_A",
                    "Senkou_Span_B",
                    "Chikou_Span",
                ],
                max(
                    isd["ichimoku_tenkan_period"],
                    isd["ichimoku_kijun_period"],
                    isd["ichimoku_senkou_span_b_period"],
                )
                + isd["ichimoku_chikou_span_offset"],
            ),
            "psar": (
                self.calculate_psar,
                {
                    "acceleration": isd["psar_acceleration"],
                    "max_acceleration": isd["psar_max_acceleration"],
                },
                ["PSAR_Val", "PSAR_Dir"],
                MIN_DATA_POINTS_PSAR,
            ),
            "vwap": (self.calculate_vwap, {}, "VWAP", 1),
            "ehlers_supertrend": (  # Combined for easier config access, will be split internally
                self._calculate_ehlers_supertrend_internal,
                {},
                [
                    "ST_Fast_Dir",
                    "ST_Fast_Val",
                    "ST_Slow_Dir",
                    "ST_Slow_Val",
                ],  # This is a placeholder, actual assignment is inside helper
                max(isd["ehlers_fast_period"] * 3, isd["ehlers_slow_period"] * 3),
            ),
            "macd": (
                self.calculate_macd,
                {
                    "fast_period": isd["macd_fast_period"],
                    "slow_period": isd["macd_slow_period"],
                    "signal_period": isd["macd_signal_period"],
                },
                ["MACD_Line", "MACD_Signal", "MACD_Hist"],
                isd["macd_slow_period"] + isd["macd_signal_period"],
            ),
            "adx": (
                self.calculate_adx,
                {"period": isd["adx_period"]},
                ["ADX", "PlusDI", "MinusDI"],
                isd["adx_period"] * 2,
            ),
            "volatility_index": (
                self.calculate_volatility_index,
                {"period": isd["volatility_index_period"]},
                "Volatility_Index",
                isd["volatility_index_period"],
            ),
            "vwma": (
                self.calculate_vwma,
                {"period": isd["vwma_period"]},
                "VWMA",
                isd["vwma_period"],
            ),
            "volume_delta": (
                self.calculate_volume_delta,
                {"period": isd["volume_delta_period"]},
                "Volume_Delta",
                isd["volume_delta_period"],
            ),
            "kaufman_ama": (
                self.calculate_kaufman_ama,
                {
                    "period": isd["kama_period"],
                    "fast_period": isd["kama_fast_period"],
                    "slow_period": isd["kama_slow_period"],
                },
                "Kaufman_AMA",
                isd["kama_period"] + isd["kama_slow_period"],
            ),
            "relative_volume": (
                self.calculate_relative_volume,
                {"period": isd["relative_volume_period"]},
                "Relative_Volume",
                isd["relative_volume_period"],
            ),
            "market_structure": (
                self.calculate_market_structure,
                {"lookback_period": isd["market_structure_lookback_period"]},
                "Market_Structure_Trend",
                isd["market_structure_lookback_period"] * 2,
            ),
            "dema": (
                self.calculate_dema,
                {"series": self.df["close"], "period": isd["dema_period"]},
                "DEMA",
                2 * isd["dema_period"],
            ),
            "keltner_channels": (
                self.calculate_keltner_channels,
                {
                    "period": isd["keltner_period"],
                    "atr_multiplier": isd["keltner_atr_multiplier"],
                },
                ["Keltner_Upper", "Keltner_Middle", "Keltner_Lower"],
                isd["keltner_period"] + isd["atr_period"],
            ),
            "roc": (
                self.calculate_roc,
                {"period": isd["roc_period"]},
                "ROC",
                isd["roc_period"] + 1,
            ),
            "candlestick_patterns": (
                self.detect_candlestick_patterns,
                {},
                "Candlestick_Pattern",
                MIN_CANDLESTICK_PATTERNS_BARS,
            ),
        }

        for ind_key, (
            calc_func,
            func_kwargs,
            result_keys,
            min_dp,
        ) in indicator_map.items():
            if cfg["indicators"].get(ind_key, False):
                # Special handling for SuperTrend due to its multiple outputs and internal processing
                if ind_key == "ehlers_supertrend":
                    self._calculate_ehlers_supertrend_internal()  # Call the internal helper
                # Special handling for DEMA since it takes 'series' as an explicit argument
                elif ind_key == "dema":
                    result = self._safe_calculate(
                        calc_func,
                        ind_key,
                        min_data_points=min_dp,
                        series=self.df["close"],
                        period=func_kwargs["period"],
                    )
                    if result is not None:
                        self.df[result_keys] = result.reindex(self.df.index)
                        if not result.empty:
                            self.indicator_values[result_keys] = result.iloc[-1]
                else:
                    result = self._safe_calculate(
                        calc_func,
                        ind_key,
                        min_data_points=min_dp,
                        **func_kwargs,
                    )

                    if result is not None:
                        if isinstance(
                            result_keys,
                            list,
                        ):  # Multiple return values (e.g., StochRSI, BB)
                            if isinstance(result, tuple) and len(result) == len(
                                result_keys,
                            ):
                                for i, key in enumerate(result_keys):
                                    if result[i] is not None:
                                        self.df[key] = result[i].reindex(self.df.index)
                                        if not result[i].empty:
                                            self.indicator_values[key] = result[i].iloc[
                                                -1
                                            ]
                            else:
                                self.logger.warning(
                                    f"[{self.symbol}] Indicator '{ind_key}' expected {len(result_keys)} results but got {type(result)}: {result}. Skipping storage.",
                                )
                        elif isinstance(result, pd.Series):
                            self.df[result_keys] = result.reindex(self.df.index)
                            if not result.empty:
                                self.indicator_values[result_keys] = result.iloc[-1]
                        else:  # e.g., single scalar for specific patterns
                            self.df[result_keys] = pd.Series(
                                result,
                                index=self.df.index,
                            )
                            self.indicator_values[result_keys] = result

        # Final dropna after all indicators are calculated
        initial_len = len(self.df)
        self.df.dropna(subset=["close"], inplace=True)
        self.df.fillna(0, inplace=True)  # Fill any remaining NaNs in indicator columns

        if len(self.df) < initial_len:
            self.logger.debug(
                f"Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations.",
            )

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty after calculating all indicators and dropping NaNs.{RESET}",
            )
        else:
            self.logger.debug(
                f"[{self.symbol}] Indicators calculated. Final DataFrame size: {len(self.df)}",
            )

    def _calculate_emas(
        self,
        short_period: int,
        long_period: int,
    ) -> tuple[pd.Series, pd.Series]:
        """Helper to calculate multiple EMAs."""
        ema_short = self.df["close"].ewm(span=short_period, adjust=False).mean()
        ema_long = self.df["close"].ewm(span=long_period, adjust=False).mean()
        return ema_short, ema_long

    def _calculate_atr_internal(self, period: int) -> pd.Series:
        """Internal helper to calculate ATR, ensuring TR is calculated first."""
        tr = self._safe_calculate(
            self.calculate_true_range,
            "TR",
            min_data_points=MIN_DATA_POINTS_TR,
        )
        if tr is None:
            return pd.Series(np.nan, index=self.df.index)
        atr = tr.ewm(span=period, adjust=False).mean()
        return atr

    def _calculate_ehlers_supertrend_internal(self) -> None:
        """Helper to calculate both fast and slow Ehlers SuperTrend."""
        isd = self.indicator_settings

        st_fast_result = self._safe_calculate(
            self.calculate_ehlers_supertrend,
            "EhlersSuperTrendFast",
            min_data_points=isd["ehlers_fast_period"] * 3,
            period=isd["ehlers_fast_period"],
            multiplier=isd["ehlers_fast_multiplier"],
        )
        if st_fast_result is not None and not st_fast_result.empty:
            self.df["ST_Fast_Dir"] = st_fast_result["direction"]
            self.df["ST_Fast_Val"] = st_fast_result["supertrend"]
            self.indicator_values["ST_Fast_Dir"] = st_fast_result["direction"].iloc[-1]
            self.indicator_values["ST_Fast_Val"] = st_fast_result["supertrend"].iloc[-1]

        st_slow_result = self._safe_calculate(
            self.calculate_ehlers_supertrend,
            "EhlersSuperTrendSlow",
            min_data_points=isd["ehlers_slow_period"] * 3,
            period=isd["ehlers_slow_period"],
            multiplier=isd["ehlers_slow_multiplier"],
        )
        if st_slow_result is not None and not st_slow_result.empty:
            self.df["ST_Slow_Dir"] = st_slow_result["direction"]
            self.df["ST_Slow_Val"] = st_slow_result["supertrend"]
            self.indicator_values["ST_Slow_Dir"] = st_slow_result["direction"].iloc[-1]
            self.indicator_values["ST_Slow_Val"] = st_slow_result["supertrend"].iloc[-1]

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
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER_INIT:
            return pd.Series(np.nan, index=series.index)

        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER_INIT:
            return pd.Series(np.nan, index=series.index)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(0.0, index=series.index)
        if len(series) >= 1:
            filt.iloc[0] = series.iloc[0]
        if len(series) >= MIN_DATA_POINTS_SMOOTHER_INIT:
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
        if len(self.df) < period * 3:  # Need more data for smoothing and ATR
            self.logger.debug(
                f"[{self.symbol}] Not enough data for Ehlers SuperTrend (period={period}). Need at least {period * 3} bars.",
            )
            return None

        df_copy = self.df.copy()

        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)

        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr

        # Handle cases where smoothing results in too many NaNs
        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty:
            self.logger.warning(
                f"[{self.symbol}] Ehlers SuperTrend: DataFrame empty after smoothing. Returning None.",
            )
            return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        # Initialize the first valid supertrend value
        first_valid_idx_loc = 0
        while first_valid_idx_loc < len(df_copy) and pd.isna(
            df_copy["close"].iloc[first_valid_idx_loc],
        ):
            first_valid_idx_loc += 1
        if first_valid_idx_loc >= len(df_copy):
            return None  # No valid close price

        # Initialize direction based on first valid close relative to bands
        if (
            df_copy["close"].iloc[first_valid_idx_loc]
            > upper_band.iloc[first_valid_idx_loc]
        ):
            direction.iloc[first_valid_idx_loc] = 1
            supertrend.iloc[first_valid_idx_loc] = lower_band.iloc[first_valid_idx_loc]
        elif (
            df_copy["close"].iloc[first_valid_idx_loc]
            < lower_band.iloc[first_valid_idx_loc]
        ):
            direction.iloc[first_valid_idx_loc] = -1
            supertrend.iloc[first_valid_idx_loc] = upper_band.iloc[first_valid_idx_loc]
        else:
            direction.iloc[first_valid_idx_loc] = 0
            supertrend.iloc[first_valid_idx_loc] = lower_band.iloc[
                first_valid_idx_loc
            ]  # Default to lower for 'uncertain'

        for i in range(first_valid_idx_loc + 1, len(df_copy)):
            prev_direction = direction.iloc[i - 1]
            prev_supertrend = supertrend.iloc[i - 1]
            curr_close = df_copy["close"].iloc[i]

            if prev_direction == 1:  # Previous was an UP trend
                if curr_close < prev_supertrend:
                    direction.iloc[i] = -1
                    supertrend.iloc[i] = upper_band.iloc[i]
                else:
                    direction.iloc[i] = 1
                    supertrend.iloc[i] = max(lower_band.iloc[i], prev_supertrend)
            elif prev_direction == -1:  # Previous was a DOWN trend
                if curr_close > prev_supertrend:
                    direction.iloc[i] = 1
                    supertrend.iloc[i] = lower_band.iloc[i]
                else:
                    direction.iloc[i] = -1
                    supertrend.iloc[i] = min(upper_band.iloc[i], prev_supertrend)
            elif curr_close > upper_band.iloc[i]:  # Neutral to Up
                direction.iloc[i] = 1
                supertrend.iloc[i] = lower_band.iloc[i]
            elif curr_close < lower_band.iloc[i]:  # Neutral to Down
                direction.iloc[i] = -1
                supertrend.iloc[i] = upper_band.iloc[i]
            else:  # Still within bands or unable to determine a clear trend, maintain prev
                direction.iloc[i] = prev_direction
                supertrend.iloc[i] = prev_supertrend

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
        plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100

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
        vwap = cumulative_tp_vol / cumulative_vol
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
        cci = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))
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
        if (
            len(self.df)
            < max(tenkan_period, kijun_period, senkou_span_b_period)
            + chikou_span_offset
        ):
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

        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)

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
        # Use vectorized operations where possible
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

        # Initialize EP based on the initial trend (first two closes)
        ep = (
            self.df["low"].iloc[0]
            if self.df["close"].iloc[0] < self.df["close"].iloc[1]
            else self.df["high"].iloc[0]
        )
        bull.iloc[0] = (
            self.df["close"].iloc[0] < self.df["close"].iloc[1]
        )  # Initial bull direction

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

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()

        diff = recent_high - recent_low

        if diff <= 0:  # Handle cases where high and low are the same or inverted
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Invalid high-low range for Fibonacci calculation. Diff: {diff}{RESET}",
            )
            return

        price_precision_str = (
            "0." + "0" * (self.config["trade_management"]["price_precision"] - 1) + "1"
        )
        self.fib_levels = {
            "0.0%": Decimal(str(recent_high)).quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            ),
            "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            ),
            "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            ),
            "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            ),
            "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            ),
            "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            ),
            "100.0%": Decimal(str(recent_low)).quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            ),
        }
        self.logger.debug(
            f"[{self.symbol}] Calculated Fibonacci levels: {self.fib_levels}",
        )

    def calculate_fibonacci_pivot_points(self) -> None:
        """Calculate Fibonacci Pivot Points (Pivot, R1, R2, S1, S2)."""
        if self.df.empty or len(self.df) < 2:  # Need at least previous bar for pivot
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is too short for Fibonacci Pivot Points calculation.{RESET}",
            )
            return

        # Use the previous day's (or previous bar's) High, Low, Close for calculation
        prev_high = self.df["high"].iloc[-2]
        prev_low = self.df["low"].iloc[-2]
        prev_close = self.df["close"].iloc[-2]

        pivot = (prev_high + prev_low + prev_close) / 3

        # Calculate Resistance and Support Levels using Fibonacci ratios
        r1 = pivot + (prev_high - prev_low) * 0.382
        r2 = pivot + (prev_high - prev_low) * 0.618
        s1 = pivot - (prev_high - prev_low) * 0.382
        s2 = pivot - (prev_high - prev_low) * 0.618

        # Store the latest values in indicator_values
        price_precision_str = (
            "0." + "0" * (self.config["trade_management"]["price_precision"] - 1) + "1"
        )
        self.indicator_values["Pivot"] = Decimal(str(pivot)).quantize(
            Decimal(price_precision_str),
            rounding=ROUND_DOWN,
        )
        self.indicator_values["R1"] = Decimal(str(r1)).quantize(
            Decimal(price_precision_str),
            rounding=ROUND_DOWN,
        )
        self.indicator_values["R2"] = Decimal(str(r2)).quantize(
            Decimal(price_precision_str),
            rounding=ROUND_DOWN,
        )
        self.indicator_values["S1"] = Decimal(str(s1)).quantize(
            Decimal(price_precision_str),
            rounding=ROUND_DOWN,
        )
        self.indicator_values["S2"] = Decimal(str(s2)).quantize(
            Decimal(price_precision_str),
            rounding=ROUND_DOWN,
        )

        self.logger.debug(f"[{self.symbol}] Calculated Fibonacci Pivot Points.")

    def calculate_volatility_index(self, period: int) -> pd.Series:
        """Calculate a simple Volatility Index based on ATR normalized by price."""
        if len(self.df) < period or "ATR" not in self.df.columns:
            return pd.Series(np.nan, index=self.df.index)

        # ATR is already calculated in _calculate_all_indicators
        normalized_atr = self.df["ATR"] / self.df["close"]
        volatility_index = normalized_atr.rolling(window=period).mean()
        return volatility_index

    def calculate_vwma(self, period: int) -> pd.Series:
        """Calculate Volume Weighted Moving Average (VWMA)."""
        if len(self.df) < period or self.df["volume"].isnull().any():
            return pd.Series(np.nan, index=self.df.index)

        # Ensure volume is numeric and not zero
        valid_volume = self.df["volume"].replace(0, np.nan)
        pv = self.df["close"] * valid_volume
        vwma = (
            pv.rolling(window=period).sum() / valid_volume.rolling(window=period).sum()
        )
        return vwma

    def calculate_volume_delta(self, period: int) -> pd.Series:
        """Calculate Volume Delta, indicating buying vs selling pressure."""
        if len(self.df) < MIN_DATA_POINTS_SMOOTHER_INIT:
            return pd.Series(np.nan, index=self.df.index)

        # Approximate buy/sell volume based on close relative to open
        buy_volume = self.df["volume"].where(self.df["close"] > self.df["open"], 0)
        sell_volume = self.df["volume"].where(self.df["close"] < self.df["open"], 0)

        # Rolling sum of buy/sell volume
        buy_volume_sum = buy_volume.rolling(window=period, min_periods=1).sum()
        sell_volume_sum = sell_volume.rolling(window=period, min_periods=1).sum()

        total_volume_sum = buy_volume_sum + sell_volume_sum
        # Avoid division by zero
        volume_delta = (buy_volume_sum - sell_volume_sum) / total_volume_sum.replace(
            0,
            np.nan,
        )
        return volume_delta.fillna(0)

    def calculate_kaufman_ama(
        self,
        period: int,
        fast_period: int,
        slow_period: int,
    ) -> pd.Series:
        """Calculate Kaufman's Adaptive Moving Average (KAMA)."""
        if (
            len(self.df) < period + slow_period
        ):  # KAMA requires data for period, plus fast/slow EMA
            return pd.Series(np.nan, index=self.df.index)

        close_prices = self.df["close"].values
        kama = np.full_like(close_prices, np.nan)

        # Efficiency Ratio (ER)
        # Price change over the period
        price_change = np.abs(close_prices - np.roll(close_prices, period))
        price_change[:period] = (
            np.nan
        )  # First 'period' values are not valid for full 'price_change'

        # Volatility as sum of absolute differences
        # Using a rolling sum of absolute differences for volatility
        volatility_diffs = pd.Series(close_prices).diff().abs()
        # The rolling window should align with the price_change window for the ER calculation
        volatility = volatility_diffs.rolling(window=period).sum().values
        volatility[:period] = (
            np.nan
        )  # Same as price_change, first 'period' values are not valid

        er = np.full_like(close_prices, np.nan)
        for i in range(period, len(close_prices)):
            if volatility[i] == 0:
                er[i] = 0
            else:
                er[i] = price_change[i] / volatility[i]

        # Smoothing Constant (SC)
        fast_alpha = 2 / (fast_period + 1)
        slow_alpha = 2 / (slow_period + 1)
        sc = (er * (fast_alpha - slow_alpha) + slow_alpha) ** 2

        # KAMA calculation
        first_valid_idx = period
        while first_valid_idx < len(close_prices) and (
            np.isnan(close_prices[first_valid_idx]) or np.isnan(sc[first_valid_idx])
        ):
            first_valid_idx += 1

        if first_valid_idx >= len(close_prices):
            return pd.Series(np.nan, index=self.df.index)

        kama[first_valid_idx] = close_prices[first_valid_idx]

        for i in range(first_valid_idx + 1, len(close_prices)):
            if not np.isnan(sc[i]):
                kama[i] = kama[i - 1] + sc[i] * (close_prices[i] - kama[i - 1])
            else:
                kama[i] = kama[i - 1]  # If SC is NaN, hold previous KAMA value

        return pd.Series(kama, index=self.df.index)

    def calculate_relative_volume(self, period: int) -> pd.Series:
        """Calculate Relative Volume, comparing current volume to average volume."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)

        avg_volume = self.df["volume"].rolling(window=period, min_periods=period).mean()
        # Avoid division by zero
        relative_volume = (self.df["volume"] / avg_volume.replace(0, np.nan)).fillna(
            1.0,
        )  # Default to 1 if no avg volume
        return relative_volume

    def calculate_market_structure(self, lookback_period: int) -> pd.Series:
        """Detects higher highs/lows or lower highs/lows over a lookback period.

        Returns 'UP', 'DOWN', or 'SIDEWAYS'.
        """
        if (
            len(self.df) < lookback_period * 2
        ):  # Need enough data to find two swing points
            return pd.Series("UNKNOWN", index=self.df.index, dtype="object")

        # Find recent swing high and low within the last 'lookback_period' bars
        recent_segment_high = self.df["high"].iloc[-lookback_period:].max()
        recent_segment_low = self.df["low"].iloc[-lookback_period:].min()

        # Compare with previous segment's high/low
        prev_segment_high = (
            self.df["high"].iloc[-2 * lookback_period : -lookback_period].max()
        )
        prev_segment_low = (
            self.df["low"].iloc[-2 * lookback_period : -lookback_period].min()
        )

        trend = "SIDEWAYS"
        if (
            not pd.isna(recent_segment_high)
            and not pd.isna(recent_segment_low)
            and not pd.isna(prev_segment_high)
            and not pd.isna(prev_segment_low)
        ):
            is_higher_high = recent_segment_high > prev_segment_high
            is_higher_low = recent_segment_low > prev_segment_low
            is_lower_high = recent_segment_high < prev_segment_high
            is_lower_low = recent_segment_low < prev_segment_low

            if is_higher_high and is_higher_low:
                trend = "UP"
            elif is_lower_high and is_lower_low:
                trend = "DOWN"

        # Return a series where the last value is the detected trend
        result_series = pd.Series(trend, index=self.df.index, dtype="object")
        return result_series

    def calculate_dema(self, series: pd.Series, period: int) -> pd.Series:
        """Calculate Double Exponential Moving Average (DEMA)."""
        if len(series) < 2 * period:  # DEMA requires more data than simple EMA
            return pd.Series(np.nan, index=series.index)

        ema1 = series.ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        dema = 2 * ema1 - ema2
        return dema

    def calculate_keltner_channels(
        self,
        period: int,
        atr_multiplier: float,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Keltner Channels."""
        # Ensure ATR is calculated first. If not available, trigger it or return NaN.
        if "ATR" not in self.df.columns or self.df["ATR"].isnull().all():
            self.logger.debug(
                f"[{self.symbol}] ATR not available for Keltner Channels. Attempting to calculate.",
            )
            atr_series = self._calculate_atr_internal(
                self.indicator_settings["atr_period"],
            )
            if atr_series is not None and not atr_series.empty:
                self.df["ATR"] = atr_series
            else:
                return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        if (
            len(self.df) < period or self.df["ATR"].isnull().all()
        ):  # Re-check after potential ATR calculation
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema = self.df["close"].ewm(span=period, adjust=False).mean()
        atr = self.df["ATR"]  # ATR is now guaranteed to be in df and not all NaN

        upper_band = ema + (atr * atr_multiplier)
        lower_band = ema - (atr * atr_multiplier)

        return upper_band, ema, lower_band

    def calculate_roc(self, period: int) -> pd.Series:
        """Calculate Rate of Change (ROC)."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index)

        roc = (
            (self.df["close"] - self.df["close"].shift(period))
            / self.df["close"].shift(period)
        ) * 100
        return roc

    def detect_candlestick_patterns(self) -> str:
        """Detects common candlestick patterns for the latest bar.

        Returns a string like 'Bullish Engulfing', 'Bearish Hammer', or 'No Pattern'.
        """
        if (
            len(self.df) < MIN_CANDLESTICK_PATTERNS_BARS
        ):  # Need at least two bars for most patterns
            return "No Pattern"

        # Focus on the latest bar for efficiency in real-time processing
        i = len(self.df) - 1
        current_bar = self.df.iloc[i]
        prev_bar = self.df.iloc[i - 1]

        # Ensure numeric values are available
        if any(
            pd.isna(val)
            for val in [
                current_bar["open"],
                current_bar["close"],
                current_bar["high"],
                current_bar["low"],
                prev_bar["open"],
                prev_bar["close"],
                prev_bar["high"],
                prev_bar["low"],
            ]
        ):
            return "No Pattern"

        # Bullish Engulfing
        if (
            current_bar["open"] < prev_bar["close"]
            and current_bar["close"] > prev_bar["open"]
            and current_bar["close"] > current_bar["open"]
            and prev_bar["close"] < prev_bar["open"]
        ):
            return "Bullish Engulfing"
        # Bearish Engulfing
        if (
            current_bar["open"] > prev_bar["close"]
            and current_bar["close"] < prev_bar["open"]
            and current_bar["close"] < current_bar["open"]
            and prev_bar["close"] > prev_bar["open"]
        ):
            return "Bearish Engulfing"
        # Hammer (check specific characteristics like small body, long lower shadow, no or small upper shadow)
        # Assuming body is 10-20% of total range, lower shadow is 2x body, upper shadow is < 0.5x body
        if (
            current_bar["close"] > current_bar["open"]  # Bullish candle
            and abs(current_bar["close"] - current_bar["open"])
            <= (current_bar["high"] - current_bar["low"])
            * 0.3  # Small body (30% max of range)
            and (current_bar["open"] - current_bar["low"])
            >= 2
            * abs(
                current_bar["close"] - current_bar["open"],
            )  # Long lower shadow (at least 2x body)
            and (current_bar["high"] - current_bar["close"])
            <= 0.5
            * abs(
                current_bar["close"] - current_bar["open"],
            )  # Small upper shadow (less than 0.5x body)
        ):
            return "Bullish Hammer"
        # Shooting Star (similar to Hammer, but inverted for bearish)
        if (
            current_bar["close"] < current_bar["open"]  # Bearish candle
            and abs(current_bar["close"] - current_bar["open"])
            <= (current_bar["high"] - current_bar["low"])
            * 0.3  # Small body (30% max of range)
            and (current_bar["high"] - current_bar["open"])
            >= 2
            * abs(
                current_bar["close"] - current_bar["open"],
            )  # Long upper shadow (at least 2x body)
            and (current_bar["close"] - current_bar["low"])
            <= 0.5
            * abs(
                current_bar["close"] - current_bar["open"],
            )  # Small lower shadow (less than 0.5x body)
        ):
            return "Bearish Shooting Star"

        return "No Pattern"

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyze orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b[1]) for b in bids)
        ask_volume = sum(Decimal(a[1]) for a in asks)

        if bid_volume + ask_volume == 0:
            return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(
            f"[{self.symbol}] Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})",
        )
        return float(imbalance)

    def calculate_support_resistance_from_orderbook(self, orderbook_data: dict) -> None:
        """Calculates support and resistance levels from orderbook data based on volume concentration.

        Identifies the highest volume bid as support and highest volume ask as resistance.
        """
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        # Find highest volume bid (Support)
        max_bid_volume = Decimal("0")
        support_level = Decimal("0")
        for bid_price_str, bid_volume_str in bids:
            bid_volume_decimal = Decimal(bid_volume_str)
            if bid_volume_decimal > max_bid_volume:
                max_bid_volume = bid_volume_decimal
                support_level = Decimal(bid_price_str)

        # Find highest volume ask (Resistance)
        max_ask_volume = Decimal("0")
        resistance_level = Decimal("0")
        for ask_price_str, ask_volume_str in asks:
            ask_volume_decimal = Decimal(ask_volume_str)
            if ask_volume_decimal > max_ask_volume:
                max_ask_volume = ask_volume_decimal
                resistance_level = Decimal(ask_price_str)

        price_precision_str = (
            "0." + "0" * (self.config["trade_management"]["price_precision"] - 1) + "1"
        )
        if support_level > 0:
            self.indicator_values["Support_Level"] = support_level.quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            )
            self.logger.debug(
                f"[{self.symbol}] Identified Support Level: {support_level} (Volume: {max_bid_volume})",
            )
        if resistance_level > 0:
            self.indicator_values["Resistance_Level"] = resistance_level.quantize(
                Decimal(price_precision_str),
                rounding=ROUND_DOWN,
            )
            self.logger.debug(
                f"[{self.symbol}] Identified Resistance Level: {resistance_level} (Volume: {max_ask_volume})",
            )

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty:
            return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"[{self.symbol}] MTF SMA: Not enough data for {period} period. Have {len(higher_tf_df)}.",
                )
                return "UNKNOWN"
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
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"[{self.symbol}] MTF EMA: Not enough data for {period} period. Have {len(higher_tf_df)}.",
                )
                return "UNKNOWN"
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
            temp_analyzer = TradingAnalyzer(
                higher_tf_df,
                self.config,
                self.logger,
                self.symbol,
            )
            # Use slow period for trend direction in MTF
            st_result = temp_analyzer.calculate_ehlers_supertrend(
                period=self.indicator_settings["ehlers_slow_period"],
                multiplier=self.indicator_settings["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1:
                    return "UP"
                if st_dir == -1:
                    return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_data: dict | None,
        mtf_trends: dict[str, str],
    ) -> tuple[str, float, dict]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        signal_breakdown: dict[str, float] = {}
        active_indicators = self.config["indicators"]
        weights = self.weights
        isd = self.indicator_settings

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}",
            )
            return "HOLD", 0.0, {}

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(
            str(self.df["close"].iloc[-2]) if len(self.df) > 1 else current_close,
        )

        trend_strength_multiplier = 1.0  # Initialize here for ADX impact

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}",
            )
            return "HOLD", 0.0, {}

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(
            str(self.df["close"].iloc[-2]) if len(self.df) > 1 else current_close,
        )

        # ADX Alignment Scoring (Modified to influence trend_strength_multiplier)
        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            adx_weight = weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                adx_contrib = 0.0
                if adx_val > ADX_STRONG_TREND_THRESHOLD:
                    if plus_di > minus_di:
                        adx_contrib = adx_weight  # Strong confirmation of bullish trend
                        self.logger.debug(
                            f"ADX: Strong BUY trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, +DI > -DI).",
                        )
                        trend_strength_multiplier = (
                            1.2  # Boost trend-following indicators
                        )
                    elif minus_di > plus_di:
                        adx_contrib = (
                            -adx_weight
                        )  # Strong confirmation of bearish trend
                        self.logger.debug(
                            f"ADX: Strong SELL trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, -DI > +DI).",
                        )
                        trend_strength_multiplier = (
                            1.2  # Boost trend-following indicators
                        )
                elif adx_val < ADX_WEAK_TREND_THRESHOLD:
                    self.logger.debug(
                        f"ADX: Weak trend (ADX < {ADX_WEAK_TREND_THRESHOLD}). Neutral signal.",
                    )
                    trend_strength_multiplier = 0.8  # Dampen trend-following indicators
                signal_score += adx_contrib
                signal_breakdown["ADX"] = adx_contrib

        # EMA Alignment
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                ema_contrib = (
                    weights.get("ema_alignment", 0) * trend_strength_multiplier
                )
                if ema_short > ema_long:
                    signal_score += ema_contrib
                    signal_breakdown["EMA Alignment"] = ema_contrib
                elif ema_short < ema_long:
                    signal_score -= ema_contrib
                    signal_breakdown["EMA Alignment"] = -ema_contrib
                else:
                    signal_breakdown["EMA Alignment"] = 0.0

        # SMA Trend Filter
        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                sma_contrib = (
                    weights.get("sma_trend_filter", 0) * trend_strength_multiplier
                )
                if current_close > sma_long:
                    signal_score += sma_contrib
                    signal_breakdown["SMA Trend Filter"] = sma_contrib
                elif current_close < sma_long:
                    signal_score -= sma_contrib
                    signal_breakdown["SMA Trend Filter"] = -sma_contrib
                else:
                    signal_breakdown["SMA Trend Filter"] = 0.0

        # Momentum Indicators (RSI, StochRSI, CCI, WR, MFI)
        if active_indicators.get("momentum", False):
            momentum_weight = weights.get("momentum_rsi_stoch_cci_wr_mfi", 0)

            # RSI
            if active_indicators.get("rsi", False):
                rsi = self._get_indicator_value("RSI")
                if not pd.isna(rsi):
                    rsi_contrib = 0.0
                    if rsi < isd["rsi_oversold"]:
                        rsi_contrib = momentum_weight * 0.5
                    elif rsi > isd["rsi_overbought"]:
                        rsi_contrib = -momentum_weight * 0.5
                    signal_score += rsi_contrib
                    signal_breakdown["RSI"] = rsi_contrib

            # StochRSI Crossover
            if active_indicators.get("stoch_rsi", False):
                stoch_k = self._get_indicator_value("StochRSI_K")
                stoch_d = self._get_indicator_value("StochRSI_D")
                if not pd.isna(stoch_k) and not pd.isna(stoch_d) and len(self.df) > 1:
                    prev_stoch_k = self.df["StochRSI_K"].iloc[-2]
                    prev_stoch_d = self.df["StochRSI_D"].iloc[-2]
                    stoch_contrib = 0.0
                    if (
                        stoch_k > stoch_d
                        and prev_stoch_k <= prev_stoch_d
                        and stoch_k < isd["stoch_rsi_oversold"]
                    ):
                        stoch_contrib = momentum_weight * 0.6
                        self.logger.debug(
                            f"[{self.symbol}] StochRSI: Bullish crossover from oversold.",
                        )
                    elif (
                        stoch_k < stoch_d
                        and prev_stoch_k >= prev_stoch_d
                        and stoch_k > isd["stoch_rsi_overbought"]
                    ):
                        stoch_contrib = -momentum_weight * 0.6
                        self.logger.debug(
                            f"[{self.symbol}] StochRSI: Bearish crossover from overbought.",
                        )
                    elif (
                        stoch_k > stoch_d and stoch_k < STOCH_RSI_MID_POINT
                    ):  # General bullish momentum
                        stoch_contrib = momentum_weight * 0.2
                    elif (
                        stoch_k < stoch_d and stoch_k > STOCH_RSI_MID_POINT
                    ):  # General bearish momentum
                        stoch_contrib = -momentum_weight * 0.2
                    signal_score += stoch_contrib
                    signal_breakdown["StochRSI Crossover"] = stoch_contrib

            # CCI
            if active_indicators.get("cci", False):
                cci = self._get_indicator_value("CCI")
                if not pd.isna(cci):
                    cci_contrib = 0.0
                    if cci < isd["cci_oversold"]:
                        cci_contrib = momentum_weight * 0.4
                    elif cci > isd["cci_overbought"]:
                        cci_contrib = -momentum_weight * 0.4
                    signal_score += cci_contrib
                    signal_breakdown["CCI"] = cci_contrib

            if active_indicators.get("wr", False):
                wr = self._get_indicator_value("WR")
                if not pd.isna(wr):
                    wr_contrib = 0.0
                    if wr < isd["williams_r_oversold"]:
                        wr_contrib = momentum_weight * 0.4
                    elif wr > isd["williams_r_overbought"]:
                        wr_contrib = -momentum_weight * 0.4
                    signal_score += wr_contrib
                    signal_breakdown["Williams %R"] = wr_contrib

            # MFI
            if active_indicators.get("mfi", False):
                mfi = self._get_indicator_value("MFI")
                if not pd.isna(mfi):
                    mfi_contrib = 0.0
                    if mfi < isd["mfi_oversold"]:
                        mfi_contrib = momentum_weight * 0.4
                    elif mfi > isd["mfi_overbought"]:
                        mfi_contrib = -momentum_weight * 0.4
                    signal_score += mfi_contrib
                    signal_breakdown["MFI"] = mfi_contrib

        # Bollinger Bands
        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                bb_contrib = 0.0
                if current_close < bb_lower:
                    bb_contrib = weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper:
                    bb_contrib = -weights.get("bollinger_bands", 0) * 0.5
                signal_score += bb_contrib
                signal_breakdown["Bollinger Bands"] = bb_contrib

        # VWAP
        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                vwap_contrib = 0.0
                if current_close > vwap:
                    vwap_contrib = (
                        weights.get("vwap", 0) * 0.2 * trend_strength_multiplier
                    )
                elif current_close < vwap:
                    vwap_contrib = (
                        -weights.get("vwap", 0) * 0.2 * trend_strength_multiplier
                    )

                if len(self.df) > 1 and "VWAP" in self.df.columns:
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap:
                        vwap_contrib += (
                            weights.get("vwap", 0) * 0.3 * trend_strength_multiplier
                        )
                        self.logger.debug(
                            f"[{self.symbol}] VWAP: Bullish crossover detected.",
                        )
                    elif current_close < vwap and prev_close >= prev_vwap:
                        vwap_contrib -= (
                            weights.get("vwap", 0) * 0.3 * trend_strength_multiplier
                        )
                        self.logger.debug(
                            f"[{self.symbol}] VWAP: Bearish crossover detected.",
                        )
                signal_score += vwap_contrib
                signal_breakdown["VWAP"] = vwap_contrib

        # PSAR
        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                psar_contrib = 0.0
                if psar_dir == 1:
                    psar_contrib = (
                        weights.get("psar", 0) * 0.5 * trend_strength_multiplier
                    )
                elif psar_dir == -1:
                    psar_contrib = (
                        -weights.get("psar", 0) * 0.5 * trend_strength_multiplier
                    )

                if len(self.df) > 1 and "PSAR_Val" in self.df.columns:
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if current_close > psar_val and prev_close <= prev_psar_val:
                        psar_contrib += (
                            weights.get("psar", 0) * 0.4 * trend_strength_multiplier
                        )
                        self.logger.debug("PSAR: Bullish reversal detected.")
                    elif current_close < psar_val and prev_close >= prev_psar_val:
                        psar_contrib -= (
                            weights.get("psar", 0) * 0.4 * trend_strength_multiplier
                        )
                        self.logger.debug("PSAR: Bearish reversal detected.")
                signal_score += psar_contrib
                signal_breakdown["PSAR"] = psar_contrib

        # Orderbook Imbalance
        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            imbalance_contrib = imbalance * weights.get("orderbook_imbalance", 0)
            signal_score += imbalance_contrib
            signal_breakdown["Orderbook Imbalance"] = imbalance_contrib
            self.calculate_support_resistance_from_orderbook(orderbook_data)

        # Fibonacci Levels (confluence with price action)
        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            fib_contrib = 0.0
            for level_name, level_price in self.fib_levels.items():
                # Check if price is within a small percentage of a Fibonacci level
                if (
                    level_name not in ["0.0%", "100.0%"]
                    and current_price > Decimal("0")
                    and abs((current_price - level_price) / current_price)
                    < Decimal("0.001")
                ):
                    self.logger.debug(
                        f"Price near Fibonacci level {level_name}: {level_price}",
                    )
                    if len(self.df) > 1:
                        if (
                            current_close > prev_close and current_close > level_price
                        ):  # Price broke above level
                            fib_contrib += weights.get("fibonacci_levels", 0) * 0.1
                        elif (
                            current_close < prev_close and current_close < level_price
                        ):  # Price broke below level
                            fib_contrib -= weights.get("fibonacci_levels", 0) * 0.1
            signal_score += fib_contrib
            signal_breakdown["Fibonacci Levels"] = fib_contrib

        # Fibonacci Pivot Points
        if active_indicators.get("fibonacci_pivot_points", False):
            pivot = self._get_indicator_value("Pivot")
            r1 = self._get_indicator_value("R1")
            r2 = self._get_indicator_value("R2")
            s1 = self._get_indicator_value("S1")
            s2 = self._get_indicator_value("S2")

            if not any(pd.isna(val) for val in [pivot, r1, r2, s1, s2]):
                fib_pivot_contrib = weights.get("fibonacci_pivot_points_confluence", 0)

                # Bullish signals
                if current_close > r1 and prev_close <= r1:  # Break above R1
                    signal_score += fib_pivot_contrib * 0.5
                    signal_breakdown["Fibonacci R1 Breakout"] = fib_pivot_contrib * 0.5
                elif current_close > r2 and prev_close <= r2:  # Break above R2
                    signal_score += fib_pivot_contrib * 1.0
                    signal_breakdown["Fibonacci R2 Breakout"] = fib_pivot_contrib * 1.0
                elif current_close > pivot and prev_close <= pivot:  # Break above Pivot
                    signal_score += fib_pivot_contrib * 0.2
                    signal_breakdown["Fibonacci Pivot Breakout"] = (
                        fib_pivot_contrib * 0.2
                    )

                # Bearish signals
                if current_close < s1 and prev_close >= s1:  # Break below S1
                    signal_score -= fib_pivot_contrib * 0.5
                    signal_breakdown["Fibonacci S1 Breakout"] = -fib_pivot_contrib * 0.5
                elif current_close < s2 and prev_close >= s2:  # Break below S2
                    signal_score -= fib_pivot_contrib * 1.0
                    signal_breakdown["Fibonacci S2 Breakout"] = -fib_pivot_contrib * 1.0
                elif current_close < pivot and prev_close >= pivot:  # Break below Pivot
                    signal_score -= fib_pivot_contrib * 0.2
                    signal_breakdown["Fibonacci Pivot Breakdown"] = (
                        -fib_pivot_contrib * 0.2
                    )

        # Ehlers SuperTrend Alignment Scoring
        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir = (
                self.df["ST_Fast_Dir"].iloc[-2]
                if "ST_Fast_Dir" in self.df.columns and len(self.df) > 1
                else np.nan
            )
            weight = (
                weights.get("ehlers_supertrend_alignment", 0.0)
                * trend_strength_multiplier
            )

            if (
                not pd.isna(st_fast_dir)
                and not pd.isna(st_slow_dir)
                and not pd.isna(prev_st_fast_dir)
            ):
                st_contrib = 0.0
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
                    st_contrib = weight
                    self.logger.debug(
                        "Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend).",
                    )
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
                    st_contrib = -weight
                    self.logger.debug(
                        "Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend).",
                    )
                elif st_slow_dir == 1 and st_fast_dir == 1:
                    st_contrib = weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1:
                    st_contrib = -weight * 0.3
                signal_score += st_contrib
                signal_breakdown["Ehlers SuperTrend"] = st_contrib

        # MACD Alignment Scoring
        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = weights.get("macd_alignment", 0.0) * trend_strength_multiplier

            if (
                not pd.isna(macd_line)
                and not pd.isna(signal_line)
                and not pd.isna(histogram)
                and len(self.df) > 1
                and "MACD_Line" in self.df.columns
                and "MACD_Signal" in self.df.columns
            ):
                macd_contrib = 0.0
                if (
                    macd_line > signal_line
                    and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]
                ):
                    macd_contrib = weight
                    self.logger.debug(
                        "MACD: BUY signal (MACD line crossed above Signal line).",
                    )
                elif (
                    macd_line < signal_line
                    and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]
                ):
                    macd_contrib = -weight
                    self.logger.debug(
                        "MACD: SELL signal (MACD line crossed below Signal line).",
                    )
                elif histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0:
                    macd_contrib = weight * 0.2
                elif histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0:
                    macd_contrib = -weight * 0.2
                signal_score += macd_contrib
                signal_breakdown["MACD"] = macd_contrib

        # --- Ichimoku Cloud Alignment Scoring ---
        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = weights.get("ichimoku_confluence", 0.0) * trend_strength_multiplier

            if (
                not pd.isna(tenkan_sen)
                and not pd.isna(kijun_sen)
                and not pd.isna(senkou_span_a)
                and not pd.isna(senkou_span_b)
                and not pd.isna(chikou_span)
                and len(self.df) > 1
                and "Tenkan_Sen" in self.df.columns
                and "Kijun_Sen" in self.df.columns
                and "Senkou_Span_A" in self.df.columns
                and "Senkou_Span_B" in self.df.columns
                and "Chikou_Span" in self.df.columns
            ):
                ichimoku_contrib = 0.0
                if (
                    tenkan_sen > kijun_sen
                    and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]
                ):
                    ichimoku_contrib = weight * 0.5
                    self.logger.debug(
                        "Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish).",
                    )
                elif (
                    tenkan_sen < kijun_sen
                    and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]
                ):
                    ichimoku_contrib = -weight * 0.5
                    self.logger.debug(
                        "Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish).",
                    )

                if current_close > max(senkou_span_a, senkou_span_b) and self.df[
                    "close"
                ].iloc[-2] <= max(
                    self.df["Senkou_Span_A"].iloc[-2],
                    self.df["Senkou_Span_B"].iloc[-2],
                ):
                    ichimoku_contrib += weight * 0.7
                    self.logger.debug(
                        "Ichimoku: Price broke above Kumo (strong bullish).",
                    )
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df[
                    "close"
                ].iloc[-2] >= min(
                    self.df["Senkou_Span_A"].iloc[-2],
                    self.df["Senkou_Span_B"].iloc[-2],
                ):
                    ichimoku_contrib -= weight * 0.7
                    self.logger.debug(
                        "Ichimoku: Price broke below Kumo (strong bearish).",
                    )

                if (
                    chikou_span > current_close
                    and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]
                ):
                    ichimoku_contrib += weight * 0.3
                    self.logger.debug(
                        "Ichimoku: Chikou Span crossed above price (bullish confirmation).",
                    )
                elif (
                    chikou_span < current_close
                    and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]
                ):
                    ichimoku_contrib -= weight * 0.3
                    self.logger.debug(
                        "Ichimoku: Chikou Span crossed below price (bearish confirmation).",
                    )
                signal_score += ichimoku_contrib
                signal_breakdown["Ichimoku Cloud"] = ichimoku_contrib

        # --- OBV Alignment Scoring ---
        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)

            if (
                not pd.isna(obv_val)
                and not pd.isna(obv_ema)
                and len(self.df) > 1
                and "OBV" in self.df.columns
                and "OBV_EMA" in self.df.columns
            ):
                obv_contrib = 0.0
                if (
                    obv_val > obv_ema
                    and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]
                ):
                    obv_contrib = weight * 0.5
                    self.logger.debug("OBV: Bullish crossover detected.")
                elif (
                    obv_val < obv_ema
                    and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]
                ):
                    obv_contrib = -weight * 0.5
                    self.logger.debug("OBV: Bearish crossover detected.")

                if len(self.df) > 2:
                    if (
                        obv_val > self.df["OBV"].iloc[-2]
                        and obv_val > self.df["OBV"].iloc[-3]
                    ):
                        obv_contrib += weight * 0.2
                    elif (
                        obv_val < self.df["OBV"].iloc[-2]
                        and obv_val < self.df["OBV"].iloc[-3]
                    ):
                        obv_contrib -= weight * 0.2
                signal_score += obv_contrib
                signal_breakdown["OBV"] = obv_contrib

        # --- CMF Alignment Scoring ---
        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)

            if not pd.isna(cmf_val):
                cmf_contrib = 0.0
                if cmf_val > 0:
                    cmf_contrib = weight * 0.5
                elif cmf_val < 0:
                    cmf_contrib = -weight * 0.5

                if len(self.df) > 2 and "CMF" in self.df.columns:
                    if (
                        cmf_val > self.df["CMF"].iloc[-2]
                        and cmf_val > self.df["CMF"].iloc[-3]
                    ):
                        cmf_contrib += weight * 0.3
                    elif (
                        cmf_val < self.df["CMF"].iloc[-2]
                        and cmf_val < self.df["CMF"].iloc[-3]
                    ):
                        cmf_contrib -= weight * 0.3
                signal_score += cmf_contrib
                signal_breakdown["CMF"] = cmf_contrib

        # --- Volatility Index Scoring ---
        if active_indicators.get("volatility_index", False):
            vol_idx = self._get_indicator_value("Volatility_Index")
            weight = weights.get("volatility_index_signal", 0.0)
            if not pd.isna(vol_idx):
                vol_contrib = 0.0
                if len(self.df) > 2 and "Volatility_Index" in self.df.columns:
                    prev_vol_idx = self.df["Volatility_Index"].iloc[-2]
                    prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3]

                    if (
                        vol_idx > prev_vol_idx > prev_prev_vol_idx
                    ):  # Increasing volatility
                        if signal_score > 0:
                            vol_contrib = weight * 0.2
                        elif signal_score < 0:
                            vol_contrib = -weight * 0.2
                    elif (
                        vol_idx < prev_vol_idx < prev_prev_vol_idx
                    ):  # Decreasing volatility
                        if abs(signal_score) > 0:
                            vol_contrib = signal_score * -0.2
                signal_score += vol_contrib
                signal_breakdown["Volatility Index"] = vol_contrib

        # --- VWMA Cross Scoring ---
        if active_indicators.get("vwma", False):
            vwma = self._get_indicator_value("VWMA")
            weight = weights.get("vwma_cross", 0.0)
            if not pd.isna(vwma) and len(self.df) > 1 and "VWMA" in self.df.columns:
                vwma_contrib = 0.0
                prev_vwma = self.df["VWMA"].iloc[-2]
                if current_close > vwma and prev_close <= prev_vwma:
                    vwma_contrib = weight * trend_strength_multiplier
                    self.logger.debug("VWMA: Bullish crossover (price above VWMA).")
                elif current_close < vwma and prev_close >= prev_vwma:
                    vwma_contrib = -weight * trend_strength_multiplier
                    self.logger.debug("VWMA: Bearish crossover (price below VWMA).")
                signal_score += vwma_contrib
                signal_breakdown["VWMA Cross"] = vwma_contrib

        # --- Volume Delta Scoring ---
        if active_indicators.get("volume_delta", False):
            volume_delta = self._get_indicator_value("Volume_Delta")
            volume_delta_threshold = isd["volume_delta_threshold"]
            weight = weights.get("volume_delta_signal", 0.0)

            if not pd.isna(volume_delta):
                vol_delta_contrib = 0.0
                if volume_delta > volume_delta_threshold:  # Strong buying pressure
                    vol_delta_contrib = weight
                    self.logger.debug("Volume Delta: Strong buying pressure detected.")
                elif volume_delta < -volume_delta_threshold:  # Strong selling pressure
                    vol_delta_contrib = -weight
                    self.logger.debug("Volume Delta: Strong selling pressure detected.")
                elif volume_delta > 0:
                    vol_delta_contrib = weight * 0.3
                elif volume_delta < 0:
                    vol_delta_contrib = -weight * 0.3
                signal_score += vol_delta_contrib
                signal_breakdown["Volume Delta"] = vol_delta_contrib

        # --- Kaufman AMA Cross Scoring ---
        if active_indicators.get("kaufman_ama", False):
            kama = self._get_indicator_value("Kaufman_AMA")
            weight = weights.get("kaufman_ama_cross", 0.0)
            if (
                not pd.isna(kama)
                and len(self.df) > 1
                and "Kaufman_AMA" in self.df.columns
            ):
                kama_contrib = 0.0
                prev_kama = self.df["Kaufman_AMA"].iloc[-2]
                if current_close > kama and prev_close <= prev_kama:
                    kama_contrib = weight * trend_strength_multiplier
                    self.logger.debug("KAMA: Bullish crossover (price above KAMA).")
                elif current_close < kama and prev_close >= prev_kama:
                    kama_contrib = -weight * trend_strength_multiplier
                    self.logger.debug("KAMA: Bearish crossover (price below KAMA).")
                signal_score += kama_contrib
                signal_breakdown["Kaufman AMA Cross"] = kama_contrib

        # Relative Volume Confirmation
        if active_indicators.get("relative_volume", False):
            relative_volume = self._get_indicator_value("Relative_Volume")
            volume_threshold = isd["relative_volume_threshold"]
            weight = weights.get("relative_volume_confirmation", 0.0)

            if not pd.isna(relative_volume):
                rv_contrib = 0.0
                if relative_volume >= volume_threshold:  # Significantly higher volume
                    if current_close > prev_close:  # Bullish bar with high volume
                        rv_contrib = weight
                        self.logger.debug(
                            f"Volume: High relative bullish volume ({relative_volume:.2f}x average).",
                        )
                    elif current_close < prev_close:  # Bearish bar with high volume
                        rv_contrib = -weight
                        self.logger.debug(
                            f"Volume: High relative bearish volume ({relative_volume:.2f}x average).",
                        )
                signal_score += rv_contrib
                signal_breakdown["Relative Volume"] = rv_contrib

        # Market Structure Confluence
        if active_indicators.get("market_structure", False):
            ms_trend = self._get_indicator_value("Market_Structure_Trend", "SIDEWAYS")
            weight = weights.get("market_structure_confluence", 0.0)

            if ms_trend == "UP":
                ms_contrib = weight * trend_strength_multiplier
                self.logger.debug("Market Structure: Confirmed Uptrend.")
            elif ms_trend == "DOWN":
                ms_contrib = -weight * trend_strength_multiplier
                self.logger.debug("Market Structure: Confirmed Downtrend.")
            else:
                ms_contrib = 0.0
            signal_score += ms_contrib
            signal_breakdown["Market Structure"] = ms_contrib

        # DEMA Crossover with EMA_Short (example signal)
        if active_indicators.get("dema", False) and active_indicators.get(
            "ema_alignment",
            False,
        ):
            dema = self._get_indicator_value("DEMA")
            ema_short = self._get_indicator_value("EMA_Short")
            weight = weights.get("dema_crossover", 0.0)

            if (
                not pd.isna(dema)
                and not pd.isna(ema_short)
                and len(self.df) > 1
                and "DEMA" in self.df.columns
                and "EMA_Short" in self.df.columns
            ):
                dema_contrib = 0.0
                prev_dema = self.df["DEMA"].iloc[-2]
                prev_ema_short = self.df["EMA_Short"].iloc[-2]

                if dema > ema_short and prev_dema <= prev_ema_short:
                    dema_contrib = weight * trend_strength_multiplier
                    self.logger.debug("DEMA: Bullish crossover (DEMA above EMA_Short).")
                elif dema < ema_short and prev_dema >= prev_ema_short:
                    dema_contrib = -weight * trend_strength_multiplier
                    self.logger.debug("DEMA: Bearish crossover (DEMA below EMA_Short).")
                signal_score += dema_contrib
                signal_breakdown["DEMA Crossover"] = dema_contrib

        # Keltner Channel Breakout
        if active_indicators.get("keltner_channels", False):
            kc_upper = self._get_indicator_value("Keltner_Upper")
            kc_lower = self._get_indicator_value("Keltner_Lower")
            weight = weights.get("keltner_breakout", 0.0)

            if (
                not pd.isna(kc_upper)
                and not pd.isna(kc_lower)
                and len(self.df) > 1
                and "Keltner_Upper" in self.df.columns
                and "Keltner_Lower" in self.df.columns
            ):
                kc_contrib = 0.0
                if (
                    current_close > kc_upper
                    and prev_close <= self.df["Keltner_Upper"].iloc[-2]
                ):
                    kc_contrib = weight
                    self.logger.debug(
                        "Keltner Channels: Bullish breakout above upper channel.",
                    )
                elif (
                    current_close < kc_lower
                    and prev_close >= self.df["Keltner_Lower"].iloc[-2]
                ):
                    kc_contrib = -weight
                    self.logger.debug(
                        "Keltner Channels: Bearish breakout below lower channel.",
                    )
                signal_score += kc_contrib
                signal_breakdown["Keltner Channels"] = kc_contrib

        # ROC Signals
        if active_indicators.get("roc", False):
            roc = self._get_indicator_value("ROC")
            weight = weights.get("roc_signal", 0.0)

            if not pd.isna(roc):
                roc_contrib = 0.0
                if roc < isd["roc_oversold"]:
                    roc_contrib = weight * 0.7  # Bullish signal from oversold
                    self.logger.debug(f"ROC: Oversold ({roc:.2f}), potential bounce.")
                elif roc > isd["roc_overbought"]:
                    roc_contrib = -weight * 0.7  # Bearish signal from overbought
                    self.logger.debug(
                        f"ROC: Overbought ({roc:.2f}), potential pullback.",
                    )

                # Zero-line crossover (simple trend indication)
                if len(self.df) > 1 and "ROC" in self.df.columns:
                    prev_roc = self.df["ROC"].iloc[-2]
                    if roc > 0 and prev_roc <= 0:
                        roc_contrib += (
                            weight * 0.3 * trend_strength_multiplier
                        )  # Bullish zero-line cross
                        self.logger.debug("ROC: Bullish zero-line crossover.")
                    elif roc < 0 and prev_roc >= 0:
                        roc_contrib -= (
                            weight * 0.3 * trend_strength_multiplier
                        )  # Bearish zero-line cross
                        self.logger.debug("ROC: Bearish zero-line crossover.")
                signal_score += roc_contrib
                signal_breakdown["ROC"] = roc_contrib

        # Candlestick Pattern Confirmation
        if active_indicators.get("candlestick_patterns", False):
            pattern = self._get_indicator_value("Candlestick_Pattern", "No Pattern")
            weight = weights.get("candlestick_confirmation", 0.0)

            if pattern in ["Bullish Engulfing", "Bullish Hammer"]:
                cp_contrib = weight
                self.logger.debug(f"Candlestick: Detected Bullish Pattern ({pattern}).")
            elif pattern in ["Bearish Engulfing", "Bearish Shooting Star"]:
                cp_contrib = -weight
                self.logger.debug(f"Candlestick: Detected Bearish Pattern ({pattern}).")
            else:
                cp_contrib = 0.0
            signal_score += cp_contrib
            signal_breakdown["Candlestick Pattern"] = cp_contrib

        # Multi-Timeframe Trend Confluence Scoring (Modified)
        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_count = 0
            mtf_sell_count = 0
            total_mtf_indicators = len(mtf_trends)

            for _tf_indicator, trend in mtf_trends.items():
                if trend == "UP":
                    mtf_buy_count += 1
                elif trend == "DOWN":
                    mtf_sell_count += 1

            mtf_weight = weights.get("mtf_trend_confluence", 0.0)
            mtf_contribution = 0.0

            if total_mtf_indicators > 0:
                if mtf_buy_count == total_mtf_indicators:  # All TFs agree bullish
                    mtf_contribution = mtf_weight * 1.5  # Stronger boost
                    self.logger.debug(
                        f"MTF: All {total_mtf_indicators} higher TFs are UP. Strong bullish confluence.",
                    )
                elif mtf_sell_count == total_mtf_indicators:  # All TFs agree bearish
                    mtf_contribution = -mtf_weight * 1.5  # Stronger penalty
                    self.logger.debug(
                        f"MTF: All {total_mtf_indicators} higher TFs are DOWN. Strong bearish confluence.",
                    )
                else:  # Mixed or some agreement
                    normalized_mtf_score = (
                        mtf_buy_count - mtf_sell_count
                    ) / total_mtf_indicators
                    mtf_contribution = (
                        mtf_weight * normalized_mtf_score
                    )  # Proportional score

                signal_score += mtf_contribution
                signal_breakdown["MTF Confluence"] = mtf_contribution
                self.logger.debug(
                    f"MTF Confluence: Buy: {mtf_buy_count}, Sell: {mtf_sell_count}. MTF contribution: {mtf_contribution:.2f}",
                )

        # --- Final Signal Determination ---
        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold:
            final_signal = "BUY"
        elif signal_score <= -threshold:
            final_signal = "SELL"

        self.logger.info(
            f"{NEON_YELLOW}Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}",
        )
        return final_signal, signal_score, signal_breakdown

    def calculate_entry_tp_sl(
        self,
        current_price: Decimal,
        atr_value: Decimal,
        signal: Literal["BUY", "SELL"],
    ) -> tuple[Decimal, Decimal]:
        """Calculate Take Profit and Stop Loss levels."""
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"]),
        )
        price_precision_str = (
            "0." + "0" * (self.config["trade_management"]["price_precision"] - 1) + "1"
        )

        if signal == "BUY":
            stop_loss = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit = current_price + (atr_value * take_profit_atr_multiple)
        elif signal == "SELL":
            stop_loss = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit = current_price - (atr_value * take_profit_atr_multiple)
        else:
            return Decimal("0"), Decimal("0")  # Should not happen for valid signals

        return take_profit.quantize(
            Decimal(price_precision_str),
            rounding=ROUND_DOWN,
        ), stop_loss.quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)


def display_indicator_values_and_price(
    config: dict[str, Any],
    logger: logging.Logger,
    current_price: Decimal,
    analyzer: TradingAnalyzer,  # Pass the analyzer instance directly
    orderbook_data: dict | None,
    mtf_trends: dict[str, str],
    signal_breakdown: dict[str, float] | None = None,
) -> None:
    """Display current price and calculated indicator values."""
    logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
    logger.info(f"{NEON_GREEN}Current Price: {current_price.normalize()}{RESET}")

    if analyzer.df.empty:
        logger.warning(
            f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.{RESET}",
        )
        return

    logger.info(f"{NEON_CYAN}--- Indicator Values ---{RESET}")
    for indicator_name, value in analyzer.indicator_values.items():
        color = INDICATOR_COLORS.get(indicator_name, NEON_YELLOW)
        # Format Decimal values for consistent display
        if isinstance(value, Decimal):
            logger.info(f"  {color}{indicator_name:<20}: {value.normalize()}{RESET}")
        elif isinstance(value, float):
            logger.info(f"  {color}{indicator_name:<20}: {value:.8f}{RESET}")
        else:
            logger.info(f"  {color}{indicator_name:<20}: {value}{RESET}")

    if analyzer.fib_levels:
        logger.info(f"{NEON_CYAN}--- Fibonacci Retracement Levels ---{RESET}")
        for level_name, level_price in analyzer.fib_levels.items():
            logger.info(
                f"  {NEON_YELLOW}{level_name:<20}: {level_price.normalize()}{RESET}",
            )

    # Display Fibonacci Pivot Points
    if config["indicators"].get("fibonacci_pivot_points", False):
        if (
            "Pivot" in analyzer.indicator_values
            and "R1" in analyzer.indicator_values
            and "S1" in analyzer.indicator_values
        ):
            logger.info(f"{NEON_CYAN}--- Fibonacci Pivot Points ---{RESET}")
            logger.info(
                f"  {INDICATOR_COLORS.get('Pivot', NEON_YELLOW)}Pivot              : {analyzer.indicator_values['Pivot'].normalize()}{RESET}",
            )
            logger.info(
                f"  {INDICATOR_COLORS.get('R1', NEON_GREEN)}R1                 : {analyzer.indicator_values['R1'].normalize()}{RESET}",
            )
            logger.info(
                f"  {INDICATOR_COLORS.get('R2', NEON_GREEN)}R2                 : {analyzer.indicator_values['R2'].normalize()}{RESET}",
            )
            logger.info(
                f"  {INDICATOR_COLORS.get('S1', NEON_RED)}S1                 : {analyzer.indicator_values['S1'].normalize()}{RESET}",
            )
            logger.info(
                f"  {INDICATOR_COLORS.get('S2', NEON_RED)}S2                 : {analyzer.indicator_values['S2'].normalize()}{RESET}",
            )

    # Display Support and Resistance Levels (from orderbook)
    if (
        "Support_Level" in analyzer.indicator_values
        or "Resistance_Level" in analyzer.indicator_values
    ):
        logger.info(f"{NEON_CYAN}--- Orderbook S/R Levels ---{RESET}")
        if "Support_Level" in analyzer.indicator_values:
            logger.info(
                f"  {INDICATOR_COLORS.get('Support_Level', NEON_YELLOW)}Support Level     : {analyzer.indicator_values['Support_Level'].normalize()}{RESET}",
            )
        if "Resistance_Level" in analyzer.indicator_values:
            logger.info(
                f"  {INDICATOR_COLORS.get('Resistance_Level', NEON_YELLOW)}Resistance Level  : {analyzer.indicator_values['Resistance_Level'].normalize()}{RESET}",
            )

    if mtf_trends:
        logger.info(f"{NEON_CYAN}--- Multi-Timeframe Trends ---{RESET}")
        for tf_indicator, trend in mtf_trends.items():
            logger.info(f"  {NEON_YELLOW}{tf_indicator:<20}: {trend}{RESET}")

    if signal_breakdown:
        logger.info(f"{NEON_CYAN}--- Signal Score Breakdown ---{RESET}")
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

    # Concise Trend Summary
    logger.info(f"{NEON_PURPLE}--- Current Trend Summary ---{RESET}")
    trend_summary_lines = []

    # EMA Alignment
    ema_short = analyzer._get_indicator_value("EMA_Short")
    ema_long = analyzer._get_indicator_value("EMA_Long")
    if not pd.isna(ema_short) and not pd.isna(ema_long):
        if ema_short > ema_long:
            trend_summary_lines.append(f"{Fore.GREEN}EMA Cross  : ▲ Up{RESET}")
        elif ema_short < ema_long:
            trend_summary_lines.append(f"{Fore.RED}EMA Cross  : ▼ Down{RESET}")
        else:
            trend_summary_lines.append(f"{Fore.YELLOW}EMA Cross  : ↔ Sideways{RESET}")

    # Ehlers SuperTrend (Slow)
    st_slow_dir = analyzer._get_indicator_value("ST_Slow_Dir")
    if not pd.isna(st_slow_dir):
        if st_slow_dir == 1:
            trend_summary_lines.append(f"{Fore.GREEN}SuperTrend : ▲ Up{RESET}")
        elif st_slow_dir == -1:
            trend_summary_lines.append(f"{Fore.RED}SuperTrend : ▼ Down{RESET}")
        else:
            trend_summary_lines.append(f"{Fore.YELLOW}SuperTrend : ↔ Sideways{RESET}")

    # MACD Histogram (momentum)
    macd_hist = analyzer._get_indicator_value("MACD_Hist")
    if not pd.isna(macd_hist):
        if "MACD_Hist" in analyzer.df.columns and len(analyzer.df) > 1:
            prev_macd_hist = analyzer.df["MACD_Hist"].iloc[-2]
            if macd_hist > 0 and prev_macd_hist <= 0:
                trend_summary_lines.append(
                    f"{Fore.GREEN}MACD Hist  : ↑ Bullish Cross{RESET}",
                )
            elif macd_hist < 0 and prev_macd_hist >= 0:
                trend_summary_lines.append(
                    f"{Fore.RED}MACD Hist  : ↓ Bearish Cross{RESET}",
                )
            elif macd_hist > 0:
                trend_summary_lines.append(
                    f"{Fore.LIGHTGREEN_EX}MACD Hist  : Above 0{RESET}",
                )
            elif macd_hist < 0:
                trend_summary_lines.append(
                    f"{Fore.LIGHTRED_EX}MACD Hist  : Below 0{RESET}",
                )
        else:
            trend_summary_lines.append(f"{Fore.YELLOW}MACD Hist  : N/A{RESET}")

    # ADX Strength
    adx_val = analyzer._get_indicator_value("ADX")
    if not pd.isna(adx_val):
        if adx_val > ADX_STRONG_TREND_THRESHOLD:
            plus_di = analyzer._get_indicator_value("PlusDI")
            minus_di = analyzer._get_indicator_value("MinusDI")
            if not pd.isna(plus_di) and not pd.isna(minus_di):
                if plus_di > minus_di:
                    trend_summary_lines.append(
                        f"{Fore.LIGHTGREEN_EX}ADX Trend  : Strong Up ({adx_val:.0f}){RESET}",
                    )
                else:
                    trend_summary_lines.append(
                        f"{Fore.LIGHTRED_EX}ADX Trend  : Strong Down ({adx_val:.0f}){RESET}",
                    )
        elif adx_val < ADX_WEAK_TREND_THRESHOLD:
            trend_summary_lines.append(
                f"{Fore.YELLOW}ADX Trend  : Weak/Ranging ({adx_val:.0f}){RESET}",
            )
        else:
            trend_summary_lines.append(
                f"{Fore.CYAN}ADX Trend  : Moderate ({adx_val:.0f}){RESET}",
            )

    # Ichimoku Cloud (Kumo position)
    senkou_span_a = analyzer._get_indicator_value("Senkou_Span_A")
    senkou_span_b = analyzer._get_indicator_value("Senkou_Span_B")
    if not pd.isna(senkou_span_a) and not pd.isna(senkou_span_b):
        kumo_upper = max(senkou_span_a, senkou_span_b)
        kumo_lower = min(senkou_span_a, senkou_span_b)
        if current_price > kumo_upper:
            trend_summary_lines.append(f"{Fore.GREEN}Ichimoku   : Above Kumo{RESET}")
        elif current_price < kumo_lower:
            trend_summary_lines.append(f"{Fore.RED}Ichimoku   : Below Kumo{RESET}")
        else:
            trend_summary_lines.append(f"{Fore.YELLOW}Ichimoku   : Inside Kumo{RESET}")

    # MTF Confluence
    if mtf_trends:
        up_count = sum(1 for t in mtf_trends.values() if t == "UP")
        down_count = sum(1 for t in mtf_trends.values() if t == "DOWN")
        total = len(mtf_trends)
        if total > 0:
            if up_count == total:
                trend_summary_lines.append(
                    f"{Fore.GREEN}MTF Confl. : All Bullish ({up_count}/{total}){RESET}",
                )
            elif down_count == total:
                trend_summary_lines.append(
                    f"{Fore.RED}MTF Confl. : All Bearish ({down_count}/{total}){RESET}",
                )
            elif up_count > down_count:
                trend_summary_lines.append(
                    f"{Fore.LIGHTGREEN_EX}MTF Confl. : Mostly Bullish ({up_count}/{total}){RESET}",
                )
            elif down_count > up_count:
                trend_summary_lines.append(
                    f"{Fore.LIGHTRED_EX}MTF Confl. : Mostly Bearish ({down_count}/{total}){RESET}",
                )
            else:
                trend_summary_lines.append(
                    f"{Fore.YELLOW}MTF Confl. : Mixed ({up_count}/{total} Bull, {down_count}/{total} Bear){RESET}",
                )

    # Print the summary lines
    for line in trend_summary_lines:
        logger.info(f"  {line}")

    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")


# --- Main Execution Logic ---
def main() -> None:
    """Orchestrate the bot's operation."""
    logger = setup_logger("wgwhalex_bot")
    config = load_config(CONFIG_FILE, logger)
    alert_system = AlertSystem(logger)

    # Validate interval format at startup
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

    position_manager = PositionManager(config, logger, config["symbol"])
    performance_tracker = PerformanceTracker(logger, config)

    while True:
        try:
            logger.info(
                f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}",
            )
            current_price = fetch_current_price(config["symbol"], logger)

            # Initialize signal variables for the current loop iteration
            trading_signal = "HOLD"
            signal_score = 0.0
            signal_breakdown = {}
            if current_price is None:
                alert_system.send_alert(
                    f"[{config['symbol']}] Failed to fetch current price. Skipping loop.",
                    "WARNING",
                )
                time.sleep(config["loop_delay"])
                continue

            df = fetch_klines(config["symbol"], config["interval"], 1000, logger)
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
                )

            mtf_trends: dict[str, str] = {}
            if config["mtf_analysis"]["enabled"]:
                for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                    logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
                    htf_df = fetch_klines(config["symbol"], htf_interval, 1000, logger)
                    if htf_df is not None and not htf_df.empty:
                        for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                            temp_htf_analyzer = TradingAnalyzer(
                                htf_df,
                                config,
                                logger,
                                config["symbol"],
                            )
                            trend = temp_htf_analyzer._get_mtf_trend(
                                temp_htf_analyzer.df,
                                trend_ind,
                            )
                            mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                            logger.debug(
                                f"MTF Trend ({htf_interval}, {trend_ind}): {trend}",
                            )
                    else:
                        logger.warning(
                            f"{NEON_YELLOW}Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}",
                        )
                    time.sleep(
                        config["mtf_analysis"]["mtf_request_delay_seconds"],
                    )  # Delay between MTF requests

            analyzer = TradingAnalyzer(df, config, logger, config["symbol"])

            if analyzer.df.empty:
                alert_system.send_alert(
                    f"[{config['symbol']}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                    "WARNING",
                )
                time.sleep(config["loop_delay"])
                continue

            trading_signal, signal_score, signal_breakdown = (
                analyzer.generate_trading_signal(
                    current_price,
                    orderbook_data,
                    mtf_trends,
                )
            )
            atr_value = Decimal(
                str(analyzer._get_indicator_value("ATR", Decimal("0.01"))),
            )

            display_indicator_values_and_price(
                config,
                logger,
                current_price,
                analyzer,  # Pass the analyzer instance
                orderbook_data,
                mtf_trends,
                signal_breakdown,
            )

            position_manager.manage_positions(current_price, performance_tracker)

            if (
                trading_signal == "BUY"
                and signal_score >= config["signal_score_threshold"]
            ):
                logger.info(
                    f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}{RESET}",
                )
                position_manager.open_position("BUY", current_price, atr_value)
            elif (
                trading_signal == "SELL"
                and signal_score <= -config["signal_score_threshold"]
            ):
                logger.info(
                    f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}{RESET}",
                )
                position_manager.open_position("SELL", current_price, atr_value)
            else:
                logger.info(
                    f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}",
                )

            open_positions = position_manager.get_open_positions()
            if open_positions:
                logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}")
                for pos in open_positions:
                    logger.info(
                        f"  - {pos['side']} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}){RESET}",
                    )
            else:
                logger.info(f"{NEON_CYAN}No open positions.{RESET}")

            perf_summary = performance_tracker.get_summary()
            logger.info(
                f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}",
            )

            logger.info(
                f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}",
            )
            time.sleep(config["loop_delay"])

        except Exception as e:
            alert_system.send_alert(
                f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}",
                "ERROR",
            )
            logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
            time.sleep(config["loop_delay"] * 2)


if __name__ == "__main__":
    main()
