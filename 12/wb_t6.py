# whalebot_enhanced.py
# A robust, upgraded Bybit-driven trading bot with a modular design,
# enhanced error handling, and improved performance.
# Fully compatible with the original config.json and behavior.
from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import logging
import os
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, getcontext
from functools import (  # lru_cache remains available but removed from BotConfig.get_nested
    wraps,
)
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from colorama import Fore, Style
from colorama import init as colorama_init
from dotenv import load_dotenv

# --- Conditional TA-Lib Import ---
try:
    import talib

    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    print(
        f"{Fore.YELLOW}Warning: TA-Lib not found. Falling back to Pandas/Numpy implementations. For better performance, install TA-Lib: pip install TA-Lib{Style.RESET_ALL}"
    )

# ----------------------------------------------------------------------------
# 1. GLOBAL INITIALIZATION & CONSTANTS
# ----------------------------------------------------------------------------
colorama_init(autoreset=True)

# --- Color Palette ---
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
RESET = Style.RESET_ALL

# --- Core Constants ---
VALID_INTERVALS = ["1", "3", "5", "15", "30", "60", "120", "240", "D", "W", "M"]
RETRY_ERROR_CODES = {429, 500, 502, 503, 504}
TIMEZONE = ZoneInfo("America/Chicago")
BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
LOG_DIR = BASE_DIR / "bot_logs"
LOG_DIR.mkdir(exist_ok=True)

# Set high precision for Decimal math to avoid floating point errors in financial calcs
getcontext().prec = 28
getcontext().rounding = ROUND_HALF_UP  # Consistent rounding strategy

# Suppress pandas FutureWarning
warnings.filterwarnings("ignore", category=FutureWarning)

