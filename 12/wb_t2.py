# whalebot_enhanced.py
# A robust, upgraded Bybit-driven trading bot with a modular design,
# enhanced error handling, and improved performance.
# Fully compatible with the original config.json and behavior.

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from colorama import Fore, Style
from colorama import init as colorama_init
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
getcontext().prec = 12

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
    # Prevent duplicate handlers if script is reloaded/re-run in interactive sessions
    if not logger.handlers:
        logger.addHandler(handler)
    return logger


LOGGER = setup_logger("whalebot_main")


# ----------------------------------------------------------------------------
# 3. CONFIGURATION HANDLING
# ----------------------------------------------------------------------------
@dataclass(slots=True)
class BotConfig:
    """A lightweight, type-safe wrapper around the JSON configuration."""

    raw: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)


def _get_default_config() -> dict[str, Any]:
    """Returns the default configuration dictionary."""
    return {
        "interval": "15",
        "analysis_interval": 30,
        "retry_delay": 5,
        "momentum_period": 10,
        "momentum_ma_short": 12,
        "momentum_ma_long": 26,
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
        "indicators": {
            "ema_alignment": True,
            "momentum": True,
            "volume_confirmation": True,
            "divergence": True,
            "stoch_rsi": True,
            "rsi": True,
            "macd": True,
            "vwap": True,  # Enabled by default
            "obv": True,
            "adi": True,
            "cci": True,
            "wr": True,  # Enabled by default
            "adx": True,
            "psar": True,
            "fve": True,
            "sma_10": True,
            "mfi": True,
            "stochastic_oscillator": True,
        },
        "weight_sets": {
            "low_volatility": {
                "ema_alignment": 0.3,
                "momentum": 0.2,
                "volume_confirmation": 0.2,
                "divergence": 0.1,
                "stoch_rsi": 0.5,
                "rsi": 0.3,
                "macd": 0.3,
                "vwap": 0.2,  # New weight
                "obv": 0.1,
                "adi": 0.1,
                "cci": 0.1,
                "wr": 0.1,  # New weights
                "adx": 0.1,
                "psar": 0.1,
                "fve": 0.2,
                "sma_10": 0.0,
                "mfi": 0.3,
                "stochastic_oscillator": 0.4,
            },
            "high_volatility": {
                "ema_alignment": 0.1,
                "momentum": 0.4,
                "volume_confirmation": 0.1,
                "divergence": 0.2,
                "stoch_rsi": 0.4,
                "rsi": 0.4,
                "macd": 0.4,
                "vwap": 0.1,  # New weight
                "obv": 0.1,
                "adi": 0.1,
                "cci": 0.1,
                "wr": 0.1,  # New weights
                "adx": 0.1,
                "psar": 0.1,
                "fve": 0.3,
                "sma_10": 0.0,
                "mfi": 0.4,
                "stochastic_oscillator": 0.3,
            },
        },
        "stoch_rsi_oversold_threshold": 20,
        "stoch_rsi_overbought_threshold": 80,
        "stoch_rsi_confidence_boost": 5,
        "stoch_rsi_mandatory": False,
        "rsi_confidence_boost": 2,
        "mfi_confidence_boost": 2,
        "order_book_support_confidence_boost": 3,
        "order_book_resistance_confidence_boost": 3,
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
            "sma_10": 10,
            "fve_price_ema": 10,
            "fve_obv_sma": 20,
            "fve_atr_sma": 20,
            "stoch_osc_k": 14,
            "stoch_osc_d": 3,
            "vwap": 14,  # New period
        },
        "order_book_analysis": {
            "enabled": True,
            "wall_threshold_multiplier": 2.0,
            "depth_to_check": 10,
        },
        "trailing_stop_loss": {
            "enabled": False,
            "initial_activation_percent": 0.5,
            "trailing_stop_multiple_atr": 1.5,
        },
        "take_profit_scaling": {
            "enabled": False,
            "targets": [
                {"level": 1.5, "percentage": 0.25},
                {"level": 2.0, "percentage": 0.50},
            ],
        },
    }


def load_config(fp: Path) -> BotConfig:
    """Loads config from file, creating a default if missing or corrupt."""
    defaults = _get_default_config()
    if not fp.exists():
        LOGGER.warning(
            f"{NEON_YELLOW}Config not found. Creating default at: {fp}{RESET}",
        )
        try:
            fp.write_text(json.dumps(defaults, indent=4))
        except OSError as e:
            LOGGER.error(f"{NEON_RED}Failed to write default config: {e}{RESET}")
            return BotConfig(defaults)  # Return in-memory default
        return BotConfig(defaults)

    try:
        user_cfg = json.loads(fp.read_text())
        # Deep merge nested dictionaries like 'indicators' and 'weight_sets'
        merged = defaults.copy()
        for key, value in user_cfg.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = defaults[key].copy()  # Start with default for deep update
                merged[key].update(value)
            else:
                merged[key] = value
    except json.JSONDecodeError as e:
        LOGGER.error(
            f"{NEON_RED}Corrupt config file: {e}. Backing up and creating new default.{RESET}",
        )
        backup_fp = fp.with_name(fp.stem + f".bak_{int(time.time())}{fp.suffix}")
        try:
            fp.rename(backup_fp)
            fp.write_text(json.dumps(defaults, indent=4))
        except OSError as backup_err:
            LOGGER.error(
                f"{NEON_RED}Could not back up corrupt config: {backup_err}{RESET}",
            )
        merged = defaults
    except OSError as e:
        LOGGER.error(
            f"{NEON_RED}Could not read config file: {e}. Using default config.{RESET}",
        )
        merged = defaults

    # Final validation
    if merged["interval"] not in VALID_INTERVALS:
        LOGGER.warning(
            f"{NEON_YELLOW}Invalid interval '{merged['interval']}' in config. Falling back to default '15'.{RESET}",
        )
        merged["interval"] = "15"

    return BotConfig(merged)


CFG = load_config(CONFIG_FILE)


# ----------------------------------------------------------------------------
# 4. BYBIT API INTERACTION
# ----------------------------------------------------------------------------
def _sign(secret: str, params: dict[str, Any]) -> str:
    """Generates the required HMAC-SHA256 signature for Bybit API."""
    qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(secret.encode(), qs.encode(), hashlib.sha256).hexdigest()


def _send_request(
    method: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
    retries: int = 3,
    logger: logging.Logger = LOGGER,
) -> dict[str, Any] | None:
    """Generic, robust HTTP request wrapper with exponential backoff and jitter."""
    if not API_KEY or not API_SECRET:
        logger.critical(
            f"{NEON_RED}API_KEY or API_SECRET is not set. Cannot send request.{RESET}",
        )
        return None

    params = params or {}
    params["timestamp"] = str(int(time.time() * 1000))
    headers = {
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-SIGN": _sign(API_SECRET, params),
        "X-BAPI-TIMESTAMP": params["timestamp"],
        "Content-Type": "application/json",
    }
    url = f"{BASE_URL}{endpoint}"

    for attempt in range(retries):
        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                params=params if method == "GET" else None,
                json=params if method != "GET" else None,
                timeout=10,
            )
            if resp.status_code in RETRY_ERROR_CODES:
                raise requests.HTTPError(
                    f"Retryable HTTP Error: {resp.status_code} {resp.reason}",
                )

            resp.raise_for_status()  # Raise for other non-2xx codes
            data = resp.json()

            if data.get("retCode") != 0:
                logger.error(
                    f"{NEON_RED}Bybit API Error (retCode={data.get('retCode')}): {data.get('retMsg')}{RESET}",
                )
                return None
            return data

        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as e:
            sleep_s = (2**attempt) + random.uniform(
                0, 1,
            )  # Exponential backoff with jitter
            logger.warning(
                f"{NEON_YELLOW}Request failed ({e}). Retrying in {sleep_s:.2f}s... ({attempt + 1}/{retries}){RESET}",
            )
            time.sleep(sleep_s)
        except OSError as e:  # Catch potential issues with response reading
            logger.error(f"{NEON_RED}IO error during request processing: {e}{RESET}")
            # Decide if this warrants a retry or immediate failure

    logger.error(f"{NEON_RED}Max retries exceeded for {method} {endpoint}.{RESET}")
    return None


