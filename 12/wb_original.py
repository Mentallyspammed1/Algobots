import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime
from decimal import Decimal, getcontext
from typing import Any

# --- END CORRECTED IMPORT ---
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

# --- CORRECTED IMPORT ---
from colorama import Fore, Style, init
from dotenv import load_dotenv
from logger_config import setup_custom_logger

# Set Decimal precision for financial calculations to avoid floating point errors
getcontext().prec = 10

# Initialize colorama for cross-platform colored terminal output
init(autoreset=True) # <-- This line now correctly uses the imported init

# Load environment variables from .env file
load_dotenv()

# --- Color Codex ---
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
RESET = Style.RESET_ALL

# --- Configuration & Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs"
TIMEZONE = ZoneInfo("America/Chicago") # Using a specific timezone for consistency
MAX_API_RETRIES = 3
RETRY_DELAY_SECONDS = 5
VALID_INTERVALS = ["1", "3", "5", "15", "30", "60", "120", "240", "D", "W", "M"]
RETRY_ERROR_CODES = [429, 500, 502, 503, 504] # HTTP status codes to trigger a retry

# Ensure log directory exists
os.makedirs(LOG_DIRECTORY, exist_ok=True)

# Setup the main application logger
logger = setup_custom_logger('whalebot_main')


def load_config(filepath: str) -> dict:
    """
    Loads configuration from a JSON file, merging with default values.
    If the file is not found or is invalid, it creates one with default settings.
    """
    default_config = {
        "interval": "15",
        "analysis_interval": 30, # Time in seconds between main analysis cycles
        "retry_delay": 5, # Delay in seconds for API retries
        "momentum_period": 10,
        "momentum_ma_short": 12,
        "momentum_ma_long": 26,
        "volume_ma_period": 20,
        "atr_period": 14,
        "trend_strength_threshold": 0.4,
        "sideways_atr_multiplier": 1.5,
        "signal_score_threshold": 1.0, # Minimum combined weight for a signal to be valid
        "indicators": {
            "ema_alignment": True,
            "momentum": True,
            "volume_confirmation": True,
            "divergence": True,
            "stoch_rsi": True,
            "rsi": True, # Money Flow Index
            "macd": True,
            "vwap": False,
            "obv": True,
            "adi": True,
            "cci": True,
            "wr": True,
            "adx": True,
            "psar": True,
            "fve": True,
            "sma_10": False,
            "mfi": True,
        },
        "weight_sets": {
            "low_volatility": { # Weights for a low volatility market environment
                "ema_alignment": 0.3,
                "momentum": 0.2,
                "volume_confirmation": 0.2,
                "divergence": 0.1,
                "stoch_rsi": 0.5,
                "rsi": 0.3,
                "macd": 0.3,
                "vwap": 0.0,
                "obv": 0.1,
                "adi": 0.1,
                "cci": 0.1,
                "wr": 0.1,
                "adx": 0.1,
                "psar": 0.1,
                "fve": 0.2,
                "sma_10": 0.0,
                "mfi": 0.3,
            },
            "high_volatility": { # Weights for a high volatility market environment
                "ema_alignment": 0.1,
                "momentum": 0.4,
                "volume_confirmation": 0.1,
                "divergence": 0.2,
                "stoch_rsi": 0.4,
                "rsi": 0.4,
                "macd": 0.4,
                "vwap": 0.0,
                "obv": 0.1,
                "adi": 0.1,
                "cci": 0.1,
                "wr": 0.1,
                "adx": 0.1,
                "psar": 0.1,
                "fve": 0.3,
                "sma_10": 0.0,
                "mfi": 0.4,
            }
        },
        "stoch_rsi_oversold_threshold": 20,
        "stoch_rsi_overbought_threshold": 80,
        "stoch_rsi_confidence_boost": 5, # Additional boost for strong Stoch RSI signals
        "stoch_rsi_mandatory": False, # If true, Stoch RSI must be a confirming factor
        "rsi_confidence_boost": 2,
        "mfi_confidence_boost": 2,
        "order_book_support_confidence_boost": 3,
        "order_book_resistance_confidence_boost": 3,
        "stop_loss_multiple": 1.5, # Multiplier for ATR to determine stop loss distance
        "take_profit_multiple": 1.0, # Multiplier for ATR to determine take profit distance
        "order_book_wall_threshold_multiplier": 2.0, # Multiplier for average volume to identify a "wall"
        "order_book_depth_to_check": 10, # Number of order book levels to check for walls
        "price_change_threshold": 0.005, # % change in price to consider significant
        "atr_change_threshold": 0.005, # % change in ATR to consider significant volatility change
        "signal_cooldown_s": 60, # Seconds to wait before generating another signal
        "order_book_debounce_s": 10, # Seconds to wait between order book API calls
        "ema_short_period": 12,
        "ema_long_period": 26,
        "volume_confirmation_multiplier": 1.5, # Volume must be this many times average volume for confirmation
        # --- New: Indicator Period Customization ---
        "indicator_periods": {
            "rsi": 14,
            "mfi": 14,
            "cci": 20,
            "williams_r": 14,
            "adx": 14,
            "stoch_rsi_period": 14,
            "stoch_rsi_k_period": 3,
            "stoch_rsi_d_period": 3,
            "momentum": 10,
            "momentum_ma_short": 12,
            "momentum_ma_long": 26,
            "volume_ma": 20,
            "atr": 14,
        },
        # --- New: Order Book Analysis Configuration ---
        "order_book_analysis": {
            "enabled": True,
            "wall_threshold_multiplier": 2.0,
            "depth_to_check": 10,
            "support_boost": 3,
            "resistance_boost": 3,
        },
        # --- New: Trailing Stop Loss Configuration ---
        "trailing_stop_loss": {
            "enabled": False, # Disabled by default
            "initial_activation_percent": 0.5, # Activate trailing stop after price moves X% in favor
            "trailing_stop_multiple_atr": 1.5 # Trail stop based on ATR multiple
        },
        # --- New: Take Profit Scaling Configuration ---
        "take_profit_scaling": {
            "enabled": False, # Disabled by default
            "targets": [
                {"level": 1.5, "percentage": 0.25}, # Sell 25% when price hits 1.5x ATR TP
                {"level": 2.0, "percentage": 0.50}  # Sell 50% of remaining when price hits 2.0x ATR TP
            ]
        }
    }
    try:
        with open(filepath, encoding="utf-8") as f:
            config = json.load(f)
            # Merge loaded config with defaults. Prioritize loaded values, but ensure all default keys exist.
            merged_config = {**default_config, **config}

            # Basic validation for interval and analysis_interval
            if merged_config.get("interval") not in VALID_INTERVALS:
                logger.warning(f"{NEON_YELLOW}Invalid 'interval' in config, using default: {default_config['interval']}{RESET}")
                merged_config["interval"] = default_config["interval"]
            if not isinstance(merged_config.get("analysis_interval"), int) or merged_config.get("analysis_interval") <= 0:
                logger.warning(f"{NEON_YELLOW}Invalid 'analysis_interval' in config, using default: {default_config['analysis_interval']}{RESET}")
                merged_config["analysis_interval"] = default_config["analysis_interval"]

            return merged_config
    except FileNotFoundError:
        logger.warning(f"{NEON_YELLOW}Config file not found, loading defaults and creating {filepath}{RESET}")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4)
        return default_config
    except json.JSONDecodeError:
        logger.error(f"{NEON_RED}Invalid JSON in config file, loading defaults.{RESET}")
        # Optionally, back up the corrupt file before overwriting
        try:
            os.rename(filepath, f"{filepath}.bak_{int(time.time())}")
            logger.info(f"{NEON_YELLOW}Backed up corrupt config file to {filepath}.bak_{int(time.time())}{RESET}")
        except OSError as e:
            logger.error(f"{NEON_RED}Failed to backup corrupt config file: {e}{RESET}")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4)
        return default_config

# Load the configuration
CONFIG = load_config(CONFIG_FILE)

def generate_signature(api_secret: str, params: dict) -> str:
    """Generates the HMAC SHA256 signature for Bybit API requests."""
    # Ensure params are sorted by key for consistent signature generation
    param_str = "&".join([f"{key}={value}" for key, value in sorted(params.items())])
    return hmac.new(api_secret.encode(), param_str.encode(), hashlib.sha256).hexdigest()

