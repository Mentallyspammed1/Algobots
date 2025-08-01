# utils.py
import logging
import os
import datetime as dt # Use dt alias for datetime module
from decimal import Decimal, getcontext, InvalidOperation
from typing import Any, Dict, Optional, Type

from colorama import Fore, Style, init

class OrderBook:
    def __init__(self, logger):
        self.bids = {}
        self.asks = {}
        self.last_seq = 0
        self.logger = logger

    def handle_snapshot(self, data):
        """
        Initializes the order book from a snapshot message.
        """
        self.bids = {Decimal(price): Decimal(qty) for price, qty in data.get('b', []) if Decimal(qty) > 0}
        self.asks = {Decimal(price): Decimal(qty) for price, qty in data.get('a', []) if Decimal(qty) > 0}
        self.last_seq = data.get('seq', 0)
        self.logger.debug(f"Order book snapshot initialized with seq: {self.last_seq}")

    def apply_delta(self, data):
        """
        Applies incremental updates (deltas) to the order book.
        """
        update_seq = data.get('seq')
        if update_seq is None or update_seq <= self.last_seq:
            self.logger.debug(f"Stale or out-of-order order book update (current seq: {update_seq}, last seq: {self.last_seq}). Skipping.")
            return

        for price_str, qty_str in data.get('b', []):
            try:
                price = Decimal(price_str)
                qty = Decimal(qty_str)
                if qty == Decimal('0'):
                    if price in self.bids:
                        del self.bids[price]
                else:
                    self.bids[price] = qty
            except InvalidOperation:
                self.logger.warning(f"Invalid decimal value in bid: {price_str}, {qty_str}")

        for price_str, qty_str in data.get('a', []):
            try:
                price = Decimal(price_str)
                qty = Decimal(qty_str)
                if qty == Decimal('0'):
                    if price in self.asks:
                        del self.asks[price]
                else:
                    self.asks[price] = qty
            except InvalidOperation:
                self.logger.warning(f"Invalid decimal value in ask: {price_str}, {qty_str}")

        self.last_seq = update_seq

    def get_imbalance(self) -> Decimal:
        bid_volume = sum(price * qty for price, qty in self.bids.items())
        ask_volume = sum(price * qty for price, qty in self.asks.items())
        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return Decimal('0')
        return (bid_volume - ask_volume) / total_volume

# --- Module-level logger ---
_module_logger = logging.getLogger(__name__)

# --- Timezone Handling ---
_ActualZoneInfo: Type[dt.tzinfo] # This will hold the class to use for timezones (zoneinfo.ZoneInfo or FallbackZoneInfo)

class FallbackZoneInfo(dt.tzinfo):
    """
    A basic, UTC-only fallback implementation for timezone handling,
    mimicking zoneinfo.ZoneInfo for the 'UTC' timezone.
    It is used if the 'zoneinfo' module (Python 3.9+) is not available.
    This class only truly supports 'UTC'; other timezone keys will default to UTC.
    """
    _offset: dt.timedelta
    _name: str

    def __init__(self, key: str):
        super().__init__() # Call tzinfo's __init__

        # For this fallback, we only truly support "UTC".
        # key is expected to be a string as per type hint.
        if key.upper() == 'UTC':
            self._offset = dt.timedelta(0)
            self._name = "UTC"
        else:
            _module_logger.warning(
                f"FallbackZoneInfo initialized with key '{key}' which is not 'UTC'. "
                f"This fallback only supports UTC. Effective timezone will be UTC."
            )
            self._offset = dt.timedelta(0)
            self._name = "UTC" # Effective name is UTC

    def fromutc(self, dt_obj: dt.datetime) -> dt.datetime:
        """
        Called by datetime.astimezone() after adjusting dt_obj to UTC.
        Since this class represents UTC, no further adjustment is needed.
        dt_obj.tzinfo is self when this method is called.
        """
        if not isinstance(dt_obj, dt.datetime):
            raise TypeError("fromutc() requires a datetime argument")
        # dt_obj is already in UTC wall time, with tzinfo=self.
        return dt_obj.replace(tzinfo=self) # Ensure tzinfo is correctly self

    def utcoffset(self, dt_obj: Optional[dt.datetime]) -> dt.timedelta:
        """Returns the UTC offset for this timezone."""
        # dt_obj can be None as per tzinfo.utcoffset signature
        return self._offset

    def dst(self, dt_obj: Optional[dt.datetime]) -> Optional[dt.timedelta]:
        """Returns the Daylight Saving Time offset (always 0 for UTC)."""
        # dt_obj can be None as per tzinfo.dst signature
        return dt.timedelta(0)

    def tzname(self, dt_obj: Optional[dt.datetime]) -> Optional[str]:
        """Returns the name of the timezone."""
        # dt_obj can be None as per tzinfo.tzname signature
        return self._name

    def __repr__(self) -> str:
        return f"<FallbackZoneInfo name='{self._name}'>"

    def __str__(self) -> str:
        return self._name

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FallbackZoneInfo):
            return NotImplemented
        # All FallbackZoneInfo instances are effectively UTC and thus equal
        # if they have the same _name and _offset (which they will, by construction).
        return self._name == other._name and self._offset == other._offset

    def __hash__(self) -> int:
        # All FallbackZoneInfo instances hash the same if _name is always "UTC".
        return hash((self._name, self._offset))

