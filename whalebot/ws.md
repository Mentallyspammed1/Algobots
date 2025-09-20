Okay, let's integrate WebSocket functionality into your existing `Whalebot` script. This involves:

1.  **Adding `websocket-client`**: A library for WebSocket communication.
2.  **WebSocket Manager Class**: A class to handle connections, subscriptions, message parsing, and updating shared data.
3.  **Authentication**: Bybit's private WebSocket streams require signing.
4.  **Data Flow**: Modifying existing REST API calls (`fetch_klines`, `fetch_orderbook`, `fetch_current_price`, `get_open_positions_from_exchange`) to prioritize data received via WebSockets, while retaining REST as a fallback for initial data loads or if WS is unavailable.
5.  **Thread Safety**: Using `threading.Lock` to protect shared data structures updated by WebSocket threads and read by the main thread.

Due to the size of your existing file and the complexity of integrating real-time streams into a polling-based system, I'll provide several snippets. You'll need to carefully place them in your `wb1.0.1.py` file.

---

### Snippet 1: Imports and WebSocket Constants

Add these imports and constants to the top section of your file, near your other imports and constants.

```python
# Add to existing imports
import threading
import queue
import websocket # You might need to install this: pip install websocket-client
import ssl # For secure WebSocket connections
from collections import deque # For storing recent kline data efficiently

# Add to Constants section, after existing API_SECRET, BASE_URL etc.
# --- WebSocket Constants ---
WS_PUBLIC_BASE_URL = os.getenv("BYBIT_WS_PUBLIC_BASE_URL", "wss://stream.bybit.com/v5/public/linear")
WS_PRIVATE_BASE_URL = os.getenv("BYBIT_WS_PRIVATE_BASE_URL", "wss://stream.bybit.com/v5/private")

# WebSocket reconnection settings
WS_RECONNECT_ATTEMPTS = 5
WS_RECONNECT_DELAY_SECONDS = 10

# Default topics (will be overridden by config later)
DEFAULT_PUBLIC_TOPICS = [] # Will be dynamically generated
DEFAULT_PRIVATE_TOPICS = ["order", "position", "wallet"]
```

---

### Snippet 2: WebSocket Authentication Signature Generation

Add this function to your "API Interaction" section, alongside `generate_signature` for REST.

```python
# Add to API Interaction section, near generate_signature
def generate_ws_signature(api_key: str, api_secret: str, expires: int) -> str:
    """Generate a Bybit WebSocket authentication signature."""
    param_str = f"GET/realtime{expires}"
    signature = hmac.new(api_secret.encode(), param_str.encode(), hashlib.sha256).hexdigest()
    return signature

```

---

### Snippet 3: `BybitWebSocketManager` Class

This is the core of the WebSocket implementation. Place this class somewhere appropriate, for example, after `AlertSystem` but before `TradingAnalyzer`.