def handle_api_error(response: requests.Response, logger: logging.Logger) -> None:
    """Logs detailed API error responses."""
    logger.error(f"{NEON_RED}API request failed with status code: {response.status_code}{RESET}")
    try:
        error_json = response.json()
        logger.error(f"{NEON_RED}Error details: {error_json}{RESET}")
    except json.JSONDecodeError:
        logger.error(f"{NEON_RED}Response text: {response.text}{RESET}")

def bybit_request(method: str, endpoint: str, api_key: str, api_secret: str, params: dict[str, Any] = None, logger: logging.Logger = None) -> dict | None:
    """
    Sends a signed request to the Bybit API with retry logic.

    Args:
        method (str): HTTP method (e.g., "GET", "POST").
        endpoint (str): API endpoint path.
        api_key (str): Your Bybit API key.
        api_secret (str): Your Bybit API secret.
        params (Dict[str, Any], optional): Dictionary of request parameters. Defaults to None.
        logger (logging.Logger, optional): Logger instance for logging. Defaults to None.

    Returns:
        Union[dict, None]: JSON response data if successful, None otherwise.
    """
    params = params or {}
    params['timestamp'] = str(int(time.time() * 1000)) # Current timestamp in milliseconds
    signature = generate_signature(api_secret, params)
    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": signature,
        "X-BAPI-TIMESTAMP": params['timestamp'],
        "Content-Type": "application/json"
    }
    url = f"{BASE_URL}{endpoint}"

    for retry in range(MAX_API_RETRIES):
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                params=params if method == "GET" else None,
                json=params if method == "POST" else None,
                timeout=10 # Set a timeout for requests
            )
            response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)

            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code in RETRY_ERROR_CODES:
                if logger:
                    logger.warning(f"{NEON_YELLOW}API Error {e.response.status_code} ({e.response.reason}), retrying {retry + 1}/{MAX_API_RETRIES}...{RESET}")
                time.sleep(RETRY_DELAY_SECONDS * (2**retry)) # Exponential backoff
            else:
                if logger:
                    handle_api_error(e.response, logger)
                return None
        except requests.exceptions.RequestException as e:
            if logger:
                logger.error(f"{NEON_RED}Request exception: {e}, retrying {retry + 1}/{MAX_API_RETRIES}...{RESET}")
            time.sleep(RETRY_DELAY_SECONDS * (2**retry))

    if logger:
        logger.error(f"{NEON_RED}Max retries reached for {method} {endpoint}{RESET}")
    return None

def fetch_current_price(symbol: str, api_key: str, api_secret: str, logger: logging.Logger) -> Decimal | None:
    """Fetches the current last traded price for a given symbol."""
    endpoint = "/v5/market/tickers"
    params = {"category": "linear", "symbol": symbol}
    response_data = bybit_request("GET", endpoint, api_key, api_secret, params, logger)
    if response_data and response_data.get("retCode") == 0 and response_data.get("result"):
        tickers = response_data["result"].get("list")
        if tickers:
            for ticker in tickers:
                if ticker.get("symbol") == symbol:
                    last_price = ticker.get("lastPrice")
                    return Decimal(last_price) if last_price else None
    logger.error(f"{NEON_RED}Could not fetch current price for {symbol}. Response: {response_data}{RESET}")
    return None

def fetch_klines(symbol: str, interval: str, api_key: str, api_secret: str, logger: logging.Logger, limit: int = 200) -> pd.DataFrame:
    """Fetches historical K-line (candlestick) data for a given symbol and interval."""
    endpoint = "/v5/market/kline"
    params = {"symbol": symbol, "interval": interval, "limit": limit, "category": "linear"}
    response_data = bybit_request("GET", endpoint, api_key, api_secret, params, logger)
    if response_data and response_data.get("retCode") == 0 and response_data.get("result") and response_data["result"].get("list"):
        data = response_data["result"]["list"]
        # Bybit's kline list order is: [timestamp, open, high, low, close, volume, turnover]
        columns = ["start_time", "open", "high", "low", "close", "volume", "turnover"]
        df = pd.DataFrame(data, columns=columns)
        df["start_time"] = pd.to_datetime(df["start_time"], unit="ms")
        # Convert numeric columns, coercing errors to NaN
        for col in df.columns[1:]:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        # Drop any rows that resulted in all NaNs after conversion (shouldn't happen with valid data)
        df.dropna(subset=df.columns[1:], inplace=True)
        return df.sort_values(by="start_time", ascending=True).reset_index(drop=True) # Ensure chronological order
    logger.error(f"{NEON_RED}Failed to fetch Kline data for {symbol}, interval {interval}. Response: {response_data}{RESET}")
    return pd.DataFrame()

def fetch_order_book(symbol: str, api_key: str, api_secret: str, logger: logging.Logger, limit: int = 50) -> dict | None:
    """Fetches the order book (bids and asks) for a given symbol."""
    endpoint = "/v5/market/orderbook"
    params = {"symbol": symbol, "limit": limit, "category": "linear"}
    response_data = bybit_request("GET", endpoint, api_key, api_secret, params, logger)
    if response_data and response_data.get("retCode") == 0 and response_data.get("result"):
        return response_data["result"]
    logger.warning(f"{NEON_YELLOW}Could not fetch order book for {symbol}. Response: {response_data}{RESET}")
    return None

