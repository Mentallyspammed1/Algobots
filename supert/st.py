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
"""

import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from enum import Enum

import pandas as pd
import pandas_ta as ta
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

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

@dataclass
class Config:
    """Bot configuration"""
    # API Configuration
    API_KEY: str = "YOUR_BYBIT_API_KEY"
    API_SECRET: str = "YOUR_BYBIT_API_SECRET"
    TESTNET: bool = True

    # Trading Configuration
    SYMBOL: str = "BTCUSDT"
    CATEGORY: Category = Category.LINEAR
    LEVERAGE: int = 5

    # Position Sizing
    RISK_PER_TRADE_PCT: float = 1.0  # Risk % of account balance per trade
    MAX_POSITION_SIZE_USD: float = 10000.0  # Max position value in USD
    MIN_POSITION_SIZE_USD: float = 10.0  # Min position value in USD

    # Strategy Parameters
    TIMEFRAME: str = "15"  # Kline interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)
    LOOKBACK_PERIODS: int = 100  # Historical data to fetch for indicators

    # Supertrend Indicator Parameters
    ST_PERIOD: int = 10  # ATR period for Supertrend
    ST_MULTIPLIER: float = 3.0  # Multiplier for ATR

    # Risk Management
    STOP_LOSS_PCT: float = 0.015  # 1.5% stop loss from entry
    TAKE_PROFIT_PCT: float = 0.03  # 3% take profit from entry
    TRAILING_STOP_PCT: float = 0.005 # 0.5% trailing stop from highest profit
    MAX_DAILY_LOSS_PCT: float = 0.05 # 5% max daily loss from start balance
    MAX_OPEN_POSITIONS: int = 1

    # Execution Settings
    ORDER_TYPE: OrderType = OrderType.MARKET
    TIME_IN_FORCE: str = "GTC"  # 'GTC', 'IOC', 'FOK', 'PostOnly'
    REDUCE_ONLY: bool = False

    # Bot Settings
    LOOP_INTERVAL_SEC: int = 60  # Check interval in seconds
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "supertrend_bot.log"

# =====================================================================
# LOGGING SETUP
# =====================================================================

def setup_logger(config: Config) -> logging.Logger:
    """Setup logging configuration"""
    logger = logging.getLogger('SupertrendBot')
    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper()))

    # Prevent duplicate handlers if called multiple times
    if not logger.handlers:
        # File handler
        fh = logging.FileHandler(config.LOG_FILE)
        fh.setLevel(logging.DEBUG)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        logger.addHandler(fh)
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

    contract_value: Decimal = Decimal('1')
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
        categories = [cat.value for cat in Category]

        for category in categories:
            try:
                response = self.session.get_instruments_info(category=category)

                if response['retCode'] == 0:
                    for inst in response['result']['list']:
                        symbol = inst['symbol']

                        specs = self._parse_instrument_specs(inst, category)
                        self.instruments[symbol] = specs

            except Exception as e:
                self.logger.error(f"Error loading {category} instruments: {e}")

    def _parse_instrument_specs(self, inst: dict, category: str) -> InstrumentSpecs:
        """Parse instrument specifications based on category"""
        lot_size = inst.get('lotSizeFilter', {})
        price_filter = inst.get('priceFilter', {})
        leverage_filter = inst.get('leverageFilter', {})

        # Default values for filters that might be missing
        lot_size = lot_size if lot_size else {'minOrderQty': '0', 'maxOrderQty': '1e9', 'qtyStep': '0.001'}
        price_filter = price_filter if price_filter else {'minPrice': '0', 'maxPrice': '1e9', 'tickSize': '0.01'}
        leverage_filter = leverage_filter if leverage_filter else {'minLeverage': '1', 'maxLeverage': '10', 'leverageStep': '0.1'}

        # Extracting fees (may not be present for all categories or might be default)
        maker_fee = Decimal(inst.get('makerFeeRate', '0.0001'))
        taker_fee = Decimal(inst.get('takerFeeRate', '0.0006'))

        return InstrumentSpecs(
            symbol=inst['symbol'],
            category=category,
            base_currency=inst['baseCoin'],
            quote_currency=inst['quoteCoin'],
            status=inst['status'],
            min_price=Decimal(price_filter.get('minPrice', '0')),
            max_price=Decimal(price_filter.get('maxPrice', '1e9')),
            tick_size=Decimal(price_filter.get('tickSize', '0.01')),
            min_order_qty=Decimal(lot_size['minOrderQty']),
            max_order_qty=Decimal(lot_size['maxOrderQty']),
            qty_step=Decimal(lot_size['qtyStep']),
            min_leverage=Decimal(leverage_filter['minLeverage']),
            max_leverage=Decimal(leverage_filter['maxLeverage']),
            leverage_step=Decimal(leverage_filter['leverageStep']),
            max_position_value=Decimal(lot_size.get('maxMktOrderQty', lot_size.get('maxOrderAmt', '1e9'))), # Use different keys for different categories
            min_position_value=Decimal(lot_size.get('minOrderAmt', lot_size.get('minOrderQty', '1'))),
            contract_value=Decimal(inst.get('contractValue', '1')), # For derivatives
            is_inverse=(category == 'inverse'),
            maker_fee=maker_fee,
            taker_fee=taker_fee
        )

    def get_specs(self, symbol: str) -> InstrumentSpecs | None:
        """Get instrument specs for a symbol"""
        return self.instruments.get(symbol)

    def round_price(self, symbol: str, price: float | Decimal) -> Decimal:
        """Round price to correct tick size"""
        specs = self.get_specs(symbol)
        if not specs:
            self.logger.warning(f"Symbol {symbol} specs not found, using default rounding.")
            return Decimal(str(price)).quantize(Decimal('0.00000001')) # Default high precision

        price_decimal = Decimal(str(price))
        tick_size = specs.tick_size

        # Round to nearest tick, ensure it's within bounds
        rounded = (price_decimal / tick_size).quantize(Decimal('1'), rounding=ROUND_DOWN) * tick_size
        rounded = max(specs.min_price, min(rounded, specs.max_price))

        return rounded

    def round_quantity(self, symbol: str, quantity: float | Decimal) -> Decimal:
        """Round quantity to correct step size"""
        specs = self.get_specs(symbol)
        if not specs:
            self.logger.warning(f"Symbol {symbol} specs not found, using default rounding.")
            return Decimal(str(quantity)).quantize(Decimal('0.00000001')) # Default high precision

        qty_decimal = Decimal(str(quantity))
        qty_step = specs.qty_step

        # Round down to nearest step, ensure it's within bounds
        rounded = (qty_decimal / qty_step).quantize(Decimal('1'), rounding=ROUND_DOWN) * qty_step
        rounded = max(specs.min_order_qty, min(rounded, specs.max_order_qty))

        return rounded

    def get_decimal_places(self, symbol: str) -> tuple[int, int]:
        """Get decimal places for price and quantity"""
        specs = self.get_specs(symbol)
        if not specs:
            return 2, 3  # Default values if specs are missing

        try:
            price_decimals = abs(specs.tick_size.as_tuple().exponent)
            qty_decimals = abs(specs.qty_step.as_tuple().exponent)
            return price_decimals, qty_decimals
        except Exception:
            return 2, 3 # Fallback

# =====================================================================
# ORDER SIZING CALCULATOR
# =====================================================================

class OrderSizingCalculator:
    """Calculate optimal order sizes based on risk management"""

    def __init__(self, precision_manager: PrecisionManager, logger: logging.Logger):
        self.precision = precision_manager
        self.logger = logger

    def calculate_position_size_fixed_risk(
        self,
        symbol: str,
        account_balance_usdt: float,
        risk_percent: float,
        entry_price: float,
        stop_loss_price: float,
        leverage: float = 1.0
    ) -> Decimal | None:
        """
        Calculate position size based on fixed risk percentage and leverage.
        Returns position size in base currency units.
        """
        specs = self.precision.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot calculate position size: Symbol {symbol} specs not found.")
            return None

        # Convert to Decimal for precision
        balance = Decimal(str(account_balance_usdt))
        risk_pct = Decimal(str(risk_percent / 100))
        entry = Decimal(str(entry_price))
        stop_loss = Decimal(str(stop_loss_price))
        lev = Decimal(str(leverage))

        # Calculate risk amount
        risk_amount = balance * risk_pct

        # Calculate stop loss distance in price terms
        stop_distance_price = abs(entry - stop_loss)

        # Calculate stop loss distance in percentage terms
        stop_distance_pct = (stop_distance_price / entry) if entry > 0 else Decimal('0')

        # Calculate position value needed to risk 'risk_amount'
        if stop_distance_pct > 0:
            position_value_needed = risk_amount / stop_distance_pct
        else:
            self.logger.warning(f"Stop loss distance is zero for {symbol}. Cannot calculate size.")
            return None



        # Calculate the quantity based on the position value needed and entry price
        if specs.category == 'spot':
            # For spot, position value is directly quantity * price
            quantity = position_value_needed / entry
        elif specs.category in ['linear', 'inverse']:
            # For derivatives, contract value might matter, but typically quantity
            # is in base currency
            # Linear: quantity is in base currency, value is quantity * price (in quote)
            # Inverse: quantity is in base currency, value is quantity * contract_value (in base)
            quantity = position_value_needed / entry # For linear, this is the quantity of base currency
        else:  # option
            quantity = position_value_needed / entry # Assuming option price is per contract

        # Round quantity to correct precision
        quantity = self.precision.round_quantity(symbol, quantity)

        # Validate against min/max quantity and value limits
        if quantity < specs.min_order_qty:
            self.logger.warning(f"Calculated quantity {quantity} for {symbol} is below minimum {specs.min_order_qty}.")
            quantity = specs.min_order_qty
        elif quantity > specs.max_order_qty:
            self.logger.warning(f"Calculated quantity {quantity} for {symbol} is above maximum {specs.max_order_qty}.")
            quantity = specs.max_order_qty

        # Calculate actual position value and check against max position value
        actual_position_value = quantity * entry
        if actual_position_value > specs.max_position_value:
            self.logger.warning(f"Calculated position value {actual_position_value:.2f} for {symbol} exceeds max {specs.max_position_value:.2f}.")
            # Adjust quantity to fit max position value
            quantity = self.precision.round_quantity(symbol, specs.max_position_value / entry)
            actual_position_value = quantity * entry

        # Ensure minimum position value is met
        if actual_position_value < specs.min_position_value:
            self.logger.warning(f"Calculated position value {actual_position_value:.2f} for {symbol} is below minimum {specs.min_position_value:.2f}.")
            # Adjust quantity to meet minimum position value
            quantity = self.precision.round_quantity(symbol, specs.min_position_value / entry)
            actual_position_value = quantity * entry

        # Recalculate actual risk based on final quantity
        final_risk_amount = actual_position_value * stop_distance_pct / lev
        final_risk_pct = (final_risk_amount / balance * 100) if balance > 0 else Decimal('0')

        self.logger.debug(f"Size Calc {symbol}: Qty={quantity}, Value={actual_position_value:.2f}, Risk={final_risk_amount:.2f} ({final_risk_pct:.2f}%)")

        return quantity

# =====================================================================
# TRAILING STOP MANAGER
# =====================================================================

class TrailingStopManager:
    """Manage trailing stop losses for profitable positions"""

    def __init__(self, session: HTTP, precision_manager: PrecisionManager, logger: logging.Logger):
        self.session = session
        self.precision = precision_manager
        self.logger = logger
        # Stores active trailing stop info: {symbol: {'side': 'Buy'/'Sell',
        # 'activation_price': Decimal, 'trail_percent': Decimal,
        # 'current_stop': Decimal, 'highest_price': Decimal/None,
        # 'lowest_price': Decimal/None}}
        self.active_trailing_stops: dict[str, dict] = {}

    def initialize_trailing_stop(
        self,
        symbol: str,
        position_side: str,
        entry_price: float,
        current_price: float,
        trail_percent: float = 1.0,
        activation_percent: float = 0.5
    ) -> dict | None:
        """
        Initialize trailing stop for a position.
        Returns the initial trailing stop configuration if successful.
        """
        specs = self.precision.get_specs(symbol)
        if not specs:
            self.logger.error(f"Cannot initialize trailing stop for {symbol}: Specs not found.")
            return None

        entry = Decimal(str(entry_price))
        current = Decimal(str(current_price))
        trail_pct = Decimal(str(trail_percent / 100))
        activation_pct = Decimal(str(activation_percent / 100))

        activation_price = Decimal('0')
        current_stop = Decimal('0')
        highest_price = None
        lowest_price = None

        if position_side == "Buy":
            activation_price = entry * (Decimal('1') + activation_pct)
            is_activated = current >= activation_price
            highest_price = current if is_activated else entry # Track highest price reached
            current_stop = self.precision.round_price(symbol, highest_price * (Decimal('1') - trail_pct))
        else:  # Sell/Short
            activation_price = entry * (Decimal('1') - activation_pct)
            is_activated = current <= activation_price
            lowest_price = current if is_activated else entry # Track lowest price reached
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
        self.logger.info(f"Initialized trailing stop for {symbol} ({position_side}): Initial Stop={current_stop}, Activation={activation_price}")
        return trailing_stop_info

    def update_trailing_stop(
        self,
        symbol: str,
        current_price: float,
        update_exchange: bool = True
    ) -> bool:
        """
        Update trailing stop based on current price.
        Returns True if the stop was potentially updated or needs exchange update.
        """
        if symbol not in self.active_trailing_stops:
            return False

        ts_info = self.active_trailing_stops[symbol]
        current = Decimal(str(current_price))
        updated_locally = False

        if ts_info['side'] == "Buy":
            # Activate if not already and price crosses activation level
            if not ts_info['is_activated'] and current >= ts_info['activation_price']:
                ts_info['is_activated'] = True
                ts_info['highest_price'] = current # Start tracking from activation price
                self.logger.info(f"Trailing stop activated for {symbol} at {current}.")

            # If activated, update highest price and stop if current price is higher
            if ts_info['is_activated'] and current > ts_info['highest_price']:
                ts_info['highest_price'] = current
                new_stop = current * (Decimal('1') - ts_info['trail_percent'])

                # Only update if the new stop is higher than the current stop
                if new_stop > ts_info['current_stop']:
                    ts_info['current_stop'] = self.precision.round_price(symbol, new_stop)
                    updated_locally = True
                    self.logger.debug(f"Trailing stop updated for {symbol}: {ts_info['current_stop']}")

        else:  # Sell/Short position
            # Activate if not already and price crosses activation level
            if not ts_info['is_activated'] and current <= ts_info['activation_price']:
                ts_info['is_activated'] = True
                ts_info['lowest_price'] = current # Start tracking from activation price
                self.logger.info(f"Trailing stop activated for {symbol} at {current}.")

            # If activated, update lowest price and stop if current price is lower
            if ts_info['is_activated'] and current < ts_info['lowest_price']:
                ts_info['lowest_price'] = current
                new_stop = current * (Decimal('1') + ts_info['trail_percent'])

                # Only update if the new stop is lower than the current stop
                if new_stop < ts_info['current_stop']:
                    ts_info['current_stop'] = self.precision.round_price(symbol, new_stop)
                    updated_locally = True
                    self.logger.debug(f"Trailing stop updated for {symbol}: {ts_info['current_stop']}")

        ts_info['last_update'] = datetime.now()

        # If locally updated and exchange update is requested, attempt to update exchange
        if updated_locally and update_exchange:
            self.logger.debug(f"Attempting to update stop loss on exchange for {symbol} to {ts_info['current_stop']}")
            return self._update_stop_loss_on_exchange(symbol, ts_info['current_stop'])

        return updated_locally # Return True if locally updated, False otherwise

    def _update_stop_loss_on_exchange(self, symbol: str, stop_price: Decimal) -> bool:
        """Update stop loss on exchange using set_trading_stop"""
        specs = self.precision.get_specs(symbol)
        if not specs:
            self.logger.error(f"Failed to update stop loss for {symbol}: Specs not found.")
            return False

        try:
            response = self.session.set_trading_stop(
                category=specs.category,
                symbol=symbol,
                stopLoss=str(stop_price),
                # tpOrderType='Limit', # Can also set TP here if needed
                # slOrderType='Market' # Default is Market for SL
            )

            if response['retCode'] == 0:
                self.logger.info(f"Successfully updated stop loss on exchange for {symbol} to {stop_price}")
                return True
            else:
                self.logger.error(f"Failed to update stop loss on exchange for {symbol}: {response.get('retMsg', 'Unknown error')}")
                return False

        except Exception as e:
            self.logger.error(f"Exception updating stop loss on exchange for {symbol}: {e}")
            return False

    def remove_trailing_stop(self, symbol: str):
        """Remove trailing stop for a symbol"""
        if symbol in self.active_trailing_stops:
            del self.active_trailing_stops[symbol]
            self.logger.info(f"Removed trailing stop for {symbol}")

# =====================================================================
# MAIN TRADING BOT CLASS
# =====================================================================

class SupertrendBot:
    def __init__(self, config: Config):
        self.config = config
        self.logger = setup_logger(config)

        # Initialize API connections
        self.session = HTTP(
            testnet=config.TESTNET,
            api_key=config.API_KEY,
            api_secret=config.API_SECRET
        )

        # Initialize managers
        self.precision_manager = PrecisionManager(self.session, self.logger)
        self.order_sizer = OrderSizingCalculator(self.precision_manager, self.logger)
        self.trailing_stop_manager = TrailingStopManager(self.session, self.precision_manager, self.logger)

        # Data storage
        self.market_data = pd.DataFrame()
        self.current_positions = {} # {symbol: position_data}
        self.open_orders = {} # {order_id: order_data}
        self.account_balance_usdt = 0.0
        self.start_balance_usdt = 0.0
        self.daily_loss_amount = 0.0

        # Strategy state
        self.current_signal = Signal.NEUTRAL
        self.position_active = False # True if we have an open position for the target symbol
        self.current_position_side = None # 'Buy' or 'Sell'
        self.current_position_entry_price = Decimal('0')
        self.current_position_size = Decimal('0')

        self.logger.info("Supertrend Trading Bot initialized.")
        self.logger.info(f"Mode: {'Testnet' if config.TESTNET else 'Mainnet'}")
        self.logger.info(f"Symbol: {config.SYMBOL}, Category: {config.CATEGORY.value}, Timeframe: {config.TIMEFRAME}")
        self.logger.info(f"Supertrend Params: Period={config.ST_PERIOD}, Multiplier={config.ST_MULTIPLIER}")

    # =====================================================================
    # DATA FETCHING METHODS
    # =====================================================================

    def fetch_klines(self, limit: int | None = None) -> pd.DataFrame:
        """Fetch historical kline data from Bybit"""
        try:
            fetch_limit = limit if limit else self.config.LOOKBACK_PERIODS

            response = self.session.get_kline(
                category=self.config.CATEGORY.value,
                symbol=self.config.SYMBOL,
                interval=self.config.TIMEFRAME,
                limit=fetch_limit
            )

            if response['retCode'] == 0:
                klines = response['result']['list']

                df = pd.DataFrame(klines, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
                ])

                # Convert types
                df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
                for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                    df[col] = df[col].astype(float)

                # Sort by timestamp (oldest first) and set index
                df = df.sort_values('timestamp')
                df.set_index('timestamp', inplace=True)

                self.logger.debug(f"Fetched {len(df)} klines for {self.config.SYMBOL}.")
                return df
            else:
                self.logger.error(f"Failed to fetch klines for {self.config.SYMBOL}: {response.get('retMsg', 'Unknown error')}")
                return pd.DataFrame()

        except Exception as e:
            self.logger.error(f"Exception fetching klines for {self.config.SYMBOL}: {e}")
            return pd.DataFrame()

    def get_ticker(self) -> dict | None:
        """Get current ticker data for the symbol"""
        try:
            response = self.session.get_tickers(
                category=self.config.CATEGORY.value,
                symbol=self.config.SYMBOL
            )

            if response['retCode'] == 0:
                if response['result']['list']:
                    return response['result']['list'][0]
                else:
                    self.logger.error(f"Ticker data not found for {self.config.SYMBOL}.")
                    return None
            else:
                self.logger.error(f"Failed to fetch ticker for {self.config.SYMBOL}: {response.get('retMsg', 'Unknown error')}")
                return None

        except Exception as e:
            self.logger.error(f"Exception fetching ticker for {self.config.SYMBOL}: {e}")
            return None

    # =====================================================================
    # TECHNICAL INDICATORS
    # =====================================================================

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Supertrend and ATR using pandas_ta"""
        if df.empty:
            return df

        try:
            # Calculate ATR
            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=self.config.ST_PERIOD)

            # Calculate Supertrend
            # pandas_ta's supertrend returns multiple columns: Supertrend, Supertrend_Direction,
            # Supertrend_UpperBand, Supertrend_LowerBand
            st = ta.supertrend(
                high=df['high'],
                low=df['low'],
                close=df['close'],
                length=self.config.ST_PERIOD,
                multiplier=self.config.ST_MULTIPLIER
            )

            # Rename columns for clarity and consistency
            df['supertrend'] = st[f'SUPERT_{self.config.ST_PERIOD}_{self.config.ST_MULTIPLIER}']
            df['supertrend_direction'] = st[f'SUPERTd_{self.config.ST_PERIOD}_{self.config.ST_MULTIPLIER}']
            df['supertrend_upper'] = st[f'SUPERTl_{self.config.ST_PERIOD}_{self.config.ST_MULTIPLIER}']
            df['supertrend_lower'] = st[f'SUPERTu_{self.config.ST_PERIOD}_{self.config.ST_MULTIPLIER}']

            # Fill NaNs in supertrend bands with close price for initial periods
            df['supertrend_upper'] = df['supertrend_upper'].fillna(df['close'])
            df['supertrend_lower'] = df['supertrend_lower'].fillna(df['close'])

            # Fill any remaining NaNs created by indicator calculations (e.g., at the
            # beginning of the series)
            # Use ffill for most indicators, then fill remaining NaNs with 0 or appropriate default
            df = df.ffill().fillna(0)
            df = df.fillna(0) # Final catch-all for any remaining NaNs

            self.logger.debug("Supertrend and ATR indicators calculated.")
            return df

        except Exception as e:
            self.logger.error(f"Error calculating indicators: {e}")
            return df

    # =====================================================================
    # STRATEGY LOGIC
    # =====================================================================

    def generate_signal(self, df: pd.DataFrame) -> Signal:
        """
        Generate trading signal based on Supertrend direction changes.
        """
        if df.empty or len(df) < 2:
            return Signal.NEUTRAL

        try:
            latest = df.iloc[-1]
            prev = df.iloc[-2]

            # Supertrend direction: 1 for uptrend, -1 for downtrend
            # Supertrend line: price of the Supertrend indicator

            # Buy Signal: Supertrend flips from downtrend to uptrend AND price is above
            # Supertrend line
            # or if Supertrend is already green and price is rising.
            if latest['supertrend_direction'] == 1:
                if prev['supertrend_direction'] == -1: # Trend flip from down to up
                    self.current_signal = Signal.STRONG_BUY
                elif latest['close'] > latest['supertrend']: # Already in uptrend and price is above line
                    self.current_signal = Signal.BUY
                else:
                    self.current_signal = Signal.NEUTRAL

            # Sell Signal: Supertrend flips from uptrend to downtrend AND price is below
            # Supertrend line
            # or if Supertrend is already red and price is falling.
            elif latest['supertrend_direction'] == -1:
                if prev['supertrend_direction'] == 1: # Trend flip from up to down
                    self.current_signal = Signal.STRONG_SELL
                elif latest['close'] < latest['supertrend']: # Already in downtrend and price is below line
                    self.current_signal = Signal.SELL
                else:
                    self.current_signal = Signal.NEUTRAL

            else: # Neutral or error in indicator calculation
                self.current_signal = Signal.NEUTRAL

            self.logger.debug(f"Signal generated: {self.current_signal.name}. Close={latest['close']:.2f}, ST={latest['supertrend']:.2f}, ST_Dir={latest['supertrend_direction']}")
            return self.current_signal

        except Exception as e:
            self.logger.error(f"Error generating signal: {e}")
            return Signal.NEUTRAL

    # =====================================================================
    # RISK MANAGEMENT
    # =====================================================================

    def calculate_position_size_usd(self, entry_price: float, stop_loss_price: float) -> Decimal | None:
        """Calculate position size in USD based on risk parameters."""
        try:
            # Get current account balance
            current_balance = self.get_account_balance_usdt()
            if current_balance <= 0:
                self.logger.warning("Account balance is zero or negative. Cannot calculate position size.")
                return None

            # Calculate risk amount for this trade
            risk_amount = Decimal(str(current_balance)) * Decimal(str(self.config.RISK_PER_TRADE_PCT / 100))

            # Calculate stop loss distance in price terms
            stop_distance_price = abs(Decimal(str(entry_price)) - Decimal(str(stop_loss_price)))

            # Calculate stop loss distance in percentage terms
            stop_distance_pct = (stop_distance_price / Decimal(str(entry_price))) if entry_price > 0 else Decimal('0')

            # Calculate the required position value to risk 'risk_amount'
            if stop_distance_pct > 0:
                position_value_needed = risk_amount / stop_distance_pct
            else:
                self.logger.warning(f"Stop loss distance is zero for {self.config.SYMBOL}. Cannot calculate size.")
                return None

            # Apply leverage to get the effective trading capital for this trade
            effective_capital = Decimal(str(current_balance)) * Decimal(str(self.config.LEVERAGE))

            # Ensure position value does not exceed effective capital or max position size
            position_value_needed = min(position_value_needed, Decimal(str(self.config.MAX_POSITION_SIZE_USD)), effective_capital)

            # Ensure minimum position value is met
            if position_value_needed < Decimal(str(self.config.MIN_POSITION_SIZE_USD)):
                self.logger.warning(f"Calculated position value {position_value_needed:.2f} is below minimum {self.config.MIN_POSITION_SIZE_USD}. Using minimum.")
                position_value_needed = Decimal(str(self.config.MIN_POSITION_SIZE_USD))

            # Convert position value to quantity using the symbol's specs
            specs = self.precision_manager.get_specs(self.config.SYMBOL)
            if not specs:
                self.logger.error(f"Cannot convert position value to quantity for {self.config.SYMBOL}: Specs not found.")
                return None

            # Calculate quantity based on category
            if specs.category == 'spot' or specs.category in ['linear', 'inverse']:
                quantity = position_value_needed / Decimal(str(entry_price))
            else: # option
                quantity = position_value_needed / Decimal(str(entry_price))

            # Round quantity to correct precision and validate against limits
            quantity = self.precision_manager.round_quantity(self.config.SYMBOL, quantity)

            # Final check against min/max quantity
            if quantity < specs.min_order_qty:
                self.logger.warning(f"Final quantity {quantity} for {self.config.SYMBOL} is below minimum {specs.min_order_qty}.")
                quantity = specs.min_order_qty
            elif quantity > specs.max_order_qty:
                self.logger.warning(f"Final quantity {quantity} for {self.config.SYMBOL} is above maximum {specs.max_order_qty}.")
                quantity = specs.max_order_qty

            # Ensure quantity is not zero after rounding and checks
            if quantity <= 0:
                self.logger.warning(f"Calculated quantity is zero or negative for {self.config.SYMBOL}. Cannot place order.")
                return None

            self.logger.info(f"Calculated position size: {quantity} {specs.base_currency} for {self.config.SYMBOL}.")
            return quantity

        except Exception as e:
            self.logger.error(f"Error calculating position size for {self.config.SYMBOL}: {e}")
            return None

    def check_daily_loss_limit(self) -> bool:
        """Check if the daily loss limit has been reached."""
        try:
            if self.start_balance_usdt <= 0: # If start balance is not set or invalid
                return True # Allow trading if balance is not properly initialized

            current_balance = self.get_account_balance_usdt()
            if current_balance <= 0: # If current balance is zero, we've lost everything
                return False

            loss_amount = self.start_balance_usdt - current_balance

            if loss_amount >= self.daily_loss_amount:
                self.logger.warning(f"Daily loss limit reached. Current loss: {loss_amount:.2f} USDT (Limit: {self.daily_loss_amount:.2f} USDT). Stopping trading.")
                return False

            return True

        except Exception as e:
            self.logger.error(f"Error checking daily loss limit: {e}")
            return False

    # =====================================================================
    # ORDER MANAGEMENT
    # =====================================================================

    def place_order(self, side: str, qty: Decimal, order_type: OrderType,
                   entry_price: float | None = None, stop_loss_price: float | None = None,
                   take_profit_price: float | None = None) -> dict | None:
        """Place an order on Bybit"""
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot place order for {self.config.SYMBOL}: Specs not found.")
            return None

        try:
            # Round quantity and prices according to symbol specifications
            rounded_qty = self.precision_manager.round_quantity(self.config.SYMBOL, qty)

            # Prepare order parameters
            params = {
                "category": specs.category,
                "symbol": self.config.SYMBOL,
                "side": side,
                "orderType": order_type.value,
                "qty": str(rounded_qty),
                "timeInForce": self.config.TIME_IN_FORCE,
                "reduceOnly": self.config.REDUCE_ONLY,
                "closeOnTrigger": False, # Usually False unless specific use case
                "positionIdx": 0 # Default to one-way mode
            }

            # Add price for limit orders
            if order_type == OrderType.LIMIT and entry_price is not None:
                rounded_price = self.precision_manager.round_price(self.config.SYMBOL, entry_price)
                params["price"] = str(rounded_price)

            # Add stop loss
            if stop_loss_price is not None:
                rounded_sl = self.precision_manager.round_price(self.config.SYMBOL, stop_loss_price)
                params["stopLoss"] = str(rounded_sl)

            # Add take profit
            if take_profit_price is not None:
                rounded_tp = self.precision_manager.round_price(self.config.SYMBOL, take_profit_price)
                params["takeProfit"] = str(rounded_tp)

            # Set TP/SL mode to 'Full' for orders that include TP/SL
            if stop_loss_price is not None or take_profit_price is not None:
                params["tpslMode"] = "Full"
                # Specify order type for TP/SL if needed (e.g., 'Market' for SL)
                if stop_loss_price is not None:
                    params["slOrderType"] = "Market" # Common practice for SL
                if take_profit_price is not None:
                    params["tpOrderType"] = "Limit" # Common practice for TP

            self.logger.debug(f"Placing order with params: {params}")

            # Place order
            response = self.session.place_order(**params)

            if response['retCode'] == 0:
                order_id = response['result']['orderId']
                self.logger.info(f"Order placed successfully: {side} {rounded_qty} {self.config.SYMBOL} ({order_type.value}), OrderID: {order_id}")
                if stop_loss_price:
                    self.logger.info(f"  Stop Loss set to: {params.get('stopLoss')}")
                if take_profit_price:
                    self.logger.info(f"  Take Profit set to: {params.get('takeProfit')}")

                # Store open order details if needed
                self.open_orders[order_id] = {
                    'symbol': self.config.SYMBOL,
                    'side': side,
                    'qty': rounded_qty,
                    'type': order_type.value,
                    'price': params.get('price'),
                    'stopLoss': params.get('stopLoss'),
                    'takeProfit': params.get('takeProfit'),
                    'status': 'New' # Initial status
                }
                return response['result']
            else:
                self.logger.error(f"Failed to place order for {self.config.SYMBOL}: {response.get('retMsg', 'Unknown error')}")
                return None

        except Exception as e:
            self.logger.error(f"Exception placing order for {self.config.SYMBOL}: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific order"""
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot cancel order for {self.config.SYMBOL}: Specs not found.")
            return False

        try:
            response = self.session.cancel_order(
                category=specs.category,
                symbol=self.config.SYMBOL,
                orderId=order_id
            )

            if response['retCode'] == 0:
                self.logger.info(f"Order {order_id} cancelled successfully for {self.config.SYMBOL}.")
                # Remove from open orders if it exists
                if order_id in self.open_orders:
                    del self.open_orders[order_id]
                return True
            else:
                self.logger.error(f"Failed to cancel order {order_id} for {self.config.SYMBOL}: {response.get('retMsg', 'Unknown error')}")
                return False

        except Exception as e:
            self.logger.error(f"Exception cancelling order {order_id} for {self.config.SYMBOL}: {e}")
            return False

    def cancel_all_orders(self) -> bool:
        """Cancel all open orders for the symbol"""
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot cancel all orders for {self.config.SYMBOL}: Specs not found.")
            return False

        try:
            response = self.session.cancel_all_orders(
                category=specs.category,
                symbol=self.config.SYMBOL
            )

            if response['retCode'] == 0:
                self.logger.info(f"All open orders cancelled for {self.config.SYMBOL}.")
                self.open_orders.clear() # Clear local tracking
                return True
            else:
                self.logger.error(f"Failed to cancel all orders for {self.config.SYMBOL}: {response.get('retMsg', 'Unknown error')}")
                return False

        except Exception as e:
            self.logger.error(f"Exception cancelling all orders for {self.config.SYMBOL}: {e}")
            return False

    # =====================================================================
    # POSITION MANAGEMENT
    # =====================================================================

    def get_positions(self):
        """Fetch and update current positions for the symbol"""
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot get positions for {self.config.SYMBOL}: Specs not found.")
            return

        try:
            response = self.session.get_positions(
                category=specs.category,
                symbol=self.config.SYMBOL
            )

            if response['retCode'] == 0:
                positions = response['result']['list']

                # Update internal position tracking
                self.current_positions = {}
                for pos in positions:
                    if Decimal(pos.get('size', '0')) > 0:
                        self.current_positions[pos['symbol']] = pos

                        # Update strategy state variables if this is our target symbol
                        if pos['symbol'] == self.config.SYMBOL:
                            self.position_active = True
                            self.current_position_side = pos['side']
                            self.current_position_entry_price = Decimal(pos['avgPrice'])
                            self.current_position_size = Decimal(pos['size'])

                            # Initialize trailing stop if we just entered a position
                            if self.config.TRAILING_STOP_PCT > 0 and self.config.ORDER_TYPE == OrderType.MARKET:
                                current_price = float(pos.get('markPrice', 0))
                                if current_price > 0 and self.config.TRAILING_STOP_PCT > 0:
                                    self.trailing_stop_manager.initialize_trailing_stop(
                                        symbol=self.config.SYMBOL,
                                        position_side=pos['side'],
                                        entry_price=float(pos['avgPrice']),
                                        current_price=current_price,
                                        trail_percent=self.config.TRAILING_STOP_PCT * 100, # Pass as percentage
                                        activation_percent=self.config.TRAILING_STOP_PCT * 100 # Simple activation for now
                                    )

                        break # Assume only one position for the target symbol

                if not self.current_positions.get(self.config.SYMBOL):
                    self.position_active = False
                    self.current_position_side = None
                    self.current_position_entry_price = Decimal('0')
                    self.current_position_size = Decimal('0')
                    self.trailing_stop_manager.remove_trailing_stop(self.config.SYMBOL) # Remove trailing stop if position closed

                self.logger.debug(f"Position status for {self.config.SYMBOL}: Active={self.position_active}, Side={self.current_position_side}, Size={self.current_position_size}")

            else:
                self.logger.error(f"Failed to get positions for {self.config.SYMBOL}: {response.get('retMsg', 'Unknown error')}")
                self.position_active = False # Assume no position if API fails

        except Exception as e:
            self.logger.error(f"Exception getting positions for {self.config.SYMBOL}: {e}")
            self.position_active = False

    def close_position(self) -> bool:
        """Close the current open position for the target symbol"""
        if not self.position_active or not self.current_position_side:
            self.logger.warning(f"No active position to close for {self.config.SYMBOL}.")
            return False

        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot close position for {self.config.SYMBOL}: Specs not found.")
            return False

        try:
            # Determine side to close
            close_side = "Sell" if self.current_position_side == "Buy" else "Buy"

            # Place a market order to close the position
            self.logger.info(f"Attempting to close {self.config.SYMBOL} position ({self.current_position_side} {self.current_position_size} contracts).")

            # For closing, we don't need specific SL/TP, just the market order to exit
            result = self.place_order(
                side=close_side,
                qty=self.current_position_size,
                order_type=OrderType.MARKET
            )

            if result:
                self.logger.info(f"Market order to close position for {self.config.SYMBOL} placed successfully.")
                # Update internal state immediately, actual position closure will be
                # confirmed by get_positions() next cycle
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
            self.logger.error(f"Exception closing position for {self.config.SYMBOL}: {e}")
            return False

    def update_stop_loss(self, stop_loss_price: float) -> bool:
        """Update the stop loss for the current position on the exchange."""
        if not self.position_active:
            self.logger.warning(f"No active position to update stop loss for {self.config.SYMBOL}.")
            return False

        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot update stop loss for {self.config.SYMBOL}: Specs not found.")
            return False

        try:
            rounded_sl = self.precision_manager.round_price(self.config.SYMBOL, stop_loss_price)

            response = self.session.set_trading_stop(
                category=specs.category,
                symbol=self.config.SYMBOL,
                stopLoss=str(rounded_sl),
                # tpOrderType='Limit', # Can also set TP here if needed
                slOrderType='Market' # Default is Market for SL
            )

            if response['retCode'] == 0:
                self.logger.info(f"Stop loss updated successfully on exchange for {self.config.SYMBOL} to {rounded_sl}")
                return True
            else:
                self.logger.error(f"Failed to update stop loss on exchange for {self.config.SYMBOL}: {response.get('retMsg', 'Unknown error')}")
                return False

        except Exception as e:
            self.logger.error(f"Exception updating stop loss on exchange for {self.config.SYMBOL}: {e}")
            return False

    # =====================================================================
    # ACCOUNT MANAGEMENT
    # =====================================================================

    def get_account_balance_usdt(self) -> float:
        """Get current account balance in USDT"""
        try:
            account_type = "UNIFIED" if self.config.CATEGORY != Category.SPOT else "SPOT"
            response = self.session.get_wallet_balance(accountType=account_type)

            if response['retCode'] == 0:
                # Find USDT balance from the list of coins
                for coin_data in response['result']['list']:
                    if coin_data['coin'] == 'USDT':
                        balance = float(coin_data['walletBalance'])
                        self.account_balance_usdt = balance
                        return balance

                self.logger.error(f"USDT balance not found in account response for {account_type}.")
                return 0.0
            else:
                self.logger.error(f"Failed to get account balance: {response.get('retMsg', 'Unknown error')}")
                return 0.0

        except Exception as e:
            self.logger.error(f"Exception getting account balance: {e}")
            return 0.0

    def set_leverage(self) -> bool:
        """Set leverage for the trading symbol"""
        if self.config.CATEGORY == Category.SPOT:
            self.logger.info("Spot trading does not use leverage. Skipping leverage setting.")
            return True # Spot doesn't use leverage

        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot set leverage for {self.config.SYMBOL}: Specs not found.")
            return False

        try:
            # Ensure leverage is within allowed limits
            leverage_to_set = Decimal(str(self.config.LEVERAGE))
            max_leverage = specs.max_leverage
            min_leverage = specs.min_leverage

            if leverage_to_set > max_leverage:
                self.logger.warning(f"Requested leverage {leverage_to_set} exceeds max {max_leverage} for {self.config.SYMBOL}. Setting to max.")
                leverage_to_set = max_leverage
            if leverage_to_set < min_leverage:
                self.logger.warning(f"Requested leverage {leverage_to_set} is below min {min_leverage} for {self.config.SYMBOL}. Setting to min.")
                leverage_to_set = min_leverage

            # Adjust leverage if it's not on a valid step
            leverage_step = specs.leverage_step
            if leverage_step > 0:
                leverage_to_set = (leverage_to_set / leverage_step).quantize(Decimal('1'), rounding=ROUND_DOWN) * leverage_step

            response = self.session.set_leverage(
                category=specs.category,
                symbol=self.config.SYMBOL,
                buyLeverage=str(leverage_to_set),
                sellLeverage=str(leverage_to_set)
            )

            if response['retCode'] == 0:
                self.logger.info(f"Leverage set successfully to {leverage_to_set}x for {self.config.SYMBOL}.")
                return True
            else:
                self.logger.error(f"Failed to set leverage for {self.config.SYMBOL}: {response.get('retMsg', 'Unknown error')}")
                return False

        except Exception as e:
            self.logger.error(f"Exception setting leverage for {self.config.SYMBOL}: {e}")
            return False

    # =====================================================================
    # MAIN EXECUTION LOOP
    # =====================================================================

    def execute_trade_based_on_signal(self, signal: Signal):
        """Execute trades based on the generated signal and current position state."""
        specs = self.precision_manager.get_specs(self.config.SYMBOL)
        if not specs:
            self.logger.error(f"Cannot execute trade for {self.config.SYMBOL}: Specs not found.")
            return

        try:
            # Check if we should trade at all (daily loss limit)
            if not self.check_daily_loss_limit():
                self.logger.warning("Daily loss limit reached. Skipping trade execution.")
                return

            # Get current market data
            ticker = self.get_ticker()
            if not ticker:
                self.logger.warning("Could not get ticker data. Skipping trade execution.")
                return

            current_price = float(ticker['lastPrice'])
            current_price_decimal = Decimal(str(current_price))

            # --- Handle OPENING NEW POSITIONS ---
            # If we are NOT in a position and receive a BUY signal
            if not self.position_active and signal in [Signal.BUY, Signal.STRONG_BUY]:
                self.logger.info("Received BUY signal. Attempting to open position.")

                # Calculate stop loss price
                stop_loss_price = current_price_decimal * (Decimal('1') - Decimal(str(self.config.STOP_LOSS_PCT)))
                # Calculate take profit price
                take_profit_price = current_price_decimal * (Decimal('1') + Decimal(str(self.config.TAKE_PROFIT_PCT)))

                # Calculate position size in base currency units
                position_qty = self.calculate_position_size_usd(
                    entry_price=current_price,
                    stop_loss_price=float(stop_loss_price)
                )

                if position_qty is not None and position_qty > 0:
                    # Place the order
                    order_result = self.place_order(
                        side="Buy",
                        qty=position_qty,
                        order_type=self.config.ORDER_TYPE,
                        entry_price=current_price if self.config.ORDER_TYPE == OrderType.LIMIT else None,
                        stop_loss_price=float(stop_loss_price),
                        take_profit_price=float(take_profit_price)
                    )

                    if order_result:
                        # If order placed successfully, update internal state
                        # Note: Actual position confirmation comes from get_positions() in the
                        # next loop
                        self.position_active = True # Tentatively set to true
                        self.current_position_side = "Buy"
                        self.current_position_entry_price = current_price_decimal
                        self.current_position_size = position_qty
                        self.logger.info("BUY order placed. Waiting for position confirmation.")
                    else:
                        self.logger.error("Failed to place BUY order.")
                else:
                    self.logger.warning("Could not calculate valid position size for BUY signal.")

            # If we are NOT in a position and receive a SELL signal
            elif not self.position_active and signal in [Signal.SELL, Signal.STRONG_SELL]:
                self.logger.info("Received SELL signal. Attempting to open position.")

                # Calculate stop loss price
                stop_loss_price = current_price_decimal * (Decimal('1') + Decimal(str(self.config.STOP_LOSS_PCT)))
                # Calculate take profit price
                take_profit_price = current_price_decimal * (Decimal('1') - Decimal(str(self.config.TAKE_PROFIT_PCT)))

                # Calculate position size in base currency units
                position_qty = self.calculate_position_size_usd(
                    entry_price=current_price,
                    stop_loss_price=float(stop_loss_price)
                )

                if position_qty is not None and position_qty > 0:
                    # Place the order
                    order_result = self.place_order(
                        side="Sell",
                        qty=position_qty,
                        order_type=self.config.ORDER_TYPE,
                        entry_price=current_price if self.config.ORDER_TYPE == OrderType.LIMIT else None,
                        stop_loss_price=float(stop_loss_price),
                        take_profit_price=float(take_profit_price)
                    )

                    if order_result:
                        # If order placed successfully, update internal state
                        self.position_active = True # Tentatively set to true
                        self.current_position_side = "Sell"
                        self.current_position_entry_price = current_price_decimal
                        self.current_position_size = position_qty
                        self.logger.info("SELL order placed. Waiting for position confirmation.")
                    else:
                        self.logger.error("Failed to place SELL order.")
                else:
                    self.logger.warning("Could not calculate valid position size for SELL signal.")

            # --- Handle MANAGING EXISTING POSITIONS ---
            # If we ARE in a position and the signal flips against us
            elif self.position_active:
                # If we have a BUY position and signal is SELL/STRONG_SELL
                if self.current_position_side == "Buy" and signal in [Signal.SELL, Signal.STRONG_SELL]:
                    self.logger.info("Signal flipped to SELL/STRONG_SELL while in BUY position. Closing position.")
                    self.close_position()

                # If we have a SELL position and signal is BUY/STRONG_BUY
                elif self.current_position_side == "Sell" and signal in [Signal.BUY, Signal.STRONG_BUY]:
                    self.logger.info("Signal flipped to BUY/STRONG_BUY while in SELL position. Closing position.")
                    self.close_position()

                # --- Handle Trailing Stop Loss ---
                elif self.config.TRAILING_STOP_PCT > 0:
                    # Update trailing stop based on current price and strategy state
                    # Trailing stop is managed by the TrailingStopManager
                    self.trailing_stop_manager.update_trailing_stop(
                        symbol=self.config.SYMBOL,
                        current_price=current_price,
                        update_exchange=True # Attempt to update on exchange if logic dictates
                    )

        except Exception as e:
            self.logger.error(f"Error during trade execution for {self.config.SYMBOL}: {e}")

    def run_strategy(self):
        """Main trading loop"""
        try:
            # Initial setup
            if not self.set_leverage():
                self.logger.critical("Failed to set leverage. Bot cannot proceed.")
                return

            self.start_balance_usdt = self.get_account_balance_usdt()
            if self.start_balance_usdt <= 0:
                self.logger.critical("Failed to get initial account balance. Bot cannot proceed.")
                return

            self.daily_loss_amount = self.start_balance_usdt * (self.config.MAX_DAILY_LOSS_PCT / 100)
            self.logger.info(f"Starting Balance: {self.start_balance_usdt:.2f} USDT. Daily Loss Limit: {self.daily_loss_amount:.2f} USDT.")

            # Fetch initial position status
            self.get_positions()

            # Main loop
            while True:
                try:
                    # Fetch market data
                    self.market_data = self.fetch_klines()
                    if self.market_data.empty:
                        self.logger.warning("No market data fetched. Waiting...")
                        time.sleep(self.config.LOOP_INTERVAL_SEC)
                        continue

                    # Calculate indicators
                    self.market_data = self.calculate_indicators(self.market_data)

                    # Generate trading signal
                    current_signal = self.generate_signal(self.market_data)

                    # Update position status (important for managing existing trades)
                    self.get_positions() # Refresh position status before executing trades

                    # Execute trade based on signal and current position state
                    self.execute_trade_based_on_signal(current_signal)

                    # Log current status
                    current_balance = self.get_account_balance_usdt()
                    pnl = current_balance - self.start_balance_usdt
                    pnl_pct = (pnl / self.start_balance_usdt * 100) if self.start_balance_usdt > 0 else 0

                    self.logger.info(f"Loop Iteration: Signal={current_signal.name}, Balance={current_balance:.2f} USDT, PnL={pnl:.2f} ({pnl_pct:.2f}%), Position Active={self.position_active}, Side={self.current_position_side}")

                    # Wait for the next interval
                    time.sleep(self.config.LOOP_INTERVAL_SEC)

                except KeyboardInterrupt:
                    self.logger.info("Strategy execution interrupted by user.")
                    break
                except Exception as e:
                    self.logger.error(f"Error in main strategy loop: {e}")
                    # Wait before retrying to avoid rapid error loops
                    time.sleep(self.config.LOOP_INTERVAL_SEC)

        except Exception as e:
            self.logger.critical(f"Critical error in run_strategy: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Perform cleanup actions before exiting"""
        self.logger.info("Starting bot cleanup...")
        try:
            # Cancel all open orders
            self.cancel_all_orders()

            # Close any open positions if the bot is stopping
            # (Optional: depending on desired behavior when stopping)
            # if self.position_active:
            #     self.logger.info("Closing open position during cleanup.")
            #     self.close_position()

            # Final summary
            final_balance = self.get_account_balance_usdt()
            total_pnl = final_balance - self.start_balance_usdt
            total_pnl_pct = (total_pnl / self.start_balance_usdt * 100) if self.start_balance_usdt > 0 else 0

            self.logger.info("=" * 60)
            self.logger.info("Supertrend Trading Bot Stopped.")
            self.logger.info(f"Final Balance: {final_balance:.2f} USDT")
            self.logger.info(f"Total PnL: {total_pnl:.2f} USDT ({total_pnl_pct:.2f}%)")
            self.logger.info("=" * 60)

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

# =====================================================================
# MAIN ENTRY POINT
# =====================================================================

def main():
    """Main function to initialize and run the bot."""

    # --- Load Configuration ---
    config = Config()

    # Basic validation for API keys
    if config.API_KEY == "YOUR_BYBIT_API_KEY" or config.API_SECRET == "YOUR_BYBIT_API_SECRET":
        print("\nERROR: Bybit API Key or Secret not configured.")
        print("Please set BYBIT_API_KEY and BYBIT_API_SECRET environment variables,")
        print("or update the Config class in config.py directly.")
        sys.exit(1)

    # --- Initialize and Run Bot ---
    bot = SupertrendBot(config)

    try:
        bot.run_strategy()
    except Exception as e:
        print(f"\nFATAL ERROR: An unhandled exception occurred: {e}")
        # Log the critical error before exiting
        bot.logger.critical(f"FATAL ERROR: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