def fetch_current_price(symbol: str, log: logging.Logger) -> Decimal | None:
    """Fetches the latest price for a symbol."""
    data = _send_request(
        "GET",
        "/v5/market/tickers",
        {"category": "linear", "symbol": symbol},
        logger=log,
    )
    if not data:
        return None
    try:
        # API might return multiple tickers, ensure we get the correct one
        for ticker_data in data.get("result", {}).get("list", []):
            if ticker_data.get("symbol") == symbol:
                price_str = ticker_data.get("lastPrice")
                if price_str:
                    return Decimal(price_str)
        log.error(
            f"{NEON_RED}Price not found for symbol {symbol} in ticker data.{RESET}",
        )
        return None
    except (KeyError, IndexError, TypeError, ValueError) as e:
        log.error(
            f"{NEON_RED}Could not parse price from API response: {e}. Data: {data}{RESET}",
        )
        return None


kline_cache: dict[str, tuple[datetime, pd.DataFrame]] = {}  # Global cache for klines


def fetch_klines(
    symbol: str,
    interval: str,
    limit: int,
    log: logging.Logger,
    cache: dict[str, tuple[datetime, pd.DataFrame]],
) -> pd.DataFrame:
    """Fetches K-line data with a 30-second in-memory cache."""
    now_utc = datetime.now(UTC)
    cache_key = f"{symbol}_{interval}"
    if cache_key in cache and (now_utc - cache[cache_key][0]).total_seconds() < 30:
        return cache[cache_key][1].copy()

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
        "category": "linear",
    }
    data = _send_request("GET", "/v5/market/kline", params, logger=log)
    if not data or not (kline_list := data.get("result", {}).get("list")):
        log.warning(
            f"{NEON_YELLOW}No kline data received for {symbol} ({interval}).{RESET}",
        )
        return pd.DataFrame()

    cols = ["ts", "open", "high", "low", "close", "volume", "turnover"]
    df = pd.DataFrame(kline_list, columns=cols)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    numeric_cols = ["open", "high", "low", "close", "volume", "turnover"]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
    df.dropna(inplace=True)
    df.sort_values("ts", inplace=True, ascending=True)
    df.reset_index(drop=True, inplace=True)

    cache[cache_key] = (now_utc, df)
    return df.copy()


def fetch_order_book(
    symbol: str, depth: int, log: logging.Logger,
) -> dict[str, Any] | None:
    """Fetches the order book for a symbol."""
    params = {"symbol": symbol, "limit": depth, "category": "linear"}
    data = _send_request("GET", "/v5/market/orderbook", params, logger=log)
    return data.get("result") if data else None