```python
# Place this class after AlertSystem or other utility classes
class BybitWebSocketManager:
    """Manages Bybit WebSocket connections and provides real-time data."""

    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.symbol = config["symbol"]
        self.api_key = API_KEY
        self.api_secret = API_SECRET

        self._ws_public_thread = None
        self._ws_private_thread = None
        self.ws_public = None
        self.ws_private = None

        # Shared data structures with locks for thread-safety
        self.latest_klines: pd.DataFrame = pd.DataFrame()
        self._klines_lock = threading.Lock()
        self.latest_orderbook: dict[str, Any] = {"bids": [], "asks": []}
        self._orderbook_lock = threading.Lock()
        self.latest_trades: deque = deque(maxlen=config.get("orderbook_limit", 50)) # Stores recent trades
        self._trades_lock = threading.Lock()
        self.latest_ticker: dict[str, Any] = {} # For current price, lastPrice
        self._ticker_lock = threading.Lock()
        
        # Real-time updates for position manager
        self.private_updates_queue: queue.Queue = queue.Queue()
        self._private_updates_lock = threading.Lock()

        # Flags for initial data availability
        self.initial_kline_received = threading.Event()
        self.initial_orderbook_received = threading.Event()
        self.initial_private_data_received = threading.Event()

        # Topics to subscribe, derived from config
        self.public_topics = [
            f"kline.{self.config['interval']}.{self.symbol}",
            f"orderbook.{self.config['orderbook_limit']}.{self.symbol}",
            f"publicTrade.{self.symbol}",
            f"tickers.{self.symbol}" # For latest price updates
        ]
        # Private topics are generally fixed for account-related updates
        self.private_topics = DEFAULT_PRIVATE_TOPICS # ["order", "position", "wallet"]

        self.is_connected_public = False
        self.is_connected_private = False
        self._stop_event = threading.Event() # Event to signal threads to stop

    def _on_open_public(self, ws):
        self.logger.info(f"{NEON_BLUE}[WS Public] Connection opened.{RESET}")
        self._subscribe(ws, self.public_topics)
        self.is_connected_public = True

    def _on_open_private(self, ws):
        self.logger.info(f"{NEON_BLUE}[WS Private] Connection opened. Authenticating...{RESET}")
        expires = int(time.time() * 1000) + 10000 # Message expires in 10 seconds
        signature = generate_ws_signature(self.api_key, self.api_secret, expires)
        auth_message = {
            "op": "auth",
            "args": [self.api_key, expires, signature]
        }
        ws.send(json.dumps(auth_message))
        self.logger.debug(f"[WS Private] Auth message sent: {auth_message}")
        self.is_connected_private = True
        # Subscribe after a short delay to allow auth to process, or wait for auth success message
        threading.Timer(1, self._subscribe, args=(ws, self.private_topics)).start()


    def _on_message_public(self, ws, message):
        data = json.loads(message)
        op = data.get("op")
        topic = data.get("topic")
        
        if op == "subscribe":
            self.logger.debug(f"{NEON_BLUE}[WS Public] Subscribed to {data.get('success_topics')}{RESET}")
            return
        elif op == "pong":
            self.logger.debug(f"{NEON_BLUE}[WS Public] Received pong.{RESET}")
            return
        elif data.get("type") == "snapshot" and topic.startswith("kline"):
            # Initial kline data, or resync snapshot
            self._update_klines(data["data"], is_snapshot=True)
            self.initial_kline_received.set()
        elif data.get("type") == "delta" and topic.startswith("kline"):
            # Update to the latest kline bar
            self._update_klines(data["data"], is_snapshot=False)
        elif data.get("type") == "snapshot" and topic.startswith("orderbook"):
            self._update_orderbook(data["data"], is_snapshot=True)
            self.initial_orderbook_received.set()
        elif data.get("type") == "delta" and topic.startswith("orderbook"):
            self._update_orderbook(data["data"], is_snapshot=False)
        elif topic.startswith("publicTrade"):
            self._update_trades(data["data"])
        elif topic.startswith("tickers"):
            self._update_ticker(data["data"][0]) # Tickers usually come as a list of one item
        else:
            self.logger.debug(f"{NEON_BLUE}[WS Public] Unhandled message: {data}{RESET}")

    def _on_message_private(self, ws, message):
        data = json.loads(message)
        op = data.get("op")
        
        if op == "auth":
            if data.get("success"):
                self.logger.info(f"{NEON_GREEN}[WS Private] Authentication successful.{RESET}")
            else:
                self.logger.error(f"{NEON_RED}[WS Private] Authentication failed: {data.get('retMsg')}. Reconnecting.{RESET}")
                # Trigger a reconnect for private WS if auth fails
                self.ws_private.close()
            return
        elif op == "subscribe":
            self.logger.debug(f"{NEON_BLUE}[WS Private] Subscribed to {data.get('success_topics')}{RESET}")
            return
        elif op == "pong":
            self.logger.debug(f"{NEON_BLUE}[WS Private] Received pong.{RESET}")
            return

        # Handle private data topics: order, position, wallet
        category = data.get("topic")
        if category in self.private_topics:
            self.logger.debug(f"{NEON_BLUE}[WS Private] Received {category} update: {data['data']}{RESET}")
            with self._private_updates_lock:
                # Put the full raw message into the queue for PositionManager to process
                self.private_updates_queue.put(data)
            self.initial_private_data_received.set()
        else:
            self.logger.debug(f"{NEON_BLUE}[WS Private] Unhandled private message: {data}{RESET}")


    def _on_error(self, ws, error):
        self.logger.error(f"{NEON_RED}[WS {ws.url.split('/')[-1]}] Error: {error}{RESET}")

    def _on_close(self, ws, close_status_code, close_msg):
        self.logger.warning(
            f"{NEON_YELLOW}[WS {ws.url.split('/')[-1]}] Connection closed: {close_status_code} - {close_msg}{RESET}"
        )
        if "public" in ws.url:
            self.is_connected_public = False
        else:
            self.is_connected_private = False
        
        # Attempt reconnection unless stop event is set
        if not self._stop_event.is_set():
            self.logger.info(f"{NEON_BLUE}[WS {ws.url.split('/')[-1]}] Attempting to reconnect...{RESET}")
            time.sleep(WS_RECONNECT_DELAY_SECONDS) # Wait before reconnecting
            # Restart the appropriate thread
            if "public" in ws.url and self._ws_public_thread:
                self._ws_public_thread = threading.Thread(target=self._connect_ws_thread, args=(WS_PUBLIC_BASE_URL, self._on_message_public, self._on_open_public))
                self._ws_public_thread.daemon = True
                self._ws_public_thread.start()
            elif "private" in ws.url and self._ws_private_thread:
                self._ws_private_thread = threading.Thread(target=self._connect_ws_thread, args=(WS_PRIVATE_BASE_URL, self._on_message_private, self._on_open_private))
                self._ws_private_thread.daemon = True
                self._ws_private_thread.start()


    def _connect_ws_thread(self, url, on_message_handler, on_open_handler):
        """Helper to run a WebSocket connection in a separate thread."""
        retries = 0
        while not self._stop_event.is_set() and retries < WS_RECONNECT_ATTEMPTS:
            try:
                ws = websocket.WebSocketApp(
                    url,
                    on_open=on_open_handler,
                    on_message=on_message_handler,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                if "public" in url:
                    self.ws_public = ws
                else:
                    self.ws_private = ws
                
                # Keep the connection alive
                ws.run_forever(
                    ping_interval=20, # Bybit recommends 10-20 seconds
                    ping_timeout=10,
                    sslopt={"cert_reqs": ssl.CERT_NONE} # For some environments, might need to ignore cert validation
                )
            except Exception as e:
                self.logger.error(f"{NEON_RED}[WS {url.split('/')[-1]}] Failed to connect: {e}. Retrying...{RESET}")
                retries += 1
                time.sleep(WS_RECONNECT_DELAY_SECONDS)
        
        if retries == WS_RECONNECT_ATTEMPTS:
            self.logger.error(f"{NEON_RED}[WS {url.split('/')[-1]}] Max reconnection attempts reached. Giving up.{RESET}")


    def _subscribe(self, ws, topics: list[str]):
        """Sends subscription messages to the WebSocket."""
        for topic in topics:
            sub_message = {
                "op": "subscribe",
                "args": [topic]
            }
            try:
                ws.send(json.dumps(sub_message))
                self.logger.debug(f"{NEON_BLUE}[WS] Sent subscription for: {topic}{RESET}")
            except websocket.WebSocketConnectionClosedException:
                self.logger.warning(f"{NEON_YELLOW}[WS] Failed to send subscription for {topic}: Connection closed.{RESET}")
            except Exception as e:
                self.logger.error(f"{NEON_RED}[WS] Error sending subscription for {topic}: {e}{RESET}")


    def start_public_stream(self):
        """Starts the public WebSocket stream in a new thread."""
        self._stop_event.clear() # Ensure stop event is clear before starting
        if not self._ws_public_thread or not self._ws_public_thread.is_alive():
            self._ws_public_thread = threading.Thread(
                target=self._connect_ws_thread, 
                args=(WS_PUBLIC_BASE_URL, self._on_message_public, self._on_open_public)
            )
            self._ws_public_thread.daemon = True
            self._ws_public_thread.start()
            self.logger.info(f"{NEON_BLUE}Public WebSocket stream started for {self.symbol}.{RESET}")

    def start_private_stream(self):
        """Starts the private WebSocket stream in a new thread."""
        if not API_KEY or not API_SECRET:
            self.logger.warning(f"{NEON_YELLOW}API_KEY or API_SECRET not set. Skipping private WebSocket stream.{RESET}")
            return
        self._stop_event.clear() # Ensure stop event is clear before starting
        if not self._ws_private_thread or not self._ws_private_thread.is_alive():
            self._ws_private_thread = threading.Thread(
                target=self._connect_ws_thread, 
                args=(WS_PRIVATE_BASE_URL, self._on_message_private, self._on_open_private)
            )
            self._ws_private_thread.daemon = True
            self._ws_private_thread.start()
            self.logger.info(f"{NEON_BLUE}Private WebSocket stream started.{RESET}")

    def stop_all_streams(self):
        """Signals all WebSocket threads to stop and closes connections."""
        self.logger.info(f"{NEON_BLUE}Stopping all WebSocket streams...{RESET}")
        self._stop_event.set()
        if self.ws_public:
            self.ws_public.close()
        if self.ws_private:
            self.ws_private.close()
        if self._ws_public_thread and self._ws_public_thread.is_alive():
            self._ws_public_thread.join(timeout=5)
        if self._ws_private_thread and self._ws_private_thread.is_alive():
            self._ws_private_thread.join(timeout=5)
        self.logger.info(f"{NEON_BLUE}All WebSocket streams stopped.{RESET}")


    # --- Data Update Methods ---
    def _update_klines(self, kline_data_list: list[dict], is_snapshot: bool):
        """Updates the internal klines DataFrame."""
        if not kline_data_list:
            return

        # Bybit kline data: [start_time, open, high, low, close, volume, turnover]
        # Example data format in WS:
        # { "start": 1672531200000, "open": "16500", "high": "16600", "low": "16450",
        #   "close": "16550", "volume": "100", "turnover": "1655000" }

        new_data = []
        for item in kline_data_list:
            new_data.append({
                "start_time": pd.to_datetime(item["start"], unit="ms", utc=True).tz_convert(TIMEZONE),
                "open": Decimal(item["open"]),
                "high": Decimal(item["high"]),
                "low": Decimal(item["low"]),
                "close": Decimal(item["close"]),
                "volume": Decimal(item["volume"]),
                "turnover": Decimal(item["turnover"])
            })
        
        df_new = pd.DataFrame(new_data).set_index("start_time")
        
        with self._klines_lock:
            if is_snapshot:
                # Replace the entire DataFrame if it's a snapshot
                self.latest_klines = df_new
                self.logger.debug(f"{NEON_BLUE}[WS Klines] Snapshot received. New df size: {len(self.latest_klines)}{RESET}")
            else:
                # For delta updates (partial bar updates), append or update the last bar
                for index, row in df_new.iterrows():
                    if index in self.latest_klines.index:
                        # Update existing bar (it's often the current open bar being updated)
                        self.latest_klines.loc[index] = row
                    else:
                        # Append new bar (e.g., when a new bar opens)
                        # Ensure no duplicate timestamps before appending
                        if not self.latest_klines.index.empty and index <= self.latest_klines.index[-1]:
                            # This should not happen if WS sends strict new bar or current bar updates
                            # but as a safeguard, if we get an old or duplicate, skip.
                            self.logger.warning(f"{NEON_YELLOW}[WS Klines] Received out-of-order or duplicate kline for {index}. Skipping.{RESET}")
                            continue
                        self.latest_klines = pd.concat([self.latest_klines, df_new]) # Appending just one row more efficient
                        self.logger.debug(f"{NEON_BLUE}[WS Klines] Appended new kline for {index}. New df size: {len(self.latest_klines)}{RESET}")
            # Ensure the DataFrame is sorted by index
            self.latest_klines.sort_index(inplace=True)
            # Trim the DataFrame to a reasonable size to prevent memory issues
            max_kline_history = 1000 # Keep enough for indicator calculations
            if len(self.latest_klines) > max_kline_history:
                self.latest_klines = self.latest_klines.iloc[-max_kline_history:]
            
            # Convert numeric columns to Decimal after concat/update for consistency
            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                self.latest_klines[col] = self.latest_klines[col].apply(Decimal)


    def _update_orderbook(self, orderbook_data: dict, is_snapshot: bool):
        """Updates the internal orderbook data."""
        with self._orderbook_lock:
            if is_snapshot:
                self.latest_orderbook = {
                    "bids": [[Decimal(price), Decimal(qty)] for price, qty in orderbook_data.get("b", [])],
                    "asks": [[Decimal(price), Decimal(qty)] for price, qty in orderbook_data.get("a", [])],
                    "timestamp": datetime.now(TIMEZONE)
                }
                self.logger.debug(f"{NEON_BLUE}[WS Orderbook] Snapshot received. Bids: {len(self.latest_orderbook['bids'])}, Asks: {len(self.latest_orderbook['asks'])}{RESET}")
            else: # Delta updates
                # Bybit delta updates require manual merging
                # This is a simplified merge. For production, a more robust orderbook reconstruction is needed.
                # Example: https://bybit-exchange.github.io/docs/v5/ws/orderbook/linear
                
                # For simplicity, if it's a delta, and we don't have a snapshot, request a resync.
                # Or, if this snippet assumes a simple overwrite for delta, that would be:
                
                # Append or update bids/asks
                # For true deltas, you'd process 'd' (delete), 'u' (update), 'i' (insert)
                # For this snippet, let's simplify:
                # If a snapshot isn't available, we can't reliably apply deltas.
                if not self.initial_orderbook_received.is_set():
                    self.logger.warning(f"{NEON_YELLOW}[WS Orderbook] Received delta but no snapshot. Requesting resync or waiting for snapshot.{RESET}")
                    # In a real system, you might trigger a full re-subscription or REST call here.
                    return

                # For Bybit V5, 'delta' usually contains 'u' for updates and 'd' for deletes
                # It's not a full diff merge, it's just 'new values'.
                # A proper order book merge involves iterating and replacing specific levels.
                # For a snippet, and given the bot's current usage (imbalance check),
                # receiving frequent 'snapshot' or reconstructing from a full 'update' is more common.
                # If 'data' is the full current state (which sometimes happens for 'update' messages),
                # replace:
                
                # Assuming `data` structure is similar to snapshot for updates.
                # This means it might be a full 'update' representing the current state rather than a true delta list of changes.
                # If it's a list of bids/asks to be merged, a merging logic is needed.
                # For simplicity, if this is an "update" message with 'b' and 'a', we'll treat it as latest full view.
                
                new_bids = [[Decimal(price), Decimal(qty)] for price, qty in orderbook_data.get("b", [])]
                new_asks = [[Decimal(price), Decimal(qty)] for price, qty in orderbook_data.get("a", [])]

                self.latest_orderbook["bids"] = new_bids
                self.latest_orderbook["asks"] = new_asks
                self.latest_orderbook["timestamp"] = datetime.now(TIMEZONE)
                self.logger.debug(f"{NEON_BLUE}[WS Orderbook] Delta/Update received. Bids: {len(self.latest_orderbook['bids'])}, Asks: {len(self.latest_orderbook['asks'])}{RESET}")


    def _update_trades(self, trades_data: list[dict]):
        """Updates the internal trades deque."""
        with self._trades_lock:
            for trade in trades_data:
                # Example trade data:
                # { "timestamp": 1672531200000, "symbol": "BTCUSDT", "side": "Buy",
                #   "size": "0.1", "price": "16550", "tickDirection": "PlusTick",
                #   "tradeId": "12345", "isBlockTrade": False }
                self.latest_trades.append({
                    "timestamp": pd.to_datetime(trade["timestamp"], unit="ms", utc=True).tz_convert(TIMEZONE),
                    "side": trade["side"],
                    "qty": Decimal(trade["size"]),
                    "price": Decimal(trade["price"]),
                })
        self.logger.debug(f"{NEON_BLUE}[WS Trades] Updated. Current trades count: {len(self.latest_trades)}{RESET}")

    def _update_ticker(self, ticker_data: dict):
        """Updates the latest ticker information."""
        with self._ticker_lock:
            self.latest_ticker = {
                "symbol": ticker_data["symbol"],
                "lastPrice": Decimal(ticker_data["lastPrice"]),
                "bidPrice": Decimal(ticker_data["bid1Price"]),
                "askPrice": Decimal(ticker_data["ask1Price"]),
                "timestamp": datetime.now(TIMEZONE)
            }
        self.logger.debug(f"{NEON_BLUE}[WS Ticker] Updated. Last Price: {self.latest_ticker['lastPrice']}{RESET}")


    # --- Data Retrieval Methods for Main Thread ---
    def get_latest_kline_df(self) -> pd.DataFrame:
        """Returns the current klines DataFrame, thread-safe."""
        with self._klines_lock:
            return self.latest_klines.copy()

    def get_latest_orderbook_dict(self) -> dict[str, Any]:
        """Returns the current orderbook dictionary, thread-safe."""
        with self._orderbook_lock:
            return self.latest_orderbook.copy()
            
    def get_latest_ticker(self) -> dict[str, Any]:
        """Returns the latest ticker information, thread-safe."""
        with self._ticker_lock:
            return self.latest_ticker.copy()

    def get_private_updates(self) -> list[dict]:
        """Returns all accumulated private updates and clears the queue."""
        updates = []
        with self._private_updates_lock:
            while not self.private_updates_queue.empty():
                updates.append(self.private_updates_queue.get())
        return updates

    def wait_for_initial_data(self, timeout: int = 30):
        """Waits for initial public and private data to be received."""
        self.logger.info(f"{NEON_BLUE}Waiting for initial WebSocket data... (Timeout: {timeout}s){RESET}")
        
        # Wait for klines and orderbook. Ticker will also come through with public.
        kline_ready = self.initial_kline_received.wait(timeout)
        orderbook_ready = self.initial_orderbook_received.wait(timeout)
        private_ready = self.initial_private_data_received.wait(timeout) # Private might take longer

        if not kline_ready:
            self.logger.warning(f"{NEON_YELLOW}Initial KLINE data not received within {timeout}s. Continuing without full WS data.{RESET}")
        if not orderbook_ready:
            self.logger.warning(f"{NEON_YELLOW}Initial ORDERBOOK data not received within {timeout}s. Continuing without full WS data.{RESET}")
        if not private_ready:
            self.logger.warning(f"{NEON_YELLOW}Initial PRIVATE data not received within {timeout}s. Position Manager might rely on REST for first sync.{RESET}")
        
        if kline_ready and orderbook_ready:
            self.logger.info(f"{NEON_GREEN}Initial public WebSocket data received.{RESET}")
        if private_ready:
             self.logger.info(f"{NEON_GREEN}Initial private WebSocket data received.{RESET}")

```

