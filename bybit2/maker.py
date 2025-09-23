#!/usr/bin/env python3
"""Bybit v5 Market-Making Bot - Ultra Enhanced Version with Latest API Integration

This is an advanced market-making bot for Bybit's v5 API, designed for
production-ready trading with comprehensive error handling, risk
management, and performance optimizations.

This version is optimized for Termux environments on Android.

Enhanced Features:
- Latest Bybit API v5 Authentication (X-BAPI-* headers)
- Official pybit library integration (with fallback)
- Centralized Configuration Management
- Multi-Symbol Support Structure
- Advanced API Client with Robust Error Handling & Rate Limiting
- Smart Order Placement & Management Strategies (with cancel-replace)
- Real-time Performance Analytics and Monitoring
- Advanced inventory management with hedging capabilities
- WebSocket support with robust reconnection and message handling (Private and Public)
- File-based state persistence with atomic writes and expiration
- Comprehensive risk management metrics and calculations
- Volatility-based order sizing (conceptually integrated)
- Structured JSON logging
- Graceful shutdown procedures
- Improved Decimal precision handling
- Symbol-specific configuration and caching (including exchange info for precision)
- Enhanced error recovery and resilience
- Termux-specific setup instructions and graceful psutil handling
- PnL tracking and risk metrics updates on trade fills
"""

# --- Termux Installation and Setup Instructions ---
TERMUX_INSTALL_INSTRUCTIONS = """
=====================================================
 Termux Setup Instructions for Bybit Market Maker Bot
=====================================================

1. Update Termux packages:
   pkg update && pkg upgrade -y

2. Install Python and necessary libraries:
   pkg install python -y
   pip install --upgrade pip
   pip install pybit colorama structlog numpy pandas python-dotenv aiohttp websockets psutil

   # Note: psutil might require specific handling or might not be fully functional without root.
   # If 'pip install psutil' fails, try 'pip install psutil --no-cache-dir'.

3. Set Environment Variables:
   You NEED to set your Bybit API Key and Secret. You can do this temporarily for the current session,
   or permanently by editing your Termux shell profile (e.g., ~/.bashrc or ~/.zshrc).

   For the current session (run these commands in Termux before running the script):
   export BYBIT_API_KEY="YOUR_ACTUAL_BYBIT_API_KEY"
   export BYBIT_API_SECRET="YOUR_ACTUAL_BYBIT_API_SECRET"
   export BYBIT_TESTNET="true"  # Set to "false" for mainnet

   Example:
   export BYBIT_API_KEY="xxxxxxx"
   export BYBIT_API_SECRET="yyyyyyy"
   export BYBIT_TESTNET="true"

4. Run the Bot:
   python your_bot_script_name.py

5. Running in Background (Recommended for long-term execution):
   Use 'nohup' to keep the script running even if you close Termux.
   nohup python your_bot_script_name.py > bot.log 2>&1 &

   To view logs while running:
   tail -f bot.log

   To stop the bot:
   Find its PID using 'pgrep -f your_bot_script_name.py'
   Then kill the process using 'kill PID' (e.g., kill 12345)

=====================================================
"""

# --- Standard Library Imports ---
import asyncio
import gc
import hashlib
import hmac
import json
import logging
import logging.handlers
import os
import signal
import sys
import time
import urllib.parse
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import aiohttp
import websockets

# --- Third-Party Library Imports ---
# Attempt to import optional libraries and handle ImportError
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    from pybit.unified_trading import HTTP as PybitHTTP, WebSocket as PybitWebSocket
    PYBIT_AVAILABLE = True
except ImportError:
    PYBIT_AVAILABLE = False

try:
    from colorama import Fore, Style, init
    init(autoreset=True)
except ImportError:
    class DummyColor: # Dummy class if colorama is not installed
        def __getattr__(self, name): return ""
    Fore = DummyColor()
    Style = DummyColor()

# --- Decimal Configuration ---
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation, getcontext

getcontext().prec = 30
getcontext().rounding = ROUND_HALF_UP

# --- Constants and Global Setup ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
IS_TESTNET = os.getenv("BYBIT_TESTNET", "true").lower() in ["true", "1", "yes", "y"]

STATE_DIR = os.path.join(os.path.expanduser("~"), ".bybit_market_maker_state")
LOG_DIR = os.path.join(os.path.expanduser("~"), "bybit_bot_logs")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(STATE_DIR, exist_ok=True)

# --- Logging Setup ---
logger = logging.getLogger('BybitMMBot')
trade_logger = logging.getLogger('TradeLogger')

