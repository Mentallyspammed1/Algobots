#!/usr/bin/env python3
"""
MMXCEL v2.5 – Bybit Hedge-Mode Market-Making Bot
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
from decimal import Decimal, getcontext, ROUND_DOWN, ROUND_UP, DecimalException
from typing import Any, Dict, Optional, List, Tuple

from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket
from colorama import Fore, Style, init

# Initialize colorama for cross-platform color support – Setting the stage with vibrant hues
init(autoreset=True)

# High-precision decimals for financial calculations – The loom of precision
getcontext().prec = 12

# Optional: prettier colours if termcolor is available (A minor enchantment, not strictly required)
try:
    from termcolor import colored
    _has_termcolor = True
except ImportError:
    _has_termcolor = False
    def colored(text, color):  # Fallback function for basic charm
        return text

# ANSI Color shortcuts – The palette of the digital alchemist
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
LIGHT_BLACK = Fore.LIGHTBLACK_EX # For subtle debug messages

# Load environment variables – Unveiling the hidden keys
load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

# Load runtime configuration – Reading the ancient scrolls of configuration
try:
    with open("config.json", "r") as f:
        config = json.load(f)
except FileNotFoundError:
    print(f"{RED}config.json not found. Please create it. The ritual cannot begin without its sacred texts.{NC}")
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"{RED}config.json is malformed JSON: {e}. The configuration scrolls are corrupted.{NC}")
    sys.exit(1)

# Configure logging with rotation – Scribing the chronicles of the bot's journey
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

# Global configuration aliases (read robustly using .get() with defaults) – The bot's fundamental parameters
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
BALANCE_REFRESH_INTERVAL = int(config.get("BALANCE_REFRESH_INTERVAL", 30)) # Refreshes balance from API

# Constants for data freshness and retry delays – Safeguards against the volatile ether
MAX_DATA_AGE_SECONDS = 10  # Maximum acceptable age for market data
MAX_RETRIES_API = 5        # Default maximum retries for API calls
RETRY_DELAY_API = 2        # Initial delay for API retries in seconds
WS_MONITOR_INTERVAL = 10   # How often to check WS connection status
PNL_MONITOR_INTERVAL = 5   # How often to check for PnL triggers

# Exchange precision placeholders (initialized globally) – The granularities of the market realm
symbol_info = {
    "price_precision": Decimal("0.0001"),
    "qty_precision": Decimal("0.001"),
    "min_order_value": Decimal("10.0"), # Fallback minimum order value
    "max_order_value_limit": Decimal("0"), # Max notional value from API filters
    "min_price": Decimal("0"),
    "max_price": Decimal("1000000.00"), # Default high value, will be updated
    "min_qty": Decimal("0"),
}

# WebSocket shared state – The ever-shifting tapestry of market data
ws_state = {
    "mid_price": Decimal("0"),
    "best_bid": Decimal("0"),
    "best_ask": Decimal("0"),
    "open_orders": {},      # Stores details of currently open orders: {orderId: {client_order_id, symbol, side, price, qty, status, timestamp}}
    "positions": {},        # Stores details of current positions: {Long: {size, avg_price, unrealisedPnl}, Short: {...}}
    "last_update_time": 0,  # Timestamp of last successful WS market data update
    "last_balance_update": 0,
    "available_balance": Decimal("0")
}

# Global session statistics – The chronicle of the bot's achievements
session_stats = {
    "start_time": time.time(),
    "orders_placed": 0,
    "orders_filled": 0,
    "rebalances_count": 0,
    "circuit_breaker_activations": 0,
}

# Flag to check if termux-toast command is available – For transient whispers from the device
_HAS_TERMUX_TOAST_CMD = False # This will be set by check_termux_toast() in main

# Global flag for graceful shutdown – The signal to cease the spell
_SHUTDOWN_REQUESTED = False

# Bot Operational States - Tracking the bot's current activity
BOT_STATE = "IDLE" # Possible states: INITIALIZING, SYNCING, ACTIVE, PAUSED, CIRCUIT_BREAK, SHUTDOWN

# -----------------------------
# Helper Functions – Minor Incantations
# -----------------------------

def _calculate_decimal_precision(d: Decimal) -> int:
    """Determine the number of decimal places in a Decimal value for display."""
    if not isinstance(d, Decimal):
        return 0
    # Normalize removes trailing zeros and exponent notation
    s = str(d.normalize())
    # Handle cases like '1.' or '.5'
    if "." in s:
        return len(s.split(".")[1])
    return 0

def clear_screen() -> None:
    """Clear the terminal screen – A momentary vanishing act."""
    os.system("cls" if os.name == "nt" else "clear")

def print_neon_header(text: str, color: str = UNDERLINE, length: int = 80) -> None:
    """Print a styled header with border – Forging a luminous banner."""
    border_char = "✨"
    max_text_len = length - (len(border_char) * 2 + 4) # Calculate max text length respecting borders
    if len(text) > max_text_len:
        text = text[: max_text_len - 3] + "..." # Truncate if too long
    header_text = f" {border_char}-- {text} --{border_char} "
    padding_total = length - len(header_text)
    padding_left = padding_total // 2
    padding_right = padding_total - padding_left
    full_header = f"{' ' * padding_left}{color}{header_text}{NC}{' ' * padding_right}"
    print(full_header)

def print_neon_separator(length: int = 80, char: str = "─", color: str = CYAN) -> None:
    """Print a separator line – Drawing a line in the digital sands."""
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
    """Format a label-value pair for display with precision and color – Illuminating the metrics."""
    formatted_label = f"{label_color}{label:<{label_width}}{NC}"
    actual_value_color = value_color if value_color else label_color
    formatted_value = ""

    if isinstance(value, Decimal):
        # Determine precision: use specified or calculate from value
        current_precision = value_precision if value_precision is not None else _calculate_decimal_precision(value)
        if is_pnl:
            actual_value_color = GREEN if value >= Decimal("0") else RED
            # sign = "+" if value > Decimal("0") else "" # Not used in format string
            formatted_value = f"{actual_value_color}{value:,.{current_precision}f}{unit}{NC}"
        else:
            formatted_value = f"{actual_value_color}{value:,.{current_precision}f}{unit}{NC}"
    elif isinstance(value, (int, float)):
        if is_pnl:
            actual_value_color = GREEN if value >= 0 else RED
            # sign = "+" if value > 0 else "" # Not used in format string
            formatted_value = f"{actual_value_color}{value:,}{unit}{NC}"
        else:
            formatted_value = f"{actual_value_color}{value:,}{unit}{NC}"
    else: # For strings or other types
        formatted_value = f"{actual_value_color}{str(value)}{unit}{NC}"
    return f"{formatted_label}: {formatted_value}"

def check_termux_toast() -> bool:
    """Checks if the termux-toast command is available – Divining Termux:API presence."""
    # Execute command and check return code. Redirect stdout/stderr to null.
    return os.system("command -v termux-toast > /dev/null 2>&1") == 0

def send_toast(message: str, color: str = "#336699", text_color: str = "white") -> None:
    """Sends a toast message if termux-toast is available – A transient whisper from the device."""
    if _HAS_TERMUX_TOAST_CMD:
        # Sanitize message to prevent command injection, though unlikely for toast
        sanitized_message = message.replace("'", "\\'").replace('"', '\\"')
        os.system(f"termux-toast -b '{color}' -c '{text_color}' '{sanitized_message}'")
    else:
        logger.debug(f"{LIGHT_BLACK}Toast (unavailable): {message}{NC}")


# -----------------------------
# WebSocket Callbacks – Listening to the Ether's Whispers
# -----------------------------

def on_public_ws_message(msg: Dict[str, Any]) -> None:
    """Handle public WebSocket messages (orderbook) – Decoding the market's heartbeat."""
    try:
        topic = msg.get("topic")
        if topic and topic.startswith(f"orderbook.1."):
            data = msg.get("data")
            if data and data.get("b") and data.get("a"): # Check if bid and ask data exist
                bid_info = data["b"][0]
                ask_info = data["a"][0]
                
                ws_state["best_bid"] = Decimal(bid_info[0])
                ws_state["best_ask"] = Decimal(ask_info[0])
                # Calculate mid-price only if both bid and ask are valid (non-zero)
                if ws_state["best_bid"] > Decimal("0") and ws_state["best_ask"] > Decimal("0"):
                    ws_state["mid_price"] = (ws_state["best_bid"] + ws_state["best_ask"]) / Decimal("2")
                else:
                    ws_state["mid_price"] = Decimal("0") # Mark mid-price as invalid if bid/ask are zero
                
                ws_state["last_update_time"] = time.time()
                logger.debug(f"{Fore.BLUE}WS Orderbook: Bid={ws_state['best_bid']:.4f}, Ask={ws_state['best_ask']:.4f}, Mid={ws_state['mid_price']:.4f}{NC}")
    except (KeyError, IndexError, ValueError, TypeError, DecimalException) as e:
        logger.error(f"{RED}Error processing public WS message: {type(e).__name__} - {e} | Message: {msg}{NC}")
    except Exception as e:
        logger.error(f"{RED}Unexpected error in public WS handler: {type(e).__name__} - {e} | Message: {msg}{NC}")

