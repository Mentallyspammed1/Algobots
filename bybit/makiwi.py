#!/usr/bin/env python3
"""MMXCEL v3.0 – Bybit Hedge-Mode Market-Making Bot
Major enhancements, bug fixes, and performance improvements for v3.0.
- Fixed 'return outside function' SyntaxError.
- Improved asynchronous API calls with robust retries and error handling.
- Enhanced position and order management.
- Added dynamic dashboard functionality.
Author: Pyrmethus, Termux-Coding Wizard
"""

import asyncio
import json
import logging
import logging.handlers
import os
import signal
import sys
import time
import uuid
from decimal import ROUND_DOWN
from decimal import Decimal
from decimal import DecimalException
from decimal import getcontext
from typing import Any

from colorama import Fore
from colorama import Style
from colorama import init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP
from pybit.unified_trading import WebSocket

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

    def colored(text, color, attrs=None):
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
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5
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
CAPITAL_ALLOCATION_PERCENTAGE = Decimal(
    str(config.get("CAPITAL_ALLOCATION_PERCENTAGE", "0.05"))
)
ABNORMAL_SPREAD_THRESHOLD = Decimal(
    str(config.get("ABNORMAL_SPREAD_THRESHOLD", "0.015"))
)
REBALANCE_ORDER_TYPE = str(config.get("REBALANCE_ORDER_TYPE", "Market"))
REBALANCE_PRICE_OFFSET_PERCENTAGE = Decimal(
    str(config.get("REBALANCE_PRICE_OFFSET_PERCENTAGE", "0"))
)

# Constants for data freshness and retry delays
MAX_DATA_AGE_SECONDS = 10
MAX_RETRIES_API = 5
RETRY_DELAY_API = 2
WS_MONITOR_INTERVAL = 10
PNL_MONITOR_INTERVAL = 5
DASHBOARD_REFRESH_INTERVAL = 1

# Exchange precision placeholders (initialized globally)
symbol_info = {
    "price_precision": Decimal("0.0001"),
    "qty_precision": Decimal("0.001"),
    "min_order_value": Decimal("10.0"),
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
    "last_update_time": 0,
    "last_balance_update": 0,
    "available_balance": Decimal("0"),
}

# Global session statistics
session_stats = {
    "start_time": time.time(),
    "orders_placed": 0,
    "orders_filled": 0,
    "rebalances_count": 0,
    "circuit_breaker_activations": 0,
    "total_pnl": Decimal("0"),
}

# Global state for bot operations
BOT_STATE = "INITIALIZING"

_HAS_TERMUX_TOAST_CMD = False
_SHUTDOWN_REQUESTED = False

# -----------------------------
# Helper Functions
# -----------------------------


def set_bot_state(state: str):
    """Sets the global bot state and logs the change."""
    global BOT_STATE
    if state != BOT_STATE:
        logger.info(f"{Fore.CYAN}Bot State Change: {BOT_STATE} -> {state}{NC}")
        BOT_STATE = state


def _calculate_decimal_precision(d: Decimal) -> int:
    """Determine the number of decimal places in a Decimal value for display."""
    if not isinstance(d, Decimal):
        return 0
    return abs(d.as_tuple().exponent)


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
        current_precision = (
            value_precision
            if value_precision is not None
            else _calculate_decimal_precision(value)
        )
        if is_pnl:
            actual_value_color = GREEN if value >= Decimal("0") else RED
            formatted_value = (
                f"{actual_value_color}{value:,.{current_precision}f}{unit}{NC}"
            )
        else:
            formatted_value = (
                f"{actual_value_color}{value:,.{current_precision}f}{unit}{NC}"
            )
    elif isinstance(value, (int, float)):
        if is_pnl:
            actual_value_color = GREEN if value >= 0 else RED
            formatted_value = f"{actual_value_color}{value:,}{unit}{NC}"
        else:
            formatted_value = f"{actual_value_color}{value:,}{unit}{NC}"
    else:
        formatted_value = f"{actual_value_color}{value!s}{unit}{NC}"
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


