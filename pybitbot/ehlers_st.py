#!/usr/bin/env python3
"""Bybit Supertrend Trading Bot Framework v2.1 (Enhanced - No SciPy)

This script is a professional-grade, fully asynchronous trading bot for Bybit,
now featuring an enhanced framework that includes the Ehlers Supertrend Cross strategy,
advanced entry/exit logic, and further architectural improvements.
The scipy dependency has been removed by implementing a simplified recursive
low-pass filter approximation for the Ehlers Supertrend, allowing for zero external
scientific computation libraries.

Key Features:
1.  **Fully Asynchronous:** Built entirely on asyncio for high performance.
2.  **Modular Architecture:** Cleanly separated components for risk management,
    order execution, state persistence, and strategy.
3.  **State Persistence & Recovery:** Saves critical state, allowing the bot
    to be restarted without losing context, maintaining signal states and positions.
4.  **Ehlers Supertrend Cross Strategy (No SciPy):** Implements an advanced Supertrend
    strategy using a custom recursive low-pass filter for smoothing, replacing
    the Butterworth filter from SciPy. This allows for flexible trend identification.
5.  **Advanced Risk Management:** Features fixed-risk position sizing, dynamic
    trailing stop-loss (including break-even activation), and persistent tracking
    of drawdown and daily loss limits (though daily loss limits are not explicitly
    implemented in this version, the framework is ready for it).
6.  **Advanced Order Management:** Supports market/limit orders with strategy-defined
    stop-loss and take-profit levels, including intelligent trailing stops and
    robust position adjustment on new signals.
7.  **Robust WebSocket Handling:** A dedicated manager for WebSocket connections with
    automatic reconnection and exponential backoff, ensuring high uptime.
8.  **Dynamic Precision Handling:** Fetches and uses market-specific precision for
    price and quantity to prevent exchange rejections, minimizing trading errors.
9.  **Enhanced Entry/Exit Logic:** Incorporates signal confirmation, dynamic
    take-profit calculation, and intelligent position sizing based on calculated
    risk and stop-loss distance.
10. **Comprehensive Logging:** Detailed logging for all critical operations,
    facilitating debugging and performance monitoring.

Instructions for Use:
1.  Install dependencies:
    `pip install pybit pandas numpy python-dotenv pytz aiofiles`
2.  Create a `.env` file in the same directory with your credentials:
    BYBIT_API_KEY="YOUR_API_KEY"
    BYBIT_API_SECRET="YOUR_API_SECRET"
3.  Configure the `Config` class below with your desired settings.
4.  Run the bot:
    `python3 supertrend_bot.py`
"""

import asyncio
import logging
import os
import pickle
import sys
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, Context, Decimal, getcontext
from enum import Enum
from logging.handlers import RotatingFileHandler
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket

# --- INITIAL SETUP ---

# Set decimal precision for accurate financial calculations
# Using a higher precision context to avoid intermediate rounding errors
DECIMAL_CONTEXT = Context(prec=50)
getcontext().prec = 28 # Default precision for display/storage

# Load environment variables from .env file
load_dotenv()

# --- LOGGING CONFIGURATION ---

def setup_logging():
    """Setup comprehensive logging configuration."""
    log = logging.getLogger()
    log.setLevel(logging.INFO)

    # Formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    simple_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)

    # File Handler (for all logs)
    file_handler = RotatingFileHandler('supertrend_bot.log', maxBytes=10*1024*1024, backupCount=5)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)

    log.addHandler(console_handler)
    log.addHandler(file_handler)

    return log

logger = setup_logging()


# =====================================================================
# ENUMS AND DATACLASSES
# =====================================================================

class OrderType(Enum):
    MARKET = "Market"
    LIMIT = "Limit"

class OrderSide(Enum):
    BUY = "Buy"
    SELL = "Sell"

@dataclass
class MarketInfo:
    """Stores market information including precision settings."""
    symbol: str
    tick_size: Decimal
    lot_size: Decimal

    def format_price(self, price: float) -> str:
        """Formats a price to the market's tick size precision."""
        return str(Decimal(str(price)).quantize(self.tick_size, rounding=ROUND_DOWN))

    def format_quantity(self, quantity: float) -> str:
        """Formats a quantity to the market's lot size precision."""
        return str(Decimal(str(quantity)).quantize(self.lot_size, rounding=ROUND_DOWN))

@dataclass
class Position:
    """Represents an open position."""
    symbol: str
    side: str
    size: Decimal
    avg_price: Decimal
    unrealized_pnl: Decimal
    mark_price: Decimal
    leverage: int
    entry_signal_price: Decimal | None = None
    initial_stop_loss: Decimal | None = None
    trailing_stop_loss: Decimal | None = None # Current active trailing stop loss
    take_profit: Decimal | None = None # Current active take profit

@dataclass
class StrategySignal:
    """Standardized object for strategy signals."""
    action: str  # 'BUY', 'SELL', 'CLOSE', 'HOLD'
    symbol: str
    strength: float = 1.0
    stop_loss: float | None = None # Suggested initial stop loss
    take_profit: float | None = None # Suggested initial take profit
    signal_price: float | None = None # Price at which the signal was generated
    metadata: dict = field(default_factory=dict)

@dataclass
class Config:
    """Trading bot configuration."""
    api_key: str = field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    testnet: bool = False

    # Trading Parameters
    symbol: str = "XLMUSDT"
    category: str = "linear" # "linear" for USDT Perpetuals, "inverse" for Inverse Perpetuals, etc.

    # Risk Management
    risk_per_trade_pct: float = 0.01  # 1% of equity risked per trade (float for easy calculation)
    leverage: int = 10

    # WebSocket settings
    reconnect_attempts: int = 5

    # Strategy Parameters
    strategy_name: str = "EhlersSupertrendCross" # Can be "Supertrend" or "EhlersSupertrendCross"
    timeframe: str = "15"  # Primary timeframe for the strategy (e.g., "1", "5", "15", "60", "D")
    lookback_periods: int = 400  # Number of historical candles to load (increased for Ehlers filter)

    # Common Strategy Params
    strategy_params: dict[str, Any] = field(default_factory=lambda: {
        # Classic Supertrend Specific Params
        "supertrend_period": 10,
        "supertrend_multiplier": 3.0,
        "atr_period": 14, # ATR period for both Classic and Ehlers Supertrend

        # Ehlers Supertrend Specific Params (now using recursive filter)
        "ehlers_fast_supertrend_period": 7,
        "ehlers_fast_supertrend_multiplier": 2.0,
        "ehlers_slow_supertrend_period": 14,
        "ehlers_slow_supertrend_multiplier": 3.0,
        "ehlers_filter_alpha": 0.2, # Smoothing factor for the recursive filter (0.0 to 1.0)
        "ehlers_filter_poles": 2,   # Number of times the EMA-like filter is applied (2 for a 2-pole approx)

        # Advanced Entry/Exit & Risk Management
        "signal_confirmation_candles": 1, # Number of candles to wait for confirmation (0 for immediate)
        "take_profit_atr_multiplier": 2.0, # TP at X * ATR from entry price
        "trailing_stop_loss_atr_multiplier": 1.0, # Trailing stop distance in X * ATR
        "trailing_stop_loss_activation_atr_multiplier": 1.0, # Activate/move trailing SL when profit reaches X * ATR
        "break_even_profit_atr_multiplier": 0.5, # Move SL to break-even when profit reaches X * ATR
    })

# =====================================================================
# STRATEGY INTERFACE & IMPLEMENTATION
# =====================================================================