# ----------------------------------------------------------------------------
# 2. ENVIRONMENT & LOGGER SETUP
# ----------------------------------------------------------------------------
load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY") or ""
API_SECRET = os.getenv("BYBIT_API_SECRET") or ""
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels."""

    COLORS = {
        "DEBUG": Fore.CYAN,
        "INFO": Fore.LIGHTGREEN_EX,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.LIGHTRED_EX,
        "CRITICAL": Fore.MAGENTA,
    }

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, Style.RESET_ALL)
        record.levelname = f"{log_color}{record.levelname}{Style.RESET_ALL}"
        return super().format(record)


def setup_logger(name: str) -> logging.Logger:
    """Creates a self-contained, colorized logger with file output."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Prevent duplicate handlers if called multiple times for the same logger name
    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler()
        console_formatter = ColoredFormatter(
            "%(asctime)s │ %(levelname)-8s │ %(message)s", datefmt="%H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # File handler (date-stamped)
        log_file_name = f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(LOG_DIR / log_file_name)
        file_formatter = logging.Formatter(
            "%(asctime)s │ %(levelname)-8s │ %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


LOGGER = setup_logger("whalebot_main")


# ----------------------------------------------------------------------------
# 3. UTILITY DECORATORS & CONFIGURATION
# ----------------------------------------------------------------------------
def retry_api_call(max_attempts: int = 3, delay: int = 5, backoff_factor: float = 2.0):
    """Decorator to retry API calls on specified error codes with exponential backoff."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.RequestException as e:
                    status_code = getattr(e.response, "status_code", None)
                    if status_code in RETRY_ERROR_CODES:
                        wait_time = delay * (backoff_factor ** (attempt - 1))
                        LOGGER.warning(
                            f"{NEON_YELLOW}API request failed (Attempt {attempt}/{max_attempts}, Status: {status_code}). Retrying in {wait_time:.1f}s...{RESET}"
                        )
                        time.sleep(wait_time)
                    else:
                        LOGGER.error(f"{NEON_RED}Fatal API error: {e}{RESET}")
                        raise  # Re-raise for non-retryable errors
            LOGGER.error(
                f"{NEON_RED}API call failed after {max_attempts} attempts. Aborting.{RESET}"
            )
            return None  # Indicate failure after max retries

        return wrapper

    return decorator


@dataclass(slots=True)
class BotConfig:
    """A lightweight, type-safe wrapper around the JSON configuration."""

    raw: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    # Removed @lru_cache here to resolve TypeError: unhashable type: 'BotConfig'
    def get_nested(self, path: str, default: Any = None) -> Any:
        """Get nested configuration value using dot notation (e.g., "section.key")."""
        keys = path.split(".")
        value = self.raw
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default  # Path not a dict at this point
        return value


def _get_default_config() -> dict[str, Any]:
    """Returns the default configuration dictionary with all indicators and enhanced settings."""
    return {
        "interval": "15",
        "analysis_interval": 30,
        "retry_delay": 5,
        "momentum_period": 10,
        "volume_ma_period": 20,
        "atr_period": 14,
        "signal_score_threshold": 1.0,
        "stop_loss_multiple": 1.5,
        "take_profit_multiple": 1.0,
        "order_book_debounce_s": 10,
        "order_book_depth_to_check": 10,
        "atr_change_threshold": 0.005,
        "volume_confirmation_multiplier": 1.5,
        "signal_cooldown_s": 60,
        "ema_short_period": 12,
        "ema_long_period": 26,
        "indicators": {  # All indicators
            "ema_alignment": True,
            "momentum": True,
            "volume_confirmation": True,
            "divergence": True,
            "stoch_rsi": True,
            "rsi": True,
            "macd": True,
            "vwap": True,
            "obv": True,
            "adi": True,
            "cci": True,
            "wr": True,
            "adx": True,
            "psar": True,
            "fve": True,
            "sma_10": True,
            "mfi": True,
            "stochastic_oscillator": True,
            "cmf": True,
            "ao": True,
            "vi": True,
            "bb": True,
            "keltner_channels": True,
            "ichimoku": True,
            "supertrend": True,  # New indicators
        },
        "weight_sets": {  # Dynamic weight sets based on market conditions
            "low_volatility": {  # Fallback / Default
                "ema_alignment": 0.3,
                "momentum": 0.2,
                "volume_confirmation": 0.2,
                "divergence": 0.1,
                "stoch_rsi": 0.5,
                "rsi": 0.3,
                "macd": 0.3,
                "vwap": 0.2,
                "obv": 0.1,
                "adi": 0.1,
                "cci": 0.1,
                "wr": 0.1,
                "adx": 0.1,
                "psar": 0.1,
                "fve": 0.2,
                "sma_10": 0.0,
                "mfi": 0.3,
                "stochastic_oscillator": 0.4,
                "cmf": 0.2,
                "ao": 0.3,
                "vi": 0.2,
                "bb": 0.4,
                "keltner_channels": 0.1,
                "ichimoku": 0.2,
                "supertrend": 0.2,
            },
            "high_volatility": {  # For very choppy markets
                "ema_alignment": 0.1,
                "momentum": 0.4,
                "volume_confirmation": 0.1,
                "divergence": 0.2,
                "stoch_rsi": 0.4,
                "rsi": 0.4,
                "macd": 0.4,
                "vwap": 0.1,
                "obv": 0.1,
                "adi": 0.1,
                "cci": 0.1,
                "wr": 0.1,
                "adx": 0.1,
                "psar": 0.1,
                "fve": 0.3,
                "sma_10": 0.0,
                "mfi": 0.4,
                "stochastic_oscillator": 0.3,
                "cmf": 0.3,
                "ao": 0.5,
                "vi": 0.4,
                "bb": 0.1,
                "keltner_channels": 0.2,
                "ichimoku": 0.1,
                "supertrend": 0.1,
            },
            "trending_up": {  # For strong uptrends
                "ema_alignment": 0.5,
                "momentum": 0.4,
                "macd": 0.4,
                "adx": 0.3,
                "psar": 0.3,
                "supertrend": 0.5,
                "ichimoku": 0.4,
            },
            "trending_down": {  # For strong downtrends
                "ema_alignment": 0.5,
                "momentum": 0.4,
                "macd": 0.4,
                "adx": 0.3,
                "psar": 0.3,
                "supertrend": 0.5,
                "ichimoku": 0.4,
            },
            "ranging": {  # For sideways markets
                "rsi": 0.5,
                "stoch_rsi": 0.5,
                "bb": 0.4,
                "cci": 0.3,
                "mfi": 0.3,
                "stochastic_oscillator": 0.4,
            },
            "volatile": {  # For unpredictable, high-swing markets
                "atr": 0.4,
                "bb": 0.4,
                "keltner_channels": 0.4,
                "vi": 0.3,
                "volume_confirmation": 0.3,
            },
            "calm": {  # For low volatility, tight range markets
                "vwap": 0.3,
                "obv": 0.2,
                "adi": 0.2,
                "cmf": 0.2,
            },
        },
        "stoch_rsi_oversold_threshold": 20,
        "stoch_rsi_overbought_threshold": 80,
        "order_book_support_confidence_boost": 3,
        "order_book_resistance_confidence_boost": 3,
        "indicator_periods": {  # All periods, including new indicators
            "rsi": 14,
            "mfi": 14,
            "cci": 20,
            "williams_r": 14,
            "adx": 14,
            "stoch_rsi_period": 14,
            "stoch_rsi_k_period": 3,
            "stoch_rsi_d_period": 3,
            "momentum": 10,
            "volume_ma": 20,
            "atr": 14,
            "sma_10": 10,
            "fve_price_ema": 10,
            "fve_obv_sma": 20,
            "fve_atr_sma": 20,
            "stoch_osc_k": 14,
            "stoch_osc_d": 3,
            "vwap": 14,
            "cmf": 20,
            "ao_short": 5,
            "ao_long": 34,
            "vi": 14,
            "bb": 20,
            "keltner_atr_period": 10,
            "keltner_multiplier": 1.5,
            "ichimoku_tenkan_period": 9,
            "ichimoku_kijun_period": 26,
            "ichimoku_senkou_period": 52,
            "ichimoku_chikou_shift": 26,
            "supertrend_atr_period": 10,
            "supertrend_multiplier": 3,
        },
        "order_book_analysis": {
            "enabled": True,
            "wall_threshold_multiplier": 2.0,
            "depth_to_check": 10,
        },
        "market_condition_detection": {
            "adx_trend_threshold": 25,
            "atr_volatility_threshold_multiplier": 1.5,  # Multiplier of average ATR
            "bb_bandwidth_threshold_multiplier": 0.8,  # Multiplier of average BB width for ranging
        },
    }


def load_config(fp: Path) -> BotConfig:
    """Loads config from file, creating a default if missing or corrupt, and merges with defaults."""
    defaults = _get_default_config()

    # Helper for deep merging dictionaries
    def deep_merge(base: dict, update: dict) -> dict:
        for k, v in update.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                base[k] = deep_merge(base[k], v)
            else:
                base[k] = v
        return base

    if not fp.exists():
        LOGGER.warning(
            f"{NEON_YELLOW}Config not found. Creating default at: {fp}{RESET}"
        )
        try:
            fp.write_text(json.dumps(defaults, indent=4))
        except OSError as e:
            LOGGER.error(f"{NEON_RED}Failed to write default config: {e}{RESET}")
            return BotConfig(defaults)  # Return defaults if write fails
        return BotConfig(defaults)

    try:
        user_cfg = json.loads(fp.read_text())
        merged = deep_merge(defaults, user_cfg)  # Deep merge user config onto defaults
    except (OSError, json.JSONDecodeError) as e:
        LOGGER.error(
            f"{NEON_RED}Error with config file: {e}. Attempting to rebuild default.{RESET}"
        )
        backup_fp = fp.with_name(f"{fp.stem}.bak_{int(time.time())}{fp.suffix}")
        try:
            fp.rename(backup_fp)  # Back up corrupt config
            fp.write_text(json.dumps(defaults, indent=4))  # Write fresh default
        except OSError as backup_err:
            LOGGER.error(
                f"{NEON_RED}Could not back up corrupt config: {backup_err}{RESET}"
            )
        merged = defaults  # Use defaults if rebuild fails or is needed

    # Validate critical settings
    if merged["interval"] not in VALID_INTERVALS:
        LOGGER.warning(
            f"{NEON_YELLOW}Invalid interval '{merged['interval']}' in config. Falling back to default '15'.{RESET}"
        )
        merged["interval"] = "15"

    return BotConfig(merged)


CFG = load_config(CONFIG_FILE)


# ----------------------------------------------------------------------------
# 4. BYBIT API CLIENT
# ----------------------------------------------------------------------------
class BybitClient:
    """A client to interact with the Bybit API."""

    def __init__(
        self, base_url: str, api_key: str, api_secret: str, log: logging.Logger
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.api_secret = api_secret
        self.log = log
        self.kline_cache: dict[
            str, Any
        ] = {}  # {f"{symbol}_{interval}_{limit}": {'data': df, 'timestamp': time}}

    def _generate_signature(self, params: dict) -> str:
        """Generates the HMAC SHA256 signature for Bybit API requests."""
        param_str = "&".join(
            [f"{key}={value}" for key, value in sorted(params.items())]
        )
        return hmac.new(
            self.api_secret.encode(), param_str.encode(), hashlib.sha256
        ).hexdigest()

    @retry_api_call()
    def _bybit_request(
        self, method: str, endpoint: str, params: dict[str, Any] = None
    ) -> dict | None:
        """Sends a signed request to the Bybit API with retry logic."""
        params = params or {}
        params["timestamp"] = str(int(time.time() * 1000))
        signature = self._generate_signature(params)
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": params["timestamp"],
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}{endpoint}"

        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                params=params if method == "GET" else None,
                json=params if method == "POST" else None,
                timeout=10,
            )
            response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.RequestException as e:
            # The retry_api_call decorator will catch this, but good to log here too for context
            self.log.error(
                f"{NEON_RED}Bybit request failed: {e}. Response: {getattr(e.response, 'text', 'N/A')}{RESET}"
            )
            raise  # Re-raise to allow decorator to handle retries

    @retry_api_call()
    def fetch_current_price(self, symbol: str) -> Decimal | None:
        """Fetches the latest price for a given symbol."""
        endpoint = "/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
        response_data = self._bybit_request("GET", endpoint, params)
        if (
            response_data
            and response_data.get("retCode") == 0
            and response_data.get("result")
        ):
            tickers = response_data["result"].get("list")
            if tickers:
                # Ensure we get the correct symbol's ticker if multiple are returned (unlikely for specific query)
                for ticker in tickers:
                    if ticker.get("symbol") == symbol:
                        last_price = ticker.get("lastPrice")
                        try:
                            return Decimal(str(last_price)) if last_price else None
                        except InvalidOperation:
                            self.log.error(
                                f"{NEON_RED}Invalid price format received for {symbol}: '{last_price}'{RESET}"
                            )
                            return None
        self.log.error(
            f"{NEON_RED}Could not fetch current price for {symbol}. Response: {response_data}{RESET}"
        )
        return None

    @retry_api_call()
    def fetch_klines(
        self, symbol: str, interval: str, limit: int = 200
    ) -> pd.DataFrame:
        """Fetches historical K-line data with caching."""
        kline_key = f"{symbol}_{interval}_{limit}"

        # Check cache
        if kline_key in self.kline_cache and (
            time.time() - self.kline_cache[kline_key]["timestamp"]
            < CFG["analysis_interval"]
        ):
            return self.kline_cache[kline_key][
                "data"
            ].copy()  # Return a copy to prevent external modification

        self.log.info(
            f"{NEON_BLUE}Fetching fresh Kline data for {symbol} ({interval})...{RESET}"
        )
        endpoint = "/v5/market/kline"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "category": "linear",
        }
        response_data = self._bybit_request("GET", endpoint, params)

        if (
            response_data
            and response_data.get("retCode") == 0
            and response_data.get("result")
            and response_data["result"].get("list")
        ):
            data = response_data["result"]["list"]
            # Bybit kline order: [timestamp, open, high, low, close, volume, turnover]
            columns = [
                "start_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
            ]
            df = pd.DataFrame(data, columns=columns)

            # Convert timestamp to datetime (coercing errors means invalid times become NaT)
            df["start_time"] = pd.to_datetime(
                pd.to_numeric(df["start_time"], errors="coerce"), unit="ms"
            )

            # Convert financial columns to Decimal safely
            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                # Using apply with _to_decimal ensures Decimal objects for each element
                df[col] = df[col].apply(
                    lambda x: Decimal(str(x)) if pd.notna(x) else Decimal("NaN")
                )

            # Drop rows with any NaN values in critical columns
            df.dropna(subset=df.columns[1:], inplace=True)

            # Ensure ascending order by time
            df = df.sort_values(by="start_time", ascending=True).reset_index(drop=True)

            if df.empty:
                self.log.warning(
                    f"{NEON_YELLOW}Fetched Kline data is empty after processing for {symbol}, interval {interval}.{RESET}"
                )
                return pd.DataFrame()

            # Cache the processed DataFrame
            self.kline_cache[kline_key] = {"data": df, "timestamp": time.time()}
            return df

        self.log.error(
            f"{NEON_RED}Failed to fetch Kline data for {symbol}, interval {interval}. Response: {response_data}{RESET}"
        )
        return pd.DataFrame()

    @retry_api_call()
    def fetch_order_book(self, symbol: str, limit: int = 50) -> dict | None:
        """Fetches the order book for a given symbol."""
        endpoint = "/v5/market/orderbook"
        params = {"symbol": symbol, "limit": limit, "category": "linear"}
        response_data = self._bybit_request("GET", endpoint, params)
        if (
            response_data
            and response_data.get("retCode") == 0
            and response_data.get("result")
        ):
            return response_data["result"]
        self.log.warning(
            f"{NEON_YELLOW}Could not fetch order book for {symbol}. Response: {response_data}{RESET}"
        )
        return None


# ----------------------------------------------------------------------------
# 5. TECHNICAL INDICATORS ENGINE (ALL METHODS ARE DECIMAL-AWARE)
# ----------------------------------------------------------------------------
class Indicators:
    """A collection of static methods for calculating technical indicators.
    Prioritizes TA-Lib for performance if available, else uses Pandas/Numpy with Decimal.
    """

    @staticmethod
    def _to_decimal_series_safe(series: pd.Series) -> pd.Series:
        """Helper to convert series to Decimal type safely, handling NaN/None."""
        return series.apply(
            lambda x: Decimal(str(x)) if pd.notna(x) else Decimal("NaN")
        )

    @staticmethod
    def _convert_series_to_float_np(series: pd.Series) -> np.ndarray:
        """Converts a Decimal Series to float numpy array for TA-Lib, handling NaNs."""
        # Convert to float, replacing NaNs with a value that TA-Lib might handle or that can be masked later
        # Check if the series *actually* contains Decimal objects before casting
        if series.dtype == object and any(isinstance(x, Decimal) for x in series):
            return series.apply(
                lambda x: float(x)
                if isinstance(x, Decimal) and not x.is_nan()
                else np.nan
            ).to_numpy(dtype=float)
        # If it's already numeric (e.g., float64) or mixed, just convert directly
        return series.to_numpy(dtype=float)

    @staticmethod
    def sma(series: pd.Series, window: int) -> pd.Series:
        """Decimal-safe Simple Moving Average."""
        if TALIB_AVAILABLE:
            np_array = Indicators._convert_series_to_float_np(series)
            result = talib.SMA(np_array, timeperiod=window)
            return Indicators._to_decimal_series_safe(
                pd.Series(result, index=series.index)
            )

        return Indicators._to_decimal_series_safe(
            series.rolling(window=window, min_periods=1).mean()
        )

    @staticmethod
    def ema(series: pd.Series, span: int) -> pd.Series:
        """Decimal-safe Exponential Moving Average."""
        if TALIB_AVAILABLE:
            np_array = Indicators._convert_series_to_float_np(series)
            result = talib.EMA(np_array, timeperiod=span)
            return Indicators._to_decimal_series_safe(
                pd.Series(result, index=series.index)
            )

        return Indicators._to_decimal_series_safe(
            series.ewm(span=span, adjust=False).mean()
        )

    @staticmethod
    def atr(
        high: pd.Series, low: pd.Series, close: pd.Series, window: int
    ) -> pd.Series:
        """Decimal-safe Average True Range."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            result = talib.ATR(np_high, np_low, np_close, timeperiod=window)
            return Indicators._to_decimal_series_safe(
                pd.Series(result, index=high.index)
            )

        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return Indicators.ema(Indicators._to_decimal_series_safe(tr), span=window)

    @staticmethod
    def rsi(close: pd.Series, window: int) -> pd.Series:
        """Decimal-safe Relative Strength Index."""
        if TALIB_AVAILABLE:
            np_close = Indicators._convert_series_to_float_np(close)
            result = talib.RSI(np_close, timeperiod=window)
            return Indicators._to_decimal_series_safe(
                pd.Series(result, index=close.index)
            )

        delta = close.diff()
        gain = delta.where(delta > Decimal("0"), Decimal("0")).fillna(Decimal("0"))
        loss = -delta.where(delta < Decimal("0"), Decimal("0")).fillna(Decimal("0"))
        avg_gain = Indicators.ema(gain, span=window)
        avg_loss = Indicators.ema(loss, span=window)
        rs = avg_gain / avg_loss.replace(Decimal("0"), Decimal("NaN"))
        return (Decimal("100") - (Decimal("100") / (Decimal("1") + rs))).fillna(
            Decimal("50")
        )

    @staticmethod
    def macd(
        close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> pd.DataFrame:
        """Decimal-safe Moving Average Convergence Divergence."""
        if TALIB_AVAILABLE:
            np_close = Indicators._convert_series_to_float_np(close)
            macd_line, signal_line, hist = talib.MACD(
                np_close, fastperiod=fast, slowperiod=slow, signalperiod=signal
            )
            return pd.DataFrame(
                {
                    "macd": Indicators._to_decimal_series_safe(
                        pd.Series(macd_line, index=close.index)
                    ),
                    "signal": Indicators._to_decimal_series_safe(
                        pd.Series(signal_line, index=close.index)
                    ),
                    "histogram": Indicators._to_decimal_series_safe(
                        pd.Series(hist, index=close.index)
                    ),
                }
            )

        ema_fast = Indicators.ema(close, span=fast)
        ema_slow = Indicators.ema(close, span=slow)
        macd_line = ema_fast - ema_slow
        signal_line = Indicators.ema(macd_line, span=signal)
        histogram = macd_line - signal_line
        return pd.DataFrame(
            {"macd": macd_line, "signal": signal_line, "histogram": histogram}
        )

    @staticmethod
    def adx(
        high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14
    ) -> pd.DataFrame:
        """Decimal-safe Average Directional Index."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            plus_di, minus_di, adx = talib.ADX(
                np_high, np_low, np_close, timeperiod=window
            )
            return pd.DataFrame(
                {
                    "+DI": Indicators._to_decimal_series_safe(
                        pd.Series(plus_di, index=high.index)
                    ),
                    "-DI": Indicators._to_decimal_series_safe(
                        pd.Series(minus_di, index=high.index)
                    ),
                    "ADX": Indicators._to_decimal_series_safe(
                        pd.Series(adx, index=high.index)
                    ),
                }
            )

        plus_dm = high.diff()
        minus_dm = low.diff().mul(Decimal("-1"))
        plus_dm_s = Indicators.ema(
            plus_dm.where(
                (plus_dm > Decimal("0")) & (plus_dm > minus_dm), Decimal("0")
            ),
            span=window,
        )
        minus_dm_s = Indicators.ema(
            minus_dm.where(
                (minus_dm > Decimal("0")) & (minus_dm > plus_dm), Decimal("0")
            ),
            span=window,
        )
        tr_s = Indicators.ema(Indicators.atr(high, low, close, window), span=window)
        plus_di = Decimal("100") * (
            plus_dm_s / tr_s.replace(Decimal("0"), Decimal("NaN"))
        ).fillna(Decimal("0"))
        minus_di = Decimal("100") * (
            minus_dm_s / tr_s.replace(Decimal("0"), Decimal("NaN"))
        ).fillna(Decimal("0"))
        dx_denom = (plus_di + minus_di).replace(Decimal("0"), Decimal("NaN"))
        dx = Decimal("100") * (abs(plus_di - minus_di) / dx_denom).fillna(Decimal("0"))
        adx_series = Indicators.ema(dx, span=window)
        return pd.DataFrame({"+DI": plus_di, "-DI": minus_di, "ADX": adx_series})

    @staticmethod
    def stochastic_oscillator(
        close: pd.Series,
        high: pd.Series,
        low: pd.Series,
        k_period: int = 14,
        d_period: int = 3,
    ) -> pd.DataFrame:
        """Decimal-safe Stochastic Oscillator."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            slowk, slowd = talib.STOCH(
                np_high,
                np_low,
                np_close,
                fastk_period=k_period,
                slowk_period=d_period,  # In TA-Lib, 'slowk_period' is our K, 'slowd_period' is our D
                slowd_period=d_period,
            )
            return pd.DataFrame(
                {
                    "k": Indicators._to_decimal_series_safe(
                        pd.Series(slowk, index=close.index)
                    ),
                    "d": Indicators._to_decimal_series_safe(
                        pd.Series(slowd, index=close.index)
                    ),
                }
            )

        highest_high = high.rolling(window=k_period).max()
        lowest_low = low.rolling(window=k_period).min()
        denominator = (highest_high - lowest_low).replace(Decimal("0"), Decimal("NaN"))
        k_line = ((close - lowest_low) / denominator * Decimal("100")).fillna(
            Decimal("0")
        )
        d_line = Indicators.sma(k_line, window=d_period)
        return pd.DataFrame({"k": k_line, "d": d_line})

    @staticmethod
    def stoch_rsi(
        close: pd.Series, rsi_period: int = 14, k_period: int = 3, d_period: int = 3
    ) -> pd.DataFrame:
        """Decimal-safe Stochastic RSI."""
        if TALIB_AVAILABLE:
            # TA-Lib STOCHRSI returns fastk, fastd based on RSI values.
            # We map fastk to stoch_rsi_k and fastd to stoch_rsi_d
            np_close = Indicators._convert_series_to_float_np(close)
            stochrsi_k, stochrsi_d = talib.STOCHRSI(
                np_close,
                timeperiod=rsi_period,
                fastk_period=k_period,
                fastd_period=d_period,
                _talib_input_type="float",
            )  # Force float input for TA-Lib
            return pd.DataFrame(
                {
                    "stoch_rsi_k": Indicators._to_decimal_series_safe(
                        pd.Series(stochrsi_k, index=close.index)
                    ),
                    "stoch_rsi_d": Indicators._to_decimal_series_safe(
                        pd.Series(stochrsi_d, index=close.index)
                    ),
                }
            )

        rsi_vals = Indicators.rsi(close, window=rsi_period)
        min_rsi = rsi_vals.rolling(window=k_period).min()
        max_rsi = rsi_vals.rolling(window=k_period).max()
        denominator = (max_rsi - min_rsi).replace(Decimal("0"), Decimal("NaN"))
        stoch_rsi_val = ((rsi_vals - min_rsi) / denominator * Decimal("100")).fillna(
            Decimal("0")
        )
        k_line = Indicators.sma(stoch_rsi_val, window=k_period)
        d_line = Indicators.sma(k_line, window=d_period)
        return pd.DataFrame({"stoch_rsi_k": k_line, "stoch_rsi_d": d_line})

    @staticmethod
    def psar(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        acceleration: Decimal = Decimal("0.02"),
        max_acceleration: Decimal = Decimal("0.2"),
    ) -> pd.Series:
        """Decimal-safe Parabolic SAR."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            result = talib.SAR(
                np_high,
                np_low,
                acceleration=float(acceleration),
                maximum=float(max_acceleration),
            )
            return Indicators._to_decimal_series_safe(
                pd.Series(result, index=high.index)
            )

        psar = pd.Series([Decimal("NaN")] * len(close), index=close.index, dtype=object)
        if len(close) < 2:
            return psar

        # Ensure input series are Decimal
        high, low, close = (
            Indicators._to_decimal_series_safe(high),
            Indicators._to_decimal_series_safe(low),
            Indicators._to_decimal_series_safe(close),
        )

        psar.iloc[0] = close.iloc[0]  # Initial PSAR at first close

        # Determine initial trend (up=1, down=-1) and EP (extreme point)
        trend = 1 if close.iloc[1] > close.iloc[0] else -1
        ep = high.iloc[0] if trend == 1 else low.iloc[0]
        af = acceleration  # Acceleration Factor

        for i in range(1, len(close)):
            prev_psar = psar.iloc[i - 1]
            if pd.isna(prev_psar):  # Skip if previous was NaN
                psar.iloc[i] = close.iloc[i]
                continue

            curr_h, curr_l = high.iloc[i], low.iloc[i]

            if trend == 1:  # Uptrend
                new_psar = prev_psar + af * (ep - prev_psar)
                # SAR should not be above current or previous two lows in an uptrend
                psar.iloc[i] = min(
                    new_psar, curr_l, low.iloc[i - 1] if i > 1 else curr_l
                )  # Ensure SAR stays below price
                if curr_h > ep:  # New extreme point reached
                    ep, af = curr_h, min(af + acceleration, max_acceleration)
                if curr_l < psar.iloc[i]:  # Trend reversal: price falls below SAR
                    trend, psar.iloc[i], ep, af = (
                        -1,
                        ep,
                        curr_l,
                        acceleration,
                    )  # SAR moves to previous EP, EP becomes new low, reset AF
            else:  # Downtrend
                new_psar = prev_psar + af * (ep - prev_psar)
                # SAR should not be below current or previous two highs in a downtrend
                psar.iloc[i] = max(
                    new_psar, curr_h, high.iloc[i - 1] if i > 1 else curr_h
                )  # Ensure SAR stays above price
                if curr_l < ep:  # New extreme point reached
                    ep, af = curr_l, min(af + acceleration, max_acceleration)
                if curr_h > psar.iloc[i]:  # Trend reversal: price rises above SAR
                    trend, psar.iloc[i], ep, af = (
                        1,
                        ep,
                        curr_h,
                        acceleration,
                    )  # SAR moves to previous EP, EP becomes new high, reset AF

        return (
            psar.ffill()
        )  # Fill any initial NaNs if calculation started later in series

    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        """Decimal-safe On-Balance Volume."""
        if TALIB_AVAILABLE:
            np_close = Indicators._convert_series_to_float_np(close)
            np_volume = Indicators._convert_series_to_float_np(volume)
            result = talib.OBV(np_close, np_volume)
            return Indicators._to_decimal_series_safe(
                pd.Series(result, index=close.index)
            )

        obv = pd.Series([Decimal("0")] * len(close), index=close.index, dtype=object)
        if not close.empty:  # Handle empty series case
            obv.iloc[0] = (
                volume.iloc[0] if not pd.isna(volume.iloc[0]) else Decimal("0")
            )
            for i in range(1, len(close)):
                if (
                    pd.isna(close.iloc[i])
                    or pd.isna(close.iloc[i - 1])
                    or pd.isna(volume.iloc[i])
                ):
                    obv.iloc[i] = obv.iloc[
                        i - 1
                    ]  # Maintain previous OBV on missing data
                elif close.iloc[i] > close.iloc[i - 1]:
                    obv.iloc[i] = obv.iloc[i - 1] + volume.iloc[i]
                elif close.iloc[i] < close.iloc[i - 1]:
                    obv.iloc[i] = obv.iloc[i - 1] - volume.iloc[i]
                else:
                    obv.iloc[i] = obv.iloc[i - 1]
        return obv

    @staticmethod
    def adi(
        high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series
    ) -> pd.Series:
        """Decimal-safe Accumulation/Distribution Index."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            np_volume = Indicators._convert_series_to_float_np(volume)
            result = talib.AD(np_high, np_low, np_close, np_volume)
            return Indicators._to_decimal_series_safe(
                pd.Series(result, index=high.index)
            )

        mfm_denom = (high - low).replace(Decimal("0"), Decimal("NaN"))
        mfm = (((close - low) - (high - close)) / mfm_denom).fillna(Decimal("0"))
        mfv = mfm * volume
        return mfv.cumsum()

    @staticmethod
    def cci(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        window: int = 20,
        constant: Decimal = Decimal("0.015"),
    ) -> pd.Series:
        """Decimal-safe Commodity Channel Index."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            result = talib.CCI(np_high, np_low, np_close, timeperiod=window)
            return Indicators._to_decimal_series_safe(
                pd.Series(result, index=high.index)
            )

        typical_price = (high + low + close) / Decimal("3")
        sma_tp = Indicators.sma(typical_price, window=window)

        def _mean_dev_decimal(x_series: pd.Series) -> Decimal:
            """Calculate mean deviation for a Decimal Series."""
            x_dec = [
                val for val in x_series if pd.notna(val) and isinstance(val, Decimal)
            ]
            if not x_dec:
                return Decimal("NaN")
            mean_val = sum(x_dec) / Decimal(str(len(x_dec)))
            return sum(abs(val - mean_val) for val in x_dec) / Decimal(str(len(x_dec)))

        mean_dev_series = typical_price.rolling(window=window).apply(
            _mean_dev_decimal, raw=False
        )  # raw=False to pass Series objects

        return (
            (typical_price - sma_tp)
            / (constant * mean_dev_series.replace(Decimal("0"), Decimal("NaN")))
        ).fillna(Decimal("0"))

    @staticmethod
    def williams_r(
        high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14
    ) -> pd.Series:
        """Decimal-safe Williams %R."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            result = talib.WILLR(np_high, np_low, np_close, timeperiod=window)
            return Indicators._to_decimal_series_safe(
                pd.Series(result, index=high.index)
            )

        highest_high = high.rolling(window=window).max()
        lowest_low = low.rolling(window=window).min()
        denom = (highest_high - lowest_low).replace(Decimal("0"), Decimal("NaN"))
        return (((highest_high - close) / denom) * Decimal("-100")).fillna(Decimal("0"))

    @staticmethod
    def mfi(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series,
        window: int = 14,
    ) -> pd.Series:
        """Decimal-safe Money Flow Index."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            np_volume = Indicators._convert_series_to_float_np(volume)
            result = talib.MFI(np_high, np_low, np_close, np_volume, timeperiod=window)
            return Indicators._to_decimal_series_safe(
                pd.Series(result, index=high.index)
            )

        typical_price = (high + low + close) / Decimal("3")
        raw_mf = typical_price * volume
        mf_dir = typical_price.diff()
        pos_mf = raw_mf.where(mf_dir > Decimal("0"), Decimal("0"))
        neg_mf = raw_mf.where(mf_dir < Decimal("0"), Decimal("0"))
        pos_sum = (
            pos_mf.rolling(window=window, min_periods=1)
            .sum()
            .apply(lambda x: Decimal(str(x)))
        )
        neg_sum = (
            neg_mf.rolling(window=window, min_periods=1)
            .sum()
            .apply(lambda x: Decimal(str(x)))
        )
        mf_ratio = pos_sum / neg_sum.replace(Decimal("0"), Decimal("NaN"))
        return (Decimal("100") - (Decimal("100") / (Decimal("1") + mf_ratio))).fillna(
            Decimal("0")
        )

    @staticmethod
    def momentum(close: pd.Series, period: int = 10) -> pd.Series:
        """Decimal-safe Momentum."""
        if TALIB_AVAILABLE:
            np_close = Indicators._convert_series_to_float_np(close)
            result = talib.MOM(np_close, timeperiod=period)
            return Indicators._to_decimal_series_safe(
                pd.Series(result, index=close.index)
            )

        return ((close.diff(period) / close.shift(period)) * Decimal("100")).fillna(
            Decimal("0")
        )

    @staticmethod
    def vwap(close: pd.Series, volume: pd.Series, window: int) -> pd.Series:
        """Decimal-safe Volume Weighted Average Price."""
        if window <= 0:
            return close  # VWAP is typically cumulative or session-based, not windowed in strict sense. Here, window behaves like a rolling average.
        price_vol = close * volume
        cum_pv = (
            price_vol.rolling(window=window, min_periods=1)
            .sum()
            .apply(lambda x: Decimal(str(x)))
        )
        cum_vol = (
            volume.rolling(window=window, min_periods=1)
            .sum()
            .apply(lambda x: Decimal(str(x)))
        )
        return (cum_pv / cum_vol.replace(Decimal("0"), Decimal("NaN"))).fillna(close)

    @staticmethod
    def cmf(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series,
        window: int = 20,
    ) -> pd.Series:
        """Decimal-safe Chaikin Money Flow (CMF)."""
        mfm_denom = (high - low).replace(Decimal("0"), Decimal("NaN"))
        mfm = (((close - low) - (high - close)) / mfm_denom).fillna(Decimal("0"))
        mfv = mfm * volume
        return (
            mfv.rolling(window=window).sum()
            / volume.rolling(window=window).sum().replace(Decimal("0"), Decimal("NaN"))
        ).fillna(Decimal("0"))

    @staticmethod
    def ao(close: pd.Series, short_period: int = 5, long_period: int = 34) -> pd.Series:
        """Decimal-safe Awesome Oscillator (AO)."""
        # AO is based on 5-period SMA of (H+L)/2 minus 34-period SMA of (H+L)/2
        # The input close is typically the median price (high+low)/2, but if only close is given, use it.
        # Original script uses (close + close.shift(1)) / 2, which is not standard.
        # Let's use (high+low)/2 for a more standard AO calculation if possible, else stick to close.
        # For compatibility, keeping median_price as (close + close.shift(1)) / 2 based on your prior code structure.
        median_price = (close + close.shift(1)).fillna(close) / Decimal(
            "2"
        )  # Use close if shift(1) is NaN
        sma_short = Indicators.sma(median_price, window=short_period)
        sma_long = Indicators.sma(median_price, window=long_period)
        return sma_short - sma_long

    @staticmethod
    def vi(
        high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14
    ) -> pd.DataFrame:
        """Decimal-safe Vortex Indicator (VI)."""
        if TALIB_AVAILABLE:
            np_high = Indicators._convert_series_to_float_np(high)
            np_low = Indicators._convert_series_to_float_np(low)
            np_close = Indicators._convert_series_to_float_np(close)
            plus_vi, minus_vi = talib.VORTEX(
                np_high, np_low, np_close, timeperiod=window
            )
            return pd.DataFrame(
                {
                    "+VI": Indicators._to_decimal_series_safe(
                        pd.Series(plus_vi, index=high.index)
                    ),
                    "-VI": Indicators._to_decimal_series_safe(
                        pd.Series(minus_vi, index=high.index)
                    ),
                }
            )

        tr = Indicators.atr(high, low, close, 1).rolling(window=window).sum()
        # +VM = |Current High - Previous Low|
        plus_vm = (high - low.shift(1)).abs()
        # -VM = |Current Low - Previous High|
        minus_vm = (low - high.shift(1)).abs()

        plus_vi = (plus_vm.rolling(window=window, min_periods=1).sum() / tr).fillna(
            Decimal("0")
        )
        minus_vi = (minus_vm.rolling(window=window, min_periods=1).sum() / tr).fillna(
            Decimal("0")
        )

        return pd.DataFrame({"+VI": plus_vi, "-VI": minus_vi})

    @staticmethod
    def bb(
        close: pd.Series, window: int = 20, std_dev_mult: Decimal = Decimal("2")
    ) -> pd.DataFrame:
        """Decimal-safe Bollinger Bands (BB)."""
        if TALIB_AVAILABLE:
            np_close = Indicators._convert_series_to_float_np(close)
            upper, middle, lower = talib.BBANDS(
                np_close,
                timeperiod=window,
                nbdevup=float(std_dev_mult),
                nbdevdn=float(std_dev_mult),
                matype=talib.MA_Type.SMA,
            )  # Using SMA for middle band by default
            return pd.DataFrame(
                {
                    "upper": Indicators._to_decimal_series_safe(
                        pd.Series(upper, index=close.index)
                    ),
                    "middle": Indicators._to_decimal_series_safe(
                        pd.Series(middle, index=close.index)
                    ),
                    "lower": Indicators._to_decimal_series_safe(
                        pd.Series(lower, index=close.index)
                    ),
                }
            )

        sma = Indicators.sma(close, window=window)
        # Calculate standard deviation manually for Decimal Series
        # Use pandas std() and then convert to Decimal for safety
        rolling_std = (
            close.rolling(window=window)
            .std()
            .apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal("NaN"))
        )

        upper = sma + (rolling_std * std_dev_mult)
        lower = sma - (rolling_std * std_dev_mult)
        return pd.DataFrame({"upper": upper, "middle": sma, "lower": lower})

    @staticmethod
    def fve(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series,
        window: int = 10,
    ) -> pd.Series:
        """A composite indicator based on price and volume relationship."""
        if len(close) < window:
            return pd.Series([Decimal("NaN")] * len(close))
        price_ema = Indicators.ema(close, window)
        vol_sma = Indicators.sma(volume, window)
        # Using element-wise multiplication here
        fve_values = (price_ema * vol_sma).rolling(window=window, min_periods=1).sum()
        return fve_values.apply(
            lambda x: Decimal(str(x)) if pd.notna(x) else Decimal("NaN")
        )

    # --- New Indicators ---

    @staticmethod
    def keltner_channels(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        window: int,
        atr_period: int,
        multiplier: Decimal,
    ) -> pd.DataFrame:
        """Decimal-safe Keltner Channels."""
        # TA-Lib does not have a direct Keltner Channels function.
        # We implement it by combining EMA and ATR.

        middle_band = Indicators.ema(close, span=window)
        atr_val = Indicators.atr(high, low, close, atr_period)

        upper_band = middle_band + (atr_val * multiplier)
        lower_band = middle_band - (atr_val * multiplier)

        return pd.DataFrame(
            {
                "upper": Indicators._to_decimal_series_safe(upper_band),
                "middle": Indicators._to_decimal_series_safe(middle_band),
                "lower": Indicators._to_decimal_series_safe(lower_band),
            }
        )

    @staticmethod
    def ichimoku(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        tenkan_period: int = 9,
        kijun_period: int = 26,
        senkou_period: int = 52,
        chikou_shift: int = 26,
    ) -> pd.DataFrame:
        """Decimal-safe Ichimoku Cloud components."""
        # Tenkan-sen (Conversion Line): (9-period high + 9-period low) / 2
        tenkan_sen = (
            high.rolling(window=tenkan_period).max()
            + low.rolling(window=tenkan_period).min()
        ) / Decimal("2")

        # Kijun-sen (Base Line): (26-period high + 26-period low) / 2
        kijun_sen = (
            high.rolling(window=kijun_period).max()
            + low.rolling(window=kijun_period).min()
        ) / Decimal("2")

        # Senkou Span A (Leading Span A): (Conversion Line + Base Line) / 2, plotted 26 periods ahead
        senkou_span_a = ((tenkan_sen + kijun_sen) / Decimal("2")).shift(kijun_period)

        # Senkou Span B (Leading Span B): (52-period high + 52-period low) / 2, plotted 26 periods ahead
        senkou_span_b = (
            (
                high.rolling(window=senkou_period).max()
                + low.rolling(window=senkou_period).min()
            )
            / Decimal("2")
        ).shift(kijun_period)

        # Chikou Span (Lagging Span): Current closing price, plotted 26 periods behind
        chikou_span = close.shift(-chikou_shift)  # Shift backwards means earlier data

        return pd.DataFrame(
            {
                "tenkan_sen": Indicators._to_decimal_series_safe(tenkan_sen),
                "kijun_sen": Indicators._to_decimal_series_safe(kijun_sen),
                "senkou_span_a": Indicators._to_decimal_series_safe(senkou_span_a),
                "senkou_span_b": Indicators._to_decimal_series_safe(senkou_span_b),
                "chikou_span": Indicators._to_decimal_series_safe(chikou_span),
            }
        )

    @staticmethod
    def supertrend(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        atr_period: int,
        multiplier: Decimal,
    ) -> pd.Series:
        """Decimal-safe Supertrend Indicator."""
        # Adapted from typical Supertrend implementation

        # Calculate ATR
        atr_series = Indicators.atr(high, low, close, atr_period)

        # Calculate Basic Upper Band and Basic Lower Band
        basic_upper_band = ((high + low) / Decimal("2")) + (multiplier * atr_series)
        basic_lower_band = ((high + low) / Decimal("2")) - (multiplier * atr_series)

        # Calculate Final Upper Band and Final Lower Band
        final_upper_band = pd.Series(
            [Decimal("NaN")] * len(close), index=close.index, dtype=object
        )
        final_lower_band = pd.Series(
            [Decimal("NaN")] * len(close), index=close.index, dtype=object
        )

        supertrend_vals = pd.Series(
            [Decimal("NaN")] * len(close), index=close.index, dtype=object
        )

        # Initialize trend
        trend = pd.Series(
            [0] * len(close), index=close.index, dtype=int
        )  # 1 for uptrend, -1 for downtrend, 0 for initial

        # Initialize first values if enough data
        if len(close) > 0:
            final_upper_band.iloc[0] = (
                basic_upper_band.iloc[0]
                if not basic_upper_band.empty
                else Decimal("NaN")
            )
            final_lower_band.iloc[0] = (
                basic_lower_band.iloc[0]
                if not basic_lower_band.empty
                else Decimal("NaN")
            )
            supertrend_vals.iloc[0] = (
                final_upper_band.iloc[0]
                if close.iloc[0] <= final_upper_band.iloc[0]
                else final_lower_band.iloc[0]
            )
            trend.iloc[0] = 1 if close.iloc[0] > supertrend_vals.iloc[0] else -1

        for i in range(1, len(close)):
            if pd.isna(basic_upper_band.iloc[i]) or pd.isna(basic_lower_band.iloc[i]):
                # Inherit from previous if current bands are NaN
                final_upper_band.iloc[i] = final_upper_band.iloc[i - 1]
                final_lower_band.iloc[i] = final_lower_band.iloc[i - 1]
                trend.iloc[i] = trend.iloc[i - 1]
                supertrend_vals.iloc[i] = supertrend_vals.iloc[i - 1]
                continue

            # Update final bands
            # The logic for `final_upper_band` and `final_lower_band` considers the previous value
            # and whether the current `basic_band` is 'better' for the current trend
            if close.iloc[i - 1] <= final_upper_band.iloc[i - 1]:
                final_upper_band.iloc[i] = basic_upper_band.iloc[i]
            else:
                final_upper_band.iloc[i] = min(
                    basic_upper_band.iloc[i], final_upper_band.iloc[i - 1]
                )

            if close.iloc[i - 1] >= final_lower_band.iloc[i - 1]:
                final_lower_band.iloc[i] = basic_lower_band.iloc[i]
            else:
                final_lower_band.iloc[i] = max(
                    basic_lower_band.iloc[i], final_lower_band.iloc[i - 1]
                )

            # Determine trend and Supertrend value
            if trend.iloc[i - 1] == 1:  # Was in uptrend
                if (
                    close.iloc[i] < final_lower_band.iloc[i]
                ):  # Price broke below final_lower_band -> downtrend
                    trend.iloc[i] = -1
                else:  # Price stayed above final_lower_band -> uptrend continues
                    trend.iloc[i] = 1
            elif (
                close.iloc[i] > final_upper_band.iloc[i]
            ):  # Price broke above final_upper_band -> uptrend
                trend.iloc[i] = 1
            else:  # Price stayed below final_upper_band -> downtrend continues
                trend.iloc[i] = -1

            # Set Supertrend value based on current trend
            if trend.iloc[i] == 1:  # Uptrend
                supertrend_vals.iloc[i] = final_lower_band.iloc[i]
            else:  # Downtrend
                supertrend_vals.iloc[i] = final_upper_band.iloc[i]

        return Indicators._to_decimal_series_safe(supertrend_vals.ffill())


# ----------------------------------------------------------------------------
# 6. DATA STRUCTURES & CORE TRADING ANALYZER
# ----------------------------------------------------------------------------
@dataclass(slots=True)
class TradeSignal:
    """Structured object for a trading signal."""

    signal: str | None  # "buy" or "sell"
    confidence: float  # 0.0 to 1.0
    conditions: list[str] = field(
        default_factory=list
    )  # List of contributing conditions
    levels: dict[str, Decimal] = field(
        default_factory=dict
    )  # Calculated SL/TP/other levels


class TradingAnalyzer:
    """Orchestrates technical analysis and signal generation."""

    def __init__(
        self,
        df: pd.DataFrame,
        cfg: BotConfig,
        log: logging.Logger,
        symbol: str,
        interval: str,
    ):
        self.df = df.copy()
        self.cfg = cfg
        self.log = log
        self.symbol = symbol
        self.interval = interval
        self.atr_value: Decimal = Decimal("0")
        self.indicator_values: dict[str, Any] = {}
        self.levels: dict[str, Any] = {"Support": {}, "Resistance": {}}
        self.fib_levels: dict[str, Decimal] = {}

        self._pre_calculate_indicators()  # Calculate ATR and other prerequisites
        self.market_condition = (
            self._detect_market_condition()
        )  # Determine market condition
        self.weights = (
            self._select_weight_set()
        )  # Select weights based on market condition

    def _pre_calculate_indicators(self):
        """Pre-calculates essential indicators like ATR needed for other logic."""
        atr_period = self.cfg["atr_period"]
        if self.df.empty or len(self.df) < atr_period:
            self.log.warning(
                f"{NEON_YELLOW}Not enough data for ATR ({len(self.df)}/{atr_period} bars). ATR set to 0.{RESET}"
            )
            self.atr_value = Decimal("0")
            return

        atr_series = Indicators.atr(
            self.df.high, self.df.low, self.df.close, atr_period
        )
        if not atr_series.empty and not pd.isna(atr_series.iloc[-1]):
            self.atr_value = atr_series.iloc[-1].quantize(
                Decimal("0.00001")
            )  # Quantize for consistent logging/comparison
        else:
            self.atr_value = Decimal("0")
            self.log.warning(
                f"{NEON_YELLOW}ATR calculation resulted in NaN for {self.symbol}. ATR set to 0.{RESET}"
            )
        self.indicator_values["atr"] = self.atr_value

    def _detect_market_condition(self) -> str:
        """Detects overall market condition (trending, ranging, volatile, calm)."""
        adx_period = self.cfg.get_nested("indicator_periods.adx", 14)
        bb_window = self.cfg.get_nested("indicator_periods.bb", 20)
        ema_long_period = self.cfg.get_nested("ema_long_period", 26)

        required_data = max(adx_period, bb_window, ema_long_period)
        if len(self.df) < required_data + 10:  # Add a buffer for robust calculations
            self.log.warning(
                f"{NEON_YELLOW}Insufficient data to reliably detect market condition ({len(self.df)}/{required_data + 10} bars). Defaulting to 'low_volatility'.{RESET}"
            )
            return "low_volatility"

        # Calculate ADX
        adx_data = Indicators.adx(
            self.df.high, self.df.low, self.df.close, window=adx_period
        )
        adx_val = (
            adx_data["ADX"].iloc[-1]
            if not adx_data.empty and not pd.isna(adx_data["ADX"].iloc[-1])
            else Decimal("0")
        )

        # Calculate Bollinger Bands
        bb_data = Indicators.bb(
            self.df.close,
            window=bb_window,
            std_dev_mult=Decimal(
                str(self.cfg.get_nested("indicator_periods.bb_std", 2))
            ),
        )
        bb_upper = bb_data["upper"].iloc[-1] if not bb_data.empty else Decimal("0")
        bb_lower = bb_data["lower"].iloc[-1] if not bb_data.empty else Decimal("0")
        bb_middle = bb_data["middle"].iloc[-1] if not bb_data.empty else Decimal("0")

        # Calculate Bollinger Bandwidth and Average Bandwidth for context
        bb_bandwidth = (
            (bb_upper - bb_lower) / bb_middle
            if bb_middle != Decimal("0")
            else Decimal("0")
        )

        # Recent ATR mean for volatility context
        atr_series = Indicators.atr(
            self.df.high, self.df.low, self.df.close, self.cfg["atr_period"]
        )
        recent_atr_mean = (
            atr_series.iloc[-min(10, len(atr_series)) :].mean()
            if not atr_series.empty
            else Decimal("0")
        )

        # Define thresholds from config
        adx_trend_threshold = Decimal(
            str(
                self.cfg.get_nested(
                    "market_condition_detection.adx_trend_threshold", 25
                )
            )
        )
        atr_vol_multiplier = Decimal(
            str(
                self.cfg.get_nested(
                    "market_condition_detection.atr_volatility_threshold_multiplier",
                    1.5,
                )
            )
        )
        bb_range_multiplier = Decimal(
            str(
                self.cfg.get_nested(
                    "market_condition_detection.bb_bandwidth_threshold_multiplier", 0.8
                )
            )
        )

        # Determine conditions
        is_trending_strong = adx_val > adx_trend_threshold
        is_volatile = (
            self.atr_value > (recent_atr_mean * atr_vol_multiplier)
            if recent_atr_mean > 0
            else False
        )
        is_ranging = (
            bb_bandwidth
            < (
                self.df["close"]
                .iloc[-min(bb_window, len(self.df)) :]
                .std()
                .apply(lambda x: Decimal(str(x)))
                * bb_range_multiplier
            )
            if len(self.df) >= bb_window
            else False
        )

        # Trend direction using EMA
        ema_long = Indicators.ema(self.df.close, span=ema_long_period)
        is_uptrend, is_downtrend = False, False
        if len(ema_long) >= 5:  # Need at least 5 periods to check slope
            is_uptrend = (
                self.df.close.iloc[-1] > ema_long.iloc[-1]
                and ema_long.iloc[-1] > ema_long.iloc[-5]
            )  # Price above EMA and EMA sloping up
            is_downtrend = (
                self.df.close.iloc[-1] < ema_long.iloc[-1]
                and ema_long.iloc[-1] < ema_long.iloc[-5]
            )  # Price below EMA and EMA sloping down

        condition = "low_volatility"  # Default fallback (original low_volatility)

        if is_trending_strong:
            if is_uptrend:
                condition = "trending_up"
            elif is_downtrend:
                condition = "trending_down"
            else:  # Strong ADX but no clear EMA direction indicates potential reversal or exhaustion
                condition = "volatile"  # Or "ranging" if BB is narrow
                if is_ranging:
                    condition = "ranging"  # Prioritize ranging if true
        elif is_volatile:
            condition = "volatile"
        elif is_ranging:
            condition = "ranging"
        else:  # Neither strongly trending nor ranging nor volatile, implies calm or consolidating
            condition = "calm"

        self.log.info(
            f"Detected Market Condition: {NEON_PURPLE}{condition.upper()}{RESET} "
            f"(ADX: {adx_val:.2f}, ATR: {self.atr_value:.5f}, BB Bandwidth: {bb_bandwidth:.4f})"
        )
        return condition

    def _select_weight_set(self) -> dict[str, float]:
        """Selects indicator weights based on market condition."""
        # This function now uses the detected market condition
        selected_weights = self.cfg["weight_sets"].get(
            self.market_condition, self.cfg["weight_sets"]["low_volatility"]
        )
        self.log.info(
            f"Using weight set: {NEON_PURPLE}{self.market_condition.upper()}{RESET}"
        )
        return selected_weights

    def _calculate_ema_alignment(self) -> Decimal:
        """Calculates a score based on EMA alignment and price position."""
        short_p, long_p = self.cfg["ema_short_period"], self.cfg["ema_long_period"]
        if len(self.df) < long_p:
            return Decimal("0")
        ema_short = Indicators.ema(self.df.close, span=short_p)
        ema_long = Indicators.ema(self.df.close, span=long_p)
        price = self.df.close

        # Ensure latest values are available
        if (
            ema_short.empty
            or ema_long.empty
            or price.empty
            or pd.isna(ema_short.iloc[-1])
            or pd.isna(ema_long.iloc[-1])
            or pd.isna(price.iloc[-1])
        ):
            return Decimal("0")

        # Check for price above EMAs and EMAs aligned bullishly (short > long)
        if price.iloc[-1] > ema_short.iloc[-1] > ema_long.iloc[-1]:
            # Also check previous candle for consistency for a stronger signal
            if len(price) > 1 and (
                price.iloc[-2] > ema_short.iloc[-2] > ema_long.iloc[-2]
            ):
                return Decimal("1.0")  # Strong bullish alignment
            return Decimal("0.5")  # Moderate bullish alignment (just current candle)

        # Check for price below EMAs and EMAs aligned bearishly (short < long)
        if price.iloc[-1] < ema_short.iloc[-1] < ema_long.iloc[-1]:
            if len(price) > 1 and (
                price.iloc[-2] < ema_short.iloc[-2] < ema_long.iloc[-2]
            ):
                return Decimal("-1.0")  # Strong bearish alignment
            return Decimal("-0.5")  # Moderate bearish alignment

        # Check for bullish crossover (short crosses above long)
        if (
            ema_short.iloc[-1] > ema_long.iloc[-1]
            and len(ema_short) > 1
            and ema_short.iloc[-2] <= ema_long.iloc[-2]
        ):
            return Decimal("0.3")

        # Check for bearish crossover (short crosses below long)
        if (
            ema_short.iloc[-1] < ema_long.iloc[-1]
            and len(ema_short) > 1
            and ema_short.iloc[-2] >= ema_long.iloc[-2]
        ):
            return Decimal("-0.3")

        return Decimal("0")

    def _calculate_volume_confirmation(self) -> bool:
        """Checks if the latest volume is significantly above its moving average."""
        vol_ma_series = Indicators.sma(self.df.volume, self.cfg["volume_ma_period"])
        if (
            vol_ma_series.empty
            or pd.isna(vol_ma_series.iloc[-1])
            or vol_ma_series.iloc[-1] == Decimal("0")
        ):
            return False
        vol_ma_value = vol_ma_series.iloc[-1]
        multiplier = Decimal(str(self.cfg["volume_confirmation_multiplier"]))
        return self.df.volume.iloc[-1] > vol_ma_value * multiplier

    def _detect_macd_divergence(self) -> str | None:
        """Detects bullish or bearish MACD divergence (simplified logic)."""
        macd_df = Indicators.macd(
            self.df.close,
            fast=self.cfg.get_nested("indicator_periods.ema_short", 12),
            slow=self.cfg.get_nested("indicator_periods.ema_long", 26),
            signal=self.cfg.get_nested("indicator_periods.macd_signal", 9),
        )

        if (
            macd_df.empty
            or len(self.df)
            < self.cfg.get_nested("signal_generation.divergence_lookback", 10) + 1
        ):
            return None

        prices = self.df["close"]
        macd_hist = macd_df["histogram"]
        lookback = self.cfg.get_nested("signal_generation.divergence_lookback", 10)

        # Ensure we have enough data after indicator calculations
        if len(prices) < lookback + 1 or len(macd_hist) < lookback + 1:
            return None

        # Bullish divergence: Lower lows in price, higher lows in MACD histogram
        if (
            prices.iloc[-1] < prices.iloc[-lookback]
            and macd_hist.iloc[-1] > macd_hist.iloc[-lookback]
        ):
            return "bullish"

        # Bearish divergence: Higher highs in price, lower highs in MACD histogram
        if (
            prices.iloc[-1] > prices.iloc[-lookback]
            and macd_hist.iloc[-1] < macd_hist.iloc[-lookback]
        ):
            return "bearish"

        return None

    def _analyze_order_book_walls(
        self, order_book: dict[str, Any]
    ) -> tuple[bool, bool, dict[str, Decimal], dict[str, Decimal]]:
        """Detect bullish/bearish walls from bids/asks."""
        enabled = self.cfg.get_nested("order_book_analysis.enabled", False)
        if not enabled or not order_book:
            return False, False, {}, {}

        depth_to_check = int(
            self.cfg.get_nested("order_book_analysis.depth_to_check", 10)
        )
        wall_threshold_multiplier = Decimal(
            str(
                self.cfg.get_nested(
                    "order_book_analysis.wall_threshold_multiplier", 2.0
                )
            )
        )

        bids = [
            (Decimal(p), Decimal(q))
            for p, q in order_book.get("bids", [])[:depth_to_check]
        ]
        asks = [
            (Decimal(p), Decimal(q))
            for p, q in order_book.get("asks", [])[:depth_to_check]
        ]

        all_qty = [q for _, q in bids] + [q for _, q in asks]
        if not all_qty:
            return False, False, {}, {}

        avg_qty = sum(all_qty) / Decimal(str(len(all_qty))) if all_qty else Decimal("0")
        wall_threshold = avg_qty * wall_threshold_multiplier

        current_price = self.df.close.iloc[-1]
        bullish_walls_details, bearish_walls_details = {}, {}

        for price_dec, qty_dec in bids:
            if (
                qty_dec >= wall_threshold and price_dec < current_price
            ):  # Bid wall below current price (support)
                bullish_walls_details[
                    f"Bid@{price_dec.quantize(Decimal('0.0001'))}"
                ] = qty_dec
                break  # Only log the first significant wall for simplicity

        for price_dec, qty_dec in asks:
            if (
                qty_dec >= wall_threshold and price_dec > current_price
            ):  # Ask wall above current price (resistance)
                bearish_walls_details[
                    f"Ask@{price_dec.quantize(Decimal('0.0001'))}"
                ] = qty_dec
                break  # Only log the first significant wall for simplicity

        return (
            bool(bullish_walls_details),
            bool(bearish_walls_details),
            bullish_walls_details,
            bearish_walls_details,
        )

    def calculate_fibonacci_retracement(
        self, high: Decimal, low: Decimal, current_price: Decimal
    ) -> None:
        """Calculates Fibonacci retracement levels based on a given high and low."""
        diff = high - low
        if diff <= 0:  # Avoid division by zero or negative diff
            self.fib_levels = {}
            # Clear existing Fib levels in support/resistance
            self.levels["Support"] = {
                k: v
                for k, v in self.levels["Support"].items()
                if not k.startswith("Fib ")
            }
            self.levels["Resistance"] = {
                k: v
                for k, v in self.levels["Resistance"].items()
                if not k.startswith("Fib ")
            }
            return

        fib_ratios = {
            "23.6%": Decimal("0.236"),
            "38.2%": Decimal("0.382"),
            "50.0%": Decimal("0.500"),
            "61.8%": Decimal("0.618"),
            "78.6%": Decimal("0.786"),
            "88.6%": Decimal("0.886"),
        }

        # Calculate retracement levels and quantize for display/comparison
        self.fib_levels = {
            f"Fib {label}": (high - (diff * ratio)).quantize(Decimal("0.00001"))
            for label, ratio in fib_ratios.items()
        }

        for label, value in self.fib_levels.items():
            if value < current_price:
                self.levels["Support"][label] = value
            elif value > current_price:
                self.levels["Resistance"][label] = value

    def calculate_pivot_points(self, high: Decimal, low: Decimal, close: Decimal):
        """Calculates standard Pivot Points."""
        pivot = (high + low + close) / Decimal("3")
        r1 = (Decimal("2") * pivot) - low
        s1 = (Decimal("2") * pivot) - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)
        r3 = high + Decimal("2") * (pivot - low)
        s3 = low - Decimal("2") * (high - pivot)

        precision = Decimal("0.00001")  # Standard precision for prices
        pivots = {
            "Pivot": pivot,
            "R1": r1,
            "S1": s1,
            "R2": r2,
            "S2": s2,
            "R3": r3,
            "S3": s3,
        }

        # Add to main levels dict, quantizing
        for label, val in pivots.items():
            if val is not None and not val.is_nan():
                if val <= close:  # Support if at or below current close
                    self.levels["Support"][label] = val.quantize(precision)
                else:  # Resistance if above current close
                    self.levels["Resistance"][label] = val.quantize(precision)

    def find_nearest_levels(
        self, current_price: Decimal, num_levels: int = 5
    ) -> tuple[list[tuple[str, Decimal]], list[tuple[str, Decimal]]]:
        """Finds the nearest support and resistance levels from calculated Fibonacci and Pivot Points."""
        supports: list[tuple[str, Decimal]] = []
        resistances: list[tuple[str, Decimal]] = []

        # Iterate through combined support/resistance levels
        for level_type, levels_dict in self.levels.items():
            for label, value in levels_dict.items():
                if value is not None and not value.is_nan():
                    if value <= current_price:
                        supports.append((label, value))
                    else:
                        resistances.append((label, value))

        # Sort and return the top N nearest
        sorted_supports = sorted(supports, key=lambda x: current_price - x[1])
        sorted_resistances = sorted(resistances, key=lambda x: x[1] - current_price)

        return sorted_supports[:num_levels], sorted_resistances[:num_levels]

    def _interpret_and_color_indicator(self, name: str, value: Any) -> str:
        """Interprets indicator values and formats them with neon colors."""
        line = f"  {name.upper():<20}: {value!s}"  # Default string representation
        color = NEON_BLUE  # Default color

        # Conditional formatting for specific indicators
        if name == "ema_alignment":
            if value == Decimal("1.0"):
                color = NEON_GREEN
                line = f"  EMA Alignment     : {NEON_GREEN}Strong Bullish{RESET}"
            elif value == Decimal("0.5"):
                color = NEON_GREEN
                line = f"  EMA Alignment     : {NEON_GREEN}Bullish{RESET}"
            elif value == Decimal("-1.0"):
                color = NEON_RED
                line = f"  EMA Alignment     : {NEON_RED}Strong Bearish{RESET}"
            elif value == Decimal("-0.5"):
                color = NEON_RED
                line = f"  EMA Alignment     : {NEON_RED}Bearish{RESET}"
            elif value == Decimal("0.3"):
                color = NEON_GREEN
                line = f"  EMA Alignment     : {NEON_GREEN}Bullish Crossover{RESET}"
            elif value == Decimal("-0.3"):
                color = NEON_RED
                line = f"  EMA Alignment     : {NEON_RED}Bearish Crossover{RESET}"
            else:
                line = f"  EMA Alignment     : {NEON_YELLOW}Neutral{RESET}"
        elif name == "volume_confirmation":
            line = (
                f"  Volume Conf.      : {NEON_GREEN}Confirmed{RESET}"
                if value
                else f"  Volume Conf.      : {NEON_YELLOW}Unconfirmed{RESET}"
            )
        elif name == "rsi":
            if value > Decimal("70"):
                color = NEON_RED
                status = "Overbought"
            elif value < Decimal("30"):
                color = NEON_GREEN
                status = "Oversold"
            else:
                color = NEON_BLUE
                status = "Neutral"
            line = f"  RSI               : {color}{value:.2f} ({status}){RESET}"
        elif name == "macd":
            hist = value.get("histogram", Decimal("0"))
            macd_line = value.get("macd", Decimal("0"))
            signal_line = value.get("signal", Decimal("0"))
            if hist > Decimal("0"):
                color = NEON_GREEN
            elif hist < Decimal("0"):
                color = NEON_RED
            line = f"  MACD              : {color}Hist: {hist:.5f} (MACD: {macd_line:.5f} Sig: {signal_line:.5f}){RESET}"
        elif name == "stoch_rsi":
            k, d = (
                value.get("stoch_rsi_k", Decimal("0")),
                value.get("stoch_rsi_d", Decimal("0")),
            )
            color_k = NEON_GREEN if k < 20 else NEON_RED if k > 80 else NEON_YELLOW
            color_d = NEON_GREEN if d < 20 else NEON_RED if d > 80 else NEON_YELLOW
            line = f"  Stoch RSI         : K={color_k}{k:.2f}{RESET} D={color_d}{d:.2f}{RESET}"
        elif name == "psar":
            # PSAR value is the point itself, compare to current price to determine signal
            current_price = (
                self.df.close.iloc[-1] if not self.df.close.empty else Decimal("0")
            )
            if current_price > value:
                color = NEON_GREEN
                status = "Bullish"
            elif current_price < value:
                color = NEON_RED
                status = "Bearish"
            else:
                color = NEON_BLUE
                status = "Neutral"
            line = f"  PSAR              : {color}{value:.5f} ({status}){RESET}"
        elif name == "cmf":
            if value > Decimal("0"):
                color = NEON_GREEN
                status = "Positive"
            elif value < Decimal("0"):
                color = NEON_RED
                status = "Negative"
            else:
                status = "Neutral"
            line = f"  CMF               : {color}{value:.4f} ({status}){RESET}"
        elif name == "ao":
            if value > Decimal("0"):
                color = NEON_GREEN
                status = "Bullish"
            elif value < Decimal("0"):
                color = NEON_RED
                status = "Bearish"
            else:
                status = "Neutral"
            line = f"  AO                : {color}{value:.5f} ({status}){RESET}"
        elif name == "vi":
            plus_vi, minus_vi = (
                value.get("+VI", Decimal("0")),
                value.get("-VI", Decimal("0")),
            )
            if plus_vi > minus_vi:
                color = NEON_GREEN
                status = "Bullish"
            elif plus_vi < minus_vi:
                color = NEON_RED
                status = "Bearish"
            else:
                color = NEON_BLUE
                status = "Neutral"
            line = f"  Vortex Indicator  : +VI={NEON_GREEN}{plus_vi:.2f}{RESET} -VI={NEON_RED}{minus_vi:.2f}{RESET} ({color}{status}{RESET})"
        elif name == "bb":
            upper, middle, lower = (
                value.get("upper", Decimal("0")),
                value.get("middle", Decimal("0")),
                value.get("lower", Decimal("0")),
            )
            current_price = self.df.close.iloc[-1]
            if current_price > upper:
                color = NEON_RED
                status = "Overbought"
            elif current_price < lower:
                color = NEON_GREEN
                status = "Oversold"
            else:
                color = NEON_BLUE
                status = "In Band"
            line = f"  Bollinger Bands   : Price {color}{status}{RESET} (Mid: {middle:.5f} Up: {upper:.5f} Low: {lower:.5f})"
        elif name == "keltner_channels":
            upper, middle, lower = (
                value.get("upper", Decimal("0")),
                value.get("middle", Decimal("0")),
                value.get("lower", Decimal("0")),
            )
            current_price = self.df.close.iloc[-1]
            if current_price > upper:
                color = NEON_RED
                status = "Above Upper"
            elif current_price < lower:
                color = NEON_GREEN
                status = "Below Lower"
            else:
                color = NEON_BLUE
                status = "Within Channel"
            line = f"  Keltner Channels  : Price {color}{status}{RESET} (Mid: {middle:.5f} Up: {upper:.5f} Low: {lower:.5f})"
        elif name == "ichimoku":
            tenkan, kijun, senkou_a, senkou_b, chikou = (
                value.get("tenkan_sen", Decimal("0")),
                value.get("kijun_sen", Decimal("0")),
                value.get("senkou_span_a", Decimal("0")),
                value.get("senkou_span_b", Decimal("0")),
                value.get("chikou_span", Decimal("0")),
            )
            current_price = self.df.close.iloc[-1]

            status_parts = []
            if current_price > senkou_a and current_price > senkou_b:
                status_parts.append(f"{NEON_GREEN}Above Cloud{RESET}")
            elif current_price < senkou_a and current_price < senkou_b:
                status_parts.append(f"{NEON_RED}Below Cloud{RESET}")
            else:
                status_parts.append(f"{NEON_YELLOW}In Cloud{RESET}")

            if tenkan > kijun:
                status_parts.append(f"{NEON_GREEN}Tenkan > Kijun{RESET}")
            else:
                status_parts.append(f"{NEON_RED}Tenkan < Kijun{RESET}")

            line = f"  Ichimoku          : {' | '.join(status_parts)} (T: {tenkan:.5f} K: {kijun:.5f} SA: {senkou_a:.5f} SB: {senkou_b:.5f} Ch: {chikou:.5f})"
        elif name == "supertrend":
            current_price = self.df.close.iloc[-1]
            if current_price > value:
                color = NEON_GREEN
                status = "Uptrend"
            elif current_price < value:
                color = NEON_RED
                status = "Downtrend"
            else:
                color = NEON_BLUE
                status = "Neutral/Flat"
            line = f"  Supertrend        : {color}{value:.5f} ({status}){RESET}"

        return line

    def analyze(self, price: Decimal, ts: str, order_book: dict[str, Any] | None):
        """Performs a full analysis and logs a detailed summary."""
        cfg_ind = self.cfg["indicators"]
        cfg_prd = self.cfg["indicator_periods"]

        # Ensure latest price data is used for levels calculation
        if self.df.empty:
            self.log.error(
                f"{NEON_RED}DataFrame is empty, cannot perform analysis.{RESET}"
            )
            return

        high_dec, low_dec, close_dec = (
            self.df.high.max(),
            self.df.low.min(),
            self.df.close.iloc[-1],
        )

        # Initialize levels dictionary for each analysis run
        self.levels = {"Support": {}, "Resistance": {}}

        self.calculate_fibonacci_retracement(high_dec, low_dec, price)
        self.calculate_pivot_points(high_dec, low_dec, close_dec)

        # Map available data and periods to indicator parameters
        indicator_params: dict[str, Any] = {
            "high": self.df.high,
            "low": self.df.low,
            "close": self.df.close,
            "volume": self.df.volume,
        }
        # Add all periods from config
        indicator_params.update(cfg_prd)

        # Calculate and store indicator values dynamically
        for name in sorted(
            cfg_ind.keys()
        ):  # Iterate through indicators defined in config
            if not cfg_ind.get(name):
                continue  # Skip if indicator is disabled

            try:
                indicator_method = getattr(Indicators, name, None)
                if indicator_method:
                    # Construct parameters based on the method's signature
                    params_for_method = {}
                    sig = inspect.signature(indicator_method)
                    for param_name, param_obj in sig.parameters.items():
                        if param_name in indicator_params:
                            params_for_method[param_name] = indicator_params[param_name]
                        elif (
                            param_obj.default is inspect.Parameter.empty
                        ):  # Mandatory parameter missing
                            self.log.warning(
                                f"{NEON_YELLOW}Skipping '{name}': Missing mandatory parameter '{param_name}'.{RESET}"
                            )
                            params_for_method = None  # Mark as uncallable
                            break

                    if params_for_method is not None:
                        series_or_df = indicator_method(**params_for_method)
                        if isinstance(series_or_df, pd.Series):
                            self.indicator_values[name] = (
                                series_or_df.iloc[-1]
                                if not series_or_df.empty
                                and not pd.isna(series_or_df.iloc[-1])
                                else Decimal("NaN")
                            )
                        elif isinstance(series_or_df, pd.DataFrame):
                            # Convert last row of DataFrame to dictionary for easier access
                            self.indicator_values[name] = (
                                series_or_df.iloc[-1].to_dict()
                                if not series_or_df.empty
                                else {}
                            )
                        else:
                            self.indicator_values[name] = (
                                None  # Should not happen if method returns Series/DataFrame
                            )
            except Exception as e:
                self.log.error(
                    f"{NEON_RED}Error calculating indicator '{name}': {e}{RESET}"
                )
                self.indicator_values[name] = (
                    None  # Ensure it's explicitly None on error
                )

        # Manual checks for specific indicators that aren't direct function calls
        self.indicator_values["ema_alignment"] = self._calculate_ema_alignment()
        self.indicator_values["volume_confirmation"] = (
            self._calculate_volume_confirmation()
        )
        self.indicator_values["divergence"] = self._detect_macd_divergence()

        has_bull, has_bear, bullish_details, bearish_details = (
            self._analyze_order_book_walls(order_book or {})
        )
        self.indicator_values["order_book_walls"] = {
            "bullish": has_bull,
            "bearish": has_bear,
            "bullish_details": bullish_details,
            "bearish_details": bearish_details,
        }

        # --- Log Summary ---
        log_lines = [
            f"\n{'─' * 20} ANALYSIS FOR {self.symbol} ({self.interval}) {'─' * 20}",
            f" Timestamp: {ts} │ Current Price: {NEON_BLUE}{price:.5f}{RESET}",
            f" Market Condition: {NEON_PURPLE}{self.market_condition.upper()}{RESET}",
            f" Price History: {self.df['close'].iloc[-3]:.5f} | {self.df['close'].iloc[-2]:.5f} | {self.df['close'].iloc[-1]:.5f}",
            f" Volume History: {self.df['volume'].iloc[-3]:,.0f} | {self.df['volume'].iloc[-2]:,.0f} | {self.df['volume'].iloc[-1]:,.0f}",
            f" ATR({self.cfg['atr_period']}): {self.atr_value:.5f}",
        ]

        log_lines.append(f"\n{NEON_BLUE}─ Indicators:{RESET}")
        for name in sorted(self.indicator_values.keys()):
            # Filter out non-configured indicators or temporary values
            # atr is explicitly logged above, so don't re-log here unless it's for display consistency
            if name not in cfg_ind and name not in [
                "ema_alignment",
                "volume_confirmation",
                "divergence",
                "order_book_walls",
            ]:
                continue  # Only log configured indicators and special internal ones

            value = self.indicator_values.get(name)
            if (
                value is None
                or (isinstance(value, Decimal) and value.is_nan())
                or (isinstance(value, dict) and not value)
            ):  # Empty dicts from indicator outputs
                continue  # Don't log if value is None, NaN, or empty dict

            colored_line = self._interpret_and_color_indicator(name, value)
            if colored_line:
                log_lines.append(colored_line)

        log_lines.append(f"\n{NEON_BLUE}─ Order Book Walls:{RESET}")
        if has_bull:
            log_lines.append(
                f"{NEON_GREEN}  Bullish Walls Found: {', '.join([f'{k}:{v:,.0f}' for k, v in bullish_details.items()])}{RESET}"
            )
        if has_bear:
            log_lines.append(
                f"{NEON_RED}  Bearish Walls Found: {', '.join([f'{k}:{v:,.0f}' for k, v in bearish_details.items()])}{RESET}"
            )
        if not has_bull and not has_bear:
            log_lines.append("  No significant walls detected.")

        log_lines.append(f"\n{NEON_BLUE}─ Support/Resistance Levels:{RESET}")
        nearest_supports, nearest_resistances = self.find_nearest_levels(price)
        for label, val in nearest_supports:
            log_lines.append(f"S: {label} ${val:.5f}")
        for label, val in nearest_resistances:
            log_lines.append(f"R: {label} ${val:.5f}")
        if not nearest_supports and not nearest_resistances:
            log_lines.append("  No significant levels calculated.")

        self.log.info("\n".join(log_lines))
        self.log.info("─" * (42 + len(self.symbol) + len(self.interval)))

    def generate_trading_signal(self, current_price: Decimal) -> TradeSignal:
        """Combines indicator scores and other analysis to generate a final trade signal."""
        raw_score = Decimal("0.0")
        conditions_met = []

        # Calculate scores from main indicators based on selected weights
        for name, weight_float in self.weights.items():
            if not self.cfg["indicators"].get(name):
                continue  # Only consider enabled indicators

            value = self.indicator_values.get(name)
            if (
                value is None
                or (isinstance(value, Decimal) and value.is_nan())
                or (isinstance(value, dict) and not value)
            ):  # Skip if indicator value is not available, NaN, or empty dict
                continue

            weight_dec = Decimal(str(weight_float))

            # --- Scoring Logic for each indicator ---
            if name == "ema_alignment":
                if value == Decimal("1.0"):
                    raw_score += weight_dec
                    conditions_met.append("EMA Alignment (Strong Bullish)")
                elif value == Decimal("0.5"):
                    raw_score += weight_dec * Decimal("0.5")
                    conditions_met.append("EMA Alignment (Bullish)")
                elif value == Decimal("-1.0"):
                    raw_score -= weight_dec
                    conditions_met.append("EMA Alignment (Strong Bearish)")
                elif value == Decimal("-0.5"):
                    raw_score -= weight_dec * Decimal("0.5")
                    conditions_met.append("EMA Alignment (Bearish)")
                elif value == Decimal("0.3"):
                    raw_score += weight_dec * Decimal("0.3")
                    conditions_met.append("EMA Bullish Crossover")
                elif value == Decimal("-0.3"):
                    raw_score -= weight_dec * Decimal("0.3")
                    conditions_met.append("EMA Bearish Crossover")

            elif name == "volume_confirmation":
                if value:
                    raw_score += weight_dec
                    conditions_met.append("Volume Confirmation")

            elif name == "divergence":
                if value == "bullish":
                    raw_score += weight_dec
                    conditions_met.append("Bullish Divergence")
                elif value == "bearish":
                    raw_score -= weight_dec
                    conditions_met.append("Bearish Divergence")

            elif name == "stoch_rsi":
                k, d = (
                    value.get("stoch_rsi_k", Decimal("0")),
                    value.get("stoch_rsi_d", Decimal("0")),
                )
                stoch_oversold_threshold = Decimal(
                    str(self.cfg.get("stoch_rsi_oversold_threshold", 20))
                )
                stoch_overbought_threshold = Decimal(
                    str(self.cfg.get("stoch_rsi_overbought_threshold", 80))
                )
                if k < stoch_oversold_threshold and k > d:
                    raw_score += weight_dec
                    conditions_met.append("StochRSI Oversold (K>D)")
                elif k > stoch_overbought_threshold and k < d:
                    raw_score -= weight_dec
                    conditions_met.append("StochRSI Overbought (K<D)")

            elif name == "rsi":
                if value < Decimal("30"):
                    raw_score += weight_dec
                    conditions_met.append("RSI Oversold")
                elif value > Decimal("70"):
                    raw_score -= weight_dec
                    conditions_met.append("RSI Overbought")

            elif name == "macd":
                hist = value.get("histogram")
                if hist and hist > Decimal("0"):
                    raw_score += weight_dec
                    conditions_met.append("MACD Bullish")
                elif hist and hist < Decimal("0"):
                    raw_score -= weight_dec
                    conditions_met.append("MACD Bearish")

            elif name == "psar":
                if value and current_price > value:
                    raw_score += weight_dec
                    conditions_met.append("PSAR Bullish")
                elif value and current_price < value:
                    raw_score -= weight_dec
                    conditions_met.append("PSAR Bearish")

            elif name == "stochastic_oscillator":
                k, d = value.get("k", Decimal("0")), value.get("d", Decimal("0"))
                if k < Decimal("20") and k > d:
                    raw_score += weight_dec
                    conditions_met.append("Stoch Osc Oversold (K>D)")
                elif k > Decimal("80") and k < d:
                    raw_score -= weight_dec
                    conditions_met.append("Stoch Osc Overbought (K<D)")

            elif name == "cmf":
                if value > Decimal("0"):
                    raw_score += weight_dec
                    conditions_met.append("CMF Positive")
                elif value < Decimal("0"):
                    raw_score -= weight_dec
                    conditions_met.append("CMF Negative")

            elif name == "ao":
                if value > Decimal("0"):
                    raw_score += weight_dec
                    conditions_met.append("AO Bullish")
                elif value < Decimal("0"):
                    raw_score -= weight_dec
                    conditions_met.append("AO Bearish")

            elif name == "vi":
                plus_vi, minus_vi = (
                    value.get("+VI", Decimal("0")),
                    value.get("-VI", Decimal("0")),
                )
                if plus_vi > minus_vi:
                    raw_score += weight_dec
                    conditions_met.append("VI Bullish Crossover")
                elif plus_vi < minus_vi:
                    raw_score -= weight_dec
                    conditions_met.append("VI Bearish Crossover")

            elif name == "bb":
                upper, lower = (
                    value.get("upper", Decimal("0")),
                    value.get("lower", Decimal("0")),
                )
                if current_price < lower:
                    raw_score += weight_dec
                    conditions_met.append("BB Oversold")
                elif current_price > upper:
                    raw_score -= weight_dec
                    conditions_met.append("BB Overbought")

            elif name == "keltner_channels":
                upper, lower = (
                    value.get("upper", Decimal("0")),
                    value.get("lower", Decimal("0")),
                )
                if current_price < lower:
                    raw_score += weight_dec
                    conditions_met.append("Keltner Below Lower")
                elif current_price > upper:
                    raw_score -= weight_dec
                    conditions_met.append("Keltner Above Upper")

            elif name == "ichimoku":
                tenkan, kijun, senkou_a, senkou_b, chikou = (
                    value.get("tenkan_sen", Decimal("0")),
                    value.get("kijun_sen", Decimal("0")),
                    value.get("senkou_span_a", Decimal("0")),
                    value.get("senkou_span_b", Decimal("0")),
                    value.get("chikou_span", Decimal("0")),
                )

                # Cloud position
                if current_price > senkou_a and current_price > senkou_b:
                    raw_score += weight_dec * Decimal("0.5")
                    conditions_met.append("Ichimoku Price Above Cloud")
                elif current_price < senkou_a and current_price < senkou_b:
                    raw_score -= weight_dec * Decimal("0.5")
                    conditions_met.append("Ichimoku Price Below Cloud")

                # Tenkan/Kijun cross
                # Use current and previous values to detect a crossover
                prev_ichimoku = self.indicator_values.get(
                    "ichimoku_prev", {}
                )  # Store previous ichimoku values
                prev_tenkan = prev_ichimoku.get("tenkan_sen", Decimal("0"))
                prev_kijun = prev_ichimoku.get("kijun_sen", Decimal("0"))

                if tenkan > kijun and prev_tenkan <= prev_kijun:  # Bullish Cross
                    raw_score += weight_dec * Decimal("0.3")
                    conditions_met.append("Ichimoku Bullish Cross (Tenkan over Kijun)")
                elif tenkan < kijun and prev_tenkan >= prev_kijun:  # Bearish Cross
                    raw_score -= weight_dec * Decimal("0.3")
                    conditions_met.append("Ichimoku Bearish Cross (Tenkan under Kijun)")

            elif name == "supertrend":
                if value and current_price > value:
                    raw_score += weight_dec
                    conditions_met.append("Supertrend Bullish")
                elif value and current_price < value:
                    raw_score -= weight_dec
                    conditions_met.append("Supertrend Bearish")

            elif name in ["fve", "vwap", "obv", "adi", "cci", "wr", "adx", "sma_10"]:
                # These indicators are primarily for analysis and market condition detection,
                # their direct contribution to score is usually captured by other indicators or market condition.
                # If specific scoring logic is needed, it can be added here.
                pass

        # Store current Ichimoku values for next cycle's crossover detection
        self.indicator_values["ichimoku_prev"] = self.indicator_values.get(
            "ichimoku", {}
        )

        # Order book walls add a confidence boost
        ob_walls = self.indicator_values.get("order_book_walls", {})
        if ob_walls.get("bullish"):
            raw_score += Decimal(
                str(self.cfg.get("order_book_support_confidence_boost", 0))
            )
            conditions_met.append("Order Book: Bullish Wall")
        if ob_walls.get("bearish"):
            raw_score -= Decimal(
                str(self.cfg.get("order_book_resistance_confidence_boost", 0))
            )
            conditions_met.append("Order Book: Bearish Wall")

        signal = None
        min_threshold = Decimal(str(self.cfg["signal_score_threshold"]))
        if raw_score >= min_threshold:
            signal = "buy"
        elif raw_score <= -min_threshold:
            signal = "sell"

        # Calculate Stop Loss and Take Profit
        sl, tp = Decimal("0"), Decimal("0")
        if signal and self.atr_value > Decimal("0"):
            atr_multiple_sl = Decimal(str(self.cfg["stop_loss_multiple"]))
            atr_multiple_tp = Decimal(str(self.cfg["take_profit_multiple"]))

            if signal == "buy":
                sl = (current_price - (self.atr_value * atr_multiple_sl)).quantize(
                    Decimal("0.00001")
                )
                tp = (current_price + (self.atr_value * atr_multiple_tp)).quantize(
                    Decimal("0.00001")
                )
            else:  # sell
                sl = (current_price + (self.atr_value * atr_multiple_sl)).quantize(
                    Decimal("0.00001")
                )
                tp = (current_price - (self.atr_value * atr_multiple_tp)).quantize(
                    Decimal("0.00001")
                )

        # Normalize score to a confidence level (0.0 to 1.0)
        # Max possible score calculation needs to be dynamic based on current weights
        # Simple sum of absolute weights + boosts
        max_possible_score = (
            sum(abs(w) for w in self.weights.values())
            + self.cfg.get("order_book_support_confidence_boost", 0)
            + self.cfg.get("order_book_resistance_confidence_boost", 0)
        )

        confidence = (
            abs(float(raw_score)) / max_possible_score
            if max_possible_score > 0
            else 0.0
        )
        # Cap confidence at 1.0, and format to 2 decimal places
        confidence = round(min(1.0, confidence), 2)

        return TradeSignal(
            signal, confidence, conditions_met, {"stop_loss": sl, "take_profit": tp}
        )


# ----------------------------------------------------------------------------
# 7. MAIN APPLICATION LOOP
# ----------------------------------------------------------------------------
def main():
    """Main function to initialize and run the trading bot loop."""
    if not API_KEY or not API_SECRET:
        LOGGER.critical(
            f"{NEON_RED}API credentials (BYBIT_API_KEY, BYBIT_API_SECRET) are missing in .env file. Running in analysis-only mode.{RESET}"
        )
        bybit_client = None  # Set client to None if API keys are missing
    else:
        bybit_client = BybitClient(BASE_URL, API_KEY, API_SECRET, LOGGER)

    symbol = (
        input(f"{NEON_BLUE}Enter symbol (default BTCUSDT): {RESET}") or "BTCUSDT"
    ).upper()
    interval = (
        input(
            f"{NEON_BLUE}Enter interval ({', '.join(VALID_INTERVALS)}) (default {CFG['interval']}): {RESET}"
        )
        or CFG["interval"]
    )

    if interval not in VALID_INTERVALS:
        LOGGER.warning(
            f"{NEON_YELLOW}Invalid interval '{interval}'. Falling back to default '{CFG['interval']}'.{RESET}"
        )
        interval = CFG["interval"]

    symbol_logger = setup_logger(symbol)  # Specific logger for the symbol
    symbol_logger.info(
        f"🚀 WhaleBot Enhanced starting for {NEON_PURPLE}{symbol}{RESET} on interval {NEON_PURPLE}{interval}{RESET}"
    )

    last_signal_time = 0.0
    last_ob_fetch_time = 0.0
    order_book: dict[str, Any] | None = None

    try:
        while True:
            price: Decimal | None = None  # Initialize price to None

            if bybit_client:
                price = bybit_client.fetch_current_price(symbol)
                if price is None:
                    symbol_logger.error(
                        f"{NEON_RED}Failed to fetch current price. Retrying in {CFG['retry_delay']}s...{RESET}"
                    )
                    time.sleep(CFG["retry_delay"])
                    continue
            else:  # If running in analysis-only mode without API keys
                symbol_logger.warning(
                    f"{NEON_YELLOW}Running in analysis-only mode. No live price/kline/orderbook will be fetched.{RESET}"
                )
                symbol_logger.info(
                    f"{NEON_YELLOW}Please manually provide current price (e.g., 28000.0) or press enter to skip:{RESET}"
                )
                manual_price_input = input()
                try:
                    price = Decimal(manual_price_input)
                    # In analysis-only mode without live data, providing a single price
                    # doesn't allow for historical chart analysis required for indicators.
                    # We need to explicitly state this limitation.
                    symbol_logger.warning(
                        f"{NEON_YELLOW}Manual price input is for demonstration. Cannot run full indicator analysis without historical Kline data. Skipping cycle.{RESET}"
                    )
                    time.sleep(CFG["analysis_interval"])
                    continue
                except (InvalidOperation, ValueError):
                    symbol_logger.warning(
                        f"{NEON_YELLOW}Invalid or no manual price provided. Skipping analysis cycle.{RESET}"
                    )
                    time.sleep(CFG["analysis_interval"])
                    continue

            # Determine minimum data needed for all ENABLED indicators based on their periods
            min_data_needed = 0
            # Initialize with default min needed for general price action/volume
            min_data_needed = max(min_data_needed, 30)

            for name, enabled in CFG["indicators"].items():
                if enabled:
                    # Dynamically get the parameters for the indicator method
                    indicator_method = getattr(Indicators, name, None)
                    if indicator_method:
                        sig = inspect.signature(indicator_method)
                        for param_name, param_obj in sig.parameters.items():
                            if (
                                param_name.endswith("_period")
                                or param_name.endswith("_span")
                                or param_name.endswith("_k")
                                or param_name.endswith("_d")
                                or param_name.endswith("_multiplier")
                            ):
                                # Attempt to get period from CFG["indicator_periods"]
                                period_val = CFG.get_nested(
                                    f"indicator_periods.{param_name}", None
                                )

                                if period_val is not None:
                                    # Ensure it's an integer for periods, or convertible for multipliers
                                    try:
                                        if (
                                            "multiplier" in param_name
                                        ):  # Multipliers can be float/decimal
                                            min_data_needed = max(
                                                min_data_needed, 1
                                            )  # Multipliers don't directly add to data length
                                        else:  # Periods usually integer
                                            min_data_needed = max(
                                                min_data_needed, int(period_val)
                                            )
                                    except (ValueError, TypeError):
                                        symbol_logger.warning(
                                            f"{NEON_YELLOW}Config error: Period '{param_name}' for indicator '{name}' is not a valid number. Defaulting to 1 for calculation.{RESET}"
                                        )
                                        min_data_needed = max(min_data_needed, 1)
                            # Special case for Ichimoku shifts as they require data before/after current point
                            elif name == "ichimoku" and param_name == "chikou_shift":
                                shift_val = CFG.get_nested(
                                    "indicator_periods.ichimoku_chikou_shift", 26
                                )
                                min_data_needed = max(min_data_needed, shift_val)

            min_data_needed += 10  # Add a buffer for safe indexing / rolling operations

            df: pd.DataFrame = pd.DataFrame()  # Initialize df
            if bybit_client:  # Only fetch klines if client exists
                df = bybit_client.fetch_klines(symbol, interval, min_data_needed)
                if df.empty or len(df) < min_data_needed:
                    symbol_logger.warning(
                        f"{NEON_YELLOW}Insufficient Kline data ({len(df)}/{min_data_needed} bars). Retrying...{RESET}"
                    )
                    time.sleep(CFG["retry_delay"])
                    continue

                current_time = time.time()
                if current_time - last_ob_fetch_time >= CFG["order_book_debounce_s"]:
                    order_book = bybit_client.fetch_order_book(
                        symbol, CFG["order_book_depth_to_check"]
                    )
                    last_ob_fetch_time = current_time
            else:
                # In analysis-only mode, we don't have live klines or order book
                symbol_logger.info(
                    f"{NEON_YELLOW}No Bybit client available. Cannot fetch live data. Waiting for next cycle...{RESET}"
                )
                time.sleep(CFG["analysis_interval"])
                continue  # Skip analysis if no real data source

            analyzer = TradingAnalyzer(df, CFG, symbol_logger, symbol, interval)
            timestamp_str = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")

            # Ensure price is not None before passing to analyze
            if price is None:
                symbol_logger.error(
                    f"{NEON_RED}Price is None, cannot perform analysis. Skipping cycle.{RESET}"
                )
                time.sleep(CFG["analysis_interval"])
                continue

            analyzer.analyze(
                price, timestamp_str, order_book
            )  # Pass price and order_book

            trade_signal = analyzer.generate_trading_signal(price)

            # Check for signal cooldown before outputting trade signal
            current_time = time.time()  # Re-check current time after analysis
            if trade_signal.signal and (
                current_time - last_signal_time >= CFG["signal_cooldown_s"]
            ):
                last_signal_time = current_time  # Update last signal time
                color = NEON_GREEN if trade_signal.signal == "buy" else NEON_RED

                signal_message = (
                    f"\n{color}🔔 {'-' * 10} TRADE SIGNAL: {trade_signal.signal.upper()} {'-' * 10}{RESET}\n"
                    f"   Confidence Score: {trade_signal.confidence:.2f}\n"
                    f"   Conditions Met: {'; '.join(trade_signal.conditions)}\n"
                )

                if trade_signal.levels:
                    sl_val = trade_signal.levels.get("stop_loss", Decimal("0"))
                    tp_val = trade_signal.levels.get("take_profit", Decimal("0"))
                    # Ensure formatting matches original output
                    signal_message += (
                        f"   Stop Loss: {sl_val:.5f} | Take Profit: {tp_val:.5f}\n"
                    )

                signal_message += f"{NEON_YELLOW}   --- Placeholder: Order placement logic would execute here ---{RESET}\n"

                symbol_logger.info(signal_message)
            elif trade_signal.signal:
                symbol_logger.info(
                    f"{NEON_YELLOW}Signal detected ({trade_signal.signal.upper()}) but still in cooldown period ({int(CFG['signal_cooldown_s'] - (current_time - last_signal_time))}s remaining).{RESET}"
                )
            # Log that no trade signal was generated this cycle if confidence is too low or no signal
            else:
                symbol_logger.info(
                    f"{NEON_BLUE}No trade signal generated (score too low or neutral).{RESET}"
                )

            time.sleep(CFG["analysis_interval"])  # Wait for next analysis cycle

    except KeyboardInterrupt:
        symbol_logger.info(
            f"\n{NEON_YELLOW}User stopped analysis. Shutting down...{RESET}"
        )
    except Exception as e:
        symbol_logger.exception(
            f"{NEON_RED}An unexpected critical error occurred: {e}{RESET}"
        )
        time.sleep(CFG["retry_delay"] * 2)  # Wait longer on critical errors


if __name__ == "__main__":
    main()
