import os
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import hmac
import hashlib
import time
from dotenv import load_dotenv
from typing import Dict, Tuple, List, Union
from colorama import init, Fore, Style
from zoneinfo import ZoneInfo
from logger_config import setup_custom_logger  # Assuming logger_config.py exists
from decimal import Decimal, getcontext
import json

getcontext().prec = 10
logger = setup_custom_logger('whalebot')
init(autoreset=True)
load_dotenv()

API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
if not API_KEY or not API_SECRET:
    raise ValueError("BYBIT_API_KEY and BYBIT_API_SECRET must be set in .env")
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs"
TIMEZONE = ZoneInfo("America/Chicago")
MAX_API_RETRIES = 3
RETRY_DELAY_SECONDS = 5
VALID_INTERVALS = ["1", "3", "5", "15", "30", "60", "120", "240", "D", "W", "M"]
RETRY_ERROR_CODES = [429, 500, 502, 503, 504]
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
RESET = Style.RESET_ALL

os.makedirs(LOG_DIRECTORY, exist_ok=True)

def load_config(filepath: str) -> dict:
    default_config = {
        "interval": "15",
        "analysis_interval": 30,
        "retry_delay": 5,
        "momentum_period": 10,
        "momentum_ma_short": 12,
        "momentum_ma_long": 26,
        "volume_ma_period": 20,
        "atr_period": 14,
        "trend_strength_threshold": 0.4,
        "sideways_atr_multiplier": 1.5,
        "signal_score_threshold": 1.0, # New: Configurable signal score threshold
        "indicators": {
            "ema_alignment": True, # New: EMA Alignment Indicator
            "momentum": True,
            "volume_confirmation": True, # New: Volume Confirmation Indicator
            "divergence": True,
            "stoch_rsi": True,
            "rsi": True,  # Enabled RSI by default
            "macd": True, # Enabled MACD by default
            "vwap": False, # VWAP remains disabled by default
            "obv": True,
            "adi": True,
            "cci": True,
            "wr": True,
            "adx": True,
            "psar": True,
            "fve": True, # Enabled FVE by default
            "sma_10": False, # Example SMA, disabled by default
        },
        "weight_sets": {
            "low_volatility": {
                "ema_alignment": 0.3, # New: Weight for EMA Alignment
                "momentum": 0.2,
                "volume_confirmation": 0.2, # New: Weight for Volume Confirmation
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
                "fve": 0.2, # Weight for FVE
                "sma_10": 0.0, # Example SMA weight
            },
            "high_volatility": { # Example of another weight set
                "ema_alignment": 0.1, # New: Weight for EMA Alignment in high volatility
                "momentum": 0.4,
                "volume_confirmation": 0.1, # New: Weight for Volume Confirmation in high volatility
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
                "fve": 0.3, # Weight for FVE in high volatility
                "sma_10": 0.0, # Example SMA weight
            }
        },
        "stoch_rsi_oversold_threshold": 20,
        "stoch_rsi_overbought_threshold": 80,
        "stoch_rsi_confidence_boost": 5,
        "stoch_rsi_mandatory": False, # Example - could be used to require Stoch RSI for signals
        "rsi_confidence_boost" : 2,
        "mfi_confidence_boost" : 2,
        "order_book_support_confidence_boost" : 3,
        "order_book_resistance_confidence_boost" : 3,
        "stop_loss_multiple" : 1.5,
        "take_profit_multiple" : 1,
        "order_book_wall_threshold_multiplier" : 2,
        "order_book_depth_to_check" : 10,
        "price_change_threshold" : 0.005,
        "atr_change_threshold" : 0.005,
        "signal_cooldown_s": 60,
        "order_book_debounce_s": 1,
        "ema_short_period": 12, # New: Configurable EMA short period
        "ema_long_period": 26,  # New: Configurable EMA long period
        "volume_confirmation_multiplier": 1.5, # New: Configurable volume confirmation multiplier
    }
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            config = json.load(f)
            # Merge loaded config with defaults, prioritizing loaded values
            merged_config = {**default_config, **config}

            # Basic validation for interval and analysis_interval
            if merged_config.get("interval") not in VALID_INTERVALS:
                logger.warning(f"{NEON_YELLOW}Invalid interval in config, using default: {default_config['interval']}{RESET}")
                merged_config["interval"] = default_config["interval"]
            if not isinstance(merged_config.get("analysis_interval"), int) or merged_config.get("analysis_interval") <= 0:
                logger.warning(f"{NEON_YELLOW}Invalid analysis_interval in config, using default: {default_config['analysis_interval']}{RESET}")
                merged_config["analysis_interval"] = default_config["analysis_interval"]

            return merged_config
    except FileNotFoundError:
        print(f"{NEON_YELLOW}Config file not found, loading defaults and creating {filepath}{RESET}")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4)
        return default_config
    except json.JSONDecodeError:
        print(f"{NEON_YELLOW}Invalid JSON in config file, loading defaults.{RESET}")
        return default_config

CONFIG = load_config(CONFIG_FILE)

def setup_symbol_logger(symbol: str) -> logging.Logger:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(LOG_DIRECTORY, f"{symbol}_{timestamp}.log")
    symbol_logger = logging.getLogger(symbol)
    symbol_logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(log_filename)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    symbol_logger.addHandler(file_handler)
    stream_handler = logging.StreamHandler()
    stream_formatter = logging.Formatter(NEON_BLUE + "%(asctime)s" + RESET + " - %(levelname)s - %(message)s")
    stream_handler.setFormatter(stream_formatter)
    symbol_logger.addHandler(stream_handler)
    return symbol_logger

def generate_signature(api_secret: str, params: dict) -> str:
    param_str = "&".join([f"{key}={value}" for key, value in sorted(params.items())])
    return hmac.new(api_secret.encode(), param_str.encode(), hashlib.sha256).hexdigest()

