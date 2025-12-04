"""Whalebot: An automated cryptocurrency trading bot for Bybit.

This upgraded version refactors the original script to use asyncio for
non-blocking I/O, improving performance and responsiveness. It also
enhances the WebSocket management, error handling, and overall code
structure for better maintainability and reliability.
"""

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import os
import random
import sys
import time
import traceback
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, InvalidOperation, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Generic, Literal, TypeVar

import aiohttp
import numpy as np
import pandas as pd
import pandas_ta as ta
from colorama import Fore, Style, init

# --- Guarded Imports ---
# This ensures the script can run even if optional libraries aren't installed.
try:
    import pybit
    import pybit.exceptions
    from pybit.unified_trading import HTTP, WebSocket

    PYBIT_AVAILABLE = True
except ImportError:
    PYBIT_AVAILABLE = False

    # Define dummy classes to prevent crashes
    class HTTP:
        def __init__(self, **kwargs):
            pass

        def __getattr__(self, name):
            return self._dummy_method

        def _dummy_method(self, **kwargs):
            logging.getLogger(__name__).warning(
                "Pybit not available. Using dummy client.",
            )

    class WebSocket:
        def __init__(self, **kwargs):
            pass

        def __getattr__(self, name):
            return self._dummy_method

        def _dummy_method(self, *args, **kwargs):
            logging.getLogger(__name__).warning(
                "Pybit not available. Using dummy WebSocket.",
            )

    class WebSocketConnectionClosedException(Exception):
        pass


try:
    import indicators
except ImportError:

    class indicators:
        @staticmethod
        def __getattr__(name):
            def dummy_indicator(*args, **kwargs):
                logging.getLogger(__name__).error(
                    f"indicators.py not found. Using dummy function for '{name}'.",
                )
                return (
                    pd.Series(np.nan)
                    if "calculate" in name
                    or name in ["calculate_dema", "calculate_roc", "calculate_vwap"]
                    else {"Market_Structure_Trend": "UNKNOWN"}
                )

            return dummy_indicator

    logging.getLogger(__name__).error(
        "indicators.py not found. Please ensure it's in the same directory or accessible via PYTHONPATH.",
    )

try:
    from alert_system import AlertSystem
except ImportError:

    class AlertSystem:
        def __init__(self, logger):
            self.logger = logger

        def send_alert(self, message, level="INFO"):
            self.logger.log(logging.INFO, f"ALERT (Dummy): {message}")

    logging.getLogger(__name__).error(
        "alert_system.py not found. Using dummy alert system.",
    )


# --- Initialization ---
getcontext().prec = 28
init(autoreset=True)

# --- Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
CONFIG_FILE = "config.json"
STATE_FILE = "bot_state.json"
PAUSE_FILE = "pause.json"
LOG_DIRECTORY = "bot_logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)
TIMEZONE = UTC
MAX_API_RETRIES = 5
RETRY_DELAY_SECONDS = 7
REQUEST_TIMEOUT = 20
LOOP_DELAY_SECONDS = 15

# Indicator specific constants
MIN_DATA_POINTS_TR = 2
MIN_DATA_POINTS_SMOOTHER = 2
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR = 2
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20
MIN_CANDLESTICK_PATTERNS_BARS = 2

# WebSocket constants
WS_RECONNECT_DELAY_SECONDS = 5
API_CALL_RETRY_DELAY_SECONDS = 3
EXECUTION_POLL_INTERVAL_MS = 1000
HEARTBEAT_INTERVAL_MS = 5000

# --- Global Logger Instance ---
global_logger = logging.getLogger("whalebot")

# --- Color Palette ---
NEON_GREEN, NEON_BLUE, NEON_PURPLE, NEON_YELLOW, NEON_RED, NEON_CYAN = (
    Fore.LIGHTGREEN_EX,
    Fore.CYAN,
    Fore.MAGENTA,
    Fore.YELLOW,
    Fore.LIGHTRED_EX,
    Fore.CYAN,
)
RESET = Style.RESET_ALL

# Indicator Colors (mapping for display)
INDICATOR_COLORS = {
    "SMA_10": NEON_BLUE,
    "SMA_Long": Fore.BLUE,
    "EMA_Short": NEON_PURPLE,
    "EMA_Long": Fore.MAGENTA,
    "ATR": NEON_YELLOW,
    "RSI": NEON_GREEN,
    "StochRSI_K": NEON_CYAN,
    "StochRSI_D": Fore.LIGHTCYAN_EX,
    "BB_Upper": NEON_RED,
    "BB_Middle": Fore.WHITE,
    "BB_Lower": NEON_RED,
    "CCI": NEON_GREEN,
    "WR": NEON_RED,
    "MFI": NEON_GREEN,
    "OBV": Fore.BLUE,
    "OBV_EMA": NEON_BLUE,
    "CMF": NEON_PURPLE,
    "Tenkan_Sen": NEON_CYAN,
    "Kijun_Sen": Fore.LIGHTCYAN_EX,
    "Senkou_Span_A": NEON_GREEN,
    "Senkou_Span_B": NEON_RED,
    "Chikou_Span": NEON_YELLOW,
    "PSAR_Val": NEON_PURPLE,
    "PSAR_Dir": Fore.LIGHTMAGENTA_EX,
    "VWAP": Fore.WHITE,
    "ST_Fast_Dir": Fore.BLUE,
    "ST_Fast_Val": NEON_BLUE,
    "ST_Slow_Dir": NEON_PURPLE,
    "ST_Slow_Val": Fore.LIGHTMAGENTA_EX,
    "MACD_Line": NEON_GREEN,
    "MACD_Signal": Fore.LIGHTGREEN_EX,
    "MACD_Hist": NEON_YELLOW,
    "ADX": NEON_CYAN,
    "PlusDI": Fore.LIGHTCYAN_EX,
    "MinusDI": NEON_RED,
    "Volatility_Index": NEON_YELLOW,
    "Volume_Delta": Fore.LIGHTCYAN_EX,
    "VWMA": Fore.WHITE,
    "Kaufman_AMA": NEON_GREEN,
    "Relative_Volume": NEON_PURPLE,
    "Market_Structure_Trend": Fore.LIGHTCYAN_EX,
    "DEMA": Fore.BLUE,
    "Keltner_Upper": NEON_PURPLE,
    "Keltner_Middle": Fore.WHITE,
    "Keltner_Lower": NEON_PURPLE,
    "ROC": NEON_GREEN,
    "Pivot": Fore.WHITE,
    "R1": NEON_CYAN,
    "R2": Fore.LIGHTCYAN_EX,
    "S1": NEON_PURPLE,
    "S2": Fore.LIGHTMAGENTA_EX,
    "Candlestick_Pattern": Fore.LIGHTYELLOW_EX,
    "Support_Level": NEON_CYAN,
    "Resistance_Level": NEON_RED,
}


# --- Helper Functions for Precision and Safety ---
def round_qty(qty: Decimal, qty_step: Decimal) -> Decimal:
    if qty_step is None or qty_step.is_zero():
        return qty.quantize(Decimal("1e-6"), rounding=ROUND_DOWN)
    return (qty // qty_step) * qty_step


def round_price(price: Decimal, price_precision: int) -> Decimal:
    price_precision = max(price_precision, 0)
    return price.quantize(Decimal(f"1e-{price_precision}"), rounding=ROUND_DOWN)


def _safe_divide_decimal(
    numerator: Decimal,
    denominator: Decimal,
    default: Decimal = Decimal("0"),
) -> Decimal:
    try:
        if denominator.is_zero() or denominator.is_nan() or numerator.is_nan():
            return default
        return numerator / denominator
    except InvalidOperation:
        return default


# --- Configuration Management ---
def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    default_config = {
        "symbol": "BTCUSDT",
        "interval": "15",
        "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50,
        "signal_score_threshold": 2.0,
        "cooldown_sec": 60,
        "hysteresis_ratio": 0.85,
        "volume_confirmation_multiplier": 1.5,
        "trade_management": {
            "enabled": True,
            "account_balance": 1000.0,
            "risk_per_trade_percent": 1.0,
            "stop_loss_atr_multiple": 1.5,
            "take_profit_atr_multiple": 2.0,
            "trailing_stop_atr_multiple": 0.5,
            "max_open_positions": 1,
            "order_precision": 5,
            "price_precision": 3,
            "slippage_percent": 0.001,
            "trading_fee_percent": 0.0005,
        },
        "risk_guardrails": {
            "enabled": True,
            "max_day_loss_pct": 3.0,
            "max_drawdown_pct": 8.0,
            "cooldown_after_kill_min": 120,
            "spread_filter_bps": 5.0,
            "ev_filter_enabled": True,
            "consecutive_losses_limit": 5,
            "api_error_limit_per_hour": 10,
            "ws_disconnect_limit_per_hour": 5,
        },
        "session_filter": {
            "enabled": False,
            "utc_allowed": [["00:00", "08:00"], ["13:00", "20:00"]],
        },
        "pyramiding": {
            "enabled": False,
            "max_adds": 2,
            "step_atr": 0.7,
            "size_pct_of_initial": 0.5,
        },
        "mtf_analysis": {
            "enabled": True,
            "higher_timeframes": ["60", "240"],
            "trend_indicators": ["ema", "ehlers_supertrend"],
            "trend_period": 50,
            "mtf_request_delay_seconds": 0.5,
        },
        "ml_enhancement": {"enabled": False},
        "execution": {
            "use_pybit": False,
            "testnet": False,
            "account_type": "UNIFIED",
            "category": "linear",
            "position_mode": "ONE_WAY",
            "tpsl_mode": "Partial",
            "buy_leverage": "3",
            "sell_leverage": "3",
            "tp_trigger_by": "LastPrice",
            "sl_trigger_by": "LastPrice",
            "default_time_in_force": "GoodTillCancel",
            "reduce_only_default": False,
            "post_only_default": False,
            "position_idx_overrides": {"ONE_WAY": 0, "HEDGE_BUY": 1, "HEDGE_SELL": 2},
            "proxies": {"enabled": False, "http": "", "https": ""},
            "tp_scheme": {
                "mode": "atr_multiples",
                "targets": [
                    {
                        "name": "TP1",
                        "atr_multiple": 1.0,
                        "size_pct": 0.40,
                        "order_type": "Limit",
                        "tif": "PostOnly",
                        "post_only": True,
                    },
                    {
                        "name": "TP2",
                        "atr_multiple": 1.5,
                        "size_pct": 0.40,
                        "order_type": "Limit",
                        "tif": "IOC",
                        "post_only": False,
                    },
                    {
                        "name": "TP3",
                        "atr_multiple": 2.0,
                        "size_pct": 0.20,
                        "order_type": "Limit",
                        "tif": "GoodTillCancel",
                        "post_only": False,
                    },
                ],
            },
            "sl_scheme": {
                "type": "atr_multiple",
                "atr_multiple": 1.5,
                "percent": 1.0,
                "use_conditional_stop": True,
                "stop_order_type": "Market",
            },
            "breakeven_after_tp1": {
                "enabled": True,
                "offset_type": "atr",
                "offset_value": 0.10,
                "lock_in_min_percent": 0,
                "sl_trigger_by": "LastPrice",
            },
            "live_sync": {
                "enabled": True,
                "poll_ms": EXECUTION_POLL_INTERVAL_MS,
                "max_exec_fetch": 200,
                "only_track_linked": True,
                "heartbeat": {"enabled": True, "interval_ms": HEARTBEAT_INTERVAL_MS},
            },
        },
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
            "kama_period": 10,
            "kama_fast_period": 2,
            "kama_slow_period": 30,
            "relative_volume_period": 20,
            "relative_volume_threshold": 1.5,
            "market_structure_lookback_period": 20,
            "dema_period": 14,
            "keltner_period": 20,
            "keltner_atr_multiplier": 2.0,
            "roc_period": 12,
            "roc_oversold": -5.0,
            "roc_overbought": 5.0,
        },
        "indicators": {
            "atr": True,
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
            "kaufman_ama": True,
            "relative_volume": True,
            "market_structure": True,
            "dema": True,
            "keltner_channels": True,
            "roc": True,
            "candlestick_patterns": True,
            "fibonacci_pivot_points": True,
        },
        "weight_sets": {
            "default_scalping": {
                "ema_alignment": 0.22,
                "sma_trend_filter": 0.28,
                "momentum_rsi_stoch_cci_wr_mfi": 0.18,
                "volume_confirmation": 0.12,
                "bollinger_bands": 0.22,
                "vwap": 0.22,
                "cci": 0.08,
                "wr": 0.08,
                "psar": 0.22,
                "sma_10": 0.07,
                "mfi": 0.12,
                "orderbook_imbalance": 0.07,
                "fibonacci_levels": 0.10,
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
                "kaufman_ama_cross": 0.20,
                "relative_volume_confirmation": 0.10,
                "market_structure_confluence": 0.25,
                "dema_crossover": 0.18,
                "keltner_breakout": 0.20,
                "roc_signal": 0.12,
                "candlestick_confirmation": 0.15,
                "fibonacci_pivot_points_confluence": 0.20,
            },
        },
    }
    if not Path(filepath).exists():
        try:
            with Path(filepath).open("w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            logger.warning(
                f"{NEON_YELLOW}Configuration file not found. Created default config at {filepath}{RESET}",
            )
            return default_config
        except OSError as e:
            logger.error(f"{NEON_RED}Error creating default config file: {e}{RESET}")
            return default_config
    try:
        with Path(filepath).open("r", encoding="utf-8") as f:
            config = json.load(f)
        _ensure_config_keys(config, default_config)
        with Path(filepath).open("w", encoding="utf-8") as f_write:
            json.dump(config, f_write, indent=4)
        return config
    except (OSError, FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(
            f"{NEON_RED}Error loading config file '{filepath}': {e}. Using default configuration.{RESET}",
        )
        return default_config


def _ensure_config_keys(config: dict[str, Any], default_config: dict[str, Any]) -> None:
    for key, default_value in default_config.items():
        if key not in config:
            config[key] = default_value
        elif isinstance(default_value, dict) and isinstance(config.get(key), dict):
            _ensure_config_keys(config[key], default_value)


# --- Logging Setup ---
class SensitiveFormatter(logging.Formatter):
    SENSITIVE_WORDS: ClassVar[list[str]] = ["API_KEY", "API_SECRET"]

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
    logger = logging.getLogger(log_name)
    if not logger.handlers:
        logger.setLevel(level)
        logger.propagate = False
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            SensitiveFormatter(
                f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}",
            ),
        )
        logger.addHandler(console_handler)
        log_file = Path(LOG_DIRECTORY) / f"{log_name}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        )
        file_handler.setFormatter(
            SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
        )
        logger.addHandler(file_handler)
    return logger