# ----------------------------------------------------------------------------
# 5. TECHNICAL INDICATORS ENGINE
# ----------------------------------------------------------------------------
class Indicators:
    """A collection of static methods for calculating technical indicators."""

    @staticmethod
    def sma(series: pd.Series, window: int) -> pd.Series:
        return series.rolling(window=window, min_periods=1).mean()

    @staticmethod
    def ema(series: pd.Series, span: int) -> pd.Series:
        return series.ewm(span=span, adjust=False).mean()

    @staticmethod
    def atr(
        high: pd.Series, low: pd.Series, close: pd.Series, window: int,
    ) -> pd.Series:
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return Indicators.ema(tr, span=window)

    @staticmethod
    def rsi(close: pd.Series, window: int) -> pd.Series:
        delta = close.diff()
        gain = delta.where(delta > 0, 0).fillna(0)
        loss = -delta.where(delta < 0, 0).fillna(0)
        avg_gain = Indicators.ema(gain, span=window)
        avg_loss = Indicators.ema(loss, span=window)
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return (100 - (100 / (1 + rs))).fillna(50)  # Default to 50 if rs is NaN

    @staticmethod
    def macd(
        close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9,
    ) -> pd.DataFrame:
        ema_fast = Indicators.ema(close, span=fast)
        ema_slow = Indicators.ema(close, span=slow)
        macd_line = ema_fast - ema_slow
        signal_line = Indicators.ema(macd_line, span=signal)
        histogram = macd_line - signal_line
        return pd.DataFrame(
            {"macd": macd_line, "signal": signal_line, "histogram": histogram},
        )

    @staticmethod
    def adx(
        high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14,
    ) -> pd.DataFrame:
        """Calculates ADX, +DI, and -DI."""
        plus_dm = high.diff()
        minus_dm = low.diff().mul(-1)
        # Apply Wilder's smoothing logic (essentially EMA)
        plus_dm_s = Indicators.ema(
            plus_dm.where((plus_dm > 0) & (plus_dm > minus_dm), 0), span=window,
        )
        minus_dm_s = Indicators.ema(
            minus_dm.where((minus_dm > 0) & (minus_dm > plus_dm), 0), span=window,
        )
        tr_s = Indicators.ema(Indicators.atr(high, low, close, window), span=window)

        # Avoid division by zero and inf/nan results
        plus_di = 100 * (plus_dm_s / tr_s).replace([np.inf, -np.inf], np.nan).fillna(0)
        minus_di = 100 * (minus_dm_s / tr_s).replace([np.inf, -np.inf], np.nan).fillna(
            0,
        )
        dx_denom = (plus_di + minus_di).replace(0, np.nan)
        dx = 100 * (abs(plus_di - minus_di) / dx_denom).fillna(0)
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
        """Calculates Stochastic Oscillator (%K and %D)."""
        if close.empty or high.empty or low.empty:
            return pd.DataFrame()
        highest_high = high.rolling(window=k_period).max()
        lowest_low = low.rolling(window=k_period).min()
        denominator = (highest_high - lowest_low).replace(0, np.nan)
        k_line = ((close - lowest_low) / denominator * 100).fillna(0)
        d_line = k_line.rolling(window=d_period, min_periods=1).mean()
        return pd.DataFrame({"k": k_line, "d": d_line})

    @staticmethod
    def stoch_rsi(
        close: pd.Series, rsi_period: int = 14, k_period: int = 3, d_period: int = 3,
    ) -> pd.DataFrame:
        """Calculates Stochastic RSI (%K, %D, and the RSI value itself)."""
        rsi_vals = Indicators.rsi(close, window=rsi_period)
        if rsi_vals.empty:
            return pd.DataFrame()
        min_rsi = rsi_vals.rolling(window=k_period).min()
        max_rsi = rsi_vals.rolling(window=k_period).max()
        denominator = (max_rsi - min_rsi).replace(0, np.nan)
        stoch_rsi_val = ((rsi_vals - min_rsi) / denominator * 100).fillna(0)
        k_line = stoch_rsi_val.rolling(
            window=k_period, min_periods=1,
        ).mean()  # %K for Stoch RSI
        d_line = k_line.rolling(
            window=d_period, min_periods=1,
        ).mean()  # %D for Stoch RSI
        return pd.DataFrame(
            {"rsi": rsi_vals, "stoch_rsi_k": k_line, "stoch_rsi_d": d_line},
        )

    @staticmethod
    def psar(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        acceleration: float = 0.02,
        max_acceleration: float = 0.2,
    ) -> pd.Series:
        """Calculates a PSAR-like indicator. Note: This is a simplified implementation."""
        psar = pd.Series(index=close.index, dtype="float64")
        if len(close) < 2:
            return psar

        # Initialize PSAR with the first closing price (common practice)
        psar.iloc[0] = close.iloc[0]
        # Determine initial trend based on first two closing prices
        trend = 1 if close.iloc[1] > close.iloc[0] else -1
        # Initial Extreme Point (EP)
        ep = high.iloc[0] if trend == 1 else low.iloc[0]
        af = acceleration

        for i in range(1, len(close)):
            prev_psar = psar.iloc[i - 1]
            curr_h, curr_l = high.iloc[i], low.iloc[i]

            if trend == 1:  # Uptrend
                psar.iloc[i] = prev_psar + af * (ep - prev_psar)
                # Ensure PSAR does not go below current or previous low (or current high)
                psar.iloc[i] = min(
                    psar.iloc[i], curr_l, low.iloc[i - 1] if i > 1 else curr_l,
                )
                if curr_h > ep:
                    ep = curr_h
                    af = min(af + acceleration, max_acceleration)
                # Check for trend reversal
                if curr_l < psar.iloc[i]:
                    trend = -1
                    psar.iloc[i] = ep  # Jump PSAR to previous EP
                    ep = curr_l
                    af = acceleration
            else:  # trend == -1 (Downtrend)
                psar.iloc[i] = prev_psar + af * (ep - prev_psar)
                # Ensure PSAR does not go above current or previous high (or current low)
                psar.iloc[i] = max(
                    psar.iloc[i], curr_h, high.iloc[i - 1] if i > 1 else curr_h,
                )
                if curr_l < ep:
                    ep = curr_l
                    af = min(af + acceleration, max_acceleration)
                # Check for trend reversal
                if curr_h > psar.iloc[i]:
                    trend = 1
                    psar.iloc[i] = ep
                    ep = curr_h
                    af = acceleration
        return psar.fillna(method="ffill")  # Fill any initial NaNs

    @staticmethod
    def fve(
        close: pd.Series,
        volume: pd.Series,
        atr: pd.Series,
        price_ema_p: int = 10,
        obv_norm_p: int = 20,
        atr_norm_p: int = 20,
    ) -> pd.Series:
        """Calculates a 'Fictional Value Estimate' - a composite indicator."""
        if close.empty or volume.empty or atr.empty:
            return pd.Series(dtype=float)
        min_points = max(
            obv_norm_p, atr_norm_p, price_ema_p, len(atr),
        )  # Ensure enough data for all components
        if len(close) < min_points:
            return pd.Series([np.nan] * len(close))

        try:
            price_comp = Indicators.ema(close, span=price_ema_p)
            obv_comp = Indicators.obv(close, volume)
            # atr is passed directly

            # Normalize using Decimal for precision and handle edge cases
            def safe_normalize(series: pd.Series) -> pd.Series:
                if series.empty or series.isna().all():
                    return pd.Series([Decimal("0")] * len(series), index=series.index)
                series_dec = pd.Series(
                    [
                        Decimal(str(v)) if pd.notna(v) else Decimal("NaN")
                        for v in series
                    ],
                    index=series.index,
                )
                s_mean = series_dec.mean()
                s_std = series_dec.std()
                if pd.isna(s_mean) or pd.isna(s_std) or s_std == Decimal("0"):
                    return pd.Series(
                        [Decimal("0")] * len(series_dec), index=series_dec.index,
                    )
                return ((series_dec - s_mean) / s_std).fillna(0)

            price_norm = safe_normalize(price_comp)
            obv_norm = safe_normalize(obv_comp)

            # Inverse ATR normalization
            atr_inv = pd.Series(
                [
                    Decimal("1.0") / Decimal(str(v))
                    if pd.notna(v) and v != 0
                    else Decimal("NaN")
                    for v in atr
                ],
                index=atr.index,
            )
            atr_inv_norm = safe_normalize(atr_inv)

            fve_dec = price_norm + obv_norm + atr_inv_norm
            return pd.Series([float(v) for v in fve_dec], index=close.index)
        except Exception as e:
            LOGGER.error(f"{NEON_RED}Error in FVE calculation: {e}{RESET}")
            return pd.Series([np.nan] * len(close))

    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        """Calculates On-Balance Volume (OBV)."""
        if close.empty or volume.empty:
            return pd.Series(dtype=float)
        obv = pd.Series(0.0, index=close.index)
        obv.iloc[0] = volume.iloc[0]
        for i in range(1, len(close)):
            if close.iloc[i] > close.iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] + volume.iloc[i]
            elif close.iloc[i] < close.iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] - volume.iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i - 1]
        return obv

    @staticmethod
    def adi(
        high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series,
    ) -> pd.Series:
        """Calculates Accumulation/Distribution Index (ADI)."""
        if high.empty or low.empty or close.empty or volume.empty:
            return pd.Series(dtype=float)
        mfm_denom = (high - low).replace(0, np.nan)
        mfm = (((close - low) - (high - close)) / mfm_denom).fillna(0)
        mfv = mfm * volume
        return mfv.cumsum()

    @staticmethod
    def cci(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        window: int = 20,
        constant: float = 0.015,
    ) -> pd.Series:
        """Calculates the Commodity Channel Index (CCI)."""
        if high.empty or low.empty or close.empty:
            return pd.Series(dtype=float)
        typical_price = (high + low + close) / 3
        sma_typical_price = Indicators.sma(typical_price, window=window)
        # Mean Deviation
        mean_deviation = typical_price.rolling(window=window).apply(
            lambda x: np.abs(x - x.mean()).mean(), raw=True,
        )
        cci_series = (typical_price - sma_typical_price) / (
            constant * mean_deviation
        ).replace(0, np.nan)
        return cci_series.replace([np.inf, -np.inf], np.nan).fillna(0)

    @staticmethod
    def williams_r(
        high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14,
    ) -> pd.Series:
        """Calculates the Williams %R indicator."""
        if high.empty or low.empty or close.empty:
            return pd.Series(dtype=float)
        highest_high = high.rolling(window=window).max()
        lowest_low = low.rolling(window=window).min()
        denominator = (highest_high - lowest_low).replace(0, np.nan)
        wr_series = ((highest_high - close) / denominator) * -100
        return wr_series.replace([np.inf, -np.inf], np.nan).fillna(0)

    @staticmethod
    def mfi(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series,
        window: int = 14,
    ) -> pd.Series:
        """Calculates the Money Flow Index (MFI)."""
        if high.empty or low.empty or close.empty or volume.empty:
            return pd.Series(dtype=float)
        typical_price = (high + low + close) / 3
        raw_money_flow = typical_price * volume

        money_flow_direction = typical_price.diff()
        positive_flow = raw_money_flow.where(money_flow_direction > 0, 0)
        negative_flow = raw_money_flow.where(money_flow_direction < 0, 0)

        positive_mf = positive_flow.rolling(window=window, min_periods=1).sum()
        negative_mf = negative_flow.rolling(window=window, min_periods=1).sum()

        money_ratio = positive_mf / negative_mf.replace(0, np.nan)
        mfi_series = 100 - (100 / (1 + money_ratio))
        return mfi_series.replace([np.inf, -np.inf], np.nan).fillna(0)

    @staticmethod
    def momentum(close: pd.Series, period: int = 10) -> pd.Series:
        """Calculates the Momentum indicator as price percentage change."""
        if close.empty or len(close) < period:
            return pd.Series(dtype=float)
        return (close.diff(period) / close.shift(period) * 100).fillna(0)

    @staticmethod
    def vwap(close: pd.Series, volume: pd.Series, window: int) -> pd.Series:
        """Calculates Volume Weighted Average Price over a rolling window."""
        if close.empty or volume.empty:
            return pd.Series(dtype=float)
        if window <= 0:
            return close  # If window is invalid, return close price

        # Calculate cumulative price*volume and cumulative volume over the window
        price_volume = close * volume
        cumulative_pv = price_volume.rolling(window=window, min_periods=1).sum()
        cumulative_v = volume.rolling(window=window, min_periods=1).sum()

        # Avoid division by zero
        vwap_series = (cumulative_pv / cumulative_v.replace(0, np.nan)).fillna(
            close,
        )  # Fill initial NaNs with close
        return vwap_series


