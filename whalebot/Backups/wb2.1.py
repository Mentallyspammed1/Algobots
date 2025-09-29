import asyncio
import hashlib
import hmac
import json
import logging
import os
import sys
import time
import warnings
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import (
    Any,
    ClassVar,
    Literal,
)

import httpx  # For asynchronous HTTP requests
import numpy as np
import pandas as pd
import pandas_ta as ta
from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# Suppress warnings from libraries like pandas_ta
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# Initialize colorama and set decimal precision
getcontext().prec = 28  # High precision for financial calculations
init(autoreset=True)
load_dotenv()

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
WS_RECONNECT_DELAY_SECONDS = 5
API_CALL_RETRY_DELAY_SECONDS = 3

# Magic Numbers as Constants (expanded and named for clarity)
MIN_DATA_POINTS_TRUE_RANGE = 2
MIN_DATA_POINTS_SUPERSMOOTHER = 2
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR_INITIAL = 4  # PSAR needs a few points to initialize reliably
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20
MIN_DATA_POINTS_VWMA = 2
MIN_DATA_POINTS_VOLATILITY = 2
MIN_DATA_POINTS_VOLUME_DELTA = (
    2  # Volume Delta needs at least 2 bars (current and previous)
)

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
}


# --- Configuration Management ---
def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    """Load configuration from JSON file, creating a default if not found."""
    default_config = {
        # Core Settings
        "symbol": "BTCUSDT",
        "interval": "15",
        "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50,
        "testnet": True,
        "timezone": "America/Chicago",
        # Signal Generation
        "signal_score_threshold": 2.0,
        "volume_confirmation_multiplier": 1.5,
        # Position & Risk Management
        "trade_management": {
            "enabled": True,
            "account_balance": 10.0,  # Simulated balance if not using real API
            "risk_per_trade_percent": 1.0,  # Percentage of account_balance to risk
            "stop_loss_atr_multiple": 1.5,  # Stop loss distance as multiple of ATR
            "take_profit_atr_multiple": 2.0,  # Take profit distance as multiple of ATR
            "trailing_stop_atr_multiple": 0.3,  # Trailing stop distance as multiple of ATR
            "max_open_positions": 1,
            "order_precision": 4,  # Decimal places for order quantity (fallback)
            "price_precision": 2,  # Decimal places for price (fallback)
            "leverage": 10,  # Leverage for perpetual contracts
            "order_mode": "MARKET",  # MARKET or LIMIT for entry orders
            "take_profit_type": "MARKET",  # MARKET or LIMIT for TP
            "stop_loss_type": "MARKET",  # MARKET or LIMIT for SL
            "trailing_stop_activation_percent": 0.5,  # % profit to activate trailing stop
            "trailing_stop_trigger_by": "LastPrice",  # Index price or Last price for TS
        },
        # Multi-Timeframe Analysis
        "mtf_analysis": {
            "enabled": True,
            "higher_timeframes": ["60", "240"],
            "trend_indicators": ["ema", "ehlers_supertrend"],
            "trend_period": 50,  # Period for MTF trend indicators like SMA/EMA
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
            "feature_lags": [1, 2, 3, 5],  # Added default values
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
            "volatility_index_period": 20,
            "vwma_period": 20,
            "volume_delta_period": 5,
            "volume_delta_threshold": 0.2,
            "vwap_daily_reset": False,  # Should VWAP reset daily or be continuous
        },
        # Active Indicators & Weights (expanded)
        "indicators": {
            "ema_alignment": True,
            "sma_trend_filter": True,
            "momentum": True,
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
            "orderbook_imbalance": False,  # Kept as False by default due to complexity without WebSocket
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
        "weight_sets": {
            "default_scalping": {
                "ema_alignment": 0.22,
                "sma_trend_filter": 0.28,
                "momentum_rsi_stoch_cci_wr_mfi": 0.18,
                "volume_confirmation": 0.12,  # This is a placeholder, needs specific logic if used
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
            }
        },
        # Gemini AI Analysis (Optional)
        "gemini_ai_analysis": {
            "enabled": False,
            "model_name": "gemini-1.0-pro",
            "temperature": 0.7,
            "top_p": 0.9,
            "weight": 0.3,  # Weight of Gemini's signal in the final score
        },
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(
                f"{NEON_YELLOW}Configuration file not found. "
                f"Created default config at {filepath} for symbol "
                f"{default_config['symbol']}{RESET}"
            )
            return default_config
        except OSError as e:
            logger.error(f"{NEON_RED}Error creating default config file: {e}{RESET}")
            return default_config

    try:
        with Path(filepath).open(encoding="utf-8") as f:
            config = json.load(f)
        _ensure_config_keys(config, default_config)
        # Save updated config to include any newly added default keys
        with Path(filepath).open("w", encoding="utf-8") as f_write:
            json.dump(config, f_write, indent=4)
        return config
    except (OSError, FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(
            f"{NEON_RED}Error loading config: {e}. Using default and attempting to save.{RESET}"
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
        """Initializes the SensitiveFormatter."""
        super().__init__(fmt, datefmt, style)
        self._fmt = fmt if fmt else self.default_fmt()

    def default_fmt(self):
        """Returns the default log format string."""
        return "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def format(self, record):
        """Formats the log record, redacting sensitive words."""
        original_message = super().format(record)
        redacted_message = original_message
        for word in self.SENSITIVE_WORDS:
            # Ensure replacement happens only for full words or clear identifiers
            # This is a basic redaction, more sophisticated regex might be needed for complex cases
            redacted_message = redacted_message.replace(f"'{word}'", "'********'")
            redacted_message = redacted_message.replace(f'"{word}"', '"********"')
            redacted_message = redacted_message.replace(word, "********")
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
                f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}"
            )
        )
        logger.addHandler(console_handler)

        # File Handler
        log_file = Path(LOG_DIRECTORY) / f"{log_name}.log"
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setFormatter(
            SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)

    return logger


# --- API Interaction (Asynchronous with httpx) ---
async def create_async_session() -> httpx.AsyncClient:
    """Create an asynchronous httpx session with retry logic."""
    # httpx does not have built-in `Retry` like requests.adapters.Retry.
    # Custom retry logic can be implemented using `tenacity` or a similar library,
    # or by wrapping calls. For simplicity, we'll implement a basic retry mechanism
    # directly in `bybit_request_async` for now, or rely on `httpx`'s default.
    # For a full production system, a more sophisticated retry strategy (e.g., tenacity) is recommended.
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT)


def generate_signature(payload: str, api_secret: str) -> str:
    """Generate a Bybit API signature."""
    return hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_pybit_client(testnet: bool = False) -> HTTP:
    """Create and return a pybit HTTP client."""
    return HTTP(
        testnet=testnet,
        api_key=API_KEY,
        api_secret=API_SECRET,
        # pybit handles time sync and retries internally, so no need for custom time_offset_ms or retry logic here
        # recv_window can be set here if needed, default is 5000
        # timeout can be set here, default is 10 seconds
    )


async def fetch_current_price(
    symbol: str,
    logger: logging.Logger,
    client: httpx.AsyncClient,
    time_offset_ms: int = 0,
) -> Decimal | None:
    """Fetch the current market price for a symbol."""
    endpoint = "/v5/market/tickers"
    params = {"category": "linear", "symbol": symbol}
    response = await bybit_request_async(
        "GET",
        endpoint,
        params,
        logger=logger,
        client=client,
        time_offset_ms=time_offset_ms,
    )
    if response and response["result"] and response["result"]["list"]:
        price = Decimal(response["result"]["list"][0]["lastPrice"])
        logger.debug(f"Fetched current price for {symbol}: {price}")
        return price
    logger.warning(f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}")
    return None


async def fetch_klines(
    symbol: str,
    interval: str,
    limit: int,
    logger: logging.Logger,
    client: httpx.AsyncClient,
    time_offset_ms: int = 0,
) -> pd.DataFrame | None:
    """Fetch kline data for a symbol and interval."""
    endpoint = "/v5/market/kline"
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    response = await bybit_request_async(
        "GET",
        endpoint,
        params,
        logger=logger,
        client=client,
        time_offset_ms=time_offset_ms,
    )
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
            df["start_time"].astype(int), unit="ms", utc=True
        ).dt.tz_convert(TIMEZONE)
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.set_index("start_time", inplace=True)
        df.sort_index(inplace=True)

        # Drop rows with any NaN values in critical columns (open, high, low, close, volume)
        df.dropna(subset=["open", "high", "low", "close", "volume"], inplace=True)

        if df.empty:
            logger.warning(
                f"{NEON_YELLOW}Fetched klines for {symbol} {interval} but DataFrame is empty after processing/cleaning. Raw response: {response}{RESET}"
            )
            return None

        logger.debug(f"Fetched {len(df)} {interval} klines for {symbol}.")
        return df
    logger.warning(
        f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}. API response might be empty or invalid. Raw response: {response}{RESET}"
    )
    return None


async def fetch_orderbook(
    symbol: str,
    limit: int,
    logger: logging.Logger,
    client: httpx.AsyncClient,
    time_offset_ms: int = 0,
) -> dict | None:
    """Fetch orderbook data for a symbol."""
    endpoint = "/v5/market/orderbook"
    params = {"category": "linear", "symbol": symbol, "limit": limit}
    response = await bybit_request_async(
        "GET",
        endpoint,
        params,
        logger=logger,
        client=client,
        time_offset_ms=time_offset_ms,
    )
    if response and response["result"]:
        logger.debug(f"Fetched orderbook for {symbol} with limit {limit}.")
        return response["result"]
    logger.warning(f"{NEON_YELLOW}Could not fetch orderbook for {symbol}.{RESET}")
    return None


async def get_wallet_balance(
    account_type: Literal["UNIFIED", "CONTRACT"],
    coin: str,
    logger: logging.Logger,
    client: httpx.AsyncClient,
    time_offset_ms: int = 0,
) -> Decimal | None:
    """Fetch wallet balance for a specific coin."""
    endpoint = "/v5/account/wallet-balance"
    params = {"accountType": account_type, "coin": coin}
    response = await bybit_request_async(
        "GET",
        endpoint,
        params,
        signed=True,
        logger=logger,
        client=client,
        time_offset_ms=time_offset_ms,
    )
    if response and response["result"] and response["result"]["list"]:
        for item in response["result"]["list"]:
            # Accessing the first element of the 'coin' list within each item
            if item["coin"][0]["coin"] == coin:
                balance = Decimal(item["coin"][0]["walletBalance"])
                logger.debug(f"Fetched {coin} wallet balance: {balance}")
                return balance
    logger.warning(f"{NEON_YELLOW}Could not fetch {coin} wallet balance.{RESET}")
    return None


async def get_exchange_open_positions(
    symbol: str,
    category: str,
    logger: logging.Logger,
    client: httpx.AsyncClient,
    time_offset_ms: int = 0,
) -> list[dict] | None:
    """Fetch currently open positions from the exchange."""
    endpoint = "/v5/position/list"
    params = {"category": category, "symbol": symbol}
    response = await bybit_request_async(
        "GET",
        endpoint,
        params,
        signed=True,
        logger=logger,
        client=client,
        time_offset_ms=time_offset_ms,
    )
    if response and response["result"] and response["result"]["list"]:
        return response["result"]["list"]
    return []


async def fetch_bybit_server_time(
    logger: logging.Logger, client: httpx.AsyncClient
) -> int | None:
    """Fetch Bybit's server time in milliseconds."""
    endpoint = "/v5/market/time"  # V5 public endpoint for server time
    response = await bybit_request_async(
        "GET", endpoint, signed=False, logger=logger, client=client
    )
    if response and response.get("retCode") == 0:
        server_time_ms = response["result"]["timeNano"]  # timeNano is in nanoseconds
        return int(
            int(server_time_ms) / 1_000_000
        )  # Convert nanoseconds to milliseconds
    logger.error(
        f"{NEON_RED}Failed to fetch Bybit server time. Response: {response}{RESET}"
    )
    return None


async def place_order(
    symbol: str,
    side: Literal["Buy", "Sell"],
    order_type: Literal["Market", "Limit"],
    qty: Decimal,
    price: Decimal | None = None,
    reduce_only: bool = False,
    take_profit: Decimal | None = None,
    stop_loss: Decimal | None = None,
    tp_sl_mode: Literal["Full", "Partial"] = "Full",
    logger: logging.Logger | None = None,
    position_idx: int | None = None,  # Added parameter for hedge mode
    client: httpx.AsyncClient | None = None,
    time_offset_ms: int = 0,  # New parameter
) -> dict | None:
    """Place an order on Bybit."""
    if logger is None:
        logger = setup_logger("bybit_api")
    if client is None:
        client = await create_async_session()

    params: dict[str, Any] = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "orderType": order_type,
        "qty": str(qty),
        "reduceOnly": reduce_only,
    }
    if order_type == "Limit" and price is not None:
        params["price"] = str(price)

    if position_idx is not None:
        params["positionIdx"] = position_idx

    # Add TP/SL to the order itself
    if take_profit is not None:
        params["takeProfit"] = str(take_profit)
        params["tpslMode"] = tp_sl_mode  # Usually 'Full' to apply to entire position
    if stop_loss is not None:
        params["stopLoss"] = str(stop_loss)
        params["tpslMode"] = tp_sl_mode  # Usually 'Full' to apply to entire position

    endpoint = "/v5/order/create"
    response = await bybit_request_async(
        "POST",
        endpoint,
        params,
        signed=True,
        logger=logger,
        client=client,
        time_offset_ms=time_offset_ms,
    )
    if response:
        logger.info(
            f"{NEON_GREEN}Order placed successfully for {symbol}: {response['result']}{RESET}"
        )
        return response["result"]
    logger.error(f"{NEON_RED}Failed to place order for {symbol}: {params}{RESET}")
    return None


async def cancel_order(
    symbol: str,
    order_id: str,
    logger: logging.Logger | None = None,
    client: httpx.AsyncClient | None = None,
    time_offset_ms: int = 0,
) -> dict | None:
    """Cancel an existing order on Bybit."""
    if logger is None:
        logger = setup_logger("bybit_api")
    if client is None:
        client = await create_async_session()

    endpoint = "/v5/order/cancel"
    params = {"category": "linear", "symbol": symbol, "orderId": order_id}
    response = await bybit_request_async(
        "POST",
        endpoint,
        params,
        signed=True,
        logger=logger,
        client=client,
        time_offset_ms=time_offset_ms,
    )
    if response:
        logger.info(
            f"{NEON_GREEN}Order {order_id} cancelled for {symbol}: {response['result']}{RESET}"
        )
        return response["result"]
    logger.error(f"{NEON_RED}Failed to cancel order {order_id} for {symbol}.{RESET}")
    return None


async def set_trailing_stop(
    symbol: str,
    side: Literal["Buy", "Sell"],  # Refers to the position side to apply the stop to
    stop_loss: Decimal,
    position_idx: int,
    logger: logging.Logger | None = None,
    client: httpx.AsyncClient | None = None,
    trailing_stop_trigger_by: Literal["LastPrice", "IndexPrice"] = "LastPrice",
    time_offset_ms: int = 0,  # New parameter
) -> dict | None:
    """Set or update a trailing stop loss for an existing position on Bybit."""
    if logger is None:
        logger = setup_logger("bybit_api")
    if client is None:
        client = await create_async_session()

    # Bybit's API takes the absolute price for 'trailingStop', NOT a callback rate.
    # The 'stopLoss' parameter is used here to mean the trailing stop price itself.
    params: dict[str, Any] = {
        "category": "linear",
        "symbol": symbol,
        "trailingStop": str(stop_loss),  # This is the specific trigger price for TS
        "tpSlMode": "Full",  # Always applies to full position
        "positionIdx": position_idx,
        "triggerBy": trailing_stop_trigger_by,
    }

    # We also need to specify a stopLoss here if we are setting a specific price based stop.
    # However, for trailing stop, we're usually updating a dynamic level.
    # Bybit API docs for set-trading-stop indicate 'trailingStop' directly.
    # If the goal is to set a specific (fixed) SL, use 'stopLoss' parameter instead of 'trailingStop'
    # or to update it. For dynamic trailing SL, 'trailingStop' is the correct one.

    endpoint = "/v5/position/set-trading-stop"
    response = await bybit_request_async(
        "POST",
        endpoint,
        params,
        signed=True,
        logger=logger,
        client=client,
        time_offset_ms=time_offset_ms,
    )
    if response and response.get("retCode") == 0:
        logger.info(
            f"{NEON_GREEN}Successfully set/updated trailing stop for {symbol} ({side}) to {stop_loss.normalize()}.{RESET}"
        )
        return response["result"]
    logger.error(
        f"{NEON_RED}Failed to set/update trailing stop for {symbol} ({side}) to {stop_loss.normalize()}. Response: {response}{RESET}"
    )
    return None


