l# bybit_ws_trade_helper.py
import logging
import time
import threading
from typing import Dict, Any, Optional, Callable, List, Union

from pybit.unified_trading import WebSocketTrading
from pybit.exceptions import BybitWebsocketError # Specific WebSocket error

# Configure logging for the module
logging.basicConfig(
    level=logging.INFO, # Changed to INFO for less verbose default output, DEBUG for full details
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BybitWsTradeHelper:
    """
    A helper class for high-frequency trading operations (orders and positions)
    via Pybit's WebSocket Trading interface. Offers lower latency compared to HTTP.
    All operations are asynchronous and rely on callback functions for responses.
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False, recv_window: int = 5000):
        """
        Initializes the BybitWsTradeHelper.

        :param api_key: Your Bybit API key.
        :param api_secret: Your Bybit API secret.
        :param testnet: Set to True to connect to the Bybit testnet, False for mainnet.
        :param recv_window: The maximum time (in milliseconds) for the request to be valid
                            on the server side. Default is 5000ms.
        """
        if not api_key or not api_secret:
            logger.error("API Key and Secret are required for BybitWsTradeHelper.")
            raise ValueError("API Key and Secret must be provided.")

        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.recv_window = recv_window
        self.ws_trading_client: Optional[WebSocketTrading] = None
        self._connection_lock = threading.Lock() # To manage connection state safely
        logger.info(f"BybitWsTradeHelper initialized for {'testnet' if self.testnet else 'mainnet'}.")

    def connect(self) -> bool:
        """
        Establishes the WebSocket Trading connection.
        This method is blocking until the connection is attempted.

        :return: True if the connection client was successfully initialized, False otherwise.
                 Note: Actual WebSocket connection status needs to be verified via callbacks or `is_connected()`.
        """
        with self._connection_lock:
            if self.ws_trading_client and self.ws_trading_client.is_connected():
                logger.warning("WebSocket Trading client is already connected.")
                return True

            logger.info(f"Connecting to WebSocket Trading (Testnet: {self.testnet})...")
            try:
                self.ws_trading_client = WebSocketTrading(
                    testnet=self.testnet,
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    recv_window=self.recv_window
                )
                # pybit's WebSocketTrading handles its own connection loop in a separate thread.
                # We can't directly get a sync 'connected' status here without waiting for a callback.
                # For simplicity, we assume initialization is successful.
                logger.info("WebSocket Trading client initiated. Connection status will be reflected in response callbacks.")
                return True
            except Exception as e:
                logger.exception(f"Failed to initialize WebSocket Trading client: {e}")
                self.ws_trading_client = None
                return False

    def disconnect(self) -> None:
        """
        Closes the WebSocket Trading connection.
        """
        with self._connection_lock:
            if self.ws_trading_client:
                logger.info("Closing WebSocket Trading connection...")
                self.ws_trading_client.close()
                self.ws_trading_client = None
                logger.info("WebSocket Trading connection closed.")
            else:
                logger.info("WebSocket Trading client not active.")

    def is_connected(self) -> bool:
        """
        Checks if the WebSocket Trading client is currently connected.

        :return: True if connected, False otherwise.
        """
        with self._connection_lock:
            return self.ws_trading_client is not None and self.ws_trading_client.is_connected()

    def _validate_order_params(self, category: str, symbol: str, side: str, order_type: str, qty: str, price: Optional[str]) -> bool:
        """Internal validation for common order parameters."""
        if not all(isinstance(arg, str) and arg for arg in [category, symbol, side, order_type, qty]):
            logger.error(f"Invalid or empty string provided for required order parameters. Category: '{category}', Symbol: '{symbol}', Side: '{side}', OrderType: '{order_type}', Qty: '{qty}'")
            return False
        
        try:
            float(qty)
            if price is not None:
                float(price)
        except ValueError:
            logger.error(f"Invalid numerical format for qty ('{qty}') or price ('{price}').")
            return False

        if order_type == 'Limit' and price is None:
            logger.error("Price is required for Limit orders.")
            return False
        if order_type == 'Market' and price is not None:
            logger.warning("Price is ignored for Market orders but was provided.")
        
        return True

    def place_ws_order(self,
                       callback: Callable[[Dict[str, Any]], None],
                       category: str,
                       symbol: str,
                       side: str,
                       order_type: str,
                       qty: str,
                       price: Optional[str] = None,
                       **kwargs) -> None:
        """
        Places a new order via WebSocket. The response will be sent to the provided callback.

        :param callback: A callable function (e.g., `def handle_response(message: Dict[str, Any]): ...`)
                         to process the API response.
        :param category: The product type (e.g., "spot", "linear", "inverse", "option").
        :param symbol: The trading symbol (e.g., "BTCUSDT").
        :param side: The order direction ("Buy" or "Sell").
        :param order_type: The order type ("Limit" or "Market").
        :param qty: The quantity to buy or sell (as a string).
        :param price: Optional. The price for Limit orders (as a string). Required for Limit order.
        :param kwargs: Additional optional parameters (e.g., `timeInForce`, `orderLinkId`, `takeProfit`, `stopLoss`).
        """
        if not self.is_connected():
            logger.error("Cannot place WS order: WebSocket Trading client is not connected.")
            return
        if not self._validate_order_params(category, symbol, side, order_type, qty, price):
            logger.error(f"Invalid parameters for placing WS order for {symbol}.")
            return
        
        request_params: Dict[str, Any] = {
            'category': category,
            'symbol': symbol,
            'side': side,
            'orderType': order_type,
            'qty': qty
        }
        if price:
            request_params['price'] = price
        request_params.update(kwargs)

        logger.debug(f"Placing WS order for {symbol}: {request_params}")
        try:
            self.ws_trading_client.place_order(callback=callback, request=request_params)
        except BybitWebsocketError as e:
            logger.exception(f"WebSocket error placing order for {symbol}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error placing WS order for {symbol}: {e}")

    def amend_ws_order(self,
                       callback: Callable[[Dict[str, Any]], None],
                       category: str,
                       symbol: str,
                       order_id: Optional[str] = None,
                       order_link_id: Optional[str] = None,
                       new_qty: Optional[str] = None,
                       new_price: Optional[str] = None,
                       **kwargs) -> None:
        """
        Amends an existing order via WebSocket by its `order_id` or `order_link_id`.
        The response will be sent to the provided callback.

        :param callback: A callable function to process the API response.
        :param category: The product type.
        :param symbol: The trading symbol.
        :param order_id: Optional. The exchange-generated order ID.
        :param order_link_id: Optional. Your client-generated order ID.
        :param new_qty: Optional. The new quantity for the order (as a string).
        :param new_price: Optional. The new price for the order (as a string).
        :param kwargs: Additional optional parameters.
        """
        if not self.is_connected():
            logger.error("Cannot amend WS order: WebSocket Trading client is not connected.")
            return
        if not all(isinstance(arg, str) and arg for arg in [category, symbol]):
            logger.error("Invalid or empty string provided for category or symbol.")
            return
        if not (order_id or order_link_id):
            logger.error("Either 'order_id' or 'order_link_id' must be provided to amend an order.")
            return
        if not (new_qty or new_price):
            logger.error("Either 'new_qty' or 'new_price' must be provided to amend an order.")
            return
        try:
            if new_qty is not None: float(new_qty)
            if new_price is not None: float(new_price)
        except ValueError:
            logger.error(f"Invalid numerical format for new_qty ('{new_qty}') or new_price ('{new_price}').")
            return

        request_params: Dict[str, Any] = {
            'category': category,
            'symbol': symbol,
        }
        if order_id:
            request_params['orderId'] = order_id
        if order_link_id:
            request_params['orderLinkId'] = order_link_id
        if new_qty:
            request_params['qty'] = new_qty
        if new_price:
            request_params['price'] = new_price
        request_params.update(kwargs)

        logger.debug(f"Amending WS order for {symbol}: {request_params}")
        try:
            self.ws_trading_client.amend_order(callback=callback, request=request_params)
        except BybitWebsocketError as e:
            logger.exception(f"WebSocket error amending order for {symbol}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error amending WS order for {symbol}: {e}")

    def cancel_ws_order(self,
                        callback: Callable[[Dict[str, Any]], None],
                        category: str,
                        symbol: str,
                        order_id: Optional[str] = None,
                        order_link_id: Optional[str] = None) -> None:
        """
        Cancels an active order via WebSocket by its `order_id` or `order_link_id`.
        The response will be sent to the provided callback.

        :param callback: A callable function to process the API response.
        :param category: The product type.
        :param symbol: The trading symbol.
        :param order_id: Optional. The exchange-generated order ID.
        :param order_link_id: Optional. Your client-generated order ID.
        """
        if not self.is_connected():
            logger.error("Cannot cancel WS order: WebSocket Trading client is not connected.")
            return
        if not all(isinstance(arg, str) and arg for arg in [category, symbol]):
            logger.error("Invalid or empty string provided for category or symbol.")
            return
        if not (order_id or order_link_id):
            logger.error("Either 'order_id' or 'order_link_id' must be provided to cancel an order.")
            return

        request_params: Dict[str, Any] = {
            'category': category,
            'symbol': symbol,
        }
        if order_id:
            request_params['orderId'] = order_id
        if order_link_id:
            request_params['orderLinkId'] = order_link_id

        logger.debug(f"Cancelling WS order for {symbol}: {request_params}")
        try:
            self.ws_trading_client.cancel_order(callback=callback, request=request_params)
        except BybitWebsocketError as e:
            logger.exception(f"WebSocket error cancelling order for {symbol}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error cancelling WS order for {symbol}: {e}")

    def place_batch_ws_order(self,
                             callback: Callable[[Dict[str, Any]], None],
                             category: str,
                             requests: List[Dict[str, Any]]) -> None:
        """
        Places multiple orders in a single batch request via WebSocket.
        Each item in 'requests' list should be a dictionary of order parameters.
        The response will be sent to the provided callback.

        :param callback: A callable function to process the API response.
        :param category: The product type.
        :param requests: A list of dictionaries, where each dict contains parameters for a single order.
                         Each order dict should have 'symbol', 'side', 'orderType', 'qty', and optionally 'price', 'orderLinkId', etc.
        """
        if not self.is_connected():
            logger.error("Cannot place WS batch orders: WebSocket Trading client is not connected.")
            return
        if not isinstance(category, str) or not category:
            logger.error("Invalid or empty string provided for category for batch order.")
            return
        if not isinstance(requests, list) or not requests:
            logger.error("Requests must be a non-empty list of dictionaries for batch order.")
            return
        # Basic validation for each request in the batch
        for req in requests:
            if not self._validate_order_params(category, req.get('symbol', ''), req.get('side', ''), req.get('orderType', ''), req.get('qty', ''), req.get('price')):
                logger.error(f"Invalid order parameters found in batch request: {req}. Aborting batch.")
                return

        logger.debug(f"Placing WS batch orders ({len(requests)}): {requests}")
        try:
            self.ws_trading_client.place_batch_order(callback=callback, category=category, request=requests)
        except BybitWebsocketError as e:
            logger.exception(f"WebSocket error placing batch orders: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error placing WS batch orders: {e}")

    def amend_batch_ws_order(self,
                             callback: Callable[[Dict[str, Any]], None],
                             category: str,
                             requests: List[Dict[str, Any]]) -> None:
        """
        Amends multiple orders in a single batch request via WebSocket.
        Each item in 'requests' list should be a dictionary with orderId/orderLinkId and new parameters.
        The response will be sent to the provided callback.

        :param callback: A callable function to process the API response.
        :param category: The product type.
        :param requests: A list of dictionaries, where each dict contains parameters for amending a single order.
                         Each amend dict should have 'symbol', and either 'orderId' or 'orderLinkId',
                         and at least one of 'qty' or 'price'.
        """
        if not self.is_connected():
            logger.error("Cannot amend WS batch orders: WebSocket Trading client is not connected.")
            return
        if not isinstance(category, str) or not category:
            logger.error("Invalid or empty string provided for category for batch amendment.")
            return
        if not isinstance(requests, list) or not requests:
            logger.error("Requests must be a non-empty list of dictionaries for batch amendment.")
            return
        # Basic validation for each request in the batch
        for req in requests:
            if not (req.get('orderId') or req.get('orderLinkId')):
                logger.error(f"Batch amend request missing 'orderId' or 'orderLinkId': {req}. Aborting batch.")
                return
            if not (req.get('qty') or req.get('price')):
                logger.error(f"Batch amend request missing 'qty' or 'price': {req}. Aborting batch.")
                return
            try:
                if req.get('qty') is not None: float(req['qty'])
                if req.get('price') is not None: float(req['price'])
            except ValueError:
                logger.error(f"Invalid numerical format in batch amend request: {req}. Aborting batch.")
                return

        logger.debug(f"Amending WS batch orders ({len(requests)}): {requests}")
        try:
            self.ws_trading_client.amend_batch_order(callback=callback, category=category, request=requests)
        except BybitWebsocketError as e:
            logger.exception(f"WebSocket error amending batch orders: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error amending WS batch orders: {e}")

    def cancel_batch_ws_order(self,
                              callback: Callable[[Dict[str, Any]], None],
                              category: str,
                              requests: List[Dict[str, Any]]) -> None:
        """
        Cancels multiple orders in a single batch request via WebSocket.
        Each item in 'requests' list should be a dictionary with orderId/orderLinkId.
        The response will be sent to the provided callback.

        :param callback: A callable function to process the API response.
        :param category: The product type.
        :param requests: A list of dictionaries, where each dict contains parameters for cancelling a single order.
                         Each cancel dict should have 'symbol', and either 'orderId' or 'orderLinkId'.
        """
        if not self.is_connected():
            logger.error("Cannot cancel WS batch orders: WebSocket Trading client is not connected.")
            return
        if not isinstance(category, str) or not category:
            logger.error("Invalid or empty string provided for category for batch cancellation.")
            return
        if not isinstance(requests, list) or not requests:
            logger.error("Requests must be a non-empty list of dictionaries for batch cancellation.")
            return
        # Basic validation for each request in the batch
        for req in requests:
            if not (req.get('orderId') or req.get('orderLinkId')):
                logger.error(f"Batch cancel request missing 'orderId' or 'orderLinkId': {req}. Aborting batch.")
                return
            if not isinstance(req.get('symbol'), str) or not req.get('symbol'):
                 logger.error(f"Batch cancel request missing 'symbol' or invalid type: {req}. Aborting batch.")
                 return

        logger.debug(f"Cancelling WS batch orders ({len(requests)}): {requests}")
        try:
            self.ws_trading_client.cancel_batch_order(callback=callback, category=category, request=requests)
        except BybitWebsocketError as e:
            logger.exception(f"WebSocket error cancelling batch orders: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error cancelling WS batch orders: {e}")


# Example Usage
if __name__ == "__main__":
    # IMPORTANT: Replace with your actual API key and secret.
    # For security, consider using environment variables (e.g., os.getenv("BYBIT_API_KEY")).
    # Set USE_TESTNET to False for production (mainnet).
    API_KEY = "YOUR_API_KEY"
    API_SECRET = "YOUR_API_SECRET"
    USE_TESTNET = True

    if API_KEY == "YOUR_API_KEY" or API_SECRET == "YOUR_API_SECRET":
        logger.error("Please replace YOUR_API_KEY and YOUR_API_SECRET with your actual credentials in bybit_ws_trade_helper.py example.")
        # For demonstration, we'll proceed but expect API calls to fail.
        # exit()
        pass

    ws_trade_helper = BybitWsTradeHelper(API_KEY, API_SECRET, testnet=USE_TESTNET)

    SYMBOL = "BTCUSDT"
    CATEGORY = "linear"

    # Define a callback function to handle responses from WebSocket trading operations
    def handle_ws_response(message: Dict[str, Any]) -> None:
        op = message.get('op')
        ret_code = message.get('retCode')
        ret_msg = message.get('retMsg')
        data = message.get('data')

        if ret_code == 0:
            logger.info(f"WS Trading Response - {op} SUCCESS: {ret_msg}. Data: {data}")
        else:
            logger.error(f"WS Trading Response - {op} FAILED: {ret_msg}. Code: {ret_code}. Data: {data}")

    try:
        if ws_trade_helper.connect():
            logger.info("WebSocket Trading client connected successfully. Waiting for operations...")
            time.sleep(2) # Give some time for the WebSocket connection to establish fully

            # --- Place a single order via WebSocket ---
            print(f"\n--- Placing a BUY Limit Order for {SYMBOL} via WS ---")
            client_order_id_ws_buy = f"ws-buy-{int(time.time())}"
            ws_trade_helper.place_ws_order(
                callback=handle_ws_response,
                category=CATEGORY,
                symbol=SYMBOL,
                side="Buy",
                order_type="Limit",
                qty="0.001",
                price="40000", # Adjust price for testnet
                timeInForce="GTC",
                orderLinkId=client_order_id_ws_buy
            )
            time.sleep(1) # Allow time for response

            # --- Place a batch of orders via WebSocket ---
            print(f"\n--- Placing a Batch of Orders for {SYMBOL} via WS ---")
            batch_requests = [
                {
                    'symbol': SYMBOL, 'side': 'Sell', 'orderType': 'Limit', 'qty': '0.001', 'price': '45000',
                    'orderLinkId': f"ws-batch-sell-1-{int(time.time())}", 'timeInForce': 'GTC'
                },
                {
                    'symbol': SYMBOL, 'side': 'Buy', 'orderType': 'Limit', 'qty': '0.001', 'price': '35000',
                    'orderLinkId': f"ws-batch-buy-1-{int(time.time())}", 'timeInForce': 'GTC'
                }
            ]
            ws_trade_helper.place_batch_ws_order(callback=handle_ws_response, category=CATEGORY, requests=batch_requests)
            time.sleep(2) # Allow time for responses

            # --- Amend a single order via WebSocket (using the client_order_id from the first order) ---
            print(f"\n--- Amending Order {client_order_id_ws_buy} via WS ---")
            ws_trade_helper.amend_ws_order(
                callback=handle_ws_response,
                category=CATEGORY,
                symbol=SYMBOL,
                order_link_id=client_order_id_ws_buy,
                new_price="40500" # New price
            )
            time.sleep(1) # Allow time for response

            # --- Cancel a single order via WebSocket (using the client_order_id from the first order) ---
            print(f"\n--- Cancelling Order {client_order_id_ws_buy} via WS ---")
            ws_trade_helper.cancel_ws_order(
                callback=handle_ws_response,
                category=CATEGORY,
                symbol=SYMBOL,
                order_link_id=client_order_id_ws_buy
            )
            time.sleep(1) # Allow time for response

            # --- Cancel a batch of orders via WebSocket (using client_order_ids from the batch) ---
            print(f"\n--- Cancelling Batch Orders via WS ---")
            cancel_batch_requests = [
                {'symbol': SYMBOL, 'orderLinkId': batch_requests[0]['orderLinkId']},
                {'symbol': SYMBOL, 'orderLinkId': batch_requests[1]['orderLinkId']}
            ]
            ws_trade_helper.cancel_batch_ws_order(callback=handle_ws_response, category=CATEGORY, requests=cancel_batch_requests)
            time.sleep(2) # Allow time for responses

        else:
            logger.error("Failed to connect to WebSocket Trading. Skipping operations.")

    except Exception as e:
        logger.exception("An error occurred in the main execution block.")
    finally:
        ws_trade_helper.disconnect()
        logger.info("WebSocket trading application finished.")
