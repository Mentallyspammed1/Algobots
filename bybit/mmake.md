#!/usr/bin/env python3
"""
MMXCEL v2.9.1 – Bybit Hedge-Mode Market-Making Bot
Compatible drop-in replacement for xmm.py
Author: Pyrmethus, Termux-Coding Wizard
"""

import os
import asyncio
import logging
import logging.handlers
import time
import json
import signal
import sys
import select
import uuid # Added for unique client order IDs
from decimal import Decimal, getcontext, ROUND_DOWN, ROUND_UP, DecimalException
from typing import Any, Dict, Optional, List, Tuple

from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket
from colorama import Fore, Style, init

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
    with open("config.json", "r") as f:
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

# Global configuration aliases (read robustly using .get() with defaults)
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

# New configurable parameters
BALANCE_REFRESH_INTERVAL = int(config.get("BALANCE_REFRESH_INTERVAL", 30))
CAPITAL_ALLOCATION_PERCENTAGE = Decimal(str(config.get("CAPITAL_ALLOCATION_PERCENTAGE", "0.05")))
ABNORMAL_SPREAD_THRESHOLD = Decimal(str(config.get("ABNORMAL_SPREAD_THRESHOLD", "0.015")))
REBALANCE_ORDER_TYPE = str(config.get("REBALANCE_ORDER_TYPE", "Market")) # "Market" or "Limit"
REBALANCE_PRICE_OFFSET_PERCENTAGE = Decimal(str(config.get("REBALANCE_PRICE_OFFSET_PERCENTAGE", "0"))) # For Limit rebalance orders

# Constants for data freshness and retry delays
MAX_DATA_AGE_SECONDS = 10  # Maximum acceptable age for market data
MAX_RETRIES_API = 5        # Default maximum retries for API calls
RETRY_DELAY_API = 2        # Initial delay for API retries in seconds
WS_MONITOR_INTERVAL = 10   # How often to check WS connection status
PNL_MONITOR_INTERVAL = 5   # How often to check for PnL triggers

# Exchange precision placeholders (initialized globally)
symbol_info = {
    "price_precision": Decimal("0.0001"),
    "qty_precision": Decimal("0.001"),
    "min_order_value": Decimal("10.0"), # Default, will be updated by get_symbol_info
    "min_price": Decimal("0"),
    "min_qty": Decimal("0"),
}

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

# Global session statistics
session_stats = {
    "start_time": time.time(),
    "orders_placed": 0,
    "orders_filled": 0,
    "rebalances_count": 0,
    "circuit_breaker_activations": 0,
}

# Global state for bot operations
BOT_STATE = "INITIALIZING"

# Flag to check if termux-toast command is available
_HAS_TERMUX_TOAST_CMD = False # This will be set by check_termux_toast() in main

# Global flag for graceful shutdown
_SHUTDOWN_REQUESTED = False

# -----------------------------
# Helper Functions
# -----------------------------

def set_bot_state(state: str):
    """Sets the global bot state and logs the change."""
    global BOT_STATE
    if BOT_STATE != state:
        logger.info(f"{Fore.CYAN}Bot State Change: {BOT_STATE} -> {state}{NC}")
        BOT_STATE = state

def _calculate_decimal_precision(d: Decimal) -> int:
    """Determine the number of decimal places in a Decimal value for display."""
    if not isinstance(d, Decimal):
        return 0
    # Use as_tuple().exponent for accurate decimal place calculation
    # The exponent is negative for decimal places, so we take its absolute value.
    return abs(d.normalize().as_tuple().exponent)

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
    value_color: Optional[str] = None,
    label_width: int = 25,
    value_precision: Optional[int] = None,
    unit: str = "",
    is_pnl: bool = False,
) -> str:
    """Format a label-value pair for display with precision and color."""
    formatted_label = f"{label_color}{label:<{label_width}}{NC}"
    actual_value_color = value_color if value_color else label_color
    formatted_value = ""

    if isinstance(value, Decimal):
        current_precision = value_precision if value_precision is not None else _calculate_decimal_precision(value)
        if is_pnl:
            actual_value_color = GREEN if value >= Decimal("0") else RED
            # sign = "+" if value > Decimal("0") else "" # Sign is automatically added by f-string for positive numbers
            formatted_value = f"{actual_value_color}{value:,.{current_precision}f}{unit}{NC}"
        else:
            formatted_value = f"{actual_value_color}{value:,.{current_precision}f}{unit}{NC}"
    elif isinstance(value, (int, float)):
        if is_pnl:
            actual_value_color = GREEN if value >= 0 else RED
            # sign = "+" if value > 0 else ""
            formatted_value = f"{actual_value_color}{value:,}{unit}{NC}"
        else:
            formatted_value = f"{actual_value_color}{value:,}{unit}{NC}"
    else: # For strings or other types
        formatted_value = f"{actual_value_color}{str(value)}{unit}{NC}"
    return f"{formatted_label}: {formatted_value}"

def check_termux_toast() -> bool:
    """Checks if the termux-toast command is available."""
    return os.system("command -v termux-toast > /dev/null 2>&1") == 0

def send_toast(message: str, color: str = "#336699", text_color: str = "white") -> None:
    """Sends a toast message if termux-toast is available."""
    if _HAS_TERMUX_TOAST_CMD: 
        os.system(f"termux-toast -b '{color}' -c '{text_color}' '{message}'")
    else:
        logger.debug(f"Toast (unavailable): {message}")


# -----------------------------
# WebSocket Callbacks
# -----------------------------

def on_public_ws_message(msg: Dict[str, Any]) -> None:
    """Handle public WebSocket messages (orderbook)."""
    try:
        topic = msg.get("topic")
        if topic and topic.startswith(f"orderbook.1."):
            data = msg.get("data")
            if data and data.get("b") and data.get("a"):
                bid_info = data["b"][0]
                ask_info = data["a"][0]
                
                ws_state["best_bid"] = Decimal(bid_info[0])
                ws_state["best_ask"] = Decimal(ask_info[0])
                if ws_state["best_bid"] > 0 and ws_state["best_ask"] > 0:
                    ws_state["mid_price"] = (ws_state["best_bid"] + ws_state["best_ask"]) / Decimal("2")
                else:
                    ws_state["mid_price"] = Decimal("0")
                
                ws_state["last_update_time"] = time.time()
                logger.debug(f"WS Orderbook: Bid={ws_state['best_bid']:.4f}, Ask={ws_state['best_ask']:.4f}, Mid={ws_state['mid_price']:.4f}")
    except (KeyError, IndexError, ValueError, TypeError, DecimalException) as e:
        logger.error(f"Error processing public WS message: {type(e).__name__} - {e} | Message: {msg}")
    except Exception as e:
        logger.error(f"Unexpected error in public WS handler: {type(e).__name__} - {e} | Message: {msg}")

def on_private_ws_message(msg: Dict[str, Any]) -> None:
    """Handle private WebSocket messages (orders, positions)."""
    try:
        topic = msg.get("topic")
        if topic == "order":
            for o in msg["data"]:
                oid = o.get("orderId")
                if not oid: continue
                
                if o.get("orderStatus") in ("Filled", "Canceled", "Deactivated"):
                    if oid in ws_state["open_orders"]:
                        order_details = ws_state["open_orders"].pop(oid, None)
                        if order_details and o["orderStatus"] == "Filled":
                            session_stats["orders_filled"] += 1
                            logger.info(f"Order filled: {order_details['side']} {order_details['qty']} @ {order_details['price']}")
                            send_toast(f"Order filled: {order_details['side']} {order_details['qty']}", "green", "white")
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
                    current_unrealised_pnl = Decimal(p.get("unrealisedPnl", "0"))
                    
                    ws_state["positions"][side] = {
                        "size": Decimal(p.get("size", "0")),
                        "avg_price": Decimal(p.get("avgPrice", "0")),
                        "unrealisedPnl": current_unrealised_pnl,
                    }
                    logger.debug(f"WS Position Update: {side} Size={p.get('size')}, PnL={current_unrealised_pnl}")
    except (KeyError, ValueError, TypeError, DecimalException) as e:
        logger.error(f"Error processing private WS message: {type(e).__name__} - {e} | Message: {msg}")
    except Exception as e:
        logger.error(f"Unexpected error in private WS handler: {type(e).__name__} - {e} | Message: {msg}")

# -----------------------------
# Bybit Client Class
# -----------------------------

