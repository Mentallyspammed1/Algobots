Okay, let's turn your script into a more robust, fully functional, and enhanced Bybit trading bot.

Here's a breakdown of the enhancements and upgrades:

1.  **Fix Duplicate `fetch_symbol_info`:** Removed the redundant definitions.
2.  **Consistent Decimal Usage:** Ensured all financial calculations and quantities use `Decimal` for precision, especially in `calculate_position_size` and `place_order`. The `place_order` method now accepts `Decimal` and converts to `str` for the API call.
3.  **Helper Functions for Precision:** Added `_round_to_qty_step` and `_round_to_tick_size` to ensure quantities and prices adhere to Bybit's trading rules.
4.  **Improved WebSocket Management:**
    *   Added `start()` and `stop()` methods to the `BybitWebSocketManager` for explicit connection management.
    *   The `run` method of the bot now explicitly starts and stops the WS manager.
    *   Added `_check_ws_connection` to the bot to ensure WS is alive.
5.  **Enhanced `place_order`:**
    *   Now accepts `Decimal` for `qty`, `price`, `stop_loss_price`, `take_profit_price`.
    *   Includes a check for `max_open_positions` before placing new orders.
    *   Includes a check for `qty > 0` and `price > 0`.
6.  **Robust Error Handling & Logging:** More `try-except` blocks, detailed logging messages, and `exc_info=True` for critical errors.
7.  **Strategy Integration:** The bot is designed to easily plug in different strategies. I've created a placeholder `market_making_strategy.py` file that you'll need to save separately.
8.  **Configuration:** Uses environment variables for API keys and testnet flag.
9.  **Main Loop Refinement:** The `run` method is more robust, handling potential data fetching issues.
10. **Docstrings and Type Hinting:** Added more comprehensive docstrings and type hints for better readability and maintainability.
11. **Asynchronous Considerations:** Added comments about the synchronous nature of `pybit.HTTP` calls within an `async` bot and suggested `asyncio.to_thread` for true non-blocking behavior in a production environment.

---

**Step 1: Save the main bot file**

Save the following code as `bybit_bot.py`:

```python
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

# Set decimal precision for financial calculations
getcontext().prec = 10

# --- Configuration ---
# Load API credentials from environment variables
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
USE_TESTNET = os.getenv("BYBIT_USE_TESTNET", "false").lower() == "true"

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- WebSocket Manager ---
class BybitWebSocketManager:
    """
    Manages WebSocket connections for Bybit public and private streams.
    Stores real-time market data, positions, and orders.
    """
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.ws_public: Optional[WebSocket] = None
        self.ws_private: Optional[WebSocket] = None
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        self.market_data: Dict[str, Any] = {} # Stores orderbook, ticker, last_trade
        self.positions: Dict[str, Any] = {}   # Stores open positions
        self.orders: Dict[str, Any] = {}      # Stores open/recent orders

        self._public_subscriptions: List[str] = []
        self._private_subscriptions: List[str] = []

    def _init_public_ws(self):
        """Initializes the public WebSocket connection if not already active."""
        if not self.ws_public or not self.ws_public.is_connected():
            self.ws_public = WebSocket(
                testnet=self.testnet,
                channel_type="linear" # Or "spot", "inverse" based on needs
            )
            logger.info("Public WebSocket initialized.")

    def _init_private_ws(self):
        """Initializes the private WebSocket connection if not already active."""
        if not self.ws_private or not self.ws_private.is_connected():
            self.ws_private = WebSocket(
                testnet=self.testnet,
                channel_type="private",
                api_key=self.api_key,
                api_secret=self.api_secret,
                recv_window=10000
            )
            logger.info("Private WebSocket initialized.")

    def handle_orderbook(self, message: Dict):
        """Processes orderbook updates and stores the data."""
        try:
            data = message.get("data", {})
            symbol = data.get("s")
            if symbol:
                self.market_data.setdefault(symbol, {})["orderbook"] = data
                self.market_data[symbol]["timestamp"] = message.get("ts")
                # logger.debug(f"Orderbook for {symbol}: Bids: {data.get('b', [])[:1]}, Asks: {data.get('a', [])[:1]}")
        except Exception as e:
            logger.error(f"Error handling orderbook: {e}", exc_info=True)

    def handle_trades(self, message: Dict):
        """Processes trade updates and stores the latest trade."""
        try:
            data = message.get("data", [])
            for trade in data:
                symbol = trade.get("s")
                if symbol:
                    self.market_data.setdefault(symbol, {})["last_trade"] = trade
                    # logger.debug(f"Trade for {symbol}: Price: {trade.get('p')}, Size: {trade.get('v')}")
        except Exception as e:
            logger.error(f"Error handling trades: {e}", exc_info=True)

    def handle_ticker(self, message: Dict):
        """Processes ticker updates and stores the data."""
        try:
            data = message.get("data", {})
            symbol = data.get("s")
            if symbol:
                self.market_data.setdefault(symbol, {})["ticker"] = data
                # logger.debug(f"Ticker for {symbol}: Last Price: {data.get('lastPrice')}")
        except Exception as e:
            logger.error(f"Error handling ticker: {e}", exc_info=True)

    def handle_position(self, message: Dict):
        """Processes position updates and stores them by symbol."""
        try:
            data = message.get("data", [])
            for position in data:
                symbol = position.get("symbol")
                if symbol:
                    self.positions[symbol] = position
                    # logger.debug(f"Position for {symbol}: Side: {position.get('side')}, Size: {position.get('size')}")
        except Exception as e:
            logger.error(f"Error handling position: {e}", exc_info=True)

    def handle_order(self, message: Dict):
        """Processes order updates and stores them by orderId."""
        try:
            data = message.get("data", [])
            for order in data:
                order_id = order.get("orderId")
                if order_id:
                    self.orders[order_id] = order
                    # logger.debug(f"Order update for {order_id}: Status: {order.get('orderStatus')}")
        except Exception as e:
            logger.error(f"Error handling order: {e}", exc_info=True)

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

    async def subscribe_public_channels(self, symbols: List[str], channels: List[str] = ["orderbook", "publicTrade", "tickers"]):
        """Subscribes to public market data channels for specified symbols."""
        self._init_public_ws()
        if not self.ws_public:
            logger.error("Public WebSocket not initialized for subscription.")
            return

        # Add a small delay to allow WebSocket to fully establish before subscribing
        await asyncio.sleep(0.5)

        for symbol in symbols:
            if "orderbook" in channels and f"orderbook.1.{symbol}" not in self._public_subscriptions:
                try:
                    self.ws_public.orderbook_stream(
                        depth=1, # Small depth for quick updates
                        symbol=symbol,
                        callback=self.handle_orderbook
                    )
                    self._public_subscriptions.append(f"orderbook.1.{symbol}")
                    logger.info(f"Subscribed to orderbook.1.{symbol}")
                except Exception as e:
                    logger.error(f"Error subscribing to orderbook for {symbol}: {e}", exc_info=True)
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

    async def subscribe_private_channels(self, channels: List[str] = ["position", "order", "execution", "wallet"]):
        """Subscribes to private account channels."""
        self._init_private_ws()
        if not self.ws_private:
            logger.error("Private WebSocket not initialized for subscription.")
            return

        # Add a small delay to allow WebSocket to fully establish before subscribing
        await asyncio.sleep(0.5)

        if "position" in channels and "position" not in self._private_subscriptions:
            self.ws_private.position_stream(callback=self.handle_position)
            self._private_subscriptions.append("position")
            logger.info("Subscribed to position stream.")
        if "order" in channels and "order" not in self._private_subscriptions:
            self.ws_private.order_stream(callback=self.handle_order)
            self._private_subscriptions.append("order")
            logger.info("Subscribed to order stream.")
        if "execution" in channels and "execution" not in self._private_subscriptions:
            self.ws_private.execution_stream(callback=self.handle_execution)
            self._private_subscriptions.append("execution")
            logger.info("Subscribed to execution stream.")
        if "wallet" in channels and "wallet" not in self._private_subscriptions:
            self.ws_private.wallet_stream(callback=self.handle_wallet)
            self._private_subscriptions.append("wallet")
            logger.info("Subscribed to wallet stream.")

    def start(self):
        """Starts the WebSocket connections."""
        # The actual connection happens when subscribe methods are called.
        # This method is more for conceptual start/stop management.
        logger.info("WebSocket Manager started.")

    def stop(self):
        """Stops and closes all WebSocket connections."""
        if self.ws_public:
            self.ws_public.exit()
            logger.info("Public WebSocket connection closed.")
        if self.ws_private:
            self.ws_private.exit()
            logger.info("Private WebSocket connection closed.")
        logger.info("WebSocket Manager stopped.")

    def is_public_connected(self) -> bool:
        """Checks if the public WebSocket is connected."""
        return self.ws_public is not None and self.ws_public.is_connected()

    def is_private_connected(self) -> bool:
        """Checks if the private WebSocket is connected."""
        return self.ws_private is not None and self.ws_private.is_connected()

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
        self.ws_manager = BybitWebSocketManager(api_key, api_secret, testnet)
        self.strategy: Optional[Callable[[Dict, Dict, HTTP, Any, List[str]], None]] = None # Strategy now accepts bot_instance and symbols
        self.symbol_info: Dict[str, Any] = {} # Stores instrument details for position sizing and precision
        self.max_open_positions: int = 5 # Max number of open positions for risk management
        self.category: str = "linear" # Default trading category

        logger.info(f"Bybit Trading Bot initialized. Testnet: {testnet}, Category: {self.category}")

    async def fetch_symbol_info(self, symbols: List[str]):
        """Fetches and stores instrument details for given symbols."""
        logger.info(f"Fetching instrument info for symbols: {symbols}")
        try:
            for symbol in symbols:
                response = self.session.get_instruments_info(category=self.category, symbol=symbol)
                if response and response['retCode'] == 0:
                    for item in response.get('result', {}).get('list', []):
                        if item.get('symbol') == symbol: # Ensure it's the correct symbol
                            self.symbol_info[symbol] = {
                                "minOrderQty": Decimal(item['lotSizeFilter']['minOrderQty']),
                                "qtyStep": Decimal(item['lotSizeFilter']['qtyStep']),
                                "tickSize": Decimal(item['priceFilter']['tickSize']),
                                "minPrice": Decimal(item['priceFilter']['minPrice']),
                                "maxPrice": Decimal(item['priceFilter']['maxPrice']),
                                "leverageFilter": item.get('leverageFilter', {}) # Store leverage info
                            }
                            logger.info(f"Successfully fetched instrument info for {symbol}.")
                            break
                else:
                    logger.error(f"Failed to fetch instrument info for {symbol}: {response.get('retMsg')}")
        except Exception as e:
            logger.error(f"Error fetching instrument info: {e}", exc_info=True)

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
        qty_step = self.symbol_info[symbol]["qtyStep"]
        return (quantity / qty_step).quantize(Decimal('1')) * qty_step

    def _round_to_tick_size(self, symbol: str, price: Decimal) -> Decimal:
        """Rounds a price to the nearest valid tick size for a given symbol."""
        if symbol not in self.symbol_info:
            logger.warning(f"Symbol info not available for {symbol}. Cannot round price.")
            return price
        tick_size = self.symbol_info[symbol]["tickSize"]
        return price.quantize(tick_size)

    async def get_market_data(self, symbol: str) -> Optional[Dict]:
        """
        Retrieve current market data for a symbol.
        Prioritizes WebSocket data if available and fresh, falls back to REST API.
        """
        # Check WebSocket data first
        ws_data = self.ws_manager.market_data.get(symbol)
        if ws_data and ws_data.get("orderbook") and ws_data.get("ticker"):
            # You might want to add a timestamp check here to ensure data freshness
            # e.g., if (time.time() * 1000 - ws_data.get("timestamp", 0)) < 5000: # data is less than 5 seconds old
            return ws_data
        
        logger.warning(f"WebSocket data for {symbol} not fresh or complete. Falling back to REST API.")
        
        # Fallback to REST API
        try:
            orderbook_resp = self.session.get_orderbook(category=self.category, symbol=symbol)
            ticker_resp = self.session.get_tickers(category=self.category, symbol=symbol)

            if orderbook_resp and orderbook_resp['retCode'] == 0 and ticker_resp and ticker_resp['retCode'] == 0:
                # pybit's get_public_trading_records is often slow or has rate limits,
                # and WS handles trades better. For a quick snapshot, we might skip it.
                # trades_resp = self.session.get_public_trading_records(category=self.category, symbol=symbol, limit=1)
                
                return {
                    "orderbook": orderbook_resp.get('result', {}).get('list', []),
                    "ticker": ticker_resp.get('result', {}).get('list', []),
                    "last_trade": [] # Placeholder if not fetched via REST
                }
            else:
                logger.warning(f"Failed to get market data for {symbol} via REST. Orderbook: {orderbook_resp}, Ticker: {ticker_resp}")
                return None
        except Exception as e:
            logger.error(f"Error fetching market data for {symbol} via REST: {e}", exc_info=True)
            return None

    async def get_account_info(self, account_type: str = "UNIFIED") -> Optional[Dict]:
        """
        Retrieve account balance information.
        Prioritizes WebSocket data if available, falls back to REST API.
        """
        # WebSocket wallet updates are usually just for changes, not a full snapshot.
        # So, REST API is generally preferred for a current balance snapshot.
        try:
            balance = self.session.get_wallet_balance(accountType=account_type)
            if balance and balance['retCode'] == 0:
                return balance.get('result', {})
            else:
                logger.warning(f"Failed to get account balance. Response: {balance.get('retMsg')}")
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
            available_balance_usd = Decimal(0)
            # Assuming 'USDT' as the base currency for calculating capital
            # For UNIFIED account, balance is usually under 'list' -> 'coin'
            for wallet in account_info.get('list', []):
                if wallet.get('coin') == 'USDT': # Adjust coin as per your base currency
                    available_balance_usd = Decimal(wallet.get('availableToWithdraw', '0'))
                    break

            if available_balance_usd <= 0:
                logger.warning("No available balance to calculate position size.")
                return Decimal(0)

            if price <= 0:
                logger.warning("Price must be positive to calculate position size.")
                return Decimal(0)

            target_capital = available_balance_usd * Decimal(str(capital_percentage))
            raw_qty = target_capital / price

            # Round quantity to the nearest qtyStep and ensure it meets minOrderQty
            rounded_qty = self._round_to_qty_step(symbol, raw_qty)
            min_order_qty = self.symbol_info[symbol]["minOrderQty"]

            if rounded_qty < min_order_qty:
                logger.warning(f"Calculated quantity {rounded_qty} is less than min order qty {min_order_qty} for {symbol}. Returning 0.")
                return Decimal(0)

            logger.info(f"Calculated position size for {symbol}: {rounded_qty} (Target Capital: {target_capital:.2f} USDT, Price: {price})")
            return rounded_qty

        except Exception as e:
            logger.error(f"Error calculating position size for {symbol}: {e}", exc_info=True)
            return Decimal(0)

    async def get_historical_klines(self, symbol: str, interval: str, limit: int = 200) -> Optional[Dict]:
        """Retrieve historical candlestick data (Klines)."""
        try:
            klines = self.session.get_kline(
                category=self.category,
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            if klines and klines['retCode'] == 0:
                return klines
            else:
                logger.warning(f"Failed to get historical klines for {symbol} ({interval}). Response: {klines.get('retMsg')}")
                return None
        except Exception as e:
            logger.error(f"Error fetching historical klines for {symbol} ({interval}): {e}", exc_info=True)
            return None

    def get_open_positions_count(self) -> int:
        """Returns the current number of open positions across all symbols."""
        count = 0
        for symbol, position_data in self.ws_manager.positions.items():
            # A position is considered open if size is not zero
            if Decimal(position_data.get('size', '0')) != Decimal('0'):
                count += 1
        return count

    async def place_order(self, symbol: str, side: str, order_type: str, qty: Decimal, price: Optional[Decimal] = None, stop_loss_price: Optional[Decimal] = None, take_profit_price: Optional[Decimal] = None, trigger_by: str = "LastPrice", time_in_force: str = "GTC", **kwargs) -> Optional[Dict]:
        """
        Place an order on Bybit.
        Args:
            symbol (str): Trading pair (e.g., "BTCUSDT").
            side (str): "Buy" or "Sell".
            order_type (str): "Limit", "Market", "PostOnly", etc.
            qty (Decimal): Quantity to trade.
            price (Optional[Decimal]): Price for Limit orders.
            stop_loss_price (Optional[Decimal]): Stop Loss price.
            take_profit_price (Optional[Decimal]): Take Profit price.
            trigger_by (str): Trigger type for stop/take profit orders ("LastPrice", "IndexPrice", "MarkPrice").
            time_in_force (str): "GTC", "IOC", "FOK".
            **kwargs: Additional parameters for the order (e.g., "orderLinkId").
        Returns:
            Optional[Dict]: The order response from Bybit if successful, else None.
        """
        if qty <= 0:
            logger.warning(f"Invalid quantity ({qty}) for order on {symbol}. Must be positive.")
            return None
        if order_type == "Limit" and (price is None or price <= 0):
            logger.warning(f"Price must be positive for Limit order on {symbol}.")
            return None

        # Risk management: Check max open positions for new entries
        current_position = Decimal(self.ws_manager.positions.get(symbol, {}).get('size', '0'))
        if current_position == Decimal('0') and self.get_open_positions_count() >= self.max_open_positions:
            logger.warning(f"Max open positions ({self.max_open_positions}) reached. Not placing new entry order for {symbol}.")
            return None
        
        # Round quantity and price to symbol's precision
        qty = self._round_to_qty_step(symbol, qty)
        if price:
            price = self._round_to_tick_size(symbol, price)
        if stop_loss_price:
            stop_loss_price = self._round_to_tick_size(symbol, stop_loss_price)
        if take_profit_price:
            take_profit_price = self._round_to_tick_size(symbol, take_profit_price)

        try:
            params = {
                "category": self.category,
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty), # Convert Decimal to string for API
                "timeInForce": time_in_force,
                **kwargs
            }
            if price is not None:
                params["price"] = str(price) # Convert Decimal to string for API
            if stop_loss_price is not None:
                params["stopLoss"] = str(stop_loss_price) # Convert Decimal to string for API
                params["triggerBy"] = trigger_by # Apply triggerBy if SL is set
            if take_profit_price is not None:
                params["takeProfit"] = str(take_profit_price) # Convert Decimal to string for API

            # IMPORTANT: pybit's HTTP client methods are synchronous.
            # While this method is `async def`, the actual API call will block the event loop.
            # For high-performance, truly non-blocking behavior, consider using `asyncio.to_thread`
            # or an asynchronous HTTP client wrapper for pybit.
            order_response = self.session.place_order(**params)

            if order_response and order_response['retCode'] == 0:
                logger.info(f"Order placed successfully for {symbol}: {order_response.get('result')}")
                return order_response.get('result')
            else:
                logger.error(f"Failed to place order for {symbol}: {order_response.get('retMsg')}")
                return None
        except Exception as e:
            logger.error(f"Error placing order for {symbol}: {e}", exc_info=True)
            return None

    async def cancel_order(self, symbol: str, order_id: Optional[str] = None, order_link_id: Optional[str] = None) -> bool:
        """Cancel an order by orderId or orderLinkId."""
        try:
            params = {"category": self.category, "symbol": symbol}
            if order_id:
                params["orderId"] = order_id
            elif order_link_id:
                params["orderLinkId"] = order_link_id
            else:
                logger.warning("Either order_id or order_link_id must be provided to cancel an order.")
                return False

            cancel_response = self.session.cancel_order(**params)
            if cancel_response and cancel_response['retCode'] == 0:
                logger.info(f"Order cancelled successfully for {symbol}: {cancel_response.get('result')}")
                return True
            else:
                logger.error(f"Failed to cancel order for {symbol}: {cancel_response.get('retMsg')}")
                return False
        except Exception as e:
            logger.error(f"Error cancelling order for {symbol}: {e}", exc_info=True)
            return False

    async def log_current_pnl(self):
        """Logs the current unrealized PnL from all open positions."""
        total_unrealized_pnl = Decimal('0')
        has_pnl = False
        for symbol, position_data in self.ws_manager.positions.items():
            unrealized_pnl = Decimal(position_data.get('unrealisedPnl', '0'))
            if unrealized_pnl != Decimal('0'):
                total_unrealized_pnl += unrealized_pnl
                logger.info(f"Unrealized PnL for {symbol} ({position_data.get('side')} {position_data.get('size')}): {unrealized_pnl:.4f}")
                has_pnl = True
        if has_pnl:
            logger.info(f"Total Unrealized PnL: {total_unrealized_pnl:.4f}")

    async def _check_ws_connection(self, symbols: List[str]):
        """Periodically checks WebSocket connection status and attempts re-subscription."""
        if not self.ws_manager.is_public_connected():
            logger.warning("Public WebSocket disconnected. Attempting re-subscription...")
            await self.ws_manager.subscribe_public_channels(symbols)
        if not self.ws_manager.is_private_connected():
            logger.warning("Private WebSocket disconnected. Attempting re-subscription...")
            await self.ws_manager.subscribe_private_channels()

    async def run(self, symbols: List[str], interval: int = 5):
        """Main bot execution loop."""
        if not self.strategy:
            logger.error("No trading strategy set. Please call set_strategy() before running the bot.")
            return

        self.ws_manager.start()
        
        # Subscribe to WebSocket streams
        await self.ws_manager.subscribe_public_channels(symbols)
        await self.ws_manager.subscribe_private_channels()

        # Fetch symbol information for position sizing and precision
        await self.fetch_symbol_info(symbols)

        logger.info("Bot starting main loop...")
        try:
            while True:
                await self._check_ws_connection(symbols) # Ensure WS connections are alive

                # Fetch latest market data and account info
                # Prioritize WS data where available and fresh
                current_market_data: Dict[str, Any] = {}
                for symbol in symbols:
                    # Get from WS manager first, if not available or not fresh, get from REST
                    ws_md = self.ws_manager.market_data.get(symbol)
                    if ws_md and ws_md.get("orderbook") and ws_md.get("ticker"):
                        current_market_data[symbol] = ws_md
                    else:
                        rest_md = await self.get_market_data(symbol)
                        if rest_md:
                            current_market_data[symbol] = rest_md
                        else:
                            logger.warning(f"Could not get market data for {symbol} from WS or REST.")

                account_info = await self.get_account_info()

                if not current_market_data or not account_info:
                    logger.warning("Skipping strategy execution due to missing market or account data. Retrying in next interval.")
                    await asyncio.sleep(interval)
                    continue

                # Execute the plugged-in strategy
                # The strategy function will receive live data, account info, the HTTP client, and the bot instance
                await self.strategy(current_market_data, account_info, self.session, self, symbols)

                # Log current PnL
                await self.log_current_pnl()

                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            logger.info("Bot stopped by user (KeyboardInterrupt).")
        except Exception as e:
            logger.critical(f"An unhandled error occurred in main bot loop: {e}", exc_info=True)
        finally:
            self.ws_manager.stop()
            logger.info("Bot gracefully shut down.")

# --- Main Execution ---
async def main():
    # Ensure API_KEY and API_SECRET are set
    if not API_KEY or not API_SECRET:
        logger.error("BYBIT_API_KEY and BYBIT_API_SECRET environment variables must be set.")
        logger.error("Please set them: export BYBIT_API_KEY='your_key' && export BYBIT_API_SECRET='your_secret'")
        return

    bot = BybitTradingBot(api_key=API_KEY, api_secret=API_SECRET, testnet=USE_TESTNET)
    
    # Define symbols to trade
    # IMPORTANT: Ensure these symbols are available on Bybit for the 'linear' category
    symbols_to_trade = ["BTCUSDT", "ETHUSDT"] # Example symbols

    # Plug in your strategy here
    # You need to create a market_making_strategy.py file (see Step 2)
    try:
        from market_making_strategy import market_making_strategy
        bot.set_strategy(market_making_strategy)
    except ImportError:
        logger.error("Could not import 'market_making_strategy'. Please ensure 'market_making_strategy.py' is in the same directory.")
        logger.error("The bot will run but no strategy will be executed.")
        # As a fallback, you could set a dummy strategy or exit
        return

    # Run the bot
    await bot.run(symbols=symbols_to_trade, interval=5) # Check every 5 seconds

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot process terminated by user.")
    except Exception as e:
        logger.critical(f"An unhandled error occurred during bot startup or execution: {e}", exc_info=True)

```