# --- Precision Management ---
class PrecisionManager:
    """Manages symbol-specific precision for order quantity and price."""

    def __init__(
        self,
        symbol: str,
        logger: logging.Logger,
        config: dict[str, Any],
        client: httpx.AsyncClient,
    ):
        """Initializes the PrecisionManager."""
        self.symbol = symbol
        self.logger = logger
        self.config = config
        self.client = client  # Async client for API calls
        self.qty_step: Decimal | None = None
        self.price_tick_size: Decimal | None = None
        self.min_order_qty: Decimal | None = None
        self.max_order_qty: Decimal | None = None
        self.min_price: Decimal | None = None
        self.max_price: Decimal | None = None

    async def initialize(self, time_offset_ms: int = 0) -> None:
        """Asynchronously fetch precision info during initialization."""
        await self._fetch_precision_info(time_offset_ms)

    async def _fetch_precision_info(self, time_offset_ms: int = 0) -> None:
        """Fetch and store precision info from the exchange."""
        self.logger.info(f"[{self.symbol}] Fetching precision information...")
        endpoint = "/v5/market/instruments-info"
        params = {"category": "linear", "symbol": self.symbol}
        response = await bybit_request_async(
            "GET",
            endpoint,
            params,
            signed=False,
            logger=self.logger,
            client=self.client,
            time_offset_ms=time_offset_ms,
        )

        if response and response.get("result") and response["result"].get("list"):
            instrument_info = response["result"]["list"][0]
            lot_size_filter = instrument_info.get("lotSizeFilter", {})
            price_filter = instrument_info.get("priceFilter", {})

            self.qty_step = Decimal(lot_size_filter.get("qtyStep", "0.001"))
            self.price_tick_size = Decimal(price_filter.get("tickSize", "0.01"))
            self.min_order_qty = Decimal(lot_size_filter.get("minOrderQty", "0.001"))
            self.max_order_qty = Decimal(lot_size_filter.get("maxOrderQty", "100000"))
            self.min_price = Decimal(price_filter.get("minPrice", "0.01"))
            self.max_price = Decimal(price_filter.get("maxPrice", "1000000"))

            self.logger.info(
                f"[{self.symbol}] Precision loaded: Qty Step={self.qty_step.normalize()}, "
                f"Price Tick Size={self.price_tick_size.normalize()}, "
                f"Min Qty={self.min_order_qty.normalize()}"
            )
        else:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Failed to fetch precision info. Using default values from config. "
                f"This may cause order placement errors.{RESET}"
            )
            # Fallback to config values if API fails
            order_precision = self.config["trade_management"]["order_precision"]
            price_precision = self.config["trade_management"]["price_precision"]
            self.qty_step = Decimal("0." + "0" * (order_precision - 1) + "1")
            self.price_tick_size = Decimal("0." + "0" * (price_precision - 1) + "1")
            self.min_order_qty = Decimal("0.001")  # A reasonable default

    def format_quantity(self, quantity: Decimal) -> Decimal:
        """Formats the order quantity according to the symbol's qtyStep."""
        if self.qty_step is None or self.qty_step == Decimal("0"):
            order_precision = self.config["trade_management"]["order_precision"]
            fallback_step = Decimal("0." + "0" * (order_precision - 1) + "1")
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] qty_step is not set or zero. Using fallback precision {fallback_step} for quantity.{RESET}"
            )
            return quantity.quantize(fallback_step, rounding=ROUND_DOWN)
        return (quantity // self.qty_step) * self.qty_step

    def format_price(self, price: Decimal) -> Decimal:
        """Formats the order price according to the symbol's tickSize."""
        if self.price_tick_size is None or self.price_tick_size == Decimal("0"):
            price_precision = self.config["trade_management"]["price_precision"]
            fallback_tick = Decimal("0." + "0" * (price_precision - 1) + "1")
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] price_tick_size is not set or zero. Using fallback precision {fallback_tick} for price.{RESET}"
            )
            return price.quantize(fallback_tick, rounding=ROUND_DOWN)
        return (price // self.price_tick_size) * self.price_tick_size


# --- Position Management ---
class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""

    def __init__(
        self,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
        client: httpx.AsyncClient,
    ):
        """Initializes the PositionManager."""
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.client = client
        self.open_positions: dict[
            str, dict
        ] = {}  # Tracks positions opened by the bot locally
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.precision_manager = PrecisionManager(symbol, logger, config, client)
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.leverage = config["trade_management"]["leverage"]
        self.order_mode = config["trade_management"]["order_mode"]
        self.tp_sl_mode = "Full"  # Default to full for simplicity, can be configured
        self.trailing_stop_activation_percent = (
            Decimal(str(config["trade_management"]["trailing_stop_activation_percent"]))
            / 100
        )
        self.trailing_stop_trigger_by = config["trade_management"][
            "trailing_stop_trigger_by"
        ]

    async def initialize(self, time_offset_ms: int = 0) -> None:
        """Asynchronously initialize precision manager and set leverage."""
        await self.precision_manager.initialize(time_offset_ms)
        # Set leverage (only once or when changed)
        if self.trade_management_enabled:
            await self._set_leverage(time_offset_ms)
            await self._reconcile_positions_with_exchange(time_offset_ms)

    async def _set_leverage(self, time_offset_ms: int = 0) -> None:
        """Set leverage for the trading pair."""
        endpoint = "/v5/position/set-leverage"
        params = {
            "category": "linear",
            "symbol": self.symbol,
            "buyLeverage": str(self.leverage),
            "sellLeverage": str(self.leverage),
        }
        response = await bybit_request_async(
            "POST",
            endpoint,
            params,
            signed=True,
            logger=self.logger,
            client=self.client,
            time_offset_ms=time_offset_ms,
        )
        if response and response.get("retCode") == 0:
            self.logger.info(
                f"{NEON_GREEN}[{self.symbol}] Leverage set to {self.leverage}x.{RESET}"
            )
        else:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Failed to set leverage to {self.leverage}x. Error: {response.get('retMsg') if response else 'Unknown'}{RESET}"
            )

    async def _get_available_balance(self, time_offset_ms: int = 0) -> Decimal:
        """Fetch current available account balance for order sizing."""
        if not self.trade_management_enabled:
            return Decimal(str(self.config["trade_management"]["account_balance"]))

        balance = await get_wallet_balance(
            account_type="UNIFIED",
            coin="USDT",
            logger=self.logger,
            client=self.client,
            time_offset_ms=time_offset_ms,
        )  # Assuming USDT for linear contracts
        if balance is None:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Failed to fetch actual balance. Using simulated balance for calculation.{RESET}"
            )
            return Decimal(str(self.config["trade_management"]["account_balance"]))
        return balance

    def _calculate_order_size(
        self, current_price: Decimal, atr_value: Decimal
    ) -> Decimal:
        """Calculate order size based on risk per trade, ATR, and available balance."""
        if not self.trade_management_enabled:
            return Decimal("0")

        account_balance = (
            self._get_available_balance()
        )  # This will be async when called. For calculation, use current value.
        risk_per_trade_percent = (
            Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
            / 100
        )
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )

        risk_amount = account_balance * risk_per_trade_percent
        stop_loss_distance_usd = atr_value * stop_loss_atr_multiple

        if stop_loss_distance_usd <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated stop loss distance is zero or negative ({stop_loss_distance_usd}). Cannot determine order size.{RESET}"
            )
            return Decimal("0")

        # Order size in USD value (notional value)
        # For leverage, the actual order value is `risk_amount / (stop_loss_distance_usd / entry_price)`
        # if using fixed risk and stop loss.
        # This simplifies to: order_qty = risk_amount / stop_loss_distance_usd (in terms of price units)
        # Then we multiply by leverage to get notional value, and divide by price to get quantity.
        # A simpler way often used with fixed risk:
        # Quantity = (Risk Amount / (ATR * ATR_Multiple)) / Price
        # Or more accurately, use (Risk Amount / Stop Loss Pips) * Leverage
        # Here we follow the simpler risk_amount / stop_loss_distance_usd approach for quantity.

        # Calculate quantity based on risk amount and stop loss distance
        order_qty_base = risk_amount / stop_loss_distance_usd

        # Adjust for leverage: the 'size' on Bybit is the actual quantity you're trading.
        # The margin required is what's affected by leverage.
        # So, the order_qty_base is the actual quantity to trade for the given risk.
        order_qty = order_qty_base

        # Round order_qty to appropriate precision for the symbol
        order_qty = self.precision_manager.format_quantity(order_qty)

        # Check against min order quantity
        if (
            self.precision_manager.min_order_qty is not None
            and order_qty < self.precision_manager.min_order_qty
        ):
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated order quantity ({order_qty.normalize()}) is below the minimum "
                f"({self.precision_manager.min_order_qty.normalize()}). Cannot open position. "
                f"Consider reducing risk per trade or using a larger account balance.{RESET}"
            )
            return Decimal("0")

        if order_qty <= Decimal("0"):
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated order quantity ({order_qty.normalize()}) is too small or zero. Cannot open position.{RESET}"
            )
            return Decimal("0")

        self.logger.info(
            f"[{self.symbol}] Calculated order size: {order_qty.normalize()} (Risk: {risk_amount.normalize():.2f} USDT, SL Distance: {stop_loss_distance_usd.normalize():.4f})"
        )
        return order_qty

    async def open_position(
        self,
        signal: Literal["BUY", "SELL"],
        current_price: Decimal,
        atr_value: Decimal,
        time_offset_ms: int = 0,
    ) -> dict | None:
        """Open a new position if conditions allow by placing an order on the exchange."""
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Trade management is disabled. Skipping opening position.{RESET}"
            )
            return None

        # Check if we already have an open position for this symbol
        if (
            self.symbol in self.open_positions
            and self.open_positions[self.symbol]["status"] == "OPEN"
        ):
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Already have an open position. Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
            )
            return None

        # Check against max_open_positions from config
        if (
            self.max_open_positions > 0
            and len(self.open_positions) >= self.max_open_positions
        ):
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
            )
            return None

        if signal not in ["BUY", "SELL"]:
            self.logger.debug(f"Invalid signal '{signal}' for opening position.")
            return None

        order_qty = self._calculate_order_size(current_price, atr_value)
        if order_qty <= Decimal("0"):
            return None

        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"])
        )

        side = "Buy" if signal == "BUY" else "Sell"
        # For Hedge Mode: 1 for long (Buy), 2 for short (Sell)
        # For One-Way Mode: 0 for both (Bybit v5 default for unified margin)
        # Assuming One-Way Mode unless specifically configured for Hedge Mode and the bot tracks individual positionIdx
        # If we get an error about positionIdx not matching position mode, we should set it to 0.
        position_idx = (
            0  # Default to 0 for one-way mode, or 1/2 for hedge mode as per Bybit setup
        )

        entry_price = (
            current_price  # For Market orders, entry price is roughly current price
        )

        if signal == "BUY":
            stop_loss_price = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit_price = current_price + (atr_value * take_profit_atr_multiple)
        else:  # SELL
            stop_loss_price = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit_price = current_price - (atr_value * take_profit_atr_multiple)

        entry_price = self.precision_manager.format_price(entry_price)
        stop_loss_price = self.precision_manager.format_price(stop_loss_price)
        take_profit_price = self.precision_manager.format_price(take_profit_price)

        self.logger.info(
            f"[{self.symbol}] Attempting to place {side} order: Qty={order_qty.normalize()}, SL={stop_loss_price.normalize()}, TP={take_profit_price.normalize()}"
        )

        placed_order = await place_order(
            symbol=self.symbol,
            side=side,
            order_type=self.order_mode,
            qty=order_qty,
            price=entry_price if self.order_mode == "Limit" else None,
            take_profit=take_profit_price,
            stop_loss=stop_loss_price,
            tp_sl_mode=self.tp_sl_mode,
            logger=self.logger,
            position_idx=position_idx,  # Pass position_idx
            client=self.client,
            time_offset_ms=time_offset_ms,  # Pass time_offset_ms
        )

        if placed_order:
            self.logger.info(
                f"{NEON_GREEN}[{self.symbol}] Successfully initiated {signal} trade with order ID: {placed_order.get('orderId')}{RESET}"
            )
            # For logging/tracking purposes, return a simplified representation
            position_info = {
                "entry_time": datetime.now(TIMEZONE),
                "symbol": self.symbol,
                "side": signal,
                "entry_price": entry_price,  # This might be different from actual fill price for market orders
                "qty": order_qty,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price,
                "status": "OPEN",
                "order_id": placed_order.get("orderId"),
                "is_trailing_activated": False,
                "current_trailing_sl": stop_loss_price,  # Initialize trailing SL to initial SL
                "position_idx": position_idx,  # Store positionIdx for later use
            }
            self.open_positions[self.symbol] = (
                position_info  # Track the position locally
            )
            return position_info
        self.logger.error(
            f"{NEON_RED}[{self.symbol}] Failed to place {signal} order. Check API logs for details.{RESET}"
        )
        return None

    async def _reconcile_positions_with_exchange(self, time_offset_ms: int = 0) -> None:
        """Reconcile locally tracked positions with actual open positions on the exchange."""
        if not self.trade_management_enabled:
            return

        exchange_positions = await get_exchange_open_positions(
            self.symbol,
            "linear",
            self.logger,
            self.client,
            time_offset_ms=time_offset_ms,
        )

        if exchange_positions is None:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Could not fetch open positions from exchange for reconciliation.{RESET}"
            )
            return

        # Clear existing local positions that are no longer open on the exchange
        # or update their status
        temp_local_positions = self.open_positions.copy()
        for symbol, local_pos in temp_local_positions.items():
            if local_pos["status"] == "OPEN":
                found_on_exchange = False
                for ex_pos in exchange_positions:
                    if (
                        ex_pos["symbol"] == local_pos["symbol"]
                        and ex_pos["side"].lower() == local_pos["side"].lower()
                        and Decimal(ex_pos["size"]) > 0
                        # For hedge mode, check positionIdx if applicable
                        # and ex_pos.get("positionIdx", 0) == local_pos.get("position_idx", 0)
                    ):
                        found_on_exchange = True
                        # Update local position with exchange data (e.g., actual entry price, SL/TP if they changed)
                        local_pos["qty"] = Decimal(ex_pos["size"])
                        local_pos["entry_price"] = Decimal(ex_pos["avgPrice"])
                        local_pos["stop_loss"] = Decimal(
                            ex_pos.get("stopLoss", str(local_pos["stop_loss"]))
                        )  # Use existing if not on exchange
                        local_pos["take_profit"] = Decimal(
                            ex_pos.get("takeProfit", str(local_pos["take_profit"]))
                        )  # Use existing if not on exchange
                        local_pos["current_trailing_sl"] = Decimal(
                            ex_pos.get("trailingStop", str(local_pos["stop_loss"]))
                        )
                        if Decimal(ex_pos.get("trailingStop", "0")) > 0:
                            local_pos["is_trailing_activated"] = True

                        # Store bybit position ID if available, not the orderId from initial placement
                        local_pos["bybit_position_id"] = ex_pos.get("positionId")
                        self.open_positions[symbol] = local_pos
                        break
                if not found_on_exchange:
                    self.logger.info(
                        f"{NEON_PURPLE}Local position for {symbol} not found on exchange. Marking as closed (EXTERNAL_CLOSURE).{RESET}"
                    )
                    local_pos["status"] = "CLOSED"
                    local_pos["exit_time"] = datetime.now(TIMEZONE)
                    local_pos["closed_by"] = "EXTERNAL_CLOSURE"
                    # We can't determine PnL accurately here without knowing the exit price.
                    # This is a limitation of reconciliation if the bot didn't issue the close.
                    # For now, mark as closed without PnL.
                    # In a real system, you'd need to listen to user trade execution reports via websocket.
                    del self.open_positions[symbol]  # Remove it from active tracking

        # Add new positions found on exchange that aren't tracked locally
        for ex_pos in exchange_positions:
            if (
                Decimal(ex_pos["size"]) > 0
                and ex_pos["symbol"] not in self.open_positions
            ):
                self.logger.info(
                    f"{NEON_CYAN}Found new open position on exchange for {ex_pos['symbol']}. Adding to local tracking.{RESET}"
                )
                side = "BUY" if ex_pos["side"] == "Buy" else "SELL"
                new_pos_info = {
                    "entry_time": datetime.now(TIMEZONE),  # Estimate if not available
                    "symbol": ex_pos["symbol"],
                    "side": side,
                    "entry_price": Decimal(ex_pos["avgPrice"]),
                    "qty": Decimal(ex_pos["size"]),
                    "stop_loss": Decimal(ex_pos.get("stopLoss", "0")),
                    "take_profit": Decimal(ex_pos.get("takeProfit", "0")),
                    "status": "OPEN",
                    "order_id": None,  # Initial order ID is not available from position list
                    "is_trailing_activated": Decimal(ex_pos.get("trailingStop", "0"))
                    > 0,
                    "current_trailing_sl": Decimal(ex_pos.get("trailingStop", "0")),
                    "position_idx": ex_pos.get("positionIdx", 0),
                    "bybit_position_id": ex_pos.get("positionId"),
                }
                self.open_positions[ex_pos["symbol"]] = new_pos_info

        self.logger.info(
            f"[{self.symbol}] Positions reconciled. Currently tracking {len(self.open_positions)} open positions locally."
        )

    async def manage_positions(
        self,
        current_price: Decimal,
        atr_value: Decimal,
        performance_tracker: Any,
        time_offset_ms: int = 0,
    ) -> None:
        """Check and manage open positions on the exchange (TP/SL are handled by Bybit).
        This method handles trailing stop logic by interacting with the Bybit API.
        """
        if not self.trade_management_enabled:
            return

        # First, reconcile with exchange to get the latest state including any closed positions
        await self._reconcile_positions_with_exchange()

        # Iterate over a copy to allow modification if a position is closed/removed
        positions_to_close_locally = []
        for symbol, position in list(self.open_positions.items()):
            if position["status"] == "OPEN":
                side = position["side"]
                entry_price = position["entry_price"]
                stop_loss = position["stop_loss"]
                take_profit = position["take_profit"]
                qty = position["qty"]
                is_trailing_activated = position.get("is_trailing_activated", False)
                current_trailing_sl = position.get("current_trailing_sl", stop_loss)
                position_idx = position.get(
                    "position_idx", 0
                )  # Default to 0 for one-way

                # Calculate current PnL for trailing stop activation
                unrealized_pnl = Decimal("0")
                if side == "BUY":
                    unrealized_pnl = (current_price - entry_price) * qty
                elif side == "SELL":
                    unrealized_pnl = (entry_price - current_price) * qty

                # Activate/Update Trailing Stop Logic (if enabled and profitable enough)
                if (
                    self.config["trade_management"].get("trailing_stop_atr_multiple", 0)
                    > 0
                ):
                    trailing_stop_atr_multiple = Decimal(
                        str(
                            self.config["trade_management"][
                                "trailing_stop_atr_multiple"
                            ]
                        )
                    )

                    # Calculate profit percentage relative to entry price (assuming entry_price is not zero)
                    profit_percent = Decimal("0")
                    if entry_price != Decimal("0"):
                        profit_percent = (unrealized_pnl / (entry_price * qty)) * 100

                    if (
                        not is_trailing_activated
                        and profit_percent
                        >= self.trailing_stop_activation_percent * 100
                    ):
                        position["is_trailing_activated"] = True

                        # Calculate initial trailing stop price based on current price
                        new_trailing_sl_price = Decimal("0")
                        if side == "BUY":
                            new_trailing_sl_price = current_price - (
                                atr_value * trailing_stop_atr_multiple
                            )
                            # Ensure trailing SL doesn't go below initial SL
                            new_trailing_sl_price = max(
                                new_trailing_sl_price, stop_loss
                            )
                        else:  # SELL
                            new_trailing_sl_price = current_price + (
                                atr_value * trailing_stop_atr_multiple
                            )
                            # Ensure trailing SL doesn't go above initial SL
                            new_trailing_sl_price = min(
                                new_trailing_sl_price, stop_loss
                            )

                        position["current_trailing_sl"] = (
                            self.precision_manager.format_price(new_trailing_sl_price)
                        )
                        self.logger.info(
                            f"{NEON_GREEN}Trailing stop activated for {symbol} ({side}). Initial SL: {position['current_trailing_sl'].normalize()}{RESET}"
                        )
                        await set_trailing_stop(
                            self.symbol,
                            side,
                            position["current_trailing_sl"],
                            position_idx,
                            self.logger,
                            self.client,
                            self.trailing_stop_trigger_by,
                            time_offset_ms,  # Pass time_offset_ms
                        )

                    elif is_trailing_activated:
                        # Trailing stop is active, check if it needs updating
                        potential_new_sl = Decimal("0")
                        moved_sl = False
                        if side == "BUY":
                            potential_new_sl = current_price - (
                                atr_value * trailing_stop_atr_multiple
                            )
                            # Only move trailing SL up (for buy)
                            if potential_new_sl > current_trailing_sl:
                                potential_new_sl = self.precision_manager.format_price(
                                    potential_new_sl
                                )
                                position["current_trailing_sl"] = potential_new_sl
                                moved_sl = True
                        elif side == "SELL":
                            potential_new_sl = current_price + (
                                atr_value * trailing_stop_atr_multiple
                            )
                            # Only move trailing SL down (for sell)
                            if potential_new_sl < current_trailing_sl:
                                potential_new_sl = self.precision_manager.format_price(
                                    potential_new_sl
                                )
                                position["current_trailing_sl"] = potential_new_sl
                                moved_sl = True

                        if moved_sl:
                            self.logger.info(
                                f"{NEON_GREEN}Updating trailing stop for {symbol} ({side}) to {position['current_trailing_sl'].normalize()}{RESET}"
                            )
                            await set_trailing_stop(
                                self.symbol,
                                side,
                                position["current_trailing_sl"],
                                position_idx,
                                self.logger,
                                self.client,
                                self.trailing_stop_trigger_by,
                            )

                # Check for local price crossing initial TP/SL (Bybit handles this on exchange, but for simulation/logging)
                # This part is mostly for local logging/tracking consistency.
                # Actual closure would be reported by reconcile, or via websockets in a real system.
                closed_by = ""
                exit_price = Decimal("0")

                if side == "BUY":
                    if (
                        current_price <= current_trailing_sl
                    ):  # Check against trailing SL first
                        closed_by = "TRAILING_STOP_LOSS"
                        exit_price = current_trailing_sl
                    elif (
                        current_price <= stop_loss and not is_trailing_activated
                    ):  # Fallback to fixed SL if TS not active
                        closed_by = "STOP_LOSS"
                        exit_price = stop_loss
                    elif current_price >= take_profit:
                        closed_by = "TAKE_PROFIT"
                        exit_price = take_profit
                elif side == "SELL":
                    if (
                        current_price >= current_trailing_sl
                    ):  # Check against trailing SL first
                        closed_by = "TRAILING_STOP_LOSS"
                        exit_price = current_trailing_sl
                    elif (
                        current_price >= stop_loss and not is_trailing_activated
                    ):  # Fallback to fixed SL if TS not active
                        closed_by = "STOP_LOSS"
                        exit_price = stop_loss
                    elif current_price <= take_profit:
                        closed_by = "TAKE_PROFIT"
                        exit_price = take_profit

                if closed_by:
                    self.logger.info(
                        f"{NEON_PURPLE}Position for {symbol} closed by {closed_by} locally. Recording trade.{RESET}"
                    )
                    # We expect reconciliation to handle actual exchange closure,
                    # but for local tracking completeness, we log and mark.
                    position["status"] = "CLOSED"
                    position["exit_time"] = datetime.now(TIMEZONE)
                    position["exit_price"] = self.precision_manager.format_price(
                        exit_price
                    )
                    position["closed_by"] = closed_by

                    pnl = (
                        (exit_price - entry_price) * qty
                        if side == "BUY"
                        else (entry_price - exit_price) * qty
                    )
                    performance_tracker.record_trade(position, pnl)
                    positions_to_close_locally.append(symbol)
                    # Note: The actual order cancellation for TP/SL is handled by Bybit once hit.
                    # If this was a manual closure, we would issue a close order.

        # Remove closed positions from local tracking (those that were closed by bot logic or reconciliation)
        for symbol in positions_to_close_locally:
            if symbol in self.open_positions:
                del self.open_positions[symbol]

    def get_open_positions(self) -> list[dict]:
        """Return a list of currently open positions tracked locally."""
        return [pos for pos in self.open_positions.values() if pos["status"] == "OPEN"]