# --- Asynchronous API Interaction ---
async def bybit_request_async(
    session: aiohttp.ClientSession,
    method: Literal["GET", "POST"],
    endpoint: str,
    params: dict | None = None,
    signed: bool = False,
    logger: logging.Logger | None = None,
) -> dict | None:
    if logger is None:
        logger = global_logger
    base_url = "https://api.bybit.com"
    url = f"{base_url}{endpoint}"
    headers = {"Content-Type": "application/json"}

    # Retry logic
    for attempt in range(MAX_API_RETRIES):
        try:
            if signed:
                if not API_KEY or not API_SECRET:
                    logger.error(
                        f"{NEON_RED}API_KEY or API_SECRET not set for signed request.{RESET}",
                    )
                    return None
                timestamp = str(int(time.time() * 1000))
                recv_window = "20000"
                if method == "GET":
                    query_string = urllib.parse.urlencode(params) if params else ""
                    param_str = timestamp + API_KEY + recv_window + query_string
                    signature = hmac.new(
                        API_SECRET.encode(),
                        param_str.encode(),
                        hashlib.sha256,
                    ).hexdigest()
                    headers.update(
                        {
                            "X-BAPI-API-KEY": API_KEY,
                            "X-BAPI-TIMESTAMP": timestamp,
                            "X-BAPI-SIGN": signature,
                            "X-BAPI-RECV-WINDOW": recv_window,
                        },
                    )
                    async with session.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=REQUEST_TIMEOUT,
                    ) as response:
                        response.raise_for_status()
                        data = await response.json()
                else:  # POST
                    json_params = json.dumps(params) if params else ""
                    param_str = timestamp + API_KEY + recv_window + json_params
                    signature = hmac.new(
                        API_SECRET.encode(),
                        param_str.encode(),
                        hashlib.sha256,
                    ).hexdigest()
                    headers.update(
                        {
                            "X-BAPI-API-KEY": API_KEY,
                            "X-BAPI-TIMESTAMP": timestamp,
                            "X-BAPI-SIGN": signature,
                            "X-BAPI-RECV-WINDOW": recv_window,
                        },
                    )
                    async with session.post(
                        url,
                        json=params,
                        headers=headers,
                        timeout=REQUEST_TIMEOUT,
                    ) as response:
                        response.raise_for_status()
                        data = await response.json()
            else:  # Public request (GET)
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

            if data.get("retCode") != 0:
                logger.error(
                    f"{NEON_RED}Bybit API Error: {data.get('retMsg')} (Code: {data.get('retCode')}){RESET}",
                )
                return None
            return data

        except aiohttp.ClientResponseError as e:
            logger.error(
                f"{NEON_RED}HTTP Error {e.status}: {e.message}. Retrying... ({attempt + 1}/{MAX_API_RETRIES}){RESET}",
            )
            await asyncio.sleep(RETRY_DELAY_SECONDS)
        except aiohttp.ClientConnectionError as e:
            logger.error(
                f"{NEON_RED}Connection Error: {e}. Retrying... ({attempt + 1}/{MAX_API_RETRIES}){RESET}",
            )
            await asyncio.sleep(RETRY_DELAY_SECONDS)
        except aiohttp.ClientError as e:
            logger.error(
                f"{NEON_RED}Request Exception: {e}. Retrying... ({attempt + 1}/{MAX_API_RETRIES}){RESET}",
            )
            await asyncio.sleep(RETRY_DELAY_SECONDS)
        except json.JSONDecodeError:
            logger.error(
                f"{NEON_RED}Failed to decode JSON response. Retrying... ({attempt + 1}/{MAX_API_RETRIES}){RESET}",
            )
            await asyncio.sleep(RETRY_DELAY_SECONDS)
        except Exception as e:
            logger.error(
                f"{NEON_RED}Unexpected error during API request: {e}. Retrying... ({attempt + 1}/{MAX_API_RETRIES}){RESET}",
                exc_info=True,
            )
            await asyncio.sleep(RETRY_DELAY_SECONDS)

    logger.error(
        f"{NEON_RED}Max API retries ({MAX_API_RETRIES}) exceeded. Trading halted.{RESET}",
    )
    return None


# --- Data Managers for WebSocket Data ---
KT = TypeVar("KT")
VT = TypeVar("VT")


@dataclass(slots=True)
class PriceLevel:
    price: float
    quantity: float
    timestamp: int
    order_count: int = 1

    def __lt__(self, other: "PriceLevel") -> bool:
        return self.price < other.price

    def __eq__(self, other: "PriceLevel") -> bool:
        return abs(self.price - other.price) < 1e-8


class OptimizedSkipList(Generic[KT, VT]):
    class Node(Generic[KT, VT]):
        def __init__(self, key: KT, value: VT, level: int):
            self.key = key
            self.value = value
            self.forward: list[OptimizedSkipList.Node | None] = [None] * (level + 1)
            self.level = level

    def __init__(self, max_level: int = 16, p: float = 0.5):
        self.max_level = max_level
        self.p = p
        self.level = 0
        self.header = self.Node(None, None, max_level)
        self._size = 0

    def _random_level(self) -> int:
        level = 1
        while random.random() < self.p and level < self.max_level:
            level += 1
        return level

    def insert(self, key: KT, value: VT) -> None:
        update = [None] * (self.max_level + 1)
        current = self.header
        for i in range(self.level, -1, -1):
            while (
                current.forward[i]
                and current.forward[i].key is not None
                and current.forward[i].key < key
            ):
                current = current.forward[i]
            update[i] = current
        current = current.forward[0]
        if current and current.key == key:
            current.value = value
            return
        new_level = self._random_level()
        if new_level > self.level:
            for i in range(self.level + 1, new_level + 1):
                update[i] = self.header
            self.level = new_level
        new_node = self.Node(key, value, new_level)
        for i in range(new_level + 1):
            new_node.forward[i] = update[i].forward[i]
            update[i].forward[i] = new_node
        self._size += 1

    def delete(self, key: KT) -> bool:
        update = [None] * (self.max_level + 1)
        current = self.header
        for i in range(self.level, -1, -1):
            while (
                current.forward[i]
                and current.forward[i].key is not None
                and current.forward[i].key < key
            ):
                current = current.forward[i]
            update[i] = current
        current = current.forward[0]
        if not current or current.key != key:
            return False
        for i in range(self.level + 1):
            if update[i].forward[i] != current:
                break
            update[i].forward[i] = current.forward[i]
        while self.level > 0 and not self.header.forward[self.level]:
            self.level -= 1
        self._size -= 1
        return True

    def get_sorted_items(self, reverse: bool = False) -> list[tuple[KT, VT]]:
        items = []
        current = self.header.forward[0]
        while current:
            if current.key is not None:
                items.append((current.key, current.value))
            current = current.forward[0]
        return list(reversed(items)) if reverse else items

    def peek_top(self, reverse: bool = False) -> VT | None:
        items = self.get_sorted_items(reverse=reverse)
        return items[0][1] if items else None

    @property
    def size(self) -> int:
        return self._size


