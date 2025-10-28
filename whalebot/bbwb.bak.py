import asyncio
import contextlib
import json
import logging
import os
import random
import sys
import time
from dataclasses import dataclass  # New: Explicit import for dataclass
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal, getcontext
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Generic, TypeVar
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pandas_ta as ta
import requests
from colorama import Fore, Style, init
from pybit.unified_trading import HTTP, WebSocket

SKLEARN_AVAILABLE = False

getcontext().prec = 28
init(autoreset=True)
# Manually load .env file as a fallback
try:
    with open("/data/data/com.termux/files/home/Algobots/whalebot/.env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'\"")
                if value:
                    os.environ[key] = value
except FileNotFoundError:
    # The script will check for the env vars later and exit if not found
    pass

NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
NEON_CYAN = Fore.CYAN
RESET = Style.RESET_ALL

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
}

API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs"
Path(LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

TIMEZONE = ZoneInfo("America/Chicago")
MAX_API_RETRIES = 5
RETRY_DELAY_SECONDS = 7
REQUEST_TIMEOUT = 20
LOOP_DELAY_SECONDS = 15

MIN_DATA_POINTS_TR = 2
MIN_DATA_POINTS_SMOOTHER = 2
MIN_DATA_POINTS_OBV = 2
MIN_DATA_POINTS_PSAR = 2
ADX_STRONG_TREND_THRESHOLD = 25
ADX_WEAK_TREND_THRESHOLD = 20

WS_RECONNECT_DELAY_SECONDS = 5
API_CALL_RETRY_DELAY_SECONDS = 3


def load_config(filepath: str, logger: logging.Logger) -> dict[str, Any]:
    """Load configuration from JSON file, creating a default if not found."""
    default_config = {
        "symbol": "BTCUSDT",
        "interval": "15",
        "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50,
        "testnet": True,
        "timezone": "America/Chicago",
        "signal_score_threshold": 2.0,
        "volume_confirmation_multiplier": 1.5,
        "trade_management": {
            "enabled": True,
            "account_balance": 1000.0,
            "risk_per_trade_percent": 1.0,
            "stop_loss_atr_multiple": 1.5,
            "take_profit_atr_multiple": 2.0,
            "trailing_stop_atr_multiple": 0.5,
            "max_open_positions": 1,
            "default_leverage": 5,
        },
        "mtf_analysis": {
            "enabled": True,
            "higher_timeframes": ["60", "240"],
            "trend_indicators": ["ema", "ehlers_supertrend"],
            "trend_period": 50,
            "mtf_request_delay_seconds": 0.5,
        },
        "ml_enhancement": {
            "enabled": False,
            "model_path": "ml_model.pkl",
            "retrain_on_startup": False,
            "training_data_limit": 5000,
            "prediction_lookahead": 12,
            "profit_target_percent": 0.5,
            "feature_lags": [1, 2, 3, 5],
            "cross_validation_folds": 5,
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
        },
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
        with Path(filepath).open(encoding="utf-8") as f:
            config = json.load(f)
        _ensure_config_keys(config, default_config)
        with Path(filepath).open("w", encoding="utf-8") as f_write:
            json.dump(config, f_write, indent=4)
        return config
    except (OSError, FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(
            f"{NEON_RED}Error loading config: {e}. Using default and attempting to save.{RESET}",
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


class SensitiveFormatter(logging.Formatter):
    """Formatter that redacts API keys from log records."""

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
    """Configure and return a logger with file and console handlers."""
    logger = logging.getLogger(log_name)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
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


KT = TypeVar("KT")
VT = TypeVar("VT")


@dataclass(slots=True)
class PriceLevel:
    """Price level with metadata, optimized for memory with slots."""

    price: float
    quantity: float
    timestamp: int
    order_count: int = 1

    def __lt__(self, other: "PriceLevel") -> bool:
        return self.price < other.price

    def __eq__(self, other: "PriceLevel") -> bool:
        return abs(self.price - other.price) < 1e-8


class OptimizedSkipList(Generic[KT, VT]):
    """Enhanced Skip List implementation with O(log n) insert/delete/search.
    Asynchronous operations are not directly supported by SkipList itself,
    but it's protected by an asyncio.Lock in the manager.
    """

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
        level = 0
        while level < self.max_level and random.random() < self.p:
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


class EnhancedHeap:
    """Enhanced heap implementation (Min-Heap or Max-Heap) with position tracking
    for O(log n) update and removal operations.
    Protected by an asyncio.Lock in the manager.
    """

    def __init__(self, is_max_heap: bool = True):
        self.heap: list[PriceLevel] = []
        self.is_max_heap = is_max_heap
        self.position_map: dict[float, int] = {}

    def _parent(self, i: int) -> int:
        return (i - 1) // 2

    def _left_child(self, i: int) -> int:
        return 2 * i + 1

    def _right_child(self, i: int) -> int:
        return 2 * i + 2

    def _compare(self, a: PriceLevel, b: PriceLevel) -> bool:
        if self.is_max_heap:
            return a.price > b.price
        return a.price < b.price

    def _swap(self, i: int, j: int) -> None:
        self.position_map[self.heap[i].price] = j
        self.position_map[self.heap[j].price] = i
        self.heap[i], self.heap[j] = self.heap[j], self.heap[i]

    def _heapify_up(self, i: int) -> None:
        while i > 0:
            parent = self._parent(i)
            if not self._compare(self.heap[i], self.heap[parent]):
                break
            self._swap(i, parent)
            i = parent

    def _heapify_down(self, i: int) -> None:
        while True:
            largest = i
            left = self._left_child(i)
            right = self._right_child(i)
            if left < len(self.heap) and self._compare(
                self.heap[left],
                self.heap[largest],
            ):
                largest = left
            if right < len(self.heap) and self._compare(
                self.heap[right],
                self.heap[largest],
            ):
                largest = right
            if largest == i:
                break
            self._swap(i, largest)
            i = largest

    def insert(self, price_level: PriceLevel) -> None:
        if price_level.price in self.position_map:
            idx = self.position_map[price_level.price]
            old_price = self.heap[idx].price
            self.heap[idx] = price_level
            self.position_map[price_level.price] = idx
            if abs(old_price - price_level.price) > 1e-8:
                del self.position_map[old_price]
            self._heapify_up(idx)
            self._heapify_down(idx)
        else:
            self.heap.append(price_level)
            idx = len(self.heap) - 1
            self.position_map[price_level.price] = idx
            self._heapify_up(idx)

    def remove(self, price: float) -> bool:
        if price not in self.position_map:
            return False
        idx = self.position_map[price]
        del self.position_map[price]
        if idx == len(self.heap) - 1:
            self.heap.pop()
            return True
        last = self.heap.pop()
        self.heap[idx] = last
        self.position_map[last.price] = idx
        self._heapify_up(idx)
        self._heapify_down(idx)
        return True

    def peek_top(self) -> PriceLevel | None:
        return self.heap[0] if self.heap else None

    @property
    def size(self) -> int:
        return len(self.heap)


class AdvancedOrderbookManager:
    """Manages the orderbook for a single symbol using either OptimizedSkipList or EnhancedHeap.
    Provides thread-safe (asyncio-safe) operations, snapshot/delta processing,
    and access to best bid/ask.
    """

    def __init__(self, symbol: str, logger: logging.Logger, use_skip_list: bool = True):
        self.symbol = symbol
        self.logger = logger
        self.use_skip_list = use_skip_list
        self._lock = asyncio.Lock()

        if use_skip_list:
            self.logger.info(f"OrderbookManager for {symbol}: Using OptimizedSkipList.")
            self.bids_ds = OptimizedSkipList[float, PriceLevel]()
            self.asks_ds = OptimizedSkipList[float, PriceLevel]()
        else:
            self.logger.info(f"OrderbookManager for {symbol}: Using EnhancedHeap.")
            self.bids_ds = EnhancedHeap(is_max_heap=True)
            self.asks_ds = EnhancedHeap(is_max_heap=False)

        self.last_update_id: int = 0

    @contextlib.asynccontextmanager
    async def _lock_context(self):
        """Async context manager for acquiring and releasing the asyncio.Lock."""
        async with self._lock:
            yield

    async def _validate_price_quantity(self, price: float, quantity: float) -> bool:
        """Validates if price and quantity are non-negative and numerically valid."""
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
        """Processes an initial orderbook snapshot."""
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
                self.bids_ds = EnhancedHeap(is_max_heap=True)
                self.asks_ds = EnhancedHeap(is_max_heap=False)

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
                            self.bids_ds.insert(level)
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
                            self.asks_ds.insert(level)
                except (ValueError, TypeError) as e:
                    self.logger.error(
                        f"Failed to parse ask in snapshot for {self.symbol}: {price_str}/{qty_str}, error={e}",
                    )

            self.last_update_id = data.get("u", 0)
            self.logger.info(
                f"Orderbook {self.symbol} snapshot updated. Last Update ID: {self.last_update_id}",
            )

    async def update_delta(self, data: dict[str, Any]) -> None:
        """Applies incremental updates (deltas) to the orderbook."""
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

                    if quantity == 0.0:
                        self.bids_ds.delete(
                            price,
                        ) if self.use_skip_list else self.bids_ds.remove(price)
                    else:
                        level = PriceLevel(price, quantity, int(time.time() * 1000))
                        if self.use_skip_list:
                            self.bids_ds.insert(price, level)
                        else:
                            self.bids_ds.insert(level)
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

                    if quantity == 0.0:
                        self.asks_ds.delete(
                            price,
                        ) if self.use_skip_list else self.asks_ds.remove(price)
                    else:
                        level = PriceLevel(price, quantity, int(time.time() * 1000))
                        if self.use_skip_list:
                            self.asks_ds.insert(price, level)
                        else:
                            self.asks_ds.insert(level)
                except (ValueError, TypeError) as e:
                    self.logger.error(
                        f"Failed to parse ask delta for {self.symbol}: {price_str}/{qty_str}, error={e}",
                    )

            self.last_update_id = current_update_id
            self.logger.debug(
                f"Orderbook {self.symbol} delta applied. Last Update ID: {self.last_update_id}",
            )

    async def get_best_bid_ask(self) -> tuple[float | None, float | None]:
        """Returns the current best bid and best ask prices."""
        async with self._lock_context():
            best_bid_level = (
                self.bids_ds.peek_top(reverse=True)
                if self.use_skip_list
                else self.bids_ds.peek_top()
            )
            best_ask_level = (
                self.asks_ds.peek_top(reverse=False)
                if self.use_skip_list
                else self.asks_ds.peek_top()
            )

            best_bid = best_bid_level.price if best_bid_level else None
            best_ask = best_ask_level.price if best_ask_level else None
            return best_bid, best_ask

    async def get_depth(self, depth: int) -> tuple[list[PriceLevel], list[PriceLevel]]:
        """Retrieves the top N bids and asks."""
        async with self._lock_context():
            if self.use_skip_list:
                bids = [
                    item[1]
                    for item in self.bids_ds.get_sorted_items(reverse=True)[:depth]
                ]
                asks = [item[1] for item in self.asks_ds.get_sorted_items()[:depth]]
            else:
                bids_list: list[PriceLevel] = []
                asks_list: list[PriceLevel] = []
                temp_bids_storage: list[PriceLevel] = []
                temp_asks_storage: list[PriceLevel] = []

                for _ in range(min(depth, self.bids_ds.size)):
                    level = self.bids_ds.peek_top()
                    if level:
                        self.bids_ds.remove(level.price)
                        bids_list.append(level)
                        temp_bids_storage.append(level)
                for level in temp_bids_storage:
                    self.bids_ds.insert(level)

                for _ in range(min(depth, self.asks_ds.size)):
                    level = self.asks_ds.peek_top()
                    if level:
                        self.asks_ds.remove(level.price)
                        asks_list.append(level)
                        temp_asks_storage.append(level)
                for level in temp_asks_storage:
                    self.asks_ds.insert(level)

                bids = bids_list
                asks = asks_list
            return bids, asks


class BybitClient:
    """Manages all Bybit API interactions (HTTP & WebSocket) and includes retry logic."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        config: dict[str, Any],
        logger: logging.Logger,
    ):
        self.config = config
        self.logger = logger
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = config["testnet"]
        self.symbol = config["symbol"]
        self.category = "linear"

        self.http_session = HTTP(
            testnet=self.testnet,
            api_key=self.api_key,
            api_secret=self.api_secret,
        )

        self.ws_public: WebSocket | None = None
        self.ws_private: WebSocket | None = None
        self.ws_tasks: list[asyncio.Task] = []

        self.logger.info(f"BybitClient initialized (Testnet: {self.testnet})")

    async def _bybit_request_with_retry(
        self,
        method: str,
        func: callable,
        *args,
        **kwargs,
    ) -> dict | None:
        """Helper to execute pybit HTTP calls with retry logic."""
        for attempt in range(MAX_API_RETRIES):
            try:
                response = func(*args, **kwargs)
                if response:
                    ret_code = response.get("retCode")
                    if ret_code == 0:
                        return response
                    if ret_code == 110043:  # Leverage not modified
                        self.logger.info(
                            f"{NEON_YELLOW}Leverage already set to requested value or cannot be modified at this time. Proceeding.{RESET}",
                        )
                        return {
                            "retCode": 0,
                            "retMsg": "Leverage already set",
                        }  # Return a success response
                    error_msg = response.get("retMsg", "Unknown error")
                    self.logger.error(
                        f"{NEON_RED}Bybit API Error ({method} attempt {attempt + 1}/{MAX_API_RETRIES}): {error_msg} (Code: {ret_code}){RESET}",
                    )
                else:  # No response
                    self.logger.error(
                        f"{NEON_RED}Bybit API Error ({method} attempt {attempt + 1}/{MAX_API_RETRIES}): No response{RESET}",
                    )
            except requests.exceptions.HTTPError as e:
                self.logger.error(
                    f"{NEON_RED}HTTP Error during {method} (attempt {attempt + 1}/{MAX_API_RETRIES}): {e.response.status_code} - {e.response.text}{RESET}",
                )
            except requests.exceptions.ConnectionError as e:
                self.logger.error(
                    f"{NEON_RED}Connection Error during {method} (attempt {attempt + 1}/{MAX_API_RETRIES}): {e}{RESET}",
                )
            except requests.exceptions.Timeout:
                self.logger.error(
                    f"{NEON_RED}Request timed out during {method} (attempt {attempt + 1}/{MAX_API_RETRIES}){RESET}",
                )
            except Exception as e:
                error_message = str(e)
                if "110043" in error_message:
                    self.logger.info(
                        f"{NEON_YELLOW}Leverage already set to requested value or cannot be modified at this time. Proceeding.{RESET}",
                    )
                    return {"retCode": 0, "retMsg": "Leverage already set"}
                self.logger.error(
                    f"{NEON_RED}Unexpected Error during {method} (attempt {attempt + 1}/{MAX_API_RETRIES}): {error_message}{RESET}",
                )

            if attempt < MAX_API_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

        self.logger.critical(
            f"{NEON_RED}Bybit API {method} failed after {MAX_API_RETRIES} attempts.{RESET}",
        )
        return None

    async def fetch_current_price(self, symbol: str) -> Decimal | None:
        """Fetch the current market price for a symbol."""
        response = await self._bybit_request_with_retry(
            "fetch_current_price",
            self.http_session.get_tickers,
            category=self.category,
            symbol=symbol,
        )
        if response and response["result"] and response["result"]["list"]:
            price = Decimal(response["result"]["list"][0]["lastPrice"])
            self.logger.debug(f"Fetched current price for {symbol}: {price}")
            return price
        self.logger.warning(
            f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}",
        )
        return None

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> pd.DataFrame | None:
        """Fetch kline data for a symbol and interval."""
        response = await self._bybit_request_with_retry(
            "fetch_klines",
            self.http_session.get_kline,
            category=self.category,
            symbol=symbol,
            interval=interval,
            limit=limit,
        )
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
                df["start_time"].astype(int),
                unit="ms",
                utc=True,
            ).dt.tz_convert(self.config["timezone"])
            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df.set_index("start_time", inplace=True)
            df.sort_index(inplace=True)

            if df.empty:
                self.logger.warning(
                    f"{NEON_YELLOW}Fetched klines for {symbol} {interval} but DataFrame is empty after processing. Raw response: {response}{RESET}",
                )
                return None

            self.logger.debug(f"Fetched {len(df)} {interval} klines for {symbol}.")
            return df
        self.logger.warning(
            f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}. API response might be empty or invalid. Raw response: {response}{RESET}",
        )
        return None

    async def fetch_orderbook(self, symbol: str, limit: int) -> dict | None:
        """Fetch orderbook data for a symbol via REST."""
        response = await self._bybit_request_with_retry(
            "fetch_orderbook",
            self.http_session.get_orderbook,
            category=self.category,
            symbol=symbol,
            limit=limit,
        )
        if response and response["result"]:
            self.logger.debug(
                f"Fetched orderbook for {symbol} with limit {limit} via REST.",
            )
            return response["result"]
        self.logger.warning(
            f"{NEON_YELLOW}Could not fetch orderbook for {symbol} via REST.{RESET}",
        )
        return None

    async def place_order(
        self,
        symbol: str,
        side: str,
        qty: str,
        order_type: str = "Market",
        price: str | None = None,
        reduce_only: bool = False,
        stop_loss: str | None = None,
        take_profit: str | None = None,
        client_order_id: str | None = None,
    ) -> dict | None:
        """Place an order on Bybit."""
        params = {
            "category": self.category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
            "reduceOnly": reduce_only,
        }
        if price:
            params["price"] = price
        if stop_loss:
            params["stopLoss"] = stop_loss
        if take_profit:
            params["takeProfit"] = take_profit
        if client_order_id:
            params["orderLinkId"] = client_order_id

        response = await self._bybit_request_with_retry(
            "place_order",
            self.http_session.place_order,
            **params,
        )
        if response and response.get("result"):
            self.logger.info(f"{NEON_GREEN}Order placed: {response['result']}{RESET}")
            return response["result"]
        return None

    async def cancel_order(self, symbol: str, order_id: str) -> dict | None:
        """Cancel an order on Bybit."""
        response = await self._bybit_request_with_retry(
            "cancel_order",
            self.http_session.cancel_order,
            category=self.category,
            symbol=symbol,
            orderId=order_id,
        )
        if response and response.get("result"):
            self.logger.info(
                f"{NEON_YELLOW}Order cancelled: {response['result']}{RESET}",
            )
            return response["result"]
        return None

    async def cancel_all_orders(self, symbol: str) -> dict | None:
        """Cancel all open orders for a symbol."""
        response = await self._bybit_request_with_retry(
            "cancel_all_orders",
            self.http_session.cancel_all_orders,
            category=self.category,
            symbol=symbol,
        )
        if response and response.get("result"):
            self.logger.info(
                f"{NEON_YELLOW}All orders cancelled for {symbol}: {response['result']}{RESET}",
            )
            return response["result"]
        return None

    async def set_leverage(self, symbol: str, leverage: str) -> bool:
        """Set leverage for a symbol."""
        response = await self._bybit_request_with_retry(
            "set_leverage",
            self.http_session.set_leverage,
            category=self.category,
            symbol=symbol,
            buyLeverage=leverage,
            sellLeverage=leverage,
        )
        if response:
            self.logger.info(
                f"{NEON_GREEN}Leverage set to {leverage} for {symbol}{RESET}",
            )
            return True
        return False

    async def set_trading_stop(
        self,
        symbol: str,
        stop_loss: str | None = None,
        take_profit: str | None = None,
        trailing_stop: str | None = None,
        active_price: str | None = None,
        position_idx: int = 0,
        tp_trigger_by: str = "MarkPrice",
        sl_trigger_by: str = "MarkPrice",
    ) -> bool:
        """Set or amend stop loss, take profit, or trailing stop for an existing position."""
        params = {
            "category": self.category,
            "symbol": symbol,
            "positionIdx": position_idx,
            "tpTriggerBy": tp_trigger_by,
            "slTriggerBy": sl_trigger_by,
        }
        if stop_loss is not None:
            params["stopLoss"] = stop_loss
        if take_profit is not None:
            params["takeProfit"] = take_profit
        if trailing_stop is not None:
            params["trailingStop"] = trailing_stop
        if active_price is not None:
            params["activePrice"] = active_price

        response = await self._bybit_request_with_retry(
            "set_trading_stop",
            self.http_session.set_trading_stop,
            **params,
        )
        if response:
            self.logger.info(
                f"{NEON_GREEN}Trading stop updated for {symbol}: SL={stop_loss}, TP={take_profit}, Trailing={trailing_stop}{RESET}",
            )
            return True
        return False

    async def get_wallet_balance(self) -> Decimal | None:
        """Get current account balance."""
        response = await self._bybit_request_with_retry(
            "get_wallet_balance",
            self.http_session.get_wallet_balance,
            accountType="UNIFIED",
        )
        if response and response["result"] and response["result"]["list"]:
            for coin_data in response["result"]["list"][0]["coin"]:
                if coin_data["coin"] == "USDT":
                    return Decimal(coin_data["walletBalance"])
        self.logger.warning(f"{NEON_YELLOW}Could not fetch wallet balance.{RESET}")
        return None

    async def get_positions(self) -> list[dict[str, Any]]:
        """Get all open positions."""
        response = await self._bybit_request_with_retry(
            "get_positions",
            self.http_session.get_positions,
            category=self.category,
            symbol=self.symbol,
        )
        if response and response["result"] and response["result"]["list"]:
            return response["result"]["list"]
        return []

    async def start_public_ws(
        self,
        symbol: str,
        orderbook_depth: int,
        kline_interval: str,
        ticker_callback: callable,
        orderbook_callback: callable,
        kline_callback: callable,
    ):
        """Starts public WebSocket streams."""
        self.ws_public = WebSocket(channel_type=self.category, testnet=self.testnet)

        async def _ws_callback_wrapper(raw_message):
            try:
                message = json.loads(raw_message)
                topic = message.get("topic")
                if topic and "kline" in topic:
                    await kline_callback(message)
                elif topic and "ticker" in topic:
                    await ticker_callback(message)
                elif topic and "orderbook" in topic:
                    await orderbook_callback(message)
            except json.JSONDecodeError:
                self.logger.error(
                    f"{NEON_RED}Failed to decode WS message: {raw_message}{RESET}",
                )
            except Exception as e:
                self.logger.error(
                    f"{NEON_RED}Error in public WS callback: {e} | Message: {raw_message[:100]}{RESET}",
                    exc_info=True,
                )

        self.ws_public.kline_stream(
            interval=kline_interval,
            symbol=symbol,
            callback=_ws_callback_wrapper,
        )
        self.ws_public.ticker_stream(symbol=symbol, callback=_ws_callback_wrapper)
        self.ws_public.orderbook_stream(
            depth=orderbook_depth,
            symbol=symbol,
            callback=_ws_callback_wrapper,
        )

        self.ws_tasks.append(
            asyncio.create_task(
                self._monitor_ws_connection(self.ws_public, "Public WS"),
            ),
        )
        self.logger.info(f"{NEON_BLUE}Public WebSocket for {symbol} started.{RESET}")

    async def start_private_ws(
        self,
        position_callback: callable,
        order_callback: callable,
        execution_callback: callable,
        wallet_callback: callable,
    ):
        """Starts private WebSocket streams."""
        self.ws_private = WebSocket(
            channel_type="private",
            testnet=self.testnet,
            api_key=self.api_key,
            api_secret=self.api_secret,
        )

        async def _ws_callback_wrapper(raw_message):
            try:
                message = json.loads(raw_message)
                topic = message.get("topic")
                if topic == "position":
                    await position_callback(message)
                elif topic == "order":
                    await order_callback(message)
                elif topic == "execution":
                    await execution_callback(message)
                elif topic == "wallet":
                    await wallet_callback(message)
            except json.JSONDecodeError:
                self.logger.error(
                    f"{NEON_RED}Failed to decode WS message: {raw_message}{RESET}",
                )
            except Exception as e:
                self.logger.error(
                    f"{NEON_RED}Error in private WS callback: {e} | Message: {raw_message[:100]}{RESET}",
                    exc_info=True,
                )

        self.ws_private.position_stream(callback=_ws_callback_wrapper)
        self.ws_private.order_stream(callback=_ws_callback_wrapper)
        self.ws_private.execution_stream(callback=_ws_callback_wrapper)
        self.ws_private.wallet_stream(callback=_ws_callback_wrapper)

        self.ws_tasks.append(
            asyncio.create_task(
                self._monitor_ws_connection(self.ws_private, "Private WS"),
            ),
        )
        self.logger.info(f"{NEON_BLUE}Private WebSocket started.{RESET}")

    async def _monitor_ws_connection(self, ws_client: WebSocket, name: str):
        """Monitors WebSocket connection and logs status."""
        while True:
            await asyncio.sleep(5)
            if not ws_client.is_connected():
                self.logger.warning(
                    f"{NEON_YELLOW}{name} is not connected. pybit will attempt automatic reconnection.{RESET}",
                )
            else:
                self.logger.debug(f"{name} is connected.")

    async def stop_ws(self):
        """Stops all WebSocket connections."""
        for task in self.ws_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self.ws_public:
            await self.ws_public.close()
        if self.ws_private:
            await self.ws_private.close()
        self.logger.info(f"{NEON_BLUE}All WebSockets stopped.{RESET}")


class PrecisionManager:
    """Manages decimal precision for trading operations based on Bybit's instrument info."""

    def __init__(self, bybit_client: BybitClient, logger: logging.Logger):
        self.bybit_client = bybit_client
        self.logger = logger
        self.instruments_info: dict[str, Any] = {}
        self.initialized = False

    async def load_instrument_info(self, symbol: str):
        """Load instrument specifications from Bybit."""
        response = await self.bybit_client._bybit_request_with_retry(
            "get_instruments_info",
            self.bybit_client.http_session.get_instruments_info,
            category=self.bybit_client.category,
            symbol=symbol,
        )
        if response and response["result"] and response["result"]["list"]:
            spec = response["result"]["list"][0]
            price_filter = spec["priceFilter"]
            lot_size_filter = spec["lotSizeFilter"]

            self.instruments_info[symbol] = {
                "price_precision_str": price_filter["tickSize"],
                "price_precision_decimal": Decimal(price_filter["tickSize"]),
                "qty_precision_str": lot_size_filter["qtyStep"],
                "qty_precision_decimal": Decimal(lot_size_filter["qtyStep"]),
                "min_qty": Decimal(lot_size_filter["minOrderQty"]),
                "max_qty": Decimal(lot_size_filter["maxOrderQty"]),
                "min_notional": Decimal(lot_size_filter.get("minNotionalValue", "0")),
            }
            self.logger.info(
                f"{NEON_GREEN}Instrument specs loaded for {symbol}: Price tick={self.instruments_info[symbol]['price_precision_decimal']}, Qty step={self.instruments_info[symbol]['qty_precision_decimal']}{RESET}",
            )
            self.initialized = True
        else:
            self.logger.error(
                f"{NEON_RED}Failed to load instrument specs for {symbol}. Trading might be inaccurate.{RESET}",
            )

    def _get_specs(self, symbol: str) -> dict | None:
        """Helper to get specs for a symbol."""
        specs = self.instruments_info.get(symbol)
        if not specs and self.initialized:
            self.logger.warning(
                f"{NEON_YELLOW}Instrument specs not found for {symbol}. Using generic Decimal precision.{RESET}",
            )
            return None
        return specs

    def round_price(self, price: Decimal, symbol: str) -> Decimal:
        """Round price to correct tick size."""
        specs = self._get_specs(symbol)
        if specs:
            return price.quantize(
                specs["price_precision_decimal"],
                rounding=ROUND_HALF_EVEN,
            )
        return price.quantize(Decimal("0.00001"), rounding=ROUND_HALF_EVEN)

    def round_qty(self, qty: Decimal, symbol: str) -> Decimal:
        """Round quantity to correct step size."""
        specs = self._get_specs(symbol)
        if specs:
            return qty.quantize(specs["qty_precision_decimal"], rounding=ROUND_DOWN)
        return qty.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)

    def get_min_qty(self, symbol: str) -> Decimal:
        """Get minimum order quantity."""
        specs = self._get_specs(symbol)
        return specs["min_qty"] if specs else Decimal("0.00001")

    def get_max_qty(self, symbol: str) -> Decimal:
        """Get maximum order quantity."""
        specs = self._get_specs(symbol)
        return specs["max_qty"] if specs else Decimal("1000000")

    def get_min_notional(self, symbol: str) -> Decimal:
        """Get minimum notional value (order cost)."""
        specs = self._get_specs(symbol)
        return specs["min_notional"] if specs else Decimal("5")


class IndicatorCalculator:
    """Calculates various technical indicators."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def _safe_series_op(self, series: pd.Series, op_name: str) -> pd.Series:
        """Safely handle series operations that might result in NaN or inf."""
        if series.empty:
            self.logger.debug(f"Input series for {op_name} is empty.")
            return pd.Series(np.nan, index=[])
        series = pd.to_numeric(series, errors="coerce")
        series.replace([np.inf, -np.inf], np.nan, inplace=True)
        return series

    def calculate_true_range(self, df: pd.DataFrame) -> pd.Series:
        """Calculate True Range (TR)."""
        if len(df) < MIN_DATA_POINTS_TR:
            return pd.Series(np.nan, index=df.index)
        high_low = self._safe_series_op(df["high"] - df["low"], "TR_high_low")
        high_prev_close = self._safe_series_op(
            (df["high"] - df["close"].shift()).abs(),
            "TR_high_prev_close",
        )
        low_prev_close = self._safe_series_op(
            (df["low"] - df["close"].shift()).abs(),
            "TR_low_prev_close",
        )
        return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(
            axis=1,
        )

    def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
        """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
        if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER:
            return pd.Series(np.nan, index=series.index)

        series = self._safe_series_op(series, "SuperSmoother_input").dropna()
        if len(series) < MIN_DATA_POINTS_SMOOTHER:
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
        return filt.reindex(series.index)

    def calculate_ehlers_supertrend(
        self,
        df: pd.DataFrame,
        period: int,
        multiplier: float,
    ) -> pd.DataFrame | None:
        """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
        if len(df) < period * 3:
            self.logger.debug(
                f"Not enough data for Ehlers SuperTrend (period={period}). Need at least {period * 3} bars.",
            )
            return None

        df_copy = df.copy()

        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        smoothed_price = self.calculate_super_smoother(hl2, period)

        tr = self.calculate_true_range(df_copy)
        smoothed_atr = self.calculate_super_smoother(tr, period)

        df_copy["smoothed_price"] = smoothed_price
        df_copy["smoothed_atr"] = smoothed_atr

        df_copy.dropna(subset=["smoothed_price", "smoothed_atr"], inplace=True)
        if df_copy.empty:
            self.logger.debug(
                "Ehlers SuperTrend: DataFrame empty after smoothing. Returning None.",
            )
            return None

        upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
        lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]

        direction = pd.Series(0, index=df_copy.index, dtype=int)
        supertrend = pd.Series(np.nan, index=df_copy.index)

        if df_copy.empty:
            return None

        first_valid_idx = df_copy.index[0]
        supertrend.loc[first_valid_idx] = (
            lower_band.loc[first_valid_idx]
            if df_copy["close"].loc[first_valid_idx] > lower_band.loc[first_valid_idx]
            else upper_band.loc[first_valid_idx]
        )
        direction.loc[first_valid_idx] = (
            1
            if df_copy["close"].loc[first_valid_idx] > supertrend.loc[first_valid_idx]
            else -1
        )

        for i in range(1, len(df_copy)):
            current_idx = df_copy.index[i]
            prev_idx = df_copy.index[i - 1]

            prev_direction = direction.loc[prev_idx]
            prev_supertrend = supertrend.loc[prev_idx]
            curr_close = df_copy["close"].loc[current_idx]

            if prev_direction == 1:
                supertrend.loc[current_idx] = max(
                    lower_band.loc[current_idx],
                    prev_supertrend,
                )
                if curr_close < supertrend.loc[current_idx]:
                    direction.loc[current_idx] = -1
            else:
                supertrend.loc[current_idx] = min(
                    upper_band.loc[current_idx],
                    prev_supertrend,
                )
                if curr_close > supertrend.loc[current_idx]:
                    direction.loc[current_idx] = 1

            if pd.isna(supertrend.loc[current_idx]):
                supertrend.loc[current_idx] = (
                    lower_band.loc[current_idx]
                    if curr_close > lower_band.loc[current_idx]
                    else upper_band.loc[current_idx]
                )

        result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
        return result.reindex(df.index)

    def calculate_macd(
        self,
        df: pd.DataFrame,
        fast_period: int,
        slow_period: int,
        signal_period: int,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Moving Average Convergence Divergence (MACD)."""
        if len(df) < slow_period + signal_period:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        macd_result = ta.macd(
            df["close"],
            fast=fast_period,
            slow=slow_period,
            signal=signal_period,
        )
        if macd_result.empty:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        macd_line = self._safe_series_op(
            macd_result[f"MACD_{fast_period}_{slow_period}_{signal_period}"],
            "MACD_Line",
        )
        signal_line = self._safe_series_op(
            macd_result[f"MACDs_{fast_period}_{slow_period}_{signal_period}"],
            "MACD_Signal",
        )
        histogram = self._safe_series_op(
            macd_result[f"MACDh_{fast_period}_{slow_period}_{signal_period}"],
            "MACD_Hist",
        )

        return macd_line, signal_line, histogram

    def calculate_rsi(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(df) <= period:
            return pd.Series(np.nan, index=df.index)
        rsi = ta.rsi(df["close"], length=period)
        return self._safe_series_op(rsi, "RSI")

    def calculate_stoch_rsi(
        self,
        df: pd.DataFrame,
        period: int,
        k_period: int,
        d_period: int,
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI."""
        if len(df) <= period:
            return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)
        stochrsi = ta.stochrsi(
            df["close"],
            length=period,
            rsi_length=period,
            k=k_period,
            d=d_period,
        )

        stoch_rsi_k = self._safe_series_op(
            stochrsi[f"STOCHRSIk_{period}_{period}_{k_period}_{d_period}"],
            "StochRSI_K",
        )
        stoch_rsi_d = self._safe_series_op(
            stochrsi[f"STOCHRSId_{period}_{period}_{k_period}_{d_period}"],
            "StochRSI_D",
        )

        return stoch_rsi_k, stoch_rsi_d

    def calculate_adx(
        self,
        df: pd.DataFrame,
        period: int,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Average Directional Index (ADX)."""
        if len(df) < period * 2:
            return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)

        adx_result = ta.adx(df["high"], df["low"], df["close"], length=period)

        adx_val = self._safe_series_op(adx_result[f"ADX_{period}"], "ADX")
        plus_di = self._safe_series_op(adx_result[f"DMP_{period}"], "PlusDI")
        minus_di = self._safe_series_op(adx_result[f"DMN_{period}"], "MinusDI")

        return adx_val, plus_di, minus_di

    def calculate_bollinger_bands(
        self,
        df: pd.DataFrame,
        period: int,
        std_dev: float,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        if len(df) < period:
            return (
                pd.Series(np.nan, index=df.index),
                pd.Series(np.nan, index=df.index),
                pd.Series(np.nan, index=df.index),
            )
        bbands = ta.bbands(df["close"], length=period, std=std_dev)

        upper_band = self._safe_series_op(bbands[f"BBU_{period}_{std_dev}"], "BB_Upper")
        middle_band = self._safe_series_op(
            bbands[f"BBM_{period}_{std_dev}"],
            "BB_Middle",
        )
        lower_band = self._safe_series_op(bbands[f"BBL_{period}_{std_dev}"], "BB_Lower")

        return upper_band, middle_band, lower_band

    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Calculate Volume Weighted Average Price (VWAP)."""
        if df.empty:
            return pd.Series(np.nan, index=df.index)

        vwap = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
        return self._safe_series_op(vwap, "VWAP")

    def calculate_cci(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Commodity Channel Index (CCI)."""
        if len(df) < period:
            return pd.Series(np.nan, index=df.index)
        cci = ta.cci(df["high"], df["low"], df["close"], length=period)
        return self._safe_series_op(cci, "CCI")

    def calculate_williams_r(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Williams %R."""
        if len(df) < period:
            return pd.Series(np.nan, index=df.index)
        wr = ta.willr(df["high"], df["low"], df["close"], length=period)
        return self._safe_series_op(wr, "WR")

    def calculate_mfi(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Money Flow Index (MFI)."""
        if len(df) <= period:
            return pd.Series(np.nan, index=df.index)
        mfi = ta.mfi(df["high"], df["low"], df["close"], df["volume"], length=period)
        return self._safe_series_op(mfi, "MFI")

    def calculate_obv(
        self,
        df: pd.DataFrame,
        ema_period: int,
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate On-Balance Volume (OBV) and its EMA."""
        if len(df) < MIN_DATA_POINTS_OBV:
            return pd.Series(np.nan), pd.Series(np.nan)

        obv = ta.obv(df["close"], df["volume"])
        obv_ema = ta.ema(obv, length=ema_period)

        return self._safe_series_op(obv, "OBV"), self._safe_series_op(
            obv_ema,
            "OBV_EMA",
        )

    def calculate_cmf(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Chaikin Money Flow (CMF)."""
        if len(df) < period:
            return pd.Series(np.nan)

        cmf = ta.cmf(df["high"], df["low"], df["close"], df["volume"], length=period)
        return self._safe_series_op(cmf, "CMF")

    def calculate_ichimoku_custom(
        self,
        df: pd.DataFrame,
        tenkan_period: int,
        kijun_period: int,
        senkou_span_b_period: int,
        chikou_span_offset: int,
    ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Ichimoku Cloud components manually."""
        # Tenkan-sen (Conversion Line): (Highest High + Lowest Low) / 2 over tenkan_period
        high_tenkan = df["high"].rolling(window=tenkan_period).max()
        low_tenkan = df["low"].rolling(window=tenkan_period).min()
        tenkan_sen = (high_tenkan + low_tenkan) / 2

        # Kijun-sen (Base Line): (Highest High + Lowest Low) / 2 over kijun_period
        high_kijun = df["high"].rolling(window=kijun_period).max()
        low_kijun = df["low"].rolling(window=kijun_period).min()
        kijun_sen = (high_kijun + low_kijun) / 2

        # Senkou Span A (Leading Span A): (Tenkan-sen + Kijun-sen) / 2, plotted kijun_period periods ahead.
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)

        # Senkou Span B (Leading Span B): (Highest High + Lowest Low) / 2 over senkou_span_b_period, plotted kijun_period periods ahead.
        high_senkou_b = df["high"].rolling(window=senkou_span_b_period).max()
        low_senkou_b = df["low"].rolling(window=senkou_span_b_period).min()
        senkou_span_b = ((high_senkou_b + low_senkou_b) / 2).shift(kijun_period)

        # Chikou Span (Lagging Span): Closing price plotted kijun_period periods behind.
        chikou_span = df["close"].shift(-chikou_span_offset)  # Shift backwards

        return (
            self._safe_series_op(tenkan_sen, "Tenkan_Sen"),
            self._safe_series_op(kijun_sen, "Kijun_Sen"),
            self._safe_series_op(senkou_span_a, "Senkou_Span_A"),
            self._safe_series_op(senkou_span_b, "Senkou_Span_B"),
            self._safe_series_op(chikou_span, "Chikou_Span"),
        )

    def calculate_psar(
        self,
        df: pd.DataFrame,
        acceleration: float,
        max_acceleration: float,
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR."""
        if len(df) < MIN_DATA_POINTS_PSAR:
            return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)

        try:
            psar_result = ta.psar(
                df["high"],
                df["low"],
                df["close"],
                af0=acceleration,
                af=acceleration,
                max_af=max_acceleration,
            )
            if not isinstance(psar_result, pd.DataFrame):
                self.logger.error(
                    f"{NEON_RED}pandas_ta.psar did not return a DataFrame. Type: {type(psar_result)}{RESET}",
                )
                return pd.Series(np.nan, index=df.index), pd.Series(
                    np.nan,
                    index=df.index,
                )
            self.logger.debug(f"PSAR result columns: {psar_result.columns.tolist()}")
        except Exception as e:
            self.logger.error(f"{NEON_RED}Error calling pandas_ta.psar: {e}{RESET}")
            return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)

        # Assuming standard pandas_ta PSAR column names
        psar_val_col = f"PSARr_{acceleration}_{max_acceleration}"  # Reversal PSAR value
        psar_long_col = f"PSARl_{acceleration}_{max_acceleration}"
        psar_short_col = f"PSARs_{acceleration}_{max_acceleration}"

        if not all(
            col in psar_result.columns
            for col in [psar_val_col, psar_long_col, psar_short_col]
        ):
            self.logger.error(
                f"{NEON_RED}Missing expected PSAR columns in result: {psar_result.columns.tolist()}. Expected: {psar_val_col}, {psar_long_col}, {psar_short_col}{RESET}",
            )
            return pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)

        psar_val = self._safe_series_op(psar_result[psar_val_col], "PSAR_Val")
        psar_long = psar_result[psar_long_col]
        psar_short = psar_result[psar_short_col]

        psar_dir = pd.Series(0, index=df.index, dtype=int)
        psar_dir[df["close"] > psar_long.fillna(0)] = 1
        psar_dir[df["close"] < psar_short.fillna(0)] = -1
        psar_dir.mask(psar_dir == 0, psar_dir.shift(1), inplace=True)
        psar_dir.fillna(0, inplace=True)

        return psar_val, psar_dir


class TradingAnalyzer:
    """Analyzes trading data and generates signals with MTF and Ehlers SuperTrend."""

    def __init__(
        self,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
        indicator_calculator: IndicatorCalculator,
    ):
        """Initializes the TradingAnalyzer."""
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.indicator_calculator = indicator_calculator
        self.df: pd.DataFrame = pd.DataFrame()
        self.indicator_values: dict[str, float | str | Decimal] = {}
        self.fib_levels: dict[str, Decimal] = {}
        self.weights = config["weight_sets"]["default_scalping"]
        self.indicator_settings = config["indicator_settings"]

    def update_data(self, new_df: pd.DataFrame):
        """Updates the internal DataFrame and recalculates indicators."""
        if new_df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}TradingAnalyzer received an empty DataFrame. Skipping indicator recalculation.{RESET}",
            )
            return

        self.df = new_df.copy()
        self._calculate_all_indicators()
        if self.config["indicators"].get("fibonacci_levels", False):
            self.calculate_fibonacci_levels()

    def _safe_calculate(
        self,
        func: callable,
        name: str,
        min_data_points: int = 0,
        *args,
        **kwargs,
    ) -> Any | None:
        """Safely calculate indicators and log errors, with min_data_points check."""
        if self.df.empty:
            self.logger.debug(f"Skipping indicator '{name}': DataFrame is empty.")
            return None
        if len(self.df) < min_data_points:
            self.logger.debug(
                f"Skipping indicator '{name}': Not enough data. Need {min_data_points}, have {len(self.df)}.",
            )
            return None
        try:
            result = func(*args, **kwargs)
            if (
                result is None
                or (isinstance(result, pd.Series) and result.empty)
                or (isinstance(result, pd.DataFrame) and result.empty)
                or (
                    isinstance(result, tuple)
                    and all(
                        r is None
                        or (isinstance(r, pd.Series) and r.empty)
                        or (isinstance(r, pd.DataFrame) and r.empty)
                        for r in result
                    )
                )
            ):
                self.logger.warning(
                    f"{NEON_YELLOW}Indicator '{name}' returned empty or None after calculation. Not enough valid data?{RESET}",
                )
                return None
            return result
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}Error calculating indicator '{name}': {e}{RESET}",
                exc_info=True,
            )
            return None

    def _calculate_all_indicators(self) -> None:
        """Calculate all enabled technical indicators, including Ehlers SuperTrend."""
        self.logger.debug("Calculating technical indicators...")
        cfg = self.config
        isd = self.indicator_settings

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}Cannot calculate indicators: DataFrame is empty.{RESET}",
            )
            return

        if cfg["indicators"].get("sma_10", False):
            self.df["SMA_10"] = self._safe_calculate(
                lambda: ta.sma(self.df["close"], length=isd["sma_short_period"]),
                "SMA_10",
                min_data_points=isd["sma_short_period"],
            )
            if self.df["SMA_10"] is not None and not self.df["SMA_10"].empty:
                self.indicator_values["SMA_10"] = self.df["SMA_10"].iloc[-1]
        if cfg["indicators"].get("sma_trend_filter", False):
            self.df["SMA_Long"] = self._safe_calculate(
                lambda: ta.sma(self.df["close"], length=isd["sma_long_period"]),
                "SMA_Long",
                min_data_points=isd["sma_long_period"],
            )
            if self.df["SMA_Long"] is not None and not self.df["SMA_Long"].empty:
                self.indicator_values["SMA_Long"] = self.df["SMA_Long"].iloc[-1]

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
                self.indicator_values["EMA_Short"] = self.df["EMA_Short"].iloc[-1]
            if self.df["EMA_Long"] is not None and not self.df["EMA_Long"].empty:
                self.indicator_values["EMA_Long"] = self.df["EMA_Long"].iloc[-1]

        self.df["TR"] = self._safe_calculate(
            self.indicator_calculator.calculate_true_range,
            "TR",
            min_data_points=2,
            df=self.df,
        )
        self.df["ATR"] = self._safe_calculate(
            lambda: ta.atr(
                self.df["high"],
                self.df["low"],
                self.df["close"],
                length=isd["atr_period"],
            ),
            "ATR",
            min_data_points=isd["atr_period"],
        )
        if self.df["ATR"] is not None and not self.df["ATR"].empty:
            self.indicator_values["ATR"] = self.df["ATR"].iloc[-1]

        if cfg["indicators"].get("rsi", False):
            self.df["RSI"] = self._safe_calculate(
                self.indicator_calculator.calculate_rsi,
                "RSI",
                min_data_points=isd["rsi_period"] + 1,
                df=self.df,
                period=isd["rsi_period"],
            )
            if self.df["RSI"] is not None and not self.df["RSI"].empty:
                self.indicator_values["RSI"] = self.df["RSI"].iloc[-1]

        if cfg["indicators"].get("stoch_rsi", False):
            stoch_rsi_k, stoch_rsi_d = self._safe_calculate(
                self.indicator_calculator.calculate_stoch_rsi,
                "StochRSI",
                min_data_points=isd["stoch_rsi_period"]
                + isd["stoch_d_period"]
                + isd["stoch_k_period"],
                df=self.df,
                period=isd["stoch_rsi_period"],
                k_period=isd["stoch_k_period"],
                d_period=isd["stoch_d_period"],
            )
            if stoch_rsi_k is not None and not stoch_rsi_k.empty:
                self.df["StochRSI_K"] = stoch_rsi_k
                self.indicator_values["StochRSI_K"] = stoch_rsi_k.iloc[-1]
            if stoch_rsi_d is not None and not stoch_rsi_d.empty:
                self.df["StochRSI_D"] = stoch_rsi_d
                self.indicator_values["StochRSI_D"] = stoch_rsi_d.iloc[-1]

        if cfg["indicators"].get("bollinger_bands", False):
            bb_upper, bb_middle, bb_lower = self._safe_calculate(
                self.indicator_calculator.calculate_bollinger_bands,
                "BollingerBands",
                min_data_points=isd["bollinger_bands_period"],
                df=self.df,
                period=isd["bollinger_bands_period"],
                std_dev=isd["bollinger_bands_std_dev"],
            )
            if bb_upper is not None and not bb_upper.empty:
                self.df["BB_Upper"] = bb_upper
                self.indicator_values["BB_Upper"] = bb_upper.iloc[-1]
            if bb_middle is not None and not bb_middle.empty:
                self.df["BB_Middle"] = bb_middle
                self.indicator_values["BB_Middle"] = bb_middle.iloc[-1]
            if bb_lower is not None and not bb_lower.empty:
                self.df["BB_Lower"] = bb_lower
                self.indicator_values["BB_Lower"] = bb_lower.iloc[-1]

        if cfg["indicators"].get("cci", False):
            self.df["CCI"] = self._safe_calculate(
                self.indicator_calculator.calculate_cci,
                "CCI",
                min_data_points=isd["cci_period"],
                df=self.df,
                period=isd["cci_period"],
            )
            if self.df["CCI"] is not None and not self.df["CCI"].empty:
                self.indicator_values["CCI"] = self.df["CCI"].iloc[-1]

        if cfg["indicators"].get("wr", False):
            self.df["WR"] = self._safe_calculate(
                self.indicator_calculator.calculate_williams_r,
                "WR",
                min_data_points=isd["williams_r_period"],
                df=self.df,
                period=isd["williams_r_period"],
            )
            if self.df["WR"] is not None and not self.df["WR"].empty:
                self.indicator_values["WR"] = self.df["WR"].iloc[-1]

        if cfg["indicators"].get("mfi", False):
            self.df["MFI"] = self._safe_calculate(
                self.indicator_calculator.calculate_mfi,
                "MFI",
                min_data_points=isd["mfi_period"] + 1,
                df=self.df,
                period=isd["mfi_period"],
            )
            if self.df["MFI"] is not None and not self.df["MFI"].empty:
                self.indicator_values["MFI"] = self.df["MFI"].iloc[-1]

        if cfg["indicators"].get("obv", False):
            obv_val, obv_ema = self._safe_calculate(
                self.indicator_calculator.calculate_obv,
                "OBV",
                min_data_points=isd["obv_ema_period"],
                df=self.df,
                ema_period=isd["obv_ema_period"],
            )
            if obv_val is not None and not obv_val.empty:
                self.df["OBV"] = obv_val
                self.indicator_values["OBV"] = obv_val.iloc[-1]
            if obv_ema is not None and not obv_ema.empty:
                self.df["OBV_EMA"] = obv_ema
                self.indicator_values["OBV_EMA"] = obv_ema.iloc[-1]

        if cfg["indicators"].get("cmf", False):
            cmf_val = self._safe_calculate(
                self.indicator_calculator.calculate_cmf,
                "CMF",
                min_data_points=isd["cmf_period"],
                df=self.df,
                period=isd["cmf_period"],
            )
            if cmf_val is not None and not cmf_val.empty:
                self.df["CMF"] = cmf_val
                self.indicator_values["CMF"] = cmf_val.iloc[-1]

        if cfg["indicators"].get("ichimoku_cloud", False):
            tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span = (
                self._safe_calculate(
                    self.indicator_calculator.calculate_ichimoku_custom,
                    "IchimokuCloud",
                    min_data_points=max(
                        isd["ichimoku_tenkan_period"],
                        isd["ichimoku_kijun_period"],
                        isd["ichimoku_senkou_span_b_period"],
                    )
                    + isd["ichimoku_chikou_span_offset"],
                    df=self.df,
                    tenkan_period=isd["ichimoku_tenkan_period"],
                    kijun_period=isd["ichimoku_kijun_period"],
                    senkou_span_b_period=isd["ichimoku_senkou_span_b_period"],
                    chikou_span_offset=isd["ichimoku_chikou_span_offset"],
                )
            )
            if tenkan_sen is not None and not tenkan_sen.empty:
                self.df["Tenkan_Sen"] = tenkan_sen
                self.indicator_values["Tenkan_Sen"] = tenkan_sen.iloc[-1]
            if kijun_sen is not None and not kijun_sen.empty:
                self.df["Kijun_Sen"] = kijun_sen
                self.indicator_values["Kijun_Sen"] = kijun_sen.iloc[-1]
            if senkou_span_a is not None and not senkou_span_a.empty:
                self.df["Senkou_Span_A"] = senkou_span_a
                self.indicator_values["Senkou_Span_A"] = senkou_span_a.iloc[-1]
            if senkou_span_b is not None and not senkou_span_b.empty:
                self.df["Senkou_Span_B"] = senkou_span_b
                self.indicator_values["Senkou_Span_B"] = senkou_span_b.iloc[-1]
            if chikou_span is not None and not chikou_span.empty:
                self.df["Chikou_Span"] = chikou_span
                self.indicator_values["Chikou_Span"] = chikou_span.fillna(0).iloc[-1]

        if cfg["indicators"].get("psar", False):
            psar_result = self._safe_calculate(
                self.indicator_calculator.calculate_psar,
                "PSAR",
                min_data_points=MIN_DATA_POINTS_PSAR,
                df=self.df,
                acceleration=isd["psar_acceleration"],
                max_acceleration=isd["psar_max_acceleration"],
            )
            if psar_result:
                psar_val, psar_dir = psar_result
                if psar_val is not None and not psar_val.empty:
                    self.df["PSAR_Val"] = psar_val
                    self.indicator_values["PSAR_Val"] = psar_val.iloc[-1]
                if psar_dir is not None and not psar_dir.empty:
                    self.df["PSAR_Dir"] = psar_dir
                    self.indicator_values["PSAR_Dir"] = psar_dir.iloc[-1]
            else:
                self.logger.warning(
                    f"{NEON_YELLOW}PSAR calculation failed, skipping assignments.{RESET}",
                )

        if cfg["indicators"].get("vwap", False):
            self.df["VWAP"] = self._safe_calculate(
                self.indicator_calculator.calculate_vwap,
                "VWAP",
                min_data_points=1,
                df=self.df,
            )
            if self.df["VWAP"] is not None and not self.df["VWAP"].empty:
                self.indicator_values["VWAP"] = self.df["VWAP"].iloc[-1]

        if cfg["indicators"].get("ehlers_supertrend", False):
            st_fast_result = self._safe_calculate(
                self.indicator_calculator.calculate_ehlers_supertrend,
                "EhlersSuperTrendFast",
                min_data_points=isd["ehlers_fast_period"] * 3,
                df=self.df,
                period=isd["ehlers_fast_period"],
                multiplier=isd["ehlers_fast_multiplier"],
            )
            if st_fast_result is not None and not st_fast_result.empty:
                self.df["st_fast_dir"] = st_fast_result["direction"]
                self.df["st_fast_val"] = st_fast_result["supertrend"]
                self.indicator_values["ST_Fast_Dir"] = st_fast_result["direction"].iloc[
                    -1
                ]
                self.indicator_values["ST_Fast_Val"] = st_fast_result[
                    "supertrend"
                ].iloc[-1]

            st_slow_result = self._safe_calculate(
                self.indicator_calculator.calculate_ehlers_supertrend,
                "EhlersSuperTrendSlow",
                min_data_points=isd["ehlers_slow_period"] * 3,
                df=self.df,
                period=isd["ehlers_slow_period"],
                multiplier=isd["ehlers_slow_multiplier"],
            )
            if st_slow_result is not None and not st_slow_result.empty:
                self.df["st_slow_dir"] = st_slow_result["direction"]
                self.df["st_slow_val"] = st_slow_result["supertrend"]
                self.indicator_values["ST_Slow_Dir"] = st_slow_result["direction"].iloc[
                    -1
                ]
                self.indicator_values["ST_Slow_Val"] = st_slow_result[
                    "supertrend"
                ].iloc[-1]

        if cfg["indicators"].get("macd", False):
            macd_line, signal_line, histogram = self._safe_calculate(
                self.indicator_calculator.calculate_macd,
                "MACD",
                min_data_points=isd["macd_slow_period"] + isd["macd_signal_period"],
                df=self.df,
                fast_period=isd["macd_fast_period"],
                slow_period=isd["macd_slow_period"],
                signal_period=isd["macd_signal_period"],
            )
            if macd_line is not None and not macd_line.empty:
                self.df["MACD_Line"] = macd_line
                self.indicator_values["MACD_Line"] = macd_line.iloc[-1]
            if signal_line is not None and not signal_line.empty:
                self.df["MACD_Signal"] = signal_line
                self.indicator_values["MACD_Signal"] = signal_line.iloc[-1]
            if histogram is not None and not histogram.empty:
                self.df["MACD_Hist"] = histogram
                self.indicator_values["MACD_Hist"] = histogram.iloc[-1]

        if cfg["indicators"].get("adx", False):
            adx_val, plus_di, minus_di = self._safe_calculate(
                self.indicator_calculator.calculate_adx,
                "ADX",
                min_data_points=isd["adx_period"] * 2,
                df=self.df,
                period=isd["adx_period"],
            )
            if adx_val is not None and not adx_val.empty:
                self.df["ADX"] = adx_val
                self.indicator_values["ADX"] = adx_val.iloc[-1]
            if plus_di is not None and not plus_di.empty:
                self.df["PlusDI"] = plus_di
                self.indicator_values["PlusDI"] = plus_di.iloc[-1]
            if minus_di is not None and not minus_di.empty:
                self.df["MinusDI"] = minus_di
                self.indicator_values["MinusDI"] = minus_di.iloc[-1]

        initial_len = len(self.df)

        for col in self.df.columns:
            if col not in ["open", "high", "low", "close", "volume", "turnover"]:
                self.df[col].fillna(method="ffill", inplace=True)
                self.df[col].fillna(0, inplace=True)

        if len(self.df) < initial_len:
            self.logger.debug(
                f"Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations.",
            )

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}DataFrame is empty after calculating all indicators and dropping NaNs.{RESET}",
            )
        else:
            self.logger.debug(
                f"Indicators calculated. Final DataFrame size: {len(self.df)}",
            )

    def calculate_fibonacci_levels(self) -> None:
        """Calculate Fibonacci retracement levels based on a recent high-low swing."""
        window = self.config["indicator_settings"]["fibonacci_window"]
        if len(self.df) < window:
            self.logger.warning(
                f"{NEON_YELLOW}Not enough data for Fibonacci levels (need {window} bars).{RESET}",
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
                Decimal("0.00001"),
                rounding=ROUND_DOWN,
            ),
            "38.2%": (decimal_high - Decimal("0.382") * decimal_diff).quantize(
                Decimal("0.00001"),
                rounding=ROUND_DOWN,
            ),
            "50.0%": (decimal_high - Decimal("0.500") * decimal_diff).quantize(
                Decimal("0.00001"),
                rounding=ROUND_DOWN,
            ),
            "61.8%": (decimal_high - Decimal("0.618") * decimal_diff).quantize(
                Decimal("0.00001"),
                rounding=ROUND_DOWN,
            ),
            "78.6%": (decimal_high - Decimal("0.786") * decimal_diff).quantize(
                Decimal("0.00001"),
                rounding=ROUND_DOWN,
            ),
            "100.0%": decimal_low,
        }
        self.logger.debug(f"Calculated Fibonacci levels: {self.fib_levels}")

    def _get_indicator_value(self, key: str, default: Any = np.nan) -> Any:
        """Safely retrieve an indicator value."""
        return self.indicator_values.get(key, default)

    async def _check_orderbook(
        self,
        current_price: Decimal,
        orderbook_manager: AdvancedOrderbookManager,
    ) -> float:
        """Analyze orderbook imbalance."""
        best_bid, best_ask = await orderbook_manager.get_best_bid_ask()
        if best_bid is None or best_ask is None:
            self.logger.warning(
                f"{NEON_YELLOW}Orderbook data not available for imbalance check.{RESET}",
            )
            return 0.0

        depth_limit = self.config["orderbook_limit"]
        bids, asks = await orderbook_manager.get_depth(depth_limit)

        bid_volume = sum(Decimal(str(b.quantity)) for b in bids)
        ask_volume = sum(Decimal(str(a.quantity)) for a in asks)

        if bid_volume + ask_volume == 0:
            return 0.0

        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        self.logger.debug(
            f"Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})",
        )
        return float(imbalance)

    def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
        """Determine trend from higher timeframe using specified indicator."""
        if higher_tf_df.empty:
            return "UNKNOWN"

        last_close = higher_tf_df["close"].iloc[-1]
        isd = self.indicator_settings

        if indicator_type == "sma":
            period = self.config["mtf_analysis"]["trend_period"]
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"MTF SMA: Not enough data for {period} period. Have {len(higher_tf_df)}.",
                )
                return "UNKNOWN"
            sma = ta.sma(higher_tf_df["close"], length=period).iloc[-1]
            if last_close > sma:
                return "UP"
            if last_close < sma:
                return "DOWN"
            return "SIDEWAYS"
        if indicator_type == "ema":
            period = self.config["mtf_analysis"]["trend_period"]
            if len(higher_tf_df) < period:
                self.logger.debug(
                    f"MTF EMA: Not enough data for {period} period. Have {len(higher_tf_df)}.",
                )
                return "UNKNOWN"
            ema = ta.ema(higher_tf_df["close"], length=period).iloc[-1]
            if last_close > ema:
                return "UP"
            if last_close < ema:
                return "DOWN"
            return "SIDEWAYS"
        if indicator_type == "ehlers_supertrend":
            st_result = self.indicator_calculator.calculate_ehlers_supertrend(
                higher_tf_df,
                period=isd["ehlers_slow_period"],
                multiplier=isd["ehlers_slow_multiplier"],
            )
            if st_result is not None and not st_result.empty:
                st_dir = st_result["direction"].iloc[-1]
                if st_dir == 1:
                    return "UP"
                if st_dir == -1:
                    return "DOWN"
            return "UNKNOWN"
        return "UNKNOWN"

    async def generate_trading_signal(
        self,
        current_price: Decimal,
        orderbook_manager: AdvancedOrderbookManager,
        mtf_trends: dict[str, str],
    ) -> tuple[str, float]:
        """Generate a signal using confluence of indicators, including Ehlers SuperTrend."""
        signal_score = 0.0
        active_indicators = self.config["indicators"]
        weights = self.weights

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}",
            )
            return "HOLD", 0.0

        current_close = Decimal(str(self.df["close"].iloc[-1]))
        isd = self.indicator_settings

        if active_indicators.get("ema_alignment", False):
            ema_short = self._get_indicator_value("EMA_Short")
            ema_long = self._get_indicator_value("EMA_Long")
            if not pd.isna(ema_short) and not pd.isna(ema_long):
                if ema_short > ema_long:
                    signal_score += weights.get("ema_alignment", 0)
                elif ema_short < ema_long:
                    signal_score -= weights.get("ema_alignment", 0)

        if active_indicators.get("sma_trend_filter", False):
            sma_long = self._get_indicator_value("SMA_Long")
            if not pd.isna(sma_long):
                if current_close > sma_long:
                    signal_score += weights.get("sma_trend_filter", 0)
                elif current_close < sma_long:
                    signal_score -= weights.get("sma_trend_filter", 0)

        if active_indicators.get("momentum", False):
            rsi = self._get_indicator_value("RSI")
            stoch_k = self._get_indicator_value("StochRSI_K")
            stoch_d = self._get_indicator_value("StochRSI_D")
            cci = self._get_indicator_value("CCI")
            wr = self._get_indicator_value("WR")
            mfi = self._get_indicator_value("MFI")

            if not pd.isna(rsi):
                if rsi < isd["rsi_oversold"]:
                    signal_score += weights.get("rsi", 0) * 0.5
                elif rsi > isd["rsi_overbought"]:
                    signal_score -= weights.get("rsi", 0) * 0.5

            if not pd.isna(stoch_k) and not pd.isna(stoch_d):
                if stoch_k > stoch_d and stoch_k < isd["stoch_rsi_oversold"]:
                    signal_score += weights.get("stoch_rsi", 0) * 0.5
                elif stoch_k < stoch_d and stoch_k > isd["stoch_rsi_overbought"]:
                    signal_score -= weights.get("stoch_rsi", 0) * 0.5

            if not pd.isna(cci):
                if cci < isd["cci_oversold"]:
                    signal_score += weights.get("cci", 0) * 0.5
                elif cci > isd["cci_overbought"]:
                    signal_score -= weights.get("cci", 0) * 0.5

            if not pd.isna(wr):
                if wr < isd["williams_r_oversold"]:
                    signal_score += weights.get("wr", 0) * 0.5
                elif wr > isd["williams_r_overbought"]:
                    signal_score -= weights.get("wr", 0) * 0.5

            if not pd.isna(mfi):
                if mfi < isd["mfi_oversold"]:
                    signal_score += weights.get("mfi", 0) * 0.5
                elif mfi > isd["mfi_overbought"]:
                    signal_score -= weights.get("mfi", 0) * 0.5

        if active_indicators.get("bollinger_bands", False):
            bb_upper = self._get_indicator_value("BB_Upper")
            bb_lower = self._get_indicator_value("BB_Lower")
            if not pd.isna(bb_upper) and not pd.isna(bb_lower):
                if current_close < bb_lower:
                    signal_score += weights.get("bollinger_bands", 0) * 0.5
                elif current_close > bb_upper:
                    signal_score -= weights.get("bollinger_bands", 0) * 0.5

        if active_indicators.get("vwap", False):
            vwap = self._get_indicator_value("VWAP")
            if not pd.isna(vwap):
                if current_close > vwap:
                    signal_score += weights.get("vwap", 0) * 0.2
                elif current_close < vwap:
                    signal_score -= weights.get("vwap", 0) * 0.2

                if len(self.df) > 1 and "VWAP" in self.df.columns:
                    prev_close = Decimal(str(self.df["close"].iloc[-2]))
                    prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
                    if current_close > vwap and prev_close <= prev_vwap:
                        signal_score += weights.get("vwap", 0) * 0.3
                        self.logger.debug("VWAP: Bullish crossover detected.")
                    elif current_close < vwap and prev_close >= prev_vwap:
                        signal_score -= weights.get("vwap", 0) * 0.3
                        self.logger.debug("VWAP: Bearish crossover detected.")

        if active_indicators.get("psar", False):
            psar_val = self._get_indicator_value("PSAR_Val")
            psar_dir = self._get_indicator_value("PSAR_Dir")

            # Debugging PSAR values and types
            self.logger.debug(f"PSAR_Val: {psar_val} (Type: {type(psar_val)})")
            self.logger.debug(f"PSAR_Dir: {psar_dir} (Type: {type(psar_dir)})")
            self.logger.debug(
                f"Current Close: {current_close} (Type: {type(current_close)})",
            )

            if not pd.isna(psar_val) and not pd.isna(psar_dir):
                # Ensure psar_val is a comparable numeric type
                psar_val_numeric = (
                    Decimal(str(psar_val))
                    if not isinstance(psar_val, Decimal)
                    else psar_val
                )

                # Check for PSAR buy signal (price crosses above PSAR)
                if psar_dir == 1:
                    # Need previous close and previous PSAR value for a true cross
                    if len(self.df) >= 2:
                        prev_close = Decimal(str(self.df["close"].iloc[-2]))
                        # Retrieve previous PSAR_Val from indicator_values, not self.df["PSAR_Val"]
                        prev_psar_val = self._get_indicator_value(
                            "PSAR_Val",
                            default=0.0,
                        )
                        prev_psar_val_numeric = (
                            Decimal(str(prev_psar_val))
                            if not isinstance(prev_psar_val, Decimal)
                            else prev_psar_val
                        )

                        self.logger.debug(
                            f"Prev Close: {prev_close} (Type: {type(prev_close)})",
                        )
                        self.logger.debug(
                            f"Prev PSAR_Val: {prev_psar_val} (Type: {type(prev_psar_val)})",
                        )

                        if (
                            current_close > psar_val_numeric
                            and prev_close <= prev_psar_val_numeric
                        ):
                            signal_score += (
                                weights.get("psar", 0) * 0.5
                            )  # Strong buy signal

                # Check for PSAR sell signal (price crosses below PSAR)
                elif psar_dir == -1:
                    if len(self.df) >= 2:
                        prev_close = Decimal(str(self.df["close"].iloc[-2]))
                        # Retrieve previous PSAR_Val from indicator_values, not self.df["PSAR_Val"]
                        prev_psar_val = self._get_indicator_value(
                            "PSAR_Val",
                            default=0.0,
                        )
                        prev_psar_val_numeric = (
                            Decimal(str(prev_psar_val))
                            if not isinstance(prev_psar_val, Decimal)
                            else prev_psar_val
                        )

                        if (
                            current_close < psar_val_numeric
                            and prev_close >= prev_psar_val_numeric
                        ):
                            signal_score -= (
                                weights.get("psar", 0) * 0.5
                            )  # Strong sell signal

        if active_indicators.get("orderbook_imbalance", False) and orderbook_manager:
            imbalance = await self._check_orderbook(current_price, orderbook_manager)
            signal_score += imbalance * weights.get("orderbook_imbalance", 0)

        if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
            for level_name, level_price in self.fib_levels.items():
                if level_name not in ["0.0%", "100.0%"] and abs(
                    current_price - level_price,
                ) / current_price < Decimal("0.001"):
                    self.logger.debug(
                        f"Price near Fibonacci level {level_name}: {level_price}",
                    )
                    if len(self.df) > 1:
                        prev_close = Decimal(str(self.df["close"].iloc[-2]))
                        if current_close > prev_close and current_close > level_price:
                            signal_score += weights.get("fibonacci_levels", 0) * 0.1
                        elif current_close < prev_close and current_close < level_price:
                            signal_score -= weights.get("fibonacci_levels", 0) * 0.1

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
                if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
                    signal_score += weight
                    self.logger.debug(
                        "Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend).",
                    )
                elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
                    signal_score -= weight
                    self.logger.debug(
                        "Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend).",
                    )
                elif st_slow_dir == 1 and st_fast_dir == 1:
                    signal_score += weight * 0.3
                elif st_slow_dir == -1 and st_fast_dir == -1:
                    signal_score -= weight * 0.3

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
                if (
                    macd_line > signal_line
                    and "MACD_Line" in self.df.columns
                    and "MACD_Signal" in self.df.columns
                    and len(self.df) > 1
                    and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]
                ):
                    signal_score += weight
                    self.logger.debug(
                        "MACD: BUY signal (MACD line crossed above Signal line).",
                    )
                elif (
                    macd_line < signal_line
                    and "MACD_Line" in self.df.columns
                    and "MACD_Signal" in self.df.columns
                    and len(self.df) > 1
                    and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]
                ):
                    signal_score -= weight
                    self.logger.debug(
                        "MACD: SELL signal (MACD line crossed below Signal line).",
                    )
                elif (
                    histogram > 0
                    and "MACD_Hist" in self.df.columns
                    and len(self.df) > 1
                    and self.df["MACD_Hist"].iloc[-2] < 0
                ):
                    signal_score += weight * 0.2
                elif (
                    histogram < 0
                    and "MACD_Hist" in self.df.columns
                    and len(self.df) > 1
                    and self.df["MACD_Hist"].iloc[-2] > 0
                ):
                    signal_score -= weight * 0.2

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
                            "ADX: Strong BUY trend (ADX > 25, +DI > -DI).",
                        )
                    elif minus_di > plus_di:
                        signal_score -= weight
                        self.logger.debug(
                            "ADX: Strong SELL trend (ADX > 25, -DI > +DI).",
                        )
                elif adx_val < ADX_WEAK_TREND_THRESHOLD:
                    signal_score += 0
                    self.logger.debug("ADX: Weak trend (ADX < 20). Neutral signal.")

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
                has_history = len(self.df) > 1 and all(
                    col in self.df.columns
                    for col in [
                        "Tenkan_Sen",
                        "Kijun_Sen",
                        "Senkou_Span_A",
                        "Senkou_Span_B",
                        "Chikou_Span",
                    ]
                )

                if has_history:
                    if (
                        tenkan_sen > kijun_sen
                        and self.df["Tenkan_Sen"].iloc[-2]
                        <= self.df["Kijun_Sen"].iloc[-2]
                    ):
                        signal_score += weight * 0.5
                        self.logger.debug(
                            "Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish).",
                        )
                    elif (
                        tenkan_sen < kijun_sen
                        and self.df["Tenkan_Sen"].iloc[-2]
                        >= self.df["Kijun_Sen"].iloc[-2]
                    ):
                        signal_score -= weight * 0.5
                        self.logger.debug(
                            "Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish).",
                        )

                if has_history:
                    current_max_kumo = max(senkou_span_a, senkou_span_b)
                    current_min_kumo = min(senkou_span_a, senkou_span_b)
                    prev_max_kumo = max(
                        Decimal(str(self.df["Senkou_Span_A"].iloc[-2])),
                        Decimal(str(self.df["Senkou_Span_B"].iloc[-2])),
                    )
                    prev_min_kumo = min(
                        Decimal(str(self.df["Senkou_Span_A"].iloc[-2])),
                        Decimal(str(self.df["Senkou_Span_B"].iloc[-2])),
                    )

                    if (
                        current_close > current_max_kumo
                        and Decimal(str(self.df["close"].iloc[-2])) <= prev_max_kumo
                    ):
                        signal_score += weight * 0.7
                        self.logger.debug(
                            "Ichimoku: Price broke above Kumo (strong bullish).",
                        )
                    elif (
                        current_close < current_min_kumo
                        and Decimal(str(self.df["close"].iloc[-2])) >= prev_min_kumo
                    ):
                        signal_score -= weight * 0.7
                        self.logger.debug(
                            "Ichimoku: Price broke below Kumo (strong bearish).",
                        )

                if has_history:
                    if chikou_span > current_close and Decimal(
                        str(self.df["Chikou_Span"].iloc[-2]),
                    ) <= Decimal(str(self.df["close"].iloc[-2])):
                        signal_score += weight * 0.3
                        self.logger.debug(
                            "Ichimoku: Chikou Span crossed above price (bullish confirmation).",
                        )
                    elif chikou_span < current_close and Decimal(
                        str(self.df["Chikou_Span"].iloc[-2]),
                    ) >= Decimal(str(self.df["close"].iloc[-2])):
                        signal_score -= weight * 0.3
                        self.logger.debug(
                            "Ichimoku: Chikou Span crossed below price (bearish confirmation).",
                        )

        if active_indicators.get("obv", False):
            obv_val = self._get_indicator_value("OBV")
            obv_ema = self._get_indicator_value("OBV_EMA")

            weight = weights.get("obv_momentum", 0.0)

            if not pd.isna(obv_val) and not pd.isna(obv_ema):
                has_history = (
                    len(self.df) > 1
                    and "OBV" in self.df.columns
                    and "OBV_EMA" in self.df.columns
                )

                if has_history:
                    if (
                        obv_val > obv_ema
                        and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]
                    ):
                        signal_score += weight * 0.5
                        self.logger.debug("OBV: Bullish crossover detected.")
                    elif (
                        obv_val < obv_ema
                        and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]
                    ):
                        signal_score -= weight * 0.5
                        self.logger.debug("OBV: Bearish crossover detected.")

                if len(self.df) > 2 and "OBV" in self.df.columns:
                    if (
                        obv_val > self.df["OBV"].iloc[-2]
                        and obv_val > self.df["OBV"].iloc[-3]
                    ):
                        signal_score += weight * 0.2
                    elif (
                        obv_val < self.df["OBV"].iloc[-2]
                        and obv_val < self.df["OBV"].iloc[-3]
                    ):
                        signal_score -= weight * 0.2

        if active_indicators.get("cmf", False):
            cmf_val = self._get_indicator_value("CMF")

            weight = weights.get("cmf_flow", 0.0)

            if not pd.isna(cmf_val):
                has_history = len(self.df) > 1 and "CMF" in self.df.columns

                if cmf_val > 0:
                    signal_score += weight * 0.5
                elif cmf_val < 0:
                    signal_score -= weight * 0.5

                if len(self.df) > 2 and "CMF" in self.df.columns:
                    if (
                        cmf_val > self.df["CMF"].iloc[-2]
                        and cmf_val > self.df["CMF"].iloc[-3]
                    ):
                        signal_score += weight * 0.3
                    elif (
                        cmf_val < self.df["CMF"].iloc[-2]
                        and cmf_val < self.df["CMF"].iloc[-3]
                    ):
                        signal_score -= weight * 0.3

        if self.config["mtf_analysis"]["enabled"] and mtf_trends:
            mtf_buy_score = 0
            mtf_sell_score = 0
            for _tf_indicator, trend in mtf_trends.items():
                if trend == "UP":
                    mtf_buy_score += 1
                elif trend == "DOWN":
                    mtf_sell_score += 1

            mtf_weight = weights.get("mtf_trend_confluence", 0.0)

            total_mtf_trends = len(mtf_trends)
            if total_mtf_trends > 0:
                normalized_mtf_score = (
                    mtf_buy_score - mtf_sell_score
                ) / total_mtf_trends
                signal_score += mtf_weight * normalized_mtf_score
                self.logger.debug(
                    f"MTF Confluence: Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {mtf_sell_score}). Total MTF contribution: {mtf_weight * normalized_mtf_score:.2f}",
                )

        threshold = self.config["signal_score_threshold"]
        final_signal = "HOLD"
        if signal_score >= threshold:
            final_signal = "BUY"
        elif signal_score <= -threshold:
            final_signal = "SELL"

        self.logger.info(
            f"{NEON_YELLOW}Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}",
        )
        return final_signal, signal_score

    def calculate_entry_tp_sl(
        self,
        current_price: Decimal,
        atr_value: Decimal,
        signal: str,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """Calculate Take Profit, Stop Loss, and Trailing Stop activation/value levels."""
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )
        take_profit_atr_multiple = Decimal(
            str(self.config["trade_management"]["take_profit_atr_multiple"]),
        )
        trailing_stop_atr_multiple = Decimal(
            str(self.config["trade_management"]["trailing_stop_atr_multiple"]),
        )

        stop_loss = Decimal("0")
        take_profit = Decimal("0")
        trailing_activation_price = Decimal("0")
        trailing_value = Decimal("0")

        if signal == "BUY":
            stop_loss = current_price - (atr_value * stop_loss_atr_multiple)
            take_profit = current_price + (atr_value * take_profit_atr_multiple)
            trailing_activation_price = current_price + (atr_value * Decimal("0.5"))
            trailing_value = atr_value * trailing_stop_atr_multiple
        elif signal == "SELL":
            stop_loss = current_price + (atr_value * stop_loss_atr_multiple)
            take_profit = current_price - (atr_value * take_profit_atr_multiple)
            trailing_activation_price = current_price - (atr_value * Decimal("0.5"))
            trailing_value = atr_value * trailing_stop_atr_multiple
        else:
            return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")

        quantized_tp = take_profit.quantize(Decimal("0.00001"), rounding=ROUND_DOWN)
        quantized_sl = stop_loss.quantize(Decimal("0.00001"), rounding=ROUND_DOWN)
        quantized_trailing_activation = trailing_activation_price.quantize(
            Decimal("0.00001"),
            rounding=ROUND_DOWN,
        )
        quantized_trailing_value = trailing_value.quantize(
            Decimal("0.00001"),
            rounding=ROUND_DOWN,
        )

        return (
            quantized_tp,
            quantized_sl,
            quantized_trailing_activation,
            quantized_trailing_value,
        )