class TradingAnalyzer:
    """
    Performs technical analysis on candlestick data and generates trading signals.
    """
    def __init__(self, df: pd.DataFrame, config: dict, symbol_logger: logging.Logger, symbol: str, interval: str):
        self.df = df.copy() # Work on a copy to avoid modifying original DataFrame
        self.config = config
        self.logger = symbol_logger
        self.symbol = symbol
        self.interval = interval
        self.levels: dict[str, Any] = {} # Stores support/resistance levels (fib, pivot)
        self.fib_levels: dict[str, float] = {} # Stores calculated Fibonacci levels
        self.weight_sets = config["weight_sets"]
        self.indicator_values: dict[str, Any] = {} # Stores calculated indicator values
        self.atr_value: float = 0.0 # Stores the latest ATR value

        # Pre-calculate common indicators needed for others or for weight selection
        self._pre_calculate_indicators()

        # Now that ATR is potentially calculated, select the weight set
        self.user_defined_weights = self._select_weight_set() # Dynamically selected weights

        # Calculate Stoch RSI if enabled, as it's used in signal generation
        if self.config["indicators"].get("stoch_rsi"):
            self.indicator_values["stoch_rsi_vals"] = self._calculate_stoch_rsi()

    def _pre_calculate_indicators(self):
        """Pre-calculates indicators necessary for weight selection or other calculations."""
        if not self.df.empty:
            # Calculate ATR once for volatility assessment
            atr_series = self._calculate_atr(window=self.config["atr_period"])
            if not atr_series.empty and not pd.isna(atr_series.iloc[-1]):
                self.atr_value = atr_series.iloc[-1]
            else:
                self.atr_value = 0.0 # Default ATR to 0 if calculation fails or is NaN
            self.indicator_values["atr"] = self.atr_value # Store ATR for logging/analysis

            # Calculate momentum MAs for trend determination
            self._calculate_momentum_ma()

    def _select_weight_set(self) -> dict[str, float]:
        """
        Selects a weight set (e.g., low_volatility, high_volatility) based on current ATR.
        """
        # Use the atr_value that was pre-calculated in _pre_calculate_indicators
        if self.atr_value > self.config["atr_change_threshold"]:
            self.logger.info(f"{NEON_YELLOW}Market detected as HIGH VOLATILITY (ATR: {self.atr_value:.4f}). Using 'high_volatility' weights.{RESET}")
            return self.weight_sets.get("high_volatility", self.weight_sets["low_volatility"])
        self.logger.info(f"{NEON_BLUE}Market detected as LOW VOLATILITY (ATR: {self.atr_value:.4f}). Using 'low_volatility' weights.{RESET}")
        return self.weight_sets["low_volatility"]

    def _safe_series_operation(self, column: str, operation: str, window: int = None, series: pd.Series = None) -> pd.Series:
        """Helper to safely perform operations on DataFrame columns or provided series."""
        if series is not None:
            data_series = series
        elif column in self.df.columns:
            data_series = self.df[column]
        else:
            self.logger.error(f"{NEON_RED}Missing '{column}' column for {operation} calculation.{RESET}")
            return pd.Series(dtype=float)

        if data_series.empty:
            return pd.Series(dtype=float)

        try:
            if operation == "sma":
                return data_series.rolling(window=window).mean()
            elif operation == "ema":
                return data_series.ewm(span=window, adjust=False).mean()
            elif operation == "max":
                return data_series.rolling(window=window).max()
            elif operation == "min":
                return data_series.rolling(window=window).min()
            elif operation == "diff":
                return data_series.diff(window)
            elif operation == "abs_diff_mean":
                return data_series.rolling(window=window).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
            elif operation == "cumsum":
                return data_series.cumsum()
            else:
                self.logger.error(f"{NEON_RED}Unsupported series operation: {operation}{RESET}")
                return pd.Series(dtype=float)
        except Exception as e:
            self.logger.error(f"{NEON_RED}Error during {operation} calculation on {column}: {e}{RESET}")
            return pd.Series(dtype=float)

    def _calculate_sma(self, window: int, series: pd.Series = None) -> pd.Series:
        """Calculates Simple Moving Average (SMA). Can operate on a specified series or 'close' price."""
        return self._safe_series_operation('close', 'sma', window, series)

    def _calculate_ema(self, window: int, series: pd.Series = None) -> pd.Series:
        """Calculates Exponential Moving Average (EMA). Can operate on a specified series or 'close' price."""
        return self._safe_series_operation('close', 'ema', window, series)

    def _calculate_ema_alignment(self) -> float:
        """
        Calculates an EMA alignment score.
        Score is 1.0 for strong bullish alignment, -1.0 for strong bearish, 0.0 for neutral.
        """
        ema_short = self._calculate_ema(self.config["ema_short_period"])
        ema_long = self._calculate_ema(self.config["ema_long_period"])

        if ema_short.empty or ema_long.empty or len(self.df) < max(self.config["ema_short_period"], self.config["ema_long_period"]):
            return 0.0

        latest_short_ema = Decimal(str(ema_short.iloc[-1]))
        latest_long_ema = Decimal(str(ema_long.iloc[-1]))
        current_price = Decimal(str(self.df["close"].iloc[-1]))

        # Check for consistent alignment over the last few bars (e.g., 3 bars)
        alignment_period = 3
        if len(ema_short) < alignment_period or len(ema_long) < alignment_period:
            return 0.0

        bullish_aligned_count = 0
        bearish_aligned_count = 0

        for i in range(1, alignment_period + 1):
            if (ema_short.iloc[-i] > ema_long.iloc[-i] and
                self.df["close"].iloc[-i] > ema_short.iloc[-i]):
                bullish_aligned_count += 1
            elif (ema_short.iloc[-i] < ema_long.iloc[-i] and
                  self.df["close"].iloc[-i] < ema_short.iloc[-i]):
                bearish_aligned_count += 1

        if bullish_aligned_count >= alignment_period - 1: # At least (period-1) bars are aligned
            return 1.0 # Strong bullish alignment
        elif bearish_aligned_count >= alignment_period - 1:
            return -1.0 # Strong bearish alignment
        else:
            # Check for recent crossover as a weaker signal
            if latest_short_ema > latest_long_ema and ema_short.iloc[-2] <= latest_long_ema:
                return 0.5 # Recent bullish crossover
            elif latest_short_ema < latest_long_ema and ema_short.iloc[-2] >= latest_long_ema:
                return -0.5 # Recent bearish crossover
            return 0.0 # Neutral

    def _calculate_momentum(self, period: int = 10) -> pd.Series:
        """Calculates the Momentum indicator."""
        return self._safe_series_operation('close', 'diff', period) / self.df["close"].shift(period) * 100

    def _calculate_cci(self, window: int = 20, constant: float = 0.015) -> pd.Series:
        """Calculates the Commodity Channel Index (CCI)."""
        required_columns = ['high', 'low', 'close']
        if not all(col in self.df.columns for col in required_columns):
            self.logger.error(f"{NEON_RED}Missing required columns for CCI calculation.{RESET}")
            return pd.Series(dtype=float)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_typical_price = self._safe_series_operation(None, 'sma', window, typical_price)
        mean_deviation = self._safe_series_operation(None, 'abs_diff_mean', window, typical_price)
        # Avoid division by zero
        cci = (typical_price - sma_typical_price) / (constant * mean_deviation)
        return cci.replace([np.inf, -np.inf], np.nan) # Handle potential inf values

    def _calculate_williams_r(self, window: int = 14) -> pd.Series:
        """Calculates the Williams %R indicator."""
        required_columns = ['high', 'low', 'close']
        if not all(col in self.df.columns for col in required_columns):
            self.logger.error(f"{NEON_RED}Missing required columns for Williams %R calculation.{RESET}")
            return pd.Series(dtype=float)
        highest_high = self._safe_series_operation('high', 'max', window)
        lowest_low = self._safe_series_operation('low', 'min', window)
        # Avoid division by zero
        denominator = (highest_high - lowest_low)
        wr = ((highest_high - self.df["close"]) / denominator) * -100
        return wr.replace([np.inf, -np.inf], np.nan)

    def _calculate_mfi(self, window: int = 14) -> pd.Series:
        """Calculates the Money Flow Index (MFI)."""
        required_columns = ['high', 'low', 'close', 'volume']
        if not all(col in self.df.columns for col in required_columns):
            self.logger.error(f"{NEON_RED}Missing required columns for MFI calculation.{RESET}")
            return pd.Series(dtype=float)

        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        raw_money_flow = typical_price * self.df["volume"]

        # Calculate positive and negative money flow
        money_flow_direction = typical_price.diff()
        positive_flow = raw_money_flow.where(money_flow_direction > 0, 0)
        negative_flow = raw_money_flow.where(money_flow_direction < 0, 0)

        # Calculate sums over the window
        positive_mf = self._safe_series_operation(None, 'sma', window, positive_flow) * window # sum not mean
        negative_mf = self._safe_series_operation(None, 'sma', window, negative_flow) * window # sum not mean

        # Avoid division by zero
        money_ratio = positive_mf / negative_mf.replace(0, np.nan) # Replace 0 with NaN to handle division by zero
        mfi = 100 - (100 / (1 + money_ratio))
        return mfi.replace([np.inf, -np.inf], np.nan).fillna(0) # Fill NaN from division by zero with 0 or a sensible value

    def calculate_fibonacci_retracement(self, high: Decimal, low: Decimal, current_price: Decimal) -> dict[str, Decimal]:
        """Calculates Fibonacci retracement levels based on a given high and low."""
        diff = high - low
        if diff <= 0: # Handle cases where high <= low
            self.logger.warning(f"{NEON_YELLOW}Cannot calculate Fibonacci retracement: High ({high}) <= Low ({low}).{RESET}")
            self.fib_levels = {}
            self.levels = {"Support": {}, "Resistance": {}}
            return {}

        # Standard Fibonacci ratios
        fib_ratios = {
            "23.6%": Decimal('0.236'), "38.2%": Decimal('0.382'), "50.0%": Decimal('0.500'),
            "61.8%": Decimal('0.618'), "78.6%": Decimal('0.786'), "88.6%": Decimal('0.886'),
            "94.1%": Decimal('0.941')
        }
        fib_levels_calculated: dict[str, Decimal] = {}

        # Assuming an uptrend (retracement from high to low)
        # Levels are calculated from the high, moving down
        for label, ratio in fib_ratios.items():
            level = high - (diff * ratio)
            fib_levels_calculated[f"Fib {label}"] = level.quantize(Decimal('0.00001')) # Quantize for consistent precision

        self.fib_levels = fib_levels_calculated
        self.levels = {"Support": {}, "Resistance": {}}

        # Categorize levels as support or resistance relative to current price
        for label, value in self.fib_levels.items():
            if value < current_price:
                self.levels["Support"][label] = value
            elif value > current_price:
                self.levels["Resistance"][label] = value

        return self.fib_levels

    def calculate_pivot_points(self, high: Decimal, low: Decimal, close: Decimal):
        """Calculates standard Pivot Points."""
        pivot = (high + low + close) / 3
        r1 = (2 * pivot) - low
        s1 = (2 * pivot) - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)
        r3 = high + 2 * (pivot - low)
        s3 = low - 2 * (high - pivot)

        # Quantize all pivot points for consistent precision
        precision = Decimal('0.00001')
        self.levels.update({
            "Pivot": pivot.quantize(precision),
            "R1": r1.quantize(precision), "S1": s1.quantize(precision),
            "R2": r2.quantize(precision), "S2": s2.quantize(precision),
            "R3": r3.quantize(precision), "S3": s3.quantize(precision),
        })

    def find_nearest_levels(self, current_price: Decimal, num_levels: int = 5) -> tuple[list[tuple[str, Decimal]], list[tuple[str, Decimal]]]:
        """
        Finds the nearest support and resistance levels from calculated Fibonacci and Pivot Points.
        """
        all_support_levels: list[tuple[str, Decimal]] = []
        all_resistance_levels: list[tuple[str, Decimal]] = []

        def process_level(label: str, value: Decimal):
            if value < current_price:
                all_support_levels.append((label, value))
            elif value > current_price:
                all_resistance_levels.append((label, value))

        # Process all levels stored in self.levels (from Fibonacci and Pivot)
        for label, value in self.levels.items():
            if isinstance(value, dict): # For nested levels like "Support": {"Fib 23.6%": ...}
                for sub_label, sub_value in value.items():
                    if isinstance(sub_value, Decimal):
                        process_level(f"{label} ({sub_label})", sub_value)
            elif isinstance(value, Decimal): # For direct levels like "Pivot"
                process_level(label, value)

        # Sort by distance to current price and select the 'num_levels' closest
        nearest_supports = sorted(all_support_levels, key=lambda x: current_price - x[1])[:num_levels]
        nearest_resistances = sorted(all_resistance_levels, key=lambda x: x[1] - current_price)[:num_levels]

        return nearest_supports, nearest_resistances

    def _calculate_atr(self, window: int = 14) -> pd.Series:
        """Calculates the Average True Range (ATR)."""
        required_columns = ['high', 'low', 'close']
        if not all(col in self.df.columns for col in required_columns):
            self.logger.error(f"{NEON_RED}Missing required columns for ATR calculation.{RESET}")
            return pd.Series(dtype=float)

        high_low = self.df["high"] - self.df["low"]
        high_close = abs(self.df["high"] - self.df["close"].shift())
        low_close = abs(self.df["low"] - self.df["close"].shift())

        # True Range is the maximum of the three
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return self._safe_series_operation(None, 'ema', window, tr) # Use EMA for ATR for smoothing

    def _calculate_rsi(self, window: int = 14) -> pd.Series:
        """Calculates the Relative Strength Index (RSI)."""
        if 'close' not in self.df.columns:
            self.logger.error(f"{NEON_RED}Missing 'close' column for RSI calculation.{RESET}")
            return pd.Series(dtype=float)

        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = self._safe_series_operation(None, 'ema', window, gain)
        avg_loss = self._safe_series_operation(None, 'ema', window, loss)

        # Avoid division by zero
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.replace([np.inf, -np.inf], np.nan).fillna(0) # Fill NaN from division by zero with 0

    def _calculate_stoch_rsi(self, rsi_window: int = 14, stoch_window: int = 14, k_window: int = 3, d_window: int = 3) -> pd.DataFrame:
        """Calculates Stochastic RSI (%K and %D lines)."""
        rsi = self._calculate_rsi(window=rsi_window)
        if rsi.empty:
            return pd.DataFrame()

        # Calculate StochRSI
        stoch_rsi = (rsi - self._safe_series_operation(None, 'min', stoch_window, rsi)) / \
                    (self._safe_series_operation(None, 'max', stoch_window, rsi) - self._safe_series_operation(None, 'min', stoch_window, rsi))

        # Handle division by zero for StochRSI (if max == min)
        stoch_rsi = stoch_rsi.replace([np.inf, -np.inf], np.nan).fillna(0)

        k_line = self._safe_series_operation(None, 'sma', k_window, stoch_rsi) * 100 # Scale to 0-100
        d_line = self._safe_series_operation(None, 'sma', d_window, k_line) # Signal line for %K

        return pd.DataFrame({'stoch_rsi': stoch_rsi * 100, 'k': k_line, 'd': d_line}) # Return StochRSI also scaled

    def _calculate_momentum_ma(self) -> None:
        """Calculates momentum and its moving averages, and volume moving average."""
        if 'close' not in self.df.columns or 'volume' not in self.df.columns:
            self.logger.error(f"{NEON_RED}Missing 'close' or 'volume' column for Momentum MA calculation.{RESET}")
            return

        self.df["momentum"] = self._safe_series_operation('close', 'diff', self.config["momentum_period"])
        self.df["momentum_ma_short"] = self._safe_series_operation(None, 'sma', self.config["momentum_ma_short"], self.df["momentum"])
        self.df["momentum_ma_long"] = self._safe_series_operation(None, 'sma', self.config["momentum_ma_long"], self.df["momentum"])
        self.df["volume_ma"] = self._safe_series_operation('volume', 'sma', self.config["volume_ma_period"])

    def _calculate_macd(self) -> pd.DataFrame:
        """Calculates Moving Average Convergence Divergence (MACD)."""
        if 'close' not in self.df.columns:
            self.logger.error(f"{NEON_RED}Missing 'close' column for MACD calculation.{RESET}")
            return pd.DataFrame()

        ma_short = self._safe_series_operation('close', 'ema', 12)
        ma_long = self._safe_series_operation('close', 'ema', 26)
        macd = ma_short - ma_long
        signal = self._safe_series_operation(None, 'ema', 9, macd)
        histogram = macd - signal
        return pd.DataFrame({'macd': macd, 'signal': signal, 'histogram': histogram})

    def detect_macd_divergence(self) -> str | None:
        """Detects bullish or bearish MACD divergence."""
        macd_df = self._calculate_macd()
        if macd_df.empty or len(self.df) < 30: # Need sufficient data for reliable divergence
            return None

        prices = self.df["close"]
        macd_histogram = macd_df["histogram"]

        # Simple divergence check on last two bars (can be expanded for more robust detection)
        if (prices.iloc[-2] > prices.iloc[-1] and macd_histogram.iloc[-2] < macd_histogram.iloc[-1]):
            self.logger.info(f"{NEON_GREEN}Detected Bullish MACD Divergence.{RESET}")
            return "bullish"
        elif (prices.iloc[-2] < prices.iloc[-1] and macd_histogram.iloc[-2] > macd_histogram.iloc[-1]):
            self.logger.info(f"{NEON_RED}Detected Bearish MACD Divergence.{RESET}")
            return "bearish"
        return None

    def determine_trend_momentum(self) -> dict[str, str | float]:
        """Determines the current trend and its strength based on momentum MAs and ATR."""
        if self.df.empty or len(self.df) < max(self.config["momentum_ma_long"], self.config["atr_period"]):
            return {"trend": "Insufficient Data", "strength": 0.0}

        # Ensure momentum_ma_short, momentum_ma_long, and atr_value are calculated
        if self.df["momentum_ma_short"].empty or self.df["momentum_ma_long"].empty or self.atr_value == 0:
            self.logger.warning(f"{NEON_YELLOW}Momentum MAs or ATR not available for trend calculation.{RESET}")
            return {"trend": "Neutral", "strength": 0.0}

        latest_short_ma = self.df["momentum_ma_short"].iloc[-1]
        latest_long_ma = self.df["momentum_ma_long"].iloc[-1]

        trend = "Neutral"
        if latest_short_ma > latest_long_ma:
            trend = "Uptrend"
        elif latest_short_ma < latest_long_ma:
            trend = "Downtrend"

        # Strength is normalized by ATR to make it comparable across symbols/timeframes
        strength = abs(latest_short_ma - latest_long_ma) / self.atr_value
        return {"trend": trend, "strength": strength}

    def _calculate_adx(self, window: int = 14) -> float:
        """Calculates the Average Directional Index (ADX)."""
        df_adx = self.df.copy()
        required_columns = ['high', 'low', 'close']
        if not all(col in df_adx.columns for col in required_columns):
            self.logger.error(f"{NEON_RED}Missing required columns for ADX calculation.{RESET}")
            return 0.0

        # True Range
        df_adx["TR"] = pd.concat([
            df_adx["high"] - df_adx["low"],
            abs(df_adx["high"] - df_adx["close"].shift()),
            abs(df_adx["low"] - df_adx["close"].shift())
        ], axis=1).max(axis=1)

        # Directional Movement
        df_adx["+DM"] = np.where((df_adx["high"] - df_adx["high"].shift()) > (df_adx["low"].shift() - df_adx["low"]),
                                 np.maximum(df_adx["high"] - df_adx["high"].shift(), 0), 0)
        df_adx["-DM"] = np.where((df_adx["low"].shift() - df_adx["low"]) > (df_adx["high"] - df_adx["high"].shift()),
                                 np.maximum(df_adx["low"].shift() - df_adx["low"], 0), 0)

        # Smoothed True Range and Directional Movement (using EMA)
        df_adx["TR_ema"] = self._safe_series_operation(None, 'ema', window, df_adx["TR"])
        df_adx["+DM_ema"] = self._safe_series_operation(None, 'ema', window, df_adx["+DM"])
        df_adx["-DM_ema"] = self._safe_series_operation(None, 'ema', window, df_adx["-DM"])

        # Directional Indicators
        df_adx["+DI"] = 100 * (df_adx["+DM_ema"] / df_adx["TR_ema"].replace(0, np.nan))
        df_adx["-DI"] = 100 * (df_adx["-DM_ema"] / df_adx["TR_ema"].replace(0, np.nan))

        # Directional Movement Index (DX)
        df_adx["DX"] = 100 * abs(df_adx["+DI"] - df_adx["-DI"]) / (df_adx["+DI"] + df_adx["-DI"]).replace(0, np.nan)

        # Average Directional Index (ADX)
        adx_value = self._safe_series_operation(None, 'ema', window, df_adx["DX"]).iloc[-1]
        return adx_value if not pd.isna(adx_value) else 0.0

    def _calculate_obv(self) -> pd.Series:
        """Calculates On-Balance Volume (OBV)."""
        if 'close' not in self.df.columns or 'volume' not in self.df.columns:
            self.logger.error(f"{NEON_RED}Missing 'close' or 'volume' column for OBV calculation.{RESET}")
            return pd.Series(dtype=float)

        obv = pd.Series(0, index=self.df.index, dtype=float)
        obv.iloc[0] = self.df["volume"].iloc[0] # Initialize with first volume

        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] - self.df["volume"].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1] # No change if close price is the same

        return obv

    def _calculate_adi(self) -> pd.Series:
        """Calculates Accumulation/Distribution Index (ADI)."""
        required_columns = ['high', 'low', 'close', 'volume']
        if not all(col in self.df.columns for col in required_columns):
            self.logger.error(f"{NEON_RED}Missing required columns for ADI calculation.{RESET}")
            return pd.Series(dtype=float)

        # Money Flow Multiplier (MFM)
        mfm_denominator = (self.df["high"] - self.df["low"])
        mfm = ((self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])) / mfm_denominator.replace(0, np.nan)
        mfm.fillna(0, inplace=True) # If high == low, MFM is 0

        # Money Flow Volume (MFV)
        money_flow_volume = mfm * self.df["volume"]

        # Accumulation/Distribution Line (ADL) is the cumulative sum of MFV
        return self._safe_series_operation(None, 'cumsum', series=money_flow_volume)

    def _calculate_psar(self, acceleration: float = 0.02, max_acceleration: float = 0.2) -> pd.Series:
        """Calculates Parabolic SAR (PSAR)."""
        psar = pd.Series(index=self.df.index, dtype="float64")
        if self.df.empty or len(self.df) < 2: # Need at least two bars to start
            return psar

        # Initial values
        psar.iloc[0] = self.df["close"].iloc[0] # Start PSAR at first close
        # Determine initial trend based on first two bars
        if self.df["close"].iloc[1] > self.df["close"].iloc[0]:
            trend = 1 # Uptrend
            ep = self.df["high"].iloc[0] # Extreme Point
        else:
            trend = -1 # Downtrend
            ep = self.df["low"].iloc[0] # Extreme Point
        af = acceleration # Acceleration Factor

        for i in range(1, len(self.df)):
            current_high = self.df["high"].iloc[i]
            current_low = self.df["low"].iloc[i]
            prev_psar = psar.iloc[i-1]

            if trend == 1: # Uptrend
                psar.iloc[i] = prev_psar + af * (ep - prev_psar)
                # Check if PSAR should be below current low
                psar.iloc[i] = min(psar.iloc[i], current_low, self.df["low"].iloc[i-1] if i > 1 else current_low)
                if current_high > ep: # New extreme high
                    ep = current_high
                    af = min(af + acceleration, max_acceleration)
                if current_low < psar.iloc[i]: # Trend reversal
                    trend = -1
                    psar.iloc[i] = ep # PSAR jumps to old EP
                    ep = current_low
                    af = acceleration
            elif trend == -1: # Downtrend
                psar.iloc[i] = prev_psar + af * (ep - prev_psar)
                # Check if PSAR should be above current high
                psar.iloc[i] = max(psar.iloc[i], current_high, self.df["high"].iloc[i-1] if i > 1 else current_high)
                if current_low < ep: # New extreme low
                    ep = current_low
                    af = min(af + acceleration, max_acceleration)
                if current_high > psar.iloc[i]: # Trend reversal
                    trend = 1
                    psar.iloc[i] = ep # PSAR jumps to old EP
                    ep = current_high
                    af = acceleration
        return psar

    def _calculate_fve(self) -> pd.Series:
        """
        Calculates a "Fictional Value Estimate" (FVE) by combining price, volume, and volatility.
        This is a custom composite indicator for demonstrative purposes.
        """
        if 'close' not in self.df.columns or 'volume' not in self.df.columns:
            self.logger.error(f"{NEON_RED}Missing 'close' or 'volume' column for FVE calculation.{RESET}")
            return pd.Series(dtype=float)

        try:
            # Components:
            # 1. Price Momentum (e.g., short EMA of close)
            # 2. Volume Strength (e.g., OBV)
            # 3. Volatility (e.g., inverse of ATR)

            # Ensure enough data for calculations
            min_data_points = max(20, self.config["atr_period"])
            if len(self.df) < min_data_points:
                self.logger.warning(f"{NEON_YELLOW}Insufficient data for FVE calculation. Need at least {min_data_points} bars.{RESET}")
                return pd.Series([np.nan] * len(self.df))

            price_component = self._calculate_ema(window=10) # Short term price trend
            obv_component = self._calculate_obv()
            atr_component = self._calculate_atr()

            # Normalize components to prevent one from dominating excessively
            # Simple normalization example: (value - mean) / std_dev
            # Or scale to a common range if means/std_devs are vastly different
            price_norm = (price_component - price_component.mean()) / price_component.std().replace(0, np.nan)
            obv_norm = (obv_component - obv_component.mean()) / obv_component.std().replace(0, np.nan)
            # Inverse of ATR: lower ATR means higher stability/less volatility, which can be seen as positive for trend following
            atr_inverse_norm = (1 / atr_component).replace([np.inf, -np.inf], np.nan)
            atr_inverse_norm = (atr_inverse_norm - atr_inverse_norm.mean()) / atr_inverse_norm.std().replace(0, np.nan)

            # Combine them - this formula is illustrative and should be fine-tuned
            # Higher FVE indicates more "value" or bullishness.
            fve = price_norm.fillna(0) + obv_norm.fillna(0) + atr_inverse_norm.fillna(0)
            return fve
        except Exception as e:
            self.logger.error(f"{NEON_RED}Error calculating FVE: {e}{RESET}")
            return pd.Series([np.nan] * len(self.df))

    def _calculate_volume_confirmation(self) -> bool:
        """
        Checks if the current volume confirms a trend (e.g., significant spike).
        Returns True if current volume is significantly higher than average.
        """
        if 'volume' not in self.df.columns or 'volume_ma' not in self.df.columns:
            self.logger.error(f"{NEON_RED}Missing 'volume' or 'volume_ma' column for Volume Confirmation.{RESET}")
            return False
        if self.df["volume"].empty or self.df["volume_ma"].empty:
            return False

        current_volume = self.df['volume'].iloc[-1]
        average_volume = self.df['volume_ma'].iloc[-1]

        if average_volume <= 0: # Avoid division by zero or nonsensical average
            return False

        return current_volume > average_volume * self.config["volume_confirmation_multiplier"]

    def analyze_order_book_walls(self, order_book: dict[str, Any]) -> tuple[bool, bool, dict[str, Decimal], dict[str, Decimal]]:
        """
        Analyzes order book for significant bid (support) and ask (resistance) walls.
        Returns whether bullish/bearish walls are found and the wall details.
        """
        has_bullish_wall = False
        has_bearish_wall = False
        bullish_wall_details: dict[str, Decimal] = {}
        bearish_wall_details: dict[str, Decimal] = {}

        if not self.config["order_book_analysis"]["enabled"]:
            return False, False, {}, {}

        if not order_book or not order_book.get('bids') or not order_book.get('asks'):
            self.logger.warning(f"{NEON_YELLOW}Order book data incomplete for wall analysis.{RESET}")
            return False, False, {}, {}

        bids = [(Decimal(price), Decimal(qty)) for price, qty in order_book['bids'][:self.config["order_book_analysis"]["depth_to_check"]]]
        asks = [(Decimal(price), Decimal(qty)) for price, qty in order_book['asks'][:self.config["order_book_analysis"]["depth_to_check"]]]

        # Calculate average quantity across relevant depth
        all_quantities = [qty for _, qty in bids + asks]
        if not all_quantities:
            return False, False, {}, {}

        avg_qty = Decimal(str(np.mean([float(q) for q in all_quantities]))) # Convert to float for numpy, then back to Decimal
        wall_threshold = avg_qty * Decimal(str(self.config["order_book_analysis"]["wall_threshold_multiplier"]))

        # Check for bullish walls (large bids below current price)
        current_price = Decimal(str(self.df["close"].iloc[-1]))
        for bid_price, bid_qty in bids:
            if bid_qty >= wall_threshold and bid_price < current_price:
                has_bullish_wall = True
                bullish_wall_details[f"Bid@{bid_price}"] = bid_qty
                self.logger.info(f"{NEON_GREEN}Detected Bullish Order Book Wall: Bid {bid_qty:.2f} at {bid_price:.2f}{RESET}")
                break # Only need to find one significant wall

        # Check for bearish walls (large asks above current price)
        for ask_price, ask_qty in asks:
            if ask_qty >= wall_threshold and ask_price > current_price:
                has_bearish_wall = True
                bearish_wall_details[f"Ask@{ask_price}"] = ask_qty
                self.logger.info(f"{NEON_RED}Detected Bearish Order Book Wall: Ask {ask_qty:.2f} at {ask_price:.2f}{RESET}")
                break # Only need to find one significant wall

        return has_bullish_wall, has_bearish_wall, bullish_wall_details, bearish_wall_details

    def analyze(self, current_price: Decimal, timestamp: str, order_book: dict[str, Any]):
        """
        Performs comprehensive analysis, calculates indicators, and logs the findings.
        This method populates `self.indicator_values` and generates the output string.
        It does NOT generate the final signal; that is done by `generate_trading_signal`.
        """
        # Ensure Decimal type for price calculations
        current_price_dec = Decimal(str(current_price))
        high_dec = Decimal(str(self.df["high"].max()))
        low_dec = Decimal(str(self.df["low"].min()))
        close_dec = Decimal(str(self.df["close"].iloc[-1]))

        # Calculate Support/Resistance Levels
        self.calculate_fibonacci_retracement(high_dec, low_dec, current_price_dec)
        self.calculate_pivot_points(high_dec, low_dec, close_dec)
        nearest_supports, nearest_resistances = self.find_nearest_levels(current_price_dec)

        # Calculate and store indicator values based on config
        if self.config["indicators"].get("obv"):
            obv_series = self._calculate_obv()
            self.indicator_values["obv"] = obv_series.iloc[-3:].tolist() if not obv_series.empty else []
        if self.config["indicators"].get("rsi"):
            rsi_series = self._calculate_rsi(window=self.config["indicator_periods"]["rsi"])
            self.indicator_values["rsi"] = rsi_series.iloc[-3:].tolist() if not rsi_series.empty else []
        if self.config["indicators"].get("mfi"):
            mfi_series = self._calculate_mfi(window=self.config["indicator_periods"]["mfi"])
            self.indicator_values["mfi"] = mfi_series.iloc[-3:].tolist() if not mfi_series.empty else []
        if self.config["indicators"].get("cci"):
            cci_series = self._calculate_cci(window=self.config["indicator_periods"]["cci"])
            self.indicator_values["cci"] = cci_series.iloc[-3:].tolist() if not cci_series.empty else []
        if self.config["indicators"].get("wr"):
            wr_series = self._calculate_williams_r(window=self.config["indicator_periods"]["williams_r"])
            self.indicator_values["wr"] = wr_series.iloc[-3:].tolist() if not wr_series.empty else []
        if self.config["indicators"].get("adx"):
            adx_value = self._calculate_adx(window=self.config["indicator_periods"]["adx"])
            self.indicator_values["adx"] = [adx_value] # ADX is a single value
        if self.config["indicators"].get("adi"):
            adi_series = self._calculate_adi()
            self.indicator_values["adi"] = adi_series.iloc[-3:].tolist() if not adi_series.empty else []
        if self.config["indicators"].get("momentum"):
            trend_data = self.determine_trend_momentum()
            self.indicator_values["mom"] = trend_data # Store dict directly
        if self.config["indicators"].get("sma_10"):
            sma_series = self._calculate_sma(10)
            self.indicator_values["sma_10"] = [sma_series.iloc[-1]] if not sma_series.empty else []
        if self.config["indicators"].get("psar"):
            psar_series = self._calculate_psar()
            self.indicator_values["psar"] = psar_series.iloc[-3:].tolist() if not psar_series.empty else []
        if self.config["indicators"].get("fve"):
            fve_series = self._calculate_fve()
            self.indicator_values["fve"] = fve_series.iloc[-3:].tolist() if not fve_series.empty else []
        if self.config["indicators"].get("macd"):
            macd_df = self._calculate_macd()
            self.indicator_values["macd"] = macd_df.iloc[-3:].values.tolist() if not macd_df.empty else []
        if self.config["indicators"].get("ema_alignment"):
            ema_alignment_score = self._calculate_ema_alignment()
            self.indicator_values["ema_alignment"] = ema_alignment_score # Store score directly

        # Order Book Analysis
        has_bullish_wall, has_bearish_wall, bullish_wall_details, bearish_wall_details = \
            self.analyze_order_book_walls(order_book)
        self.indicator_values["order_book_walls"] = {
            "bullish": has_bullish_wall, "bearish": has_bearish_wall,
            "bullish_details": bullish_wall_details, "bearish_details": bearish_wall_details
        }

        # Prepare output string
        output = f"""
{NEON_BLUE}Exchange:{RESET} Bybit
{NEON_BLUE}Symbol:{RESET} {self.symbol}
{NEON_BLUE}Interval:{RESET} {self.interval}
{NEON_BLUE}Timestamp:{RESET} {timestamp}
{NEON_BLUE}Price History:{RESET} {self.df['close'].iloc[-3]:.2f} | {self.df['close'].iloc[-2]:.2f} | {self.df['close'].iloc[-1]:.2f}
{NEON_BLUE}Volume History:{RESET} {self.df['volume'].iloc[-3]:,.0f} | {self.df['volume'].iloc[-2]:,.0f} | {self.df['volume'].iloc[-1]:,.0f}
{NEON_BLUE}Current Price:{RESET} {current_price_dec:.5f}
{NEON_BLUE}ATR ({self.config['atr_period']}):{RESET} {self.atr_value:.5f}
{NEON_BLUE}Trend:{RESET} {self.indicator_values.get("mom", {}).get("trend", "N/A")} (Strength: {self.indicator_values.get("mom", {}).get("strength", 0.0):.2f})
"""
        # Append indicator interpretations
        for indicator_name, values in self.indicator_values.items():
            # Skip indicators that are already logged in a custom format or are internal
            if indicator_name in ['mom', 'atr', 'stoch_rsi_vals', 'ema_alignment', 'order_book_walls']:
                continue
            interpreted_line = interpret_indicator(self.logger, indicator_name, values)
            if interpreted_line:
                output += interpreted_line + "\n"

        # Custom logging for specific indicators
        if self.config["indicators"].get("ema_alignment"):
            ema_alignment_score = self.indicator_values.get("ema_alignment", 0.0)
            status = 'Bullish' if ema_alignment_score > 0 else 'Bearish' if ema_alignment_score < 0 else 'Neutral'
            output += f"{NEON_PURPLE}EMA Alignment:{RESET} Score={ema_alignment_score:.2f} ({status})\n"

        if self.config["indicators"].get("stoch_rsi") and self.indicator_values.get("stoch_rsi_vals") is not None and not self.indicator_values["stoch_rsi_vals"].empty:
            stoch_rsi_df = self.indicator_values["stoch_rsi_vals"]
            if not stoch_rsi_df.empty:
                output += f"{NEON_GREEN}Stoch RSI:{RESET} K={stoch_rsi_df['k'].iloc[-1]:.2f}, D={stoch_rsi_df['d'].iloc[-1]:.2f}, Stoch_RSI={stoch_rsi_df['stoch_rsi'].iloc[-1]:.2f}\n"

        # Order Book Wall Logging
        output += f"\n{NEON_BLUE}Order Book Walls:{RESET}\n"
        if has_bullish_wall:
            output += f"{NEON_GREEN}  Bullish Walls Found: {', '.join([f'{k}:{v:.2f}' for k,v in bullish_wall_details.items()])}{RESET}\n"
        if has_bearish_wall:
            output += f"{NEON_RED}  Bearish Walls Found: {', '.join([f'{k}:{v:.2f}' for k,v in bearish_wall_details.items()])}{RESET}\n"
        if not has_bullish_wall and not has_bearish_wall:
            output += "  No significant walls detected.\n"


        output += f"""
{NEON_BLUE}Support and Resistance Levels:{RESET}
"""
        for s_label, s_val in nearest_supports:
            output += f"S: {s_label} ${s_val:.5f}\n"
        for r_label, r_val in nearest_resistances:
            output += f"R: {r_label} ${r_val:.5f}\n"

        self.logger.info(output)

    def generate_trading_signal(self, current_price: Decimal) -> tuple[str | None, float, list[str], dict[str, Decimal]]:
        """
        Generates a trading signal (buy/sell) based on indicator values and configuration.
        Returns the signal, its confidence score, conditions met, and suggested SL/TP levels.
        """
        signal_score = Decimal('0.0')
        signal = None
        conditions_met: list[str] = []
        trade_levels: dict[str, Decimal] = {}

        # --- Bullish Signal Logic ---
        # Sum weights of bullish conditions met
        if self.config["indicators"].get("stoch_rsi") and not self.indicator_values["stoch_rsi_vals"].empty:
            stoch_rsi_k = Decimal(str(self.indicator_values["stoch_rsi_vals"]['k'].iloc[-1]))
            stoch_rsi_d = Decimal(str(self.indicator_values["stoch_rsi_vals"]['d'].iloc[-1]))
            if stoch_rsi_k < self.config["stoch_rsi_oversold_threshold"] and stoch_rsi_k > stoch_rsi_d:
                signal_score += Decimal(str(self.user_defined_weights["stoch_rsi"]))
                conditions_met.append("Stoch RSI Oversold Crossover")

        if self.config["indicators"].get("rsi") and self.indicator_values.get("rsi") and self.indicator_values["rsi"][-1] < 30:
            signal_score += Decimal(str(self.user_defined_weights["rsi"]))
            conditions_met.append("RSI Oversold")

        if self.config["indicators"].get("mfi") and self.indicator_values.get("mfi") and self.indicator_values["mfi"][-1] < 20:
            signal_score += Decimal(str(self.user_defined_weights["mfi"]))
            conditions_met.append("MFI Oversold")

        if self.config["indicators"].get("ema_alignment") and self.indicator_values.get("ema_alignment", 0.0) > 0:
            signal_score += Decimal(str(self.user_defined_weights["ema_alignment"])) * Decimal(str(abs(self.indicator_values["ema_alignment"]))) # Scale by score
            conditions_met.append("Bullish EMA Alignment")

        if self.config["indicators"].get("volume_confirmation") and self._calculate_volume_confirmation():
            signal_score += Decimal(str(self.user_defined_weights["volume_confirmation"]))
            conditions_met.append("Volume Confirmation")

        if self.config["indicators"].get("divergence") and self.detect_macd_divergence() == "bullish":
            signal_score += Decimal(str(self.user_defined_weights["divergence"]))
            conditions_met.append("Bullish MACD Divergence")

        if self.indicator_values["order_book_walls"].get("bullish"):
            signal_score += Decimal(str(self.config["order_book_support_confidence_boost"] / 10.0)) # Boost score for order book wall
            conditions_met.append("Bullish Order Book Wall")

        # Final check for Bullish signal
        if signal_score >= Decimal(str(self.config["signal_score_threshold"])):
            signal = "buy"
            # Calculate Stop Loss and Take Profit
            if self.atr_value > 0:
                stop_loss = current_price - (Decimal(str(self.atr_value)) * Decimal(str(self.config["stop_loss_multiple"])))
                take_profit = current_price + (Decimal(str(self.atr_value)) * Decimal(str(self.config["take_profit_multiple"])))
                trade_levels["stop_loss"] = stop_loss.quantize(Decimal('0.00001'))
                trade_levels["take_profit"] = take_profit.quantize(Decimal('0.00001'))

        # --- Bearish Signal Logic (similar structure) ---
        bearish_score = Decimal('0.0')
        bearish_conditions: list[str] = []

        if self.config["indicators"].get("stoch_rsi") and not self.indicator_values["stoch_rsi_vals"].empty:
            stoch_rsi_k = Decimal(str(self.indicator_values["stoch_rsi_vals"]['k'].iloc[-1]))
            stoch_rsi_d = Decimal(str(self.indicator_values["stoch_rsi_vals"]['d'].iloc[-1]))
            if stoch_rsi_k > self.config["stoch_rsi_overbought_threshold"] and stoch_rsi_k < stoch_rsi_d:
                bearish_score += Decimal(str(self.user_defined_weights["stoch_rsi"]))
                bearish_conditions.append("Stoch RSI Overbought Crossover")

        if self.config["indicators"].get("rsi") and self.indicator_values.get("rsi") and self.indicator_values["rsi"][-1] > 70:
            bearish_score += Decimal(str(self.user_defined_weights["rsi"]))
            bearish_conditions.append("RSI Overbought")

        if self.config["indicators"].get("mfi") and self.indicator_values.get("mfi") and self.indicator_values["mfi"][-1] > 80:
            bearish_score += Decimal(str(self.user_defined_weights["mfi"]))
            bearish_conditions.append("MFI Overbought")

        if self.config["indicators"].get("ema_alignment") and self.indicator_values.get("ema_alignment", 0.0) < 0:
            bearish_score += Decimal(str(self.user_defined_weights["ema_alignment"])) * Decimal(str(abs(self.indicator_values["ema_alignment"])))
            bearish_conditions.append("Bearish EMA Alignment")

        if self.config["indicators"].get("divergence") and self.detect_macd_divergence() == "bearish":
            bearish_score += Decimal(str(self.user_defined_weights["divergence"]))
            bearish_conditions.append("Bearish MACD Divergence")

        if self.indicator_values["order_book_walls"].get("bearish"):
            bearish_score += Decimal(str(self.config["order_book_resistance_confidence_boost"] / 10.0))
            bearish_conditions.append("Bearish Order Book Wall")


        # Final check for Bearish signal (only if no bullish signal already)
        if signal is None and bearish_score >= Decimal(str(self.config["signal_score_threshold"])):
            signal = "sell"
            signal_score = bearish_score # Use bearish score if it's the chosen signal
            conditions_met = bearish_conditions # Use bearish conditions
            # Calculate Stop Loss and Take Profit for sell signal
            if self.atr_value > 0:
                stop_loss = current_price + (Decimal(str(self.atr_value)) * Decimal(str(self.config["stop_loss_multiple"])))
                take_profit = current_price - (Decimal(str(self.atr_value)) * Decimal(str(self.config["take_profit_multiple"])))
                trade_levels["stop_loss"] = stop_loss.quantize(Decimal('0.00001'))
                trade_levels["take_profit"] = take_profit.quantize(Decimal('0.00001'))

        return signal, float(signal_score), conditions_met, trade_levels


