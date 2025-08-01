import asyncio
import hashlib
import hmac
import json
import time
import urllib.parse
import logging
import os
import random
from typing import Dict, Any, Optional, Set, Callable, Union, Awaitable
import httpx
import websockets
from dataclasses import dataclass, field
from dotenv import load_dotenv
from decimal import Decimal, InvalidOperation
import traceback

# --- Load environment variables for API keys ---
load_dotenv(override=True)

# --- Constants ---
DEFAULT_RECV_WINDOW = 10000
MAX_RETRIES = 3
INITIAL_BACKOFF = 1
WS_PING_INTERVAL = 20
WS_PING_TIMEOUT = 10
WS_RECONNECT_DELAY = 5
AUTH_EXPIRES_MS = 30000

# --- Logging Configuration ---
logger = logging.getLogger(__name__)

class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

    PYRMETHUS_GREEN = GREEN
    PYRMETHUS_BLUE = BLUE
    PYRMETHUS_PURPLE = MAGENTA
    PYRMETHUS_ORANGE = YELLOW
    PYRMETHUS_GREY = DIM
    PYRMETHUS_YELLOW = YELLOW
    PYRMETHUS_CYAN = CYAN

    @staticmethod
    def setup_logging(level=logging.INFO):
        class ColorFormatter(logging.Formatter):
            LEVEL_COLORS = {
                logging.DEBUG: Color.DIM,
                logging.INFO: Color.CYAN,
                logging.WARNING: Color.YELLOW,
                logging.ERROR: Color.RED,
                logging.CRITICAL: Color.BOLD + Color.RED,
            }
            def format(self, record):
                color = self.LEVEL_COLORS.get(record.levelno, Color.RESET)
                record.levelname = f"{color}{record.levelname}{Color.RESET}"
                return super().format(record)
        handler = logging.StreamHandler()
        handler.setFormatter(ColorFormatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(level)

Color.setup_logging()

# --- Custom Exceptions ---
class BybitAPIError(Exception):
    def __init__(self, ret_code: int, ret_msg: str, original_response: Dict):
        self.ret_code, self.ret_msg, self.original_response = ret_code, ret_msg, original_response
        super().__init__(f"{Color.RED}Bybit API Error {Color.BOLD}{ret_code}{Color.RESET}{Color.RED}: {ret_msg}{Color.RESET}")

class WebSocketConnectionError(Exception): pass
class RESTRequestError(Exception): pass

# --- API Endpoints ---
BYBIT_REST_MAINNET = "https://api.bybit.com"
BYBIT_REST_TESTNET = "https://api-testnet.bybit.com"
BYBIT_WS_PRIVATE_MAINNET = "wss://stream.bybit.com/v5/private"
BYBIT_WS_PRIVATE_TESTNET = "wss://stream-testnet.bybit.com/v5/private"
BYBIT_WS_PUBLIC_LINEAR_MAINNET = "wss://stream.bybit.com/v5/public/linear"
BYBIT_WS_PUBLIC_LINEAR_TESTNET = "wss://stream-testnet.bybit.com/v5/public/linear"

# --- Rate Limiter Class ---
class RateLimiter:
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = time.time()
            # Filter out calls older than the period
            self.calls = [t for t in self.calls if t > now - self.period]
            
            if len(self.calls) >= self.max_calls:
                # Calculate time to wait until the first call in the window expires
                wait_time = self.period - (now - self.calls[0])
                logger.warning(f"{Color.PYRMETHUS_ORANGE}Rate limit hit. Waiting for {wait_time:.2f}s.{Color.RESET}")
                await asyncio.sleep(wait_time)
                # After waiting, re-filter calls and add the new one
                now = time.time()
                self.calls = [t for t in self.calls if t > now - self.period]
            self.calls.append(now)

# --- Data Structures ---
@dataclass
class ConnectionState:
    is_connected: bool = False
    is_authenticated: bool = False
    is_active: bool = True
    last_ping_time: float = 0.0
    last_pong_time: float = 0.0
    websocket_instance: Optional[websockets.WebSocketClientProtocol] = None
    listener_task: Optional[asyncio.Task] = None
    _ws_authenticated_event: asyncio.Event = field(default_factory=asyncio.Event)

class ExponentialBackoff:
    def __init__(self, initial_delay=5, max_delay=60):
        self.initial_delay, self.max_delay, self.current_delay = initial_delay, max_delay, initial_delay
    def next(self) -> float:
        result = self.current_delay
        self.current_delay = min(self.current_delay * 2, self.max_delay)
        return result
    def reset(self): self.current_delay = self.initial_delay

# --- Main API Client Class ---
class BybitContractAPI:
    def __init__(
        self,
        testnet: bool = False,
        log_level: int = logging.INFO,
        ws_kline_normalize_timestamp: bool = True
    ):
        logger.setLevel(log_level)
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")
        if not api_key:
            raise ValueError(f"{Color.RED}Missing environment variable: BYBIT_API_KEY{Color.RESET}")
        if not api_secret:
            raise ValueError(f"{Color.RED}Missing environment variable: BYBIT_API_SECRET{Color.RESET}")
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip().encode('utf-8')

        self.base_rest_url = BYBIT_REST_TESTNET if testnet else BYBIT_REST_MAINNET
        self.base_ws_private_url = BYBIT_WS_PRIVATE_TESTNET if testnet else BYBIT_WS_PRIVATE_MAINNET
        self.base_ws_public_linear_url = BYBIT_WS_PUBLIC_LINEAR_TESTNET if testnet else BYBIT_WS_PUBLIC_LINEAR_MAINNET

        self.client = httpx.AsyncClient(
            base_url=self.base_rest_url,
            timeout=httpx.Timeout(5.0, connect=5.0, read=30.0)
        )

        self.private_connection_state = ConnectionState()
        self.public_connection_state = ConnectionState()
        self.ws_ping_interval = WS_PING_INTERVAL
        self.ws_ping_timeout = WS_PING_TIMEOUT
        
        # --- Rate Limiter Instance ---
        self.rate_limiter = RateLimiter(max_calls=config.API_RATE_LIMIT_CALLS, period=config.API_RATE_LIMIT_PERIOD)

        self._private_subscriptions: Set[str] = set()
        self._public_subscriptions: Set[str] = set()
        self.ws_kline_normalize_timestamp = ws_kline_normalize_timestamp

        logger.info(f"{Color.PYRMETHUS_GREEN}BybitContractAPI initialized. Testnet: {testnet}{Color.RESET}")

    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc_val, exc_tb): await self.close_connections()

    async def close_connections(self):
        logger.info(f"{Color.PYRMETHUS_GREY}Closing all connections...{Color.RESET}")
        self.private_connection_state.is_active = False
        self.public_connection_state.is_active = False
        for state in [self.private_connection_state, self.public_connection_state]:
            if state.websocket_instance:
                try:
                    await state.websocket_instance.close()
                    logger.info(f"{Color.PYRMETHUS_YELLOW}WebSocket closed.{Color.RESET}")
                except Exception as e:
                    logger.warning(f"{Color.PYRMETHUS_YELLOW}Error during WebSocket closure: {e}{Color.RESET}")
        if not self.client.is_closed:
            await self.client.aclose()
            logger.info(f"{Color.PYRMETHUS_YELLOW}HTTP client closed.{Color.RESET}")
        logger.info(f"{Color.PYRMETHUS_GREEN}All connections severed.{Color.RESET}")

    def _convert_to_decimal_recursive(self, obj: Any) -> Any:
        if isinstance(obj, dict): return {k: self._convert_to_decimal_recursive(v) for k, v in obj.items()}
        if isinstance(obj, list): return [self._convert_to_decimal_recursive(elem) for elem in obj]
        if isinstance(obj, str):
            try: return Decimal(obj)
            except (InvalidOperation, ValueError): return obj
        if isinstance(obj, float): return Decimal(str(obj))
        return obj

    def _generate_rest_signature(self, ts: str, recv: str, params: str) -> str:
        return hmac.new(self.api_secret, f"{ts}{self.api_key}{recv}{params}".encode('utf-8'), hashlib.sha256).hexdigest()

    def _generate_ws_signature(self, exp: int) -> str:
        return hmac.new(self.api_secret, f"GET/realtime{exp}".encode('utf-8'), hashlib.sha256).hexdigest()

    async def get_server_time_ms(self) -> int:
        try:
            r = await self.client.get("/v5/market/time", timeout=5.0)
            r.raise_for_status()
            j = r.json()
            if j.get("retCode") == 0: return int(int(j["result"]["timeNano"]) / 1_000_000)
            logger.warning(f"{Color.PYRMETHUS_YELLOW}Time API err: {j.get('retMsg')}. Using local time.{Color.RESET}")
        except Exception as e:
            logger.warning(f"{Color.PYRMETHUS_YELLOW}Error fetching server time: {e}. Using local time.{Color.RESET}")
        return int(time.time() * 1000)

    async def _get_server_time_ms(self) -> int: return await self.get_server_time_ms()

    async def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, body: Optional[Dict] = None, signed: bool = True) -> Dict:
        await self.rate_limiter.acquire() # Acquire a slot from the rate limiter
        for attempt in range(MAX_RETRIES):
            try:
                ts = str(await self._get_server_time_ms())
                headers = {"X-BAPI-API-KEY": self.api_key, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": str(DEFAULT_RECV_WINDOW), "Content-Type": "application/json"}
                kwargs = {"headers": headers}
                if signed:
                    if method == "POST":
                        payload = json.dumps(body, separators=(",", ":")) if body else ""
                        headers["X-BAPI-SIGN"] = self._generate_rest_signature(ts, str(DEFAULT_RECV_WINDOW), payload)
                        kwargs["content"] = payload
                        r = await self.client.post(endpoint, **kwargs)
                    else:
                        payload = urllib.parse.urlencode(sorted(params.items())) if params else ""
                        headers["X-BAPI-SIGN"] = self._generate_rest_signature(ts, str(DEFAULT_RECV_WINDOW), payload)
                        kwargs["params"] = params
                        r = await self.client.get(endpoint, **kwargs)
                else:
                    kwargs["params"] = params if params else {}
                    r = await self.client.get(endpoint, **kwargs)
                r.raise_for_status()
                j = r.json()
                if j.get("retCode") != 0:
                    ret_code = j.get("retCode")
                    ret_msg = j.get("retMsg", "Unknown API error")
                    logger.error(f"{Color.RED}Bybit API Error {ret_code}: {ret_msg} for {method} {endpoint}. Response: {j}{Color.RESET}")
                    raise BybitAPIError(ret_code, ret_msg, j)
                logger.info(f"{Color.PYRMETHUS_GREEN}REST OK: {method} {endpoint}{Color.RESET}")
                return self._convert_to_decimal_recursive(j)
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.warning(f"{Color.PYRMETHUS_ORANGE}Attempt {attempt+1}/{MAX_RETRIES}: HTTP error for {method} {endpoint}: {e}{Color.RESET}")
                if attempt < MAX_RETRIES - 1: await asyncio.sleep(INITIAL_BACKOFF * (2 ** attempt))
                else: raise RESTRequestError(f"HTTP request failed after {MAX_RETRIES} retries.") from e
            except BybitAPIError: 
                # Re-raise BybitAPIError immediately, as it's a specific API response error
                raise
            except Exception as e:
                logger.error(f"{Color.RED}Unexpected REST error for {method} {endpoint}: {e}\n{traceback.format_exc()}{Color.RESET}")
                if attempt < MAX_RETRIES - 1: await asyncio.sleep(INITIAL_BACKOFF * (2 ** attempt))
                else: raise RESTRequestError(f"Unexpected error after {MAX_RETRIES} retries.") from e
        raise RESTRequestError(f"Request failed after all retries.")

    async def get_kline(self, **kwargs) -> Dict: return await self._make_request("GET", "/v5/market/kline", params=kwargs, signed=False)
    async def get_kline_rest_fallback(self, **kwargs) -> Dict: return await self.get_kline(**kwargs)
    async def get_instruments_info(self, **kwargs) -> Dict: return await self._make_request("GET", "/v5/market/instruments-info", params=kwargs, signed=False)
    async def get_orderbook(self, **kwargs) -> Dict: return await self._make_request("GET", "/v5/market/orderbook", params=kwargs, signed=False)
    async def get_symbol_ticker(self, **kwargs) -> Dict: return await self._make_request("GET", "/v5/market/tickers", params=kwargs, signed=False)
    async def get_positions(self, **kwargs) -> Dict: return await self._make_request("GET", "/v5/position/list", params=kwargs)
    async def create_order(self, **kwargs) -> Dict: return await self._make_request("POST", "/v5/order/create", body=kwargs)
    async def amend_order(self, **kwargs) -> Dict: return await self._make_request("POST", "/v5/order/amend", body=kwargs)
    async def trading_stop(self, **kwargs) -> Dict: return await self._make_request("POST", "/v5/position/trading-stop", body=kwargs)
    async def get_wallet_balance(self, **kwargs) -> Dict: return await self._make_request("GET", "/v5/account/wallet-balance", params=kwargs)
    async def get_order_status(self, **kwargs) -> Dict:
        cat = kwargs.get('category')
        if cat in ['linear', 'inverse']: return await self._make_request("GET", "/v5/order/realtime", params=kwargs)
        if cat == 'spot': return await self._make_request("GET", "/v5/order/history", params=kwargs)
        raise ValueError(f"Unsupported category for get_order_status: {cat}")
    async def get_open_order_id(self, **kwargs) -> Optional[str]:
        try:
            resp = await self._make_request("GET", "/v5/order/realtime", params=kwargs)
            orders = resp.get("result", {}).get("list", [])
            return orders[0].get("orderId") if orders else None
        except BybitAPIError as e:
            if e.ret_code in [10009, 110001]: return None
            raise

    async def _connect_websocket(self, url: str, state: ConnectionState, subs: Set[str], resub: Callable, cb: Callable, auth: bool = False) -> Optional[websockets.WebSocketClientProtocol]:
        if state.is_connected and state.is_active: return state.websocket_instance
        logger.info(f"{Color.PYRMETHUS_GREY}Connecting to WebSocket: {url}...{Color.RESET}")
        state.is_connected = state.is_authenticated = False
        state._ws_authenticated_event.clear()
        ws = None
        try:
            # Increased open_timeout for more resilience on slow networks
            ws = await websockets.connect(url, ping_interval=self.ws_ping_interval, ping_timeout=self.ws_ping_timeout, open_timeout=20)
            state.websocket_instance, state.is_connected = ws, True
            logger.info(f"{Color.PYRMETHUS_GREEN}WebSocket connected: {url}{Color.RESET}")
            if auth:
                exp = int(time.time() * 1000) + AUTH_EXPIRES_MS
                sig = self._generate_ws_signature(exp)
                await self._send_ws_message(ws, {"op": "auth", "args": [self.api_key, exp, sig]}, is_private=True)
                await asyncio.wait_for(state._ws_authenticated_event.wait(), timeout=15.0) # Increased auth timeout
                logger.info(f"{Color.PYRMETHUS_GREEN}WS authenticated.{Color.RESET}")
            await resub()
            return ws
        except (websockets.exceptions.WebSocketException, ConnectionError, asyncio.TimeoutError) as e:
            logger.error(f"{Color.RED}WebSocket connection failed for {url}: {e}{Color.RESET}")
        except Exception as e:
            logger.error(f"{Color.RED}Unexpected WS connect error for {url}: {e}\n{traceback.format_exc()}{Color.RESET}")
        if ws:
            try:
                await ws.close()
            except Exception as close_e:
                logger.warning(f"{Color.PYRMETHUS_YELLOW}Error closing failed websocket connection: {close_e}{Color.RESET}")
        state.is_connected = False
        return None

    async def _send_ws_message(self, ws: Optional[websockets.WebSocketClientProtocol], msg: Dict, is_private: bool = False):
        state = self.private_connection_state if is_private else self.public_connection_state
        if not ws:
            state.is_connected = False
            logger.warning(f"{Color.PYRMETHUS_ORANGE}WS not connected. Dropped: {msg}{Color.RESET}")
            return
        try:
            await ws.send(json.dumps(msg))
            logger.debug(f"{'Private' if is_private else 'Public'} WS → {msg}")
        except websockets.exceptions.ConnectionClosed:
            state.is_connected = False
            logger.error(f"{Color.RED}WS send failed: connection closed.{Color.RESET}")
        except Exception as e:
            state.is_connected = False
            logger.error(f"{Color.RED}WS send failed: {e}.{Color.RESET}")

    async def _resubscribe_topics(self, state: ConnectionState, subs: Set[str], url: str, is_private: bool):
        if not state.is_connected or not subs: return
        logger.info(f"{Color.PYRMETHUS_CYAN}Resubscribing to {'private' if is_private else 'public'} topics...{Color.RESET}")
        await self._send_ws_message(state.websocket_instance, {"op": "subscribe", "args": list(subs)}, is_private)

    def _validate_websocket_message(self, message: Dict[str, Any]) -> bool:
        if not isinstance(message, dict):
            logger.warning(f"{Color.PYRMETHUS_YELLOW}Invalid WS message format (not dict): {message}{Color.RESET}")
            return False
        if "topic" not in message and "op" not in message and "success" not in message:
            logger.warning(f"{Color.PYRMETHUS_YELLOW}WS message missing 'topic', 'op', or 'success' key: {message}{Color.RESET}")
            return False
        return True

    async def _message_receiving_loop(self, ws: websockets.WebSocketClientProtocol, state: ConnectionState, auth: bool, cb: Callable):
        while state.is_active:
            raw_message, parsed_message = None, None
            try:
                raw_message = await asyncio.wait_for(ws.recv(), timeout=self.ws_ping_interval + self.ws_ping_timeout)
                parsed_message = json.loads(raw_message)
                logger.debug(f"{'Private' if auth else 'Public'} WS ← {parsed_message}")

                # Validate the incoming message
                if not self._validate_websocket_message(parsed_message):
                    continue

                if parsed_message.get("op") == "pong":
                    state.last_pong_time = time.time()
                    continue
                if auth and parsed_message.get("op") == "auth":
                    if parsed_message.get("success"): state._ws_authenticated_event.set()
                    else:
                        logger.error(f"{Color.RED}WS auth failed: {parsed_message.get('retMsg')}{Color.RESET}")
                        break
                    continue

                if self.ws_kline_normalize_timestamp and isinstance(parsed_message, dict) and parsed_message.get("topic", "").startswith("kline"):
                    if "data" in parsed_message and isinstance(parsed_message["data"], list):
                        for kline in parsed_message["data"]:
                            if "timestamp" not in kline:
                                for candidate in ["start", "startTime", "openTime"]:
                                    if candidate in kline:
                                        kline["timestamp"] = kline[candidate]
                                        break
                try:
                    processed_msg = self._convert_to_decimal_recursive(parsed_message)
                    if asyncio.iscoroutinefunction(cb): await cb(processed_msg)
                    else: cb(processed_msg)
                except Exception as cb_exc:
                    logger.error(f"{Color.RED}Exception in WebSocket callback for message: {json.dumps(parsed_message)}{Color.RESET}")
                    logger.error(f"{Color.RED}Callback Error: {cb_exc}\n{traceback.format_exc()}{Color.RESET}")

            except asyncio.TimeoutError:
                if state.last_pong_time < state.last_ping_time:
                    logger.error(f"{Color.RED}WS pong timeout. Reconnecting.{Color.RESET}")
                    break
                else:
                    state.last_ping_time = time.time()
                    try: await ws.ping()
                    except Exception as e: logger.error(f"{Color.RED}WS ping failed: {e}{Color.RESET}"); break
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"{Color.PYRMETHUS_ORANGE}WS closed: {e}. Reconnecting.{Color.RESET}"); break
            except json.JSONDecodeError:
                logger.error(f"{Color.RED}Failed to decode JSON: {raw_message}{Color.RESET}"); continue
            except Exception as e:
                logger.error(f"{Color.RED}Error in WS listener: {e}\n{traceback.format_exc()}{Color.RESET}"); break

        logger.info(f"{Color.PYRMETHUS_GREY}WS message loop ended.{Color.RESET}")
        state.is_connected = state.is_authenticated = False
        if auth: state._ws_authenticated_event.clear()
        if ws:
            try:
                await ws.close()
            except Exception as e:
                logger.warning(f"{Color.PYRMETHUS_YELLOW}Error closing websocket in message loop: {e}{Color.RESET}")
        state.websocket_instance = None

    async def start_websocket_listener(self, url: str, state: ConnectionState, subs: Set[str], resub: Callable, cb: Callable, auth: bool = False) -> asyncio.Task:
        async def _listener_task():
            backoff = ExponentialBackoff(initial_delay=WS_RECONNECT_DELAY, max_delay=60)
            while state.is_active:
                ws = None
                try:
                    ws = await self._connect_websocket(url, state, subs, resub, cb, auth)
                    if not ws:
                        delay = backoff.next()
                        logger.info(f"{Color.PYRMETHUS_ORANGE}Connection failed. Retrying in {delay:.1f}s...{Color.RESET}")
                        await asyncio.sleep(delay)
                        continue
                    backoff.reset() # Reset backoff on successful connection
                    await self._message_receiving_loop(ws, state, auth, cb)
                except Exception as e:
                    logger.error(f"{Color.RED}Unhandled exception in WS listener task: {e}\n{traceback.format_exc()}{Color.RESET}")
                
                # This block now runs after the message loop ends due to disconnection or error
                if state.is_active:
                    delay = backoff.next()
                    logger.info(f"{Color.PYRMETHUS_ORANGE}WebSocket disconnected. Reconnecting in {delay:.1f}s...{Color.RESET}")
                    await asyncio.sleep(delay)
            logger.info(f"{Color.PYRMETHUS_GREY}Exiting WS listener task for {url}.{Color.RESET}")

        state.listener_task = asyncio.create_task(_listener_task())
        return state.listener_task

    def start_private_websocket_listener(self, cb: Callable, delay: int = WS_RECONNECT_DELAY) -> asyncio.Task:
        return self.start_websocket_listener(self.base_ws_private_url, self.private_connection_state, self._private_subscriptions, lambda: self._resubscribe_topics(self.private_connection_state, self._private_subscriptions, self.base_ws_private_url, True), cb, True)
    def start_public_websocket_listener(self, cb: Callable, delay: int = WS_RECONNECT_DELAY) -> asyncio.Task:
        return self.start_websocket_listener(self.base_ws_public_linear_url, self.public_connection_state, self._public_subscriptions, lambda: self._resubscribe_topics(self.public_connection_state, self._public_subscriptions, self.base_ws_public_linear_url, False), cb, False)

    async def subscribe_ws_private_topic(self, topic: str):
        self._private_subscriptions.add(topic)
        if self.private_connection_state.is_connected:
            await self._subscribe_ws_topic(self.private_connection_state.websocket_instance, self._private_subscriptions, topic, True)
    async def subscribe_ws_public_topic(self, topic: str):
        self._public_subscriptions.add(topic)
        if self.public_connection_state.is_connected:
            await self._subscribe_ws_topic(self.public_connection_state.websocket_instance, self._public_subscriptions, topic, False)
    async def _subscribe_ws_topic(self, ws: Optional[websockets.WebSocketClientProtocol], subs: Set[str], topic: str, is_private: bool):
        if topic in subs: return
        logger.info(f"{Color.PYRMETHUS_CYAN}Subscribing to: '{topic}'...{Color.RESET}")
        await self._send_ws_message(ws, {"op": "subscribe", "args": [topic]}, is_private)

