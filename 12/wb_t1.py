#  whalebot_enhanced.py
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
    # This keeps the load_config function cleaner
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
                "stochastic_oscillator": 0.3,
            },
        },
        "stoch_rsi_oversold_threshold": 20,
        "stoch_rsi_overbought_threshold": 80,
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
                merged[key].update(value)
            else:
                merged[key] = value
    except json.JSONDecodeError as e:
        LOGGER.error(
            f"{NEON_RED}Corrupt config file: {e}. Backing up and creating new default.{RESET}",
        )
        backup_fp = fp.with_suffix(f".bak_{int(time.time())}")
        try:
            fp.rename(backup_fp)
            fp.write_text(json.dumps(defaults, indent=4))
        except OSError as backup_err:
            LOGGER.error(
                f"{NEON_RED}Could not back up corrupt config: {backup_err}{RESET}",
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
        price_str = data["result"]["list"][0]["lastPrice"]
        return Decimal(price_str)
    except (KeyError, IndexError, TypeError):
        log.error(f"{NEON_RED}Could not parse price from API response: {data}{RESET}")
        return None


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
        return (100 - (100 / (1 + rs))).fillna(50)

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
        plus_dm = high.diff()
        minus_dm = low.diff().mul(-1)
        plus_dm[(plus_dm < 0) | (plus_dm <= minus_dm)] = 0
        minus_dm[(minus_dm < 0) | (minus_dm <= plus_dm)] = 0

        tr = Indicators.atr(high, low, close, window)
        atr_s = Indicators.ema(tr, span=window)
        plus_di = 100 * (Indicators.ema(plus_dm, span=window) / atr_s)
        minus_di = 100 * (Indicators.ema(minus_dm, span=window) / atr_s)
        dx = 100 * (
            abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
        ).fillna(0)
        adx_series = Indicators.ema(dx, span=window)
        return pd.DataFrame({"+DI": plus_di, "-DI": minus_di, "ADX": adx_series})


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
        self.df = df
        self.cfg = cfg
        self.log = log
        self.symbol = symbol
        self.interval = interval
        self.atr_value: float = 0.0
        self.indicator_values: dict[str, Any] = {}
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

    def _select_weight_set(self) -> dict[str, float]:
        """Selects indicator weights based on market volatility (ATR)."""
        vol_mode = (
            "high_volatility"
            if self.atr_value > self.cfg["atr_change_threshold"]
            else "low_volatility"
        )
        self.log.info(
            f"Market Volatility: {NEON_YELLOW}{vol_mode.replace('_', ' ').upper()}{RESET} (ATR: {self.atr_value:.5f})",
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

    def analyze(self, price: Decimal, ts: str, order_book: dict[str, Any] | None):
        """Performs a full analysis and logs a detailed summary."""
        rsi_val = Indicators.rsi(
            self.df.close, self.cfg["indicator_periods"]["rsi"],
        ).iloc[-1]
        ema_score = self._calculate_ema_alignment()
        vol_spike = self._calculate_volume_confirmation()
        adx_df = Indicators.adx(
            self.df.high,
            self.df.low,
            self.df.close,
            self.cfg["indicator_periods"]["adx"],
        )
        adx_val = adx_df["ADX"].iloc[-1]

        # Store for signal generation
        self.indicator_values["rsi"] = rsi_val
        self.indicator_values["ema_alignment"] = ema_score
        self.indicator_values["volume_confirmation"] = vol_spike
        self.indicator_values["adx"] = adx_val

        # --- Logging ---
        trend_status = (
            f"{NEON_GREEN}Trending{RESET}"
            if adx_val > 25
            else f"{NEON_YELLOW}Ranging{RESET}"
        )
        rsi_status = (
            f"{NEON_RED}Overbought{RESET}"
            if rsi_val > 70
            else f"{NEON_GREEN}Oversold{RESET}"
            if rsi_val < 30
            else f"{NEON_YELLOW}Neutral{RESET}"
        )

        self.log.info(
            f"\n"
            f"{'─' * 20} ANALYSIS FOR {self.symbol} ({self.interval}) {'─' * 20}\n"
            f" Timestamp: {ts} │ Current Price: {NEON_BLUE}{price:.5f}{RESET}\n"
            f" ATR({self.cfg['atr_period']}): {self.atr_value:.5f} │ ADX({self.cfg['indicator_periods']['adx']}): {adx_val:.2f} ({trend_status})\n"
            f" RSI({self.cfg['indicator_periods']['rsi']}): {rsi_val:.2f} ({rsi_status}) │ EMA Align: {ema_score:+.1f} │ Vol Spike: {vol_spike}\n",
        )
        if order_book and "bids" in order_book and "asks" in order_book:
            bid0_price, bid0_qty = order_book["bids"][0]
            ask0_price, ask0_qty = order_book["asks"][0]
            self.log.info(
                f" Order Book: Bid {bid0_qty} @ {bid0_price} | Ask {ask0_qty} @ {ask0_price}",
            )
        self.log.info("─" * (42 + len(self.symbol) + len(self.interval)))

    def generate_trading_signal(self, price: Decimal) -> TradeSignal:
        """Generates a trading signal based on a weighted scoring system."""
        score = Decimal("0.0")
        conditions: list[str] = []

        # --- Bullish Conditions ---
        if self.indicator_values.get("rsi", 50) < 30:
            score += Decimal(str(self.weights.get("rsi", 0)))
            conditions.append("RSI Oversold")
        if self.indicator_values.get("ema_alignment", 0) > 0:
            score += Decimal(str(self.weights.get("ema_alignment", 0))) * Decimal(
                str(abs(self.indicator_values["ema_alignment"])),
            )
            conditions.append("Bullish EMA Alignment")
        if self.indicator_values.get("volume_confirmation", False):
            score += Decimal(str(self.weights.get("volume_confirmation", 0)))
            conditions.append("Volume Confirmation")

        # --- Bearish Conditions (example) ---
        bearish_score = Decimal("0.0")
        bearish_conditions: list[str] = []
        if self.indicator_values.get("rsi", 50) > 70:
            bearish_score += Decimal(str(self.weights.get("rsi", 0)))
            bearish_conditions.append("RSI Overbought")
        if self.indicator_values.get("ema_alignment", 0) < 0:
            bearish_score += Decimal(
                str(self.weights.get("ema_alignment", 0)),
            ) * Decimal(str(abs(self.indicator_values["ema_alignment"])))
            bearish_conditions.append("Bearish EMA Alignment")

        # --- Final Signal Decision ---
        signal: str | None = None
        final_score = 0.0
        final_conditions: list[str] = []

        if score >= Decimal(str(self.cfg["signal_score_threshold"])):
            signal = "buy"
            final_score = float(score)
            final_conditions = conditions
        elif bearish_score >= Decimal(str(self.cfg["signal_score_threshold"])):
            signal = "sell"
            final_score = float(bearish_score)
            final_conditions = bearish_conditions

        # Calculate SL/TP levels if a signal is generated
        levels: dict[str, Decimal] = {}
        if signal and self.atr_value > 0:
            atr_d = Decimal(str(self.atr_value))
            sl_mult = Decimal(str(self.cfg["stop_loss_multiple"]))
            tp_mult = Decimal(str(self.cfg["take_profit_multiple"]))
            precision = Decimal("0.00001")
            if signal == "buy":
                levels["stop_loss"] = (price - atr_d * sl_mult).quantize(precision)
                levels["take_profit"] = (price + atr_d * tp_mult).quantize(precision)
            elif signal == "sell":
                levels["stop_loss"] = (price + atr_d * sl_mult).quantize(precision)
                levels["take_profit"] = (price - atr_d * tp_mult).quantize(precision)

        return TradeSignal(signal, final_score, final_conditions, levels)


# ----------------------------------------------------------------------------
# 8. MAIN APPLICATION LOOP
# ----------------------------------------------------------------------------
def main() -> None:
    """Main function to initialize and run the trading bot loop."""
    if not API_KEY or not API_SECRET:
        LOGGER.critical(
            f"{NEON_RED}BYBIT_API_KEY and BYBIT_API_SECRET must be set in .env file.{RESET}",
        )
        return

    symbol = (
        input(f"{NEON_BLUE}Enter symbol (default BTCUSDT): {RESET}") or "BTCUSDT"
    ).upper()
    interval = (
        input(
            f"{NEON_BLUE}Enter interval {VALID_INTERVALS} (default {CFG['interval']}): {RESET}",
        )
        or CFG["interval"]
    )
    if interval not in VALID_INTERVALS:
        LOGGER.warning(
            f"{NEON_YELLOW}Invalid interval. Using default: {CFG['interval']}{RESET}",
        )
        interval = CFG["interval"]

    symbol_logger = setup_logger(symbol)
    symbol_logger.info(
        f"🚀 WhaleBot Enhanced starting for {NEON_PURPLE}{symbol}{RESET} on interval {NEON_PURPLE}{interval}{RESET}",
    )

    kline_cache: dict[str, tuple[datetime, pd.DataFrame]] = {}
    last_signal_time = 0.0
    last_ob_fetch_time = 0.0
    order_book: dict[str, Any] | None = None

    try:
        while True:
            price = fetch_current_price(symbol, symbol_logger)
            if price is None:
                time.sleep(CFG["retry_delay"])
                continue

            df = fetch_klines(symbol, interval, 200, symbol_logger, kline_cache)
            if df.empty:
                time.sleep(CFG["retry_delay"])
                continue

            current_time = time.time()
            if current_time - last_ob_fetch_time >= CFG["order_book_debounce_s"]:
                order_book = fetch_order_book(
                    symbol, CFG["order_book_depth_to_check"], symbol_logger,
                )
                last_ob_fetch_time = current_time

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
                    f"   Conditions Met: {'; '.join(trade_signal.conditions)}\n",
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


if __name__ == "__main__":
    main()
