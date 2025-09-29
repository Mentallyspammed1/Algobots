import asyncio
import json
import os
from typing import Any

from colorama import Fore, Style, init
from dotenv import load_dotenv
from loguru import logger
from pybit.unified_trading import HTTP
from pybit.websocket.websocket_client import WebsocketClient

# --- Initialize Colorama ---
init(autoreset=True)

# --- Load Environment Variables ---
load_dotenv()


class BybitClient:
    """A unified client for interacting with Bybit's V5 API (HTTP and WebSocket).
    Incorporates Pyrmethus's persona for enhanced logging.
    """

    def __init__(self):
        self.logger = logger  # Use the global logger instance
        self.logger.info(
            Fore.MAGENTA
            + "# Pyrmethus: Forging the Bybit API conduit... #"
            + Style.RESET_ALL
        )

        # --- API Credentials and Configuration ---
        self.api_key = os.getenv("BYBIT_API_KEY")
        self.api_secret = os.getenv("BYBIT_API_SECRET")
        self.testnet = os.getenv("BYBIT_TESTNET", "True").lower() == "true"
        # self.account_type = os.getenv('BYBIT_ACCOUNT_TYPE', 'UNIFIED') # Example for account type

        if not self.api_key or not self.api_secret:
            self.logger.error(
                Fore.RED
                + "  # ERROR: BYBIT_API_KEY or BYBIT_API_SECRET not found. Please set them in your .env file."
                + Style.RESET_ALL
            )
            raise ValueError("API Key or Secret not found. Please configure them.")

        self.http_client: HTTP | None = None
        self.ws_client: WebsocketClient | None = None

        # --- WebSocket Data Storage ---
        self.websocket_data: dict[str, Any] = {
            "kline": {},  # Stores latest kline data per symbol/interval
            "position": {},  # Stores latest position data per symbol
            "order": {},  # Stores latest order updates
            "tickers": {},
            "orderbook": {},
            "trades": {},
        }
        self.subscribed_topics = set()
        self.websocket_connected = False
        self.websocket_reconnect_delay = int(
            os.getenv("WEBSOCKET_RECONNECT_DELAY", 5)
        )  # Default 5 seconds

    async def initialize(self):
        """Initializes HTTP and WebSocket clients."""
        self.logger.info(
            Fore.CYAN + "  # Initializing Bybit HTTP client..." + Style.RESET_ALL
        )
        try:
            self.http_client = HTTP(
                testnet=self.testnet,
                api_key=self.api_key,
                api_secret=self.api_secret,
                # account_type=self.account_type # Uncomment if needed
            )
            self.logger.success(
                Fore.GREEN
                + "  # Bybit HTTP client initialized successfully."
                + Style.RESET_ALL
            )

            # Verify connection by fetching server time
            await self.verify_connection()

        except Exception as e:
            self.logger.error(
                Fore.RED
                + f"  # Failed to initialize HTTP client: {e}"
                + Style.RESET_ALL
            )
            raise

        self.logger.info(
            Fore.CYAN + "  # Initializing Bybit WebSocket client..." + Style.RESET_ALL
        )
        try:
            # The pybit WebsocketClient needs a callback function to handle messages
            self.ws_client = WebsocketClient(
                on_message=self.handle_websocket_message,
                on_open=self.on_websocket_open,
                on_close=self.on_websocket_close,
                on_error=self.on_websocket_error,
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet,
                # account_type=self.account_type # Uncomment if needed
            )
            self.logger.success(
                Fore.GREEN + "  # Bybit WebSocket client initialized." + Style.RESET_ALL
            )
        except Exception as e:
            self.logger.error(
                Fore.RED
                + f"  # Failed to initialize WebSocket client: {e}"
                + Style.RESET_ALL
            )
            raise

    async def verify_connection(self):
        """Verifies the API connection by fetching server time."""
        self.logger.info(
            Fore.CYAN
            + "  # Verifying connection by fetching server time..."
            + Style.RESET_ALL
        )
        try:
            # Use async HTTP client if available, otherwise sync
            if hasattr(self.http_client, "get_server_time_async"):
                response = await self.http_client.get_server_time_async()
            else:
                response = self.http_client.get_server_time()

            if response and response.get("retCode") == 0:
                time_ms = response["result"]["timeNano"] // 1_000_000
                self.logger.success(
                    Fore.GREEN
                    + f"  # Connection verified. Server Time (ms): {time_ms}"
                    + Style.RESET_ALL
                )
            else:
                self.logger.error(
                    Fore.RED
                    + f"  # Connection verification failed. Response: {response}"
                    + Style.RESET_ALL
                )
                raise ConnectionError(f"Failed to verify connection: {response}")
        except Exception as e:
            self.logger.error(
                Fore.RED
                + f"  # Error during connection verification: {e}"
                + Style.RESET_ALL
            )
            raise

    async def start_websocket(self, topics: list[str], market_type: str = "linear"):
        """Subscribes to specified WebSocket topics."""
        if not self.ws_client:
            self.logger.error(
                Fore.RED
                + "  # WebSocket client not initialized. Cannot subscribe."
                + Style.RESET_ALL
            )
            return

        if not self.websocket_connected:
            self.logger.info(
                Fore.CYAN + "  # Starting WebSocket connection..." + Style.RESET_ALL
            )
            try:
                # pybit's connect() is synchronous, so we run it in an executor
                await asyncio.get_event_loop().run_in_executor(
                    None, self.ws_client.connect
                )
                # Give it a moment to establish connection
                await asyncio.sleep(1)
            except Exception as e:
                self.logger.error(
                    Fore.RED + f"  # Failed to connect WebSocket: {e}" + Style.RESET_ALL
                )
                # Implement reconnection logic here if needed
                return

        self.logger.info(
            Fore.CYAN
            + f"  # Subscribing to topics: {topics} (Market Type: {market_type})..."
            + Style.RESET_ALL
        )
        try:
            # pybit's subscribe() is synchronous
            await asyncio.get_event_loop().run_in_executor(
                None, self.ws_client.subscribe, topics, market_type
            )
            for topic in topics:
                self.subscribed_topics.add(f"{topic}:{market_type}")
            self.logger.success(
                Fore.GREEN + "  # Subscription request sent." + Style.RESET_ALL
            )
        except Exception as e:
            self.logger.error(
                Fore.RED + f"  # Failed to subscribe to topics: {e}" + Style.RESET_ALL
            )

    def handle_websocket_message(self, message: dict[str, Any]):
        """Callback function to handle incoming WebSocket messages."""
        # self.logger.debug(f"Raw WS Message: {message}") # Uncomment for debugging raw messages

        if message.get("topic") in ["connection", "heartbeat"]:
            # Ignore connection and heartbeat messages for data processing
            return

        topic = message.get("topic")
        data = message.get("data")

        if not topic or not data:
            self.logger.warning(
                Fore.YELLOW
                + f"  # Received message with missing topic or data: {message}"
                + Style.RESET_ALL
            )
            return

        # --- Route messages based on topic ---
        try:
            if topic.startswith("kline."):
                # pybit might return a list of klines, process accordingly
                if isinstance(data, list):
                    for kline_data in data:
                        symbol_interval = topic.split(".")[1:]  # e.g., ['5', 'BTCUSDT']
                        symbol = symbol_interval[1]
                        interval = symbol_interval[0]
                        self.websocket_data["kline"][f"{symbol}:{interval}"] = (
                            kline_data
                        )
                        self.logger.debug(f"Updated kline for {symbol}:{interval}")
                else:  # Handle single kline data if format differs
                    symbol_interval = topic.split(".")[1:]
                    symbol = symbol_interval[1]
                    interval = symbol_interval[0]
                    self.websocket_data["kline"][f"{symbol}:{interval}"] = data
                    self.logger.debug(f"Updated kline for {symbol}:{interval}")

            elif topic.startswith("position."):
                # pybit might return a list of positions, process accordingly
                if isinstance(data, list):
                    for pos_data in data:
                        symbol = pos_data.get("symbol")
                        if symbol:
                            self.websocket_data["position"][symbol] = pos_data
                            self.logger.debug(f"Updated position for {symbol}")
                else:  # Handle single position data
                    symbol = data.get("symbol")
                    if symbol:
                        self.websocket_data["position"][symbol] = data
                        self.logger.debug(f"Updated position for {symbol}")

            elif topic.startswith("order."):
                # Handle order updates
                order_id = data.get("orderId")
                if order_id:
                    self.websocket_data["order"][order_id] = data
                    self.logger.debug(f"Updated order {order_id}")

            # Add handlers for other topics like 'trade', 'tickers', 'orderbook'
            # elif topic.startswith("publicTrade."): ...
            # elif topic.startswith("tickers."): ...
            # elif topic.startswith("orderbook."): ...

            else:
                self.logger.warning(
                    Fore.YELLOW
                    + f"  # Unhandled WebSocket topic: {topic}"
                    + Style.RESET_ALL
                )

        except Exception as e:
            self.logger.error(
                Fore.RED
                + f"  # Error processing WebSocket message for topic {topic}: {e}"
                + Style.RESET_ALL
            )

    def get_latest_kline(self, symbol: str, interval: str) -> dict[str, Any] | None:
        """Retrieves the latest kline data for a given symbol and interval."""
        return self.websocket_data.get("kline", {}).get(f"{symbol}:{interval}")

    def get_latest_position(self, symbol: str) -> dict[str, Any] | None:
        """Retrieves the latest position data for a given symbol."""
        return self.websocket_data.get("position", {}).get(symbol)

    def get_latest_order_update(self, order_id: str) -> dict[str, Any] | None:
        """Retrieves the latest order update for a given order ID."""
        return self.websocket_data.get("order", {}).get(order_id)

    # --- HTTP Request Methods (Wrappers for pybit.HTTP) ---
    async def _make_http_request(
        self, method_name: str, *args, **kwargs
    ) -> dict[str, Any] | None:
        """Internal helper to make HTTP requests with error handling."""
        if not self.http_client:
            self.logger.error(
                Fore.RED + "  # HTTP client not initialized." + Style.RESET_ALL
            )
            return None

        try:
            # Check if the method is async or sync
            method = getattr(self.http_client, method_name)
            if asyncio.iscoroutinefunction(method):
                response = await method(*args, **kwargs)
            else:
                # Run sync methods in an executor to avoid blocking the event loop
                response = await asyncio.get_event_loop().run_in_executor(
                    None, method, *args, **kwargs
                )

            # Basic check for successful response structure from pybit
            if response and response.get("retCode") == 0:
                return response
            else:
                self.logger.error(
                    Fore.RED
                    + f"  # HTTP Request '{method_name}' failed. Response: {response}"
                    + Style.RESET_ALL
                )
                return response  # Return response even on failure for inspection
        except Exception as e:
            self.logger.error(
                Fore.RED
                + f"  # Exception during HTTP request '{method_name}': {e}"
                + Style.RESET_ALL
            )
            return None

    async def get_server_time(self) -> dict[str, Any] | None:
        """Fetches the Bybit server time."""
        return await self._make_http_request("get_server_time")

    async def get_account_info(self) -> dict[str, Any] | None:
        """Fetches account information."""
        return await self._make_http_request("get_account_info")

    async def get_wallet_balance(
        self, account_type: str = "UNIFIED", coin: str | None = None
    ) -> dict[str, Any] | None:
        """Fetches wallet balance."""
        return await self._make_http_request(
            "get_wallet_balance", accountType=account_type, coin=coin
        )

    async def create_order(self, **kwargs) -> dict[str, Any] | None:
        """Creates an order."""
        # pybit's create_order is sync, run in executor
        return await self._make_http_request("create_order", **kwargs)

    async def amend_order(self, **kwargs) -> dict[str, Any] | None:
        """Amends an existing order."""
        # pybit's amend_order is sync, run in executor
        return await self._make_http_request("amend_order", **kwargs)

    async def cancel_order(self, **kwargs) -> dict[str, Any] | None:
        """Cancels an order."""
        # pybit's cancel_order is sync, run in executor
        return await self._make_http_request("cancel_order", **kwargs)

    async def get_open_orders(self, **kwargs) -> dict[str, Any] | None:
        """Gets open orders."""
        # pybit's get_open_orders is sync, run in executor
        return await self._make_http_request("get_open_orders", **kwargs)

    async def get_positions(self, **kwargs) -> dict[str, Any] | None:
        """Gets positions."""
        # pybit's get_positions is sync, run in executor
        return await self._make_http_request("get_positions", **kwargs)

    async def set_leverage(self, **kwargs) -> dict[str, Any] | None:
        """Sets leverage for a symbol."""
        # pybit's set_leverage is sync, run in executor
        return await self._make_http_request("set_leverage", **kwargs)

    # --- WebSocket Event Handlers ---
    def on_websocket_open(self):
        """Callback when WebSocket connection is established."""
        self.websocket_connected = True
        self.logger.success(
            Fore.GREEN + "  # WebSocket connection established." + Style.RESET_ALL
        )
        # Re-subscribe to topics if connection was lost and re-established
        if self.subscribed_topics:
            self.logger.info(
                Fore.CYAN
                + "  # Re-subscribing to topics after connection..."
                + Style.RESET_ALL
            )
            # Note: pybit's subscribe is sync, needs executor
            asyncio.get_event_loop().run_in_executor(
                None, self.ws_client.subscribe, list(self.subscribed_topics), "linear"
            )  # Assuming linear for now

    def on_websocket_close(self):
        """Callback when WebSocket connection is closed."""
        self.websocket_connected = False
        self.logger.warning(
            Fore.YELLOW + "  # WebSocket connection closed." + Style.RESET_ALL
        )
        # Implement reconnection logic here
        asyncio.create_task(self.reconnect_websocket())

    def on_websocket_error(self, error):
        """Callback for WebSocket errors."""
        self.logger.error(Fore.RED + f"  # WebSocket error: {error}" + Style.RESET_ALL)
        self.websocket_connected = False
        # Reconnection logic will be triggered by on_websocket_close or can be initiated here

    async def reconnect_websocket(self):
        """Attempts to reconnect the WebSocket connection after a delay."""
        if not self.websocket_connected:
            self.logger.info(
                Fore.CYAN
                + f"  # Attempting to reconnect WebSocket in {self.websocket_reconnect_delay} seconds..."
                + Style.RESET_ALL
            )
            await asyncio.sleep(self.websocket_reconnect_delay)
            try:
                # Re-initialize or just connect if client is still valid
                if self.ws_client:
                    self.ws_client.connect()  # This is sync, needs executor if not already handled
                    # Give it a moment to establish connection
                    await asyncio.sleep(1)
                    if self.subscribed_topics:
                        self.logger.info(
                            Fore.CYAN
                            + "  # Re-subscribing to topics after reconnection..."
                            + Style.RESET_ALL
                        )
                        await asyncio.get_event_loop().run_in_executor(
                            None,
                            self.ws_client.subscribe,
                            list(self.subscribed_topics),
                            "linear",
                        )
                else:
                    self.logger.error(
                        Fore.RED
                        + "  # WebSocket client is no longer available. Cannot reconnect."
                        + Style.RESET_ALL
                    )
            except Exception as e:
                self.logger.error(
                    Fore.RED
                    + f"  # Failed to reconnect WebSocket: {e}"
                    + Style.RESET_ALL
                )
                # Schedule another reconnect attempt
                asyncio.create_task(self.reconnect_websocket())

    async def process_websocket_messages(self):
        """This method is a placeholder. In a real async application,
        the WebsocketClient would typically run in its own task and
        call the on_message callback directly.
        This method is here to illustrate where message processing might be triggered
        if the WebsocketClient didn't handle callbacks directly.
        For pybit, the callbacks are handled internally by the client's thread.
        """
        # In pybit, messages are handled by the `on_message` callback.
        # This method might be used for other async tasks or checks.
        pass

    def close(self):
        """Closes the WebSocket connection."""
        if self.ws_client and self.websocket_connected:
            self.logger.info(
                Fore.CYAN + "  # Closing WebSocket connection..." + Style.RESET_ALL
            )
            try:
                self.ws_client.close()
                self.websocket_connected = False
                self.logger.success(
                    Fore.GREEN + "  # WebSocket connection closed." + Style.RESET_ALL
                )
            except Exception as e:
                self.logger.error(
                    Fore.RED + f"  # Error closing WebSocket: {e}" + Style.RESET_ALL
                )

    def __del__(self):
        """Ensures resources are cleaned up when the client is garbage collected."""
        self.close()


