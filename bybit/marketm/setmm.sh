#!/bin/bash

# Define project name and directory
PROJECT_NAME="bybit_trading_bot"
PROJECT_DIR="./$PROJECT_NAME"

# --- Step 1: Project Setup ---
echo "Creating project directory: $PROJECT_DIR"
mkdir -p "$PROJECT_DIR"
if [ $? -ne 0 ]; then
    echo "Error: Failed to create project directory '$PROJECT_DIR'. Please check permissions."
    exit 1
fi

# Change into the project directory
cd "$PROJECT_DIR" || { echo "Error: Failed to change directory to '$PROJECT_DIR'. Exiting."; exit 1; }
echo "Successfully changed directory to $(pwd)"

# --- Step 2: Create Python Files ---

# Create bybit_bot.py
echo "Creating bybit_bot.py..."
cat << 'EOF' > bybit_bot.py
# bybit_bot.py

import os
import time
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from pybit.unified_trading import HTTP, WebSocket
from decimal import Decimal, getcontext
import asyncio
import functools
import yaml  # Added for YAML config support
import smtplib  # Added for email alerts
from email.mime.text import MIMEText  # Added for email alerts
import traceback  # Added for better error tracing
import random  # Added for jitter in backoff
import sys  # Added for sys exit on critical errors

# Set decimal precision for financial calculations (Improvement 1: Increased precision for better accuracy in high-value trades)
getcontext().prec = 28

# --- Logging Setup ---
# Improvement 5: Added file handler for persistent logs
# Improvement 6: Set to DEBUG for more detailed logging
log_level = logging.DEBUG if os.getenv("DEBUG_LOG", "false").lower() == "true" else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bybit_bot.log")
    ]
)
logger = logging.getLogger(__name__)

# --- Configuration ---
# Load API credentials from environment variables or YAML config (Improvement 2: Added YAML config fallback for flexibility)
config = {}
try:
    with open("bot_config.yaml", "r") as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    logger.warning("bot_config.yaml not found. Relying on environment variables.")
except Exception as e:
    logger.error(f"Error loading bot_config.yaml: {e}")

API_KEY = os.getenv("BYBIT_API_KEY") or config.get("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET") or config.get("BYBIT_API_SECRET")
USE_TESTNET = (os.getenv("BYBIT_USE_TESTNET", "false") or config.get("BYBIT_USE_TESTNET", "false")).lower() == "true"
EMAIL_ALERTS = config.get("EMAIL_ALERTS", False)  # Improvement 3: Added email alert configuration
EMAIL_SERVER = config.get("EMAIL_SERVER", {})
MAX_RETRIES = int(config.get("MAX_RETRIES", 5))  # Improvement 4: Configurable max retries for API calls

# Improvement 7: Added function to send email alerts
def send_email_alert(subject: str, body: str):
    if not EMAIL_ALERTS:
        return
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_SERVER.get('from')
        msg['To'] = EMAIL_SERVER.get('to')
        
        if not all([EMAIL_SERVER.get('host'), EMAIL_SERVER.get('port'), EMAIL_SERVER.get('user'), EMAIL_SERVER.get('pass')]):
            logger.error("Email server configuration is incomplete. Cannot send alert.")
            return

        with smtplib.SMTP(EMAIL_SERVER.get('host'), EMAIL_SERVER.get('port')) as server:
            # server.starttls() # Uncomment if your SMTP server requires TLS
            server.login(EMAIL_SERVER.get('user'), EMAIL_SERVER.get('pass'))
            server.send_message(msg)
        logger.info("Email alert sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send email alert: {e}", exc_info=True)