try:
    from zoneinfo import ZoneInfo as _ZoneInfo_FromModule # Import with a temporary name (Python 3.9+)
    _ActualZoneInfo = _ZoneInfo_FromModule # Assign to the variable with the correct type hint
except ImportError:
    _module_logger.warning(
        "Module 'zoneinfo' not found (requires Python 3.9+ and possibly 'tzdata' package). "
        "Using a basic UTC-only fallback for timezone handling. "
        "For full timezone support on older Python, consider installing 'pytz'."
    )
    _ActualZoneInfo = FallbackZoneInfo # FallbackZoneInfo is Type[dt.tzinfo]

# Global timezone object, lazily initialized
TIMEZONE: Optional[dt.tzinfo] = None

# --- Decimal Context ---
getcontext().prec = 38 # Set precision for Decimal calculations

# --- Colorama Initialization ---
init(autoreset=True) # Initialize Colorama for cross-platform colored output

# --- Configuration Constants ---
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs"
DEFAULT_TIMEZONE = "America/Chicago" # Default if TIMEZONE env var is not set

# --- API and Bot Behavior Constants ---
MAX_API_RETRIES = 3
RETRY_DELAY_SECONDS = 5
RETRY_ERROR_CODES = (429, 500, 502, 503, 504) # Tuple for immutability
RETRY_HTTP_STATUS_CODES = (408, 429, 500, 502, 503, 504) # For HTTP specific retries
LOOP_DELAY_SECONDS = 10
POSITION_CONFIRM_DELAY_SECONDS = 8

# --- Trading Constants ---
VALID_INTERVALS = ["1", "3", "5", "15", "30", "60", "120", "240", "D", "W", "M"]
CCXT_INTERVAL_MAP = {
    "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
    "60": "1h", "120": "2h", "240": "4h", "D": "1d", "W": "1w", "M": "1M"
}
FIB_LEVELS = [
    Decimal("0.0"), Decimal("0.236"), Decimal("0.382"), Decimal("0.5"),
    Decimal("0.618"), Decimal("0.786"), Decimal("1.0")
]

# --- Indicator Default Periods ---
DEFAULT_INDICATOR_PERIODS = {
    "atr_period": 14, "cci_window": 20, "williams_r_window": 14, "mfi_window": 14,
    "stoch_rsi_window": 14, "stoch_rsi_rsi_window": 12, "stoch_rsi_k": 3, "stoch_rsi_d": 3,
    "rsi_period": 14, "bollinger_bands_period": 20, "bollinger_bands_std_dev": 2.0,
    "sma_10_window": 10, "ema_short_period": 9, "ema_long_period": 21,
    "momentum_period": 7, "volume_ma_period": 15, "fibonacci_window": 50,
    "psar_af": 0.02, "psar_max_af": 0.2,
}

# --- Colorama Color Constants ---
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.LIGHTBLUE_EX
NEON_PURPLE = Fore.LIGHTMAGENTA_EX
NEON_YELLOW = Fore.LIGHTYELLOW_EX
NEON_RED = Fore.LIGHTRED_EX
NEON_CYAN = Fore.LIGHTCYAN_EX
RESET_ALL_STYLE = Style.RESET_ALL


