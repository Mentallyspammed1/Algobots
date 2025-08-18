import asyncio
import hashlib
import hmac
import json
import time
import urllib.parse
import logging
import os
import random
from typing import Dict, Any, Optional, Set, Callable

import httpx
import websockets
from dataclasses import dataclass, field
from dotenv import load_dotenv
from decimal import Decimal, InvalidOperation
import traceback

import config

# Load environment variables
load_dotenv(override=True)

# --- Constants ---
DEFAULT_RECV_WINDOW = 10000
MAX_RETRIES = 3
INITIAL_BACKOFF = 1
WS_PING_INTERVAL = 20
WS_PING_TIMEOUT = 10
WS_RECONNECT_DELAY = 5
AUTH_EXPIRES_MS = 30000

# --- Logging & Colors ---
logger = logging.getLogger(__name__)

class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"

# --- Custom Exceptions ---
class BybitAPIError(Exception):
    def __init__(self, ret_code: int, ret_msg: str, original_response: Dict):
        self.ret_code = ret_code
        self.ret_msg = ret_msg
        self.original_response = original_response
        super().__init__(f"Bybit API Error {ret_code}: {ret_msg}")

# --- API Endpoints ---
BYBIT_REST_MAINNET = "https://api.bybit.com"
BYBIT_REST_TESTNET = "https://api-testnet.bybit.com"
BYBIT_WS_PRIVATE_MAINNET = "wss://stream.bybit.com/v5/private"
BYBIT_WS_PRIVATE_TESTNET = "wss://stream-testnet.bybit.com/v5/private"
BYBIT_WS_PUBLIC_LINEAR_MAINNET = "wss://stream.bybit.com/v5/public/linear"
BYBIT_WS_PUBLIC_LINEAR_TESTNET = "wss://stream-testnet.bybit.com/v5/public/linear"

# --- Rate Limiter ---
class RateLimiter:
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = time.time()
            self.calls = [t for t in self.calls if t > now - self.period]
            if len(self.calls) >= self.max_calls:
                wait_time = self.period - (now - self.calls[0])
                await asyncio.sleep(wait_time)
            self.calls.append(time.time())

# --- Connection State ---
@dataclass
class ConnectionState:
    is_connected: bool = False
    is_authenticated: bool = False
    is_active: bool = True
    websocket_instance: Optional[websockets.WebSocketClientProtocol] = None
    listener_task: Optional[asyncio.Task] = None
    auth_event: asyncio.Event = field(default_factory=asyncio.Event)

# --- Exponential Backoff ---
class ExponentialBackoff:
    def __init__(self, initial_delay=5, max_delay=60):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.current_delay = initial_delay

    def next(self) -> float:
        delay = self.current_delay
        self.current_delay = min(self.current_delay * 2, self.max_delay)
        return delay

    def reset(self):
        self.current_delay = self.initial_delay

