#!/usr/bin/env python3
"""
MMXCEL v3.1 – Enhanced Bybit Hedge-Mode Market-Making Bot
Improved version with better error handling, performance optimizations, and new features
Author: Enhanced by AI Assistant, Original by Pyrmethus
"""

import asyncio
import json
import logging
import logging.handlers
import os
import select
import signal
import sys
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_UP, Decimal, DecimalException, getcontext
from typing import Any

from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket

# Initialize colorama for cross-platform color support
init(autoreset=True)

# High-precision decimals for financial calculations
getcontext().prec = 18  # Increased precision for better accuracy

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

@dataclass
class BotConfig:
    """Configuration class for better organization and validation"""
    SYMBOL: str = "BTCUSDT"
    CATEGORY: str = "linear"
    QUANTITY: Decimal = Decimal("0.001")
    SPREAD_PERCENTAGE: Decimal = Decimal("0.0005")
    MAX_OPEN_ORDERS: int = 2
    ORDER_LIFESPAN_SECONDS: int = 30
    REBALANCE_THRESHOLD_QTY: Decimal = Decimal("0.0001")
    PROFIT_PERCENTAGE: Decimal = Decimal("0.001")
    STOP_LOSS_PERCENTAGE: Decimal = Decimal("0.005")
    PRICE_THRESHOLD: Decimal = Decimal("0.0002")
    USE_TESTNET: bool = True
    ORDER_REFRESH_INTERVAL: int = 5
    BALANCE_REFRESH_INTERVAL: int = 30
    CAPITAL_ALLOCATION_PERCENTAGE: Decimal = Decimal("0.05")
    ABNORMAL_SPREAD_THRESHOLD: Decimal = Decimal("0.015")
    REBALANCE_ORDER_TYPE: str = "Market"
    REBALANCE_PRICE_OFFSET_PERCENTAGE: Decimal = Decimal("0")

    # New enhanced parameters
    MAX_POSITION_SIZE: Decimal = Decimal("0.1")  # Maximum position size as % of balance
    VOLATILITY_ADJUSTMENT: bool = True  # Enable dynamic spread adjustment
    EMERGENCY_STOP_LOSS: Decimal = Decimal("0.02")  # Emergency stop at 2% loss

    def __post_init__(self):
        """Validate configuration after initialization"""
        if self.SPREAD_PERCENTAGE <= 0:
            raise ValueError("SPREAD_PERCENTAGE must be positive")
        if self.MAX_OPEN_ORDERS <= 0:
            raise ValueError("MAX_OPEN_ORDERS must be positive")
        if not self.SYMBOL:
            raise ValueError("SYMBOL cannot be empty")

def load_config() -> BotConfig:
    """Load and validate configuration from file"""
    try:
        with open("config.json") as f:
            config_data = json.load(f)

        # Convert string decimals to Decimal objects
        decimal_fields = [
            'QUANTITY', 'SPREAD_PERCENTAGE', 'REBALANCE_THRESHOLD_QTY',
            'PROFIT_PERCENTAGE', 'STOP_LOSS_PERCENTAGE', 'PRICE_THRESHOLD',
            'CAPITAL_ALLOCATION_PERCENTAGE', 'ABNORMAL_SPREAD_THRESHOLD',
            'REBALANCE_PRICE_OFFSET_PERCENTAGE', 'MAX_POSITION_SIZE',
            'EMERGENCY_STOP_LOSS'
        ]

        for field_name in decimal_fields:
            if field_name in config_data:
                config_data[field_name] = Decimal(str(config_data[field_name]))

        return BotConfig(**config_data)

    except FileNotFoundError:
        print(f"{RED}config.json not found. Creating default configuration...{NC}")
        config = BotConfig()
        save_default_config(config)
        return config
    except json.JSONDecodeError as e:
        print(f"{RED}config.json is malformed JSON: {e}{NC}")
        sys.exit(1)
    except Exception as e:
        print(f"{RED}Error loading configuration: {e}{NC}")
        sys.exit(1)

def save_default_config(config: BotConfig):
    """Save default configuration to file"""
    config_dict = {}
    for key, value in config.__dict__.items():
        if isinstance(value, Decimal):
            config_dict[key] = str(value)
        else:
            config_dict[key] = value

    with open("config.json", "w") as f:
        json.dump(config_dict, f, indent=2)
    print(f"{GREEN}Default config.json created. Please review and modify as needed.{NC}")

# Load configuration
config = load_config()

# Constants for data freshness and retry delays
MAX_DATA_AGE_SECONDS = 10
MAX_RETRIES_API = 5
RETRY_DELAY_API = 2
WS_MONITOR_INTERVAL = 10
PNL_MONITOR_INTERVAL = 5
DASHBOARD_REFRESH_INTERVAL = 1

@dataclass
class SymbolInfo:
    """Symbol information with better type safety"""
    price_precision: Decimal = Decimal("0.0001")
    qty_precision: Decimal = Decimal("0.001")
    min_order_value: Decimal = Decimal("10.0")
    min_price: Decimal = Decimal("0")
    min_qty: Decimal = Decimal("0")
    max_qty: Decimal = Decimal("1000000")  # Add max quantity limit

@dataclass
class MarketState:
    """Market state with better organization"""
    mid_price: Decimal = Decimal("0")
    best_bid: Decimal = Decimal("0")
    best_ask: Decimal = Decimal("0")
    open_orders: dict[str, dict] = field(default_factory=dict)
    positions: dict[str, dict] = field(default_factory=dict)
    last_update_time: float = 0
    last_balance_update: float = 0
    available_balance: Decimal = Decimal("0")

    def is_data_fresh(self, max_age: float = MAX_DATA_AGE_SECONDS) -> bool:
        """Check if market data is fresh"""
        return (time.time() - self.last_update_time) <= max_age and self.mid_price > 0

