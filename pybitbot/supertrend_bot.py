#!/usr/bin/env python3
"""
Bybit Supertrend Trading Bot Framework v1.0

This script is a professional-grade, fully asynchronous trading bot for Bybit,
specifically implementing a Supertrend strategy. It is built upon a robust
framework that includes:

Key Features:
1.  **Fully Asynchronous:** Built entirely on asyncio for high performance.
2.  **Modular Architecture:** Cleanly separated components for risk management,
    order execution, state persistence, and strategy.
3.  **State Persistence & Recovery:** Saves critical state, allowing the bot
    to be restarted without losing context.
4.  **Supertrend Strategy:** Implements a classic Supertrend strategy to
    identify trend direction and generate trading signals.
5.  **Advanced Risk Management:** Features fixed-risk position sizing and
    persistent tracking of drawdown and daily loss limits.
6.  **Advanced Order Management:** Supports market/limit orders and allows for
    strategy-defined stop-loss and take-profit levels.
7.  **Robust WebSocket Handling:** A dedicated manager for WebSocket connections with
    automatic reconnection and exponential backoff.
8.  **Dynamic Precision Handling:** Fetches and uses market-specific precision for
    price and quantity to prevent exchange rejections.

Instructions for Use:
1.  Install dependencies:
    `pip install pybit pandas numpy python-dotenv pytz aiosqlite aiofiles`
2.  Create a `.env` file in the same directory with your credentials:
    BYBIT_API_KEY="YOUR_API_KEY"
    BYBIT_API_SECRET="YOUR_API_SECRET"
3.  Configure the `Config` class below with your desired settings.
4.  Run the bot:
    `python3 supertrend_bot.py`
"""

import asyncio
import json
import logging
import sys
import os
import time
import pickle
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, getcontext
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Tuple
from logging.handlers import RotatingFileHandler

import aiofiles
import numpy as np
import pandas as pd
import pytz
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

# ANSI color codes for NEW "neon" style logging
class NeonColors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    # Bright/Intense colors for a more "neon" feel
    BRIGHT_GREEN = "\033[92m"    # INFO
    BRIGHT_YELLOW = "\033[93m"   # WARNING
    BRIGHT_RED = "\033[91m"      # ERROR
    BRIGHT_MAGENTA = "\033[95m"  # CRITICAL (vibrant pink/purple)
    BRIGHT_CYAN = "\033[96m"     # DEBUG
    BRIGHT_BLUE = "\033[94m"     # General/Other
    BRIGHT_WHITE = "\033[97m"    # Default/Subtle