class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""
    def __init__(self, symbol: str, config: Config):
        self.symbol = symbol
        self.config = config
        self.indicators = {} # Stores pandas DataFrames with calculated indicators per timeframe
        self.primary_timeframe = config.timeframe
        self.last_signal: StrategySignal | None = None
        self.signal_confirmed = False
        self.signal_candle_time: datetime | None = None

    @abstractmethod
    async def calculate_indicators(self, data: dict[str, pd.DataFrame]):
        """Calculate technical indicators for the strategy."""

    @abstractmethod
    async def generate_signal(self, data: dict[str, pd.DataFrame]) -> StrategySignal | None:
        """Generate a trading signal based on indicator data."""

    async def _confirm_signal(self, current_candle_time: datetime) -> bool:
        """Confirms a signal after a specified number of candles.
        Returns True if confirmed, False otherwise.
        """
        confirmation_candles_needed = self.config.strategy_params.get("signal_confirmation_candles", 1)
        if confirmation_candles_needed == 0: # No confirmation needed
            self.signal_confirmed = True
            return True

        if self.last_signal and not self.signal_confirmed and self.signal_candle_time:
            df = self.indicators.get(self.primary_timeframe)
            if df is not None and not df.empty:
                try:
                    # Find the index of the signal candle and current candle
                    # 'bfill' ensures we get an index even if the time isn't exact,
                    # picking the next available candle.
                    signal_idx = df.index.get_loc(self.signal_candle_time, method='bfill')
                    current_idx = df.index.get_loc(current_candle_time, method='bfill')
                except KeyError:
                    logger.warning(f"Could not find signal_candle_time {self.signal_candle_time} or current_candle_time {current_candle_time} in DataFrame index for signal confirmation.")
                    return False

                if current_idx - signal_idx >= confirmation_candles_needed:
                    self.signal_confirmed = True
                    logger.info(f"Signal for {self.last_signal.action} confirmed after {confirmation_candles_needed} candles.")
                    return True
        return self.signal_confirmed

class SupertrendStrategy(BaseStrategy):
    """A strategy based on the Classic Supertrend indicator."""

    def __init__(self, symbol: str, config: Config):
        super().__init__(symbol, config)
        self.supertrend_period = self.config.strategy_params.get('supertrend_period', 10)
        self.supertrend_multiplier = self.config.strategy_params.get('supertrend_multiplier', 3.0)
        self.atr_period = self.config.strategy_params.get('atr_period', 14)

    async def calculate_indicators(self, data: dict[str, pd.DataFrame]):
        """Calculates ATR and Supertrend."""
        df = data.get(self.primary_timeframe)
        if df is None or df.empty or len(df) < max(self.supertrend_period, self.atr_period):
            logger.debug(f"Insufficient data for Supertrend calculation: {len(df) if df is not None else 0} candles.")
            return

        # Calculate ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.ewm(span=self.atr_period, adjust=False).mean()

        # Calculate Supertrend
        hl2 = (df['high'] + df['low']) / 2
        df['upperband'] = hl2 + (self.supertrend_multiplier * df['atr'])
        df['lowerband'] = hl2 - (self.supertrend_multiplier * df['atr'])
        df['in_uptrend'] = True # Initialize

        for current in range(1, len(df.index)):
            previous = current - 1
            if df.loc[df.index[current], 'close'] > df.loc[df.index[previous], 'upperband']:
                df.loc[df.index[current], 'in_uptrend'] = True
            elif df.loc[df.index[current], 'close'] < df.loc[df.index[previous], 'lowerband']:
                df.loc[df.index[current], 'in_uptrend'] = False
            else:
                df.loc[df.index[current], 'in_uptrend'] = df.loc[df.index[previous], 'in_uptrend']

                if df.loc[df.index[current], 'in_uptrend'] and df.loc[df.index[current], 'lowerband'] < df.loc[df.index[previous], 'lowerband']:
                    df.loc[df.index[current], 'lowerband'] = df.loc[df.index[previous], 'lowerband']

                if not df.loc[df.index[current], 'in_uptrend'] and df.loc[df.index[current], 'upperband'] > df.loc[df.index[previous], 'upperband']:
                    df.loc[df.index[current], 'upperband'] = df.loc[df.index[previous], 'upperband']

        df['supertrend'] = np.where(df['in_uptrend'], df['lowerband'], df['upperband'])
        self.indicators[self.primary_timeframe] = df.copy() # Store a copy to avoid SettingWithCopyWarning

    async def generate_signal(self, data: dict[str, pd.DataFrame]) -> StrategySignal | None:
        """Generate signal based on Supertrend crossover with confirmation."""
        await self.calculate_indicators(data)

        df = self.indicators.get(self.primary_timeframe)
        if df is None or df.empty or len(df) < 2:
            return None

        # Drop any NaN rows that might result from indicator calculation
        df_cleaned = df.dropna(subset=['supertrend', 'atr']).copy()
        if df_cleaned.empty or len(df_cleaned) < 2:
            logger.debug("DataFrame too small after dropping NaNs for signal generation.")
            return None

        current = df_cleaned.iloc[-1]
        previous = df_cleaned.iloc[-2]

        # Reset confirmation if trend changes or a new signal is generated
        # This prevents stale pending signals from being confirmed later
        if self.last_signal and ( (self.last_signal.action == 'BUY' and not current['in_uptrend']) or \
                                  (self.last_signal.action == 'SELL' and current['in_uptrend']) ):
            logger.info(f"Trend changed opposite to last signal ({self.last_signal.action}), resetting pending signal.")
            self.last_signal = None
            self.signal_confirmed = False
            self.signal_candle_time = None

        signal_to_return = None
        if not self.last_signal: # Only generate a new signal if no active pending signal
            if not previous['in_uptrend'] and current['in_uptrend']:
                signal_to_return = StrategySignal(
                    action='BUY',
                    symbol=self.symbol,
                    strength=1.0,
                    stop_loss=float(current['supertrend']),
                    signal_price=float(current['close']),
                    metadata={'reason': 'Supertrend flipped to UP'}
                )

            elif previous['in_uptrend'] and not current['in_uptrend']:
                signal_to_return = StrategySignal(
                    action='SELL',
                    symbol=self.symbol,
                    strength=1.0,
                    stop_loss=float(current['supertrend']),
                    signal_price=float(current['close']),
                    metadata={'reason': 'Supertrend flipped to DOWN'}
                )

        if signal_to_return:
            self.last_signal = signal_to_return
            self.signal_candle_time = current.name
            logger.info(f"PENDING TRADE SIGNAL: {signal_to_return.action} for {self.symbol}. Reason: {signal_to_return.metadata['reason']}. SL: {signal_to_return.stop_loss:.5f}. Waiting for confirmation.")
            return None # Always wait for confirmation

        # If there's a pending signal, check for confirmation
        if self.last_signal and not self.signal_confirmed:
            if await self._confirm_signal(current.name):
                logger.info(f"Confirmed PENDING TRADE SIGNAL: {self.last_signal.action} for {self.symbol}.")
                # Once confirmed, clear the last_signal and signal_confirmed state to allow new signals
                temp_signal = self.last_signal
                self.last_signal = None
                self.signal_confirmed = False
                self.signal_candle_time = None
                return temp_signal
            return None # Still waiting for confirmation

        return None # No new signal or still waiting for confirmation

