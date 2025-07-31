import asyncio
import hashlib
import hmac
import json
import time
import urllib.parse
import logging
import os
from typing import Dict, Any, Optional, List, Union
import httpx
import websockets
import websockets.protocol
from dataclasses import dataclass

# --- Color Codex ---
class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

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

# --- Configuration & Constants ---
BYBIT_REST_MAINNET = "https://api.bybit.com"
BYBIT_REST_TESTNET = "https://api-testnet.bybit.com"
BYBIT_WS_PRIVATE_MAINNET = "wss://stream.bybit.com/v5/private"
BYBIT_WS_PRIVATE_TESTNET = "wss://stream-testnet.bybit.com/v5/private"

# Public WebSocket URLs
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
    is_active: bool = True  # To control the main listener loop

class BybitContractAPI:
    """
    A comprehensive asynchronous Python client for Bybit V5 Contract Account API.
    """
    def __init__(self, testnet: bool = False):
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")

        if not api_key or not api_secret:
            raise ValueError(f"{Color.RED}API Key and Secret must be set via BYBIT_API_KEY and BYBIT_API_SECRET environment variables.{Color.RESET}")

        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip().encode('utf-8')
        self.base_rest_url = BYBIT_REST_TESTNET if testnet else BYBIT_REST_MAINNET
        self.base_ws_private_url = BYBIT_WS_PRIVATE_TESTNET if testnet else BYBIT_WS_PRIVATE_MAINNET
        self.base_ws_public_linear_url = BYBIT_WS_PUBLIC_LINEAR_TESTNET if testnet else BYBIT_WS_PUBLIC_LINEAR_MAINNET
        self.client = httpx.AsyncClient(base_url=self.base_rest_url, timeout=30.0)
        
        self.private_websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.public_websocket: Optional[websockets.WebSocketClientProtocol] = None

        self.private_connection_state = ConnectionState()
        self.public_connection_state = ConnectionState()

        self._ws_authenticated_event = asyncio.Event()
        self._private_subscriptions: set = set()
        self._public_subscriptions: set = set()


        logger.info(f"{Color.GREEN}BybitContractAPI initialized. Testnet mode: {testnet}{Color.RESET}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_connections()

    async def close_connections(self):
        """Gracefully close all connections."""
        self.private_connection_state.is_active = False
        self.private_connection_state.is_connected = False
        self.private_connection_state.is_authenticated = False
        self._ws_authenticated_event.clear()

        self.public_connection_state.is_active = False
        self.public_connection_state.is_connected = False

        if self.private_websocket:
            await self.private_websocket.close()
            logger.info(f"{Color.YELLOW}Private WebSocket connection closed.{Color.RESET}")
        
        if self.public_websocket:
            await self.public_websocket.close()
            logger.info(f"{Color.YELLOW}Public WebSocket connection closed.{Color.RESET}")
        
        await self.client.aclose()
        logger.info(f"{Color.YELLOW}HTTP client closed.{Color.RESET}")

    def _generate_rest_signature(self, params: Dict[str, Any], timestamp: str, recv_window: str, method: str, body: str = "") -> str:
        if method == "GET":
            query_string = urllib.parse.urlencode(sorted(params.items()))
            param_str = f"{timestamp}{self.api_key}{recv_window}{query_string}"
        else:  # POST
            param_str = f"{timestamp}{self.api_key}{recv_window}{body}"
        logger.info(f"{Color.MAGENTA}Signing REST request with string: {param_str}{Color.RESET}")
        return hmac.new(self.api_secret, param_str.encode('utf-8'), hashlib.sha256).hexdigest()

    def _generate_ws_signature(self, expires: int) -> str:
        sign_string = f"GET/realtime{expires}"
        return hmac.new(self.api_secret, sign_string.encode('utf-8'), hashlib.sha256).hexdigest()

    async def _get_server_time_ms(self) -> int:
        try:
            response = await self.client.get("/v5/market/time", timeout=5.0)
            response.raise_for_status()
            json_response = response.json()
            if json_response.get("retCode") == 0:
                return int(int(json_response["result"]["timeNano"]) / 1_000_000)
        except Exception as e:
            logger.warning(f"{Color.YELLOW}Error fetching server time: {e}. Using local time.{Color.RESET}")
        return int(time.time() * 1000)

    MAX_RETRIES = 3
    INITIAL_BACKOFF = 1  # seconds

    async def _make_request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, signed: bool = True) -> Dict[str, Any]:
        for attempt in range(self.MAX_RETRIES):
            try:
                current_timestamp = str(await self._get_server_time_ms())
                headers = {
                    "X-BAPI-API-KEY": self.api_key,
                    "X-BAPI-TIMESTAMP": current_timestamp,
                    "X-BAPI-RECV-WINDOW": DEFAULT_RECV_WINDOW,
                }
                request_params = params.copy() if params else {}
                
                if signed:
                    body_str = json.dumps(request_params) if method == "POST" else ""
                    signature = self._generate_rest_signature(request_params, current_timestamp, DEFAULT_RECV_WINDOW, method, body=body_str)
                    headers["X-BAPI-SIGN"] = signature

                if method == "POST":
                    headers["Content-Type"] = "application/json"
                    response = await self.client.post(endpoint, content=json.dumps(request_params), headers=headers)
                else: # GET
                    response = await self.client.get(endpoint, params=request_params, headers=headers)

                response.raise_for_status()
                json_response = response.json()
                if json_response.get("retCode") != 0:
                    raise BybitAPIError(json_response.get("retCode"), json_response.get("retMsg", "Unknown error"), json_response)
                return json_response
            except httpx.RequestError as e:
                logger.warning(f"{Color.YELLOW}Attempt {attempt + 1}/{self.MAX_RETRIES}: Request error for {endpoint}: {e}{Color.RESET}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.INITIAL_BACKOFF * (2 ** attempt))
                else:
                    raise
            except httpx.HTTPStatusError as e:
                logger.warning(f"{Color.YELLOW}Attempt {attempt + 1}/{self.MAX_RETRIES}: HTTP status error for {endpoint}: {e.response.status_code} - {e.response.text}{Color.RESET}")
                if e.response.status_code >= 500 and attempt < self.MAX_RETRIES - 1: # Retry on 5xx errors
                    await asyncio.sleep(self.INITIAL_BACKOFF * (2 ** attempt))
                else:
                    raise
            except BybitAPIError as e:
                # Do not retry on Bybit specific API errors (retCode != 0)
                raise
            except Exception as e:
                logger.error(f"{Color.RED}An unexpected error occurred during REST request to {endpoint}: {e}{Color.RESET}")
                raise

    async def get_kline(self, **kwargs) -> Dict[str, Any]:
        """Fetches kline data via REST API."""
        return await self._make_request("GET", "/v5/market/kline", kwargs, signed=False)

    async def get_kline_rest_fallback(self, **kwargs) -> Dict[str, Any]:
        """Fetches kline data via REST API as a fallback mechanism."""
        logger.warning(f"{Color.YELLOW}Falling back to REST API for kline data.{Color.RESET}")
        return await self.get_kline(**kwargs)

    async def get_instruments_info(self, **kwargs) -> Dict[str, Any]:
        return await self._make_request("GET", "/v5/market/instruments-info", kwargs, signed=False)

    async def get_positions(self, **kwargs) -> Dict[str, Any]:
        return await self._make_request("GET", "/v5/position/list", kwargs)

    async def get_orderbook(self, **kwargs) -> Dict[str, Any]:
        """Fetches order book data."""
        return await self._make_request("GET", "/v5/market/orderbook", kwargs, signed=False)

    async def create_order(self, **kwargs) -> Dict[str, Any]:
        return await self._make_request("POST", "/v5/order/create", kwargs)

    async def set_trading_stop(self, **kwargs) -> Dict[str, Any]:
        return await self._make_request("POST", "/v5/position/set-trading-stop", kwargs)

    async def _connect_private_ws(self) -> None:
        if self.private_connection_state.is_connected and self.private_websocket:
            return

        self._ws_authenticated_event.clear()
        self.private_connection_state.is_connected = False
        self.private_connection_state.is_authenticated = False

        try:
            self.private_websocket = await websockets.connect(
                self.base_ws_private_url,
                ping_interval=20,
                ping_timeout=10
            )
            self.private_connection_state.is_connected = True
            logger.info(f"{Color.GREEN}Connected to Bybit private WebSocket.{Color.RESET}")

            expires = int(time.time() * 1000) + 30000  # 30 seconds expiration
            signature = self._generate_ws_signature(expires)
            auth_message = {"op": "auth", "args": [self.api_key, expires, signature]}
            await self._send_private_ws_message(auth_message)
            logger.info(f"{Color.GREEN}Private WebSocket authentication message sent.{Color.RESET}")

        except websockets.exceptions.WebSocketException as e:
            self.private_connection_state.is_connected = False
            logger.error(f"{Color.RED}Private WebSocket connection error: {e}{Color.RESET}")
            raise WebSocketConnectionError(f"Private WebSocket connection error: {e}")

    async def _connect_public_ws(self) -> None:
        if self.public_connection_state.is_connected and self.public_websocket:
            return

        self.public_connection_state.is_connected = False

        try:
            self.public_websocket = await websockets.connect(
                self.base_ws_public_linear_url,
                ping_interval=20,
                ping_timeout=10
            )
            self.public_connection_state.is_connected = True
            logger.info(f"{Color.GREEN}Connected to Bybit public WebSocket (Linear).{Color.RESET}")

        except websockets.exceptions.WebSocketException as e:
            self.public_connection_state.is_connected = False
            logger.error(f"{Color.RED}Public WebSocket connection error: {e}{Color.RESET}")
            raise WebSocketConnectionError(f"Public WebSocket connection error: {e}")

    async def _send_private_ws_message(self, message: Dict[str, Any]) -> None:
        if not self.private_websocket or not self.private_connection_state.is_connected:
            raise WebSocketConnectionError("Private WebSocket not connected.")
        await self.private_websocket.send(json.dumps(message))
        logger.debug(f"Private WS Sent: {message}")

    async def _send_public_ws_message(self, message: Dict[str, Any]) -> None:
        if not self.public_websocket or not self.public_connection_state.is_connected:
            raise WebSocketConnectionError("Public WebSocket not connected.")
        await self.public_websocket.send(json.dumps(message))
        logger.debug(f"Public WS Sent: {message}")

    async def subscribe_ws_private_topic(self, topic: str) -> None:
        self._private_subscriptions.add(topic)
        if self.private_connection_state.is_authenticated:
            await self._send_private_ws_message({"op": "subscribe", "args": [topic]})
            logger.info(f"{Color.MAGENTA}Subscribing to private WebSocket topic: {topic}{Color.RESET}")
        else:
            logger.info(f"{Color.YELLOW}Queued private subscription for '{topic}'. Will subscribe after auth.{Color.RESET}")

    async def subscribe_ws_public_topic(self, topic: str) -> None:
        self._public_subscriptions.add(topic)
        if self.public_connection_state.is_connected:
            await self._send_public_ws_message({"op": "subscribe", "args": [topic]})
            logger.info(f"{Color.MAGENTA}Subscribing to public WebSocket topic: {topic}{Color.RESET}")
        else:
            logger.info(f"{Color.YELLOW}Queued public subscription for '{topic}'. Will subscribe after connection.{Color.RESET}")

    async def _resubscribe_private_topics(self):
        if not self._private_subscriptions:
            return
        logger.info(f"{Color.GREEN}Resubscribing to private topics: {list(self._private_subscriptions)}{Color.RESET}")
        await self._send_private_ws_message({"op": "subscribe", "args": list(self._private_subscriptions)})

    async def _resubscribe_public_topics(self):
        if not self._public_subscriptions:
            return
        logger.info(f"{Color.GREEN}Resubscribing to public topics: {list(self._public_subscriptions)}{Color.RESET}")
        await self._send_public_ws_message({"op": "subscribe", "args": list(self._public_subscriptions)})

    async def start_private_websocket_listener(self, callback: callable, reconnect_delay: int = 5) -> asyncio.Task:
        async def _listener_task():
            while self.private_connection_state.is_active:
                try:
                    await self._connect_private_ws()
                    while self.private_connection_state.is_connected:
                        try:
                            message = await asyncio.wait_for(self.private_websocket.recv(), timeout=30)
                            parsed_message = json.loads(message)
                            logger.debug(f"Private WS Received: {parsed_message}")

                            if parsed_message.get("op") == "auth":
                                if parsed_message.get("success"):
                                    self.private_connection_state.is_authenticated = True
                                    self._ws_authenticated_event.set()
                                    logger.info(f"{Color.GREEN}Private WebSocket authenticated successfully.{Color.RESET}")
                                    await self._resubscribe_private_topics()
                                else:
                                    logger.error(f"{Color.RED}Private WebSocket auth failed: {parsed_message.get('retMsg', 'Unknown error')}. Full response: {json.dumps(parsed_message)}{Color.RESET}")
                                    break
                            elif parsed_message.get("op") != "pong":
                                await callback(parsed_message)

                        except asyncio.TimeoutError:
                            logger.warning(f"{Color.YELLOW}Private WebSocket recv timed out. Reconnecting...{Color.RESET}")
                            break
                        except websockets.exceptions.ConnectionClosed as e:
                            logger.warning(f"{Color.YELLOW}Private WebSocket closed: {e}. Reconnecting...{Color.RESET}")
                            break
                except Exception as e:
                    logger.error(f"{Color.RED}Error in private WebSocket listener: {e}. Retrying...{Color.RESET}")
                
                self.private_connection_state.is_connected = False
                self.private_connection_state.is_authenticated = False
                self._ws_authenticated_event.clear()
                if self.private_connection_state.is_active:
                    await asyncio.sleep(reconnect_delay)
            logger.info(f"{Color.YELLOW}Private WebSocket listener stopped.{Color.RESET}")
        return asyncio.create_task(_listener_task())

    async def start_public_websocket_listener(self, callback: callable, reconnect_delay: int = 5) -> asyncio.Task:
        async def _listener_task():
            while self.public_connection_state.is_active:
                try:
                    await self._connect_public_ws()
                    while self.public_connection_state.is_connected:
                        try:
                            message = await asyncio.wait_for(self.public_websocket.recv(), timeout=60)
                            parsed_message = json.loads(message)
                            logger.debug(f"Public WS Received: {parsed_message}")

                            # Public WS does not have 'auth' messages, just data or pongs
                            if parsed_message.get("op") != "pong":
                                await callback(parsed_message)

                        except asyncio.TimeoutError:
                            logger.warning(f"{Color.YELLOW}Public WebSocket recv timed out. Reconnecting...{Color.RESET}")
                            break
                        except websockets.exceptions.ConnectionClosed as e:
                            logger.warning(f"{Color.YELLOW}Public WebSocket closed: {e}. Reconnecting...{Color.RESET}")
                            break
                except Exception as e:
                    logger.error(f"{Color.RED}Error in public WebSocket listener: {e}. Retrying...{Color.RESET}")
                
                self.public_connection_state.is_connected = False
                if self.public_connection_state.is_active:
                    await asyncio.sleep(reconnect_delay)
            logger.info(f"{Color.YELLOW}Public WebSocket listener stopped.{Color.RESET}")
        return asyncio.create_task(_listener_task())
