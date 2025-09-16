# pyrm_ultimate.py (ULTIMATE LIVE TRADING VERSION)
# WARNING: THIS SCRIPT IS FOR LIVE TRADING AND WILL USE REAL MONEY.
# ENSURE YOUR .ENV FILE CONTAINS LIVE API KEYS.
# Enhanced with 45 mystical insights for supreme trading mastery

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import sqlite3  # (Pyrmethus's Insight #31) For persistent state storage
import threading
import time
import warnings
from collections import defaultdict, deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from decimal import ROUND_DOWN, Decimal, InvalidOperation, getcontext
from enum import Enum
from typing import Any

import numpy as np  # (Pyrmethus's Insight #33) For advanced analytics
from cryptography.fernet import (
    Fernet,  # (Pyrmethus's Insight #34) For API key encryption
)
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket

warnings.filterwarnings('ignore')

# Channeling the ether for vibrant terminal displays
from colorama import Fore, Style, init

init(autoreset=True)

# (Pyrmethus's Insight #2) Load environment variables from .env file with immediate override
load_dotenv(override=True)

# --- Configuration & Helpers ---
# Set decimal precision for financial calculations
getcontext().prec = 18
# (Pyrmethus's Insight #3) Enforce consistent rounding globally for deterministic financial flows
getcontext().rounding = ROUND_DOWN

# (Pyrmethus's Insight #35) Market Regime Enumeration
class MarketRegime(Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    CALM = "calm"

# (Pyrmethus's Insight #16) Custom exceptions for clearer error divination
class TradingBotError(Exception):
    """Base exception for all trading bot related errors."""

class InsufficientBalanceError(TradingBotError):
    """Raised when an operation cannot proceed due to insufficient funds."""

class OrderPlacementError(TradingBotError):
    """Raised when an order fails to be placed on the exchange."""

class MaxDrawdownExceeded(TradingBotError):
    """(Pyrmethus's Insight #36) Raised when maximum drawdown limit is breached."""

class RateLimitExceeded(TradingBotError):
    """(Pyrmethus's Insight #37) Raised when API rate limits are exceeded."""

# (Pyrmethus's Insight #38) Enhanced Performance Metrics with advanced analytics
@dataclass
class EnhancedPerformanceMetrics:
    """Track comprehensive bot performance metrics with advanced analytics."""
    total_orders_placed: int = 0
    successful_orders: int = 0
    failed_orders: int = 0
    total_fills: int = 0
    total_market_closes: int = 0
    total_pnl_realized: Decimal = Decimal("0")
    total_pnl_unrealized: Decimal = Decimal("0")
    total_volume_traded: Decimal = Decimal("0")
    total_fees_paid: Decimal = Decimal("0")
    winning_trades: int = 0
    losing_trades: int = 0
    max_drawdown: Decimal = Decimal("0")
    peak_equity: Decimal = Decimal("0")
    current_equity: Decimal = Decimal("0")
    start_time: float = field(default_factory=time.time)
    daily_pnl: dict[str, Decimal] = field(default_factory=dict)
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    fill_rates: dict[str, float] = field(default_factory=dict)
    slippage_stats: list[Decimal] = field(default_factory=list)

    def get_uptime_hours(self) -> float:
        return (time.time() - self.start_time) / 3600

    def get_success_rate(self) -> float:
        if self.total_orders_placed == 0:
            return 0.0
        return (self.successful_orders / self.total_orders_placed) * 100

    def get_win_rate(self) -> float:
        total_trades = self.winning_trades + self.losing_trades
        if total_trades == 0:
            return 0.0
        return (self.winning_trades / total_trades) * 100

    def get_profit_factor(self) -> float:
        if self.losing_trades == 0:
            return float('inf') if self.winning_trades > 0 else 0.0
        # This would need actual profit/loss amounts for accuracy
        return self.winning_trades / self.losing_trades

    def update_drawdown(self, current_equity: Decimal):
        """(Pyrmethus's Insight #36) Track maximum drawdown dynamically."""
        self.current_equity = current_equity
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        if self.peak_equity > 0:
            drawdown = (self.peak_equity - current_equity) / self.peak_equity
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown

    def calculate_sharpe_ratio(self, returns: list[float], risk_free_rate: float = 0.0) -> float:
        """(Pyrmethus's Insight #39) Calculate Sharpe ratio for risk-adjusted returns."""
        if len(returns) < 2:
            return 0.0

        avg_return = np.mean(returns)
        std_return = np.std(returns)

        if std_return == 0:
            return 0.0

        return (avg_return - risk_free_rate) / std_return

# (Pyrmethus's Insight #31) Database Manager for persistent state
class DatabaseManager:
    """Manages persistent storage of bot state and history."""
    def __init__(self, db_path: str = "pyrm_ultimate.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._init_tables()

    def _init_tables(self):
        """Initialize database schema."""
        with self._lock:
            cursor = self.conn.cursor()

            # Orders table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    order_link_id TEXT PRIMARY KEY,
                    order_id TEXT,
                    symbol TEXT,
                    side TEXT,
                    order_type TEXT,
                    quantity REAL,
                    price REAL,
                    status TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Trades table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id TEXT PRIMARY KEY,
                    order_link_id TEXT,
                    symbol TEXT,
                    side TEXT,
                    quantity REAL,
                    price REAL,
                    fee REAL,
                    pnl REAL,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_link_id) REFERENCES orders(order_link_id)
                )
            ''')

            # Performance snapshots
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS performance_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    equity REAL,
                    pnl_realized REAL,
                    pnl_unrealized REAL,
                    positions_count INTEGER,
                    metrics_json TEXT
                )
            ''')

            # Market regime history
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS market_regime (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    regime TEXT,
                    confidence REAL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            self.conn.commit()

    def save_order(self, order_data: dict):
        """Save order to database."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO orders 
                (order_link_id, order_id, symbol, side, order_type, quantity, price, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                order_data.get('orderLinkId'),
                order_data.get('orderId'),
                order_data.get('symbol'),
                order_data.get('side'),
                order_data.get('orderType'),
                float(order_data.get('qty', 0)),
                float(order_data.get('price', 0)),
                order_data.get('orderStatus', 'New')
            ))
            self.conn.commit()

    def save_performance_snapshot(self, metrics: EnhancedPerformanceMetrics, equity: Decimal):
        """Save performance snapshot for historical analysis."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO performance_snapshots 
                (equity, pnl_realized, pnl_unrealized, positions_count, metrics_json)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                float(equity),
                float(metrics.total_pnl_realized),
                float(metrics.total_pnl_unrealized),
                metrics.total_orders_placed,
                json.dumps(asdict(metrics), default=str)
            ))
            self.conn.commit()

    def close(self):
        """Close database connection."""
        self.conn.close()