def interpret_indicator(logger: logging.Logger, indicator_name: str, values: list[float] | float | dict[str, Any]) -> str | None:
    """
    Provides a human-readable interpretation of indicator values.
    """
    if values is None or (isinstance(values, list) and not values) or (isinstance(values, pd.DataFrame) and values.empty):
        return f"{NEON_YELLOW}{indicator_name.upper()}:{RESET} No data available."
    try:
        # Convert single float values to list for consistent indexing if needed
        if isinstance(values, (float, int)):
            values = [values]
        elif isinstance(values, dict): # For 'mom' which is a dict
            if indicator_name == "mom":
                trend = values.get("trend", "N/A")
                strength = values.get("strength", 0.0)
                return f"{NEON_PURPLE}Momentum Trend:{RESET} {trend} (Strength: {strength:.2f})"
            else:
                return f"{NEON_YELLOW}{indicator_name.upper()}:{RESET} Dictionary format not specifically interpreted."
        elif isinstance(values, pd.DataFrame): # For stoch_rsi_vals which is a DataFrame
            if indicator_name == "stoch_rsi_vals":
                # Stoch RSI interpretation is handled directly in analyze function
                return None
            else:
                return f"{NEON_YELLOW}{indicator_name.upper()}:{RESET} DataFrame format not specifically interpreted."


        # Interpret based on indicator name
        last_value = values[-1] if isinstance(values, list) and values else values[0] if isinstance(values, list) else values # Handles single value lists too

        if indicator_name == "rsi":
            if last_value > 70:
                return f"{NEON_RED}RSI:{RESET} Overbought ({last_value:.2f})"
            elif last_value < 30:
                return f"{NEON_GREEN}RSI:{RESET} Oversold ({last_value:.2f})"
            else:
                return f"{NEON_YELLOW}RSI:{RESET} Neutral ({last_value:.2f})"
        elif indicator_name == "mfi":
            if last_value > 80:
                return f"{NEON_RED}MFI:{RESET} Overbought ({last_value:.2f})"
            elif last_value < 20:
                return f"{NEON_GREEN}MFI:{RESET} Oversold ({last_value:.2f})"
            else:
                return f"{NEON_YELLOW}MFI:{RESET} Neutral ({last_value:.2f})"
        elif indicator_name == "cci":
            if last_value > 100:
                return f"{NEON_RED}CCI:{RESET} Overbought ({last_value:.2f})"
            elif last_value < -100:
                return f"{NEON_GREEN}CCI:{RESET} Oversold ({last_value:.2f})"
            else:
                return f"{NEON_YELLOW}CCI:{RESET} Neutral ({last_value:.2f})"
        elif indicator_name == "wr":
            if last_value < -80:
                return f"{NEON_GREEN}Williams %R:{RESET} Oversold ({last_value:.2f})"
            elif last_value > -20:
                return f"{NEON_RED}Williams %R:{RESET} Overbought ({last_value:.2f})"
            else:
                return f"{NEON_YELLOW}Williams %R:{RESET} Neutral ({last_value:.2f})"
        elif indicator_name == "adx":
            if last_value > 25:
                return f"{NEON_GREEN}ADX:{RESET} Trending ({last_value:.2f})"
            else:
                return f"{NEON_YELLOW}ADX:{RESET} Ranging ({last_value:.2f})"
        elif indicator_name == "obv":
            if len(values) >= 2:
                return f"{NEON_BLUE}OBV:{RESET} {'Bullish' if values[-1] > values[-2] else 'Bearish' if values[-1] < values[-2] else 'Neutral'}"
            else:
                return f"{NEON_BLUE}OBV:{RESET} {last_value:.2f} (Insufficient history for trend)"
        elif indicator_name == "adi":
            if len(values) >= 2:
                return f"{NEON_BLUE}ADI:{RESET} {'Accumulation' if values[-1] > values[-2] else 'Distribution' if values[-1] < values[-2] else 'Neutral'}"
            else:
                return f"{NEON_BLUE}ADI:{RESET} {last_value:.2f} (Insufficient history for trend)"
        elif indicator_name == "sma_10":
            return f"{NEON_YELLOW}SMA (10):{RESET} {last_value:.2f}"
        elif indicator_name == "psar":
            return f"{NEON_BLUE}PSAR:{RESET} {last_value:.4f} (Last Value)"
        elif indicator_name == "fve":
            return f"{NEON_BLUE}FVE:{RESET} {last_value:.2f} (Last Value)"
        elif indicator_name == "macd":
            # values for MACD are [macd_line, signal_line, histogram]
            if len(values[-1]) == 3:
                macd_line, signal_line, histogram = values[-1][0], values[-1][1], values[-1][2]
                return f"{NEON_GREEN}MACD:{RESET} MACD={macd_line:.2f}, Signal={signal_line:.2f}, Histogram={histogram:.2f}"
            else:
                return f"{NEON_RED}MACD:{RESET} Calculation issue."
        else:
            return f"{NEON_YELLOW}{indicator_name.upper()}:{RESET} No specific interpretation available."
    except (TypeError, IndexError, KeyError, ValueError) as e:
        logger.error(f"{NEON_RED}Error interpreting {indicator_name}: {e}. Values: {values}{RESET}")
        return f"{NEON_RED}{indicator_name.upper()}:{RESET} Interpretation error."


