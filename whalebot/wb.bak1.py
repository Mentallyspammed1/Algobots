"""Whalebot: An automated cryptocurrency trading bot for Bybit.

This bot leverages various technical indicators and multi-timeframe analysis
to generate trading signals and manage positions on the Bybit exchange.
It includes features for risk management, performance tracking, and alerts.
"""

import hashlib
import hmac
import json
import logging
import os
import sys
import time
import urllib.parse
from datetime import datetime
from decimal import ROUND_DOWN, Decimal, getcontext
from logging.handlers import RotatingFileHandler  # Added this line
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
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

# --- Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

TIMEZONE = ZoneInfo("America/Chicago")
MAX_API_RETRIES = 5
RETRY_DELAY_SECONDS = 7
REQUEST_TIMEOUT = 20
LOOP_DELAY_SECONDS = 15

# --- Configuration Management ---


def load_config(filepath: str) -> dict[str, Any]:
    """Load configuration from JSON file, creating a default if not found."""
    default_config = {
        # Core Settings
        "symbol": "BTCUSDT",
        "interval": "15m",
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
        },
        # Multi-Timeframe Analysis
        "mtf_analysis": {
            "enabled": True,
            "higher_timeframes": ["1h", "4h"],
            "trend_indicators": ["ema", "ehlers_supertrend"],
            "trend_period": 50,
            "mtf_request_delay_seconds": 0.5,  # New: Delay between MTF API requests
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
            "obv_ema_period": 20,  # For OBV EMA signal line
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
        },
        # Active Indicators & Weights
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
        },
        "weight_sets": {
            "default_scalping": {
                "ema_alignment": 0.22,
                "sma_trend_filter": 0.28,
                "momentum": 0.18,
                "volume_confirmation": 0.12,
                "stoch_rsi": 0.30,
                "rsi": 0.12,
                "bollinger_bands": 0.22,
                "vwap": 0.22,
                "cci": 0.08,
                "wr": 0.08,
                "psar": 0.22,
                "sma_10": 0.07,
                "mfi": 0.12,
                "orderbook_imbalance": 0.07,
                "ehlers_supertrend_alignment": 0.55,
                "macd_alignment": 0.28,
                "adx_strength": 0.18,
                "ichimoku_confluence": 0.38,
                "obv_momentum": 0.18,
                "cmf_flow": 0.12,
                "mtf_trend_confluence": 0.32,
            }
        },
    }
    if not Path(filepath).exists():
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(
                f"{NEON_YELLOW}Configuration file not found. Created default config at {filepath}{RESET}"
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

    SENSITIVE_WORDS = ["API_KEY", "API_SECRET"]

    def __init__(self, fmt=None, datefmt=None, style="%"):
        super().__init__(fmt, datefmt, style)
        self._fmt = fmt if fmt else self.default_fmt()

    def default_fmt(self):
        return "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def format(self, record):
        original_message = super().format(record)
        redacted_message = original_message
        for word in self.SENSITIVE_WORDS:
            if word in redacted_message:
                redacted_message = redacted_message.replace(word, "*" * len(word))
        return redacted_message


def setup_logger(log_name: str, level=logging.INFO) -> logging.Logger:
    """Configures and returns a logger with file and console handlers."""
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
        log_file = os.path.join(LOG_DIRECTORY, f"{log_name}.log")
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
    """Creates a requests session with retry logic."""
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
    """Generates a Bybit API signature."""
    return hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def bybit_request(
    method: str,
    endpoint: str,
    params: dict | None = None,
    signed: bool = False,
    logger: logging.Logger = setup_logger("bybit_api"),
) -> dict | None:
    """Sends a request to the Bybit API."""
    session = create_session()
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}

    if signed:
        if not API_KEY or not API_SECRET:
            logger.error(
                f"{NEON_RED}API_KEY or API_SECRET not set for signed request.{RESET}"
            )
            return None

        timestamp = str(int(time.time() * 1000))
        if method == "GET":
            query_string = urllib.parse.urlencode(params) if params else ""
            recv_window = "20000"
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
            logger.debug(f"GET Request: {url}?{query_string}")
            response = session.get(
                url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
            )
        else:  # POST
            json_params = json.dumps(params) if params else ""
            recv_window = "20000"
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
            logger.debug(f"POST Request: {url} with payload {json_params}")
            response = session.post(
                url, json=params, headers=headers, timeout=REQUEST_TIMEOUT
            )
    else:
        logger.debug(f"Public Request: {url} with params {params}")
        response = session.get(
            url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
        )

    try:
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") != 0:
            logger.error(
                f"{NEON_RED}Bybit API Error: {data.get('retMsg')} (Code: {data.get('retCode')}){RESET}"
            )
            return None
        return data
    except requests.exceptions.HTTPError as e:
        logger.error(
            f"{NEON_RED}HTTP Error: {e.response.status_code} - {e.response.text}{RESET}"
        )
    except requests.exceptions.ConnectionError as e:
        logger.error(f"{NEON_RED}Connection Error: {e}{RESET}")
    except requests.exceptions.Timeout:
        logger.error(
            f"{NEON_RED}Request timed out after {REQUEST_TIMEOUT} seconds.{RESET}"
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"{NEON_RED}Request Exception: {e}{RESET}")
    except json.JSONDecodeError:
        logger.error(
            f"{NEON_RED}Failed to decode JSON response: {response.text}{RESET}"
        )
    return None


def fetch_current_price(symbol: str, logger: logging.Logger) -> Decimal | None:
    """Fetches the current market price for a symbol."""
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
    """Fetches kline data for a symbol and interval."""
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

        if df.empty:
            logger.warning(
                f"{NEON_YELLOW}Fetched klines for {symbol} {interval} but DataFrame is empty after processing. Raw response: {response}{RESET}"
            )
            return None

        logger.debug(f"Fetched {len(df)} {interval} klines for {symbol}.")
        return df
    logger.warning(
        f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}. API response might be empty or invalid. Raw response: {response}{RESET}"
    )
    return None


