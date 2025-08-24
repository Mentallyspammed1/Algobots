#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time
import pandas as pd
import numpy as np
from decimal import Decimal, ROUND_DOWN, InvalidOperation # Corrected import: import Decimal directly
import logging
import colorlog
import threading
import subprocess # For termux-toast and termux-sms-send
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket
from pybit.exceptions import FailedRequestError, InvalidRequestError
import ta # pandas_ta is better for Supertrend, but using ta for other indicators as per original
from datetime import datetime, timedelta
from colorama import init, Fore, Style # Pyrmethus's color enchantment
import dateutil.parser # For parsing diverse date strings
import dateutil.tz     # For handling timezones
import signal          # For graceful shutdown
import json            # For structured JSON logging
import random          # For jitter in backoff retry
from types import SimpleNamespace # For safe stub initialization
from typing import Optional, Dict, Any, List, Tuple
import sys # For sys.exit
from dataclasses import dataclass, field
from enum import Enum


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

def parse_to_utc(dt_str: str) -> datetime:
    """
    # An incantation to transmute a date/time string from any known locale
    # or timezone into a pure, naive UTC datetime object.
    # It drops timezone info with replace(tzinfo=None) for consistency after conversion.
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
    TESTNET: bool = field(default=True)

    # Trading Configuration
    SYMBOL: str = field(default="BTCUSDT")
    CATEGORY: str = field(default="linear")
    LEVERAGE: int = field(default=5)
    HEDGE_MODE: bool = field(default=False)
    POSITION_IDX: int = field(default=0) # 0=One-way mode, 1=Long, 2=Short in hedge mode

    # Position Sizing
    RISK_PER_TRADE_PCT: float = field(default=1.0) # Risk % of account balance per trade
    MAX_POSITION_SIZE_USD: float = field(default=10000.0) # Max position value in USD
    MIN_POSITION_SIZE_USD: float = field(default=10.0) # Min position value in USD

    # Strategy Parameters
    TIMEFRAME: str = field(default="15") # Kline interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)
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

    # Risk Management
    STOP_LOSS_PCT: float = field(default=0.015) # 1.5% stop loss from entry
    TAKE_PROFIT_PCT: float = field(default=0.03) # 3% take profit from entry
    TRAILING_STOP_PCT: float = field(default=0.005) # 0.5% trailing stop from highest profit
    MAX_DAILY_LOSS_PCT: float = field(default=0.05) # 5% max daily loss from start balance

    # Execution Settings
    ORDER_TYPE: str = field(default="Market")
    TIME_IN_FORCE: str = field(default="GTC")
    REDUCE_ONLY: bool = field(default=False)

    # Bot Settings
    LOOP_INTERVAL_SEC: int = field(default=60) # Check interval in seconds
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
    SIGNAL_COOLDOWN_SEC: int = field(default=60)
    SIGNAL_CONFIRM_BARS: int = field(default=1)


    def __post_init__(self):
        """Load configuration from environment variables and validate."""
        self.API_KEY = os.getenv("BYBIT_API_KEY", self.API_KEY)
        self.API_SECRET = os.getenv("BYBIT_API_SECRET", self.API_SECRET)
        self.TESTNET = os.getenv("BYBIT_TESTNET", str(self.TESTNET)).lower() in ['true', '1', 't']
        self.SYMBOL = os.getenv("TRADING_SYMBOL", self.SYMBOL) # Use TRADING_SYMBOL
        self.CATEGORY = os.getenv("BYBIT_CATEGORY", self.CATEGORY)
        self.LEVERAGE = int(os.getenv("BYBIT_LEVERAGE", self.LEVERAGE))
        self.HEDGE_MODE = os.getenv("BYBIT_HEDGE_MODE", str(self.HEDGE_MODE)).lower() in ['true', '1', 't']
        self.POSITION_IDX = int(os.getenv("BYBIT_POSITION_IDX", self.POSITION_IDX))

        self.RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", self.RISK_PER_TRADE_PCT))
        self.MAX_POSITION_SIZE_USD = float(os.getenv("BYBIT_MAX_POSITION_SIZE_USD", self.MAX_POSITION_SIZE_USD))
        self.MIN_POSITION_SIZE_USD = float(os.getenv("BYBIT_MIN_POSITION_SIZE_USD", self.MIN_POSITION_SIZE_USD))

        self.TIMEFRAME = os.getenv("TRADING_TIMEFRAME", self.TIMEFRAME) # Use TRADING_TIMEFRAME
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


# =====================================================================
# LOGGING SETUP
# =====================================================================

# --- Structured JSON Logging alongside Color Console ---
class SimpleJSONFormatter(logging.Formatter):
    """
    # A scribe to record the bot's saga in machine-readable JSON format,
    # for deeper analysis in the digital archives.
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
    # Forging the logger to chronicle the bot's journey,
    # with vibrant console hues and a steadfast log file (both plain and JSON).
    """
    logger = logging.getLogger("EhlersSuperTrendBot")
    if logger.handlers:
        return logger # Avoid re-configuring if already set up, preserving harmony

    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Clear existing handlers to prevent duplicate logs if this function is called multiple times
    if logger.hasHandlers():
        logger.handlers.clear()

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


# =====================================================================
# PRECISION MANAGEMENT
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

    max_position_value: Decimal
    min_position_value: Decimal

    contract_value: Decimal = Decimal('1')  # For derivatives, typically the value of one contract
    is_inverse: bool = False

    maker_fee: Decimal = Decimal('0.0001')
    taker_fee: Decimal = Decimal('0.0006')


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

                if response and response['retCode'] == 0:
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
                return Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                return Decimal(default)

        tick_size = safe_decimal(price_filter.get('tickSize', '0.00000001')) # Default to high precision if missing
        min_price = safe_decimal(price_filter.get('minPrice', '0'))
        max_price = safe_decimal(price_filter.get('maxPrice', '1e9')) # Default to a large number

        qty_step = safe_decimal(lot_size_filter.get('qtyStep', unified_lot_size_filter.get('qtyStep', '0.00000001'))) # Default to high precision
        min_order_qty = safe_decimal(lot_size_filter.get('minOrderQty', unified_lot_size_filter.get('minOrderQty', '0')))
        max_order_qty = safe_decimal(lot_size_filter.get('maxOrderQty', unified_lot_size_filter.get('maxOrderQty', '1e9')))

        min_leverage = safe_decimal(leverage_filter.get('minLeverage', '1'))
        max_leverage = safe_decimal(leverage_filter.get('maxLeverage', '100')) # Default max leverage
        leverage_step = safe_decimal(leverage_filter.get('leverageStep', '0.1'))

        # Max/Min Position Value can be tricky, using lotSizeFilter's limits as a proxy
        max_position_value = safe_decimal(lot_size_filter.get('maxMktOrderQty', lot_size_filter.get('maxOrderAmt', '1e9')))
        min_position_value = safe_decimal(lot_size_filter.get('minOrderAmt', lot_size_filter.get('minOrderQty', '1'))) # Default to a small value

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
            max_position_value=max_position_value,
            min_position_value=min_position_value,
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
        if step == 0:
            return value
        try:
            # Use normalize() to get the decimal representation of the step (e.g., 0.01)
            quantize_exp = step.normalize()

            # Calculate the number of steps. Use floor division for consistent rounding down.
            num_steps = (value / step).quantize(Decimal('1'), rounding=ROUND_DOWN)

            rounded_value = num_steps * step

            # If the step itself has decimal places, use quantize for precision
            if quantize_exp.as_tuple().exponent < 0:
                 rounded_value = rounded_value.quantize(quantize_exp, rounding=ROUND_DOWN)

            return rounded_value

        except Exception as e:
            self.logger.error(f"Error rounding decimal value {value} with step {step}: {e}", exc_info=True)
            return value # Return original value if rounding fails

    def round_price(self, symbol: str, price: float | Decimal) -> Decimal:
        """Round price to correct tick size, ensuring it's within min/max price bounds."""
        specs = self.get_specs(symbol)
        if not specs:
            self.logger.warning(f"Symbol {symbol} specs not found. Using default high precision rounding for price.")
            try:
                # Default to a high precision if specs are missing
                return Decimal(str(price)).quantize(Decimal('0.00000001'))
            except Exception:
                return Decimal(str(price)) # Return original if even high precision fails

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
            self.logger.warning(f"Symbol {symbol} specs not found. Using default high precision rounding for quantity.")
            try:
                # Default to a high precision if specs are missing
                return Decimal(str(quantity)).quantize(Decimal('0.00000001'))
            except Exception:
                return Decimal(str(quantity)) # Return original if even high precision fails

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

    def __init__(self, precision_manager: PrecisionManager, logger: logging.Logger):
        self.precision = precision_manager
        self.logger = logger

    def calculate_position_size_usd(
        self,
        symbol: str,
        account_balance_usdt: Decimal,
        risk_percent: Decimal,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        leverage: Decimal
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
        if account_balance_usdt <= 0:
            self.logger.warning(f"Account balance is zero or negative ({account_balance_usdt}). Cannot calculate position size.")
            return None
        if entry_price <= 0:
            self.logger.warning(f"Entry price is zero or negative ({entry_price}). Cannot calculate position size.")
            return None
        if leverage <= 0:
            self.logger.warning(f"Leverage is zero or negative ({leverage}). Cannot calculate position size.")
            return None

        stop_distance_price = abs(entry_price - stop_loss_price)
        if stop_distance_price <= 0:
            self.logger.warning(f"Stop loss distance is zero or negative ({stop_distance_price}). Cannot calculate position size.")
            return None

        # --- Calculations ---
        # Calculate risk amount in USDT
        risk_amount_usdt = account_balance_usdt * risk_percent

        # Calculate stop loss distance in percentage terms
        stop_distance_pct = stop_distance_price / entry_price

        # Calculate the required position value in USDT to risk 'risk_amount_usdt'
        # position_value_usd * stop_distance_pct = risk_amount_usdt
        # position_value_usd = risk_amount_usdt / stop_distance_pct
        if stop_distance_pct > 0:
            position_value_needed_usd = risk_amount_usdt / stop_distance_pct
        else:
            self.logger.warning("Stop distance percentage is zero. Cannot calculate required position value.")
            return None

        # Apply leverage to determine the maximum tradeable position value based on account balance
        # For derivatives, max position value might also be limited by 'max_position_value' from specs
        max_tradeable_value_usd = account_balance_usdt * leverage

        # Cap the needed position value by maximum tradeable value and Bybit's max position value limits
        position_value_usd = min(
            position_value_needed_usd,
            max_tradeable_value_usd,
            specs.max_position_value # Apply Bybit's specific max order value if available
        )

        # Ensure minimum position value is met
        if position_value_usd < specs.min_position_value:
            self.logger.warning(f"Calculated position value ({position_value_usd:.4f} USD) is below minimum ({specs.min_position_value:.4f} USD). Using minimum.")
            position_value_usd = specs.min_position_value

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
        if final_quantity <= 0:
            self.logger.warning(f"Calculated final quantity is zero or negative ({final_quantity}). Cannot proceed with order.")
            return None

        # Recalculate actual risk based on final quantity and compare against allowed risk
        actual_position_value_usd = final_quantity * entry_price
        actual_risk_amount_usdt = actual_position_value_usd * stop_distance_pct
        actual_risk_percent = (actual_risk_amount_usdt / account_balance_usdt) * 100 if account_balance_usdt > 0 else Decimal('0')

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
    """Manage trailing stop losses for profitable positions by updating exchange SL."""

    def __init__(self, bybit_session: HTTP, precision_manager: PrecisionManager, logger: logging.Logger, api_call_wrapper: Any):
        self.session = bybit_session
        self.precision = precision_manager
        self.logger = logger
        self.api_call = api_call_wrapper # Reference to the bot's api_call method
        # Stores active trailing stop info: {symbol: {'side': 'Buy'/'Sell',
        # 'activation_price': Decimal, 'trail_percent': Decimal,
        # 'current_stop': Decimal, 'highest_price': Decimal/None,
        # 'lowest_price': Decimal/None, 'is_activated': bool}}
        self.active_trailing_stops: Dict[str, dict] = {}

    def initialize_trailing_stop(
        self,
        symbol: str,
        position_side: str,
        entry_price: Decimal,
        current_price: Decimal,
        trail_percent: float, # Pass as percentage
        activation_percent: float # Pass as percentage
    ) -> Optional[dict]:
        """
        Initialize trailing stop for a position.
        Returns the initial trailing stop configuration if successful.
        """
        specs = self.precision.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot initialize trailing stop for {symbol}: Specs not found.")
            return None

        if specs.category == 'spot':
            self.logger.debug(f"Trailing stops are not applicable for spot category {symbol}. Skipping initialization logic.")
            return None

        trail_pct = Decimal(str(trail_percent / 100))
        activation_pct = Decimal(str(activation_percent / 100))

        activation_price = Decimal('0')
        current_stop = Decimal('0')
        highest_price = Decimal('0') # Track highest price reached for Buy orders
        lowest_price = Decimal('0')  # Track lowest price reached for Sell orders
        is_activated = False

        if position_side == "Buy":
            activation_price = entry_price * (Decimal('1') + activation_pct)
            is_activated = current_price >= activation_price
            highest_price = current_price if is_activated else entry_price # Start tracking from current price if activated
            if is_activated and highest_price > 0:
                # Calculate initial stop based on highest price reached
                current_stop = self.precision.round_price(symbol, highest_price * (Decimal('1') - trail_pct))
        else:  # Sell/Short
            activation_price = entry_price * (Decimal('1') - activation_pct)
            is_activated = current_price <= activation_price
            lowest_price = current_price if is_activated else entry_price # Start tracking from current price if activated
            if is_activated and lowest_price > 0:
                # Calculate initial stop based on lowest price reached
                current_stop = self.precision.round_price(symbol, lowest_price * (Decimal('1') + trail_pct))

        trailing_stop_info = {
            'side': position_side,
            'activation_price': activation_price,
            'trail_percent': trail_pct,
            'is_activated': is_activated,
            'highest_price': highest_price,
            'lowest_price': lowest_price,
            'current_stop': current_stop,
            'last_update': datetime.now()
        }

        self.active_trailing_stops[symbol] = trailing_stop_info
        if is_activated and current_stop > 0:
            self.logger.info(f"Initialized and activated trailing stop for {symbol} ({position_side}): Initial Stop={current_stop}, Activation={activation_price}")
        else:
            self.logger.info(f"Initialized trailing stop for {symbol} ({position_side}): Activation={activation_price}")
        return trailing_stop_info

    def update_trailing_stop(
        self,
        symbol: str,
        current_price: Decimal,
        update_exchange: bool = True
    ) -> bool:
        """
        Update trailing stop based on current price.
        Returns True if the stop was potentially updated locally or needs exchange update.
        """
        if symbol not in self.active_trailing_stops:
            return False # No active trailing stop for this symbol

        ts_info = self.active_trailing_stops[symbol]
        updated_locally = False

        if ts_info['side'] == "Buy":
            # If not activated and price crosses activation level
            if not ts_info['is_activated'] and current_price >= ts_info['activation_price']:
                ts_info['is_activated'] = True
                ts_info['highest_price'] = current_price # Start tracking from this price
                self.logger.info(f"Trailing stop activated for {symbol} at {current_price}.")

            # If activated, update highest price and stop if current price is higher
            if ts_info['is_activated']:
                if current_price > ts_info['highest_price']:
                    ts_info['highest_price'] = current_price
                    new_stop = current_price * (Decimal('1') - ts_info['trail_percent'])

                    # Only update if the new stop is higher than the current stop
                    if new_stop > ts_info['current_stop']:
                        ts_info['current_stop'] = self.precision.round_price(symbol, new_stop)
                        updated_locally = True
                        self.logger.debug(f"Trailing stop updated for {symbol}: New Stop={ts_info['current_stop']}")

        else:  # Sell/Short position
            # If not activated and price crosses activation level
            if not ts_info['is_activated'] and current_price <= ts_info['activation_price']:
                ts_info['is_activated'] = True
                ts_info['lowest_price'] = current_price # Start tracking from this price
                self.logger.info(f"Trailing stop activated for {symbol} at {current_price}.")

            # If activated, update lowest price and stop if current price is lower
            if ts_info['is_activated']:
                if current_price < ts_info['lowest_price']:
                    ts_info['lowest_price'] = current_price
                    new_stop = current_price * (Decimal('1') + ts_info['trail_percent'])

                    # Only update if the new stop is lower than the current stop
                    if new_stop < ts_info['current_stop']:
                        ts_info['current_stop'] = self.precision.round_price(symbol, new_stop)
                        updated_locally = True
                        self.logger.debug(f"Trailing stop updated for {symbol}: New Stop={ts_info['current_stop']}")

        ts_info['last_update'] = datetime.now()

        # If locally updated and exchange update is requested, attempt to update exchange
        if updated_locally and update_exchange and ts_info['current_stop'] > 0:
            self.logger.info(f"Attempting to update stop loss on exchange for {symbol} to {ts_info['current_stop']}")
            success = self._update_stop_loss_on_exchange(symbol, ts_info['current_stop'])
            if success:
                return True # Indicate that an exchange update was attempted and succeeded
            else:
                # Log failure but indicate local update might have occurred
                self.logger.error(f"Failed to update trailing stop on exchange for {symbol}. Local state updated, but exchange state may be stale.")
                return True # Still return True if local update happened
        elif updated_locally: # Locally updated but not updated on exchange (e.g., update_exchange=False or stop_price=0)
            return True
        else: # Not updated locally
            return False

    def _update_stop_loss_on_exchange(self, symbol: str, stop_price: Decimal) -> bool:
        """Update stop loss on exchange using set_trading_stop"""
        specs = self.precision.get_specs(symbol)
        if not specs:
            self.logger.error(f"Failed to update stop loss for {symbol}: Specs not found.")
            return False

        if specs.category == 'spot':
            self.logger.warning(f"Cannot update stop loss for spot symbol {symbol}.")
            return False

        try:
            # Use the bot's api_call wrapper
            response = self.api_call(
                self.session.set_trading_stop,
                category=specs.category,
                symbol=symbol,
                stopLoss=str(stop_price),
                slOrderType='Market' # Typically Market order for stop loss
            )

            if response is not None: # api_call returns None on failure, or dict on success
                self.logger.info(f"Successfully updated stop loss on exchange for {symbol} to {stop_price}")
                return True
            else:
                self.logger.error(f"Failed to update stop loss on exchange for {symbol}: API call wrapper returned None.")
                return False

        except Exception as e:
            self.logger.error(f"Exception updating stop loss on exchange for {symbol}: {e}", exc_info=True)
            return False

    def remove_trailing_stop(self, symbol: str):
        """Remove trailing stop for a symbol"""
        if symbol in self.active_trailing_stops:
            del self.active_trailing_stops[symbol]
            self.logger.info(f"Removed trailing stop data for {symbol}")


# =====================================================================
# TERMUX SMS NOTIFIER
# =====================================================================

class TermuxSMSNotifier:
    """
    # A digital carrier pigeon to send urgent messages via Termux SMS,
    # alerting the wizard directly on their Android device.
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
            subprocess.run(["termux-sms-send", "-n", self.recipient_number, message], check=True)
            self.logger.info(Fore.GREEN + f"SMS sent to {self.recipient_number}: {message[:50]}..." + Style.RESET_ALL)
        except FileNotFoundError:
            self.logger.error(Fore.RED + "Termux command 'termux-sms-send' not found. Is 'pkg install termux-api' installed?" + Style.RESET_ALL)
        except subprocess.CalledProcessError as e:
            self.logger.error(Fore.RED + f"Termux SMS command failed with error: {e}" + Style.RESET_ALL)
        except Exception as e:
            self.logger.error(Fore.RED + f"Failed to send Termux SMS: {e}" + Style.RESET_ALL)
            
    def send_trade_alert(self, side, symbol, price, sl, tp, reason):
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
    # A specialized client to commune directly with Bybit API v5 endpoints,\n
    # returning raw responses for the bot's api_call to interpret.\n
    """
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True, default_category: str = 'linear'):
        self.session = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret)
        self._default_category = default_category

    def get_server_time(self) -> Dict[str, Any]:
        """Fetches server time (used for credential validation)."""
        return self.session.get_server_time()

    def get_instruments_info(self, symbol: Optional[str] = None, category: Optional[str] = None) -> Dict[str, Any]:
        """List active trading symbols and product info."""
        params = {'category': category or self._default_category}
        if symbol:
            params['symbol'] = symbol
        return self.session.get_instruments_info(**params)

    def get_wallet_balance(self, accountType: str = 'UNIFIED') -> Dict[str, Any]:
        """Fetches wallet balances."""
        return self.session.get_wallet_balance(accountType=accountType)

    def get_kline(self, symbol: str, interval: str, limit: int = 200, category: Optional[str] = None) -> Dict[str, Any]:
        """Fetches historical candlestick data."""
        return self.session.get_kline(category=category or self._default_category, symbol=symbol, interval=interval, limit=limit)

    def get_positions(self, symbol: Optional[str] = None, category: Optional[str] = None) -> Dict[str, Any]:
        """Lists active positions."""
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
        """Places a new order."""
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
        if price is not None: params['price'] = price
        if stopLoss is not None:
            params['stopLoss'] = stopLoss
            if slOrderType: params['slOrderType'] = slOrderType
        if takeProfit is not None:
            params['takeProfit'] = takeProfit
            if tpOrderType: params['tpOrderType'] = tpOrderType
        if tpslMode is not None: params['tpslMode'] = tpslMode

        return self.session.place_order(**params)

    def set_trading_stop(self, symbol: str, side: str, callbackRate: Optional[str] = None,
                         stopLoss: Optional[str] = None, takeProfit: Optional[str] = None,
                         category: Optional[str] = None, slOrderType: Optional[str] = None,
                         tpOrderType: Optional[str] = None) -> Dict[str, Any]:
        """Manages TP/SL/Trailing Stops."""
        params = {
            'category': category or self._default_category,
            'symbol': symbol,
            'side': side # Side is required for set_trading_stop on unified account
        }
        if callbackRate is not None: params['callbackRate'] = callbackRate
        if stopLoss is not None:
            params['stopLoss'] = stopLoss
            if slOrderType: params['slOrderType'] = slOrderType
        if takeProfit is not None:
            params['takeProfit'] = takeProfit
            if tpOrderType: params['tpOrderType'] = tpOrderType
        return self.session.set_trading_stop(**params)

    def get_order_history(self, symbol: str, orderId: Optional[str] = None, limit: int = 50,
                          category: Optional[str] = None) -> Dict[str, Any]:
        """Fetches order history."""
        params = {'category': category or self._default_category, 'symbol': symbol, 'limit': limit}
        if orderId: params['orderId'] = orderId
        return self.session.get_order_history(**params)

    def get_open_orders(self, symbol: str, orderId: Optional[str] = None, limit: int = 50,
                        category: Optional[str] = None) -> Dict[str, Any]:
        """Fetches currently open orders."""
        params = {'category': category or self._default_category, 'symbol': symbol, 'limit': limit}
        if orderId: params['orderId'] = orderId
        return self.session.get_open_orders(**params)

    def cancel_order(self, category: str, symbol: str, orderId: str) -> Dict[str, Any]:
        """Cancels a specific order."""
        return self.session.cancel_order(category=category, symbol=symbol, orderId=orderId)

    def cancel_all_orders(self, category: str, symbol: str) -> Dict[str, Any]:
        """Cancels all open orders for a symbol."""
        return self.session.cancel_all_orders(category=category, symbol=symbol)

    def set_leverage(self, category: str, symbol: str, buyLeverage: str, sellLeverage: str) -> Dict[str, Any]:
        """Sets leverage for a symbol."""
        return self.session.set_leverage(category=category, symbol=symbol, buyLeverage=buyLeverage, sellLeverage=sellLeverage)

    def get_tickers(self, category: str, symbol: str) -> Dict[str, Any]:
        """Fetches ticker information."""
        return self.session.get_tickers(category=category, symbol=symbol)