def set_timezone(tz_str: str) -> None:
    """
    Sets the global timezone for the application.

    If the specified timezone string is invalid or 'zoneinfo' is unavailable
    for non-UTC timezones, it defaults to UTC.

    Args:
        tz_str: The timezone string (e.g., "America/Chicago", "UTC").
    """
    global TIMEZONE
    try:
        TIMEZONE = _ActualZoneInfo(tz_str)
        _module_logger.info(f"Timezone successfully set to: {str(TIMEZONE)}")
        # Warn if fallback is active (i.e., _ActualZoneInfo is FallbackZoneInfo)
        # and a non-UTC zone was requested, as FallbackZoneInfo will default to UTC.
        if _ActualZoneInfo is FallbackZoneInfo and tz_str.upper() != 'UTC':
            _module_logger.warning(
                f"'zoneinfo' module is not found and timezone '{tz_str}' was requested. "
                f"Effective timezone is UTC due to FallbackZoneInfo limitations."
            )
    except Exception as tz_err:
        # This handles errors from _ActualZoneInfo(tz_str) constructor,
        # e.g., zoneinfo.ZoneInfoNotFoundError if tz_str is invalid.
        _module_logger.warning(
            f"Could not load timezone '{tz_str}'. Defaulting to UTC. Error: {tz_err}",
            exc_info=True # Log full traceback for the timezone loading error
        )
        # Ensure TIMEZONE is always set, defaulting to UTC
        if _ActualZoneInfo is not FallbackZoneInfo: # _ActualZoneInfo is zoneinfo.ZoneInfo
            try:
                TIMEZONE = _ActualZoneInfo("UTC") # Try real zoneinfo.ZoneInfo("UTC")
            except Exception as utc_load_err: # Should be extremely rare
                _module_logger.error(
                    f"Critical: Could not load 'UTC' with available 'zoneinfo' module: {utc_load_err}. "
                    "Forcing FallbackZoneInfo for UTC.",
                    exc_info=True
                )
                TIMEZONE = FallbackZoneInfo("UTC") # Ultimate fallback
        else: # zoneinfo not available, _ActualZoneInfo is FallbackZoneInfo
            # FallbackZoneInfo("UTC") is robust and should not fail.
            TIMEZONE = _ActualZoneInfo("UTC") # This is FallbackZoneInfo("UTC")

def get_timezone() -> dt.tzinfo:
    """
    Retrieves the global timezone object.

    Initializes it from the TIMEZONE environment variable or `DEFAULT_TIMEZONE`
    if not already set.

    Returns:
        A datetime.tzinfo object representing the configured timezone.
    """
    global TIMEZONE
    if TIMEZONE is None:
        env_tz = os.getenv("TIMEZONE")
        chosen_tz_str: str

        if env_tz:
            _module_logger.info(f"TIMEZONE environment variable found: '{env_tz}'. Attempting to use it.")
            chosen_tz_str = env_tz
        else:
            _module_logger.info(
                f"TIMEZONE environment variable not set. "
                f"Using default timezone: '{DEFAULT_TIMEZONE}'."
            )
            chosen_tz_str = DEFAULT_TIMEZONE

        set_timezone(chosen_tz_str) # This will initialize TIMEZONE

    # At this point, TIMEZONE must be set by set_timezone.
    # An assert helps catch unexpected None states during development.
    assert TIMEZONE is not None, "TIMEZONE should have been initialized by set_timezone."
    return TIMEZONE

class SensitiveFormatter(logging.Formatter):
    """
    Custom logging formatter that redacts sensitive information (API key and secret)
    from log messages.
    """
    # Store sensitive data as class attributes.
    # This assumes one set of credentials for the application instance using this formatter.
    _api_key: Optional[str] = None
    _api_secret: Optional[str] = None

    @classmethod
    def set_sensitive_data(cls, api_key: Optional[str], api_secret: Optional[str]) -> None:
        """Sets the API key and secret to be redacted."""
        cls._api_key = api_key
        cls._api_secret = api_secret

    def format(self, record: logging.LogRecord) -> str:
        """Formats the log record, redacting sensitive data."""
        # Get the formatted message from the base class.
        msg = super().format(record)

        # Redact API key if it's set and present in the message.
        # Ensure _api_key is not None and not an empty string before replacing.
        if SensitiveFormatter._api_key:
            msg = msg.replace(SensitiveFormatter._api_key, "***API_KEY***")

        # Redact API secret if it's set and present in the message.
        # Ensure _api_secret is not None and not an empty string.
        if SensitiveFormatter._api_secret:
            msg = msg.replace(SensitiveFormatter._api_secret, "***API_SECRET***")
        return msg

    @classmethod
    def from_environment_variables(cls) -> 'SensitiveFormatter':
        """
        Creates a SensitiveFormatter instance from environment variables.

        Returns:
            A SensitiveFormatter instance.
        """
        api_key = os.environ.get('API_KEY')
        api_secret = os.environ.get('API_SECRET')

        if not api_key or not api_secret:
            raise ValueError("API key or secret is missing")

        return cls(api_key, api_secret)