def setup_logging():
    """Configures logging for the bot with JSON format, colors, and file output."""
    log_level = logging.DEBUG if os.getenv("DEBUG_MODE", "false").lower() == "true" else logging.INFO

    log_handlers = []

    # Console Handler (with colors if available)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    if PYBIT_AVAILABLE and not isinstance(Fore, DummyColor): # Check if colorama is working
         try:
            import structlog
            from structlog import get_logger as structlog_get_logger
            from structlog.dev import ConsoleRenderer
            from structlog.stdlib import ProcessorFormatter

            structlog.configure(
                processors=[
                    structlog.stdlib.add_log_level, structlog.stdlib.add_logger_name,
                    structlog.processors.TimeStamper(fmt="iso"), structlog.processors.format_exc_info,
                    structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
                ],
                wrapper_class=structlog.stdlib.BoundLogger, logger_factory=structlog.stdlib.LoggerFactory(),
                cache_logger_on_first_use=True,
            )
            console_formatter = ProcessorFormatter(
                processor=ConsoleRenderer(colors=True, pad_eventual_key=10),
                foreign_pre_chain=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.stdlib.add_log_level, structlog.stdlib.add_logger_name,
                    structlog.processors.TimeStamper(fmt="iso"), structlog.processors.format_exc_info
                ]
            )
            console_handler.setFormatter(console_formatter)
            log_handlers.append(console_handler)
            logger.info("Using structlog for colored console logging.")
         except ImportError:
            logger.warning("structlog not found for colored logging. Falling back to basic formatter.")
            basic_formatter = logging.Formatter(f'%(asctime)s - {Fore.CYAN}%(levelname)s{Style.RESET_ALL} - %(name)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            console_handler.setFormatter(basic_formatter)
            log_handlers.append(console_handler)

    else: # Colorama not available or structlog import failed
        basic_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        console_handler.setFormatter(basic_formatter)
        log_handlers.append(console_handler)
        if isinstance(Fore, DummyColor):
             logger.warning("Colorama not found. Terminal output will not be colored. Install with: pip install colorama")

    # File Handler (Main Bot Log - JSON format)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_handler = logging.FileHandler(os.path.join(LOG_DIR, f"bot_{timestamp_str}.log"), mode='w', encoding='utf-8')
    file_handler.setLevel(log_level)
    try:
        from structlog import processors
        json_formatter = ProcessorFormatter(
            processor=processors.JSONRenderer(),
            foreign_pre_chain=[
                processors.add_log_level, processors.add_logger_name,
                processors.TimeStamper(fmt="iso"), processors.format_exc_info,
                processors.format_exc_info, # Ensure exception info is JSON formatted
                processors.UnicodeEncoder(), # Ensure unicode compatibility
                processors.StackInfoRenderer(), # Add stack info if available
                processors.format_exc_info, # Re-apply format_exc_info after unicode encoding
                processors.ExceptionRenderer(), # Render exception details
                processors.JSONRenderer() # Final JSON rendering
            ]
        )
        file_handler.setFormatter(json_formatter)
        log_handlers.append(file_handler)
        logger.info("Using structlog for JSON file logging.")
    except ImportError:
        logger.warning("structlog not found for JSON logging. Using basic formatter for file logs.")
        basic_file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(basic_file_formatter)
        log_handlers.append(file_handler)

    # Trade Logger (CSV Format)
    trade_file_handler = logging.FileHandler(os.path.join(LOG_DIR, f"trades_{timestamp_str}.csv"), mode='w', encoding='utf-8')
    trade_file_handler.setLevel(logging.INFO)
    trade_formatter = logging.Formatter('%(asctime)s,%(levelname)s,%(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    trade_file_handler.setFormatter(trade_formatter)
    try:
        trade_file_handler.write("timestamp,symbol,side,quantity,price,realized_pnl,fee,order_id,trade_type\n")
    except Exception as e:
        logger.error(f"Failed to write CSV header: {e}")
    trade_file_handler.flush() # Ensure header is written immediately
    log_handlers.append(trade_file_handler)

    # Configure root logger
    logger.setLevel(log_level)
    if logger.hasHandlers(): logger.handlers.clear() # Prevent duplicate handlers
    for handler in log_handlers:
        logger.addHandler(handler)

    # Configure trade logger (non-propagating)
    trade_logger.setLevel(logging.INFO)
    if trade_logger.hasHandlers(): trade_logger.handlers.clear()
    trade_logger.addHandler(trade_file_handler)
    trade_logger.propagate = False

    # Add checks for optional dependencies
    if not PYBIT_AVAILABLE: logger.warning("pybit library not found. Falling back to manual API calls and WebSocket connections.")
    if not PSUTIL_AVAILABLE: logger.warning("psutil not found. CPU/Memory monitoring will be limited. Install with: pip install psutil --no-cache-dir")
    if not NUMPY_AVAILABLE or not PANDAS_AVAILABLE: logger.warning("numpy or pandas not found. Some performance ratio calculations may be unavailable.")

    logger.info(f"Logging setup complete. Level: {logging.getLevelName(log_level)}. Console logs enabled. File logs saved to: {LOG_DIR}")


# --- Custom Exceptions ---
class BybitAPIError(Exception):
    """Custom exception for Bybit API errors."""
    def __init__(self, message: str, code: str | None = None, response: dict | None = None):
        super().__init__(message)
        self.code = code
        self.response = response

class RateLimitExceededError(BybitAPIError):
    """Exception raised when rate limits are exceeded."""

class InvalidOrderParameterError(BybitAPIError):
    """Exception for invalid order parameters (e.g., quantity, price)."""

class CircuitBreakerOpenError(Exception):
    """Custom exception for when the circuit breaker is open."""

class WebSocketConnectionError(Exception):
    """Exception for WebSocket connection issues."""

# --- Enhanced Enums ---
class OrderStatus(Enum):
    """Order status enumeration for enhanced readability"""
    NEW = "New"
    PARTIALLY_FILLED = "PartiallyFilled"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"
    EXPIRED = "Expired"
    PENDING = "Pending" # Placeholder

class TradeSide(Enum):
    """Trade side enumeration for clarity"""
    BUY = "Buy"
    SELL = "Sell"
    NONE = "None"

class ConnectionState(Enum):
    """WebSocket connection state enumeration"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    ERROR = "error"

# --- Enhanced Data Structures ---
@dataclass
class OrderData:
    """Enhanced order data structure with additional fields for comprehensive tracking"""
    order_id: str
    symbol: str
    side: TradeSide
    price: Decimal
    quantity: Decimal
    status: OrderStatus
    timestamp: float # When the order was created (seconds)
    type: str = "Limit"
    time_in_force: str = "GTC"
    filled_qty: Decimal = Decimal('0')
    avg_price: Decimal = Decimal('0')
    fee: Decimal = Decimal('0') # Total fee associated with the order's fills
    reduce_only: bool = False
    post_only: bool = True
    client_order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime | None = None
    updated_at: datetime | None = None
    order_pnl: Decimal = Decimal('0') # PnL directly attributed to this order's fills (can be complex)
    retry_count: int = 0
    last_error: str | None = None
    exec_type: str | None = None # For WS messages: Trade, Cancel, etc.

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization, ensuring Decimal to str conversion"""
        data = asdict(self)
        data['side'] = self.side.value
        data['status'] = self.status.value
        data['price'] = str(self.price)
        data['quantity'] = str(self.quantity)
        data['filled_qty'] = str(self.filled_qty)
        data['avg_price'] = str(self.avg_price)
        data['fee'] = str(self.fee)
        data['order_pnl'] = str(self.order_pnl)
        if self.created_at: data['created_at'] = self.created_at.isoformat()
        if self.updated_at: data['updated_at'] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_api(cls, api_data: dict[str, Any]) -> 'OrderData':
        """Create OrderData object from API response dictionary (REST or WS)"""
        try:
            created_time_ms = float(api_data.get("createdTime", 0)) if api_data.get("createdTime") else time.time() * 1000
            updated_time_ms = float(api_data.get("updatedTime", created_time_ms))

            side_str = api_data.get("side", "None")
            side = TradeSide(side_str) if side_str in TradeSide.__members__.values() else TradeSide.NONE

            order_status_str = api_data.get("orderStatus", api_data.get("orderStatus", api_data.get("stopOrderType", "New"))) # Handle different fields
            status = OrderStatus[order_status_str.upper()] if order_status_str.upper() in OrderStatus.__members__ else OrderStatus.NEW

            return cls(
                order_id=str(api_data.get("orderId", api_data.get("order_id", str(uuid.uuid4())))),
                symbol=api_data.get("symbol", ""),
                side=side,
                price=Decimal(api_data.get("price", api_data.get("avgPrice", "0"))),
                quantity=Decimal(api_data.get("qty", api_data.get("cumExecQty", "0"))), # Use qty or cumExecQty based on context
                status=status,
                timestamp=created_time_ms / 1000,
                filled_qty=Decimal(api_data.get("cumExecQty", "0")),
                avg_price=Decimal(api_data.get("avgPrice", "0")),
                type=api_data.get("orderType", api_data.get("orderType", "Limit")),
                time_in_force=api_data.get("timeInForce", "GTC"),
                reduce_only=api_data.get("reduceOnly", False),
                post_only=api_data.get("postOnly", False),
                client_order_id=api_data.get("orderLinkId", api_data.get("orderLinkId", "")),
                created_at=datetime.fromtimestamp(created_time_ms / 1000, tz=timezone.utc) if created_time_ms > 0 else None,
                updated_at=datetime.fromtimestamp(updated_time_ms / 1000, tz=timezone.utc) if updated_time_ms > 0 else None,
                order_pnl=Decimal(api_data.get("orderPnl", "0")) # PnL might be specific to the trade/fill, not the whole order
            )
        except (ValueError, KeyError, TypeError, InvalidOperation) as e:
            logger.error(f"Error creating OrderData from API data: {api_data} - {e}", exc_info=True)
            raise # Re-raise after logging

@dataclass
class MarketData:
    """Enhanced market data structure with additional analytics"""
    symbol: str
    best_bid: Decimal
    best_ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    mid_price: Decimal = Decimal('0')
    spread: Decimal = Decimal('0')
    timestamp: float # Timestamp of the data update (seconds)
    volume_24h: Decimal = Decimal('0')
    trades_24h: int = 0
    last_price: Decimal | None = None
    funding_rate: Decimal | None = None
    open_interest: Decimal | None = None
    mark_price: Decimal | None = None
    index_price: Decimal | None = None

    # For volatility tracking
    last_price_history: deque = field(default_factory=lambda: deque(maxlen=100)) # Store recent last prices

    def __post_init__(self):
        self._calculate_derived_metrics()

    @property
    def spread_bps(self) -> Decimal:
        if self.mid_price > 0:
            return (self.spread / self.mid_price) * Decimal('10000')
        return Decimal('0')

    @property
    def bid_ask_imbalance(self) -> Decimal:
        total_size = self.bid_size + self.ask_size
        if total_size > 0:
            return (self.bid_size - self.ask_size) / total_size
        return Decimal('0')

    def _calculate_derived_metrics(self):
        """Helper to calculate mid-price and spread."""
        if self.best_bid > 0 and self.best_ask > 0:
            self.mid_price = (self.best_bid + self.best_ask) / Decimal('2')
            self.spread = self.best_ask - self.best_bid
        else:
            self.mid_price = Decimal('0')
            self.spread = Decimal('0')

    def update_from_tick(self, tick_data: dict[str, Any]):
        """Update market data from a ticker stream or API response"""
        self.best_bid = safe_decimal(tick_data.get('bid1Price', str(self.best_bid or '0')))
        self.best_ask = safe_decimal(tick_data.get('ask1Price', str(self.best_ask or '0')))
        self.bid_size = safe_decimal(tick_data.get('bid1Size', str(self.bid_size or '0')))
        self.ask_size = safe_decimal(tick_data.get('ask1Size', str(self.ask_size or '0')))
        self.last_price = safe_decimal(tick_data.get('lastPrice', str(self.last_price or '0')))
        self.volume_24h = safe_decimal(tick_data.get('volume24h', str(self.volume_24h or '0')))
        self.mark_price = safe_decimal(tick_data.get('markPrice', str(self.mark_price or '0')))
        self.index_price = safe_decimal(tick_data.get('indexPrice', str(self.index_price or '0')))

        ts = float(tick_data.get('ts', tick_data.get('updatedTime', time.time()*1000))) # Handle timestamp variations
        self.timestamp = ts / 1000 if ts > 1_000_000_000_000 else ts # Convert ms to seconds if needed

        # Add last price to history for volatility calculation
        if self.last_price is not None and self.last_price > 0:
             self.last_price_history.append(self.last_price)

        self._calculate_derived_metrics()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, Decimal):
                data[key] = str(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, deque): # Convert deques to lists
                data[key] = list(value)
        return data

@dataclass
class RiskMetrics:
    """Enhanced risk management metrics with additional safety features"""
    max_drawdown_pct: Decimal = Decimal('0')
    max_drawdown_abs: Decimal = Decimal('0')
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0
    var_95: Decimal = Decimal('0') # Value at Risk (not implemented in detail here)
    sortino_ratio: float = 0.0

    # Runtime metrics
    initial_equity: Decimal = Decimal('0') # Equity at the start of the bot session/day
    current_equity: Decimal = Decimal('0') # Equity based on realized + unrealized PnL
    realized_pnl: Decimal = Decimal('0')
    unrealized_pnl: Decimal = Decimal('0')
    current_position_base: Decimal = Decimal('0') # Current inventory in base asset (e.g., BTC)
    max_position_base: Decimal = Decimal('0') # Max allowed position size in base asset
    trade_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_winning_pnl: Decimal = Decimal('0')
    total_losing_pnl: Decimal = Decimal('0')
    peak_equity: Decimal = Decimal('0') # Highest equity reached since start/reset

    # Daily metrics
    last_daily_pnl_reset: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0))
    daily_pnl: Decimal = Decimal('0') # PnL accumulated since the start of the current day
    max_daily_loss_pct: Decimal = Decimal('0.05') # Max loss allowed per day in percentage of initial equity

    # Consecutive loss tracking
    consecutive_losses: int = 0
    max_consecutive_losses: int = 0

    # History tracking for performance metrics
    hourly_pnl_history: deque = field(default_factory=lambda: deque(maxlen=24)) # Stores equity at start of each hour
    trade_pnl_history: deque = field(default_factory=lambda: deque(maxlen=100)) # Stores individual trade PnLs

    # Volatility tracking history
    volatility_history: dict[str, deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=100)))

    def __post_init__(self):
        # Ensure initial equity is set if provided, otherwise default to 0 and log warning
        if self.initial_equity == 0:
            logger.warning("Initial equity not set. Risk calculations like drawdown and daily limits may be inaccurate. Consider setting 'initial_equity' in SymbolConfig risk_params.")
        self.peak_equity = self.initial_equity if self.initial_equity > 0 else Decimal('0')
        self.current_equity = self.initial_equity if self.initial_equity > 0 else Decimal('0')
        self.last_daily_pnl_reset = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) # Ensure it's set correctly initially

    def update_trade_stats(self, pnl: Decimal):
        """Update trade statistics with enhanced tracking based on a single trade's PnL."""
        self.trade_count += 1
        self.realized_pnl += pnl
        self.trade_pnl_history.append(pnl)

        if pnl > 0:
            self.winning_trades += 1
            self.total_winning_pnl += pnl
            self.consecutive_losses = 0 # Reset consecutive losses on a win
        else: # PnL is 0 or negative
            self.losing_trades += 1
            self.total_losing_pnl += abs(pnl)
            self.consecutive_losses += 1
            self.max_consecutive_losses = max(self.max_consecutive_losses, self.consecutive_losses)

        # Update Win Rate and Profit Factor
        if self.trade_count > 0:
            self.win_rate = (self.winning_trades / self.trade_count) * 100.0
        else:
            self.win_rate = 0.0

        if self.total_losing_pnl > 0:
            self.profit_factor = float(self.total_winning_pnl / self.total_losing_pnl)
        elif self.total_winning_pnl > 0:
            self.profit_factor = float('inf') # Infinite profit factor if no losing trades
        else:
            self.profit_factor = 0.0 # No profit or loss yet

        self.update_equity_and_drawdown() # Recalculate equity and drawdown metrics

    def update_equity_and_drawdown(self):
        """Updates current equity based on realized/unrealized PnL and recalculates drawdown.
        Manages daily PnL reset and peak equity.
        """
        self.current_equity = self.initial_equity + self.realized_pnl + self.unrealized_pnl

        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity

        drawdown_abs = self.peak_equity - self.current_equity
        self.max_drawdown_abs = max(self.max_drawdown_abs, drawdown_abs)

        if self.peak_equity > 0:
            self.max_drawdown_pct = (self.max_drawdown_abs / self.peak_equity) * Decimal('100.0')
        else:
            self.max_drawdown_pct = Decimal('0')

        # Update hourly PnL tracking
        now_utc = datetime.now(timezone.utc)
        current_hour_start = now_utc.replace(minute=0, second=0, microsecond=0)

        # Add current equity to hourly history at the start of a new hour, avoid duplicates
        if not self.hourly_pnl_history or \
           (self.hourly_pnl_history and current_hour_start > self.hourly_pnl_history[-1].__getattribute__('replace')(minute=0, second=0, microsecond=0)):
             # Correct way to get the hour start from datetime object if stored
            self.hourly_pnl_history.append(self.current_equity)

        # Daily PnL reset logic
        if now_utc.date() > self.last_daily_pnl_reset.date():
            self.daily_pnl = self.current_equity - self.peak_equity # PnL for the just-finished day
            logger.info(f"Daily PnL reset. Previous day's PnL: {self.daily_pnl:.4f}. Resetting for new day.")

            # Reset for the new day
            self.last_daily_pnl_reset = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            self.peak_equity = self.current_equity # New day's peak starts from current equity
            self.daily_pnl = Decimal('0') # Reset daily PnL for the new day
        else:
            # Intra-day PnL relative to the current day's peak
            self.daily_pnl = self.current_equity - self.peak_equity

    def check_and_apply_risk_limits(self) -> bool:
        """Checks risk limits and returns True if trading should be halted/reduced.
        """
        # 1. Max Drawdown Check
        if self.max_drawdown_pct > self.max_daily_loss_pct * Decimal('100'): # Use daily loss pct as proxy for overall drawdown limit if needed
            logger.critical(f"CRITICAL RISK: Max drawdown breached! ({self.max_drawdown_pct:.2f}% > {self.max_daily_loss_pct*100:.2f}%)")
            return True

        # 2. Daily Loss Limit Check
        # Compare current equity against the equity at the start of the day (peak_equity for the day)
        if self.initial_equity > 0 and self.daily_pnl < -(self.initial_equity * self.max_daily_loss_pct):
            logger.critical(f"CRITICAL RISK: Daily loss limit breached! Current daily PnL: {self.daily_pnl:.4f} (limit: -{self.initial_equity * self.max_daily_loss_pct:.4f})")
            return True

        # 3. Consecutive Losses Check
        if self.consecutive_losses >= 5:
            logger.warning(f"ELEVATED RISK: {self.consecutive_losses} consecutive losses detected.")
            if self.consecutive_losses >= 10:
                logger.critical(f"CRITICAL RISK: {self.consecutive_losses} consecutive losses! Halting trading.")
                return True

        # 4. Max Position Size Check (might not halt trading, but warn or affect sizing)
        if self.max_position_base > 0 and abs(self.current_position_base) > self.max_position_base:
            logger.warning(f"ELEVATED RISK: Max position limit ({self.max_position_base}) exceeded! Current: {self.current_position_base}. Consider reducing position.")
            # Decide if this should return True to halt, or just warn. For MM, often adjust sizing instead of halting.
            return False # Allow continuing, but strategy should adjust sizing

        return False # No critical risks detected

    def calculate_performance_ratios(self, risk_free_rate: float = 0.0):
        """Calculate enhanced performance ratios including Sortino. Requires numpy."""
        if not NUMPY_AVAILABLE:
             logger.warning("Skipping performance ratio calculation: numpy not available.")
             return

        if len(self.trade_pnl_history) >= 2:
            try:
                pnl_list = [float(pnl) for pnl in list(self.trade_pnl_history) if pnl is not None] # Filter None values
                if not pnl_list: return # Need data to calculate

                std_dev_pnl = Decimal(np.std(pnl_list))
                avg_pnl = self.realized_pnl / self.trade_count if self.trade_count > 0 else Decimal('0')

                # Sharpe Ratio calculation
                if std_dev_pnl > 0:
                    sharpe = (avg_pnl - Decimal(str(risk_free_rate))) / std_dev_pnl
                    self.sharpe_ratio = float(sharpe)
                else:
                    self.sharpe_ratio = 0.0

                # Sortino Ratio calculation (using downside deviation)
                negative_returns = [pnl for pnl in pnl_list if pnl < 0]
                if negative_returns:
                    downside_deviation = Decimal(np.std(negative_returns))
                    if downside_deviation > 0:
                        sortino = (avg_pnl - Decimal(str(risk_free_rate))) / downside_deviation
                        self.sortino_ratio = float(sortino)
                    else:
                        self.sortino_ratio = 0.0 # No downside volatility
                else:
                    self.sortino_ratio = float('inf') if avg_pnl > 0 else 0.0 # All positive returns

            except Exception as e:
                logger.error(f"Error calculating performance ratios: {e}", exc_info=True)
                self.sharpe_ratio = 0.0; self.sortino_ratio = 0.0
        else:
             logger.debug("Not enough trade history (>1 trade) to calculate performance ratios.")

        # Calmar Ratio calculation
        if self.max_drawdown_pct > 0:
            try:
                pf_val = float(self.profit_factor)
                if not np.isfinite(pf_val): pf_val = 0.0 # Handle infinite profit factor gracefully

                calmar = pf_val / float(self.max_drawdown_pct) if self.max_drawdown_pct else 0.0
                self.calmar_ratio = calmar
            except Exception as e:
                logger.error(f"Error calculating Calmar Ratio: {e}", exc_info=True)
                self.calmar_ratio = 0.0
        else:
            self.calmar_ratio = 0.0

    def track_volatility(self, symbol: str, price: Decimal):
        """Tracks price history for volatility calculation."""
        if symbol not in self.volatility_history:
             self.volatility_history[symbol] = deque(maxlen=100)
        self.volatility_history[symbol].append(price)

    def calculate_volatility(self, symbol: str) -> Decimal:
        """Calculates standard deviation of recent prices for volatility."""
        if symbol in self.volatility_history and len(self.volatility_history[symbol]) >= 2 and NUMPY_AVAILABLE:
            prices = list(self.volatility_history[symbol])
            std_dev = np.std(prices)
            # Normalize volatility relative to price for better comparison across symbols/scales
            avg_price = np.mean(prices)
            if avg_price > 0:
                return Decimal(str(std_dev / avg_price)) # Volatility as % of price
            return Decimal('0')
        return Decimal('0') # Default if not enough data or numpy unavailable

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, Decimal): data[key] = str(value)
            elif isinstance(value, datetime): data[key] = value.isoformat()
            elif isinstance(value, deque): data[key] = list(value)
            elif isinstance(value, dict) and key == 'volatility_history': # Special handling for nested dicts
                data[key] = {s: list(d) for s, d in value.items()}
        return data

