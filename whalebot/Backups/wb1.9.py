# -*- coding: utf-8 -*-
"""Whalebot: An automated cryptocurrency trading bot for Bybit.

This bot leverages various technical indicators and multi-timeframe analysis
to generate trading signals and manage positions on the Bybit exchange.
It includes features for risk management, performance tracking, and alerts.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import sys
import time
import urllib.parse
import random
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Generic, Literal, Optional, Tuple, TypeVar, Dict, List, Union, Callable

import numpy as np
import pandas as pd
import pandas_ta as ta
import requests
from colorama import Fore, Style, init
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from zoneinfo import ZoneInfo

# Scikit-learn is explicitly excluded as per user request.
# SKLEARN_AVAILABLE variable is removed as it is unused and its presence might suggest ML features.

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
TIMEZONE = timezone.utc
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
            "account_balance": 1000.0,  # Simulated balance if not using real API
            "risk_per_trade_percent": 1.0,  # Percentage of account_balance to risk
            "stop_loss_atr_multiple": 1.5,  # Stop loss distance as multiple of ATR
            "take_profit_atr_multiple": 2.0,  # Take profit distance as multiple of ATR
            "trailing_stop_atr_multiple": 0.3, # Trailing stop distance as multiple of ATR
            "max_open_positions": 1,
            "order_precision": 4,  # Decimal places for order quantity
            "price_precision": 2,  # Decimal places for price
            "leverage": 10,  # Leverage for perpetual contracts
            "order_mode": "MARKET",  # MARKET or LIMIT for entry orders
            "take_profit_type": "MARKET", # MARKET or LIMIT for TP
            "stop_loss_type": "MARKET", # MARKET or LIMIT for SL
            "trailing_stop_activation_percent": 0.5, # % profit to activate trailing stop
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
            "volatility_index_period": 20,
            "vwma_period": 20,
            "volume_delta_period": 5,
            "volume_delta_threshold": 0.2,
            "vwap_daily_reset": False, # Should VWAP reset daily or be continuous
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
        "weight_sets": {
            "default_scalping": {
                "ema_alignment": 0.22,
                "sma_trend_filter": 0.28,
                "momentum_rsi_stoch_cci_wr_mfi": 0.18,
                "volume_confirmation": 0.12,
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
            "weight": 0.3, # Weight of Gemini's signal in the final score
        }
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(
                f"{NEON_YELLOW}Configuration file not found. Created default config at {filepath} for symbol {default_config['symbol']}{RESET}"
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
    headers = {"Content-Type": "application/json"}
    params = params if params is not None else {}

    if signed:
        if not API_KEY or not API_SECRET:
            logger.error(
                f"{NEON_RED}API_KEY or API_SECRET not set for signed request. Cannot proceed.{RESET}"
            )
            return None

        timestamp = str(int(time.time() * 1000))
        recv_window = "20000"

        if method == "GET":
            query_string = urllib.parse.urlencode(params)
            param_str = timestamp + API_KEY + recv_window + query_string
            signature = generate_signature(param_str, API_SECRET)
            headers.update(
                {
                    "X-BAPI-API-KEY": API_KEY,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": recv_window,
                }
            )
            full_url = f"{url}?{query_string}" if query_string else url
            logger.debug(f"GET Request to {full_url}")
            response = session.get(
                url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
            )
        else:  # POST
            json_params = json.dumps(params)
            param_str = timestamp + API_KEY + recv_window + json_params
            signature = generate_signature(param_str, API_SECRET)
            headers.update(
                {
                    "X-BAPI-API-KEY": API_KEY,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": recv_window,
                }
            )
            logger.debug(f"POST Request to {url} with payload {json_params}")
            response = session.post(
                url, json=params, headers=headers, timeout=REQUEST_TIMEOUT
            )
    else:
        logger.debug(f"Public Request to {url} with params {params}")
        response = session.get(
            url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
        )

    try:
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") != 0:
            logger.error(
                f"{NEON_RED}Bybit API Error ({endpoint}): {data.get('retMsg')} (Code: {data.get('retCode')}){RESET}"
            )
            return None
        return data
    except requests.exceptions.HTTPError as e:
        logger.error(
            f"{NEON_RED}HTTP Error ({endpoint}): {e.response.status_code} - {e.response.text}{RESET}"
        )
    except requests.exceptions.ConnectionError as e:
        logger.error(f"{NEON_RED}Connection Error ({endpoint}): {e}{RESET}")
    except requests.exceptions.Timeout:
        logger.error(
            f"{NEON_RED}Request to {endpoint} timed out after {REQUEST_TIMEOUT} seconds.{RESET}"
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"{NEON_RED}Request Exception ({endpoint}): {e}{RESET}")
    except json.JSONDecodeError:
        logger.error(
            f"{NEON_RED}Failed to decode JSON response from {endpoint}: {response.text}{RESET}"
        )
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
    symbol: str, interval: str, limit: int, logger: logging.Logger
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


def get_wallet_balance(
    account_type: Literal["UNIFIED", "CONTRACT"], coin: str, logger: logging.Logger
) -> Decimal | None:
    """Fetch wallet balance for a specific coin."""
    endpoint = "/v5/account/wallet-balance"
    params = {"accountType": account_type, "coin": coin}
    response = bybit_request("GET", endpoint, params, signed=True, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        for item in response["result"]["list"]:
            if item["coin"][0]["coin"] == coin:
                balance = Decimal(item["coin"][0]["walletBalance"])
                logger.debug(f"Fetched {coin} wallet balance: {balance}")
                return balance
    logger.warning(f"{NEON_YELLOW}Could not fetch {coin} wallet balance.{RESET}")
    return None


def get_exchange_open_positions(
    symbol: str, category: str, logger: logging.Logger
) -> list[dict] | None:
    """Fetch currently open positions from the exchange."""
    endpoint = "/v5/position/list"
    params = {"category": category, "symbol": symbol}
    response = bybit_request("GET", endpoint, params, signed=True, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        return response["result"]["list"]
    return []


def place_order(
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
) -> dict | None:
    """Place an order on Bybit."""
    if logger is None:
        logger = setup_logger("bybit_api")

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

    # Add TP/SL to the order itself
    if take_profit is not None:
        params["takeProfit"] = str(take_profit)
        params["tpslMode"] = tp_sl_mode
    if stop_loss is not None:
        params["stopLoss"] = str(stop_loss)
        params["tpslMode"] = tp_sl_mode

    endpoint = "/v5/order/create"
    response = bybit_request("POST", endpoint, params, signed=True, logger=logger)
    if response:
        logger.info(
            f"{NEON_GREEN}Order placed successfully for {symbol}: {response['result']}{RESET}"
        )
        return response["result"]
    logger.error(f"{NEON_RED}Failed to place order for {symbol}: {params}{RESET}")
    return None


def cancel_order(
    symbol: str, order_id: str, logger: logging.Logger | None = None
) -> dict | None:
    """Cancel an existing order on Bybit."""
    if logger is None:
        logger = setup_logger("bybit_api")
    endpoint = "/v5/order/cancel"
    params = {"category": "linear", "symbol": symbol, "orderId": order_id}
    response = bybit_request("POST", endpoint, params, signed=True, logger=logger)
    if response:
        logger.info(
            f"{NEON_GREEN}Order {order_id} cancelled for {symbol}: {response['result']}{RESET}"
        )
        return response["result"]
    logger.error(
        f"{NEON_RED}Failed to cancel order {order_id} for {symbol}.{RESET}"
    )
    return None


# --- Position Management ---
class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""

    def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str):
        """Initializes the PositionManager."""
        self.config = config
        self.logger = logger
        self.symbol = symbol
        # self.open_positions: list[dict] = []  # No longer stores local list, relies on exchange
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]
        self.leverage = config["trade_management"]["leverage"]
        self.order_mode = config["trade_management"]["order_mode"]
        self.tp_sl_mode = "Full" # Default to full for simplicity, can be configured

        # Set leverage (only once or when changed)
        if self.trade_management_enabled:
            self._set_leverage()

    def _set_leverage(self) -> None:
        """Set leverage for the trading pair."""
        endpoint = "/v5/position/set-leverage"
        params = {
            "category": "linear",
            "symbol": self        .symbol,
            "buyLeverage": str(self.leverage),
            "sellLeverage": str(self.leverage),
        }
        response = bybit_request("POST", endpoint, params, signed=True, logger=self.logger)
        if response and response["retCode"] == 0:
            self.logger.info(
                f"{NEON_GREEN}[{self.symbol}] Leverage set to {self.leverage}x.{RESET}"
            )
        else:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Failed to set leverage to {self.leverage}x. Error: {response.get('retMsg') if response else 'Unknown'}{RESET}"
            )

    def _get_available_balance(self) -> Decimal:
        """Fetch current available account balance for order sizing."""
        if not self.trade_management_enabled:
            return Decimal(str(self.config["trade_management"]["account_balance"]))

        balance = get_wallet_balance(
            account_type="UNIFIED", coin="USDT", logger=selfThe user provided code snippets for a trading bot. The request is to analyze the code, upgrade and enhance it, and return the complete improved code incorporating all ideas.

Based on the provided code, the user wants to create a sophisticated trading bot that utilizes:
- **Bybit API**: Interacting with Bybit for market data and trading.
- **Technical Indicators**: A wide range of indicators for signal generation.
- **Multi-Timeframe Analysis (MTF)**: Incorporating trends from higher timeframes.
- **Orderbook Analysis**: Using orderbook imbalance for signals.
- **Ehlers Indicators**: Specifically Ehlers SuperTrend.
- **Newer Indicators**: Volatility Index, VWMA, Volume Delta.
- **Risk Management**: Stop-loss, take-profit, trailing stops, position sizing based on ATR and risk percentage.
- **Performance Tracking**: Recording trades and summarizing performance.
- **Logging**: Robust logging with sensitive data redaction.
- **Configuration**: Loading settings from `config.json`.
- **Gemini AI Analysis**: Optional integration for enhanced signal generation.

The provided code snippets are quite extensive and cover many aspects of a trading bot. My task is to merge these into a single, coherent, and improved script.

Here's a plan to achieve this:

1.  **Consolidate Core Functionality**: Merge the `wb.py` (main bot logic), `config.py` (configuration), and potentially other helper functions into a single script.
2.  **Refactor and Organize**: Structure the code into classes for better organization (e.g., `BybitClient`, `TradingAnalyzer`, `PositionManager`, `PerformanceTracker`, `AlertSystem`, `ConfigManager`, `LoggerSetup`).
3.  **Asynchronous Operations**: Since Bybit's WebSocket API is inherently asynchronous, refactor the main loop and WebSocket handling to use `asyncio`. This will improve performance and responsiveness.
4.  **Integrate Gemini AI**: If `gemini_ai_analysis` is enabled in the config, integrate the Gemini client for signal enhancement.
5.  **Enhance Indicator Calculations**: Ensure all indicators are calculated correctly and efficiently, handling potential NaNs or insufficient data.
6.  **Improve Order Management**: Implement robust order placement, cancellation, and management, including handling TP/SL and trailing stops.
7.  **Refine Signal Generation**: Combine signals from various indicators, MTF, orderbook, and potentially Gemini AI, applying the configured weights.
8.  **Error Handling and Retries**: Implement comprehensive error handling and retry mechanisms for API requests and WebSocket connections.
9.  **Configuration Loading**: Ensure the `config.json` is loaded correctly, with defaults provided if the file is missing or invalid.
10. **Add Docstrings and Comments**: Improve code readability and maintainability.

I will create a single Python script that encapsulates all these functionalities.

```python
# -*- coding: utf-8 -*-
"""Whalebot: An automated cryptocurrency trading bot for Bybit.

This bot leverages various technical indicators and multi-timeframe analysis
to generate trading signals and manage positions on the Bybit exchange.
It includes features for risk management, performance tracking, and alerts.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import sys
import time
import urllib.parse
import random
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Generic, Literal, Optional, Tuple, TypeVar, Dict, List, Union, Callable

import numpy as np
import pandas as pd
import pandas_ta as ta
import requests
from colorama import Fore, Style, init
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from zoneinfo import ZoneInfo