@dataclass
class SessionStats:
    """Session statistics tracking"""
    start_time: float = field(default_factory=time.time)
    orders_placed: int = 0
    orders_filled: int = 0
    orders_cancelled: int = 0
    rebalances_count: int = 0
    circuit_breaker_activations: int = 0
    total_pnl: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    peak_balance: Decimal = Decimal("0")

    def update_pnl(self, current_pnl: Decimal):
        """Update PnL tracking with drawdown calculation"""
        self.total_pnl = current_pnl
        if current_pnl > self.peak_balance:
            self.peak_balance = current_pnl

        if self.peak_balance > 0:
            drawdown = (self.peak_balance - current_pnl) / self.peak_balance
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown

# Global instances
symbol_info = SymbolInfo()
market_state = MarketState()
session_stats = SessionStats()

# Global state for bot operations
BOT_STATE = "INITIALIZING"
_HAS_TERMUX_TOAST_CMD = False
_SHUTDOWN_REQUESTED = False

# Configure enhanced logging
LOG_FILE = "mmxcel.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=10  # 10MB files, keep 10
        ),
    ],
)
logger = logging.getLogger("MMXCEL")

# Performance monitoring
class PerformanceMonitor:
    """Monitor bot performance metrics"""

    def __init__(self):
        self.api_call_times = []
        self.order_latencies = []
        self.last_performance_log = time.time()

    def record_api_call(self, duration: float):
        """Record API call duration"""
        self.api_call_times.append(duration)
        if len(self.api_call_times) > 100:  # Keep last 100 calls
            self.api_call_times.pop(0)

    def record_order_latency(self, duration: float):
        """Record order placement latency"""
        self.order_latencies.append(duration)
        if len(self.order_latencies) > 50:  # Keep last 50 orders
            self.order_latencies.pop(0)

    def get_avg_api_time(self) -> float:
        """Get average API call time"""
        return sum(self.api_call_times) / len(self.api_call_times) if self.api_call_times else 0

    def get_avg_order_latency(self) -> float:
        """Get average order latency"""
        return sum(self.order_latencies) / len(self.order_latencies) if self.order_latencies else 0

    def should_log_performance(self) -> bool:
        """Check if it's time to log performance metrics"""
        if time.time() - self.last_performance_log > 300:  # Every 5 minutes
            self.last_performance_log = time.time()
            return True
        return False

performance_monitor = PerformanceMonitor()

# Helper Functions
def set_bot_state(state: str):
    """Sets the global bot state and logs the change."""
    global BOT_STATE
    if state != BOT_STATE:
        logger.info(f"{Fore.CYAN}Bot State Change: {BOT_STATE} -> {state}{NC}")
        BOT_STATE = state

def calculate_decimal_precision(d: Decimal) -> int:
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

    if isinstance(value, Decimal):
        current_precision = value_precision if value_precision is not None else calculate_decimal_precision(value)
        if is_pnl:
            actual_value_color = GREEN if value >= Decimal("0") else RED
        formatted_value = f"{actual_value_color}{value:,.{current_precision}f}{unit}{NC}"
    elif isinstance(value, (int, float)):
        if is_pnl:
            actual_value_color = GREEN if value >= 0 else RED
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

# WebSocket Callbacks
def on_public_ws_message(msg: dict[str, Any]) -> None:
    """Handle public WebSocket messages (orderbook)."""
    try:
        topic = msg.get("topic")
        if topic and topic.startswith("orderbook.1."):
            data = msg.get("data")
            if data and data.get("b") and data.get("a"):
                bid_info = data["b"][0]
                ask_info = data["a"][0]

                market_state.best_bid = Decimal(bid_info[0])
                market_state.best_ask = Decimal(ask_info[0])

                if market_state.best_bid > 0 and market_state.best_ask > 0:
                    market_state.mid_price = (market_state.best_bid + market_state.best_ask) / Decimal("2")
                else:
                    market_state.mid_price = Decimal("0")

                market_state.last_update_time = time.time()
                logger.debug(f"WS Orderbook: Bid={market_state.best_bid:.4f}, Ask={market_state.best_ask:.4f}, Mid={market_state.mid_price:.4f}")

    except (KeyError, IndexError, ValueError, TypeError, DecimalException) as e:
        logger.error(f"Error processing public WS message: {type(e).__name__} - {e}")
    except Exception as e:
        logger.error(f"Unexpected error in public WS handler: {type(e).__name__} - {e}")