def handle_api_error(response: requests.Response, logger: logging.Logger) -> None:
    if response.status_code != 200:
        logger.error(f"{NEON_RED}API request failed with status code: {response.status_code}{RESET}")
        try:
            error_json = response.json()
            logger.error(f"{NEON_RED}Error details: {error_json}{RESET}")
        except json.JSONDecodeError:
            logger.error(f"{NEON_RED}Response text: {response.text}{RESET}")

def bybit_request(method: str, endpoint: str, api_key: str, api_secret: str, params: dict = None, logger: logging.Logger = None) -> Union[dict, None]:
    params = params or {}
    params['timestamp'] = str(int(time.time() * 1000))
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
            response = requests.request(method, url, headers=headers, params=params if method == "GET" else None, json=params if method == "POST" else None, timeout=10)
            if response.status_code == 200:
                return response.json()
            elif response.status_code in RETRY_ERROR_CODES:
                if logger:
                    logger.warning(f"{NEON_YELLOW}Rate limit or server error, retrying {retry + 1}/{MAX_API_RETRIES}...{RESET}")
                time.sleep(RETRY_DELAY_SECONDS * (2**retry))
            else:
                if logger:
                    handle_api_error(response, logger)
                return None
        except requests.exceptions.RequestException as e:
            if logger:
                logger.error(f"{NEON_RED}Request exception: {e}, retrying {retry + 1}/{MAX_API_RETRIES}...{RESET}")
            time.sleep(RETRY_DELAY_SECONDS * (2**retry))
    if logger:
        logger.error(f"{NEON_RED}Max retries reached for {method} {endpoint}{RESET}")
    return None

def fetch_current_price(symbol: str, api_key: str, api_secret: str, logger: logging.Logger) -> Union[Decimal, None]:
    endpoint = "/v5/market/tickers"
    params = {"category": "linear", "symbol": symbol}
    response_data = bybit_request("GET", endpoint, api_key, api_secret, params, logger)
    if response_data and response_data.get("retCode") == 0 and response_data.get("result"):
        tickers = response_data["result"].get("list",)
        for ticker in tickers:
            if ticker.get("symbol") == symbol:
                last_price = ticker.get("lastPrice")
                return Decimal(last_price) if last_price else None
    return None

def fetch_klines(symbol: str, interval: str, api_key: str, api_secret: str, logger: logging.Logger, limit: int = 200) -> pd.DataFrame:
    endpoint = "/v5/market/kline"
    params = {"symbol": symbol, "interval": interval, "limit": limit, "category": "linear"}
    response_data = bybit_request("GET", endpoint, api_key, api_secret, params, logger)
    if response_data and response_data.get("retCode") == 0 and response_data.get("result") and response_data["result"].get("list"):
        data = response_data["result"]["list"]
        columns = ["start_time", "open", "high", "low", "close", "volume", "turnover"][:len(data[0])]
        df = pd.DataFrame(data, columns=columns)
        df["start_time"] = pd.to_datetime(df["start_time"], unit="ms")
        for col in df.columns[1:]: # Convert columns after 'start_time' to numeric
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    return pd.DataFrame()

def fetch_order_book(symbol: str, api_key: str, api_secret: str, logger: logging.Logger, limit: int = 50) -> Union[dict, None]: # Function to fetch order book
    endpoint = "/v5/market/orderbook"
    params = {"symbol": symbol, "limit": limit, "category": "linear"}
    response_data = bybit_request("GET", endpoint, api_key, api_secret, params, logger)
    if response_data and response_data.get("retCode") == 0 and response_data.get("result"):
        return response_data["result"]
    return None

