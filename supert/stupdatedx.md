#!/usr/bin/env python3
import os
import time
import pandas as pd
import numpy as np
from decimal import Decimal, ROUND_DOWN, InvalidOperation
import logging
import colorlog
import threading
import subprocess
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket
from pybit.exceptions import FailedRequestError, InvalidRequestError
import ta
from datetime import datetime, timedelta
from colorama import init, Fore, Style
import dateutil.parser
import dateutil.tz
import signal
import json
import random
from types import SimpleNamespace
from typing import Optional, Dict, Any, List, Tuple
import sys
from dataclasses import dataclass, field
from enum import Enum
import hmac
import hashlib
import requests

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

def parse_to_utc(dt_str: str) -> Optional[datetime]:
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
    LEVERAGE: int = field(default=5)
    MARGIN_MODE: int = field(default=1) # 0 for cross, 1 for isolated
    HEDGE_MODE: bool = field(default=False)
    POSITION_IDX: int = field(default=0) # 0=One-way mode, 1=Long, 2=Short in hedge mode

    # Position Sizing
    RISK_PER_TRADE_PCT: float = field(default=1.0) # Risk % of account balance per trade
    MAX_POSITION_SIZE_USD: float = field(default=10000.0) # Max position value in USD
    MIN_POSITION_SIZE_USD: float = field(default=10.0) # Min position value in USD

    # Strategy Parameters
    TIMEFRAME: str = field(default="1") # Kline interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)
    LOOKBACK_PERIODS: int = field(default=200) # Historical data to fetch for indicators

    # Ehlers Adaptive Trend Parameters (from supertrend.py)
    EHLERS_LENGTH: int = field(default=30)
    SMOOTHING_LENGTH: int = field(default=10)
    SENSITIVITY: float = field(default=1.0)

    # Ehlers Supertrend Indicator Parameters (from supertrend.py)
    EHLERS_ST_LENGTH: int = field(default=10)
    EHLERS_ST_MULTIPLIER: float = field(default=3.0)

    # Other Indicator Parameters
    RSI_WINDOW: int = field(default=14)
    MACD_FAST: int = field(default=12)
    MACD_SLOW: int = field(default=26)
    MACD_SIGNAL: int = field(default=9)
    ADX_WINDOW: int = field(default=14) # Added ADX_WINDOW

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
    TERMUX_SMS_RECIPIENT_NUMBER: Optional[str] = field(default=None)

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
    PARTIAL_TP_TARGETS: List[Dict[str, float]] = field(default_factory=lambda: [
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
    TRADE_DAYS_OF_WEEK: List[str] = field(default_factory=lambda: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])

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
    TRAILING_PROFIT_TIERS: List[Dict[str, float]] = field(default_factory=lambda: [
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
    NEWS_API_ENDPOINT: Optional[str] = field(default=None) # e.g., "https://api.finnhub.io/api/v1/calendar/economic"
    NEWS_API_KEY: Optional[str] = field(default=None)
    IMPACT_LEVELS_TO_PAUSE: List[str] = field(default_factory=lambda: ["High"]) # e.g., ["High", "Medium"]
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
    REQUIRED_BULLISH_PATTERNS: List[str] = field(default_factory=lambda: ["ENGULFING", "HAMMER"])
    REQUIRED_BEARISH_PATTERNS: List[str] = field(default_factory=lambda: ["BEARISH_ENGULFING", "SHOOTING_STAR"])
    PATTERN_STRENGTH_MULTIPLIER: float = field(default=0.75)


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
        self.instruments: Dict[str, InstrumentSpecs] = {}
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
        max_order_qty = safe_decimal(unified_lot_size_filter.get('maxOrderQty', lot_size_filter.get('maxOrderQty', '1e9')))

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

    def get_specs(self, symbol: str) -> Optional[InstrumentSpecs]:
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

    def get_decimal_places(self, symbol: str) -> Tuple[int, int]:
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
        current_atr: Optional[Decimal] = None # New parameter for Volatility-Adjusted Sizing
    ) -> Optional[Decimal]:
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

        # FEATURE: Volatility-Adjusted Position Sizing
        if self.config.VOLATILITY_ADJUSTED_SIZING_ENABLED and current_atr is not None and current_atr > Decimal('0'):
            self.logger.debug(f"Using Volatility-Adjusted Sizing with ATR: {current_atr:.4f}")
            # The goal is to risk a maximum dollar amount (derived from MAX_RISK_PER_TRADE_BALANCE_PCT).
            # Position_Value_USD = (Risk_Amount_USD / (Stop_Loss_Distance_Price / Entry_Price))
            # If the stop_loss_price is dynamically set (e.g., based on ATR),
            # then a larger ATR (higher volatility) will result in a larger stop_loss_distance_price,
            # which in turn leads to a smaller calculated position_value_usd_unadjusted for the same risk amount.
            # This implicitly adjusts position size for volatility.

            risk_amount_usdt = account_balance_usdt * Decimal(str(self.config.MAX_RISK_PER_TRADE_BALANCE_PCT))
            position_value_usd_unadjusted = risk_amount_usdt / (stop_distance_price / entry_price) # This is position value in USD

        else: # Original logic
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
    Manage trailing stop losses by setting Bybit's native trailing stop (`callbackRate`).
    Once set, Bybit handles the trailing aspect. This manager focuses on initialization
    and removal of the trailing stop setting.
    """

    def __init__(self, bybit_session: HTTP, precision_manager: PrecisionManager, logger: logging.Logger, api_call_wrapper: Any, config: Config):
        self.session = bybit_session
        self.precision = precision_manager
        self.logger = logger
        self.api_call = api_call_wrapper # Reference to the bot's api_call method
        self.config = config # Added config for dynamic trailing
        # Stores active trailing stop info: {symbol: {'side': 'Buy'/'Sell', 'trail_percent': Decimal}}
        self.active_trailing_stops: Dict[str, dict] = {}
        # Store current PnL for dynamic trailing stop logic
        self.current_unrealized_pnl_pct: Dict[str, Decimal] = {}

    def initialize_trailing_stop(
        self,
        symbol: str,
        position_side: str,
        entry_price: Decimal, # Not strictly used for Bybit's callbackRate, but good for context
        current_price: Decimal, # Not strictly used for Bybit's callbackRate, but good for context
        trail_percent: float, # Pass as percentage (e.g., 0.5 for 0.5%)
        activation_percent: float # Not directly used by Bybit's callbackRate, but kept for consistency
    ) -> bool:
        """
        Initialize trailing stop for a position using Bybit's callbackRate.
        Returns True if successful, False otherwise.
        """
        specs = self.precision.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot initialize trailing stop for {symbol}: Specs not found.")
            return False

        if specs.category == 'spot':
            self.logger.debug(f"Trailing stops are not applicable for spot category {symbol}. Skipping initialization.")
            return False

        # Bybit's `callbackRate` is a percentage. So 0.5% trailing stop means callbackRate="0.5"
        # The API expects it as a string.
        trail_rate_str = str(trail_percent)

        try:
            # Set the trailing stop using set_trading_stop with callbackRate.
            # Bybit will manage the activation and trailing once set.
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
                    'trail_percent': Decimal(str(trail_percent))
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
        current_price: Decimal, # Not directly used for Bybit's callbackRate, but passed by bot
        current_unrealized_pnl_pct: Decimal, # New parameter for dynamic trailing
        update_exchange: bool = True # Typically True to ensure it's set
    ) -> bool:
        """
        Re-confirms or re-sets the trailing stop on the exchange if `update_exchange` is True.
        For Bybit's native `callbackRate`, this usually means ensuring it's still active.
        
        FEATURE: Profit Target Trailing Stop (Dynamic Trailing)
        Adjusts the trailing stop percentage based on current profit tiers.
        """
        if symbol not in self.active_trailing_stops:
            return False # No active trailing stop to update

        self.current_unrealized_pnl_pct[symbol] = current_unrealized_pnl_pct

        if not update_exchange:
            self.logger.debug(f"Internal trailing stop check for {symbol}: current price {current_price}.")
            return False # No exchange update requested

        # Determine the effective trailing percentage, potentially dynamically
        effective_trail_pct = Decimal(str(self.config.TRAILING_STOP_PCT)) * Decimal('100') # Default from config

        if self.config.DYNAMIC_TRAILING_ENABLED:
            # Sort tiers by profit_pct_trigger in descending order to find the highest applicable tier
            sorted_tiers = sorted(self.config.TRAILING_PROFIT_TIERS, key=lambda x: x['profit_pct_trigger'], reverse=True)
            
            for tier in sorted_tiers:
                if current_unrealized_pnl_pct >= Decimal(str(tier['profit_pct_trigger'])) * Decimal('100'): # Convert to % for comparison
                    effective_trail_pct = Decimal(str(tier['new_trail_pct'])) * Decimal('100')
                    self.logger.debug(f"Dynamic Trailing: PnL {current_unrealized_pnl_pct:.2f}% reached tier {tier['profit_pct_trigger']*100:.2f}%. New trail: {effective_trail_pct:.2f}%")
                    break # Use the tightest applicable trailing stop

        # Only update if the effective trailing percentage has changed or if it's the first time
        current_ts_info = self.active_trailing_stops.get(symbol)
        if current_ts_info and effective_trail_pct == current_ts_info['trail_percent']:
            self.logger.debug(f"Trailing stop for {symbol} already at desired effective rate ({effective_trail_pct:.2f}%). No update needed.")
            return True # No change, so consider it successful

        # Re-initialize the trailing stop to ensure it's active with the configured rate.
        # This will override any existing trailing stop settings for the symbol.
        ts_info = self.active_trailing_stops[symbol]
        
        # Update the active_trailing_stops with the new effective_trail_pct BEFORE calling initialize
        # to ensure it's consistent if initialize fails.
        ts_info['trail_percent'] = effective_trail_pct
        
        return self.initialize_trailing_stop(
            symbol=symbol,
            position_side=ts_info['side'],
            entry_price=Decimal('0'), # Dummy value as not used by Bybit's callbackRate
            current_price=current_price,
            trail_percent=float(effective_trail_pct), # Pass as float for API call
            activation_percent=float(effective_trail_pct) # Dummy value as not used by Bybit's callbackRate
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
    def __init__(self, recipient_number: Optional[str], logger: logging.Logger, price_precision: int):
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

    def get_server_time(self) -> Dict[str, Any]:
        """Fetches server time to synchronize our chronomancy."""
        return self.session.get_server_time()

    def get_instruments_info(self, symbol: Optional[str] = None, category: Optional[str] = None) -> Dict[str, Any]:
        """Lists active trading symbols and deciphers their fundamental laws."""
        params = {'category': category or self._default_category}
        if symbol:
            params['symbol'] = symbol
        return self.session.get_instruments_info(**params)

    def get_wallet_balance(self, accountType: str = 'UNIFIED', coin: Optional[str] = None) -> Dict[str, Any]:
        """
        Summons the knowledge of the user's wallet balance from the Bybit V5 API.
        This spell relies on the pybit library's own powerful incantation.
        """
        params = {'accountType': accountType}
        if coin:
            params['coin'] = coin
        return self.session.get_wallet_balance(**params)

    def get_kline(self, symbol: str, interval: str, limit: int = 200, category: Optional[str] = None) -> Dict[str, Any]:
        """Fetches the echoes of past market movements (historical klines)."""
        return self.session.get_kline(category=category or self._default_category, symbol=symbol, interval=interval, limit=limit)

    def get_positions(self, symbol: Optional[str] = None, category: Optional[str] = None) -> Dict[str, Any]:
        """Takes stock of all active positions, revealing their current state."""
        params = {'category': category or self._default_category}
        if symbol:
            params['symbol'] = symbol
        return self.session.get_positions(**params)

    def place_order(self, symbol: str, side: str, orderType: str, qty: str,
                    price: Optional[str] = None, stopLoss: Optional[str] = None,
                    takeProfit: Optional[str] = None, reduceOnly: bool = False,
                    category: Optional[str] = None, timeInForce: str = "GTC",
                    closeOnTrigger: bool = False, positionIdx: int = 0,
                    slOrderType: Optional[str] = None, tpOrderType: Optional[str] = None,
                    tpslMode: Optional[str] = None) -> Dict[str, Any]:
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

    def set_trading_stop(self, symbol: str, side: str, callbackRate: Optional[str] = None,
                         stopLoss: Optional[str] = None, takeProfit: Optional[str] = None,
                         category: Optional[str] = None, slOrderType: Optional[str] = None,
                         tpOrderType: Optional[str] = None, tpslMode: Optional[str] = None) -> Dict[str, Any]:
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

    def get_order_history(self, symbol: str, orderId: Optional[str] = None, limit: int = 50,
                          category: Optional[str] = None) -> Dict[str, Any]:
        """Fetches the chronicles of past orders."""
        params = {'category': category or self._default_category, 'symbol': symbol, 'limit': limit}
        if orderId:
            params['orderId'] = orderId
        return self.session.get_order_history(**params)

    def get_open_orders(self, symbol: Optional[str] = None, orderId: Optional[str] = None, limit: int = 50,
                        category: Optional[str] = None) -> Dict[str, Any]:
        """Reveals orders that currently lie in wait."""
        params = {'category': category or self._default_category, 'limit': limit}
        if symbol:
            params['symbol'] = symbol
        if orderId:
            params['orderId'] = orderId
        return self.session.get_open_orders(**params)

    def cancel_order(self, category: str, symbol: str, orderId: str) -> Dict[str, Any]:
        """Unweaves a specific thread from the market's loom (cancels an order)."""
        return self.session.cancel_order(category=category, symbol=symbol, orderId=orderId)

    def cancel_all_orders(self, category: str, symbol: str) -> Dict[str, Any]:
        """Unweaves all open threads for a symbol."""
        return self.session.cancel_all_orders(category=category, symbol=symbol)

    def switch_margin_mode(self, category: str, symbol: str, tradeMode: str) -> Dict[str, Any]:
        """Alters the margin mode for a symbol's contract."""
        return self.session.switch_margin_mode(category=category, symbol=symbol, tradeMode=tradeMode)

    def set_leverage(self, category: str, symbol: str, buyLeverage: str, sellLeverage: str) -> Dict[str, Any]:
        """Adjusts the leverage, the very amplification of one's market power."""
        return self.session.set_leverage(category=category, symbol=symbol, buyLeverage=buyLeverage, sellLeverage=sellLeverage)

    def get_tickers(self, category: str, symbol: str) -> Dict[str, Any]:
        """Fetches the current pulse of the market (ticker information)."""
        return self.session.get_tickers(category=category, symbol=symbol)

    def get_funding_rate(self, symbol: str, category: Optional[str] = None) -> Dict[str, Any]:
        """Fetches funding rate information for a perpetual contract."""
        # Note: Bybit V5 get_tickers already includes fundingRate and nextFundingTime
        # This wrapper can directly call get_tickers and extract the info.
        return self.session.get_tickers(category=category or self._default_category, symbol=symbol)


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
                print(f"{Fore.GREEN}║ Take Profit:            {Fore.WHITE}${Decimal('0.0'):.{state.price_precision}f} (N/A){Fore.GREEN:<{73 - len('Take Profit:            ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")

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
        self.news_events: List[Dict[str, Any]] = []
        self.last_fetch_time: Optional[datetime] = None
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

    def is_trading_paused(self) -> Tuple[bool, str]:
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

    def detect_pattern(self, df: pd.DataFrame, patterns: List[str]) -> Optional[str]:
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
        self.ws: Optional[WebSocket] = None # WebSocket instance
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
        self.all_open_positions: Dict[str, dict] = {} # {symbol: position_data} - New: for Max Concurrent Positions
        self.open_orders: Dict[str, dict] = {} # {order_id: order_data}
        self.account_balance_usdt: Decimal = Decimal('0.0')
        self.initial_equity: Decimal = Decimal('0.0')
        
        # --- Strategy State ---
        self.position_active: bool = False # Whether there's an active position for self.config.SYMBOL
        self.current_position_side: Optional[str] = None # 'Buy' or 'Sell' for self.config.SYMBOL
        self.current_position_entry_price: Decimal = Decimal('0') # For self.config.SYMBOL
        self.current_position_size: Decimal = Decimal('0') # For self.config.SYMBOL
        self.last_signal: Optional[str] = None # Stores the last signal acted upon
        self.last_kline_ts: int = 0 # Unix timestamp of the last processed confirmed candle
        self.last_trade_time: float = 0.0 # For trade cooldown
        self.cumulative_pnl: Decimal = Decimal('0.0') # Total realized PnL from closed trades

        # New: State for Breakeven Stop Loss
        self.breakeven_activated: Dict[str, bool] = {} # {symbol: True/False}

        # New: State for Partial Take Profit
        # {symbol: {target_idx: True}} indicates which partial TP targets have been hit for the current position
        self.partial_tp_targets_hit: Dict[str, Dict[int, bool]] = {}
        self.initial_position_qty: Decimal = Decimal('0.0') # Store initial quantity for partial TP

        # New: State for Signal Retracement Entry
        self.pending_retracement_order: Optional[Dict[str, Any]] = None # {'orderId': ..., 'side': ..., 'qty': ..., 'price': ..., 'time_placed_kline_ts': ...}

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
            self.logger.info(f"Leverage set to 1 for SPOT category as it's not applicable.")

        self.logger.info(f"Bot Configuration Loaded:")
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


    def _install_signal_handlers(self):
        """Installs signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Any):
        """Handler for termination signals to stop the bot gracefully."""
        self.logger.info(f"Signal {signum} received, stopping bot gracefully...")
        self.stop_event.set() # Signal all threads to stop

    def _handle_bybit_response(self, response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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

    def api_call(self, api_method: Any, no_retry_codes: Optional[List[int]] = None, **kwargs) -> Optional[Dict[str, Any]]:
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
                    self.logger.warning(f"Shutdown requested during API retry. Aborting retries.")
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
                    self.logger.warning(f"Shutdown requested during API retry. Aborting retries.")
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
            self.logger.critical(Fore.RED + f"Invalid timeframe '{self.config.TIMEFRAME}'. Must be one of {sorted(valid_intervals)}. Exiting." + Style.RESET_ALL)
            subprocess.run(["termux-toast", f"Invalid Timeframe: {self.config.TIMEFRAME}"])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"CRITICAL: Invalid timeframe '{self.config.TIMEFRAME}' for {self.config.SYMBOL}. Exiting.")
            sys.exit(1)
        
        # Validate higher timeframe if enabled
        if self.config.MULTI_TIMEFRAME_CONFIRMATION_ENABLED and str(self.config.HIGHER_TIMEFRAME) not in valid_intervals:
            self.logger.critical(Fore.RED + f"Invalid higher timeframe '{self.config.HIGHER_TIMEFRAME}'. Must be one of {sorted(valid_intervals)}. Exiting." + Style.RESET_ALL)
            subprocess.run(["termux-toast", f"Invalid Higher Timeframe: {self.config.HIGHER_TIMEFRAME}"])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"CRITICAL: Invalid higher timeframe '{self.config.HIGHER_TIMEFRAME}' for {self.config.SYMBOL}. Exiting.")
            sys.exit(1)


        try:
            data = self.api_call(self.bybit_client.get_instruments_info, symbol=self.config.SYMBOL, category=self.config.CATEGORY_ENUM.value)
            lst = (data or {}).get('list', [])
            if not lst:
                self.logger.critical(Fore.RED + f"Symbol '{self.config.SYMBOL}' not found for category '{self.config.CATEGORY_ENUM.value}'. Exiting." + Style.RESET_ALL)
                subprocess.run(["termux-toast", f"Symbol Not Found: {self.config.SYMBOL}"])
                if self.sms_notifier.is_enabled:
                    self.sms_notifier.send_sms(f"CRITICAL: Symbol '{self.config.SYMBOL}' not found. Exiting.")
                sys.exit(1)
            self.logger.info(Fore.GREEN + f"Symbol '{self.config.SYMBOL}' and timeframe '{self.config.TIMEFRAME}' validated." + Style.RESET_ALL)
        except SystemExit:
            raise
        except Exception as e:
            self.logger.critical(Fore.RED + f"Symbol/timeframe validation failed: {e}. Exiting." + Style.RESET_ALL)
            subprocess.run(["termux-toast", f"Symbol/Timeframe Validation Failed: {e}"])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"CRITICAL: Symbol/Timeframe validation failed for {self.config.SYMBOL}: {e}. Exiting.")
            sys.exit(1)

    def _capture_initial_equity(self):
        """
        Records the account's equity at the beginning of the bot's operation,
        a baseline for the cumulative loss protection enchantment.
        """
        eq = self.get_account_balance_usdt()
        if eq > Decimal('0'):
            self.initial_equity = eq
            with self.bot_state.lock:
                self.bot_state.initial_equity = eq # Update BotState
            self.logger.info(Fore.GREEN + f"Initial equity set to {self.initial_equity:.4f} USDT." + Style.RESET_ALL)
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"Bot session started. Initial Equity: ${self.initial_equity:.2f}")
        else:
            self.logger.warning(Fore.YELLOW + "Could not fetch initial equity or equity is zero; cumulative loss guard will use PnL fallback logic." + Style.RESET_ALL)

    def _cumulative_loss_guard(self) -> bool:
        """
        A protective ward that halts trading if the cumulative equity drawdown
        exceeds the predefined maximum loss threshold from the initial equity.
        """
        current_equity = self.get_account_balance_usdt() # This also updates bot_state.current_equity
        
        if self.initial_equity <= Decimal('0') or current_equity <= Decimal('0'): # Ensure valid initial and current equity
            self.logger.warning(Fore.YELLOW + "Could not fetch valid initial or current equity for cumulative loss guard. Proceeding cautiously." + Style.RESET_ALL)
            # Fallback to cumulative PnL-based logic if initial equity wasn't captured or current is zero
            # This fallback assumes initial_equity was at least captured once.
            if self.initial_equity > Decimal('0') and self.cumulative_pnl < -abs(Decimal(str(self.config.MAX_DAILY_LOSS_PCT))) * self.initial_equity:
                self.logger.critical(Fore.RED + f"Cumulative PnL loss limit reached ({self.cumulative_pnl:.2f} USDT). Trading halted!" + Style.RESET_ALL)
                subprocess.run(["termux-toast", "Cumulative PnL Loss Limit Reached! Trading Halted."])
                if self.sms_notifier.is_enabled:
                    self.sms_notifier.send_sms(f"CRITICAL: Cumulative PnL loss limit reached for {self.config.SYMBOL} ({self.cumulative_pnl:.2f} USDT). Trading halted!")
                return False
            elif self.initial_equity <= Decimal('0'):
                self.logger.warning(Fore.YELLOW + "Initial equity not set. Cumulative loss guard is inactive." + Style.RESET_ALL)
                return True # Cannot apply loss guard without initial equity
            return True

        drop_amount = self.initial_equity - current_equity
        drop_pct = (drop_amount / self.initial_equity) * Decimal('100')

        if drop_pct >= Decimal(str(self.config.MAX_DAILY_LOSS_PCT * 100)): # Compare percentage directly
            self.logger.critical(Fore.RED + Style.BRIGHT + f"Cumulative equity drawdown {drop_pct:.2f}% exceeded limit ({self.config.MAX_DAILY_LOSS_PCT*100:.2f}%). Trading halted!" + Style.RESET_ALL)
            subprocess.run(["termux-toast", f"Cumulative Loss Limit Reached! Drawdown: {drop_pct:.2f}%"])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"CRITICAL: Cumulative equity drawdown {drop_pct:.2f}% exceeded limit for {self.config.SYMBOL}. Trading halted!")
            
            # Optional: close open position if loss limit is hit
            if self.position_active: # Check bot's internal state
                self.logger.warning(Fore.YELLOW + "Closing open position due to cumulative loss limit enchantment." + Style.RESET_ALL)
                self.close_position() # This will also update cumulative_pnl and bot_state
            return False
        return True

    # =====================================================================
    # DATA FETCHING METHODS
    # =====================================================================

    def fetch_klines(self, symbol: str, interval: str, limit: Optional[int] = None) -> pd.DataFrame:
        """Fetch historical kline data from Bybit."""
        try:
            fetch_limit = limit if limit else self.config.LOOKBACK_PERIODS
            if fetch_limit < 2: # Need at least 2 candles for signal generation
                fetch_limit = 2

            self.logger.debug(f"Fetching {fetch_limit} klines for {symbol} ({interval})...")
            response_data = self.api_call(
                self.bybit_client.get_kline,
                category=self.config.CATEGORY_ENUM.value,
                symbol=symbol,
                interval=interval,
                limit=fetch_limit
            )

            if response_data is not None and response_data.get('list'):
                klines = response_data['list']
                if not klines:
                    self.logger.warning(f"No kline data returned for {symbol}.")
                    return pd.DataFrame()

                df = pd.DataFrame(klines, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
                ])

                # Convert types for correct calculations
                df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
                for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                    df[col] = pd.to_numeric(df[col], errors='coerce') # Use to_numeric for robust conversion

                # Sort by timestamp and set index
                df = df.sort_values('timestamp')
                df.set_index('timestamp', inplace=True)

                # Drop rows with NaN values that might occur from parsing errors
                df.dropna(inplace=True)

                self.logger.debug(f"Successfully fetched and processed {len(df)} klines for {symbol}.")
                return df
            else:
                self.logger.error(f"Failed to fetch klines for {symbol}: API call wrapper returned None or empty list.")
                return pd.DataFrame()

        except Exception as e:
            self.logger.error(f"Exception fetching klines for {symbol}: {e}", exc_info=True)
            return pd.DataFrame()

    def _get_current_orderbook(self) -> Tuple[Decimal, Decimal]:
        """Fetches the top bid and ask prices from the ticker for UI."""
        try:
            response_data = self.api_call(
                self.bybit_client.get_tickers,
                category=self.config.CATEGORY_ENUM.value,
                symbol=self.config.SYMBOL
            )
            if response_data and response_data.get('list'):
                ticker_info = response_data['list'][0]
                bid_price = Decimal(str(ticker_info.get('bid1Price', '0')))
                ask_price = Decimal(str(ticker_info.get('ask1Price', '0')))
                return bid_price, ask_price
        except Exception as e:
            self.logger.error(f"Failed to get ticker for {self.config.SYMBOL} (for bid/ask): {e}")
        return Decimal('0.0'), Decimal('0.0')

    def get_account_balance_usdt(self) -> Decimal:
        """Get current account balance in USDT and update internal state and BotState."""
        account_type = "UNIFIED"
        if self.config.CATEGORY_ENUM == Category.SPOT:
            account_type = "SPOT"

        try:
            response_data = self.api_call(self.bybit_client.get_wallet_balance, accountType=account_type)

            if response_data is not None and response_data.get('list'):
                account_list = response_data['list']
                for account in account_list:
                    if account.get('accountType') == account_type:
                        for coin_data in account.get('coin', []):
                            if coin_data.get('coin') == 'USDT': # Or self.config.QUOTE_CURRENCY if configurable
                                balance = Decimal(coin_data.get('walletBalance', '0'))
                                self.account_balance_usdt = balance
                                with self.bot_state.lock: # Update BotState
                                    self.bot_state.current_equity = balance
                                self.logger.debug(f"Successfully fetched account balance: {balance:.4f} USDT ({account_type})")
                                return balance
                
                self.logger.warning(f"USDT balance not found in response for account type {account_type}. Returning 0.")
                self.account_balance_usdt = Decimal('0.0')
                with self.bot_state.lock:
                    self.bot_state.current_equity = Decimal('0.0')
                return Decimal('0.0')
            else:
                self.logger.error(f"Failed to get account balance ({account_type}): API call wrapper returned None or empty list.")
                self.account_balance_usdt = Decimal('0.0')
                with self.bot_state.lock:
                    self.bot_state.current_equity = Decimal('0.0')
                return Decimal('0.0')

        except Exception as e:
            self.logger.error(f"Exception getting account balance ({account_type}): {e}", exc_info=True)
            self.account_balance_usdt = Decimal('0.0')
            with self.bot_state.lock:
                self.bot_state.current_equity = Decimal('0.0')
            return Decimal('0.0')

    def _configure_trading_parameters(self) -> bool:
        """Set margin mode and leverage for the trading symbol, respecting min/max/step limits."""
        if self.config.CATEGORY_ENUM == Category.SPOT:
            self.logger.info("Spot trading does not use margin mode or leverage. Skipping parameter configuration.")
            return True

        # --- Set Margin Mode ---
        try:
            margin_mode_str = 'Isolated' if self.config.MARGIN_MODE == 1 else 'Cross'
            self.logger.info(f"Attempting to set margin mode to {margin_mode_str} for {self.config.SYMBOL}...")
            self.api_call(
                self.bybit_client.switch_margin_mode,
                category=self.config.CATEGORY_ENUM.value,
                symbol=self.config.SYMBOL,
                tradeMode=str(self.config.MARGIN_MODE)
            )
            self.logger.info(f"Margin mode set successfully to {margin_mode_str} for {self.config.SYMBOL}.")
        except (InvalidRequestError, RuntimeError) as e:
            if "100028" in str(e) or "unified account is forbidden" in str(e):
                self.logger.warning(Fore.YELLOW + "A whisper from the ether (100028): Margin mode is immutable for Unified Accounts via API.")
                self.logger.warning(Fore.YELLOW + f"Please ensure your account is manually set to your desired mode ({margin_mode_str}) in your Bybit settings.")
                self.logger.info("The bot shall proceed, assuming the mode is correctly configured.")
            else:
                self.logger.error(f"An unexpected error occurred while setting margin mode: {e}. The bot will continue.", exc_info=True)
        except Exception as e:
            self.logger.error(f"A critical error occurred during margin mode configuration: {e}", exc_info=True)

        # --- Set Leverage ---
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot set leverage for {self.config.SYMBOL}: Specs not found.")
            return False

        try:
            leverage_to_set_decimal = Decimal(str(self.config.LEVERAGE))
            min_lev, max_lev, lev_step = specs.min_leverage, specs.max_leverage, specs.leverage_step

            if leverage_to_set_decimal < min_lev:
                self.logger.warning(f"Requested leverage {leverage_to_set_decimal}x is below minimum {min_lev}x. Adjusting to minimum.")
                leverage_to_set_decimal = min_lev
            elif leverage_to_set_decimal > max_lev:
                self.logger.warning(f"Requested leverage {leverage_to_set_decimal}x exceeds maximum {max_lev}x. Adjusting to maximum.")
                leverage_to_set_decimal = max_lev

            if lev_step > Decimal('0'):
                num_steps = (leverage_to_set_decimal / lev_step).quantize(Decimal('1'), rounding=ROUND_DOWN)
                leverage_to_set_decimal = num_steps * lev_step
                leverage_to_set_decimal = max(min_lev, min(leverage_to_set_decimal, max_lev))

            leverage_str = str(leverage_to_set_decimal)
            self.logger.info(f"Attempting to set leverage to {leverage_str}x for {self.config.SYMBOL}...")
            
            self.api_call(
                self.bybit_client.set_leverage,
                category=self.config.CATEGORY_ENUM.value,
                symbol=self.config.SYMBOL,
                buyLeverage=leverage_str,
                sellLeverage=leverage_str
            )
            self.logger.info(f"Leverage set successfully to {leverage_str}x for {self.config.SYMBOL}.")
            return True
        except (InvalidRequestError, RuntimeError) as e:
            if "110043" in str(e): # leverage not modified
                self.logger.info(Fore.GREEN + "Leverage is already set to the desired value. No modification needed." + Style.RESET_ALL)
                return True
            else:
                self.logger.error(f"An API error occurred while setting leverage: {e}", exc_info=True)
                return False
        except Exception as e:
            self.logger.error(f"A critical exception occurred setting leverage for {self.config.SYMBOL}: {e}", exc_info=True)
            return False

    # =====================================================================
    # TECHNICAL INDICATORS
    # =====================================================================

    def calculate_indicators(self, df: pd.DataFrame, is_higher_timeframe: bool = False) -> pd.DataFrame:
        """
        Applies all required indicators to the DataFrame,
        weaving complex patterns from the raw market energies with enhanced robustness.
        FEATURE: Adaptive Indicator Parameters (Volatility-Based)
        """
        
        # Determine indicator parameters dynamically if enabled
        ehlers_length = self.config.EHLERS_LENGTH
        rsi_window = self.config.RSI_WINDOW

        if self.config.ADAPTIVE_INDICATORS_ENABLED and not is_higher_timeframe: # Only apply to primary timeframe
            if len(df) >= self.config.VOLATILITY_MEASURE_WINDOW:
                # Calculate volatility using ATR as a percentage of price
                atr_series = ta.volatility.AverageTrueRange(
                    high=df['high'],
                    low=df['low'],
                    close=df['close'],
                    window=self.config.VOLATILITY_MEASURE_WINDOW,
                    fillna=True
                ).average_true_range()
                
                # Avoid division by zero if close price is 0
                current_volatility = atr_series.iloc[-1] / df['close'].iloc[-1] if df['close'].iloc[-1] > 0 else 0

                if current_volatility >= self.config.VOLATILITY_THRESHOLD_HIGH:
                    ehlers_length = self.config.EHLERS_LENGTH_HIGH_VOL
                    rsi_window = self.config.RSI_WINDOW_HIGH_VOL
                    self.logger.debug(f"High volatility detected ({current_volatility:.4f}%). Adapting Ehlers Length to {ehlers_length}, RSI Window to {rsi_window}.")
                elif current_volatility <= self.config.VOLATILITY_THRESHOLD_LOW:
                    ehlers_length = self.config.EHLERS_LENGTH_LOW_VOL
                    rsi_window = self.config.RSI_WINDOW_LOW_VOL
                    self.logger.debug(f"Low volatility detected ({current_volatility:.4f}%). Adapting Ehlers Length to {ehlers_length}, RSI Window to {rsi_window}.")
                else:
                    self.logger.debug(f"Normal volatility ({current_volatility:.4f}%). Using default Ehlers Length {ehlers_length}, RSI Window {rsi_window}.")
            else:
                self.logger.warning(f"Not enough data for adaptive indicators (need {self.config.VOLATILITY_MEASURE_WINDOW} periods). Using default parameters.")
        
        # Update bot_state with adaptive parameters
        if not is_higher_timeframe:
            with self.bot_state.lock:
                self.bot_state.adaptive_ehlers_length = ehlers_length
                self.bot_state.adaptive_rsi_window = rsi_window
            self.current_ehlers_length = ehlers_length
            self.current_rsi_window = rsi_window


        # Ensure sufficient data for all indicators
        min_len = max(ehlers_length + self.config.SMOOTHING_LENGTH + 5,
                      self.config.EHLERS_ST_LENGTH + 5,
                      self.config.MACD_SLOW + self.config.MACD_SIGNAL + 5,
                      rsi_window + 5,
                      self.config.ADX_WINDOW + 5,
                      self.config.ATR_TP_WINDOW + 5, # For Dynamic TP
                      60) # A reasonable minimum for most TA indicators

        if len(df) < min_len:
            self.logger.warning(Fore.YELLOW + f"Not enough data for indicators (have {len(df)}, need {min_len}). Returning DataFrame with NaNs for indicators." + Style.RESET_ALL)
            # Ensure indicator columns exist and are filled with NaN if data is insufficient
            for col in ["ehlers_trend", "ehlers_filter", "supertrend_line_value", "supertrend_direction", "rsi", "macd", "macd_signal", "macd_diff", "adx", "adx_plus_di", "adx_minus_di", "atr"]:
                if col not in df.columns:
                    df[col] = np.nan
            return df

        # Ensure numeric types for calculations
        close = df['close'].astype(float).values
        high = df['high'].astype(float).values
        low = df['low'].astype(float).values

        # Ehlers Adaptive Trend: Sensing the hidden currents (custom filter from original bot)
        a1 = np.exp(-np.pi * np.sqrt(2) / float(self.config.SMOOTHING_LENGTH))
        b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / float(self.config.SMOOTHING_LENGTH))
        c2, c3, c1 = b1, -a1 * a1, 1 - b1 + a1 * a1
        
        filt = np.zeros(len(close), dtype=float)
        # Handle initial values for filt to avoid index errors or NaN propagation
        if len(close) > 0:
            filt[0] = close[0]
        if len(close) > 1:
            filt[1] = (c1 * (close[1] + close[0]) / 2.0) + (c2 * filt[0])
        for i in range(2, len(close)): # Start from 2 as 0 and 1 are handled
            filt[i] = c1 * (close[i] + close[i-1]) / 2.0 + c2 * filt[i-1] + c3 * filt[i-2]
        df['ehlers_filter'] = pd.Series(filt, index=df.index) # Store Ehlers filter for UI

        vol_series = pd.Series(high - low, index=df.index)
        # Use min_periods to allow calculation with less than full window at start
        volatility = vol_series.rolling(ehlers_length, min_periods=max(1, ehlers_length//2)).std().ewm(span=self.config.SMOOTHING_LENGTH, adjust=False).mean()
        
        raw_trend = np.where(df['close'] > (filt + (volatility * self.config.SENSITIVITY)), 1,\
                             np.where(df['close'] < (filt - (volatility * self.config.SENSITIVITY)), -1, np.nan))
        df['ehlers_trend'] = pd.Series(raw_trend, index=df.index).ffill() # Fill NaNs forward

        # --- SuperTrend (Manual Implementation) ---
        atr = ta.volatility.AverageTrueRange(
            high=df['high'],
            low=df['low'],
            close=df['close'],
            window=self.config.EHLERS_ST_LENGTH,
            fillna=True
        ).average_true_range()

        basic_upper = (df['high'] + df['low']) / 2 + self.config.EHLERS_ST_MULTIPLIER * atr
        basic_lower = (df['high'] + df['low']) / 2 - self.config.EHLERS_ST_MULTIPLIER * atr

        final_upper = pd.Series(np.nan, index=df.index)
        final_lower = pd.Series(np.nan, index=df.index)
        supertrend_line = pd.Series(np.nan, index=df.index)

        if not df.empty:
            final_upper.iloc[0] = basic_upper.iloc[0]
            final_lower.iloc[0] = basic_lower.iloc[0]
            supertrend_line.iloc[0] = final_lower.iloc[0]

            for i in range(1, len(df)):
                if basic_upper.iloc[i] < final_upper.iloc[i-1] or df['close'].iloc[i-1] > final_upper.iloc[i-1]:
                    final_upper.iloc[i] = basic_upper.iloc[i]
                else:
                    final_upper.iloc[i] = final_upper.iloc[i-1]

                if basic_lower.iloc[i] > final_lower.iloc[i-1] or df['close'].iloc[i-1] < final_lower.iloc[i-1]:
                    final_lower.iloc[i] = basic_lower.iloc[i]
                else:
                    final_lower.iloc[i] = final_lower.iloc[i-1]

                if supertrend_line.iloc[i-1] == final_upper.iloc[i-1] and df['close'].iloc[i] > final_upper.iloc[i]:
                    supertrend_line.iloc[i] = final_lower.iloc[i]
                elif supertrend_line.iloc[i-1] == final_upper.iloc[i-1] and df['close'].iloc[i] <= final_upper.iloc[i]:
                    supertrend_line.iloc[i] = final_upper.iloc[i]
                elif supertrend_line.iloc[i-1] == final_lower.iloc[i-1] and df['close'].iloc[i] < final_lower.iloc[i]:
                    supertrend_line.iloc[i] = final_upper.iloc[i]
                elif supertrend_line.iloc[i-1] == final_lower.iloc[i-1] and df['close'].iloc[i] >= final_lower.iloc[i]:
                    supertrend_line.iloc[i] = final_lower.iloc[i]
        
        df['supertrend_line_value'] = supertrend_line
        df['supertrend_direction'] = np.where(df['close'] > df['supertrend_line_value'], 1, -1)

        # Additional Filters - RSI: Measuring the momentum's fervor
        rsi = ta.momentum.RSIIndicator(df['close'], window=rsi_window, fillna=True)
        df['rsi'] = rsi.rsi()

        # Additional Filters - MACD: Unveiling the convergence and divergence of forces
        macd = ta.trend.MACD(df['close'], window_fast=self.config.MACD_FAST, window_slow=self.config.MACD_SLOW, window_sign=self.config.MACD_SIGNAL, fillna=True)
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()
        
        # ADX: Trend Strength and Direction
        adx_indicator = ta.trend.ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=self.config.ADX_WINDOW, fillna=True)
        df['adx'] = adx_indicator.adx()
        df['adx_plus_di'] = adx_indicator.adx_pos()
        df['adx_minus_di'] = adx_indicator.adx_neg()

        # FEATURE: ATR for Dynamic TP and Volatility Sizing
        df['atr'] = ta.volatility.AverageTrueRange(
            high=df['high'],
            low=df['low'],
            close=df['close'],
            window=self.config.ATR_TP_WINDOW if not is_higher_timeframe else self.config.VOLATILITY_WINDOW, # Use ATR_TP_WINDOW for primary, VOLATILITY_WINDOW for sizing
            fillna=True
        ).average_true_range()
        
        # Drop rows where indicators are NaN (remove initial NaN rows, after fillna)
        required_indicator_cols = ['ehlers_trend', 'ehlers_filter', 'supertrend_direction', 'supertrend_line_value', 'rsi', 'macd', 'macd_signal', 'macd_diff', 'adx', 'adx_plus_di', 'adx_minus_di', 'atr']
        df.dropna(subset=required_indicator_cols, inplace=True)

        if df.empty:
            self.logger.warning("All rows dropped due to NaN indicators. Cannot proceed.")
            return pd.DataFrame()

        self.logger.debug(f"Ehlers indicators calculated. DataFrame shape: {df.shape}")
        return df

    # =====================================================================
    # STRATEGY LOGIC
    # =====================================================================

    def generate_signal(self, df: pd.DataFrame) -> Tuple[Optional[str], str]:
        """
        Generates a potent trading signal by harmonizing the whispers of multiple indicators,
        seeking confluence for optimal entry and exit points, with optional bar confirmation.
        Returns the signal ('BUY'/'SELL'/None) and a detailed reason string.
        """
        if len(df) < 2:
            return None, "Insufficient data for signal generation."

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # --- Primary Scalping Signal: Supertrend Flip ---
        st_flipped_up = latest['supertrend_direction'] == 1 and prev['supertrend_direction'] == -1
        st_flipped_down = latest['supertrend_direction'] == -1 and prev['supertrend_direction'] == 1

        # --- Base Confirmation Filters ---
        price_above_filter = latest['close'] > latest['ehlers_filter']
        price_below_filter = latest['close'] < latest['ehlers_filter']
        
        rsi_bullish = latest['rsi'] > 52
        rsi_bearish = latest['rsi'] < 48

        macd_bullish = latest['macd_diff'] > 0
        macd_bearish = latest['macd_diff'] < 0

        # --- FEATURE: Market Trend Filter (ADX-based) ---
        if self.config.ADX_TREND_FILTER_ENABLED:
            if latest['adx'] < self.config.ADX_MIN_THRESHOLD:
                return None, f"ADX ({latest['adx']:.1f}) below min threshold ({self.config.ADX_MIN_THRESHOLD}). No trade."
            
            if self.config.ADX_TREND_DIRECTION_CONFIRMATION:
                if st_flipped_up and latest['adx_plus_di'] < latest['adx_minus_di']:
                    return None, f"ADX Plus DI ({latest['adx_plus_di']:.1f}) not confirming BUY signal. No trade."
                if st_flipped_down and latest['adx_minus_di'] < latest['adx_plus_di']:
                    return None, f"ADX Minus DI ({latest['adx_minus_di']:.1f}) not confirming SELL signal. No trade."

        # --- FEATURE: Multiple Timeframe Confluence Filter ---
        if self.config.MULTI_TIMEFRAME_CONFIRMATION_ENABLED and not self.higher_timeframe_data.empty:
            htf_latest = self.higher_timeframe_data.iloc[-1]
            htf_confluence = False
            htf_reason = ""

            if self.config.HIGHER_TIMEFRAME_INDICATOR == "EHLERS_SUPERTR_DIRECTION":
                htf_st_direction = htf_latest.get('supertrend_direction')
                if st_flipped_up and htf_st_direction == 1:
                    htf_confluence = True
                    htf_reason = f"HTF {self.config.HIGHER_TIMEFRAME} Ehlers ST is UP."
                elif st_flipped_down and htf_st_direction == -1:
                    htf_confluence = True
                    htf_reason = f"HTF {self.config.HIGHER_TIMEFRAME} Ehlers ST is DOWN."
                else:
                    htf_reason = f"HTF {self.config.HIGHER_TIMEFRAME} Ehlers ST is not confirming primary timeframe."
            # Add other indicator checks for higher timeframe here if needed
            # elif self.config.HIGHER_TIMEFRAME_INDICATOR == "ADX_TREND":
            # ...

            if self.config.REQUIRED_CONFLUENCE and not htf_confluence:
                return None, f"Multi-timeframe filter rejected signal. {htf_reason}"
            elif htf_confluence:
                self.logger.debug(f"Multi-timeframe confluence confirmed: {htf_reason}")

        # --- FEATURE: Price Action Confirmation (Candlestick Patterns) ---
        if self.config.PRICE_ACTION_CONFIRMATION_ENABLED:
            pattern_detected = None
            if st_flipped_up: # Look for bullish patterns
                pattern_detected = self.candlestick_detector.detect_pattern(df, self.config.REQUIRED_BULLISH_PATTERNS)
                if not pattern_detected:
                    return None, "Bullish signal detected, but no required bullish candlestick pattern found."
            elif st_flipped_down: # Look for bearish patterns
                pattern_detected = self.candlestick_detector.detect_pattern(df, self.config.REQUIRED_BEARISH_PATTERNS)
                if not pattern_detected:
                    return None, "Bearish signal detected, but no required bearish candlestick pattern found."
            
            if pattern_detected:
                self.logger.debug(f"Candlestick pattern '{pattern_detected}' confirmed signal.")


        # --- Signal Generation ---
        if st_flipped_up and price_above_filter and rsi_bullish and macd_bullish:
            reason = f"BUY: Supertrend flipped UP, Price > Ehlers Filter, RSI({latest['rsi']:.1f}) > 52, MACD Hist > 0"
            return 'BUY', reason

        if st_flipped_down and price_below_filter and rsi_bearish and macd_bearish:
            reason = f"SELL: Supertrend flipped DOWN, Price < Ehlers Filter, RSI({latest['rsi']:.1f}) < 48, MACD Hist < 0"
            return 'SELL', reason

        return None, "No clear scalping signal."

    # =====================================================================
    # RISK MANAGEMENT
    # =====================================================================

    def calculate_trade_sl_tp(self, side: str, entry_price: Decimal, df: pd.DataFrame) -> Tuple[Decimal, Decimal]:
        """
        Calculates Stop Loss and Take Profit levels based on fixed percentages,
        or dynamically using ATR if enabled.
        Returns (stop_loss_price, take_profit_price).
        """
        sl_pct_decimal = Decimal(str(self.config.STOP_LOSS_PCT))
        
        # FEATURE: Dynamic Take Profit (DTP) via ATR
        if self.config.DYNAMIC_TP_ENABLED and not df.empty and 'atr' in df.columns:
            atr_value = Decimal(str(df['atr'].iloc[-1])) # Use ATR from current timeframe
            if atr_value > Decimal('0'):
                # Calculate TP in price units based on ATR
                dynamic_tp_price_units = atr_value * Decimal(str(self.config.ATR_TP_MULTIPLIER))
                
                # Convert to percentage relative to entry price
                dynamic_tp_pct = dynamic_tp_price_units / entry_price
                
                # Clamp between min and max TP percentages
                tp_pct_decimal = max(Decimal(str(self.config.MIN_TAKE_PROFIT_PCT)),
                                     min(dynamic_tp_pct, Decimal(str(self.config.MAX_TAKE_PROFIT_PCT))))
                self.logger.debug(f"Dynamic TP calculated: ATR={atr_value:.4f}, Price Units={dynamic_tp_price_units:.4f}, Raw PCT={dynamic_tp_pct:.4f}, Final PCT={tp_pct_decimal:.4f}")
            else:
                self.logger.warning("ATR value is zero or not available for Dynamic TP. Using fixed TP percentage.")
                tp_pct_decimal = Decimal(str(self.config.TAKE_PROFIT_PCT))
        else:
            tp_pct_decimal = Decimal(str(self.config.TAKE_PROFIT_PCT))
        
        if side == 'Buy':
            stop_loss = entry_price * (Decimal('1') - sl_pct_decimal)
            take_profit = entry_price * (Decimal('1') + tp_pct_decimal)
        else: # Sell
            stop_loss = entry_price * (Decimal('1') + sl_pct_decimal)
            take_profit = entry_price * (Decimal('1') - tp_pct_decimal)

        # Round to appropriate price precision
        stop_loss = self.precision_manager.round_price(self.config.SYMBOL, stop_loss)
        take_profit = self.precision_manager.round_price(self.config.SYMBOL, take_profit)

        self.logger.info(Fore.LIGHTMAGENTA_EX + f"Calculated SL/TP: SL=${stop_loss:.{self.bot_state.price_precision}f}, TP=${take_profit:.{self.bot_state.price_precision}f}" + Style.RESET_ALL)
        return stop_loss, take_profit


    # =====================================================================
    # ORDER MANAGEMENT
    # =====================================================================

    def place_order(self, side: str, qty: Decimal, order_type: OrderType,
                   entry_price: Optional[Decimal] = None, stopLoss: Optional[Decimal] = None,
                   takeProfit: Optional[Decimal] = None, reduce_only: bool = False) -> Optional[dict]:
        """
        Place an order on Bybit, handling precision and Bybit V5 API parameters.
        Includes verification if the order was actually filled.
        Returns the filled order details on success, None otherwise.
        
        FEATURE: Slippage Tolerance for Market Orders
        Checks for excessive slippage for market orders and logs a warning.
        """
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot place order for {self.config.SYMBOL}: Specs not found.")
            return None

        rounded_qty = self.precision_manager.round_quantity(self.config.SYMBOL, qty)
        if rounded_qty <= Decimal('0'):
            self.logger.warning(f"Invalid quantity ({qty} rounded to {rounded_qty}) for order placement in {self.config.SYMBOL}. Aborting order.")
            return None

        # Determine the intended price for market orders for slippage check
        intended_price = entry_price
        if order_type == OrderType.MARKET and intended_price is None:
            intended_price = Decimal(str(self.market_data['close'].iloc[-1])) if not self.market_data.empty else Decimal('0.0')
        if intended_price <= Decimal('0'):
            self.logger.warning("Intended price for market order is zero or not available. Slippage check will be skipped.")

        # Convert Decimal values to string for API
        str_qty = str(rounded_qty)
        str_price = str(self.precision_manager.round_price(self.config.SYMBOL, entry_price)) if entry_price else None
        str_stopLoss = str(self.precision_manager.round_price(self.config.SYMBOL, stopLoss)) if stopLoss else None
        str_takeProfit = str(self.precision_manager.round_price(self.config.SYMBOL, takeProfit)) if takeProfit else None

        self.logger.info(f"Placing order for {self.config.SYMBOL}: Side={side}, Qty={str_qty}, Type={order_type.value}, "
                         f"Price={str_price}, SL={str_stopLoss}, TP={str_takeProfit}, ReduceOnly={reduce_only}")
        
        if self.config.DRY_RUN:
            self.logger.info(Fore.YELLOW + f"[DRY RUN] Would place {side} order of {str_qty} {self.config.SYMBOL} ({order_type.value})" + Style.RESET_ALL)
            # Simulate a successful order placement for dry run
            simulated_price = entry_price or Decimal(self.market_data['close'].iloc[-1])
            return {'orderId': 'DRY_RUN_ORDER_ID_' + str(int(time.time())), 'orderStatus': 'Filled', 'avgPrice': str(simulated_price), 'cumExecQty': str_qty}

        try:
            order_response = self.api_call(
                self.bybit_client.place_order,
                symbol=self.config.SYMBOL,
                side=side,
                orderType=order_type.value,
                qty=str_qty,
                price=str_price,
                stopLoss=str_stopLoss,
                takeProfit=str_takeProfit,
                reduceOnly=reduce_only,
                category=specs.category,
                timeInForce=self.config.TIME_IN_FORCE,
                closeOnTrigger=False, # Not using this for primary orders
                positionIdx=self.config.POSITION_IDX if self.config.HEDGE_MODE else 0,
                slOrderType='Market', # Always market for SL
                tpOrderType='Limit', # Usually limit for TP
                tpslMode='Full' if (stopLoss is not None or takeProfit is not None) else None
            )
            
            if order_response and order_response.get('orderId'):
                order_id = order_response['orderId']
                self.logger.info(Fore.GREEN + f"Order spell cast with ID: {order_id}. Awaiting the market's response..." + Style.RESET_ALL)
                
                # --- VERIFY ORDER EXECUTION --- 
                # Poll for order status to confirm fill
                max_retries = 5
                retry_delay = 1 # seconds
                for i in range(max_retries):
                    time.sleep(retry_delay)
                    order_details = self.api_call(self.bybit_client.get_order_history, symbol=self.config.SYMBOL, orderId=order_id, category=specs.category)
                    
                    if order_details and order_details.get('list') and order_details['list']:
                        filled_order = order_details['list'][0]
                        order_status = filled_order.get('orderStatus')
                        
                        if order_status in ('Filled', 'PartiallyFilled'):
                            avg_price_str = filled_order.get('avgPrice')
                            filled_price = Decimal(avg_price_str) if avg_price_str and Decimal(avg_price_str) > Decimal('0') else (entry_price or Decimal(self.market_data['close'].iloc[-1])) # Fallback
                            filled_qty = Decimal(filled_order.get('cumExecQty', '0'))
                            
                            # FEATURE: Slippage Tolerance for Market Orders
                            if order_type == OrderType.MARKET and intended_price is not None and intended_price > Decimal('0'):
                                actual_slippage_pct = abs(filled_price - intended_price) / intended_price
                                if actual_slippage_pct > Decimal(str(self.config.SLIPPAGE_TOLERANCE_PCT)):
                                    self.logger.warning(Fore.YELLOW + f"⚠️ High Slippage Detected for Market Order {order_id}: {actual_slippage_pct*100:.2f}% (Intended: ${intended_price:.{self.bot_state.price_precision}f}, Filled: ${filled_price:.{self.bot_state.price_precision}f}). Tolerance: {self.config.SLIPPAGE_TOLERANCE_PCT*100:.2f}%" + Style.RESET_ALL)
                                    # Depending on policy, might raise an error or just log. For now, log and proceed.
                                else:
                                    self.logger.info(f"Slippage for market order {order_id}: {actual_slippage_pct*100:.2f}% (within tolerance).")


                            self.logger.info(Fore.GREEN + f"✅ Order FILLED: {side} {filled_qty:.{self.bot_state.qty_precision}f} {self.config.SYMBOL} at avg ${filled_price:.{self.bot_state.price_precision}f} (Order ID: {order_id})" + Style.RESET_ALL)
                            subprocess.run(["termux-toast", f"Order FILLED: {side} {self.config.SYMBOL} at {filled_price:.{self.bot_state.price_precision}f}"])
                            if self.sms_notifier.is_enabled:
                                self.sms_notifier.send_trade_alert(side, self.config.SYMBOL, float(filled_price), float(stopLoss or Decimal('0')), float(takeProfit or Decimal('0')), "Order Filled")
                            return filled_order # Return the filled order details
                        elif order_status in ('New', 'Created'):
                            self.logger.debug(f"Order {order_id} still pending, status: {order_status}. Retrying...")
                        else: # Cancelled, Rejected, etc.
                            self.logger.error(Fore.RED + f"Order {order_id} not filled, final status: {order_status}. Manual intervention may be required." + Style.RESET_ALL)
                            subprocess.run(["termux-toast", f"Order NOT FILLED: {self.config.SYMBOL} (ID: {order_id})"])
                            if self.sms_notifier.is_enabled:
                                self.sms_notifier.send_sms(f"CRITICAL: Order {order_id} for {self.config.SYMBOL} NOT FILLED! Status: {order_status}.")
                            # Attempt to cancel if it's still open and not filled
                            self.cancel_order(order_id)
                            return None
                    else:
                        self.logger.debug(f"No order history for {order_id} yet. Retrying...")
                
                self.logger.error(Fore.RED + f"Order {order_id} not confirmed filled after {max_retries} retries. Manual check needed." + Style.RESET_ALL)
                subprocess.run(["termux-toast", f"Order NOT FILLED: {self.config.SYMBOL} (ID: {order_id})"])
                if self.sms_notifier.is_enabled:
                    self.sms_notifier.send_sms(f"CRITICAL: Order {order_id} for {self.config.SYMBOL} NOT FILLED after retries.")
                return None
            else:
                self.logger.error(Fore.RED + f"Order placement failed: API call returned no order ID or data for {self.config.SYMBOL}." + Style.RESET_ALL)
                if self.sms_notifier.is_enabled:
                    self.sms_notifier.send_sms(f"Order placement failed for {self.config.SYMBOL}: No order ID returned.")
                return None
        except Exception as e:
            self.logger.error(Fore.RED + f"An unforeseen exception occurred during order placement for {self.config.SYMBOL}: {e}" + Style.RESET_ALL)
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"Order exception for {self.config.SYMBOL}: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific open order."""
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot cancel order {order_id} for {self.config.SYMBOL}: Specs not found.")
            return False

        if self.config.DRY_RUN:
            self.logger.info(Fore.YELLOW + f"[DRY RUN] Would cancel order {order_id} for {self.config.SYMBOL}." + Style.RESET_ALL)
            self.open_orders.pop(order_id, None) # Simulate removal
            # FEATURE: Retracement Entry Management
            if self.pending_retracement_order and self.pending_retracement_order['orderId'] == order_id:
                self.pending_retracement_order = None # Clear pending order
            return True

        try:
            self.logger.debug(f"Attempting to cancel order {order_id} for {self.config.SYMBOL}...")
            response_data = self.api_call(
                self.bybit_client.cancel_order,
                category=specs.category,
                symbol=self.config.SYMBOL,
                orderId=order_id
            )

            if response_data is not None:
                self.logger.info(f"Order {order_id} cancelled successfully for {self.config.SYMBOL}.")
                self.open_orders.pop(order_id, None)
                # FEATURE: Retracement Entry Management
                if self.pending_retracement_order and self.pending_retracement_order['orderId'] == order_id:
                    self.pending_retracement_order = None # Clear pending order
                return True
            else:
                self.logger.error(f"Failed to cancel order {order_id} for {self.config.SYMBOL}: API call wrapper returned None.")
                return False

        except Exception as e:
            self.logger.error(f"Exception cancelling order {order_id} for {self.config.SYMBOL}: {e}", exc_info=True)
            return False

    def cancel_all_orders(self) -> bool:
        """Cancel all open orders for the configured symbol."""
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot cancel all orders for {self.config.SYMBOL}: Specs not found.")
            return False

        if self.config.DRY_RUN:
            self.logger.info(Fore.YELLOW + f"[DRY RUN] Would cancel all open orders for {self.config.SYMBOL}." + Style.RESET_ALL)
            self.open_orders.clear()
            self.pending_retracement_order = None # Clear any pending retracement order
            return True

        try:
            self.logger.info(f"Attempting to cancel all open orders for {self.config.SYMBOL}...")
            response_data = self.api_call(
                self.bybit_client.cancel_all_orders,
                category=specs.category,
                symbol=self.config.SYMBOL
            )

            if response_data is not None:
                self.logger.info(f"All open orders successfully cancelled for {self.config.SYMBOL}.")
                self.open_orders.clear()
                self.pending_retracement_order = None # Clear any pending retracement order
                return True
            else:
                self.logger.error(f"Failed to cancel all orders for {self.config.SYMBOL}: API call wrapper returned None.")
                return False

        except Exception as e:
            self.logger.error(f"Exception cancelling all orders for {self.config.SYMBOL}: {e}", exc_info=True)
            return False

    def fetch_open_orders(self):
        """Fetch open orders from exchange to sync local state."""
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot fetch open orders for {self.config.SYMBOL}: Specs not found.")
            return

        try:
            self.logger.debug(f"Fetching open orders for {self.config.SYMBOL}...")
            # If using retracement entry, we need to fetch specific order status
            if self.pending_retracement_order:
                order_id = self.pending_retracement_order['orderId']
                response_data = self.api_call(
                    self.bybit_client.get_open_orders,
                    category=specs.category,
                    symbol=self.config.SYMBOL,
                    orderId=order_id
                )
            else: # Fetch all open orders for the symbol
                response_data = self.api_call(
                    self.bybit_client.get_open_orders,
                    category=specs.category,
                    symbol=self.config.SYMBOL
                )
            
            if response_data is not None:
                orders = response_data.get('list', [])
                self.open_orders.clear()
                for order in orders:
                    self.open_orders[order['orderId']] = order
                self.logger.debug(f"Fetched {len(orders)} open orders for {self.config.SYMBOL}.")
            else:
                self.logger.error(f"Failed to fetch open orders for {self.config.SYMBOL}: API call wrapper returned None.")
        except Exception as e:
            self.logger.error(f"Exception fetching open orders for {self.config.SYMBOL}: {e}", exc_info=True)


    # =====================================================================
    # POSITION MANAGEMENT
    # =====================================================================

    def get_positions(self) -> Optional[Dict[str, Any]]:
        """
        Fetch and update current positions for the configured symbol.
        Also updates BotState with position details.
        
        FEATURE: Max Concurrent Positions Limit
        This method now fetches *all* active positions across the account
        to support the global concurrent positions limit.
        """
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot get positions for {self.config.SYMBOL}: Specs not found.")
            return None

        # --- Fetch ALL positions for the category ---
        try:
            self.logger.debug(f"Fetching ALL positions for category {self.config.CATEGORY_ENUM.value}...")
            response_data = self.api_call(
                self.bybit_client.get_positions,
                category=specs.category,
                symbol=None # Fetch all symbols in category
            )

            if response_data is not None:
                positions_list = response_data.get('list', [])
                self.all_open_positions.clear() # Reset all_open_positions
                
                # Filter for positions with actual size > 0 and store them
                for pos in positions_list:
                    if Decimal(pos.get('size', '0')) > Decimal('0'):
                        self.all_open_positions[pos['symbol']] = pos
                
                self.logger.debug(f"Fetched {len(self.all_open_positions)} active positions across all symbols.")

                # --- Update state for the SPECIFIC symbol this bot instance manages ---
                position_for_current_symbol = self.all_open_positions.get(self.config.SYMBOL)

                if position_for_current_symbol:
                    # Initialize breakeven/partial TP status if it's a new position
                    if not self.position_active:
                        self.breakeven_activated[self.config.SYMBOL] = False
                        self.partial_tp_targets_hit[self.config.SYMBOL] = {i: False for i in range(len(self.config.PARTIAL_TP_TARGETS))}
                        self.initial_position_qty = Decimal(position_for_current_symbol['size'])

                    self.position_active = True
                    self.current_position_side = position_for_current_symbol['side']
                    self.current_position_entry_price = Decimal(position_for_current_symbol.get('avgPrice', '0'))
                    self.current_position_size = Decimal(position_for_current_symbol['size'])

                    # Update BotState position info
                    with self.bot_state.lock:
                        self.bot_state.open_position_qty = Decimal(position_for_current_symbol['size'])
                        self.bot_state.open_position_side = position_for_current_symbol['side']
                        self.bot_state.open_position_entry_price = Decimal(position_for_current_symbol['avgPrice'])
                        # Unrealized PnL from position data is for last mark price, can be used for UI
                        self.bot_state.unrealized_pnl = Decimal(position_for_current_symbol.get('unrealisedPnl', '0.0'))
                        pos_value = Decimal(position_for_current_symbol['size']) * Decimal(position_for_current_symbol.get('markPrice', '0'))
                        if pos_value > Decimal('0'):
                            self.bot_state.unrealized_pnl_pct = (self.bot_state.unrealized_pnl / pos_value) * Decimal('100')
                        else:
                            self.bot_state.unrealized_pnl_pct = Decimal('0.0')

                    # Initialize/Update trailing stop if active
                    if self.config.TRAILING_STOP_PCT > 0:
                        current_mark_price = Decimal(position_for_current_symbol.get('markPrice', '0'))
                        if current_mark_price > Decimal('0'):
                            self.trailing_stop_manager.initialize_trailing_stop(
                                symbol=self.config.SYMBOL,
                                position_side=position_for_current_symbol['side'],
                                entry_price=self.current_position_entry_price,
                                current_price=current_mark_price,
                                trail_percent=self.config.TRAILING_STOP_PCT * 100, # Convert to percentage for callbackRate
                                activation_percent=self.config.TRAILING_STOP_PCT * 100 # Can be same as trail
                            )
                        else:
                            self.logger.warning(f"Mark price not available for {self.config.SYMBOL} position, cannot initialize/update trailing stop.")
                else: # No position for the current symbol
                    if self.position_active:
                        self.logger.info(f"Position for {self.config.SYMBOL} was closed.")
                    self.position_active = False
                    self.current_position_side = None
                    self.current_position_entry_price = Decimal('0')
                    self.current_position_size = Decimal('0')
                    self.all_open_positions.pop(self.config.SYMBOL, None)
                    self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)
                    self.breakeven_activated.pop(self.config.SYMBOL, None) # Clear breakeven status
                    self.partial_tp_targets_hit.pop(self.config.SYMBOL, None) # Clear partial TP status
                    self.initial_position_qty = Decimal('0.0')

                    # Clear BotState position info
                    with self.bot_state.lock:
                        self.bot_state.open_position_qty = Decimal('0.0')
                        self.bot_state.open_position_side = "NONE"
                        self.bot_state.open_position_entry_price = Decimal('0.0')
                        self.bot_state.unrealized_pnl = Decimal('0.0')
                        self.bot_state.unrealized_pnl_pct = Decimal('0.0')

                self.logger.debug(f"Position status update for {self.config.SYMBOL}: Active={self.position_active}, Side={self.current_position_side}, Size={self.current_position_size}, Entry={self.current_position_entry_price}")
                return position_for_current_symbol # Return the specific position data

            else:
                self.logger.error(f"Failed to get positions for {self.config.SYMBOL}: API call wrapper returned None.")
                # Clear all position related states on API failure
                self.position_active = False
                self.current_position_side = None
                self.current_position_entry_price = Decimal('0')
                self.current_position_size = Decimal('0')
                self.all_open_positions.clear()
                self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)
                self.breakeven_activated.pop(self.config.SYMBOL, None)
                self.partial_tp_targets_hit.pop(self.config.SYMBOL, None)
                self.initial_position_qty = Decimal('0.0')
                with self.bot_state.lock: # Also clear BotState on API failure
                        self.bot_state.open_position_qty = Decimal('0.0')
                        self.bot_state.open_position_side = "NONE"
                        self.bot_state.open_position_entry_price = Decimal('0.0')
                        self.bot_state.unrealized_pnl = Decimal('0.0')
                        self.bot_state.unrealized_pnl_pct = Decimal('0.0')
                return None

        except Exception as e:
            self.logger.error(f"Exception getting positions for {self.config.SYMBOL}: {e}", exc_info=True)
            # Clear all position related states on error
            self.position_active = False
            self.current_position_side = None
            self.current_position_entry_price = Decimal('0')
            self.current_position_size = Decimal('0')
            self.all_open_positions.clear()
            self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)
            self.breakeven_activated.pop(self.config.SYMBOL, None)
            self.partial_tp_targets_hit.pop(self.config.SYMBOL, None)
            self.initial_position_qty = Decimal('0.0')
            with self.bot_state.lock: # Also clear BotState on error
                self.bot_state.open_position_qty = Decimal('0.0')
                self.bot_state.open_position_side = "NONE"
                self.bot_state.open_position_entry_price = Decimal('0.0')
                self.bot_state.unrealized_pnl = Decimal('0.0')
                self.bot_state.unrealized_pnl_pct = Decimal('0.0')
            return None


    def close_position(self, qty_to_close: Optional[Decimal] = None) -> bool:
        """
        Closes the currently open position, gracefully retreating from the market.
        Updates cumulative_pnl and bot_state.
        Can be called with a specific quantity for partial closes.
        """
        current_pos = self.all_open_positions.get(self.config.SYMBOL) # Get the specific position
        if not current_pos or Decimal(current_pos['size']) == Decimal('0'):
            self.logger.warning(Fore.YELLOW + "No active position to close." + Style.RESET_ALL)
            return False
        
        side_to_close = 'Sell' if current_pos['side'] == 'Buy' else 'Buy'
        
        # If qty_to_close is not specified, close the full position
        if qty_to_close is None:
            qty_to_close = self.precision_manager.round_quantity(self.config.SYMBOL, Decimal(current_pos['size']))
            # is_partial_close = False # Not used, but kept for context
        else:
            qty_to_close = self.precision_manager.round_quantity(self.config.SYMBOL, qty_to_close)
            # is_partial_close = True # Not used, but kept for context

        if qty_to_close <= Decimal('0'):
            self.logger.warning(f"Quantity to close is zero or negative ({qty_to_close}). Aborting close operation.")
            return False

        if self.config.DRY_RUN:
            pnl_realized = Decimal(current_pos.get('unrealisedPnl', '0.0')) * (qty_to_close / Decimal(current_pos['size'])) # Simulate PnL for closed portion
            self.cumulative_pnl += pnl_realized
            self.logger.info(Fore.YELLOW + f"[DRY RUN] Would close {qty_to_close:.{self.bot_state.qty_precision}f} of {current_pos['side']} position of {self.config.SYMBOL}. Simulated PnL: ${pnl_realized:.2f}" + Style.RESET_ALL)
            self.sms_notifier.send_sms(f"DRY RUN: Close {qty_to_close:.{self.bot_state.qty_precision}f} {current_pos['side']} {self.config.SYMBOL}. Simulated PnL: ${pnl_realized:.2f}")
            
            # Simulate updating internal position state and BotState
            remaining_qty = Decimal(current_pos['size']) - qty_to_close
            if remaining_qty <= Decimal('0'):
                self.position_active = False
                self.current_position_side = None
                self.current_position_entry_price = Decimal('0')
                self.current_position_size = Decimal('0')
                self.all_open_positions.pop(self.config.SYMBOL, None)
                self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)
                self.breakeven_activated.pop(self.config.SYMBOL, None)
                self.partial_tp_targets_hit.pop(self.config.SYMBOL, None)
                self.initial_position_qty = Decimal('0.0')
                with self.bot_state.lock:
                    self.bot_state.realized_pnl_total = self.cumulative_pnl
                    self.bot_state.open_position_qty = Decimal('0.0')
                    self.bot_state.open_position_side = "NONE"
                    self.bot_state.open_position_entry_price = Decimal('0.0')
                    self.bot_state.unrealized_pnl = Decimal('0.0')
                    self.bot_state.unrealized_pnl_pct = Decimal('0.0')
            else:
                self.current_position_size = remaining_qty
                self.all_open_positions[self.config.SYMBOL]['size'] = str(remaining_qty) # Update mock position
                with self.bot_state.lock:
                    self.bot_state.realized_pnl_total = self.cumulative_pnl
                    self.bot_state.open_position_qty = remaining_qty
                    # PnL will be updated by _update_market_data_and_state
            return True

        try:
            self.logger.info(f"Attempting to close {qty_to_close} of {current_pos['side']} position for {self.config.SYMBOL}...")
            
            close_order_data = self.place_order( # Use place_order for closing to leverage its verification logic
                side=side_to_close,
                qty=qty_to_close,
                order_type=OrderType.MARKET,
                reduce_only=True
            )
            
            if close_order_data: # place_order returns filled order data on success
                # For realized PnL, Bybit's get_positions gives unrealisedPnl.
                # When a position is closed, this becomes realized.
                # Here, we use the unrealized PnL from `current_pos` as a proxy for realized PnL upon closure.
                pnl_realized = Decimal(current_pos.get('unrealisedPnl', '0.0')) * (qty_to_close / Decimal(current_pos['size']))
                self.cumulative_pnl += pnl_realized
                
                self.logger.info(Fore.MAGENTA + f"✅ Position Closed: {qty_to_close:.{self.bot_state.qty_precision}f} of {current_pos['side']} {self.config.SYMBOL} | PnL: ${pnl_realized:.{self.bot_state.price_precision}f}" + Style.RESET_ALL)
                subprocess.run(["termux-toast", f"Position Closed: {self.config.SYMBOL}. PnL: {pnl_realized:.{self.bot_state.price_precision}f}"])
                
                current_equity = self.get_account_balance_usdt() # Refresh equity for notification
                if self.sms_notifier.is_enabled:
                    self.sms_notifier.send_pnl_update(float(pnl_realized), float(current_equity))
                
                # Update internal position state. Call get_positions to fully sync.
                self.get_positions() # This will update self.position_active, self.current_position_size etc.

                # Update BotState with realized PnL
                with self.bot_state.lock:
                    self.bot_state.realized_pnl_total = self.cumulative_pnl
                return True
            else:
                self.logger.error(Fore.RED + f"Failed to place market order to close position for {self.config.SYMBOL}.")
                return False
        except Exception as e:
            self.logger.error(Fore.RED + f"An unforeseen exception occurred during position closure for {self.config.SYMBOL}: {e}" + Style.RESET_ALL)
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"Close order exception for {self.config.SYMBOL}: {e}")
            return False


    # =====================================================================
    # MAIN EXECUTION LOGIC
    # =====================================================================

    def _is_time_to_trade(self) -> bool:
        """FEATURE: Time-Based Trading Window check."""
        if not self.config.TIME_WINDOW_ENABLED:
            return True # If disabled, always allow

        now_utc = datetime.now(dateutil.tz.UTC)
        current_hour_utc = now_utc.hour
        current_weekday = now_utc.strftime('%A') # e.g., "Monday"

        if current_weekday not in self.config.TRADE_DAYS_OF_WEEK:
            self.logger.info(f"Trading is disabled on {current_weekday}.")
            return False

        if not (self.config.TRADE_START_HOUR_UTC <= current_hour_utc < self.config.TRADE_END_HOUR_UTC):
            self.logger.info(f"Trading is outside allowed hours ({self.config.TRADE_START_HOUR_UTC}-{self.config.TRADE_END_HOUR_UTC} UTC). Current hour: {current_hour_utc} UTC.")
            return False
        
        return True

    def _is_funding_rate_avoidance_active(self) -> bool:
        """FEATURE: Funding Rate Avoidance (Perpetuals)."""
        if not self.config.FUNDING_RATE_AVOIDANCE_ENABLED or self.config.CATEGORY_ENUM != Category.LINEAR:
            return False

        try:
            ticker_data = self.api_call(self.bybit_client.get_tickers, symbol=self.config.SYMBOL, category=self.config.CATEGORY_ENUM.value)
            if ticker_data and ticker_data.get('list'):
                ticker_info = ticker_data['list'][0]
                funding_rate = Decimal(ticker_info.get('fundingRate', '0'))
                next_funding_time_ms = int(ticker_info.get('nextFundingTime', '0'))

                if next_funding_time_ms == 0:
                    self.logger.warning("nextFundingTime not available. Skipping funding rate avoidance.")
                    return False

                next_funding_dt = datetime.fromtimestamp(next_funding_time_ms / 1000, tz=dateutil.tz.UTC)
                time_until_funding = next_funding_dt - datetime.now(dateutil.tz.UTC)
                
                if abs(funding_rate) >= Decimal(str(self.config.FUNDING_RATE_THRESHOLD_PCT)):
                    if time_until_funding <= timedelta(minutes=self.config.FUNDING_GRACE_PERIOD_MINUTES) and time_until_funding > timedelta(seconds=0):
                        self.logger.warning(Fore.YELLOW + f"Funding rate avoidance active: Funding rate {funding_rate*100:.4f}% is high and funding payment is in {time_until_funding}. Avoiding new trades." + Style.RESET_ALL)
                        return True
        except Exception as e:
            self.logger.error(f"Error checking funding rate: {e}", exc_info=True)
        return False

    def _manage_retracement_order(self, current_kline_ts: int):
        """FEATURE: Signal Retracement Entry - monitoring and cancellation."""
        if not self.config.RETRACEMENT_ENTRY_ENABLED or self.pending_retracement_order is None:
            return

        order_id = self.pending_retracement_order['orderId']
        time_placed_kline_ts = self.pending_retracement_order['time_placed_kline_ts']
        
        # Check if the order is still open or has been filled
        self.fetch_open_orders() # Refresh self.open_orders
        
        if order_id not in self.open_orders:
            # Order is no longer open, likely filled or cancelled by exchange/user
            self.logger.info(f"Pending retracement order {order_id} is no longer open. Assuming filled or externally cancelled.")
            self.pending_retracement_order = None
            return # Let the next cycle check for new position

        # Check if max wait time exceeded
        current_kline_count = (current_kline_ts - time_placed_kline_ts) / (self._get_timeframe_in_ms() / 1000)
        if current_kline_count >= self.config.RETRACEMENT_CANDLE_WAIT:
            self.logger.warning(f"Retracement limit order {order_id} not filled within {self.config.RETRACEMENT_CANDLE_WAIT} candles. Cancelling.")
            self.cancel_order(order_id)
            self.pending_retracement_order = None
            self.last_trade_time = time.time() # Apply cooldown after failed retracement
            return

        self.logger.debug(f"Retracement order {order_id} still pending (Candle {current_kline_count}/{self.config.RETRACEMENT_CANDLE_WAIT}).")

    def _get_timeframe_in_ms(self) -> int:
        """Helper to convert timeframe string to milliseconds."""
        tf = self.config.TIMEFRAME
        if tf.endswith('D'):
            return 24 * 60 * 60 * 1000
        if tf.endswith('W'):
            return 7 * 24 * 60 * 60 * 1000
        if tf.endswith('M'):
            return 30 * 24 * 60 * 60 * 1000 # Approx month
        return int(tf) * 60 * 1000 # Minutes to milliseconds

    def _manage_breakeven_stop_loss(self):
        """FEATURE: Breakeven Stop Loss Activation."""
        if not self.config.BREAKEVEN_ENABLED or not self.position_active:
            return

        symbol = self.config.SYMBOL
        if self.breakeven_activated.get(symbol, False):
            return # Breakeven already activated for this position

        current_pos = self.all_open_positions.get(symbol)
        if not current_pos:
            return

        current_unrealized_pnl_pct = self.bot_state.unrealized_pnl_pct # From BotState, already updated
        
        if current_unrealized_pnl_pct >= Decimal(str(self.config.BREAKEVEN_PROFIT_TRIGGER_PCT)) * Decimal('100'):
            entry_price = self.current_position_entry_price
            breakeven_sl = Decimal('0')
            if self.current_position_side == 'Buy':
                breakeven_sl = entry_price + entry_price * Decimal(str(self.config.BREAKEVEN_OFFSET_PCT))
            else: # Sell
                breakeven_sl = entry_price - entry_price * Decimal(str(self.config.BREAKEVEN_OFFSET_PCT))
            
            breakeven_sl = self.precision_manager.round_price(symbol, breakeven_sl)

            # Check if current SL is already better than breakeven_sl
            current_sl_from_exchange = Decimal(current_pos.get('stopLoss', '0'))
            if current_sl_from_exchange > Decimal('0'): # If an SL is already set
                if (self.current_position_side == 'Buy' and current_sl_from_exchange >= breakeven_sl) or \
                   (self.current_position_side == 'Sell' and current_sl_from_exchange <= breakeven_sl):
                    self.logger.debug(f"Breakeven SL ({breakeven_sl:.{self.bot_state.price_precision}f}) not better than existing SL ({current_sl_from_exchange:.{self.bot_state.price_precision}f}). No update needed.")
                    self.breakeven_activated[symbol] = True # Consider it activated if current SL is already at or past breakeven
                    return

            self.logger.info(Fore.YELLOW + f"Breakeven activated for {symbol}: PnL {current_unrealized_pnl_pct:.2f}% >= {self.config.BREAKEVEN_PROFIT_TRIGGER_PCT*100:.2f}%. Setting SL to {breakeven_sl:.{self.bot_state.price_precision}f}." + Style.RESET_ALL)
            
            try:
                self.api_call(
                    self.bybit_client.set_trading_stop,
                    category=self.config.CATEGORY_ENUM.value,
                    symbol=symbol,
                    side=self.current_position_side,
                    stopLoss=str(breakeven_sl),
                    tpslMode='Partial' # Allow other TP/TS to remain
                )
                self.breakeven_activated[symbol] = True
            except Exception as e:
                self.logger.error(f"Failed to set breakeven SL for {symbol}: {e}", exc_info=True)

    def _manage_partial_take_profit(self):
        """FEATURE: Partial Take Profit (Scaling Out)."""
        if not self.config.PARTIAL_TP_ENABLED or not self.position_active:
            return

        symbol = self.config.SYMBOL
        current_pos = self.all_open_positions.get(symbol)
        if not current_pos or self.initial_position_qty <= Decimal('0'):
            return

        current_unrealized_pnl_pct = self.bot_state.unrealized_pnl_pct
        
        for i, target in enumerate(self.config.PARTIAL_TP_TARGETS):
            if not self.partial_tp_targets_hit.get(symbol, {}).get(i, False): # If this target hasn't been hit yet
                if current_unrealized_pnl_pct >= Decimal(str(target['profit_pct'])) * Decimal('100'):
                    qty_to_close = self.initial_position_qty * Decimal(str(target['close_qty_pct']))
                    
                    # Ensure we don't try to close more than currently open
                    current_remaining_qty = Decimal(current_pos['size'])
                    qty_to_close = min(qty_to_close, current_remaining_qty)
                    
                    if qty_to_close > Decimal('0'):
                        self.logger.info(Fore.YELLOW + f"Partial TP hit for {symbol} (Target {i+1}): PnL {current_unrealized_pnl_pct:.2f}% >= {target['profit_pct']*100:.2f}%. Closing {qty_to_close:.{self.bot_state.qty_precision}f} ({(target['close_qty_pct']*100):.1f}% of initial)." + Style.RESET_ALL)
                        if self.close_position(qty_to_close=qty_to_close):
                            # Mark this target as hit
                            if symbol not in self.partial_tp_targets_hit:
                                self.partial_tp_targets_hit[symbol] = {}
                            self.partial_tp_targets_hit[symbol][i] = True
                            # After a partial close, `get_positions` will update `self.current_position_size` and `all_open_positions`
                            # which is crucial for subsequent partial TP calculations.
                            self.last_trade_time = time.time() # Apply cooldown
                        else:
                            self.logger.error(f"Failed to execute partial TP for {symbol} (Target {i+1}).")
                    else:
                        self.logger.info(f"Partial TP target {i+1} met, but calculated quantity to close is zero or less than current remaining quantity. Skipping.")
            
    def execute_trade_based_on_signal(self, signal_type: Optional[str], reason: str):
        """
        Execute trades based on the generated signal and current position state.
        Manages opening new positions, closing existing ones based on signal reversal,
        and updating stop losses (including trailing stops).
        
        Includes checks for:
        - Cumulative Loss Guard
        - Time-Based Trading Window
        - Max Concurrent Positions Limit
        - Funding Rate Avoidance
        - News Event Trading Pause
        - Signal Retracement Entry (initial placement)
        - Breakeven Stop Loss (monitoring)
        - Partial Take Profit (monitoring)
        """
        # Global checks before any trade action
        if not self._cumulative_loss_guard():
            self.logger.warning("Cumulative loss limit reached. Skipping trade execution for this cycle.")
            return
        
        if not self._is_time_to_trade():
            self.logger.info("Outside allowed trading window. Skipping trade execution for this cycle.")
            return

        if self.config.NEWS_PAUSE_ENABLED:
            paused, pause_reason = self.news_calendar_manager.is_trading_paused()
            if paused:
                self.logger.info(f"Trading paused: {pause_reason}")
                return # Skip all trading actions

        # Fetch current market data (ticker for price)
        current_market_price = Decimal(str(self.market_data['close'].iloc[-1])) if not self.market_data.empty else Decimal('0.0')
        if current_market_price <= Decimal('0'):
            self.logger.warning("Could not retrieve current market price from kline data. Cannot execute trade based on signal.")
            return

        # Ensure we have valid instrument specifications for precision rounding
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Instrument specifications not found for {self.config.SYMBOL}. Cannot execute trade.")
            return

        # --- Trade Cooldown Check ---
        now_ts = time.time()
        if now_ts - self.last_trade_time < self.config.SIGNAL_COOLDOWN_SEC:
            self.logger.info(Fore.LIGHTBLACK_EX + f"Trade cooldown active ({self.config.SIGNAL_COOLDOWN_SEC}s). Skipping trade execution." + Style.RESET_ALL)
            return

        # --- Manage pending retracement orders ---
        # This handles cancelling old orders, actual fill is handled in `_process_websocket_message`
        self._manage_retracement_order(self.last_kline_ts)
        # If there's a pending retracement order, don't try to open new positions
        if self.pending_retracement_order:
            self.logger.info(f"A retracement order is pending. Not opening new positions until it's filled or cancelled.")
            return

        # --- State Management & Trade Execution ---
        latest_st_direction = self.market_data['supertrend_direction'].iloc[-1]

        # 1. Handle Closing Existing Positions on Reversal
        if self.position_active:
            perform_close = False
            if self.current_position_side == "Buy" and latest_st_direction == -1:
                self.logger.info(f"Exit Signal: Supertrend flipped DOWN while in a LONG position. Closing position.")
                perform_close = True
            elif self.current_position_side == "Sell" and latest_st_direction == 1:
                self.logger.info(f"Exit Signal: Supertrend flipped UP while in a SHORT position. Closing position.")
                perform_close = True
            
            if perform_close:
                if self.close_position():
                    self.last_trade_time = now_ts
                return # Exit after closing, wait for next candle

        # 2. Handle Opening New Positions
        if not self.position_active and signal_type in ['BUY', 'SELL']:
            # FEATURE: Max Concurrent Positions Limit Check
            if len(self.all_open_positions) >= self.config.MAX_CONCURRENT_POSITIONS:
                self.logger.warning(f"Max concurrent positions limit ({self.config.MAX_CONCURRENT_POSITIONS}) reached. Cannot open new position for {self.config.SYMBOL}.")
                return
            
            # FEATURE: Funding Rate Avoidance (Perpetuals)
            if self._is_funding_rate_avoidance_active():
                self.logger.warning("Funding rate avoidance active. Skipping new position opening.")
                return

            trade_side = signal_type
            self.logger.info(f"Received {trade_side} signal. Reason: {reason}. Attempting to open {trade_side.lower()} position.")
            subprocess.run(["termux-toast", f"Signal: {trade_side} {self.config.SYMBOL}. Reason: {reason}"])

            # Calculate Stop Loss and Take Profit prices (with DTP)
            stop_loss_price, take_profit_price = self.calculate_trade_sl_tp(trade_side, current_market_price, self.market_data)

            # FEATURE: Volatility-Adjusted Position Sizing - pass current ATR
            current_atr_for_sizing = Decimal(str(self.market_data['atr'].iloc[-1])) if 'atr' in self.market_data.columns else None

            # Calculate position size in base currency units
            position_qty = self.order_sizer.calculate_position_size_usd(
                symbol=self.config.SYMBOL,
                account_balance_usdt=self.account_balance_usdt,
                risk_percent=Decimal(str(self.config.RISK_PER_TRADE_PCT / 100)),
                entry_price=current_market_price,
                stop_loss_price=stop_loss_price,
                leverage=Decimal(str(self.config.LEVERAGE)),
                current_atr=current_atr_for_sizing # Pass ATR
            )

            if position_qty is not None and position_qty > Decimal('0'):
                order_type_to_place = self.config.ORDER_TYPE_ENUM
                entry_price_to_place = current_market_price # Default for market or if retracement not enabled
                
                # FEATURE: Signal Retracement Entry
                if self.config.RETRACEMENT_ENTRY_ENABLED:
                    order_type_to_place = OrderType[self.config.RETRACEMENT_ORDER_TYPE.upper()]
                    if trade_side == 'Buy':
                        entry_price_to_place = current_market_price * (Decimal('1') - Decimal(str(self.config.RETRACEMENT_PCT_FROM_CLOSE)))
                    else: # Sell
                        entry_price_to_place = current_market_price * (Decimal('1') + Decimal(str(self.config.RETRACEMENT_PCT_FROM_CLOSE)))
                    
                    entry_price_to_place = self.precision_manager.round_price(self.config.SYMBOL, entry_price_to_place)
                    self.logger.info(f"Placing {order_type_to_place.value} order for retracement at {entry_price_to_place:.{self.bot_state.price_precision}f}.")
                
                order_result = self.place_order(
                    side=trade_side,
                    qty=position_qty,
                    order_type=order_type_to_place,
                    entry_price=entry_price_to_place if order_type_to_place == OrderType.LIMIT else None, # Only pass price for limit orders
                    stopLoss=stop_loss_price,
                    takeProfit=take_profit_price
                )

                if order_result:
                    if order_result.get('orderStatus') == 'Filled' or self.config.DRY_RUN:
                        # Update internal state based on order result (especially the filled price)
                        filled_price = Decimal(order_result.get('avgPrice', str(current_market_price)))
                        filled_qty = Decimal(order_result.get('cumExecQty', str(position_qty)))

                        self.position_active = True
                        self.current_position_side = trade_side
                        self.current_position_entry_price = filled_price
                        self.current_position_size = filled_qty
                        self.initial_position_qty = filled_qty # Store initial quantity for partial TP
                        self.last_trade_time = now_ts
                        self.last_signal = trade_side
                        self.breakeven_activated[self.config.SYMBOL] = False # Reset breakeven status for new position
                        self.partial_tp_targets_hit[self.config.SYMBOL] = {i: False for i in range(len(self.config.PARTIAL_TP_TARGETS))} # Reset partial TP status
                        self.pending_retracement_order = None # Clear pending retracement order

                        self.logger.info(f"{trade_side} order placed and confirmed filled. Entry: {filled_price}, Qty: {filled_qty}.")
                        
                        # Update BotState with new position
                        with self.bot_state.lock:
                            self.bot_state.open_position_qty = filled_qty
                            self.bot_state.open_position_side = trade_side
                            self.bot_state.open_position_entry_price = filled_price
                            self.bot_state.unrealized_pnl = Decimal('0.0') # Start with 0 PnL
                            self.bot_state.unrealized_pnl_pct = Decimal('0.0')
                    elif order_result.get('orderStatus') in ('New', 'Created') and self.config.RETRACEMENT_ENTRY_ENABLED:
                        # If retracement order is pending, store its details
                        self.pending_retracement_order = {
                            'orderId': order_result['orderId'],
                            'side': trade_side,
                            'qty': position_qty,
                            'price': entry_price_to_place,
                            'time_placed_kline_ts': self.last_kline_ts
                        }
                        self.logger.info(f"Retracement limit order {order_result['orderId']} placed and pending fill.")
                    else:
                        self.logger.error(f"Failed to place {trade_side} order.")
                else:
                    self.logger.error(f"Failed to place {trade_side} order.")
            else:
                self.logger.warning(f"Could not calculate a valid position size for the {trade_side} signal. Skipping order placement.")

        # 3. Handle Managing Existing Positions (Signal Reversal or just monitoring)
        elif self.position_active:
            perform_close = False
            if self.current_position_side == "Buy" and signal_type == 'SELL':
                self.logger.info(f"Signal reversal to SELL detected while in BUY position. Closing position. Reason: {reason}")
                perform_close = True
            elif self.current_position_side == "Sell" and signal_type == 'BUY':
                self.logger.info(f"Signal reversal to BUY detected while in SELL position. Closing position. Reason: {reason}")
                perform_close = True

            if perform_close:
                if self.close_position():
                    self.logger.info(f"Position for {self.config.SYMBOL} closed successfully due to signal reversal.")
                    self.last_trade_time = now_ts
                    self.last_signal = signal_type # Update last signal after successful closure
                else:
                    self.logger.error(f"Failed to close position for {self.config.SYMBOL} on signal reversal.")

            # If not closing, apply other position management features
            if not perform_close:
                # FEATURE: Breakeven Stop Loss Activation
                self._manage_breakeven_stop_loss()
                
                # FEATURE: Partial Take Profit (Scaling Out)
                self._manage_partial_take_profit()

                # FEATURE: Trailing Stop Loss Updates (Dynamic Trailing)
                if self.config.TRAILING_STOP_PCT > 0 and specs.category != 'spot':
                    # `get_positions` already fetches markPrice and updates internal state for trailing stop manager
                    # So we just need to ensure the trailing stop is set/active.
                    self.trailing_stop_manager.update_trailing_stop(
                        symbol=self.config.SYMBOL,
                        current_price=current_market_price, # Pass latest market price
                        current_unrealized_pnl_pct=self.bot_state.unrealized_pnl_pct, # Pass for dynamic trailing
                        update_exchange=True
                    )
        else:
            self.logger.info(Fore.WHITE + "No active position and no new signal to act on." + Style.RESET_ALL)


    def connect_websocket(self):
        """
        Establishes and maintains a mystical WebSocket connection,
        listening for the whispers of new market candles, until a stop signal is received.
        """
        reconnect_attempts = 0
        max_reconnect_attempts = 10
        base_reconnect_delay = 5

        while not self.stop_event.is_set():
            try:
                self.logger.info(Fore.CYAN + "Attempting to forge WebSocket connection..." + Style.RESET_ALL)
                if self.ws:
                    try:
                        self.ws.exit()
                        self.logger.info(Fore.BLUE + "Previous WebSocket connection closed cleanly." + Style.RESET_ALL)
                    except Exception as e:
                        self.logger.warning(Fore.YELLOW + f"Error closing previous WebSocket: {e}" + Style.RESET_ALL)
                    self.ws = None

                self.ws = WebSocket(testnet=self.config.TESTNET, channel_type=self.config.CATEGORY_ENUM.value)
                self.ws.kline_stream(interval=self.config.TIMEFRAME, symbol=self.config.SYMBOL, callback=self._process_websocket_message)
                
                with self.bot_state.lock:
                    self.bot_state.bot_status = "Running" # Update UI status
                self.logger.info(Fore.GREEN + "WebSocket connected and streaming." + Style.RESET_ALL)
                reconnect_attempts = 0

                while not self.stop_event.is_set():
                    time.sleep(1) # Keep thread alive, check stop_event periodically

            except Exception as e:
                if self.stop_event.is_set():
                    break

                reconnect_attempts += 1
                if reconnect_attempts > max_reconnect_attempts:
                    self.logger.critical(Fore.RED + f"Max reconnect attempts ({max_reconnect_attempts}) reached. Stopping WebSocket thread." + Style.RESET_ALL)
                    self.stop_event.set() # Signal main thread and other threads to stop
                    break

                sleep_time = min(60, base_reconnect_delay * (2 ** (reconnect_attempts - 1)))
                sleep_time *= (1.0 + random.uniform(-0.2, 0.2))
                self.logger.error(Fore.RED + f"WebSocket error: {e}. Reconnecting attempt {reconnect_attempts}/{max_reconnect_attempts} in {sleep_time:.1f}s..." + Style.RESET_ALL)
                time.sleep(sleep_time)

        self.logger.info(Fore.BLUE + "WebSocket loop gracefully exited." + Style.RESET_ALL)

    def _update_market_data_and_state(self):
        """Fetches klines, calculates indicators, and updates BotState."""
        self.logger.info("Updating market data and indicators...")
        
        # Primary timeframe data
        self.market_data = self.fetch_klines(self.config.SYMBOL, self.config.TIMEFRAME, limit=self.config.LOOKBACK_PERIODS)
        if self.market_data.empty:
            self.logger.warning("Failed to retrieve primary market data for state update.")
            return
        self.market_data = self.calculate_indicators(self.market_data, is_higher_timeframe=False)
        if self.market_data.empty:
            self.logger.warning("Primary indicators could not be calculated. State not updated.")
            return

        # FEATURE: Multiple Timeframe Confluence Filter - higher timeframe data
        if self.config.MULTI_TIMEFRAME_CONFIRMATION_ENABLED:
            self.higher_timeframe_data = self.fetch_klines(self.config.SYMBOL, self.config.HIGHER_TIMEFRAME, limit=self.config.LOOKBACK_PERIODS)
            if self.higher_timeframe_data.empty:
                self.logger.warning("Failed to retrieve higher timeframe market data for MTF filter.")
            else:
                self.higher_timeframe_data = self.calculate_indicators(self.higher_timeframe_data, is_higher_timeframe=True)
                if self.higher_timeframe_data.empty:
                    self.logger.warning("Higher timeframe indicators could not be calculated for MTF filter.")

        bid_price_dec, ask_price_dec = self._get_current_orderbook()
        current_price_dec = Decimal(str(self.market_data['close'].iloc[-1]))

        with self.bot_state.lock:
            self.bot_state.last_updated_time = datetime.now()
            self.bot_state.current_price = current_price_dec
            self.bot_state.bid_price = bid_price_dec
            self.bot_state.ask_price = ask_price_dec
            
            latest_indicator_row = self.market_data.iloc[-1]

            # Ehlers SuperTrend
            self.bot_state.ehlers_supertrend_value = Decimal(str(latest_indicator_row.get('supertrend_line_value', '0.0')))
            direction_val = latest_indicator_row.get('supertrend_direction', 0)
            if direction_val == 1:
                self.bot_state.ehlers_supertrend_direction = "UP"
            elif direction_val == -1:
                self.bot_state.ehlers_supertrend_direction = "DOWN"
            else:
                self.bot_state.ehlers_supertrend_direction = "NONE"
            
            self.bot_state.ehlers_filter_value = Decimal(str(latest_indicator_row.get('ehlers_filter', '0.0')))

            # ADX
            adx_val = Decimal(str(latest_indicator_row.get('adx', '0.0')))
            self.bot_state.adx_value = adx_val
            if adx_val > Decimal('25'):
                self.bot_state.adx_trend_strength = "Strong"
            elif adx_val > Decimal('20'):
                self.bot_state.adx_trend_strength = "Developing"
            else:
                self.bot_state.adx_trend_strength = "Weak"
            self.bot_state.adx_plus_di = Decimal(str(latest_indicator_row.get('adx_plus_di', '0.0')))
            self.bot_state.adx_minus_di = Decimal(str(latest_indicator_row.get('adx_minus_di', '0.0')))
            
            # RSI
            rsi_val = Decimal(str(latest_indicator_row.get('rsi', '0.0')))
            self.bot_state.rsi_value = rsi_val
            if rsi_val > Decimal('70'):
                self.bot_state.rsi_state = "Overbought"
            elif rsi_val < Decimal('30'):
                self.bot_state.rsi_state = "Oversold"
            else:
                self.bot_state.rsi_state = "Neutral"

            # MACD
            self.bot_state.macd_value = Decimal(str(latest_indicator_row.get('macd', '0.0')))
            self.bot_state.macd_signal_value = Decimal(str(latest_indicator_row.get('macd_signal', '0.0')))
            self.bot_state.macd_diff_value = Decimal(str(latest_indicator_row.get('macd_diff', '0.0')))

            # Update PnL
            if self.bot_state.open_position_qty > Decimal('0') and current_price_dec > Decimal('0'):
                pos_size = self.bot_state.open_position_qty
                entry_price = self.bot_state.open_position_entry_price
                if pos_size > Decimal('0') and entry_price > Decimal('0'):
                    pnl_factor = Decimal('1') if self.bot_state.open_position_side == 'Buy' else Decimal('-1')
                    self.bot_state.unrealized_pnl = (current_price_dec - entry_price) * pos_size * pnl_factor
                    pos_value = entry_price * pos_size
                    if pos_value > Decimal('0'):
                        self.bot_state.unrealized_pnl_pct = (self.bot_state.unrealized_pnl / pos_value) * Decimal('100')
            else: # No open position for this symbol
                self.bot_state.unrealized_pnl = Decimal('0.0')
                self.bot_state.unrealized_pnl_pct = Decimal('0.0')


        self.logger.info("Market data and bot state updated successfully.")

    def _process_websocket_message(self, msg: Dict[str, Any]):
        """
        The core incantation, triggered by each new confirmed k-line,
        where market data is transformed into signals and actions.
        """
        if self.stop_event.is_set():
            return

        if "topic" in msg and str(msg["topic"]).startswith(f"kline.{self.config.TIMEFRAME}.{self.config.SYMBOL}"):
            kline = msg['data'][0]
            if not kline['confirm']:
                return # Only process confirmed (closed) candles

            ts = int(kline['start'])
            if ts <= self.last_kline_ts:
                return # Skip duplicate or old candle data
            self.last_kline_ts = ts

            self.logger.info(Fore.LIGHTMAGENTA_EX + f"--- New Confirmed Candle [{datetime.fromtimestamp(ts/1000)}] ---" + Style.RESET_ALL)

            # Update data and state
            self._update_market_data_and_state()

            # After updating, generate signal and execute trade
            if not self.market_data.empty:
                signal, reason = self.generate_signal(self.market_data)
                self.logger.info(Fore.WHITE + f"Signal: {signal or 'NONE'} | Reason: {reason}" + Style.RESET_ALL)
                self.get_positions() # Refresh position state before trading
                self.execute_trade_based_on_signal(signal, reason)


    def cleanup(self):
        """Perform cleanup actions before exiting the bot. Enhanced with optional auto-close."""
        self.logger.info("Starting bot cleanup process...")
        try:
            # Cancel all open orders to prevent unintended trades upon restart or shutdown
            self.logger.info("Cancelling all open orders...")
            self.cancel_all_orders()

            # Optionally close any open positions if configured
            if self.config.AUTO_CLOSE_ON_SHUTDOWN and self.position_active and self.current_position_size > Decimal('0'):
                self.logger.warning(f"Auto-close on shutdown enabled. Closing open position ({self.current_position_side} {self.current_position_size} {self.config.SYMBOL}).")
                self.close_position()
            else:
                self.logger.info("Auto-close on shutdown is disabled or no active position. Not closing positions.")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}", exc_info=True)
        finally:
            self.logger.info(Fore.LIGHTBLUE_EX + Style.BRIGHT + "Ehlers SuperTrend Bot has ceased its operations. Until next time!" + Style.RESET_ALL)
            subprocess.run(["termux-toast", f"Ehlers SuperTrend Bot for {self.config.SYMBOL} has ceased operations."])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"Ehlers SuperTrend Bot for {self.config.SYMBOL} has ceased operations.")

    def run(self):
        """
        Initiates the bot's grand operation, starting the WebSocket vigil
        and managing its continuous market engagement, with graceful shutdown.
        """
        self.logger.info(Fore.LIGHTYELLOW_EX + Style.BRIGHT + f"🚀 Launching Ehlers SuperTrend Bot for {self.config.SYMBOL}! May its journey be prosperous." + Style.RESET_ALL)
        subprocess.run(["termux-toast", f"Ehlers SuperTrend Bot for {self.config.SYMBOL} is commencing its arcane operations."])
        if self.sms_notifier.is_enabled:
            self.sms_notifier.send_sms(f"Ehlers SuperTrend Bot for {self.config.SYMBOL} is commencing its arcane operations.")

        self._install_signal_handlers() # Install signal handlers

        # --- Initial Data Load ---
        self._update_market_data_and_state()

        # Start BotUI thread
        ui_thread = BotUI(self.bot_state)
        ui_thread.start()

        # Start WebSocket connection in a separate thread
        ws_thread = threading.Thread(target=self.connect_websocket, daemon=True)
        ws_thread.start()

        # The main thread now simply waits for a stop event, keeping the bot running continuously
        self.logger.info(Fore.BLUE + "Bot now running continuously, awaiting stop signal (Ctrl+C)." + Style.RESET_ALL)
        self.stop_event.wait() # Block until stop_event is set (e.g., by signal handler)

        self.logger.info(Fore.BLUE + "Bot's main loop gracefully exited. Farewell, seeker." + Style.RESET_ALL)
        ui_thread.stop() # Signal UI thread to stop
        ui_thread.join(timeout=5) # Wait for UI thread to finish
        self.cleanup() # Perform cleanup after the main loop exit


# =====================================================================
# MAIN ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    # Load configuration
    config = Config()

    # Create and run the bot
    bot = EhlersSuperTrendBot(config)
    bot.run()

