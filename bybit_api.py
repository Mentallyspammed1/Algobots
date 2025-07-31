import asyncio
import hashlib
import hmac
import json
import time
import urllib.parse
import logging
import os
from typing import Dict, Any, Optional, List, Union, Callable
import httpx
import websockets
import websockets.protocol
from dataclasses import dataclass, field

# --- Color Codex ---
class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

# --- Pyrmethus's Color Codex ---
try:
    from color_codex import (
        COLOR_RESET, COLOR_BOLD, COLOR_DIM,
        COLOR_RED, COLOR_GREEN, COLOR_YELLOW, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN,
        PYRMETHUS_GREEN, PYRMETHUS_BLUE, PYRMETHUS_PURPLE, PYRMETHUS_ORANGE, PYRMETHUS_GREY, PYRMETHUS_YELLOW
    )
except ImportError:
    COLOR_RESET = "\033[0m"
    COLOR_BOLD = "\033[1m"
    COLOR_DIM = "\033[2m"
    COLOR_RED = "\033[31m"
    COLOR_GREEN = "\033[32m"
    COLOR_YELLOW = "\033[33m"
    COLOR_BLUE = "\033[34m"
    COLOR_MAGENTA = "\033[35m"
    COLOR_CYAN = "\033[36m"
    PYRMETHUS_GREEN = COLOR_GREEN
    PYRMETHUS_BLUE = COLOR_BLUE
    PYRMETHUS_PURPLE = COLOR_MAGENTA
    PYRMETHUS_ORANGE = COLOR_YELLOW
    PYRMETHUS_GREY = COLOR_DIM
    PYRMETHUS_YELLOW = COLOR_YELLOW

# --- Custom Exceptions ---
class BybitAPIError(Exception):
    """Custom exception for Bybit API errors."""
    def __init__(self, ret_code: int, ret_msg: str, original_response: Dict):
        self.ret_code = ret_code
        self.ret_msg = ret_msg
        self.original_response = original_response
        super().__init__(f"Bybit API Error {ret_code}: {ret_msg}")

class WebSocketConnectionError(Exception):
    """Custom exception for WebSocket connection issues."""
    pass

class RESTRequestError(Exception):
    """Exception for REST request failures."""
    pass

# --- Configuration & Constants ---
BYBIT_REST_MAINNET = "https://api.bybit.com"
BYBIT_REST_TESTNET = "https://api-testnet.bybit.com"
BYBIT_WS_PRIVATE_MAINNET = "wss://stream.bybit.com/v5/private"
BYBIT_WS_PRIVATE_TESTNET = "wss://stream-testnet.bybit.com/v5/private"

BYBIT_WS_PUBLIC_LINEAR_MAINNET = "wss://stream.bybit.com/v5/public/linear"
BYBIT_WS_PUBLIC_LINEAR_TESTNET = "wss://stream-testnet.bybit.com/v5/public/linear"

DEFAULT_RECV_WINDOW = "5000"

