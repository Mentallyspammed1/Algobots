import logging
import os
import sys  # For sys.exit
import time
from decimal import ROUND_DOWN  # Import ROUND_UP
from decimal import ROUND_UP  # Import ROUND_UP
from decimal import Decimal  # Import ROUND_UP
from decimal import getcontext  # Import ROUND_UP

# Ensure Decimal precision for financial calculations
getcontext().prec = 10  # Set precision for Decimal operations

# Import pybit components
try:
    from pybit.unified_trading import HTTP
    from pybit.unified_trading import WebSocket
except ImportError:
    logging.error("Please install pybit: pip install pybit")
    sys.exit(1)

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
    "ORDER_SIZE_USDT": Decimal(
        "10.0"
    ),  # Order size in USDT (as Decimal) - this will be PER LEVEL
    "INVENTORY_TARGET": Decimal(
        "0"
    ),  # Target base asset (e.g., BTC) inventory. 0 = neutral.
    "INVENTORY_SKEW_FACTOR": Decimal("0.0001"),  # Skew factor for inventory management
    "ORDER_LEVELS": 2,  # Number of order levels to place on each side (e.g., 2 bids, 2 asks)
    "LEVEL_PRICE_OFFSET_FACTOR": Decimal(
        "0.00005"
    ),  # Additional spread per level (e.g., 0.005% per level)
    "ORDER_ID_PREFIX": "my_mm_bot",  # Unique prefix for bot-placed orders
    "HEARTBEAT_INTERVAL_SEC": 5,  # How often the main loop sleeps
    "ORDER_PLACEMENT_INTERVAL_SEC": 3,  # How often to check and place/update orders
    "MAX_SPREAD_PERCENT": Decimal(
        "0.005"
    ),  # Max allowed spread (0.5%) before halting order placement
    "CIRCUIT_BREAKER_TIMEOUT_SEC": 300,  # Time in seconds before circuit breaker can reset (5 minutes)
    "MAX_CONSECUTIVE_ERRORS": 5,  # How many consecutive errors before activating circuit breaker
    "WS_RECONNECT_INTERVAL_SEC": 5,  # How long to wait before attempting WebSocket reconnect
    "WS_MAX_RECONNECT_ATTEMPTS": 10,  # Max reconnect attempts before activating circuit breaker
    "ORDER_AMEND_TOLERANCE_PERCENT": Decimal(
        "0.00005"
    ),  # Price/Qty diff % to trigger amend instead of cancel/place
}

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("market_maker.log"), logging.StreamHandler()],
)


