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
from dataclasses import dataclass, field
from dotenv import load_dotenv

# --- Load environment variables for API keys ---
# This allows storing sensitive keys in a .env file for better security.
load_dotenv()

# --- Constants ---
DEFAULT_RECV_WINDOW = 10000  # Default receive window for API requests in milliseconds
MAX_RETRIES = 3             # Maximum number of retries for failed requests
INITIAL_BACKOFF = 1         # Initial delay in seconds for exponential backoff
WS_PING_INTERVAL = 20       # Interval in seconds for sending WebSocket pings
WS_PING_TIMEOUT = 10        # Timeout in seconds for receiving a WebSocket pong after a ping
WS_RECONNECT_DELAY = 5      # Default delay in seconds before attempting WebSocket reconnection
AUTH_EXPIRES_MS = 30000     # Validity period for WebSocket authentication signatures in milliseconds

# --- Logging Configuration ---
# Configures the logger to output messages with timestamps and severity levels.
logger = logging.getLogger(__name__)

# --- Color Codex (Pyrmethus Style) ---
# Defines ANSI escape codes for colored terminal output, aligning with Pyrmethus's aesthetic.
class Color:
    RESET = getattr(logging, '_color_reset', "\033[0m")
    BOLD = getattr(logging, '_color_bold', "\033[1m")
    DIM = getattr(logging, '_color_dim', "\033[2m")
    RED = getattr(logging, '_color_red', "\033[31m")
    GREEN = getattr(logging, '_color_green', "\033[32m")
    YELLOW = getattr(logging, '_color_yellow', "\033[33m")
    BLUE = getattr(logging, '_color_blue', "\033[34m")
    MAGENTA = getattr(logging, '_color_magenta', "\033[35m")
    CYAN = getattr(logging, '_color_cyan', "\033[36m")

    # Pyrmethus specific thematic colors
    PYRMETHUS_GREEN = GREEN
    PYRMETHUS_BLUE = BLUE
    PYRMETHUS_PURPLE = MAGENTA
    PYRMETHUS_ORANGE = YELLOW
    PYRMETHUS_GREY = DIM
    PYRMETHUS_YELLOW = YELLOW
    PYRMETHUS_CYAN = CYAN

    @staticmethod
    def setup_logging(level=logging.INFO):
        """Initializes the logging configuration with custom formatting and colors."""
        logging.basicConfig(level=level, format=f'%(asctime)s - {Color.CYAN}%(levelname)s{Color.RESET} - %(message)s')

# Initialize logging with default level
Color.setup_logging()

# --- Custom Exceptions ---
# Define custom exceptions for better error management and clarity.
class BybitAPIError(Exception):
    """Custom exception for Bybit API errors, capturing return codes and messages."""
    def __init__(self, ret_code: int, ret_msg: str, original_response: Dict):
        self.ret_code = ret_code
        self.ret_msg = ret_msg
        self.original_response = original_response
        super().__init__(f"{Color.RED}Bybit API Error {Color.BOLD}{ret_code}{Color.RESET}{Color.RED}: {ret_msg}{Color.RESET}")

class WebSocketConnectionError(Exception):
    """Custom exception for WebSocket connection-related issues."""
    pass

class RESTRequestError(Exception):
    """Custom exception for failures during REST API requests."""
    pass

# --- API Endpoints Configuration ---
# Define base URLs for Bybit's REST and WebSocket APIs for both mainnet and testnet.
BYBIT_REST_MAINNET = "https://api.bybit.com"
BYBIT_REST_TESTNET = "https://api-testnet.bybit.com"
BYBIT_WS_PRIVATE_MAINNET = "wss://stream.bybit.com/v5/private"
BYBIT_WS_PRIVATE_TESTNET = "wss://stream-testnet.bybit.com/v5/private"
BYBIT_WS_PUBLIC_LINEAR_MAINNET = "wss://stream.bybit.com/v5/public/linear"
BYBIT_WS_PUBLIC_LINEAR_TESTNET = "wss://stream-testnet.bybit.com/v5/public/linear"

# Rate Limiting Constants
RATE_LIMIT_INTERVAL = 2  # seconds
RATE_LIMIT_CALLS = 120   # calls per interval


# --- Data Structures ---
@dataclass
class ConnectionState:
    """
    Tracks the state of a WebSocket connection, including connection status,
    authentication, activity, and timing information for ping/pong.
    """
    is_connected: bool = False
    is_authenticated: bool = False
    is_active: bool = True  # Flag to control the listener loop
    last_ping_time: float = 0.0
    last_pong_time: float = 0.0
    websocket_instance: Optional[websockets.WebSocketClientProtocol] = None
    listener_task: Optional[asyncio.Task] = None
    # Event to signal successful WebSocket authentication
    _ws_authenticated_event: asyncio.Event = field(default_factory=asyncio.Event)

# --- Exponential Backoff Strategy ---
class ExponentialBackoff:
    """
    Implements an exponential backoff strategy for managing retry delays.
    Helps to avoid overwhelming a service during temporary outages.
    """
    def __init__(self, initial_delay=5, max_delay=60):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.current_delay = initial_delay

    def next(self):
        """Returns the next delay time and updates the internal state."""
        result = self.current_delay
        # Increase delay exponentially, capped at max_delay
        self.current_delay = min(self.current_delay * 2, self.max_delay)
        return result

    def reset(self):
        """Resets the backoff delay to the initial value."""
        self.current_delay = self.initial_delay