# ----------------------------------------------------------------------------
# 6. DATA STRUCTURES
# ----------------------------------------------------------------------------
@dataclass(slots=True)
class TradeSignal:
    """Structured object for a trading signal."""

    signal: str | None
    confidence: float
    conditions: list[str] = field(default_factory=list)
    levels: dict[str, Decimal] = field(default_factory=dict)


# ----------------------------------------------------------------------------
# 7. CORE TRADING ANALYZER
# ----------------------------------------------------------------------------
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
        self.atr_value: float = 0.0
        self.indicator_values: dict[str, Any] = {}
        self.levels: dict[str, Any] = {"Support": {}, "Resistance": {}}
        self._pre_calculate_indicators()
        self.weights = self._select_weight_set()

    def _pre_calculate_indicators(self):
        """Pre-calculates essential indicators like ATR needed for other logic."""
        if self.df.empty:
            return
        atr_series = Indicators.atr(
            self.df.high, self.df.low, self.df.close, self.cfg["atr_period"],
        )
        if not atr_series.empty and pd.notna(atr_series.iloc[-1]):
            self.atr_value = float(atr_series.iloc[-1])
        self.indicator_values["atr"] = self.atr_value

    def _select_weight_set(self) -> dict[str, float]:
        """Selects indicator weights based on market volatility (ATR)."""
        vol_mode = (
            "high_volatility"
            if self.atr_value > self.cfg["atr_change_threshold"]
            else "low_volatility"
        )
        self.log.info(
            f"Market Volatility: {NEON_YELLOW}{vol_mode.upper()}{RESET} (ATR: {self.atr_value:.5f})",
        )
        return self.cfg["weight_sets"][vol_mode]

    def _calculate_ema_alignment(self) -> float:
        """Calculates a score based on EMA alignment and price position."""
        short_p, long_p = self.cfg["ema_short_period"], self.cfg["ema_long_period"]
        if len(self.df) < long_p:
            return 0.0
        ema_short = Indicators.ema(self.df.close, span=short_p)
        ema_long = Indicators.ema(self.df.close, span=long_p)
        price = self.df.close

        # Check for strong alignment (last 3 bars) or recent crossover
        if (price.iloc[-1] > ema_short.iloc[-1] > ema_long.iloc[-1]) and (
            price.iloc[-2] > ema_short.iloc[-2] > ema_long.iloc[-2]
        ):
            return 1.0  # Strong Bullish
        if (price.iloc[-1] < ema_short.iloc[-1] < ema_long.iloc[-1]) and (
            price.iloc[-2] < ema_short.iloc[-2] < ema_long.iloc[-2]
        ):
            return -1.0  # Strong Bearish
        if (
            ema_short.iloc[-1] > ema_long.iloc[-1]
            and ema_short.iloc[-2] <= ema_long.iloc[-2]
        ):
            return 0.5  # Bullish Crossover
        if (
            ema_short.iloc[-1] < ema_long.iloc[-1]
            and ema_short.iloc[-2] >= ema_long.iloc[-2]
        ):
            return -0.5  # Bearish Crossover
        return 0.0

    def _calculate_volume_confirmation(self) -> bool:
        """Checks if the latest volume is significantly above its moving average."""
        vol_ma = Indicators.sma(self.df.volume, self.cfg["volume_ma_period"])
        if vol_ma.empty or pd.isna(vol_ma.iloc[-1]) or vol_ma.iloc[-1] == 0:
            return False
        return (
            self.df.volume.iloc[-1]
            > vol_ma.iloc[-1] * self.cfg["volume_confirmation_multiplier"]
        )

    def _detect_macd_divergence(self) -> str | None:
        """Detects bullish or bearish MACD divergence (simplified logic)."""
        macd_df = Indicators.macd(self.df.close)
        if macd_df.empty or len(self.df) < 30:  # Need sufficient data
            return None

        prices = self.df["close"]
        macd_hist = macd_df["histogram"]

        # Look back a few bars for divergence confirmation
        lookback = 5
        if len(prices) < lookback:
            return None

        # Bullish divergence: Lower lows in price, higher lows in histogram
        price_ll = prices.iloc[-1] < prices.iloc[-lookback]
        macd_hl = macd_hist.iloc[-1] > macd_hist.iloc[-lookback]
        if price_ll and macd_hl:
            self.log.debug(
                f"{NEON_GREEN}Possible Bullish MACD Divergence detected.{RESET}",
            )
            return "bullish"

        # Bearish divergence: Higher highs in price, lower highs in histogram
        price_hh = prices.iloc[-1] > prices.iloc[-lookback]
        macd_lh = macd_hist.iloc[-1] < macd_hist.iloc[-lookback]
        if price_hh and macd_lh:
            self.log.debug(
                f"{NEON_RED}Possible Bearish MACD Divergence detected.{RESET}",
            )
            return "bearish"
        return None

    def analyze(self, price: Decimal, ts: str, order_book: dict[str, Any] | None):
        """Performs a full analysis and logs a detailed summary."""
        # Calculate and store indicators based on config
        indicators_cfg = self.cfg["indicators"]
        periods_cfg = self.cfg["indicator_periods"]

        # Core Indicators
        if indicators_cfg.get("atr"):
            # ATR is already pre-calculated in __init__
            self.indicator_values["atr"] = self.atr_value
        if indicators_cfg.get("ema_alignment"):
            self.indicator_values["ema_alignment"] = self._calculate_ema_alignment()
        if indicators_cfg.get("volume_confirmation"):
            self.indicator_values["volume_confirmation"] = (
                self._calculate_volume_confirmation()
            )

        # Other requested indicators
        if indicators_cfg.get("rsi"):
            rsi_series = Indicators.rsi(self.df.close, periods_cfg["rsi"])
            self.indicator_values["rsi"] = (
                float(rsi_series.iloc[-1]) if not rsi_series.empty else np.nan
            )
        if indicators_cfg.get("macd"):
            macd_df = Indicators.macd(self.df.close)
            self.indicator_values["macd"] = (
                macd_df.iloc[-1].to_dict() if not macd_df.empty else {}
            )
        if indicators_cfg.get("adx"):
            adx_df = Indicators.adx(
                self.df.high, self.df.low, self.df.close, periods_cfg["adx"],
            )
            self.indicator_values["adx"] = (
                float(adx_df["ADX"].iloc[-1]) if not adx_df.empty else np.nan
            )
        if indicators_cfg.get("stochastic_oscillator"):
            stoch_osc_df = Indicators.stochastic_oscillator(
                self.df.close,
                self.df.high,
                self.df.low,
                periods_cfg["stoch_osc_k"],
                periods_cfg["stoch_osc_d"],
            )
            self.indicator_values["stochastic_oscillator"] = (
                stoch_osc_df.iloc[-1].to_dict() if not stoch_osc_df.empty else {}
            )
        if indicators_cfg.get("stoch_rsi"):
            stoch_rsi_df = Indicators.stoch_rsi(
                self.df.close,
                periods_cfg["stoch_rsi_period"],
                periods_cfg["stoch_rsi_k_period"],
                periods_cfg["stoch_rsi_d_period"],
            )
            self.indicator_values["stoch_rsi"] = (
                stoch_rsi_df.iloc[-1].to_dict() if not stoch_rsi_df.empty else {}
            )
        if indicators_cfg.get("momentum"):
            mom_series = Indicators.momentum(self.df.close, periods_cfg["momentum"])
            self.indicator_values["momentum"] = (
                float(mom_series.iloc[-1]) if not mom_series.empty else np.nan
            )
        if indicators_cfg.get("vwap"):
            vwap_series = Indicators.vwap(
                self.df.close, self.df.volume, periods_cfg["vwap"],
            )
            self.indicator_values["vwap"] = (
                float(vwap_series.iloc[-1]) if not vwap_series.empty else np.nan
            )
        if indicators_cfg.get("obv"):
            obv_series = Indicators.obv(self.df.close, self.df.volume)
            self.indicator_values["obv"] = (
                float(obv_series.iloc[-1]) if not obv_series.empty else np.nan
            )
        if indicators_cfg.get("adi"):
            adi_series = Indicators.adi(
                self.df.high, self.df.low, self.df.close, self.df.volume,
            )
            self.indicator_values["adi"] = (
                float(adi_series.iloc[-1]) if not adi_series.empty else np.nan
            )
        if indicators_cfg.get("cci"):
            cci_series = Indicators.cci(
                self.df.high, self.df.low, self.df.close, periods_cfg["cci"],
            )
            self.indicator_values["cci"] = (
                float(cci_series.iloc[-1]) if not cci_series.empty else np.nan
            )
        if indicators_cfg.get("wr"):
            wr_series = Indicators.williams_r(
                self.df.high, self.df.low, self.df.close, periods_cfg["williams_r"],
            )
            self.indicator_values["wr"] = (
                float(wr_series.iloc[-1]) if not wr_series.empty else np.nan
            )
        if indicators_cfg.get("mfi"):
            mfi_series = Indicators.mfi(
                self.df.high,
                self.df.low,
                self.df.close,
                self.df.volume,
                periods_cfg["mfi"],
            )
            self.indicator_values["mfi"] = (
                float(mfi_series.iloc[-1]) if not mfi_series.empty else np.nan
            )
        if indicators_cfg.get("psar"):
            psar_series = Indicators.psar(self.df.high, self.df.low, self.df.close)
            self.indicator_values["psar"] = (
                float(psar_series.iloc[-1]) if not psar_series.empty else np.nan
            )
        if indicators_cfg.get("fve"):
            fve_series = Indicators.fve(
                self.df.close,
                self.df.volume,
                Indicators.atr(
                    self.df.high, self.df.low, self.df.close, periods_cfg["atr"],
                ),
                periods_cfg["fve_price_ema"],
                periods_cfg["fve_obv_sma"],
                periods_cfg["fve_atr_sma"],
            )
            self.indicator_values["fve"] = (
                float(fve_series.iloc[-1]) if not fve_series.empty else np.nan
            )
        if indicators_cfg.get("sma_10"):
            sma_10_series = Indicators.sma(self.df.close, periods_cfg["sma_10"])
            self.indicator_values["sma_10"] = (
                float(sma_10_series.iloc[-1]) if not sma_10_series.empty else np.nan
            )
        if indicators_cfg.get("divergence"):
            self.indicator_values["divergence"] = self._detect_macd_divergence()

        # Order Book Analysis
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
        self.log.info(
            f"\n{'─' * 20} ANALYSIS FOR {self.symbol} ({self.interval}) {'─' * 20}",
        )
        self.log.info(f" Timestamp: {ts} │ Price: {NEON_BLUE}{price:.5f}{RESET}")
        self.log.info(f" ATR({self.cfg['atr_period']}): {self.atr_value:.5f}")

        # Dynamic indicator logging
        for name, value in self.indicator_values.items():
            # Skip complex objects or values handled separately
            if name in [
                "atr",
                "ema_alignment",
                "volume_confirmation",
                "stochastic_oscillator",
                "stoch_rsi",
                "macd",
                "order_book_walls",
                "divergence",
            ]:
                continue
            interpreted_line = interpret_indicator(self.log, name, value)
            if interpreted_line:
                self.log.info(interpreted_line)

        # Log specific complex indicators
        if indicators_cfg.get("ema_alignment"):
            ema_score = self.indicator_values.get("ema_alignment", 0.0)
            status = (
                "Bullish"
                if ema_score > 0
                else "Bearish"
                if ema_score < 0
                else "Neutral"
            )
            self.log.info(
                f"{NEON_PURPLE}EMA Alignment:{RESET} Score={ema_score:+.1f} ({status})",
            )
        if indicators_cfg.get("stochastic_oscillator") and isinstance(
            self.indicator_values.get("stochastic_oscillator"), dict,
        ):
            so_data = self.indicator_values["stochastic_oscillator"]
            self.log.info(
                f"{NEON_CYAN}Stochastic Oscillator:{RESET} K={so_data.get('k', np.nan):.1f}, D={so_data.get('d', np.nan):.1f}",
            )
        if indicators_cfg.get("stoch_rsi") and isinstance(
            self.indicator_values.get("stoch_rsi"), dict,
        ):
            srsi_data = self.indicator_values["stoch_rsi"]
            self.log.info(
                f"{NEON_GREEN}Stoch RSI:{RESET} K={srsi_data.get('stoch_rsi_k', np.nan):.1f}, D={srsi_data.get('stoch_rsi_d', np.nan):.1f} (RSI: {srsi_data.get('rsi', np.nan):.1f})",
            )
        if indicators_cfg.get("macd") and isinstance(
            self.indicator_values.get("macd"), dict,
        ):
            macd_data = self.indicator_values["macd"]
            self.log.info(
                f"{NEON_PURPLE}MACD:{RESET} MACD={macd_data.get('macd', np.nan):.2f}, Signal={macd_data.get('signal', np.nan):.2f}, Hist={macd_data.get('histogram', np.nan):.2f}",
            )
        if indicators_cfg.get("divergence") and self.indicator_values.get("divergence"):
            div_type = self.indicator_values["divergence"]
            self.log.info(
                f"{NEON_YELLOW}Divergence:{RESET} {div_type.upper()} MACD Divergence detected.",
            )

        # Order Book Walls
        self.log.info(f"\n{NEON_BLUE}Order Book Walls:{RESET}")
        if has_bull:
            self.log.info(
                f"{NEON_GREEN}  Bullish Walls Found: {', '.join([f'{k}:{v:,.0f}' for k, v in bullish_details.items()])}{RESET}",
            )
        if has_bear:
            self.log.info(
                f"{NEON_RED}  Bearish Walls Found: {', '.join([f'{k}:{v:,.0f}' for k, v in bearish_details.items()])}{RESET}",
            )
        if not has_bull and not has_bear:
            self.log.info("  No significant walls detected.")

        self.log.info("─" * (42 + len(self.symbol) + len(self.interval)))

    def _analyze_order_book_walls(
        self, order_book: dict[str, Any],
    ) -> tuple[bool, bool, dict[str, Decimal], dict[str, Decimal]]:
        """Detect bullish/bearish walls from bids/asks."""
        enabled = self.cfg.get("order_book_analysis", {}).get("enabled", False)
        if not enabled or not order_book:
            return False, False, {}, {}

        depth = int(self.cfg.get("order_book_depth_to_check", 10))
        bids = [(Decimal(p), Decimal(q)) for p, q in order_book.get("bids", [])[:depth]]
        asks = [(Decimal(p), Decimal(q)) for p, q in order_book.get("asks", [])[:depth]]

        all_qty = [q for _, q in bids] + [q for _, q in asks]
        if not all_qty:
            return False, False, {}, {}

        avg_qty = Decimal(str(np.mean([float(q) for q in all_qty])))
        wall = avg_qty * Decimal(
            str(self.cfg.get("order_book_wall_threshold_multiplier", 2.0)),
        )

        current_price = Decimal(str(self.df.close.iloc[-1]))
        bullish = {}
        bearish = {}

        for price, qty in bids:
            if qty >= wall and price < current_price:
                bullish[f"Bid@{price.quantize(Decimal('0.0001'))}"] = qty
                break

        for price, qty in asks:
            if qty >= wall and price > current_price:
                bearish[f"Ask@{price.quantize(Decimal('0.0001'))}"] = qty
                break

        return bool(bullish), bool(bearish), bullish, bearish

    def generate_trading_signal(self, price: Decimal) -> TradeSignal:
        """Generates a trading signal based on a weighted scoring system."""
        bull_score = Decimal("0.0")
        bull_conditions: list[str] = []
        bear_score = Decimal("0.0")
        bear_conditions: list[str] = []

        indicators_to_check = self.cfg["indicators"]  # Get which indicators are enabled

        # Dynamically check indicators based on config and apply weights
        if (
            indicators_to_check.get("rsi")
            and self.indicator_values.get("rsi") is not None
        ):
            rsi_val = self.indicator_values["rsi"]
            if rsi_val < 30:
                bull_score += Decimal(str(self.weights.get("rsi", 0)))
                bull_conditions.append("RSI Oversold")
            elif rsi_val > 70:
                bear_score += Decimal(str(self.weights.get("rsi", 0)))
                bear_conditions.append("RSI Overbought")

        if (
            indicators_to_check.get("ema_alignment")
            and self.indicator_values.get("ema_alignment") is not None
        ):
            ema_align = self.indicator_values["ema_alignment"]
            if ema_align > 0:
                bull_score += Decimal(
                    str(self.weights.get("ema_alignment", 0)),
                ) * Decimal(str(abs(ema_align)))
                bull_conditions.append("Bullish EMA Align")
            elif ema_align < 0:
                bear_score += Decimal(
                    str(self.weights.get("ema_alignment", 0)),
                ) * Decimal(str(abs(ema_align)))
                bear_conditions.append("Bearish EMA Align")

        if (
            indicators_to_check.get("volume_confirmation")
            and self.indicator_values.get("volume_confirmation") is not None
        ):
            if self.indicator_values["volume_confirmation"]:
                # Volume confirmation is typically for trend confirmation, so needs price context
                # For simplicity, assuming current signal bias determines direction
                # This could be refined by checking price movement direction with volume spike
                if bull_score > bear_score:  # If leaning bullish
                    bull_score += Decimal(
                        str(self.weights.get("volume_confirmation", 0)),
                    )
                    bull_conditions.append("Volume Confirm (Bullish)")
                else:  # If leaning bearish or neutral
                    bear_score += Decimal(
                        str(self.weights.get("volume_confirmation", 0)),
                    )
                    bear_conditions.append("Volume Confirm (Bearish)")

        if indicators_to_check.get("stochastic_oscillator") and isinstance(
            self.indicator_values.get("stochastic_oscillator"), dict,
        ):
            so_data = self.indicator_values["stochastic_oscillator"]
            k_osc, d_osc = (
                Decimal(str(so_data.get("k", np.nan))),
                Decimal(str(so_data.get("d", np.nan))),
            )
            if not pd.isna(k_osc) and not pd.isna(d_osc):
                if k_osc < 20 and k_osc > d_osc:
                    bull_score += Decimal(
                        str(self.weights.get("stochastic_oscillator", 0)),
                    )
                    bull_conditions.append("StochOsc Oversold Cross")
                elif k_osc > 80 and k_osc < d_osc:
                    bear_score += Decimal(
                        str(self.weights.get("stochastic_oscillator", 0)),
                    )
                    bear_conditions.append("StochOsc Overbought Cross")

        if indicators_to_check.get("stoch_rsi") and isinstance(
            self.indicator_values.get("stoch_rsi"), dict,
        ):
            srsi_data = self.indicator_values["stoch_rsi"]
            k_srsi, d_srsi = (
                Decimal(str(srsi_data.get("stoch_rsi_k", np.nan))),
                Decimal(str(srsi_data.get("stoch_rsi_d", np.nan))),
            )
            if not pd.isna(k_srsi) and not pd.isna(d_srsi):
                if (
                    k_srsi < self.cfg["stoch_rsi_oversold_threshold"]
                    and k_srsi > d_srsi
                ):
                    bull_score += Decimal(str(self.weights.get("stoch_rsi", 0)))
                    bull_conditions.append("StochRSI Oversold Cross")
                elif (
                    k_srsi > self.cfg["stoch_rsi_overbought_threshold"]
                    and k_srsi < d_srsi
                ):
                    bear_score += Decimal(str(self.weights.get("stoch_rsi", 0)))
                    bear_conditions.append("StochRSI Overbought Cross")

        if (
            indicators_to_check.get("momentum")
            and self.indicator_values.get("momentum") is not None
        ):
            mom_val = self.indicator_values["momentum"]
            if mom_val > 0.5:  # Example: 0.5% positive momentum
                bull_score += Decimal(str(self.weights.get("momentum", 0)))
                bull_conditions.append("Positive Momentum")
            elif mom_val < -0.5:  # Example: 0.5% negative momentum
                bear_score += Decimal(str(self.weights.get("momentum", 0)))
                bear_conditions.append("Negative Momentum")

        if (
            indicators_to_check.get("vwap")
            and self.indicator_values.get("vwap") is not None
        ):
            vwap_val = Decimal(str(self.indicator_values["vwap"]))
            if price > vwap_val:
                bull_score += Decimal(str(self.weights.get("vwap", 0)))
                bull_conditions.append("Price Above VWAP")
            elif price < vwap_val:
                bear_score += Decimal(str(self.weights.get("vwap", 0)))
                bear_conditions.append("Price Below VWAP")

        if (
            indicators_to_check.get("obv")
            and self.indicator_values.get("obv") is not None
            and len(self.df.index) > 1
        ):
            obv_current = self.indicator_values["obv"]
            obv_prev = Indicators.obv(self.df.close, self.df.volume).iloc[-2]
            if obv_current > obv_prev:
                bull_score += Decimal(str(self.weights.get("obv", 0)))
                bull_conditions.append("OBV Rising")
            elif obv_current < obv_prev:
                bear_score += Decimal(str(self.weights.get("obv", 0)))
                bear_conditions.append("OBV Falling")

        if (
            indicators_to_check.get("adi")
            and self.indicator_values.get("adi") is not None
            and len(self.df.index) > 1
        ):
            adi_current = self.indicator_values["adi"]
            adi_prev = Indicators.adi(
                self.df.high, self.df.low, self.df.close, self.df.volume,
            ).iloc[-2]
            if adi_current > adi_prev:
                bull_score += Decimal(str(self.weights.get("adi", 0)))
                bull_conditions.append("ADI Accumulation")
            elif adi_current < adi_prev:
                bear_score += Decimal(str(self.weights.get("adi", 0)))
                bear_conditions.append("ADI Distribution")

        if (
            indicators_to_check.get("cci")
            and self.indicator_values.get("cci") is not None
        ):
            cci_val = self.indicator_values["cci"]
            if cci_val < -100:
                bull_score += Decimal(str(self.weights.get("cci", 0)))
                bull_conditions.append("CCI Oversold")
            elif cci_val > 100:
                bear_score += Decimal(str(self.weights.get("cci", 0)))
                bear_conditions.append("CCI Overbought")

        if (
            indicators_to_check.get("wr")
            and self.indicator_values.get("wr") is not None
        ):
            wr_val = self.indicator_values["wr"]
            if wr_val < -80:
                bull_score += Decimal(str(self.weights.get("wr", 0)))
                bull_conditions.append("Williams %R Oversold")
            elif wr_val > -20:
                bear_score += Decimal(str(self.weights.get("wr", 0)))
                bear_conditions.append("Williams %R Overbought")

        if (
            indicators_to_check.get("mfi")
            and self.indicator_values.get("mfi") is not None
        ):
            mfi_val = self.indicator_values["mfi"]
            if mfi_val < 20:
                bull_score += Decimal(str(self.weights.get("mfi", 0)))
                bull_conditions.append("MFI Oversold")
            elif mfi_val > 80:
                bear_score += Decimal(str(self.weights.get("mfi", 0)))
                bear_conditions.append("MFI Overbought")

        if (
            indicators_to_check.get("psar")
            and self.indicator_values.get("psar") is not None
        ):
            psar_val = Decimal(str(self.indicator_values["psar"]))
            if price > psar_val:
                bull_score += Decimal(str(self.weights.get("psar", 0)))
                bull_conditions.append("Price Above PSAR")
            elif price < psar_val:
                bear_score += Decimal(str(self.weights.get("psar", 0)))
                bear_conditions.append("Price Below PSAR")

        if (
            indicators_to_check.get("fve")
            and self.indicator_values.get("fve") is not None
        ):
            fve_val = self.indicator_values["fve"]
            # FVE is a composite, interpretation depends on its design (e.g., >0.5 bullish)
            if fve_val > 0.5:  # Arbitrary threshold for FVE for demonstration
                bull_score += Decimal(str(self.weights.get("fve", 0)))
                bull_conditions.append("Positive FVE")
            elif fve_val < -0.5:
                bear_score += Decimal(str(self.weights.get("fve", 0)))
                bear_conditions.append("Negative FVE")

        if (
            indicators_to_check.get("sma_10")
            and self.indicator_values.get("sma_10") is not None
        ):
            sma_10_val = Decimal(str(self.indicator_values["sma_10"]))
            if price > sma_10_val:
                bull_score += Decimal(str(self.weights.get("sma_10", 0)))
                bull_conditions.append("Price Above SMA10")
            elif price < sma_10_val:
                bear_score += Decimal(str(self.weights.get("sma_10", 0)))
                bear_conditions.append("Price Below SMA10")

        if indicators_to_check.get("divergence") and self.indicator_values.get(
            "divergence",
        ):
            div_type = self.indicator_values["divergence"]
            if div_type == "bullish":
                bull_score += Decimal(str(self.weights.get("divergence", 0)))
                bull_conditions.append("Bullish MACD Divergence")
            elif div_type == "bearish":
                bear_score += Decimal(str(self.weights.get("divergence", 0)))
                bear_conditions.append("Bearish MACD Divergence")

        # Order book walls
        order_book_walls_data = self.indicator_values.get("order_book_walls", {})
        if order_book_walls_data.get("bullish"):
            bull_score += Decimal(
                str(self.cfg.get("order_book_support_confidence_boost", 0)),
            ) / Decimal("10.0")
            bull_conditions.append("Bullish Order Book Wall")
        if order_book_walls_data.get("bearish"):
            bear_score += Decimal(
                str(self.cfg.get("order_book_resistance_confidence_boost", 0)),
            ) / Decimal("10.0")
            bear_conditions.append("Bearish Order Book Wall")

        # Final Signal Decision
        signal: str | None = None
        final_score = 0.0
        final_conditions: list[str] = []

        if bull_score >= Decimal(str(self.cfg["signal_score_threshold"])):
            signal = "buy"
            final_score = float(bull_score)
            final_conditions = bull_conditions
        elif bear_score >= Decimal(str(self.cfg["signal_score_threshold"])):
            signal = "sell"
            final_score = float(bear_score)
            final_conditions = bear_conditions

        # Calculate SL/TP levels if a signal is generated
        levels: dict[str, Decimal] = {}
        if signal and self.atr_value > 0:
            atr_d = Decimal(str(self.atr_value))
            sl_mult = Decimal(str(self.cfg["stop_loss_multiple"]))
            tp_mult = Decimal(str(self.cfg["take_profit_multiple"]))
            precision = Decimal("0.00001")  # Define precision for SL/TP

            if signal == "buy":
                levels["stop_loss"] = (price - atr_d * sl_mult).quantize(precision)
                levels["take_profit"] = (price + atr_d * tp_mult).quantize(precision)
            elif signal == "sell":
                levels["stop_loss"] = (price + atr_d * sl_mult).quantize(precision)
                levels["take_profit"] = (price - atr_d * tp_mult).quantize(precision)

        return TradeSignal(signal, final_score, final_conditions, levels)


