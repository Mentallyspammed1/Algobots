import logging
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal
from typing import Any

from colorama import Fore, Style

# Color Scheme
NEON_RED = Fore.LIGHTRED_EX
NEON_YELLOW = Fore.YELLOW
NEON_GREEN = Fore.LIGHTGREEN_EX
RESET = Style.RESET_ALL


class PrecisionManager:
    """Manages decimal precision for trading operations based on Bybit's instrument info."""

    def __init__(self, bybit_client, logger: logging.Logger):
        self.bybit_client = (
            bybit_client  # This will be an instance of the new BybitClient
        )
        self.logger = logger
        self.instruments_info: dict[str, Any] = {}
        self.initialized = False

    async def load_instrument_info(self, symbol: str):
        """Load instrument specifications from Bybit."""
        response = await self.bybit_client._bybit_request_with_retry(
            "get_instruments_info",
            self.bybit_client.http_session.get_instruments_info,
            category=self.bybit_client.category,
            symbol=symbol,
        )
        if response and response["result"] and response["result"]["list"]:
            spec = response["result"]["list"][0]
            price_filter = spec["priceFilter"]
            lot_size_filter = spec["lotSizeFilter"]

            self.instruments_info[symbol] = {
                "price_precision_str": str(Decimal(price_filter["tickSize"])),
                "price_precision_decimal": Decimal(price_filter["tickSize"]),
                "qty_precision_str": str(Decimal(lot_size_filter["qtyStep"])),
                "qty_precision_decimal": Decimal(lot_size_filter["qtyStep"]),
                "min_qty": Decimal(lot_size_filter["minOrderQty"]),
                "max_qty": Decimal(lot_size_filter["maxOrderQty"]),
                "min_notional": Decimal(
                    lot_size_filter.get("minNotionalValue", "0"),
                ),  # Some categories might not have this
            }
            self.logger.info(
                f"{NEON_GREEN}Instrument specs loaded for {symbol}: Price tick={self.instruments_info[symbol]['price_precision_decimal']}, Qty step={self.instruments_info[symbol]['qty_precision_decimal']}{RESET}",
            )
            self.initialized = True
        else:
            self.logger.error(
                f"{NEON_RED}Failed to load instrument specs for {symbol}. Trading might be inaccurate.{RESET}",
            )

    def _get_specs(self, symbol: str) -> dict | None:
        """Helper to get specs for a symbol."""
        specs = self.instruments_info.get(symbol)
        if not specs and self.initialized:  # Avoid spamming if not initialized yet
            self.logger.warning(
                f"{NEON_YELLOW}Instrument specs not found for {symbol}. Using generic Decimal precision.{RESET}",
            )
            return None
        return specs

    def round_price(self, price: Decimal, symbol: str) -> Decimal:
        """Round price to correct tick size."""
        specs = self._get_specs(symbol)
        if specs:
            return price.quantize(
                specs["price_precision_decimal"],
                rounding=ROUND_HALF_EVEN,
            )
        return price.quantize(Decimal("0.00001"), rounding=ROUND_HALF_EVEN)  # Default

    def round_qty(self, qty: Decimal, symbol: str) -> Decimal:
        """Round quantity to correct step size."""
        specs = self._get_specs(symbol)
        if specs:
            return qty.quantize(specs["qty_precision_decimal"], rounding=ROUND_DOWN)
        return qty.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)  # Default

    def get_min_qty(self, symbol: str) -> Decimal:
        """Get minimum order quantity."""
        specs = self._get_specs(symbol)
        return specs["min_qty"] if specs else Decimal("0.00001")

    def get_max_qty(self, symbol: str) -> Decimal:
        """Get maximum order quantity."""
        specs = self._get_specs(symbol)
        return specs["max_qty"] if specs else Decimal("1000000")

    def get_min_notional(self, symbol: str) -> Decimal:
        """Get minimum notional value (order cost)."""
        specs = self._get_specs(symbol)
        return specs["min_notional"] if specs else Decimal("5")  # Default $5 notional
