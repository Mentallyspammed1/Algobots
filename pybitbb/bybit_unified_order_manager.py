# bybit_unified_order_manager.py
import logging
import threading
import time
from typing import Any, Literal

# Import the specific helpers we've already created
from bybit_trade_helper import BybitTradeHelper
from bybit_ws_private_helper import (
    BybitWsPrivateHelper,  # For real-time order status updates
)
from bybit_ws_trade_helper import BybitWsTradeHelper

# Configure logging for the module
logging.basicConfig(
    level=logging.INFO, # Changed to INFO for less verbose default output, DEBUG for full details
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Define a type alias for the trading mode
TradingMode = Literal["http", "websocket"]

class BybitUnifiedOrderManager:
    """A unified helper class for comprehensive order placement and management on Bybit.
    It abstracts away the underlying communication mechanism (HTTP or WebSocket)
    and provides real-time order status tracking via private WebSocket streams.
    """

    def __init__(self,
                 api_key: str,
                 api_secret: str,
                 testnet: bool = False,
                 default_mode: TradingMode = "http",
                 ws_recv_window: int = 5000):
        """Initializes the BybitUnifiedOrderManager.

        :param api_key: Your Bybit API key.
        :param api_secret: Your Bybit API secret.
        :param testnet: Set to True to connect to the Bybit testnet, False for mainnet.
        :param default_mode: The default trading mode to use for order operations ("http" or "websocket").
        :param ws_recv_window: The recv_window for WebSocket trading operations (in milliseconds).
        """
        if not api_key or not api_secret:
            logger.error("API Key and Secret are required for BybitUnifiedOrderManager.")
            raise ValueError("API Key and Secret must be provided.")

        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.default_mode = default_mode
        self.ws_recv_window = ws_recv_window

        # Initialize underlying helpers
        self._http_trade_helper = BybitTradeHelper(api_key, api_secret, testnet)
        self._ws_trade_helper = BybitWsTradeHelper(api_key, api_secret, testnet, ws_recv_window)
        self._ws_private_helper = BybitWsPrivateHelper(api_key, api_secret, testnet)

        # Internal order tracking (orderId -> order_details)
        self.tracked_orders: dict[str, dict[str, Any]] = {}
        self._order_update_lock = threading.Lock() # Protects access to tracked_orders

        # Event to signal that private WS is connected and order stream is subscribed
        self._ws_private_ready_event = threading.Event()
        self._ws_private_thread: threading.Thread | None = None

        logger.info(f"BybitUnifiedOrderManager initialized. Default mode: '{self.default_mode}'. Testnet: {self.testnet}")

    def _start_ws_private_listener(self) -> None:
        """Starts the private WebSocket helper in a separate thread to listen for order updates.
        """
        if self._ws_private_thread and self._ws_private_thread.is_alive():
            logger.warning("Private WebSocket listener is already running.")
            return

        logger.info("Starting Private WebSocket listener thread for order updates...")
        self._ws_private_thread = threading.Thread(target=self._run_ws_private_helper_loop, daemon=True)
        self._ws_private_thread.start()

        # Wait for the private WS to be ready
        if not self._ws_private_ready_event.wait(timeout=15):
            logger.error("Timeout waiting for private WebSocket listener to become ready.")
            raise RuntimeError("Private WebSocket listener failed to start or sync.")
        logger.info("Private WebSocket listener thread ready and subscribed to order stream.")

    def _run_ws_private_helper_loop(self) -> None:
        """The main loop for the private WebSocket helper, run in a separate thread.
        """
        try:
            if self._ws_private_helper.connect(wait_for_connection=True, timeout=15):
                logger.info("Private WS helper connected. Subscribing to order stream...")
                self._ws_private_helper.subscribe_to_order_stream(self._on_private_order_update)
                self._ws_private_ready_event.set() # Signal that it's ready
                # Keep the thread alive while connected
                while self._ws_private_helper.is_connected():
                    time.sleep(1)
            else:
                logger.error("Failed to connect private WS helper in thread.")
        except Exception:
            logger.exception("Error in private WS helper thread.")
        finally:
            self._ws_private_helper.disconnect()
            self._ws_private_ready_event.clear()
            logger.info("Private WS helper thread finished.")

    def _on_private_order_update(self, message: dict[str, Any]) -> None:
        """Internal callback to process private order updates from WebSocket.
        Updates the `tracked_orders` dictionary.
        """
        data = message.get('data')
        if data:
            with self._order_update_lock:
                for order_update in data:
                    order_id = order_update.get('orderId')
                    if order_id and order_id in self.tracked_orders:
                        old_status = self.tracked_orders[order_id].get('orderStatus')
                        new_status = order_update.get('orderStatus')

                        # Only log and update if status has changed
                        if new_status and new_status != old_status:
                            logger.debug(f"Order {order_id} status changed from {old_status} to {new_status}")
                            # Update all fields for the tracked order
                            self.tracked_orders[order_id].update(order_update)
                        elif not new_status:
                             logger.warning(f"Order update for {order_id} received without new status: {order_update}")
                    elif order_id:
                        # If an order update comes for an untracked order, log it but don't add to tracked_orders
                        # (this manager only tracks orders it places or is explicitly told to track)
                        logger.debug(f"Received WS update for untracked order ID {order_id}: {order_update.get('orderStatus')}")

    def start(self) -> None:
        """Starts the necessary background services (e.g., WebSocket private listener).
        Must be called before performing any order operations that rely on WS tracking.
        """
        logger.info("Starting BybitUnifiedOrderManager services...")
        # Connect WS trading client if default mode is 'websocket'
        if self.default_mode == "websocket":
            if not self._ws_trade_helper.connect():
                logger.error("Failed to connect WebSocket Trading client for default mode 'websocket'.")
                raise RuntimeError("Failed to connect WebSocket Trading client.")

        self._start_ws_private_listener()
        logger.info("BybitUnifiedOrderManager services started.")

    def stop(self) -> None:
        """Stops all background services and disconnects WebSocket clients.
        """
        logger.info("Stopping BybitUnifiedOrderManager services...")
        self._ws_trade_helper.disconnect()
        if self._ws_private_helper:
            self._ws_private_helper.disconnect()
            if self._ws_private_thread and self._ws_private_thread.is_alive():
                self._ws_private_thread.join(timeout=5) # Wait for thread to finish
                if self._ws_private_thread.is_alive():
                    logger.warning("Private WS listener thread did not terminate gracefully.")
        logger.info("BybitUnifiedOrderManager services stopped.")

    def place_order(self,
                    category: str,
                    symbol: str,
                    side: str,
                    order_type: str,
                    qty: str,
                    price: str | None = None,
                    mode: TradingMode | None = None,
                    **kwargs) -> dict[str, Any] | None:
        """Places a new order using either HTTP or WebSocket.

        :param category: The product type.
        :param symbol: The trading symbol.
        :param side: The order direction ("Buy" or "Sell").
        :param order_type: The order type ("Limit" or "Market").
        :param qty: The quantity (as a string).
        :param price: Optional. The price for Limit orders (as a string).
        :param mode: Optional. Override the default trading mode ("http" or "websocket") for this specific call.
        :param kwargs: Additional optional parameters.
        :return: A dictionary containing the order placement response or None on failure.
        """
        actual_mode = mode if mode else self.default_mode
        response = None

        if actual_mode == "http":
            response = self._http_trade_helper.place_order(category, symbol, side, order_type, qty, price, **kwargs)
        elif actual_mode == "websocket":
            if not self._ws_trade_helper.is_connected():
                logger.error(f"WebSocket trading client not connected for placing order for {symbol}. Attempting to reconnect...")
                if not self._ws_trade_helper.connect():
                    logger.error("Failed to connect WebSocket trading client. Cannot place order via WS.")
                    return None

            # For WS, we need a callback to receive the response.
            # We'll use a local event and a temporary callback to get the response.
            ws_response_event = threading.Event()
            ws_response_data: dict[str, Any] = {}

            def _temp_ws_callback(message: dict[str, Any]) -> None:
                nonlocal ws_response_data
                ws_response_data.update(message)
                ws_response_event.set()

            self._ws_trade_helper.place_ws_order(_temp_ws_callback, category, symbol, side, order_type, qty, price, **kwargs)

            if not ws_response_event.wait(timeout=10): # Wait for WS response
                logger.error(f"Timeout waiting for WebSocket order placement response for {symbol}.")
                return None

            if ws_response_data.get('retCode') == 0:
                response = ws_response_data.get('data')
            else:
                logger.error(f"WS order placement failed: {ws_response_data.get('retMsg')}")
                return None
        else:
            logger.error(f"Unsupported trading mode: {actual_mode}")
            return None

        if response and response.get('orderId'):
            with self._order_update_lock:
                # Store the initial order details for tracking
                self.tracked_orders[response['orderId']] = {
                    'orderId': response['orderId'],
                    'orderLinkId': response.get('orderLinkId'),
                    'symbol': symbol,
                    'category': category,
                    'side': side,
                    'orderType': order_type,
                    'qty': qty,
                    'price': price,
                    'orderStatus': response.get('orderStatus', 'New'), # Default to 'New' if not provided
                    'placedTime': int(time.time() * 1000)
                }
            logger.info(f"Order {response['orderId']} added to tracking.")
        return response

    def amend_order(self,
                    category: str,
                    symbol: str,
                    order_id: str | None = None,
                    order_link_id: str | None = None,
                    new_qty: str | None = None,
                    new_price: str | None = None,
                    mode: TradingMode | None = None,
                    **kwargs) -> dict[str, Any] | None:
        """Amends an existing order using either HTTP or WebSocket.

        :param category: The product type.
        :param symbol: The trading symbol.
        :param order_id: Optional. The exchange-generated order ID.
        :param order_link_id: Optional. Your client-generated order ID.
        :param new_qty: Optional. The new quantity (as a string).
        :param new_price: Optional. The new price (as a string).
        :param mode: Optional. Override the default trading mode.
        :param kwargs: Additional optional parameters.
        :return: A dictionary containing the order amendment response or None on failure.
        """
        actual_mode = mode if mode else self.default_mode
        response = None

        if actual_mode == "http":
            response = self._http_trade_helper.amend_order(category, symbol, order_id, order_link_id, new_qty, new_price, **kwargs)
        elif actual_mode == "websocket":
            if not self._ws_trade_helper.is_connected():
                logger.error(f"WebSocket trading client not connected for amending order for {symbol}.")
                return None

            ws_response_event = threading.Event()
            ws_response_data: dict[str, Any] = {}

            def _temp_ws_callback(message: dict[str, Any]) -> None:
                nonlocal ws_response_data
                ws_response_data.update(message)
                ws_response_event.set()

            self._ws_trade_helper.amend_ws_order(_temp_ws_callback, category, symbol, order_id, order_link_id, new_qty, new_price, **kwargs)

            if not ws_response_event.wait(timeout=10):
                logger.error(f"Timeout waiting for WebSocket order amendment response for {symbol}.")
                return None

            if ws_response_data.get('retCode') == 0:
                response = ws_response_data.get('data')
            else:
                logger.error(f"WS order amendment failed: {ws_response_data.get('retMsg')}")
                return None
        else:
            logger.error(f"Unsupported trading mode: {actual_mode}")
            return None

        if response and response.get('orderId'):
            with self._order_update_lock:
                # Update tracked order if it exists
                if response['orderId'] in self.tracked_orders:
                    self.tracked_orders[response['orderId']].update({
                        'qty': new_qty if new_qty else self.tracked_orders[response['orderId']].get('qty'),
                        'price': new_price if new_price else self.tracked_orders[response['orderId']].get('price'),
                        'orderStatus': response.get('orderStatus', self.tracked_orders[response['orderId']].get('orderStatus')),
                        'amendedTime': int(time.time() * 1000)
                    })
            logger.info(f"Order {response['orderId']} amended and tracking updated.")
        return response

    def cancel_order(self,
                     category: str,
                     symbol: str,
                     order_id: str | None = None,
                     order_link_id: str | None = None,
                     mode: TradingMode | None = None) -> dict[str, Any] | None:
        """Cancels an active order using either HTTP or WebSocket.

        :param category: The product type.
        :param symbol: The trading symbol.
        :param order_id: Optional. The exchange-generated order ID.
        :param order_link_id: Optional. Your client-generated order ID.
        :param mode: Optional. Override the default trading mode.
        :return: A dictionary containing the order cancellation response or None on failure.
        """
        actual_mode = mode if mode else self.default_mode
        response = None

        if actual_mode == "http":
            response = self._http_trade_helper.cancel_order(category, symbol, order_id, order_link_id)
        elif actual_mode == "websocket":
            if not self._ws_trade_helper.is_connected():
                logger.error(f"WebSocket trading client not connected for cancelling order for {symbol}.")
                return None

            ws_response_event = threading.Event()
            ws_response_data: dict[str, Any] = {}

            def _temp_ws_callback(message: dict[str, Any]) -> None:
                nonlocal ws_response_data
                ws_response_data.update(message)
                ws_response_event.set()

            self._ws_trade_helper.cancel_ws_order(_temp_ws_callback, category, symbol, order_id, order_link_id)

            if not ws_response_event.wait(timeout=10):
                logger.error(f"Timeout waiting for WebSocket order cancellation response for {symbol}.")
                return None

            if ws_response_data.get('retCode') == 0:
                response = ws_response_data.get('data')
            else:
                logger.error(f"WS order cancellation failed: {ws_response_data.get('retMsg')}")
                return None
        else:
            logger.error(f"Unsupported trading mode: {actual_mode}")
            return None

        if response and response.get('orderId'):
            with self._order_update_lock:
                # Mark order as cancelled in tracking
                if response['orderId'] in self.tracked_orders:
                    self.tracked_orders[response['orderId']]['orderStatus'] = 'Cancelled'
                    self.tracked_orders[response['orderId']]['cancelledTime'] = int(time.time() * 1000)
            logger.info(f"Order {response['orderId']} cancelled and tracking updated.")
        return response

    def get_tracked_order(self, order_id: str) -> dict[str, Any] | None:
        """Retrieves the current tracked status of a specific order.

        :param order_id: The exchange-generated order ID.
        :return: A dictionary with the latest tracked order details or None if not found.
        """
        with self._order_update_lock:
            return self.tracked_orders.get(order_id)

    def get_all_tracked_orders(self) -> dict[str, dict[str, Any]]:
        """Retrieves all currently tracked orders.

        :return: A dictionary where keys are order IDs and values are order details.
        """
        with self._order_update_lock:
            return self.tracked_orders.copy()

    def get_open_orders(self, category: str, symbol: str | None = None, mode: TradingMode | None = None, **kwargs) -> dict[str, Any] | None:
        """Retrieves active open orders using either HTTP or WebSocket.
        Note: WebSocket trading client does not have a direct 'get_open_orders' equivalent.
        This will fall back to HTTP if WS is requested.

        :param category: The product type.
        :param symbol: Optional. The trading symbol.
        :param mode: Optional. Override the default trading mode.
        :param kwargs: Additional optional parameters.
        :return: A dictionary containing a list of open orders or None on failure.
        """
        actual_mode = mode if mode else self.default_mode
        if actual_mode == "websocket":
            logger.warning("WebSocket trading client does not support direct 'get_open_orders' query. Falling back to HTTP.")
            actual_mode = "http" # Force HTTP for queries

        return self._http_trade_helper.get_open_orders(category, symbol, **kwargs)

    def cancel_all_orders(self, category: str, symbol: str | None = None, mode: TradingMode | None = None, **kwargs) -> dict[str, Any] | None:
        """Cancels all active orders for a specific category and optionally a symbol.
        This operation is always performed via HTTP for robustness.

        :param category: The product type.
        :param symbol: Optional. The trading symbol.
        :param mode: Optional. Override the default trading mode (will always use HTTP for this operation).
        :param kwargs: Additional optional parameters.
        :return: A dictionary containing the cancellation response or None on failure.
        """
        logger.info(f"Cancelling all orders for {symbol if symbol else category} via HTTP (always uses HTTP for cancel_all_orders).")
        response = self._http_trade_helper.cancel_all_orders(category, symbol, **kwargs)

        if response and response.get('list'):
            with self._order_update_lock:
                for cancelled_order in response['list']:
                    order_id = cancelled_order.get('orderId')
                    if order_id and order_id in self.tracked_orders:
                        self.tracked_orders[order_id]['orderStatus'] = 'Cancelled'
                        self.tracked_orders[order_id]['cancelledTime'] = int(time.time() * 1000)
            logger.info("Tracked orders updated after mass cancellation.")
        return response


# Example Usage
if __name__ == "__main__":
    # IMPORTANT: Replace with your actual API key and secret.
    API_KEY = "YOUR_API_KEY"
    API_SECRET = "YOUR_API_SECRET"
    USE_TESTNET = True

    if API_KEY == "YOUR_API_KEY" or API_SECRET == "YOUR_API_SECRET":
        logger.error("Please replace YOUR_API_KEY and YOUR_API_SECRET with your actual credentials in bybit_unified_order_manager.py example.")
        # For demonstration, we'll proceed but expect API calls to fail.
        # exit()

    # Initialize the Unified Order Manager
    # You can set default_mode="websocket" for high-frequency trading
    order_manager = BybitUnifiedOrderManager(
        api_key=API_KEY,
        api_secret=API_SECRET,
        testnet=USE_TESTNET,
        default_mode="http" # Change to "websocket" to test WS trading operations
    )

    SYMBOL = "BTCUSDT"
    CATEGORY = "linear"
    ORDER_QTY = "0.001"

    try:
        # 1. Start the Unified Order Manager's services (private WS listener)
        order_manager.start()
        logger.info("Manager services started. Waiting for 5 seconds for WS to connect...")
        time.sleep(5) # Give time for WS to connect and subscribe

        # 2. Place an order (using default mode, e.g., HTTP)
        print(f"\n--- Placing a BUY Limit Order for {SYMBOL} (Mode: {order_manager.default_mode}) ---")
        client_order_id = f"unified-buy-{int(time.time())}"
        place_response = order_manager.place_order(
            category=CATEGORY,
            symbol=SYMBOL,
            side="Buy",
            order_type="Limit",
            qty=ORDER_QTY,
            price="40000", # Adjust price for testnet
            timeInForce="GTC",
            orderLinkId=client_order_id
        )
        placed_order_id = None
        if place_response:
            placed_order_id = place_response.get('orderId')
            logger.info(f"Order placed: {placed_order_id}, Client ID: {client_order_id}")
            # Give some time for WS update to reflect status
            time.sleep(2)
            tracked_order = order_manager.get_tracked_order(placed_order_id)
            if tracked_order:
                print(f"  Tracked order status: {tracked_order.get('orderStatus')}")
        else:
            print("  Failed to place order.")

        # 3. Amend the order (if placed successfully)
        if placed_order_id:
            print(f"\n--- Amending Order {placed_order_id} to new price (Mode: {order_manager.default_mode}) ---")
            amend_response = order_manager.amend_order(
                category=CATEGORY,
                symbol=SYMBOL,
                order_id=placed_order_id,
                new_price="40100" # Adjust price for testnet
            )
            if amend_response:
                logger.info(f"Order {placed_order_id} amended.")
                time.sleep(2)
                tracked_order = order_manager.get_tracked_order(placed_order_id)
                if tracked_order:
                    print(f"  Tracked order status after amendment: {tracked_order.get('orderStatus')}, new price: {tracked_order.get('price')}")
            else:
                print("  Failed to amend order.")

            # 4. Cancel the order
            print(f"\n--- Cancelling Order {placed_order_id} (Mode: {order_manager.default_mode}) ---")
            cancel_response = order_manager.cancel_order(
                category=CATEGORY,
                symbol=SYMBOL,
                order_id=placed_order_id
            )
            if cancel_response:
                logger.info(f"Order {placed_order_id} cancelled.")
                time.sleep(2)
                tracked_order = order_manager.get_tracked_order(placed_order_id)
                if tracked_order:
                    print(f"  Tracked order status after cancellation: {tracked_order.get('orderStatus')}")
            else:
                print("  Failed to cancel order.")

        # 5. Get open orders (always uses HTTP)
        print(f"\n--- Getting Open Orders for {SYMBOL} ---")
        open_orders = order_manager.get_open_orders(category=CATEGORY, symbol=SYMBOL)
        if open_orders and open_orders.get('list'):
            print("  Open Orders:")
            for order in open_orders['list']:
                print(f"    ID: {order.get('orderId')}, Side: {order.get('side')}, Price: {order.get('price')}, Status: {order.get('orderStatus')}")
        else:
            print("  No open orders or failed to retrieve.")

        # 6. Place another order, then cancel all orders (always uses HTTP for cancel_all)
        print("\n--- Placing another order for mass cancellation demo ---")
        client_order_id_2 = f"unified-sell-{int(time.time())}"
        order_manager.place_order(
            category=CATEGORY, symbol=SYMBOL, side="Sell", order_type="Limit", qty="0.001",
            price="45000", timeInForce="GTC", orderLinkId=client_order_id_2
        )
        time.sleep(2) # Give time to process

        print(f"\n--- Cancelling ALL orders for {SYMBOL} ---")
        cancel_all_response = order_manager.cancel_all_orders(category=CATEGORY, symbol=SYMBOL)
        if cancel_all_response:
            logger.info("All orders cancellation initiated.")
            time.sleep(3) # Give time for WS updates to come in
            print("  Current tracked orders after mass cancellation:")
            for oid, details in order_manager.get_all_tracked_orders().items():
                print(f"    Order ID: {oid}, Status: {details.get('orderStatus')}")
        else:
            print("  Failed to cancel all orders.")


    except Exception:
        logger.exception("An unhandled error occurred in the main execution block.")
    finally:
        order_manager.stop()
        logger.info("Unified Order Manager application finished.")