def on_private_ws_message(msg: Dict[str, Any]) -> None:
    """Handle private WebSocket messages (orders, positions) – Interpreting the bot's own echoes."""
    try:
        topic = msg.get("topic")
        if topic == "order":
            for o in msg["data"]:
                oid = o.get("orderId")
                if not oid: continue # Skip if no orderId
                
                # Process orders that are closed (Filled, Canceled, Deactivated)
                if o.get("orderStatus") in ("Filled", "Canceled", "Deactivated"):
                    if oid in ws_state["open_orders"]:
                        order_details = ws_state["open_orders"].pop(oid, None) # Remove from tracking
                        if order_details and o["orderStatus"] == "Filled":
                            session_stats["orders_filled"] += 1
                            logger.info(f"{GREEN}Order filled: {order_details['side']} {order_details['qty']} @ {order_details['price']}{NC}")
                            send_toast(f"Order filled: {order_details['side']} {order_details['qty']}", "green", "white")
                    logger.debug(f"{Fore.CYAN}WS Order Closed: ID {oid}, Status {o['orderStatus']}{NC}")
                else:
                    # Update status for orders that are still open
                    ws_state["open_orders"][oid] = {
                        "client_order_id": o.get("orderLinkId", "N/A"),
                        "symbol": o.get("symbol"),
                        "side": o.get("side"),
                        "price": Decimal(o.get("price", "0")),
                        "qty": Decimal(o.get("qty", "0")),
                        "status": o.get("orderStatus"),
                        "timestamp": float(o.get("createdTime", 0)) / 1000, # Convert ms to seconds
                    }
        elif topic == "position":
            for p in msg["data"]:
                if p.get("symbol") == SYMBOL: # Process only for the target symbol
                    side = "Long" if p.get("side") == "Buy" else "Short"
                    current_unrealised_pnl = Decimal(p.get("unrealisedPnl", "0"))
                    
                    ws_state["positions"][side] = {
                        "size": Decimal(p.get("size", "0")),
                        "avg_price": Decimal(p.get("avgPrice", "0")),
                        "unrealisedPnl": current_unrealised_pnl,
                    }
                    logger.debug(f"{Fore.CYAN}WS Position Update: {side} Size={p.get('size')}, PnL={current_unrealised_pnl}{NC}")
    except (KeyError, ValueError, TypeError, DecimalException) as e:
        logger.error(f"{RED}Error processing private WS message: {type(e).__name__} - {e} | Message: {msg}{NC}")
    except Exception as e:
        logger.error(f"{RED}Unexpected error in private WS handler: {type(e).__name__} - {e} | Message: {msg}{NC}")

# -----------------------------
# Bybit Client Class – The Conduit to the Exchange Realm
# -----------------------------