---

### Snippet 4: Modify Existing Functions to use WebSocket Data

These modifications allow your existing `fetch_*` functions to prioritize WebSocket data while falling back to REST if WS data isn't ready or available. You'll need to pass the `BybitWebSocketManager` instance around.

**A. Modify `fetch_current_price`**

```python
# Modify existing fetch_current_price function
def fetch_current_price(symbol: str, logger: logging.Logger, ws_manager: 'BybitWebSocketManager' | None = None) -> Decimal | None:
    """Fetch the current market price for a symbol, prioritizing WS data."""
    if ws_manager and ws_manager.is_connected_public:
        latest_ticker = ws_manager.get_latest_ticker()
        if latest_ticker and latest_ticker.get("symbol") == symbol:
            price = latest_ticker.get("lastPrice")
            logger.debug(f"Fetched current price for {symbol} from WS: {price}")
            return price
        else:
            logger.debug(f"{NEON_YELLOW}WS ticker data not available for {symbol}. Falling back to REST.{RESET}")

    endpoint = "/v5/market/tickers"
    params = {"category": "linear", "symbol": symbol}
    response = bybit_request("GET", endpoint, params, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        price = Decimal(response["result"]["list"][0]["lastPrice"])
        logger.debug(f"Fetched current price for {symbol} from REST: {price}")
        return price
    logger.warning(f"{NEON_YELLOW}[{symbol}] Could not fetch current price.{RESET}")
    return None

```