class PositionManager:
    """Manages open positions, stop-loss, and take-profit levels."""

    def __init__(
        self,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
        bybit_client: BybitClient,
        precision_manager: PrecisionManager,
        alert_system: Any,
        performance_tracker: Any,
        trading_analyzer: TradingAnalyzer,  # Added trading_analyzer to access calculate_entry_tp_sl
    ):
        """Initializes the PositionManager."""
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.bybit_client = bybit_client
        self.precision_manager = precision_manager
        self.alert_system = alert_system
        self.performance_tracker = performance_tracker
        self.trading_analyzer = trading_analyzer

        self.open_positions: dict[str, dict] = {}
        self.trade_management_enabled = config["trade_management"]["enabled"]
        self.max_open_positions = config["trade_management"]["max_open_positions"]
        self.current_account_balance: Decimal = Decimal("0")

        self.active_trailing_stops: dict[str, dict] = {}

    async def _get_current_balance(self) -> Decimal:
        """Fetch current account balance (from actual API)."""
        balance = await self.bybit_client.get_wallet_balance()
        if balance is not None:
            self.current_account_balance = balance
            return balance

        self.logger.warning(
            f"{NEON_YELLOW}Failed to fetch live balance, using fallback from config.{RESET}",
        )
        return Decimal(str(self.config["trade_management"]["account_balance"]))

    async def _calculate_order_size(
        self,
        current_price: Decimal,
        atr_value: Decimal,
    ) -> Decimal:
        """Calculate order size based on risk per trade and ATR."""
        if not self.trade_management_enabled:
            return Decimal("0")

        account_balance = await self._get_current_balance()
        risk_per_trade_percent = (
            Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
            / 100
        )
        stop_loss_atr_multiple = Decimal(
            str(self.config["trade_management"]["stop_loss_atr_multiple"]),
        )

        risk_amount = account_balance * risk_per_trade_percent
        stop_loss_distance_usd = atr_value * stop_loss_atr_multiple

        if stop_loss_distance_usd <= 0:
            self.logger.warning(
                f"{NEON_YELLOW}Calculated stop loss distance is zero or negative. Cannot determine order size.{RESET}",
            )
            return Decimal("0")

        order_qty_unleveraged = risk_amount / stop_loss_distance_usd

        order_qty = order_qty_unleveraged

        order_qty = self.precision_manager.round_qty(order_qty, self.symbol)

        min_qty = self.precision_manager.get_min_qty(self.symbol)
        max_qty = self.precision_manager.get_max_qty(self.symbol)
        min_notional = self.precision_manager.get_min_notional(self.symbol)

        if order_qty < min_qty:
            self.logger.warning(
                f"{NEON_YELLOW}Calculated order quantity {order_qty} is less than minimum quantity {min_qty}. Adjusting to minimum.{RESET}",
            )
            order_qty = min_qty
        if order_qty > max_qty:
            self.logger.warning(
                f"{NEON_YELLOW}Calculated order quantity {order_qty} is greater than maximum quantity {max_qty}. Adjusting to maximum.{RESET}",
            )
            order_qty = max_qty

        notional_value = order_qty * current_price
        if notional_value < min_notional:
            self.logger.warning(
                f"{NEON_YELLOW}Calculated order notional value {notional_value:.2f} is less than minimum notional {min_notional:.2f}. Cannot place trade.{RESET}",
            )
            return Decimal("0")

        self.logger.info(
            f"Calculated order size: {order_qty} {self.symbol} (Risk: {risk_amount:.2f} USD, Notional: {notional_value:.2f} USD)",
        )
        return order_qty

    async def open_position(
        self,
        signal: str,
        current_price: Decimal,
        atr_value: Decimal,
    ) -> dict | None:
        """Open a new position if conditions allow.

        Returns the new position details or None.
        """
        if not self.trade_management_enabled:
            self.logger.info(
                f"{NEON_YELLOW}Trade management is disabled. Skipping opening position.{RESET}",
            )
            return None

        if self.symbol in self.open_positions:
            existing_pos = self.open_positions[self.symbol]
            if existing_pos["status"] == "OPEN" and existing_pos["side"] == signal:
                self.logger.info(
                    f"{NEON_BLUE}Already in a {signal} position for {self.symbol}. No new position opened.{RESET}",
                )
                return None
            if existing_pos["status"] == "OPEN" and existing_pos["side"] != signal:
                if self.max_open_positions == 1:
                    self.logger.info(
                        f"{NEON_YELLOW}Attempting to close existing {existing_pos['side']} position before opening new {signal} position.{RESET}",
                    )
                    await self.close_position(existing_pos)
                    await asyncio.sleep(
                        API_CALL_RETRY_DELAY_SECONDS,
                    )  # Give time for close order to process
                else:
                    self.logger.info(
                        f"{NEON_YELLOW}Already in an opposing position for {self.symbol}. Not opening new position.{RESET}",
                    )
                    return None

        if (
            len(self.open_positions) >= self.max_open_positions
            and self.max_open_positions > 0
        ):
            self.logger.info(
                f"{NEON_YELLOW}Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}",
            )
            return None

        if signal not in ["BUY", "SELL"]:
            self.logger.debug(f"Invalid signal '{signal}' for opening position.")
            return None

        order_qty = await self._calculate_order_size(current_price, atr_value)
        if order_qty <= Decimal("0"):
            self.logger.warning(
                f"{NEON_YELLOW}Order quantity is zero or negative. Cannot open position.{RESET}",
            )
            return None

        take_profit, stop_loss, trailing_activation_price, trailing_value = (
            self.trading_analyzer.calculate_entry_tp_sl(
                current_price,
                atr_value,
                signal,
            )
        )

        client_order_id = f"whalebot-{self.symbol}-{signal}-{int(time.time() * 1000)}"
        order_response = await self.bybit_client.place_order(
            symbol=self.symbol,
            side=signal,
            qty=str(order_qty),
            order_type="Market",
            stop_loss=str(stop_loss),
            take_profit=str(take_profit),
            client_order_id=client_order_id,
        )

        if order_response:
            position = {
                "entry_time": datetime.now(ZoneInfo(self.config["timezone"])),
                "symbol": self.symbol,
                "side": signal,
                "entry_price": current_price,
                "qty": order_qty,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "trailing_stop_activation_price": trailing_activation_price,
                "trailing_stop_value": trailing_value,
                "current_trailing_sl": stop_loss,  # Initial SL is the fixed stop loss
                "is_trailing_activated": False,
                "status": "OPEN",
                "order_id": order_response.get("orderId"),
                "client_order_id": client_order_id,
                "unrealized_pnl": Decimal("0"),
            }
            self.open_positions[self.symbol] = position
            self.logger.info(
                f"{NEON_GREEN}Opened {signal} position for {self.symbol}: {position}{RESET}",
            )
            self.alert_system.send_alert(
                f"Opened {signal} {order_qty} of {self.symbol} @ {current_price}",
                "INFO",
            )
            return position

        self.logger.error(
            f"{NEON_RED}Failed to open {signal} position for {self.symbol}. Order response: {order_response}{RESET}",
        )
        return None

    async def close_position(self, position: dict) -> bool:
        """Close an existing open position via a market order."""
        if position["status"] != "OPEN":
            self.logger.warning(
                f"{NEON_YELLOW}Attempted to close a non-open position for {position['symbol']}.{RESET}",
            )
            return False

        opposing_side = "Sell" if position["side"] == "BUY" else "Buy"
        close_qty = self.precision_manager.round_qty(
            position["qty"],
            position["symbol"],
        )

        self.logger.info(
            f"{NEON_YELLOW}Attempting to close {position['side']} position for {position['symbol']} (Qty: {close_qty}).{RESET}",
        )

        order_response = await self.bybit_client.place_order(
            symbol=position["symbol"],
            side=opposing_side,
            qty=str(close_qty),
            order_type="Market",
            reduce_only=True,
        )

        if order_response:
            self.logger.info(
                f"{NEON_GREEN}Market order placed to close position: {order_response}{RESET}",
            )
            position["status"] = "PENDING_CLOSE"
            self.open_positions[position["symbol"]] = position
            self.alert_system.send_alert(
                f"Placed order to close {position['side']} {close_qty} of {position['symbol']}",
                "INFO",
            )
            return True

        self.logger.error(
            f"{NEON_RED}Failed to place market order to close position for {position['symbol']}.{RESET}",
        )
        return False

    async def manage_positions(
        self,
        current_price: Decimal,
        atr_value: Decimal,
    ) -> None:
        """Check and manage all open positions (SL/TP/Trailing Stop)."""
        if not self.trade_management_enabled or not self.open_positions:
            return

        for symbol, position in list(self.open_positions.items()):
            if position["status"] == "OPEN":
                side = position["side"]
                entry_price = position["entry_price"]
                stop_loss = position["stop_loss"]
                take_profit = position["take_profit"]
                trailing_activation_price = position["trailing_stop_activation_price"]
                trailing_value = position["trailing_stop_value"]
                is_trailing_activated = position["is_trailing_activated"]
                current_trailing_sl = position["current_trailing_sl"]

                closed_by = ""

                if side == "BUY":
                    if current_price <= stop_loss:
                        closed_by = "STOP_LOSS"
                    elif current_price >= take_profit:
                        closed_by = "TAKE_PROFIT"
                    elif is_trailing_activated and current_price <= current_trailing_sl:
                        closed_by = "TRAILING_STOP_LOSS"
                elif current_price >= stop_loss:
                    closed_by = "STOP_LOSS"
                elif current_price <= take_profit:
                    closed_by = "TAKE_PROFIT"
                elif is_trailing_activated and current_price >= current_trailing_sl:
                    closed_by = "TRAILING_STOP_LOSS"

                if closed_by:
                    self.logger.info(
                        f"{NEON_PURPLE}Position for {symbol} closed by {closed_by}. Closing position.{RESET}",
                    )
                    await self.bybit_client.cancel_all_orders(symbol)
                    await self.close_position(position)
                    position["status"] = "PENDING_CLOSE"
                    position["exit_time"] = datetime.now(
                        ZoneInfo(self.config["timezone"]),
                    )
                    position["exit_price"] = current_price
                    position["closed_by"] = closed_by

                    pnl = (
                        (current_price - entry_price) * position["qty"]
                        if side == "BUY"
                        else (entry_price - current_price) * position["qty"]
                    )
                    self.performance_tracker.record_trade(position, pnl)
                    continue

                if not is_trailing_activated:
                    if (
                        side == "BUY" and current_price >= trailing_activation_price
                    ) or (
                        side == "SELL" and current_price <= trailing_activation_price
                    ):
                        position["is_trailing_activated"] = True

                        potential_new_sl = (
                            current_price - trailing_value
                            if side == "BUY"
                            else current_price + trailing_value
                        )
                        position["current_trailing_sl"] = (
                            self.precision_manager.round_price(potential_new_sl, symbol)
                        )

                        self.logger.info(
                            f"{NEON_GREEN}Trailing stop activated for {symbol}. Initial SL: {position['current_trailing_sl']:.5f}{RESET}",
                        )
                        await self.bybit_client.set_trading_stop(
                            symbol=symbol,
                            stop_loss=str(position["current_trailing_sl"]),
                            trailing_stop=str(trailing_value),
                            active_price=str(current_price),
                        )
                else:
                    updated_sl = Decimal("0")
                    if side == "BUY":
                        potential_new_sl = current_price - trailing_value
                        if potential_new_sl > current_trailing_sl:
                            updated_sl = potential_new_sl
                    else:
                        potential_new_sl = current_price + trailing_value
                        if potential_new_sl < current_trailing_sl:
                            updated_sl = potential_new_sl

                    if updated_sl != Decimal("0") and updated_sl != current_trailing_sl:
                        # Ensure trailing SL doesn't go below entry for buy or above entry for sell if it's supposed to lock in profit
                        if (side == "BUY" and updated_sl > entry_price) or (
                            side == "SELL" and updated_sl < entry_price
                        ):
                            rounded_sl = self.precision_manager.round_price(
                                updated_sl,
                                symbol,
                            )
                            position["current_trailing_sl"] = rounded_sl
                            self.logger.info(
                                f"{NEON_CYAN}Updating trailing stop for {symbol} to {position['current_trailing_sl']:.5f}{RESET}",
                            )
                            await self.bybit_client.set_trading_stop(
                                symbol=symbol,
                                stop_loss=str(position["current_trailing_sl"]),
                            )

                self.open_positions[symbol] = position

    async def update_position_from_ws(self, ws_position_data: dict[str, Any]):
        """Update internal position state from WebSocket data."""
        symbol = ws_position_data.get("symbol")
        if symbol != self.symbol:
            return

        size = Decimal(ws_position_data.get("size", "0"))
        side = ws_position_data.get("side")
        avg_price = Decimal(ws_position_data.get("avgPrice", "0"))
        unrealized_pnl = Decimal(ws_position_data.get("unrealisedPnl", "0"))

        if size == Decimal("0"):
            if (
                symbol in self.open_positions
                and self.open_positions[symbol]["status"] != "CLOSED"
            ):
                self.logger.info(
                    f"{NEON_PURPLE}Position for {symbol} detected as closed on exchange. Removing from active positions.{RESET}",
                )
                closed_pos = self.open_positions.pop(symbol)
                if closed_pos["status"] not in ["CLOSED", "PENDING_CLOSE"]:
                    closed_pos["status"] = "CLOSED"
                    closed_pos["exit_time"] = datetime.now(
                        ZoneInfo(self.config["timezone"]),
                    )
                    closed_pos["exit_price"] = avg_price
                    pnl = unrealized_pnl
                    self.performance_tracker.record_trade(closed_pos, pnl)
            return

        if symbol in self.open_positions:
            position = self.open_positions[symbol]
            position["qty"] = size
            position["side"] = side
            position["entry_price"] = avg_price
            position["unrealized_pnl"] = unrealized_pnl
            position["status"] = "OPEN"
            self.open_positions[symbol] = position
            self.logger.debug(
                f"Updated internal position for {symbol}: Size={size}, AvgPrice={avg_price}, PnL={unrealized_pnl}",
            )
        else:
            self.logger.warning(
                f"{NEON_YELLOW}Detected new open position for {symbol} via WS not tracked internally. Adding it.{RESET}",
            )
            new_pos = {
                "entry_time": datetime.now(ZoneInfo(self.config["timezone"])),
                "symbol": symbol,
                "side": side,
                "entry_price": avg_price,
                "qty": size,
                "stop_loss": Decimal("0"),
                "take_profit": Decimal("0"),
                "trailing_stop_activation_price": Decimal("0"),
                "trailing_stop_value": Decimal("0"),
                "current_trailing_sl": Decimal("0"),
                "is_trailing_activated": False,
                "status": "OPEN",
                "order_id": None,
                "client_order_id": None,
                "unrealized_pnl": unrealized_pnl,
            }
            self.open_positions[symbol] = new_pos

    def get_open_positions(self) -> list[dict]:
        """Return a list of currently open positions."""
        return [pos for pos in self.open_positions.values() if pos["status"] == "OPEN"]