if __name__ == "__main__":
    # --- Pyrmethus Persona: Testing the Bybit Client ---
    print(
        Fore.MAGENTA
        + "# Pyrmethus: Conjuring the Bybit API Client for testing... #"
        + Style.RESET_ALL
    )

    async def test_client():
        try:
            client = BybitClient()
            await client.initialize()

            # Example: Get account info
            account_info = await client.get_account_info()
            if account_info:
                logger.info(f"Account Info: {json.dumps(account_info, indent=2)}")

            # Example: Get wallet balance for BTC
            wallet_balance = await client.get_wallet_balance(coin="BTC")
            if wallet_balance:
                logger.info(
                    f"BTC Wallet Balance: {json.dumps(wallet_balance, indent=2)}"
                )

            # Example: Subscribe to kline data
            await client.start_websocket(
                topics=["kline.5.BTCUSDT", "position.BTCUSDT"], market_type="linear"
            )

            # Keep the script running for a bit to receive WebSocket messages
            logger.info(
                "Keeping client running for 10 seconds to receive WS messages..."
            )
            await asyncio.sleep(10)

        except ValueError as ve:
            logger.error(f"Initialization error: {ve}")
        except Exception as e:
            logger.error(f"An error occurred during client testing: {e}")
        finally:
            if "client" in locals() and client:
                client.close()
            logger.info("Test finished.")

    asyncio.run(test_client())