class AdvancedOrderbookManager:
    def __init__(self, symbol: str, logger: logging.Logger, use_skip_list: bool = True):
        self.symbol = symbol
        self.logger = logger
        self.use_skip_list = use_skip_list
        self._lock = asyncio.Lock()
        if use_skip_list:
            self.bids_ds = OptimizedSkipList[float, PriceLevel]()
            self.asks_ds = OptimizedSkipList[float, PriceLevel]()
        else:
            self.bids_ds = []
            self.asks_ds = []
        self.last_update_id: int = 0

    @contextlib.asynccontextmanager
    async def _lock_context(self):
        async with self._lock:
            yield

    async def _validate_price_quantity(self, price: float, quantity: float) -> bool:
        if not (isinstance(price, (int, float)) and isinstance(quantity, (int, float))):
            self.logger.error(
                f"Invalid type for price or quantity for {self.symbol}. Price: {type(price)}, Qty: {type(quantity)}",
            )
            return False
        if price < 0 or quantity < 0:
            self.logger.error(
                f"Negative price or quantity detected for {self.symbol}: price={price}, quantity={quantity}",
            )
            return False
        return True

    async def update_snapshot(self, data: dict[str, Any]) -> None:
        async with self._lock_context():
            if (
                not isinstance(data, dict)
                or "b" not in data
                or "a" not in data
                or "u" not in data
            ):
                self.logger.error(
                    f"Invalid snapshot data format for {self.symbol}: {data}",
                )
                return
            if self.use_skip_list:
                self.bids_ds = OptimizedSkipList[float, PriceLevel]()
                self.asks_ds = OptimizedSkipList[float, PriceLevel]()
            else:
                self.bids_ds = []
                self.asks_ds = []
            for price_str, qty_str in data.get("b", []):
                try:
                    price = float(price_str)
                    quantity = float(qty_str)
                    if (
                        await self._validate_price_quantity(price, quantity)
                        and quantity > 0
                    ):
                        level = PriceLevel(price, quantity, int(time.time() * 1000))
                        if self.use_skip_list:
                            self.bids_ds.insert(price, level)
                        else:
                            self.bids_ds.append(level)
                except (ValueError, TypeError) as e:
                    self.logger.error(
                        f"Failed to parse bid in snapshot for {self.symbol}: {price_str}/{qty_str}, error={e}",
                    )
            for price_str, qty_str in data.get("a", []):
                try:
                    price = float(price_str)
                    quantity = float(qty_str)
                    if (
                        await self._validate_price_quantity(price, quantity)
                        and quantity > 0
                    ):
                        level = PriceLevel(price, quantity, int(time.time() * 1000))
                        if self.use_skip_list:
                            self.asks_ds.insert(price, level)
                        else:
                            self.asks_ds.append(level)
                except (ValueError, TypeError) as e:
                    self.logger.error(
                        f"Failed to parse ask in snapshot for {self.symbol}: {price_str}/{qty_str}, error={e}",
                    )
            self.last_update_id = data.get("u", 0)
            if not self.use_skip_list:
                self.bids_ds.sort(key=lambda x: x.price, reverse=True)
                self.asks_ds.sort(key=lambda x: x.price)
            self.logger.info(
                f"Orderbook {self.symbol} snapshot updated. Last Update ID: {self.last_update_id}",
            )

    async def update_delta(self, data: dict[str, Any]) -> None:
        async with self._lock_context():
            if (
                not isinstance(data, dict)
                or not ("b" in data or "a" in data)
                or "u" not in data
            ):
                self.logger.error(
                    f"Invalid delta data format for {self.symbol}: {data}",
                )
                return
            current_update_id = data.get("u", 0)
            if current_update_id <= self.last_update_id:
                self.logger.debug(
                    f"Outdated OB update for {self.symbol}: current={current_update_id}, last={self.last_update_id}. Skipping.",
                )
                return
            for price_str, qty_str in data.get("b", []):
                try:
                    price = float(price_str)
                    quantity = float(qty_str)
                    if not await self._validate_price_quantity(price, quantity):
                        continue
                    if self.use_skip_list:
                        if quantity == 0.0:
                            self.bids_ds.delete(price)
                        else:
                            self.bids_ds.insert(
                                price,
                                PriceLevel(price, quantity, int(time.time() * 1000)),
                            )
                    else:
                        levels = [
                            lvl for lvl in self.bids_ds if abs(lvl.price - price) > 1e-8
                        ]
                        if quantity > 0:
                            levels.append(
                                PriceLevel(price, quantity, int(time.time() * 1000)),
                            )
                        self.bids_ds = sorted(
                            levels,
                            key=lambda x: x.price,
                            reverse=True,
                        )
                except (ValueError, TypeError) as e:
                    self.logger.error(
                        f"Failed to parse bid delta for {self.symbol}: {price_str}/{qty_str}, error={e}",
                    )
            for price_str, qty_str in data.get("a", []):
                try:
                    price = float(price_str)
                    quantity = float(qty_str)
                    if not await self._validate_price_quantity(price, quantity):
                        continue
                    if self.use_skip_list:
                        if quantity == 0.0:
                            self.asks_ds.delete(price)
                        else:
                            self.asks_ds.insert(
                                price,
                                PriceLevel(price, quantity, int(time.time() * 1000)),
                            )
                    else:
                        levels = [
                            lvl for lvl in self.asks_ds if abs(lvl.price - price) > 1e-8
                        ]
                        if quantity > 0:
                            levels.append(
                                PriceLevel(price, quantity, int(time.time() * 1000)),
                            )
                        self.asks_ds = sorted(levels, key=lambda x: x.price)
                except (ValueError, TypeError) as e:
                    self.logger.error(
                        f"Failed to parse ask delta for {self.symbol}: {price_str}/{qty_str}, error={e}",
                    )
            self.last_update_id = current_update_id
            self.logger.debug(
                f"Orderbook {self.symbol} delta applied. Last Update ID: {self.last_update_id}",
            )

    async def get_best_bid_ask(self) -> tuple[float | None, float | None]:
        async with self._lock_context():
            best_bid = (
                self.bids_ds.peek_top(reverse=True)
                if self.use_skip_list
                else (self.bids_ds[0] if self.bids_ds else None)
            )
            best_ask = (
                self.asks_ds.peek_top(reverse=False)
                if self.use_skip_list
                else (self.asks_ds[0] if self.asks_ds else None)
            )
            best_bid_price = best_bid.price if best_bid else None
            best_ask_price = best_ask.price if best_ask else None
            return best_bid_price, best_ask_price

    async def get_depth(self, depth: int) -> tuple[list[PriceLevel], list[PriceLevel]]:
        async with self._lock_context():
            bids = (
                self.bids_ds.get_sorted_items(reverse=True)[:depth]
                if self.use_skip_list
                else self.bids_ds[:depth]
            )
            asks = (
                self.asks_ds.get_sorted_items()[:depth]
                if self.use_skip_list
                else self.asks_ds[:depth]
            )
            if self.use_skip_list:
                bids = [item[1] for item in bids]
            if self.use_skip_list:
                asks = [item[1] for item in asks]
            return bids, asks


class KlineDataManager:
    def __init__(
        self,
        symbol: str,
        interval: str,
        max_klines: int,
        logger: logging.Logger,
    ):
        self.symbol = symbol
        self.interval = interval
        self.max_klines = max_klines
        self.logger = logger
        self._df: pd.DataFrame = pd.DataFrame()
        self._df_lock = asyncio.Lock()
        self._last_candle_open_time: datetime | None = None

    async def initialize(self, pybit_client: "PybitTradingClient"):
        df = await pybit_client.fetch_klines(
            self.symbol,
            self.interval,
            self.max_klines,
        )
        async with self._df_lock:
            if df is not None and not df.empty:
                self._df = df
                self._last_candle_open_time = self._df.index[-1]
                self.logger.info(
                    f"Initialized KlineDataManager for {self.symbol}@{self.interval} with {len(df)} klines.",
                )
            else:
                self.logger.warning(
                    f"Failed to initialize KlineDataManager for {self.symbol}@{self.interval}.",
                )

    async def get_df(self) -> pd.DataFrame:
        async with self._df_lock:
            return self._df.copy()

    async def update_from_ws(self, ws_kline_data: dict[str, Any]):
        new_candle = {
            "start_time": pd.to_datetime(
                ws_kline_data["timestamp"],
                unit="ms",
                utc=True,
            ).dt.tz_convert(TIMEZONE),
            "open": float(ws_kline_data["open"]),
            "high": float(ws_kline_data["high"]),
            "low": float(ws_kline_data["low"]),
            "close": float(ws_kline_data["close"]),
            "volume": float(ws_kline_data["volume"]),
            "turnover": float(ws_kline_data.get("turnover", 0.0)),
        }
        new_df_row = pd.DataFrame([new_candle]).set_index("start_time")
        async with self._df_lock:
            if (
                self._last_candle_open_time is None
                or new_df_row.index[0] > self._last_candle_open_time
            ):
                self._df = pd.concat([self._df, new_df_row])
                self._df = self._df.iloc[-self.max_klines :]
                self._last_candle_open_time = self._df.index[-1]
                self.logger.debug(
                    f"WS: Appended new candle {new_df_row.index[0]} to {self.symbol}@{self.interval} data.",
                )
            elif new_df_row.index[0] == self._last_candle_open_time:
                self._df.loc[new_df_row.index[0]] = new_df_row.iloc[0]
                self.logger.debug(
                    f"WS: Updated current candle {new_df_row.index[0]} for {self.symbol}@{self.interval} data.",
                )