# ----------------------------------------------------------------------------
# 8. INDICATOR INTERPRETER FOR LOGGING
# ----------------------------------------------------------------------------
def interpret_indicator(
    logger: logging.Logger, indicator_name: str, value: Any,
) -> str | None:
    """Provides a human-readable interpretation of indicator values for logging."""
    if value is None or (isinstance(value, (float, int)) and np.isnan(value)):
        return f"{NEON_YELLOW}{indicator_name.upper()}:{RESET} N/A"

    try:
        # Special handling for dicts (like MACD, Stochastics data)
        if isinstance(value, dict):
            if indicator_name == "macd":
                return f"{NEON_PURPLE}MACD:{RESET} MACD={value.get('macd', np.nan):.2f}, Signal={value.get('signal', np.nan):.2f}, Hist={value.get('histogram', np.nan):.2f}"
            if indicator_name == "stochastic_oscillator":
                return f"{NEON_CYAN}Stochastic Oscillator:{RESET} K={value.get('k', np.nan):.1f}, D={value.get('d', np.nan):.1f}"
            if indicator_name == "stoch_rsi":
                return f"{NEON_GREEN}Stoch RSI:{RESET} K={value.get('stoch_rsi_k', np.nan):.1f}, D={value.get('stoch_rsi_d', np.nan):.1f} (RSI: {value.get('rsi', np.nan):.1f})"
            return f"{NEON_YELLOW}{indicator_name.upper()}:{RESET} Complex data format."

        # Handle simple numerical values
        val_float = float(value)

        if indicator_name == "rsi":
            if val_float > 70:
                return f"{NEON_RED}RSI:{RESET} Overbought ({val_float:.2f})"
            if val_float < 30:
                return f"{NEON_GREEN}RSI:{RESET} Oversold ({val_float:.2f})"
            return f"{NEON_YELLOW}RSI:{RESET} Neutral ({val_float:.2f})"
        if indicator_name == "mfi":
            if val_float > 80:
                return f"{NEON_RED}MFI:{RESET} Overbought ({val_float:.2f})"
            if val_float < 20:
                return f"{NEON_GREEN}MFI:{RESET} Oversold ({val_float:.2f})"
            return f"{NEON_YELLOW}MFI:{RESET} Neutral ({val_float:.2f})"
        if indicator_name == "cci":
            if val_float > 100:
                return f"{NEON_RED}CCI:{RESET} Overbought ({val_float:.2f})"
            if val_float < -100:
                return f"{NEON_GREEN}CCI:{RESET} Oversold ({val_float:.2f})"
            return f"{NEON_YELLOW}CCI:{RESET} Neutral ({val_float:.2f})"
        if indicator_name == "wr":
            if val_float < -80:
                return f"{NEON_GREEN}Williams %R:{RESET} Oversold ({val_float:.2f})"
            if val_float > -20:
                return f"{NEON_RED}Williams %R:{RESET} Overbought ({val_float:.2f})"
            return f"{NEON_YELLOW}Williams %R:{RESET} Neutral ({val_float:.2f})"
        if indicator_name == "adx":
            if val_float > 25:
                return f"{NEON_GREEN}ADX:{RESET} Trending ({val_float:.2f})"
            return f"{NEON_YELLOW}ADX:{RESET} Ranging ({val_float:.2f})"
        if indicator_name == "obv":
            return f"{NEON_BLUE}OBV:{RESET} {val_float:,.0f}"  # Raw OBV value, trend is derived from change
        if indicator_name == "adi":
            return f"{NEON_BLUE}ADI:{RESET} {val_float:,.0f}"  # Raw ADI value, trend is derived from change
        if indicator_name == "sma_10":
            return f"{NEON_YELLOW}SMA (10):{RESET} {val_float:.5f}"
        if indicator_name == "psar":
            return f"{NEON_BLUE}PSAR:{RESET} {val_float:.5f}"
        if indicator_name == "fve":
            if val_float > 0.5:
                return f"{NEON_GREEN}FVE:{RESET} Bullish ({val_float:.2f})"
            if val_float < -0.5:
                return f"{NEON_RED}FVE:{RESET} Bearish ({val_float:.2f})"
            return f"{NEON_YELLOW}FVE:{RESET} Neutral ({val_float:.2f})"
        if indicator_name == "momentum":
            if val_float > 0:
                return f"{NEON_GREEN}Momentum:{RESET} Bullish ({val_float:.2f}%)"
            if val_float < 0:
                return f"{NEON_RED}Momentum:{RESET} Bearish ({val_float:.2f}%)"
            return f"{NEON_YELLOW}Momentum:{RESET} Neutral ({val_float:.2f}%)"
        if indicator_name == "vwap":
            return f"{NEON_BLUE}VWAP:{RESET} {val_float:.5f}"

        return None  # No specific interpretation for other cases
    except Exception as e:
        logger.error(
            f"{NEON_RED}Error interpreting {indicator_name}: {e}. Value: {value}{RESET}",
        )
        return f"{NEON_RED}{indicator_name.upper()}:{RESET} Interpretation error."


