# whalebot_improved.py
# A robust, upgraded Bybit-driven trading bot with ADX support and modular indicators.
# Drop-in replacement with the same public behavior, enhanced internals.

from __future__ import annotations

import os
import json
import time
import random
import hmac
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
import numpy as np
import pandas as pd
from colorama import Fore, Style, init as colorama_init
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from dataclasses import dataclass, field

# Initialize color output
colorama_init(autoreset=True)

# -----------------------------
# 1) Global constants + palette
# -----------------------------
NEON_GREEN  = Fore.LIGHTGREEN_EX
NEON_BLUE   = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED    = Fore.LIGHTRED_EX
RESET       = Style.RESET_ALL

VALID_INTERVALS = ["1", "3", "5", "15", "30", "60", "120", "240", "D", "W", "M"]
RETRY_ERROR_CODES = {429, 500, 502, 503, 504}

TIMEZONE = ZoneInfo("America/Chicago")
BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
LOG_DIR = BASE_DIR / "bot_logs"
LOG_DIR.mkdir(exist_ok=True)

# Decimal precision
getcontext().prec = 12

# API config (will be populated in main or on import)
API_KEY = ""
API_SECRET = ""
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")

# Simple in-file logger (reusable)
def setup_logger(name: str) -> logging.Logger:
    fmt = "%(asctime)s │ %(levelname)-8s │ %(message)s"
    datefmt = "%H:%M:%S"
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(handler)
    return logger

LOGGER = setup_logger("whalebot")

# -----------------------------
# 2) Config handling
# -----------------------------
@dataclass
class BotConfig:
    raw: Dict[str, Any]

    def get(self, key: str, default: Any = None):
        return self.raw.get(key, default)

    def __getitem__(self, key: str):
        return self.raw[key]

def _default_config() -> Dict[str, Any]:
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
        "indicators": {
            "ema_alignment": True,
            "momentum": True,
            "volume_confirmation": True,
            "divergence": True,
            "stoch_rsi": True,
            "rsi": True,
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
        "stoch_rsi_confidence_boost": 5,
        "stoch_rsi_mandatory": False,
        "rsi_confidence_boost": 2,
        "mfi_confidence_boost": 2,
        "order_book_support_confidence_boost": 3,
        "order_book_resistance_confidence_boost": 3,
        "stop_loss_multiple": 1.5,
        "take_profit_multiple": 1.0,
        "order_book_wall_threshold_multiplier": 2.0,
        "order_book_depth_to_check": 10,
        "price_change_threshold": 0.005,
        "atr_change_threshold": 0.005,
        "signal_cooldown_s": 60,
        "order_book_debounce_s": 10,
        "ema_short_period": 12,
        "ema_long_period": 26,
        "volume_confirmation_multiplier": 1.5,
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
        }
    }

def load_config(fp: Path) -> BotConfig:
    defaults = _default_config()
    if not fp.exists():
        LOGGER.warning(f"{NEON_YELLOW}Config not found → creating defaults at {fp}{RESET}")
        fp.write_text(json.dumps(defaults, indent=4))
        return BotConfig(defaults)

    try:
        with open(fp, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        merged = {**defaults, **user_cfg}
        return BotConfig(merged)
    except json.JSONDecodeError as e:
        LOGGER.error(f"{NEON_RED}Corrupt config → {e}. Rebuilding default.{RESET}")
        backup = fp.with_name(fp.stem + f".bak_{int(time.time())}{fp.suffix}")
        fp.rename(backup)
        fp.write_text(json.dumps(defaults, indent=4))
        return BotConfig(defaults)

CFG = load_config(CONFIG_FILE)

# -----------------------------
# 3) Bybit API helpers
# -----------------------------
def _sign(api_secret: str, params: Dict[str, Any]) -> str:
    qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(api_secret.encode(), qs.encode(), hashlib.sha256).hexdigest()

def _log_api_error(resp: requests.Response, logger: Optional[logging.Logger] = None) -> None:
    try:
        data = resp.json()
        if logger:
            logger.error(f"{NEON_RED}API Error {resp.status_code}: {data}{RESET}")
    except Exception:
        if logger:
            logger.error(f"{NEON_RED}API Error {resp.status_code}: {resp.text}{RESET}")

def _send_request(
    method: str,
    endpoint: str,
    api_key: str,
    api_secret: str,
    params: Optional[Dict[str, Any]] = None,
    retries: int = 5,
    logger: Optional[logging.Logger] = None,
) -> Optional[Dict[str, Any]]:
    """Signed Bybit API request with retry/backoff & jitter."""
    params = params or {}
    params["timestamp"] = str(int(time.time() * 1000))
    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": _sign(api_secret, params),
        "X-BAPI-TIMESTAMP": params["timestamp"],
        "Content-Type": "application/json",
    }
    url = f"{BASE_URL}{endpoint}"

    for attempt in range(1, retries + 1):
        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                params=params if method == "GET" else None,
                json=params if method != "GET" else None,
                timeout=10,
            )
            if resp.status_code >= 400:
                if resp.status_code in RETRY_ERROR_CODES:
                    raise requests.HTTPError(f"{resp.status_code}")
                _log_api_error(resp, logger)
                return None

            data = resp.json()
            if data.get("retCode") != 0:
                if logger:
                    logger.error(f"{NEON_RED}Bybit API error: {data.get('retMsg', 'Unknown')} (retCode={data.get('retCode')}){RESET}")
                return None
            return data
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as err:
            backoff = (2 ** attempt) + random.random()
            if logger:
                logger.warning(f"{NEON_YELLOW}HTTP issue: {err} – retry {attempt}/{retries} in {backoff:.2f}s{RESET}")
            time.sleep(backoff)
        except Exception as e:
            if logger:
                logger.error(f"{NEON_RED}Request error: {e}{RESET}")
            time.sleep(1)

    if logger:
        logger.error(f"{NEON_RED}Max retries reached for {method} {endpoint}{RESET}")
    return None

# Convenience wrappers
def fetch_current_price(symbol: str, api_key: str, api_secret: str, logger: logging.Logger) -> Optional[Decimal]:
    endpoint = "/v5/market/tickers"
    data = _send_request("GET", endpoint, api_key, api_secret, {"category": "linear", "symbol": symbol}, logger=logger)
    if not data or data.get("retCode") != 0:
        return None
    result = data.get("result", {})
    lst = result.get("list", [])
    for t in lst:
        if t.get("symbol") == symbol:
            price = t.get("lastPrice")
            return Decimal(price) if price is not None else None
    return None