# --- Pybit Trading Client ---
class PybitTradingClient:
    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.cfg, self.logger = config, logger
        self.enabled = (
            bool(config.get("execution", {}).get("use_pybit", False))
            and PYBIT_AVAILABLE
            and API_KEY
            and API_SECRET
        )
        self.category = config.get("execution", {}).get("category", "linear")
        self.testnet = bool(config.get("execution", {}).get("testnet", False))
        self.session: HTTP | None = None
        self.ws_manager: WebSocketManager | None = None
        self.stop_event = asyncio.Event()
        self.state_data: dict = {}
        self.api_error_count_hourly = 0
        self.ws_disconnect_count_hourly = 0
        self._last_hour_reset_api_errors = datetime.now(TIMEZONE)
        self._last_hour_reset_ws_disconnects = datetime.now(TIMEZONE)
        self.kline_data_managers: dict[str, KlineDataManager] = {}
        self.orderbook_data_manager: AdvancedOrderbookManager | None = None
        self.new_kline_event = asyncio.Event()

        if not self.enabled:
            if not PYBIT_AVAILABLE:
                self.logger.error(
                    f"{NEON_RED}Pybit library not found. Please install it: pip install pybit.{RESET}",
                )
            if not (API_KEY and API_SECRET):
                self.logger.error(
                    f"{NEON_RED}API keys (BYBIT_API_KEY, BYBIT_API_SECRET) not set in .env.{RESET}",
                )
            self.logger.info(
                f"{NEON_YELLOW}PyBit execution disabled in config or due to missing dependencies.{RESET}",
            )
            return

        proxies = {}
        proxy_conf = self.cfg.get("execution", {}).get("proxies", {})
        if proxy_conf.get("enabled", False):
            if proxy_conf.get("http"):
                proxies["http"] = proxy_conf["http"]
            if proxy_conf.get("https"):
                proxies["https"] = proxy_conf["https"]
            if proxies:
                self.logger.info(f"{NEON_BLUE}Using proxies: {proxies}.{RESET}")

        try:
            self.session = HTTP(
                api_key=API_KEY,
                api_secret=API_SECRET,
                testnet=self.testnet,
                timeout=REQUEST_TIMEOUT,
                proxies=proxies if proxies else None,
            )
            self.logger.info(
                f"{NEON_GREEN}PyBit HTTP client initialized. Testnet={self.testnet}{RESET}",
            )
            kline_key = f"{self.cfg['symbol']}_{self.cfg['interval']}"
            self.kline_data_managers[kline_key] = KlineDataManager(
                self.cfg["symbol"],
                self.cfg["interval"],
                1000,
                self.logger,
            )
            self.orderbook_data_manager = AdvancedOrderbookManager(
                self.cfg["symbol"],
                self.logger,
                use_skip_list=True,
            )
        except pybit.exceptions.FailedRequestError as e:
            self.enabled = False
            self.logger.critical(
                f"{NEON_RED}Failed to initialize PyBit client due to API error: {e}. Check credentials and network.{RESET}",
            )
        except Exception as e:
            self.enabled = False
            self.logger.critical(
                f"{NEON_RED}Failed to initialize PyBit client: {e}\n{traceback.format_exc()}{RESET}",
            )

    def _reset_hourly_error_counts(self):
        now = datetime.now(TIMEZONE)
        if (now - self._last_hour_reset_api_errors).total_seconds() >= 3600:
            self.api_error_count_hourly = 0
            self._last_hour_reset_api_errors = now
        if (now - self._last_hour_reset_ws_disconnects).total_seconds() >= 3600:
            self.ws_disconnect_count_hourly = 0
            self._last_hour_reset_ws_disconnects = now

    def _track_api_error(self, success: bool):
        self._reset_hourly_error_counts()
        if not success:
            self.api_error_count_hourly += 1

    def _track_ws_disconnect(self):
        self._reset_hourly_error_counts()
        self.ws_disconnect_count_hourly += 1

    def is_circuit_breaker_tripped(self) -> bool:
        self._reset_hourly_error_counts()
        api_limit = self.cfg["risk_guardrails"]["api_error_limit_per_hour"]
        ws_limit = self.cfg["risk_guardrails"]["ws_disconnect_limit_per_hour"]
        if self.api_error_count_hourly >= api_limit:
            self.logger.critical(
                f"{NEON_RED}CIRCUIT BREAKER: API error limit ({api_limit}) exceeded! Trading halted.{RESET}",
            )
            return True
        if self.ws_disconnect_count_hourly >= ws_limit:
            self.logger.critical(
                f"{NEON_RED}CIRCUIT BREAKER: WebSocket disconnect limit ({ws_limit}) exceeded! Trading halted.{RESET}",
            )
            return True
        return False

    def _log_api(self, action: str, resp: dict | None, log_level: str = "error"):
        if not resp:
            getattr(self.logger, log_level)(
                f"{NEON_RED}{action}: No response received.{RESET}",
            )
            self._track_api_error(False)
            return
        if resp.get("retCode") != 0:
            error_msg = resp.get("retMsg", "Unknown error")
            ret_code = resp.get("retCode", "N/A")
            getattr(self.logger, log_level)(
                f"{NEON_RED}{action}: Failed with code {ret_code} - {error_msg}{RESET}",
            )
            self._track_api_error(False)
        else:
            self._track_api_error(True)

    def _ok(self, resp: dict | None) -> bool:
        return bool(resp and resp.get("retCode") == 0)

    def _q(self, x: Any) -> str:
        return str(x)

    def _side_to_bybit(self, side: Literal["BUY", "SELL"]) -> Literal["Buy", "Sell"]:
        return "Buy" if side == "BUY" else "Sell"

    def _pos_idx(self, side: Literal["BUY", "SELL"]) -> Literal[0, 1, 2]:
        pmode = self.cfg["execution"].get("position_mode", "ONE_WAY").upper()
        overrides = self.cfg["execution"].get("position_idx_overrides", {})
        if pmode == "ONE_WAY":
            return int(overrides.get("ONE_WAY", 0))
        return int(overrides.get(f"HEDGE_{side}", 1 if side == "BUY" else 2))

    def _handle_403_error(self, e: Exception):
        if isinstance(e, pybit.exceptions.FailedRequestError) and e.status_code == 403:
            self.logger.critical(
                f"{NEON_RED}API Error 403 Forbidden: Check API key permissions and IP whitelist settings. Disabling client permanently.{RESET}",
            )
            self.enabled = False
            self.stop_event.set()

    async def set_leverage(self, symbol: str, buy: str, sell: str) -> bool:
        if not self.enabled or not self.session:
            return False
        try:
            resp = self.session.set_leverage(
                category=self.category,
                symbol=symbol,
                buyLeverage=self._q(buy),
                sellLeverage=self._q(sell),
            )
            self._log_api("set_leverage", resp, "debug")
            return self._ok(resp)
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(
                f"set_leverage failed for {symbol}: {e}\n{traceback.format_exc()}",
            )
            self._handle_403_error(e)
            return False

    async def get_positions(self, symbol: str | None = None) -> dict | None:
        if not self.enabled or not self.session:
            return None
        try:
            params = {"category": self.category}
            if symbol:
                params["symbol"] = symbol
            resp = self.session.get_positions(**params)
            self._log_api("get_positions", resp, "debug")
            return resp
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(f"get_positions exception: {e}\n{traceback.format_exc()}")
            self._handle_403_error(e)
            return None

    async def get_wallet_balance(self, coin: str = "USDT") -> dict | None:
        if not self.enabled or not self.session:
            return None
        try:
            resp = self.session.get_wallet_balance(
                accountType=self.cfg["execution"]["account_type"],
                coin=coin,
            )
            self._log_api("get_wallet_balance", resp, "debug")
            return resp
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(
                f"get_wallet_balance exception: {e}\n{traceback.format_exc()}",
            )
            self._handle_403_error(e)
            return None

    async def place_order(self, **kwargs) -> dict | None:
        if not self.enabled or not self.session:
            return None
        try:
            resp = self.session.place_order(category=self.category, **kwargs)
            self._log_api("place_order", resp)
            return resp
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(f"place_order exception: {e}\n{traceback.format_exc()}")
            self._handle_403_error(e)
            return None

    async def batch_place_orders(self, orders: list[dict]) -> dict | None:
        if not self.enabled or not self.session:
            return None
        if not orders:
            return {"retCode": 0, "retMsg": "No orders to place."}
        try:
            for order in orders:
                if "category" not in order:
                    order["category"] = self.category
            resp = self.session.batch_place_order(request=orders)
            self._log_api("batch_place_orders", resp)
            return resp
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(
                f"batch_place_orders exception: {e}\n{traceback.format_exc()}",
            )
            self._handle_403_error(e)
            return None

    async def cancel_order(
        self,
        symbol: str,
        order_id: str | None = None,
        order_link_id: str | None = None,
    ) -> dict | None:
        if not self.enabled or not self.session:
            return None
        try:
            params = {"category": self.category, "symbol": symbol}
            if order_id:
                params["orderId"] = order_id
            elif order_link_id:
                params["orderLinkId"] = order_link_id
            else:
                self.logger.warning(
                    "No orderId or orderLinkId provided for cancel_order.",
                )
                return None
            resp = self.session.cancel_order(**params)
            self._log_api("cancel_order", resp, "debug")
            return resp
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(
                f"cancel_order exception for {symbol}: {e}\n{traceback.format_exc()}",
            )
            self._handle_403_error(e)
            return None

    async def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        if not self.enabled or not self.session:
            return []
        try:
            params = {"category": self.category, "openOnly": 0}
            if symbol:
                params["symbol"] = symbol
            resp = self.session.get_open_orders(**params)
            self._log_api("get_open_orders", resp, "debug")
            if self._ok(resp) and resp.get("result", {}).get("list"):
                return resp["result"]["list"]
            return []
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(
                f"get_open_orders exception: {e}\n{traceback.format_exc()}",
            )
            self._handle_403_error(e)
            return []

    async def fetch_current_price(self, symbol: str) -> Decimal | None:
        if not self.enabled or not self.session:
            return None
        try:
            params = {"category": self.category, "symbol": symbol}
            response = self.session.get_tickers(**params)
            if self._ok(response) and response.get("result", {}).get("list"):
                return Decimal(response["result"]["list"][0]["lastPrice"])
            self.logger.warning(
                f"Could not fetch current price for {symbol}. Response: {response}",
            )
            return None
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(
                f"fetch_current_price exception for {symbol}: {e}\n{traceback.format_exc()}",
            )
            self._handle_403_error(e)
            return None

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> pd.DataFrame | None:
        if not self.enabled or not self.session:
            return None
        try:
            resp = self.session.get_kline(
                category=self.category,
                symbol=symbol,
                interval=interval,
                limit=limit,
            )
            if self._ok(resp) and resp.get("result", {}).get("list"):
                df = pd.DataFrame(
                    resp["result"]["list"],
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
                    df["start_time"].astype(int),
                    unit="ms",
                    utc=True,
                ).dt.tz_convert(TIMEZONE)
                for col in ["open", "high", "low", "close", "volume", "turnover"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df.set_index("start_time", inplace=True)
                df.sort_index(inplace=True)
                if df.empty:
                    self.logger.warning(
                        f"Fetched klines for {symbol} {interval} but DataFrame is empty after processing.",
                    )
                    return None
                return df
            self.logger.warning(
                f"Could not fetch klines for {symbol} {interval}. Response: {resp}",
            )
            return None
        except (pybit.exceptions.FailedRequestError, KeyError, ValueError) as e:
            self.logger.error(
                f"fetch_klines exception for {symbol} {interval}: {e}\n{traceback.format_exc()}",
            )
            self._handle_403_error(e)
            return None

    async def fetch_orderbook(self, symbol: str, limit: int) -> dict | None:
        if not self.enabled or not self.session:
            return None
        try:
            params = {"category": self.category, "symbol": symbol, "limit": limit}
            response = self.session.get_orderbook(**params)
            if self._ok(response) and response.get("result"):
                return response["result"]
            self.logger.warning(
                f"Could not fetch orderbook for {symbol}. Response: {response}",
            )
            return None
        except (pybit.exceptions.FailedRequestError, KeyError) as e:
            self.logger.error(
                f"fetch_orderbook exception for {symbol}: {e}\n{traceback.format_exc()}",
            )
            self._handle_403_error(e)
            return None

    async def fetch_instrument_info(self, symbol: str) -> dict | None:
        if not self.enabled or not self.session:
            return None
        try:
            params = {"category": self.category, "symbol": symbol}
            response = self.session.get_instruments_info(**params)
            if self._ok(response) and response.get("result", {}).get("list"):
                return response["result"]["list"][0]
            self.logger.warning(
                f"Could not fetch instrument info for {symbol}. Response: {response}",
            )
            return None
        except (pybit.exceptions.FailedRequestError, KeyError) as e:
            self.logger.error(
                f"fetch_instrument_info exception for {symbol}: {e}\n{traceback.format_exc()}",
            )
            self._handle_403_error(e)
            return None

    async def get_executions(
        self,
        symbol: str,
        start_time_ms: int,
        limit: int,
    ) -> dict | None:
        if not self.enabled or not self.session:
            return None
        try:
            params = {
                "category": self.category,
                "symbol": symbol,
                "startTime": start_time_ms,
                "limit": limit,
            }
            response = self.session.get_executions(**params)
            self._log_api("get_executions", response, "debug")
            return response
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(
                f"get_executions exception: {e}\n{traceback.format_exc()}",
            )
            self._handle_403_error(e)
            return None

    async def cancel_all_orders(self, symbol: str) -> dict | None:
        if not self.enabled or not self.session:
            return None
        try:
            params = {"category": self.category, "symbol": symbol}
            resp = self.session.cancel_all_orders(**params)
            self._log_api("cancel_all_orders", resp)
            return resp
        except (pybit.exceptions.FailedRequestError, Exception) as e:
            self.logger.error(
                f"cancel_all_orders exception for {symbol}: {e}\n{traceback.format_exc()}",
            )
            self._handle_403_error(e)
            return None

    # --- WebSocket Management (Asyncio) ---
    async def _run_ws(
        self,
        ws_type: Literal["public", "private"],
        pybit_ws_instance: WebSocket,
    ):
        while not self.stop_event.is_set():
            try:
                self.logger.info(f"Attempting {ws_type} WebSocket connection...")
                await pybit_ws_instance.connect()

                # Subscribe to channels
                subscriptions = []
                symbol = self.cfg["symbol"]
                if ws_type == "public":
                    subscriptions.append(f"kline.{self.cfg['interval']}.{symbol}")
                    subscriptions.append(f"orderbook.1.{symbol}")
                    subscriptions.append(f"tickers.{symbol}")
                else:
                    subscriptions.extend(["position", "order", "execution", "wallet"])

                await pybit_ws_instance.subscribe(subscriptions)
                self.logger.info(
                    f"{ws_type} WebSocket connection opened and subscribed.",
                )

                while pybit_ws_instance.ws and pybit_ws_instance.ws.connected:
                    await asyncio.sleep(
                        self.cfg["execution"]["live_sync"]["heartbeat"]["interval_ms"]
                        / 1000.0,
                    )

            except Exception as e:
                self.logger.error(
                    f"WebSocket error ({ws_type}): {e}. Retrying in {WS_RECONNECT_DELAY_SECONDS}s.\n{traceback.format_exc()}",
                )
                self._track_ws_disconnect()
                await asyncio.sleep(WS_RECONNECT_DELAY_SECONDS)

    async def _handle_ws_messages(self, ws_instance: WebSocket):
        try:
            while not self.stop_event.is_set():
                await asyncio.sleep(0.1)
        except Exception as e:
            self.logger.error(f"Error handling WS messages: {e}")

    async def start_websocket_manager(self):
        if not self.enabled:
            return
        self.ws_manager = WebSocketManager(self, self.cfg, self.logger)
        await self.ws_manager.start()

    async def shutdown(self):
        self.stop_event.set()
        if self.ws_manager:
            await self.ws_manager.shutdown()
        self.save_state()
        self.logger.info("PybitTradingClient shutdown complete.")

    def save_state(self):
        pass

    def load_state(self) -> bool:
        pass


class WebSocketManager:
    def __init__(
        self,
        api_client: PybitTradingClient,
        config: dict,
        logger: logging.Logger,
    ):
        self.api_client, self.cfg, self.logger = api_client, config, logger
        self.stop_event = api_client.stop_event
        self.public_ws_url = (
            "wss://stream.bybit.com/v5/public/linear"
            if not api_client.testnet
            else "wss://stream-testnet.bybit.com/v5/public/linear"
        )
        self.private_ws_url = (
            "wss://stream.bybit.com/v5/private"
            if not api_client.testnet
            else "wss://stream-testnet.bybit.com/v5/private"
        )
        self.ws_public: WebSocket | None = None
        self.ws_private: WebSocket | None = None
        self.public_ws_task: asyncio.Task | None = None
        self.private_ws_task: asyncio.Task | None = None
        self.positions: dict[str, dict] = {}
        self.orders: dict[str, dict] = {}
        self.last_exec_time_ms = 0
        self.state_lock = asyncio.Lock()
        self.listeners = {
            "position_update": [self.handle_position_update],
            "order_update": [self.handle_order_update],
            "execution": [self.handle_execution_update],
            "account_update": [self.handle_account_update],
            "kline_update": [self.handle_kline_update],
            "orderbook_update": [self.handle_orderbook_update],
            "ticker_update": [self.handle_ticker_update],
        }

    async def start(self):
        self.ws_public = WebSocket(
            testnet=self.api_client.testnet,
            api_key=API_KEY,
            api_secret=API_SECRET,
            ws_url=self.public_ws_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
            ping_interval=self.cfg["execution"]["live_sync"]["heartbeat"]["interval_ms"]
            / 1000.0,
            ping_timeout=self.cfg["execution"]["live_sync"]["heartbeat"]["interval_ms"]
            / 2000.0,
        )
        self.ws_private = WebSocket(
            testnet=self.api_client.testnet,
            api_key=API_KEY,
            api_secret=API_SECRET,
            ws_url=self.private_ws_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
            ping_interval=self.cfg["execution"]["live_sync"]["heartbeat"]["interval_ms"]
            / 1000.0,
            ping_timeout=self.cfg["execution"]["live_sync"]["heartbeat"]["interval_ms"]
            / 2000.0,
        )
        self.public_ws_task = asyncio.create_task(
            self._run_ws("public", self.ws_public),
        )
        if self.api_client.enabled:
            self.private_ws_task = asyncio.create_task(
                self._run_ws("private", self.ws_private),
            )

    async def shutdown(self):
        if self.ws_public:
            self.ws_public.close()
        if self.ws_private:
            self.ws_private.close()
        if self.public_ws_task:
            self.public_ws_task.cancel()
        if self.private_ws_task:
            self.private_ws_task.cancel()
        await asyncio.gather(
            self.public_ws_task,
            self.private_ws_task,
            return_exceptions=True,
        )

    async def _run_ws(self, ws_type: str, ws: WebSocket):
        while not self.stop_event.is_set():
            try:
                self.logger.info(f"Attempting {ws_type} WebSocket connection...")
                await ws.connect()
                subscriptions = []
                symbol = self.cfg["symbol"]
                if ws_type == "public":
                    subscriptions.append(f"kline.{self.cfg['interval']}.{symbol}")
                    subscriptions.append(f"orderbook.1.{symbol}")
                    subscriptions.append(f"tickers.{symbol}")
                else:
                    subscriptions.extend(["position", "order", "execution", "wallet"])
                await ws.subscribe(subscriptions)
                self.logger.info(
                    f"{ws_type} WebSocket connection opened and subscribed.",
                )
                await ws.run_forever()
            except Exception as e:
                self.logger.error(
                    f"WebSocket error ({ws_type}): {e}. Retrying in {WS_RECONNECT_DELAY_SECONDS}s.\n{traceback.format_exc()}",
                )
                self.api_client._track_ws_disconnect()
                await asyncio.sleep(WS_RECONNECT_DELAY_SECONDS)

    def _on_message(self, message):
        try:
            data = json.loads(message)
            asyncio.create_task(self._process_ws_message(data))
        except Exception:
            self.logger.exception("Error processing WS message")

    def _on_error(self, ws, error):
        self.logger.error(f"WebSocket Error: {error}")
        self.api_client._track_ws_disconnect()

    def _on_close(self, ws_inst, close_status_code, close_msg):
        self.logger.warning(
            f"WebSocket closed: {close_status_code} {close_msg}. Reconnecting...",
        )
        self.api_client._track_ws_disconnect()

    def _on_open(self, ws_inst):
        self.logger.info("WebSocket connection opened.")
        self.api_client.new_kline_event.set()

    async def _process_ws_message(self, data):
        topic = data.get("topic")
        if topic and topic.startswith("position"):
            await self.handle_position_update(data.get("data", []))
        elif topic and topic.startswith("order"):
            await self.handle_order_update(data.get("data", []))
        elif topic and topic.startswith("execution"):
            await self.handle_execution_update(data.get("data", []))
        elif topic and topic.startswith("wallet"):
            await self.handle_account_update(data.get("data", {}))
        elif topic and topic.startswith("kline."):
            await self.handle_kline_update(data.get("data", []))
        elif topic and topic.startswith("orderbook."):
            await self.handle_orderbook_update(data.get("data", {}))
        elif topic and topic.startswith("tickers."):
            await self.handle_ticker_update(data.get("data", []))

    async def handle_position_update(self, position_list: list[dict]):
        for pos_info in position_list:
            symbol = pos_info.get("symbol")
            if symbol and symbol == self.cfg["symbol"]:
                local_pos = self._convert_ws_position_to_local(pos_info)
                if local_pos:
                    async with self.state_lock:
                        self.positions[symbol] = local_pos

    async def handle_order_update(self, order_list: list[dict]):
        for order_info in order_list:
            order_id = order_info.get("orderId")
            if order_id:
                async with self.state_lock:
                    self.orders[order_id] = order_info

    async def handle_execution_update(self, execution_list: list[dict]):
        for exec_info in execution_list:
            exec_time_ms = int(exec_info.get("execTime", 0))
            self.last_exec_time_ms = max(self.last_exec_time_ms, exec_time_ms)

    async def handle_account_update(self, account_data: dict):
        pass

    async def handle_kline_update(self, kline_data: list[dict]):
        if kline_data and kline_data[0].get("confirm") is True:
            kline_manager = self.api_client.kline_data_managers.get(
                f"{self.cfg['symbol']}_{self.cfg['interval']}",
            )
            if kline_manager:
                await kline_manager.update_from_ws(kline_data[0])
            self.api_client.new_kline_event.set()

    async def handle_orderbook_update(self, orderbook_data: dict):
        if self.api_client.orderbook_data_manager:
            if orderbook_data.get("u") is not None:
                await self.api_client.orderbook_data_manager.update_delta(
                    orderbook_data,
                )
            else:
                await self.api_client.orderbook_data_manager.update_snapshot(
                    orderbook_data,
                )

    async def handle_ticker_update(self, ticker_data: list[dict]):
        pass

    def _convert_ws_position_to_local(self, ws_pos: dict) -> dict | None:
        symbol = ws_pos.get("symbol")
        if not symbol:
            return None
        try:
            return {
                "entry_time": datetime.fromtimestamp(
                    int(ws_pos.get("createdTime", 0)) / 1000,
                    tz=TIMEZONE,
                ),
                "symbol": symbol,
                "side": "BUY" if ws_pos.get("side") == "Buy" else "SELL",
                "entry_price": Decimal(ws_pos.get("avgPrice", "0")),
                "qty": Decimal(ws_pos.get("size", "0")),
                "stop_loss": Decimal(ws_pos.get("stopLoss", "0")),
                "take_profit": Decimal(ws_pos.get("takeProfit", "0")),
                "status": "OPEN",
                "link_prefix": f"ws_{int(time.time() * 1000)}",
                "adds": 0,
                "order_id": None,
                "stop_loss_order_id": None,
                "take_profit_order_ids": [],
                "breakeven_set": False,
                "unrealized_pnl": Decimal(ws_pos.get("unrealisedPnl", "0")),
            }
        except (ValueError, KeyError) as e:
            self.logger.error(
                f"Error converting WS position data for {symbol}: {e}\n{traceback.format_exc()}",
            )
            return None


# --- Position Management ---
@dataclass
class Position:
    entry_time: datetime
    symbol: str
    side: Literal["BUY", "SELL"]
    entry_price: Decimal
    qty: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    status: Literal["OPEN", "CLOSED", "PENDING_CLOSE"]
    link_prefix: str
    adds: int
    order_id: str | None = None
    stop_loss_order_id: str | None = None
    take_profit_order_ids: list[str] = field(default_factory=list)
    breakeven_set: bool = False
    unrealized_pnl: Decimal = Decimal("0")
    best_price: Decimal | None = None


class PositionManager:
    def __init__(
        self,
        config: dict,
        logger: logging.Logger,
        symbol: str,
        pybit_client: PybitTradingClient,
        performance_tracker: "PerformanceTracker",
    ):
        self.config, self.logger, self.symbol = config, logger, symbol
        self.pybit = pybit_client
        self.performance_tracker = performance_tracker
        self.live = bool(config.get("execution", {}).get("use_pybit", False))
        self.open_positions: dict[str, Position] = {}
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.order_precision = config["trade_management"]["order_precision"]
        self.price_precision = config["trade_management"]["price_precision"]
        self.qty_step = None
        self.slippage_percent = Decimal(
            str(config["trade_management"].get("slippage_percent", 0.0)),
        )
        self.stop_loss_atr_multiple = Decimal(
            str(config["trade_management"]["stop_loss_atr_multiple"]),
        )
        self.take_profit_atr_multiple = Decimal(
            str(config["trade_management"]["take_profit_atr_multiple"]),
        )
        self.trailing_stop_atr_multiple = Decimal(
            str(config["trade_management"].get("trailing_stop_atr_multiple", 0.5)),
        )
        self.trade_management_enabled = bool(config["trade_management"]["enabled"])
        self.current_account_balance = Decimal(
            str(config["trade_management"]["account_balance"]),
        )

    async def _update_precision_from_exchange(self):
        if not self.live or not self.pybit or not self.pybit.enabled:
            return
        info = await self.pybit.fetch_instrument_info(self.symbol)
        if info:
            if "lotSizeFilter" in info:
                lot_size_filter = info["lotSizeFilter"]
                self.qty_step = Decimal(str(lot_size_filter.get("qtyStep")))
                if not self.qty_step.is_zero():
                    self.order_precision = abs(self.qty_step.as_tuple().exponent)
            if "priceFilter" in info:
                price_filter = info["priceFilter"]
                tick_size = Decimal(str(price_filter.get("tickSize")))
                if not tick_size.is_zero():
                    self.price_precision = abs(tick_size.as_tuple().exponent)

    async def _get_current_balance(self) -> Decimal:
        if self.live and self.pybit and self.pybit.enabled:
            resp = await self.pybit.get_wallet_balance(coin="USDT")
            if resp and self.pybit._ok(resp) and resp.get("result", {}).get("list"):
                for account in resp["result"]["list"]:
                    for coin_balance in account.get("coin", []):
                        if coin_balance["coin"] == "USDT":
                            return Decimal(coin_balance["walletBalance"])
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    def _calculate_order_size(
        self,
        current_price: Decimal,
        atr_value: Decimal,
        conviction: float = 1.0,
    ) -> Decimal:
        if not self.trade_management_enabled:
            return Decimal("0")
        account_balance = self.current_account_balance
        risk_per_trade_percent = (
            Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
            / 100
        )
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )
        risk_multiplier = Decimal(str(np.clip(0.5 + conviction, 0.5, 1.5)))
        risk_amount = account_balance * risk_per_trade_percent * risk_multiplier
        stop_loss_distance_usd = atr_value * stop_loss_atr_multiple
        if stop_loss_distance_usd <= 0:
            return Decimal("0")
        order_qty = (risk_amount / stop_loss_distance_usd) / current_price
        if self.qty_step and self.qty_step > Decimal(0):
            return round_qty(order_qty, self.qty_step)
        return order_qty.quantize(Decimal("1e-6"), rounding=ROUND_DOWN)

    def _compute_stop_loss_price(
        self,
        side: Literal["BUY", "SELL"],
        entry_price: Decimal,
        atr_value: Decimal,
    ) -> Decimal:
        sl_cfg = self.config["execution"]["sl_scheme"]
        sl = Decimal("0")
        if sl_cfg["type"] == "atr_multiple":
            sl = (
                (entry_price - atr_value * self.stop_loss_atr_multiple)
                if side == "BUY"
                else (entry_price + atr_value * self.stop_loss_atr_multiple)
            )
        elif sl_cfg["type"] == "percent":
            sl_pct = Decimal(str(sl_cfg["percent"])) / 100
            sl = (
                (entry_price * (Decimal("1") - sl_pct))
                if side == "BUY"
                else (entry_price * (Decimal("1") + sl_pct))
            )
        return round_price(sl, self.price_precision)

    def _calculate_take_profit_price(
        self,
        side: Literal["BUY", "SELL"],
        entry_price: Decimal,
        atr_value: Decimal,
    ) -> Decimal:
        tp = (
            (entry_price + atr_value * self.take_profit_atr_multiple)
            if side == "BUY"
            else (entry_price - atr_value * self.take_profit_atr_multiple)
        )
        return round_price(tp, self.price_precision)

    def get_open_positions(self) -> list[Position]:
        return [pos for pos in self.open_positions.values() if pos.status == "OPEN"]

    def update_position_from_ws(self, ws_data: dict):
        local_pos = self.pybit.ws_manager._convert_ws_position_to_local(ws_data)
        if local_pos:
            self.open_positions[self.symbol] = Position(**local_pos)
            self.logger.debug(
                f"Position updated from WS: {self.open_positions[self.symbol]}",
            )

    async def open_position(
        self,
        signal: Literal["BUY", "SELL"],
        current_price: Decimal,
        atr_value: Decimal,
        conviction: float = 1.0,
    ) -> Position | None:
        if not self.trade_management_enabled or (
            self.symbol in self.open_positions
            and self.open_positions[self.symbol].status == "OPEN"
        ):
            self.logger.info(
                f"[{self.symbol}] Position management disabled or already open. Skipping.",
            )
            return None
        if len(self.get_open_positions()) >= self.max_open_positions:
            self.logger.warning(
                f"Max open positions ({self.max_open_positions}) reached.",
            )
            return None
        order_qty = self._calculate_order_size(current_price, atr_value, conviction)
        if order_qty <= 0:
            return None
        stop_loss = self._compute_stop_loss_price(signal, current_price, atr_value)
        take_profit = self._calculate_take_profit_price(
            signal,
            current_price,
            atr_value,
        )

        position = Position(
            entry_time=datetime.now(TIMEZONE),
            symbol=self.symbol,
            side=signal,
            entry_price=round_price(current_price, self.price_precision),
            qty=order_qty,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status="OPEN",
            link_prefix=f"wgx_{int(time.time() * 1000)}",
            adds=0,
            best_price=current_price,
        )

        if self.live and self.pybit and self.pybit.enabled:
            entry_link_id = f"{position.link_prefix}_entry"
            resp = await self.pybit.place_order(
                category=self.pybit.category,
                symbol=self.symbol,
                side=self.pybit._side_to_bybit(signal),
                orderType="Market",
                qty=self.pybit._q(order_qty),
                orderLinkId=entry_link_id,
            )
            if not self.pybit._ok(resp):
                self.logger.error(
                    f"Live entry failed. Simulating only. Response: {resp}",
                )
                return None
            self.logger.info(f"Live entry submitted: {entry_link_id}")
            position.order_id = resp["result"].get("orderId")
            position.entry_price = Decimal(resp["result"].get("avgPrice", "0"))
            position.qty = Decimal(resp["result"].get("qty", "0"))

        self.open_positions[self.symbol] = position
        self.logger.info(f"[{self.symbol}] Opened {signal} position: {position}")
        return position

    async def close_position(self, position: Position) -> bool:
        if position.status != "OPEN":
            return False
        opposing_side = "SELL" if position.side == "BUY" else "BUY"
        if self.live and self.pybit and self.pybit.enabled:
            await self.pybit.cancel_all_orders(self.symbol)
            order_response = await self.pybit.place_order(
                category=self.pybit.category,
                symbol=self.symbol,
                side=self.pybit._side_to_bybit(opposing_side),
                orderType="Market",
                qty=self.pybit._q(position.qty),
                reduceOnly=True,
            )
            if order_response and self.pybit._ok(order_response):
                position.status = "PENDING_CLOSE"
                self.logger.info(
                    f"[{self.symbol}] Placed order to close {position.side} {position.qty.normalize()}.",
                )
                return True
            self.logger.error(
                f"[{self.symbol}] Failed to place market order to close position. Response: {order_response}",
            )
            return False
        return True

    async def manage_positions(self, current_price: Decimal, atr_value: Decimal):
        if self.live:
            return
        symbols_to_remove = []
        for symbol, pos in self.open_positions.items():
            if pos.status != "OPEN":
                continue
            closed_by = ""
            close_price = Decimal("0")

            if pos.side == "BUY":
                if current_price <= pos.stop_loss:
                    closed_by = "STOP_LOSS"
                elif current_price >= pos.take_profit:
                    closed_by = "TAKE_PROFIT"
                elif pos.best_price is not None and current_price <= (
                    pos.best_price - (atr_value * self.trailing_stop_atr_multiple)
                ):
                    closed_by = "TRAILING_STOP"
                if closed_by:
                    close_price = current_price * (Decimal("1") - self.slippage_percent)
            elif pos.side == "SELL":
                if current_price >= pos.stop_loss:
                    closed_by = "STOP_LOSS"
                elif current_price <= pos.take_profit:
                    closed_by = "TAKE_PROFIT"
                elif pos.best_price is not None and current_price >= (
                    pos.best_price + (atr_value * self.trailing_stop_atr_multiple)
                ):
                    closed_by = "TRAILING_STOP"
                if closed_by:
                    close_price = current_price * (Decimal("1") + self.slippage_percent)

            if closed_by:
                pos.status = "CLOSED"
                pos.exit_time = datetime.now(TIMEZONE)
                pos.exit_price = close_price
                pos.closed_by = closed_by
                pnl = (
                    ((close_price - pos.entry_price) * pos.qty)
                    if pos.side == "BUY"
                    else ((pos.entry_price - close_price) * pos.qty)
                )
                self.performance_tracker.record_trade(pos, pnl)
                self.logger.info(
                    f"[{self.symbol}] Closed simulated {pos.side} position by {closed_by}. PnL: {pnl:.2f}",
                )
                symbols_to_remove.append(symbol)

        for symbol in symbols_to_remove:
            del self.open_positions[symbol]

    async def trail_stop(
        self,
        pos: Position,
        current_price: Decimal,
        atr_value: Decimal,
    ):
        if pos.status != "OPEN":
            return
        pos.best_price = (
            max(pos.best_price or Decimal("0"), current_price)
            if pos.side == "BUY"
            else min(pos.best_price or Decimal("99999999"), current_price)
        )

        trailing_value = self.trailing_stop_atr_multiple * atr_value
        if trailing_value <= 0:
            return

        new_sl_price = Decimal("0")
        if pos.side == "BUY":
            new_sl_price = pos.best_price - trailing_value
            if new_sl_price <= pos.stop_loss:
                return
        else:
            new_sl_price = pos.best_price + trailing_value
            if new_sl_price >= pos.stop_loss:
                return

        new_sl_price = round_price(new_sl_price, self.price_precision)

        if abs(new_sl_price - pos.stop_loss) > Decimal("0.001"):
            self.logger.info(
                f"Updating trailing stop for {self.symbol} from {pos.stop_loss:.5f} to {new_sl_price:.5f}",
            )
            pos.stop_loss = new_sl_price
            if self.live and self.pybit and self.pybit.enabled:
                await self.pybit.set_trading_stop(
                    symbol=self.symbol,
                    stop_loss=self.pybit._q(new_sl_price),
                )

    async def try_pyramid(self, current_price: Decimal, atr_value: Decimal):
        if (
            not self.config.get("pyramiding", {}).get("enabled", False)
            or not self.open_positions
        ):
            return
        py_cfg = self.config["pyramiding"]
        for symbol, pos in list(self.open_positions.items()):
            if pos.status != "OPEN" or pos.adds >= py_cfg.get("max_adds", 0):
                continue
            step_atr_mult = Decimal(str(py_cfg.get("step_atr", 0.7)))
            step_distance = step_atr_mult * atr_value
            target_price = (
                pos.entry_price + step_distance
                if pos.side == "BUY"
                else pos.entry_price - step_distance
            )

            should_add = (pos.side == "BUY" and current_price >= target_price) or (
                pos.side == "SELL" and current_price <= target_price
            )
            if should_add:
                add_qty = round_qty(
                    pos.qty * Decimal(str(py_cfg.get("size_pct_of_initial", 0.5))),
                    self.qty_step,
                )
                if add_qty <= 0:
                    continue

                self.logger.info(
                    f"Pyramiding add #{pos.adds + 1} for {self.symbol}. Adding {add_qty.normalize()} at {current_price.normalize()}",
                )

                new_total_cost = (pos.qty * pos.entry_price) + (add_qty * current_price)
                pos.qty += add_qty
                pos.entry_price = new_total_cost / pos.qty
                pos.adds += 1

                if self.live and self.pybit and self.pybit.enabled:
                    add_link_id = f"{pos.link_prefix}_add_{pos.adds}"
                    resp = await self.pybit.place_order(
                        category=self.pybit.category,
                        symbol=self.symbol,
                        side=self.pybit._side_to_bybit(pos.side),
                        orderType="Market",
                        qty=self.pybit._q(add_qty),
                        orderLinkId=add_link_id,
                    )
                    if not self.pybit._ok(resp):
                        self.logger.error(f"Live pyramiding add failed: {resp}")