# ----------------------------------------------------------------------------
# 9. MAIN APPLICATION LOOP
# ----------------------------------------------------------------------------
def main():
    """Main function to initialize and run the trading bot loop."""
    if not API_KEY or not API_SECRET:
        LOGGER.critical(
            f"{NEON_RED}API credentials (BYBIT_API_KEY, BYBIT_API_SECRET) are missing in .env file.{RESET}",
        )
        return

    symbol = (
        input(f"{NEON_BLUE}Enter symbol (default BTCUSDT): {RESET}") or "BTCUSDT"
    ).upper()
    interval = (
        input(
            f"{NEON_BLUE}Enter interval ({', '.join(VALID_INTERVALS)}) (default {CFG['interval']}): {RESET}",
        )
        or CFG["interval"]
    )
    if interval not in VALID_INTERVALS:
        LOGGER.warning(
            f"{NEON_YELLOW}Invalid interval '{interval}'. Using default '{CFG['interval']}'.{RESET}",
        )
        interval = CFG["interval"]

    symbol_logger = setup_logger(symbol)
    symbol_logger.info(
        f"🚀 WhaleBot Enhanced starting for {NEON_PURPLE}{symbol}{RESET} on interval {NEON_PURPLE}{interval}{RESET}",
    )

    last_signal_time = 0.0
    last_ob_fetch_time = 0.0
    order_book: dict[str, Any] | None = None

    try:
        while True:
            price = fetch_current_price(symbol, symbol_logger)
            if price is None:
                symbol_logger.error(
                    f"{NEON_RED}Failed to fetch current price for {symbol}. Retrying in {CFG['retry_delay']}s...{RESET}",
                )
                time.sleep(CFG["retry_delay"])
                continue

            df = fetch_klines(symbol, interval, 200, symbol_logger, kline_cache)
            if df.empty or len(df) < max(
                CFG["atr_period"],
                CFG["ema_long_period"],
                CFG["indicator_periods"]["adx"],
                CFG["indicator_periods"]["vwap"],
            ):  # Ensure enough data for indicators
                symbol_logger.warning(
                    f"{NEON_YELLOW}Insufficient Kline data received for {symbol} ({interval}). Need more bars. Retrying in {CFG['retry_delay']}s...{RESET}",
                )
                time.sleep(CFG["retry_delay"])
                continue

            current_time = time.time()
            if current_time - last_ob_fetch_time >= CFG["order_book_debounce_s"]:
                order_book = fetch_order_book(
                    symbol, CFG["order_book_depth_to_check"], symbol_logger,
                )
                last_ob_fetch_time = current_time
            else:
                symbol_logger.debug(
                    f"{NEON_YELLOW}Order book fetch debounced. Next in ~{CFG['order_book_debounce_s'] - (current_time - last_ob_fetch_time):.1f}s{RESET}",
                )

            analyzer = TradingAnalyzer(df, CFG, symbol_logger, symbol, interval)
            timestamp_str = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
            analyzer.analyze(price, timestamp_str, order_book)

            trade_signal = analyzer.generate_trading_signal(price)
            if trade_signal.signal and (
                current_time - last_signal_time >= CFG["signal_cooldown_s"]
            ):
                last_signal_time = current_time
                color = NEON_GREEN if trade_signal.signal == "buy" else NEON_RED
                symbol_logger.info(
                    f"\n{color}🔔 {'-' * 10} TRADE SIGNAL: {trade_signal.signal.upper()} {'-' * 10}{RESET}\n"
                    f"   Confidence Score: {trade_signal.confidence:.2f}\n"
                    f"   Conditions Met: {'; '.join(trade_signal.conditions) if trade_signal.conditions else 'None'}\n",
                )
                if trade_signal.levels:
                    sl = trade_signal.levels["stop_loss"]
                    tp = trade_signal.levels["take_profit"]
                    symbol_logger.info(
                        f"   Stop Loss: {sl:.5f} | Take Profit: {tp:.5f}",
                    )
                symbol_logger.info(
                    f"{NEON_YELLOW}   --- Placeholder: Order placement logic would execute here ---{RESET}\n",
                )

            time.sleep(CFG["analysis_interval"])

    except KeyboardInterrupt:
        symbol_logger.info(
            f"\n{NEON_YELLOW}User stopped analysis. Shutting down...{RESET}",
        )
    except Exception as e:
        symbol_logger.exception(
            f"{NEON_RED}An unexpected critical error occurred: {e}{RESET}",
        )
        time.sleep(CFG["retry_delay"] * 2)  # Longer delay for unexpected errors


if __name__ == "__main__":
    main()