def fetch_klines(
    symbol: str,
    interval: str,
    api_key: str,
    api_secret: str,
    logger: logging.Logger,
    limit: int = 200,
    cache: Optional[Dict[str, Tuple[datetime, pd.DataFrame]]] = None,
) -> pd.DataFrame:
    """Fetch K-line data with a tiny 30s in-memory cache per symbol/interval."""
    cache = cache or {}
    key = f"{symbol}_{interval}"
    now = datetime.utcnow()
    if key in cache and (now - cache[key][0]).total_seconds() < 30:
        return cache[key][1].copy()

    data = _send_request(
        "GET",
        "/v5/market/kline",
        api_key,
        api_secret,
        {"symbol": symbol, "interval": interval, "limit": limit, "category": "linear"},
        logger=logger,
    )
    if not data or data.get("retCode") != 0:
        return pd.DataFrame()

    lst = data.get("result", {}).get("list", [])
    cols = ["ts", "open", "high", "low", "close", "volume", "turnover"]
    df = pd.DataFrame(lst, columns=cols)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df["ts"] = df["ts"].dt.tz_convert(TIMEZONE)
    for c in ["open", "high", "low", "close", "volume", "turnover"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df.dropna(inplace=True)
    df.sort_values("ts", inplace=True)
    cache[key] = (now, df.copy())
    return df

def fetch_order_book(symbol: str, api_key: str, api_secret: str, logger: logging.Logger, limit: int = 50) -> Optional[Dict[str, Any]]:
    endpoint = "/v5/market/orderbook"
    data = _send_request("GET", endpoint, api_key, api_secret, {"symbol": symbol, "limit": limit, "category": "linear"}, logger=logger)
    if data and data.get("retCode") == 0:
        return data.get("result")
    logger.warning(f"{NEON_YELLOW}Could not fetch order book for {symbol}{RESET}")
    return None

# -----------------------------
# 4) Indicators (modular)
# -----------------------------
class Indicators:
    """Standalone static helpers; easy to extend and unit-test."""

    @staticmethod
    def sma(series: pd.Series, window: int) -> pd.Series:
        return series.rolling(window).mean()

    @staticmethod
    def ema(series: pd.Series, span: int) -> pd.Series:
        return series.ewm(span=span, adjust=False).mean()

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        return Indicators.ema(tr, window)

    @staticmethod
    def rsi(close: pd.Series, window: int) -> pd.Series:
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = Indicators.ema(gain, window)
        avg_loss = Indicators.ema(loss, window)

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.replace([np.inf, -np.inf], np.nan).fillna(0)

    @staticmethod
    def macd(close: pd.Series) -> pd.DataFrame:
        ema12 = Indicators.ema(close, 12)
        ema26 = Indicators.ema(close, 26)
        macd_line = ema12 - ema26
        signal = Indicators.ema(macd_line, 9)
        hist = macd_line - signal
        return pd.DataFrame({"macd": macd_line, "signal": signal, "hist": hist})

    @staticmethod
    def adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> float:
        """
        Robust ADX computation (Wilder smoothing).
        Returns a single float value (last value of ADX).
        """
        # Shifted previous values
        prev_close = close.shift(1)
        # True Range
        TR = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)

        # +DM and -DM
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        plus_DM = ((up_move > down_move) & (up_move > 0)).astype(float) * up_move
        minus_DM = ((down_move > up_move) & (down_move > 0)).astype(float) * down_move

        # Smoothed using EMA (as Wilder's method uses EA)
        TR_s = Indicators.ema(TR, window)
        plus_DM_s = Indicators.ema(plus_DM, window)
        minus_DM_s = Indicators.ema(minus_DM, window)

        # DI values
        plus_DI = 100 * (plus_DM_s / TR_s).replace([np.inf, -np.inf], np.nan)
        minus_DI = 100 * (minus_DM_s / TR_s).replace([np.inf, -np.inf], np.nan)

        # DX
        dx = 100 * (plus_DI - minus_DI).abs() / (plus_DI + minus_DI).replace(0, np.nan)
        dx = dx.fillna(0)

        # ADX (smoothed DX)
        adx_series = Indicators.ema(dx, window)
        return float(adx_series.iloc[-1]) if not adx_series.empty else 0.0

# -----------------------------
# 5) Data structures
# -----------------------------
@dataclass
class TradeSignal:
    signal: Optional[str]
    confidence: float
    conditions: List[str] = field(default_factory=list)
    levels: Dict[str, Decimal] = field(default_factory=dict)