def get_price_precision(market_info: Dict[str, Any], logger: logging.Logger) -> int:
    """
    Determines the number of decimal places for price formatting for a given market.

    It tries to extract this information from `market_info['precision']['price']`
    (interpreting int as places, float/str as tick size) or
    `market_info['limits']['price']['min']` as a fallback heuristic.

    Args:
        market_info: A dictionary containing market data from CCXT.
        logger: Logger instance for logging warnings or debug information.

    Returns:
        The determined price precision (number of decimal places). Defaults to 4.

    Raises:
        ValueError: If the market_info dictionary is missing or invalid.
    """
    if not market_info:
        raise ValueError("Market info dictionary is missing or invalid")
    symbol = market_info.get('symbol', 'UNKNOWN_SYMBOL')
    default_precision = 4 # Define default early for clarity

    # 1. Try 'precision'.'price'
    precision_data = market_info.get('precision', {})
    price_precision_value = precision_data.get('price')

    if price_precision_value is not None:
        if isinstance(price_precision_value, int):
            if price_precision_value >= 0:
                logger.debug(f"Using integer price precision for {symbol}: {price_precision_value}")
                return price_precision_value
            else:
                logger.warning(
                    f"Invalid negative integer price precision for {symbol}: {price_precision_value}. "
                    "Proceeding to next check."
                )

        elif isinstance(price_precision_value, (str, float)):
            try:
                # Assume this value represents the tick size
                tick_size = Decimal(str(price_precision_value))
                if tick_size > Decimal('0'):
                    # Precision is the number of decimal places in the tick size
                    # .normalize() removes trailing zeros, .as_tuple().exponent gives num decimal places (negative)
                    precision = abs(tick_size.normalize().as_tuple().exponent)
                    logger.debug(f"Derived price precision for {symbol} from tick size {tick_size}: {precision}")
                    return precision
                else: # tick_size is zero or negative
                    logger.warning(
                        f"Invalid non-positive tick size '{price_precision_value}' from market_info.precision.price "
                        f"for {symbol}. Proceeding to next check."
                    )
            except (ValueError, TypeError, InvalidOperation) as e:
                logger.warning(
                    f"Could not parse market_info.precision.price '{price_precision_value}' "
                    f"as Decimal for {symbol}: {e}. Proceeding to next check."
                )
        else:
            logger.warning(
                f"Unsupported type for market_info.precision.price for {symbol}: {type(price_precision_value)}. "
                "Proceeding to next check."
            )

    # 2. Try 'limits'.'price'.'min' as a heuristic for tick size to derive precision
    price_limits = market_info.get('limits', {}).get('price', {})
    min_price_str = price_limits.get('min')

    if min_price_str is not None:
        try:
            min_price_tick = Decimal(str(min_price_str))
            if min_price_tick > Decimal('0'):
                # If min_price is positive, assume it can represent the tick size or a value
                # from which precision can be derived.
                precision = abs(min_price_tick.normalize().as_tuple().exponent)
                logger.debug(
                    f"Derived price precision for {symbol} from min_price_limit {min_price_tick} "
                    f"(parsed from '{min_price_str}'): {precision}"
                )
                return precision
            # else: min_price_tick is zero or negative, not useful for precision.
        except (ValueError, TypeError, InvalidOperation) as e:
            logger.warning(
                f"Could not parse market_info.limits.price.min '{min_price_str}' "
                f"as Decimal for {symbol}: {e}. Falling back to default."
            )

    # 3. Default precision
    logger.warning(
        f"Could not determine price precision for {symbol} from market_info. "
        f"Using default: {default_precision}."
    )
    return default_precision

