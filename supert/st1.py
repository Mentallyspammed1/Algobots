"""
Standalone Ehlers Supertrend Trading Bot for Bybit V5 API.

This script implements a trading bot that uses the Supertrend indicator
(based on Ehlers' methodology, commonly implemented with ATR) to generate
trading signals and execute trades on Bybit via the pybit library.

Features:
- Configuration management via Config dataclass and environment variables.
- Robust precision handling for Bybit instrument specifications.
- Risk-based position sizing.
- Stop-loss and take-profit order placement.
- Basic trailing stop loss mechanism.
- Logging for bot operations and errors.
- Main trading loop with signal generation and order execution.
- Displays current price and indicator values in the log.
- Improved error handling for API initialization and rate limits.
- Corrected leverage setting logic to use configured category directly.
- Addressed potential `AttributeError` by ensuring manager initialization and handling API failures gracefully.
- Enhanced handling for Bybit API errors related to leverage setting for specific symbols/categories.
- Added type hints and Python 3.10+ union syntax for clarity.
- Improved docstrings and comments for maintainability.
- Added retry logic for critical API calls to improve robustness.
- Added graceful shutdown handling with signal module.
- Added option to configure hedge mode and positionIdx.
- Added more detailed logging for order lifecycle.
- Added environment variable support for hedge mode and positionIdx.
- Added more robust rounding logic with quantize fallback.
- Added more detailed exception handling for API calls.
- Added option to disable trailing stop updates on exchange for testing.
- Added more detailed status logging including open orders count.
- Added option to log to stdout only or file + stdout.
- Added more consistent use of Decimal for financial calculations.
- Added helper method to fetch open orders from exchange to sync local state.
- Added option to configure max retries and retry delay for API calls.
"""

import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from enum import Enum
from typing import Any

import pandas as pd
import pandas_ta as ta
from dotenv import load_dotenv
from pybit.exceptions import FailedRequestError, InvalidRequestError
from pybit.unified_trading import HTTP

# Load environment variables from .env file
load_dotenv()


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
    """Bot configuration"""
    # API Configuration
    API_KEY: str = field(default="YOUR_BYBIT_API_KEY")
    API_SECRET: str = field(default="YOUR_BYBIT_API_SECRET")
    TESTNET: bool = field(default=True)

    # Trading Configuration
    SYMBOL: str = field(default="BTCUSDT")
    CATEGORY: str = field(default="linear")  # Store as string initially, convert to Enum later
    LEVERAGE: int = field(default=5)
    HEDGE_MODE: bool = field(default=False)
    POSITION_IDX: int = field(default=0)  # 0=One-way mode, 1=Long, 2=Short in hedge mode

    # Position Sizing
    RISK_PER_TRADE_PCT: float = field(default=1.0)  # Risk % of account balance per trade
    MAX_POSITION_SIZE_USD: float = field(default=10000.0)  # Max position value in USD
    MIN_POSITION_SIZE_USD: float = field(default=10.0)  # Min position value in USD

    # Strategy Parameters
    TIMEFRAME: str = field(default="15")  # Kline interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)
    LOOKBACK_PERIODS: int = field(default=100)  # Historical data to fetch for indicators

    # Supertrend Indicator Parameters
    ST_PERIOD: int = field(default=10)  # ATR period for Supertrend
    ST_MULTIPLIER: float = field(default=3.0)  # Multiplier for ATR

    # Risk Management
    STOP_LOSS_PCT: float = field(default=0.015)  # 1.5% stop loss from entry
    TAKE_PROFIT_PCT: float = field(default=0.03)  # 3% take profit from entry
    TRAILING_STOP_PCT: float = field(default=0.005)  # 0.5% trailing stop from highest profit
    MAX_DAILY_LOSS_PCT: float = field(default=0.05)  # 5% max daily loss from start balance
    MAX_OPEN_POSITIONS: int = field(default=1)  # Not actively used in current logic, but good for future

    # Execution Settings
    ORDER_TYPE: str = field(default="Market")  # Store as string initially, convert to Enum later
    TIME_IN_FORCE: str = field(default="GTC")  # 'GTC', 'IOC', 'FOK', 'PostOnly'
    REDUCE_ONLY: bool = field(default=False)

    # Bot Settings
    LOOP_INTERVAL_SEC: int = field(default=60)  # Check interval in seconds
    LOG_LEVEL: str = field(default="INFO")
    LOG_FILE: str = field(default="supertrend_bot.log")
    LOG_TO_STDOUT_ONLY: bool = field(default=False)

    # API Retry Settings
    MAX_API_RETRIES: int = field(default=3)
    API_RETRY_DELAY_SEC: int = field(default=5)

    def __post_init__(self):
        """Load configuration from environment variables and validate."""
        self.API_KEY = os.getenv("BYBIT_API_KEY", self.API_KEY)
        self.API_SECRET = os.getenv("BYBIT_API_SECRET", self.API_SECRET)
        self.TESTNET = os.getenv("BYBIT_TESTNET", str(self.TESTNET)).lower() in ['true', '1', 't']
        self.SYMBOL = os.getenv("BYBIT_SYMBOL", self.SYMBOL)
        self.CATEGORY = os.getenv("BYBIT_CATEGORY", self.CATEGORY)
        self.LEVERAGE = int(os.getenv("BYBIT_LEVERAGE", self.LEVERAGE))
        self.HEDGE_MODE = os.getenv("BYBIT_HEDGE_MODE", str(self.HEDGE_MODE)).lower() in ['true', '1', 't']
        self.POSITION_IDX = int(os.getenv("BYBIT_POSITION_IDX", self.POSITION_IDX))

        self.RISK_PER_TRADE_PCT = float(os.getenv("BYBIT_RISK_PER_TRADE_PCT", self.RISK_PER_TRADE_PCT))
        self.MAX_POSITION_SIZE_USD = float(os.getenv("BYBIT_MAX_POSITION_SIZE_USD", self.MAX_POSITION_SIZE_USD))
        self.MIN_POSITION_SIZE_USD = float(os.getenv("BYBIT_MIN_POSITION_SIZE_USD", self.MIN_POSITION_SIZE_USD))

        self.TIMEFRAME = os.getenv("BYBIT_TIMEFRAME", self.TIMEFRAME)
        self.LOOKBACK_PERIODS = int(os.getenv("BYBIT_LOOKBACK_PERIODS", self.LOOKBACK_PERIODS))

        self.ST_PERIOD = int(os.getenv("BYBIT_ST_PERIOD", self.ST_PERIOD))
        self.ST_MULTIPLIER = float(os.getenv("BYBIT_ST_MULTIPLIER", self.ST_MULTIPLIER))

        self.STOP_LOSS_PCT = float(os.getenv("BYBIT_STOP_LOSS_PCT", self.STOP_LOSS_PCT))
        self.TAKE_PROFIT_PCT = float(os.getenv("BYBIT_TAKE_PROFIT_PCT", self.TAKE_PROFIT_PCT))
        self.TRAILING_STOP_PCT = float(os.getenv("BYBIT_TRAILING_STOP_PCT", self.TRAILING_STOP_PCT))
        self.MAX_DAILY_LOSS_PCT = float(os.getenv("BYBIT_MAX_DAILY_LOSS_PCT", self.MAX_DAILY_LOSS_PCT))

        self.ORDER_TYPE = os.getenv("BYBIT_ORDER_TYPE", self.ORDER_TYPE)
        self.TIME_IN_FORCE = os.getenv("BYBIT_TIME_IN_FORCE", self.TIME_IN_FORCE)
        self.REDUCE_ONLY = os.getenv("BYBIT_REDUCE_ONLY", str(self.REDUCE_ONLY)).lower() in ['true', '1', 't']

        self.LOOP_INTERVAL_SEC = int(os.getenv("BYBIT_LOOP_INTERVAL_SEC", self.LOOP_INTERVAL_SEC))
        self.LOG_LEVEL = os.getenv("BYBIT_LOG_LEVEL", self.LOG_LEVEL)
        self.LOG_FILE = os.getenv("BYBIT_LOG_FILE", self.LOG_FILE)
        self.LOG_TO_STDOUT_ONLY = os.getenv("BYBIT_LOG_TO_STDOUT_ONLY", str(self.LOG_TO_STDOUT_ONLY)).lower() in ['true', '1', 't']

        self.MAX_API_RETRIES = int(os.getenv("BYBIT_MAX_API_RETRIES", self.MAX_API_RETRIES))
        self.API_RETRY_DELAY_SEC = int(os.getenv("BYBIT_API_RETRY_DELAY_SEC", self.API_RETRY_DELAY_SEC))

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
            self.logger.info("Leverage set to 1 for SPOT category as it's not applicable.")