class EnhancedPerformanceMonitor:
    """Enhanced performance monitoring with detailed metrics"""
    def __init__(self):
        self.start_time = time.time()
        self.metrics = defaultdict(float)
        self.latencies = deque(maxlen=2000)
        self.order_latencies = deque(maxlen=2000)
        self.ws_latencies = deque(maxlen=2000)
        self.api_call_counts = defaultdict(int)
        self.api_error_counts = defaultdict(int)
        self.last_gc_collection = time.time()
        self.ws_reconnection_count = 0
        self.circuit_breaker_trips = 0
        self.rate_limit_hits = 0
        self.memory_peak_mb = 0.0
        self.lock = threading.Lock()
        self._last_perf_log_time = 0.0

    def record_metric(self, metric_name: str, value: float = 1.0):
        with self.lock: self.metrics[metric_name] += value

    def record_latency(self, latency_type: str, latency: float):
        if latency is not None and latency >= 0:
            with self.lock:
                if latency_type == 'order': self.order_latencies.append(latency)
                elif latency_type == 'ws': self.ws_latencies.append(latency)
                else: self.latencies.append(latency)

    def record_api_call(self, endpoint: str, success: bool = True):
        with self.lock:
            self.api_call_counts[endpoint] += 1
            if not success: self.api_error_counts[endpoint] += 1

    def record_ws_reconnection(self):
        with self.lock: self.ws_reconnection_count += 1

    def record_circuit_breaker_trip(self):
        with self.lock: self.circuit_breaker_trips += 1

    def record_rate_limit_hit(self):
        with self.lock: self.rate_limit_hits += 1

    def get_cpu_usage(self) -> float | None:
        if not PSUTIL_AVAILABLE: return None
        try: return psutil.cpu_percent(interval=None)
        except Exception as e: logger.error(f"Failed to get CPU usage: {e}"); return None

    def get_memory_usage(self) -> tuple[float | None, float]:
        if not PSUTIL_AVAILABLE: return None, self.memory_peak_mb
        try:
            process = psutil.Process(os.getpid())
            current_memory = process.memory_info().rss / 1024 / 1024 # MB
            self.memory_peak_mb = max(self.memory_peak_mb, current_memory)
            return current_memory, self.memory_peak_mb
        except Exception as e: logger.error(f"Failed to get memory usage: {e}"); return None, self.memory_peak_mb

    def trigger_gc(self):
        collected = gc.collect()
        current_memory, peak_memory = self.get_memory_usage()
        self.last_gc_collection = time.time()
        if current_memory is not None:
            logger.debug(f"GC triggered: {collected} objects collected, Memory: {current_memory:.1f}MB (Peak: {peak_memory:.1f}MB)")
        else:
            logger.debug(f"GC triggered: {collected} objects collected.")

    def get_stats(self) -> dict[str, Any]:
        uptime = time.time() - self.start_time
        current_memory_mb, memory_peak_mb = self.get_memory_usage()
        cpu_usage_percent = self.get_cpu_usage()

        stats = {
            'uptime_hours': round(uptime / 3600, 2),
            'total_orders_placed': self.metrics.get('orders_placed', 0),
            'total_orders_filled': self.metrics.get('orders_filled', 0),
            'total_orders_cancelled': self.metrics.get('orders_cancelled', 0),
            'total_orders_rejected': self.metrics.get('orders_rejected', 0),
            'ws_messages_processed': self.metrics.get('ws_messages', 0),
            'ws_reconnections': self.ws_reconnection_count,
            'circuit_breaker_trips': self.circuit_breaker_trips,
            'rate_limit_hits': self.rate_limit_hits,
            'total_api_errors': sum(self.api_error_counts.values()),
            'memory_usage_mb': round(current_memory_mb, 2) if current_memory_mb is not None else "N/A",
            'memory_peak_mb': round(memory_peak_mb, 2) if memory_peak_mb is not None else "N/A",
            'cpu_usage_percent': round(cpu_usage_percent, 2) if cpu_usage_percent is not None else "N/A",
            'active_threads': threading.active_count(),
            'gc_collections': gc.get_count(),
        }

        # Latency stats calculation
        if NUMPY_AVAILABLE:
            if self.order_latencies: stats.update({f'{stat}_{unit}': round(val, 2) for stat, val, unit in zip(
                ['avg_order_latency_ms', 'p95_order_latency_ms', 'p99_order_latency_ms', 'max_order_latency_ms'],
                [np.mean(list(self.order_latencies)), np.percentile(list(self.order_latencies), 95), np.percentile(list(self.order_latencies), 99), np.max(list(self.order_latencies))],
                ['ms'] * 4, strict=False
            )})
            else: stats.update({'avg_order_latency_ms': 0, 'p95_order_latency_ms': 0, 'p99_order_latency_ms': 0, 'max_order_latency_ms': 0})

            if self.ws_latencies: stats.update({f'{stat}_{unit}': round(val, 2) for stat, val, unit in zip(
                ['avg_ws_latency_ms', 'p95_ws_latency_ms', 'p99_ws_latency_ms'],
                [np.mean(list(self.ws_latencies)), np.percentile(list(self.ws_latencies), 95), np.percentile(list(self.ws_latencies), 99)],
                ['ms'] * 3, strict=False
            )})
            else: stats.update({'avg_ws_latency_ms': 0, 'p95_ws_latency_ms': 0, 'p99_ws_latency_ms': 0})
        else: # Fallback if numpy is missing
            stats.update({'avg_order_latency_ms': "N/A", 'p95_order_latency_ms': "N/A", 'p99_order_latency_ms': "N/A", 'max_order_latency_ms': "N/A",
                          'avg_ws_latency_ms': "N/A", 'p95_ws_latency_ms': "N/A", 'p99_ws_latency_ms': "N/A"})

        stats['api_call_counts'] = dict(self.api_call_counts)
        stats['api_error_counts'] = dict(self.api_error_counts)
        return stats

class EnhancedCircuitBreaker:
    """Enhanced circuit breaker with exponential backoff and health checks"""
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0,
                 expected_exceptions: tuple[type[Exception], ...] = (Exception,),
                 max_recovery_timeout: float = 300.0):
        self.failure_threshold = failure_threshold
        self.base_recovery_timeout = recovery_timeout
        self.max_recovery_timeout = max_recovery_timeout
        self.expected_exceptions = expected_exceptions
        self.failure_count = 0
        self.state = "CLOSED" # Possible states: CLOSED, OPEN, HALF-OPEN
        self.last_failure_time = 0.0
        self.lock = asyncio.Lock()
        self.recovery_attempts = 0
        self.success_count_since_failure = 0

    async def __aenter__(self):
        async with self.lock:
            if self.state == "OPEN":
                current_timeout = min(self.base_recovery_timeout * (2 ** self.recovery_attempts), self.max_recovery_timeout)
                if time.time() - self.last_failure_time > current_timeout:
                    self.state = "HALF-OPEN"
                    self.recovery_attempts += 1
                    logger.warning(f"Circuit Breaker: Recovery timeout elapsed. Moving to HALF-OPEN (attempt {self.recovery_attempts})")
                else:
                    remaining_time = current_timeout - (time.time() - self.last_failure_time)
                    raise CircuitBreakerOpenError(f"Circuit breaker is OPEN. Try again in {remaining_time:.2f}s")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self.lock:
            if exc_type is not None and issubclass(exc_type, self.expected_exceptions):
                # Failure occurred
                self.failure_count += 1
                self.last_failure_time = time.time()
                self.success_count_since_failure = 0 # Reset success count on failure

                if self.state == "HALF-OPEN":
                    self.state = "OPEN" # Re-open if HALF-OPEN failed
                    logger.error(f"Circuit Breaker: HALF-OPEN request failed ({exc_val}). Re-opening circuit.")
                elif self.failure_count >= self.failure_threshold:
                    self.state = "OPEN" # Trip the breaker if threshold reached
                    logger.critical(f"Circuit Breaker: Failure threshold ({self.failure_threshold}) reached. Opening circuit.")
                else:
                    logger.warning(f"Circuit Breaker: Failure detected ({exc_val}). Count: {self.failure_count}/{self.failure_threshold}.")

            elif self.state == "HALF-OPEN":
                # Success occurred in HALF-OPEN state
                self.success_count_since_failure += 1
                if self.success_count_since_failure >= 3: # Require multiple successes to close
                    self.state = "CLOSED"
                    self.failure_count = 0 # Reset failure state
                    self.recovery_attempts = 0
                    logger.info("Circuit Breaker: Multiple HALF-OPEN requests succeeded. Closing circuit.")
                else:
                    logger.debug(f"Circuit Breaker: HALF-OPEN request succeeded ({self.success_count_since_failure}/3 needed).")
            elif self.state == "CLOSED" and self.failure_count > 0:
                # Track successes in CLOSED state to reset failure count if healthy
                self.success_count_since_failure += 1
                if self.success_count_since_failure >= 5: # Reset after 5 consecutive successes
                    self.failure_count = 0
                    self.success_count_since_failure = 0
                    logger.debug("Circuit Breaker: Multiple successful requests. Resetting failure count.")