def fetch_orderbook(symbol: str, limit: int, logger: logging.Logger) -> dict | None:
    """Fetches orderbook data for a symbol."""
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
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.open_positions: list[dict] = []  # Stores active positions
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]

    def _get_current_balance(self) -> Decimal:
        """Fetches current account balance (simplified for simulation)."""
        # In a real bot, this would query the exchange.
        # For simulation, use configured account balance.
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    def _calculate_order_size(
        self, current_price: Decimal, atr_value: Decimal
    ) -> Decimal:
        """Calculates order size based on risk per trade and ATR."""
        if not self.trade_management_enabled:
            return Decimal("0")

        account_balance = self._get_current_balance()
        risk_per_trade_percent = (
            Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
            / 100
        )
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )

        risk_amount = account_balance * risk_per_trade_percent
        stop_loss_distance = atr_value * stop_loss_atr_multiple

        if stop_loss_distance <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}Calculated stop loss distance is zero or negative. Cannot determine order size.{RESET}"
            )
            return Decimal("0")

        # Order size in USD value
        order_value = risk_amount / stop_loss_distance
        # Convert to quantity of the asset (e.g., BTC)
        order_qty = order_value / current_price

        # Round order_qty to appropriate precision for the symbol (e.g., BTCUSDT might be 0.0001)
        # This requires knowing the symbol's lot size filter, which is exchange-specific.
        # For simulation, we'll use a generic rounding.
        order_qty = order_qty.quantize(
            Decimal("0.0001"), rounding=ROUND_DOWN
        )  # Example precision

        self.logger.info(
            f"Calculated order size: {order_qty} {self.symbol} (Risk: {risk_amount:.2f} USD)"
        )
        return order_qty

    def open_position(
        self, signal: str, current_price: Decimal, atr_value: Decimal
    ) -> dict | None:
        """Opens a new position if conditions allow.
        Returns the new position details or None.
        """
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}Trade management is disabled. Skipping opening position.{RESET}"
            )
            return None

        if len(self.open_positions) >= self.max_open_positions:
            self.logger.info(
                f"{NEON_YELLOW}Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
            )
            return None

        if signal not in ["BUY", "SELL"]:
            self.logger.debug(f"Invalid signal '{signal}' for opening position.")
            return None

        order_qty = self._calculate_order_size(current_price, atr_value)
        if order_qty <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}Order quantity is zero or negative. Cannot open position.{RESET}"
            )
            return None

        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"])
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"])
        )

        if signal == "BUY":
            stop_loss = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit = current_price + (atr_value * take_profit_atr_multiple)
        else:  # SELL
            stop_loss = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit = current_price - (atr_value * take_profit_atr_multiple)

        position = {
            "entry_time": datetime.now(TIMEZONE),
            "symbol": self.symbol,
            "side": signal,
            "entry_price": current_price,
            "qty": order_qty,
            "stop_loss": stop_loss.quantize(Decimal("0.00001"), rounding=ROUND_DOWN),
            "take_profit": take_profit.quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "status": "OPEN",
        }
        self.open_positions.append(position)
        self.logger.info(f"{NEON_GREEN}Opened {signal} position: {position}{RESET}")
        return position

    def manage_positions(
        self, current_price: Decimal, performance_tracker: Any
    ) -> None:
        """Checks and manages all open positions (SL/TP).
        In a real bot, this would interact with exchange orders.
        """
        if not self.trade_management_enabled or not self.open_positions:
            return

        positions_to_close = []
        for i, position in enumerate(self.open_positions):
            if position["status"] == "OPEN":
                side = position["side"]
                entry_price = position["entry_price"]
                stop_loss = position["stop_loss"]
                take_profit = position["take_profit"]
                qty = position["qty"]

                closed_by = ""
                close_price = Decimal("0")

                if side == "BUY":
                    if current_price <= stop_loss:
                        closed_by = "STOP_LOSS"
                        close_price = current_price
                    elif current_price >= take_profit:
                        closed_by = "TAKE_PROFIT"
                        close_price = current_price
                elif current_price >= stop_loss:
                    closed_by = "STOP_LOSS"
                    close_price = current_price
                elif current_price <= take_profit:
                    closed_by = "TAKE_PROFIT"
                    close_price = current_price

                if closed_by:
                    position["status"] = "CLOSED"
                    position["exit_time"] = datetime.now(TIMEZONE)
                    position["exit_price"] = close_price
                    position["closed_by"] = closed_by
                    positions_to_close.append(i)

                    pnl = (
                        (close_price - entry_price) * qty
                        if side == "BUY"
                        else (entry_price - close_price) * qty
                    )
                    performance_tracker.record_trade(position, pnl)
                    self.logger.info(
                        f"{NEON_PURPLE}Closed {side} position by {closed_by}: {position}. PnL: {pnl:.2f}{RESET}"
                    )

        # Remove closed positions
        self.open_positions = [
            pos
            for i, pos in enumerate(self.open_positions)
            if i not in positions_to_close
        ]

    def get_open_positions(self) -> list[dict]:
        """Returns a list of currently open positions."""
        return [pos for pos in self.open_positions if pos["status"] == "OPEN"]