# --- Performance Tracking ---
class PerformanceTracker:
    def __init__(self, logger: logging.Logger, config: dict):
        self.logger = logger
        self.config = config
        self.trades: list[dict] = []
        self.total_pnl = Decimal("0")
        self.gross_profit = Decimal("0")
        self.gross_loss = Decimal("0")
        self.wins = 0
        self.losses = 0
        self.peak_pnl = Decimal("0")
        self.max_drawdown = Decimal("0")
        self.trading_fee_percent = Decimal(
            str(config["trade_management"].get("trading_fee_percent", 0.0)),
        )
        self._daily_pnl = Decimal("0")
        self._last_day_reset = datetime.now(TIMEZONE).date()
        self.consecutive_losses = 0

    def _reset_daily_stats(self):
        today = datetime.now(TIMEZONE).date()
        if today != self._last_day_reset:
            self._daily_pnl = Decimal("0")
            self._last_day_reset = today
            self.logger.info("Resetting daily performance statistics.")

    def record_trade(self, position: dict | Position, pnl: Decimal):
        self._reset_daily_stats()
        trade_record = {
            "entry_time": position.entry_time,
            "exit_time": position.exit_time,
            "symbol": position.symbol,
            "side": position.side,
            "entry_price": position.entry_price,
            "exit_price": position.exit_price,
            "qty": position.qty,
            "pnl_gross": pnl,
            "closed_by": position.closed_by,
        }
        entry_fee = (
            Decimal(str(position.entry_price))
            * Decimal(str(position.qty))
            * self.trading_fee_percent
        )
        exit_fee = (
            Decimal(str(position.exit_price))
            * Decimal(str(position.qty))
            * self.trading_fee_percent
        )
        total_fees = entry_fee + exit_fee
        pnl_net = pnl - total_fees
        trade_record["fees"] = total_fees
        trade_record["pnl_net"] = pnl_net
        self.trades.append(trade_record)
        self.total_pnl += pnl_net
        self._daily_pnl += pnl_net
        self.peak_pnl = max(self.peak_pnl, self.total_pnl)
        drawdown = self.peak_pnl - self.total_pnl
        self.max_drawdown = max(self.max_drawdown, drawdown)
        if pnl_net > 0:
            self.wins += 1
            self.gross_profit += pnl_net
            self.consecutive_losses = 0
        else:
            self.losses += 1
            self.gross_loss += abs(pnl_net)
            self.consecutive_losses += 1
        self.logger.info(
            f"{NEON_CYAN}[{position.symbol}] Trade recorded. Gross PnL: {pnl.normalize():.4f}, Fees: {total_fees.normalize():.4f}, Net PnL: {pnl_net.normalize():.4f}. "
            f"Total PnL: {self.total_pnl.normalize():.4f}, Daily PnL: {self._daily_pnl.normalize():.4f}{RESET}",
        )

    def get_summary(self) -> dict:
        total_trades = len(self.trades)
        win_rate = (self.wins / total_trades) * 100 if total_trades > 0 else 0
        profit_factor = (
            self.gross_profit / self.gross_loss
            if self.gross_loss > 0
            else Decimal("inf")
        )
        avg_win = self.gross_profit / self.wins if self.wins > 0 else Decimal("0")
        avg_loss = self.gross_loss / self.losses if self.losses > 0 else Decimal("0")
        return {
            "total_trades": total_trades,
            "total_pnl": f"{self.total_pnl:.4f}",
            "gross_profit": f"{self.gross_profit:.4f}",
            "gross_loss": f"{self.gross_loss:.4f}",
            "profit_factor": f"{profit_factor:.2f}",
            "max_drawdown": f"{self.max_drawdown:.4f}",
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": f"{win_rate:.2f}%",
            "avg_win": f"{avg_win:.4f}",
            "avg_loss": f"{avg_loss:.4f}",
            "daily_pnl": f"{self._daily_pnl:.4f}",
            "consecutive_losses": self.consecutive_losses,
        }


