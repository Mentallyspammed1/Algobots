#!/usr/bin/env python3
"""
MMXCEL – Bybit Hedge-Mode Market-Making Bot
Compatible drop-in replacement for xmm.py
"""

import asyncio
import json
import logging
import logging.handlers  # Explicitly imported to fix AttributeError
import os
import signal
import sys
import time
from decimal import ROUND_DOWN, ROUND_UP, Decimal, DecimalException, getcontext
from typing import Any

from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket

# Initialize colorama for cross-platform color support
init(autoreset=True)

# High-precision decimals for financial calculations
getcontext().prec = 12

# Optional: prettier colours if termcolor is available
try:
    from termcolor import colored
    _has_termcolor = True
except ImportError:
    _has_termcolor = False
    def colored(text, color):  # Fallback function
        return text

# ANSI Color shortcuts
NC = Style.RESET_ALL
BOLD = Style.BRIGHT
RED = Fore.RED
GREEN = Fore.GREEN
YELLOW = Fore.YELLOW
BLUE = Fore.BLUE
MAGENTA = Fore.MAGENTA
CYAN = Fore.CYAN
WHITE = Fore.WHITE
UNDERLINE = BOLD + Fore.CYAN

# Load environment variables
load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

# Load runtime configuration
try:
    with open("config.json") as f:
        config = json.load(f)
except FileNotFoundError:
    print(f"{RED}config.json not found. Please create it.{NC}")
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"{RED}config.json is malformed JSON: {e}{NC}")
    sys.exit(1)

# Configure logging with rotation
LOG_FILE = "mmxcel.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5  # 5MB log file size
        ),
    ],
)
logger = logging.getLogger("MMXCEL")

# Global configuration aliases
SYMBOL = str(config.get("SYMBOL", "BTCUSDT"))
CATEGORY = str(config.get("CATEGORY", "linear"))
QUANTITY = Decimal(str(config.get("QUANTITY", "0.001")))
SPREAD_PERCENTAGE = Decimal(str(config.get("SPREAD_PERCENTAGE", "0.0005")))
MAX_OPEN_ORDERS = int(config.get("MAX_OPEN_ORDERS", 2))
ORDER_LIFESPAN_SECONDS = int(config.get("ORDER_LIFESPAN_SECONDS", 30))
REBALANCE_THRESHOLD_QTY = Decimal(str(config.get("REBALANCE_THRESHOLD_QTY", "0.0001")))
PROFIT_PERCENTAGE = Decimal(str(config.get("PROFIT_PERCENTAGE", "0.001")))
STOP_LOSS_PERCENTAGE = Decimal(str(config.get("STOP_LOSS_PERCENTAGE", "0.005")))
PRICE_THRESHOLD = Decimal(str(config.get("PRICE_THRESHOLD", "0.0002")))
USE_TESTNET = bool(config.get("USE_TESTNET", True))
ORDER_REFRESH_INTERVAL = int(config.get("ORDER_REFRESH_INTERVAL", 5))

# Constants for data freshness and retry delays
MAX_DATA_AGE_SECONDS = 10  # Maximum acceptable age for market data
MAX_RETRIES_DEFAULT = 5    # Default maximum retries for API calls
RETRY_DELAY_DEFAULT = 2    # Initial delay for retries in seconds

# WebSocket shared state
ws_state = {
    "mid_price": Decimal("0"),
    "best_bid": Decimal("0"),
    "best_ask": Decimal("0"),
    "open_orders": {},
    "positions": {},
    "last_update_time": 0,  # Timestamp of last successful WS market data update
    "last_balance_update": 0,
    "available_balance": Decimal("0")
}

# Flag to check if termux-toast command is available
_HAS_TERMUX_TOAST_CMD = False

# -----------------------------
# Helper Functions
# -----------------------------

def _calculate_decimal_precision(d: Decimal) -> int:
    """Determine the number of decimal places in a Decimal value for display."""
    if not isinstance(d, Decimal):
        return 0
    # Normalize to remove trailing zeros, then check decimal places
    s = str(d.normalize())
    return len(s.split(".")[1]) if "." in s else 0

