#!/usr/bin/env python3
"""
Advanced Supertrend Trading Bot for Bybit V5 API - Enhanced Edition v2.0

This script implements an advanced trading bot using the Supertrend indicator
(based on Ehlers' methodology) with a comprehensive set of enhancements.

Key Features:
- **Multi-timeframe Analysis**: Uses multiple timeframes for signal confirmation.
- **Real-time WebSockets**: Connects to Bybit's WebSocket for live market data (klines, tickers, order book)
  and account updates (positions, wallet).
- **Advanced Order Book Analysis**: Calculates order book imbalance and VWAP for market sentiment.
- **Adaptive Indicator Parameters**: Supertrend parameters adjust based on market volatility.
- **Kelly Criterion Position Sizing**: Dynamically adjusts position size based on trading history
  and Kelly Criterion principles, with a configurable cap.
- **Performance Analytics & Trade Journaling**: Tracks detailed performance metrics, generates
  Sharpe Ratio, and saves trade history to CSV.
- **Market Regime Detection**: Identifies current market conditions (trending, ranging, volatile, calm).
- **Volume Profile Analysis**: Calculates Point of Control (POC) and Volume Weighted Average Price (VWAP).
- **Enhanced Real-time Terminal UI**: Provides a rich, color-coded, and organized display of bot status,
  market data, indicators, position details, and performance metrics.
- **Robust State Persistence & Graceful Shutdown**: Saves and loads bot state to/from a file,
  and handles termination signals (Ctrl+C, SIGTERM) for clean shutdown, including optional
  auto-closing of open positions.
- **Comprehensive Risk Management**: Includes configurable stop-loss, take-profit, breakeven,
  and trailing stop loss mechanisms. Implements daily loss limits, maximum trades,
  consecutive loss limits, and maximum drawdown limits.
- **Signal Filters**: Incorporates ADX, RSI, MACD, and Volume filters to confirm trading signals,
  assigning a confidence "strength" to each signal.
- **Partial Take Profits**: Allows for staged profit-taking at multiple price targets.
- **Precision Handling**: Automatically handles Bybit instrument specifications for accurate
  price and quantity rounding.
- **API Resilience**: Implements retry logic with exponential backoff for API calls.
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
from decimal import ROUND_DOWN, Decimal, InvalidOperation, getcontext
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
    """Trading signals."""

    STRONG_BUY = 2
    BUY = 1
    NEUTRAL = 0
    SELL = -1
    STRONG_SELL = -2


class OrderType(Enum):
    """Supported order types."""

    MARKET = "Market"
    LIMIT = "Limit"


class Category(Enum):
    """Bybit product categories."""

    LINEAR = "linear"
    SPOT = "spot"
    INVERSE = "inverse"
    OPTION = "option"

    @classmethod
    def from_string(cls, value: str) -> "Category":
        """Converts a string to a Category enum member."""
        try:
            return cls[value.upper()]
        except KeyError:
            raise ValueError(
                f"Invalid Category value: {value}. Choose from {[c.name for c in cls]}"
            )


class MarketRegime(Enum):
    """Identified market regimes."""

    TRENDING_UP = "Trending Up"
    TRENDING_DOWN = "Trending Down"
    RANGING = "Ranging"
    VOLATILE = "Volatile"
    CALM = "Calm"
    UNKNOWN = "Unknown"


@dataclass
class EnhancedConfig:
    """Enhanced bot configuration with advanced features.

    This dataclass holds all configurable parameters for the trading bot,
    covering API settings, trading parameters, timeframes, risk management,
    order execution, signal filters, market structure analysis, partial take profits,
    breakeven/trailing stops, performance logging, and Kelly Criterion sizing.
    Values are loaded from environment variables.
    """

    # API Configuration
    API_KEY: str = field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    API_SECRET: str = field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    TESTNET: bool = field(
        default_factory=lambda: os.getenv("BYBIT_TESTNET", "true").lower()
        in ["true", "1"]
    )

    # Trading Configuration
    SYMBOL: str = field(default_factory=lambda: os.getenv("BYBIT_SYMBOL", "BTCUSDT"))
    CATEGORY: str = field(
        default_factory=lambda: os.getenv("BYBIT_CATEGORY", "linear")
    )  # "linear", "spot", "inverse"
    LEVERAGE: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("BYBIT_LEVERAGE", "10"))
    )

    # Multi-timeframe Configuration
    PRIMARY_TIMEFRAME: str = field(
        default_factory=lambda: os.getenv("PRIMARY_TIMEFRAME", "15")
    )  # e.g., "1", "5", "15", "60", "240", "D"
    SECONDARY_TIMEFRAMES: list[str] = field(
        default_factory=lambda: os.getenv("SECONDARY_TIMEFRAMES", "5,60").split(",")
    )  # Additional TFs for confirmation
    LOOKBACK_PERIODS: int = field(
        default_factory=lambda: int(os.getenv("LOOKBACK_PERIODS", "200"))
    )  # Klines to fetch initially

    # Adaptive SuperTrend Parameters
    ST_PERIOD_BASE: int = field(
        default_factory=lambda: int(os.getenv("ST_PERIOD", "10"))
    )
    ST_MULTIPLIER_BASE: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("ST_MULTIPLIER", "3.0"))
    )
    ADAPTIVE_PARAMS: bool = field(
        default_factory=lambda: os.getenv("ADAPTIVE_PARAMS", "true").lower()
        in ["true", "1"]
    )

    # Risk Management
    RISK_PER_TRADE_PCT: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
    )  # % of equity risked per trade
    MAX_POSITION_SIZE_PCT: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("MAX_POSITION_SIZE_PCT", "30.0"))
    )  # Max % of equity for position
    STOP_LOSS_PCT: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("STOP_LOSS_PCT", "1.5"))
    )  # Default SL % if ATR_STOPS is false
    TAKE_PROFIT_PCT: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("TAKE_PROFIT_PCT", "3.0"))
    )  # Default TP % if ATR_STOPS is false
    USE_ATR_STOPS: bool = field(
        default_factory=lambda: os.getenv("USE_ATR_STOPS", "true").lower()
        in ["true", "1"]
    )
    ATR_STOP_MULTIPLIER: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("ATR_STOP_MULTIPLIER", "1.5"))
    )  # ATR Multiplier for SL
    ATR_TP_MULTIPLIER: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("ATR_TP_MULTIPLIER", "3.0"))
    )  # ATR Multiplier for TP

    # Daily Limits
    MAX_DAILY_LOSS_PCT: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("MAX_DAILY_LOSS_PCT", "5.0"))
    )
    MAX_DAILY_TRADES: int = field(
        default_factory=lambda: int(os.getenv("MAX_DAILY_TRADES", "10"))
    )
    MAX_CONSECUTIVE_LOSSES: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
    )
    MAX_DRAWDOWN_PCT: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("MAX_DRAWDOWN_PCT", "10.0"))
    )  # Max % drop from peak equity

    # Order Type & Execution
    ORDER_TYPE: str = field(
        default_factory=lambda: os.getenv("ORDER_TYPE", "Market")
    )  # "Market" or "Limit"
    LIMIT_ORDER_OFFSET_PCT: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("LIMIT_ORDER_OFFSET_PCT", "0.01"))
    )  # Place limit orders 0.01% better than market
    POST_ONLY_LIMIT_ORDERS: bool = field(
        default_factory=lambda: os.getenv("POST_ONLY_LIMIT_ORDERS", "true").lower()
        in ["true", "1"]
    )
    # HEDGE_MODE and POSITION_IDX are critical for Bybit V5 for derivatives
    HEDGE_MODE: bool = field(
        default_factory=lambda: os.getenv("BYBIT_HEDGE_MODE", "false").lower()
        in ["true", "1"]
    )
    POSITION_IDX: int = field(
        default_factory=lambda: int(os.getenv("BYBIT_POSITION_IDX", "0"))
    )  # 0=One-way mode, 1=Long, 2=Short in hedge mode

    # Signal Filters
    ADX_TREND_FILTER: bool = field(
        default_factory=lambda: os.getenv("ADX_TREND_FILTER", "true").lower()
        in ["true", "1"]
    )
    ADX_MIN_THRESHOLD: int = field(
        default_factory=lambda: int(os.getenv("ADX_MIN_THRESHOLD", "25"))
    )
    ADX_WINDOW: int = field(
        default_factory=lambda: int(os.getenv("ADX_WINDOW", "14"))
    )  # ADX period
    VOLUME_FILTER: bool = field(
        default_factory=lambda: os.getenv("VOLUME_FILTER", "true").lower()
        in ["true", "1"]
    )
    VOLUME_MULTIPLIER: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("VOLUME_MULTIPLIER", "1.5"))
    )  # Volume must be 1.5x avg
    RSI_FILTER: bool = field(
        default_factory=lambda: os.getenv("RSI_FILTER", "true").lower() in ["true", "1"]
    )
    RSI_WINDOW: int = field(
        default_factory=lambda: int(os.getenv("RSI_WINDOW", "14"))
    )  # RSI period
    RSI_OVERSOLD: int = field(
        default_factory=lambda: int(os.getenv("RSI_OVERSOLD", "30"))
    )
    RSI_OVERBOUGHT: int = field(
        default_factory=lambda: int(os.getenv("RSI_OVERBOUGHT", "70"))
    )
    MACD_FILTER: bool = field(
        default_factory=lambda: os.getenv("MACD_FILTER", "true").lower()
        in ["true", "1"]
    )
    MACD_FAST: int = field(default_factory=lambda: int(os.getenv("MACD_FAST", "12")))
    MACD_SLOW: int = field(default_factory=lambda: int(os.getenv("MACD_SLOW", "26")))
    MACD_SIGNAL: int = field(default_factory=lambda: int(os.getenv("MACD_SIGNAL", "9")))

    # Market Structure
    USE_ORDER_BOOK: bool = field(
        default_factory=lambda: os.getenv("USE_ORDER_BOOK", "true").lower()
        in ["true", "1"]
    )
    ORDER_BOOK_IMBALANCE_THRESHOLD: Decimal = field(
        default_factory=lambda: Decimal(
            os.getenv("ORDER_BOOK_IMBALANCE_THRESHOLD", "0.6")
        )
    )  # 60% imbalance
    ORDER_BOOK_DEPTH_LEVELS: int = field(
        default_factory=lambda: int(os.getenv("ORDER_BOOK_DEPTH_LEVELS", "10"))
    )  # Levels to fetch
    USE_VOLUME_PROFILE: bool = field(
        default_factory=lambda: os.getenv("USE_VOLUME_PROFILE", "true").lower()
        in ["true", "1"]
    )

    # Partial Take Profit
    PARTIAL_TP_ENABLED: bool = field(
        default_factory=lambda: os.getenv("PARTIAL_TP_ENABLED", "true").lower()
        in ["true", "1"]
    )
    PARTIAL_TP_TARGETS: list[dict[str, Decimal]] = field(
        default_factory=lambda: [
            {
                "profit_pct": Decimal("1.0"),
                "close_qty_pct": Decimal("0.3"),
            },  # Close 30% at 1% profit
            {
                "profit_pct": Decimal("2.0"),
                "close_qty_pct": Decimal("0.3"),
            },  # Close another 30% at 2% profit
            {
                "profit_pct": Decimal("3.0"),
                "close_qty_pct": Decimal("0.4"),
            },  # Close remaining 40% at 3% profit
        ]
    )

    # Breakeven & Trailing Stop
    BREAKEVEN_ENABLED: bool = field(
        default_factory=lambda: os.getenv("BREAKEVEN_ENABLED", "true").lower()
        in ["true", "1"]
    )
    BREAKEVEN_PROFIT_PCT: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("BREAKEVEN_PROFIT_PCT", "0.5"))
    )  # Move SL to entry at 0.5% profit
    BREAKEVEN_OFFSET_PCT: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("BREAKEVEN_OFFSET_PCT", "0.01"))
    )  # Offset above entry for breakeven SL
    TRAILING_SL_ENABLED: bool = field(
        default_factory=lambda: os.getenv("TRAILING_SL_ENABLED", "true").lower()
        in ["true", "1"]
    )
    TRAILING_SL_ACTIVATION_PCT: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("TRAILING_SL_ACTIVATION_PCT", "1.0"))
    )  # Activate trailing SL at 1% profit
    TRAILING_SL_DISTANCE_PCT: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("TRAILING_SL_DISTANCE_PCT", "0.5"))
    )  # Trail by 0.5%

    # Performance & Logging
    LOG_LEVEL: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    SAVE_TRADES_CSV: bool = field(
        default_factory=lambda: os.getenv("SAVE_TRADES_CSV", "true").lower()
        in ["true", "1"]
    )
    TRADES_FILE: str = "trades_history.csv"
    STATE_FILE: str = "bot_state.pkl"
    SAVE_STATE_INTERVAL: int = field(
        default_factory=lambda: int(os.getenv("SAVE_STATE_INTERVAL", "300"))
    )  # seconds

    # API Retry Settings
    MAX_API_RETRIES: int = field(
        default_factory=lambda: int(os.getenv("MAX_API_RETRIES", "5"))
    )
    API_RETRY_DELAY_SEC: int = field(
        default_factory=lambda: int(os.getenv("API_RETRY_DELAY_SEC", "5"))
    )

    # Kelly Criterion
    USE_KELLY_SIZING: bool = field(
        default_factory=lambda: os.getenv("USE_KELLY_SIZING", "false").lower()
        in ["true", "1"]
    )
    KELLY_FRACTION_CAP: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("KELLY_FRACTION_CAP", "0.25"))
    )  # Max 25% of Kelly fraction

    # Auto-close on shutdown
    AUTO_CLOSE_ON_SHUTDOWN: bool = field(
        default_factory=lambda: os.getenv("AUTO_CLOSE_ON_SHUTDOWN", "false").lower()
        in ["true", "1"]
    )

    # Internal properties for derived enum types
    CATEGORY_ENUM: Category = field(init=False)
    ORDER_TYPE_ENUM: OrderType = field(init=False)

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Convert category and order type to enums for internal use
        try:
            self.CATEGORY_ENUM = Category.from_string(self.CATEGORY)
        except ValueError as e:
            raise ValueError(f"Invalid BYBIT_CATEGORY: {self.CATEGORY}. {e}")

        try:
            self.ORDER_TYPE_ENUM = OrderType[self.ORDER_TYPE.upper()]
        except KeyError:
            raise ValueError(
                f"Invalid ORDER_TYPE: '{self.ORDER_TYPE}'. Choose from {[ot.name for ot in OrderType]}"
            )

        # Validate API Keys
        if (
            not self.API_KEY
            or not self.API_SECRET
            or self.API_KEY == "YOUR_BYBIT_API_KEY"
        ):
            raise ValueError(
                "Bybit API Key or Secret not configured. Please set BYBIT_API_KEY and BYBIT_API_SECRET environment variables."
            )

        # Validate percentages (should be positive)
        for attr in [
            "RISK_PER_TRADE_PCT",
            "STOP_LOSS_PCT",
            "TAKE_PROFIT_PCT",
            "MAX_DAILY_LOSS_PCT",
            "BREAKEVEN_PROFIT_PCT",
            "BREAKEVEN_OFFSET_PCT",
            "TRAILING_SL_ACTIVATION_PCT",
            "TRAILING_SL_DISTANCE_PCT",
            "KELLY_FRACTION_CAP",
        ]:
            val = getattr(self, attr)
            if not isinstance(val, Decimal) or val < 0:
                raise ValueError(
                    f"Configuration error: {attr} must be a non-negative Decimal. Current: {val}"
                )

        # Validate integer fields
        for attr in [
            "LOOKBACK_PERIODS",
            "ST_PERIOD_BASE",
            "ADX_MIN_THRESHOLD",
            "ADX_WINDOW",
            "RSI_WINDOW",
            "RSI_OVERSOLD",
            "RSI_OVERBOUGHT",
            "MACD_FAST",
            "MACD_SLOW",
            "MACD_SIGNAL",
            "ORDER_BOOK_DEPTH_LEVELS",
            "MAX_DAILY_TRADES",
            "MAX_CONSECUTIVE_LOSSES",
            "SAVE_STATE_INTERVAL",
            "MAX_API_RETRIES",
            "API_RETRY_DELAY_SEC",
            "POSITION_IDX",
        ]:
            val = getattr(self, attr)
            if not isinstance(val, int) or val < 0:
                raise ValueError(
                    f"Configuration error: {attr} must be a non-negative integer. Current: {val}"
                )

        # Sort partial TP targets by profit percentage
        self.PARTIAL_TP_TARGETS.sort(key=lambda x: x["profit_pct"])
        if not self.PARTIAL_TP_TARGETS:
            # Provide a default partial TP if none configured
            self.PARTIAL_TP_TARGETS = [
                {"profit_pct": Decimal("1.0"), "close_qty_pct": Decimal("0.5")}
            ]

        # Ensure leverage is 1 for SPOT, and warn if it was set otherwise
        if self.CATEGORY_ENUM == Category.SPOT and Decimal("1") != self.LEVERAGE:
            print(
                f"WARNING: Leverage is not applicable for SPOT category. Setting LEVERAGE to 1 for {self.SYMBOL}."
            )
            self.LEVERAGE = Decimal("1")

        # Validate positionIdx based on mode
        if self.HEDGE_MODE:
            if self.POSITION_IDX not in [1, 2]:
                raise ValueError(
                    f"Invalid BYBIT_POSITION_IDX '{self.POSITION_IDX}' for Hedge Mode. Must be 1 (Long) or 2 (Short)."
                )
        elif self.POSITION_IDX != 0:
            raise ValueError(
                f"Invalid BYBIT_POSITION_IDX '{self.POSITION_IDX}' for One-Way Mode. Must be 0."
            )


# =====================================================================
# DATA STRUCTURES
# =====================================================================


@dataclass
class MarketData:
    """Real-time market data container for a specific timeframe.

    Holds OHLCV data, bid/ask prices, spread, order book imbalance, and VWAP
    for a given market symbol and timeframe.
    """

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: Decimal = Decimal("0")
    bid: Decimal = Decimal("0")
    ask: Decimal = Decimal("0")
    spread_pct: Decimal = Decimal("0")
    order_book_imbalance: Decimal = Decimal("0")
    vwap: Decimal = Decimal("0")
    poc: Decimal = Decimal("0")  # Point of Control


@dataclass
class Position:
    """Active position information.

    Tracks details of an open trade, including symbol, side, size, entry price,
    current price, PnL, stop loss, take profit, and status flags for breakeven,
    trailing stops, and partial closes.
    """

    symbol: str
    side: str  # "Buy" or "Sell"
    size: Decimal  # Quantity
    entry_price: Decimal
    current_price: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    stop_loss: Decimal = Decimal("0")
    take_profit: Decimal = Decimal("0")
    breakeven_activated: bool = False
    trailing_sl_activated: bool = False
    partial_closes: list[dict[str, Decimal]] = field(
        default_factory=list
    )  # [{'profit_pct': Decimal, 'closed_qty': Decimal}]
    entry_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    order_id: str | None = None  # Bybit order ID for the entry order

    @property
    def pnl_pct(self) -> Decimal:
        """Calculates the unrealized profit or loss as a percentage."""
        if self.entry_price == Decimal("0"):
            return Decimal("0")
        if self.side == "Buy":
            return (
                (self.current_price - self.entry_price) / self.entry_price
            ) * Decimal("100")
        else:  # Sell
            return (
                (self.entry_price - self.current_price) / self.entry_price
            ) * Decimal("100")

    @property
    def duration(self) -> timedelta:
        """Calculates the duration the position has been open."""
        return datetime.now(timezone.utc) - self.entry_time


@dataclass
class Trade:
    """Completed trade record.

    Stores details of a closed trade, including symbol, side, entry/exit prices,
    size, PnL, duration, exit reason, and fees.
    """

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
    fees: Decimal = Decimal("0")


@dataclass
class PerformanceMetrics:
    """Performance tracking metrics.

    Aggregates statistics for trading performance, including total trades,
    win/loss counts, PnL, win rate, profit factor, drawdown, streaks, and
    average trade statistics. Also tracks daily performance and historical returns
    for potential Sharpe ratio calculations.
    """

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")

    # Streak tracking
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # Statistics
    win_rate: Decimal = Decimal("0")
    profit_factor: Decimal = Decimal("0")

    # Drawdown
    max_drawdown: Decimal = Decimal("0")  # %
    current_drawdown: Decimal = Decimal("0")  # %
    peak_balance: Decimal = Decimal("0")

    # Trade statistics
    avg_win_pct: Decimal = Decimal("0")
    avg_loss_pct: Decimal = Decimal("0")
    avg_trade_duration: timedelta = timedelta()
    best_trade_pct: Decimal = Decimal("0")
    worst_trade_pct: Decimal = Decimal("0")

    # Daily tracking
    daily_pnl: dict[str, Decimal] = field(default_factory=dict)  # Date -> PnL
    daily_trades: dict[str, int] = field(default_factory=dict)  # Date -> Trade Count

    # For Kelly Criterion and Sharpe Ratio
    historical_returns_pct: list[Decimal] = field(
        default_factory=list
    )  # Percentage returns per trade

    def update(self, trade: Trade, current_balance: Decimal):
        """Update metrics with a new completed trade."""
        self.total_trades += 1
        self.total_pnl += trade.pnl
        self.total_fees += trade.fees
        self.historical_returns_pct.append(trade.pnl_pct)

        # Track daily stats
        today = trade.exit_time.strftime("%Y-%m-%d")
        self.daily_pnl[today] = self.daily_pnl.get(today, Decimal("0")) + trade.pnl
        self.daily_trades[today] = self.daily_trades.get(today, 0) + 1

        # Update win/loss stats
        if trade.pnl > Decimal("0"):
            self.winning_trades += 1
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            self.max_consecutive_wins = max(
                self.max_consecutive_wins, self.consecutive_wins
            )
            self.best_trade_pct = max(self.best_trade_pct, trade.pnl_pct)
        else:
            self.losing_trades += 1
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            self.max_consecutive_losses = max(
                self.max_consecutive_losses, self.consecutive_losses
            )
            self.worst_trade_pct = min(self.worst_trade_pct, trade.pnl_pct)

        # Recalculate averages for win/loss PnL %
        winning_pnl_pcts = [r for r in self.historical_returns_pct if r > Decimal("0")]
        losing_pnl_pcts = [r for r in self.historical_returns_pct if r < Decimal("0")]

        self.avg_win_pct = (
            sum(winning_pnl_pcts) / len(winning_pnl_pcts)
            if winning_pnl_pcts
            else Decimal("0")
        )
        self.avg_loss_pct = (
            sum(losing_pnl_pcts) / len(losing_pnl_pcts)
            if losing_pnl_pcts
            else Decimal("0")
        )

        # Update ratios
        self.win_rate = (
            Decimal(self.winning_trades) / Decimal(self.total_trades)
            if self.total_trades > 0
            else Decimal("0")
        )

        if self.avg_loss_pct != Decimal("0"):
            # Profit Factor = (Gross Profit) / (Gross Loss)
            gross_profit = sum(
                pnl for pnl in self.historical_returns_pct if pnl > Decimal("0")
            )
            gross_loss = sum(
                pnl for pnl in self.historical_returns_pct if pnl < Decimal("0")
            )
            if gross_loss != Decimal("0"):
                self.profit_factor = abs(gross_profit / gross_loss)
            else:
                self.profit_factor = (
                    Decimal("inf") if gross_profit > Decimal("0") else Decimal("0")
                )  # Infinite if no losses
        else:
            self.profit_factor = (
                Decimal("inf") if self.winning_trades > 0 else Decimal("0")
            )  # Infinite if no losses

        # Update average duration
        self.avg_trade_duration = (
            (self.avg_trade_duration * (self.total_trades - 1) + trade.duration)
            / self.total_trades
            if self.total_trades > 0
            else timedelta()
        )

        # Update Drawdown
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
            self.current_drawdown = Decimal("0")
        else:
            self.current_drawdown = (
                (self.peak_balance - current_balance) / self.peak_balance
            ) * Decimal("100")
            self.max_drawdown = max(self.max_drawdown, self.current_drawdown)

    def calculate_sharpe_ratio(self, risk_free_rate: Decimal = Decimal("0")) -> Decimal:
        """Calculate Sharpe ratio from historical returns.

        Uses daily percentage returns for calculation.
        """
        if len(self.daily_pnl) < 2:
            return Decimal("0")

        # Convert daily PnL to daily percentage returns relative to daily_start_balance
        daily_pct_returns = []
        sorted_dates = sorted(self.daily_pnl.keys())
        for date_str in sorted_dates:
            # Need to store daily_start_balance per day or calculate from initial balance + prior PnL
            # For simplicity here, if current_balance is not passed, this becomes tricky.
            # Let's assume daily_start_balance for the first day of operation, and for subsequent days,
            # it's the previous day's closing balance. This needs proper state management for 'daily_start_balance'.
            # For now, we will use total PnL of the day divided by initial balance as proxy.
            # A more accurate Sharpe requires proper daily equity curve.
            if (
                self.peak_balance > 0
            ):  # Use peak_balance as a base for daily returns if not tracked specifically
                daily_pct_returns.append(
                    (self.daily_pnl[date_str] / self.peak_balance) * Decimal("100")
                )
            else:
                daily_pct_returns.append(Decimal("0"))

        if not daily_pct_returns or len(daily_pct_returns) < 2:
            return Decimal("0")

        # Convert to float for numpy calculations (Sharpe is often calculated using floats)
        daily_returns_float = np.array([float(r) for r in daily_pct_returns])

        avg_return = np.mean(daily_returns_float)
        std_dev = np.std(daily_returns_float)

        if std_dev == 0:
            return Decimal("0")

        # Annualize (assuming 252 trading days for daily returns)
        annualized_sharpe = (
            (Decimal(str(avg_return)) - risk_free_rate)
            / Decimal(str(std_dev))
            * Decimal(str(np.sqrt(252)))
        )
        return annualized_sharpe

    def calculate_kelly_fraction(
        self, kelly_fraction_cap: Decimal = Decimal("1.0")
    ) -> Decimal:
        """Calculate optimal Kelly Criterion fraction.

        Requires sufficient historical data (at least 10 trades) to be meaningful.
        """
        if (
            self.winning_trades == 0
            or self.losing_trades == 0
            or self.total_trades < 10
        ):
            return Decimal("0")

        p = self.win_rate
        q = Decimal("1") - p

        if p == Decimal("0") or q == Decimal("0"):  # Avoid division by zero
            return Decimal("0")

        # Average win and average loss as fractions (not percentages)
        W = self.avg_win_pct / Decimal("100")
        L = abs(self.avg_loss_pct / Decimal("100"))

        if Decimal("0") == W or Decimal("0") == L:  # Avoid division by zero
            return Decimal("0")

        # Kelly formula (simplified for win rate and average win/loss ratio)
        # f = p - (q / (b)) where b is win/loss ratio
        # More robust: f = (p * R - q) / R, where R = W/L (average profit/average loss)
        R = W / L
        kelly_f = (p * R - q) / R if R > 0 else Decimal("0")

        return max(Decimal("0"), min(kelly_f, kelly_fraction_cap))


@dataclass
class BotState:
    """Enhanced thread-safe state manager for the bot.

    This dataclass holds all the dynamic state of the bot, including its status,
    market data, indicator values, current position, performance metrics,
    trade history, and logs. It uses a threading.RLock for thread-safe access
    to its attributes, ensuring data integrity across concurrent operations.
    """

    # System
    symbol: str
    bot_status: str = "Initializing"
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    errors_count: int = 0
    last_error: str | None = None
    stop_requested: bool = False  # New flag for graceful shutdown

    # Market data
    market_regime: MarketRegime = MarketRegime.UNKNOWN
    current_price: Decimal = Decimal("0")
    price_direction: int = 0  # 1=up, -1=down, 0=neutral from last tick
    market_data: dict[str, MarketData] = field(default_factory=dict)  # TF -> MarketData

    # Indicators
    supertrend_direction: str = "Neutral"  # From primary TF
    supertrend_line: Decimal | None = None  # From primary TF
    indicator_values: dict[str, Any] = field(
        default_factory=dict
    )  # Primary TF indicators
    signal_strength: Decimal = Decimal("0")  # Combined signal confidence
    last_signal: Signal | None = None
    last_signal_time: datetime | None = None
    last_signal_reason: str = "N/A"

    # Position
    position: Position | None = None
    pending_orders: list[dict] = field(
        default_factory=list
    )  # List of active pending orders

    # Performance
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    account_balance: Decimal = Decimal("0")
    initial_balance: Decimal = Decimal("0")  # Balance at bot start
    daily_start_balance: Decimal = Decimal("0")  # Balance at start of current day

    # Logging
    log_messages: deque[str] = field(
        default_factory=lambda: deque(maxlen=20)
    )  # Buffer for UI logs
    trade_history: list[Trade] = field(default_factory=list)

    # Thread safety
    lock: threading.RLock = field(
        default_factory=threading.RLock, compare=False
    )  # Exclude lock from comparison and hashing

    def __post_init__(self):
        # Initialize market_data for primary timeframe
        self.market_data[self.symbol] = MarketData()  # Placeholder

    def update(self, **kwargs):
        """Thread-safe state update."""
        with self.lock:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)

    def add_log(self, message: str, level: str = "INFO"):
        """Add a log message to the UI buffer."""
        with self.lock:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_messages.append(f"{timestamp} [{level}] {message}")

    def save_state(self, filepath: str):
        """Save current state to file."""
        try:
            with self.lock:
                # Only save essential, non-ephemeral state
                state_to_save = {
                    "metrics": self.metrics,
                    "trade_history": self.trade_history,
                    "initial_balance": self.initial_balance,
                    "daily_start_balance": self.daily_start_balance,
                }
                with open(filepath, "wb") as f:
                    pickle.dump(state_to_save, f)
                self.add_log(f"Bot state saved to {filepath}", "INFO")
        except Exception as e:
            self.add_log(f"Failed to save state: {e}", "ERROR")

    def load_state(self, filepath: str) -> bool:
        """Load state from file."""
        try:
            if Path(filepath).exists():
                with open(filepath, "rb") as f:
                    state_dict = pickle.load(f)
                    with self.lock:
                        self.metrics = state_dict.get("metrics", PerformanceMetrics())
                        self.trade_history = state_dict.get("trade_history", [])
                        self.initial_balance = state_dict.get(
                            "initial_balance", Decimal("0")
                        )
                        self.daily_start_balance = state_dict.get(
                            "daily_start_balance", Decimal("0")
                        )
                        # If a new day has started, reset daily_start_balance for current day
                        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        if today_str not in self.metrics.daily_pnl:
                            self.daily_start_balance = (
                                self.account_balance
                            )  # This will be updated by get_account_balance
                            self.metrics.daily_pnl[today_str] = Decimal("0")
                            self.metrics.daily_trades[today_str] = 0
                self.add_log(f"Bot state loaded from {filepath}", "INFO")
                return True
        except Exception as e:
            self.add_log(f"Failed to load state: {e}", "ERROR")
        return False


# =====================================================================
# ENHANCED UI
# =====================================================================


class EnhancedUI(threading.Thread):
    """Advanced terminal UI with comprehensive display.

    This class runs in a separate thread to render real-time bot status,
    market data, indicators, position details, performance metrics, and logs
    to the terminal in a visually organized manner.
    """

    def __init__(self, state: BotState, config: EnhancedConfig):
        super().__init__(daemon=True, name="EnhancedUI")
        self.state = state
        self.config = config
        self._stop_event = threading.Event()
        self.last_render_time = time.time()
        self.render_interval = 1  # seconds

    def stop(self):
        """Signals the UI thread to stop."""
        self._stop_event.set()

    def run(self):
        """The main loop for rendering the UI."""
        while not self._stop_event.is_set():
            if time.time() - self.last_render_time >= self.render_interval:
                self.display()
                self.last_render_time = time.time()
            time.sleep(0.1)  # Small sleep to avoid busy-waiting

    def display(self):
        """Renders the entire UI to the terminal."""
        with self.state.lock:
            os.system("cls" if os.name == "nt" else "clear")

            self._display_header()
            self._display_market_overview()
            self._display_indicators()
            self._display_position()
            self._display_performance()
            self._display_logs()
            self._display_footer()

    def _display_header(self):
        """Displays the bot's header information."""
        print(Style.BRIGHT + Fore.CYAN + "=" * 80 + Style.RESET_ALL)
        status_color = (
            Fore.GREEN
            if "Live" in self.state.bot_status
            else Fore.YELLOW
            if "Analyzing" in self.state.bot_status
            else Fore.RED
        )
        print(
            Style.BRIGHT
            + Fore.CYAN
            + f"    ADVANCED SUPERTREND BOT v2.0 | {self.state.symbol} | Status: {status_color}{self.state.bot_status}{Style.RESET_ALL}"
        )
        print(Style.BRIGHT + Fore.CYAN + "=" * 80 + Style.RESET_ALL)

    def _display_market_overview(self):
        """Displays current market price, spread, volume, and regime."""
        print(Style.BRIGHT + "\n📊 MARKET OVERVIEW" + Style.RESET_ALL)
        print("-" * 40)

        # Price
        price_color = (
            Fore.GREEN
            if self.state.price_direction == 1
            else Fore.RED
            if self.state.price_direction == -1
            else Fore.WHITE
        )
        arrow = (
            "↑"
            if self.state.price_direction == 1
            else "↓"
            if self.state.price_direction == -1
            else "→"
        )
        print(
            f"Current Price: {price_color}{self.state.current_price:.4f} {arrow}{Style.RESET_ALL}"
        )

        # Market data from primary timeframe
        primary_tf_data = self.state.market_data.get(self.config.PRIMARY_TIMEFRAME)
        if primary_tf_data:
            if primary_tf_data.bid > 0 and primary_tf_data.ask > 0:
                print(
                    f"Bid/Ask: {primary_tf_data.bid:.4f} / {primary_tf_data.ask:.4f} (Spread: {primary_tf_data.spread_pct:.3f}%)"
                )
            if primary_tf_data.volume > 0:
                print(
                    f"Volume ({self.config.PRIMARY_TIMEFRAME}): {primary_tf_data.volume:,.0f}"
                )
            if primary_tf_data.order_book_imbalance != Decimal("0"):
                imb_color = (
                    Fore.GREEN
                    if primary_tf_data.order_book_imbalance
                    > self.config.ORDER_BOOK_IMBALANCE_THRESHOLD
                    else Fore.RED
                    if primary_tf_data.order_book_imbalance
                    < -self.config.ORDER_BOOK_IMBALANCE_THRESHOLD
                    else Fore.YELLOW
                )
                print(
                    f"Order Book Imbalance: {imb_color}{primary_tf_data.order_book_imbalance:.2%}{Style.RESET_ALL}"
                )
            if primary_tf_data.vwap > 0:
                print(f"VWAP: {primary_tf_data.vwap:.4f}")
            if primary_tf_data.poc > 0:
                print(f"POC: {primary_tf_data.poc:.4f}")

        # Market regime
        regime_colors = {
            MarketRegime.TRENDING_UP: Fore.LIGHTGREEN_EX,
            MarketRegime.TRENDING_DOWN: Fore.LIGHTRED_EX,
            MarketRegime.RANGING: Fore.YELLOW,
            MarketRegime.VOLATILE: Fore.MAGENTA,
            MarketRegime.CALM: Fore.CYAN,
            MarketRegime.UNKNOWN: Fore.WHITE,
        }
        regime_color = regime_colors.get(self.state.market_regime, Fore.WHITE)
        print(
            f"Market Regime: {regime_color}{self.state.market_regime.value}{Style.RESET_ALL}"
        )

    def _display_indicators(self):
        """Displays current technical indicator values."""
        print(Style.BRIGHT + "\n📈 TECHNICAL INDICATORS" + Style.RESET_ALL)
        print("-" * 40)

        # SuperTrend
        st_color = (
            Fore.GREEN
            if self.state.supertrend_direction == "Uptrend"
            else Fore.RED
            if self.state.supertrend_direction == "Downtrend"
            else Fore.YELLOW
        )
        st_value = (
            f"{self.state.supertrend_line:.4f}"
            if self.state.supertrend_line
            else "Calculating..."
        )
        print(
            f"SuperTrend ({self.config.PRIMARY_TIMEFRAME}): {st_color}{self.state.supertrend_direction} @ {st_value}{Style.RESET_ALL}"
        )

        # Other indicators
        indicators = self.state.indicator_values
        if indicators:
            # RSI
            rsi = indicators.get("rsi")
            if rsi is not None and not pd.isna(rsi):
                rsi_color = (
                    Fore.RED
                    if rsi > self.config.RSI_OVERBOUGHT
                    else Fore.GREEN
                    if rsi < self.config.RSI_OVERSOLD
                    else Fore.YELLOW
                )
                print(
                    f"RSI({self.config.RSI_WINDOW}): {rsi_color}{rsi:.1f}{Style.RESET_ALL}",
                    end=" | ",
                )

            # ADX
            adx = indicators.get("adx")
            if adx is not None and not pd.isna(adx):
                adx_color = (
                    Fore.GREEN if adx > self.config.ADX_MIN_THRESHOLD else Fore.YELLOW
                )
                print(
                    f"ADX({self.config.ADX_WINDOW}): {adx_color}{adx:.1f}{Style.RESET_ALL}",
                    end=" | ",
                )

            # MACD
            macd = indicators.get("macd_hist")
            if macd is not None and not pd.isna(macd):
                macd_color = Fore.GREEN if macd > 0 else Fore.RED
                print(f"MACD Hist: {macd_color}{macd:.4f}{Style.RESET_ALL}")
            else:
                print()  # Newline if MACD not printed

            # Volume
            vol_ratio = indicators.get("volume_ratio")
            if vol_ratio is not None and not pd.isna(vol_ratio):
                vol_color = (
                    Fore.GREEN
                    if vol_ratio > self.config.VOLUME_MULTIPLIER
                    else Fore.YELLOW
                )
                print(
                    f"Volume Ratio: {vol_color}{vol_ratio:.2f}x{Style.RESET_ALL}",
                    end=" | ",
                )

            # Ehlers Filter
            ehlers_filter = indicators.get("ehlers_filter")
            if ehlers_filter is not None and not pd.isna(ehlers_filter):
                print(f"Ehlers Filter: {ehlers_filter:.4f}")
            else:
                print()  # Newline if Ehlers not printed

        # Signal strength
        if self.state.last_signal and self.state.last_signal != Signal.NEUTRAL:
            strength_color = (
                Fore.GREEN
                if self.state.signal_strength > Decimal("0.7")
                else Fore.YELLOW
                if self.state.signal_strength > Decimal("0.5")
                else Fore.RED
            )
            bars = "█" * int(self.state.signal_strength * 10)
            print(
                f"Signal Strength: {strength_color}{bars} {self.state.signal_strength:.1%}{Style.RESET_ALL}"
            )

        # Last signal
        if self.state.last_signal and self.state.last_signal_time:
            signal_age = (
                datetime.now(timezone.utc) - self.state.last_signal_time
            ).total_seconds()
            signal_color = (
                Fore.GREEN
                if self.state.last_signal.value > 0
                else Fore.RED
                if self.state.last_signal.value < 0
                else Fore.YELLOW
            )
            print(
                f"Last Signal: {signal_color}{self.state.last_signal.name}{Style.RESET_ALL} ({signal_age:.0f}s ago) - {self.state.last_signal_reason}"
            )

    def _display_position(self):
        """Displays details of the current active position, if any."""
        print(Style.BRIGHT + "\n💼 POSITION" + Style.RESET_ALL)
        print("-" * 40)

        if self.state.position:
            pos = self.state.position

            # Position details
            side_color = Fore.GREEN if pos.side == "Buy" else Fore.RED
            print(
                f"Side: {side_color}{pos.side}{Style.RESET_ALL} | Size: {pos.size:.4f}"
            )
            print(f"Entry: ${pos.entry_price:.4f} | Current: ${pos.current_price:.4f}")

            # PnL
            # Ensure unrealized_pnl is Decimal
            pos.unrealized_pnl = Decimal(str(pos.unrealized_pnl))
            pnl_color = Fore.GREEN if pos.unrealized_pnl >= Decimal("0") else Fore.RED
            pnl_pct_color = Fore.GREEN if pos.pnl_pct >= Decimal("0") else Fore.RED
            print(
                f"PnL: {pnl_color}${pos.unrealized_pnl:,.2f}{Style.RESET_ALL} "
                f"({pnl_pct_color}{pos.pnl_pct:+.2f}%{Style.RESET_ALL})"
            )

            # Risk levels
            print(f"SL: ${pos.stop_loss:.4f} | TP: ${pos.take_profit:.4f}")

            # Status flags
            flags = []
            if pos.breakeven_activated:
                flags.append(f"{Fore.LIGHTGREEN_EX}BREAKEVEN{Style.RESET_ALL}")
            if pos.trailing_sl_activated:
                flags.append(f"{Fore.CYAN}TRAILING{Style.RESET_ALL}")
            if pos.partial_closes:
                closed_qty_sum = sum(p["closed_qty"] for p in pos.partial_closes)
                closed_pct = (
                    (closed_qty_sum / (closed_qty_sum + pos.size)) * Decimal("100")
                    if (closed_qty_sum + pos.size) > 0
                    else Decimal("0")
                )
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
            if self.state.account_balance > Decimal("0"):
                balance_change = self.state.account_balance - self.state.initial_balance
                balance_color = (
                    Fore.GREEN if balance_change >= Decimal("0") else Fore.RED
                )
                print(
                    f"Account Balance: ${self.state.account_balance:,.2f} "
                    f"({balance_color}{balance_change:+.2f}{Style.RESET_ALL} total PnL)"
                )

                daily_change = (
                    self.state.account_balance - self.state.daily_start_balance
                )
                daily_color = Fore.GREEN if daily_change >= Decimal("0") else Fore.RED
                print(f"Daily PnL: {daily_color}{daily_change:+.2f}{Style.RESET_ALL}")

    def _display_performance(self):
        """Displays the bot's performance metrics."""
        print(Style.BRIGHT + "\n📊 PERFORMANCE METRICS" + Style.RESET_ALL)
        print("-" * 40)

        metrics = self.state.metrics

        # Win rate and trades
        if metrics.total_trades > 0:
            wr_color = (
                Fore.GREEN
                if metrics.win_rate >= Decimal("0.5")
                else Fore.YELLOW
                if metrics.win_rate >= Decimal("0.4")
                else Fore.RED
            )
            print(
                f"Win Rate: {wr_color}{metrics.win_rate:.1%}{Style.RESET_ALL} "
                f"({metrics.winning_trades}W/{metrics.losing_trades}L | Total: {metrics.total_trades})"
            )
        else:
            print("No trades yet.")
            return

        # Overall PnL
        total_color = (
            Fore.GREEN
            if metrics.total_pnl > Decimal("0")
            else Fore.RED
            if metrics.total_pnl < Decimal("0")
            else Fore.WHITE
        )
        print(
            f"Total PnL: {total_color}${metrics.total_pnl:,.2f}{Style.RESET_ALL} (Fees: ${metrics.total_fees:,.2f})"
        )

        # Key ratios
        if metrics.profit_factor != Decimal("0"):
            pf_color = (
                Fore.GREEN
                if metrics.profit_factor > Decimal("1.5")
                else Fore.YELLOW
                if metrics.profit_factor > Decimal("1")
                else Fore.RED
            )
            print(
                f"Profit Factor: {pf_color}{metrics.profit_factor:.2f}{Style.RESET_ALL}"
            )

        sharpe = metrics.calculate_sharpe_ratio()
        if sharpe != Decimal("0"):
            sharpe_color = (
                Fore.GREEN
                if sharpe > Decimal("1")
                else Fore.YELLOW
                if sharpe > Decimal("0")
                else Fore.RED
            )
            print(
                f"Sharpe Ratio (Annualized): {sharpe_color}{sharpe:.2f}{Style.RESET_ALL}"
            )

        # Drawdown
        if metrics.max_drawdown != Decimal("0"):
            dd_color = Fore.YELLOW if metrics.max_drawdown < Decimal("5") else Fore.RED
            print(
                f"Max Drawdown: {dd_color}{metrics.max_drawdown:.1f}%{Style.RESET_ALL}"
            )

        # Streaks
        if metrics.consecutive_wins > 0:
            print(
                f"Streak: {Fore.GREEN}↑{metrics.consecutive_wins} wins{Style.RESET_ALL} (Max: {metrics.max_consecutive_wins})"
            )
        elif metrics.consecutive_losses > 0:
            print(
                f"Streak: {Fore.RED}↓{metrics.consecutive_losses} losses{Style.RESET_ALL} (Max: {metrics.max_consecutive_losses})"
            )

        # Best/Worst trades
        if metrics.best_trade_pct != Decimal("0") or metrics.worst_trade_pct != Decimal(
            "0"
        ):
            print(
                f"Best/Worst: {Fore.LIGHTGREEN_EX}+{metrics.best_trade_pct:.1f}%{Style.RESET_ALL} / "
                f"{Fore.LIGHTRED_EX}{metrics.worst_trade_pct:.1f}%{Style.RESET_ALL}"
            )

        # Avg Win/Loss
        if metrics.avg_win_pct != Decimal("0") or metrics.avg_loss_pct != Decimal("0"):
            print(
                f"Avg Win/Loss: {Fore.LIGHTGREEN_EX}+{metrics.avg_win_pct:.1f}%{Style.RESET_ALL} / "
                f"{Fore.LIGHTRED_EX}{metrics.avg_loss_pct:.1f}%{Style.RESET_ALL}"
            )

        if (
            self.config.USE_KELLY_SIZING and metrics.total_trades > 10
        ):  # Only show if enough data
            kelly_f = metrics.calculate_kelly_fraction(self.config.KELLY_FRACTION_CAP)
            kelly_color = Fore.GREEN if kelly_f > 0 else Fore.YELLOW
            print(f"Kelly Fraction: {kelly_color}{kelly_f:.2%}{Style.RESET_ALL}")

    def _display_logs(self):
        """Displays the recent activity log messages."""
        print(Style.BRIGHT + "\n📝 RECENT ACTIVITY" + Style.RESET_ALL)
        print("-" * 40)

        for msg in list(self.state.log_messages):
            # Color code based on message content
            if "[ERROR]" in msg:
                print(Fore.RED + msg + Style.RESET_ALL)
            elif "[WARNING]" in msg:
                print(Fore.YELLOW + msg + Style.RESET_ALL)
            elif (
                "[SUCCESS]" in msg
                or "profit" in msg.lower()
                or "filled" in msg.lower()
                or "opened" in msg.lower()
            ):
                print(Fore.GREEN + msg + Style.RESET_ALL)
            else:
                print(msg)

    def _display_footer(self):
        """Displays the bot's footer information, including uptime and error count."""
        print(Style.BRIGHT + Fore.CYAN + "\n" + "=" * 80 + Style.RESET_ALL)

        # Running time
        uptime = datetime.now(timezone.utc) - self.state.start_time
        hours = uptime.total_seconds() // 3600
        minutes = (uptime.total_seconds() % 3600) // 60
        print(f"Uptime: {hours:.0f}h {minutes:.0f}m | ", end="")

        # Error count
        if self.state.errors_count > 0:
            print(
                f"{Fore.RED}Errors: {self.state.errors_count}{Style.RESET_ALL} | ",
                end="",
            )
        else:
            print("Errors: 0 | ", end="")

        print(Fore.YELLOW + "Press Ctrl+C to exit gracefully" + Style.RESET_ALL)


