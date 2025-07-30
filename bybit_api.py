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
        self.client = httpx.AsyncClient(base_url=self.base_rest_url, timeout=30.0)
        
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connection_state = ConnectionState()
        self._ws_authenticated_event = asyncio.Event()
        self._subscriptions: set = set()

        logger.info(f"{Color.GREEN}BybitContractAPI initialized. Testnet mode: {testnet}{Color.RESET}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_connections()

    async def close_connections(self):
        """Gracefully close all connections."""
        self.connection_state.is_active = False
        self.connection_state.is_connected = False
        self.connection_state.is_authenticated = False
        self._ws_authenticated_event.clear()

        if self.websocket:
            await self.websocket.close()
            logger.info(f"{Color.YELLOW}WebSocket connection closed.{Color.RESET}")
        
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
        sign_string = f"GET/realtime{expires}{self.api_key}"
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

    async def _make_request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, signed: bool = True) -> Dict[str, Any]:
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

    async def get_kline(self, **kwargs) -> Dict[str, Any]:
        return await self._make_request("GET", "/v5/market/kline", kwargs, signed=False)

    async def get_instruments_info(self, **kwargs) -> Dict[str, Any]:
        return await self._make_request("GET", "/v5/market/instruments-info", kwargs, signed=False)

    async def get_positions(self, **kwargs) -> Dict[str, Any]:
        return await self._make_request("GET", "/v5/position/list", kwargs)

    async def create_order(self, **kwargs) -> Dict[str, Any]:
        return await self._make_request("POST", "/v5/order/create", kwargs)

    async def set_trading_stop(self, **kwargs) -> Dict[str, Any]:
        return await self._make_request("POST", "/v5/position/set-trading-stop", kwargs)

    async def _connect_ws(self) -> None:
        if self.connection_state.is_connected and self.websocket:
            return

        self._ws_authenticated_event.clear()
        self.connection_state.is_connected = False
        self.connection_state.is_authenticated = False

        try:
            self.websocket = await websockets.connect(
                self.base_ws_private_url,
                ping_interval=20,
                ping_timeout=10
            )
            self.connection_state.is_connected = True
            logger.info(f"{Color.GREEN}Connected to Bybit private WebSocket.{Color.RESET}")

            expires = await self._get_server_time_ms() + 10000
            signature = self._generate_ws_signature(expires)
            auth_message = {"op": "auth", "args": [self.api_key, expires, signature]}
            await self._send_ws_message(auth_message)
            logger.info(f"{Color.GREEN}WebSocket authentication message sent.{Color.RESET}")

        except websockets.exceptions.WebSocketException as e:
            self.connection_state.is_connected = False
            logger.error(f"{Color.RED}WebSocket connection error: {e}{Color.RESET}")
            raise WebSocketConnectionError(f"WebSocket connection error: {e}")

    async def _send_ws_message(self, message: Dict[str, Any]) -> None:
        if not self.websocket or not self.connection_state.is_connected:
            raise WebSocketConnectionError("WebSocket not connected.")
        await self.websocket.send(json.dumps(message))
        logger.debug(f"WS Sent: {message}")

    async def subscribe_ws_private_topic(self, topic: str) -> None:
        self._subscriptions.add(topic)
        if self.connection_state.is_authenticated:
            await self._send_ws_message({"op": "subscribe", "args": [topic]})
            logger.info(f"{Color.MAGENTA}Subscribing to WebSocket topic: {topic}{Color.RESET}")
        else:
            logger.info(f"{Color.YELLOW}Queued subscription for '{topic}'. Will subscribe after auth.{Color.RESET}")

    async def _resubscribe_topics(self):
        if not self._subscriptions:
            return
        logger.info(f"{Color.GREEN}Resubscribing to topics: {list(self._subscriptions)}{Color.RESET}")
        await self._send_ws_message({"op": "subscribe", "args": list(self._subscriptions)})

    async def start_websocket_listener(self, callback: callable, reconnect_delay: int = 5) -> asyncio.Task:
        async def _listener_task():
            while self.connection_state.is_active:
                try:
                    await self._connect_ws()
                    while self.connection_state.is_connected:
                        try:
                            message = await asyncio.wait_for(self.websocket.recv(), timeout=30)
                            parsed_message = json.loads(message)
                            logger.debug(f"WS Received: {parsed_message}")

                            if parsed_message.get("op") == "auth":
                                if parsed_message.get("success"):
                                    self.connection_state.is_authenticated = True
                                    self._ws_authenticated_event.set()
                                    logger.info(f"{Color.GREEN}WebSocket authenticated successfully.{Color.RESET}")
                                    await self._resubscribe_topics()
                                else:
                                    logger.error(f"{Color.RED}WebSocket auth failed: {parsed_message.get('retMsg', 'Unknown error')}. Full response: {json.dumps(parsed_message)}{Color.RESET}")
                                    break
                            elif parsed_message.get("op") != "pong":
                                await callback(parsed_message)

                        except asyncio.TimeoutError:
                            logger.warning(f"{Color.YELLOW}WebSocket recv timed out. Reconnecting...{Color.RESET}")
                            break
                        except websockets.exceptions.ConnectionClosed as e:
                            logger.warning(f"{Color.YELLOW}WebSocket closed: {e}. Reconnecting...{Color.RESET}")
                            break
                except Exception as e:
                    logger.error(f"{Color.RED}Error in WebSocket listener: {e}. Retrying...{Color.RESET}")
                
                self.connection_state.is_connected = False
                self.connection_state.is_authenticated = False
                self._ws_authenticated_event.clear()
                if self.connection_state.is_active:
                    await asyncio.sleep(reconnect_delay)
            logger.info(f"{Color.YELLOW}WebSocket listener stopped.{Color.RESET}")
        return asyncio.create_task(_listener_task())