class EnhancedRateLimiter:
    """Enhanced rate limiter with adaptive limits."""
    def __init__(self, limits: dict[str, tuple[int, int]], default_limit: tuple[int, int] = (100, 60),
                 burst_allowance_factor: float = 0.15, adaptive: bool = True):
        self.limits = {k: v for k, v in limits.items()}
        self.default_limit = default_limit
        self.burst_allowance_factor = burst_allowance_factor
        self.adaptive = adaptive
        self.requests = defaultdict(lambda: deque()) # Stores timestamps {endpoint: deque([ts1, ts2, ...])}
        self.lock = asyncio.Lock()
        self.adaptive_factors = defaultdict(lambda: 1.0) # {endpoint: factor}

    async def acquire(self, endpoint: str, priority: str = "normal"):
        """Acquire a permit, waiting if necessary."""
        async with self.lock:
            max_requests, window_seconds = self._get_effective_limit(endpoint)
            # Calculate effective requests considering burst and adaptive factor
            effective_max_requests = max(1, int(max_requests * (1 + self.burst_allowance_factor) * self.adaptive_factors[endpoint]))

            request_times = self.requests[endpoint]
            now = time.time()

            # Clean up old timestamps
            while request_times and request_times[0] < now - window_seconds:
                request_times.popleft()

            # Check if limit is reached
            if len(request_times) >= effective_max_requests:
                if self.adaptive: self._adjust_adaptive_factor(endpoint, False) # Reduce factor on hit

                time_to_wait = window_seconds - (now - request_times[0]) if request_times else window_seconds
                if time_to_wait > 0:
                    logger.warning(f"Rate limit hit for {endpoint}. Effective limit {effective_max_requests}/{window_seconds}s. Waiting {time_to_wait:.2f}s")
                    self.record_rate_limit_hit() # Record the hit
                    await asyncio.sleep(time_to_wait) # Wait
                    return await self.acquire(endpoint, priority) # Retry after waiting
                logger.warning(f"Rate limit condition for {endpoint}, but wait time <= 0. Proceeding.")

            # Add current request timestamp
            request_times.append(now)

            # Increase adaptive factor if well below limit (encourages faster requests)
            if self.adaptive and len(request_times) < effective_max_requests * 0.8:
                self._adjust_adaptive_factor(endpoint, True)

    def _get_effective_limit(self, endpoint: str) -> tuple[int, int]:
        """Find the most specific rate limit rule for the endpoint."""
        best_match_limit = self.default_limit
        longest_match_len = 0
        for prefix, limit_config in self.limits.items():
            if endpoint.startswith(prefix) and len(prefix) > longest_match_len:
                longest_match_len = len(prefix)
                best_match_limit = limit_config
        return best_match_limit

    def _adjust_adaptive_factor(self, endpoint: str, success: bool):
        """Adjust adaptive factor based on success/failure."""
        if success:
            self.adaptive_factors[endpoint] = min(self.adaptive_factors[endpoint] * 1.02, 1.5) # Increase factor, capped
        else:
            self.adaptive_factors[endpoint] = max(self.adaptive_factors[endpoint] * 0.95, 0.5) # Decrease factor, capped
        logger.debug(f"Adaptive factor for {endpoint} adjusted to {self.adaptive_factors[endpoint]:.2f}")

# --- Configuration Data Structures ---
@dataclass
class SymbolConfig:
    symbol: str
    base_qty: Decimal
    order_levels: int = 5
    spread_bps: Decimal = Decimal('0.05')
    inventory_target_base: Decimal = Decimal('0')
    risk_params: dict[str, Any] = field(default_factory=lambda: {
        "max_position_base": Decimal('0.1'), "max_drawdown_pct": Decimal('10.0'),
        "initial_equity": Decimal('10000'), "max_daily_loss_pct": Decimal('0.05')
    })
    min_spread_bps: Decimal = Decimal('0.01')
    max_spread_bps: Decimal = Decimal('0.20')
    volatility_adjustment_factor: Decimal = Decimal('1.0')
    inventory_skew_factor: Decimal = Decimal('0.1')

    # Will be populated from exchange info
    price_precision: Decimal = Decimal('0.01')
    qty_precision: Decimal = Decimal('0.001')
    min_order_qty: Decimal = Decimal('0.001')

@dataclass
class BotConfig:
    api_key: str
    api_secret: str
    is_testnet: bool
    state_directory: str = STATE_DIR
    symbols: list[SymbolConfig] = field(default_factory=list)

    # Bot settings
    log_level: str = "INFO"
    debug_mode: bool = False
    performance_monitoring_interval: int = 60
    state_save_interval: int = 300
    polling_interval_sec: float = 5.0 # Main loop polling interval
    order_cancellation_deviation_bps: Decimal = Decimal('2') # Cancel order if market moves N bps past it

    # API Client settings
    api_timeout_total: int = 45
    api_timeout_connect: int = 10
    api_timeout_sock_read: int = 20
    api_connection_limit: int = 150
    api_connection_limit_per_host: int = 50
    api_keepalive_timeout: int = 60
    api_retry_attempts: int = 3
    api_retry_delay: float = 1.0

    # Rate Limiter settings
    rate_limits: dict[str, tuple[int, int]] = field(default_factory=lambda: {
        '/v5/order/create': (50, 60), '/v5/order/cancel': (50, 60), '/v5/order/active': (50, 60),
        '/v5/position': (120, 60), '/v5/account': (120, 60), '/v5/market': (120, 60),
        '/v5/market/tickers': (120, 60), '/v5/market/orderbook': (120, 60),
        '/v5/market/instruments-info': (10, 60), '/v5/asset': (60, 60),
    })

    # WebSocket settings
    ws_ping_interval: int = 30
    ws_ping_timeout: int = 10
    ws_close_timeout: int = 10
    ws_max_size: int = 2**20
    ws_compression: str | None = "deflate"
    ws_reconnect_delay: float = 5.0 # Initial delay for WS reconnection
    ws_max_reconnect_delay: float = 300.0 # Max WS reconnection delay

    # Circuit Breaker settings
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: float = 60.0
    circuit_breaker_max_recovery_timeout: float = 300.0

# --- Utility Functions ---
def safe_decimal(value: Any, default: Decimal = Decimal('0')) -> Decimal:
    """Safely convert value to Decimal, returning default on error."""
    try:
        return Decimal(str(value)) if value is not None else default
    except (InvalidOperation, ValueError, TypeError):
        logger.warning(f"Could not convert '{value}' to Decimal. Using default {default}.")
        return default

# --- Bybit API Client ---
class BybitV5APIClient:
    """Enhanced Bybit v5 API client with updated authentication and error handling"""
    def __init__(self, config: BotConfig):
        self.config = config
        self.api_key = config.api_key
        self.api_secret = config.api_secret
        self.is_testnet = config.is_testnet
        self.base_url = BASE_URL
        self.recv_window = "5000"

        self.rate_limiter = EnhancedRateLimiter(limits=config.rate_limits, default_limit=(100, 60), adaptive=True)
        self.circuit_breaker = EnhancedCircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            recovery_timeout=config.circuit_breaker_recovery_timeout,
            max_recovery_timeout=config.circuit_breaker_max_recovery_timeout,
            expected_exceptions=(BybitAPIError, aiohttp.ClientError, asyncio.TimeoutError)
        )

        self._session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()
        self._session_created = False

        # Pybit client initialization
        if PYBIT_AVAILABLE:
            try:
                self.pybit_client = PybitHTTP(testnet=self.is_testnet, api_key=self.api_key, api_secret=self.api_secret)
                logger.info("Official pybit client initialized successfully.")
            except Exception as e:
                logger.warning(f"Failed to initialize pybit client: {e}. Falling back to manual HTTP requests.")
                self.pybit_client = None
        else:
            self.pybit_client = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Provides a shared, properly configured aiohttp ClientSession."""
        async with self._session_lock:
            if not self._session or self._session.closed:
                connector = aiohttp.TCPConnector(
                    limit=self.config.api_connection_limit, limit_per_host=self.config.api_connection_limit_per_host,
                    keepalive_timeout=self.config.api_keepalive_timeout, enable_cleanup_closed=True)
                timeout = aiohttp.ClientTimeout(
                    total=self.config.api_timeout_total, connect=self.config.api_timeout_connect,
                    sock_read=self.config.api_timeout_sock_read)
                self._session = aiohttp.ClientSession(
                    connector=connector, timeout=timeout, headers={"User-Agent": "BybitMMBot/2.0 (Termux)"})
                self._session_created = True
                logger.debug("aiohttp ClientSession created.")
            return self._session

    async def close(self):
        """Gracefully close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session_created = False
            logger.info("aiohttp ClientSession closed.")

    def _generate_signature(self, timestamp: str, method: str, path: str, params_or_body: str = "") -> str:
        """Generate HMAC-SHA256 signature for Bybit v5 API requests."""
        param_str = f"{timestamp}{self.api_key}{self.recv_window}{params_or_body}"
        return hmac.new(self.api_secret.encode('utf-8'), param_str.encode('utf-8'), hashlib.sha256).hexdigest()

    def _build_headers(self, timestamp: str, signature: str) -> dict[str, str]:
        """Builds the required headers for Bybit v5 API authentication."""
        return {
            'X-BAPI-API-KEY': self.api_key, 'X-BAPI-TIMESTAMP': timestamp, 'X-BAPI-RECV-WINDOW': self.recv_window,
            'X-BAPI-SIGN': signature, 'Content-Type': 'application/json'
        }

    async def _make_request(self, method: str, endpoint: str, params: dict | None = None,
                          data: dict | None = None, retries: int | None = None) -> dict[str, Any]:
        """Makes an authenticated API request with rate limiting, circuit breaking, and retries."""
        if retries is None: retries = self.config.api_retry_attempts

        url = f"{self.base_url}/v5/{endpoint}"
        timestamp = str(int(time.time() * 1000))

        query_string = urllib.parse.urlencode(sorted(params.items())) if params else ""
        request_body = json.dumps(data, separators=(',', ':')) if data else ""
        signature_payload = query_string if method == "GET" else request_body
        signature = self._generate_signature(timestamp, method, f"/v5/{endpoint}", signature_payload)
        headers = self._build_headers(timestamp, signature)

        await self.rate_limiter.acquire(f"/v5/{endpoint}") # Acquire permit before request

        async with self.circuit_breaker: # Use circuit breaker context
            for attempt in range(retries):
                try:
                    session = await self._get_session()
                    async with session.request(method=method, url=url, params=params if method == "GET" else None,
                                               json=data if method != "GET" else None, headers=headers) as response:

                        response_data = await response.json()
                        self.rate_limiter.record_api_call(f"/v5/{endpoint}") # Record successful call attempt

                        if response_data.get('retCode') != 0:
                            error_msg = response_data.get('retMsg', 'Unknown error')
                            error_code = response_data.get('retCode')
                            self.perf_monitor.record_api_call(f"/v5/{endpoint}", success=False)

                            if error_code == 10006: raise RateLimitExceededError(f"Rate limit exceeded: {error_msg}")
                            if error_code in [10001, 10003]: raise BybitAPIError(f"Auth/Permission error: {error_msg}", str(error_code))
                            if error_code in [110001, 110003, 110004]: raise InvalidOrderParameterError(f"Invalid order param: {error_msg}", str(error_code))
                            raise BybitAPIError(f"API error ({error_code}): {error_msg}", str(error_code), response_data)

                        return response_data # Success

                except (aiohttp.ClientError, asyncio.TimeoutError, BybitAPIError) as e:
                    logger.error(f"API request failed ({method} {endpoint}, attempt {attempt+1}/{retries}): {e}", exc_info=True)
                    if isinstance(e, RateLimitExceededError):
                        self.perf_monitor.record_rate_limit_hit()
                        await asyncio.sleep(5) # Specific wait for rate limits
                    elif attempt < retries - 1:
                        wait_time = (2 ** attempt) * self.config.api_retry_delay # Exponential backoff
                        logger.info(f"Retrying in {wait_time:.2f}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        raise # Re-raise after last attempt fails
            raise BybitAPIError(f"Failed request after {retries} attempts: {method} {endpoint}")

    # --- Public API Methods ---
    async def get_orderbook(self, symbol: str, category: str = "linear", limit: int = 200) -> dict[str, Any]:
        """Get orderbook data using v5 API."""
        if self.pybit_client:
            try: return self.pybit_client.get_orderbook(category=category, symbol=symbol, limit=limit)
            except Exception as e: logger.warning(f"Pybit orderbook failed for {symbol}, falling back: {e}")
        return await self._make_request("GET", "market/orderbook", {"category": category, "symbol": symbol, "limit": limit})

    async def get_ticker(self, symbol: str, category: str = "linear") -> dict[str, Any]:
        """Get ticker information using v5 API."""
        response = await self._make_request("GET", "market/tickers", {"category": category, "symbol": symbol})
        return response.get('result', {}).get('list', [{}])[0] # Return first ticker or empty dict

    async def get_recent_trades(self, symbol: str, category: str = "linear", limit: int = 60) -> dict[str, Any]:
        """Get recent trades using v5 API."""
        return await self._make_request("GET", "market/recent-trade", {"category": category, "symbol": symbol, "limit": limit})

    async def get_exchange_info(self, symbol: str | None = None, category: str = "linear") -> dict[str, Any]:
        """Fetches exchange instrument information."""
        params = {"category": category}
        if symbol: params["symbol"] = symbol
        response = await self._make_request("GET", "market/instruments-info", params)
        return {item['symbol']: item for item in response.get('result', {}).get('list', [])} if response else {}

    # --- Account & Order Methods ---
    async def get_wallet_balance(self, account_type: str = "UNIFIED", coin: str | None = None) -> dict[str, Any]:
        """Get wallet balance using v5 API."""
        params = {"accountType": account_type}
        if coin: params["coin"] = coin
        return await self._make_request("GET", "account/wallet-balance", params)

    async def get_positions(self, category: str = "linear", symbol: str | None = None) -> list[dict[str, Any]]:
        """Get user's current positions."""
        params = {"category": category}
        if symbol: params["symbol"] = symbol
        response = await self._make_request("GET", "position/list", params)
        return response.get('result', {}).get('list', [])

    async def place_order(self, symbol: str, side: TradeSide, order_type: str, qty: Decimal,
                          price: Decimal | None = None, time_in_force: str = "GTC",
                          reduce_only: bool = False, post_only: bool = False,
                          client_order_id: str | None = None, category: str = "linear", **kwargs) -> dict[str, Any]:
        """Place an order using Bybit v5 API."""
        if not client_order_id: client_order_id = str(uuid.uuid4())

        order_params = {
            "category": category, "symbol": symbol, "side": side.value, "orderType": order_type,
            "qty": str(qty), "timeInForce": time_in_force, "reduceOnly": reduce_only,
            "postOnly": post_only, "orderLinkId": client_order_id
        }
        if price is not None: order_params["price"] = str(price)
        for key, value in kwargs.items():
            if value is not None: order_params[key] = str(value) if isinstance(value, Decimal) else value

        # Use pybit if available and suitable, otherwise manual request
        if self.pybit_client and order_type == "Limit" and not kwargs: # Limit pybit usage for simplicity
            try:
                pybit_params = {k: v for k, v in order_params.items()}
                pybit_params['order_link_id'] = pybit_params.pop('orderLinkId')
                pybit_params['order_type'] = pybit_params.pop('orderType')
                pybit_params['time_in_force'] = pybit_params.pop('timeInForce')
                pybit_params['post_only'] = pybit_params.pop('postOnly')

                response = self.pybit_client.place_order(**pybit_params)
                logger.debug(f"Pybit order placement response: {response}")
                return response
            except Exception as e:
                logger.warning(f"Pybit order placement failed, falling back to manual request: {e}")

        return await self._make_request("POST", "order/create", data=order_params)

    async def cancel_order(self, symbol: str, category: str = "linear",
                           order_id: str | None = None, client_order_id: str | None = None) -> dict[str, Any]:
        """Cancel an order by order ID or client order ID using Bybit v5 API."""
        if not order_id and not client_order_id:
            raise ValueError("Either order_id or client_order_id must be provided.")

        cancel_params = {"category": category, "symbol": symbol}
        if order_id: cancel_params["orderId"] = order_id
        if client_order_id: cancel_params["orderLinkId"] = client_order_id

        if self.pybit_client:
            try:
                response = self.pybit_client.cancel_order(**cancel_params)
                logger.debug(f"Pybit order cancellation response: {response}")
                return response
            except Exception as e:
                logger.warning(f"Pybit order cancellation failed, falling back to manual request: {e}")

        return await self._make_request("POST", "order/cancel", data=cancel_params)

    async def get_open_orders(self, symbol: str | None = None, category: str = "linear") -> list[dict[str, Any]]:
        """Get currently open orders (New, PartiallyFilled) via REST API."""
        params = {"category": category}
        if symbol: params["symbol"] = symbol
        response = await self._make_request("GET", "order/active", params)
        return response.get('result', {}).get('list', [])

# --- State Persistence ---
def atomic_write_json(filepath: str, data: Any):
    """Write JSON data atomically to a file."""
    tmp_path = f"{filepath}.tmp"
    try:
        with open(tmp_path, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, filepath) # Atomic rename
        logger.debug(f"Atomically wrote state to {filepath}")
    except OSError as e:
        logger.error(f"Failed to write state file {filepath}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during atomic write to {filepath}: {e}", exc_info=True)
    finally:
        if os.path.exists(tmp_path): # Clean up temp file if it exists
            try: os.remove(tmp_path)
            except OSError as e: logger.error(f"Failed to remove temp state file {tmp_path}: {e}")

def atomic_load_json(filepath: str, default_data: Any | None = None) -> Any:
    """Load JSON data atomically, returning default if file is missing or corrupt."""
    if not os.path.exists(filepath):
        logger.warning(f"State file not found: {filepath}. Returning default data.")
        return default_data

    current_file_path = filepath
    tmp_path = f"{filepath}.tmp"

    # Check if temp file exists and is potentially newer (indicates interrupted write)
    if os.path.exists(tmp_path):
        try:
            if os.path.getmtime(tmp_path) > os.path.getmtime(filepath):
                current_file_path = tmp_path
                logger.warning(f"Found newer temporary state file {tmp_path}, attempting load.")
        except FileNotFoundError: pass # Ignore if file disappears concurrently
        except Exception as e: logger.error(f"Error checking temp file time: {e}")

    try:
        with open(current_file_path, encoding='utf-8') as f:
            data = json.load(f)
            logger.debug(f"Successfully loaded state from {current_file_path}")
            if current_file_path == tmp_path: # Finalize by renaming temp file to final path
                os.replace(tmp_path, filepath)
                logger.debug(f"Finalized state file by renaming {tmp_path} to {filepath}")
            return data
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load/parse state file {current_file_path}: {e}. Returning default.", exc_info=True)
        if os.path.exists(tmp_path): # Clean up problematic temp file
            try: os.remove(tmp_path)
            except OSError as e: logger.error(f"Failed removing temp file {tmp_path}: {e}")
        return default_data
    except Exception as e:
        logger.error(f"Unexpected error loading state file {current_file_path}: {e}. Returning default.", exc_info=True)
        return default_data

# --- Graceful Shutdown Handler ---
shutdown_event = asyncio.Event() # Global event to signal shutdown

def signal_handler(sig, frame):
    """Handles signals like SIGINT (Ctrl+C) and SIGTERM."""
    logger.warning(f"Received signal {sig}. Initiating graceful shutdown...")
    shutdown_event.set() # Signal all tasks to stop

def setup_signal_handlers(loop: asyncio.AbstractEventLoop):
    """Sets up signal handlers for graceful shutdown."""
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s, None))
        except NotImplementedError: # Fallback for platforms without add_signal_handler
            signal.signal(sig, signal_handler)
    logger.info("Signal handlers set up for graceful shutdown.")