class BybitClient:
    MAX_RETRIES = MAX_RETRIES_API
    RETRY_DELAY = RETRY_DELAY_API

    def __init__(self, key: str, secret: str, testnet: bool):
        self.http = HTTP(testnet=testnet, api_key=key, api_secret=secret)
        self.ws_public = WebSocket(testnet=testnet, channel_type="linear", retries=self.MAX_RETRIES)
        self.ws_private = WebSocket(testnet=testnet, channel_type="private", api_key=key, api_secret=secret, retries=self.MAX_RETRIES)
        self.current_balance = Decimal("0")
        self.is_public_ws_connected = False
        self.is_private_ws_connected = False
        
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
            logger.info(f"{Fore.GREEN}Public WebSocket connection established.{NC}")
        elif ws_type == "private":
            self.is_private_ws_connected = True
            logger.info(f"{Fore.GREEN}Private WebSocket connection established.{NC}")

    def _on_ws_close(self, ws_type: str):
        """Callback when a WebSocket connection closes."""
        if ws_type == "public":
            self.is_public_ws_connected = False
            logger.warning(f"{Fore.YELLOW}Public WebSocket connection closed. Pybit will attempt reconnect.{NC}")
        elif ws_type == "private":
            self.is_private_ws_connected = False
            logger.warning(f"{Fore.YELLOW}Private WebSocket connection closed. Pybit will attempt reconnect.{NC}")

    def _on_ws_error(self, ws_type: str, error: Exception):
        """Callback for WebSocket errors."""
        logger.error(f"{Fore.RED}{ws_type.capitalize()} WebSocket error: {error}{NC}")
    
    async def _monitor_websockets(self, strategy_instance):
        """Periodically checks WS connection status."""
        while strategy_instance.running and not _SHUTDOWN_REQUESTED:
            if not self.is_public_ws_connected:
                logger.warning(f"{Fore.YELLOW}Public WS connection currently disconnected. Awaiting pybit reconnect.{NC}")
                send_toast("WS Public disconnected", "#FFA500", "white")
            
            if not self.is_private_ws_connected:
                logger.warning(f"{Fore.YELLOW}Private WS connection currently disconnected. Awaiting pybit reconnect.{NC}")
                send_toast("WS Private disconnected", "#FFA500", "white")
            
            await asyncio.sleep(WS_MONITOR_INTERVAL)

    async def _api(self, api_method, *args, **kwargs):
        """Generic retry wrapper for API calls with exponential backoff and error handling."""
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = api_method(*args, **kwargs)
                if response and response.get("retCode") == 0:
                    return response

                ret_code = response.get('retCode') if response else None
                ret_msg = response.get('retMsg', 'No response or unknown error') if response else 'No response'
                error_msg = f"{Fore.YELLOW}API Call Failed (Attempt {attempt}/{self.MAX_RETRIES}, Code: {ret_code}): {ret_msg}{NC}"
                logger.warning(error_msg)

                # Specific handling for non-recoverable errors (e.g., authentication, invalid parameters)
                # These codes are chosen based on typical Bybit API error meanings.
                # 10001: System error (retry)
                # 10006: Too many requests (retry with backoff)
                # 30034: Order failed (retry)
                # 30035: Too many attempts (retry)
                # 10007: Authentication failed (stop, requires user action)
                # 10002: Invalid parameter (stop, indicates code error)
                if ret_code in [10001, 10006, 30034, 30035]: 
                    if attempt < self.MAX_RETRIES:
                        delay = self.RETRY_DELAY * (2 ** (attempt - 1)) + (time.time() % 1) # Add small jitter
                        logger.warning(f"{Fore.YELLOW}Retrying in {delay:.1f}s...{NC}")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"{Fore.RED}API retries exhausted for {api_method.__name__}. Last error: {ret_msg}{NC}")
                        return None
                elif ret_code in [10007, 10002]: # Non-retryable errors
                    logger.error(f"{Fore.RED}Non-retryable API error: {ret_msg}. Action required.{NC}")
                    # Consider setting a global flag to stop operations or trigger emergency shutdown
                    return None
                else: # Any other error code not explicitly handled
                    logger.error(f"{Fore.RED}Unhandled API error code {ret_code}: {ret_msg}. Stopping retries for this specific error.{NC}")
                    return None
            except Exception as e:
                error_msg = f"{Fore.RED}Exception during API call (Attempt {attempt}/{self.MAX_RETRIES}): {type(e).__name__} - {e}{NC}"
                logger.error(error_msg, exc_info=True) # exc_info=True logs full traceback
                if attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAY * (2 ** (attempt - 1)) + (time.time() % 1) # Add small jitter
                    logger.warning(f"{Fore.YELLOW}Retrying in {delay:.1f}s...{NC}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"{Fore.RED}API call failed after all retries: {type(e).__name__} - {e}{NC}")
                    return None
        return None

    async def get_symbol_info(self) -> bool:
        """Fetch symbol precision details, including min order value and quantity."""
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
                
                symbol_info["min_price"] = Decimal(price_filter.get('minPrice', "0"))
                symbol_info["min_qty"] = Decimal(lot_size_filter.get('minQty', "0"))
                
                # The prompt mentioned max_order_value_limit. This typically comes from an exchange,
                # but Bybit's instruments info doesn't provide a direct max_order_value_limit
                # or similar. We'll use a conservative default or calculation.
                # Assuming 'basePrecision' is similar or can be derived.
                # For now, stick to min_order_value as the primary value constraint.
                
                # Calculate a sensible min_order_value if not explicitly provided
                calculated_min_value = symbol_info["min_qty"] * symbol_info["min_price"]
                # Use 5 USDT as a common minimum, or the calculated min if it's higher.
                symbol_info["min_order_value"] = max(calculated_min_value, Decimal("5")) 

                logger.info(f"{Fore.CYAN}Symbol Info: {SYMBOL} | Price Prc: {symbol_info['price_precision']}, Qty Prc: {symbol_info['qty_precision']}, Min Price: {symbol_info['min_price']}, Min Qty: {symbol_info['min_qty']}, Min Order Value: {symbol_info['min_order_value']}{NC}")
                return True
            logger.error(f"{Fore.RED}Symbol {SYMBOL} not found in instruments info.{NC}")
            return False
        logger.error(f"{Fore.RED}Failed to fetch instrument info for {SYMBOL}.{NC}")
        return False

    async def test_credentials(self) -> bool:
        """Verify API credentials by fetching wallet balance."""
        response = await self._api(self.http.get_wallet_balance, accountType="UNIFIED")
        if response and response.get("retCode") == 0:
            logger.info(f"{Fore.GREEN}API credentials validated successfully.{NC}")
            return True
        logger.error(f"{Fore.RED}API credentials validation failed. Check keys, secret, and testnet setting.{NC}")
        return False

    def start_websockets(self):
        """Start public and private WebSocket streams."""
        logger.info(f"{Fore.CYAN}Starting public orderbook stream for {SYMBOL}...{NC}")
        self.ws_public.orderbook_stream(symbol=SYMBOL, depth=1, callback=on_public_ws_message)
        logger.info(f"{Fore.CYAN}Starting private order and position streams...{NC}")
        self.ws_private.order_stream(callback=on_private_ws_message)
        self.ws_private.position_stream(callback=on_private_ws_message)
        logger.info(f"{Fore.CYAN}WebSocket streams initiated.{NC}")

    async def get_balance(self) -> Decimal:
        """Fetch available balance for USDT."""
        response = await self._api(self.http.get_wallet_balance, accountType="UNIFIED", coin="USDT")
        if response and response.get('retCode') == 0:
            try:
                balance_list = response.get("result", {}).get("list", [])
                if balance_list:
                    coin_info = balance_list[0].get("coin", [{}])[0]
                    balance_str = coin_info.get("availableToWithdraw", "0")
                    logger.debug(f"{Fore.CYAN}Attempting to convert balance string: '{balance_str}' to Decimal.{NC}")
                    balance = Decimal(balance_str)
                    self.current_balance = balance
                    ws_state["available_balance"] = balance
                    ws_state["last_balance_update"] = time.time()
                    logger.debug(f"{Fore.CYAN}Balance updated: {balance}{NC}")
                    return balance
                logger.warning(f"{Fore.YELLOW}Balance response structure unexpected or empty.{NC}")
                return Decimal("0")
            except (KeyError, IndexError, ValueError, TypeError) as e:
                logger.error(f"{Fore.RED}Error accessing balance data from API response: {type(e).__name__} - {e} | Response: {response}{NC}")
                return Decimal("0")
            except DecimalException as e:
                logger.error(f"{Fore.RED}Error converting balance string '{balance_str}' to Decimal: {type(e).__name__} - {e}{NC}")
                return Decimal("0")
        logger.error(f"{Fore.RED}Failed to fetch balance (API response error).{NC}")
        return Decimal("0")

    async def get_open_orders_rest(self) -> Dict[str, Any]:
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
                    logger.error(f"{Fore.RED}Error processing REST order data: {type(e).__name__} - {e} | Order: {order}{NC}")
            
            ws_state["open_orders"] = current_open_orders
            logger.debug(f"{Fore.CYAN}REST sync: Found {len(current_open_orders)} open orders.{NC}")
            return current_open_orders
        logger.error(f"{Fore.RED}Failed to fetch open orders via REST.{NC}")
        return {}

    async def get_positions_rest(self) -> Dict[str, Any]:
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
                    logger.error(f"{Fore.RED}Error processing REST position data: {type(e).__name__} - {e} | Position: {pos}{NC}")

            ws_state["positions"] = current_positions
            logger.debug(f"{Fore.CYAN}REST sync: Found {len(current_positions)} active positions.{NC}")
            return current_positions
        logger.error(f"{Fore.RED}Failed to fetch positions via REST.{NC}")
        return {}

    async def place_order(self, side: str, qty: Decimal, price: Optional[Decimal] = None, client_order_id: Optional[str] = None, order_type: str = "Limit") -> Optional[Dict[str, Any]]:
        """Place a single order, applying quantization and minimum checks."""
        if order_type == "Limit" and price is None:
            logger.error(f"{Fore.RED}Price must be specified for a Limit order.{NC}")
            return None
        if order_type == "Market" and price is not None:
            logger.warning(f"{Fore.YELLOW}Price specified for Market order will be ignored.{NC}")
            price = None

        try:
            quantized_qty = qty.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            if quantized_qty <= Decimal("0"):
                logger.error(f"{Fore.RED}Order quantity {qty} results in zero or negative after quantization ({quantized_qty}).{NC}")
                return None
            if symbol_info.get("min_qty", Decimal("0")) > Decimal("0") and quantized_qty < symbol_info["min_qty"]:
                 logger.error(f"{Fore.RED}Order quantity {quantized_qty} is below minimum required quantity ({symbol_info['min_qty']}).{NC}")
                 return None
        except DecimalException as e:
            logger.error(f"{Fore.RED}Error quantizing quantity {qty}: {e}{NC}")
            return None

        quantized_price = None
        if price is not None:
            try:
                rounding_method = ROUND_DOWN if side == "Buy" else ROUND_UP
                quantized_price = price.quantize(symbol_info["price_precision"], rounding=rounding_method)
                
                if symbol_info.get("min_price", Decimal("0")) > Decimal("0") and quantized_price < symbol_info["min_price"]:
                    logger.error(f"{Fore.RED}Order price {quantized_price} is below minimum required price ({symbol_info['min_price']}).{NC}")
                    return None
            except DecimalException as e:
                logger.error(f"{Fore.RED}Error quantizing price {price}: {e}{NC}")
                return None

        # Check against min_order_value for limit/market orders
        if quantized_qty and ws_state["mid_price"] > Decimal("0") and symbol_info.get("min_order_value", Decimal("0")) > Decimal("0"):
            # For Limit order, use its specific price for value check
            # For Market order, use mid_price for an estimated value check
            value_check_price = quantized_price if quantized_price else ws_state["mid_price"]
            if value_check_price > Decimal("0"):
                order_value = quantized_qty * value_check_price
                if order_value < symbol_info["min_order_value"]:
                    logger.error(f"{Fore.RED}Calculated order value ({order_value:.2f}) is below minimum order value ({symbol_info['min_order_value']:.2f}).{NC}")
                    return None

        payload = {
            "category": CATEGORY,
            "symbol": SYMBOL,
            "side": side,
            "orderType": order_type,
            "qty": str(quantized_qty),
            "positionIdx": 1 if side == "Buy" else 2 # For Hedge Mode
        }
        if quantized_price:
            payload["price"] = str(quantized_price)
        if client_order_id:
            payload["orderLinkId"] = client_order_id
        if order_type == "Limit":
            payload["timeInForce"] = "GTC" # Good-Till-Canceled for limit orders

        logger.debug(f"{Fore.BLUE}Placing Order Payload: {payload}{NC}")
        response = await self._api(self.http.place_order, **payload)

        if response and response.get('retCode') == 0:
            order_info = response['result']
            session_stats["orders_placed"] += 1
            logger.info(f"{Fore.GREEN}Successfully placed {order_type} {side} order: ID={order_info.get('orderId', 'N/A')}, Qty={quantized_qty}, Price={quantized_price if quantized_price else 'N/A'}{NC}")
            
            # Immediately update ws_state with the new order (WS will confirm/update later)
            new_order_id = order_info.get('orderId')
            if new_order_id:
                ws_state["open_orders"][new_order_id] = {
                    "client_order_id": client_order_id if client_order_id else "N/A",
                    "symbol": SYMBOL,
                    "side": side,
                    "price": quantized_price,
                    "qty": quantized_qty,
                    "status": "New", # Assuming 'New' status after placement
                    "timestamp": time.time(),
                }
            return order_info
        else:
            logger.error(f"{Fore.RED}Failed to place {order_type} {side} order: {response.get('retMsg', 'Unknown error') if response else 'No response'}{NC}")
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
            logger.info(f"{Fore.GREEN}Successfully canceled order: {order_id}{NC}")
            ws_state["open_orders"].pop(order_id, None) # Remove from local state
            return True
        else:
            logger.error(f"{Fore.RED}Failed to cancel order {order_id}: {response.get('retMsg', 'Unknown error') if response else 'No response'}{NC}")
            return False

    async def cancel_all_orders(self) -> None:
        """Cancel all open orders for the current symbol."""
        logger.warning(f"{Fore.YELLOW}Attempting to cancel all open orders for {SYMBOL}...{NC}")
        response = await self._api(
            self.http.cancel_all_orders,
            category=CATEGORY,
            symbol=SYMBOL
        )
        if response and response.get('retCode') == 0:
            logger.info(f"{Fore.GREEN}Successfully canceled all open orders for {SYMBOL}.{NC}")
            ws_state["open_orders"].clear() # Clear local state
            send_toast("All orders cancelled!", "red", "white")
        else:
            logger.error(f"{Fore.RED}Failed to cancel all orders for {SYMBOL}: {response.get('retMsg', 'Unknown error') if response else 'No response'}{NC}")
            send_toast("Failed to cancel all orders!", "red", "white")

    async def place_batch_orders(self, orders: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Place multiple orders in a single batch request, with quantization and validation."""
        if not orders:
            logger.warning(f"{Fore.YELLOW}No orders provided for batch placement.{NC}")
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
                    logger.warning(f"{Fore.YELLOW}Skipping batch order due to missing side or quantity: {order}{NC}")
                    continue

                quantized_qty = qty.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
                if quantized_qty <= Decimal("0"):
                    logger.warning(f"{Fore.YELLOW}Skipping batch order due to zero/negative quantized quantity: {quantized_qty}{NC}")
                    continue
                if symbol_info.get("min_qty", Decimal("0")) > Decimal("0") and quantized_qty < symbol_info["min_qty"]:
                     logger.warning(f"{Fore.YELLOW}Skipping batch order: quantity {quantized_qty} below minimum {symbol_info['min_qty']}.{NC}")
                     continue

                quantized_price = None
                if price is not None:
                    rounding_method = ROUND_DOWN if side == "Buy" else ROUND_UP
                    quantized_price = price.quantize(symbol_info["price_precision"], rounding=rounding_method)
                    if symbol_info.get("min_price", Decimal("0")) > Decimal("0") and quantized_price < symbol_info["min_price"]:
                        logger.warning(f"{Fore.YELLOW}Skipping batch order: price {quantized_price} below minimum {symbol_info['min_price']}.{NC}")
                        continue
                
                # Check against min_order_value for each order in batch
                if quantized_qty and ws_state["mid_price"] > Decimal("0") and symbol_info.get("min_order_value", Decimal("0")) > Decimal("0"):
                    value_check_price = quantized_price if quantized_price else ws_state["mid_price"]
                    if value_check_price > Decimal("0"):
                        order_value = quantized_qty * value_check_price
                        if order_value < symbol_info["min_order_value"]:
                            logger.warning(f"{Fore.YELLOW}Skipping batch order: value {order_value:.2f} below minimum {symbol_info['min_order_value']:.2f}.{NC}")
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
                logger.error(f"{Fore.RED}Error preparing batch order {order}: {type(e).__name__} - {e}{NC}")
            except Exception as e:
                logger.error(f"{Fore.RED}Unexpected error preparing batch order {order}: {type(e).__name__} - {e}{NC}")

        if not batch_payloads:
            logger.warning(f"{Fore.YELLOW}No valid orders to place in batch after preparation.{NC}")
            return None

        logger.debug(f"{Fore.BLUE}Placing Batch Order Payloads: {batch_payloads}{NC}")
        response = await self._api(
            self.http.place_batch_order,
            category=CATEGORY,
            request=batch_payloads 
        )

        if response and response.get('retCode') == 0:
            session_stats["orders_placed"] += len(batch_payloads)
            logger.info(f"{Fore.GREEN}Successfully placed {len(batch_payloads)} batch orders.{NC}")
            
            # Immediately update ws_state for batch orders
            for result_item, original_order in zip(response['result']['list'], batch_payloads):
                new_order_id = result_item.get('orderId')
                if new_order_id:
                    ws_state["open_orders"][new_order_id] = {
                        "client_order_id": original_order.get("orderLinkId", "N/A"),
                        "symbol": SYMBOL,
                        "side": original_order.get("side"),
                        "price": Decimal(original_order.get("price", "0")),
                        "qty": Decimal(original_order.get("qty", "0")),
                        "status": "New",
                        "timestamp": time.time(),
                    }

            return response['result']
        else:
            logger.error(f"{Fore.RED}Failed to place batch orders: {response.get('retMsg', 'Unknown error') if response else 'No response'}{NC}")
            return None

# -----------------------------
# Market Making Strategy
# -----------------------------

class MarketMakingStrategy:
    def __init__(self, client: BybitClient):
        self.client = client
        self.running = False
        self.rebalance_task = None
        self.pnl_monitor_task = None
        self.ws_monitor_task = None 
        self.last_mid_price_for_replacement = Decimal("0")

    def _is_market_data_fresh(self) -> bool:
        """Checks if the market data (bid/ask/mid) is considered fresh."""
        if ws_state["last_update_time"] == 0 or ws_state["mid_price"] <= Decimal("0"):
            return False
        age = time.time() - ws_state["last_update_time"]
        if age > MAX_DATA_AGE_SECONDS:
            logger.warning(f"{Fore.YELLOW}Market data is stale (age: {age:.1f}s > {MAX_DATA_AGE_SECONDS}s). Skipping operation.{NC}")
            send_toast("Market data stale!", "#FFA500", "white")
            return False
        return True

    def _calculate_dynamic_quantity(self) -> Decimal:
        """
        Calculates the order quantity dynamically based on global settings,
        available balance, and market volatility.
        """
        adjusted_qty = QUANTITY
        effective_qty_from_capital = Decimal("0")

        if ws_state["mid_price"] > Decimal("0") and ws_state["available_balance"] > Decimal("0"):
            # Use configurable CAPITAL_ALLOCATION_PERCENTAGE
            max_capital_per_order = ws_state["available_balance"] * CAPITAL_ALLOCATION_PERCENTAGE
            
            min_qty_by_value = Decimal("0")
            if symbol_info.get("min_order_value", Decimal("0")) > Decimal("0"):
                min_qty_by_value = (symbol_info["min_order_value"] / ws_state["mid_price"]).quantize(symbol_info["qty_precision"], rounding=ROUND_UP)

            effective_qty_from_capital = (max_capital_per_order / ws_state["mid_price"]).quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            
            # Use the smallest of configured QUANTITY, capital-derived quantity, and ensure it's at least min_qty_by_value
            adjusted_qty = min(QUANTITY, max(effective_qty_from_capital, min_qty_by_value))
            
            if adjusted_qty <= Decimal("0"):
                logger.warning(f"{Fore.YELLOW}Dynamic quantity adjusted to zero or less due to balance/min_order_value constraints. Falling back to min_qty or base QUANTITY.{NC}")
                adjusted_qty = max(symbol_info["min_qty"], QUANTITY * Decimal("0.1")) # Small fallback if too constrained
                
        current_spread_percent = (ws_state["best_ask"] - ws_state["best_bid"]) / ws_state["mid_price"] if ws_state["mid_price"] > 0 else Decimal("0")
        volatility_factor = Decimal("1")
        if SPREAD_PERCENTAGE > Decimal("0") and current_spread_percent > Decimal("0"):
            volatility_factor_calc = SPREAD_PERCENTAGE / current_spread_percent
            volatility_factor = max(Decimal("0.5"), min(Decimal("1.5"), volatility_factor_calc)) # Clamp volatility factor

        adjusted_qty *= volatility_factor
        
        final_qty = adjusted_qty.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
        
        if symbol_info.get("min_qty", Decimal("0")) > Decimal("0"):
            final_qty = max(final_qty, symbol_info["min_qty"])
        
        # Final check to ensure min_order_value is met after all adjustments
        if ws_state["mid_price"] > Decimal("0") and symbol_info.get("min_order_value", Decimal("0")) > Decimal("0"):
            current_order_value = final_qty * ws_state["mid_price"]
            if current_order_value < symbol_info["min_order_value"]:
                recalculated_qty_for_min_value = (symbol_info["min_order_value"] / ws_state["mid_price"]).quantize(symbol_info["qty_precision"], rounding=ROUND_UP)
                final_qty = max(final_qty, recalculated_qty_for_min_value)
                logger.debug(f"{Fore.CYAN}Adjusted dynamic quantity to meet min order value: {final_qty}{NC}")

        # Log dynamic quantity calculation, ensuring effective_qty_from_capital is always bound
        if ws_state["mid_price"] > Decimal("0") and ws_state["available_balance"] > Decimal("0"):
            logger.debug(f"{Fore.CYAN}Dynamic Quantity Calculation: Base={QUANTITY}, Capital Adj={effective_qty_from_capital}, Volatility Factor={volatility_factor:.2f}, Final={final_qty}{NC}")
        else:
            logger.debug(f"{Fore.CYAN}Dynamic Quantity Calculation: Base={QUANTITY}, Capital Adj=N/A (balance/price zero), Volatility Factor={volatility_factor:.2f}, Final={final_qty}{NC}")
        
        return final_qty

    async def place_market_making_orders(self):
        """Manages the placement of limit orders for market making."""
        mid = ws_state["mid_price"]
        bid = ws_state["best_bid"]
        ask = ws_state["best_ask"]

        if not self._is_market_data_fresh() or not self._is_valid_price(mid, bid, ask):
            return

        abnormal_market, reason = self._detect_abnormal_conditions()
        if abnormal_market:
            if BOT_STATE != "CIRCUIT_BREAK":
                set_bot_state("CIRCUIT_BREAK") # Set state
            logger.critical(f"{RED}CIRCUIT BREAKER ACTIVATED: {reason}. Cancelling orders and pausing trading.{NC}")
            send_toast(f"Circuit Breaker: {reason[:30]}", "red", "white")
            await self.client.cancel_all_orders()
            session_stats["circuit_breaker_activations"] += 1
            await asyncio.sleep(60) # Pause for 1 minute
            set_bot_state("ACTIVE") # Resume after pause, assuming conditions improved
            return

        # If we were in circuit break, and conditions are now normal, reset state
        if BOT_STATE == "CIRCUIT_BREAK":
            set_bot_state("ACTIVE")

        if self.last_mid_price_for_replacement > Decimal("0") and mid > Decimal("0"):
            try:
                price_change = abs(mid - self.last_mid_price_for_replacement) / self.last_mid_price_for_replacement
                if price_change >= PRICE_THRESHOLD:
                    logger.info(f"{Fore.YELLOW}Price moved {price_change:.4%}, initiating order re-placement sequence.{NC}")
                    send_toast(f"Price moved {price_change:.2%}, re-placing orders.", "blue", "white")
                    await self.client.cancel_all_orders()
            except DecimalException:
                logger.warning(f"{Fore.YELLOW}Decimal division error during price change calculation for price threshold.{NC}")
        
        await self._cancel_stale_orders()

        if len(ws_state["open_orders"]) >= MAX_OPEN_ORDERS:
            logger.debug(f"{Fore.CYAN}Max open orders ({MAX_OPEN_ORDERS}) reached. Skipping new MM orders.{NC}")
            return

        bid_price = mid * (Decimal("1") - SPREAD_PERCENTAGE)
        ask_price = mid * (Decimal("1") + SPREAD_PERCENTAGE)

        # Ensure our target prices are within the current best bid/ask bounds to avoid immediate fill
        # and to respect market depth, but also allow crossing the spread if needed for aggressive placement
        # The logic here is to ensure bid_price_adjusted <= best_bid and ask_price_adjusted >= best_ask
        bid_price_adjusted = min(bid_price.quantize(symbol_info["price_precision"], rounding=ROUND_DOWN), bid)
        ask_price_adjusted = max(ask_price.quantize(symbol_info["price_precision"], rounding=ROUND_UP), ask)
        
        # Ensure bid is always less than ask, especially after quantization and clamping
        if bid_price_adjusted >= ask_price_adjusted:
            logger.warning(f"{Fore.YELLOW}Calculated bid_price_adjusted ({bid_price_adjusted}) is >= ask_price_adjusted ({ask_price_adjusted}). Adjusting to ensure bid < ask.{NC}")
            # If they cross or are equal, shift them slightly
            if bid_price_adjusted >= ask_price_adjusted:
                bid_price_adjusted = ask_price_adjusted - symbol_info["price_precision"]
                # Re-quantize bid after adjustment
                bid_price_adjusted = bid_price_adjusted.quantize(symbol_info["price_precision"], rounding=ROUND_DOWN)
                if bid_price_adjusted <= Decimal("0"):
                    logger.error(f"{Fore.RED}Adjusted bid price is zero or negative. Skipping MM orders.{NC}")
                    return

        dynamic_order_qty = self._calculate_dynamic_quantity()

        if dynamic_order_qty <= Decimal("0"):
            logger.warning(f"{Fore.YELLOW}Dynamic order quantity calculated to zero or less. Skipping order placement.{NC}")
            return

        orders_to_place = []
        
        # Only place if no existing buy order OR we want more buy orders (depends on MAX_OPEN_ORDERS)
        if not any(o['side'] == 'Buy' for o in ws_state["open_orders"].values()) and len(ws_state["open_orders"]) < MAX_OPEN_ORDERS:
            client_buy_id = f"mmxcel-buy-{uuid.uuid4().hex}" # Use full hex for uniqueness
            orders_to_place.append({
                "side": "Buy",
                "qty": dynamic_order_qty,
                "price": bid_price_adjusted,
                "client_order_id": client_buy_id,
                "orderType": "Limit"
            })

        # Only place if no existing sell order AND (count of current open orders + new buy order) < MAX_OPEN_ORDERS
        if not any(o['side'] == 'Sell' for o in ws_state["open_orders"].values()) and (len(ws_state["open_orders"]) + len(orders_to_place)) < MAX_OPEN_ORDERS:
            client_sell_id = f"mmxcel-sell-{uuid.uuid4().hex}" # Use full hex for uniqueness
            orders_to_place.append({
                "side": "Sell",
                "qty": dynamic_order_qty,
                "price": ask_price_adjusted,
                "client_order_id": client_sell_id,
                "orderType": "Limit"
            })

        if orders_to_place:
            await self.client.place_batch_orders(orders_to_place)
            self.last_mid_price_for_replacement = mid # Update last mid price after successful placement
        elif not ws_state["open_orders"]: # If there are no orders and none were placed, update mid price anyway
             self.last_mid_price_for_replacement = mid

    async def _cancel_stale_orders(self):
        """Cancel orders that have exceeded their lifespan."""
        stale_order_ids = []
        for oid, data in list(ws_state["open_orders"].items()):
            if data.get("timestamp") is None:
                logger.warning(f"{Fore.YELLOW}Order {oid} missing timestamp, considering stale.{NC}")
                stale_order_ids.append(oid)
                continue
            if time.time() - data["timestamp"] > ORDER_LIFESPAN_SECONDS:
                stale_order_ids.append(oid)
        
        if stale_order_ids:
            logger.info(f"{Fore.YELLOW}Found {len(stale_order_ids)} stale orders. Cancelling them...{NC}")
            send_toast(f"Cancelling {len(stale_order_ids)} stale orders.", "orange", "white")
            tasks = [self.client.cancel_order(oid) for oid in stale_order_ids]
            # Use asyncio.gather to cancel orders concurrently for efficiency
            await asyncio.gather(*tasks, return_exceptions=True) # return_exceptions=True to allow one failure not to stop others

    def _is_valid_price(self, *prices) -> bool:
        """Check if prices are valid (non-zero, non-negative Decimals)."""
        for p in prices:
            if not isinstance(p, Decimal) or p <= Decimal("0"):
                logger.warning(f"{Fore.YELLOW}Invalid price detected: {p}. Skipping.{NC}")
                return False
        return True
    
    def _detect_abnormal_conditions(self) -> Tuple[bool, str]:
        """Detects abnormal market conditions like excessively wide spread."""
        mid = ws_state["mid_price"]
        bid = ws_state["best_bid"]
        ask = ws_state["best_ask"]

        if mid <= Decimal("0") or bid <= Decimal("0") or ask <= Decimal("0"):
            return True, "Market data unavailable or invalid"

        if bid >= ask:
            return True, f"Bid ({bid}) is greater or equal to Ask ({ask})"

        spread_percent = (ask - bid) / mid
        if spread_percent > ABNORMAL_SPREAD_THRESHOLD: # Using global ABNORMAL_SPREAD_THRESHOLD
            return True, f"Excessive spread: {spread_percent:.2%}"
        
        return False, ""

    async def rebalance_inventory(self):
        """Rebalance the position if it deviates from neutral beyond a threshold."""
        if not self._is_market_data_fresh():
            return

        long_size = ws_state['positions'].get('Long', {}).get('size', Decimal('0'))
        short_size = ws_state['positions'].get('Short', {}).get('size', Decimal('0'))
        net_position = long_size - short_size

        if abs(net_position) > REBALANCE_THRESHOLD_QTY:
            if BOT_STATE != "REBALANCING":
                set_bot_state("REBALANCING")
            
            side_to_close = "Sell" if net_position > Decimal("0") else "Buy" # If net long, sell. If net short, buy.
            qty_to_rebalance = abs(net_position).quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            
            if qty_to_rebalance <= Decimal("0"):
                logger.warning(f"{Fore.YELLOW}Rebalance quantity is zero after quantization. Skipping rebalance.{NC}")
                set_bot_state("ACTIVE") # Revert to active if no rebalance needed after calc
                return
            
            logger.info(f"{YELLOW}Inventory imbalance detected: Net Position {net_position:.{_calculate_decimal_precision(symbol_info['qty_precision'])}f}. Rebalancing by closing {side_to_close} {qty_to_rebalance}.{NC}")
            send_toast(f"Rebalancing {qty_to_rebalance} {SYMBOL}!", "yellow", "black")
            
            rebalance_price = None
            order_type = REBALANCE_ORDER_TYPE
            
            if REBALANCE_ORDER_TYPE == "Limit":
                if ws_state["mid_price"] <= Decimal("0"):
                    logger.warning(f"{Fore.YELLOW}Mid price not available for Limit rebalance, falling back to Market order.{NC}")
                    order_type = "Market"
                else:
                    if side_to_close == "Buy": # Closing a short position (buying back)
                        rebalance_price = ws_state["mid_price"] * (Decimal("1") - REBALANCE_PRICE_OFFSET_PERCENTAGE)
                        # Ensure buy limit price is at or below the current best ask for better fill chances
                        rebalance_price = min(rebalance_price, ws_state["best_ask"])
                    else: # side_to_close == "Sell", Closing a long position (selling)
                        rebalance_price = ws_state["mid_price"] * (Decimal("1") + REBALANCE_PRICE_OFFSET_PERCENTAGE)
                        # Ensure sell limit price is at or above the current best bid for better fill chances
                        rebalance_price = max(rebalance_price, ws_state["best_bid"])
                    
                    # Quantize the calculated price
                    rounding_method = ROUND_DOWN if side_to_close == "Buy" else ROUND_UP
                    rebalance_price = rebalance_price.quantize(symbol_info["price_precision"], rounding=rounding_method)
                    
                    # Validate the calculated limit price
                    if rebalance_price <= Decimal("0") or (symbol_info["min_price"] > Decimal("0") and rebalance_price < symbol_info["min_price"]):
                         logger.warning(f"{Fore.YELLOW}Calculated rebalance price {rebalance_price} is invalid. Falling back to Market order.{NC}")
                         order_type = "Market"

            rebalance_order_info = await self.client.place_order(side_to_close, qty_to_rebalance, price=rebalance_price, order_type=order_type)
            
            if rebalance_order_info:
                session_stats["rebalances_count"] += 1
            
            # Refresh positions and open orders to reflect the rebalance trade
            await self.client.get_positions_rest()
            await self.client.get_open_orders_rest()
            set_bot_state("ACTIVE") # Revert to active state after rebalancing attempt
        else:
            logger.debug(f"{Fore.CYAN}Net position {net_position:.{_calculate_decimal_precision(symbol_info['qty_precision'])}f} within threshold. No rebalance needed.{NC}")
            if BOT_STATE == "REBALANCING": # If we were rebalancing and it's now done/not needed
                set_bot_state("ACTIVE")

    async def monitor_pnl(self):
        """Monitors positions for stop-loss and profit-take conditions."""
        while self.running and not _SHUTDOWN_REQUESTED:
            if not self._is_market_data_fresh():
                await asyncio.sleep(PNL_MONITOR_INTERVAL)
                continue

            mid = ws_state["mid_price"]
            long_pos = ws_state["positions"].get("Long")
            short_pos = ws_state["positions"].get("Short")
            
            # Monitor Long Position
            if long_pos and long_pos["size"] > Decimal("0") and long_pos["avg_price"] > Decimal("0"):
                entry_price = long_pos["avg_price"]
                pnl_percent = (mid - entry_price) / entry_price
                
                if pnl_percent < -STOP_LOSS_PERCENTAGE:
                    logger.critical(f"{RED}Long position stop-loss triggered! PnL: {pnl_percent:.2%}. Exiting position.{NC}")
                    send_toast(f"Long SL: {pnl_percent:.2%}! Closing.", "red", "white")
                    set_bot_state("CLOSING_POSITION")
                    await self.client.cancel_all_orders()
                    await self.client.place_order("Sell", long_pos["size"], order_type="Market")
                    await self.client.get_positions_rest()
                    set_bot_state("ACTIVE")
                elif pnl_percent >= PROFIT_PERCENTAGE: 
                    logger.info(f"{GREEN}Long position profit-take triggered! PnL: {pnl_percent:.2%}. Exiting position.{NC}")
                    send_toast(f"Long TP: {pnl_percent:.2%}! Closing.", "green", "white")
                    set_bot_state("CLOSING_POSITION")
                    await self.client.cancel_all_orders()
                    await self.client.place_order("Sell", long_pos["size"], order_type="Market")
                    await self.client.get_positions_rest()
                    set_bot_state("ACTIVE")
            
            # Monitor Short Position
            if short_pos and short_pos["size"] > Decimal("0") and short_pos["avg_price"] > Decimal("0"):
                entry_price = short_pos["avg_price"]
                pnl_percent = (entry_price - mid) / entry_price
                
                if pnl_percent < -STOP_LOSS_PERCENTAGE:
                    logger.critical(f"{RED}Short position stop-loss triggered! PnL: {pnl_percent:.2%}. Exiting position.{NC}")
                    send_toast(f"Short SL: {pnl_percent:.2%}! Closing.", "red", "white")
                    set_bot_state("CLOSING_POSITION")
                    await self.client.cancel_all_orders()
                    await self.client.place_order("Buy", short_pos["size"], order_type="Market")
                    await self.client.get_positions_rest()
                    set_bot_state("ACTIVE")
                elif pnl_percent >= PROFIT_PERCENTAGE: 
                    logger.info(f"{GREEN}Short position profit-take triggered! PnL: {pnl_percent:.2%}. Exiting position.{NC}")
                    send_toast(f"Short TP: {pnl_percent:.2%}! Closing.", "green", "white")
                    set_bot_state("CLOSING_POSITION")
                    await self.client.cancel_all_orders()
                    await self.client.place_order("Buy", short_pos["size"], order_type="Market")
                    await self.client.get_positions_rest()
                    set_bot_state("ACTIVE")
            
            await asyncio.sleep(PNL_MONITOR_INTERVAL)


# -----------------------------
# Signal Handling and Main Execution
# -----------------------------

def signal_handler(signum, frame):
    """Handles signals for graceful shutdown."""
    global _SHUTDOWN_REQUESTED 
    set_bot_state("SHUTTING_DOWN") # Set state immediately on signal
    logger.info(f"{Fore.RED}Interruption signal ({signum}) received. Initiating graceful shutdown...{NC}")
    _SHUTDOWN_REQUESTED = True
    send_toast("MMXCEL: Shutdown initiated.", "red", "white")

# Register the signal handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

async def read_hotkey(timeout: float = 0.1) -> Optional[str]:
    """Reads a single character from stdin if available, without blocking."""
    rlist, _, _ = select.select([sys.stdin], [], [], timeout)
    if rlist:
        return sys.stdin.read(1)
    return None

async def main():
    """The main invocation of Pyrmethus's market-making spell."""
    global _HAS_TERMUX_TOAST_CMD
    global _SHUTDOWN_REQUESTED 

    _HAS_TERMUX_TOAST_CMD = check_termux_toast()

    print_neon_header("MMXCEL - Bybit Hedge-Mode Market-Making Bot", color=UNDERLINE)
    print(f"{Fore.CYAN}  {BOLD}A creation by Pyrmethus, the Termux Coding Wizard{NC}")
    print_neon_separator()

    set_bot_state("INITIALIZING")

    if not API_KEY or not API_SECRET:
        logger.error(f"{RED}API_KEY or API_SECRET not found in .env. Aborting ritual.{NC}")
        send_toast("MMXCEL: API keys missing!", "red", "white")
        set_bot_state("SHUTTING_DOWN")
        sys.exit(1)

    client = BybitClient(API_KEY, API_SECRET, USE_TESTNET)
    strategy = MarketMakingStrategy(client)

    logger.info(f"{Fore.YELLOW}Testing the connection to the Bybit API realm...{NC}")
    if not await client.test_credentials():
        logger.error(f"{RED}Failed to validate API credentials. Check your .env file and network connection.{NC}")
        send_toast("MMXCEL: Credential validation failed!", "red", "white")
        set_bot_state("SHUTTING_DOWN")
        sys.exit(1)

    logger.info(f"{Fore.YELLOW}Unveiling the hidden paths of {SYMBOL}...{NC}")
    if not await client.get_symbol_info():
        logger.error(f"{RED}Failed to retrieve symbol information for {SYMBOL}. Is the symbol correct?{NC}")
        send_toast(f"MMXCEL: Failed to get {SYMBOL} info!", "red", "white")
        set_bot_state("SHUTTING_DOWN")
        sys.exit(1)

    logger.info(f"{Fore.GREEN}All preliminary checks complete. The realm is ready for our spell!{NC}")
    send_toast("MMXCEL: Bot initializing...", "green", "white")

    strategy.running = True
    client.start_websockets()

    strategy.ws_monitor_task = asyncio.create_task(client._monitor_websockets(strategy), name="ws_monitor_task")
    strategy.pnl_monitor_task = asyncio.create_task(strategy.monitor_pnl(), name="pnl_monitor_task")

    # Initial sync of data via REST
    await client.get_open_orders_rest()
    await client.get_positions_rest()
    await client.get_balance()

    last_order_refresh_time = 0
    last_balance_refresh_time = 0
    
    set_bot_state("ACTIVE") # Set to active after all initialization

    try:
        while strategy.running and not _SHUTDOWN_REQUESTED:
            clear_screen()
            print_neon_header(f"MMXCEL - Market Making Live (Symbol: {SYMBOL}, Testnet: {USE_TESTNET})", color=UNDERLINE)
            
            price_disp_precision = _calculate_decimal_precision(symbol_info["price_precision"])
            qty_disp_precision = _calculate_decimal_precision(symbol_info["qty_precision"])

            print(f"{Fore.CYAN}{BOLD}Bot State:{NC}")
            print(format_metric("Current State", BOT_STATE, Fore.YELLOW))
            print_neon_separator(char="═")

            print(f"{Fore.CYAN}{BOLD}Market Data & Status:{NC}")
            print(format_metric("Mid Price", ws_state["mid_price"], Fore.BLUE, value_precision=price_disp_precision))
            print(format_metric("Best Bid", ws_state["best_bid"], Fore.BLUE, value_precision=price_disp_precision))
            print(format_metric("Best Ask", ws_state["best_ask"], Fore.BLUE, value_precision=price_disp_precision))
            print(format_metric("Data Freshness (s)", (time.time() - ws_state["last_update_time"]), Fore.MAGENTA, value_precision=1))
            print_neon_separator(char="═")

            print(f"{Fore.CYAN}{BOLD}Account Information:{NC}")
            print(format_metric("Available Balance (USDT)", ws_state["available_balance"], Fore.GREEN, value_precision=4))
            print(format_metric("Last Balance Update (s)", (time.time() - ws_state["last_balance_update"]), Fore.MAGENTA, value_precision=0))
            print_neon_separator(char="═")

            print(f"{Fore.CYAN}{BOLD}Current Positions ({SYMBOL}):{NC}")
            long_pos = ws_state["positions"].get("Long", {"size": Decimal("0"), "unrealisedPnl": Decimal("0")})
            short_pos = ws_state["positions"].get("Short", {"size": Decimal("0"), "unrealisedPnl": Decimal("0")})
            
            print(format_metric("Long Size", long_pos["size"], Fore.GREEN, value_precision=qty_disp_precision))
            print(format_metric("Long PnL", long_pos["unrealisedPnl"], Fore.GREEN, value_precision=4, is_pnl=True))
            print(format_metric("Short Size", short_pos["size"], Fore.RED, value_precision=qty_disp_precision))
            print(format_metric("Short PnL", short_pos["unrealisedPnl"], Fore.RED, value_precision=4, is_pnl=True))
            print(format_metric("Net Position", long_pos["size"] - short_pos["size"], Fore.YELLOW, value_precision=qty_disp_precision))
            print_neon_separator(char="═")

            print(f"{Fore.CYAN}{BOLD}Active Orders ({len(ws_state['open_orders'])}):{NC}")
            if not ws_state["open_orders"]:
                print(f"{Fore.YELLOW}  No active orders channeling the market's flow.{NC}")
            else:
                for oid, order in ws_state["open_orders"].items():
                    price_color = GREEN if order['side'] == 'Buy' else RED
                    print(f"  {order['side']} {order['qty']:.{qty_disp_precision}f} @ {price_color}{order['price']:.{price_disp_precision}f}{NC} (Client: {order['client_order_id']})")
            print_neon_separator(char="═")

            print(f"{Fore.CYAN}{BOLD}Session Statistics:{NC}")
            elapsed_time = time.time() - session_stats["start_time"]
            hours, rem = divmod(elapsed_time, 3600)
            minutes, seconds = divmod(rem, 60)
            print(format_metric("Uptime", f"{int(hours):02d}h {int(minutes):02d}m {int(seconds):02d}s", Fore.MAGENTA))
            print(format_metric("Orders Placed", session_stats["orders_placed"], Fore.MAGENTA))
            print(format_metric("Orders Filled", session_stats["orders_filled"], Fore.MAGENTA))
            print(format_metric("Rebalances Triggered", session_stats["rebalances_count"], Fore.MAGENTA))
            total_session_pnl = long_pos["unrealisedPnl"] + short_pos["unrealisedPnl"]
            print(format_metric("Total Unrealized PnL", total_session_pnl, Fore.MAGENTA, is_pnl=True, value_precision=4))
            print(format_metric("Circuit Breaker Hits", session_stats["circuit_breaker_activations"], Fore.RED))
            print_neon_separator()
            print(f"{Fore.YELLOW}Type 'q' to quit, 'c' to cancel all orders, 'r' to force rebalance.{NC}")


            # Perform periodic tasks
            if time.time() - last_order_refresh_time >= ORDER_REFRESH_INTERVAL:
                await client.get_open_orders_rest()
                await strategy.place_market_making_orders()
                last_order_refresh_time = time.time()

            if time.time() - last_balance_refresh_time >= BALANCE_REFRESH_INTERVAL: # Use configurable BALANCE_REFRESH_INTERVAL
                await client.get_balance()
                last_balance_refresh_time = time.time()

            # Rebalance task: Create a new task if the previous one is done or was never started.
            # Only run rebalance if bot is not in circuit break or already rebalancing
            if BOT_STATE not in ["CIRCUIT_BREAK"] and (strategy.rebalance_task is None or strategy.rebalance_task.done()):
                strategy.rebalance_task = asyncio.create_task(strategy.rebalance_inventory(), name="rebalance_task")
            
            key = await read_hotkey(timeout=1)
            if key == 'q':
                _SHUTDOWN_REQUESTED = True
            elif key == 'c':
                logger.warning(f"{Fore.YELLOW}Hotkey 'c' pressed. Cancelling all open orders...{NC}")
                send_toast("MMXCEL: Cancelling all orders.", "orange", "white")
                await client.cancel_all_orders()
                await client.get_open_orders_rest()
            elif key == 'r':
                logger.warning(f"{Fore.YELLOW}Hotkey 'r' pressed. Forcing rebalance...{NC}")
                send_toast("MMXCEL: Forcing rebalance.", "purple", "white")
                if strategy.rebalance_task and not strategy.rebalance_task.done():
                    strategy.rebalance_task.cancel()
                    try: await strategy.rebalance_task # Await to clear cancellation
                    except asyncio.CancelledError: pass
                strategy.rebalance_task = asyncio.create_task(strategy.rebalance_inventory(), name="rebalance_task")

    except asyncio.CancelledError:
        logger.info(f"{Fore.MAGENTA}Main loop cancelled, initiating cleanup...{NC}")
    except Exception as e:
        logger.critical(f"{RED}An unhandled exception halted the spell: {type(e).__name__} - {e}{NC}", exc_info=True)
        send_toast(f"MMXCEL: Critical Error! {type(e).__name__}", "red", "white")
    finally:
        strategy.running = False
        set_bot_state("SHUTTING_DOWN") # Ensure state is shutting down for final logs
        logger.info(f"{Fore.MAGENTA}Cancelling remaining tasks and closing connections...{NC}")
        
        # Gather all tasks to ensure they are cancelled and cleaned up
        await asyncio.gather(
            *(task for task in [strategy.rebalance_task, strategy.pnl_monitor_task, strategy.ws_monitor_task] if task is not None and not task.done()),
            return_exceptions=True # Allow individual task cancellation/exception not to stop others
        )
        
        await client.cancel_all_orders() # Final attempt to clean up orders
        # Explicitly call exit() to clean up pybit's internal threads/connections
        client.ws_public.exit()
        client.ws_private.exit()
        logger.info(f"{Fore.GREEN}MMXCEL spell gracefully concluded. May your digital journey be ever enlightened.{NC}")
        send_toast("MMXCEL: Shutdown complete.", "green", "white")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info(f"{Fore.RED}KeyboardInterrupt detected. Exiting.{NC}")
    except Exception as e:
        logger.critical(f"{RED}Fatal error during bot execution: {type(e).__name__} - {e}{NC}")
import os
import asyncio
import logging.handlers # For RotatingFileHandler
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
    # Use a generic toast if termux-api isn't guaranteed to be installed yet
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
POSITION_MODE = config.get("POSITION_MODE", "HedgeMode") # "HedgeMode" or "OneWayMode"
ORDER_REFRESH_INTERVAL = config.get("ORDER_REFRESH_INTERVAL", 5) # How often to check for order refreshes in seconds
MIN_ORDER_REFRESH_INTERVAL = config.get("MIN_ORDER_REFRESH_INTERVAL", 1) # Minimum time between order refreshes to prevent API spam
MAX_ORDER_REFRESH_INTERVAL = config.get("MAX_ORDER_REFRESH_INTERVAL", 60) # Maximum time between order refreshes to prevent stale orders
COIN_FOR_BALANCE = config.get("COIN_FOR_BALANCE", "USDT")

# --- Global Symbol Info Placeholder (to be fetched from exchange) ---
# This will store dynamic precision values crucial for accurate trading.
symbol_info = {
    "price_precision": Decimal("0.0001"), # Default, will be updated by get_symbol_info
    "qty_precision": Decimal("0.001")     # Default, will be updated by get_symbol_info
}

# --- Termux Toast Helper ---
_TERMUX_TOAST_ENABLED = False
def _check_termux_toast_availability():
    global _TERMUX_TOAST_ENABLED
    if os.system("command -v termux-toast > /dev/null 2>&1") == 0:
        _TERMUX_TOAST_ENABLED = True
    else:
        logger.warning(f"{YELLOW}Warning: 'termux-toast' command not found. Toasts will be disabled. "
                       f"Please install it via 'pkg install termux-api' and the Termux:API app if you are on Termux.{NC}")

def send_toast(message: str, background_color: str = 'green', text_color: str = 'white', duration: int = 3000):
    """Sends a toast notification via Termux:API if available."""
    if _TERMUX_TOAST_ENABLED:
        try:
            os.system(f"termux-toast -b '{background_color}' -c '{text_color}' -t {duration} '{message}'")
        except Exception as e:
            logger.error(f"Failed to send Termux toast: {e}")

# Helper function to get precision from a Decimal value for display
def _calculate_decimal_precision(value: Decimal) -> int:
    """Calculates the number of decimal places of a Decimal value.
    This is for display formatting, not for exchange-specific precision."""
    if value == Decimal("0"):
        return 0 # Or a default display precision if desired for zero
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
        # Determine precision dynamically for Decimals if not specified
        current_precision = value_precision if value_precision is not None else _calculate_decimal_precision(Decimal(str(value)))

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
    # Use f-string formatting with dynamic precision
    formatted_price = f"{order['price']:.{price_precision}f}" if price_precision is not None else str(order['price'])
    formatted_qty = f"{order['qty']:.{qty_precision}f}" if qty_precision is not None else str(order['qty'])
    return f"  [{side_color}{order['side']}{NC}] @ {formatted_price} Qty: {formatted_qty} (Client ID: {client_id})"

def format_position(position: Dict[str, Any], side: str, price_precision: int, qty_precision: int) -> str:
    """Formats a position for display in the UI."""
    side_color = GREEN if side == 'Long' else RED
    # Use f-string formatting with dynamic precision
    formatted_size = f"{position['size']:.{qty_precision}f}" if qty_precision is not None else str(position['size'])
    formatted_avg_price = f"{position['avg_price']:.{price_precision}f}" if price_precision is not None else str(position['avg_price'])
    return f"  {side_color}{side}{NC} Position: {formatted_size} @ {formatted_avg_price} | Unrealized PnL: {position['unrealisedPnl']:.2f} USDT"

# --- WebSocket Listener ---
# Shared state for WebSocket updates, a crystal ball reflecting market reality
ws_state = {
    "mid_price": Decimal("0"),
    "best_bid": Decimal("0"),
    "best_ask": Decimal("0"),
    "open_orders": {},
    "positions": {}, # Stores 'Long' and 'Short' positions
    "last_update_time": 0
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
                logger.debug(f"WS Orderbook: Mid Price: {ws_state['mid_price']:.{_calculate_decimal_precision(symbol_info['price_precision'])}f}")
    except (KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError) as e:
        logger.error(f"Error processing public WS message: {type(e).__name__} - {e} | Message: {message}", exc_info=True)

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
                        logger.info(f"WS Order Update: Order {order_id} (Client ID: {order_update.get('orderLinkId')}) for {order_update.get('symbol')} is {order_update['orderStatus']}.")
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
        logger.error(f"Error processing private WS message: {type(e).__name__} - {e} | Message: {message}", exc_info=True)

class BybitClient:
    """The Grand Conjuror, interacting with the Bybit exchange."""
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 2 # Initial delay, will double on each retry

    def __init__(self, api_key: str, api_secret: str, testnet: bool):
        self.http_session = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret)
        self.ws_public = WebSocket(testnet=testnet, channel_type="linear") # For linear/inverse
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

                ret_code = response.get('retCode')
                error_msg = response.get('retMsg', f"Unknown error (retCode: {ret_code})")
                logger.warning(f"API call to {api_method.__name__} failed (Attempt {attempt + 1}/{self.MAX_RETRIES}) with retCode {ret_code}: {error_msg} | Args: {args}, Kwargs: {kwargs}")

                # Specific error codes that might warrant a retry (e.g., rate limits, internal server errors)
                # Bybit API codes for retrying: 10001 (System error), 10006 (Too many requests),
                # 30034 (Spot order placement failed), 30035 (Too many spot order requests)
                # 10002 (Parameter error) - generally not retryable, but if transient, can be.
                if ret_code in [10001, 10006, 30034, 30035]: # Add 10002 if parameter errors are sometimes transient
                    if attempt < self.MAX_RETRIES - 1:
                        delay = self.RETRY_DELAY_SECONDS * (2 ** attempt)
                        logger.warning(f"Retrying {api_method.__name__} in {delay} seconds...")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"API call {api_method.__name__} exhausted retries: {error_msg}")
                        return None
                else:
                    # For non-retryable errors (e.g., invalid parameters), don't retry
                    logger.error(f"Non-retryable API error for {api_method.__name__}: {error_msg}")
                    return None
            except Exception as e:
                logger.error(f"Exception during API call to {api_method.__name__} (Attempt {attempt + 1}/{self.MAX_RETRIES}): {type(e).__name__} - {e} | Args: {args}, Kwargs: {kwargs}", exc_info=True)
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAY_SECONDS * (2 ** attempt)
                    logger.warning(f"Retrying {api_method.__name__} in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"API call exception for {api_method.__name__} exhausted retries: {type(e).__name__} - {e}")
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

    async def set_position_mode(self, mode: str) -> bool:
        """Sets the position mode (e.g., HedgeMode, OneWayMode) for the category.
           For linear/inverse, 'mode' typically refers to 'HedgeMode' or 'OneWayMode' as strings,
           or positionIdx 1/2 for Buy/Sell respectively in HedgeMode.
           The pybit library handles the mapping for set_position_mode.
        """
        if CATEGORY not in ["linear", "inverse"]:
            logger.warning(f"Position mode setting is typically for linear/inverse. Current category: {CATEGORY}. Skipping.")
            return True # Not applicable or handled elsewhere

        # Note: Bybit API for set_position_mode uses mode '3' for HedgeMode, '0' for One-Way Mode
        # for unified accounts, but for non-unified (like linear/inverse perpetuals) it's often
        # a string "HedgeMode" or "OneWayMode" or determined by positionIdx.
        # The pybit library's `set_position_mode` handles this, accepting string 'HedgeMode' or 'OneWayMode'.
        if mode not in ["HedgeMode", "OneWayMode"]:
            logger.error(f"Invalid position mode '{mode}'. Must be 'HedgeMode' or 'OneWayMode'.")
            return False

        response = await self._make_api_call(
            self.http_session.set_position_mode,
            category=CATEGORY,
            symbol=SYMBOL, # Symbol is required for this call
            mode=mode
        )
        if response and response.get('retCode') == 0:
            logger.info(f"Successfully set position mode to {mode} for {SYMBOL} in {CATEGORY} category.")
            return True
        else:
            logger.warning(f"Failed to set position mode to {mode} for {SYMBOL}: {response.get('retMsg', 'No error message')}. "
                           "This might be expected if already set, or indicate an API issue. "
                           "Ensure your desired mode is enabled for this symbol in your Bybit account settings. Proceeding...")
            return False

    def start_websocket_streams(self):
        """Starts public and private websocket streams, opening channels to the ether."""
        try:
            self.ws_public.orderbook_stream(
                symbol=SYMBOL,
                depth=1,
                callback=on_public_ws_message
            )
            self.ws_private.order_stream(callback=on_private_ws_message)
            self.ws_private.position_stream(callback=on_private_ws_message)
            logger.info("WebSocket streams started and listening for real-time updates.")
        except Exception as e:
            logger.error(f"Error starting WebSocket streams: {type(e).__name__} - {e}", exc_info=True)
            send_toast(f"MMXCEL Critical: WS streams failed to start for {SYMBOL}!", 'red', 'white')
            raise # Re-raise to halt execution if core communication fails

    async def get_balance(self, account_type: str = "UNIFIED", coin: str = COIN_FOR_BALANCE) -> Decimal:
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
                available_balance_str = balance_info.get('availableToWithdraw')

                if available_balance_str is None or available_balance_str == '':
                    self.current_balance = Decimal("0")
                    logger.warning(f"Available balance for {coin} was None or empty string from API, defaulting to 0. (Raw: '{available_balance_str}')")
                else:
                    try:
                        self.current_balance = Decimal(str(available_balance_str))
                    except Exception as e:
                        logger.error(f"Failed to transmute '{available_balance_str}' to Decimal: {type(e).__name__} - {e}. Defaulting to 0.", exc_info=True)
                        self.current_balance = Decimal("0")
                return self.current_balance
            logger.error(f"Unexpected balance response structure: {response.get('retMsg', 'No error message')} | Raw: {response}")
            return Decimal("0")
        else:
            logger.error(f"Failed to get balance for {coin}: {response.get('retMsg', 'No error message') if response else 'No response'}")
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
            logger.error(f"Failed to get open orders via REST for {SYMBOL}: {response.get('retMsg', 'No error message') if response else 'No response'}")
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
            logger.error(f"Failed to get positions via REST for {SYMBOL}: {response.get('retMsg', 'No error message') if response else 'No response'}")
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
            logger.error(f"Attempted to place order with non-positive quantized quantity: {quantized_qty} for {SYMBOL} {side}.")
            return None

        try:
            order_payload = {
                "category": CATEGORY,
                "symbol": SYMBOL,
                "side": side,
                "orderType": order_type,
                "qty": str(quantized_qty),
                "positionIdx": 1 if side == "Buy" else 2 # 1 for long, 2 for short in HedgeMode
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
                log_msg = f"Placed {order_type} {side} order for {SYMBOL}: {order_info.get('orderId', 'N/A')}"
                if quantized_price is not None:
                    log_msg += f" @ {quantized_price}"
                log_msg += f" Qty: {quantized_qty}"
                if client_order_id is not None:
                    log_msg += f" (Client ID: {client_order_id})"
                logger.info(log_msg)
                return order_info
            else:
                logger.error(f"Failed to place {order_type} {side} order for {SYMBOL} {quantized_qty}@{quantized_price if quantized_price else 'N/A'}: {response.get('retMsg', 'No error message') if response else 'No response'}")
                return None
        except Exception as e:
            logger.error(f"Error placing order for {SYMBOL} {side} {quantized_qty}@{quantized_price if quantized_price else 'N/A'} (Type: {order_type}): {type(e).__name__} - {e}", exc_info=True)
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
            logger.info(f"Cancelled order: {order_id} for {SYMBOL}")
            return True
        else:
            logger.error(f"Failed to cancel order {order_id} for {SYMBOL}: {response.get('retMsg', 'No error message') if response else 'No response'}")
            return False

    async def cancel_all_orders(self) -> None:
        """Cancels all open orders for the symbol, sweeping the slate clean."""
        response = await self._make_api_call(
            self.http_session.cancel_all_orders,
            category=CATEGORY,
            symbol=SYMBOL
        )
        if response and response.get('retCode') == 0:
            logger.info(f"Successfully cancelled all open orders for {SYMBOL}.")
            ws_state["open_orders"].clear()
        else:
            logger.error(f"Failed to cancel all orders for {SYMBOL}: {response.get('retMsg', 'No error message') if response else 'No response'}")

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
                logger.warning(f"Skipping batch order with non-positive quantized quantity: {quantized_qty} for {order.get('side')} {SYMBOL}")
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

        response = await self._make_api_call(self.http_session.place_batch_order, batch_request_payload)

        if response and response.get('retCode') == 0:
            logger.info(f"Successfully placed {len(batch_request_payload['request'])} batch orders for {SYMBOL}.")
            return response['result']
        else:
            logger.error(f"Failed to place batch orders for {SYMBOL}: {response.get('retMsg', 'No error message') if response else 'No response'}")
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
            if orderbook and 'bids' in orderbook and 'asks' in orderbook:
                best_bid = Decimal(orderbook['bids'][0][0]) if orderbook['bids'] else Decimal("0")
                best_ask = Decimal(orderbook['asks'][0][0]) if orderbook['asks'] else Decimal("0")
                mid_price = (best_bid + best_ask) / Decimal("2")
                ws_state["best_bid"] = best_bid
                ws_state["best_ask"] = best_ask
                ws_state["mid_price"] = mid_price
                ws_state["last_update_time"] = time.time()
                logger.debug(f"Orderbook snapshot: Mid Price: {mid_price:.{_calculate_decimal_precision(symbol_info['price_precision'])}f}")
                return orderbook
            else:
                logger.error(f"Orderbook snapshot for {SYMBOL} returned but missing bids/asks data.")
                return None
        else:
            logger.error(f"Failed to get orderbook snapshot for {SYMBOL}: {response.get('retMsg', 'No error message') if response else 'No response'}")
            return None

class MarketMakingStrategy:
    """The Alchemist's Strategy, overseeing the delicate balance of market forces."""
    def __init__(self, client: BybitClient):
        self.client = client
        self.running = False
        self.rebalance_task = None
        self.stop_loss_task = None
        self.exit_flag = asyncio.Event()
        self.last_mid_price = Decimal("0") # Track last mid-price for dynamic order replacement
        self.last_order_refresh_time = 0
        self.order_refresh_interval = ORDER_REFRESH_INTERVAL
        self.min_order_refresh_interval = MIN_ORDER_REFRESH_INTERVAL
        self.max_order_refresh_interval = MAX_ORDER_REFRESH_INTERVAL
        self.order_refresh_counter = 0
        self.max_order_refresh_attempts = 3 # Maximum attempts to refresh orders before giving up

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
        if not isinstance(MAX_OPEN_ORDERS, int) or MAX_OPEN_ORDERS <= 0:
            logger.critical(f"{RED}Config Error: MAX_OPEN_ORDERS must be a positive integer. Current: {MAX_OPEN_ORDERS}{NC}")
            is_valid = False
        if not isinstance(ORDER_LIFESPAN_SECONDS, int) or ORDER_LIFESPAN_SECONDS <= 0:
            logger.critical(f"{RED}Config Error: ORDER_LIFESPAN_SECONDS must be a positive integer. Current: {ORDER_LIFESPAN_SECONDS}{NC}")
            is_valid = False
        if not isinstance(ORDER_REFRESH_INTERVAL, int) or ORDER_REFRESH_INTERVAL <= 0:
            logger.critical(f"{RED}Config Error: ORDER_REFRESH_INTERVAL must be a positive integer. Current: {ORDER_REFRESH_INTERVAL}{NC}")
            is_valid = False
        if not isinstance(MIN_ORDER_REFRESH_INTERVAL, int) or MIN_ORDER_REFRESH_INTERVAL <= 0 or MIN_ORDER_REFRESH_INTERVAL > ORDER_REFRESH_INTERVAL:
            logger.critical(f"{RED}Config Error: MIN_ORDER_REFRESH_INTERVAL must be a positive integer <= ORDER_REFRESH_INTERVAL. Current: {MIN_ORDER_REFRESH_INTERVAL}{NC}")
            is_valid = False
        if not isinstance(MAX_ORDER_REFRESH_INTERVAL, int) or MAX_ORDER_REFRESH_INTERVAL <= 0 or MAX_ORDER_REFRESH_INTERVAL < ORDER_REFRESH_INTERVAL:
            logger.critical(f"{RED}Config Error: MAX_ORDER_REFRESH_INTERVAL must be a positive integer >= ORDER_REFRESH_INTERVAL. Current: {MAX_ORDER_REFRESH_INTERVAL}{NC}")
            is_valid = False

        if SPREAD_PERCENTAGE >= PRICE_THRESHOLD and PRICE_THRESHOLD > 0:
            logger.warning(f"{YELLOW}Warning: SPREAD_PERCENTAGE ({SPREAD_PERCENTAGE:.4%}) is greater than or equal to PRICE_THRESHOLD ({PRICE_THRESHOLD:.4%}). "
                           "This might lead to frequent order cancellations and re-placements even with small price movements or fills.{NC}")

        if PROFIT_PERCENTAGE <= SPREAD_PERCENTAGE:
            logger.warning(f"{YELLOW}Warning: PROFIT_PERCENTAGE ({PROFIT_PERCENTAGE:.4%}) is less than or equal to SPREAD_PERCENTAGE ({SPREAD_PERCENTAGE:.4%}). "
                           "This might lead to trades that barely cover fees or are unprofitable.{NC}")

        # Warning for QUANTITY being too small relative to symbol's qty_precision
        if QUANTITY < symbol_info["qty_precision"] * 2: # Check if QUANTITY is very close to minimum step
             logger.warning(f"{YELLOW}Warning: Configured QUANTITY ({QUANTITY}) is very small compared to the exchange's minimum quantity step ({symbol_info['qty_precision']}). "
                            "This might lead to issues if exchange minimums are higher, or if positions become too small to rebalance/close effectively.{NC}")


        return is_valid

    async def place_market_making_orders(self):
        """Manages the placement of market-making orders based on real-time data."""
        # First, check if we have valid market data
        if not self._is_market_data_available():
            return

        current_time = time.time()

        # Check if it's time to refresh orders
        if current_time - self.last_order_refresh_time >= self.order_refresh_interval:
            self.order_refresh_counter += 1
            self.last_order_refresh_time = current_time

            # Dynamically adjust the refresh interval based on recent activity
            # If we've tried to refresh multiple times without success (e.g., API errors), increase the interval
            if self.order_refresh_counter >= self.max_order_refresh_attempts:
                self.order_refresh_interval = min(self.order_refresh_interval * 2, self.max_order_refresh_interval)
                logger.info(f"Increasing order refresh interval to {self.order_refresh_interval} seconds due to multiple attempts without successful order placement/management.")
                self.order_refresh_counter = 0 # Reset counter after adjustment
            else:
                # If we successfully managed orders (or attempted to), reset counter and consider decreasing interval
                self.order_refresh_counter = 0
                if self.order_refresh_interval > self.min_order_refresh_interval:
                    self.order_refresh_interval = max(self.order_refresh_interval * 0.9, self.min_order_refresh_interval)
                    logger.debug(f"Decreasing order refresh interval to {self.order_refresh_interval:.2f} seconds.")


            # Check if price has moved significantly to trigger re-placement
            mid_price = ws_state["mid_price"]
            price_change_percentage = Decimal("0")
            if self.last_mid_price != Decimal("0") and mid_price != Decimal("0"):
                if self.last_mid_price == mid_price:
                    price_change_percentage = Decimal("0")
                else:
                    price_change_percentage = abs(mid_price - self.last_mid_price) / self.last_mid_price

                if price_change_percentage >= PRICE_THRESHOLD:
                    logger.info(f"Price moved {price_change_percentage:.4%} (>= {PRICE_THRESHOLD:.4%}). Cancelling all orders to re-place for {SYMBOL}.")
                    await self.client.cancel_all_orders()
                    # Do not reset last_mid_price yet, it will be updated after new orders are placed
                else:
                    # If price hasn't moved significantly, and we already have orders, skip placing new ones
                    if ws_state["open_orders"]:
                        logger.debug(f"No significant price change for {SYMBOL} and orders exist. Skipping new order placement.")
                        return # Skip placing new orders if price hasn't moved and orders are already out

            # Check for stale orders and cancel them, removing forgotten spirits
            orders_to_cancel_ids = [
                order_id for order_id, details in list(ws_state["open_orders"].items())
                if time.time() - details['timestamp'] > ORDER_LIFESPAN_SECONDS
            ]
            if orders_to_cancel_ids:
                logger.info(f"Cancelling {len(orders_to_cancel_ids)} stale orders for {SYMBOL} to keep the ledger clean.")
                # Use asyncio.gather for concurrent cancellation if multiple stale orders
                await asyncio.gather(*[self.client.cancel_order(oid) for oid in orders_to_cancel_ids])

            # Get fresh state from REST to handle any missed WS updates, ensuring perfect synchronicity
            await self.client.get_open_orders_rest()

            # Check if we have too many open orders, avoiding over-committing arcane energy
            if len(ws_state["open_orders"]) >= MAX_OPEN_ORDERS:
                logger.info(f"Max open orders ({MAX_OPEN_ORDERS}) reached for {SYMBOL}. Skipping new order placement.")
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
            else:
                logger.debug(f"No new orders to place for {SYMBOL} at this time (e.g., max orders reached or existing orders are fine).")


    def _is_market_data_available(self) -> bool:
        """Helper to check if market data is available, avoiding redundant checks."""
        if ws_state["mid_price"] == Decimal("0") or ws_state["best_bid"] == Decimal("0") or ws_state["best_ask"] == Decimal("0"):
            logger.warning(f"Market data (mid, bid, ask) for {SYMBOL} not available yet. Skipping operation.")
            return False
        return True

    async def rebalance_inventory(self):
        """Periodically rebalances inventory (position) to a neutral state, maintaining equilibrium."""
        if not self._is_market_data_available():
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
                logger.warning(f"Quantized rebalance quantity for {SYMBOL} is zero ({quantized_qty_to_rebalance}), skipping rebalance.")
                return

            logger.warning(f"{YELLOW}Inventory imbalance detected for {SYMBOL}. Net position: {net_position:.{_calculate_decimal_precision(symbol_info['qty_precision'])}f}. "
                             f"Attempting to rebalance by placing a {side_to_rebalance} market order for {quantized_qty_to_rebalance}.{NC}")
            send_toast(f"MMXCEL: Rebalancing {quantized_qty_to_rebalance:.{_calculate_decimal_precision(symbol_info['qty_precision'])}f} {SYMBOL}!", 'yellow', 'black')

            # Place a market order to quickly rebalance
            client_rebalance_id = f"mmxcel-rebal-{int(time.time() * 1000)}"
            asyncio.create_task(self.client.place_order(side_to_rebalance, quantized_qty_to_rebalance, order_type="Market", client_order_id=client_rebalance_id))
        else:
            logger.debug(f"No significant inventory imbalance for {SYMBOL}. Net position: {net_position:.{_calculate_decimal_precision(symbol_info['qty_precision'])}f}.")


    async def manage_stop_loss_and_profit_take(self):
        """Monitors positions for stop-loss and profit-taking opportunities, safeguarding and harvesting gains."""
        if not self._is_market_data_available():
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
                pnl_percentage = pnl_usdt / (long_avg_price * long_size)  # Corrected: PnL as percentage of entry value

            # Quantize the size before placing a closing order
            quantized_long_size = long_size.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            if quantized_long_size <= 0:
                logger.warning(f"Quantized long closing quantity for {SYMBOL} is zero ({quantized_long_size}), skipping close.")
            elif pnl_percentage < -STOP_LOSS_PERCENTAGE:
                logger.critical(f"{RED}Stop-loss triggered for LONG position on {SYMBOL}! Unrealised PnL: {pnl_usdt:.2f} USDT ({pnl_percentage:.2%}). "
                                 f"Placing market sell order to close {quantized_long_size}.{NC}")
                send_toast(f"MMXCEL: LONG SL triggered for {SYMBOL}! PnL: {pnl_usdt:.2f} USDT", 'red', 'white')
                asyncio.create_task(self.client.place_order("Sell", quantized_long_size, order_type="Market", client_order_id=f"mmxcel-sl-long-{int(time.time() * 1000)}"))
            elif pnl_percentage >= PROFIT_PERCENTAGE:
                logger.info(f"{GREEN}Profit-take triggered for LONG position on {SYMBOL}. Unrealised PnL: {pnl_usdt:.2f} USDT ({pnl_percentage:.2%}). "
                                 f"Placing market sell order to close {quantized_long_size}.{NC}")
                send_toast(f"MMXCEL: LONG TP triggered for {SYMBOL}! PnL: {pnl_usdt:.2f} USDT", 'green', 'black')
                asyncio.create_task(self.client.place_order("Sell", quantized_long_size, order_type="Market", client_order_id=f"mmxcel-tp-long-{int(time.time() * 1000)}"))
            else:
                logger.debug(f"Long position for {SYMBOL} within acceptable PnL range. Current PnL: {pnl_usdt:.2f} USDT ({pnl_percentage:.2%}).")


        # Check short position
        short_pos = ws_state['positions'].get('Short', {})
        short_size = short_pos.get('size', Decimal('0'))
        short_avg_price = short_pos.get('avg_price', Decimal('0'))

        if short_size > 0 and short_avg_price > 0: # Ensure valid position
            pnl_usdt = short_pos.get('unrealisedPnl', Decimal('0'))

            pnl_percentage = Decimal('0')
            if (short_avg_price * short_size) > 0:
                pnl_percentage = pnl_usdt / (short_avg_price * short_size)  # Corrected: PnL as percentage of entry value

            # Quantize the size before placing a closing order
            quantized_short_size = short_size.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            if quantized_short_size <= 0:
                logger.warning(f"Quantized short closing quantity for {SYMBOL} is zero ({quantized_short_size}), skipping close.")
            elif pnl_percentage < -STOP_LOSS_PERCENTAGE:
                logger.critical(f"{RED}Stop-loss triggered for SHORT position on {SYMBOL}! Unrealised PnL: {pnl_usdt:.2f} USDT ({pnl_percentage:.2%}). "
                                 f"Placing market buy order to close {quantized_short_size}.{NC}")
                send_toast(f"MMXCEL: SHORT SL triggered for {SYMBOL}! PnL: {pnl_usdt:.2f} USDT", 'red', 'white')
                asyncio.create_task(self.client.place_order("Buy", quantized_short_size, order_type="Market", client_order_id=f"mmxcel-sl-short-{int(time.time() * 1000)}"))
            elif pnl_percentage >= PROFIT_PERCENTAGE:
                logger.info(f"{GREEN}Profit-take triggered for SHORT position on {SYMBOL}. Unrealised PnL: {pnl_usdt:.2f} USDT ({pnl_percentage:.2%}). "
                                 f"Placing market buy order to close {quantized_short_size}.{NC}")
                send_toast(f"MMXCEL: SHORT TP triggered for {SYMBOL}! PnL: {pnl_usdt:.2f} USDT", 'green', 'black')
                asyncio.create_task(self.client.place_order("Buy", quantized_short_size, order_type="Market", client_order_id=f"mmxcel-tp-short-{int(time.time() * 1000)}"))
            else:
                logger.debug(f"Short position for {SYMBOL} within acceptable PnL range. Current PnL: {pnl_usdt:.2f} USDT ({pnl_percentage:.2%}).")


    async def shutdown(self):
        """Gracefully shuts down the bot, including cancelling open orders, and silencing the arcane channels."""
        if self.running:
            self.running = False
            logger.info("Shutdown initiated. Cancelling all open orders...")
            send_toast(f"MMXCEL: Shutting down {SYMBOL}, cancelling orders...", '#FFA500', 'white')
            await self.client.cancel_all_orders()
            # Stop any running tasks
            if self.rebalance_task and not self.rebalance_task.done():
                self.rebalance_task.cancel()
            if self.stop_loss_task and not self.stop_loss_task.done():
                self.stop_loss_task.cancel()

            self.exit_flag.set()
            send_toast(f"MMXCEL: Shutdown complete for {SYMBOL}.", 'green', 'white')

    async def run(self):
        """Unleashes the bot's full power, beginning its market-making vigil."""
        self.running = True

        # Validate configuration values before starting operations
        if not self._validate_config():
            logger.critical("Configuration validation failed. Aborting bot startup.")
            send_toast(f"MMXCEL Config Error for {SYMBOL}! Check logs.", 'red', 'white')
            return

        # Fetch symbol information first, crucial for correct price/quantity handling
        if not await self.client.get_symbol_info():
            logger.critical("Failed to fetch symbol information. Cannot proceed without it.")
            send_toast(f"MMXCEL Error: Symbol info fetch failed for {SYMBOL}!", 'red', 'white')
            return

        # Set position mode (e.g., HedgeMode)
        if not await self.client.set_position_mode(POSITION_MODE):
            logger.critical(f"Failed to set position mode to {POSITION_MODE}. This is critical for the bot's strategy. Aborting.")
            send_toast(f"MMXCEL Error: Failed to set {POSITION_MODE} for {SYMBOL}!", 'red', 'white')
            return

        self.client.start_websocket_streams()

        # Give some time for WS to connect and get initial data from the ether
        await asyncio.sleep(5)

        # Fetch initial state via REST to ensure we don't miss anything
        await self.client.get_balance(coin=COIN_FOR_BALANCE)
        await self.client.get_open_orders_rest()
        await self.client.get_positions_rest() # Explicitly fetch initial positions

        # Start background tasks for rebalancing and stop-loss/profit-taking
        self.rebalance_task = asyncio.create_task(self._periodic_task(self.rebalance_inventory, interval=10, name="Rebalance"))
        self.stop_loss_task = asyncio.create_task(self._periodic_task(self.manage_stop_loss_and_profit_take, interval=2, name="PnL Management"))

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
                print(format_metric("Position Mode", POSITION_MODE, YELLOW, value_color=WHITE, label_width=20))
                print(format_metric("Price Tick Size", symbol_info['price_precision'], YELLOW, value_precision=price_disp_prec, label_width=20))
                print(format_metric("Quantity Step Size", symbol_info['qty_precision'], YELLOW, value_precision=qty_disp_prec, label_width=20))
                print(format_metric("Order Refresh Interval (s)", self.order_refresh_interval, YELLOW, value_color=WHITE, label_width=20))
                print_neon_separator()

                # Market and Account Data
                print(f"{BOLD}{CYAN}--- Current Market & Account Status ---{NC}")
                print(format_metric("Mid Price", ws_state['mid_price'], BLUE, value_precision=price_disp_prec))
                print(format_metric("Best Bid", ws_state['best_bid'], BLUE, value_precision=price_disp_prec))
                print(format_metric("Best Ask", ws_state['best_ask'], BLUE, value_precision=price_disp_prec))
                await self.client.get_balance(coin=COIN_FOR_BALANCE) # Refresh balance every loop for display
                print(format_metric(f"Available Balance ({COIN_FOR_BALANCE})", self.client.current_balance, YELLOW, value_precision=2))
                # Display last market data update time
                last_update_str = datetime.fromtimestamp(ws_state['last_update_time']).strftime('%Y-%m-%d %H:%M:%S') if ws_state['last_update_time'] else "N/A"
                print(format_metric("Last Market Data Update", last_update_str, YELLOW, value_color=WHITE, label_width=20))
                print_neon_separator()

                # Position Details
                print(f"{BOLD}{CYAN}--- Active Positions ({SYMBOL}) ---{NC}")
                long_pos = ws_state['positions'].get('Long', {'size': Decimal('0'), 'unrealisedPnl': Decimal('0'), 'avg_price': Decimal('0')})
                short_pos = ws_state['positions'].get('Short', {'size': Decimal('0'), 'unrealisedPnl': Decimal('0'), 'avg_price': Decimal('0')})

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
            send_toast(f"MMXCEL Critical Error: Bot crashed! Check logs for {SYMBOL}!", 'red', 'white')
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
            logger.error(f"Error in periodic task '{name}': {type(e).__name__} - {e}", exc_info=True)
            send_toast(f"MMXCEL Critical: {name} task failed for {SYMBOL}!", 'red', 'white')
        finally:
            logger.info(f"Periodic task '{name}' has finished.")


def signal_handler(sig, frame):
    """Handles graceful shutdown on SIGINT (Ctrl+C) or SIGTERM."""
    print(f"\n{YELLOW}Termination signal detected! Initiating graceful shutdown...{NC}")
    send_toast(f"MMXCEL: Termination signal received for {SYMBOL}. Shutting down...", '#FFA500', 'white')
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
        sys.exit(0) # Use sys.exit for clean exit if loop not running

async def main():
    """The main incantation, summoning the bot and its powerful strategies."""
    # Check Termux toast availability early
    _check_termux_toast_availability()

    if not API_KEY or not API_SECRET:
        print(f"{RED}BYBIT_API_KEY or BYBIT_API_SECRET not found in .env file. "
              f"Please ensure your magical credentials are in place.{NC}")
        send_toast(f"MMXCEL Error: API credentials missing!", 'red', 'white')
        return

    print(f"{BOLD}{CYAN}MMXCEL Bybit Market Making Bot is being summoned...{NC}")

    client = BybitClient(api_key=API_KEY, api_secret=API_SECRET, testnet=USE_TESTNET)
    strategy = MarketMakingStrategy(client)

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
        send_toast(f"MMXCEL Critical Error: Bot crashed! Check logs for {SYMBOL}!", 'red', 'white')
    finally:
        # Ensure shutdown is called even if an error occurs or after cancellation
        # The strategy.shutdown() is implicitly called by the strategy.run() finally block.
        # This outer finally ensures it's called if run() didn't start or completed abnormally.
        if strategy.running: # Only call if it wasn't already gracefully shut down
            await strategy.shutdown()
        logger.info("Bot execution finished. May your digital journey be ever enlightened.")

if __name__ == '__main__':
    # asyncio.run() handles the creation and closing of the event loop
    asyncio.run(main())import os
import asyncio
import logging.handlers
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
    # Use a generic toast if termux-api isn't guaranteed to be installed yet
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
POSITION_MODE = config.get("POSITION_MODE", "HedgeMode") # "HedgeMode" or "OneWayMode"
ORDER_REFRESH_INTERVAL = config.get("ORDER_REFRESH_INTERVAL", 5) # How often to check for order refreshes in seconds
MIN_ORDER_REFRESH_INTERVAL = config.get("MIN_ORDER_REFRESH_INTERVAL", 1) # Minimum time between order refreshes to prevent API spam
MAX_ORDER_REFRESH_INTERVAL = config.get("MAX_ORDER_REFRESH_INTERVAL", 60) # Maximum time between order refreshes to prevent stale orders
COIN_FOR_BALANCE = config.get("COIN_FOR_BALANCE", "USDT")

# --- Global Symbol Info Placeholder (to be fetched from exchange) ---
# This will store dynamic precision values crucial for accurate trading.
symbol_info = {
    "price_precision": Decimal("0.0001"), # Default, will be updated by get_symbol_info
    "qty_precision": Decimal("0.001")     # Default, will be updated by get_symbol_info
}

# --- Termux Toast Helper ---
_TERMUX_TOAST_ENABLED = False
def _check_termux_toast_availability():
    global _TERMUX_TOAST_ENABLED
    if os.system("command -v termux-toast > /dev/null 2>&1") == 0:
        _TERMUX_TOAST_ENABLED = True
    else:
        logger.warning(f"{YELLOW}Warning: 'termux-toast' command not found. Toasts will be disabled. "
                       f"Please install it via 'pkg install termux-api' and the Termux:API app if you are on Termux.{NC}")

def send_toast(message: str, background_color: str = 'green', text_color: str = 'white', duration: int = 3000):
    """Sends a toast notification via Termux:API if available."""
    if _TERMUX_TOAST_ENABLED:
        try:
            os.system(f"termux-toast -b '{background_color}' -c '{text_color}' -t {duration} '{message}'")
        except Exception as e:
            logger.error(f"Failed to send Termux toast: {e}")

# Helper function to get precision from a Decimal value for display
def _calculate_decimal_precision(value: Decimal) -> int:
    """Calculates the number of decimal places of a Decimal value.
    This is for display formatting, not for exchange-specific precision."""
    if value == Decimal("0"):
        return 0 # Or a default display precision if desired for zero
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
        # Determine precision dynamically for Decimals if not specified
        current_precision = value_precision if value_precision is not None else _calculate_decimal_precision(Decimal(str(value)))

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
    # Use f-string formatting with dynamic precision
    formatted_price = f"{order['price']:.{price_precision}f}" if price_precision is not None else str(order['price'])
    formatted_qty = f"{order['qty']:.{qty_precision}f}" if qty_precision is not None else str(order['qty'])
    return f"  [{side_color}{order['side']}{NC}] @ {formatted_price} Qty: {formatted_qty} (Client ID: {client_id})"

def format_position(position: Dict[str, Any], side: str, price_precision: int, qty_precision: int) -> str:
    """Formats a position for display in the UI."""
    side_color = GREEN if side == 'Long' else RED
    # Use f-string formatting with dynamic precision
    formatted_size = f"{position['size']:.{qty_precision}f}" if qty_precision is not None else str(position['size'])
    formatted_avg_price = f"{position['avg_price']:.{price_precision}f}" if price_precision is not None else str(position['avg_price'])
    return f"  {side_color}{side}{NC} Position: {formatted_size} @ {formatted_avg_price} | Unrealized PnL: {position['unrealisedPnl']:.2f} USDT"

# --- WebSocket Listener ---
# Shared state for WebSocket updates, a crystal ball reflecting market reality
ws_state = {
    "mid_price": Decimal("0"),
    "best_bid": Decimal("0"),
    "best_ask": Decimal("0"),
    "open_orders": {},
    "positions": {}, # Stores 'Long' and 'Short' positions
    "last_update_time": 0
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
                logger.debug(f"WS Orderbook: Mid Price: {ws_state['mid_price']:.{_calculate_decimal_precision(symbol_info['price_precision'])}f}")
    except (KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError) as e:
        logger.error(f"Error processing public WS message: {type(e).__name__} - {e} | Message: {message}", exc_info=True)

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
                        logger.info(f"WS Order Update: Order {order_id} (Client ID: {order_update.get('orderLinkId')}) for {order_update.get('symbol')} is {order_update['orderStatus']}.")
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
        logger.error(f"Error processing private WS message: {type(e).__name__} - {e} | Message: {message}", exc_info=True)

class BybitClient:
    """The Grand Conjuror, interacting with the Bybit exchange."""
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 2 # Initial delay, will double on each retry

    def __init__(self, api_key: str, api_secret: str, testnet: bool):
        self.http_session = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret)
        self.ws_public = WebSocket(testnet=testnet, channel_type="linear") # For linear/inverse
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

                ret_code = response.get('retCode')
                error_msg = response.get('retMsg', f"Unknown error (retCode: {ret_code})")
                logger.warning(f"API call to {api_method.__name__} failed (Attempt {attempt + 1}/{self.MAX_RETRIES}) with retCode {ret_code}: {error_msg} | Args: {args}, Kwargs: {kwargs}")

                # Specific error codes that might warrant a retry (e.g., rate limits, internal server errors)
                # Bybit API codes for retrying: 10001 (System error), 10006 (Too many requests),
                # 30034 (Spot order placement failed), 30035 (Too many spot order requests)
                # 10002 (Parameter error) - generally not retryable, but if transient, can be.
                if ret_code in [10001, 10006, 30034, 30035]: # Add 10002 if parameter errors are sometimes transient
                    if attempt < self.MAX_RETRIES - 1:
                        delay = self.RETRY_DELAY_SECONDS * (2 ** attempt)
                        logger.warning(f"Retrying {api_method.__name__} in {delay} seconds...")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"API call {api_method.__name__} exhausted retries: {error_msg}")
                        return None
                else:
                    # For non-retryable errors (e.g., invalid parameters), don't retry
                    logger.error(f"Non-retryable API error for {api_method.__name__}: {error_msg}")
                    return None
            except Exception as e:
                logger.error(f"Exception during API call to {api_method.__name__} (Attempt {attempt + 1}/{self.MAX_RETRIES}): {type(e).__name__} - {e} | Args: {args}, Kwargs: {kwargs}", exc_info=True)
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAY_SECONDS * (2 ** attempt)
                    logger.warning(f"Retrying {api_method.__name__} in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"API call exception for {api_method.__name__} exhausted retries: {type(e).__name__} - {e}")
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

    async def set_position_mode(self, mode: str) -> bool:
        """Sets the position mode (e.g., HedgeMode, OneWayMode) for the category.
           For linear/inverse, 'mode' typically refers to 'HedgeMode' or 'OneWayMode' as strings,
           or positionIdx 1/2 for Buy/Sell respectively in HedgeMode.
           The pybit library handles the mapping for set_position_mode.
        """
        if CATEGORY not in ["linear", "inverse"]:
            logger.warning(f"Position mode setting is typically for linear/inverse. Current category: {CATEGORY}. Skipping.")
            return True # Not applicable or handled elsewhere

        # Note: Bybit API for set_position_mode uses mode '3' for HedgeMode, '0' for One-Way Mode
        # for unified accounts, but for non-unified (like linear/inverse perpetuals) it's often
        # a string "HedgeMode" or "OneWayMode" or determined by positionIdx.
        # The pybit library's `set_position_mode` handles this, accepting string 'HedgeMode' or 'OneWayMode'.
        if mode not in ["HedgeMode", "OneWayMode"]:
            logger.error(f"Invalid position mode '{mode}'. Must be 'HedgeMode' or 'OneWayMode'.")
            return False

        response = await self._make_api_call(
            self.http_session.set_position_mode,
            category=CATEGORY,
            symbol=SYMBOL, # Symbol is required for this call
            mode=mode
        )
        if response and response.get('retCode') == 0:
            logger.info(f"Successfully set position mode to {mode} for {SYMBOL} in {CATEGORY} category.")
            return True
        else:
            logger.warning(f"Failed to set position mode to {mode} for {SYMBOL}: {response.get('retMsg', 'No error message')}. "
                           "This might be expected if already set, or indicate an API issue. "
                           "Ensure your desired mode is enabled for this symbol in your Bybit account settings. Proceeding...")
            return False

    def start_websocket_streams(self):
        """Starts public and private websocket streams, opening channels to the ether."""
        try:
            self.ws_public.orderbook_stream(
                symbol=SYMBOL,
                depth=1,
                callback=on_public_ws_message
            )
            self.ws_private.order_stream(callback=on_private_ws_message)
            self.ws_private.position_stream(callback=on_private_ws_message)
            logger.info("WebSocket streams started and listening for real-time updates.")
        except Exception as e:
            logger.error(f"Error starting WebSocket streams: {type(e).__name__} - {e}", exc_info=True)
            send_toast(f"MMXCEL Critical: WS streams failed to start for {SYMBOL}!", 'red', 'white')
            raise # Re-raise to halt execution if core communication fails

    async def get_balance(self, account_type: str = "UNIFIED", coin: str = COIN_FOR_BALANCE) -> Decimal:
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
                available_balance_str = balance_info.get('availableToWithdraw')

                if available_balance_str is None or available_balance_str == '':
                    self.current_balance = Decimal("0")
                    logger.warning(f"Available balance for {coin} was None or empty string from API, defaulting to 0. (Raw: '{available_balance_str}')")
                else:
                    try:
                        self.current_balance = Decimal(str(available_balance_str))
                    except Exception as e:
                        logger.error(f"Failed to transmute '{available_balance_str}' to Decimal: {type(e).__name__} - {e}. Defaulting to 0.", exc_info=True)
                        self.current_balance = Decimal("0")
                return self.current_balance
            logger.error(f"Unexpected balance response structure: {response.get('retMsg', 'No error message')} | Raw: {response}")
            return Decimal("0")
        else:
            logger.error(f"Failed to get balance for {coin}: {response.get('retMsg', 'No error message') if response else 'No response'}")
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
            logger.error(f"Failed to get open orders via REST for {SYMBOL}: {response.get('retMsg', 'No error message') if response else 'No response'}")
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
            logger.error(f"Failed to get positions via REST for {SYMBOL}: {response.get('retMsg', 'No error message') if response else 'No response'}")
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
            logger.error(f"Attempted to place order with non-positive quantized quantity: {quantized_qty} for {SYMBOL} {side}.")
            return None

        try:
            order_payload = {
                "category": CATEGORY,
                "symbol": SYMBOL,
                "side": side,
                "orderType": order_type,
                "qty": str(quantized_qty),
                "positionIdx": 1 if side == "Buy" else 2 # 1 for long, 2 for short in HedgeMode
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
                log_msg = f"Placed {order_type} {side} order for {SYMBOL}: {order_info.get('orderId', 'N/A')}"
                if quantized_price is not None:
                    log_msg += f" @ {quantized_price}"
                log_msg += f" Qty: {quantized_qty}"
                if client_order_id is not None:
                    log_msg += f" (Client ID: {client_order_id})"
                logger.info(log_msg)
                return order_info
            else:
                logger.error(f"Failed to place {order_type} {side} order for {SYMBOL} {quantized_qty}@{quantized_price if quantized_price else 'N/A'}: {response.get('retMsg', 'No error message') if response else 'No response'}")
                return None
        except Exception as e:
            logger.error(f"Error placing order for {SYMBOL} {side} {quantized_qty}@{quantized_price if quantized_price else 'N/A'} (Type: {order_type}): {type(e).__name__} - {e}", exc_info=True)
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
            logger.info(f"Cancelled order: {order_id} for {SYMBOL}")
            return True
        else:
            logger.error(f"Failed to cancel order {order_id} for {SYMBOL}: {response.get('retMsg', 'No error message') if response else 'No response'}")
            return False

    async def cancel_all_orders(self) -> None:
        """Cancels all open orders for the symbol, sweeping the slate clean."""
        response = await self._make_api_call(
            self.http_session.cancel_all_orders,
            category=CATEGORY,
            symbol=SYMBOL
        )
        if response and response.get('retCode') == 0:
            logger.info(f"Successfully cancelled all open orders for {SYMBOL}.")
            ws_state["open_orders"].clear()
        else:
            logger.error(f"Failed to cancel all orders for {SYMBOL}: {response.get('retMsg', 'No error message') if response else 'No response'}")

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
                logger.warning(f"Skipping batch order with non-positive quantized quantity: {quantized_qty} for {order.get('side')} {SYMBOL}")
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

        response = await self._make_api_call(self.http_session.place_batch_order, batch_request_payload)

        if response and response.get('retCode') == 0:
            logger.info(f"Successfully placed {len(batch_request_payload['request'])} batch orders for {SYMBOL}.")
            return response['result']
        else:
            logger.error(f"Failed to place batch orders for {SYMBOL}: {response.get('retMsg', 'No error message') if response else 'No response'}")
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
            if orderbook and 'bids' in orderbook and 'asks' in orderbook:
                best_bid = Decimal(orderbook['bids'][0][0]) if orderbook['bids'] else Decimal("0")
                best_ask = Decimal(orderbook['asks'][0][0]) if orderbook['asks'] else Decimal("0")
                mid_price = (best_bid + best_ask) / Decimal("2")
                ws_state["best_bid"] = best_bid
                ws_state["best_ask"] = best_ask
                ws_state["mid_price"] = mid_price
                ws_state["last_update_time"] = time.time()
                logger.debug(f"Orderbook snapshot: Mid Price: {mid_price:.{_calculate_decimal_precision(symbol_info['price_precision'])}f}")
                return orderbook
            else:
                logger.error(f"Orderbook snapshot for {SYMBOL} returned but missing bids/asks data.")
                return None
        else:
            logger.error(f"Failed to get orderbook snapshot for {SYMBOL}: {response.get('retMsg', 'No error message') if response else 'No response'}")
            return None

class MarketMakingStrategy:
    """The Alchemist's Strategy, overseeing the delicate balance of market forces."""
    def __init__(self, client: BybitClient):
        self.client = client
        self.running = False
        self.rebalance_task = None
        self.stop_loss_task = None
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
        if not self._is_market_data_available():
            return

        current_time = time.time()

        # Check if it's time to refresh orders
        if current_time - self.last_order_refresh_time >= self.order_refresh_interval:
            self.order_refresh_counter += 1
            self.last_order_refresh_time = current_time

            # Dynamically adjust the refresh interval based on recent activity
            # If we've tried to refresh multiple times without success (e.g., API errors), increase the interval
            if self.order_refresh_counter >= self.max_order_refresh_attempts:
                self.order_refresh_interval = min(self.order_refresh_interval * 2, self.max_order_refresh_interval)
                logger.info(f"Increasing order refresh interval to {self.order_refresh_interval} seconds due to multiple attempts without successful order placement/management.")
                self.order_refresh_counter = 0 # Reset counter after adjustment
            else:
                # If we successfully managed orders (or attempted to), reset counter and consider decreasing interval
                self.order_refresh_counter = 0
                if self.order_refresh_interval > self.min_order_refresh_interval:
                    self.order_refresh_interval = max(self.order_refresh_interval * 0.9, self.min_order_refresh_interval)
                    logger.debug(f"Decreasing order refresh interval to {self.order_refresh_interval:.2f} seconds.")


            # Check if price has moved significantly to trigger re-placement
            mid_price = ws_state["mid_price"]
            price_change_percentage = Decimal("0")
            if self.last_mid_price != Decimal("0") and mid_price != Decimal("0"):
                if self.last_mid_price == mid_price:
                    price_change_percentage = Decimal("0")
                else:
                    price_change_percentage = abs(mid_price - self.last_mid_price) / self.last_mid_price

                if price_change_percentage >= PRICE_THRESHOLD:
                    logger.info(f"Price moved {price_change_percentage:.4%} (>= {PRICE_THRESHOLD:.4%}). Cancelling all orders to re-place for {SYMBOL}.")
                    await self.client.cancel_all_orders()
                    # Do not reset last_mid_price yet, it will be updated after new orders are placed
                else:
                    # If price hasn't moved significantly, and we already have orders, skip placing new ones
                    if ws_state["open_orders"]:
                        logger.debug(f"No significant price change for {SYMBOL} and orders exist. Skipping new order placement.")
                        return # Skip placing new orders if price hasn't moved and orders are already out

            # Check for stale orders and cancel them, removing forgotten spirits
            orders_to_cancel_ids = [
                order_id for order_id, details in list(ws_state["open_orders"].items())
                if time.time() - details['timestamp'] > ORDER_LIFESPAN_SECONDS
            ]
            if orders_to_cancel_ids:
                logger.info(f"Cancelling {len(orders_to_cancel_ids)} stale orders for {SYMBOL} to keep the ledger clean.")
                # Use asyncio.gather for concurrent cancellation if multiple stale orders
                await asyncio.gather(*[self.client.cancel_order(oid) for oid in orders_to_cancel_ids])

            # Get fresh state from REST to handle any missed WS updates, ensuring perfect synchronicity
            await self.client.get_open_orders_rest()

            # Check if we have too many open orders, avoiding over-committing arcane energy
            if len(ws_state["open_orders"]) >= MAX_OPEN_ORDERS:
                logger.info(f"Max open orders ({MAX_OPEN_ORDERS}) reached for {SYMBOL}. Skipping new order placement.")
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
            else:
                logger.debug(f"No new orders to place for {SYMBOL} at this time (e.g., max orders reached or existing orders are fine).")


    def _is_market_data_available(self) -> bool:
        """Helper to check if market data is available, avoiding redundant checks."""
        if ws_state["mid_price"] == Decimal("0") or ws_state["best_bid"] == Decimal("0") or ws_state["best_ask"] == Decimal("0"):
            logger.warning(f"Market data (mid, bid, ask) for {SYMBOL} not available yet. Skipping operation.")
            return False
        return True

    async def rebalance_inventory(self):
        """Periodically rebalances inventory (position) to a neutral state, maintaining equilibrium."""
        if not self._is_market_data_available():
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
                logger.warning(f"Quantized rebalance quantity for {SYMBOL} is zero ({quantized_qty_to_rebalance}), skipping rebalance.")
                return

            logger.warning(f"{YELLOW}Inventory imbalance detected for {SYMBOL}. Net position: {net_position:.{_calculate_decimal_precision(symbol_info['qty_precision'])}f}. "
                             f"Attempting to rebalance by placing a {side_to_rebalance} market order for {quantized_qty_to_rebalance}.{NC}")
            send_toast(f"MMXCEL: Rebalancing {quantized_qty_to_rebalance:.{_calculate_decimal_precision(symbol_info['qty_precision'])}f} {SYMBOL}!", 'yellow', 'black')

            # Place a market order to quickly rebalance
            client_rebalance_id = f"mmxcel-rebal-{int(time.time() * 1000)}"
            asyncio.create_task(self.client.place_order(side_to_rebalance, quantized_qty_to_rebalance, order_type="Market", client_order_id=client_rebalance_id))
        else:
            logger.debug(f"No significant inventory imbalance for {SYMBOL}. Net position: {net_position:.{_calculate_decimal_precision(symbol_info['qty_precision'])}f}.")


    async def manage_stop_loss_and_profit_take(self):
        """Monitors positions for stop-loss and profit-taking opportunities, safeguarding and harvesting gains."""
        if not self._is_market_data_available():
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
                pnl_percentage = pnl_usdt / (long_avg_price * long_size) / long_avg_price # PnL as percentage of entry price

            # Quantize the size before placing a closing order
            quantized_long_size = long_size.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            if quantized_long_size <= 0:
                logger.warning(f"Quantized long closing quantity for {SYMBOL} is zero ({quantized_long_size}), skipping close.")
            elif pnl_percentage < -STOP_LOSS_PERCENTAGE:
                logger.critical(f"{RED}Stop-loss triggered for LONG position on {SYMBOL}! Unrealised PnL: {pnl_usdt:.2f} USDT ({pnl_percentage:.2%}). "
                                 f"Placing market sell order to close {quantized_long_size}.{NC}")
                send_toast(f"MMXCEL: LONG SL triggered for {SYMBOL}! PnL: {pnl_usdt:.2f} USDT", 'red', 'white')
                asyncio.create_task(self.client.place_order("Sell", quantized_long_size, order_type="Market", client_order_id=f"mmxcel-sl-long-{int(time.time() * 1000)}"))
            elif pnl_percentage >= PROFIT_PERCENTAGE:
                logger.info(f"{GREEN}Profit-take triggered for LONG position on {SYMBOL}. Unrealised PnL: {pnl_usdt:.2f} USDT ({pnl_percentage:.2%}). "
                                 f"Placing market sell order to close {quantized_long_size}.{NC}")
                send_toast(f"MMXCEL: LONG TP triggered for {SYMBOL}! PnL: {pnl_usdt:.2f} USDT", 'green', 'black')
                asyncio.create_task(self.client.place_order("Sell", quantized_long_size, order_type="Market", client_order_id=f"mmxcel-tp-long-{int(time.time() * 1000)}"))
            else:
                logger.debug(f"Long position for {SYMBOL} within acceptable PnL range. Current PnL: {pnl_usdt:.2f} USDT ({pnl_percentage:.2%}).")


        # Check short position
        short_pos = ws_state['positions'].get('Short', {})
        short_size = short_pos.get('size', Decimal('0'))
        short_avg_price = short_pos.get('avg_price', Decimal('0'))

        if short_size > 0 and short_avg_price > 0: # Ensure valid position
            pnl_usdt = short_pos.get('unrealisedPnl', Decimal('0'))

            pnl_percentage = Decimal('0')
            if (short_avg_price * short_size) > 0:
                pnl_percentage = pnl_usdt / (short_avg_price * short_size) / short_avg_price # PnL as percentage of entry price

            # Quantize the size before placing a closing order
            quantized_short_size = short_size.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            if quantized_short_size <= 0:
                logger.warning(f"Quantized short closing quantity for {SYMBOL} is zero ({quantized_short_size}), skipping close.")
            elif pnl_percentage < -STOP_LOSS_PERCENTAGE:
                logger.critical(f"{RED}Stop-loss triggered for SHORT position on {SYMBOL}! Unrealised PnL: {pnl_usdt:.2f} USDT ({pnl_percentage:.2%}). "
                                 f"Placing market buy order to close {quantized_short_size}.{NC}")
                send_toast(f"MMXCEL: SHORT SL triggered for {SYMBOL}! PnL: {pnl_usdt:.2f} USDT", 'red', 'white')
                asyncio.create_task(self.client.place_order("Buy", quantized_short_size, order_type="Market", client_order_id=f"mmxcel-sl-short-{int(time.time() * 1000)}"))
            elif pnl_percentage >= PROFIT_PERCENTAGE:
                logger.info(f"{GREEN}Profit-take triggered for SHORT position on {SYMBOL}. Unrealised PnL: {pnl_usdt:.2f} USDT ({pnl_percentage:.2%}). "
                                 f"Placing market buy order to close {quantized_short_size}.{NC}")
                send_toast(f"MMXCEL: SHORT TP triggered for {SYMBOL}! PnL: {pnl_usdt:.2f} USDT", 'green', 'black')
                asyncio.create_task(self.client.place_order("Buy", quantized_short_size, order_type="Market", client_order_id=f"mmxcel-tp-short-{int(time.time() * 1000)}"))
            else:
                logger.debug(f"Short position for {SYMBOL} within acceptable PnL range. Current PnL: {pnl_usdt:.2f} USDT ({pnl_percentage:.2%}).")


    async def shutdown(self):
        """Gracefully shuts down the bot, including cancelling open orders, and silencing the arcane channels."""
        if self.running:
            self.running = False
            logger.info("Shutdown initiated. Cancelling all open orders...")
            send_toast(f"MMXCEL: Shutting down {SYMBOL}, cancelling orders...", '#FFA500', 'white')
            await self.client.cancel_all_orders()
            # Stop any running tasks
            if self.rebalance_task and not self.rebalance_task.done():
                self.rebalance_task.cancel()
            if self.stop_loss_task and not self.stop_loss_task.done():
                self.stop_loss_task.cancel()

            self.exit_flag.set()
            send_toast(f"MMXCEL: Shutdown complete for {SYMBOL}.", 'green', 'white')

    async def run(self):
        """Unleashes the bot's full power, beginning its market-making vigil."""
        self.running = True

        # Validate configuration values before starting operations
        if not self._validate_config():
            logger.critical("Configuration validation failed. Aborting bot startup.")
            send_toast(f"MMXCEL Config Error for {SYMBOL}! Check logs.", 'red', 'white')
            return

        # Fetch symbol information first, crucial for correct price/quantity handling
        if not await self.client.get_symbol_info():
            logger.critical("Failed to fetch symbol information. Cannot proceed without it.")
            send_toast(f"MMXCEL Error: Symbol info fetch failed for {SYMBOL}!", 'red', 'white')
            return

        # Set position mode (e.g., HedgeMode)
        if not await self.client.set_position_mode(POSITION_MODE):
            logger.critical(f"Failed to set position mode to {POSITION_MODE}. This is critical for the bot's strategy. Aborting.")
            send_toast(f"MMXCEL Error: Failed to set {POSITION_MODE} for {SYMBOL}!", 'red', 'white')
            return

        self.client.start_websocket_streams()

        # Give some time for WS to connect and get initial data from the ether
        await asyncio.sleep(5)

        # Fetch initial state via REST to ensure we don't miss anything
        await self.client.get_balance(coin=COIN_FOR_BALANCE)
        await self.client.get_open_orders_rest()
        await self.client.get_positions_rest() # Explicitly fetch initial positions

        # Start background tasks for rebalancing and stop-loss/profit-taking
        self.rebalance_task = asyncio.create_task(self._periodic_task(self.rebalance_inventory, interval=10, name="Rebalance"))
        self.stop_loss_task = asyncio.create_task(self._periodic_task(self.manage_stop_loss_and_profit_take, interval=2, name="PnL Management"))

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
                print(format_metric("Position Mode", POSITION_MODE, YELLOW, value_color=WHITE, label_width=20))
                print(format_metric("Price Tick Size", symbol_info['price_precision'], YELLOW, value_precision=price_disp_prec, label_width=20))
                print(format_metric("Quantity Step Size", symbol_info['qty_precision'], YELLOW, value_precision=qty_disp_prec, label_width=20))
                print(format_metric("Order Refresh Interval (s)", self.order_refresh_interval, YELLOW, value_color=WHITE, label_width=20))
                print_neon_separator()

                # Market and Account Data
                print(f"{BOLD}{CYAN}--- Current Market & Account Status ---{NC}")
                print(format_metric("Mid Price", ws_state['mid_price'], BLUE, value_precision=price_disp_prec))
                print(format_metric("Best Bid", ws_state['best_bid'], BLUE, value_precision=price_disp_prec))
                print(format_metric("Best Ask", ws_state['best_ask'], BLUE, value_precision=price_disp_prec))
                await self.client.get_balance(coin=COIN_FOR_BALANCE) # Refresh balance every loop for display
                print(format_metric(f"Available Balance ({COIN_FOR_BALANCE})", self.client.current_balance, YELLOW, value_precision=2))
                # Display last market data update time
                last_update_str = datetime.fromtimestamp(ws_state['last_update_time']).strftime('%Y-%m-%d %H:%M:%S') if ws_state['last_update_time'] else "N/A"
                print(format_metric("Last Market Data Update", last_update_str, YELLOW, value_color=WHITE, label_width=20))
                print_neon_separator()

                # Position Details
                print(f"{BOLD}{CYAN}--- Active Positions ({SYMBOL}) ---{NC}")
                long_pos = ws_state['positions'].get('Long', {'size': Decimal('0'), 'unrealisedPnl': Decimal('0')})
                short_pos = ws_state['positions'].get('Short', {'size': Decimal('0'), 'unrealisedPnl': Decimal('0')})

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
            logger.critical(f"An unhandled critical error occurred in the main loop: {type(e).__name__} - {e