def on_private_ws_message(msg: dict[str, Any]) -> None:
    """Handle private WebSocket messages (orders, positions)."""
    try:
        topic = msg.get("topic")

        if topic == "order":
            for order_data in msg["data"]:
                order_id = order_data.get("orderId")
                if not order_id:
                    continue

                order_status = order_data.get("orderStatus")
                if order_status in ("Filled", "Canceled", "Deactivated"):
                    if order_id in market_state.open_orders:
                        order_details = market_state.open_orders.pop(order_id, None)
                        if order_details and order_status == "Filled":
                            session_stats.orders_filled += 1
                            filled_price = Decimal(order_data.get('avgPrice', order_data.get('price', '0')))
                            filled_qty = Decimal(order_data.get('qty', '0'))
                            side = order_data.get('side', 'N/A')

                            logger.info(f"Order filled: {side} {filled_qty} @ {filled_price:.4f}")
                            send_toast(f"Order filled: {side} {filled_qty}", "green", "white")
                        elif order_status in ("Canceled", "Deactivated"):
                            session_stats.orders_cancelled += 1
                else:
                    # Update open orders
                    market_state.open_orders[order_id] = {
                        "client_order_id": order_data.get("orderLinkId", "N/A"),
                        "symbol": order_data.get("symbol"),
                        "side": order_data.get("side"),
                        "price": Decimal(order_data.get("price", "0")),
                        "qty": Decimal(order_data.get("qty", "0")),
                        "status": order_status,
                        "timestamp": float(order_data.get("createdTime", 0)) / 1000,
                    }

        elif topic == "position":
            for pos_data in msg["data"]:
                if pos_data.get("symbol") == config.SYMBOL:
                    side = "Long" if pos_data.get("side") == "Buy" else "Short"
                    unrealised_pnl = Decimal(pos_data.get("unrealisedPnl", "0"))

                    market_state.positions[side] = {
                        "size": Decimal(pos_data.get("size", "0")),
                        "avg_price": Decimal(pos_data.get("avgPrice", "0")),
                        "unrealisedPnl": unrealised_pnl,
                        "leverage": Decimal(pos_data.get("leverage", "1")),
                        "liq_price": Decimal(pos_data.get("liqPrice", "0")),
                    }

                    # Update session PnL tracking
                    total_pnl = sum(pos.get("unrealisedPnl", Decimal("0"))
                                  for pos in market_state.positions.values())
                    session_stats.update_pnl(total_pnl)

        elif topic == "wallet":
            for wallet_data in msg["data"]:
                if wallet_data.get("coin") == 'USDT':
                    market_state.available_balance = Decimal(wallet_data.get('availableBalance', '0'))
                    market_state.last_balance_update = time.time()

    except (KeyError, ValueError, TypeError, DecimalException) as e:
        logger.error(f"Error processing private WS message: {type(e).__name__} - {e}")
    except Exception as e:
        logger.error(f"Unexpected error in private WS handler: {type(e).__name__} - {e}")