# --- Main Bot Logic ---
class MarketMakerBot:
    """Orchestrates the bot's operation: config, API, state, strategy, WS, risk."""
    def __init__(self, config: BotConfig):
        self.config = config
        self.api_client = BybitV5APIClient(config)
        self.perf_monitor = EnhancedPerformanceMonitor()

        # Initialize RiskMetrics using config for the primary symbol
        primary_symbol_cfg = config.symbols[0]
        self.risk_metrics = RiskMetrics(
            initial_equity=primary_symbol_cfg.risk_params.get("initial_equity", Decimal('0')),
            max_position_base=primary_symbol_cfg.risk_params.get("max_position_base", Decimal('0')),
            max_daily_loss_pct=primary_symbol_cfg.risk_params.get("max_daily_loss_pct", Decimal('0.05'))
        )

        # Bot state storage
        self.state = {
            "orders": {}, "market_data": {}, "exchange_info": {},
            "current_inventory": defaultdict(Decimal),
            "last_state_save": 0.0,
            "ws_public_state": ConnectionState.DISCONNECTED,
            "ws_private_state": ConnectionState.DISCONNECTED,
        }
        self.state_file_path = os.path.join(self.config.state_directory, "bot_state.json")

        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._ws_private_client: PybitWebSocket | None = None # pybit WS client
        self._ws_public_client: websockets.WebSocketClientProtocol | None = None # Manual WS client
        self._ws_reconnect_attempts = 0 # Track WS reconnect attempts

    # --- State Management ---
    async def load_state(self):
        """Loads bot state from file, deserializing Decimals and datetimes."""
        loaded_state = atomic_load_json(self.state_file_path, default_data={})
        if not loaded_state:
            logger.info("No previous state found or loaded. Starting fresh.")
            return # Start with initial empty state

        try:
            # Deserialize orders
            for oid, data_dict in loaded_state.get("orders", {}).items():
                data_dict['price'] = safe_decimal(data_dict.get('price'))
                data_dict['quantity'] = safe_decimal(data_dict.get('quantity'))
                data_dict['filled_qty'] = safe_decimal(data_dict.get('filled_qty'))
                data_dict['avg_price'] = safe_decimal(data_dict.get('avg_price'))
                data_dict['fee'] = safe_decimal(data_dict.get('fee'))
                data_dict['order_pnl'] = safe_decimal(data_dict.get('order_pnl'))
                data_dict['side'] = TradeSide(data_dict.get('side', 'None'))
                data_dict['status'] = OrderStatus(data_dict.get('status', 'New'))
                if data_dict.get('created_at'): data_dict['created_at'] = datetime.fromisoformat(data_dict['created_at'])
                if data_dict.get('updated_at'): data_dict['updated_at'] = datetime.fromisoformat(data_dict['updated_at'])
                self.state["orders"][oid] = OrderData(**data_dict)

            # Deserialize market_data
            for sym, data_dict in loaded_state.get("market_data", {}).items():
                for key in ['best_bid', 'best_ask', 'bid_size', 'ask_size', 'mid_price', 'spread', 'volume_24h', 'last_price', 'funding_rate', 'open_interest', 'mark_price', 'index_price']:
                    if key in data_dict and data_dict[key] is not None: data_dict[key] = safe_decimal(data_dict[key])
                self.state["market_data"][sym] = MarketData(**data_dict)

            # Deserialize inventory and risk metrics
            for sym, qty_str in loaded_state.get("current_inventory", {}).items():
                self.state["current_inventory"][sym] = safe_decimal(qty_str)

            rm_dict = loaded_state.get("risk_metrics", {})
            for key, val in rm_dict.items():
                if isinstance(getattr(self.risk_metrics, key), Decimal):
                    setattr(self.risk_metrics, key, safe_decimal(val))
                elif isinstance(getattr(self.risk_metrics, key), datetime):
                    try: setattr(self.risk_metrics, key, datetime.fromisoformat(val))
                    except: logger.warning(f"Failed to parse datetime for {key}: {val}")
                elif isinstance(getattr(self.risk_metrics, key), deque):
                    setattr(self.risk_metrics, key, deque(val, maxlen=getattr(self.risk_metrics, key).maxlen))
                else:
                    setattr(self.risk_metrics, key, val)

            self.state["last_state_save"] = loaded_state.get("last_state_save", 0.0)
            logger.info(f"Loaded state: {len(self.state['orders'])} orders, {len(self.state['market_data'])} market data, {len(self.state['current_inventory'])} inventory positions.")

        except Exception as e:
            logger.error(f"Error deserializing state data: {e}. Resetting state.", exc_info=True)
            # Reset to default state if deserialization fails
            self.state = {"orders": {}, "market_data": {}, "exchange_info": {}, "current_inventory": defaultdict(Decimal),
                          "last_state_save": 0.0, "ws_public_state": ConnectionState.DISCONNECTED, "ws_private_state": ConnectionState.DISCONNECTED,}

    def save_state(self):
        """Saves the current bot state atomically."""
        if time.time() - self.state["last_state_save"] < self.config.state_save_interval * 0.8:
            return # Avoid saving too frequently if interval is short

        serializable_state = {
            "orders": {oid: order.to_dict() for oid, order in self.state["orders"].items()},
            "market_data": {sym: mdata.to_dict() for sym, mdata in self.state["market_data"].items()},
            "current_inventory": {sym: str(qty) for sym, qty in self.state["current_inventory"].items()},
            "risk_metrics": self.risk_metrics.to_dict(),
            "exchange_info": self.state["exchange_info"], # Assuming exchange info is serializable
            "last_state_save": time.time(),
        }
        atomic_write_json(self.state_file_path, serializable_state)
        self.state["last_state_save"] = time.time()

    # --- Utility Methods ---
    def _quantize_price(self, price: Decimal, symbol: str) -> Decimal:
        """Quantizes price according to symbol's tick size from exchange info."""
        info = self.state["exchange_info"].get(symbol)
        tick_size_str = info.get('priceFilter', {}).get('tickSize') if info else None
        if tick_size_str:
            tick_size = Decimal(tick_size_str)
            return price.quantize(tick_size, rounding=ROUND_DOWN)
        logger.warning(f"Price tick size not found for {symbol}. Using default quantization.")
        return price.quantize(Decimal('0.01'), rounding=ROUND_DOWN)

    def _quantize_qty(self, qty: Decimal, symbol: str) -> Decimal:
        """Quantizes quantity according to symbol's lot size rules."""
        info = self.state["exchange_info"].get(symbol)
        min_qty_str = info.get('lotSizeFilter', {}).get('minOrderQty')
        qty_step_str = info.get('lotSizeFilter', {}).get('qtyStep')

        if min_qty_str and qty_step_str:
            min_qty = Decimal(min_qty_str)
            qty_step = Decimal(qty_step_str)

            quantized_qty = (qty / qty_step).quantize(Decimal('1'), rounding=ROUND_DOWN) * qty_step
            return max(min_qty, quantized_qty) # Ensure min order quantity is met
        logger.warning(f"Quantity precision/step/min not found for {symbol}. Using defaults.")
        return max(Decimal('0.001'), qty.quantize(Decimal('0.001'), rounding=ROUND_DOWN)) # Default


    def _calculate_fill_pnl(self, order_data: OrderData, fill_qty: Decimal, fill_price: Decimal, exec_fee: Decimal) -> Decimal:
        """Calculates realized PnL for a trade fill. Basic implementation assumes MM spread capture.
        Requires more robust inventory/cost tracking for accurate PnL calculation.
        """
        # Simplified PnL calculation: Assume market maker captures spread.
        # PnL is realized when a position is closed or offset.
        # For a single fill event in MM, PnL is often related to the fee or immediate spread profit.
        # This placeholder uses fee as a proxy, assuming the primary goal is spread capture over time.
        # A true calculation needs average entry price tracking.

        # Placeholder PnL: Assume fee is deducted. The actual profit comes from buying low and selling high.
        # A filled order contributes positively if it captures spread, negatively if it takes liquidity at a loss or high fee.
        # Let's return the negative fee as the immediate 'PnL' impact of this fill for simplicity.
        return -exec_fee # Net effect of this specific fill action (mainly fee impact)

    # --- Market Data & Exchange Info Fetching ---
    async def update_market_data(self, symbol: str):
        """Fetches and updates market data for a given symbol."""
        try:
            ticker_data = await self.api_client.get_ticker(symbol=symbol)
            if ticker_data:
                market_data = self.state["market_data"].get(symbol)
                if not market_data: # Initialize if not present
                    market_data = MarketData(symbol=symbol, best_bid=Decimal('0'), best_ask=Decimal('0'), bid_size=Decimal('0'), ask_size=Decimal('0'), timestamp=time.time())

                market_data.update_from_tick(ticker_data)
                self.state["market_data"][symbol] = market_data
                logger.debug(f"Updated market data for {symbol}: Mid={market_data.mid_price:.4f}, Spread={market_data.spread:.4f} ({market_data.spread_bps:.2f} bps)")
                self.perf_monitor.record_metric("market_data_updates")
            else: logger.warning(f"Received empty ticker data for {symbol}")
        except Exception as e:
            logger.error(f"Error updating market data for {symbol}: {e}", exc_info=True)
            self.perf_monitor.record_api_call(endpoint=f"/v5/market/tickers/{symbol}", success=False)

    async def fetch_exchange_info(self, symbol: str | None = None):
        """Fetches and caches exchange instrument information for precision and limits."""
        try:
            info_data = await self.api_client.get_exchange_info(symbol=symbol, category="linear")
            if info_data:
                updated_symbols = set()
                for sym, info in info_data.items():
                    self.state["exchange_info"][sym] = info
                    updated_symbols.add(sym)
                    # Update SymbolConfig precision settings
                    for cfg_symbol in self.config.symbols:
                        if cfg_symbol.symbol == sym:
                            cfg_symbol.price_precision = safe_decimal(info.get('priceFilter', {}).get('tickSize'), default=Decimal('0.01'))
                            cfg_symbol.qty_precision = safe_decimal(info.get('lotSizeFilter', {}).get('qtyStep'), default=Decimal('0.001'))
                            cfg_symbol.min_order_qty = safe_decimal(info.get('lotSizeFilter', {}).get('minOrderQty'), default=Decimal('0.001'))
                            logger.debug(f"Updated exchange info for {sym}: PricePrec={cfg_symbol.price_precision}, QtyPrec={cfg_symbol.qty_precision}, MinQty={cfg_symbol.min_order_qty}")
                self.perf_monitor.record_metric("exchange_info_updates")
                if symbol: logger.info(f"Fetched exchange info for {symbol}.")
                elif updated_symbols: logger.info(f"Fetched exchange info for {len(updated_symbols)} symbols.")
            else:
                logger.warning(f"Received empty exchange info for {symbol or 'all symbols'}.")
        except Exception as e:
            logger.error(f"Error fetching exchange info for {symbol or 'all symbols'}: {e}", exc_info=True)
            self.perf_monitor.record_api_call(endpoint="/v5/market/instruments-info", success=False)

    async def update_positions_and_pnl(self):
        """Fetches current positions and updates PnL components in risk metrics."""
        try:
            positions = await self.api_client.get_positions(category="linear")
            total_unrealized_pnl = Decimal('0')

            for pos in positions:
                symbol = pos.get('symbol')
                if not symbol: continue # Skip if no symbol

                size = safe_decimal(pos.get('size', '0'))
                side = pos.get('side', 'None')
                unrealized_pnl = safe_decimal(pos.get('unrealisedPnl', '0'))

                # Update inventory map
                self.state["current_inventory"][symbol] = size if side == 'Buy' else -size if side == 'Sell' else Decimal('0')

                # Aggregate unrealized PnL (consider USD value for multi-symbol)
                total_unrealized_pnl += unrealized_pnl
                logger.debug(f"Position Update ({symbol}): {side} {size}, Unrealized PnL: {unrealized_pnl:.4f}")

            self.risk_metrics.unrealized_pnl = total_unrealized_pnl
            # Update overall position for risk metrics (simplified for single symbol)
            if len(self.config.symbols) == 1 and self.config.symbols[0].symbol in self.state["current_inventory"]:
                self.risk_metrics.current_position_base = self.state["current_inventory"][self.config.symbols[0].symbol]

            self.risk_metrics.update_equity_and_drawdown() # Recalculate equity/drawdown
            logger.debug(f"Updated total unrealized PnL: {self.risk_metrics.unrealized_pnl:.4f}. Current equity: {self.risk_metrics.current_equity:.4f}")
            self.perf_monitor.record_metric("position_updates")

        except Exception as e:
            logger.error(f"Error updating positions or unrealized PnL: {e}", exc_info=True)
            self.perf_monitor.record_api_call(endpoint="/v5/position/list", success=False)

    # --- Strategy Logic ---
    async def process_symbol_strategy(self, symbol_config: SymbolConfig):
        """Main logic for placing and managing market making orders for a symbol."""
        symbol = symbol_config.symbol
        market_data = self.state["market_data"].get(symbol)
        exchange_info = self.state["exchange_info"].get(symbol)

        if not market_data or not exchange_info:
            logger.warning(f"Missing market data or exchange info for {symbol}. Skipping strategy.")
            return

        mid_price = market_data.mid_price
        if mid_price <= 0:
            logger.warning(f"Invalid mid price ({mid_price}) for {symbol}. Skipping strategy.")
            return

        # Calculate target prices and quantities, applying adjustments
        effective_spread_bps = symbol_config.spread_bps
        spread_amount = mid_price * (effective_spread_bps / Decimal('10000'))

        current_inventory = self.state["current_inventory"].get(symbol, Decimal('0'))
        skew_adjust_val = (current_inventory / symbol_config.max_position_base) * symbol_config.inventory_skew_factor * mid_price

        bid_price = self._quantize_price(mid_price - spread_amount / Decimal('2') + skew_adjust_val, symbol)
        ask_price = self._quantize_price(mid_price + spread_amount / Decimal('2') + skew_adjust_val, symbol)

        # Volatility adjustment for quantity
        volatility_factor = Decimal('1.0')
        if NUMPY_AVAILABLE:
            volatility = market_data.calculate_volatility(symbol) # Use the method in MarketData
            # Example: Increase quantity if volatile, decrease if calm
            volatility_factor = max(0.5, min(2.0, 1.0 + volatility * 2)) # Simple scaling
            logger.debug(f"Volatility for {symbol}: {volatility:.4f}. Volatility factor: {volatility_factor:.2f}")

        order_qty = self._quantize_qty(symbol_config.base_qty * volatility_factor * (1 - abs(current_inventory) / symbol_config.max_position_base), symbol) # Adjust qty based on inventory too
        order_qty = max(order_qty, symbol_config.min_order_qty) # Ensure minimum quantity

        if order_qty < symbol_config.min_order_qty:
            logger.warning(f"Calculated order quantity {order_qty} is below minimum {symbol_config.min_order_qty} for {symbol}. Skipping.")
            return

        # Check risk limits before potentially placing orders
        if self.risk_metrics.check_and_apply_risk_limits():
            logger.warning(f"Risk limits prevent placing new orders for {symbol}.")
            # Optionally cancel existing orders if risk is critical
            # await self.cancel_all_orders_for_symbol(symbol)
            return

        # Manage existing orders: Cancel stale ones, place new ones
        await self.manage_orders_for_symbol(symbol, symbol_config, bid_price, ask_price, order_qty)

    async def manage_orders_for_symbol(self, symbol: str, config: SymbolConfig, target_bid_price: Decimal, target_ask_price: Decimal, target_qty: Decimal):
        """Cancels stale orders and places new ones based on target prices/quantities."""
        current_open_orders = {
            order.order_id: order for order in self.state["orders"].values()
            if order.symbol == symbol and order.status in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]
        }

        existing_bid = next((o for o in current_open_orders.values() if o.side == TradeSide.BUY), None)
        existing_ask = next((o for o in current_open_orders.values() if o.side == TradeSide.SELL), None)

        cancellation_threshold_abs = market_data.mid_price * (self.config.order_cancellation_deviation_bps / Decimal('10000'))

        # Process Bid Order Management
        if existing_bid:
            if abs(existing_bid.price - target_bid_price) > cancellation_threshold_abs or not safe_decimal(existing_bid.quantity) == target_qty:
                logger.info(f"Cancelling stale BID order {existing_bid.order_id} for {symbol} (Price deviation or Qty mismatch).")
                await self.cancel_order_and_update_state(existing_bid)
                existing_bid = None # Clear reference
        if not existing_bid and target_bid_price > 0: # Place new bid if needed
             await self.place_order_and_update_state(symbol, TradeSide.BUY, "Limit", target_qty, target_bid_price, post_only=True, category="linear")

        # Process Ask Order Management
        if existing_ask:
            if abs(existing_ask.price - target_ask_price) > cancellation_threshold_abs or not safe_decimal(existing_ask.quantity) == target_qty:
                logger.info(f"Cancelling stale ASK order {existing_ask.order_id} for {symbol} (Price deviation or Qty mismatch).")
                await self.cancel_order_and_update_state(existing_ask)
                existing_ask = None
        if not existing_ask and target_ask_price > 0: # Place new ask if needed
            await self.place_order_and_update_state(symbol, TradeSide.SELL, "Limit", target_qty, target_ask_price, post_only=True, category="linear")

    async def cancel_order_and_update_state(self, order_data: OrderData):
        """Helper to cancel an order and update its status in state."""
        try:
            cancel_resp = await self.api_client.cancel_order(symbol=order_data.symbol, order_id=order_data.order_id, category="linear")
            if cancel_resp and cancel_resp.get('retCode') == 0:
                logger.info(f"Successfully requested cancellation for order {order_data.order_id}.")
                # Update state locally immediately, relying on WS/polling to confirm final status
                order_data.status = OrderStatus.CANCELLED
                self.state["orders"][order_data.order_id] = order_data # Update in state dict
                self.perf_monitor.record_metric("orders_cancelled")
            else:
                logger.error(f"Failed to cancel order {order_data.order_id}: {cancel_resp}")
                self.perf_monitor.record_metric("orders_rejected")
        except BybitAPIError as e: logger.error(f"API error cancelling order {order_data.order_id}: {e}")
        except Exception as e: logger.error(f"Unexpected error cancelling order {order_data.order_id}: {e}", exc_info=True)

    async def place_order_and_update_state(self, symbol, side, order_type, qty, price, post_only=False, category="linear"):
        """Helper to place an order and update state with the new order."""
        try:
            place_resp = await self.api_client.place_order(symbol=symbol, side=side, order_type=order_type, qty=qty, price=price, post_only=post_only, category=category)
            if place_resp and place_resp.get('retCode') == 0:
                order_info = place_resp.get('result', {}).get('order')
                if order_info:
                    order_obj = OrderData.from_api(order_info)
                    self.state["orders"][order_obj.order_id] = order_obj
                    self.perf_monitor.record_metric("orders_placed")
                    logger.info(f"Placed {order_obj.side.value} order {order_obj.order_id} for {symbol} @ {order_obj.price:.4f} Qty: {order_obj.quantity:.4f}")
                    return order_obj
                logger.warning(f"Order placement successful but no order info returned: {place_resp}")
            else:
                logger.error(f"Failed to place {side.value} order for {symbol}: {place_resp}")
                self.perf_monitor.record_metric("orders_rejected")
        except (BybitAPIError, InvalidOrderParameterError) as e: logger.error(f"Order placement API error: {e}")
        except Exception as e: logger.error(f"Unexpected error placing order: {e}", exc_info=True)
        return None

    async def sync_orders_status_via_polling(self):
        """Fetches open orders via REST API and updates internal state."""
        active_tracked_orders = [oid for oid, order in self.state["orders"].items() if order.status in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]]
        if not active_tracked_orders: return

        orders_by_symbol = defaultdict(list)
        for order_id in active_tracked_orders: orders_by_symbol[self.state["orders"][order_id].symbol].append(order_id)

        for symbol, order_ids_for_symbol in orders_by_symbol.items():
            try:
                open_orders_api = await self.api_client.get_open_orders(symbol=symbol, category="linear")
                api_orders_map = {str(o.get("orderId")): o for o in open_orders_api}

                for order_id in order_ids_for_symbol:
                    tracked_order = self.state["orders"][order_id]

                    if order_id in api_orders_map: # Order still open on exchange
                        api_order_info = api_orders_map[order_id]
                        updated_order = OrderData.from_api(api_order_info)

                        # Update if status or fill details changed
                        if tracked_order.status != updated_order.status or tracked_order.filled_qty != updated_order.filled_qty:
                            logger.info(f"Order {order_id} ({symbol}) status update: {tracked_order.status.value} -> {updated_order.status.value}. Filled: {updated_order.filled_qty:.4f}")

                            # Handle PnL and inventory updates on fill events
                            if updated_order.status == OrderStatus.FILLED or (updated_order.status == OrderStatus.PARTIALLY_FILLED and updated_order.filled_qty > tracked_order.filled_qty):
                                fill_qty = updated_order.filled_qty - tracked_order.filled_qty
                                if fill_qty > 0:
                                    fill_price = updated_order.avg_price # Use average price for the fill
                                    # Get fee for this specific fill if available, otherwise use order fee estimate
                                    exec_fee = safe_decimal(api_order_info.get('fee', api_order_info.get('execFee', '0')))

                                    pnl = self._calculate_fill_pnl(tracked_order, fill_qty, fill_price, exec_fee)
                                    self.risk_metrics.update_trade_stats(pnl)
                                    self.update_inventory(symbol, updated_order.side, fill_qty) # Update inventory state

                                    trade_logger.info(f"{datetime.now(timezone.utc).isoformat()},{symbol},{updated_order.side.value},{fill_qty},{fill_price},{pnl},{exec_fee},{order_id},POLLING_FILL")
                                    self.perf_monitor.record_metric("orders_filled") # Count as filled/partially filled

                            self.state["orders"][order_id] = updated_order # Update tracked order

                    else: # Order disappeared from active list - assume cancelled/rejected/expired
                        if tracked_order.status not in [OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED]:
                            logger.info(f"Order {order_id} ({symbol}) not found in active list. Marking as CANCELLED.")
                            tracked_order.status = OrderStatus.CANCELLED
                            self.state["orders"][order_id] = tracked_order # Update state
                            self.perf_monitor.record_metric("orders_cancelled")

            except Exception as e:
                logger.error(f"Error syncing order status for {symbol}: {e}", exc_info=True)
                self.perf_monitor.record_api_call(endpoint="/v5/order/active", success=False)

        # Cleanup: Remove fully processed orders from state
        orders_to_remove = [
            oid for oid, order in self.state["orders"].items()
            if order.symbol == symbol and order.status not in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]
        ]
        for oid in orders_to_remove:
            del self.state["orders"][oid]
            logger.debug(f"Removed inactive order {oid} from state.")

    # --- WebSocket Handling ---
    async def _websocket_auth(self, ws: websockets.WebSocketClientProtocol):
        """Authenticates a private WebSocket connection."""
        expires = int((time.time() + 10) * 1000)
        signature = hmac.new(self.config.api_secret.encode(), f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
        auth_message = {"op": "auth", "args": [self.config.api_key, expires, signature]}
        await ws.send(json.dumps(auth_message))

        try:
            response = json.loads(await ws.recv())
            if response.get('success') and response.get('ret_msg') == 'OK':
                logger.info("Private WebSocket authenticated successfully.")
                return True
            logger.error(f"Private WebSocket authentication failed: {response}")
            return False
        except Exception as e:
            logger.error(f"Error during private WebSocket authentication: {e}", exc_info=True)
            return False

    async def _handle_private_ws_message(self, message: dict[str, Any]):
        """Handles messages received from the private WebSocket."""
        logger.debug(f"Received private WS message: {message}")
        topic = message.get('topic')
        data = message.get('data')

        if not data: return

        if topic == "order": # Order updates
            for order_info in data:
                order_id = str(order_info.get('orderId'))
                symbol = order_info.get('symbol')
                exec_type = order_info.get('execType')

                if order_id in self.state["orders"]:
                    tracked_order: OrderData = self.state["orders"][order_id]
                    old_status = tracked_order.status
                    old_filled_qty = tracked_order.filled_qty

                    updated_order = OrderData.from_api(order_info) # Create new OrderData object from WS payload
                    self.state["orders"][order_id] = updated_order # Update state

                    if exec_type == 'Trade' and updated_order.filled_qty > old_filled_qty:
                        fill_qty = updated_order.filled_qty - old_filled_qty
                        fill_price = updated_order.avg_price
                        exec_fee = safe_decimal(order_info.get('execFee', '0')) # Fee for this specific fill

                        pnl = self._calculate_fill_pnl(tracked_order, fill_qty, fill_price, exec_fee)
                        self.risk_metrics.update_trade_stats(pnl)
                        self.update_inventory(symbol, updated_order.side, fill_qty)

                        trade_logger.info(f"{datetime.now(timezone.utc).isoformat()},{symbol},{updated_order.side.value},{fill_qty},{fill_price},{pnl},{exec_fee},{order_id},FILL_WS")
                        self.perf_monitor.record_metric("orders_filled")
                        logger.info(f"Trade fill via WS (Order {order_id}): {updated_order.side.value} {fill_qty:.4f} @ {fill_price:.4f}. PnL: {pnl:.4f}, Fee: {exec_fee:.6f}")

                    # Handle final status updates
                    if updated_order.status == OrderStatus.FILLED and old_status != OrderStatus.FILLED:
                        logger.info(f"Order {order_id} ({symbol}) fully filled via WebSocket.")
                    elif updated_order.status == OrderStatus.CANCELLED and old_status != OrderStatus.CANCELLED:
                        logger.info(f"Order {order_id} ({symbol}) cancelled via WebSocket.")
                        self.perf_monitor.record_metric("orders_cancelled")
                    elif updated_order.status == OrderStatus.REJECTED and old_status != OrderStatus.REJECTED:
                        logger.error(f"Order {order_id} ({symbol}) rejected via WebSocket: {order_info.get('rejectReason')}")
                        self.perf_monitor.record_metric("orders_rejected")

                else: # Order appeared on WS but not tracked locally - potentially add it?
                    logger.warning(f"New order {order_id} ({symbol}) appeared on WS not in tracked state. Adding.")
                    self.state["orders"][order_id] = OrderData.from_api(order_info)

        elif topic == "position": # Position updates
            for pos_info in data:
                symbol = pos_info.get('symbol')
                if not symbol: continue
                size = safe_decimal(pos_info.get('size', '0'))
                side = pos_info.get('side', 'None')
                unrealized_pnl = safe_decimal(pos_info.get('unrealisedPnl', '0'))

                self.state["current_inventory"][symbol] = size if side == 'Buy' else -size if side == 'Sell' else Decimal('0')
                # Update aggregated unrealized PnL and position metrics
                # Note: This assumes WS provides the total unrealized PnL correctly aggregated.
                self.risk_metrics.unrealized_pnl = unrealized_pnl # If WS provides per-symbol PnL, sum them if needed
                self.risk_metrics.current_position_base = self.state["current_inventory"].get(symbol, Decimal('0'))
                self.risk_metrics.update_equity_and_drawdown()
                logger.debug(f"WS Position Update ({symbol}): {side} {size}, Unrealized PnL: {unrealized_pnl:.4f}")

        elif topic == "wallet": # Wallet balance updates
            for wallet_info in data:
                coin = wallet_info.get('coin')
                equity = safe_decimal(wallet_info.get('equity', '0'))
                if coin in ('USDT', 'USD'): # Assuming quote currency is USDT or USD
                    self.risk_metrics.current_equity = equity
                    self.risk_metrics.update_equity_and_drawdown()
                    logger.info(f"WS Wallet Update ({coin}): Equity={equity:.4f}")


    async def websocket_private_listener(self):
        """Manages the private WebSocket connection for order, position, wallet updates."""
        while self._running and not shutdown_event.is_set():
            client = None
            try:
                if PYBIT_AVAILABLE:
                    client = PybitWebSocket(testnet=self.config.is_testnet, api_key=self.config.api_key, api_secret=self.config.api_secret)
                    client.order_stream(callback=lambda msg: asyncio.create_task(self._handle_private_ws_message(msg)))
                    client.position_stream(callback=lambda msg: asyncio.create_task(self._handle_private_ws_message(msg)))
                    client.wallet_stream(callback=lambda msg: asyncio.create_task(self._handle_private_ws_message(msg)))

                    logger.info("Subscribed to private WS streams (order, position, wallet) via pybit.")
                    self.state["ws_private_state"] = ConnectionState.AUTHENTICATED
                    self._ws_reconnect_attempts = 0

                    # Keep connection alive (pybit handles pings internally)
                    while self._running and not shutdown_event.is_set() and client._ws and not client._ws.closed:
                         await asyncio.sleep(1)
                    logger.warning("Pybit private WebSocket connection closed unexpectedly. Attempting reconnect.")

                else: # Manual WebSocket if pybit is not available
                    logger.info(f"Connecting to private WebSocket: {WS_PRIVATE_URL}")
                    async with websockets.connect(WS_PRIVATE_URL, ping_interval=self.config.ws_ping_interval, ping_timeout=self.config.ws_ping_timeout,
                                                  close_timeout=self.config.ws_close_timeout, max_size=self.config.ws_max_size) as websocket:
                        self.state["ws_private_state"] = ConnectionState.CONNECTED
                        if not await self._websocket_auth(websocket):
                            raise WebSocketConnectionError("Private WS auth failed.")
                        self.state["ws_private_state"] = ConnectionState.AUTHENTICATED
                        self._ws_reconnect_attempts = 0

                        subscribe_msg = {"op": "subscribe", "args": ["order", "position", "wallet"]}
                        await websocket.send(json.dumps(subscribe_msg))
                        logger.info("Subscribed to private WS streams.")

                        while self._running and not shutdown_event.is_set():
                            try:
                                message = await asyncio.wait_for(websocket.recv(), timeout=self.config.ws_ping_timeout + 5)
                                data = json.loads(message)
                                asyncio.create_task(self._handle_private_ws_message(data))
                            except asyncio.TimeoutError:
                                await websocket.ping() # Send ping if idle
                            except (websockets.exceptions.ConnectionClosedOK, websockets.exceptions.ConnectionClosedError) as e:
                                logger.warning(f"Private WebSocket connection closed: {e}. Reconnecting...")
                                break # Exit loop to trigger reconnect
                            except Exception as e:
                                logger.error(f"Error processing private WS message: {e}", exc_info=True)
                                break # Exit loop on error to trigger reconnect

            except Exception as e: # Catch connection errors and auth failures
                self.state["ws_private_state"] = ConnectionState.ERROR
                logger.error(f"Private WebSocket connection/setup failed: {e}. Reconnecting...", exc_info=True)

            # Cleanup before reconnect attempt
            if client: client.close() # Close pybit WS client if it was open
            self.perf_monitor.record_ws_reconnection()
            self._ws_reconnect_attempts += 1
            reconnect_delay = min(self.config.ws_reconnect_delay * (2 ** (self._ws_reconnect_attempts - 1)), self.config.ws_max_reconnect_delay)
            logger.info(f"Attempting private WebSocket reconnect in {reconnect_delay:.2f}s (attempt {self._ws_reconnect_attempts})...")
            await asyncio.sleep(reconnect_delay)
        logger.info("Private WebSocket listener stopped.")

    async def websocket_public_listener(self):
        """Manages public WebSocket for market data (tickers, orderbooks)."""
        while self._running and not shutdown_event.is_set():
            topics = [f"tickers.{cfg.symbol}" for cfg in self.config.symbols]
            topics.extend([f"orderbook.1.{cfg.symbol}" for cfg in self.config.symbols]) # Depth 1 orderbook

            try:
                logger.info(f"Connecting to public WebSocket: {WS_PUBLIC_URL}")
                async with websockets.connect(WS_PUBLIC_URL, ping_interval=self.config.ws_ping_interval,
                                              ping_timeout=self.config.ws_ping_timeout, close_timeout=self.config.ws_close_timeout,
                                              max_size=self.config.ws_max_size, compression=self.config.ws_compression) as websocket:

                    self.state["ws_public_state"] = ConnectionState.CONNECTED
                    self._ws_reconnect_attempts = 0

                    subscribe_msg = {"op": "subscribe", "args": topics}
                    await websocket.send(json.dumps(subscribe_msg))
                    logger.info(f"Subscribed to public WS topics: {', '.join(topics)}")

                    while self._running and not shutdown_event.is_set():
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=self.config.ws_ping_timeout + 5)
                            data = json.loads(message)

                            topic = data.get('topic')
                            if not topic: continue # Skip messages without topic

                            # Filter subscribed topics
                            if topic not in topics:
                                logger.debug(f"Ignoring unsubscribed topic: {topic}")
                                continue

                            await self._handle_public_ws_message(data) # Process message in background task

                        except asyncio.TimeoutError:
                            await websocket.ping() # Send ping if idle
                        except (websockets.exceptions.ConnectionClosedOK, websockets.exceptions.ConnectionClosedError) as e:
                            logger.warning(f"Public WebSocket connection closed: {e}. Reconnecting...")
                            break
                        except Exception as e:
                            logger.error(f"Error processing public WS message: {e}", exc_info=True)
                            break

            except Exception as e: # Catch connection errors
                self.state["ws_public_state"] = ConnectionState.ERROR
                logger.error(f"Public WebSocket connection/setup failed: {e}. Reconnecting...", exc_info=True)

            # Reconnection logic
            self.perf_monitor.record_ws_reconnection()
            self._ws_reconnect_attempts += 1
            reconnect_delay = min(self.config.ws_reconnect_delay * (2 ** (self._ws_reconnect_attempts - 1)), self.config.ws_max_reconnect_delay)
            logger.info(f"Attempting public WebSocket reconnect in {reconnect_delay:.2f}s (attempt {self._ws_reconnect_attempts})...")
            await asyncio.sleep(reconnect_delay)
        logger.info("Public WebSocket listener stopped.")

    async def _handle_public_ws_message(self, message: dict[str, Any]):
        """Handles messages received from the public WebSocket."""
        topic = message.get('topic')
        data_list = message.get('data')

        if not topic or not data_list: return

        # Process Ticker Updates
        if topic.startswith("tickers."):
            symbol = topic.split('.')[-1]
            if symbol in self.state["market_data"]:
                market_data = self.state["market_data"][symbol]
                # Ticker data comes as a list, often with one element for a specific symbol request
                if data_list and len(data_list) > 0:
                     market_data.update_from_tick(data_list[0]) # Update market data
                     self.perf_monitor.record_metric("market_data_updates")
                     logger.debug(f"WS Ticker Update ({symbol}): Mid={market_data.mid_price:.4f}")
            else: logger.warning(f"Received ticker update for untracked symbol: {symbol}")

        # Process Orderbook Updates (Depth 1)
        elif topic.startswith("orderbook.1."):
            symbol = topic.split('.')[-1]
            if symbol in self.state["market_data"]:
                market_data = self.state["market_data"][symbol]
                if data_list and len(data_list) > 0:
                    orderbook_data = data_list[0] # Orderbook data structure
                    # Update bid/ask/size from the payload
                    if orderbook_data.get('b') and len(orderbook_data['b']) > 0: # Bid side
                        market_data.best_bid = safe_decimal(orderbook_data['b'][0][0])
                        market_data.bid_size = safe_decimal(orderbook_data['b'][0][1])
                    if orderbook_data.get('a') and len(orderbook_data['a']) > 0: # Ask side
                        market_data.best_ask = safe_decimal(orderbook_data['a'][0][0])
                        market_data.ask_size = safe_decimal(orderbook_data['a'][0][1])

                    market_data.timestamp = float(safe_decimal(orderbook_data.get('ts', time.time()*1000))) / 1000
                    market_data._calculate_derived_metrics() # Recalculate mid/spread
                    market_data.track_volatility(symbol, market_data.last_price if market_data.last_price else market_data.mid_price) # Track price for volatility

                    self.state["market_data"][symbol] = market_data
                    logger.info(f"WS Orderbook Update ({symbol}): Bid={market_data.best_bid:.4f}, Ask={market_data.best_ask:.4f}")
                    self.perf_monitor.record_metric("market_data_updates")
            else: logger.warning(f"Received orderbook update for untracked symbol: {symbol}")

    # --- Main Bot Loops ---
    async def main_strategy_loop(self):
        """Main loop for executing the market making strategy."""
        while self._running and not shutdown_event.is_set():
            try:
                # Pre-checks: Ensure essential data is loaded
                for config in self.config.symbols:
                    if config.symbol not in self.state["market_data"] or config.symbol not in self.state["exchange_info"]:
                        logger.warning(f"Missing data for {config.symbol}. Fetching...")
                        await self.update_market_data(config.symbol)
                        await self.fetch_exchange_info(config.symbol)
                        if config.symbol not in self.state["market_data"] or config.symbol not in self.state["exchange_info"]:
                            logger.error(f"Failed to get essential data for {config.symbol}. Skipping strategy for this cycle.")
                            continue # Skip this symbol if data is still missing

                # Update positions and PnL from API (can be supplemented/replaced by WS if reliable)
                await self.update_positions_and_pnl()

                # Process strategy for each symbol
                strategy_tasks = [self.process_symbol_strategy(cfg) for cfg in self.config.symbols]
                await asyncio.gather(*strategy_tasks)

                # Periodically sync orders via REST as a backup or if WS is slow/down
                # Check if enough time has passed since last sync
                if time.time() - getattr(self.state, "_last_poll_sync_time", 0.0) > 60: # Poll every 60s
                    await self.sync_orders_status_via_polling()
                    self.state["_last_poll_sync_time"] = time.time()

                # Sleep interval before the next strategy cycle
                await asyncio.sleep(self.config.polling_interval_sec)

            except asyncio.CancelledError:
                logger.info("Main strategy loop task cancelled.")
                break
            except Exception as e:
                logger.error(f"Critical error in main strategy loop: {e}", exc_info=True)
                self.perf_monitor.record_metric("critical_errors", 1)
                await asyncio.sleep(self.config.polling_interval_sec * 2) # Backoff before retry

    async def _state_saving_loop(self):
        """Periodically saves the bot's state."""
        while self._running and not shutdown_event.is_set():
            await asyncio.sleep(self.config.state_save_interval)
            if self._running and not shutdown_event.is_set():
                self.save_state()

    async def _performance_monitoring_loop(self):
        """Periodically logs performance statistics and triggers GC."""
        while self._running and not shutdown_event.is_set():
            await asyncio.sleep(self.config.performance_monitoring_interval)
            if self._running and not shutdown_event.is_set():
                perf_stats = self.perf_monitor.get_stats()
                logger.info(f"Performance Metrics: {perf_stats}")
                # Trigger garbage collection periodically
                if time.time() - self.perf_monitor.last_gc_collection > 600: # Every 10 minutes
                    self.perf_monitor.trigger_gc()

    async def run(self):
        """Starts all bot tasks (strategy, WS listeners, state saving, monitoring)."""
        await self.load_state() # Load state first

        # Start background tasks
        self._tasks.append(asyncio.create_task(self.main_strategy_loop(), name="main_strategy_loop"))
        self._tasks.append(asyncio.create_task(self._state_saving_loop(), name="state_saving_loop"))
        self._tasks.append(asyncio.create_task(self._performance_monitoring_loop(), name="perf_monitor_loop"))
        self._tasks.append(asyncio.create_task(self.websocket_private_listener(), name="ws_private_listener"))
        self._tasks.append(asyncio.create_task(self.websocket_public_listener(), name="ws_public_listener"))

        logger.info("Bot tasks started. Waiting for shutdown signal...")
        # Wait until the shutdown event is set
        await shutdown_event.wait()
        logger.info("Shutdown signal received. Terminating bot.")

    async def shutdown(self):
        """Performs graceful shutdown: cancels tasks, closes connections, saves state."""
        logger.info("Executing graceful shutdown sequence...")
        self._running = False # Signal loops to stop

        # Cancel all running tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
                logger.debug(f"Cancelled task: {task.get_name()}")

        # Wait for tasks to finish cancellation
        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Error during task cleanup: {e}", exc_info=True)

        # Close WebSocket connections
        if self._ws_private_client:
            self._ws_private_client.close()
            logger.debug("Pybit private WebSocket client closed.")
        if self._ws_public_client and not self._ws_public_client.closed:
            await self._ws_public_client.close()
            logger.debug("Manual public WebSocket client closed.")

        # Close API session
        await self.api_client.close()

        # Save final state
        self.save_state()
        logger.info("Final state saved. Bot shut down successfully.")
        sys.exit(0)