class NeonFormatter(logging.Formatter):
    """A custom formatter for neon-style colored console output with new scheme."""

    FORMATS = {
        logging.DEBUG: NeonColors.BRIGHT_CYAN + '%(asctime)s - ' + NeonColors.BOLD + '%(levelname)s' + NeonColors.RESET + NeonColors.BRIGHT_CYAN + ' - %(name)s - %(funcName)s:%(lineno)d - %(message)s' + NeonColors.RESET,
        logging.INFO: NeonColors.BRIGHT_GREEN + '%(asctime)s - ' + NeonColors.BOLD + '%(levelname)s' + NeonColors.RESET + NeonColors.BRIGHT_GREEN + ' - %(message)s' + NeonColors.RESET,
        logging.WARNING: NeonColors.BRIGHT_YELLOW + '%(asctime)s - ' + NeonColors.BOLD + '%(levelname)s' + NeonColors.RESET + NeonColors.BRIGHT_YELLOW + ' - %(message)s' + NeonColors.RESET,
        logging.ERROR: NeonColors.BRIGHT_RED + '%(asctime)s - ' + NeonColors.BOLD + '%(levelname)s' + NeonColors.RESET + NeonColors.BRIGHT_RED + ' - %(funcName)s:%(lineno)d - %(message)s' + NeonColors.RESET,
        logging.CRITICAL: NeonColors.BOLD + NeonColors.BRIGHT_MAGENTA + '%(asctime)s - ' + NeonColors.BOLD + '%(levelname)s' + NeonColors.RESET + NeonColors.BRIGHT_MAGENTA + ' - %(funcName)s:%(lineno)d - %(message)s' + NeonColors.RESET
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        # We need to re-create the formatter each time because the format string changes based on level
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

def setup_logging():
    """Setup comprehensive logging configuration with neon console output."""
    log = logging.getLogger()
    log.setLevel(logging.INFO) # Default level, can be overridden per handler
    
    # Formatters
    detailed_formatter = logging.Formatter( # For file logs (no colors)
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    neon_formatter = NeonFormatter() # For console logs (with colors)
    
    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(neon_formatter) # Use neon formatter for console
    
    # File Handler (for all logs, no colors)
    file_handler = RotatingFileHandler('supertrend_bot.log', maxBytes=10*1024*1024, backupCount=5)
    file_handler.setLevel(logging.DEBUG) # Log all levels to file
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
        return str(Decimal(str(price)).quantize(self.tick_size, rounding=ROUND_DOWN))

    def format_quantity(self, quantity: float) -> str:
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
    entry_signal_price: Optional[Decimal] = None # Price at which strategy generated the signal to enter
    initial_stop_loss: Optional[Decimal] = None # Original strategy SL for risk calculation
    trailing_stop_loss: Optional[Decimal] = None # Current active trailing stop loss on exchange
    take_profit: Optional[Decimal] = None # Current active take profit on exchange

@dataclass
class StrategySignal:
    """Standardized object for strategy signals."""
    action: str  # 'BUY', 'SELL', 'CLOSE', 'HOLD'
    symbol: str
    strength: float = 1.0
    stop_loss: Optional[float] = None # Suggested initial stop loss price
    take_profit: Optional[float] = None # Suggested initial take profit price
    signal_price: Optional[float] = None # Price at which the signal was generated (current close)
    metadata: Dict = field(default_factory=dict)

@dataclass
class Config:
    """Trading bot configuration."""
    api_key: str = field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    testnet: bool = False
    
    # Trading Parameters
    symbol: str = "XLMUSDT"
    category: str = "linear" # "linear" for USDT Perpetuals, "inverse" for Inverse Perpetuals, etc.
    min_order_value_usdt: float = 5.0 # Minimum order value in USDT for Bybit
    
    # Risk Management (Tuned for Scalping)
    risk_per_trade_pct: float = 0.005  # 0.5% of equity risked per trade (smaller for scalping)
    leverage: int = 20 # Higher leverage for scalping to magnify small moves
    
    # WebSocket settings
    reconnect_attempts: int = 5
    
    # Strategy Parameters (Tuned for Scalping)
    strategy_name: str = "EhlersSupertrendCross" 
    timeframe: str = "3"  # Shorter timeframe for scalping (e.g., "1", "3", "5")
    lookback_periods: int = 200  # Reduced lookback to minimize data processing per candle
    
    # Common Strategy Params
    strategy_params: Dict[str, Any] = field(default_factory=lambda: {
        # Classic Supertrend Specific Params (if used)
        "supertrend_period": 7, # Shorter period
        "supertrend_multiplier": 2.5, # Tighter multiplier
        "atr_period": 10, # Shorter ATR period

        # Ehlers Supertrend Specific Params (Scalping Tuned)
        "ehlers_fast_supertrend_period": 5, # Very fast
        "ehlers_fast_supertrend_multiplier": 1.5, # Very tight
        "ehlers_slow_supertrend_period": 10, # Still relatively fast
        "ehlers_slow_supertrend_multiplier": 2.5, # Tighter
        "ehlers_filter_alpha": 0.35, # Increased alpha for less smoothing / more responsiveness
        "ehlers_filter_poles": 1,   # Reduced poles for less lag (more EMA-like)
        
        # Advanced Entry/Exit & Risk Management (Scalping Tuned)
        "signal_confirmation_candles": 0, # Immediate entry for scalping (0 for no confirmation)
        "take_profit_atr_multiplier": 1.0, # Smaller TP targets
        "trailing_stop_loss_atr_multiplier": 0.75, # Tighter trailing stops
        "trailing_stop_loss_activation_atr_multiplier": 0.5, # Activate trailing SL very quickly
        "break_even_profit_atr_multiplier": 0.2, # Move to break-even almost immediately (within this ATR range)
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
        self.last_signal: Optional[StrategySignal] = None
        self.signal_confirmed = False
        self.signal_candle_time: Optional[datetime] = None

        # Determine strategy-specific ATR period for consistent access
        self.atr_period = self.config.strategy_params.get('atr_period', 14)

    @abstractmethod
    async def calculate_indicators(self, data: Dict[str, pd.DataFrame]):
        """Calculate technical indicators for the strategy."""
        pass

    @abstractmethod
    async def generate_signal(self, data: Dict[str, pd.DataFrame]) -> Optional[StrategySignal]:
        """Generate a trading signal based on indicator data."""
        pass

    async def _confirm_signal(self, current_candle_time: datetime) -> bool:
        """
        Confirms a signal after a specified number of candles.
        Returns True if confirmed, False otherwise.
        """
        confirmation_candles_needed = self.config.strategy_params.get("signal_confirmation_candles", 1)
        if confirmation_candles_needed == 0: # No confirmation needed, immediate action
            self.signal_confirmed = True
            return True

        if self.last_signal and not self.signal_confirmed and self.signal_candle_time:
            df = self.indicators.get(self.primary_timeframe)
            if df is None or df.empty or self.signal_candle_time not in df.index:
                logger.debug(f"DataFrame for {self.primary_timeframe} is empty or signal_candle_time {self.signal_candle_time} not in index for confirmation.")
                return False

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
        return False # Still waiting for confirmation or conditions not met

class SupertrendStrategy(BaseStrategy):
    """A strategy based on the Classic Supertrend indicator."""

    def __init__(self, symbol: str, config: Config):
        super().__init__(symbol, config)
        self.supertrend_period = self.config.strategy_params.get('supertrend_period', 10)
        self.supertrend_multiplier = self.config.strategy_params.get('supertrend_multiplier', 3.0)
        # atr_period is inherited from BaseStrategy

    async def calculate_indicators(self, data: Dict[str, pd.DataFrame]):
        """Calculates ATR and Supertrend."""
        df = data.get(self.primary_timeframe)
        min_data_needed = max(self.supertrend_period, self.atr_period)
        if df is None or df.empty or len(df) < min_data_needed:
            logger.debug(f"Insufficient data for Supertrend calculation ({len(df) if df is not None else 0} < {min_data_needed} candles).")
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

    async def generate_signal(self, data: Dict[str, pd.DataFrame]) -> Optional[StrategySignal]:
        """Generate signal based on Supertrend crossover with confirmation."""
        await self.calculate_indicators(data)
        
        df = self.indicators.get(self.primary_timeframe)
        if df is None or df.empty or len(df) < 2:
            return None

        # Drop any NaN rows that might result from indicator calculation to get clean data for signal
        df_cleaned = df.dropna(subset=['supertrend', 'atr']).copy()
        if df_cleaned.empty or len(df_cleaned) < 2:
            logger.debug("DataFrame too small after dropping NaNs for signal generation.")
            return None

        current = df_cleaned.iloc[-1]
        previous = df_cleaned.iloc[-2]
        
        # If there's a pending signal, check if it's confirmed or if the trend has reversed
        if self.last_signal:
            # Check for trend reversal relative to the *pending* signal's direction
            if (self.last_signal.action == 'BUY' and not current['in_uptrend']) or 
               (self.last_signal.action == 'SELL' and current['in_uptrend']):
                logger.info(f"Trend changed opposite to pending signal ({self.last_signal.action}), resetting pending signal.")
                self.last_signal = None
                self.signal_confirmed = False
                self.signal_candle_time = None
                return None # No active signal now, strategy needs to re-evaluate

            # If not reversed, check for confirmation
            if not self.signal_confirmed:
                if await self._confirm_signal(current.name):
                    logger.info(f"Confirmed PENDING TRADE SIGNAL: {self.last_signal.action} for {self.symbol}.")
                    temp_signal = self.last_signal
                    # Reset state after confirmation to allow for new signals
                    self.last_signal = None 
                    self.signal_confirmed = False
                    self.signal_candle_time = None
                    return temp_signal
                return None # Still waiting for confirmation, so no signal returned yet
            else:
                return None # Signal already confirmed, waiting for new trend change, so no signal returned
        
        # No pending signal, check for a new one
        signal_to_generate = None
        if not previous['in_uptrend'] and current['in_uptrend']:
            signal_to_generate = StrategySignal(
                action='BUY',
                symbol=self.symbol,
                strength=1.0,
                stop_loss=float(current['supertrend']),
                signal_price=float(current['close']),
                metadata={'reason': 'Supertrend flipped to UP'}
            )
        elif previous['in_uptrend'] and not current['in_uptrend']:
            signal_to_generate = StrategySignal(
                action='SELL',
                symbol=self.symbol,
                strength=1.0,
                stop_loss=float(current['supertrend']),
                signal_price=float(current['close']),
                metadata={'reason': 'Supertrend flipped to DOWN'}
            )
        
        if signal_to_generate:
            self.last_signal = signal_to_generate
            self.signal_candle_time = current.name
            logger.info(f"PENDING TRADE SIGNAL: {signal_to_generate.action} for {self.symbol}. Reason: {signal_to_generate.metadata['reason']}. SL: {signal_to_generate.stop_loss:.5f}. Waiting for confirmation (0 for immediate).")
            # If confirmation_candles_needed is 0, it will immediately confirm in the next cycle.
            return None # A pending signal is now active, but we wait for its confirmation before returning it
        
        return None # No new signal generated in this cycle

class EhlersSupertrendCrossStrategy(BaseStrategy):
    """
    A strategy based on the cross of two Ehlers Supertrend indicators
    (fast and slow), incorporating a recursive low-pass filter for smoothing.
    This version replaces scipy with a custom filter implementation and is tuned for scalping.
    """

    def __init__(self, symbol: str, config: Config):
        super().__init__(symbol, config)
        self.fast_st_period = self.config.strategy_params.get('ehlers_fast_supertrend_period', 5)
        self.fast_st_multiplier = self.config.strategy_params.get('ehlers_fast_supertrend_multiplier', 1.5)
        self.slow_st_period = self.config.strategy_params.get('ehlers_slow_supertrend_period', 10)
        self.slow_st_multiplier = self.config.strategy_params.get('ehlers_slow_supertrend_multiplier', 2.5)
        self.filter_alpha = self.config.strategy_params.get('ehlers_filter_alpha', 0.35)
        self.filter_poles = self.config.strategy_params.get('ehlers_filter_poles', 1)
        # atr_period is inherited from BaseStrategy

    def _recursive_low_pass_filter(self, data: pd.Series) -> pd.Series:
        """
        Implements a simple recursive low-pass filter by applying an EMA multiple times.
        This approximates a higher-order filter but is not a true Butterworth filter.
        The 'filter_alpha' (smoothing factor) and 'filter_poles' (number of EMA applications)
        control the smoothing and lag. For scalping, higher alpha and fewer poles for less lag.
        """
        if data.empty:
            return pd.Series(dtype=float)
        
        filtered_data = data.copy() 
        
        for _ in range(self.filter_poles):
            # The adjust=False parameter makes it a true recursive EMA
            filtered_data = filtered_data.ewm(alpha=self.filter_alpha, adjust=False).mean()
        
        return filtered_data

    async def calculate_indicators(self, data: Dict[str, pd.DataFrame]):
        """Calculates ATR and Ehlers Supertrend for fast and slow periods using recursive filter."""
        df = data.get(self.primary_timeframe)
        # Determine minimum data needed based on all relevant periods and filter requirements
        min_data_needed = max(
            self.fast_st_period, 
            self.slow_st_period, 
            self.atr_period, 
            # Note: filter_poles * 2 is a heuristic. Actual warm-up might be less for EMA.
            (self.filter_poles * 2) 
        )
        if df is None or df.empty or len(df) < min_data_needed:
            logger.debug(f"Insufficient data for Ehlers Supertrend calculation ({len(df) if df is not None else 0} < {min_data_needed} candles).")
            return

        # Apply custom recursive filter to price data
        df_filtered = df.copy() # Work on a copy to avoid modifying original df directly
        df_filtered['filtered_close'] = self._recursive_low_pass_filter(df_filtered['close'])
        df_filtered['filtered_high'] = self._recursive_low_pass_filter(df_filtered['high'])
        df_filtered['filtered_low'] = self._recursive_low_pass_filter(df_filtered['low'])
        
        # Drop NaNs introduced by filtering (especially at the beginning of the series)
        df_filtered.dropna(subset=['filtered_close', 'filtered_high', 'filtered_low'], inplace=True)

        if df_filtered.empty or len(df_filtered) < self.atr_period: # Ensure enough data for ATR after filtering
            logger.debug(f"DataFrame too small after filtering for Ehlers Supertrend calculation ({len(df_filtered)} < {self.atr_period} candles).")
            return

        # Calculate ATR on filtered prices
        high_low_filtered = df_filtered['filtered_high'] - df_filtered['filtered_low']
        high_close_filtered = np.abs(df_filtered['filtered_high'] - df_filtered['filtered_close'].shift())
        low_close_filtered = np.abs(df_filtered['filtered_low'] - df_filtered['filtered_close'].shift())
        tr_filtered = pd.concat([high_low_filtered, high_close_filtered, low_close_filtered], axis=1).max(axis=1)
        df_filtered['atr_filtered'] = tr_filtered.ewm(span=self.atr_period, adjust=False).mean()
        
        # Ensure 'atr_filtered' has enough non-NaN values for Supertrend calculation
        if df_filtered['atr_filtered'].isnull().all() or (not df_filtered['atr_filtered'].empty and df_filtered['atr_filtered'].iloc[-1] == 0):
            logger.debug("ATR filtered values are all NaN or last ATR is zero, cannot calculate Supertrend.")
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

    async def generate_signal(self, data: Dict[str, pd.DataFrame]) -> Optional[StrategySignal]:
        """Generate signal based on Ehlers Supertrend cross with confirmation."""
        await self.calculate_indicators(data)
        
        df = self.indicators.get(self.primary_timeframe)
        if df is None or df.empty or len(df) < 2:
            logger.debug("Insufficient data for Ehlers Supertrend Cross signal generation.")
            return None

        # Drop any NaN rows that might result from indicator calculation to get clean data for signal
        df_cleaned = df.dropna(subset=['supertrend_fast', 'supertrend_slow', 'atr_filtered', 'filtered_close']).copy()
        if df_cleaned.empty or len(df_cleaned) < 2:
            logger.debug("DataFrame too small after dropping NaNs for Ehlers Supertrend Cross signal generation.")
            return None

        current = df_cleaned.iloc[-1]
        previous = df_cleaned.iloc[-2]

        # Determine overall trend based on slow Supertrend
        in_uptrend_overall = current['in_uptrend_slow']

        # If there's a pending signal, check if it's confirmed or if the trend has reversed
        if self.last_signal:
            # Check for trend reversal relative to the *pending* signal's direction
            if (self.last_signal.action == 'BUY' and not in_uptrend_overall) or 
               (self.last_signal.action == 'SELL' and in_uptrend_overall):
                logger.info(f"Overall trend based on slow ST changed opposite to pending signal ({self.last_signal.action}), resetting pending signal.")
                self.last_signal = None
                self.signal_confirmed = False
                self.signal_candle_time = None
                return None # No active signal now, strategy needs to re-evaluate

            # If not reversed, check for confirmation
            if not self.signal_confirmed:
                if await self._confirm_signal(current.name):
                    logger.info(f"Confirmed PENDING TRADE SIGNAL: {self.last_signal.action} for {self.symbol}.")
                    temp_signal = self.last_signal
                    # Reset state after confirmation to allow for new signals
                    self.last_signal = None 
                    self.signal_confirmed = False
                    self.signal_candle_time = None
                    return temp_signal
                return None # Still waiting for confirmation, so no signal returned yet
            else:
                return None # Signal already confirmed, waiting for new trend change, so no signal returned
        
        # No pending signal, check for a new one
        signal_to_generate = None
        current_atr = float(current.get('atr_filtered', 0.0))
        take_profit_multiplier = self.config.strategy_params.get("take_profit_atr_multiplier", 1.0) # Scalping tuned

        # Buy signal: Fast ST crosses above Slow ST and overall trend is up
        if previous['supertrend_fast'] <= previous['supertrend_slow'] and 
           current['supertrend_fast'] > current['supertrend_slow'] and 
           in_uptrend_overall:
            take_profit_val = (float(current['close']) + current_atr * take_profit_multiplier) if current_atr > 0 else None
            
            signal_to_generate = StrategySignal(
                action='BUY',
                symbol=self.symbol,
                strength=1.0,
                stop_loss=float(current['supertrend_slow']), # Use slow ST for initial SL
                take_profit=take_profit_val,
                signal_price=float(current['close']),
                metadata={'reason': 'Ehlers Fast ST Crosses Above Slow ST (Uptrend)'}
            )
        
        # Sell signal: Fast ST crosses below Slow ST and overall trend is down
        elif previous['supertrend_fast'] >= previous['supertrend_slow'] and 
             current['supertrend_fast'] < current['supertrend_slow'] and 
             not in_uptrend_overall:
            take_profit_val = (float(current['close']) - current_atr * take_profit_multiplier) if current_atr > 0 else None

            signal_to_generate = StrategySignal(
                action='SELL',
                symbol=self.symbol,
                strength=1.0,
                stop_loss=float(current['supertrend_slow']), # Use slow ST for initial SL
                take_profit=take_profit_val,
                signal_price=float(current['close']),
                metadata={'reason': 'Ehlers Fast ST Crosses Below Slow ST (Downtrend)'}
            )
        
        if signal_to_generate:
            self.last_signal = signal_to_generate
            self.signal_candle_time = current.name
            logger.info(f"PENDING TRADE SIGNAL: {signal_to_generate.action} for {self.symbol}. Reason: {signal_to_generate.metadata['reason']}. SL: {signal_to_generate.stop_loss:.5f}, TP: {signal_to_generate.take_profit if signal_to_generate.take_profit else 'N/A':.5f}. Waiting for confirmation (0 for immediate).")
            # If confirmation_candles_needed is 0, it will immediately confirm in the next cycle.
            return None # A pending signal is now active, but we wait for its confirmation before returning it
        
        return None # No new signal generated in this cycle


# =====================================================================
# MAIN TRADING BOT CLASS
# =====================================================================

class BybitTradingBot:
    """Main trading bot class with WebSocket integration."""
    
    def __init__(self, config: Config, strategy: BaseStrategy, session: Optional[HTTP] = None):
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
        
        self.market_info: Optional[MarketInfo] = None
        self.market_data: Dict[str, pd.DataFrame] = {} # Stores raw kline data
        self.position: Optional[Position] = None
        self.balance: Decimal = Decimal('0', DECIMAL_CONTEXT) # Initialize balance with Decimal context
        self.is_running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.last_processed_candle_time: Optional[datetime] = None
        self.order_tasks: Dict[str, asyncio.Task] = {} # To track open order tasks (not fully implemented for robustness)

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
            logger.critical(f"Critical Error loading market info: {e}", exc_info=True)
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
                df['time'] = pd.to_datetime(df['time'].astype(int), unit='ms', utc=True)
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
            logger.critical(f"Critical Error loading historical data: {e}", exc_info=True)
            sys.exit(1) # Exit if historical data cannot be loaded

    async def _place_single_order(self, side: OrderSide, quantity: float, order_type: OrderType,
                                  price: Optional[float] = None, stop_loss: Optional[float] = None,
                                  take_profit: Optional[float] = None) -> Optional[str]:
        """Internal helper to place a single order with proper precision and error handling."""
        if not self.market_info:
            logger.error("Cannot place order, market info not loaded.")
            return None
        
        try:
            formatted_qty = self.market_info.format_quantity(quantity)
            if float(formatted_qty) <= float(self.market_info.lot_size): # Ensure quantity is not zero or too small after precision formatting
                logger.warning(f"Formatted quantity for order is too small ({formatted_qty}), skipping. Original: {quantity}. Minimum lot size: {self.market_info.lot_size}")
                return None

            params = {
                "category": self.config.category,
                "symbol": self.config.symbol,
                "side": side.value,
                "orderType": order_type.value,
                "qty": formatted_qty,
                "isLeverage": 1, # Always use leverage for derivatives
                "tpslMode": "Full" # Ensure SL/TP are attached to the position
            }

            if order_type == OrderType.LIMIT and price is not None:
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
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response from API'
                logger.error(f"Failed to place order: {error_msg} (Code: {response.get('retCode', 'N/A')})")
                return None
        except Exception as e:
            logger.error(f"Error placing order: {e}", exc_info=True)
            return None

    async def place_market_order(self, side: OrderSide, quantity: float, stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> Optional[str]:
        """Place a market order."""
        return await self._place_single_order(side, quantity, OrderType.MARKET, stop_loss=stop_loss, take_profit=take_profit)

    async def place_limit_order(self, side: OrderSide, quantity: float, price: float, stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> Optional[str]:
        """Place a limit order."""
        return await self._place_single_order(side, quantity, OrderType.LIMIT, price=price, stop_loss=stop_loss, take_profit=take_profit)

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
                    
                    # Try to preserve existing initial_stop_loss and entry_signal_price from internal state
                    # if position is the same. These are fixed at entry time and not usually returned by API.
                    existing_initial_sl = self.position.initial_stop_loss if self.position and self.position.side == current_position_side else None
                    existing_entry_signal_price = self.position.entry_signal_price if self.position and self.position.side == current_position_side else None

                    # Use Bybit API's reported SL/TP if available, otherwise fall back to saved internal state.
                    # Bybit's API for `stopLoss` and `takeProfit` in `get_positions` typically reflects the *active* SL/TP
                    # which for our bot would be the `trailing_stop_loss` if trailing is active.
                    bybit_sl = Decimal(pos_data['stopLoss'], DECIMAL_CONTEXT) if 'stopLoss' in pos_data and pos_data['stopLoss'] else None
                    bybit_tp = Decimal(pos_data['takeProfit'], DECIMAL_CONTEXT) if 'takeProfit' in pos_data and pos_data['takeProfit'] else None

                    # Consolidate the effective trailing SL and TP for our internal state
                    final_trailing_sl = bybit_sl if bybit_sl is not None else (self.position.trailing_stop_loss if self.position and self.position.side == current_position_side else None)
                    final_take_profit = bybit_tp if bybit_tp is not None else (self.position.take_profit if self.position and self.position.side == current_position_side else None)

                    self.position = Position(
                        symbol=self.config.symbol,
                        side=current_position_side,
                        size=size,
                        avg_price=Decimal(pos_data['avgPrice'], DECIMAL_CONTEXT),
                        unrealized_pnl=Decimal(pos_data['unrealisedPnl'], DECIMAL_CONTEXT),
                        mark_price=Decimal(pos_data['markPrice'], DECIMAL_CONTEXT),
                        leverage=int(pos_data.get('leverage', 1)),
                        entry_signal_price=existing_entry_signal_price,
                        initial_stop_loss=existing_initial_sl,
                        trailing_stop_loss=final_trailing_sl,
                        take_profit=final_take_profit
                    )
                    logger.debug(f"Position updated from API: {self.position}")
                else:
                    self.position = None
                    logger.debug("No active position found for symbol via API response.")
            else:
                self.position = None
                logger.debug("No active position found for symbol (API response list empty or retCode issue).")
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
        """
        Calculates position size based on fixed risk percentage and stop-loss distance.
        Returns the quantity in asset units (e.g., XLM amount).
        """
        if signal.stop_loss is None or signal.signal_price is None:
            logger.error("Cannot calculate position size without a valid stop-loss and signal price from the strategy.")
            return 0.0

        risk_amount_usd = self.balance * Decimal(str(self.config.risk_per_trade_pct), DECIMAL_CONTEXT)
        
        # Calculate distance to stop loss in price
        stop_loss_distance_raw = Decimal('0', DECIMAL_CONTEXT)
        signal_price_dec = Decimal(str(signal.signal_price), DECIMAL_CONTEXT)
        stop_loss_dec = Decimal(str(signal.stop_loss), DECIMAL_CONTEXT)

        if signal.action == 'BUY':
            stop_loss_distance_raw = signal_price_dec - stop_loss_dec
        elif signal.action == 'SELL':
            stop_loss_distance_raw = stop_loss_dec - signal_price_dec

        # Ensure stop_loss_distance_raw is sufficiently positive to avoid division by zero or negative risk
        if stop_loss_distance_raw <= Decimal('0', DECIMAL_CONTEXT) or stop_loss_distance_raw < self.market_info.tick_size:
            logger.warning(f"Stop loss distance is non-positive or too small ({stop_loss_distance_raw:.5f} < {self.market_info.tick_size}), cannot calculate position size safely. Returning 0.")
            return 0.0
        
        # Position size in asset units, accounting for leverage
        # Formula: Quantity = (Risk Amount / Stop Loss Distance) * Leverage
        position_size_asset_unleveraged = risk_amount_usd / stop_loss_distance_raw
        
        # Apply configured leverage
        leveraged_position_size_asset = position_size_asset_unleveraged * Decimal(str(self.config.leverage), DECIMAL_CONTEXT)
        
        # Format to market's lot size precision
        # Convert to float for `format_quantity` which expects float, then back to Decimal for the log message precision
        formatted_position_size = Decimal(self.market_info.format_quantity(float(leveraged_position_size_asset)), DECIMAL_CONTEXT)

        # Calculate order value in USDT
        order_value_usdt = formatted_position_size * signal_price_dec

        if order_value_usdt < Decimal(str(self.config.min_order_value_usdt), DECIMAL_CONTEXT):
            logger.warning(f"Calculated order value ({order_value_usdt:.2f} USDT) is below minimum required ({self.config.min_order_value_usdt} USDT). Skipping trade.")
            return 0.0

        logger.info(f"Risk Amount: {risk_amount_usd:.2f} USDT, SL Distance: {stop_loss_distance_raw:.5f} USDT, "
                    f"Calculated Position Size (Leveraged & Formatted): {formatted_position_size:.5f} {self.config.symbol}, "
                    f"Order Value: {order_value_usdt:.2f} USDT")
        
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
            tp_multiplier = Decimal(str(self.config.strategy_params.get("take_profit_atr_multiplier", 1.0)), DECIMAL_CONTEXT) # Scalping tuned default
            signal_price_dec = Decimal(str(signal.signal_price), DECIMAL_CONTEXT)
            current_atr_dec = Decimal(str(current_atr), DECIMAL_CONTEXT)

            if signal.action == 'BUY':
                signal.take_profit = float(signal_price_dec + current_atr_dec * tp_multiplier)
            elif signal.action == 'SELL':
                signal.take_profit = float(signal_price_dec - current_atr_dec * tp_multiplier)
            logger.info(f"Dynamically calculated Take Profit: {signal.take_profit:.5f}")


        position_size = self._calculate_position_size(signal)
        if position_size <= 0:
            logger.warning("Calculated position size is zero or too small, aborting trade.")
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
                    await self.get_position() # Update position state (should become None if closed)
                    await self.update_account_balance() # Update balance
                    
                    if not self.position: # Successfully closed, now open new one
                        logger.info("Existing position successfully closed. Proceeding to open new one.")
                        new_order_id = await self.place_market_order(
                            side=OrderSide.BUY if signal.action == 'BUY' else OrderSide.SELL,
                            quantity=position_size,
                            stop_loss=signal.stop_loss,
                            take_profit=signal.take_profit
                        )
                        if new_order_id:
                            # Temporarily update internal position state. Actual values will be pulled from API
                            self.position = Position(
                                symbol=self.config.symbol, side=signal.action, size=Decimal(str(position_size), DECIMAL_CONTEXT),
                                avg_price=Decimal(str(current_close_price), DECIMAL_CONTEXT), unrealized_pnl=Decimal('0', DECIMAL_CONTEXT),
                                mark_price=Decimal(str(current_close_price), DECIMAL_CONTEXT), leverage=self.config.leverage,
                                entry_signal_price=Decimal(str(signal.signal_price), DECIMAL_CONTEXT) if signal.signal_price else None,
                                initial_stop_loss=Decimal(str(signal.stop_loss), DECIMAL_CONTEXT) if signal.stop_loss else None,
                                trailing_stop_loss=Decimal(str(signal.stop_loss), DECIMAL_CONTEXT) if signal.stop_loss else None, # Initial trailing SL is the provided SL
                                take_profit=Decimal(str(signal.take_profit), DECIMAL_CONTEXT) if signal.take_profit else None
                            )
                            self._save_state()
                        else:
                            logger.error("Failed to open new position after closing existing one. Check logs for details.")
                    else:
                        logger.error("Failed to confirm closure of existing position. Aborting new trade to prevent conflicting positions.")
                else:
                    logger.error("Failed to place order to close existing position. Aborting new trade.")
                return # Handled reversing position

            # Scenario 2: Signal is in the same direction as the current position (ADJUST SL/TP)
            elif (signal.action == 'BUY' and self.position.side == 'Buy') or \
                 (signal.action == 'SELL' and self.position.side == 'Sell'):
                logger.info(f"Signal to {signal.action} received, but already in a {self.position.side} position. Considering updating SL/TP.")
                
                new_sl_to_set: Optional[Decimal] = None
                new_tp_to_set: Optional[Decimal] = None

                # Update initial_stop_loss if the new signal suggests a tighter (more favorable) SL
                if signal.stop_loss is not None:
                    new_signal_sl = Decimal(str(signal.stop_loss), DECIMAL_CONTEXT)
                    
                    # For BUY: new SL must be higher than existing initial SL (tighter)
                    # For SELL: new SL must be lower than existing initial SL (tighter)
                    should_update_initial_sl = False
                    if self.position.initial_stop_loss is None: 
                        should_update_initial_sl = True
                    elif (self.position.side == 'BUY' and new_signal_sl > self.position.initial_stop_loss):
                        should_update_initial_sl = True
                    elif (self.position.side == 'SELL' and new_signal_sl < self.position.initial_stop_loss):
                        should_update_initial_sl = True

                    if should_update_initial_sl:
                        self.position.initial_stop_loss = new_signal_sl
                        logger.info(f"Internal initial stop loss updated to new strategy SL: {new_signal_sl:.5f}")
                        
                        # Also check if the new initial SL is tighter than the current trailing SL. 
                        # If so, the trailing SL on the exchange should be moved to this new initial SL.
                        if self.position.trailing_stop_loss is None or \
                           (self.position.side == 'BUY' and new_signal_sl > self.position.trailing_stop_loss):
                           new_sl_to_set = new_signal_sl
                           logger.info(f"Trailing stop loss on exchange will be moved to new initial SL: {new_sl_to_set:.5f}")
                        elif (self.position.side == 'SELL' and new_signal_sl < self.position.trailing_stop_loss):
                           new_sl_to_set = new_signal_sl
                           logger.info(f"Trailing stop loss on exchange will be moved to new initial SL: {new_sl_to_set:.5f}")
                
                # Update take_profit if new signal suggests a better TP
                if signal.take_profit is not None:
                    new_signal_tp = Decimal(str(signal.take_profit), DECIMAL_CONTEXT)
                    
                    # For BUY: new TP must be higher than existing TP (more profitable)
                    # For SELL: new TP must be lower than existing TP (more profitable)
                    should_update_tp = False
                    if self.position.take_profit is None:
                        should_update_tp = True
                    elif (self.position.side == 'BUY' and new_signal_tp > self.position.take_profit):
                        should_update_tp = True
                    elif (self.position.side == 'SELL' and new_signal_tp < self.position.take_profit):
                        should_update_tp = True
                    
                    if should_update_tp:
                        new_tp_to_set = new_signal_tp
                        logger.info(f"Take profit updated to a more favorable level: {new_tp_to_set:.5f}")
                
                if new_sl_to_set or new_tp_to_set:
                    await self.update_stop_loss_and_take_profit(self.position.side, new_stop_loss=new_sl_to_set)
                else:
                    logger.info("No beneficial SL/TP updates from current signal, skipping API call.")
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
                # Temporarily update internal position state. Actual values will be pulled from API
                self.position = Position(
                    symbol=self.config.symbol, side=signal.action, size=Decimal(str(position_size), DECIMAL_CONTEXT),
                    avg_price=Decimal(str(current_close_price), DECIMAL_CONTEXT), unrealized_pnl=Decimal('0', DECIMAL_CONTEXT),
                    mark_price=Decimal(str(current_close_price), DECIMAL_CONTEXT), leverage=self.config.leverage,
                    entry_signal_price=Decimal(str(signal.signal_price), DECIMAL_CONTEXT) if signal.signal_price else None,
                    initial_stop_loss=Decimal(str(signal.stop_loss), DECIMAL_CONTEXT) if signal.stop_loss else None,
                    trailing_stop_loss=Decimal(str(signal.stop_loss), DECIMAL_CONTEXT) if signal.stop_loss else None, # Initial trailing SL is the provided SL
                    take_profit=Decimal(str(signal.take_profit), DECIMAL_CONTEXT) if signal.take_profit else None
                )
                self._save_state()
            else:
                logger.error("Failed to open new position. Check logs for details.")
            return # Handled opening new position


    async def _update_trailing_stop_loss(self):
        """
        Updates the trailing stop loss for an open position.
        Activates when profit reaches 'break_even_profit_atr_multiplier' * ATR (to break-even)
        or 'trailing_stop_loss_activation_atr_multiplier' * ATR (to trail more aggressively).
        Moves by 'trailing_stop_loss_atr_multiplier' * ATR.
        """
        if not self.position or self.position.entry_signal_price is None or self.position.initial_stop_loss is None or \
           self.strategy.indicators.get(self.config.timeframe) is None or self.strategy.indicators[self.config.timeframe].empty:
            logger.debug("Cannot update trailing stop: no position, no entry price/initial SL, or no indicators.")
            return

        current_df = self.strategy.indicators[self.config.timeframe].iloc[-1]
        current_price = Decimal(str(current_df['close']), DECIMAL_CONTEXT)
        
        current_atr = Decimal(str(current_df.get('atr_filtered', current_df.get('atr', 0.0))), DECIMAL_CONTEXT)
        if current_atr <= 0:
            logger.warning("ATR not available or non-positive for trailing stop calculation.")
            return

        activation_multiplier = Decimal(str(self.config.strategy_params.get("trailing_stop_loss_activation_atr_multiplier", 0.5)), DECIMAL_CONTEXT) # Scalping tuned
        trailing_multiplier = Decimal(str(self.config.strategy_params.get("trailing_stop_loss_atr_multiplier", 0.75)), DECIMAL_CONTEXT) # Scalping tuned
        break_even_profit_multiplier = Decimal(str(self.config.strategy_params.get("break_even_profit_atr_multiplier", 0.2)), DECIMAL_CONTEXT) # Scalping tuned

        # Calculate current profit in USD and ATR units
        profit_in_usd = Decimal('0', DECIMAL_CONTEXT)
        if self.position.side == 'BUY':
            profit_in_usd = current_price - self.position.entry_signal_price
        elif self.position.side == 'SELL':
            profit_in_usd = self.position.entry_signal_price - current_price
        
        profit_in_atr = profit_in_usd / current_atr if current_atr > 0 else Decimal('0', DECIMAL_CONTEXT)

        # Determine potential new trailing stop price
        potential_new_stop_price: Optional[Decimal] = None
        current_trailing_sl = self.position.trailing_stop_loss # The last SL value we set on the exchange
        initial_sl = self.position.initial_stop_loss # The initial SL from the strategy signal

        # For BUY position
        if self.position.side == 'BUY':
            # 1. Move to break-even + a small buffer if profit condition is met
            if profit_in_atr >= break_even_profit_multiplier:
                # Calculate break-even SL with a small buffer (e.g., 0.05 ATR above entry)
                calculated_be_sl = self.position.entry_signal_price + (current_atr * Decimal('0.05', DECIMAL_CONTEXT))
                # The new potential SL should be at least the initial SL, and higher than the current trailing SL (if set)
                if current_trailing_sl is None or calculated_be_sl > current_trailing_sl:
                    potential_new_stop_price = max(calculated_be_sl, initial_sl)
            
            # 2. Aggressively trail if a higher profit condition is met
            if profit_in_atr >= activation_multiplier:
                trailing_point_sl = current_price - (current_atr * trailing_multiplier)
                # If this trailing point is higher than the current best potential SL, use it
                if potential_new_stop_price is None or trailing_point_sl > potential_new_stop_price:
                     potential_new_stop_price = max(trailing_point_sl, initial_sl)
            
            # Final safety check: ensure potential_new_stop_price is never below initial_sl
            if potential_new_stop_price and potential_new_stop_price < initial_sl:
                potential_new_stop_price = initial_sl

        # For SELL position
        elif self.position.side == 'SELL':
            # 1. Move to break-even + a small buffer if profit condition is met
            if profit_in_atr >= break_even_profit_multiplier:
                # Calculate break-even SL with a small buffer (e.g., 0.05 ATR below entry)
                calculated_be_sl = self.position.entry_signal_price - (current_atr * Decimal('0.05', DECIMAL_CONTEXT))
                # The new potential SL should be at most the initial SL, and lower than the current trailing SL (if set)
                if current_trailing_sl is None or calculated_be_sl < current_trailing_sl:
                    potential_new_stop_price = min(calculated_be_sl, initial_sl)
            
            # 2. Aggressively trail if a higher profit condition is met
            if profit_in_atr >= activation_multiplier:
                trailing_point_sl = current_price + (current_atr * trailing_multiplier)
                # If this trailing point is lower than the current best potential SL, use it
                if potential_new_stop_price is None or trailing_point_sl < potential_new_stop_price:
                     potential_new_stop_price = min(trailing_point_sl, initial_sl)
            
            # Final safety check: ensure potential_new_stop_price is never above initial_sl
            if potential_new_stop_price and potential_new_stop_price > initial_sl:
                potential_new_stop_price = initial_sl
        
        # Now, compare the determined `potential_new_stop_price` with the `current_trailing_sl` on the exchange
        if potential_new_stop_price is not None:
            should_update_exchange = False
            if current_trailing_sl is None: # No current trailing SL set on exchange
                should_update_exchange = True
            elif current_trailing_sl == potential_new_stop_price: # No change
                should_update_exchange = False
            elif self.position.side == 'BUY' and potential_new_stop_price > current_trailing_sl: # Move SL up for a Buy
                should_update_exchange = True
            elif self.position.side == 'SELL' and potential_new_stop_price < current_trailing_sl: # Move SL down for a Sell
                should_update_exchange = True

            if should_update_exchange:
                # Call update_stop_loss_and_take_profit, which will also update self.position.trailing_stop_loss and save state
                logger.info(f"Trailing SL update triggered for {self.position.side} position. Old: {current_trailing_sl:.5f if current_trailing_sl else 'N/A'}, New: {potential_new_stop_price:.5f}")
                await self.update_stop_loss_and_take_profit(self.position.side, new_stop_loss=potential_new_stop_price)
            else:
                logger.debug(f"Calculated trailing stop {potential_new_stop_price:.5f} is not better than current {current_trailing_sl:.5f if current_trailing_sl else 'N/A'}, skipping update.")
        else:
            logger.debug(f"Profit {profit_in_atr:.2f} ATR. Trailing stop conditions not met yet or no beneficial move calculated.")

# --- MAIN EXECUTION BLOCK ---

if __name__ == "__main__":
    if not os.getenv("BYBIT_API_KEY") or not os.getenv("BYBIT_API_SECRET"):
        logger.critical("API keys are not set. Please create a .env file.")
        sys.exit(1)

    bot_config = Config()
    
    if bot_config.strategy_name == "Supertrend":
        bot_strategy = SupertrendStrategy(symbol=bot_config.symbol, config=bot_config)
    else:
        logger.critical(f"Unknown strategy: {bot_config.strategy_name}")
        sys.exit(1)
        
    bot = BybitTradingBot(config=bot_config, strategy=bot_strategy)

    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
        asyncio.run(bot.stop())
    except Exception as e:
        logger.critical(f"An unhandled exception occurred: {e}", exc_info=True)
        asyncio.run(bot.stop())