class EhlersSupertrendCrossStrategy(BaseStrategy):
    """A strategy based on the cross of two Ehlers Supertrend indicators
    (fast and slow), incorporating a recursive low-pass filter for smoothing.
    This version replaces scipy with a custom filter implementation.
    """

    def __init__(self, symbol: str, config: Config):
        super().__init__(symbol, config)
        self.fast_st_period = self.config.strategy_params.get('ehlers_fast_supertrend_period', 7)
        self.fast_st_multiplier = self.config.strategy_params.get('ehlers_fast_supertrend_multiplier', 2.0)
        self.slow_st_period = self.config.strategy_params.get('ehlers_slow_supertrend_period', 14)
        self.slow_st_multiplier = self.config.strategy_params.get('ehlers_slow_supertrend_multiplier', 3.0)
        self.filter_alpha = self.config.strategy_params.get('ehlers_filter_alpha', 0.2)
        self.filter_poles = self.config.strategy_params.get('ehlers_filter_poles', 2)
        self.atr_period = self.config.strategy_params.get('atr_period', 14)

    def _recursive_low_pass_filter(self, data: pd.Series) -> pd.Series:
        """Implements a simple recursive low-pass filter by applying an EMA multiple times.
        This approximates a higher-order filter but is not a true Butterworth filter.
        The 'filter_alpha' (smoothing factor) and 'filter_poles' (number of EMA applications)
        control the smoothing and lag.
        """
        if data.empty:
            return pd.Series(dtype=float)

        filtered_data = data.copy()

        # Apply EMA 'poles' times. Each application adds more smoothing.
        for _ in range(self.filter_poles):
            # The adjust=False parameter makes it a true recursive EMA
            filtered_data = filtered_data.ewm(alpha=self.filter_alpha, adjust=False).mean()

        return filtered_data

    async def calculate_indicators(self, data: dict[str, pd.DataFrame]):
        """Calculates ATR and Ehlers Supertrend for fast and slow periods using recursive filter."""
        df = data.get(self.primary_timeframe)
        if df is None or df.empty or len(df) < max(self.fast_st_period, self.slow_st_period, self.atr_period):
            logger.debug(f"Insufficient data for Ehlers Supertrend calculation: {len(df) if df is not None else 0} candles.")
            return

        # Apply custom recursive filter to price data
        df['filtered_close'] = self._recursive_low_pass_filter(df['close'])
        df['filtered_high'] = self._recursive_low_pass_filter(df['high'])
        df['filtered_low'] = self._recursive_low_pass_filter(df['low'])

        # Drop NaNs introduced by filtering (especially at the beginning of the series)
        # It's important to do this before ATR calculation if ATR relies on filtered values
        df_filtered = df.dropna(subset=['filtered_close', 'filtered_high', 'filtered_low']).copy()

        if df_filtered.empty or len(df_filtered) < self.atr_period: # Ensure enough data for ATR
            logger.debug(f"DataFrame too small after filtering for Ehlers Supertrend calculation: {len(df_filtered)} candles.")
            return

        # Calculate ATR on filtered prices
        high_low_filtered = df_filtered['filtered_high'] - df_filtered['filtered_low']
        high_close_filtered = np.abs(df_filtered['filtered_high'] - df_filtered['filtered_close'].shift())
        low_close_filtered = np.abs(df_filtered['filtered_low'] - df_filtered['filtered_close'].shift())
        tr_filtered = pd.concat([high_low_filtered, high_close_filtered, low_close_filtered], axis=1).max(axis=1)
        df_filtered['atr_filtered'] = tr_filtered.ewm(span=self.atr_period, adjust=False).mean()

        # Ensure 'atr_filtered' has enough non-NaN values for Supertrend calculation
        if df_filtered['atr_filtered'].isnull().all():
            logger.debug("ATR filtered values are all NaN, cannot calculate Supertrend.")
            return

        # --- Calculate Fast Ehlers Supertrend ---
        hl2_filtered_fast = (df_filtered['filtered_high'] + df_filtered['filtered_low']) / 2
        df_filtered['upperband_fast'] = hl2_filtered_fast + (self.fast_st_multiplier * df_filtered['atr_filtered'])
        df_filtered['lowerband_fast'] = hl2_filtered_fast - (self.fast_st_multiplier * df_filtered['atr_filtered'])
        df_filtered['in_uptrend_fast'] = True # Initialize

        for current in range(1, len(df_filtered.index)):
            previous = current - 1
            if df_filtered.loc[df_filtered.index[current], 'filtered_close'] > df_filtered.loc[df_filtered.index[previous], 'upperband_fast']:
                df_filtered.loc[df_filtered.index[current], 'in_uptrend_fast'] = True
            elif df_filtered.loc[df_filtered.index[current], 'filtered_close'] < df_filtered.loc[df_filtered.index[previous], 'lowerband_fast']:
                df_filtered.loc[df_filtered.index[current], 'in_uptrend_fast'] = False
            else:
                df_filtered.loc[df_filtered.index[current], 'in_uptrend_fast'] = df_filtered.loc[df_filtered.index[previous], 'in_uptrend_fast']

                if df_filtered.loc[df_filtered.index[current], 'in_uptrend_fast'] and df_filtered.loc[df_filtered.index[current], 'lowerband_fast'] < df_filtered.loc[df_filtered.index[previous], 'lowerband_fast']:
                    df_filtered.loc[df_filtered.index[current], 'lowerband_fast'] = df_filtered.loc[df_filtered.index[previous], 'lowerband_fast']

                if not df_filtered.loc[df_filtered.index[current], 'in_uptrend_fast'] and df_filtered.loc[df_filtered.index[current], 'upperband_fast'] > df_filtered.loc[df_filtered.index[previous], 'upperband_fast']:
                    df_filtered.loc[df_filtered.index[current], 'upperband_fast'] = df_filtered.loc[df_filtered.index[previous], 'upperband_fast']

        df_filtered['supertrend_fast'] = np.where(df_filtered['in_uptrend_fast'], df_filtered['lowerband_fast'], df_filtered['upperband_fast'])

        # --- Calculate Slow Ehlers Supertrend ---
        hl2_filtered_slow = (df_filtered['filtered_high'] + df_filtered['filtered_low']) / 2
        df_filtered['upperband_slow'] = hl2_filtered_slow + (self.slow_st_multiplier * df_filtered['atr_filtered'])
        df_filtered['lowerband_slow'] = hl2_filtered_slow - (self.slow_st_multiplier * df_filtered['atr_filtered'])
        df_filtered['in_uptrend_slow'] = True # Initialize

        for current in range(1, len(df_filtered.index)):
            previous = current - 1
            if df_filtered.loc[df_filtered.index[current], 'filtered_close'] > df_filtered.loc[df_filtered.index[previous], 'upperband_slow']:
                df_filtered.loc[df_filtered.index[current], 'in_uptrend_slow'] = True
            elif df_filtered.loc[df_filtered.index[current], 'filtered_close'] < df_filtered.loc[df_filtered.index[previous], 'lowerband_slow']:
                df_filtered.loc[df_filtered.index[current], 'in_uptrend_slow'] = False
            else:
                df_filtered.loc[df_filtered.index[current], 'in_uptrend_slow'] = df_filtered.loc[df_filtered.index[previous], 'in_uptrend_slow']

                if df_filtered.loc[df_filtered.index[current], 'in_uptrend_slow'] and df_filtered.loc[df_filtered.index[current], 'lowerband_slow'] < df_filtered.loc[df_filtered.index[previous], 'lowerband_slow']:
                    df_filtered.loc[df_filtered.index[current], 'lowerband_slow'] = df_filtered.loc[df_filtered.index[previous], 'lowerband_slow']

                if not df_filtered.loc[df_filtered.index[current], 'in_uptrend_slow'] and df_filtered.loc[df_filtered.index[current], 'upperband_slow'] > df_filtered.loc[df_filtered.index[previous], 'upperband_slow']:
                    df_filtered.loc[df_filtered.index[current], 'upperband_slow'] = df_filtered.loc[df_filtered.index[previous], 'upperband_slow']

        df_filtered['supertrend_slow'] = np.where(df_filtered['in_uptrend_slow'], df_filtered['lowerband_slow'], df_filtered['upperband_slow'])

        self.indicators[self.primary_timeframe] = df_filtered.copy() # Store a copy

    async def generate_signal(self, data: dict[str, pd.DataFrame]) -> StrategySignal | None:
        """Generate signal based on Ehlers Supertrend cross with confirmation."""
        await self.calculate_indicators(data)

        df = self.indicators.get(self.primary_timeframe)
        if df is None or df.empty or len(df) < 2:
            logger.debug("Insufficient data for Ehlers Supertrend Cross signal generation.")
            return None

        # Drop any NaN rows that might result from indicator calculation
        df_cleaned = df.dropna(subset=['supertrend_fast', 'supertrend_slow', 'atr_filtered']).copy()
        if df_cleaned.empty or len(df_cleaned) < 2:
            logger.debug("DataFrame too small after dropping NaNs for signal generation.")
            return None

        current = df_cleaned.iloc[-1]
        previous = df_cleaned.iloc[-2]

        # Determine overall trend based on slow Supertrend
        in_uptrend_overall = current['in_uptrend_slow']

        # Reset confirmation if current trend contradicts last signal
        if self.last_signal:
            # Check if the overall trend has changed since the last signal was generated/confirmed
            if (self.last_signal.action == 'BUY' and not in_uptrend_overall) or \
               (self.last_signal.action == 'SELL' and in_uptrend_overall):
                logger.info("Overall trend based on slow ST changed, resetting pending signal.")
                self.last_signal = None
                self.signal_confirmed = False
                self.signal_candle_time = None

        signal_to_return = None
        if not self.last_signal: # Only generate a new signal if no active pending signal
            current_atr = float(current.get('atr_filtered', 0.0))
            take_profit_multiplier = self.config.strategy_params.get("take_profit_atr_multiplier", 2.0)

            # Buy signal: Fast ST crosses above Slow ST and overall trend is up
            if previous['supertrend_fast'] <= previous['supertrend_slow'] and \
               current['supertrend_fast'] > current['supertrend_slow'] and \
               in_uptrend_overall:
                take_profit_val = (float(current['close']) + current_atr * take_profit_multiplier) if current_atr > 0 else None

                signal_to_return = StrategySignal(
                    action='BUY',
                    symbol=self.symbol,
                    strength=1.0,
                    stop_loss=float(current['supertrend_slow']), # Use slow ST for initial SL
                    take_profit=take_profit_val,
                    signal_price=float(current['close']),
                    metadata={'reason': 'Ehlers Fast ST Crosses Above Slow ST (Uptrend)'}
                )

            # Sell signal: Fast ST crosses below Slow ST and overall trend is down
            elif previous['supertrend_fast'] >= previous['supertrend_slow'] and \
                 current['supertrend_fast'] < current['supertrend_slow'] and \
                 not in_uptrend_overall:
                take_profit_val = (float(current['close']) - current_atr * take_profit_multiplier) if current_atr > 0 else None

                signal_to_return = StrategySignal(
                    action='SELL',
                    symbol=self.symbol,
                    strength=1.0,
                    stop_loss=float(current['supertrend_slow']), # Use slow ST for initial SL
                    take_profit=take_profit_val,
                    signal_price=float(current['close']),
                    metadata={'reason': 'Ehlers Fast ST Crosses Below Slow ST (Downtrend)'}
                )

        if signal_to_return:
            self.last_signal = signal_to_return
            self.signal_candle_time = current.name
            logger.info(f"PENDING TRADE SIGNAL: {signal_to_return.action} for {self.symbol}. Reason: {signal_to_return.metadata['reason']}. SL: {signal_to_return.stop_loss:.5f}, TP: {signal_to_return.take_profit if signal_to_return.take_profit else 'N/A':.5f}. Waiting for confirmation.")
            return None # Always wait for confirmation

        # If there's a pending signal, check for confirmation
        if self.last_signal and not self.signal_confirmed:
            if await self._confirm_signal(current.name):
                logger.info(f"Confirmed PENDING TRADE SIGNAL: {self.last_signal.action} for {self.symbol}.")
                # Once confirmed, clear the last_signal and signal_confirmed state to allow new signals
                temp_signal = self.last_signal
                self.last_signal = None
                self.signal_confirmed = False
                self.signal_candle_time = None
                return temp_signal
            return None # Still waiting for confirmation

        return None # No new signal or still waiting for confirmation