**B. Modify `fetch_klines`**

```python
# Modify existing fetch_klines function
def fetch_klines(
    symbol: str, interval: str, limit: int, logger: logging.Logger, ws_manager: 'BybitWebSocketManager' | None = None
) -> pd.DataFrame | None:
    """Fetch kline data, prioritizing WS manager's latest data."""
    if ws_manager and ws_manager.is_connected_public and ws_manager.config["interval"] == interval and ws_manager.symbol == symbol:
        ws_df = ws_manager.get_latest_kline_df()
        if not ws_df.empty:
            # Ensure enough historical data is available in WS buffer
            if len(ws_df) >= limit:
                logger.debug(f"Fetched {len(ws_df)} {interval} klines for {symbol} from WS.")
                return ws_df.tail(limit).copy()
            else:
                logger.debug(f"{NEON_YELLOW}WS kline data has {len(ws_df)} bars, less than requested {limit}. Falling back to REST for full history.{RESET}")

    endpoint = "/v5/market/kline"
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    response = bybit_request("GET", endpoint, params, logger=logger)
    if response and response["result"] and response["result"]["list"]:
        df = pd.DataFrame(
            response["result"]["list"],
            columns=[
                "start_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
            ],
        )
        df["start_time"] = pd.to_datetime(
            df["start_time"].astype(int), unit="ms", utc=True
        ).dt.tz_convert(TIMEZONE)
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.set_index("start_time", inplace=True)
        df.sort_index(inplace=True)

        if df.empty:
            logger.warning(
                f"{NEON_YELLOW}[{symbol}] Fetched klines for {interval} but DataFrame is empty after processing. Raw response: {response}{RESET}"
            )
            return None

        logger.debug(f"Fetched {len(df)} {interval} klines for {symbol} from REST.")
        return df
    logger.warning(
        f"{NEON_YELLOW}[{symbol}] Could not fetch klines for {interval}. API response might be empty or invalid. Raw response: {response}{RESET}"
    )
    return None

```