---

**Step 2: Create the Strategy File**

Save the following code as `market_making_strategy.py` in the **same directory** as `bybit_bot.py`.

This is a **very basic placeholder strategy**. A real market-making strategy would involve:
*   Calculating bid/ask spreads.
*   Placing limit orders on both sides of the order book.
*   Adjusting orders based on market movement.
*   Managing inventory risk.
*   Handling order fills and cancellations.

```python
# market_making_strategy.py

import logging
from typing import Dict, List, Any
from pybit.unified_trading import HTTP
from decimal import Decimal

logger = logging.getLogger(__name__)

async def market_making_strategy(
    market_data: Dict[str, Any],
    account_info: Dict[str, Any],
    http_client: HTTP,
    bot_instance: Any, # Type hint as Any to avoid circular imports with BybitTradingBot
    symbols: List[str]
):
    """
    A placeholder market-making strategy.
    This strategy will simply log data and attempt to place a small limit order
    for demonstration purposes if certain conditions are met.
    It does NOT implement a full market-making logic.

    Args:
        market_data (Dict[str, Any]): Current market data from WebSocket/REST.
        account_info (Dict[str, Any]): Current account balance and info.
        http_client (HTTP): The Pybit HTTP client for direct API calls.
        bot_instance (Any): The BybitTradingBot instance, allowing access to its methods (e.g., place_order).
        symbols (List[str]): List of symbols the bot is configured to trade.
    """
    logger.info("-" * 50)
    logger.info(f"Executing Market Making Strategy at {datetime.now()}")

    # Example: Log account balance
    for wallet in account_info.get('list', []):
        if wallet.get('coin') == 'USDT':
            logger.info(f"USDT Balance: Available={wallet.get('availableToWithdraw')}, Total={wallet.get('walletBalance')}")
            break

    for symbol in symbols:
        logger.info(f"Processing symbol: {symbol}")

        # Get market data for the current symbol
        symbol_market_data = market_data.get(symbol)
        if not symbol_market_data:
            logger.warning(f"No market data available for {symbol}. Skipping strategy for this symbol.")
            continue

        # Extract relevant data from WebSocket/REST
        orderbook = symbol_market_data.get("orderbook", {})
        ticker = symbol_market_data.get("ticker", {})
        
        best_bid_price = Decimal(orderbook.get('b', [['0']])[0][0]) if orderbook.get('b') else Decimal('0')
        best_ask_price = Decimal(orderbook.get('a', [['0']])[0][0]) if orderbook.get('a') else Decimal('0')
        last_price = Decimal(ticker.get('lastPrice', '0')) if ticker else Decimal('0')

        logger.info(f"  {symbol} - Last Price: {last_price}, Best Bid: {best_bid_price}, Best Ask: {best_ask_price}")

        # Get current position for the symbol
        current_position = Decimal(bot_instance.ws_manager.positions.get(symbol, {}).get('size', '0'))
        position_side = bot_instance.ws_manager.positions.get(symbol, {}).get('side', 'None')
        logger.info(f"  Current position for {symbol}: {position_side} {current_position}")

        # --- Simple Market Making Logic (Placeholder) ---
        # This is a very simplified example. A real MM strategy is much more complex.

        # Conditions for placing new orders:
        # 1. No open position for this symbol (or very small to allow for scaling)
        # 2. Valid bid/ask prices are available
        # 3. Bot is not at max open positions
        
        if current_position == Decimal('0') and best_bid_price > 0 and best_ask_price > 0:
            if bot_instance.get_open_positions_count() < bot_instance.max_open_positions:
                # Calculate a small order quantity (e.g., 0.01% of available capital)
                # This is just for testing, use proper risk management in production!
                capital_to_use_percentage = 0.0001 # 0.01% of available capital for a small test order
                
                # Calculate quantity for a buy order at the bid price
                buy_qty = await bot_instance.calculate_position_size(
                    symbol=symbol,
                    capital_percentage=capital_to_use_percentage,
                    price=best_bid_price,
                    account_info=account_info
                )
                
                # Calculate quantity for a sell order at the ask price
                sell_qty = await bot_instance.calculate_position_size(
                    symbol=symbol,
                    capital_percentage=capital_to_use_percentage,
                    price=best_ask_price,
                    account_info=account_info
                )

                # Ensure quantities are valid and meet min order requirements
                if buy_qty > 0:
                    # Place a limit buy order slightly below the best bid
                    limit_buy_price = bot_instance._round_to_tick_size(symbol, best_bid_price * Decimal('0.999')) # 0.1% below bid
                    
                    logger.info(f"  Attempting to place BUY order for {symbol}: Qty={buy_qty}, Price={limit_buy_price}")
                    buy_order_response = await bot_instance.place_order(
                        symbol=symbol,
                        side="Buy",
                        order_type="Limit",
                        qty=buy_qty,
                        price=limit_buy_price,
                        time_in_force="GTC",
                        orderLinkId=f"mm_buy_{int(time.time() * 1000)}" # Unique ID
                    )
                    if buy_order_response:
                        logger.info(f"  Placed BUY order: {buy_order_response.get('orderId')}")
                    else:
                        logger.warning(f"  Failed to place BUY order for {symbol}.")
                else:
                    logger.info(f"  Buy quantity for {symbol} is zero or too small ({buy_qty}). Skipping buy order.")

                if sell_qty > 0:
                    # Place a limit sell order slightly above the best ask
                    limit_sell_price = bot_instance._round_to_tick_size(symbol, best_ask_price * Decimal('1.001')) # 0.1% above ask
                    
                    logger.info(f"  Attempting to place SELL order for {symbol}: Qty={sell_qty}, Price={limit_sell_price}")
                    sell_order_response = await bot_instance.place_order(
                        symbol=symbol,
                        side="Sell",
                        order_type="Limit",
                        qty=sell_qty,
                        price=limit_sell_price,
                        time_in_force="GTC",
                        orderLinkId=f"mm_sell_{int(time.time() * 1000)}" # Unique ID
                    )
                    if sell_order_response:
                        logger.info(f"  Placed SELL order: {sell_order_response.get('orderId')}")
                    else:
                        logger.warning(f"  Failed to place SELL order for {symbol}.")
                else:
                    logger.info(f"  Sell quantity for {symbol} is zero or too small ({sell_qty}). Skipping sell order.")
            else:
                logger.info(f"  Max open positions reached ({bot_instance.max_open_positions}). Not placing new orders for {symbol}.")
        elif current_position != Decimal('0'):
            logger.info(f"  Position already open for {symbol}. Not placing new entry orders.")
            # In a real MM strategy, you'd manage this position (e.g., close it, adjust orders)
            # Example: If you have a long position, you might place a sell order to close it.
            # if position_side == "Long":
            #     await bot_instance.place_order(symbol=symbol, side="Sell", order_type="Market", qty=current_position)
            #     logger.info(f"  Attempted to close long position for {symbol} with Market Sell.")

    logger.info("-" * 50)

```