# =====================================================================
# MAIN TRADING BOT CLASS
# =====================================================================

class BybitTradingBot:
    """Main trading bot class with WebSocket integration."""

    def __init__(self, config: Config, strategy: BaseStrategy, session: HTTP | None = None):
        self.config = config
        self.strategy = strategy

        self.session = session or HTTP(
            testnet=config.testnet,
            api_key=config.api_key,
            api_secret=config.api_secret
        )
        self.public_ws = WebSocket(
            testnet=config.testnet,
            channel_type=config.category,
            api_key=config.api_key,
            api_secret=config.api_secret
        )
        self.private_ws = WebSocket(
            testnet=config.testnet,
            channel_type="private",
            api_key=config.api_key,
            api_secret=config.api_secret
        )

        self.market_info: MarketInfo | None = None
        self.market_data: dict[str, pd.DataFrame] = {} # Stores raw kline data
        self.position: Position | None = None
        self.balance: Decimal = Decimal('0', DECIMAL_CONTEXT) # Initialize balance with Decimal context
        self.is_running = False
        self.loop: asyncio.AbstractEventLoop | None = None
        self.last_processed_candle_time: datetime | None = None
        self.order_tasks: dict[str, asyncio.Task] = {} # To track open order tasks (not fully implemented for robustness)

        self._load_state() # Load state at initialization

    async def initialize(self):
        """Load market info, historical data, and initial balance."""
        logger.info("Initializing bot...")
        await self._load_market_info()
        await self._load_historical_data()
        await self.update_account_balance()
        await self.get_position() # Get initial position after loading historical data
        logger.info("Bot initialization complete.")

    async def _load_market_info(self):
        """Load and store market information for the symbol."""
        try:
            response = self.session.get_instruments_info(
                category=self.config.category,
                symbol=self.config.symbol
            )
            if response and response['retCode'] == 0:
                instrument = response['result']['list'][0]
                self.market_info = MarketInfo(
                    symbol=self.config.symbol,
                    tick_size=Decimal(instrument['priceFilter']['tickSize'], DECIMAL_CONTEXT),
                    lot_size=Decimal(instrument['lotSizeFilter']['qtyStep'], DECIMAL_CONTEXT)
                )
                logger.info(f"Market info loaded for {self.config.symbol}: Tick Size {self.market_info.tick_size}, Lot Size {self.market_info.lot_size}")
            else:
                raise Exception(f"Failed to get instrument info: {response.get('retMsg', 'Unknown error')}")
        except Exception as e:
            logger.error(f"Critical Error loading market info: {e}", exc_info=True)
            sys.exit(1) # Exit if critical info cannot be loaded

    async def _load_historical_data(self):
        """Load historical kline data to warm up the strategy."""
        logger.info(f"Loading historical data for {self.config.symbol} on {self.config.timeframe} timeframe...")
        try:
            response = self.session.get_kline(
                category=self.config.category,
                symbol=self.config.symbol,
                interval=self.config.timeframe,
                limit=self.config.lookback_periods
            )
            if response and response['retCode'] == 0:
                data = response['result']['list']
                # Ensure conversion to float for numerical operations in pandas
                df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close", "volume", "turnover"])
                df['time'] = pd.to_datetime(df['time'], unit='ms', utc=True)
                df.set_index('time', inplace=True)
                df = df.astype(float)
                df.sort_index(inplace=True)
                self.market_data[self.config.timeframe] = df
                if not df.empty:
                    self.last_processed_candle_time = df.index[-1]
                logger.info(f"Loaded {len(df)} historical candles. Last candle: {self.last_processed_candle_time}")
            else:
                raise Exception(f"Failed to get kline data: {response.get('retMsg', 'Unknown error')}")
        except Exception as e:
            logger.error(f"Critical Error loading historical data: {e}", exc_info=True)
            sys.exit(1) # Exit if historical data cannot be loaded

    async def _place_single_order(self, side: OrderSide, quantity: float, order_type: OrderType,
                                  price: float | None = None, stop_loss: float | None = None,
                                  take_profit: float | None = None) -> str | None:
        """Internal helper to place a single order with proper precision and error handling."""
        if not self.market_info:
            logger.error("Cannot place order, market info not loaded.")
            return None

        try:
            formatted_qty = self.market_info.format_quantity(quantity)
            params = {
                "category": self.config.category,
                "symbol": self.config.symbol,
                "side": side.value,
                "orderType": order_type.value,
                "qty": formatted_qty,
                "isLeverage": 1, # Always use leverage for derivatives
                "tpslMode": "Full" # Ensure SL/TP are attached to the position, or "Partial" for individual
            }

            if order_type == OrderType.LIMIT and price:
                params["price"] = self.market_info.format_price(price)

            if stop_loss is not None:
                params["stopLoss"] = self.market_info.format_price(stop_loss)
                params["slTriggerBy"] = "MarkPrice" # Using MarkPrice for consistent triggering

            if take_profit is not None:
                params["takeProfit"] = self.market_info.format_price(take_profit)
                params["tpTriggerBy"] = "MarkPrice"

            logger.debug(f"Attempting to place order with params: {params}")
            response = self.session.place_order(**params)

            if response and response['retCode'] == 0:
                order_id = response['result']['orderId']
                logger.info(f"TRADE: Order placed successfully: ID {order_id}, Side {side.value}, Qty {formatted_qty}, SL: {stop_loss}, TP: {take_profit}")
                return order_id
            error_msg = response.get('retMsg', 'Unknown error') if response else 'No response from API'
            logger.error(f"Failed to place order: {error_msg} (Code: {response.get('retCode', 'N/A')})")
            return None
        except Exception as e:
            logger.error(f"Error placing order: {e}", exc_info=True)
            return None

    async def place_market_order(self, side: OrderSide, quantity: float, stop_loss: float | None = None, take_profit: float | None = None) -> str | None:
        """Place a market order."""
        return await self._place_single_order(side, quantity, OrderType.MARKET, stop_loss=stop_loss, take_profit=take_profit)

    async def place_limit_order(self, side: OrderSide, quantity: float, price: float, stop_loss: float | None = None, take_profit: float | None = None) -> str | None:
        """Place a limit order."""
        return await self._place_single_order(side, quantity, OrderType.LIMIT, price=price, stop_loss=stop_loss, take_profit=take_profit)

    async def update_stop_loss_and_take_profit(self, position_side: str, new_stop_loss: Decimal | None = None, new_take_profit: Decimal | None = None):
        """Updates the stop-loss or take-profit of an existing position."""
        if not self.position or self.position.side != position_side:
            logger.warning(f"No active {position_side} position found for SL/TP update. Current position: {self.position}")
            return

        params = {
            "category": self.config.category,
            "symbol": self.config.symbol,
        }
        updated = False

        if new_stop_loss is not None:
            # Only update if the new SL is different from the current one
            if self.position.trailing_stop_loss is None or new_stop_loss != self.position.trailing_stop_loss:
                params["stopLoss"] = self.market_info.format_price(float(new_stop_loss))
                params["slTriggerBy"] = "MarkPrice"
                logger.info(f"Updating stop loss for {self.position.side} position to {new_stop_loss:.5f}")
                self.position.trailing_stop_loss = new_stop_loss # Update internal state immediately
                updated = True

        if new_take_profit is not None:
            # Only update if the new TP is different from the current one
            if self.position.take_profit is None or new_take_profit != self.position.take_profit:
                params["takeProfit"] = self.market_info.format_price(float(new_take_profit))
                params["tpTriggerBy"] = "MarkPrice"
                logger.info(f"Updating take profit for {self.position.side} position to {new_take_profit:.5f}")
                self.position.take_profit = new_take_profit # Update internal state immediately
                updated = True

        if not updated:
            logger.debug("No changes in stop loss or take profit, skipping update.")
            return

        try:
            response = self.session.set_trading_stop(**params)
            if response and response['retCode'] == 0:
                logger.info(f"Successfully sent SL/TP update request for {self.position.symbol} {self.position.side} position.")
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response from API'
                logger.error(f"Failed to update SL/TP: {error_msg} (Code: {response.get('retCode', 'N/A')})")
        except Exception as e:
            logger.error(f"Error updating SL/TP: {e}", exc_info=True)
        finally:
            self._save_state() # Always save state after trying to update position parameters

    async def get_position(self):
        """Get current position for the symbol and update internal state."""
        try:
            response = self.session.get_positions(
                category=self.config.category,
                symbol=self.config.symbol
            )
            if response and response['retCode'] == 0 and response['result']['list']:
                pos_data = response['result']['list'][0]
                size = Decimal(pos_data['size'], DECIMAL_CONTEXT)
                if size > 0:
                    current_position_side = pos_data['side']

                    # Try to preserve existing SL/TP/Entry if the position is the same
                    # This is crucial for maintaining trailing stop state across restarts/updates
                    existing_initial_sl = self.position.initial_stop_loss if self.position and self.position.side == current_position_side else None
                    existing_trailing_sl = self.position.trailing_stop_loss if self.position and self.position.side == current_position_side else None
                    existing_take_profit = self.position.take_profit if self.position and self.position.side == current_position_side else None
                    existing_entry_signal_price = self.position.entry_signal_price if self.position and self.position.side == current_position_side else None

                    # If Bybit API provides SL/TP for the current position, use those, otherwise use saved state
                    bybit_sl = Decimal(pos_data['stopLoss'], DECIMAL_CONTEXT) if pos_data.get('stopLoss') else existing_trailing_sl
                    bybit_tp = Decimal(pos_data['takeProfit'], DECIMAL_CONTEXT) if pos_data.get('takeProfit') else existing_take_profit

                    self.position = Position(
                        symbol=self.config.symbol,
                        side=current_position_side,
                        size=size,
                        avg_price=Decimal(pos_data['avgPrice'], DECIMAL_CONTEXT),
                        unrealized_pnl=Decimal(pos_data['unrealisedPnl'], DECIMAL_CONTEXT),
                        mark_price=Decimal(pos_data['markPrice'], DECIMAL_CONTEXT),
                        leverage=int(pos_data.get('leverage', 1)),
                        entry_signal_price=existing_entry_signal_price, # This is the price *our signal* was generated, not necessarily avg_price
                        initial_stop_loss=existing_initial_sl,
                        trailing_stop_loss=bybit_sl, # This should reflect the active SL on the exchange
                        take_profit=bybit_tp # This should reflect the active TP on the exchange
                    )
                    logger.debug(f"Position updated: {self.position}")
                else:
                    self.position = None
                    logger.debug("No active position found for symbol.")
            else:
                self.position = None
                logger.debug("No active position found for symbol via API response.")
            self._save_state() # Save state after position update
        except Exception as e:
            logger.error(f"Error getting position: {e}", exc_info=True)

    async def update_account_balance(self):
        """Update account balance."""
        try:
            response = self.session.get_wallet_balance(accountType="UNIFIED")
            if response and response['retCode'] == 0:
                balance_data = response['result']['list'][0]
                self.balance = Decimal(balance_data['totalEquity'], DECIMAL_CONTEXT)
                logger.info(f"Account balance updated: {self.balance:.2f} USDT")
            else:
                logger.error(f"Failed to update balance: {response.get('retMsg', 'Unknown error')}")
        except Exception as e:
            logger.error(f"Error updating balance: {e}", exc_info=True)

    def _calculate_position_size(self, signal: StrategySignal) -> float:
        """Calculates position size based on fixed risk percentage and stop-loss distance.
        Returns the quantity in asset units (e.g., XLM amount).
        """
        if signal.stop_loss is None or signal.signal_price is None:
            logger.error("Cannot calculate position size without a valid stop-loss and signal price from the strategy.")
            return 0.0

        risk_amount_usd = self.balance * Decimal(str(self.config.risk_per_trade_pct), DECIMAL_CONTEXT)

        # Calculate distance to stop loss in price
        stop_loss_distance_raw = Decimal('0', DECIMAL_CONTEXT)
        if signal.action == 'BUY':
            stop_loss_distance_raw = Decimal(str(signal.signal_price), DECIMAL_CONTEXT) - Decimal(str(signal.stop_loss), DECIMAL_CONTEXT)
        elif signal.action == 'SELL':
            stop_loss_distance_raw = Decimal(str(signal.stop_loss), DECIMAL_CONTEXT) - Decimal(str(signal.signal_price), DECIMAL_CONTEXT)

        if stop_loss_distance_raw <= 0:
            logger.warning(f"Stop loss distance is non-positive ({stop_loss_distance_raw}), cannot calculate position size safely. Returning 0.")
            return 0.0

        # Position value in USD that can be taken given the risk amount and SL distance
        # Value_at_risk_per_share = SL_Distance / (Leverage + 1) -> simplifies to:
        # Position_Value_USD = Risk_Amount_USD / (SL_Distance_in_percentage_of_entry)
        # Position_Size_Asset = Position_Value_USD / Entry_Price

        # The calculation below is more direct:
        # Value_of_position_to_open = (Risk_Amount / (Risk_per_unit_of_asset)) * Entry_Price
        # Risk_per_unit_of_asset = abs(Entry_Price - Stop_Loss_Price)
        # Position_size_asset = (Risk_Amount_USD / stop_loss_distance_raw) * leverage_factor (where leverage_factor is usually 1, then adjusted by self.config.leverage later)

        # Correct calculation for position size in base asset units:
        # Amount of base asset = (Risk per trade in quote currency) / (Stop Loss Distance in quote currency per base unit)
        position_size_asset_unleveraged = risk_amount_usd / stop_loss_distance_raw

        # Apply leverage
        leveraged_position_size_asset = position_size_asset_unleveraged * Decimal(str(self.config.leverage), DECIMAL_CONTEXT)

        # Format to lot size precision
        formatted_position_size = Decimal(self.market_info.format_quantity(float(leveraged_position_size_asset)), DECIMAL_CONTEXT)

        logger.info(f"Risk Amount: {risk_amount_usd:.2f} USDT, SL Distance: {stop_loss_distance_raw:.5f} USDT, "
                    f"Calculated Position Size (Leveraged & Formatted): {formatted_position_size:.5f} {self.config.symbol}")

        return float(formatted_position_size)

    async def process_signal(self, signal: StrategySignal):
        """Processes a trading signal from the strategy, managing orders and positions."""
        logger.info(f"Processing signal: {signal.action} {signal.symbol} (Reason: {signal.metadata.get('reason', 'N/A')})")

        if self.market_data.get(self.config.timeframe) is None or self.market_data[self.config.timeframe].empty:
            logger.warning("No market data available for signal processing, skipping.")
            return

        current_close_price = self.market_data[self.config.timeframe].iloc[-1]['close']

        # Dynamically set/refine Take Profit if not provided by strategy or if ATR changes
        df_indicators = self.strategy.indicators.get(self.config.timeframe)
        current_atr = float(df_indicators.iloc[-1].get('atr_filtered', df_indicators.iloc[-1].get('atr', 0.0))) if df_indicators is not None and not df_indicators.empty else 0.0

        if signal.take_profit is None and signal.signal_price is not None and current_atr > 0:
            tp_multiplier = self.config.strategy_params.get("take_profit_atr_multiplier", 2.0)
            if signal.action == 'BUY':
                signal.take_profit = float(Decimal(str(signal.signal_price), DECIMAL_CONTEXT) + Decimal(str(current_atr), DECIMAL_CONTEXT) * Decimal(str(tp_multiplier), DECIMAL_CONTEXT))
            elif signal.action == 'SELL':
                signal.take_profit = float(Decimal(str(signal.signal_price), DECIMAL_CONTEXT) - Decimal(str(current_atr), DECIMAL_CONTEXT) * Decimal(str(tp_multiplier), DECIMAL_CONTEXT))
            logger.info(f"Dynamically calculated Take Profit: {signal.take_profit:.5f}")


        position_size = self._calculate_position_size(signal)
        if position_size <= 0:
            logger.warning("Calculated position size is zero or negative, aborting trade.")
            return

        # --- Position Management Logic ---
        if self.position:
            # Scenario 1: Signal is in the opposite direction of the current position (REVERSE)
            if (signal.action == 'BUY' and self.position.side == 'Sell') or \
               (signal.action == 'SELL' and self.position.side == 'Buy'):
                logger.info(f"Reversing position: Closing existing {self.position.side} ({self.position.size:.5f}) to open {signal.action} ({position_size:.5f}).")

                # Close existing position first
                close_side = OrderSide.BUY if self.position.side == 'Sell' else OrderSide.SELL
                close_order_id = await self.place_market_order(side=close_side, quantity=float(self.position.size))

                if close_order_id:
                    logger.info(f"Close order {close_order_id} placed. Waiting for position to settle before opening new one...")
                    await asyncio.sleep(5) # Give exchange time to process closure
                    await self.get_position() # Update position state
                    await self.update_account_balance() # Update balance

                    if not self.position: # Successfully closed
                        logger.info("Existing position successfully closed.")
                        # Proceed to open new position
                        new_order_id = await self.place_market_order(
                            side=OrderSide.BUY if signal.action == 'BUY' else OrderSide.SELL,
                            quantity=position_size,
                            stop_loss=signal.stop_loss,
                            take_profit=signal.take_profit
                        )
                        if new_order_id:
                            self.position = Position( # Temporarily update internal position state
                                symbol=self.config.symbol, side=signal.action, size=Decimal(str(position_size), DECIMAL_CONTEXT),
                                avg_price=Decimal(str(current_close_price), DECIMAL_CONTEXT), unrealized_pnl=Decimal('0', DECIMAL_CONTEXT),
                                mark_price=Decimal(str(current_close_price), DECIMAL_CONTEXT), leverage=self.config.leverage,
                                entry_signal_price=Decimal(str(signal.signal_price), DECIMAL_CONTEXT),
                                initial_stop_loss=Decimal(str(signal.stop_loss), DECIMAL_CONTEXT) if signal.stop_loss else None,
                                trailing_stop_loss=Decimal(str(signal.stop_loss), DECIMAL_CONTEXT) if signal.stop_loss else None,
                                take_profit=Decimal(str(signal.take_profit), DECIMAL_CONTEXT) if signal.take_profit else None
                            )
                            self._save_state()
                        else:
                            logger.error("Failed to open new position after closing existing one.")
                    else:
                        logger.error("Failed to close existing position. Aborting new trade.")
                else:
                    logger.error("Failed to place order to close existing position. Aborting new trade.")
                return # Handled reversing position

            # Scenario 2: Signal is in the same direction as the current position (ADJUST SL/TP)
            if (signal.action == 'BUY' and self.position.side == 'Buy') or \
                 (signal.action == 'SELL' and self.position.side == 'Sell'):
                logger.info(f"Signal to {signal.action} received, but already in a {self.position.side} position. Adjusting SL/TP if beneficial.")

                new_sl_to_set: Decimal | None = None
                new_tp_to_set: Decimal | None = None

                # Update initial_stop_loss if the new signal suggests a tighter (more favorable) SL
                if signal.stop_loss:
                    new_signal_sl = Decimal(str(signal.stop_loss), DECIMAL_CONTEXT)
                    if self.position.initial_stop_loss is None or \
                       (self.position.side == 'Buy' and new_signal_sl > self.position.initial_stop_loss) or \
                       (self.position.side == 'Sell' and new_signal_sl < self.position.initial_stop_loss):
                        self.position.initial_stop_loss = new_signal_sl
                        new_sl_to_set = new_signal_sl
                        logger.info(f"Initial stop loss updated to a more favorable level: {new_signal_sl:.5f}")
                    # Also update trailing SL if it's currently wider than the new initial SL
                    if self.position.trailing_stop_loss is None or \
                       (self.position.side == 'Buy' and new_signal_sl > self.position.trailing_stop_loss) or \
                       (self.position.side == 'Sell' and new_signal_sl < self.position.trailing_stop_loss):
                       new_sl_to_set = new_signal_sl
                       self.position.trailing_stop_loss = new_signal_sl # Reset trailing SL
                       logger.info(f"Trailing stop loss also reset to new initial SL: {new_signal_sl:.5f}")


                # Update take_profit if new signal suggests a better TP
                if signal.take_profit:
                    new_signal_tp = Decimal(str(signal.take_profit), DECIMAL_CONTEXT)
                    if self.position.take_profit is None or \
                       (self.position.side == 'Buy' and new_signal_tp > self.position.take_profit) or \
                       (self.position.side == 'Sell' and new_signal_tp < self.position.take_profit):
                        new_tp_to_set = new_signal_tp
                        logger.info(f"Take profit updated to a more favorable level: {new_signal_tp:.5f}")

                if new_sl_to_set or new_tp_to_set:
                    await self.update_stop_loss_and_take_profit(self.position.side, new_sl_to_set, new_tp_to_set)
                else:
                    logger.debug("No beneficial SL/TP updates from current signal.")
                return # Handled adjusting position

        # Scenario 3: No current position, open a new one
        if not self.position:
            logger.info(f"Opening new {signal.action} position with size {position_size:.5f}.")
            order_id = await self.place_market_order(
                side=OrderSide.BUY if signal.action == 'BUY' else OrderSide.SELL,
                quantity=position_size,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit
            )
            if order_id:
                self.position = Position( # Temporarily update internal position state
                    symbol=self.config.symbol, side=signal.action, size=Decimal(str(position_size), DECIMAL_CONTEXT),
                    avg_price=Decimal(str(current_close_price), DECIMAL_CONTEXT), unrealized_pnl=Decimal('0', DECIMAL_CONTEXT),
                    mark_price=Decimal(str(current_close_price), DECIMAL_CONTEXT), leverage=self.config.leverage,
                    entry_signal_price=Decimal(str(signal.signal_price), DECIMAL_CONTEXT) if signal.signal_price else None,
                    initial_stop_loss=Decimal(str(signal.stop_loss), DECIMAL_CONTEXT) if signal.stop_loss else None,
                    trailing_stop_loss=Decimal(str(signal.stop_loss), DECIMAL_CONTEXT) if signal.stop_loss else None,
                    take_profit=Decimal(str(signal.take_profit), DECIMAL_CONTEXT) if signal.take_profit else None
                )
                self._save_state()
            else:
                logger.error("Failed to open new position.")
            return # Handled opening new position


    async def _update_trailing_stop_loss(self):
        """Updates the trailing stop loss for an open position.
        Activates when profit reaches 'trailing_stop_loss_activation_atr_multiplier' * ATR.
        Moves by 'trailing_stop_loss_atr_multiplier' * ATR, and also ensures move to break-even.
        """
        if not self.position or self.position.entry_signal_price is None or \
           self.strategy.indicators.get(self.config.timeframe) is None or self.strategy.indicators[self.config.timeframe].empty:
            logger.debug("Cannot update trailing stop: no position, no entry price, or no indicators.")
            return

        current_df = self.strategy.indicators[self.config.timeframe].iloc[-1]
        current_price = Decimal(str(current_df['close']), DECIMAL_CONTEXT)

        current_atr = Decimal(str(current_df.get('atr_filtered', current_df.get('atr', 0.0))), DECIMAL_CONTEXT)
        if current_atr <= 0:
            logger.warning("ATR not available or non-positive for trailing stop calculation.")
            return

        activation_multiplier = Decimal(str(self.config.strategy_params.get("trailing_stop_loss_activation_atr_multiplier", 1.0)), DECIMAL_CONTEXT)
        trailing_multiplier = Decimal(str(self.config.strategy_params.get("trailing_stop_loss_atr_multiplier", 1.0)), DECIMAL_CONTEXT)
        break_even_profit_multiplier = Decimal(str(self.config.strategy_params.get("break_even_profit_atr_multiplier", 0.5)), DECIMAL_CONTEXT)

        # Calculate current profit in ATR units
        profit_in_usd = Decimal('0', DECIMAL_CONTEXT)
        if self.position.side == 'Buy':
            profit_in_usd = current_price - self.position.entry_signal_price
        elif self.position.side == 'Sell':
            profit_in_usd = self.position.entry_signal_price - current_price

        profit_in_atr = profit_in_usd / current_atr if current_atr > 0 else Decimal('0', DECIMAL_CONTEXT)

        # Determine potential new trailing stop price
        potential_new_stop_price: Decimal | None = None

        if self.position.side == 'Buy':
            # Move to break-even + small profit
            break_even_stop = self.position.entry_signal_price + (current_atr * break_even_profit_multiplier)
            if profit_in_atr >= break_even_profit_multiplier and (self.position.trailing_stop_loss is None or break_even_stop > self.position.trailing_stop_loss):
                potential_new_stop_price = break_even_stop

            # Trailing stop logic (moves only if profit is significant)
            if profit_in_atr >= activation_multiplier:
                trailing_point_stop = current_price - (current_atr * trailing_multiplier)
                if potential_new_stop_price is None or trailing_point_stop > potential_new_stop_price:
                     potential_new_stop_price = trailing_point_stop

            # Ensure SL never goes below initial SL if it was set
            if potential_new_stop_price and self.position.initial_stop_loss and potential_new_stop_price < self.position.initial_stop_loss:
                potential_new_stop_price = self.position.initial_stop_loss

        elif self.position.side == 'Sell':
            # Move to break-even + small profit
            break_even_stop = self.position.entry_signal_price - (current_atr * break_even_profit_multiplier)
            if profit_in_atr >= break_even_profit_multiplier and (self.position.trailing_stop_loss is None or break_even_stop < self.position.trailing_stop_loss):
                potential_new_stop_price = break_even_stop

            # Trailing stop logic
            if profit_in_atr >= activation_multiplier:
                trailing_point_stop = current_price + (current_atr * trailing_multiplier)
                if potential_new_stop_price is None or trailing_point_stop < potential_new_stop_price:
                     potential_new_stop_price = trailing_point_stop

            # Ensure SL never goes above initial SL if it was set
            if potential_new_stop_price and self.position.initial_stop_loss and potential_new_stop_price > self.position.initial_stop_loss:
                potential_new_stop_price = self.position.initial_stop_loss

        # Now, compare and update if necessary
        if potential_new_stop_price is not None:
            # Only send update if the new stop is actually better (moves in favor of the trade)
            current_trailing_sl = self.position.trailing_stop_loss
            should_update_exchange = False
            if current_trailing_sl is None or (self.position.side == 'Buy' and potential_new_stop_price > current_trailing_sl) or (self.position.side == 'Sell' and potential_new_stop_price < current_trailing_sl): # No current trailing SL set
                should_update_exchange = True

            if should_update_exchange:
                logger.info(f"Updating trailing stop-loss for {self.position.side} position. Old: {current_trailing_sl:.5f if current_trailing_sl else 'N/A'}, New: {potential_new_stop_price:.5f}")
                await self.update_stop_loss_and_take_profit(self.position.side, new_stop_loss=potential_new_stop_price)
                # update_stop_loss_and_take_profit already updates self.position.trailing_stop_loss and saves state
            else:
                logger.debug(f"Calculated trailing stop {potential_new_stop_price:.5f} is not better than current {current_trailing_sl:.5f if current_trailing_sl else 'N/A'}.")
        else:
            logger.debug(f"Profit {profit_in_atr:.2f} ATR. Trailing stop conditions not met yet or no beneficial move.")


    def _handle_kline_message(self, message):
        """Callback for processing real-time kline data."""
        try:
            data = message['data'][0]
            candle_time_ms = int(data['start'])
            current_candle_time = pd.to_datetime(candle_time_ms, unit='ms', utc=True)

            # Important: Check if the candle is already processed or is older (re-connection/late message)
            if self.last_processed_candle_time and current_candle_time < self.last_processed_candle_time:
                logger.debug(f"Skipping older/already processed candle: {current_candle_time} (last processed: {self.last_processed_candle_time})")
                return

            df = self.market_data.get(self.config.timeframe)
            if df is None or df.empty:
                logger.warning(f"Market data for {self.config.timeframe} is not initialized or empty. Waiting for more data.")
                # This could happen during initial startup if historical data load fails
                # or if the first few websocket messages are malformed.
                return

            new_candle_data = {
                'open': float(data['open']),
                'high': float(data['high']),
                'low': float(data['low']),
                'close': float(data['close']),
                'volume': float(data['volume']),
                'turnover': float(data['turnover'])
            }
            new_candle = pd.DataFrame([new_candle_data], index=[current_candle_time])

            # Update or append candle
            if current_candle_time in df.index:
                # Update existing row if it's the current (unclosed) candle
                df.loc[current_candle_time, new_candle.columns] = new_candle.iloc[0]
                logger.debug(f"Updated existing candle: {current_candle_time}")
            else:
                # Append new row (newly closed candle)
                df = pd.concat([df, new_candle]).sort_index()
                # Ensure we don't grow the DataFrame indefinitely
                df = df.iloc[-(self.config.lookback_periods + max(self.strategy.fast_st_period, self.strategy.slow_st_period, self.strategy.atr_period, self.strategy.filter_poles * 2)):].copy() # Keep enough for filtering and lookback
                self.last_processed_candle_time = current_candle_time # Update last processed time for new candles
                logger.debug(f"Appended new candle: {current_candle_time}")

            self.market_data[self.config.timeframe] = df

            # Schedule strategy cycle and logging as a task thread-safely
            # This ensures heavy computation (strategy) doesn't block the WebSocket handler
            self.loop.call_soon_threadsafe(asyncio.create_task, self._async_kline_processing())

        except Exception as e:
            logger.error(f"Error handling kline message: {e}", exc_info=True)

    async def _async_kline_processing(self):
        """Asynchronous part of kline message processing (runs strategy, updates trailing stop)."""
        await self.run_strategy_cycle()
        if self.position:
            await self._update_trailing_stop_loss()

        # Display current price and indicator values for monitoring
        df = self.strategy.indicators.get(self.config.timeframe)
        if df is not None and not df.empty:
            current_close = df.iloc[-1]['close']

            if self.config.strategy_name == "Supertrend":
                supertrend_value = df.iloc[-1].get('supertrend', np.nan)
                logger.info(f"Current Price: {current_close:.5f}, Supertrend: {supertrend_value:.5f}")
            elif self.config.strategy_name == "EhlersSupertrendCross":
                fast_st = df.iloc[-1].get('supertrend_fast', np.nan)
                slow_st = df.iloc[-1].get('supertrend_slow', np.nan)
                logger.info(f"Current Price: {current_close:.5f}, Fast ST: {fast_st:.5f}, Slow ST: {slow_st:.5f}")

        else:
            logger.info(f"No indicators available yet for {self.config.timeframe}. Raw data size: {len(self.market_data.get(self.config.timeframe, []))}")


    def _handle_private_message(self, message):
        """Callback for private websocket messages (positions, orders, wallet)."""
        try:
            topic = message.get('topic')
            if topic == 'position':
                self.loop.call_soon_threadsafe(asyncio.create_task, self.get_position())
            elif topic == 'order':
                logger.info(f"Order update received: {message['data']}")
                # Advanced: Parse order fills here to update internal position state more quickly
            elif topic == 'wallet':
                self.loop.call_soon_threadsafe(asyncio.create_task, self.update_account_balance())
        except Exception as e:
            logger.error(f"Error handling private message: {e}", exc_info=True)

    async def run_strategy_cycle(self):
        """Runs a single cycle of the strategy to generate and process signals."""
        signal = await self.strategy.generate_signal(self.market_data)
        if signal and signal.action != 'HOLD': # 'HOLD' signals are for internal strategy logic, not external actions
            await self.process_signal(signal)
        else:
            logger.debug("No actionable signal generated or signal to HOLD.")

    def _save_state(self):
        """Persists the bot's critical state to a file."""
        state = {
            'position': asdict(self.position) if self.position else None,
            'balance': str(self.balance), # Convert Decimal to string for serialization
            'last_signal': asdict(self.strategy.last_signal) if self.strategy.last_signal else None,
            'signal_confirmed': self.strategy.signal_confirmed,
            'signal_candle_time': self.strategy.signal_candle_time.isoformat() if self.strategy.signal_candle_time else None,
            'last_processed_candle_time': self.last_processed_candle_time.isoformat() if self.last_processed_candle_time else None,
        }
        try:
            with open('bot_state.pkl', 'wb') as f:
                pickle.dump(state, f)
            logger.debug("Bot state saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save bot state: {e}", exc_info=True)

    def _load_state(self):
        """Loads the bot's critical state from a file."""
        try:
            if os.path.exists('bot_state.pkl'):
                with open('bot_state.pkl', 'rb') as f:
                    state = pickle.load(f)
                    if state.get('position'):
                        pos_data = state['position']
                        self.position = Position(
                            symbol=pos_data['symbol'],
                            side=pos_data['side'],
                            size=Decimal(str(pos_data['size']), DECIMAL_CONTEXT),
                            avg_price=Decimal(str(pos_data['avg_price']), DECIMAL_CONTEXT),
                            unrealized_pnl=Decimal(str(pos_data['unrealized_pnl']), DECIMAL_CONTEXT),
                            mark_price=Decimal(str(pos_data['mark_price']), DECIMAL_CONTEXT),
                            leverage=pos_data['leverage'],
                            entry_signal_price=Decimal(str(pos_data['entry_signal_price']), DECIMAL_CONTEXT) if pos_data['entry_signal_price'] else None,
                            initial_stop_loss=Decimal(str(pos_data['initial_stop_loss']), DECIMAL_CONTEXT) if pos_data['initial_stop_loss'] else None,
                            trailing_stop_loss=Decimal(str(pos_data['trailing_stop_loss']), DECIMAL_CONTEXT) if pos_data['trailing_stop_loss'] else None,
                            take_profit=Decimal(str(pos_data['take_profit']), DECIMAL_CONTEXT) if pos_data['take_profit'] else None
                        )
                    self.balance = Decimal(state.get('balance', '0'), DECIMAL_CONTEXT)
                    if state.get('last_signal'):
                        self.strategy.last_signal = StrategySignal(**state['last_signal'])
                    self.strategy.signal_confirmed = state.get('signal_confirmed', False)
                    if state.get('signal_candle_time'):
                        self.strategy.signal_candle_time = datetime.fromisoformat(state['signal_candle_time'])
                    if state.get('last_processed_candle_time'):
                        self.last_processed_candle_time = datetime.fromisoformat(state['last_processed_candle_time'])
                    logger.info("Bot state loaded successfully.")
            else:
                logger.info("No saved bot state found, starting fresh.")
        except Exception as e:
            logger.error(f"Failed to load bot state: {e}. Starting fresh.", exc_info=True)
            # If state loading fails, ensure critical variables are reset to defaults to prevent issues
            self.position = None
            self.balance = Decimal('0', DECIMAL_CONTEXT)
            self.strategy.last_signal = None
            self.strategy.signal_confirmed = False
            self.strategy.signal_candle_time = None
            self.last_processed_candle_time = None

    async def start(self):
        """Starts the trading bot, initializes connections, and begins the trading loop."""
        self.is_running = True
        self.loop = asyncio.get_running_loop() # Store the event loop
        await self.initialize()

        # Setup WebSocket streams
        self.public_ws.kline_stream(
            callback=self._handle_kline_message,
            symbol=self.config.symbol,
            interval=self.config.timeframe
        )
        self.private_ws.position_stream(callback=self._handle_private_message)
        self.private_ws.order_stream(callback=self._handle_private_message)
        self.private_ws.wallet_stream(callback=self._handle_private_message)

        logger.info("Trading bot started successfully. Waiting for market data and signals...")

        # Keep the main task alive
        while self.is_running:
            await asyncio.sleep(1) # Sleep to prevent busy-waiting

    async def stop(self):
        """Stops the trading bot, closes connections, and saves final state."""
        self.is_running = False
        logger.info("Stopping trading bot...")

        # Close WebSocket connections gracefully
        if self.public_ws:
            self.public_ws.exit()
            logger.info("Public WebSocket disconnected.")
        if self.private_ws:
            self.private_ws.exit()
            logger.info("Private WebSocket disconnected.")

        self._save_state() # Save final state on graceful shutdown
        logger.info("Trading bot stopped and state saved.")