class TradingAnalyzer:
    def __init__(self, df: pd.DataFrame, config: dict, symbol_logger: logging.Logger, symbol: str, interval: str):
        self.df = df
        self.config = config
        self.logger = symbol_logger
        self.symbol = symbol
        self.interval = interval
        self.levels = {}
        self.fib_levels = {}
        self.weight_sets = config["weight_sets"]
        self.user_defined_weights = self._select_weight_set() # Select weight set dynamically
        self.stoch_rsi_df = self._calculate_stoch_rsi()
        self.indicator_values = {} # Initialize indicator_values here

    def _select_weight_set(self): # Function to select weight set based on volatility (ATR)
        atr_value = self._calculate_atr(window=14).iloc[-1] if not self.df.empty and len(self.df) >= 14 else 0
        if atr_value > self.config["atr_change_threshold"]: # Example threshold for high volatility
            return self.weight_sets.get("high_volatility", self.weight_sets["low_volatility"]) # Default to low_volatility if high_volatility not defined
        return self.weight_sets["low_volatility"] # Default to low volatility

    def _calculate_sma(self, window: int) -> pd.Series:
        if 'close' not in self.df.columns:
            self.logger.error(f"{NEON_RED}Missing 'close' column for SMA calculation{RESET}")
            return pd.Series(dtype=float)
        return self.df["close"].rolling(window=window).mean()

    def _calculate_ema_alignment(self) -> float: # New: Function to calculate EMA alignment score
        ema_short = self._calculate_ema(self.config["ema_short_period"])
        ema_long = self._calculate_ema(self.config["ema_long_period"])
        if ema_short.empty or ema_long.empty:
            return 0.0

        # Alignment logic: Higher score if short EMA is significantly above long EMA (uptrend) or significantly below (downtrend)
        latest_short_ema = ema_short.iloc[-1]
        latest_long_ema = ema_long.iloc[-1]
        current_price = self.df["close"].iloc[-1]

        if latest_short_ema > latest_long_ema and current_price > latest_short_ema: # Bullish alignment
            return 1.0 # Full bullish alignment
        elif latest_short_ema < latest_long_ema and current_price < latest_short_ema: # Bearish alignment
            return -1.0 # Full bearish alignment
        else:
            return 0.0 # Neutral alignment


    def _calculate_momentum(self, period: int = 10) -> pd.Series:
        if 'close' not in self.df.columns:
            self.logger.error(f"{NEON_RED}Missing 'close' column for Momentum calculation{RESET}")
            return pd.Series(dtype=float)
        return ((self.df["close"] - self.df["close"].shift(period)) / self.df["close"].shift(period)) * 100

    def _calculate_cci(self, window: int = 20, constant: float = 0.015) -> pd.Series:
        required_columns = ['high', 'low', 'close']
        for col in required_columns:
            if col not in self.df.columns:
                self.logger.error(f"{NEON_RED}Missing '{col}' column for CCI calculation{RESET}")
                return pd.Series(dtype=float)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_typical_price = typical_price.rolling(window=window).mean()
        mean_deviation = typical_price.rolling(window=window).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        return (typical_price - sma_typical_price) / (constant * mean_deviation)

    def _calculate_williams_r(self, window: int = 14) -> pd.Series:
        required_columns = ['high', 'low', 'close']
        for col in required_columns:
            if col not in self.df.columns:
                self.logger.error(f"{NEON_RED}Missing '{col}' column for Williams %R calculation{RESET}")
                return pd.Series(dtype=float)
        highest_high = self.df["high"].rolling(window=window).max()
        lowest_low = self.df["low"].rolling(window=window).min()
        return (highest_high - self.df["close"]) / (highest_high - lowest_low) * -100

    def _calculate_mfi(self, window: int = 14) -> pd.Series:
        required_columns = ['high', 'low', 'close', 'volume']
        for col in required_columns:
            if col not in self.df.columns:
                self.logger.error(f"{NEON_RED}Missing '{col}' column for MFI calculation{RESET}")
                return pd.Series(dtype=float)
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        raw_money_flow = typical_price * self.df["volume"]
        positive_flow = pd.Series([mf if tp > tp_prev else 0 for tp, tp_prev, mf in zip(typical_price[1:], typical_price[:-1], raw_money_flow[1:])])
        negative_flow = pd.Series([mf if tp < tp_prev else 0 for tp, tp_prev, mf in zip(typical_price[1:], typical_price[:-1], raw_money_flow[1:])])
        positive_mf = positive_flow.rolling(window=window).sum()
        negative_mf = negative_flow.rolling(window=window).sum()
        money_ratio = positive_mf / negative_mf
        return 100 - (100 / (1 + money_ratio))

    def calculate_fibonacci_retracement(self, high: float, low: float, current_price: float) -> Dict[str, float]:
        diff = high - low
        if diff == 0:
            return {}
        fib_levels = {
            "Fib 23.6%": high - diff * 0.236,
            "Fib 38.2%": high - diff * 0.382,
            "Fib 50.0%": high - diff * 0.5,
            "Fib 61.8%": high - diff * 0.618,
            "Fib 78.6%": high - diff * 0.786,
            "Fib 88.6%": high - diff * 0.886,
            "Fib 94.1%": high - diff * 0.941,
        }
        self.levels = {"Support": {}, "Resistance": {}}
        for label, value in fib_levels.items():
            if value < current_price:
                self.levels["Support"][label] = value
            elif value > current_price:
                self.levels["Resistance"][label] = value
        self.fib_levels = fib_levels
        return self.fib_levels

    def calculate_pivot_points(self, high: float, low: float, close: float):
        pivot = (high + low + close) / 3
        r1 = (2 * pivot) - low
        s1 = (2 * pivot) - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)
        r3 = high + 2 * (pivot - low)
        s3 = low - 2 * (high - pivot)
        self.levels = {
            "pivot": pivot,
            "r1": r1,
            "s1": s1,
            "r2": r2,
            "s2": s2,
            "r3": r3,
            "s3": s3,
        }

    def find_nearest_levels(self, current_price: float, num_levels: int = 5) -> Tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
        support_levels = []
        resistance_levels = []

        def process_level(label, value):
            if value < current_price:
                support_levels.append((label, value))
            elif value > current_price:
                resistance_levels.append((label, value))

        for label, value in self.levels.items():
            if isinstance(value, dict):
                for sub_label, sub_value in value.items():
                    if isinstance(sub_value, (float, Decimal)):
                        process_level(f"{label} ({sub_label})", sub_value)
            elif isinstance(value, (float, Decimal)):
                process_level(label, value)

        nearest_supports = sorted(
            support_levels, key=lambda x: abs(x[1] - current_price)
        )[:num_levels][::-1] # Modified sorting for supports
        nearest_resistances = sorted(
            resistance_levels, key=lambda x: abs(x[1] - current_price)
        )[:num_levels]
        return nearest_supports, nearest_resistances

    def _calculate_atr(self, window: int = 20) -> pd.Series:
        required_columns = ['high', 'low', 'close']
        for col in required_columns:
            if col not in self.df.columns:
                self.logger.error(f"{NEON_RED}Missing '{col}' column for ATR calculation{RESET}")
                return pd.Series(dtype=float)
        high_low = self.df["high"] - self.df["low"]
        high_close = abs(self.df["high"] - self.df["close"].shift())
        low_close = abs(self.df["low"] - self.df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=window).mean()

    def _calculate_rsi(self, window: int = 14) -> pd.Series:
        if 'close' not in self.df.columns:
            self.logger.error(f"{NEON_RED}Missing 'close' column for RSI calculation{RESET}")
            return pd.Series(dtype=float)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=window).mean()
        avg_loss = loss.rolling(window=window).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _calculate_stoch_rsi(self, rsi_window: int = 14, stoch_window: int = 14, k_window: int = 3, d_window: int = 3) -> pd.DataFrame:
        rsi = self._calculate_rsi(window=rsi_window)
        if rsi.empty:
            return pd.DataFrame()
        stoch_rsi = (rsi - rsi.rolling(stoch_window).min()) / (rsi.rolling(stoch_window).max() - rsi.rolling(stoch_window).min())
        k_line = stoch_rsi.rolling(window=k_window).mean()
        d_line = k_line.rolling(window=d_window).mean()
        return pd.DataFrame({'stoch_rsi': stoch_rsi, 'k': k_line, 'd': d_line})

    def _calculate_momentum_ma(self) -> None:
        if 'close' not in self.df.columns or 'volume' not in self.df.columns:
            self.logger.error(f"{NEON_RED}Missing 'close' or 'volume' column for Momentum MA calculation{RESET}")
            return
        self.df["momentum"] = self.df["close"].diff(self.config["momentum_period"])
        self.df["momentum_ma_short"] = self.df["momentum"].rolling(window=self.config["momentum_ma_short"]).mean()
        self.df["momentum_ma_long"] = self.df["momentum"].rolling(window=self.config["momentum_ma_long"]).mean()
        self.df["volume_ma"] = self.df["volume"].rolling(window=self.config["volume_ma_period"]).mean()

    def _calculate_macd(self) -> pd.DataFrame:
        if 'close' not in self.df.columns:
            self.logger.error(f"{NEON_RED}Missing 'close' column for MACD calculation{RESET}")
            return pd.DataFrame()
        ma_short = self.df["close"].ewm(span=12, adjust=False).mean()
        ma_long = self.df["close"].ewm(span=26, adjust=False).mean()
        macd = ma_short - ma_long
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal
        return pd.DataFrame({'macd': macd, 'signal': signal, 'histogram': histogram})

    def detect_macd_divergence(self) -> str | None:
        macd_df = self._calculate_macd()
        if macd_df.empty or len(self.df) < 30:
            return None
        prices = self.df["close"]
        macd_histogram = macd_df["histogram"]
        if prices.iloc[-2] > prices.iloc[-1] and macd_histogram.iloc[-2] < macd_histogram.iloc[-1]:
            return "bullish"
        elif prices.iloc[-2] < prices.iloc[-1] and macd_histogram.iloc[-2] > macd_histogram.iloc[-1]:
            return "bearish"
        return None

    def _calculate_ema(self, window: int) -> pd.Series:
        if 'close' not in self.df.columns:
            self.logger.error(f"{NEON_RED}Missing 'close' column for EMA calculation{RESET}")
            return pd.Series(dtype=float)
        return self.df["close"].ewm(span=window, adjust=False).mean()

    def determine_trend_momentum(self) -> dict:
        if self.df.empty or len(self.df) < 26:
            return {"trend": "Insufficient Data", "strength": 0}
        atr = self._calculate_atr()
        if atr.iloc[-1] == 0:
            self.logger.warning(f"{NEON_YELLOW}ATR is zero, cannot calculate trend strength.{RESET}")
            return {"trend": "Neutral", "strength": 0}
        self._calculate_momentum_ma()
        if self.df["momentum_ma_short"].iloc[-1] > self.df["momentum_ma_long"].iloc[-1]:
            trend = "Uptrend"
        elif self.df["momentum_ma_short"].iloc[-1] < self.df["momentum_ma_long"].iloc[-1]:
            trend = "Downtrend"
        else:
            trend = "Neutral"
        strength = abs(self.df["momentum_ma_short"].iloc[-1] - self.df["momentum_ma_long"].iloc[-1]) / atr.iloc[-1]
        return {"trend": trend, "strength": strength}

    def _calculate_adx(self, window: int = 14) -> float:
        df = self.df.copy()
        required_columns = ['high', 'low', 'close']
        for col in required_columns:
            if col not in df.columns:
                self.logger.error(f"{NEON_RED}Missing '{col}' column for ADX calculation{RESET}")
                return 0.0
        df["TR"] = pd.concat([df["high"] - df["low"], abs(df["high"] - df["close"].shift()), abs(df["low"] - df["close"].shift())], axis=1).max(axis=1)
        df["+DM"] = np.where((df["high"] - df["high"].shift()) > (df["low"].shift() - df["low"]), np.maximum(df["high"] - df["high"].shift(), 0), 0)
        df["-DM"] = np.where((df["low"].shift() - df["low"]) > (df["high"] - df["high"].shift()), np.maximum(df["low"].shift() - df["low"], 0), 0)
        df["TR_sum"] = df["TR"].rolling(window).sum()
        df["+DM_sum"] = df["+DM"].rolling(window).sum()
        df["-DM_sum"] = df["-DM"].rolling(window).sum()
        df["+DI"] = 100 * (df["+DM_sum"] / df["TR_sum"])
        df["-DI"] = 100 * (df["-DM_sum"] / df["TR_sum"])
        df["DX"] = 100 * abs(df["+DI"] - df["-DI"]) / (df["+DI"] + df["-DI"])
        return df["DX"].rolling(window).mean().iloc[-1]

    def _calculate_obv(self) -> pd.Series:
        if 'close' not in self.df.columns or 'volume' not in self.df.columns:
            self.logger.error(f"{NEON_RED}Missing 'close' or 'volume' column for OBV calculation{RESET}")
            return pd.Series(dtype=float)
        obv = np.where(self.df["close"] > self.df["close"].shift(1), self.df["volume"], np.where(self.df["close"] < self.df["close"].shift(1), -self.df["volume"], 0))
        return pd.Series(np.cumsum(obv), index=self.df.index)

    def _calculate_adi(self) -> pd.Series:
        required_columns = ['high', 'low', 'close', 'volume']
        for col in required_columns:
            if col not in self.df.columns:
                self.logger.error(f"{NEON_RED}Missing '{col}' column for ADI calculation{RESET}")
                return pd.Series(dtype=float)
        money_flow_multiplier = ((self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])) / (self.df["high"] - self.df["low"])
        money_flow_volume = money_flow_multiplier * self.df["volume"]
        return money_flow_volume.cumsum()

    def _calculate_psar(self, acceleration=0.02, max_acceleration=0.2) -> pd.Series:
        psar = pd.Series(index=self.df.index, dtype="float64")
        if self.df.empty: return psar # Return empty if no data
        psar.iloc[0] = self.df["low"].iloc[0]
        trend = 1
        ep = self.df["high"].iloc[0]
        af = acceleration
        for i in range(1, len(self.df)):
            if trend == 1:
                psar.iloc[i] = psar.iloc[i-1] + af * (ep - psar.iloc[i-1])
                if self.df["high"].iloc[i] > ep:
                    ep = self.df["high"].iloc[i]
                    af = min(af + acceleration, max_acceleration)
                if self.df["low"].iloc[i] < psar.iloc[i]:
                    trend = -1
                    psar.iloc[i] = ep
                    ep = self.df["low"].iloc[i]
                    af = acceleration
            elif trend == -1:
                psar.iloc[i] = psar.iloc[i-1] + af * (ep - psar.iloc[i-1])
                if self.df["low"].iloc[i] < ep:
                    ep = self.df["low"].iloc[i]
                    af = min(af + acceleration, max_acceleration)
                if self.df["high"].iloc[i] > psar.iloc[i]:
                    trend = 1
                    psar.iloc[i] = ep
                    ep = self.df["high"].iloc[i]
                    af = acceleration
        return psar

    def _calculate_fve(self) -> pd.Series: # Example FVE calculation - improved example
        if 'close' not in self.df.columns or 'volume' not in self.df.columns:
            self.logger.error(f"{NEON_RED}Missing 'close' or 'volume' column for FVE calculation{RESET}")
            return pd.Series(dtype=float)

        try:
            # Example FVE calculation: (SMA of close) + (OBV normalized by its MA) - (ATR normalized by SMA of ATR)
            sma_close = self._calculate_sma(window=20)
            obv = self._calculate_obv()
            sma_obv = self._calculate_sma(window=20, series=obv) # Need to adjust _calculate_sma to accept series
            atr = self._calculate_atr()
            sma_atr = self._calculate_sma(window=20, series=atr)

            # Normalize OBV and ATR to SMA scales to make them comparable and combine them
            normalized_obv = (obv - sma_obv) / sma_obv.abs() # Normalize OBV by SMA_OBV - handles zero SMA_OBV
            normalized_atr = (atr - sma_atr) / sma_atr.abs() # Normalize ATR by SMA_ATR - handles zero SMA_ATR

            fve = sma_close + normalized_obv - normalized_atr # Example combination - you can adjust this formula
            return fve
        except Exception as e:
            self.logger.error(f"{NEON_RED}Error calculating FVE: {e}{RESET}")
            return pd.Series([np.nan] * len(self.df)) # Return NaN series in case of error

    def _calculate_volume_confirmation(self) -> bool: # New: Volume confirmation indicator
        if 'volume' not in self.df.columns:
            self.logger.error(f"{NEON_RED}Missing 'volume' column for Volume Confirmation{RESET}")
            return False
        current_volume = self.df['volume'].iloc[-1]
        average_volume = self.df['volume_ma'].iloc[-1] # Assuming volume_ma is calculated

        if average_volume == 0: # Avoid division by zero
            return False

        return current_volume > average_volume * self.config["volume_confirmation_multiplier"] # Volume spike confirmation


    def analyze(self, current_price: Decimal, timestamp: str):
        high = self.df["high"].max()
        low = self.df["low"].min()
        close = self.df["close"].iloc[-1]

        atr = self._calculate_atr() # Calculate ATR here
        self.indicator_values["atr"] = [atr.iloc[-1]] if atr is not None and not atr.empty else ['N/A'] # Store ATR value in indicator_values

        self.calculate_fibonacci_retracement(high, low, float(current_price))
        self.calculate_pivot_points(high, low, close)
        nearest_supports, nearest_resistances = self.find_nearest_levels(float(current_price))

        self.indicator_values = {}  # Store indicator values for signal generation - moved to __init__
        if self.config["indicators"]["obv"]:  # Respect config flags
            obv = self._calculate_obv()
            self.indicator_values["obv"] = obv.tail(3).tolist()
        if self.config["indicators"]["rsi"]:
            rsi = self._calculate_rsi()
            self.indicator_values["rsi"] = rsi.tail(3).tolist()
        if self.config["indicators"]["mfi"]:
            mfi = self._calculate_mfi()
            self.indicator_values["mfi"] = mfi.tail(3).tolist()
        if self.config["indicators"]["cci"]:
            cci = self._calculate_cci()
            self.indicator_values["cci"] = cci.tail(3).tolist()
        if self.config["indicators"]["wr"]:
            wr = self._calculate_williams_r()
            self.indicator_values["wr"] = wr.tail(3).tolist()
        if self.config["indicators"]["adx"]:
            adx = self._calculate_adx()
            self.indicator_values["adx"] = [adx] * 3  # Keep ADX in indicator_values for signal logic
        if self.config["indicators"]["adi"]:
            adi = self._calculate_adi()
            self.indicator_values["adi"] = adi.tail(3).tolist()
        if self.config["indicators"]["momentum"]:
            trend_data = self.determine_trend_momentum()
            self.indicator_values["mom"] = [trend_data] * 3  # Keep trend data for signal logic
        if self.config["indicators"]["sma_10"]:  # Example for SMA, add config flag in config.json if needed
            sma = self._calculate_sma(10)
            self.indicator_values["sma"] = [self.df["close"].iloc[-1]]  # Keep SMA for logging
        if self.config["indicators"]["psar"]:
            psar = self._calculate_psar()
            self.indicator_values["psar"] = psar.tail(3).tolist()
        if self.config["indicators"]["fve"]:
            fve = self._calculate_fve()
            self.indicator_values["fve"] = fve.tail(3).tolist()
        if self.config["indicators"]["macd"]:
            macd_df = self._calculate_macd()
            self.indicator_values["macd"] = macd_df.tail(3).values.tolist() if not macd_df.empty else []
        if self.config["indicators"]["stoch_rsi"]:
            self.indicator_values["stoch_rsi_vals"] = self.stoch_rsi_df.tail(3).values.tolist()  # Store Stoch RSI values
        if self.config["indicators"]["ema_alignment"]:  # New: EMA Alignment
            ema_alignment_score = self._calculate_ema_alignment()
            self.indicator_values["ema_alignment"] = [ema_alignment_score] * 3  # Keep EMA alignment score


        # Fetch Order Book Data (Basic Integration)
        order_book = fetch_order_book(self.symbol, API_KEY, API_SECRET, self.logger, limit=10)  # Fetch order book
        top_bid_price = order_book['bids'][0][0] if order_book and order_book.get('bids') else 'N/A'  # Get top bid
        top_ask_price = order_book['asks'][0][0] if order_book and order_book.get('asks') else 'N/A'  # Get top ask


        output = f"""
{NEON_BLUE}Exchange:{RESET} Bybit
{NEON_BLUE}Symbol:{RESET} {self.symbol}
{NEON_BLUE}Interval:{RESET} {self.interval}
{NEON_BLUE}Timestamp:{RESET} {timestamp}
{NEON_BLUE}Price:{RESET}   {self.df['close'].iloc[-3]:.2f} | {self.df['close'].iloc[-2]:.2f} | {self.df['close'].iloc[-1]:.2f}
{NEON_BLUE}Vol:{RESET}   {self.df['volume'].iloc[-3]:,} | {self.df['volume'].iloc[-2]:,} | {self.df['volume'].iloc[-1]:,}
{NEON_BLUE}Current Price:{RESET} {current_price:.2f}
{NEON_BLUE}ATR:{RESET} {self.indicator_values.get("atr", ['N/A'])[0]:.4f if self.indicator_values.get('atr') else 'N/A'}
{NEON_BLUE}Trend:{RESET} {self.indicator_values.get("mom", [{"trend": "N/A"}])[0].get("trend", "N/A")} (Strength: {self.indicator_values.get("mom", [{"strength": 0}]) [0].get("strength", 0):.2f})
"""
        for indicator_name, values in self.indicator_values.items():
            if indicator_name not in ['mom', 'atr', 'stoch_rsi_vals', 'ema_alignment']:  # Skip 'mom'/'atr'/'stoch_rsi_vals'/'ema_alignment' as they are already logged above or handled separately
                output += interpret_indicator(self.logger, indicator_name, values) + "\n"

        if self.config["indicators"]["ema_alignment"]:  # Log EMA Alignment separately
            ema_alignment_score = self.indicator_values.get("ema_alignment", [0.0])[0]  # Default to 0.0 if missing
            output += f"{NEON_PURPLE}EMA Alignment:{RESET} Score={ema_alignment_score:.2f} ({'Bullish' if ema_alignment_score > 0.5 else 'Bearish' if ema_alignment_score < -0.5 else 'Neutral'})\n"

        if self.config["indicators"]["stoch_rsi"]:  # Log Stoch RSI separately as it has k/d lines
            stoch_rsi_vals = self.indicator_values.get("stoch_rsi_vals", [])
            if stoch_rsi_vals and len(stoch_rsi_vals[-1]) >= 3:
                output += f"{NEON_GREEN}Stoch RSI:{RESET} K={stoch_rsi_vals[-1][1]:.2f}, D={stoch_rsi_vals[-1][2]:.2f}, Stoch_RSI={stoch_rsi_vals[-1][0]:.2f}\n"

        output += f"""
{NEON_BLUE}Order Book:{RESET} Top Bid: {top_bid_price}, Top Ask: {top_ask_price}
{NEON_BLUE}Support and Resistance Levels:{RESET}
"""
        for s in nearest_supports:
            output += f"S: {s[0]} ${s[1]:.3f}\n"
        for r in nearest_resistances:
            output += f"R: {r[0]} ${r[1]:.3f}\n"

        # --- Signal Generation Logic ---
        signal, confidence, conditions_met = self.generate_trading_signal(self.indicator_values, current_price)  # Get conditions met

        if signal:
            output += f"\n{NEON_PURPLE}--- Trading Signal ---{RESET}\n"
            output += f"{NEON_BLUE}Signal:{RESET} {signal.upper()} (Confidence: {confidence:.2f})\n"
            output += f"{NEON_BLUE}Conditions Met:{RESET} {', '.join(conditions_met) if conditions_met else 'None'}\n"  # Log conditions met
            # Placeholder for order execution logic - would go here in a trading bot

        self.logger.info(output)


    def generate_trading_signal(self, indicator_values: dict, current_price: Decimal) -> Tuple[Union[str, None], float, List[str]]: # Return conditions met
        signal_score = 0
        signal = None
        conditions_met = [] # List to store conditions met

        # --- Bullish Signal Logic ---
        bullish_conditions = 0
        confidence_boost = 0

        # 1. Stoch RSI Oversold and Crossover
        if self.config["indicators"]["stoch_rsi"] and indicator_values.get("stoch_rsi_vals"):
            stoch_rsi_k = indicator_values["stoch_rsi_vals"][-1][1] if indicator_values["stoch_rsi_vals"] and len(indicator_values["stoch_rsi_vals"][-1]) >= 2 else None
            stoch_rsi_d = indicator_values["stoch_rsi_vals"][-1][2] if indicator_values["stoch_rsi_vals"] and len(indicator_values["stoch_rsi_vals"][-1]) >= 3 else None

            if stoch_rsi_k and stoch_rsi_d and stoch_rsi_k < self.config["stoch_rsi_oversold_threshold"] and stoch_rsi_k > stoch_rsi_d: # Stoch RSI Oversold and K crossing above D
                bullish_conditions += self.user_defined_weights["stoch_rsi"]
                confidence_boost += self.config["stoch_rsi_confidence_boost"]
                conditions_met.append("Stoch RSI Oversold Crossover") # Add condition to list

        # 2. RSI Oversold
        if self.config["indicators"]["rsi"] and indicator_values.get("rsi"):
            rsi_val = indicator_values["rsi"][-1]
            if rsi_val < 30: # RSI Oversold
                bullish_conditions += self.user_defined_weights["rsi"]
                confidence_boost += self.config["rsi_confidence_boost"]
                conditions_met.append("RSI Oversold") # Add condition to list

        # 3. MFI Oversold
        if self.config["indicators"]["mfi"] and indicator_values.get("mfi"):
            mfi_val = indicator_values["mfi"][-1]
            if mfi_val < 20: # MFI Oversold
                bullish_conditions += self.user_defined_weights["mfi"]
                confidence_boost += self.config["mfi_confidence_boost"]
                conditions_met.append("MFI Oversold") # Add condition to list

        # 4. EMA Alignment (Bullish)
        if self.config["indicators"]["ema_alignment"] and indicator_values.get("ema_alignment"):
            ema_alignment_score = indicator_values["ema_alignment"][-1]
            if ema_alignment_score > 0.5: # Bullish EMA Alignment
                bullish_conditions += self.user_defined_weights["ema_alignment"] # Use configured weight
                conditions_met.append("Bullish EMA Alignment") # Add condition

        # 5. Volume Confirmation (Bullish)
        if self.config["indicators"]["volume_confirmation"]:
            if self._calculate_volume_confirmation(): # Volume spike confirmation
                bullish_conditions += self.user_defined_weights["volume_confirmation"] # Use configured weight
                conditions_met.append("Volume Confirmation") # Add condition


        if bullish_conditions >= self.config["signal_score_threshold"]: # Configurable signal threshold
            signal = "buy"
            signal_score = bullish_conditions + (confidence_boost / 100.0)


        # --- Bearish Signal Logic ---
        bearish_conditions = 0

        # 1. Stoch RSI Overbought and Crossover
        if self.config["indicators"]["stoch_rsi"] and indicator_values.get("stoch_rsi_vals"):
            stoch_rsi_k = indicator_values["stoch_rsi_vals"][-1][1] if indicator_values["stoch_rsi_vals"] and len(indicator_values["stoch_rsi_vals"][-1]) >= 2 else None
            stoch_rsi_d = indicator_values["stoch_rsi_vals"][-1][2] if indicator_values["stoch_rsi_vals"] and len(indicator_values["stoch_rsi_vals"][-1]) >= 3 else None

            if stoch_rsi_k and stoch_rsi_d and stoch_rsi_k > self.config["stoch_rsi_overbought_threshold"] and stoch_rsi_k < stoch_rsi_d: # Stoch RSI Overbought and K crossing below D
                bearish_conditions += self.user_defined_weights["stoch_rsi"]
                conditions_met.append("Stoch RSI Overbought Crossover") # Add condition

        # 2. RSI Overbought
        if self.config["indicators"]["rsi"] and indicator_values.get("rsi"):
            rsi_val = indicator_values["rsi"][-1]
            if rsi_val > 70: # RSI Overbought
                bearish_conditions += self.user_defined_weights["rsi"]
                conditions_met.append("RSI Overbought") # Add condition

        # 3. MFI Overbought
        if self.config["indicators"]["mfi"] and indicator_values.get("mfi"):
            mfi_val = indicator_values["mfi"][-1]
            if mfi_val > 80: # MFI Overbought
                bearish_conditions += self.user_defined_weights["mfi"]
                conditions_met.append("MFI Overbought") # Add condition

        # 4. EMA Alignment (Bearish)
        if self.config["indicators"]["ema_alignment"] and indicator_values.get("ema_alignment"):
            ema_alignment_score = indicator_values["ema_alignment"][-1]
            if ema_alignment_score < -0.5: # Bearish EMA Alignment
                bearish_conditions += self.user_defined_weights["ema_alignment"] # Use configured weight
                conditions_met.append("Bearish EMA Alignment") # Condition met


        # 5. Volume Confirmation (Bearish - optional, you might only want bullish volume confirmation)
        # if self.config["indicators"]["volume_confirmation"]: # Example - you might adapt volume confirmation for bearish signals differently
        #     if self._calculate_volume_confirmation(): # Volume spike confirmation
        #         bearish_conditions += self.user_defined_weights["volume_confirmation"]
        #         conditions_met.append("Volume Confirmation")


        if bearish_conditions >= self.config["signal_score_threshold"]: # Configurable signal threshold
            signal = "sell"
            signal_score = bearish_conditions


        if signal:
            return signal, signal_score, conditions_met
        return None, 0, []# Return empty list for conditions_met if no signal