# --- Trading Analyzer ---
class TradingAnalyzer:
    def __init__(
        self,
        df: pd.DataFrame,
        config: dict,
        logger: logging.Logger,
        symbol: str,
    ):
        self.df = df.copy()
        self.config, self.logger, self.symbol = config, logger, symbol
        self.indicator_values: dict[str, Any] = {}
        self.fib_levels: dict[str, Decimal] = {}
        self.weights = config["weight_sets"]["default_scalping"]
        self.indicator_settings = config["indicator_settings"]
        self._last_score = float(config.get("_last_score", 0.0))
        self._last_signal_ts = int(config.get("_last_signal_ts", 0))

    def update_data(self, new_df: pd.DataFrame):
        self.df = new_df.copy()
        if self.df.empty:
            return
        self._calculate_all_indicators()
        if self.config["indicators"].get("fibonacci_levels", False):
            self.calculate_fibonacci_levels()
        if self.config["indicators"].get("fibonacci_pivot_points", False):
            self.calculate_fibonacci_pivot_points()

    def _safe_calculate(
        self,
        func: Callable,
        name: str,
        min_data_points: int = 0,
        *args,
        **kwargs,
    ) -> Any | None:
        if len(self.df) < min_data_points:
            self.logger.debug(
                f"[{self.symbol}] Skipping indicator '{name}': Not enough data (need {min_data_points}, have {len(self.df)}).",
            )
            return None
        try:
            result = func(self.df, *args, **kwargs)
            if isinstance(result, (pd.Series, pd.DataFrame)) and result.empty:
                return None
            return result
        except Exception as e:
            self.logger.error(
                f"[{self.symbol}] Error calculating indicator '{name}': {e}\n{traceback.format_exc()}",
            )
            return None

    def _calculate_all_indicators(self):
        self.logger.debug(f"[{self.symbol}] Calculating all technical indicators...")
        cfg, isd = self.config, self.indicator_settings
        self.indicator_values.clear()

        # Recalculate indicators
        # Your original indicator calculation logic here... (truncated for brevity)
        if cfg["indicators"].get("atr", False):
            self.df["ATR"] = ta.atr(
                self.df.high,
                self.df.low,
                self.df.close,
                length=isd["atr_period"],
            )
            if not self.df["ATR"].empty and not pd.isna(self.df["ATR"].iloc[-1]):
                self.indicator_values["ATR"] = Decimal(str(self.df["ATR"].iloc[-1]))

        # ... (all other indicators)

    def calculate_fibonacci_levels(self) -> None:
        window = self.config["indicator_settings"]["fibonacci_window"]
        fib_levels = indicators.calculate_fibonacci_levels(self.df, window)
        if fib_levels:
            price_precision = self.config["trade_management"]["price_precision"]
            self.fib_levels = {
                k: Decimal(str(v)).quantize(
                    Decimal(f"1e-{price_precision}"),
                    rounding=ROUND_DOWN,
                )
                for k, v in fib_levels.items()
            }

    def calculate_fibonacci_pivot_points(self) -> None:
        pivot_data = indicators.calculate_fibonacci_pivot_points(self.df)
        if pivot_data:
            price_precision = self.config["trade_management"]["price_precision"]
            for key, value in pivot_data.items():
                try:
                    self.indicator_values[key.upper()] = Decimal(str(value)).quantize(
                        Decimal(f"1e-{price_precision}"),
                        rounding=ROUND_DOWN,
                    )
                except InvalidOperation:
                    self.logger.warning(
                        f"[{self.symbol}] Could not convert pivot point value '{value}' to Decimal. Skipping.",
                    )

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        return self.indicator_values.get(key, default)

    async def _check_orderbook(
        self,
        orderbook_manager: AdvancedOrderbookManager,
    ) -> float:
        best_bid, best_ask = await orderbook_manager.get_best_bid_ask()
        if best_bid is None or best_ask is None:
            return 0.0
        depth_limit = self.config["orderbook_limit"]
        bids_levels, asks_levels = await orderbook_manager.get_depth(depth_limit)
        bid_volume = sum(Decimal(str(level.quantity)) for level in bids_levels)
        ask_volume = sum(Decimal(str(level.quantity)) for level in asks_levels)
        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return 0.0
        imbalance = _safe_divide_decimal(bid_volume - ask_volume, total_volume)
        return float(imbalance)

    async def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_manager: AdvancedOrderbookManager,
        mtf_trends: dict[str, str],
        pybit_client: "PybitTradingClient",
    ) -> tuple[str, float, dict[str, float]]:
        signal_score = 0.0
        signal_breakdown: dict[str, float] = {}
        active_indicators = self.config["indicators"]
        weights = self.weights
        isd = self.indicator_settings
        if self.df.empty:
            return "HOLD", 0.0, {}
        current_close = Decimal(str(self.df["close"].iloc[-1]))
        prev_close = Decimal(
            str(self.df["close"].iloc[-2]) if len(self.df) > 1 else current_close,
        )

        # Market Regime & Dynamic Weights
        # ... (Your original logic here)

        # Score Indicators (incorporate your original logic here)
        # ... (e.g., ADX, EMA, SMA, Momentum, etc.)

        # Orderbook Imbalance is now async
        if active_indicators.get("orderbook_imbalance", False) and orderbook_manager:
            imbalance = await self._check_orderbook(orderbook_manager)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        # MTF Analysis is now async
        if self.config["mtf_analysis"]["enabled"]:
            for htf_interval in self.config["mtf_analysis"]["higher_timeframes"]:
                kline_key = f"{self.symbol}_{htf_interval}"
                if kline_key not in pybit_client.kline_data_managers:
                    pybit_client.kline_data_managers[kline_key] = KlineDataManager(
                        self.symbol,
                        htf_interval,
                        1000,
                        self.logger,
                    )
                    await pybit_client.kline_data_managers[kline_key].initialize(
                        pybit_client,
                    )
                higher_tf_df = await pybit_client.kline_data_managers[
                    kline_key
                ].get_df()
                trend = indicators._get_mtf_trend(
                    higher_tf_df,
                    htf_interval,
                    self.config["mtf_analysis"]["trend_indicators"][0],
                )
                if trend != "UNKNOWN":
                    mtf_trends[
                        f"{htf_interval}_{self.config['mtf_analysis']['trend_indicators'][0]}"
                    ] = trend
                await asyncio.sleep(
                    self.config["mtf_analysis"]["mtf_request_delay_seconds"],
                )

        # Final Signal Determination
        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold:
            final_signal = "BUY"
        elif signal_score <= -threshold:
            final_signal = "SELL"
        self.logger.info(
            f"[{self.symbol}] Generated Signal: {final_signal} (Score: {signal_score:.2f}, Threshold: {threshold:.2f})",
        )
        return final_signal, signal_score, signal_breakdown