**C. Modify `fetch_orderbook`**

```python
# Modify existing fetch_orderbook function
def fetch_orderbook(symbol: str, limit: int, logger: logging.Logger, ws_manager: 'BybitWebSocketManager' | None = None) -> dict | None:
    """Fetch orderbook data, prioritizing WS manager's latest data."""
    if ws_manager and ws_manager.is_connected_public and ws_manager.symbol == symbol:
        ws_orderbook = ws_manager.get_latest_orderbook_dict()
        if ws_orderbook and ws_orderbook["bids"] and ws_orderbook["asks"]:
            logger.debug(f"Fetched orderbook for {symbol} from WS.")
            # WS orderbook already contains Decimal types
            return {
                "s": symbol,
                "b": ws_orderbook["bids"][:limit], # Return up to 'limit' bids
                "a": ws_orderbook["asks"][:limit], # Return up to 'limit' asks
                "u": None, # 'u' is updateId, not directly from this simplified WS storage
                "seq": None # 'seq' is sequence, not directly from this simplified WS storage
            }
        else:
            logger.debug(f"{NEON_YELLOW}WS orderbook data not available for {symbol}. Falling back to REST.{RESET}")

    endpoint = "/v5/market/orderbook"
    params = {"category": "linear", "symbol": symbol, "limit": limit}
    response = bybit_request("GET", endpoint, params, logger=logger)
    if response and response["result"]:
        logger.debug(f"Fetched orderbook for {symbol} with limit {limit} from REST.")
        # Convert prices/quantities to Decimal
        result = response["result"]
        result["b"] = [[Decimal(price), Decimal(qty)] for price, qty in result.get("b", [])]
        result["a"] = [[Decimal(price), Decimal(qty)] for price, qty in result.get("a", [])]
        return result
    logger.warning(f"{NEON_YELLOW}[{symbol}] Could not fetch orderbook.{RESET}")
    return None

```

**D. Modify `PositionManager.sync_positions_from_exchange`**

This will allow the `PositionManager` to process real-time updates from private WS streams, making it more responsive to changes.