# --- Example Usage with Best-Practice Callback Dispatcher ---
async def main_example():
    print(f"{Color.BOLD}--- Pyrmethus's Bybit Contract API Demonstration ---{Color.RESET}")
    api = None
    try:
        api = BybitContractAPI(testnet=True)

        # --- Define Specific Handlers for each data type ---
        async def handle_kline_update(message: dict):
            print(f"{Color.PYRMETHUS_GREEN}Kline Update Received:{Color.RESET} {message.get('topic')}")
            # Your pandas logic here is now SAFE.
            # e.g., import pandas as pd; df = pd.DataFrame(message['data'])
            # df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            # print(df.tail(1))

        async def handle_ticker_update(message: dict):
            print(f"{Color.PYRMETHUS_BLUE}Ticker Update Received:{Color.RESET} {message.get('topic')}")
            # Handle ticker data...

        async def handle_position_update(message: dict):
            print(f"{Color.PYRMETHUS_PURPLE}Position Update Received:{Color.RESET} Topic: {message.get('topic')}")
            # Handle position data...

        # --- Create Robust "Dispatcher" Callbacks ---
        async def public_callback_dispatcher(message: dict):
            """This function receives ALL public messages and routes them."""
            topic = message.get("topic", "")
            if topic.startswith("kline"):
                await handle_kline_update(message)
            elif topic.startswith("tickers"):
                await handle_ticker_update(message)
            else:
                # Handle other public topics or log them
                print(f"{Color.PYRMETHUS_GREY}Unhandled Public Msg:{Color.RESET} {message}")

        async def private_callback_dispatcher(message: dict):
            """This function receives ALL private messages and routes them."""
            topic = message.get("topic", "")
            if topic == "position":
                await handle_position_update(message)
            # Add handlers for "order", "wallet", etc.
            else:
                print(f"{Color.PYRMETHUS_GREY}Unhandled Private Msg:{Color.RESET} {message}")

        # --- Start Listeners with the Dispatcher Callbacks ---
        print(f"\n{Color.BOLD}--- Starting WebSocket Listeners ---{Color.RESET}")
        api.start_private_websocket_listener(private_callback_dispatcher)
        api.start_public_websocket_listener(public_callback_dispatcher)

        # Allow time for connections
        await asyncio.sleep(5)

        # --- Subscribe to Topics ---
        await api.subscribe_ws_private_topic("position")
        await api.subscribe_ws_public_topic("kline.1.BTCUSD")
        await api.subscribe_ws_public_topic("tickers.BTCUSD") # Specific ticker for cleaner output

        print(f"\n{Color.PYRMETHUS_YELLOW}Listeners active. Monitoring topics for 30s...{Color.RESET}")
        await asyncio.sleep(30)

    except Exception as e:
        print(f"{Color.RED}An unexpected error occurred in main_example: {e}\n{traceback.format_exc()}{Color.RESET}")
    finally:
        if api:
            await api.close_connections()

if __name__ == "__main__":
    try:
        asyncio.run(main_example())
    except KeyboardInterrupt:
        print(f"\n{Color.PYRMETHUS_GREY}Demonstration interrupted.{Color.RESET}")