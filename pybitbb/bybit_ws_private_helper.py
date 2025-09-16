# bybit_ws_private_helper.py
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from pybit.exceptions import BybitWebsocketError
from pybit.unified_trading import WebSocket

# Configure logging for the module
logging.basicConfig(
    level=logging.INFO, # Changed to INFO for less verbose default output, DEBUG for full details
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BybitWsPrivateHelper:
    """A helper class for managing various private WebSocket data streams from Bybit,
    including wallet balance, position, order, and execution updates.
    These streams require API key authentication.
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """Initializes the BybitWsPrivateHelper.

        :param api_key: Your Bybit API key.
        :param api_secret: Your Bybit API secret.
        :param testnet: Set to True to connect to the Bybit testnet, False for mainnet.
        """
        if not api_key or not api_secret:
            logger.error("API Key and Secret are required for BybitWsPrivateHelper.")
            raise ValueError("API Key and Secret must be provided.")

        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.websocket_client: WebSocket | None = None
        self._connection_lock = threading.Lock()
        self._is_connected_event = threading.Event() # Event to signal connection status
        # Stores {topic: (callback, kwargs)} for re-subscription on reconnect
        self._subscriptions: dict[str, tuple[Callable[[dict[str, Any]], None], dict[str, Any]]] = {}

        logger.info(f"BybitWsPrivateHelper initialized for {'testnet' if self.testnet else 'mainnet'}.")

    def _on_message(self, message: dict[str, Any]) -> None:
        """Internal callback to process incoming WebSocket messages.
        It dispatches messages to the appropriate user-defined callback based on the topic.
        """
        if not message:
            logger.warning("Received empty WebSocket message.")
            return

        topic = message.get('topic')
        if not topic:
            logger.debug(f"Received WebSocket message without topic: {message}")
            return

        # Find the specific subscription matching the topic
        matched_callback = None
        for sub_topic, (callback, sub_kwargs) in self._subscriptions.items():
            # Private topics are usually exact matches (e.g., 'wallet', 'position.linear')
            if sub_topic == topic:
                matched_callback = callback
                break

        if matched_callback:
            try:
                matched_callback(message)
            except Exception as e:
                logger.exception(f"Error in user-defined callback for topic {topic}: {e}")
        else:
            logger.debug(f"No registered callback for topic: {topic}. Message: {message}")

    def _on_connect(self) -> None:
        """Internal callback for WebSocket connection establishment."""
        logger.info("WebSocket connected.")
        self._is_connected_event.set()
        # Re-subscribe to all active subscriptions upon reconnection
        self._resubscribe_all()

    def _on_disconnect(self) -> None:
        """Internal callback for WebSocket disconnection."""
        logger.warning("WebSocket disconnected.")
        self._is_connected_event.clear()

    def _on_error(self, error_message: str) -> None:
        """Internal callback for WebSocket errors."""
        logger.error(f"WebSocket error: {error_message}")
        self._is_connected_event.clear()

    def _resubscribe_all(self) -> None:
        """Re-subscribes to all active topics after a reconnection."""
        if self.websocket_client and self.websocket_client.is_connected():
            logger.info(f"Re-subscribing to {len(self._subscriptions)} private topics after reconnection.")
            for topic, (callback, kwargs) in list(self._subscriptions.items()): # Iterate over a copy
                # Pybit's WebSocket client handles the actual subscription logic based on topic names
                # We need to re-call the appropriate subscription method.
                # This requires mapping the generic topic string back to pybit's specific methods.
                try:
                    if topic == "wallet":
                        self.websocket_client.wallet_stream(callback=self._on_message)
                    elif topic.startswith("position."): # e.g., position.linear
                        # pybit's position_stream doesn't take 'category' directly in topic, but uses it internally
                        # The topic will be 'position' and the category is managed by pybit.
                        # For now, we'll call the generic position stream.
                        self.websocket_client.position_stream(callback=self._on_message)
                    elif topic == "order":
                        self.websocket_client.order_stream(callback=self._on_message)
                    elif topic == "execution":
                        self.websocket_client.execution_stream(callback=self._on_message)
                    elif topic == "greeks":
                        self.websocket_client.greek_stream(callback=self._on_message)
                    elif topic.startswith("fast_execution."): # e.g., fast_execution.linear
                        # pybit's fast_execution_stream takes 'categorised_topic'
                        cat_topic = topic.split('.', 1)[1] # 'linear' from 'fast_execution.linear'
                        self.websocket_client.fast_execution_stream(callback=self._on_message, categorised_topic=cat_topic)
                    else:
                        logger.warning(f"Attempted to re-subscribe to unknown private topic: {topic}. Skipping.")
                except Exception as e:
                    logger.error(f"Error re-subscribing to private topic {topic}: {e}", exc_info=True)
        else:
            logger.warning("Cannot re-subscribe: WebSocket client not connected.")

    def connect(self, wait_for_connection: bool = True, timeout: int = 10) -> bool:
        """Establishes the WebSocket connection.

        :param wait_for_connection: If True, blocks until connection is established or timeout.
        :param timeout: Maximum seconds to wait for connection if `wait_for_connection` is True.
        :return: True if connected (or connection attempt started), False on failure.
        """
        with self._connection_lock:
            if self.websocket_client and self.websocket_client.is_connected():
                logger.warning("WebSocket client is already connected.")
                return True

            logger.info(f"Connecting to private WebSocket (Testnet: {self.testnet})...")
            try:
                self.websocket_client = WebSocket(
                    testnet=self.testnet,
                    channel_type='private', # IMPORTANT: Use 'private' for authenticated streams
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    callback=self._on_message, # Generic message callback
                    on_connect=self._on_connect,
                    on_disconnect=self._on_disconnect,
                    on_error=self._on_error
                )

                if wait_for_connection:
                    if not self._is_connected_event.wait(timeout=timeout):
                        logger.error("Timeout waiting for private WebSocket connection.")
                        self.websocket_client.close() # Attempt to close if timeout
                        self.websocket_client = None
                        return False
                logger.info("Private WebSocket client initiated.")
                return True
            except Exception as e:
                logger.exception(f"Failed to initialize private WebSocket client: {e}")
                self.websocket_client = None
                return False

    def disconnect(self) -> None:
        """Closes the WebSocket connection.
        """
        with self._connection_lock:
            if self.websocket_client:
                logger.info("Closing private WebSocket connection...")
                self.websocket_client.close()
                self.websocket_client = None
                self._is_connected_event.clear()
                self._subscriptions.clear() # Clear all subscriptions on disconnect
                logger.info("Private WebSocket connection closed.")
            else:
                logger.info("Private WebSocket client not active.")

    def is_connected(self) -> bool:
        """Checks if the WebSocket client is currently connected.
        """
        return self._is_connected_event.is_set()

    def subscribe_to_wallet_stream(self, callback: Callable[[dict[str, Any]], None]) -> bool:
        """Subscribes to the real-time wallet balance update stream.

        :param callback: A callable function to process wallet updates.
        :return: True if subscription was successfully initiated, False otherwise.
        """
        if not self.is_connected():
            logger.error("Cannot subscribe to wallet stream: WebSocket not connected.")
            return False
        topic = "wallet"
        if topic in self._subscriptions:
            logger.warning("Already subscribed to wallet stream. Updating callback.")
        self._subscriptions[topic] = (callback, {})
        try:
            self.websocket_client.wallet_stream(callback=self._on_message)
            logger.info("Successfully initiated subscription to wallet stream.")
            return True
        except BybitWebsocketError as e:
            logger.exception(f"WebSocket error subscribing to wallet stream: {e}")
            del self._subscriptions[topic]
            return False
        except Exception as e:
            logger.exception(f"Unexpected error subscribing to wallet stream: {e}")
            del self._subscriptions[topic]
            return False

    def subscribe_to_position_stream(self, callback: Callable[[dict[str, Any]], None]) -> bool:
        """Subscribes to the real-time position update stream.
        This stream provides updates for all categories (linear, inverse, spot, option).

        :param callback: A callable function to process position updates.
        :return: True if subscription was successfully initiated, False otherwise.
        """
        if not self.is_connected():
            logger.error("Cannot subscribe to position stream: WebSocket not connected.")
            return False
        topic = "position"
        if topic in self._subscriptions:
            logger.warning("Already subscribed to position stream. Updating callback.")
        self._subscriptions[topic] = (callback, {})
        try:
            self.websocket_client.position_stream(callback=self._on_message)
            logger.info("Successfully initiated subscription to position stream.")
            return True
        except BybitWebsocketError as e:
            logger.exception(f"WebSocket error subscribing to position stream: {e}")
            del self._subscriptions[topic]
            return False
        except Exception as e:
            logger.exception(f"Unexpected error subscribing to position stream: {e}")
            del self._subscriptions[topic]
            return False

    def subscribe_to_order_stream(self, callback: Callable[[dict[str, Any]], None]) -> bool:
        """Subscribes to the real-time order update stream.
        This stream provides updates for all categories (linear, inverse, spot, option).

        :param callback: A callable function to process order updates.
        :return: True if subscription was successfully initiated, False otherwise.
        """
        if not self.is_connected():
            logger.error("Cannot subscribe to order stream: WebSocket not connected.")
            return False
        topic = "order"
        if topic in self._subscriptions:
            logger.warning("Already subscribed to order stream. Updating callback.")
        self._subscriptions[topic] = (callback, {})
        try:
            self.websocket_client.order_stream(callback=self._on_message)
            logger.info("Successfully initiated subscription to order stream.")
            return True
        except BybitWebsocketError as e:
            logger.exception(f"WebSocket error subscribing to order stream: {e}")
            del self._subscriptions[topic]
            return False
        except Exception as e:
            logger.exception(f"Unexpected error subscribing to order stream: {e}")
            del self._subscriptions[topic]
            return False

    def subscribe_to_execution_stream(self, callback: Callable[[dict[str, Any]], None]) -> bool:
        """Subscribes to the real-time execution update stream.
        This stream provides updates for all categories (linear, inverse, spot, option).

        :param callback: A callable function to process execution updates.
        :return: True if subscription was successfully initiated, False otherwise.
        """
        if not self.is_connected():
            logger.error("Cannot subscribe to execution stream: WebSocket not connected.")
            return False
        topic = "execution"
        if topic in self._subscriptions:
            logger.warning("Already subscribed to execution stream. Updating callback.")
        self._subscriptions[topic] = (callback, {})
        try:
            self.websocket_client.execution_stream(callback=self._on_message)
            logger.info("Successfully initiated subscription to execution stream.")
            return True
        except BybitWebsocketError as e:
            logger.exception(f"WebSocket error subscribing to execution stream: {e}")
            del self._subscriptions[topic]
            return False
        except Exception as e:
            logger.exception(f"Unexpected error subscribing to execution stream: {e}")
            del self._subscriptions[topic]
            return False

    def subscribe_to_fast_execution_stream(self, callback: Callable[[dict[str, Any]], None], categorised_topic: str) -> bool:
        """Subscribes to the real-time fast execution update stream for a specific category.
        This stream offers lower latency but with limited data fields.

        :param callback: A callable function to process fast execution updates.
        :param categorised_topic: The specific category topic (e.g., "linear", "spot").
        :return: True if subscription was successfully initiated, False otherwise.
        """
        if not self.is_connected():
            logger.error("Cannot subscribe to fast execution stream: WebSocket not connected.")
            return False
        if not isinstance(categorised_topic, str) or not categorised_topic:
            logger.error("Invalid 'categorised_topic' provided for fast execution stream.")
            return False

        topic = f"fast_execution.{categorised_topic}"
        if topic in self._subscriptions:
            logger.warning(f"Already subscribed to fast execution stream for {categorised_topic}. Updating callback.")
        self._subscriptions[topic] = (callback, {'categorised_topic': categorised_topic})
        try:
            self.websocket_client.fast_execution_stream(callback=self._on_message, categorised_topic=categorised_topic)
            logger.info(f"Successfully initiated subscription to fast execution stream for {categorised_topic}.")
            return True
        except BybitWebsocketError as e:
            logger.exception(f"WebSocket error subscribing to fast execution stream for {categorised_topic}: {e}")
            del self._subscriptions[topic]
            return False
        except Exception as e:
            logger.exception(f"Unexpected error subscribing to fast execution stream for {categorised_topic}: {e}")
            del self._subscriptions[topic]
            return False

    def subscribe_to_greek_stream(self, callback: Callable[[dict[str, Any]], None]) -> bool:
        """Subscribes to the real-time options Greeks data stream (Delta, Gamma, Theta, Vega).

        :param callback: A callable function to process Greeks updates.
        :return: True if subscription was successfully initiated, False otherwise.
        """
        if not self.is_connected():
            logger.error("Cannot subscribe to Greeks stream: WebSocket not connected.")
            return False
        topic = "greeks"
        if topic in self._subscriptions:
            logger.warning("Already subscribed to Greeks stream. Updating callback.")
        self._subscriptions[topic] = (callback, {})
        try:
            self.websocket_client.greek_stream(callback=self._on_message)
            logger.info("Successfully initiated subscription to Greeks stream.")
            return True
        except BybitWebsocketError as e:
            logger.exception(f"WebSocket error subscribing to Greeks stream: {e}")
            del self._subscriptions[topic]
            return False
        except Exception as e:
            logger.exception(f"Unexpected error subscribing to Greeks stream: {e}")
            del self._subscriptions[topic]
            return False


    def unsubscribe_from_stream(self, stream_type: str, **kwargs) -> bool:
        """Unsubscribes from a specific private WebSocket stream.
        Note: Pybit's WebSocket client typically handles unsubscription implicitly on close
        or by not re-subscribing. This method primarily removes the internal callback mapping.

        :param stream_type: The type of stream to unsubscribe from (e.g., "wallet", "position", "order", "execution", "greeks", "fast_execution").
        :param kwargs: Additional parameters to identify the topic (e.g., `categorised_topic` for fast_execution).
        :return: True if successfully removed from internal subscriptions, False otherwise.
        """
        topic = stream_type
        if stream_type == "fast_execution":
            categorised_topic = kwargs.get('categorised_topic')
            if not isinstance(categorised_topic, str) or not categorised_topic:
                logger.error("Invalid 'categorised_topic' for unsubscribing from fast execution stream.")
                return False
            topic = f"fast_execution.{categorised_topic}"

        if topic not in self._subscriptions:
            logger.warning(f"Not subscribed to topic: {topic}. No action taken.")
            return False

        try:
            del self._subscriptions[topic]
            logger.info(f"Removed internal subscription for {topic}. Note: Pybit's client does not expose direct unsubscribe per topic over network.")
            return True
        except Exception as e:
            logger.exception(f"Error during unsubscription from {topic}: {e}")
            return False


# Example Usage
if __name__ == "__main__":
    # IMPORTANT: Replace with your actual API key and secret.
    # For security, consider using environment variables (e.g., os.getenv("BYBIT_API_KEY")).
    # Set USE_TESTNET to False for production (mainnet).
    API_KEY = "YOUR_API_KEY"
    API_SECRET = "YOUR_API_SECRET"
    USE_TESTNET = True

    if API_KEY == "YOUR_API_KEY" or API_SECRET == "YOUR_API_SECRET":
        logger.error("Please replace YOUR_API_KEY and YOUR_API_SECRET with your actual credentials in bybit_ws_private_helper.py example.")
        # For demonstration, we'll proceed but expect API calls to fail.
        # exit()

    private_ws_helper = BybitWsPrivateHelper(API_KEY, API_SECRET, testnet=USE_TESTNET)

    # --- Define callback functions for different private streams ---
    def handle_wallet_update(message: dict[str, Any]) -> None:
        data = message.get('data')
        if data:
            for wallet_info in data:
                logger.info(f"Wallet Update: Account={wallet_info.get('accountType')}, Equity={wallet_info.get('totalEquity')}, Coin='{wallet_info.get('coin', [{}])[0].get('coin')}', Available={wallet_info.get('coin', [{}])[0].get('availableToWithdraw')}")

    def handle_position_update(message: dict[str, Any]) -> None:
        data = message.get('data')
        if data:
            for position in data:
                logger.info(f"Position Update: Symbol={position.get('symbol')}, Side={position.get('side')}, Size={position.get('size')}, PnL={position.get('unrealisedPnl')}")

    def handle_order_update(message: dict[str, Any]) -> None:
        data = message.get('data')
        if data:
            for order in data:
                logger.info(f"Order Update: Symbol={order.get('symbol')}, Side={order.get('side')}, Type={order.get('orderType')}, Status={order.get('orderStatus')}, Price={order.get('price')}, Qty={order.get('qty')}")

    def handle_execution_update(message: dict[str, Any]) -> None:
        data = message.get('data')
        if data:
            for execution in data:
                logger.info(f"Execution Update: Symbol={execution.get('symbol')}, Price={execution.get('execPrice')}, Qty={execution.get('execQty')}, Side={execution.get('side')}, Fee={execution.get('execFee')}")

    def handle_fast_execution_update(message: dict[str, Any]) -> None:
        data = message.get('data')
        if data:
            for execution in data:
                logger.debug(f"Fast Execution Update: Symbol={execution.get('s')}, Price={execution.get('p')}, Qty={execution.get('q')}")

    def handle_greeks_update(message: dict[str, Any]) -> None:
        data = message.get('data')
        if data:
            for greeks in data:
                logger.info(f"Greeks Update: Symbol={greeks.get('symbol')}, Delta={greeks.get('delta')}, Gamma={greeks.get('gamma')}")

    try:
        if private_ws_helper.connect(wait_for_connection=True, timeout=15):
            logger.info("Private WebSocket connected. Subscribing to streams...")

            # Subscribe to Wallet stream
            private_ws_helper.subscribe_to_wallet_stream(handle_wallet_update)
            time.sleep(1)

            # Subscribe to Position stream
            private_ws_helper.subscribe_to_position_stream(handle_position_update)
            time.sleep(1)

            # Subscribe to Order stream
            private_ws_helper.subscribe_to_order_stream(handle_order_update)
            time.sleep(1)

            # Subscribe to Execution stream
            private_ws_helper.subscribe_to_execution_stream(handle_execution_update)
            time.sleep(1)

            # Subscribe to Fast Execution stream for 'linear' category
            # Note: Fast execution stream is usually for derivatives.
            private_ws_helper.subscribe_to_fast_execution_stream(handle_fast_execution_update, categorised_topic="linear")
            time.sleep(1)

            # Subscribe to Greeks stream (primarily for options)
            # private_ws_helper.subscribe_to_greek_stream(handle_greeks_update)
            # time.sleep(1)

            print("\nListening to private streams for 60 seconds...")
            time.sleep(60)

            print("\nUnsubscribing from Wallet stream...")
            private_ws_helper.unsubscribe_from_stream("wallet")
            print("Listening for another 10 seconds (wallet updates should stop)...")
            time.sleep(10)

        else:
            logger.error("Failed to connect to Private WebSocket. Skipping subscriptions.")

    except Exception:
        logger.exception("An error occurred in the main execution block.")
    finally:
        private_ws_helper.disconnect()
        logger.info("Private WebSocket application finished.")
