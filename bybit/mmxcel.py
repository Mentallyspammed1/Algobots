import os
import asyncio
import logging.handlers # Import handlers module
import time
import json
import signal
from decimal import Decimal, getcontext, ROUND_DOWN, ROUND_UP, ROUND_HALF_UP
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket
from colorama import Fore, Style, init
from typing import Optional, Dict, Any, List, Tuple
import math
import platform
import sys
from datetime import datetime
import psutil # The eye that sees the system's soul

# Initialize Colorama for beautiful terminal output
init(autoreset=True)

# Set decimal precision for financial calculations
getcontext().prec = 10

# --- ANSI Colors for Enhanced Neon Output ---
NC = Style.RESET_ALL      # No Color - Resets all styling
BOLD = Style.BRIGHT       # Bold font
RED = Fore.RED            # Red foreground
GREEN = Fore.GREEN        # Green foreground
YELLOW = Fore.YELLOW      # Yellow foreground
BLUE = Fore.BLUE          # Blue foreground
MAGENTA = Fore.MAGENTA    # Magenta foreground
CYAN = Fore.CYAN         # Cyan foreground
WHITE = Fore.WHITE       # White foreground
UNDERLINE = Style.BRIGHT + Fore.CYAN # Bright Cyan for headers

# --- Configuration & Logging Setup ---
# Channeling secrets from the ethereal .env file
load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

# Casting the config.json into existence to draw trading parameters
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    print(f"{RED}config.json not found in the current realm. Please forge it with your trading parameters.{NC}")
    os.system(f"termux-toast -b red -c white 'MMXCEL Error: config.json missing!'")
    exit()
except json.JSONDecodeError:
    print(f"{RED}A distortion detected in config.json. Please verify its crystalline structure (JSON format).{NC}")
    os.system(f"termux-toast -b red -c white 'MMXCEL Error: config.json corrupt!'")
    exit()

# Set up logging with rotation to prevent log files from growing too large
LOG_FILE = 'mmxcel.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(), # Echoes to the console
        logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1024*1024, backupCount=3) # 1MB max, keep 3 backups
    ]
)
logger = logging.getLogger(__name__)

# Extracting trading parameters from the Tome of Config
SYMBOL = config.get("SYMBOL", "BTCUSDT")
CATEGORY = config.get("CATEGORY", "linear")
QUANTITY = Decimal(str(config.get("QUANTITY", "0.001")))
SPREAD_PERCENTAGE = Decimal(str(config.get("SPREAD_PERCENTAGE", "0.0005")))
ORDER_COUNT = config.get("ORDER_COUNT", 1) # Retained for potential future use
MAX_OPEN_ORDERS = config.get("MAX_OPEN_ORDERS", 2)
ORDER_LIFESPAN_SECONDS = config.get("ORDER_LIFESPAN_SECONDS", 30)
REBALANCE_THRESHOLD_QTY = Decimal(str(config.get("REBALANCE_THRESHOLD_QTY", "0.0001")))
PROFIT_PERCENTAGE = Decimal(str(config.get("PROFIT_PERCENTAGE", "0.001")))
STOP_LOSS_PERCENTAGE = Decimal(str(config.get("STOP_LOSS_PERCENTAGE", "0.005")))
PRICE_THRESHOLD = Decimal(str(config.get("PRICE_THRESHOLD", "0.0002"))) # 0.02% price movement to trigger re-placement
USE_TESTNET = config.get("USE_TESTNET", True)
POSITION_MODE = "HedgeMode" # For linear/inverse, HedgeMode is required for separate long/short positions
ORDER_REFRESH_INTERVAL = config.get("ORDER_REFRESH_INTERVAL", 5) # How often to check for order refreshes in seconds
MIN_ORDER_REFRESH_INTERVAL = 1 # Minimum time between order refreshes to prevent API spam
MAX_ORDER_REFRESH_INTERVAL = 60 # Maximum time between order refreshes to prevent stale orders
MEMORY_CLEANUP_INTERVAL = config.get("MEMORY_CLEANUP_INTERVAL", 300) # Interval for garbage collection
ORDERBOOK_DEPTH_LEVELS = config.get("ORDERBOOK_DEPTH_LEVELS", 50) # Orderbook depth

# --- Global Symbol Info Placeholder (to be fetched from exchange) ---
# This will store dynamic precision values crucial for accurate trading.
symbol_info = {
    "price_precision": Decimal("0.0001"), # Default, will be updated by get_symbol_info
    "qty_precision": Decimal("0.001")     # Default, will be updated by get_symbol_info
}

# Helper function to get precision from a Decimal value for display
def _calculate_decimal_precision(value: Decimal) -> int:
    """Calculates the number of decimal places of a Decimal value.
    This is for display formatting, not for exchange-specific precision."""
    s = str(value.normalize())
    if '.' in s:
        return len(s.split('.')[1])
    return 0