# --- Performance Tracking ---
class PerformanceTracker:
    """Tracks and reports trading performance."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.trades: list[dict] = []
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0

    def record_trade(self, position: dict, pnl: Decimal) -> None:
        """Records a completed trade."""
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
            f"{NEON_CYAN}Trade recorded. Current Total PnL: {self.total_pnl:.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}"
        )

    def get_summary(self) -> dict:
        """Returns a summary of all recorded trades."""
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
        self.logger = logger

    def send_alert(self, message: str, level: str = "INFO") -> None:
        """Sends an alert (currently logs it)."""
        if level == "INFO":
            self.logger.info(f"{NEON_BLUE}ALERT: {message}{RESET}")
        elif level == "WARNING":
            self.logger.warning(f"{NEON_YELLOW}ALERT: {message}{RESET}")
        elif level == "ERROR":
            self.logger.error(f"{NEON_RED}ALERT: {message}{RESET}")
        # In a real bot, integrate with Telegram, Discord, Email etc.


# --- Trading Analysis (Upgraded with Ehlers SuperTrend) ---
class TradingAnalyzer:
    """Analyzes trading data and generates signals with MTF and Ehlers SuperTrend."""

    def __init__(
        self,
        df: pd.DataFrame,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
    ):
        self.df = df.copy()
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.indicator_values: dict[str, float | str | Decimal] = {}
        self.fib_levels: dict[str, Decimal] = {}
        self.weights = config["weight_sets"]["default_scalping"]
        self.indicator_settings = config["indicator_settings"]

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.{RESET}"
            )
            return

        self._calculate_all_indicators()
        if self.config["indicators"].get("fibonacci_levels", False):
            self.calculate_fibonacci_levels()

    def _safe_calculate(
        self, func: callable, name: str, min_data_points: int = 0, *args, **kwargs
    ) -> Any | None:
        """Helper to safely calculate indicators and log errors, with min_data_points check."""
        if len(self.df) < min_data_points:
            self.logger.debug(
                f"Skipping indicator '{name}': Not enough data. Need {min_data_points}, have {len(self.df)}."
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
                    f"{NEON_YELLOW}Indicator '{name}' returned empty or None after calculation. Not enough valid data?{RESET}"
                )
                return None
            return result
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}Error calculating indicator '{name}': {e}{RESET}"
            )
            return None

    def _calculate_all_indicators(self) -> None:
        """Calculate all enabled technical indicators, including Ehlers SuperTrend."""
        self.logger.debug("Calculating technical indicators...")
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
            self.calculate_true_range, "TR", min_data_points=2
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

            if tenkan_sen is not None:
                self.indicator_values["Tenkan_Sen"] = tenkan_sen.iloc[-1]
            if kijun_sen is not None:
                self.indicator_values["Kijun_Sen"] = kijun_sen.iloc[-1]
            if senkou_span_a is not None:
                self.indicator_values["Senkou_Span_A"] = senkou_span_a.iloc[-1]
            if senkou_span_b is not None:
                self.indicator_values["Senkou_Span_B"] = senkou_span_b.iloc[-1]
            if chikou_span is not None:
                self.indicator_values["Chikou_Span"] = chikou_span.fillna(0).iloc[
                    -1
                ]  # Fill NaN before taking last value

        # PSAR
        if cfg["indicators"].get("psar", False):
            psar_val, psar_dir = self._safe_calculate(
                self.calculate_psar,
                "PSAR",
                min_data_points=2,  # PSAR needs at least 2 bars to start
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
                self.calculate_vwap, "VWAP", min_data_points=1
            )
            if self.df["VWAP"] is not None:
                self.indicator_values["VWAP"] = self.df["VWAP"].iloc[-1]

        # --- Ehlers SuperTrend Calculation ---
        if cfg["indicators"].get("ehlers_supertrend", False):
            st_fast = self._safe_calculate(
                self.calculate_ehlers_supertrend,
                "EhlersSuperTrendFast",
                min_data_points=isd["ehlers_fast_period"]
                * 3,  # Needs more data for smoothing
                period=isd["ehlers_fast_period"],
                multiplier=isd["ehlers_fast_multiplier"],
            )
            if st_fast is not None and not st_fast.empty:
                self.df["st_fast_dir"] = st_fast["direction"]
                self.df["st_fast_val"] = st_fast["supertrend"]
                self.indicator_values["ST_Fast_Dir"] = st_fast["direction"].iloc[-1]
                self.indicator_values["ST_Fast_Val"] = st_fast["supertrend"].iloc[-1]

            st_slow = self._safe_calculate(
                self.calculate_ehlers_supertrend,
                "EhlersSuperTrendSlow",
                min_data_points=isd["ehlers_slow_period"]
                * 3,  # Needs more data for smoothing
                period=isd["ehlers_slow_period"],
                multiplier=isd["ehlers_slow_multiplier"],
            )
            if st_slow is not None and not st_slow.empty:
                self.df["st_slow_dir"] = st_slow["direction"]
                self.df["st_slow_val"] = st_slow["supertrend"]
                self.indicator_values["ST_Slow_Dir"] = st_slow["direction"].iloc[-1]
                self.indicator_values["ST_Slow_Val"] = st_slow["supertrend"].iloc[-1]

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
                min_data_points=isd["adx_period"] * 2,
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

        # Final dropna after all indicators are calculated
        initial_len = len(self.df)
        # Only drop rows where 'close' is NaN, or if a row is entirely NaN after calculations
        self.df.dropna(
            subset=["close"], inplace=True
        )  # Ensure close price is always valid
        self.df.fillna(
            0, inplace=True
        )  # Fill any remaining NaNs in indicator columns with 0

        if len(self.df) < initial_len:
            self.logger.debug(
                f"Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations."
            )

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}DataFrame is empty after calculating all indicators and dropping NaNs.{RESET}"
            )
        else:
            self.logger.debug(
                f"Indicators calculated. Final DataFrame size: {len(self.df)}"
            )

    def calculate_true_range(self) -> pd.Series:
        """Calculates True Range (TR)."""
        if len(self.df) < 2:
            return pd.Series(np.nan, index=self.df.index)
        high_low = self.df["high"] - self.df["low"]
        high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
        low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(
            axis=1
        )

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < 2:
            return pd.Series(np.nan, index=series.index)

        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < 2:
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
        self, period: int, multiplier: float
    ) -> pd.DataFrame | None:
        """Calculates SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(self.df) < period * 3:
            self.logger.debug(
                f"Not enough data for Ehlers SuperTrend (period={period}). Need at least {period*3} bars."
            )
            return None

        df_copy = self.df.copy()

        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)

        tr = self.calculate_true_range()
        smoothed_atr = self.calculate_super_smoother(tr, period)

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr
        # Removed df_copy.dropna(inplace=True) from here
        if df_copy.empty:
            self.logger.debug(
                "Ehlers SuperTrend: DataFrame empty after smoothing. Returning None."
            )
            return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        first_valid_idx = df_copy.index[0]
        supertrend.loc[first_valid_idx] = lower_band.loc[first_valid_idx]

        for i in range(1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 0:
                if curr_close > prev_supertrend:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = max(
                        lower_band.loc[current_idx], prev_supertrend
                    )
                else:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = min(
                        upper_band.loc[current_idx], prev_supertrend
                    )
            elif prev_direction == 1:
                if curr_close < prev_supertrend:
                    direction.loc[current_idx] = -1
                    supertrend.loc[current_idx] = upper_band.loc[current_idx]
                else:
                    direction.loc[current_idx] = 1
                    supertrend.loc[current_idx] = max(
                        lower_band.loc[current_idx], prev_supertrend
                    )
            elif curr_close > prev_supertrend:
                direction.loc[current_idx] = 1
                supertrend.loc[current_idx] = lower_band.loc[current_idx]
            else:
                direction.loc[current_idx] = -1
                supertrend.loc[current_idx] = min(
                    upper_band.loc[current_idx], prev_supertrend
                )

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(self.df.index)

    def calculate_macd(
        self, fast_period: int, slow_period: int, signal_period: int
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculates Moving Average Convergence Divergence (MACD)."""
        if len(self.df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def calculate_rsi(self, period: int) -> pd.Series:
        """Calculates Relative Strength Index (RSI)."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stoch_rsi(
        self, period: int, k_period: int, d_period: int
    ) -> tuple[pd.Series, pd.Series]:
        """Calculates Stochastic RSI."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index), pd.Series(
                np.nan, index=self.df.index
            )
        rsi = self.calculate_rsi(period)

        lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
        highest_rsi = rsi.rolling(window=period, min_periods=period).max()

        # Avoid division by zero if highest_rsi == lowest_rsi
        stoch_rsi_k_raw = ((rsi - lowest_rsi) / (highest_rsi - lowest_rsi)).fillna(
            0
        ) * 100
        stoch_rsi_k_raw[np.isinf(stoch_rsi_k_raw)] = 0  # Handle inf values

        stoch_rsi_k = stoch_rsi_k_raw.rolling(
            window=k_period, min_periods=k_period
        ).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean()

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculates Average Directional Index (ADX)."""
        if len(self.df) < period * 2:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        # True Range
        tr = self.calculate_true_range()

        # Directional Movement
        plus_dm = self.df["high"].diff().clip(lower=0)
        minus_dm = -self.df["low"].diff().clip(lower=0)

        # Adjust for cases where both are positive or negative
        # If +DM > -DM, then -DM = 0. If -DM > +DM, then +DM = 0.
        # If both are negative, both are 0.
        # If both are positive, take the larger one and set the other to 0.
        # This is handled by the clip(lower=0) and the subsequent logic.

        # When +DM > -DM, set -DM to 0
        plus_dm[plus_dm < minus_dm] = 0
        # When -DM > +DM, set +DM to 0
        minus_dm[minus_dm < plus_dm] = 0

        # Smoothed True Range, +DM, -DM
        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = (plus_dm.ewm(span=period, adjust=False).mean() / atr) * 100
        minus_di = (minus_dm.ewm(span=period, adjust=False).mean() / atr) * 100

        # DX
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)).fillna(0) * 100
        dx[np.isinf(dx)] = 0  # Handle inf values from division by zero

        # ADX
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx, plus_di, minus_di

    def calculate_bollinger_bands(
        self, period: int, std_dev: float
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculates Bollinger Bands."""
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
        """Calculates Volume Weighted Average Price (VWAP)."""
        if self.df.empty:
            return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        # Ensure cumulative sum starts from valid data
        cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
        cumulative_vol = self.df["volume"].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap

    def calculate_cci(self, period: int) -> pd.Series:
        """Calculates Commodity Channel Index (CCI)."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)
        tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_tp = tp.rolling(window=period, min_periods=period).mean()
        # Corrected: Use np.abs for element-wise absolute value on potential numpy array from rolling.apply(raw=True)
        mad = tp.rolling(window=period, min_periods=period).apply(
            lambda x: np.abs(x - x.mean()).mean(), raw=False
        )
        cci = (tp - sma_tp) / (0.015 * mad)
        return cci

    def calculate_williams_r(self, period: int) -> pd.Series:
        """Calculates Williams %R."""
        if len(self.df) < period:
            return pd.Series(np.nan, index=self.df.index)
        highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
        lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
        wr = -100 * ((highest_high - self.df["close"]) / (highest_high - lowest_low))
        return wr

    def calculate_ichimoku_cloud(
        self,
        tenkan_period: int,
        kijun_period: int,
        senkou_span_b_period: int,
        chikou_span_offset: int,
    ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculates Ichimoku Cloud components."""
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

        # Tenkan-sen (Conversion Line): (Highest High + Lowest Low) / 2 over the last 9 periods
        tenkan_sen = (
            self.df["high"].rolling(window=tenkan_period).max()
            + self.df["low"].rolling(window=tenkan_period).min()
        ) / 2

        # Kijun-sen (Base Line): (Highest High + Lowest Low) / 2 over the last 26 periods
        kijun_sen = (
            self.df["high"].rolling(window=kijun_period).max()
            + self.df["low"].rolling(window=kijun_period).min()
        ) / 2

        # Senkou Span A (Leading Span A): (Tenkan-sen + Kijun-sen) / 2 projected 26 periods ahead
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)

        # Senkou Span B (Leading Span B): (Highest High + Lowest Low) / 2 over the last 52 periods projected 26 periods ahead
        senkou_span_b = (
            (
                self.df["high"].rolling(window=senkou_span_b_period).max()
                + self.df["low"].rolling(window=senkou_span_b_period).min()
            )
            / 2
        ).shift(kijun_period)

        # Chikou Span (Lagging Span): Current closing price projected 26 periods back
        chikou_span = self.df["close"].shift(-chikou_span_offset)

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    def calculate_mfi(self, period: int) -> pd.Series:
        """Calculates Money Flow Index (MFI)."""
        if len(self.df) <= period:
            return pd.Series(np.nan, index=self.df.index)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        money_flow = typical_price * self.df["volume"]

        positive_flow = pd.Series(0.0, index=self.df.index)
        negative_flow = pd.Series(0.0, index=self.df.index)

        # Calculate positive and negative money flow
        for i in range(1, len(self.df)):
            if typical_price.iloc[i] > typical_price.iloc[i - 1]:
                positive_flow.iloc[i] = money_flow.iloc[i]
            elif typical_price.iloc[i] < typical_price.iloc[i - 1]:
                negative_flow.iloc[i] = money_flow.iloc[i]

        # Rolling sum for period
        positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
        negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()

        # Avoid division by zero
        mf_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + mf_ratio))
        return mfi

    def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
        """Calculates On-Balance Volume (OBV) and its EMA."""
        if len(self.df) < 2:
            return pd.Series(np.nan), pd.Series(np.nan)

        obv = pd.Series(0.0, index=self.df.index)
        obv.iloc[0] = 0  # Initialize OBV

        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i - 1]

        obv_ema = obv.ewm(span=ema_period, adjust=False).mean()

        return obv, obv_ema

    def calculate_cmf(self, period: int) -> pd.Series:
        """Calculates Chaikin Money Flow (CMF)."""
        if len(self.df) < period:
            return pd.Series(np.nan)

        # Money Flow Multiplier (MFM)
        mfm = (
            (self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])
        ) / (self.df["high"] - self.df["low"])
        mfm = mfm.fillna(0)  # Handle division by zero if high == low

        # Money Flow Volume (MFV)
        mfv = mfm * self.df["volume"]

        # CMF
        cmf = (
            mfv.rolling(window=period).sum()
            / self.df["volume"].rolling(window=period).sum()
        )
        cmf = cmf.fillna(0)  # Handle division by zero if volume sum is zero

        return cmf

    def calculate_psar(
        self, acceleration: float, max_acceleration: float
    ) -> tuple[pd.Series, pd.Series]:
        """Calculates Parabolic SAR."""
        if len(self.df) < 2:
            return pd.Series(np.nan, index=self.df.index), pd.Series(
                np.nan, index=self.df.index
            )

        psar = self.df["close"].copy()
        bull = pd.Series(True, index=self.df.index)
        af = acceleration
        ep = (
            self.df["low"].iloc[0]
            if self.df["close"].iloc[0] < self.df["close"].iloc[1]
            else self.df["high"].iloc[0]
        )

        for i in range(1, len(self.df)):
            if bull.iloc[i - 1]:  # Bullish trend
                psar.iloc[i] = psar.iloc[i - 1] + af * (ep - psar.iloc[i - 1])
            else:  # Bearish trend
                psar.iloc[i] = psar.iloc[i - 1] - af * (psar.iloc[i - 1] - ep)

            reverse = False
            if bull.iloc[i - 1] and self.df["low"].iloc[i] < psar.iloc[i]:
                bull.iloc[i] = False
                reverse = True
            elif not bull.iloc[i - 1] and self.df["high"].iloc[i] > psar.iloc[i]:
                bull.iloc[i] = True
                reverse = True
            else:
                bull.iloc[i] = bull.iloc[i - 1]

            if reverse:
                af = acceleration
                ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
            elif bull.iloc[i]:
                if self.df["high"].iloc[i] > ep:
                    ep = self.df["high"].iloc[i]
                    af = min(af + acceleration, max_acceleration)
            elif self.df["low"].iloc[i] < ep:
                ep = self.df["low"].iloc[i]
                af = min(af + acceleration, max_acceleration)

        direction = pd.Series(0, index=self.df.index, dtype=int)
        direction[psar < self.df["close"]] = 1
        direction[psar > self.df["close"]] = -1

        return psar, direction

    def calculate_fibonacci_levels(self) -> None:
        """Calculates Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(
                f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}"
            )
            return

        recent_high = self.df["high"].iloc[-window:].max()
        recent_low = self.df["low"].iloc[-window:].min()

        diff = recent_high - recent_low

        self.fib_levels = {
            "0.0%": Decimal(str(recent_high)),
            "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(
                Decimal("0.00001"), rounding=ROUND_DOWN
            ),
            "100.0%": Decimal(str(recent_low)),
        }
        self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieves an indicator value."""
        return self.indicator_values.get(key, default)

    def _check_orderbook(self, current_price: Decimal, orderbook_data: dict) -> float:
        """Analyzes orderbook imbalance."""
        bids = orderbook_data.get("b", [])
        asks = orderbook_data.get("a", [])

        bid_volume = sum(Decimal(b[1]) for b in bids)
        ask_volume = sum(Decimal(a[1]) for a in asks)

        if bid_volume + ask_volume == 0:
            return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(
            f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})"
        )
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determines trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty:
            return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]

        if indicator_type == "sma":
            period = self.config["mtf_analysis"]["trend_period"]
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"MTF SMA: Not enough data for {period} period. Have {len(higher_tf_df)}."
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
            period = self.config["mtf_analysis"]["trend_period"]
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"MTF EMA: Not enough data for {period} period. Have {len(higher_tf_df)}."
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
            # Temporarily create an analyzer for the higher timeframe data to calculate its ST
            # Pass the logger and symbol to the temporary analyzer
            temp_analyzer = TradingAnalyzer(
                higher_tf_df, self.config, self.logger, self.symbol
            )
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
    ) -> tuple[str, float]:
        """Generates a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}"
            )
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))

        # EMA Alignment
        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long:
                    signal_score += weights.get("ema_alignment", 0)
                elif ema_short < ema_long:
                    signal_score -= weights.get("ema_alignment", 0)

        # SMA Trend Filter
        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long:
                    signal_score += weights.get("sma_trend_filter", 0)
                elif current_close < sma_long:
                    signal_score -= weights.get("sma_trend_filter", 0)

        # Momentum (RSI, StochRSI, CCI, WR, MFI)
        if active_indicators.get("momentum", False):
            rsi = self._get_indicator_value("RSI")
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            cci = self._get_indicator_value("CCI")
            wr = self._get_indicator_value("WR")
            mfi = self._get_indicator_value("MFI")

            isd = self.indicator_settings

            # RSI
            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]:
                    signal_score += weights.get("rsi", 0) * 0.5
                elif rsi > isd["rsi_overbought"]:
                    signal_score -= weights.get("rsi", 0) * 0.5

            # StochRSI Crossover
            if not pd.isna(stoch_k) and not pd.isna(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd["stoch_rsi_oversold"]:
                    signal_score += weights.get("stoch_rsi", 0) * 0.5
                elif stoch_k < stoch_d and stoch_k > isd["stoch_rsi_overbought"]:
                    signal_score -= weights.get("stoch_rsi", 0) * 0.5

            # CCI
            if not pd.isna(cci):
                if cci < isd["cci_oversold"]:
                    signal_score += weights.get("cci", 0) * 0.5
                elif cci > isd["cci_overbought"]:
                    signal_score -= weights.get("cci", 0) * 0.5

            # Williams %R
            if not pd.isna(wr):
                if wr < isd["williams_r_oversold"]:
                    signal_score += weights.get("wr", 0) * 0.5
                elif wr > isd["williams_r_overbought"]:
                    signal_score -= weights.get("wr", 0) * 0.5

            # MFI
            if not pd.isna(mfi):
                if mfi < isd["mfi_oversold"]:
                    signal_score += weights.get("mfi", 0) * 0.5
                elif mfi > isd["mfi_overbought"]:
                    signal_score -= weights.get("mfi", 0) * 0.5

        # Bollinger Bands
        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower:
                    signal_score += weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper:
                    signal_score -= weights.get("bollinger_bands", 0) * 0.5

        # VWAP
        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                # Price above VWAP is bullish, below is bearish
                if current_close > vwap:
                    signal_score += weights.get("vwap", 0) * 0.2
                elif current_close < vwap:
                    signal_score -= weights.get("vwap", 0) * 0.2

                # Price crossing VWAP can be a stronger signal
                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if (
                        current_close > vwap and prev_close <= prev_vwap
                    ):  # Bullish crossover
                        signal_score += weights.get("vwap", 0) * 0.3
                        self.logger.debug("VWAP: Bullish crossover detected.")
                    elif (
                        current_close < vwap and prev_close >= prev_vwap
                    ):  # Bearish crossover
                        signal_score -= weights.get("vwap", 0) * 0.3
                        self.logger.debug("VWAP: Bearish crossover detected.")

        # PSAR
        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")
            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                # PSAR direction indicates trend
                if psar_dir == 1:  # PSAR is below price, bullish
                    signal_score += weights.get("psar", 0) * 0.5
                elif psar_dir == -1:  # PSAR is above price, bearish
                    signal_score -= weights.get("psar", 0) * 0.5

                # Price crossing PSAR can be a stronger signal
                if len(self.df) > 1:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
                    if (
                        current_close > psar_val and prev_close <= prev_psar_val
                    ):  # Bullish reversal
                        signal_score += weights.get("psar", 0) * 0.4
                        self.logger.debug("PSAR: Bullish reversal detected.")
                    elif (
                        current_close < psar_val and prev_close >= prev_psar_val
                    ):  # Bearish reversal
                        signal_score -= weights.get("psar", 0) * 0.4
                        self.logger.debug("PSAR: Bearish reversal detected.")

        # Orderbook Imbalance
        if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
            imbalance = self._check_orderbook(current_price, orderbook_data)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        # Fibonacci Levels (confluence with price action)
        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            # Check if price is near a key Fibonacci level and reacting
            # This is a simplified check, real logic would be more complex
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"]:  # Exclude high/low
                    if abs(current_price - level_price) / current_price < Decimal(
                        "0.001"
                    ):  # Within 0.1%
                        self.logger.debug(
                            f"Price near Fibonacci level {level_name}: {level_price}"
                        )
                        # Add a small boost/detraction based on previous bar's reaction
                        if len(self.df) > 1:  # Ensure there's a previous close
                            prev_close = Decimal(str(self.df["close"].iloc[-2]))
                            if (
                                current_price > prev_close
                                and current_price > level_price
                            ):
                                signal_score += weights.get("fibonacci_levels", 0) * 0.1
                            elif (
                                current_price < prev_close
                                and current_price < level_price
                            ):
                                signal_score -= weights.get("fibonacci_levels", 0) * 0.1

        # --- Ehlers SuperTrend Alignment Scoring ---
        if active_indicators.get("ehlers_supertrend", False):
            st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
            st_slow_dir = self._get_indicator_value("ST_Slow_Dir")

            prev_st_fast_dir = (
                self.df["st_fast_dir"].iloc[-2]
                if "st_fast_dir" in self.df.columns and len(self.df) > 1
                else np.nan
            )

            weight = weights.get("ehlers_supertrend_alignment", 0.0)

            if (
                not pd.isna(st_fast_dir)
                and not pd.isna(st_slow_dir)
                and not pd.isna(prev_st_fast_dir)
            ):
                # High-conviction BUY signal: Slow trend is UP, and fast trend just flipped UP
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
                    signal_score += weight
                    self.logger.debug(
                        "Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend)."
                    )
                # High-conviction SELL signal: Slow trend is DOWN, and fast trend just flipped DOWN
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
                    signal_score -= weight
                    self.logger.debug(
                        "Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend)."
                    )
                # Weaker continuation signal: Both trends are aligned
                elif st_slow_dir == 1 and st_fast_dir == 1:
                    signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1:
                    signal_score -= weight * 0.3

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
            ):
                # MACD Crossover Buy Signal
                if (
                    macd_line > signal_line
                    and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]
                ):
                    signal_score += weight
                    self.logger.debug(
                        "MACD: BUY signal (MACD line crossed above Signal line)."
                    )
                # MACD Crossover Sell Signal
                elif (
                    macd_line < signal_line
                    and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]
                ):
                    signal_score -= weight
                    self.logger.debug(
                        "MACD: SELL signal (MACD line crossed below Signal line)."
                    )
                # Histogram increasing/decreasing (momentum confirmation)
                elif (
                    histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0
                ):  # Histogram crosses above zero
                    signal_score += weight * 0.2
                elif (
                    histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0
                ):  # Histogram crosses below zero
                    signal_score -= weight * 0.2

        # --- ADX Alignment Scoring ---
        if active_indicators.get("adx", False):
            adx_val = self._get_indicator_value("ADX")
            plus_di = self._get_indicator_value("PlusDI")
            minus_di = self._get_indicator_value("MinusDI")

            weight = weights.get("adx_strength", 0.0)

            if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
                # ADX strength (trend presence)
                if adx_val > 25:  # Strong trend
                    if plus_di > minus_di:  # Bullish trend
                        signal_score += weight
                        self.logger.debug(
                            "ADX: Strong BUY trend (ADX > 25, +DI > -DI)."
                        )
                    elif minus_di > plus_di:  # Bearish trend
                        signal_score -= weight
                        self.logger.debug(
                            "ADX: Strong SELL trend (ADX > 25, -DI > +DI)."
                        )
                elif adx_val < 20:  # Weak or no trend
                    # Neutral or reduce signal strength if ADX is low
                    signal_score += 0  # No strong signal from ADX
                    self.logger.debug("ADX: Weak trend (ADX < 20). Neutral signal.")

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
            ):

                # Tenkan-sen crosses Kijun-sen
                if (
                    tenkan_sen > kijun_sen
                    and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]
                ):
                    signal_score += (
                        weight * 0.5
                    )  # Tenkan-sen crosses above Kijun-sen (bullish)
                    self.logger.debug(
                        "Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish)."
                    )
                elif (
                    tenkan_sen < kijun_sen
                    and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]
                ):
                    signal_score -= (
                        weight * 0.5
                    )  # Tenkan-sen crosses below Kijun-sen (bearish)
                    self.logger.debug(
                        "Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish)."
                    )

                # Price breaks through Kumo (Cloud)
                if current_close > max(senkou_span_a, senkou_span_b) and self.df[
                    "close"
                ].iloc[-2] <= max(
                    self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
                ):
                    signal_score += (
                        weight * 0.7
                    )  # Price breaks above Kumo (strong bullish)
                    self.logger.debug(
                        "Ichimoku: Price broke above Kumo (strong bullish)."
                    )
                elif current_close < min(senkou_span_a, senkou_span_b) and self.df[
                    "close"
                ].iloc[-2] >= min(
                    self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
                ):
                    signal_score -= (
                        weight * 0.7
                    )  # Price breaks below Kumo (strong bearish)
                    self.logger.debug(
                        "Ichimoku: Price broke below Kumo (strong bearish)."
                    )

                # Chikou Span confirmation
                if (
                    chikou_span > current_close
                    and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]
                ):
                    signal_score += (
                        weight * 0.3
                    )  # Chikou Span crosses above price (bullish confirmation)
                    self.logger.debug(
                        "Ichimoku: Chikou Span crossed above price (bullish confirmation)."
                    )
                elif (
                    chikou_span < current_close
                    and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]
                ):
                    signal_score -= (
                        weight * 0.3
                    )  # Chikou Span crosses below price (bearish confirmation)
                    self.logger.debug(
                        "Ichimoku: Chikou Span crossed below price (bearish confirmation)."
                    )

        # --- OBV Alignment Scoring ---
        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")

            weight = weights.get("obv_momentum", 0.0)

            if not pd.isna(obv_val) and not pd.isna(obv_ema):
                # OBV crossing its EMA
                if (
                    obv_val > obv_ema
                    and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]
                ):
                    signal_score += weight * 0.5  # Bullish crossover
                    self.logger.debug("OBV: Bullish crossover detected.")
                elif (
                    obv_val < obv_ema
                    and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]
                ):
                    signal_score -= weight * 0.5  # Bearish crossover
                    self.logger.debug("OBV: Bearish crossover detected.")

                # OBV trend (divergence with price can be powerful, but harder to implement simply)
                # For now, simple trend following
                if len(self.df) > 2:
                    if (
                        obv_val > self.df["OBV"].iloc[-2]
                        and obv_val > self.df["OBV"].iloc[-3]
                    ):
                        signal_score += weight * 0.2  # OBV trending up
                    elif (
                        obv_val < self.df["OBV"].iloc[-2]
                        and obv_val < self.df["OBV"].iloc[-3]
                    ):
                        signal_score -= weight * 0.2  # OBV trending down

        # --- CMF Alignment Scoring ---
        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")

            weight = weights.get("cmf_flow", 0.0)

            if not pd.isna(cmf_val):
                # CMF above/below zero indicates money flow direction
                if cmf_val > 0:
                    signal_score += weight * 0.5  # Positive money flow
                elif cmf_val < 0:
                    signal_score -= weight * 0.5  # Negative money flow

                # CMF trend (increasing/decreasing)
                if len(self.df) > 2:
                    if (
                        cmf_val > self.df["CMF"].iloc[-2]
                        and cmf_val > self.df["CMF"].iloc[-3]
                    ):
                        signal_score += weight * 0.3  # CMF trending up
                    elif (
                        cmf_val < self.df["CMF"].iloc[-2]
                        and cmf_val < self.df["CMF"].iloc[-3]
                    ):
                        signal_score -= weight * 0.3  # CMF trending down

        # --- Multi-Timeframe Trend Confluence Scoring ---
        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = 0
            mtf_sell_score = 0
            for tf, trend in mtf_trends.items():
                if trend == "UP":
                    mtf_buy_score += 1
                elif trend == "DOWN":
                    mtf_sell_score -= 1  # Subtract for sell bias

            mtf_weight = weights.get("mtf_trend_confluence", 0.0)
            # Normalize MTF score by number of MTF indicators/timeframes
            if mtf_trends:
                # Calculate a normalized score based on the balance of buy/sell trends
                # e.g., if 2 UP, 1 DOWN, score is (2-1)/3 = 0.33
                normalized_mtf_score = (mtf_buy_score + mtf_sell_score) / len(
                    mtf_trends
                )
                signal_score += mtf_weight * normalized_mtf_score
                self.logger.debug(
                    f"MTF Confluence: Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {abs(mtf_sell_score)}). Total MTF contribution: {mtf_weight * normalized_mtf_score:.2f}"
                )

        # --- Final Signal Determination ---
        threshold = self.config["signal_score_threshold"]
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
        self, current_price: Decimal, atr_value: Decimal, signal: str
    ) -> tuple[Decimal, Decimal]:
        """Calculates Take Profit and Stop Loss levels."""
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
            return Decimal("0"), Decimal("0")  # Should not happen for valid signals

        return take_profit.quantize(
            Decimal("0.01"), rounding=ROUND_DOWN
        ), stop_loss.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def display_indicator_values_and_price(
    config: dict[str, Any],
    logger: logging.Logger,
    current_price: Decimal,
    df: pd.DataFrame,
    orderbook_data: dict | None,
    mtf_trends: dict[str, str],
) -> None:
    """Displays current price and calculated indicator values."""
    logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
    logger.info(f"{NEON_GREEN}Current Price: {current_price}{RESET}")

    analyzer = TradingAnalyzer(df, config, logger, config["symbol"])

    if analyzer.df.empty:
        logger.warning(
            f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.{RESET}"
        )
        return

    logger.info(f"{NEON_CYAN}--- Indicator Values ---{RESET}")
    for indicator_name, value in analyzer.indicator_values.items():
        # Format Decimal values for consistent display
        if isinstance(value, Decimal) or isinstance(value, float):
            logger.info(f"  {NEON_YELLOW}{indicator_name}: {value:.8f}{RESET}")
        else:
            logger.info(f"  {NEON_YELLOW}{indicator_name}: {value}{RESET}")

    if analyzer.fib_levels:
        logger.info(f"{NEON_CYAN}--- Fibonacci Levels ---{RESET}")
        for level_name, level_price in analyzer.fib_levels.items():
            logger.info(f"  {NEON_YELLOW}{level_name}: {level_price:.8f}{RESET}")

    if mtf_trends:
        logger.info(f"{NEON_CYAN}--- Multi-Timeframe Trends ---{RESET}")
        for tf_indicator, trend in mtf_trends.items():
            logger.info(f"  {NEON_YELLOW}{tf_indicator}: {trend}{RESET}")

    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")