# =====================================================================
# LOGGING SETUP
# =====================================================================

def setup_logger(config: Config) -> logging.Logger:
    """Setup logging configuration"""
    logger = logging.getLogger('SupertrendBot')
    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Clear existing handlers to prevent duplicate logs if this function is called multiple times
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if config.LOG_TO_STDOUT_ONLY:
        ch = logging.StreamHandler()
        ch.setLevel(log_level)
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    else:
        # File handler for all logs (DEBUG level)
        fh = logging.FileHandler(config.LOG_FILE)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        # Console handler for specified log level
        ch = logging.StreamHandler()
        ch.setLevel(log_level)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

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

    def __init__(self, session: HTTP, logger: logging.Logger):
        self.session = session
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
        lot_size_alt = inst.get('unifiedLotSizeFilter', {}) # For potential unified account specifics

        def safe_decimal(value: Any, default: str = '0') -> Decimal:
            """Safely convert value to Decimal, returning default on error."""
            try:
                return Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                return Decimal(default)

        tick_size = safe_decimal(price_filter.get('tickSize', '0.00000001')) # Default to high precision if missing
        min_price = safe_decimal(price_filter.get('minPrice', '0'))
        max_price = safe_decimal(price_filter.get('maxPrice', '1e9')) # Default to a large number

        qty_step = safe_decimal(lot_size_filter.get('qtyStep', lot_size_alt.get('qtyStep', '0.00000001'))) # Default to high precision
        min_order_qty = safe_decimal(lot_size_filter.get('minOrderQty', lot_size_alt.get('minOrderQty', '0')))
        max_order_qty = safe_decimal(lot_size_filter.get('maxOrderQty', lot_size_alt.get('maxOrderQty', '1e9')))

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
            base_currency=inst.get('baseCoin', ''), # May be absent for spot sometimes
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

    def get_specs(self, symbol: str) -> InstrumentSpecs | None:
        """Get instrument specs for a symbol"""
        return self.instruments.get(symbol.upper())

    def _round_decimal(self, value: Decimal, step: Decimal) -> Decimal:
        """Helper to round a Decimal to the nearest step, rounding down."""
        if step == 0:
            return value
        try:
            # Use normalize() to get the decimal representation of the step (e.g., 0.01)
            quantize_exp = step.normalize()

            # Ensure value and step are positive for calculation, handle sign later if needed
            sign = value.sign
            value_abs = abs(value)
            step_abs = abs(step)

            # Calculate the number of steps
            # Use floor division to round down
            num_steps = (value_abs // step_abs)

            # Reapply sign and step
            rounded_value = sign * num_steps * step_abs

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
    ) -> Decimal | None:
        """
        Calculate position size in base currency units based on fixed risk percentage, leverage,
        entry price, and stop loss price. Returns None if calculation is not possible.
        Enhanced for category-specific handling.
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

    def __init__(self, session: HTTP, precision_manager: PrecisionManager, logger: logging.Logger):
        self.session = session
        self.precision = precision_manager
        self.logger = logger
        # Stores active trailing stop info: {symbol: {'side': 'Buy'/'Sell',
        # 'activation_price': Decimal, 'trail_percent': Decimal,
        # 'current_stop': Decimal, 'highest_price': Decimal/None,
        # 'lowest_price': Decimal/None, 'is_activated': bool}}
        self.active_trailing_stops: dict[str, dict] = {}

    def initialize_trailing_stop(
        self,
        symbol: str,
        position_side: str,
        entry_price: Decimal,
        current_price: Decimal,
        trail_percent: float, # Pass as percentage
        activation_percent: float # Pass as percentage
    ) -> dict | None:
        """
        Initialize trailing stop for a position.
        Returns the initial trailing stop configuration if successful.
        """
        specs = self.precision.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot initialize trailing stop for {symbol}: Specs not found.")
            return None

        # Trailing stops are typically not applicable or handled differently for spot.
        # However, the general logic might still apply for some platforms.
        # For Bybit, it's mainly for derivatives.
        if specs.category == 'spot':
            self.logger.debug(f"Trailing stops may not be fully supported or applicable for spot category {symbol}. Skipping initialization logic.")
            # Return None or a placeholder if spot does not support it.
            return None

        trail_pct = Decimal(str(trail_percent / 100))
        activation_pct = Decimal(str(activation_percent / 100))

        activation_price = Decimal('0')
        current_stop = Decimal('0')
        highest_price = None # Track highest price reached for Buy orders
        lowest_price = None  # Track lowest price reached for Sell orders
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

        # Spot category does not support direct stop loss setting via set_trading_stop.
        # This should ideally be checked before calling.
        if specs.category == 'spot':
            self.logger.warning(f"Cannot update stop loss for spot symbol {symbol}.")
            return False

        try:
            response = self.session.set_trading_stop(
                category=specs.category,
                symbol=symbol,
                stopLoss=str(stop_price),
                slOrderType='Market' # Typically Market order for stop loss
            )

            if response and response['retCode'] == 0:
                self.logger.info(f"Successfully updated stop loss on exchange for {symbol} to {stop_price}")
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.logger.error(f"Failed to update stop loss on exchange for {symbol}: {error_msg}")
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
# MAIN TRADING BOT CLASS
# =====================================================================

class SupertrendBot:
    def __init__(self, config: Config):
        self.config = config
        self.logger = setup_logger(config)

        self.logger.info("Initializing Supertrend Trading Bot...")

        # --- API Session Initialization ---
        self.session = None
        self._init_api_session() # Initialize and test API connection with retries

        # --- Managers Initialization ---
        self.precision_manager = PrecisionManager(self.session, self.logger)
        self.order_sizer = OrderSizingCalculator(self.precision_manager, self.logger)
        self.trailing_stop_manager = TrailingStopManager(self.session, self.precision_manager, self.logger)

        # --- Data Storage ---
        self.market_data = pd.DataFrame()
        # Stores active positions: {symbol: position_data} - might only track one symbol for this bot
        self.current_positions: dict[str, dict] = {}
        # Stores open orders: {order_id: order_data}
        self.open_orders: dict[str, dict] = {}
        self.account_balance_usdt: Decimal = Decimal('0.0')
        self.start_balance_usdt: Decimal = Decimal('0.0')
        self.daily_loss_amount: Decimal = Decimal('0.0')

        # --- Strategy State ---
        # Current active position details for the configured symbol
        self.position_active: bool = False
        self.current_position_side: str | None = None # 'Buy' or 'Sell'
        self.current_position_entry_price: Decimal = Decimal('0')
        self.current_position_size: Decimal = Decimal('0')
        self.last_signal: Signal = Signal.NEUTRAL

        self.logger.info("Bot Configuration Loaded:")
        self.logger.info(f"  Mode: {'Testnet' if config.TESTNET else 'Mainnet'}")
        self.logger.info(f"  Symbol: {config.SYMBOL}, Category: {config.CATEGORY_ENUM.value}")
        self.logger.info(f"  Leverage: {config.LEVERAGE}x")
        self.logger.info(f"  Hedge Mode: {config.HEDGE_MODE}, PositionIdx: {config.POSITION_IDX}")
        self.logger.info(f"  Timeframe: {config.TIMEFRAME}")
        self.logger.info(f"  Supertrend Params: Period={config.ST_PERIOD}, Multiplier={config.ST_MULTIPLIER}")
        self.logger.info(f"  Risk Params: Risk/Trade={config.RISK_PER_TRADE_PCT}%, SL={config.STOP_LOSS_PCT*100:.2f}%, TP={config.TAKE_PROFIT_PCT*100:.2f}%, Trail={config.TRAILING_STOP_PCT*100:.2f}%, Max Daily Loss={config.MAX_DAILY_LOSS_PCT*100:.2f}%")
        self.logger.info(f"  Execution: OrderType={config.ORDER_TYPE_ENUM.value}, TimeInForce={config.TIME_IN_FORCE}, ReduceOnly={config.REDUCE_ONLY}")
        self.logger.info(f"  Loop Interval: {config.LOOP_INTERVAL_SEC} seconds")
        self.logger.info(f"  API Retry: MaxRetries={config.MAX_API_RETRIES}, RetryDelay={config.API_RETRY_DELAY_SEC}s")

        # Graceful shutdown handling
        self._stop_requested = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Any):
        """Handler for termination signals to stop the bot gracefully."""
        self.logger.info(f"Signal {signum} received, stopping bot gracefully...")
        self._stop_requested = True

    def _init_api_session(self):
        """Initialize Bybit API session with retry logic."""
        for attempt in range(1, self.config.MAX_API_RETRIES + 1):
            try:
                self.session = HTTP(
                    testnet=self.config.TESTNET,
                    api_key=self.config.API_KEY,
                    api_secret=self.config.API_SECRET
                )
                # Test connection by fetching instruments info. This also validates API keys early on.
                self.session.get_instruments_info(category=self.config.CATEGORY_ENUM.value)
                self.logger.info(f"Successfully connected to Bybit API ({'Testnet' if self.config.TESTNET else 'Mainnet'}).")
                return # Exit loop on success
            except FailedRequestError as e:
                self.logger.critical(f"Failed to initialize Bybit API session or validate keys (Attempt {attempt}/{self.config.MAX_API_RETRIES}): {e}", exc_info=True)
                if attempt < self.config.MAX_API_RETRIES:
                    self.logger.info(f"Retrying in {self.config.API_RETRY_DELAY_SEC} seconds...")
                    time.sleep(self.config.API_RETRY_DELAY_SEC)
                else:
                    self.logger.critical("Max retries reached. Exiting.")
                    sys.exit(1)
            except Exception as e:
                self.logger.critical(f"Unexpected error during API session initialization (Attempt {attempt}/{self.config.MAX_API_RETRIES}): {e}", exc_info=True)
                if attempt < self.config.MAX_API_RETRIES:
                    self.logger.info(f"Retrying in {self.config.API_RETRY_DELAY_SEC} seconds...")
                    time.sleep(self.config.API_RETRY_DELAY_SEC)
                else:
                    self.logger.critical("Max retries reached. Exiting.")
                    sys.exit(1)

    # =====================================================================
    # DATA FETCHING METHODS
    # =====================================================================

    def fetch_klines(self, limit: int | None = None) -> pd.DataFrame:
        """Fetch historical kline data from Bybit."""
        try:
            fetch_limit = limit if limit else self.config.LOOKBACK_PERIODS
            if fetch_limit < 2: # Need at least 2 candles for signal generation
                fetch_limit = 2

            self.logger.debug(f"Fetching {fetch_limit} klines for {self.config.SYMBOL} ({self.config.TIMEFRAME})...")
            response = self.session.get_kline(
                category=self.config.CATEGORY_ENUM.value,
                symbol=self.config.SYMBOL,
                interval=self.config.TIMEFRAME,
                limit=fetch_limit
            )

            if response and response['retCode'] == 0:
                klines = response['result'].get('list', [])
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
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.logger.error(f"Failed to fetch klines for {self.config.SYMBOL}: {error_msg}")
                return pd.DataFrame()

        except Exception as e:
            self.logger.error(f"Exception fetching klines for {self.config.SYMBOL}: {e}", exc_info=True)
            return pd.DataFrame()

    def get_ticker(self) -> dict | None:
        """Get current ticker data for the symbol."""
        try:
            response = self.session.get_tickers(
                category=self.config.CATEGORY_ENUM.value,
                symbol=self.config.SYMBOL
            )

            if response and response['retCode'] == 0:
                tickers = response['result'].get('list', [])
                if tickers:
                    return tickers[0] # Expecting a single ticker for the specified symbol
                else:
                    self.logger.warning(f"Ticker data list is empty for {self.config.SYMBOL}.")
                    return None
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.logger.error(f"Failed to fetch ticker for {self.config.SYMBOL}: {error_msg}")
                return None

        except Exception as e:
            self.logger.error(f"Exception fetching ticker for {self.config.SYMBOL}: {e}", exc_info=True)
            return None

    # =====================================================================
    # TECHNICAL INDICATORS
    # =====================================================================

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Supertrend and ATR using pandas_ta. Enhanced with robust column handling and NaN removal."""
        if df.empty:
            self.logger.warning("DataFrame is empty, cannot calculate indicators.")
            return df

        try:
            # Ensure required columns exist and are numeric
            required_cols = ['high', 'low', 'close']
            for col in required_cols:
                if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
                    self.logger.error(f"Required column '{col}' is missing or not numeric in DataFrame. Cannot calculate indicators.")
                    return df # Return original df if essential columns are missing

            # Calculate ATR
            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=self.config.ST_PERIOD)

            # Calculate Supertrend
            # pandas_ta's supertrend returns multiple columns: Supertrend value, direction, lower band, upper band
            # The column names are generated based on parameters. We'll infer them.
            st_col_prefix = f'SUPERT_{self.config.ST_PERIOD}_{self.config.ST_MULTIPLIER}'
            st_direction_col = f'{st_col_prefix}d' # Direction column suffix

            # Calculate Supertrend. `append=True` is deprecated. We manually add columns.
            # It's safer to get the DataFrame from `ta.supertrend` and then merge/assign.
            st_results = ta.supertrend(
                high=df['high'],
                low=df['low'],
                close=df['close'],
                length=self.config.ST_PERIOD,
                multiplier=self.config.ST_MULTIPLIER,
                fillna=0 # Fill NaN with 0 during calculation if needed, but we'll drop later.
            )

            if st_results is not None and not st_results.empty:
                # Check for expected column names based on pandas_ta version and input parameters
                expected_st_col = None
                expected_dir_col = None
                for col in st_results.columns:
                    if col.startswith(st_col_prefix) and 'd' not in col:
                        expected_st_col = col
                    elif col.startswith(st_col_prefix) and 'd' in col:
                        expected_dir_col = col

                if expected_st_col and expected_dir_col:
                    df['supertrend'] = st_results[expected_st_col]
                    df['supertrend_direction'] = st_results[expected_dir_col]
                    self.logger.debug(f"Supertrend columns joined: '{expected_st_col}' -> 'supertrend', '{expected_dir_col}' -> 'supertrend_direction'")
                else:
                    self.logger.warning("Could not find expected Supertrend columns. Setting neutral indicators.")
                    df['supertrend'] = df['close']  # Fallback to close price
                    df['supertrend_direction'] = 0
            else:
                self.logger.warning("Supertrend calculation returned empty DataFrame. Setting neutral indicators.")
                df['supertrend'] = df['close']  # Fallback to close price
                df['supertrend_direction'] = 0

            # Drop rows where indicators are NaN (improved: remove initial NaN rows instead of filling with 0)
            # Ensure all necessary columns exist before dropna
            required_indicator_cols = ['supertrend', 'supertrend_direction', 'atr']
            for col in required_indicator_cols:
                if col not in df.columns:
                    df[col] = 0 # Add missing columns with default if they didn't get created

            df.dropna(subset=required_indicator_cols, inplace=True)

            if df.empty:
                self.logger.warning("All rows dropped due to NaN indicators. Cannot proceed.")
                return pd.DataFrame()

            # Ensure direction is integer
            df['supertrend_direction'] = df['supertrend_direction'].astype(int)

            self.logger.debug(f"Supertrend and ATR indicators calculated. DataFrame shape: {df.shape}")
            return df

        except Exception as e:
            self.logger.error(f"Error calculating indicators: {e}", exc_info=True)
            return df # Return DataFrame as-is if calculation fails

    # =====================================================================
    # STRATEGY LOGIC
    # =====================================================================

    def generate_signal(self, df: pd.DataFrame) -> Signal:
        """
        Generate trading signal based on Supertrend direction changes.
        Uses the last two data points to detect trend flips.
        """
        if df.empty or len(df) < 2:
            self.logger.warning("Not enough data points to generate signal (need at least 2).")
            return Signal.NEUTRAL

        try:
            # Get the last two rows
            latest = df.iloc[-1]
            previous = df.iloc[-2]

            # Supertrend direction: 1 for uptrend, -1 for downtrend
            # Supertrend line: the price value of the Supertrend indicator
            current_st_dir = int(latest.get('supertrend_direction', 0)) # Ensure int
            prev_st_dir = int(previous.get('supertrend_direction', 0)) # Ensure int

            current_close = latest.get('close', Decimal('0.0'))
            current_st_price = latest.get('supertrend', Decimal('0.0'))

            # --- Signal Logic ---
            # BUY Signals:
            # 1. Strong Buy: Trend flipped from DOWN (-1) to UP (1)
            # 2. Buy: Trend is UP (1) and price is above Supertrend line
            if current_st_dir == 1:
                if prev_st_dir == -1: # Trend flip from down to up
                    self.last_signal = Signal.STRONG_BUY
                elif current_close > current_st_price: # Trend is up and price is above ST line
                    self.last_signal = Signal.BUY
                else: # Trend is up, but price is below ST line (possible weak signal or reversal)
                    self.last_signal = Signal.NEUTRAL
            # SELL Signals:
            # 1. Strong Sell: Trend flipped from UP (1) to DOWN (-1)
            # 2. Sell: Trend is DOWN (-1) and price is below Supertrend line
            elif current_st_dir == -1:
                if prev_st_dir == 1: # Trend flip from up to down
                    self.last_signal = Signal.STRONG_SELL
                elif current_close < current_st_price: # Trend is down and price is below ST line
                    self.last_signal = Signal.SELL
                else: # Trend is down, but price is above ST line
                    self.last_signal = Signal.NEUTRAL
            else: # Neutral direction or indicator not calculated properly
                self.last_signal = Signal.NEUTRAL

            self.logger.debug(f"Signal generated: {self.last_signal.name} (Close={current_close:.2f}, ST={current_st_price:.2f}, ST_Dir={current_st_dir})")
            return self.last_signal

        except Exception as e:
            self.logger.error(f"Error generating signal: {e}", exc_info=True)
            return Signal.NEUTRAL

    # =====================================================================
    # RISK MANAGEMENT
    # =====================================================================

    def calculate_position_size_usd(self, entry_price: float, stop_loss_price: float) -> Decimal | None:
        """Calculate position size in USDT based on risk parameters."""
        try:
            # Convert inputs to Decimal for precision
            current_balance = self.account_balance_usdt
            risk_pct = Decimal(str(self.config.RISK_PER_TRADE_PCT / 100))
            entry_price_dec = Decimal(str(entry_price))
            stop_loss_price_dec = Decimal(str(stop_loss_price))
            leverage_dec = Decimal(str(self.config.LEVERAGE))

            # Use the consolidated calculator
            quantity = self.order_sizer.calculate_position_size_usd(
                symbol=self.config.SYMBOL,
                account_balance_usdt=current_balance,
                risk_percent=risk_pct,
                entry_price=entry_price_dec,
                stop_loss_price=stop_loss_price_dec,
                leverage=leverage_dec
            )

            # The calculator already performs validation and returns None if size is invalid
            if quantity is not None and quantity <= 0:
                 self.logger.warning(f"Calculated position size for {self.config.SYMBOL} is zero or negative ({quantity}).")
                 return None

            return quantity

        except Exception as e:
            self.logger.error(f"Error calculating position size for {self.config.SYMBOL}: {e}", exc_info=True)
            return None

    def check_daily_loss_limit(self) -> bool:
        """Check if the daily loss limit has been reached."""
        if self.start_balance_usdt <= 0: # If start balance is not set or invalid, cannot check limit
            self.logger.warning("Start balance not initialized or zero. Daily loss limit check bypassed.")
            return True

        try:
            current_balance = self.get_account_balance_usdt() # Fetch latest balance
            if current_balance <= 0: # If current balance is zero, we've lost everything
                self.logger.warning("Current account balance is zero or negative. Assuming loss limit hit.")
                return False

            loss_amount = self.start_balance_usdt - current_balance
            max_allowed_loss = self.daily_loss_amount

            if loss_amount >= max_allowed_loss:
                self.logger.warning(f"Daily loss limit reached. Current loss: {loss_amount:.2f} USDT (Limit: {max_allowed_loss:.2f} USDT). Halting trading operations.")
                return False
            else:
                self.logger.debug(f"Daily loss check: Current Loss={loss_amount:.2f} USDT, Limit={max_allowed_loss:.2f} USDT. Within limits.")
                return True

        except Exception as e:
            self.logger.error(f"Error checking daily loss limit: {e}", exc_info=True)
            return False # Assume limit hit on error for safety

    # =====================================================================
    # ORDER MANAGEMENT
    # =====================================================================

    def place_order(self, side: str, qty: Decimal, order_type: OrderType,
                   entry_price: Decimal | None = None, stop_loss_price: Decimal | None = None,
                   take_profit_price: Decimal | None = None) -> dict | None:
        """Place an order on Bybit, handling precision and Bybit V5 API parameters. Enhanced for spot category."""
        specs = self.precision_manager.get_specs(self.config.SYMBOL) # Use precision_manager
        if not specs:
            self.logger.error(f"Cannot place order for {self.config.SYMBOL}: Specs not found.")
            return None

        try:
            # Round quantity and prices according to symbol specifications
            rounded_qty = self.precision_manager.round_quantity(self.config.SYMBOL, qty) # Use precision_manager

            # Basic validation before preparing order parameters
            if rounded_qty <= 0:
                self.logger.warning(f"Invalid quantity ({qty} rounded to {rounded_qty}) for order placement in {self.config.SYMBOL}. Aborting order.")
                return None

            # Prepare base order parameters
            params: dict[str, Any] = {
                "category": specs.category,
                "symbol": self.config.SYMBOL,
                "side": side,
                "orderType": order_type.value,
                "qty": str(rounded_qty),
                "timeInForce": self.config.TIME_IN_FORCE,
                "reduceOnly": self.config.REDUCE_ONLY,
                "closeOnTrigger": False, # Typically false unless specific use case
                "positionIdx": self.config.POSITION_IDX if self.config.HEDGE_MODE else 0 # Use configured positionIdx if hedge mode is enabled
            }

            # For spot, remove derivative-specific params that are not applicable
            if specs.category == 'spot':
                params.pop('reduceOnly', None)
                # Note: positionIdx might still be relevant for Bybit's spot API in some contexts, but generally 0 for spot.
                # We'll keep it as it is, Bybit's API should handle it.

            # Add price for limit orders
            if order_type == OrderType.LIMIT:
                if entry_price is None:
                    self.logger.error(f"Limit order requires an entry_price. Aborting order for {self.config.SYMBOL}.")
                    return None
                rounded_price = self.precision_manager.round_price(self.config.SYMBOL, entry_price) # Use precision_manager
                if rounded_price <= 0:
                    self.logger.warning(f"Invalid entry price ({entry_price} rounded to {rounded_price}) for limit order in {self.config.SYMBOL}. Aborting order.")
                    return None
                params["price"] = str(rounded_price)

            # Add stop loss if provided
            if stop_loss_price is not None:
                rounded_sl = self.precision_manager.round_price(self.config.SYMBOL, stop_loss_price) # Use precision_manager
                if rounded_sl > 0: # Ensure SL is valid
                    params["stopLoss"] = str(rounded_sl)
                    params["slOrderType"] = "Market" # Common practice: SL triggers as Market order

            # Add take profit if provided
            if take_profit_price is not None:
                rounded_tp = self.precision_manager.round_price(self.config.SYMBOL, take_profit_price) # Use precision_manager
                if rounded_tp > 0: # Ensure TP is valid
                    params["takeProfit"] = str(rounded_tp)
                    params["tpOrderType"] = "Limit" # Common practice: TP triggers as Limit order

            # Set TPSL mode if either SL or TP is provided
            if "stopLoss" in params or "takeProfit" in params:
                params["tpslMode"] = "Full" # Default to Full TP/SL

            self.logger.debug(f"Placing order with parameters: {params}")

            # Execute the order placement API call
            response = self.session.place_order(**params)

            if response and response['retCode'] == 0:
                order_id = response['result']['orderId']
                order_link_id = response['result'].get('orderLinkId', 'N/A') # orderLinkId is optional but good to track
                self.logger.info(f"Order placed successfully: {side} {rounded_qty} {self.config.SYMBOL} ({order_type.value}), OrderID: {order_id}, OrderLinkId: {order_link_id}")
                if "stopLoss" in params:
                    self.logger.info(f"  Stop Loss set to: {params['stopLoss']}")
                if "takeProfit" in params:
                    self.logger.info(f"  Take Profit set to: {params['takeProfit']}")

                # Store open order details locally for tracking
                self.open_orders[order_id] = {
                    'symbol': self.config.SYMBOL,
                    'side': side,
                    'qty': rounded_qty,
                    'type': order_type.value,
                    'price': params.get('price'),
                    'stopLoss': params.get('stopLoss'),
                    'takeProfit': params.get('takeProfit'),
                    'status': 'New', # Initial status
                    'orderLinkId': order_link_id
                }
                return response['result']
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.logger.error(f"Failed to place order for {self.config.SYMBOL}: {error_msg}")
                return None

        except Exception as e:
            self.logger.error(f"Exception placing order for {self.config.SYMBOL}: {e}", exc_info=True)
            return None

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific open order."""
        specs = self.precision_manager.get_specs(self.config.SYMBOL) # Use precision_manager
        if not specs:
            self.logger.error(f"Cannot cancel order {order_id} for {self.config.SYMBOL}: Specs not found.")
            return False

        try:
            self.logger.debug(f"Attempting to cancel order {order_id} for {self.config.SYMBOL}...")
            response = self.session.cancel_order(
                category=specs.category,
                symbol=self.config.SYMBOL,
                orderId=order_id
            )

            if response and response['retCode'] == 0:
                self.logger.info(f"Order {order_id} cancelled successfully for {self.config.SYMBOL}.")
                # Remove from open orders tracking if it exists
                self.open_orders.pop(order_id, None)
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.logger.error(f"Failed to cancel order {order_id} for {self.config.SYMBOL}: {error_msg}")
                return False

        except Exception as e:
            self.logger.error(f"Exception cancelling order {order_id} for {self.config.SYMBOL}: {e}", exc_info=True)
            return False

    def cancel_all_orders(self) -> bool:
        """Cancel all open orders for the configured symbol."""
        specs = self.precision_manager.get_specs(self.config.SYMBOL) # Use precision_manager
        if not specs:
            self.logger.error(f"Cannot cancel all orders for {self.config.SYMBOL}: Specs not found.")
            return False

        try:
            self.logger.info(f"Attempting to cancel all open orders for {self.config.SYMBOL}...")
            response = self.session.cancel_all_orders(
                category=specs.category,
                symbol=self.config.SYMBOL
            )

            if response and response['retCode'] == 0:
                self.logger.info(f"All open orders successfully cancelled for {self.config.SYMBOL}.")
                # Clear local tracking of open orders
                self.open_orders.clear()
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.logger.error(f"Failed to cancel all orders for {self.config.SYMBOL}: {error_msg}")
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
            response = self.session.get_open_orders(
                category=specs.category,
                symbol=self.config.SYMBOL
            )
            if response and response['retCode'] == 0:
                orders = response['result'].get('list', [])
                self.open_orders.clear()
                for order in orders:
                    self.open_orders[order['orderId']] = order
                self.logger.debug(f"Fetched {len(orders)} open orders for {self.config.SYMBOL}.")
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.logger.error(f"Failed to fetch open orders for {self.config.SYMBOL}: {error_msg}")
        except Exception as e:
            self.logger.error(f"Exception fetching open orders for {self.config.SYMBOL}: {e}", exc_info=True)

    # =====================================================================
    # POSITION MANAGEMENT
    # =====================================================================

    def get_positions(self):
        """Fetch and update current positions for the configured symbol."""
        specs = self.precision_manager.get_specs(self.config.SYMBOL) # Use precision_manager
        if not specs:
            self.logger.error(f"Cannot get positions for {self.config.SYMBOL}: Specs not found.")
            return

        # Spot trading doesn't have open positions in the same way derivatives do.
        # We'll reset state if category is spot, as position management is different.
        if specs.category == 'spot':
            self.logger.debug("Position status reset for spot category.")
            self.position_active = False
            self.current_position_side = None
            self.current_position_entry_price = Decimal('0')
            self.current_position_size = Decimal('0')
            self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)
            return

        try:
            self.logger.debug(f"Fetching positions for {self.config.SYMBOL}...")
            response = self.session.get_positions(
                category=specs.category,
                symbol=self.config.SYMBOL
            )

            if response and response['retCode'] == 0:
                positions_list = response['result'].get('list', [])
                self.current_positions = {} # Reset current positions for this symbol

                found_position_for_symbol = False
                for pos in positions_list:
                    # Only consider positions with size > 0
                    if Decimal(pos.get('size', '0')) > 0:
                        # Store all active positions if needed, but focus on the bot's target symbol
                        self.current_positions[pos['symbol']] = pos

                        if pos['symbol'] == self.config.SYMBOL:
                            found_position_for_symbol = True
                            # Update strategy state variables
                            self.position_active = True
                            self.current_position_side = pos['side']
                            self.current_position_entry_price = Decimal(pos.get('avgPrice', '0'))
                            self.current_position_size = Decimal(pos['size'])

                            # Initialize trailing stop if active and not already initialized/updated
                            if self.config.TRAILING_STOP_PCT > 0 and self.config.ORDER_TYPE_ENUM == OrderType.MARKET:
                                # Ensure markPrice is available for trailing stop activation logic
                                mark_price_str = pos.get('markPrice')
                                if mark_price_str:
                                    current_mark_price = Decimal(mark_price_str)
                                    # Only initialize if the stop hasn't been set or if it needs resetting
                                    if self.config.SYMBOL not in self.trailing_stop_manager.active_trailing_stops or \
                                       self.trailing_stop_manager.active_trailing_stops[self.config.SYMBOL]['current_stop'] == 0:
                                        self.logger.info(f"Initializing trailing stop for {self.config.SYMBOL} at entry {self.current_position_entry_price:.4f}")
                                        self.trailing_stop_manager.initialize_trailing_stop(
                                            symbol=self.config.SYMBOL,
                                            position_side=pos['side'],
                                            entry_price=self.current_position_entry_price,
                                            current_price=current_mark_price, # Use mark price for TS init/update
                                            trail_percent=self.config.TRAILING_STOP_PCT * 100, # Pass as percentage
                                            activation_percent=self.config.TRAILING_STOP_PCT * 100 # Simple activation for now (can be made configurable)
                                        )
                                else:
                                    self.logger.warning(f"Mark price not available for {self.config.SYMBOL} position, cannot initialize trailing stop.")
                            break # Assume only one position for the target symbol

                # If no position found for the target symbol after checking all
                if not found_position_for_symbol:
                    # Reset strategy state if position is closed
                    if self.position_active: # Log that the position was closed
                        self.logger.info(f"Position for {self.config.SYMBOL} was closed.")
                    self.position_active = False
                    self.current_position_side = None
                    self.current_position_entry_price = Decimal('0')
                    self.current_position_size = Decimal('0')
                    # Remove any trailing stop data associated with this symbol
                    self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)

                self.logger.debug(f"Position status update: Active={self.position_active}, Side={self.current_position_side}, Size={self.current_position_size}, Entry={self.current_position_entry_price}")

            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.logger.error(f"Failed to get positions for {self.config.SYMBOL}: {error_msg}")
                # If API fails to get positions, assume no position for safety
                self.position_active = False
                self.current_position_side = None
                self.current_position_entry_price = Decimal('0')
                self.current_position_size = Decimal('0')
                self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)

        except Exception as e:
            self.logger.error(f"Exception getting positions for {self.config.SYMBOL}: {e}", exc_info=True)
            # If an exception occurs, assume no position for safety
            self.position_active = False
            self.current_position_side = None
            self.current_position_entry_price = Decimal('0')
            self.current_position_size = Decimal('0')
            self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)


    def close_position(self) -> bool:
        """Close the current open position for the target symbol by placing a Market order."""
        if not self.position_active or not self.current_position_side or self.current_position_size <= 0:
            self.logger.warning(f"No active position or position size is zero to close for {self.config.SYMBOL}.")
            return False

        specs = self.precision_manager.get_specs(self.config.SYMBOL) # Use precision_manager
        if not specs:
            self.logger.error(f"Cannot close position for {self.config.SYMBOL}: Specs not found.")
            return False

        # Spot category is handled differently if closing positions is needed.
        # For this bot's current logic (derivatives focus), we'll warn if trying to close on spot.
        if specs.category == 'spot':
            self.logger.warning(f"Attempting to close position for spot symbol {self.config.SYMBOL}. Spot position management is not explicitly handled here. Consider manual closing.")
            return False

        try:
            # Determine the side to place the closing order (opposite of current position)
            close_side = "Sell" if self.current_position_side == "Buy" else "Buy"

            self.logger.info(f"Attempting to close {self.config.SYMBOL} position ({self.current_position_side} {self.current_position_size} {specs.base_currency}).")

            # Place a Market order to close the position
            # Note: No SL/TP needed for a simple market close order.
            result = self.place_order(
                side=close_side,
                qty=self.current_position_size,
                order_type=OrderType.MARKET
            )

            if result:
                self.logger.info(f"Market order to close {self.config.SYMBOL} position placed successfully.")
                # Immediately update internal state. The actual position closure will be confirmed
                # by the next call to get_positions().
                self.position_active = False
                self.current_position_side = None
                self.current_position_entry_price = Decimal('0')
                self.current_position_size = Decimal('0')
                self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL)
                return True
            else:
                self.logger.error(f"Failed to place market order to close position for {self.config.SYMBOL}.")
                return False

        except Exception as e:
            self.logger.error(f"Exception closing position for {self.config.SYMBOL}: {e}", exc_info=True)
            return False

    def update_stop_loss(self, stop_loss_price: Decimal) -> bool:
        """Update the stop loss for the current position on the exchange."""
        if not self.position_active:
            self.logger.warning(f"No active position to update stop loss for {self.config.SYMBOL}.")
            return False

        specs = self.precision_manager.get_specs(self.config.SYMBOL) # Use precision_manager
        if not specs:
            self.logger.error(f"Cannot update stop loss for {self.config.SYMBOL}: Specs not found.")
            return False

        # Spot category does not support direct stop loss setting via set_trading_stop.
        if specs.category == 'spot':
            self.logger.warning("Stop loss updates via set_trading_stop not supported for spot category.")
            return False

        try:
            # Round the stop loss price to the correct tick size
            rounded_sl = self.precision_manager.round_price(self.config.SYMBOL, stop_loss_price) # Use precision_manager
            if rounded_sl <= 0:
                self.logger.warning(f"Invalid stop loss price provided ({stop_loss_price} rounded to {rounded_sl}). Cannot update.")
                return False

            self.logger.debug(f"Attempting to update stop loss for {self.config.SYMBOL} to {rounded_sl}...")
            response = self.session.set_trading_stop(
                category=specs.category,
                symbol=self.config.SYMBOL,
                stopLoss=str(rounded_sl),
                slOrderType='Market' # Ensure SL is a Market order for execution
            )

            if response and response['retCode'] == 0:
                self.logger.info(f"Stop loss updated successfully on exchange for {self.config.SYMBOL} to {rounded_sl}")
                # Update internal state if needed (though often not necessary if only exchange SL is changed)
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.logger.error(f"Failed to update stop loss on exchange for {self.config.SYMBOL}: {error_msg}")
                return False

        except Exception as e:
            self.logger.error(f"Exception updating stop loss on exchange for {self.config.SYMBOL}: {e}", exc_info=True)
            return False

    # =====================================================================
    # ACCOUNT MANAGEMENT
    # =====================================================================

    def get_account_balance_usdt(self) -> Decimal:
        """Get current account balance in USDT and update internal state. Enhanced for unified accounts."""
        # Determine the account type to query based on the configured category
        account_type = "UNIFIED" # Default for derivatives (linear, inverse, option)
        if self.config.CATEGORY_ENUM == Category.SPOT:
            account_type = "SPOT"

        try:
            self.logger.debug(f"Fetching wallet balance for account type: {account_type}...")
            response = self.session.get_wallet_balance(accountType=account_type)

            if response and response['retCode'] == 0:
                balances = response['result'].get('list', [])
                # Find USDT balance
                for coin_data in balances:
                    if coin_data.get('coin') == 'USDT':
                        # Wallet balance is typically the total balance including margin
                        balance = Decimal(coin_data.get('walletBalance', '0'))
                        self.account_balance_usdt = balance
                        self.logger.debug(f"Successfully fetched account balance: {balance:.4f} USDT ({account_type})")
                        return balance

                # If USDT is not found, return 0
                self.logger.warning(f"USDT balance not found in response for account type {account_type}. Returning 0.")
                self.account_balance_usdt = Decimal('0.0')
                return Decimal('0.0')
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                self.logger.error(f"Failed to get account balance ({account_type}): {error_msg}")
                self.account_balance_usdt = Decimal('0.0') # Assume zero balance on error
                return Decimal('0.0')

        except Exception as e:
            self.logger.error(f"Exception getting account balance ({account_type}): {e}", exc_info=True)
            self.account_balance_usdt = Decimal('0.0') # Assume zero balance on error
            return Decimal('0.0')

    def set_leverage(self) -> bool:
        """Set leverage for the trading symbol, respecting min/max/step limits."""
        # Spot trading does not use leverage, so skip for spot category
        if self.config.CATEGORY_ENUM == Category.SPOT:
            self.logger.info("Spot trading does not use leverage. Skipping leverage setting.")
            return True

        specs = self.precision_manager.get_specs(self.config.SYMBOL) # Use precision_manager
        if not specs:
            self.logger.error(f"Cannot set leverage for {self.config.SYMBOL}: Specs not found.")
            return False

        try:
            leverage_to_set_decimal = Decimal(str(self.config.LEVERAGE))
            min_lev = specs.min_leverage
            max_lev = specs.max_leverage
            lev_step = specs.leverage_step

            # Clamp leverage to valid range
            if leverage_to_set_decimal < min_lev:
                self.logger.warning(f"Requested leverage {leverage_to_set_decimal} for {self.config.SYMBOL} is below minimum {min_lev}. Setting to minimum.")
                leverage_to_set_decimal = min_lev
            elif leverage_to_set_decimal > max_lev:
                self.logger.warning(f"Requested leverage {leverage_to_set_decimal} for {self.config.SYMBOL} exceeds maximum {max_lev}. Setting to maximum.")
                leverage_to_set_decimal = max_lev

            # Adjust leverage to the nearest valid step if step is defined and > 0
            if lev_step > 0:
                # Calculate how many steps are needed
                num_steps = (leverage_to_set_decimal / lev_step).quantize(Decimal('1'), rounding=ROUND_DOWN)
                leverage_to_set_decimal = num_steps * lev_step
                # Re-clamp to ensure it didn't go out of bounds due to rounding
                leverage_to_set_decimal = max(min_lev, min(leverage_to_set_decimal, max_lev))

            # The set_leverage method expects strings for leverage values
            leverage_str = str(leverage_to_set_decimal)

            # Bybit V5 set_leverage parameters: category, symbol, buyLeverage, sellLeverage
            # For one-way mode, buy and sell leverage should be the same.
            # For hedge mode, they can potentially differ, but we'll use the same value.
            response = self.session.set_leverage(
                category=self.config.CATEGORY_ENUM.value, # Use the validated category enum value
                symbol=self.config.SYMBOL,
                buyLeverage=leverage_str,
                sellLeverage=leverage_str
            )

            if response and response['retCode'] == 0:
                self.logger.info(f"Leverage set successfully to {leverage_str}x for {self.config.SYMBOL}.")
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error') if response else 'No response'
                # Common error: Leverage already set to the same value
                if "leverage is already set" in error_msg.lower() or "same as the current" in error_msg.lower():
                    self.logger.info(f"Leverage for {self.config.SYMBOL} is already set to {leverage_str}x. No change needed.")
                    return True
                # Handle errors indicating leverage might not be applicable or supported for the symbol/category
                elif "leverage not modified" in error_msg.lower() or "illegal category" in error_msg.lower() or "110043" in str(response.get('retCode')):
                     self.logger.warning(f"Could not set leverage for {self.config.SYMBOL} ({self.config.CATEGORY_ENUM.value}): Leverage may not be supported, applicable for this symbol/category, or already set correctly. Error: {error_msg}")
                     # Return True as the bot should not fail if leverage is not applicable, as long as it doesn't actively prevent trading.
                     return True
                else:
                    self.logger.error(f"Failed to set leverage for {self.config.SYMBOL}: {error_msg}")
                    return False

        except InvalidRequestError as e:
            # Catch specific Bybit API errors for invalid requests, which leverage setting might fall into.
            self.logger.error(f"Invalid request error setting leverage for {self.config.SYMBOL}: {e}. This might indicate the symbol or category does not support leverage adjustments.", exc_info=True)
            return False # Propagate failure
        except Exception as e:
            self.logger.error(f"Exception setting leverage for {self.config.SYMBOL}: {e}", exc_info=True)
            return False

    # =====================================================================
    # MAIN EXECUTION LOOP
    # =====================================================================

    def execute_trade_based_on_signal(self, signal: Signal):
        """
        Execute trades based on the generated signal and current position state.
        Manages opening new positions, closing existing ones based on signal reversal,
        and updating stop losses (including trailing stops).
        """
        # Check if trading is allowed based on daily loss limit
        if not self.check_daily_loss_limit():
            self.logger.warning("Daily loss limit reached. Skipping trade execution for this cycle.")
            return

        # Fetch current market data (ticker for price)
        ticker = self.get_ticker()
        if not ticker:
            self.logger.warning("Could not retrieve ticker data. Cannot execute trade based on signal.")
            return

        try:
            # Extract current price using Decimal for precision
            current_price_str = ticker.get('lastPrice')
            if not current_price_str:
                self.logger.warning(f"Ticker data for {self.config.SYMBOL} is missing 'lastPrice'. Cannot proceed.")
                return
            current_price = Decimal(current_price_str)

            # Ensure we have valid instrument specifications for precision rounding
            specs = self.precision_manager.get_specs(self.config.SYMBOL) # Use precision_manager
            if not specs:
                self.logger.error(f"Instrument specifications not found for {self.config.SYMBOL}. Cannot execute trade.")
                return

            # --- State Management & Trade Execution ---

            # 1. Handle Opening New Positions
            # If we are NOT in a position and receive a BUY signal (BUY or STRONG_BUY)
            if not self.position_active and signal in [Signal.BUY, Signal.STRONG_BUY]:
                self.logger.info(f"Received BUY signal ({signal.name}). Attempting to open long position.")

                # Calculate Stop Loss and Take Profit prices
                stop_loss_price = current_price * (Decimal('1') - Decimal(str(self.config.STOP_LOSS_PCT)))
                take_profit_price = current_price * (Decimal('1') + Decimal(str(self.config.TAKE_PROFIT_PCT)))

                # Calculate position size in base currency units
                position_qty = self.calculate_position_size_usd(
                    entry_price=float(current_price), # Pass as float for calculator's internal usage, will be converted to Decimal
                    stop_loss_price=float(stop_loss_price) # Pass as float
                )

                if position_qty is not None and position_qty > 0:
                    # Place the order (Market or Limit as configured)
                    order_result = self.place_order(
                        side="Buy",
                        qty=position_qty,
                        order_type=self.config.ORDER_TYPE_ENUM,
                        entry_price=current_price if self.config.ORDER_TYPE_ENUM == OrderType.LIMIT else None,
                        stop_loss_price=stop_loss_price, # SL/TP are handled in place_order to check category
                        take_profit_price=take_profit_price
                    )

                    if order_result:
                        # Update internal state tentatively. Real position confirmation comes from get_positions().
                        self.position_active = True # Mark as active, will be confirmed next loop
                        self.current_position_side = "Buy"
                        self.current_position_entry_price = current_price
                        self.current_position_size = position_qty
                        self.logger.info("BUY order placed successfully. Waiting for position confirmation.")
                    else:
                        self.logger.error("Failed to place BUY order.")
                else:
                    self.logger.warning("Could not calculate a valid position size for the BUY signal. Skipping order placement.")

            # If we are NOT in a position and receive a SELL signal (SELL or STRONG_SELL)
            elif not self.position_active and signal in [Signal.SELL, Signal.STRONG_SELL]:
                self.logger.info(f"Received SELL signal ({signal.name}). Attempting to open short position.")

                # Calculate Stop Loss and Take Profit prices
                stop_loss_price = current_price * (Decimal('1') + Decimal(str(self.config.STOP_LOSS_PCT)))
                take_profit_price = current_price * (Decimal('1') - Decimal(str(self.config.TAKE_PROFIT_PCT)))

                # Calculate position size in base currency units
                position_qty = self.calculate_position_size_usd(
                    entry_price=float(current_price),
                    stop_loss_price=float(stop_loss_price)
                )

                if position_qty is not None and position_qty > 0:
                    # Place the order (Market or Limit as configured)
                    order_result = self.place_order(
                        side="Sell",
                        qty=position_qty,
                        order_type=self.config.ORDER_TYPE_ENUM,
                        entry_price=current_price if self.config.ORDER_TYPE_ENUM == OrderType.LIMIT else None,
                        stop_loss_price=stop_loss_price,
                        take_profit_price=take_profit_price
                    )

                    if order_result:
                        self.position_active = True # Tentative state update
                        self.current_position_side = "Sell"
                        self.current_position_entry_price = current_price
                        self.current_position_size = position_qty
                        self.logger.info("SELL order placed successfully. Waiting for position confirmation.")
                    else:
                        self.logger.error("Failed to place SELL order.")
                else:
                    self.logger.warning("Could not calculate a valid position size for the SELL signal. Skipping order placement.")

            # 2. Handle Managing Existing Positions
            elif self.position_active: # If we are currently in a position
                # Check for signal reversal to close the position
                if self.current_position_side == "Buy" and signal in [Signal.SELL, Signal.STRONG_SELL]:
                    self.logger.info(f"Signal reversal to {signal.name} detected while in BUY position. Closing position.")
                    self.close_position() # Attempt to close the current position

                elif self.current_position_side == "Sell" and signal in [Signal.BUY, Signal.STRONG_BUY]:
                    self.logger.info(f"Signal reversal to {signal.name} detected while in SELL position. Closing position.")
                    self.close_position() # Attempt to close the current position

                # 3. Handle Trailing Stop Loss Updates
                # Only update trailing stop if enabled and we are in a position and the category supports it
                if self.config.TRAILING_STOP_PCT > 0 and specs.category != 'spot':
                    # The TrailingStopManager handles the logic of activation and price updates
                    # We need to provide the current market price (or mark price if available)
                    # From get_positions(), we might have 'markPrice' if available. Otherwise, use lastPrice from ticker.
                    current_price_for_ts = current_price
                    pos_data = self.current_positions.get(self.config.SYMBOL) # Get current position data
                    if pos_data and pos_data.get('markPrice'):
                        current_price_for_ts = Decimal(pos_data['markPrice'])

                    # Update trailing stop. The manager will decide if exchange SL needs updating.
                    # The update_exchange=True flag tells the manager to try and push changes to Bybit.
                    self.trailing_stop_manager.update_trailing_stop(
                        symbol=self.config.SYMBOL,
                        current_price=current_price_for_ts,
                        update_exchange=True
                    )

        except Exception as e:
            self.logger.error(f"An error occurred during trade execution logic for {self.config.SYMBOL}: {e}", exc_info=True)


    def run_strategy(self):
        """Main trading loop: fetch data, calculate indicators, generate signals, and execute trades."""
        try:
            # Initial setup: Set leverage and fetch initial state
            if not self.set_leverage():
                # The set_leverage method now handles SPOT category gracefully. If it still returns False for other reasons,
                # it's a critical failure.
                self.logger.critical("Failed to set initial leverage. Bot cannot proceed.")
                return

            # Fetch initial account balance and set daily loss limit
            initial_balance = self.get_account_balance_usdt()
            if initial_balance <= 0:
                self.logger.critical("Failed to get initial account balance or balance is zero. Bot cannot proceed.")
                return
            self.start_balance_usdt = initial_balance
            self.daily_loss_amount = self.start_balance_usdt * (Decimal(str(self.config.MAX_DAILY_LOSS_PCT)) / Decimal('100'))
            self.logger.info(f"Starting Balance: {self.start_balance_usdt:.4f} USDT. Daily Loss Limit: {self.daily_loss_amount:.4f} USDT.")

            # Fetch initial position status
            self.get_positions()

            # Main execution loop
            self.logger.info("Starting main trading loop...")
            while not self._stop_requested: # Loop until shutdown signal is received
                try:
                    # Fetch market data (klines)
                    self.market_data = self.fetch_klines()
                    if self.market_data.empty:
                        self.logger.warning("No market data fetched. Waiting for next interval.")
                        time.sleep(self.config.LOOP_INTERVAL_SEC)
                        continue # Skip to next loop iteration if no data

                    # Calculate technical indicators (Supertrend)
                    self.market_data = self.calculate_indicators(self.market_data)

                    # Generate trading signal based on the latest indicator data
                    current_signal = self.generate_signal(self.market_data)

                    # Refresh current position status before making trading decisions
                    # This ensures we know if we are in a position or if it was recently closed.
                    self.get_positions()

                    # Execute trades based on the generated signal and current position state
                    # This method also handles SL/TP and trailing stop updates.
                    self.execute_trade_based_on_signal(current_signal)

                    # --- Log Current Status Summary with Price and Indicator Values ---
                    current_balance = self.get_account_balance_usdt() # Fetch latest balance
                    pnl = current_balance - self.start_balance_usdt
                    pnl_pct = (pnl / self.start_balance_usdt * 100) if self.start_balance_usdt > 0 else Decimal('0')

                    # Extract latest price and indicator values for logging
                    current_price_log = Decimal('0.0')
                    supertrend_value_log = Decimal('0.0')
                    supertrend_direction_log = 0
                    if not self.market_data.empty and len(self.market_data) >= 1:
                        latest = self.market_data.iloc[-1]
                        current_price_log = latest.get('close', Decimal('0.0')) # Use close price as current price for logging
                        supertrend_value_log = latest.get('supertrend', Decimal('0.0'))
                        supertrend_direction_log = latest.get('supertrend_direction', 0)

                    # Format and log the detailed status
                    self.logger.info(
                        f"Loop Cycle Complete: "
                        f"Signal={current_signal.name:<12} | "
                        f"Price={current_price_log:<10.4f} | " # Displaying current price
                        f"ST={supertrend_value_log:<10.4f} | "   # Displaying Supertrend value
                        f"ST_Dir={supertrend_direction_log:<2} | " # Displaying Supertrend direction
                        f"Balance={current_balance:.4f} USDT | "
                        f"PnL={pnl:.4f} ({pnl_pct:.4f}%) | "
                        f"Pos Active={self.position_active} | "
                        f"Side={self.current_position_side or 'None'} | "
                        f"Open Orders={len(self.open_orders)}"
                    )

                    # Wait for the next interval before the next iteration
                    time.sleep(self.config.LOOP_INTERVAL_SEC)

                except KeyboardInterrupt:
                    self.logger.info("Trading loop interrupted by user (KeyboardInterrupt). Shutting down.")
                    break # Exit the loop on Ctrl+C
                except Exception as e:
                    self.logger.error(f"An unexpected error occurred in the main trading loop: {e}", exc_info=True)
                    # Wait before retrying to avoid rapid error loops
                    self.logger.info(f"Waiting {self.config.LOOP_INTERVAL_SEC} seconds before retrying...")
                    time.sleep(self.config.LOOP_INTERVAL_SEC)

        except Exception as e:
            self.logger.critical(f"A critical error occurred during strategy execution setup or loop: {e}", exc_info=True)
        finally:
            self.cleanup() # Ensure cleanup actions are performed

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
            total_pnl = final_balance - self.start_balance_usdt
            total_pnl_pct = (total_pnl / self.start_balance_usdt * 100) if self.start_balance_usdt > 0 else Decimal('0')

            self.logger.info("=" * 60)
            self.logger.info("Supertrend Trading Bot Stopped.")
            self.logger.info(f"Final Balance: {final_balance:.4f} USDT")
            self.logger.info(f"Total PnL: {total_pnl:.4f} USDT ({total_pnl_pct:.4f}%)")
            self.logger.info("=" * 60)

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
        bot = SupertrendBot(config)
        bot.run_strategy()

    except Exception as e:
        # Catch any unhandled exceptions during bot initialization or execution
        print(f"\nFATAL ERROR: An unhandled exception occurred: {e}")
        # Attempt to log the critical error if the logger is available
        try:
            # If bot object was partially initialized, try to use its logger
            if 'bot' in locals() and bot.logger:
                bot.logger.critical(f"FATAL ERROR: {e}", exc_info=True)
            else: # Otherwise, use a basic logger for fatal errors
                logging.basicConfig(level=logging.CRITICAL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                logging.critical(f"FATAL ERROR: {e}", exc_info=True)
        except Exception as log_e:
            print(f"Error occurred while trying to log fatal error: {log_e}")

        sys.exit(1) # Exit with a non-zero status code to indicate failure


if __name__ == "__main__":
    main()