def clear_screen() -> None:
    """Clear the terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")

def print_neon_header(text: str, color: str = UNDERLINE, length: int = 80) -> None:
    """Print a styled header with border."""
    border_char = "✨"
    max_text_len = length - (len(border_char) * 2 + 4)
    if len(text) > max_text_len:
        text = text[: max_text_len - 3] + "..."
    header_text = f" {border_char}-- {text} --{border_char} "
    padding_total = length - len(header_text)
    padding_left = padding_total // 2
    padding_right = padding_total - padding_left
    full_header = f"{' ' * padding_left}{color}{header_text}{NC}{' ' * padding_right}"
    print(full_header)

def print_neon_separator(length: int = 80, char: str = "─", color: str = CYAN) -> None:
    """Print a separator line."""
    print(f"{color}{char * length}{NC}")

def format_metric(
    label: str,
    value: Any,
    label_color: str,
    value_color: str | None = None,
    label_width: int = 25,
    value_precision: int | None = None,
    unit: str = "",
    is_pnl: bool = False,
) -> str:
    """Format a label-value pair for display with precision and color."""
    formatted_label = f"{label_color}{label:<{label_width}}{NC}"
    actual_value_color = value_color if value_color else label_color
    formatted_value = ""

    if isinstance(value, Decimal):
        # Dynamically determine precision if not provided
        current_precision = value_precision if value_precision is not None else _calculate_decimal_precision(value)
        if is_pnl:
            actual_value_color = GREEN if value >= Decimal("0") else RED
            sign = "+" if value > Decimal("0") else ""
            formatted_value = f"{actual_value_color}{sign}{value:,.{current_precision}f}{unit}{NC}"
        else:
            formatted_value = f"{actual_value_color}{value:,.{current_precision}f}{unit}{NC}"
    elif isinstance(value, (int, float)):
        if is_pnl:
            actual_value_color = GREEN if value >= 0 else RED
            sign = "+" if value > 0 else ""
            formatted_value = f"{actual_value_color}{sign}{value:,}{unit}{NC}"
        else:
            formatted_value = f"{actual_value_color}{value:,}{unit}{NC}"
    else: # For strings or other types
        formatted_value = f"{actual_value_color}{value!s}{unit}{NC}"
    return f"{formatted_label}: {formatted_value}"

def check_termux_toast() -> bool:
    """Checks if the termux-toast command is available."""
    return os.system("command -v termux-toast > /dev/null 2>&1") == 0

def send_toast(message: str, color: str = "#336699", text_color: str = "white") -> None:
    """Sends a toast message if termux-toast is available."""
    if _HAS_TERMUX_TOAST_CMD:
        os.system(f"termux-toast -b '{color}' -c '{text_color}' '{message}'")

# -----------------------------
# WebSocket Callbacks
# -----------------------------

def on_public_ws_message(msg: dict[str, Any]) -> None:
    """Handle public WebSocket messages (orderbook)."""
    try:
        topic = msg.get("topic")
        # Ensure it's the expected orderbook topic
        if topic and topic.startswith("orderbook.1."):
            data = msg.get("data")
            if data and data.get("b") and data.get("a"):
                bid_info = data["b"][0]
                ask_info = data["a"][0]

                ws_state["best_bid"] = Decimal(bid_info[0])
                ws_state["best_ask"] = Decimal(ask_info[0])
                # Calculate mid-price only if both bid and ask are valid
                if ws_state["best_bid"] > 0 and ws_state["best_ask"] > 0:
                    ws_state["mid_price"] = (ws_state["best_bid"] + ws_state["best_ask"]) / Decimal("2")
                else:
                    ws_state["mid_price"] = Decimal("0")

                ws_state["last_update_time"] = time.time()
                # Log detailed market data only at debug level
                logger.debug(f"WS Orderbook: Bid={ws_state['best_bid']:.4f}, Ask={ws_state['best_ask']:.4f}, Mid={ws_state['mid_price']:.4f}")
    except (KeyError, IndexError, ValueError, TypeError, DecimalException) as e:
        logger.error(f"Error processing public WS message: {type(e).__name__} - {e} | Message: {msg}")
    except Exception as e:
        logger.error(f"Unexpected error in public WS handler: {type(e).__name__} - {e} | Message: {msg}")

def on_private_ws_message(msg: dict[str, Any]) -> None:
    """Handle private WebSocket messages (orders, positions)."""
    try:
        topic = msg.get("topic")
        if topic == "order":
            for o in msg["data"]:
                oid = o.get("orderId")
                if not oid: continue # Skip if orderId is missing

                if o.get("orderStatus") in ("Filled", "Canceled", "Deactivated"):
                    ws_state["open_orders"].pop(oid, None)
                    logger.debug(f"WS Order Closed: ID {oid}, Status {o['orderStatus']}")
                else:
                    ws_state["open_orders"][oid] = {
                        "client_order_id": o.get("orderLinkId", "N/A"),
                        "symbol": o.get("symbol"),
                        "side": o.get("side"),
                        "price": Decimal(o.get("price", "0")),
                        "qty": Decimal(o.get("qty", "0")),
                        "status": o.get("orderStatus"),
                        "timestamp": float(o.get("createdTime", 0)) / 1000,
                    }
        elif topic == "position":
            for p in msg["data"]:
                if p.get("symbol") == SYMBOL:
                    side = "Long" if p.get("side") == "Buy" else "Short"
                    ws_state["positions"][side] = {
                        "size": Decimal(p.get("size", "0")),
                        "avg_price": Decimal(p.get("avgPrice", "0")),
                        "unrealisedPnl": Decimal(p.get("unrealisedPnl", "0")),
                    }
    except (KeyError, ValueError, TypeError, DecimalException) as e:
        logger.error(f"Error processing private WS message: {type(e).__name__} - {e} | Message: {msg}")
    except Exception as e:
        logger.error(f"Unexpected error in private WS handler: {type(e).__name__} - {e} | Message: {msg}")

# -----------------------------
# Bybit Client Class
# -----------------------------

class BybitClient:
    # Use default values for max_retries and retry_delay
    # These can be overridden if needed, but library defaults are often good.
    MAX_RETRIES = 5
    RETRY_DELAY = 2  # Initial delay in seconds

    def __init__(self, key: str, secret: str, testnet: bool):
        self.http = HTTP(testnet=testnet, api_key=key, api_secret=secret)
        # Set retries for WebSocket reconnection
        self.ws_public = WebSocket(testnet=testnet, channel_type="linear", retries=self.MAX_RETRIES)
        self.ws_private = WebSocket(testnet=testnet, channel_type="private", api_key=key, api_secret=secret, retries=self.MAX_RETRIES)
        self.current_balance = Decimal("0")
        self.is_public_ws_connected = False
        self.is_private_ws_connected = False

        # Register callbacks for connection status changes
        self.ws_public.on_open = lambda: self._on_ws_open("public")
        self.ws_private.on_open = lambda: self._on_ws_open("private")
        self.ws_public.on_close = lambda: self._on_ws_close("public")
        self.ws_private.on_close = lambda: self._on_ws_close("private")
        self.ws_public.on_error = lambda err: self._on_ws_error("public", err)
        self.ws_private.on_error = lambda err: self._on_ws_error("private", err)

    def _on_ws_open(self, ws_type: str):
        """Callback when a WebSocket connection opens."""
        if ws_type == "public":
            self.is_public_ws_connected = True
            logger.info("Public WebSocket connection established.")
        elif ws_type == "private":
            self.is_private_ws_connected = True
            logger.info("Private WebSocket connection established.")

    def _on_ws_close(self, ws_type: str):
        """Callback when a WebSocket connection closes."""
        if ws_type == "public":
            self.is_public_ws_connected = False
            logger.warning("Public WebSocket connection closed. Attempting to reconnect...")
        elif ws_type == "private":
            self.is_private_ws_connected = False
            logger.warning("Private WebSocket connection closed. Attempting to reconnect...")

    def _on_ws_error(self, ws_type: str, error: Exception):
        """Callback for WebSocket errors."""
        logger.error(f"{ws_type.capitalize()} WebSocket error: {error}")

    async def _api(self, api_method, *args, **kwargs):
        """Generic retry wrapper for API calls with exponential backoff and error handling."""
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = api_method(*args, **kwargs)
                if response and response.get("retCode") == 0:
                    return response

                # Extract error details
                ret_code = response.get('retCode') if response else None
                ret_msg = response.get('retMsg', 'No response or unknown error') if response else 'No response'
                error_msg = f"API Call Failed (Attempt {attempt}/{self.MAX_RETRIES}, Code: {ret_code}): {ret_msg}"
                logger.warning(error_msg)

                # Handle specific error codes for retries
                # 10001: System error, 10006: Too many requests (rate limit),
                # 30034: Spot order placement failed, 30035: Too many spot order requests
                if ret_code in [10001, 10006, 30034, 30035]:
                    if attempt < self.MAX_RETRIES:
                        delay = self.RETRY_DELAY * (2 ** (attempt - 1))  # Exponential backoff
                        logger.warning(f"Retrying in {delay}s...")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"API retries exhausted for {api_method.__name__}. Last error: {ret_msg}")
                        return None
                else:
                    # Non-retryable errors (e.g., invalid parameters, authentication failure)
                    logger.error(f"Non-retryable API error: {ret_msg}")
                    return None
            except Exception as e:
                # Catch network errors, connection issues, unexpected exceptions
                error_msg = f"Exception during API call (Attempt {attempt}/{self.MAX_RETRIES}): {type(e).__name__} - {e}"
                logger.error(error_msg)
                if attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAY * (2 ** (attempt - 1)) # Exponential backoff
                    logger.warning(f"Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"API call failed after all retries: {type(e).__name__} - {e}")
                    return None
        return None # Should not be reached if MAX_RETRIES >= 1, but good practice

    async def get_symbol_info(self) -> bool:
        """Fetch symbol precision details, including min order value."""
        response = await self._api(
            self.http.get_instruments_info,
            category=CATEGORY,
            symbol=SYMBOL
        )
        if response and response.get('retCode') == 0:
            instruments = response.get('result', {}).get('list')
            if instruments:
                instrument_info = instruments[0]
                price_filter = instrument_info.get('priceFilter', {})
                lot_size_filter = instrument_info.get('lotSizeFilter', {})

                symbol_info["price_precision"] = Decimal(price_filter.get('tickSize', "0.0001"))
                symbol_info["qty_precision"] = Decimal(lot_size_filter.get('qtyStep', "0.001"))

                # Attempt to infer minimum order value. Bybit's API doesn't directly expose min_order_value.
                # We can use minPrice * minQty or minPrice * qty_precision as a proxy.
                # Using minPrice directly might be too restrictive if minQty is small.
                # Let's use minPrice for price filter check and minQty for quantity check.
                min_price = Decimal(price_filter.get('minPrice', "0"))
                min_qty = Decimal(lot_size_filter.get('minQty', "0"))

                # Store for validation later
                symbol_info["min_price"] = min_price
                symbol_info["min_qty"] = min_qty

                # Calculate a safety minimum order value proxy
                if min_price > 0 and min_qty > 0:
                    symbol_info["min_order_value"] = min_price * min_qty
                else:
                    symbol_info["min_order_value"] = Decimal("10.0") # Default if cannot infer

                logger.info(f"Symbol Info: {SYMBOL} | Price Precision={symbol_info['price_precision']}, Qty Precision={symbol_info['qty_precision']}, Min Price={min_price}, Min Qty={min_qty}")
                return True
            logger.error(f"Symbol {SYMBOL} not found in instruments info.")
            return False
        logger.error(f"Failed to fetch instrument info for {SYMBOL}.")
        return False

    async def test_credentials(self) -> bool:
        """Verify API credentials by fetching wallet balance."""
        response = await self._api(self.http.get_wallet_balance, accountType="UNIFIED")
        if response and response.get("retCode") == 0:
            logger.info("API credentials validated successfully.")
            return True
        logger.error("API credentials validation failed. Check keys, secret, and testnet setting.")
        return False

    def start_websockets(self):
        """Start public and private WebSocket streams."""
        logger.info(f"Starting public orderbook stream for {SYMBOL}...")
        self.ws_public.orderbook_stream(symbol=SYMBOL, depth=1, callback=on_public_ws_message)
        logger.info("Starting private order and position streams...")
        self.ws_private.order_stream(callback=on_private_ws_message)
        self.ws_private.position_stream(callback=on_private_ws_message)
        logger.info("WebSocket streams initiated.")

    async def get_balance(self) -> Decimal:
        """Fetch available balance for USDT."""
        response = await self._api(self.http.get_wallet_balance, accountType="UNIFIED", coin="USDT")
        if response and response.get('retCode') == 0:
            try:
                # Navigate the response structure carefully
                balance_list = response.get("result", {}).get("list", [])
                if balance_list:
                    coin_info = balance_list[0].get("coin", [{}])[0]
                    balance_str = coin_info.get("availableToWithdraw", "0")
                    balance = Decimal(balance_str)
                    self.current_balance = balance
                    ws_state["available_balance"] = balance # Update shared state
                    ws_state["last_balance_update"] = time.time()
                    return balance
                logger.warning("Balance response structure unexpected or empty.")
                return Decimal("0")
            except (KeyError, IndexError, ValueError, DecimalException, TypeError) as e:
                logger.error(f"Error parsing balance response: {type(e).__name__} - {e}")
                return Decimal("0")
        logger.error("Failed to fetch balance.")
        return Decimal("0")

    async def get_open_orders_rest(self) -> dict[str, Any]:
        """Sync open orders from REST API."""
        response = await self._api(
            self.http.get_open_orders,
            category=CATEGORY,
            symbol=SYMBOL
        )
        if response and response.get('retCode') == 0:
            orders_data = response.get("result", {}).get("list", [])
            current_open_orders = {}
            for order in orders_data:
                try:
                    oid = order.get("orderId")
                    if not oid: continue
                    current_open_orders[oid] = {
                        "client_order_id": order.get("orderLinkId", "N/A"),
                        "symbol": order.get("symbol"),
                        "side": order.get("side"),
                        "price": Decimal(order.get("price", "0")),
                        "qty": Decimal(order.get("qty", "0")),
                        "status": order.get("orderStatus"),
                        "timestamp": float(order.get("createdTime", 0)) / 1000,
                    }
                except (KeyError, ValueError, DecimalException, TypeError) as e:
                    logger.error(f"Error processing REST order data: {type(e).__name__} - {e} | Order: {order}")

            ws_state["open_orders"] = current_open_orders
            logger.debug(f"REST sync: Found {len(current_open_orders)} open orders.")
            return current_open_orders
        logger.error("Failed to fetch open orders via REST.")
        return {}

    async def get_positions_rest(self) -> dict[str, Any]:
        """Sync positions from REST API."""
        response = await self._api(
            self.http.get_positions,
            category=CATEGORY,
            symbol=SYMBOL
        )
        if response and response.get('retCode') == 0:
            positions_data = response.get("result", {}).get("list", [])
            current_positions = {}
            for pos in positions_data:
                try:
                    if pos.get("symbol") == SYMBOL and Decimal(pos.get("size", "0")) > Decimal("0"):
                        side = "Long" if pos.get("side") == "Buy" else "Short"
                        current_positions[side] = {
                            "size": Decimal(pos.get("size", "0")),
                            "avg_price": Decimal(pos.get("avgPrice", "0")),
                            "unrealisedPnl": Decimal(pos.get("unrealisedPnl", "0")),
                        }
                except (KeyError, ValueError, DecimalException, TypeError) as e:
                    logger.error(f"Error processing REST position data: {type(e).__name__} - {e} | Position: {pos}")

            ws_state["positions"] = current_positions
            logger.debug(f"REST sync: Found {len(current_positions)} active positions.")
            return current_positions
        logger.error("Failed to fetch positions via REST.")
        return {}

    async def place_order(self, side: str, qty: Decimal, price: Decimal | None = None, client_order_id: str | None = None, order_type: str = "Limit") -> dict[str, Any] | None:
        """Place a single order, applying quantization and minimum checks."""
        if order_type == "Limit" and price is None:
            logger.error("Price must be specified for a Limit order.")
            return None
        if order_type == "Market" and price is not None:
            logger.warning("Price specified for Market order will be ignored.")
            price = None # Ensure price is None for market orders

        # Validate quantity against precision and minimums
        try:
            quantized_qty = qty.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            if quantized_qty <= Decimal("0"):
                logger.error(f"Order quantity {qty} results in zero or negative after quantization ({quantized_qty}).")
                return None
            if quantized_qty < symbol_info.get("min_qty", Decimal("0")) and symbol_info.get("min_qty", Decimal("0")) > 0:
                 logger.error(f"Order quantity {quantized_qty} is below minimum required quantity ({symbol_info['min_qty']}).")
                 return None
        except DecimalException as e:
            logger.error(f"Error quantizing quantity {qty}: {e}")
            return None

        # Quantize price based on side for better fill probability
        quantized_price = None
        if price is not None:
            try:
                rounding_method = ROUND_DOWN if side == "Buy" else ROUND_UP
                quantized_price = price.quantize(symbol_info["price_precision"], rounding=rounding_method)

                # Check against minimum price
                if symbol_info.get("min_price", Decimal("0")) > 0 and quantized_price < symbol_info["min_price"]:
                    logger.error(f"Order price {quantized_price} is below minimum required price ({symbol_info['min_price']}).")
                    return None
            except DecimalException as e:
                logger.error(f"Error quantizing price {price}: {e}")
                return None

        # Check minimum order value
        if quantized_price and quantized_qty and symbol_info.get("min_order_value", Decimal("0")) > 0:
            order_value = quantized_qty * quantized_price
            if order_value < symbol_info["min_order_value"]:
                logger.error(f"Calculated order value ({order_value:.2f}) is below minimum order value ({symbol_info['min_order_value']:.2f}).")
                return None

        payload = {
            "category": CATEGORY,
            "symbol": SYMBOL,
            "side": side,
            "orderType": order_type,
            "qty": str(quantized_qty),
            "positionIdx": 1 if side == "Buy" else 2  # 1 for Buy side, 2 for Sell side in Hedge Mode
        }
        if quantized_price:
            payload["price"] = str(quantized_price)
        if client_order_id:
            payload["orderLinkId"] = client_order_id
        if order_type == "Limit":
            payload["timeInForce"] = "GTC"  # Good Till Cancelled

        logger.debug(f"Placing Order Payload: {payload}")
        response = await self._api(self.http.place_order, **payload)

        if response and response.get('retCode') == 0:
            order_info = response['result']
            logger.info(f"Successfully placed {order_type} {side} order: ID={order_info.get('orderId', 'N/A')}, Qty={quantized_qty}, Price={quantized_price if quantized_price else 'N/A'}")
            return order_info
        else:
            logger.error(f"Failed to place {order_type} {side} order: {response.get('retMsg', 'Unknown error') if response else 'No response'}")
            return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific order."""
        response = await self._api(
            self.http.cancel_order,
            category=CATEGORY,
            symbol=SYMBOL,
            orderId=order_id
        )
        if response and response.get('retCode') == 0:
            logger.info(f"Successfully canceled order: {order_id}")
            # Remove from ws_state if successful, though WS callback should handle it
            ws_state["open_orders"].pop(order_id, None)
            return True
        else:
            logger.error(f"Failed to cancel order {order_id}: {response.get('retMsg', 'Unknown error') if response else 'No response'}")
            return False

    async def cancel_all_orders(self) -> None:
        """Cancel all open orders for the current symbol."""
        logger.warning(f"Attempting to cancel all open orders for {SYMBOL}...")
        response = await self._api(
            self.http.cancel_all_orders,
            category=CATEGORY,
            symbol=SYMBOL
        )
        if response and response.get('retCode') == 0:
            logger.info(f"Successfully canceled all open orders for {SYMBOL}.")
            ws_state["open_orders"].clear() # Clear state immediately
        else:
            logger.error(f"Failed to cancel all orders for {SYMBOL}: {response.get('retMsg', 'Unknown error') if response else 'No response'}")

    async def place_batch_orders(self, orders: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Place multiple orders in a single batch request, with quantization and validation."""
        if not orders:
            logger.warning("No orders provided for batch placement.")
            return None

        batch_payloads = []
        for order in orders:
            try:
                side = order.get("side")
                order_type = order.get("orderType", "Limit")
                qty = order.get("qty")
                price = order.get("price")
                client_order_id = order.get("client_order_id")

                if not side or not qty:
                    logger.warning(f"Skipping batch order due to missing side or quantity: {order}")
                    continue

                # Quantize quantity
                quantized_qty = qty.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
                if quantized_qty <= Decimal("0"):
                    logger.warning(f"Skipping batch order due to zero/negative quantized quantity: {quantized_qty}")
                    continue
                if symbol_info.get("min_qty", Decimal("0")) > 0 and quantized_qty < symbol_info["min_qty"]:
                    logger.warning(f"Skipping batch order: quantity {quantized_qty} below minimum {symbol_info['min_qty']}.")
                    continue

                # Quantize price
                quantized_price = None
                if price is not None:
                    rounding_method = ROUND_DOWN if side == "Buy" else ROUND_UP
                    quantized_price = price.quantize(symbol_info["price_precision"], rounding=rounding_method)
                    if symbol_info.get("min_price", Decimal("0")) > 0 and quantized_price < symbol_info["min_price"]:
                        logger.warning(f"Skipping batch order: price {quantized_price} below minimum {symbol_info['min_price']}.")
                        continue

                # Check minimum order value
                if quantized_price and quantized_qty and symbol_info.get("min_order_value", Decimal("0")) > 0:
                    order_value = quantized_qty * quantized_price
                    if order_value < symbol_info["min_order_value"]:
                        logger.warning(f"Skipping batch order: value {order_value:.2f} below minimum {symbol_info['min_order_value']:.2f}.")
                        continue

                order_payload = {
                    "symbol": SYMBOL,
                    "side": side,
                    "orderType": order_type,
                    "qty": str(quantized_qty),
                    "positionIdx": 1 if side == "Buy" else 2
                }
                if quantized_price:
                    order_payload["price"] = str(quantized_price)
                if client_order_id:
                    order_payload["orderLinkId"] = client_order_id
                if order_type == "Limit":
                    order_payload["timeInForce"] = order.get("timeInForce", "GTC")

                batch_payloads.append(order_payload)

            except (KeyError, ValueError, DecimalException, TypeError) as e:
                logger.error(f"Error preparing batch order {order}: {type(e).__name__} - {e}")
            except Exception as e:
                logger.error(f"Unexpected error preparing batch order {order}: {type(e).__name__} - {e}")

        if not batch_payloads:
            logger.warning("No valid orders to place in batch after preparation.")
            return None

        logger.debug(f"Placing Batch Order Payloads: {batch_payloads}")
        response = await self._api(self.http.place_batch_order, {"category": CATEGORY, "request": batch_payloads})

        if response and response.get('retCode') == 0:
            logger.info(f"Successfully placed {len(batch_payloads)} batch orders.")
            return response['result']
        else:
            logger.error(f"Failed to place batch orders: {response.get('retMsg', 'Unknown error') if response else 'No response'}")
            return None

# -----------------------------
# Market Making Strategy
# -----------------------------

class MarketMakingStrategy:
    def __init__(self, client: BybitClient):
        self.client = client
        self.running = False
        self.rebalance_task = None
        self.stop_loss_task = None
        self.exit_flag = asyncio.Event()
        self.last_mid_price_for_replacement = Decimal("0") # Tracks price for MM order replacement logic
        self.balance_update_interval = 30  # Update balance every 30 seconds

    def _is_market_data_fresh(self) -> bool:
        """Checks if the market data (bid/ask/mid) is considered fresh."""
        if ws_state["last_update_time"] == 0:
            return False # Never received data
        age = time.time() - ws_state["last_update_time"]
        if age > MAX_DATA_AGE_SECONDS:
            logger.warning(f"Market data is stale (age: {age:.1f}s > {MAX_DATA_AGE_SECONDS}s). Skipping operation.")
            return False
        return True

    async def place_market_making_orders(self):
        """Manages the placement of limit orders for market making."""
        mid = ws_state["mid_price"]
        bid = ws_state["best_bid"]
        ask = ws_state["best_ask"]

        # Check if market data is fresh and valid
        if not self._is_market_data_fresh() or not self._is_valid_price(mid, bid, ask):
            return

        # Detect significant price movement to re-align orders
        if self.last_mid_price_for_replacement > Decimal("0") and mid > Decimal("0"):
            try:
                price_change = abs(mid - self.last_mid_price_for_replacement) / self.last_mid_price_for_replacement
                if price_change >= PRICE_THRESHOLD:
                    logger.info(f"Price moved {price_change:.4%}, initiating order re-placement sequence.")
                    await self.client.cancel_all_orders() # Cancel existing MM orders
                    self.last_mid_price_for_replacement = mid # Update reference price
            except DecimalException:
                logger.warning("Decimal division error during price change calculation.")

        # Update order state from REST to ensure accuracy
        await self.client.get_open_orders_rest()

        # Cancel stale orders (orders placed long ago)
        await self._cancel_stale_orders()

        # If we have reached the maximum number of open MM orders, do nothing
        if len(ws_state["open_orders"]) >= MAX_OPEN_ORDERS:
            logger.debug(f"Max open orders ({MAX_OPEN_ORDERS}) reached. Skipping new MM orders.")
            return

        # Calculate desired MM bid and ask prices
        bid_price = mid * (Decimal("1") - SPREAD_PERCENTAGE)
        ask_price = mid * (Decimal("1") + SPREAD_PERCENTAGE)

        # Adjust prices to be within the current best bid/ask and quantized
        bid_price = min(bid_price.quantize(symbol_info["price_precision"], rounding=ROUND_DOWN), bid)
        ask_price = max(ask_price.quantize(symbol_info["price_precision"], rounding=ROUND_UP), ask)

        # Prepare orders to place
        orders_to_place = []

        # Add Buy order if no existing buy order and we have capacity
        if not any(o['side'] == 'Buy' for o in ws_state["open_orders"].values()) and len(ws_state["open_orders"]) < MAX_OPEN_ORDERS:
            client_buy_id = f"mmxcel-buy-{int(time.time() * 1000)}"
            orders_to_place.append({
                "side": "Buy",
                "qty": QUANTITY,
                "price": bid_price,
                "client_order_id": client_buy_id,
                "orderType": "Limit"
            })

        # Add Sell order if no existing sell order and we have capacity
        if not any(o['side'] == 'Sell' for o in ws_state["open_orders"].values()) and (len(ws_state["open_orders"]) + len(orders_to_place)) < MAX_OPEN_ORDERS:
            client_sell_id = f"mmxcel-sell-{int(time.time() * 1000)}"
            orders_to_place.append({
                "side": "Sell",
                "qty": QUANTITY,
                "price": ask_price,
                "client_order_id": client_sell_id,
                "orderType": "Limit"
            })

        if orders_to_place:
            await self.client.place_batch_orders(orders_to_place)
            # Update last reference price only after successfully placing orders
            self.last_mid_price_for_replacement = mid
        elif not ws_state["open_orders"]: # If no orders placed and no open orders (e.g., startup)
             self.last_mid_price_for_replacement = mid # Ensure it's set for future comparison

    async def _cancel_stale_orders(self):
        """Cancel orders that have exceeded their lifespan."""
        stale_order_ids = []
        for oid, data in list(ws_state["open_orders"].items()): # Use list to allow modification during iteration
            if time.time() - data.get("timestamp", 0) > ORDER_LIFESPAN_SECONDS:
                stale_order_ids.append(oid)

        if stale_order_ids:
            logger.info(f"Found {len(stale_order_ids)} stale orders. Cancelling them...")
            # Concurrently cancel stale orders
            tasks = [self.client.cancel_order(oid) for oid in stale_order_ids]
            await asyncio.gather(*tasks)

    def _is_valid_price(self, *prices) -> bool:
        """Check if prices are valid (non-zero, non-negative Decimals)."""
        for p in prices:
            if not isinstance(p, Decimal) or p <= Decimal("0"):
                return False
        return True

    async def rebalance_inventory(self):
        """Rebalance the position if it deviates from neutral beyond a threshold."""
        if not self._is_market_data_fresh():
            return

        long_size = ws_state['positions'].get('Long', {}).get('size', Decimal('0'))
        short_size = ws_state['positions'].get('Short', {}).get('size', Decimal('0'))
        net_position = long_size - short_size

        # Check if rebalancing is needed
        if abs(net_position) > REBALANCE_THRESHOLD_QTY:
            side_to_close = "Sell" if net_position > Decimal("0") else "Buy" # Close long if positive, close short if negative
            qty_to_rebalance = abs(net_position).quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)

            if qty_to_rebalance <= Decimal("0"):
                logger.warning("Rebalance quantity is zero after quantization. Skipping rebalance.")
                return

            logger.info(f"{YELLOW}Inventory imbalance detected: Net Position {net_position:.{_calculate_decimal_precision(symbol_info['qty_precision'])}f}. Rebalancing by closing {side_to_close} {qty_to_rebalance}.{NC}")
            send_toast(f"Rebalancing {qty_to_rebalance} {SYMBOL}!")

            # Place a market order to rebalance
            await self.client.place_order(side_to_close, qty_to_rebalance, order_type="Market", client_order_id=f"mmxcel-rebal-{int(time.time() * 1000)}")

    async def manage_stop_loss_and_profit_take(self):
        """Monitors open positions for stop-loss and profit-take triggers."""
        if not self._is_market_data_fresh():
            return

        mid_price = ws_state["mid_price"]

        for side in ["Long", "Short"]:
            pos = ws_state['positions'].get(side, {})
            size = pos.get('size', Decimal('0'))
            avg_price = pos.get('avg_price', Decimal('0'))
            unrealised_pnl = pos.get('unrealisedPnl', Decimal('0'))

            # Skip if position is invalid or zero
            if size <= Decimal("0") or avg_price <= Decimal("0"):
                continue

            # Calculate PnL percentage based on exchange's PnL figure
            pnl_percentage = Decimal("0")
            if abs(unrealised_pnl) > Decimal("0") and (avg_price * size) != Decimal("0"):
                 # Use direct PnL from exchange for percentage calculation
                 pnl_percentage = unrealised_pnl / (avg_price * size)

            quantized_size = size.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            if quantized_size <= Decimal("0"):
                logger.warning(f"Position size {size} for {side} resulted in zero quantized size. Skipping PnL management.")
                continue

            # Trigger Stop Loss
            if pnl_percentage < -STOP_LOSS_PERCENTAGE:
                logger.critical(f"{RED}Stop-loss triggered for {side} position! PnL: {unrealised_pnl:.2f} ({pnl_percentage:.2%}). Closing position.{NC}")
                send_toast(f"{side} SL triggered! PnL: {unrealised_pnl:.2f}")
                # Close position with a market order
                await self.client.place_order("Sell" if side == "Long" else "Buy", quantized_size, order_type="Market", client_order_id=f"mmxcel-sl-{side.lower()}-{int(time.time() * 1000)}")

            # Trigger Profit Take
            elif pnl_percentage >= PROFIT_PERCENTAGE:
                logger.info(f"{GREEN}Profit-take triggered for {side} position! PnL: {unrealised_pnl:.2f} ({pnl_percentage:.2%}). Closing position.{NC}")
                send_toast(f"{side} TP triggered! PnL: {unrealised_pnl:.2f}")
                # Close position with a market order
                await self.client.place_order("Sell" if side == "Long" else "Buy", quantized_size, order_type="Market", client_order_id=f"mmxcel-tp-{side.lower()}-{int(time.time() * 1000)}")

    async def shutdown(self):
        """Gracefully shut down the bot, cancelling all open orders."""
        if self.running:
            self.running = False
            logger.info("Initiating graceful shutdown...")
            send_toast("MMXCEL: Shutting down...", "#FFA500")

            # Cancel all open orders
            await self.client.cancel_all_orders()

            # Cancel background tasks if they are still running
            if self.rebalance_task and not self.rebalance_task.done():
                self.rebalance_task.cancel()
                try: await self.rebalance_task # Wait for cancellation
                except asyncio.CancelledError: pass
            if self.stop_loss_task and not self.stop_loss_task.done():
                self.stop_loss_task.cancel()
                try: await self.stop_loss_task # Wait for cancellation
                except asyncio.CancelledError: pass

            self.exit_flag.set() # Signal shutdown is complete
            logger.info("All open orders cancelled and background tasks stopped.")
            send_toast("MMXCEL: Shutdown complete.", "green")

    async def run(self):
        """Main event loop for the market-making strategy."""
        self.running = True

        # Validate configuration settings against defaults and basic logic
        if not self._validate_config():
            logger.critical("Configuration validation failed. Aborting startup.")
            send_toast("MMXCEL Config Error!", "red")
            return

        # Fetch critical symbol information first
        if not await self.client.get_symbol_info():
            logger.critical("Failed to fetch symbol information. Cannot proceed without it.")
            send_toast("MMXCEL Error: Symbol Info Failed!", "red")
            return

        # Re-validate config against fetched symbol info
        if not self._validate_config_against_symbol_info():
             logger.critical("Configuration validation failed against symbol info. Aborting startup.")
             send_toast("MMXCEL Config Error (Symbol Info)!", "red")
             return

        # Set trading mode to Hedge Mode
        logger.info(f"Setting trading mode to Hedge Mode (for category: {CATEGORY})...")
        try:
            # Use set_position_mode for Hedge Mode
            response = await self.client._api(self.client.http.set_position_mode, hedgeMode=True) # category is often implied or default is linear
            if response and response.get('retCode') == 0:
                logger.info("Trading preference set to Hedge Mode successfully.")
            else:
                logger.warning(f"Failed to set trading preference to Hedge Mode: {response.get('retMsg', 'Unknown error')}. This might be expected if already set or an API issue. Ensure HedgeMode is enabled in Bybit settings. Proceeding...")
        except Exception as e:
            logger.warning(f"Error setting trading preference: {type(e).__name__} - {e}. Ensure HedgeMode is enabled in Bybit settings. Proceeding...")

        # Start WebSocket streams
        self.client.start_websockets()

        # Initial synchronization of state
        logger.info("Synchronizing initial account state...")
        await self.client.get_balance() # Fetches and updates ws_state["available_balance"]
        await self.client.get_open_orders_rest() # Populates ws_state["open_orders"]
        await self.client.get_positions_rest() # Populates ws_state["positions"]

        # Allow WS a moment to establish connection and receive initial data
        await asyncio.sleep(5)

        # Start background tasks for recurring operations
        self.rebalance_task = asyncio.create_task(self._periodic_task(self.rebalance_inventory, 10, "RebalanceInventory"), name="rebalance_task")
        self.stop_loss_task = asyncio.create_task(self._periodic_task(self.manage_stop_loss_and_profit_take, 2, "PnLManagement"), name="pnl_task")

        logger.info(f"MMXCEL Bot started successfully for {SYMBOL}.")
        send_toast(f"MMXCEL started for {SYMBOL}!")

        # Main loop execution
        try:
            while self.running:
                self._display_status() # Update terminal display

                # Perform market making logic
                await self.place_market_making_orders()

                # Update balance periodically for display
                if time.time() - ws_state["last_balance_update"] > self.balance_update_interval:
                    await self.client.get_balance()

                # Wait for the next iteration
                await asyncio.sleep(ORDER_REFRESH_INTERVAL)

        except asyncio.CancelledError:
            logger.info("Main strategy loop cancelled.")
        except Exception as e:
            logger.critical(f"An unhandled critical error occurred in the main loop: {type(e).__name__} - {e}", exc_info=True)
            send_toast("MMXCEL CRITICAL ERROR! Check logs.", "red")
        finally:
            # Ensure shutdown is called even if errors occur or task is cancelled
            await self.shutdown()

    async def _periodic_task(self, func, interval: int, task_name: str):
        """Helper function to run a coroutine periodically."""
        try:
            while self.running:
                await func()
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info(f"Periodic task '{task_name}' was cancelled.")
        except Exception as e:
            logger.error(f"Error in periodic task '{task_name}': {type(e).__name__} - {e}", exc_info=True)
            send_toast(f"MMXCEL Error: {task_name} failed!", "orange")

    def _validate_config(self) -> bool:
        """Basic validation of config values against common sense and types."""
        is_valid = True

        checks = [
            (isinstance(QUANTITY, Decimal) and Decimal("0") < QUANTITY, "QUANTITY must be a positive Decimal"),
            (isinstance(SPREAD_PERCENTAGE, Decimal) and Decimal("0") < SPREAD_PERCENTAGE, "SPREAD_PERCENTAGE must be a positive Decimal"),
            (isinstance(PROFIT_PERCENTAGE, Decimal) and Decimal("0") < PROFIT_PERCENTAGE, "PROFIT_PERCENTAGE must be a positive Decimal"),
            (isinstance(STOP_LOSS_PERCENTAGE, Decimal) and Decimal("0") < STOP_LOSS_PERCENTAGE, "STOP_LOSS_PERCENTAGE must be a positive Decimal"),
            (isinstance(MAX_OPEN_ORDERS, int) and MAX_OPEN_ORDERS > 0, "MAX_OPEN_ORDERS must be a positive integer"),
            (isinstance(ORDER_LIFESPAN_SECONDS, int) and ORDER_LIFESPAN_SECONDS > 0, "ORDER_LIFESPAN_SECONDS must be a positive integer"),
            (isinstance(REBALANCE_THRESHOLD_QTY, Decimal) and Decimal("0") <= REBALANCE_THRESHOLD_QTY, "REBALANCE_THRESHOLD_QTY must be a non-negative Decimal"),
            (isinstance(PRICE_THRESHOLD, Decimal) and Decimal("0") <= PRICE_THRESHOLD, "PRICE_THRESHOLD must be a non-negative Decimal"),
            (isinstance(ORDER_REFRESH_INTERVAL, int) and ORDER_REFRESH_INTERVAL > 0, "ORDER_REFRESH_INTERVAL must be a positive integer"),
        ]

        for check, msg in checks:
            if not check:
                logger.critical(f"Config Error: {msg}")
                is_valid = False

        # Warning for potentially problematic settings
        if SPREAD_PERCENTAGE >= PRICE_THRESHOLD and Decimal("0") < PRICE_THRESHOLD:
            logger.warning(f"{YELLOW}Warning: SPREAD_PERCENTAGE ({SPREAD_PERCENTAGE:.4%}) is greater than or equal to PRICE_THRESHOLD ({PRICE_THRESHOLD:.4%}). "
                           "This may lead to frequent order re-placements.{NC}")

        return is_valid

    def _validate_config_against_symbol_info(self) -> bool:
        """Validates configuration against fetched symbol specifics like min quantities."""
        is_valid = True

        # Validate QUANTITY against symbol's minimum quantity and precision
        try:
            quantized_config_qty = QUANTITY.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            if quantized_config_qty <= Decimal("0"):
                logger.critical(f"Config Error: QUANTITY ({QUANTITY}) results in zero or negative after quantization ({quantized_config_qty}).")
                is_valid = False
            elif symbol_info.get("min_qty", Decimal("0")) > Decimal("0") and quantized_config_qty < symbol_info["min_qty"]:
                 logger.critical(f"Config Error: QUANTITY ({QUANTITY}, quantized to {quantized_config_qty}) is below the symbol's minimum trade quantity ({symbol_info['min_qty']}).")
                 is_valid = False

            # Check if QUANTITY multiplied by a reasonable price (e.g., mid-price or min-price) exceeds min order value
            # Using a placeholder price for this check as mid_price might not be available yet, or could be 0
            # Use min_price from symbol info as a safer lower bound for this check.
            min_price_check = symbol_info.get("min_price", Decimal("1")) # Default to 1 if not found
            if min_price_check <= Decimal("0"): min_price_check = Decimal("1") # Ensure it's positive

            min_order_val_check = quantized_config_qty * min_price_check
            if symbol_info.get("min_order_value", Decimal("0")) > Decimal("0") and min_order_val_check < symbol_info["min_order_value"]:
                logger.critical(f"Config Error: QUANTITY ({QUANTITY}) multiplied by minimum price ({min_price_check}) results in an order value ({min_order_val_check:.2f}) potentially below the symbol's minimum order value ({symbol_info['min_order_value']:.2f}). Adjust QUANTITY or check symbol specs.")
                is_valid = False

        except DecimalException as e:
            logger.critical(f"Config Validation Error: Decimal issue with QUANTITY or symbol info: {e}")
            is_valid = False

        return is_valid

    def _display_status(self):
        """Clears screen and displays current bot status, config, and market data."""
        clear_screen()
        print_neon_header(f"MMXCEL Bybit Market Maker - {SYMBOL}", color=MAGENTA)
        print_neon_separator()

        # Display Configuration
        print(f"{BOLD}{CYAN}--- Configuration ---{NC}")
        price_disp_prec = _calculate_decimal_precision(symbol_info["price_precision"])
        qty_disp_prec = _calculate_decimal_precision(symbol_info["qty_precision"])

        print(format_metric("Symbol", SYMBOL, YELLOW, WHITE))
        print(format_metric("Order Qty", QUANTITY, YELLOW, value_precision=qty_disp_prec))
        print(format_metric("Spread %", SPREAD_PERCENTAGE * 100, YELLOW, value_precision=4))
        print(format_metric("Max Open Orders", MAX_OPEN_ORDERS, YELLOW))
        print(format_metric("Order Lifespan (s)", ORDER_LIFESPAN_SECONDS, YELLOW))
        print(format_metric("Rebalance Threshold", REBALANCE_THRESHOLD_QTY, YELLOW, value_precision=qty_disp_prec))
        print(format_metric("Profit Take %", PROFIT_PERCENTAGE * 100, YELLOW))
        print(format_metric("Stop Loss %", STOP_LOSS_PERCENTAGE * 100, YELLOW))
        print(format_metric("Price Threshold %", PRICE_THRESHOLD * 100, YELLOW))
        print(format_metric("Refresh Interval (s)", ORDER_REFRESH_INTERVAL, YELLOW))
        print(format_metric("Testnet Enabled", USE_TESTNET, YELLOW))
        print(format_metric("Price Precision", symbol_info["price_precision"], YELLOW, value_precision=price_disp_prec))
        print(format_metric("Qty Precision", symbol_info["qty_precision"], YELLOW, value_precision=qty_disp_prec))
        print(format_metric("Min Trade Qty", symbol_info.get("min_qty", "N/A"), YELLOW, value_precision=qty_disp_prec if symbol_info.get("min_qty", Decimal("0")) > 0 else None))
        print(format_metric("Min Order Value", symbol_info.get("min_order_value", "N/A"), YELLOW, value_precision=2 if symbol_info.get("min_order_value", Decimal("0")) > 0 else None))
        print_neon_separator()

        # Display Market and Account Status
        print(f"{BOLD}{CYAN}--- Market & Account ---{NC}")
        market_data_fresh = self._is_market_data_fresh()
        data_freshness_color = GREEN if market_data_fresh else RED
        print(format_metric("Market Data Fresh", market_data_fresh, YELLOW, data_freshness_color))

        if market_data_fresh:
            print(format_metric("Mid Price", ws_state['mid_price'], BLUE, value_precision=price_disp_prec))
            print(format_metric("Best Bid", ws_state['best_bid'], GREEN, value_precision=price_disp_prec))
            print(format_metric("Best Ask", ws_state['best_ask'], RED, value_precision=price_disp_prec))
        else:
            print(format_metric("Mid Price", "N/A", BLUE))
            print(format_metric("Best Bid", "N/A", GREEN))
            print(format_metric("Best Ask", "N/A", RED))

        print(format_metric("Available Balance (USDT)", self.client.current_balance, YELLOW, value_precision=2))
        print_neon_separator()

        # Display Positions
        print(f"{BOLD}{CYAN}--- Positions ({SYMBOL}) ---{NC}")
        long_pos = ws_state['positions'].get('Long', {'size': Decimal('0'), 'unrealisedPnl': Decimal('0')})
        short_pos = ws_state['positions'].get('Short', {'size': Decimal('0'), 'unrealisedPnl': Decimal('0')})

        print(format_metric("Long Position", long_pos['size'], GREEN, value_precision=qty_disp_prec))
        print(format_metric("Unrealized PnL (Long)", long_pos['unrealisedPnl'], GREEN, is_pnl=True, value_precision=2))
        print(format_metric("Short Position", short_pos['size'], RED, value_precision=qty_disp_prec))
        print(format_metric("Unrealized PnL (Short)", short_pos['unrealisedPnl'], RED, is_pnl=True, value_precision=2))
        print_neon_separator()

        # Display Open Orders
        print(f"{BOLD}{CYAN}--- Open Orders ({len(ws_state['open_orders'])}) ---{NC}")
        if ws_state["open_orders"]:
            # Sort orders by timestamp for consistent display
            sorted_orders = sorted(list(ws_state["open_orders"].values()), key=lambda x: x.get('timestamp', 0))
            for order in sorted_orders:
                color = GREEN if order.get('side') == 'Buy' else RED
                client_id = order.get('client_order_id', 'N/A')
                # Ensure price/qty are accessible and format them
                price_val = order.get('price', Decimal('0'))
                qty_val = order.get('qty', Decimal('0'))
                print(f"  [{color}{order.get('side', 'N/A')}{NC}] @ {price_val:.{price_disp_prec}f} Qty: {qty_val:.{qty_disp_prec}f} (ID: {order.get('status', 'N/A')}, Client: {client_id})")
        else:
            print(f"  {YELLOW}No open orders detected.{NC}")
        print_neon_separator()

# -----------------------------
# Signal Handling and Main Execution
# -----------------------------

def signal_handler(sig, frame):
    """Handle termination signals (SIGINT, SIGTERM) for graceful shutdown."""
    logger.warning(f"Received termination signal ({sig}). Initiating graceful shutdown...")
    loop = asyncio.get_event_loop()

    # Find the main strategy task and cancel it
    main_task = None
    for task in asyncio.all_tasks(loop):
        if task.get_name() == 'strategy_task':
            main_task = task
            break

    if main_task:
        main_task.cancel()
        # Schedule the shutdown coroutine to run on the loop after main task is cancelled
        asyncio.create_task(asyncio.get_event_loop().create_task(strategy.shutdown()))
    else:
        # If main task isn't running or found, attempt direct shutdown if possible
        if loop.is_running():
             asyncio.create_task(asyncio.get_event_loop().create_task(strategy.shutdown()))
        else: # If loop not running, just exit (likely very early termination)
             sys.exit(0) # Exit cleanly if loop isn't set up yet.

async def main():
    """Main entry point for the MMXCEL bot."""
    global _HAS_TERMUX_TOAST_CMD, strategy # Make strategy accessible for signal handler

    # Check for essential configuration first
    if not API_KEY or not API_SECRET:
        print(f"{RED}ERROR: BYBIT_API_KEY or BYBIT_API_SECRET not found in .env file.{NC}")
        sys.exit(1)

    # Check for termux-toast availability early
    _HAS_TERMUX_TOAST_CMD = check_termux_toast()
    if not _HAS_TERMUX_TOAST_CMD:
        logger.warning("Termux:API command 'termux-toast' not found. Toasts will be disabled. Please install 'termux-api' package and app.")

    send_toast("MMXCEL: Starting bot...", "#336699")

    client = BybitClient(API_KEY, API_SECRET, USE_TESTNET)
    strategy = MarketMakingStrategy(client) # Initialize strategy instance

    # 1. Test API Credentials
    if not await client.test_credentials():
        send_toast("MMXCEL Auth Failed!", "red")
        sys.exit(1) # Exit if credentials are invalid

    # 2. Set Trading Mode (Hedge Mode)
    logger.info(f"Setting trading mode to Hedge Mode for category: {CATEGORY}...")
    try:
        # Use set_position_mode which is the correct method in pybit v2.0+ for hedge mode
        response = await client._api(client.http.set_position_mode, hedgeMode=True)
        if response and response.get('retCode') == 0:
            logger.info("Trading preference set to Hedge Mode successfully.")
        else:
            logger.warning(f"Failed to set trading preference: {response.get('retMsg', 'Unknown error')}. Ensure HedgeMode is enabled in Bybit account settings. Proceeding...")
    except Exception as e:
        logger.warning(f"Error setting trading preference: {type(e).__name__} - {e}. Ensure HedgeMode is enabled in Bybit settings. Proceeding...")

    # 3. Fetch Symbol Information (Crucial for precision)
    if not await client.get_symbol_info():
        send_toast("MMXCEL Error: Symbol Info Failed!", "red")
        sys.exit(1)

    # 4. Validate Configuration against fetched Symbol Info
    if not strategy._validate_config_against_symbol_info():
        send_toast("MMXCEL Config Error (vs Symbol)!", "red")
        sys.exit(1)

    # 5. Start WebSocket Streams
    client.start_websockets()

    # 6. Initial State Synchronization (Balance, Orders, Positions)
    logger.info("Performing initial state synchronization...")
    await client.get_balance()
    await client.get_open_orders_rest()
    await client.get_positions_rest()

    # Allow WS a moment to connect and establish channels
    await asyncio.sleep(5)

    # 7. Start Background Tasks
    strategy.rebalance_task = asyncio.create_task(strategy._periodic_task(strategy.rebalance_inventory, 10, "RebalanceInventory"), name="rebalance_task")
    strategy.stop_loss_task = asyncio.create_task(strategy._periodic_task(strategy.manage_stop_loss_and_profit_take, 2, "PnLManagement"), name="pnl_task")

    logger.info(f"MMXCEL Bot initialized and running for {SYMBOL}.")
    send_toast(f"MMXCEL running for {SYMBOL}!")

    # 8. Register Signal Handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler) # Handle termination signals

    # 9. Run the main strategy loop
    main_strategy_task = asyncio.create_task(strategy.run(), name='strategy_task')

    try:
        await main_strategy_task # Wait for the strategy to finish or be cancelled
    except asyncio.CancelledError:
        logger.info("Main strategy task was cancelled.")
    except Exception as e:
        logger.critical(f"Critical error in main execution block: {type(e).__name__} - {e}", exc_info=True)
    finally:
        # Ensure shutdown is always called
        if strategy.running: # Check if shutdown hasn't already been called by signal handler
            await strategy.shutdown()
        logger.info("MMXCEL Bot has shut down. Goodbye!")

if __name__ == '__main__':
    # Ensure the global strategy object is defined before main() is called,
    # so signal_handler can access it.
    strategy = None # Define it here, it will be assigned in main()
    asyncio.run(main())