# --- Neon UI Helper Functions ---
def clear_screen() -> None:
    """Clears the terminal screen using ANSI escape codes, a quick vanishing spell."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_neon_header(text: str, color: str = UNDERLINE, length: int = 80) -> None:
    """Prints a centered header with a neon-like border, illuminating the command center."""
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
    """Prints a separator line, dividing the insights into clear segments."""
    print(f"{color}{char * length}{NC}")

def format_metric(
    label: str,
    value: Any,
    label_color: str,
    value_color: Optional[str] = None,
    label_width: int = 25,
    value_precision: Optional[int] = None, # Make optional, use _calculate_decimal_precision if None
    unit: str = "",
    is_pnl: bool = False,
) -> str:
    """Formats a label and its value for neon display, giving form to raw data."""
    formatted_label = f"{label_color}{label:<{label_width}}{NC}"
    actual_value_color = value_color if value_color else label_color
    formatted_value = ""

    if isinstance(value, (Decimal, float)):
        if value_precision is None:
            # Determine precision dynamically for Decimals if not specified
            current_precision = _calculate_decimal_precision(Decimal(str(value)))
        else:
            current_precision = value_precision

        if is_pnl:
            actual_value_color = GREEN if value >= 0 else RED
            sign = "+" if value > 0 else ""
            formatted_value = f"{actual_value_color}{sign}{value:,.{current_precision}f}{unit}{NC}"
        else:
            formatted_value = f"{actual_value_color}{value:,.{current_precision}f}{unit}{NC}"
    elif isinstance(value, int):
        if is_pnl:
            actual_value_color = GREEN if value >= 0 else RED
            sign = "+" if value > 0 else ""
            formatted_value = f"{actual_value_color}{sign}{value:,}{unit}{NC}"
        else:
            formatted_value = f"{actual_value_color}{value:,}{unit}{NC}"
    else:
        formatted_value = f"{actual_value_color}{str(value)}{unit}{NC}"
    return f"{formatted_label}: {formatted_value}"

def format_order(order: Dict[str, Any], price_precision: int, qty_precision: int) -> str:
    """Formats an order for display in the UI."""
    side_color = GREEN if order['side'] == 'Buy' else RED
    client_id = order.get('client_order_id', 'N/A')
    return f"  [{side_color}{order['side']}{NC}] @ {order['price']:.{price_precision}f} Qty: {order['qty']:.{qty_precision}f} (Client ID: {client_id})"

def format_position(position: Dict[str, Any], side: str, price_precision: int, qty_precision: int) -> str:
    """Formats a position for display in the UI."""
    side_color = GREEN if side == 'Long' else RED
    return f"  {side_color}{side}{NC} Position: {position['size']:.{qty_precision}f} @ {position['avg_price']:.{price_precision}f} | Unrealized PnL: {position['unrealisedPnl']:.2f} USDT"

# --- WebSocket Listener ---
# Shared state for WebSocket updates, a crystal ball reflecting market reality
ws_state = {
    "mid_price": Decimal("0"),
    "best_bid": Decimal("0"),
    "best_ask": Decimal("0"),
    "open_orders": {},
    "positions": {}, # Stores 'Long' and 'Short' positions
    "last_update_time": 0,
    "system_stats": {
        "cpu_usage": 0.0,
        "memory_usage": 0.0,
        "network_io": (0, 0) # bytes_sent, bytes_recv
    }
}

def on_public_ws_message(message: Dict[str, Any]):
    """Callback for public websocket messages (orderbook), whispering market depth."""
    try:
        data = message.get('data', {})
        # Assuming orderbook stream 'orderbook.1'
        if message.get('topic') == f'orderbook.1.{SYMBOL}':
            if data.get('b') and data.get('a'):
                best_bid_price = Decimal(data['b'][0][0])
                best_ask_price = Decimal(data['a'][0][0])
                ws_state["best_bid"] = best_bid_price
                ws_state["best_ask"] = best_ask_price
                ws_state["mid_price"] = (best_bid_price + best_ask_price) / Decimal("2")
                ws_state["last_update_time"] = time.time()
                logger.debug(f"WS Orderbook: Mid Price: {ws_state['mid_price']:.4f}")
    except (KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError) as e:
        logger.error(f"Error processing public WS message: {type(e).__name__} - {e} | Message: {message}")

def on_private_ws_message(message: Dict[str, Any]):
    """Callback for private websocket messages (orders, positions), revealing personal arcane dealings."""
    try:
        topic = message.get('topic')
        if topic == 'order':
            for order_update in message.get('data', []):
                order_id = order_update.get('orderId')
                if not order_id:
                    continue
                # Update order status or remove if filled/canceled/deactivated
                if order_update['orderStatus'] in ['Filled', 'Canceled', 'Deactivated']:
                    if order_id in ws_state["open_orders"]:
                        logger.info(f"WS Order Update: Order {order_id} (Client ID: {order_update.get('orderLinkId')}) is {order_update['orderStatus']}.")
                        del ws_state["open_orders"][order_id]
                else:
                    ws_state["open_orders"][order_id] = {
                        "client_order_id": order_update.get('orderLinkId', 'N/A'),
                        "symbol": order_update['symbol'],
                        "side": order_update['side'],
                        "price": Decimal(order_update['price']),
                        "qty": Decimal(order_update['qty']),
                        "status": order_update['orderStatus'],
                        "timestamp": float(order_update['createdTime']) / 1000
                    }
        elif topic == 'position':
            for position_update in message.get('data', []):
                # We are in HedgeMode, so we have separate long and short positions
                if position_update.get('symbol') == SYMBOL:
                    side = 'Long' if position_update.get('side') == 'Buy' else 'Short'
                    ws_state['positions'][side] = {
                        'size': Decimal(position_update.get('size', '0')),
                        'avg_price': Decimal(position_update.get('avgPrice', '0')),
                        'unrealisedPnl': Decimal(position_update.get('unrealisedPnl', '0'))
                    }
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
        logger.error(f"Error processing private WS message: {type(e).__name__} - {e} | Message: {message}")

class BybitClient:
    """The Grand Conjuror, interacting with the Bybit exchange."""
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 2 # Initial delay, will double on each retry

    def __init__(self, api_key: str, api_secret: str, testnet: bool):
        self.http_session = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret)
        self.ws_public = WebSocket(testnet=testnet, channel_type="linear")
        self.ws_private = WebSocket(testnet=testnet, channel_type="private", api_key=api_key, api_secret=api_secret)
        self.current_balance = Decimal("0")
        self.last_api_call_time = 0
        self.api_call_cooldown = 0.1 # Minimum time between API calls to prevent rate limiting

    async def _make_api_call(self, api_method, *args, **kwargs):
        """Helper to make API calls with retry logic, navigating transient network ripples."""
        # Rate limiting protection
        current_time = time.time()
        if current_time - self.last_api_call_time < self.api_call_cooldown:
            await asyncio.sleep(self.api_call_cooldown - (current_time - self.last_api_call_time))

        self.last_api_call_time = current_time

        for attempt in range(self.MAX_RETRIES):
            try:
                response = api_method(*args, **kwargs)
                if response and response.get('retCode') == 0:
                    return response

                error_msg = response.get('retMsg', f"Unknown error (retCode: {response.get('retCode')})")
                logger.warning(f"API call failed (Attempt {attempt + 1}/{self.MAX_RETRIES}): {error_msg}")

                # Specific error codes that might warrant a retry (e.g., rate limits, internal server errors)
                # Bybit API codes for retrying: 10001 (System error), 10006 (Too many requests),
                # 30034 (Spot order placement failed), 30035 (Too many spot order requests)
                if response.get('retCode') in [10001, 10006, 30034, 30035]:
                    if attempt < self.MAX_RETRIES - 1:
                        delay = self.RETRY_DELAY_SECONDS * (2 ** attempt)
                        logger.warning(f"Retrying in {delay} seconds...")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"API call exhausted retries: {error_msg}")
                        return None
                else:
                    # For non-retryable errors (e.g., invalid parameters), don't retry
                    logger.error(f"Non-retryable API error: {error_msg}")
                    return None
            except Exception as e:
                logger.error(f"Exception during API call (Attempt {attempt + 1}/{self.MAX_RETRIES}): {type(e).__name__} - {e}")
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAY_SECONDS * (2 ** attempt)
                    logger.warning(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"API call exception exhausted retries: {type(e).__name__} - {e}")
                    return None
        return None # Should not be reached if MAX_RETRIES > 0

    async def get_symbol_info(self) -> bool:
        """Fetches the dynamic price and quantity precision for the symbol, adapting to market nuances."""
        response = await self._make_api_call(
            self.http_session.get_instruments_info,
            category=CATEGORY,
            symbol=SYMBOL
        )
        if response and response.get('retCode') == 0:
            instruments = response['result']['list']
            if instruments:
                instrument_info = instruments[0]
                price_filter = instrument_info.get('priceFilter', {})
                lot_size_filter = instrument_info.get('lotSizeFilter', {})

                # Extract tickSize (price_precision)
                tick_size_str = price_filter.get('tickSize')
                if tick_size_str:
                    symbol_info["price_precision"] = Decimal(tick_size_str)
                else:
                    logger.warning(f"Could not find tickSize for {SYMBOL}. Using default: {symbol_info['price_precision']}")

                # Extract qtyStep (qty_precision)
                qty_step_str = lot_size_filter.get('qtyStep')
                if qty_step_str:
                    symbol_info["qty_precision"] = Decimal(qty_step_str)
                else:
                    logger.warning(f"Could not find qtyStep for {SYMBOL}. Using default: {symbol_info['qty_precision']}")

                logger.info(f"Fetched symbol info for {SYMBOL}: Price Precision = {symbol_info['price_precision']}, Quantity Precision = {symbol_info['qty_precision']}")
                return True
            else:
                logger.error(f"Symbol {SYMBOL} not found in instruments info.")
                return False
        else:
            logger.error(f"Failed to fetch instrument info for {SYMBOL}.")
            return False

    def start_websocket_streams(self):
        """Starts public and private websocket streams, opening channels to the ether."""
        try:
            self.ws_public.orderbook_stream(
                symbol=SYMBOL,
                depth=ORDERBOOK_DEPTH_LEVELS,
                callback=on_public_ws_message
            )
            self.ws_private.order_stream(callback=on_private_ws_message)
            self.ws_private.position_stream(callback=on_private_ws_message)
            logger.info("WebSocket streams started and listening for real-time updates.")
        except Exception as e:
            logger.error(f"Error starting WebSocket streams: {type(e).__name__} - {e}")
            os.system(f"termux-toast -b red -c white 'MMXCEL Critical: WS streams failed to start!'")
            raise # Re-raise to halt execution if core communication fails

    async def get_balance(self, account_type: str = "UNIFIED", coin: str = "USDT") -> Decimal:
        """Fetches available balance via REST API, discerning the available arcane energies."""
        response = await self._make_api_call(
            self.http_session.get_wallet_balance,
            accountType=account_type,
            coin=coin
        )
        if response and response.get('retCode') == 0:
            if 'result' in response and 'list' in response['result'] and \
               response['result']['list'] and response['result']['list'][0] and \
               'coin' in response['result']['list'][0] and response['result']['list'][0]['coin']:
                balance_info = response['result']['list'][0]['coin'][0]
                available_balance_str = balance_info.get('walletBalance')

                if available_balance_str is None or available_balance_str == '':
                    self.current_balance = Decimal("0")
                    logger.warning(f"Wallet balance for {coin} was None or empty string from API, defaulting to 0. (Raw: '{available_balance_str}')")
                else:
                    try:
                        self.current_balance = Decimal(str(available_balance_str))
                    except Exception as e:
                        logger.error(f"Failed to transmute '{available_balance_str}' to Decimal: {type(e).__name__} - {e}. Defaulting to 0.")
                        self.current_balance = Decimal("0")
                return self.current_balance
            logger.error(f"Unexpected balance response structure: {response.get('retMsg', 'No error message')} | Raw: {response}")
            return Decimal("0")
        else:
            logger.error(f"Failed to get balance: {response.get('retMsg', 'No error message') if response else 'No response'}")
            return Decimal("0")

    async def get_open_orders_rest(self) -> Dict[str, Any]:
        """Fetches open orders via REST API to sync state, aligning the bot's perception with reality."""
        response = await self._make_api_call(
            self.http_session.get_open_orders,
            category=CATEGORY,
            symbol=SYMBOL
        )
        if response and response.get('retCode') == 0:
            current_open_orders = {}
            for order in response['result']['list']:
                current_open_orders[order['orderId']] = {
                    "client_order_id": order.get('orderLinkId', 'N/A'),
                    "symbol": order['symbol'],
                    "side": order['side'],
                    "price": Decimal(order['price']),
                    "qty": Decimal(order['qty']),
                    "status": order['orderStatus'],
                    "timestamp": float(order['createdTime']) / 1000
                }
            ws_state["open_orders"] = current_open_orders
            return current_open_orders
        else:
            logger.error(f"Failed to get open orders via REST: {response.get('retMsg', 'No error message') if response else 'No response'}")
            return {}

    async def get_positions_rest(self) -> Dict[str, Any]:
        """Fetches current positions via REST API to sync state, revealing the bot's current holdings."""
        response = await self._make_api_call(
            self.http_session.get_positions,
            category=CATEGORY,
            symbol=SYMBOL
        )
        if response and response.get('retCode') == 0:
            current_positions = {}
            for position in response['result']['list']:
                # Filter for the specific symbol and ensure it's a valid position
                if position.get('symbol') == SYMBOL and Decimal(position.get('size', '0')) > 0:
                    side = 'Long' if position.get('side') == 'Buy' else 'Short'
                    current_positions[side] = {
                        'size': Decimal(position.get('size', '0')),
                        'avg_price': Decimal(position.get('avgPrice', '0')),
                        'unrealisedPnl': Decimal(position.get('unrealisedPnl', '0'))
                    }
            ws_state['positions'] = current_positions # Update shared state
            return current_positions
        else:
            logger.error(f"Failed to get positions via REST: {response.get('retMsg', 'No error message') if response else 'No response'}")
            return {}

    async def place_order(self, side: str, qty: Decimal, price: Optional[Decimal] = None, client_order_id: Optional[str] = None, order_type: str = "Limit") -> Optional[Dict[str, Any]]:
        """Places a single order on the exchange, manifesting a new trade intention."""
        if order_type == "Limit" and price is None:
            logger.error("Price must be specified for a Limit order.")
            return None
        if order_type == "Market" and price is not None:
            logger.warning("Price specified for a Market order. It will be ignored.")
            price = None # Market orders do not use price

        # Quantize price and quantity based on symbol info
        quantized_qty = qty.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
        quantized_price = None
        if price is not None:
            quantized_price = price.quantize(symbol_info["price_precision"], rounding=ROUND_DOWN)

        if quantized_qty <= 0:
            logger.error(f"Attempted to place order with non-positive quantized quantity: {quantized_qty}")
            return None

        try:
            order_payload = {
                "category": CATEGORY,
                "symbol": SYMBOL,
                "side": side,
                "orderType": order_type,
                "qty": str(quantized_qty),
                "positionIdx": 1 if side == "Buy" else 2
            }
            if quantized_price is not None:
                order_payload["price"] = str(quantized_price)
            if client_order_id is not None:
                order_payload["orderLinkId"] = client_order_id

            if order_type == "Limit":
                order_payload["timeInForce"] = "GTC" # Good Till Cancelled

            response = await self._make_api_call(self.http_session.place_order, **order_payload)

            if response and response.get('retCode') == 0:
                order_info = response['result']
                log_msg = f"Placed {order_type} {side} order: {order_info.get('orderId', 'N/A')}"
                if quantized_price is not None:
                    log_msg += f" @ {quantized_price}"
                log_msg += f" Qty: {quantized_qty}"
                if client_order_id is not None:
                    log_msg += f" (Client ID: {client_order_id})"
                logger.info(log_msg)
                return order_info
            else:
                logger.error(f"Failed to place {order_type} {side} order for {quantized_qty}@{quantized_price if quantized_price else 'N/A'}: {response.get('retMsg', 'No error message') if response else 'No response'}")
                return None
        except Exception as e:
            logger.error(f"Error placing order for {side} {quantized_qty}@{quantized_price if quantized_price else 'N/A'} (Type: {order_type}): {type(e).__name__} - {e}")
            return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancels a specific order, dissolving a trade intention from the ledger."""
        response = await self._make_api_call(
            self.http_session.cancel_order,
            category=CATEGORY,
            symbol=SYMBOL,
            orderId=order_id
        )
        if response and response.get('retCode') == 0:
            logger.info(f"Cancelled order: {order_id}")
            return True
        else:
            logger.error(f"Failed to cancel order {order_id}: {response.get('retMsg', 'No error message') if response else 'No response'}")
            return False

    async def cancel_all_orders(self) -> None:
        """Cancels all open orders for the symbol, sweeping the slate clean."""
        response = await self._make_api_call(
            self.http_session.cancel_all_orders,
            category=CATEGORY,
            symbol=SYMBOL
        )
        if response and response.get('retCode') == 0:
            logger.info("Successfully cancelled all open orders.")
            ws_state["open_orders"].clear()
        else:
            logger.error(f"Failed to cancel all orders: {response.get('retMsg', 'No error message') if response else 'No response'}")

    async def place_batch_orders(self, orders: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Places multiple orders in a single batch request, a powerful conjuration."""
        if not orders:
            logger.warning("No orders provided for batch placement.")
            return None

        batch_request_payload = {
            "category": CATEGORY,
            "request": []
        }
        for order in orders:
            # Quantize price and quantity for each order in the batch
            quantized_qty = order["qty"].quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            if quantized_qty <= 0:
                logger.warning(f"Skipping batch order with non-positive quantized quantity: {quantized_qty}")
                continue

            quantized_price = None
            if "price" in order and order["price"] is not None:
                quantized_price = order["price"].quantize(symbol_info["price_precision"], rounding=ROUND_DOWN)

            order_payload = {
                "symbol": SYMBOL,
                "side": order["side"],
                "orderType": order["orderType"],
                "qty": str(quantized_qty),
                "positionIdx": 1 if order["side"] == "Buy" else 2
            }
            if quantized_price is not None:
                order_payload["price"] = str(quantized_price)
            if "client_order_id" in order and order["client_order_id"] is not None:
                order_payload["orderLinkId"] = order["client_order_id"]
            if order["orderType"] == "Limit":
                order_payload["timeInForce"] = order.get("timeInForce", "GTC")

            batch_request_payload["request"].append(order_payload)

        if not batch_request_payload["request"]:
            logger.warning("All orders in batch filtered out due to invalid quantities after quantization.")
            return None

        response = await self._make_api_call(self.http_session.place_batch_order, **batch_request_payload)

        if response and response.get('retCode') == 0:
            logger.info(f"Successfully placed {len(batch_request_payload['request'])} batch orders.")
            return response['result']
        else:
            logger.error(f"Failed to place batch orders: {response.get('retMsg', 'No error message') if response else 'No response'}")
            return None

    async def get_orderbook_snapshot(self) -> Optional[Dict[str, Any]]:
        """Fetches a snapshot of the orderbook for more reliable market data."""
        response = await self._make_api_call(
            self.http_session.get_orderbook,
            category=CATEGORY,
            symbol=SYMBOL
        )
        if response and response.get('retCode') == 0:
            orderbook = response['result']
            # Bybit v5 uses 'a' (asks) and 'b' (bids)
            if orderbook and 'b' in orderbook and 'a' in orderbook and orderbook['b'] and orderbook['a']:
                best_bid = Decimal(orderbook['b'][0][0])
                best_ask = Decimal(orderbook['a'][0][0])
                mid_price = (best_bid + best_ask) / Decimal("2")
                ws_state["best_bid"] = best_bid
                ws_state["best_ask"] = best_ask
                ws_state["mid_price"] = mid_price
                ws_state["last_update_time"] = time.time()
                logger.debug(f"Orderbook snapshot: Mid Price: {mid_price:.4f}")
                return orderbook
            else:
                logger.error(f"Orderbook snapshot returned but missing bids/asks data. Raw response: {response}")
                return None
        else:
            logger.error(f"Failed to get orderbook snapshot: {response.get('retMsg', 'No error message') if response else 'No response'}")
            return None