# =====================================================================
# EHLERS SUPERTREND INDICATOR FUNCTION (from supertrend.py)
# =====================================================================

def ehlers_supertrend(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """
    # Calculates Ehlers SuperTrend indicator using ATR and exponential smoothing.\n
    # Returns a DataFrame with 'ehlers_supertrend_line' (the line) and 'ehlers_supertrend_direction' (1=uptrend, -1=downtrend).\n
    """
    # Calculate True Range (TR)
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Smoothed ATR with exponential moving average
    atr = tr.ewm(span=length, adjust=False).mean()

    # Median price
    hl2 = (high + low) / 2

    # Define upper and lower bands
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    supertrend_line = pd.Series(index=close.index, dtype=float)
    supertrend_direction = pd.Series(index=close.index, dtype=int)

    for i in range(len(close)):
        if i == 0:
            supertrend_line.iloc[i] = upper_band.iloc[i]
            supertrend_direction.iloc[i] = -1  # start with downtrend by default
            continue

        curr_close = close.iloc[i]
        prev_supertrend_line = supertrend_line.iloc[i - 1]
        prev_supertrend_direction = supertrend_direction.iloc[i - 1]
        curr_upper = upper_band.iloc[i]
        curr_lower = lower_band.iloc[i]

        # SuperTrend logic
        if prev_supertrend_direction == 1: # Was in uptrend
            if curr_close < curr_lower: # Price drops below lower band
                supertrend_line.iloc[i] = curr_upper # Switch to upper band
                supertrend_direction.iloc[i] = -1 # New downtrend
            else:
                # Stay in uptrend, supertrend is max of previous supertrend and current lower band
                supertrend_line.iloc[i] = max(curr_lower, prev_supertrend_line)
                supertrend_direction.iloc[i] = 1 # Continue uptrend
        elif prev_supertrend_direction == -1: # Was in downtrend
            if curr_close > curr_upper: # Price rises above upper band
                supertrend_line.iloc[i] = curr_lower # Switch to lower band
                supertrend_direction.iloc[i] = 1 # New uptrend
            else:
                # Stay in downtrend, supertrend is min of previous supertrend and current upper band
                supertrend_line.iloc[i] = min(curr_upper, prev_supertrend_line)
                supertrend_direction.iloc[i] = -1 # Continue downtrend
        else:
            # Fallback for initial NaN or unexpected state
            supertrend_line.iloc[i] = np.nan
            supertrend_direction.iloc[i] = 0

    # Fill initial NaNs for supertrend and direction if any (e.g. from ATR warmup)
    supertrend_line = supertrend_line.ffill().bfill() # ffill then bfill to handle leading NaNs
    supertrend_direction = supertrend_direction.ffill().bfill() # ffill then bfill to handle leading NaNs

    return pd.DataFrame({\
        'ehlers_supertrend_line': supertrend_line,\
        'ehlers_supertrend_direction': supertrend_direction\
    })


# =====================================================================
# MAIN TRADING BOT CLASS
# =====================================================================

class EhlersSuperTrendBot:
    def __init__(self, config: Config):
        self.config = config
        self.logger = setup_logger(config)

        self.logger.info("Initializing Ehlers SuperTrend Trading Bot...")

        # --- API Session Initialization (using BybitClient) ---
        self.bybit_client = BybitClient(
            api_key=self.config.API_KEY,
            api_secret=self.config.API_SECRET,
            testnet=self.config.TESTNET,
            default_category=self.config.CATEGORY_ENUM.value
        )
        self.ws: Optional[WebSocket] = None # WebSocket instance

        # --- Managers Initialization ---
        # PrecisionManager needs the raw HTTP session
        self.precision_manager = PrecisionManager(self.bybit_client.session, self.logger)
        self.order_sizer = OrderSizingCalculator(self.precision_manager, self.logger)
        # TrailingStopManager needs the bot's api_call wrapper
        self.trailing_stop_manager = TrailingStopManager(self.bybit_client.session, self.precision_manager, self.logger, self.api_call)

        # --- Termux SMS Notifier ---
        self.sms_notifier = TermuxSMSNotifier(
            recipient_number=self.config.TERMUX_SMS_RECIPIENT_NUMBER,
            logger=self.logger,
            price_precision=self.precision_manager.get_decimal_places(self.config.SYMBOL)[0]
        )

        # --- Data Storage ---
        self.market_data: pd.DataFrame = pd.DataFrame()
        self.current_positions: Dict[str, dict] = {} # {symbol: position_data}
        self.open_orders: Dict[str, dict] = {} # {order_id: order_data}
        self.account_balance_usdt: Decimal = Decimal('0.0')
        self.initial_equity: Decimal = Decimal('0.0') # Renamed from start_balance_usdt for consistency with supertrend.py

        # --- Strategy State ---
        self.position_active: bool = False
        self.current_position_side: Optional[str] = None # 'Buy' or 'Sell'
        self.current_position_entry_price: Decimal = Decimal('0')
        self.current_position_size: Decimal = Decimal('0')
        self.last_signal: Optional[str] = None # Changed to str to match generate_signal output
        self.last_kline_ts: int = 0 # Unix timestamp of the last processed confirmed candle
        self.last_trade_time: float = 0.0 # For trade cooldown
        self.cumulative_pnl: float = 0.0 # Total realized PnL for cumulative loss guard

        # --- Initializations & Validations ---
        self._validate_api_credentials() # Test API connection and keys
        self._validate_symbol_timeframe() # Validate symbol and timeframe
        self._capture_initial_equity() # Capture initial equity for cumulative loss guard

        if self.config.CATEGORY_ENUM == Category.SPOT:
            self.logger.info(f"Leverage set to 1 for SPOT category as it's not applicable.")
        else:
            self.set_leverage() # Set leverage for derivatives

        self.logger.info(f"Bot Configuration Loaded:")
        self.logger.info(f"  Mode: {'Testnet' if config.TESTNET else 'Mainnet'}")
        self.logger.info(f"  Symbol: {config.SYMBOL}, Category: {config.CATEGORY_ENUM.value}")
        self.logger.info(f"  Leverage: {config.LEVERAGE}x")
        self.logger.info(f"  Hedge Mode: {config.HEDGE_MODE}, PositionIdx: {config.POSITION_IDX}")
        self.logger.info(f"  Timeframe: {config.TIMEFRAME}, Lookback: {config.LOOKBACK_PERIODS} periods")
        self.logger.info(f"  Ehlers Adaptive Trend Params: Length={config.EHLERS_LENGTH}, Smoothing={config.SMOOTHING_LENGTH}, Sensitivity={config.SENSITIVITY}")
        self.logger.info(f"  Ehlers Supertrend Params: Length={config.EHLERS_ST_LENGTH}, Multiplier={config.EHLERS_ST_MULTIPLIER}")
        self.logger.info(f"  RSI Params: Window={config.RSI_WINDOW}")
        self.logger.info(f"  MACD Params: Fast={config.MACD_FAST}, Slow={config.MACD_SLOW}, Signal={config.MACD_SIGNAL}")
        self.logger.info(f"  Risk Params: Risk/Trade={config.RISK_PER_TRADE_PCT}%, SL={config.STOP_LOSS_PCT*100:.2f}%, TP={config.TAKE_PROFIT_PCT*100:.2f}%, Trail={config.TRAILING_STOP_PCT*100:.2f}%, Max Daily Loss={config.MAX_DAILY_LOSS_PCT*100:.2f}%")
        self.logger.info(f"  Execution: OrderType={config.ORDER_TYPE_ENUM.value}, TimeInForce={config.TIME_IN_FORCE}, ReduceOnly={config.REDUCE_ONLY}")
        self.logger.info(f"  Loop Interval: {config.LOOP_INTERVAL_SEC} seconds")
        self.logger.info(f"  API Retry: MaxRetries={config.MAX_API_RETRIES}, RetryDelay={config.API_RETRY_DELAY_SEC}s")
        self.logger.info(f"  Auto Close on Shutdown: {config.AUTO_CLOSE_ON_SHUTDOWN}")
        self.logger.info(f"  Signal Cooldown: {config.SIGNAL_COOLDOWN_SEC}s, Confirm Bars: {config.SIGNAL_CONFIRM_BARS}")

        if self.sms_notifier.is_enabled:
            self.sms_notifier.send_sms(f"🚀 Bot initialized for {self.config.SYMBOL} on {'TESTNET' if self.config.TESTNET else 'MAINNET'}.")


        # Graceful shutdown handling
        self._stop_requested = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)


    def _signal_handler(self, signum: int, frame: Any):
        """Handler for termination signals to stop the bot gracefully."""
        self.logger.info(f"Signal {signum} received, stopping bot gracefully...")
        self._stop_requested = True
        self.stop_event.set() # Also set the threading event for WebSocket thread


    def _handle_bybit_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        # Parses Bybit API JSON response, enforcing success checks and raising
        # specific exceptions for known error codes. Returns the 'result' data on success.
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
            if ret_code == 130014: # Example Bybit rate limit code
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

    def api_call(self, api_method: Any, **kwargs) -> Optional[Dict[str, Any]]:
        """
        # A resilient incantation to invoke pybit HTTP methods,
        # equipped with retries, exponential backoff (with jitter), and wise error handling.
        # It guards against transient network whispers and rate limit enchantments.
        # Returns the 'result' data dictionary on success, or None if all retries fail.
        """
        for attempt in range(1, self.config.MAX_API_RETRIES + 1):
            try:
                raw_resp = api_method(**kwargs)
                result_data = self._handle_bybit_response(raw_resp)
                return result_data # Success, return the extracted result
            
            except PermissionError as e:
                self.logger.critical(Fore.RED + Style.BRIGHT + f"Fatal API error: {e}. Exiting bot." + Style.RESET_ALL)
                sys.exit(1) # Halt the bot immediately
            
            except (ConnectionRefusedError, RuntimeError, FailedRequestError, InvalidRequestError) as e:
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
        # A preliminary ritual to confirm the API keys possess true power
        # before the bot embarks on its trading quest.
        # Uses get_wallet_balance first (a private endpoint), falling back to get_positions if needed.
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
        # A guardian spell to ensure the chosen symbol and timeframe
        # are recognized and valid within the Bybit realm.
        """
        valid_intervals = {"1","3","5","15","30","60","120","240","360","720","D","W","M"}
        if str(self.config.TIMEFRAME) not in valid_intervals:
            self.logger.critical(Fore.RED + f"Invalid timeframe '{self.config.TIMEFRAME}'. Must be one of {sorted(valid_intervals)}. Exiting." + Style.RESET_ALL)
            subprocess.run(["termux-toast", f"Invalid Timeframe: {self.config.TIMEFRAME}"])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"CRITICAL: Invalid timeframe '{self.config.TIMEFRAME}' for {self.config.SYMBOL}. Exiting.")
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
        # Records the account's equity at the beginning of the bot's operation,
        # a baseline for the cumulative loss protection enchantment.
        """
        eq = self.get_account_balance_usdt()
        if eq > 0:
            self.initial_equity = eq
            self.logger.info(Fore.GREEN + f"Initial equity set to {self.initial_equity:.4f} USDT." + Style.RESET_ALL)
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"Bot session started. Initial Equity: ${self.initial_equity:.2f}")
        else:
            self.logger.warning(Fore.YELLOW + "Could not fetch initial equity or equity is zero; cumulative loss guard will use PnL fallback logic." + Style.RESET_ALL)

    def _cumulative_loss_guard(self) -> bool:
        """
        # A protective ward that halts trading if the cumulative equity drawdown
        # exceeds the predefined maximum loss threshold from the initial equity.
        """
        current_equity = self.get_account_balance_usdt()
        if current_equity <= 0:
            self.logger.critical(Fore.RED + "Current account balance is zero or negative. Trading halted." + Style.RESET_ALL)
            subprocess.run(["termux-toast", "CRITICAL: Account balance zero! Trading Halted."])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"CRITICAL: Account balance for {self.config.SYMBOL} is zero or negative. Trading halted!")
            return False

        if self.initial_equity <= 0:
            # Fallback to cumulative PnL-based logic if initial equity wasn't captured or was zero
            if self.cumulative_pnl < -self.config.MAX_DAILY_LOSS_PCT * float(self.initial_equity): # Assuming initial_equity was captured correctly earlier
                self.logger.critical(Fore.RED + f"Cumulative PnL loss limit reached (${self.cumulative_pnl:.2f}, {self.config.MAX_DAILY_LOSS_PCT*100:.2f}% limit). Trading halted." + Style.RESET_ALL)
                subprocess.run(["termux-toast", "Cumulative PnL Loss Limit Reached! Trading Halted."])
                if self.sms_notifier.is_enabled:
                    self.sms_notifier.send_sms(f"CRITICAL: Cumulative PnL loss limit reached for {self.config.SYMBOL} (${self.cumulative_pnl:.2f}, {self.config.MAX_DAILY_LOSS_PCT*100:.2f}% limit). Trading halted!")
                return False
            return True

        drop_pct = ((self.initial_equity - current_equity) / self.initial_equity)
        if drop_pct >= Decimal(str(self.config.MAX_DAILY_LOSS_PCT)):
            self.logger.critical(Fore.RED + Style.BRIGHT + f"Cumulative equity drawdown {drop_pct*100:.2f}% exceeded limit ({self.config.MAX_DAILY_LOSS_PCT*100:.2f}%). Trading halted!" + Style.RESET_ALL)
            subprocess.run(["termux-toast", f"Cumulative Loss Limit Reached! Drawdown: {drop_pct*100:.2f}%"])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"CRITICAL: Cumulative equity drawdown {drop_pct*100:.2f}% exceeded limit for {self.config.SYMBOL}. Trading halted!")

            pos = self.get_positions() # Fetch latest position
            if self.position_active:
                self.logger.warning(Fore.YELLOW + "Closing open position due to cumulative loss limit enchantment." + Style.RESET_ALL)
                self.close_position()
            return False
        return True

    # =====================================================================
    # DATA FETCHING METHODS
    # =====================================================================

    def fetch_klines(self, limit: Optional[int] = None) -> pd.DataFrame:
        """Fetch historical kline data from Bybit."""
        try:
            fetch_limit = limit if limit else self.config.LOOKBACK_PERIODS
            if fetch_limit < 2: # Need at least 2 candles for signal generation
                fetch_limit = 2

            self.logger.debug(f"Fetching {fetch_limit} klines for {self.config.SYMBOL} ({self.config.TIMEFRAME})...")
            response_data = self.api_call(
                self.bybit_client.get_kline,
                category=self.config.CATEGORY_ENUM.value,
                symbol=self.config.SYMBOL,
                interval=self.config.TIMEFRAME,
                limit=fetch_limit
            )

            if response_data is not None and response_data.get('list'):
                klines = response_data['list']
                if not klines:
                    self.logger.warning(f"No kline data returned for {self.config.SYMBOL}.")
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

                self.logger.debug(f"Successfully fetched and processed {len(df)} klines for {self.config.SYMBOL}.")
                return df
            else:
                self.logger.error(f"Failed to fetch klines for {self.config.SYMBOL}: API call wrapper returned None or empty list.")
                return pd.DataFrame()

        except Exception as e:
            self.logger.error(f"Exception fetching klines for {self.config.SYMBOL}: {e}", exc_info=True)
            return pd.DataFrame()

    def get_ticker(self) -> Optional[dict]:
        """Get current ticker data for the symbol."""
        try:
            response_data = self.api_call(
                self.bybit_client.get_tickers,
                category=self.config.CATEGORY_ENUM.value,
                symbol=self.config.SYMBOL
            )

            if response_data is not None and response_data.get('list'):
                tickers = response_data['list']
                if tickers:
                    return tickers[0] # Expecting a single ticker for the specified symbol
                else:
                    self.logger.warning(f"Ticker data list is empty for {self.config.SYMBOL}.")
                    return None
            else:
                self.logger.error(f"Failed to fetch ticker for {self.config.SYMBOL}: API call wrapper returned None or empty list.")
                return None

        except Exception as e:
            self.logger.error(f"Exception fetching ticker for {self.config.SYMBOL}: {e}", exc_info=True)
            return None

    # =====================================================================
    # TECHNICAL INDICATORS
    # =====================================================================

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        # Applies all required indicators to the DataFrame,
        # weaving complex patterns from the raw market energies with enhanced robustness.
        """
        # Ensure sufficient data for all indicators
        min_len = max(self.config.EHLERS_LENGTH + self.config.SMOOTHING_LENGTH + 5,
                      self.config.EHLERS_ST_LENGTH + 5,
                      self.config.MACD_SLOW + self.config.MACD_SIGNAL + 5,
                      self.config.RSI_WINDOW + 5,
                      60) # A reasonable minimum for most TA indicators

        if len(df) < min_len:
            self.logger.warning(Fore.YELLOW + f"Not enough data for indicators (have {len(df)}, need {min_len}). Returning DataFrame with NaNs for indicators." + Style.RESET_ALL)
            # Ensure indicator columns exist and are filled with NaN if data is insufficient
            for col in ["ehlers_trend", "ehlers_supertrend_line", "ehlers_supertrend_direction", "rsi", "macd", "macd_signal", "macd_diff"]:
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

        vol_series = pd.Series(high - low, index=df.index)
        # Use min_periods to allow calculation with less than full window at start
        volatility = vol_series.rolling(self.config.EHLERS_LENGTH, min_periods=max(1, self.config.EHLERS_LENGTH//2)).std().ewm(span=self.config.SMOOTHING_LENGTH, adjust=False).mean()
        
        raw_trend = np.where(df['close'] > (filt + (volatility * self.config.SENSITIVITY)), 1,\
                             np.where(df['close'] < (filt - (volatility * self.config.SENSITIVITY)), -1, np.nan))
        df['ehlers_trend'] = pd.Series(raw_trend, index=df.index).ffill() # Fill NaNs forward

        # --- Ehlers Supertrend (using the custom function) ---
        st_data = ehlers_supertrend(df['high'], df['low'], df['close'],
                                    length=self.config.EHLERS_ST_LENGTH,
                                    multiplier=self.config.EHLERS_ST_MULTIPLIER)
        df['ehlers_supertrend_direction'] = st_data['ehlers_supertrend_direction']
        df['ehlers_supertrend_line'] = st_data['ehlers_supertrend_line']

        # Additional Filters - RSI: Measuring the momentum's fervor
        rsi = ta.momentum.RSIIndicator(df['close'], window=self.config.RSI_WINDOW)
        df['rsi'] = rsi.rsi().ffill() # Modern pandas method

        # Additional Filters - MACD: Unveiling the convergence and divergence of forces
        macd = ta.trend.MACD(df['close'], window_fast=self.config.MACD_FAST, window_slow=self.config.MACD_SLOW, window_sign=self.config.MACD_SIGNAL)
        df['macd'] = macd.macd().fillna(0.0) # Fill NaNs with 0.0 at beginning
        df['macd_signal'] = macd.macd_signal().fillna(0.0)
        df['macd_diff'] = macd.macd_diff().fillna(0.0)
        
        # Drop rows where indicators are NaN (remove initial NaN rows)
        required_indicator_cols = ['ehlers_trend', 'ehlers_supertrend_direction', 'ehlers_supertrend_line', 'rsi', 'macd', 'macd_signal', 'macd_diff']
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
        # Generates a potent trading signal by harmonizing the whispers of multiple indicators,
        # seeking confluence for optimal entry and exit points, with optional bar confirmation.
        # Returns the signal ('BUY'/'SELL'/None) and a detailed reason string.
        """
        # Ensure enough data for comparison and confirmation
        if len(df) < max(2, self.config.SIGNAL_CONFIRM_BARS + 1):
            return None, "Insufficient data for signal generation."

        latest = df.iloc[-1]
        second_latest = df.iloc[-2]

        # Individual conditions
        ehlers_flip_up = latest['ehlers_trend'] == 1 and second_latest['ehlers_trend'] == -1
        ehlers_flip_down = latest['ehlers_trend'] == -1 and second_latest['ehlers_trend'] == 1

        ehlers_supertrend_is_bullish = latest['ehlers_supertrend_direction'] == 1
        ehlers_supertrend_is_bearish = latest['ehlers_supertrend_direction'] == -1

        rsi_over_50 = latest['rsi'] > 50
        rsi_under_50 = latest['rsi'] < 50

        macd_cross_up = latest['macd_diff'] > 0 and second_latest['macd_diff'] < 0
        macd_cross_down = latest['macd_diff'] < 0 and second_latest['macd_diff'] > 0

        # Optional confirmation for Supertrend: require last N bars agree with direction
        confirmed_supertrend_bullish = ehlers_supertrend_is_bullish
        confirmed_supertrend_bearish = ehlers_supertrend_is_bearish
        if self.config.SIGNAL_CONFIRM_BARS > 1:
            recent_supertrend_directions = df['ehlers_supertrend_direction'].iloc[-self.config.SIGNAL_CONFIRM_BARS:]
            if ehlers_flip_up: # Only apply confirmation if Ehlers is flipping
                confirmed_supertrend_bullish = ehlers_supertrend_is_bullish and (recent_supertrend_directions == 1).all()
            if ehlers_flip_down: # Only apply confirmation if Ehlers is flipping
                confirmed_supertrend_bearish = ehlers_supertrend_is_bearish and (recent_supertrend_directions == -1).all()


        # --- Build reason string based on conditions ---
        buy_conditions_met = []
        if ehlers_flip_up: buy_conditions_met.append(f"Ehlers Trend flipped UP (Current: {int(latest['ehlers_trend'])})")
        if confirmed_supertrend_bullish: buy_conditions_met.append(f"Ehlers Supertrend is BULLISH (Direction: {int(latest['ehlers_supertrend_direction'])})")
        if rsi_over_50: buy_conditions_met.append(f"RSI ({latest['rsi']:.1f}) > 50")
        if macd_cross_up: buy_conditions_met.append(f"MACD Diff ({latest['macd_diff']:.4f}) crossed UP")

        sell_conditions_met = []
        if ehlers_flip_down: sell_conditions_met.append(f"Ehlers Trend flipped DOWN (Current: {int(latest['ehlers_trend'])})")
        if confirmed_supertrend_bearish: sell_conditions_met.append(f"Ehlers Supertrend is BEARISH (Direction: {int(latest['ehlers_supertrend_direction'])})")
        if rsi_under_50: sell_conditions_met.append(f"RSI ({latest['rsi']:.1f}) < 50")
        if macd_cross_down: sell_conditions_met.append(f"MACD Diff ({latest['macd_diff']:.4f}) crossed DOWN")


        # Combined signal with all filters: The true incantation
        if (ehlers_flip_up and confirmed_supertrend_bullish and rsi_over_50 and macd_cross_up):
            reason = "BUY Signal: " + ", ".join(buy_conditions_met)
            return 'BUY', reason
        elif (ehlers_flip_down and confirmed_supertrend_bearish and rsi_under_50 and macd_cross_down):
            reason = "SELL Signal: " + ", ".join(sell_conditions_met)
            return 'SELL', reason

        return None, "No clear signal, market is calm." # No clear signal, the ether is calm

    # =====================================================================
    # RISK MANAGEMENT
    # =====================================================================

    def calculate_trade_sl_tp(self, side: str, entry_price: Decimal, df: pd.DataFrame) -> Tuple[Decimal, Decimal]:
        """
        Calculates Stop Loss and Take Profit levels based on ATR or fixed percentages.
        Returns (stop_loss_price, take_profit_price).
        """
        atr_val = self._compute_atr(df, period=self.config.EHLERS_ST_LENGTH) # Use ST length for ATR

        if atr_val and atr_val > 0:
            sl_dist = Decimal(str(self.config.ATR_MULT_SL)) * Decimal(str(atr_val))
            tp_dist = Decimal(str(self.config.ATR_MULT_TP)) * Decimal(str(atr_val))

            if side == 'Buy':
                stop_loss = entry_price - sl_dist
                take_profit = entry_price + tp_dist
            else: # Sell
                stop_loss = entry_price + sl_dist
                take_profit = entry_price - tp_dist
            self.logger.info(Fore.LIGHTMAGENTA_EX + f"ATR-based SL/TP: SL_Dist={sl_dist:.{self.precision_manager.get_decimal_places(self.config.SYMBOL)[0]}f}, TP_Dist={tp_dist:.{self.precision_manager.get_decimal_places(self.config.SYMBOL)[0]}f} (ATR={atr_val:.{self.precision_manager.get_decimal_places(self.config.SYMBOL)[0]}f})" + Style.RESET_ALL)
        else:
            # Fallback to percentage-based if ATR unavailable or invalid
            sl_pct = Decimal(str(self.config.STOP_LOSS_PCT))
            tp_pct = Decimal(str(self.config.TAKE_PROFIT_PCT))
            if side == 'Buy':
                stop_loss = entry_price * (Decimal('1') - sl_pct)
                take_profit = entry_price * (Decimal('1') + tp_pct)
            else: # Sell
                stop_loss = entry_price * (Decimal('1') + sl_pct)
                take_profit = entry_price * (Decimal('1') - tp_pct)
            self.logger.info(Fore.LIGHTMAGENTA_EX + f"Percentage-based SL/TP: SL={self.config.STOP_LOSS_PCT*100:.2f}%, TP={self.config.TAKE_PROFIT_PCT*100:.2f}%" + Style.RESET_ALL)

        return self.precision_manager.round_price(self.config.SYMBOL, stop_loss), \
               self.precision_manager.round_price(self.config.SYMBOL, take_profit)

    def _compute_atr(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """
        # Calculates the Average True Range (ATR), a measure of market volatility,
        # to dynamically adjust risk.
        """
        if len(df) < period:
            return None
        try:
            atr = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=period).average_true_range()
            return float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else None
        except Exception as e:
            self.logger.error(Fore.RED + f"Failed to compute ATR: {e}" + Style.RESET_ALL)
            return None

    def get_account_balance_usdt(self) -> Decimal:
        """Get current account balance in USDT and update internal state."""
        account_type = "UNIFIED"
        if self.config.CATEGORY_ENUM == Category.SPOT:
            account_type = "SPOT"

        try:
            response_data = self.api_call(self.bybit_client.get_wallet_balance, accountType=account_type)

            if response_data is not None and response_data.get('list'):
                balances = response_data['list']
                for coin_data in balances:
                    if coin_data.get('coin') == 'USDT':
                        balance = Decimal(coin_data.get('walletBalance', '0'))
                        self.account_balance_usdt = balance
                        self.logger.debug(f"Successfully fetched account balance: {balance:.4f} USDT ({account_type})")
                        return balance

                self.logger.warning(f"USDT balance not found in response for account type {account_type}. Returning 0.")
                self.account_balance_usdt = Decimal('0.0')
                return Decimal('0.0')
            else:
                self.logger.error(f"Failed to get account balance ({account_type}): API call wrapper returned None or empty list.")
                self.account_balance_usdt = Decimal('0.0')
                return Decimal('0.0')

        except Exception as e:
            self.logger.error(f"Exception getting account balance ({account_type}): {e}", exc_info=True)
            self.account_balance_usdt = Decimal('0.0')
            return Decimal('0.0')

    def set_leverage(self) -> bool:
        """Set leverage for the trading symbol, respecting min/max/step limits."""
        if self.config.CATEGORY_ENUM == Category.SPOT:
            self.logger.info("Spot trading does not use leverage. Skipping leverage setting.")
            return True

        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot set leverage for {self.config.SYMBOL}: Specs not found.")
            return False

        try:
            leverage_to_set_decimal = Decimal(str(self.config.LEVERAGE))
            min_lev = specs.min_leverage
            max_lev = specs.max_leverage
            lev_step = specs.leverage_step

            if leverage_to_set_decimal < min_lev:
                self.logger.warning(f"Requested leverage {leverage_to_set_decimal} for {self.config.SYMBOL} is below minimum {min_lev}. Setting to minimum.")
                leverage_to_set_decimal = min_lev
            elif leverage_to_set_decimal > max_lev:
                self.logger.warning(f"Requested leverage {leverage_to_set_decimal} for {self.config.SYMBOL} exceeds maximum {max_lev}. Setting to maximum.")
                leverage_to_set_decimal = max_lev

            if lev_step > 0:
                num_steps = (leverage_to_set_decimal / lev_step).quantize(Decimal('1'), rounding=ROUND_DOWN)
                leverage_to_set_decimal = num_steps * lev_step
                leverage_to_set_decimal = max(min_lev, min(leverage_to_set_decimal, max_lev))

            leverage_str = str(leverage_to_set_decimal)

            response_data = self.api_call(
                self.bybit_client.set_leverage,
                category=self.config.CATEGORY_ENUM.value,
                symbol=self.config.SYMBOL,
                buyLeverage=leverage_str,
                sellLeverage=leverage_str
            )

            if response_data is not None:
                self.logger.info(f"Leverage set successfully to {leverage_str}x for {self.config.SYMBOL}.")
                return True
            else:
                self.logger.error(f"Failed to set leverage for {self.config.SYMBOL}: API call wrapper returned None.")
                return False

        except Exception as e:
            self.logger.error(f"Exception setting leverage for {self.config.SYMBOL}: {e}", exc_info=True)
            return False

    # =====================================================================
    # ORDER MANAGEMENT
    # =====================================================================

    def place_order(self, side: str, qty: Decimal, order_type: OrderType,
                   entry_price: Optional[Decimal] = None, stop_loss_price: Optional[Decimal] = None,
                   take_profit_price: Optional[Decimal] = None, reduceOnly: bool = False) -> Optional[dict]:
        """Place an order on Bybit, handling precision and Bybit V5 API parameters."""
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot place order for {self.config.SYMBOL}: Specs not found.")
            return None

        try:
            rounded_qty = self.precision_manager.round_quantity(self.config.SYMBOL, qty)
            if rounded_qty <= 0:
                self.logger.warning(f"Invalid quantity ({qty} rounded to {rounded_qty}) for order placement in {self.config.SYMBOL}. Aborting order.")
                return None

            params: Dict[str, Any] = {
                "category": specs.category,
                "symbol": self.config.SYMBOL,
                "side": side,
                "orderType": order_type.value,
                "qty": str(rounded_qty),
                "timeInForce": self.config.TIME_IN_FORCE,
                "reduceOnly": reduceOnly, # Use passed reduceOnly
                "closeOnTrigger": False,
                "positionIdx": self.config.POSITION_IDX if self.config.HEDGE_MODE else 0
            }

            if specs.category == 'spot':
                params.pop('reduceOnly', None)

            if order_type == OrderType.LIMIT:
                if entry_price is None:
                    self.logger.error(f"Limit order requires an entry_price. Aborting order for {self.config.SYMBOL}.")
                    return None
                rounded_price = self.precision_manager.round_price(self.config.SYMBOL, entry_price)
                if rounded_price <= 0:
                    self.logger.warning(f"Invalid entry price ({entry_price} rounded to {rounded_price}) for limit order in {self.config.SYMBOL}. Aborting order.")
                    return None
                params["price"] = str(rounded_price)

            if stop_loss_price is not None:
                rounded_sl = self.precision_manager.round_price(self.config.SYMBOL, stop_loss_price)
                if rounded_sl > 0:
                    params["stopLoss"] = str(rounded_sl)
                    params["slOrderType"] = "Market"

            if take_profit_price is not None:
                rounded_tp = self.precision_manager.round_price(self.config.SYMBOL, take_profit_price)
                if rounded_tp > 0:
                    params["takeProfit"] = str(rounded_tp)
                    params["tpOrderType"] = "Limit"

            if "stopLoss" in params or "takeProfit" in params:
                params["tpslMode"] = "Full"

            self.logger.debug(f"Placing order with parameters: {params}")

            response_data = self.api_call(self.bybit_client.place_order, **params)

            if response_data is not None:
                order_id = response_data['orderId']
                order_link_id = response_data.get('orderLinkId', 'N/A')
                self.logger.info(f"Order placed successfully: {side} {rounded_qty} {self.config.SYMBOL} ({order_type.value}), OrderID: {order_id}, OrderLinkId: {order_link_id}")
                if "stopLoss" in params:
                    self.logger.info(f"  Stop Loss set to: {params['stopLoss']}")
                if "takeProfit" in params:
                    self.logger.info(f"  Take Profit set to: {params['takeProfit']}")

                self.open_orders[order_id] = {
                    'symbol': self.config.SYMBOL,
                    'side': side,
                    'qty': rounded_qty,
                    'type': order_type.value,
                    'price': params.get('price'),
                    'stopLoss': params.get('stopLoss'),
                    'takeProfit': params.get('takeProfit'),
                    'status': 'New',
                    'orderLinkId': order_link_id
                }
                return response_data
            else:
                self.logger.error(f"Failed to place order for {self.config.SYMBOL}: API call wrapper returned None.")
                return None

        except Exception as e:
            self.logger.error(f"Exception placing order for {self.config.SYMBOL}: {e}", exc_info=True)
            return None

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific open order."""
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot cancel order {order_id} for {self.config.SYMBOL}: Specs not found.")
            return False

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
        """Fetch and update current positions for the configured symbol."""
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot get positions for {self.config.SYMBOL}: Specs not found.")
            return None

        if specs.category == 'spot':
            self.logger.debug("Position status reset for spot category (no open derivatives positions).")
            self.position_active = False
            self.current_position_side = None
            self.current_position_entry_price = Decimal('0')
            self.current_position_size = Decimal('0')
            self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)
            return None

        try:
            self.logger.debug(f"Fetching positions for {self.config.SYMBOL}...")
            response_data = self.api_call(
                self.bybit_client.get_positions,
                category=specs.category,
                symbol=self.config.SYMBOL
            )

            if response_data is not None:
                positions_list = response_data.get('list', [])
                self.current_positions = {} # Reset current positions for this symbol

                found_position_for_symbol = False
                for pos in positions_list:
                    if Decimal(pos.get('size', '0')) > 0:
                        self.current_positions[pos['symbol']] = pos

                        if pos['symbol'] == self.config.SYMBOL:
                            found_position_for_symbol = True
                            self.position_active = True
                            self.current_position_side = pos['side']
                            self.current_position_entry_price = Decimal(pos.get('avgPrice', '0'))
                            self.current_position_size = Decimal(pos['size'])

                            # Initialize/Update trailing stop if active
                            if self.config.TRAILING_STOP_PCT > 0:
                                mark_price_str = pos.get('markPrice')
                                if mark_price_str:
                                    current_mark_price = Decimal(mark_price_str)
                                    # Always try to update, manager handles activation logic
                                    self.trailing_stop_manager.update_trailing_stop(
                                        symbol=self.config.SYMBOL,
                                        current_price=current_mark_price,
                                        update_exchange=True # Attempt to push updates to exchange
                                    )
                                    # If not initialized, initialize it now
                                    if self.config.SYMBOL not in self.trailing_stop_manager.active_trailing_stops:
                                        self.trailing_stop_manager.initialize_trailing_stop(
                                            symbol=self.config.SYMBOL,
                                            position_side=pos['side'],
                                            entry_price=self.current_position_entry_price,
                                            current_price=current_mark_price,
                                            trail_percent=self.config.TRAILING_STOP_PCT * 100,
                                            activation_percent=self.config.TRAILING_STOP_PCT * 100
                                        )
                                else:
                                    self.logger.warning(f"Mark price not available for {self.config.SYMBOL} position, cannot initialize/update trailing stop.")
                            break # Assume only one position for the target symbol

                if not found_position_for_symbol:
                    if self.position_active:
                        self.logger.info(f"Position for {self.config.SYMBOL} was closed.")
                    self.position_active = False
                    self.current_position_side = None
                    self.current_position_entry_price = Decimal('0')
                    self.current_position_size = Decimal('0')
                    self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)

                self.logger.debug(f"Position status update: Active={self.position_active}, Side={self.current_position_side}, Size={self.current_position_size}, Entry={self.current_position_entry_price}")
                return self.current_positions.get(self.config.SYMBOL) # Return the specific position data

            else:
                self.logger.error(f"Failed to get positions for {self.config.SYMBOL}: API call wrapper returned None.")
                self.position_active = False
                self.current_position_side = None
                self.current_position_entry_price = Decimal('0')
                self.current_position_size = Decimal('0')
                self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)
                return None

        except Exception as e:
            self.logger.error(f"Exception getting positions for {self.config.SYMBOL}: {e}", exc_info=True)
            self.position_active = False
            self.current_position_side = None
            self.current_position_entry_price = Decimal('0')
            self.current_position_size = Decimal('0')
            self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)
            return None


    def close_position(self) -> bool:
        """Close the current open position for the target symbol by placing a Market order."""
        if not self.position_active or not self.current_position_side or self.current_position_size <= 0:
            self.logger.warning(f"No active position or position size is zero to close for {self.config.SYMBOL}.")
            return False

        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot close position for {self.config.SYMBOL}: Specs not found.")
            return False

        if specs.category == 'spot':
            self.logger.warning(f"Attempting to close position for spot symbol {self.config.SYMBOL}. This bot's close_position is designed for derivatives.")
            return False

        try:
            close_side = "Sell" if self.current_position_side == "Buy" else "Buy"

            self.logger.info(f"Attempting to close {self.config.SYMBOL} position ({self.current_position_side} {self.current_position_size} {specs.base_currency}).")
            subprocess.run(["termux-toast", f"Closing {self.config.SYMBOL} position..."])

            result = self.place_order(
                side=close_side,
                qty=self.current_position_size,
                order_type=OrderType.MARKET,
                reduceOnly=True # Ensure this order only reduces existing position
            )

            if result:
                self.logger.info(f"Market order to close {self.config.SYMBOL} position placed successfully.")
                # Fetch position again to get latest PnL after closure attempt
                time.sleep(1) # Give time for order to process
                self.get_positions() # This will update self.position_active etc.

                if not self.position_active: # If get_positions confirms closure
                    # For realized PnL, we'd typically need to fetch order history for the closing order.
                    # For now, we'll use a placeholder and rely on the UI or manual check for exact PnL.
                    realized_pnl = 0.0 # Placeholder
                    current_equity = self.get_account_balance_usdt()
                    self.cumulative_pnl += float(realized_pnl) # Update cumulative PnL with realized PnL
                    self.display_pnl_update(realized_pnl, float(current_equity))

                    self.logger.info(Fore.MAGENTA + f"✅ Position Closed for {self.config.SYMBOL}." + Style.RESET_ALL)
                    subprocess.run(["termux-toast", f"Position Closed: {self.config.SYMBOL}"])

                    if self.sms_notifier.is_enabled:
                        self.sms_notifier.send_pnl_update(realized_pnl, float(current_equity))

                    self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)
                    return True
                else:
                    self.logger.warning(f"Position for {self.config.SYMBOL} still active after closing order. Manual check needed.")
                    return False
            else:
                self.logger.error(f"Failed to place market order to close position for {self.config.SYMBOL}.")
                return False

        except Exception as e:
            self.logger.error(f"Exception closing position for {self.config.SYMBOL}: {e}", exc_info=True)
            return False

    def _get_order_history(self, order_id: str, limit: int = 1) -> List[Dict[str, Any]]:
        """Helper to fetch specific order history details."""
        data = self.api_call(self.bybit_client.get_order_history, symbol=self.config.SYMBOL, orderId=order_id, limit=limit, category=self.config.CATEGORY_ENUM.value)
        return (data or {}).get('list', [])


    # =====================================================================
    # CONSOLE DISPLAY METHODS
    # =====================================================================

    def display_current_price(self, price: float):
        """Display current price with color coding to the console."""
        print(Fore.WHITE + f"Current Price: ${price:.{self.precision_manager.get_decimal_places(self.config.SYMBOL)[0]}f}" + Style.RESET_ALL)

    def display_indicator_values(self, df: pd.DataFrame):
        """Display current indicator values with color coding to the console."""
        if df.empty or len(df) == 0:
            print(Fore.RED + "No data available for indicator display." + Style.RESET_ALL)
            return

        latest = df.iloc[-1]

        ehlers_val = latest.get('ehlers_trend')
        ehlers_color = Fore.GREEN if ehlers_val == 1 else Fore.RED if ehlers_val == -1 else Fore.YELLOW
        print(ehlers_color + f"Ehlers Trend: {ehlers_val}" + Style.RESET_ALL)

        supertrend_dir_val = latest.get('ehlers_supertrend_direction')
        supertrend_dir_color = Fore.GREEN if supertrend_dir_val == 1 else Fore.RED if supertrend_dir_val == -1 else Fore.YELLOW
        print(supertrend_dir_color + f"Ehlers Supertrend Direction: {supertrend_dir_val}" + Style.RESET_ALL)

        supertrend_line_val = latest.get('ehlers_supertrend_line')
        if supertrend_line_val is not None:
             print(supertrend_dir_color + f"Ehlers Supertrend Line: {supertrend_line_val:.{self.precision_manager.get_decimal_places(self.config.SYMBOL)[0]}f}" + Style.RESET_ALL)

        rsi_val = latest.get('rsi')
        rsi_color = Fore.GREEN if rsi_val is not None and 40 <= rsi_val <= 60 else Fore.RED if rsi_val is not None and rsi_val > 70 else Fore.BLUE if rsi_val is not None and rsi_val < 30 else Fore.YELLOW
        print(rsi_color + f"RSI: {rsi_val:.1f}" + Style.RESET_ALL)

        macd_val = latest.get('macd_diff')
        macd_color = Fore.GREEN if macd_val is not None and macd_val > 0 else Fore.RED if macd_val is not None and macd_val < 0 else Fore.YELLOW
        print(macd_color + f"MACD Diff: {macd_val:.4f}" + Style.RESET_ALL)

        print("-" * 30) # Separator

    def display_pnl_update(self, pnl: float, balance: float):
        """Display PNL update with color coding to the console."""
        pnl_color = Fore.GREEN if pnl > 0 else Fore.RED if pnl < 0 else Fore.YELLOW
        balance_color = Fore.GREEN if balance > float(self.initial_equity) else Fore.RED if balance < float(self.initial_equity) else Fore.WHITE

        print(pnl_color + f"Realized P&L: ${pnl:.2f}" + Style.RESET_ALL)
        print(balance_color + f"Current Balance: ${balance:.2f}" + Style.RESET_ALL)
        print(Fore.WHITE + f"Cumulative Realized P&L: ${self.cumulative_pnl:.2f}" + Style.RESET_ALL)
        print("=" * 30) # Separator


    # =====================================================================
    # MAIN EXECUTION LOGIC
    # =====================================================================

    def execute_trade_based_on_signal(self, signal_type: Optional[str], reason: str):
        """
        Execute trades based on the generated signal and current position state.
        Manages opening new positions, closing existing ones based on signal reversal,
        and updating stop losses (including trailing stops).
        """
        # Check if trading is allowed based on cumulative loss limit
        if not self._cumulative_loss_guard():
            self.logger.warning("Cumulative loss limit reached. Skipping trade execution for this cycle.")
            return

        # Fetch current market data (ticker for price)
        ticker = self.get_ticker()
        if not ticker or not ticker.get('lastPrice'):
            self.logger.warning("Could not retrieve ticker data or 'lastPrice'. Cannot execute trade based on signal.")
            return
        current_price = Decimal(ticker['lastPrice'])

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

        # --- State Management & Trade Execution ---

        # 1. Handle Opening New Positions
        if not self.position_active and signal_type in ['BUY', 'SELL']:
            trade_side = signal_type
            self.logger.info(f"Received {trade_side} signal. Reason: {reason}. Attempting to open {trade_side.lower()} position.")
            subprocess.run(["termux-toast", f"Signal: {trade_side} {self.config.SYMBOL}. Reason: {reason}"])

            # Calculate Stop Loss and Take Profit prices
            stop_loss_price, take_profit_price = self.calculate_trade_sl_tp(trade_side, current_price, self.market_data)

            # Calculate position size in base currency units
            position_qty = self.order_sizer.calculate_position_size_usd(
                symbol=self.config.SYMBOL,
                account_balance_usdt=self.account_balance_usdt,
                risk_percent=Decimal(str(self.config.RISK_PER_TRADE_PCT / 100)),
                entry_price=current_price,
                stop_loss_price=stop_loss_price,
                leverage=Decimal(str(self.config.LEVERAGE))
            )

            if position_qty is not None and position_qty > 0:
                if self.config.DRY_RUN:
                    self.logger.info(Fore.YELLOW + f"[DRY RUN] Would place {trade_side} order of {position_qty} {self.config.SYMBOL} at ${current_price:.{self.precision_manager.get_decimal_places(self.config.SYMBOL)[0]}f} | SL: ${stop_loss_price:.{self.precision_manager.get_decimal_places(self.config.SYMBOL)[0]}f}, TP: ${take_profit_price:.{self.precision_manager.get_decimal_places(self.config.SYMBOL)[0]}f} | Reason: {reason}" + Style.RESET_ALL)
                    self.sms_notifier.send_trade_alert(trade_side, self.config.SYMBOL, float(current_price), float(stop_loss_price), float(take_profit_price), f"DRY RUN: {reason}")
                    self.last_trade_time = now_ts # Update cooldown even in dry run
                    self.last_signal = trade_side # Update last signal even in dry run
                    return

                order_result = self.place_order(
                    side=trade_side,
                    qty=position_qty,
                    order_type=self.config.ORDER_TYPE_ENUM,
                    entry_price=current_price if self.config.ORDER_TYPE_ENUM == OrderType.LIMIT else None,
                    stop_loss_price=stop_loss_price,
                    take_profit_price=take_profit_price
                )

                if order_result:
                    # Update internal state tentatively. Real position confirmation comes from get_positions().
                    self.position_active = True
                    self.current_position_side = trade_side
                    self.current_position_entry_price = current_price
                    self.current_position_size = position_qty
                    self.last_trade_time = now_ts
                    self.last_signal = trade_side
                    self.logger.info(f"{trade_side} order placed successfully. Waiting for position confirmation.")
                else:
                    self.logger.error(f"Failed to place {trade_side} order.")
            else:
                self.logger.warning(f"Could not calculate a valid position size for the {trade_side} signal. Skipping order placement.")

        # 2. Handle Managing Existing Positions (Signal Reversal)
        elif self.position_active:
            perform_close = False
            if self.current_position_side == "Buy" and signal_type == 'SELL':
                self.logger.info(f"Signal reversal to SELL detected while in BUY position. Closing position. Reason: {reason}")
                perform_close = True
            elif self.current_position_side == "Sell" and signal_type == 'BUY':
                self.logger.info(f"Signal reversal to BUY detected while in SELL position. Closing position. Reason: {reason}")
                perform_close = True

            if perform_close:
                if self.config.DRY_RUN:
                    self.logger.info(Fore.YELLOW + f"[DRY RUN] Would close {self.current_position_side} position for {self.config.SYMBOL}. Reason: {reason}" + Style.RESET_ALL)
                    self.sms_notifier.send_sms(f"DRY RUN: Close {self.current_position_side} {self.config.SYMBOL}. Reason: {reason}")
                    self.last_trade_time = now_ts
                    self.last_signal = signal_type # Update last signal even in dry run for next cycle
                    return

                if self.close_position():
                    self.logger.info(f"Position for {self.config.SYMBOL} closed successfully due to signal reversal.")
                    self.last_trade_time = now_ts
                    self.last_signal = signal_type # Update last signal after successful closure
                else:
                    self.logger.error(f"Failed to close position for {self.config.SYMBOL} on signal reversal.")

            # 3. Handle Trailing Stop Loss Updates (if not closing position)
            if not perform_close and self.config.TRAILING_STOP_PCT > 0 and specs.category != 'spot':
                current_price_for_ts = current_price
                pos_data = self.current_positions.get(self.config.SYMBOL)
                if pos_data and pos_data.get('markPrice'):
                    current_price_for_ts = Decimal(pos_data['markPrice'])

                self.trailing_stop_manager.update_trailing_stop(
                    symbol=self.config.SYMBOL,
                    current_price=current_price_for_ts,
                    update_exchange=True
                )
        else:
            self.logger.info(Fore.WHITE + "No active position and no new signal to act on." + Style.RESET_ALL)


    def run(self):
        """
        # Initiates the bot's grand operation, starting the WebSocket vigil
        # and managing its continuous market engagement, with graceful shutdown.
        """
        self.logger.info(Fore.LIGHTYELLOW_EX + Style.BRIGHT + f"🚀 Launching Ehlers SuperTrend Bot for {self.config.SYMBOL}! May its journey be prosperous." + Style.RESET_ALL)
        subprocess.run(["termux-toast", f"Ehlers SuperTrend Bot for {self.config.SYMBOL} is commencing its arcane operations."])
        if self.sms_notifier.is_enabled:
            self.sms_notifier.send_sms(f"Ehlers SuperTrend Bot for {self.config.SYMBOL} is commencing its arcane operations.")

        # Start WebSocket connection in a separate thread
        ws_thread = threading.Thread(target=self._connect_websocket_loop, daemon=True)
        ws_thread.start()

        # The main thread now simply waits for a stop event, keeping the bot running continuously
        self.logger.info(Fore.BLUE + "Bot now running continuously, awaiting stop signal (Ctrl+C)." + Style.RESET_ALL)
        self.stop_event.wait() # Block until stop_event is set (e.g., by signal handler)

        self.logger.info(Fore.BLUE + "Bot's main loop gracefully exited. Farewell, seeker." + Style.RESET_ALL)
        self.cleanup() # Perform cleanup after the main loop exits

    def _connect_websocket_loop(self):
        """
        # Establishes and maintains a mystical WebSocket connection,
        # listening for the whispers of new market candles, until a stop signal is received.
        """
        reconnect_attempts = 0
        max_reconnect_attempts = 10
        base_reconnect_delay = 5

        while not self._stop_requested: # Use _stop_requested for this thread
            try:
                self.logger.info(Fore.CYAN + "Attempting to forge WebSocket connection..." + Style.RESET_ALL)
                if self.ws:
                    try:
                        self.ws.exit()
                        self.logger.info(Fore.BLUE + "Previous WebSocket connection closed cleanly." + Style.RESET_ALL)
                    except Exception as e:
                        self.logger.warning(Fore.YELLOW + f"Error closing previous WebSocket: {e}" + Style.RESET_ALL)
                    self.ws = None

                self.ws = WebSocket(testnet=self.config.TESTNET, channel_type="linear")
                self.ws.kline_stream(interval=self.config.TIMEFRAME, symbol=self.config.SYMBOL, callback=self._process_websocket_message)
                self.logger.info(Fore.GREEN + "WebSocket connected and streaming." + Style.RESET_ALL)
                reconnect_attempts = 0

                while not self._stop_requested:
                    time.sleep(1)

            except Exception as e:
                if self._stop_requested:
                    break

                reconnect_attempts += 1
                if reconnect_attempts > max_reconnect_attempts:
                    self.logger.critical(Fore.RED + f"Max reconnect attempts ({max_reconnect_attempts}) reached. Stopping WebSocket thread." + Style.RESET_ALL)
                    self._stop_requested = True # Signal this thread to stop
                    self.stop_event.set() # Signal main thread to stop
                    break

                sleep_time = min(60, base_reconnect_delay * (2 ** (reconnect_attempts - 1)))
                sleep_time *= (1.0 + random.uniform(-0.2, 0.2))
                self.logger.error(Fore.RED + f"WebSocket error: {e}. Reconnecting attempt {reconnect_attempts}/{max_reconnect_attempts} in {sleep_time:.1f}s..." + Style.RESET_ALL)
                time.sleep(sleep_time)

        self.logger.info(Fore.BLUE + "WebSocket loop gracefully exited." + Style.RESET_ALL)


    def _process_websocket_message(self, msg: Dict[str, Any]):
        """
        # The core incantation, triggered by each new confirmed k-line,
        # where market data is transformed into signals and actions.
        """
        if self._stop_requested:
            return

        if "topic" in msg and str(msg["topic"]).startswith(f"kline.{self.config.TIMEFRAME}.{self.config.SYMBOL}"):
            kline = msg['data'][0]
            if not kline['confirm']:
                return # Only process confirmed (closed) candles

            ts, close_price = int(kline['start']), float(kline['close'])
            if ts <= self.last_kline_ts:
                return # Skip duplicate or old candle data
            self.last_kline_ts = ts

            self.logger.info(Fore.LIGHTMAGENTA_EX + f"--- New Confirmed Candle [{datetime.fromtimestamp(ts/1000)}] ---" + Style.RESET_ALL)

            # Fetch market data (historical klines) to ensure enough lookback for indicators
            self.market_data = self.fetch_klines(limit=self.config.LOOKBACK_PERIODS)
            if self.market_data.empty:
                self.logger.warning(Fore.YELLOW + "Failed to retrieve market data for signal generation. Awaiting next candle." + Style.RESET_ALL)
                return

            self.market_data = self.calculate_indicators(self.market_data)
            if self.market_data.empty:
                self.logger.warning(Fore.YELLOW + "Indicators could not be calculated due to insufficient data. Awaiting next candle." + Style.RESET_ALL)
                return

            # Display current price and indicators (console-only)
            current_price_float = float(self.market_data['close'].iloc[-1])
            self.display_current_price(current_price_float)
            self.display_indicator_values(self.market_data)

            signal_type, reason = self.generate_signal(self.market_data)
            self.logger.info(Fore.WHITE + f"Signal: {signal_type or 'NONE'} | Reason: {reason}" + Style.RESET_ALL)

            # Refresh position state before making trading decisions
            self.get_positions()

            # Execute trades based on the generated signal and current position state
            self.execute_trade_based_on_signal(signal_type, reason)


    def cleanup(self):
        """Perform cleanup actions before exiting the bot. Enhanced with optional auto-close."""
        self.logger.info("Starting bot cleanup process...")
        try:
            # Cancel all open orders to prevent unintended trades upon restart or shutdown
            self.logger.info("Cancelling all open orders...")
            self.cancel_all_orders()

            # Optionally close any open positions if configured
            if self.config.AUTO_CLOSE_ON_SHUTDOWN and self.position_active and self.current_position_size > 0:
                self.logger.warning(f"Auto-close on shutdown enabled. Closing open position ({self.current_position_side} {self.current_position_size} {self.config.SYMBOL}).")
                self.close_position()
            else:
                if self.position_active:
                    self.logger.warning(f"Bot shutting down with open position ({self.current_position_side} {self.current_position_size} {self.config.SYMBOL}). Manual intervention may be required.")

            # Final summary of bot's performance
            final_balance = self.get_account_balance_usdt() # Fetch latest balance
            total_pnl = final_balance - self.initial_equity
            total_pnl_pct = (total_pnl / self.initial_equity * 100) if self.initial_equity > 0 else Decimal('0')

            self.logger.info("=" * 60)
            self.logger.info("Ehlers SuperTrend Trading Bot Stopped.")
            self.logger.info(f"Final Balance: {final_balance:.4f} USDT")
            self.logger.info(f"Total PnL: {total_pnl:.4f} USDT ({total_pnl_pct:.4f}%)")
            self.logger.info("=" * 60)
            subprocess.run(["termux-toast", "Ehlers Bot: Shut down. Check logs for summary."])

        except Exception as e:
            self.logger.error(f"An error occurred during the cleanup process: {e}", exc_info=True)


# =====================================================================
# MAIN ENTRY POINT
# =====================================================================

def main():
    """Main function to initialize and run the bot."""
    try:
        # --- Load and Validate Configuration ---
        config = Config()

        # --- Initialize and Run Bot ---
        bot = EhlersSuperTrendBot(config)
        bot.run()

    except Exception as e:
        # Catch any unhandled exceptions during bot initialization or execution
        print(f"\nFATAL ERROR: An unhandled exception occurred: {e}")
        # Attempt to log the critical error if the logger is available
        try:
            # If bot object was partially initialized, try to use its logger
            if 'bot' in locals() and hasattr(bot, 'logger') and bot.logger:
                bot.logger.critical(f"FATAL ERROR: {e}", exc_info=True)
            else: # Otherwise, use a basic logger for fatal errors
                logging.basicConfig(level=logging.CRITICAL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                logging.critical(f"FATAL ERROR: {e}", exc_info=True)
        except Exception as log_e:
            print(f"Error occurred while trying to log fatal error: {log_e}")

        sys.exit(1) # Exit with a non-zero status code to indicate failure


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
def parse_to_utc(dt_str: str) -> datetime:
    """
    # An incantation to transmute a date/time string from any known locale
    # or timezone into a pure, naive UTC datetime object.
    # It drops timezone info with replace(tzinfo=None) for consistency after conversion.
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
    TESTNET: bool = field(default=True)
    # Trading Configuration
    SYMBOL: str = field(default="BTCUSDT")
    CATEGORY: str = field(default="linear")
    LEVERAGE: int = field(default=5)
    HEDGE_MODE: bool = field(default=False)
    POSITION_IDX: int = field(default=0) # 0=One-way mode, 1=Long, 2=Short in hedge mode
    # Position Sizing
    RISK_PER_TRADE_PCT: float = field(default=1.0) # Risk % of account balance per trade
    MAX_POSITION_SIZE_USD: float = field(default=10000.0) # Max position value in USD
    MIN_POSITION_SIZE_USD: float = field(default=10.0) # Min position value in USD
    # Strategy Parameters
    TIMEFRAME: str = field(default="15") # Kline interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)
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
    ADX_WINDOW: int = field(default=14) # Added ADX_WINDOW to config
    # Risk Management
    STOP_LOSS_PCT: float = field(default=0.015) # 1.5% stop loss from entry
    TAKE_PROFIT_PCT: float = field(default=0.03) # 3% take profit from entry
    TRAILING_STOP_PCT: float = field(default=0.005) # 0.5% trailing stop from highest profit
    MAX_DAILY_LOSS_PCT: float = field(default=0.05) # 5% max daily loss from start balance
    # Execution Settings
    ORDER_TYPE: str = field(default="Market")
    TIME_IN_FORCE: str = field(default="GTC")
    REDUCE_ONLY: bool = field(default=False)
    # Bot Settings
    LOOP_INTERVAL_SEC: int = field(default=60) # Check interval in seconds
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
    SIGNAL_COOLDOWN_SEC: int = field(default=60)
    SIGNAL_CONFIRM_BARS: int = field(default=1)

    def __post_init__(self):
        """Load configuration from environment variables and validate."""
        self.API_KEY = os.getenv("BYBIT_API_KEY", self.API_KEY)
        self.API_SECRET = os.getenv("BYBIT_API_SECRET", self.API_SECRET)
        self.TESTNET = os.getenv("BYBIT_TESTNET", str(self.TESTNET)).lower() in ['true', '1', 't']
        self.SYMBOL = os.getenv("TRADING_SYMBOL", self.SYMBOL) # Use TRADING_SYMBOL
        self.CATEGORY = os.getenv("BYBIT_CATEGORY", self.CATEGORY)
        self.LEVERAGE = int(os.getenv("BYBIT_LEVERAGE", self.LEVERAGE))
        self.HEDGE_MODE = os.getenv("BYBIT_HEDGE_MODE", str(self.HEDGE_MODE)).lower() in ['true', '1', 't']
        self.POSITION_IDX = int(os.getenv("BYBIT_POSITION_IDX", self.POSITION_IDX))
        self.RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", self.RISK_PER_TRADE_PCT))
        self.MAX_POSITION_SIZE_USD = float(os.getenv("BYBIT_MAX_POSITION_SIZE_USD", self.MAX_POSITION_SIZE_USD))
        self.MIN_POSITION_SIZE_USD = float(os.getenv("BYBIT_MIN_POSITION_SIZE_USD", self.MIN_POSITION_SIZE_USD))
        self.TIMEFRAME = os.getenv("TRADING_TIMEFRAME", self.TIMEFRAME) # Use TRADING_TIMEFRAME
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
        self.ADX_WINDOW = int(os.getenv("ADX_WINDOW", self.ADX_WINDOW)) # Load ADX_WINDOW
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
            print("\nERROR: Bybit API Key or Secret not configured. Please set BYBIT_API_KEY and BYBIT_API_SECRET environment variables,")
            print("or update the corresponding .env file or default values in the Config class.")
            sys.exit(1)
        # Validate positionIdx for hedge mode
        if self.HEDGE_MODE and self.POSITION_IDX not in [0, 1, 2]:
            print(f"Configuration Error: Invalid POSITION_IDX '{self.POSITION_IDX}'. Must be 0, 1, or 2.")
            sys.exit(1)
        # Force leverage to 1 for spot trading to avoid potential API errors or incorrect settings
        if self.CATEGORY_ENUM == Category.SPOT:
            self.LEVERAGE = 1