# --- Main API Client ---
class BybitContractAPI:
    def __init__(self, testnet: bool = False):
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")
        if not api_key or not api_secret:
            raise ValueError("Missing BYBIT_API_KEY or BYBIT_API_SECRET environment variables.")
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip().encode('utf-8')

        self.base_rest_url = BYBIT_REST_TESTNET if testnet else BYBIT_REST_MAINNET
        self.ws_private_url = BYBIT_WS_PRIVATE_TESTNET if testnet else BYBIT_WS_PRIVATE_MAINNET
        self.ws_public_url = BYBIT_WS_PUBLIC_LINEAR_TESTNET if testnet else BYBIT_WS_PUBLIC_LINEAR_MAINNET

        self.client = httpx.AsyncClient(base_url=self.base_rest_url, timeout=30.0)
        self.rate_limiter = RateLimiter(config.API_RATE_LIMIT_CALLS, config.API_RATE_LIMIT_PERIOD)

        self.private_ws = ConnectionState()
        self.public_ws = ConnectionState()
        self._private_subscriptions = set()
        self._public_subscriptions = set()

    async def close_websocket_streams(self):
        logger.info("Closing websocket streams...")
        self.private_ws.is_active = False
        self.public_ws.is_active = False
        for ws_state in [self.private_ws, self.public_ws]:
            if ws_state.listener_task:
                ws_state.listener_task.cancel()
                try:
                    await ws_state.listener_task
                except asyncio.CancelledError:
                    pass
            if ws_state.websocket_instance:
                await ws_state.websocket_instance.close()

    def _generate_signature(self, timestamp, payload):
        param_str = f"{timestamp}{self.api_key}{DEFAULT_RECV_WINDOW}{payload}"
        return hmac.new(self.api_secret, param_str.encode("utf-8"), hashlib.sha256).hexdigest()

    async def _make_request(self, method, endpoint, params=None, signed=True):
        await self.rate_limiter.acquire()
        timestamp = str(int(time.time() * 1000))
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": str(DEFAULT_RECV_WINDOW),
            "Content-Type": "application/json"
        }
        query_string = ""
        if params:
            query_string = urllib.parse.urlencode(sorted(params.items()))

        if signed:
            payload = query_string if method == "GET" else json.dumps(params)
            headers["X-BAPI-SIGN"] = self._generate_signature(timestamp, payload)

        url = f"{self.base_rest_url}{endpoint}"

        retries = 0
        while retries < config.API_REQUEST_RETRIES:
            try:
                if method == "GET":
                    response = await self.client.get(url, params=params, headers=headers)
                elif method == "POST":
                    response = await self.client.post(url, json=params, headers=headers)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                response.raise_for_status()
                data = response.json()
                if data.get("retCode") != 0:
                    raise BybitAPIError(data.get("retCode"), data.get("retMsg"), data)
                return data
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                retries += 1
                if retries < config.API_REQUEST_RETRIES:
                    backoff_delay = config.API_BACKOFF_FACTOR * (2 ** (retries - 1))
                    logger.warning(f"HTTP request failed: {e}. Retrying in {backoff_delay:.2f}s (Attempt {retries}/{config.API_REQUEST_RETRIES})")
                    await asyncio.sleep(backoff_delay)
                else:
                    logger.error(f"HTTP request failed after {config.API_REQUEST_RETRIES} retries: {e}")
                    raise

    async def get_kline_rest_fallback(self, **kwargs): return await self._make_request("GET", "/v5/market/kline", kwargs, signed=False)
    async def get_positions(self, **kwargs): return await self._make_request("GET", "/v5/position/list", kwargs)
    async def trading_stop(self, **kwargs): return await self._make_request("POST", "/v5/position/trading-stop", kwargs)
    async def get_symbol_ticker(self, **kwargs): return await self._make_request("GET", "/v5/market/tickers", kwargs, signed=False)

    async def _websocket_handler(self, url, ws_state, subscriptions, callback, is_private):
        backoff = ExponentialBackoff()
        while ws_state.is_active:
            try:
                async with websockets.connect(url, ping_interval=WS_PING_INTERVAL, ping_timeout=WS_PING_TIMEOUT) as ws:
                    ws_state.websocket_instance = ws
                    ws_state.is_connected = True
                    backoff.reset()
                    logger.info(f"WebSocket connected to {url}")

                    if is_private:
                        expires = int((time.time() + 10) * 1000)
                        signature = hmac.new(self.api_secret, f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
                        await ws.send(json.dumps({"op": "auth", "args": [self.api_key, expires, signature]}))

                    if subscriptions:
                        await ws.send(json.dumps({"op": "subscribe", "args": list(subscriptions)}))

                    async for message in ws:
                        data = json.loads(message)
                        if "op" in data:
                            if data["op"] == "auth" and data["success"]:
                                ws_state.is_authenticated = True
                                ws_state.auth_event.set()
                                logger.info("WebSocket authenticated.")
                            continue
                        await callback(data)
            except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError) as e:
                logger.warning(f"WebSocket disconnected from {url}: {e}")
            except Exception as e:
                logger.error(f"WebSocket error on {url}: {e}")
            finally:
                ws_state.is_connected = ws_state.is_authenticated = False
                ws_state.auth_event.clear()
                if ws_state.is_active:
                    delay = backoff.next()
                    logger.info(f"Reconnecting to {url} in {delay}s...")
                    await asyncio.sleep(delay)

    def start_websocket_listener(self, url, ws_state, subscriptions, callback, is_private) -> asyncio.Task:
        ws_state.is_active = True
        ws_state.listener_task = asyncio.create_task(
            self._websocket_handler(url, ws_state, subscriptions, callback, is_private)
        )
        return ws_state.listener_task

    def start_private_websocket_listener(self, callback) -> asyncio.Task:
        return self.start_websocket_listener(self.ws_private_url, self.private_ws, self._private_subscriptions, callback, True)

    def start_public_websocket_listener(self, callback) -> asyncio.Task:
        return self.start_websocket_listener(self.ws_public_url, self.public_ws, self._public_subscriptions, callback, False)

    async def subscribe_ws_private_topic(self, topic):
        self._private_subscriptions.add(topic)
        if self.private_ws.is_connected and self.private_ws.is_authenticated:
            await self.private_ws.websocket_instance.send(json.dumps({"op": "subscribe", "args": [topic]}))

    async def subscribe_ws_public_topic(self, topic):
        self._public_subscriptions.add(topic)
        if self.public_ws.is_connected:
            await self.public_ws.websocket_instance.send(json.dumps({"op": "subscribe", "args": [topic]}))