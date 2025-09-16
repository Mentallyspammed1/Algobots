#!/usr/bin/env python3
"""
Advanced Supertrend Trading Bot for Bybit V5 API - Enhanced Edition v2.0

Enhanced features include:
- Multi-timeframe analysis for signal confirmation
- Real-time WebSocket for orders and positions
- Advanced order book analysis
- Adaptive indicator parameters
- Kelly Criterion position sizing
- Performance analytics and trade journaling
- Market regime detection
- Volume profile analysis
- Enhanced real-time terminal UI
- Robust state persistence and graceful shutdown
"""

import logging
import logging.handlers
import os
import pickle
import signal
import sys
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal, getcontext
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta
from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.exceptions import FailedRequestError, InvalidRequestError
from pybit.unified_trading import HTTP, WebSocket

# Initialize colorama for cross-platform colored terminal output
init(autoreset=True)
# Load environment variables from .env file
load_dotenv()
# Set decimal precision for financial calculations
getcontext().prec = 10

# =====================================================================
# CONFIGURATION & ENUMS
# =====================================================================

class Signal(Enum):
    STRONG_BUY = 2
    BUY = 1
    NEUTRAL = 0
    SELL = -1
    STRONG_SELL = -2

class OrderType(Enum):
    MARKET = "Market"
    LIMIT = "Limit"
    # LIMIT_MAKER is typically "Limit" with postOnly=True, handled in logic

class MarketRegime(Enum):
    TRENDING_UP = "Trending Up"
    TRENDING_DOWN = "Trending Down"
    RANGING = "Ranging"
    VOLATILE = "Volatile"
    CALM = "Calm"
    UNKNOWN = "Unknown"

@dataclass
class EnhancedConfig:
    """Enhanced bot configuration with advanced features."""
    # API Configuration
    API_KEY: str = os.getenv("BYBIT_API_KEY", "")
    API_SECRET: str = os.getenv("BYBIT_API_SECRET", "")
    TESTNET: bool = os.getenv("BYBIT_TESTNET", "true").lower() in ['true', '1']

    # Trading Configuration
    SYMBOL: str = os.getenv("BYBIT_SYMBOL", "BTCUSDT")
    CATEGORY: str = os.getenv("BYBIT_CATEGORY", "linear") # "linear", "spot", "inverse"
    LEVERAGE: Decimal = Decimal(os.getenv("BYBIT_LEVERAGE", "10"))

    # Multi-timeframe Configuration
    PRIMARY_TIMEFRAME: str = os.getenv("PRIMARY_TIMEFRAME", "15") # e.g., "1", "5", "15", "60", "240", "D"
    SECONDARY_TIMEFRAMES: list[str] = field(default_factory=lambda: ["5", "60"]) # Additional TFs for confirmation
    LOOKBACK_PERIODS: int = int(os.getenv("LOOKBACK_PERIODS", "200")) # Klines to fetch initially

    # Adaptive SuperTrend Parameters
    ST_PERIOD_BASE: int = int(os.getenv("ST_PERIOD", "10"))
    ST_MULTIPLIER_BASE: Decimal = Decimal(os.getenv("ST_MULTIPLIER", "3.0"))
    ADAPTIVE_PARAMS: bool = os.getenv("ADAPTIVE_PARAMS", "true").lower() in ['true', '1']

    # Risk Management
    RISK_PER_TRADE_PCT: Decimal = Decimal(os.getenv("RISK_PER_TRADE_PCT", "1.0")) # % of equity risked per trade
    MAX_POSITION_SIZE_PCT: Decimal = Decimal(os.getenv("MAX_POSITION_SIZE_PCT", "30.0")) # Max % of equity for position
    STOP_LOSS_PCT: Decimal = Decimal(os.getenv("STOP_LOSS_PCT", "1.5")) # Default SL % if ATR_STOPS is false
    TAKE_PROFIT_PCT: Decimal = Decimal(os.getenv("TAKE_PROFIT_PCT", "3.0")) # Default TP % if ATR_STOPS is false
    USE_ATR_STOPS: bool = os.getenv("USE_ATR_STOPS", "true").lower() in ['true', '1']
    ATR_STOP_MULTIPLIER: Decimal = Decimal(os.getenv("ATR_STOP_MULTIPLIER", "1.5")) # ATR Multiplier for SL
    ATR_TP_MULTIPLIER: Decimal = Decimal(os.getenv("ATR_TP_MULTIPLIER", "3.0")) # ATR Multiplier for TP

    # Daily Limits
    MAX_DAILY_LOSS_PCT: Decimal = Decimal(os.getenv("MAX_DAILY_LOSS_PCT", "5.0"))
    MAX_DAILY_TRADES: int = int(os.getenv("MAX_DAILY_TRADES", "10"))
    MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
    MAX_DRAWDOWN_PCT: Decimal = Decimal(os.getenv("MAX_DRAWDOWN_PCT", "10.0")) # Max % drop from peak equity

    # Order Type & Execution
    ORDER_TYPE: str = os.getenv("ORDER_TYPE", "Market") # "Market" or "Limit"
    LIMIT_ORDER_OFFSET_PCT: Decimal = Decimal(os.getenv("LIMIT_ORDER_OFFSET_PCT", "0.01"))  # Place limit orders 0.01% better than market
    POST_ONLY_LIMIT_ORDERS: bool = os.getenv("POST_ONLY_LIMIT_ORDERS", "true").lower() in ['true', '1']

    # Signal Filters
    ADX_TREND_FILTER: bool = os.getenv("ADX_TREND_FILTER", "true").lower() in ['true', '1']
    ADX_MIN_THRESHOLD: int = int(os.getenv("ADX_MIN_THRESHOLD", "25"))
    VOLUME_FILTER: bool = os.getenv("VOLUME_FILTER", "true").lower() in ['true', '1']
    VOLUME_MULTIPLIER: Decimal = Decimal(os.getenv("VOLUME_MULTIPLIER", "1.5")) # Volume must be 1.5x avg
    RSI_FILTER: bool = os.getenv("RSI_FILTER", "true").lower() in ['true', '1']
    RSI_OVERSOLD: int = int(os.getenv("RSI_OVERSOLD", "30"))
    RSI_OVERBOUGHT: int = int(os.getenv("RSI_OVERBOUGHT", "70"))

    # Market Structure
    USE_ORDER_BOOK: bool = os.getenv("USE_ORDER_BOOK", "true").lower() in ['true', '1']
    ORDER_BOOK_IMBALANCE_THRESHOLD: Decimal = Decimal(os.getenv("ORDER_BOOK_IMBALANCE_THRESHOLD", "0.6")) # 60% imbalance
    ORDER_BOOK_DEPTH_LEVELS: int = int(os.getenv("ORDER_BOOK_DEPTH_LEVELS", "10")) # Levels to fetch
    USE_VOLUME_PROFILE: bool = os.getenv("USE_VOLUME_PROFILE", "true").lower() in ['true', '1']

    # Partial Take Profit
    PARTIAL_TP_ENABLED: bool = os.getenv("PARTIAL_TP_ENABLED", "true").lower() in ['true', '1']
    PARTIAL_TP_TARGETS: list[dict[str, Decimal]] = field(default_factory=lambda: [
        {"profit_pct": Decimal("1.0"), "close_qty_pct": Decimal("0.3")}, # Close 30% at 1% profit
        {"profit_pct": Decimal("2.0"), "close_qty_pct": Decimal("0.3")}, # Close another 30% at 2% profit
        {"profit_pct": Decimal("3.0"), "close_qty_pct": Decimal("0.4")}  # Close remaining 40% at 3% profit
    ])

    # Breakeven & Trailing Stop
    BREAKEVEN_PROFIT_PCT: Decimal = Decimal(os.getenv("BREAKEVEN_PROFIT_PCT", "0.5")) # Move SL to entry at 0.5% profit
    BREAKEVEN_OFFSET_PCT: Decimal = Decimal(os.getenv("BREAKEVEN_OFFSET_PCT", "0.01")) # Offset above entry for breakeven SL
    TRAILING_SL_ENABLED: bool = os.getenv("TRAILING_SL_ENABLED", "true").lower() in ['true', '1']
    TRAILING_SL_ACTIVATION_PCT: Decimal = Decimal(os.getenv("TRAILING_SL_ACTIVATION_PCT", "1.0")) # Activate trailing SL at 1% profit
    TRAILING_SL_DISTANCE_PCT: Decimal = Decimal(os.getenv("TRAILING_SL_DISTANCE_PCT", "0.5")) # Trail by 0.5%

    # Performance & Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    SAVE_TRADES_CSV: bool = os.getenv("SAVE_TRADES_CSV", "true").lower() in ['true', '1']
    TRADES_FILE: str = "trades_history.csv"
    STATE_FILE: str = "bot_state.pkl"
    SAVE_STATE_INTERVAL: int = int(os.getenv("SAVE_STATE_INTERVAL", "300"))  # seconds

    # Kelly Criterion
    USE_KELLY_SIZING: bool = os.getenv("USE_KELLY_SIZING", "false").lower() in ['true', '1']
    KELLY_FRACTION_CAP: Decimal = Decimal(os.getenv("KELLY_FRACTION_CAP", "0.25"))  # Max 25% of Kelly fraction

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Convert category and order type to enums for internal use
        self.CATEGORY_ENUM = self.CATEGORY
        self.ORDER_TYPE_ENUM = OrderType[self.ORDER_TYPE.upper()]

        # Validate percentages
        for attr in ['RISK_PER_TRADE_PCT', 'STOP_LOSS_PCT', 'TAKE_PROFIT_PCT',
                     'MAX_DAILY_LOSS_PCT', 'BREAKEVEN_PROFIT_PCT',
                     'BREAKEVEN_OFFSET_PCT', 'TRAILING_SL_ACTIVATION_PCT',
                     'TRAILING_SL_DISTANCE_PCT', 'KELLY_FRACTION_CAP']:
            val = getattr(self, attr)
            if not isinstance(val, Decimal) or val < 0:
                raise ValueError(f"Configuration error: {attr} must be a non-negative Decimal.")

        # Sort partial TP targets by profit percentage
        self.PARTIAL_TP_TARGETS.sort(key=lambda x: x['profit_pct'])

        # Ensure leverage is 1 for SPOT
        if self.CATEGORY.lower() == "spot":
            self.LEVERAGE = Decimal('1')


# =====================================================================
# DATA STRUCTURES
# =====================================================================

@dataclass
class MarketData:
    """Real-time market data container for a specific timeframe."""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    open: Decimal = Decimal('0')
    high: Decimal = Decimal('0')
    low: Decimal = Decimal('0')
    close: Decimal = Decimal('0')
    volume: Decimal = Decimal('0')
    bid: Decimal = Decimal('0')
    ask: Decimal = Decimal('0')
    spread_pct: Decimal = Decimal('0')
    order_book_imbalance: Decimal = Decimal('0')
    vwap: Decimal = Decimal('0')

@dataclass
class Position:
    """Active position information."""
    symbol: str
    side: str # "Buy" or "Sell"
    size: Decimal # Quantity
    entry_price: Decimal
    current_price: Decimal = Decimal('0')
    unrealized_pnl: Decimal = Decimal('0')
    realized_pnl: Decimal = Decimal('0')
    stop_loss: Decimal = Decimal('0')
    take_profit: Decimal = Decimal('0')
    breakeven_activated: bool = False
    trailing_sl_activated: bool = False
    partial_closes: list[dict[str, Decimal]] = field(default_factory=list) # [{'profit_pct': Decimal, 'closed_qty': Decimal}]
    entry_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    order_id: str | None = None # Bybit order ID for the entry order

    @property
    def pnl_pct(self) -> Decimal:
        if self.entry_price == 0:
            return Decimal('0')
        if self.side == "Buy":
            return ((self.current_price - self.entry_price) / self.entry_price) * Decimal('100')
        else: # Sell
            return ((self.entry_price - self.current_price) / self.entry_price) * Decimal('100')

    @property
    def duration(self) -> timedelta:
        return datetime.now(timezone.utc) - self.entry_time

@dataclass
class Trade:
    """Completed trade record."""
    symbol: str
    side: str
    entry_price: Decimal
    exit_price: Decimal
    size: Decimal
    pnl: Decimal
    pnl_pct: Decimal
    entry_time: datetime
    exit_time: datetime
    duration: timedelta
    exit_reason: str
    fees: Decimal = Decimal('0')