---

**Step 3: Set up Environment Variables**

Before running the bot, you need to set your Bybit API Key and Secret as environment variables.
Also, decide if you want to use the testnet.

**For Linux/macOS:**
```bash
export BYBIT_API_KEY="YOUR_API_KEY"
export BYBIT_API_SECRET="YOUR_API_SECRET"
export BYBIT_USE_TESTNET="true" # Set to "false" for live trading
```

**For Windows (Command Prompt):**
```cmd
set BYBIT_API_KEY="YOUR_API_KEY"
set BYBIT_API_SECRET="YOUR_API_SECRET"
set BYBIT_USE_TESTNET="true"
```

**For Windows (PowerShell):**
```powershell
$env:BYBIT_API_KEY="YOUR_API_KEY"
$env:BYBIT_API_SECRET="YOUR_API_SECRET"
$env:BYBIT_USE_TESTNET="true"
```

Replace `YOUR_API_KEY` and `YOUR_API_SECRET` with your actual Bybit API credentials.
**Always use the testnet first** to ensure your bot works as expected without risking real funds.

---

**Step 4: Install Dependencies**

Make sure you have `pybit` and `python-dotenv` (optional, but good for local development) installed:

```bash
pip install pybit-unified-trading
```

---

**Step 5: Run the Bot**