logging.basicConfig(level=logging.INFO, format=f'{Color.CYAN}[BybitAPI]{Color.RESET} %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ConnectionState:
    """Track WebSocket connection state."""
    is_connected: bool = False
    is_authenticated: bool = False
    is_active: bool = True
    last_ping_time: float = 0.0
    last_pong_time: float = 0.0
    websocket_instance: Optional[websockets.WebSocketClientProtocol] = None
    listener_task: Optional[asyncio.Task] = None
    _ws_authenticated_event: asyncio.Event = field(default_factory=asyncio.Event)

class BybitContractAPI:
    """
    A comprehensive asynchronous Python client for Bybit V5 Contract Account API.
    Enhanced with robust reconnection, error handling, rate limiting, and structured message processing.
    """
    def __init__(self, testnet: bool = False, log_level: int = logging.INFO):
        logger.setLevel(log_level)
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")

        if not api_key or not api_secret:
            raise ValueError(f"{Color.RED}API Key and Secret must be set in BYBIT_API_KEY and BYBIT_API_SECRET{Color.RESET}")

        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip().encode('utf-8')
        self.base_rest_url = BYBIT_REST_TESTNET if testnet else BYBIT_REST_MAINNET
        self.base_ws_private_url = BYBIT_WS_PRIVATE_TESTNET if testnet else BYBIT_WS_PRIVATE_MAINNET
        self.base_ws_public_linear_url = BYBIT_WS_PUBLIC_LINEAR_TESTNET if testnet else BYBIT_WS_PUBLIC_LINEAR_MAINNET
        
        self.client = httpx.AsyncClient(
            base_url=self.base_rest_url,
            timeout=httpx.Timeout(5.0, connect=5.0, read=30.0)
        )
        
        self.private_websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.public_websocket: Optional[websockets.WebSocketClientProtocol] = None

        self.private_connection_state = ConnectionState()
        self.public_connection_state = ConnectionState()

        self.ws_ping_interval = 20 # seconds
        self.ws_ping_timeout = 10 # seconds

        # REST API Rate Limiting
        self.rest_rate_limit_interval = 60 # seconds
        self.rest_rate_limit_calls = 120 # calls per interval
        self._last_rest_call_time = 0.0
        self._rest_call_count = 0

        # --- INITIALIZE SUBSCRIPTION SETS ---
        self._private_subscriptions: set = set()
        self._public_subscriptions: set = set()
        # --- END INITIALIZATION ---

        logger.info(f"{Color.GREEN}BybitContractAPI initialized. Testnet mode: {testnet}{Color.RESET}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_connections()

    async def close_connections(self):
        """Gracefully close all connections."""
        self.private_connection_state.is_active = False
        self.public_connection_state.is_active = False

        if self.private_websocket:
            try:
                await self.private_websocket.close()
                logger.info(f"{Color.YELLOW}Private WebSocket connection closed.{Color.RESET}")
            except Exception as e:
                logger.warning(f"{Color.YELLOW}Error closing private WebSocket: {e}{Color.RESET}")
        
        if self.public_websocket:
            try:
                await self.public_websocket.close()
                logger.info(f"{Color.YELLOW}Public WebSocket connection closed.{Color.RESET}")
            except Exception as e:
                logger.warning(f"{Color.YELLOW}Error closing public WebSocket: {e}{Color.RESET}")
        
        await self.client.aclose()
        logger.info(f"{Color.YELLOW}HTTP client closed.{Color.RESET}")

    def _generate_rest_signature(self, params: Dict[str, Any], timestamp: str, recv_window: str, method: str, body: str = "") -> str:
        """Generates the signature for REST API requests."""
        if method == "GET":
            query_string = urllib.parse.urlencode(sorted(params.items()))
            param_str = f"{timestamp}{self.api_key}{recv_window}{query_string}"
        else:  # POST
            param_str = f"{timestamp}{self.api_key}{recv_window}{body}"
        return hmac.new(self.api_secret, param_str.encode('utf-8'), hashlib.sha256).hexdigest()

    def _generate_ws_signature(self, expires: int, path: str = "/realtime") -> str:
        """Generates the signature for WebSocket authentication."""
        sign_string = f"GET{path}{expires}"
        return hmac.new(self.api_secret, sign_string.encode('utf-8'), hashlib.sha256).hexdigest()

    async def _get_server_time_ms(self) -> int:
        """Fetches the current server time in milliseconds."""
        try:
            response = await self.client.get("/v5/market/time", timeout=5.0)
            response.raise_for_status()
            json_response = response.json()
            if json_response.get("retCode") == 0:
                return int(int(json_response["result"]["timeNano"]) / 1_000_000)
        except Exception as e:
            logger.warning(f"{Color.YELLOW}Error fetching server time: {e}. Using local time.{Color.RESET}")
        return int(time.time() * 1000)

    # --- REST API Request Handling ---
    MAX_RETRIES = 3
    INITIAL_BACKOFF = 1  # seconds

    async def _rate_limit_wait(self):
        """Waits if necessary to comply with REST API rate limits."""
        current_time = time.time()
        elapsed = current_time - self._last_rest_call_time
        
        if elapsed < self.rest_rate_limit_interval and self._rest_call_count >= self.rest_rate_limit_calls:
            wait_time = self.rest_rate_limit_interval - elapsed
            logger.warning(f"{Color.YELLOW}Rate limit approaching. Waiting for {wait_time:.2f} seconds.{Color.RESET}")
            await asyncio.sleep(wait_time)
        
        if elapsed >= self.rest_rate_limit_interval:
            self._rest_call_count = 0
            self._last_rest_call_time = current_time
        
        self._rest_call_count += 1

    async def _make_request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, signed: bool = True, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Makes a generic REST API request with retry logic and signature generation."""
        await self._rate_limit_wait()

        for attempt in range(self.MAX_RETRIES):
            try:
                current_timestamp = str(await self._get_server_time_ms())
                headers = {
                    "X-BAPI-API-KEY": self.api_key,
                    "X-BAPI-TIMESTAMP": current_timestamp,
                    "X-BAPI-RECV-WINDOW": DEFAULT_RECV_WINDOW,
                }
                
                request_params = params.copy() if params else {}
                request_body = body.copy() if body else {}
                
                if signed:
                    # Sort keys for canonical representation
                    body_str = json.dumps(request_body, separators=(",", ":"), sort_keys=True) if method == "POST" else ""
                    signature = self._generate_rest_signature(request_params, current_timestamp, DEFAULT_RECV_WINDOW, method, body=body_str)
                    headers["X-BAPI-SIGN"] = signature

                logger.debug(f"{Color.CYAN}Making REST request: {method} {endpoint} with params={request_params}, body={request_body}{Color.RESET}")

                if method == "POST":
                    headers["Content-Type"] = "application/json"
                    response = await self.client.post(endpoint, json=request_body, headers=headers)
                else: # GET
                    response = await self.client.get(endpoint, params=request_params, headers=headers)

                response.raise_for_status()
                json_response = response.json()
                
                if json_response.get("retCode") != 0:
                    raise BybitAPIError(json_response.get("retCode"), json_response.get("retMsg", "Unknown error"), json_response)
                
                logger.info(f"{Color.GREEN}REST request successful: {endpoint}{Color.RESET}")
                return json_response
                
            except httpx.RequestError as e:
                logger.warning(f"{Color.YELLOW}Attempt {attempt + 1}/{self.MAX_RETRIES}: Request error for {endpoint}: {e}{Color.RESET}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.INITIAL_BACKOFF * (2 ** attempt))
                else:
                    raise RESTRequestError(f"REST request failed after {self.MAX_RETRIES} retries: {e}") from e
            except httpx.HTTPStatusError as e:
                logger.warning(f"{Color.YELLOW}Attempt {attempt + 1}/{self.MAX_RETRIES}: HTTP status error for {endpoint}: {e.response.status_code} - {e.response.text}{Color.RESET}")
                if e.response.status_code >= 500 and attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.INITIAL_BACKOFF * (2 ** attempt))
                else:
                    raise WebSocketConnectionError(f"HTTP error {e.response.status_code} for {endpoint}") from e
            except BybitAPIError as e:
                logger.error(f"{Color.RED}Bybit API Error for {endpoint}: {e.ret_msg} (Code: {e.ret_code}){Color.RESET}")
                raise
            except Exception as e:
                logger.error(f"{Color.RED}An unexpected error occurred during REST request to {endpoint}: {e}{Color.RESET}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.INITIAL_BACKOFF * (2 ** attempt))
                else:
                    raise WebSocketConnectionError(f"Unexpected error after {self.MAX_RETRIES} retries for {endpoint}: {e}") from e
        
        raise WebSocketConnectionError(f"Failed to complete REST request to {endpoint} after all retries.")

    # --- Public API Endpoints ---
    async def get_kline(self, **kwargs) -> Dict[str, Any]:
        """Fetches kline data via REST API."""
        return await self._make_request("GET", "/v5/market/kline", params=kwargs, signed=False)

    async def get_kline_rest_fallback(self, **kwargs) -> Dict[str, Any]:
        """Fetches kline data via REST API as a fallback mechanism."""
        logger.warning(f"{Color.YELLOW}Falling back to REST API for kline data.{Color.RESET}")
        return await self.get_kline(**kwargs)

    async def get_instruments_info(self, **kwargs) -> Dict[str, Any]:
        """Fetches instrument information."""
        return await self._make_request("GET", "/v5/market/instruments-info", params=kwargs, signed=False)

    async def get_positions(self, **kwargs) -> Dict[str, Any]:
        """Fetches current positions."""
        return await self._make_request("GET", "/v5/position/list", params=kwargs)

    async def get_orderbook(self, **kwargs) -> Dict[str, Any]:
        """Fetches order book data."""
        return await self._make_request("GET", "/v5/market/orderbook", params=kwargs, signed=False)

    async def create_order(self, **kwargs) -> Dict[str, Any]:
        """Creates a new order."""
        return await self._make_request("POST", "/v5/order/create", signed=True, body=kwargs)

    async def amend_order(self, **kwargs) -> Dict[str, Any]:
        """Amends an existing order."""
        return await self._make_request("POST", "/v5/order/amend", signed=True, body=kwargs)

    async def set_trading_stop(self, **kwargs) -> Dict[str, Any]:
        """Sets or updates stop loss and take profit orders."""
        return await self._make_request("POST", "/v5/position/set-trading-stop", signed=True, body=kwargs)

    async def get_order_status(self, **kwargs) -> Dict[str, Any]:
        """Gets the status of orders (history or real-time). Use precise params like orderId."""
        return await self._make_request("GET", "/v5/order/history", params=kwargs)

    async def get_open_order_id(self, **kwargs) -> Optional[str]:
        """
        Gets the order ID of the first open order matching the criteria.
        Uses the '/v5/order/realtime' endpoint and returns the first list item.
        """
        try:
            resp = await self._make_request("GET", "/v5/order/realtime", params=kwargs)
            lst = resp.get("result", {}).get("list", [])
            return lst[0].get("orderId") if lst else None

        except BybitAPIError as e:
            if e.ret_code == 10009:  # Order not found
                logger.info(f"{Color.YELLOW}No open orders matching {kwargs}.{Color.RESET}")
                return None
            raise

    async def get_wallet_balance(self, **kwargs) -> Dict[str, Any]:
        """Gets the wallet balance."""
        return await self._make_request("GET", "/v5/account/wallet-balance", params=kwargs)

    async def get_symbol_ticker(self, **kwargs) -> Dict[str, Any]:
        """Fetches the ticker price for a symbol."""
        try:
            return await self._make_request("GET", "/v5/market/tickers", params=kwargs, signed=False)

        except BybitAPIError as e:
            if e.ret_code == 10009:
                logger.error(
                    f"{Color.RED}Invalid symbol/category: "
                    f"{kwargs.get('symbol')}/{kwargs.get('category')}. "
                    f"{e.ret_msg}{Color.RESET}"
                )
                raise RESTRequestError(f"Invalid symbol/category: {kwargs}") from e
            raise

        except Exception as e:
            logger.error(f"{Color.RED}Unexpected error in get_symbol_ticker: {e}{Color.RESET}")
            raise

# --- WebSocket Handling ---
    async def _connect_websocket(
        self,
        url: str,
        connection_state: ConnectionState,
        subscriptions: set,
        resubscribe_func: Callable,
        callback: Callable,
        auth_required: bool = False,
        reconnect_delay: int = 5
    ) -> Optional[websockets.WebSocketClientProtocol]:
        """Common logic for connecting/authenticating & initial subscribe."""
        if connection_state.is_connected and connection_state.is_active:
            return connection_state.websocket_instance

        # reset state
        connection_state.is_connected = False
        connection_state.is_authenticated = False
        connection_state._ws_authenticated_event.clear()

        try:
            ws = await websockets.connect(
                url,
                ping_interval=self.ws_ping_interval,
                ping_timeout=self.ws_ping_timeout,
                open_timeout=15
            )
            connection_state.websocket_instance = ws
            connection_state.is_connected = True
            logger.info(f"{Color.GREEN}WS connected: {url}{Color.RESET}")

            if auth_required:
                expires = int(time.time() * 1000) + 30_000
                sig = self._generate_ws_signature(expires, path="/v5/private")
                auth_msg = {"op": "auth", "args": [self.api_key, expires, sig]}
                await self._send_ws_message(ws, auth_msg, is_private=True)

            await resubscribe_func()
            return ws

        except (websockets.exceptions.WebSocketException, ConnectionError, asyncio.TimeoutError) as e:
            logger.error(f"{Color.RED}WS conn error {url}: {e}{Color.RESET}")
            await asyncio.sleep(reconnect_delay)
            return None

    async def _send_ws_message(
        self,
        websocket: Optional[websockets.WebSocketClientProtocol],
        message: Dict[str, Any],
        is_private: bool = False
    ) -> None:
        """Safely send a JSON message over WebSocket."""
        state = self.private_connection_state if is_private else self.public_connection_state

        if not websocket or websocket.closed:
            state.is_connected = False
            logger.warning(f"{Color.YELLOW}WS not open, msg dropped: {message}{Color.RESET}")
            return

        try:
            await websocket.send(json.dumps(message))
            logger.debug(f"{'Priv' if is_private else 'Pub'} WS → {message}")
        except Exception as e:
            state.is_connected = False
            logger.error(f"{Color.RED}WS send failed: {e}{Color.RESET}")

    async def subscribe_ws_topic(
        self,
        websocket: Optional[websockets.WebSocketClientProtocol],
        subscriptions: set,
        topic: str,
        is_private: bool = False
    ) -> None:
        """Subscribes to a WebSocket topic if not already in the set."""
        state = self.private_connection_state if is_private else self.public_connection_state

        if topic in subscriptions:
            logger.debug(f"Already subscribed to {topic}")
            return

        subscriptions.add(topic)
        sub_msg = {"op": "subscribe", "args": [topic]}
        await self._send_ws_message(websocket, sub_msg, is_private)

    async def _resubscribe_topics(self, connection_state: ConnectionState, subscriptions: set, url: str, is_private: bool) -> None:
        """Resubscribes to all topics when connection is re-established."""
        if not connection_state.is_connected or not subscriptions:
            return
        
        logger.info(f"{Color.GREEN}Resubscribing to {'private' if is_private else 'public'} WebSocket topics...{Color.RESET}")
        message = {"op": "subscribe", "args": list(subscriptions)}
        await self._send_ws_message(connection_state.websocket_instance, message, is_private=is_private)

    async def _message_receiving_loop(self, websocket: websockets.WebSocketClientProtocol, connection_state: ConnectionState, auth_required: bool, callback: Callable):
        """
        Main message receiving loop for handling WebSocket connections.
        """
        while connection_state.is_connected and connection_state.is_active:
            if not websocket or not websocket.open:
                logger.warning(f"{Color.YELLOW}{'Private' if auth_required else 'Public'} WebSocket no longer open. Breaking to reconnect. {Color.RESET}")
                break

            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=self.ws_ping_interval + self.ws_ping_timeout)
                parsed_message = json.loads(message)
                logger.debug(f"{'Private' if auth_required else 'Public'} WS Received: {parsed_message}")

                if parsed_message.get("op") == "pong":
                    connection_state.last_pong_time = time.time()
                    logger.debug(f"{'Private' if auth_required else 'Public'} WS Pong received.")
                    continue
                
                if auth_required and parsed_message.get("op") == "auth":
                    if parsed_message.get("success"):
                        connection_state.is_authenticated = True
                        connection_state._ws_authenticated_event.set()
                        logger.info(f"{Color.GREEN}Private WebSocket authenticated successfully.{Color.RESET}")
                    else:
                        logger.error(f"{Color.RED}Private WebSocket auth failed: {parsed_message.get('retMsg', 'Unknown error')}. Response: {json.dumps(parsed_message)}{Color.RESET}")
                        break # Auth failed, break to reconnect

                await callback(parsed_message)

            except asyncio.TimeoutError:
                logger.warning(f"{Color.YELLOW}{'Private' if auth_required else 'Public'} WebSocket recv timed out. Checking connection health...{Color.RESET}")
                if connection_state.last_pong_time < connection_state.last_ping_time:
                    logger.error(f"{Color.RED}No pong received after ping. Connection likely dead. Reconnecting...{Color.RESET}")
                    break
                else:
                    connection_state.last_ping_time = time.time()
                    try:
                        await websocket.ping()
                    except Exception as ping_e:
                         logger.error(f"{Color.RED}Error sending ping: {ping_e}{Color.RESET}")
                         break
                    logger.debug(f"{'Private' if auth_required else 'Public'} WS Ping sent.")

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"{Color.YELLOW}{'Private' if auth_required else 'Public'} WebSocket closed: {e}. Reconnecting...{Color.RESET}")
                break
            except json.JSONDecodeError:
                logger.error(f"{Color.RED}Failed to decode JSON message: {message}{Color.RESET}")
            except Exception as e:
                logger.error(f"{Color.RED}Error processing message in {'private' if auth_required else 'public'} WebSocket listener: {e}{Color.RESET}")
                if isinstance(e, WebSocketConnectionError):
                    break

    async def start_websocket_listener(self, url: str, connection_state: ConnectionState, subscriptions: set, resubscribe_func: Callable, callback: Callable, auth_required: bool = False, reconnect_delay: int = 5) -> asyncio.Task:
        """Generic listener task for both private and public WebSockets."""
        async def _listener_task():
            while connection_state.is_active:
                websocket = None
                try:
                    websocket = await self._connect_websocket(url, connection_state, subscriptions, resubscribe_func, callback, auth_required, reconnect_delay)
                    if not websocket: # Connection failed, retry after delay
                        continue

                    # Hand off to the message receiving loop
                    await self._message_receiving_loop(websocket, connection_state, auth_required, callback)

                except WebSocketConnectionError as e:
                    pass # Error already logged in _connect_websocket
                except Exception as e:
                    logger.error(f"{Color.RED}Unhandled error in {'private' if auth_required else 'public'} WebSocket listener task: {e}{Color.RESET}")
                
                # --- Cleanup and Reconnection ---
                connection_state.is_connected = False
                connection_state.is_authenticated = False
                if auth_required: connection_state._ws_authenticated_event.clear()
                
                if websocket and not websocket.closed:
                    try: await websocket.close()
                    except Exception as close_e: logger.warning(f"Error during cleanup close: {close_e}")
                
                connection_state.websocket_instance = None # Clear the instance

                if connection_state.is_active:
                    logger.info(f"{Color.YELLOW}Waiting {reconnect_delay} seconds before retrying connection...{Color.RESET}")
                    await asyncio.sleep(reconnect_delay)
            
            logger.info(f"{Color.YELLOW}{'Private' if auth_required else 'Public'} WebSocket listener stopped.{Color.RESET}")
        
        task = asyncio.create_task(_listener_task())
        connection_state.listener_task = task
        return task

    def start_private_websocket_listener(self, callback: Callable, reconnect_delay: int = 5) -> asyncio.Task:
        """Starts the listener for private WebSocket events."""
        return self.start_websocket_listener(
            self.base_ws_private_url, self.private_connection_state, self._private_subscriptions,
            lambda: self._resubscribe_topics(self.private_connection_state, self._private_subscriptions, self.base_ws_private_url, is_private=True),
            callback, auth_required=True, reconnect_delay=reconnect_delay
        )

    def start_public_websocket_listener(self, callback: Callable, reconnect_delay: int = 5) -> asyncio.Task:
        """Starts the listener for public WebSocket events."""
        return self.start_websocket_listener(
            self.base_ws_public_linear_url, self.public_connection_state, self._public_subscriptions,
            lambda: self._resubscribe_topics(self.public_connection_state, self._public_subscriptions, self.base_ws_public_linear_url, is_private=False),
            callback, auth_required=False, reconnect_delay=reconnect_delay
        )

    async def subscribe_ws_private_topic(self, topic: str) -> None:
        """Subscribes to a private WebSocket topic."""
        if not self.private_connection_state.is_connected:
            logger.info(f"{Color.YELLOW}Queued private subscription for '{topic}'. Will subscribe after connection.{Color.RESET}")
            self._private_subscriptions.add(topic)
            return
        await self.subscribe_ws_topic(self.private_websocket, self._private_subscriptions, topic, is_private=True)

    async def subscribe_ws_public_topic(self, topic: str) -> None:
        """Subscribes to a public WebSocket topic."""
        if not self.public_connection_state.is_connected:
            logger.info(f"{Color.YELLOW}Queued public subscription for '{topic}'. Will subscribe after connection.{Color.RESET}")
            self._public_subscriptions.add(topic)
            return
        await self.subscribe_ws_topic(self.public_websocket, self._public_subscriptions, topic, is_private=False)

# --- Example Usage (requires API keys and other modules) ---
async def main_example():
    """Example demonstrating BybitContractAPI usage."""
    try:
        api = BybitContractAPI(testnet=True) # Use testnet=True for testing

        print(f"\n{Color.BOLD}--- REST API Examples ---{Color.RESET}")
        try:
            server_time = await api.get_server_time_ms()
            print(f"{Color.GREEN}Server Time: {server_time}{Color.RESET}")

            instruments = await api.get_instruments_info(category="linear", symbol="BTCUSD")
            if instruments and instruments.get('result', {}).get('list'):
                print(f"{Color.GREEN}Instrument Info (BTCUSD): {json.dumps(instruments['result']['list'][0], indent=2)}{Color.RESET}")

            ticker = await api.get_symbol_ticker(category="linear", symbol="BTCUSD")
            if ticker and ticker.get('result', {}).get('list'):
                 print(f"{Color.GREEN}BTCUSD Ticker: LastPrice={ticker['result']['list'][0]['lastPrice']}, HighPrice={ticker['result']['list'][0]['highPrice']}{Color.RESET}")

            positions = await api.get_positions(category="linear", symbol="BTCUSD")
            print(f"{Color.GREEN}Positions for BTCUSD: {json.dumps(positions, indent=2)}{Color.RESET}")

        except (BybitAPIError, WebSocketConnectionError, ValueError, httpx.HTTPStatusError, httpx.RequestError) as e:
            print(f"{Color.RED}REST API Error during example: {e}{Color.RESET}")
        except Exception as e:
            print(f"{Color.RED}An unexpected error occurred during REST examples: {e}{Color.RESET}")

        print(f"\n{Color.BOLD}--- WebSocket Examples ---{Color.RESET}")
        
        private_listener = api.start_private_websocket_listener(lambda msg: print(f"{Color.CYAN}Private WS Callback:{Color.RESET} {msg}"))
        public_listener = api.start_public_websocket_listener(lambda msg: print(f"{Color.CYAN}Public WS Callback:{Color.RESET} {msg}"))

        await asyncio.sleep(3) # Wait for connection/auth

        await api.subscribe_ws_private_topic("position")
        await api.subscribe_ws_public_topic("kline.1.BTCUSD") 

        print(f"{Color.YELLOW}Running WebSocket listeners for 30 seconds... Press Ctrl+C to stop.{Color.RESET}")
        await asyncio.sleep(30)

    except ValueError as e:
        print(f"{Color.RED}Initialization Error: {e}{Color.RESET}")
    except WebSocketConnectionError as e:
        print(f"{Color.RED}WebSocket Error: {e}{Color.RESET}")
    except Exception as e:
        print(f"{Color.RED}An unexpected error occurred in main_example: {e}{Color.RESET}")
    finally:
        print(f"{Color.YELLOW}Closing connections...{Color.RESET}")
        await api.close_connections()

# To run the example:
if __name__ == "__main__":
    # Ensure you have set BYBIT_API_KEY and BYBIT_API_SECRET environment variables
    # And have the necessary libraries installed (httpx, websockets, pandas, python-dotenv)
    # And have algobots_types.py and color_codex.py available if not using fallbacks.
    asyncio.run(main_example())