def main():
    """
    Main function to run the trading analysis bot.
    Handles user input, data fetching, analysis, and signal generation loop.
    """
    if not API_KEY or not API_SECRET:
        logger.error(f"{NEON_RED}BYBIT_API_KEY and BYBIT_API_SECRET must be set in your .env file.{RESET}")
        return

    symbol_input = input(f"{NEON_BLUE}Enter trading symbol (e.g., BTCUSDT): {RESET}").upper().strip()
    symbol = symbol_input if symbol_input else "BTCUSDT"

    interval_input = input(f"{NEON_BLUE}Enter timeframe (e.g., {', '.join(VALID_INTERVALS)} or press Enter for default {CONFIG['interval']}): {RESET}").strip()
    interval = interval_input if interval_input and interval_input in VALID_INTERVALS else CONFIG["interval"]

    # Setup a dedicated logger for this symbol's activities
    symbol_logger = setup_custom_logger(symbol)
    symbol_logger.info(f"{NEON_BLUE}Starting analysis for {symbol} with interval {interval}{RESET}")

    last_signal_time = 0.0 # Tracks the last time a signal was triggered for cooldown
    last_order_book_fetch_time = 0.0 # Tracks last order book fetch time for debouncing

    while True:
        try:
            current_price = fetch_current_price(symbol, API_KEY, API_SECRET, symbol_logger)
            if current_price is None:
                symbol_logger.error(f"{NEON_RED}Failed to fetch current price for {symbol}. Skipping cycle.{RESET}")
                time.sleep(CONFIG["retry_delay"])
                continue

            df = fetch_klines(symbol, interval, API_KEY, API_SECRET, symbol_logger, limit=200)
            if df.empty:
                symbol_logger.error(f"{NEON_RED}Failed to fetch Kline data for {symbol}. Skipping cycle.{RESET}")
                time.sleep(CONFIG["retry_delay"])
                continue

            # Debounce order book fetching to reduce API calls
            order_book_data = None
            if time.time() - last_order_book_fetch_time >= CONFIG["order_book_debounce_s"]:
                order_book_data = fetch_order_book(symbol, API_KEY, API_SECRET, symbol_logger, limit=CONFIG["order_book_depth_to_check"])
                last_order_book_fetch_time = time.time()
            else:
                symbol_logger.debug(f"{NEON_YELLOW}Order book fetch debounced. Next fetch in {CONFIG['order_book_debounce_s'] - (time.time() - last_order_book_fetch_time):.1f}s{RESET}")


            analyzer = TradingAnalyzer(df, CONFIG, symbol_logger, symbol, interval)
            timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")

            # Perform analysis and log the current state of indicators
            analyzer.analyze(current_price, timestamp, order_book_data)

            # Generate trading signal based on the analysis
            current_time_seconds = time.time()
            signal, confidence, conditions_met, trade_levels = analyzer.generate_trading_signal(current_price)

            if signal and (current_time_seconds - last_signal_time >= CONFIG["signal_cooldown_s"]):
                symbol_logger.info(f"\n{NEON_PURPLE}--- TRADING SIGNAL TRIGGERED ---{RESET}")
                symbol_logger.info(f"{NEON_BLUE}Signal:{RESET} {signal.upper()} (Confidence: {confidence:.2f})")
                symbol_logger.info(f"{NEON_BLUE}Conditions Met:{RESET} {', '.join(conditions_met) if conditions_met else 'None'}")
                if trade_levels:
                    symbol_logger.info(f"{NEON_GREEN}Suggested Stop Loss:{RESET} {trade_levels.get('stop_loss'):.5f}")
                    symbol_logger.info(f"{NEON_GREEN}Suggested Take Profit:{RESET} {trade_levels.get('take_profit'):.5f}")
                symbol_logger.info(f"{NEON_YELLOW}--- Placeholder: Order placement logic would be here for {signal.upper()} signal ---{RESET}")
                last_signal_time = current_time_seconds # Update last signal time

            time.sleep(CONFIG["analysis_interval"])

        except requests.exceptions.RequestException as e:
            symbol_logger.error(f"{NEON_RED}Network or API communication error: {e}. Retrying in {CONFIG['retry_delay']} seconds...{RESET}")
            time.sleep(CONFIG["retry_delay"])
        except KeyboardInterrupt:
            symbol_logger.info(f"{NEON_YELLOW}Analysis stopped by user.{RESET}")
            break
        except Exception as e:
            symbol_logger.exception(f"{NEON_RED}An unexpected error occurred: {e}. Retrying in {CONFIG['retry_delay']} seconds...{RESET}")
            time.sleep(CONFIG["retry_delay"])

if __name__ == "__main__":
    main()