# --- WebSocket Manager ---
class BybitWebSocketManager:
    """
    Manages WebSocket connections for Bybit public and private streams.
    Stores real-time market data, positions, and orders.
    """
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True, category: str = "linear"): # Improvement 9: Added category parameter
        self.ws_public: Optional[WebSocket] = None
        self.ws_private: Optional[WebSocket] = None
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.category = category # Improvement 9: Store category

        self.market_data: Dict[str, Any] = {}  # Stores orderbook, ticker, last_trade
        self.positions: Dict[str, Any] = {}    # Stores open positions
        self.orders: Dict[str, Any] = {}       # Stores open/recent orders

        self._public_subscriptions: List[str] = []
        self._private_subscriptions: List[str] = []
        self.reconnect_attempts: int = 0  # Improvement 8: Track reconnect attempts

    def _init_public_ws(self):
        """Initializes the public WebSocket connection if not already active."""
        if not self.ws_public or not self.ws_public.is_connected():
            try:
                self.ws_public = WebSocket(
                    testnet=self.testnet,
                    channel_type=self.category,  # Improvement 9: Use stored category
                )
                logger.info(f"Public WebSocket initialized for category: {self.category}.")
            except Exception as e:
                logger.error(f"Failed to initialize public WebSocket: {e}", exc_info=True)
                send_email_alert("WS Init Error", f"Failed to initialize public WebSocket: {e}")

    def _init_private_ws(self):
        """Initializes the private WebSocket connection if not already active."""
        if not self.ws_private or not self.ws_private.is_connected():
            try:
                self.ws_private = WebSocket(
                    testnet=self.testnet,
                    channel_type="private",
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    recv_window=10000
                )
                logger.info("Private WebSocket initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize private WebSocket: {e}", exc_info=True)
                send_email_alert("WS Init Error", f"Failed to initialize private WebSocket: {e}")

    def handle_orderbook(self, message: Dict):
        """Processes orderbook updates and stores the data."""
        try:
            data = message.get("data", {})
            symbol = data.get("s")
            if symbol:
                self.market_data.setdefault(symbol, {})["orderbook"] = data
                self.market_data[symbol]["timestamp"] = message.get("ts")
                # Improvement 10: Reduced logging to INFO level for performance
                # logger.info(f"Orderbook updated for {symbol}") # Too verbose for INFO
        except Exception as e:
            logger.error(f"Error handling orderbook: {e}", exc_info=True)
            send_email_alert("Orderbook Error", str(e))  # Improvement 11: Alert on error

    def handle_trades(self, message: Dict):
        """Processes trade updates and stores the latest trade."""
        try:
            data = message.get("data", [])
            for trade in data:
                symbol = trade.get("s")
                if symbol:
                    self.market_data.setdefault(symbol, {})["last_trade"] = trade
                    # logger.info(f"Trade updated for {symbol}") # Too verbose for INFO
        except Exception as e:
            logger.error(f"Error handling trades: {e}", exc_info=True)
            send_email_alert("Trades Error", str(e))

    def handle_ticker(self, message: Dict):
        """Processes ticker updates and stores the data."""
        try:
            data = message.get("data", {})
            symbol = data.get("s")
            if symbol:
                self.market_data.setdefault(symbol, {})["ticker"] = data
                # logger.info(f"Ticker updated for {symbol}") # Too verbose for INFO
        except Exception as e:
            logger.error(f"Error handling ticker: {e}", exc_info=True)
            send_email_alert("Ticker Error", str(e))

    def handle_position(self, message: Dict):
        """Processes position updates and stores them by symbol."""
        try:
            data = message.get("data", [])
            for position in data:
                symbol = position.get("symbol")
                if symbol:
                    self.positions[symbol] = position
                    # logger.info(f"Position updated for {symbol}") # Too verbose for INFO
        except Exception as e:
            logger.error(f"Error handling position: {e}", exc_info=True)
            send_email_alert("Position Error", str(e))

    def handle_order(self, message: Dict):
        """Processes order updates and stores them by orderId."""
        try:
            data = message.get("data", [])
            for order in data:
                order_id = order.get("orderId")
                if order_id:
                    self.orders[order_id] = order
                    # logger.info(f"Order updated for {order_id}") # Too verbose for INFO
        except Exception as e:
            logger.error(f"Error handling order: {e}", exc_info=True)
            send_email_alert("Order Error", str(e))

    def handle_execution(self, message: Dict):
        """Processes execution/fill updates."""
        try:
            data = message.get("data", [])
            for execution in data:
                order_id = execution.get("orderId")
                if order_id:
                    logger.info(f"Execution for {order_id}: Price: {execution.get('execPrice')}, Qty: {execution.get('execQty')}, Side: {execution.get('side')}")
        except Exception as e:
            logger.error(f"Error handling execution: {e}", exc_info=True)
            send_email_alert("Execution Error", str(e))

    def handle_wallet(self, message: Dict):
        """Processes wallet updates."""
        try:
            data = message.get("data", [])
            for wallet_data in data:
                coin = wallet_data.get("coin")
                if coin:
                    logger.info(f"Wallet update for {coin}: Available: {wallet_data.get('availableToWithdraw')}, Total: {wallet_data.get('walletBalance')}")
        except Exception as e:
            logger.error(f"Error handling wallet: {e}", exc_info=True)
            send_email_alert("Wallet Error", str(e))

    # Improvement 12: Added more WS handlers (e.g., for kline, if subscribed)
    def handle_kline(self, message: Dict):
        try:
            data = message.get("data", [])
            # The topic format can vary, e.g., "kline.1.BTCUSDT" or "kline.1m.BTCUSDT"
            # Safely extract symbol from topic if available
            symbol = None
            if "topic" in message:
                parts = message["topic"].split(".")
                if len(parts) >= 3 and parts[0] == "kline":
                    symbol = parts[-1] # Assume last part is symbol
            
            if symbol and data:
                self.market_data.setdefault(symbol, {})["kline"] = data
                # logger.info(f"Kline updated for {symbol}") # Too verbose for INFO
        except Exception as e:
            logger.error(f"Error handling kline: {e}", exc_info=True)

    async def subscribe_public_channels(self, symbols: List[str], channels: List[str] = ["orderbook", "publicTrade", "tickers", "kline"]):  # Improvement 13: Added kline channel
        """Subscribes to public market data channels for specified symbols."""
        self._init_public_ws()
        if not self.ws_public or not self.ws_public.is_connected():
            logger.error("Public WebSocket not initialized or connected for subscription.")
            return

        # Add a small delay to allow WS to establish before subscribing
        await asyncio.sleep(0.5) 

        for symbol in symbols:
            # Orderbook subscription
            if "orderbook" in channels and f"orderbook.1.{symbol}" not in self._public_subscriptions:
                try:
                    self.ws_public.orderbook_stream(
                        depth=1,
                        symbol=symbol,
                        callback=self.handle_orderbook
                    )
                    self._public_subscriptions.append(f"orderbook.1.{symbol}")
                    logger.info(f"Subscribed to orderbook.1.{symbol}")
                except Exception as e:
                    logger.error(f"Error subscribing to orderbook for {symbol}: {e}", exc_info=True)
            
            # Public trade subscription
            if "publicTrade" in channels and f"publicTrade.{symbol}" not in self._public_subscriptions:
                try:
                    self.ws_public.trade_stream(
                        symbol=symbol,
                        callback=self.handle_trades
                    )
                    self._public_subscriptions.append(f"publicTrade.{symbol}")
                    logger.info(f"Subscribed to publicTrade.{symbol}")
                except Exception as e:
                    logger.error(f"Error subscribing to publicTrade for {symbol}: {e}", exc_info=True)
            
            # Ticker subscription
            if "tickers" in channels and f"tickers.{symbol}" not in self._public_subscriptions:
                try:
                    self.ws_public.ticker_stream(
                        symbol=symbol,
                        callback=self.handle_ticker
                    )
                    self._public_subscriptions.append(f"tickers.{symbol}")
                    logger.info(f"Subscribed to tickers.{symbol}")
                except Exception as e:
                    logger.error(f"Error subscribing to tickers for {symbol}: {e}", exc_info=True)
            
            # Kline subscription (Improvement 14: Subscribe to 1m kline)
            if "kline" in channels and f"kline.1m.{symbol}" not in self._public_subscriptions:
                try:
                    self.ws_public.kline_stream(
                        interval="1", # 1 minute interval
                        symbol=symbol,
                        callback=self.handle_kline
                    )
                    self._public_subscriptions.append(f"kline.1m.{symbol}")
                    logger.info(f"Subscribed to kline.1m.{symbol}")
                except Exception as e:
                    logger.error(f"Error subscribing to kline for {symbol}: {e}", exc_info=True)

    async def subscribe_private_channels(self, channels: List[str] = ["position", "order", "execution", "wallet"]):
        """Subscribes to private account channels."""
        self._init_private_ws()
        if not self.ws_private or not self.ws_private.is_connected():
            logger.error("Private WebSocket not initialized or connected for subscription.")
            return

        # Add a small delay to allow WS to establish before subscribing
        await asyncio.sleep(0.5)

        if "position" in channels and "position" not in self._private_subscriptions:
            try:
                self.ws_private.position_stream(callback=self.handle_position)
                self._private_subscriptions.append("position")
                logger.info("Subscribed to position stream.")
            except Exception as e:
                logger.error(f"Error subscribing to position stream: {e}", exc_info=True)
                send_email_alert("WS Subscription Error", f"Failed to subscribe to position stream: {e}")

        if "order" in channels and "order" not in self._private_subscriptions:
            try:
                self.ws_private.order_stream(callback=self.handle_order)
                self._private_subscriptions.append("order")
                logger.info("Subscribed to order stream.")
            except Exception as e:
                logger.error(f"Error subscribing to order stream: {e}", exc_info=True)
                send_email_alert("WS Subscription Error", f"Failed to subscribe to order stream: {e}")

        if "execution" in channels and "execution" not in self._private_subscriptions:
            try:
                self.ws_private.execution_stream(callback=self.handle_execution)
                self._private_subscriptions.append("execution")
                logger.info("Subscribed to execution stream.")
            except Exception as e:
                logger.error(f"Error subscribing to execution stream: {e}", exc_info=True)
                send_email_alert("WS Subscription Error", f"Failed to subscribe to execution stream: {e}")

        if "wallet" in channels and "wallet" not in self._private_subscriptions:
            try:
                self.ws_private.wallet_stream(callback=self.handle_wallet)
                self._private_subscriptions.append("wallet")
                logger.info("Subscribed to wallet stream.")
            except Exception as e:
                logger.error(f"Error subscribing to wallet stream: {e}", exc_info=True)
                send_email_alert("WS Subscription Error", f"Failed to subscribe to wallet stream: {e}")

    def start(self):
        """Starts the WebSocket connections."""
        logger.info("WebSocket Manager started.")

    def stop(self):
        """Stops and closes all WebSocket connections."""
        if self.ws_public:
            try:
                self.ws_public.exit()
                logger.info("Public WebSocket connection closed.")
            except Exception as e:
                logger.error(f"Error closing public WebSocket: {e}", exc_info=True)
        if self.ws_private:
            try:
                self.ws_private.exit()
                logger.info("Private WebSocket connection closed.")
            except Exception as e:
                logger.error(f"Error closing private WebSocket: {e}", exc_info=True)
        logger.info("WebSocket Manager stopped.")

    def is_public_connected(self) -> bool:
        """Checks if the public WebSocket is connected."""
        return self.ws_public is not None and self.ws_public.is_connected()

    def is_private_connected(self) -> bool:
        """Checks if the private WebSocket is connected."""
        return self.ws_private is not None and self.ws_private.is_connected()

    # Improvement 15: Added reconnect with exponential backoff
    async def reconnect(self, symbols: List[str]):
        self.reconnect_attempts += 1
        if self.reconnect_attempts > MAX_RETRIES:
            logger.critical("Max reconnect attempts reached. Shutting down.")
            send_email_alert("Critical: Max Reconnects", "Bot shutting down due to persistent connection issues.")
            sys.exit(1)
        
        # Exponential backoff with jitter
        backoff = min(2 ** self.reconnect_attempts + random.uniform(0, 1), 60)
        logger.warning(f"Reconnecting WebSocket after {backoff:.2f} seconds (Attempt {self.reconnect_attempts}/{MAX_RETRIES})")
        await asyncio.sleep(backoff)
        
        try:
            await self.subscribe_public_channels(symbols)
            await self.subscribe_private_channels()
            # Reset attempts if reconnection is successful
            if self.is_public_connected() and self.is_private_connected():
                self.reconnect_attempts = 0
                logger.info("WebSocket reconnected successfully.")
            else:
                logger.warning("WebSocket reconnection attempt finished, but connections not fully established.")
        except Exception as e:
            logger.error(f"Error during WebSocket reconnection: {e}", exc_info=True)
            send_email_alert("WS Reconnect Error", f"Error during reconnection attempt: {e}")