# =====================================================================
# INSTRUMENT SPECS DATACLASS
# =====================================================================
@dataclass
class InstrumentSpecs:
    symbol: str
    category: str
    base_currency: str
    quote_currency: str
    status: str
    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal
    min_order_qty: Decimal
    max_order_qty: Decimal
    qty_step: Decimal
    min_leverage: Decimal
    max_leverage: Decimal
    leverage_step: Decimal
    max_position_value: Decimal # Max quantity in quote currency (e.g., USD for USDT pairs)
    min_position_value: Decimal # Min quantity in quote currency
    contract_value: Decimal
    is_inverse: bool
    maker_fee: Decimal
    taker_fee: Decimal

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
                self.logger.error(f"Exception during loading of {category} instruments: {e}")
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
        
        # Max/Min Order Amount for position value limits
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
        if step == Decimal('0'): # Changed to Decimal('0')
            return value
        try:
            # Calculate the number of steps. Use floor division for consistent rounding down.
            num_steps = (value / step).quantize(Decimal('1'), rounding=ROUND_DOWN)
            rounded_value = num_steps * step
            # Ensure the number of decimal places for the final value matches the step's precision
            # Only if the step itself has decimal places
            if step.as_tuple().exponent < 0:
                rounded_value = rounded_value.quantize(Decimal(f'1e{step.as_tuple().exponent}'), rounding=ROUND_DOWN)
            return rounded_value
        except Exception as e:
            self.logger.error(f"Error rounding decimal value {value} with step {step}: {e}", exc_info=True)
            return value # Return original value if rounding fails

    def round_price(self, symbol: str, price: float | Decimal) -> Decimal:
        """Round price to correct tick size, ensuring it's within min/max price bounds."""
        specs = self.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot round price for {symbol}: Specs not found.")
            return Decimal('0')
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
            self.logger.error(f"Cannot round quantity for {symbol}: Specs not found.")
            return Decimal('0')
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
    def __init__(self, precision_manager: PrecisionManager, logger: logging.Logger):
        self.precision = precision_manager
        self.logger = logger

    def calculate_position_size_usd(
        self,
        symbol: str,
        account_balance_usdt: Decimal,
        risk_percent: Decimal,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        leverage: Decimal
    ) -> Optional[Decimal]:
        """
        Calculate position size in base currency units based on fixed risk percentage, leverage,
        entry price, and stop loss price. Returns None if calculation is not possible.
        """
        specs = self.precision.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot calculate position size for {symbol}: Specs not found.")
            return None
        # --- Input Validation ---
        if account_balance_usdt <= Decimal('0'): # Changed to Decimal
            self.logger.warning(f"Account balance is zero or negative ({account_balance_usdt}). Cannot calculate position size.")
            return None
        if entry_price <= Decimal('0'): # Changed to Decimal
            self.logger.warning(f"Entry price is zero or negative ({entry_price}). Cannot calculate position size.")
            return None
        if leverage <= Decimal('0'): # Changed to Decimal
            self.logger.warning(f"Leverage is zero or negative ({leverage}). Cannot calculate position size.")
            return None
        stop_distance_price = abs(entry_price - stop_loss_price)
        if stop_distance_price <= Decimal('0'): # Changed to Decimal
            self.logger.warning(f"Stop loss distance is zero or negative ({stop_distance_price}). Cannot calculate position size.")
            return None
        
        # --- Calculations ---
        # Calculate risk amount in USDT
        risk_amount_usdt = account_balance_usdt * risk_percent
        
        # Calculate stop loss distance in percentage terms
        stop_distance_pct = stop_distance_price / entry_price
        
        # Calculate the required position value in USDT to risk 'risk_amount_usdt'
        if stop_distance_pct > Decimal('0'): # Changed to Decimal
            position_value_needed_usd = risk_amount_usdt / stop_distance_pct
        else:
            self.logger.warning("Stop distance percentage is zero. Cannot calculate required position value.")
            return None
        
        # Apply leverage to determine the maximum tradeable position value based onaccount balance
        max_tradeable_value_usd = account_balance_usdt * leverage
        
        # Cap the needed position value by maximum tradeable value and Bybit's max position value limits
        position_value_usd = min(
            position_value_needed_usd,
            max_tradeable_value_usd,
            specs.max_position_value # Apply Bybit's specific max order value if available
        )
        
        # Ensure minimum position value is met
        if position_value_usd < specs.min_position_value:
            self.logger.warning(f"Calculated position value ({position_value_usd:.{self.precision.get_decimal_places(symbol)[0]}f} USD) is below minimum ({specs.min_position_value:.{self.precision.get_decimal_places(symbol)[0]}f} USD). Using minimum.")
            position_value_usd = specs.min_position_value
        
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
        if final_quantity <= Decimal('0'): # Changed to Decimal
            self.logger.warning(f"Calculated final quantity is zero or negative ({final_quantity}). Cannot proceed with order.")
            return None
        
        # Recalculate actual risk based on final quantity and compare against allowed risk
        actual_position_value_usd = final_quantity * entry_price
        actual_risk_amount_usdt = actual_position_value_usd * stop_distance_pct
        actual_risk_percent = (actual_risk_amount_usdt / account_balance_usdt) * Decimal('100') if account_balance_usdt > Decimal('0') else Decimal('0') # Changed to Decimal
        self.logger.debug(f"Order Sizing for {symbol}: Entry={entry_price}, SL={stop_loss_price}, Risk%={risk_percent:.4f}")
        self.logger.debug(f"  Calculated Qty={quantity_base:.8f} {specs.base_currency}, Rounded Qty={final_quantity:.8f}")
        self.logger.debug(f"  Position Value={position_value_usd:.4f} USD, Actual Risk={actual_risk_amount_usdt:.4f} USDT ({actual_risk_percent:.4f}%)")
        return final_quantity