# --- Performance Tracking ---
class PerformanceTracker:
    """Tracks and reports trading performance. Trades are saved to a file."""

    def __init__(self, logger: logging.Logger, config_file: str = "trades.json"):
        """Initializes the PerformanceTracker."""
        self.logger = logger
        self.config_file = Path(config_file)
        self.trades: list[dict] = self._load_trades()
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0
        self._recalculate_summary()  # Recalculate summary from loaded trades

    def _load_trades(self) -> list[dict]:
        """Load trade history from file."""
        if self.config_file.exists():
            try:
                with self.config_file.open("r", encoding="utf-8") as f:
                    raw_trades = json.load(f)
                    # Convert Decimal/datetime from string after loading
                    loaded_trades = []
                    for trade in raw_trades:
                        for key in [
                            "pnl",
                            "entry_price",
                            "exit_price",
                            "qty",
                            "stop_loss",
                            "take_profit",
                            "current_trailing_sl",
                        ]:
                            if key in trade and trade[key] is not None:
                                trade[key] = Decimal(str(trade[key]))
                        for key in ["entry_time", "exit_time"]:
                            if key in trade and trade[key] is not None:
                                trade[key] = datetime.fromisoformat(trade[key])
                        loaded_trades.append(trade)
                    return loaded_trades
            except (json.JSONDecodeError, OSError) as e:
                self.logger.error(
                    f"{NEON_RED}Error loading trades from {self.config_file}: {e}{RESET}",
                    exc_info=True,
                )
        return []

    def _save_trades(self) -> None:
        """Save trade history to file."""
        try:
            # Ensure the directory exists
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with self.config_file.open("w", encoding="utf-8") as f:
                # Convert Decimal/datetime to string for JSON serialization
                serializable_trades = []
                for trade in self.trades:
                    s_trade = trade.copy()
                    for key in [
                        "pnl",
                        "entry_price",
                        "exit_price",
                        "qty",
                        "stop_loss",
                        "take_profit",
                        "current_trailing_sl",
                    ]:
                        if key in s_trade and s_trade[key] is not None:
                            s_trade[key] = str(s_trade[key])
                    for key in ["entry_time", "exit_time"]:
                        if key in s_trade and s_trade[key] is not None:
                            s_trade[key] = s_trade[key].isoformat()
                    serializable_trades.append(s_trade)
                json.dump(serializable_trades, f, indent=4)
        except OSError as e:
            self.logger.error(
                f"{NEON_RED}Error saving trades to {self.config_file}: {e}{RESET}",
                exc_info=True,
            )

    def _recalculate_summary(self) -> None:
        """Recalculate summary metrics from the list of trades."""
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0
        for trade in self.trades:
            pnl = Decimal(str(trade["pnl"]))  # Ensure pnl is Decimal
            self.total_pnl += pnl
            if pnl > 0:
                self.wins += 1
            else:
                self.losses += 1

    def record_trade(self, position: dict, pnl: Decimal) -> None:
        """Record a completed trade."""
        trade_record = {
            "entry_time": position.get(
                "entry_time", datetime.now(TIMEZONE)
            ).isoformat(),
            "exit_time": position.get("exit_time", datetime.now(TIMEZONE)).isoformat(),
            "symbol": position["symbol"],
            "side": position["side"],
            "entry_price": str(position["entry_price"]),
            "exit_price": str(position["exit_price"]),
            "qty": str(position["qty"]),
            "pnl": str(pnl),
            "closed_by": position.get("closed_by", "UNKNOWN"),
            "stop_loss": str(position["stop_loss"]),
            "take_profit": str(position["take_profit"]),
            "current_trailing_sl": str(position.get("current_trailing_sl", "N/A")),
        }
        self.trades.append(trade_record)
        self._recalculate_summary()  # Update summary immediately
        self._save_trades()  # Save to file
        self.logger.info(
            f"{NEON_CYAN}[{position['symbol']}] Trade recorded. Current Total PnL: {self.total_pnl.normalize():.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}"
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
        self, message: str, level: Literal["INFO", "WARNING", "ERROR"]
    ) -> None:
        """Send an alert (currently logs it)."""
        if level == "INFO":
            self.logger.info(f"{NEON_BLUE}ALERT: {message}{RESET}")
        elif level == "WARNING":
            self.logger.warning(f"{NEON_YELLOW}ALERT: {message}{RESET}")
        elif level == "ERROR":
            self.logger.error(f"{NEON_RED}ALERT: {message}{RESET}")