# --- Main Entrypoint ---
async def main():
    """Sets up logging, configuration, bot instance, and runs the bot."""
    setup_logging()
    # Display Termux setup instructions only if running in Termux-like env or if first run
    if 'termux' in sys.stdout.encoding.lower() or not os.getenv("BYBIT_API_KEY"): # Basic check for Termux context
        print(Fore.CYAN + TERMUX_INSTALL_INSTRUCTIONS + Style.RESET_ALL)
        print(Fore.YELLOW + "INFO: For continuous operation, consider using 'nohup python your_script.py > bot.log 2>&1 &' in Termux." + Style.RESET_ALL)

    # --- Configuration Loading ---
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    is_testnet = os.getenv("BYBIT_TESTNET", "true").lower() in ["true", "1", "yes", "y"]

    if not api_key or not api_secret:
        logger.critical("API Key or Secret is missing. Please set BYBIT_API_KEY and BYBIT_API_SECRET environment variables.")
        sys.exit(1)

    # Define default symbol configurations (can be overridden by config file/DB)
    symbol_configs = [
        SymbolConfig(
            symbol="BTCUSDT",
            base_qty=Decimal("0.0001"), # Example quantity for testing
            order_levels=2, # Place 1 bid, 1 ask
            spread_bps=Decimal("0.05"), # 5 bps spread
            inventory_target_base=Decimal("0"),
            risk_params={ # Default risk parameters
                "max_position_base": Decimal('0.01'), # Max 0.01 BTC position
                "max_drawdown_pct": Decimal('5.0'),
                "initial_equity": Decimal('1000'), # Lower equity for testing
                "max_daily_loss_pct": Decimal('0.02')
            },
            min_spread_bps=Decimal('0.01'), max_spread_bps=Decimal('0.20')
        ),
    ]

    # Create BotConfig, prioritizing environment variables
    bot_config = BotConfig(
        api_key=api_key, api_secret=api_secret, is_testnet=is_testnet,
        symbols=symbol_configs,
        debug_mode=(os.getenv("DEBUG_MODE", "false").lower() == "true"),
        log_level=(os.getenv("DEBUG_MODE", "false").lower() == "true" and "DEBUG") or "INFO",
        polling_interval_sec=5.0, state_save_interval=180, performance_monitoring_interval=30
    )

    # TODO: Add loading config from file (e.g., JSON) here if desired

    bot = MarketMakerBot(bot_config)

    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()
    setup_signal_handlers(loop)

    logger.info(f"Market Maker Bot starting for {', '.join([s.symbol for s in bot_config.symbols])} on {'Testnet' if bot_config.is_testnet else 'Mainnet'}...")

    try:
        await bot.run() # Start the bot and wait for shutdown signal
    except asyncio.CancelledError:
        logger.info("Bot execution cancelled.") # Expected during shutdown
    except Exception as e:
        logger.critical(f"Fatal unhandled error during bot execution: {e}", exc_info=True)
    finally:
        await bot.shutdown() # Ensure shutdown sequence runs

# --- Script Execution ---
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(Fore.RED + "\nBot process terminated by KeyboardInterrupt." + Style.RESET_ALL)
        # The signal handler should have already initiated shutdown, but this provides a fallback message.
    except Exception as e:
        print(Fore.RED + f"\nUnhandled exception during script execution: {e}" + Style.RESET_ALL)
        sys.exit(1)