def interpret_indicator(logger: logging.Logger, indicator_name: str, values: List[float]) -> Union[str, None]:
    if not values:
        return f"{indicator_name.upper()}: No data available."
    try:
        if indicator_name == "rsi":
            if values[-1] > 70:
                return f"{NEON_RED}RSI:{RESET} Overbought ({values[-1]:.2f})"
            elif values[-1] < 30:
                return f"{NEON_GREEN}RSI:{RESET} Oversold ({values[-1]:.2f})"
            else:
                return f"{NEON_YELLOW}RSI:{RESET} Neutral ({values[-1]:.2f})"
        elif indicator_name == "mfi":
            if values[-1] > 80:
                return f"{NEON_RED}MFI:{RESET} Overbought ({values[-1]:.2f})"
            elif values[-1] < 20:
                return f"{NEON_GREEN}MFI:{RESET} Oversold ({values[-1]:.2f})"
            else:
                return f"{NEON_YELLOW}MFI:{RESET} Neutral ({values[-1]:.2f})"
        elif indicator_name == "cci":
            if values[-1] > 100:
                return f"{NEON_RED}CCI:{RESET} Overbought ({values[-1]:.2f})"
            elif values[-1] < -100:
                return f"{NEON_GREEN}CCI:{RESET} Oversold ({values[-1]:.2f})"
            else:
                return f"{NEON_YELLOW}CCI:{RESET} Neutral ({values[-1]:.2f})"
        elif indicator_name == "wr":
            if values[-1] < -80:
                return f"{NEON_GREEN}Williams %R:{RESET} Oversold ({values[-1]:.2f})"
            elif values[-1] > -20:
                return f"{NEON_RED}Williams %R:{RESET} Overbought ({values[-1]:.2f})"
            else:
                return f"{NEON_YELLOW}Williams %R:{RESET} Neutral ({values[-1]:.2f})"
        elif indicator_name == "adx":
            if values[0] > 25:
                return f"{NEON_GREEN}ADX:{RESET} Trending ({values[0]:.2f})"
            else:
                return f"{NEON_YELLOW}ADX:{RESET} Ranging ({values[0]:.2f})"
        elif indicator_name == "obv":
            return f"{NEON_BLUE}OBV:{RESET} {'Bullish' if values[-1] > values[-2] else 'Bearish' if values[-1] < values[-2] else 'Neutral'}"
        elif indicator_name == "adi":
            return f"{NEON_BLUE}ADI:{RESET} {'Accumulation' if values[-1] > values[-2] else 'Distribution' if values[-1] < values[-2] else 'Neutral'}"
        elif indicator_name == "mom":
            trend = values[0]["trend"]
            strength = values[0]["strength"]
            return f"{NEON_PURPLE}Momentum:{RESET} {trend} (Strength: {strength:.2f})"
        elif indicator_name == "sma":
            return f"{NEON_YELLOW}SMA (10):{RESET} {values[0]:.2f}"
        elif indicator_name == "psar":
            return f"{NEON_BLUE}PSAR:{RESET} {values[-1]:.4f} (Last Value)"
        elif indicator_name == "fve":
            return f"{NEON_BLUE}FVE:{RESET} {values[-1]:.0f} (Last Value)"
        elif indicator_name == "macd":
            macd_values = values[-1]
            if len(macd_values) == 3:
                macd_line, signal_line, histogram = macd_values[0], macd_values[1], macd_values[2]
                return f"{NEON_GREEN}MACD:{RESET} MACD={macd_line:.2f}, Signal={signal_line:.2f}, Histogram={histogram:.2f}"
            else:
                return f"{NEON_RED}MACD:{RESET} Calculation issue."
        elif indicator_name == "stoch_rsi_vals": # Stoch RSI interpretation is handled directly in analyze function for K/D lines
            return None # Interpretation done directly in analyze function
        elif indicator_name == "ema_alignment": # EMA Alignment interpretation is handled directly in analyze function
            return None
        else:
            return f"{NEON_YELLOW}{indicator_name.upper()}:{RESET} No interpretation available."
    except (TypeError, IndexError) as e:
        logger.error(f"Error interpreting {indicator_name}: {e}")
        return f"{NEON_RED}{indicator_name.upper()}:{RESET} Interpretation error."