# --- Trading Analysis ---
class TradingAnalyzer:
    """Analyzes trading data and generates signals with MTF, Ehlers SuperTrend, and other new indicators."""

    def __init__(
        self,
        df: pd.DataFrame,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
        precision_manager: Any,
    ):
        """Initializes the TradingAnalyzer."""
        self.df = df.copy()
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.indicator_values: dict[str, float | str | Decimal] = {}
        self.fib_levels: dict[str, Decimal] = {}
        self.weights = config["weight_sets"]["default_scalping"]
        self.indicator_settings = config["indicator_settings"]
        self.price_precision = config["trade_management"][
            "price_precision"
        ]  # For Fibonacci levels
        self.precision_manager = precision_manager  # Add this line

        self.gemini_client: Any | None = None  # Placeholder for GeminiClient
        if self.config["gemini_ai_analysis"]["enabled"]:
            gemini_api_key = os.getenv("GEMINI_API_KEY")
            if not gemini_api_key:
                self.logger.error(
                    f"{NEON_RED}GEMINI_API_KEY environment variable is not set, but gemini_ai_analysis is enabled. Disabling Gemini AI analysis.{RESET}"
                )
                self.config["gemini_ai_analysis"]["enabled"] = False
            else:
                # Assuming GeminiClient is available and correctly imported/implemented elsewhere
                # from gemini_client import GeminiClient # Uncomment if GeminiClient is available
                # self.gemini_client = GeminiClient(
                #     api_key=gemini_api_key,
                #     model_name=self.config["gemini_ai_analysis"]["model_name"],
                #     temperature=self.config["gemini_ai_analysis"]["temperature"],
                #     top_p=self.config["gemini_ai_analysis"]["top_p"],
                #     logger=logger
                # )
                self.logger.warning(
                    f"{NEON_YELLOW}Gemini AI analysis enabled, but GeminiClient is not implemented/imported. Placeholder used.{RESET}"
                )

                # Placeholder for GeminiClient if not available
                class DummyGeminiClient:  # Define a dummy class for a cleaner placeholder
                    def analyze_market_data(self, data):
                        self.logger.info(
                            "Dummy Gemini AI: Analyzing market data (no actual analysis)."
                        )
                        return {
                            "entry": "HOLD",
                            "confidence_level": 50,
                            "reason": "Dummy analysis.",
                        }

                self.gemini_client = DummyGeminiClient()

        if not self.df.empty:
            self._calculate_all_indicators()
            if self.config["indicators"].get("fibonacci_levels", False):
                self.calculate_fibonacci_levels()

    def _safe_series_op(self, series: pd.Series, name: str) -> pd.Series:
        """Safely perform operations on a Series, handling potential NaNs and logging."""
        if series is None or series.empty:
            self.logger.debug(
                f"Series '{name}' is empty or None. Returning empty Series."
            )
            # Return an empty Series with float dtype
            return pd.Series(dtype=float)
        # Ensure the series is numeric before checking for all NaNs
        if not pd.api.types.is_numeric_dtype(series) or series.isnull().all():
            self.logger.debug(
                f"Series '{name}' contains all NaNs or is not numeric. Returning Series with NaNs."
            )
            return pd.Series(np.nan, index=series.index, dtype=float)
        return series

    def _safe_calculate(
        self, func: callable, name: str, min_data_points: int = 0, *args, **kwargs
    ) -> Any | None:
        """Safely calculate indicators and log errors, with min_data_points check."""
        if self.df.empty:
            self.logger.debug(f"Skipping indicator '{name}': DataFrame is empty.")
            return None
        if len(self.df) < min_data_points:
            self.logger.debug(
                f"Skipping indicator '{name}': Not enough data. Need {min_data_points}, have {len(self.df)}."
            )
            return None
        try:
            result = func(*args, **kwargs)

            # Check for empty series or all NaNs
            if isinstance(result, pd.Series) and (
                result.empty or result.isnull().all()
            ):
                self.logger.warning(
                    f"{NEON_YELLOW}Indicator '{name}' returned an empty or all-NaN Series. Not enough valid data?{RESET}"
                )
                return None
            if isinstance(result, tuple) and all(
                isinstance(r, pd.Series) and (r.empty or r.isnull().all())
                for r in result
            ):
                self.logger.warning(
                    f"{NEON_YELLOW}Indicator '{name}' returned all-empty or all-NaN Series in tuple. Not enough valid data?{RESET}"
                )
                return None
            return result
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}Error calculating indicator '{name}': {e}{RESET}",
                exc_info=True,  # Add exc_info for full traceback
            )
            return None

    def _calculate_all_indicators(self) -> None:
        """Calculate all enabled technical indicators."""
        self.logger.debug(f"[{self.symbol}] Calculating technical indicators...")
        cfg = self.config
        isd = self.indicator_settings

        # Ensure True Range is calculated first as it's a dependency for many indicators
        self.df["TR"] = self._safe_calculate(
            self.calculate_true_range, "TR", min_data_points=MIN_DATA_POINTS_TRUE_RANGE
        )
        # ATR (depends on TR, pandas_ta handles this internally if 'TR' column is missing but uses high/low/close)
        self.df["ATR"] = self._safe_calculate(
            lambda: ta.atr(
                self.df["high"],
                self.df["low"],
                self.df["close"],
                length=isd["atr_period"],
            ),
            "ATR",
            min_data_points=isd["atr_period"]
            + 1,  # ATR requires one more period than its length
        )
        if self.df["ATR"] is not None and not self.df["ATR"].empty:
            self.indicator_values["ATR"] = Decimal(
                str(self.df["ATR"].iloc[-1].item())
            )  # .item() to convert numpy float to Python float
        else:
            self.indicator_values["ATR"] = Decimal("0.01")  # Default to a small value

        # SMA
        if cfg["indicators"].get("sma_10", False):
            self.df["SMA_10"] = self._safe_calculate(
                lambda: ta.sma(self.df["close"], length=isd["sma_short_period"]),
                "SMA_10",
                min_data_points=isd["sma_short_period"],
            )
            if self.df["SMA_10"] is not None and not self.df["SMA_10"].empty:
                self.indicator_values["SMA_10"] = Decimal(
                    str(self.df["SMA_10"].iloc[-1].item())
                )
        if cfg["indicators"].get("sma_trend_filter", False):
            self.df["SMA_Long"] = self._safe_calculate(
                lambda: ta.sma(self.df["close"], length=isd["sma_long_period"]),
                "SMA_Long",
                min_data_points=isd["sma_long_period"],
            )
            if self.df["SMA_Long"] is not None and not self.df["SMA_Long"].empty:
                self.indicator_values["SMA_Long"] = Decimal(
                    str(self.df["SMA_Long"].iloc[-1].item())
                )

        # EMA
        if cfg["indicators"].get("ema_alignment", False):
            self.df["EMA_Short"] = self._safe_calculate(
                lambda: ta.ema(self.df["close"], length=isd["ema_short_period"]),
                "EMA_Short",
                min_data_points=isd["ema_short_period"],
            )
            self.df["EMA_Long"] = self._safe_calculate(
                lambda: ta.ema(self.df["close"], length=isd["ema_long_period"]),
                "EMA_Long",
                min_data_points=isd["ema_long_period"],
            )
            if self.df["EMA_Short"] is not None and not self.df["EMA_Short"].empty:
                self.indicator_values["EMA_Short"] = Decimal(
                    str(self.df["EMA_Short"].iloc[-1].item())
                )
            if self.df["EMA_Long"] is not None and not self.df["EMA_Long"].empty:
                self.indicator_values["EMA_Long"] = Decimal(
                    str(self.df["EMA_Long"].iloc[-1].item())
                )

        # RSI
        if cfg["indicators"].get("rsi", False):
            self.df["RSI"] = self._safe_calculate(
                lambda: ta.rsi(self.df["close"], length=isd["rsi_period"]),
                "RSI",
                min_data_points=isd["rsi_period"] + 1,
            )
            if self.df["RSI"] is not None and not self.df["RSI"].empty:
                self.indicator_values["RSI"] = float(self.df["RSI"].iloc[-1].item())

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
            if stoch_rsi_k is not None and not stoch_rsi_k.empty:
                self.indicator_values["StochRSI_K"] = float(stoch_rsi_k.iloc[-1].item())
            if stoch_rsi_d is not None and not stoch_rsi_d.empty:
                self.indicator_values["StochRSI_D"] = float(stoch_rsi_d.iloc[-1].item())

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
            if bb_upper is not None and not bb_upper.empty:
                self.indicator_values["BB_Upper"] = Decimal(
                    str(bb_upper.iloc[-1].item())
                )
            if bb_middle is not None and not bb_middle.empty:
                self.indicator_values["BB_Middle"] = Decimal(
                    str(bb_middle.iloc[-1].item())
                )
            if bb_lower is not None and not bb_lower.empty:
                self.indicator_values["BB_Lower"] = Decimal(
                    str(bb_lower.iloc[-1].item())
                )

        # CCI
        if cfg["indicators"].get("cci", False):
            self.df["CCI"] = self._safe_calculate(
                lambda: ta.cci(
                    self.df["high"],
                    self.df["low"],
                    self.df["close"],
                    length=isd["cci_period"],
                ),
                "CCI",
                min_data_points=isd["cci_period"],
            )
            if self.df["CCI"] is not None and not self.df["CCI"].empty:
                self.indicator_values["CCI"] = float(self.df["CCI"].iloc[-1].item())

        # Williams %R
        if cfg["indicators"].get("wr", False):
            self.df["WR"] = self._safe_calculate(
                lambda: ta.willr(
                    self.df["high"],
                    self.df["low"],
                    self.df["close"],
                    length=isd["williams_r_period"],
                ),
                "WR",
                min_data_points=isd["williams_r_period"],
            )
            if self.df["WR"] is not None and not self.df["WR"].empty:
                self.indicator_values["WR"] = float(self.df["WR"].iloc[-1].item())

        # MFI
        if cfg["indicators"].get("mfi", False):
            self.df["MFI"] = self._safe_calculate(
                lambda: ta.mfi(
                    self.df["high"],
                    self.df["low"],
                    self.df["close"],
                    self.df["volume"].astype(float),  # Explicitly cast volume to float
                    length=isd["mfi_period"],
                ),
                "MFI",
                min_data_points=isd["mfi_period"]
                + 1,  # MFI needs slightly more than its period
            )
            if self.df["MFI"] is not None and not self.df["MFI"].empty:
                self.indicator_values["MFI"] = float(self.df["MFI"].iloc[-1].item())

        # OBV
        if cfg["indicators"].get("obv", False):
            obv_val, obv_ema = self._safe_calculate(
                self.calculate_obv,
                "OBV",
                min_data_points=isd["obv_ema_period"]
                + 1,  # OBV itself has no period, but EMA does
                ema_period=isd["obv_ema_period"],
            )
            if obv_val is not None:
                self.df["OBV"] = obv_val
            if obv_ema is not None:
                self.df["OBV_EMA"] = obv_ema
            if obv_val is not None and not obv_val.empty:
                self.indicator_values["OBV"] = float(obv_val.iloc[-1].item())
            if obv_ema is not None and not obv_ema.empty:
                self.indicator_values["OBV_EMA"] = float(obv_ema.iloc[-1].item())

        # CMF
        if cfg["indicators"].get("cmf", False):
            cmf_val = self._safe_calculate(
                lambda: ta.cmf(
                    self.df["high"],
                    self.df["low"],
                    self.df["close"],
                    self.df["volume"],
                    length=isd["cmf_period"],
                ),
                "CMF",
                min_data_points=isd["cmf_period"],
            )
            if cmf_val is not None:
                self.df["CMF"] = cmf_val
            if cmf_val is not None and not cmf_val.empty:
                self.indicator_values["CMF"] = float(cmf_val.iloc[-1].item())

        # Ichimoku Cloud
        if cfg["indicators"].get("ichimoku_cloud", False):
            tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span = (
                self._safe_calculate(
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

            if tenkan_sen is not None and not tenkan_sen.empty:
                self.indicator_values["Tenkan_Sen"] = Decimal(
                    str(tenkan_sen.iloc[-1].item())
                )
            if kijun_sen is not None and not kijun_sen.empty:
                self.indicator_values["Kijun_Sen"] = Decimal(
                    str(kijun_sen.iloc[-1].item())
                )
            if senkou_span_a is not None and not senkou_span_a.empty:
                self.indicator_values["Senkou_Span_A"] = Decimal(
                    str(senkou_span_a.iloc[-1].item())
                )
            if senkou_span_b is not None and not senkou_span_b.empty:
                self.indicator_values["Senkou_Span_B"] = Decimal(
                    str(senkou_span_b.iloc[-1].item())
                )
            if chikou_span is not None and not chikou_span.empty:
                self.indicator_values["Chikou_Span"] = Decimal(
                    str(chikou_span.fillna(0).iloc[-1].item())
                )

        # PSAR
        if cfg["indicators"].get("psar", False):
            psar_val, psar_dir = self._safe_calculate(
                self.calculate_psar,
                "PSAR",
                min_data_points=MIN_DATA_POINTS_PSAR_INITIAL,
                acceleration=isd["psar_acceleration"],
                max_acceleration=isd["psar_max_acceleration"],
            )
            if psar_val is not None:
                self.df["PSAR_Val"] = psar_val
            if psar_dir is not None:
                self.df["PSAR_Dir"] = psar_dir
            if psar_val is not None and not psar_val.empty:
                self.indicator_values["PSAR_Val"] = Decimal(
                    str(psar_val.iloc[-1].item())
                )
            if psar_dir is not None and not psar_dir.empty:
                self.indicator_values["PSAR_Dir"] = float(psar_dir.iloc[-1].item())

        # VWAP (requires volume and turnover, which are in df)
        if cfg["indicators"].get("vwap", False):
            self.df["VWAP"] = self._safe_calculate(
                lambda: ta.vwap(
                    self.df["high"], self.df["low"], self.df["close"], self.df["volume"]
                ),
                "VWAP",
                min_data_points=1,
            )
            if self.df["VWAP"] is not None and not self.df["VWAP"].empty:
                self.indicator_values["VWAP"] = Decimal(
                    str(self.df["VWAP"].iloc[-1].item())
                )

        # --- Ehlers SuperTrend Calculation ---
        if cfg["indicators"].get("ehlers_supertrend", False):
            st_fast_result = self._safe_calculate(
                self.calculate_ehlers_supertrend,
                "EhlersSuperTrendFast",
                min_data_points=isd["ehlers_fast_period"] * 3,
                period=isd["ehlers_fast_period"],
                multiplier=isd["ehlers_fast_multiplier"],
            )
            if st_fast_result is not None and not st_fast_result.empty:
                self.df["st_fast_dir"] = st_fast_result["direction"]
                self.df["st_fast_val"] = st_fast_result["supertrend"]
                self.indicator_values["ST_Fast_Dir"] = float(
                    st_fast_result["direction"].iloc[-1].item()
                )
                self.indicator_values["ST_Fast_Val"] = Decimal(
                    str(st_fast_result["supertrend"].iloc[-1].item())
                )

            st_slow_result = self._safe_calculate(
                self.calculate_ehlers_supertrend,
                "EhlersSuperTrendSlow",
                min_data_points=isd["ehlers_slow_period"] * 3,
                period=isd["ehlers_slow_period"],
                multiplier=isd["ehlers_slow_multiplier"],
            )
            if st_slow_result is not None and not st_slow_result.empty:
                self.df["st_slow_dir"] = st_slow_result["direction"]
                self.df["st_slow_val"] = st_slow_result["supertrend"]
                self.indicator_values["ST_Slow_Dir"] = float(
                    st_slow_result["direction"].iloc[-1].item()
                )
                self.indicator_values["ST_Slow_Val"] = Decimal(
                    str(st_slow_result["supertrend"].iloc[-1].item())
                )

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
            if macd_line is not None and not macd_line.empty:
                self.indicator_values["MACD_Line"] = float(macd_line.iloc[-1].item())
            if signal_line is not None and not signal_line.empty:
                self.indicator_values["MACD_Signal"] = float(
                    signal_line.iloc[-1].item()
                )
            if histogram is not None and not histogram.empty:
                self.indicator_values["MACD_Hist"] = float(histogram.iloc[-1].item())

        # ADX
        if cfg["indicators"].get("adx", False):
            adx_val, plus_di, minus_di = self._safe_calculate(
                self.calculate_adx,
                "ADX",
                min_data_points=isd["adx_period"] * 2
                + 1,  # ADX needs more data for initial TR and smoothing
                period=isd["adx_period"],
            )
            if adx_val is not None:
                self.df["ADX"] = adx_val
            if plus_di is not None:
                self.df["PlusDI"] = plus_di
            if minus_di is not None:
                self.df["MinusDI"] = minus_di
            if adx_val is not None and not adx_val.empty:
                self.indicator_values["ADX"] = float(adx_val.iloc[-1].item())
            if plus_di is not None and not plus_di.empty:
                self.indicator_values["PlusDI"] = float(plus_di.iloc[-1].item())
            if minus_di is not None and not minus_di.empty:
                self.indicator_values["MinusDI"] = float(minus_di.iloc[-1].item())

        # --- New Indicators ---
        # Volatility Index
        if cfg["indicators"].get("volatility_index", False):
            self.df["Volatility_Index"] = self._safe_calculate(
                lambda: self.calculate_volatility_index(
                    period=isd["volatility_index_period"]
                ),
                "Volatility_Index",
                min_data_points=isd["volatility_index_period"] + 1,
            )
            if (
                self.df["Volatility_Index"] is not None
                and not self.df["Volatility_Index"].empty
            ):
                self.indicator_values["Volatility_Index"] = float(
                    self.df["Volatility_Index"].iloc[-1].item()
                )

        # VWMA
        if cfg["indicators"].get("vwma", False):
            self.df["VWMA"] = self._safe_calculate(
                lambda: self.calculate_vwma(period=isd["vwma_period"]),
                "VWMA",
                min_data_points=isd["vwma_period"],
            )
            if self.df["VWMA"] is not None and not self.df["VWMA"].empty:
                self.indicator_values["VWMA"] = Decimal(
                    str(self.df["VWMA"].iloc[-1].item())
                )

        # Volume Delta
        if cfg["indicators"].get("volume_delta", False):
            self.df["Volume_Delta"] = self._safe_calculate(
                lambda: self.calculate_volume_delta(period=isd["volume_delta_period"]),
                "Volume_Delta",
                min_data_points=isd["volume_delta_period"] + 1,
            )
            if (
                self.df["Volume_Delta"] is not None
                and not self.df["Volume_Delta"].empty
            ):
                self.indicator_values["Volume_Delta"] = float(
                    self.df["Volume_Delta"].iloc[-1].item()
                )

        # Fill any remaining NaNs in indicator columns with 0 after all calculations,
        # or use a more specific strategy based on indicator type (e.g., ffill for trends).
        # For simplicity, filling all with 0 where appropriate.
        numeric_cols = self.df.select_dtypes(include=np.number).columns
        self.df[numeric_cols] = self.df[numeric_cols].fillna(0)

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty after calculating all indicators and cleaning NaNs.{RESET}"
            )
        else:
            self.logger.debug(
                f"[{self.symbol}] Indicators calculated. Final DataFrame size: {len(self.df)}"
            )

    def calculate_true_range(self) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(self.df) < MIN_DATA_POINTS_TRUE_RANGE:
            return pd.Series(np.nan, index=self.df.index, dtype=float)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()

        tr_series = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(
            axis=1
        )
        return self._safe_series_op(tr_series, "TR")

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SUPERSMOOTHER:
            return pd.Series(np.nan, index=series.index, dtype=float)

        # Drop NaNs for calculation, reindex at the end
        series_clean = self._safe_series_op(series, "SuperSmoother_input").dropna()
        if len(series_clean) < MIN_DATA_POINTS_SUPERSMOOTHER:
            return pd.Series(np.nan, index=series.index, dtype=float)

        a1 = np.exp(-np.sqrt(2) * np.pi / period)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
        c1 = 1 - b1 + a1**2
        c2 = b1 - 2 * a1**2
        c3 = a1**2

        filt = pd.Series(np.nan, index=series_clean.index, dtype=float)
        if len(series_clean) >= 1:
            filt.iloc[0] = series_clean.iloc[0]
        if len(series_clean) >= 2:
            filt.iloc[1] = (series_clean.iloc[0] + series_clean.iloc[1]) / 2

        for i in range(2, len(series_clean)):
            filt.iloc[i] = (
                (c1 / 2) * (series_clean.iloc[i] + series_clean.iloc[i - 1])
                + c2 * filt.iloc[i - 1]
                - c3 * filt.iloc[i - 2]
            )
        # Reindex to original DataFrame index
        return filt.reindex(self.df.index)

    def calculate_ehlers_supertrend(
        self, period: int, multiplier: float
    ) -> pd.DataFrame | None:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3:
            self.logger.debug(
                f"[{self.symbol}] Not enough data for Ehlers SuperTrend (period={period}). Need at least {period * 3} bars."
            )
            return None

        df_copy = self.df.copy()

        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)

        tr = self.calculate_true_range()  # Should already be in df or calculated here
        smoothed_atr = self.calculate_super_smoother(tr, period)

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr

        # Drop NaNs introduced by smoothing to work with complete data for SuperTrend calculation
        df_clean = df_copy.dropna(
            subset=["smoothed_price", "smoothed_atr", "close", "high", "low"]
        )
        if df_clean.empty:
            self.logger.warning(
                f"[{self.symbol}] Ehlers SuperTrend (period={period}): DataFrame empty after smoothing and NaN drop. Returning None."
            )
            return None

        upper_band = df_clean["smoothed_price"] + multiplier * df_clean["smoothed_atr"]
        lower_band = df_clean["smoothed_price"] - multiplier * df_clean["smoothed_atr"]

        direction = pd.Series(np.nan, index=df_clean.index, dtype=float)
        supertrend = pd.Series(np.nan, index=df_clean.index, dtype=float)

        # Initialize the first valid supertrend value
        first_valid_idx_loc = 0
        while first_valid_idx_loc < len(df_clean) and (
            pd.isna(df_clean["close"].iloc[first_valid_idx_loc])
            or pd.isna(upper_band.iloc[first_valid_idx_loc])
            or pd.isna(lower_band.iloc[first_valid_idx_loc])
        ):
            first_valid_idx_loc += 1

        if first_valid_idx_loc >= len(df_clean):
            return None  # No valid data points

        if (
            df_clean["close"].iloc[first_valid_idx_loc]
            > upper_band.iloc[first_valid_idx_loc]
        ):
            direction.iloc[first_valid_idx_loc] = 1  # 1 for Up
            supertrend.iloc[first_valid_idx_loc] = lower_band.iloc[first_valid_idx_loc]
        else:
            direction.iloc[first_valid_idx_loc] = -1  # -1 for Down
            supertrend.iloc[first_valid_idx_loc] = upper_band.iloc[first_valid_idx_loc]

        for i in range(first_valid_idx_loc + 1, len(df_clean)):
            prev_direction = direction.iloc[i - 1]
            prev_supertrend = supertrend.iloc[i - 1]
            curr_close = df_clean["close"].iloc[i]

            if curr_close > prev_supertrend and prev_direction == -1:
                # Flip from Down to Up
                direction.iloc[i] = 1
                supertrend.iloc[i] = lower_band.iloc[i]
            elif curr_close < prev_supertrend and prev_direction == 1:
                # Flip from Up to Down
                direction.iloc[i] = -1
                supertrend.iloc[i] = upper_band.iloc[i]
            else:
                # Continue in the same direction
                direction.iloc[i] = prev_direction
                if prev_direction == 1:
                    supertrend.iloc[i] = max(lower_band.iloc[i], prev_supertrend)
                else:
                    supertrend.iloc[i] = min(upper_band.iloc[i], prev_supertrend)

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        # Reindex to original DataFrame index
        return result.reindex(self.df.index)

    def calculate_macd(
        self, fast_period: int, slow_period: int, signal_period: int
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        # pandas_ta automatically handles min_periods and NaNs
        macd_result = ta.macd(
            self.df["close"], fast=fast_period, slow=slow_period, signal=signal_period
        )
        if macd_result is None or macd_result.empty:
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series, nan_series

        macd_line = self._safe_series_op(
            macd_result[f"MACD_{fast_period}_{slow_period}_{signal_period}"],
            "MACD_Line",
        )
        signal_line = self._safe_series_op(
            macd_result[f"MACDs_{fast_period}_{slow_period}_{signal_period}"],
            "MACD_Signal",
        )
        histogram = self._safe_series_op(
            macd_result[f"MACDh_{fast_period}_{slow_period}_{signal_period}"],
            "MACD_Hist",
        )

        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        rsi = ta.rsi(self.df["close"], length=period)
        return self._safe_series_op(rsi, "RSI").fillna(0).clip(0, 100)

    def calculate_stoch_rsi(
        self, period: int, k_period: int, d_period: int
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        # pandas_ta can calculate StochRSI directly
        stoch_rsi = ta.stochrsi(
            self.df["close"], length=period, rsi_length=period, k=k_period, d=d_period
        )
        if stoch_rsi is None or stoch_rsi.empty:
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series

        stoch_k = (
            self._safe_series_op(
                stoch_rsi[f"STOCHRSIk_{period}_{period}_{k_period}_{d_period}"],
                "StochRSI_K",
            )
            .fillna(0)
            .clip(0, 100)
        )
        stoch_d = (
            self._safe_series_op(
                stoch_rsi[f"STOCHRSId_{period}_{period}_{k_period}_{d_period}"],
                "StochRSI_D",
            )
            .fillna(0)
            .clip(0, 100)
        )

        return stoch_k, stoch_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        # pandas_ta can calculate ADX directly
        adx_df = ta.adx(
            self.df["high"], self.df["low"], self.df["close"], length=period
        )
        if adx_df is None or adx_df.empty:
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series, nan_series

        adx_val = (
            self._safe_series_op(adx_df[f"ADX_{period}"], "ADX").fillna(0).clip(0, 100)
        )
        plus_di = (
            self._safe_series_op(adx_df[f"DMP_{period}"], "PlusDI")
            .fillna(0)
            .clip(0, 100)
        )
        minus_di = (
            self._safe_series_op(adx_df[f"DMN_{period}"], "MinusDI")
            .fillna(0)
            .clip(0, 100)
        )

        return adx_val, plus_di, minus_di

    def calculate_bollinger_bands(
        self, period: int, std_dev: float
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        bbands = ta.bbands(self.df["close"], length=period, std=std_dev)
        if bbands is None or bbands.empty:
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series, nan_series
        upper_band = self._safe_series_op(bbands[f"BBU_{period}_{std_dev}"], "BB_Upper")
        middle_band = self._safe_series_op(
            bbands[f"BBM_{period}_{std_dev}"], "BB_Middle"
        )
        lower_band = self._safe_series_op(bbands[f"BBL_{period}_{std_dev}"], "BB_Lower")
        return upper_band, middle_band, lower_band

    def calculate_vwap(self, daily_reset: bool = False) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty:
            return pd.Series(np.nan, index=self.df.index, dtype=float)

        # Ensure volume is numeric and not zero
        valid_volume = self.df["volume"].replace(0, np.nan).astype(float)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3

        if daily_reset:
            # Group by date and calculate cumsum within each day
            vwap_series = []
            for date, group in self.df.groupby(self.df.index.date):
                group_tp_vol = (
                    typical_price.loc[group.index] * valid_volume.loc[group.index]
                ).cumsum()
                group_vol = valid_volume.loc[group.index].cumsum()
                vwap_series.append(group_tp_vol / group_vol.replace(0, np.nan))
            vwap = pd.concat(vwap_series).reindex(self.df.index)
        else:
            # Continuous VWAP over the entire DataFrame
            cumulative_tp_vol = (typical_price * valid_volume).cumsum()
            cumulative_vol = valid_volume.cumsum()
            vwap = (cumulative_tp_vol / cumulative_vol.replace(0, np.nan)).reindex(
                self.df.index
            )

        return self._safe_series_op(
            vwap, "VWAP"
        ).ffill()  # Forward fill NaNs if volume is zero, as VWAP typically holds

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        cci = ta.cci(self.df["high"], self.df["low"], self.df["close"], length=period)
        return self._safe_series_op(cci, "CCI").fillna(0)

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        wr = ta.willr(self.df["high"], self.df["low"], self.df["close"], length=period)
        return self._safe_series_op(wr, "WR").fillna(-50).clip(-100, 0)

    def calculate_ichimoku_cloud(
        self,
        tenkan_period: int,
        kijun_period: int,
        senkou_span_b_period: int,
        chikou_span_offset: int,
    ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components using pandas_ta."""
        # Ensure enough data for Ichimoku calculation
        min_ichimoku_data = (
            max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset
        )
        if len(self.df.dropna()) < min_ichimoku_data:
            self.logger.warning(
                f"{NEON_YELLOW}Not enough clean data for Ichimoku calculation. Need at least {min_ichimoku_data} bars, have {len(self.df.dropna())}. Returning NaN series.{RESET}"
            )
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series, nan_series, nan_series, nan_series

        ichimoku_result = ta.ichimoku(
            self.df["high"],
            self.df["low"],
            self.df["close"],
            tenkan=tenkan_period,
            kijun=kijun_period,
            senkou=senkou_span_b_period,
            offset=chikou_span_offset,
            append=False,  # Do not append to self.df directly, we'll handle it
        )

        # pandas_ta.ichimoku returns a tuple of (DataFrame, DataFrame)
        # The first DataFrame contains the Tenkan, Kijun, Senkou Span A, Senkou Span B
        # The second DataFrame contains the Chikou Span
        if ichimoku_result is None or len(ichimoku_result) < 2:
            self.logger.warning(
                f"{NEON_YELLOW}pandas_ta.ichimoku returned insufficient data.{RESET}"
            )
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series, nan_series, nan_series, nan_series

        ichimoku_df = ichimoku_result[0]
        chikou_span_df = ichimoku_result[1]

        nan_series = pd.Series(np.nan, index=self.df.index)

        # Helper to safely get a series or return NaN series
        def _get_safe_series(df_to_check, col_name, default_name):
            if df_to_check is not None and col_name in df_to_check.columns:
                return self._safe_series_op(df_to_check[col_name], default_name)
            self.logger.warning(
                f"{NEON_YELLOW}Ichimoku column '{col_name}' not found. Returning NaN series for {default_name}.{RESET}"
            )
            return nan_series

        tenkan_sen = _get_safe_series(ichimoku_df, f"ITS_{tenkan_period}", "Tenkan_Sen")
        kijun_sen = _get_safe_series(ichimoku_df, f"KJS_{kijun_period}", "Kijun_Sen")
        senkou_span_a = _get_safe_series(
            ichimoku_df, f"SSA_{kijun_period}", "Senkou_Span_A"
        )  # SSA uses kijun_period for offset
        senkou_span_b = _get_safe_series(
            ichimoku_df, f"SSB_{senkou_span_b_period}", "Senkou_Span_B"
        )
        chikou_span = _get_safe_series(
            chikou_span_df, f"CS_{chikou_span_offset}", "Chikou_Span"
        ).fillna(0)

        return (
            self._safe_series_op(tenkan_sen, "Tenkan_Sen"),
            self._safe_series_op(kijun_sen, "Kijun_Sen"),
            self._safe_series_op(senkou_span_a, "Senkou_Span_A"),
            self._safe_series_op(senkou_span_b, "Senkou_Span_B"),
            self._safe_series_op(chikou_span, "Chikou_Span"),
        )

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        mfi = ta.mfi(
            self.df["high"],
            self.df["low"],
            self.df["close"],
            self.df["volume"],
            length=period,
        )
        return self._safe_series_op(mfi, "MFI").fillna(50).clip(0, 100)

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        obv = ta.obv(self.df["close"], self.df["volume"])
        obv_ema = ta.ema(obv, length=ema_period)

        return self._safe_series_op(obv, "OBV"), self._safe_series_op(
            obv_ema, "OBV_EMA"
        )

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        cmf = ta.cmf(
            self.df["high"],
            self.df["low"],
            self.df["close"],
            self.df["volume"],
            length=period,
        )
        return self._safe_series_op(cmf, "CMF").fillna(0).clip(-1, 1)

    def calculate_psar(
        self, acceleration: float, max_acceleration: float
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        # Use pandas_ta for PSAR calculation
        psar_result = ta.psar(
            self.df["high"],
            self.df["low"],
            self.df["close"],
            af0=acceleration,
            af=acceleration,
            max_af=max_acceleration,
        )
        if psar_result is None or psar_result.empty:
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series

        # pandas_ta returns PSAR value and PSAR direction columns (long/short signal)
        psar_val_col = f"PSARr_{acceleration}_{max_acceleration}"
        psar_long_col = f"PSARl_{acceleration}_{max_acceleration}"
        psar_short_col = f"PSARs_{acceleration}_{max_acceleration}"

        if psar_val_col not in psar_result.columns:
            self.logger.error(
                f"{NEON_RED}Missing expected PSAR column '{psar_val_col}' in result: {psar_result.columns.tolist()}{RESET}"
            )
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series

        psar_val = self._safe_series_op(psar_result[psar_val_col], "PSAR_Val")

        # Determine direction based on long/short signals
        direction = pd.Series(0, index=self.df.index, dtype=int)

        # 1 if in uptrend (PSAR_LONG is not NaN), -1 if in downtrend (PSAR_SHORT is not NaN)
        # Assuming PSAR_LONG and PSAR_SHORT are mutually exclusive
        direction[psar_result[psar_long_col].notna()] = 1
        direction[psar_result[psar_short_col].notna()] = -1

        # Fill any remaining initial NaNs with 0
        direction.fillna(0, inplace=True)
        return psar_val, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Not enough data for Fibonacci levels (need {window} bars).{RESET}"
            )
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()

        diff = recent_high - recent_low

        decimal_high = Decimal(str(recent_high.item()))
        decimal_low = Decimal(str(recent_low.item()))
        decimal_diff = Decimal(str(diff.item()))

        # Use PrecisionManager for price formatting
        self.fib_levels = {
            "0.0%": self.precision_manager.format_price(decimal_high),
            "23.6%": self.precision_manager.format_price(
                decimal_high - Decimal("0.236") * decimal_diff
            ),
            "38.2%": self.precision_manager.format_price(
                decimal_high - Decimal("0.382") * decimal_diff
            ),
            "50.0%": self.precision_manager.format_price(
                decimal_high - Decimal("0.500") * decimal_diff
            ),
            "61.8%": self.precision_manager.format_price(
                decimal_high - Decimal("0.618") * decimal_diff
            ),
            "78.6%": self.precision_manager.format_price(
                decimal_high - Decimal("0.786") * decimal_diff
            ),
            "100.0%": self.precision_manager.format_price(decimal_low),
        }
        self.logger.debug(
            f"[{self.symbol}] Calculated Fibonacci levels: {self.fib_levels}"
        )

    def calculate_volatility_index(self, period: int) -> pd.Series:
        """Calculate a simple Volatility Index based on ATR normalized by price."""
        if (
            len(self.df) < period
            or "ATR" not in self.df.columns
            or self.df["ATR"].isnull().all()
        ):
            return pd.Series(np.nan, index=self.df.index, dtype=float)

        # ATR is already calculated
        # Avoid division by zero for close price
        normalized_atr = self.df["ATR"] / self.df["close"].replace(0, np.nan)
        volatility_index = normalized_atr.rolling(
            window=period, min_periods=MIN_DATA_POINTS_VOLATILITY
        ).mean()
        return self._safe_series_op(volatility_index, "Volatility_Index").fillna(0)

    def calculate_vwma(self, period: int) -> pd.Series:
        """Calculate Volume Weighted Moving Average (VWMA)."""
        if len(self.df) < period or self.df["volume"].isnull().any():
            return pd.Series(np.nan, index=self.df.index, dtype=float)

        # Ensure volume is numeric and not zero
        valid_volume = self.df["volume"].replace(0, np.nan).astype(float)
        pv = self.df["close"] * valid_volume
        # Use min_periods for rolling sums
        vwma = pv.rolling(window=period, min_periods=1).sum() / valid_volume.rolling(
            window=period, min_periods=1
        ).sum().replace(0, np.nan)
        return self._safe_series_op(
            vwma, "VWMA"
        ).ffill()  # Forward fill NaNs if volume is zero, as VWMA typically holds

    def calculate_volume_delta(self, period: int) -> pd.Series:
        """Calculate Volume Delta, indicating buying vs selling pressure."""
        if len(self.df) < MIN_DATA_POINTS_VOLUME_DELTA:
            return pd.Series(np.nan, index=self.df.index, dtype=float)

        # Approximate buy/sell volume based on close relative to open
        buy_volume = self.df["volume"].where(self.df["close"] > self.df["open"], 0)
        sell_volume = self.df["volume"].where(self.df["close"] < self.df["open"], 0)

        # Rolling sum of buy/sell volume
        buy_volume_sum = buy_volume.rolling(window=period, min_periods=1).sum()
        sell_volume_sum = sell_volume.rolling(window=period, min_periods=1).sum()

        total_volume_sum = buy_volume_sum + sell_volume_sum
        # Avoid division by zero
        volume_delta = (buy_volume_sum - sell_volume_sum) / total_volume_sum.replace(
            0, np.nan
        )
        return self._safe_series_op(volume_delta.fillna(0), "Volume_Delta").clip(
            -1, 1
        )  # Fill NaNs with 0, clip to [-1, 1]

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_manager: Any) -> float:
        """Analyze orderbook imbalance. Placeholder as AdvancedOrderbookManager is not provided."""
        # This method requires access to the orderbook_manager instance,
        # which should be passed during initialization or to the signal generation method.
        # For a full implementation, this would involve fetching real-time order book data
        # via WebSocket and calculating bid/ask volume imbalance.
        if not orderbook_manager:
            self.logger.debug(
                "Orderbook manager not available for imbalance check. Returning 0.0."
            )
            return 0.0

        self.logger.warning(
            f"{NEON_YELLOW}Orderbook imbalance calculation is a placeholder and not fully implemented. Returning 0.0.{RESET}"
        )
        # Placeholder logic if orderbook_manager were implemented:
        # bids, asks = orderbook_manager.get_depth(self.config["orderbook_limit"])
        # bid_volume = sum(Decimal(str(b.quantity)) for b in bids)
        # ask_volume = sum(Decimal(str(a.quantity)) for a in asks)
        # total_volume = bid_volume + ask_volume
        # if total_volume == 0:
        #     return 0.0
        # imbalance = (bid_volume - ask_volume) / total_volume
        # self.logger.debug(
        #     f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume.normalize()}, Asks: {ask_volume.normalize()})"
        # )
        # return float(imbalance)
        return 0.0

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty:
            return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        # Create a temporary TradingAnalyzer for the HTF data to calculate indicators
        # This ensures proper initialization and data handling for HTF specific indicators
        temp_htf_analyzer = TradingAnalyzer(
            higher_tf_df, self.config, self.logger, self.symbol, self.precision_manager
        )

        if indicator_type == "sma":
            sma = temp_htf_analyzer._safe_calculate(
                lambda: ta.sma(temp_htf_analyzer.df["close"], length=period),
                f"MTF_SMA_{period}",
                min_data_points=period,
            )
            if sma is not None and not sma.empty and not pd.isna(sma.iloc[-1]):
                if last_close > sma.iloc[-1]:
                    return "UP"
                if last_close < sma.iloc[-1]:
                    return "DOWN"
            return "SIDEWAYS"
        if indicator_type == "ema":
            ema = temp_htf_analyzer._safe_calculate(
                lambda: ta.ema(temp_htf_analyzer.df["close"], length=period),
                f"MTF_EMA_{period}",
                min_data_points=period,
            )
            if ema is not None and not ema.empty and not pd.isna(ema.iloc[-1]):
                if last_close > ema.iloc[-1]:
                    return "UP"
                if last_close < ema.iloc[-1]:
                    return "DOWN"
            return "SIDEWAYS"
        if indicator_type == "ehlers_supertrend":
            st_result = temp_htf_analyzer._safe_calculate(
                temp_htf_analyzer.calculate_ehlers_supertrend,
                "MTF_EhlersSuperTrend",
                min_data_points=temp_htf_analyzer.indicator_settings[
                    "ehlers_slow_period"
                ]
                * 3,
                period=temp_htf_analyzer.indicator_settings["ehlers_slow_period"],
                multiplier=temp_htf_analyzer.indicator_settings[
                    "ehlers_slow_multiplier"
                ],
            )
            if (
                st_result is not None
                and not st_result.empty
                and not pd.isna(st_result["direction"].iloc[-1])
            ):
                st_dir = float(st_result["direction"].iloc[-1].item())
                if st_dir == 1:
                    return "UP"
                if st_dir == -1:
                    return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    # --- Signal Scoring Helper Methods ---
    def _score_ema_alignment(self, signal_score: float) -> float:
        ema_short = self._get_indicator_value("EMA_Short")
        ema_long = self._get_indicator_value("EMA_Long")
        weight = self.weights.get("ema_alignment", 0)

        if not pd.isna(ema_short) and not pd.isna(ema_long):
            if ema_short > ema_long:
                signal_score += weight
                self.logger.debug(f"  EMA Alignment: Bullish (+{weight:.2f})")
            elif ema_short < ema_long:
                signal_score -= weight
                self.logger.debug(f"  EMA Alignment: Bearish (-{weight:.2f})")
        return signal_score

    def _score_sma_trend_filter(
        self, current_close: Decimal, signal_score: float
    ) -> float:
        sma_long = self._get_indicator_value("SMA_Long")
        weight = self.weights.get("sma_trend_filter", 0)

        if not pd.isna(sma_long):
            if current_close > sma_long:
                signal_score += weight
                self.logger.debug(f"  SMA Trend Filter: Bullish (+{weight:.2f})")
            elif current_close < sma_long:
                signal_score -= weight
                self.logger.debug(f"  SMA Trend Filter: Bearish (-{weight:.2f})")
        return signal_score

    def _score_momentum_indicators(self, signal_score: float) -> float:
        active_indicators = self.config["indicators"]
        isd = self.indicator_settings
        momentum_weight = self.weights.get("momentum_rsi_stoch_cci_wr_mfi", 0)

        # RSI
        if active_indicators.get("rsi", False):
            rsi = self._get_indicator_value("RSI")
            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]:
                    signal_score += momentum_weight * 0.5
                    self.logger.debug(f"  RSI: Oversold (+{momentum_weight * 0.5:.2f})")
                elif rsi > isd["rsi_overbought"]:
                    signal_score -= momentum_weight * 0.5
                    self.logger.debug(
                        f"  RSI: Overbought (-{momentum_weight * 0.5:.2f})"
                    )

        # StochRSI Crossover
        if active_indicators.get("stoch_rsi", False):
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            if not pd.isna(stoch_k) and not pd.isna(stoch_d) and len(self.df) > 1:
                prev_stoch_k = (
                    self.df["StochRSI_K"].iloc[-2].item()
                    if "StochRSI_K" in self.df.columns
                    and not pd.isna(self.df["StochRSI_K"].iloc[-2])
                    else np.nan
                )
                prev_stoch_d = (
                    self.df["StochRSI_D"].iloc[-2].item()
                    if "StochRSI_D" in self.df.columns
                    and not pd.isna(self.df["StochRSI_D"].iloc[-2])
                    else np.nan
                )
                if (
                    stoch_k > stoch_d
                    and (pd.isna(prev_stoch_k) or prev_stoch_k <= prev_stoch_d)
                    and stoch_k < isd["stoch_rsi_oversold"]
                ):
                    signal_score += momentum_weight * 0.6
                    self.logger.debug(
                        f"  StochRSI: Bullish crossover from oversold (+{momentum_weight * 0.6:.2f})"
                    )
                elif (
                    stoch_k < stoch_d
                    and (pd.isna(prev_stoch_k) or prev_stoch_k >= prev_stoch_d)
                    and stoch_k > isd["stoch_rsi_overbought"]
                ):
                    signal_score -= momentum_weight * 0.6
                    self.logger.debug(
                        f"  StochRSI: Bearish crossover from overbought (-{momentum_weight * 0.6:.2f})"
                    )
                elif stoch_k > stoch_d and stoch_k < 50:  # General bullish momentum
                    signal_score += momentum_weight * 0.2
                    self.logger.debug(
                        f"  StochRSI: General bullish momentum (+{momentum_weight * 0.2:.2f})"
                    )
                elif stoch_k < stoch_d and stoch_k > 50:  # General bearish momentum
                    signal_score -= momentum_weight * 0.2
                    self.logger.debug(
                        f"  StochRSI: General bearish momentum (-{momentum_weight * 0.2:.2f})"
                    )

            # CCI
            if active_indicators.get("cci", False):
                cci = self._get_indicator_value("CCI")
                if not pd.isna(cci):
                    if cci < isd["cci_oversold"]:
                        signal_score += momentum_weight * 0.4
                        self.logger.debug(
                            f"  CCI: Oversold (+{momentum_weight * 0.4:.2f})"
                        )
                    elif cci > isd["cci_overbought"]:
                        signal_score -= momentum_weight * 0.4
                        self.logger.debug(
                            f"  CCI: Overbought (-{momentum_weight * 0.4:.2f})"
                        )

            # Williams %R
            if active_indicators.get("wr", False):
                wr = self._get_indicator_value("WR")
                if not pd.isna(wr):
                    if wr < isd["williams_r_oversold"]:
                        signal_score += momentum_weight * 0.4
                        self.logger.debug(
                            f"  WR: Oversold (+{momentum_weight * 0.4:.2f})"
                        )
                    elif wr > isd["williams_r_overbought"]:
                        signal_score -= momentum_weight * 0.4
                        self.logger.debug(
                            f"  WR: Overbought (-{momentum_weight * 0.4:.2f})"
                        )

            # MFI
            if active_indicators.get("mfi", False):
                mfi = self._get_indicator_value("MFI")
                if not pd.isna(mfi):
                    if mfi < isd["mfi_oversold"]:
                        signal_score += momentum_weight * 0.4
                        self.logger.debug(
                            f"  MFI: Oversold (+{momentum_weight * 0.4:.2f})"
                        )
                    elif mfi > isd["mfi_overbought"]:
                        signal_score -= momentum_weight * 0.4
                        self.logger.debug(
                            f"  MFI: Overbought (-{momentum_weight * 0.4:.2f})"
                        )
        return signal_score

    def _score_bollinger_bands(
        self, current_close: Decimal, signal_score: float
    ) -> float:
        bb_upper = self._get_indicator_value("BB_Upper")
        bb_lower = self._get_indicator_value("BB_Lower")
        weight = self.weights.get("bollinger_bands", 0)

        if not pd.isna(bb_upper) and not pd.isna(bb_lower):
            if current_close < bb_lower:
                signal_score += weight * 0.5
                self.logger.debug(f"  BB: Price below lower band (+{weight * 0.5:.2f})")
            elif current_close > bb_upper:
                signal_score -= weight * 0.5
                self.logger.debug(f"  BB: Price above upper band (-{weight * 0.5:.2f})")
        return signal_score

    def _score_vwap(
        self, current_close: Decimal, prev_close: Decimal, signal_score: float
    ) -> float:
        vwap = self._get_indicator_value("VWAP")
        weight = self.weights.get("vwap", 0)

        if not pd.isna(vwap):
            if current_close > vwap:
                signal_score += weight * 0.2
                self.logger.debug(f"  VWAP: Price above VWAP (+{weight * 0.2:.2f})")
            elif current_close < vwap:
                signal_score -= weight * 0.2
                self.logger.debug(f"  VWAP: Price below VWAP (-{weight * 0.2:.2f})")

            if len(self.df) > 1 and not pd.isna(prev_close):
                prev_vwap_series = (
                    self.df["VWAP"].iloc[-2].item()
                    if "VWAP" in self.df.columns
                    and not pd.isna(self.df["VWAP"].iloc[-2])
                    else np.nan
                )
                prev_vwap = (
                    Decimal(str(prev_vwap_series))
                    if not pd.isna(prev_vwap_series)
                    else vwap
                )
                if current_close > vwap and prev_close <= prev_vwap:
                    signal_score += weight * 0.3
                    self.logger.debug(
                        f"  VWAP: Bullish crossover detected (+{weight * 0.3:.2f})"
                    )
                elif current_close < vwap and prev_close >= prev_vwap:
                    signal_score -= weight * 0.3
                    self.logger.debug(
                        f"  VWAP: Bearish crossover detected (-{weight * 0.3:.2f})"
                    )
        return signal_score

    def _score_psar(
        self, current_close: Decimal, prev_close: Decimal, signal_score: float
    ) -> float:
        psar_val = self._get_indicator_value("PSAR_Val")
        psar_dir = self._get_indicator_value("PSAR_Dir")
        weight = self.weights.get("psar", 0)

        if not pd.isna(psar_val) and not pd.isna(psar_dir):
            if psar_dir == 1:  # Bullish direction
                signal_score += weight * 0.5
                self.logger.debug(f"  PSAR: Bullish direction (+{weight * 0.5:.2f})")
            elif psar_dir == -1:  # Bearish direction
                signal_score -= weight * 0.5
                self.logger.debug(f"  PSAR: Bearish direction (-{weight * 0.5:.2f})")

            if len(self.df) > 1 and not pd.isna(prev_close):
                prev_psar_val_series = (
                    self.df["PSAR_Val"].iloc[-2].item()
                    if "PSAR_Val" in self.df.columns
                    and not pd.isna(self.df["PSAR_Val"].iloc[-2])
                    else np.nan
                )
                prev_psar_val = (
                    Decimal(str(prev_psar_val_series))
                    if not pd.isna(prev_psar_val_series)
                    else psar_val
                )
                if current_close > psar_val and prev_close <= prev_psar_val:
                    signal_score += weight * 0.4
                    self.logger.debug(
                        f"  PSAR: Bullish reversal detected (+{weight * 0.4:.2f})"
                    )
                elif current_close < psar_val and prev_close >= prev_psar_val:
                    signal_score -= weight * 0.4
                    self.logger.debug(
                        f"  PSAR: Bearish reversal detected (-{weight * 0.4:.2f})"
                    )
        return signal_score

    def _score_fibonacci_levels(
        self, current_price: Decimal, prev_close: Decimal, signal_score: float
    ) -> float:
        weight = self.weights.get("fibonacci_levels", 0)

        if self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                # Check if price is within a very small proximity of a Fibonacci level
                # Use a small epsilon for floating point comparison with Decimal
                epsilon = Decimal("0.0001") * level_price  # 0.01%

                if level_name not in ["0.0%", "100.0%"] and (
                    (level_price - epsilon) <= current_price <= (level_price + epsilon)
                ):
                    self.logger.debug(
                        f"  Price near Fibonacci level {level_name}: {level_price.normalize()}"
                    )
                    if len(self.df) > 1 and not pd.isna(prev_close):
                        if current_price > prev_close and current_price > level_price:
                            signal_score += weight * 0.1
                            self.logger.debug(
                                f"  Fibonacci: Bullish breakout/bounce (+{weight * 0.1:.2f})"
                            )
                        elif current_price < prev_close and current_price < level_price:
                            signal_score -= weight * 0.1
                            self.logger.debug(
                                f"  Fibonacci: Bearish breakout/bounce (-{weight * 0.1:.2f})"
                            )
        return signal_score

    def _score_ehlers_supertrend_alignment(self, signal_score: float) -> float:
        st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
        st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
        weight = self.weights.get("ehlers_supertrend_alignment", 0.0)

        prev_st_fast_dir_series = (
            self.df["st_fast_dir"].iloc[-2].item()
            if "st_fast_dir" in self.df.columns
            and len(self.df) > 1
            and not pd.isna(self.df["st_fast_dir"].iloc[-2])
            else np.nan
        )
        prev_st_fast_dir = (
            float(prev_st_fast_dir_series)
            if not pd.isna(prev_st_fast_dir_series)
            else np.nan
        )

        if (
            not pd.isna(st_fast_dir)
            and not pd.isna(st_slow_dir)
            and not pd.isna(prev_st_fast_dir)  # Check for previous value for crossover
        ):
            if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
                signal_score += weight
                self.logger.debug(
                    f"Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend) (+{weight:.2f})."
                )
            elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
                signal_score -= weight
                self.logger.debug(
                    f"Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend) (-{weight:.2f})."
                )
            elif st_slow_dir == 1 and st_fast_dir == 1:
                signal_score += weight * 0.3
                self.logger.debug(
                    f"Ehlers SuperTrend: Bullish alignment (+{weight * 0.3:.2f})."
                )
            elif st_slow_dir == -1 and st_fast_dir == -1:
                signal_score -= weight * 0.3
                self.logger.debug(
                    f"Ehlers SuperTrend: Bearish alignment (-{weight * 0.3:.2f})."
                )
        return signal_score

    def _score_macd_alignment(self, signal_score: float) -> float:
        macd_line = self._get_indicator_value("MACD_Line")
        signal_line = self._get_indicator_value("MACD_Signal")
        histogram = self._get_indicator_value("MACD_Hist")
        weight = self.weights.get("macd_alignment", 0.0)

        if (
            not pd.isna(macd_line)
            and not pd.isna(signal_line)
            and not pd.isna(histogram)
            and len(self.df) > 1
        ):
            prev_macd_line = (
                self.df["MACD_Line"].iloc[-2].item()
                if "MACD_Line" in self.df.columns
                and not pd.isna(self.df["MACD_Line"].iloc[-2])
                else np.nan
            )
            prev_signal_line = (
                self.df["MACD_Signal"].iloc[-2].item()
                if "MACD_Signal" in self.df.columns
                and not pd.isna(self.df["MACD_Signal"].iloc[-2])
                else np.nan
            )

            if macd_line > signal_line and (
                pd.isna(prev_macd_line) or prev_macd_line <= prev_signal_line
            ):
                signal_score += weight
                self.logger.debug(
                    f"MACD: BUY signal (MACD line crossed above Signal line) (+{weight:.2f})."
                )
            elif macd_line < signal_line and (
                pd.isna(prev_macd_line) or prev_macd_line >= prev_signal_line
            ):
                signal_score -= weight
                self.logger.debug(
                    f"MACD: SELL signal (MACD line crossed below Signal line) (-{weight:.2f})."
                )
            elif histogram > 0 and (
                len(self.df) > 2
                and "MACD_Hist" in self.df.columns
                and self.df["MACD_Hist"].iloc[-2].item() < 0
            ):
                signal_score += weight * 0.2
                self.logger.debug(
                    f"MACD: Histogram turned positive (+{weight * 0.2:.2f})."
                )
            elif histogram < 0 and (
                len(self.df) > 2
                and "MACD_Hist" in self.df.columns
                and self.df["MACD_Hist"].iloc[-2].item() > 0
            ):
                signal_score -= weight * 0.2
                self.logger.debug(
                    f"MACD: Histogram turned negative (-{weight * 0.2:.2f})."
                )
        return signal_score

    def _score_adx_strength(self, signal_score: float) -> float:
        adx_val = self._get_indicator_value("ADX")
        plus_di = self._get_indicator_value("PlusDI")
        minus_di = self._get_indicator_value("MinusDI")
        weight = self.weights.get("adx_strength", 0.0)

        if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
            if adx_val > ADX_STRONG_TREND_THRESHOLD:
                if plus_di > minus_di:
                    signal_score += weight
                    self.logger.debug(
                        f"ADX: Strong BUY trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, +DI > -DI) (+{weight:.2f})."
                    )
                elif minus_di > plus_di:
                    signal_score -= weight
                    self.logger.debug(
                        f"ADX: Strong SELL trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, -DI > +DI) (-{weight:.2f})."
                    )
            elif adx_val < ADX_WEAK_TREND_THRESHOLD:
                # Neutral signal if trend is weak
                self.logger.debug(
                    f"ADX: Weak trend (ADX < {ADX_WEAK_TREND_THRESHOLD}). Neutral signal."
                )
        return signal_score

    def _score_ichimoku_confluence(
        self, current_close: Decimal, prev_close: Decimal, signal_score: float
    ) -> float:
        tenkan_sen = self._get_indicator_value("Tenkan_Sen")
        kijun_sen = self._get_indicator_value("Kijun_Sen")
        senkou_span_a = self._get_indicator_value("Senkou_Span_A")
        senkou_span_b = self._get_indicator_value("Senkou_Span_B")
        chikou_span = self._get_indicator_value("Chikou_Span")
        weight = self.weights.get("ichimoku_confluence", 0.0)

        if (
            not pd.isna(tenkan_sen)
            and not pd.isna(kijun_sen)
            and not pd.isna(senkou_span_a)
            and not pd.isna(senkou_span_b)
            and not pd.isna(chikou_span)
            and len(self.df) > 1
        ):
            prev_tenkan = (
                self.df["Tenkan_Sen"].iloc[-2].item()
                if "Tenkan_Sen" in self.df.columns
                and not pd.isna(self.df["Tenkan_Sen"].iloc[-2])
                else np.nan
            )
            prev_kijun = (
                self.df["Kijun_Sen"].iloc[-2].item()
                if "Kijun_Sen" in self.df.columns
                and not pd.isna(self.df["Kijun_Sen"].iloc[-2])
                else np.nan
            )
            prev_senkou_a = (
                self.df["Senkou_Span_A"].iloc[-2].item()
                if "Senkou_Span_A" in self.df.columns
                and not pd.isna(self.df["Senkou_Span_A"].iloc[-2])
                else np.nan
            )
            prev_senkou_b = (
                self.df["Senkou_Span_B"].iloc[-2].item()
                if "Senkou_Span_B" in self.df.columns
                and not pd.isna(self.df["Senkou_Span_B"].iloc[-2])
                else np.nan
            )
            prev_chikou = (
                self.df["Chikou_Span"].iloc[-2].item()
                if "Chikou_Span" in self.df.columns
                and not pd.isna(self.df["Chikou_Span"].iloc[-2])
                else np.nan
            )

            # Tenkan-sen / Kijun-sen crossover
            if tenkan_sen > kijun_sen and (
                pd.isna(prev_tenkan) or prev_tenkan <= prev_kijun
            ):
                signal_score += weight * 0.5
                self.logger.debug(
                    f"Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish) (+{weight * 0.5:.2f})."
                )
            elif tenkan_sen < kijun_sen and (
                pd.isna(prev_tenkan) or prev_tenkan >= prev_kijun
            ):
                signal_score -= weight * 0.5
                self.logger.debug(
                    f"Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish) (-{weight * 0.5:.2f})."
                )

            # Price breaking above/below Kumo (Cloud)
            kumo_top = max(senkou_span_a, senkou_span_b)
            kumo_bottom = min(senkou_span_a, senkou_span_b)
            prev_kumo_top = (
                max(Decimal(str(prev_senkou_a)), Decimal(str(prev_senkou_b)))
                if not pd.isna(prev_senkou_a) and not pd.isna(prev_senkou_b)
                else Decimal("0")
            )
            prev_kumo_bottom = (
                min(Decimal(str(prev_senkou_a)), Decimal(str(prev_senkou_b)))
                if not pd.isna(prev_senkou_a) and not pd.isna(prev_senkou_b)
                else Decimal("0")
            )

            if current_close > kumo_top and prev_close <= prev_kumo_top:
                signal_score += weight * 0.7
                self.logger.debug(
                    f"Ichimoku: Price broke above Kumo (strong bullish) (+{weight * 0.7:.2f})."
                )
            elif current_close < kumo_bottom and prev_close >= prev_kumo_bottom:
                signal_score -= weight * 0.7
                self.logger.debug(
                    f"Ichimoku: Price broke below Kumo (strong bearish) (-{weight * 0.7:.2f})."
                )

            # Chikou Span crossing price (confirmation)
            if chikou_span > current_close and (
                pd.isna(prev_chikou) or prev_chikou <= prev_close
            ):
                signal_score += weight * 0.3
                self.logger.debug(
                    f"Ichimoku: Chikou Span crossed above price (bullish confirmation) (+{weight * 0.3:.2f})."
                )
            elif chikou_span < current_close and (
                pd.isna(prev_chikou) or prev_chikou >= prev_close
            ):
                signal_score -= weight * 0.3
                self.logger.debug(
                    f"Ichimoku: Chikou Span crossed below price (bearish confirmation) (-{weight * 0.3:.2f})."
                )
        return signal_score

    def _score_obv_momentum(self, signal_score: float) -> float:
        obv_val = self._get_indicator_value("OBV")
        obv_ema = self._get_indicator_value("OBV_EMA")
        weight = self.weights.get("obv_momentum", 0.0)

        if not pd.isna(obv_val) and not pd.isna(obv_ema) and len(self.df) > 1:
            prev_obv_val = (
                self.df["OBV"].iloc[-2].item()
                if "OBV" in self.df.columns and not pd.isna(self.df["OBV"].iloc[-2])
                else np.nan
            )
            prev_obv_ema = (
                self.df["OBV_EMA"].iloc[-2].item()
                if "OBV_EMA" in self.df.columns
                and not pd.isna(self.df["OBV_EMA"].iloc[-2])
                else np.nan
            )

            if obv_val > obv_ema and (
                pd.isna(prev_obv_val) or prev_obv_val <= prev_obv_ema
            ):
                signal_score += weight * 0.5
                self.logger.debug(
                    f"  OBV: Bullish crossover detected (+{weight * 0.5:.2f})."
                )
            elif obv_val < obv_ema and (
                pd.isna(prev_obv_val) or prev_obv_val >= prev_obv_ema
            ):
                signal_score -= weight * 0.5
                self.logger.debug(
                    f"  OBV: Bearish crossover detected (-{weight * 0.5:.2f})."
                )

            if len(self.df) > 2 and "OBV" in self.df.columns:
                if (
                    obv_val > self.df["OBV"].iloc[-2].item()
                    and obv_val > self.df["OBV"].iloc[-3].item()
                ):
                    signal_score += weight * 0.2
                    self.logger.debug(
                        f"  OBV: Increasing momentum (+{weight * 0.2:.2f})."
                    )
                elif (
                    obv_val < self.df["OBV"].iloc[-2].item()
                    and obv_val < self.df["OBV"].iloc[-3].item()
                ):
                    signal_score -= weight * 0.2
                    self.logger.debug(
                        f"  OBV: Decreasing momentum (-{weight * 0.2:.2f})."
                    )
        return signal_score

    def _score_cmf_flow(self, signal_score: float) -> float:
        cmf_val = self._get_indicator_value("CMF")
        weight = self.weights.get("cmf_flow", 0.0)

        if not pd.isna(cmf_val):
            if cmf_val > 0:
                signal_score += weight * 0.5
                self.logger.debug(f"  CMF: Positive money flow (+{weight * 0.5:.2f}).")
            elif cmf_val < 0:
                signal_score -= weight * 0.5
                self.logger.debug(f"  CMF: Negative money flow (-{weight * 0.5:.2f}).")

            if len(self.df) > 2 and "CMF" in self.df.columns:
                if (
                    cmf_val > self.df["CMF"].iloc[-2].item()
                    and cmf_val > self.df["CMF"].iloc[-3].item()
                ):
                    signal_score += weight * 0.3
                    self.logger.debug(
                        f"  CMF: Increasing bullish flow (+{weight * 0.3:.2f})."
                    )
                elif (
                    cmf_val < self.df["CMF"].iloc[-2].item()
                    and cmf_val < self.df["CMF"].iloc[-3].item()
                ):
                    signal_score -= weight * 0.3
                    self.logger.debug(
                        f"  CMF: Increasing bearish flow (-{weight * 0.3:.2f})."
                    )
        return signal_score

    def _score_volatility_index(self, signal_score: float) -> float:
        vol_idx = self._get_indicator_value("Volatility_Index")
        weight = self.weights.get("volatility_index_signal", 0.0)
        if (
            not pd.isna(vol_idx)
            and len(self.df) > 2
            and "Volatility_Index" in self.df.columns
        ):
            prev_vol_idx = self.df["Volatility_Index"].iloc[-2].item()
            prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3].item()

            if vol_idx > prev_vol_idx > prev_prev_vol_idx:  # Increasing volatility
                if signal_score > 0:
                    signal_score += weight * 0.2
                    self.logger.debug(
                        f"  Volatility Index: Increasing volatility, adds confidence to BUY (+{weight * 0.2:.2f})."
                    )
                elif signal_score < 0:
                    signal_score -= weight * 0.2
                    self.logger.debug(
                        f"  Volatility Index: Increasing volatility, adds confidence to SELL (-{weight * 0.2:.2f})."
                    )
            elif vol_idx < prev_vol_idx < prev_prev_vol_idx:  # Decreasing volatility
                if (
                    abs(signal_score) > 0
                ):  # If there's an existing signal, slightly reduce its conviction
                    signal_score *= 1 - weight * 0.1  # Reduce by 10% of the weight
                    self.logger.debug(
                        f"  Volatility Index: Decreasing volatility, reduces signal conviction (x{(1 - weight * 0.1):.2f})."
                    )
        return signal_score

    def _score_vwma_cross(
        self, current_close: Decimal, prev_close: Decimal, signal_score: float
    ) -> float:
        vwma = self._get_indicator_value("VWMA")
        weight = self.weights.get("vwma_cross", 0.0)
        if not pd.isna(vwma) and len(self.df) > 1 and not pd.isna(prev_close):
            prev_vwma_series = (
                self.df["VWMA"].iloc[-2].item()
                if "VWMA" in self.df.columns and not pd.isna(self.df["VWMA"].iloc[-2])
                else np.nan
            )
            prev_vwma = (
                Decimal(str(prev_vwma_series))
                if not pd.isna(prev_vwma_series)
                else vwma
            )
            if current_close > vwma and prev_close <= prev_vwma:
                signal_score += weight
                self.logger.debug(
                    f"  VWMA: Bullish crossover (price above VWMA) (+{weight:.2f})."
                )
            elif current_close < vwma and prev_close >= prev_vwma:
                signal_score -= weight
                self.logger.debug(
                    f"  VWMA: Bearish crossover (price below VWMA) (-{weight:.2f})."
                )
        return signal_score

    def _score_volume_delta(self, signal_score: float) -> float:
        volume_delta = self._get_indicator_value("Volume_Delta")
        volume_delta_threshold = self.indicator_settings["volume_delta_threshold"]
        weight = self.weights.get("volume_delta_signal", 0.0)

        if not pd.isna(volume_delta):
            if volume_delta > volume_delta_threshold:  # Strong buying pressure
                signal_score += weight
                self.logger.debug(
                    f"  Volume Delta: Strong buying pressure detected (+{weight:.2f})."
                )
            elif volume_delta < -volume_delta_threshold:  # Strong selling pressure
                signal_score -= weight
                self.logger.debug(
                    f"  Volume Delta: Strong selling pressure detected (-{weight:.2f})."
                )
            elif volume_delta > 0:
                signal_score += weight * 0.3
                self.logger.debug(
                    f"  Volume Delta: Moderate buying pressure detected (+{weight * 0.3:.2f})."
                )
            elif volume_delta < 0:
                signal_score -= weight * 0.3
                self.logger.debug(
                    f"  Volume Delta: Moderate selling pressure detected (-{weight * 0.3:.2f})."
                )
        return signal_score

    def _score_mtf_trend_confluence(
        self, mtf_trends: dict[str, str], signal_score: float
    ) -> float:
        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = 0
            mtf_sell_score = 0
            for _tf_indicator, trend in mtf_trends.items():
                if trend == "UP":
                    mtf_buy_score += 1
                elif trend == "DOWN":
                    mtf_sell_score -= 1  # Subtract for bearish MTF trend

            mtf_weight = self.weights.get("mtf_trend_confluence", 0.0)
            if mtf_trends:
                # Calculate a normalized score based on the balance of buy/sell trends
                normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(
                    mtf_trends
                )
                signal_score += mtf_weight * normalized_mtf_score
                self.logger.debug(
                    f"MTF Confluence: Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {abs(mtf_sell_score)}). Total MTF contribution: {mtf_weight * normalized_mtf_score:.2f}"
                )
        return signal_score

    async def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_manager: Any,
        mtf_trends: dict[str, str],
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}"
            )
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1].item()))
        # Use .get() with default to handle cases where there might be less than 2 bars after NaN drops
        prev_close_series = (
            self.df["close"].iloc[-2].item()
            if len(self.df) > 1 and not pd.isna(self.df["close"].iloc[-2])
            else np.nan
        )
        prev_close = (
            Decimal(str(prev_close_series))
            if not pd.isna(prev_close_series)
            else current_close
        )

        self.logger.debug(f"[{self.symbol}] --- Signal Scoring ---")

        if active_indicators.get("ema_alignment", False):
            signal_score = self._score_ema_alignment(signal_score)

        if active_indicators.get("sma_trend_filter", False):
            signal_score = self._score_sma_trend_filter(current_close, signal_score)

        if active_indicators.get("momentum", False):
            signal_score = self._score_momentum_indicators(signal_score)

        if active_indicators.get("bollinger_bands", False):
            signal_score = self._score_bollinger_bands(current_close, signal_score)

        if active_indicators.get("vwap", False):
            signal_score = self._score_vwap(current_close, prev_close, signal_score)

        if active_indicators.get("psar", False):
            signal_score = self._score_psar(current_close, prev_close, signal_score)

        # Orderbook Imbalance (placeholder)
        if active_indicators.get("orderbook_imbalance", False) and orderbook_manager:
            imbalance = self._check_orderbook(current_price, orderbook_manager)
            signal_score += imbalance * self.weights.get("orderbook_imbalance", 0)
            self.logger.debug(
                f"  Orderbook Imbalance: {imbalance:.2f} (Contribution: {imbalance * self.weights.get('orderbook_imbalance', 0):.2f})"
            )

        if active_indicators.get("fibonacci_levels", False):
            signal_score = self._score_fibonacci_levels(
                current_price, prev_close, signal_score
            )

        if active_indicators.get("ehlers_supertrend", False):
            signal_score = self._score_ehlers_supertrend_alignment(signal_score)

        if active_indicators.get("macd", False):
            signal_score = self._score_macd_alignment(signal_score)

        if active_indicators.get("adx", False):
            signal_score = self._score_adx_strength(signal_score)

        if active_indicators.get("ichimoku_cloud", False):
            signal_score = self._score_ichimoku_confluence(
                current_close, prev_close, signal_score
            )

        if active_indicators.get("obv", False):
            signal_score = self._score_obv_momentum(signal_score)

        if active_indicators.get("cmf", False):
            signal_score = self._score_cmf_flow(signal_score)

        if active_indicators.get("volatility_index", False):
            signal_score = self._score_volatility_index(signal_score)

        if active_indicators.get("vwma", False):
            signal_score = self._score_vwma_cross(
                current_close, prev_close, signal_score
            )

        if active_indicators.get("volume_delta", False):
            signal_score = self._score_volume_delta(signal_score)

        if self.config["mtf_analysis"]["enabled"]:
            signal_score = self._score_mtf_trend_confluence(mtf_trends, signal_score)

        # --- Gemini AI Analysis Scoring ---
        if self.config["gemini_ai_analysis"]["enabled"] and self.gemini_client:
            # Prepare a prompt or data for Gemini AI. This is a very simplified example.
            # In a real scenario, you'd send more structured data or a detailed prompt.
            market_summary = {
                "current_price": str(current_price),
                "last_candle_close": str(current_close),
                "indicator_values": {
                    k: str(v) for k, v in self.indicator_values.items()
                },
                "mtf_trends": mtf_trends,
            }
            gemini_analysis = self.gemini_client.analyze_market_data(market_summary)

            if gemini_analysis:
                self.logger.info(
                    f"{NEON_PURPLE}Gemini AI Analysis: {json.dumps(gemini_analysis, indent=2)}{RESET}"
                )
                gemini_entry = gemini_analysis.get("entry")
                gemini_confidence = gemini_analysis.get("confidence_level", 0)
                gemini_weight = self.config["gemini_ai_analysis"]["weight"]

                if gemini_confidence >= 50:  # Only consider if confidence is reasonable
                    if gemini_entry == "BUY":
                        signal_score += gemini_weight
                        self.logger.info(
                            f"{NEON_GREEN}Gemini AI recommends BUY (Confidence: {gemini_confidence}). Adding {gemini_weight} to signal score.{RESET}"
                        )
                    elif gemini_entry == "SELL":
                        signal_score -= gemini_weight
                        self.logger.info(
                            f"{NEON_RED}Gemini AI recommends SELL (Confidence: {gemini_confidence}). Subtracting {gemini_weight} from signal score.{RESET}"
                        )
                    else:
                        self.logger.info(
                            f"{NEON_YELLOW}Gemini AI recommends HOLD (Confidence: {gemini_confidence}). No change to signal score.{RESET}"
                        )
                else:
                    self.logger.info(
                        f"{NEON_YELLOW}Gemini AI confidence ({gemini_confidence}) too low. Skipping influence on signal score.{RESET}"
                    )
            else:
                self.logger.warning(
                    f"{NEON_YELLOW}Gemini AI analysis failed or returned no data. Skipping influence on signal score.{RESET}"
                )

        # --- Final Signal Determination ---
        threshold = Decimal(str(self.config["signal_score_threshold"]))
        final_signal = "HOLD"
        if signal_score >= threshold:
            final_signal = "BUY"
        elif signal_score <= -threshold:
            final_signal = "SELL"

        self.logger.info(
            f"{NEON_YELLOW}Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}"
        )
        return final_signal, signal_score

    def calculate_entry_tp_sl(
        self, current_price: Decimal, atr_value: Decimal, signal: Literal["BUY", "SELL"]
    ) -> tuple[Decimal, Decimal]:
        """Calculate Take Profit and Stop Loss levels."""
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"])
        )

        if signal == "BUY":
            stop_loss = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit = current_price + (atr_value * take_profit_atr_multiple)
        elif signal == "SELL":
            stop_loss = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit = current_price - (atr_value * take_profit_atr_multiple)
        else:
            # Should not happen for valid signals
            return Decimal("0"), Decimal("0")

        return (
            self.precision_manager.format_price(take_profit),
            self.precision_manager.format_price(stop_loss),
        )


def display_indicator_values_and_price(
    config: dict[str, Any],
    logger: logging.Logger,
    current_price: Decimal,
    analyzer: "TradingAnalyzer",
    orderbook_manager: Any,
    mtf_trends: dict[str, str],
) -> None:
    """Display current price and calculated indicator values."""
    logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
    logger.info(f"{NEON_GREEN}Current Price: {current_price.normalize()}{RESET}")

    if analyzer.df.empty:
        logger.warning(
            f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.{RESET}"
        )
        return

    logger.info(f"{NEON_CYAN}--- Indicator Values ---{RESET}")
    for indicator_name, value in analyzer.indicator_values.items():
        color = INDICATOR_COLORS.get(indicator_name, NEON_YELLOW)
        # Format Decimal values for consistent display
        if isinstance(value, Decimal):
            logger.info(f"  {color}{indicator_name}: {value.normalize()}{RESET}")
        elif isinstance(value, float):
            logger.info(
                f"  {color}{indicator_name}: {value:.8f}{RESET}"
            )  # Display floats with more reasonable precision
        else:
            logger.info(f"  {color}{indicator_name}: {value}{RESET}")

    if analyzer.fib_levels:
        logger.info(f"{NEON_CYAN}--- Fibonacci Levels ---{RESET}")
        for level_name, level_price in analyzer.fib_levels.items():
            logger.info(
                f"  {NEON_YELLOW}{level_name}: {level_price.normalize()}{RESET}"
            )

    if mtf_trends:
        logger.info(f"{NEON_CYAN}--- Multi-Timeframe Trends ---{RESET}")
        for tf_indicator, trend in mtf_trends.items():
            logger.info(f"  {NEON_YELLOW}{tf_indicator}: {trend}{RESET}")

    if config["indicators"].get("orderbook_imbalance", False):
        imbalance = analyzer._check_orderbook(current_price, orderbook_manager)
        if (
            imbalance != 0.0
        ):  # Only display if the placeholder is not returning default 0.0
            logger.info(f"{NEON_CYAN}Orderbook Imbalance: {imbalance:.4f}{RESET}")

    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")


async def main_async_loop(
    config: dict[str, Any],
    logger: logging.Logger,
    position_manager: PositionManager,
    performance_tracker: PerformanceTracker,
    alert_system: AlertSystem,
    gemini_client: Any,
) -> None:
    """The main asynchronous loop for the trading bot."""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        # Initialize components that need the async client
        position_manager.client = client
        time_offset_ms = 0  # Initialize here
        server_time_response = await fetch_bybit_server_time(logger, client)
        if server_time_response:
            local_time_ms = int(time.time() * 1000)
            time_offset_ms = server_time_response - local_time_ms
            logger.info(
                f"{NEON_GREEN}Bybit server time synchronized. Offset: {time_offset_ms} ms.{RESET}"
            )
        else:
            logger.warning(
                f"{NEON_YELLOW}Could not synchronize with Bybit server time. Using local time. This may cause signature errors.{RESET}"
            )

        await position_manager.initialize(
            time_offset_ms
        )  # Now time_offset_ms is defined

        while True:
            try:
                logger.info(
                    f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}"
                )
                current_price = await fetch_current_price(
                    config["symbol"], logger, client, time_offset_ms
                )
                if current_price is None:
                    alert_system.send_alert(
                        f"[{config['symbol']}] Failed to fetch current price. Skipping loop.",
                        "WARNING",
                    )
                    await asyncio.sleep(config["loop_delay"])
                    continue

                df = await fetch_klines(
                    config["symbol"],
                    config["interval"],
                    500,
                    logger,
                    client,
                    time_offset_ms,  # Increased limit to 500
                )  # Increased limit for more robust indicator calc
                if df is None or df.empty:
                    alert_system.send_alert(
                        f"[{config['symbol']}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
                        "WARNING",
                    )
                    await asyncio.sleep(config["loop_delay"])
                    continue

                # AdvancedOrderbookManager is not implemented, so this will remain None
                orderbook_data = None

                mtf_trends: dict[str, str] = {}
                if config["mtf_analysis"]["enabled"]:
                    for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                        logger.debug(
                            f"Fetching klines for MTF interval: {htf_interval}"
                        )
                        htf_df = await fetch_klines(
                            config["symbol"],
                            htf_interval,
                            500,
                            logger,
                            client,
                            time_offset_ms,  # Increased limit to 500
                        )  # Increased limit
                        if htf_df is not None and not htf_df.empty:
                            for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                                # A new TradingAnalyzer is created for each HTF to avoid cross-contamination
                                temp_htf_analyzer = TradingAnalyzer(
                                    htf_df,
                                    config,
                                    logger,
                                    config["symbol"],
                                    position_manager.precision_manager,
                                )
                                trend = temp_htf_analyzer._get_mtf_trend(
                                    htf_df,
                                    trend_ind,
                                )
                                mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                                logger.debug(
                                    f"MTF Trend ({htf_interval}, {trend_ind}): {trend}"
                                )
                        else:
                            logger.warning(
                                f"{NEON_YELLOW}Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}"
                            )
                        await asyncio.sleep(
                            config["mtf_analysis"]["mtf_request_delay_seconds"]
                        )  # Delay between MTF requests

                analyzer = TradingAnalyzer(
                    df,
                    config,
                    logger,
                    config["symbol"],
                    position_manager.precision_manager,
                )

                if analyzer.df.empty:
                    alert_system.send_alert(
                        f"[{config['symbol']}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                        "WARNING",
                    )
                    await asyncio.sleep(config["loop_delay"])
                    continue

                # Pass None for orderbook_manager as it's not implemented
                trading_signal, signal_score = await analyzer.generate_trading_signal(
                    current_price, None, mtf_trends
                )
                atr_value = Decimal(
                    str(analyzer._get_indicator_value("ATR", Decimal("0.01")))
                )  # Default to a small positive value if ATR is missing

                # Manage existing positions before potentially opening new ones
                await position_manager.manage_positions(
                    current_price, atr_value, performance_tracker, time_offset_ms
                )

                if (
                    trading_signal == "BUY"
                    and signal_score >= config["signal_score_threshold"]
                ):
                    logger.info(
                        f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}. Attempting to open position.{RESET}"
                    )
                    await position_manager.open_position(
                        "BUY", current_price, atr_value, time_offset_ms
                    )
                elif (
                    trading_signal == "SELL"
                    and signal_score <= -config["signal_score_threshold"]
                ):
                    logger.info(
                        f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}. Attempting to open position.{RESET}"
                    )
                    await position_manager.open_position(
                        "SELL", current_price, atr_value, time_offset_ms
                    )
                else:
                    logger.info(
                        f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}"
                    )

                open_positions = position_manager.get_open_positions()
                if open_positions:
                    logger.info(
                        f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}"
                    )
                    for pos in open_positions:
                        logger.info(
                            f"  - {pos['side']} {pos['qty'].normalize()} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}, Trailing SL: {pos.get('current_trailing_sl', 'N/A').normalize() if isinstance(pos.get('current_trailing_sl'), Decimal) else pos.get('current_trailing_sl', 'N/A')}){RESET}"
                        )
                else:
                    logger.info(f"{NEON_CYAN}No open positions.{RESET}")

                perf_summary = performance_tracker.get_summary()
                logger.info(
                    f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}"
                )

                # Display indicator values and price
                display_indicator_values_and_price(
                    config,
                    logger,
                    current_price,
                    analyzer,
                    None,  # Pass None for orderbook_manager
                    mtf_trends,
                )

                logger.info(
                    f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}"
                )
                await asyncio.sleep(config["loop_delay"])

            except asyncio.CancelledError:
                logger.info(f"{NEON_BLUE}Main loop cancelled gracefully.{RESET}")
                break
            except Exception as e:
                alert_system.send_alert(
                    f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}",
                    "ERROR",
                )
                logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
                # Longer delay on error
                await asyncio.sleep(config["loop_delay"] * 2)


# --- Main execution ---
if __name__ == "__main__":
    try:
        # Load config and setup logger early
        logger = setup_logger("whalebot_main", level=logging.INFO)
        config = load_config(CONFIG_FILE, logger)
        alert_system = AlertSystem(logger)

        # Validate intervals
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
                f"{NEON_RED}Invalid primary interval '{config['interval']}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.{RESET}"
            )
            sys.exit(1)
        for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
            if htf_interval not in valid_bybit_intervals:
                logger.error(
                    f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}' in config.json. Please use Bybit's valid string formats (e.g., '60', '240'). Exiting.{RESET}"
                )
                sys.exit(1)

        if not API_KEY or not API_SECRET:
            logger.critical(
                f"{NEON_RED}BYBIT_API_KEY or BYBIT_API_SECRET environment variables are not set. Please set them before running the bot. Exiting.{RESET}"
            )
            sys.exit(1)

        logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Initialized ---{RESET}")
        logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
        logger.info(
            f"Trade Management Enabled: {config['trade_management']['enabled']}"
        )
        if config["trade_management"]["enabled"]:
            logger.info(
                f"Leverage: {config['trade_management']['leverage']}x, Order Mode: {config['trade_management']['order_mode']}"
            )
        else:
            logger.info(
                f"Using simulated balance for position sizing: {config['trade_management']['account_balance']:.2f} USDT"
            )

        # Initialize PerformanceTracker here
        performance_tracker = PerformanceTracker(
            logger, config_file="bot_logs/trading-bot/trades.json"
        )  # Save trades to a file

        # Initialize other components needed by the main loop or analyzer
        gemini_client = None
        if config["gemini_ai_analysis"]["enabled"]:
            gemini_api_key = os.getenv("GEMINI_API_KEY")
            if gemini_api_key:
                # Assuming GeminiClient is available and correctly implemented elsewhere
                # from gemini_client import GeminiClient # Uncomment if GeminiClient is available
                # gemini_client = GeminiClient(
                #     api_key=gemini_api_key,
                #     model_name=config["gemini_ai_analysis"]["model_name"],
                #     temperature=config["gemini_ai_analysis"]["temperature"],
                #     top_p=config["gemini_ai_analysis"]["top_p"],
                #     logger=logger
                # )
                logger.warning(
                    f"{NEON_YELLOW}Gemini AI analysis enabled, but GeminiClient is not implemented/imported. Placeholder used.{RESET}"
                )

                class DummyGeminiClient:
                    def __init__(self, logger_instance):
                        self.logger = logger_instance

                    def analyze_market_data(self, data):
                        self.logger.info(
                            "Dummy Gemini AI: Analyzing market data (no actual analysis)."
                        )
                        return {
                            "entry": "HOLD",
                            "confidence_level": 50,
                            "reason": "Dummy analysis.",
                        }

                gemini_client = DummyGeminiClient(logger)
            else:
                logger.error(
                    f"{NEON_RED}GEMINI_API_KEY not set, disabling Gemini AI analysis.{RESET}"
                )
                config["gemini_ai_analysis"]["enabled"] = False

        # PositionManager needs the async client as well, it will be passed to main_async_loop
        # and then the client attribute will be set.
        # Initialize with a dummy client, it will be updated in main_async_loop
        position_manager = PositionManager(config, logger, config["symbol"], None)

        # Start the asynchronous main loop
        asyncio.run(
            main_async_loop(
                config,
                logger,
                position_manager,
                performance_tracker,
                alert_system,
                gemini_client,
            )
        )

    except KeyboardInterrupt:
        logger.info(
            f"{NEON_BLUE}KeyboardInterrupt detected. Shutting down bot...{RESET}"
        )
        # The shutdown logic is handled within main_async_loop's finally block
    except Exception as e:
        logger.critical(
            f"{NEON_RED}Critical error during bot startup or top-level execution: {e}{RESET}",
            exc_info=True,
        )
        sys.exit(1)  # Exit if critical setup fails