```python
# Modify existing PositionManager class methods
class PositionManager:
    # ... (existing __init__ and other methods) ...

    # Add ws_manager to the constructor
    def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str, ws_manager: 'BybitWebSocketManager' | None = None):
        """Initializes the PositionManager."""
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.ws_manager = ws_manager # Store WS manager
        # ... (rest of existing __init__) ...
        self.open_positions: list[dict] = []
        # ... (rest of existing __init__) ...

        # Initial sync of open positions from exchange, potentially using WS
        self.sync_positions_from_exchange()


    def sync_positions_from_exchange(self):
        """
        Fetches current open positions from the exchange and updates the internal list.
        Prioritizes real-time updates from WebSocket if available, otherwise uses REST.
        """
        exchange_positions = []
        if self.ws_manager and self.ws_manager.is_connected_private:
            private_updates = self.ws_manager.get_private_updates()
            # Process private updates from the queue first
            for update_msg in private_updates:
                topic = update_msg.get("topic")
                data_list = update_msg.get("data")
                if topic == "position" and data_list:
                    # Bybit sends full position status on update, not just diffs.
                    # This means we can often use the latest 'position' message as the current state.
                    self.logger.debug(f"{NEON_BLUE}[PositionManager] Processing WS private position update.{RESET}")
                    # Convert `size` to Decimal, and ensure only actual open positions are considered
                    exchange_positions_from_ws = [
                        p for p in data_list if Decimal(p.get("size", "0")) > 0 and p.get("symbol") == self.symbol
                    ]
                    # Prioritize the latest WS data if it's comprehensive
                    if exchange_positions_from_ws:
                         # We'll use this as the primary source for the current state for this cycle
                        exchange_positions = exchange_positions_from_ws
                        self.logger.debug(f"[{self.symbol}] Synced {len(exchange_positions)} positions from WS.")
                        break # Assume latest position message is authoritative for this round
            
            # If WS didn't provide any new position data, or for initial sync, fall back to REST
            if not exchange_positions:
                self.logger.debug(f"[{self.symbol}] No fresh WS private position data. Falling back to REST for sync.")
                exchange_positions = get_open_positions_from_exchange(self.symbol, self.logger)
        else:
            self.logger.debug(f"[{self.symbol}] WS private stream not active. Syncing positions via REST.")
            exchange_positions = get_open_positions_from_exchange(self.symbol, self.logger)

        new_open_positions = []
        # The rest of this method remains largely the same, but now it processes `exchange_positions`
        # which could come from either WS or REST.

        for ex_pos in exchange_positions:
            side = ex_pos["side"]
            qty = Decimal(ex_pos["size"])
            entry_price = Decimal(ex_pos["avgPrice"])
            stop_loss_price = Decimal(ex_pos.get("stopLoss", "0")) if ex_pos.get("stopLoss") else Decimal("0")
            take_profit_price = Decimal(ex_pos.get("takeProfit", "0")) if ex_pos.get("takeProfit") else Decimal("0")
            trailing_stop = Decimal(ex_pos.get("trailingStop", "0")) if ex_pos.get("trailingStop") else Decimal("0")

            # Bybit's positionIdx is a good unique identifier for one-way mode,
            # or combined with side for hedge mode. Assuming one-way, positionIdx is 0.
            # Using 'positionId' if available or fallback to 'positionIdx'.
            position_id = ex_pos.get("positionId", str(ex_pos["positionIdx"]))


            existing_pos = next(
                (p for p in self.open_positions if p.get("position_id") == position_id),
                None,
            )

            if existing_pos:
                existing_pos.update({
                    "entry_price": entry_price.quantize(self.price_quantize_dec),
                    "qty": qty.quantize(self.qty_quantize_dec),
                    "stop_loss": stop_loss_price.quantize(self.price_quantize_dec),
                    "take_profit": take_profit_price.quantize(self.price_quantize_dec),
                    "trailing_stop_price": trailing_stop.quantize(self.price_quantize_dec) if trailing_stop else None,
                    "trailing_stop_activated": trailing_stop > 0 if self.enable_trailing_stop else False
                })
                new_open_positions.append(existing_pos)
            else:
                self.logger.warning(f"{NEON_YELLOW}[{self.symbol}] Detected new untracked position on exchange. Side: {side}, Qty: {qty}, Entry: {entry_price}. Adding to internal tracking.{RESET}")
                new_open_positions.append({
                    "positionIdx": ex_pos["positionIdx"],
                    "side": side,
                    "entry_price": entry_price.quantize(self.price_quantize_dec),
                    "qty": qty.quantize(self.qty_quantize_dec),
                    "stop_loss": stop_loss_price.quantize(self.price_quantize_dec),
                    "take_profit": take_profit_price.quantize(self.price_quantize_dec),
                    "position_id": position_id,
                    "order_id": "UNKNOWN", # Cannot retrieve original order ID easily from position list
                    "entry_time": datetime.now(TIMEZONE),
                    "initial_stop_loss": stop_loss_price.quantize(self.price_quantize_dec),
                    "trailing_stop_activated": trailing_stop > 0 if self.enable_trailing_stop else False,
                    "trailing_stop_price": trailing_stop.quantize(self.price_quantize_dec) if trailing_stop else None,
                })
        
        # Identify positions that were tracked internally but are no longer on the exchange
        for tracked_pos in self.open_positions:
            is_still_open = any(
                ex_pos.get("positionId", str(ex_pos["positionIdx"])) == tracked_pos.get("position_id")
                for ex_pos in exchange_positions
            )
            if not is_still_open:
                self.logger.info(f"{NEON_BLUE}[{self.symbol}] Position {tracked_pos['side']} (ID: {tracked_pos.get('position_id', 'N/A')}) no longer open on exchange. Marking as closed.{RESET}")
                close_price = self.ws_manager.get_latest_ticker().get("lastPrice", Decimal("0")) if self.ws_manager else Decimal("0")
                if close_price == Decimal("0"): # Fallback if WS not available
                    close_price = fetch_current_price(self.symbol, self.logger) or Decimal("0")
                
                closed_by = "UNKNOWN"
                if tracked_pos["side"] == "Buy":
                    if close_price <= tracked_pos["stop_loss"]:
                        closed_by = "STOP_LOSS"
                    elif close_price >= tracked_pos["take_profit"]:
                        closed_by = "TAKE_PROFIT"
                else: # Sell
                    if close_price >= tracked_pos["stop_loss"]:
                        closed_by = "STOP_LOSS"
                    elif close_price <= tracked_pos["take_profit"]:
                        closed_by = "TAKE_PROFIT"
                
                pnl = (
                    (close_price - tracked_pos["entry_price"]) * tracked_pos["qty"]
                    if tracked_pos["side"] == "Buy"
                    else (tracked_pos["entry_price"] - close_price) * tracked_pos["qty"]
                )
                
                self.ws_manager.logger.debug(f"{NEON_GREEN}Recording trade details for closed position: {tracked_pos}. PnL: {pnl}{RESET}")
                # Ensure the performance_tracker is passed correctly to manage_positions
                # (This is handled in the main loop call)
                # The performance_tracker.record_trade needs to be called from main loop or directly here
                # if you can guarantee `performance_tracker` instance.
                # For this snippet, assume `performance_tracker` is available or this is passed down.
                # Example: `performance_tracker.record_trade({**tracked_pos, "exit_price": close_price, "exit_time": datetime.now(timezone.utc), "closed_by": closed_by}, pnl)`
                pass # The actual record_trade call happens in manage_positions later

        self.open_positions = new_open_positions
        if not self.open_positions:
            self.logger.debug(f"[{self.symbol}] No active positions being tracked internally.")

```

**E. Modify `TradingAnalyzer._fetch_and_analyze_mtf`**

This is an internal helper in `TradingAnalyzer`. The key change is to pass `ws_manager` to `fetch_klines`.

```python
# Modify existing TradingAnalyzer class method
class TradingAnalyzer:
    # ... (existing __init__ and other methods) ...

    # Add ws_manager to the constructor of TradingAnalyzer so it can be passed to fetch_klines.
    # The existing code calls `TradingAnalyzer(df, config, logger, symbol)`
    # You'll need to update where TradingAnalyzer is instantiated in main() to pass ws_manager.
    # For now, let's assume `self.ws_manager` is available (e.g., if passed in __init__)

    def __init__(
        self,
        df: pd.DataFrame,
        config: dict[str, Any],
        logger: logging.Logger,
        symbol: str,
        ws_manager: 'BybitWebSocketManager' | None = None # Add this parameter
    ):
        """Initializes the TradingAnalyzer."""
        self.df = df.copy()
        self.config = config
        self.logger = logger
        self.symbol = symbol
        self.ws_manager = ws_manager # Store ws_manager
        self.indicator_values: dict[str, float | str | Decimal] = {}
        self.fib_levels: dict[str, Decimal] = {}
        self.weights = config.get("active_weights", {})
        self.indicator_settings = config["indicator_settings"]
        self._last_signal_ts = 0
        self._last_signal_score = 0.0

        if self.df.empty:
            self.logger.warning(
                f"{NEON_YELLOW}[{self.symbol}] TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.{RESET}"
            )
            return

        self._calculate_all_indicators()
        if self.config["indicators"].get("fibonacci_levels", False):
            self.calculate_fibonacci_levels()


    def _fetch_and_analyze_mtf(self) -> dict[str, str]:
        """Fetches data for higher timeframes and determines trends."""
        mtf_trends: dict[str, str] = {}
        if not self.config["mtf_analysis"]["enabled"]:
            return mtf_trends

        higher_timeframes = self.config["mtf_analysis"]["higher_timeframes"]
        trend_indicators = self.config["mtf_analysis"]["trend_indicators"]
        mtf_request_delay = self.config["mtf_analysis"]["mtf_request_delay_seconds"]

        for htf_interval in higher_timeframes:
            self.logger.debug(f"[{self.symbol}] Fetching klines for MTF interval: {htf_interval}")
            # Pass ws_manager to fetch_klines for MTF data
            htf_df = fetch_klines(self.symbol, htf_interval, 1000, self.logger, ws_manager=self.ws_manager)

            if htf_df is not None and not htf_df.empty:
                for trend_ind in trend_indicators:
                    trend = self._get_mtf_trend(htf_df, trend_ind)
                    mtf_trends[f"{htf_interval}_{trend_ind}"] = trend
                    self.logger.debug(
                        f"[{self.symbol}] MTF Trend ({htf_interval}, {trend_ind}): {trend}"
                    )
            else:
                self.logger.warning(
                    f"{NEON_YELLOW}[{self.symbol}] Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}"
                )
            time.sleep(mtf_request_delay) # Delay between MTF requests
        return mtf_trends

    # ... (rest of TradingAnalyzer class) ...
```