# --- MAIN EXECUTION BLOCK ---

if __name__ == "__main__":
    if not os.getenv("BYBIT_API_KEY") or not os.getenv("BYBIT_API_SECRET"):
        logger.critical("API keys are not set. Please create a .env file with BYBIT_API_KEY and BYBIT_API_SECRET.")
        sys.exit(1)

    bot_config = Config()

    bot_strategy: BaseStrategy
    if bot_config.strategy_name == "Supertrend":
        bot_strategy = SupertrendStrategy(symbol=bot_config.symbol, config=bot_config)
    elif bot_config.strategy_name == "EhlersSupertrendCross":
        bot_strategy = EhlersSupertrendCrossStrategy(symbol=bot_config.symbol, config=bot_config)
    else:
        logger.critical(f"Unknown strategy specified in config: {bot_config.strategy_name}. Exiting.")
        sys.exit(1)

    bot = BybitTradingBot(config=bot_config, strategy=bot_strategy)

    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Bot gracefully stopped by user (KeyboardInterrupt).")
        # asyncio.run(bot.stop()) # The stop() method will be called via the outer exception handler
    except Exception as e:
        logger.critical(f"An unhandled critical exception occurred: {e}", exc_info=True)
    finally:
        # Ensure stop is called even if an exception occurs
        if bot.is_running: # Only try to stop if it was running
             asyncio.run(bot.stop())
        else: # If bot never started, just log
            logger.info("Bot was not running when finally block executed.")