class MarketMaker:
    """A market making bot for Bybit Unified Trading Account, enhanced with
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
        self.inventory_target = config["INVENTORY_TARGET"]
        self.inventory_skew_factor = config["INVENTORY_SKEW_FACTOR"]
        self.order_levels = config["ORDER_LEVELS"]
        self.level_price_offset_factor = config["LEVEL_PRICE_OFFSET_FACTOR"]
        self.max_spread_percent = config["MAX_SPREAD_PERCENT"]
        self.order_amend_tolerance = config["ORDER_AMEND_TOLERANCE_PERCENT"]

        # Instrument precision (fetched from exchange)
        self.price_tick_size = Decimal("0.0")
        self.qty_step_size = Decimal("0.0")
        self.min_order_qty = Decimal("0.0")

        # Volatile market data and state
        self.mid_price = Decimal("0.0")
        self.current_inventory = Decimal("0.0")
        self.last_order_placement_time = 0.0
        # active_orders: {order_link_id: {orderId, price, qty, side, status, level}}
        self.active_orders = {}

        # Concurrency control
        self.api_lock = Lock()
        self.data_lock = (
            Lock()
        )  # For protecting mid_price, current_inventory, active_orders

        # Circuit Breaker
        self.circuit_breaker_active = False
        self.circuit_breaker_start_time = 0.0
        self.consecutive_errors = 0
        self.ws_reconnect_attempts = 0

        # --- Initialize API Sessions ---
        # REST API for placing/canceling orders and fetching account data
        self.session = HTTP(
            testnet=True, api_key=self.api_key, api_secret=self.api_secret
        )

        # Websocket will be connected in run() after initial setup
        self.ws = None
        self.ws_connected = False

    def _connect_ws(self):
        """Initializes and subscribes to WebSocket streams with retry logic."""
        if self.ws:
            self.ws.exit()  # Close existing connection if any
            logging.info("Closed existing WebSocket connection.")
            self.ws = None  # Clear the old WS object

        self.ws_connected = False
        self.ws_reconnect_attempts = 0

        while (
            not self.ws_connected
            and self.ws_reconnect_attempts < self.config["WS_MAX_RECONNECT_ATTEMPTS"]
        ):
            try:
                logging.info(
                    f"Attempting WebSocket connection (Attempt {self.ws_reconnect_attempts + 1}/{self.config['WS_MAX_RECONNECT_ATTEMPTS']})..."
                )
                self.ws = WebSocket(
                    testnet=True,
                    channel_type=self.category,
                    api_key=self.api_key,  # For private streams
                    api_secret=self.api_secret,  # For private streams
                )

                self.ws.orderbook_stream(
                    symbol=self.symbol,
                    depth=1,  # We only need the top of the book for this strategy
                    callback=self._on_orderbook_update,
                )
                logging.info(f"Subscribed to orderbook stream for {self.symbol}.")

                self.ws.position_stream(callback=self._on_position_update)
                logging.info(f"Subscribed to position stream for {self.symbol}.")

                self.ws.order_stream(callback=self._on_order_update)
                logging.info(f"Subscribed to order stream for {self.symbol}.")

                self.ws_connected = True
                self.consecutive_errors = (
                    0  # Reset error count on successful connection
                )
                logging.info("WebSocket connection established and subscriptions made.")
            except Exception as e:
                logging.error(f"Failed to connect WebSocket: {e}")
                self.ws_reconnect_attempts += 1
                if (
                    self.ws_reconnect_attempts
                    < self.config["WS_MAX_RECONNECT_ATTEMPTS"]
                ):
                    sleep_time = self.config["WS_RECONNECT_INTERVAL_SEC"] * (
                        2 ** (self.ws_reconnect_attempts - 1)
                    )  # Exponential backoff
                    logging.warning(
                        f"Retrying WebSocket connection in {min(sleep_time, 60)} seconds..."
                    )
                    time.sleep(
                        min(sleep_time, 60)
                    )  # Cap sleep time to avoid excessive delays
                else:
                    logging.error("Max WebSocket reconnect attempts reached.")
                    self.activate_circuit_breaker(
                        f"Max WebSocket reconnect attempts reached: {e}"
                    )
                    break  # Exit loop, circuit breaker will handle

    def _handle_api_response(self, response: dict, action_name: str):
        """Centralized handler for API responses."""
        if response and response.get("retCode") == 0:
            logging.debug(f"{action_name} successful: {response.get('retMsg')}")
            self.consecutive_errors = 0  # Reset error count on success
            return response.get("result")
        error_msg = response.get("retMsg", "Unknown error")
        logging.error(
            f"{action_name} failed: retCode={response.get('retCode')}, retMsg={error_msg}, data={response.get('result')}"
        )
        self.consecutive_errors += 1
        if self.consecutive_errors >= self.config["MAX_CONSECUTIVE_ERRORS"]:
            self.activate_circuit_breaker(
                f"Too many API errors during {action_name}: {error_msg}"
            )
        return None

    def _on_orderbook_update(self, message: dict):
        """Callback for websocket order book updates."""
        if self.circuit_breaker_active and not self._check_circuit_breaker_timeout():
            logging.debug("Circuit breaker active, ignoring orderbook update.")
            return

        try:
            data = message.get("data")
            if not data or not data.get("b", []) or not data.get("a", []):
                logging.debug("Incomplete order book data received.")
                return

            bid_price = Decimal(data["b"][0][0])
            ask_price = Decimal(data["a"][0][0])

            with self.data_lock:
                self.mid_price = (bid_price + ask_price) / Decimal("2")

            current_spread_percent = (ask_price - bid_price) / self.mid_price
            if current_spread_percent > self.max_spread_percent:
                logging.warning(
                    f"Spread too wide ({current_spread_percent:.4f} > {self.max_spread_percent:.4f}), not placing orders."
                )
                return

            logging.debug(
                f"Received Orderbook Update - Bid: {bid_price}, Ask: {ask_price}, Mid: {self.mid_price}, Spread: {current_spread_percent:.4f}"
            )

        except (KeyError, IndexError, ValueError, TypeError) as e:
            logging.error(
                f"Error processing order book update: {e} | Message: {message}"
            )
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
            data = message.get("data", [])
            if not data:
                return

            for position in data:
                if position.get("symbol") == self.symbol:
                    pos_size = Decimal(position.get("size", "0"))
                    pos_side = position.get("side", "")

                    with self.data_lock:
                        if pos_side == "Buy":
                            self.current_inventory = pos_size
                        elif pos_side == "Sell":
                            self.current_inventory = (
                                -pos_size
                            )  # Represent a short position or holding quote
                        else:  # E.g., if size is 0 and side is empty
                            self.current_inventory = Decimal("0")

                    logging.info(
                        f"Position update received. Current inventory: {self.current_inventory} {self.symbol}"
                    )
                    return
        except (KeyError, ValueError, TypeError) as e:
            logging.error(f"Error processing position update: {e} | Message: {message}")
            self.activate_circuit_breaker(f"Position data parsing error: {e}")
        except Exception as e:
            logging.error(f"Unexpected error in _on_position_update: {e}")
            self.activate_circuit_breaker(f"Unexpected error in position update: {e}")

    def _on_order_update(self, message: dict):
        """Callback for websocket order updates."""
        if self.circuit_breaker_active and not self._check_circuit_breaker_timeout():
            logging.debug("Circuit breaker active, ignoring order update.")
            return

        try:
            data = message.get("data", [])
            if not data:
                return

            for order in data:
                symbol = order.get("symbol")
                order_link_id = order.get("orderLinkId")
                order_id = order.get("orderId")
                order_status = order.get(
                    "orderStatus"
                )  # New, PartiallyFilled, Filled, Cancelled, Rejected, Expired
                side = order.get("side")
                price = Decimal(order.get("price", "0"))
                qty = Decimal(order.get("qty", "0"))

                if symbol != self.symbol or not order_link_id.startswith(
                    self.config["ORDER_ID_PREFIX"]
                ):
                    continue  # Not our order or not for our symbol

                with self.data_lock:
                    if order_status in ["New", "PartiallyFilled"]:
                        # Extract level from orderLinkId (assuming format: prefix_side_level)
                        level = (
                            int(order_link_id.split("_")[-1])
                            if order_link_id.split("_")[-1].isdigit()
                            else -1
                        )
                        self.active_orders[order_link_id] = {
                            "orderId": order_id,
                            "price": price,
                            "qty": qty,
                            "side": side,
                            "orderLinkId": order_link_id,
                            "status": order_status,
                            "level": level,
                        }
                        logging.debug(
                            f"Order updated: {order_link_id} Status: {order_status} Price: {price} Qty: {qty}"
                        )
                    elif order_status in ["Filled", "Cancelled", "Rejected", "Expired"]:
                        if order_link_id in self.active_orders:
                            del self.active_orders[order_link_id]
                            logging.info(
                                f"Order removed: {order_link_id} Status: {order_status}"
                            )
                    else:
                        logging.warning(
                            f"Unhandled order status for {order_link_id}: {order_status}"
                        )

        except (KeyError, ValueError, TypeError) as e:
            logging.error(f"Error processing order update: {e} | Message: {message}")
            self.activate_circuit_breaker(f"Order data parsing error: {e}")
        except Exception as e:
            logging.error(f"Unexpected error in _on_order_update: {e}")
            self.activate_circuit_breaker(f"Unexpected error in order update: {e}")

    def get_instrument_info(self):
        """Fetches instrument details like tick size and lot size."""
        retries = 3
        for i in range(retries):
            with self.api_lock:
                response = self.session.get_instruments_info(
                    category=self.category, symbol=self.symbol
                )
                result = self._handle_api_response(response, "Get Instruments Info")
                if result and result.get("list"):
                    instrument = result["list"][0]
                    price_filter = instrument.get("priceFilter", {})
                    lot_size_filter = instrument.get("lotSizeFilter", {})

                    self.price_tick_size = Decimal(price_filter.get("tickSize", "0.01"))
                    self.qty_step_size = Decimal(
                        lot_size_filter.get("qtyStep", "0.0001")
                    )
                    self.min_order_qty = Decimal(
                        lot_size_filter.get("minOrderQty", "0.001")
                    )

                    logging.info(
                        f"Instrument Info for {self.symbol}: Price Tick Size={self.price_tick_size}, Qty Step Size={self.qty_step_size}, Min Order Qty={self.min_order_qty}"
                    )
                    return True
                logging.warning(
                    f"Could not get instrument info. Retrying ({i + 1}/{retries})..."
                )
                time.sleep(2)
        self.activate_circuit_breaker(
            "Failed to get instrument info after multiple retries."
        )
        return False

    def get_account_data(self):
        """Fetches initial account data (e.g., wallet balance, position).
        This is typically done on startup.
        """
        with self.api_lock:
            response = self.session.get_positions(
                category=self.category, symbol=self.symbol
            )
            positions = self._handle_api_response(response, "Get Positions")
            if positions and positions.get("list"):
                position = positions["list"][0]
                with self.data_lock:
                    pos_size = Decimal(position.get("size", "0"))
                    pos_side = position.get("side", "")
                    if pos_side == "Buy":
                        self.current_inventory = pos_size
                    elif pos_side == "Sell":
                        self.current_inventory = -pos_size
                    else:
                        self.current_inventory = Decimal("0")
                logging.info(
                    f"Initial position fetched. Inventory: {self.current_inventory}"
                )
            else:
                logging.warning("No initial position found or failed to fetch.")
                # If no position, assume 0 for starting
                with self.data_lock:
                    self.current_inventory = Decimal("0")

    def get_price_info(self):
        """Fetch initial market data to get the mid-price.
        This is a fallback/initialization step, as websocket handles updates.
        """
        retries = 3
        for i in range(retries):
            with self.api_lock:
                response = self.session.get_orderbook(
                    category=self.category, symbol=self.symbol, limit=1
                )
                result = self._handle_api_response(response, "Get Orderbook")
                if result and result.get("bids") and result.get("asks"):
                    bid = Decimal(result["bids"][0][0])
                    ask = Decimal(result["asks"][0][0])
                    with self.data_lock:
                        self.mid_price = (bid + ask) / Decimal("2")
                    logging.info(f"Initial mid-price fetched: {self.mid_price}")
                    return
                logging.warning(
                    f"Could not get initial price info. Retrying ({i + 1}/{retries})..."
                )
                time.sleep(2)
        self.activate_circuit_breaker(
            "Failed to get initial price info after multiple retries."
        )

    def cancel_all_bot_orders(self):
        """Cancels all open orders placed by this bot for the symbol."""
        with self.api_lock:
            try:
                # Fetch and filter by orderLinkId prefix for precision
                response = self.session.get_open_orders(
                    category=self.category, symbol=self.symbol, limit=50
                )
                open_orders = self._handle_api_response(
                    response, "Get Open Orders for Cancellation"
                )

                if open_orders and open_orders.get("list"):
                    orders_to_cancel = [
                        order
                        for order in open_orders["list"]
                        if order.get("orderLinkId", "").startswith(
                            self.config["ORDER_ID_PREFIX"]
                        )
                    ]
                    if orders_to_cancel:
                        logging.info(
                            f"Found {len(orders_to_cancel)} bot orders to cancel."
                        )
                        for order in orders_to_cancel:
                            cancel_resp = self.session.cancel_order(
                                category=self.category,
                                symbol=self.symbol,
                                orderId=order.get("orderId"),
                            )
                            self._handle_api_response(
                                cancel_resp, f"Cancel Order {order.get('orderId')}"
                            )
                            time.sleep(0.05)  # Small delay
                        logging.info(f"All bot orders for {self.symbol} cancelled.")
                    else:
                        logging.info("No bot orders found to cancel.")
                else:
                    logging.info("No open orders found to cancel.")

                with self.data_lock:
                    self.active_orders.clear()  # Clear local tracking
            except Exception as e:
                logging.error(f"Failed to cancel all orders: {e}")
                self.activate_circuit_breaker(f"Failed to cancel orders: {e}")

    def _calculate_desired_orders(
        self, mid_price: Decimal, inventory: Decimal
    ) -> list[dict]:
        """Calculates desired bid and ask orders based on mid-price, inventory skew, and order levels."""
        desired_orders = []
        skew_amount = self.inventory_skew_factor * (inventory - self.inventory_target)

        for i in range(self.order_levels):
            level_offset = self.level_price_offset_factor * i

            # Bid side
            bid_price = (
                mid_price
                * (Decimal("1") - self.spread_percent / Decimal("2") - level_offset)
                - skew_amount
            )
            bid_qty = self.order_size_usdt / bid_price

            # Ask side
            ask_price = (
                mid_price
                * (Decimal("1") + self.spread_percent / Decimal("2") + level_offset)
                - skew_amount
            )
            ask_qty = self.order_size_usdt / ask_price

            # Quantize prices and quantities using instrument info
            bid_price = bid_price.quantize(self.price_tick_size, rounding=ROUND_DOWN)
            ask_price = ask_price.quantize(
                self.price_tick_size, rounding=ROUND_UP
            )  # ROUND_UP for asks
            bid_qty = bid_qty.quantize(self.qty_step_size, rounding=ROUND_DOWN)
            ask_qty = ask_qty.quantize(self.qty_step_size, rounding=ROUND_DOWN)

            # Ensure quantities meet minimums
            if bid_qty < self.min_order_qty:
                logging.warning(
                    f"Calculated bid qty {bid_qty} is below min {self.min_order_qty}. Skipping bid level {i}."
                )
            else:
                desired_orders.append(
                    {"side": "Buy", "price": bid_price, "qty": bid_qty, "level": i}
                )

            if ask_qty < self.min_order_qty:
                logging.warning(
                    f"Calculated ask qty {ask_qty} is below min {self.min_order_qty}. Skipping ask level {i}."
                )
            else:
                desired_orders.append(
                    {"side": "Sell", "price": ask_price, "qty": ask_qty, "level": i}
                )

        return desired_orders

    def manage_orders(self):
        """Manages existing orders and places new ones to maintain the desired market making strategy.
        This function is called periodically.
        """
        with self.data_lock:
            current_mid_price = self.mid_price
            current_inventory = self.current_inventory
            current_active_orders = (
                self.active_orders.copy()
            )  # Work on a copy to avoid lock contention during API calls

        if current_mid_price == Decimal("0.0") or self.price_tick_size == Decimal(
            "0.0"
        ):
            logging.warning("Mid price or instrument info is 0, cannot place orders.")
            return

        if self.circuit_breaker_active and not self._check_circuit_breaker_timeout():
            logging.warning("Circuit breaker active, not managing orders.")
            return

        current_time = time.time()
        if (
            current_time - self.last_order_placement_time
            < self.config["ORDER_PLACEMENT_INTERVAL_SEC"]
        ):
            logging.debug("Too soon to place/update orders.")
            return

        logging.info("Managing orders...")

        try:
            desired_orders = self._calculate_desired_orders(
                current_mid_price, current_inventory
            )

            orders_to_cancel_ids = []  # List of orderIds to cancel
            orders_to_amend = []  # List of (orderId, new_price, new_qty)
            orders_to_place = []  # List of (side, price, qty, level)

            # Map existing orders by side and level for easier comparison
            existing_bids = {
                order_info["level"]: order_info
                for order_info in current_active_orders.values()
                if order_info["side"] == "Buy"
            }
            existing_asks = {
                order_info["level"]: order_info
                for order_info in current_active_orders.values()
                if order_info["side"] == "Sell"
            }

            # Check desired orders against existing ones
            for desired_order in desired_orders:
                side = desired_order["side"]
                level = desired_order["level"]
                desired_price = desired_order["price"]
                desired_qty = desired_order["qty"]

                existing_order = None
                if side == "Buy" and level in existing_bids:
                    existing_order = existing_bids[level]
                elif side == "Sell" and level in existing_asks:
                    existing_order = existing_asks[level]

                if existing_order:
                    # Check if existing order needs amendment or cancellation
                    price_diff_percent = (
                        abs(existing_order["price"] - desired_price) / desired_price
                        if desired_price
                        else Decimal("inf")
                    )
                    qty_diff_percent = (
                        abs(existing_order["qty"] - desired_qty) / desired_qty
                        if desired_qty
                        else Decimal("inf")
                    )

                    if (
                        price_diff_percent > self.order_amend_tolerance
                        or qty_diff_percent > self.order_amend_tolerance
                    ):
                        # Amend if price/qty is significantly different
                        orders_to_amend.append(
                            {
                                "orderId": existing_order["orderId"],
                                "orderLinkId": existing_order["orderLinkId"],
                                "side": side,
                                "price": desired_price,
                                "qty": desired_qty,
                            }
                        )
                        logging.info(
                            f"Marking {side} order {existing_order['orderLinkId']} for amendment (Level {level}). Old P/Q: {existing_order['price']}/{existing_order['qty']} New P/Q: {desired_price}/{desired_qty}"
                        )
                    else:
                        logging.debug(
                            f"Existing {side} order {existing_order['orderLinkId']} (Level {level}) is still optimal."
                        )
                else:
                    # No existing order for this side/level, place a new one
                    orders_to_place.append(desired_order)
                    logging.info(
                        f"Marking new {side} order for placement (Level {level}). Price: {desired_price} Qty: {desired_qty}"
                    )

            # Identify orders to cancel (those existing but not desired)
            desired_order_keys = set()
            for d_order in desired_orders:
                desired_order_keys.add((d_order["side"], d_order["level"]))

            for olink, order_info in current_active_orders.items():
                if (order_info["side"], order_info["level"]) not in desired_order_keys:
                    orders_to_cancel_ids.append(order_info["orderId"])
                    logging.info(
                        f"Marking stale order {olink} for cancellation (not in desired set)."
                    )

            # Execute cancellations
            for order_id in orders_to_cancel_ids:
                with self.api_lock:
                    response = self.session.cancel_order(
                        category=self.category, symbol=self.symbol, orderId=order_id
                    )
                    self._handle_api_response(response, f"Cancel Order {order_id}")
                time.sleep(0.05)  # Small delay between API calls

            # Execute amendments
            for amend_data in orders_to_amend:
                with self.api_lock:
                    response = self.session.amend_order(
                        category=self.category,
                        symbol=self.symbol,
                        orderId=amend_data["orderId"],
                        qty=str(amend_data["qty"]),
                        price=str(amend_data["price"]),
                        orderLinkId=amend_data[
                            "orderLinkId"
                        ],  # Pass orderLinkId for reference
                    )
                    result = self._handle_api_response(
                        response,
                        f"Amend {amend_data['side']} Order {amend_data['orderId']}",
                    )
                    if result:
                        logging.info(
                            f"Amended {amend_data['side']} order {amend_data['orderId']}: Qty={amend_data['qty']}, Price={amend_data['price']}"
                        )
                time.sleep(0.05)  # Small delay between API calls

            # Execute new order placements
            for order_data in orders_to_place:
                order_link_id = f"{self.config['ORDER_ID_PREFIX']}_{order_data['side'].lower()}_{order_data['level']}"
                with self.api_lock:
                    response = self.session.place_order(
                        category=self.category,
                        symbol=self.symbol,
                        side=order_data["side"],
                        orderType="Limit",
                        qty=str(
                            order_data["qty"]
                        ),  # pybit expects string for qty/price
                        price=str(order_data["price"]),
                        orderLinkId=order_link_id,
                        timeInForce="GTC",
                        isLeverage="0",  # For spot, ensure no leverage
                        orderFilter="Order",  # Ensure it's a normal order, not a conditional one
                        is_post_only=True,  # Crucial for market making to avoid taker fees
                    )
                    result = self._handle_api_response(
                        response,
                        f"Place {order_data['side']} Order (Level {order_data['level']})",
                    )
                    if result:
                        logging.info(
                            f"Placed {order_data['side']} order (Level {order_data['level']}): Qty={order_data['qty']}, Price={order_data['price']}"
                        )
                        # The _on_order_update callback will add this to active_orders
                time.sleep(0.05)  # Small delay between API calls

            self.last_order_placement_time = current_time

        except Exception as e:
            logging.error(f"Failed to manage orders: {e}")
            self.activate_circuit_breaker(f"Order management error: {e}")

    def activate_circuit_breaker(self, reason: str):
        """Activates the circuit breaker, cancels all orders, and halts trading."""
        if not self.circuit_breaker_active:
            self.circuit_breaker_active = True
            self.circuit_breaker_start_time = time.time()
            logging.critical(f"CIRCUIT BREAKER ACTIVATED: {reason}. TRADING HALTED.")
            self.cancel_all_bot_orders()  # Cancel all bot's orders
            if self.ws:
                self.ws.exit()  # Disconnect WebSocket
                self.ws_connected = False
            # Optionally, send a notification (e.g., email, push) here
        else:
            logging.warning(f"Circuit breaker already active. Reason: {reason}")

    def _check_circuit_breaker_timeout(self) -> bool:
        """Checks if the circuit breaker timeout has expired."""
        if self.circuit_breaker_active:
            elapsed_time = time.time() - self.circuit_breaker_start_time
            if elapsed_time >= self.config["CIRCUIT_BREAKER_TIMEOUT_SEC"]:
                self.deactivate_circuit_breaker()
                return True
            logging.debug(
                f"Circuit breaker active. Time remaining: {self.config['CIRCUIT_BREAKER_TIMEOUT_SEC'] - elapsed_time:.0f}s"
            )
            return False
        return True  # Not active

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
        # Re-fetch instrument info in case something changed (unlikely but safe)
        self.get_instrument_info()

    def run(self):
        """Main loop for the market maker."""
        logging.info("Starting market maker bot...")

        # Initial setup
        if not self.get_instrument_info():  # Get instrument info first for precision
            logging.critical("Failed to get instrument info. Exiting.")
            sys.exit(1)
        self.get_price_info()  # Get an initial price to start with
        self.get_account_data()  # Get initial inventory
        self._connect_ws()  # Connect WebSocket after initial REST calls

        if not self.ws_connected:
            logging.critical("Failed to establish WebSocket connection. Exiting.")
            sys.exit(1)

        logging.info("Bot is now running and awaiting websocket updates...")

        while True:
            if self.circuit_breaker_active:
                if self._check_circuit_breaker_timeout():
                    logging.info(
                        "Circuit breaker timeout expired. Attempting to resume."
                    )
                else:
                    logging.warning(
                        "Circuit breaker active. Waiting for timeout or manual intervention."
                    )
                    time.sleep(self.config["HEARTBEAT_INTERVAL_SEC"])
                    continue  # Skip trading logic if circuit breaker is active

            # Ensure WebSocket is still connected
            if not self.ws_connected:
                logging.warning("WebSocket disconnected. Attempting to reconnect...")
                self._connect_ws()
                if not self.ws_connected:
                    logging.error(
                        "Failed to reconnect WebSocket. Circuit breaker might be activated."
                    )
                    time.sleep(
                        self.config["HEARTBEAT_INTERVAL_SEC"]
                    )  # Wait before next check
                    continue

            # Periodically manage orders based on interval
            if (
                time.time() - self.last_order_placement_time
                >= self.config["ORDER_PLACEMENT_INTERVAL_SEC"]
            ):
                self.manage_orders()

            # Keep the main thread alive to listen for websocket updates
            time.sleep(self.config["HEARTBEAT_INTERVAL_SEC"])


if __name__ == "__main__":
    # Validate API keys
    if CONFIG["API_KEY"] == "YOUR_API_KEY" or CONFIG["API_SECRET"] == "YOUR_API_SECRET":
        logging.error(
            "Please set your BYBIT_API_KEY and BYBIT_API_SECRET environment variables or update CONFIG."
        )
        sys.exit(1)

    mm_bot = MarketMaker(CONFIG)
    try:
        mm_bot.run()
    except KeyboardInterrupt:
        logging.info(
            "Bot stopped by user (KeyboardInterrupt). Cancelling all orders..."
        )
        mm_bot.cancel_all_bot_orders()
        if mm_bot.ws:
            mm_bot.ws.exit()  # Close WebSocket connection
        logging.info("Bot gracefully shut down.")
    except Exception as e:
        logging.critical(
            f"An unhandled exception occurred: {e}", exc_info=True
        )  # exc_info to log traceback
        mm_bot.cancel_all_bot_orders()
        if mm_bot.ws:
            mm_bot.ws.exit()
        logging.critical("Bot terminated due to unhandled exception.")