# Note: Scikit-learn is explicitly excluded as per user request.
# SKLEARN_AVAILABLE variable is removed as it is unused and its presence might suggest ML features.

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
TIMEZONE = timezone.utc
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
            "account_balance": 1000.0,  # Simulated balance if not using real API
            "risk_per_trade_percent": 1.0,  # Percentage of account_balance to risk
            "stop_loss_atr_multiple": 1.5,  # Stop loss distance as multiple of ATR
            "take_profit_atr_multiple": 2.0,  # Take profit distance as multiple of ATR
            "trailing_stop_atr_multiple": 0.3, # Trailing stop distance as multiple of ATR
            "max_open_positions": 1,
            "order_precision": 4,  # Decimal places for order quantity
            "price_precision": 2,  # Decimal places for price
            "leverage": 10,  # Leverage for perpetual contracts
            "order_mode": "MARKET",  # MARKET or LIMIT for entry orders
            "take_profit_type": "MARKET", # MARKET or LIMIT for TP
            "stop_loss_type": "MARKET", # MARKET or LIMIT for SL
            "trailing_stop_activation_percent": 0.5, # % profit to activate trailing stop
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
            "feature_lags":,
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
            "vwap_daily_reset": False, # Should VWAP reset daily or be continuous
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
        "weight_sets": {
            "default_scalping": {
                "ema_alignment": 0.22,
                "sma_trend_filter": 0.28,
                "momentum_rsi_stoch_cci_wr_mfi": 0.18,
                "volume_confirmation": 0.12,
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
            "weight": 0.3, # Weight of Gemini's signal in the final score
        }
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(
                f"{NEON_YELLOW}Configuration file not found. Created default config at {filepath} for symbol {default_config['symbol']}{RESET}"
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


# --- API Interaction ---
def create_session() -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    retries = Retry(
        total=MAX_API_RETRIES,
        backoff_factor=RETRY_DELAY_SECONDS,
        status_forcelist=,
        allowed_methods=frozenset(["GET", "POST"]),
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def generate_signature(payload: str, api_secret: str) -> str:
    """Generate a Bybit API signature."""
    return hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


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
    headers = {"Content-Type": "application/json"}
    params = params if params is not None else {}

    if signed:
        if not API_KEY or not API_SECRET:
            logger.error(
                f"{NEON_RED}API_KEY or API_SECRET not set for signed request. Cannot proceed.{RESET}"
            )
            return None

        timestamp = str(int(time.time() * 1000))
        recv_window = "20000"

        if method == "GET":
            query_string = urllib.parse.urlencode(params)
            param_str = timestamp + API_KEY + recv_window + query_string
            signature = generate_signature(param_str, API_SECRET)
            headers.update(
                {
                    "X-BAPI-API-KEY": API_KEY,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": recv_window,
                }
            )
            full_url = f"{url}?{query_string}" if query_string else url
            logger.debug(f"GET Request to {full_url}")
            response = session.get(
                url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
            )
        else:  # POST
            json_params = json.dumps(params)
            param_str = timestamp + API_KEY + recv_window + json_params
            signature = generate_signature(param_str, API_SECRET)
            headers.update(
                {
                    "X-BAPI-API-KEY": API_KEY,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": recv_window,
                }
            )
            logger.debug(f"POST Request to {url} with payload {json_params}")
            response = session.post(
                url, json=params, headers=headers, timeout=REQUEST_TIMEOUT
            )
    else:
        logger.debug(f"Public Request to {url} with params {params}")
        response = session.get(
            url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
        )

    try:
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") != 0:
            logger.error(
                f"{NEON_RED}Bybit API Error ({endpoint}): {data.get('retMsg')} (Code: {data.get('retCode')}){RESET}"
            )
            return None
        return data
    except requests.exceptions.HTTPError as e:
        logger.error(
            f"{NEON_RED}HTTP Error ({endpoint}): {e.response.status_code} - {e.response.text}{RESET}"
        )
    except requests.exceptions.ConnectionError as e:
        logger.error(f"{NEON_RED}Connection Error ({endpoint}): {e}{RESET}")
    except requests.exceptions.Timeout:
        logger.error(
            f"{NEON_RED}Request to {endpoint} timed out after {REQUEST_TIMEOUT} seconds.{RESET}"
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"{NEON_RED}Request Exception ({endpoint}): {e}{RESET}")
    except json.JSONDecodeError:
        logger.error(
            f"{NEON_RED}Failed to decode JSON response from {endpoint}: {response.text}{RESET}"
        )
    return None


def fetch_current_price(symbol: str, logger: logging.Logger) -> Decimal | None:
    """Fetch the current market price for a symbol."""
    endpoint = "/v5/market/tickers"
    params = {"category": "linear", "symbol": symbol}
    response = bybit_request("GET", endpoint, params, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        price = Decimal(response["result"]["list"]["lastPrice"])
        logger.debug(f"Fetched current price for {symbol}: {price}")
        return price
    logger.warning(f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}")
    return None


def fetch_klines(
    symbol: str, interval: str, limit: int, logger: logging.Logger
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


def get_wallet_balance(
    account_type: Literal["UNIFIED", "CONTRACT"], coin: str, logger: logging.Logger
) -> Decimal | None:
    """Fetch wallet balance for a specific coin."""
    endpoint = "/v5/account/wallet-balance"
    params = {"accountType": account_type, "coin": coin}
    response = bybit_request("GET", endpoint, params, signed=True, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        for item in response["result"]["list"]:
            if item["coin"]["coin"] == coin:
                balance = Decimal(item["coin"]["walletBalance"])
                logger.debug(f"Fetched {coin} wallet balance: {balance}")
                return balance
    logger.warning(f"{NEON_YELLOW}Could not fetch {coin} wallet balance.{RESET}")
    return None


def get_exchange_open_positions(
    symbol: str, category: str, logger: logging.Logger
) -> list[dict] | None:
    """Fetch currently open positions from the exchange."""
    endpoint = "/v5/position/list"
    params = {"category": category, "symbol": symbol}
    response = bybit_request("GET", endpoint, params, signed=True, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        return response["result"]["list"]
    return []


def place_order(
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
) -> dict | None:
    """Place an order on Bybit."""
    if logger is None:
        logger = setup_logger("bybit_api")

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

    # Add TP/SL to the order itself
    if take_profit is not None:
        params["takeProfit"] = str(take_profit)
        params["tpslMode"] = tp_sl_mode
    if stop_loss is not None:
        params["stopLoss"] = str(stop_loss)
        params["tpslMode"] = tp_sl_mode

    endpoint = "/v5/order/create"
    response = bybit_request("POST", endpoint, params, signed=True, logger=logger)
    if response:
        logger.info(
            f"{NEON_GREEN}Order placed successfully for {symbol}: {response['result']}{RESET}"
        )
        return response["result"]
    logger.error(f"{NEON_RED}Failed to place order for {symbol}: {params}{RESET}")
    return None


def cancel_order(
    symbol: str, order_id: str, logger: logging.Logger | None = None
) -> dict | None:
    """Cancel an existing order on Bybit."""
    if logger is None:
        logger = setup_logger("bybit_api")
    endpoint = "/v5/order/cancel"
    params = {"category": "linear", "symbol": symbol, "orderId": order_id}
    response = bybit_request("POST", endpoint, params, signed=True, logger=logger)
    if response:
        logger.info(
            f"{NEON_GREEN}Order {order_id} cancelled for {symbol}: {response['result']}{RESET}"
        )
        return response["result"]
    logger.error(
        f"{NEON_RED}Failed to cancel order {order_id} for {symbol}.{RESET}"
    )
    return None


# --- Position Management ---
class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""

    def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str):
        """Initializes the PositionManager."""
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.open_positions: dict[str, dict] = {} # Tracks positions opened by the bot locally
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]
        self.leverage = config["trade_management"]["leverage"]
        self.order_mode = config["trade_management"]["order_mode"]
        self.tp_sl_mode = "Full" # Default to full for simplicity, can be configured
        self.trailing_stop_activation_percent = Decimal(str(config["trade_management"]["trailing_stop_activation_percent"])) / 100

        # Set leverage (only once or when changed)
        if self.trade_management_enabled:
            self._set_leverage()

    def _set_leverage(self) -> None:
        """Set leverage for the trading pair."""
        endpoint = "/v5/position/set-leverage"
        params = {
            "category": "linear",
            "symbol": self.symbol,
            "buyLeverage": str(self.leverage),
            "sellLeverage": str(self.leverage),
        }
        response = bybit_request("POST", endpoint, params, signed=True, logger=self.logger)
        if response and response["retCode"] == 0:
            self.logger.info(
                f"{NEON_GREEN}[{self.symbol}] Leverage set to {self.leverage}x.{RESET}"
            )
        else:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Failed to set leverage to {self.leverage}x. Error: {response.get('retMsg') if response else 'Unknown'}{RESET}"
            )

    def _get_available_balance(self) -> Decimal:
        """Fetch current available account balance for order sizing."""
        if not self.trade_management_enabled:
            return Decimal(str(self.config["trade_management"]["account_balance"]))

        balance = get_wallet_balance(
            account_type="UNIFIED", coin="USDT", logger=self.logger
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

        account_balance = self._get_available_balance()
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
        order_value_notional = risk_amount / stop_loss_distance_usd
        # Convert to quantity of the asset (e.g., BTC)
        order_qty = order_value_notional / current_price

        # Round order_qty to appropriate precision for the symbol
        precision_str = "0." + "0" * (self.order_precision - 1) + "1"
        order_qty = order_qty.quantize(Decimal(precision_str), rounding=ROUND_DOWN)

        if order_qty <= Decimal("0"):
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated order quantity ({order_qty.normalize()}) is too small or zero. Cannot open position.{RESET}"
            )
            return Decimal("0")

        self.logger.info(
            f"[{self.symbol}] Calculated order size: {order_qty.normalize()} (Risk: {risk_amount.normalize():.2f} USDT, SL Distance: {stop_loss_distance_usd.normalize():.4f})"
        )
        return order_qty

    def open_position(
        self, signal: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal
    ) -> dict | None:
        """Open a new position if conditions allow by placing an order on the exchange."""
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Trade management is disabled. Skipping opening position.{RESET}"
            )
            return None

        # Check if we already have an open position for this symbol
        if self.symbol in self.open_positions and self.open_positions[self.symbol]["status"] == "OPEN":
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Already have an open position. Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
            )
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
        entry_price = current_price # For Market orders, entry price is roughly current price

        if signal == "BUY":
            stop_loss_price = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit_price = current_price + (atr_value * take_profit_atr_multiple)
        else:  # SELL
            stop_loss_price = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit_price = current_price - (atr_value * take_profit_atr_multiple)

        price_precision_str = "0." + "0" * (self.price_precision - 1) + "1"
        entry_price = entry_price.quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        )
        stop_loss_price = stop_loss_price.quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        )
        take_profit_price = take_profit_price.quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        )

        self.logger.info(
            f"[{self.symbol}] Attempting to place {side} order: Qty={order_qty.normalize()}, SL={stop_loss_price.normalize()}, TP={take_profit_price.normalize()}"
        )

        placed_order = place_order(
            symbol=self.symbol,
            side=side,
            order_type=self.order_mode,
            qty=order_qty,
            price=entry_price if self.order_mode == "Limit" else None,
            take_profit=take_profit_price,
            stop_loss=stop_loss_price,
            tp_sl_mode=self.tp_sl_mode,
            logger=self.logger,
        )

        if placed_order:
            self.logger.info(
                f"{NEON_GREEN}[{self.symbol}] Successfully initiated {signal} trade with order ID: {placed_order.get('orderId')}{RESET}"
            )
            # For logging/tracking purposes, return a simplified representation
            return {
                "entry_time": datetime.now(TIMEZONE),
                "symbol": self.symbol,
                "side": signal,
                "entry_price": entry_price, # This might be different from actual fill price for market orders
                "qty": order_qty,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price,
                "status": "OPEN",
                "order_id": placed_order.get('orderId')
            }
        else:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Failed to place {signal} order. Check API logs for details.{RESET}"
            )
            return None

    def manage_positions(
        self, current_price: Decimal, atr_value: Decimal, performance_tracker: Any
    ) -> None:
        """Check and manage open positions on the exchange (SL/TP are handled by Bybit).
        This method will mainly check if positions are closed and record them.
        It also handles trailing stop logic locally.
        """
        if not self.trade_management_enabled or not self.open_positions:
            return

        positions_to_remove = []
        for symbol, position in self.open_positions.items():
            if position["status"] == "OPEN":
                side = position["side"]
                entry_price = position["entry_price"]
                stop_loss = position["stop_loss"]
                take_profit = position["take_profit"]
                qty = position["qty"]
                is_trailing_activated = position.get("is_trailing_activated", False)
                current_trailing_sl = position.get("current_trailing_sl", stop_loss)

                closed_by = ""
                exit_price = Decimal("0")

                # Check for Stop Loss or Take Profit hits
                if side == "BUY":
                    if current_price <= stop_loss:
                        closed_by = "STOP_LOSS"
                        exit_price = stop_loss # Use SL price for exit if hit
                    elif current_price >= take_profit:
                        closed_by = "TAKE_PROFIT"
                        exit_price = take_profit # Use TP price for exit if hit
                    elif is_trailing_activated and current_price <= current_trailing_sl:
                        closed_by = "TRAILING_STOP_LOSS"
                        exit_price = current_trailing_sl
                elif side == "SELL":
                    if current_price >= stop_loss:
                        closed_by = "STOP_LOSS"
                        exit_price = stop_loss
                    elif current_price <= take_profit:
                        closed_by = "TAKE_PROFIT"
                        exit_price = take_profit
                    elif is_trailing_activated and current_price >= current_trailing_sl:
                        closed_by = "TRAILING_STOP_LOSS"
                        exit_price = current_trailing_sl

                if closed_by:
                    position["status"] = "CLOSED"
                    position["exit_time"] = datetime.now(TIMEZONE)
                    position["exit_price"] = exit_price.quantize(
                        Decimal("0." + "0" * (selfA user provided a Python script (`wb.py`) and a configuration file (`config.json`). The user also provided several markdown files (`pybit2.md`, `pybit.md`, `pybit.md`, `pybit.md`, `pybit.md`) which seem to be documentation snippets related to the `pybit` library. The request is to analyze the code, upgrade and enhance it, and return the complete improved code incorporating all ideas.

Here's a breakdown of the tasks and how I'll approach them:

1.  **Analyze Provided Code**: Understand the functionality of `wb.py`, `config.json`, and the `pybit` documentation snippets.
2.  **Identify Enhancement Areas**: Based on the provided config and the `pybit` documentation, identify potential improvements such as:
    *   **Asynchronous Operations**: `pybit` supports asynchronous operations, which would be beneficial for handling multiple WebSocket streams and API calls concurrently.
    *   **Error Handling and Retries**: Enhance robustness for API requests and WebSocket connections.
    *   **Modularity**: Improve the structure by separating concerns into different classes (e.g., `BybitClient`, `IndicatorCalculator`, `SignalGenerator`, `PositionManager`, `PerformanceTracker`).
    *   **Indicator Integration**: Ensure all configured indicators are calculated and used effectively.
    *   **Risk Management**: Implement stop-loss, take-profit, and potentially trailing stops based on ATR.
    *   **Order Sizing**: Dynamically calculate order sizes based on account balance, risk per trade, and ATR.
    *   **Configuration Loading**: Ensure `config.json` is loaded correctly and defaults are handled.
    *   **Logging**: Improve logging with sensitive data redaction and better formatting.
    *   **Gemini AI Integration**: If `gemini_ai_analysis` is enabled, integrate its functionality.
    *   **Orderbook Analysis**: Implement orderbook imbalance calculations.
    *   **MTF Analysis**: Integrate multi-timeframe analysis as configured.
3.  **Upgrade and Enhance**:
    *   **Refactor `wb.py`**: Convert the main script into a more object-oriented structure with classes for different functionalities.
    *   **Implement Asynchronous Logic**: Use `asyncio` for WebSocket handling and potentially for API calls where appropriate.
    *   **Integrate `pybit`**: Ensure all necessary `pybit` functions (HTTP and WebSocket) are used correctly within the new structure.
    *   **Add Missing Functionality**: Implement features suggested by the config and documentation but not fully present in `wb.py` (e.g., proper trailing stops, more detailed position management).
    *   **Improve Signal Generation**: Create a dedicated `SignalGenerator` or `TradingAnalyzer` class that takes indicator data and config to produce a weighted signal.
    *   **Enhance Risk Management**: Implement dynamic order sizing, stop-loss, and take-profit calculations based on ATR and config parameters.
    *   **Add Performance Tracking**: Implement a class to track trades, wins, losses, PnL, etc.
    *   **Gemini AI Integration**: Add a placeholder or actual integration for Gemini AI if its configuration is enabled.
4.  **Return Complete Improved Code**: Provide a single, runnable Python script that integrates all these enhancements.

Given the extensive nature of the provided code and the request to merge and enhance, I will focus on creating a robust, asynchronous trading bot structure that leverages the `pybit` library effectively and incorporates the configuration options.

```python
# -*- coding: utf-8 -*-
"""Whalebot: An automated cryptocurrency trading bot for Bybit.

This bot leverages various technical indicators and multi-timeframe analysis
to generate trading signals and manage positions on the Bybit exchange.
It includes features for risk management, performance tracking, and alerts.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import sys
import time
import urllib.parse
import random
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Generic, Literal, Optional, Tuple, TypeVar, Dict, List, Union, Callable

import numpy as np
import pandas as pd
import pandas_ta as ta
import requests
from colorama import Fore, Style, init
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from zoneinfo import ZoneInfo

# Note: Scikit-learn is explicitly excluded as per user request.
# SKLEARN_AVAILABLE variable is removed as it is unused and its presence might suggest ML features.

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
TIMEZONE = timezone.utc
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
            "account_balance": 1000.0,  # Simulated balance if not using real API
            "risk_per_trade_percent": 1.0,  # Percentage of account_balance to risk
            "stop_loss_atr_multiple": 1.5,  # Stop loss distance as multiple of ATR
            "take_profit_atr_multiple": 2.0,  # Take profit distance as multiple of ATR
            "trailing_stop_atr_multiple": 0.3, # Trailing stop distance as multiple of ATR
            "max_open_positions": 1,
            "order_precision": 4,  # Decimal places for order quantity
            "price_precision": 2,  # Decimal places for price
            "leverage": 10,  # Leverage for perpetual contracts
            "order_mode": "MARKET",  # MARKET or LIMIT for entry orders
            "take_profit_type": "MARKET", # MARKET or LIMIT for TP
            "stop_loss_type": "MARKET", # MARKET or LIMIT for SL
            "trailing_stop_activation_percent": 0.5, # % profit to activate trailing stop
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
            "volatility_index_period": 20,
            "vwma_period": 20,
            "volume_delta_period": 5,
            "volume_delta_threshold": 0.2,
            "vwap_daily_reset": False, # Should VWAP reset daily or be continuous
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
        "weight_sets": {
            "default_scalping": {
                "ema_alignment": 0.22,
                "sma_trend_filter": 0.28,
                "momentum_rsi_stoch_cci_wr_mfi": 0.18,
                "volume_confirmation": 0.12,
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
            "weight": 0.3, # Weight of Gemini's signal in the final score
        }
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(
                f"{NEON_YELLOW}Configuration file not found. Created default config at {filepath} for symbol {default_config['symbol']}{RESET}"
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
    headers = {"Content-Type": "application/json"}
    params = params if params is not None else {}

    if signed:
        if not API_KEY or not API_SECRET:
            logger.error(
                f"{NEON_RED}API_KEY or API_SECRET not set for signed request. Cannot proceed.{RESET}"
            )
            return None

        timestamp = str(int(time.time() * 1000))
        recv_window = "20000"

        if method == "GET":
            query_string = urllib.parse.urlencode(params)
            param_str = timestamp + API_KEY + recv_window + query_string
            signature = generate_signature(param_str, API_SECRET)
            headers.update(
                {
                    "X-BAPI-API-KEY": API_KEY,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": recv_window,
                }
            )
            full_url = f"{url}?{query_string}" if query_string else url
            logger.debug(f"GET Request to {full_url}")
            response = session.get(
                url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
            )
        else:  # POST
            json_params = json.dumps(params)
            param_str = timestamp + API_KEY + recv_window + json_params
            signature = generate_signature(param_str, API_SECRET)
            headers.update(
                {
                    "X-BAPI-API-KEY": API_KEY,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": recv_window,
                }
            )
            logger.debug(f"POST Request to {url} with payload {json_params}")
            response = session.post(
                url, json=params, headers=headers, timeout=REQUEST_TIMEOUT
            )
    else:
        logger.debug(f"Public Request to {url} with params {params}")
        response = session.get(
            url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
        )

    try:
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") != 0:
            logger.error(
                f"{NEON_RED}Bybit API Error ({endpoint}): {data.get('retMsg')} (Code: {data.get('retCode')}){RESET}"
            )
            return None
        return data
    except requests.exceptions.HTTPError as e:
        logger.error(
            f"{NEON_RED}HTTP Error ({endpoint}): {e.response.status_code} - {e.response.text}{RESET}"
        )
    except requests.exceptions.ConnectionError as e:
        logger.error(f"{NEON_RED}Connection Error ({endpoint}): {e}{RESET}")
    except requests.exceptions.Timeout:
        logger.error(
            f"{NEON_RED}Request to {endpoint} timed out after {REQUEST_TIMEOUT} seconds.{RESET}"
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"{NEON_RED}Request Exception ({endpoint}): {e}{RESET}")
    except json.JSONDecodeError:
        logger.error(
            f"{NEON_RED}Failed to decode JSON response from {endpoint}: {response.text}{RESET}"
        )
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
    symbol: str, interval: str, limit: int, logger: logging.Logger
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


def get_wallet_balance(
    account_type: Literal["UNIFIED", "CONTRACT"], coin: str, logger: logging.Logger
) -> Decimal | None:
    """Fetch wallet balance for a specific coin."""
    endpoint = "/v5/account/wallet-balance"
    params = {"accountType": account_type, "coin": coin}
    response = bybit_request("GET", endpoint, params, signed=True, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        for item in response["result"]["list"]:
            if item["coin"][0]["coin"] == coin:
                balance = Decimal(item["coin"][0]["walletBalance"])
                logger.debug(f"Fetched {coin} wallet balance: {balance}")
                return balance
    logger.warning(f"{NEON_YELLOW}Could not fetch {coin} wallet balance.{RESET}")
    return None


def get_exchange_open_positions(
    symbol: str, category: str, logger: logging.Logger
) -> list[dict] | None:
    """Fetch currently open positions from the exchange."""
    endpoint = "/v5/position/list"
    params = {"category": category, "symbol": symbol}
    response = bybit_request("GET", endpoint, params, signed=True, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        return response["result"]["list"]
    return []


def place_order(
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
) -> dict | None:
    """Place an order on Bybit."""
    if logger is None:
        logger = setup_logger("bybit_api")

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

    # Add TP/SL to the order itself
    if take_profit is not None:
        params["takeProfit"] = str(take_profit)
        params["tpslMode"] = tp_sl_mode
    if stop_loss is not None:
        params["stopLoss"] = str(stop_loss)
        params["tpslMode"] = tp_sl_mode

    endpoint = "/v5/order/create"
    response = bybit_request("POST", endpoint, params, signed=True, logger=logger)
    if response:
        logger.info(
            f"{NEON_GREEN}Order placed successfully for {symbol}: {response['result']}{RESET}"
        )
        return response["result"]
    logger.error(f"{NEON_RED}Failed to place order for {symbol}: {params}{RESET}")
    return None


def cancel_order(
    symbol: str, order_id: str, logger: logging.Logger | None = None
) -> dict | None:
    """Cancel an existing order on Bybit."""
    if logger is None:
        logger = setup_logger("bybit_api")
    endpoint = "/v5/order/cancel"
    params = {"category": "linear", "symbol": symbol, "orderId": order_id}
    response = bybit_request("POST", endpoint, params, signed=True, logger=logger)
    if response:
        logger.info(
            f"{NEON_GREEN}Order {order_id} cancelled for {symbol}: {response['result']}{RESET}"
        )
        return response["result"]
    logger.error(
        f"{NEON_RED}Failed to cancel order {order_id} for {symbol}.{RESET}"
    )
    return None


# --- Position Management ---
class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""

    def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str):
        """Initializes the PositionManager."""
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.open_positions: dict[str, dict] = {} # Tracks positions opened by the bot locally
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]
        self.leverage = config["trade_management"]["leverage"]
        self.order_mode = config["trade_management"]["order_mode"]
        self.tp_sl_mode = "Full" # Default to full for simplicity, can be configured
        self.trailing_stop_activation_percent = Decimal(str(config["trade_management"]["trailing_stop_activation_percent"])) / 100

        # Set leverage (only once or when changed)
        if self.trade_management_enabled:
            self._set_leverage()

    def _set_leverage(self) -> None:
        """Set leverage for the trading pair."""
        endpoint = "/v5/position/set-leverage"
        params = {
            "category": "linear",
            "symbol": self.symbol,
            "buyLeverage": str(self.leverage),
            "sellLeverage": str(self.leverage),
        }
        response = bybit_request("POST", endpoint, params, signed=True, logger=self.logger)
        if response and response["retCode"] == 0:
            self.logger.info(
                f"{NEON_GREEN}[{self.symbol}] Leverage set to {self.leverage}x.{RESET}"
            )
        else:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Failed to set leverage to {self.leverage}x. Error: {response.get('retMsg') if response else 'Unknown'}{RESET}"
            )

    def _get_available_balance(self) -> Decimal:
        """Fetch current available account balance for order sizing."""
        if not self.trade_management_enabled:
            return Decimal(str(self.config["trade_management"]["account_balance"]))

        balance = get_wallet_balance(
            account_type="UNIFIED", coin="USDT", logger=self.logger
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

        account_balance = self._get_available_balance()
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
        order_value_notional = risk_amount / stop_loss_distance_usd
        # Convert to quantity of the asset (e.g., BTC)
        order_qty = order_value_notional / current_price

        # Round order_qty to appropriate precision for the symbol
        precision_str = "0." + "0" * (self.order_precision - 1) + "1"
        order_qty = order_qty.quantize(Decimal(precision_str), rounding=ROUND_DOWN)

        if order_qty <= Decimal("0"):
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Calculated order quantity ({order_qty.normalize()}) is too small or zero. Cannot open position.{RESET}"
            )
            return Decimal("0")

        self.logger.info(
            f"[{self.symbol}] Calculated order size: {order_qty.normalize()} (Risk: {risk_amount.normalize():.2f} USDT, SL Distance: {stop_loss_distance_usd.normalize():.4f})"
        )
        return order_qty

    def open_position(
        self, signal: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal
    ) -> dict | None:
        """Open a new position if conditions allow by placing an order on the exchange."""
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}[{self.symbol}] Trade management is disabled. Skipping opening position.{RESET}"
            )
            return None

        # Check if we already have an open position for this symbol
        if self.symbol in self.open_positions and self.open_positions[self.symbol]["status"] == "OPEN":
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] Already have an open position. Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
            )
            return None

        if self.max_open_positions > 0 and len(self.open_positions) >= self.max_open_positions:
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
        entry_price = current_price # For Market orders, entry price is roughly current price

        if signal == "BUY":
            stop_loss_price = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit_price = current_price + (atr_value * take_profit_atr_multiple)
        else:  # SELL
            stop_loss_price = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit_price = current_price - (atr_value * take_profit_atr_multiple)

        price_precision_str = "0." + "0" * (self.price_precision - 1) + "1"
        entry_price = entry_price.quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        )
        stop_loss_price = stop_loss_price.quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        )
        take_profit_price = take_profit_price.quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        )

        self.logger.info(
            f"[{self.symbol}] Attempting to place {side} order: Qty={order_qty.normalize()}, SL={stop_loss_price.normalize()}, TP={take_profit_price.normalize()}"
        )

        placed_order = place_order(
            symbol=self.symbol,
            side=side,
            order_type=self.order_mode,
            qty=order_qty,
            price=entry_price if self.order_mode == "Limit" else None,
            take_profit=take_profit_price,
            stop_loss=stop_loss_price,
            tp_sl_mode=self.tp_sl_mode,
            logger=self.logger,
        )

        if placed_order:
            self.logger.info(
                f"{NEON_GREEN}[{self.symbol}] Successfully initiated {signal} trade with order ID: {placed_order.get('orderId')}{RESET}"
            )
            # For logging/tracking purposes, return a simplified representation
            return {
                "entry_time": datetime.now(TIMEZONE),
                "symbol": self.symbol,
                "side": signal,
                "entry_price": entry_price, # This might be different from actual fill price for market orders
                "qty": order_qty,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price,
                "status": "OPEN",
                "order_id": placed_order.get('orderId')
            }
        else:
            self.logger.error(
                f"{NEON_RED}[{self.symbol}] Failed to place {signal} order. Check API logs for details.{RESET}"
            )
            return None

    def manage_positions(
        self, current_price: Decimal, atr_value: Decimal, performance_tracker: Any
    ) -> None:
        """Check and manage open positions on the exchange (SL/TP are handled by Bybit).
        This method will mainly check if positions are closed and record them.
        It also handles trailing stop logic locally.
        """
        if not self.trade_management_enabled or not self.open_positions:
            return

        positions_to_remove = []
        for symbol, position in self.open_positions.items():
            if position["status"] == "OPEN":
                side = position["side"]
                entry_price = position["entry_price"]
                stop_loss = position["stop_loss"]
                take_profit = position["take_profit"]
                qty = position["qty"]
                is_trailing_activated = position.get("is_trailing_activated", False)
                current_trailing_sl = position.get("current_trailing_sl", stop_loss)

                closed_by = ""
                exit_price = Decimal("0")

                # Check for Stop Loss or Take Profit hits
                if side == "BUY":
                    if current_price <= stop_loss:
                        closed_by = "STOP_LOSS"
                        exit_price = stop_loss # Use SL price for exit if hit
                    elif current_price >= take_profit:
                        closed_by = "TAKE_PROFIT"
                        exit_price = take_profit # Use TP price for exit if hit
                    elif is_trailing_activated and current_price <= current_trailing_sl:
                        closed_by = "TRAILING_STOP_LOSS"
                        exit_price = current_trailing_sl
                elif side == "SELL":
                    if current_price >= stop_loss:
                        closed_by = "STOP_LOSS"
                        exit_price = stop_loss
                    elif current_price <= take_profit:
                        closed_by = "TAKE_PROFIT"
                        exit_price = take_profit
                    elif is_trailing_activated and current_price >= current_trailing_sl:
                        closed_by = "TRAILING_STOP_LOSS"
                        exit_price = current_trailing_sl

                if closed_by:
                    self.logger.info(
                        f"{NEON_PURPLE}Position for {symbol} closed by {closed_by}. Closing position.{RESET}"
                    )
                    # In a real scenario, you'd send a cancel_all_orders or close position API call here
                    # For this simulation, we just mark it as closed and record the trade.
                    position["status"] = "CLOSED"
                    position["exit_time"] = datetime.now(TIMEZONE)
                    position["exit_price"] = exit_price.quantize(
                        Decimal("0." + "0" * (self.price_precision - 1) + "1"), rounding=ROUND_DOWN
                    )
                    position["closed_by"] = closed_by

                    pnl = (
                        (exit_price - entry_price) * qty
                        if side == "BUY"
                        else (entry_price - exit_price) * qty
                    )
                    performance_tracker.record_trade(position, pnl)
                    positions_to_remove.append(symbol)
                    continue # Move to the next position

                # Handle Trailing Stop Logic
                if not is_trailing_activated:
                    # Check if activation threshold is met
                    if (side == "BUY" and current_price >= entry_price * (1 + self.trailing_stop_activation_percent)) or \
                       (side == "SELL" and current_price <= entry_price * (1 - self.trailing_stop_activation_percent)):
                        
                        position["is_trailing_activated"] = True
                        
                        # Calculate initial trailing stop price
                        if side == "BUY":
                            initial_trailing_sl = current_price - (atr_value * Decimal(str(self.config["trade_management"]["trailing_stop_atr_multiple"])))
                            position["current_trailing_sl"] = initial_trailing_sl.quantize(Decimal("0." + "0" * (self.price_precision - 1) + "1"), rounding=ROUND_DOWN)
                        else: # SELL
                            initial_trailing_sl = current_price + (atr_value * Decimal(str(self.config["trade_management"]["trailing_stop_atr_multiple"])))
                            position["current_trailing_sl"] = initial_trailing_sl.quantize(Decimal("0." + "0" * (self.price_precision - 1) + "1"), rounding=ROUND_DOWN)
                        
                        self.logger.info(f"Trailing stop activated for {symbol}. Initial SL: {position['current_trailing_sl']}")
                        # In a real bot, you'd call an API to set this trailing stop
                        # For now, we just update the local state.
                else:
                    # Trailing stop is active, check if it needs updating
                    potential_new_sl = Decimal("0")
                    if side == "BUY":
                        potential_new_sl = current_price - (atr_value * Decimal(str(self.config["trade_management"]["trailing_stop_atr_multiple"])))
                        if potential_new_sl > current_trailing_sl:
                            potential_new_sl = potential_new_sl.quantize(Decimal("0." + "0" * (self.price_precision - 1) + "1"), rounding=ROUND_DOWN)
                    elif side == "SELL":
                        potential_new_sl = current_price + (atr_value * Decimal(str(self.config["trade_management"]["trailing_stop_atr_multiple"])))
                        if potential_new_sl < current_trailing_sl:
                            potential_new_sl = potential_new_sl.quantize(Decimal("0." + "0" * (self.price_precision - 1) + "1"), rounding=ROUND_DOWN)

                    if potential_new_sl != Decimal("0") and potential_new_sl != current_trailing_sl:
                        # Ensure trailing SL doesn't move against the trade direction relative to entry
                        if (side == "BUY" and potential_new_sl > entry_price) or \
                           (side == "SELL" and potential_new_sl < entry_price):
                            
                            position["current_trailing_sl"] = potential_new_sl
                            self.logger.info(f"Updating trailing stop for {symbol} to {position['current_trailing_sl']}")
                            # In a real bot, you'd call an API to update the trailing stop here.
                            # For simulation, we just update local state.

                # Update the position in our local tracking
                self.open_positions[symbol] = position

        # Remove closed positions from local tracking
        for symbol in positions_to_remove:
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
        self._recalculate_summary() # Recalculate summary from loaded trades

    def _load_trades(self) -> list[dict]:
        """Load trade history from file."""
        if self.config_file.exists():
            try:
                with self.config_file.open("r", encoding="utf-8") as f:
                    raw_trades = json.load(f)
                    # Convert Decimal/datetime from string after loading
                    loaded_trades = []
                    for trade in raw_trades:
                        for key in ["pnl", "entry_price", "exit_price", "qty"]:
                            if key in trade:
                                trade[key] = Decimal(str(trade[key]))
                        for key in ["entry_time", "exit_time"]:
                            if key in trade:
                                trade[key] = datetime.fromisoformat(trade[key])
                        loaded_trades.append(trade)
                    return loaded_trades
            except (json.JSONDecodeError, OSError) as e:
                self.logger.error(f"{NEON_RED}Error loading trades from {self.config_file}: {e}{RESET}")
        return []

    def _save_trades(self) -> None:
        """Save trade history to file."""
        try:
            with self.config_file.open("w", encoding="utf-8") as f:
                # Convert Decimal/datetime to string for JSON serialization
                serializable_trades = []
                for trade in self.trades:
                    s_trade = trade.copy()
                    for key in ["pnl", "entry_price", "exit_price", "qty"]:
                        if key in s_trade:
                            s_trade[key] = str(s_trade[key])
                    for key in ["entry_time", "exit_time"]:
                        if key in s_trade:
                            s_trade[key] = s_trade[key].isoformat()
                    serializable_trades.append(s_trade)
                json.dump(serializable_trades, f, indent=4)
        except OSError as e:
            self.logger.error(f"{NEON_RED}Error saving trades to {self.config_file}: {e}{RESET}")

    def _recalculate_summary(self) -> None:
        """Recalculate summary metrics from the list of trades."""
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0
        for trade in self.trades:
            self.total_pnl += trade["pnl"]
            if trade["pnl"] > 0:
                self.wins += 1
            else:
                self.losses += 1

    def record_trade(self, position: dict, pnl: Decimal) -> None:
        """Record a completed trade."""
        trade_record = {
            "entry_time": position.get("entry_time", datetime.now(TIMEZONE)),
            "exit_time": position.get("exit_time", datetime.now(TIMEZONE)),
            "symbol": position["symbol"],
            "side": position["side"],
            "entry_price": position["entry_price"],
            "exit_price": position["exit_price"],
            "qty": position["qty"],
            "pnl": pnl,
            "closed_by": position.get("closed_by", "UNKNOWN"),
        }
        self.trades.append(trade_record)
        self._recalculate_summary() # Update summary immediately
        self._save_trades() # Save to file
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

    def send_alert(self, message: str, level: Literal["INFO", "WARNING", "ERROR"]) -> None:
        """Send an alert (currently logs it)."""
        # Placeholder for actual alert integrations (Telegram, Discord, Email, etc.)
        # Example for Telegram:
        # if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        #     try:
        #         requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={TELEGRAM_CHAT_ID}&text={message}")
        #     except Exception as e:
        #         self.logger.error(f"Failed to send Telegram alert: {e}")

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

        self.gemini_client: Any | None = None # Placeholder for GeminiClient
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
                self.logger.warning(f"{NEON_YELLOW}Gemini AI analysis enabled, but GeminiClient is not implemented/imported. Placeholder used.{RESET}")
                # Placeholder for GeminiClient if not available
                self.gemini_client = lambda: None


        if not self.df.empty:
            self._calculate_all_indicators()
            if self.config["indicators"].get("fibonacci_levels", False):
                self.calculate_fibonacci_levels()

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
            # Ensure the function only receives df with enough data
            result = func(*args, **kwargs)

            # Check for empty series or all NaNs
            if isinstance(result, pd.Series) and (result.empty or result.isnull().all()):
                self.logger.warning(
                    f"{NEON_YELLOW}Indicator '{name}' returned an empty or all-NaN Series. Not enough valid data?{RESET}"
                )
                return None
            if (
                isinstance(result, tuple)
                and all(
                    isinstance(r, pd.Series) and (r.empty or r.isnull().all())
                    for r in result
                )
            ):
                self.logger.warning(
                    f"{NEON_YELLOW}Indicator '{name}' returned all-empty or all-NaN Series in tuple. Not enough valid data?{RESET}"
                )
                return None
            return result
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}Error calculating indicator '{name}': {e}{RESET}", exc_info=True # Add exc_info for full traceback
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
        # ATR
        self.df["ATR"] = self._safe_calculate(
            lambda: ta.atr(self.df["high"], self.df["low"], self.df["close"], length=isd["atr_period"]),
            "ATR",
            min_data_points=isd["atr_period"],
        )
        if self.df["ATR"] is not None and not self.df["ATR"].empty:
            self.indicator_values["ATR"] = Decimal(str(self.df["ATR"].iloc[-1]))
        else:
            self.indicator_values["ATR"] = Decimal("0.01") # Default to a small value

        # SMA
        if cfg["indicators"].get("sma_10", False):
            self.df["SMA_10"] = self._safe_calculate(
                lambda: ta.sma(self.df["close"], length=isd["sma_short_period"]),
                "SMA_10",
                min_data_points=isd["sma_short_period"],
            )
            if self.df["SMA_10"] is not None and not self.df["SMA_10"].empty:
                self.indicator_values["SMA_10"] = Decimal(str(self.df["SMA_10"].iloc[-1]))
        if cfg["indicators"].get("sma_trend_filter", False):
            self.df["SMA_Long"] = self._safe_calculate(
                lambda: ta.sma(self.df["close"], length=isd["sma_long_period"]),
                "SMA_Long",
                min_data_points=isd["sma_long_period"],
            )
            if self.df["SMA_Long"] is not None and not self.df["SMA_Long"].empty:
                self.indicator_values["SMA_Long"] = Decimal(str(self.df["SMA_Long"].iloc[-1]))

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
                self.indicator_values["EMA_Short"] = Decimal(str(self.df["EMA_Short"].iloc[-1]))
            if self.df["EMA_Long"] is not None and not self.df["EMA_Long"].empty:
                self.indicator_values["EMA_Long"] = Decimal(str(self.df["EMA_Long"].iloc[-1]))

        # RSI
        if cfg["indicators"].get("rsi", False):
            self.df["RSI"] = self._safe_calculate(
                lambda: ta.rsi(self.df["close"], length=isd["rsi_period"]),
                "RSI",
                min_data_points=isd["rsi_period"] + 1,
            )
            if self.df["RSI"] is not None and not self.df["RSI"].empty:
                self.indicator_values["RSI"] = float(self.df["RSI"].iloc[-1]) # Keep as float, typical for RSI

        # Stochastic RSI
        if cfg["indicators"].get("stoch_rsi", False):
            stoch_rsi_k, stoch_rsi_d = self._safe_calculate(
                self.calculate_stoch_rsi,
                "StochRSI",
                min_data_points=isd["stoch_rsi_period"]
                + isd["stoch_d_period"]
                + isd["stoch_k_period"], # Minimum period for StochRSI itself plus smoothing
                period=isd["stoch_rsi_period"],
                k_period=isd["stoch_k_period"],
                d_period=isd["stoch_d_period"],
            )
            if stoch_rsi_k is not None:
                self.df["StochRSI_K"] = stoch_rsi_k
            if stoch_rsi_d is not None:
                self.df["StochRSI_D"] = stoch_rsi_d
            if stoch_rsi_k is not None and not stoch_rsi_k.empty:
                self.indicator_values["StochRSI_K"] = float(stoch_rsi_k.iloc[-1])
            if stoch_rsi_d is not None and not stoch_rsi_d.empty:
                self.indicator_values["StochRSI_D"] = float(stoch_rsi_d.iloc[-1])

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
                self.indicator_values["BB_Upper"] = Decimal(str(bb_upper.iloc[-1]))
            if bb_middle is not None and not bb_middle.empty:
                self.indicator_values["BB_Middle"] = Decimal(str(bb_middle.iloc[-1]))
            if bb_lower is not None and not bb_lower.empty:
                self.indicator_values["BB_Lower"] = Decimal(str(bb_lower.iloc[-1]))

        # CCI
        if cfg["indicators"].get("cci", False):
            self.df["CCI"] = self._safe_calculate(
                lambda: ta.cci(self.df["high"], self.df["low"], self.df["close"], length=isd["cci_period"]),
                "CCI",
                min_data_points=isd["cci_period"],
            )
            if self.df["CCI"] is not None and not self.df["CCI"].empty:
                self.indicator_values["CCI"] = float(self.df["CCI"].iloc[-1])

        # Williams %R
        if cfg["indicators"].get("wr", False):
            self.df["WR"] = self._safe_calculate(
                lambda: ta.willr(self.df["high"], self.df["low"], self.df["close"], length=isd["williams_r_period"]),
                "WR",
                min_data_points=isd["williams_r_period"],
            )
            if self.df["WR"] is not None and not self.df["WR"].empty:
                self.indicator_values["WR"] = float(self.df["WR"].iloc[-1])

        # MFI
        if cfg["indicators"].get("mfi", False):
            self.df["MFI"] = self._safe_calculate(
                lambda: ta.mfi(self.df["high"], self.df["low"], self.df["close"], self.df["volume"], length=isd["mfi_period"]),
                "MFI",
                min_data_points=isd["mfi_period"] + 1,
            )
            if self.df["MFI"] is not None and not self.df["MFI"].empty:
                self.indicator_values["MFI"] = float(self.df["MFI"].iloc[-1])

        # OBV
        if cfg["indicators"].get("obv", False):
            obv_val, obv_ema = self._safe_calculate(
                self.calculate_obv,
                "OBV",
                min_data_points=isd["obv_ema_period"], # OBV itself has no period, but EMA does
                ema_period=isd["obv_ema_period"],
            )
            if obv_val is not None:
                self.df["OBV"] = obv_val
            if obv_ema is not None:
                self.df["OBV_EMA"] = obv_ema
            if obv_val is not None and not obv_val.empty:
                self.indicator_values["OBV"] = float(obv_val.iloc[-1])
            if obv_ema is not None and not obv_ema.empty:
                self.indicator_values["OBV_EMA"] = float(obv_ema.iloc[-1])

        # CMF
        if cfg["indicators"].get("cmf", False):
            cmf_val = self._safe_calculate(
                lambda: ta.cmf(self.df["high"], self.df["low"], self.df["close"], self.df["volume"], length=isd["cmf_period"]),
                "CMF",
                min_data_points=isd["cmf_period"],
            )
            if cmf_val is not None:
                self.df["CMF"] = cmf_val
            if cmf_val is not None and not cmf_val.empty:
                self.indicator_values["CMF"] = float(cmf_val.iloc[-1])

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
                self.indicator_values["Tenkan_Sen"] = Decimal(str(tenkan_sen.iloc[-1]))
            if kijun_sen is not None and not kijun_sen.empty:
                self.indicator_values["Kijun_Sen"] = Decimal(str(kijun_sen.iloc[-1]))
            if senkou_span_a is not None and not senkou_span_a.empty:
                self.indicator_values["Senkou_Span_A"] = Decimal(str(senkou_span_a.iloc[-1]))
            if senkou_span_b is not None and not senkou_span_b.empty:
                self.indicator_values["Senkou_Span_B"] = Decimal(str(senkou_span_b.iloc[-1]))
            if chikou_span is not None and not chikou_span.empty:
                self.indicator_values["Chikou_Span"] = Decimal(str(chikou_span.fillna(0).iloc[-1]))

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
                self.indicator_values["PSAR_Val"] = Decimal(str(psar_val.iloc[-1]))
            if psar_dir is not None and not psar_dir.empty:
                self.indicator_values["PSAR_Dir"] = float(psar_dir.iloc[-1])

        # VWAP (requires volume and turnover, which are in df)
        if cfg["indicators"].get("vwap", False):
            self.df["VWAP"] = self._safe_calculate(
                lambda: ta.vwap(self.df["high"], self.df["low"], self.df["close"], self.df["volume"]),
                "VWAP",
                min_data_points=1,
            )
            if self.df["VWAP"] is not None and not self.df["VWAP"].empty:
                self.indicator_values["VWAP"] = Decimal(str(self.df["VWAP"].iloc[-1]))

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
                self.indicator_values["ST_Fast_Dir"] = float(st_fast_result["direction"].iloc[-1])
                self.indicator_values["ST_Fast_Val"] = Decimal(str(st_fast_result["supertrend"].iloc[-1]))

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
                self.indicator_values["ST_Slow_Dir"] = float(st_slow_result["direction"].iloc[-1])
                self.indicator_values["ST_Slow_Val"] = Decimal(str(st_slow_result["supertrend"].iloc[-1]))

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
                self.indicator_values["MACD_Line"] = float(macd_line.iloc[-1])
            if signal_line is not None and not signal_line.empty:
                self.indicator_values["MACD_Signal"] = float(signal_line.iloc[-1])
            if histogram is not None and not histogram.empty:
                self.indicator_values["MACD_Hist"] = float(histogram.iloc[-1])

        # ADX
        if cfg["indicators"].get("adx", False):
            adx_val, plus_di, minus_di = self._safe_calculate(
                self.calculate_adx,
                "ADX",
                min_data_points=isd["adx_period"] * 2,
                period=isd["adx_period"],
            )
            if adx_val is not None:
                self.df["ADX"] = adx_val
            if plus_di is not None:
                self.df["PlusDI"] = plus_di
            if minus_di is not None:
                self.df["MinusDI"] = minus_di
            if adx_val is not None and not adx_val.empty:
                self.indicator_values["ADX"] = float(adx_val.iloc[-1])
            if plus_di is not None and not plus_di.empty:
                self.indicator_values["PlusDI"] = float(plus_di.iloc[-1])
            if minus_di is not None and not minus_di.empty:
                self.indicator_values["MinusDI"] = float(minus_di.iloc[-1])

        # --- New Indicators ---
        # Volatility Index
        if cfg["indicators"].get("volatility_index", False):
            self.df["Volatility_Index"] = self._safe_calculate(
                lambda: self.calculate_volatility_index(period=isd["volatility_index_period"]),
                "Volatility_Index",
                min_data_points=isd["volatility_index_period"],
            )
            if self.df["Volatility_Index"] is not None and not self.df["Volatility_Index"].empty:
                self.indicator_values["Volatility_Index"] = float(self.df["Volatility_Index"].iloc[-1])

        # VWMA
        if cfg["indicators"].get("vwma", False):
            self.df["VWMA"] = self._safe_calculate(
                lambda: self.calculate_vwma(period=isd["vwma_period"]),
                "VWMA",
                min_data_points=isd["vwma_period"],
            )
            if self.df["VWMA"] is not None and not self.df["VWMA"].empty:
                self.indicator_values["VWMA"] = Decimal(str(self.df["VWMA"].iloc[-1]))

        # Volume Delta
        if cfg["indicators"].get("volume_delta", False):
            self.df["Volume_Delta"] = self._safe_calculate(
                lambda: self.calculate_volume_delta(period=isd["volume_delta_period"]),
                "Volume_Delta",
                min_data_points=isd["volume_delta_period"],
            )
            if self.df["Volume_Delta"] is not None and not self.df["Volume_Delta"].empty:
                self.indicator_values["Volume_Delta"] = float(self.df["Volume_Delta"].iloc[-1])

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
            return pd.Series(np.nan, index=self.df.index)
        high_low = self._safe_series_op(self.df["high"] - self.df["low"], "TR_high_low")
        high_prev_close = self._safe_series_op((self.df["high"] - self.df["close"].shift()).abs(), "TR_high_prev_close")
        low_prev_close = self._safe_series_op((self.df["low"] - self.df["close"].shift()).abs(), "TR_low_prev_close")
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(
            axis=1
        )

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SUPERSMOOTHER:
            return pd.Series(np.nan, index=series.index)

        # Drop NaNs for calculation, reindex at the end
        series_clean = self._safe_series_op(series, "SuperSmoother_input").dropna()
        if len(series_clean) < MIN_DATA_POINTS_SUPERSMOOTHER:
            return pd.Series(np.nan, index=series.index)

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
        return filt.reindex(self.df.index) # Reindex to original DataFrame index

    def calculate_ehlers_supertrend(
        self, period: int, multiplier: float
    ) -> pd.DataFrame | None:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3:
            self.logger.debug(
                f"[{self.symbol}] Not enough data for Ehlers SuperTrend (period={period}). Need at least {period*3} bars."
            )
            return None

        df_copy = self.df.copy()

        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)

        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr

        # Drop NaNs introduced by smoothing to work with complete data for SuperTrend calculation
        df_clean = df_copy.dropna(subset=["smoothed_price", "smoothed_atr", "close", "high", "low"])
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
        first_valid_idx = 0
        while first_valid_idx < len(df_clean) and (
            pd.isna(df_clean["close"].iloc[first_valid_idx]) or
            pd.isna(upper_band.iloc[first_valid_idx]) or
            pd.isna(lower_band.iloc[first_valid_idx])
        ):
            first_valid_idx += 1

        if first_valid_idx >= len(df_clean):
            return None # No valid data points

        if df_clean["close"].iloc[first_valid_idx] > upper_band.iloc[first_valid_idx]:
            direction.iloc[first_valid_idx] = 1 # 1 for Up
            supertrend.iloc[first_valid_idx] = lower_band.iloc[first_valid_idx]
        else:
            direction.iloc[first_valid_idx] = -1 # -1 for Down
            supertrend.iloc[first_valid_idx] = upper_band.iloc[first_valid_idx]

        for i in range(first_valid_idx + 1, len(df_clean)):
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
        return result.reindex(self.df.index) # Reindex to original DataFrame index

    def calculate_macd(
        self, fast_period: int, slow_period: int, signal_period: int
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan, index=self.df.index), pd.Series(np.nan, index=self.df.index), pd.Series(np.nan, index=self.df.index)

        macd_result = ta.macd(self.df["close"], fast=fast_period, slow=slow_period, signal=signal_period)
        if macd_result.empty:
            return pd.Series(np.nan, index=self.df.index), pd.Series(np.nan, index=self.df.index), pd.Series(np.nan, index=self.df.index)

        macd_line = self._safe_series_op(macd_result[f'MACD_{fast_period}_{slow_period}_{signal_period}'], "MACD_Line")
        signal_line = self._safe_series_op(macd_result[f'MACDs_{fast_period}_{slow_period}_{signal_period}'], "MACD_Signal")
        histogram = self._safe_series_op(macd_result[f'MACDh_{fast_period}_{slow_period}_{signal_period}'], "MACD_Hist")

        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index)
        rsi = ta.rsi(self.df["close"], length=period)
        return self._safe_series_op(rsi, "RSI").fillna(0).clip(0, 100) # Clip to [0, 100] and fill NaNs

    def calculate_stoch_rsi(
        self, period: int, k_period: int, d_period: int
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index), pd.Series(np.nan, index=self.df.index)

        rsi = self.calculate_rsi(period=period)
        if rsi.isnull().all():
            return pd.Series(np.nan, index=self.df.index), pd.Series(np.nan, index=self.df.index)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        denominator = highest_rsi - lowest_rsi
        # Replace 0 with NaN for division, then fillna(0) for the result later
        stoch_rsi_k_raw = ((rsi - lowest_rsi) / denominator.replace(0, np.nan)) * 100
        stoch_rsi_k_raw = self._safe_series_op(stoch_rsi_k_raw, "StochRSI_K_raw").fillna(0).clip(0, 100)

        # Smoothing with rolling mean, ensuring min_periods
        stoch_rsi_k = stoch_rsi_k_raw.rolling(window=k_period, min_periods=k_period).mean().fillna(0)
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean().fillna(0)

        return self._safe_series_op(stoch_rsi_k, "StochRSI_K"), self._safe_series_op(stoch_rsi_d, "StochRSI_D")

    def calculate_adx(
        self, period: int
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(self.df) < period * 2:
            return pd.Series(np.nan, index=self.df.index), pd.Series(np.nan, index=self.df.index), pd.Series(np.nan, index=self.df.index)

        tr = self.df["TR"] # Should have been calculated by _calculate_all_indicators

        plus_dm = self.df["high"].diff()
        minus_dm = -self.df["low"].diff()

        plus_dm_final = pd.Series(0.0, index=self.df.index)
        minus_dm_final = pd.Series(0.0, index=self.df.index)

        for i in range(1, len(self.df)):
            if plus_dm.iloc[i] > minus_dm.iloc[i] and plus_dm.iloc[i] > 0:
                plus_dm_final.iloc[i] = plus_dm.iloc[i]
            if minus_dm.iloc[i] > plus_dm.iloc[i] and minus_dm.iloc[i] > 0:
                minus_dm_final.iloc[i] = minus_dm.iloc[i]

        # Use ewm for smoothing with min_periods
        atr = self._safe_series_op(self.df["ATR"], "ATR_for_ADX") # ATR should be pre-calculated
        plus_di = (plus_dm_final.ewm(span=period, adjust=False, min_periods=period).mean() / atr.replace(0,np.nan)) * 100
        minus_di = (minus_dm_final.ewm(span=period, adjust=False, min_periods=period).mean() / atr.replace(0,np.nan)) * 100

        di_diff = (plus_di - minus_di).abs()
        di_sum = plus_di + minus_di
        dx = (di_diff / di_sum.replace(0, np.nan)).fillna(0) * 100
        adx = dx.ewm(span=period, adjust=False, min_periods=period).mean()

        return self._safe_series_op(adx, "ADX"), self._safe_series_op(plus_di, "PlusDI"), self._safe_series_op(minus_di, "MinusDI")

    def calculate_bollinger_bands(
        self, period: int, std_dev: float
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(self.df) < period:
            return (
                pd.Series(np.nan, index=self.df.index),
                pd.Series(np.nan, index=self.df.index),
                pd.Series(np.nan, index=self.df.index),
            )
        bbands = ta.bbands(self.df["close"], length=period, std=std_dev)
        upper_band = self._safe_series_op(bbands[f'BBU_{period}_{std_dev}'], "BB_Upper")
        middle_band = self._safe_series_op(bbands[f'BBM_{period}_{std_dev}'], "BB_Middle")
        lower_band = self._safe_series_op(bbands[f'BBL_{period}_{std_dev}'], "BB_Lower")
        return upper_band, middle_band, lower_band

    def calculate_vwap(self, daily_reset: bool = False) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if self.df.empty:
            return pd.Series(np.nan, index=self.df.index)

        # Ensure volume is numeric and not zero
        valid_volume = self.df["volume"].replace(0, np.nan)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3

        if daily_reset:
            # Group by date and calculate cumsum within each day
            vwap_series = []
            for date, group in self.df.groupby(self.df.index.date):
                group_tp_vol = (typical_price.loc[group.index] * valid_volume.loc[group.index]).cumsum()
                group_vol = valid_volume.loc[group.index].cumsum()
                vwap_series.append(group_tp_vol / group_vol.replace(0,np.nan))
            vwap = pd.concat(vwap_series).reindex(self.df.index)
        else:
            # Continuous VWAP over the entire DataFrame
            cumulative_tp_vol = (typical_price * valid_volume).cumsum()
            cumulative_vol = valid_volume.cumsum()
            vwap = (cumulative_tp_vol / cumulative_vol.replace(0,np.nan)).reindex(self.df.index)

        return self._safe_series_op(vwap, "VWAP").ffill() # Forward fill NaNs if volume is zero, as VWAP typically holds

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)
        cci = ta.cci(self.df["high"], self.df["low"], self.df["close"], length=period)
        return self._safe_series_op(cci, "CCI")

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)
        wr = ta.willr(self.df["high"], self.df["low"], self.df["close"], length=period)
        return self._safe_series_op(wr, "WR").fillna(-50).clip(-100, 0) # Fill NaNs, clip to [-100, 0]

    def calculate_ichimoku_cloud(
        self,
        tenkan_period: int,
        kijun_period: int,
        senkou_span_b_period: int,
        chikou_span_offset: int,
    ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components."""
        required_len = max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset
        if len(self.df) < required_len:
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series, nan_series, nan_series, nan_series

        tenkan_sen = (
            self.df["high"].rolling(window=tenkan_period, min_periods=tenkan_period).max()
            + self.df["low"].rolling(window=tenkan_period, min_periods=tenkan_period).min()
        ) / 2

        kijun_sen = (
            self.df["high"].rolling(window=kijun_period, min_periods=kijun_period).max()
            + self.df["low"].rolling(window=kijun_period, min_periods=kijun_period).min()
        ) / 2

        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period) # Future projection
        senkou_span_b = (
            (
                self.df["high"].rolling(window=senkou_span_b_period, min_periods=senkou_span_b_period).max()
                + self.df["low"].rolling(window=senkou_span_b_period, min_periods=senkou_span_b_period).min()
            )
            / 2
        ).shift(kijun_period) # Future projection

        chikou_span = self.df["close"].shift(-chikou_span_offset) # Past projection

        return (
            self._safe_series_op(tenkan_sen, "Tenkan_Sen"),
            self._safe_series_op(kijun_sen, "Kijun_Sen"),
            self._safe_series_op(senkou_span_a, "Senkou_Span_A"),
            self._safe_series_op(senkou_span_b, "Senkou_Span_B"),
            self._safe_series_op(chikou_span, "Chikou_Span"),
        )

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index)
        mfi = ta.mfi(self.df["high"], self.df["low"], self.df["close"], self.df["volume"], length=period)
        return self._safe_series_op(mfi, "MFI").fillna(50).clip(0, 100) # Fill NaNs with 50 (neutral), clip to [0, 100]

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < MIN_DATA_POINTS_OBV:
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series

        obv = ta.obv(self.df["close"], self.df["volume"])
        obv_ema = ta.ema(obv, length=ema_period)

        return self._safe_series_op(obv, "OBV"), self._safe_series_op(obv_ema, "OBV_EMA")

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)

        cmf = ta.cmf(self.df["high"], self.df["low"], self.df["close"], self.df["volume"], length=period)
        return self._safe_series_op(cmf, "CMF").fillna(0).clip(-1, 1) # Fill NaNs with 0, clip to [-1, 1]

    def calculate_psar(
        self, acceleration: float, max_acceleration: float
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(self.df) < MIN_DATA_POINTS_PSAR_INITIAL:
            nan_series = pd.Series(np.nan, index=self.df.index)
            return nan_series, nan_series

        # Use pandas_ta for PSAR calculation
        psar_result = ta.psar(self.df["high"], self.df["low"], self.df["close"], af0=acceleration, af=acceleration, max_af=max_acceleration)
        if not isinstance(psar_result, pd.DataFrame):
            self.logger.error(f"{NEON_RED}pandas_ta.psar did not return a DataFrame. Type: {type(psar_result)}{RESET}")
            return pd.Series(np.nan, index=self.df.index), pd.Series(np.nan, index=self.df.index)

        psar_val_col = f'PSARr_{acceleration}_{max_acceleration}' # Reversal PSAR value
        psar_long_col = f'PSARl_{acceleration}_{max_acceleration}'
        psar_short_col = f'PSARs_{acceleration}_{max_acceleration}'

        if not all(col in psar_result.columns for col in [psar_val_col, psar_long_col, psar_short_col]):
            self.logger.error(f"{NEON_RED}Missing expected PSAR columns in result: {psar_result.columns.tolist()}. Expected: {psar_val_col}, {psar_long_col}, {psar_short_col}{RESET}")
            return pd.Series(np.nan, index=self.df.index), pd.Series(np.nan, index=self.df.index)

        psar_val = self._safe_series_op(psar_result[psar_val_col], "PSAR_Val")
        psar_long = psar_result[psar_long_col]
        psar_short = psar_result[psar_short_col]

        # Determine direction based on price relative to PSAR lines
        direction = pd.Series(0, index=self.df.index, dtype=int)
        # Shift PSAR by one to avoid look-ahead bias if current price is used against future PSAR
        direction[psar_val.shift(-1) < self.df["close"]] = 1
        direction[psar_val.shift(-1) > self.df["close"]] = -1
        direction.mask(direction == 0, direction.shift(1), inplace=True) # Carry forward direction if no crossover
        direction.fillna(0, inplace=True) # Fill initial NaNs

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

        decimal_high = Decimal(str(recent_high))
        decimal_low = Decimal(str(recent_low))
        decimal_diff = Decimal(str(diff))

        self.fib_levels = {
            "0.0%": decimal_high,
            "23.6%": (decimal_high - Decimal("0.236") * decimal_diff).quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "38.2%": (decimal_high - Decimal("0.382") * decimal_diff).quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "50.0%": (decimal_high - Decimal("0.500") * decimal_diff).quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "61.8%": (decimal_high - Decimal("0.618") * decimal_diff).quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "78.6%": (decimal_high - Decimal("0.786") * decimal_diff).quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "100.0%": decimal_low,
        }
        self.logger.debug(f"[{self.symbol}] Calculated Fibonacci levels: {self.fib_levels}")

    def calculate_volatility_index(self, period: int) -> pd.Series:
        """Calculate a simple Volatility Index based on ATR normalized by price."""
        if len(self.df) < period or "ATR" not in self.df.columns or self.df["ATR"].isnull().all():
            return pd.Series(np.nan, index=self.df.index)

        # ATR is already calculated
        # Avoid division by zero for close price
        normalized_atr = self.df["ATR"] / self.df["close"].replace(0, np.nan)
        volatility_index = normalized_atr.rolling(window=period).mean()
        return self._safe_series_op(volatility_index, "Volatility_Index").fillna(0)

    def calculate_vwma(self, period: int) -> pd.Series:
        """Calculate Volume Weighted Moving Average (VWMA)."""
        if len(self.df) < period or self.df["volume"].isnull().any():
            return pd.Series(np.nan, index=self.df.index)

        # Ensure volume is numeric and not zero
        valid_volume = self.df["volume"].replace(0, np.nan)
        pv = self.df["close"] * valid_volume
        # Use min_periods for rolling sums
        vwma = pv.rolling(window=period).sum() / valid_volume.rolling(
            window=period
        ).sum().replace(0, np.nan)
        return self._safe_series_op(vwma, "VWMA").ffill() # Forward fill NaNs if volume is zero, as VWMA typically holds

    def calculate_volume_delta(self, period: int) -> pd.Series:
        """Calculate Volume Delta, indicating buying vs selling pressure."""
        if len(self.df) < MIN_DATA_POINTS_VOLATILITY:
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
            0, np.nan
        )
        return self._safe_series_op(volume_delta.fillna(0), "Volume_Delta").clip(-1, 1) # Fill NaNs with 0, clip to [-1, 1]

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_manager: 'AdvancedOrderbookManager') -> float:
        """Analyze orderbook imbalance."""
        # This method requires access to the orderbook_manager instance,
        # which should be passed during initialization or to the signal generation method.
        # For now, assuming it's accessible.
        if not orderbook_manager:
            self.logger.warning("Orderbook manager not available for imbalance check.")
            return 0.0

        bids, asks = orderbook_manager.get_depth(self.config["orderbook_limit"])

        bid_volume = sum(Decimal(str(b.quantity)) for b in bids)
        ask_volume = sum(Decimal(str(a.quantity)) for a in asks)

        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return 0.0

        imbalance = (bid_volume - ask_volume) / total_volume
        self.logger.debug(
            f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume.normalize()}, Asks: {ask_volume.normalize()})"
        )
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty:
            return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        period = self.config["mtf_analysis"]["trend_period"]

        if indicator_type == "sma":
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"MTF SMA: Not enough data for {period} period. Have {len(higher_tf_df)}."
                )
                return "UNKNOWN"
            sma = ta.sma(higher_tf_df["close"], length=period).iloc[-1]
            if not pd.isna(sma):
                if last_close > sma:
                    return "UP"
                if last_close < sma:
                    return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ema":
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"MTF EMA: Not enough data for {period} period. Have {len(higher_tf_df)}."
                )
                return "UNKNOWN"
            ema = ta.ema(higher_tf_df["close"], length=period).iloc[-1]
            if not pd.isna(ema):
                if last_close > ema:
                    return "UP"
                if last_close < ema:
                    return "DOWN"
            return "SIDEWAYS"
        elif indicator_type == "ehlers_supertrend":
            # Temporarily create an analyzer for the higher timeframe data to get ST direction
            temp_config = self.config.copy()
            temp_config["indicators"]["ehlers_supertrend"] = True # Ensure ST is enabled for temp analyzer
            temp_analyzer = TradingAnalyzer(
                higher_tf_df, temp_config, self.logger, self.symbol
            )
            st_dir = temp_analyzer._get_indicator_value("ST_Slow_Dir")
            if not pd.isna(st_dir):
                if st_dir == 1:
                    return "UP"
                if st_dir == -1:
                    return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    async def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_manager: 'AdvancedOrderbookManager',
        mtf_trends: dict[str, str],
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights
        isd = self.indicator_settings

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}"
            )
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        # Use .get() with default to handle cases where there might be less than 2 bars after NaN drops
        prev_close_series = self.df["close"].iloc[-2] if len(self.df) > 1 else np.nan
        prev_close = Decimal(str(prev_close_series)) if not pd.isna(prev_close_series) else current_close

        self.logger.debug(f"[{self.symbol}] --- Signal Scoring ---")

        # EMA Alignment
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long:
                    signal_score += weights.get("ema_alignment", 0)
                    self.logger.debug(f"  EMA Alignment: Bullish (+{weights.get('ema_alignment', 0):.2f})")
                elif ema_short < ema_long:
                    signal_score -= weights.get("ema_alignment", 0)
                    self.logger.debug(f"  EMA Alignment: Bearish (-{weights.get('ema_alignment', 0):.2f})")

        # SMA Trend Filter
        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long:
                    signal_score += weights.get("sma_trend_filter", 0)
                    self.logger.debug(f"  SMA Trend Filter: Bullish (+{weights.get('sma_trend_filter', 0):.2f})")
                elif current_close < sma_long:
                    signal_score -= weights.get("sma_trend_filter", 0)
                    self.logger.debug(f"  SMA Trend Filter: Bearish (-{weights.get('sma_trend_filter', 0):.2f})")

        # Momentum Indicators (RSI, StochRSI, CCI, WR, MFI)
        if active_indicators.get("momentum", False):
            momentum_weight = weights.get("momentum_rsi_stoch_cci_wr_mfi", 0)

            # RSI
            if active_indicators.get("rsi", False):
                rsi = self._get_indicator_value("RSI")
                if not pd.isna(rsi):
                    if rsi < isd["rsi_oversold"]:
                        signal_score += momentum_weight * 0.5
                        self.logger.debug(f"  RSI: Oversold (+{momentum_weight * 0.5:.2f})")
                    elif rsi > isd["rsi_overbought"]:
                        signal_score -= momentum_weight * 0.5
                        self.logger.debug(f"  RSI: Overbought (-{momentum_weight * 0.5:.2f})")

            # StochRSI Crossover
            if active_indicators.get("stoch_rsi", False):
                stoch_k = self._get_indicator_value("StochRSI_K")
                stoch_d = self._get_indicator_value("StochRSI_D")
                if not pd.isna(stoch_k) and not pd.isna(stoch_d) and len(self.df) > 1:
                    prev_stoch_k = self.df["StochRSI_K"].iloc[-2]
                    prev_stoch_d = self.df["StochRSI_D"].iloc[-2]
                    if (
                        stoch_k > stoch_d
                        and prev_stoch_k <= prev_stoch_d
                        and stoch_k < isd["stoch_rsi_oversold"]
                    ):
                        signal_score += momentum_weight * 0.6
                        self.logger.debug(f"  StochRSI: Bullish crossover from oversold (+{momentum_weight * 0.6:.2f})")
                    elif (
                        stoch_k < stoch_d
                        and prev_stoch_k >= prev_stoch_d
                        and stoch_k > isd["stoch_rsi_overbought"]
                    ):
                        signal_score -= momentum_weight * 0.6
                        self.logger.debug(f"  StochRSI: Bearish crossover from overbought (-{momentum_weight * 0.6:.2f})")
                    elif stoch_k > stoch_d and stoch_k < 50: # General bullish momentum
                        signal_score += momentum_weight * 0.2
                        self.logger.debug(f"  StochRSI: General bullish momentum (+{momentum_weight * 0.2:.2f})")
                    elif stoch_k < stoch_d and stoch_k > 50: # General bearish momentum
                        signal_score -= momentum_weight * 0.2
                        self.logger.debug(f"  StochRSI: General bearish momentum (-{momentum_weight * 0.2:.2f})")

            # CCI
            if active_indicators.get("cci", False):
                cci = self._get_indicator_value("CCI")
                if not pd.isna(cci):
                    if cci < isd["cci_oversold"]:
                        signal_score += momentum_weight * 0.4
                        self.logger.debug(f"  CCI: Oversold (+{momentum_weight * 0.4:.2f})")
                    elif cci > isd["cci_overbought"]:
                        signal_score -= momentum_weight * 0.4
                        self.logger.debug(f"  CCI: Overbought (-{momentum_weight * 0.4:.2f})")

            # Williams %R
            if active_indicators.get("wr", False):
                wr = self._get_indicator_value("WR")
                if not pd.isna(wr):
                    if wr < isd["williams_r_oversold"]:
                        signal_score += momentum_weight * 0.4
                        self.logger.debug(f"  WR: Oversold (+{momentum_weight * 0.4:.2f})")
                    elif wr > isd["williams_r_overbought"]:
                        signal_score -= momentum_weight * 0.4
                        self.logger.debug(f"  WR: Overbought (-{momentum_weight * 0.4:.2f})")

            # MFI
            if active_indicators.get("mfi", False):
                mfi = self._get_indicator_value("MFI")
                if not pd.isna(mfi):
                    if mfi < isd["mfi_oversold"]:
                        signal_score += momentum_weight * 0.4
                        self.logger.debug(f"  MFI: Oversold (+{momentum_weight * 0.4:.2f})")
                    elif mfi > isd["mfi_overbought"]:
                        signal_score -= momentum_weight * 0.4
                        self.logger.debug(f"  MFI: Overbought (-{momentum_weight * 0.4:.2f})")

        # Bollinger Bands
        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower:
                    signal_score += weights.get("bollinger_bands", 0) * 0.5
                    self.logger.debug(f"  BB: Price below lower band (+{weights.get('bollinger_bands', 0) * 0.5:.2f})")
                elif current_close > bb_upper:
                    signal_score -= weights.get("bollinger_bands", 0) * 0.5
                    self.logger.debug(f"  BB: Price above upper band (-{weights.get('bollinger_bands', 0) * 0.5:.2f})")

        # VWAP
        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap:
                    signal_score += weights.get("vwap", 0) * 0.2
                    self.logger.debug(f"  VWAP: Price above VWAP (+{weights.get('vwap', 0) * 0.2:.2f})")
                elif current_close < vwap:
                    signal_score -= weights.get("vwap", 0) * 0.2
                    self.logger.debug(f"  VWAP: Price below VWAP (-{weights.get('vwap', 0) * 0.2:.2f})")

                if len(self.df) > 1:
                    prev_vwap_series = self.df["VWAP"].iloc[-2] if "VWAP" in self.df.columns else np.nan
                    prev_vwap = Decimal(str(prev_vwap_series)) if not pd.isna(prev_vwap_series) else vwap
                    if (current_close > vwap and prev_close <= prev_vwap):
                        signal_score += weights.get("vwap", 0) * 0.3
                        self.logger.debug(f"  VWAP: Bullish crossover detected (+{weights.get('vwap', 0) * 0.3:.2f})")
                    elif (current_close < vwap and prev_close >= prev_vwap):
                        signal_score -= weights.get("vwap", 0) * 0.3
                        self.logger.debug(f"  VWAP: Bearish crossover detected (-{weights.get('vwap', 0) * 0.3:.2f})")

        # PSAR
        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                if psar_dir == 1: # Bullish direction
                    signal_score += weights.get("psar", 0) * 0.5
                    self.logger.debug(f"  PSAR: Bullish direction (+{weights.get('psar', 0) * 0.5:.2f})")
                elif psar_dir == -1: # Bearish direction
                    signal_score -= weights.get("psar", 0) * 0.5
                    self.logger.debug(f"  PSAR: Bearish direction (-{weights.get('psar', 0) * 0.5:.2f})")

                if len(self.df) > 1:
                    prev_psar_val_series = self.df["PSAR_Val"].iloc[-2] if "PSAR_Val" in self.df.columns else np.nan
                    prev_psar_val = Decimal(str(prev_psar_val_series)) if not pd.isna(prev_psar_val_series) else psar_val
                    if (current_close > psar_val and prev_close <= prev_psar_val):
                        signal_score += weights.get("psar", 0) * 0.4
                        self.logger.debug("  PSAR: Bullish reversal detected (+{weights.get('psar', 0) * 0.4:.2f})")
                    elif (current_close < psar_val and prev_close >= prev_psar_val):
                        signal_score -= weights.get("psar", 0) * 0.4
                        self.logger.debug("  PSAR: Bearish reversal detected (-{weights.get('psar', 0) * 0.4:.2f})")

        # Orderbook Imbalance
        if active_indicators.get("orderbook_imbalance", False) and orderbook_manager:
            imbalance = self._check_orderbook(current_price, orderbook_manager)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)
            self.logger.debug(f"  Orderbook Imbalance: {imbalance:.2f} (Contribution: {imbalance * weights.get('orderbook_imbalance', 0):.2f})")


        # Fibonacci Levels (confluence with price action)
        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                # Check if price is within a very small proximity of a Fibonacci level
                if (level_name not in ["0.0%", "100.0%"] and
                    (level_price * Decimal("0.999") <= current_price <= level_price * Decimal("1.001"))):
                        self.logger.debug(
                            f"  Price near Fibonacci level {level_name}: {level_price.normalize()}"
                        )
                        if len(self.df) > 1:
                            if (current_close > prev_close and current_close > level_price):
                                signal_score += weights.get("fibonacci_levels", 0) * 0.1
                                self.logger.debug(f"  Fibonacci: Bullish breakout/bounce (+{weights.get('fibonacci_levels', 0) * 0.1:.2f})")
                            elif (current_close < prev_close and current_close < level_price):
                                signal_score -= weights.get("fibonacci_levels", 0) * 0.1
                                self.logger.debug(f"  Fibonacci: Bearish breakout/bounce (-{weights.get('fibonacci_levels', 0) * 0.1:.2f})")

        # --- Ehlers SuperTrend Alignment Scoring ---
        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
            prev_st_fast_dir_series = (
                self.df["st_fast_dir"].iloc[-2]
                if "st_fast_dir" in self.df.columns and len(self.df) > 1
                else np.nan
            )
            prev_st_fast_dir = float(prev_st_fast_dir_series) if not pd.isna(prev_st_fast_dir_series) else np.nan
            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if (
                not pd.isna(st_fast_dir)
                and not pd.isna(st_slow_dir)
                and not pd.isna(prev_st_fast_dir)
            ):
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
                    signal_score += weight
                    self.logger.debug(
                        "Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend) (+{weight:.2f})."
                    )
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
                    signal_score -= weight
                    self.logger.debug(
                        "Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend) (-{weight:.2f})."
                    )
                elif st_slow_dir == 1 and st_fast_dir == 1:
                    signal_score += weight * 0.3
                    self.logger.debug(f"Ehlers SuperTrend: Bullish alignment (+{weight * 0.3:.2f}).")
                elif st_slow_dir == -1 and st_fast_dir == -1:
                    signal_score -= weight * 0.3
                    self.logger.debug(f"Ehlers SuperTrend: Bearish alignment (-{weight * 0.3:.2f}).")

        # --- MACD Alignment Scoring ---
        if active_indicators.get("macd", False):
            macd_line = self._get_indicator_value("MACD_Line")
            signal_line = self._get_indicator_value("MACD_Signal")
            histogram = self._get_indicator_value("MACD_Hist")
            weight = weights.get("macd_alignment", 0.0)

            if (
                not pd.isna(macd_line)
                and not pd.isna(signal_line)
                and not pd.isna(histogram)
                and len(self.df) > 1
            ):
                prev_macd_line = self.df["MACD_Line"].iloc[-2] if "MACD_Line" in self.df.columns else np.nan
                prev_signal_line = self.df["MACD_Signal"].iloc[-2] if "MACD_Signal" in self.df.columns else np.nan

                if (
                    macd_line > signal_line
                    and (pd.isna(prev_macd_line) or pd.isna(prev_signal_line) or prev_macd_line <= prev_signal_line)
                ):
                    signal_score += weight
                    self.logger.debug(
                        f"MACD: BUY signal (MACD line crossed above Signal line) (+{weight:.2f})."
                    )
                elif (
                    macd_line < signal_line
                    and (pd.isna(prev_macd_line) or pd.isna(prev_signal_line) or prev_macd_line >= prev_signal_line)
                ):
                    signal_score -= weight
                    self.logger.debug(
                        f"MACD: SELL signal (MACD line crossed below Signal line) (-{weight:.2f})."
                    )
                elif histogram > 0 and (len(self.df) > 2 and self.df["MACD_Hist"].iloc[-2] < 0):
                    signal_score += weight * 0.2
                    self.logger.debug(f"MACD: Histogram turned positive (+{weight * 0.2:.2f}).")
                elif histogram < 0 and (len(self.df) > 2 and self.df["MACD_Hist"].iloc[-2] > 0):
                    signal_score -= weight * 0.2
                    self.logger.debug(f"MACD: Histogram turned negative (-{weight * 0.2:.2f}).")

        # --- ADX Alignment Scoring ---
        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")
            weight = weights.get("adx_strength", 0.0)

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
                    self.logger.debug(f"ADX: Weak trend (ADX < {ADX_WEAK_TREND_THRESHOLD}). Neutral signal.")

        # --- Ichimoku Cloud Alignment Scoring ---
        if active_indicators.get("ichimoku_cloud", False):
            tenkan_sen = self._get_indicator_value("Tenkan_Sen")
            kijun_sen = self._get_indicator_value("Kijun_Sen")
            senkou_span_a = self._get_indicator_value("Senkou_Span_A")
            senkou_span_b = self._get_indicator_value("Senkou_Span_B")
            chikou_span = self._get_indicator_value("Chikou_Span")
            weight = weights.get("ichimoku_confluence", 0.0)

            if (
                not pd.isna(tenkan_sen)
                and not pd.isna(kijun_sen)
                and not pd.isna(senkou_span_a)
                and not pd.isna(senkou_span_b)
                and not pd.isna(chikou_span)
                and len(self.df) > 1
            ):
                prev_tenkan = self.df["Tenkan_Sen"].iloc[-2] if "Tenkan_Sen" in self.df.columns else np.nan
                prev_kijun = self.df["Kijun_Sen"].iloc[-2] if "Kijun_Sen" in self.df.columns else np.nan
                prev_senkou_a = self.df["Senkou_Span_A"].iloc[-2] if "Senkou_Span_A" in self.df.columns else np.nan
                prev_senkou_b = self.df["Senkou_Span_B"].iloc[-2] if "Senkou_Span_B" in self.df.columns else np.nan
                prev_chikou = self.df["Chikou_Span"].iloc[-2] if "Chikou_Span" in self.df.columns else np.nan

                if (
                    tenkan_sen > kijun_sen
                    and (pd.isna(prev_tenkan) or pd.isna(prev_kijun) or prev_tenkan <= prev_kijun)
                ):
                    signal_score += weight * 0.5
                    self.logger.debug(
                        f"Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish) (+{weight * 0.5:.2f})."
                    )
                elif (
                    tenkan_sen < kijun_sen
                    and (pd.isna(prev_tenkan) or pd.isna(prev_kijun) or prev_tenkan >= prev_kijun)
                ):
                    signal_score -= weight * 0.5
                    self.logger.debug(
                        f"Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish) (-{weight * 0.5:.2f})."
                    )

                # Price breaking above/below Kumo (Cloud)
                kumo_top = max(senkou_span_a, senkou_span_b)
                kumo_bottom = min(senkou_span_a, senkou_span_b)
                prev_kumo_top = max(prev_senkou_a, prev_senkou_b)
                prev_kumo_bottom = min(prev_senkou_a, prev_senkou_b)

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
                if (
                    chikou_span > current_close
                    and (pd.isna(prev_chikou) or prev_chikou <= prev_close)
                ):
                    signal_score += weight * 0.3
                    self.logger.debug(
                        f"Ichimoku: Chikou Span crossed above price (bullish confirmation) (+{weight * 0.3:.2f})."
                    )
                elif (
                    chikou_span < current_close
                    and (pd.isna(prev_chikou) or prev_chikou >= prev_close)
                ):
                    signal_score -= weight * 0.3
                    self.logger.debug(
                        f"Ichimoku: Chikou Span crossed below price (bearish confirmation) (-{weight * 0.3:.2f})."
                    )

        # --- OBV Alignment Scoring ---
        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")
            weight = weights.get("obv_momentum", 0.0)

            if not pd.isna(obv_val) and not pd.isna(obv_ema) and len(self.df) > 1:
                prev_obv_val = self.df["OBV"].iloc[-2] if "OBV" in self.df.columns else np.nan
                prev_obv_ema = self.df["OBV_EMA"].iloc[-2] if "OBV_EMA" in self.df.columns else np.nan

                if (
                    obv_val > obv_ema
                    and (pd.isna(prev_obv_val) or pd.isna(prev_obv_ema) or prev_obv_val <= prev_obv_ema)
                ):
                    signal_score += weight * 0.5
                    self.logger.debug(f"  OBV: Bullish crossover detected (+{weight * 0.5:.2f}).")
                elif (
                    obv_val < obv_ema
                    and (pd.isna(prev_obv_val) or pd.isna(prev_obv_ema) or prev_obv_val >= prev_obv_ema)
                ):
                    signal_score -= weight * 0.5
                    self.logger.debug(f"  OBV: Bearish crossover detected (-{weight * 0.5:.2f}).")

                if len(self.df) > 2:
                    if (
                        obv_val > self.df["OBV"].iloc[-2]
                        and obv_val > self.df["OBV"].iloc[-3]
                    ):
                        signal_score += weight * 0.2
                        self.logger.debug(f"  OBV: Increasing momentum (+{weight * 0.2:.2f}).")
                    elif (
                        obv_val < self.df["OBV"].iloc[-2]
                        and obv_val < self.df["OBV"].iloc[-3]
                    ):
                        signal_score -= weight * 0.2
                        self.logger.debug(f"  OBV: Decreasing momentum (-{weight * 0.2:.2f}).")

        # --- CMF Alignment Scoring ---
        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")
            weight = weights.get("cmf_flow", 0.0)

            if not pd.isna(cmf_val):
                if cmf_val > 0:
                    signal_score += weight * 0.5
                    self.logger.debug(f"  CMF: Positive money flow (+{weight * 0.5:.2f}).")
                elif cmf_val < 0:
                    signal_score -= weight * 0.5
                    self.logger.debug(f"  CMF: Negative money flow (-{weight * 0.5:.2f}).")

                if len(self.df) > 2:
                    if (
                        cmf_val > self.df["CMF"].iloc[-2]
                        and cmf_val > self.df["CMF"].iloc[-3]
                    ):
                        signal_score += weight * 0.3
                        self.logger.debug(f"  CMF: Increasing bullish flow (+{weight * 0.3:.2f}).")
                    elif (
                        cmf_val < self.df["CMF"].iloc[-2]
                        and cmf_val < self.df["CMF"].iloc[-3]
                    ):
                        signal_score -= weight * 0.3
                        self.logger.debug(f"  CMF: Increasing bearish flow (-{weight * 0.3:.2f}).")

        # --- Volatility Index Scoring ---
        if active_indicators.get("volatility_index", False):
            vol_idx = self._get_indicator_value("Volatility_Index")
            weight = weights.get("volatility_index_signal", 0.0)
            if not pd.isna(vol_idx) and len(self.df) > 2 and "Volatility_Index" in self.df.columns:
                prev_vol_idx = self.df["Volatility_Index"].iloc[-2]
                prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3]

                if vol_idx > prev_vol_idx > prev_prev_vol_idx:  # Increasing volatility
                    if signal_score > 0:
                        signal_score += weight * 0.2
                        self.logger.debug(f"  Volatility Index: Increasing volatility, adds confidence to BUY (+{weight * 0.2:.2f}).")
                    elif signal_score < 0:
                        signal_score -= weight * 0.2
                        self.logger.debug(f"  Volatility Index: Increasing volatility, adds confidence to SELL (-{weight * 0.2:.2f}).")
                elif vol_idx < prev_vol_idx < prev_prev_vol_idx: # Decreasing volatility
                    if abs(signal_score) > 0: # If there's an existing signal, slightly reduce its conviction
                         signal_score *= (1 - weight * 0.1) # Reduce by 10% of the weight
                         self.logger.debug(f"  Volatility Index: Decreasing volatility, reduces signal conviction (x{(1 - weight * 0.1):.2f}).")

        # --- VWMA Cross Scoring ---
        if active_indicators.get("vwma", False):
            vwma = self._get_indicator_value("VWMA")
            weight = weights.get("vwma_cross", 0.0)
            if not pd.isna(vwma) and len(self.df) > 1:
                prev_vwma_series = self.df["VWMA"].iloc[-2] if "VWMA" in self.df.columns else np.nan
                prev_vwma = Decimal(str(prev_vwma_series)) if not pd.isna(prev_vwma_series) else vwma
                if current_close > vwma and prev_close <= prev_vwma:
                    signal_score += weight
                    self.logger.debug(f"  VWMA: Bullish crossover (price above VWMA) (+{weight:.2f}).")
                elif current_close < vwma and prev_close >= prev_vwma:
                    signal_score -= weight
                    self.logger.debug(f"  VWMA: Bearish crossover (price below VWMA) (-{weight:.2f}).")

        # --- Volume Delta Scoring ---
        if active_indicators.get("volume_delta", False):
            volume_delta = self._get_indicator_value("Volume_Delta")
            volume_delta_threshold = isd["volume_delta_threshold"]
            weight = weights.get("volume_delta_signal", 0.0)

            if not pd.isna(volume_delta):
                if volume_delta > volume_delta_threshold:  # Strong buying pressure
                    signal_score += weight
                    self.logger.debug(f"  Volume Delta: Strong buying pressure detected (+{weight:.2f}).")
                elif volume_delta < -volume_delta_threshold:  # Strong selling pressure
                    signal_score -= weight
                    self.logger.debug(f"  Volume Delta: Strong selling pressure detected (-{weight:.2f}).")
                elif volume_delta > 0:
                    signal_score += weight * 0.3
                    self.logger.debug(f"  Volume Delta: Moderate buying pressure detected (+{weight * 0.3:.2f}).")
                elif volume_delta < 0:
                    signal_score -= weight * 0.3
                    self.logger.debug(f"  Volume Delta: Moderate selling pressure detected (-{weight * 0.3:.2f}).")


        # --- Multi-Timeframe Trend Confluence Scoring ---
        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = 0
            mtf_sell_score = 0
            for _tf_indicator, trend in mtf_trends.items():
                if trend == "UP":
                    mtf_buy_score += 1
                elif trend == "DOWN":
                    mtf_sell_score += 1

            mtf_weight = weights.get("mtf_trend_confluence", 0.0)
            if mtf_trends:
                # Calculate a normalized score based on the balance of buy/sell trends
                normalized_mtf_score = (mtf_buy_score - mtf_sell_score) / len(
                    mtf_trends
                )
                signal_score += mtf_weight * normalized_mtf_score
                self.logger.debug(
                    f"MTF Confluence: Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {mtf_sell_score}). Total MTF contribution: {mtf_weight * normalized_mtf_score:.2f}"
                )

        # --- Gemini AI Analysis Scoring ---
        if self.config["gemini_ai_analysis"]["enabled"] and self.gemini_client:
            gemini_prompt = self._summarize_market_for_gemini(current_close)
            # This part assumes GeminiClient has an async analyze_market_data method
            # gemini_analysis = await self.gemini_client.analyze_market_data(gemini_prompt)
            gemini_analysis = None # Placeholder if GeminiClient is not implemented

            if gemini_analysis:
                self.logger.info(f"{NEON_PURPLE}Gemini AI Analysis: {json.dumps(gemini_analysis, indent=2)}{RESET}")
                gemini_entry = gemini_analysis.get("entry")
                gemini_confidence = gemini_analysis.get("confidence_level", 0)
                gemini_weight = self.config["gemini_ai_analysis"]["weight"]

                if gemini_confidence >= 50: # Only consider if confidence is reasonable
                    if gemini_entry == "BUY":
                        signal_score += gemini_weight
                        self.logger.info(f"{NEON_GREEN}Gemini AI recommends BUY (Confidence: {gemini_confidence}). Adding {gemini_weight} to signal score.{RESET}")
                    elif gemini_entry == "SELL":
                        signal_score -= gemini_weight
                        self.logger.info(f"{NEON_RED}Gemini AI recommends SELL (Confidence: {gemini_confidence}). Subtracting {gemini_weight} from signal score.{RESET}")
                    else:
                        self.logger.info(f"{NEON_YELLOW}Gemini AI recommends HOLD (Confidence: {gemini_confidence}). No change to signal score.{RESET}")
                else:
                    self.logger.info(f"{NEON_YELLOW}Gemini AI confidence ({gemini_confidence}) too low. Skipping influence on signal score.{RESET}")
            else:
                self.logger.warning(f"{NEON_YELLOW}Gemini AI analysis failed or returned no data. Skipping influence on signal score.{RESET}")

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
        price_precision_str = "0." + "0" * (self.price_precision - 1) + "1"


        if signal == "BUY":
            stop_loss = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit = current_price + (atr_value * take_profit_atr_multiple)
        elif signal == "SELL":
            stop_loss = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit = current_price - (atr_value * take_profit_atr_multiple)
        else:
            return Decimal("0"), Decimal("0")  # Should not happen for valid signals

        return take_profit.quantize(
            Decimal(price_precision_str), rounding=ROUND_DOWN
        ), stop_loss.quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)


def display_indicator_values_and_price(
    config: dict[str, Any],
    logger: logging.Logger,
    current_price: Decimal,
    analyzer: 'TradingAnalyzer',
    orderbook_manager: 'AdvancedOrderbookManager',
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
            logger.info(f"  {color}{indicator_name}: {value:.8f}{RESET}") # Display floats with more reasonable precision
        else:
            logger.info(f"  {color}{indicator_name}: {value}{RESET}")

    if analyzer.fib_levels:
        logger.info(f"{NEON_CYAN}--- Fibonacci Levels ---{RESET}")
        logger.info("") # Added newline for spacing
        for level_name, level_price in analyzer.fib_levels.items():
            logger.info(f"  {NEON_YELLOW}{level_name}: {level_price.normalize()}{RESET}")

    if mtf_trends:
        logger.info(f"{NEON_CYAN}--- Multi-Timeframe Trends ---{RESET}")
        logger.info("") # Added newline for spacing
        for tf_indicator, trend in mtf_trends.items():
            logger.info(f"  {NEON_YELLOW}{tf_indicator}: {trend}{RESET}")

    if config["indicators"].get("orderbook_imbalance", False):
        imbalance = analyzer._check_orderbook(current_price, orderbook_manager)
        logger.info(f"{NEON_CYAN}Orderbook Imbalance: {imbalance:.4f}{RESET}")

    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")


# --- Main Execution Logic ---
def main() -> None:
    """Orchestrate the bot's operation."""
    logger = setup_logger("whalebot_main", level=logging.INFO) # Use a specific logger for main
    config = load_config(CONFIG_FILE, logger)
    alert_system = AlertSystem(logger)

    # Validate interval format at startup
    valid_bybit_intervals = [
        "1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"
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
        logger.critical(f"{NEON_RED}BYBIT_API_KEY or BYBIT_API_SECRET environment variables are not set. Please set them before running the bot. Exiting.{RESET}")
        sys.exit(1)

    logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Initialized ---{RESET}")
    logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
    logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")
    if config["trade_management"]["enabled"]:
        logger.info(f"Leverage: {config['trade_management']['leverage']}x, Order Mode: {config['trade_management']['order_mode']}")
    else:
        logger.info(f"Using simulated balance for position sizing: {config['trade_management']['account_balance']:.2f} USDT")

    position_manager = PositionManager(config, logger, config["symbol"])
    performance_tracker = PerformanceTracker(logger, config_file="bot_logs/trading-bot/trades.json") # Save trades to a file
    
    # Initialize other components that might be needed by the main loop or analyzer
    # Note: GeminiClient initialization is conditional and requires API key setup.
    # For now, it's a placeholder.
    gemini_client = None
    if config["gemini_ai_analysis"]["enabled"]:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if gemini_api_key:
            # Assuming GeminiClient is available and correctly implemented elsewhere
            # from gemini_client import GeminiClient # Uncomment if GeminiClient is available
            # gemini_client = GeminiClient(...)
            logger.warning(f"{NEON_YELLOW}Gemini AI analysis enabled, but GeminiClient is not implemented/imported. Placeholder used.{RESET}")
            gemini_client = lambda: None # Placeholder
        else:
            logger.error(f"{NEON_RED}GEMINI_API_KEY not set, disabling Gemini AI analysis.{RESET}")
            config["gemini_ai_analysis"]["enabled"] = False

    # Main loop execution needs to be asynchronous
    async def run_bot_loop():
        while True:
            try:
                logger.info(f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}")
                current_price = fetch_current_price(config["symbol"], logger)
                if current_price is None:
                    alert_system.send_alert(
                        f"[{config['symbol']}] Failed to fetch current price. Skipping loop.", "WARNING"
                    )
                    await asyncio.sleep(config["loop_delay"])
                    continue

                df = fetch_klines(config["symbol"], config["interval"], 200, logger) # Increased limit for more robust indicator calc
                if df is None or df.empty:
                    alert_system.send_alert(
                        f"[{config['symbol']}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
                        "WARNING",
                    )
                    await asyncio.sleep(config["loop_delay"])
                    continue

                orderbook_data = None
                if config["indicators"].get("orderbook_imbalance", False):
                    orderbook_data = fetch_orderbook(
                        config["symbol"], config["orderbook_limit"], logger
                    )

                mtf_trends: dict[str, str] = {}
                if config["mtf_analysis"]["enabled"]:
                    for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                        logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
                        htf_df = fetch_klines(config["symbol"], htf_interval, 200, logger) # Increased limit
                        if htf_df is not None and not htf_df.empty:
                            for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                                # A new TradingAnalyzer is created for each HTF to avoid cross-contamination
                                temp_htf_analyzer = TradingAnalyzer(
                                    htf_df, config, logger, config["symbol"]
                                )
                                trend = temp_htf_analyzer._get_mtf_trend(
                                    temp_htf_df, trend_ind
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

                analyzer = TradingAnalyzer(df, config, logger, config["symbol"])

                if analyzer.df.empty:
                    alert_system.send_alert(
                        f"[{config['symbol']}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                        "WARNING",
                    )
                    await asyncio.sleep(config["loop_delay"])
                    continue

                trading_signal, signal_score = await analyzer.generate_trading_signal(
                    current_price, None, mtf_trends # Pass None for orderbook_manager if not used here
                )
                atr_value = Decimal(
                    str(analyzer._get_indicator_value("ATR", Decimal("0.01")))
                ) # Default to a small positive value if ATR is missing

                # Manage existing positions before potentially opening new ones
                position_manager.manage_positions(current_price, atr_value, performance_tracker)

                if (
                    trading_signal == "BUY"
                    and signal_score >= config["signal_score_threshold"]
                ):
                    logger.info(
                        f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}. Attempting to open position.{RESET}"
                    )
                    position_manager.open_position("BUY", current_price, atr_value)
                elif (
                    trading_signal == "SELL"
                    and signal_score <= -config["signal_score_threshold"]
                ):
                    logger.info(
                        f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}. Attempting to open position.{RESET}"
                    )
                    position_manager.open_position("SELL", current_price, atr_value)
                else:
                    logger.info(
                        f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}"
                    )

                open_positions = position_manager.get_open_positions()
                if open_positions:
                    logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}")
                    for pos in open_positions:
                        logger.info(
                            f"  - {pos['side']} {pos['qty'].normalize()} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}, Trailing SL: {pos.get('current_trailing_sl', 'N/A')}){RESET}"
                        )
                else:
                    logger.info(f"{NEON_CYAN}No open positions.{RESET}")

                perf_summary = performance_tracker.get_summary()
                logger.info(
                    f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}"
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
                    f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}", "ERROR"
                )
                logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
                await asyncio.sleep(config["loop_delay"] * 2) # Longer delay on error

    # --- Main execution ---
    async def main():
        """Orchestrate the bot's operation."""
        logger = setup_logger("whalebot_main", level=logging.INFO)
        config = load_config(CONFIG_FILE, logger)
        alert_system = AlertSystem(logger)

        # Validate interval format at startup
        valid_bybit_intervals = [
            "1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"
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
            logger.critical(f"{NEON_RED}BYBIT_API_KEY or BYBIT_API_SECRET environment variables are not set. Please set them before running the bot. Exiting.{RESET}")
            sys.exit(1)

        logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Initialized ---{RESET}")
        logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
        logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")
        if config["trade_management"]["enabled"]:
            logger.info(f"Leverage: {config['trade_management']['leverage']}x, Order Mode: {config['trade_management']['order_mode']}")
        else:
            logger.info(f"Using simulated balance for position sizing: {config['trade_management']['account_balance']:.2f} USDT")

        position_manager = PositionManager(config, logger, config["symbol"])
        performance_tracker = PerformanceTracker(logger, config_file="bot_logs/trading-bot/trades.json") # Save trades to a file

        # Initialize other components needed by the main loop or analyzer
        # Note: GeminiClient initialization is conditional and requires API key setup.
        # For now, it's a placeholder.
        gemini_client = None
        if config["gemini_ai_analysis"]["enabled"]:
            gemini_api_key = os.getenv("GEMINI_API_KEY")
            if gemini_api_key:
                # Assuming GeminiClient is available and correctly implemented elsewhere
                # from gemini_client import GeminiClient # Uncomment if GeminiClient is available
                # gemini_client = GeminiClient(...)
                logger.warning(f"{NEON_YELLOW}Gemini AI analysis enabled, but GeminiClient is not implemented/imported. Placeholder used.{RESET}")
                gemini_client = lambda: None # Placeholder
            else:
                logger.error(f"{NEON_RED}GEMINI_API_KEY not set, disabling Gemini AI analysis.{RESET}")
                config["gemini_ai_analysis"]["enabled"] = False

        # Main loop execution needs to be asynchronous
        await run_bot_loop(config, logger, position_manager, performance_tracker, alert_system, gemini_client)

    async def run_bot_loop(config, logger, position_manager, performance_tracker, alert_system, gemini_client):
        """The main asynchronous loop for the trading bot."""
        while True:
            try:
                logger.info(f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}")
                current_price = fetch_current_price(config["symbol"], logger)
                if current_price is None:
                    alert_system.send_alert(
                        f"[{config['symbol']}] Failed to fetch current price. Skipping loop.", "WARNING"
                    )
                    await asyncio.sleep(config["loop_delay"])
                    continue

                df = fetch_klines(config["symbol"], config["interval"], 200, logger) # Increased limit for more robust indicator calc
                if df is None or df.empty:
                    alert_system.send_alert(
                        f"[{config['symbol']}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
                        "WARNING",
                    )
                    await asyncio.sleep(config["loop_delay"])
                    continue

                orderbook_data = None
                if config["indicators"].get("orderbook_imbalance", False):
                    orderbook_data = fetch_orderbook(
                        config["symbol"], config["orderbook_limit"], logger
                    )

                mtf_trends: dict[str, str] = {}
                if config["mtf_analysis"]["enabled"]:
                    for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                        logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
                        htf_df = fetch_klines(config["symbol"], htf_interval, 200, logger) # Increased limit
                        if htf_df is not None and not htf_df.empty:
                            for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                                # A new TradingAnalyzer is created for each HTF to avoid cross-contamination
                                temp_htf_analyzer = TradingAnalyzer(
                                    htf_df, config, logger, config["symbol"]
                                )
                                trend = temp_htf_analyzer._get_mtf_trend(
                                    temp_htf_df, trend_ind
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

                analyzer = TradingAnalyzer(df, config, logger, config["symbol"])

                if analyzer.df.empty:
                    alert_system.send_alert(
                        f"[{config['symbol']}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                        "WARNING",
                    )
                    await asyncio.sleep(config["loop_delay"])
                    continue

                trading_signal, signal_score = await analyzer.generate_trading_signal(
                    current_price, None, mtf_trends # Pass None for orderbook_manager if not used here
                )
                atr_value = Decimal(
                    str(analyzer._get_indicator_value("ATR", Decimal("0.01")))
                ) # Default to a small positive value if ATR is missing

                # Manage existing positions before potentially opening new ones
                position_manager.manage_positions(current_price, atr_value, performance_tracker)

                if (
                    trading_signal == "BUY"
                    and signal_score >= config["signal_score_threshold"]
                ):
                    logger.info(
                        f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}. Attempting to open position.{RESET}"
                    )
                    position_manager.open_position("BUY", current_price, atr_value)
                elif (
                    trading_signal == "SELL"
                    and signal_score <= -config["signal_score_threshold"]
                ):
                    logger.info(
                        f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}. Attempting to open position.{RESET}"
                    )
                    position_manager.open_position("SELL", current_price, atr_value)
                else:
                    logger.info(
                        f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}"
                    )

                open_positions = position_manager.get_open_positions()
                if open_positions:
                    logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}")
                    for pos in open_positions:
                        logger.info(
                            f"  - {pos['side']} {pos['qty'].normalize()} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}, Trailing SL: {pos.get('current_trailing_sl', 'N/A')}){RESET}"
                        )
                else:
                    logger.info(f"{NEON_CYAN}No open positions.{RESET}")

                perf_summary = performance_tracker.get_summary()
                logger.info(
                    f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}"
                )

                logger.info(
                    f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_loop_delay']}s ---{RESET}"
                )
                await asyncio.sleep(config["loop_delay"])

            except asyncio.CancelledError:
                logger.info(f"{NEON_BLUE}Main loop cancelled gracefully.{RESET}")
                break
            except Exception as e:
                alert_system.send_alert(
                    f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}", "ERROR"
                )
                logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
                await asyncio.sleep(config["loop_delay"] * 2) # Longer delay on error

    # --- Main execution ---
    if __name__ == "__main__":
        try:
            # Load config and setup logger early
            logger = setup_logger("whalebot_main", level=logging.INFO)
            config = load_config(CONFIG_FILE, logger)
            alert_system = AlertSystem(logger)

            # Validate intervals
            valid_bybit_intervals = [
                "1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"
            ]
            if config["interval"] not in valid_bybit_intervals:
                logger.error(f"{NEON_RED}Invalid primary interval '{config['interval']}'. Exiting.{RESET}")
                sys.exit(1)
            for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                if htf_interval not in valid_bybit_intervals:
                    logger.error(f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}'. Exiting.{RESET}")
                    sys.exit(1)

            if not API_KEY or not API_SECRET:
                logger.critical(f"{NEON_RED}BYBIT_API_KEY or BYBIT_API_SECRET not set. Exiting.{RESET}")
                sys.exit(1)

            logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Initialized ---{RESET}")
            logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
            logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")
            if config["trade_management"]["enabled"]:
                logger.info(f"Leverage: {config['trade_management']['leverage']}x, Order Mode: {config['trade_management']['order_mode']}")
            else:
                logger.info(f"Using simulated balance: {config['trade_management']['account_balance']:.2f} USDT")

            # Initialize core components
            position_manager = PositionManager(config, logger, config["symbol"])
            performance_tracker = PerformanceTracker(logger, config_file="bot_logs/trading-bot/trades.json") # Save trades to a file

            # Initialize other components needed by the main loop or analyzer
            gemini_client = None # Placeholder for GeminiClient
            if config["gemini_ai_analysis"]["enabled"]:
                gemini_api_key = os.getenv("GEMINI_API_KEY")
                if gemini_api_key:
                    # Assuming GeminiClient is available and correctly implemented elsewhere
                    # from gemini_client import GeminiClient # Uncomment if GeminiClient is available
                    # gemini_client = GeminiClient(...)
                    logger.warning(f"{NEON_YELLOW}Gemini AI analysis enabled, but GeminiClient is not implemented/imported. Placeholder used.{RESET}")
                    gemini_client = lambda: None # Placeholder
                else:
                    logger.error(f"{NEON_RED}GEMINI_API_KEY not set, disabling Gemini AI analysis.{RESET}")
                    config["gemini_ai_analysis"]["enabled"] = False

            # Start the asynchronous main loop
            asyncio.run(main_async_loop(config, logger, position_manager, performance_tracker, alert_system, gemini_client))

        except KeyboardInterrupt:
            logger.info(f"{NEON_BLUE}KeyboardInterrupt detected. Shutting down bot...{RESET}")
            # The shutdown logic is handled within main_async_loop's finally block
        except Exception as e:
            logger.critical(f"{NEON_RED}Critical error during bot startup or top-level execution: {e}{RESET}", exc_info=True)
            sys.exit(1) # Exit if critical setup fails


async def main_async_loop(config, logger, position_manager, performance_tracker, alert_system, gemini_client):
    """The main asynchronous loop for the trading bot."""
    while True:
        try:
            logger.info(f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}")
            current_price = fetch_current_price(config["symbol"], logger)
            if current_price is None:
                alert_system.send_alert(
                    f"[{config['symbol']}] Failed to fetch current price. Skipping loop.", "WARNING"
                )
                await asyncio.sleep(config["loop_delay"])
                continue

            df = fetch_klines(config["symbol"], config["interval"], 200, logger) # Increased limit for more robust indicator calc
            if df is None or df.empty:
                alert_system.send_alert(
                    f"[{config['symbol']}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
                    "WARNING",
                )
                await asyncio.sleep(config["loop_delay"])
                continue

            orderbook_data = None
            if config["indicators"].get("orderbook_imbalance", False):
                orderbook_data = fetch_orderbook(
                    config["symbol"], config["orderbook_limit"], logger
                )

            mtf_trends: dict[str, str] = {}
            if config["mtf_analysis"]["enabled"]:
                for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                    logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
                    htf_df = fetch_klines(config["symbol"], htf_interval, 200, logger) # Increased limit
                    if htf_df is not None and not htf_df.empty:
                        for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                            # A new TradingAnalyzer is created for each HTF to avoid cross-contamination
                            temp_htf_analyzer = TradingAnalyzer(
                                htf_df, config, logger, config["symbol"]
                            )
                            trend = temp_htf_analyzer._get_mtf_trend(
                                temp_htf_df, trend_ind
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

            analyzer = TradingAnalyzer(df, config, logger, config["symbol"])

            if analyzer.df.empty:
                alert_system.send_alert(
                    f"[{config['symbol']}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                    "WARNING",
                )
                await asyncio.sleep(config["loop_loop_delay"])
                continue

            trading_signal, signal_score = await analyzer.generate_trading_signal(
                current_price, None, mtf_trends # Pass None for orderbook_manager if not used here
            )
            atr_value = Decimal(
                str(analyzer._get_indicator_value("ATR", Decimal("0.01")))
            ) # Default to a small positive value if ATR is missing

            # Manage existing positions before potentially opening new ones
            position_manager.manage_positions(current_price, atr_value, performance_tracker)

            if (
                trading_signal == "BUY"
                and signal_score >= config["signal_score_threshold"]
            ):
                logger.info(
                    f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}. Attempting to open position.{RESET}"
                )
                position_manager.open_position("BUY", current_price, atr_value)
            elif (
                trading_signal == "SELL"
                and signal_score <= -config["signal_score_threshold"]
            ):
                logger.info(
                    f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}. Attempting to open position.{RESET}"
                )
                position_manager.open_position("SELL", current_price, atr_value)
            else:
                logger.info(
                    f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}"
                )

            open_positions = position_manager.get_open_positions()
            if open_positions:
                logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}")
                for pos in open_positions:
                    logger.info(
                        f"  - {pos['side']} {pos['qty'].normalize()} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}, Trailing SL: {pos.get('current_trailing_sl', 'N/A')}){RESET}"
                    )
            else:
                logger.info(f"{NEON_CYAN}No open positions.{RESET}")

            perf_summary = performance_tracker.get_summary()
            logger.info(
                f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}"
            )

            logger.info(
                f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}"
            )
            await asyncio.sleep(config["loop_delay"])

        except asyncio.CancelledError:
            logger.info(f"{NEON_BLUE}Main loop cancelled gracefully.{RESET}")
            # Perform cleanup tasks here if needed before exiting the loop
            break
        except Exception as e:
            alert_system.send_alert(
                f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}", "ERROR"
            )
            logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
            await asyncio.sleep(config["loop_delay"] * 2) # Longer delay on error

    # --- Main execution ---
    if __name__ == "__main__":
        try:
            # Load config and setup logger early
            logger = setup_logger("whalebot_main", level=logging.INFO)
            config = load_config(CONFIG_FILE, logger)
            alert_system = AlertSystem(logger)

            # Validate intervals
            valid_bybit_intervals = [
                "1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"
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
                logger.critical(f"{NEON_RED}BYBIT_API_KEY or BYBIT_API_SECRET environment variables are not set. Please set them before running the bot. Exiting.{RESET}")
                sys.exit(1)

            logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Initialized ---{RESET}")
            logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
            logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")
            if config["trade_management"]["enabled"]:
                logger.info(f"Leverage: {config['trade_management']['leverage']}x, Order Mode: {config['trade_management']['order_mode']}")
            else:
                logger.info(f"Using simulated balance for position sizing: {config['trade_management']['account_balance']:.2f} USDT")

            position_manager = PositionManager(config, logger, config["symbol"])
            performance_tracker = PerformanceTracker(logger, config_file="bot_logs/trading-bot/trades.json") # Save trades to a file

            # Initialize other components needed by the main loop or analyzer
            # Note: GeminiClient initialization is conditional and requires API key setup.
            # For now, it's a placeholder.
            gemini_client = None
            if config["gemini_ai_analysis"]["enabled"]:
                gemini_api_key = os.getenv("GEMINI_API_KEY")
                if gemini_api_key:
                    # Assuming GeminiClient is available and correctly implemented elsewhere
                    # from gemini_client import GeminiClient # Uncomment if GeminiClient is available
                    # gemini_client = GeminiClient(...)
                    logger.warning(f"{NEON_YELLOW}Gemini AI analysis enabled, but GeminiClient is not implemented/imported. Placeholder used.{RESET}")
                    gemini_client = lambda: None # Placeholder
                else:
                    logger.error(f"{NEON_RED}GEMINI_API_KEY not set, disabling Gemini AI analysis.{RESET}")
                    config["gemini_ai_analysis"]["enabled"] = False

            # Start the asynchronous main loop
            asyncio.run(main_async_loop(config, logger, position_manager, performance_tracker, alert_system, gemini_client))

        except KeyboardInterrupt:
            logger.info(f"{NEON_BLUE}KeyboardInterrupt detected. Shutting down bot...{RESET}")
            # The shutdown logic is handled within main_async_loop's finally block
        except Exception as e:
            logger.critical(f"{NEON_RED}Critical error during bot startup or top-level execution: {e}{RESET}", exc_info=True)
            sys.exit(1) # Exit if critical setup fails


async def main_async_loop(config, logger, position_manager, performance_tracker, alert_system, gemini_client):
    """The main asynchronous loop for the trading bot."""
    while True:
        try:
            logger.info(f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}")
            current_price = fetch_current_price(config["symbol"], logger)
            if current_price is None:
                alert_system.send_alert(
                    f"[{config['symbol']}] Failed to fetch current price. Skipping loop.", "WARNING"
                )
                await asyncio.sleep(config["loop_delay"])
                continue

            df = fetch_klines(config["symbol"], config["interval"], 200, logger) # Increased limit for more robust indicator calc
            if df is None or df.empty:
                alert_system.send_alert(
                    f"[{config['symbol']}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
                    "WARNING",
                )
                await asyncio.sleep(config["loop_delay"])
                continue

            orderbook_data = None
            if config["indicators"].get("orderbook_imbalance", False):
                orderbook_data = fetch_orderbook(
                    config["symbol"], config["orderbook_limit"], logger
                )

            mtf_trends: dict[str, str] = {}
            if config["mtf_analysis"]["enabled"]:
                for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                    logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
                    htf_df = fetch_klines(config["symbol"], htf_interval, 200, logger) # Increased limit
                    if htf_df is not None and not htf_df.empty:
                        for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                            # A new TradingAnalyzer is created for each HTF to avoid cross-contamination
                            temp_htf_analyzer = TradingAnalyzer(
                                htf_df, config, logger, config["symbol"]
                            )
                            trend = temp_htf_analyzer._get_mtf_trend(
                                temp_htf_df, trend_ind
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

            analyzer = TradingAnalyzer(df, config, logger, config["symbol"])

            if analyzer.df.empty:
                alert_system.send_alert(
                    f"[{config['symbol']}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                    "WARNING",
                )
                await asyncio.sleep(config["loop_delay"])
                continue

            trading_signal, signal_score = await analyzer.generate_trading_signal(
                current_price, None, mtf_trends # Pass None for orderbook_manager if not used here
            )
            atr_value = Decimal(
                str(analyzer._get_indicator_value("ATR", Decimal("0.01")))
            ) # Default to a small positive value if ATR is missing

            # Manage existing positions before potentially opening new ones
            position_manager.manage_positions(current_price, atr_value, performance_tracker)

            if (
                trading_signal == "BUY"
                and signal_score >= config["signal_score_threshold"]
            ):
                logger.info(
                    f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}. Attempting to open position.{RESET}"
                )
                position_manager.open_position("BUY", current_price, atr_value)
            elif (
                trading_signal == "SELL"
                and signal_score <= -config["signal_score_threshold"]
            ):
                logger.info(
                    f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}. Attempting to open position.{RESET}"
                )
                position_manager.open_position("SELL", current_price, atr_value)
            else:
                logger.info(
                    f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}"
                )

            open_positions = position_manager.get_open_positions()
            if open_positions:
                logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}")
                for pos in open_positions:
                    logger.info(
                        f"  - {pos['side']} {pos['qty'].normalize()} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}, Trailing SL: {pos.get('current_trailing_sl', 'N/A')}){RESET}"
                    )
            else:
                logger.info(f"{NEON_CYAN}No open positions.{RESET}")

            perf_summary = performance_tracker.get_summary()
            logger.info(