# (Pyrmethus's Insight #40) Rate Limiter for API protection
class RateLimiter:
    """Implements sophisticated rate limiting with per-endpoint tracking."""
    def __init__(self):
        self.limits = {
            # Bybit rate limits (approximate)
            'place_order': {'calls': 100, 'period': 60},
            'cancel_order': {'calls': 100, 'period': 60},
            'get_orderbook': {'calls': 50, 'period': 1},
            'get_wallet_balance': {'calls': 120, 'period': 60},
            'default': {'calls': 120, 'period': 60}
        }
        self.calls: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def can_call(self, endpoint: str) -> bool:
        """Check if we can make a call to the endpoint."""
        with self._lock:
            limit = self.limits.get(endpoint, self.limits['default'])
            now = time.time()

            # Remove old calls outside the time window
            while self.calls[endpoint] and self.calls[endpoint][0] < now - limit['period']:
                self.calls[endpoint].popleft()

            # Check if we're under the limit
            return len(self.calls[endpoint]) < limit['calls']

    def record_call(self, endpoint: str):
        """Record a call to the endpoint."""
        with self._lock:
            self.calls[endpoint].append(time.time())

    def get_wait_time(self, endpoint: str) -> float:
        """Get time to wait before next call is allowed."""
        with self._lock:
            limit = self.limits.get(endpoint, self.limits['default'])
            if len(self.calls[endpoint]) < limit['calls']:
                return 0.0

            oldest_call = self.calls[endpoint][0]
            wait_time = (oldest_call + limit['period']) - time.time()
            return max(0.0, wait_time)

LOG_LEVEL = os.getenv("BYBIT_LOG_LEVEL", "INFO").upper()

# --- Logging Setup ---
class ColoredFormatter(logging.Formatter):
    """A mystical scribe that imbues log messages with color for the console."""
    COLORS = {
        'DEBUG': Fore.BLUE,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Style.BRIGHT + Fore.RED,
    }

    def format(self, record):
        log_message = super().format(record)
        return self.COLORS.get(record.levelname, Fore.WHITE) + log_message + Style.RESET_ALL

LOG_LEVEL = os.getenv("BYBIT_LOG_LEVEL", "INFO").upper()

# --- Logging Setup ---
class ColoredFormatter(logging.Formatter):
    """A mystical scribe that imbues log messages with color for the console."""
    COLORS = {
        'DEBUG': Fore.BLUE,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Style.BRIGHT + Fore.RED,
    }

    def format(self, record):
        log_message = super().format(record)
        return self.COLORS.get(record.levelname, Fore.WHITE) + log_message + Style.RESET_ALL

def setup_logging():
    """Setup enhanced logging with file rotation and Colorama for console."""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColoredFormatter(log_format))

    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        'pyrm_ultimate.log',
        maxBytes=10*1024*1024,
        backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(log_format))

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    return logging.getLogger(__name__)

logger = setup_logging()