# --- Main Bot Logic ---
def check_manual_pause() -> bool:
    if Path(PAUSE_FILE).exists():
        global_logger.warning(
            f"{NEON_YELLOW}Manual pause file '{PAUSE_FILE}' detected. Trading halted.{RESET}",
        )
        return True
    return False


def get_spread_bps_from_levels(ob_data: dict) -> float:
    bids, asks = ob_data.get("bids", []), ob_data.get("asks", [])
    if bids and asks:
        best_bid = Decimal(str(bids[0].price))
        best_ask = Decimal(str(asks[0].price))
        spread = best_ask - best_bid
        if best_ask > 0:
            return float((spread / best_ask) * 10000)
    return float("inf")


def expected_value(pt: PerformanceTracker) -> float:
    summary = pt.get_summary()
    win_rate = float(summary["win_rate"].replace("%", "")) / 100
    avg_win = float(summary["avg_win"])
    avg_loss = float(summary["avg_loss"])
    loss_rate = 1 - win_rate
    ev = (win_rate * avg_win) - (loss_rate * avg_loss)
    return ev if pt.wins + pt.losses > 10 else 1.0


def in_allowed_session(config: dict) -> bool:
    if not config["session_filter"]["enabled"]:
        return True
    now = datetime.now(UTC)
    for start_str, end_str in config["session_filter"]["utc_allowed"]:
        start_time = datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.strptime(end_str, "%H:%M").time()
        current_time = now.time()
        if start_time < end_time:
            if start_time <= current_time <= end_time:
                return True
        elif current_time >= start_time or current_time <= end_time:
            return True
    return False