# Enhanced Bybit Client
class EnhancedBybitClient:
    """Enhanced Bybit client with better error handling and performance monitoring"""

    def __init__(self, key: str, secret: str, testnet: bool):
        self.http = HTTP(testnet=testnet, api_key=key, api_secret=secret)
        self.ws_public = WebSocket(testnet=testnet, channel_type="linear", retries=MAX_RETRIES_API)
        self.ws_private = WebSocket(testnet=testnet, channel_type="private", api_key=key, api_secret=secret, retries=MAX_RETRIES_API)

        self.is_public_ws_connected = False
        self.is_private_ws_connected = False
        self.connection_retry_count = 0
        self.max_connection_retries = 10

        # Setup WebSocket callbacks
        self._setup_websocket_callbacks()

    def _setup_websocket_callbacks(self):
        """Setup WebSocket event callbacks"""
        self.ws_public.on_open = lambda: self._on_ws_open("public")
        self.ws_private.on_open = lambda: self._on_ws_open("private")
        self.ws_public.on_close = lambda: self._on_ws_close("public")
        self.ws_private.on_close = lambda: self._on_ws_close("private")
        self.ws_public.on_error = lambda err: self._on_ws_error("public", err)
        self.ws_private.on_error = lambda err: self._on_ws_error("private", err)

    def _on_ws_open(self, ws_type: str):
        """Callback when WebSocket connection opens"""
        if ws_type == "public":
            self.is_public_ws_connected = True
            logger.info(f"{GREEN}Public WebSocket connected{NC}")
        elif ws_type == "private":
            self.is_private_ws_connected = True
            logger.info(f"{GREEN}Private WebSocket connected{NC}")

        self.connection_retry_count = 0  # Reset retry count on successful connection

    def _on_ws_close(self, ws_type: str):
        """Callback when WebSocket connection closes"""
        if ws_type == "public":
            self.is_public_ws_connected = False
            logger.warning(f"{YELLOW}Public WebSocket disconnected{NC}")
        elif ws_type == "private":
            self.is_private_ws_connected = False
            logger.warning(f"{YELLOW}Private WebSocket disconnected{NC}")

    def _on_ws_error(self, ws_type: str, error: Exception):
        """Callback for WebSocket errors"""
        logger.error(f"{RED}{ws_type.capitalize()} WebSocket error: {error}{NC}")
        self.connection_retry_count += 1

        if self.connection_retry_count > self.max_connection_retries:
            logger.critical(f"{RED}Max WebSocket connection retries exceeded. Manual intervention required.{NC}")
            send_toast("WebSocket connection failed!", "red", "white")

    @asynccontextmanager
    async def api_call_context(self, method_name: str):
        """Context manager for API calls with performance monitoring"""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            performance_monitor.record_api_call(duration)

            if performance_monitor.should_log_performance():
                avg_time = performance_monitor.get_avg_api_time()
                logger.info(f"API Performance - Avg call time: {avg_time:.3f}s")

    async def api_call_with_retry(self, api_method, *args, **kwargs):
        """Enhanced API call wrapper with retry logic and monitoring"""
        async with self.api_call_context(api_method.__name__):
            for attempt in range(1, MAX_RETRIES_API + 1):
                try:
                    response = api_method(*args, **kwargs)

                    if response and response.get("retCode") == 0:
                        return response

                    ret_code = response.get('retCode') if response else None
                    ret_msg = response.get('retMsg', 'Unknown error') if response else 'No response'

                    logger.warning(f"API call failed (attempt {attempt}/{MAX_RETRIES_API}): {ret_msg}")

                    # Handle specific error codes
                    if ret_code in [10001, 10006, 30034, 30035, 10018]:  # Retryable errors
                        if attempt < MAX_RETRIES_API:
                            delay = RETRY_DELAY_API * (2 ** (attempt - 1))
                            await asyncio.sleep(delay)
                            continue
                    elif ret_code in [10007, 10002]:  # Non-retryable errors
                        logger.error(f"Non-retryable API error: {ret_msg}")
                        return None
                    else:
                        logger.error(f"Unhandled API error {ret_code}: {ret_msg}")
                        return None

                except Exception as e:
                    logger.error(f"API call exception (attempt {attempt}): {e}")
                    if attempt < MAX_RETRIES_API:
                        delay = RETRY_DELAY_API * (2 ** (attempt - 1))
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"API call failed after all retries: {e}")
                        return None

            return None

    async def get_symbol_info(self) -> bool:
        """Fetch symbol information with enhanced error handling"""
        response = await self.api_call_with_retry(
            self.http.get_instruments_info,
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )

        if response and response.get('retCode') == 0:
            instruments = response.get('result', {}).get('list')
            if instruments:
                instrument = instruments[0]
                price_filter = instrument.get('priceFilter', {})
                lot_size_filter = instrument.get('lotSizeFilter', {})

                symbol_info.price_precision = Decimal(price_filter.get('tickSize', "0.0001"))
                symbol_info.qty_precision = Decimal(lot_size_filter.get('qtyStep', "0.001"))
                symbol_info.min_price = Decimal(price_filter.get('minPrice', "0"))
                symbol_info.min_qty = Decimal(lot_size_filter.get('minQty', "0"))
                symbol_info.max_qty = Decimal(lot_size_filter.get('maxOrderQty', "1000000"))
                symbol_info.min_order_value = Decimal(lot_size_filter.get('minOrderAmt', "10.0"))

                logger.info(f"{CYAN}Symbol info loaded for {config.SYMBOL}{NC}")
                return True

        logger.error(f"{RED}Failed to fetch symbol info for {config.SYMBOL}{NC}")
        return False

    async def test_credentials(self) -> bool:
        """Test API credentials"""
        response = await self.api_call_with_retry(
            self.http.get_wallet_balance,
            accountType="UNIFIED"
        )

        if response and response.get("retCode") == 0:
            logger.info(f"{GREEN}API credentials validated{NC}")
            return True

        logger.error(f"{RED}API credentials validation failed{NC}")
        return False

    def start_websockets(self):
        """Start WebSocket connections"""
        logger.info(f"{CYAN}Starting WebSocket connections...{NC}")

        # Start public orderbook stream
        self.ws_public.orderbook_stream(
            symbol=config.SYMBOL,
            depth=1,
            callback=on_public_ws_message
        )

        # Start private streams
        self.ws_private.order_stream(callback=on_private_ws_message)
        self.ws_private.position_stream(callback=on_private_ws_message)
        self.ws_private.wallet_stream(callback=on_private_ws_message)

        logger.info(f"{CYAN}WebSocket streams initiated{NC}")

    async def get_wallet_balance(self) -> bool:
        """Get wallet balance"""
        response = await self.api_call_with_retry(
            self.http.get_wallet_balance,
            accountType="UNIFIED"
        )

        if response and response.get('retCode') == 0:
            balance_list = response.get('result', {}).get('list', [])
            for balance in balance_list:
                for coin in balance.get('coin', []):
                    if coin.get('coin') == 'USDT':
                        market_state.available_balance = Decimal(coin.get('availableToWithdraw', '0'))
                        market_state.last_balance_update = time.time()
                        return True

        logger.error(f"{RED}Failed to fetch wallet balance{NC}")
        return False

    async def get_open_orders(self) -> bool:
        """Fetch open orders"""
        response = await self.api_call_with_retry(
            self.http.get_open_orders,
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )

        if response and response.get('retCode') == 0:
            orders = response.get('result', {}).get('list', [])
            market_state.open_orders.clear()

            for order in orders:
                order_id = order.get('orderId')
                if order_id:
                    market_state.open_orders[order_id] = {
                        "client_order_id": order.get("orderLinkId", "N/A"),
                        "symbol": order.get("symbol"),
                        "side": order.get("side"),
                        "price": Decimal(order.get("price", "0")),
                        "qty": Decimal(order.get("qty", "0")),
                        "status": order.get("orderStatus"),
                        "timestamp": float(order.get("createdTime", 0)) / 1000,
                    }

            return True

        return False

    async def get_positions(self) -> bool:
        """Fetch positions"""
        response = await self.api_call_with_retry(
            self.http.get_positions,
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )

        if response and response.get('retCode') == 0:
            positions = response.get('result', {}).get('list', [])
            market_state.positions.clear()

            for pos in positions:
                if pos.get("symbol") == config.SYMBOL and Decimal(pos.get("size", "0")) > 0:
                    side = "Long" if pos.get("side") == "Buy" else "Short"
                    market_state.positions[side] = {
                        "size": Decimal(pos.get("size", "0")),
                        "avg_price": Decimal(pos.get("avgPrice", "0")),
                        "unrealisedPnl": Decimal(pos.get("unrealisedPnl", "0")),
                        "leverage": Decimal(pos.get("leverage", "1")),
                        "liq_price": Decimal(pos.get("liqPrice", "0")),
                    }

            return True

        return False

    async def place_order(self, side: str, order_type: str, qty: Decimal, price: Decimal | None = None) -> dict | None:
        """Place an order with enhanced validation"""
        start_time = time.time()

        try:
            # Validate and quantize quantity
            quantized_qty = qty.quantize(symbol_info.qty_precision, rounding=ROUND_DOWN)
            if quantized_qty <= 0 or quantized_qty < symbol_info.min_qty:
                logger.warning(f"Invalid quantity: {qty} -> {quantized_qty}")
                return None

            if quantized_qty > symbol_info.max_qty:
                logger.warning(f"Quantity exceeds maximum: {quantized_qty} > {symbol_info.max_qty}")
                return None

            # Prepare order parameters
            order_params = {
                "category": config.CATEGORY,
                "symbol": config.SYMBOL,
                "side": side,
                "orderType": order_type,
                "qty": str(quantized_qty),
                "orderLinkId": f"mmxcel-{uuid.uuid4()}",
                "timeInForce": "GTC" if order_type == "Limit" else "IOC",
            }

            # Add price for limit orders
            if order_type == "Limit" and price:
                rounding = ROUND_DOWN if side == "Buy" else ROUND_UP
                quantized_price = price.quantize(symbol_info.price_precision, rounding=rounding)

                if quantized_price < symbol_info.min_price:
                    logger.warning(f"Price below minimum: {quantized_price} < {symbol_info.min_price}")
                    return None

                order_params["price"] = str(quantized_price)

                # Check minimum order value
                order_value = quantized_qty * quantized_price
                if order_value < symbol_info.min_order_value:
                    logger.warning(f"Order value below minimum: {order_value} < {symbol_info.min_order_value}")
                    return None

            # Place the order
            response = await self.api_call_with_retry(self.http.place_order, **order_params)

            if response and response.get('retCode') == 0:
                session_stats.orders_placed += 1
                order_latency = time.time() - start_time
                performance_monitor.record_order_latency(order_latency)

                logger.info(f"{GREEN}Order placed: {side} {quantized_qty} @ {price or 'Market'}{NC}")
                return response.get('result', {})

            return None

        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific order"""
        response = await self.api_call_with_retry(
            self.http.cancel_order,
            category=config.CATEGORY,
            symbol=config.SYMBOL,
            orderId=order_id
        )

        if response and response.get('retCode') == 0:
            logger.info(f"{GREEN}Order cancelled: {order_id}{NC}")
            market_state.open_orders.pop(order_id, None)
            return True

        return False

    async def cancel_all_orders(self) -> bool:
        """Cancel all open orders"""
        response = await self.api_call_with_retry(
            self.http.cancel_all_orders,
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )

        if response and response.get('retCode') == 0:
            logger.info(f"{GREEN}All orders cancelled{NC}")
            market_state.open_orders.clear()
            send_toast("All orders cancelled", "orange", "white")
            return True

        return False

    async def monitor_connections(self):
        """Monitor WebSocket connections"""
        while not _SHUTDOWN_REQUESTED:
            if not self.is_public_ws_connected:
                logger.warning(f"{YELLOW}Public WebSocket disconnected{NC}")
                send_toast("Public WS disconnected", "#FFA500", "white")

            if not self.is_private_ws_connected:
                logger.warning(f"{YELLOW}Private WebSocket disconnected{NC}")
                send_toast("Private WS disconnected", "#FFA500", "white")

            await asyncio.sleep(WS_MONITOR_INTERVAL)

# Enhanced Market Making Strategy
class EnhancedMarketMakingStrategy:
    """Enhanced market making strategy with improved risk management"""

    def __init__(self, client: EnhancedBybitClient):
        self.client = client
        self.running = False
        self.last_rebalance_time = 0
        self.emergency_stop_triggered = False
        self.volatility_multiplier = Decimal("1.0")

    def calculate_dynamic_spread(self) -> Decimal:
        """Calculate dynamic spread based on market conditions"""
        base_spread = config.SPREAD_PERCENTAGE

        if not config.VOLATILITY_ADJUSTMENT:
            return base_spread

        # Calculate current market spread
        if market_state.mid_price > 0 and market_state.best_bid > 0 and market_state.best_ask > 0:
            market_spread = (market_state.best_ask - market_state.best_bid) / market_state.mid_price

            # Adjust spread based on market conditions
            if market_spread > base_spread * 2:
                # Wide market spread - reduce our spread to be more competitive
                adjusted_spread = base_spread * Decimal("0.8")
            elif market_spread < base_spread * Decimal("0.5"):
                # Tight market spread - increase our spread for safety
                adjusted_spread = base_spread * Decimal("1.2")
            else:
                adjusted_spread = base_spread

            return max(adjusted_spread, symbol_info.price_precision / market_state.mid_price)

        return base_spread

    def calculate_position_size(self) -> Decimal:
        """Calculate optimal position size based on available balance and risk"""
        if market_state.available_balance <= 0 or market_state.mid_price <= 0:
            return config.QUANTITY

        # Calculate size based on capital allocation
        max_capital = market_state.available_balance * config.CAPITAL_ALLOCATION_PERCENTAGE
        size_from_capital = (max_capital / market_state.mid_price).quantize(
            symbol_info.qty_precision, rounding=ROUND_DOWN
        )

        # Apply maximum position size limit
        max_position_value = market_state.available_balance * config.MAX_POSITION_SIZE
        max_size_from_limit = (max_position_value / market_state.mid_price).quantize(
            symbol_info.qty_precision, rounding=ROUND_DOWN
        )

        # Use the minimum of configured quantity, capital-based size, and position limit
        optimal_size = min(config.QUANTITY, size_from_capital, max_size_from_limit)

        # Ensure minimum requirements are met
        if optimal_size < symbol_info.min_qty:
            optimal_size = symbol_info.min_qty

        # Check minimum order value
        if market_state.mid_price > 0:
            order_value = optimal_size * market_state.mid_price
            if order_value < symbol_info.min_order_value:
                optimal_size = (symbol_info.min_order_value / market_state.mid_price).quantize(
                    symbol_info.qty_precision, rounding=ROUND_UP
                )

        return optimal_size

    def check_emergency_conditions(self) -> tuple[bool, str]:
        """Check for emergency stop conditions"""
        # Check total unrealized PnL
        total_pnl = sum(pos.get("unrealisedPnl", Decimal("0"))
                       for pos in market_state.positions.values())

        if market_state.available_balance > 0:
            pnl_percentage = abs(total_pnl) / market_state.available_balance
            if pnl_percentage >= config.EMERGENCY_STOP_LOSS:
                return True, f"Emergency stop: PnL {pnl_percentage:.2%} exceeds limit"

        # Check for abnormal market conditions
        if market_state.mid_price > 0 and market_state.best_bid > 0 and market_state.best_ask > 0:
            spread_percentage = (market_state.best_ask - market_state.best_bid) / market_state.mid_price
            if spread_percentage > config.ABNORMAL_SPREAD_THRESHOLD:
                return True, f"Abnormal spread: {spread_percentage:.2%}"

        # Check for stale data
        if not market_state.is_data_fresh():
            return True, "Market data is stale"

        return False, ""

    async def place_market_making_orders(self):
        """Place market making orders with enhanced logic"""
        if not market_state.is_data_fresh():
            logger.warning("Market data not fresh, skipping order placement")
            return

        # Check emergency conditions
        emergency, reason = self.check_emergency_conditions()
        if emergency:
            if not self.emergency_stop_triggered:
                logger.critical(f"{RED}EMERGENCY STOP: {reason}{NC}")
                send_toast(f"Emergency stop: {reason[:30]}", "red", "white")
                await self.client.cancel_all_orders()
                self.emergency_stop_triggered = True
            return
        else:
            self.emergency_stop_triggered = False

        # Skip if we have enough orders
        if len(market_state.open_orders) >= config.MAX_OPEN_ORDERS:
            return

        # Calculate dynamic parameters
        spread = self.calculate_dynamic_spread()
        position_size = self.calculate_position_size()

        if position_size <= 0:
            logger.warning("Position size is zero, skipping order placement")
            return

        # Calculate order prices
        bid_price = market_state.mid_price * (Decimal("1") - spread)
        ask_price = market_state.mid_price * (Decimal("1") + spread)

        # Ensure prices don't cross the market
        bid_price = min(bid_price, market_state.best_bid - symbol_info.price_precision)
        ask_price = max(ask_price, market_state.best_ask + symbol_info.price_precision)

        # Place orders if we don't have them
        has_buy_order = any(order['side'] == 'Buy' for order in market_state.open_orders.values())
        has_sell_order = any(order['side'] == 'Sell' for order in market_state.open_orders.values())

        if not has_buy_order and len(market_state.open_orders) < config.MAX_OPEN_ORDERS:
            await self.client.place_order("Buy", "Limit", position_size, bid_price)

        if not has_sell_order and len(market_state.open_orders) < config.MAX_OPEN_ORDERS:
            await self.client.place_order("Sell", "Limit", position_size, ask_price)

    async def manage_positions(self):
        """Manage positions and rebalancing"""
        if not market_state.is_data_fresh():
            return

        # Calculate net position
        long_size = market_state.positions.get('Long', {}).get('size', Decimal('0'))
        short_size = market_state.positions.get('Short', {}).get('size', Decimal('0'))
        net_position = long_size - short_size

        # Check if rebalancing is needed
        if abs(net_position) > config.REBALANCE_THRESHOLD_QTY:
            # Avoid frequent rebalancing
            if time.time() - self.last_rebalance_time < 30:  # 30 second cooldown
                return

            logger.info(f"{YELLOW}Rebalancing needed: net position {net_position}{NC}")

            # Determine rebalance side and quantity
            rebalance_side = "Sell" if net_position > 0 else "Buy"
            rebalance_qty = abs(net_position).quantize(symbol_info.qty_precision, rounding=ROUND_DOWN)

            if rebalance_qty > 0:
                # Cancel existing orders before rebalancing
                await self.client.cancel_all_orders()
                await asyncio.sleep(1)  # Wait for cancellations

                # Place rebalance order
                if config.REBALANCE_ORDER_TYPE == "Market":
                    await self.client.place_order(rebalance_side, "Market", rebalance_qty)
                else:
                    # Use limit order with slight price improvement
                    if rebalance_side == "Buy":
                        price = market_state.best_ask + symbol_info.price_precision
                    else:
                        price = market_state.best_bid - symbol_info.price_precision

                    await self.client.place_order(rebalance_side, "Limit", rebalance_qty, price)

                self.last_rebalance_time = time.time()
                session_stats.rebalances_count += 1
                send_toast(f"Rebalanced {rebalance_qty} {config.SYMBOL}", "yellow", "black")

    async def cancel_stale_orders(self):
        """Cancel orders that have exceeded their lifespan"""
        current_time = time.time()
        stale_orders = []

        for order_id, order_data in market_state.open_orders.items():
            order_age = current_time - order_data.get('timestamp', current_time)
            if order_age > config.ORDER_LIFESPAN_SECONDS:
                stale_orders.append(order_id)

        if stale_orders:
            logger.info(f"Cancelling {len(stale_orders)} stale orders")
            tasks = [self.client.cancel_order(order_id) for order_id in stale_orders]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def monitor_pnl(self):
        """Monitor PnL and trigger stops if needed"""
        while self.running and not _SHUTDOWN_REQUESTED:
            if not market_state.is_data_fresh():
                await asyncio.sleep(PNL_MONITOR_INTERVAL)
                continue

            # Check individual position PnL
            for side, position in market_state.positions.items():
                if position['size'] <= 0 or position['avg_price'] <= 0:
                    continue

                entry_price = position['avg_price']
                current_price = market_state.mid_price

                if side == "Long":
                    pnl_pct = (current_price - entry_price) / entry_price
                else:  # Short
                    pnl_pct = (entry_price - current_price) / entry_price

                # Check stop loss
                if pnl_pct <= -config.STOP_LOSS_PERCENTAGE:
                    logger.critical(f"{RED}{side} position stop loss triggered: {pnl_pct:.2%}{NC}")
                    await self.client.cancel_all_orders()

                    close_side = "Sell" if side == "Long" else "Buy"
                    await self.client.place_order(close_side, "Market", position['size'])

                    send_toast(f"{side} stop loss: {pnl_pct:.2%}", "red", "white")

                # Check take profit
                elif pnl_pct >= config.PROFIT_PERCENTAGE:
                    logger.info(f"{GREEN}{side} position take profit triggered: {pnl_pct:.2%}{NC}")
                    await self.client.cancel_all_orders()

                    close_side = "Sell" if side == "Long" else "Buy"
                    await self.client.place_order(close_side, "Market", position['size'])

                    send_toast(f"{side} take profit: {pnl_pct:.2%}", "green", "white")

            await asyncio.sleep(PNL_MONITOR_INTERVAL)

    async def main_strategy_loop(self):
        """Main strategy execution loop"""
        last_order_refresh = 0
        last_balance_refresh = 0

        while self.running and not _SHUTDOWN_REQUESTED:
            try:
                current_time = time.time()

                # Refresh data periodically
                if current_time - last_balance_refresh >= config.BALANCE_REFRESH_INTERVAL:
                    await self.client.get_wallet_balance()
                    await self.client.get_positions()
                    last_balance_refresh = current_time

                if current_time - last_order_refresh >= config.ORDER_REFRESH_INTERVAL:
                    await self.client.get_open_orders()
                    last_order_refresh = current_time

                # Execute strategy components
                await self.cancel_stale_orders()
                await self.manage_positions()
                await self.place_market_making_orders()

                # Update bot state
                if self.emergency_stop_triggered:
                    set_bot_state("EMERGENCY_STOP")
                elif len(market_state.open_orders) > 0:
                    set_bot_state("ACTIVE_TRADING")
                else:
                    set_bot_state("WAITING")

                await asyncio.sleep(1)  # Main loop interval

            except Exception as e:
                logger.error(f"Error in strategy loop: {e}")
                set_bot_state("ERROR")
                await asyncio.sleep(5)  # Error recovery delay

# Dashboard and UI
async def display_dashboard():
    """Display enhanced dashboard"""
    while not _SHUTDOWN_REQUESTED:
        try:
            clear_screen()
            print_neon_header(f"MMXCEL v3.1 - Enhanced Market Maker ({config.SYMBOL})", UNDERLINE)

            # Bot status
            status_color = GREEN if BOT_STATE == "ACTIVE_TRADING" else YELLOW if BOT_STATE == "WAITING" else RED
            print(format_metric("Bot Status", BOT_STATE, WHITE, status_color))
            print(format_metric("Testnet Mode", "ON" if config.USE_TESTNET else "OFF", WHITE, YELLOW if config.USE_TESTNET else GREEN))
            print_neon_separator()

            # Market data
            print(f"{CYAN}{BOLD}Market Data:{NC}")
            price_precision = calculate_decimal_precision(symbol_info.price_precision)
            print(format_metric("Mid Price", market_state.mid_price, WHITE, value_precision=price_precision))
            print(format_metric("Best Bid", market_state.best_bid, WHITE, value_precision=price_precision))
            print(format_metric("Best Ask", market_state.best_ask, WHITE, value_precision=price_precision))

            if market_state.mid_price > 0:
                spread_pct = (market_state.best_ask - market_state.best_bid) / market_state.mid_price * 100
                print(format_metric("Market Spread", f"{spread_pct:.3f}%", WHITE))

            data_age = time.time() - market_state.last_update_time
            age_color = GREEN if data_age < 5 else YELLOW if data_age < 10 else RED
            print(format_metric("Data Age", f"{data_age:.1f}s", WHITE, age_color))
            print_neon_separator()

            # Account info
            print(f"{CYAN}{BOLD}Account Information:{NC}")
            print(format_metric("Available Balance", f"{market_state.available_balance:.2f} USDT", WHITE, GREEN))

            # Positions
            print(f"{CYAN}{BOLD}Positions:{NC}")
            long_pos = market_state.positions.get('Long', {'size': Decimal('0'), 'unrealisedPnl': Decimal('0')})
            short_pos = market_state.positions.get('Short', {'size': Decimal('0'), 'unrealisedPnl': Decimal('0')})

            qty_precision = calculate_decimal_precision(symbol_info.qty_precision)
            print(format_metric("Long Position", long_pos['size'], WHITE, value_precision=qty_precision))
            print(format_metric("Long PnL", long_pos['unrealisedPnl'], WHITE, is_pnl=True, value_precision=2))
            print(format_metric("Short Position", short_pos['size'], WHITE, value_precision=qty_precision))
            print(format_metric("Short PnL", short_pos['unrealisedPnl'], WHITE, is_pnl=True, value_precision=2))

            net_position = long_pos['size'] - short_pos['size']
            print(format_metric("Net Position", net_position, WHITE, value_precision=qty_precision))
            print_neon_separator()

            # Open orders
            print(f"{CYAN}{BOLD}Open Orders ({len(market_state.open_orders)}):{NC}")
            if market_state.open_orders:
                for order_id, order in list(market_state.open_orders.items())[:5]:  # Show max 5 orders
                    side_color = GREEN if order['side'] == 'Buy' else RED
                    age = time.time() - order['timestamp']
                    age_color = GREEN if age < 15 else YELLOW if age < 30 else RED
                    print(f"  {side_color}{order['side']:<4}{NC} {order['qty']:.{qty_precision}f} @ {order['price']:.{price_precision}f} {age_color}({age:.0f}s){NC}")
            else:
                print(f"  {YELLOW}No active orders{NC}")
            print_neon_separator()

            # Performance metrics
            print(f"{CYAN}{BOLD}Performance:{NC}")
            uptime = time.time() - session_stats.start_time
            hours, remainder = divmod(uptime, 3600)
            minutes, seconds = divmod(remainder, 60)
            print(format_metric("Uptime", f"{int(hours):02d}h {int(minutes):02d}m {int(seconds):02d}s", WHITE))
            print(format_metric("Orders Placed", session_stats.orders_placed, WHITE))
            print(format_metric("Orders Filled", session_stats.orders_filled, WHITE))
            print(format_metric("Orders Cancelled", session_stats.orders_cancelled, WHITE))
            print(format_metric("Rebalances", session_stats.rebalances_count, WHITE))

            total_pnl = long_pos['unrealisedPnl'] + short_pos['unrealisedPnl']
            print(format_metric("Total PnL", total_pnl, WHITE, is_pnl=True, value_precision=2))
            print(format_metric("Max Drawdown", f"{session_stats.max_drawdown:.2%}", WHITE, RED if session_stats.max_drawdown > 0 else GREEN))

            # Performance stats
            avg_api_time = performance_monitor.get_avg_api_time()
            avg_order_latency = performance_monitor.get_avg_order_latency()
            if avg_api_time > 0:
                print(format_metric("Avg API Time", f"{avg_api_time:.3f}s", WHITE))
            if avg_order_latency > 0:
                print(format_metric("Avg Order Latency", f"{avg_order_latency:.3f}s", WHITE))

            print_neon_separator()
            print(f"{YELLOW}Commands: 'q' quit | 'c' cancel all | 'r' rebalance | 's' emergency stop{NC}")

            await asyncio.sleep(DASHBOARD_REFRESH_INTERVAL)

        except Exception as e:
            logger.error(f"Dashboard error: {e}")
            await asyncio.sleep(1)

# Input handling
async def handle_user_input(strategy: EnhancedMarketMakingStrategy):
    """Handle user keyboard input"""
    while not _SHUTDOWN_REQUESTED:
        try:
            # Non-blocking input check
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                key = sys.stdin.read(1).lower()

                if key == 'q':
                    logger.info("User requested shutdown")
                    global _SHUTDOWN_REQUESTED
                    _SHUTDOWN_REQUESTED = True
                    break

                elif key == 'c':
                    logger.info("User requested cancel all orders")
                    await strategy.client.cancel_all_orders()
                    send_toast("All orders cancelled by user", "orange", "white")

                elif key == 'r':
                    logger.info("User requested manual rebalance")
                    strategy.last_rebalance_time = 0  # Reset cooldown
                    await strategy.manage_positions()
                    send_toast("Manual rebalance triggered", "blue", "white")

                elif key == 's':
                    logger.warning("User triggered emergency stop")
                    strategy.emergency_stop_triggered = True
                    await strategy.client.cancel_all_orders()
                    send_toast("Emergency stop activated", "red", "white")

            await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Input handling error: {e}")
            await asyncio.sleep(1)

# Signal handling
def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global _SHUTDOWN_REQUESTED
    logger.info(f"Received signal {signum}, initiating shutdown...")
    _SHUTDOWN_REQUESTED = True
    send_toast("MMXCEL: Shutdown signal received", "red", "white")

# Main execution
async def main():
    """Main application entry point"""
    global _HAS_TERMUX_TOAST_CMD, _SHUTDOWN_REQUESTED

    # Setup
    _HAS_TERMUX_TOAST_CMD = check_termux_toast()
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print_neon_header("MMXCEL v3.1 - Enhanced Market Maker", UNDERLINE)
    print(f"{CYAN}Initializing enhanced trading bot...{NC}")
    print_neon_separator()

    # Validate configuration
    if not API_KEY or not API_SECRET:
        logger.error("API credentials not found in environment")
        sys.exit(1)

    # Initialize client and strategy
    client = EnhancedBybitClient(API_KEY, API_SECRET, config.USE_TESTNET)
    strategy = EnhancedMarketMakingStrategy(client)

    try:
        # Test credentials
        set_bot_state("TESTING_CREDENTIALS")
        if not await client.test_credentials():
            logger.error("Credential validation failed")
            sys.exit(1)

        # Get symbol info
        set_bot_state("LOADING_SYMBOL_INFO")
        if not await client.get_symbol_info():
            logger.error("Failed to load symbol information")
            sys.exit(1)

        # Start WebSocket connections
        set_bot_state("CONNECTING_WEBSOCKETS")
        client.start_websockets()

        # Wait for WebSocket connections
        connection_timeout = 30
        start_time = time.time()
        while not (client.is_public_ws_connected and client.is_private_ws_connected):
            if time.time() - start_time > connection_timeout:
                logger.error("WebSocket connection timeout")
                sys.exit(1)
            await asyncio.sleep(0.5)

        logger.info(f"{GREEN}WebSocket connections established{NC}")

        # Initial data sync
        set_bot_state("SYNCING_DATA")
        await client.get_wallet_balance()
        await client.get_open_orders()
        await client.get_positions()

        # Validate initial state
        if market_state.available_balance <= 0:
            logger.error("No available balance found")
            sys.exit(1)

        # Start strategy
        set_bot_state("STARTING_STRATEGY")
        strategy.running = True

        logger.info(f"{GREEN}Bot initialization complete. Starting trading...{NC}")
        send_toast("MMXCEL v3.1 started successfully", "green", "white")

        # Run main tasks
        await asyncio.gather(
            strategy.main_strategy_loop(),
            strategy.monitor_pnl(),
            client.monitor_connections(),
            display_dashboard(),
            handle_user_input(strategy),
            return_exceptions=True
        )

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        # Cleanup
        set_bot_state("SHUTTING_DOWN")
        strategy.running = False

        logger.info("Performing cleanup...")

        # Cancel all orders
        try:
            await client.cancel_all_orders()
        except Exception as e:
            logger.error(f"Error cancelling orders during shutdown: {e}")

        # Close WebSocket connections
        try:
            if hasattr(client, 'ws_public'):
                client.ws_public.exit()
            if hasattr(client, 'ws_private'):
                client.ws_private.exit()
        except Exception as e:
            logger.error(f"Error closing WebSocket connections: {e}")

        logger.info(f"{GREEN}MMXCEL v3.1 shutdown complete{NC}")
        send_toast("MMXCEL v3.1 shutdown complete", "blue", "white")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Shutdown requested by user{NC}")
    except Exception as e:
        print(f"\n{RED}Fatal error: {e}{NC}")
        logger.critical(f"Fatal error during execution: {e}", exc_info=True)