# =====================================================================
# TERMUX SMS NOTIFIER
# =====================================================================
class TermuxSMSNotifier:
    """
    # A digital carrier pigeon to send urgent messages via Termux SMS,
    # alerting the wizard directly on their Android device.
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
            subprocess.run(["termux-sms-send", "-n", self.recipient_number, message])
            self.logger.info(Fore.GREEN + f"SMS sent to {self.recipient_number}: {message[:50]}..." + Style.RESET_ALL)
        except FileNotFoundError:
            self.logger.error(Fore.RED + "Termux command 'termux-sms-send' not found. Is 'pkg install termux-api' installed?" + Style.RESET_ALL)
        except subprocess.CalledProcessError as e:
            self.logger.error(Fore.RED + f"Termux SMS command failed with error: {e}" + Style.RESET_ALL)
        except Exception as e:
            self.logger.error(Fore.RED + f"Failed to send Termux SMS: {e}" + Style.RESET_ALL)
            
    def send_trade_alert(self, side, symbol, price, sl, tp, reason):
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
    # A specialized client to commune directly with Bybit API v5 endpoints,\n
    # returning raw responses for the bot's api_call to interpret.\n
    """
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True, default_category: str = 'linear'):
        self.session = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret)
        self._default_category = default_category
    def get_server_time(self) -> Dict[str, Any]:
        """Fetches server time (used for credential validation)."""
        return self.session.get_server_time()
    def get_instruments_info(self, symbol: Optional[str] = None, category: Optional[str] = None) -> Dict[str, Any]:
        """List active trading symbols and product info."""
        params = {'category': category or self._default_category}
        if symbol:
            params['symbol'] = symbol
        return self.session.get_instruments_info(**params)
    def get_wallet_balance(self, accountType: str = 'UNIFIED') -> Dict[str, Any]:
        """Fetches wallet balances."""
        return self.session.get_wallet_balance(accountType=accountType)
    def get_kline(self, symbol: str, interval: str, limit: int = 200, category: Optional[str] = None) -> Dict[str, Any]:
        """Fetches historical candlestick data."""
        return self.session.get_kline(category=category or self._default_category, symbol=symbol, interval=interval, limit=limit)
    def get_positions(self, symbol: Optional[str] = None, category: Optional[str] = None) -> Dict[str, Any]:
        """Lists active positions."""
        params = {'category': category or self._default_category}
        if symbol:
            params['symbol'] = symbol
        return self.session.get_positions(**params)
    def place_order(self, symbol: str, side: str, orderType: str,
                   qty: str,
                   price: Optional[str] = None, stopLoss: Optional[str] = None,
                   takeProfit: Optional[str] = None, reduceOnly: bool = False,
                   category: Optional[str] = None, timeInForce: str = "GTC",
                   closeOnTrigger: bool = False, positionIdx: int = 0,
                   slOrderType: Optional[str] = None, tpOrderType: Optional[str] = None,
                   tpslMode: Optional[str] = None) -> Dict[str, Any]:
        """Places a new order."""
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
        if price is not None: params['price'] = price
        if stopLoss is not None:
            params['stopLoss'] = stopLoss
            if slOrderType: params['slOrderType'] = slOrderType
        if takeProfit is not None:
            params['takeProfit'] = takeProfit
            if tpOrderType: params['tpOrderType'] = tpOrderType
        if tpslMode is not None: params['tpslMode'] = tpslMode
        return self.session.place_order(**params)
    def set_trading_stop(self, symbol: str, side: str, callbackRate: Optional[str] = None,
                       stopLoss: Optional[str] = None, takeProfit: Optional[str] = None,
                       category: Optional[str] = None, slOrderType: Optional[str] = None,
                       tpOrderType: Optional[str] = None) -> Dict[str, Any]: # Added tpOrderType for consistency
        """Manages TP/SL/Trailing Stops."""
        params = {
            'category': category or self._default_category,
            'symbol': symbol,
            'side': side # Side is required for set_trading_stop on unified account
        }
        if callbackRate is not None: params['callbackRate'] = callbackRate
        if stopLoss is not None:
            params['stopLoss'] = stopLoss
            if slOrderType: params['slOrderType'] = slOrderType
        if takeProfit is not None:
            params['takeProfit'] = takeProfit
            if tpOrderType: params['tpOrderType'] = tpOrderType
        return self.session.set_trading_stop(**params)
    def get_order_history(self, symbol: str, orderId: Optional[str] = None, limit: int = 50,
                         category: Optional[str] = None) -> Dict[str, Any]:
        """Fetches order history."""
        params = {'category': category or self._default_category, 'symbol': symbol, 'limit': limit}
        if orderId: params['orderId'] = orderId
        return self.session.get_order_history(**params)
    def get_open_orders(self, symbol: str, orderId: Optional[str] = None, limit: int = 50,
                      category: Optional[str] = None) -> Dict[str, Any]:
        """Fetches currently open orders."""
        params = {'category': category or self._default_category, 'symbol': symbol, 'limit': limit}
        if orderId: params['orderId'] = orderId
        return self.session.get_open_orders(**params)
    def cancel_order(self, category: str, symbol: str, orderId: str) -> Dict[str, Any]:
        """Cancels a specific order."""
        return self.session.cancel_order(category=category, symbol=symbol, orderId=orderId)
    def cancel_all_orders(self, category: str, symbol: str) -> Dict[str, Any]:
        """Cancels all open orders for a symbol."""
        return self.session.cancel_all_orders(category=category, symbol=symbol)
    def set_leverage(self, category: str, symbol: str, buyLeverage: str, sellLeverage: str) -> Dict[str, Any]:
        """Sets leverage for a symbol."""
        return self.session.set_leverage(category=category, symbol=symbol, buyLeverage=buyLeverage, sellLeverage=sellLeverage)
    def get_tickers(self, category: str, symbol: str) -> Dict[str, Any]:
        """Fetches ticker information."""
        return self.session.get_tickers(category=category, symbol=symbol)