@dataclass
class PerformanceMetrics:
    """Performance tracking metrics."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: Decimal = Decimal('0')
    total_fees: Decimal = Decimal('0')

    # Streak tracking
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # Statistics
    win_rate: Decimal = Decimal('0')
    profit_factor: Decimal = Decimal('0')
    sharpe_ratio: Decimal = Decimal('0')
    sortino_ratio: Decimal = Decimal('0') # Not implemented, but good to have
    calmar_ratio: Decimal = Decimal('0') # Not implemented, but good to have

    # Drawdown
    max_drawdown: Decimal = Decimal('0') # %
    current_drawdown: Decimal = Decimal('0') # %
    peak_balance: Decimal = Decimal('0')

    # Trade statistics
    avg_win_pct: Decimal = Decimal('0')
    avg_loss_pct: Decimal = Decimal('0')
    avg_trade_duration: timedelta = timedelta()
    best_trade_pct: Decimal = Decimal('0')
    worst_trade_pct: Decimal = Decimal('0')

    # Daily tracking
    daily_pnl: dict[str, Decimal] = field(default_factory=dict) # Date -> PnL
    daily_trades: dict[str, int] = field(default_factory=dict) # Date -> Trade Count

    # For Kelly Criterion
    historical_returns: list[Decimal] = field(default_factory=list)

    def update(self, trade: Trade, current_balance: Decimal):
        """Update metrics with a new completed trade."""
        self.total_trades += 1
        self.total_pnl += trade.pnl
        self.total_fees += trade.fees
        self.historical_returns.append(trade.pnl_pct)

        # Track daily stats
        today = trade.exit_time.strftime("%Y-%m-%d")
        self.daily_pnl[today] = self.daily_pnl.get(today, Decimal('0')) + trade.pnl
        self.daily_trades[today] = self.daily_trades.get(today, 0) + 1

        # Update win/loss stats
        if trade.pnl > 0:
            self.winning_trades += 1
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            self.max_consecutive_wins = max(self.max_consecutive_wins, self.consecutive_wins)
            self.best_trade_pct = max(self.best_trade_pct, trade.pnl_pct)
        else:
            self.losing_trades += 1
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            self.max_consecutive_losses = max(self.max_consecutive_losses, self.consecutive_losses)
            self.worst_trade_pct = min(self.worst_trade_pct, trade.pnl_pct)

        # Calculate averages for win/loss PnL %
        winning_pnl_pcts = [r for r in self.historical_returns if r > 0]
        losing_pnl_pcts = [r for r in self.historical_returns if r < 0]

        self.avg_win_pct = sum(winning_pnl_pcts) / len(winning_pnl_pcts) if winning_pnl_pcts else Decimal('0')
        self.avg_loss_pct = sum(losing_pnl_pcts) / len(losing_pnl_pcts) if losing_pnl_pcts else Decimal('0')

        # Update ratios
        self.win_rate = Decimal(self.winning_trades) / Decimal(self.total_trades) if self.total_trades > 0 else Decimal('0')

        if self.avg_loss_pct != 0:
            self.profit_factor = abs(self.avg_win_pct * self.winning_trades) / abs(self.avg_loss_pct * self.losing_trades) if self.losing_trades > 0 else Decimal('inf')
        else:
            self.profit_factor = Decimal('inf') if self.winning_trades > 0 else Decimal('0')

        # Update average duration
        self.avg_trade_duration = (
            (self.avg_trade_duration * (self.total_trades - 1) + trade.duration) / self.total_trades
            if self.total_trades > 0 else timedelta()
        )

        # Update Drawdown
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
            self.current_drawdown = Decimal('0')
        else:
            self.current_drawdown = ((self.peak_balance - current_balance) / self.peak_balance) * Decimal('100')
            self.max_drawdown = max(self.max_drawdown, self.current_drawdown)

    def calculate_sharpe_ratio(self, risk_free_rate: Decimal = Decimal('0')) -> Decimal:
        """Calculate Sharpe ratio from historical returns."""
        if len(self.historical_returns) < 2:
            return Decimal('0')

        # Convert to daily returns in Decimal
        daily_returns_decimal = [self.daily_pnl.get(d, Decimal('0')) for d in sorted(self.daily_pnl.keys())]
        if not daily_returns_decimal or len(daily_returns_decimal) < 2:
            return Decimal('0')

        # Convert to float for numpy calculations
        daily_returns_float = np.array([float(r) for r in daily_returns_decimal])

        avg_return = np.mean(daily_returns_float)
        std_dev = np.std(daily_returns_float)

        if std_dev == 0:
            return Decimal('0')

        # Annualize (assuming 252 trading days for daily returns)
        annualized_sharpe = (Decimal(str(avg_return)) - risk_free_rate) / Decimal(str(std_dev)) * Decimal(str(np.sqrt(252)))
        return annualized_sharpe

    def calculate_kelly_fraction(self, kelly_fraction_cap: Decimal = Decimal('1.0')) -> Decimal:
        """Calculate optimal Kelly Criterion fraction."""
        if self.winning_trades == 0 or self.losing_trades == 0:
            return Decimal('0')

        p = self.win_rate
        q = Decimal('1') - p

        if p == 0 or q == 0: # Avoid division by zero
            return Decimal('0')

        # Average win and average loss as fractions (not percentages)
        W = self.avg_win_pct / Decimal('100')
        L = abs(self.avg_loss_pct / Decimal('100'))

        if L == 0: # Avoid division by zero if no losses
            return Decimal('0') if p > 0 else Decimal('0')

        kelly_f = (p * W - q * L) / (W * L) # Original formula

        # Simplified Kelly if using Win Rate and Avg Win/Loss ratios
        # kelly_f = p - (q / (W / L))

        return max(Decimal('0'), min(kelly_f, kelly_fraction_cap))


@dataclass
class BotState:
    """Enhanced thread-safe state manager."""
    # System
    symbol: str
    bot_status: str = "Initializing"
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    errors_count: int = 0
    last_error: str | None = None

    # Market data
    market_regime: MarketRegime = MarketRegime.UNKNOWN
    current_price: Decimal = Decimal('0')
    price_direction: int = 0  # 1=up, -1=down, 0=neutral from last tick
    market_data: dict[str, MarketData] = field(default_factory=dict) # TF -> MarketData

    # Indicators
    supertrend_direction: str = "Neutral" # From primary TF
    supertrend_line: Decimal | None = None # From primary TF
    indicator_values: dict[str, Any] = field(default_factory=dict) # Primary TF indicators
    signal_strength: Decimal = Decimal('0') # Combined signal confidence
    last_signal: Signal | None = None
    last_signal_time: datetime | None = None
    last_signal_reason: str = "N/A"

    # Position
    position: Position | None = None
    pending_orders: list[dict] = field(default_factory=list) # List of active pending orders

    # Performance
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    account_balance: Decimal = Decimal('0')
    initial_balance: Decimal = Decimal('0') # Balance at bot start
    daily_start_balance: Decimal = Decimal('0') # Balance at start of current day

    # Logging
    log_messages: deque[str] = field(default_factory=lambda: deque(maxlen=20)) # Buffer for UI logs
    trade_history: list[Trade] = field(default_factory=list)

    # Thread safety
    lock: threading.RLock = field(default_factory=threading.RLock)

    def update(self, **kwargs):
        """Thread-safe state update."""
        with self.lock:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)

    def add_log(self, message: str, level: str = "INFO"):
        """Add a log message to the UI buffer."""
        with self.lock:
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.log_messages.append(f"{timestamp} [{level}] {message}")

    def save_state(self, filepath: str):
        """Save current state to file."""
        try:
            with self.lock:
                state_dict = {
                    'metrics': self.metrics,
                    'trade_history': self.trade_history,
                    'initial_balance': self.initial_balance,
                    'daily_start_balance': self.daily_start_balance
                }
                with open(filepath, 'wb') as f:
                    pickle.dump(state_dict, f)
                self.add_log(f"Bot state saved to {filepath}", "INFO")
        except Exception as e:
            self.add_log(f"Failed to save state: {e}", "ERROR")

    def load_state(self, filepath: str) -> bool:
        """Load state from file."""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    state_dict = pickle.load(f)
                    with self.lock:
                        self.metrics = state_dict.get('metrics', PerformanceMetrics())
                        self.trade_history = state_dict.get('trade_history', [])
                        self.initial_balance = state_dict.get('initial_balance', Decimal('0'))
                        self.daily_start_balance = state_dict.get('daily_start_balance', Decimal('0'))
                self.add_log(f"Bot state loaded from {filepath}", "INFO")
                return True
        except Exception as e:
            self.add_log(f"Failed to load state: {e}", "ERROR")
        return False

# =====================================================================
# ENHANCED UI
# =====================================================================

class EnhancedUI(threading.Thread):
    """Advanced terminal UI with comprehensive display."""

    def __init__(self, state: BotState, config: EnhancedConfig):
        super().__init__(daemon=True, name="EnhancedUI")
        self.state = state
        self.config = config
        self._stop_event = threading.Event()
        self.last_render_time = time.time()
        self.render_interval = 1 # seconds

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            if time.time() - self.last_render_time >= self.render_interval:
                self.display()
                self.last_render_time = time.time()
            time.sleep(0.1) # Small sleep to avoid busy-waiting

    def display(self):
        with self.state.lock:
            os.system('cls' if os.name == 'nt' else 'clear')

            self._display_header()
            self._display_market_overview()
            self._display_indicators()
            self._display_position()
            self._display_performance()
            self._display_logs()
            self._display_footer()

    def _display_header(self):
        print(Style.BRIGHT + Fore.CYAN + "=" * 80 + Style.RESET_ALL)
        status_color = Fore.GREEN if "Live" in self.state.bot_status else Fore.YELLOW
        print(Style.BRIGHT + Fore.CYAN +
              f"    ADVANCED SUPERTREND BOT v2.0 | {self.state.symbol} | Status: {status_color}{self.state.bot_status}{Style.RESET_ALL}")
        print(Style.BRIGHT + Fore.CYAN + "=" * 80 + Style.RESET_ALL)

    def _display_market_overview(self):
        print(Style.BRIGHT + "\n📊 MARKET OVERVIEW" + Style.RESET_ALL)
        print("-" * 40)

        # Price
        price_color = (Fore.GREEN if self.state.price_direction == 1 else
                      Fore.RED if self.state.price_direction == -1 else Fore.WHITE)
        arrow = "↑" if self.state.price_direction == 1 else "↓" if self.state.price_direction == -1 else "→"
        print(f"Price: {price_color}{self.state.current_price:.4f} {arrow}{Style.RESET_ALL}")

        # Market data from primary timeframe
        if self.config.PRIMARY_TIMEFRAME in self.state.market_data:
            data = self.state.market_data[self.config.PRIMARY_TIMEFRAME]
            if data.bid > 0 and data.ask > 0:
                print(f"Bid/Ask: {data.bid:.4f} / {data.ask:.4f} (Spread: {data.spread_pct:.3f}%)")
            if data.volume > 0:
                print(f"Volume: {data.volume:,.0f}")
            if data.order_book_imbalance != 0:
                imb_color = (Fore.GREEN if data.order_book_imbalance > self.config.ORDER_BOOK_IMBALANCE_THRESHOLD else
                            Fore.RED if data.order_book_imbalance < -self.config.ORDER_BOOK_IMBALANCE_THRESHOLD else Fore.YELLOW)
                print(f"Order Book Imbalance: {imb_color}{data.order_book_imbalance:.2%}{Style.RESET_ALL}")
            if data.vwap > 0:
                print(f"VWAP: {data.vwap:.4f}")

        # Market regime
        regime_colors = {
            MarketRegime.TRENDING_UP: Fore.GREEN,
            MarketRegime.TRENDING_DOWN: Fore.RED,
            MarketRegime.RANGING: Fore.YELLOW,
            MarketRegime.VOLATILE: Fore.MAGENTA,
            MarketRegime.CALM: Fore.CYAN,
            MarketRegime.UNKNOWN: Fore.WHITE
        }
        regime_color = regime_colors.get(self.state.market_regime, Fore.WHITE)
        print(f"Market Regime: {regime_color}{self.state.market_regime.value}{Style.RESET_ALL}")

    def _display_indicators(self):
        print(Style.BRIGHT + "\n📈 TECHNICAL INDICATORS" + Style.RESET_ALL)
        print("-" * 40)

        # SuperTrend
        st_color = (Fore.GREEN if self.state.supertrend_direction == "Uptrend" else
                   Fore.RED if self.state.supertrend_direction == "Downtrend" else Fore.YELLOW)
        st_value = f"{self.state.supertrend_line:.4f}" if self.state.supertrend_line else "Calculating..."
        print(f"SuperTrend ({self.config.PRIMARY_TIMEFRAME}): {st_color}{self.state.supertrend_direction} @ {st_value}{Style.RESET_ALL}")

        # Other indicators
        indicators = self.state.indicator_values
        if indicators:
            # RSI
            rsi = indicators.get('rsi')
            if rsi is not None:
                rsi_color = (Fore.RED if rsi > self.config.RSI_OVERBOUGHT else Fore.GREEN if rsi < self.config.RSI_OVERSOLD else Fore.YELLOW)
                print(f"RSI: {rsi_color}{rsi:.1f}{Style.RESET_ALL}", end=" | ")

            # ADX
            adx = indicators.get('adx')
            if adx is not None:
                adx_color = Fore.GREEN if adx > self.config.ADX_MIN_THRESHOLD else Fore.YELLOW
                print(f"ADX: {adx_color}{adx:.1f}{Style.RESET_ALL}", end=" | ")

            # MACD
            macd = indicators.get('macd_hist')
            if macd is not None:
                macd_color = Fore.GREEN if macd > 0 else Fore.RED
                print(f"MACD Hist: {macd_color}{macd:.4f}{Style.RESET_ALL}")

            # Volume
            vol_ratio = indicators.get('volume_ratio')
            if vol_ratio is not None:
                vol_color = Fore.GREEN if vol_ratio > self.config.VOLUME_MULTIPLIER else Fore.YELLOW
                print(f"Volume Ratio: {vol_color}{vol_ratio:.2f}x{Style.RESET_ALL}")

            # Ehlers Filter
            ehlers_filter = indicators.get('ehlers_filter')
            if ehlers_filter is not None:
                print(f"Ehlers Filter: {ehlers_filter:.4f}")

        # Signal strength
        if self.state.last_signal != Signal.NEUTRAL:
            strength_color = (Fore.GREEN if self.state.signal_strength > Decimal('0.7') else
                            Fore.YELLOW if self.state.signal_strength > Decimal('0.5') else Fore.RED)
            bars = "█" * int(self.state.signal_strength * 10)
            print(f"Signal Strength: {strength_color}{bars} {self.state.signal_strength:.1%}{Style.RESET_ALL}")

        # Last signal
        if self.state.last_signal and self.state.last_signal_time:
            signal_age = (datetime.now(timezone.utc) - self.state.last_signal_time).total_seconds()
            signal_color = Fore.GREEN if self.state.last_signal.value > 0 else Fore.RED if self.state.last_signal.value < 0 else Fore.YELLOW
            print(f"Last Signal: {signal_color}{self.state.last_signal.name}{Style.RESET_ALL} ({signal_age:.0f}s ago) - {self.state.last_signal_reason}")

    def _display_position(self):
        print(Style.BRIGHT + "\n💼 POSITION" + Style.RESET_ALL)
        print("-" * 40)

        if self.state.position:
            pos = self.state.position

            # Position details
            side_color = Fore.GREEN if pos.side == "Buy" else Fore.RED
            print(f"Side: {side_color}{pos.side}{Style.RESET_ALL} | Size: {pos.size:.4f}")
            print(f"Entry: ${pos.entry_price:.4f} | Current: ${pos.current_price:.4f}")

            # PnL
            pnl_color = Fore.GREEN if pos.unrealized_pnl >= 0 else Fore.RED
            pnl_pct_color = Fore.GREEN if pos.pnl_pct >= 0 else Fore.RED
            print(f"PnL: {pnl_color}${pos.unrealized_pnl:.2f}{Style.RESET_ALL} "
                  f"({pnl_pct_color}{pos.pnl_pct:+.2f}%{Style.RESET_ALL})")

            # Risk levels
            print(f"SL: ${pos.stop_loss:.4f} | TP: ${pos.take_profit:.4f}")

            # Status flags
            flags = []
            if pos.breakeven_activated:
                flags.append(f"{Fore.GREEN}BREAKEVEN{Style.RESET_ALL}")
            if pos.trailing_sl_activated:
                flags.append(f"{Fore.CYAN}TRAILING{Style.RESET_ALL}")
            if pos.partial_closes:
                closed_pct = sum(p['closed_qty_pct'] for p in pos.partial_closes) * Decimal('100')
                flags.append(f"{Fore.YELLOW}PARTIAL {closed_pct:.0f}%{Style.RESET_ALL}")

            if flags:
                print(f"Status: {' | '.join(flags)}")

            # Duration
            duration = pos.duration
            hours = duration.total_seconds() // 3600
            minutes = (duration.total_seconds() % 3600) // 60
            print(f"Duration: {hours:.0f}h {minutes:.0f}m")
        else:
            print(Fore.YELLOW + "No active position" + Style.RESET_ALL)

            # Show account balance
            if self.state.account_balance > 0:
                balance_change = self.state.account_balance - self.state.initial_balance
                balance_color = Fore.GREEN if balance_change >= 0 else Fore.RED
                print(f"Account Balance: ${self.state.account_balance:.2f} "
                      f"({balance_color}{balance_change:+.2f}{Style.RESET_ALL} total)")

                daily_change = self.state.account_balance - self.state.daily_start_balance
                daily_color = Fore.GREEN if daily_change >= 0 else Fore.RED
                print(f"Daily PnL: {daily_color}{daily_change:+.2f}{Style.RESET_ALL}")

    def _display_performance(self):
        print(Style.BRIGHT + "\n📊 PERFORMANCE METRICS" + Style.RESET_ALL)
        print("-" * 40)

        metrics = self.state.metrics

        # Win rate and trades
        if metrics.total_trades > 0:
            wr_color = (Fore.GREEN if metrics.win_rate >= Decimal('0.5') else
                       Fore.YELLOW if metrics.win_rate >= Decimal('0.4') else Fore.RED)
            print(f"Win Rate: {wr_color}{metrics.win_rate:.1%}{Style.RESET_ALL} "
                  f"({metrics.winning_trades}W/{metrics.losing_trades}L)")
        else:
            print("No trades yet.")
            return

        # Overall PnL
        total_color = Fore.GREEN if metrics.total_pnl > 0 else Fore.RED if metrics.total_pnl < 0 else Fore.WHITE
        print(f"Total PnL: {total_color}${metrics.total_pnl:.2f}{Style.RESET_ALL} (Fees: ${metrics.total_fees:.2f})")

        # Key ratios
        if metrics.profit_factor != Decimal('0'):
            pf_color = Fore.GREEN if metrics.profit_factor > Decimal('1.5') else Fore.YELLOW if metrics.profit_factor > Decimal('1') else Fore.RED
            print(f"Profit Factor: {pf_color}{metrics.profit_factor:.2f}{Style.RESET_ALL}")

        sharpe = metrics.calculate_sharpe_ratio()
        if sharpe != Decimal('0'):
            sharpe_color = Fore.GREEN if sharpe > Decimal('1') else Fore.YELLOW if sharpe > Decimal('0') else Fore.RED
            print(f"Sharpe Ratio (Annualized): {sharpe_color}{sharpe:.2f}{Style.RESET_ALL}")

        # Drawdown
        if metrics.max_drawdown != Decimal('0'):
            dd_color = Fore.YELLOW if metrics.max_drawdown < Decimal('5') else Fore.RED
            print(f"Max Drawdown: {dd_color}{metrics.max_drawdown:.1f}%{Style.RESET_ALL}")

        # Streaks
        if metrics.consecutive_wins > 0:
            print(f"Streak: {Fore.GREEN}↑{metrics.consecutive_wins} wins{Style.RESET_ALL} (Max: {metrics.max_consecutive_wins})")
        elif metrics.consecutive_losses > 0:
            print(f"Streak: {Fore.RED}↓{metrics.consecutive_losses} losses{Style.RESET_ALL} (Max: {metrics.max_consecutive_losses})")

        # Best/Worst trades
        if metrics.best_trade_pct != Decimal('0') or metrics.worst_trade_pct != Decimal('0'):
            print(f"Best/Worst: {Fore.GREEN}+{metrics.best_trade_pct:.1f}%{Style.RESET_ALL} / "
                  f"{Fore.RED}{metrics.worst_trade_pct:.1f}%{Style.RESET_ALL}")

        # Avg Win/Loss
        if metrics.avg_win_pct != Decimal('0') or metrics.avg_loss_pct != Decimal('0'):
            print(f"Avg Win/Loss: {Fore.GREEN}+{metrics.avg_win_pct:.1f}%{Style.RESET_ALL} / "
                  f"{Fore.RED}{metrics.avg_loss_pct:.1f}%{Style.RESET_ALL}")

        if self.config.USE_KELLY_SIZING and metrics.total_trades > 10: # Only show if enough data
            kelly_f = metrics.calculate_kelly_fraction(self.config.KELLY_FRACTION_CAP)
            kelly_color = Fore.GREEN if kelly_f > 0 else Fore.YELLOW
            print(f"Kelly Fraction: {kelly_color}{kelly_f:.2%}{Style.RESET_ALL}")

    def _display_logs(self):
        print(Style.BRIGHT + "\n📝 RECENT ACTIVITY" + Style.RESET_ALL)
        print("-" * 40)

        for msg in list(self.state.log_messages):
            # Color code based on message content
            if "[ERROR]" in msg:
                print(Fore.RED + msg + Style.RESET_ALL)
            elif "[WARNING]" in msg:
                print(Fore.YELLOW + msg + Style.RESET_ALL)
            elif "[SUCCESS]" in msg or "profit" in msg.lower() or "filled" in msg.lower():
                print(Fore.GREEN + msg + Style.RESET_ALL)
            else:
                print(msg)

    def _display_footer(self):
        print(Style.BRIGHT + Fore.CYAN + "\n" + "=" * 80 + Style.RESET_ALL)

        # Running time
        uptime = datetime.now(timezone.utc) - self.state.start_time
        hours = uptime.total_seconds() // 3600
        minutes = (uptime.total_seconds() % 3600) // 60
        print(f"Uptime: {hours:.0f}h {minutes:.0f}m | ", end="")

        # Error count
        if self.state.errors_count > 0:
            print(f"{Fore.YELLOW}Errors: {self.state.errors_count}{Style.RESET_ALL} | ", end="")

        print(Fore.YELLOW + "Press Ctrl+C to exit gracefully" + Style.RESET_ALL)

# =====================================================================
# LOGGING SETUP
# =====================================================================

def setup_logger(config: EnhancedConfig) -> logging.Logger:
    """Configures a logger with both console and file handlers."""
    logger = logging.getLogger('SuperTrendBot')
    logger.setLevel(config.LOG_LEVEL.upper())

    # Clear existing handlers to prevent duplicate logs on reload
    if logger.hasHandlers():
        logger.handlers.clear()

    # Console Handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File Handler
    file_handler = logging.handlers.RotatingFileHandler(
        'bot_activity.log', maxBytes=10*1024*1024, backupCount=5
    )
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger

# =====================================================================
# MARKET ANALYSIS
# =====================================================================

class MarketAnalyzer:
    """Advanced market analysis and regime detection."""

    def __init__(self, config: EnhancedConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.regime_window = 50 # Number of candles for regime detection
        self.volatility_window = 20 # Number of candles for volatility

    def analyze_market_regime(self, df: pd.DataFrame) -> MarketRegime:
        """Determine current market regime using multiple factors."""
        if len(df) < self.regime_window:
            return MarketRegime.UNKNOWN

        # Ensure numeric types
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)

        if len(df) < self.regime_window: # Recheck after dropna
            return MarketRegime.UNKNOWN

        close_prices = df['close'].values[-self.regime_window:]

        # 1. Trend strength using linear regression (simplified without scipy)
        x = np.arange(len(close_prices))
        slope, intercept = np.polyfit(x, close_prices.astype(float), 1)
        # A simple threshold for slope can indicate trend strength
        trend_strength_threshold = 0.01 # Adjust as needed

        # 2. Volatility using ATR
        if 'atr' not in df.columns or df['atr'].iloc[-1] == 0:
            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
            df.dropna(subset=['atr'], inplace=True)
            if df['atr'].empty: return MarketRegime.UNKNOWN

        atr = df['atr'].iloc[-1]
        atr_pct = (atr / df['close'].iloc[-1]) * Decimal('100') if df['close'].iloc[-1] > 0 else Decimal('0')

        # 3. Price position relative to moving averages (EMA 20 & 50)
        # Assuming EMA 20 and 50 are already calculated or can be calculated here
        if 'ema_20' not in df.columns: df['ema_20'] = ta.ema(df['close'], length=20)
        if 'ema_50' not in df.columns: df['ema_50'] = ta.ema(df['close'], length=50)
        df.dropna(subset=['ema_20', 'ema_50'], inplace=True)
        if df['ema_20'].empty: return MarketRegime.UNKNOWN

        ema_20 = df['ema_20'].iloc[-1]
        ema_50 = df['ema_50'].iloc[-1]
        price = df['close'].iloc[-1]

        # Determine regime
        if atr_pct > Decimal('3.0'): # High volatility
            return MarketRegime.VOLATILE
        elif atr_pct < Decimal('0.5'): # Low volatility
            return MarketRegime.CALM
        elif abs(slope) > trend_strength_threshold: # Strong trend based on slope
            if slope > 0 and price > ema_20 and ema_20 > ema_50:
                return MarketRegime.TRENDING_UP
            elif slope < 0 and price < ema_20 and ema_20 < ema_50:
                return MarketRegime.TRENDING_DOWN

        # If not strongly trending or very volatile/calm, it's ranging
        return MarketRegime.RANGING

    def calculate_support_resistance(self, df: pd.DataFrame, window: int = 20) -> dict[str, Decimal]:
        """Calculate dynamic support and resistance levels using Pivot Points and historical highs/lows."""
        if len(df) < window:
            return {}

        # Ensure numeric types
        for col in ['high', 'low', 'close']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < window: return {}

        # Rolling highs and lows
        recent_high = df['high'].iloc[-window:].max()
        recent_low = df['low'].iloc[-window:].min()

        # Classic Pivot Points
        last_high = df['high'].iloc[-1]
        last_low = df['low'].iloc[-1]
        last_close = df['close'].iloc[-1]

        pivot = (last_high + last_low + last_close) / 3

        return {
            'resistance_recent': Decimal(str(recent_high)),
            'support_recent': Decimal(str(recent_low)),
            'pivot': Decimal(str(pivot)),
            'r1': Decimal(str(2 * pivot - last_low)),
            's1': Decimal(str(2 * pivot - last_high))
        }

    def analyze_volume_profile(self, df: pd.DataFrame, bins: int = 10) -> dict[str, Any]:
        """Analyze volume distribution across price levels (simplified for candle data)."""
        if len(df) < bins:
            return {}

        # Ensure numeric types
        for col in ['close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < bins: return {}

        # Calculate VWAP
        vwap = (df['close'] * df['volume']).sum() / df['volume'].sum() if df['volume'].sum() > 0 else df['close'].iloc[-1]

        # Create price bins and sum volume
        min_price = df['close'].min()
        max_price = df['close'].max()

        if max_price == min_price: # Handle flat market
            return {
                'poc': Decimal(str(min_price)),
                'vwap': Decimal(str(vwap)),
                'volume_profile': {f"{min_price:.2f}-{max_price:.2f}": df['volume'].sum()}
            }

        bin_edges = np.linspace(min_price, max_price, bins + 1)
        volume_bins = defaultdict(Decimal)

        for _, row in df.iterrows():
            price = row['close']
            volume = Decimal(str(row['volume']))

            # Find which bin the price falls into
            for i in range(bins):
                if bin_edges[i] <= price < bin_edges[i+1]:
                    volume_bins[f"{bin_edges[i]:.2f}-{bin_edges[i+1]:.2f}"] += volume
                    break
            # Edge case for max price
            if price == max_price:
                volume_bins[f"{bin_edges[bins-1]:.2f}-{bin_edges[bins]:.2f}"] += volume

        # Find POC (Point of Control - price level with highest volume)
        poc_range_str = max(volume_bins, key=volume_bins.get) if volume_bins else None

        poc_price = Decimal('0')
        if poc_range_str:
            lower, upper = map(Decimal, poc_range_str.split('-'))
            poc_price = (lower + upper) / 2

        return {
            'volume_profile': volume_bins,
            'poc': poc_price,
            'vwap': Decimal(str(vwap))
        }

    def analyze_order_book_imbalance(self, bids: list[dict], asks: list[dict], depth: int) -> Decimal:
        """Calculates order book imbalance for a given depth."""
        if not bids or not asks:
            return Decimal('0')

        bid_volume = sum(Decimal(b['size']) for b in bids[:depth])
        ask_volume = sum(Decimal(a['size']) for a in asks[:depth])

        total_volume = bid_volume + ask_volume
        if total_volume == Decimal('0'):
            return Decimal('0')

        imbalance = (bid_volume - ask_volume) / total_volume
        return imbalance

# =====================================================================
# TECHNICAL INDICATORS
# =====================================================================

class IndicatorCalculator:
    """Advanced technical indicator calculations."""

    def __init__(self, config: EnhancedConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger

    def calculate_ehlers_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates the Ehlers Filter (a low-lag, adaptive moving average)."""
        if len(df) < 2:
            df['ehlers_filter'] = df['close'] # Or NaN if preferred
            return df

        # Ensure numeric types
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df.dropna(subset=['close'], inplace=True)
        if df.empty: return df

        # Constants for a 10-period Ehlers Filter (approx 10-bar cycle)
        # These are derived from Ehlers' calculations for a 10-period adaptive filter
        # The original code used a fixed a1, b1, c1, c2, c3. This is a common interpretation.
        # For a truly adaptive Ehlers filter, the alpha/beta values would change based on dominant cycle.
        # For simplicity and consistency with the original script's spirit, we keep it a fixed-parameter filter here.
        # If a truly adaptive one is needed, it would involve calculating dominant cycle period first.

        # These coefficients are from a specific Ehlers filter implementation, not directly from his original "Supertrend"
        # which uses a different filter (e.g., adaptive moving average or Hilbert Transform)
        # Assuming these are for a 10-period "Ehlers filter" as implied by the original code.
        a1 = np.exp(-np.pi * np.sqrt(2) / 10)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / 10)
        c2, c3 = b1, -a1 * a1
        c1 = 1 - b1 + a1 * a1

        filt = np.zeros(len(df.close))

        # Handle initial values
        if len(df.close) > 0:
            filt[0] = df.close.iloc[0]
        if len(df.close) > 1:
            filt[1] = (c1 * (df.close.iloc[1] + df.close.iloc[0]) / 2.0) + (c2 * filt[0])

        # Apply filter for subsequent values
        for i in range(2, len(df.close)):
            filt[i] = c1 * (df.close.iloc[i] + df.close.iloc[i-1]) / 2.0 + c2 * filt[i-1] + c3 * filt[i-2]

        df['ehlers_filter'] = filt
        return df

    def calculate_adaptive_supertrend(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate SuperTrend with adaptive parameters based on volatility."""
        if df.empty:
            return df

        # Ensure numeric types
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if df.empty: return df

        # Calculate volatility using ATR as a proxy
        if 'atr' not in df.columns or df['atr'].isnull().all():
            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
            df.dropna(subset=['atr'], inplace=True)
            if df.empty: return df

        # Percentage ATR to normalize volatility
        atr_pct = (df['atr'].iloc[-1] / df['close'].iloc[-1]) * 100 if df['close'].iloc[-1] > 0 else 0

        period = self.config.ST_PERIOD_BASE
        multiplier = float(self.config.ST_MULTIPLIER_BASE)

        if self.config.ADAPTIVE_PARAMS:
            if atr_pct < 0.5: # Very low volatility (calm market)
                period = min(self.config.ST_PERIOD_BASE + 5, 20) # Increase period, reduce sensitivity
                multiplier = max(float(self.config.ST_MULTIPLIER_BASE) - 0.5, 1.5)
                self.logger.debug(f"Adaptive ST: Low volatility. Period={period}, Multiplier={multiplier:.1f}")
            elif atr_pct > 2.0: # High volatility (volatile market)
                period = max(self.config.ST_PERIOD_BASE - 3, 7) # Decrease period, increase sensitivity
                multiplier = min(float(self.config.ST_MULTIPLIER_BASE) + 0.5, 4.0)
                self.logger.debug(f"Adaptive ST: High volatility. Period={period}, Multiplier={multiplier:.1f}")
            else:
                self.logger.debug(f"Adaptive ST: Moderate volatility. Period={period}, Multiplier={multiplier:.1f}")

        # Calculate SuperTrend using pandas_ta
        # Note: pandas_ta appends columns with names like SUPERT_LENGTH_MULTIPLIER
        df.ta.supertrend(length=period, multiplier=multiplier, append=True)

        # Rename columns for consistency
        st_col = f'SUPERT_{period}_{multiplier:.1f}' # .1f for multiplier as it's a float
        st_dir_col = f'SUPERTd_{period}_{multiplier:.1f}'

        if st_col in df.columns:
            df['supertrend_line'] = df[st_col]
            df['supertrend_direction'] = df[st_dir_col]
            # Drop the original pandas_ta generated columns
            df.drop([st_col, st_dir_col], axis=1, inplace=True, errors='ignore')
        else:
            self.logger.warning(f"SuperTrend columns {st_col}, {st_dir_col} not found in DataFrame.")
            df['supertrend_line'] = np.nan
            df['supertrend_direction'] = np.nan

        return df

    def calculate_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate comprehensive set of technical indicators."""
        if df.empty:
            return df

        # Ensure we have float data for calculations
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if df.empty: return df

        # Ehlers Filter (custom implementation)
        df = self.calculate_ehlers_filter(df)

        # Trend Indicators
        df = self.calculate_adaptive_supertrend(df) # Includes ATR for adaptive logic
        df['ema_9'] = ta.ema(df['close'], length=9)
        df['ema_20'] = ta.ema(df['close'], length=20)
        df['ema_50'] = ta.ema(df['close'], length=50)
        df['sma_200'] = ta.sma(df['close'], length=200)

        # Momentum Indicators
        df['rsi'] = ta.rsi(df['close'], length=self.config.RSI_WINDOW)
        macd = ta.macd(df['close'], fast=self.config.MACD_FAST, slow=self.config.MACD_SLOW, signal=self.config.MACD_SIGNAL)
        if macd is not None and not macd.empty:
            df['macd'] = macd[f'MACD_{self.config.MACD_FAST}_{self.config.MACD_SLOW}_{self.config.MACD_SIGNAL}']
            df['macd_signal'] = macd[f'MACDs_{self.config.MACD_FAST}_{self.config.MACD_SLOW}_{self.config.MACD_SIGNAL}']
            df['macd_hist'] = macd[f'MACDh_{self.config.MACD_FAST}_{self.config.MACD_SLOW}_{self.config.MACD_SIGNAL}']
        else:
            df['macd'] = np.nan
            df['macd_signal'] = np.nan
            df['macd_hist'] = np.nan

        # Stochastic
        stoch = ta.stoch(df['high'], df['low'], df['close'])
        if stoch is not None and not stoch.empty:
            df['stoch_k'] = stoch['STOCHk_14_3_3']
            df['stoch_d'] = stoch['STOCHd_14_3_3']
        else:
            df['stoch_k'] = np.nan
            df['stoch_d'] = np.nan

        # Volatility Indicators (ATR already calculated in adaptive supertrend, BBANDS still useful)
        bb = ta.bbands(df['close'])
        if bb is not None and not bb.empty:
            df['bb_upper'] = bb['BBU_20_2.0']
            df['bb_middle'] = bb['BBM_20_2.0']
            df['bb_lower'] = bb['BBL_20_2.0']
            df['bb_width'] = df['bb_upper'] - df['bb_lower']
            df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        else:
            df['bb_upper'] = np.nan
            df['bb_middle'] = np.nan
            df['bb_lower'] = np.nan
            df['bb_width'] = np.nan
            df['bb_position'] = np.nan

        # Volume Indicators
        df['volume_sma'] = ta.sma(df['volume'], length=20)
        df['volume_ratio'] = df['volume'] / df['volume_sma'] if df['volume_sma'].iloc[-1] > 0 else 0
        df['obv'] = ta.obv(df['close'], df['volume'])

        # Trend Strength
        adx = ta.adx(df['high'], df['low'], df['close'], length=self.config.ADX_WINDOW)
        if adx is not None and not adx.empty:
            df['adx'] = adx[f'ADX_{self.config.ADX_WINDOW}']
            df['dmp'] = adx[f'DMP_{self.config.ADX_WINDOW}']
            df['dmn'] = adx[f'DMN_{self.config.ADX_WINDOW}']
        else:
            df['adx'] = np.nan
            df['dmp'] = np.nan
            df['dmn'] = np.nan

        # Custom calculations
        df['hl2'] = (df['high'] + df['low']) / 2
        df['hlc3'] = (df['high'] + df['low'] + df['close']) / 3
        df['ohlc4'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4

        # Price action
        df['body'] = abs(df['close'] - df['open'])
        df['upper_wick'] = df['high'] - df[['close', 'open']].max(axis=1)
        df['lower_wick'] = df[['close', 'open']].min(axis=1) - df['low']

        return df.dropna().reset_index(drop=True) # Drop any remaining NaNs from indicator calculations

# =====================================================================
# PRECISION & ORDER SIZING
# =====================================================================

@dataclass
class InstrumentSpecs:
    """Stores instrument specifications from Bybit."""
    tick_size: Decimal
    qty_step: Decimal
    min_order_qty: Decimal
    max_order_qty: Decimal
    min_order_value: Decimal # For SPOT, min quote order qty

class PrecisionManager:
    """Manages decimal precision for trading pairs."""
    def __init__(self, session: HTTP, logger: logging.Logger):
        self.session = session
        self.logger = logger
        self.instruments: dict[str, InstrumentSpecs] = {}

    def get_specs(self, symbol: str, category: str) -> InstrumentSpecs | None:
        if symbol in self.instruments:
            return self.instruments[symbol]
        try:
            response = self.session.get_instruments_info(category=category, symbol=symbol)
            if response['retCode'] == 0:
                info = response['result']['list'][0]

                # Default values
                min_order_value = Decimal('0')
                max_order_qty = Decimal('999999999') # Effectively unlimited

                if category == "spot":
                    # Spot uses baseCoin and quoteCoin, and minNotional
                    min_order_qty = Decimal(info['lotSizeFilter']['baseMinTradeQty'])
                    qty_step = Decimal(info['lotSizeFilter']['baseTickSize'])
                    tick_size = Decimal(info['priceFilter']['tickSize'])
                    min_order_value = Decimal(info['lotSizeFilter']['minNotional'])
                    max_order_qty = Decimal(info['lotSizeFilter']['baseMaxTradeQty'])
                else: # Linear/Inverse
                    min_order_qty = Decimal(info['lotSizeFilter']['minOrderQty'])
                    qty_step = Decimal(info['lotSizeFilter']['qtyStep'])
                    tick_size = Decimal(info['priceFilter']['tickSize'])
                    max_order_qty = Decimal(info['lotSizeFilter']['maxOrderQty'])

                specs = InstrumentSpecs(
                    tick_size=tick_size,
                    qty_step=qty_step,
                    min_order_qty=min_order_qty,
                    max_order_qty=max_order_qty,
                    min_order_value=min_order_value
                )
                self.instruments[symbol] = specs
                self.logger.info(f"Fetched instrument specs for {symbol}: {specs}")
                return specs
            else:
                self.logger.error(f"Failed to get instrument info for {symbol}: {response['retMsg']}")
        except Exception as e:
            self.logger.error(f"Error fetching instrument specs for {symbol}: {e}")
        return None

    def round_price(self, specs: InstrumentSpecs, price: Decimal) -> Decimal:
        return (price / specs.tick_size).quantize(Decimal('1'), rounding=ROUND_DOWN) * specs.tick_size

    def round_quantity(self, specs: InstrumentSpecs, quantity: Decimal) -> Decimal:
        return (quantity / specs.qty_step).quantize(Decimal('1'), rounding=ROUND_DOWN) * specs.qty_step

class OrderSizingCalculator:
    """Calculates order sizes based on risk management."""
    def __init__(self, precision_manager: PrecisionManager, logger: logging.Logger, config: EnhancedConfig):
        self.precision = precision_manager
        self.logger = logger
        self.config = config

    def calculate_position_size(self, specs: InstrumentSpecs, balance: Decimal, entry: Decimal, sl: Decimal, leverage: Decimal, metrics: PerformanceMetrics) -> Decimal | None:
        if balance <= 0 or entry <= 0 or leverage <= 0:
            self.logger.warning("Invalid inputs for position sizing: balance, entry, leverage must be positive.")
            return None

        if self.config.USE_KELLY_SIZING and metrics.total_trades >= 10: # Need enough data for Kelly
            kelly_fraction = metrics.calculate_kelly_fraction(self.config.KELLY_FRACTION_CAP)
            if kelly_fraction > 0:
                # Kelly gives fraction of total bankroll to wager
                # For leveraged trading, Kelly fraction * leverage = position size as % of equity
                # Or, simpler: Kelly fraction is applied directly to equity for position value
                position_value_usd = balance * kelly_fraction
                self.logger.info(f"Using Kelly Criterion: Kelly Fraction={kelly_fraction:.2%}, Position Value=${position_value_usd:,.2f}")
            else:
                self.logger.warning("Kelly Criterion suggested no position or negative fraction. Falling back to fixed risk.")
                return self._calculate_fixed_risk_size(specs, balance, entry, sl, leverage)
        else:
            return self._calculate_fixed_risk_size(specs, balance, entry, sl, leverage)

        # Apply max position size limit
        max_position_value = balance * (self.config.MAX_POSITION_SIZE_PCT / Decimal('100'))
        position_value_usd = min(position_value_usd, max_position_value)

        if position_value_usd <= 0:
            self.logger.warning("Calculated position value is zero or negative.")
            return None

        qty = position_value_usd / entry

        # Apply min/max order quantity and min notional value
        qty = self.precision.round_quantity(specs, qty)

        if qty < specs.min_order_qty:
            self.logger.warning(f"Calculated quantity {qty} is less than min order qty {specs.min_order_qty}. Adjusting to min order qty.")
            qty = specs.min_order_qty

        if qty > specs.max_order_qty:
            self.logger.warning(f"Calculated quantity {qty} exceeds max order qty {specs.max_order_qty}. Adjusting to max order qty.")
            qty = specs.max_order_qty

        if self.config.CATEGORY_ENUM == "spot" and (qty * entry) < specs.min_order_value:
            self.logger.warning(f"Calculated order value {qty * entry} is less than min notional {specs.min_order_value}. No trade.")
            return None

        return qty

    def _calculate_fixed_risk_size(self, specs: InstrumentSpecs, balance: Decimal, entry: Decimal, sl: Decimal, leverage: Decimal) -> Decimal | None:
        if abs(entry - sl) == 0:
            self.logger.warning("Stop loss is at entry price, cannot calculate risk-based size.")
            return None

        risk_amount = balance * (self.config.RISK_PER_TRADE_PCT / Decimal('100'))

        # Calculate PnL per unit if SL is hit
        loss_per_unit = abs(entry - sl)

        # Max quantity based on risk_amount
        qty_from_risk = risk_amount / loss_per_unit

        # Max quantity based on leverage and max position size %
        max_equity_for_pos = balance * (self.config.MAX_POSITION_SIZE_PCT / Decimal('100'))
        max_position_value_by_leverage = max_equity_for_pos * leverage
        qty_from_leverage = max_position_value_by_leverage / entry

        # Take the minimum of the two calculated quantities
        final_qty = min(qty_from_risk, qty_from_leverage)

        # Apply min/max order quantity and min notional value
        final_qty = self.precision.round_quantity(specs, final_qty)

        if final_qty < specs.min_order_qty:
            self.logger.warning(f"Calculated quantity {final_qty} is less than min order qty {specs.min_order_qty}. Adjusting to min order qty.")
            final_qty = specs.min_order_qty

        if final_qty > specs.max_order_qty:
            self.logger.warning(f"Calculated quantity {final_qty} exceeds max order qty {specs.max_order_qty}. Adjusting to max order qty.")
            final_qty = specs.max_order_qty

        if self.config.CATEGORY_ENUM == "spot" and (final_qty * entry) < specs.min_order_value:
            self.logger.warning(f"Calculated order value {final_qty * entry} is less than min notional {specs.min_order_value}. No trade.")
            return None

        return final_qty

# =====================================================================
# MAIN TRADING BOT CLASS
# =====================================================================

class AdvancedSupertrendBot:
    """The main class for the Enhanced Supertrend trading bot."""
    def __init__(self, config: EnhancedConfig):
        self.config = config
        self.logger = setup_logger(config)
        self.bot_state = BotState(symbol=config.SYMBOL)
        self.stop_event = threading.Event()
        self.ws_reconnect_event = threading.Event()

        self.session = HTTP(testnet=config.TESTNET, api_key=config.API_KEY, api_secret=config.API_SECRET)
        self.precision_manager = PrecisionManager(self.session, self.logger)
        self.order_sizer = OrderSizingCalculator(self.precision_manager, self.logger, config)
        self.market_analyzer = MarketAnalyzer(self.config, self.logger)
        self.indicator_calculator = IndicatorCalculator(self.config, self.logger)

        self.ws_public = None
        self.ws_private = None
        self.klines_dfs: dict[str, pd.DataFrame] = {} # {timeframe: DataFrame}
        self.order_book_data: dict[str, Any] = {'bids': [], 'asks': []} # Real-time order book
        self.last_kline_timestamp: dict[str, datetime] = {} # To track last processed kline for each TF

        # State persistence thread
        self.state_saver_thread = threading.Thread(target=self._state_saver_loop, daemon=True)

    def _api_call(self, api_method: Callable, **kwargs) -> dict[str, Any] | None:
        """A resilient wrapper for API calls with exponential backoff."""
        for attempt in range(5):
            try:
                response = api_method(**kwargs)
                if response['retCode'] == 0:
                    return response['result']
                else:
                    error_msg = response.get('retMsg', 'Unknown error')
                    self.logger.error(f"API Error ({response['retCode']}): {error_msg} (Attempt {attempt+1}/5)")
                    self.bot_state.update(errors_count=self.bot_state.errors_count + 1, last_error=error_msg)
            except InvalidRequestError as e:
                self.logger.error(f"Invalid API Request: {e}. Not retrying.")
                self.bot_state.update(errors_count=self.bot_state.errors_count + 1, last_error=str(e))
                return None # Don't retry on bad requests
            except FailedRequestError as e:
                self.logger.error(f"Bybit Request Error: {e} (Attempt {attempt+1}/5)")
                self.bot_state.update(errors_count=self.bot_state.errors_count + 1, last_error=str(e))
            except Exception as e:
                self.logger.error(f"General API Exception: {e} (Attempt {attempt+1}/5)")
                self.bot_state.update(errors_count=self.bot_state.errors_count + 1, last_error=str(e))

            time.sleep(min(2 ** attempt, 60)) # Exponential backoff, max 60 seconds
        self.logger.critical(f"API call failed after multiple retries: {api_method.__name__} with kwargs {kwargs}")
        return None

    def run(self):
        """Starts the bot and all its components."""
        self.bot_state.add_log("🚀 Starting Advanced Supertrend Bot...", "INFO")
        self._install_signal_handlers()

        # Load previous state if available
        if self.bot_state.load_state(self.config.STATE_FILE):
            self.bot_state.add_log("Loaded previous bot state.", "INFO")
        else:
            self.bot_state.add_log("No previous state found or failed to load. Starting fresh.", "INFO")

        # Initial setup and data fetching
        current_balance = self._get_account_balance()
        if current_balance == Decimal('0'):
            self.bot_state.add_log("Could not retrieve initial account balance. Exiting.", "ERROR")
            self.logger.critical("Could not retrieve initial account balance. Shutting down.")
            return

        with self.bot_state.lock:
            self.bot_state.account_balance = current_balance
            if self.bot_state.initial_balance == Decimal('0'): # Set initial balance only once
                self.bot_state.initial_balance = current_balance

            # Reset daily balance if a new day has started
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if not self.bot_state.daily_pnl.get(today_str): # If today's PnL hasn't been initialized
                 self.bot_state.daily_start_balance = current_balance
            else:
                 # If PnL exists for today, it means we're resuming, so daily_start_balance should reflect
                 # the balance at the beginning of the day the bot started/restarted, not necessarily current.
                 # For simplicity, if we loaded state for current day, assume daily_start_balance was set correctly.
                 pass # No change if already set for the current day.

        # Fetch initial kline data for all timeframes
        all_timeframes = [self.config.PRIMARY_TIMEFRAME] + self.config.SECONDARY_TIMEFRAMES
        for tf in sorted(list(set(all_timeframes))): # Use set to avoid duplicates
            if not self._fetch_initial_klines(tf):
                self.bot_state.add_log(f"Failed to fetch initial kline data for {tf}. Shutting down.", "ERROR")
                self.logger.critical(f"Failed to fetch initial kline data for {tf}. Shutting down.")
                return

        self._set_leverage_and_margin()

        # Start UI and WebSocket threads
        self.ui = EnhancedUI(self.bot_state, self.config)
        self.ui.start()
        self.state_saver_thread.start()

        threading.Thread(target=self._websocket_manager, daemon=True, name="WebSocketManager").start()

        self.bot_state.add_log("Bot is now running. Press Ctrl+C to stop.", "INFO")
        self.stop_event.wait() # Main thread waits here until a stop signal is received

        self.cleanup()

    def _websocket_manager(self):
        """Manages WebSocket connections and reconnections."""
        while not self.stop_event.is_set():
            try:
                self._connect_websockets()
                self.ws_reconnect_event.clear() # Clear event after successful connection
                # Keep the thread alive while websockets are active
                while not self.stop_event.is_set() and not self.ws_reconnect_event.is_set():
                    time.sleep(1) # Sleep to prevent busy-waiting
            except Exception as e:
                self.bot_state.add_log(f"WebSocket connection error: {e}. Reconnecting in 5s...", "ERROR")
                self.logger.error(f"WebSocket connection error: {e}. Reconnecting in 5s...")
                self.ws_reconnect_event.set() # Set event to signal reconnection needed
                time.sleep(5) # Wait before attempting to reconnect
            finally:
                self._close_websockets()

    def _connect_websockets(self):
        """Initializes and connects the WebSocket client(s)."""
        self.bot_state.add_log("Connecting to WebSockets...", "INFO")
        self.logger.info("Connecting to WebSockets...")

        # Public WebSocket for Klines, Tickers, Order Book
        self.ws_public = WebSocket(
            testnet=self.config.TESTNET,
            channel_type='spot' if self.config.CATEGORY == 'spot' else 'unified', # unified for linear/inverse
        )
        # Private WebSocket for Positions, Wallet
        self.ws_private = WebSocket(
            testnet=self.config.TESTNET,
            channel_type='spot' if self.config.CATEGORY == 'spot' else 'unified',
            api_key=self.config.API_KEY,
            api_secret=self.config.API_SECRET
        )

        # Subscribe to public streams
        all_timeframes = [self.config.PRIMARY_TIMEFRAME] + self.config.SECONDARY_TIMEFRAMES
        for tf in sorted(list(set(all_timeframes))):
            self.ws_public.kline_stream(tf, self.config.SYMBOL, lambda msg, tf=tf: self._handle_kline_message(msg, tf))
        self.ws_public.tickers_stream(self.config.SYMBOL, self._handle_ticker_message)
        if self.config.USE_ORDER_BOOK:
            self.ws_public.orderbook_stream(self.config.ORDER_BOOK_DEPTH_LEVELS, self.config.SYMBOL, self._handle_orderbook_message)

        # Subscribe to private streams
        self.ws_private.position_stream(self._handle_position_message)
        self.ws_private.wallet_stream(self._handle_wallet_message)

        with self.bot_state.lock:
            self.bot_state.status = "Live"
        self.bot_state.add_log("WebSockets connected and subscribed.", "SUCCESS")
        self.logger.info("WebSockets connected and subscribed.")

    def _close_websockets(self):
        """Closes all active WebSocket connections."""
        self.bot_state.add_log("Closing WebSockets...", "INFO")
        self.logger.info("Closing WebSockets...")
        if self.ws_public:
            self.ws_public.exit()
            self.ws_public = None
        if self.ws_private:
            self.ws_private.exit()
            self.ws_private = None

    # --- WebSocket Handlers ---
    def _handle_kline_message(self, message: dict[str, Any], timeframe: str):
        kline = message['data'][0]
        if kline['confirm']: # Only process confirmed candles
            kline_timestamp = datetime.fromtimestamp(int(kline['start']) / 1000, tz=timezone.utc)

            # Check if this candle has already been processed for this TF
            if timeframe in self.last_kline_timestamp and kline_timestamp <= self.last_kline_timestamp[timeframe]:
                self.logger.debug(f"Skipping duplicate/old confirmed kline for {timeframe} at {kline_timestamp}")
                return

            self.logger.info(f"New confirmed candle received for {timeframe} at {kline_timestamp}")
            self.last_kline_timestamp[timeframe] = kline_timestamp

            self._update_kline_data(kline, timeframe)

            # Only run strategy cycle on primary timeframe's confirmed candle
            if timeframe == self.config.PRIMARY_TIMEFRAME:
                self._run_strategy_cycle()

    def _handle_ticker_message(self, message: dict[str, Any]):
        with self.bot_state.lock:
            old_price = self.bot_state.current_price
            new_price = Decimal(message['data']['lastPrice'])
            self.bot_state.current_price = new_price
            if new_price > old_price:
                self.bot_state.price_direction = 1
            elif new_price < old_price:
                self.bot_state.price_direction = -1
            else:
                self.bot_state.price_direction = 0

    def _handle_position_message(self, message: dict[str, Any]):
        self.logger.info("Position update received.")
        self._update_position_state()

    def _handle_wallet_message(self, message: dict[str, Any]):
        self.logger.info("Wallet update received.")
        with self.bot_state.lock:
            self.bot_state.account_balance = self._get_account_balance()
            # Check if it's a new day for daily balance tracking
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if today_str not in self.bot_state.metrics.daily_pnl:
                self.bot_state.daily_start_balance = self.bot_state.account_balance
                self.bot_state.metrics.daily_pnl[today_str] = Decimal('0')
                self.bot_state.metrics.daily_trades[today_str] = 0
                self.bot_state.add_log("New trading day started. Resetting daily balance.", "INFO")

    def _handle_orderbook_message(self, message: dict[str, Any]):
        with self.bot_state.lock:
            self.order_book_data['bids'] = message['data']['b']
            self.order_book_data['asks'] = message['data']['a']
            # Update market data with imbalance for primary TF
            if self.config.PRIMARY_TIMEFRAME in self.bot_state.market_data:
                imbalance = self.market_analyzer.analyze_order_book_imbalance(
                    self.order_book_data['bids'], self.order_book_data['asks'], self.config.ORDER_BOOK_DEPTH_LEVELS
                )
                self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].order_book_imbalance = imbalance

                # Also update bid/ask prices
                if self.order_book_data['bids']:
                    self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].bid = Decimal(self.order_book_data['bids'][0][0])
                if self.order_book_data['asks']:
                    self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].ask = Decimal(self.order_book_data['asks'][0][0])

                if self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].bid > 0 and self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].ask > 0:
                    spread = self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].ask - self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].bid
                    self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].spread_pct = (spread / self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].ask) * Decimal('100')

    # --- Core Bot Logic ---
    def _run_strategy_cycle(self):
        """The main logic cycle that runs on each new primary timeframe candle."""
        with self.bot_state.lock:
            self.bot_state.status = "Analyzing..."

        self.logger.info("Running strategy cycle...")

        # 1. Update all indicators for all timeframes
        self._calculate_all_timeframe_indicators()

        # 2. Analyze market conditions (regime, S/R, volume profile)
        self._analyze_market_conditions()

        # 3. Update position state from API
        self._update_position_state()

        # 4. Strategy execution
        if self.bot_state.position:
            self._manage_active_position()
        else:
            self._check_for_entry_signal()

        with self.bot_state.lock:
            self.bot_state.status = "Live"
        self.logger.info("Strategy cycle completed.")

    def _check_daily_limits(self) -> bool:
        """Checks if daily loss or trade limits have been exceeded."""
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_pnl = self.bot_state.account_balance - self.bot_state.daily_start_balance
        daily_trades = self.bot_state.metrics.daily_trades.get(today_str, 0)

        # Check max daily loss
        if daily_pnl < (-self.config.MAX_DAILY_LOSS_PCT / Decimal('100')) * self.bot_state.daily_start_balance:
            self.bot_state.add_log(f"Daily loss limit ({self.config.MAX_DAILY_LOSS_PCT:.1f}%) exceeded. Stopping new trades.", "WARNING")
            self.logger.warning("Daily loss limit exceeded. Stopping new trades.")
            return False

        # Check max daily trades
        if daily_trades >= self.config.MAX_DAILY_TRADES:
            self.bot_state.add_log(f"Daily trade limit ({self.config.MAX_DAILY_TRADES}) exceeded. Stopping new trades.", "WARNING")
            self.logger.warning("Daily trade limit exceeded. Stopping new trades.")
            return False

        # Check max consecutive losses
        if self.bot_state.metrics.consecutive_losses >= self.config.MAX_CONSECUTIVE_LOSSES:
            self.bot_state.add_log(f"Max consecutive losses ({self.config.MAX_CONSECUTIVE_LOSSES}) reached. Stopping new trades.", "WARNING")
            self.logger.warning("Max consecutive losses reached. Stopping new trades.")
            return False

        # Check max drawdown
        if self.bot_state.metrics.current_drawdown >= self.config.MAX_DRAWDOWN_PCT:
            self.bot_state.add_log(f"Max drawdown limit ({self.config.MAX_DRAWDOWN_PCT:.1f}%) reached. Stopping new trades.", "WARNING")
            self.logger.warning("Max drawdown limit reached. Stopping new trades.")
            return False

        return True

    def _check_for_entry_signal(self):
        """Generates a signal and places a trade if conditions are met."""
        if not self._check_daily_limits():
            self.bot_state.add_log("Daily trading limits hit. No new trades.", "WARNING")
            return

        signal, reason, strength = self._generate_signal()
        with self.bot_state.lock:
            self.bot_state.last_signal = signal
            self.bot_state.last_signal_reason = reason
            self.bot_state.signal_strength = strength

        if signal != Signal.NEUTRAL:
            self.bot_state.add_log(f"Signal Generated: {signal.name} (Strength: {strength:.1%}) - Reason: {reason}", "INFO")
            self._execute_trade(signal)

    def _generate_signal(self) -> tuple[Signal, str, Decimal]:
        """
        Generates a trading signal based on the Ehlers Supertrend Cross strategy
        with multi-timeframe confirmation and filters.
        """
        primary_df = self.klines_dfs.get(self.config.PRIMARY_TIMEFRAME)
        if primary_df is None or primary_df.empty or len(primary_df) < max(self.config.ST_PERIOD_BASE, self.config.ADX_WINDOW, self.config.RSI_WINDOW, self.config.MACD_SLOW) + 10:
            return Signal.NEUTRAL, "Insufficient primary timeframe data.", Decimal('0')

        latest_primary = primary_df.iloc[-1]
        prev_primary = primary_df.iloc[-2]

        # Base Ehlers Supertrend Cross Logic (Primary Timeframe)
        ehlers_cross_up = prev_primary['ehlers_filter'] < prev_primary['supertrend_line'] and latest_primary['ehlers_filter'] > latest_primary['supertrend_line']
        ehlers_cross_down = prev_primary['ehlers_filter'] > prev_primary['supertrend_line'] and latest_primary['ehlers_filter'] < latest_primary['supertrend_line']

        st_dir_primary = latest_primary['supertrend_direction']

        base_buy_signal = ehlers_cross_up and st_dir_primary == 1 # Supertrend is already bullish
        base_sell_signal = ehlers_cross_down and st_dir_primary == -1 # Supertrend is already bearish

        signal_strength = Decimal('0')
        reason_parts = []

        # --- Signal Confirmation & Filters ---

        # 1. Multi-timeframe Supertrend Confirmation
        mtf_st_confirmation = True
        for tf in self.config.SECONDARY_TIMEFRAMES:
            df_tf = self.klines_dfs.get(tf)
            if df_tf is None or df_tf.empty or 'supertrend_direction' not in df_tf.columns:
                mtf_st_confirmation = False
                break

            latest_tf = df_tf.iloc[-1]
            if base_buy_signal and latest_tf['supertrend_direction'] != 1:
                mtf_st_confirmation = False
                break
            if base_sell_signal and latest_tf['supertrend_direction'] != -1:
                mtf_st_confirmation = False
                break

        if mtf_st_confirmation:
            signal_strength += Decimal('0.3') # 30% for MTF ST confirmation
            reason_parts.append("MTF ST Confirmed")
        else:
            self.logger.debug("MTF ST not confirmed.")
            # If MTF ST is not confirmed, it's a weaker signal, or no signal at all for strong signals
            # For strict strategy, we might return NEUTRAL here. For a flexible one, we continue.

        # 2. ADX Trend Filter
        adx_ok = False
        if self.config.ADX_TREND_FILTER and 'adx' in latest_primary and latest_primary['adx'] > self.config.ADX_MIN_THRESHOLD:
            adx_ok = True
            signal_strength += Decimal('0.2') # 20% for ADX
            reason_parts.append(f"ADX({latest_primary['adx']:.1f}) > {self.config.ADX_MIN_THRESHOLD}")
        elif self.config.ADX_TREND_FILTER:
            self.logger.debug(f"ADX ({latest_primary.get('adx', 'N/A'):.1f}) below threshold {self.config.ADX_MIN_THRESHOLD}")

        # 3. RSI Filter
        rsi_ok = False
        if self.config.RSI_FILTER and 'rsi' in latest_primary:
            if (base_buy_signal and latest_primary['rsi'] < self.config.RSI_OVERBOUGHT) or (base_sell_signal and latest_primary['rsi'] > self.config.RSI_OVERSOLD): # Not overbought
                rsi_ok = True

        if rsi_ok:
            signal_strength += Decimal('0.15') # 15% for RSI
            reason_parts.append(f"RSI({latest_primary['rsi']:.1f}) OK")
        elif self.config.RSI_FILTER:
            self.logger.debug(f"RSI ({latest_primary.get('rsi', 'N/A'):.1f}) outside range.")

        # 4. MACD Confirmation
        macd_ok = False
        if 'macd_hist' in latest_primary:
            if (base_buy_signal and latest_primary['macd_hist'] > 0) or (base_sell_signal and latest_primary['macd_hist'] < 0): # Bullish momentum
                macd_ok = True

        if macd_ok:
            signal_strength += Decimal('0.15') # 15% for MACD
            reason_parts.append(f"MACD Hist({latest_primary['macd_hist']:.4f}) Confirmed")
        else:
            self.logger.debug(f"MACD Hist ({latest_primary.get('macd_hist', 'N/A'):.4f}) not confirmed.")

        # 5. Volume Filter
        volume_ok = False
        if self.config.VOLUME_FILTER and 'volume_ratio' in latest_primary and latest_primary['volume_ratio'] > self.config.VOLUME_MULTIPLIER:
            volume_ok = True
            signal_strength += Decimal('0.1') # 10% for Volume
            reason_parts.append(f"Volume Ratio({latest_primary['volume_ratio']:.2f}x) > {self.config.VOLUME_MULTIPLIER}")
        elif self.config.VOLUME_FILTER:
            self.logger.debug(f"Volume Ratio ({latest_primary.get('volume_ratio', 'N/A'):.2f}x) below threshold {self.config.VOLUME_MULTIPLIER}")

        # 6. Order Book Imbalance (if enabled)
        order_book_ok = False
        if self.config.USE_ORDER_BOOK:
            imbalance = self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].order_book_imbalance
            if (base_buy_signal and imbalance > self.config.ORDER_BOOK_IMBALANCE_THRESHOLD) or (base_sell_signal and imbalance < -self.config.ORDER_BOOK_IMBALANCE_THRESHOLD):
                order_book_ok = True

        if order_book_ok:
            signal_strength += Decimal('0.1') # 10% for Order Book
            reason_parts.append(f"OB Imbalance({imbalance:.2%}) Confirmed")
        elif self.config.USE_ORDER_BOOK:
            self.logger.debug(f"Order Book Imbalance ({self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].order_book_imbalance:.2%}) not confirmed.")

        final_reason = " | ".join(reason_parts) if reason_parts else "No specific confirmations."

        # Final Signal Decision
        if base_buy_signal and mtf_st_confirmation and adx_ok and rsi_ok and macd_ok and volume_ok and order_book_ok:
            return Signal.STRONG_BUY, "Strong Buy: All confirmations passed.", signal_strength
        elif base_buy_signal and mtf_st_confirmation and adx_ok: # Minimum strong confirmation
            return Signal.BUY, "Buy: Base + MTF ST + ADX confirmed.", signal_strength
        elif base_sell_signal and mtf_st_confirmation and adx_ok and rsi_ok and macd_ok and volume_ok and order_book_ok:
            return Signal.STRONG_SELL, "Strong Sell: All confirmations passed.", signal_strength
        elif base_sell_signal and mtf_st_confirmation and adx_ok: # Minimum strong confirmation
            return Signal.SELL, "Sell: Base + MTF ST + ADX confirmed.", signal_strength

        return Signal.NEUTRAL, "No strong signal or insufficient confirmations.", Decimal('0')

    def _execute_trade(self, signal: Signal):
        """Calculates parameters and places the entry order."""
        specs = self.precision_manager.get_specs(self.config.SYMBOL, self.config.CATEGORY)
        if not specs:
            self.bot_state.add_log("Could not get instrument specs. Cannot place trade.", "ERROR")
            return

        side = "Buy" if signal.value > 0 else "Sell"
        entry_price = self.bot_state.current_price # Use latest ticker price for market orders

        # --- Calculate SL and TP ---
        primary_df = self.klines_dfs.get(self.config.PRIMARY_TIMEFRAME)
        if primary_df.empty or 'atr' not in primary_df.columns or primary_df['atr'].iloc[-1] == 0:
            self.bot_state.add_log("ATR not available or zero for stop/take profit calculation. Using default percentage.", "WARNING")
            atr = Decimal('0')
        else:
            atr = Decimal(str(primary_df['atr'].iloc[-1]))

        if self.config.USE_ATR_STOPS and atr > 0:
            sl_distance = atr * self.config.ATR_STOP_MULTIPLIER
            tp_distance = atr * self.config.ATR_TP_MULTIPLIER
        else:
            sl_distance = entry_price * (self.config.STOP_LOSS_PCT / Decimal('100'))
            tp_distance = entry_price * (self.config.TAKE_PROFIT_PCT / Decimal('100'))

        if side == "Buy":
            sl_price = entry_price - sl_distance
            tp_price = entry_price + tp_distance
        else: # Sell
            sl_price = entry_price + sl_distance
            tp_price = entry_price - tp_distance

        sl_price = self.precision_manager.round_price(specs, sl_price)
        tp_price = self.precision_manager.round_price(specs, tp_price)

        # Ensure SL/TP are valid (not crossing entry)
        if (side == "Buy" and sl_price >= entry_price) or (side == "Sell" and sl_price <= entry_price):
            self.bot_state.add_log(f"Invalid SL price calculated ({sl_price:.4f}) for entry {entry_price:.4f}. Adjusting.", "WARNING")
            sl_price = entry_price * (Decimal('1') - (self.config.STOP_LOSS_PCT / Decimal('100'))) if side == "Buy" else entry_price * (Decimal('1') + (self.config.STOP_LOSS_PCT / Decimal('100')))
            sl_price = self.precision_manager.round_price(specs, sl_price)

        if (side == "Buy" and tp_price <= entry_price) or (side == "Sell" and tp_price >= entry_price):
            self.bot_state.add_log(f"Invalid TP price calculated ({tp_price:.4f}) for entry {entry_price:.4f}. Adjusting.", "WARNING")
            tp_price = entry_price * (Decimal('1') + (self.config.TAKE_PROFIT_PCT / Decimal('100'))) if side == "Buy" else entry_price * (Decimal('1') - (self.config.TAKE_PROFIT_PCT / Decimal('100')))
            tp_price = self.precision_manager.round_price(specs, tp_price)

        # --- Calculate Position Size ---
        qty = self.order_sizer.calculate_position_size(
            specs, self.bot_state.account_balance, entry_price, sl_price, self.config.LEVERAGE, self.bot_state.metrics
        )

        if qty and qty >= specs.min_order_qty:
            self.bot_state.add_log(f"Placing {side} order for {qty:.4f} {self.config.SYMBOL} at ~{entry_price:.4f} with SL {sl_price:.4f} and TP {tp_price:.4f}", "INFO")
            order_id = self._place_order(side, qty, self.config.ORDER_TYPE_ENUM, entry_price, sl_price, tp_price)
            if order_id:
                # Initialize position object immediately, it will be updated by WebSocket later
                with self.bot_state.lock:
                    self.bot_state.position = Position(
                        symbol=self.config.SYMBOL,
                        side=side,
                        size=qty,
                        entry_price=entry_price, # This will be updated to actual avgPrice by WS
                        stop_loss=sl_price,
                        take_profit=tp_price,
                        order_id=order_id,
                        entry_time=datetime.now(timezone.utc)
                    )
                self.bot_state.add_log(f"Entry order {order_id} placed successfully.", "SUCCESS")
            else:
                self.bot_state.add_log("Entry order placement failed.", "ERROR")
        else:
            self.bot_state.add_log(f"Calculated quantity ({qty or 'N/A'}) is below minimum or invalid. No trade placed.", "WARNING")

    def _manage_active_position(self):
        """Manages SL, TP, breakeven, and partial profits for an open position."""
        pos = self.bot_state.position
        if not pos: return

        # Ensure current price is updated
        pos.current_price = self.bot_state.current_price

        # PnL calculations for management
        pnl_pct = pos.pnl_pct

        # --- Breakeven Logic ---
        if self.config.BREAKEVEN_ENABLED and not pos.breakeven_activated:
            if (pos.side == "Buy" and pnl_pct >= self.config.BREAKEVEN_PROFIT_PCT) or \
               (pos.side == "Sell" and pnl_pct >= self.config.BREAKEVEN_PROFIT_PCT):

                new_sl = pos.entry_price
                if pos.side == "Buy":
                    new_sl += pos.entry_price * (self.config.BREAKEVEN_OFFSET_PCT / Decimal('100'))
                else: # Sell
                    new_sl -= pos.entry_price * (self.config.BREAKEVEN_OFFSET_PCT / Decimal('100'))

                specs = self.precision_manager.get_specs(self.config.SYMBOL, self.config.CATEGORY)
                if specs:
                    new_sl = self.precision_manager.round_price(specs, new_sl)
                    if (pos.side == "Buy" and new_sl > pos.stop_loss) or \
                       (pos.side == "Sell" and new_sl < pos.stop_loss):

                        self.bot_state.add_log(f"Breakeven profit target hit ({pnl_pct:.2f}%). Moving SL to {new_sl:.4f}.", "INFO")
                        if self._update_trading_stop(stop_loss=new_sl):
                            with self.bot_state.lock:
                                pos.stop_loss = new_sl
                                pos.breakeven_activated = True
                        else:
                            self.bot_state.add_log("Failed to set breakeven stop loss.", "ERROR")

        # --- Trailing Stop Logic ---
        if self.config.TRAILING_SL_ENABLED:
            if not pos.trailing_sl_activated and pnl_pct >= self.config.TRAILING_SL_ACTIVATION_PCT:
                with self.bot_state.lock:
                    pos.trailing_sl_activated = True
                self.bot_state.add_log(f"Trailing SL activated at {pnl_pct:.2f}% profit.", "INFO")

            if pos.trailing_sl_activated:
                new_trailing_sl = Decimal('0')
                if pos.side == "Buy":
                    # Trail by a percentage below current price
                    new_trailing_sl = pos.current_price * (Decimal('1') - (self.config.TRAILING_SL_DISTANCE_PCT / Decimal('100')))
                else: # Sell
                    # Trail by a percentage above current price
                    new_trailing_sl = pos.current_price * (Decimal('1') + (self.config.TRAILING_SL_DISTANCE_PCT / Decimal('100')))

                specs = self.precision_manager.get_specs(self.config.SYMBOL, self.config.CATEGORY)
                if specs:
                    new_trailing_sl = self.precision_manager.round_price(specs, new_trailing_sl)

                    # Only update if the new trailing SL is better (higher for buy, lower for sell)
                    # and if it's not worse than the current SL (which could be breakeven)
                    if (pos.side == "Buy" and new_trailing_sl > pos.stop_loss) or \
                       (pos.side == "Sell" and new_trailing_sl < pos.stop_loss):

                        self.bot_state.add_log(f"Updating trailing SL to {new_trailing_sl:.4f}.", "INFO")
                        if self._update_trading_stop(stop_loss=new_trailing_sl):
                            with self.bot_state.lock:
                                pos.stop_loss = new_trailing_sl
                        else:
                            self.bot_state.add_log("Failed to update trailing stop loss.", "ERROR")

        # --- Partial Take Profit Logic ---
        if self.config.PARTIAL_TP_ENABLED and pos.size > specs.min_order_qty:
            for target in self.config.PARTIAL_TP_TARGETS:
                # Check if this target has already been hit
                if any(t['profit_pct'] == target['profit_pct'] for t in pos.partial_closes):
                    continue

                if (pos.side == "Buy" and pnl_pct >= target['profit_pct']) or \
                   (pos.side == "Sell" and pnl_pct >= target['profit_pct']):

                    qty_to_close = pos.size * target['close_qty_pct']
                    qty_to_close = self.precision_manager.round_quantity(specs, qty_to_close)

                    # Ensure we don't close more than available or less than min order qty
                    if qty_to_close > pos.size: qty_to_close = pos.size
                    if qty_to_close < specs.min_order_qty:
                        self.bot_state.add_log(f"Calculated partial TP qty {qty_to_close:.4f} is too small. Skipping.", "WARNING")
                        continue

                    self.bot_state.add_log(f"Partial TP target hit ({target['profit_pct']:.2f}%). Closing {qty_to_close:.4f} of position.", "INFO")
                    if self._close_position(partial_qty=qty_to_close):
                        with self.bot_state.lock:
                            pos.partial_closes.append({
                                'profit_pct': target['profit_pct'],
                                'closed_qty': qty_to_close,
                                'closed_qty_pct': target['close_qty_pct'] # Store original % for UI display
                            })
                            pos.size -= qty_to_close # Update local position size
                            if pos.size < specs.min_order_qty: # If remaining size is too small after partial close
                                self.bot_state.add_log(f"Remaining position size {pos.size:.4f} is too small. Closing the rest.", "INFO")
                                self._close_position(partial_qty=pos.size) # Close the tiny remainder
                            self.bot_state.add_log(f"Partial close successful. Remaining size: {pos.size:.4f}", "SUCCESS")
                    else:
                        self.bot_state.add_log("Failed to execute partial take profit.", "ERROR")

    # --- Data & State Management ---
    def _fetch_initial_klines(self, timeframe: str) -> bool:
        """Fetches the initial set of kline data for indicators."""
        self.bot_state.add_log(f"Fetching initial {self.config.LOOKBACK_PERIODS} klines for {self.config.SYMBOL} on {timeframe} TF...", "INFO")
        result = self._api_call(self.session.get_kline,
            category=self.config.CATEGORY,
            symbol=self.config.SYMBOL,
            interval=timeframe,
            limit=self.config.LOOKBACK_PERIODS
        )
        if result and result['list']:
            df = pd.DataFrame(result['list'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            with self.bot_state.lock:
                self.klines_dfs[timeframe] = df.sort_values('timestamp').reset_index(drop=True)
                if not df.empty:
                    self.last_kline_timestamp[timeframe] = df['timestamp'].iloc[-1]
            self.bot_state.add_log(f"Initial kline data fetched successfully for {timeframe}.", "SUCCESS")
            return True
        self.bot_state.add_log(f"Failed to fetch initial kline data for {timeframe}.", "ERROR")
        return False

    def _update_kline_data(self, kline: dict[str, Any], timeframe: str):
        """Updates the main kline DataFrame with a new candle."""
        new_row = {
            'timestamp': datetime.fromtimestamp(int(kline['start']) / 1000, tz=timezone.utc),
            'open': Decimal(kline['open']),
            'high': Decimal(kline['high']),
            'low': Decimal(kline['low']),
            'close': Decimal(kline['close']),
            'volume': Decimal(kline['volume']),
            'turnover': Decimal(kline['turnover'])
        }
        with self.bot_state.lock:
            df = self.klines_dfs.get(timeframe)
            if df is None:
                self.logger.warning(f"DataFrame for {timeframe} not initialized. Cannot update kline.")
                return

            # Append new row and drop oldest
            df.loc[len(df)] = new_row
            df.drop(df.index[0], inplace=True)
            df.reset_index(drop=True, inplace=True)
            self.klines_dfs[timeframe] = df

    def _calculate_all_timeframe_indicators(self):
        """Calculates indicators for all active timeframes."""
        with self.bot_state.lock:
            for tf, df in self.klines_dfs.items():
                if df.empty:
                    self.logger.warning(f"DataFrame for {tf} is empty, skipping indicator calculation.")
                    continue

                processed_df = self.indicator_calculator.calculate_all_indicators(df.copy()) # Use copy to avoid SettingWithCopyWarning
                self.klines_dfs[tf] = processed_df

                if tf == self.config.PRIMARY_TIMEFRAME and not processed_df.empty:
                    # Update bot_state with primary TF indicators for UI
                    latest_indicators = processed_df.iloc[-1].to_dict()
                    self.bot_state.indicator_values = {k: v for k, v in latest_indicators.items() if k not in ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover']}
                    self.bot_state.supertrend_line = Decimal(str(latest_indicators.get('supertrend_line', '0')))
                    self.bot_state.supertrend_direction = "Uptrend" if latest_indicators.get('supertrend_direction') == 1 else \
                                                          "Downtrend" if latest_indicators.get('supertrend_direction') == -1 else "Neutral"

                    # Update MarketData for primary TF
                    self.bot_state.market_data[tf] = MarketData(
                        timestamp=latest_indicators['timestamp'],
                        open=Decimal(str(latest_indicators['open'])),
                        high=Decimal(str(latest_indicators['high'])),
                        low=Decimal(str(latest_indicators['low'])),
                        close=Decimal(str(latest_indicators['close'])),
                        volume=Decimal(str(latest_indicators['volume']))
                    )
            self.logger.debug("Indicators calculated for all timeframes.")

    def _analyze_market_conditions(self):
        """Performs market analysis and updates bot state."""
        with self.bot_state.lock:
            primary_df = self.klines_dfs.get(self.config.PRIMARY_TIMEFRAME)
            if primary_df is None or primary_df.empty:
                self.logger.warning("Primary timeframe DataFrame is empty for market analysis.")
                self.bot_state.market_regime = MarketRegime.UNKNOWN
                return

            # Market Regime
            self.bot_state.market_regime = self.market_analyzer.analyze_market_regime(primary_df)

            # S/R Levels (optional, for potential future use or display)
            sr_levels = self.market_analyzer.calculate_support_resistance(primary_df)
            self.bot_state.indicator_values.update(sr_levels)

            # Volume Profile (if enabled)
            if self.config.USE_VOLUME_PROFILE:
                volume_profile_data = self.market_analyzer.analyze_volume_profile(primary_df)
                self.bot_state.indicator_values.update(volume_profile_data)
                if self.config.PRIMARY_TIMEFRAME in self.bot_state.market_data:
                    self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].vwap = volume_profile_data.get('vwap', Decimal('0'))

            self.logger.debug(f"Market analysis complete. Regime: {self.bot_state.market_regime.value}")

    def _update_position_state(self):
        """Fetches and updates the bot's current position state."""
        result = self._api_call(self.session.get_positions, category=self.config.CATEGORY, symbol=self.config.SYMBOL)
        with self.bot_state.lock:
            if result and result['list']:
                pos_info = result['list'][0]
                size_decimal = Decimal(pos_info['size'])

                if size_decimal > Decimal('0'):
                    self.bot_state.position_active = True
                    # Update existing position object or create a new one
                    if self.bot_state.position is None or self.bot_state.position.symbol != self.config.SYMBOL:
                        self.bot_state.position = Position(
                            symbol=self.config.SYMBOL,
                            side=pos_info['side'],
                            size=size_decimal,
                            entry_price=Decimal(pos_info['avgPrice']),
                            stop_loss=Decimal(pos_info.get('stopLoss', '0')),
                            take_profit=Decimal(pos_info.get('takeProfit', '0')),
                            unrealized_pnl=Decimal(pos_info.get('unrealisedPnl', '0')),
                            entry_time=datetime.fromtimestamp(int(pos_info['createdTime']) / 1000, tz=timezone.utc)
                        )
                    else: # Update existing position
                        self.bot_state.position.size = size_decimal
                        self.bot_state.position.entry_price = Decimal(pos_info['avgPrice'])
                        self.bot_state.position.stop_loss = Decimal(pos_info.get('stopLoss', '0'))
                        self.bot_state.position.take_profit = Decimal(pos_info.get('takeProfit', '0'))
                        self.bot_state.position.unrealized_pnl = Decimal(pos_info.get('unrealisedPnl', '0'))
                        self.bot_state.position.current_price = self.bot_state.current_price # Update from ticker
                        # Breakeven/trailing flags are managed internally by the bot logic, not from Bybit API directly
                else:
                    # Position closed, record trade if it was active
                    if self.bot_state.position_active and self.bot_state.position is not None:
                        self._record_trade(self.bot_state.position)

                    self.bot_state.position_active = False
                    self.bot_state.position = None
            else:
                if self.bot_state.position_active and self.bot_state.position is not None:
                    self._record_trade(self.bot_state.position)
                self.bot_state.position_active = False
                self.bot_state.position = None
            self.logger.debug(f"Position state updated: Active={self.bot_state.position_active}")

    def _get_account_balance(self, coin="USDT") -> Decimal:
        """Fetches the account balance for a specific coin."""
        result = self._api_call(self.session.get_wallet_balance, accountType="UNIFIED", coin=coin)
        if result and result['list']:
            for item in result['list']:
                for c in item['coin']:
                    if c['coin'] == coin:
                        return Decimal(c['walletBalance'])
        self.bot_state.add_log(f"Could not retrieve account balance for {coin}.", "WARNING")
        return Decimal('0')

    # --- Order Execution ---
    def _place_order(self, side: str, qty: Decimal, order_type: OrderType, price: Decimal | None, sl: Decimal, tp: Decimal) -> str | None:
        """Places a trade order on Bybit."""
        params = {
            "category": self.config.CATEGORY,
            "symbol": self.config.SYMBOL,
            "side": side,
            "orderType": order_type.value,
            "qty": str(qty),
            "stopLoss": str(sl),
            "takeProfit": str(tp),
        }
        if order_type == OrderType.LIMIT and price:
            # For Limit orders, adjust price slightly for better fill odds or post-only
            target_price = price
            if self.config.LIMIT_ORDER_OFFSET_PCT > 0:
                offset = self.bot_state.current_price * (self.config.LIMIT_ORDER_OFFSET_PCT / Decimal('100'))
                if side == "Buy": # Buy lower
                    target_price = self.bot_state.current_price - offset
                else: # Sell higher
                    target_price = self.bot_state.current_price + offset

            specs = self.precision_manager.get_specs(self.config.SYMBOL, self.config.CATEGORY)
            if specs:
                target_price = self.precision_manager.round_price(specs, target_price)

            params["price"] = str(target_price)
            if self.config.POST_ONLY_LIMIT_ORDERS:
                params["timeInForce"] = "PostOnly"

        result = self._api_call(self.session.place_order, **params)
        if result:
            order_id = result.get('orderId')
            self.bot_state.add_log(f"Order placed: {side} {qty:.4f} @ {order_type.value} price {params.get('price', 'Market')} (OrderID: {order_id})", "INFO")
            return order_id
        else:
            self.bot_state.add_log("Order placement failed.", "ERROR")
            return None

    def _update_trading_stop(self, stop_loss: Decimal | None = None, take_profit: Decimal | None = None) -> bool:
        """Updates the stop loss and/or take profit for an active position."""
        pos = self.bot_state.position
        if not pos:
            self.logger.warning("No active position to update trading stop.")
            return False

        params = {
            "category": self.config.CATEGORY,
            "symbol": self.config.SYMBOL,
            "positionIdx": 0 if self.config.CATEGORY == "spot" else 0, # 0 for one-way mode, 1 for long, 2 for short for hedge mode
            "tpslMode": "Full" # Ensure SL/TP apply to full position
        }
        if stop_loss is not None:
            params["stopLoss"] = str(stop_loss)
        if take_profit is not None:
            params["takeProfit"] = str(take_profit)

        result = self._api_call(self.session.set_trading_stop, **params)
        if result:
            self.bot_state.add_log(f"Trading stop updated for {self.config.SYMBOL}. SL: {stop_loss or 'N/A'}, TP: {take_profit or 'N/A'}", "INFO")
            return True
        else:
            self.bot_state.add_log("Failed to update trading stop.", "ERROR")
            return False

    def _close_position(self, partial_qty: Decimal | None = None) -> bool:
        """Closes the current active position, fully or partially."""
        pos = self.bot_state.position
        if not pos:
            self.bot_state.add_log("No active position to close.", "WARNING")
            return False

        side = "Sell" if pos.side == "Buy" else "Buy" # Opposite side to close
        qty = partial_qty if partial_qty else pos.size

        specs = self.precision_manager.get_specs(self.config.SYMBOL, self.config.CATEGORY)
        if not specs:
            self.bot_state.add_log("Could not get instrument specs for closing position.", "ERROR")
            return False

        qty = self.precision_manager.round_quantity(specs, qty)
        if qty < specs.min_order_qty:
            self.bot_state.add_log(f"Quantity to close ({qty:.4f}) is less than min order qty {specs.min_order_qty}. Cannot close.", "WARNING")
            return False

        self.bot_state.add_log(f"Closing {'part of' if partial_qty else 'all of'} position. Side: {side}, Qty: {qty:.4f}", "INFO")

        # We use MARKET order to ensure immediate closure
        order_id = self._place_order(side, qty, OrderType.MARKET, None, Decimal('0'), Decimal('0'))

        if order_id:
            self.bot_state.add_log(f"Close order {order_id} placed successfully.", "SUCCESS")
            # The position state will be updated by the WebSocket position handler
            return True
        else:
            self.bot_state.add_log("Close order placement failed.", "ERROR")
            return False

    def _set_leverage_and_margin(self):
        """Sets leverage and margin mode for the trading symbol."""
        if self.config.CATEGORY.lower() == "spot":
            self.logger.info("Spot trading does not use leverage or margin mode.")
            return

        # Set Cross Margin mode (common for bots)
        self.logger.info(f"Setting margin mode to CROSS for {self.config.SYMBOL}")
        self._api_call(self.session.set_margin_mode,
            category=self.config.CATEGORY,
            symbol=self.config.SYMBOL,
            tradeMode=1, # 0: Isolated, 1: Cross
            buyLeverage=str(self.config.LEVERAGE), # Required even for cross
            sellLeverage=str(self.config.LEVERAGE)
        )

        self.logger.info(f"Setting leverage to {self.config.LEVERAGE}x for {self.config.SYMBOL}")
        self._api_call(self.session.set_leverage,
            category=self.config.CATEGORY,
            symbol=self.config.SYMBOL,
            buyLeverage=str(self.config.LEVERAGE),
            sellLeverage=str(self.config.LEVERAGE)
        )

    def _record_trade(self, closed_position: Position):
        """Records a completed trade to history and updates performance metrics."""
        self.logger.info(f"Recording trade for {closed_position.symbol} (Side: {closed_position.side})...")

        # Fetch actual realized PnL and fees if possible (might need to query order history or transaction log)
        # For simplicity, we'll use the unrealized PnL at close as 'pnl' and assume 0 fees for now.
        # A more advanced implementation would query Bybit's transaction history for actual fees.
        exit_price = self.bot_state.current_price
        pnl = closed_position.unrealized_pnl # This is a simplification; ideally get actual realized PnL

        # Re-calculate PnL % based on actual exit price
        if closed_position.entry_price == Decimal('0'):
            pnl_pct_actual = Decimal('0')
        elif closed_position.side == "Buy":
            pnl_pct_actual = ((exit_price - closed_position.entry_price) / closed_position.entry_price) * Decimal('100')
        else: # Sell
            pnl_pct_actual = ((closed_position.entry_price - exit_price) / closed_position.entry_price) * Decimal('100')

        # Assume fees are 0.05% of trade value (maker/taker) for a rough estimate if not fetched from API
        estimated_fees = (closed_position.size * closed_position.entry_price * Decimal('0.0005')) + \
                         (closed_position.size * exit_price * Decimal('0.0005'))
        pnl_after_fees = pnl - estimated_fees

        trade_record = Trade(
            symbol=closed_position.symbol,
            side=closed_position.side,
            entry_price=closed_position.entry_price,
            exit_price=exit_price,
            size=closed_position.size,
            pnl=pnl_after_fees,
            pnl_pct=pnl_pct_actual,
            entry_time=closed_position.entry_time,
            exit_time=datetime.now(timezone.utc),
            duration=closed_position.duration,
            exit_reason="Closed by bot logic/SL/TP", # Can be more specific
            fees=estimated_fees
        )

        with self.bot_state.lock:
            self.bot_state.trade_history.append(trade_record)
            self.bot_state.metrics.update(trade_record, self.bot_state.account_balance)
            self.bot_state.add_log(f"Trade recorded: {trade_record.side} {trade_record.size:.4f} @ {trade_record.entry_price:.4f} -> {trade_record.exit_price:.4f}. PnL: {trade_record.pnl:+.2f} ({trade_record.pnl_pct:+.2f}%)", "SUCCESS")

            if self.config.SAVE_TRADES_CSV:
                self._save_trade_to_csv(trade_record)
        self.logger.info("Trade recorded and metrics updated.")

    def _save_trade_to_csv(self, trade: Trade):
        """Appends a single trade record to a CSV file."""
        trade_dict = asdict(trade)
        df = pd.DataFrame([trade_dict])

        # Check if file exists to write header or append
        file_exists = Path(self.config.TRADES_FILE).is_file()
        df.to_csv(self.config.TRADES_FILE, mode='a', header=not file_exists, index=False)
        self.logger.debug(f"Trade appended to {self.config.TRADES_FILE}")

    def _state_saver_loop(self):
        """Periodically saves the bot's state."""
        while not self.stop_event.is_set():
            time.sleep(self.config.SAVE_STATE_INTERVAL)
            if not self.stop_event.is_set():
                self.bot_state.save_state(self.config.STATE_FILE)

    # --- Shutdown & Cleanup ---
    def _signal_handler(self, signum, frame):
        self.bot_state.add_log(f"Signal {signum} received. Initiating graceful shutdown...", "WARNING")
        self.logger.warning(f"Signal {signum} received. Initiating graceful shutdown...")
        self.stop_event.set()

    def _install_signal_handlers(self):
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def cleanup(self):
        self.bot_state.add_log("Cleaning up and shutting down bot...", "INFO")
        self.logger.info("Cleaning up and shutting down bot...")

        # Stop UI thread
        if hasattr(self, 'ui') and self.ui:
            self.ui.stop()
            self.ui.join(timeout=5) # Wait for UI thread to finish

        # Stop state saver thread
        if self.state_saver_thread:
            self.state_saver_thread.join(timeout=5)

        # Close WebSockets
        self._close_websockets()

        # Save final state
        self.bot_state.save_state(self.config.STATE_FILE)

        # Auto-close active position if configured
        if self.config.AUTO_CLOSE_ON_SHUTDOWN:
            self._update_position_state() # Get latest position state
            if self.bot_state.position_active:
                self.bot_state.add_log("Auto-closing active position as per configuration.", "INFO")
                self._close_position() # This will trigger a final trade record via WS handler
                time.sleep(2) # Give some time for the order to process and WS to update

        self.bot_state.add_log("Bot shutdown complete. Goodbye! 👋", "INFO")
        self.logger.info("Bot shutdown complete. Goodbye! 👋")

# =====================================================================
# MAIN ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    # --- Interactive Setup for Symbol and Timeframe ---
    print(Fore.CYAN + Style.BRIGHT + "--- Advanced Supertrend Bot Setup ---" + Style.RESET_ALL)

    # Create a temporary config to get default values for user prompts
    temp_config = EnhancedConfig()

    user_symbol = input(f"Enter trading symbol (e.g., BTCUSDT) [Default: {temp_config.SYMBOL}]: ").strip().upper()
    if user_symbol:
        temp_config.SYMBOL = user_symbol

    valid_intervals = {"1", "3", "5", "15", "30", "60", "120", "240", "D", "W", "M"}
    all_timeframes = sorted(list(valid_intervals))

    while True:
        user_primary_timeframe = input(f"Enter primary timeframe {all_timeframes} [Default: {temp_config.PRIMARY_TIMEFRAME}]: ").strip()
        if not user_primary_timeframe:
            break
        if user_primary_timeframe in valid_intervals:
            temp_config.PRIMARY_TIMEFRAME = user_primary_timeframe
            break
        else:
            print(Fore.RED + "Invalid primary timeframe selected. Please try again.")

    secondary_tfs_str = ", ".join(temp_config.SECONDARY_TIMEFRAMES)
    user_secondary_timeframes = input(f"Enter secondary timeframes (comma-separated, e.g., 5,60) [Default: {secondary_tfs_str}]: ").strip()
    if user_secondary_timeframes:
        chosen_secondary = []
        for tf in user_secondary_timeframes.split(','):
            tf = tf.strip()
            if tf in valid_intervals:
                chosen_secondary.append(tf)
            else:
                print(Fore.YELLOW + f"Warning: Invalid secondary timeframe '{tf}' ignored." + Style.RESET_ALL)
        if chosen_secondary:
            temp_config.SECONDARY_TIMEFRAMES = chosen_secondary

    print(Fore.GREEN + f"\nConfiguration set to Symbol: {temp_config.SYMBOL}, Primary TF: {temp_config.PRIMARY_TIMEFRAME}, Secondary TFs: {', '.join(temp_config.SECONDARY_TIMEFRAMES)}\n" + Style.RESET_ALL)

    try:
        # Use the modified temp_config to create the actual config object
        config = EnhancedConfig(
            API_KEY=temp_config.API_KEY,
            API_SECRET=temp_config.API_SECRET,
            TESTNET=temp_config.TESTNET,
            SYMBOL=temp_config.SYMBOL,
            CATEGORY=temp_config.CATEGORY,
            LEVERAGE=temp_config.LEVERAGE,
            PRIMARY_TIMEFRAME=temp_config.PRIMARY_TIMEFRAME,
            SECONDARY_TIMEFRAMES=temp_config.SECONDARY_TIMEFRAMES,
            LOOKBACK_PERIODS=temp_config.LOOKBACK_PERIODS,
            ST_PERIOD_BASE=temp_config.ST_PERIOD_BASE,
            ST_MULTIPLIER_BASE=temp_config.ST_MULTIPLIER_BASE,
            ADAPTIVE_PARAMS=temp_config.ADAPTIVE_PARAMS,
            RISK_PER_TRADE_PCT=temp_config.RISK_PER_TRADE_PCT,
            MAX_POSITION_SIZE_PCT=temp_config.MAX_POSITION_SIZE_PCT,
            STOP_LOSS_PCT=temp_config.STOP_LOSS_PCT,
            TAKE_PROFIT_PCT=temp_config.TAKE_PROFIT_PCT,
            USE_ATR_STOPS=temp_config.USE_ATR_STOPS,
            ATR_STOP_MULTIPLIER=temp_config.ATR_STOP_MULTIPLIER,
            ATR_TP_MULTIPLIER=temp_config.ATR_TP_MULTIPLIER,
            MAX_DAILY_LOSS_PCT=temp_config.MAX_DAILY_LOSS_PCT,
            MAX_DAILY_TRADES=temp_config.MAX_DAILY_TRADES,
            MAX_CONSECUTIVE_LOSSES=temp_config.MAX_CONSECUTIVE_LOSSES,
            MAX_DRAWDOWN_PCT=temp_config.MAX_DRAWDOWN_PCT,
            ORDER_TYPE=temp_config.ORDER_TYPE,
            LIMIT_ORDER_OFFSET_PCT=temp_config.LIMIT_ORDER_OFFSET_PCT,
            POST_ONLY_LIMIT_ORDERS=temp_config.POST_ONLY_LIMIT_ORDERS,
            ADX_TREND_FILTER=temp_config.ADX_TREND_FILTER,
            ADX_MIN_THRESHOLD=temp_config.ADX_MIN_THRESHOLD,
            VOLUME_FILTER=temp_config.VOLUME_FILTER,
            VOLUME_MULTIPLIER=temp_config.VOLUME_MULTIPLIER,
            RSI_FILTER=temp_config.RSI_FILTER,
            RSI_OVERSOLD=temp_config.RSI_OVERSOLD,
            RSI_OVERBOUGHT=temp_config.RSI_OVERBOUGHT,
            USE_ORDER_BOOK=temp_config.USE_ORDER_BOOK,
            ORDER_BOOK_IMBALANCE_THRESHOLD=temp_config.ORDER_BOOK_IMBALANCE_THRESHOLD,
            ORDER_BOOK_DEPTH_LEVELS=temp_config.ORDER_BOOK_DEPTH_LEVELS,
            USE_VOLUME_PROFILE=temp_config.USE_VOLUME_PROFILE,
            PARTIAL_TP_ENABLED=temp_config.PARTIAL_TP_ENABLED,
            PARTIAL_TP_TARGETS=temp_config.PARTIAL_TP_TARGETS,
            BREAKEVEN_PROFIT_PCT=temp_config.BREAKEVEN_PROFIT_PCT,
            BREAKEVEN_OFFSET_PCT=temp_config.BREAKEVEN_OFFSET_PCT,
            TRAILING_SL_ENABLED=temp_config.TRAILING_SL_ENABLED,
            TRAILING_SL_ACTIVATION_PCT=temp_config.TRAILING_SL_ACTIVATION_PCT,
            TRAILING_SL_DISTANCE_PCT=temp_config.TRAILING_SL_DISTANCE_PCT,
            LOG_LEVEL=temp_config.LOG_LEVEL,
            SAVE_TRADES_CSV=temp_config.SAVE_TRADES_CSV,
            TRADES_FILE=temp_config.TRADES_FILE,
            STATE_FILE=temp_config.STATE_FILE,
            SAVE_STATE_INTERVAL=temp_config.SAVE_STATE_INTERVAL,
            USE_KELLY_SIZING=temp_config.USE_KELLY_SIZING,
            KELLY_FRACTION_CAP=temp_config.KELLY_FRACTION_CAP
        )

        bot = AdvancedSupertrendBot(config)
        bot.run()
    except Exception as e:
        # Catch any fatal error during bot initialization or main loop
        # Ensure a basic logger is set up if the main bot's logger failed
        if not logging.getLogger('SuperTrendBot').handlers:
            logging.basicConfig(level=logging.CRITICAL, format='%(asctime)s - %(levelname)s - %(message)s')
        logging.getLogger('SuperTrendBot').critical(f"A fatal error occurred: {e}", exc_info=True)
        sys.exit(1)