def to_decimal(val: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Converts a value to Decimal, robustly handling various input types."""
    try:
        if isinstance(val, str):
            val = val.strip()
        return Decimal(str(val)) if val is not None and val != "" else default
    except (InvalidOperation, ValueError, TypeError):
        logger.error(Fore.RED + f"  # Failed to transmute value '{val}' into Decimal. Defaulting to {default}." + Style.RESET_ALL)
        return default

# (Pyrmethus's Insight #34) Secure API key management
class SecureConfig:
    """Manages encrypted API keys and sensitive configuration."""
    def __init__(self):
        self.cipher_suite = None
        self._init_encryption()

    def _init_encryption(self):
        """Initialize encryption for API keys."""
        key = os.getenv("ENCRYPTION_KEY")
        if not key:
            # Generate a new key if not provided
            key = Fernet.generate_key()
            logger.warning(Fore.YELLOW + f"  # Generated new encryption key. Save this in .env: ENCRYPTION_KEY={key.decode()}" + Style.RESET_ALL)
        else:
            key = key.encode() if isinstance(key, str) else key

        self.cipher_suite = Fernet(key)

    def encrypt_value(self, value: str) -> str:
        """Encrypt a sensitive value."""
        return self.cipher_suite.encrypt(value.encode()).decode()

    def decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt a sensitive value."""
        return self.cipher_suite.decrypt(encrypted_value.encode()).decode()

# Load configuration
secure_config = SecureConfig()
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
USE_TESTNET = False

# --- CRITICAL WARNING ---

logger = setup_logging()

def to_decimal(val: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Converts a value to Decimal, robustly handling various input types."""
    try:
        if isinstance(val, str):
            val = val.strip()
        return Decimal(str(val)) if val is not None and val != "" else default
    except (InvalidOperation, ValueError, TypeError):
        logger.error(Fore.RED + f"  # Failed to transmute value '{val}' into Decimal. Defaulting to {default}." + Style.RESET_ALL)
        return default

# (Pyrmethus's Insight #34) Secure API key management
class SecureConfig:
    """Manages encrypted API keys and sensitive configuration."""
    def __init__(self):
        self.cipher_suite = None
        self._init_encryption()

    def _init_encryption(self):
        """Initialize encryption for API keys."""
        key = os.getenv("ENCRYPTION_KEY")
        if not key:
            # Generate a new key if not provided
            key = Fernet.generate_key()
            logger.warning(Fore.YELLOW + f"  # Generated new encryption key. Save this in .env: ENCRYPTION_KEY={key.decode()}" + Style.RESET_ALL)
        else:
            key = key.encode() if isinstance(key, str) else key

        self.cipher_suite = Fernet(key)

    def encrypt_value(self, value: str) -> str:
        """Encrypt a sensitive value."""
        return self.cipher_suite.encrypt(value.encode()).decode()

    def decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt a sensitive value."""
        return self.cipher_suite.decrypt(encrypted_value.encode()).decode()

# Load configuration
secure_config = SecureConfig()
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
USE_TESTNET = False

# --- CRITICAL WARNING ---
logger.warning(Style.BRIGHT + Fore.LIGHTRED_EX + "="*60)
logger.warning(Style.BRIGHT + Fore.LIGHTRED_EX + "      *** ULTIMATE LIVE TRADING MODE ACTIVATED ***")
logger.warning(Style.BRIGHT + Fore.LIGHTRED_EX + "This bot is configured to execute trades on the LIVE market.")
logger.warning(Style.BRIGHT + Fore.LIGHTRED_EX + "Ensure your API keys in .env are for your LIVE account.")
logger.warning(Style.BRIGHT + Fore.LIGHTRED_EX + "           You are trading with REAL funds.")
logger.warning(Style.BRIGHT + Fore.LIGHTRED_EX + "      Proceed with caution. Monitor your account closely.")
logger.warning(Style.BRIGHT + Fore.LIGHTRED_EX + "="*60 + Style.RESET_ALL)

# (Pyrmethus's Insight #18) Circuit Breaker with enhanced recovery
class EnhancedCircuitBreaker:
    """Implements circuit breaker pattern with gradual recovery."""
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60, half_open_success_threshold: int = 3):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_success_threshold = half_open_success_threshold
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"
        self._lock = threading.Lock()
        self.failure_reasons: deque = deque(maxlen=10)

    def call_succeeded(self):
        with self._lock:
            if self.state == "HALF_OPEN":
                self.success_count += 1
                if self.success_count >= self.half_open_success_threshold:
                    logger.info(Fore.GREEN + f"  # Circuit breaker fully recovered after {self.success_count} successful calls." + Style.RESET_ALL)
                    self.state = "CLOSED"
                    self.failure_count = 0
                    self.success_count = 0
            elif self.state == "CLOSED":
                self.failure_count = max(0, self.failure_count - 1)

    def call_failed(self, reason: str = "Unknown"):
        with self._lock:
            self.failure_count += 1
            self.failure_reasons.append((time.time(), reason))
            self.last_failure_time = time.time()

            if self.state == "CLOSED" and self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.warning(Fore.YELLOW + f"  # Circuit breaker opened after {self.failure_count} failures. Recent failures: {list(self.failure_reasons)}" + Style.RESET_ALL)
            elif self.state == "HALF_OPEN":
                self.state = "OPEN"
                self.success_count = 0
                logger.warning(Fore.YELLOW + "  # Circuit breaker returned to OPEN state after HALF_OPEN test failed." + Style.RESET_ALL)

    def can_execute(self) -> bool:
        with self._lock:
            if self.state == "CLOSED":
                return True
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    self.success_count = 0
                    logger.info(Fore.CYAN + "  # Circuit breaker entering HALF_OPEN state. Testing API health..." + Style.RESET_ALL)
                    return True
                return False
            # HALF_OPEN
            return True

# (Pyrmethus's Insight #41) Market Microstructure Analyzer
class MarketMicrostructureAnalyzer:
    """Analyzes market microstructure for informed trading decisions."""
    def __init__(self, lookback_periods: int = 100):
        self.lookback_periods = lookback_periods
        self.order_flow_imbalance: dict[str, deque] = defaultdict(lambda: deque(maxlen=lookback_periods))
        self.spread_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=lookback_periods))
        self.volume_profile: dict[str, dict[Decimal, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        self._lock = threading.Lock()

    def update_order_flow(self, symbol: str, bid_volume: Decimal, ask_volume: Decimal):
        """Update order flow imbalance metrics."""
        with self._lock:
            total_volume = bid_volume + ask_volume
            if total_volume > 0:
                imbalance = (bid_volume - ask_volume) / total_volume
                self.order_flow_imbalance[symbol].append((time.time(), imbalance))

    def update_spread(self, symbol: str, spread: Decimal):
        """Update spread history."""
        with self._lock:
            self.spread_history[symbol].append((time.time(), spread))

    def get_order_flow_signal(self, symbol: str) -> float:
        """Get order flow imbalance signal (-1 to 1)."""
        with self._lock:
            if symbol not in self.order_flow_imbalance or len(self.order_flow_imbalance[symbol]) < 10:
                return 0.0

            recent_imbalances = [imb for _, imb in list(self.order_flow_imbalance[symbol])[-20:]]
            return float(np.mean(recent_imbalances))

    def detect_market_regime(self, symbol: str, price_history: deque) -> tuple[MarketRegime, float]:
        """Detect current market regime with confidence score."""
        if len(price_history) < 50:
            return MarketRegime.RANGING, 0.5

        prices = [float(p) for _, p in list(price_history)[-100:]]
        returns = np.diff(prices) / prices[:-1]

        # Calculate metrics
        volatility = np.std(returns)
        trend = np.polyfit(range(len(prices)), prices, 1)[0]
        mean_return = np.mean(returns)

        # Regime detection logic
        if abs(trend) > volatility * 2:
            regime = MarketRegime.TRENDING_UP if trend > 0 else MarketRegime.TRENDING_DOWN
            confidence = min(0.9, abs(trend) / (volatility * 3))
        elif volatility > np.percentile([np.std(returns[i:i+10]) for i in range(len(returns)-10)], 80):
            regime = MarketRegime.VOLATILE
            confidence = min(0.9, volatility / np.mean(np.abs(returns)))
        elif volatility < np.percentile([np.std(returns[i:i+10]) for i in range(len(returns)-10)], 20):
            regime = MarketRegime.CALM
            confidence = 0.7
        else:
            regime = MarketRegime.RANGING
            confidence = 0.6

        return regime, float(confidence)

# (Pyrmethus's Insight #42) Smart Order Manager with order layering
class SmartOrderManager:
    """Enhanced order manager with support for complex order types."""
    def __init__(self, db_manager: DatabaseManager):
        self._orders: dict[str, dict] = {}
        self._order_layers: dict[str, list[dict]] = defaultdict(list)  # For order layering
        self._iceberg_orders: dict[str, dict] = {}  # For iceberg orders
        self._lock = threading.Lock()
        self.db_manager = db_manager

    def add(self, order_response: dict):
        """Adds or updates an order."""
        order_link_id = order_response.get("orderLinkId")
        if not order_link_id:
            return

        with self._lock:
            self._orders[order_link_id] = order_response
            self.db_manager.save_order(order_response)

    def add_order_layer(self, base_order_id: str, layer_orders: list[dict]):
        """Add layered orders associated with a base order."""
        with self._lock:
            self._order_layers[base_order_id] = layer_orders
            for order in layer_orders:
                self.add(order)

    def add_iceberg_order(self, order_id: str, total_qty: Decimal, show_qty: Decimal):
        """Track iceberg order parameters."""
        with self._lock:
            self._iceberg_orders[order_id] = {
                'total_qty': total_qty,
                'show_qty': show_qty,
                'filled_qty': Decimal('0'),
                'active': True
            }

    def update_iceberg_fill(self, order_id: str, filled_qty: Decimal) -> Decimal | None:
        """Update iceberg order fill and return remaining quantity to place."""
        with self._lock:
            if order_id not in self._iceberg_orders:
                return None

            iceberg = self._iceberg_orders[order_id]
            iceberg['filled_qty'] += filled_qty

            remaining = iceberg['total_qty'] - iceberg['filled_qty']
            if remaining <= 0:
                iceberg['active'] = False
                return None

            return min(remaining, iceberg['show_qty'])

    def remove(self, order_link_id: str) -> dict | None:
        """Removes an order and its associated layers."""
        with self._lock:
            # Remove layered orders if this is a base order
            if order_link_id in self._order_layers:
                for layer_order in self._order_layers[order_link_id]:
                    self._orders.pop(layer_order.get('orderLinkId'), None)
                del self._order_layers[order_link_id]

            return self._orders.pop(order_link_id, None)

    def get_all_orders(self) -> list[dict]:
        """Returns all tracked orders."""
        with self._lock:
            return list(self._orders.values())

    def get_orders_for_symbol(self, symbol: str) -> list[dict]:
        """Returns all tracked orders for a specific symbol."""
        with self._lock:
            return [o for o in self._orders.values() if o.get('symbol') == symbol]

# --- Enhanced WebSocket Manager ---
class EnhancedBybitWebSocketManager:
    """Enhanced WebSocket manager with improved reliability and features."""
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        self.ws_public: WebSocket | None = None
        self.ws_private: WebSocket | None = None
        self.api_key, self.api_secret, self.testnet = api_key, api_secret, testnet
        self.market_data: dict[str, Any] = {}
        self.positions: dict[str, Any] = {}
        self.executions: dict[str, list[dict]] = defaultdict(list)  # (Pyrmethus's Insight #43) Track executions
        self.price_history: dict[str, deque[tuple[float, Decimal]]] = {}
        self._lock = threading.Lock()
        self._last_ws_heartbeat: dict[str, float] = {}
        self._reconnect_attempts: dict[str, int] = {}
        self._max_reconnect_attempts = 5
        self._reconnect_delay_base = 1
        self._message_sequence: dict[str, int] = defaultdict(int)  # (Pyrmethus's Insight #44) Message sequencing
        self.microstructure_analyzer = MarketMicrostructureAnalyzer()

    def _init_ws(self, private: bool):
        """Forging the WebSocket connection with enhanced error handling."""
        ws_type = "private" if private else "linear"
        try:
            ws_obj = WebSocket(
                testnet=self.testnet,
                channel_type=ws_type,
                api_key=self.api_key if private else None,
                api_secret=self.api_secret if private else None,
                ping_interval=20,  # (Pyrmethus's Insight #45) Custom ping interval
                ping_timeout=10,
                max_data_length=2**20  # 1MB max message size
            )

            if not ws_obj.is_connected():
                logger.error(Fore.RED + f"  # The {ws_type} WebSocket failed to establish a stable link." + Style.RESET_ALL)
                self._handle_reconnect(private)
                return

            if private:
                self.ws_private = ws_obj
                logger.info(Fore.CYAN + "  # Private WebSocket channel opened for personal insights." + Style.RESET_ALL)
            else:
                self.ws_public = ws_obj
                logger.info(Fore.CYAN + "  # Public WebSocket channel opened for market whispers." + Style.RESET_ALL)

            self._reconnect_attempts[ws_type] = 0
            self._last_ws_heartbeat[ws_type] = time.time()

        except Exception as e:
            logger.critical(Fore.RED + f"  # Catastrophic failure initializing {ws_type} WebSocket: {e}" + Style.RESET_ALL, exc_info=True)
            self._handle_reconnect(private)

    async def _handle_reconnect(self, private: bool):
        """Enhanced reconnection with jittered exponential backoff."""
        ws_type = "private" if private else "linear"
        self._reconnect_attempts[ws_type] = self._reconnect_attempts.get(ws_type, 0) + 1
        attempt = self._reconnect_attempts[ws_type]

        if attempt > self._max_reconnect_attempts:
            logger.critical(Fore.RED + f"  # Max reconnection attempts reached for {ws_type} WebSocket." + Style.RESET_ALL)
            return

        # Add jitter to prevent thundering herd
        jitter = random.uniform(0, 0.3)
        backoff_time = min(60, self._reconnect_delay_base * (2 ** (attempt - 1)) * (1 + jitter))

        logger.warning(Fore.YELLOW + f"  # Reconnecting {ws_type} WebSocket (Attempt {attempt}/{self._max_reconnect_attempts}) in {backoff_time:.1f}s..." + Style.RESET_ALL)
        await asyncio.sleep(backoff_time)
        self._init_ws(private)

    def handle_orderbook(self, msg: dict):
        """Enhanced orderbook handling with microstructure analysis."""
        try:
            data = msg.get("data", {})
            symbol = data.get("s")
            sequence = msg.get("seq", 0)

            if symbol:
                with self._lock:
                    # Check message sequence
                    if sequence <= self._message_sequence[f"{symbol}_orderbook"]:
                        logger.debug(f"  # Stale orderbook message for {symbol} (seq: {sequence})")
                        return

                    self._message_sequence[f"{symbol}_orderbook"] = sequence

                    entry = self.market_data.setdefault(symbol, {})
                    entry["orderbook"] = data
                    entry["timestamp"] = msg.get("ts")
                    self._last_ws_heartbeat["linear"] = time.time()

                    # Calculate metrics
                    bids = data.get("b", [])
                    asks = data.get("a", [])
                    if bids and asks:
                        best_bid = to_decimal(bids[0][0])
                        best_ask = to_decimal(asks[0][0])
                        mid_price = (best_bid + best_ask) / Decimal('2')
                        spread = best_ask - best_bid

                        # Update microstructure analyzer
                        bid_volume = sum(to_decimal(b[1]) for b in bids[:5])
                        ask_volume = sum(to_decimal(a[1]) for a in asks[:5])
                        self.microstructure_analyzer.update_order_flow(symbol, bid_volume, ask_volume)
                        self.microstructure_analyzer.update_spread(symbol, spread)

                        # Store price history
                        timestamp = float(msg.get("ts")) / 1000
                        if symbol not in self.price_history:
                            self.price_history[symbol] = deque(maxlen=3600)  # 1 hour at 1-second intervals

                        self.price_history[symbol].append((timestamp, mid_price))

        except Exception as e:
            logger.error(Fore.RED + f"  # Error in orderbook handling: {e}" + Style.RESET_ALL, exc_info=True)

    def handle_execution(self, msg: dict):
        """(Pyrmethus's Insight #43) Handle execution messages for fill tracking."""
        try:
            data = msg.get("data", [])
            for execution in data:
                symbol = execution.get("symbol")
                if symbol:
                    with self._lock:
                        self.executions[symbol].append(execution)
                        # Keep only recent executions
                        if len(self.executions[symbol]) > 100:
                            self.executions[symbol] = self.executions[symbol][-100:]

                        self._last_ws_heartbeat["private"] = time.time()

        except Exception as e:
            logger.error(Fore.RED + f"  # Error handling execution data: {e}" + Style.RESET_ALL, exc_info=True)

    def handle_position(self, msg: dict):
        """Enhanced position handling with P&L tracking."""
        try:
            data = msg.get("data", [])
            for position in data:
                symbol = position.get("symbol")
                if symbol:
                    with self._lock:
                        self.positions[symbol] = position
                        self._last_ws_heartbeat["private"] = time.time()

        except Exception as e:
            logger.error(Fore.RED + f"  # Error handling position data: {e}" + Style.RESET_ALL, exc_info=True)

    async def subscribe_public(self, symbols: list[str]):
        """Enhanced public subscription with trade data."""
        if not self.ws_public or not self.is_public_connected():
            await self._handle_reconnect(private=False)
            if not self.ws_public or not self.is_public_connected():
                logger.error(Fore.RED + "  # Failed to establish public WebSocket." + Style.RESET_ALL)
                return

        await asyncio.sleep(0.5)
        for symbol in symbols:
            try:
                # Subscribe to orderbook
                self.ws_public.orderbook_stream(depth=25, symbol=symbol, callback=self.handle_orderbook)
                # Subscribe to trades for better market insight
                self.ws_public.trade_stream(symbol=symbol, callback=lambda msg: logger.debug(f"Trade: {msg}"))
                logger.info(Fore.CYAN + f"  # Subscribed to enhanced market streams for {symbol}." + Style.RESET_ALL)
            except Exception as e:
                logger.error(Fore.RED + f"  # Failed to subscribe to {symbol}: {e}" + Style.RESET_ALL)

    async def subscribe_private(self):
        """Enhanced private subscription with execution tracking."""
        if not self.ws_private or not self.is_private_connected():
            await self._handle_reconnect(private=True)
            if not self.ws_private or not self.is_private_connected():
                logger.error(Fore.RED + "  # Failed to establish private WebSocket." + Style.RESET_ALL)
                return

        await asyncio.sleep(0.5)
        try:
            self.ws_private.position_stream(callback=self.handle_position)
            self.ws_private.execution_stream(callback=self.handle_execution)  # Track fills
            self.ws_private.order_stream(callback=lambda msg: logger.debug(f"Order update: {msg}"))
            logger.info(Fore.CYAN + "  # Subscribed to enhanced private streams." + Style.RESET_ALL)
        except Exception as e:
            logger.error(Fore.RED + f"  # Failed to subscribe to private streams: {e}" + Style.RESET_ALL)

    def stop(self):
        """Gracefully close WebSocket connections."""
        for ws, name in [(self.ws_public, "public"), (self.ws_private, "private")]:
            if ws:
                try:
                    ws.exit()
                    logger.info(Fore.MAGENTA + f"  # {name.capitalize()} WebSocket gracefully closed." + Style.RESET_ALL)
                except Exception as e:
                    logger.error(Fore.RED + f"  # Error closing {name} WebSocket: {e}" + Style.RESET_ALL)

    def is_public_connected(self) -> bool:
        """Check public WebSocket health."""
        return (self.ws_public is not None and
                self.ws_public.is_connected() and
                (time.time() - self._last_ws_heartbeat.get("linear", 0)) < 30)

    def is_private_connected(self) -> bool:
        """Check private WebSocket health."""
        return (self.ws_private is not None and
                self.ws_private.is_connected() and
                (time.time() - self._last_ws_heartbeat.get("private", 0)) < 30)

# --- Enhanced Trading Bot Core ---
class UltimateBybitTradingBot:
    """Ultimate Bybit trading bot with advanced features and robust architecture."""
    def __init__(self, api_key: str, api_secret: str, testnet: bool, dry_run: bool):
        self.dry_run = dry_run
        self.rate_limiter = RateLimiter()
        self.db_manager = DatabaseManager()

        # Initialize HTTP session with connection pooling
        self.session = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret)
        self.ws_manager = EnhancedBybitWebSocketManager(api_key, api_secret, testnet)
        self.order_manager = SmartOrderManager(self.db_manager)
        self.metrics = EnhancedPerformanceMetrics()
        self.circuit_breaker = EnhancedCircuitBreaker()

        # Strategies
        self.strategies: list[Callable] = []
        self.symbol_info: dict[str, Any] = {}

        # Configuration
        self.max_open_positions = int(os.getenv("BOT_MAX_OPEN_POSITIONS", 5))
        self.max_drawdown_pct = to_decimal(os.getenv("BOT_MAX_DRAWDOWN_PCT", "0.2"))  # 20% default
        self.category = os.getenv("BYBIT_CATEGORY", "linear")
        self.min_notional_usd = to_decimal(os.getenv("BOT_MIN_NOTIONAL_USD", "5"))
        self.api_timeout_s = 10
        self.account_refresh_interval = int(os.getenv("BOT_ACCOUNT_REFRESH_INTERVAL_S", "300"))
        self._last_account_refresh_time = 0
        self._cached_account_info = None

        # Performance tracking
        self._performance_snapshot_interval = 300  # 5 minutes
        self._last_performance_snapshot = 0

        # Executor for parallel operations
        self.executor = ThreadPoolExecutor(max_workers=4)

    async def _http_call(self, method: Callable, **kwargs) -> dict | None:
        """Enhanced HTTP call with rate limiting and circuit breaker."""
        endpoint = method.__name__

        # Check rate limits
        if not self.rate_limiter.can_call(endpoint):
            wait_time = self.rate_limiter.get_wait_time(endpoint)
            logger.warning(Fore.YELLOW + f"  # Rate limit reached for {endpoint}. Waiting {wait_time:.1f}s..." + Style.RESET_ALL)
            await asyncio.sleep(wait_time)

        # Check circuit breaker
        if not self.circuit_breaker.can_execute():
            logger.warning(Fore.YELLOW + f"  # Circuit breaker OPEN. Blocking {endpoint}." + Style.RESET_ALL)
            return None

        # Record the API call
        self.rate_limiter.record_call(endpoint)

        for attempt in range(3):
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(method, **kwargs),
                    timeout=self.api_timeout_s
                )

                if response and response.get('retCode') == 0:
                    self.circuit_breaker.call_succeeded()
                    return response
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.circuit_breaker.call_failed(f"{endpoint}: {error_msg}")

                # Handle specific error codes
                if response and response.get('retCode') == 10003:  # Rate limit error
                    raise RateLimitExceeded(f"Rate limit exceeded: {error_msg}")

                return response

            except asyncio.TimeoutError:
                logger.warning(Fore.YELLOW + f"  # {endpoint} timed out (attempt {attempt+1}/3)" + Style.RESET_ALL)
                self.circuit_breaker.call_failed(f"{endpoint}: Timeout")
            except RateLimitExceeded:
                logger.error(Fore.RED + f"  # Rate limit exceeded for {endpoint}. Backing off..." + Style.RESET_ALL)
                await asyncio.sleep(60)  # Back off for 1 minute on rate limit
            except Exception as e:
                logger.error(Fore.RED + f"  # {endpoint} failed: {e}" + Style.RESET_ALL, exc_info=True)
                self.circuit_breaker.call_failed(f"{endpoint}: {e!s}")

            await asyncio.sleep(1 * (2 ** attempt))

        logger.critical(Fore.RED + f"  # All attempts to call {endpoint} failed." + Style.RESET_ALL)
        return None

    async def fetch_symbol_info(self, symbols: list[str]):
        """Fetch and validate symbol information."""
        logger.info(Fore.CYAN + f"  # Fetching instrument info for: {', '.join(symbols)}" + Style.RESET_ALL)

        # Batch fetch if possible
        response = await self._http_call(self.session.get_instruments_info, category=self.category)

        if response and response.get('retCode') == 0:
            instruments = response['result']['list']
            for instrument in instruments:
                symbol = instrument.get('symbol')
                if symbol in symbols:
                    try:
                        self.symbol_info[symbol] = {
                            "minOrderQty": to_decimal(instrument['lotSizeFilter']['minOrderQty']),
                            "qtyStep": to_decimal(instrument['lotSizeFilter']['qtyStep']),
                            "tickSize": to_decimal(instrument['priceFilter']['tickSize']),
                            "minPrice": to_decimal(instrument['priceFilter'].get('minPrice', '0')),
                            "maxPrice": to_decimal(instrument['priceFilter'].get('maxPrice', '999999')),
                            "status": instrument.get('status', 'Trading')
                        }
                        logger.info(Fore.GREEN + f"  # Loaded info for {symbol}" + Style.RESET_ALL)
                    except (KeyError, IndexError) as e:
                        logger.error(Fore.RED + f"  # Malformed instrument data for {symbol}: {e}" + Style.RESET_ALL)

        # Verify all symbols were loaded
        missing_symbols = [s for s in symbols if s not in self.symbol_info]
        if missing_symbols:
            logger.error(Fore.RED + f"  # Failed to load info for: {', '.join(missing_symbols)}" + Style.RESET_ALL)

    def add_strategy(self, strategy_func: Callable):
        """Add a strategy to the bot's arsenal."""
        self.strategies.append(strategy_func)
        logger.info(Fore.MAGENTA + f"  # Strategy '{strategy_func.__name__}' added to bot." + Style.RESET_ALL)

    def _round_qty(self, symbol: str, quantity: Decimal) -> Decimal:
        """Round quantity to valid step size."""
        info = self.symbol_info.get(symbol)
        if not info or info["qtyStep"] <= 0:
            return quantity
        return (quantity / info["qtyStep"]).to_integral_value(rounding=ROUND_DOWN) * info["qtyStep"]

    def _round_price(self, symbol: str, price: Decimal) -> Decimal:
        """Round price to valid tick size."""
        info = self.symbol_info.get(symbol)
        if not info or info["tickSize"] <= 0:
            return price
        return price.quantize(info["tickSize"], rounding=ROUND_DOWN)

    async def calculate_position_size(self, symbol: str, capital_percentage: float,
                                    price: Decimal, account_info: dict) -> Decimal:
        """Calculate position size with advanced risk management."""
        # Get available balance
        available_balance = to_decimal(
            next((c.get('availableToWithdraw', '0')
                  for acct in account_info.get('list', [])
                  for c in acct.get('coin', [])
                  if c.get('coin') == 'USDT'), '0')
        )

        if available_balance <= 0 or price <= 0:
            return Decimal('0')

        # Check drawdown limits
        current_equity = to_decimal(account_info.get('result', {}).get('list', [{}])[0].get('totalEquity', '0'))
        self.metrics.update_drawdown(current_equity)

        if self.metrics.max_drawdown >= self.max_drawdown_pct:
            logger.warning(Fore.RED + f"  # Max drawdown exceeded ({self.metrics.max_drawdown:.2%}). Halting new positions." + Style.RESET_ALL)
            raise MaxDrawdownExceeded(f"Drawdown {self.metrics.max_drawdown:.2%} exceeds limit {self.max_drawdown_pct:.2%}")

        # Calculate base position size
        target_capital = available_balance * to_decimal(str(capital_percentage))

        # Apply Kelly Criterion adjustment (simplified)
        win_rate = self.metrics.get_win_rate() / 100
        if win_rate > 0 and self.metrics.losing_trades > 0:
            kelly_fraction = max(0.1, min(0.25, win_rate - (1 - win_rate)))
            target_capital *= to_decimal(str(kelly_fraction))

        qty = self._round_qty(symbol, target_capital / price)

        # Validate against symbol constraints
        if symbol not in self.symbol_info:
            return Decimal('0')

        min_order_qty = self.symbol_info[symbol]["minOrderQty"]
        if qty < min_order_qty:
            return Decimal('0')

        # Check minimum notional
        if (qty * price) < self.min_notional_usd:
            return Decimal('0')

        return qty

    async def place_order_with_layers(self, symbol: str, side: str, base_price: Decimal,
                                     base_qty: Decimal, layers: int = 1, layer_spread: Decimal = Decimal('0.0005')) -> list[dict]:
        """Place orders with optional layering for better fills."""
        orders_placed = []

        # Calculate layer quantities
        qty_per_layer = self._round_qty(symbol, base_qty / Decimal(layers))

        for i in range(layers):
            if side == "Buy":
                layer_price = base_price * (Decimal('1') - layer_spread * Decimal(i))
            else:
                layer_price = base_price * (Decimal('1') + layer_spread * Decimal(i))

            layer_price = self._round_price(symbol, layer_price)

            order_result = await self.place_order(
                symbol=symbol,
                side=side,
                order_type="Limit",
                qty=str(qty_per_layer),
                price=str(layer_price),
                timeInForce="GTC",
                orderLinkId=f"layer_{side.lower()}_{symbol}_{i}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
            )

            if order_result:
                orders_placed.append(order_result)

        # Track layered orders
        if orders_placed and layers > 1:
            self.order_manager.add_order_layer(orders_placed[0]['orderLinkId'], orders_placed[1:])

        return orders_placed

    async def place_order(self, **kwargs) -> dict | None:
        """Place order with comprehensive tracking and error handling."""
        self.metrics.total_orders_placed += 1

        # Convert numeric values to strings
        for k in ("price", "qty", "stopLoss", "takeProfit"):
            if k in kwargs and kwargs[k] is not None:
                kwargs[k] = str(kwargs[k])

        if self.dry_run:
            mock_response = {
                "orderId": f"dry_{int(time.time()*1000)}",
                "orderLinkId": kwargs.get("orderLinkId", f"dry_link_{int(time.time()*1000)}"),
                **kwargs
            }
            logger.info(Fore.YELLOW + f"[DRY RUN] Would place order: {kwargs}" + Style.RESET_ALL)
            self.order_manager.add(mock_response)
            self.metrics.successful_orders += 1
            return mock_response

        try:
            order_response = await self._http_call(self.session.place_order, category=self.category, **kwargs)

            if order_response and order_response.get('retCode') == 0:
                result = order_response['result']
                logger.info(Fore.GREEN + f"  # Order placed: {result}" + Style.RESET_ALL)
                self.order_manager.add({**result, "symbol": kwargs.get("symbol")})
                self.metrics.successful_orders += 1

                # Update volume traded
                qty = to_decimal(kwargs.get('qty', '0'))
                price = to_decimal(kwargs.get('price', '0'))
                self.metrics.total_volume_traded += qty * price

                return result
            error_msg = order_response.get('retMsg') if order_response else 'No response'
            logger.error(Fore.RED + f"  # Order placement failed: {error_msg}" + Style.RESET_ALL)
            self.metrics.failed_orders += 1
            raise OrderPlacementError(f"Order placement failed: {error_msg}")

        except Exception:
            self.metrics.failed_orders += 1
            raise

    async def cancel_order(self, symbol: str, order_link_id: str) -> bool:
        """Cancel order with tracking."""
        if self.dry_run:
            logger.info(Fore.YELLOW + f"[DRY RUN] Would cancel order: {order_link_id}" + Style.RESET_ALL)
            self.order_manager.remove(order_link_id)
            return True

        response = await self._http_call(
            self.session.cancel_order,
            category=self.category,
            symbol=symbol,
            orderLinkId=order_link_id
        )

        if response and response.get('retCode') == 0:
            logger.info(Fore.GREEN + f"  # Order cancelled: {response['result']}" + Style.RESET_ALL)
            self.order_manager.remove(order_link_id)
            return True

        logger.error(Fore.RED + f"  # Failed to cancel order {order_link_id}" + Style.RESET_ALL)
        return False

    async def cancel_all_tracked_orders(self):
        """Cancel all tracked orders efficiently."""
        logger.info(Fore.MAGENTA + "  # Cancelling all tracked orders..." + Style.RESET_ALL)
        orders = self.order_manager.get_all_orders()

        if not orders:
            logger.info(Fore.CYAN + "  # No orders to cancel." + Style.RESET_ALL)
            return

        # Group by symbol for batch cancellation
        orders_by_symbol = defaultdict(list)
        for order in orders:
            orders_by_symbol[order['symbol']].append(order)

        cancel_tasks = []
        for symbol, symbol_orders in orders_by_symbol.items():
            # Bybit supports batch cancel
            order_ids = [o['orderLinkId'] for o in symbol_orders]
            if len(order_ids) == 1:
                cancel_tasks.append(self.cancel_order(symbol, order_ids[0]))
            else:
                # For multiple orders, could implement batch cancel
                for order_id in order_ids:
                    cancel_tasks.append(self.cancel_order(symbol, order_id))

        await asyncio.gather(*cancel_tasks, return_exceptions=True)
        logger.info(Fore.MAGENTA + "  # All orders cancelled." + Style.RESET_ALL)

    async def update_performance_snapshot(self, account_info: dict):
        """Save performance snapshot to database."""
        if time.time() - self._last_performance_snapshot < self._performance_snapshot_interval:
            return

        current_equity = to_decimal(
            account_info.get('result', {}).get('list', [{}])[0].get('totalEquity', '0')
        )

        # Calculate unrealized P&L from positions
        unrealized_pnl = Decimal('0')
        for position in self.ws_manager.positions.values():
            pos_pnl = to_decimal(position.get('unrealisedPnl', '0'))
            unrealized_pnl += pos_pnl

        self.metrics.total_pnl_unrealized = unrealized_pnl
        self.metrics.update_drawdown(current_equity)

        # Save snapshot
        self.db_manager.save_performance_snapshot(self.metrics, current_equity)
        self._last_performance_snapshot = time.time()

        logger.info(
            Fore.LIGHTCYAN_EX +
            f"  # Performance: Equity={current_equity:.2f} | " +
            f"Realized P&L={self.metrics.total_pnl_realized:.2f} | " +
            f"Unrealized P&L={unrealized_pnl:.2f} | " +
            f"Max DD={self.metrics.max_drawdown:.2%} | " +
            f"Win Rate={self.metrics.get_win_rate():.1f}%" +
            Style.RESET_ALL
        )

    async def _async_termux_toast(self, message: str):
        """Send notification via Termux."""
        try:
            process = await asyncio.create_subprocess_exec(
                "termux-toast", message,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
        except Exception:
            pass  # Silently fail if termux-toast not available

    async def run(self, symbols: list[str], interval: int):
        """Main bot execution loop with enhanced monitoring."""
        await self.fetch_symbol_info(symbols)
        await self.ws_manager.subscribe_public(symbols)
        await self.ws_manager.subscribe_private()

        logger.info(Fore.MAGENTA + "  # Ultimate Pyrmethus bot commencing operations..." + Style.RESET_ALL)

        loop_count = 0
        try:
            while True:
                loop_start = time.monotonic()

                # Health checks
                if not self.ws_manager.is_public_connected():
                    logger.warning(Fore.YELLOW + "  # Public WS disconnected. Reconnecting..." + Style.RESET_ALL)
                    await self.ws_manager.subscribe_public(symbols)

                if not self.ws_manager.is_private_connected():
                    logger.warning(Fore.YELLOW + "  # Private WS disconnected. Reconnecting..." + Style.RESET_ALL)
                    await self.ws_manager.subscribe_private()

                # Gather market data
                market_data_tasks = [self._get_market_data(s) for s in symbols]
                all_market_data_list = await asyncio.gather(*market_data_tasks)
                all_market_data = {s: md for s, md in zip(symbols, all_market_data_list, strict=False) if md}

                # Refresh account info if needed
                account_info = await self._get_account_info()

                if not account_info:
                    logger.critical(Fore.RED + "  # Failed to get account info. Skipping cycle." + Style.RESET_ALL)
                    await asyncio.sleep(interval)
                    continue

                # Update performance metrics
                await self.update_performance_snapshot(account_info)

                # Execute strategies
                if self.strategies and all_market_data:
                    for strategy in self.strategies:
                        try:
                            await strategy(self, all_market_data, account_info, symbols)
                        except MaxDrawdownExceeded:
                            logger.critical(Fore.RED + "  # MAX DRAWDOWN EXCEEDED. Halting all trading." + Style.RESET_ALL)
                            await self.cancel_all_tracked_orders()
                            await self._async_termux_toast("⚠️ Pyrmethus: MAX DRAWDOWN EXCEEDED! Trading halted.")
                            return  # Exit the bot
                        except Exception as e:
                            logger.error(Fore.RED + f"  # Strategy error: {e}" + Style.RESET_ALL, exc_info=True)

                # Status update
                loop_count += 1
                if loop_count % 10 == 0:
                    elapsed = time.monotonic() - loop_start
                    logger.info(
                        Fore.LIGHTCYAN_EX +
                        f"  # Cycle {loop_count} | Time: {elapsed:.2f}s | " +
                        f"Orders: {self.metrics.successful_orders}/{self.metrics.total_orders_placed} | " +
                        f"Win Rate: {self.metrics.get_win_rate():.1f}% | " +
                        f"Max DD: {self.metrics.max_drawdown:.2%}" +
                        Style.RESET_ALL
                    )

                # Sleep for remainder of interval
                elapsed = time.monotonic() - loop_start
                await asyncio.sleep(max(0, interval - elapsed))

        except asyncio.CancelledError:
            logger.info(Fore.YELLOW + "  # Bot operations cancelled." + Style.RESET_ALL)
        except KeyboardInterrupt:
            logger.info(Fore.YELLOW + "  # Bot interrupted by user." + Style.RESET_ALL)
