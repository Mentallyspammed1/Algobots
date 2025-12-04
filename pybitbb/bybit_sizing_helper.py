# bybit_sizing_helper.py
import logging
import math
import time
from typing import Any

# Import the market data helper to fetch instrument information
from bybit_market_data_helper import BybitMarketDataHelper

# Configure logging for the module
logging.basicConfig(
    level=logging.INFO,  # Changed to INFO for less verbose default output, DEBUG for full details
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


class BybitSizingHelper:
    """A helper class for managing order sizing, decimal precision, and price tick
    rules for Bybit trading instruments. It fetches instrument information
    to ensure orders comply with exchange requirements.
    """

    def __init__(self, testnet: bool = False, api_key: str = "", api_secret: str = ""):
        """Initializes the BybitSizingHelper.

        :param testnet: Set to True to connect to the Bybit testnet, False for mainnet.
        :param api_key: Optional. Your Bybit API key.
        :param api_secret: Optional. Your Bybit API secret.
        """
        self.market_data_helper = BybitMarketDataHelper(
            testnet=testnet, api_key=api_key, api_secret=api_secret,
        )
        # Cache for instrument info: {f"{category}_{symbol}": instrument_details_dict}
        self._instrument_info_cache: dict[str, dict[str, Any]] = {}
        self._cache_expiry_time: dict[
            str, float,
        ] = {}  # {f"{category}_{symbol}": timestamp_of_expiry}
        self.cache_duration_seconds = 3600  # Cache instrument info for 1 hour

        logger.info(f"BybitSizingHelper initialized. Testnet: {testnet}.")

    def _get_instrument_info(
        self, category: str, symbol: str, force_update: bool = False,
    ) -> dict[str, Any] | None:
        """Internal method to get instrument information, utilizing a cache.

        :param category: The product type.
        :param symbol: The trading symbol.
        :param force_update: If True, bypasses the cache and fetches new data.
        :return: A dictionary containing instrument details or None on failure.
        """
        cache_key = f"{category}_{symbol}"
        current_time = time.time()

        if (
            not force_update
            and cache_key in self._instrument_info_cache
            and current_time < self._cache_expiry_time.get(cache_key, 0)
        ):
            logger.debug(f"Using cached instrument info for {symbol}.")
            return self._instrument_info_cache[cache_key]

        logger.info(
            f"Fetching fresh instrument info for {symbol} (category: {category}).",
        )
        info = self.market_data_helper.get_instruments_info(
            category=category, symbol=symbol,
        )

        if info and info.get("list"):
            instrument_details = info["list"][0]
            self._instrument_info_cache[cache_key] = instrument_details
            self._cache_expiry_time[cache_key] = (
                current_time + self.cache_duration_seconds
            )
            logger.debug(
                f"Cached instrument info for {symbol} (expires in {self.cache_duration_seconds}s).",
            )
            return instrument_details

        logger.error(
            f"Failed to retrieve instrument info for {symbol} (category: {category}).",
        )
        return None

    def _get_filter_value(
        self,
        category: str,
        symbol: str,
        filter_type: str,
        key: str,
        default: float = 0.0,
    ) -> float:
        """Helper to safely extract filter values from instrument info."""
        info = self._get_instrument_info(category, symbol)
        if info:
            filter_data = info.get(filter_type, {})
            value = filter_data.get(key)
            if value is not None:
                try:
                    return float(value)
                except ValueError:
                    logger.error(
                        f"Invalid numerical value for {key} in {filter_type} for {symbol}: {value}",
                    )
        logger.warning(
            f"Could not get {key} from {filter_type} for {symbol}. Using default: {default}",
        )
        return default

    # --- Quantity Filters ---
    def get_min_order_qty(self, category: str, symbol: str) -> float:
        """Retrieves the minimum order quantity allowed for a symbol.

        :param category: The product type.
        :param symbol: The trading symbol.
        :return: Minimum order quantity as a float. Returns 0.0 if not found.
        """
        return self._get_filter_value(
            category, symbol, "lotSizeFilter", "minOrderQty", default=0.0,
        )

    def get_max_order_qty(self, category: str, symbol: str) -> float:
        """Retrieves the maximum order quantity allowed for a symbol.

        :param category: The product type.
        :param symbol: The trading symbol.
        :return: Maximum order quantity as a float. Returns a very large number if not found.
        """
        # Max order qty might not always be explicitly set, use a large default
        return self._get_filter_value(
            category, symbol, "lotSizeFilter", "maxOrderQty", default=float("inf"),
        )

    def get_qty_step(self, category: str, symbol: str) -> float:
        """Retrieves the quantity step size (increment) for a symbol.

        :param category: The product type.
        :param symbol: The trading symbol.
        :return: Quantity step size as a float. Returns 0.0 if not found.
        """
        return self._get_filter_value(
            category, symbol, "lotSizeFilter", "qtyStep", default=0.0,
        )

    def get_qty_precision(self, category: str, symbol: str) -> int:
        """Calculates the decimal precision for quantity based on `qtyStep`.

        :param category: The product type.
        :param symbol: The trading symbol.
        :return: Number of decimal places for quantity. Returns 0 if not found.
        """
        qty_step = self.get_qty_step(category, symbol)
        if qty_step == 0.0:  # Avoid log10(0)
            return 0
        # Calculate precision: e.g., 0.01 -> 2, 0.001 -> 3
        precision = int(round(-math.log10(qty_step), 0)) if qty_step < 1 else 0
        return max(0, precision)  # Ensure non-negative precision

    # --- Price Filters ---
    def get_min_price(self, category: str, symbol: str) -> float:
        """Retrieves the minimum price allowed for an order.

        :param category: The product type.
        :param symbol: The trading symbol.
        :return: Minimum price as a float. Returns 0.0 if not found.
        """
        return self._get_filter_value(
            category, symbol, "priceFilter", "minPrice", default=0.0,
        )

    def get_max_price(self, category: str, symbol: str) -> float:
        """Retrieves the maximum price allowed for an order.

        :param category: The product type.
        :param symbol: The trading symbol.
        :return: Maximum price as a float. Returns a very large number if not found.
        """
        return self._get_filter_value(
            category, symbol, "priceFilter", "maxPrice", default=float("inf"),
        )

    def get_price_tick_size(self, category: str, symbol: str) -> float:
        """Retrieves the price tick size (minimum increment) for a symbol.

        :param category: The product type.
        :param symbol: The trading symbol.
        :return: Price tick size as a float. Returns 0.0 if not found.
        """
        return self._get_filter_value(
            category, symbol, "priceFilter", "tickSize", default=0.0,
        )

    def get_price_precision(self, category: str, symbol: str) -> int:
        """Calculates the decimal precision for price based on `tickSize`.

        :param category: The product type.
        :param symbol: The trading symbol.
        :return: Number of decimal places for price. Returns 0 if not found.
        """
        tick_size = self.get_price_tick_size(category, symbol)
        if tick_size == 0.0:  # Avoid log10(0)
            return 0
        # Calculate precision: e.g., 0.01 -> 2, 0.001 -> 3
        precision = int(round(-math.log10(tick_size), 0)) if tick_size < 1 else 0
        return max(0, precision)  # Ensure non-negative precision

    # --- Rounding and Validation ---
    def round_qty(self, category: str, symbol: str, quantity: float | str) -> float:
        """Rounds a given quantity to the nearest valid quantity based on `qtyStep`.

        :param category: The product type.
        :param symbol: The trading symbol.
        :param quantity: The quantity to round.
        :return: The rounded quantity as a float.
        """
        try:
            qty_float = float(quantity)
        except ValueError:
            logger.error(f"Invalid quantity format '{quantity}' for rounding.")
            return 0.0

        qty_step = self.get_qty_step(category, symbol)
        if qty_step == 0.0:
            return qty_float  # Cannot round if step is 0

        rounded_qty = round(qty_float / qty_step) * qty_step
        # Ensure correct precision for floating point arithmetic issues
        precision = self.get_qty_precision(category, symbol)
        return round(rounded_qty, precision)

    def round_price(self, category: str, symbol: str, price: float | str) -> float:
        """Rounds a given price to the nearest valid price based on `tickSize`.

        :param category: The product type.
        :param symbol: The trading symbol.
        :param price: The price to round.
        :return: The rounded price as a float.
        """
        try:
            price_float = float(price)
        except ValueError:
            logger.error(f"Invalid price format '{price}' for rounding.")
            return 0.0

        tick_size = self.get_price_tick_size(category, symbol)
        if tick_size == 0.0:
            return price_float  # Cannot round if tick size is 0

        rounded_price = round(price_float / tick_size) * tick_size
        # Ensure correct precision for floating point arithmetic issues
        precision = self.get_price_precision(category, symbol)
        return round(rounded_price, precision)

    def is_valid_qty(self, category: str, symbol: str, quantity: float | str) -> bool:
        """Checks if a given quantity is valid according to the instrument's rules.

        :param category: The product type.
        :param symbol: The trading symbol.
        :param quantity: The quantity to validate.
        :return: True if the quantity is valid, False otherwise.
        """
        try:
            qty_float = float(quantity)
        except ValueError:
            logger.warning(f"Invalid quantity format '{quantity}' for validation.")
            return False

        min_qty = self.get_min_order_qty(category, symbol)
        max_qty = self.get_max_order_qty(category, symbol)
        qty_step = self.get_qty_step(category, symbol)

        if qty_float < min_qty:
            logger.warning(
                f"Quantity {qty_float} is less than min_qty {min_qty} for {symbol}.",
            )
            return False
        if qty_float > max_qty:
            logger.warning(
                f"Quantity {qty_float} is greater than max_qty {max_qty} for {symbol}.",
            )
            return False

        # Check if quantity is a multiple of qty_step
        if (
            qty_step > 0 and (qty_float - min_qty) % qty_step > 1e-9
        ):  # Allow small float tolerance
            logger.warning(
                f"Quantity {qty_float} is not a multiple of qty_step {qty_step} (min_qty={min_qty}) for {symbol}.",
            )
            return False

        return True

    def is_valid_price(self, category: str, symbol: str, price: float | str) -> bool:
        """Checks if a given price is valid according to the instrument's rules.

        :param category: The product type.
        :param symbol: The trading symbol.
        :param price: The price to validate.
        :return: True if the price is valid, False otherwise.
        """
        try:
            price_float = float(price)
        except ValueError:
            logger.warning(f"Invalid price format '{price}' for validation.")
            return False

        min_price = self.get_min_price(category, symbol)
        max_price = self.get_max_price(category, symbol)
        tick_size = self.get_price_tick_size(category, symbol)

        if price_float < min_price:
            logger.warning(
                f"Price {price_float} is less than min_price {min_price} for {symbol}.",
            )
            return False
        if price_float > max_price:
            logger.warning(
                f"Price {price_float} is greater than max_price {max_price} for {symbol}.",
            )
            return False

        # Check if price is a multiple of tick_size
        if (
            tick_size > 0 and price_float % tick_size > 1e-9
        ):  # Allow small float tolerance
            logger.warning(
                f"Price {price_float} is not a multiple of tick_size {tick_size} for {symbol}.",
            )
            return False

        return True


# Example Usage
if __name__ == "__main__":
    # For public market data, API key/secret are optional.
    # Set USE_TESTNET to False for production (mainnet).
    API_KEY = ""  # Optional for public market data
    API_SECRET = ""  # Optional for public market data
    USE_TESTNET = True

    sizing_helper = BybitSizingHelper(
        testnet=USE_TESTNET, api_key=API_KEY, api_secret=API_SECRET,
    )

    SYMBOL = "BTCUSDT"
    CATEGORY = "linear"  # Or 'spot', 'inverse', 'option'

    print(f"\n--- Retrieving Sizing Information for {SYMBOL} ({CATEGORY}) ---")

    # Force update to see initial fetch log
    sizing_helper._get_instrument_info(CATEGORY, SYMBOL, force_update=True)

    min_qty = sizing_helper.get_min_order_qty(CATEGORY, SYMBOL)
    qty_step = sizing_helper.get_qty_step(CATEGORY, SYMBOL)
    qty_precision = sizing_helper.get_qty_precision(CATEGORY, SYMBOL)
    max_qty = sizing_helper.get_max_order_qty(CATEGORY, SYMBOL)

    min_price = sizing_helper.get_min_price(CATEGORY, SYMBOL)
    price_tick_size = sizing_helper.get_price_tick_size(CATEGORY, SYMBOL)
    price_precision = sizing_helper.get_price_precision(CATEGORY, SYMBOL)
    max_price = sizing_helper.get_max_price(CATEGORY, SYMBOL)

    print(f"  Min Order Quantity: {min_qty}")
    print(f"  Quantity Step: {qty_step}")
    print(f"  Quantity Precision (decimals): {qty_precision}")
    print(f"  Max Order Quantity: {max_qty}")
    print(f"  Min Price: {min_price}")
    print(f"  Price Tick Size: {price_tick_size}")
    print(f"  Price Precision (decimals): {price_precision}")
    print(f"  Max Price: {max_price}")

    print(f"\n--- Testing Quantity Rounding and Validation for {SYMBOL} ---")
    test_qty = 0.0012345
    rounded_qty = sizing_helper.round_qty(CATEGORY, SYMBOL, test_qty)
    is_valid_test_qty = sizing_helper.is_valid_qty(CATEGORY, SYMBOL, rounded_qty)
    print(f"  Original Qty: {test_qty}")
    print(f"  Rounded Qty: {rounded_qty}")
    print(f"  Is Rounded Qty Valid? {is_valid_test_qty}")

    invalid_qty_low = min_qty / 2
    is_valid_low = sizing_helper.is_valid_qty(CATEGORY, SYMBOL, invalid_qty_low)
    print(f"  Is {invalid_qty_low} valid? {is_valid_low} (Expected: False)")

    invalid_qty_step = (
        min_qty + (qty_step / 2) if qty_step > 0 else min_qty + 0.000000001
    )
    is_valid_step = sizing_helper.is_valid_qty(CATEGORY, SYMBOL, invalid_qty_step)
    print(
        f"  Is {invalid_qty_step} valid? {is_valid_step} (Expected: False, due to step)",
    )

    print(f"\n--- Testing Price Rounding and Validation for {SYMBOL} ---")
    test_price = 45123.456789
    rounded_price = sizing_helper.round_price(CATEGORY, SYMBOL, test_price)
    is_valid_test_price = sizing_helper.is_valid_price(CATEGORY, SYMBOL, rounded_price)
    print(f"  Original Price: {test_price}")
    print(f"  Rounded Price: {rounded_price}")
    print(f"  Is Rounded Price Valid? {is_valid_test_price}")

    invalid_price_low = min_price / 2
    is_valid_low_price = sizing_helper.is_valid_price(
        CATEGORY, SYMBOL, invalid_price_low,
    )
    print(f"  Is {invalid_price_low} valid? {is_valid_low_price} (Expected: False)")

    invalid_price_tick = (
        min_price + (price_tick_size / 2)
        if price_tick_size > 0
        else min_price + 0.000000001
    )
    is_valid_tick = sizing_helper.is_valid_price(CATEGORY, SYMBOL, invalid_price_tick)
    print(
        f"  Is {invalid_price_tick} valid? {is_valid_tick} (Expected: False, due to tick size)",
    )

    # Test with a symbol that might have different rules (e.g., a spot pair)
    SPOT_SYMBOL = "ETHUSDT"
    SPOT_CATEGORY = "spot"
    print(
        f"\n--- Retrieving Sizing Information for {SPOT_SYMBOL} ({SPOT_CATEGORY}) ---",
    )
    sizing_helper._get_instrument_info(SPOT_CATEGORY, SPOT_SYMBOL, force_update=True)
    print(
        f"  Min Order Quantity for {SPOT_SYMBOL}: {sizing_helper.get_min_order_qty(SPOT_CATEGORY, SPOT_SYMBOL)}",
    )
    print(
        f"  Price Tick Size for {SPOT_SYMBOL}: {sizing_helper.get_price_tick_size(SPOT_CATEGORY, SPOT_SYMBOL)}",
    )
