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
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, getcontext
from functools import wraps
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from colorama import Fore, Style, init as colorama_init
from dotenv import load_dotenv

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
getcontext().prec = 18
# Suppress pandas FutureWarning
warnings.filterwarnings("ignore", category=FutureWarning)
# ----------------------------------------------------------------------------
# 2. ENVIRONMENT & LOGGER SETUP
# ----------------------------------------------------------------------------
load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY") or ""
API_SECRET = os.getenv("BYBIT_API_SECRET") or ""
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
def setup_logger(name: str) -> logging.Logger:
    """Creates a self-contained, colorized logger."""
    fmt = "%(asctime)s │ %(levelname)-8s │ %(message)s"
    datefmt = "%H:%M:%S"
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(handler)
    return logger
LOGGER = setup_logger("whalebot_main")
# ----------------------------------------------------------------------------
# 3. UTILITY DECORATORS & CONFIGURATION
# ----------------------------------------------------------------------------
def retry_api_call(max_attempts: int = 3, delay: int = 5):
    """Decorator to retry API calls on specified error codes with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.RequestException as e:
                    status_code = getattr(e.response, 'status_code', None)
                    if status_code in RETRY_ERROR_CODES:
                        LOGGER.warning(f"{NEON_YELLOW}API request failed (Attempt {attempt}/{max_attempts}, Status: {status_code}). Retrying in {delay}s...{RESET}")
                        time.sleep(delay * (2**(attempt - 1)))
                    else:
                        LOGGER.error(f"{NEON_RED}Fatal API error: {e}{RESET}")
                        raise
            LOGGER.error(f"{NEON_RED}API call failed after {max_attempts} attempts. Aborting.{RESET}")
            return None
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
def _get_default_config() -> dict[str, Any]:
    """Returns the default configuration dictionary with all 22 indicators."""
    return {
        "interval": "15", "analysis_interval": 30, "retry_delay": 5,
        "momentum_period": 10, "volume_ma_period": 20, "atr_period": 14,
        "signal_score_threshold": 1.0, "stop_loss_multiple": 1.5, "take_profit_multiple": 1.0,
        "order_book_debounce_s": 10, "order_book_depth_to_check": 10,
        "atr_change_threshold": 0.005, "volume_confirmation_multiplier": 1.5,
        "signal_cooldown_s": 60, "ema_short_period": 12, "ema_long_period": 26,
        "indicators": {
            "ema_alignment": True, "momentum": True, "volume_confirmation": True,
            "divergence": True, "stoch_rsi": True, "rsi": True, "macd": True,
            "vwap": True, "obv": True, "adi": True, "cci": True, "wr": True,
            "adx": True, "psar": True, "fve": True, "sma_10": True, "mfi": True,
            "stochastic_oscillator": True, "cmf": True, "ao": True, "vi": True, "bb": True
        },
        "weight_sets": {
            "low_volatility": {
                "ema_alignment": 0.3, "momentum": 0.2, "volume_confirmation": 0.2,
                "divergence": 0.1, "stoch_rsi": 0.5, "rsi": 0.3, "macd": 0.3,
                "vwap": 0.2, "obv": 0.1, "adi": 0.1, "cci": 0.1, "wr": 0.1,
                "adx": 0.1, "psar": 0.1, "fve": 0.2, "sma_10": 0.0, "mfi": 0.3,
                "stochastic_oscillator": 0.4, "cmf": 0.2, "ao": 0.3, "vi": 0.2, "bb": 0.4
            },
            "high_volatility": {
                "ema_alignment": 0.1, "momentum": 0.4, "volume_confirmation": 0.1,
                "divergence": 0.2, "stoch_rsi": 0.4, "rsi": 0.4, "macd": 0.4,
                "vwap": 0.1, "obv": 0.1, "adi": 0.1, "cci": 0.1, "wr": 0.1,
                "adx": 0.1, "psar": 0.1, "fve": 0.3, "sma_10": 0.0, "mfi": 0.4,
                "stochastic_oscillator": 0.3, "cmf": 0.3, "ao": 0.5, "vi": 0.4, "bb": 0.1
            }
        },
        "stoch_rsi_oversold_threshold": 20, "stoch_rsi_overbought_threshold": 80,
        "order_book_support_confidence_boost": 3, "order_book_resistance_confidence_boost": 3,
        "indicator_periods": {
            "rsi": 14, "mfi": 14, "cci": 20, "williams_r": 14, "adx": 14,
            "stoch_rsi_period": 14, "stoch_rsi_k_period": 3, "stoch_rsi_d_period": 3,
            "momentum": 10, "volume_ma": 20, "atr": 14, "sma_10": 10,
            "fve_price_ema": 10, "fve_obv_sma": 20, "fve_atr_sma": 20,
            "stoch_osc_k": 14, "stoch_osc_d": 3, "vwap": 14,
            "cmf": 20, "ao_short": 5, "ao_long": 34, "vi": 14, "bb": 20,
        },
        "order_book_analysis": {"enabled": True, "wall_threshold_multiplier": 2.0, "depth_to_check": 10},
    }
def load_config(fp: Path) -> BotConfig:
    """Loads config from file, creating a default if missing or corrupt."""
    defaults = _get_default_config()
    if not fp.exists():
        LOGGER.warning(f"{NEON_YELLOW}Config not found. Creating default at: {fp}{RESET}")
        try:
            fp.write_text(json.dumps(defaults, indent=4))
        except OSError as e:
            LOGGER.error(f"{NEON_RED}Failed to write default config: {e}{RESET}")
            return BotConfig(defaults)
        return BotConfig(defaults)
    try:
        user_cfg = json.loads(fp.read_text())
        merged = defaults.copy()
        for key, value in user_cfg.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = defaults[key].copy()
                merged[key].update(value)
            else:
                merged[key] = value
    except (OSError, json.JSONDecodeError) as e:
        LOGGER.error(f"{NEON_RED}Error with config file: {e}. Rebuilding default.{RESET}")
        backup_fp = fp.with_name(f"{fp.stem}.bak_{int(time.time())}{fp.suffix}")
        try:
            fp.rename(backup_fp)
            fp.write_text(json.dumps(defaults, indent=4))
        except OSError as backup_err:
            LOGGER.error(f"{NEON_RED}Could not back up corrupt config: {backup_err}{RESET}")
        merged = defaults
    if merged["interval"] not in VALID_INTERVALS:
        LOGGER.warning(f"{NEON_YELLOW}Invalid interval '{merged['interval']}'. Falling back to default.{RESET}")
        merged["interval"] = "15"
    return BotConfig(merged)
CFG = load_config(CONFIG_FILE)
# ----------------------------------------------------------------------------
# 4. BYBIT API CLIENT
# ----------------------------------------------------------------------------
class BybitClient:
    """A client to interact with the Bybit API."""
    def __init__(self, base_url: str, api_key: str, api_secret: str, log: logging.Logger):
        self.base_url = base_url
        self.api_key = api_key
        self.api_secret = api_secret
        self.log = log
        self.kline_cache: dict[str, Any] = {}
    def _generate_signature(self, params: dict) -> str:
        """Generates the HMAC SHA256 signature for Bybit API requests."""
        param_str = "&".join([f"{key}={value}" for key, value in sorted(params.items())])
        return hmac.new(self.api_secret.encode(), param_str.encode(), hashlib.sha256).hexdigest()
    @retry_api_call()
    def _bybit_request(self, method: str, endpoint: str, params: dict[str, Any] = None) -> dict | None:
        """Sends a signed request to the Bybit API with retry logic."""
        params = params or {}
        params['timestamp'] = str(int(time.time() * 1000))
        signature = self._generate_signature(params)
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": params['timestamp'],
            "Content-Type": "application/json"
        }
        url = f"{self.base_url}{endpoint}"
        response = requests.request(
            method, url, headers=headers,
            params=params if method == "GET" else None,
            json=params if method == "POST" else None,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    @retry_api_call()
    def fetch_current_price(self, symbol: str) -> Decimal | None:
        """Fetches the latest price for a given symbol."""
        endpoint = "/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
        response_data = self._bybit_request("GET", endpoint, params)
        if response_data and response_data.get("retCode") == 0 and response_data.get("result"):
            tickers = response_data["result"].get("list")
            if tickers:
                for ticker in tickers:
                    if ticker.get("symbol") == symbol:
                        last_price = ticker.get("lastPrice")
                        return Decimal(str(last_price)) if last_price else None
        self.log.error(f"{NEON_RED}Could not fetch current price for {symbol}. Response: {response_data}{RESET}")
        return None
    @retry_api_call()
    def fetch_klines(self, symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
        """Fetches historical K-line data with caching."""
        kline_key = f"{symbol}_{interval}_{limit}"
        if kline_key in self.kline_cache and (time.time() - self.kline_cache[kline_key]['timestamp'] < CFG['analysis_interval']):
            return self.kline_cache[kline_key]['data']
        self.log.info(f"{NEON_BLUE}Fetching fresh Kline data for {symbol} ({interval})...{RESET}")
        endpoint = "/v5/market/kline"
        params = {"symbol": symbol, "interval": interval, "limit": limit, "category": "linear"}
        response_data = self._bybit_request("GET", endpoint, params)
        if response_data and response_data.get("retCode") == 0 and response_data.get("result") and response_data["result"].get("list"):
            data = response_data["result"]["list"]
            columns = ["start_time", "open", "high", "low", "close", "volume", "turnover"]
            df = pd.DataFrame(data, columns=columns)

            # Convert timestamp to datetime with explicit numeric conversion
            df["start_time"] = pd.to_datetime(pd.to_numeric(df["start_time"], errors='coerce'), unit="ms")
            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                df[col] = df[col].apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal('NaN'))

            df.dropna(subset=df.columns[1:], inplace=True)
            df = df.sort_values(by="start_time", ascending=True).reset_index(drop=True)
            self.kline_cache[kline_key] = {'data': df, 'timestamp': time.time()}
            return df

        self.log.error(f"{NEON_RED}Failed to fetch Kline data for {symbol}, interval {interval}. Response: {response_data}{RESET}")
        return pd.DataFrame()
    @retry_api_call()
    def fetch_order_book(self, symbol: str, limit: int = 50) -> dict | None:
        """Fetches the order book for a given symbol."""
        endpoint = "/v5/market/orderbook"
        params = {"symbol": symbol, "limit": limit, "category": "linear"}
        response_data = self._bybit_request("GET", endpoint, params)
        if response_data and response_data.get("retCode") == 0 and response_data.get("result"):
            return response_data["result"]
        self.log.warning(f"{NEON_YELLOW}Could not fetch order book for {symbol}. Response: {response_data}{RESET}")
        return None
# ----------------------------------------------------------------------------
# 5. TECHNICAL INDICATORS ENGINE (ALL METHODS ARE DECIMAL-AWARE)
# ----------------------------------------------------------------------------
class Indicators:
    """A collection of static methods for calculating technical indicators."""
    @staticmethod
    def _to_decimal(series: pd.Series) -> pd.Series:
        """Helper to convert series to Decimal type safely."""
        return series.apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal('NaN'))

    @staticmethod
    def sma(series: pd.Series, window: int) -> pd.Series:
        """Decimal-safe Simple Moving Average."""
        return series.rolling(window=window, min_periods=1).mean().apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal('NaN'))

    @staticmethod
    def ema(series: pd.Series, span: int) -> pd.Series:
        """Decimal-safe Exponential Moving Average."""
        return series.ewm(span=span, adjust=False).mean().apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal('NaN'))

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
        """Decimal-safe Average True Range."""
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return Indicators.ema(tr, span=window)

    @staticmethod
    def rsi(close: pd.Series, window: int) -> pd.Series:
        """Decimal-safe Relative Strength Index."""
        delta = close.diff()
        gain = delta.where(delta > Decimal('0'), Decimal('0')).fillna(Decimal('0'))
        loss = -delta.where(delta < Decimal('0'), Decimal('0')).fillna(Decimal('0'))
        avg_gain = Indicators.ema(gain, span=window)
        avg_loss = Indicators.ema(loss, span=window)
        rs = avg_gain / avg_loss.replace(Decimal('0'), Decimal('NaN'))
        return (Decimal('100') - (Decimal('100') / (Decimal('1') + rs))).fillna(Decimal('50'))

    @staticmethod
    def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
        """Decimal-safe Moving Average Convergence Divergence."""
        ema_fast = Indicators.ema(close, span=fast)
        ema_slow = Indicators.ema(close, span=slow)
        macd_line = ema_fast - ema_slow
        signal_line = Indicators.ema(macd_line, span=signal)
        histogram = macd_line - signal_line
        return pd.DataFrame({"macd": macd_line, "signal": signal_line, "histogram": histogram})

    @staticmethod
    def adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.DataFrame:
        """Decimal-safe Average Directional Index."""
        plus_dm = high.diff()
        minus_dm = low.diff().mul(Decimal('-1'))
        plus_dm_s = Indicators.ema(plus_dm.where((plus_dm > Decimal('0')) & (plus_dm > minus_dm), Decimal('0')), span=window)
        minus_dm_s = Indicators.ema(minus_dm.where((minus_dm > Decimal('0')) & (minus_dm > plus_dm), Decimal('0')), span=window)
        tr_s = Indicators.ema(Indicators.atr(high, low, close, window), span=window)
        plus_di = Decimal('100') * (plus_dm_s / tr_s.replace(Decimal('0'), Decimal('NaN'))).fillna(Decimal('0'))
        minus_di = Decimal('100') * (minus_dm_s / tr_s.replace(Decimal('0'), Decimal('NaN'))).fillna(Decimal('0'))
        dx_denom = (plus_di + minus_di).replace(Decimal('0'), Decimal('NaN'))
        dx = Decimal('100') * (abs(plus_di - minus_di) / dx_denom).fillna(Decimal('0'))
        adx_series = Indicators.ema(dx, span=window)
        return pd.DataFrame({"+DI": plus_di, "-DI": minus_di, "ADX": adx_series})

    @staticmethod
    def stochastic_oscillator(close: pd.Series, high: pd.Series, low: pd.Series, k_period: int = 14, d_period: int = 3) -> pd.DataFrame:
        """Decimal-safe Stochastic Oscillator."""
        highest_high = high.rolling(window=k_period).max()
        lowest_low = low.rolling(window=k_period).min()
        denominator = (highest_high - lowest_low).replace(Decimal('0'), Decimal('NaN'))
        k_line = ((close - lowest_low) / denominator * Decimal('100')).fillna(Decimal('0'))
        d_line = Indicators.sma(k_line, window=d_period)
        return pd.DataFrame({"k": k_line, "d": d_line})

    @staticmethod
    def stoch_rsi(close: pd.Series, rsi_period: int = 14, k_period: int = 3, d_period: int = 3) -> pd.DataFrame:
        """Decimal-safe Stochastic RSI."""
        rsi_vals = Indicators.rsi(close, window=rsi_period)
        min_rsi = rsi_vals.rolling(window=k_period).min()
        max_rsi = rsi_vals.rolling(window=k_period).max()
        denominator = (max_rsi - min_rsi).replace(Decimal('0'), Decimal('NaN'))
        stoch_rsi_val = ((rsi_vals - min_rsi) / denominator * Decimal('100')).fillna(Decimal('0'))
        k_line = Indicators.sma(stoch_rsi_val, window=k_period)
        d_line = Indicators.sma(k_line, window=d_period)
        return pd.DataFrame({"rsi": rsi_vals, "stoch_rsi_k": k_line, "stoch_rsi_d": d_line})

    @staticmethod
    def psar(high: pd.Series, low: pd.Series, close: pd.Series, acceleration: Decimal = Decimal('0.02'), max_acceleration: Decimal = Decimal('0.2')) -> pd.Series:
        """Decimal-safe Parabolic SAR."""
        psar = pd.Series([Decimal('NaN')] * len(close), index=close.index, dtype=object)
        if len(close) < 2: return psar
        psar.iloc[0] = close.iloc[0]
        trend = 1 if close.iloc[1] > close.iloc[0] else -1
        ep = high.iloc[0] if trend == 1 else low.iloc[0]
        af = acceleration
        for i in range(1, len(close)):
            prev_psar = psar.iloc[i - 1]
            if pd.isna(prev_psar):
                psar.iloc[i] = close.iloc[i]; continue
            curr_h, curr_l = high.iloc[i], low.iloc[i]
            if trend == 1:
                psar.iloc[i] = prev_psar + af * (ep - prev_psar)
                psar.iloc[i] = min(psar.iloc[i], curr_l, low.iloc[i-1] if i > 1 else curr_l)
                if curr_h > ep: ep, af = curr_h, min(af + acceleration, max_acceleration)
                if curr_l < psar.iloc[i]: trend, psar.iloc[i], ep, af = -1, ep, curr_l, acceleration
            else:
                psar.iloc[i] = prev_psar + af * (ep - prev_psar)
                psar.iloc[i] = max(psar.iloc[i], curr_h, high.iloc[i-1] if i > 1 else curr_h)
                if curr_l < ep: ep, af = curr_l, min(af + acceleration, max_acceleration)
                if curr_h > psar.iloc[i]: trend, psar.iloc[i], ep, af = 1, ep, curr_h, acceleration
        return psar.ffill()

    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        """Decimal-safe On-Balance Volume."""
        obv = pd.Series([Decimal('0')] * len(close), index=close.index, dtype=object)
        obv.iloc[0] = volume.iloc[0]
        for i in range(1, len(close)):
            if close.iloc[i] > close.iloc[i-1]: obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
            elif close.iloc[i] < close.iloc[i-1]: obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
            else: obv.iloc[i] = obv.iloc[i-1]
        return obv

    @staticmethod
    def adi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
        """Decimal-safe Accumulation/Distribution Index."""
        mfm_denom = (high - low).replace(Decimal('0'), Decimal('NaN'))
        mfm = (((close - low) - (high - close)) / mfm_denom).fillna(Decimal('0'))
        mfv = mfm * volume
        return mfv.cumsum()

    @staticmethod
    def cci(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 20, constant: Decimal = Decimal('0.015')) -> pd.Series:
        """Decimal-safe Commodity Channel Index."""
        typical_price = (high + low + close) / Decimal('3')
        sma_tp = Indicators.sma(typical_price, window=window)

        # Calculate mean deviation using pure Python to avoid numpy issues
        def mean_dev(x):
            if len(x) == 0 or pd.isna(x).all():
                return Decimal('NaN')
            # Convert to list of Decimals for safe arithmetic
            x_dec = [Decimal(str(val)) for val in x if not pd.isna(val)]
            if not x_dec:
                return Decimal('NaN')
            mean = sum(x_dec) / Decimal(str(len(x_dec)))
            return sum(abs(val - mean) for val in x_dec) / Decimal(str(len(x_dec)))

        mean_dev = typical_price.rolling(window=window).apply(mean_dev, raw=True).apply(
            lambda x: Decimal(str(x)) if pd.notna(x) else Decimal('NaN'))

        return ((typical_price - sma_tp) / (constant * mean_dev.replace(Decimal('0'), Decimal('NaN')))).fillna(Decimal('0'))

    @staticmethod
    def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
        """Decimal-safe Williams %R."""
        highest_high = high.rolling(window=window).max()
        lowest_low = low.rolling(window=window).min()
        denom = (highest_high - lowest_low).replace(Decimal('0'), Decimal('NaN'))
        return (((highest_high - close) / denom) * Decimal('-100')).fillna(Decimal('0'))

    @staticmethod
    def mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, window: int = 14) -> pd.Series:
        """Decimal-safe Money Flow Index."""
        typical_price = (high + low + close) / Decimal('3')
        raw_mf = typical_price * volume
        mf_dir = typical_price.diff()
        pos_mf = raw_mf.where(mf_dir > Decimal('0'), Decimal('0'))
        neg_mf = raw_mf.where(mf_dir < Decimal('0'), Decimal('0'))
        pos_sum = pos_mf.rolling(window=window, min_periods=1).sum().apply(lambda x: Decimal(str(x)))
        neg_sum = neg_mf.rolling(window=window, min_periods=1).sum().apply(lambda x: Decimal(str(x)))
        mf_ratio = pos_sum / neg_sum.replace(Decimal('0'), Decimal('NaN'))
        return (Decimal('100') - (Decimal('100') / (Decimal('1') + mf_ratio))).fillna(Decimal('0'))

    @staticmethod
    def momentum(close: pd.Series, period: int = 10) -> pd.Series:
        """Decimal-safe Momentum."""
        return ((close.diff(period) / close.shift(period)) * Decimal('100')).fillna(Decimal('0'))

    @staticmethod
    def vwap(close: pd.Series, volume: pd.Series, window: int) -> pd.Series:
        """Decimal-safe Volume Weighted Average Price."""
        if window <= 0: return close
        price_vol = close * volume
        cum_pv = price_vol.rolling(window=window, min_periods=1).sum().apply(lambda x: Decimal(str(x)))
        cum_vol = volume.rolling(window=window, min_periods=1).sum().apply(lambda x: Decimal(str(x)))
        return (cum_pv / cum_vol.replace(Decimal('0'), Decimal('NaN'))).fillna(close)

    @staticmethod
    def cmf(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, window: int = 20) -> pd.Series:
        """Decimal-safe Chaikin Money Flow (CMF)."""
        mfm_denom = (high - low).replace(Decimal('0'), Decimal('NaN'))
        mfm = (((close - low) - (high - close)) / mfm_denom).fillna(Decimal('0'))
        mfv = mfm * volume
        return mfv.rolling(window=window).sum() / volume.rolling(window=window).sum().replace(Decimal('0'), Decimal('NaN'))

    @staticmethod
    def ao(close: pd.Series, short_period: int = 5, long_period: int = 34) -> pd.Series:
        """Decimal-safe Awesome Oscillator (AO)."""
        median_price = (close + close.shift(1)) / Decimal('2')
        sma_short = Indicators.sma(median_price, window=short_period)
        sma_long = Indicators.sma(median_price, window=long_period)
        return sma_short - sma_long

    @staticmethod
    def vi(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.DataFrame:
        """Decimal-safe Vortex Indicator (VI)."""
        tr = Indicators.atr(high, low, close, 1).rolling(window=window).sum()
        plus_vi = (high.diff().abs() + low.diff().abs()).rolling(window=window).sum() / tr
        minus_vi = (high.diff(-1).abs() + low.diff(-1).abs()).shift(-1).rolling(window=window).sum() / tr
        return pd.DataFrame({"+VI": plus_vi, "-VI": minus_vi})

    @staticmethod
    def bb(close: pd.Series, window: int = 20, std_dev_mult: Decimal = Decimal('2')) -> pd.DataFrame:
        """Decimal-safe Bollinger Bands (BB)."""
        sma = Indicators.sma(close, window=window)
        rolling_std = close.rolling(window=window).std().apply(lambda x: Decimal(str(x)))
        upper = sma + (rolling_std * std_dev_mult)
        lower = sma - (rolling_std * std_dev_mult)
        return pd.DataFrame({"upper": upper, "middle": sma, "lower": lower})

    @staticmethod
    def fve(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, window: int = 10) -> pd.Series:
        """A composite indicator based on price and volume relationship."""
        if len(close) < window: return pd.Series([Decimal('NaN')] * len(close))
        price_ema = Indicators.ema(close, window)
        vol_sma = Indicators.sma(volume, window)
        fve = (price_ema * vol_sma).rolling(window=window).sum()
        return fve.apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal('NaN'))
# ----------------------------------------------------------------------------
# 6. DATA STRUCTURES & CORE TRADING ANALYZER
# ----------------------------------------------------------------------------
@dataclass(slots=True)
class TradeSignal:
    """Structured object for a trading signal."""
    signal: str | None
    confidence: float
    conditions: list[str] = field(default_factory=list)
    levels: dict[str, Decimal] = field(default_factory=dict)
class TradingAnalyzer:
    """Orchestrates technical analysis and signal generation."""
    def __init__(self, df: pd.DataFrame, cfg: BotConfig, log: logging.Logger, symbol: str, interval: str):
        self.df = df.copy()
        self.cfg = cfg
        self.log = log
        self.symbol = symbol
        self.interval = interval
        self.atr_value: Decimal = Decimal('0')
        self.indicator_values: dict[str, Any] = {}
        self.levels: dict[str, Any] = {"Support": {}, "Resistance": {}}
        self.fib_levels: dict[str, Decimal] = {}
        self._pre_calculate_indicators()
        self.weights = self._select_weight_set()
    def _pre_calculate_indicators(self):
        """Pre-calculates essential indicators like ATR needed for other logic."""
        if self.df.empty: return
        atr_series = Indicators.atr(self.df.high, self.df.low, self.df.close, self.cfg["atr_period"])
        if not atr_series.empty and pd.notna(atr_series.iloc[-1]):
            self.atr_value = atr_series.iloc[-1]
        self.indicator_values["atr"] = self.atr_value
    def _select_weight_set(self) -> dict[str, float]:
        """Selects indicator weights based on market volatility (ATR)."""
        vol_mode = "high_volatility" if self.atr_value > Decimal(str(self.cfg["atr_change_threshold"])) else "low_volatility"
        self.log.info(f"Market Volatility: {NEON_YELLOW}{vol_mode.upper()}{RESET} (ATR: {self.atr_value:.5f})")
        return self.cfg["weight_sets"][vol_mode]
    def _calculate_ema_alignment(self) -> Decimal:
        """Calculates a score based on EMA alignment and price position."""
        short_p, long_p = self.cfg["ema_short_period"], self.cfg["ema_long_period"]
        if len(self.df) < long_p: return Decimal('0')
        ema_short = Indicators.ema(self.df.close, span=short_p)
        ema_long = Indicators.ema(self.df.close, span=long_p)
        price = self.df.close
        if len(ema_short) < 2 or len(ema_long) < 2 or len(price) < 2: return Decimal('0')
        if (price.iloc[-1] > ema_short.iloc[-1] > ema_long.iloc[-1]) and (price.iloc[-2] > ema_short.iloc[-2] > ema_long.iloc[-2]): return Decimal('1.0')
        if (price.iloc[-1] < ema_short.iloc[-1] < ema_long.iloc[-1]) and (price.iloc[-2] < ema_short.iloc[-2] < ema_long.iloc[-2]): return Decimal('-1.0')
        if ema_short.iloc[-1] > ema_long.iloc[-1] and ema_short.iloc[-2] <= ema_long.iloc[-2]: return Decimal('0.5')
        if ema_short.iloc[-1] < ema_long.iloc[-1] and ema_short.iloc[-2] >= ema_long.iloc[-2]: return Decimal('-0.5')
        return Decimal('0')
    def _calculate_volume_confirmation(self) -> bool:
        """Checks if the latest volume is significantly above its moving average."""
        vol_ma_series = Indicators.sma(self.df.volume, self.cfg["volume_ma_period"])
        if vol_ma_series.empty or pd.isna(vol_ma_series.iloc[-1]) or vol_ma_series.iloc[-1] == Decimal('0'): return False
        vol_ma_value = vol_ma_series.iloc[-1]
        multiplier = Decimal(str(self.cfg["volume_confirmation_multiplier"]))
        return self.df.volume.iloc[-1] > vol_ma_value * multiplier
    def _detect_macd_divergence(self) -> str | None:
        """Detects bullish or bearish MACD divergence (simplified logic)."""
        macd_df = Indicators.macd(self.df.close)
        if macd_df.empty or len(self.df) < 30: return None
        prices = self.df["close"]
        macd_hist = macd_df["histogram"]
        lookback = 5
        if len(prices) < lookback + 1: return None
        if prices.iloc[-1] < prices.iloc[-lookback] and macd_hist.iloc[-1] > macd_hist.iloc[-lookback]: return "bullish"
        if prices.iloc[-1] > prices.iloc[-lookback] and macd_hist.iloc[-1] < macd_hist.iloc[-lookback]: return "bearish"
        return None
    def _analyze_order_book_walls(self, order_book: dict[str, Any]) -> tuple[bool, bool, dict[str, Decimal], dict[str, Decimal]]:
        """Detect bullish/bearish walls from bids/asks."""
        enabled = self.cfg.get("order_book_analysis", {}).get("enabled", False)
        if not enabled or not order_book: return False, False, {}, {}
        depth = int(self.cfg.get("order_book_depth_to_check", 10))
        bids = [(Decimal(p), Decimal(q)) for p, q in order_book.get("bids", [])[:depth]]
        asks = [(Decimal(p), Decimal(q)) for p, q in order_book.get("asks", [])[:depth]]
        all_qty = [q for _, q in bids] + [q for _, q in asks]
        if not all_qty: return False, False, {}, {}
        avg_qty = sum(all_qty) / Decimal(str(len(all_qty)))
        wall_threshold = avg_qty * Decimal(str(self.cfg.get("order_book_wall_threshold_multiplier", 2.0)))
        current_price = self.df.close.iloc[-1]
        bullish, bearish = {}, {}
        for price_dec, qty_dec in bids:
            if qty_dec >= wall_threshold and price_dec < current_price:
                bullish[f"Bid@{price_dec.quantize(Decimal('0.0001'))}"] = qty_dec
                break
        for price_dec, qty_dec in asks:
            if qty_dec >= wall_threshold and price_dec > current_price:
                bearish[f"Ask@{price_dec.quantize(Decimal('0.0001'))}"] = qty_dec
                break
        return bool(bullish), bool(bearish), bullish, bearish
    def calculate_fibonacci_retracement(self, high: Decimal, low: Decimal, current_price: Decimal) -> None:
        """Calculates Fibonacci retracement levels based on a given high and low."""
        diff = high - low
        if diff <= 0:
            self.fib_levels, self.levels["Support"], self.levels["Resistance"] = {}, {}, {}
            return
        fib_ratios = {"23.6%": Decimal('0.236'), "38.2%": Decimal('0.382'), "50.0%": Decimal('0.500'),
                      "61.8%": Decimal('0.618'), "78.6%": Decimal('0.786'), "88.6%": Decimal('0.886')}
        self.fib_levels = {f"Fib {label}": (high - (diff * ratio)).quantize(Decimal('0.00001')) for label, ratio in fib_ratios.items()}
        for label, value in self.fib_levels.items():
            if value < current_price: self.levels["Support"][label] = value
            elif value > current_price: self.levels["Resistance"][label] = value
    def calculate_pivot_points(self, high: Decimal, low: Decimal, close: Decimal):
        """Calculates standard Pivot Points."""
        pivot = (high + low + close) / Decimal('3')
        r1 = (Decimal('2') * pivot) - low; s1 = (Decimal('2') * pivot) - high
        r2 = pivot + (high - low); s2 = pivot - (high - low)
        r3 = high + Decimal('2') * (pivot - low); s3 = low - Decimal('2') * (high - pivot)
        precision = Decimal('0.00001')
        pivots = {"Pivot": pivot, "R1": r1, "S1": s1, "R2": r2, "S2": s2, "R3": r3, "S3": s3}
        self.levels.update({label: val.quantize(precision) for label, val in pivots.items()})
    def find_nearest_levels(self, current_price: Decimal, num_levels: int = 5) -> tuple[list[tuple[str, Decimal]], list[tuple[str, Decimal]]]:
        """Finds the nearest support and resistance levels from calculated Fibonacci and Pivot Points."""
        supports, resistances = [], []
        for label, value in self.levels.items():
            if isinstance(value, dict):
                for sub_label, sub_value in value.items():
                    if sub_value < current_price: supports.append((f"{label} ({sub_label})", sub_value))
                    else: resistances.append((f"{label} ({sub_label})", sub_value))
            elif isinstance(value, Decimal):
                if value < current_price: supports.append((label, value))
                else: resistances.append((label, value))
        return sorted(supports, key=lambda x: current_price - x[1])[:num_levels], sorted(resistances, key=lambda x: x[1] - current_price)[:num_levels]
    def _interpret_and_color_indicator(self, name: str, value: Any) -> str:
        """Interprets indicator values and formats them with neon colors."""
        line = f"  {name.upper():<20}: {value!s}"
        color = NEON_BLUE
        if name == "ema_alignment":
            if value > Decimal('0'): color = NEON_GREEN; line = f"  EMA Alignment     : {NEON_GREEN}Bullish{RESET}"
            elif value < Decimal('0'): color = NEON_RED; line = f"  EMA Alignment     : {NEON_RED}Bearish{RESET}"
            else: line = f"  EMA Alignment     : {NEON_YELLOW}Neutral{RESET}"
        elif name == "volume_confirmation":
            line = f"  Volume Conf.      : {NEON_GREEN}Confirmed{RESET}" if value else f"  Volume Conf.      : {NEON_YELLOW}Unconfirmed{RESET}"
        elif name == "rsi":
            if value > Decimal('70'): color = NEON_RED
            elif value < Decimal('30'): color = NEON_GREEN
        elif name == "macd":
            hist = value.get('histogram', Decimal('0'))
            if hist > Decimal('0'): color = NEON_GREEN
            elif hist < Decimal('0'): color = NEON_RED
            line = f"  MACD              : {color}Histogram: {hist:.5f}{RESET}"
        elif name == "stoch_rsi":
            k, d = value.get('stoch_rsi_k', Decimal('0')), value.get('stoch_rsi_d', Decimal('0'))
            color_k = NEON_GREEN if k < 20 else NEON_RED if k > 80 else NEON_YELLOW
            color_d = NEON_GREEN if d < 20 else NEON_RED if d > 80 else NEON_YELLOW
            line = f"  Stoch RSI         : K={color_k}{k:.2f}{RESET} D={color_d}{d:.2f}{RESET}"
        elif name == "psar":
            if self.df.close.iloc[-1] > value: color = NEON_GREEN
            elif self.df.close.iloc[-1] < value: color = NEON_RED
            line = f"  PSAR              : {color}{value:.5f}{RESET}"
        elif name == "cmf" or name == "ao":
            if value > Decimal('0'): color = NEON_GREEN
            elif value < Decimal('0'): color = NEON_RED
        elif name == "vi":
            plus_vi, minus_vi = value.get('+VI'), value.get('-VI')
            line = f"  Vortex Indicator  : +VI={NEON_GREEN}{plus_vi:.2f}{RESET} -VI={NEON_RED}{minus_vi:.2f}{RESET}"
        elif name == "bb":
            upper, lower = value.get('upper'), value.get('lower')
            current_price = self.df.close.iloc[-1]
            if current_price > upper: color = NEON_RED; status="Overbought"
            elif current_price < lower: color = NEON_GREEN; status="Oversold"
            else: color=NEON_BLUE; status="In Band"
            line = f"  Bollinger Bands   : Price {color}{status}{RESET}"

        return line
    def analyze(self, price: Decimal, ts: str, order_book: dict[str, Any] | None):
        """Performs a full analysis and logs a detailed summary."""
        cfg_ind = self.cfg["indicators"]
        cfg_prd = self.cfg["indicator_periods"]
        # Calculate Levels
        high_dec, low_dec, close_dec = self.df.high.max(), self.df.low.min(), self.df.close.iloc[-1]
        self.levels = {"Support": {}, "Resistance": {}}
        self.calculate_fibonacci_retracement(high_dec, low_dec, price)
        self.calculate_pivot_points(high_dec, low_dec, close_dec)
        # Map available data and periods to indicator parameters
        indicator_data = {
            'high': self.df.high, 'low': self.df.low, 'close': self.df.close, 'volume': self.df.volume,
            'window': 0, 'span': 0, 'period': 0, 'fast': 0, 'slow': 0, 'signal': 0,
            'k_period': 0, 'd_period': 0, 'rsi_period': 0, 'short_period': 0, 'long_period': 0,
            'std_dev_mult': Decimal('2')
        }

        # Populate period values from config
        for key, val in cfg_prd.items():
            if key in indicator_data:
                indicator_data[key] = val
        indicator_data.update({
            'window': cfg_prd.get('atr', 14),
            'span': cfg_prd.get('atr', 14),
            'period': cfg_prd.get('momentum', 10),
            'fast': 12, 'slow': 26, 'signal': 9, # MACD defaults
            'k_period': cfg_prd.get('stoch_osc_k', 14),
            'd_period': cfg_prd.get('stoch_osc_d', 3),
            'rsi_period': cfg_prd.get('stoch_rsi_period', 14),
            'short_period': cfg_prd.get('ao_short', 5),
            'long_period': cfg_prd.get('ao_long', 34),
        })
        # Calculate and store indicator values dynamically
        for name in sorted(cfg_ind.keys()):
            if not cfg_ind.get(name): continue
            try:
                indicator_method = getattr(Indicators, name, None)
                if indicator_method:
                    # Get the function signature
                    sig = inspect.signature(indicator_method)
                    params = {}
                    # Build the parameter dictionary from available data
                    for param_name in sig.parameters:
                        if param_name in indicator_data:
                            params[param_name] = indicator_data[param_name]
                        elif param_name == 'close' and name != 'vwap' and 'close' in indicator_data:
                            params['close'] = indicator_data['close']
                        elif param_name == 'high' and 'high' in indicator_data:
                            params['high'] = indicator_data['high']
                        elif param_name == 'low' and 'low' in indicator_data:
                            params['low'] = indicator_data['low']
                        elif param_name == 'volume' and 'volume' in indicator_data:
                            params['volume'] = indicator_data['volume']
                        else:
                            self.log.debug(f"Skipping parameter '{param_name}' for indicator '{name}' due to missing data.")
                    series = indicator_method(**params)
                    self.indicator_values[name] = series.iloc[-1] if isinstance(series, pd.Series) else (series.iloc[-1].to_dict() if isinstance(series, pd.DataFrame) else None)
            except Exception as e:
                self.log.error(f"{NEON_RED}Error calculating indicator '{name}': {e}{RESET}")
                self.indicator_values[name] = None
        # Manual checks for specific indicators
        self.indicator_values["ema_alignment"] = self._calculate_ema_alignment()
        self.indicator_values["volume_confirmation"] = self._calculate_volume_confirmation()
        self.indicator_values["divergence"] = self._detect_macd_divergence()
        has_bull, has_bear, bullish_details, bearish_details = self._analyze_order_book_walls(order_book or {})
        self.indicator_values["order_book_walls"] = {"bullish": has_bull, "bearish": has_bear, "bullish_details": bullish_details, "bearish_details": bearish_details}
        # --- Log Summary ---
        log_lines = [f"\n{'─'*20} ANALYSIS FOR {self.symbol} ({self.interval}) {'─'*20}",
                     f" Timestamp: {ts} │ Current Price: {NEON_BLUE}{price:.5f}{RESET}",
                     f" Price History: {self.df['close'].iloc[-3]:.5f} | {self.df['close'].iloc[-2]:.5f} | {self.df['close'].iloc[-1]:.5f}",
                     f" Volume History: {self.df['volume'].iloc[-3]:,.0f} | {self.df['volume'].iloc[-2]:,.0f} | {self.df['volume'].iloc[-1]:,.0f}",
                     f" ATR({self.cfg['atr_period']}): {self.atr_value:.5f}"]
        for name in sorted(self.indicator_values.keys()):
            value = self.indicator_values.get(name)
            if value is None or (isinstance(value, Decimal) and value.is_nan()): continue
            colored_line = self._interpret_and_color_indicator(name, value)
            if colored_line: log_lines.append(colored_line)
        log_lines.append(f"\n{NEON_BLUE}Order Book Walls:{RESET}")
        if has_bull: log_lines.append(f"{NEON_GREEN}  Bullish Walls Found: {', '.join([f'{k}:{v:,.0f}' for k, v in bullish_details.items()])}{RESET}")
        if has_bear: log_lines.append(f"{NEON_RED}  Bearish Walls Found: {', '.join([f'{k}:{v:,.0f}' for k, v in bearish_details.items()])}{RESET}")
        if not has_bull and not has_bear: log_lines.append("  No significant walls detected.")
        log_lines.append(f"\n{NEON_BLUE}Support/Resistance Levels:{RESET}")
        nearest_supports, nearest_resistances = self.find_nearest_levels(price)
        for label, val in nearest_supports: log_lines.append(f"S: {label} ${val:.5f}")
        for label, val in nearest_resistances: log_lines.append(f"R: {label} ${val:.5f}")
        if not nearest_supports and not nearest_resistances: log_lines.append("  No significant levels calculated.")
        self.log.info("\n".join(log_lines))
        self.log.info("─" * (42 + len(self.symbol) + len(self.interval)))
    def generate_trading_signal(self, current_price: Decimal) -> TradeSignal:
        """Combines indicator scores and other analysis to generate a final trade signal.
        """
        raw_score = Decimal('0.0')
        conditions_met = []

        # Calculate scores from main indicators
        for name, weight in self.weights.items():
            if not self.cfg["indicators"].get(name): continue
            value = self.indicator_values.get(name)
            if value is None: continue
            weight_dec = Decimal(str(weight))

            if name == "ema_alignment":
                if value == Decimal('1.0'): raw_score += weight_dec; conditions_met.append("EMA Alignment (Bullish)")
                elif value == Decimal('-1.0'): raw_score -= weight_dec; conditions_met.append("EMA Alignment (Bearish)")
            elif name == "volume_confirmation":
                if value: raw_score += weight_dec; conditions_met.append("Volume Confirmation")
            elif name == "divergence":
                if value == "bullish": raw_score += weight_dec; conditions_met.append("Bullish Divergence")
                elif value == "bearish": raw_score -= weight_dec; conditions_met.append("Bearish Divergence")
            elif name == "stoch_rsi":
                k, d = value.get('stoch_rsi_k', Decimal('0')), value.get('stoch_rsi_d', Decimal('0'))
                if k < Decimal(str(self.cfg['stoch_rsi_oversold_threshold'])) and k > d:
                    raw_score += weight_dec; conditions_met.append("StochRSI Oversold")
                elif k > Decimal(str(self.cfg['stoch_rsi_overbought_threshold'])) and k < d:
                    raw_score -= weight_dec; conditions_met.append("StochRSI Overbought")
            elif name == "rsi":
                if value < Decimal('30'): raw_score += weight_dec; conditions_met.append("RSI Oversold")
                elif value > Decimal('70'): raw_score -= weight_dec; conditions_met.append("RSI Overbought")
            elif name == "macd":
                hist = value.get('histogram')
                if hist and hist > Decimal('0'): raw_score += weight_dec; conditions_met.append("MACD Bullish")
                elif hist and hist < Decimal('0'): raw_score -= weight_dec; conditions_met.append("MACD Bearish")
            elif name == "psar":
                if value and current_price > value: raw_score += weight_dec; conditions_met.append("PSAR Bullish")
                elif value and current_price < value: raw_score -= weight_dec; conditions_met.append("PSAR Bearish")
            elif name == "stochastic_oscillator":
                k, d = value.get('k'), value.get('d')
                if k < Decimal('20') and k > d: raw_score += weight_dec; conditions_met.append("Stoch Osc Oversold")
                elif k > Decimal('80') and k < d: raw_score -= weight_dec; conditions_met.append("Stoch Osc Overbought")
            elif name == "cmf":
                if value > Decimal('0'): raw_score += weight_dec; conditions_met.append("CMF Positive")
                elif value < Decimal('0'): raw_score -= weight_dec; conditions_met.append("CMF Negative")
            elif name == "ao":
                if value > Decimal('0'): raw_score += weight_dec; conditions_met.append("AO Bullish")
                elif value < Decimal('0'): raw_score -= weight_dec; conditions_met.append("AO Bearish")
            elif name == "vi":
                plus_vi, minus_vi = value.get('+VI'), value.get('-VI')
                if plus_vi > minus_vi: raw_score += weight_dec; conditions_met.append("VI Bullish Crossover")
                elif plus_vi < minus_vi: raw_score -= weight_dec; conditions_met.append("VI Bearish Crossover")
            elif name == "bb":
                upper, lower = value.get('upper'), value.get('lower')
                if current_price > upper: raw_score -= weight_dec; conditions_met.append("BB Overbought")
                elif current_price < lower: raw_score += weight_dec; conditions_met.append("BB Oversold")
            elif name in ["fve", "vwap", "obv", "adi", "cci", "wr", "adx"]:
                # Generic scoring for other indicators based on bullish/bearish signal
                # Implement specific logic here if needed. For now, they contribute to the analysis log.
                pass
        # Order book walls add a confidence boost
        ob_walls = self.indicator_values.get("order_book_walls", {})
        if ob_walls.get("bullish"):
            raw_score += Decimal(str(self.cfg.get("order_book_support_confidence_boost", 0))); conditions_met.append("Order Book: Bullish Wall")
        if ob_walls.get("bearish"):
            raw_score -= Decimal(str(self.cfg.get("order_book_resistance_confidence_boost", 0))); conditions_met.append("Order Book: Bearish Wall")
        signal = None
        if raw_score >= Decimal(str(self.cfg["signal_score_threshold"])):
            signal = "buy"
        elif raw_score <= -Decimal(str(self.cfg["signal_score_threshold"])):
            signal = "sell"
        # Calculate Stop Loss and Take Profit
        sl, tp = Decimal('0'), Decimal('0')
        if signal and self.atr_value > Decimal('0'):
            atr_multiple_sl = Decimal(str(self.cfg['stop_loss_multiple']))
            atr_multiple_tp = Decimal(str(self.cfg['take_profit_multiple']))
            if signal == "buy":
                sl = current_price - (self.atr_value * atr_multiple_sl)
                tp = current_price + (self.atr_value * atr_multiple_tp)
            else: # sell
                sl = current_price + (self.atr_value * atr_multiple_sl)
                tp = current_price - (self.atr_value * atr_multiple_tp)
        # Normalize score to a confidence level
        max_score = sum(self.weights.values()) + self.cfg.get("order_book_support_confidence_boost", 0)
        confidence = abs(float(raw_score)) / max_score if max_score > 0 else 0
        return TradeSignal(signal, confidence, conditions_met, {"stop_loss": sl, "take_profit": tp})
# ----------------------------------------------------------------------------
# 7. MAIN APPLICATION LOOP
# ----------------------------------------------------------------------------
def main():
    """Main function to initialize and run the trading bot loop."""
    if not API_KEY or not API_SECRET:
        LOGGER.critical(f"{NEON_RED}API credentials (BYBIT_API_KEY, BYBIT_API_SECRET) are missing in .env file.{RESET}")
        return
    bybit_client = BybitClient(BASE_URL, API_KEY, API_SECRET, LOGGER)
    symbol = (input(f"{NEON_BLUE}Enter symbol (default BTCUSDT): {RESET}") or "BTCUSDT").upper()
    interval = (input(f"{NEON_BLUE}Enter interval ({', '.join(VALID_INTERVALS)}) (default {CFG['interval']}): {RESET}") or CFG["interval"])
    if interval not in VALID_INTERVALS:
        LOGGER.warning(f"{NEON_YELLOW}Invalid interval '{interval}'. Using default '{CFG['interval']}'.{RESET}")
        interval = CFG["interval"]
    symbol_logger = setup_logger(symbol)
    symbol_logger.info(f"🚀 WhaleBot Enhanced starting for {NEON_PURPLE}{symbol}{RESET} on interval {NEON_PURPLE}{interval}{RESET}")
    last_signal_time = 0.0
    last_ob_fetch_time = 0.0
    order_book: dict[str, Any] | None = None
    try:
        while True:
            price = bybit_client.fetch_current_price(symbol)
            if price is None:
                symbol_logger.error(f"{NEON_RED}Failed to fetch current price. Retrying in {CFG['retry_delay']}s...{RESET}")
                time.sleep(CFG["retry_delay"])
                continue
            min_data_needed = 30
            for name, enabled in CFG["indicators"].items():
                if enabled and name in CFG["indicator_periods"]:
                    min_data_needed = max(min_data_needed, CFG["indicator_periods"][name])
                if enabled and name == 'stoch_rsi':
                    min_data_needed = max(min_data_needed, CFG["indicator_periods"]["stoch_rsi_period"])
            min_data_needed += 10
            df = bybit_client.fetch_klines(symbol, interval, min_data_needed)
            if df.empty or len(df) < min_data_needed:
                symbol_logger.warning(f"{NEON_YELLOW}Insufficient Kline data ({len(df)}/{min_data_needed} bars). Retrying...{RESET}")
                time.sleep(CFG["retry_delay"])
                continue
            current_time = time.time()
            if current_time - last_ob_fetch_time >= CFG["order_book_debounce_s"]:
                order_book = bybit_client.fetch_order_book(symbol, CFG["order_book_depth_to_check"])
                last_ob_fetch_time = current_time
            analyzer = TradingAnalyzer(df, CFG, symbol_logger, symbol, interval)
            timestamp_str = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
            analyzer.analyze(price, timestamp_str, order_book)
            trade_signal = analyzer.generate_trading_signal(price)
            if trade_signal.signal and (current_time - last_signal_time >= CFG["signal_cooldown_s"]):
                last_signal_time = current_time
                color = NEON_GREEN if trade_signal.signal == "buy" else NEON_RED
                symbol_logger.info(
                    f"\n{color}🔔 {"-"*10} TRADE SIGNAL: {trade_signal.signal.upper()} {'-'*10}{RESET}\n"
                    f"   Confidence Score: {trade_signal.confidence:.2f}\n"
                    f"   Conditions Met: {'; '.join(trade_signal.conditions)}\n"
                )
                if trade_signal.levels:
                    sl, tp = trade_signal.levels['stop_loss'], trade_signal.levels['take_profit']
                    symbol_logger.info(f"   Stop Loss: {sl:.5f} | Take Profit: {tp:.5f}")
                symbol_logger.info(f"{NEON_YELLOW}   --- Placeholder: Order placement logic would execute here ---{RESET}\n")
            time.sleep(CFG["analysis_interval"])
    except KeyboardInterrupt:
        symbol_logger.info(f"\n{NEON_YELLOW}User stopped analysis. Shutting down...{RESET}")
    except Exception as e:
        symbol_logger.exception(f"{NEON_RED}An unexpected critical error occurred: {e}{RESET}")
        time.sleep(CFG["retry_delay"] * 2)
if __name__ == "__main__":
    main()