# =====================================================================
# TrailingStopManager (Stub, as it was in original code)
# This class needs a full implementation if trailing stops are to be used.
# For the purpose of UI, we'll assume it exists and manages state.
# =====================================================================
class TrailingStopManager:
    def __init__(self, bybit_session: HTTP, precision_manager: PrecisionManager, logger: logging.Logger, api_call_wrapper: Any):
        self.bybit_session = bybit_session
        self.precision_manager = precision_manager
        self.logger = logger
        self.api_call = api_call_wrapper
        self._trailing_stop_data: Dict[str, Dict[str, Decimal]] = {} # {symbol: {'active_price': Decimal, 'trail_offset_usd': Decimal}}

    def initialize_trailing_stop(self, symbol: str, position_side: str, entry_price: Decimal, current_price: Decimal, trail_percent: float, activation_percent: float):
        specs = self.precision_manager.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot initialize trailing stop for {symbol}: Specs not found.")
            return

        trail_rate_str = str(trail_percent) # Bybit API expects percentage as a string, e.g., "0.3" for 0.3%

        try:
            # Set the trailing stop. Note: Bybit's set_trading_stop with callbackRate sets a trailing stop percentage.
            # It starts trailing once the price moves enough in profit.
            response = self.api_call(
                self.bybit_session.set_trading_stop,
                category=specs.category,
                symbol=symbol,
                side=position_side, # Must specify side for unified account
                callbackRate=trail_rate_str
            )
            if response is not None:
                self.logger.info(f"Trailing stop for {symbol} initialized/updated with callbackRate: {trail_rate_str}%")
                # Store enough info to manage it internally if needed
                self._trailing_stop_data[symbol] = {
                    'entry_price': entry_price,
                    'position_side': position_side,
                    'trail_percent': Decimal(str(trail_percent)),
                    'activation_percent': Decimal(str(activation_percent)),
                    'last_trail_price': current_price # Keep track of where it last trailed from
                }
            else:
                self.logger.error(f"Failed to set trailing stop for {symbol}.")
        except Exception as e:
            self.logger.error(f"Error setting trailing stop for {symbol}: {e}")

    def update_trailing_stop(self, symbol: str, current_price: Decimal, update_exchange: bool = False):
        # Bybit's API usually handles the "trailing" part automatically once a callbackRate is set.
        # This method would primarily be for internal state tracking or if a complex custom trailing logic is needed.
        # For simplicity with Bybit API's callbackRate, this might not need to update the exchange frequently
        # unless you want to *modify* the callback rate or reactivate it if it was somehow cancelled.

        # The initialize_trailing_stop already sets the callbackRate.
        # We can update `last_trail_price` internally for tracking.
        if symbol in self._trailing_stop_data:
            self._trailing_stop_data[symbol]['last_trail_price'] = current_price
            self.logger.debug(f"Internal trailing stop data for {symbol} updated. Last known price: {current_price}")
        
        if update_exchange:
            # Re-setting the trailing stop with the same parameters effectively just re-confirms it.
            # Only do this if strictly necessary (e.g., if you suspect it got cancelled).
            # Otherwise, the exchange manages it.
            data = self._trailing_stop_data.get(symbol)
            if data:
                self.initialize_trailing_stop(
                    symbol=symbol,
                    position_side=data['position_side'],
                    entry_price=data['entry_price'],
                    current_price=current_price,
                    trail_percent=float(data['trail_percent']),
                    activation_percent=float(data['activation_percent'])
                )

    def remove_trailing_stop(self, symbol: str):
        # To remove a trailing stop, one would typically set stopLoss or takeProfit directly,
        # or cancel any existing conditional orders that implement trailing stop logic.
        # If `set_trading_stop` was used with `callbackRate`, setting SL/TP to 0 might remove it.
        # This is a complex area and depends on Bybit's exact behavior. For now, we clear internal state.
        if symbol in self._trailing_stop_data:
            del self._trailing_stop_data[symbol]
            self.logger.info(f"Internal trailing stop data for {symbol} cleared.")
            # Actual API call to remove trailing stop would go here if Bybit provided a direct "remove trailing stop" endpoint
            # or if setting SL/TP to 0 overrides it.

# =====================================================================
# GLOBAL LOGGER SETUP
# =====================================================================
def setup_logger(config: Config):
    """
    # Forging the logger to chronicle the bot's journey,
    # with vibrant console hues and a steadfast log file (both plain and JSON).
    """
    logger = logging.getLogger("EhlersBot")
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler) # Remove existing handlers to prevent duplicate logs
        
    logger.setLevel(config.LOG_LEVEL.upper())
    
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
logger = logging.getLogger("EhlersBot") # This will be reconfigured later by EhlersSuperTrendBot.__init__

# =====================================================================
# BotState: Shared state for UI and bot logic
# =====================================================================
@dataclass
class BotState:
    """
    # A shared scroll containing the bot's current market perception and state,
    # ensuring that all modules, especially the UI, can read consistent data.
    """
    lock: threading.Lock = field(default_factory=threading.Lock) # Guards against simultaneous writes from different threads
    
    current_price: Decimal = field(default=Decimal('0.0'))
    bid_price: Decimal = field(default=Decimal('0.0'))
    ask_price: Decimal = field(default=Decimal('0.0'))
    
    ehlers_supertrend_value: Decimal = field(default=Decimal('0.0')) # The actual ST line value
    ehlers_supertrend_direction: str = field(default="NONE") # e.g., "UP", "DOWN"
    ehlers_filter_value: Decimal = field(default=Decimal('0.0')) # From Ehlers Adaptive Trend custom filter
    
    adx_value: Decimal = field(default=Decimal('0.0'))
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