# --- Trading Bot Core ---
class BybitTradingBot:
    """
    Core Bybit trading bot functionality, integrating HTTP API and WebSocket data.
    """
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
            recv_window=10000
        )
        self.category: str = config.get("CATEGORY", "linear")  # Improvement 17: Configurable category
        # Improvement 9: Pass category to WebSocket manager
        self.ws_manager = BybitWebSocketManager(api_key, api_secret, testnet, category=self.category) 
        self.strategy: Optional[Callable[[Dict, Dict, HTTP, Any, List[str]], None]] = None
        self.symbol_info: Dict[str, Any] = {}
        self.max_open_positions: int = config.get("MAX_OPEN_POSITIONS", 5)  # Improvement 16: Configurable max positions
        self.base_currency: str = config.get("BASE_CURRENCY", "USDT")  # Improvement 18: Configurable base currency

        logger.info(f"Bybit Trading Bot initialized. Testnet: {testnet}, Category: {self.category}, Base Currency: {self.base_currency}")

    async def fetch_symbol_info(self, symbols: List[str]):
        """Fetches and stores instrument details for given symbols."""
        logger.info(f"Fetching instrument info for symbols: {symbols}")
        try:
            for symbol in symbols:
                # Improvement 19: Added retry logic for fetching info
                for attempt in range(MAX_RETRIES):
                    try:
                        # Use asyncio.to_thread for non-async HTTP calls
                        response = await asyncio.to_thread(self.session.get_instruments_info, category=self.category, symbol=symbol)
                        if response and response.get('retCode') == 0:
                            instrument_list = response.get('result', {}).get('list', [])
                            found = False
                            for item in instrument_list:
                                if item.get('symbol') == symbol:
                                    self.symbol_info[symbol] = {
                                        "minOrderQty": Decimal(item.get('lotSizeFilter', {}).get('minOrderQty', '0')),
                                        "qtyStep": Decimal(item.get('lotSizeFilter', {}).get('qtyStep', '1')),
                                        "tickSize": Decimal(item.get('priceFilter', {}).get('tickSize', '0.000001')),
                                        "minPrice": Decimal(item.get('priceFilter', {}).get('minPrice', '0')),
                                        "maxPrice": Decimal(item.get('priceFilter', {}).get('maxPrice', '1000000')),
                                        "leverageFilter": item.get('leverageFilter', {}),
                                        "riskLimit": item.get('riskLimit', {})  # Improvement 20: Added risk limit info
                                    }
                                    logger.info(f"Successfully fetched instrument info for {symbol}.")
                                    found = True
                                    break
                            if not found:
                                logger.warning(f"Symbol {symbol} not found in instruments list response.")
                            break # Break retry loop if successful
                        else:
                            logger.warning(f"Attempt {attempt+1}/{MAX_RETRIES} for {symbol}: API returned error code {response.get('retCode')}: {response.get('retMsg')}")
                            await asyncio.sleep(2 ** attempt) # Wait before retrying
                    except Exception as e:
                        logger.warning(f"Attempt {attempt+1}/{MAX_RETRIES} for {symbol}: Exception occurred: {e}")
                        await asyncio.sleep(2 ** attempt) # Wait before retrying
                else: # This else belongs to the for loop (executes if loop completes without break)
                    logger.error(f"Failed to fetch instrument info for {symbol} after {MAX_RETRIES} retries.")
                    send_email_alert("Symbol Info Failure", f"Failed to fetch instrument info for {symbol} after retries.")
        except Exception as e:
            logger.error(f"An unexpected error occurred during fetch_symbol_info: {e}", exc_info=True)

    def set_strategy(self, strategy_func: Callable[[Dict, Dict, HTTP, Any, List[str]], None]):
        """
        Sets the trading strategy function.
        The strategy function should accept (market_data, account_info, http_client, bot_instance, symbols) as arguments.
        """
        self.strategy = strategy_func
        logger.info("Trading strategy set.")

    def _round_to_qty_step(self, symbol: str, quantity: Decimal) -> Decimal:
        """Rounds a quantity to the nearest valid step for a given symbol."""
        if symbol not in self.symbol_info:
            logger.warning(f"Symbol info not available for {symbol}. Cannot round quantity.")
            return quantity
        try:
            qty_step = self.symbol_info[symbol]["qtyStep"]
            if qty_step <= 0: # Avoid division by zero or invalid step
                logger.warning(f"Invalid qtyStep ({qty_step}) for {symbol}. Returning original quantity.")
                return quantity
            # Improvement 21: Changed to floor division for conservative rounding
            return (quantity // qty_step) * qty_step
        except Exception as e:
            logger.error(f"Error rounding quantity for {symbol}: {e}", exc_info=True)
            return quantity

    def _round_to_tick_size(self, symbol: str, price: Decimal) -> Decimal:
        """Rounds a price to the nearest valid tick size for a given symbol."""
        if symbol not in self.symbol_info:
            logger.warning(f"Symbol info not available for {symbol}. Cannot round price.")
            return price
        try:
            tick_size = self.symbol_info[symbol]["tickSize"]
            if tick_size <= 0: # Avoid division by zero or invalid tick size
                logger.warning(f"Invalid tickSize ({tick_size}) for {symbol}. Returning original price.")
                return price
            return price.quantize(tick_size)
        except Exception as e:
            logger.error(f"Error rounding price for {symbol}: {e}", exc_info=True)
            return price

    async def get_market_data(self, symbol: str) -> Optional[Dict]:
        """
        Retrieve current market data for a symbol.
        Prioritizes WebSocket data if available and fresh, falls back to REST API.
        """
        ws_data = self.ws_manager.market_data.get(symbol)
        # Improvement 22: Added 2s freshness check
        # Check if WS data exists, has orderbook and ticker, and is within 2 seconds
        if ws_data and ws_data.get("orderbook") and ws_data.get("ticker") and (time.time() * 1000 - ws_data.get("timestamp", 0)) < 2000:
            return ws_data
        
        logger.debug(f"WebSocket data for {symbol} not fresh or complete. Falling back to REST API.")
        
        try:
            # Improvement 23: Wrapped in to_thread for async
            orderbook_resp = await asyncio.to_thread(self.session.get_orderbook, category=self.category, symbol=symbol)
            ticker_resp = await asyncio.to_thread(self.session.get_tickers, category=self.category, symbol=symbol)

            if orderbook_resp and orderbook_resp.get('retCode') == 0 and ticker_resp and ticker_resp.get('retCode') == 0:
                # Improvement 24: Adjusted for list structure for ticker
                ticker_list = ticker_resp.get('result', {}).get('list', [])
                ticker_data = ticker_list[0] if ticker_list else {}
                
                # Combine WS data (if any) with REST data for a more complete picture
                combined_data = {
                    "orderbook": orderbook_resp.get('result', {}),
                    "ticker": ticker_data,
                    "last_trade": ws_data.get("last_trade") if ws_data else [] # Keep last WS trade if available
                }
                # Update WS timestamp if we got data from REST, to avoid immediate re-fetch
                if combined_data.get("orderbook"):
                    combined_data["timestamp"] = time.time() * 1000

                return combined_data
            else:
                logger.warning(f"Failed to get market data for {symbol} via REST. Orderbook: {orderbook_resp.get('retMsg')}, Ticker: {ticker_resp.get('retMsg')}")
                return None
        except Exception as e:
            logger.error(f"Error fetching market data for {symbol} via REST: {e}", exc_info=True)
            return None

    async def get_account_info(self, account_type: str = "UNIFIED") -> Optional[Dict]:
        """
        Retrieve account balance information.
        Prioritizes WebSocket data if available, falls back to REST API.
        """
        # Note: The current implementation only uses REST API for account info.
        # If WS wallet updates are frequent and reliable, they could be used.
        try:
            # Improvement 25: Wrapped in to_thread
            balance_response = await asyncio.to_thread(self.session.get_wallet_balance, accountType=account_type)
            if balance_response and balance_response.get('retCode') == 0:
                return balance_response.get('result', {})
            else:
                logger.warning(f"Failed to get account balance. API Response: {balance_response.get('retMsg')}")
                return None
        except Exception as e:
            logger.error(f"Error fetching account balance: {e}", exc_info=True)
            return None

    async def calculate_position_size(self, symbol: str, capital_percentage: float, price: Decimal, account_info: Dict) -> Decimal:
        """
        Calculates the position size based on a percentage of available capital.
        Returns the quantity as a Decimal, rounded to the symbol's qtyStep.
        """
        if symbol not in self.symbol_info:
            logger.warning(f"Symbol info not available for {symbol}. Cannot calculate position size.")
            return Decimal(0)

        try:
            available_balance = Decimal(0)
            # Improvement 26: Handle nested coin list structure correctly
            # Improvement 48: Support for multiple base currencies (iterates, but uses singular self.base_currency)
            for wallet_entry in account_info.get('list', []):
                for coin_info in wallet_entry.get('coin', []):
                    if coin_info.get('coin') == self.base_currency:
                        available_balance = Decimal(coin_info.get('availableToWithdraw', '0'))
                        break # Found the base currency, no need to check other coins in this wallet
                if available_balance > 0: # If found in current wallet, break outer loop too
                    break

            if available_balance <= 0:
                logger.warning(f"No available balance for {self.base_currency} to calculate position size.")
                return Decimal(0)

            if price <= 0:
                logger.warning(f"Invalid price ({price}) for {symbol}. Cannot calculate position size.")
                return Decimal(0)

            target_capital = available_balance * Decimal(str(capital_percentage))
            raw_qty = target_capital / price

            rounded_qty = self._round_to_qty_step(symbol, raw_qty)
            min_order_qty = self.symbol_info[symbol]["minOrderQty"]

            if rounded_qty < min_order_qty:
                logger.info(f"Calculated quantity {rounded_qty} for {symbol} is below minimum order quantity {min_order_qty}. Skipping.")
                return Decimal(0)

            # Improvement 27: Added max qty check from leverage filter
            max_leverage = Decimal(self.symbol_info[symbol]["leverageFilter"].get("maxLeverage", "1"))
            # Max quantity is limited by available balance and max leverage
            max_qty_by_leverage = (available_balance * max_leverage) / price
            
            if rounded_qty > max_qty_by_leverage:
                logger.warning(f"Calculated quantity {rounded_qty} for {symbol} exceeds max quantity by leverage ({max_qty_by_leverage}). Adjusting.")
                rounded_qty = self._round_to_qty_step(symbol, max_qty_by_leverage)
                if rounded_qty < min_order_qty:
                    logger.warning(f"Adjusted quantity for {symbol} is now below minimum order quantity. Skipping.")
                    return Decimal(0)

            logger.info(f"Calculated position size for {symbol}: {rounded_qty} (Capital: {target_capital:.4f} {self.base_currency}, Price: {price})")
            return rounded_qty

        except Exception as e:
            logger.error(f"Error calculating position size for {symbol}: {e}", exc_info=True)
            return Decimal(0)

    async def get_historical_klines(self, symbol: str, interval: str, limit: int = 200) -> Optional[Dict]:
        """Retrieve historical candlestick data (Klines)."""
        try:
            # Improvement 28: Wrapped in to_thread
            klines_response = await asyncio.to_thread(self.session.get_kline,
                                             category=self.category,
                                             symbol=symbol,
                                             interval=interval,
                                             limit=limit)
            if klines_response and klines_response.get('retCode') == 0:
                return klines_response
            else:
                logger.warning(f"Failed to get historical klines for {symbol}. API Response: {klines_response.get('retMsg')}")
                return None
        except Exception as e:
            logger.error(f"Error fetching historical klines for {symbol}: {e}", exc_info=True)
            return None

    def get_open_positions_count(self) -> int:
        """Returns the current number of open positions across all symbols."""
        # Counts positions that have a non-zero size
        count = sum(1 for position_data in self.ws_manager.positions.values() if Decimal(position_data.get('size', '0')) != Decimal('0'))
        return count

    async def place_order(self, symbol: str, side: str, order_type: str, qty: Decimal, price: Optional[Decimal] = None, stop_loss_price: Optional[Decimal] = None, take_profit_price: Optional[Decimal] = None, trigger_by: str = "LastPrice", time_in_force: str = "GTC", **kwargs) -> Optional[Dict]:
        """
        Place an order on Bybit.
        """
        if qty <= 0:
            logger.warning(f"Order quantity for {symbol} is zero or negative. Skipping order placement.")
            return None
        if order_type == "Limit" and (price is None or price <= 0):
            logger.warning(f"Limit order for {symbol} requires a valid price. Skipping order placement.")
            return None

        # Check against max open positions limit
        current_open_positions = self.get_open_positions_count()
        if current_open_positions >= self.max_open_positions:
            logger.warning(f"Max open positions ({self.max_open_positions}) reached. Cannot place new order for {symbol}.")
            return None
        
        # Round quantities and prices according to symbol specifications
        qty = self._round_to_qty_step(symbol, qty)
        if qty <= 0: # After rounding, quantity might become zero
            logger.warning(f"Rounded quantity for {symbol} is zero. Skipping order placement.")
            return None
            
        if price is not None:
            price = self._round_to_tick_size(symbol, price)
        if stop_loss_price is not None:
            stop_loss_price = self._round_to_tick_size(symbol, stop_loss_price)
        if take_profit_price is not None:
            take_profit_price = self._round_to_tick_size(symbol, take_profit_price)

        try:
            params = {
                "category": self.category,
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                "timeInForce": time_in_force,
                **kwargs
            }
            if price is not None:
                params["price"] = str(price)
            if stop_loss_price is not None:
                params["stopLoss"] = str(stop_loss_price)
                params["triggerBy"] = trigger_by # Only applicable if stopLoss is set
            if take_profit_price is not None:
                params["takeProfit"] = str(take_profit_price)

            # Improvement 29: Wrapped sync call in to_thread for true async
            order_response = await asyncio.to_thread(self.session.place_order, **params)

            if order_response and order_response.get('retCode') == 0:
                order_result = order_response.get('result', {})
                logger.info(f"Order placed successfully for {symbol}: OrderID={order_result.get('orderId')}, Type={order_type}, Side={side}, Qty={qty}, Price={price if price else 'N/A'}")
                return order_result
            else:
                error_msg = order_response.get('retMsg', 'Unknown error')
                logger.error(f"Failed to place order for {symbol}: {error_msg}")
                send_email_alert("Order Placement Failure", f"For {symbol} ({order_type} {side} {qty}): {error_msg}")
                return None
        except Exception as e:
            logger.error(f"Exception occurred while placing order for {symbol}: {e}", exc_info=True)
            return None

    async def cancel_order(self, symbol: str, order_id: Optional[str] = None, order_link_id: Optional[str] = None) -> bool:
        """Cancel an order by orderId or orderLinkId."""
        if order_id is None and order_link_id is None:
            logger.warning(f"Cannot cancel order for {symbol}: No orderId or orderLinkId provided.")
            return False
        
        try:
            params = {"category": self.category, "symbol": symbol}
            if order_id:
                params["orderId"] = order_id
            elif order_link_id:
                params["orderLinkId"] = order_link_id
            
            # Improvement 30: Wrapped in to_thread
            cancel_response = await asyncio.to_thread(self.session.cancel_order, **params)
            
            if cancel_response and cancel_response.get('retCode') == 0:
                logger.info(f"Order cancelled successfully for {symbol} (ID: {order_id or order_link_id}).")
                return True
            else:
                error_msg = cancel_response.get('retMsg', 'Unknown error')
                logger.error(f"Failed to cancel order for {symbol} (ID: {order_id or order_link_id}): {error_msg}")
                return False
        except Exception as e:
            logger.error(f"Exception occurred while cancelling order for {symbol} (ID: {order_id or order_link_id}): {e}", exc_info=True)
            return False

    # Improvement 31: Added method to cancel all open orders for a symbol
    async def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all open orders for a specific symbol."""
        try:
            response = await asyncio.to_thread(self.session.cancel_all_orders, category=self.category, symbol=symbol)
            if response and response.get('retCode') == 0:
                logger.info(f"All open orders cancelled for {symbol}.")
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error')
                logger.error(f"Failed to cancel all orders for {symbol}: {error_msg}")
                return False
        except Exception as e:
            logger.error(f"Exception occurred while cancelling all orders for {symbol}: {e}", exc_info=True)
            return False

    async def log_current_pnl(self):
        """Logs the current unrealized PnL from all open positions."""
        total_unrealized_pnl = Decimal('0')
        has_pnl_data = False
        for symbol, position_data in self.ws_manager.positions.items():
            # Ensure position_data is a dict and has 'unrealisedPnl'
            if isinstance(position_data, dict) and 'unrealisedPnl' in position_data:
                try:
                    unrealized_pnl = Decimal(position_data.get('unrealisedPnl', '0'))
                    if unrealized_pnl != Decimal('0'):
                        total_unrealized_pnl += unrealized_pnl
                        logger.info(f"Unrealized PnL for {symbol}: {unrealized_pnl:.4f}")
                        has_pnl_data = True
                except Exception as e:
                    logger.error(f"Error processing PnL for {symbol}: {e}", exc_info=True)
        
        if has_pnl_data:
            logger.info(f"Total Unrealized PnL: {total_unrealized_pnl:.4f}")
            # Improvement 32: Alert if PNL drops below threshold
            pnl_threshold_str = config.get("PNL_ALERT_THRESHOLD", "-100")
            try:
                pnl_threshold = Decimal(pnl_threshold_str)
                if total_unrealized_pnl < pnl_threshold:
                    logger.warning(f"Total PNL ({total_unrealized_pnl:.4f}) is below threshold ({pnl_threshold:.4f}). Sending alert.")
                    send_email_alert("PNL Alert", f"Total PNL dropped below threshold to {total_unrealized_pnl:.4f}")
            except Exception as e:
                logger.error(f"Invalid PNL_ALERT_THRESHOLD configuration: {pnl_threshold_str}. Error: {e}")

    async def _check_ws_connection(self, symbols: List[str]):
        """Periodically checks WebSocket connection status and attempts re-subscription."""
        # Check if either public or private WS is disconnected
        if not self.ws_manager.is_public_connected() or not self.ws_manager.is_private_connected():
            logger.warning("WebSocket disconnected. Attempting reconnect...")
            await self.ws_manager.reconnect(symbols)

    # Improvement 33: Added method to close all positions
    async def close_all_positions(self, symbols: List[str]):
        """Closes all open positions for the given symbols."""
        logger.info("Closing all open positions...")
        for symbol in symbols:
            position = self.ws_manager.positions.get(symbol, {})
            size = Decimal(position.get('size', '0'))
            side = position.get('side')
            
            if size > 0:
                close_side = "Sell" if side == "Buy" else "Buy"
                logger.info(f"Closing {side} position for {symbol} with size {size}...")
                try:
                    await self.place_order(symbol, close_side, "Market", size.abs())
                    # Give a small delay for the order to be processed
                    await asyncio.sleep(0.5) 
                except Exception as e:
                    logger.error(f"Error closing position for {symbol}: {e}", exc_info=True)
                    send_email_alert("Position Close Error", f"Error closing position for {symbol}: {e}")
            else:
                logger.debug(f"No open position found for {symbol} to close.")
        logger.info("Finished closing all open positions.")

    async def run(self, symbols: List[str], interval: int = 5):
        """Main bot execution loop."""
        if not self.strategy:
            logger.error("No trading strategy set. Bot cannot run.")
            return

        self.ws_manager.start()
        
        # Initial subscriptions
        await self.ws_manager.subscribe_public_channels(symbols)
        await self.ws_manager.subscribe_private_channels()

        # Fetch initial symbol info
        await self.fetch_symbol_info(symbols)

        logger.info("Bot starting main loop...")
        try:
            while True:
                # Check and attempt to reconnect WebSocket if necessary
                await self._check_ws_connection(symbols)

                current_market_data: Dict[str, Any] = {}
                for symbol in symbols:
                    # Fetch market data for each symbol
                    market_data_for_symbol = await self.get_market_data(symbol)
                    if market_data_for_symbol:
                        current_market_data[symbol] = market_data_for_symbol
                    else:
                        logger.warning(f"Could not retrieve market data for {symbol}. Skipping strategy execution for this symbol.")
                
                # Fetch account information
                account_info = await self.get_account_info()

                # Proceed only if we have market data and account info
                if not current_market_data or not account_info:
                    logger.warning("Missing market data or account info. Waiting for next cycle.")
                    await asyncio.sleep(interval) # Wait before next attempt
                    continue

                # Execute the trading strategy
                await self.strategy(current_market_data, account_info, self.session, self, symbols)

                # Log current PnL
                await self.log_current_pnl()

                # Improvement 34: Added random jitter to interval for anti-pattern detection
                sleep_duration = interval + random.uniform(-1, 1)
                if sleep_duration < 1: sleep_duration = 1 # Ensure minimum sleep time
                await asyncio.sleep(sleep_duration)

        except KeyboardInterrupt:
            logger.info("Bot stopped by user (KeyboardInterrupt).")
        except Exception as e:
            logger.critical(f"Unhandled critical error in main loop: {e}", exc_info=True)
            send_email_alert("Critical Bot Error", f"An unhandled critical error occurred:\n{traceback.format_exc()}")
        finally:
            # Improvement 50: Enhanced shutdown logic to cancel all orders before closing positions.
            logger.info("Initiating shutdown sequence...")
            for symbol in symbols:
                await self.cancel_all_orders(symbol)
            await self.close_all_positions(symbols)
            self.ws_manager.stop()
            logger.info("Bot gracefully shut down.")

# --- Main Execution ---
async def main():
    if not API_KEY or not API_SECRET:
        logger.error("API credentials (BYBIT_API_KEY, BYBIT_API_SECRET) are missing. Please set them in environment variables or bot_config.yaml.")
        return

    bot = BybitTradingBot(api_key=API_KEY, api_secret=API_SECRET, testnet=USE_TESTNET)
    
    symbols_to_trade = config.get("SYMBOLS", ["BTCUSDT", "ETHUSDT"])  # Improvement 36: Configurable symbols
    if not symbols_to_trade:
        logger.error("No trading symbols configured in SYMBOLS. Please add symbols to bot_config.yaml or environment variables.")
        return

    try:
        # Dynamically import the strategy
        from market_making_strategy import market_making_strategy
        bot.set_strategy(market_making_strategy)
        logger.info("Market making strategy loaded successfully.")
    except ImportError:
        logger.error("Failed to import 'market_making_strategy'. Ensure 'market_making_strategy.py' is in the same directory and correctly named.")
        return
    except Exception as e:
        logger.error(f"An error occurred during strategy import: {e}", exc_info=True)
        return

    # Improvement 37: Added configurable interval
    interval = config.get("INTERVAL", 5)
    if not isinstance(interval, int) or interval <= 0:
        logger.warning(f"Invalid INTERVAL configuration: {interval}. Using default of 5 seconds.")
        interval = 5

    await bot.run(symbols=symbols_to_trade, interval=interval)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot terminated by user.")
    except Exception as e:
        logger.critical(f"Unhandled error during asyncio run: {e}", exc_info=True)
EOF

if [ $? -ne 0 ]; then
    echo "Error: Failed to create bybit_bot.py. Exiting."
    exit 1
fi

# Create market_making_strategy.py
echo "Creating market_making_strategy.py..."
cat << 'EOF' > market_making_strategy.py
# market_making_strategy.py

import logging
import time
from datetime import datetime
from typing import Dict, List, Any
from pybit.unified_trading import HTTP
from decimal import Decimal
import numpy as np  # Improvement 38: Added numpy for volatility calculation

logger = logging.getLogger(__name__)

async def market_making_strategy(
    market_data: Dict[str, Any],
    account_info: Dict[str, Any],
    http_client: HTTP, # Note: http_client is passed but not used directly here, bot_instance has it.
    bot_instance: Any,
    symbols: List[str]
):
    """
    Enhanced market-making strategy with volatility adjustment, inventory management, and order cancellation.
    """
    logger.info("-" * 50)
    logger.info(f"Executing Market Making Strategy at {datetime.now()}")

    # Log base currency balance
    base_currency = bot_instance.base_currency
    for wallet_entry in account_info.get('list', []):
        for coin_info in wallet_entry.get('coin', []):
            if coin_info.get('coin') == base_currency:
                logger.info(f"{base_currency} Balance: Available={coin_info.get('availableToWithdraw')}, Total={coin_info.get('walletBalance')}")
                break # Found the base currency in this wallet

    for symbol in symbols:
        logger.info(f"Processing symbol: {symbol}")

        symbol_market_data = market_data.get(symbol)
        if not symbol_market_data:
            logger.warning(f"  No market data available for {symbol}. Skipping.")
            continue

        orderbook = symbol_market_data.get("orderbook", {})
        ticker = symbol_market_data.get("ticker", {})
        
        # Safely get best bid and ask prices from orderbook
        bids = orderbook.get('b', [])
        asks = orderbook.get('a', [])

        best_bid_price = Decimal('0')
        if bids and isinstance(bids, list) and len(bids) > 0 and isinstance(bids[0], list) and len(bids[0]) > 0:
            best_bid_price = Decimal(bids[0][0])

        best_ask_price = Decimal('0')
        if asks and isinstance(asks, list) and len(asks) > 0 and isinstance(asks[0], list) and len(asks[0]) > 0:
            best_ask_price = Decimal(asks[0][0])

        last_price = Decimal(ticker.get('lastPrice', '0')) if ticker else Decimal('0')

        logger.info(f"  {symbol} - Last Price: {last_price}, Best Bid: {best_bid_price}, Best Ask: {best_ask_price}")

        # Get current position details from WS manager
        position_data = bot_instance.ws_manager.positions.get(symbol, {})
        current_position_size = Decimal(position_data.get('size', '0'))
        position_side = position_data.get('side', 'None')
        logger.info(f"  Current position for {symbol}: {position_side} {current_position_size}")

        # Improvement 39: Fetch historical klines for volatility calculation
        klines_data = await bot_instance.get_historical_klines(symbol, "1", limit=100) # 1 minute interval
        volatility = Decimal('0.01') # Default volatility
        if klines_data and klines_data.get('result', {}).get('list'):
            # Extract closing prices from klines
            closes = [Decimal(k[4]) for k in klines_data.get('result', {}).get('list', []) if len(k) > 4]
            if len(closes) > 1:
                # Calculate percentage returns
                returns = np.diff([float(c) for c in closes]) / [float(c) for c in closes[:-1]]
                # Calculate volatility as standard deviation of returns
                volatility = Decimal(np.std(returns))
                logger.info(f"  Volatility for {symbol}: {volatility:.4f}")
            else:
                logger.warning(f"  Not enough kline data for {symbol} to calculate volatility.")
        else:
            logger.warning(f"  Failed to fetch klines for {symbol}. Using default volatility.")

        # Improvement 40: Dynamic spread based on volatility
        base_spread = Decimal('0.001')  # Base spread of 0.1%
        # Scale spread: increase spread for higher volatility
        # The multiplier '10' is a tuning parameter. Adjust as needed.
        adjusted_spread = base_spread * (Decimal('1') + volatility * Decimal('10')) 

        # Improvement 41: Inventory management - skew prices based on position
        inventory_skew = Decimal('0')
        max_inventory_units = Decimal(config.get("MAX_INVENTORY_UNITS", "10")) # Example max units, configurable
        
        if current_position_size > 0: # If long position
            # Skew ask price lower, bid price higher to encourage closing long positions
            inventory_skew = (current_position_size / max_inventory_units) * adjusted_spread 
        elif current_position_size < 0: # If short position
            # Skew bid price higher, ask price lower to encourage closing short positions
            inventory_skew = (current_position_size / max_inventory_units) * adjusted_spread 

        # Check if we are within inventory limits and have valid bid/ask prices
        if current_position_size.abs() < max_inventory_units and best_bid_price > 0 and best_ask_price > 0:
            # Check if bot is below max open positions limit
            if bot_instance.get_open_positions_count() < bot_instance.max_open_positions:
                # Define capital percentage for each order (small for market making)
                capital_percentage_per_order = Decimal(config.get("ORDER_CAPITAL_PERCENTAGE", "0.0001")) # e.g., 0.01% of capital per order
                
                # Calculate buy quantity
                buy_qty = await bot_instance.calculate_position_size(symbol, float(capital_percentage_per_order), best_bid_price, account_info)
                
                if buy_qty > 0:
                    # Improvement 42: Adjusted buy price with spread and skew
                    # Place buy order slightly below best bid, adjusted by spread and inventory skew
                    limit_buy_price = bot_instance._round_to_tick_size(symbol, best_bid_price * (Decimal('1') - adjusted_spread - inventory_skew))
                    
                    # Ensure the buy price is not zero or negative after adjustments
                    if limit_buy_price > 0:
                        logger.info(f"  Attempting to place BUY order for {symbol}: Qty={buy_qty}, Price={limit_buy_price}")
                        # Improvement 43: Added SL and TP
                        # Set stop loss and take profit prices
                        stop_loss_buy = limit_buy_price * Decimal('0.98') # 2% stop loss
                        take_profit_buy = limit_buy_price * Decimal('1.02') # 2% take profit
                        
                        buy_order_response = await bot_instance.place_order(
                            symbol=symbol,
                            side="Buy",
                            order_type="Limit",
                            qty=buy_qty,
                            price=limit_buy_price,
                            time_in_force="GTC", # Good Till Cancelled
                            orderLinkId=f"mm_buy_{int(time.time() * 1000)}_{symbol}", # Unique order link ID
                            stop_loss_price=stop_loss_buy,
                            take_profit_price=take_profit_buy
                        )
                        if buy_order_response:
                            logger.info(f"  Placed BUY order: {buy_order_response.get('orderId')}")
                    else:
                        logger.warning(f"  Calculated limit buy price for {symbol} is invalid ({limit_buy_price}). Skipping BUY order.")
                else:
                    logger.info(f"  Buy quantity for {symbol} is too small. Skipping.")

                # Calculate sell quantity
                sell_qty = await bot_instance.calculate_position_size(symbol, float(capital_percentage_per_order), best_ask_price, account_info)
                
                if sell_qty > 0:
                    # Place sell order slightly above best ask, adjusted by spread and inventory skew
                    limit_sell_price = bot_instance._round_to_tick_size(symbol, best_ask_price * (Decimal('1') + adjusted_spread + inventory_skew))
                    
                    # Ensure the sell price is not zero or negative after adjustments
                    if limit_sell_price > 0:
                        logger.info(f"  Attempting to place SELL order for {symbol}: Qty={sell_qty}, Price={limit_sell_price}")
                        # Set stop loss and take profit prices
                        stop_loss_sell = limit_sell_price * Decimal('1.02') # 2% stop loss
                        take_profit_sell = limit_sell_price * Decimal('0.98') # 2% take profit
                        
                        sell_order_response = await bot_instance.place_order(
                            symbol=symbol,
                            side="Sell",
                            order_type="Limit",
                            qty=sell_qty,
                            price=limit_sell_price,
                            time_in_force="GTC",
                            orderLinkId=f"mm_sell_{int(time.time() * 1000)}_{symbol}",
                            stop_loss_price=stop_loss_sell,
                            take_profit_price=take_profit_sell
                        )
                        if sell_order_response:
                            logger.info(f"  Placed SELL order: {sell_order_response.get('orderId')}")
                    else:
                        logger.warning(f"  Calculated limit sell price for {symbol} is invalid ({limit_sell_price}). Skipping SELL order.")
                else:
                    logger.info(f"  Sell quantity for {symbol} is too small. Skipping.")
            else:
                logger.info(f"  Max open positions ({bot_instance.max_open_positions}) reached. Not placing new orders for {symbol}.")
        
        # Improvement 44: Close position if inventory exceeds limit
        elif current_position_size.abs() >= max_inventory_units:
            logger.warning(f"  Inventory limit reached for {symbol} (Current: {current_position_size.abs()}, Limit: {max_inventory_units}). Closing position.")
            close_side = "Sell" if position_side == "Buy" else "Buy"
            # Use market order to close position quickly
            await bot_instance.place_order(symbol, close_side, "Market", current_position_size.abs())

        # Improvement 45: Cancel stale orders older than 60 seconds
        current_time_ms = int(time.time() * 1000)
        stale_order_threshold_ms = 60000 # 60 seconds
        
        # Iterate over a copy of the orders dictionary to allow modification during iteration
        for order_id, order in list(bot_instance.ws_manager.orders.items()):
            # Check if order is still active ('New' status) and if it's stale
            if order.get('orderStatus') == "New":
                try:
                    order_creation_time_ms = int(order.get('createdTime', 0))
                    if current_time_ms - order_creation_time_ms > stale_order_threshold_ms:
                        logger.info(f"  Cancelling stale order {order_id} for {symbol} (Created: {datetime.fromtimestamp(order_creation_time_ms/1000)})")
                        await bot_instance.cancel_order(symbol, order_id=order_id)
                except Exception as e:
                    logger.error(f"  Error processing stale order {order_id} for {symbol}: {e}", exc_info=True)

    logger.info("-" * 50)
EOF

if [ $? -ne 0 ]; then
    echo "Error: Failed to create market_making_strategy.py. Exiting."
    exit 1
fi

# Create bot_config.yaml
echo "Creating bot_config.yaml..."
cat << 'EOF' > bot_config.yaml
# bot_config.yaml

# --- Bybit API Credentials ---
# IMPORTANT: Replace with your actual API Key and Secret.
# It is highly recommended to use environment variables for security.
# If BYBIT_API_KEY/BYBIT_API_SECRET are set in your environment, they will be used.
BYBIT_API_KEY: "YOUR_BYBIT_API_KEY"
BYBIT_API_SECRET: "YOUR_BYBIT_API_SECRET"

# --- Trading Settings ---
# Set to true to use the Bybit Testnet, false for the live Bybit trading environment.
BYBIT_USE_TESTNET: true

# The trading category (e.g., 'linear', 'inverse', 'spot'). 'linear' is common for perpetual futures.
CATEGORY: linear

# The base currency for calculations and balance checks (e.g., USDT, USDC).
BASE_CURRENCY: USDT

# List of symbols to trade (e.g., BTCUSDT, ETHUSDT).
SYMBOLS: ["BTCUSDT", "ETHUSDT"]

# The main loop interval in seconds. Affects how often the strategy is re-evaluated.
INTERVAL: 5

# Maximum number of open positions the bot will manage across all symbols.
MAX_OPEN_POSITIONS: 10

# --- Strategy Specific Configurations ---
# Maximum units of a single asset the bot will hold in inventory before attempting to close.
MAX_INVENTORY_UNITS: 15

# Percentage of available capital to risk per order. e.g., 0.0001 for 0.01%.
ORDER_CAPITAL_PERCENTAGE: 0.00005

# --- Alerting ---
# Enable or disable email alerts.
EMAIL_ALERTS: false

# Email server configuration for sending alerts.
EMAIL_SERVER:
  host: "smtp.example.com" # e.g., smtp.gmail.com
  port: 587
  user: "your_email@example.com"
  pass: "your_email_password_or_app_password"
  from: "bot_sender@example.com" # Must match the 'user' or be allowed by the SMTP server
  to: "alert_recipient@example.com"

# PNL Alerting
# Alert when total unrealized PnL drops below this threshold. Set to a very low number to disable.
PNL_ALERT_THRESHOLD: -50

# --- Advanced Settings ---
# Maximum number of retries for API calls before failing.
MAX_RETRIES: 5
EOF

if [ $? -ne 0 ]; then
    echo "Error: Failed to create bot_config.yaml. Exiting."
    exit 1
fi

# --- Step 3: Provide Instructions ---
echo ""
echo "---------------------------------------------------------------------"
echo "Project setup complete! Files have been created in: $(pwd)"
echo "---------------------------------------------------------------------"
echo ""
echo "Next Steps:"
echo "1.  **Configure API Keys and Settings:**"
echo "    - Open the 'bot_config.yaml' file in this directory."
echo "    - Replace 'YOUR_BYBIT_API_KEY' and 'YOUR_BYBIT_API_SECRET' with your actual Bybit API credentials."
echo "    - If using testnet, ensure 'BYBIT_USE_TESTNET: true'."
echo "    - Adjust 'SYMBOLS', 'INTERVAL', 'MAX_OPEN_POSITIONS', and other settings as needed."
echo "    - For email alerts, configure 'EMAIL_ALERTS: true' and fill in your 'EMAIL_SERVER' details."
echo ""
echo "2.  **Install Dependencies:**"
echo "    - Make sure you have Python 3.7+ and pip installed."
echo "    - Run the following command in your terminal (from outside this project directory or within it):"
echo "      pip install pybit-unified-trading numpy pyyaml"
echo ""
echo "3.  **Run the Bot:**"
echo "    - Navigate to the project directory in your terminal:"
echo "      cd $PROJECT_NAME"
echo "    - Execute the bot script:"
echo "      python bybit_bot.py"
echo ""
echo "---------------------------------------------------------------------"
echo "Remember to keep your API keys secure and never share them publicly."
echo "---------------------------------------------------------------------"

exit 0