def get_paged_results(batch_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Combines list results from multiple paginated API calls."""
    if not isinstance(batch_results, list) or not all(
        "list" in r for r in batch_results
    ):
        logger.error("Invalid batch_results format for get_paged_results.")
        return {"list": []}
    # Fix: This code block was outside of the function, causing a SyntaxError.
    return {"list": [item for sublist in batch_results for item in sublist["list"]]}


# -----------------------------
# WebSocket Callbacks
# -----------------------------


def on_public_ws_message(msg: dict[str, Any]) -> None:
    """Handle public WebSocket messages (orderbook)."""
    try:
        topic = msg.get("topic")
        if topic and topic.startswith("orderbook.1."):
            data = msg.get("data")
            if data and data.get("b") and data.get("a"):
                bid_info = data["b"][0]
                ask_info = data["a"][0]

                ws_state["best_bid"] = Decimal(bid_info[0])
                ws_state["best_ask"] = Decimal(ask_info[0])
                if ws_state["best_bid"] > 0 and ws_state["best_ask"] > 0:
                    ws_state["mid_price"] = (
                        ws_state["best_bid"] + ws_state["best_ask"]
                    ) / Decimal("2")
                else:
                    ws_state["mid_price"] = Decimal("0")

                ws_state["last_update_time"] = time.time()
                logger.debug(
                    f"WS Orderbook: Bid={ws_state['best_bid']:.4f}, Ask={ws_state['best_ask']:.4f}, Mid={ws_state['mid_price']:.4f}"
                )
    except (KeyError, IndexError, ValueError, TypeError, DecimalException) as e:
        logger.error(
            f"Error processing public WS message: {type(e).__name__} - {e} | Message: {msg}"
        )
    except Exception as e:
        logger.error(
            f"Unexpected error in public WS handler: {type(e).__name__} - {e} | Message: {msg}"
        )


def on_private_ws_message(msg: dict[str, Any]) -> None:
    """Handle private WebSocket messages (orders, positions)."""
    try:
        topic = msg.get("topic")
        if topic == "order":
            for o in msg["data"]:
                oid = o.get("orderId")
                if not oid:
                    continue

                if o.get("orderStatus") in ("Filled", "Canceled", "Deactivated"):
                    if oid in ws_state["open_orders"]:
                        order_details = ws_state["open_orders"].pop(oid, None)
                        if order_details and o["orderStatus"] == "Filled":
                            session_stats["orders_filled"] += 1
                            filled_price = Decimal(
                                o.get("avgPrice", o.get("price", "0"))
                            )
                            filled_qty = Decimal(o.get("qty", "0"))
                            side = o.get("side", "N/A")
                            filled_value = filled_price * filled_qty
                            logger.info(
                                f"Order filled: {side} {filled_qty} @ {filled_price:.4f} (Value: {filled_value:.2f})"
                            )
                            send_toast(
                                f"Order filled: {side} {filled_qty}", "green", "white"
                            )

                            # Simple PnL tracking for filled orders (can be enhanced)
                            # This is a basic approach and might not reflect true PnL in all scenarios
                            # (e.g., when a position is closed by multiple trades).
                            positions = ws_state.get("positions", {})
                            if side == "Buy" and "Long" in positions:
                                position_info = positions["Long"]
                                if position_info["size"] > 0:
                                    # Simple PnL for closing a short position with a buy order
                                    pnl = (
                                        position_info["avg_price"] - filled_price
                                    ) * filled_qty
                                    session_stats["total_pnl"] += pnl
                            elif side == "Sell" and "Short" in positions:
                                position_info = positions["Short"]
                                if position_info["size"] > 0:
                                    # Simple PnL for closing a long position with a sell order
                                    pnl = (
                                        filled_price - position_info["avg_price"]
                                    ) * filled_qty
                                    session_stats["total_pnl"] += pnl

                    logger.debug(
                        f"WS Order Closed: ID {oid}, Status {o['orderStatus']}"
                    )
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
                if p.get("symbol") == SYMBOL and p.get("positionIdx") != 2:
                    side = "Long" if p.get("side") == "Buy" else "Short"
                    current_unrealised_pnl = Decimal(p.get("unrealisedPnl", "0"))

                    ws_state["positions"][side] = {
                        "size": Decimal(p.get("size", "0")),
                        "avg_price": Decimal(p.get("avgPrice", "0")),
                        "unrealisedPnl": current_unrealised_pnl,
                        "leverage": Decimal(p.get("leverage", "1")),
                        "liq_price": Decimal(p.get("liqPrice", "0")),
                    }
                    logger.debug(
                        f"WS Position Update: {side} Size={p.get('size')}, PnL={current_unrealised_pnl}"
                    )
        elif topic == "wallet":
            for w in msg["data"]:
                # Assuming single currency for now, e.g., USDT
                if w.get("coin") == "USDT":
                    ws_state["available_balance"] = Decimal(
                        w.get("availableBalance", "0")
                    )
                    ws_state["last_balance_update"] = time.time()
                    logger.debug(
                        f"WS Wallet Update: Available Balance={ws_state['available_balance']:.2f}"
                    )

    except (KeyError, ValueError, TypeError, DecimalException) as e:
        logger.error(
            f"Error processing private WS message: {type(e).__name__} - {e} | Message: {msg}"
        )
    except Exception as e:
        logger.error(
            f"Unexpected error in private WS handler: {type(e).__name__} - {e} | Message: {msg}"
        )


# -----------------------------
# Bybit Client Class
# -----------------------------


class BybitClient:
    MAX_RETRIES = MAX_RETRIES_API
    RETRY_DELAY = RETRY_DELAY_API

    def __init__(self, key: str, secret: str, testnet: bool):
        self.http = HTTP(testnet=testnet, api_key=key, api_secret=secret)
        self.ws_public = WebSocket(
            testnet=testnet,
            channel_type="linear",
            retries=self.MAX_RETRIES,
            ping_interval=20,
            ping_timeout=10,
        )
        self.ws_private = WebSocket(
            testnet=testnet,
            channel_type="private",
            api_key=key,
            api_secret=secret,
            retries=self.MAX_RETRIES,
            ping_interval=20,
            ping_timeout=10,
        )
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

    def start_websockets(self):
        """Start public and private WebSocket streams."""
        logger.info(f"{Fore.CYAN}Starting public orderbook stream for {SYMBOL}...{NC}")
        self.ws_public.orderbook_stream(
            symbol=SYMBOL, depth=1, callback=on_public_ws_message
        )
        logger.info(f"{Fore.CYAN}Starting private order and position streams...{NC}")
        self.ws_private.position_stream(on_private_ws_message)
        self.ws_private.order_stream(on_private_ws_message)
        self.ws_private.wallet_stream(on_private_ws_message)
        logger.info(f"{Fore.CYAN}WebSocket streams initiated.{NC}")

    def _on_ws_close(self, ws_type: str):
        """Callback when a WebSocket connection closes."""
        if ws_type == "public":
            self.is_public_ws_connected = False
            logger.warning(
                f"{Fore.YELLOW}Public WebSocket connection closed. Pybit will attempt reconnect.{NC}"
            )
        elif ws_type == "private":
            self.is_private_ws_connected = False
            logger.warning(
                f"{Fore.YELLOW}Private WebSocket connection closed. Pybit will attempt reconnect.{NC}"
            )

    def _on_ws_error(self, ws_type: str, error: Exception):
        """Callback for WebSocket errors."""
        logger.error(f"{Fore.RED}{ws_type.capitalize()} WebSocket error: {error}{NC}")

    async def _monitor_websockets(self, strategy_instance):
        """Periodically checks WS connection status."""
        while strategy_instance.running and not _SHUTDOWN_REQUESTED:
            if not self.is_public_ws_connected:
                logger.warning(
                    f"{Fore.YELLOW}Public WS connection currently disconnected. Awaiting pybit reconnect.{NC}"
                )
                send_toast("WS Public disconnected", "#FFA500", "white")

            if not self.is_private_ws_connected:
                logger.warning(
                    f"{Fore.YELLOW}Private WS connection currently disconnected. Awaiting pybit reconnect.{NC}"
                )
                send_toast("WS Private disconnected", "#FFA500", "white")

            await asyncio.sleep(WS_MONITOR_INTERVAL)

    async def _api(self, api_method, *args, **kwargs):
        """Generic retry wrapper for API calls with exponential backoff and error handling."""
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = api_method(*args, **kwargs)
                if response and response.get("retCode") == 0:
                    return response

                ret_code = response.get("retCode") if response else None
                ret_msg = (
                    response.get("retMsg", "No response or unknown error")
                    if response
                    else "No response"
                )
                error_msg = f"{Fore.YELLOW}API Call Failed (Attempt {attempt}/{self.MAX_RETRIES}, Code: {ret_code}): {ret_msg}{NC}"
                logger.warning(error_msg)

                if ret_code in [
                    10001,
                    10006,
                    30034,
                    30035,
                    10018,
                ]:  # 10018: order not found, retry if needed.
                    if attempt < self.MAX_RETRIES:
                        delay = self.RETRY_DELAY * (2 ** (attempt - 1)) + (
                            time.time() % 1
                        )
                        logger.warning(f"{Fore.YELLOW}Retrying in {delay:.1f}s...{NC}")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"{Fore.RED}API retries exhausted for {api_method.__name__}. Last error: {ret_msg}{NC}"
                        )
                        return None
                elif ret_code in [10007, 10002]:
                    logger.error(
                        f"{Fore.RED}Non-retryable API error: {ret_msg}. Action required.{NC}"
                    )
                    return None
                else:
                    logger.error(
                        f"{Fore.RED}Unhandled API error code {ret_code}: {ret_msg}. Stopping retries for this specific error.{NC}"
                    )
                    return None
            except Exception as e:
                error_msg = f"{Fore.RED}Exception during API call (Attempt {attempt}/{self.MAX_RETRIES}): {type(e).__name__} - {e}{NC}"
                logger.error(error_msg, exc_info=True)
                if attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAY * (2 ** (attempt - 1)) + (time.time() % 1)
                    logger.warning(f"{Fore.YELLOW}Retrying in {delay:.1f}s...{NC}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"{Fore.RED}API call failed after all retries: {type(e).__name__} - {e}{NC}"
                    )
                    return None
        return None

    async def get_symbol_info(self) -> bool:
        """Fetch symbol precision details, including min order value and quantity."""
        response = await self._api(
            self.http.get_instruments_info, category=CATEGORY, symbol=SYMBOL
        )
        if response and response.get("retCode") == 0:
            instruments = response.get("result", {}).get("list")
            if instruments:
                instrument_info = instruments[0]
                price_filter = instrument_info.get("priceFilter", {})
                lot_size_filter = instrument_info.get("lotSizeFilter", {})
                symbol_info["price_precision"] = Decimal(
                    price_filter.get("tickSize", "0.0001")
                )
                symbol_info["qty_precision"] = Decimal(
                    lot_size_filter.get("qtyStep", "0.001")
                )
                symbol_info["min_price"] = Decimal(price_filter.get("minPrice", "0"))
                symbol_info["min_qty"] = Decimal(lot_size_filter.get("minQty", "0"))
                symbol_info["min_order_value"] = Decimal(
                    lot_size_filter.get("minOrderAmt", "10.0")
                )
                logger.info(
                    f"{Fore.CYAN}Symbol Info: {SYMBOL} | Price Precision: {symbol_info['price_precision']} | Qty Precision: {symbol_info['qty_precision']}{NC}"
                )
                return True
        logger.error(f"{Fore.RED}Failed to fetch symbol info for {SYMBOL}.{NC}")
        return False

    async def get_wallet_balance(self) -> bool:
        """Fetch and update wallet balance from REST API."""
        response = await self._api(self.http.get_wallet_balance, accountType="UNIFIED")
        if response and response.get("retCode") == 0:
            for balance in response.get("result", {}).get("list", []):
                if balance.get("coin") == "USDT":
                    ws_state["available_balance"] = Decimal(
                        balance.get("availableToWithdraw", "0")
                    )
                    ws_state["last_balance_update"] = time.time()
                    logger.info(
                        f"{Fore.CYAN}Updated wallet balance: {ws_state['available_balance']:.2f} USDT{NC}"
                    )
                    return True
        logger.error(f"{Fore.RED}Failed to fetch wallet balance.{NC}")
        return False

    async def get_open_orders(self):
        """Fetches open orders from REST API."""
        response = await self._api(
            self.http.get_open_orders, category=CATEGORY, symbol=SYMBOL, limit=50
        )
        if response and response.get("retCode") == 0:
            open_orders_list = response.get("result", {}).get("list", [])
            ws_state["open_orders"] = {
                o.get("orderId"): {
                    "client_order_id": o.get("orderLinkId", "N/A"),
                    "symbol": o.get("symbol"),
                    "side": o.get("side"),
                    "price": Decimal(o.get("price", "0")),
                    "qty": Decimal(o.get("qty", "0")),
                    "status": o.get("orderStatus"),
                    "timestamp": float(o.get("createdTime", 0)) / 1000,
                }
                for o in open_orders_list
            }
            logger.debug(f"Fetched {len(open_orders_list)} open orders from REST.")
            return True
        return False

    async def get_my_positions(self):
        """Fetches positions from REST API."""
        response = await self._api(
            self.http.get_positions, category=CATEGORY, symbol=SYMBOL
        )
        if response and response.get("retCode") == 0:
            positions_list = response.get("result", {}).get("list", [])
            ws_state["positions"] = {}
            for p in positions_list:
                if p.get("positionIdx") != 2:
                    side = "Long" if p.get("side") == "Buy" else "Short"
                    ws_state["positions"][side] = {
                        "size": Decimal(p.get("size", "0")),
                        "avg_price": Decimal(p.get("avgPrice", "0")),
                        "unrealisedPnl": Decimal(p.get("unrealisedPnl", "0")),
                        "leverage": Decimal(p.get("leverage", "1")),
                        "liq_price": Decimal(p.get("liqPrice", "0")),
                    }
            logger.debug(f"Fetched {len(positions_list)} positions from REST.")
            return True
        return False

    async def place_order(
        self, side: str, order_type: str, qty: Decimal, price: Decimal | None = None
    ):
        """Places a new order."""
        client_order_id = f"mmxcel-{uuid.uuid4()}"
        order_params = {
            "category": CATEGORY,
            "symbol": SYMBOL,
            "side": side,
            "orderType": order_type,
            "qty": str(qty.quantize(symbol_info["qty_precision"], rounding=ROUND_DOWN)),
            "timeInForce": "GTC",
            "orderLinkId": client_order_id,
            "isLeverage": 1,
        }
        if order_type == "Limit":
            order_params["price"] = str(price.quantize(symbol_info["price_precision"]))

        # Check if the order value meets the minimum requirement
        if order_type == "Limit":
            order_value = qty * price
            if order_value < symbol_info["min_order_value"]:
                logger.warning(
                    f"{Fore.YELLOW}Skipping order due to minimum value constraint. Value: {order_value:.2f}, Min: {symbol_info['min_order_value']}{NC}"
                )
                return None

        response = await self._api(self.http.place_order, **order_params)
        if response and response.get("retCode") == 0:
            session_stats["orders_placed"] += 1
            logger.info(
                f"{Fore.GREEN}Placed {order_type} {side} order: {qty} @ {price}{NC}"
            )
            return response.get("result", {})
        return None

    async def cancel_order(self, order_id: str):
        """Cancels a specific order."""
        response = await self._api(
            self.http.cancel_order, category=CATEGORY, symbol=SYMBOL, orderId=order_id
        )
        if response and response.get("retCode") == 0:
            logger.info(f"{Fore.GREEN}Canceled order {order_id}{NC}")
            return True
        return False

    async def cancel_all_orders(self):
        """Cancels all open orders for the symbol."""
        response = await self._api(
            self.http.cancel_all_orders, category=CATEGORY, symbol=SYMBOL
        )
        if response and response.get("retCode") == 0:
            logger.info(f"{Fore.GREEN}Canceled all open orders.{NC}")
            return True
        return False

    async def set_leverage(self, leverage: int = 1):
        """Sets the leverage for the symbol."""
        response = await self._api(
            self.http.set_leverage,
            category=CATEGORY,
            symbol=SYMBOL,
            buyLeverage=str(leverage),
            sellLeverage=str(leverage),
        )
        if response and response.get("retCode") == 0:
            logger.info(f"{Fore.GREEN}Leverage set to {leverage}x for {SYMBOL}.{NC}")
            return True
        logger.error(
            f"{Fore.RED}Failed to set leverage. Error: {response.get('retMsg') if response else 'Unknown'}{NC}"
        )
        return False


# -----------------------------
# Core Strategy Logic
# -----------------------------


class MakiwiStrategy:
    def __init__(self, client: BybitClient):
        self.client = client
        self.running = False
        self.last_order_refresh = 0
        self.last_dashboard_update = 0
        self.is_rebalancing = False

    async def startup_sequence(self):
        """Runs initial setup tasks before starting the main loop."""
        print_neon_header("MMXCEL BOT INITIALIZING", color=UNDERLINE)
        logger.info(f"{Fore.MAGENTA}Starting MMXCEL Bot v3.0...{NC}")
        if not API_KEY or not API_SECRET:
            logger.error(
                f"{RED}API_KEY or API_SECRET not found in .env file. Exiting.{NC}"
            )
            sys.exit(1)

        # Initiate WebSocket connections and wait for them to establish and receive data.
        logger.info("Initiating WebSocket connections and waiting for data...")
        self.client.start_websockets()  # Start the WebSocket connections

        start_time = time.time()
        while not (
            self.client.is_public_ws_connected
            and self.client.is_private_ws_connected
            and ws_state["mid_price"] > Decimal("0")
        ):
            await asyncio.sleep(0.5)
            if time.time() - start_time > 20:  # 20-second timeout
                logger.error(
                    f"{RED}WebSocket connection timeout or no market data received. Public: {self.client.is_public_ws_connected}, Private: {self.client.is_private_ws_connected}, Mid Price: {ws_state['mid_price']}. Exiting.{NC}"
                )
                sys.exit(1)
        logger.info(
            f"{Fore.GREEN}WebSockets connected and market data received successfully.{NC}"
        )

        # Fetch initial market data and wallet balance
        if not await self.client.get_symbol_info():
            sys.exit(1)
        if not await self.client.get_wallet_balance():
            sys.exit(1)
        # Set leverage to 1x by default to simplify initial hedging.
        # This can be made configurable later if needed.
        await self.client.set_leverage(1)

        # Clear any existing orders to start fresh
        await self.client.cancel_all_orders()
        await self.client.get_open_orders()
        await self.client.get_my_positions()

        # Final checks
        if not ws_state["available_balance"]:
            logger.error(
                f"{RED}Available balance is zero. Cannot start trading. Exiting.{NC}"
            )
            sys.exit(1)
        if not ws_state["mid_price"]:
            logger.error(f"{RED}No initial mid-price from WebSocket. Exiting.{NC}")
            sys.exit(1)

        set_bot_state("RUNNING")
        self.running = True
        logger.info(f"{Fore.GREEN}Startup successful. Bot is now active.{NC}")

    async def dashboard_updater(self):
        """Updates the console dashboard periodically."""
        while self.running and not _SHUTDOWN_REQUESTED:
            if time.time() - self.last_dashboard_update > DASHBOARD_REFRESH_INTERVAL:
                clear_screen()
                print_neon_header(
                    "MMXCEL Bybit Market-Maker Dashboard", color=UNDERLINE
                )
                print_neon_separator()
                print(
                    format_metric(
                        "Status",
                        BOT_STATE,
                        label_color=WHITE,
                        value_color=GREEN if BOT_STATE == "RUNNING" else YELLOW,
                    )
                )
                print(
                    format_metric("Symbol", SYMBOL, label_color=WHITE, value_color=CYAN)
                )
                print(
                    format_metric(
                        "Mid Price",
                        ws_state["mid_price"],
                        label_color=WHITE,
                        value_precision=_calculate_decimal_precision(
                            symbol_info["price_precision"]
                        ),
                    )
                )
                print(
                    format_metric(
                        "Best Bid",
                        ws_state["best_bid"],
                        label_color=WHITE,
                        value_precision=_calculate_decimal_precision(
                            symbol_info["price_precision"]
                        ),
                    )
                )
                print(
                    format_metric(
                        "Best Ask",
                        ws_state["best_ask"],
                        label_color=WHITE,
                        value_precision=_calculate_decimal_precision(
                            symbol_info["price_precision"]
                        ),
                    )
                )
                print_neon_separator()
                print(
                    format_metric(
                        "Open Orders",
                        len(ws_state["open_orders"]),
                        label_color=WHITE,
                        value_color=CYAN,
                    )
                )

                long_pos = ws_state["positions"].get(
                    "Long", {"size": Decimal("0"), "unrealisedPnl": Decimal("0")}
                )
                short_pos = ws_state["positions"].get(
                    "Short", {"size": Decimal("0"), "unrealisedPnl": Decimal("0")}
                )

                print(
                    format_metric(
                        "Long Position",
                        long_pos["size"],
                        label_color=WHITE,
                        unit=f" {SYMBOL.split('USDT')[0]}",
                        value_precision=_calculate_decimal_precision(
                            symbol_info["qty_precision"]
                        ),
                    )
                )
                print(
                    format_metric(
                        "Short Position",
                        short_pos["size"],
                        label_color=WHITE,
                        unit=f" {SYMBOL.split('USDT')[0]}",
                        value_precision=_calculate_decimal_precision(
                            symbol_info["qty_precision"]
                        ),
                    )
                )

                total_unrealized_pnl = (
                    long_pos["unrealisedPnl"] + short_pos["unrealisedPnl"]
                )
                print(
                    format_metric(
                        "Unrealized PnL",
                        total_unrealized_pnl,
                        label_color=WHITE,
                        value_precision=2,
                        is_pnl=True,
                    )
                )
                print_neon_separator()

                # Dynamic order status section
                if ws_state["open_orders"]:
                    print_neon_header("Open Orders Status", color=BOLD + WHITE)
                    for oid, order in ws_state["open_orders"].items():
                        age = time.time() - order["timestamp"]
                        age_color = RED if age > ORDER_LIFESPAN_SECONDS else GREEN
                        print(
                            f"{Fore.WHITE}  - {order['side']:<5} {order['qty']:.{_calculate_decimal_precision(symbol_info['qty_precision'])}f} @ {order['price']:.{_calculate_decimal_precision(symbol_info['price_precision'])}f} {age_color}({age:.1f}s ago){NC}"
                        )
                    print_neon_separator()

                print_neon_header("Session Statistics", color=BOLD + WHITE)
                uptime = time.time() - session_stats["start_time"]
                print(
                    format_metric(
                        "Uptime",
                        f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s",
                        label_color=WHITE,
                        value_color=CYAN,
                    )
                )
                print(
                    format_metric(
                        "Total Orders Placed",
                        session_stats["orders_placed"],
                        label_color=WHITE,
                        value_color=CYAN,
                    )
                )
                print(
                    format_metric(
                        "Total Orders Filled",
                        session_stats["orders_filled"],
                        label_color=WHITE,
                        value_color=CYAN,
                    )
                )
                print(
                    format_metric(
                        "Total Realized PnL",
                        session_stats["total_pnl"],
                        label_color=WHITE,
                        value_precision=2,
                        is_pnl=True,
                    )
                )
                print_neon_separator(char="═")

                self.last_dashboard_update = time.time()

            # Non-blocking sleep
            await asyncio.sleep(0.1)

    async def main_loop(self):
        """Main loop for the bot's trading logic."""
        while self.running and not _SHUTDOWN_REQUESTED:
            try:
                # 1. Stale Data Check
                if time.time() - ws_state["last_update_time"] > MAX_DATA_AGE_SECONDS:
                    set_bot_state("STALE DATA")
                    logger.warning(
                        f"{Fore.YELLOW}Market data is stale! Age: {time.time() - ws_state['last_update_time']:.1f}s. Cancelling all orders.{NC}"
                    )
                    await self.client.cancel_all_orders()
                    await asyncio.sleep(1)  # Wait a bit for WS to catch up
                    continue
                set_bot_state("RUNNING")

                mid_price = ws_state["mid_price"]
                if mid_price == Decimal("0"):
                    logger.warning(
                        f"{Fore.YELLOW}Mid price is zero, waiting for WebSocket data.{NC}"
                    )
                    await asyncio.sleep(1)
                    continue

                # 2. Rebalance check
                long_size = (
                    ws_state["positions"].get("Long", {}).get("size", Decimal("0"))
                )
                short_size = (
                    ws_state["positions"].get("Short", {}).get("size", Decimal("0"))
                )
                position_imbalance = abs(long_size - short_size)

                if (
                    position_imbalance >= REBALANCE_THRESHOLD_QTY
                    and not self.is_rebalancing
                ):
                    self.is_rebalancing = True
                    set_bot_state("REBALANCING")
                    logger.warning(
                        f"{Fore.MAGENTA}Position imbalance detected ({position_imbalance}). Initiating rebalance.{NC}"
                    )
                    session_stats["rebalances_count"] += 1

                    # Cancel all orders before rebalancing to avoid conflicts
                    await self.client.cancel_all_orders()
                    await asyncio.sleep(1)  # Give time for cancellations

                    imbalance_side = "Buy" if long_size < short_size else "Sell"
                    qty_to_rebalance = position_imbalance
                    rebalance_price = None

                    if REBALANCE_ORDER_TYPE == "Limit":
                        rebalance_price = mid_price * (
                            Decimal("1")
                            + (
                                REBALANCE_PRICE_OFFSET_PERCENTAGE
                                * (
                                    Decimal("1")
                                    if imbalance_side == "Buy"
                                    else Decimal("-1")
                                )
                            )
                        )
                        await self.client.place_order(
                            imbalance_side, "Limit", qty_to_rebalance, rebalance_price
                        )
                    else:  # Market order
                        await self.client.place_order(
                            imbalance_side, "Market", qty_to_rebalance
                        )

                    # Wait for a few seconds for the rebalance order to process
                    await asyncio.sleep(ORDER_REFRESH_INTERVAL)
                    self.is_rebalancing = False
                    set_bot_state("RUNNING")

                # 3. Order Placement & Management
                open_orders = ws_state["open_orders"]

                # Check for and cancel old orders
                orders_to_cancel = [
                    oid
                    for oid, order in open_orders.items()
                    if time.time() - order["timestamp"] > ORDER_LIFESPAN_SECONDS
                ]
                if orders_to_cancel:
                    logger.info(
                        f"{Fore.YELLOW}Cancelling {len(orders_to_cancel)} stale orders.{NC}"
                    )
                    for oid in orders_to_cancel:
                        await self.client.cancel_order(oid)

                # Place new orders if needed
                if len(open_orders) < MAX_OPEN_ORDERS and not self.is_rebalancing:
                    num_orders_to_place = MAX_OPEN_ORDERS - len(open_orders)
                    logger.debug(f"Need to place {num_orders_to_place} new orders.")

                    # Place new buy and sell orders symmetrically
                    if num_orders_to_place >= 2:
                        buy_price = mid_price * (Decimal("1") - SPREAD_PERCENTAGE)
                        sell_price = mid_price * (Decimal("1") + SPREAD_PERCENTAGE)

                        if "Buy" not in [o["side"] for o in open_orders.values()]:
                            await self.client.place_order(
                                "Buy", "Limit", QUANTITY, buy_price
                            )

                        if "Sell" not in [o["side"] for o in open_orders.values()]:
                            await self.client.place_order(
                                "Sell", "Limit", QUANTITY, sell_price
                            )

                    # Wait for orders to be processed
                    await asyncio.sleep(ORDER_REFRESH_INTERVAL)
                    await self.client.get_open_orders()  # Refresh open orders list

            except Exception as e:
                logger.error(
                    f"{Fore.RED}Exception in main loop: {type(e).__name__} - {e}{NC}",
                    exc_info=True,
                )
                set_bot_state("ERROR")
                # Add a longer sleep here to prevent rapid error looping
                await asyncio.sleep(5)

            await asyncio.sleep(0.5)  # Main loop sleep to prevent high CPU usage


async def shutdown(loop, signame):
    """Gracefully shuts down the bot."""
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = True
    print_neon_header(
        f"Shutdown signal received ({signame}). Starting graceful shutdown...",
        color=RED,
    )

    # Cancel all pending tasks except the current one
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()

    # Wait for tasks to finish
    await asyncio.gather(*tasks, return_exceptions=True)

    # Perform final cleanup actions
    await client.cancel_all_orders()  # FIX: Await the coroutine
    logger.info(f"{Fore.MAGENTA}All open orders cancelled.{NC}")

    # Wait for the client to close its connections
    if client.is_public_ws_connected:
        client.ws_public.exit()
    if client.is_private_ws_connected:
        client.ws_private.exit()

    logger.info(f"{Fore.GREEN}MMXCEL bot has shut down gracefully.{NC}")
    loop.stop()


if __name__ == "__main__":
    _HAS_TERMUX_TOAST_CMD = check_termux_toast()
    client = BybitClient(API_KEY, API_SECRET, USE_TESTNET)
    strategy = MakiwiStrategy(client)

    loop = asyncio.new_event_loop()  # FIX: Use new_event_loop
    asyncio.set_event_loop(loop)

    for signame in ("SIGINT", "SIGTERM"):
        loop.add_signal_handler(
            getattr(signal, signame),
            lambda: asyncio.ensure_future(shutdown(loop, signame)),
        )

    try:
        # Run startup sequence first
        loop.run_until_complete(strategy.startup_sequence())

        # If startup is successful, run the main tasks
        loop.run_until_complete(
            asyncio.gather(
                client._monitor_websockets(strategy),
                strategy.dashboard_updater(),
                strategy.main_loop(),
            )
        )
    except (KeyboardInterrupt, SystemExit):
        print("\nKeyboard interrupt received, initiating shutdown...")
        loop.run_until_complete(shutdown(loop, "SIGINT"))
    finally:
        loop.close()