# =====================================================================
# BotUI: Renders the console UI
# =====================================================================
class BotUI(threading.Thread):
    """
    # A visual spell to display the bot's current state and market insights
    # directly in the terminal, updating continuously without disturbing the bot's operations.
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
            status_text_display = f"Status: {Fore.GREEN}{state.bot_status} ({'TESTNET' if BYBIT_TESTNET else 'MAINNET'}){Fore.CYAN}"
            last_update_text = f"Last Updated: {state.last_updated_time.strftime('%H:%M:%S')}"
            # Calculate padding dynamically
            padding_len = 73 - (len(status_text_display.replace(Fore.GREEN, '').replace(Fore.CYAN, '').replace('(', '').replace(')', '')) + len(last_update_text))
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
            print(f"{Fore.MAGENTA}║ Ehlers SuperTrend:      {ehlers_color}{ehlers_st_display_str}{Fore.MAGENTA:<{73 - len('Ehlers SuperTrend:      ') - len(ehlers_st_display_str)}}║{Style.RESET_ALL}")
            
            ehlers_filter_str = f"{state.ehlers_filter_value:.2f}"
            print(f"{Fore.MAGENTA}║ Ehlers Filter:          {Fore.WHITE}{ehlers_filter_str}{Fore.MAGENTA:<{73 - len('Ehlers Filter:          ') - len(ehlers_filter_str)}}║{Style.RESET_ALL}")
            
            adx_str = f"{state.adx_value:.1f} (Trend: {state.adx_trend_strength})"
            print(f"{Fore.MAGENTA}║ ADX:                    {adx_color}{adx_str}{Fore.MAGENTA:<{73 - len('ADX:                    ') - len(adx_str)}}║{Style.RESET_ALL}")
            
            rsi_str = f"{state.rsi_value:.1f} (State: {state.rsi_state})"
            print(f"{Fore.MAGENTA}║ RSI:                    {rsi_color}{rsi_str}{Fore.MAGENTA:<{73 - len('RSI:                    ') - len(rsi_str)}}║{Style.RESET_ALL}")

            # MACD (3 decimals for all MACD components)
            print(f"{Fore.MAGENTA}║ MACD:                   {Fore.WHITE}{state.macd_value:.3f}{Fore.MAGENTA:<{73 - len('MACD:                   ') - len(f'{state.macd_value:.3f}')}}║{Style.RESET_ALL}")
            print(f"{Fore.MAGENTA}║ MACD Signal:            {Fore.WHITE}{state.macd_signal_value:.3f}{Fore.MAGENTA:<{73 - len('MACD Signal:            ') - len(f'{state.macd_signal_value:.3f}')}}║{Style.RESET_ALL}")
            print(f"{Fore.MAGENTA}║ MACD Diff:              {Fore.WHITE}{state.macd_diff_value:.3f}{Fore.MAGENTA:<{73 - len('MACD Diff:              ') - len(f'{state.macd_diff_value:.3f}')}}║{Style.RESET_ALL}")

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
            print(f"{Fore.GREEN}║ Current Equity:         {equity_color}{current_equity_display_str}{Fore.GREEN:<{73 - len('Current Equity:         ') - len(current_equity_display_str) + len(Fore.GREEN) + len(Style.RESET_ALL)}}║{Style.RESET_ALL}")
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
                print(f"{Fore.GREEN}║ Stop Loss:              {Fore.WHITE}$0.000 (N/A){Fore.GREEN:<{73 - len('Stop Loss:              ') - len('$0.000 (N/A)')}}║{Style.RESET_ALL}")
                print(f"{Fore.GREEN}║ Take Profit:            {Fore.WHITE}$0.000 (N/A){Fore.GREEN:<{73 - len('Take Profit:            ') - len('$0.000 (N/A)')}}║{Style.RESET_ALL}")

            else:
                # Consistent padding for "no open position" state
                # Adjust formatting to use Decimal('0.0') for consistency and correct precision padding
                print(f"║ Open Position:          {Fore.WHITE}{Decimal('0.0'):.{state.qty_precision}f} {state.symbol}{Fore.GREEN:<{73 - len('Open Position:          ') - len(f'{Decimal('0.0'):.{state.qty_precision}f} {state.symbol}')}}║{Style.RESET_ALL}")
                print(f"║ Avg Entry Price:        {Fore.WHITE}${Decimal('0.0'):.{state.price_precision}f}{Fore.GREEN:<{73 - len('Avg Entry Price:        ') - len(f'${Decimal('0.0'):.{state.price_precision}f}')}}║{Style.RESET_ALL}")
                print(f"║ Unrealized PNL:         {Fore.WHITE}${Decimal('0.0'):.2f} ({Decimal('0.0'):+.2f}%){Fore.GREEN:<{73 - len('Unrealized PNL:         ') - len(f'${Decimal('0.0'):.2f} ({Decimal('0.0'):+.2f}%)')}}║{Style.RESET_ALL}")
                print(f"║ Stop Loss:              {Fore.WHITE}${Decimal('0.0'):.{state.price_precision}f} (N/A){Fore.GREEN:<{73 - len('Stop Loss:              ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")
                print(f"║ Take Profit:            {Fore.WHITE}${Decimal('0.0'):.{state.price_precision}f} (N/A){Fore.GREEN:<{73 - len('Take Profit:            ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")

            realized_pnl_str = f"${state.realized_pnl_total:.2f}" # Realized PNL to 2 decimals
            print(f"{Fore.GREEN}║                                                                           {Fore.GREEN}║{Style.RESET_ALL}")
            print(f"{Fore.GREEN}║ Realized PNL (Total):   {pnl_color_realized}{realized_pnl_str}{Fore.GREEN:<{73 - len('Realized PNL (Total):   ') - len(realized_pnl_str) + len(pnl_color_realized) + len(Style.RESET_ALL)}}║{Style.RESET_ALL}")
            print(f"{Fore.GREEN}╚═══════════════════════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
            print(Style.RESET_ALL) # Ensure all colors are reset at the end


# =====================================================================
# MAIN TRADING BOT CLASS
# =====================================================================
class EhlersSuperTrendBot:
    def __init__(self, config: Config):
        self.config = config
        # Initial logger setup for early messages, will be reconfigured by config later
        global logger
        logger = setup_logger(config)
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
        
        # --- Managers Initialization ---
        # PrecisionManager needs the raw HTTP session
        self.precision_manager = PrecisionManager(self.bybit_client.session, self.logger)
        self.order_sizer = OrderSizingCalculator(self.precision_manager, self.logger)
        # TrailingStopManager needs the bot's api_call wrapper
        # The `api_call` method of the bot will be passed, ensuring resilience
        self.trailing_stop_manager = TrailingStopManager(self.bybit_client.session, self.precision_manager, self.logger, self.api_call)
        
        # --- Termux SMS Notifier ---
        self.sms_notifier = TermuxSMSNotifier(
            recipient_number=self.config.TERMUX_SMS_RECIPIENT_NUMBER,
            logger=self.logger,
            price_precision=self.precision_manager.get_decimal_places(self.config.SYMBOL)[0] # Pass int precision
        )
        
        # --- Data Storage ---
        self.market_data: pd.DataFrame = pd.DataFrame()
        self.current_positions: Dict[str, dict] = {} # {symbol: position_data}
        self.open_orders: Dict[str, dict] = {} # {order_id: order_data}
        self.account_balance_usdt: Decimal = Decimal('0.0')
        self.initial_equity: Decimal = Decimal('0.0') 
        
        # --- Strategy State ---
        self.position_active: bool = False
        self.current_position_side: Optional[str] = None # 'Buy' or 'Sell'
        self.current_position_entry_price: Decimal = Decimal('0')
        self.current_position_size: Decimal = Decimal('0')
        self.last_signal: Optional[str] = None # Changed to str to match generate_signal output
        self.last_kline_ts: int = 0 # For last processed confirmed candle
        self.last_trade_time: float = 0.0 # For trade cooldown
        self.cumulative_pnl: Decimal = Decimal('0.0') # Total realized PnL for cumulative loss guard

        # --- Update BotState with initial config ---
        with self.bot_state.lock:
            self.bot_state.symbol = self.config.SYMBOL
            self.bot_state.timeframe = self.config.TIMEFRAME
            self.bot_state.dry_run = self.config.TESTNET # Dry run usually associated with testnet for demo
            self.bot_state.bot_status = "Initialized"
            # Precision is updated by get_symbol_precision below

        # --- Initializations & Validations ---
        self.precision_manager.get_decimal_places(self.config.SYMBOL) # Load precision for the symbol and update bot_state
        self._validate_api_credentials() # Test API connection and keys
        self._validate_symbol_timeframe() # Validate symbol and timeframe
        self._capture_initial_equity() # Capture initial equity for cumulative loss protection
        if self.config.CATEGORY_ENUM == Category.SPOT:
            self.logger.info(f"Leverage set to 1 for SPOT category as it's not applicable.")
        else:
            self.set_leverage() # Set leverage for derivatives
        self.logger.info(f"Bot Configuration Loaded:")
        self.logger.info(f"  Mode: {'Testnet' if self.config.TESTNET else 'Mainnet'}")
        self.logger.info(f"  Symbol: {self.config.SYMBOL}, Category: {self.config.CATEGORY_ENUM.value}")
        self.logger.info(f"  Leverage: {self.config.LEVERAGE}x")
        self.logger.info(f"  Hedge Mode: {self.config.HEDGE_MODE}, PositionIdx: {self.config.POSITION_IDX}")
        self.logger.info(f"  Timeframe: {self.config.TIMEFRAME}, Lookback: {self.config.LOOKBACK_PERIODS} periods")
        self.logger.info(f"  Loop Interval: {self.config.LOOP_INTERVAL_SEC}s")
        if self.sms_notifier.is_enabled:
            self.sms_notifier.send_sms(f"Ehlers SuperTrend Bot for {self.config.SYMBOL} is commencing its arcane operations.")

    def _validate_api_credentials(self):
        """Validate API credentials and test connection."""
        try:
            # Prefer a private endpoint that implies full auth
            data = self.api_call(self.bybit_client.get_wallet_balance, accountType='UNIFIED')
            if data is None: # If get_wallet_balance failed, try get_positions
                _ = self.api_call(self.bybit_client.get_positions, symbol=self.config.SYMBOL) 
            self.logger.info(Fore.GREEN + f"API credentials validated. Environment: {'Testnet' if self.config.TESTNET else 'Mainnet'}." + Style.RESET_ALL)
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"Ehlers Bot: API keys validated. Environment: {'Testnet' if self.config.TESTNET else 'Mainnet'}.")
        except SystemExit: # Catch the SystemExit from api_call for fatal errors
            raise
        except Exception as e:
            self.logger.critical(Fore.RED + f"API credential validation failed: {e}. Ensure keys are correct and have appropriate permissions." + Style.RESET_ALL)
            subprocess.run(["termux-toast", f"CRITICAL: API credential validation failed for {self.config.SYMBOL}: {e}"])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"CRITICAL: API credential validation failed for {self.config.SYMBOL}: {e}")
            sys.exit(1) # Halt the bot if validation fails

    def _validate_symbol_timeframe(self):
        """Validate symbol and timeframe."""
        valid_intervals = {"1","3","5","15","30","60","120","240","360","720","D","W","M"}
        if str(self.config.TIMEFRAME) not in valid_intervals:
            self.logger.critical(Fore.RED + f"Invalid timeframe '{self.config.TIMEFRAME}'. Must be one of {sorted(valid_intervals)}. Exiting." + Style.RESET_ALL)
            subprocess.run(["termux-toast", f"Invalid Timeframe: {self.config.TIMEFRAME}"])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"CRITICAL: Invalid timeframe '{self.config.TIMEFRAME}' for {self.config.SYMBOL}. Exiting.")
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
        """Capture initial equity for cumulative loss protection enchantment."""
        eq = self.get_account_balance_usdt()
        if eq > Decimal('0'): # Changed to Decimal
            self.initial_equity = eq
            with self.bot_state.lock:
                self.bot_state.initial_equity = eq # Update BotState
            self.logger.info(Fore.GREEN + f"Initial equity set to {self.initial_equity:.4f} USDT." + Style.RESET_ALL)
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"Bot session started. Initial Equity: ${self.initial_equity:.2f}")
        else:
            self.logger.warning(Fore.YELLOW + "Could not fetch initial equity or equity is zero; cumulative loss guard will use PnL fallback logic." + Style.RESET_ALL)

    def get_account_balance_usdt(self) -> Decimal:
        """Get current account balance in USDT."""
        try:
            data = self.api_call(self.bybit_client.get_wallet_balance, accountType='UNIFIED')
            if data is not None: # check for None after api_call
                balances = data.get('list', []) # result is already extracted by api_call
                if balances:
                    for coin_data in balances:
                        if coin_data.get('coin') == 'USDT':
                            balance = Decimal(coin_data.get('walletBalance', '0'))
                            self.account_balance_usdt = balance
                            with self.bot_state.lock: # Update BotState
                                self.bot_state.current_equity = balance
                            self.logger.debug(f"Successfully fetched account balance: {balance:.4f} USDT")
                            return balance
                self.logger.warning(f"No USDT balance returned in response for {self.config.SYMBOL}.")
                return Decimal('0')
            else:
                self.logger.error(f"Failed to get account balance for {self.config.SYMBOL}: API call wrapper returned None.")
                return Decimal('0')
        except Exception as e:
            self.logger.error(f"Exception getting account balance for {self.config.SYMBOL}: {e}", exc_info=True)
            return Decimal('0')

    def api_call(self, api_method: Any, **kwargs) -> Optional[Dict[str, Any]]:
        """
        # A resilient incantation to invoke pybit HTTP methods,
        # equipped with retries, exponential backoff (with jitter), and wise error handling.
        # It guards against transient network whispers and rate limit enchantments.
        # Returns the 'result' data dictionary on success.
        """
        for attempt in range(1, self.config.MAX_API_RETRIES + 1):
            try:
                raw_resp = api_method(**kwargs)
                result_data = self._handle_bybit_response(raw_resp)
                if result_data is not None: # Success, return the extracted result
                    return result_data
            except PermissionError as e:
                self.logger.critical(Fore.RED + f"Fatal API error: {e}. Exiting bot." + Style.RESET_ALL)
                sys.exit(1) # Halt the bot immediately
            except (ConnectionRefusedError, RuntimeError, FailedRequestError, InvalidRequestError) as e:
                if attempt == self.config.MAX_API_RETRIES:
                    self.logger.error(Fore.RED + f"API call failed after {self.config.MAX_API_RETRIES} attempts: {e}" + Style.RESET_ALL)
                    return None
                sleep_time = min(60.0, self.config.API_RETRY_DELAY_SEC * (2 ** (attempt - 1)))
                sleep_time *= (1.0 + random.uniform(-0.2, 0.2)) # Add jitter for backoff retry
                self.logger.warning(Fore.YELLOW + f"API transient error: {e} | Retrying {attempt}/{self.config.MAX_API_RETRIES} in {sleep_time:.1f}s" + Style.RESET_ALL)
                time.sleep(sleep_time)
            except Exception as e:
                if attempt == self.config.MAX_API_RETRIES:
                    self.logger.error(Fore.RED + f"API call exhausted retries due to unexpected error: {e}" + Style.RESET_ALL)
                    return None
                sleep_time = min(60.0, self.config.API_RETRY_DELAY_SEC * (2 ** (attempt - 1)))
                sleep_time *= (1.0 + random.uniform(-0.2, 0.2)) # Add jitter for backoff retry
                self.logger.warning(Fore.YELLOW + f"API unexpected exception: {e} | Retrying {attempt}/{self.config.MAX_API_RETRIES} in {sleep_time:.1f}s" + Style.RESET_ALL)
                time.sleep(sleep_time)
        self.logger.error(Fore.RED + "API call exhausted retries without success." + Style.RESET_ALL)
        return None

    def _handle_bybit_response(self, response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        # Parses Bybit API JSON response, enforcing success checks and raising
        # specific exceptions for known error codes.
        # Returns the 'result' field on success.
        """
        if not isinstance(response, dict):
            self.logger.error(Fore.RED + f"Unexpected API response format: {type(response).__name__}, expected a dict." + Style.RESET_ALL)
            raise ValueError("Unexpected API response format, expected a dict")
        
        ret_code = response.get('retCode')
        ret_msg = response.get('retMsg', 'No message provided') if response else 'No response'
        result = response.get('result')
        
        if ret_code != 0:
            # Common authentication / permission errors
            if ret_code in {10001, 10002, 10003, 10004, 10005, 130006}: 
                self.logger.critical(Fore.RED + f"Fatal Bybit API authentication error {ret_code}: {ret_msg}." + Style.RESET_ALL)
                subprocess.run(["termux-toast", f"Ehlers Bot: Fatal API Auth Error {ret_code}"])
                if self.sms_notifier.is_enabled:
                    self.sms_notifier.send_sms(f"CRITICAL: Bybit API authentication error {ret_code} for {self.config.SYMBOL}: {ret_msg}")
                sys.exit(1) # Halt the bot if authentication fails
            
            # Rate limit error
            if ret_code == 130014: # Example Bybit rate limit code
                self.logger.warning(Fore.YELLOW + f"Bybit API rate limit reached {ret_code}: {ret_msg}." + Style.RESET_ALL)
                raise ConnectionRefusedError(f"Bybit API rate limit reached: {ret_msg}")
                
            # Other general API errors
            self.logger.error(Fore.RED + f"Bybit API returned error {ret_code}: {ret_msg}." + Style.RESET_ALL)
            subprocess.run(["termux-toast", f"Ehlers Bot: API Error {ret_code}"])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"ERROR: Bybit API error {ret_code} for {self.config.SYMBOL}: {ret_msg}")
            raise RuntimeError(f"Bybit API returned error {ret_code}: {ret_msg}")
        
        # Even if retCode is 0, ensure 'result' field exists for data calls
        if result is None:
            self.logger.warning(Fore.YELLOW + "Bybit API response missing 'result' field despite success code. Returning empty dict." + Style.RESET_ALL)
            return {}
        
        return result

    def set_leverage(self) -> bool:
        """Set leverage for the trading symbol, respecting min/max/step limits."""
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot set leverage for {self.config.SYMBOL}: Specs not found.")
            return False
        if specs.category == 'spot':
            self.logger.info(Fore.BLUE + "Leverage set to 1 for SPOT category as it's not applicable." + Style.RESET_ALL)
            return True
        try:
            leverage_to_set_decimal = Decimal(str(self.config.LEVERAGE))
            min_lev = specs.min_leverage
            max_lev = specs.max_leverage
            leverage_step = specs.leverage_step
            if leverage_to_set_decimal < min_lev:
                self.logger.warning(f"Requested leverage {leverage_to_set_decimal} for {self.config.SYMBOL} is below minimum {min_lev}. Setting to minimum.")
                leverage_to_set_decimal = min_lev
            elif leverage_to_set_decimal > max_lev:
                self.logger.warning(f"Requested leverage {leverage_to_set_decimal} for {self.config.SYMBOL} exceeds maximum {max_lev}. Setting to maximum.")
                leverage_to_set_decimal = max_lev
            if leverage_step > Decimal('0'): # Changed to Decimal
                num_steps = (leverage_to_set_decimal / leverage_step).quantize(Decimal('1'), rounding=ROUND_DOWN)
                leverage_to_set_decimal = num_steps * leverage_step
                leverage_to_set_decimal = max(min_lev, min(leverage_to_set_decimal, max_lev))
            leverage_str = str(leverage_to_set_decimal)
            response_data = self.api_call(
                self.bybit_client.set_leverage,
                category=specs.category,
                symbol=self.config.SYMBOL,
                buyLeverage=leverage_str,
                sellLeverage=leverage_str
            )
            if response_data is not None:
                self.logger.info(f"Leverage set successfully to {leverage_str}x for {self.config.SYMBOL}.")
                return True
            else:
                self.logger.error(f"Failed to set leverage for {self.config.SYMBOL}: API call wrapper returned None.")
                return False
        except Exception as e:
            self.logger.error(f"Exception setting leverage for {self.config.SYMBOL}: {e}", exc_info=True)
            return False

    # =====================================================================
    # TECHNICAL INDICATORS
    # =====================================================================
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        # Applies all required indicators to the DataFrame,
        # weaving complex patterns from the raw market energies with enhanced robustness.
        """
        # Ensure sufficient data
        min_len = max(self.config.EHLERS_LENGTH + self.config.SMOOTHING_LENGTH + 5,
                      self.config.EHLERS_ST_LENGTH + 5,
                      self.config.MACD_SLOW + self.config.MACD_SIGNAL + 5,
                      self.config.RSI_WINDOW + 5,
                      self.config.ADX_WINDOW + 5, # Use config for ADX_WINDOW
                      60) # A reasonable minimum for most TA indicators
        if len(df) < min_len:
            self.logger.warning(Fore.YELLOW + f"Not enough data for indicators (have {len(df)}, need {min_len}). Returning DataFrame with NaNs for indicators." + Style.RESET_ALL)
            # Ensure indicator columns exist and are filled with NaN if data is insufficient
            # Added 'supertrend_line_value' for the actual line, not just direction
            for col in ["ehlers_trend", "supertrend_direction", "supertrend_line_value", "ehlers_filter", "rsi", "macd", "macd_signal", "macd_diff", "adx", "adx_plus_di", "adx_minus_di"]:
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
        volatility = vol_series.rolling(self.config.EHLERS_LENGTH, min_periods=max(1, self.config.EHLERS_LENGTH//2)).std().ewm(span=self.config.SMOOTHING_LENGTH, adjust=False).mean()
        
        raw_trend = np.where(df['close'] > (filt + (volatility * self.config.SENSITIVITY)), 1,
                             np.where(df['close'] < (filt - (volatility * self.config.SENSITIVITY)), -1, np.nan))
        df['ehlers_trend'] = pd.Series(raw_trend, index=df.index).ffill() # Fill NaNs forward

        # --- SuperTrend (using ta.volatility.SuperTrend, parameters from Ehlers ST config) ---
        st_indicator = ta.volatility.SuperTrend(
            df['high'], df['low'], df['close'],
            window=self.config.EHLERS_ST_LENGTH,
            multiplier=self.config.EHLERS_ST_MULTIPLIER,
            fillna=True # Fill NaNs in the output Series directly
        )
        df['supertrend_direction'] = st_indicator.super_trend_indicator()
        
        # SuperTrend line value: if direction is UP, it's super_trend_lower, else super_trend_upper
        df['supertrend_line_value'] = np.where(
            df['supertrend_direction'] == 1,
            st_indicator.super_trend_lower(),
            st_indicator.super_trend_upper()
        )

        # Additional Filters - RSI: Measuring the momentum's fervor
        rsi = ta.momentum.RSIIndicator(df['close'], window=self.config.RSI_WINDOW, fillna=True)
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
        
        # Drop rows where indicators are NaN (remove initial NaN rows, after fillna)
        required_indicator_cols = ['ehlers_trend', 'supertrend_direction', 'supertrend_line_value', 'ehlers_filter', 'rsi', 'macd', 'macd_signal', 'macd_diff', 'adx', 'adx_plus_di', 'adx_minus_di']
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
        # Generates a potent trading signal by harmonizing the whispers of multiple indicators,
        # seeking confluence for optimal entry and exit points, with optional bar confirmation.
        # Returns the signal ('BUY'/'SELL'/None) and a detailed reason string.
        """
        # Ensure enough data for comparison and confirmation
        if len(df) < max(2, self.config.SIGNAL_CONFIRM_BARS + 1):
            return None, "Insufficient data for signal generation."
        
        latest = df.iloc[-1]
        second_latest = df.iloc[-2]

        # Ensure values are not NaN before comparison
        if any(pd.isna(latest[col]) for col in ['ehlers_trend', 'supertrend_direction', 'rsi', 'macd_diff']):
            return None, "Latest indicator values are NaN, cannot generate signal."
        if any(pd.isna(second_latest[col]) for col in ['ehlers_trend', 'macd_diff']):
            return None, "Second latest indicator values are NaN, cannot generate signal."

        # Individual conditions
        ehlers_flip_up = latest['ehlers_trend'] == 1 and second_latest['ehlers_trend'] == -1
        ehlers_flip_down = latest['ehlers_trend'] == -1 and second_latest['ehlers_trend'] == 1
        ehlers_supertrend_is_bullish = latest['supertrend_direction'] == 1
        ehlers_supertrend_is_bearish = latest['supertrend_direction'] == -1
        rsi_over_50 = latest['rsi'] > 50
        rsi_under_50 = latest['rsi'] < 50
        macd_cross_up = latest['macd_diff'] > 0 and second_latest['macd_diff'] < 0
        macd_cross_down = latest['macd_diff'] < 0 and second_latest['macd_diff'] > 0
        
        # Combined signal with all filters: The true incantation
        buy_conditions_met = []
        if ehlers_flip_up: buy_conditions_met.append(f"Ehlers Trend flipped UP (Current: {int(latest['ehlers_trend'])})")
        if ehlers_supertrend_is_bullish: buy_conditions_met.append(f"Supertrend is BULLISH (Direction: {int(latest['supertrend_direction'])})")
        if rsi_over_50: buy_conditions_met.append(f"RSI ({latest['rsi']:.1f}) > 50")
        if macd_cross_up: buy_conditions_met.append(f"MACD Diff ({latest['macd_diff']:.4f}) crossed UP")

        sell_conditions_met = []
        if ehlers_flip_down: sell_conditions_met.append(f"Ehlers Trend flipped DOWN (Current: {int(latest['ehlers_trend'])})")
        if ehlers_supertrend_is_bearish: sell_conditions_met.append(f"Supertrend is BEARISH (Direction: {int(latest['supertrend_direction'])})")
        if rsi_under_50: sell_conditions_met.append(f"RSI ({latest['rsi']:.1f}) < 50")
        if macd_cross_down: sell_conditions_met.append(f"MACD Diff ({latest['macd_diff']:.4f}) crossed DOWN")
        
        # Combined signal with all filters: The true incantation
        if (ehlers_flip_up and ehlers_supertrend_is_bullish and rsi_over_50 and macd_cross_up):
            reason = "BUY Signal: " + ", ".join(buy_conditions_met)
            return 'BUY', reason
        elif (ehlers_flip_down and ehlers_supertrend_is_bearish and rsi_under_50 and macd_cross_down):
            reason = "SELL Signal: " + ", ".join(sell_conditions_met)
            return 'SELL', reason
        
        return None, "No clear signal, market is calm."

    # =====================================================================
    # TRADE EXECUTION
    # =====================================================================
    def execute_trade_based_on_signal(self, signal_type: Optional[str], reason: str):
        """
        Execute trades based on the generated signal and current position state.
        Manages opening new positions, closing existing ones, and updating stop losses.
        """
        # Check if trading is allowed based on cumulative loss protection
        if not self._cumulative_loss_guard():
            self.logger.warning("Cumulative loss limit reached. Skipping trade execution for this cycle.")
            return
        
        # Refresh position state before making trading decisions
        # This will also update bot_state with latest position info
        self.get_positions() 
        
        # Trade Cooldown Check
        now_ts = time.time()
        if now_ts - self.last_trade_time < self.config.SIGNAL_COOLDOWN_SEC:
            self.logger.info(Fore.LIGHTBLACK_EX + f"Trade cooldown active ({self.config.SIGNAL_COOLDOWN_SEC}s). Skipping trade execution." + Style.RESET_ALL)
            return
        
        # Get current mark price for SL/TP calculation (use latest data from df if available)
        current_market_price = Decimal(str(self.market_data['close'].iloc[-1])) if not self.market_data.empty else Decimal('0.0')
        if current_market_price == Decimal('0.0'):
             self.logger.warning(Fore.YELLOW + "Current market price is 0. Cannot execute trade." + Style.RESET_ALL)
             return

        # State Management & Trade Execution
        # 1. Handle Opening New Positions
        if not self.position_active and signal_type in ['BUY', 'SELL']:
            trade_side = signal_type
            self.logger.info(f"Received {trade_side} signal. Reason: {reason}. Attempting to open {trade_side.lower()} position.")
            subprocess.run(["termux-toast", f"Signal: {trade_side} {self.config.SYMBOL}. Reason: {reason}"])
            
            # Calculate Stop Loss and Take Profit prices (based on current_market_price)
            stop_loss_price, take_profit_price = self.calculate_trade_sl_tp(trade_side, current_market_price) # Pass Decimal current_market_price

            # Calculate position size in base currency units
            position_qty = self.order_sizer.calculate_position_size_usd(
                symbol=self.config.SYMBOL,
                account_balance_usdt=self.account_balance_usdt,
                risk_percent=Decimal(str(self.config.RISK_PER_TRADE_PCT / 100)),
                entry_price=current_market_price,
                stop_loss_price=stop_loss_price,
                leverage=Decimal(str(self.config.LEVERAGE))
            )
            
            if position_qty is not None and position_qty > Decimal('0'): # Changed to Decimal
                if self.config.DRY_RUN:
                    self.logger.info(Fore.YELLOW + f"[DRY RUN] Would place {trade_side} order of {position_qty:.{self.bot_state.qty_precision}f} {self.config.SYMBOL} at ${current_market_price:.{self.bot_state.price_precision}f} | SL: ${stop_loss_price:.{self.bot_state.price_precision}f}, TP: ${take_profit_price:.{self.bot_state.price_precision}f} | Reason: {reason}" + Style.RESET_ALL)
                    self.sms_notifier.send_trade_alert(trade_side, self.config.SYMBOL, float(current_market_price), float(stop_loss_price), float(take_profit_price), reason)
                    self.last_trade_time = now_ts
                    self.last_signal = trade_side
                    # Simulate updating bot_state for dry run
                    with self.bot_state.lock:
                        self.bot_state.open_position_qty = position_qty
                        self.bot_state.open_position_side = trade_side
                        self.bot_state.open_position_entry_price = current_market_price
                        self.bot_state.unrealized_pnl = Decimal('0.0') # Start with 0 PnL
                        self.bot_state.unrealized_pnl_pct = Decimal('0.0')
                    return

                order_result = self.place_order(
                    side=trade_side,
                    qty=position_qty,
                    order_type=self.config.ORDER_TYPE_ENUM,
                    entry_price=current_market_price if self.config.ORDER_TYPE_ENUM == OrderType.LIMIT else None,
                    stopLoss=stop_loss_price,
                    takeProfit=take_profit_price
                )
                if order_result:
                    # Update internal state tentatively. Real position confirmation comes from get_positions().
                    self.position_active = True
                    self.current_position_side = trade_side
                    self.current_position_entry_price = current_market_price # Assuming market order fills at this price for now
                    self.current_position_size = position_qty
                    self.last_trade_time = now_ts
                    self.last_signal = trade_side
                    self.logger.info(f"{trade_side} order placed successfully. Waiting for position confirmation.")
                    # Update BotState with new position
                    with self.bot_state.lock:
                        self.bot_state.open_position_qty = position_qty
                        self.bot_state.open_position_side = trade_side
                        self.bot_state.open_position_entry_price = current_market_price # Use initial market price until filled price is known
                        self.bot_state.unrealized_pnl = Decimal('0.0') # Starts at 0
                        self.bot_state.unrealized_pnl_pct = Decimal('0.0')
                else:
                    self.logger.error(f"Failed to place {trade_side} order.")
            else:
                self.logger.warning(f"Could not calculate a valid position size for the {trade_side} signal. Skipping order placement.")
        
        # 2. Handle Managing Existing Positions (Signal Reversal)
        elif self.position_active:
            perform_close = False
            if self.current_position_side == "Buy" and signal_type == 'SELL':
                self.logger.info(f"Signal reversal to SELL detected while in BUY position. Closing position. Reason: {reason}")
                perform_close = True
            elif self.current_position_side == "Sell" and signal_type == 'BUY':
                self.logger.info(f"Signal reversal to BUY detected while in SELL position. Closing position. Reason: {reason}")
                perform_close = True
            
            if perform_close:
                if self.config.DRY_RUN:
                    self.logger.info(Fore.YELLOW + f"[DRY RUN] Would close {self.current_position_side} position for {self.config.SYMBOL}. Reason: {reason}" + Style.RESET_ALL)
                    self.sms_notifier.send_sms(f"DRY RUN: Close {self.current_position_side} {self.config.SYMBOL}. Reason: {reason}")
                    self.last_trade_time = now_ts
                    self.last_signal = signal_type
                    # Simulate closing position for UI
                    with self.bot_state.lock:
                        self.bot_state.open_position_qty = Decimal('0.0')
                        self.bot_state.open_position_side = "NONE"
                        self.bot_state.open_position_entry_price = Decimal('0.0')
                        self.bot_state.unrealized_pnl = Decimal('0.0')
                        self.bot_state.unrealized_pnl_pct = Decimal('0.0')
                    return
                if self.close_position(): # This method will update cumulative_pnl and bot_state
                    self.logger.info(f"Position for {self.config.SYMBOL} closed successfully due to signal reversal.")
                    self.last_trade_time = now_ts
                    self.last_signal = signal_type
                    return
            
            # 3. Handle Trailing Stop Updates (if not closing position)
            # Make sure trailing stop logic respects SPOT category.
            if not perform_close and self.config.TRAILING_STOP_PCT > 0 and self.config.CATEGORY_ENUM != Category.SPOT:
                pos_data = self.current_positions.get(self.config.SYMBOL)
                if pos_data and pos_data.get('markPrice'):
                    current_price_for_ts = Decimal(pos_data['markPrice'])
                else:
                    current_price_for_ts = current_market_price
                self.trailing_stop_manager.update_trailing_stop(
                    symbol=self.config.SYMBOL,
                    current_price=current_price_for_ts,
                    update_exchange=True
                )
        else:
            self.logger.info(Fore.WHITE + "No active position and no new signal to act on." + Style.RESET_ALL)

    def get_positions(self) -> Optional[Dict[str, dict]]:
        """Fetch and update current position data for the configured symbol."""
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.warning(f"Cannot get positions for {self.config.SYMBOL}: Specs not found.")
            return None
        if specs.category == 'spot':
            self.logger.info(Fore.BLUE + "Position status reset for spot category (no open derivatives positions)." + Style.RESET_ALL)
            self.position_active = False
            self.current_position_side = None
            self.current_position_entry_price = Decimal('0')
            self.current_position_size = Decimal('0')
            self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)
            # Clear BotState position info
            with self.bot_state.lock:
                self.bot_state.open_position_qty = Decimal('0.0')
                self.bot_state.open_position_side = "NONE"
                self.bot_state.open_position_entry_price = Decimal('0.0')
                self.bot_state.unrealized_pnl = Decimal('0.0')
                self.bot_state.unrealized_pnl_pct = Decimal('0.0')
            return None
        
        try:
            self.logger.debug(f"Fetching positions for {self.config.SYMBOL}...")
            response_data = self.api_call(
                self.bybit_client.get_positions,
                category=specs.category,
                symbol=self.config.SYMBOL
            )
            
            if response_data is not None:
                positions_list = response_data.get('list', []) # 'list' is directly in 'result' from api_call
                
                found_position = False
                for pos in positions_list:
                    if Decimal(pos['size']) > Decimal('0'): # Changed to Decimal
                        self.current_positions[pos['symbol']] = pos
                        if pos['symbol'] == self.config.SYMBOL:
                            self.position_active = True
                            self.current_position_side = pos['side']
                            self.current_position_entry_price = Decimal(pos['avgPrice'])
                            self.current_position_size = Decimal(pos['size'])
                            found_position = True

                            # Update BotState position info
                            with self.bot_state.lock:
                                self.bot_state.open_position_qty = Decimal(pos['size'])
                                self.bot_state.open_position_side = pos['side']
                                self.bot_state.open_position_entry_price = Decimal(pos['avgPrice'])
                                self.bot_state.unrealized_pnl = Decimal(pos.get('unrealisedPnl', '0.0')) # Ensure Decimal
                                # Calculate unrealized PnL percentage for UI
                                pos_value = Decimal(pos['size']) * Decimal(pos['avgPrice'])
                                if pos_value > Decimal('0'):
                                    self.bot_state.unrealized_pnl_pct = (self.bot_state.unrealized_pnl / pos_value) * Decimal('100')
                                else:
                                    self.bot_state.unrealized_pnl_pct = Decimal('0.0')

                            # Initialize/Update trailing stop if active
                            if self.config.TRAILING_STOP_PCT > 0:
                                current_mark_price = Decimal(pos.get('markPrice', '0'))
                                self.trailing_stop_manager.initialize_trailing_stop(
                                    symbol=self.config.SYMBOL,
                                    position_side=pos['side'],
                                    entry_price=self.current_position_entry_price,
                                    current_price=current_mark_price,
                                    trail_percent=self.config.TRAILING_STOP_PCT * 100, # Convert to percentage for callbackRate
                                    activation_percent=self.config.TRAILING_STOP_PCT * 100 # Can be same as trail
                                )
                                self.logger.info(f"Initialized and activated trailing stop for {self.config.SYMBOL} ({pos['side']})")
                            break # Assume only one position for the target symbol
                
                if not found_position: # No position found or size is 0
                    self.position_active = False
                    self.current_position_side = None
                    self.current_position_entry_price = Decimal('0')
                    self.current_position_size = Decimal('0')
                    self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)
                    # Clear BotState position info
                    with self.bot_state.lock:
                        self.bot_state.open_position_qty = Decimal('0.0')
                        self.bot_state.open_position_side = "NONE"
                        self.bot_state.open_position_entry_price = Decimal('0.0')
                        self.bot_state.unrealized_pnl = Decimal('0.0')
                        self.bot_state.unrealized_pnl_pct = Decimal('0.0')
                    self.logger.debug(f"No active position found for {self.config.SYMBOL}.")
                
                self.logger.debug(f"Position status updated: Active={self.position_active}")
                return self.current_positions.get(self.config.SYMBOL) # Return the specific position data
            else:
                self.logger.error(f"Failed to get positions for {self.config.SYMBOL}: API call wrapper returned None.")
                # Ensure state is reset on API failure
                self.position_active = False
                self.current_position_side = None
                self.current_position_entry_price = Decimal('0')
                self.current_position_size = Decimal('0')
                self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)
                with self.bot_state.lock:
                        self.bot_state.open_position_qty = Decimal('0.0')
                        self.bot_state.open_position_side = "NONE"
                        self.bot_state.open_position_entry_price = Decimal('0.0')
                        self.bot_state.unrealized_pnl = Decimal('0.0')
                        self.bot_state.unrealized_pnl_pct = Decimal('0.0')
                return None

        except Exception as e:
            self.logger.error(f"Exception getting positions for {self.config.SYMBOL}: {e}", exc_info=True)
            self.position_active = False
            self.current_position_side = None
            self.current_position_entry_price = Decimal('0')
            self.current_position_size = Decimal('0')
            self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)
            with self.bot_state.lock: # Also clear BotState on error
                self.bot_state.open_position_qty = Decimal('0.0')
                self.bot_state.open_position_side = "NONE"
                self.bot_state.open_position_entry_price = Decimal('0.0')
                self.bot_state.unrealized_pnl = Decimal('0.0')
                self.bot_state.unrealized_pnl_pct = Decimal('0.0')
            return None

    def calculate_trade_sl_tp(self, side: str, price: Decimal) -> Tuple[Decimal, Decimal]:
        """
        Calculates Stop Loss and Take Profit levels based on percentage.
        Now takes Decimal price and returns Decimal SL/TP.
        """
        sl_pct_decimal = Decimal(str(self.config.STOP_LOSS_PCT))
        tp_pct_decimal = Decimal(str(self.config.TAKE_PROFIT_PCT))
        
        if side == 'Buy':
            stop_loss = price * (Decimal('1') - sl_pct_decimal)
            take_profit = price * (Decimal('1') + tp_pct_decimal)
        else: # Sell
            stop_loss = price * (Decimal('1') + sl_pct_decimal)
            take_profit = price * (Decimal('1') - tp_pct_decimal)

        # Round to appropriate price precision
        stop_loss = self.precision_manager.round_price(self.config.SYMBOL, stop_loss)
        take_profit = self.precision_manager.round_price(self.config.SYMBOL, take_profit)

        self.logger.info(Fore.LIGHTMAGENTA_EX + f"Calculated SL/TP: SL=${stop_loss:.{self.bot_state.price_precision}f}, TP=${take_profit:.{self.bot_state.price_precision}f}" + Style.RESET_ALL)
        return stop_loss, take_profit

    # =====================================================================
    # ORDER MANAGEMENT
    # =====================================================================
    def place_order(self, side: str, qty: Decimal, order_type: OrderType,
                   entry_price: Optional[Decimal] = None, stopLoss: Optional[Decimal] = None, # Renamed for clarity in place_order
                   takeProfit: Optional[Decimal] = None, reduce_only: bool = False,
                   category: Optional[str] = None, time_in_force: str = "GTC",
                   close_on_trigger: bool = False, position_idx: int = 0,
                   sl_order_type: Optional[str] = None, tp_order_type: Optional[str] = None,
                   tpsl_mode: Optional[str] = None) -> Optional[dict]:
        """Place an order on Bybit, handling precision and Bybit V5 API parameters."""
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot place order for {self.config.SYMBOL}: Specs not found.")
            return None
        
        rounded_qty = self.precision_manager.round_quantity(self.config.SYMBOL, qty)
        if rounded_qty <= Decimal('0'): # Changed to Decimal
            self.logger.warning(f"Rounded quantity is zero or negative ({rounded_qty}). Cannot place order.")
            return None
        
        try:
            # Convert Decimal values to string for API
            str_qty = str(rounded_qty)
            str_price = str(self.precision_manager.round_price(self.config.SYMBOL, entry_price)) if entry_price else None
            str_stopLoss = str(self.precision_manager.round_price(self.config.SYMBOL, stopLoss)) if stopLoss else None
            str_takeProfit = str(self.precision_manager.round_price(self.config.SYMBOL, takeProfit)) if takeProfit else None

            self.logger.info(f"Placing order for {self.config.SYMBOL}: Side={side}, Qty={str_qty}, Type={order_type.value}, "
                             f"Price={str_price}, SL={str_stopLoss}, TP={str_takeProfit}, ReduceOnly={reduce_only}")
            
            order_data = self.api_call(
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
                timeInForce=time_in_force,
                closeOnTrigger=close_on_trigger,
                positionIdx=position_idx,
                slOrderType=sl_order_type,
                tpOrderType=tp_order_type,
                tpslMode=tpsl_mode
            )
            
            if order_data and order_data.get('orderId'):
                order_id = order_data['orderId']
                self.logger.info(Fore.GREEN + f"Order placed with ID: {order_id}. Verifying execution..." + Style.RESET_ALL)
                
                # --- VERIFY ORDER EXECUTION --- 
                time.sleep(1) # Small delay for exchange processing
                order_details = self.api_call(self.bybit_client.get_order_history, symbol=self.config.SYMBOL, orderId=order_id)
                
                if order_details and order_details.get('list') and order_details['list'][0].get('orderStatus') in ('Filled', 'PartiallyFilled'):
                    filled_order = order_details['list'][0]
                    avg_price_str = filled_order.get('avgPrice')
                    filled_price = Decimal(avg_price_str) if avg_price_str and Decimal(avg_price_str) > Decimal('0') else (entry_price or Decimal(self.market_data['close'].iloc[-1])) # Fallback
                    filled_qty = Decimal(filled_order.get('cumExecQty', '0'))
                    
                    self.logger.info(Fore.GREEN + f"✅ Order FILLED: {side} {filled_qty:.{self.bot_state.qty_precision}f} {self.config.SYMBOL} at avg ${filled_price:.{self.bot_state.price_precision}f} (Order ID: {order_id})" + Style.RESET_ALL)
                    subprocess.run(["termux-toast", f"Order FILLED: {side} {self.config.SYMBOL} at {filled_price:.{self.bot_state.price_precision}f}"])
                    if self.sms_notifier.is_enabled:
                        self.sms_notifier.send_trade_alert(side, self.config.SYMBOL, float(filled_price), float(stopLoss or Decimal('0')), float(takeProfit or Decimal('0')), reason)
                    return order_data
                else:
                    status = order_details['list'][0].get('orderStatus', 'Unknown') if order_details and order_details.get('list') else 'Unknown'
                    self.logger.error(Fore.RED + f"Order {order_id} placed but NOT FILLED. Status: {status}. Manual intervention may be required." + Style.RESET_ALL)
                    subprocess.run(["termux-toast", f"Order NOT FILLED: {self.config.SYMBOL} (ID: {order_id})"])
                    if self.sms_notifier.is_enabled:
                        self.sms_notifier.send_sms(f"CRITICAL: Order {order_id} for {self.config.SYMBOL} NOT FILLED! Status: {status}.")
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
    
    def close_position(self) -> bool:
        """
        # Closes the currently open position, gracefully retreating from the market.
        # Updates cumulative_pnl and bot_state.
        """
        current_pos = self.current_positions.get(self.config.SYMBOL)
        if not current_pos or Decimal(current_pos['size']) == Decimal('0'): # Changed to Decimal
            self.logger.warning(Fore.YELLOW + "No active position to close." + Style.RESET_ALL)
            return False
        
        side_to_close = 'Sell' if current_pos['side'] == 'Buy' else 'Buy'
        qty_to_close = self.precision_manager.round_quantity(self.config.SYMBOL, Decimal(current_pos['size'])) # Ensure Decimal and rounded
        
        try:
            self.logger.info(f"Attempting to close {current_pos['side']} position of {qty_to_close} {self.config.SYMBOL}...")
            
            close_order_data = self.api_call(
                self.bybit_client.place_order,
                symbol=self.config.SYMBOL,
                side=side_to_close,
                orderType='Market',
                qty=str(qty_to_close),
                reduceOnly=True, # Ensures this order only reduces existing position
                category=self.config.CATEGORY_ENUM.value
            )
            
            if close_order_data and close_order_data.get('orderId'):
                order_id = close_order_data['orderId']
                self.logger.info(Fore.GREEN + f"Close order placed with ID: {order_id}. Verifying execution..." + Style.RESET_ALL)
                
                # Verify order execution
                time.sleep(1) # Small delay for exchange processing
                order_details = self.api_call(self.bybit_client.get_order_history, symbol=self.config.SYMBOL, orderId=order_id)
                
                if order_details and order_details.get('list') and order_details['list'][0].get('orderStatus') in ('Filled', 'PartiallyFilled'):
                    pnl_realized = Decimal(current_pos.get('unrealisedPnl', '0.0')) # Use unrealized PnL at the moment of closing
                    self.cumulative_pnl += pnl_realized 
                    
                    self.logger.info(Fore.MAGENTA + f"✅ Position Closed: {side_to_close} {qty_to_close:.{self.bot_state.qty_precision}f} {self.config.SYMBOL} | PnL: ${pnl_realized:.{self.bot_state.price_precision}f}" + Style.RESET_ALL)
                    subprocess.run(["termux-toast", f"Position Closed: {self.config.SYMBOL}. PnL: {pnl_realized:.{self.bot_state.price_precision}f}"])
                    
                    current_equity = self.get_account_balance_usdt() # Refresh equity for notification
                    if self.sms_notifier.is_enabled:
                        self.sms_notifier.send_pnl_update(float(pnl_realized), float(current_equity))
                    
                    # Clear internal position state
                    self.position_active = False
                    self.current_position_side = None
                    self.current_position_entry_price = Decimal('0')
                    self.current_position_size = Decimal('0')
                    self.current_positions.pop(self.config.SYMBOL, None) # Remove from dictionary
                    self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)

                    # Update BotState with realized PnL and clear open position data
                    with self.bot_state.lock:
                        self.bot_state.realized_pnl_total = self.cumulative_pnl
                        self.bot_state.open_position_qty = Decimal('0.0')
                        self.bot_state.open_position_side = "NONE"
                        self.bot_state.open_position_entry_price = Decimal('0.0')
                        self.bot_state.unrealized_pnl = Decimal('0.0')
                        self.bot_state.unrealized_pnl_pct = Decimal('0.0')
                    return True
                else:
                    status = order_details['list'][0].get('orderStatus', 'Unknown') if order_details and order_details.get('list') else 'Unknown'
                    self.logger.error(Fore.RED + f"Close order {order_id} placed but NOT FILLED. Status: {status}. Manual intervention may be required." + Style.RESET_ALL)
                    subprocess.run(["termux-toast", f"Close Order NOT FILLED: {self.config.SYMBOL} (ID: {order_id})"])
                    if self.sms_notifier.is_enabled:
                        self.sms_notifier.send_sms(f"CRITICAL: Close order {order_id} for {self.config.SYMBOL} NOT FILLED! Status: {status}.")
                    return False
            else:
                self.logger.error(Fore.RED + f"Close order failed to manifest: API call returned no order ID or data for {self.config.SYMBOL}." + Style.RESET_ALL)
                if self.sms_notifier.is_enabled:
                    self.sms_notifier.send_sms(f"Close order failed for {self.config.SYMBOL}: No order ID returned.")
                return False
        except Exception as e:
            self.logger.error(Fore.RED + f"An unforeseen exception occurred during position closure for {self.config.SYMBOL}: {e}" + Style.RESET_ALL)
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"Close order exception for {self.config.SYMBOL}: {e}")
            return False

    def _cumulative_loss_guard(self) -> bool:
        """
        # A protective ward that halts trading if the cumulative equity drawdown
        # exceeds the predefined maximum loss threshold from the initial equity.
        """
        current_equity = self.get_account_balance_usdt() # This also updates bot_state.current_equity
        
        if self.initial_equity <= Decimal('0') or current_equity <= Decimal('0'): # Ensure valid initial and current equity
            self.logger.warning(Fore.YELLOW + "Could not fetch valid initial or current equity for cumulative loss guard. Proceeding cautiously." + Style.RESET_ALL)
            # Fallback to cumulative PnL-based logic if initial equity wasn't captured or current is zero
            if self.cumulative_pnl < -Decimal(str(self.config.MAX_DAILY_LOSS_PCT)):
                self.logger.critical(Fore.RED + f"Cumulative PnL loss limit reached ({self.cumulative_pnl:.2f} USDT). Trading halted!" + Style.RESET_ALL)
                subprocess.run(["termux-toast", "Cumulative PnL Loss Limit Reached! Trading Halted."])
                if self.sms_notifier.is_enabled:
                    self.sms_notifier.send_sms(f"CRITICAL: Cumulative PnL loss limit reached for {self.config.SYMBOL} ({self.cumulative_pnl:.2f} USDT). Trading halted!")
                return False
            return True

        drop_amount = self.initial_equity - current_equity
        drop_pct = (drop_amount / self.initial_equity) * Decimal('100')

        if drop_pct >= Decimal(str(self.config.MAX_DAILY_LOSS_PCT)): # Compare percentage directly
            self.logger.critical(Fore.RED + Style.BRIGHT + f"Cumulative equity drawdown {drop_pct:.2f}% exceeded limit ({self.config.MAX_DAILY_LOSS_PCT:.2f}%). Trading halted!" + Style.RESET_ALL)
            subprocess.run(["termux-toast", f"Cumulative Loss Limit Reached! Drawdown: {drop_pct:.2f}%"])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"CRITICAL: Cumulative equity drawdown {drop_pct:.2f}% exceeded limit for {self.config.SYMBOL}. Trading halted!")
            
            # Optional: close open position if loss limit is hit
            if self.position_active: # Check bot's internal state
                self.logger.warning(Fore.YELLOW + "Closing open position due to cumulative loss limit enchantment." + Style.RESET_ALL)
                self.close_position() # This will also update cumulative_pnl and bot_state
            return False
        return True

    def _get_current_orderbook(self) -> Tuple[Decimal, Decimal]:
        """Fetches the top bid and ask prices from the ticker."""
        try:
            data = self.api_call(self.bybit_client.get_tickers, category=self.config.CATEGORY_ENUM.value, symbol=self.config.SYMBOL)
            if data and data.get('list'):
                ticker_info = data['list'][0]
                ask_price = Decimal(ticker(ticker_info.get('ask1Price', '0')))
                bid_price = Decimal(str(ticker_info.get('bid1Price', '0')))
                return bid_price, ask_price
        except Exception as e:
            self.logger.error(Fore.RED + f"Failed to get ticker for {self.config.SYMBOL}: {e}" + Style.RESET_ALL)
        return Decimal('0.0'), Decimal('0.0')

    def connect_websocket(self):
        """
        # Establishes and maintains a mystical WebSocket connection,
        # listening for the whispers of new market candles, until a stop signal is received.
        """
        while not self.stop_event.is_set():
            try:
                self.logger.info(Fore.CYAN + "Attempting to forge WebSocket connection..." + Style.RESET_ALL)
                self.ws = WebSocket(testnet=self.config.TESTNET, channel_type=self.config.CATEGORY_ENUM.value)
                self.ws.kline_stream(interval=self.config.TIMEFRAME, symbol=self.config.SYMBOL, callback=self.process_message)
                
                with self.bot_state.lock:
                    self.bot_state.bot_status = "Running" # Update UI status
                
                # Keep the connection alive, like a steady heartbeat, checking for stop signal
                while not self.stop_event.is_set():
                    time.sleep(1) # Short sleep to allow event check
                
            except Exception as e:
                if self.stop_event.is_set(): # If we're stopping, don't try to reconnect
                    break
                self.logger.error(Fore.RED + f"WebSocket error: {e}. Reconnecting in 5s..." + Style.RESET_ALL)
                time.sleep(5)  # Pause before attempting to reconnect
        self.logger.info(Fore.BLUE + "WebSocket loop gracefully exited." + Style.RESET_ALL)
    
    def process_message(self, msg):
        """
        # The core incantation, triggered by each new confirmed k-line,
        # where market data is transformed into signals and actions.
        """
        if self.stop_event.is_set(): # Check stop event early
            return

        # Harden WebSocket topic filter to use startswith
        if "topic" in msg and str(msg["topic"]).startswith(f"kline.{self.config.TIMEFRAME}.{self.config.SYMBOL}"):
            kline = msg['data'][0]
            if not kline['confirm']: return  # Only process confirmed (closed) candles, avoiding premature judgment
            ts, close_price = int(kline['start']), float(kline['close'])
            if ts <= self.last_kline_ts: return  # Skip duplicate candle data, maintaining temporal integrity
            self.last_kline_ts = ts
            
            # Fetch current bid/ask for UI (using HTTP API for more reliability)
            bid_price_dec, ask_price_dec = self._get_current_orderbook()
            current_price_dec = Decimal(str(close_price))

            self.logger.info(Fore.LIGHTMAGENTA_EX + f"--- New Candle [{datetime.fromtimestamp(ts/1000)}] | Price: ${current_price_dec:.{self.bot_state.price_precision}f} ---" + Style.RESET_ALL)
            df = self.get_market_data()
            if df.empty: # Check for empty DataFrame
                self.logger.warning(Fore.YELLOW + "Failed to retrieve market data for signal generation. Awaiting next candle." + Style.RESET_ALL)
                return
            
            df_with_indicators = self.calculate_indicators(df)
            if df_with_indicators.empty: # Check for empty DataFrame after indicator calculation
                self.logger.warning(Fore.YELLOW + "DataFrame empty after indicator calculation. Awaiting next candle." + Style.RESET_ALL)
                return

            self.market_data = df_with_indicators # Store latest df for ATR calculation and future indicator updates
            
            # --- Update BotState with latest market data and indicators ---
            with self.bot_state.lock:
                self.bot_state.last_updated_time = datetime.now()
                self.bot_state.current_price = current_price_dec
                self.bot_state.bid_price = bid_price_dec
                self.bot_state.ask_price = ask_price_dec
                
                latest_indicator_row = df_with_indicators.iloc[-1]

                # Ehlers SuperTrend
                if 'supertrend_line_value' in latest_indicator_row and not np.isnan(latest_indicator_row['supertrend_line_value']):
                    self.bot_state.ehlers_supertrend_value = Decimal(str(latest_indicator_row['supertrend_line_value']))
                else:
                    self.bot_state.ehlers_supertrend_value = Decimal('0.0')

                if 'supertrend_direction' in latest_indicator_row and not np.isnan(latest_indicator_row['supertrend_direction']):
                    if latest_indicator_row['supertrend_direction'] == 1:
                        self.bot_state.ehlers_supertrend_direction = "UP"
                    elif latest_indicator_row['supertrend_direction'] == -1:
                        self.bot_state.ehlers_supertrend_direction = "DOWN"
                    else:
                        self.bot_state.ehlers_supertrend_direction = "NONE"
                else:
                    self.bot_state.ehlers_supertrend_direction = "NONE"
                
                # Ehlers Filter
                if 'ehlers_filter' in latest_indicator_row and not np.isnan(latest_indicator_row['ehlers_filter']):
                    self.bot_state.ehlers_filter_value = Decimal(str(latest_indicator_row['ehlers_filter']))
                else:
                    self.bot_state.ehlers_filter_value = Decimal('0.0')

                # ADX
                if 'adx' in latest_indicator_row and not np.isnan(latest_indicator_row['adx']):
                    adx_val = Decimal(str(latest_indicator_row['adx']))
                    self.bot_state.adx_value = adx_val
                    if adx_val > Decimal('25'): self.bot_state.adx_trend_strength = "Strong"
                    elif adx_val > Decimal('20'): self.bot_state.adx_trend_strength = "Developing"
                    else: self.bot_state.adx_trend_strength = "Weak"
                else:
                    self.bot_state.adx_value = Decimal('0.0')
                    self.bot_state.adx_trend_strength = "N/A"
                
                # RSI
                if 'rsi' in latest_indicator_row and not np.isnan(latest_indicator_row['rsi']):
                    rsi_val = Decimal(str(latest_indicator_row['rsi']))
                    self.bot_state.rsi_value = rsi_val
                    if rsi_val > Decimal('70'): self.bot_state.rsi_state = "Overbought"
                    elif rsi_val < Decimal('30'): self.bot_state.rsi_state = "Oversold"
                    else: self.bot_state.rsi_state = "Neutral"
                else:
                    self.bot_state.rsi_value = Decimal('0.0')
                    self.bot_state.rsi_state = "N/A"

                # MACD
                if 'macd' in latest_indicator_row and not np.isnan(latest_indicator_row['macd']):
                    self.bot_state.macd_value = Decimal(str(latest_indicator_row['macd']))
                else:
                    self.bot_state.macd_value = Decimal('0.0')
                if 'macd_signal' in latest_indicator_row and not np.isnan(latest_indicator_row['macd_signal']):
                    self.bot_state.macd_signal_value = Decimal(str(latest_indicator_row['macd_signal']))
                else:
                    self.bot_state.macd_signal_value = Decimal('0.0')
                if 'macd_diff' in latest_indicator_row and not np.isnan(latest_indicator_row['macd_diff']):
                    self.bot_state.macd_diff_value = Decimal(str(latest_indicator_row['macd_diff']))
                else:
                    self.bot_state.macd_diff_value = Decimal('0.0')

            signal, reason = self.generate_signal(df_with_indicators)
            self.logger.info(Fore.WHITE + f"Signal: {signal or 'NONE'}" + Style.RESET_ALL)
            
            # Update position info & unrealized PnL in BotState
            # get_positions method already updates bot_state
            self.get_positions() 
            
            # --- Update unrealized PnL based on latest close price ---
            # This logic should be here, as `get_positions` might not give the *latest* mark price
            with self.bot_state.lock:
                if self.bot_state.open_position_qty > Decimal('0') and current_price_dec > Decimal('0'):
                    pos_size = self.bot_state.open_position_qty
                    entry_price = self.bot_state.open_position_entry_price
                    if pos_size > Decimal('0') and entry_price > Decimal('0'):
                        if self.bot_state.open_position_side == 'Buy':
                            self.bot_state.unrealized_pnl = (current_price_dec - entry_price) * pos_size
                        else: # Sell position
                            self.bot_state.unrealized_pnl = (entry_price - current_price_dec) * pos_size
                        if entry_price * pos_size > Decimal('0'):
                            self.bot_state.unrealized_pnl_pct = (self.bot_state.unrealized_pnl / (entry_price * pos_size)) * Decimal('100')
                        else:
                            self.bot_state.unrealized_pnl_pct = Decimal('0.0')
                    else:
                        self.bot_state.unrealized_pnl = Decimal('0.0')
                        self.bot_state.unrealized_pnl_pct = Decimal('0.0')
                else:
                    self.bot_state.unrealized_pnl = Decimal('0.0')
                    self.bot_state.unrealized_pnl_pct = Decimal('0.0')
            
            if signal and signal != self.last_signal:
                if self.bot_state.open_position_qty > Decimal('0'): # Check if an active position exists via bot_state
                    self.logger.warning(Fore.YELLOW + "An existing position is found. Closing it before opening a new one, to maintain balance." + Style.RESET_ALL)
                    self.close_position() # This will update cumulative_pnl and bot_state
                    time.sleep(3)  # A brief pause to allow the order to settle
                
                self.logger.info(Fore.GREEN + f"Executing new signal: {signal}. Reason: {reason}" + Style.RESET_ALL)
                self.execute_trade_based_on_signal(signal_type=signal, reason=reason)
                self.last_signal = signal
            elif self.bot_state.open_position_qty > Decimal('0'): # If holding position but no new signal
                self.logger.info(Fore.CYAN + f"Holding {self.bot_state.open_position_side} position. Size: {self.bot_state.open_position_qty:.{self.bot_state.qty_precision}f}. Entry: ${self.bot_state.open_position_entry_price:.{self.bot_state.price_precision}f}" + Style.RESET_ALL)
            else:
                self.logger.info(Fore.WHITE + "Awaiting a clear signal. No active position in the market's currents." + Style.RESET_ALL)
    
    def run(self):
        """
        # Initiates the bot's grand operation, starting the WebSocket vigil
        # and managing its continuous market engagement, with graceful shutdown.
        """
        self.logger.info(Fore.LIGHTYELLOW_EX + Style.BRIGHT + f"🚀 Launching Ehlers SuperTrend Bot for {self.config.SYMBOL}! May its journey be prosperous." + Style.RESET_ALL)
        subprocess.run(["termux-toast", f"Ehlers SuperTrend Bot for {self.config.SYMBOL} is commencing its arcane operations."])
        if self.sms_notifier.is_enabled:
            self.sms_notifier.send_sms(f"Ehlers SuperTrend Bot for {self.config.SYMBOL} is commencing its arcane operations.")

        self._install_signal_handlers() # Install signal handlers

        # Start BotUI thread
        ui_thread = BotUI(self.bot_state)
        ui_thread.start()

        # Start WebSocket connection in a separate thread
        ws_thread = threading.Thread(target=self.connect_websocket)
        ws_thread.daemon = True # Allows the main program to exit even if this thread is running
        ws_thread.start()
        
        # The main thread now simply waits for a stop event, keeping the bot running continuously
        self.logger.info(Fore.BLUE + "Bot now running continuously, awaiting stop signal (Ctrl+C)." + Style.RESET_ALL)
        self.stop_event.wait() # Block until stop_event is set (e.g., by signal handler)

        # Signal UI thread to stop gracefully and wait for it
        ui_thread.stop()
        ui_thread.join() 

        self.logger.info(Fore.BLUE + "Bot's main loop gracefully exited. Farewell, seeker." + Style.RESET_ALL)


