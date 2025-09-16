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
    TESTNET: bool = field(default=False)

    # Trading Configuration
    SYMBOLS: List[str] = field(default_factory=lambda: ["BTCUSDT"])
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


    def __post_init__(self):
        """Load configuration from environment variables and validate."""
        self.API_KEY = os.getenv("BYBIT_API_KEY", self.API_KEY)
        self.API_SECRET = os.getenv("BYBIT_API_SECRET", self.API_SECRET)
        self.TESTNET = os.getenv("BYBIT_TESTNET", str(self.TESTNET)).lower() in ['true', '1', 't']
        
        symbols_str = os.getenv("TRADING_SYMBOLS")
        if symbols_str:
            self.SYMBOLS = [s.strip().upper() for s in symbols_str.split(',')]
        else:
            # Fallback to single symbol env var for backward compatibility
            single_symbol = os.getenv("TRADING_SYMBOL", self.SYMBOLS[0])
            self.SYMBOLS = [single_symbol.strip().upper()]

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
                rounded_value = rounded_value.quantize(Decimal(f'1e{step.as_tuple().exponent}'), rounding=ROUND_DOWN)
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
        # Calculate risk amount in USDT
        risk_amount_usdt = account_balance_usdt * risk_percent

        # Calculate stop loss distance in percentage terms
        stop_distance_pct = stop_distance_price / entry_price

        # Calculate the required position value in USDT to risk 'risk_amount_usdt'
        # position_value_usd * stop_distance_pct = risk_amount_usdt
        # position_value_usd = risk_amount_usdt / stop_distance_pct
        if stop_distance_pct > Decimal('0'):
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

    def __init__(self, bybit_session: HTTP, precision_manager: PrecisionManager, logger: logging.Logger, api_call_wrapper: Any):
        self.session = bybit_session
        self.precision = precision_manager
        self.logger = logger
        self.api_call = api_call_wrapper # Reference to the bot's api_call method
        # Stores active trailing stop info: {symbol: {'side': 'Buy'/'Sell', 'trail_percent': Decimal}}
        self.active_trailing_stops: Dict[str, dict] = {}

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
        update_exchange: bool = True # Typically True to ensure it's set
    ) -> bool:
        """
        Re-confirms or re-sets the trailing stop on the exchange if `update_exchange` is True.
        For Bybit's native `callbackRate`, this usually means ensuring it's still active.
        """
        if symbol not in self.active_trailing_stops:
            return False # No active trailing stop to update

        if not update_exchange:
            self.logger.debug(f"Internal trailing stop check for {symbol}: current price {current_price}.")
            return False # No exchange update requested

        # Re-initialize the trailing stop to ensure it's active with the configured rate.
        # This will override any existing trailing stop settings for the symbol.
        ts_info = self.active_trailing_stops[symbol]
        return self.initialize_trailing_stop(
            symbol=symbol,
            position_side=ts_info['side'],
            entry_price=Decimal('0'), # Dummy value as not used by Bybit's callbackRate
            current_price=current_price,
            trail_percent=float(ts_info['trail_percent']),
            activation_percent=float(ts_info['trail_percent']) # Dummy value as not used by Bybit's callbackRate
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
    # A conduit to the Bybit ether, allowing direct communion with its V5 API endpoints.
    # This client wraps the pybit library, ensuring all calls are harmonized and returning
    # raw responses for the bot's api_call to interpret.
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
        # Summons the knowledge of the user's wallet balance from the Bybit V5 API.
        # This spell relies on the pybit library's own powerful incantation.
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
        """Manages protective wards (TP/SL/Trailing Stops)."""
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
        """Fetches the chronicles of past orders."""
        params = {'category': category or self._default_category, 'symbol': symbol, 'limit': limit}
        if orderId: params['orderId'] = orderId
        return self.session.get_order_history(**params)

    def get_open_orders(self, symbol: str, orderId: Optional[str] = None, limit: int = 50,
                        category: Optional[str] = None) -> Dict[str, Any]:
        """Reveals orders that currently lie in wait."""
        params = {'category': category or self._default_category, 'symbol': symbol, 'limit': limit}
        if orderId: params['orderId'] = orderId
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
    # A shared scroll containing the bot's current market perception and state,
    # ensuring that all modules, especially the UI, can read consistent data.
    """
    lock: threading.Lock = field(default_factory=threading.Lock) # Guards against simultaneous writes from different threads
    
    # General Bot Info
    initial_equity: Decimal = field(default=Decimal('0.0'))
    current_equity: Decimal = field(default=Decimal('0.0'))
    realized_pnl_total: Decimal = field(default=Decimal('0.0')) # Cumulative PnL from closed trades
    last_updated_time: datetime = field(default_factory=datetime.now)
    bot_status: str = field(default="Initializing")
    dry_run: bool = field(default=False)
    testnet: bool = field(default=True)

    # Per-Symbol Data - Dictionaries keyed by symbol
    market_data: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    position_data: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class SymbolState:
    """
    # A scroll to hold the unique state and memories for a single symbol,
    # allowing the bot to manage multiple market realms concurrently.
    """
    symbol: str
    market_data: pd.DataFrame = field(default_factory=pd.DataFrame)
    position_active: bool = False
    current_position_side: Optional[str] = None
    current_position_entry_price: Decimal = Decimal('0')
    current_position_size: Decimal = Decimal('0')
    last_signal: Optional[str] = None
    last_kline_ts: int = 0
    last_trade_time: float = 0.0


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
            
            # --- UI Layout ---
            # Main Header
            print(f"{Fore.CYAN}╔═══════════════════════════════════════════════════════════════════════════╗{Style.RESET_ALL}")
            dry_run_str = " [DRY RUN]" if state.dry_run else ""
            header_title = f"Multi-Symbol Ehlers SuperTrend Bot{dry_run_str}"
            print(f"{Fore.CYAN}║ {Fore.WHITE}{header_title:<73}{Fore.CYAN} ║{Style.RESET_ALL}")
            print(f"{Fore.CYAN}╠═══════════════════════════════════════════════════════════════════════════╣{Style.RESET_ALL}")
            status_text_display = f"Status: {Fore.GREEN}{state.bot_status} ({'TESTNET' if state.testnet else 'MAINNET'}){Fore.CYAN}"
            last_update_text = f"Last Updated: {state.last_updated_time.strftime('%H:%M:%S')}"
            status_len_no_color = len(state.bot_status) + len(f" ({'TESTNET' if state.testnet else 'MAINNET'})")
            padding_len = 73 - (len("Status: ") + status_len_no_color + len(last_update_text) + len("Last Updated: "))
            
            print(f"{Fore.CYAN}║ {status_text_display}{' ' * padding_len}{last_update_text} {Fore.CYAN}║{Style.RESET_ALL}")
            
            # Portfolio Summary
            pnl_color_realized = Fore.GREEN if state.realized_pnl_total >= Decimal('0') else Fore.RED
            initial_equity_str = f"${state.initial_equity:.2f}"
            current_equity_str = f"${state.current_equity:.2f}"
            equity_change_pct_val = Decimal('0.0')
            if state.initial_equity > Decimal('0') and state.current_equity > Decimal('0'):
                equity_change_pct_val = ((state.current_equity - state.initial_equity) / state.initial_equity) * Decimal('100')
            equity_color = Fore.GREEN if equity_change_pct_val >= Decimal('0') else Fore.RED
            equity_pct_str = f"{equity_change_pct_val:+.2f}%"
            current_equity_display_str = f"{current_equity_str} ({equity_pct_str})"
            realized_pnl_str = f"${state.realized_pnl_total:.2f}"

            print(f"{Fore.CYAN}╠═══════════════════════════════════════════════════════════════════════════╣{Style.RESET_ALL}")
            print(f"{Fore.CYAN}║ Initial Equity: {Fore.WHITE}{initial_equity_str:<20} {Fore.CYAN}Current Equity: {equity_color}{current_equity_display_str:<20}{Fore.CYAN} ║")
            print(f"{Fore.CYAN}║ Realized PNL (Total): {pnl_color_realized}{realized_pnl_str:<51}{Fore.CYAN} ║")
            print(f"{Fore.CYAN}╚═══════════════════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
")

            # Per-Symbol Display
            for symbol, market in state.market_data.items():
                pos = state.position_data.get(symbol, {})
                
                # Formatting and Coloring Logic
                pnl_color_unrealized = Fore.GREEN if pos.get('unrealized_pnl', Decimal('0')) >= Decimal('0') else Fore.RED
                adx_color = Fore.WHITE
                if market.get('adx_trend_strength') == "Strong": adx_color = Fore.LIGHTGREEN_EX
                elif market.get('adx_trend_strength') == "Developing": adx_color = Fore.LIGHTYELLOW_EX
                elif market.get('adx_trend_strength') == "Weak": adx_color = Fore.LIGHTBLACK_EX

                rsi_color = Fore.WHITE
                if market.get('rsi_state') == "Overbought": rsi_color = Fore.RED
                elif market.get('rsi_state') == "Oversold": rsi_color = Fore.GREEN
                
                ehlers_color = Fore.WHITE
                if market.get('ehlers_supertrend_direction') == "UP": ehlers_color = Fore.LIGHTGREEN_EX
                elif market.get('ehlers_supertrend_direction') == "DOWN": ehlers_color = Fore.LIGHTRED_EX

                # --- Symbol Header ---
                print(f"{Fore.BLUE}╔══ {Fore.WHITE}{symbol:<15} ═══════════════════════════════════════════════════════╗{Style.RESET_ALL}")
                
                # --- Market & Indicators ---
                price_str = f"${market.get('current_price', Decimal('0')):.{market.get('price_precision', 2)}f}"
                ehlers_st_val_str = f"${market.get('ehlers_supertrend_value', Decimal('0')):.{market.get('price_precision', 2)}f}"
                ehlers_st_display_str = f"{ehlers_st_val_str} ({market.get('ehlers_supertrend_direction', 'N/A')})"
                adx_str = f"{market.get('adx_value', Decimal('0')):.1f} ({market.get('adx_trend_strength', 'N/A')})"
                rsi_str = f"{market.get('rsi_value', Decimal('0')):.1f} ({market.get('rsi_state', 'N/A')})"

                print(f"{Fore.BLUE}║ Price: {Fore.YELLOW}{price_str:<18} {Fore.BLUE}ADX: {adx_color}{adx_str:<20} {Fore.BLUE}║")
                print(f"{Fore.BLUE}║ Ehlers ST: {ehlers_color}{ehlers_st_display_str:<14} {Fore.BLUE}RSI: {rsi_color}{rsi_str:<20} {Fore.BLUE}║")
                
                # --- Position Info ---
                print(f"{Fore.BLUE}╠═══════════════════════════════════════════════════════════════════════════╣{Style.RESET_ALL}")
                if pos.get('qty', Decimal('0')) > Decimal('0'):
                    pos_info = f"{pos.get('qty'):.{pos.get('qty_precision', 1)}f} {symbol} ({pos.get('side', 'N/A')})"
                    entry_price_str = f"${pos.get('entry_price'):.{market.get('price_precision', 2)}f}"
                    unrealized_pnl_str = f"${pos.get('unrealized_pnl'):.2f} ({pos.get('unrealized_pnl_pct'):+.2f}%)"
                    
                    print(f"{Fore.BLUE}║ Position: {Fore.WHITE}{pos_info:<15} {Fore.BLUE}Entry: {Fore.WHITE}{entry_price_str:<15} {Fore.BLUE}║")
                    print(f"{Fore.BLUE}║ PnL: {pnl_color_unrealized}{unrealized_pnl_str:<60}{Fore.BLUE} ║")
                else:
                    print(f"{Fore.BLUE}║ Position: {Fore.WHITE}None{Fore.BLUE:<65}║")

                print(f"{Fore.BLUE}╚═══════════════════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
")
            
            print(Style.RESET_ALL) # Ensure all colors are reset at the end



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
        self.order_sizer = OrderSizingCalculator(self.precision_manager, self.logger)
        # TrailingStopManager needs the bot's api_call wrapper
        self.trailing_stop_manager = TrailingStopManager(self.bybit_client.session, self.precision_manager, self.logger, self.api_call)
        
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
        self.current_positions: Dict[str, dict] = {} # {symbol: position_data}
        self.open_orders: Dict[str, dict] = {} # {order_id: order_data}
        self.account_balance_usdt: Decimal = Decimal('0.0')
        self.initial_equity: Decimal = Decimal('0.0') 
        
        # --- Strategy State ---
        self.position_active: bool = False
        self.current_position_side: Optional[str] = None # 'Buy' or 'Sell'
        self.current_position_entry_price: Decimal = Decimal('0')
        self.current_position_size: Decimal = Decimal('0')
        self.last_signal: Optional[str] = None # Stores the last signal acted upon
        self.last_kline_ts: int = 0 # Unix timestamp of the last processed confirmed candle
        self.last_trade_time: float = 0.0 # For trade cooldown
        self.cumulative_pnl: Decimal = Decimal('0.0') # Total realized PnL for cumulative loss guard

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
        self.logger.info(f"  Symbol: {self.config.SYMBOL}, Category: {config.CATEGORY_ENUM.value}")
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