def get_min_tick_size(market_info: Dict[str, Any], logger: logging.Logger) -> Decimal:
    """
    Determines the minimum tick size (price increment) for a given market.

    It tries to extract this from `market_info['precision']['price']`
    (interpreting float/str as tick size, int as precision for 10^-n) or
    `market_info['limits']['price']['min']`. Falls back to a value derived
    from `get_price_precision`.

    Args:
        market_info: A dictionary containing market data from CCXT.
        logger: Logger instance for logging warnings or debug information.

    Returns:
        The minimum tick size as a Decimal.
    """
    symbol = market_info.get('symbol', 'UNKNOWN_SYMBOL')

    # 1. Try 'precision'.'price'
    precision_data = market_info.get('precision', {})
    price_precision_value = precision_data.get('price')

    if price_precision_value is not None:
        if isinstance(price_precision_value, (str, float)): # Typically, this is the tick size itself
            try:
                tick_size = Decimal(str(price_precision_value))
                if tick_size > Decimal('0'):
                    logger.debug(f"Using tick size from precision.price for {symbol}: {tick_size}")
                    return tick_size
                else: # tick_size is zero or negative
                    logger.warning(
                        f"Invalid non-positive value '{price_precision_value}' from market_info.precision.price "
                        f"for {symbol}. Proceeding to next check."
                    )
            except (ValueError, TypeError, InvalidOperation) as e:
                logger.warning(
                    f"Could not parse market_info.precision.price '{price_precision_value}' "
                    f"as Decimal for {symbol}: {e}. Proceeding to next check."
                )

        elif isinstance(price_precision_value, int): # Often number of decimal places
            if price_precision_value >= 0:
                # If 'precision'.'price' is an int, it's often number of decimal places for price
                tick_size = Decimal('1e-' + str(price_precision_value))
                logger.debug(f"Calculated tick size from integer precision for {symbol}: {tick_size}")
                return tick_size
            else:
                logger.warning(
                    f"Invalid negative integer for precision.price for {symbol}: {price_precision_value}. "
                    "Proceeding to next check."
                )
        else:
            logger.warning(
                f"Unsupported type for market_info.precision.price for {symbol}: {type(price_precision_value)}. "
                "Proceeding to next check."
            )

    # 2. Try 'limits'.'price'.'min'
    # This is sometimes the tick size, or at least related.
    price_limits = market_info.get('limits', {}).get('price', {})
    min_price_str = price_limits.get('min')

    if min_price_str is not None:
        try:
            min_tick_from_limit = Decimal(str(min_price_str))
            # If min_price from limits is positive, it might be the tick size.
            if min_tick_from_limit > Decimal('0'):
                logger.debug(
                    f"Using min_price from limits ('{min_price_str}') as tick size for {symbol}: {min_tick_from_limit}"
                )
                return min_tick_from_limit
            # else: min_tick_from_limit is zero or negative, not a valid tick size.
        except (ValueError, TypeError, InvalidOperation) as e:
            logger.warning(
                f"Could not parse market_info.limits.price.min '{min_price_str}' "
                f"as Decimal for {symbol}: {e}. Falling back."
            )

    # 3. Fallback: derive tick size from calculated price precision
    # This re-uses get_price_precision, which has its own logging for defaults.
    price_prec_places = get_price_precision(market_info, logger) # This call might log a warning if it defaults
    fallback_tick_size = Decimal('1e-' + str(price_prec_places))
    logger.warning(
        f"Could not determine specific min_tick_size for {symbol} from market_info. "
        f"Using fallback based on derived price precision ({price_prec_places} places): {fallback_tick_size}"
    )
    return fallback_tick_size

def _format_signal(signal_payload: Any, *, success: bool = True, detail: Optional[str] = None) -> str:
    """
    Formats a trading signal or related message for display, potentially with color.
    This is a placeholder to resolve the import error and can be customized
    based on the actual structure and requirements for signal formatting.

    Args:
        signal_payload: The content of the signal (e.g., "BUY", "SELL", a dictionary).
        success: If True, formats as a success/neutral message. If False, as an error/warning.
        detail: Optional additional detail string.

    Returns:
        A formatted string representation of the signal.
    """
    base_color = NEON_GREEN if success else NEON_RED
    prefix = "Signal" if success else "Signal Alert"

    signal_str = str(signal_payload)
    # Basic truncation for very long signal payloads to keep logs readable
    if len(signal_str) > 100:
        signal_str = signal_str[:97] + "..."

    message = f"{base_color}{prefix}: {signal_str}{RESET_ALL_STYLE}"
    if detail:
        message += f" ({base_color}{detail}{RESET_ALL_STYLE})" # Color detail similarly

    return message