if __name__ == "__main__":
    print(Fore.LIGHTYELLOW_EX + Style.BRIGHT + "\nPyrmethus, the Termux Coding Wizard, at your service! Let the arcane trading begin!" + Style.RESET_ALL)
    
    # --- DEMONSTRATION OF parse_to_utc ---
    print(Fore.CYAN + "\n# Demonstrating the temporal conversion incantation:" + Style.RESET_ALL)
    example_local_times = [
        "2025-08-24 10:00:00 AM EST",
        "2025-08-24 15:00:00 BST",
        "2025-08-24 14:00:00 GMT",
        "2025-08-24 18:00:00 CET",
        "2025-08-24 02:00:00 JST",
        "2025-08-24 01:00:00 AM PDT",
    ]
    
    for local_time_str in example_local_times:
        utc_time = parse_to_utc(local_time_str)
        if utc_time:
            print(Fore.WHITE + f"  Local: {local_time_str}" + Fore.GREEN + f" -> UTC: {utc_time}" + Style.RESET_ALL)
    print(Fore.CYAN + "# Temporal conversion demonstration complete." + Style.RESET_ALL)
    subprocess.run(["termux-toast", "Ehlers Bot: Temporal conversion demo complete."])
    # ------------------------------------

    # Initialize configuration
    config = Config()
    
    bot = EhlersSuperTrendBot(config)
    bot.run()
    
    print(Fore.MAGENTA + "\n# May your digital journey be ever enlightened." + Style.RESET_ALL)
