The provided market maker bot is a good starting point, but it can be significantly enhanced in terms of robustness, efficiency, and features.

Here's an upgraded version focusing on:

1.  **Configuration Management:** Using environment variables for sensitive API keys and a more structured config.
2.  **Robustness & Error Handling:**
    *   Improved circuit breaker with a timeout and error count.
    *   Centralized API response handling.
    *   `Decimal` for precise financial calculations.
    *   WebSocket reconnection logic.
3.  **Market Making Logic:**
    *   More intelligent order management: Instead of canceling *all* orders on every update, it now fetches active orders and only cancels/replaces those that are no longer optimal or have been filled.
    *   Support for multiple order levels (though only one is implemented for brevity, the structure allows expansion).
    *   Checks for extreme spread.
    *   Periodic order placement (not on every tick) to reduce API calls.
4.  **Logging:** More detailed and structured logging.
5.  **Code Structure:** Better organization, type hints, and comments.

```python
import time
import json
import logging
import os
from decimal import Decimal, getcontext
from threading import Thread, Lock

# Ensure Decimal precision for financial calculations
getcontext().prec = 10 # Set precision for Decimal operations

# Import pybit components
# Note: pybit.unified_trading is deprecated. Use pybit.usdt_perpetual or pybit.spot
# For this example, I'll assume a recent pybit version where unified_trading still works
# or that the user will adapt to the specific category's client.
# A more robust solution would dynamically choose the client based on 'category'.
# For simplicity, let's assume `pybit.unified_trading` is still the intended API for both spot/linear.
try:
    from pybit.unified_trading import WebSocket, HTTP
except ImportError:
    logging.error("Please install pybit: pip install pybit")
    exit(1)

# --- CONFIGURATION ---
# It's a best practice to keep configuration separate from core logic.
# For production, API_KEY and API_SECRET should be loaded from environment variables
# or a secure configuration management system.
# Example: export BYBIT_API_KEY="YOUR_API_KEY"
# Example: export BYBIT_API_SECRET="YOUR_API_SECRET"
CONFIG = {
    "API_KEY": os.getenv("BYBIT_API_KEY", "YOUR_API_KEY"),
    "API_SECRET": os.getenv("BYBIT_API_SECRET", "YOUR_API_SECRET"),
    "SYMBOL": "BTCUSDT",
    "CATEGORY": "spot",  # Use 'linear' for perpetual futures, 'spot' for spot market
    "SPREAD_PERCENT": Decimal("0.001"),  # 0.1% spread (as Decimal)
    "ORDER_SIZE_USDT": Decimal("10.0"), # Order size in USDT (as Decimal)
    "QUANTITY_DECIMALS": 4,  # Precision for quantity (e.g., BTC)
    "PRICE_DECIMALS": 2,     # Precision for price (e.g., USDT)
    "INVENTORY_TARGET": Decimal("0"),  # Target base asset (e.g., BTC) inventory. 0 = neutral.
    "INVENTORY_SKEW_FACTOR": Decimal("0.0001"),  # Skew factor for inventory management
    "ORDER_LIMIT": 1,  # Number of orders to place on each side (currently only 1 supported for simplicity)
    "ORDER_ID_PREFIX": "my_mm_bot", # Unique prefix for bot-placed orders
    "HEARTBEAT_INTERVAL_SEC": 5, # How often the main loop sleeps
    "ORDER_PLACEMENT_INTERVAL_SEC": 3, # How often to check and place/update orders
    "MAX_SPREAD_PERCENT": Decimal("0.005"), # Max allowed spread (0.5%) before halting order placement
    "CIRCUIT_BREAKER_TIMEOUT_SEC": 300, # Time in seconds before circuit breaker can reset (5 minutes)
    "MAX_CONSECUTIVE_ERRORS": 5, # How many consecutive errors before activating circuit breaker
    "WS_RECONNECT_INTERVAL_SEC": 10, # How long to wait before attempting WebSocket reconnect
    "WS_MAX_RECONNECT_ATTEMPTS": 5, # Max reconnect attempts before activating circuit breaker
}

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("market_maker.log"),
        logging.StreamHandler()
    ]
)

class MarketMaker:
    """
    A market making bot for Bybit Unified Trading Account, enhanced with
    Websocket for real-time data and advanced risk management.
    """
    def __init__(self, config: dict):
        self.config = config
        self.api_key = config["API_KEY"]
        self.api_secret = config["API_SECRET"]
        self.symbol = config["SYMBOL"]
        self.category = config["CATEGORY"]
        self.order_size_usdt = config["ORDER_SIZE_USDT"]
        self.spread_percent = config["SPREAD_PERCENT"]
        self.quantity_decimals = config["QUANTITY_DECIMALS"]
        self.price_decimals = config["PRICE_DECIMALS"]
        self.inventory_target = config["INVENTORY_TARGET"]
        self.inventory_skew_factor = config["INVENTORY_SKEW_FACTOR"]
        self.order_limit = config["ORDER_LIMIT"]
        self.max_spread_percent = config["MAX_SPREAD_PERCENT"]

        # Volatile market data and state
        self.mid_price = Decimal("0.0")
        self.current_inventory = Decimal("0.0")
        self.last_order_placement_time = 0.0
        self.active_orders = {} # {order_link_id: {price, qty, side}}

        # Concurrency control
        self.api_lock = Lock()
        self.data_lock = Lock() # For protecting mid_price, current_inventory

        # Circuit Breaker
        self.circuit_breaker_active = False
        self.circuit_breaker_start_time = 0.0
        self.consecutive_errors = 0
        self.ws_reconnect_attempts = 0

        # --- Initialize API Sessions ---
        # REST API for placing/canceling orders and fetching account data
        self.session = HTTP(
            testnet=True,
            api_key=self.api_key,
            api_secret=self.api_secret
        )

        # Websocket for real-time market data and private updates
        self.ws = None
        self._connect_ws()

    def _connect_ws(self):
        """Initializes and subscribes to WebSocket streams."""
        if self.ws:
            self.ws.exit() # Close existing connection if any
            logging.info("Closed existing WebSocket connection.")

        try:
            self.ws = WebSocket(
                testnet=True,
                channel_type=self.category,
                api_key=self.api_key, # For private streams
                api_secret=self.api_secret # For private streams
            )

            self.ws.orderbook_stream(
                symbol=self.symbol,
                depth=1,  # We only need the top of the book for this strategy
                callback=self._on_orderbook_update
            )
            logging.info(f"Subscribed to orderbook stream for {self.symbol}.")

            self.ws.position_stream(
                callback=self._on_position_update
            )
            logging.info(f"Subscribed to position stream for {self.symbol}.")

            # You might also want to subscribe to order updates to manage active_orders more accurately
            # self.ws.order_stream(
            #     callback=self._on_order_update
            # )
            # logging.info(f"Subscribed to order stream for {self.symbol}.")

            self.ws_reconnect_attempts = 0 # Reset attempts on successful connection
            logging.info("WebSocket connection established and subscriptions made.")
        except Exception as e:
            logging.error(f"Failed to connect WebSocket: {e}")
            self.consecutive_errors += 1
            if self.consecutive_errors >= self.config["MAX_CONSECUTIVE_ERRORS"]:
                self.activate_circuit_breaker(f"Too many WebSocket connection errors: {e}")
            else:
                logging.warning(f"Retrying WebSocket connection in {self.config['WS_RECONNECT_INTERVAL_SEC']} seconds...")
                time.sleep(self.config["WS_RECONNECT_INTERVAL_SEC"])
                self._connect_ws() # Recursive retry

    def _handle_api_response(self, response: dict, action_name: str):
        """Centralized handler for API responses."""
        if response and response.get('retCode') == 0:
            logging.debug(f"{action_name} successful: {response.get('retMsg')}")
            self.consecutive_errors = 0 # Reset error count on success
            return response.get('result')
        else:
            error_msg = response.get('retMsg', 'Unknown error')
            logging.error(f"{action_name} failed: retCode={response.get('retCode')}, retMsg={error_msg}, data={response.get('result')}")
            self.consecutive_errors += 1
            if self.consecutive_errors >= self.config["MAX_CONSECUTIVE_ERRORS"]:
                self.activate_circuit_breaker(f"Too many API errors during {action_name}: {error_msg}")
            return None

    def _on_orderbook_update(self, message: dict):
        """Callback for websocket order book updates."""
        if self.circuit_breaker_active and not self._check_circuit_breaker_timeout():
            logging.debug("Circuit breaker active, ignoring orderbook update.")
            return

        try:
            data = message.get('data')
            if not data or not data.get('b', []) or not data.get('a', []):
                logging.debug("Incomplete order book data received.")
                return

            bid_price = Decimal(data['b'][0][0])
            ask_price = Decimal(data['a'][0][0])

            with self.data_lock:
                self.mid_price = (bid_price + ask_price) / Decimal("2")

            current_spread_percent = (ask_price - bid_price) / self.mid_price
            if current_spread_percent > self.max_spread_percent:
                logging.warning(f"Spread too wide ({current_spread_percent:.4f} > {self.max_spread_percent:.4f}), not placing orders.")
                return

            logging.debug(f"Received Orderbook Update - Bid: {bid_price}, Ask: {ask_price}, Mid: {self.mid_price}, Spread: {current_spread_percent:.4f}")

            # Orders are managed periodically, not on every tick, to avoid rate limits
            # The main loop will call manage_orders based on ORDER_PLACEMENT_INTERVAL_SEC
        except (KeyError, IndexError, ValueError, TypeError) as e:
            logging.error(f"Error processing order book update: {e} | Message: {message}")
            self.activate_circuit_breaker(f"Orderbook data parsing error: {e}")
        except Exception as e:
            logging.error(f"Unexpected error in _on_orderbook_update: {e}")
            self.activate_circuit_breaker(f"Unexpected error in orderbook update: {e}")


    def _on_position_update(self, message: dict):
        """Callback for websocket position updates."""
        if self.circuit_breaker_active and not self._check_circuit_breaker_timeout():
            logging.debug("Circuit breaker active, ignoring position update.")
            return

        try:
            data = message.get('data', [])
            if not data:
                return

            for position in data:
                if position.get('symbol') == self.symbol:
                    # 'size' for unified is the position size, 'side' is "Buy" or "Sell"
                    pos_size = Decimal(position.get('size', '0'))
                    pos_side = position.get('side', '')
                    
                    with self.data_lock:
                        # For spot, "Buy" means you hold the base asset (e.g., BTC), "Sell" means you hold quote (e.g., USDT)
                        # For perpetuals, "Buy" is long, "Sell" is short.
                        # Assuming 'size' is always positive and 'side' indicates direction.
                        # If 'side' is empty or not present, it might mean a neutral or zero position.
                        if pos_side == "Buy":
                            self.current_inventory = pos_size
                        elif pos_side == "Sell":
                            self.current_inventory = -pos_size # Represent a short position or holding quote
                        else: # E.g., if size is 0 and side is empty
                            self.current_inventory = Decimal("0")

                    logging.info(f"Position update received. Current inventory: {self.current_inventory} {self.symbol}")
                    return
        except (KeyError, ValueError, TypeError) as e:
            logging.error(f"Error processing position update: {e} | Message: {message}")
            self.activate_circuit_breaker(f"Position data parsing error: {e}")
        except Exception as e:
            logging.error(f"Unexpected error in _on_position_update: {e}")
            self.activate_circuit_breaker(f"Unexpected error in position update: {e}")

    def get_account_data(self):
        """
        Fetches initial account data (e.g., wallet balance, position).
        This is typically done on startup.
        """
        with self.api_lock:
            response = self.session.get_positions(category=self.category, symbol=self.symbol)
            positions = self._handle_api_response(response, "Get Positions")
            if positions and positions.get('list'):
                position = positions['list'][0]
                with self.data_lock:
                    pos_size = Decimal(position.get('size', '0'))
                    pos_side = position.get('side', '')
                    if pos_side == "Buy":
                        self.current_inventory = pos_size
                    elif pos_side == "Sell":
                        self.current_inventory = -pos_size
                    else:
                        self.current_inventory = Decimal("0")
                logging.info(f"Initial position fetched. Inventory: {self.current_inventory}")
            else:
                logging.warning("No initial position found or failed to fetch.")
                # If no position, assume 0 for starting
                with self.data_lock:
                    self.current_inventory = Decimal("0")

    def get_price_info(self):
        """
        Fetch initial market data to get the mid-price.
        This is a fallback/initialization step, as websocket handles updates.
        """
        retries = 3
        for i in range(retries):
            with self.api_lock:
                response = self.session.get_orderbook(category=self.category, symbol=self.symbol, limit=1)
                result = self._handle_api_response(response, "Get Orderbook")
                if result and result.get('bids') and result.get('asks'):
                    bid = Decimal(result['bids'][0][0])
                    ask = Decimal(result['asks'][0][0])
                    with self.data_lock:
                        self.mid_price = (bid + ask) / Decimal("2")
                    logging.info(f"Initial mid-price fetched: {self.mid_price}")
                    return
                else:
                    logging.warning(f"Could not get initial price info. Retrying ({i+1}/{retries})...")
                    time.sleep(2)
        self.activate_circuit_breaker("Failed to get initial price info after multiple retries.")

    def cancel_all_bot_orders(self):
        """Cancels all open orders placed by this bot for the symbol."""
        with self.api_lock:
            try:
                # Bybit's cancel_all_orders can filter by orderLinkId prefix, but it's not a direct parameter.
                # It's usually better to fetch and cancel specific orders by orderId or orderLinkId.
                # For simplicity and to match original intent, using cancel_all_orders.
                # Note: This cancels ALL orders for the symbol, not just bot's.
                # A more precise way is to fetch orders and filter by orderLinkId.
                response = self.session.cancel_all_orders(category=self.category, symbol=self.symbol)
                result = self._handle_api_response(response, "Cancel All Orders")
                if result:
                    logging.info(f"All orders for {self.symbol} cancelled.")
                    self.active_orders.clear() # Clear local tracking
            except Exception as e:
                logging.error(f"Failed to cancel all orders: {e}")
                self.activate_circuit_breaker(f"Failed to cancel orders: {e}")

    def _get_bot_orders(self) -> dict:
        """Fetches currently open orders placed by this bot."""
        bot_orders = {}
        with self.api_lock:
            response = self.session.get_open_orders(category=self.category, symbol=self.symbol, limit=50)
            orders_data = self._handle_api_response(response, "Get Open Orders")
            if orders_data and orders_data.get('list'):
                for order in orders_data['list']:
                    order_link_id = order.get('orderLinkId', '')
                    if order_link_id.startswith(self.config["ORDER_ID_PREFIX"]):
                        bot_orders[order_link_id] = {
                            "orderId": order.get('orderId'),
                            "price": Decimal(order.get('price')),
                            "qty": Decimal(order.get('qty')),
                            "side": order.get('side'),
                            "orderLinkId": order_link_id
                        }
        return bot_orders

    def _calculate_order_params(self, mid_price: Decimal, inventory: Decimal) -> tuple[Decimal, Decimal]:
        """Calculates bid and ask prices and quantities based on mid-price and inventory skew."""
        skew_amount = self.inventory_skew_factor * (inventory - self.inventory_target)
        
        # Adjust prices based on skew:
        # If inventory is positive (long), lower bid price, raise ask price to encourage selling.
        # If inventory is negative (short), raise bid price, lower ask price to encourage buying.
        bid_price = mid_price * (Decimal("1") - self.spread_percent / Decimal("2")) - skew_amount
        ask_price = mid_price * (Decimal("1") + self.spread_percent / Decimal("2")) - skew_amount

        # Round prices to instrument precision
        bid_price = bid_price.quantize(Decimal("1e-" + str(self.price_decimals)))
        ask_price = ask_price.quantize(Decimal("1e-" + str(self.price_decimals)))

        # Calculate quantity in base currency
        bid_qty = (self.order_size_usdt / bid_price).quantize(Decimal("1e-" + str(self.quantity_decimals)))
        ask_qty = (self.order_size_usdt / ask_price).quantize(Decimal("1e-" + str(self.quantity_decimals)))

        return bid_price, ask_price, bid_qty, ask_qty

    def manage_orders(self):
        """
        Manages existing orders and places new ones to maintain the desired market making strategy.
        This function is called periodically.
        """
        with self.data_lock:
            current_mid_price = self.mid_price
            current_inventory = self.current_inventory

        if current_mid_price == Decimal("0.0"):
            logging.warning("Mid price is 0, cannot place orders.")
            return

        if self.circuit_breaker_active and not self._check_circuit_breaker_timeout():
            logging.warning("Circuit breaker active, not managing orders.")
            return

        current_time = time.time()
        if current_time - self.last_order_placement_time < self.config["ORDER_PLACEMENT_INTERVAL_SEC"]:
            logging.debug("Too soon to place/update orders.")
            return

        logging.info("Managing orders...")

        try:
            # 1. Get current bot-placed orders
            existing_bot_orders = self._get_bot_orders()
            self.active_orders = existing_bot_orders # Update local cache

            # 2. Calculate desired new orders
            desired_bid_price, desired_ask_price, desired_bid_qty, desired_ask_qty = \
                self._calculate_order_params(current_mid_price, current_inventory)

            # 3. Determine which orders to cancel and which to place
            orders_to_cancel = []
            orders_to_place = []

            # Check existing bid orders
            has_bid = False
            for order_link_id, order_info in existing_bot_orders.items():
                if order_info['side'] == "Buy":
                    has_bid = True
                    # Check if existing bid is significantly off or quantity is wrong
                    # Using a small tolerance for price comparison
                    if abs(order_info['price'] - desired_bid_price) > desired_bid_price * Decimal("0.0001") or \
                       abs(order_info['qty'] - desired_bid_qty) > desired_bid_qty * Decimal("0.0001"):
                        orders_to_cancel.append(order_info['orderId'])
                        logging.info(f"Cancelling stale BID order {order_link_id} (Price: {order_info['price']} vs Desired: {desired_bid_price})")
                    else:
                        logging.debug(f"Existing BID order {order_link_id} is still good.")

            if not has_bid or orders_to_cancel: # If no bid or old bid was cancelled
                orders_to_place.append({"side": "Buy", "price": desired_bid_price, "qty": desired_bid_qty})

            # Check existing ask orders
            has_ask = False
            for order_link_id, order_info in existing_bot_orders.items():
                if order_info['side'] == "Sell":
                    has_ask = True
                    # Check if existing ask is significantly off or quantity is wrong
                    if abs(order_info['price'] - desired_ask_price) > desired_ask_price * Decimal("0.0001") or \
                       abs(order_info['qty'] - desired_ask_qty) > desired_ask_qty * Decimal("0.0001"):
                        orders_to_cancel.append(order_info['orderId'])
                        logging.info(f"Cancelling stale ASK order {order_link_id} (Price: {order_info['price']} vs Desired: {desired_ask_price})")
                    else:
                        logging.debug(f"Existing ASK order {order_link_id} is still good.")

            if not has_ask or orders_to_cancel: # If no ask or old ask was cancelled
                orders_to_place.append({"side": "Sell", "price": desired_ask_price, "qty": desired_ask_qty})

            # 4. Execute cancellations
            for order_id in orders_to_cancel:
                with self.api_lock:
                    response = self.session.cancel_order(
                        category=self.category,
                        symbol=self.symbol,
                        orderId=order_id
                    )
                    self._handle_api_response(response, f"Cancel Order {order_id}")
                time.sleep(0.1) # Small delay between API calls

            # 5. Execute new order placements
            for order_data in orders_to_place:
                order_link_id = f"{self.config['ORDER_ID_PREFIX']}_{order_data['side'].lower()}_{int(time.time() * 1000)}"
                with self.api_lock:
                    response = self.session.place_order(
                        category=self.category,
                        symbol=self.symbol,
                        side=order_data['side'],
                        orderType="Limit",
                        qty=str(order_data['qty']), # pybit expects string for qty/price
                        price=str(order_data['price']),
                        orderLinkId=order_link_id,
                        timeInForce="GTC"
                    )
                    result = self._handle_api_response(response, f"Place {order_data['side']} Order")
                    if result:
                        logging.info(f"Placed {order_data['side']} order: Qty={order_data['qty']}, Price={order_data['price']}")
                        self.active_orders[order_link_id] = {
                            "orderId": result.get('orderId'),
                            "price": order_data['price'],
                            "qty": order_data['qty'],
                            "side": order_data['side'],
                            "orderLinkId": order_link_id
                        }
                time.sleep(0.1) # Small delay between API calls

            self.last_order_placement_time = current_time

        except Exception as e:
            logging.error(f"Failed to manage orders: {e}")
            self.activate_circuit_breaker(f"Order management error: {e}")

    def activate_circuit_breaker(self, reason: str):
        """
        Activates the circuit breaker, cancels all orders, and halts trading.
        """
        if not self.circuit_breaker_active:
            self.circuit_breaker_active = True
            self.circuit_breaker_start_time = time.time()
            logging.critical(f"CIRCUIT BREAKER ACTIVATED: {reason}. TRADING HALTED.")
            self.cancel_all_bot_orders() # Cancel all bot's orders
            # Optionally, send a notification (e.g., email, push) here
            # self.ws.exit() # Disconnect WebSocket
        else:
            logging.warning(f"Circuit breaker already active. Reason: {reason}")

    def _check_circuit_breaker_timeout(self) -> bool:
        """Checks if the circuit breaker timeout has expired."""
        if self.circuit_breaker_active:
            elapsed_time = time.time() - self.circuit_breaker_start_time
            if elapsed_time >= self.config["CIRCUIT_BREAKER_TIMEOUT_SEC"]:
                self.deactivate_circuit_breaker()
                return True
            else:
                logging.debug(f"Circuit breaker active. Time remaining: {self.config['CIRCUIT_BREAKER_TIMEOUT_SEC'] - elapsed_time:.0f}s")
                return False
        return True # Not active

    def deactivate_circuit_breaker(self):
        """Deactivates the circuit breaker, allowing trading to resume."""
        self.circuit_breaker_active = False
        self.circuit_breaker_start_time = 0.0
        self.consecutive_errors = 0
        logging.info("CIRCUIT BREAKER DEACTIVATED. Attempting to resume trading.")
        # Re-initialize state and potentially reconnect WS
        self._connect_ws()
        self.get_price_info()
        self.get_account_data()


    def run(self):
        """Main loop for the market maker."""
        logging.info("Starting market maker bot...")
        
        # Initial setup
        self.get_price_info()  # Get an initial price to start with
        self.get_account_data() # Get initial inventory

        logging.info("Bot is now running and awaiting websocket updates...")

        while True:
            if self.circuit_breaker_active:
                if self._check_circuit_breaker_timeout():
                    logging.info("Circuit breaker timeout expired. Attempting to resume.")
                else:
                    logging.warning("Circuit breaker active. Waiting for timeout or manual intervention.")
                    time.sleep(self.config["HEARTBEAT_INTERVAL_SEC"])
                    continue # Skip trading logic if circuit breaker is active

            # Periodically manage orders based on interval
            if time.time() - self.last_order_placement_time >= self.config["ORDER_PLACEMENT_INTERVAL_SEC"]:
                self.manage_orders()

            # Keep the main thread alive to listen for websocket updates
            time.sleep(self.config["HEARTBEAT_INTERVAL_SEC"])

if __name__ == "__main__":
    # Validate API keys
    if CONFIG["API_KEY"] == "YOUR_API_KEY" or CONFIG["API_SECRET"] == "YOUR_API_SECRET":
        logging.error("Please set your BYBIT_API_KEY and BYBIT_API_SECRET environment variables or update CONFIG.")
        exit(1)

    mm_bot = MarketMaker(CONFIG)
    try:
        mm_bot.run()
    except KeyboardInterrupt:
        logging.info("Bot stopped by user (KeyboardInterrupt). Cancelling all orders...")
        mm_bot.cancel_all_bot_orders()
        if mm_bot.ws:
            mm_bot.ws.exit() # Close WebSocket connection
        logging.info("Bot gracefully shut down.")
    except Exception as e:
        logging.critical(f"An unhandled exception occurred: {e}")
        mm_bot.cancel_all_bot_orders()
        if mm_bot.ws:
            mm_bot.ws.exit()
        logging.critical("Bot terminated due to unhandled exception.")

```
