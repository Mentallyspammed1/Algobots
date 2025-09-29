# precision_manager.py

import asyncio
import logging
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal, getcontext

from pybit.unified_trading import HTTP

# Set high precision for Decimal context globally (if not already set)
getcontext().prec = 28


@dataclass
class InstrumentSpecs:
    """Stores instrument specifications from Bybit."""

    symbol: str
    category: str
    base_currency: str
    quote_currency: str
    status: str

    # Price specifications
    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal  # Price precision

    # Quantity specifications
    min_order_qty: Decimal
    max_order_qty: Decimal
    qty_step: Decimal  # Quantity precision

    # Leverage specifications
    min_leverage: Decimal
    max_leverage: Decimal
    leverage_step: Decimal

    # Notional limits
    min_notional_value: Decimal = Decimal("0")  # Min order value in quote currency
    max_notional_value: Decimal = Decimal("0")  # Max order value in quote currency

    # Contract specifications (for derivatives)
    contract_value: Decimal = Decimal("1")
    is_inverse: bool = False

    # Fee rates (Fetched dynamically or default)
    maker_fee: Decimal = Decimal("0.0001")  # 0.01%
    taker_fee: Decimal = Decimal("0.0006")  # 0.06%


class PrecisionManager:
    """Manages decimal precision and instrument specifications for trading pairs."""

    def __init__(self, http_session: HTTP, logger: logging.Logger):
        self.http_session = http_session
        self.logger = logger
        self.instruments: dict[str, InstrumentSpecs] = {}
        self._lock = asyncio.Lock()  # For async loading
        self.is_loaded = False

    async def load_all_instruments(
        self, retry_delay: float = 5.0, max_retries: int = 3
    ):
        """Loads all instrument specifications from Bybit asynchronously."""
        async with self._lock:
            if self.is_loaded:
                self.logger.debug("Instruments already loaded.")
                return

            self.logger.info("Loading instrument specifications from Bybit...")
            categories = ["linear", "inverse", "spot", "option"]

            for category in categories:
                for attempt in range(max_retries):
                    try:
                        response = self.http_session.get_instruments_info(
                            category=category, limit=1000
                        )  # Max limit

                        if response["retCode"] == 0:
                            for inst_data in response["result"]["list"]:
                                symbol = inst_data["symbol"]

                                if category in ["linear", "inverse"]:
                                    specs = self._parse_derivatives_specs(
                                        inst_data, category
                                    )
                                elif category == "spot":
                                    specs = self._parse_spot_specs(inst_data, category)
                                elif category == "option":
                                    specs = self._parse_option_specs(
                                        inst_data, category
                                    )
                                else:
                                    self.logger.warning(
                                        f"Skipping unknown instrument category: {category}"
                                    )
                                    continue

                                self.instruments[symbol] = specs
                            self.logger.debug(
                                f"Loaded {len(response['result']['list'])} instruments for category: {category}"
                            )
                            break  # Success, move to next category
                        self.logger.error(
                            f"Failed to fetch {category} instruments (attempt {attempt + 1}/{max_retries}): {response['retMsg']}"
                        )
                        await asyncio.sleep(retry_delay)
                    except Exception as e:
                        self.logger.error(
                            f"Exception loading {category} instruments (attempt {attempt + 1}/{max_retries}): {e}"
                        )
                        await asyncio.sleep(retry_delay)
                else:  # This block runs if the loop completes without a 'break' (i.e., all retries failed)
                    self.logger.critical(
                        f"Failed to load {category} instruments after {max_retries} attempts. Bot might not function correctly."
                    )

            if not self.instruments:
                self.logger.critical(
                    "No instruments loaded. Critical error in PrecisionManager."
                )
            else:
                self.is_loaded = True
                self.logger.info(
                    f"Successfully loaded {len(self.instruments)} total instrument specifications."
                )

    async def fetch_and_update_fee_rates(
        self, category: str, symbol: str, retry_delay: float = 3.0, max_retries: int = 3
    ):
        """Fetches and updates user-specific fee rates for a given symbol and category asynchronously."""
        specs = self.get_specs(symbol)
        if not specs:
            self.logger.warning(
                f"Cannot update fee rates for {symbol}: specs not loaded. Please load instruments first."
            )
            return

        for attempt in range(max_retries):
            try:
                response = self.http_session.get_fee_rates(
                    category=category, symbol=symbol
                )
                if response["retCode"] == 0 and response["result"]["list"]:
                    fee_info = response["result"]["list"][0]
                    specs.maker_fee = Decimal(fee_info["makerFeeRate"])
                    specs.taker_fee = Decimal(fee_info["takerFeeRate"])
                    self.logger.info(
                        f"Updated fee rates for {symbol}: Maker={specs.maker_fee:.4f}, Taker={specs.taker_fee:.4f}"
                    )
                    return  # Success
                self.logger.warning(
                    f"Failed to fetch fee rates for {symbol} (attempt {attempt + 1}/{max_retries}): {response.get('retMsg', 'Unknown error')}. Using default fees."
                )
                await asyncio.sleep(retry_delay)
            except Exception as e:
                self.logger.error(
                    f"Exception fetching fee rates for {symbol} (attempt {attempt + 1}/{max_retries}): {e}. Using default fees."
                )
                await asyncio.sleep(retry_delay)
        self.logger.warning(
            f"Could not update fee rates for {symbol} after {max_retries} retries. Using default fee rates."
        )

    def _parse_derivatives_specs(self, inst: dict, category: str) -> InstrumentSpecs:
        """Parses derivatives instrument specifications."""
        lot_size = inst["lotSizeFilter"]
        price_filter = inst["priceFilter"]
        leverage_filter = inst["leverageFilter"]

        return InstrumentSpecs(
            symbol=inst["symbol"],
            category=category,
            base_currency=inst["baseCoin"],
            quote_currency=inst["quoteCoin"],
            status=inst["status"],
            min_price=Decimal(price_filter["minPrice"]),
            max_price=Decimal(price_filter["maxPrice"]),
            tick_size=Decimal(price_filter["tickSize"]),
            min_order_qty=Decimal(lot_size["minOrderQty"]),
            max_order_qty=Decimal(lot_size["maxOrderQty"]),
            qty_step=Decimal(lot_size["qtyStep"]),
            min_leverage=Decimal(leverage_filter["minLeverage"]),
            max_leverage=Decimal(leverage_filter["maxLeverage"]),
            leverage_step=Decimal(leverage_filter["leverageStep"]),
            min_notional_value=Decimal(
                lot_size.get("minOrderAmt", "0")
            ),  # Unified approach, 'minOrderAmt' for derivatives is notional
            max_notional_value=Decimal(lot_size.get("maxOrderAmt", "1000000000")),
            contract_value=Decimal(
                inst.get("contractValue", "1")
            ),  # e.g. 0.0001 BTC for inverse
            is_inverse=(category == "inverse"),
        )

    def _parse_spot_specs(self, inst: dict, category: str) -> InstrumentSpecs:
        """Parses spot instrument specifications."""
        lot_size = inst["lotSizeFilter"]
        price_filter = inst["priceFilter"]

        return InstrumentSpecs(
            symbol=inst["symbol"],
            category=category,
            base_currency=inst["baseCoin"],
            quote_currency=inst["quoteCoin"],
            status=inst["status"],
            min_price=Decimal(price_filter["minPrice"]),
            max_price=Decimal(price_filter["maxPrice"]),
            tick_size=Decimal(price_filter["tickSize"]),
            min_order_qty=Decimal(
                lot_size["basePrecision"]
            ),  # Spot uses basePrecision for min qty
            max_order_qty=Decimal(lot_size["maxOrderQty"]),
            qty_step=Decimal(
                lot_size["basePrecision"]
            ),  # Spot uses basePrecision for qty step
            min_leverage=Decimal("1"),  # Spot doesn't have leverage, use 1x
            max_leverage=Decimal("1"),
            leverage_step=Decimal("1"),
            min_notional_value=Decimal(
                lot_size.get("minOrderAmt", "0")
            ),  # min order value in quote currency
            max_notional_value=Decimal(lot_size.get("maxOrderAmt", "1000000000")),
            contract_value=Decimal("1"),
            is_inverse=False,
        )

    def _parse_option_specs(self, inst: dict, category: str) -> InstrumentSpecs:
        """Parses option instrument specifications."""
        lot_size = inst["lotSizeFilter"]
        price_filter = inst["priceFilter"]

        return InstrumentSpecs(
            symbol=inst["symbol"],
            category=category,
            base_currency=inst["baseCoin"],
            quote_currency=inst["quoteCoin"],
            status=inst["status"],
            min_price=Decimal(price_filter["minPrice"]),
            max_price=Decimal(price_filter["maxPrice"]),
            tick_size=Decimal(price_filter["tickSize"]),
            min_order_qty=Decimal(lot_size["minOrderQty"]),
            max_order_qty=Decimal(lot_size["maxOrderQty"]),
            qty_step=Decimal(lot_size["qtyStep"]),
            min_leverage=Decimal(
                "1"
            ),  # Options don't have traditional leverage, often 1x
            max_leverage=Decimal("1"),
            leverage_step=Decimal("1"),
            min_notional_value=Decimal(lot_size.get("minOrderAmt", "0")),
            max_notional_value=Decimal(lot_size.get("maxOrderAmt", "1000000000")),
            contract_value=Decimal("1"),
            is_inverse=False,
        )

    def get_specs(self, symbol: str) -> InstrumentSpecs | None:
        """Retrieves instrument specifications for a given symbol."""
        specs = self.instruments.get(symbol)
        if not specs:
            self.logger.warning(
                f"Instrument specifications for {symbol} not found. Ensure it's loaded."
            )
        return specs

    def round_price(
        self, symbol: str, price: float | Decimal, rounding_mode=ROUND_DOWN
    ) -> Decimal:
        """Rounds a price to the correct tick size for a symbol."""
        specs = self.get_specs(symbol)
        if not specs:
            # Fallback to a common precision if specs not found (e.g., for logging before specs loaded)
            return Decimal(str(price)).quantize(
                Decimal("0.000001"), rounding=rounding_mode
            )

        price_decimal = Decimal(str(price))
        tick_size = specs.tick_size

        if tick_size == Decimal("0"):  # Avoid division by zero
            return price_decimal

        rounded = (price_decimal / tick_size).quantize(
            Decimal("1"), rounding=rounding_mode
        ) * tick_size

        # Ensure within min/max bounds (optional, but good for validation)
        # rounded = max(specs.min_price, min(rounded, specs.max_price))

        return rounded

    def round_quantity(
        self, symbol: str, quantity: float | Decimal, rounding_mode=ROUND_DOWN
    ) -> Decimal:
        """Rounds a quantity to the correct step size for a symbol."""
        specs = self.get_specs(symbol)
        if not specs:
            # Fallback to a common precision if specs not found
            return Decimal(str(quantity)).quantize(
                Decimal("0.0001"), rounding=rounding_mode
            )

        qty_decimal = Decimal(str(quantity))
        qty_step = specs.qty_step

        if qty_step == Decimal("0"):  # Avoid division by zero
            return qty_decimal

        # Always round down quantities to avoid over-ordering
        rounded = (qty_decimal / qty_step).quantize(
            Decimal("1"), rounding=rounding_mode
        ) * qty_step

        # Ensure within min/max bounds (optional)
        # rounded = max(specs.min_order_qty, min(rounded, specs.max_order_qty))

        return rounded

    def get_decimal_places(self, symbol: str) -> tuple[int, int]:
        """Returns (price_decimal_places, quantity_decimal_places) for a symbol."""
        specs = self.get_specs(symbol)
        if not specs:
            return 6, 4  # Default common precisions

        price_decimals = abs(specs.tick_size.as_tuple().exponent)
        qty_decimals = abs(specs.qty_step.as_tuple().exponent)

        return price_decimals, qty_decimals