# --- Main API Client Class ---
class BybitContractAPI:
    """
    A comprehensive asynchronous Python client for Bybit V5 Contract Account API.
    Forged with robust reconnection, error handling, rate limiting, and structured message processing,
    designed for use within the Termux environment.
    """
    def __init__(self, testnet: bool = False, log_level: int = logging.INFO):
        """
        Initializes the Bybit API client.

        Args:
            testnet (bool): Whether to use the Bybit testnet environment. Defaults to False.
            log_level (int): The logging level for output messages. Defaults to logging.INFO.
        """
        logger.setLevel(log_level)
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")

        # Validate that API keys are provided
        if not api_key or not api_secret:
            raise ValueError(f"{Color.RED}Arcane keys (API Key and Secret) must be set in BYBIT_API_KEY and BYBIT_API_SECRET environment variables.{Color.RESET}")

        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip().encode('utf-8') # Encode secret for HMAC

        # Set base URLs based on the testnet flag
        self.base_rest_url = BYBIT_REST_TESTNET if testnet else BYBIT_REST_MAINNET
        self.base_ws_private_url = BYBIT_WS_PRIVATE_TESTNET if testnet else BYBIT_WS_PRIVATE_MAINNET
        self.base_ws_public_linear_url = BYBIT_WS_PUBLIC_LINEAR_TESTNET if testnet else BYBIT_WS_PUBLIC_LINEAR_MAINNET

        # Initialize httpx client for REST requests with appropriate timeouts
        self.client = httpx.AsyncClient(
            base_url=self.base_rest_url,
            timeout=httpx.Timeout(5.0, connect=5.0, read=30.0) # Connect timeout, read timeout
        )

        # Initialize connection state trackers for private and public WebSockets
        self.private_connection_state = ConnectionState()
        self.public_connection_state = ConnectionState()

        # WebSocket ping/pong configuration
        self.ws_ping_interval = WS_PING_INTERVAL
        self.ws_ping_timeout = WS_PING_TIMEOUT

        # REST API Rate Limiting Configuration
        self.rest_rate_limit_interval = RATE_LIMIT_INTERVAL # Interval for tracking calls
        self.rest_rate_limit_calls = RATE_LIMIT_CALLS     # Max calls within the interval
        self._last_rest_call_time = 0.0                   # Timestamp of the last REST call
        self._rest_call_count = 0                         # Counter for REST calls within the interval

        # Initialize sets to keep track of subscribed topics for each WebSocket type
        self._private_subscriptions: set = set()
        self._public_subscriptions: set = set()

        logger.info(f"{Color.PYRMETHUS_GREEN}BybitContractAPI initialized. Testnet mode: {testnet}{Color.RESET}")

    async def __aenter__(self):
        """Enters the asynchronous context manager, returning the API client instance."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exits the asynchronous context manager, ensuring all connections are gracefully closed."""
        await self.close_connections()

    async def close_connections(self):
        """
        Gracefully closes all active connections (REST and WebSocket).
        This is crucial for releasing resources and ensuring a clean shutdown.
        """
        logger.info(f"{Color.PYRMETHUS_GREY}Initiating closure of all etheric links...{Color.RESET}")
        # Signal that no new connections or operations should be started
        self.private_connection_state.is_active = False
        self.public_connection_state.is_active = False

        # Close active WebSocket connections
        for state in [self.private_connection_state, self.public_connection_state]:
            if state.websocket_instance and not state.websocket_instance.closed:
                try:
                    await state.websocket_instance.close()
                    logger.info(f"{Color.PYRMETHUS_YELLOW}WebSocket connection closed gracefully.{Color.RESET}")
                except Exception as e:
                    logger.warning(f"{Color.PYRMETHUS_YELLOW}Error during WebSocket closure: {e}{Color.RESET}")

        # Close the HTTP client session
        if not self.client.is_closed:
            await self.client.aclose()
            logger.info(f"{Color.PYRMETHUS_YELLOW}HTTP client closed.{Color.RESET}")
        logger.info(f"{Color.PYRMETHUS_GREEN}All connections have been severed.{Color.RESET}")

    # --- Signature Generation ---
    def _generate_rest_signature(self, timestamp: str, recv_window: str, param_str: str) -> str:
        """
        Generates the HMAC-SHA256 signature required for authenticated REST API requests.
        The signature is based on the timestamp, API key, receive window, and the query string or request body.
        """
        signature_string = f"{timestamp}{self.api_key}{recv_window}{param_str}"
        return hmac.new(self.api_secret, signature_string.encode('utf-8'), hashlib.sha256).hexdigest()

    def _generate_ws_signature(self, expires: int) -> str:
        """
        Generates the HMAC-SHA256 signature for WebSocket authentication.
        The signature is based on the HTTP method (GET), endpoint (/realtime), and an expiration timestamp.
        """
        sign_string = f"GET/realtime{expires}"
        return hmac.new(self.api_secret, sign_string.encode('utf-8'), hashlib.sha256).hexdigest()

    # --- Server Time Fetching ---
    async def _get_server_time_ms(self) -> int:
        """
        Fetches the current server time in milliseconds from Bybit's market time endpoint.
        Falls back to local system time if the API call fails, ensuring timestamp availability.
        """
        try:
            response = await self.client.get("/v5/market/time", timeout=5.0)
            response.raise_for_status() # Raise HTTPStatusError for bad responses (4xx or 5xx)
            json_response = response.json()
            if json_response.get("retCode") == 0:
                # Bybit returns timeNano; convert nanoseconds to milliseconds
                return int(int(json_response["result"]["timeNano"]) / 1_000_000)
            else:
                logger.warning(f"{Color.PYRMETHUS_YELLOW}API returned error for time: {json_response.get('retMsg')}. Using local time.{Color.RESET}")
        except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"{Color.PYRMETHUS_YELLOW}Error fetching server time: {e}. Using local time.{Color.RESET}")
        except Exception as e:
            logger.error(f"{Color.RED}An unexpected error occurred fetching server time: {e}. Using local time.{Color.RESET}")

        # Fallback to local time if API call fails or returns unexpected data
        return int(time.time() * 1000)

    # --- REST API Request Handling ---
    async def _rate_limit_wait(self):
        """
        Manages REST API rate limiting. If the call frequency exceeds limits,
        it introduces a delay to comply with Bybit's requirements.
        """
        current_time = time.time()
        elapsed = current_time - self._last_rest_call_time

        # Check if the call limit is about to be reached within the interval
        if elapsed < self.rest_rate_limit_interval and self._rest_call_count >= self.rest_rate_limit_calls:
            wait_time = self.rest_rate_limit_interval - elapsed
            logger.warning(f"{Color.PYRMETHUS_ORANGE}Rate limit approaching. Waiting for {wait_time:.2f} seconds before next REST call.{Color.RESET}")
            await asyncio.sleep(wait_time)
            # Reset time and count after waiting to ensure the next interval starts correctly
            self._last_rest_call_time = time.time()
            self._rest_call_count = 0
        elif elapsed >= self.rest_rate_limit_interval:
            # Reset counters if the interval has passed since the last call batch
            self._rest_call_count = 0
            self._last_rest_call_time = current_time

        self._rest_call_count += 1

    async def _make_request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, body: Optional[Dict[str, Any]] = None, signed: bool = True) -> Dict[str, Any]:
        """
        Core function for making REST API requests. Handles signing, retries, rate limiting,
        and error processing.

        Args:
            method (str): HTTP method (e.g., "GET", "POST").
            endpoint (str): The API endpoint path.
            params (Optional[Dict[str, Any]]): URL parameters for GET requests.
            body (Optional[Dict[str, Any]]): Request body for POST requests.
            signed (bool): Whether the request requires authentication signature.

        Returns:
            Dict[str, Any]: The JSON response from the API.

        Raises:
            RESTRequestError: If the request fails after all retries or encounters critical errors.
            BybitAPIError: If the Bybit API returns an error code.
        """
        await self._rate_limit_wait() # Enforce rate limits before making the call

        for attempt in range(MAX_RETRIES):
            try:
                current_timestamp = str(await self._get_server_time_ms())
                headers = {
                    "X-BAPI-API-KEY": self.api_key,
                    "X-BAPI-TIMESTAMP": current_timestamp,
                    "X-BAPI-RECV-WINDOW": str(DEFAULT_RECV_WINDOW),
                    "Content-Type": "application/json"
                }

                request_kwargs = {"headers": headers}
                response = None

                if signed:
                    if method == "POST":
                        # Serialize body to JSON string for signature and request
                        body_str = json.dumps(body, separators=(",", ":")) if body else ""
                        signature = self._generate_rest_signature(current_timestamp, str(DEFAULT_RECV_WINDOW), body_str)
                        headers["X-BAPI-SIGN"] = signature
                        request_kwargs["content"] = body_str
                        response = await self.client.post(endpoint, **request_kwargs)
                    else: # GET request (signed)
                        # Sort parameters for consistent signature generation
                        query_string = urllib.parse.urlencode(sorted(params.items())) if params else ""
                        signature = self._generate_rest_signature(current_timestamp, str(DEFAULT_RECV_WINDOW), query_string)
                        headers["X-BAPI-SIGN"] = signature
                        request_kwargs["params"] = params
                        response = await self.client.get(endpoint, **request_kwargs)
                else:
                    # Unsigned requests (e.g., market data)
                    if params:
                        request_kwargs["params"] = params
                    response = await self.client.get(endpoint, **request_kwargs)

                response.raise_for_status() # Raise for 4xx/5xx errors
                json_response = response.json()

                # Check for Bybit-specific API errors (retCode != 0)
                if json_response.get("retCode") != 0:
                    raise BybitAPIError(json_response.get("retCode"), json_response.get("retMsg", "Unknown API error"), json_response)

                logger.info(f"{Color.PYRMETHUS_GREEN}REST request successful: {method} {endpoint}{Color.RESET}")
                return json_response

            # Handle specific exceptions during the request
            except httpx.RequestError as e:
                logger.warning(f"{Color.PYRMETHUS_ORANGE}Attempt {attempt + 1}/{MAX_RETRIES}: Request error for {method} {endpoint}: {e}{Color.RESET}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(INITIAL_BACKOFF * (2 ** attempt)) # Exponential backoff
                else:
                    raise RESTRequestError(f"REST request failed after {MAX_RETRIES} retries: {e}") from e
            except httpx.HTTPStatusError as e:
                logger.warning(f"{Color.PYRMETHUS_ORANGE}Attempt {attempt + 1}/{MAX_RETRIES}: HTTP status error for {method} {endpoint}: {e.response.status_code} - {e.response.text}{Color.RESET}")
                # Retry on server errors (5xx), but not client errors (4xx)
                if e.response.status_code >= 500 and attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(INITIAL_BACKOFF * (2 ** attempt))
                else:
                    raise RESTRequestError(f"HTTP error {e.response.status_code} for {method} {endpoint}") from e
            except BybitAPIError as e:
                # Log Bybit API errors and re-raise them for handling by the caller
                logger.error(f"{Color.RED}Bybit API Error for {method} {endpoint}: {e.ret_msg} (Code: {e.ret_code}){Color.RESET}")
                raise
            except Exception as e:
                # Catch any other unexpected errors during the request process
                logger.error(f"{Color.RED}An unexpected error occurred during REST request to {method} {endpoint}: {e}{Color.RESET}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(INITIAL_BACKOFF * (2 ** attempt))
                else:
                    raise RESTRequestError(f"Unexpected error after {MAX_RETRIES} retries for {method} {endpoint}: {e}") from e

        # If the loop completes without returning, all retries have failed
        raise RESTRequestError(f"Failed to complete REST request to {method} {endpoint} after all retries.")

    # --- Public API Endpoints (Unsigned Market Data) ---
    async def get_kline(self, **kwargs) -> Dict[str, Any]:
        """
        Fetches kline (candlestick) data via REST API. Requires 'category' and 'symbol'.
        Example: await api.get_kline(category='linear', symbol='BTCUSD', interval='1', limit=100)
        """
        logger.info(f"{Color.PYRMETHUS_BLUE}Incantation: Fetching Klines for {kwargs.get('symbol')}{Color.RESET}")
        return await self._make_request("GET", "/v5/market/kline", params=kwargs, signed=False)

    async def get_kline_rest_fallback(self, **kwargs) -> Dict[str, Any]:
        """
        Fallback alias for initial kline loading.
        Delegates to the primary get_kline() method.
        """
        logger.info(f"{Color.PYRMETHUS_ORANGE}Invoking REST fallback for Klines: {kwargs.get('symbol')}{Color.RESET}")
        return await self.get_kline(**kwargs)

    async def get_instruments_info(self, **kwargs) -> Dict[str, Any]:
        """
        Fetches instrument information for a given category (e.g., 'linear', 'inverse', 'option').
        Example: await api.get_instruments_info(category='linear', status='Trading')
        """
        logger.info(f"{Color.PYRMETHUS_BLUE}Incantation: Fetching instrument info for category '{kwargs.get('category')}'.{Color.RESET}")
        return await self._make_request("GET", "/v5/market/instruments-info", params=kwargs, signed=False)

    async def get_orderbook(self, **kwargs) -> Dict[str, Any]:
        """
        Fetches order book data for a specified symbol and category.
        Example: await api.get_orderbook(category='linear', symbol='BTCUSD', limit=20)
        """
        logger.info(f"{Color.PYRMETHUS_BLUE}Incantation: Fetching orderbook for {kwargs.get('symbol')}{Color.RESET}")
        return await self._make_request("GET", "/v5/market/orderbook", params=kwargs, signed=False)

    async def get_symbol_ticker(self, **kwargs) -> Dict[str, Any]:
        """
        Fetches the ticker price for a symbol. Requires 'category' and 'symbol'.
        Example: await api.get_symbol_ticker(category='linear', symbol='BTCUSD')
        """
        logger.info(f"{Color.PYRMETHUS_BLUE}Incantation: Fetching ticker for {kwargs.get('symbol')}{Color.RESET}")
        try:
            return await self._make_request("GET", "/v5/market/tickers", params=kwargs, signed=False)
        except BybitAPIError as e:
            # Handle specific error for invalid symbol/category
            if e.ret_code == 10009:
                logger.error(
                    f"{Color.RED}Invalid symbol or category provided: "
                    f"Symbol='{kwargs.get('symbol')}', Category='{kwargs.get('category')}'. {e.ret_msg}{Color.RESET}"
                )
                raise RESTRequestError(f"Invalid symbol/category: {kwargs}") from e
            raise # Re-raise other Bybit API errors
        except Exception as e:
            logger.error(f"{Color.RED}Unexpected error in get_symbol_ticker: {e}{Color.RESET}")
            raise

    # --- Private API Endpoints (Signed Account & Order Data) ---
    async def get_positions(self, **kwargs) -> Dict[str, Any]:
        """
        Fetches current positions for the account. Requires 'category'. Optional: 'symbol'.
        Example: await api.get_positions(category='linear', symbol='BTCUSD')
        """
        logger.info(f"{Color.PYRMETHUS_PURPLE}Incantation: Fetching positions...{Color.RESET}")
        return await self._make_request("GET", "/v5/position/list", params=kwargs)

    async def create_order(self, **kwargs) -> Dict[str, Any]:
        """
        Creates a new order. Requires parameters like 'category', 'symbol', 'side', 'orderType', 'qty'.
        'price' is required for LIMIT orders.
        Example: await api.create_order(category='linear', symbol='BTCUSD', side='Buy', orderType='Limit', qty='100', price='30000')
        """
        logger.info(f"{Color.PYRMETHUS_PURPLE}Incantation: Creating order for {kwargs.get('symbol')} ({kwargs.get('side')})...{Color.RESET}")
        return await self._make_request("POST", "/v5/order/create", signed=True, body=kwargs)

    async def amend_order(self, **kwargs) -> Dict[str, Any]:
        """
        Amends an existing order. Requires 'orderId' or 'orderLinkId', and parameters to change (e.g., 'price', 'qty').
        Example: await api.amend_order(category='linear', symbol='BTCUSD', orderId='12345', p r i c e='31000')
        """
        logger.info(f"{Color.PYRMETHUS_PURPLE}Incantation: Amending order {kwargs.get('orderId', kwargs.get('orderLinkId'))}...{Color.RESET}")
        return await self._make_request("POST", "/v5/order/amend", signed=True, body=kwargs)

    async def set_trading_stop(self, **kwargs) -> Dict[str, Any]:
        """
        Sets or updates stop loss and take profit orders for a position.
        Requires 'positionIdx', 'symbol', and either 'stopLoss' or 'takeProfit'.
        Example: await api.set_trading_stop(category='linear', symbol='BTCUSD', positionIdx='0', stopLoss='29000')
        """
        logger.info(f"{Color.PYRMETHUS_PURPLE}Incantation: Setting trading stop for {kwargs.get('symbol')} (PositionIdx: {kwargs.get('positionIdx')})...{Color.RESET}")
        return await self._make_request("POST", "/v5/position/set-trading-stop", signed=True, body=kwargs)

    async def get_order_status(self, **kwargs) -> Dict[str, Any]:
        """
        Retrieves order status. This method intelligently routes to the correct endpoint
        based on the provided category. For 'linear' or 'inverse', it uses '/v5/order/realtime'.
        For 'spot', it uses '/v5/order/history'.
        """
        logger.info(f"{Color.PYRMETHUS_PURPLE}Incantation: Fetching order status for category '{kwargs.get('category')}'...{Color.RESET}")
        category = kwargs.get('category')
        
        if category in ['linear', 'inverse']:
            # Use the realtime endpoint for derivatives
            return await self._make_request("GET", "/v5/order/realtime", params=kwargs)
        elif category == 'spot':
            # Use the history endpoint for spot
            return await self._make_request("GET", "/v5/order/history", params=kwargs)
        else:
            # Fallback or error for unknown categories
            logger.error(f"{Color.RED}Unsupported category '{category}' for get_order_status.{Color.RESET}")
            raise ValueError(f"Unsupported category for get_order_status: {category}")

    async def get_open_order_id(self, **kwargs) -> Optional[str]:
        """
        Retrieves the order ID of the first open order matching the specified criteria.
        Uses the '/v5/order/realtime' endpoint. Returns None if no matching open order is found.
        Example: await api.get_open_order_id(category='linear', symbol='BTCUSD')
        """
        logger.info(f"{Color.PYRMETHUS_PURPLE}Incantation: Fetching realtime order status...{Color.RESET}")
        try:
            resp = await self._make_request("GET", "/v5/order/realtime", params=kwargs)
            order_list = resp.get("result", {}).get("list", [])
            # Return the orderId of the first order in the list, or None if the list is empty
            return order_list[0].get("orderId") if order_list else None

        except BybitAPIError as e:
            # Handle specific error code for 'Order not found'
            if e.ret_code == 10009:
                logger.info(f"{Color.PYRMETHUS_ORANGE}No open orders found matching criteria: {kwargs}.{Color.RESET}")
                return None
            raise # Re-raise other Bybit API errors

    async def get_wallet_balance(self, **kwargs) -> Dict[str, Any]:
        """
        Retrieves wallet balance information. Requires 'accountType'. Optional: 'coin'.
        Example: await api.get_wallet_balance(accountType='UNIFIED', coin='USDT')
        """
        logger.info(f"{Color.PYRMETHUS_PURPLE}Incantation: Fetching wallet balance...{Color.RESET}")
        return await self._make_request("GET", "/v5/account/wallet-balance", params=kwargs)

    # --- WebSocket Handling ---
    async def _connect_websocket(self, url: str, connection_state: ConnectionState, subscriptions: set, resubscribe_func: Callable, callback: Callable, auth_required: bool = False, reconnect_delay: int = WS_RECONNECT_DELAY) -> Optional[websockets.WebSocketClientProtocol]:
        """
        Establishes a WebSocket connection to the specified URL.
        Handles authentication if required and returns the WebSocket client instance upon success.
        Returns None if the connection fails.
        """
        if connection_state.is_connected and connection_state.is_active:
            logger.debug(f"WebSocket already connected to {url}.")
            return connection_state.websocket_instance

        logger.info(f"{Color.PYRMETHUS_GREY}Attempting to forge etheric link to {url}...{Color.RESET}")
        # Reset connection state before attempting a new connection
        connection_state.is_connected = False
        connection_state.is_authenticated = False
        connection_state._ws_authenticated_event.clear()

        ws = None # Initialize ws to None
        try:
            ws = await websockets.connect(
                url,
                ping_interval=self.ws_ping_interval,
                ping_timeout=self.ws_ping_timeout,
                open_timeout=15 # Timeout for establishing the connection
            )
            connection_state.websocket_instance = ws
            connection_state.is_connected = True
            logger.info(f"{Color.PYRMETHUS_GREEN}Etheric link established: {url}{Color.RESET}")

            # Handle authentication for private channels
            if auth_required:
                expires = int(time.time() * 1000) + AUTH_EXPIRES_MS
                sig = self._generate_ws_signature(expires)
                auth_msg = {"op": "auth", "args": [self.api_key, expires, sig]}
                await self._send_ws_message(ws, auth_msg, is_private=True)

                try:
                    # Wait for authentication confirmation with a timeout
                    await asyncio.wait_for(connection_state._ws_authenticated_event.wait(), timeout=10.0)
                except asyncio.TimeoutError:
                    logger.error(f"{Color.RED}WebSocket authentication timed out for {url}. Closing connection.{Color.RESET}")
                    await ws.close() # Close if authentication fails
                    connection_state.is_connected = False
                    return None # Indicate connection failure
                else:
                    logger.info(f"{Color.PYRMETHUS_GREEN}Authenticated successfully via WebSocket. Preparing to subscribe to topics.{Color.RESET}")

            # Resubscribe to topics after successful connection/authentication
            await resubscribe_func()
            return ws

        except (websockets.exceptions.WebSocketException, ConnectionError, asyncio.TimeoutError) as e:
            logger.error(f"{Color.RED}Failed to establish WebSocket connection to {url}: {e}{Color.RESET}")
            # Clean up potentially half-opened connection
            if ws and not ws.closed:
                try: await ws.close()
                except Exception: pass
            connection_state.is_connected = False
            return None # Indicate connection failure
        except Exception as e:
            logger.error(f"{Color.RED}An unexpected error occurred during WebSocket connection to {url}: {e}{Color.RESET}")
            if ws and not ws.closed:
                try: await ws.close()
                except Exception: pass
            connection_state.is_connected = False
            return None # Indicate connection failure

    async def _send_ws_message(self, websocket: Optional[websockets.WebSocketClientProtocol], message: Dict[str, Any], is_private: bool = False) -> None:
        """
        Safely sends a JSON-encoded message over the WebSocket connection.
        Handles cases where the WebSocket might be closed or disconnected.
        """
        state = self.private_connection_state if is_private else self.public_connection_state

        if not websocket:
            state.is_connected = False # Mark as disconnected if sending fails
            logger.warning(f"{Color.PYRMETHUS_ORANGE}Cannot send message: WebSocket is not connected. Message dropped: {message}{Color.RESET}")
            return

        try:
            await websocket.send(json.dumps(message))
            logger.debug(f"{'Private' if is_private else 'Public'} WS → {message}")
        except websockets.exceptions.ConnectionClosed:
            state.is_connected = False # Mark as disconnected on send error
            logger.error(f"{Color.RED}WebSocket send failed: Connection is closed. Marking connection as closed.{Color.RESET}")
        except Exception as e:
            state.is_connected = False # Mark as disconnected on other send errors
            logger.error(f"{Color.RED}WebSocket send failed: {e}. Marking connection as closed.{Color.RESET}")

    async def _resubscribe_topics(self, connection_state: ConnectionState, subscriptions: set, url: str, is_private: bool) -> None:
        """
        Resubscribes to all tracked topics when a WebSocket connection is re-established.
        This ensures data streams are maintained after reconnections.
        """
        if not connection_state.is_connected or not subscriptions:
            logger.debug(f"Skipping resubscribe: Connected={connection_state.is_connected}, Subscriptions={len(subscriptions)}.")
            return

        logger.info(f"{Color.PYRMETHUS_CYAN}Resubscribing to {'private' if is_private else 'public'} WebSocket topics...{Color.RESET}")
        message = {"op": "subscribe", "args": list(subscriptions)}
        await self._send_ws_message(connection_state.websocket_instance, message, is_private=is_private)

    async def _message_receiving_loop(self, websocket: websockets.WebSocketClientProtocol, connection_state: ConnectionState, auth_required: bool, callback: Callable):
        """
        The core loop for receiving and processing messages from a WebSocket connection.
        Handles pings, authentication responses, and dispatches messages to the user-defined callback.
        Breaks the loop on connection closure or critical errors, triggering reconnection logic.
        """
        while connection_state.is_active:
            try:
                # Wait for a message with a timeout slightly longer than ping interval to detect inactivity
                message = await asyncio.wait_for(websocket.recv(), timeout=self.ws_ping_interval + self.ws_ping_timeout)

                # Attempt to parse the received message as JSON
                try:
                    parsed_message = json.loads(message)
                    logger.debug(f"{'Private' if auth_required else 'Public'} WS Received: {parsed_message}")
                except json.JSONDecodeError:
                    logger.error(f"{Color.RED}Failed to decode JSON message: {message}{Color.RESET}")
                    continue # Skip malformed messages

                # Handle WebSocket control messages (e.g., pong)
                if parsed_message.get("op") == "pong":
                    connection_state.last_pong_time = time.time()
                    logger.debug(f"{'Private' if auth_required else 'Public'} WS Pong received.")
                    continue

                # Handle WebSocket authentication response
                if auth_required and parsed_message.get("op") == "auth":
                    if parsed_message.get("success"):
                        connection_state.is_authenticated = True
                        connection_state._ws_authenticated_event.set() # Signal successful authentication
                        logger.info(f"{Color.PYRMETHUS_GREEN}Private WebSocket authenticated successfully.{Color.RESET}")
                    else:
                        logger.error(f"{Color.RED}Private WebSocket authentication failed: {parsed_message.get('retMsg', 'Unknown error')}. Response: {json.dumps(parsed_message)}{Color.RESET}")
                        break # Critical failure, break loop to trigger reconnection
                    continue # Processed auth message, move to next

                # Dispatch the message to the user-provided callback function
                await callback(parsed_message)

            except asyncio.TimeoutError:
                # Ping timeout: Check if we received a pong since the last ping
                logger.warning(f"{Color.PYRMETHUS_ORANGE}{'Private' if auth_required else 'Public'} WebSocket recv timed out. Checking connection health...{Color.RESET}")
                if connection_state.last_pong_time < connection_state.last_ping_time:
                    # No pong received, connection is likely dead
                    logger.error(f"{Color.RED}No pong received after ping. Connection likely dead. Triggering reconnection.{Color.RESET}")
                    break # Break loop to initiate reconnection
                else:
                    # Connection seems alive, send a ping to verify
                    connection_state.last_ping_time = time.time()
                    try:
                        await websocket.ping()
                        logger.debug(f"{'Private' if auth_required else 'Public'} WS Ping sent.")
                    except Exception as ping_e:
                         logger.error(f"{Color.RED}Error sending ping: {ping_e}{Color.RESET}")
                         break # Break loop if ping fails

            except websockets.exceptions.ConnectionClosed as e:
                # Handle normal WebSocket closure
                logger.warning(f"{Color.PYRMETHUS_ORANGE}{'Private' if auth_required else 'Public'} WebSocket connection closed: {e}. Triggering reconnection...{Color.RESET}")
                break # Break loop to initiate reconnection
            except Exception as e:
                # Catch any other unexpected errors during message processing
                logger.error(f"{Color.RED}Error processing message in {'private' if auth_required else 'public'} WebSocket listener: {e}{Color.RESET}")
                # Break loop for critical errors that might indicate a broken connection
                if isinstance(e, (WebSocketConnectionError, RESTRequestError)):
                    break

        # --- Cleanup after loop exit ---
        logger.info(f"{Color.PYRMETHUS_GREY}Message receiving loop ended for {'private' if auth_required else 'public'} WS.{Color.RESET}")
        # Reset connection state flags
        connection_state.is_connected = False
        connection_state.is_authenticated = False
        if auth_required: connection_state._ws_authenticated_event.clear()

        # Ensure the websocket instance is properly closed if it exists and is not already closed
        if websocket and not websocket.closed:
            try:
                await websocket.close()
                logger.info(f"{Color.PYRMETHUS_YELLOW}WebSocket instance closed during loop exit.{Color.RESET}")
            except Exception as close_e:
                logger.warning(f"{Color.PYRMETHUS_YELLOW}Error during WebSocket closure in loop exit: {close_e}{Color.RESET}")

        connection_state.websocket_instance = None # Clear the instance reference

    async def start_websocket_listener(self, url: str, connection_state: ConnectionState, subscriptions: set, resubscribe_func: Callable, callback: Callable, auth_required: bool = False, reconnect_delay: int = WS_RECONNECT_DELAY) -> asyncio.Task:
        """
        Starts a persistent listener task for a given WebSocket URL.
        Manages the connection lifecycle, including connection attempts, authentication,
        message reception, and automatic reconnection using exponential backoff.
        """
        async def _listener_task():
            backoff = ExponentialBackoff(initial_delay=reconnect_delay, max_delay=60)
            while connection_state.is_active:
                websocket = None
                try:
                    # Attempt to establish the WebSocket connection
                    websocket = await self._connect_websocket(url, connection_state, subscriptions, resubscribe_func, callback, auth_required, reconnect_delay)

                    if not websocket: # Connection failed, wait before retrying
                        logger.warning(f"{Color.PYRMETHUS_ORANGE}Connection failed. Waiting {backoff.current_delay}s before retry...{Color.RESET}")
                        await asyncio.sleep(backoff.next())
                        continue # Retry the connection attempt
                    else:
                        backoff.reset() # Reset backoff strategy on successful connection

                    # If connection is successful, start the message receiving loop
                    await self._message_receiving_loop(websocket, connection_state, auth_required, callback)

                except WebSocketConnectionError as e:
                    # Error already logged within _connect_websocket or _message_receiving_loop
                    pass
                except Exception as e:
                    # Catch any unexpected errors in the listener task itself
                    logger.error(f"{Color.RED}Unhandled exception in {'private' if auth_required else 'public'} WebSocket listener task: {e}{Color.RESET}")

                # --- Reconnection Logic ---
                # Reset connection state flags after loop breaks (due to error or closure)
                connection_state.is_connected = False
                connection_state.is_authenticated = False
                if auth_required: connection_state._ws_authenticated_event.clear()

                # Clean up the websocket instance if it exists and is not already closed
                if websocket and not websocket.closed:
                    try: await websocket.close()
                    except Exception as close_e: logger.warning(f"Error during cleanup close in listener task: {close_e}{Color.RESET}")

                connection_state.websocket_instance = None # Clear the reference

                # If the listener is still meant to be active, wait before attempting to reconnect
                if connection_state.is_active:
                    logger.info(f"{Color.PYRMETHUS_ORANGE}Waiting {backoff.current_delay} seconds before attempting to re-establish connection...{Color.RESET}")
                    await asyncio.sleep(backoff.next())

            # Exit loop if connection_state.is_active becomes False
            logger.info(f"{Color.PYRMETHUS_GREY}Exiting {'private' if auth_required else 'public'} WebSocket listener task loop.{Color.RESET}")

        # Create and return the task
        task = asyncio.create_task(_listener_task())
        connection_state.listener_task = task # Store the task reference
        return task

    # --- Public Methods for Starting Listeners ---
    def start_private_websocket_listener(self, callback: Callable, reconnect_delay: int = WS_RECONNECT_DELAY) -> asyncio.Task:
        """
        Starts the listener task for private WebSocket events (e.g., account updates, orders).
        Requires authentication.
        """
        logger.info(f"{Color.PYRMETHUS_CYAN}Summoning private WebSocket listener...{Color.RESET}")
        task = self.start_websocket_listener(
            self.base_ws_private_url,
            self.private_connection_state,
            self._private_subscriptions,
            lambda: self._resubscribe_topics(self.private_connection_state, self._private_subscriptions, self.base_ws_private_url, is_private=True),
            callback,
            auth_required=True,
            reconnect_delay=reconnect_delay
        )
        return task

    def start_public_websocket_listener(self, callback: Callable, reconnect_delay: int = WS_RECONNECT_DELAY) -> asyncio.Task:
        """
        Starts the listener task for public WebSocket events (e.g., market data, tickers).
        Does not require authentication.
        """
        logger.info(f"{Color.PYRMETHUS_CYAN}Summoning public WebSocket listener...{Color.RESET}")
        task = self.start_websocket_listener(
            self.base_ws_public_linear_url,
            self.public_connection_state,
            self._public_subscriptions,
            lambda: self._resubscribe_topics(self.public_connection_state, self._public_subscriptions, self.base_ws_public_linear_url, is_private=False),
            callback,
            auth_required=False,
            reconnect_delay=reconnect_delay
        )
        return task

    # --- Methods for Subscribing to WebSocket Topics ---
    async def subscribe_ws_private_topic(self, topic: str) -> None:
        """
        Subscribes to a private WebSocket topic. If the connection is not active,
        the subscription is queued and will be processed upon reconnection.
        """
        if not self.private_connection_state.is_connected:
            logger.info(f"{Color.PYRMETHUS_ORANGE}Queued private subscription for '{topic}'. Will subscribe upon connection establishment.{Color.RESET}")
            self._private_subscriptions.add(topic)
            return
        # If connected, attempt immediate subscription
        await self._subscribe_ws_topic(self.private_connection_state.websocket_instance, self._private_subscriptions, topic, is_private=True)

    async def subscribe_ws_public_topic(self, topic: str) -> None:
        """
        Subscribes to a public WebSocket topic. If the connection is not active,
        the subscription is queued and will be processed upon reconnection.
        """
        if not self.public_connection_state.is_connected:
            logger.info(f"{Color.PYRMETHUS_ORANGE}Queued public subscription for '{topic}'. Will subscribe upon connection establishment.{Color.RESET}")
            self._public_subscriptions.add(topic)
            return
        # If connected, attempt immediate subscription
        await self._subscribe_ws_topic(self.public_connection_state.websocket_instance, self._public_subscriptions, topic, is_private=False)

    async def _subscribe_ws_topic(self, websocket: Optional[websockets.WebSocketClientProtocol], subscriptions: set, topic: str, is_private: bool = False) -> None:
        """
        Internal method to handle the subscription logic, preventing duplicate subscriptions
        and sending the subscription message via WebSocket.
        """
        if topic in subscriptions:
            logger.debug(f"Already subscribed to topic '{topic}'.")
            return

        logger.info(f"{Color.PYRMETHUS_CYAN}Subscribing to topic: '{topic}'...{Color.RESET}")
        subscriptions.add(topic) # Add topic to the set of tracked subscriptions
        sub_msg = {"op": "subscribe", "args": [topic]}
        await self._send_ws_message(websocket, sub_msg, is_private)

# --- Example Usage ---
async def main_example():
    """
    Demonstrates the usage of the BybitContractAPI client within a Termux environment.
    Requires Bybit API keys to be set as environment variables (BYBIT_API_KEY, BYBIT_API_SECRET).
    Install dependencies: pkg install python && pip install httpx websockets python-dotenv
    """
    print(f"{Color.BOLD}--- Pyrmethus's Bybit Contract API Demonstration ---{Color.RESET}")

    api = None # Initialize api to None for finally block
    try:
        # Initialize the API client (use testnet=True for testing Bybit's test environment)
        api = BybitContractAPI(testnet=True)

        print(f"\n{Color.BOLD}--- REST API Incantations ---{Color.RESET}")
        try:
            # Fetch server time to verify connection and timestamp synchronization
            server_time = await api.get_server_time_ms()
            print(f"{Color.PYRMETHUS_GREEN}Current Server Time: {server_time}{Color.RESET}")

            # Fetch instrument information for BTCUSD in the linear category
            instruments = await api.get_instruments_info(category="linear", symbol="BTCUSD")
            if instruments and instruments.get('result', {}).get('list'):
                instrument_data = instruments['result']['list'][0]
                print(f"{Color.PYRMETHUS_GREEN}Instrument Info (BTCUSD):{Color.RESET}")
                print(f"  - Symbol: {instrument_data.get('symbol')}")
                print(f"  - Last Price: {instrument_data.get('lastPrice')}")
                print(f"  - Price Scale: {instrument_data.get('priceScale')}")

            # Fetch ticker price for BTCUSD
            ticker = await api.get_symbol_ticker(category="linear", symbol="BTCUSD")
            if ticker and ticker.get('result', {}).get('list'):
                 ticker_data = ticker['result']['list'][0]
                 print(f"{Color.PYRMETHUS_GREEN}BTCUSD Ticker:{Color.RESET}")
                 print(f"  - Last Price: {ticker_data.get('lastPrice')}")
                 print(f"  - High Price: {ticker_data.get('highPrice')}")
                 print(f"  - Low Price: {ticker_data.get('lowPrice')}")

            # Fetch current positions (requires authentication)
            positions = await api.get_positions(category="linear")
            print(f"{Color.PYRMETHUS_PURPLE}Current Positions:{Color.RESET}")
            print(json.dumps(positions, indent=2))

        except (BybitAPIError, RESTRequestError, ValueError, httpx.HTTPStatusError, httpx.RequestError) as e:
            print(f"{Color.RED}REST API Error during example: {e}{Color.RESET}")
        except Exception as e:
            print(f"{Color.RED}An unexpected error occurred during REST examples: {e}{Color.RESET}")

        print(f"\n{Color.BOLD}--- WebSocket Whispers ---{Color.RESET}")

        # Define callback functions for processing WebSocket messages
        def private_callback(message):
            """Callback for private WebSocket messages."""
            print(f"{Color.PYRMETHUS_CYAN}Private WS Callback:{Color.RESET} {message}")

        def public_callback(message):
            """Callback for public WebSocket messages."""
            print(f"{Color.PYRMETHUS_CYAN}Public WS Callback:{Color.RESET} {message}")

        # Start the WebSocket listeners asynchronously
        private_listener_task = api.start_private_websocket_listener(private_callback)
        public_listener_task = api.start_public_websocket_listener(public_callback)

        # Allow time for listeners to establish connections and authenticate
        await asyncio.sleep(5) # Increased delay for connection and auth

        # Subscribe to specific topics to receive real-time data
        await api.subscribe_ws_private_topic("position") # Subscribe to position updates
        await api.subscribe_ws_public_topic("kline.1.BTCUSD") # Subscribe to 1-minute BTCUSD klines
        await api.subscribe_ws_public_topic("tickers.linear") # Subscribe to all linear tickers

        print(f"\n{Color.PYRMETHUS_YELLOW}WebSocket listeners active. Monitoring topics for 30 seconds... Press Ctrl+C to stop early.{Color.RESET}")
        # Keep the example running for a duration to observe WebSocket messages
        await asyncio.sleep(30)

    except ValueError as e:
        print(f"{Color.RED}Initialization Error: {e}{Color.RESET}")
    except WebSocketConnectionError as e:
        print(f"{Color.RED}WebSocket Connection Error: {e}{Color.RESET}")
    except Exception as e:
        print(f"{Color.RED}An unexpected error occurred in main_example: {e}{Color.RESET}")
    finally:
        # Ensure all connections are closed properly, regardless of success or failure
        if api:
            print(f"\n{Color.PYRMETHUS_GREY}Concluding the demonstration. Closing all connections...{Color.RESET}")
            await api.close_connections()

# --- Script Execution Entry Point ---
if __name__ == "__main__":
    # This block executes when the script is run directly.
    # It handles the asynchronous execution of the main example function.
    try:
        asyncio.run(main_example())
    except KeyboardInterrupt:
        # Gracefully handle user interruption (Ctrl+C)
        print(f"\n{Color.PYRMETHUS_GREY}Demonstration interrupted by user.{Color.RESET}")
