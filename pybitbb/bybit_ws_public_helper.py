# bybit_ws_public_helper.py
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from pybit.exceptions import BybitWebsocketError
from pybit.unified_trading import WebSocket

# Configure logging for the module
logging.basicConfig(
    level=logging.INFO,  # Changed to INFO for less verbose default output, DEBUG for full details
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


class BybitWsPublicHelper:
    """A helper class for managing various public WebSocket data streams from Bybit,
    including tickers, klines, and trades.
    """

    def __init__(self, category: str, testnet: bool = False):
        """Initializes the BybitWsPublicHelper.

        :param category: The product category for the streams (e.g., "linear", "spot", "inverse", "option").
        :param testnet: Set to True to connect to the Bybit testnet, False for mainnet.
        """
        if not isinstance(category, str) or not category:
            logger.error("Category is required for BybitWsPublicHelper.")
            raise ValueError("Category must be provided.")

        self.category = category
        self.testnet = testnet
        self.websocket_client: WebSocket | None = None
        self._connection_lock = threading.Lock()
        self._is_connected_event = (
            threading.Event()
        )  # Event to signal connection status
        self._subscriptions: dict[
            str, tuple[Callable[[dict[str, Any]], None], dict[str, Any]],
        ] = {}  # {topic: (callback, kwargs)}

        logger.info(
            f"BybitWsPublicHelper initialized for category '{self.category}'. Testnet: {self.testnet}",
        )

    def _on_message(self, message: dict[str, Any]) -> None:
        """Internal callback to process incoming WebSocket messages.
        It dispatches messages to the appropriate user-defined callback based on the topic.
        """
        if not message:
            logger.warning(f"[{self.category}] Received empty WebSocket message.")
            return

        topic = message.get("topic")
        if not topic:
            logger.debug(
                f"[{self.category}] Received WebSocket message without topic: {message}",
            )
            return

        # Extract base topic for matching subscriptions (e.g., 'kline.1.BTCUSDT' -> 'kline')
        base_topic = topic.split(".")[0]

        # Find the specific subscription matching the topic
        # Iterate through subscriptions to find a match, as topics can be dynamic (e.g., kline.1m.BTCUSDT)
        matched_callback = None
        for sub_topic, (callback, sub_kwargs) in self._subscriptions.items():
            if sub_topic == topic:  # Exact match for specific topic
                matched_callback = callback
                break
            # Handle generic topic matches (e.g., 'kline' for 'kline.1m.BTCUSDT')
            # This requires careful design - for now, exact topic matching is safer.
            # For topics like 'kline.1.BTCUSDT', the subscription key should ideally be 'kline.1.BTCUSDT'
            # If a user subscribes to 'kline', they might expect all klines.
            # Pybit's WS client handles topic mapping, so we just need to ensure our subscription keys match.

        if matched_callback:
            try:
                matched_callback(message)
            except Exception as e:
                logger.exception(
                    f"[{self.category}] Error in user-defined callback for topic {topic}: {e}",
                )
        else:
            logger.debug(
                f"[{self.category}] No registered callback for topic: {topic}. Message: {message}",
            )

    def _on_connect(self) -> None:
        """Internal callback for WebSocket connection establishment."""
        logger.info(f"[{self.category}] WebSocket connected.")
        self._is_connected_event.set()
        # Re-subscribe to all active subscriptions upon reconnection
        self._resubscribe_all()

    def _on_disconnect(self) -> None:
        """Internal callback for WebSocket disconnection."""
        logger.warning(f"[{self.category}] WebSocket disconnected.")
        self._is_connected_event.clear()

    def _on_error(self, error_message: str) -> None:
        """Internal callback for WebSocket errors."""
        logger.error(f"[{self.category}] WebSocket error: {error_message}")
        self._is_connected_event.clear()

    def _resubscribe_all(self) -> None:
        """Re-subscribes to all active topics after a reconnection."""
        if self.websocket_client and self.websocket_client.is_connected():
            logger.info(
                f"[{self.category}] Re-subscribing to {len(self._subscriptions)} topics after reconnection.",
            )
            for topic, (callback, kwargs) in list(
                self._subscriptions.items(),
            ):  # Iterate over a copy
                # Pybit's WebSocket client handles the actual subscription logic based on topic names
                # We just need to call the appropriate method on the client.
                # This part is tricky as `pybit` doesn't expose a generic `subscribe` method for `WebSocket`.
                # Each stream type (ticker, kline, orderbook) has its own method.
                # For this helper, we'll assume the subscription methods are called externally.
                # A more robust solution would map `topic` to `pybit`'s specific subscription methods.
                # For now, this helper primarily manages the connection and message dispatch.
                # The actual `websocket_client.ticker_stream(...)` etc. calls happen in `subscribe_to_stream`.
                pass  # The actual subscription is handled by `subscribe_to_stream` which adds to `_subscriptions`
        else:
            logger.warning(
                f"[{self.category}] Cannot re-subscribe: WebSocket client not connected.",
            )

    def connect(self, wait_for_connection: bool = True, timeout: int = 10) -> bool:
        """Establishes the WebSocket connection.

        :param wait_for_connection: If True, blocks until connection is established or timeout.
        :param timeout: Maximum seconds to wait for connection if `wait_for_connection` is True.
        :return: True if connected (or connection attempt started), False on failure.
        """
        with self._connection_lock:
            if self.websocket_client and self.websocket_client.is_connected():
                logger.warning(
                    f"[{self.category}] WebSocket client is already connected.",
                )
                return True

            logger.info(
                f"[{self.category}] Connecting to WebSocket (Testnet: {self.testnet})...",
            )
            try:
                self.websocket_client = WebSocket(
                    testnet=self.testnet,
                    channel_type="public",
                    callback=self._on_message,  # Generic message callback
                    on_connect=self._on_connect,
                    on_disconnect=self._on_disconnect,
                    on_error=self._on_error,
                )

                if wait_for_connection:
                    if not self._is_connected_event.wait(timeout=timeout):
                        logger.error(
                            f"[{self.category}] Timeout waiting for WebSocket connection.",
                        )
                        self.websocket_client.close()  # Attempt to close if timeout
                        self.websocket_client = None
                        return False
                logger.info(f"[{self.category}] WebSocket client initiated.")
                return True
            except Exception as e:
                logger.exception(
                    f"[{self.category}] Failed to initialize WebSocket client: {e}",
                )
                self.websocket_client = None
                return False

    def disconnect(self) -> None:
        """Closes the WebSocket connection."""
        with self._connection_lock:
            if self.websocket_client:
                logger.info(
                    f"[{self.category}] Closing WebSocket connection for category '{self.category}'...",
                )
                self.websocket_client.close()
                self.websocket_client = None
                self._is_connected_event.clear()
                self._subscriptions.clear()  # Clear all subscriptions on disconnect
                logger.info(f"[{self.category}] WebSocket connection closed.")
            else:
                logger.info(
                    f"[{self.category}] WebSocket client not active for category '{self.category}'.",
                )

    def is_connected(self) -> bool:
        """Checks if the WebSocket client is currently connected."""
        return self._is_connected_event.is_set()

    def subscribe_to_stream(
        self,
        stream_type: str,
        callback: Callable[[dict[str, Any]], None],
        symbol: str,
        **kwargs,
    ) -> bool:
        """Subscribes to a specific public WebSocket stream.

        :param stream_type: The type of stream to subscribe to (e.g., "ticker", "kline", "trade", "orderbook").
        :param callback: A callable function to process messages from this specific stream.
        :param symbol: The trading symbol for the subscription (e.g., "BTCUSDT").
        :param kwargs: Additional parameters specific to the stream type (e.g., `interval` for kline, `depth` for orderbook).
        :return: True if subscription was successfully initiated, False otherwise.
        """
        if not self.is_connected():
            logger.error(
                f"[{self.category}] Cannot subscribe to {stream_type} for {symbol}: WebSocket not connected.",
            )
            return False
        if not isinstance(symbol, str) or not symbol:
            logger.error(
                f"[{self.category}] Invalid 'symbol' provided for subscription to {stream_type}.",
            )
            return False

        # Construct the topic string as pybit expects it for internal management
        # This part is critical for pybit's WebSocket client to correctly route messages
        topic = f"{stream_type}"
        if stream_type == "kline":
            interval = kwargs.get("interval", "1")
            topic = f"kline.{interval}.{symbol}"
        elif stream_type == "ticker":
            topic = f"tickers.{symbol}"
        elif stream_type == "trade":
            topic = f"publicTrades.{symbol}"
        elif stream_type == "orderbook":
            depth = kwargs.get("depth", 50)
            topic = f"orderbook.{depth}.{symbol}"
        elif stream_type == "liquidation":  # Deprecated, use all_liquidation_stream
            logger.warning(
                f"[{self.category}] 'liquidation' stream is deprecated. Consider using 'all_liquidation_stream'.",
            )
            topic = f"liquidation.{symbol}"
        elif stream_type == "all_liquidation":
            topic = "liquidation"  # This topic is for all symbols
            symbol = "ALL"  # Mark symbol as ALL for internal tracking
        else:
            logger.error(
                f"[{self.category}] Unsupported stream_type: {stream_type}. Cannot subscribe.",
            )
            return False

        if topic in self._subscriptions:
            logger.warning(
                f"[{self.category}] Already subscribed to topic: {topic}. Updating callback.",
            )

        # Store the user's specific callback and original kwargs
        # The _on_message will then dispatch to this specific callback if topic matches
        self._subscriptions[topic] = (callback, kwargs)

        # Call pybit's internal subscription method dynamically
        try:
            if stream_type == "kline":
                self.websocket_client.kline_stream(
                    interval=kwargs.get("interval", "1"),
                    symbol=symbol,
                    callback=self._on_message,
                )
            elif stream_type == "ticker":
                self.websocket_client.ticker_stream(
                    symbol=symbol, callback=self._on_message,
                )
            elif stream_type == "trade":
                self.websocket_client.trade_stream(
                    symbol=symbol, callback=self._on_message,
                )
            elif stream_type == "orderbook":
                self.websocket_client.orderbook_stream(
                    depth=kwargs.get("depth", 50),
                    symbol=symbol,
                    callback=self._on_message,
                )
            elif stream_type == "liquidation":
                self.websocket_client.liquidation_stream(
                    symbol=symbol, callback=self._on_message,
                )
            elif stream_type == "all_liquidation":
                self.websocket_client.all_liquidation_stream(callback=self._on_message)

            logger.info(
                f"[{self.category}] Successfully initiated subscription to {topic}.",
            )
            return True
        except BybitWebsocketError as e:
            logger.exception(
                f"[{self.category}] WebSocket error during subscription to {topic}: {e}",
            )
            del self._subscriptions[topic]  # Remove failed subscription
            return False
        except Exception as e:
            logger.exception(
                f"[{self.category}] Unexpected error during subscription to {topic}: {e}",
            )
            del self._subscriptions[topic]  # Remove failed subscription
            return False

    def unsubscribe_from_stream(self, stream_type: str, symbol: str, **kwargs) -> bool:
        """Unsubscribes from a specific public WebSocket stream.

        :param stream_type: The type of stream (e.g., "ticker", "kline").
        :param symbol: The trading symbol.
        :param kwargs: Additional parameters specific to the stream type (e.g., `interval` for kline, `depth` for orderbook).
        :return: True if successfully unsubscribed, False otherwise.
        """
        if not self.is_connected():
            logger.error(
                f"[{self.category}] Cannot unsubscribe from {stream_type} for {symbol}: WebSocket not connected.",
            )
            return False
        if not isinstance(symbol, str) or not symbol:
            logger.error(
                f"[{self.category}] Invalid 'symbol' provided for unsubscription from {stream_type}.",
            )
            return False

        topic = f"{stream_type}"
        if stream_type == "kline":
            interval = kwargs.get("interval", "1")
            topic = f"kline.{interval}.{symbol}"
        elif stream_type == "ticker":
            topic = f"tickers.{symbol}"
        elif stream_type == "trade":
            topic = f"publicTrades.{symbol}"
        elif stream_type == "orderbook":
            depth = kwargs.get("depth", 50)
            topic = f"orderbook.{depth}.{symbol}"
        elif stream_type == "liquidation":
            topic = f"liquidation.{symbol}"
        elif stream_type == "all_liquidation":
            topic = "liquidation"
            symbol = "ALL"
        else:
            logger.error(
                f"[{self.category}] Unsupported stream_type: {stream_type}. Cannot unsubscribe.",
            )
            return False

        if topic not in self._subscriptions:
            logger.warning(
                f"[{self.category}] Not subscribed to topic: {topic}. No action taken.",
            )
            return False

        try:
            # Pybit's WebSocket client automatically unsubscribes when `close()` is called,
            # or if a subscription method is called without a callback (which is not directly supported for unsubscribe).
            # The current pybit API doesn't expose an explicit `unsubscribe` method per topic.
            # The common pattern is to simply stop listening to messages for that topic.
            # If a true unsubscribe is needed on the network, it would require modifying pybit or
            # managing the raw WebSocket connection.
            # For this helper, removing from _subscriptions means we stop dispatching messages.
            del self._subscriptions[topic]
            logger.info(
                f"[{self.category}] Removed internal subscription for {topic}. Pybit's client does not expose direct unsubscribe per topic.",
            )
            return True
        except Exception as e:
            logger.exception(
                f"[{self.category}] Error during unsubscription from {topic}: {e}",
            )
            return False


# Example Usage
if __name__ == "__main__":
    # For public streams, API key/secret are not strictly needed, but can be passed.
    USE_TESTNET = True
    CATEGORY = "linear"  # Change as needed, e.g., "spot", "inverse", "option"
    SYMBOL = "BTCUSDT"

    public_ws_helper = BybitWsPublicHelper(category=CATEGORY, testnet=USE_TESTNET)

    # --- Define callback functions for different streams ---
    def handle_ticker_update(message: dict[str, Any]) -> None:
        data = message.get("data")
        if data:
            ticker = data[0]
            logger.info(
                f"[{ticker.get('symbol')}] Ticker Update: Last Price={ticker.get('lastPrice')}, Volume={ticker.get('volume24h')}",
            )

    def handle_kline_update(message: dict[str, Any]) -> None:
        data = message.get("data")
        if data:
            kline = data[0]
            logger.info(
                f"[{kline.get('symbol')}] Kline {kline.get('interval')} Update: Close={kline.get('close')}, Volume={kline.get('volume')}",
            )

    def handle_trade_update(message: dict[str, Any]) -> None:
        data = message.get("data")
        if data:
            trade = data[0]
            logger.info(
                f"[{trade.get('s')}] Trade: Price={trade.get('p')}, Qty={trade.get('v')}, Side={trade.get('S')}",
            )

    def handle_liquidation_update(message: dict[str, Any]) -> None:
        data = message.get("data")
        if data:
            liquidation = data[0]
            logger.warning(
                f"[LIQUIDATION] Symbol: {liquidation.get('s')}, Price: {liquidation.get('p')}, Qty: {liquidation.get('q')}, Side: {liquidation.get('S')}",
            )

    try:
        if public_ws_helper.connect(wait_for_connection=True, timeout=15):
            logger.info("Public WebSocket connected. Subscribing to streams...")

            # Subscribe to Ticker stream
            public_ws_helper.subscribe_to_stream("ticker", handle_ticker_update, SYMBOL)
            time.sleep(1)

            # Subscribe to 1-minute Kline stream
            public_ws_helper.subscribe_to_stream(
                "kline", handle_kline_update, SYMBOL, interval="1",
            )
            time.sleep(1)

            # Subscribe to Trade stream
            public_ws_helper.subscribe_to_stream("trade", handle_trade_update, SYMBOL)
            time.sleep(1)

            # Subscribe to All Liquidation stream (no specific symbol needed for 'all_liquidation')
            public_ws_helper.subscribe_to_stream(
                "all_liquidation", handle_liquidation_update, symbol="ALL",
            )
            time.sleep(1)

            print("\nListening to public streams for 30 seconds...")
            time.sleep(30)

            print("\nUnsubscribing from Ticker stream...")
            public_ws_helper.unsubscribe_from_stream("ticker", SYMBOL)
            print("Listening for another 10 seconds (ticker stream should stop)...")
            time.sleep(10)

        else:
            logger.error(
                "Failed to connect to Public WebSocket. Skipping subscriptions.",
            )

    except Exception:
        logger.exception("An error occurred in the main execution block.")
    finally:
        public_ws_helper.disconnect()
        logger.info("Public WebSocket application finished.")