def main():
    symbol_input = input(f"{NEON_BLUE}Enter trading symbol (e.g., BTCUSDT): {RESET}").upper().strip()
    symbol = symbol_input if symbol_input else "BTCUSDT"
    interval_input = input(f"{NEON_BLUE}Enter timeframe (e.g., {', '.join(VALID_INTERVALS)} or press Enter for default {CONFIG['interval']}): {RESET}").strip()
    interval = interval_input if interval_input and interval_input in VALID_INTERVALS else CONFIG["interval"]

    symbol_logger = setup_symbol_logger(symbol)
    analysis_interval = CONFIG["analysis_interval"]
    retry_delay = CONFIG["retry_delay"]

    symbol_logger.info(f"{NEON_BLUE}Starting analysis for {symbol} with interval {interval}{RESET}")

    last_signal_time = 0 # For signal cooldown

    while True:
        try:
            current_price = fetch_current_price(symbol, API_KEY, API_SECRET, symbol_logger)
            if current_price is None:
                symbol_logger.error(f"{NEON_RED}Failed to fetch current price for {symbol}. Retrying in {retry_delay} seconds...{RESET}")
                time.sleep(retry_delay)
                continue

            df = fetch_klines(symbol, interval, API_KEY, API_SECRET, symbol_logger)
            if df.empty:
                symbol_logger.error(f"{NEON_RED}Failed to fetch Kline data for {symbol}. Retrying in {retry_delay} seconds...{RESET}")
                time.sleep(retry_delay)
                continue

            analyzer = TradingAnalyzer(df, CONFIG, symbol_logger, symbol, interval)
            timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
            analyzer.analyze(current_price, timestamp)

            current_time_seconds = time.time()
            signal, confidence, conditions_met = analyzer.generate_trading_signal(analyzer.indicator_values, current_price) # Get conditions met

            if signal and (current_time_seconds - last_signal_time >= CONFIG["signal_cooldown_s"]): # Check for signal and cooldown
                symbol_logger.info(f"{NEON_PURPLE}--- TRADING SIGNAL TRIGGERED ---{RESET}")
                symbol_logger.info(f"{NEON_BLUE}Signal:{RESET} {signal.upper()} (Confidence: {confidence:.2f})")
                symbol_logger.info(f"{NEON_BLUE}Conditions Met:{RESET} {', '.join(conditions_met) if conditions_met else 'None'}") # Log conditions met
                # --- Placeholder for order placement logic ---
                symbol_logger.info(f"{NEON_YELLOW}--- Placeholder: Order placement logic would be here for {signal.upper()} signal ---{RESET}")
                last_signal_time = current_time_seconds # Update last signal time


            time.sleep(analysis_interval)

        except requests.exceptions.RequestException as e:
            symbol_logger.error(f"{NEON_RED}Network error: {e}. Retrying in {retry_delay} seconds...{RESET}")
            time.sleep(retry_delay)
        except KeyboardInterrupt:
            symbol_logger.info(f"{NEON_YELLOW}Analysis stopped by user.{RESET}")
            break
        except Exception as e:
            symbol_logger.exception(f"{NEON_RED}Unexpected error: {e}. Retrying in {retry_delay} seconds...{RESET}")
            time.sleep(retry_delay)

if __name__ == "__main__":
    main()