class MarketMakingStrategy:
    """The Alchemist's Strategy, overseeing the delicate balance of market forces."""
    def __init__(self, client: BybitClient):
        self.client = client
        self.running = False
        self.rebalance_task = None
        self.stop_loss_task = None
        self.system_stats_task = None
        self.memory_cleanup_task = None
        self.exit_flag = asyncio.Event()
        self.last_mid_price = Decimal("0") # Track last mid-price for dynamic order replacement
        self.last_order_refresh_time = 0
        self.order_refresh_interval = ORDER_REFRESH_INTERVAL
        self.min_order_refresh_interval = MIN_ORDER_REFRESH_INTERVAL
        self.max_order_refresh_interval = MAX_ORDER_REFRESH_INTERVAL
        self.order_refresh_counter = 0
        self.max_order_refresh_attempts = 3 # Maximum attempts to refresh orders before giving up

    async def place_market_making_orders(self):
        """Manages the placement of market-making orders based on real-time data."""
        # First, check if we have valid market data
        if not await self._is_market_data_available():
            return

        current_time = time.time()

        # Check if it's time to refresh orders
        if current_time - self.last_order_refresh_time >= self.order_refresh_interval:
            self.order_refresh_counter += 1
            self.last_order_refresh_time = current_time

            # Dynamically adjust the refresh interval based on recent activity
            if self.order_refresh_counter >= self.max_order_refresh_attempts:
                # If we've tried to refresh multiple times without success, increase the interval
                self.order_refresh_interval = min(self.order_refresh_interval * 2, self.max_order_refresh_interval)
                logger.info(f"Increasing order refresh interval to {self.order_refresh_interval} seconds due to multiple failed attempts.")
                self.order_refresh_counter = 0
            else:
                # If we successfully refreshed, reset the counter and consider decreasing the interval
                self.order_refresh_counter = 0
                if self.order_refresh_interval > self.min_order_refresh_interval:
                    self.order_refresh_interval = max(self.order_refresh_interval * 0.9, self.min_order_refresh_interval)
                    logger.debug(f"Decreasing order refresh interval to {self.order_refresh_interval} seconds.")

            # Check if price has moved significantly to trigger re-placement
            mid_price = ws_state["mid_price"]
            if self.last_mid_price != Decimal("0") and mid_price != Decimal("0"):
                if self.last_mid_price == mid_price: # Avoid division by zero if price hasn't moved
                    price_change_percentage = Decimal("0")
                else:
                    price_change_percentage = abs(mid_price - self.last_mid_price) / self.last_mid_price

                if price_change_percentage >= PRICE_THRESHOLD:
                    logger.info(f"Price moved {price_change_percentage:.4%} (>= {PRICE_THRESHOLD:.4%}). Cancelling all orders to re-place.")
                    await self.client.cancel_all_orders()
                    # Do not reset last_mid_price yet, it will be updated after new orders are placed
                else:
                    # If price hasn't moved significantly, and we already have orders, skip placing new ones
                    if ws_state["open_orders"]:
                        logger.debug("No significant price change and orders exist. Skipping new order placement.")
                        return # Skip placing new orders if price hasn't moved and orders are already out

            # Check for stale orders and cancel them, removing forgotten spirits
            orders_to_cancel_ids = [
                order_id for order_id, details in list(ws_state["open_orders"].items())
                if time.time() - details['timestamp'] > ORDER_LIFESPAN_SECONDS
            ]
            if orders_to_cancel_ids:
                logger.info(f"Cancelling {len(orders_to_cancel_ids)} stale orders to keep the ledger clean.")
                # Use asyncio.gather for concurrent cancellation if multiple stale orders
                await asyncio.gather(*[self.client.cancel_order(oid) for oid in orders_to_cancel_ids])

            # Get fresh state from REST to handle any missed WS updates, ensuring perfect synchronicity
            await self.client.get_open_orders_rest()

            # Check if we have too many open orders, avoiding over-committing arcane energy
            if len(ws_state["open_orders"]) >= MAX_OPEN_ORDERS:
                logger.info(f"Max open orders ({MAX_OPEN_ORDERS}) reached. Skipping new order placement.")
                return

            # Calculate bid and ask prices based on the arcane spread
            mid_price = ws_state["mid_price"]
            best_bid = ws_state["best_bid"]
            best_ask = ws_state["best_ask"]

            bid_price = mid_price * (Decimal("1") - SPREAD_PERCENTAGE)
            ask_price = mid_price * (Decimal("1") + SPREAD_PERCENTAGE)

            # Adjust prices to market precision using the fetched symbol_info
            # Use ROUND_DOWN for bids, ROUND_UP for asks to be more aggressive (better chance of filling)
            bid_price = bid_price.quantize(symbol_info["price_precision"], rounding=ROUND_DOWN)
            ask_price = ask_price.quantize(symbol_info["price_precision"], rounding=ROUND_UP)

            # Ensure our bid is not higher than the best bid, and our ask is not lower than the best ask
            # We want to be inside or at the current best prices to be truly market making
            # This means our bid should be AT or BELOW current best bid. Our ask AT or ABOVE current best ask.
            bid_price = min(bid_price, best_bid)
            ask_price = max(ask_price, best_ask)

            orders_to_place = []

            # Prepare buy order if not already present and within limits
            has_buy_order = any(order['side'] == 'Buy' for order in ws_state["open_orders"].values())
            if not has_buy_order and len(ws_state["open_orders"]) < MAX_OPEN_ORDERS:
                client_buy_id = f"mmxcel-buy-{int(time.time() * 1000)}"
                orders_to_place.append({
                    "side": "Buy",
                    "qty": QUANTITY,
                    "price": bid_price,
                    "client_order_id": client_buy_id,
                    "orderType": "Limit"
                })

            # Prepare sell order if not already present and within limits
            # Ensure we don't exceed MAX_OPEN_ORDERS if both buy and sell are prepared
            has_sell_order = any(order['side'] == 'Sell' for order in ws_state["open_orders"].values())
            if not has_sell_order and (len(ws_state["open_orders"]) + len(orders_to_place)) < MAX_OPEN_ORDERS:
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
                self.last_mid_price = mid_price # Update last mid price after placing orders
            elif not ws_state["open_orders"]:
                # If no orders were placed and there are no open orders (e.g., initial state or after cancellations)
                # Make sure last_mid_price is set so PRICE_THRESHOLD logic can work
                self.last_mid_price = mid_price

    async def update_system_stats(self):
        """Periodically updates system statistics using psutil."""
        try:
            ws_state["system_stats"]["cpu_usage"] = psutil.cpu_percent(interval=None)
            ws_state["system_stats"]["memory_usage"] = psutil.virtual_memory().percent
            net_io = psutil.net_io_counters()
            ws_state["system_stats"]["network_io"] = (net_io.bytes_sent, net_io.bytes_recv)
        except psutil.Error as e: # Catch psutil-specific errors, including PermissionError
            logger.warning(f"Could not update system stats: {e}. This may be due to environment restrictions. Stats will be disabled.")
            # Set to N/A and stop trying to update if it fails once.
            ws_state["system_stats"]["cpu_usage"] = "N/A"
            ws_state["system_stats"]["memory_usage"] = "N/A"
            ws_state["system_stats"]["network_io"] = ("N/A", "N/A")
            # Cancel this task so it doesn't keep logging errors
            if self.system_stats_task and not self.system_stats_task.done():
                self.system_stats_task.cancel()

    async def _is_market_data_available(self) -> bool:
        """Helper to check if market data is available, attempting to recover with a snapshot if needed."""
        # Check if data is stale (older than, say, 15 seconds) or non-existent
        is_stale = (time.time() - ws_state["last_update_time"]) > 15
        is_zero = ws_state["mid_price"] == Decimal("0")

        if is_stale or is_zero:
            logger.warning("Market data is stale or unavailable. Attempting to fetch a new orderbook snapshot via REST.")
            snapshot = await self.client.get_orderbook_snapshot()
            if snapshot:
                logger.info("Successfully recovered market data using REST snapshot.")
                return True # Data is now available
            else:
                logger.error("Failed to recover market data using REST snapshot. Skipping operation.")
                return False # Still no data
        return True

    async def rebalance_inventory(self):
        """Periodically rebalances inventory (position) to a neutral state, maintaining equilibrium."""
        if not await self._is_market_data_available():
            return

        long_size = ws_state['positions'].get('Long', {}).get('size', Decimal('0'))
        short_size = ws_state['positions'].get('Short', {}).get('size', Decimal('0'))

        # Calculate net position, the current imbalance of energy
        net_position = long_size - short_size

        if abs(net_position) > REBALANCE_THRESHOLD_QTY:
            side_to_rebalance = "Sell" if net_position > 0 else "Buy"
            qty_to_rebalance = abs(net_position)

            # Ensure quantity to rebalance is greater than zero after quantization
            quantized_qty_to_rebalance = qty_to_rebalance.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            if quantized_qty_to_rebalance <= 0:
                logger.warning(f"Quantized rebalance quantity is zero ({quantized_qty_to_rebalance}), skipping rebalance.")
                return

            logger.warning(f"{YELLOW}Inventory imbalance detected. Net position: {net_position:.{_calculate_decimal_precision(symbol_info['qty_precision'])}f}. "
                             f"Attempting to rebalance by placing a {side_to_rebalance} market order for {quantized_qty_to_rebalance}.{NC}")
            os.system(f"termux-toast -b yellow -c black 'MMXCEL: Rebalancing {quantized_qty_to_rebalance:.2f} {SYMBOL}!'")

            # Place a market order to quickly rebalance
            client_rebalance_id = f"mmxcel-rebal-{int(time.time() * 1000)}"
            asyncio.create_task(self.client.place_order(side_to_rebalance, quantized_qty_to_rebalance, order_type="Market", client_order_id=client_rebalance_id))

    async def manage_stop_loss_and_profit_take(self):
        """Monitors positions for stop-loss and profit-taking opportunities, safeguarding and harvesting gains."""
        if not await self._is_market_data_available():
            return

        # Check long position
        long_pos = ws_state['positions'].get('Long', {})
        long_size = long_pos.get('size', Decimal('0'))
        long_avg_price = long_pos.get('avg_price', Decimal('0'))

        if long_size > 0 and long_avg_price > 0: # Ensure valid position
            pnl_usdt = long_pos.get('unrealisedPnl', Decimal('0'))

            pnl_percentage = Decimal('0')
            # Avoid division by zero if position value is 0
            if (long_avg_price * long_size) > 0:
                pnl_percentage = pnl_usdt / (long_avg_price * long_size)

            # Quantize the size before placing a closing order
            quantized_long_size = long_size.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            if quantized_long_size <= 0:
                logger.warning(f"Quantized long closing quantity is zero ({quantized_long_size}), skipping close.")
            elif pnl_percentage < -STOP_LOSS_PERCENTAGE:
                logger.critical(f"{RED}Stop-loss triggered for LONG position! Unrealised PnL: {pnl_usdt:.2f} ({pnl_percentage:.2%}). "
                                 f"Placing market sell order to close {quantized_long_size}.{NC}")
                os.system(f"termux-toast -b red -c white 'MMXCEL: LONG SL triggered! PnL: {pnl_usdt:.2f}'")
                asyncio.create_task(self.client.place_order("Sell", quantized_long_size, order_type="Market", client_order_id=f"mmxcel-sl-long-{int(time.time() * 1000)}"))
            elif pnl_percentage >= PROFIT_PERCENTAGE:
                logger.info(f"{GREEN}Profit-take triggered for LONG position. Unrealised PnL: {pnl_usdt:.2f} ({pnl_percentage:.2%}). "
                                 f"Placing market sell order to close {quantized_long_size}.{NC}")
                os.system(f"termux-toast -b green -c black 'MMXCEL: LONG TP triggered! PnL: {pnl_usdt:.2f}'")
                asyncio.create_task(self.client.place_order("Sell", quantized_long_size, order_type="Market", client_order_id=f"mmxcel-tp-long-{int(time.time() * 1000)}"))

        # Check short position
        short_pos = ws_state['positions'].get('Short', {})
        short_size = short_pos.get('size', Decimal('0'))
        short_avg_price = short_pos.get('avg_price', Decimal('0'))

        if short_size > 0 and short_avg_price > 0: # Ensure valid position
            pnl_usdt = short_pos.get('unrealisedPnl', Decimal('0'))

            pnl_percentage = Decimal('0')
            if (short_avg_price * short_size) > 0:
                pnl_percentage = pnl_usdt / (short_avg_price * short_size)

            # Quantize the size before placing a closing order
            quantized_short_size = short_size.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            if quantized_short_size <= 0:
                logger.warning(f"Quantized short closing quantity is zero ({quantized_short_size}), skipping close.")
            elif pnl_percentage < -STOP_LOSS_PERCENTAGE:
                logger.critical(f"{RED}Stop-loss triggered for SHORT position! Unrealised PnL: {pnl_usdt:.2f} ({pnl_percentage:.2%}). "
                                 f"Placing market buy order to close {quantized_short_size}.{NC}")
                os.system(f"termux-toast -b red -c white 'MMXCEL: SHORT SL triggered! PnL: {pnl_usdt:.2f}'")
                asyncio.create_task(self.client.place_order("Buy", quantized_short_size, order_type="Market", client_order_id=f"mmxcel-sl-short-{int(time.time() * 1000)}"))
            elif pnl_percentage >= PROFIT_PERCENTAGE:
                logger.info(f"{GREEN}Profit-take triggered for SHORT position. Unrealised PnL: {pnl_usdt:.2f} ({pnl_percentage:.2%}). "
                                 f"Placing market buy order to close {quantized_short_size}.{NC}")
                os.system(f"termux-toast -b green -c black 'MMXCEL: SHORT TP triggered! PnL: {pnl_usdt:.2f}'")
                asyncio.create_task(self.client.place_order("Buy", quantized_short_size, order_type="Market", client_order_id=f"mmxcel-tp-short-{int(time.time() * 1000)}"))

    async def memory_cleanup(self):
        """Performs garbage collection to free up memory."""
        import gc
        gc.collect()
        logger.info("Performed periodic memory cleanup.")

    async def shutdown(self):
        """Gracefully shuts down the bot, including cancelling open orders, and silencing the arcane channels."""
        if self.running:
            self.running = False
            logger.info("Shutdown initiated. Cancelling all open orders...")
            os.system(f"termux-toast -b '#FFA500' -c white 'MMXCEL: Shutting down, cancelling orders...'")
            await self.client.cancel_all_orders()
            # Stop any running tasks
            if self.rebalance_task and not self.rebalance_task.done():
                self.rebalance_task.cancel()
            if self.stop_loss_task and not self.stop_loss_task.done():
                self.stop_loss_task.cancel()
            if self.system_stats_task and not self.system_stats_task.done():
                self.system_stats_task.cancel()
            if self.memory_cleanup_task and not self.memory_cleanup_task.done():
                self.memory_cleanup_task.cancel()

            self.exit_flag.set()
            os.system(f"termux-toast -b green -c white 'MMXCEL: Shutdown complete.'")

    async def run(self):
        """Unleashes the bot's full power, beginning its market-making vigil."""
        self.running = True

        # Validate configuration values before starting operations
        if not self._validate_config():
            logger.critical("Configuration validation failed. Aborting bot startup.")
            os.system(f"termux-toast -b red -c white 'MMXCEL Config Error! Check logs.'")
            return

        # Fetch symbol information first, crucial for correct price/quantity handling
        if not await self.client.get_symbol_info():
            logger.critical("Failed to fetch symbol information. Cannot proceed without it.")
            os.system(f"termux-toast -b red -c white 'MMXCEL Error: Symbol info fetch failed!'")
            return

        self.client.start_websocket_streams()

        # Give some time for WS to connect and get initial data from the ether
        await asyncio.sleep(5)

        # Fetch initial state via REST to ensure we don't miss anything
        await self.client.get_balance(coin="USDT")
        await self.client.get_open_orders_rest()
        await self.client.get_positions_rest() # Explicitly fetch initial positions

        # Start background tasks for rebalancing and stop-loss/profit-taking
        self.rebalance_task = asyncio.create_task(self._periodic_task(self.rebalance_inventory, interval=10, name="Rebalance"))
        self.stop_loss_task = asyncio.create_task(self._periodic_task(self.manage_stop_loss_and_profit_take, interval=2, name="PnL Management"))
        self.system_stats_task = asyncio.create_task(self._periodic_task(self.update_system_stats, interval=5, name="System Stats"))
        self.memory_cleanup_task = asyncio.create_task(self._periodic_task(self.memory_cleanup, interval=MEMORY_CLEANUP_INTERVAL, name="Memory Cleanup"))

        try:
            while self.running:
                clear_screen()
                print_neon_header(f"MMXCEL Bybit Market Making Bot - {SYMBOL}", color=MAGENTA)
                print_neon_separator()

                # Display initial configuration for clarity
                print(f"{BOLD}{CYAN}--- Active Configuration ---{NC}")
                price_disp_prec = _calculate_decimal_precision(symbol_info["price_precision"])
                qty_disp_prec = _calculate_decimal_precision(symbol_info["qty_precision"])

                print(format_metric("Symbol", SYMBOL, YELLOW, value_color=WHITE, label_width=20))
                print(format_metric("Quantity per Order", QUANTITY, YELLOW, value_precision=_calculate_decimal_precision(QUANTITY), label_width=20))
                print(format_metric("Spread Percentage", f"{SPREAD_PERCENTAGE * 100:.4f}%", YELLOW, value_color=WHITE, label_width=20))
                print(format_metric("Max Open Orders", MAX_OPEN_ORDERS, YELLOW, value_color=WHITE, label_width=20))
                print(format_metric("Order Lifespan (s)", ORDER_LIFESPAN_SECONDS, YELLOW, value_color=WHITE, label_width=20))
                print(format_metric("Rebalance Threshold", REBALANCE_THRESHOLD_QTY, YELLOW, value_precision=_calculate_decimal_precision(REBALANCE_THRESHOLD_QTY), label_width=20))
                print(format_metric("Profit Take %", f"{PROFIT_PERCENTAGE * 100:.4f}%", YELLOW, value_color=WHITE, label_width=20))
                print(format_metric("Stop Loss %", f"{STOP_LOSS_PERCENTAGE * 100:.4f}%", YELLOW, value_color=WHITE, label_width=20))
                print(format_metric("Price Threshold %", f"{PRICE_THRESHOLD * 100:.4f}%", YELLOW, value_color=WHITE, label_width=20))
                print(format_metric("Using Testnet", USE_TESTNET, YELLOW, value_color=WHITE, label_width=20))
                print(format_metric("Price Tick Size", symbol_info['price_precision'], YELLOW, value_precision=price_disp_prec, label_width=20))
                print(format_metric("Quantity Step Size", symbol_info['qty_precision'], YELLOW, value_precision=qty_disp_prec, label_width=20))
                print(format_metric("Order Refresh Interval (s)", self.order_refresh_interval, YELLOW, value_color=WHITE, label_width=20))
                print(format_metric("Memory Cleanup Interval (s)", MEMORY_CLEANUP_INTERVAL, YELLOW, value_color=WHITE, label_width=20))
                print_neon_separator()

                # System Health Monitoring
                print(f"{BOLD}{CYAN}--- System Health ---{NC}")
                print(format_metric("CPU Usage", f"{ws_state['system_stats']['cpu_usage']:.2f}%", MAGENTA, value_color=WHITE, label_width=20))
                print(format_metric("Memory Usage", f"{ws_state['system_stats']['memory_usage']:.2f}%", MAGENTA, value_color=WHITE, label_width=20))
                sent_mb = ws_state['system_stats']['network_io'][0] / (1024*1024)
                recv_mb = ws_state['system_stats']['network_io'][1] / (1024*1024)
                print(format_metric("Network I/O (Sent/Recv)", f"{sent_mb:.2f}MB / {recv_mb:.2f}MB", MAGENTA, value_color=WHITE, label_width=20))
                print_neon_separator()

                # Market and Account Data
                print(f"{BOLD}{CYAN}--- Current Market & Account Status ---{NC}")
                print(format_metric("Mid Price", ws_state['mid_price'], BLUE, value_precision=price_disp_prec))
                print(format_metric("Best Bid", ws_state['best_bid'], BLUE, value_precision=price_disp_prec))
                print(format_metric("Best Ask", ws_state['best_ask'], BLUE, value_precision=price_disp_prec))
                await self.client.get_balance(coin="USDT") # Refresh balance every loop for display
                print(format_metric("Available Balance (USDT)", self.client.current_balance, YELLOW, value_precision=2))
                print(format_metric("Last Market Data Update", datetime.fromtimestamp(ws_state['last_update_time']).strftime('%Y-%m-%d %H:%M:%S'), YELLOW, value_color=WHITE, label_width=20))
                print_neon_separator()

                # Position Details
                print(f"{BOLD}{CYAN}--- Active Positions ({SYMBOL}) ---{NC}")
                long_pos = ws_state['positions'].get('Long', {'size': Decimal('0'), 'avg_price': Decimal('0'), 'unrealisedPnl': Decimal('0')})
                short_pos = ws_state['positions'].get('Short', {'size': Decimal('0'), 'avg_price': Decimal('0'), 'unrealisedPnl': Decimal('0')})

                print(format_position(long_pos, 'Long', price_disp_prec, qty_disp_prec))
                print(format_position(short_pos, 'Short', price_disp_prec, qty_disp_prec))
                print_neon_separator()

                # Open Orders Details
                print(f"{BOLD}{CYAN}--- Open Orders ({len(ws_state['open_orders'])}) ---{NC}")
                if ws_state["open_orders"]:
                    # Sort orders by timestamp for consistent display
                    sorted_orders = sorted(list(ws_state["open_orders"].values()), key=lambda x: x['timestamp'])
                    for order in sorted_orders:
                        print(format_order(order, price_disp_prec, qty_disp_prec))
                else:
                    print(f"  {YELLOW}No open orders detected.{NC}")
                print_neon_separator()

                # Primary market-making loop
                await self.place_market_making_orders()

                # Wait for next cycle
                await asyncio.sleep(1) # Main loop delay, balances responsiveness with API usage
        except asyncio.CancelledError:
            logger.info("Main loop task cancelled.")
        except Exception as e:
            logger.critical(f"An unhandled critical error occurred in the main loop: {type(e).__name__} - {e}", exc_info=True)
            os.system(f"termux-toast -b red -c white 'MMXCEL Critical Error: Bot crashed! Check logs!'")
        finally:
            await self.shutdown()

    async def _periodic_task(self, func, interval, name):
        """A helper to run a function periodically until the bot is stopped."""
        try:
            while self.running:
                await func()
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info(f"Periodic task '{name}' was cancelled.")
        except Exception as e:
            logger.error(f"Error in periodic task '{name}': {type(e).__name__} - {e}")
            os.system(f"termux-toast -b red -c white 'MMXCEL Critical: {name} task failed!'")
        finally:
            logger.info(f"Periodic task '{name}' has finished.")

    def _validate_config(self) -> bool:
        """Validates critical configuration parameters to ensure a sound spell."""
        is_valid = True
        if not isinstance(QUANTITY, Decimal) or QUANTITY <= 0:
            logger.critical(f"{RED}Config Error: QUANTITY must be a positive Decimal. Current: {QUANTITY}{NC}")
            is_valid = False
        if not isinstance(SPREAD_PERCENTAGE, Decimal) or SPREAD_PERCENTAGE <= 0:
            logger.critical(f"{RED}Config Error: SPREAD_PERCENTAGE must be a positive Decimal. Current: {SPREAD_PERCENTAGE}{NC}")
            is_valid = False
        if not isinstance(PROFIT_PERCENTAGE, Decimal) or PROFIT_PERCENTAGE <= 0:
            logger.critical(f"{RED}Config Error: PROFIT_PERCENTAGE must be a positive Decimal. Current: {PROFIT_PERCENTAGE}{NC}")
            is_valid = False
        if not isinstance(STOP_LOSS_PERCENTAGE, Decimal) or STOP_LOSS_PERCENTAGE <= 0:
            logger.critical(f"{RED}Config Error: STOP_LOSS_PERCENTAGE must be a positive Decimal. Current: {STOP_LOSS_PERCENTAGE}{NC}")
            is_valid = False
        if not isinstance(PRICE_THRESHOLD, Decimal) or PRICE_THRESHOLD < 0: # Can be zero for continuous re-placement
            logger.critical(f"{RED}Config Error: PRICE_THRESHOLD must be a non-negative Decimal. Current: {PRICE_THRESHOLD}{NC}")
            is_valid = False
        if MAX_OPEN_ORDERS <= 0:
            logger.critical(f"{RED}Config Error: MAX_OPEN_ORDERS must be a positive integer. Current: {MAX_OPEN_ORDERS}{NC}")
            is_valid = False

        if SPREAD_PERCENTAGE >= PRICE_THRESHOLD and PRICE_THRESHOLD > 0:
            logger.warning(f"{YELLOW}Warning: SPREAD_PERCENTAGE ({SPREAD_PERCENTAGE:.4%}) is greater than or equal to PRICE_THRESHOLD ({PRICE_THRESHOLD:.4%}). "
                           "This might lead to frequent order cancellations and re-placements even with small price movements or fills.{NC}")

        return is_valid

