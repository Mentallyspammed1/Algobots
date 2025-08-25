'''
'''
I've enhanced the bot with the requested updates, focusing on improving signal generation and risk management.

Here's a summary of the changes implemented for each snippet:

1.  **Signal Strength Scoring:**
    *   A `MIN_SIGNAL_STRENGTH` configuration option was added.
    *   The `generate_signal` function now calculates a `signal_strength` score by incrementing it for each confirming indicator (Ehlers Filter, RSI, MACD, VWAP, ADX, MTF, Candlestick Patterns).
    *   Signals are only returned if their `signal_strength` meets the configured `MIN_SIGNAL_STRENGTH`.
    *   The `execute_trade_based_on_signal` and `_process_websocket_message` functions were updated to handle the new `signal_strength` return value and enforce the minimum strength requirement.
    *   Log messages now include the signal strength.
2.  **Dynamic Take Profit with ATR Quality Check:**
    *   A `MIN_ATR_TP_THRESHOLD_PCT` configuration was added.
    *   The `calculate_trade_sl_tp` function now checks if the current ATR is below this threshold. If it is, indicating low volatility, the bot falls back to using the fixed `TAKE_PROFIT_PCT` instead of a potentially too-small dynamic TP.
3.  **VWAP as Additional Entry Confirmation:**
    *   `VWAP_CONFIRMATION_ENABLED` and `VWAP_WINDOW` configurations were added.
    *   The `calculate_indicators` function now includes VWAP calculation.
    *   The `generate_signal` function incorporates VWAP confirmation: for buy signals, price must be above VWAP; for sell signals, price must be below VWAP. This contributes to the overall `signal_strength`.
4.  **Trailing Stop based on Ehlers Supertrend Line:**
    *   `EHLERS_ST_TRAILING_ENABLED` and `EHLERS_ST_TRAILING_OFFSET_PCT` configurations were added.
    *   The `TrailingStopManager` was modified to support this new trailing stop method.
    *   When `EHLERS_ST_TRAILING_ENABLED` is true, the stop loss is dynamically updated to trail the Ehlers Supertrend line plus/minus a small offset, only moving in a direction favorable to the position.
    *   The `execute_trade_based_on_signal` function now passes the Ehlers Supertrend line value to the `TrailingStopManager`.
5.  **Volatility-Adjusted Position Sizing Robustness:**
    *   A `MIN_ATR_FOR_SIZING_PCT` configuration was added.
    *   The `OrderSizingCalculator.calculate_position_size_usd` function now includes a check to see if the current ATR (as a percentage of price) is too low. If it is, it indicates very low volatility which could lead to an unrealistically tight stop loss and an excessively large position. In such cases, the sizing calculation falls back to using `MAX_RISK_PER_TRADE_BALANCE_PCT` to prevent over-sizing.
6.  **Time-Based Exit for Unprofitable Trades:**
    *   `TIME_BASED_EXIT_ENABLED` and `UNPROFITABLE_TRADE_MAX_BARS` configurations were added.
    *   A new method `_manage_time_based_exit` was introduced.
    *   This function is called on each new confirmed candle and closes any active, unprofitable trade that has been open for more than `UNPROFITABLE_TRADE_MAX_BARS`.
    *   The `open_trade_kline_ts` is set when a new position is opened to track its age.
7.  **Session-Based Volatility Filter:**
    *   `SESSION_FILTER_ENABLED`, `SESSION_START_HOUR_UTC`, `SESSION_END_HOUR_UTC`, and `SESSION_MIN_VOLATILITY_FACTOR` configurations were added.
    *   A new method `_is_session_active_and_volatile` was added.
    *   This filter checks if the current time falls within specified UTC trading hours and if the market's volatility (measured by ATR as a percentage of price) meets a minimum threshold. If not, trade execution is paused.
8.  **Dynamic Signal Cooldown based on Volatility:**
    *   `DYNAMIC_COOLDOWN_ENABLED`, `COOLDOWN_VOLATILITY_FACTOR_HIGH`, and `COOLDOWN_VOLATILITY_FACTOR_LOW` configurations were added.
    *   The `execute_trade_based_on_signal` function now dynamically adjusts the `SIGNAL_COOLDOWN_SEC` based on current market volatility (ATR). In high volatility, cooldown is reduced; in low volatility, it's increased to prevent overtrading.
9.  **Order Book Depth Check for Limit Orders:**
    *   `ORDER_BOOK_DEPTH_CHECK_ENABLED` and `MIN_LIQUIDITY_DEPTH_USD` configurations were added.
    *   A `get_orderbook` method was added to `BybitClient`.
    *   Before placing any limit order (especially for retracement entries), the `place_order` function now fetches the order book and checks if there's enough liquidity at or better than the intended entry price. If not, the order placement is aborted to prevent partial fills or missed entries.
10. **Multi-Tier Breakeven Stop Loss:**
    *   `MULTI_TIER_BREAKEVEN_ENABLED` and `BREAKEVEN_PROFIT_TIERS` configurations were added.
    *   The `_manage_breakeven_stop_loss` function was expanded to support multiple profit tiers. As the position's profit crosses each defined tier, the stop loss is progressively moved to breakeven plus a small profit offset for that tier, locking in more profit as the trade progresses.
    *   A `breakeven_tier_activated` dictionary now tracks which tiers have been hit for the current position.