# -----------------------------
# 6) Core analyzer
# -----------------------------
class TradingAnalyzer:
    """TA engine: computes indicators, levels, and generates signals."""

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

        self.indicator_values: Dict[str, Any] = {}
        self.atr_value: float = 0.0
        self.levels: Dict[str, Any] = {"Support": {}, "Resistance": {}}
        self.fib_levels: Dict[str, Decimal] = {}

        self.weight_sets = cfg.get("weight_sets", {})
        self.user_defined_weights = self._select_weight_set()

        # Pre-calc
        self._pre_calculate_indicators()

        # Optional indicators
        if self.cfg.get("indicators", {}).get("stoch_rsi"):
            self.indicator_values["stoch_rsi_vals"] = self._calculate_stoch_rsi()
        if self.cfg.get("indicators", {}).get("stochastic_oscillator"):
            self.indicator_values["stoch_osc_vals"] = self._calculate_stochastic_oscillator()

    def _pre_calculate_indicators(self) -> None:
        """Pre-calc essential indicators used elsewhere."""
        if self.df.empty:
            return
        atr = self._calculate_atr(self.cfg.get("atr_period", 14))
        if not atr.empty:
            self.atr_value = float(atr.iloc[-1])
            self.indicator_values["atr"] = self.atr_value
        self._calculate_momentum_ma()

    def _select_weight_set(self) -> Dict[str, float]:
        atr = self.atr_value
        thresh = self.cfg.get("atr_change_threshold", 0.005)
        if atr > thresh:
            self.log.info(f"{NEON_YELLOW}High volatility detected (ATR={atr:.4f}). Using 'high_volatility' weights.{RESET}")
            return self.weight_sets.get("high_volatility", self.weight_sets["low_volatility"])
        self.log.info(f"{NEON_BLUE}Low volatility detected (ATR={atr:.4f}). Using 'low_volatility' weights.{RESET}")
        return self.weight_sets["low_volatility"]

    def _safe_series_operation(self, series: Optional[pd.Series], operation: str, window: int) -> pd.Series:
        data_series = series if series is not None else self.df["close"]
        if data_series is None or data_series.empty:
            return pd.Series(dtype=float)
        try:
            if operation == "sma":
                return data_series.rolling(window).mean()
            if operation == "ema":
                return data_series.ewm(span=window, adjust=False).mean()
            if operation == "max":
                return data_series.rolling(window).max()
            if operation == "min":
                return data_series.rolling(window).min()
            if operation == "diff":
                return data_series.diff(window)
            if operation == "abs_diff_mean":
                return data_series.rolling(window).apply(lambda x: abs(x - x.mean()).mean(), raw=True)
            if operation == "cumsum":
                return data_series.cumsum()
            return pd.Series(dtype=float)
        except Exception as e:
            self.log.error(f"{NEON_RED}Series operation error: {e}{RESET}")
            return pd.Series(dtype=float)

    # ------------- core indicators -------------
    def _calculate_atr(self, window: int) -> pd.Series:
        if not all(c in self.df.columns for c in ("high", "low", "close")):
            self.log.error(f"{NEON_RED}Missing columns for ATR.{RESET}")
            return pd.Series(dtype=float)
        tr = pd.concat([
            self.df["high"] - self.df["low"],
            (self.df["high"] - self.df["close"].shift()).abs(),
            (self.df["low"] - self.df["close"].shift()).abs(),
        ], axis=1).max(axis=1)
        return self._safe_series_operation(tr, "ema", window)

    def _calculate_rsi(self, window: int) -> pd.Series:
        if "close" not in self.df.columns:
            self.log.error(f"{NEON_RED}Missing 'close' for RSI.{RESET}")
            return pd.Series(dtype=float)
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = self._safe_series_operation(gain, "ema", window)
        avg_loss = self._safe_series_operation(loss, "ema", window)
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.replace([np.inf, -np.inf], np.nan).fillna(0)

    def _calculate_stoch_rsi(self) -> pd.DataFrame:
        """Calculates Stochastic RSI (%K, %D, Stoch RSI)."""
        rsi = self._calculate_rsi(self.cfg["indicator_periods"]["stoch_rsi_period"])
        if rsi.empty:
            return pd.DataFrame()
        min_rsi = self._safe_series_operation(rsi, "min", self.cfg["indicator_periods"]["stoch_rsi_period"])
        max_rsi = self._safe_series_operation(rsi, "max", self.cfg["indicator_periods"]["stoch_rsi_period"])
        denom = (max_rsi - min_rsi).replace(0, np.nan)
        stoch = (rsi - min_rsi) / denom
        stoch = stoch.fillna(0) * 100
        k = self._safe_series_operation(stoch, "sma", 3)
        d = self._safe_series_operation(k, "sma", 3)
        return pd.DataFrame({"stoch_rsi": stoch, "k": k, "d": d})

    def _calculate_stochastic_oscillator(self) -> pd.DataFrame:
        """Calculates Stochastic Oscillator -> %K and %D."""
        k_period = self.cfg["indicator_periods"].get("stoch_osc_k", 14)
        d_period = self.cfg["indicator_periods"].get("stoch_osc_d", 3)
        if not all(col in self.df.columns for col in ("high", "low", "close")):
            self.log.error(f"{NEON_RED}Missing columns for Stochastic Oscillator{RESET}")
            return pd.DataFrame()
        highest_high = self._safe_series_operation(self.df["high"], "max", k_period)
        lowest_low = self._safe_series_operation(self.df["low"], "min", k_period)
        denom = (highest_high - lowest_low).replace(0, np.nan)
        k_line = ((self.df["close"] - lowest_low) / denom * 100).fillna(0)
        d_line = self._safe_series_operation(k_line, "sma", d_period)
        return pd.DataFrame({"k": k_line, "d": d_line})

    def _calculate_momentum_ma(self) -> None:
        """Momentum indicator + MAs for trend strength."""
        if "close" not in self.df.columns or "volume" not in self.df.columns:
            self.log.error(f"{NEON_RED}Missing 'close' or 'volume' for Momentum/MAs.{RESET}")
            return
        self.df["momentum"] = self._calculate_momentum()
        self.df["momentum_ma_short"] = self._calculate_sma(self.cfg["momentum_ma_short"], self.df["momentum"])
        self.df["momentum_ma_long"]  = self._calculate_sma(self.cfg["momentum_ma_long"], self.df["momentum"])
        self.df["volume_ma"] = self._calculate_sma(self.cfg["volume_ma_period"], self.df["volume"])

    def _calculate_momentum(self, period: int = 10) -> pd.Series:
        """Momentum as percent change over N periods."""
        if "close" not in self.df.columns:
            self.log.error(f"{NEON_RED}Missing 'close' for Momentum.{RESET}")
            return pd.Series(dtype=float)
        return (self.df["close"] - self.df["close"].shift(period)) / self.df["close"].shift(period) * 100

    def _calculate_cci(self, window: int = 20, constant: float = 0.015) -> pd.Series:
        if not all(col in self.df.columns for col in ("high", "low", "close")):
            self.log.error(f"{NEON_RED}Missing columns for CCI calculation.{RESET}")
            return pd.Series(dtype=float)
        typical = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_typical = self._safe_series_operation(typical, "sma", window)
        mean_dev = self._safe_series_operation(typical, "abs_diff_mean", window)
        cci = (typical - sma_typical) / (constant * mean_dev)
        return cci.replace([np.inf, -np.inf], np.nan).fillna(0)

    def _calculate_williams_r(self, window: int = 14) -> pd.Series:
        if not all(col in self.df.columns for col in ("high", "low", "close")):
            self.log.error(f"{NEON_RED}Missing columns for Williams %R.{RESET}")
            return pd.Series(dtype=float)
        highest_high = self._safe_series_operation(self.df["high"], "max", window)
        lowest_low = self._safe_series_operation(self.df["low"], "min", window)
        denom = (highest_high - lowest_low).replace(0, np.nan)
        wr = ((highest_high - self.df["close"]) / denom) * -100
        return wr.replace([np.inf, -np.inf], np.nan).fillna(0)

    def _calculate_mfi(self, window: int = 14) -> pd.Series:
        required = ("high", "low", "close", "volume")
        if not all(col in self.df.columns for col in required):
            self.log.error(f"{NEON_RED}Missing columns for MFI calculation.{RESET}")
            return pd.Series(dtype=float)
        typical = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        raw_money_flow = typical * self.df["volume"]
        money_direction = typical.diff()
        positive_flow = raw_money_flow.where(money_direction > 0, 0)
        negative_flow = raw_money_flow.where(money_direction < 0, 0)
        positive_mf = self._safe_series_operation(positive_flow, "sma", window) * window
        negative_mf = self._safe_series_operation(negative_flow, "sma", window) * window
        money_ratio = positive_mf / negative_mf.replace(0, np.nan)
        mfi = 100 - (100 / (1 + money_ratio))
        return mfi.replace([np.inf, -np.inf], np.nan).fillna(0)

    def _calculate_obv(self) -> pd.Series:
        if "close" not in self.df.columns or "volume" not in self.df.columns:
            self.log.error(f"{NEON_RED}Missing 'close' or 'volume' for OBV.{RESET}")
            return pd.Series(dtype=float)
        obv = pd.Series(0.0, index=self.df.index)
        obv.iloc[0] = self.df["volume"].iloc[0]
        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i - 1]
        return obv

    def _calculate_adi(self) -> pd.Series:
        required = ["high", "low", "close", "volume"]
        if not all(col in self.df.columns for col in required):
            self.log.error(f"{NEON_RED}Missing columns for ADI.{RESET}")
            return pd.Series(dtype=float)
        mfm_den = (self.df["high"] - self.df["low"])
        mfm = ((self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])) / mfm_den.replace(0, np.nan)
        mfm = mfm.fillna(0)
        mfv = mfm * self.df["volume"]
        return mfv.cumsum()

    def _calculate_psar(self) -> pd.Series:
        """Crude, robust PSAR-like indicator (not true Parabolic SAR)."""
        psar = pd.Series(index=self.df.index, dtype="float64")
        if self.df.empty or len(self.df) < 2:
            return psar
        psar.iloc[0] = self.df["close"].iloc[0]
        trend = 1 if self.df["close"].iloc[1] > self.df["close"].iloc[0] else -1
        ep = self.df["high"].iloc[0] if trend == 1 else self.df["low"].iloc[0]
        af = 0.02
        for i in range(1, len(self.df)):
            prev = psar.iloc[i - 1]
            curr_h = self.df["high"].iloc[i]
            curr_l = self.df["low"].iloc[i]
            if trend == 1:
                psar.iloc[i] = prev + af * (ep - prev)
                psar.iloc[i] = min(psar.iloc[i], curr_l)
                if curr_h > ep:
                    ep = curr_h
                    af = min(af + 0.02, 0.2)
                if curr_l < psar.iloc[i]:
                    trend = -1
                    psar.iloc[i] = ep
                    ep = curr_l
                    af = 0.02
            else:
                psar.iloc[i] = prev + af * (ep - prev)
                psar.iloc[i] = max(psar.iloc[i], curr_h)
                if curr_l < ep:
                    ep = curr_l
                    af = min(af + 0.02, 0.2)
                if curr_h > psar.iloc[i]:
                    trend = 1
                    psar.iloc[i] = ep
                    ep = curr_h
                    af = 0.02
        return psar

    def _calculate_fve(self) -> pd.Series:
        """FVE-like composite for demonstration. Not a standard indicator."""
        if "close" not in self.df.columns or "volume" not in self.df.columns:
            self.log.error(f"{NEON_RED}Missing 'close' or 'volume' for FVE.{RESET}")
            return pd.Series(dtype=float)
        min_points = max(20, self.cfg.get("atr_period", 14))
        if len(self.df) < min_points:
            self.log.warning(f"{NEON_YELLOW}Insufficient data for FVE. Need {min_points} bars.{RESET}")
            return pd.Series([np.nan] * len(self.df), index=self.df.index)

        price_component = self._calculate_ema(self.df["close"], self.cfg["indicator_periods"].get("fve_price_ema", 10))
        obv_component = self._calculate_obv()
        atr_component = self._calculate_atr(self.cfg["indicator_periods"].get("atr", 14))

        # Normalize via Decimal arithmetic for precision
        def to_dec(s: pd.Series) -> pd.Series:
            return s.map(lambda v: Decimal(str(v)) if pd.notna(v) else Decimal('NaN'))

        p_dec = to_dec(price_component)
        o_dec = to_dec(obv_component)
        a_dec = to_dec(atr_component)

        p_mean = Decimal(str(p_dec.mean())) if not p_dec.isna().all() else Decimal('NaN')
        p_std  = Decimal(str(p_dec.std())) if not p_dec.isna().all() else Decimal('NaN')
        o_mean = Decimal(str(o_dec.mean())) if not o_dec.isna().all() else Decimal('NaN')
        o_std  = Decimal(str(o_dec.std())) if not o_dec.isna().all() else Decimal('NaN')
        a_mean = Decimal(str(a_dec.mean())) if not a_dec.isna().all() else Decimal('NaN')
        a_std  = Decimal(str(a_dec.std())) if not a_dec.isna().all() else Decimal('NaN')

        price_norm = (p_dec - p_mean) / p_std if p_std != Decimal('0') else pd.Series(Decimal('0'), index=self.df.index)
        obv_norm   = (o_dec - o_mean) / o_std if o_std != Decimal('0') else pd.Series(Decimal('0'), index=self.df.index)
        atr_inv    = pd.Series([Decimal('1.0') / x if x and x != 0 else Decimal('NaN') for x in a_dec], index=self.df.index)
        atr_inv = atr_inv.replace([Decimal('Infinity'), Decimal('-Infinity')], Decimal('NaN'))
        atr_inv_mean = Decimal(str(atr_inv.mean())) if not atr_inv.isna().all() else Decimal('NaN')
        atr_inv_std = Decimal(str(atr_inv.std())) if not atr_inv.isna().all() else Decimal('NaN')
        atr_inv_norm = (atr_inv - atr_inv_mean) / atr_inv_std if atr_inv_std != Decimal('0') else pd.Series(Decimal('0'), index=self.df.index)

        fve = price_norm.fillna(Decimal('0')) + obv_norm.fillna(Decimal('0')) + atr_inv_norm.fillna(Decimal('0'))
        return pd.Series([float(v) if v != Decimal('NaN') else np.nan for v in fve], index=self.df.index)

    def _calculate_macd(self) -> pd.DataFrame:
        return Indicators.macd(self.df["close"])

    def _calculate_ema(self, series: pd.Series, span: int) -> pd.Series:
        return Indicators.ema(series, span)

    def _calculate_sma(self, window: int, series: Optional[pd.Series] = None) -> pd.Series:
        return self._safe_series_operation(series, "sma", window)

    def _calculate_ada(self) -> None:
        # Placeholder for future custom indicators if needed
        pass

    # ------------- ADX (new) -------------
    def _calculate_adx(self, window: int = 14) -> float:
        """Compute ADX with Wilder smoothing from high/low/close."""
        if not all(col in self.df.columns for col in ("high", "low", "close")):
            self.log.error(f"{NEON_RED}Missing columns for ADX calculation.{RESET}")
            return 0.0

        high = self.df["high"]
        low = self.df["low"]
        close = self.df["close"]

        prev_close = close.shift(1)

        # True Range (TR)
        TR = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)

        # +DM and -DM
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        plus_DM = ((up_move > down_move) & (up_move > 0)).astype(float) * up_move
        minus_DM = ((down_move > up_move) & (down_move > 0)).astype(float) * down_move

        # Smooth using EMA (as Wilder's smoothing is effectively a running EMA)
        TR_s = Indicators.ema(TR, window)
        plus_DM_s = Indicators.ema(plus_DM, window)
        minus_DM_s = Indicators.ema(minus_DM, window)

        # DI values
        plus_DI = 100 * (plus_DM_s / TR_s).replace([np.inf, -np.inf], np.nan)
        minus_DI = 100 * (minus_DM_s / TR_s).replace([np.inf, -np.inf], np.nan)

        # DX
        DX = 100 * (plus_DI - minus_DI).abs() / (plus_DI + minus_DI).replace(0, np.nan)
        DX = DX.fillna(0)

        # ADX (EMA of DX)
        ADX = Indicators.ema(DX, window)
        adx_value = float(ADX.iloc[-1]) if not ADX.empty else 0.0
        return adx_value

    # ------------- analysis orchestration -------------
    def calculate_fibonacci_retracement(self, high: Decimal, low: Decimal, current_price: Decimal) -> Dict[str, Decimal]:
        diff = high - low
        if diff <= 0:
            self.log.warning(f"{NEON_YELLOW}Cannot calculate Fibonacci retracement: High <= Low.{RESET}")
            self.fib_levels = {}
            self.levels = {"Support": {}, "Resistance": {}}
            return {}

        ratios = {
            "23.6%": Decimal('0.236'), "38.2%": Decimal('0.382'), "50.0%": Decimal('0.500'),
            "61.8%": Decimal('0.618'), "78.6%": Decimal('0.786'), "88.6%": Decimal('0.886'),
            "94.1%": Decimal('0.941')
        }
        fib_levels = {f"Fib {lab}": (high - diff * rat).quantize(Decimal('0.00001')) for lab, rat in ratios.items()}
        self.fib_levels = fib_levels
        self.levels = {"Support": {}, "Resistance": {}}
        for lab, val in fib_levels.items():
            if val < current_price:
                self.levels["Support"][lab] = val
            elif val > current_price:
                self.levels["Resistance"][lab] = val
        return fib_levels

    def calculate_pivot_points(self, high: Decimal, low: Decimal, close: Decimal) -> None:
        pivot = (high + low + close) / 3
        r1 = (2 * pivot) - low
        s1 = (2 * pivot) - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)
        r3 = high + 2 * (pivot - low)
        s3 = low - 2 * (high - pivot)

        precision = Decimal('0.00001')
        self.levels.update({
            "Pivot": pivot.quantize(precision),
            "R1": r1.quantize(precision), "S1": s1.quantize(precision),
            "R2": r2.quantize(precision), "S2": s2.quantize(precision),
            "R3": r3.quantize(precision), "S3": s3.quantize(precision),
        })

    def find_nearest_levels(self, current_price: Decimal, num_levels: int = 5) -> Tuple[List[Tuple[str, Decimal]], List[Tuple[str, Decimal]]]:
        """Return nearest supports and resistances based on Fibonacci/Pivot data."""
        supports: List[Tuple[str, Decimal]] = [(lab, val) for lab, val in self.levels.get("Support", {}).items()]
        resistances: List[Tuple[str, Decimal]] = [(lab, val) for lab, val in self.levels.get("Resistance", {}).items()]

        supports = sorted(supports, key=lambda t: current_price - t[1])
        resistances = sorted(resistances, key=lambda t: t[1] - current_price)

        return supports[:num_levels], resistances[:num_levels]

    # ------------- order-book walls -------------
    def analyze_order_book_walls(self, order_book: Dict[str, Any]) -> Tuple[bool, bool, Dict[str, Decimal], Dict[str, Decimal]]:
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
        wall = avg_qty * Decimal(str(self.cfg.get("order_book_wall_threshold_multiplier", 2.0)))

        current_price = Decimal(str(self.df["close"].iloc[-1]))
        bullish = {}
        bearish = {}

        for price, qty in bids:
            if qty >= wall and price < current_price:
                bullish[f"Bid@{price}"] = qty
                break

        for price, qty in asks:
            if qty >= wall and price > current_price:
                bearish[f"Ask@{price}"] = qty
                break

        return bool(bullish), bool(bearish), bullish, bearish

    # ------------- analysis orchestration -------------
    def analyze(self, current_price: Decimal, timestamp: str, order_book: Optional[Dict[str, Any]]) -> None:
        """Compute indicators, levels, and log a summary."""
        cur = Decimal(str(current_price))
        high = Decimal(str(self.df["high"].max()))
        low = Decimal(str(self.df["low"].min()))
        close = Decimal(str(self.df["close"].iloc[-1]))

        # Levels
        self.calculate_fibonacci_retracement(high, low, cur)
        self.calculate_pivot_points(high, low, close)
        nearest_supports, nearest_resistances = self.find_nearest_levels(cur)

        # Indicators (RSI, MFI, CCI, WR, etc.)
        if self.cfg.get("indicators", {}).get("obv"):
            obv = self._calculate_obv()
            self.indicator_values["obv"] = obv.iloc[-3:].tolist() if not obv.empty else []
        if self.cfg.get("indicators", {}).get("rsi"):
            rsi = self._calculate_rsi(self.cfg["indicator_periods"]["rsi"])
            self.indicator_values["rsi"] = rsi.iloc[-3:].tolist() if not rsi.empty else []
        if self.cfg.get("indicators", {}).get("mfi"):
            mfi = self._calculate_mfi(self.cfg["indicator_periods"]["mfi"])
            self.indicator_values["mfi"] = mfi.iloc[-3:].tolist() if not mfi.empty else []
        if self.cfg.get("indicators", {}).get("cci"):
            cci = self._calculate_cci(self.cfg["indicator_periods"]["cci"])
            self.indicator_values["cci"] = cci.iloc[-3:].tolist() if not cci.empty else []
        if self.cfg.get("indicators", {}).get("wr"):
            wr = self._calculate_williams_r(self.cfg["indicator_periods"]["williams_r"])
            self.indicator_values["wr"] = wr.iloc[-3:].tolist() if not wr.empty else []
        if self.cfg.get("indicators", {}).get("adx"):
            adx = self._calculate_adx(self.cfg["indicator_periods"]["adx"])
            self.indicator_values["adx"] = [adx]  # ADX is a single value
        if self.cfg.get("indicators", {}).get("adi"):
            adi = self._calculate_adi()
            self.indicator_values["adi"] = adi.iloc[-3:].tolist() if not adi.empty else []
        if self.cfg.get("indicators", {}).get("momentum"):
            trend = self.determine_trend_momentum()
            self.indicator_values["mom"] = trend
        if self.cfg.get("indicators", {}).get("sma_10"):
            sma10 = self._calculate_sma(10, self.df["close"])
            self.indicator_values["sma_10"] = [sma10.iloc[-1]] if not sma10.empty else []
        if self.cfg.get("indicators", {}).get("psar"):
            psar = self._calculate_psar()
            self.indicator_values["psar"] = psar.iloc[-3:].tolist() if not psar.empty else []
        if self.cfg.get("indicators", {}).get("fve"):
            fve = self._calculate_fve()
            self.indicator_values["fve"] = fve.iloc[-3:].tolist() if not fve.empty else []
        if self.cfg.get("indicators", {}).get("macd"):
            macd = self._calculate_macd()
            self.indicator_values["macd"] = macd.iloc[-3:].values.tolist() if not macd.empty else []
        if self.cfg.get("indicators", {}).get("ema_alignment"):
            self.indicator_values["ema_alignment"] = self._calculate_ema_alignment()
        if self.cfg.get("indicators", {}).get("stoch_rsi"):
            self.indicator_values["stoch_rsi"] = self.indicator_values.get("stoch_rsi_vals", pd.DataFrame()).to_dict("records")[-1] if isinstance(self.indicator_values.get("stoch_rsi_vals"), pd.DataFrame) else []
        if self.cfg.get("indicators", {}).get("stochastic_oscillator"):
            self.indicator_values["stoch_osc"] = self.indicator_values.get("stoch_osc_vals", pd.DataFrame()).to_dict("records")[-1] if isinstance(self.indicator_values.get("stoch_osc_vals"), pd.DataFrame) else []

        # Order book analysis
        has_bull, has_bear, bullish_details, bearish_details = self.analyze_order_book_walls(order_book or {})
        self.indicator_values["order_book_walls"] = {
            "bullish": has_bull,
            "bearish": has_bear,
            "bullish_details": bullish_details,
            "bearish_details": bearish_details,
        }

        # Pretty log output
        output = f"""
{NEON_BLUE}Exchange:{RESET} Bybit
{NEON_BLUE}Symbol:{RESET} {self.symbol}
{NEON_BLUE}Interval:{RESET} {self.interval}
{NEON_BLUE}Timestamp:{RESET} {timestamp}
{NEON_BLUE}Current Price:{RESET} {cur:.5f}
{NEON_BLUE}ATR ({self.cfg['atr_period']}):{RESET} {self.atr_value:.5f}
{NEON_BLUE}Trend:{RESET} {self.indicator_values.get("mom", {}).get("trend", "N/A")} (Strength: {self.indicator_values.get("mom", {}).get("strength", 0.0):.2f})
"""
        for name, values in self.indicator_values.items():
            if name in ("mom", "atr", "stoch_rsi_vals", "ema_alignment", "order_book_walls", "stoch_osc_vals"):
                continue
            interpreted = interpret_indicator(self.log, name, values)
            if interpreted:
                output += interpreted + "\n"

        # Stochastic gauge
        if self.cfg.get("indicators", {}).get("stochastic_oscillator"):
            stoc_osc_vals = self.indicator_values.get("stoch_osc_vals")
            if stoc_osc_vals is not None and isinstance(stoc_osc_vals, pd.DataFrame) and not stoc_osc_vals.empty:
                k = stoc_osc_vals["k"].iloc[-1]
                d = stoc_osc_vals["d"].iloc[-1]
                output += f"{NEON_BLUE}Stochastic Oscillator: K={k:.2f}, D={d:.2f}{RESET}\n"

        output += "\n" + f"{NEON_BLUE}Support/Resistance Levels:{RESET}\n"
        if nearest_supports := nearest_supports:
            for lab, val in nearest_supports:
                output += f"S: {lab} ${val:.5f}\n"
        if nearest_resistances := nearest_resistances:
            for lab, val in nearest_resistances:
                output += f"R: {lab} ${val:.5f}\n"

        self.log.info(output)

    def determine_trend_momentum(self) -> Dict[str, Union[str, float]]:
        """Trend based on momentum MAs, normalized by ATR."""
        if self.df.empty or len(self.df) < max(self.cfg.get("momentum_ma_long", 26), self.cfg.get("atr_period", 14)):
            return {"trend": "Insufficient Data", "strength": 0.0}
        latest_short = self.df["momentum_ma_short"].iloc[-1]
        latest_long = self.df["momentum_ma_long"].iloc[-1]
        trend = "Neutral"
        if latest_short > latest_long:
            trend = "Uptrend"
        elif latest_short < latest_long:
            trend = "Downtrend"
        strength = abs(latest_short - latest_long) / self.atr_value if self.atr_value else 0.0
        return {"trend": trend, "strength": strength}

    def _calculate_obv(self) -> pd.Series:
        if "close" not in self.df.columns or "volume" not in self.df.columns:
            self.log.error(f"{NEON_RED}Missing 'close' or 'volume' for OBV.{RESET}")
            return pd.Series(dtype=float)
        obv = pd.Series(0.0, index=self.df.index)
        obv.iloc[0] = self.df["volume"].iloc[0]
        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i - 1]
        return obv

    def _calculate_adi(self) -> pd.Series:
        needed = ["high", "low", "close", "volume"]
        if not all(x in self.df.columns for x in needed):
            self.log.error(f"{NEON_RED}Missing columns for ADI.{RESET}")
            return pd.Series(dtype=float)
        mfm_den = (self.df["high"] - self.df["low"])
        mfm = ((self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])) / mfm_den.replace(0, np.nan)
        mfm = mfm.fillna(0)
        mfv = mfm * self.df["volume"]
        return mfv.cumsum()

    def _calculate_psar(self) -> pd.Series:
        """Returns a PSAR-like series (not a strict Parabolic SAR)."""
        psar = pd.Series(index=self.df.index, dtype="float64")
        if self.df.empty or len(self.df) < 2:
            return psar
        psar.iloc[0] = self.df["close"].iloc[0]
        trend = 1 if self.df["close"].iloc[1] > self.df["close"].iloc[0] else -1
        ep = self.df["high"].iloc[0] if trend == 1 else self.df["low"].iloc[0]
        af = 0.02
        for i in range(1, len(self.df)):
            prev = psar.iloc[i - 1]
            curr_h = self.df["high"].iloc[i]
            curr_l = self.df["low"].iloc[i]
            if trend == 1:
                psar.iloc[i] = prev + af * (ep - prev)
                psar.iloc[i] = min(psar.iloc[i], curr_l)
                if curr_h > ep:
                    ep = curr_h
                    af = min(af + 0.02, 0.2)
                if curr_l < psar.iloc[i]:
                    trend = -1
                    psar.iloc[i] = ep
                    ep = curr_l
                    af = 0.02
            else:
                psar.iloc[i] = prev + af * (ep - prev)
                psar.iloc[i] = max(psar.iloc[i], curr_h)
                if curr_l < ep:
                    ep = curr_l
                    af = min(af + 0.02, 0.2)
                if curr_h > psar.iloc[i]:
                    trend = 1
                    psar.iloc[i] = ep
                    ep = curr_h
                    af = 0.02
        return psar

    def _log_indicator(self, name: str, values: Any) -> None:
        """Optional hook for structured indicator logging (unused)."""
        self.log.debug(f"{name}: {values!r}")

    # ------------- signal generation -------------
    def generate_trading_signal(self, current_price: Decimal) -> TradeSignal:
        """Return a bull/bear signal with a score and SL/TP if available."""
        signal_score = Decimal("0.0")
        signal: Optional[str] = None
        conditions: List[str] = []
        trade_levels: Dict[str, Decimal] = {}

        # Bullish checks (simplified but extensible)
        if self.cfg.get("indicators", {}).get("stoch_rsi") and self.indicator_values.get("stoch_rsi_vals"):
            srs = self.indicator_values["stoch_rsi_vals"]
            try:
                k = Decimal(str(srs.get("k", 0) if isinstance(srs, dict) else 0))
                d = Decimal(str(srs.get("d", 0) if isinstance(srs, dict) else 0))
                if k < Decimal(self.cfg.get("stoch_rsi_oversold_threshold", 20)) and k > d:
                    w = self.user_defined_weights.get("stoch_rsi", 0)
                    signal_score += Decimal(str(w))
                    conditions.append("Stoch RSI Oversold Crossover")
            except Exception:
                pass

        # RSI
        if self.cfg.get("indicators", {}).get("rsi") and "rsi" in self.indicator_values:
            rsi_val = self.indicator_values["rsi"][-1] if isinstance(self.indicator_values["rsi"], list) else None
            if rsi_val is not None and Decimal(str(rsi_val)) < Decimal("30"):
                signal_score += Decimal(str(self.user_defined_weights.get("rsi", 0)))
                conditions.append("RSI Oversold")

        # MFI
        if self.cfg.get("indicators", {}).get("mfi") and "mfi" in self.indicator_values:
            mfi_val = self.indicator_values["mfi"][-1] if isinstance(self.indicator_values["mfi"], list) else None
            if mfi_val is not None and Decimal(str(mfi_val)) < Decimal("20"):
                signal_score += Decimal(str(self.user_defined_weights.get("mfi", 0)))
                conditions.append("MFI Oversold")

        # EMA alignment
        ema_align = self.indicator_values.get("ema_alignment", 0.0)
        if self.cfg.get("indicators", {}).get("ema_alignment") and ema_align > 0:
            signal_score += Decimal(str(self.user_defined_weights.get("ema_alignment", 0))) * Decimal(str(abs(ema_align)))
            conditions.append("Bullish EMA Alignment")

        # Volume confirmation
        if self.cfg.get("indicators", {}).get("volume_confirmation") and self._volume_confirmation():
            signal_score += Decimal(str(self.user_defined_weights.get("volume_confirmation", 0)))
            conditions.append("Volume Confirmation")

        # Divergence (MACD divergence as placeholder)
        if self.cfg.get("indicators", {}).get("divergence") and self.detect_macd_divergence() == "bullish":
            signal_score += Decimal(str(self.user_defined_weights.get("divergence", 0)))
            conditions.append("Bullish MACD Divergence")

        if self.indicator_values.get("order_book_walls", {}).get("bullish"):
            # small boost for order book walls
            signal_score += Decimal(str(self.cfg.get("order_book_support_confidence_boost", 3))) / Decimal("10.0")
            conditions.append("Bullish Order Book Wall")

        # Bearish side
        bearish_score = Decimal("0.0")
        bearish_conditions: List[str] = []

        if self.cfg.get("indicators", {}).get("stochastic_oscillator") and self.indicator_values.get("stoch_osc_vals"):
            stoch = self.indicator_values["stoch_osc_vals"]
            k = Decimal(str(stoch.get("k", 0) if isinstance(stoch, dict) else 0))
            d = Decimal(str(stoch.get("d", 0) if isinstance(stoch, dict) else 0))
            if k > Decimal("70") and k < d:
                w = self.user_defined_weights.get("stochastic_oscillator", 0)
                bearish_score += Decimal(str(w))
                bearish_conditions.append("Stoch Oscillator Overbought Crossover")

        if "rsi" in self.indicator_values:
            rsi_last = Decimal(str(self.indicator_values.get("rsi", [])[ -1 ])) if isinstance(self.indicator_values.get("rsi"), list) and self.indicator_values["rsi"] else None
            if rsi_last is not None and rsi_last > Decimal("70"):
                bearish_score += Decimal(str(self.user_defined_weights.get("rsi", 0)))
                bearish_conditions.append("RSI Overbought")

        if self.indicator_values.get("mfi"):
            mfi_last = Decimal(str(self.indicator_values.get("mfi", [])[ -1 ])) if isinstance(self.indicator_values.get("mfi"), list) and self.indicator_values["mfi"] else None
            if mfi_last is not None and mfi_last > Decimal("80"):
                bearish_score += Decimal(str(self.user_defined_weights.get("mfi", 0)))
                bearish_conditions.append("MFI Overbought")

        # Decide final signal
        if signal is None and bearish_score >= Decimal(str(self.cfg.get("signal_score_threshold", 1.0))):
            signal = "sell"
            signal_score = bearish_score
            conditions = bearish_conditions

            if self.atr_value > 0:
                atr = Decimal(str(self.atr_value))
                sl = current_price + (atr * Decimal(str(self.cfg.get("stop_loss_multiple", 1.5))))
                tp = current_price - (atr * Decimal(str(self.cfg.get("take_profit_multiple", 1.0))))
                trade_levels["stop_loss"] = sl.quantize(Decimal("0.00001"))
                trade_levels["take_profit"] = tp.quantize(Decimal("0.00001"))

        # For bullish, also compute SL/TP
        if signal == "buy" and self.atr_value > 0:
            atr = Decimal(str(self.atr_value))
            sl = current_price - (atr * Decimal(str(self.config.get("stop_loss_multiple", 1.5)))) if hasattr(self, "config") else current_price - (atr * Decimal("1.5"))
            # We used self.cfg above; keep consistent
            sl = current_price - (atr * Decimal(str(self.cfg.get("stop_loss_multiple", 1.5))))
            tp = current_price + (atr * Decimal(str(self.cfg.get("take_profit_multiple", 1.0))))
            trade_levels["stop_loss"] = sl.quantize(Decimal("0.00001"))
            trade_levels["take_profit"] = tp.quantize(Decimal("0.00001"))

        return TradeSignal(signal, float(signal_score), conditions, trade_levels)

    # ------------- helpers -------------
    def _volume_confirmation(self) -> bool:
        if "volume" not in self.df.columns or "volume_ma" not in self.df.columns:
            self.log.error(f"{NEON_RED}Missing 'volume' or 'volume_ma' for volume confirmation.{RESET}")
            return False
        current = self.df["volume"].iloc[-1]
        avg = self.df["volume_ma"].iloc[-1]
        if avg <= 0:
            return False
        return current > avg * self.cfg.get("volume_confirmation_multiplier", 1.5)