# --- Main Execution Logic ---
def main() -> None:
    """Main function to orchestrate the bot's operation."""
    config = load_config(CONFIG_FILE)
    logger = setup_logger("wgwhalex_bot")
    alert_system = AlertSystem(logger)

    # Validate interval format at startup
    # Bybit's valid intervals for linear category: "1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"
    # The API expects these as strings.
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

    # Check primary interval
    if config["interval"] not in valid_bybit_intervals:
        logger.error(
            f"{NEON_RED}Invalid primary interval '{config['interval']}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.{RESET}"
        )
        sys.exit(1)

    # Check higher timeframes intervals
    for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
        if htf_interval not in valid_bybit_intervals:
            logger.error(
                f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}' in config.json. Please use Bybit's valid string formats (e.g., '1h' should be '60', '4h' should be '240'). Exiting.{RESET}"
            )
            sys.exit(1)

    logger.info(f"{NEON_GREEN}--- Wgwhalex Trading Bot Initialized ---{RESET}")
    logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
    logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")

    position_manager = PositionManager(config, logger, config["symbol"])
    performance_tracker = PerformanceTracker(logger)

    while True:
        try:
            logger.info(f"{NEON_PURPLE}--- New Analysis Loop Started ---{RESET}")
            current_price = fetch_current_price(config["symbol"], logger)
            if current_price is None:
                alert_system.send_alert(
                    "Failed to fetch current price. Skipping loop.", "WARNING"
                )
                time.sleep(config["loop_delay"])
                continue

            # Fetch klines for primary interval
            df = fetch_klines(config["symbol"], config["interval"], 1000, logger)
            if df is None or df.empty:
                alert_system.send_alert(
                    "Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
                    "WARNING",
                )
                time.sleep(config["loop_delay"])
                continue

            # Fetch orderbook data
            orderbook_data = None
            if config["indicators"].get("orderbook_imbalance", False):
                orderbook_data = fetch_orderbook(
                    config["symbol"], config["orderbook_limit"], logger
                )

            # --- Multi-Timeframe Analysis ---
            mtf_trends: dict[str, str] = {}
            if config["mtf_analysis"]["enabled"]:
                for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                    logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
                    htf_df = fetch_klines(config["symbol"], htf_interval, 1000, logger)
                    if htf_df is not None and not htf_df.empty:
                        # For each MTF interval, calculate trend using configured indicators
                        for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                            # Pass the logger and symbol to the temporary analyzer
                            temp_htf_analyzer = TradingAnalyzer(
                                htf_df, config, logger, config["symbol"]
                            )
                            trend = temp_htf_analyzer._get_mtf_trend(
                                temp_htf_analyzer.df, trend_ind
                            )
                            mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                            logger.debug(
                                f"MTF Trend ({htf_interval}, {trend_ind}): {trend}"
                            )
                    else:
                        logger.warning(
                            f"{NEON_YELLOW}Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}"
                        )

                    # Introduce delay between MTF requests
                    # Introduce delay between MTF requests
            time.sleep(config["mtf_analysis"]["mtf_request_delay_seconds"])

            # Display indicator values and current price
            display_indicator_values_and_price(
                config, logger, current_price, df, orderbook_data, mtf_trends
            )

            # --- Trading Signal Generation ---
            analyzer = TradingAnalyzer(df, config, logger, config["symbol"])

            if (
                analyzer.df.empty
            ):  # Check if analyzer's df is empty after indicator calculations
                alert_system.send_alert(
                    "TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                    "WARNING",
                )
                time.sleep(config["loop_delay"])
                continue

            trading_signal, signal_score = analyzer.generate_trading_signal(
                current_price, orderbook_data, mtf_trends
            )
            atr_value = Decimal(
                str(analyzer._get_indicator_value("ATR", Decimal("0.01")))
            )

            # --- Position Management ---
            position_manager.manage_positions(
                current_price, performance_tracker
            )  # Check existing positions

            if (
                trading_signal == "BUY"
                and signal_score >= config["signal_score_threshold"]
            ):
                logger.info(
                    f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}{RESET}"
                )
                position_manager.open_position("BUY", current_price, atr_value)
            elif (
                trading_signal == "SELL"
                and signal_score <= -config["signal_score_threshold"]
            ):
                logger.info(
                    f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}{RESET}"
                )
                position_manager.open_position("SELL", current_price, atr_value)
            else:
                logger.info(
                    f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}"
                )

            # Log current open positions
            open_positions = position_manager.get_open_positions()
            if open_positions:
                logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}")
                for pos in open_positions:
                    logger.info(
                        f"  - {pos['side']} @ {pos['entry_price']} (SL: {pos['stop_loss']}, TP: {pos['take_profit']}){RESET}"
                    )
            else:
                logger.info(f"{NEON_CYAN}No open positions.{RESET}")

            # Log performance summary
            perf_summary = performance_tracker.get_summary()
            logger.info(
                f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl']:.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}"
            )

            logger.info(
                f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}"
            )
            time.sleep(config["loop_delay"])

        except Exception as e:
            alert_system.send_alert(
                f"An unhandled error occurred in the main loop: {e}", "ERROR"
            )
            logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
            time.sleep(config["loop_delay"] * 2)  # Longer delay on error


if __name__ == "__main__":
    main()