# =====================================================================
# LOGGING SETUP
# =====================================================================


def setup_logger(config: EnhancedConfig) -> logging.Logger:
    """Configures a logger with both console and file handlers.

    Sets up a logger instance with specified log level, console output
    and a rotating file handler for persistent logs.
    Clears existing handlers to prevent duplicates if called multiple times.
    """
    logger = logging.getLogger("SuperTrendBot")
    logger.setLevel(config.LOG_LEVEL.upper())

    # Clear existing handlers to prevent duplicate logs on reload
    if logger.hasHandlers():
        logger.handlers.clear()

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File Handler
    file_handler = logging.handlers.RotatingFileHandler(
        "bot_activity.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger


# =====================================================================
# MARKET ANALYSIS
# =====================================================================


class MarketAnalyzer:
    """Advanced market analysis and regime detection.

    Provides methods to analyze market conditions, including determining
    the market regime, calculating support/resistance levels, analyzing
    volume profiles, and assessing order book imbalances.
    """

    def __init__(self, config: EnhancedConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.regime_window = 50  # Number of candles for regime detection
        self.volatility_window = 20  # Number of candles for volatility

    def analyze_market_regime(self, df: pd.DataFrame) -> MarketRegime:
        """Determine current market regime using multiple factors.

        Analyzes trend strength (slope), volatility (ATR), and price position
        relative to moving averages (EMA 20/50) to classify the market into
        Trending Up, Trending Down, Ranging, Volatile, or Calm regimes.

        Args:
            df (pd.DataFrame): DataFrame containing historical OHLCV data and indicators.

        Returns:
            MarketRegime: The determined market regime.
        """
        if len(df) < self.regime_window:
            return MarketRegime.UNKNOWN

        # Ensure numeric types
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df.dropna(inplace=True)

        if len(df) < self.regime_window:  # Recheck after dropna
            return MarketRegime.UNKNOWN

        # Ensure 'close' is numeric
        close_prices_series = df["close"].iloc[-self.regime_window :]
        if close_prices_series.empty or not pd.api.types.is_numeric_dtype(
            close_prices_series
        ):
            return MarketRegime.UNKNOWN
        close_prices = close_prices_series.values

        # 1. Trend strength using linear regression (simplified without scipy)
        x = np.arange(len(close_prices))
        try:
            slope, _ = np.polyfit(x, close_prices.astype(float), 1)
        except np.linalg.LinAlgError:
            self.logger.warning(
                "LinAlgError during polyfit for market regime. Returning UNKNOWN."
            )
            return MarketRegime.UNKNOWN

        # A simple threshold for slope can indicate trend strength
        # Normalized slope relative to average price
        avg_price = np.mean(close_prices.astype(float))
        trend_strength_threshold_abs = Decimal("0.0005") * Decimal(
            str(avg_price)
        )  # e.g., 0.05% change over window

        # 2. Volatility using ATR
        if "atr" not in df.columns or df["atr"].iloc[-1] == 0:
            df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)
            df.dropna(subset=["atr"], inplace=True)
            if df["atr"].empty:
                return MarketRegime.UNKNOWN

        atr = Decimal(str(df["atr"].iloc[-1]))
        close_price_dec = Decimal(str(df["close"].iloc[-1]))
        atr_pct = (
            (atr / close_price_dec) * Decimal("100")
            if close_price_dec > Decimal("0")
            else Decimal("0")
        )

        # 3. Price position relative to moving averages (EMA 20 & 50)
        # Assuming EMA 20 and 50 are already calculated or can be calculated here
        if "ema_20" not in df.columns:
            df["ema_20"] = ta.ema(df["close"], length=20)
        if "ema_50" not in df.columns:
            df["ema_50"] = ta.ema(df["close"], length=50)
        df.dropna(subset=["ema_20", "ema_50"], inplace=True)
        if df["ema_20"].empty:
            return MarketRegime.UNKNOWN

        ema_20 = Decimal(str(df["ema_20"].iloc[-1]))
        ema_50 = Decimal(str(df["ema_50"].iloc[-1]))
        price = Decimal(str(df["close"].iloc[-1]))

        # Determine regime
        if atr_pct > Decimal("3.0"):  # High volatility
            return MarketRegime.VOLATILE
        elif atr_pct < Decimal("0.5"):  # Low volatility
            return MarketRegime.CALM
        elif (
            abs(Decimal(str(slope))) > trend_strength_threshold_abs
        ):  # Strong trend based on slope
            if slope > 0 and price > ema_20 and ema_20 > ema_50:
                return MarketRegime.TRENDING_UP
            elif slope < 0 and price < ema_20 and ema_20 < ema_50:
                return MarketRegime.TRENDING_DOWN

        # If not strongly trending or very volatile/calm, it's ranging
        return MarketRegime.RANGING

    def calculate_support_resistance(
        self, df: pd.DataFrame, window: int = 20
    ) -> dict[str, Decimal]:
        """Calculate dynamic support and resistance levels using Pivot Points and historical highs/lows.

        Args:
            df (pd.DataFrame): DataFrame containing historical OHLC data.
            window (int): The lookback period for calculating rolling highs/lows.

        Returns:
            dict[str, Decimal]: A dictionary containing support and resistance levels.
        """
        if len(df) < window:
            return {}

        # Ensure numeric types
        for col in ["high", "low", "close"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df.dropna(inplace=True)
        if len(df) < window:
            return {}

        # Rolling highs and lows
        recent_high = df["high"].iloc[-window:].max()
        recent_low = df["low"].iloc[-window:].min()

        # Classic Pivot Points
        last_high = Decimal(str(df["high"].iloc[-1]))
        last_low = Decimal(str(df["low"].iloc[-1]))
        last_close = Decimal(str(df["close"].iloc[-1]))

        pivot = (last_high + last_low + last_close) / 3

        return {
            "resistance_recent": Decimal(str(recent_high)),
            "support_recent": Decimal(str(recent_low)),
            "pivot": pivot,
            "r1": (2 * pivot - last_low),
            "s1": (2 * pivot - last_high),
        }

    def analyze_volume_profile(
        self, df: pd.DataFrame, bins: int = 20
    ) -> dict[str, Any]:
        """Analyze volume distribution across price levels (simplified for candle data).

        Calculates the Point of Control (POC) and Volume Weighted Average Price (VWAP)
        by binning the volume across price ranges.

        Args:
            df (pd.DataFrame): DataFrame containing historical close prices and volumes.
            bins (int): The number of price bins to use for the volume profile.

        Returns:
            dict[str, Any]: A dictionary containing the volume profile, POC, and VWAP.
        """
        if len(df) < bins:
            return {"poc": Decimal("0"), "vwap": Decimal("0"), "volume_profile": {}}

        # Ensure numeric types
        for col in ["close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df.dropna(inplace=True)
        if len(df) < bins:
            return {"poc": Decimal("0"), "vwap": Decimal("0"), "volume_profile": {}}

        # Calculate VWAP
        total_volume = Decimal(str(df["volume"].sum()))
        vwap = (
            (Decimal(str((df["close"] * df["volume"]).sum())) / total_volume)
            if total_volume > Decimal("0")
            else Decimal(str(df["close"].iloc[-1]))
        )

        # Create price bins and sum volume
        min_price = Decimal(str(df["close"].min()))
        max_price = Decimal(str(df["close"].max()))

        if max_price == min_price:  # Handle flat market
            return {
                "poc": min_price,
                "vwap": vwap,
                "volume_profile": {f"{min_price:.4f}-{max_price:.4f}": total_volume},
            }

        bin_edges = np.linspace(float(min_price), float(max_price), bins + 1)
        volume_bins_dict = defaultdict(Decimal)

        for _, row in df.iterrows():
            price_val = float(Decimal(str(row["close"])))
            volume_val = Decimal(str(row["volume"]))

            # Find which bin the price falls into
            for i in range(bins):
                if bin_edges[i] <= price_val < bin_edges[i + 1]:
                    volume_bins_dict[f"{bin_edges[i]:.4f}-{bin_edges[i + 1]:.4f}"] += (
                        volume_val
                    )
                    break
            # Edge case for max price
            if (
                price_val == float(max_price) and bins > 0
            ):  # Ensure bins exist for max_price case
                volume_bins_dict[
                    f"{bin_edges[bins - 1]:.4f}-{bin_edges[bins]:.4f}"
                ] += volume_val

        # Find POC (Point of Control - price level with highest volume)
        poc_price = Decimal("0")
        if volume_bins_dict:
            poc_range_str = max(volume_bins_dict, key=volume_bins_dict.get)
            if poc_range_str:
                try:
                    lower_bound, upper_bound = map(Decimal, poc_range_str.split("-"))
                    poc_price = (lower_bound + upper_bound) / 2
                except InvalidOperation:
                    self.logger.warning(
                        f"Failed to parse POC range string: {poc_range_str}"
                    )
                    poc_price = Decimal("0")  # Default to 0 on error
            else:
                self.logger.warning("POC range string is empty.")
        else:
            self.logger.warning("Volume bins dictionary is empty.")

        return {"volume_profile": volume_bins_dict, "poc": poc_price, "vwap": vwap}

    def analyze_order_book_imbalance(
        self, bids: list[list[str]], asks: list[list[str]], depth: int
    ) -> Decimal:
        """Calculates order book imbalance for a given depth.

        Imbalance is calculated as (Total Bid Volume - Total Ask Volume) / (Total Bid Volume + Total Ask Volume).

        Args:
            bids (list[list[str]]): List of bid orders, each with price and size as strings.
            asks (list[list[str]]): List of ask orders, each with price and size as strings.
            depth (int): The number of levels to consider from the top of the order book.

        Returns:
            Decimal: The calculated order book imbalance.
        """
        if not bids or not asks:
            return Decimal("0")

        bid_volume = sum(Decimal(b[1]) for b in bids[:depth])
        ask_volume = sum(Decimal(a[1]) for a in asks[:depth])

        total_volume = bid_volume + ask_volume
        if total_volume == Decimal("0"):
            return Decimal("0")

        imbalance = (bid_volume - ask_volume) / total_volume
        return imbalance


# =====================================================================
# TECHNICAL INDICATORS
# =====================================================================


class IndicatorCalculator:
    """Advanced technical indicator calculations.

    Provides methods to calculate various technical indicators, including
    custom implementations like the Ehlers Filter and adaptive SuperTrend,
    as well as standard indicators using pandas_ta.
    """

    def __init__(self, config: EnhancedConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger

    def calculate_ehlers_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates the Ehlers Filter (a low-lag, adaptive moving average).

        This is a custom implementation based on Ehlers' filter coefficients.
        It aims to provide a smoother, more responsive average compared to traditional MAs.

        Args:
            df (pd.DataFrame): DataFrame containing at least 'close' prices.

        Returns:
            pd.DataFrame: The input DataFrame with an added 'ehlers_filter' column.
        """
        if df.empty or len(df) < 2:
            df["ehlers_filter"] = (
                np.nan
            )  # Or df['close'] if you prefer to fill for small data
            return df

        # Ensure numeric types
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df.dropna(subset=["close"], inplace=True)
        if df.empty:
            df["ehlers_filter"] = np.nan
            return df

        # Constants for a 10-period Ehlers Filter (approx 10-bar cycle)
        # These coefficients are from a specific Ehlers filter implementation.
        # For a truly adaptive Ehlers filter, the alpha/beta values would change based on dominant cycle.
        # For simplicity and consistency, we use fixed parameters here.
        a1 = np.exp(-np.pi * np.sqrt(2) / 10)
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / 10)
        c2, c3 = b1, -a1 * a1
        c1 = 1 - b1 + a1 * a1

        filt = np.zeros(len(df.close))

        # Handle initial values
        if len(df.close) > 0:
            filt[0] = df.close.iloc[0]
        if len(df.close) > 1:
            filt[1] = (c1 * (df.close.iloc[1] + df.close.iloc[0]) / 2.0) + (
                c2 * filt[0]
            )

        # Apply filter for subsequent values
        for i in range(2, len(df.close)):
            filt[i] = (
                c1 * (df.close.iloc[i] + df.close.iloc[i - 1]) / 2.0
                + c2 * filt[i - 1]
                + c3 * filt[i - 2]
            )

        df["ehlers_filter"] = filt
        return df

    def calculate_adaptive_supertrend(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate SuperTrend with adaptive parameters based on volatility.

        Adjusts the SuperTrend period and multiplier based on current market volatility
        (measured by ATR percentage) to make the indicator more responsive in volatile
        markets and less sensitive in calm markets.

        Args:
            df (pd.DataFrame): DataFrame containing OHLCV data and ATR.

        Returns:
            pd.DataFrame: The input DataFrame with 'supertrend_line' and 'supertrend_direction' columns.
        """
        if df.empty or len(df) < max(
            self.config.ST_PERIOD_BASE, 14
        ):  # Need enough data for ATR
            df["supertrend_line"] = np.nan
            df["supertrend_direction"] = np.nan
            return df

        # Ensure numeric types
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df.dropna(subset=["high", "low", "close"], inplace=True)
        if df.empty:
            df["supertrend_line"] = np.nan
            df["supertrend_direction"] = np.nan
            return df

        # Calculate volatility using ATR as a proxy
        if "atr" not in df.columns or df["atr"].isnull().all():
            df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)
            df.dropna(subset=["atr"], inplace=True)
            if df.empty:
                df["supertrend_line"] = np.nan
                df["supertrend_direction"] = np.nan
                return df

        # Percentage ATR to normalize volatility
        atr_val = df["atr"].iloc[-1]
        close_val = df["close"].iloc[-1]
        atr_pct = (atr_val / close_val) * 100 if close_val > 0 else 0

        period = self.config.ST_PERIOD_BASE
        multiplier = float(self.config.ST_MULTIPLIER_BASE)

        if self.config.ADAPTIVE_PARAMS:
            if atr_pct < 0.5:  # Very low volatility (calm market)
                period = min(
                    self.config.ST_PERIOD_BASE + 5, 20
                )  # Increase period, reduce sensitivity
                multiplier = max(float(self.config.ST_MULTIPLIER_BASE) - 0.5, 1.5)
                self.logger.debug(
                    f"Adaptive ST: Low volatility. Period={period}, Multiplier={multiplier:.1f}"
                )
            elif atr_pct > 2.0:  # High volatility (volatile market)
                period = max(
                    self.config.ST_PERIOD_BASE - 3, 7
                )  # Decrease period, increase sensitivity
                multiplier = min(float(self.config.ST_MULTIPLIER_BASE) + 0.5, 4.0)
                self.logger.debug(
                    f"Adaptive ST: High volatility. Period={period}, Multiplier={multiplier:.1f}"
                )
            else:
                self.logger.debug(
                    f"Adaptive ST: Moderate volatility. Period={period}, Multiplier={multiplier:.1f}"
                )

        # Calculate SuperTrend using pandas_ta
        # Note: pandas_ta appends columns with names like SUPERT_LENGTH_MULTIPLIER
        ta.supertrend(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            length=period,
            multiplier=multiplier,
            append=True,
            df=df,
        )

        # Rename columns for consistency
        st_col_base = (
            f"SUPERT_{period}_{multiplier:.1f}"  # .1f for multiplier as it's a float
        )
        st_col = f"{st_col_base}"
        st_dir_col = f"{st_col_base}d"

        if st_col in df.columns and st_dir_col in df.columns:
            df["supertrend_line"] = df[st_col]
            df["supertrend_direction"] = df[st_dir_col]
            # Drop the original pandas_ta generated columns
            df.drop(
                [c for c in df.columns if c.startswith(st_col_base)],
                axis=1,
                inplace=True,
                errors="ignore",
            )
        else:
            self.logger.warning(
                f"SuperTrend columns {st_col}, {st_dir_col} not found in DataFrame. Check pandas_ta version or parameters."
            )
            df["supertrend_line"] = np.nan
            df["supertrend_direction"] = np.nan

        return df

    def calculate_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate comprehensive set of technical indicators.

        Applies a wide range of indicators including Ehlers Filter, SuperTrend,
        EMAs, MACD, Stochastic, Bollinger Bands, ADX, and volume-based indicators.

        Args:
            df (pd.DataFrame): DataFrame containing OHLCV data.

        Returns:
            pd.DataFrame: The input DataFrame with added indicator columns.
        """
        if df.empty:
            return df

        # Ensure we have float data for calculations
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.dropna(subset=["open", "high", "low", "close", "volume"], inplace=True)
        if df.empty:
            return df

        # Ehlers Filter (custom implementation)
        df = self.calculate_ehlers_filter(df)

        # Trend Indicators
        df = self.calculate_adaptive_supertrend(df)  # Includes ATR for adaptive logic
        df["ema_9"] = ta.ema(df["close"], length=9)
        df["ema_20"] = ta.ema(df["close"], length=20)
        df["ema_50"] = ta.ema(df["close"], length=50)
        df["sma_200"] = ta.sma(df["close"], length=200)

        # Momentum Indicators
        if self.config.RSI_FILTER:
            df["rsi"] = ta.rsi(df["close"], length=self.config.RSI_WINDOW)
        if self.config.MACD_FILTER:
            macd_results = ta.macd(
                df["close"],
                fast=self.config.MACD_FAST,
                slow=self.config.MACD_SLOW,
                signal=self.config.MACD_SIGNAL,
                append=True,
            )
            if macd_results is not None and not macd_results.empty:
                # Rename columns from pandas_ta to generic names if they exist
                macd_cols = [col for col in df.columns if col.startswith("MACD_")]
                if macd_cols:
                    df["macd"] = df[macd_cols[0]] if len(macd_cols) > 0 else np.nan
                    df["macd_signal"] = (
                        df[macd_cols[1]] if len(macd_cols) > 1 else np.nan
                    )
                    df["macd_hist"] = df[macd_cols[2]] if len(macd_cols) > 2 else np.nan
            else:
                df["macd"] = np.nan
                df["macd_signal"] = np.nan
                df["macd_hist"] = np.nan

        # Stochastic
        stoch_results = ta.stoch(df["high"], df["low"], df["close"], append=True)
        if stoch_results is not None and not stoch_results.empty:
            stoch_k_col = next((c for c in df.columns if c.startswith("STOCHk_")), None)
            stoch_d_col = next((c for c in df.columns if c.startswith("STOCHd_")), None)
            df["stoch_k"] = df[stoch_k_col] if stoch_k_col else np.nan
            df["stoch_d"] = df[stoch_d_col] if stoch_d_col else np.nan
        else:
            df["stoch_k"] = np.nan
            df["stoch_d"] = np.nan

        # Volatility Indicators (ATR already calculated in adaptive supertrend, BBANDS still useful)
        bb_results = ta.bbands(df["close"], append=True)
        if bb_results is not None and not bb_results.empty:
            bb_cols = [
                c
                for c in df.columns
                if c.startswith("BBU_") or c.startswith("BBM_") or c.startswith("BBL_")
            ]
            if bb_cols:
                df["bb_upper"] = df[next(c for c in bb_cols if c.startswith("BBU_"))]
                df["bb_middle"] = df[next(c for c in bb_cols if c.startswith("BBM_"))]
                df["bb_lower"] = df[next(c for c in bb_cols if c.startswith("BBL_"))]
                df["bb_width"] = df["bb_upper"] - df["bb_lower"]
                df["bb_position"] = (df["close"] - df["bb_lower"]) / (
                    df["bb_upper"] - df["bb_lower"]
                )
        else:
            df["bb_upper"] = np.nan
            df["bb_middle"] = np.nan
            df["bb_lower"] = np.nan
            df["bb_width"] = np.nan
            df["bb_position"] = np.nan

        # Volume Indicators
        df["volume_sma"] = ta.sma(df["volume"], length=20)
        df["volume_ratio"] = (
            df["volume"] / df["volume_sma"] if df["volume_sma"].iloc[-1] > 0 else 0
        )
        df["obv"] = ta.obv(df["close"], df["volume"])

        # Trend Strength
        if self.config.ADX_TREND_FILTER:
            adx_results = ta.adx(
                df["high"],
                df["low"],
                df["close"],
                length=self.config.ADX_WINDOW,
                append=True,
            )
            if adx_results is not None and not adx_results.empty:
                adx_col = next((c for c in df.columns if c.startswith("ADX_")), None)
                dmp_col = next((c for c in df.columns if c.startswith("DMP_")), None)
                dmn_col = next((c for c in df.columns if c.startswith("DMN_")), None)
                df["adx"] = df[adx_col] if adx_col else np.nan
                df["dmp"] = df[dmp_col] if dmp_col else np.nan
                df["dmn"] = df[dmn_col] if dmn_col else np.nan
            else:
                df["adx"] = np.nan
                df["dmp"] = np.nan
                df["dmn"] = np.nan

        # Custom calculations
        df["hl2"] = (df["high"] + df["low"]) / 2
        df["hlc3"] = (df["high"] + df["low"] + df["close"]) / 3
        df["ohlc4"] = (df["open"] + df["high"] + df["low"] + df["close"]) / 4

        # Price action
        df["body"] = abs(df["close"] - df["open"])
        df["upper_wick"] = df["high"] - df[["close", "open"]].max(axis=1)
        df["lower_wick"] = df[["close", "open"]].min(axis=1) - df["low"]

        return df.dropna().reset_index(
            drop=True
        )  # Drop any remaining NaNs from indicator calculations


# =====================================================================
# PRECISION & ORDER SIZING
# =====================================================================


@dataclass
class InstrumentSpecs:
    """Stores instrument specifications from Bybit.

    Contains details like tick size, quantity step, minimum/maximum order quantity,
    and minimum order value (for spot markets) required for precise order placement.
    """

    tick_size: Decimal
    qty_step: Decimal
    min_order_qty: Decimal
    max_order_qty: Decimal
    min_order_value: Decimal  # For SPOT, min quote order qty


class PrecisionManager:
    """Manages decimal precision for trading pairs.

    Fetches and stores instrument-specific specifications (tick size, quantity step)
    from the Bybit API to ensure all order prices and quantities are rounded correctly.
    """

    def __init__(self, session: HTTP, logger: logging.Logger, config: EnhancedConfig):
        self.session = session
        self.logger = logger
        self.config = config
        self.instruments: dict[str, InstrumentSpecs] = {}
        # Pre-load specs for the primary symbol at initialization
        self.get_specs(self.config.SYMBOL, self.config.CATEGORY)

    def get_specs(
        self, symbol: str, category: Category | str
    ) -> InstrumentSpecs | None:
        """Fetches or retrieves cached instrument specifications for a given symbol and category.

        Args:
            symbol (str): The trading symbol (e.g., "BTCUSDT").
            category (Category | str): The market category (e.g., Category.LINEAR, "spot").

        Returns:
            InstrumentSpecs | None: The instrument specifications if found, otherwise None.
        """
        category_str = category.value if isinstance(category, Category) else category
        if symbol in self.instruments:
            return self.instruments[symbol]

        try:
            # Use _api_call for resilience if it's available
            if hasattr(self.session, "_api_call"):
                response = self.session._api_call(
                    self.session.get_instruments_info,
                    category=category_str,
                    symbol=symbol,
                )
            else:
                response = self.session.get_instruments_info(
                    category=category_str, symbol=symbol
                )

            if response and response["retCode"] == 0:
                info_list = response["result"].get("list", [])
                if not info_list:
                    self.logger.warning(
                        f"No instrument info found for {symbol} in category {category_str}."
                    )
                    return None

                info = info_list[0]

                # Default values
                min_order_value = Decimal("0")
                max_order_qty = Decimal("999999999")  # Effectively unlimited

                # Safely extract from filters, providing defaults
                lot_size_filter = info.get("lotSizeFilter", {})
                price_filter = info.get("priceFilter", {})

                tick_size = Decimal(price_filter.get("tickSize", "0.00000001"))
                min_price = Decimal(price_filter.get("minPrice", "0"))
                max_price = Decimal(price_filter.get("maxPrice", "1e9"))

                if category_str == "spot":
                    min_order_qty = Decimal(lot_size_filter.get("baseMinTradeQty", "0"))
                    qty_step = Decimal(
                        lot_size_filter.get("baseTickSize", "0.00000001")
                    )
                    # min_order_value is usually for the quote currency in spot, so minNotional
                    min_order_value = Decimal(lot_size_filter.get("minNotional", "0"))
                    max_order_qty = Decimal(
                        lot_size_filter.get("baseMaxTradeQty", "1e9")
                    )
                else:  # Linear/Inverse/Option
                    min_order_qty = Decimal(lot_size_filter.get("minOrderQty", "0"))
                    qty_step = Decimal(lot_size_filter.get("qtyStep", "0.00000001"))
                    min_order_value = Decimal(
                        lot_size_filter.get("minOrderAmt", "0")
                    )  # min notional for derivatives
                    max_order_qty = Decimal(lot_size_filter.get("maxOrderQty", "1e9"))

                specs = InstrumentSpecs(
                    tick_size=tick_size,
                    qty_step=qty_step,
                    min_order_qty=min_order_qty,
                    max_order_qty=max_order_qty,
                    min_order_value=min_order_value,  # This can mean min_notional for spot, min_value for derivatives
                )
                self.instruments[symbol] = specs
                self.logger.info(
                    f"Fetched instrument specs for {symbol} ({category_str}): {specs}"
                )
                return specs
            else:
                error_msg = (
                    response.get("retMsg", "Unknown error")
                    if response
                    else "No response"
                )
                self.logger.error(
                    f"Failed to get instrument info for {symbol} ({category_str}): {error_msg}"
                )
        except Exception as e:
            self.logger.error(
                f"Error fetching instrument specs for {symbol} ({category_str}): {e}",
                exc_info=True,
            )
        return None

    def _round_decimal(self, value: Decimal, step: Decimal) -> Decimal:
        """Helper to round a Decimal to the nearest step, rounding down."""
        if step == Decimal("0"):
            return value

        # Quantize to the number of decimal places in the step itself
        quantize_format = Decimal("1E" + str(-step.as_tuple().exponent))
        # Use ROUND_DOWN to ensure we don't accidentally exceed limits
        rounded = (value / step).quantize(Decimal("1."), rounding=ROUND_DOWN) * step
        # Re-quantize to the original precision of the step to avoid floating point anomalies if any
        rounded = rounded.quantize(quantize_format, rounding=ROUND_DOWN)
        return rounded

    def round_price(self, specs: InstrumentSpecs, price: Decimal) -> Decimal:
        """Rounds a price to the correct tick size."""
        if specs.tick_size == Decimal("0"):
            self.logger.warning(
                f"Tick size is zero for price {price}. Cannot round accurately."
            )
            return price
        rounded = self._round_decimal(price, specs.tick_size)
        return rounded

    def round_quantity(self, specs: InstrumentSpecs, quantity: Decimal) -> Decimal:
        """Rounds a quantity to the correct quantity step."""
        if specs.qty_step == Decimal("0"):
            self.logger.warning(
                f"Quantity step is zero for quantity {quantity}. Cannot round accurately."
            )
            return quantity
        rounded = self._round_decimal(quantity, specs.qty_step)
        return rounded


class OrderSizingCalculator:
    """Calculates order sizes based on risk management.

    Determines the optimal trade size based on account balance, risk per trade,
    stop loss level, leverage, and optionally Kelly Criterion, while respecting
    instrument-specific minimums and maximums.
    """

    def __init__(
        self,
        precision_manager: PrecisionManager,
        logger: logging.Logger,
        config: EnhancedConfig,
    ):
        self.precision = precision_manager
        self.logger = logger
        self.config = config

    def calculate_position_size(
        self,
        specs: InstrumentSpecs,
        balance: Decimal,
        entry: Decimal,
        sl: Decimal,
        leverage: Decimal,
        metrics: PerformanceMetrics,
    ) -> Decimal | None:
        """Calculates the position size (quantity) for a trade.

        Prioritizes Kelly Criterion if enabled and sufficient data is available,
        otherwise falls back to fixed risk percentage. Applies max position size limits.

        Args:
            specs (InstrumentSpecs): Instrument specifications for rounding.
            balance (Decimal): Current account balance.
            entry (Decimal): The entry price of the trade.
            sl (Decimal): The stop loss price for the trade.
            leverage (Decimal): The account leverage.
            metrics (PerformanceMetrics): Bot's performance metrics for Kelly Criterion.

        Returns:
            Decimal | None: The calculated position size, or None if calculation fails.
        """
        if balance <= Decimal("0") or entry <= Decimal("0") or leverage <= Decimal("0"):
            self.logger.warning(
                "Invalid inputs for position sizing: balance, entry, leverage must be positive."
            )
            return None

        # Ensure SL is not at entry price
        if abs(entry - sl) == Decimal("0"):
            self.logger.warning(
                "Stop loss is at entry price, cannot calculate risk-based size."
            )
            return None

        position_value_usd = Decimal("0")

        if (
            self.config.USE_KELLY_SIZING and metrics.total_trades >= 10
        ):  # Need enough data for Kelly
            kelly_fraction = metrics.calculate_kelly_fraction(
                self.config.KELLY_FRACTION_CAP
            )
            if kelly_fraction > Decimal("0"):
                # Kelly gives fraction of total bankroll to wager
                # For leveraged trading, Kelly fraction * leverage = position size as % of equity
                # Or, simpler: Kelly fraction is applied directly to equity for position value
                position_value_usd = balance * kelly_fraction
                self.logger.debug(
                    f"Using Kelly Criterion: Kelly Fraction={kelly_fraction:.2%}, Base Position Value=${position_value_usd:,.2f}"
                )
            else:
                self.logger.warning(
                    "Kelly Criterion suggested no position or negative fraction. Falling back to fixed risk."
                )
                # Fallback to fixed risk if Kelly is not applicable or suggests no position
                return self._calculate_fixed_risk_size(
                    specs, balance, entry, sl, leverage
                )
        else:
            # If Kelly is disabled or not enough trades, use fixed risk
            return self._calculate_fixed_risk_size(specs, balance, entry, sl, leverage)

        # Apply max position size limit
        max_position_value_by_config = balance * (
            self.config.MAX_POSITION_SIZE_PCT / Decimal("100")
        )
        position_value_usd = min(position_value_usd, max_position_value_by_config)

        if position_value_usd <= Decimal("0"):
            self.logger.warning("Calculated position value is zero or negative.")
            return None

        # Convert position value to quantity in base currency units
        qty = position_value_usd / entry

        # Apply min/max order quantity and min notional value
        qty = self.precision.round_quantity(specs, qty)

        if qty < specs.min_order_qty:
            self.logger.warning(
                f"Calculated quantity {qty:.4f} is less than min order qty {specs.min_order_qty}. Adjusting to min order qty."
            )
            qty = specs.min_order_qty

        if qty > specs.max_order_qty:
            self.logger.warning(
                f"Calculated quantity {qty:.4f} exceeds max order qty {specs.max_order_qty}. Adjusting to max order qty."
            )
            qty = specs.max_order_qty

        # Check minimum order value for spot, or notional for derivatives
        if (
            self.config.CATEGORY_ENUM == Category.SPOT
            and (qty * entry) < specs.min_order_value
        ) or (
            self.config.CATEGORY_ENUM != Category.SPOT
            and (qty * entry) < specs.min_order_value
        ):  # for derivatives, min_order_value is min_order_amt
            self.logger.warning(
                f"Calculated order value {qty * entry:.2f} is less than min allowed value {specs.min_order_value:.2f}. No trade."
            )
            return None

        return qty

    def _calculate_fixed_risk_size(
        self,
        specs: InstrumentSpecs,
        balance: Decimal,
        entry: Decimal,
        sl: Decimal,
        leverage: Decimal,
    ) -> Decimal | None:
        """Calculates position size based on a fixed risk percentage per trade.

        Args:
            specs (InstrumentSpecs): Instrument specifications for rounding.
            balance (Decimal): Current account balance.
            entry (Decimal): The entry price of the trade.
            sl (Decimal): The stop loss price for the trade.
            leverage (Decimal): The account leverage.

        Returns:
            Decimal | None: The calculated position size, or None if calculation fails.
        """
        if abs(entry - sl) == Decimal("0"):
            self.logger.warning(
                "Stop loss is at entry price, cannot calculate risk-based size."
            )
            return None

        risk_amount = balance * (self.config.RISK_PER_TRADE_PCT / Decimal("100"))

        # Calculate PnL per unit if SL is hit
        loss_per_unit = abs(entry - sl)

        # Max quantity based on risk_amount (how much capital to allocate to cover the risk)
        qty_from_risk = risk_amount / loss_per_unit

        # Max quantity based on leverage and max position size % (total exposure limit)
        max_equity_for_pos = balance * (
            self.config.MAX_POSITION_SIZE_PCT / Decimal("100")
        )
        # For derivatives, position value is equity * leverage
        max_position_value_by_leverage = max_equity_for_pos * leverage
        qty_from_leverage = max_position_value_by_leverage / entry

        # Take the minimum of the two calculated quantities
        final_qty = min(qty_from_risk, qty_from_leverage)

        # Apply min/max order quantity and min notional value
        final_qty = self.precision.round_quantity(specs, final_qty)

        if final_qty < specs.min_order_qty:
            self.logger.warning(
                f"Calculated quantity {final_qty:.4f} is less than min order qty {specs.min_order_qty}. Adjusting to min order qty."
            )
            final_qty = specs.min_order_qty

        if final_qty > specs.max_order_qty:
            self.logger.warning(
                f"Calculated quantity {final_qty:.4f} exceeds max order qty {specs.max_order_qty}. Adjusting to max order qty."
            )
            final_qty = specs.max_order_qty

        # Check minimum order value for spot, or notional for derivatives
        if (
            self.config.CATEGORY_ENUM == Category.SPOT
            and (final_qty * entry) < specs.min_order_value
        ) or (
            self.config.CATEGORY_ENUM != Category.SPOT
            and (final_qty * entry) < specs.min_order_value
        ):
            self.logger.warning(
                f"Calculated order value {final_qty * entry:.2f} is less than min allowed value {specs.min_order_value:.2f}. No trade."
            )
            return None

        return final_qty


# =====================================================================
# MAIN TRADING BOT CLASS
# =====================================================================


class AdvancedSupertrendBot:
    """The main class for the Enhanced Supertrend trading bot.

    Manages the bot's lifecycle, including initialization, WebSocket connections,
    market analysis, indicator calculations, signal generation, trade execution,
    and position management. It orchestrates all components to facilitate
    automated trading based on the configured strategy.
    """

    def __init__(self, config: EnhancedConfig):
        self.config = config
        self.logger = setup_logger(config)
        self.bot_state = BotState(symbol=config.SYMBOL)
        self.stop_event = threading.Event()
        self.ws_reconnect_event = threading.Event()

        self.session = HTTP(
            testnet=config.TESTNET, api_key=config.API_KEY, api_secret=config.API_SECRET
        )
        self.precision_manager = PrecisionManager(self.session, self.logger, config)
        self.order_sizer = OrderSizingCalculator(
            self.precision_manager, self.logger, config
        )
        self.market_analyzer = MarketAnalyzer(self.config, self.logger)
        self.indicator_calculator = IndicatorCalculator(self.config, self.logger)

        self.ws_public: WebSocket | None = None
        self.ws_private: WebSocket | None = None
        self.klines_dfs: dict[str, pd.DataFrame] = {}  # {timeframe: DataFrame}
        self.order_book_data: dict[str, Any] = {
            "bids": [],
            "asks": [],
        }  # Real-time order book
        self.last_kline_timestamp: dict[
            str, datetime
        ] = {}  # To track last processed kline for each TF

        # State persistence thread
        self.state_saver_thread = threading.Thread(
            target=self._state_saver_loop, daemon=True, name="StateSaver"
        )

    def _api_call(self, api_method: Callable, **kwargs) -> dict[str, Any] | None:
        """A resilient wrapper for API calls with exponential backoff.

        Handles common Bybit API exceptions and retries failed requests with
        exponential backoff, logging errors encountered during the process.

        Args:
            api_method (Callable): The Bybit API method to call (e.g., self.session.get_kline).
            **kwargs: Arguments to pass to the API method.

        Returns:
            dict[str, Any] | None: The result from the API call if successful, otherwise None.
        """
        for attempt in range(1, self.config.MAX_API_RETRIES + 1):
            try:
                response = api_method(**kwargs)
                if response and response["retCode"] == 0:
                    return response
                else:
                    error_msg = (
                        response.get("retMsg", "Unknown error")
                        if response
                        else "No response"
                    )
                    self.logger.error(
                        f"API Error ({response.get('retCode', 'N/A')}): {error_msg} (Attempt {attempt}/{self.config.MAX_API_RETRIES}) for {api_method.__name__}"
                    )
                    with self.bot_state.lock:
                        self.bot_state.errors_count += 1
                        self.bot_state.last_error = error_msg
            except InvalidRequestError as e:
                self.logger.error(
                    f"Invalid API Request: {e}. Not retrying this type of error. (Attempt {attempt}/{self.config.MAX_API_RETRIES}) for {api_method.__name__}"
                )
                with self.bot_state.lock:
                    self.bot_state.errors_count += 1
                    self.bot_state.last_error = str(e)
                return None  # Don't retry on bad requests
            except FailedRequestError as e:
                self.logger.error(
                    f"Bybit Request Error: {e} (Attempt {attempt}/{self.config.MAX_API_RETRIES}) for {api_method.__name__}"
                )
                with self.bot_state.lock:
                    self.bot_state.errors_count += 1
                    self.bot_state.last_error = str(e)
            except Exception as e:
                self.logger.error(
                    f"General API Exception: {e} (Attempt {attempt}/{self.config.MAX_API_RETRIES}) for {api_method.__name__}",
                    exc_info=True,
                )
                with self.bot_state.lock:
                    self.bot_state.errors_count += 1
                    self.bot_state.last_error = str(e)

            if attempt < self.config.MAX_API_RETRIES:
                time.sleep(
                    min(self.config.API_RETRY_DELAY_SEC * (2 ** (attempt - 1)), 60)
                )  # Exponential backoff, max 60 seconds
        self.logger.critical(
            f"API call failed after {self.config.MAX_API_RETRIES} retries: {api_method.__name__} with kwargs {kwargs}"
        )
        return None

    def run(self):
        """Starts the bot and all its components.

        This method initializes the bot, loads previous state if available,
        fetches initial market data, sets up WebSocket connections, starts
        the UI and state saver threads, and then enters the main trading loop.
        It handles graceful shutdown via signal handlers.
        """
        self.bot_state.add_log("🚀 Starting Advanced Supertrend Bot...", "INFO")
        self.logger.info("🚀 Starting Advanced Supertrend Bot...")
        self._install_signal_handlers()

        # Load previous state if available
        if self.bot_state.load_state(self.config.STATE_FILE):
            self.bot_state.add_log("Loaded previous bot state.", "INFO")
        else:
            self.bot_state.add_log(
                "No previous state found or failed to load. Starting fresh.", "INFO"
            )

        # Initial setup and data fetching
        current_balance = self._get_account_balance()
        if current_balance == Decimal("0"):
            self.bot_state.add_log(
                "Could not retrieve initial account balance. Exiting.", "ERROR"
            )
            self.logger.critical(
                "Could not retrieve initial account balance. Shutting down."
            )
            return

        with self.bot_state.lock:
            self.bot_state.account_balance = current_balance
            if self.bot_state.initial_balance == Decimal(
                "0"
            ):  # Set initial balance only once
                self.bot_state.initial_balance = current_balance
                self.bot_state.metrics.peak_balance = (
                    current_balance  # Set peak balance initially
                )

            # Reset daily balance if a new day has started
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if today_str not in self.bot_state.metrics.daily_pnl:
                self.bot_state.daily_start_balance = current_balance
                self.bot_state.metrics.daily_pnl[today_str] = Decimal("0")
                self.bot_state.metrics.daily_trades[today_str] = 0
                self.bot_state.add_log(
                    "New trading day detected. Initializing daily balance and metrics.",
                    "INFO",
                )
            else:
                self.bot_state.daily_start_balance = current_balance  # Always update to current balance when bot starts for the day
                self.bot_state.add_log(
                    f"Resumed on existing trading day {today_str}. Daily start balance set to current.",
                    "INFO",
                )

        # Fetch initial kline data for all timeframes
        all_timeframes = [
            self.config.PRIMARY_TIMEFRAME
        ] + self.config.SECONDARY_TIMEFRAMES
        for tf in sorted(list(set(all_timeframes))):  # Use set to avoid duplicates
            if not self._fetch_initial_klines(tf):
                self.bot_state.add_log(
                    f"Failed to fetch initial kline data for {tf}. Shutting down.",
                    "ERROR",
                )
                self.logger.critical(
                    f"Failed to fetch initial kline data for {tf}. Shutting down."
                )
                return

        if not self._set_leverage_and_margin():
            self.bot_state.add_log(
                "Failed to set leverage or margin mode. Shutting down.", "ERROR"
            )
            self.logger.critical(
                "Failed to set leverage or margin mode. Shutting down."
            )
            return

        # Start UI and WebSocket threads
        self.ui = EnhancedUI(self.bot_state, self.config)
        self.ui.start()
        self.state_saver_thread.start()

        threading.Thread(
            target=self._websocket_manager, daemon=True, name="WebSocketManager"
        ).start()

        self.bot_state.add_log("Bot is now running. Press Ctrl+C to stop.", "INFO")
        self.logger.info("Bot is now running.")

        # Main thread waits here until a stop signal is received
        # The strategy logic runs on kline updates from WebSocket, not a polling loop in main thread
        while not self.stop_event.is_set():
            time.sleep(1)  # Sleep to keep main thread alive

        self.cleanup()

    def _websocket_manager(self):
        """Manages WebSocket connections and reconnections.

        This method runs in a separate thread, responsible for establishing
        and maintaining WebSocket connections for both public and private data streams.
        It handles connection errors and attempts to reconnect automatically.
        """
        while not self.stop_event.is_set():
            try:
                self._connect_websockets()
                self.ws_reconnect_event.clear()  # Clear event after successful connection
                # Keep the thread alive while websockets are active
                while (
                    not self.stop_event.is_set()
                    and not self.ws_reconnect_event.is_set()
                ):
                    time.sleep(1)  # Sleep to prevent busy-waiting
            except Exception as e:
                self.bot_state.add_log(
                    f"WebSocket connection error: {e}. Reconnecting in {self.config.API_RETRY_DELAY_SEC}s...",
                    "ERROR",
                )
                self.logger.error(
                    f"WebSocket connection error: {e}. Reconnecting in {self.config.API_RETRY_DELAY_SEC}s...",
                    exc_info=True,
                )
                self.ws_reconnect_event.set()  # Set event to signal reconnection needed
                time.sleep(
                    self.config.API_RETRY_DELAY_SEC
                )  # Wait before attempting to reconnect
            finally:
                self._close_websockets()

    def _connect_websockets(self):
        """Initializes and connects the WebSocket client(s).

        Sets up public (kline, ticker, orderbook) and private (position, wallet)
        WebSocket streams, subscribing to the necessary channels for the configured
        symbol and timeframes.
        """
        self.bot_state.add_log("Connecting to WebSockets...", "INFO")
        self.logger.info("Connecting to WebSockets...")

        try:
            # Public WebSocket for Klines, Tickers, Order Book
            self.ws_public = WebSocket(
                testnet=self.config.TESTNET,
                channel_type="spot"
                if self.config.CATEGORY_ENUM == Category.SPOT
                else "unified",  # unified for linear/inverse/option
            )
            # Private WebSocket for Positions, Wallet
            self.ws_private = WebSocket(
                testnet=self.config.TESTNET,
                channel_type="spot"
                if self.config.CATEGORY_ENUM == Category.SPOT
                else "unified",
                api_key=self.config.API_KEY,
                api_secret=self.config.API_SECRET,
            )

            # Subscribe to public streams
            all_timeframes = [
                self.config.PRIMARY_TIMEFRAME
            ] + self.config.SECONDARY_TIMEFRAMES
            for tf in sorted(list(set(all_timeframes))):
                self.ws_public.kline_stream(
                    tf,
                    self.config.SYMBOL,
                    lambda msg, tf=tf: self._handle_kline_message(msg, tf),
                )
            self.ws_public.tickers_stream(
                self.config.SYMBOL, self._handle_ticker_message
            )
            if self.config.USE_ORDER_BOOK:
                self.ws_public.orderbook_stream(
                    self.config.ORDER_BOOK_DEPTH_LEVELS,
                    self.config.SYMBOL,
                    self._handle_orderbook_message,
                )

            # Subscribe to private streams
            self.ws_private.position_stream(self._handle_position_message)
            self.ws_private.wallet_stream(self._handle_wallet_message)

            with self.bot_state.lock:
                self.bot_state.bot_status = "Live"
            self.bot_state.add_log("WebSockets connected and subscribed.", "SUCCESS")
            self.logger.info("WebSockets connected and subscribed.")
        except Exception as e:
            self.bot_state.add_log(f"Failed to connect to WebSockets: {e}", "ERROR")
            self.logger.error(f"Failed to connect to WebSockets: {e}", exc_info=True)
            raise  # Re-raise to trigger reconnection logic

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
        """Handles incoming kline (candlestick) messages from the WebSocket.

        Processes confirmed kline data, updates the internal DataFrame, and
        triggers the main strategy cycle if the message is for the primary timeframe.
        It also prevents processing duplicate or old confirmed candles.

        Args:
            message (dict): The WebSocket message containing kline data.
            timeframe (str): The timeframe of the received kline data.
        """
        kline = message["data"][0]
        if kline["confirm"]:  # Only process confirmed candles
            kline_timestamp = datetime.fromtimestamp(
                int(kline["start"]) / 1000, tz=timezone.utc
            )

            # Check if this candle has already been processed for this TF
            if (
                timeframe in self.last_kline_timestamp
                and kline_timestamp <= self.last_kline_timestamp[timeframe]
            ):
                self.logger.debug(
                    f"Skipping duplicate/old confirmed kline for {timeframe} at {kline_timestamp}"
                )
                return

            self.logger.debug(
                f"New confirmed candle received for {timeframe} at {kline_timestamp}"
            )
            self.last_kline_timestamp[timeframe] = kline_timestamp

            self._update_kline_data(kline, timeframe)

            # Only run strategy cycle on primary timeframe's confirmed candle
            if timeframe == self.config.PRIMARY_TIMEFRAME:
                self._run_strategy_cycle()

    def _handle_ticker_message(self, message: dict[str, Any]):
        """Handles incoming ticker messages from the WebSocket.

        Updates the bot's current price and price direction based on the latest ticker data.
        """
        with self.bot_state.lock:
            old_price = self.bot_state.current_price
            new_price = Decimal(message["data"]["lastPrice"])
            self.bot_state.current_price = new_price
            if new_price > old_price:
                self.bot_state.price_direction = 1
            elif new_price < old_price:
                self.bot_state.price_direction = -1
            else:
                self.bot_state.price_direction = 0

            # Also update the primary timeframe's current price in market data
            if self.config.PRIMARY_TIMEFRAME in self.bot_state.market_data:
                self.bot_state.market_data[
                    self.config.PRIMARY_TIMEFRAME
                ].close = new_price  # Use 'close' for current price
                # Ensure bid/ask and spread are updated if present in ticker
                if "bidPrice" in message["data"] and "askPrice" in message["data"]:
                    bid = Decimal(message["data"]["bidPrice"])
                    ask = Decimal(message["data"]["askPrice"])
                    self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].bid = bid
                    self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].ask = ask
                    if ask > Decimal("0"):
                        self.bot_state.market_data[
                            self.config.PRIMARY_TIMEFRAME
                        ].spread_pct = ((ask - bid) / ask) * Decimal("100")

    def _handle_position_message(self, message: dict[str, Any]):
        """Handles incoming position update messages from the WebSocket.

        This method is called when Bybit sends updates about the user's positions.
        It triggers an internal update of the bot's position state.
        """
        self.logger.info(
            "Position update received via WebSocket. Triggering state update."
        )
        # Schedule position update to happen in the main cycle to avoid race conditions
        # For simplicity, we directly call it here, but in complex scenarios, queueing is better.
        self._update_position_state()

    def _handle_wallet_message(self, message: dict[str, Any]):
        """Handles incoming wallet balance update messages from the WebSocket.

        This method is called when Bybit sends updates about the user's account balance.
        It updates the bot's internal account balance and checks for daily PnL resets.
        """
        self.logger.info(
            "Wallet update received via WebSocket. Triggering balance update."
        )
        with self.bot_state.lock:
            old_balance = self.bot_state.account_balance
            new_balance = self._get_account_balance()
            self.bot_state.account_balance = new_balance
            self.logger.info(
                f"Account balance updated: {old_balance:,.2f} -> {new_balance:,.2f} USDT"
            )

            # Check if it's a new day for daily balance tracking
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if today_str not in self.bot_state.metrics.daily_pnl:
                self.bot_state.daily_start_balance = new_balance
                self.bot_state.metrics.daily_pnl[today_str] = Decimal("0")
                self.bot_state.metrics.daily_trades[today_str] = 0
                self.bot_state.add_log(
                    "New trading day started. Resetting daily balance.", "INFO"
                )

    def _handle_orderbook_message(self, message: dict[str, Any]):
        """Handles incoming order book messages from the WebSocket.

        Updates the bot's order book data and calculates the order book imbalance
        for the primary timeframe's market data.
        """
        with self.bot_state.lock:
            self.order_book_data["bids"] = message["data"]["b"]
            self.order_book_data["asks"] = message["data"]["a"]
            # Update market data with imbalance for primary TF
            if self.config.PRIMARY_TIMEFRAME in self.bot_state.market_data:
                imbalance = self.market_analyzer.analyze_order_book_imbalance(
                    self.order_book_data["bids"],
                    self.order_book_data["asks"],
                    self.config.ORDER_BOOK_DEPTH_LEVELS,
                )
                self.bot_state.market_data[
                    self.config.PRIMARY_TIMEFRAME
                ].order_book_imbalance = imbalance

                # Also update bid/ask prices
                if self.order_book_data["bids"]:
                    self.bot_state.market_data[
                        self.config.PRIMARY_TIMEFRAME
                    ].bid = Decimal(self.order_book_data["bids"][0][0])
                if self.order_book_data["asks"]:
                    self.bot_state.market_data[
                        self.config.PRIMARY_TIMEFRAME
                    ].ask = Decimal(self.order_book_data["asks"][0][0])

                if self.bot_state.market_data[
                    self.config.PRIMARY_TIMEFRAME
                ].bid > Decimal("0") and self.bot_state.market_data[
                    self.config.PRIMARY_TIMEFRAME
                ].ask > Decimal("0"):
                    spread = (
                        self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].ask
                        - self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].bid
                    )
                    self.bot_state.market_data[
                        self.config.PRIMARY_TIMEFRAME
                    ].spread_pct = (
                        spread
                        / self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].ask
                    ) * Decimal("100")

    # --- Core Bot Logic ---
    def _run_strategy_cycle(self):
        """The main logic cycle that runs on each new primary timeframe candle.

        This method orchestrates the bot's decision-making process by:
        1. Calculating all necessary technical indicators.
        2. Analyzing market conditions (regime, support/resistance, volume profile).
        3. Updating the current position state.
        4. Managing active positions (SL, TP, breakeven, partial closes).
        5. Checking for new entry signals if no position is active.
        """
        with self.bot_state.lock:
            self.bot_state.bot_status = "Analyzing..."

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
            self.bot_state.bot_status = "Live"
        self.logger.info("Strategy cycle completed.")

    def _check_daily_limits(self) -> bool:
        """Checks if daily loss or trade limits have been exceeded.

        Returns:
            bool: True if limits are not exceeded, False otherwise.
        """
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_pnl = self.bot_state.account_balance - self.bot_state.daily_start_balance
        daily_trades = self.bot_state.metrics.daily_trades.get(today_str, 0)

        # Check max daily loss
        if (
            daily_pnl
            < (-self.config.MAX_DAILY_LOSS_PCT / Decimal("100"))
            * self.bot_state.daily_start_balance
        ):
            self.bot_state.add_log(
                f"Daily loss limit ({self.config.MAX_DAILY_LOSS_PCT:.1f}%) exceeded ({daily_pnl:,.2f} USDT). Stopping new trades.",
                "WARNING",
            )
            self.logger.warning("Daily loss limit exceeded. Stopping new trades.")
            return False

        # Check max daily trades
        if daily_trades >= self.config.MAX_DAILY_TRADES:
            self.bot_state.add_log(
                f"Daily trade limit ({self.config.MAX_DAILY_TRADES}) exceeded. Stopping new trades.",
                "WARNING",
            )
            self.logger.warning("Daily trade limit exceeded. Stopping new trades.")
            return False

        # Check max consecutive losses
        if (
            self.bot_state.metrics.consecutive_losses
            >= self.config.MAX_CONSECUTIVE_LOSSES
        ):
            self.bot_state.add_log(
                f"Max consecutive losses ({self.config.MAX_CONSECUTIVE_LOSSES}) reached. Stopping new trades.",
                "WARNING",
            )
            self.logger.warning("Max consecutive losses reached. Stopping new trades.")
            return False

        # Check max drawdown
        # current_drawdown is already a positive percentage
        if self.bot_state.metrics.current_drawdown >= self.config.MAX_DRAWDOWN_PCT:
            self.bot_state.add_log(
                f"Max drawdown limit ({self.config.MAX_DRAWDOWN_PCT:.1f}%) reached. Stopping new trades.",
                "WARNING",
            )
            self.logger.warning("Max drawdown limit reached. Stopping new trades.")
            return False

        return True

    def _check_for_entry_signal(self):
        """Checks if conditions are met to generate a trading signal and place an entry order.

        First verifies daily limits, then generates a signal based on the strategy,
        and finally executes a trade if a valid signal is produced.
        """
        if not self._check_daily_limits():
            self.bot_state.add_log(
                "Daily trading limits hit. No new trades.", "WARNING"
            )
            return

        signal, reason, strength = self._generate_signal()
        with self.bot_state.lock:
            self.bot_state.last_signal = signal
            self.bot_state.last_signal_time = datetime.now(timezone.utc)
            self.bot_state.last_signal_reason = reason
            self.bot_state.signal_strength = strength

        if signal != Signal.NEUTRAL:
            self.bot_state.add_log(
                f"Signal Generated: {signal.name} (Strength: {strength:.1%}) - Reason: {reason}",
                "INFO",
            )
            self._execute_trade(signal)
        else:
            self.logger.debug(f"No entry signal. Reason: {reason}")

    def _generate_signal(self) -> tuple[Signal, str, Decimal]:
        """Generates a trading signal based on the Ehlers Supertrend Cross strategy
        with multi-timeframe confirmation and filters.

        Returns:
            tuple[Signal, str, Decimal]: A tuple containing the signal (BUY, SELL, NEUTRAL),
                                         the reason for the signal, and its strength.
        """
        primary_df = self.klines_dfs.get(self.config.PRIMARY_TIMEFRAME)
        if (
            primary_df is None
            or primary_df.empty
            or len(primary_df)
            < max(
                self.config.ST_PERIOD_BASE,
                self.config.ADX_WINDOW,
                self.config.RSI_WINDOW,
                self.config.MACD_SLOW,
            )
            + 10
        ):
            return Signal.NEUTRAL, "Insufficient primary timeframe data.", Decimal("0")

        latest_primary = primary_df.iloc[-1]
        prev_primary = primary_df.iloc[-2]

        # Base Ehlers Supertrend Cross Logic (Primary Timeframe)
        ehlers_filter_latest = latest_primary.get("ehlers_filter", np.nan)
        ehlers_filter_prev = prev_primary.get("ehlers_filter", np.nan)
        supertrend_line_latest = latest_primary.get("supertrend_line", np.nan)
        supertrend_line_prev = prev_primary.get("supertrend_line", np.nan)
        st_dir_primary = latest_primary.get("supertrend_direction", np.nan)

        if (
            pd.isna(ehlers_filter_latest)
            or pd.isna(ehlers_filter_prev)
            or pd.isna(supertrend_line_latest)
            or pd.isna(supertrend_line_prev)
            or pd.isna(st_dir_primary)
        ):
            return (
                Signal.NEUTRAL,
                "Missing Ehlers Filter or Supertrend data in primary TF.",
                Decimal("0"),
            )

        ehlers_cross_up = (
            ehlers_filter_prev < supertrend_line_prev
            and ehlers_filter_latest > supertrend_line_latest
        )
        ehlers_cross_down = (
            ehlers_filter_prev > supertrend_line_prev
            and ehlers_filter_latest < supertrend_line_latest
        )

        base_buy_signal = (
            ehlers_cross_up and st_dir_primary == 1
        )  # Supertrend is already bullish
        base_sell_signal = (
            ehlers_cross_down and st_dir_primary == -1
        )  # Supertrend is already bearish

        signal_strength = Decimal("0")
        reason_parts = []

        # --- Signal Confirmation & Filters ---

        # 1. Multi-timeframe Supertrend Confirmation
        mtf_st_confirmation = True
        if self.config.SECONDARY_TIMEFRAMES:
            for tf in self.config.SECONDARY_TIMEFRAMES:
                df_tf = self.klines_dfs.get(tf)
                if (
                    df_tf is None
                    or df_tf.empty
                    or "supertrend_direction" not in df_tf.columns
                ):
                    self.logger.debug(
                        f"Secondary TF {tf} data missing for ST confirmation."
                    )
                    mtf_st_confirmation = False
                    break

                latest_tf = df_tf.iloc[-1]
                if pd.isna(latest_tf["supertrend_direction"]):
                    self.logger.debug(f"Secondary TF {tf} ST direction is NaN.")
                    mtf_st_confirmation = False
                    break

                if base_buy_signal and latest_tf["supertrend_direction"] != 1:
                    mtf_st_confirmation = False
                    break
                if base_sell_signal and latest_tf["supertrend_direction"] != -1:
                    mtf_st_confirmation = False
                    break
        else:  # No secondary timeframes configured, assume confirmed for strength calculation
            mtf_st_confirmation = True

        if mtf_st_confirmation:
            signal_strength += Decimal("0.3")  # 30% for MTF ST confirmation
            reason_parts.append("MTF ST Confirmed")
        else:
            self.logger.debug("MTF ST not confirmed.")
            # For strict strategy, if MTF not confirmed, return neutral early for strong signals
            # For this version, we continue to add other filters but signal will be weaker.

        # 2. ADX Trend Filter
        adx_ok = False
        if (
            self.config.ADX_TREND_FILTER
            and "adx" in latest_primary
            and not pd.isna(latest_primary["adx"])
        ):
            if latest_primary["adx"] > self.config.ADX_MIN_THRESHOLD:
                if (
                    base_buy_signal
                    and latest_primary.get("dmp", 0) > latest_primary.get("dmn", 0)
                ) or (
                    base_sell_signal
                    and latest_primary.get("dmn", 0) > latest_primary.get("dmp", 0)
                ):
                    adx_ok = True

        if adx_ok:
            signal_strength += Decimal("0.2")  # 20% for ADX
            reason_parts.append(
                f"ADX({latest_primary['adx']:.1f}) > {self.config.ADX_MIN_THRESHOLD}"
            )
        elif self.config.ADX_TREND_FILTER:
            self.logger.debug(
                f"ADX ({latest_primary.get('adx', 'N/A'):.1f}) below threshold {self.config.ADX_MIN_THRESHOLD} or direction not confirmed."
            )

        # 3. RSI Filter
        rsi_ok = False
        if (
            self.config.RSI_FILTER
            and "rsi" in latest_primary
            and not pd.isna(latest_primary["rsi"])
        ):
            if (
                base_buy_signal and latest_primary["rsi"] < self.config.RSI_OVERBOUGHT
            ) or (
                base_sell_signal and latest_primary["rsi"] > self.config.RSI_OVERSOLD
            ):
                rsi_ok = True

        if rsi_ok:
            signal_strength += Decimal("0.15")  # 15% for RSI
            reason_parts.append(f"RSI({latest_primary['rsi']:.1f}) OK")
        elif self.config.RSI_FILTER:
            self.logger.debug(
                f"RSI ({latest_primary.get('rsi', 'N/A'):.1f}) outside range."
            )

        # 4. MACD Confirmation
        macd_ok = False
        if (
            self.config.MACD_FILTER
            and "macd_hist" in latest_primary
            and not pd.isna(latest_primary["macd_hist"])
        ):
            if (base_buy_signal and latest_primary["macd_hist"] > 0) or (
                base_sell_signal and latest_primary["macd_hist"] < 0
            ):
                macd_ok = True

        if macd_ok:
            signal_strength += Decimal("0.15")  # 15% for MACD
            reason_parts.append(
                f"MACD Hist({latest_primary['macd_hist']:.4f}) Confirmed"
            )
        elif self.config.MACD_FILTER:
            self.logger.debug(
                f"MACD Hist ({latest_primary.get('macd_hist', 'N/A'):.4f}) not confirmed."
            )

        # 5. Volume Filter
        volume_ok = False
        if (
            self.config.VOLUME_FILTER
            and "volume_ratio" in latest_primary
            and not pd.isna(latest_primary["volume_ratio"])
        ):
            if latest_primary["volume_ratio"] > self.config.VOLUME_MULTIPLIER:
                volume_ok = True

        if volume_ok:
            signal_strength += Decimal("0.1")  # 10% for Volume
            reason_parts.append(
                f"Volume Ratio({latest_primary['volume_ratio']:.2f}x) > {self.config.VOLUME_MULTIPLIER}"
            )
        elif self.config.VOLUME_FILTER:
            self.logger.debug(
                f"Volume Ratio ({latest_primary.get('volume_ratio', 'N/A'):.2f}x) below threshold {self.config.VOLUME_MULTIPLIER}"
            )

        # 6. Order Book Imbalance (if enabled)
        order_book_ok = False
        if self.config.USE_ORDER_BOOK:
            imbalance = self.bot_state.market_data[
                self.config.PRIMARY_TIMEFRAME
            ].order_book_imbalance
            if (
                base_buy_signal
                and imbalance > self.config.ORDER_BOOK_IMBALANCE_THRESHOLD
            ) or (
                base_sell_signal
                and imbalance < -self.config.ORDER_BOOK_IMBALANCE_THRESHOLD
            ):
                order_book_ok = True

        if order_book_ok:
            signal_strength += Decimal("0.1")  # 10% for Order Book
            reason_parts.append(f"OB Imbalance({imbalance:.2%}) Confirmed")
        elif self.config.USE_ORDER_BOOK:
            self.logger.debug(
                f"Order Book Imbalance ({self.bot_state.market_data[self.config.PRIMARY_TIMEFRAME].order_book_imbalance:.2%}) not confirmed."
            )

        final_reason = (
            " | ".join(reason_parts) if reason_parts else "No specific confirmations."
        )

        # Final Signal Decision
        if (
            base_buy_signal
            and mtf_st_confirmation
            and adx_ok
            and rsi_ok
            and macd_ok
            and volume_ok
            and order_book_ok
        ):
            return (
                Signal.STRONG_BUY,
                "Strong Buy: All confirmations passed.",
                signal_strength,
            )
        elif (
            base_buy_signal and mtf_st_confirmation and adx_ok
        ):  # Minimum strong confirmation
            return Signal.BUY, "Buy: Base + MTF ST + ADX confirmed.", signal_strength
        elif (
            base_sell_signal
            and mtf_st_confirmation
            and adx_ok
            and rsi_ok
            and macd_ok
            and volume_ok
            and order_book_ok
        ):
            return (
                Signal.STRONG_SELL,
                "Strong Sell: All confirmations passed.",
                signal_strength,
            )
        elif (
            base_sell_signal and mtf_st_confirmation and adx_ok
        ):  # Minimum strong confirmation
            return Signal.SELL, "Sell: Base + MTF ST + ADX confirmed.", signal_strength

        return (
            Signal.NEUTRAL,
            "No strong signal or insufficient confirmations.",
            Decimal("0"),
        )

    def _execute_trade(self, signal: Signal):
        """Calculates trade parameters and places the entry order.

        Determines entry price, stop loss, take profit, and position size based on
        configuration and risk management rules, then places the order via API.

        Args:
            signal (Signal): The trading signal (BUY, SELL, etc.).
        """
        specs = self.precision_manager.get_specs(
            self.config.SYMBOL, self.config.CATEGORY_ENUM
        )
        if not specs:
            self.bot_state.add_log(
                "Could not get instrument specs. Cannot place trade.", "ERROR"
            )
            return

        side = "Buy" if signal.value > 0 else "Sell"
        entry_price = (
            self.bot_state.current_price
        )  # Use latest ticker price for market orders

        # --- Calculate SL and TP ---
        primary_df = self.klines_dfs.get(self.config.PRIMARY_TIMEFRAME)
        if (
            primary_df.empty
            or "atr" not in primary_df.columns
            or primary_df["atr"].iloc[-1] == 0
            or pd.isna(primary_df["atr"].iloc[-1])
        ):
            self.bot_state.add_log(
                "ATR not available or zero for stop/take profit calculation. Using default percentage.",
                "WARNING",
            )
            atr = Decimal("0")
        else:
            atr = Decimal(str(primary_df["atr"].iloc[-1]))

        if self.config.USE_ATR_STOPS and atr > Decimal("0"):
            sl_distance = atr * self.config.ATR_STOP_MULTIPLIER
            tp_distance = atr * self.config.ATR_TP_MULTIPLIER
        else:
            sl_distance = entry_price * (self.config.STOP_LOSS_PCT / Decimal("100"))
            tp_distance = entry_price * (self.config.TAKE_PROFIT_PCT / Decimal("100"))

        if side == "Buy":
            sl_price = entry_price - sl_distance
            tp_price = entry_price + tp_distance
        else:  # Sell
            sl_price = entry_price + sl_distance
            tp_price = entry_price - tp_distance

        sl_price = self.precision_manager.round_price(specs, sl_price)
        tp_price = self.precision_manager.round_price(specs, tp_price)

        # Ensure SL/TP are valid (not crossing entry)
        if (side == "Buy" and sl_price >= entry_price) or (
            side == "Sell" and sl_price <= entry_price
        ):
            self.bot_state.add_log(
                f"Invalid SL price calculated ({sl_price:.4f}) for entry {entry_price:.4f}. Using fallback.",
                "WARNING",
            )
            sl_price = (
                entry_price
                * (Decimal("1") - (self.config.STOP_LOSS_PCT / Decimal("100")))
                if side == "Buy"
                else entry_price
                * (Decimal("1") + (self.config.STOP_LOSS_PCT / Decimal("100")))
            )
            sl_price = self.precision_manager.round_price(specs, sl_price)

        if (side == "Buy" and tp_price <= entry_price) or (
            side == "Sell" and tp_price >= entry_price
        ):
            self.bot_state.add_log(
                f"Invalid TP price calculated ({tp_price:.4f}) for entry {entry_price:.4f}. Using fallback.",
                "WARNING",
            )
            tp_price = (
                entry_price
                * (Decimal("1") + (self.config.TAKE_PROFIT_PCT / Decimal("100")))
                if side == "Buy"
                else entry_price
                * (Decimal("1") - (self.config.TAKE_PROFIT_PCT / Decimal("100")))
            )
            tp_price = self.precision_manager.round_price(specs, tp_price)

        # --- Calculate Position Size ---
        qty = self.order_sizer.calculate_position_size(
            specs,
            self.bot_state.account_balance,
            entry_price,
            sl_price,
            self.config.LEVERAGE,
            self.bot_state.metrics,
        )

        if qty and qty >= specs.min_order_qty:
            self.bot_state.add_log(
                f"Placing {side} order for {qty:.4f} {self.config.SYMBOL} at ~{entry_price:.4f} with SL {sl_price:.4f} and TP {tp_price:.4f}",
                "INFO",
            )
            order_id = self._place_order(
                side, qty, self.config.ORDER_TYPE_ENUM, entry_price, sl_price, tp_price
            )
            if order_id:
                # Initialize position object immediately, it will be updated by WebSocket later
                with self.bot_state.lock:
                    self.bot_state.position = Position(
                        symbol=self.config.SYMBOL,
                        side=side,
                        size=qty,
                        entry_price=entry_price,  # This will be updated to actual avgPrice by WS
                        stop_loss=sl_price,
                        take_profit=tp_price,
                        order_id=order_id,
                        entry_time=datetime.now(timezone.utc),
                    )
                self.bot_state.add_log(
                    f"Entry order {order_id} placed successfully.", "SUCCESS"
                )
            else:
                self.bot_state.add_log("Entry order placement failed.", "ERROR")
        else:
            self.bot_state.add_log(
                f"Calculated quantity ({qty or 'N/A'}) is below minimum or invalid. No trade placed.",
                "WARNING",
            )

    def _manage_active_position(self):
        """Manages an active open position.

        Handles dynamic adjustments to stop loss (breakeven, trailing stop)
        and partial take profits based on the configured strategy parameters and
        current market conditions.
        """
        pos = self.bot_state.position
        if not pos:
            return

        # Ensure current price is updated
        with self.bot_state.lock:
            pos.current_price = self.bot_state.current_price
            # Update unrealized_pnl based on latest price
            if pos.current_price > Decimal("0"):
                pos_value_entry = pos.size * pos.entry_price
                pos_value_current = pos.size * pos.current_price
                if pos.side == "Buy":
                    pos.unrealized_pnl = pos_value_current - pos_value_entry
                else:  # Sell
                    pos.unrealized_pnl = pos_value_entry - pos_value_current
            else:
                pos.unrealized_pnl = Decimal("0")

        # PnL calculations for management
        pnl_pct = pos.pnl_pct

        specs = self.precision_manager.get_specs(
            self.config.SYMBOL, self.config.CATEGORY_ENUM
        )
        if not specs:
            self.bot_state.add_log(
                "Could not get instrument specs for position management. Skipping advanced management.",
                "ERROR",
            )
            return

        # --- Breakeven Logic ---
        if self.config.BREAKEVEN_ENABLED and not pos.breakeven_activated:
            if (pos.side == "Buy" and pnl_pct >= self.config.BREAKEVEN_PROFIT_PCT) or (
                pos.side == "Sell" and pnl_pct >= self.config.BREAKEVEN_PROFIT_PCT
            ):
                new_sl = pos.entry_price
                if pos.side == "Buy":
                    new_sl += pos.entry_price * (
                        self.config.BREAKEVEN_OFFSET_PCT / Decimal("100")
                    )
                else:  # Sell
                    new_sl -= pos.entry_price * (
                        self.config.BREAKEVEN_OFFSET_PCT / Decimal("100")
                    )

                new_sl = self.precision_manager.round_price(specs, new_sl)
                # Only update if the new SL is more favorable than current SL
                if (pos.side == "Buy" and new_sl > pos.stop_loss) or (
                    pos.side == "Sell"
                    and (new_sl < pos.stop_loss or pos.stop_loss == Decimal("0"))
                ):  # If SL was 0 or current SL is less favorable
                    self.bot_state.add_log(
                        f"Breakeven profit target hit ({pnl_pct:.2f}%). Moving SL to {new_sl:.4f}.",
                        "INFO",
                    )
                    if self._update_trading_stop(stop_loss=new_sl):
                        with self.bot_state.lock:
                            pos.stop_loss = new_sl
                            pos.breakeven_activated = True
                    else:
                        self.bot_state.add_log(
                            "Failed to set breakeven stop loss.", "ERROR"
                        )

        # --- Trailing Stop Logic ---
        if self.config.TRAILING_SL_ENABLED:
            # Activate trailing SL if not already active and profit target is met
            if (
                not pos.trailing_sl_activated
                and pnl_pct >= self.config.TRAILING_SL_ACTIVATION_PCT
            ):
                with self.bot_state.lock:
                    pos.trailing_sl_activated = True
                self.bot_state.add_log(
                    f"Trailing SL activated at {pnl_pct:.2f}% profit.", "INFO"
                )

            # If trailing SL is active, continuously update it
            if pos.trailing_sl_activated:
                new_trailing_sl = Decimal("0")
                if pos.side == "Buy":
                    # Trail by a percentage below current price
                    new_trailing_sl = pos.current_price * (
                        Decimal("1")
                        - (self.config.TRAILING_SL_DISTANCE_PCT / Decimal("100"))
                    )
                else:  # Sell
                    # Trail by a percentage above current price
                    new_trailing_sl = pos.current_price * (
                        Decimal("1")
                        + (self.config.TRAILING_SL_DISTANCE_PCT / Decimal("100"))
                    )

                new_trailing_sl = self.precision_manager.round_price(
                    specs, new_trailing_sl
                )

                # Only update if the new trailing SL is better (higher for buy, lower for sell)
                # and it's not worse than the current SL (which could be breakeven or initial SL)
                if (pos.side == "Buy" and new_trailing_sl > pos.stop_loss) or (
                    pos.side == "Sell"
                    and (
                        new_trailing_sl < pos.stop_loss or pos.stop_loss == Decimal("0")
                    )
                ):
                    self.bot_state.add_log(
                        f"Updating trailing SL to {new_trailing_sl:.4f}.", "INFO"
                    )
                    if self._update_trading_stop(stop_loss=new_trailing_sl):
                        with self.bot_state.lock:
                            pos.stop_loss = new_trailing_sl
                    else:
                        self.bot_state.add_log(
                            "Failed to update trailing stop loss.", "ERROR"
                        )

        # --- Partial Take Profit Logic ---
        if self.config.PARTIAL_TP_ENABLED and pos.size > specs.min_order_qty:
            for target in self.config.PARTIAL_TP_TARGETS:
                # Check if this target has already been hit and recorded
                # Note: 'closed_qty_pct' in partial_closes is the *percentage of the original entry size* for that specific partial close.
                # So we sum up all percentages of original entry size.
                current_closed_pct_sum = sum(
                    pc["closed_qty_pct"] for pc in pos.partial_closes
                ) * Decimal("100")

                # Check if this specific target profit_pct has already been actioned
                if any(
                    p["profit_pct"] == target["profit_pct"] for p in pos.partial_closes
                ):
                    continue

                if (pos.side == "Buy" and pnl_pct >= target["profit_pct"]) or (
                    pos.side == "Sell" and pnl_pct >= target["profit_pct"]
                ):
                    # Calculate quantity to close based on *original* position size
                    # The `pos.size` here is the *remaining* size, not original.
                    # We need to calculate based on the initial entry size.
                    # A better way is to track `original_size` in Position class.
                    # For now, let's use the remaining size, but be aware this is a simplification.
                    qty_to_close_from_remaining = pos.size * target["close_qty_pct"]
                    qty_to_close = self.precision_manager.round_quantity(
                        specs, qty_to_close_from_remaining
                    )

                    # Ensure we don't close more than available remaining size or less than min order qty
                    if qty_to_close > pos.size:
                        qty_to_close = pos.size
                    if qty_to_close < specs.min_order_qty:
                        self.bot_state.add_log(
                            f"Calculated partial TP qty {qty_to_close:.4f} is too small (Min: {specs.min_order_qty}). Skipping.",
                            "WARNING",
                        )
                        continue

                    self.bot_state.add_log(
                        f"Partial TP target hit ({target['profit_pct']:.2f}%). Closing {qty_to_close:.4f} of position.",
                        "INFO",
                    )
                    if self._close_position(partial_qty=qty_to_close):
                        with self.bot_state.lock:
                            pos.partial_closes.append(
                                {
                                    "profit_pct": target["profit_pct"],
                                    "closed_qty": qty_to_close,
                                    "closed_qty_pct": target[
                                        "close_qty_pct"
                                    ],  # Store original % for UI display
                                }
                            )
                            pos.size -= qty_to_close  # Update local position size
                            if (
                                pos.size < specs.min_order_qty
                            ):  # If remaining size is too small after partial close
                                self.bot_state.add_log(
                                    f"Remaining position size {pos.size:.4f} is too small. Closing the rest.",
                                    "INFO",
                                )
                                self._close_position(
                                    partial_qty=pos.size
                                )  # Close the tiny remainder
                            self.bot_state.add_log(
                                f"Partial close successful. Remaining size: {pos.size:.4f}",
                                "SUCCESS",
                            )
                    else:
                        self.bot_state.add_log(
                            "Failed to execute partial take profit.", "ERROR"
                        )

    # --- Data & State Management ---
    def _fetch_initial_klines(self, timeframe: str) -> bool:
        """Fetches the initial set of kline data for indicators.

        Retrieves historical kline data from Bybit for the specified timeframe
        and symbol to initialize indicator calculations.

        Args:
            timeframe (str): The kline interval (e.g., "15", "60", "D").

        Returns:
            bool: True if data fetching was successful, False otherwise.
        """
        self.bot_state.add_log(
            f"Fetching initial {self.config.LOOKBACK_PERIODS} klines for {self.config.SYMBOL} on {timeframe} TF...",
            "INFO",
        )
        result = self._api_call(
            self.session.get_kline,
            category=self.config.CATEGORY,
            symbol=self.config.SYMBOL,
            interval=timeframe,
            limit=self.config.LOOKBACK_PERIODS,
        )
        if result and result.get("list"):
            df = pd.DataFrame(
                result["list"],
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "turnover",
                ],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df.dropna(inplace=True)  # Drop rows with NaN from conversion errors
            if df.empty:
                self.bot_state.add_log(
                    f"Fetched kline data for {timeframe} is empty after cleanup.",
                    "WARNING",
                )
                return False

            with self.bot_state.lock:
                self.klines_dfs[timeframe] = df.sort_values("timestamp").reset_index(
                    drop=True
                )
                if not df.empty:
                    self.last_kline_timestamp[timeframe] = df["timestamp"].iloc[-1]
            self.bot_state.add_log(
                f"Initial kline data fetched successfully for {timeframe} ({len(df)} candles).",
                "SUCCESS",
            )
            return True
        self.bot_state.add_log(
            f"Failed to fetch initial kline data for {timeframe}. Result: {result}",
            "ERROR",
        )
        return False

    def _update_kline_data(self, kline: dict[str, Any], timeframe: str):
        """Updates the main kline DataFrame with a new candle.

        Appends the new kline data and removes the oldest to maintain a fixed
        lookback window for indicator calculations.

        Args:
            kline (dict): The new kline data received from the WebSocket.
            timeframe (str): The timeframe of the kline data.
        """
        new_row = {
            "timestamp": datetime.fromtimestamp(
                int(kline["start"]) / 1000, tz=timezone.utc
            ),
            "open": Decimal(kline["open"]),
            "high": Decimal(kline["high"]),
            "low": Decimal(kline["low"]),
            "close": Decimal(kline["close"]),
            "volume": Decimal(kline["volume"]),
            "turnover": Decimal(kline["turnover"]),
        }
        with self.bot_state.lock:
            df = self.klines_dfs.get(timeframe)
            if df is None:
                self.logger.warning(
                    f"DataFrame for {timeframe} not initialized. Cannot update kline."
                )
                return

            # Append new row and drop oldest
            # Use pd.concat for better performance and to avoid SettingWithCopyWarning
            new_df_row = pd.DataFrame(
                [new_row], index=[new_row["timestamp"]]
            )  # Use timestamp as index
            # Drop the first row by index
            if not df.empty:
                df = pd.concat([df.iloc[1:], new_df_row])
            else:
                df = new_df_row

            df.reset_index(
                drop=True, inplace=True
            )  # Reset index after dropping first row
            self.klines_dfs[timeframe] = df
            self.logger.debug(
                f"Kline data updated for {timeframe}. New length: {len(df)}"
            )

    def _calculate_all_timeframe_indicators(self):
        """Calculates indicators for all active timeframes.

        Iterates through all configured timeframes, calculates indicators for each,
        and updates the bot's state with primary timeframe indicators for UI display.
        """
        with self.bot_state.lock:
            for tf, df in self.klines_dfs.items():
                if df.empty:
                    self.logger.warning(
                        f"DataFrame for {tf} is empty, skipping indicator calculation."
                    )
                    continue

                processed_df = self.indicator_calculator.calculate_all_indicators(
                    df.copy()
                )  # Use copy to avoid SettingWithCopyWarning
                self.klines_dfs[tf] = processed_df

                if tf == self.config.PRIMARY_TIMEFRAME and not processed_df.empty:
                    # Update bot_state with primary TF indicators for UI
                    latest_indicators_series = processed_df.iloc[-1]
                    # Filter out non-indicator columns for display
                    self.bot_state.indicator_values = {
                        k: v
                        for k, v in latest_indicators_series.items()
                        if k
                        not in [
                            "timestamp",
                            "open",
                            "high",
                            "low",
                            "close",
                            "volume",
                            "turnover",
                        ]
                    }
                    self.bot_state.supertrend_line = Decimal(
                        str(latest_indicators_series.get("supertrend_line", "0"))
                    )
                    self.bot_state.supertrend_direction = (
                        "Uptrend"
                        if latest_indicators_series.get("supertrend_direction") == 1
                        else "Downtrend"
                        if latest_indicators_series.get("supertrend_direction") == -1
                        else "Neutral"
                    )

                    # Update MarketData for primary TF with latest candle data
                    self.bot_state.market_data[tf] = MarketData(
                        timestamp=latest_indicators_series["timestamp"],
                        open=Decimal(str(latest_indicators_series["open"])),
                        high=Decimal(str(latest_indicators_series["high"])),
                        low=Decimal(str(latest_indicators_series["low"])),
                        close=Decimal(str(latest_indicators_series["close"])),
                        volume=Decimal(str(latest_indicators_series["volume"])),
                        # Preserve existing real-time ticker/orderbook info
                        bid=self.bot_state.market_data[tf].bid,
                        ask=self.bot_state.market_data[tf].ask,
                        spread_pct=self.bot_state.market_data[tf].spread_pct,
                        order_book_imbalance=self.bot_state.market_data[
                            tf
                        ].order_book_imbalance,
                        vwap=self.bot_state.market_data[tf].vwap,
                        poc=self.bot_state.market_data[tf].poc,
                    )
            self.logger.debug("Indicators calculated for all timeframes.")

    def _analyze_market_conditions(self):
        """Analyzes current market conditions.

        Determines the market regime, calculates support/resistance levels,
        and analyzes volume profiles using the MarketAnalyzer. Updates the
        bot's state with the findings.
        """
        primary_df = self.klines_dfs.get(self.config.PRIMARY_TIMEFRAME)
        if primary_df is None or primary_df.empty:
            self.logger.warning(
                "No primary timeframe data available for market condition analysis."
            )
            return

        # Analyze Market Regime
        regime = self.market_analyzer.analyze_market_regime(primary_df.copy())
        with self.bot_state.lock:
            self.bot_state.market_regime = regime

        # Analyze Volume Profile
        if self.config.USE_VOLUME_PROFILE:
            vol_profile_data = self.market_analyzer.analyze_volume_profile(
                primary_df.copy()
            )
            if vol_profile_data:
                with self.bot_state.lock:
                    self.bot_state.market_data[
                        self.config.PRIMARY_TIMEFRAME
                    ].poc = vol_profile_data.get("poc", Decimal("0"))
                    self.bot_state.market_data[
                        self.config.PRIMARY_TIMEFRAME
                    ].vwap = vol_profile_data.get("vwap", Decimal("0"))

        # Support/Resistance (currently not directly stored in bot_state for UI, but could be added)
        # sr_levels = self.market_analyzer.calculate_support_resistance(primary_df.copy())
        # self.logger.debug(f"Support/Resistance Levels: {sr_levels}")

    def _update_position_state(self):
        """Updates the bot's internal position state based on Bybit's data.

        Fetches current position details from the Bybit API via REST and
        updates the bot_state.position object accordingly.
        """
        try:
            # Fetch current position from Bybit API
            response = self._api_call(
                self.session.get_positions,
                category=self.config.CATEGORY,
                symbol=self.config.SYMBOL,
            )

            if response and "list" in response:
                current_pos_data = None
                for pos_data in response.get("list", []):
                    # Filter for our symbol and positions with size > 0
                    if pos_data["symbol"] == self.config.SYMBOL and Decimal(
                        pos_data.get("size", "0")
                    ) > Decimal("0"):
                        # If in hedge mode, ensure we pick the correct position (Long/Short)
                        if self.config.HEDGE_MODE:
                            if (
                                self.config.POSITION_IDX == 1
                                and pos_data["side"] == "Buy"
                            ) or (
                                self.config.POSITION_IDX == 2
                                and pos_data["side"] == "Sell"
                            ):
                                current_pos_data = pos_data
                                break
                        else:  # One-way mode, only one position possible
                            current_pos_data = pos_data
                            break

                with self.bot_state.lock:
                    if current_pos_data:
                        side = current_pos_data["side"]
                        size = Decimal(current_pos_data["size"])
                        entry_price = Decimal(current_pos_data["avgPrice"])
                        unrealized_pnl = Decimal(current_pos_data["unrealisedPnl"])
                        stop_loss = Decimal(current_pos_data.get("stopLoss", "0"))
                        take_profit = Decimal(current_pos_data.get("takeProfit", "0"))

                        if (
                            self.bot_state.position
                            and self.bot_state.position.symbol == self.config.SYMBOL
                        ):
                            # Update existing position
                            self.bot_state.position.side = side
                            self.bot_state.position.size = size
                            self.bot_state.position.entry_price = entry_price
                            self.bot_state.position.unrealized_pnl = unrealized_pnl
                            self.bot_state.position.stop_loss = stop_loss
                            self.bot_state.position.take_profit = take_profit
                            # Breakeven/trailing/partial flags are managed by _manage_active_position.
                            # We might need to persist these flags in state_file if we want them to survive restarts.
                            # For now, if API updates, these are reset locally to be re-evaluated.
                            self.logger.debug(
                                f"Existing position state updated from API: {side} {size:.4f} @ {entry_price:.4f}"
                            )
                        else:
                            # Create new position object (happens after an order is filled)
                            self.bot_state.position = Position(
                                symbol=self.config.SYMBOL,
                                side=side,
                                size=size,
                                entry_price=entry_price,
                                unrealized_pnl=unrealized_pnl,
                                stop_loss=stop_loss,
                                take_profit=take_profit,
                                entry_time=datetime.now(
                                    timezone.utc
                                ),  # Approximation, actual entry time might be harder to get
                            )
                            self.bot_state.add_log(
                                f"New position opened via API: {side} {size:.4f} @ {entry_price:.4f}",
                                "INFO",
                            )
                    else:
                        # No active position found for the symbol
                        if (
                            self.bot_state.position
                            and self.bot_state.position.symbol == self.config.SYMBOL
                        ):
                            self.bot_state.add_log(
                                "Position closed (no active position found in API).",
                                "INFO",
                            )
                            # Log the closed trade if it was a valid position
                            if self.bot_state.position.size > Decimal("0"):
                                self._log_closed_trade(
                                    self.bot_state.position, "Position Closed (API)"
                                )
                            self.bot_state.position = None
                        # else: position was already None, no change needed.
            else:
                error_msg = (
                    response.get("retMsg", "Unknown error")
                    if response
                    else "No response"
                )
                self.logger.error(
                    f"Failed to get positions for {self.config.SYMBOL}: {error_msg}"
                )

        except Exception as e:
            self.bot_state.add_log(f"Error updating position state: {e}", "ERROR")
            self.logger.error(f"Error updating position state: {e}", exc_info=True)

    def _get_account_balance(self) -> Decimal:
        """Fetches the account balance for the configured currency.

        Retrieves the available balance for the quote currency (e.g., USDT)
        from the Bybit API.

        Returns:
            Decimal: The available balance, or Decimal('0') if retrieval fails.
        """
        try:
            # Unified account uses accountType="UNIFIED"
            # For SPOT, it's accountType="SPOT"
            account_type = (
                "UNIFIED" if self.config.CATEGORY_ENUM != Category.SPOT else "SPOT"
            )

            # Use quote currency (USDT in BTCUSDT) to determine available capital for trading
            # For linear/inverse, often USDT. For spot, it could be base or quote.
            # Assuming trading against USDT for simplicity here.
            quote_currency = (
                "USDT"  # Default to USDT, adjust if other quote currencies are used
            )

            response = self._api_call(
                self.session.get_wallet_balance, accountType=account_type
            )

            if response and "list" in response:
                for account_info in response["list"]:
                    for coin_data in account_info.get(
                        "coin", []
                    ):  # Bybit response structure
                        if coin_data.get("coin") == quote_currency:
                            # Use availableBalance for trading decisions
                            balance = Decimal(
                                coin_data.get("availableToWithdraw", "0")
                            )  # availableToWithdraw or walletBalance
                            return balance
                self.logger.warning(
                    f"Balance for coin {quote_currency} not found in wallet response for {account_type} account."
                )
            else:
                self.logger.warning(
                    f"Wallet balance response was empty or invalid: {response}"
                )
        except Exception as e:
            self.bot_state.add_log(f"Failed to get account balance: {e}", "ERROR")
            self.logger.error(f"Failed to get account balance: {e}", exc_info=True)
        return Decimal("0")

    def _set_leverage_and_margin(self) -> bool:
        """Sets leverage and margin mode for the trading symbol.

        Configures the leverage and margin mode (e.g., 'Both' for cross margin)
        for the specified symbol and category according to the bot's configuration.
        """
        if self.config.CATEGORY_ENUM == Category.SPOT:
            self.logger.info("Leverage setting is not applicable for SPOT category.")
            return True

        try:
            leverage_str = str(self.config.LEVERAGE)
            self.logger.info(
                f"Setting leverage to {leverage_str}x for {self.config.SYMBOL}..."
            )

            # Set leverage
            leverage_response = self._api_call(
                self.session.set_leverage,
                category=self.config.CATEGORY,
                symbol=self.config.SYMBOL,
                buyLeverage=leverage_str,
                sellLeverage=leverage_str,
            )
            if leverage_response and leverage_response.get("retCode") == 0:
                self.logger.info(f"Leverage set successfully to {leverage_str}x.")
            elif (
                leverage_response
                and "leverage is already set"
                in leverage_response.get("retMsg", "").lower()
            ):
                self.logger.info(
                    f"Leverage for {self.config.SYMBOL} is already {leverage_str}x. No change needed."
                )
            else:
                self.logger.warning(
                    f"Failed to set leverage for {self.config.SYMBOL}: {leverage_response.get('retMsg', 'Unknown error')}"
                )
                return False

            # Set margin mode to 'Both' (Cross Margin) if not already set.
            # 'is_isolated=False' for cross margin.
            self.logger.info(
                f"Setting margin mode to Cross Margin for {self.config.SYMBOL}..."
            )
            margin_mode_response = self._api_call(
                self.session.switch_isolated_margin,
                category=self.config.CATEGORY,
                symbol=self.config.SYMBOL,
                tradeMode=0,  # 0 for Cross Margin
                buyLeverage=leverage_str,
                sellLeverage=leverage_str,
            )
            if margin_mode_response and margin_mode_response.get("retCode") == 0:
                self.logger.info("Margin mode set to Cross Margin successfully.")
            elif (
                margin_mode_response
                and "no actual change" in margin_mode_response.get("retMsg", "").lower()
            ):
                self.logger.info(
                    f"Margin mode for {self.config.SYMBOL} is already Cross Margin. No change needed."
                )
            else:
                self.logger.warning(
                    f"Failed to set margin mode to Cross Margin for {self.config.SYMBOL}: {margin_mode_response.get('retMsg', 'Unknown error')}"
                )
                # This is often account configuration specific, might not be a critical failure to stop bot.
                # However, for new setup, it's good to ensure.
                return False
            return True

        except Exception as e:
            self.bot_state.add_log(
                f"Error setting leverage or margin mode: {e}", "ERROR"
            )
            self.logger.error(
                f"Error setting leverage or margin mode: {e}", exc_info=True
            )
            return False

    def _place_order(
        self,
        side: str,
        qty: Decimal,
        order_type: OrderType,
        entry_price: Decimal,
        sl: Decimal,
        tp: Decimal,
        is_partial_close: bool = False,
        order_link_id: str | None = None,
    ) -> str | None:
        """Places an order (Market, Limit) with SL/TP.

        Args:
            side (str): "Buy" or "Sell".
            qty (Decimal): The quantity to trade.
            order_type (OrderType): The type of order ("Market" or "Limit").
            entry_price (Decimal): The desired entry price (used for limit orders or logging).
            sl (Decimal): The stop loss price.
            tp (Decimal): The take profit price.
            is_partial_close (bool): Flag indicating if this is a partial close order.
            order_link_id (str | None): A unique ID for the order, useful for tracking.

        Returns:
            str | None: The Bybit order ID if successful, otherwise None.
        """
        specs = self.precision_manager.get_specs(
            self.config.SYMBOL, self.config.CATEGORY_ENUM
        )
        if not specs:
            self.bot_state.add_log(
                "Cannot place order: Instrument specs not available.", "ERROR"
            )
            return None

        # Ensure quantity is rounded correctly
        qty_rounded = self.precision_manager.round_quantity(specs, qty)
        if qty_rounded < specs.min_order_qty:
            self.bot_state.add_log(
                f"Order quantity {qty_rounded:.4f} is below minimum {specs.min_order_qty}. Cannot place order.",
                "ERROR",
            )
            return None

        order_params = {
            "category": self.config.CATEGORY,
            "symbol": self.config.SYMBOL,
            "side": side,
            "orderType": order_type.value,
            "qty": str(qty_rounded),
            "timeInForce": "GTC",  # Good Till Cancelled
            "reduceOnly": self.config.REDUCE_ONLY if not is_partial_close else True,
            "positionIdx": self.config.POSITION_IDX,
        }

        # Add price for limit orders or adjust market entry price
        if order_type == OrderType.LIMIT:
            limit_price = entry_price
            if side == "Buy":
                limit_price = entry_price * (
                    Decimal("1") - (self.config.LIMIT_ORDER_OFFSET_PCT / Decimal("100"))
                )
            else:  # Sell
                limit_price = entry_price * (
                    Decimal("1") + (self.config.LIMIT_ORDER_OFFSET_PCT / Decimal("100"))
                )
            order_params["price"] = str(
                self.precision_manager.round_price(specs, limit_price)
            )
            if self.config.POST_ONLY_LIMIT_ORDERS:
                order_params["orderFilter"] = (
                    "PostOnly"  # Use 'PostOnly' for maker fees
                )
        elif order_type == OrderType.MARKET:
            # For market orders, no price needed in place_order, it uses market price.
            pass

        # Add SL/TP for derivatives if not spot
        if self.config.CATEGORY_ENUM != Category.SPOT:
            if sl > Decimal("0"):
                order_params["stopLoss"] = str(
                    self.precision_manager.round_price(specs, sl)
                )
            if tp > Decimal("0"):
                order_params["takeProfit"] = str(
                    self.precision_manager.round_price(specs, tp)
                )

            if "stopLoss" in order_params or "takeProfit" in order_params:
                order_params["tpslMode"] = "Full"  # 'Full' or 'Partial' for derivatives

        if order_link_id:
            order_params["orderLinkId"] = order_link_id
        else:
            order_params["orderLinkId"] = (
                f"bot_{side}_{int(time.time())}"  # Generate a unique ID
            )

        try:
            self.logger.info(f"Placing order with params: {order_params}")
            response = self._api_call(self.session.place_order, **order_params)

            if response and "orderId" in response.get("result", {}):
                order_id = response["result"]["orderId"]
                self.bot_state.add_log(
                    f"Order placed successfully: ID {order_id}", "SUCCESS"
                )
                return order_id
            else:
                error_msg = (
                    response.get("retMsg", "Unknown error during order placement")
                    if response
                    else "No response received"
                )
                self.bot_state.add_log(f"Failed to place order: {error_msg}", "ERROR")
                self.logger.error(f"Failed to place order: {response}")
                return None
        except Exception as e:
            self.bot_state.add_log(f"Exception during order placement: {e}", "ERROR")
            self.logger.error(f"Exception during order placement: {e}", exc_info=True)
            return None

    def _update_trading_stop(
        self, stop_loss: Decimal | None = None, take_profit: Decimal | None = None
    ) -> bool:
        """Updates the stop loss and/or take profit for an active position.

        Args:
            stop_loss (Decimal | None): The new stop loss price. If None, SL is not updated.
            take_profit (Decimal | None): The new take profit price. If None, TP is not updated.

        Returns:
            bool: True if the update was successful, False otherwise.
        """
        pos = self.bot_state.position
        if not pos:
            self.bot_state.add_log(
                "Cannot update stop loss/take profit: No active position.", "WARNING"
            )
            return False

        if self.config.CATEGORY_ENUM == Category.SPOT:
            self.logger.warning(
                "Stop loss/take profit updates are not directly supported for SPOT category via set_trading_stop."
            )
            return False

        specs = self.precision_manager.get_specs(
            self.config.SYMBOL, self.config.CATEGORY_ENUM
        )
        if not specs:
            self.bot_state.add_log(
                "Cannot update stop loss/take profit: Instrument specs not available.",
                "ERROR",
            )
            return False

        # Prepare parameters for set_trading_stop
        params = {
            "category": self.config.CATEGORY,
            "symbol": self.config.SYMBOL,
            "positionIdx": self.config.POSITION_IDX,  # Crucial for hedge mode, or 0 for one-way
        }

        # Ensure prices are rounded correctly and are valid
        if stop_loss is not None:
            stop_loss = self.precision_manager.round_price(specs, stop_loss)
            # Validate SL price based on position side
            if (pos.side == "Buy" and stop_loss >= pos.current_price) or (
                pos.side == "Sell" and stop_loss <= pos.current_price
            ):
                self.bot_state.add_log(
                    f"Calculated SL {stop_loss:.4f} invalid for {pos.side} position at {pos.current_price:.4f}. Skipping SL update.",
                    "WARNING",
                )
                stop_loss = None  # Invalidate SL
            else:
                params["stopLoss"] = str(stop_loss)

        if take_profit is not None:
            take_profit = self.precision_manager.round_price(specs, take_profit)
            # Validate TP price based on position side
            if (pos.side == "Buy" and take_profit <= pos.current_price) or (
                pos.side == "Sell" and take_profit >= pos.current_price
            ):
                self.bot_state.add_log(
                    f"Calculated TP {take_profit:.4f} invalid for {pos.side} position at {pos.current_price:.4f}. Skipping TP update.",
                    "WARNING",
                )
                take_profit = None  # Invalidate TP
            else:
                params["takeProfit"] = str(take_profit)

        if "stopLoss" not in params and "takeProfit" not in params:
            self.bot_state.add_log("No valid SL or TP provided for update.", "WARNING")
            return False

        try:
            response = self._api_call(self.session.set_trading_stop, **params)

            if response and response.get("retCode") == 0:
                self.bot_state.add_log(
                    "Trading stop/take profit updated successfully.", "SUCCESS"
                )
                # Update local state if successful
                with self.bot_state.lock:
                    if stop_loss is not None:
                        pos.stop_loss = stop_loss
                    if take_profit is not None:
                        pos.take_profit = take_profit
                return True
            else:
                error_msg = (
                    response.get("retMsg", "Unknown error")
                    if response
                    else "No response"
                )
                self.bot_state.add_log(
                    f"Failed to update trading stop/take profit: {error_msg}", "ERROR"
                )
                return False
        except Exception as e:
            self.bot_state.add_log(
                f"Exception updating trading stop/take profit: {e}", "ERROR"
            )
            self.logger.error(
                f"Exception updating trading stop/take profit: {e}", exc_info=True
            )
            return False

    def _close_position(self, partial_qty: Decimal | None = None) -> bool:
        """Closes the current active position, either partially or fully.

        Args:
            partial_qty (Decimal | None): The quantity to close. If None, the entire position is closed.

        Returns:
            bool: True if the close order was placed successfully, False otherwise.
        """
        pos = self.bot_state.position
        if not pos:
            self.bot_state.add_log(
                "Cannot close position: No active position.", "WARNING"
            )
            return False

        specs = self.precision_manager.get_specs(
            self.config.SYMBOL, self.config.CATEGORY_ENUM
        )
        if not specs:
            self.bot_state.add_log(
                "Cannot close position: Instrument specs not available.", "ERROR"
            )
            return False

        qty_to_close = partial_qty if partial_qty else pos.size
        qty_to_close = self.precision_manager.round_quantity(specs, qty_to_close)

        if qty_to_close < specs.min_order_qty:
            self.bot_state.add_log(
                f"Quantity to close ({qty_to_close:.4f}) is below minimum {specs.min_order_qty}. Cannot close.",
                "WARNING",
            )
            return False

        # Determine order side for closing
        close_side = "Sell" if pos.side == "Buy" else "Buy"
        close_price = self.bot_state.current_price  # For market close

        self.bot_state.add_log(
            f"Attempting to close {qty_to_close:.4f} of {pos.symbol} {pos.side} position.",
            "INFO",
        )

        # Place a market order to close the position
        order_id = self._place_order(
            side=close_side,
            qty=qty_to_close,
            order_type=OrderType.MARKET,
            entry_price=close_price,  # Use current price as reference for market order
            sl=Decimal("0"),  # SL/TP are not set for closing orders
            tp=Decimal("0"),
            is_partial_close=True if partial_qty else False,
            order_link_id=f"close_{pos.order_id}_{int(time.time())}"
            if pos.order_id
            else f"close_auto_{int(time.time())}",
        )

        if order_id:
            self.bot_state.add_log(
                f"Close order {order_id} placed for {qty_to_close:.4f} of {pos.symbol}.",
                "SUCCESS",
            )
            # Update local position size immediately. Full position update comes from WebSocket.
            with self.bot_state.lock:
                pos.size -= qty_to_close
                if pos.size <= specs.min_order_qty:  # If position is effectively closed
                    self.bot_state.add_log(
                        f"Position for {pos.symbol} fully closed locally.", "INFO"
                    )
                    self._log_closed_trade(pos, "Full Position Closed")
                    self.bot_state.position = None
            return True
        else:
            self.bot_state.add_log("Failed to place close order.", "ERROR")
            return False

    def _log_closed_trade(self, position: Position, exit_reason: str):
        """Logs a completed trade using the PerformanceMetrics and Trade history.

        Calculates PnL, duration, and other metrics for a closed position and
        adds it to the bot's performance tracking.

        Args:
            position (Position): The closed position object.
            exit_reason (str): The reason for closing the trade (e.g., "Stop Loss Hit").
        """
        if not position:
            return

        specs = self.precision_manager.get_specs(
            position.symbol, self.config.CATEGORY_ENUM
        )
        if not specs:
            self.logger.error("Could not get instrument specs to log closed trade.")
            return

        # Assuming current_price is the exit price for simplicity.
        # For more accuracy, real_PnL from API trade history should be used.
        exit_price = position.current_price
        pnl = position.unrealized_pnl  # This is the PnL at the time of position update
        pnl_pct = position.pnl_pct

        # For accurate fees, need to fetch from Bybit transaction history.
        # For now, default to 0 or a simple calculation.
        estimated_fees = Decimal("0")  # placeholder

        trade = Trade(
            symbol=position.symbol,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            size=position.size,  # This should be the original entry size, not remaining
            pnl=pnl,
            pnl_pct=pnl_pct,
            entry_time=position.entry_time,
            exit_time=datetime.now(timezone.utc),
            duration=position.duration,
            exit_reason=exit_reason,
            fees=estimated_fees,
        )

        with self.bot_state.lock:
            self.bot_state.metrics.update(trade, self.bot_state.account_balance)
            self.bot_state.trade_history.append(trade)
            # If SAVE_TRADES_CSV is enabled, append to CSV
            if self.config.SAVE_TRADES_CSV:
                self._save_trade_to_csv(trade)

        self.bot_state.add_log(
            f"Trade closed: {trade.side} {trade.size:.4f} {trade.symbol} | PnL: ${trade.pnl:,.2f} ({trade.pnl_pct:+.2f}%) | Reason: {exit_reason}",
            "SUCCESS",
        )
        self.logger.info(f"Trade logged: {trade}")

    def _save_trade_to_csv(self, trade: Trade):
        """Appends a completed trade to a CSV file."""
        file_exists = Path(self.config.TRADES_FILE).is_file()
        with open(self.config.TRADES_FILE, "a", newline="") as f:
            headers = [
                "symbol",
                "side",
                "entry_price",
                "exit_price",
                "size",
                "pnl",
                "pnl_pct",
                "entry_time",
                "exit_time",
                "duration_seconds",
                "exit_reason",
                "fees",
            ]
            writer = csv.DictWriter(f, fieldnames=headers)

            if not file_exists:
                writer.writeheader()

            trade_dict = asdict(trade)
            trade_dict["duration_seconds"] = trade.duration.total_seconds()
            writer.writerow(trade_dict)
        self.logger.debug(f"Trade appended to {self.config.TRADES_FILE}")

    def _install_signal_handlers(self):
        """Installs signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        """Handles signals for graceful shutdown."""
        self.bot_state.add_log(
            f"Received signal {sig}. Shutting down gracefully...", "INFO"
        )
        self.logger.warning(f"Received signal {sig}. Initiating graceful shutdown.")
        with self.bot_state.lock:
            self.bot_state.stop_requested = True
        self.stop_event.set()  # Signal main loop to stop

    def _state_saver_loop(self):
        """Periodically saves the bot's state to a file."""
        while not self.bot_state.stop_requested and not self.stop_event.is_set():
            time.sleep(self.config.SAVE_STATE_INTERVAL)
            if (
                not self.bot_state.stop_requested and not self.stop_event.is_set()
            ):  # Check again after sleep
                self.bot_state.save_state(self.config.STATE_FILE)

    def cleanup(self):
        """Performs cleanup operations before the bot exits."""
        self.bot_state.add_log("Performing cleanup...", "INFO")
        self.logger.info("Starting bot cleanup process...")

        self._close_websockets()  # Close WebSocket connections

        # Optional: Close any open positions if configured
        if self.config.AUTO_CLOSE_ON_SHUTDOWN and self.bot_state.position:
            self.bot_state.add_log(
                "Auto-close on shutdown enabled. Attempting to close open position.",
                "WARNING",
            )
            self._close_position()  # This will log the trade
        elif self.bot_state.position:
            self.bot_state.add_log(
                "Bot shutting down with open position. Manual intervention may be required.",
                "WARNING",
            )
            self.logger.warning(
                "Bot shutting down with open position. Manual intervention may be required."
            )
            # Ensure position is logged as an open position that was not gracefully closed
            # This is a bit tricky since PnL isn't realized, but could be logged as 'Unrealized PnL at shutdown'
            self._log_closed_trade(
                self.bot_state.position, "Shutdown (Unclosed Position)"
            )

        # Save final state, including any last trades
        self.bot_state.save_state(self.config.STATE_FILE)

        if self.ui and self.ui.is_alive():
            self.ui.stop()
            self.ui.join(timeout=5)  # Wait for UI thread to finish

        # Ensure state saver thread also stops
        if self.state_saver_thread and self.state_saver_thread.is_alive():
            # Signal the thread to stop and wait for it
            self.state_saver_thread.join(timeout=5)

        final_balance = self._get_account_balance()  # Fetch final balance
        if final_balance > Decimal("0"):
            with self.bot_state.lock:
                total_pnl = final_balance - self.bot_state.initial_balance
                total_pnl_pct = (
                    (total_pnl / self.bot_state.initial_balance * 100)
                    if self.bot_state.initial_balance > Decimal("0")
                    else Decimal("0")
                )
            self.bot_state.add_log("=" * 60, "INFO")
            self.bot_state.add_log("Supertrend Trading Bot Stopped.", "INFO")
            self.bot_state.add_log(f"Final Balance: {final_balance:,.2f} USDT", "INFO")
            self.bot_state.add_log(
                f"Total PnL: {total_pnl:,.2f} USDT ({total_pnl_pct:+.2f}%)", "INFO"
            )
            self.bot_state.add_log("=" * 60, "INFO")
        else:
            self.bot_state.add_log(
                "Final balance retrieval failed or zero. Cannot calculate total PnL.",
                "WARNING",
            )

        self.logger.info("Bot shut down successfully.")
        print("\nBot has been shut down. Check bot_activity.log for details.")


# =====================================================================
# MAIN EXECUTION
# =====================================================================

if __name__ == "__main__":
    import csv  # Import csv here to avoid circular dependencies if used only in cleanup

    bot_instance = None
    try:
        # Load configuration
        config = EnhancedConfig()

        # Initialize bot
        bot_instance = AdvancedSupertrendBot(config)

        # Run the bot
        bot_instance.run()

    except ValueError as ve:
        print(f"\nConfiguration Error: {ve}")
        sys.exit(1)
    except Exception as e:
        # Catch any unexpected errors during initialization or run
        print(f"\nFATAL ERROR: An unhandled exception occurred: {e}")
        # Attempt to log the error if bot_instance was initialized
        if bot_instance:
            bot_instance.logger.critical(f"FATAL ERROR: {e}", exc_info=True)
            bot_instance.cleanup()  # Attempt cleanup even on fatal error
        else:  # Fallback logger if bot_instance creation failed early
            logging.basicConfig(
                level=logging.CRITICAL,
                format="%(asctime)s | FATAL - %(message)s",
                datefmt="%H:%M:%S",
            )
            logging.critical(f"FATAL ERROR: {e}", exc_info=True)
        sys.exit(1)