# -----------------------------
# 7) Indicator interpreter
# -----------------------------
def interpret_indicator(logger: logging.Logger, indicator_name: str, values: Any) -> Optional[str]:
    """Human-friendly interpretation for logged indicators."""
    if values is None:
        return None
    try:
        if isinstance(values, dict):
            if indicator_name == "mom":
                trend = values.get("trend", "N/A")
                strength = values.get("strength", 0.0)
                return f"{NEON_PURPLE}Momentum Trend:{RESET} {trend} (Strength: {strength:.2f})"
            return None

        if isinstance(values, pd.DataFrame):
            if indicator_name in ("stoch_rsi_vals", "stoch_osc_vals"):
                return None
            return None

        last = values[-1] if isinstance(values, list) and values else values

        if indicator_name == "rsi":
            lv = float(last)
            if lv > 70:
                return f"{NEON_RED}RSI:{RESET} Overbought ({lv:.2f})"
            if lv < 30:
                return f"{NEON_GREEN}RSI:{RESET} Oversold ({lv:.2f})"
            return f"{NEON_YELLOW}RSI:{RESET} Neutral ({lv:.2f})"

        if indicator_name == "mfi":
            lv = float(last)
            if lv > 80:
                return f"{NEON_RED}MFI:{RESET} Overbought ({lv:.2f})"
            if lv < 20:
                return f"{NEON_GREEN}MFI:{RESET} Oversold ({lv:.2f})"
            return f"{NEON_YELLOW}MFI:{RESET} Neutral ({lv:.2f})"

        if indicator_name == "cci":
            lv = float(last)
            if lv > 100:
                return f"{NEON_RED}CCI:{RESET} Overbought ({lv:.2f})"
            if lv < -100:
                return f"{NEON_GREEN}CCI:{RESET} Oversold ({lv:.2f})"
            return f"{NEON_YELLOW}CCI:{RESET} Neutral ({lv:.2f})"

        if indicator_name == "wr":
            lv = float(last)
            if lv < -80:
                return f"{NEON_GREEN}Williams %R:{RESET} Oversold ({lv:.2f})"
            if lv > -20:
                return f"{NEON_RED}Williams %R:{RESET} Overbought ({lv:.2f})"
            return f"{NEON_YELLOW}Williams %R:{RESET} Neutral ({lv:.2f})"

        if indicator_name == "adx":
            lv = float(last)
            if lv > 25:
                return f"{NEON_GREEN}ADX:{RESET} Trending ({lv:.2f})"
            return f"{NEON_YELLOW}ADX:{RESET} Ranging ({lv:.2f})"

        if indicator_name == "obv":
            if isinstance(values, list) and len(values) >= 2:
                up = values[-1]
                prev = values[-2]
                status = "Bullish" if up > prev else "Bearish" if up < prev else "Neutral"
                return f"{NEON_BLUE}OBV:{RESET} {status}"
            return f"{NEON_BLUE}OBV:{RESET} {float(last) if isinstance(last, (int, float)) else last}"

        if indicator_name == "adi":
            if isinstance(values, list) and len(values) >= 2:
                status = "Accumulation" if values[-1] > values[-2] else "Distribution" if values[-1] < values[-2] else "Neutral"
                return f"{NEON_GREEN}ADI:{RESET} {status}"
            return f"{NEON_GREEN}ADI:{RESET} {float(last) if isinstance(last, (int, float)) else last}"

        if indicator_name == "sma_10":
            return f"{NEON_YELLOW}SMA (10):{RESET} {float(last):.2f}"

        if indicator_name == "macd":
            if isinstance(values, list) and len(values) > 0:
                last = values[-1]
                if isinstance(last, (list, tuple)) and len(last) == 3:
                    macd, signal, hist = last
                    return f"{NEON_GREEN}MACD:{RESET} MACD={macd:.2f}, Signal={signal:.2f}, Histogram={hist:.2f}"
            return f"{NEON_RED}MACD:{RESET} Calculation issue."

        if indicator_name == "fve":
            return f"{NEON_BLUE}FVE:{RESET} {float(last):.2f}"

        return None
    except Exception as e:
        LOGGER_error = getattr(globals(), "LOGGER", None)
        if LOGGER_error:
            LOGGER_error.error(f"{NEON_RED}Error interpreting {indicator_name}: {e}{RESET}")
        return None