def signal_handler(sig, frame):
    """Handles graceful shutdown on SIGINT (Ctrl+C) or SIGTERM."""
    print(f"\n{YELLOW}Termination signal detected! Initiating graceful shutdown...{NC}")
    loop = asyncio.get_event_loop()

    # Schedule the shutdown coroutine as a task to be run by the event loop
    if loop.is_running():
        # Find the main strategy task and request it to stop
        for task in asyncio.all_tasks(loop):
            if task.get_name() == 'MarketMakingStrategy_run_task': # Identify by its assigned name
                 task.cancel()
                 break
    else:
        # If loop isn't running yet (e.g., Ctrl+C very early), just exit.
        exit(0)

async def main():
    """The main incantation, summoning the bot and its powerful strategies."""
    if not API_KEY or not API_SECRET:
        print(f"{RED}BYBIT_API_KEY or BYBIT_API_SECRET not found in .env file. "
              f"Please ensure your magical credentials are in place.{NC}")
        os.system(f"termux-toast -b red -c white 'MMXCEL Error: API credentials missing!'")
        return

    # Check for Termux:API and warn if not found
    if os.system("command -v termux-toast > /dev/null 2>&1") != 0: # Redirect stderr to dev/null
        print(f"{YELLOW}Warning: 'termux-api' command not found. Toasts will be disabled. "
              f"Please install it via 'pkg install termux-api' and the Termux:API app.{NC}")
    else:
        os.system(f"termux-toast -b green -c white 'MMXCEL: Bot started successfully!'")

    print(f"{BOLD}{CYAN}MMXCEL Bybit Market Making Bot is being summoned...{NC}")

    client = BybitClient(api_key=API_KEY, api_secret=API_SECRET, testnet=USE_TESTNET)
    strategy = MarketMakingStrategy(client)

    # Attempt to set Hedge Mode (mode=3) for the entire USDT category at startup.
    try:
        logger.info(f"Attempting to set position mode to Hedge Mode for the {CATEGORY} category (Coin: USDT)...")
        response = client.http_session.switch_position_mode(
            category=CATEGORY,
            coin="USDT", # Set for the entire USDT perpetuals category
            mode=3  # 3 is for Hedge Mode
        )
        # Bybit API returns retCode 0 even if the mode is already set, so we just check for success.
        if response and response.get('retCode') == 0:
            logger.info(f"Successfully set position mode to Hedge Mode for the USDT category.")
            os.system(f"termux-toast -b green -c black 'Hedge Mode set successfully!'")
        else:
            # This will catch API-level errors returned in a valid response (e.g., permission denied)
            error_message = response.get('retMsg', 'Unknown error')
            logger.error(f"Failed to set Hedge Mode: {error_message}. Please set it manually in your Bybit account settings.")
            os.system(f"termux-toast -b red -c white 'Failed to set Hedge Mode! Check logs.'")
            return # Exit if we can't set the required mode.
    except Exception as e:
        # This will catch client-level errors (e.g., network issues, invalid request format)
        logger.error(f"An exception occurred while trying to set Hedge Mode: {type(e).__name__} - {e}")
        logger.error("Please ensure Hedge Mode is enabled for linear perpetuals in your Bybit account settings.")
        os.system(f"termux-toast -b red -c white 'Error setting Hedge Mode! Check logs.'")
        return # Exit if we can't set the required mode.

    logger.info(f"Starting MMXCEL Bybit Market Making Bot for {SYMBOL}...")
    logger.info(f"Using Testnet: {USE_TESTNET}")

    # Handle OS signals for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler) # Interruption from keyboard (Ctrl+C)
    signal.signal(signal.SIGTERM, signal_handler) # Termination signal (e.g., system shutdown)

    # Create the main strategy task and assign it a name for easier identification in signal handler
    main_strategy_task = asyncio.create_task(strategy.run(), name='MarketMakingStrategy_run_task')

    try:
        await main_strategy_task
    except asyncio.CancelledError:
        # This exception is caught when strategy.run() is cancelled by the signal handler
        logger.info("Main strategy run task explicitly cancelled.")
    except Exception as e:
        logger.critical(f"{RED}A critical error occurred during the main invocation: {type(e).__name__} - {e}", exc_info=True)
        os.system(f"termux-toast -b red -c white 'MMXCEL Critical Error: Bot crashed! Check logs!'")
    finally:
        # Ensure shutdown is called even if an error occurs or after cancellation
        # The strategy.shutdown() is implicitly called by the strategy.run() finally block.
        # This outer finally ensures it's called if run() didn't start or completed abnormally.
        if strategy.running: # Only call if it wasn't already gracefully shut down
            await strategy.shutdown()
        logger.info("Bot execution finished. May your digital journey be ever enlightened.")

if __name__ == '__main__':
    # asyncio.run() handles the creation and closing of the event loop
    asyncio.run(main())