Navigate to the directory where you saved `bybit_bot.py` and `market_making_strategy.py` in your terminal and run:

```bash
python bybit_bot.py
```

You should see log messages indicating the bot's initialization, WebSocket subscriptions, market data fetching, and strategy execution. If you're on the testnet with sufficient funds, you might see it attempt to place very small orders.

**Important Considerations for Production:**

*   **Security:** Never hardcode API keys. Environment variables are better, but for production, consider more secure secrets management (e.g., AWS Secrets Manager, HashiCorp Vault).
*   **Error Handling & Retries:** Implement more sophisticated retry logic with exponential backoff for API calls that fail due to rate limits or temporary network issues.
*   **State Persistence:** If the bot restarts, it loses its internal state (e.g., open orders not managed by WS, PnL history). Consider using a database (SQLite, PostgreSQL) to persist critical information.
*   **Monitoring & Alerts:** Set up monitoring for bot health, performance, and PnL. Integrate with alerting systems (email, SMS, Telegram) for critical events.
*   **Deployment:** Deploy the bot on a reliable server (VPS, cloud instance) with proper process management (e.g., `systemd`, Docker).
*   **Rate Limits:** Be mindful of Bybit's API rate limits. The `pybit` library handles some of this, but your strategy logic should also be designed to avoid excessive requests.
*   **Market Making Complexity:** The provided `market_making_strategy` is extremely basic. A real one needs to account for:
    *   **Spread Management:** Dynamically adjusting bid/ask prices based on volatility, order book depth, and inventory.
    *   **Inventory Management:** Preventing accumulating too much long or short exposure.
    *   **Hedging:** If needed, using other instruments or exchanges to hedge risk.
    *   **Latency:** For true high-frequency market making, network latency and execution speed are critical.
    *   **Fees:** Accounting for trading fees in profitability calculations.
    *   **Slippage:** The difference between the expected price and the actual execution price.
*   **Asynchronous Blocking:** As noted in the code, `pybit.HTTP` calls are synchronous. For a truly non-blocking `async` bot, you would wrap these calls with `await asyncio.to_thread(self.session.method, ...)`. This offloads the blocking call to a separate thread, allowing the main event loop to remain responsive.