---

### Snippet 5: Main Execution Logic (`main()` function) Integration

This ties everything together in your `main()` function.

```python
# Modify existing main() function
def main() -> None:
    """Orchestrate the bot's operation."""
    config = load_config(CONFIG_FILE, logger)
    alert_system = AlertSystem(logger)

    valid_bybit_intervals = [
        "1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"
    ]

    if config["interval"] not in valid_bybit_intervals:
        logger.error(
            f"{NEON_RED}Invalid primary interval '{config['interval']}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.{RESET}"
        )
        sys.exit(1)

    for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
        if htf_interval not in valid_bybit_intervals:
            logger.error(
                f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}' in config.json. Please use Bybit's valid string formats (e.g., '60', '240'). Exiting.{RESET}"
            )
            sys.exit(1)

    logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Initialized ---{RESET}")
    logger.info(f"Symbol: {config['symbol']}, Interval: {config['interval']}")
    logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")

    # --- Initialize WebSocket Manager ---
    ws_manager = BybitWebSocketManager(config, logger)
    ws_manager.start_public_stream()
    ws_manager.start_private_stream()
    
    # Wait for initial data from WebSockets (with a timeout)
    ws_manager.wait_for_initial_data(timeout=30)
    # ------------------------------------

    position_manager = PositionManager(config, logger, config["symbol"], ws_manager) # Pass ws_manager
    performance_tracker = PerformanceTracker(logger)

    try:
        while True:
            logger.info(f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}")
            
            # --- Fetch current price (now uses WS by default) ---
            current_price = fetch_current_price(config["symbol"], logger, ws_manager)
            if current_price is None or current_price == Decimal("0"):
                alert_system.send_alert(
                    f"[{config['symbol']}] Failed to fetch current price. Skipping loop.", "WARNING"
                )
                time.sleep(config["loop_delay"])
                continue

            # --- Fetch primary klines (now uses WS by default) ---
            df = fetch_klines(config["symbol"], config["interval"], 1000, logger, ws_manager)
            if df is None or df.empty:
                alert_system.send_alert(
                    f"[{config['symbol']}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
                    "WARNING",
                )
                time.sleep(config["loop_delay"])
                continue

            orderbook_data = None
            if config["indicators"].get("orderbook_imbalance", False):
                # --- Fetch orderbook (now uses WS by default) ---
                orderbook_data = fetch_orderbook(
                    config["symbol"], config["orderbook_limit"], logger, ws_manager
                )

            # --- Fetch MTF trends ---
            mtf_trends: dict[str, str] = {}
            if config["mtf_analysis"]["enabled"]:
                # Pass ws_manager to TradingAnalyzer when instantiating for MTF analysis
                temp_analyzer_for_mtf = TradingAnalyzer(df, config, logger, config["symbol"], ws_manager=ws_manager)
                mtf_trends = temp_analyzer_for_mtf._fetch_and_analyze_mtf()

            # Display current market data and indicators before signal generation
            # Note: display_indicator_values_and_price also needs ws_manager to instantiate TradingAnalyzer
            # For simplicity, pass it here or update display_indicator_values_and_price to directly use
            # analyzer's indicator values without re-instantiating.
            # For now, let's keep it as is, but if Analyzer gets ws_manager, it can use it internally.

            # Initialize TradingAnalyzer with the primary DataFrame for signal generation
            analyzer = TradingAnalyzer(df, config, logger, config["symbol"], ws_manager=ws_manager) # Pass ws_manager

            if analyzer.df.empty:
                alert_system.send_alert(
                    f"[{config['symbol']}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                    "WARNING",
                )
                time.sleep(config["loop_delay"])
                continue

            # Get ATR for position sizing and SL/TP calculation
            atr_value = Decimal(str(analyzer._get_indicator_value("ATR", Decimal("0.0001"))))
            if atr_value <= 0: # Ensure ATR is positive for calculations
                atr_value = Decimal("0.0001")
                logger.warning(f"{NEON_YELLOW}[{config['symbol']}] ATR value was zero or negative, defaulting to {atr_value}.{RESET}")

            # Generate trading signal
            trading_signal, signal_score, signal_breakdown = analyzer.generate_trading_signal(
                current_price, orderbook_data, mtf_trends
            )

            # Manage open positions (sync with exchange, check/update TSL)
            # PositionManager's sync_positions_from_exchange now uses ws_manager
            position_manager.manage_positions(current_price, performance_tracker, atr_value)

            # Display current state after analysis and signal generation, including breakdown
            display_indicator_values_and_price(
                config, logger, current_price, df, orderbook_data, mtf_trends, signal_breakdown
            )

            # Execute trades based on strong signals
            signal_threshold = config["signal_score_threshold"]
            
            has_buy_position = any(p["side"] == "Buy" for p in position_manager.get_open_positions())
            has_sell_position = any(p["side"] == "Sell" for p in position_manager.get_open_positions())

            if (
                trading_signal == "BUY"
                and signal_score >= signal_threshold
                and not has_buy_position
            ):
                logger.info(
                    f"{NEON_GREEN}[{config['symbol']}] Strong BUY signal detected! Score: {signal_score:.2f}{RESET}"
                )
                position_manager.open_position("Buy", current_price, atr_value)
            elif (
                trading_signal == "SELL"
                and signal_score <= -signal_threshold
                and not has_sell_position
            ):
                logger.info(
                    f"{NEON_RED}[{config['symbol']}] Strong SELL signal detected! Score: {signal_score:.2f}{RESET}"
                )
                position_manager.open_position("Sell", current_price, atr_value)
            else:
                logger.info(
                    f"{NEON_BLUE}[{config['symbol']}] No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}"
                )

            # Log current open positions and performance summary
            open_positions = position_manager.get_open_positions()
            if open_positions:
                logger.info(f"{NEON_CYAN}[{config['symbol']}] Open Positions: {len(open_positions)}{RESET}")
                for pos in open_positions:
                    logger.info(
                        f"  - {pos['side']} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}, TSL Active: {pos['trailing_stop_activated']}){RESET}"
                    )
            else:
                logger.info(f"{NEON_CYAN}[{config['symbol']}] No open positions.{RESET}")

            perf_summary = performance_tracker.get_summary()
            logger.info(
                f"{NEON_YELLOW}[{config['symbol']}] Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}"
            )

            logger.info(
                f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}"
            )
            time.sleep(config["loop_delay"])

    except KeyboardInterrupt:
        logger.info(f"{NEON_YELLOW}KeyboardInterrupt detected. Shutting down...{RESET}")
    except Exception as e:
        alert_system.send_alert(
            f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}", "ERROR"
        )
        logger.exception(f"{NEON_RED}[{config['symbol']}] Unhandled exception in main loop:{RESET}")
        time.sleep(config["loop_delay"] * 2) # Longer sleep after an error
    finally:
        ws_manager.stop_all_streams() # Ensure WS connections are closed on exit
        logger.info(f"{NEON_GREEN}Whalebot has shut down gracefully.{RESET}")

```