# -----------------------------
# 8) MAIN LOOP
# -----------------------------
def main() -> None:
    """Entrypoint: load config, fetch API keys, run main loop."""
    global API_KEY, API_SECRET, BASE_URL
    load_dotenv()
    API_KEY = os.getenv("BYBIT_API_KEY") or ""
    API_SECRET = os.getenv("BYBIT_API_SECRET") or ""
    BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")

    if not API_KEY or not API_SECRET:
        LOGGER.error(f"{NEON_RED}BYBIT_API_KEY and BYBIT_API_SECRET must be set in .env.{RESET}")
        return

    # User input for symbol and interval
    symbol = input(f"{NEON_BLUE}Enter trading symbol (e.g., BTCUSDT): {RESET}").upper().strip() or "BTCUSDT"
    interval = input(f"{NEON_BLUE}Enter timeframe ({', '.join(VALID_INTERVALS)} or press Enter for default {CFG.get('interval', '15')}): {RESET}").strip()
    if interval not in VALID_INTERVALS:
        interval = CFG.get("interval", "15")

    symbol_logger = setup_logger(symbol)
    symbol_logger.info(f"{NEON_BLUE}Starting WhaleBot for {symbol} @ {interval}{RESET}")

    klines_cache: Dict[str, Tuple[datetime, pd.DataFrame]] = {}
    last_signal_ts = 0.0
    last_ob_ts = 0.0
    order_book_cached: Optional[Dict[str, Any]] = None

    try:
        while True:
            price = fetch_current_price(symbol, API_KEY, API_SECRET, symbol_logger)
            if price is None:
                symbol_logger.error(f"{NEON_RED}Failed to fetch current price. Waiting and retrying...{RESET}")
                time.sleep(CFG.get("retry_delay", 5))
                continue

            df = fetch_klines(symbol, interval, API_KEY, API_SECRET, symbol_logger, limit=200, cache=klines_cache)
            if df.empty:
                symbol_logger.warning(f"{NEON_YELLOW}No Kline data received. Retrying...{RESET}")
                time.sleep(CFG.get("retry_delay", 5))
                continue

            # Debounced order-book fetch
            now = time.time()
            if now - last_ob_ts >= CFG.get("order_book_debounce_s", 10):
                order_book_cached = fetch_order_book(symbol, API_KEY, API_SECRET, symbol_logger, limit=CFG.get("order_book_depth_to_check", 10))
                last_ob_ts = now
            else:
                symbol_logger.debug(f"{NEON_YELLOW}Order book fetch debounced. Next in ~{CFG.get('order_book_debounce_s', 10) - (now - last_ob_ts):.1f}s{RESET}")

            analyzer = TradingAnalyzer(df, CFG, symbol_logger, symbol, interval)
            ts = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")

            analyzer.analyze(Decimal(str(price)), ts, order_book_cached)

            sig = analyzer.generate_trading_signal(Decimal(str(price)))
            current_time = time.time()

            if sig.signal and (current_time - last_signal_ts >= CFG.get("signal_cooldown_s", 60)):
                symbol_logger.info(f"\n{NEON_PURPLE}--- TRADING SIGNAL TRIGGERED ---{RESET}")
                symbol_logger.info(f"{NEON_BLUE}Signal:{RESET} {sig.signal.upper()} (Confidence: {sig.confidence:.2f})")
                symbol_logger.info(f"{NEON_BLUE}Conditions Met:{RESET} {', '.join(sig.conditions) if sig.conditions else 'None'}")
                if sig.levels:
                    symbol_logger.info(f"{NEON_GREEN}Stop Loss:{RESET} {sig.levels.get('stop_loss'):.5f}  {NEON_GREEN}Take Profit:{RESET} {sig.levels.get('take_profit'):.5f}")
                symbol_logger.info(f"{NEON_YELLOW}--- Placeholder: Order routing would be here ---{RESET}")
                last_signal_ts = current_time

            time.sleep(CFG.get("analysis_interval", 30))

    except KeyboardInterrupt:
        symbol_logger.info(f"{NEON_YELLOW}User interrupted. Exiting...{RESET}")
    except Exception as e:
        symbol_logger.exception(f"{NEON_RED}Unhandled exception: {e}{RESET}")

if __name__ == "__main__":
    main()