class PerformanceTracker:
    """Tracks and reports trading performance."""

    def __init__(self, logger: logging.Logger):
        """Initializes the PerformanceTracker."""
        self.logger = logger
        self.trades: list[dict] = []
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0
        self.trade_id_counter = 0

    def record_trade(self, position: dict, pnl: Decimal) -> None:
        """Record a completed trade."""
        self.trade_id_counter += 1
        trade_record = {
            "trade_id": self.trade_id_counter,
            "entry_time": position["entry_time"],
            "exit_time": position.get("exit_time", datetime.now(ZoneInfo("UTC"))),
            "symbol": position["symbol"],
            "side": position["side"],
            "entry_price": position["entry_price"],
            "exit_price": position.get("exit_price", Decimal("0")),
            "qty": position["qty"],
            "pnl": pnl,
            "closed_by": position.get("closed_by", "UNKNOWN"),
        }
        self.trades.append(trade_record)
        self.total_pnl += pnl
        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.logger.info(
            f"{NEON_CYAN}Trade recorded. Current Total PnL: {self.total_pnl:.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}",
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


class AlertSystem:
    """Handles sending alerts for critical events."""

    def __init__(self, logger: logging.Logger):
        """Initializes the AlertSystem."""
        self.logger = logger

    def send_alert(self, message: str, level: str = "INFO") -> None:
        """Send an alert (currently logs it)."""
        if level == "INFO":
            self.logger.info(f"{NEON_BLUE}ALERT: {message}{RESET}")
        elif level == "WARNING":
            self.logger.warning(f"{NEON_YELLOW}ALERT: {message}{RESET}")
        elif level == "ERROR":
            self.logger.error(f"{NEON_RED}ALERT: {message}{RESET}")


async def display_indicator_values_and_price(
    config: dict[str, Any],
    logger: logging.Logger,
    current_price: Decimal,
    trading_analyzer: TradingAnalyzer,
    orderbook_manager: AdvancedOrderbookManager,
    mtf_trends: dict[str, str],
) -> None:
    """Display current price and calculated indicator values."""
    logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
    logger.info(f"{NEON_GREEN}Current Price: {current_price}{RESET}")

    if trading_analyzer.df.empty:
        logger.warning(
            f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.{RESET}",
        )
        return

    logger.info(f"{NEON_CYAN}--- Indicator Values ---{RESET}")
    for indicator_name, value in trading_analyzer.indicator_values.items():
        color = INDICATOR_COLORS.get(indicator_name, NEON_YELLOW)
        if isinstance(value, Decimal) or isinstance(value, float):
            logger.info(f"  {color}{indicator_name}: {value:.8f}{RESET}")
        else:
            logger.info(f"  {color}{indicator_name}: {value}{RESET}")

    if trading_analyzer.fib_levels:
        logger.info(f"{NEON_CYAN}--- Fibonacci Levels ---{RESET}")
        logger.info("")
        for level_name, level_price in trading_analyzer.fib_levels.items():
            logger.info(f"  {NEON_YELLOW}{level_name}: {level_price:.8f}{RESET}")

    if mtf_trends:
        logger.info(f"{NEON_CYAN}--- Multi-Timeframe Trends ---{RESET}")
        logger.info("")
        for tf_indicator, trend in mtf_trends.items():
            logger.info(f"  {NEON_YELLOW}{tf_indicator}: {trend}{RESET}")

    if config["indicators"].get("orderbook_imbalance", False):
        imbalance = await trading_analyzer._check_orderbook(
            current_price,
            orderbook_manager,
        )
        logger.info(f"{NEON_CYAN}Orderbook Imbalance: {imbalance:.4f}{RESET}")

    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")


async def main() -> None:
    """Orchestrate the bot's operation."""
    logger = setup_logger("wgwhalex_bot")
    config = load_config(CONFIG_FILE, logger)

    global TIMEZONE
    TIMEZONE = ZoneInfo(config["timezone"])

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

    if config["interval"] not in valid_bybit_intervals:
        logger.error(
            f"{NEON_RED}Invalid primary interval '{config['interval']}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.{RESET}",
        )
        sys.exit(1)

    for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
        if htf_interval not in valid_bybit_intervals:
            logger.error(
                f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}' in config.json. Please use Bybit's valid string formats (e.g., '1h' should be '60', '4h' should be '240'). Exiting.{RESET}",
            )
            sys.exit(1)

    if not API_KEY or not API_SECRET:
        logger.critical(
            f"{NEON_RED}BYBIT_API_KEY or BYBIT_API_SECRET environment variables are NOT set. Please set them before running the bot. Exiting.{RESET}",
        )
        sys.exit(1)

    logger.info(f"{NEON_GREEN}--- Wgwhalex Trading Bot Initialized ---{RESET}")
    logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
    logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")
    logger.info(f"Using Testnet: {config['testnet']}")

    bybit_client = BybitClient(API_KEY, API_SECRET, config, logger)
    precision_manager = PrecisionManager(bybit_client, logger)
    indicator_calculator = IndicatorCalculator(logger)
    trading_analyzer = TradingAnalyzer(
        config,
        logger,
        config["symbol"],
        indicator_calculator,
    )
    performance_tracker = PerformanceTracker(logger)
    alert_system = AlertSystem(logger)
    position_manager = PositionManager(
        config,
        logger,
        config["symbol"],
        bybit_client,
        precision_manager,
        alert_system,
        performance_tracker,
        trading_analyzer,
    )
    orderbook_manager = AdvancedOrderbookManager(
        config["symbol"],
        logger,
        use_skip_list=True,
    )

    async def handle_kline_ws_message(message: dict[str, Any]):
        logger.debug(f"WS Kline: {message.get('data')}")

    async def handle_ticker_ws_message(message: dict[str, Any]):
        logger.debug(f"WS Ticker: {message.get('data')}")

    async def handle_orderbook_ws_message(message: dict[str, Any]):
        if message.get("type") == "snapshot":
            await orderbook_manager.update_snapshot(message["data"])
        elif message.get("type") == "delta":
            await orderbook_manager.update_delta(message["data"])
        logger.debug(f"WS Orderbook: {message.get('type')}")

    async def handle_position_ws_message(message: dict[str, Any]):
        for position_data in message.get("data", []):
            await position_manager.update_position_from_ws(position_data)
        logger.debug(f"WS Position: {message.get('data')}")

    async def handle_order_ws_message(message: dict[str, Any]):
        logger.debug(f"WS Order: {message.get('data')}")

    async def handle_execution_ws_message(message: dict[str, Any]):
        logger.debug(f"WS Execution: {message.get('data')}")

    async def handle_wallet_ws_message(message: dict[str, Any]):
        for wallet_data in message.get("data", []):
            if wallet_data.get("accountType") == "UNIFIED":
                for coin_data in wallet_data.get("coin", []):
                    if coin_data.get("coin") == "USDT":
                        position_manager.current_account_balance = Decimal(
                            coin_data.get("walletBalance", "0"),
                        )
                        logger.debug(
                            f"WS Wallet Balance Updated: {position_manager.current_account_balance}",
                        )
                        break
        logger.debug(f"WS Wallet: {message.get('data')}")

    await precision_manager.load_instrument_info(config["symbol"])
    if not precision_manager.initialized:
        alert_system.send_alert(
            f"Failed to load instrument info for {config['symbol']}. Bot cannot proceed.",
            "ERROR",
        )
        sys.exit(1)

    initial_leverage = str(config["trade_management"]["default_leverage"])
    if not await bybit_client.set_leverage(config["symbol"], initial_leverage):
        alert_system.send_alert(
            f"Failed to set initial leverage to {initial_leverage}. Bot cannot proceed.",
            "ERROR",
        )
        sys.exit(1)

    await bybit_client.start_public_ws(
        config["symbol"],
        config["orderbook_limit"],
        config["interval"],
        handle_ticker_ws_message,
        handle_orderbook_ws_message,
        handle_kline_ws_message,
    )
    await bybit_client.start_private_ws(
        handle_position_ws_message,
        handle_order_ws_message,
        handle_execution_ws_message,
        handle_wallet_ws_message,
    )
    await asyncio.sleep(WS_RECONNECT_DELAY_SECONDS)

    try:
        while True:
            try:
                logger.info(f"{NEON_PURPLE}--- New Analysis Loop Started ---{RESET}")
                current_price = await bybit_client.fetch_current_price(config["symbol"])
                if current_price is None:
                    alert_system.send_alert(
                        "Failed to fetch current price. Skipping loop.",
                        "WARNING",
                    )
                    await asyncio.sleep(config["loop_delay"])
                    continue

                df = await bybit_client.fetch_klines(
                    config["symbol"],
                    config["interval"],
                    1000,
                )
                if df is None or df.empty:
                    alert_system.send_alert(
                        "Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
                        "WARNING",
                    )
                    await asyncio.sleep(config["loop_delay"])
                    continue

                trading_analyzer.update_data(df)
                if trading_analyzer.df.empty:
                    alert_system.send_alert(
                        "TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                        "WARNING",
                    )
                    await asyncio.sleep(config["loop_delay"])
                    continue

                mtf_trends: dict[str, str] = {}
                if config["mtf_analysis"]["enabled"]:
                    for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
                        logger.debug(
                            f"Fetching klines for MTF interval: {htf_interval}",
                        )
                        htf_df = await bybit_client.fetch_klines(
                            config["symbol"],
                            htf_interval,
                            1000,
                        )
                        if htf_df is not None and not htf_df.empty:
                            for trend_ind in config["mtf_analysis"]["trend_indicators"]:
                                trend = trading_analyzer._get_mtf_trend(
                                    htf_df,
                                    trend_ind,
                                )
                                mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                                logger.debug(
                                    f"MTF Trend ({htf_interval}, {trend_ind}): {trend}",
                                )
                        else:
                            logger.warning(
                                f"{NEON_YELLOW}Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}",
                            )
                        await asyncio.sleep(
                            config["mtf_analysis"]["mtf_request_delay_seconds"],
                        )

                await display_indicator_values_and_price(
                    config,
                    logger,
                    current_price,
                    trading_analyzer,
                    orderbook_manager,
                    mtf_trends,
                )

                (
                    trading_signal,
                    signal_score,
                ) = await trading_analyzer.generate_trading_signal(
                    current_price,
                    orderbook_manager,
                    mtf_trends,
                )
                atr_value = Decimal(
                    str(trading_analyzer._get_indicator_value("ATR", Decimal("0.01"))),
                )

                await position_manager.manage_positions(current_price, atr_value)

                if (
                    trading_signal == "BUY"
                    and signal_score >= config["signal_score_threshold"]
                ):
                    logger.info(
                        f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}{RESET}",
                    )
                    await position_manager.open_position(
                        "BUY",
                        current_price,
                        atr_value,
                    )
                elif (
                    trading_signal == "SELL"
                    and signal_score <= -config["signal_score_threshold"]
                ):
                    logger.info(
                        f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}{RESET}",
                    )
                    await position_manager.open_position(
                        "SELL",
                        current_price,
                        atr_value,
                    )
                else:
                    logger.info(
                        f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}",
                    )

                open_positions = position_manager.get_open_positions()
                if open_positions:
                    logger.info(
                        f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}",
                    )
                    for pos in open_positions:
                        logger.info(
                            f"  - {pos['side']} @ {pos['entry_price']} (SL: {pos['stop_loss']}, TP: {pos['take_profit']}, Trailing SL: {pos['current_trailing_sl'] if pos['is_trailing_activated'] else 'N/A'}, PnL: {pos['unrealized_pnl']:.2f}){RESET}",
                        )
                else:
                    logger.info(f"{NEON_CYAN}No open positions.{RESET}")

                perf_summary = performance_tracker.get_summary()
                logger.info(
                    f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl']:.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}",
                )

                logger.info(
                    f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}",
                )
                await asyncio.sleep(config["loop_delay"])

            except asyncio.CancelledError:
                logger.info(f"{NEON_BLUE}Main loop cancelled gracefully.{RESET}")
                break
            except Exception as e:
                alert_system.send_alert(
                    f"An unhandled error occurred in the main loop: {e}",
                    "ERROR",
                )
                logger.exception(f"{NEON_RED}Unhandled exception in main loop:{RESET}")
                await asyncio.sleep(config["loop_delay"] * 2)

    except KeyboardInterrupt:
        logger.info(
            f"{NEON_BLUE}KeyboardInterrupt detected. Shutting down bot...{RESET}",
        )
    finally:
        await bybit_client.stop_ws()
        await bybit_client.cancel_all_orders(config["symbol"])
        logger.info(f"{NEON_GREEN}Wgwhalex Trading Bot Shutdown Complete.{RESET}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger = setup_logger("wgwhalex_bot_main")
        logger.critical(
            f"{NEON_RED}Critical error during bot startup or top-level execution: {e}{RESET}",
            exc_info=True,
        )