'''
#!/usr/bin/env python3
import json
import logging
import os
import random
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from enum import Enum
from typing import Any

import colorlog
import dateutil.parser
import dateutil.tz
import numpy as np
import pandas as pd
import requests
import ta
from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.exceptions import FailedRequestError, InvalidRequestError
from pybit.unified_trading import HTTP, WebSocket

# Initialize Colorama for brilliant terminal outputs
init(autoreset=True)

# Load environment variables from .env file
load_dotenv()

# --- GLOBAL TEMPORAL CONVERSION UTILITIES ---
# Forging a map to translate arcane timezone abbreviations into their true IANA forms.
# This utility is available for any external date string parsing,
# though Bybit's timestamps are already UTC Unix milliseconds.
tz_mapping = {
    "EST": dateutil.tz.gettz("America/New_York"), "EDT": dateutil.tz.gettz("America/New_York"),
    "CST": dateutil.tz.gettz("America/Chicago"), "CDT": dateutil.tz.gettz("America/Chicago"),
    "MST": dateutil.tz.gettz("America/Denver"), "MDT": dateutil.tz.gettz("America/Denver"),
    "PST": dateutil.tz.gettz("America/Los_Angeles"), "PDT": dateutil.tz.gettz("America/Los_Angeles"),
    "BST": dateutil.tz.gettz("Europe/London"), "GMT": dateutil.tz.gettz("GMT"),
    "CET": dateutil.tz.gettz("Europe/Paris"), "CEST": dateutil.tz.gettz("Europe/Paris"),
    "JST": dateutil.tz.gettz("Asia/Tokyo"), "AEST": dateutil.tz.gettz("Australia/Sydney"),
    "AEDT": dateutil.tz.gettz("Australia/Sydney"),
}

def parse_to_utc(dt_str: str) -> datetime | None:
    """
    An incantation to transmute a date/time string from any known locale
    or timezone into a pure, naive UTC datetime object.
    It drops timezone info with replace(tzinfo=None) for consistency after conversion.
    """
    try:
        dt = dateutil.parser.parse(dt_str, tzinfos=tz_mapping)
        return dt.astimezone(dateutil.tz.UTC).replace(tzinfo=None)
    except Exception as e:
        logger.error(f"Failed to parse or convert '{dt_str}' to UTC: {e}")
        return None
# --- END GLOBAL TEMPORAL CONVERSION UTILITIES ---


# =====================================================================
# CONFIGURATION & ENUMS
# =====================================================================

class Signal(Enum):
    """Trading signals"""
    STRONG_BUY = 2
    BUY = 1
    NEUTRAL = 0
    SELL = -1
    STRONG_SELL = -2


class OrderType(Enum):
    """Supported order types"""
    MARKET = "Market"
    LIMIT = "Limit"


class Category(Enum):
    """Bybit product categories"""
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
            raise ValueError(f"Invalid Category value: {value}. Choose from {[c.name for c in cls]}")


@dataclass
class Config:
    """Bot configuration, loaded from environment variables."""
    # API Configuration
    API_KEY: str = field(default="YOUR_BYBIT_API_KEY")
    API_SECRET: str = field(default="YOUR_BYBIT_API_SECRET")
    TESTNET: bool = field(default=False)

    # Trading Configuration
    SYMBOL: str = field(default="TRUMPUSDT")
    CATEGORY: str = field(default="linear")
    LEVERAGE: int = field(default=25)
    MARGIN_MODE: int = field(default=0) # 0 for cross, 1 for isolated
    HEDGE_MODE: bool = field(default=False)
    POSITION_IDX: int = field(default=0) # 0=One-way mode, 1=Long, 2=Short in hedge mode

    # Position Sizing
    RISK_PER_TRADE_PCT: float = field(default=1.0) # Risk % of account balance per trade
    MAX_POSITION_SIZE_USD: float = field(default=20.0) # Max position value in USD
    MIN_POSITION_SIZE_USD: float = field(default=5.0) # Min position value in USD

    # Strategy Parameters
    TIMEFRAME: str = field(default="1") # Kline interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)
    LOOKBACK_PERIODS: int = field(default=500) # Historical data to fetch for indicators

    # Ehlers Adaptive Trend Parameters (from supertrend.py)
    EHLERS_LENGTH: int = field(default=8)
    SMOOTHING_LENGTH: int = field(default=12)
    SENSITIVITY: float = field(default=1.0)

    # Ehlers Supertrend Indicator Parameters (from supertrend.py)
    EHLERS_ST_LENGTH: int = field(default=8)
    EHLERS_ST_MULTIPLIER: float = field(default=1.2)

    # Other Indicator Parameters
    RSI_WINDOW: int = field(default=8)
    MACD_FAST: int = field(default=8)
    MACD_SLOW: int = field(default=12)
    MACD_SIGNAL: int = field(default=9)
    ADX_WINDOW: int = field(default=10) # Added ADX_WINDOW

    # Risk Management
    STOP_LOSS_PCT: float = field(default=0.005) # 0.5% stop loss from entry
    TAKE_PROFIT_PCT: float = field(default=0.01) # 1% take profit from entry
    TRAILING_STOP_PCT: float = field(default=0.005) # 0.5% trailing stop from highest profit
    MAX_DAILY_LOSS_PCT: float = field(default=0.05) # 5% max daily loss from start balance

    # Execution Settings
    ORDER_TYPE: str = field(default="Market")
    TIME_IN_FORCE: str = field(default="GTC")
    REDUCE_ONLY: bool = field(default=False)

    # Bot Settings
    LOOP_INTERVAL_SEC: int = field(default=60) # Check interval in seconds (less relevant with WS, but for other tasks)
    LOG_LEVEL: str = field(default="INFO")
    LOG_FILE: str = field(default="ehlers_supertrend_bot.log")
    JSON_LOG_FILE: str = field(default="ehlers_supertrend_bot.jsonl")
    LOG_TO_STDOUT_ONLY: bool = field(default=False) # Not directly used with colorlog, but kept for consistency

    # API Retry Settings
    MAX_API_RETRIES: int = field(default=5) # Increased from 3
    API_RETRY_DELAY_SEC: int = field(default=5)

    # Termux SMS Notification
    TERMUX_SMS_RECIPIENT_NUMBER: str | None = field(default=None)

    # New setting for graceful shutdown
    AUTO_CLOSE_ON_SHUTDOWN: bool = field(default=False)

    # Signal Confirmation
    SIGNAL_COOLDOWN_SEC: int = field(default=10)
    SIGNAL_CONFIRM_BARS: int = field(default=1)

    # Dry Run Mode (for testing without placing actual orders)
    DRY_RUN: bool = field(default=False)

    # --- NEW FEATURES CONFIGURATION ---
    # Dynamic Take Profit (DTP) via ATR
    DYNAMIC_TP_ENABLED: bool = field(default=False)
    ATR_TP_WINDOW: int = field(default=14)
    ATR_TP_MULTIPLIER: float = field(default=1.5)
    MIN_TAKE_PROFIT_PCT: float = field(default=0.002)
    MAX_TAKE_PROFIT_PCT: float = field(default=0.02)

    # Breakeven Stop Loss Activation
    BREAKEVEN_ENABLED: bool = field(default=False)
    BREAKEVEN_PROFIT_TRIGGER_PCT: float = field(default=0.005)
    BREAKEVEN_OFFSET_PCT: float = field(default=0.0001)

    # Partial Take Profit (Scaling Out)
    PARTIAL_TP_ENABLED: bool = field(default=False)
    PARTIAL_TP_TARGETS: list[dict[str, float]] = field(default_factory=lambda: [
        {"profit_pct": 0.008, "close_qty_pct": 0.3},
        {"profit_pct": 0.015, "close_qty_pct": 0.4}
    ])

    # Volatility-Adjusted Position Sizing
    VOLATILITY_ADJUSTED_SIZING_ENABLED: bool = field(default=False)
    VOLATILITY_WINDOW: int = field(default=20)
    TARGET_RISK_ATR_MULTIPLIER: float = field(default=1.0)
    MAX_RISK_PER_TRADE_BALANCE_PCT: float = field(default=0.015)

    # Market Trend Filter (ADX-based)
    ADX_TREND_FILTER_ENABLED: bool = field(default=False)
    ADX_MIN_THRESHOLD: int = field(default=25)
    ADX_TREND_DIRECTION_CONFIRMATION: bool = field(default=True)

    # Time-Based Trading Window
    TIME_WINDOW_ENABLED: bool = field(default=False)
    TRADE_START_HOUR_UTC: int = field(default=8)
    TRADE_END_HOUR_UTC: int = field(default=20)
    TRADE_DAYS_OF_WEEK: list[str] = field(default_factory=lambda: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])

    # Max Concurrent Positions Limit
    MAX_CONCURRENT_POSITIONS: int = field(default=1) # Default to 1 for single-symbol bot

    # Signal Retracement Entry
    RETRACEMENT_ENTRY_ENABLED: bool = field(default=False)
    RETRACEMENT_PCT_FROM_CLOSE: float = field(default=0.001)
    RETRACEMENT_ORDER_TYPE: str = field(default="LIMIT") # Can be "LIMIT" or "MARKET" for immediate entry if retracement missed
    RETRACEMENT_CANDLE_WAIT: int = field(default=1) # How many candles to wait for limit order fill before cancelling

    # Multiple Timeframe Confluence Filter
    MULTI_TIMEFRAME_CONFIRMATION_ENABLED: bool = field(default=False)
    HIGHER_TIMEFRAME: str = field(default="5") # e.g., "5" for 5-minute
    HIGHER_TIMEFRAME_INDICATOR: str = field(default="EHLERS_SUPERTR_DIRECTION") # e.g., "EHLERS_SUPERTR_DIRECTION", "ADX_TREND"
    REQUIRED_CONFLUENCE: bool = field(default=True)

    # Profit Target Trailing Stop (Dynamic Trailing)
    DYNAMIC_TRAILING_ENABLED: bool = field(default=False)
    TRAILING_PROFIT_TIERS: list[dict[str, float]] = field(default_factory=lambda: [
        {"profit_pct_trigger": 0.01, "new_trail_pct": 0.003},
        {"profit_pct_trigger": 0.02, "new_trail_pct": 0.002}
    ])

    # Slippage Tolerance for Market Orders
    SLIPPAGE_TOLERANCE_PCT: float = field(default=0.0015)

    # Funding Rate Avoidance (Perpetuals)
    FUNDING_RATE_AVOIDANCE_ENABLED: bool = field(default=False)
    FUNDING_RATE_THRESHOLD_PCT: float = field(default=0.0005) # 0.05%
    FUNDING_GRACE_PERIOD_MINUTES: int = field(default=10)

    # News Event Trading Pause
    NEWS_PAUSE_ENABLED: bool = field(default=False)
    NEWS_API_ENDPOINT: str | None = field(default=None) # e.g., "https://api.finnhub.io/api/v1/calendar/economic"
    NEWS_API_KEY: str | None = field(default=None)
    IMPACT_LEVELS_TO_PAUSE: list[str] = field(default_factory=lambda: ["High"]) # e.g., ["High", "Medium"]
    PAUSE_PRE_EVENT_MINUTES: int = field(default=15)
    PAUSE_POST_EVENT_MINUTES: int = field(default=30)

    # Adaptive Indicator Parameters (Volatility-Based)
    ADAPTIVE_INDICATORS_ENABLED: bool = field(default=False)
    VOLATILITY_MEASURE_WINDOW: int = field(default=20)
    VOLATILITY_THRESHOLD_HIGH: float = field(default=0.005) # e.g., 0.5% avg daily range
    VOLATILITY_THRESHOLD_LOW: float = field(default=0.001) # e.g., 0.1% avg daily range
    EHLERS_LENGTH_HIGH_VOL: int = field(default=20)
    EHLERS_LENGTH_LOW_VOL: int = field(default=40)
    RSI_WINDOW_HIGH_VOL: int = field(default=10)
    RSI_WINDOW_LOW_VOL: int = field(default=20)

    # Price Action Confirmation (Candlestick Patterns)
    PRICE_ACTION_CONFIRMATION_ENABLED: bool = field(default=False)
    REQUIRED_BULLISH_PATTERNS: list[str] = field(default_factory=lambda: ["ENGULFING", "HAMMER"])
    REQUIRED_BEARISH_PATTERNS: list[str] = field(default_factory=lambda: ["BEARISH_ENGULFING", "SHOOTING_STAR"])
    PATTERN_STRENGTH_MULTIPLIER: float = field(default=0.75)

    # Snippet 1: Signal Strength Scoring
    MIN_SIGNAL_STRENGTH: int = field(default=3)

    # Snippet 2: Dynamic Take Profit with ATR Quality Check
    MIN_ATR_TP_THRESHOLD_PCT: float = field(default=0.0005) # 0.05%

    # Snippet 3: VWAP as Additional Entry Confirmation
    VWAP_CONFIRMATION_ENABLED: bool = field(default=False)
    VWAP_WINDOW: int = field(default=20)

    # Snippet 4: Trailing Stop based on Ehlers Supertrend Line
    EHLERS_ST_TRAILING_ENABLED: bool = field(default=False)
    EHLERS_ST_TRAILING_OFFSET_PCT: float = field(default=0.001)

    # Snippet 5: Volatility-Adjusted Position Sizing Robustness
    MIN_ATR_FOR_SIZING_PCT: float = field(default=0.001) # 0.1%

    # Snippet 6: Time-Based Exit for Unprofitable Trades
    TIME_BASED_EXIT_ENABLED: bool = field(default=False)
    UNPROFITABLE_TRADE_MAX_BARS: int = field(default=10)

    # Snippet 7: Session-Based Volatility Filter
    SESSION_FILTER_ENABLED: bool = field(default=False)
    SESSION_START_HOUR_UTC: int = field(default=8)
    SESSION_END_HOUR_UTC: int = field(default=20)
    SESSION_MIN_VOLATILITY_FACTOR: float = field(default=0.0005) # 0.05% of price

    # Snippet 8: Dynamic Signal Cooldown based on Volatility
    DYNAMIC_COOLDOWN_ENABLED: bool = field(default=False)
    COOLDOWN_VOLATILITY_FACTOR_HIGH: float = field(default=0.5)
    COOLDOWN_VOLATILITY_FACTOR_LOW: float = field(default=1.5)

    # Snippet 9: Order Book Depth Check for Limit Orders
    ORDER_BOOK_DEPTH_CHECK_ENABLED: bool = field(default=False)
    MIN_LIQUIDITY_DEPTH_USD: float = field(default=50.0)

    # Snippet 10: Multi-Tier Breakeven Stop Loss
    MULTI_TIER_BREAKEVEN_ENABLED: bool = field(default=False)
    BREAKEVEN_PROFIT_TIERS: list[dict[str, float]] = field(default_factory=lambda: [
        {"profit_pct": 0.005, "offset_pct": 0.0001},
        {"profit_pct": 0.01, "offset_pct": 0.0005}
    ])


    def __post_init__(self):
        """Load configuration from environment variables and validate."""
        self.API_KEY = os.getenv("BYBIT_API_KEY", self.API_KEY)
        self.API_SECRET = os.getenv("BYBIT_API_SECRET", self.API_SECRET)
        self.TESTNET = os.getenv("BYBIT_TESTNET", str(self.TESTNET)).lower() in ['true', '1', 't']
        self.SYMBOL = os.getenv("TRADING_SYMBOL", self.SYMBOL)
        self.CATEGORY = os.getenv("BYBIT_CATEGORY", self.CATEGORY)
        self.LEVERAGE = int(os.getenv("BYBIT_LEVERAGE", self.LEVERAGE))
        self.MARGIN_MODE = int(os.getenv("BYBIT_MARGIN_MODE", self.MARGIN_MODE))
        self.HEDGE_MODE = os.getenv("BYBIT_HEDGE_MODE", str(self.HEDGE_MODE)).lower() in ['true', '1', 't']
        self.POSITION_IDX = int(os.getenv("BYBIT_POSITION_IDX", self.POSITION_IDX))

        self.RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", self.RISK_PER_TRADE_PCT))
        self.MAX_POSITION_SIZE_USD = float(os.getenv("BYBIT_MAX_POSITION_SIZE_USD", self.MAX_POSITION_SIZE_USD))
        self.MIN_POSITION_SIZE_USD = float(os.getenv("BYBIT_MIN_POSITION_SIZE_USD", self.MIN_POSITION_SIZE_USD))

        self.TIMEFRAME = os.getenv("TRADING_TIMEFRAME", self.TIMEFRAME)
        self.LOOKBACK_PERIODS = int(os.getenv("BYBIT_LOOKBACK_PERIODS", self.LOOKBACK_PERIODS))

        self.EHLERS_LENGTH = int(os.getenv("EHLERS_LENGTH", self.EHLERS_LENGTH))
        self.SMOOTHING_LENGTH = int(os.getenv("SMOOTHING_LENGTH", self.SMOOTHING_LENGTH))
        self.SENSITIVITY = float(os.getenv("SENSITIVITY", self.SENSITIVITY))

        self.EHLERS_ST_LENGTH = int(os.getenv("EHLERS_ST_LENGTH", self.EHLERS_ST_LENGTH))
        self.EHLERS_ST_MULTIPLIER = float(os.getenv("EHLERS_ST_MULTIPLIER", self.EHLERS_ST_MULTIPLIER))

        self.RSI_WINDOW = int(os.getenv("RSI_WINDOW", self.RSI_WINDOW))
        self.MACD_FAST = int(os.getenv("MACD_FAST", self.MACD_FAST))
        self.MACD_SLOW = int(os.getenv("MACD_SLOW", self.MACD_SLOW))
        self.MACD_SIGNAL = int(os.getenv("MACD_SIGNAL", self.MACD_SIGNAL))
        self.ADX_WINDOW = int(os.getenv("ADX_WINDOW", self.ADX_WINDOW))

        self.STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", self.STOP_LOSS_PCT))
        self.TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", self.TAKE_PROFIT_PCT))
        self.TRAILING_STOP_PCT = float(os.getenv("TRAILING_STOP_PCT", self.TRAILING_STOP_PCT))
        self.MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", self.MAX_DAILY_LOSS_PCT))

        self.ORDER_TYPE = os.getenv("BYBIT_ORDER_TYPE", self.ORDER_TYPE)
        self.TIME_IN_FORCE = os.getenv("BYBIT_TIME_IN_FORCE", self.TIME_IN_FORCE)
        self.REDUCE_ONLY = os.getenv("BYBIT_REDUCE_ONLY", str(self.REDUCE_ONLY)).lower() in ['true', '1', 't']

        self.LOOP_INTERVAL_SEC = int(os.getenv("BYBIT_LOOP_INTERVAL_SEC", self.LOOP_INTERVAL_SEC))
        self.LOG_LEVEL = os.getenv("BYBIT_LOG_LEVEL", self.LOG_LEVEL)
        self.LOG_FILE = os.getenv("BYBIT_LOG_FILE", self.LOG_FILE)
        self.JSON_LOG_FILE = os.getenv("BYBIT_JSON_LOG_FILE", self.JSON_LOG_FILE)

        self.MAX_API_RETRIES = int(os.getenv("BYBIT_MAX_API_RETRIES", self.MAX_API_RETRIES))
        self.API_RETRY_DELAY_SEC = int(os.getenv("BYBIT_API_RETRY_DELAY_SEC", self.API_RETRY_DELAY_SEC))

        self.TERMUX_SMS_RECIPIENT_NUMBER = os.getenv("TERMUX_SMS_RECIPIENT_NUMBER", self.TERMUX_SMS_RECIPIENT_NUMBER)
        self.AUTO_CLOSE_ON_SHUTDOWN = os.getenv("BYBIT_AUTO_CLOSE_ON_SHUTDOWN", str(self.AUTO_CLOSE_ON_SHUTDOWN)).lower() in ['true', '1', 't']
        self.SIGNAL_COOLDOWN_SEC = int(os.getenv("SIGNAL_COOLDOWN_SEC", self.SIGNAL_COOLDOWN_SEC))
        self.SIGNAL_CONFIRM_BARS = int(os.getenv("SIGNAL_CONFIRM_BARS", self.SIGNAL_CONFIRM_BARS))
        self.DRY_RUN = os.getenv("BYBIT_DRY_RUN", str(self.DRY_RUN)).lower() in ['true', '1', 't']

        # --- Load NEW FEATURES CONFIGURATION from environment variables ---
        self.DYNAMIC_TP_ENABLED = os.getenv("DYNAMIC_TP_ENABLED", str(self.DYNAMIC_TP_ENABLED)).lower() in ['true', '1', 't']
        self.ATR_TP_WINDOW = int(os.getenv("ATR_TP_WINDOW", self.ATR_TP_WINDOW))
        self.ATR_TP_MULTIPLIER = float(os.getenv("ATR_TP_MULTIPLIER", self.ATR_TP_MULTIPLIER))
        self.MIN_TAKE_PROFIT_PCT = float(os.getenv("MIN_TAKE_PROFIT_PCT", self.MIN_TAKE_PROFIT_PCT))
        self.MAX_TAKE_PROFIT_PCT = float(os.getenv("MAX_TAKE_PROFIT_PCT", self.MAX_TAKE_PROFIT_PCT))

        self.BREAKEVEN_ENABLED = os.getenv("BREAKEVEN_ENABLED", str(self.BREAKEVEN_ENABLED)).lower() in ['true', '1', 't']
        self.BREAKEVEN_PROFIT_TRIGGER_PCT = float(os.getenv("BREAKEVEN_PROFIT_TRIGGER_PCT", self.BREAKEVEN_PROFIT_TRIGGER_PCT))
        self.BREAKEVEN_OFFSET_PCT = float(os.getenv("BREAKEVEN_OFFSET_PCT", self.BREAKEVEN_OFFSET_PCT))

        self.PARTIAL_TP_ENABLED = os.getenv("PARTIAL_TP_ENABLED", str(self.PARTIAL_TP_ENABLED)).lower() in ['true', '1', 't']
        partial_tp_targets_str = os.getenv("PARTIAL_TP_TARGETS")
        if partial_tp_targets_str:
            try:
                self.PARTIAL_TP_TARGETS = json.loads(partial_tp_targets_str)
            except json.JSONDecodeError:
                print(f"Warning: Could not decode PARTIAL_TP_TARGETS from environment variable: {partial_tp_targets_str}. Using default.")

        self.VOLATILITY_ADJUSTED_SIZING_ENABLED = os.getenv("VOLATILITY_ADJUSTED_SIZING_ENABLED", str(self.VOLATILITY_ADJUSTED_SIZING_ENABLED)).lower() in ['true', '1', 't']
        self.VOLATILITY_WINDOW = int(os.getenv("VOLATILITY_WINDOW", self.VOLATILITY_WINDOW))
        self.TARGET_RISK_ATR_MULTIPLIER = float(os.getenv("TARGET_RISK_ATR_MULTIPLIER", self.TARGET_RISK_ATR_MULTIPLIER))
        self.MAX_RISK_PER_TRADE_BALANCE_PCT = float(os.getenv("MAX_RISK_PER_TRADE_BALANCE_PCT", self.MAX_RISK_PER_TRADE_BALANCE_PCT))

        self.ADX_TREND_FILTER_ENABLED = os.getenv("ADX_TREND_FILTER_ENABLED", str(self.ADX_TREND_FILTER_ENABLED)).lower() in ['true', '1', 't']
        self.ADX_MIN_THRESHOLD = int(os.getenv("ADX_MIN_THRESHOLD", self.ADX_MIN_THRESHOLD))
        self.ADX_TREND_DIRECTION_CONFIRMATION = os.getenv("ADX_TREND_DIRECTION_CONFIRMATION", str(self.ADX_TREND_DIRECTION_CONFIRMATION)).lower() in ['true', '1', 't']

        self.TIME_WINDOW_ENABLED = os.getenv("TIME_WINDOW_ENABLED", str(self.TIME_WINDOW_ENABLED)).lower() in ['true', '1', 't']
        self.TRADE_START_HOUR_UTC = int(os.getenv("TRADE_START_HOUR_UTC", self.TRADE_START_HOUR_UTC))
        self.TRADE_END_HOUR_UTC = int(os.getenv("TRADE_END_HOUR_UTC", self.TRADE_END_HOUR_UTC))
        trade_days_str = os.getenv("TRADE_DAYS_OF_WEEK")
        if trade_days_str:
            self.TRADE_DAYS_OF_WEEK = [d.strip() for d in trade_days_str.split(',')]

        self.MAX_CONCURRENT_POSITIONS = int(os.getenv("MAX_CONCURRENT_POSITIONS", self.MAX_CONCURRENT_POSITIONS))

        self.RETRACEMENT_ENTRY_ENABLED = os.getenv("RETRACEMENT_ENTRY_ENABLED", str(self.RETRACEMENT_ENTRY_ENABLED)).lower() in ['true', '1', 't']
        self.RETRACEMENT_PCT_FROM_CLOSE = float(os.getenv("RETRACEMENT_PCT_FROM_CLOSE", self.RETRACEMENT_PCT_FROM_CLOSE))
        self.RETRACEMENT_ORDER_TYPE = os.getenv("RETRACEMENT_ORDER_TYPE", self.RETRACEMENT_ORDER_TYPE)
        self.RETRACEMENT_CANDLE_WAIT = int(os.getenv("RETRACEMENT_CANDLE_WAIT", self.RETRACEMENT_CANDLE_WAIT))

        self.MULTI_TIMEFRAME_CONFIRMATION_ENABLED = os.getenv("MULTI_TIMEFRAME_CONFIRMATION_ENABLED", str(self.MULTI_TIMEFRAME_CONFIRMATION_ENABLED)).lower() in ['true', '1', 't']
        self.HIGHER_TIMEFRAME = os.getenv("HIGHER_TIMEFRAME", self.HIGHER_TIMEFRAME)
        self.HIGHER_TIMEFRAME_INDICATOR = os.getenv("HIGHER_TIMEFRAME_INDICATOR", self.HIGHER_TIMEFRAME_INDICATOR)
        self.REQUIRED_CONFLUENCE = os.getenv("REQUIRED_CONFLUENCE", str(self.REQUIRED_CONFLUENCE)).lower() in ['true', '1', 't']

        self.DYNAMIC_TRAILING_ENABLED = os.getenv("DYNAMIC_TRAILING_ENABLED", str(self.DYNAMIC_TRAILING_ENABLED)).lower() in ['true', '1', 't']
        trailing_profit_tiers_str = os.getenv("TRAILING_PROFIT_TIERS")
        if trailing_profit_tiers_str:
            try:
                self.TRAILING_PROFIT_TIERS = json.loads(trailing_profit_tiers_str)
            except json.JSONDecodeError:
                print(f"Warning: Could not decode TRAILING_PROFIT_TIERS from environment variable: {trailing_profit_tiers_str}. Using default.")

        self.SLIPPAGE_TOLERANCE_PCT = float(os.getenv("SLIPPAGE_TOLERANCE_PCT", self.SLIPPAGE_TOLERANCE_PCT))

        self.FUNDING_RATE_AVOIDANCE_ENABLED = os.getenv("FUNDING_RATE_AVOIDANCE_ENABLED", str(self.FUNDING_RATE_AVOIDANCE_ENABLED)).lower() in ['true', '1', 't']
        self.FUNDING_RATE_THRESHOLD_PCT = float(os.getenv("FUNDING_RATE_THRESHOLD_PCT", self.FUNDING_RATE_THRESHOLD_PCT))
        self.FUNDING_GRACE_PERIOD_MINUTES = int(os.getenv("FUNDING_GRACE_PERIOD_MINUTES", self.FUNDING_GRACE_PERIOD_MINUTES))

        self.NEWS_PAUSE_ENABLED = os.getenv("NEWS_PAUSE_ENABLED", str(self.NEWS_PAUSE_ENABLED)).lower() in ['true', '1', 't']
        self.NEWS_API_ENDPOINT = os.getenv("NEWS_API_ENDPOINT", self.NEWS_API_ENDPOINT)
        self.NEWS_API_KEY = os.getenv("NEWS_API_KEY", self.NEWS_API_KEY)
        impact_levels_str = os.getenv("IMPACT_LEVELS_TO_PAUSE")
        if impact_levels_str:
            self.IMPACT_LEVELS_TO_PAUSE = [lvl.strip() for lvl in impact_levels_str.split(',')]
        self.PAUSE_PRE_EVENT_MINUTES = int(os.getenv("PAUSE_PRE_EVENT_MINUTES", self.PAUSE_PRE_EVENT_MINUTES))
        self.PAUSE_POST_EVENT_MINUTES = int(os.getenv("PAUSE_POST_EVENT_MINUTES", self.PAUSE_POST_EVENT_MINUTES))

        self.ADAPTIVE_INDICATORS_ENABLED = os.getenv("ADAPTIVE_INDICATORS_ENABLED", str(self.ADAPTIVE_INDICATORS_ENABLED)).lower() in ['true', '1', 't']
        self.VOLATILITY_MEASURE_WINDOW = int(os.getenv("VOLATILITY_MEASURE_WINDOW", self.VOLATILITY_MEASURE_WINDOW))
        self.VOLATILITY_THRESHOLD_HIGH = float(os.getenv("VOLATILITY_THRESHOLD_HIGH", self.VOLATILITY_THRESHOLD_HIGH))
        self.VOLATILITY_THRESHOLD_LOW = float(os.getenv("VOLATILITY_THRESHOLD_LOW", self.VOLATILITY_THRESHOLD_LOW))
        self.EHLERS_LENGTH_HIGH_VOL = int(os.getenv("EHLERS_LENGTH_HIGH_VOL", self.EHLERS_LENGTH_HIGH_VOL))
        self.EHLERS_LENGTH_LOW_VOL = int(os.getenv("EHLERS_LENGTH_LOW_VOL", self.EHLERS_LENGTH_LOW_VOL))
        self.RSI_WINDOW_HIGH_VOL = int(os.getenv("RSI_WINDOW_HIGH_VOL", self.RSI_WINDOW_HIGH_VOL))
        self.RSI_WINDOW_LOW_VOL = int(os.getenv("RSI_WINDOW_LOW_VOL", self.RSI_WINDOW_LOW_VOL))

        self.PRICE_ACTION_CONFIRMATION_ENABLED = os.getenv("PRICE_ACTION_CONFIRMATION_ENABLED", str(self.PRICE_ACTION_CONFIRMATION_ENABLED)).lower() in ['true', '1', 't']
        bullish_patterns_str = os.getenv("REQUIRED_BULLISH_PATTERNS")
        if bullish_patterns_str:
            self.REQUIRED_BULLISH_PATTERNS = [p.strip() for p in bullish_patterns_str.split(',')]
        bearish_patterns_str = os.getenv("REQUIRED_BEARISH_PATTERNS")
        if bearish_patterns_str:
            self.REQUIRED_BEARISH_PATTERNS = [p.strip() for p in bearish_patterns_str.split(',')]
        self.PATTERN_STRENGTH_MULTIPLIER = float(os.getenv("PATTERN_STRENGTH_MULTIPLIER", self.PATTERN_STRENGTH_MULTIPLIER))

        # Snippet 1: Signal Strength Scoring
        self.MIN_SIGNAL_STRENGTH = int(os.getenv("MIN_SIGNAL_STRENGTH", self.MIN_SIGNAL_STRENGTH))

        # Snippet 2: Dynamic Take Profit with ATR Quality Check
        self.MIN_ATR_TP_THRESHOLD_PCT = float(os.getenv("MIN_ATR_TP_THRESHOLD_PCT", self.MIN_ATR_TP_THRESHOLD_PCT))

        # Snippet 3: VWAP as Additional Entry Confirmation
        self.VWAP_CONFIRMATION_ENABLED = os.getenv("VWAP_CONFIRMATION_ENABLED", str(self.VWAP_CONFIRMATION_ENABLED)).lower() in ['true', '1', 't']
        self.VWAP_WINDOW = int(os.getenv("VWAP_WINDOW", self.VWAP_WINDOW))

        # Snippet 4: Trailing Stop based on Ehlers Supertrend Line
        self.EHLERS_ST_TRAILING_ENABLED = os.getenv("EHLERS_ST_TRAILING_ENABLED", str(self.EHLERS_ST_TRAILING_ENABLED)).lower() in ['true', '1', 't']
        self.EHLERS_ST_TRAILING_OFFSET_PCT = float(os.getenv("EHLERS_ST_TRAILING_OFFSET_PCT", self.EHLERS_ST_TRAILING_OFFSET_PCT))

        # Snippet 5: Volatility-Adjusted Position Sizing Robustness
        self.MIN_ATR_FOR_SIZING_PCT = float(os.getenv("MIN_ATR_FOR_SIZING_PCT", self.MIN_ATR_FOR_SIZING_PCT))

        # Snippet 6: Time-Based Exit for Unprofitable Trades
        self.TIME_BASED_EXIT_ENABLED = os.getenv("TIME_BASED_EXIT_ENABLED", str(self.TIME_BASED_EXIT_ENABLED)).lower() in ['true', '1', 't']
        self.UNPROFITABLE_TRADE_MAX_BARS = int(os.getenv("UNPROFITABLE_TRADE_MAX_BARS", self.UNPROFITABLE_TRADE_MAX_BARS))

        # Snippet 7: Session-Based Volatility Filter
        self.SESSION_FILTER_ENABLED = os.getenv("SESSION_FILTER_ENABLED", str(self.SESSION_FILTER_ENABLED)).lower() in ['true', '1', 't']
        self.SESSION_START_HOUR_UTC = int(os.getenv("SESSION_START_HOUR_UTC", self.SESSION_START_HOUR_UTC))
        self.SESSION_END_HOUR_UTC = int(os.getenv("SESSION_END_HOUR_UTC", self.SESSION_END_HOUR_UTC))
        self.SESSION_MIN_VOLATILITY_FACTOR = float(os.getenv("SESSION_MIN_VOLATILITY_FACTOR", self.SESSION_MIN_VOLATILITY_FACTOR))

        # Snippet 8: Dynamic Signal Cooldown based on Volatility
        self.DYNAMIC_COOLDOWN_ENABLED = os.getenv("DYNAMIC_COOLDOWN_ENABLED", str(self.DYNAMIC_COOLDOWN_ENABLED)).lower() in ['true', '1', 't']
        self.COOLDOWN_VOLATILITY_FACTOR_HIGH = float(os.getenv("COOLDOWN_VOLATILITY_FACTOR_HIGH", self.COOLDOWN_VOLATILITY_FACTOR_HIGH))
        self.COOLDOWN_VOLATILITY_FACTOR_LOW = float(os.getenv("COOLDOWN_VOLATILITY_FACTOR_LOW", self.COOLDOWN_VOLATILITY_FACTOR_LOW))

        # Snippet 9: Order Book Depth Check for Limit Orders
        self.ORDER_BOOK_DEPTH_CHECK_ENABLED = os.getenv("ORDER_BOOK_DEPTH_CHECK_ENABLED", str(self.ORDER_BOOK_DEPTH_CHECK_ENABLED)).lower() in ['true', '1', 't']
        self.MIN_LIQUIDITY_DEPTH_USD = float(os.getenv("MIN_LIQUIDITY_DEPTH_USD", self.MIN_LIQUIDITY_DEPTH_USD))

        # Snippet 10: Multi-Tier Breakeven Stop Loss
        self.MULTI_TIER_BREAKEVEN_ENABLED = os.getenv("MULTI_TIER_BREAKEVEN_ENABLED", str(self.MULTI_TIER_BREAKEVEN_ENABLED)).lower() in ['true', '1', 't']
        multi_tier_breakeven_str = os.getenv("BREAKEVEN_PROFIT_TIERS")
        if multi_tier_breakeven_str:
            try:
                self.BREAKEVEN_PROFIT_TIERS = json.loads(multi_tier_breakeven_str)
            except json.JSONDecodeError:
                print(f"Warning: Could not decode BREAKEVEN_PROFIT_TIERS from environment variable: {multi_tier_breakeven_str}. Using default.")


        # Validate Category
        try:
            self.CATEGORY_ENUM = Category.from_string(self.CATEGORY)
        except ValueError as e:
            print(f"Configuration Error: {e}")
            sys.exit(1)

        # Validate Order Type
        try:
            self.ORDER_TYPE_ENUM = OrderType[self.ORDER_TYPE.upper()]
        except KeyError:
            print(f"Configuration Error: Invalid ORDER_TYPE '{self.ORDER_TYPE}'. Choose from {[ot.name for ot in OrderType]}")
            sys.exit(1)

        # Validate API Keys
        if self.API_KEY == "YOUR_BYBIT_API_KEY" or self.API_SECRET == "YOUR_BYBIT_API_SECRET" or not self.API_KEY or not self.API_SECRET:
            print("\nERROR: Bybit API Key or Secret not configured.")
            print("Please set BYBIT_API_KEY and BYBIT_API_SECRET environment variables,")
            print("or update the corresponding .env file or default values in the Config class.")
            sys.exit(1)

        # Validate positionIdx for hedge mode
        if self.HEDGE_MODE and self.POSITION_IDX not in [0, 1, 2]:
            print(f"Configuration Error: Invalid POSITION_IDX '{self.POSITION_IDX}'. Must be 0, 1, or 2.")
            sys.exit(1)

        # Force leverage to 1 for spot trading to avoid potential API errors or incorrect settings
        if self.CATEGORY_ENUM == Category.SPOT:
            self.LEVERAGE = 1

        # Validate MAX_DAILY_LOSS_PCT is positive
        if self.MAX_DAILY_LOSS_PCT <= 0:
            print(f"Configuration Error: MAX_DAILY_LOSS_PCT must be a positive value, but got {self.MAX_DAILY_LOSS_PCT}.")
            sys.exit(1)


# =====================================================================
# INSTRUMENT SPECS DATACLASS
# =====================================================================
@dataclass
class InstrumentSpecs:
    """Store instrument specifications from Bybit"""
    symbol: str
    category: str
    base_currency: str
    quote_currency: str
    status: str

    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal  # Price precision

    min_order_qty: Decimal
    max_order_qty: Decimal
    qty_step: Decimal  # Quantity precision

    min_leverage: Decimal
    max_leverage: Decimal
    leverage_step: Decimal

    max_position_value: Decimal # Max quantity in quote currency (e.g., USD for USDT pairs)
    min_position_value: Decimal # Min quantity in quote currency

    contract_value: Decimal = Decimal('1')  # For derivatives, typically the value of one contract
    is_inverse: bool = False

    maker_fee: Decimal = Decimal('0.0001')
    taker_fee: Decimal = Decimal('0.0006')


# =====================================================================
# PRECISION MANAGEMENT
# =====================================================================

class PrecisionManager:
    """Manage decimal precision for different trading pairs"""

    def __init__(self, bybit_session: HTTP, logger: logging.Logger):
        self.session = bybit_session
        self.logger = logger
        self.instruments: dict[str, InstrumentSpecs] = {}
        self.load_all_instruments()

    def load_all_instruments(self):
        """Load all instrument specifications from Bybit"""
        categories_to_check = [cat.value for cat in Category]
        self.logger.info(f"Loading instrument specifications for categories: {categories_to_check}")

        for category in categories_to_check:
            try:
                response = self.session.get_instruments_info(category=category)

                if response and response.get('retCode') == 0:
                    instruments_data = response['result'].get('list', [])
                    if not instruments_data:
                        self.logger.warning(f"No instruments found for category: {category}")
                        continue

                    for inst in instruments_data:
                        symbol = inst.get('symbol')
                        if not symbol:
                            self.logger.warning(f"Skipping instrument with no symbol in category {category}: {inst}")
                            continue

                        try:
                            specs = self._parse_instrument_specs(inst, category)
                            self.instruments[symbol.upper()] = specs
                            self.logger.debug(f"Loaded specs for {symbol} ({category})")
                        except Exception as parse_e:
                            self.logger.error(f"Error parsing specs for {symbol} ({category}): {parse_e}")

                else:
                    error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                    self.logger.error(f"Error loading {category} instruments: {error_msg}")

            except Exception as e:
                self.logger.error(f"Exception during loading of {category} instruments: {e}", exc_info=True)
        self.logger.info(f"Finished loading instrument specifications. {len(self.instruments)} symbols loaded.")

    def _parse_instrument_specs(self, inst: dict, category: str) -> InstrumentSpecs:
        """Parse instrument specifications based on category and Bybit's API structure."""
        symbol = inst['symbol']

        lot_size_filter = inst.get('lotSizeFilter', {})
        price_filter = inst.get('priceFilter', {})
        leverage_filter = inst.get('leverageFilter', {})
        unified_lot_size_filter = inst.get('unifiedLotSizeFilter', {}) # For potential unified account specifics

        def safe_decimal(value: Any, default: str = '0') -> Decimal:
            """Safely convert value to Decimal, returning default on error."""
            try:
                if value is None:
                    return Decimal(default)
                return Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                return Decimal(default)

        tick_size = safe_decimal(price_filter.get('tickSize', '0.00000001')) # Default to high precision if missing
        min_price = safe_decimal(price_filter.get('minPrice', '0'))
        max_price = safe_decimal(price_filter.get('maxPrice', '1e9')) # Default to a large number

        # Use unifiedLotSizeFilter for qtyStep if available, otherwise lotSizeFilter
        qty_step = safe_decimal(unified_lot_size_filter.get('qtyStep', lot_size_filter.get('qtyStep', '0.00000001')))
        min_order_qty = safe_decimal(unified_lot_size_filter.get('minOrderQty', lot_size_filter.get('minOrderQty', '0')))
        max_order_qty = safe_decimal(unified_lot_size_filter.get('maxOrderQty', '1e9'))

        # Max/Min Order Amount for position value limits (in quote currency, e.g., USD for USDT pairs)
        max_position_value_usd = safe_decimal(unified_lot_size_filter.get('maxOrderAmt', '1e9'))
        min_position_value_usd = safe_decimal(unified_lot_size_filter.get('minOrderAmt', '1')) # minOrderQty is for base units, minOrderAmt for quote.

        min_leverage = safe_decimal(leverage_filter.get('minLeverage', '1'))
        max_leverage = safe_decimal(leverage_filter.get('maxLeverage', '100')) # Default max leverage
        leverage_step = safe_decimal(leverage_filter.get('leverageStep', '0.1'))

        contract_value = safe_decimal(inst.get('contractValue', '1')) # e.g., 1 for BTCUSDT perpetual

        maker_fee = safe_decimal(inst.get('makerFeeRate', '0.0001'))
        taker_fee = safe_decimal(inst.get('takerFeeRate', '0.0006'))

        return InstrumentSpecs(
            symbol=symbol,
            category=category,
            base_currency=inst.get('baseCoin', ''),
            quote_currency=inst.get('quoteCoin', ''),
            status=inst.get('status', 'Unknown'),
            min_price=min_price,
            max_price=max_price,
            tick_size=tick_size,
            min_order_qty=min_order_qty,
            max_order_qty=max_order_qty,
            qty_step=qty_step,
            min_leverage=min_leverage,
            max_leverage=max_leverage,
            leverage_step=leverage_step,
            max_position_value=max_position_value_usd, # Use calculated max position value
            min_position_value=min_position_value_usd, # Use calculated min position value
            contract_value=contract_value,
            is_inverse=(category == 'inverse'),
            maker_fee=maker_fee,
            taker_fee=taker_fee
        )

    def get_specs(self, symbol: str) -> InstrumentSpecs | None:
        """Get instrument specs for a symbol"""
        return self.instruments.get(symbol.upper())

    def _round_decimal(self, value: Decimal, step: Decimal) -> Decimal:
        """Helper to round a Decimal to the nearest step, rounding down."""
        if step == Decimal('0'):
            return value
        try:
            # Calculate the number of steps. Use floor division for consistent rounding down.
            num_steps = (value / step).quantize(Decimal('1'), rounding=ROUND_DOWN)
            rounded_value = num_steps * step
            # Ensure the number of decimal places for the final value matches the step's precision
            # Only if the step itself has decimal places
            if step.as_tuple().exponent < 0:
                rounded_value = rounded_value.quantize(Decimal(f'1e{abs(step.as_tuple().exponent)}'), rounding=ROUND_DOWN)
            return rounded_value
        except Exception as e:
            self.logger.error(f"Error rounding decimal value {value} with step {step}: {e}", exc_info=True)
            return value # Return original value if rounding fails

    def round_price(self, symbol: str, price: float | Decimal) -> Decimal:
        """Round price to correct tick size, ensuring it's within min/max price bounds."""
        specs = self.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot round price for {symbol}: Specs not found. Returning 0.")
            return Decimal('0') # Return 0 or raise error if specs are critical
        price_decimal = Decimal(str(price))
        tick_size = specs.tick_size
        rounded = self._round_decimal(price_decimal, tick_size)
        # Clamp to min/max price
        rounded = max(specs.min_price, min(rounded, specs.max_price))
        self.logger.debug(f"Rounding price {price_decimal} for {symbol} with tick {tick_size} -> {rounded} (Min: {specs.min_price}, Max: {specs.max_price})")
        return rounded

    def round_quantity(self, symbol: str, quantity: float | Decimal) -> Decimal:
        """Round quantity to correct step size, ensuring it's within min/max quantity bounds."""
        specs = self.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot round quantity for {symbol}: Specs not found. Returning 0.")
            return Decimal('0') # Return 0 or raise error if specs are critical
        qty_decimal = Decimal(str(quantity))
        qty_step = specs.qty_step
        rounded = self._round_decimal(qty_decimal, qty_step)
        # Clamp to min/max quantity
        rounded = max(specs.min_order_qty, min(rounded, specs.max_order_qty))
        self.logger.debug(f"Rounding quantity {qty_decimal} for {symbol} with step {qty_step} -> {rounded} (Min: {specs.min_order_qty}, Max: {specs.max_order_qty})")
        return rounded

    def get_decimal_places(self, symbol: str) -> tuple[int, int]:
        """Get decimal places for price and quantity based on tick_size and qty_step."""
        specs = self.get_specs(symbol)
        if not specs:
            self.logger.warning(f"Specs not found for {symbol}, returning default decimal places (2, 3).")
            return 2, 3  # Default values if specs are missing

        try:
            # Exponent of tick_size gives negative number of decimal places, e.g., -2 for 0.01
            price_decimals = abs(specs.tick_size.as_tuple().exponent) if specs.tick_size.as_tuple().exponent < 0 else 0
            qty_decimals = abs(specs.qty_step.as_tuple().exponent) if specs.qty_step.as_tuple().exponent < 0 else 0
            return price_decimals, qty_decimals
        except Exception as e:
            self.logger.error(f"Error calculating decimal places for {symbol}: {e}", exc_info=True)
            return 2, 3 # Fallback


# =====================================================================
# ORDER SIZING CALCULATOR
# =====================================================================

class OrderSizingCalculator:
    """Calculate optimal order sizes based on risk management and instrument specifications."""

    def __init__(self, precision_manager: PrecisionManager, logger: logging.Logger, config: Config):
        self.precision = precision_manager
        self.logger = logger
        self.config = config # Added config for volatility adjusted sizing

    def calculate_position_size_usd(
        self,
        symbol: str,
        account_balance_usdt: Decimal,
        risk_percent: Decimal,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        leverage: Decimal,
        current_atr: Decimal | None = None
    ) -> Decimal | None:
        """
        Calculate position size in base currency units based on fixed risk percentage, leverage,
        entry price, and stop loss price. Returns None if calculation is not possible.
        """
        specs = self.precision.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot calculate position size for {symbol}: Symbol specifications not found.")
            return None

        # --- Input Validation ---
        if account_balance_usdt <= Decimal('0'):
            self.logger.warning(f"Account balance is zero or negative ({account_balance_usdt}). Cannot calculate position size.")
            return None
        if entry_price <= Decimal('0'):
            self.logger.warning(f"Entry price is zero or negative ({entry_price}). Cannot calculate position size.")
            return None
        if leverage <= Decimal('0'):
            self.logger.warning(f"Leverage is zero or negative ({leverage}). Cannot calculate position size.")
            return None

        stop_distance_price = abs(entry_price - stop_loss_price)
        if stop_distance_price <= Decimal('0'):
            self.logger.warning(f"Stop loss distance is zero or negative ({stop_distance_price}). Cannot calculate position size.")
            return None

        # --- Calculations ---
        position_value_usd_unadjusted: Decimal

        # FEATURE: Volatility-Adjusted Position Sizing with robustness (Snippet 5)
        if self.config.VOLATILITY_ADJUSTED_SIZING_ENABLED and current_atr is not None and current_atr > Decimal('0'):
            # Check if ATR is too small, which could lead to excessively large positions
            if entry_price > Decimal('0') and (current_atr / entry_price) < Decimal(str(self.config.MIN_ATR_FOR_SIZING_PCT)):
                self.logger.warning(f"Current ATR ({current_atr:.4f}) is too low relative to price for volatility-adjusted sizing (below {self.config.MIN_ATR_FOR_SIZING_PCT*100:.2f}%). Falling back to fixed risk percentage: {self.config.MAX_RISK_PER_TRADE_BALANCE_PCT*100:.2f}%.")
                risk_amount_usdt = account_balance_usdt * Decimal(str(self.config.MAX_RISK_PER_TRADE_BALANCE_PCT))
                stop_distance_pct = abs(entry_price - stop_loss_price) / entry_price
                if stop_distance_pct > Decimal('0'):
                    position_value_usd_unadjusted = risk_amount_usdt / stop_distance_pct
                else:
                    self.logger.warning("Stop distance percentage is zero. Cannot calculate required position value.")
                    return None
            else:
                self.logger.debug(f"Using Volatility-Adjusted Sizing with ATR: {current_atr:.4f}")
                risk_amount_usdt = account_balance_usdt * Decimal(str(self.config.MAX_RISK_PER_TRADE_BALANCE_PCT))
                stop_distance_price = abs(entry_price - stop_loss_price)
                if stop_distance_price <= Decimal('0'): # Re-check if stop_distance_price became zero after any adjustments
                    self.logger.warning("Stop loss distance is zero or negative after adjustments. Cannot calculate position size.")
                    return None
                position_value_usd_unadjusted = risk_amount_usdt / (stop_distance_price / entry_price)

        else: # Original logic or if volatility-adjusted sizing is disabled
            # Calculate risk amount in USDT
            risk_amount_usdt = account_balance_usdt * risk_percent
            # Calculate stop loss distance in percentage terms
            stop_distance_pct = stop_distance_price / entry_price
            if stop_distance_pct > Decimal('0'):
                position_value_usd_unadjusted = risk_amount_usdt / stop_distance_pct
            else:
                self.logger.warning("Stop distance percentage is zero. Cannot calculate required position value.")
                return None

        # Apply leverage to determine the maximum tradeable position value based on account balance
        max_tradeable_value_usd = account_balance_usdt * leverage

        # Cap the needed position value by maximum tradeable value and Bybit's max position value limits
        position_value_usd = min(
            position_value_usd_unadjusted,
            max_tradeable_value_usd,
            specs.max_position_value # Apply Bybit's specific max order value if available
        )

        # FEATURE: Max Position Size USD from config
        position_value_usd = min(position_value_usd, Decimal(str(self.config.MAX_POSITION_SIZE_USD)))


        # Ensure minimum position value is met
        if position_value_usd < specs.min_position_value:
            self.logger.warning(f"Calculated position value ({position_value_usd:.{self.precision.get_decimal_places(symbol)[0]}f} USD) is below minimum ({specs.min_position_value:.{self.precision.get_decimal_places(symbol)[0]}f} USD). Using minimum.")
            position_value_usd = specs.min_position_value

        # FEATURE: Min Position Size USD from config
        if position_value_usd < Decimal(str(self.config.MIN_POSITION_SIZE_USD)):
            self.logger.warning(f"Calculated position value ({position_value_usd:.{self.precision.get_decimal_places(symbol)[0]}f} USD) is below configured MIN_POSITION_SIZE_USD ({self.config.MIN_POSITION_SIZE_USD:.{self.precision.get_decimal_places(symbol)[0]}f} USD). Using configured minimum.")
            position_value_usd = Decimal(str(self.config.MIN_POSITION_SIZE_USD))


        # Convert position value to quantity in base currency units (category-specific)
        # For linear and spot: Value (Quote) = Quantity (Base) * Price (Quote/Base)
        quantity_base = position_value_usd / entry_price

        # Round the quantity to the nearest valid step
        calculated_quantity = self.precision.round_quantity(symbol, quantity_base)

        # Final check on calculated quantity against min/max order quantity
        if calculated_quantity < specs.min_order_qty:
            self.logger.warning(f"Calculated quantity ({calculated_quantity} {specs.base_currency}) is below minimum order quantity ({specs.min_order_qty}). Setting to minimum.")
            final_quantity = specs.min_order_qty
        elif calculated_quantity > specs.max_order_qty:
            self.logger.warning(f"Calculated quantity ({calculated_quantity} {specs.base_currency}) exceeds maximum order quantity ({specs.max_order_qty}). Setting to maximum.")
            final_quantity = specs.max_order_qty
        else:
            final_quantity = calculated_quantity

        # Ensure final quantity is positive
        if final_quantity <= Decimal('0'):
            self.logger.warning(f"Calculated final quantity is zero or negative ({final_quantity}). Cannot proceed with order.")
            return None

        # Recalculate actual risk based on final quantity and compare against allowed risk
        actual_position_value_usd = final_quantity * entry_price
        actual_risk_amount_usdt = actual_position_value_usd * stop_distance_pct
        actual_risk_percent = (actual_risk_amount_usdt / account_balance_usdt) * Decimal('100') if account_balance_usdt > Decimal('0') else Decimal('0')

        self.logger.debug(f"Order Sizing for {symbol}: Entry={entry_price}, SL={stop_loss_price}, Risk%={risk_percent:.4f}, Balance={account_balance_usdt:.4f} USDT")
        self.logger.debug(f"  Calculated Qty={quantity_base:.8f} {specs.base_currency}, Rounded Qty={final_quantity:.8f}")
        self.logger.debug(f"  Position Value={position_value_usd:.4f} USD, Actual Risk={actual_risk_amount_usdt:.4f} USDT ({actual_risk_percent:.4f}%)")

        # Optional: Check if actual risk exceeds the allowed risk percentage
        if actual_risk_percent > risk_percent * Decimal('1.01'): # Allow for slight rounding discrepancies
            self.logger.warning(f"Calculated risk ({actual_risk_percent:.4f}%) slightly exceeds allowed risk ({risk_percent:.4f}%). Review parameters.")

        return final_quantity


# =====================================================================
# TRAILING STOP MANAGER
# =====================================================================

class TrailingStopManager:
    """
    Manage trailing stop losses by setting Bybit's native trailing stop (`callbackRate`)
    or by dynamically updating a fixed stop loss based on indicators.
    """
    def __init__(self, bybit_session: HTTP, precision_manager: PrecisionManager, logger: logging.Logger, api_call_wrapper: Any, config: Config):
        self.session = bybit_session
        self.precision = precision_manager
        self.logger = logger
        self.api_call = api_call_wrapper # Reference to the bot's api_call method
        self.config = config # Added config for dynamic trailing
        # Stores active trailing stop info: {symbol: {'side': 'Buy'/'Sell', 'trail_percent': Decimal, 'ehlers_st_trailing': bool, 'current_sl': Decimal}}
        self.active_trailing_stops: dict[str, dict] = {}
        # Store current PnL for dynamic trailing stop logic
        self.current_unrealized_pnl_pct: dict[str, Decimal] = {}

    def initialize_trailing_stop(
        self,
        symbol: str,
        position_side: str,
        entry_price: Decimal,
        current_price: Decimal,
        trail_percent: float, # Pass as percentage (e.g., 0.5 for 0.5%)
        activation_percent: float, # Not directly used by Bybit's callbackRate, but kept for consistency
        ehlers_st_trailing_enabled: bool = False, # New parameter for Snippet 4
        ehlers_st_line_value: Decimal | None = None # New parameter for Snippet 4
    ) -> bool:
        """
        Initialize trailing stop for a position using Bybit's callbackRate or
        set an initial fixed SL if Ehlers ST trailing is enabled.
        Returns True if successful, False otherwise.
        """
        specs = self.precision.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot initialize trailing stop for {symbol}: Specs not found.")
            return False

        if specs.category == 'spot':
            self.logger.debug(f"Trailing stops are not applicable for spot category {symbol}. Skipping initialization.")
            return False

        if ehlers_st_trailing_enabled and ehlers_st_line_value is not None:
            # For Ehlers ST trailing, we set a fixed SL first, then update it.
            # Bybit's callbackRate is not suitable for dynamic indicator trailing without manual updates.
            # We will set the initial SL based on the Ehlers ST line.
            stop_loss_price = Decimal('0')
            offset_value = ehlers_st_line_value * Decimal(str(self.config.EHLERS_ST_TRAILING_OFFSET_PCT))

            if position_side == 'Buy':
                stop_loss_price = ehlers_st_line_value - offset_value
            else: # Sell
                stop_loss_price = ehlers_st_line_value + offset_value
            
            stop_loss_price = self.precision.round_price(symbol, stop_loss_price)

            self.logger.info(f"Setting initial Ehlers ST trailing SL for {symbol} ({position_side}) at: ${stop_loss_price:.{self.precision.get_decimal_places(symbol)[0]}f}")
            try:
                response = self.api_call(
                    self.session.set_trading_stop,
                    category=specs.category,
                    symbol=symbol,
                    side=position_side,
                    stopLoss=str(stop_loss_price),
                    tpslMode='Full' # Setting SL will override callbackRate if already present
                )
                if response is not None:
                    self.active_trailing_stops[symbol] = {
                        'side': position_side,
                        'trail_percent': Decimal('0'), # Not using callbackRate in this mode
                        'ehlers_st_trailing': True,
                        'current_sl': stop_loss_price # Store current SL
                    }
                    self.logger.info(f"Successfully set initial Ehlers ST trailing SL for {symbol} at ${stop_loss_price:.{self.precision.get_decimal_places(symbol)[0]}f}.")
                    return True
                else:
                    self.logger.error(f"Failed to set initial Ehlers ST trailing SL for {symbol}: API call wrapper returned None.")
                    return False
            except Exception as e:
                self.logger.error(f"Exception setting initial Ehlers ST trailing SL for {symbol}: {e}", exc_info=True)
                return False
        else:
            # Original logic for Bybit's callbackRate
            trail_rate_str = str(trail_percent)

            try:
                response = self.api_call(
                    self.session.set_trading_stop,
                    category=specs.category,
                    symbol=symbol,
                    side=position_side, # Required for unified account
                    callbackRate=trail_rate_str
                )

                if response is not None:
                    self.active_trailing_stops[symbol] = {
                        'side': position_side,
                        'trail_percent': Decimal(str(trail_percent)),
                        'ehlers_st_trailing': False,
                        'current_sl': Decimal('0') # Not applicable for callbackRate
                    }
                    self.logger.info(f"Successfully set trailing stop for {symbol} ({position_side}) with callbackRate: {trail_rate_str}%")
                    return True
                else:
                    self.logger.error(f"Failed to set trailing stop for {symbol}: API call wrapper returned None.")
                    return False

            except Exception as e:
                self.logger.error(f"Exception setting trailing stop for {symbol}: {e}", exc_info=True)
                return False

    def update_trailing_stop(
        self,
        symbol: str,
        current_price: Decimal,
        current_unrealized_pnl_pct: Decimal,
        ehlers_st_line_value: Decimal | None = None, # New parameter for Snippet 4
        update_exchange: bool = True
    ) -> bool:
        """
        Re-confirms or re-sets the trailing stop on the exchange if `update_exchange` is True.
        For Bybit's native `callbackRate`, this usually means ensuring it's still active.
        If Ehlers ST trailing is enabled, it updates the fixed stop loss.
        """
        if symbol not in self.active_trailing_stops:
            return False # No active trailing stop to update

        self.current_unrealized_pnl_pct[symbol] = current_unrealized_pnl_pct

        if not update_exchange:
            self.logger.debug(f"Internal trailing stop check for {symbol}: current price {current_price}.")
            return False # No exchange update requested

        ts_info = self.active_trailing_stops[symbol]
        specs = self.precision.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot update trailing stop for {symbol}: Specs not found.")
            return False

        if ts_info.get('ehlers_st_trailing', False) and ehlers_st_line_value is not None:
            # Ehlers Supertrend Trailing Logic (Snippet 4)
            stop_loss_price = Decimal('0')
            offset_value = ehlers_st_line_value * Decimal(str(self.config.EHLERS_ST_TRAILING_OFFSET_PCT))

            if ts_info['side'] == 'Buy':
                # For a long position, SL should be below price and below ST line
                stop_loss_price = ehlers_st_line_value - offset_value
                # Ensure SL never moves down once in profit (optional, but good practice)
                if ts_info['current_sl'] > stop_loss_price: # If current SL is higher (worse for Buy), don't move it down
                    stop_loss_price = ts_info['current_sl']
            else: # Sell
                # For a short position, SL should be above price and above ST line
                stop_loss_price = ehlers_st_line_value + offset_value
                # Ensure SL never moves up once in profit
                if ts_info['current_sl'] < stop_loss_price: # If current SL is lower (worse for Sell), don't move it up
                    stop_loss_price = ts_info['current_sl']
            
            stop_loss_price = self.precision.round_price(symbol, stop_loss_price)

            # Only update if the calculated SL is better (tighter) than the current one
            current_exchange_sl = self.active_trailing_stops[symbol].get('current_sl', Decimal('0'))

            should_update = False
            if ts_info['side'] == 'Buy' and stop_loss_price > current_exchange_sl: # SL should move up
                should_update = True
            elif ts_info['side'] == 'Sell' and stop_loss_price < current_exchange_sl: # SL should move down
                should_update = True
            elif current_exchange_sl == Decimal('0'): # No SL currently set, or first update
                should_update = True

            if should_update:
                try:
                    self.logger.info(f"Updating Ehlers ST trailing SL for {symbol} ({ts_info['side']}) from ${current_exchange_sl:.{self.precision.get_decimal_places(symbol)[0]}f} to ${stop_loss_price:.{self.precision.get_decimal_places(symbol)[0]}f}.")
                    response = self.api_call(
                        self.session.set_trading_stop,
                        category=specs.category,
                        symbol=symbol,
                        side=ts_info['side'],
                        stopLoss=str(stop_loss_price),
                        tpslMode='Partial' # Allow other TP to remain
                    )
                    if response is not None:
                        self.active_trailing_stops[symbol]['current_sl'] = stop_loss_price
                        return True
                    else:
                        self.logger.error(f"Failed to update Ehlers ST trailing SL for {symbol}: API call wrapper returned None.")
                        return False
                except Exception as e:
                    self.logger.error(f"Exception updating Ehlers ST trailing SL for {symbol}: {e}", exc_info=True)
                    return False
            else:
                self.logger.debug(f"Ehlers ST trailing SL for {symbol} not improved. Current: ${current_exchange_sl:.{self.precision.get_decimal_places(symbol)[0]}f}, Calculated: ${stop_loss_price:.{self.precision.get_decimal_places(symbol)[0]}f}.")
                return True # Considered successful if no update needed
        else:
            # Original logic for Bybit's callbackRate and Dynamic Trailing (Existing Feature)
            effective_trail_pct = Decimal(str(self.config.TRAILING_STOP_PCT)) * Decimal('100') # Default from config

            if self.config.DYNAMIC_TRAILING_ENABLED:
                sorted_tiers = sorted(self.config.TRAILING_PROFIT_TIERS, key=lambda x: x['profit_pct_trigger'], reverse=True)
                for tier in sorted_tiers:
                    if current_unrealized_pnl_pct >= Decimal(str(tier['profit_pct_trigger'])) * Decimal('100'):
                        effective_trail_pct = Decimal(str(tier['new_trail_pct'])) * Decimal('100')
                        self.logger.debug(f"Dynamic Trailing: PnL {current_unrealized_pnl_pct:.2f}% reached tier {tier['profit_pct_trigger']*100:.2f}%. New trail: {effective_trail_pct:.2f}%")
                        break

            current_ts_info = self.active_trailing_stops.get(symbol)
            if current_ts_info and effective_trail_pct == current_ts_info['trail_percent']:
                self.logger.debug(f"Trailing stop for {symbol} already at desired effective rate ({effective_trail_pct:.2f}%). No update needed.")
                return True

            ts_info['trail_percent'] = effective_trail_pct
            return self.initialize_trailing_stop(
                symbol=symbol,
                position_side=ts_info['side'],
                entry_price=Decimal('0'),
                current_price=current_price,
                trail_percent=float(effective_trail_pct),
                activation_percent=float(effective_trail_pct),
                ehlers_st_trailing_enabled=False # Explicitly false for callbackRate mode
            )

    def remove_trailing_stop(self, symbol: str):
        """
        Remove trailing stop for a symbol. This typically involves setting Stop Loss
        or Take Profit to 0 or simply clearing the callbackRate on Bybit.
        Bybit's API might not have a direct "remove trailing stop" call if it's
        tied to set_trading_stop. Clearing internal state is the primary action here.
        """
        if symbol in self.active_trailing_stops:
            del self.active_trailing_stops[symbol]
            self.logger.info(f"Removed internal trailing stop data for {symbol}")
            # To actually remove it on Bybit, you might need to call set_trading_stop
            # with callbackRate="" or set a fixed SL/TP which overrides the trailing stop.
            # For simplicity, we assume setting a new SL/TP or closing position clears it.


# =====================================================================
# TERMUX SMS NOTIFIER
# =====================================================================

class TermuxSMSNotifier:
    """
    A digital carrier pigeon to send urgent messages via Termux SMS,
    alerting the wizard directly on their Android device.
    """
    def __init__(self, recipient_number: str | None, logger: logging.Logger, price_precision: int):
        self.recipient_number = recipient_number
        self.logger = logger
        self.price_precision = price_precision

        if not self.recipient_number:
            self.logger.warning(Fore.YELLOW + "TERMUX_SMS_RECIPIENT_NUMBER not set. SMS notifications will be disabled." + Style.RESET_ALL)
            self.is_enabled = False
        else:
            self.logger.info(Fore.CYAN + f"Termux SMS Notifier initialized for {self.recipient_number}." + Style.RESET_ALL)
            self.is_enabled = True

    def send_sms(self, message: str):
        """Send message via Termux SMS."""
        if not self.is_enabled:
            return

        try:
            subprocess.run(["termux-sms-send", "-n", self.recipient_number, message], check=True, capture_output=True)
            self.logger.info(Fore.GREEN + f"SMS sent to {self.recipient_number}: {message[:50]}..." + Style.RESET_ALL)
        except FileNotFoundError:
            self.logger.error(Fore.RED + "Termux command 'termux-sms-send' not found. Is 'pkg install termux-api' installed?" + Style.RESET_ALL)
        except subprocess.CalledProcessError as e:
            self.logger.error(Fore.RED + f"Termux SMS command failed with error: {e.stderr.decode()}" + Style.RESET_ALL)
        except Exception as e:
            self.logger.error(Fore.RED + f"Failed to send Termux SMS: {e}" + Style.RESET_ALL)

    def send_trade_alert(self, side: str, symbol: str, price: float, sl: float, tp: float, reason: str):
        emoji = "🟢" if side == "Buy" else "🔴"
        message = f"{emoji} {side} {symbol}\nEntry: ${price:.{self.price_precision}f}\nSL: ${sl:.{self.price_precision}f}\nTP: ${tp:.{self.price_precision}f}\nReason: {reason}\nTime: {datetime.now().strftime('%H:%M:%S')}"
        self.send_sms(message)

    def send_pnl_update(self, pnl: float, balance: float):
        emoji = "✅" if pnl > 0 else "❌"
        message = f"{emoji} Position Closed\nP&L: ${pnl:.2f}\nBalance: ${balance:.2f}\nTime: {datetime.now().strftime('%H:%M:%S')}"
        self.send_sms(message)


# =====================================================================
# BYBIT CLIENT WRAPPER (for raw API calls)
# =====================================================================

class BybitClient:
    """
    A conduit to the Bybit ether, allowing direct communion with its V5 API endpoints.
    This client wraps the pybit library, ensuring all calls are harmonized and returning
    raw responses for the bot's api_call to interpret.
    """
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True, default_category: str = 'linear'):
        # The session object is our enchanted connection to the exchange's soul.
        self.session = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret)
        self._default_category = default_category

    def get_server_time(self) -> dict[str, Any]:
        """Fetches server time to synchronize our chronomancy."""
        return self.session.get_server_time()

    def get_instruments_info(self, symbol: str | None = None, category: str | None = None) -> dict[str, Any]:
        """Lists active trading symbols and deciphers their fundamental laws."""
        params = {'category': category or self._default_category}
        if symbol:
            params['symbol'] = symbol
        return self.session.get_instruments_info(**params)

    def get_wallet_balance(self, accountType: str = 'UNIFIED', coin: str | None = None) -> dict[str, Any]:
        """
        Summons the knowledge of the user's wallet balance from the Bybit V5 API.
        This spell relies on the pybit library's own powerful incantation.
        """
        params = {'accountType': accountType}
        if coin:
            params['coin'] = coin
        return self.session.get_wallet_balance(**params)

    def get_kline(self, symbol: str, interval: str, limit: int = 200, category: str | None = None) -> dict[str, Any]:
        """Fetches the echoes of past market movements (historical klines)."""
        return self.session.get_kline(category=category or self._default_category, symbol=symbol, interval=interval, limit=limit)

    def get_positions(self, symbol: str | None = None, category: str | None = None) -> dict[str, Any]:
        """Takes stock of all active positions, revealing their current state."""
        params = {'category': category or self._default_category}
        if symbol:
            params['symbol'] = symbol
        return self.session.get_positions(**params)

    def place_order(self, symbol: str, side: str, orderType: str, qty: str,
                    price: str | None = None, stopLoss: str | None = None,
                    takeProfit: str | None = None, reduceOnly: bool = False,
                    category: str | None = None, timeInForce: str = "GTC",
                    closeOnTrigger: bool = False, positionIdx: int = 0,
                    slOrderType: str | None = None, tpOrderType: str | None = None,
                    tpslMode: str | None = None) -> dict[str, Any]:
        """Casts a new thread into the market's loom (places an order)."""
        params = {
            'category': category or self._default_category,
            'symbol': symbol,
            'side': side,
            'orderType': orderType,
            'qty': qty,
            'timeInForce': timeInForce,
            'reduceOnly': reduceOnly,
            'closeOnTrigger': closeOnTrigger,
            'positionIdx': positionIdx
        }
        if price is not None:
            params['price'] = price
        if stopLoss is not None:
            params['stopLoss'] = stopLoss
            if slOrderType:
                params['slOrderType'] = slOrderType
        if takeProfit is not None:
            params['takeProfit'] = takeProfit
            if tpOrderType:
                params['tpOrderType'] = tpOrderType
        if tpslMode is not None:
            params['tpslMode'] = tpslMode

        return self.session.place_order(**params)

    def set_trading_stop(self, symbol: str, side: str, callbackRate: str | None = None,
                         stopLoss: str | None = None, takeProfit: str | None = None,
                         category: str | None = None, slOrderType: str | None = None,
                         tpOrderType: str | None = None, tpslMode: str | None = None) -> dict[str, Any]:
        """Manages protective wards (TP/SL/Trailing Stops)."""
        params = {
            'category': category or self._default_category,
            'symbol': symbol,
            'side': side # Side is required for set_trading_stop on unified account
        }
        if callbackRate is not None:
            params['callbackRate'] = callbackRate
        if stopLoss is not None:
            params['stopLoss'] = stopLoss
            if slOrderType:
                params['slOrderType'] = slOrderType
        if takeProfit is not None:
            params['takeProfit'] = takeProfit
            if tpOrderType:
                params['tpOrderType'] = tpOrderType
        if tpslMode is not None:
            params['tpslMode'] = tpslMode
        return self.session.set_trading_stop(**params)

    def get_order_history(self, symbol: str, orderId: str | None = None, limit: int = 50,
                          category: str | None = None) -> dict[str, Any]:
        """Fetches the chronicles of past orders."""
        params = {'category': category or self._default_category, 'symbol': symbol, 'limit': limit}
        if orderId:
            params['orderId'] = orderId
        return self.session.get_order_history(**params)

    def get_open_orders(self, symbol: str | None = None, orderId: str | None = None, limit: int = 50,
                        category: str | None = None) -> dict[str, Any]:
        """Reveals orders that currently lie in wait."""
        params = {'category': category or self._default_category, 'limit': limit}
        if symbol:
            params['symbol'] = symbol
        if orderId:
            params['orderId'] = orderId
        return self.session.get_open_orders(**params)

    def cancel_order(self, category: str, symbol: str, orderId: str) -> dict[str, Any]:
        """Unweaves a specific thread from the market's loom (cancels an order)."""
        return self.session.cancel_order(category=category, symbol=symbol, orderId=orderId)

    def cancel_all_orders(self, category: str, symbol: str) -> dict[str, Any]:
        """Unweaves all open threads for a symbol."""
        return self.session.cancel_all_orders(category=category, symbol=symbol)

    def switch_margin_mode(self, category: str, symbol: str, tradeMode: str) -> dict[str, Any]:
        """Alters the margin mode for a symbol's contract."""
        return self.session.switch_margin_mode(category=category, symbol=symbol, tradeMode=tradeMode)

    def set_leverage(self, category: str, symbol: str, buyLeverage: str, sellLeverage: str) -> dict[str, Any]:
        """Adjusts the leverage, the very amplification of one's market power."""
        return self.session.set_leverage(category=category, symbol=symbol, buyLeverage=buyLeverage, sellLeverage=sellLeverage)

    def get_tickers(self, category: str, symbol: str) -> dict[str, Any]:
        """Fetches the current pulse of the market (ticker information)."""
        return self.session.get_tickers(category=category, symbol=symbol)

    def get_funding_rate(self, symbol: str, category: str | None = None) -> dict[str, Any]:
        """Fetches funding rate information for a perpetual contract."""
        # Note: Bybit V5 get_tickers already includes fundingRate and nextFundingTime
        # This wrapper can directly call get_tickers and extract the info.
        return self.session.get_tickers(category=category or self._default_category, symbol=symbol)
    
    def get_orderbook(self, category: str, symbol: str, limit: int = 1) -> dict[str, Any]:
        """Fetches order book data."""
        return self.session.get_orderbook(category=category, symbol=symbol, limit=limit)


# =====================================================================
# LOGGING SETUP
# =====================================================================
# Bybit V5 API Configuration
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
BASE_URL = 'https://api.bybit.com' if os.getenv("BYBIT_TESTNET", "true").lower() != "true" else 'https://api-testnet.bybit.com'

# --- Structured JSON Logging alongside Color Console ---
class SimpleJSONFormatter(logging.Formatter):
    """
    A scribe to record the bot's saga in machine-readable JSON format,
    for deeper analysis in the digital archives.
    """
    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "message": record.getMessage()
        }
        return json.dumps(payload, ensure_ascii=False)

def setup_logger(config: Config) -> logging.Logger:
    """
    Forging the logger to chronicle the bot's journey,
    with vibrant console hues and a steadfast log file (both plain and JSON).
    """
    logger = logging.getLogger("EhlersSuperTrendBot")
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler) # Remove existing handlers to prevent duplicate logs

    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Neon-colored console handler, a beacon in the digital night
    console_handler = colorlog.StreamHandler()
    console_format = "%(log_color)s%(asctime)s | %(levelname)-8s | %(message)s%(reset)s"
    console_formatter = colorlog.ColoredFormatter(
        console_format, datefmt="%H:%M:%S",
        log_colors={
            'DEBUG':    'bold_cyan',    'INFO':     'bold_green',
            'WARNING':  'bold_yellow',  'ERROR':    'bold_red',
            'CRITICAL': 'bold_purple',
        }
    )
    console_handler.setFormatter(console_formatter)

    # Plain text file handler, a historical scroll of the bot's deeds
    file_handler = logging.FileHandler(config.LOG_FILE, mode='a') # Append to the log file
    file_format = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)

    # JSON file handler, for structured machine-readable logs
    json_file_handler = logging.FileHandler(config.JSON_LOG_FILE, mode='a', encoding='utf-8')
    json_file_handler.setFormatter(SimpleJSONFormatter(datefmt='%Y-%m-%d %H:%M:%S'))

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(json_file_handler) # Add the JSON handler
    return logger

# Create a logger instance at module level (before Config/Bot init)
# This logger will be reconfigured by EhlersSuperTrendBot.__init__
logger = logging.getLogger("EhlersSuperTrendBot")


# =====================================================================
# BotState: Shared state for UI and bot logic
# =====================================================================
@dataclass
class BotState:
    """
    A shared scroll containing the bot's current market perception and state,
    ensuring that all modules, especially the UI, can read consistent data.
    """
    lock: threading.Lock = field(default_factory=threading.Lock) # Guards against simultaneous writes from different threads

    current_price: Decimal = field(default=Decimal('0.0'))
    bid_price: Decimal = field(default=Decimal('0.0'))
    ask_price: Decimal = field(default=Decimal('0.0'))

    ehlers_supertrend_value: Decimal = field(default=Decimal('0.0')) # The actual ST line value
    ehlers_supertrend_direction: str = field(default="NONE") # e.g., "UP", "DOWN"
    ehlers_filter_value: Decimal = field(default=Decimal('0.0')) # From Ehlers Adaptive Trend custom filter

    adx_value: Decimal = field(default=Decimal('0.0'))
    adx_plus_di: Decimal = field(default=Decimal('0.0'))
    adx_minus_di: Decimal = field(default=Decimal('0.0'))
    adx_trend_strength: str = field(default="N/A") # e.g., "Weak", "Developing", "Strong"

    rsi_value: Decimal = field(default=Decimal('0.0'))
    rsi_state: str = field(default="N/A") # e.g., "Overbought", "Oversold", "Neutral"

    macd_value: Decimal = field(default=Decimal('0.0'))
    macd_signal_value: Decimal = field(default=Decimal('0.0'))
    macd_diff_value: Decimal = field(default=Decimal('0.0'))

    initial_equity: Decimal = field(default=Decimal('0.0'))
    current_equity: Decimal = field(default=Decimal('0.0'))
    open_position_qty: Decimal = field(default=Decimal('0.0'))
    open_position_side: str = field(default="NONE") # "Buy" or "Sell"
    open_position_entry_price: Decimal = field(default=Decimal('0.0'))
    unrealized_pnl: Decimal = field(default=Decimal('0.0'))
    unrealized_pnl_pct: Decimal = field(default=Decimal('0.0'))
    realized_pnl_total: Decimal = field(default=Decimal('0.0')) # Cumulative PnL from closed trades

    last_updated_time: datetime = field(default_factory=datetime.now)
    bot_status: str = field(default="Initializing")
    symbol: str = field(default="")
    timeframe: str = field(default="")
    price_precision: int = field(default=3)
    qty_precision: int = field(default=1)
    dry_run: bool = field(default=False)
    testnet: bool = field(default=True) # Added testnet status for UI

    # New fields for Adaptive Indicators
    adaptive_ehlers_length: int = field(default=0)
    adaptive_rsi_window: int = field(default=0)


# =====================================================================
# BotUI: Renders the console UI
# =====================================================================
class BotUI(threading.Thread):
    """
    A visual spell to display the bot's current state and market insights
    directly in the terminal, updating continuously without disturbing the bot's operations.
    """
    def __init__(self, bot_state: BotState, update_interval=1):
        super().__init__()
        self.daemon = True # Allows the UI thread to exit when main program exits
        self.bot_state = bot_state
        self.update_interval = update_interval # How often the UI refreshes (in seconds)
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            self._render_ui()
            self._stop_event.wait(self.update_interval) # Use wait for graceful stop

    def stop(self):
        """Signals the UI thread to stop."""
        self._stop_event.set()

    def _clear_screen(self):
        """Clears the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')

    def _render_ui(self):
        """Renders the entire UI to the console."""
        self._clear_screen()

        with self.bot_state.lock:
            # Create a local copy of the state for consistent display during rendering
            state = self.bot_state

            # Formatting and Coloring Logic
            pnl_color_realized = Fore.GREEN if state.realized_pnl_total >= Decimal('0') else Fore.RED
            pnl_color_unrealized = Fore.GREEN if state.unrealized_pnl >= Decimal('0') else Fore.RED

            adx_color = Fore.WHITE
            if state.adx_trend_strength == "Strong":
                adx_color = Fore.LIGHTGREEN_EX
            elif state.adx_trend_strength == "Developing":
                adx_color = Fore.LIGHTYELLOW_EX
            elif state.adx_trend_strength == "Weak":
                adx_color = Fore.LIGHTBLACK_EX

            rsi_color = Fore.WHITE
            if state.rsi_state == "Overbought":
                rsi_color = Fore.RED
            elif state.rsi_state == "Oversold":
                rsi_color = Fore.GREEN

            ehlers_color = Fore.WHITE
            if state.ehlers_supertrend_direction == "UP":
                ehlers_color = Fore.LIGHTGREEN_EX
            elif state.ehlers_supertrend_direction == "DOWN":
                ehlers_color = Fore.LIGHTRED_EX

            # --- UI Layout ---
            # Main Header
            print(f"{Fore.CYAN}╔═══════════════════════════════════════════════════════════════════════════╗{Style.RESET_ALL}")
            dry_run_str = " [DRY RUN]" if state.dry_run else ""
            header_title = f"{state.symbol} Ehlers SuperTrend Bot{dry_run_str}"
            # Center header_title in 75 characters wide box, adjusted for borders
            print(f"{Fore.CYAN}║ {Fore.WHITE}{header_title:<73}{Fore.CYAN} ║{Style.RESET_ALL}")
            print(f"{Fore.CYAN}╠═══════════════════════════════════════════════════════════════════════════╣{Style.RESET_ALL}")
            status_text_display = f"Status: {Fore.GREEN}{state.bot_status} ({'TESTNET' if state.testnet else 'MAINNET'}){Fore.CYAN}"
            last_update_text = f"Last Updated: {state.last_updated_time.strftime('%H:%M:%S')}"
            # Calculate padding dynamically
            # Remove color codes for length calculation
            status_len_no_color = len(state.bot_status) + len(f" ({'TESTNET' if state.testnet else 'MAINNET'})")
            padding_len = 73 - (len("Status: ") + status_len_no_color + len(last_update_text) + len("Last Updated: "))

            print(f"{Fore.CYAN}║ {status_text_display}{' ' * padding_len}{last_update_text} {Fore.CYAN}║{Style.RESET_ALL}")
            print(f"{Fore.CYAN}╚═══════════════════════════════════════════════════════════════════════════╝{Style.RESET_ALL}\n")

            # Market Data Section
            print(f"{Fore.BLUE}╔═══════════════════════════════════════════════════════════════════════════╗{Style.RESET_ALL}")
            print(f"{Fore.BLUE}║ MARKET DATA                                                               {Fore.BLUE}║{Style.RESET_ALL}")
            print(f"{Fore.BLUE}╠═══════════════════════════════════════════════════════════════════════════╣{Style.RESET_ALL}")

            # Current Price string, 3 decimals
            print(f"{Fore.BLUE}║ Current Price:          {Fore.YELLOW}${state.current_price:.{state.price_precision}f}{Fore.BLUE:<46}║{Style.RESET_ALL}")

            # Bid Price string, 3 decimals
            print(f"{Fore.BLUE}║ Bid:                    {Fore.YELLOW}${state.bid_price:.{state.price_precision}f}{Fore.BLUE:<46}║{Style.RESET_ALL}")

            # Ask Price string, 3 decimals
            print(f"{Fore.BLUE}║ Ask:                    {Fore.YELLOW}${state.ask_price:.{state.price_precision}f}{Fore.BLUE:<46}║{Style.RESET_ALL}")
            print(f"{Fore.BLUE}╚═══════════════════════════════════════════════════════════════════════════╝{Style.RESET_ALL}\n")

            # Indicator Values Section
            print(f"{Fore.MAGENTA}╔═══════════════════════════════════════════════════════════════════════════╗{Style.RESET_ALL}")
            print(f"{Fore.MAGENTA}║ INDICATOR VALUES                                                          {Fore.MAGENTA}║{Style.RESET_ALL}")
            print(f"{Fore.MAGENTA}╠═══════════════════════════════════════════════════════════════════════════╣{Style.RESET_ALL}")

            ehlers_st_val_str = f"${state.ehlers_supertrend_value:.{state.price_precision}f}"
            ehlers_st_display_str = f"{ehlers_st_val_str} ({state.ehlers_supertrend_direction})"
            print(f"{Fore.MAGENTA}║ Ehlers SuperTrend:      {ehlers_color}{ehlers_st_display_str}{Fore.MAGENTA:<{73 - len('Ehlers SuperTrend:      ') - len(ehlers_st_display_str) + len(ehlers_color) + len(Style.RESET_ALL)}}║{Style.RESET_ALL}")

            ehlers_filter_str = f"{state.ehlers_filter_value:.2f}"
            print(f"{Fore.MAGENTA}║ Ehlers Filter:          {Fore.WHITE}{ehlers_filter_str}{Fore.MAGENTA:<{73 - len('Ehlers Filter:          ') - len(ehlers_filter_str)}}║{Style.RESET_ALL}")

            adx_str = f"{state.adx_value:.1f} (Trend: {state.adx_trend_strength})"
            print(f"{Fore.MAGENTA}║ ADX:                    {adx_color}{adx_str}{Fore.MAGENTA:<{73 - len('ADX:                    ') - len(adx_str) + len(adx_color) + len(Style.RESET_ALL)}}║{Style.RESET_ALL}")

            rsi_str = f"{state.rsi_value:.1f} (State: {state.rsi_state})"
            print(f"{Fore.MAGENTA}║ RSI:                    {rsi_color}{rsi_str}{Fore.MAGENTA:<{73 - len('RSI:                    ') - len(rsi_str) + len(rsi_color) + len(Style.RESET_ALL)}}║{Style.RESET_ALL}")

            # MACD (3 decimals for all MACD components)
            print(f"{Fore.MAGENTA}║ MACD:                   {Fore.WHITE}{state.macd_value:.3f}{Fore.MAGENTA:<{73 - len('MACD:                   ') - len(f'{state.macd_value:.3f}')}}║{Style.RESET_ALL}")
            print(f"{Fore.MAGENTA}║ MACD Signal:            {Fore.WHITE}{state.macd_signal_value:.3f}{Fore.MAGENTA:<{73 - len('MACD Signal:            ') - len(f'{state.macd_signal_value:.3f}')}}║{Style.RESET_ALL}")
            print(f"{Fore.MAGENTA}║ MACD Diff:              {Fore.WHITE}{state.macd_diff_value:.3f}{Fore.MAGENTA:<{73 - len('MACD Diff:              ') - len(f'{state.macd_diff_value:.3f}')}}║{Style.RESET_ALL}")

            # Adaptive Indicator Parameters (if enabled)
            if state.adaptive_ehlers_length > 0:
                print(f"{Fore.MAGENTA}║ Adaptive Ehlers Len:    {Fore.WHITE}{state.adaptive_ehlers_length}{Fore.MAGENTA:<{73 - len('Adaptive Ehlers Len:    ') - len(str(state.adaptive_ehlers_length))}}║{Style.RESET_ALL}")
            if state.adaptive_rsi_window > 0:
                print(f"{Fore.MAGENTA}║ Adaptive RSI Window:    {Fore.WHITE}{state.adaptive_rsi_window}{Fore.MAGENTA:<{73 - len('Adaptive RSI Window:    ') - len(str(state.adaptive_rsi_window))}}║{Style.RESET_ALL}")

            print(f"{Fore.MAGENTA}╚═══════════════════════════════════════════════════════════════════════════╝{Style.RESET_ALL}\n")

            # Portfolio & PNL Section
            print(f"{Fore.GREEN}╔═══════════════════════════════════════════════════════════════════════════╗{Style.RESET_ALL}")
            print(f"{Fore.GREEN}║ PORTFOLIO & PNL                                                           {Fore.GREEN}║{Style.RESET_ALL}")
            print(f"{Fore.GREEN}╠═══════════════════════════════════════════════════════════════════════════╣{Style.RESET_ALL}")

            initial_equity_str = f"${state.initial_equity:.2f}"
            print(f"{Fore.GREEN}║ Initial Equity:         {Fore.WHITE}{initial_equity_str}{Fore.GREEN:<{73 - len('Initial Equity:         ') - len(initial_equity_str)}}║{Style.RESET_ALL}")

            current_equity_str = f"${state.current_equity:.2f}"
            equity_change_pct_val = Decimal('0.0')
            if state.initial_equity > Decimal('0') and state.current_equity > Decimal('0'):
                equity_change_pct_val = ((state.current_equity - state.initial_equity) / state.initial_equity) * Decimal('100')
            equity_color = Fore.GREEN if equity_change_pct_val >= Decimal('0') else Fore.RED
            equity_pct_str = f"{equity_change_pct_val:+.2f}%"
            current_equity_display_str = f"{current_equity_str} ({equity_pct_str})"
            print(f"{Fore.GREEN}║ Current Equity:         {equity_color}{current_equity_display_str}{Fore.GREEN:<{73 - len('Current Equity:         ') - len(current_equity_display_str) + len(equity_color) + len(Style.RESET_ALL)}}║{Style.RESET_ALL}")
            print(f"{Fore.GREEN}║                                                                           {Fore.GREEN}║{Style.RESET_ALL}")

            if state.open_position_qty > Decimal('0'):
                pos_info = f"{state.open_position_qty:.{state.qty_precision}f} {state.symbol} ({state.open_position_side})"
                entry_price_str = f"${state.open_position_entry_price:.{state.price_precision}f}"
                unrealized_pnl_str = f"${state.unrealized_pnl:.2f} ({state.unrealized_pnl_pct:+.2f}%)" # PNL to 2 decimals, PCT to 2 decimals

                print(f"{Fore.GREEN}║ Open Position:          {Fore.WHITE}{pos_info}{Fore.GREEN:<{73 - len('Open Position:          ') - len(pos_info)}}║{Style.RESET_ALL}")
                print(f"{Fore.GREEN}║ Avg Entry Price:        {Fore.WHITE}{entry_price_str}{Fore.GREEN:<{73 - len('Avg Entry Price:        ') - len(entry_price_str)}}║{Style.RESET_ALL}")
                print(f"{Fore.GREEN}║ Unrealized PNL:         {pnl_color_unrealized}{unrealized_pnl_str}{Fore.GREEN:<{73 - len('Unrealized PNL:         ') - len(unrealized_pnl_str) + len(pnl_color_unrealized) + len(Style.RESET_ALL)}}║{Style.RESET_ALL}")
                # SL/TP for open position are not stored in BotState.open_position_info.
                # If needed, they should be extracted from 'pos' dict in get_positions and passed to BotState.
                # For now, print placeholders.
                print(f"{Fore.GREEN}║ Stop Loss:              {Fore.WHITE}${Decimal('0.0'):.{state.price_precision}f} (N/A){Fore.GREEN:<{73 - len('Stop Loss:              ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")
                print(f"{Fore.GREEN}║ Take Profit:            {Fore.WHITE}${Decimal('0.0'):.{state.price_precision}f} (N/A){Fore.GREEN:<{73 - len('Take Profit:              ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")

            else:
                # Consistent padding for "no open position" state
                # Adjust formatting to use Decimal('0.0') for consistency and correct precision padding
                print(f"{Fore.GREEN}║ Open Position:          {Fore.WHITE}{Decimal('0.0').quantize(Decimal(f'1e-{state.qty_precision}'))} {state.symbol}{Fore.GREEN:<{73 - len('Open Position:          ') - len(str(Decimal('0.0').quantize(Decimal(f'1e-{state.qty_precision}'))) + ' ' + state.symbol)}}║{Style.RESET_ALL}")
                print(f"{Fore.GREEN}║ Avg Entry Price:        {Fore.WHITE}${Decimal('0.0').quantize(Decimal(f'1e-{state.price_precision}'))}{Fore.GREEN:<{73 - len('Avg Entry Price:        ') - len(str(Decimal('0.0').quantize(Decimal(f'1e-{state.price_precision}')))) - 1}}║{Style.RESET_ALL}")
                print(f"{Fore.GREEN}║ Unrealized PNL:         {Fore.WHITE}${Decimal('0.0'):.2f} ({Decimal('0.0'):+.2f}%){Fore.GREEN:<{73 - len('Unrealized PNL:         ') - len(f'${Decimal('0.0'):.2f} ({Decimal('0.0'):+.2f}%)')}}║{Style.RESET_ALL}")
                print(f"{Fore.GREEN}║ Stop Loss:              {Fore.WHITE}${Decimal('0.0').quantize(Decimal(f'1e-{state.price_precision}'))} (N/A){Fore.GREEN:<{73 - len('Stop Loss:              ') - len(str(Decimal('0.0').quantize(Decimal(f'1e-{state.price_precision}')))) - len(' (N/A)') -1}}║{Style.RESET_ALL}")
                print(f"{Fore.GREEN}║ Take Profit:            {Fore.WHITE}${Decimal('0.0').quantize(Decimal(f'1e-{state.price_precision}'))} (N/A){Fore.GREEN:<{73 - len('Take Profit:            ') - len(str(Decimal('0.0').quantize(Decimal(f'1e-{state.price_precision}')))) - len(' (N/A)') -1}}║{Style.RESET_ALL}")

            realized_pnl_str = f"${state.realized_pnl_total:.2f}" # Realized PNL to 2 decimals
            print(f"{Fore.GREEN}║                                                                           {Fore.GREEN}║{Style.RESET_ALL}")
            print(f"{Fore.GREEN}║ Realized PNL (Total):   {pnl_color_realized}{realized_pnl_str}{Fore.GREEN:<{73 - len('Realized PNL (Total):   ') - len(realized_pnl_str) + len(pnl_color_realized) + len(Style.RESET_ALL)}}║{Style.RESET_ALL}")
            print(f"{Fore.GREEN}╚═══════════════════════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
            print(Style.RESET_ALL) # Ensure all colors are reset at the end


# =====================================================================
# NEW HELPER CLASSES/FUNCTIONS FOR FEATURES
# =====================================================================

class NewsCalendarManager:
    """
    Manages fetching and checking high-impact news events to pause trading.
    Mocks API calls if no API key is provided.
    """
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.news_events: list[dict[str, Any]] = []
        self.last_fetch_time: datetime | None = None
        self.fetch_interval_hours = 6 # Fetch news every 6 hours

        if not self.config.NEWS_PAUSE_ENABLED:
            self.logger.info("News Event Trading Pause is disabled.")
            return

        if self.config.NEWS_API_ENDPOINT and self.config.NEWS_API_KEY:
            self.logger.info(f"News Calendar Manager initialized with API: {self.config.NEWS_API_ENDPOINT}")
        else:
            self.logger.warning("News API endpoint or key not configured. News events will be mocked.")

    def _fetch_news_from_api(self):
        """Fetches news events from the configured API."""
        if not self.config.NEWS_API_ENDPOINT or not self.config.NEWS_API_KEY:
            self._mock_news_events()
            return

        try:
            # Example for Finnhub economic calendar (adjust for other APIs)
            # This is a basic example; real integration might need more complex parsing
            today = datetime.now(dateutil.tz.UTC)
            start_date = today - timedelta(days=1)
            end_date = today + timedelta(days=7) # Look 7 days ahead

            params = {
                'from': start_date.strftime('%Y-%m-%d'),
                'to': end_date.strftime('%Y-%m-%d'),
                'token': self.config.NEWS_API_KEY
            }
            response = requests.get(self.config.NEWS_API_ENDPOINT, params=params, timeout=10)
            response.raise_for_status() # Raise an exception for bad status codes
            data = response.json()

            events = []
            for event in data.get('economicCalendar', []): # Adjust key based on API response
                if event.get('impact') in self.config.IMPACT_LEVELS_TO_PAUSE:
                    event_time_utc = parse_to_utc(event['time']) # Assuming 'time' is parsable
                    if event_time_utc:
                        events.append({
                            'event': event.get('event'),
                            'time_utc': event_time_utc,
                            'impact': event.get('impact')
                        })
            self.news_events = events
            self.last_fetch_time = datetime.now(dateutil.tz.UTC)
            self.logger.info(f"Fetched {len(self.news_events)} high-impact news events.")

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to fetch news from API: {e}")
            self._mock_news_events() # Fallback to mock if API fails
        except Exception as e:
            self.logger.error(f"Error processing news API response: {e}")
            self._mock_news_events()

    def _mock_news_events(self):
        """Generates mock news events for testing without an API."""
        self.logger.warning("Using MOCKED news events due to missing API config or fetch failure.")
        now = datetime.now(dateutil.tz.UTC)
        mock_events = [
            {'event': 'Mock CPI Release', 'time_utc': now + timedelta(minutes=30), 'impact': 'High'},
            {'event': 'Mock FOMC Meeting', 'time_utc': now + timedelta(hours=2, minutes=45), 'impact': 'High'},
            {'event': 'Mock GDP Report', 'time_utc': now + timedelta(days=1, hours=10), 'impact': 'High'},
        ]
        # Filter for only high impact levels configured
        self.news_events = [e for e in mock_events if e['impact'] in self.config.IMPACT_LEVELS_TO_PAUSE]
        self.last_fetch_time = now
        self.logger.info(f"Generated {len(self.news_events)} mock high-impact news events.")

    def is_trading_paused(self) -> tuple[bool, str]:
        """
        Checks if trading should be paused due to an upcoming or recent news event.
        Returns (bool, reason_string).
        """
        if not self.config.NEWS_PAUSE_ENABLED:
            return False, "News pause disabled."

        now_utc = datetime.now(dateutil.tz.UTC)

        # Refresh news events periodically
        if self.last_fetch_time is None or (now_utc - self.last_fetch_time).total_seconds() > self.fetch_interval_hours * 3600:
            self.logger.info("Refreshing news events...")
            self._fetch_news_from_api()

        for event in self.news_events:
            event_time = event['time_utc']
            pause_start = event_time - timedelta(minutes=self.config.PAUSE_PRE_EVENT_MINUTES)
            pause_end = event_time + timedelta(minutes=self.config.PAUSE_POST_EVENT_MINUTES)

            if pause_start <= now_utc <= pause_end:
                reason = f"Trading paused for news event '{event['event']}' (Impact: {event['impact']}) at {event_time.strftime('%H:%M UTC')}. Pause ends {pause_end.strftime('%H:%M UTC')}."
                self.logger.info(Fore.YELLOW + reason + Style.RESET_ALL)
                return True, reason

        return False, "No high-impact news events requiring pause."

class CandlestickPatternDetector:
    """
    Detects common candlestick patterns for trade confirmation.
    Simplified implementation for demonstration.
    """
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def _is_bullish_engulfing(self, df: pd.DataFrame) -> bool:
        """Detects a bullish engulfing pattern."""
        if len(df) < 2:
            return False

        c2, c1 = df.iloc[-2], df.iloc[-1] # Previous, Latest

        # Previous candle must be bearish, latest must be bullish
        prev_is_bearish = c2['close'] < c2['open']
        curr_is_bullish = c1['close'] > c1['open']

        if not (prev_is_bearish and curr_is_bullish):
            return False

        # Current candle body must engulf previous candle body
        engulfs_low = c1['open'] < c2['close']
        engulfs_high = c1['close'] > c2['open']

        return engulfs_low and engulfs_high

    def _is_bearish_engulfing(self, df: pd.DataFrame) -> bool:
        """Detects a bearish engulfing pattern."""
        if len(df) < 2:
            return False

        c2, c1 = df.iloc[-2], df.iloc[-1] # Previous, Latest

        # Previous candle must be bullish, latest must be bearish
        prev_is_bullish = c2['close'] > c2['open']
        curr_is_bearish = c1['close'] < c1['open']

        if not (prev_is_bullish and curr_is_bearish):
            return False

        # Current candle body must engulf previous candle body
        engulfs_low = c1['close'] < c2['open']
        engulfs_high = c1['open'] > c2['close']

        return engulfs_low and engulfs_high

    def _is_hammer(self, df: pd.DataFrame) -> bool:
        """Detects a hammer pattern."""
        if len(df) < 1:
            return False
        c1 = df.iloc[-1]

        body_size = abs(c1['close'] - c1['open'])
        lower_shadow = min(c1['open'], c1['close']) - c1['low']
        upper_shadow = c1['high'] - max(c1['open'], c1['close'])

        # Hammer criteria: small body, long lower shadow (at least 2x body), little/no upper shadow
        return body_size > 0 and lower_shadow >= 2 * body_size and upper_shadow < body_size / 2

    def _is_shooting_star(self, df: pd.DataFrame) -> bool:
        """Detects a shooting star pattern."""
        if len(df) < 1:
            return False
        c1 = df.iloc[-1]

        body_size = abs(c1['close'] - c1['open'])
        lower_shadow = min(c1['open'], c1['close']) - c1['low']
        upper_shadow = c1['high'] - max(c1['open'], c1['close'])

        # Shooting Star criteria: small body, long upper shadow (at least 2x body), little/no lower shadow
        return body_size > 0 and upper_shadow >= 2 * body_size and lower_shadow < body_size / 2

    def detect_pattern(self, df: pd.DataFrame, patterns: list[str]) -> str | None:
        """
        Detects if any of the specified patterns are present in the latest candle(s).
        Returns the name of the detected pattern or None.
        """
        if df.empty or len(df) < 2: # Need at least 2 candles for most patterns for context
            return None

        # Ensure 'open', 'high', 'low', 'close' are present
        if not all(col in df.columns for col in ['open', 'high', 'low', 'close']):
            self.logger.warning("Candlestick pattern detection requires 'open', 'high', 'low', 'close' columns.")
            return None

        # Map pattern names to detection methods
        pattern_map = {
            "ENGULFING": self._is_bullish_engulfing, # Differentiated by context later
            "BEARISH_ENGULFING": self._is_bearish_engulfing,
            "HAMMER": self._is_hammer,
            "SHOOTING_STAR": self._is_shooting_star,
        }

        for pattern_name in patterns:
            method = pattern_map.get(pattern_name.upper())
            if method:
                if method(df):
                    self.logger.debug(f"Detected candlestick pattern: {pattern_name}")
                    return pattern_name
            else:
                self.logger.warning(f"Unsupported candlestick pattern requested: {pattern_name}")
        return None

# =====================================================================
# MAIN TRADING BOT CLASS
# =====================================================================

class EhlersSuperTrendBot:
    def __init__(self, config: Config):
        self.config = config

        # --- Logger Setup ---
        global logger # Use the global logger instance
        logger = setup_logger(config) # Reconfigure it with the bot's config
        self.logger = logger
        self.logger.info("Initializing Ehlers SuperTrend Trading Bot...")

        # --- BotState Initialization (for UI) ---
        self.bot_state = BotState()

        # --- API Session Initialization (using BybitClient) ---
        self.bybit_client = BybitClient(
            api_key=self.config.API_KEY,
            api_secret=self.config.API_SECRET,
            testnet=self.config.TESTNET,
            default_category=self.config.CATEGORY_ENUM.value
        )
        self.ws: WebSocket | None = None # WebSocket instance
        self.stop_event = threading.Event() # Event to signal threads to stop

        # --- Managers Initialization ---
        self.precision_manager = PrecisionManager(self.bybit_client.session, self.logger)
        self.order_sizer = OrderSizingCalculator(self.precision_manager, self.logger, self.config) # Pass config
        # TrailingStopManager needs the bot's api_call wrapper
        self.trailing_stop_manager = TrailingStopManager(self.bybit_client.session, self.precision_manager, self.logger, self.api_call, self.config) # Pass config
        self.news_calendar_manager = NewsCalendarManager(self.config, self.logger) # New: News Calendar Manager
        self.candlestick_detector = CandlestickPatternDetector(self.logger) # New: Candlestick Pattern Detector

        # --- Termux SMS Notifier ---
        # Get initial precision for SMS notifier
        price_prec, _ = self.precision_manager.get_decimal_places(self.config.SYMBOL)
        self.sms_notifier = TermuxSMSNotifier(
            recipient_number=self.config.TERMUX_SMS_RECIPIENT_NUMBER,
            logger=self.logger,
            price_precision=price_prec
        )

        # --- Data Storage ---
        self.market_data: pd.DataFrame = pd.DataFrame() # Stores historical klines with indicators
        self.higher_timeframe_data: pd.DataFrame = pd.DataFrame() # New: for Multi-Timeframe Confluence Filter
        self.all_open_positions: dict[str, dict] = {} # {symbol: position_data} - New: for Max Concurrent Positions
        self.open_orders: dict[str, dict] = {} # {order_id: order_data}
        self.account_balance_usdt: Decimal = Decimal('0.0')
        self.initial_equity: Decimal = Decimal('0.0')

        # --- Strategy State ---
        self.position_active: bool = False # Whether there's an active position for self.config.SYMBOL
        self.current_position_side: str | None = None # 'Buy' or 'Sell' for self.config.SYMBOL
        self.current_position_entry_price: Decimal = Decimal('0') # For self.config.SYMBOL
        self.current_position_size: Decimal = Decimal('0') # For self.config.SYMBOL
        self.last_signal: str | None = None # Stores the last signal acted upon
        self.last_kline_ts: int = 0 # Unix timestamp of the last processed confirmed candle
        self.last_trade_time: float = 0.0 # For trade cooldown
        self.cumulative_pnl: Decimal = Decimal('0.0') # Total realized PnL from closed trades

        # New: State for Breakeven Stop Loss
        self.breakeven_activated: dict[str, bool] = {} # {symbol: True/False}

        # Snippet 10: Multi-Tier Breakeven Stop Loss
        self.breakeven_tier_activated: dict[str, int] = {} # {symbol: highest_tier_index_activated} (Snippet 10)

        # New: State for Partial Take Profit
        # {symbol: {target_idx: True}} indicates which partial TP targets have been hit for the current position
        self.partial_tp_targets_hit: dict[str, dict[int, bool]] = {}
        self.initial_position_qty: Decimal = Decimal('0.0') # Store initial quantity for partial TP

        # New: State for Signal Retracement Entry
        self.pending_retracement_order: dict[str, Any] | None = None # {'orderId': ..., 'side': ..., 'qty': ..., 'price': ..., 'time_placed_kline_ts': ...}

        # Snippet 6: Time-Based Exit for Unprofitable Trades
        self.open_trade_kline_ts: int = 0 # Unix timestamp of the kline when the current trade was opened (Snippet 6)

        # New: State for Adaptive Indicators
        self.current_ehlers_length = self.config.EHLERS_LENGTH
        self.current_rsi_window = self.config.RSI_WINDOW


        # --- Update BotState with initial config ---
        with self.bot_state.lock:
            self.bot_state.symbol = self.config.SYMBOL
            self.bot_state.timeframe = self.config.TIMEFRAME
            self.bot_state.dry_run = self.config.DRY_RUN
            self.bot_state.testnet = self.config.TESTNET
            self.bot_state.bot_status = "Initialized"
            self.bot_state.price_precision, self.bot_state.qty_precision = self.precision_manager.get_decimal_places(self.config.SYMBOL)

        # --- Initializations & Validations ---
        self._validate_api_credentials() # Test API connection and keys
        self._validate_symbol_timeframe() # Validate symbol and timeframe
        self._capture_initial_equity() # Capture initial equity for cumulative loss protection

        if self.config.CATEGORY_ENUM != Category.SPOT:
            self._configure_trading_parameters() # Set margin mode and leverage for derivatives
        else:
            self.logger.info("Leverage set to 1 for SPOT category as it's not applicable.")

        self.logger.info("Bot Configuration Loaded:")
        self.logger.info(f"  Mode: {'Testnet' if config.TESTNET else 'Mainnet'}")
        self.logger.info(f"  Dry Run: {config.DRY_RUN}")
        self.logger.info(f"  Symbol: {config.SYMBOL}, Category: {config.CATEGORY_ENUM.value}")
        self.logger.info(f"  Leverage: {config.LEVERAGE}x")
        self.logger.info(f"  Hedge Mode: {config.HEDGE_MODE}, PositionIdx: {config.POSITION_IDX}")
        self.logger.info(f"  Timeframe: {config.TIMEFRAME}, Lookback: {config.LOOKBACK_PERIODS} periods")
        self.logger.info(f"  Ehlers Adaptive Trend Params: Length={config.EHLERS_LENGTH}, Smoothing={config.SMOOTHING_LENGTH}, Sensitivity={config.SENSITIVITY}")
        self.logger.info(f"  Ehlers Supertrend Params: Length={config.EHLERS_ST_LENGTH}, Multiplier={config.EHLERS_ST_MULTIPLIER}")
        self.logger.info(f"  RSI Params: Window={config.RSI_WINDOW}")
        self.logger.info(f"  MACD Params: Fast={config.MACD_FAST}, Slow={config.MACD_SLOW}, Signal={config.MACD_SIGNAL}")
        self.logger.info(f"  ADX Params: Window={config.ADX_WINDOW}")
        self.logger.info(f"  Risk Params: Risk/Trade={config.RISK_PER_TRADE_PCT}%, SL={config.STOP_LOSS_PCT*100:.2f}%, TP={config.TAKE_PROFIT_PCT*100:.2f}%, Trail={config.TRAILING_STOP_PCT*100:.2f}%, Max Daily Loss={config.MAX_DAILY_LOSS_PCT*100:.2f}%")
        self.logger.info(f"  Execution: OrderType={config.ORDER_TYPE_ENUM.value}, TimeInForce={config.TIME_IN_FORCE}, ReduceOnly={config.REDUCE_ONLY}")
        self.logger.info(f"  Loop Interval: {config.LOOP_INTERVAL_SEC} seconds")
        self.logger.info(f"  API Retry: MaxRetries={config.MAX_API_RETRIES}, RetryDelay={config.API_RETRY_DELAY_SEC}s")
        self.logger.info(f"  Auto Close on Shutdown: {config.AUTO_CLOSE_ON_SHUTDOWN}")
        self.logger.info(f"  Signal Cooldown: {config.SIGNAL_COOLDOWN_SEC}s, Confirm Bars: {config.SIGNAL_CONFIRM_BARS}")
        # Log new feature configurations
        self.logger.info(f"  Dynamic TP Enabled: {config.DYNAMIC_TP_ENABLED}, ATR Window: {config.ATR_TP_WINDOW}, Multiplier: {config.ATR_TP_MULTIPLIER}, Min/Max TP: {config.MIN_TAKE_PROFIT_PCT*100:.2f}%/{config.MAX_TAKE_PROFIT_PCT*100:.2f}%")
        self.logger.info(f"  Breakeven Enabled: {config.BREAKEVEN_ENABLED}, Trigger: {config.BREAKEVEN_PROFIT_TRIGGER_PCT*100:.2f}%, Offset: {config.BREAKEVEN_OFFSET_PCT*100:.2f}%")
        self.logger.info(f"  Partial TP Enabled: {config.PARTIAL_TP_ENABLED}, Targets: {config.PARTIAL_TP_TARGETS}")
        self.logger.info(f"  Volatility Adjusted Sizing: {config.VOLATILITY_ADJUSTED_SIZING_ENABLED}, Window: {config.VOLATILITY_WINDOW}, Target Risk ATR Mult: {config.TARGET_RISK_ATR_MULTIPLIER}, Max Risk/Trade: {config.MAX_RISK_PER_TRADE_BALANCE_PCT*100:.2f}%")
        self.logger.info(f"  ADX Trend Filter: {config.ADX_TREND_FILTER_ENABLED}, Min Threshold: {config.ADX_MIN_THRESHOLD}, Direction Confirmation: {config.ADX_TREND_DIRECTION_CONFIRMATION}")
        self.logger.info(f"  Time Window Enabled: {config.TIME_WINDOW_ENABLED}, Hours: {config.TRADE_START_HOUR_UTC}-{config.TRADE_END_HOUR_UTC} UTC, Days: {', '.join(config.TRADE_DAYS_OF_WEEK)}")
        self.logger.info(f"  Max Concurrent Positions: {config.MAX_CONCURRENT_POSITIONS}")
        self.logger.info(f"  Retracement Entry: {config.RETRACEMENT_ENTRY_ENABLED}, PCT from Close: {config.RETRACEMENT_PCT_FROM_CLOSE*100:.2f}%, Order Type: {config.RETRACEMENT_ORDER_TYPE}, Candle Wait: {config.RETRACEMENT_CANDLE_WAIT}")
        self.logger.info(f"  Multi-Timeframe Confirmation: {config.MULTI_TIMEFRAME_CONFIRMATION_ENABLED}, Higher TF: {config.HIGHER_TIMEFRAME}, Indicator: {config.HIGHER_TIMEFRAME_INDICATOR}, Required Confluence: {config.REQUIRED_CONFLUENCE}")
        self.logger.info(f"  Dynamic Trailing Stop: {config.DYNAMIC_TRAILING_ENABLED}, Tiers: {config.TRAILING_PROFIT_TIERS}")
        self.logger.info(f"  Slippage Tolerance: {config.SLIPPAGE_TOLERANCE_PCT*100:.2f}%")
        self.logger.info(f"  Funding Rate Avoidance: {config.FUNDING_RATE_AVOIDANCE_ENABLED}, Threshold: {config.FUNDING_RATE_THRESHOLD_PCT*100:.2f}%, Grace Period: {config.FUNDING_GRACE_PERIOD_MINUTES}min")
        self.logger.info(f"  News Pause: {config.NEWS_PAUSE_ENABLED}, API: {config.NEWS_API_ENDPOINT}, Impact Levels: {', '.join(config.IMPACT_LEVELS_TO_PAUSE)}, Pre/Post Pause: {config.PAUSE_PRE_EVENT_MINUTES}/{config.PAUSE_POST_EVENT_MINUTES}min")
        self.logger.info(f"  Adaptive Indicators: {config.ADAPTIVE_INDICATORS_ENABLED}, Volatility Window: {config.VOLATILITY_MEASURE_WINDOW}, High/Low Thresholds: {config.VOLATILITY_THRESHOLD_HIGH*100:.2f}%/{config.VOLATILITY_THRESHOLD_LOW*100:.2f}%, Ehlers High/Low: {config.EHLERS_LENGTH_HIGH_VOL}/{config.EHLERS_LENGTH_LOW_VOL}, RSI High/Low: {config.RSI_WINDOW_HIGH_VOL}/{config.RSI_WINDOW_LOW_VOL}")
        self.logger.info(f"  Price Action Confirmation: {config.PRICE_ACTION_CONFIRMATION_ENABLED}, Bullish: {config.REQUIRED_BULLISH_PATTERNS}, Bearish: {config.REQUIRED_BEARISH_PATTERNS}")
        # Snippet 1: Signal Strength Scoring
        self.logger.info(f"  Min Signal Strength: {config.MIN_SIGNAL_STRENGTH}")
        # Snippet 2: Dynamic Take Profit with ATR Quality Check
        self.logger.info(f"  Min ATR for Dynamic TP: {config.MIN_ATR_TP_THRESHOLD_PCT*100:.2f}%")
        # Snippet 3: VWAP as Additional Entry Confirmation
        self.logger.info(f"  VWAP Confirmation: {config.VWAP_CONFIRMATION_ENABLED}, Window: {config.VWAP_WINDOW}")
        # Snippet 4: Trailing Stop based on Ehlers Supertrend Line
        self.logger.info(f"  Ehlers ST Trailing: {config.EHLERS_ST_TRAILING_ENABLED}, Offset: {config.EHLERS_ST_TRAILING_OFFSET_PCT*100:.2f}%")
        # Snippet 5: Volatility-Adjusted Position Sizing Robustness
        self.logger.info(f"  Min ATR for Vol Sizing: {config.MIN_ATR_FOR_SIZING_PCT*100:.2f}%")
        # Snippet 6: Time-Based Exit for Unprofitable Trades
        self.logger.info(f"  Time-Based Exit: {config.TIME_BASED_EXIT_ENABLED}, Max Unprofitable Bars: {config.UNPROFITABLE_TRADE_MAX_BARS}")
        # Snippet 7: Session-Based Volatility Filter
        self.logger.info(f"  Session Filter: {config.SESSION_FILTER_ENABLED}, Hours: {config.SESSION_START_HOUR_UTC}-{config.SESSION_END_HOUR_UTC} UTC, Min Vol: {config.SESSION_MIN_VOLATILITY_FACTOR*100:.2f}%")
        # Snippet 8: Dynamic Signal Cooldown based on Volatility
        self.logger.info(f"  Dynamic Cooldown: {config.DYNAMIC_COOLDOWN_ENABLED}, High Vol Factor: {config.COOLDOWN_VOLATILITY_FACTOR_HIGH}x, Low Vol Factor: {config.COOLDOWN_VOLATILITY_FACTOR_LOW}x")
        # Snippet 9: Order Book Depth Check for Limit Orders
        self.logger.info(f"  Order Book Depth Check: {config.ORDER_BOOK_DEPTH_CHECK_ENABLED}, Min Liquidity: ${config.MIN_LIQUIDITY_DEPTH_USD:.2f}")
        # Snippet 10: Multi-Tier Breakeven Stop Loss
        self.logger.info(f"  Multi-Tier Breakeven: {config.MULTI_TIER_BREAKEVEN_ENABLED}, Tiers: {config.BREAKEVEN_PROFIT_TIERS}")


    def _install_signal_handlers(self):
        """Installs signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Any):
        """Handler for termination signals to stop the bot gracefully."""
        self.logger.info(f"Signal {signum} received, stopping bot gracefully...")
        self.stop_event.set() # Signal all threads to stop

    def _handle_bybit_response(self, response: dict[str, Any]) -> dict[str, Any] | None:
        """
        Parses Bybit API JSON response, enforcing success checks and raising
        specific exceptions for known error codes. Returns the 'result' data on success.
        """
        if not isinstance(response, dict):
            self.logger.error(Fore.RED + f"Unexpected API response format: {type(response).__name__}, expected a dict." + Style.RESET_ALL)
            raise ValueError("Unexpected API response format, expected a dict")

        ret_code = response.get('retCode')
        ret_msg = response.get('retMsg', 'No message provided')
        result = response.get('result')

        if ret_code != 0:
            # Common authentication / permission errors
            if ret_code in {10001, 10002, 10003, 10004, 10005, 130006}:
                self.logger.critical(Fore.RED + f"Fatal Bybit API authentication error {ret_code}: {ret_msg}." + Style.RESET_ALL)
                subprocess.run(["termux-toast", f"Ehlers Bot: Fatal API Auth Error {ret_code}"])
                if self.sms_notifier.is_enabled:
                    self.sms_notifier.send_sms(f"CRITICAL: Fatal API Auth Error {ret_code} for {self.config.SYMBOL}: {ret_msg}")
                raise PermissionError(f"Bybit API authentication error {ret_code}: {ret_msg}")
            # Rate limit error
            if ret_code == 10006: # Bybit rate limit code for unified trading
                self.logger.warning(Fore.YELLOW + f"Bybit API rate limit reached {ret_code}: {ret_msg}." + Style.RESET_ALL)
                raise ConnectionRefusedError(f"Bybit API rate limit reached: {ret_msg}")
            # Other general API errors
            self.logger.error(Fore.RED + f"Bybit API returned error {ret_code}: {ret_msg}." + Style.RESET_ALL)
            subprocess.run(["termux-toast", f"Ehlers Bot: API Error {ret_code}"])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"ERROR: Bybit API error {ret_code} for {self.config.SYMBOL}: {ret_msg}")
            raise RuntimeError(f"Bybit API returned error {ret_code}: {ret_msg}")

        # Even if retCode is 0, ensure 'result' field is present for data calls
        if result is None:
            self.logger.warning(Fore.YELLOW + "Bybit API response missing 'result' field despite success code. Returning empty dict." + Style.RESET_ALL)
            return {}

        return result

    def api_call(self, api_method: Any, no_retry_codes: list[int] | None = None, **kwargs) -> dict[str, Any] | None:
        """
        A resilient incantation to invoke pybit HTTP methods,
        equipped with retries, exponential backoff (with jitter), and wise error handling.
        It guards against transient network whispers and rate limit enchantments.
        Returns the 'result' data dictionary on success, or None if all retries fail.
        """
        no_retry_codes = no_retry_codes or []
        for attempt in range(1, self.config.MAX_API_RETRIES + 1):
            try:
                raw_resp = api_method(**kwargs)
                result_data = self._handle_bybit_response(raw_resp)
                return result_data # Success, return the extracted result

            except PermissionError as e:
                self.logger.critical(Fore.RED + Style.BRIGHT + f"Fatal API error: {e}. Exiting bot." + Style.RESET_ALL)
                sys.exit(1) # Halt the bot immediately

            except (ConnectionRefusedError, RuntimeError, FailedRequestError, InvalidRequestError) as e:
                # Explicitly check for non-retriable error codes
                if "100028" in str(e): # Unified account margin mode forbidden
                    self.logger.warning(Fore.YELLOW + "Received non-retriable API error code 100028 (unified account margin mode forbidden). Skipping retry." + Style.RESET_ALL)
                    return {} # Or re-raise if this should stop the bot

                if self.stop_event.is_set(): # Check if shutdown is requested during retry loop
                    self.logger.warning("Shutdown requested during API retry. Aborting retries.")
                    return None

                if attempt == self.config.MAX_API_RETRIES:
                    self.logger.error(Fore.RED + f"API call failed after {self.config.MAX_API_RETRIES} attempts: {e}" + Style.RESET_ALL)
                    subprocess.run(["termux-toast", f"API Call Failed: {e}"])
                    if self.sms_notifier.is_enabled:
                        self.sms_notifier.send_sms(f"CRITICAL: API call failed after {self.config.MAX_API_RETRIES} retries for {self.config.SYMBOL}: {e}")
                    return None

                sleep_time = min(60.0, self.config.API_RETRY_DELAY_SEC * (2 ** (attempt - 1)))
                sleep_time *= (1.0 + random.uniform(-0.2, 0.2)) # Add jitter for backoff
                self.logger.warning(Fore.YELLOW + f"API transient error: {e} | Retrying {attempt}/{self.config.MAX_API_RETRIES} in {sleep_time:.1f}s" + Style.RESET_ALL)
                time.sleep(sleep_time)

            except Exception as e:
                if self.stop_event.is_set(): # Check if shutdown is requested during retry loop
                    self.logger.warning("Shutdown requested during API retry. Aborting retries.")
                    return None

                if attempt == self.config.MAX_API_RETRIES:
                    self.logger.error(Fore.RED + f"API call failed after {self.config.MAX_API_RETRIES} attempts due to unexpected error: {e}" + Style.RESET_ALL)
                    subprocess.run(["termux-toast", f"API Call Failed Unexpectedly: {e}"])
                    if self.sms_notifier.is_enabled:
                        self.sms_notifier.send_sms(f"CRITICAL: API call failed unexpectedly after {self.config.MAX_API_RETRIES} retries for {self.config.SYMBOL}: {e}")
                    return None

                sleep_time = min(60.0, self.config.API_RETRY_DELAY_SEC * (2 ** (attempt - 1)))
                sleep_time *= (1.0 + random.uniform(-0.2, 0.2)) # Add jitter for backoff
                self.logger.warning(Fore.YELLOW + f"API unexpected exception: {e} | Retrying {attempt}/{self.config.MAX_API_RETRIES} in {sleep_time:.1f}s" + Style.RESET_ALL)
                time.sleep(sleep_time)

        self.logger.error(Fore.RED + "API call exhausted retries and did not return success." + Style.RESET_ALL)
        return None

    def _validate_api_credentials(self):
        """
        A preliminary ritual to confirm the API keys possess true power
        before the bot embarks on its trading quest.
        Uses get_wallet_balance first (a private endpoint), falling back to get_positions if needed.
        """
        try:
            # Prefer a private endpoint that implies full auth
            data = self.api_call(self.bybit_client.get_wallet_balance, accountType='UNIFIED')
            if data is None: # If get_wallet_balance failed, try get_positions
                _ = self.api_call(self.bybit_client.get_positions, symbol=self.config.SYMBOL) # Use a specific symbol for less data
            self.logger.info(Fore.GREEN + f"API credentials validated. Environment: {'Testnet' if self.config.TESTNET else 'Mainnet'}." + Style.RESET_ALL)
            subprocess.run(["termux-toast", f"Ehlers Bot: API keys validated. Testnet: {self.config.TESTNET}"])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"API credentials validated. Environment: {'Testnet' if self.config.TESTNET else 'Mainnet'}.")
        except SystemExit: # Catch the SystemExit from api_call for fatal errors
            raise
        except Exception as e:
            self.logger.critical(Fore.RED + f"API credential validation failed: {e}. Ensure keys are correct and have appropriate permissions." + Style.RESET_ALL)
            subprocess.run(["termux-toast", f"API Credential Validation Failed: {e}"])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"CRITICAL: API credential validation failed for {self.config.SYMBOL}: {e}")
            sys.exit(1) # Halt the bot if validation fails

    def _validate_symbol_timeframe(self):
        """
        A guardian spell to ensure the chosen symbol and timeframe
        are recognized and valid within the Bybit realm.
        """
        valid_intervals = {"1","3","5","15","30","60","120","240","360","720","D","W","M"}
        if str(self.config.TIMEFRAME) not in valid_intervals:
            self.logger.critical(Fore