from decimal import ROUND_HALF_UP

def round_decimal(value: float, precision: int) -> Decimal:
    """
    Rounds a float value to a specified decimal precision using Decimal for accuracy.

    Args:
        value (float): The float value to round.
        precision (int): The number of decimal places to round to.

    Returns:
        Decimal: The rounded value as a Decimal object.
    """
    if not isinstance(value, (float, int)):
        raise TypeError("Value must be a float or integer.")
    if not isinstance(precision, int) or precision < 0:
        raise ValueError("Precision must be a non-negative integer.")

    # Create a Decimal object for the value
    decimal_value = Decimal(str(value))

    # Create a rounding context based on the desired precision
    # e.g., '0.001' for 3 decimal places
    rounding_context = Decimal(10) ** -precision

    # Round using ROUND_HALF_UP (standard rounding)
    return decimal_value.quantize(rounding_context, rounding=ROUND_HALF_UP)

def calculate_order_quantity(
    usdt_amount: Decimal,
    current_price: Decimal,
    min_qty: Decimal,
    qty_step: Decimal,
    min_order_value: Decimal,
    logger: logging.Logger
) -> Decimal:
    """
    Calculates the appropriate order quantity ensuring all exchange constraints are met.

    This function performs the following steps:
    1. Calculates the raw quantity based on the desired USDT investment.
    2. Adjusts the quantity down to the nearest valid quantity step.
    3. Ensures the quantity meets the minimum order quantity.
    4. Checks if the resulting order value meets the minimum required value.
    5. If the value is too low, it recalculates the quantity to meet the minimum value and re-adjusts for the quantity step.
    6. Returns the final, validated order quantity as a Decimal.

    Args:
        usdt_amount (Decimal): The desired amount in USDT to trade.
        current_price (Decimal): The current price of the asset.
        min_qty (Decimal): The minimum order quantity for the symbol.
        qty_step (Decimal): The quantity step (increment) for the symbol.
        min_order_value (Decimal): The minimum order value in USDT for the symbol.
        logger (logging.Logger): Logger instance for logging warnings or errors.

    Returns:
        Decimal: The calculated and adjusted order quantity. Returns Decimal('0') if inputs are invalid.
    """
    if usdt_amount <= Decimal('0') or current_price <= Decimal('0'):
        logger.error(f"{NEON_RED}USDT amount and current price must be positive for order calculation.{RESET_ALL_STYLE}")
        return Decimal('0')

    # 1. Calculate raw quantity
    raw_qty = usdt_amount / current_price

    # 2. Adjust for quantity step (round down)
    adjusted_qty = (raw_qty // qty_step) * qty_step if qty_step > Decimal('0') else raw_qty

    # 3. Ensure quantity meets the minimum requirement
    if adjusted_qty < min_qty:
        logger.warning(f"{NEON_YELLOW}Initial quantity {adjusted_qty:.8f} was below min_qty {min_qty}. Adjusting to min_qty.{RESET_ALL_STYLE}")
        adjusted_qty = min_qty

    # 4. Check if the order value is sufficient
    order_value = adjusted_qty * current_price
    if order_value < min_order_value:
        logger.warning(f"{NEON_YELLOW}Order value {order_value:.4f} is below min_order_value {min_order_value}. Recalculating quantity.{RESET_ALL_STYLE}")
        # Recalculate quantity to meet min_order_value and re-apply step logic
        required_qty = min_order_value / current_price
        # Round up to the nearest step to ensure value is met
        adjusted_qty = ((required_qty + qty_step - Decimal('1e-18')) // qty_step) * qty_step if qty_step > Decimal('0') else required_qty
        logger.info(f"{NEON_BLUE}Quantity adjusted to {adjusted_qty:.8f} to meet minimum order value.{RESET_ALL_STYLE}")

    # 5. Final check to ensure it's not below min_qty after all adjustments
    if adjusted_qty < min_qty:
        adjusted_qty = min_qty

    if adjusted_qty <= Decimal('0'):
        logger.error(f"{NEON_RED}Final calculated quantity is zero or negative. Aborting order calculation.{RESET_ALL_STYLE}")
        return Decimal('0')

    return adjusted_qty

def json_decimal_default(obj: Any) -> Any:
    """
    Custom JSON serializer for objects not serializable by default json code.
    Specifically handles Decimal objects by converting them to floats.
    """
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")