async def main() -> None:
    logger = setup_logger("whalebot", logging.INFO)
    config = load_config(CONFIG_FILE, logger)
    alert_system = AlertSystem(logger)
    pybit_client = PybitTradingClient(config, logger)
    if not pybit_client.enabled:
        logger.error(
            f"{NEON_RED}Pybit client is not enabled or failed to initialize. Cannot proceed with live trading. Exiting.{RESET}",
        )
        return

    await pybit_client.kline_data_managers[
        f"{config['symbol']}_{config['interval']}"
    ].initialize(pybit_client)
    await pybit_client.start_websocket_manager()
    await asyncio.sleep(WS_RECONNECT_DELAY_SECONDS)

    position_manager = PositionManager(
        config,
        logger,
        config["symbol"],
        pybit_client,
        PerformanceTracker(logger, config),
    )
    performance_tracker = PerformanceTracker(logger, config)
    analyzer = TradingAnalyzer(pd.DataFrame(), config, logger, config["symbol"])
    exec_sync = (
        ExchangeExecutionSync(
            config["symbol"],
            pybit_client,
            config,
            position_manager,
            performance_tracker,
        )
        if config["execution"]["live_sync"]["enabled"]
        else None
    )
    heartbeat = (
        PositionHeartbeat(config["symbol"], pybit_client, config, position_manager)
        if config["execution"]["live_sync"]["heartbeat"]["enabled"]
        else None
    )

    while not pybit_client.stop_event.is_set():
        try:
            if (
                pybit_client.is_circuit_breaker_tripped()
                or check_manual_pause()
                or performance_tracker.consecutive_losses
                >= config["risk_guardrails"]["consecutive_losses_limit"]
            ):
                logger.critical(
                    f"{NEON_RED}Trading halted by risk-management or manual pause. Cooling down.{RESET}",
                )
                alert_system.send_alert("Trading halted.", "ERROR")
                await asyncio.sleep(
                    config["risk_guardrails"]["cooldown_after_kill_min"] * 60,
                )
                continue
            if not in_allowed_session(config):
                logger.info(
                    f"{NEON_BLUE}Outside allowed trading sessions. Holding.{RESET}",
                )
                await asyncio.sleep(config["loop_delay"])
                continue

            logger.info(
                f"{NEON_PURPLE}--- New Analysis Loop ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S %Z')}) ---{RESET}",
            )

            df = await pybit_client.kline_data_managers[
                f"{config['symbol']}_{config['interval']}"
            ].get_df()
            if df.empty:
                logger.warning(
                    f"[{config['symbol']}] Kline Data Manager DataFrame is empty. Waiting for data.",
                )
                await asyncio.sleep(config["loop_delay"])
                continue

            await pybit_client.new_kline_event.wait()
            pybit_client.new_kline_event.clear()

            analyzer.update_data(df)
            current_price = Decimal(str(df["close"].iloc[-1]))
            atr_value = Decimal(
                str(analyzer._get_indicator_value("ATR", Decimal("0.01"))),
            )

            ob_data = await pybit_client.orderbook_data_manager.get_depth(
                config["orderbook_limit"],
            )
            if ob_data and get_spread_bps_from_levels(
                {"bids": ob_data[0], "asks": ob_data[1]},
            ) > float(config["risk_guardrails"]["spread_filter_bps"]):
                logger.warning("Spread too high. Holding.")
                await asyncio.sleep(config["loop_delay"])
                continue
            if (
                config["risk_guardrails"]["ev_filter_enabled"]
                and expected_value(performance_tracker) <= 0
            ):
                logger.warning("Negative Expected Value detected. Holding.")
                await asyncio.sleep(config["loop_delay"])
                continue

            mtf_trends = {}
            if config["mtf_analysis"]["enabled"]:
                # The logic for MTF is now inside generate_trading_signal, simplifying the main loop.
                pass

            (
                trading_signal,
                signal_score,
                signal_breakdown,
            ) = await analyzer.generate_trading_signal(
                current_price,
                pybit_client.orderbook_data_manager,
                mtf_trends,
                pybit_client,
            )

            await position_manager.manage_positions(current_price, atr_value)
            for pos in position_manager.get_open_positions():
                await position_manager.trail_stop(pos, current_price, atr_value)
                await position_manager.try_pyramid(current_price, atr_value)

            if trading_signal in ("BUY", "SELL"):
                conviction = min(
                    1.0,
                    max(
                        0.0,
                        (abs(signal_score) - config["signal_score_threshold"])
                        / config["signal_score_threshold"],
                    ),
                )
                if abs(signal_score) >= config["signal_score_threshold"]:
                    logger.info(
                        f"Strong {trading_signal} signal detected! Score: {signal_score:.2f}",
                    )
                    await position_manager.open_position(
                        trading_signal,
                        current_price,
                        atr_value,
                        conviction,
                    )

            if exec_sync:
                await exec_sync.poll()
            if heartbeat:
                await heartbeat.tick()

            # Display summary (your original function)

            await asyncio.sleep(config["loop_delay"])
        except asyncio.CancelledError:
            logger.info(f"{NEON_BLUE}Main loop cancelled gracefully.{RESET}")
            break
        except Exception as e:
            alert_system.send_alert(
                f"[{config['symbol']}] Unhandled error in main loop: {e}",
                "ERROR",
            )
            logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
            await asyncio.sleep(config["loop_delay"] * 2)
        finally:
            await pybit_client.shutdown()


if __name__ == "__main__":
    global_logger = setup_logger("whalebot", logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        global_logger.info(
            f"{NEON_YELLOW}Bot stopped by user (KeyboardInterrupt). Shutting down...{RESET}",
        )
    except Exception as e:
        global_logger.critical(
            f"{NEON_RED}Critical error during bot startup or top-level execution: {e}{RESET}",
            exc_info=True,
        )
        sys.exit(1)