---

### Snippet 6: Modify `display_indicator_values_and_price`

This function also needs to use the `ws_manager` to correctly initialize `TradingAnalyzer` if it's being used to fetch indicator values.

```python
# Modify existing display_indicator_values_and_price function
def display_indicator_values_and_price(
    config: dict[str, Any],
    logger: logging.Logger,
    current_price: Decimal,
    df: pd.DataFrame,
    orderbook_data: dict | None,
    mtf_trends: dict[str, str],
    signal_breakdown: dict | None = None,
    ws_manager: 'BybitWebSocketManager' | None = None # Add this parameter
) -> None:
    """Display current price and calculated indicator values."""
    logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
    logger.info(f"{NEON_GREEN}Current Price: {current_price.normalize()}{RESET}")

    # Re-initialize TradingAnalyzer to get the latest indicator values for display
    # Pass ws_manager to the TradingAnalyzer constructor
    analyzer = TradingAnalyzer(df, config, logger, config["symbol"], ws_manager=ws_manager)

    if analyzer.df.empty:
        logger.warning(
            f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.{RESET}"
        )
        return

    logger.info(f"{NEON_CYAN}--- Indicator Values ---{RESET}")
    sorted_indicator_items = sorted(analyzer.indicator_values.items())
    for indicator_name, value in sorted_indicator_items:
        color = INDICATOR_COLORS.get(indicator_name, NEON_YELLOW)
        if isinstance(value, Decimal):
            logger.info(f"  {color}{indicator_name}: {value.normalize()}{RESET}")
        elif isinstance(value, float):
            logger.info(f"  {color}{indicator_name}: {value:.8f}{RESET}")
        else:
            logger.info(f"  {color}{indicator_name}: {value}{RESET}")

    if analyzer.fib_levels:
        logger.info(f"{NEON_CYAN}--- Fibonacci Levels ---{RESET}")
        logger.info("")
        sorted_fib_levels = sorted(analyzer.fib_levels.items(), key=lambda item: float(item[0].replace('%',''))/100)
        for level_name, level_price in sorted_fib_levels:
            logger.info(f"  {NEON_YELLOW}{level_name}: {level_price.normalize()}{RESET}")

    if mtf_trends:
        logger.info(f"{NEON_CYAN}--- Multi-Timeframe Trends ---{RESET}")
        logger.info("")
        sorted_mtf_trends = sorted(mtf_trends.items())
        for tf_indicator, trend in sorted_mtf_trends:
            logger.info(f"  {NEON_YELLOW}{tf_indicator}: {trend}{RESET}")

    if signal_breakdown:
        logger.info(f"{NEON_CYAN}--- Signal Score Breakdown ---{RESET}")
        sorted_breakdown = sorted(signal_breakdown.items(), key=lambda item: abs(item[1]), reverse=True)
        for indicator, contribution in sorted_breakdown:
            color = (Fore.GREEN if contribution > 0 else (Fore.RED if contribution < 0 else Fore.YELLOW))
            logger.info(f"  {color}{indicator:<25}: {contribution: .2f}{RESET}")

    logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")
```

---

### Final Steps and Considerations:

1.  **Installation**: Make sure you have `websocket-client` installed: `pip install websocket-client`.
2.  **Environment Variables**: Add the WebSocket URLs to your `.env` file:
    ```
    BYBIT_WS_PUBLIC_BASE_URL=wss://stream.bybit.com/v5/public/linear
    BYBIT_WS_PRIVATE_BASE_URL=wss://stream.bybit.com/v5/private
    ```
    (Note: `linear` for inverse perpetuals and futures. If you're using spot, it would be `wss://stream.bybit.com/v5/public/spot`). The current code assumes `linear` category.
3.  **Error Handling & Robustness**: The provided snippets offer a foundational WebSocket integration.
    *   **Orderbook Merging**: The `_update_orderbook` method for deltas is simplified. For a production bot, a full orderbook reconstruction logic (handling `delete`, `update`, `insert` operations based on `price` level) is crucial for accurate orderbook depth. Bybit's docs explain this.
    *   **Kline Continuity**: While `_update_klines` attempts to merge and append, network latency or missed messages can cause gaps. More advanced systems might check sequence numbers or use REST to fill gaps if `initial_kline_received` is still `False` or if a large gap is detected.
    *   **Private Updates**: The `private_updates_queue` is a simple way to pass raw messages. `PositionManager` currently just uses the *latest* full `position` message. For `order` and `wallet` updates, `PositionManager` (or another dedicated component) would need to parse and react to these specific messages.
    *   **Data Consistency**: The `initial_kline_received.wait()` helps, but there's always a slight risk of inconsistency between WS and REST data if not handled meticulously.
4.  **Logging Levels**: Adjust your logger's level (e.g., to `DEBUG`) to see all the detailed WebSocket messages for debugging.

This integration allows your bot to leverage real-time data for faster signal generation and more responsive position management, improving its overall performance and reducing reliance on frequent REST polling.