class BybitClient:
    MAX_RETRIES = MAX_RETRIES_API
    RETRY_DELAY = RETRY_DELAY_API

    def __init__(self, key: str, secret: str, testnet: bool):
        self.http = HTTP(testnet=testnet, api_key=key, api_secret=secret)
        # Initialize WebSockets with retry parameters
        self.ws_public = WebSocket(testnet=testnet, channel_type="linear", retries=self.MAX_RETRIES, retry_interval=self.RETRY_DELAY)
        self.ws_private = WebSocket(testnet=testnet, channel_type="private", api_key=key, api_secret=secret, retries=self.MAX_RETRIES, retry_interval=self.RETRY_DELAY)
        self.current_balance = Decimal("0")
        self.is_public_ws_connected = False
        self.is_private_ws_connected = False
        
        # Binding the ethereal callbacks for WS connection events
        self.ws_public.on_open = lambda: self._on_ws_open("public")
        self.ws_private.on_open = lambda: self._on_ws_open("private")
        self.ws_public.on_close = lambda: self._on_ws_close("public")
        self.ws_private.on_close = lambda: self._on_ws_close("private")
        self.ws_public.on_error = lambda err: self._on_ws_error("public", err)
        self.ws_private.on_error = lambda err: self._on_ws_error("private", err)

    def _on_ws_open(self, ws_type: str):
        """Callback when a WebSocket connection opens – A portal to the market opens."""
        if ws_type == "public":
            self.is_public_ws_connected = True
            logger.info(f"{Fore.GREEN}Public WebSocket connection established. The market's pulse is now channeled.{NC}")
        elif ws_type == "private":
            self.is_private_ws_connected = True
            logger.info(f"{Fore.GREEN}Private WebSocket connection established. Your own echoes are now heard.{NC}")

    def _on_ws_close(self, ws_type: str):
        """Callback when a WebSocket connection closes – A temporary rift in the ether."""
        if ws_type == "public":
            self.is_public_ws_connected = False
            logger.warning(f"{Fore.YELLOW}Public WebSocket connection closed. Pybit will attempt to re-establish the link.{NC}")
        elif ws_type == "private":
            self.is_private_ws_connected = False
            logger.warning(f"{Fore.YELLOW}Private WebSocket connection closed. Pybit will attempt to re-establish the link.{NC}")

    def _on_ws_error(self, ws_type: str, error: Exception):
        """Callback for WebSocket errors – Disturbances in the digital currents."""
        logger.error(f"{RED}{ws_type.capitalize()} WebSocket error: {error}{NC}")
    
    async def _monitor_websockets(self, strategy_instance):
        """Periodically checks WS connection status – Vigilantly guarding the ethereal connections."""
        while strategy_instance.running and not _SHUTDOWN_REQUESTED:
            if not self.is_public_ws_connected:
                logger.warning(f"{Fore.YELLOW}Public WS connection currently disconnected. Awaiting pybit reconnect...{NC}")
                send_toast("WS Public disconnected", "#FFA500", "white")
            
            if not self.is_private_ws_connected:
                logger.warning(f"{Fore.YELLOW}Private WS connection currently disconnected. Awaiting pybit reconnect...{NC}")
                send_toast("WS Private disconnected", "#FFA500", "white")
            
            await asyncio.sleep(WS_MONITOR_INTERVAL)

    async def _api(self, api_method, *args, **kwargs):
        """Generic retry wrapper for API calls with exponential backoff and error handling – Channeling the ether for swift execution."""
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = api_method(*args, **kwargs)
                if response and response.get("retCode") == 0:
                    return response # Success

                # Handle API errors
                ret_code = response.get('retCode') if response else None
                ret_msg = response.get('retMsg', 'No response or unknown error') if response else 'No response'
                
                # Log specific error types for better diagnostics
                if ret_code == 30034 or ret_code == 30035: # Rate Limit Exceeded
                     logger.warning(f"{YELLOW}API Rate limit exceeded (Code: {ret_code}, Attempt {attempt}/{self.MAX_RETRIES}). Applying backoff.{NC}")
                elif ret_code == 10002 or ret_code == 10003: # Invalid/Missing Parameter
                     logger.error(f"{RED}API Parameter Error (Code: {ret_code}, Attempt {attempt}/{self.MAX_RETRIES}). Check configuration or request payload. Message: {ret_msg}{NC}")
                     # These are usually fatal for the current operation, may not need retries for parameter errors.
                     return None 
                elif ret_code == 10007 or ret_code == 10005: # Signature or Key Error
                     logger.error(f"{RED}API Authentication Error (Code: {ret_code}, Attempt {attempt}/{self.MAX_RETRIES}). Verify API Key and Secret. Message: {ret_msg}{NC}")
                     return None # Authentication errors are fatal
                elif ret_code == 429: # Standard HTTP rate limit code (sometimes returned by APIs)
                     logger.warning(f"{YELLOW}HTTP Rate Limit exceeded (429, Attempt {attempt}/{self.MAX_RETRIES}). Applying backoff.{NC}")
                elif ret_code == 10001 or ret_code == 10006: # System errors
                     logger.error(f"{RED}System Error (Code: {ret_code}, Attempt {attempt}/{self.MAX_RETRIES}). This might be a temporary server issue. Message: {ret_msg}{NC}")
                else: # General API error
                    logger.warning(f"{YELLOW}API Call Failed (Attempt {attempt}/{self.MAX_RETRIES}, Code: {ret_code}): {ret_msg}{NC}")

                # Determine if retry is appropriate
                if attempt < self.MAX_RETRIES and ret_code not in [10002, 10003, 10005, 10007]: # Avoid retrying on parameter/auth errors
                    delay = self.RETRY_DELAY * (2 ** (attempt - 1)) + (time.time() % 1) # Add small jitter for better distribution
                    logger.warning(f"{Fore.YELLOW}Retrying in {delay:.1f}s...{NC}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"{RED}API operation failed after all retries or due to non-retryable error (Code: {ret_code}). The conduit is unresponsive.{NC}")
                    return None
            except Exception as e: # Catch network errors, timeouts, etc.
                error_msg = f"{RED}Exception during API call (Attempt {attempt}/{self.MAX_RETRIES}): {type(e).__name__} - {e}{NC}"
                logger.error(error_msg, exc_info=True) # Log traceback for debugging
                if attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAY * (2 ** (attempt - 1)) + (time.time() % 1)
                    logger.warning(f"{Fore.YELLOW}Retrying in {delay:.1f}s...{NC}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"{RED}API call failed after all retries due to exception: {type(e).__name__} - {e}. The channeling failed.{NC}")
                    return None
        return None

    async def get_symbol_info(self) -> bool:
        """Fetch symbol precision details, including min/max prices, quantities, and order value limits – Divining the market's granularities."""
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

                # Extract precision and basic filters
                symbol_info["price_precision"] = Decimal(price_filter.get('tickSize', "0.0001"))
                symbol_info["qty_precision"] = Decimal(lot_size_filter.get('qtyStep', "0.001"))
                symbol_info["min_price"] = Decimal(price_filter.get('minPrice', "0"))
                symbol_info["max_price"] = Decimal(price_filter.get('maxPrice', "1000000.00")) # Default high value
                symbol_info["min_qty"] = Decimal(lot_size_filter.get('minQty', "0"))
                
                # Determine minimum order value
                calculated_min_value = symbol_info["min_qty"] * symbol_info["min_price"]
                symbol_info["min_order_value"] = max(calculated_min_value, Decimal("5")) # Use a reasonable fallback if calculation is zero

                # Extract max notional value limits from API filters
                max_order_value_limit = Decimal("0")
                if "maxOrderSideFilters" in instrument_info and instrument_info["maxOrderSideFilters"]:
                    for filter_item in instrument_info["maxOrderSideFilters"]:
                        try:
                            side = filter_item.get("side")
                            max_notional_str = filter_item.get("maxNotional", "0")
                            if max_notional_str: # Ensure the string is not empty
                                max_notional = Decimal(max_notional_str)
                                # For market making, we typically want orders smaller than the max allowed.
                                # We'll use the minimum of buy/sell max notional as a general limit.
                                if side == "Buy":
                                     if max_order_value_limit == Decimal("0"): # Initialize if first filter seen
                                         max_order_value_limit = max_notional
                                     else:
                                         max_order_value_limit = min(max_order_value_limit, max_notional)
                                elif side == "Sell":
                                     max_order_value_limit = min(max_order_value_limit, max_notional)
                        except (DecimalException, ValueError, KeyError, TypeError) as e:
                            logger.warning(f"{YELLOW}Could not parse maxNotional for {SYMBOL} side {side}: {e}. Skipping.{NC}")
                
                symbol_info["max_order_value_limit"] = max_order_value_limit
                
                logger.info(f"{Fore.CYAN}Symbol Info: {SYMBOL} | Price Prc: {symbol_info['price_precision']}, Qty Prc: {symbol_info['qty_precision']}, Min Price: {symbol_info['min_price']}, Max Price: {symbol_info['max_price']}, Min Qty: {symbol_info['min_qty']}, Min Order Value: {symbol_info['min_order_value']:.2f}{NC}")
                if max_order_value_limit > 0:
                    logger.info(f"{Fore.CYAN}Symbol Info: Max Order Value Limit={symbol_info['max_order_value_limit']:.2f}{NC}")
                return True
            logger.error(f"{RED}Symbol {SYMBOL} not found in instruments info. Its essence remains hidden.{NC}")
            return False
        logger.error(f"{RED}Failed to fetch instrument info for {SYMBOL}. The market's secrets are guarded.{NC}")
        return False

    async def test_credentials(self) -> bool:
        """Verify API credentials by fetching wallet balance – Proving your worth to the Bybit realm."""
        response = await self._api(self.http.get_wallet_balance, accountType="UNIFIED")
        if response and response.get("retCode") == 0:
            logger.info(f"{GREEN}API credentials validated successfully. The ancient sigils are recognized.{NC}")
            return True
        logger.error(f"{RED}API credentials validation failed. Check your .env file and testnet setting. The sigils are flawed.{NC}")
        return False

    def start_websockets(self):
        """Start public and private WebSocket streams – Opening the ethereal conduits."""
        logger.info(f"{Fore.CYAN}Starting public orderbook stream for {SYMBOL}...{NC}")
        self.ws_public.orderbook_stream(symbol=SYMBOL, depth=1, callback=on_public_ws_message)
        logger.info(f"{Fore.CYAN}Starting private order and position streams...{NC}")
        self.ws_private.order_stream(callback=on_private_ws_message)
        self.ws_private.position_stream(callback=on_private_ws_message)
        logger.info(f"{Fore.CYAN}WebSocket streams initiated. The whispers begin.{NC}")

    async def get_balance(self) -> Decimal:
        """Fetch available balance for USDT – Glimpsing your reservoir of power."""
        response = await self._api(self.http.get_wallet_balance, accountType="UNIFIED", coin="USDT")
        if response and response.get('retCode') == 0:
            try:
                balance_list = response.get("result", {}).get("list", [])
                if balance_list:
                    # Find USDT balance specifically
                    usdt_balance_info = next((item for item in balance_list if item.get("coin") == "USDT"), None)
                    if usdt_balance_info:
                        balance_str = usdt_balance_info.get("availableToWithdraw", "0")
                        balance = Decimal(balance_str)
                        self.current_balance = balance
                        ws_state["available_balance"] = balance
                        ws_state["last_balance_update"] = time.time()
                        logger.debug(f"{Fore.CYAN}Balance updated: {balance:.4f} USDT{NC}")
                        return balance
                    else:
                        logger.warning(f"{YELLOW}USDT balance information not found in wallet response. Setting balance to 0.{NC}")
                        ws_state["available_balance"] = Decimal("0")
                        ws_state["last_balance_update"] = time.time()
                        return Decimal("0")
                else:
                    logger.warning(f"{YELLOW}Balance response structure unexpected or empty. The balance scroll is unreadable.{NC}")
                    return Decimal("0")
            except (KeyError, IndexError, ValueError, DecimalException, TypeError) as e:
                logger.error(f"{RED}Error parsing balance response (coin data): {type(e).__name__} - {e}. The balance scroll is torn.{NC}")
                return Decimal("0")
        logger.error(f"{RED}Failed to fetch balance (API response error). The reservoir's depth remains unknown.{NC}")
        return Decimal("0")

    async def get_open_orders_rest(self) -> Dict[str, Any]:
        """Sync open orders from REST API – Reconciling the active spells."""
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
                    if not oid: continue # Skip if no orderId
                    current_open_orders[oid] = {
                        "client_order_id": order.get("orderLinkId", "N/A"),
                        "symbol": order.get("symbol"),
                        "side": order.get("side"),
                        "price": Decimal(order.get("price", "0")),
                        "qty": Decimal(order.get("qty", "0")),
                        "status": order.get("orderStatus"),
                        "timestamp": float(order.get("createdTime", 0)) / 1000, # Convert ms to seconds
                    }
                except (KeyError, ValueError, DecimalException, TypeError) as e:
                    logger.error(f"{RED}Error processing REST order data: {type(e).__name__} - {e} | Order: {order}. A order scroll is malformed.{NC}")
            
            ws_state["open_orders"] = current_open_orders # Overwrite with REST data for reliable sync
            logger.debug(f"{Fore.CYAN}REST sync: Found {len(current_open_orders)} open orders. The active spells are recounted.{NC}")
            return current_open_orders
        logger.error(f"{RED}Failed to fetch open orders via REST. The active spells are obscured.{NC}")
        return {}

    async def get_positions_rest(self) -> Dict[str, Any]:
        """Sync positions from REST API – Assessing the current manifestation of power."""
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
                    # Ensure we only process data for the target symbol and non-zero positions
                    if pos.get("symbol") == SYMBOL and Decimal(pos.get("size", "0")) > Decimal("0"):
                        side = "Long" if pos.get("side") == "Buy" else "Short"
                        current_positions[side] = {
                            "size": Decimal(pos.get("size", "0")),
                            "avg_price": Decimal(pos.get("avgPrice", "0")),
                            "unrealisedPnl": Decimal(pos.get("unrealisedPnl", "0")),
                        }
                except (KeyError, ValueError, DecimalException, TypeError) as e:
                    logger.error(f"{RED}Error processing REST position data: {type(e).__name__} - {e} | Position: {pos}. A position scroll is malformed.{NC}")

            ws_state["positions"] = current_positions # Overwrite with REST data
            logger.debug(f"{Fore.CYAN}REST sync: Found {len(current_positions)} active positions. The manifestations are tallied.{NC}")
            return current_positions
        logger.error(f"{RED}Failed to fetch positions via REST. The manifestations are obscured.{NC}")
        return {}

    async def place_order(self, side: str, qty: Decimal, price: Optional[Decimal] = None, client_order_id: Optional[str] = None, order_type: str = "Limit") -> Optional[Dict[str, Any]]:
        """Place a single order, applying quantization and minimum checks – Weaving a single thread into the market's fabric."""
        if order_type == "Limit" and price is None:
            logger.error(f"{RED}Price must be specified for a Limit order. A limit spell requires its target.{NC}")
            return None
        if order_type == "Market" and price is not None:
            logger.warning(f"{YELLOW}Price specified for Market order will be ignored. Market spells find their own price.{NC}")
            price = None

        # Quantize quantity and perform basic checks
        try:
            quantized_qty = qty.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            if quantized_qty <= Decimal("0"):
                logger.error(f"{RED}Order quantity {qty} results in zero or negative after quantization ({quantized_qty}). The quantity is too ethereal.{NC}")
                return None
            if symbol_info.get("min_qty", Decimal("0")) > Decimal("0") and quantized_qty < symbol_info["min_qty"]:
                 logger.error(f"{RED}Order quantity {quantized_qty} is below minimum required quantity ({symbol_info['min_qty']}). The quantity is too small for this realm.{NC}")
                 return None
        except DecimalException as e:
            logger.error(f"{RED}Error quantizing quantity {qty}: {e}. The quantity's essence is unstable.{NC}")
            return None

        # Quantize price and perform basic checks
        quantized_price = None
        if price is not None:
            try:
                rounding_method = ROUND_DOWN if side == "Buy" else ROUND_UP
                quantized_price = price.quantize(symbol_info["price_precision"], rounding=rounding_method)
                
                # Clamp price within market bounds
                quantized_price = max(symbol_info["min_price"], min(quantized_price, symbol_info["max_price"]))

                if symbol_info.get("min_price", Decimal("0")) > Decimal("0") and quantized_price < symbol_info["min_price"]:
                    logger.error(f"{RED}Order price {quantized_price} is below minimum required price ({symbol_info['min_price']}). The price is beyond the market's reach.{NC}")
                    return None
            except DecimalException as e:
                logger.error(f"{RED}Error quantizing price {price}: {e}. The price's essence is unstable.{NC}")
                return None

        # Enforce minimum and maximum order value constraints
        if quantized_price and quantized_qty:
            order_value = quantized_qty * quantized_price
            min_order_val_limit = symbol_info.get("min_order_value", Decimal("0"))
            max_order_val_limit = symbol_info.get("max_order_value_limit", Decimal("0"))

            if min_order_val_limit > Decimal("0") and order_value < min_order_val_limit:
                logger.error(f"{RED}Calculated order value ({order_value:.2f}) is below minimum required value ({min_order_val_limit:.2f}). The spell lacks sufficient value.{NC}")
                return None
            if max_order_val_limit > Decimal("0") and order_value > max_order_val_limit:
                logger.error(f"{RED}Calculated order value ({order_value:.2f}) exceeds maximum allowed value ({max_order_val_limit:.2f}). The spell is too grand.{NC}")
                return None

        # Construct payload for the order
        payload = {
            "category": CATEGORY,
            "symbol": SYMBOL,
            "side": side,
            "orderType": order_type,
            "qty": str(quantized_qty),
            "positionIdx": 1 if side == "Buy" else 2 # 1 for Buy (Long), 2 for Sell (Short) in Hedge Mode
        }
        if quantized_price:
            payload["price"] = str(quantized_price)
        if client_order_id:
            payload["orderLinkId"] = client_order_id
        if order_type == "Limit":
            payload["timeInForce"] = "GTC" # Good Till Cancelled

        logger.debug(f"{Fore.BLUE}Placing Order Payload: {payload}{NC}")
        response = await self._api(self.http.place_order, **payload)

        if response and response.get('retCode') == 0:
            order_info = response['result']
            session_stats["orders_placed"] += 1
            logger.info(f"{GREEN}Successfully placed {order_type} {side} order: ID={order_info.get('orderId', 'N/A')}, Qty={quantized_qty}, Price={quantized_price if quantized_price else 'N/A'}{NC}")
            # Add order to state immediately after successful placement
            ws_state["open_orders"][order_info.get('orderId')] = {
                "client_order_id": client_order_id,
                "symbol": SYMBOL,
                "side": side,
                "price": quantized_price,
                "qty": quantized_qty,
                "status": "New", # Assume "New" status initially
                "timestamp": time.time(),
            }
            return order_info
        else:
            logger.error(f"{RED}Failed to place {order_type} {side} order: {response.get('retMsg', 'Unknown error') if response else 'No response'}. The spell faltered.{NC}")
            return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific order – Dispelling a single enchantment."""
        response = await self._api(
            self.http.cancel_order,
            category=CATEGORY,
            symbol=SYMBOL,
            orderId=order_id
        )
        if response and response.get('retCode') == 0:
            logger.info(f"{GREEN}Successfully canceled order: {order_id}. The enchantment dissipates.{NC}")
            ws_state["open_orders"].pop(order_id, None) # Remove from tracking
            return True
        else:
            logger.error(f"{RED}Failed to cancel order {order_id}: {response.get('retMsg', 'Unknown error') if response else 'No response'}. The enchantment clings stubbornly.{NC}")
            return False

    async def cancel_all_orders(self) -> None:
        """Cancel all open orders for the current symbol – Sweeping away all active spells."""
        logger.warning(f"{YELLOW}Attempting to cancel all open orders for {SYMBOL}...{NC}")
        response = await self._api(
            self.http.cancel_all_orders,
            category=CATEGORY,
            symbol=SYMBOL
        )
        if response and response.get('retCode') == 0:
            logger.info(f"{GREEN}Successfully canceled all open orders for {SYMBOL}. The market is cleared.{NC}")
            ws_state["open_orders"].clear() # Clear the local cache
            send_toast("All orders cancelled!", "red", "white")
        else:
            logger.error(f"{RED}Failed to cancel all orders for {SYMBOL}: {response.get('retMsg', 'Unknown error') if response else 'No response'}. The market resists.{NC}")
            send_toast("Failed to cancel all orders!", "red", "white")

    async def place_batch_orders(self, orders: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Place multiple orders in a single batch request, with quantization and validation – Forging multiple threads simultaneously."""
        if not orders:
            logger.warning(f"{YELLOW}No orders provided for batch placement. No threads to weave.{NC}")
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
                    logger.warning(f"{YELLOW}Skipping batch order due to missing side or quantity: {order}. A thread is incomplete.{NC}")
                    continue

                # Quantize quantity and perform basic checks
                quantized_qty = qty.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
                if quantized_qty <= Decimal("0"):
                    logger.warning(f"{YELLOW}Skipping batch order due to zero/negative quantized quantity: {quantized_qty}. The thread is too fine.{NC}")
                    continue
                if symbol_info.get("min_qty", Decimal("0")) > Decimal("0") and quantized_qty < symbol_info["min_qty"]:
                     logger.warning(f"{YELLOW}Skipping batch order: quantity {quantized_qty} below minimum {symbol_info['min_qty']}. The thread is too short.{NC}")
                     continue

                # Quantize price and perform basic checks
                quantized_price = None
                if price is not None:
                    rounding_method = ROUND_DOWN if side == "Buy" else ROUND_UP
                    quantized_price = price.quantize(symbol_info["price_precision"], rounding=rounding_method)
                    # Clamp price within market bounds
                    quantized_price = max(symbol_info["min_price"], min(quantized_price, symbol_info["max_price"]))

                    if symbol_info.get("min_price", Decimal("0")) > Decimal("0") and quantized_price < symbol_info["min_price"]:
                        logger.warning(f"{YELLOW}Skipping batch order: price {quantized_price} below minimum {symbol_info['min_price']}. The price is too low for this weave.{NC}")
                        continue
                
                # Enforce minimum and maximum order value constraints
                if quantized_price and quantized_qty:
                    order_value = quantized_qty * quantized_price
                    min_order_val_limit = symbol_info.get("min_order_value", Decimal("0"))
                    max_order_val_limit = symbol_info.get("max_order_value_limit", Decimal("0"))

                    if min_order_val_limit > Decimal("0") and order_value < min_order_val_limit:
                        logger.warning(f"{YELLOW}Skipping batch order: calculated value ({order_value:.2f}) below minimum ({min_order_val_limit:.2f}). The weave lacks value.{NC}")
                        continue
                    if max_order_val_limit > Decimal("0") and order_value > max_order_val_limit:
                        logger.warning(f"{YELLOW}Skipping batch order: calculated value ({order_value:.2f}) exceeds maximum ({max_order_val_limit:.2f}). The spell is too grand.{NC}")
                        continue

                # Construct payload for a single order within the batch
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
                logger.error(f"{RED}Error preparing batch order {order}: {type(e).__name__} - {e}. A thread snapped during preparation.{NC}")
            except Exception as e:
                logger.error(f"{RED}Unexpected error preparing batch order {order}: {type(e).__name__} - {e}. An unknown force interfered.{NC}")

        if not batch_payloads:
            logger.warning(f"{YELLOW}No valid orders to place in batch after preparation. No viable threads remain.{NC}")
            return None

        logger.debug(f"{Fore.BLUE}Placing Batch Order Payloads: {batch_payloads}{NC}")
        response = await self._api(
            self.http.place_batch_order,
            category=CATEGORY,
            request=batch_payloads
        )

        if response and response.get('retCode') == 0:
            session_stats["orders_placed"] += len(batch_payloads)
            logger.info(f"{GREEN}Successfully placed {len(batch_payloads)} batch orders. The loom hums with new activity.{NC}")
            # Update local state with newly placed orders
            results = response.get("result", {}).get("list", [])
            for res in results:
                 oid = res.get("orderId")
                 if oid and oid not in ws_state["open_orders"]:
                     # Find the corresponding order from batch_payloads for details
                     original_order = next((p for p in batch_payloads if p.get("orderLinkId") == res.get("orderLinkId")), None)
                     if original_order:
                         ws_state["open_orders"][oid] = {
                            "client_order_id": res.get("orderLinkId"),
                            "symbol": original_order.get("symbol"),
                            "side": original_order.get("side"),
                            "price": Decimal(original_order.get("price", "0")) if original_order.get("price") else Decimal("0"),
                            "qty": Decimal(original_order.get("qty", "0")),
                            "status": "New", # Assume New status
                            "timestamp": time.time(),
                         }
            return response['result']
        else:
            logger.error(f"{RED}Failed to place batch orders: {response.get('retMsg', 'Unknown error') if response else 'No response'}. The batch spell faltered.{NC}")
            return None

# -----------------------------
# Market Making Strategy – The Core Enchantment
# -----------------------------

class MarketMakingStrategy:
    def __init__(self, client: BybitClient):
        self.client = client
        self.running = False
        self.rebalance_task = None
        self.pnl_monitor_task = None
        self.ws_monitor_task = None 
        self.last_mid_price_for_replacement = Decimal("0") # Tracks the mid-price when orders were last placed
        self.balance_update_interval = BALANCE_REFRESH_INTERVAL # How often to refresh the balance from REST API

    def _is_market_data_fresh(self) -> bool:
        """Checks if the market data (bid/ask/mid) is considered fresh – Ensuring the scrying mirror is clear."""
        if ws_state["last_update_time"] == 0 or ws_state["mid_price"] <= Decimal("0"):
            logger.debug(f"{YELLOW}Market data is not yet available or invalid. Awaiting clarity from the ether.{NC}")
            return False
        age = time.time() - ws_state["last_update_time"]
        if age > MAX_DATA_AGE_SECONDS:
            logger.warning(f"{YELLOW}Market data is stale (age: {age:.1f}s > {MAX_DATA_AGE_SECONDS}s). Skipping operation to avoid missteps.{NC}")
            send_toast("Market data stale!", "#FFA500", "white")
            return False
        return True

    def _calculate_dynamic_quantity(self) -> Decimal:
        """
        Calculates the order quantity dynamically based on global settings,
        available balance, market volatility, and API constraints – Weaving the quantity spell.
        """
        adjusted_qty = QUANTITY # Start with the base configured quantity

        # Adjust quantity based on available balance and minimum order value
        if ws_state["mid_price"] > Decimal("0") and ws_state["available_balance"] > Decimal("0"):
            allocation_percentage = Decimal("0.05") # Allocate 5% of available balance per order as a basis
            max_capital_per_order = ws_state["available_balance"] * allocation_percentage
            
            # Calculate minimum quantity required to meet the minimum order value
            min_qty_by_value = Decimal("0")
            if symbol_info.get("min_order_value", Decimal("0")) > Decimal("0"):
                # Avoid division by zero if mid_price is somehow 0 here
                if ws_state["mid_price"] > Decimal("0"):
                    min_qty_by_value = (symbol_info["min_order_value"] / ws_state["mid_price"]).quantize(symbol_info["qty_precision"], rounding=ROUND_UP)
                else: # Fallback if mid_price is zero
                    min_qty_by_value = symbol_info["min_qty"] # Use min_qty as a fallback

            # Calculate quantity based on capital allocation
            effective_qty_from_capital = Decimal("0")
            if ws_state["mid_price"] > Decimal("0"):
                effective_qty_from_capital = (max_capital_per_order / ws_state["mid_price"]).quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            
            # Take the smaller of base QUANTITY or capital-allocated quantity, but not less than min_qty_by_value
            adjusted_qty = min(adjusted_qty, max(effective_qty_from_capital, min_qty_by_value))
            
            # If adjusted_qty became non-positive due to constraints, use a fallback
            if adjusted_qty <= Decimal("0"):
                logger.warning(f"{YELLOW}Dynamic quantity adjusted to zero or less due to balance/min_order_value constraints. Falling back to min_qty or a small fraction of base QUANTITY.{NC}")
                adjusted_qty = max(symbol_info["min_qty"], QUANTITY * Decimal("0.1")) # Fallback to min_qty or 10% of base QUANTITY

        # Adjust quantity based on current market spread (volatility factor)
        current_spread_percent = (ws_state["best_ask"] - ws_state["best_bid"]) / ws_state["mid_price"] if ws_state["mid_price"] > 0 else Decimal("0")
        volatility_factor = Decimal("1")
        target_spread = SPREAD_PERCENTAGE
        
        if target_spread > Decimal("0") and current_spread_percent > Decimal("0"):
            # If current spread is wider than target, reduce quantity. If tighter, increase.
            volatility_factor_calc = target_spread / current_spread_percent
            volatility_factor = max(Decimal("0.5"), min(Decimal("1.5"), volatility_factor_calc)) # Cap factor between 0.5x and 1.5x

        adjusted_qty *= volatility_factor
        
        final_qty = adjusted_qty.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
        
        # Ensure final quantity meets exchange minimums (min_qty)
        if symbol_info.get("min_qty", Decimal("0")) > Decimal("0"):
            final_qty = max(final_qty, symbol_info["min_qty"])
        
        # Re-check against min_order_value after all adjustments, especially if quantity increased
        if symbol_info.get("min_order_value", Decimal("0")) > Decimal("0") and ws_state["mid_price"] > Decimal("0"):
            current_order_value = final_qty * ws_state["mid_price"]
            if current_order_value < symbol_info["min_order_value"]:
                recalculated_qty_for_min_value = (symbol_info["min_order_value"] / ws_state["mid_price"]).quantize(symbol_info["qty_precision"], rounding=ROUND_UP)
                final_qty = max(final_qty, recalculated_qty_for_min_value)
                logger.debug(f"{Fore.CYAN}Adjusted dynamic quantity to meet min order value: {final_qty}{NC}")

        # Apply API's maximum order value limit (maxNotional)
        max_order_val_limit = symbol_info.get("max_order_value_limit", Decimal("0"))
        if max_order_val_limit > Decimal("0") and ws_state["mid_price"] > Decimal("0"):
            order_value = final_qty * ws_state["mid_price"]
            if order_value > max_order_val_limit:
                logger.warning(f"{YELLOW}Calculated order value ({order_value:.2f}) exceeds API max notional ({max_order_val_limit:.2f}). Capping quantity.{NC}")
                capped_qty = (max_order_val_limit / ws_state["mid_price"]).quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
                final_qty = max(Decimal("0"), capped_qty) # Ensure quantity is not negative after capping

        # Final check: Ensure quantity is positive after all calculations
        if final_qty <= Decimal("0"):
            logger.warning(f"{YELLOW}Final calculated quantity is zero or negative. Cannot place order.{NC}")
            return Decimal("0")

        logger.debug(f"{Fore.CYAN}Dynamic Quantity Calculation: Base={QUANTITY}, Balance Adj Qty={adjusted_qty:.{_calculate_decimal_precision(symbol_info['qty_precision'])}}, Volatility Factor={volatility_factor:.2f}, Final={final_qty:.{_calculate_decimal_precision(symbol_info['qty_precision'])}}{NC}")
        return final_qty

    async def place_market_making_orders(self):
        """Manages the placement of limit orders for market making – Orchestrating the market's dance."""
        # Ensure bot is active and market data is fresh
        if BOT_STATE not in ["ACTIVE", "SYNCING"] or not self._is_market_data_fresh():
            return

        mid = ws_state["mid_price"]
        bid = ws_state["best_bid"]
        ask = ws_state["best_ask"]

        # Validate market conditions before proceeding
        if not self._is_valid_price(mid, bid, ask):
            return

        abnormal_market, reason = self._detect_abnormal_conditions()
        if abnormal_market:
            logger.critical(f"{RED}CIRCUIT BREAKER ACTIVATED: {reason}. Cancelling orders and pausing trading to prevent harm.{NC}")
            send_toast(f"Circuit Breaker: {reason[:30]}", "red", "white")
            await self.client.cancel_all_orders()
            session_stats["circuit_breaker_activations"] += 1
            # Update state and prevent further MM operations until reset or condition clears
            self.set_bot_state("CIRCUIT_BREAK") 
            await asyncio.sleep(60) # Pause for 1 minute to let the market stabilize
            self.set_bot_state("ACTIVE") # Re-enable after pause
            return

        # Check for significant price movement to re-center orders
        if self.last_mid_price_for_replacement > Decimal("0") and mid > Decimal("0"):
            try:
                price_change = abs(mid - self.last_mid_price_for_replacement) / self.last_mid_price_for_replacement
                if price_change >= PRICE_THRESHOLD:
                    logger.info(f"{YELLOW}Price moved {price_change:.4%}, initiating order re-placement sequence. The market's ground has shifted.{NC}")
                    send_toast(f"Price moved {price_change:.2%}, re-placing orders.", "blue", "white")
                    await self.client.cancel_all_orders()
                    self.last_mid_price_for_replacement = mid # Update reference price
            except DecimalException:
                logger.warning(f"{YELLOW}Decimal division error during price change calculation for price threshold. A numerical tremor.{NC}")
        
        await self._cancel_stale_orders() # Remove old orders that have expired

        # Check if max open orders limit is reached
        if len(ws_state["open_orders"]) >= MAX_OPEN_ORDERS:
            logger.debug(f"{Fore.CYAN}Max open orders ({MAX_OPEN_ORDERS}) reached. Skipping new MM orders. The market's capacity is full.{NC}")
            return

        # Calculate target prices for new limit orders
        bid_price_calc = mid * (Decimal("1") - SPREAD_PERCENTAGE)
        ask_price_calc = mid * (Decimal("1") + SPREAD_PERCENTAGE)

        # Quantize calculated prices and clamp them within market bounds (min/max price)
        # Also ensure bid < ask, and respect best bid/ask as ultimate boundaries.
        quantized_bid_price = bid_price_calc.quantize(symbol_info["price_precision"], rounding=ROUND_DOWN)
        quantized_ask_price = ask_price_calc.quantize(symbol_info["price_precision"], rounding=ROUND_UP)

        # Clamp prices within market limits AND ensure bid is strictly less than ask
        bid_price_final = max(symbol_info["min_price"], min(quantized_bid_price, quantized_ask_price - symbol_info["price_precision"]))
        ask_price_final = min(symbol_info["max_price"], max(quantized_ask_price, bid_price_final + symbol_info["price_precision"]))
        
        # Further clamp to best bid/ask if calculated prices drift too far
        bid_price_final = min(bid_price_final, bid)
        ask_price_final = max(ask_price_final, ask)

        # Final sanity check: If prices somehow crossed, revert to best bid/ask as a safe fallback.
        if bid_price_final >= ask_price_final:
            logger.warning(f"{YELLOW}Calculated bid/ask prices crossed after clamping. Mid: {mid}. Bid: {bid_price_final}, Ask: {ask_price_final}. Adjusting to avoid invalid state.{NC}")
            bid_price_final = bid
            ask_price_final = ask
            # If even best bid/ask are invalid, we shouldn't place orders
            if not self._is_valid_price(bid_price_final, ask_price_final):
                return

        dynamic_order_qty = self._calculate_dynamic_quantity()

        if dynamic_order_qty <= Decimal("0"):
            logger.warning(f"{YELLOW}Dynamic order quantity calculated to zero or less. Skipping order placement. The quantity is too faint.{NC}")
            return

        orders_to_place = []
        
        # Place a Buy order if no existing Buy order and within max order limit
        if not any(o['side'] == 'Buy' for o in ws_state["open_orders"].values()) and len(ws_state["open_orders"]) < MAX_OPEN_ORDERS:
            client_buy_id = f"mmxcel-buy-{int(time.time() * 1000)}"
            orders_to_place.append({
                "side": "Buy",
                "qty": dynamic_order_qty,
                "price": bid_price_final,
                "client_order_id": client_buy_id,
                "orderType": "Limit"
            })

        # Place a Sell order if no existing Sell order and within remaining max order limit
        if not any(o['side'] == 'Sell' for o in ws_state["open_orders"].values()) and (len(ws_state["open_orders"]) + len(orders_to_place)) < MAX_OPEN_ORDERS:
            client_sell_id = f"mmxcel-sell-{int(time.time() * 1000)}"
            orders_to_place.append({
                "side": "Sell",
                "qty": dynamic_order_qty,
                "price": ask_price_final,
                "client_order_id": client_sell_id,
                "orderType": "Limit"
            })

        if orders_to_place:
            self.set_bot_state("PLACING_ORDERS") # Update state
            await self.client.place_batch_orders(orders_to_place)
            # No need to update last_mid_price_for_replacement here, it's updated when orders are placed successfully.
            # If orders_to_place was empty, it means all slots are filled, so no new placement is needed.
        elif not ws_state["open_orders"]:
             # If no orders were placed and none exist, still update last_mid_price to prevent immediate re-cancellation on next loop
             self.last_mid_price_for_replacement = mid

        # If no orders were placed but there are open orders, ensure state remains ACTIVE
        if len(ws_state["open_orders"]) > 0 and self.bot_state == "PLACING_ORDERS":
             self.set_bot_state("ACTIVE")
        elif len(ws_state["open_orders"]) == 0 and self.bot_state == "PLACING_ORDERS": # If all orders got filled/cancelled during placement
             self.set_bot_state("ACTIVE")

    async def _cancel_stale_orders(self):
        """Cancel orders that have exceeded their lifespan – Dispelling lingering enchantments."""
        stale_order_ids = []
        for oid, data in list(ws_state["open_orders"].items()):
            if data.get("timestamp") is None:
                logger.warning(f"{YELLOW}Order {oid} missing timestamp, considering stale. Its age is unknown.{NC}")
                stale_order_ids.append(oid)
                continue
            if time.time() - data["timestamp"] > ORDER_LIFESPAN_SECONDS:
                stale_order_ids.append(oid)
        
        if stale_order_ids:
            logger.info(f"{YELLOW}Found {len(stale_order_ids)} stale orders. Cancelling them to clear the path...{NC}")
            send_toast(f"Cancelling {len(stale_order_ids)} stale orders.", "orange", "white")
            tasks = [self.client.cancel_order(oid) for oid in stale_order_ids]
            await asyncio.gather(*tasks)

    def _is_valid_price(self, *prices) -> bool:
        """Check if prices are valid (non-zero, non-negative Decimals) – Verifying the market's coordinates."""
        for p in prices:
            if not isinstance(p, Decimal) or p <= Decimal("0"):
                logger.debug(f"{YELLOW}Invalid price detected: {p}. Skipping. The coordinates are askew.{NC}")
                return False
        return True

    ABNORMAL_SPREAD_THRESHOLD = Decimal("0.015") # Example: 1.5% spread, a sign of market turbulence
    
    def _detect_abnormal_conditions(self) -> Tuple[bool, str]:
        """Detects abnormal market conditions like excessively wide spread – Sensing disturbances in the ether."""
        mid = ws_state["mid_price"]
        bid = ws_state["best_bid"]
        ask = ws_state["best_ask"]

        if mid <= Decimal("0") or bid <= Decimal("0") or ask <= Decimal("0"):
            return True, "Market data unavailable or invalid. The scrying mirror is dark."

        if bid >= ask:
            return True, f"Bid ({bid}) is greater or equal to Ask ({ask}). The market's logic is inverted!"

        spread_percent = (ask - bid) / mid
        if spread_percent > self.ABNORMAL_SPREAD_THRESHOLD:
            return True, f"Excessive spread: {spread_percent:.2%}. The market is too volatile."
        
        return False, ""

    async def rebalance_inventory(self):
        """Rebalance the position if it deviates from neutral beyond a threshold – Restoring equilibrium."""
        if not self._is_market_data_fresh():
            return

        long_size = ws_state['positions'].get('Long', {}).get('size', Decimal('0'))
        short_size = ws_state['positions'].get('Short', {}).get('size', Decimal('0'))
        net_position = long_size - short_size

        if abs(net_position) > REBALANCE_THRESHOLD_QTY:
            side_to_close = "Sell" if net_position > Decimal("0") else "Buy" # Sell to close long, Buy to close short
            qty_to_rebalance = abs(net_position).quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)
            
            if qty_to_rebalance <= Decimal("0"):
                logger.warning(f"{YELLOW}Rebalance quantity is zero after quantization. Skipping rebalance. The imbalance is too subtle.{NC}")
                return
            
            logger.info(f"{YELLOW}Inventory imbalance detected: Net Position {net_position:.{_calculate_decimal_precision(symbol_info['qty_precision'])}f}. Rebalancing by closing {side_to_close} {qty_to_rebalance}. Restoring balance to the scales.{NC}")
            send_toast(f"Rebalancing {qty_to_rebalance} {SYMBOL}!", "yellow", "black")
            
            self.set_bot_state("REBALANCING") # Update state
            rebalance_order_info = await self.client.place_order(side_to_close, qty_to_rebalance, order_type="Market")
            if rebalance_order_info:
                session_stats["rebalances_count"] += 1
            # Refresh positions and orders after rebalance to reflect changes
            await self.client.get_positions_rest()
            await self.client.get_open_orders_rest()
            self.set_bot_state("ACTIVE") # Return to active state
        else:
            logger.debug(f"{Fore.CYAN}Net position {net_position:.{_calculate_decimal_precision(symbol_info['qty_precision'])}f} within threshold. No rebalance needed. Equilibrium holds.{NC}")

    async def monitor_pnl(self):
        """Monitors positions for stop-loss and profit-take conditions – Divining the fate of your investments."""
        while self.running and not _SHUTDOWN_REQUESTED:
            if BOT_STATE not in ["ACTIVE", "SYNCING", "REBALANCING"] or not self._is_market_data_fresh():
                await asyncio.sleep(PNL_MONITOR_INTERVAL)
                continue

            mid = ws_state["mid_price"]
            long_pos = ws_state["positions"].get("Long")
            short_pos = ws_state["positions"].get("Short")
            
            # Monitor Long Position
            if long_pos and long_pos["size"] > Decimal("0") and long_pos["avg_price"] > Decimal("0"):
                entry_price = long_pos["avg_price"]
                pnl_percent = (mid - entry_price) / entry_price
                
                # Stop Loss Trigger
                if pnl_percent < -STOP_LOSS_PERCENTAGE:
                    logger.critical(f"{RED}Long position stop-loss triggered! PnL: {pnl_percent:.2%}. Exiting position to stem the bleed.{NC}")
                    send_toast(f"Long SL: {pnl_percent:.2%}! Closing.", "red", "white")
                    await self.client.cancel_all_orders()
                    await self.client.place_order("Sell", long_pos["size"], order_type="Market")
                    await self.client.get_positions_rest() # Refresh position data
                # Profit Take Trigger
                elif pnl_percent >= PROFIT_PERCENTAGE:
                    logger.info(f"{GREEN}Long position profit-take triggered! PnL: {pnl_percent:.2%}. Exiting position to secure the bounty.{NC}")
                    send_toast(f"Long TP: {pnl_percent:.2%}! Closing.", "green", "white")
                    await self.client.cancel_all_orders()
                    await self.client.place_order("Sell", long_pos["size"], order_type="Market")
                    await self.client.get_positions_rest() # Refresh position data
            
            # Monitor Short Position
            if short_pos and short_pos["size"] > Decimal("0") and short_pos["avg_price"] > Decimal("0"):
                entry_price = short_pos["avg_price"]
                pnl_percent = (entry_price - mid) / entry_price # PnL calculation for short position
                
                # Stop Loss Trigger
                if pnl_percent < -STOP_LOSS_PERCENTAGE:
                    logger.critical(f"{RED}Short position stop-loss triggered! PnL: {pnl_percent:.2%}. Exiting position to stem the bleed.{NC}")
                    send_toast(f"Short SL: {pnl_percent:.2%}! Closing.", "red", "white")
                    await self.client.cancel_all_orders()
                    await self.client.place_order("Buy", short_pos["size"], order_type="Market")
                    await self.client.get_positions_rest() # Refresh position data
                # Profit Take Trigger
                elif pnl_percent >= PROFIT_PERCENTAGE:
                    logger.info(f"{GREEN}Short position profit-take triggered! PnL: {pnl_percent:.2%}. Exiting position to secure the bounty.{NC}")
                    send_toast(f"Short TP: {pnl_percent:.2%}! Closing.", "green", "white")
                    await self.client.cancel_all_orders()
                    await self.client.place_order("Buy", short_pos["size"], order_type="Market")
                    await self.client.get_positions_rest() # Refresh position data
            
            await asyncio.sleep(PNL_MONITOR_INTERVAL)

    def set_bot_state(self, new_state: str):
        """Updates the bot's operational state and logs the change."""
        global BOT_STATE
        if BOT_STATE != new_state:
            BOT_STATE = new_state
            logger.info(f"{Fore.MAGENTA}Bot State changed to: {BOT_STATE}{NC}")

    def get_bot_state(self) -> str:
        """Returns the current bot operational state."""
        return BOT_STATE

# -----------------------------
# Signal Handling and Main Execution – The Grand Ritual
# -----------------------------

def signal_handler(signum, frame):
    """Handles signals for graceful shutdown – Acknowledging the call to cease the spell."""
    global _SHUTDOWN_REQUESTED
    logger.info(f"{Fore.RED}Interruption signal ({signum}) received. Initiating graceful shutdown... The ritual is concluding.{NC}")
    _SHUTDOWN_REQUESTED = True
    send_toast("MMXCEL: Shutdown initiated.", "red", "white")

# Register the signal handler – Attuning to external commands
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

async def read_hotkey(timeout: float = 0.1) -> Optional[str]:
    """Reads a single character from stdin if available, without blocking – Sensing direct commands."""
    # Use select to check if stdin is ready for reading
    rlist, _, _ = select.select([sys.stdin], [], [], timeout)
    if rlist:
        return sys.stdin.read(1) # Read a single character
    return None

async def main():
    """The main invocation of Pyrmethus's market-making spell."""
    global _HAS_TERMUX_TOAST_CMD
    global _SHUTDOWN_REQUESTED

    # Inform the user about required Termux packages and setup
    print(f"{Fore.CYAN}{BOLD}\n# Before commencing the ritual, ensure these arcane tools are present:{NC}")
    print(f"{Fore.YELLOW}#   {Style.BRIGHT}pkg install python nodejs termux-api{NC}")
    print(f"{Fore.YELLOW}#   {Style.BRIGHT}pip install python-dotenv pybit-unified-trading colorama{NC}")
    print(f"{Fore.YELLOW}#   {Style.BRIGHT}npm install chalk{NC} (if using JavaScript components or for future expansion)")
    print(f"{Fore.YELLOW}#   Also, install the 'Termux:API' app from F-Droid or Google Play.\n{NC}")
    
    # Check for termux-toast availability and log if missing
    _HAS_TERMUX_TOAST_CMD = check_termux_toast()
    if not _HAS_TERMUX_TOAST_CMD:
        logger.warning(f"{YELLOW}Termux:API 'termux-toast' command not found. Device notifications will be disabled.{NC}")
        logger.warning(f"{YELLOW}To enable, ensure 'pkg install termux-api' is run and Termux:API app is installed.{NC}")


    print_neon_header("MMXCEL - Market Making Live", color=UNDERLINE)
    print(f"{Fore.CYAN}  {BOLD}A creation by Pyrmethus, the Termux Coding Wizard{NC}")
    print_neon_separator()

    # Validate API credentials from environment variables
    if not API_KEY or not API_SECRET:
        logger.error(f"{RED}API_KEY or API_SECRET not found in .env. Aborting ritual. The sacred keys are missing.{NC}")
        send_toast("MMXCEL: API keys missing!", "red", "white")
        sys.exit(1)

    # Initialize core components: Bybit Client and Market Making Strategy
    client = BybitClient(API_KEY, API_SECRET, USE_TESTNET)
    strategy = MarketMakingStrategy(client)

    # Initial setup and validation rituals
    logger.info(f"{Fore.YELLOW}Testing the connection to the Bybit API realm... Channeling initial energies.{NC}")
    if not await client.test_credentials():
        logger.error(f"{RED}Failed to validate API credentials. Check your .env file and network connection. The connection to the realm is severed.{NC}")
        send_toast("MMXCEL: Credential validation failed!", "red", "white")
        sys.exit(1)

    logger.info(f"{Fore.YELLOW}Unveiling the hidden paths of {SYMBOL}... Discovering market intricacies.{NC}")
    if not await client.get_symbol_info():
        logger.error(f"{RED}Failed to retrieve symbol information for {SYMBOL}. Is the symbol correct? The market's blueprint is unreadable.{NC}")
        send_toast(f"MMXCEL: Failed to get {SYMBOL} info!", "red", "white")
        sys.exit(1)

    # Set initial bot state
    strategy.set_bot_state("INITIALIZING")

    logger.info(f"{Fore.GREEN}All preliminary checks complete. The realm is ready for our spell! Commencing market surveillance.{NC}")
    send_toast("MMXCEL: Bot initializing...", "green", "white")

    strategy.running = True
    client.start_websockets() # Initiate WS connections

    # Create background tasks for continuous monitoring and operations
    strategy.ws_monitor_task = asyncio.create_task(client._monitor_websockets(strategy), name="ws_monitor_task")
    strategy.pnl_monitor_task = asyncio.create_task(strategy.monitor_pnl(), name="pnl_monitor_task")

    # Perform initial data synchronization from REST API
    await client.get_open_orders_rest()
    await client.get_positions_rest()
    await client.get_balance()

    # Timestamps for periodic task execution
    last_order_refresh_time = 0
    last_balance_refresh_time = 0
    
    # Set bot state to ACTIVE after initial sync
    strategy.set_bot_state("ACTIVE")

    try:
        # Main event loop – The heart of the magical operation
        while strategy.running and not _SHUTDOWN_REQUESTED:
            clear_screen() # Refresh the display
            print_neon_header(f"MMXCEL - Market Making ({SYMBOL})", color=UNDERLINE)
            
            # Determine precision for display
            price_disp_precision = _calculate_decimal_precision(symbol_info["price_precision"])
            qty_disp_precision = _calculate_decimal_precision(symbol_info["qty_precision"])

            # Display Market Data
            print(f"\n{Fore.CYAN}{BOLD}Market Data & Status:{NC}")
            print(format_metric("Bot State", strategy.get_bot_state(), Fore.CYAN))
            print(format_metric("Mid Price", ws_state["mid_price"], Fore.BLUE, value_precision=price_disp_precision, unit=f" {SYMBOL.replace('USDT', '')}/USDT"))
            print(format_metric("Best Bid", ws_state["best_bid"], Fore.BLUE, value_precision=price_disp_precision, unit=f" {SYMBOL.replace('USDT', '')}/USDT"))
            print(format_metric("Best Ask", ws_state["best_ask"], Fore.BLUE, value_precision=price_disp_precision, unit=f" {SYMBOL.replace('USDT', '')}/USDT"))
            print(format_metric("Data Freshness", (time.time() - ws_state["last_update_time"]), Fore.MAGENTA, value_precision=1, unit="s"))
            print_neon_separator(char="═")

            # Display Account Information
            print(f"{Fore.CYAN}{BOLD}Account Information:{NC}")
            print(format_metric("Available Balance", ws_state["available_balance"], Fore.GREEN, value_precision=4, unit=" USDT"))
            print(format_metric("Last Balance Update", (time.time() - ws_state["last_balance_update"]), Fore.MAGENTA, value_precision=0, unit="s ago"))
            print_neon_separator(char="═")

            # Display Current Positions
            print(f"{Fore.CYAN}{BOLD}Current Positions ({SYMBOL}):{NC}")
            long_pos = ws_state["positions"].get("Long", {"size": Decimal("0"), "unrealisedPnl": Decimal("0")})
            short_pos = ws_state["positions"].get("Short", {"size": Decimal("0"), "unrealisedPnl": Decimal("0")})
            
            print(format_metric("Long Size", long_pos["size"], Fore.GREEN, value_precision=qty_disp_precision, unit=f" {SYMBOL.replace('USDT', '')}"))
            print(format_metric("Long PnL", long_pos["unrealisedPnl"], Fore.GREEN, value_precision=4, is_pnl=True, unit=" USDT"))
            print(format_metric("Short Size", short_pos["size"], Fore.RED, value_precision=qty_disp_precision, unit=f" {SYMBOL.replace('USDT', '')}"))
            print(format_metric("Short PnL", short_pos["unrealisedPnl"], Fore.RED, value_precision=4, is_pnl=True, unit=" USDT"))
            net_pos_val = long_pos["size"] - short_pos["size"]
            print(format_metric("Net Position", net_pos_val, Fore.YELLOW, value_precision=qty_disp_precision, unit=f" {SYMBOL.replace('USDT', '')}"))
            print_neon_separator(char="═")

            # Display Active Orders
            print(f"{Fore.CYAN}{BOLD}Active Orders ({len(ws_state['open_orders'])}):{NC}")
            if not ws_state["open_orders"]:
                print(f"{Fore.YELLOW}  No active orders channeling the market's flow.{NC}")
            else:
                # Display only a few orders if too many, or scrollable might be better if this was a GUI.
                # For console, showing all up to a reasonable limit is fine.
                order_count = 0
                for oid, order in ws_state["open_orders"].items():
                    if order_count < MAX_OPEN_ORDERS + 2: # Display a few more than max, for context
                        price_color = GREEN if order['side'] == 'Buy' else RED
                        print(f"  {order['side']} {order['qty']:.{qty_disp_precision}f} @ {price_color}{order['price']:.{price_disp_precision}f}{NC} (Client: {order['client_order_id']})")
                        order_count += 1
                    else:
                        print(f"  ... and {len(ws_state['open_orders']) - order_count} more.")
                        break
            print_neon_separator(char="═")

            # Display Session Statistics
            print(f"{Fore.CYAN}{BOLD}Session Statistics:{NC}")
            elapsed_time = time.time() - session_stats["start_time"]
            hours, rem = divmod(elapsed_time, 3600)
            minutes, seconds = divmod(rem, 60)
            print(format_metric("Uptime", f"{int(hours):02d}h {int(minutes):02d}m {int(seconds):02d}s", Fore.MAGENTA))
            print(format_metric("Orders Placed", session_stats["orders_placed"], Fore.MAGENTA))
            print(format_metric("Orders Filled", session_stats["orders_filled"], Fore.MAGENTA))
            print(format_metric("Rebalances Triggered", session_stats["rebalances_count"], Fore.MAGENTA))
            total_session_pnl = long_pos["unrealisedPnl"] + short_pos["unrealisedPnl"]
            print(format_metric("Total Unrealized PnL", total_session_pnl, Fore.MAGENTA, is_pnl=True, value_precision=4, unit=" USDT"))
            print(format_metric("Circuit Breaker Hits", session_stats["circuit_breaker_activations"], Fore.RED))
            print_neon_separator()
            print(f"{Fore.YELLOW}Commands: 'q' to quit, 'c' to cancel all orders, 'r' to force rebalance.{NC}")

            # --- Periodic Task Execution ---
            current_time = time.time()

            # Refresh orders and potentially place new market-making orders
            if current_time - last_order_refresh_time >= ORDER_REFRESH_INTERVAL:
                logger.debug(f"{Fore.CYAN}Initiating periodic order and position sync...{NC}")
                await client.get_open_orders_rest()
                await client.get_positions_rest() # Sync positions as well for rebalance logic
                if BOT_STATE == "ACTIVE": # Only place MM orders when active
                    await strategy.place_market_making_orders()
                last_order_refresh_time = current_time

            # Refresh account balance periodically
            if current_time - last_balance_refresh_time >= strategy.balance_update_interval:
                logger.debug(f"{Fore.CYAN}Initiating periodic balance refresh...{NC}")
                await client.get_balance()
                last_balance_refresh_time = current_time

            # Rebalance task: Ensure it runs if not already active or if it completed
            if strategy.rebalance_task is None or strategy.rebalance_task.done():
                # Only trigger rebalance if bot is active and not in circuit break
                if BOT_STATE == "ACTIVE":
                    strategy.rebalance_task = asyncio.create_task(strategy.rebalance_inventory(), name="rebalance_task")
            
            # --- Hotkey Input Handling ---
            # Read hotkey input without blocking the main loop for too long
            key = await read_hotkey(timeout=1.0) # Check for keypress every second
            if key == 'q':
                _SHUTDOWN_REQUESTED = True
            elif key == 'c':
                logger.critical(f"{Fore.YELLOW}Hotkey 'c' pressed. Cancelling all open orders... A wave of dismissal.{NC}")
                send_toast("MMXCEL: Cancelling all orders.", "orange", "white")
                await client.cancel_all_orders()
                await client.get_open_orders_rest() # Refresh immediately after manual cancel
            elif key == 'r':
                logger.critical(f"{Fore.YELLOW}Hotkey 'r' pressed. Forcing rebalance... Compelling equilibrium.{NC}")
                send_toast("MMXCEL: Forcing rebalance.", "purple", "white")
                # Cancel any ongoing rebalance task to force a new one
                if strategy.rebalance_task and not strategy.rebalance_task.done():
                    strategy.rebalance_task.cancel()
                    try: await strategy.rebalance_task # Await its cancellation
                    except asyncio.CancelledError: pass
                # Ensure rebalance can run if bot is active
                if BOT_STATE == "ACTIVE":
                    strategy.rebalance_task = asyncio.create_task(strategy.rebalance_inventory(), name="rebalance_task")
                else:
                    logger.warning(f"{YELLOW}Cannot force rebalance. Bot is not in ACTIVE state (Current: {BOT_STATE}).{NC}")

    except asyncio.CancelledError:
        logger.info(f"{Fore.MAGENTA}Main loop cancelled, initiating cleanup... The spell's core is winding down.{NC}")
    except Exception as e:
        # Catch any unexpected errors during the main loop execution
        logger.critical(f"{RED}An unhandled exception halted the spell: {type(e).__name__} - {e}{NC}", exc_info=True)
        send_toast(f"MMXCEL: Critical Error! {type(e).__name__}", "red", "white")
    finally:
        # Ensure graceful shutdown sequence
        strategy.running = False
        strategy.set_bot_state("SHUTDOWN")
        logger.info(f"{Fore.MAGENTA}Cancelling remaining tasks and closing connections... Releasing the channeled energies.{NC}")
        
        # Gather all background tasks to ensure they complete or are cancelled cleanly
        tasks_to_gather = [
            strategy.ws_monitor_task,
            strategy.pnl_monitor_task,
            strategy.rebalance_task, # Ensure rebalance task is included if it was started
        ]
        await asyncio.gather(*(task for task in tasks_to_gather if task is not None), return_exceptions=True)

        # Final cleanup: Cancel any remaining open orders and close WebSocket connections
        await client.cancel_all_orders() 
        # Explicitly call exit() on WebSocket objects to clean up pybit's internal threads/connections
        client.ws_public.exit()
        client.ws_private.exit()
        
        logger.info(f"{Fore.GREEN}MMXCEL spell gracefully concluded. May your digital journey be ever enlightened.{NC}")
        send_toast("MMXCEL: Shutdown complete.", "green", "white")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Catch KeyboardInterrupt specifically if it occurs before asyncio.run finishes
        logger.info(f"{Fore.RED}KeyboardInterrupt detected. The user has manually halted the spell. Exiting.{NC}")
    except Exception as e:
        # Catch any fatal errors during the initial asyncio setup or run phase
        logger.critical(f"{RED}Fatal error during bot execution: {type(e).__name__} - {e}. The grand ritual failed unexpectedly.{NC}")
